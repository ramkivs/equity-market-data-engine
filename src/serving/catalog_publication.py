"""Catalog-backed atomic publication for the selected composite application.

Only pending candidates and catalog observations for affected identities are
parsed. Generations are still self-contained JSON snapshots of all incremental
inputs (not of baseline rows); their accumulated delta size is a known limit.
"""
import copy
import json
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
from .w2_continuity import build_continuity

FORMAT_ID = 'catalog-composite/1.0'
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
    try:
        cat.execute('BEGIN')
        if _metadata(cat) != meta:
            raise RegistryError('continuity catalog changed before publication')
        if meta['format'] != FORMAT:
            raise RegistryError('continuity catalog needs upgrade before publication')
        base_catalog = ticker_catalog(cat, meta)
        preview, _ = _open(baseline, path)
        try:
            staged = _pending(preview)
        finally:
            preview.close()
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
                if payload.get('format') not in (FORMAT_ID, 'bounded-composite/1.0'):
                    raise RegistryError('unknown active composite format')
                if payload.get('baseline_manifest_sha256') != baseline.manifest_digest or payload.get('baseline_index_sha256') != index_hash:
                    raise RegistryError('active composite baseline/index mismatch')
                if payload.get('format') == FORMAT_ID and payload.get('catalog_binding') != meta:
                    raise RegistryError('active composite catalog mismatch')
            if not staged:
                if previous is None:
                    raise RegistryError('no new records or prior generation')
                db.commit()
                return {'status': 'UNCHANGED', 'generation': previous[0]}
            if previous:
                if payload.get('format') != FORMAT_ID:
                    raise RegistryError('existing bounded generation requires safe catalog migration')
                payload = copy.deepcopy(payload)
                composite_index = payload['index']
                old_catalog = payload['symbol_catalog']
            else:
                if not any(rel == 'w2/associations.jsonl' for _, rel in baseline.manifest_entries):
                    raise RegistryError('baseline W2 associations missing')
                payload = {'format': FORMAT_ID, 'baseline_manifest_sha256': baseline.manifest_digest,
                           'baseline_index_sha256': index_hash, 'catalog_binding': meta,
                           'w2_overrides': {}, 'b3_overrides': {}, 'w2_delta': {}, 'b2_delta': {},
                           'delta': {}, 'evidence': {}, 'candidates': []}
                composite_index = copy.deepcopy(index)
                old_catalog = base_catalog
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
            for rec, rows_text, evidence, rows in new:
                source = 'incremental/' + rec['digest'] + '.rows.jsonl'
                pairs, flags = set(), {}
                for row in rows:
                    values = row['source_values']
                    pairs.add((values.get('listing_symbol') or '', values.get('series') or ''))
                    for flag in row.get('flags', []):
                        name = flag.get('name') if isinstance(flag, dict) else None
                        if not isinstance(name, str) or not name:
                            raise RegistryError('invalid staged flag')
                        flags[name] = flags.get(name, 0) + 1
                    projected = _projection(row)
                    w2 = normalize_upper_trim(values.get('security_isin') or '')
                    b2 = _identity(row)
                    if w2:
                        payload['w2_delta'].setdefault(w2, []).append([source, projected]); affected_w2.add(w2)
                    if b2:
                        payload['b2_delta'].setdefault(b2, []).append([source, projected]); affected_b2.add(b2)
                    ticker = observed_trading_symbol(row)['observed_symbol']
                    if ticker and isinstance(values.get('series'), str):
                        added_tickers.add((ticker, values['series']))
                    all_new.append((source, projected))
                composite_index['files'][source] = {'family': rec['family'], 'year': rec['date'][:4], 'member_stem': rec['file_name'], 'row_count': len(rows), 'instruments': [list(p) for p in sorted(pairs)], 'business_date_min': rec['date'], 'business_date_max': rec['date']}
                part = composite_index['partitions'].setdefault(rec['family'] + '/' + rec['date'][:4], {'family': rec['family'], 'year': rec['date'][:4], 'row_files': 0, 'row_count': 0})
                part['row_files'] += 1; part['row_count'] += len(rows)
                for name, count in flags.items():
                    composite_index['flag_census'][name] = composite_index['flag_census'].get(name, 0) + count
                payload['delta'][source] = rows_text
                payload['evidence'][rec['digest']] = evidence
                payload['candidates'].append(rec)
            catalog = _merge_tickers(old_catalog, all_new)
            # Reuse of a newly observed ticker affects existing valid identities,
            # even when those identities have no rows in this delta.
            affected_b2.update(o[2] for o in catalog['observations'] if (o[0], o[1]) in added_tickers and o[2])
            for identity in sorted(affected_w2):
                baseline_rows = list(observations_for_identity(cat, identity, 'w2'))
                delta_rows = [(src, row) for src, row in payload['w2_delta'].get(identity, [])]
                docs = _w2([('affected', [row for _, row in baseline_rows + delta_rows])])
                payload['w2_overrides'][identity] = docs[0] if docs else None
            for identity in sorted(affected_b2):
                base_rows = list(observations_for_identity(cat, identity, 'b2'))
                delta_rows = [(src, row) for src, row in payload['b2_delta'].get(identity, [])]
                doc = build_continuity(base_rows + delta_rows, baseline.manifest_digest, catalog_override=catalog)
                payload['b3_overrides'][identity] = doc['identities']
            composite_index['counts']['row_files'] = len(composite_index['files'])
            composite_index['counts']['row_count'] = sum(f['row_count'] for f in composite_index['files'].values())
            composite_index['counts']['instrument_pairs'] = len({tuple(p) for f in composite_index['files'].values() for p in f['instruments']})
            payload['index'] = composite_index
            payload['symbol_catalog'] = catalog
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
            return {'status': 'PUBLISHED', 'generation': generation, 'new_inputs': len(new), 'row_count': composite_index['counts']['row_count']}
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError('catalog publication failed: %s' % exc) from exc
        finally:
            db.close()
    finally:
        cat.close()
