"""Durable state-to-registry binding for normal application readers.

A binding is written before any publication and is never silently replaced.
An incomplete or mismatched binding fails closed; it is not a generation pointer.
"""
import hashlib
import json
import os

from .paths import resolved, validate_roots
from .query import QueryError

BINDING_FILE = 'composite_registry.json'
FORMAT = 'composite-registry-binding/1.0'


def has_binding(state_root):
    return os.path.lexists(os.path.join(state_root, BINDING_FILE))


def ensure_registry_binding(baseline, state_root, registry_root):
    if not os.path.isfile(os.path.join(registry_root, 'source_registry.sqlite3')):
        raise QueryError('composite-unavailable', 'registry missing; initialize it before binding')
    from .incremental_registry import DB_NAME, _open
    try:
        db, _ = _open(baseline, os.path.join(registry_root, DB_NAME))
        db.close()
    except Exception as exc:
        raise QueryError('composite-unavailable', 'cannot bind registry: %s' % exc) from exc
    ensure_binding(baseline, state_root, registry_root)


def read_binding(baseline, state_root):
    path = os.path.join(state_root, BINDING_FILE)
    if not os.path.lexists(path):
        return None
    if os.path.islink(path) or not os.path.isfile(path):
        raise QueryError('composite-unavailable', 'unsafe composite registry binding')
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


def _binding_digest(doc):
    raw = json.dumps(doc, sort_keys=True, separators=(',', ':')).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def ensure_binding(baseline, state_root, registry_root):
    """Persist an immutable binding; interrupted creation is left fail-closed."""
    registry = resolved(registry_root)
    validate_roots(package=baseline.root, state=state_root, registry=registry)
    previous = read_binding(baseline, state_root)
    if previous is not None:
        if previous != registry:
            raise QueryError('composite-unavailable', 'serving state already bound to a different registry')
        return
    doc = {'format': FORMAT, 'baseline_manifest_sha256': baseline.manifest_digest, 'registry_root': registry}
    doc['binding_sha256'] = _binding_digest(doc)
    content = json.dumps(doc, sort_keys=True, separators=(',', ':')) + '\n'
    path = os.path.join(state_root, BINDING_FILE)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if read_binding(baseline, state_root) != registry:
            raise QueryError('composite-unavailable', 'serving state already bound to a different registry')
        return
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
