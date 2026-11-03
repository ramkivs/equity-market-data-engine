"""Immutable, content-addressed incremental rows, evidence and identity groups.

The generation pins each digest; reads verify the selected content. Old blobs
are retained, so an in-flight reader remains valid across pointer switches.
"""
import hashlib
import os
import sqlite3
from collections.abc import Mapping
from urllib.parse import quote

from .query import QueryError


def sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS composite_blobs (digest TEXT PRIMARY KEY, content TEXT NOT NULL)')


def put(db, text, digest):
    if not isinstance(text, str) or sha(text) != digest:
        raise ValueError('incremental blob digest mismatch')
    db.execute('INSERT OR IGNORE INTO composite_blobs VALUES (?,?)', (digest, text))
    row = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (digest,)).fetchone()
    if row is None or row[0] != text:
        raise ValueError('incremental blob collision or corruption')


def get(db, digest):
    if not _valid_digest(digest):
        raise ValueError('invalid incremental blob digest')
    row = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (digest,)).fetchone()
    if row is None or not isinstance(row[0], str) or sha(row[0]) != digest:
        raise ValueError('incremental blob missing or digest mismatch')
    return row[0]


class BlobMap(Mapping):
    def __init__(self, path, references, expected=None):
        self.path = path
        from .persistent_index_map import PinnedReferenceMap
        self.references = references if isinstance(references, PinnedReferenceMap) else dict(references)
        self.expected = dict(expected) if expected is not None else None

    def __iter__(self):
        return iter(self.expected if self.expected is not None else self.references)

    def __len__(self):
        return len(self.references)

    def _reference(self, key):
        if self.expected is not None and key not in self.expected:
            raise KeyError(key)
        try:
            digest = self.references[key]
        except KeyError as exc:
            if self.expected is not None:
                raise QueryError('composite-unavailable', 'incremental blob reference missing') from exc
            raise
        if self.expected is not None and digest != self.expected[key]:
            raise QueryError('composite-unavailable', 'incremental blob reference mismatch')
        return digest

    def __contains__(self, key):
        try:
            self._reference(key)
            return True
        except KeyError:
            return False

    def __getitem__(self, key):
        digest = self._reference(key)
        if os.path.islink(self.path) or not os.path.isfile(self.path):
            raise QueryError('composite-unavailable', 'incremental blob registry missing or unsafe')
        try:
            db = sqlite3.connect('file:' + quote(os.path.abspath(self.path), safe='/') + '?mode=ro', uri=True)
            try:
                row = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (digest,)).fetchone()
            finally:
                db.close()
            if row is None or not isinstance(row[0], str) or sha(row[0]) != digest:
                raise ValueError('incremental blob missing or digest mismatch')
            return row[0]
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise QueryError('composite-unavailable', 'incremental blob read failed: %s' % exc) from exc


def validate_references(payload):
    """Validate the pinned per-candidate reference census, without reading blobs."""
    candidates, delta, evidence = payload.get('candidates'), payload.get('delta'), payload.get('evidence')
    if not isinstance(candidates, list) or not isinstance(delta, dict) or not isinstance(evidence, dict):
        raise ValueError('invalid incremental blob references')
    sources, digests = set(), set()
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError('invalid incremental candidate')
        digest, row_hash, ev_hash = item.get('digest'), item.get('rows_sha256'), item.get('evidence_sha256')
        for value in (digest, row_hash, ev_hash):
            if not isinstance(value, str) or len(value) != 64 or any(ch not in '0123456789abcdef' for ch in value):
                raise ValueError('invalid incremental blob digest')
        source = 'incremental/' + digest + '.rows.jsonl'
        if digest in digests or delta.get(source) != row_hash or evidence.get(digest) != ev_hash:
            raise ValueError('incremental blob reference mismatch')
        sources.add(source); digests.add(digest)
    if set(delta) != sources or set(evidence) != digests:
        raise ValueError('incremental blob reference census mismatch')


def _valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_group_references(payload):
    for name in ('w2_delta', 'b2_delta'):
        groups = payload.get(name)
        if not isinstance(groups, dict) or any(not isinstance(k, str) or not k or not _valid_digest(v) for k, v in groups.items()):
            raise ValueError('invalid incremental identity group references')


def group_document(kind, identity, rows, sources):
    """Verify identity and source for every projection in a detached group."""
    from nse_engine.compact import normalize_upper_trim
    from .continuity_catalog import _projection
    from .symbols import _identity
    if kind not in ('w2', 'b2') or not isinstance(identity, str) or not identity or not isinstance(rows, list) or not rows:
        raise ValueError('invalid incremental identity group')
    for item in rows:
        if not isinstance(item, list) or len(item) != 2 or item[0] not in sources:
            raise ValueError('incremental identity group source mismatch')
        projected = _projection(item[1])
        actual = normalize_upper_trim(projected['source_values']['security_isin']) if kind == 'w2' else _identity(projected)
        if projected != item[1] or actual != identity:
            raise ValueError('incremental identity group key mismatch')
    return {'kind': kind, 'identity': identity, 'rows': rows}


def load_group_from_db(db, kind, identity, digest, sources):
    import json
    row = db.execute('SELECT content FROM composite_blobs WHERE digest=?', (digest,)).fetchone()
    if row is None or not isinstance(row[0], str) or sha(row[0]) != digest:
        raise ValueError('incremental identity group blob missing or digest mismatch')
    doc = json.loads(row[0])
    if not isinstance(doc, dict) or set(doc) != {'kind', 'identity', 'rows'} or doc['kind'] != kind or doc['identity'] != identity:
        raise ValueError('incremental identity group blob identity mismatch')
    group_document(kind, identity, doc['rows'], sources)
    return doc['rows']


class GroupMap(BlobMap):
    def __init__(self, path, references, kind, sources):
        super().__init__(path, references)
        self.kind = kind
        self.sources = sources

    def __getitem__(self, key):
        if key not in self.references:
            raise KeyError(key)
        import json
        try:
            doc = json.loads(super().__getitem__(key))
            if not isinstance(doc, dict) or set(doc) != {'kind', 'identity', 'rows'} or doc['kind'] != self.kind or doc['identity'] != key:
                raise ValueError('incremental identity group blob identity mismatch')
            group_document(self.kind, key, doc['rows'], self.sources)
            return doc['rows']
        except (ValueError, TypeError, KeyError) as exc:
            raise QueryError('composite-unavailable', 'incremental identity group read failed: %s' % exc) from exc


def validate_override_references(payload):
    for name in ('w2_overrides', 'b3_overrides'):
        groups = payload.get(name)
        if not isinstance(groups, dict) or any(not isinstance(k, str) or not k or not _valid_digest(v) for k, v in groups.items()):
            raise ValueError('invalid incremental override references')
    if not set(payload['w2_delta']).issubset(payload['w2_overrides']) or not set(payload['b2_delta']).issubset(payload['b3_overrides']):
        raise ValueError('incremental override reference census mismatch')


def override_document(kind, identity, value):
    if kind not in ('w2', 'b3') or not isinstance(identity, str) or not identity:
        raise ValueError('invalid incremental override identity')
    if kind == 'w2':
        from .query import _validate_identity_document
        if value is not None:
            try:
                actual = _validate_identity_document(value, 'incremental override')
            except QueryError as exc:
                raise ValueError('invalid incremental W2 override: %s' % exc) from exc
            if actual != identity:
                raise ValueError('incremental W2 override identity mismatch')
    elif not isinstance(value, list) or any(not isinstance(group, dict) or group.get('security_id') != identity for group in value):
        raise ValueError('incremental B3 override identity mismatch')
    return {'kind': kind, 'identity': identity, 'value': value}


class OverrideMap(BlobMap):
    def __init__(self, path, references, kind):
        super().__init__(path, references)
        self.kind = kind

    def __contains__(self, key):
        return key in self.references

    def __getitem__(self, key):
        if key not in self.references:
            raise KeyError(key)
        import json
        try:
            doc = json.loads(super().__getitem__(key))
            if not isinstance(doc, dict) or set(doc) != {'kind', 'identity', 'value'} or doc['kind'] != self.kind or doc['identity'] != key:
                raise ValueError('incremental override blob identity mismatch')
            override_document(self.kind, key, doc['value'])
            return doc['value']
        except (ValueError, TypeError, KeyError) as exc:
            raise QueryError('composite-unavailable', 'incremental override read failed: %s' % exc) from exc
