"""Explicit baseline registry and D21 conflict capture (not an ingestor).

This preparatory component never processes or publishes new inputs. A NEW result
is a candidate, not permission to serve or a processed registry entry.
"""
import argparse
import datetime
import json
import os
import sqlite3
from urllib.parse import quote

from .baseline import sha256_file
from .paths import validate_roots, validate_store_root

FORMAT = 'incremental-source-registry/1.0'
DB_NAME = 'source_registry.sqlite3'


class RegistryError(ValueError):
    pass


def bindings(baseline):
    r = baseline.run_record
    e, t = r.get('engine_identity', {}), r.get('runner_identity', {})
    result = {'engine_sha256': e.get('tool_sha256'), 'runner_sha256': t.get('runner_sha256'),
              'spec_version': e.get('spec_version'), 'contract_version': t.get('contract_version')}
    if any(not isinstance(v, str) or not v for v in result.values()):
        raise RegistryError('baseline missing required version bindings')
    return result


def _json(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _db_path(baseline, registry_root, state, saved, history, source_roots):
    roots = {'package': baseline.root, 'registry': registry_root, 'state': state, 'saved': saved, 'history': history}
    roots.update({'source_' + name: root for name, root in source_roots.items()})
    if set(source_roots) != {'LEGACY', 'UDIFF'} or any(not p for p in roots.values()):
        raise RegistryError('complete package, registry, state, saved, history, LEGACY and UDIFF roots required')
    validate_roots(**roots)
    validate_store_root(registry_root, 'registry')
    path = os.path.join(os.path.abspath(registry_root), DB_NAME)
    if os.path.islink(path):
        raise RegistryError('registry database must not be a symlink')
    return path


def _manifest_entries(baseline):
    if not any(path == 'INPUT_MANIFEST.jsonl' for _, path in baseline.manifest_entries):
        raise RegistryError('baseline has no verified input manifest')
    records = []
    seen, seen_hashes = set(), set()
    with open(baseline.path('INPUT_MANIFEST.jsonl'), encoding='utf8') as f:
        for line in f:
            record = json.loads(line)
            required = ('root', 'relative_path', 'file_name', 'date_from_filename', 'partition',
                        'rows', 'quarantined', 'archive_sha256_observed_raw_bytes')
            if any(k not in record for k in required):
                raise RegistryError('incomplete input manifest record')
            digest = record['archive_sha256_observed_raw_bytes']
            key = (record['file_name'], record['date_from_filename'])
            if (record['root'] not in ('LEGACY', 'UDIFF') or not isinstance(digest, str) or len(digest) != 64
                    or any(c not in '0123456789abcdef' for c in digest) or key in seen or digest in seen_hashes):
                raise RegistryError('invalid or duplicate baseline archive identity/content')
            seen.add(key)
            seen_hashes.add(digest)
            records.append(record)
    if len(records) != baseline.run_record.get('corpus', {}).get('archive_count'):
        raise RegistryError('input manifest archive count disagrees with baseline')
    return records


def initialize(baseline, registry_root, state, saved, history, source_roots):
    """Seed only from the verified baseline manifest; never read source archives."""
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    records, version = _manifest_entries(baseline), bindings(baseline)
    os.makedirs(registry_root, exist_ok=True)
    # Exclusive creation preserves existing and interrupted user-owned state.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('CREATE TABLE accepted (file_name TEXT, date TEXT, digest TEXT UNIQUE, record TEXT NOT NULL, PRIMARY KEY(file_name,date))')
        db.execute('CREATE TABLE conflicts (file_name TEXT, date TEXT, digest TEXT, record TEXT NOT NULL, PRIMARY KEY(file_name,date,digest))')
        meta = {'format': FORMAT, 'manifest_sha256': baseline.manifest_digest, 'baseline_run_id': baseline.marker.get('run_id'), 'bindings': version}
        db.executemany('INSERT INTO meta VALUES (?,?)', [(k, _json(v)) for k, v in meta.items()])
        db.executemany('INSERT INTO accepted VALUES (?,?,?,?)', [(r['file_name'], r['date_from_filename'], r['archive_sha256_observed_raw_bytes'], _json(r)) for r in records])
    return {'format': FORMAT, 'accepted': len(records), 'manifest_sha256': baseline.manifest_digest}


def _open(baseline, path):
    if not os.path.isfile(path) or os.path.islink(path):
        raise RegistryError('registry missing or unsafe; initialize explicitly')
    db = sqlite3.connect('file:' + quote(path, safe='/') + '?mode=rw', uri=True)
    try:
        meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
        if meta.get('format') != FORMAT or meta.get('manifest_sha256') != baseline.manifest_digest or meta.get('bindings') != bindings(baseline):
            raise RegistryError('registry does not match verified baseline and version bindings')
        return db, meta
    except BaseException:
        db.close()
        raise


def inspect(baseline, registry_root, state, saved, history, source_roots, root, relative_path, date, scan_id, current_bindings):
    """Classify one explicitly supplied archive, recording CHANGED conflicts.

    Date must come from governed discovery evidence; it is never inferred from a
    filename. NEW is *unvalidated*, not processed or eligible for serving.
    """
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    expected = bindings(baseline)
    if not isinstance(current_bindings, dict) or set(current_bindings) != set(expected) or any(not isinstance(v, str) or not v for v in current_bindings.values()):
        raise RegistryError('complete current version bindings are required')
    if (root not in source_roots or not isinstance(relative_path, str) or not relative_path
            or os.path.isabs(relative_path) or '..' in relative_path.replace('\\', '/').split('/')):
        raise RegistryError('invalid source path')
    if not isinstance(scan_id, str) or not scan_id.strip():
        raise RegistryError('scan provenance required')
    try:
        if datetime.date.fromisoformat(date).isoformat() != date:
            raise ValueError()
    except (ValueError, TypeError):
        raise RegistryError('governed ISO date required')
    source_root = os.path.realpath(source_roots[root])
    candidate = os.path.realpath(os.path.join(source_root, relative_path))
    if os.path.commonpath((source_root, candidate)) != source_root or not os.path.isfile(candidate):
        raise RegistryError('source path escapes root or is not a file')
    name = os.path.basename(relative_path)
    digest = sha256_file(candidate)
    db, meta = _open(baseline, path)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT digest,record FROM accepted WHERE file_name=? AND date=?', (name, date)).fetchone()
        duplicate = db.execute('SELECT file_name,date FROM accepted WHERE digest=?', (digest,)).fetchone()
        stale = current_bindings != meta['bindings']
        result = {'root': root, 'relative_path': relative_path.replace(os.sep, '/'), 'file_name': name, 'date': date,
                  'sha256': digest, 'scan_id': scan_id, 'bindings_stale': stale,
                  'current_bindings': current_bindings, 'prior_bindings': meta['bindings']}
        if old and old[0] != digest:
            prior = json.loads(old[1])
            result.update(status='CHANGED-CONFLICT-UNRESOLVED', prior=prior,
                          prior_run_id=prior.get('run_id', meta['baseline_run_id']),
                          prior_manifest_sha256=prior.get('generation', baseline.manifest_digest))
            # Preserve first-observed provenance; repeats do not overwrite it.
            db.execute('INSERT OR IGNORE INTO conflicts VALUES (?,?,?,?)', (name, date, digest, _json(result)))
        elif old:
            if old[1] and (json.loads(old[1])['root'], json.loads(old[1])['relative_path']) != (root, relative_path.replace(os.sep, '/')):
                result['status'] = 'ANOMALOUS-DUPLICATE-PATH'
            else:
                result['status'] = 'STALE' if stale else 'UNCHANGED'
        elif duplicate:
            result.update(status='ANOMALOUS-DUPLICATE-CONTENT', prior_identity=list(duplicate))
        else:
            result['status'] = 'NEW-UNVALIDATED'
        db.commit()
        return result
    finally:
        db.close()


def conflicts(baseline, registry_root, state, saved, history, source_roots):
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    db, _ = _open(baseline, path)
    try:
        return [json.loads(row[0]) for row in db.execute('SELECT record FROM conflicts ORDER BY file_name,date,digest')]
    finally:
        db.close()


def main(argv=None):
    from .baseline import BaselineError, DEFAULT_M2_SPEC, open_baseline
    from .index import ServingIndexError
    from .query import QueryError
    parser = argparse.ArgumentParser(description='Explicit source registry inspection; does not ingest or publish.')
    for name in ('package', 'registry', 'state', 'saved-state', 'history-state', 'legacy-root', 'udiff-root'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--m2', action='store_true', help='verify the package against the qualified M2 pin')
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('init', help='initialize from verified baseline manifest; never overwrite')
    sub.add_parser('bootstrap', help='one-time baseline continuity catalog bootstrap')
    sub.add_parser('catalog-verify', help='fully verify the baseline continuity catalog')
    sub.add_parser('catalog-upgrade', help='upgrade a verified continuity catalog with identity proofs')
    sub.add_parser('conflicts', help='list durable unresolved findings')
    sub.add_parser('staged', help='list validated candidates that are not published')
    sub.add_parser('publish', help='publish a bounded Q1-Q5 composite generation')
    sub.add_parser('draft', help='capture an isolated, non-serveable draft snapshot')
    sub.add_parser('drafts', help='list non-serveable draft snapshots')
    stage = sub.add_parser('prepare', help='validate and stage a candidate; does not publish')
    stage.add_argument('--root', choices=('LEGACY', 'UDIFF'), required=True)
    stage.add_argument('--relative-path', required=True)
    stage.add_argument('--date', required=True, help='governed source date YYYY-MM-DD')
    stage.add_argument('--scan-id', required=True)
    scan = sub.add_parser('inspect', help='classify a candidate; does not process NEW')
    scan.add_argument('--root', choices=('LEGACY', 'UDIFF'), required=True)
    scan.add_argument('--relative-path', required=True)
    scan.add_argument('--date', required=True, help='governed source date YYYY-MM-DD')
    scan.add_argument('--scan-id', required=True)
    scan.add_argument('--current-bindings', required=True, help='JSON object with engine_sha256, runner_sha256, spec_version, contract_version')
    args = parser.parse_args(argv)
    try:
        from .continuity_catalog import FILENAME as CATALOG_FILENAME
        first_bootstrap = args.operation == 'bootstrap' and not os.path.lexists(os.path.join(args.state, CATALOG_FILENAME))
        base = open_baseline(args.package, spec=DEFAULT_M2_SPEC if args.m2 else None,
                             verify_files=args.operation == 'init' or first_bootstrap)
        common = (base, args.registry, args.state, args.saved_state, args.history_state,
                  {'LEGACY': args.legacy_root, 'UDIFF': args.udiff_root})
        if args.operation == 'init':
            result = initialize(*common)
        elif args.operation == 'bootstrap':
            from .continuity_catalog import bootstrap
            result = bootstrap(base, args.state, args.registry, args.saved_state, args.history_state, common[-1])
        elif args.operation == 'catalog-upgrade':
            from .continuity_catalog import upgrade_catalog
            result = upgrade_catalog(base, args.state)
        elif args.operation == 'catalog-verify':
            from .continuity_catalog import verify_catalog
            result = verify_catalog(base, args.state)
        elif args.operation == 'conflicts':
            result = conflicts(*common)
        elif args.operation == 'publish':
            from .incremental_publication import publish
            result = publish(*common)
        elif args.operation in ('draft', 'drafts'):
            from .incremental_drafts import create_draft, list_drafts
            result = create_draft(*common) if args.operation == 'draft' else list_drafts(*common)
        elif args.operation in ('prepare', 'staged'):
            from .incremental_staging import prepare, list_staged
            result = (prepare(*common, args.root, args.relative_path, args.date, args.scan_id)
                      if args.operation == 'prepare' else list_staged(*common))
        else:
            result = inspect(*common, args.root, args.relative_path, args.date, args.scan_id, json.loads(args.current_bindings))
        print(_json({'result': 'pass', 'data': result}))
        return 0
    except (ValueError, OSError, sqlite3.Error, BaselineError, ServingIndexError, QueryError) as exc:
        print(_json({'result': 'fail', 'detail': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
