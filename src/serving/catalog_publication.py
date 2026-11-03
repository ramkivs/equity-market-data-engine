"""Catalog-backed atomic publication for the selected composite application.

Only pending candidates, affected prior identity groups and catalog
observations for affected identities are parsed during ordinary publication. Canonical delta rows, evidence, identity projections and derived overrides are
detached immutable blobs. Compact metadata remains in the generation JSON.
"""
import copy
import json
from itertools import chain
import os
import sqlite3

from nse_engine import DEFAULT_CONFIG
from nse_engine.compact import normalize_upper_trim
from .baseline import sha256_file
from .continuity_catalog import FORMAT, _metadata, _projection, observations_for_identity, open_catalog, ticker_catalog
from .incremental_registry import RegistryError, _db_path, _json, _open, bindings, inspect
from .incremental_staging import _candidate_path
from . import incremental_staging
from .incremental_drafts import _validate
from .index import load_index
from .symbols import _identity, observed_trading_symbol
from .query import QueryError
from .w2_continuity import build_continuity
from .composite_index import empty as empty_index_delta, file_metadata, compose as compose_index, extract as extract_index, validate as validate_index_delta
from .persistent_index_map import insert as insert_index, from_overlay as index_tree_from_overlay, materialize as materialize_index_tree, validate_header as validate_index_tree
from .composite_blobs import (put as put_blob, schema as blob_schema, validate_references,
                              validate_group_references, group_document, load_group_from_db, sha as blob_sha,
                              validate_override_references, override_document)

LEGACY_FORMAT_ID = 'catalog-composite/1.0'
INLINE_GROUP_FORMAT_ID = 'catalog-composite/2.0'
INLINE_OVERRIDE_FORMAT_ID = 'catalog-composite/3.0'
INLINE_TICKER_FORMAT_ID = 'catalog-composite/4.0'
INLINE_INDEX_FORMAT_ID = 'catalog-composite/5.0'
NO_TICKER_PROOF_FORMAT_ID = 'catalog-composite/6.0'
INLINE_INDEX_TREE_FORMAT_ID = 'catalog-composite/7.0'
FORMAT_ID = 'catalog-composite/8.0'
MAX_PENDING_BYTES = 128 * 1024 * 1024
MAX_PENDING_ROWS = 20000


def _merge_tickers(catalog, rows):
    observations = {}
    for ticker, series, identity, raw, start, end in catalog['observations']:
        observations[(ticker, series, identity, raw)] = [start, end]
    for _, row in rows:
        values = row['source_values']
        ticker = observed_trading_symbol(row)['observed_symbol']
        if not ticker or not isinstance(values.get('series'), str):
            continue
        identity = _identity(row)
        key = (ticker, values['series'], identity, values.get('listing_symbol'))
        span = observations.setdefault(key, [None, None])
        date = row['business_date'] if identity else None
        if date:
            span[0] = date if span[0] is None else min(span[0], date)
            span[1] = date if span[1] is None else max(span[1], date)
    result = [(k[0], k[1], k[2], k[3], v[0], v[1]) for k, v in observations.items()]
    result.sort(key=lambda x: tuple('' if v is None else v for v in x))
    return {'observations': result}


def validate_ticker_delta(catalog):
    import datetime
    if not isinstance(catalog, dict) or set(catalog) != {'observations'} or not isinstance(catalog['observations'], (list, tuple)):
        raise ValueError('invalid incremental ticker census')
    seen = set()
    for row in catalog['observations']:
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            raise ValueError('invalid incremental ticker observation')
        ticker, series, identity, raw, start, end = row
        if (not isinstance(ticker, str) or not ticker or not isinstance(series, str) or
                (identity is not None and (not isinstance(identity, str) or not identity)) or
                (raw is not None and not isinstance(raw, str))):
            raise ValueError('invalid incremental ticker observation identity')
        if identity is None:
            if start is not None or end is not None:
                raise ValueError('invalid uncorrelated ticker dates')
        else:
            for date in (start, end):
                if not isinstance(date, str) or datetime.date.fromisoformat(date).isoformat() != date:
                    raise ValueError('invalid incremental ticker date')
            if start > end:
                raise ValueError('invalid incremental ticker date range')
        key = (ticker, series, identity, raw)
        if key in seen:
            raise ValueError('duplicate incremental ticker observation')
        seen.add(key)


def normalize_ticker_catalog(catalog):
    validate_ticker_delta(catalog)
    observations = [tuple(row) for row in catalog['observations']]
    observations.sort(key=lambda x: tuple('' if value is None else value for value in x))
    return {'observations': observations}


def merge_ticker_catalogs(base, delta):
    """Combine two compact ticker censuses without reading canonical rows."""
    spans = {}
    for ticker, series, identity, raw, start, end in chain(base['observations'], delta['observations']):
        key = (ticker, series, identity, raw)
        current = spans.setdefault(key, [None, None])
        if start:
            current[0] = start if current[0] is None else min(current[0], start)
            current[1] = end if current[1] is None else max(current[1], end)
    rows = [(k[0], k[1], k[2], k[3], v[0], v[1]) for k, v in spans.items()]
    rows.sort(key=lambda row: tuple('' if value is None else value for value in row))
    return {'observations': rows}


def _pending(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone():
        raise RegistryError('no staged candidates')
    if db.execute('SELECT 1 FROM staged_candidates s JOIN accepted a ON a.file_name=s.file_name AND a.date=s.date WHERE s.digest<>a.digest LIMIT 1').fetchone():
        raise RegistryError('staged content disagrees with accepted input identity')
    predicate = " FROM staged_candidates s LEFT JOIN accepted a ON a.file_name=s.file_name AND a.date=s.date WHERE a.file_name IS NULL"
    size = db.execute('SELECT COALESCE(sum(length(CAST(s.record AS BLOB))+length(CAST(s.rows AS BLOB))+length(CAST(s.evidence AS BLOB))),0)' + predicate).fetchone()[0]
    if size > MAX_PENDING_BYTES:
        raise RegistryError('pending publication byte limit exceeded')
    return db.execute('SELECT s.record,s.rows,s.evidence' + predicate + ' ORDER BY s.file_name,s.date,s.digest').fetchall()


def publish(baseline, registry_root, state, saved, history, source_roots):
    from .incremental_publication import _schema, _sha, _w2
    from .composite_binding import ensure_binding
    if incremental_staging.runtime_bindings() != bindings(baseline) or baseline.run_record.get('config', {}).get('config_fingerprint') != DEFAULT_CONFIG.fingerprint():
        raise RegistryError('current engine, runner or config differs from baseline')
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    index, index_hash = load_index(state, baseline)
    cat, meta = open_catalog(baseline, state)
    proof_db = None
    try:
        cat.execute('BEGIN')
        if _metadata(cat) != meta:
            raise RegistryError('continuity catalog changed before publication')
        if meta['format'] != FORMAT:
            raise RegistryError('continuity catalog needs upgrade before publication')
        from .ticker_proofs import FILE as PROOF_FILE, build as build_ticker_proofs, open_proofs, TargetedCatalog
        base_catalog = None
        preview, _ = _open(baseline, path)
        try:
            staged = _pending(preview)
            active_exists = preview.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='composite_active'").fetchone()
            active_row = preview.execute('SELECT a.generation,g.payload FROM composite_active a LEFT JOIN composite_generations g ON g.id=a.generation WHERE a.singleton=1').fetchone() if active_exists else None
            if active_row and (active_row[1] is None or _sha(active_row[1]) != active_row[0]):
                raise RegistryError('active composite pointer is missing or invalid')
            prior_format = json.loads(active_row[1]).get('format') if active_row else None
        finally:
            preview.close()
        if prior_format in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID) and not os.path.lexists(os.path.join(state, PROOF_FILE)):
            raise RegistryError('ticker lookup proofs missing; explicit recovery required')
        proof_meta = build_ticker_proofs(baseline, state, cat, meta)
        proof_db, _, proof_groups = open_proofs(state, meta, proof_meta)
        for text, _, _ in staged:
            rec = json.loads(text)
            finding = inspect(baseline, registry_root, state, saved, history, source_roots,
                              rec['root'], rec['relative_path'], rec['date'], 'publication-check-' + rec['run_id'], rec['bindings'])
            if finding['status'] != 'NEW-UNVALIDATED' or finding['sha256'] != rec['digest']:
                raise RegistryError('pending source changed, duplicated or became accepted')
        ensure_binding(baseline, state, registry_root)
        db, _ = _open(baseline, path)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            _schema(db)
            staged = _pending(db)
            active = db.execute('SELECT generation FROM composite_active WHERE singleton=1').fetchone()
            previous = db.execute('SELECT a.generation,g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation WHERE a.singleton=1').fetchone()
            if active and previous is None:
                raise RegistryError('active composite pointer is missing or invalid')
            if not active:
                accepted = (json.loads(row[0]) for row in db.execute('SELECT record FROM accepted'))
                if (db.execute('SELECT count(*) FROM composite_generations').fetchone()[0] or
                        any(item.get('publication_kind') == 'composite' for item in accepted)):
                    raise RegistryError('active composite pointer is missing or invalid')
            payload = None
            if previous:
                if _sha(previous[1]) != previous[0]:
                    raise RegistryError('active composite digest mismatch')
                payload = json.loads(previous[1])
                if payload.get('format') not in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_FORMAT_ID, INLINE_TICKER_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID, INLINE_GROUP_FORMAT_ID, LEGACY_FORMAT_ID, 'bounded-composite/1.0'):
                    raise RegistryError('unknown active composite format')
                if payload.get('baseline_manifest_sha256') != baseline.manifest_digest or payload.get('baseline_index_sha256') != index_hash:
                    raise RegistryError('active composite baseline/index mismatch')
                if payload.get('format') in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_FORMAT_ID, INLINE_TICKER_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID, INLINE_GROUP_FORMAT_ID, LEGACY_FORMAT_ID) and payload.get('catalog_binding') != meta:
                    raise RegistryError('active composite catalog mismatch')
                if payload.get('format') in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_FORMAT_ID, INLINE_TICKER_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID, INLINE_GROUP_FORMAT_ID):
                    validate_references(payload)
                if payload.get('format') in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_FORMAT_ID, INLINE_TICKER_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID):
                    validate_group_references(payload)
                if payload.get('format') in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_FORMAT_ID, INLINE_TICKER_FORMAT_ID):
                    validate_override_references(payload)
                if payload.get('format') in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_FORMAT_ID):
                    validate_ticker_delta(payload.get('symbol_delta'))
                if payload.get('format') in (INLINE_INDEX_TREE_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID):
                    validate_index_delta(payload.get('index_delta'), payload.get('candidates'))
                if payload.get('format') == FORMAT_ID:
                    validate_index_tree(payload.get('index_tree'), payload.get('candidates'))
                if payload.get('format') in (FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID) and payload.get('ticker_proofs_binding') != proof_meta:
                    raise RegistryError('ticker lookup proof binding mismatch')
            migrating = previous is not None and payload.get('format') == 'bounded-composite/1.0'
            migrate_blobs = previous is not None and payload.get('format') == LEGACY_FORMAT_ID
            migrate_groups = previous is not None and payload.get('format') in (LEGACY_FORMAT_ID, INLINE_GROUP_FORMAT_ID)
            migrate_overrides = previous is not None and payload.get('format') in (LEGACY_FORMAT_ID, INLINE_GROUP_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID)
            migrate_tickers = previous is not None and payload.get('format') in (LEGACY_FORMAT_ID, INLINE_GROUP_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID, INLINE_TICKER_FORMAT_ID)
            migrate_index = previous is not None and payload.get('format') in (LEGACY_FORMAT_ID, INLINE_GROUP_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID, INLINE_TICKER_FORMAT_ID, INLINE_INDEX_FORMAT_ID)
            migrate_proofs = previous is not None and payload.get('format') == NO_TICKER_PROOF_FORMAT_ID
            migrate_tree = previous is not None and payload.get('format') in (LEGACY_FORMAT_ID, INLINE_GROUP_FORMAT_ID, INLINE_OVERRIDE_FORMAT_ID, INLINE_TICKER_FORMAT_ID, INLINE_INDEX_FORMAT_ID, NO_TICKER_PROOF_FORMAT_ID, INLINE_INDEX_TREE_FORMAT_ID)
            if not staged and not migrating and not migrate_tree:
                if previous is None:
                    raise RegistryError('no new records or prior generation')
                db.commit()
                return {'status': 'UNCHANGED', 'generation': previous[0]}
            blob_schema(db)
            if migrate_blobs:
                # One-time migration of the old inline deltas; the source
                # archives and historical canonical baseline are not read.
                from .composite_binding import validate_inline_payload
                validate_inline_payload(db, baseline, payload)
                for candidate in payload['candidates']:
                    source = 'incremental/' + candidate['digest'] + '.rows.jsonl'
                    rows_text, ev = payload['delta'][source], payload['evidence'][candidate['digest']]
                    put_blob(db, rows_text, candidate['rows_sha256'])
                    put_blob(db, ev, candidate['evidence_sha256'])
                    payload['delta'][source] = candidate['rows_sha256']
                    payload['evidence'][candidate['digest']] = candidate['evidence_sha256']
            if migrate_groups:
                for kind in ('w2', 'b2'):
                    groups = payload.get(kind + '_delta')
                    if not isinstance(groups, dict):
                        raise RegistryError('invalid inline identity groups')
                    for identity, rows in list(groups.items()):
                        document = group_document(kind, identity, rows, payload['delta'])
                        text = _json(document)
                        digest = blob_sha(text)
                        put_blob(db, text, digest)
                        groups[identity] = digest
            if migrate_overrides:
                for kind in ('w2', 'b3'):
                    overrides = payload.get(kind + '_overrides')
                    if not isinstance(overrides, dict):
                        raise RegistryError('invalid inline identity overrides')
                    for identity, value in list(overrides.items()):
                        text = _json(override_document(kind, identity, value))
                        digest = blob_sha(text)
                        put_blob(db, text, digest)
                        overrides[identity] = digest
            if migrate_tickers:
                base_catalog = ticker_catalog(cat, meta)  # one-time legacy migration
                # A one-time migration reads retained delta blobs, never old
                # source archives or the historical canonical baseline.
                from .composite_blobs import get as get_blob
                accepted = {}
                for name, date, digest, text in db.execute('SELECT file_name,date,digest,record FROM accepted'):
                    entry = json.loads(text)
                    if entry.get('publication_kind') == 'composite':
                        key = (name, date, digest)
                        if (entry.get('file_name'), entry.get('date'), entry.get('digest')) != key:
                            raise RegistryError('ticker migration accepted registry identity mismatch')
                        accepted[key] = entry
                candidates = payload['candidates']
                if len(candidates) != len(accepted):
                    raise RegistryError('ticker migration accepted registry census mismatch')
                seen_candidates = set()
                def retained_rows():
                    for rec in candidates:
                        key = (rec['file_name'], rec['date'], rec['digest'])
                        entry = accepted.get(key)
                        if key in seen_candidates or entry is None or any(entry.get(k) != v for k, v in rec.items()):
                            raise RegistryError('ticker migration accepted input mismatch')
                        seen_candidates.add(key)
                        source = 'incremental/' + rec['digest'] + '.rows.jsonl'
                        row_text = get_blob(db, payload['delta'][source])
                        evidence_text = get_blob(db, payload['evidence'][rec['digest']])
                        for row in _validate(rec, row_text, evidence_text, baseline):
                            yield source, _projection(row)
                symbol_delta = _merge_tickers({'observations': []}, retained_rows())
                merged = merge_ticker_catalogs(base_catalog, symbol_delta)
                if _json(merged) != _json(normalize_ticker_catalog(payload['symbol_catalog'])):
                    raise RegistryError('inline ticker census disagrees with retained baseline and deltas')
                payload.pop('symbol_catalog')
                payload['symbol_delta'] = symbol_delta
            if migrate_index:
                old_delta_index = extract_index(index, payload['index'], payload['candidates'])
                # One-time proof that every retained file fragment and flag
                # count matches accepted, content-checked incremental rows.
                from .composite_blobs import get as get_blob
                rebuilt = empty_index_delta()
                accepted = {}
                for name, date, digest, text in db.execute('SELECT file_name,date,digest,record FROM accepted'):
                    entry = json.loads(text)
                    if entry.get('publication_kind') == 'composite':
                        key = (name, date, digest)
                        if (entry.get('file_name'), entry.get('date'), entry.get('digest')) != key:
                            raise RegistryError('index migration accepted registry identity mismatch')
                        accepted[key] = entry
                if len(accepted) != len(payload['candidates']):
                    raise RegistryError('index migration accepted registry census mismatch')
                seen = set()
                for rec in payload['candidates']:
                    key = (rec['file_name'], rec['date'], rec['digest'])
                    entry = accepted.get(key)
                    if key in seen or entry is None or any(entry.get(k) != v for k, v in rec.items()):
                        raise RegistryError('index migration accepted input mismatch')
                    seen.add(key)
                    source = 'incremental/' + rec['digest'] + '.rows.jsonl'
                    rows_text = get_blob(db, payload['delta'][source])
                    evidence_text = get_blob(db, payload['evidence'][rec['digest']])
                    rows = _validate(rec, rows_text, evidence_text, baseline)
                    metadata, flags = file_metadata(rec, rows)
                    rebuilt['files'][source] = metadata
                    for name, count in flags.items():
                        rebuilt['flag_census'][name] = rebuilt['flag_census'].get(name, 0) + count
                if rebuilt != old_delta_index:
                    raise RegistryError('inline composite index disagrees with retained incremental rows')
                payload.pop('index')
                payload['index_delta'] = rebuilt
            if migrate_tree:
                payload['index_tree'] = index_tree_from_overlay(db, payload.pop('index_delta'), payload['candidates'])
                payload['format'] = FORMAT_ID
                payload['ticker_proofs_binding'] = proof_meta
            if previous and payload.get('format') == FORMAT_ID:
                validate_references(payload)
                validate_group_references(payload)
                validate_override_references(payload)
            bounded = payload if migrating else None
            if previous and not migrating:
                payload = copy.deepcopy(payload)
                index_tree = payload['index_tree']
                old_delta_catalog = payload['symbol_delta']
            else:
                if not any(rel == 'w2/associations.jsonl' for _, rel in baseline.manifest_entries):
                    raise RegistryError('baseline W2 associations missing')
                payload = {'format': FORMAT_ID, 'baseline_manifest_sha256': baseline.manifest_digest,
                           'baseline_index_sha256': index_hash, 'catalog_binding': meta, 'ticker_proofs_binding': proof_meta,
                           'w2_overrides': {}, 'b3_overrides': {}, 'w2_delta': {}, 'b2_delta': {},
                           'delta': {}, 'evidence': {}, 'candidates': []}
                index_tree = {'root': None, 'file_count': 0, 'row_count': 0, 'flag_census': {}}
                old_delta_catalog = {'observations': []}
            # A bounded generation already embeds its accepted incremental
            # bytes. Rebuild only those deltas against the catalog; never read
            # the old source archives or historical canonical rows. The old
            # generation and accepted entries remain untouched.
            carried = []
            if migrating:
                candidates = bounded.get('candidates')
                delta, evidence = bounded.get('delta'), bounded.get('evidence')
                if not isinstance(candidates, list) or not candidates or not isinstance(delta, dict) or not isinstance(evidence, dict):
                    raise RegistryError('bounded migration has invalid retained evidence')
                accepted = {}
                for file_name, date, digest, text in db.execute('SELECT file_name,date,digest,record FROM accepted'):
                    entry = json.loads(text)
                    if entry.get('publication_kind') == 'composite':
                        if (entry.get('file_name'), entry.get('date'), entry.get('digest')) != (file_name, date, digest):
                            raise RegistryError('bounded migration accepted registry identity mismatch')
                        accepted[(file_name, date, digest)] = entry
                if len(accepted) != len(candidates):
                    raise RegistryError('bounded migration accepted input count mismatch')
                identities, sources, digests = set(), set(), set()
                for rec in candidates:
                    identity = (rec['file_name'], rec['date'], rec['digest'])
                    source = 'incremental/' + rec['digest'] + '.rows.jsonl'
                    entry = accepted.get(identity)
                    if identity in identities or source in sources or rec['digest'] in digests or entry is None or any(entry.get(k) != v for k, v in rec.items()):
                        raise RegistryError('bounded migration accepted input mismatch')
                    identities.add(identity); sources.add(source); digests.add(rec['digest'])
                    rows_text, ev = delta[source], evidence[rec['digest']]
                    rows = _validate(rec, rows_text, ev, baseline)
                    carried.append((rec, rows_text, ev, rows))
                if set(delta) != sources or set(evidence) != digests or sum(len(x[3]) for x in carried) > 20000:
                    raise RegistryError('bounded migration has extra or oversized retained data')
            new = []
            row_count = 0
            batch_dates, batch_digests = set(), set()
            for text, rows_text, evidence in staged:
                rec = json.loads(text)
                if sha256_file(_candidate_path(source_roots, rec['root'], rec['relative_path'])) != rec['digest']:
                    raise RegistryError('source content changed during publication')
                rows = _validate(rec, rows_text, evidence, baseline)
                row_count += len(rows)
                if row_count > MAX_PENDING_ROWS:
                    raise RegistryError('pending publication row limit exceeded')
                if (rec['digest'] in batch_digests or rec['date'] in batch_dates or
                        db.execute('SELECT 1 FROM accepted WHERE digest=? OR date=? LIMIT 1', (rec['digest'], rec['date'])).fetchone()):
                    raise RegistryError('duplicate content or governed date')
                batch_digests.add(rec['digest']); batch_dates.add(rec['date'])
                new.append((rec, rows_text, evidence, rows))
            all_new = []
            affected_w2, affected_b2, added_tickers = set(), set(), set()
            new_w2, new_b2 = {}, {}
            def verify_carried_index():
                carried_delta = materialize_index_tree(db, index_tree, payload['candidates'])
                carried_index = compose_index(index, carried_delta, payload['candidates'])
                if carried_index != bounded.get('index'):
                    raise RegistryError('bounded migration index disagrees with retained input evidence')

            for number, (rec, rows_text, evidence, rows) in enumerate(carried + new):
                if migrating and number == len(carried):
                    verify_carried_index()
                source = 'incremental/' + rec['digest'] + '.rows.jsonl'
                metadata, flags = file_metadata(rec, rows)
                for row in rows:
                    values = row['source_values']
                    projected = _projection(row)
                    w2 = normalize_upper_trim(values.get('security_isin') or '')
                    b2 = _identity(row)
                    if w2:
                        new_w2.setdefault(w2, []).append([source, projected]); affected_w2.add(w2)
                    if b2:
                        new_b2.setdefault(b2, []).append([source, projected]); affected_b2.add(b2)
                    ticker = observed_trading_symbol(row)['observed_symbol']
                    if ticker and isinstance(values.get('series'), str):
                        added_tickers.add((ticker, values['series']))
                    all_new.append((source, projected))
                index_tree['root'] = insert_index(db, index_tree['root'], source, metadata)
                index_tree['file_count'] += 1
                index_tree['row_count'] += len(rows)
                for name, count in flags.items():
                    index_tree['flag_census'][name] = index_tree['flag_census'].get(name, 0) + count
                put_blob(db, rows_text, rec['rows_sha256'])
                put_blob(db, evidence, rec['evidence_sha256'])
                payload['delta'][source] = rec['rows_sha256']
                payload['evidence'][rec['digest']] = rec['evidence_sha256']
                payload['candidates'].append(rec)
            if migrating and not new:
                verify_carried_index()
            delta_catalog = _merge_tickers(old_delta_catalog, all_new)
            validate_ticker_delta(delta_catalog)
            catalog = TargetedCatalog(state, meta, proof_meta, delta_catalog, proof_db, proof_groups)
            # Reuse of a newly observed ticker affects existing valid identities,
            # even when those identities have no rows in this delta.
            for ticker, series in sorted(added_tickers):
                affected_b2.update(o[2] for o in catalog.ticker_observations(ticker, series) if o[2])
            def affected_group(kind, identity, additions):
                groups = payload[kind + '_delta']
                previous_hash = groups.get(identity)
                rows = load_group_from_db(db, kind, identity, previous_hash, payload['delta']) if previous_hash else []
                if additions:
                    rows += additions
                    text = _json(group_document(kind, identity, rows, payload['delta']))
                    digest = blob_sha(text)
                    put_blob(db, text, digest)
                    groups[identity] = digest
                return [(src, row) for src, row in rows]

            for identity in sorted(affected_w2):
                baseline_rows = list(observations_for_identity(cat, identity, 'w2'))
                delta_rows = affected_group('w2', identity, new_w2.get(identity, []))
                docs = _w2([('affected', [row for _, row in baseline_rows + delta_rows])])
                text = _json(override_document('w2', identity, docs[0] if docs else None))
                digest = blob_sha(text); put_blob(db, text, digest)
                payload['w2_overrides'][identity] = digest
            for identity in sorted(affected_b2):
                base_rows = list(observations_for_identity(cat, identity, 'b2'))
                delta_rows = affected_group('b2', identity, new_b2.get(identity, []))
                doc = build_continuity(base_rows + delta_rows, baseline.manifest_digest, catalog_override=catalog)
                text = _json(override_document('b3', identity, doc['identities']))
                digest = blob_sha(text); put_blob(db, text, digest)
                payload['b3_overrides'][identity] = digest
            validate_index_tree(index_tree, payload['candidates'])
            validate_references(payload)
            validate_group_references(payload)
            validate_override_references(payload)
            payload['index_tree'] = index_tree
            payload['symbol_delta'] = delta_catalog
            text = _json(payload); generation = _sha(text)
            if load_index(state, baseline)[1] != index_hash:
                raise RegistryError('baseline index changed during publication')
            db.execute('INSERT OR IGNORE INTO composite_generations VALUES (?,?)', (generation, text))
            if db.execute('SELECT payload FROM composite_generations WHERE id=?', (generation,)).fetchone()[0] != text:
                raise RegistryError('generation identity mismatch')
            for rec, _, _, _ in new:
                entry = dict(rec, date_from_filename=rec['date'], archive_sha256_observed_raw_bytes=rec['digest'],
                             partition=rec['family'] + '/' + rec['date'][:4], publication_kind='composite', generation=generation)
                db.execute('INSERT INTO accepted VALUES (?,?,?,?)', (rec['file_name'], rec['date'], rec['digest'], _json(entry)))
            db.execute('INSERT INTO composite_active VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET generation=excluded.generation', (generation,))
            db.commit()
            return {'status': 'PUBLISHED', 'generation': generation, 'new_inputs': len(new), 'migrated_bounded_generation': previous[0] if migrating else None, 'migrated_inline_generation': previous[0] if migrate_blobs else None, 'migrated_groups_generation': previous[0] if migrate_groups else None, 'migrated_overrides_generation': previous[0] if migrate_overrides else None, 'migrated_tickers_generation': previous[0] if migrate_tickers else None, 'migrated_index_generation': previous[0] if migrate_index else None, 'migrated_ticker_proofs_generation': previous[0] if migrate_proofs else None, 'migrated_index_tree_generation': previous[0] if migrate_tree else None, 'row_count': index['counts']['row_count'] + index_tree['row_count']}
        except (sqlite3.Error, ValueError, KeyError, TypeError, QueryError) as exc:
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError('catalog publication failed: %s' % exc) from exc
        finally:
            db.close()
    finally:
        if proof_db is not None:
            proof_db.close()
        cat.close()
