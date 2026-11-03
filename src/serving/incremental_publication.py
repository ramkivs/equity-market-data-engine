"""Composite publication, with a bounded legacy path and catalog-backed path.

A SQLite transaction commits accepted entries, an immutable generation and its
active pointer. No source archives or baseline files are written. The catalog
path avoids baseline row scans but still has accumulated-delta JSON limits.
"""
import copy
import hashlib
import io
import json
import os
import sqlite3

from nse_engine.identity import AssociationAccumulator, AssociationRow
from nse_engine.provenance import Provenance
from .incremental_registry import RegistryError, _db_path, _json, _open, inspect
from .baseline import sha256_file
from .incremental_staging import _candidate_path
from . import incremental_staging
from .incremental_registry import bindings
from nse_engine import DEFAULT_CONFIG
from .incremental_drafts import _validate
from .index import load_index
from .w2_continuity import build_continuity

LIMIT = 20000


def _sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS composite_generations (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS composite_active (singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation TEXT NOT NULL)')


def _w2(sources):
    acc = AssociationAccumulator()
    for _, rows in sources:
        for row in rows:
            v, p = row['source_values'], dict(row['provenance'])
            p['evidence_refs'] = tuple(p.get('evidence_refs') or ())
            acc.add_row(AssociationRow(row['business_date'], row['source_line_number'],
                                      v.get('listing_symbol') or '', v.get('series') or '',
                                      v.get('security_isin') or '', row['isin_validity'], Provenance(**p)))
    return [doc.to_dict() for doc in acc.identity_documents()]


def publish(baseline, registry_root, state, saved, history, source_roots):
    """Publish all staged records, or no changes on any error.

    A verified catalog selects the catalog-backed path. Without it, the legacy
    bounded implementation still refuses large baseline materialization.
    """
    from .continuity_catalog import FILENAME as CATALOG_FILENAME
    if os.path.lexists(os.path.join(state, CATALOG_FILENAME)):
        from .catalog_publication import publish as publish_from_catalog
        return publish_from_catalog(baseline, registry_root, state, saved, history, source_roots)
    from .query import parse_associations
    if incremental_staging.runtime_bindings() != bindings(baseline) or baseline.run_record.get('config', {}).get('config_fingerprint') != DEFAULT_CONFIG.fingerprint():
        raise RegistryError('current engine, runner or config differs from baseline')
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    index, index_hash = load_index(state, baseline)
    if type(index.get('counts', {}).get('row_count')) is not int or index['counts']['row_count'] > LIMIT:
        raise RegistryError('composite publication unavailable: baseline exceeds bounded continuity limit')
    # Record changed candidates through the existing D21 path before taking the
    # publication lock. NEW candidates remain unaccepted until the transaction.
    preview, _ = _open(baseline, path)
    try:
        if not preview.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone():
            raise RegistryError('no staged candidates')
        records = [json.loads(row[0]) for row in preview.execute('SELECT record FROM staged_candidates')]
    finally:
        preview.close()
    for rec in records:
        finding = inspect(baseline, registry_root, state, saved, history, source_roots,
                          rec['root'], rec['relative_path'], rec['date'], 'publication-check-' + rec['run_id'], rec['bindings'])
        if finding['sha256'] != rec['digest']:
            raise RegistryError('source content changed after staging; held or requires revalidation')
    from .composite_binding import ensure_binding
    ensure_binding(baseline, state, registry_root)
    db, _ = _open(baseline, path)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        _schema(db)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone():
            raise RegistryError('no staged candidates')
        size = db.execute('SELECT COALESCE(sum(length(CAST(record AS BLOB))+length(CAST(rows AS BLOB))+length(CAST(evidence AS BLOB))),0) FROM staged_candidates').fetchone()[0]
        if size > 128 * 1024 * 1024:
            raise RegistryError('composite staging byte limit exceeded')
        stage = db.execute('SELECT record,rows,evidence FROM staged_candidates ORDER BY file_name,date,digest').fetchall()
        if not stage:
            raise RegistryError('no staged candidates')
        metadata = []
        for rec_text, rows_text, evidence in stage:
            rec = json.loads(rec_text)
            if sha256_file(_candidate_path(source_roots, rec['root'], rec['relative_path'])) != rec['digest']:
                raise RegistryError('source content changed during publication')
            rows = _validate(rec, rows_text, evidence, baseline)
            metadata.append((rec, rows_text, evidence, rows))
        if index['counts']['row_count'] + sum(len(rows) for _, _, _, rows in metadata) > LIMIT:
            raise RegistryError('composite row limit exceeded')
        accepted = db.execute('SELECT record FROM accepted').fetchall()
        previously = [json.loads(r[0]) for r in accepted if json.loads(r[0]).get('publication_kind') == 'composite']
        if any(not any(r['digest'] == old['archive_sha256_observed_raw_bytes'] for r, _, _, _ in metadata) for old in previously):
            raise RegistryError('accepted delta missing from retained staging; refusing incomplete generation')
        new = []
        for record, text, evidence, rows in metadata:
            found = db.execute('SELECT digest,record FROM accepted WHERE file_name=? AND date=?', (record['file_name'], record['date'])).fetchone()
            if found:
                if found[0] != record['digest'] or json.loads(found[1]).get('publication_kind') != 'composite':
                    raise RegistryError('candidate conflicts with previously accepted data')
            else:
                if db.execute('SELECT 1 FROM accepted WHERE digest=? OR date=? LIMIT 1', (record['digest'], record['date'])).fetchone():
                    raise RegistryError('duplicate content or governed date')
                new.append(record)
        if not new:
            active = db.execute('SELECT generation FROM composite_active WHERE singleton=1').fetchone()
            if not active:
                raise RegistryError('no new records or prior generation')
            db.commit()
            return {'status': 'UNCHANGED', 'generation': active[0]}
        base_sources = []
        base_count = base_bytes = 0
        for rel in baseline.row_files():
            rows = []
            with open(baseline.path(rel), encoding='utf8') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    base_count += 1
                    base_bytes += len(line.encode('utf8'))
                    if base_count > LIMIT or base_bytes > 128 * 1024 * 1024:
                        raise RegistryError('composite baseline row or byte limit exceeded')
                    rows.append(json.loads(line))
            base_sources.append((rel, rows))
        # Reproduce the published baseline's W2 exactly before composing.
        original = parse_associations(baseline)
        original_docs = [d for _, d in original] if original is not None else None
        if original_docs is None or _w2(base_sources) != original_docs:
            raise RegistryError('baseline W2 replay did not match published associations')
        delta_sources = [('incremental/' + rec['digest'] + '.rows.jsonl', rows) for rec, _, _, rows in metadata]
        sources = base_sources + delta_sources
        if sum(len(rows) for _, rows in sources) > LIMIT:
            raise RegistryError('composite row limit exceeded')
        w2 = _w2(sources)
        b3 = build_continuity(((path, row) for path, rows in sources for row in rows), baseline.manifest_digest)
        composite_index = copy.deepcopy(index)
        for (record, rows_text, evidence, rows), (relative, _) in zip(metadata, delta_sources):
            pairs = sorted({(r['source_values'].get('listing_symbol') or '', r['source_values'].get('series') or '') for r in rows})
            composite_index['files'][relative] = {'family': record['family'], 'year': record['date'][:4], 'member_stem': record['file_name'], 'row_count': len(rows), 'instruments': [list(p) for p in pairs], 'business_date_min': record['date'], 'business_date_max': record['date']}
            part = composite_index['partitions'].setdefault(record['family'] + '/' + record['date'][:4], {'family': record['family'], 'year': record['date'][:4], 'row_files': 0, 'row_count': 0})
            part['row_files'] += 1; part['row_count'] += len(rows)
            for row in rows:
                for flag in row['flags']:
                    name = flag['name']; composite_index['flag_census'][name] = composite_index['flag_census'].get(name, 0) + 1
        composite_index['counts']['row_files'] = len(composite_index['files'])
        composite_index['counts']['row_count'] = sum(f['row_count'] for f in composite_index['files'].values())
        composite_index['counts']['instrument_pairs'] = len({tuple(p) for f in composite_index['files'].values() for p in f['instruments']})
        payload = {'format': 'bounded-composite/1.0', 'baseline_manifest_sha256': baseline.manifest_digest,
                   'baseline_index_sha256': index_hash, 'index': composite_index, 'w2': w2, 'b3': b3,
                   'delta': {relative: text for (rec, text, _, _), (relative, _) in zip(metadata, delta_sources)},
                   'evidence': {rec['digest']: evidence for rec, _, evidence, _ in metadata},
                   'candidates': [r for r, _, _, _ in metadata]}
        text = _json(payload); generation = _sha(text)
        _, after = load_index(state, baseline)
        if after != index_hash:
            raise RegistryError('baseline index changed during publication')
        db.execute('INSERT OR IGNORE INTO composite_generations VALUES (?,?)', (generation, text))
        stored = db.execute('SELECT payload FROM composite_generations WHERE id=?', (generation,)).fetchone()
        if stored is None or stored[0] != text:
            raise RegistryError('generation identity mismatch')
        for record in new:
            entry = dict(record, date_from_filename=record['date'], archive_sha256_observed_raw_bytes=record['digest'],
                         partition=record['family'] + '/' + record['date'][:4], publication_kind='composite', generation=generation)
            db.execute('INSERT INTO accepted VALUES (?,?,?,?)', (record['file_name'], record['date'], record['digest'], _json(entry)))
        db.execute('INSERT INTO composite_active VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET generation=excluded.generation', (generation,))
        db.commit()
        return {'status': 'PUBLISHED', 'generation': generation, 'new_inputs': len(new), 'row_count': composite_index['counts']['row_count']}
    except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError('publication failed: %s' % exc) from exc
    finally:
        db.close()


class CompositeBaseline:
    def __init__(self, baseline, generation, payload, state=None, registry_conflicts=(), registry_accepted=()):
        self.original = baseline
        self.root = baseline.root
        self.manifest_digest = generation
        self.payload = payload
        self.state = state
        self.registry_conflicts = registry_conflicts
        self.registry_accepted = registry_accepted
    def path(self, relative):
        return self.original.path(relative)
    def open_text(self, relative):
        if relative in self.payload['delta']:
            return io.StringIO(self.payload['delta'][relative])
        return open(self.original.path(relative), encoding='utf8')


def active_snapshot(baseline, registry_root, state):
    """Pin one complete committed generation for an individual request."""
    path = os.path.join(registry_root, 'source_registry.sqlite3')
    db, _ = _open(baseline, path)
    try:
        db.execute('BEGIN')  # pointer, accepted inputs and D21 findings share one request snapshot
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='composite_active'").fetchone():
            return None
        row = db.execute('SELECT a.generation,g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation WHERE a.singleton=1').fetchone()
        if row is None:
            # A transaction may have created an empty schema before the first
            # successful publication. It still denotes baseline-only serving.
            count = db.execute('SELECT count(*) FROM composite_generations').fetchone()[0]
            accepted = (json.loads(item[0]) for item in db.execute('SELECT record FROM accepted'))
            if count == 0 and not any(item.get('publication_kind') == 'composite' for item in accepted):
                return None
            raise RegistryError('active composite pointer is missing or invalid')
        generation, text = row
        if _sha(text) != generation:
            raise RegistryError('active composite digest mismatch')
        payload = json.loads(text)
        base_index, digest = load_index(state, baseline)
        if payload.get('format') not in ('bounded-composite/1.0', 'catalog-composite/1.0', 'catalog-composite/2.0', 'catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0') or payload.get('baseline_manifest_sha256') != baseline.manifest_digest or payload.get('baseline_index_sha256') != digest:
            raise RegistryError('active composite baseline/index mismatch')
        if payload['format'] in ('catalog-composite/1.0', 'catalog-composite/2.0', 'catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0'):
            from .continuity_catalog import _metadata, open_catalog, ticker_catalog
            catalog_db, catalog_meta = open_catalog(baseline, state)
            try:
                catalog_db.execute('BEGIN')
                if payload.get('catalog_binding') != catalog_meta or _metadata(catalog_db) != catalog_meta:
                    raise RegistryError('active composite catalog mismatch')
                catalog = ticker_catalog(catalog_db, catalog_meta)
            finally:
                catalog_db.close()
        if payload['format'] in ('catalog-composite/5.0', 'catalog-composite/6.0'):
            from .catalog_publication import merge_ticker_catalogs, validate_ticker_delta
            try:
                validate_ticker_delta(payload.get('symbol_delta'))
                payload['symbol_catalog'] = merge_ticker_catalogs(catalog, payload['symbol_delta'])
            except (ValueError, TypeError, KeyError) as exc:
                raise RegistryError('invalid composite ticker census: %s' % exc) from exc
        if payload['format'] in ('catalog-composite/2.0', 'catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0'):
            from .composite_blobs import BlobMap, GroupMap, OverrideMap, validate_references, validate_group_references, validate_override_references
            try:
                validate_references(payload)
                if payload['format'] in ('catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0'):
                    validate_group_references(payload)
                if payload['format'] in ('catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0'):
                    validate_override_references(payload)
            except ValueError as exc:
                raise RegistryError('active composite blob references invalid: %s' % exc) from exc
            payload['delta'] = BlobMap(path, payload['delta'])
            payload['evidence'] = BlobMap(path, payload['evidence'])
            if payload['format'] in ('catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0'):
                payload['w2_delta'] = GroupMap(path, payload['w2_delta'], 'w2', payload['delta'])
                payload['b2_delta'] = GroupMap(path, payload['b2_delta'], 'b2', payload['delta'])
            if payload['format'] in ('catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0'):
                payload['w2_overrides'] = OverrideMap(path, payload['w2_overrides'], 'w2')
                payload['b3_overrides'] = OverrideMap(path, payload['b3_overrides'], 'b3')
        if payload['format'] == 'catalog-composite/6.0':
            from .composite_index import compose
            try:
                payload['index'] = compose(base_index, payload.get('index_delta'), payload.get('candidates'))
            except (ValueError, TypeError, KeyError) as exc:
                raise RegistryError('invalid composite index overlay: %s' % exc) from exc
        findings = tuple(row[0] for row in db.execute('SELECT record FROM conflicts ORDER BY file_name,date,digest'))
        accepted = tuple(db.execute('SELECT file_name,date,digest FROM accepted ORDER BY file_name,date'))
        return CompositeBaseline(baseline, generation, payload, state, findings, accepted), payload['index']
    finally:
        db.close()
