"""Immutable balanced search tree of verified baseline identity-group proofs.

Bootstrap uses the catalog's fully verified group manifest once. Each node is
content-addressed and roots are generation-pinned; a lookup verifies the entire
search path, including ordering, and the catalog verifies the selected rows.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from urllib.parse import quote

from .composite_blobs import get, put, sha
from .incremental_registry import _json

FORMAT = 'baseline-identity-proof-tree/1.0'


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def validate_header(header, catalog_meta):
    if (not isinstance(header, dict) or set(header) != {'root', 'count', 'catalog_group_sha256'} or
            type(header['count']) is not int or header['count'] < 0 or
            header['count'] != catalog_meta.get('group_count') or
            header['catalog_group_sha256'] != catalog_meta.get('group_sha256') or
            (header['root'] is not None and not _digest(header['root'])) or
            (header['root'] is None) != (header['count'] == 0)):
        raise ValueError('invalid baseline identity proof tree binding')


def _node(db, digest, lower=None, upper=None):
    if not _digest(digest):
        raise ValueError('invalid identity proof node digest')
    try:
        node = json.loads(get(db, digest))
    except (ValueError, TypeError) as exc:
        raise ValueError('identity proof tree node corrupt: %s' % exc) from exc
    if not isinstance(node, dict) or set(node) != {'format', 'kind', 'identity', 'row_count', 'group_sha256', 'left', 'right'}:
        raise ValueError('invalid identity proof tree node')
    key = (node['kind'], node['identity'])
    if (node['format'] != FORMAT or key[0] not in ('w2', 'b2') or not isinstance(key[1], str) or not key[1] or
            type(node['row_count']) is not int or node['row_count'] <= 0 or not _digest(node['group_sha256']) or
            any(child is not None and not _digest(child) for child in (node['left'], node['right'])) or
            (lower is not None and key <= lower) or (upper is not None and key >= upper)):
        raise ValueError('invalid identity proof tree node ordering or value')
    return node, key


def build(db, catalog_db, catalog_meta):
    """Build once from verified compact metadata, not historical rows."""
    from .continuity_catalog import _metadata, _validated_groups
    if not db.in_transaction or not catalog_db.in_transaction or _metadata(catalog_db) != catalog_meta:
        raise ValueError('identity proof bootstrap requires bound transactions')
    items = sorted(_validated_groups(catalog_db, catalog_meta).items())
    def subtree(lo, hi):
        if lo == hi:
            return None
        mid = (lo + hi) // 2
        (kind, identity), (count, digest) = items[mid]
        left, right = subtree(lo, mid), subtree(mid + 1, hi)
        text = _json({'format': FORMAT, 'kind': kind, 'identity': identity, 'row_count': count,
                      'group_sha256': digest, 'left': left, 'right': right})
        result = sha(text); put(db, text, result)
        return result
    header = {'root': subtree(0, len(items)), 'count': len(items), 'catalog_group_sha256': catalog_meta['group_sha256']}
    validate_header(header, catalog_meta)
    return header


class IdentityProofTree:
    def __init__(self, header, catalog_meta, db=None, path=None):
        validate_header(header, catalog_meta)
        self.header, self.db, self.path = dict(header), db, path

    @contextmanager
    def _connection(self):
        if self.db is not None:
            yield self.db
        else:
            if not self.path or os.path.islink(self.path) or not os.path.isfile(self.path):
                raise ValueError('proof registry missing or unsafe')
            db = sqlite3.connect('file:' + quote(os.path.abspath(self.path), safe='/') + '?mode=ro', uri=True)
            try:
                yield db
            finally:
                db.close()

    def get(self, key, default=None):
        if not isinstance(key, tuple) or len(key) != 2 or key[0] not in ('w2', 'b2') or not isinstance(key[1], str) or not key[1]:
            raise ValueError('invalid identity proof selector')
        with self._connection() as db:
            current, lower, upper = self.header['root'], None, None
            while current is not None:
                node, current_key = _node(db, current, lower, upper)
                if key == current_key:
                    return (node['row_count'], node['group_sha256'])
                if key < current_key:
                    current, upper = node['left'], current_key
                else:
                    current, lower = node['right'], current_key
            return default

    def verify(self, catalog_db, catalog_meta):
        """Explicitly compare every proof with the fully verified catalog manifest."""
        from .continuity_catalog import _metadata, _validated_groups
        if not catalog_db.in_transaction or _metadata(catalog_db) != catalog_meta:
            raise ValueError('identity proof full verification requires bound catalog transaction')
        validate_header(self.header, catalog_meta)
        actual = {}
        with self._connection() as db:
            def visit(digest, lower, upper):
                if digest is None:
                    return
                node, key = _node(db, digest, lower, upper)
                visit(node['left'], lower, key)
                if key in actual:
                    raise ValueError('duplicate identity proof key')
                actual[key] = (node['row_count'], node['group_sha256'])
                visit(node['right'], key, upper)
            visit(self.header['root'], None, None)
        if len(actual) != self.header['count'] or actual != _validated_groups(catalog_db, catalog_meta):
            raise ValueError('identity proof tree disagrees with catalog group manifest')
        return {'count': len(actual), 'catalog_group_sha256': self.header['catalog_group_sha256']}


def recover(baseline, state, registry, saved, history, source_roots):
    """Explicitly reconstruct missing tree nodes only for the active binding.

    Existing content is never overwritten. Catalog manifest corruption or a
    regenerated root that differs from the pinned generation aborts the whole
    transaction; neither source archives nor baseline canonical rows are read.
    """
    from .continuity_catalog import _metadata, open_catalog
    from .incremental_publication import _sha as generation_sha
    from .incremental_registry import _db_path, _open
    path = _db_path(baseline, registry, state, saved, history, source_roots)
    db, _ = _open(baseline, path)
    cat = None
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT a.generation,g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation WHERE a.singleton=1').fetchone()
        if row is None or generation_sha(row[1]) != row[0]:
            raise ValueError('active generation missing or invalid')
        payload = json.loads(row[1])
        if payload.get('format') not in ('catalog-composite/13.0', 'catalog-composite/14.0') or payload.get('baseline_manifest_sha256') != baseline.manifest_digest:
            raise ValueError('active generation has no identity proof tree binding')
        cat, meta = open_catalog(baseline, state)
        cat.execute('BEGIN')
        if _metadata(cat) != meta or payload.get('catalog_binding') != meta or payload.get('baseline_index_sha256') != meta['baseline_index_sha256']:
            raise ValueError('active generation catalog binding mismatch')
        expected = payload.get('identity_proof_tree')
        validate_header(expected, meta)
        actual = build(db, cat, meta)
        if actual != expected:
            raise ValueError('reconstructed identity proof tree binding mismatch')
        db.commit()
        return {'status': 'VERIFIED-OR-RECOVERED', 'generation': row[0], 'binding': actual}
    finally:
        if cat is not None:
            cat.close()
        db.close()
