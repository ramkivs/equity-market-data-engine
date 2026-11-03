"""Immutable, content-addressed incremental rows and evidence in the registry.

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


class BlobMap(Mapping):
    def __init__(self, path, references):
        self.path = path
        self.references = dict(references)

    def __iter__(self):
        return iter(self.references)

    def __len__(self):
        return len(self.references)

    def __getitem__(self, key):
        digest = self.references[key]
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
