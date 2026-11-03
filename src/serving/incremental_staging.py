"""Validate and durably stage a single new archive, without publishing it.

Staging is intentionally not acceptance: no staged candidate is part of Q1–Q10
or the processed registry until atomic composite publication succeeds.
"""
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import zipfile

from nse_engine import DEFAULT_CONFIG, SourceDescriptor, build_canonical, evidence_json, rows_jsonl, tool_fingerprint
from nse_engine.errors import NseEngineError
from .incremental_registry import RegistryError, _db_path, _json, _open, bindings, inspect

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024


def runtime_bindings():
    # Load the pinned runner identity implementation without requiring the
    # current working directory or mutating the engine/runner sources.
    filename = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'tools', 'i4_runner', 'i4_identity.py')
    spec = importlib.util.spec_from_file_location('_incremental_runner_identity', filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from nse_engine import contract
    return {'engine_sha256': tool_fingerprint(), 'runner_sha256': module.runner_fingerprint(),
            'spec_version': contract.SPEC_VERSION, 'contract_version': module.CONTRACT_VERSION}


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS staged_candidates ('
               'file_name TEXT NOT NULL, date TEXT NOT NULL, digest TEXT NOT NULL UNIQUE, '
               'record TEXT NOT NULL, rows TEXT NOT NULL, evidence TEXT NOT NULL, '
               'PRIMARY KEY(file_name,date))')


def _candidate_path(source_roots, root, relative):
    base = os.path.realpath(source_roots[root])
    candidate = os.path.realpath(os.path.join(base, relative))
    if os.path.commonpath((base, candidate)) != base or not os.path.isfile(candidate):
        raise RegistryError('source path escapes root or is not a file')
    return candidate


def prepare(baseline, registry_root, state, saved, history, source_roots, root, relative_path, date, scan_id):
    """Build and persist a validated *staged* contribution; never marks processed."""
    current = runtime_bindings()
    expected = bindings(baseline)
    if current != expected:
        raise RegistryError('current engine/runner bindings differ from the baseline; migration is not authorized')
    config = baseline.run_record.get('config', {}).get('config_fingerprint')
    if config != DEFAULT_CONFIG.fingerprint():
        raise RegistryError('current engine configuration does not match baseline')
    common = (baseline, registry_root, state, saved, history, source_roots)
    result = inspect(*common, root, relative_path, date, scan_id, current)
    if result['status'] != 'NEW-UNVALIDATED':
        return {'status': result['status'], 'inspection': result}
    path = _db_path(*common)
    db, _ = _open(baseline, path)
    try:
        db.execute('BEGIN IMMEDIATE')
        _schema(db)
        from .pending_queue import installed, verify
        if installed(db):
            verify(db)
        old = db.execute('SELECT digest,record FROM staged_candidates WHERE file_name=? AND date=?', (result['file_name'], date)).fetchone()
        duplicate = db.execute('SELECT file_name,date FROM staged_candidates WHERE digest=?', (result['sha256'],)).fetchone()
        if old:
            prior = json.loads(old[1])
            if old[0] != result['sha256']:
                raise RegistryError('different content already staged for this identity; no replacement performed')
            if (prior['root'], prior['relative_path']) != (root, relative_path.replace(os.sep, '/')):
                raise RegistryError('staged content is already present at a different path')
            db.commit()
            return {'status': 'ALREADY-STAGED', 'record': prior}
        if duplicate:
            raise RegistryError('duplicate content is already staged under another identity')
        # D16 inventory's duplicate-date anomaly: never silently add a second
        # archive for an already accepted/staged governed date.
        if db.execute('SELECT 1 FROM accepted WHERE date=? LIMIT 1', (date,)).fetchone() or db.execute('SELECT 1 FROM staged_candidates WHERE date=? LIMIT 1', (date,)).fetchone():
            raise RegistryError('governed date already present in accepted or staged inputs')
        db.commit()
    finally:
        db.close()

    candidate = _candidate_path(source_roots, root, relative_path)
    with open(candidate, 'rb') as f:
        payload = f.read(MAX_ARCHIVE_BYTES + 1)
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise RegistryError('archive exceeds staging size limit')
    if hashlib.sha256(payload).hexdigest() != result['sha256']:
        raise RegistryError('source changed during inspection; retry')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [i for i in archive.infolist() if not i.is_dir()]
            if len(members) != 1 or not members[0].filename.lower().endswith('.csv'):
                raise RegistryError('archive must contain exactly one CSV member and no other files')
            member = members[0]
            if member.file_size > MAX_MEMBER_BYTES or member.flag_bits & 1:
                raise RegistryError('member exceeds size limit or is encrypted')
            with archive.open(member) as reader:
                content = reader.read(MAX_MEMBER_BYTES + 1)
            if len(content) > MAX_MEMBER_BYTES:
                raise RegistryError('member exceeds staging size limit')
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
        raise RegistryError('invalid or corrupt archive: %s' % exc) from exc
    run_id = 'incremental-' + hashlib.sha256(_json([baseline.manifest_digest, root, relative_path, date, result['sha256']]).encode()).hexdigest()[:24]
    source = SourceDescriptor(source_archive=result['file_name'], member_name=member.filename,
                              archive_sha256=result['sha256'], archive_sha256_basis='computed-archive-bytes',
                              expected_source_date=date, evidence_refs=('incremental-source-registry',), run_id=run_id)
    try:
        build = build_canonical(content, source, DEFAULT_CONFIG)
    except (NseEngineError, ValueError) as exc:
        raise RegistryError('canonical parser rejected member: %s' % exc) from exc
    expected_family = 'legacy13' if root == 'LEGACY' else 'udiff34'
    if build.parse.header.family != expected_family or not build.rows or build.quarantined:
        raise RegistryError('wrong family, empty member, or quarantined rows')
    if any(row.business_date != date for row in build.rows):
        raise RegistryError('member business date does not match governed date')
    rows, evidence = rows_jsonl(build.rows), evidence_json(build)
    record = {'root': root, 'relative_path': relative_path.replace(os.sep, '/'), 'file_name': result['file_name'],
              'date': date, 'digest': result['sha256'], 'run_id': run_id, 'member_name': member.filename,
              'family': expected_family, 'rows': len(build.rows), 'quarantined': 0,
              'baseline_manifest_sha256': baseline.manifest_digest, 'bindings': current,
              'rows_sha256': hashlib.sha256(rows.encode('utf8')).hexdigest(),
              'evidence_sha256': hashlib.sha256(evidence.encode('utf8')).hexdigest(),
              'state': 'VALIDATED-STAGED-NOT-PUBLISHED'}
    db, _ = _open(baseline, path)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        _schema(db)
        from .pending_queue import installed, verify, seal
        queue_installed = installed(db)
        if queue_installed:
            verify(db)
        # Recheck all predicates in the same transaction as staging. Never
        # overwrite either accepted or staged entries, including concurrent runs.
        if db.execute('SELECT 1 FROM accepted WHERE (file_name=? AND date=?) OR digest=? OR date=? LIMIT 1',
                      (record['file_name'], date, record['digest'], date)).fetchone():
            raise RegistryError('candidate became accepted, duplicated, or date-conflicting')
        if db.execute('SELECT 1 FROM staged_candidates WHERE (file_name=? AND date=?) OR digest=? OR date=? LIMIT 1',
                      (record['file_name'], date, record['digest'], date)).fetchone():
            raise RegistryError('candidate was staged concurrently; retry for its state')
        db.execute('INSERT INTO staged_candidates VALUES (?,?,?,?,?,?)',
                   (record['file_name'], date, record['digest'], _json(record), rows, evidence))
        if queue_installed:
            seal(db)
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise RegistryError('staging collision: %s' % exc) from exc
    finally:
        db.close()
    return {'status': 'VALIDATED-STAGED-NOT-PUBLISHED', 'record': record}


def list_staged(baseline, registry_root, state, saved, history, source_roots):
    path = _db_path(baseline, registry_root, state, saved, history, source_roots)
    db, _ = _open(baseline, path)
    try:
        found = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_candidates'").fetchone()
        return [json.loads(row[0]) for row in db.execute('SELECT record FROM staged_candidates ORDER BY file_name,date')] if found else []
    finally:
        db.close()
