"""Durable state-to-registry binding for normal application readers.

A binding is written before any publication and is never silently replaced.
An incomplete or mismatched binding fails closed; it is not a generation pointer.
"""
import hashlib
import json
import os
from collections.abc import Mapping

from .paths import resolved, validate_roots
from .query import QueryError

BINDING_FILE = 'composite_registry.json'
GUARD_FILE = 'composite_registry_guard.json'
FORMAT = 'composite-registry-binding/1.0'


def has_binding(state_root):
    return any(os.path.lexists(os.path.join(state_root, name)) for name in (BINDING_FILE, GUARD_FILE))


def validate_inline_payload(db, baseline, payload):
    """Check old inline accepted evidence before moving it into immutable blobs."""
    from .incremental_drafts import _validate
    candidates, delta, evidence = payload.get('candidates'), payload.get('delta'), payload.get('evidence')
    if not isinstance(candidates, list) or not isinstance(delta, dict) or not isinstance(evidence, dict):
        raise ValueError('invalid inline generation evidence')
    accepted = {}
    for name, date, digest, text in db.execute('SELECT file_name,date,digest,record FROM accepted'):
        entry = json.loads(text)
        if entry.get('publication_kind') == 'composite':
            key = (name, date, digest)
            if (entry.get('file_name'), entry.get('date'), entry.get('digest')) != key:
                raise ValueError('inline accepted registry identity mismatch')
            accepted[key] = entry
    sources, digests, identities = set(), set(), set()
    for item in candidates:
        key = (item['file_name'], item['date'], item['digest'])
        source = 'incremental/' + item['digest'] + '.rows.jsonl'
        entry = accepted.get(key)
        if key in identities or item['digest'] in digests or entry is None or any(entry.get(k) != v for k, v in item.items()):
            raise ValueError('inline accepted input mismatch')
        _validate(item, delta[source], evidence[item['digest']], baseline)
        identities.add(key); sources.add(source); digests.add(item['digest'])
    if identities != set(accepted) or sources != set(delta) or digests != set(evidence):
        raise ValueError('inline generation evidence census mismatch')


def validate_registry(baseline, state_root, registry_root):
    """Validate an explicitly identified registry without modifying its data.

    Checks baseline manifest and retained staged/published evidence, not source
    archives or historical canonical rows. Hold the registry write lock while
    validating so publication cannot change it between checks.
    """
    from .incremental_registry import DB_NAME, _open, _manifest_entries
    from .incremental_drafts import _validate
    from .incremental_publication import active_snapshot
    path = os.path.join(registry_root, DB_NAME)
    db = None
    try:
        db, _ = _open(baseline, path)
        db.execute('BEGIN IMMEDIATE')
        expected = {(r['file_name'], r['date_from_filename'], r['archive_sha256_observed_raw_bytes']): r
                    for r in _manifest_entries(baseline)}
        accepted = {}
        for name, date, digest, text in db.execute('SELECT file_name,date,digest,record FROM accepted'):
            record = json.loads(text)
            identity = (name, date, digest)
            if not isinstance(record, dict):
                raise ValueError('invalid accepted record')
            if record.get('publication_kind') == 'composite':
                if (record.get('file_name'), record.get('date'), record.get('digest')) != identity:
                    raise ValueError('accepted composite identity mismatch')
                accepted[identity] = record
            else:
                if identity not in expected or record != expected.pop(identity):
                    raise ValueError('baseline accepted record does not match input manifest')
        if expected:
            raise ValueError('baseline accepted records missing from registry')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        staged_count = 0
        if 'staged_candidates' in tables:
            for name, date, digest, text, rows, evidence in db.execute('SELECT file_name,date,digest,record,rows,evidence FROM staged_candidates'):
                record = json.loads(text)
                if (record.get('file_name'), record.get('date'), record.get('digest')) != (name, date, digest):
                    raise ValueError('staged record identity mismatch')
                _validate(record, rows, evidence, baseline)
                staged_count += 1
        for name, date, digest, text in db.execute('SELECT file_name,date,digest,record FROM conflicts'):
            record = json.loads(text)
            if (record.get('file_name'), record.get('date'), record.get('sha256')) != (name, date, digest) or record.get('status') != 'CHANGED-CONFLICT-UNRESOLVED':
                raise ValueError('D21 conflict identity mismatch')
        snapshot = active_snapshot(baseline, registry_root, state_root)
        if snapshot is None:
            if accepted:
                raise ValueError('published accepted entries lack an active generation')
            generation = None
        else:
            selected = snapshot[0]
            candidates = selected.payload.get('candidates')
            delta, evidence = selected.payload.get('delta'), selected.payload.get('evidence')
            if not isinstance(candidates, list) or not isinstance(delta, Mapping) or not isinstance(evidence, Mapping):
                raise ValueError('active generation evidence is invalid')
            identities, sources, digests = set(), set(), set()
            def retained_rows():
                for item in candidates:
                    identity = (item['file_name'], item['date'], item['digest'])
                    source = 'incremental/' + item['digest'] + '.rows.jsonl'
                    entry = accepted.get(identity)
                    if identity in identities or item['digest'] in digests or entry is None or any(entry.get(k) != v for k, v in item.items()):
                        raise ValueError('active generation disagrees with accepted registry')
                    rows = _validate(item, delta[source], evidence[item['digest']], baseline)
                    identities.add(identity); sources.add(source); digests.add(item['digest'])
                    for row in rows:
                        yield source, row
            if selected.payload.get('format') == 'catalog-composite/11.0':
                from .catalog_publication import _merge_tickers
                derived_tickers = _merge_tickers({'observations': []}, retained_rows())
            else:
                for _ in retained_rows():
                    pass
            if identities != set(accepted) or set(delta) != sources or set(evidence) != digests:
                raise ValueError('active generation has missing or extra accepted evidence')
            if selected.payload.get('format') in ('catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0', 'catalog-composite/7.0', 'catalog-composite/8.0', 'catalog-composite/9.0', 'catalog-composite/10.0', 'catalog-composite/11.0'):
                for kind in ('w2_delta', 'b2_delta'):
                    for identity in selected.payload[kind]:
                        selected.payload[kind][identity]  # verify all detached groups during explicit binding
            if selected.payload.get('format') in ('catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0', 'catalog-composite/7.0', 'catalog-composite/8.0', 'catalog-composite/9.0', 'catalog-composite/10.0', 'catalog-composite/11.0'):
                for kind in ('w2_overrides', 'b3_overrides'):
                    for identity in selected.payload[kind]:
                        selected.payload[kind][identity]
            if selected.payload.get('format') == 'catalog-composite/11.0':
                actual_tickers = selected.payload['symbol_delta']['observations']  # full tree cross-check
                if list(derived_tickers['observations']) != list(actual_tickers):
                    raise ValueError('ticker delta trees disagree with retained incremental rows')
            generation = selected.manifest_digest
        return {'generation': generation, 'accepted_incremental': len(accepted), 'staged': staged_count}
    except Exception as exc:
        raise QueryError('composite-unavailable', 'cannot bind explicitly configured registry: %s' % exc) from exc
    finally:
        if db is not None:
            db.close()


def ensure_registry_binding(baseline, state_root, registry_root):
    """Validate and explicitly bind or repair a known registry, without guessing."""
    validate_roots(package=baseline.root, state=state_root, registry=registry_root)
    facts = validate_registry(baseline, state_root, registry_root)
    ensure_binding(baseline, state_root, registry_root, allow_repair=True)
    return facts


def _read_file(baseline, state_root, name):
    path = os.path.join(state_root, name)
    if not os.path.lexists(path):
        return None
    if os.path.islink(path) or not os.path.isfile(path):
        raise QueryError('composite-unavailable', 'unsafe composite registry binding or guard')
    try:
        with open(path, encoding='utf8') as f:
            text = f.read(8193)
        if len(text) > 8192:
            raise ValueError('oversized binding')
        doc = json.loads(text)
        if set(doc) != {'format', 'baseline_manifest_sha256', 'registry_root', 'binding_sha256'}:
            raise ValueError('binding schema mismatch')
        expected = _binding_digest({key: doc[key] for key in ('format', 'baseline_manifest_sha256', 'registry_root')})
        if doc['binding_sha256'] != expected:
            raise ValueError('binding digest mismatch')
        registry = doc['registry_root']
        if (doc['format'] != FORMAT or doc['baseline_manifest_sha256'] != baseline.manifest_digest or
                not isinstance(registry, str) or not os.path.isabs(registry) or resolved(registry) != registry):
            raise ValueError('binding identity mismatch')
        validate_roots(package=baseline.root, state=state_root, registry=registry)
        return registry
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise QueryError('composite-unavailable', 'invalid composite registry binding: %s' % exc) from exc


def read_binding(baseline, state_root):
    binding = _read_file(baseline, state_root, BINDING_FILE)
    guard = _read_file(baseline, state_root, GUARD_FILE)
    if binding is None and guard is not None:
        raise QueryError('composite-unavailable', 'registry binding missing; explicitly rebind the previously configured registry')
    if binding is not None and guard is not None and binding != guard:
        raise QueryError('composite-unavailable', 'registry binding and guard disagree')
    return binding


def _binding_digest(doc):
    raw = json.dumps(doc, sort_keys=True, separators=(',', ':')).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def ensure_binding(baseline, state_root, registry_root, allow_repair=False):
    """Persist immutable matching binding and guard; never overwrite either."""
    registry = resolved(registry_root)
    validate_roots(package=baseline.root, state=state_root, registry=registry)
    binding = _read_file(baseline, state_root, BINDING_FILE)
    guard = _read_file(baseline, state_root, GUARD_FILE)
    if (binding is not None and binding != registry) or (guard is not None and guard != registry):
        raise QueryError('composite-unavailable', 'serving state already bound to a different registry')
    if binding is None and guard is not None and not allow_repair:
        raise QueryError('composite-unavailable', 'registry binding missing; explicitly rebind the previously configured registry')
    doc = {'format': FORMAT, 'baseline_manifest_sha256': baseline.manifest_digest, 'registry_root': registry}
    doc['binding_sha256'] = _binding_digest(doc)
    content = json.dumps(doc, sort_keys=True, separators=(',', ':')) + '\n'
    # Guard first: interruption cannot silently revert a newly bound state to
    # baseline-only. Explicit rebinding can finish an interrupted operation.
    for name in (GUARD_FILE, BINDING_FILE):
        path = os.path.join(state_root, name)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if _read_file(baseline, state_root, name) != registry:
                raise QueryError('composite-unavailable', 'serving state already bound to a different registry')
            continue
        with os.fdopen(fd, 'w', encoding='utf8', newline='') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if os.name == 'posix':
            fd = os.open(state_root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def selected_snapshot(baseline, state_root):
    registry = read_binding(baseline, state_root)
    if registry is None:
        return None
    from .incremental_publication import active_snapshot
    try:
        return active_snapshot(baseline, registry, state_root)
    except Exception as exc:
        raise QueryError('composite-unavailable', 'composite selection failed: %s' % exc) from exc
