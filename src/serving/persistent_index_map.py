"""Immutable SHA-256 trie for generation-pinned metadata and references.

Only the changed key path is rewritten; file metadata and blob references
share the content-addressed node representation. The root and every child are
content-addressed; omitted, miskeyed or damaged nodes fail closed when read.
"""
import hashlib
import json

from .composite_blobs import get, put, sha
from .incremental_registry import _json

FORMAT = 'incremental-index-trie/1.0'


def _key_hash(key):
    if not isinstance(key, str) or not key:
        raise ValueError('invalid incremental index tree key')
    return hashlib.sha256(key.encode('utf8')).hexdigest()


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _read(db, digest, depth):
    if not _digest(digest):
        raise ValueError('invalid incremental index tree digest')
    try:
        node = json.loads(get(db, digest))
    except (TypeError, ValueError) as exc:
        raise ValueError('incremental index tree node corrupt: %s' % exc) from exc
    if not isinstance(node, dict) or node.get('format') != FORMAT or node.get('depth') != depth:
        raise ValueError('invalid incremental index tree node identity')
    if depth == 64:
        if set(node) != {'format', 'depth', 'key', 'value'} or not isinstance(node['key'], str) or not isinstance(node['value'], dict):
            raise ValueError('invalid incremental index tree leaf')
    else:
        children = node.get('children')
        if (set(node) != {'format', 'depth', 'children'} or not isinstance(children, dict) or not children or
                any(k not in '0123456789abcdef' or len(k) != 1 or not _digest(v) for k, v in children.items())):
            raise ValueError('invalid incremental index tree children')
    return node


def lookup(db, root, key):
    path = _key_hash(key)
    if root is None:
        return None
    current = root
    for depth in range(64):
        node = _read(db, current, depth)
        current = node['children'].get(path[depth])
        if current is None:
            return None
    leaf = _read(db, current, 64)
    if leaf['key'] != key:
        raise ValueError('incremental index tree key hash collision')
    return leaf['value']


def insert(db, root, key, value, replace=False):
    path = _key_hash(key)
    if not isinstance(value, dict):
        raise ValueError('invalid incremental index tree value')
    nodes = []
    current = root
    for depth in range(64):
        children = dict(_read(db, current, depth)['children']) if current is not None else {}
        nodes.append(children)
        current = children.get(path[depth])
    if current is not None:
        leaf = _read(db, current, 64)
        if leaf['key'] != key:
            raise ValueError('incremental index tree key hash collision')
        if not replace:
            raise ValueError('incremental index tree key already exists')
    text = _json({'format': FORMAT, 'depth': 64, 'key': key, 'value': value})
    current = sha(text); put(db, text, current)
    for depth in range(63, -1, -1):
        nodes[depth][path[depth]] = current
        text = _json({'format': FORMAT, 'depth': depth, 'children': nodes[depth]})
        current = sha(text); put(db, text, current)
    return current


def entries(db, root):
    if root is None:
        return {}
    result = {}
    def visit(digest, depth, prefix):
        node = _read(db, digest, depth)
        if depth == 64:
            key = node['key']
            if _key_hash(key) != prefix or key in result:
                raise ValueError('incremental index tree leaf path mismatch')
            result[key] = node['value']
        else:
            for nibble, child in sorted(node['children'].items()):
                visit(child, depth + 1, prefix + nibble)
    visit(root, 0, '')
    return result


def validate_header(index_tree, candidates):
    if not isinstance(index_tree, dict) or set(index_tree) != {'root', 'file_count', 'row_count', 'flag_census'}:
        raise ValueError('invalid incremental index tree header')
    root, files, rows, flags = (index_tree[k] for k in ('root', 'file_count', 'row_count', 'flag_census'))
    if ((root is not None and not _digest(root)) or type(files) is not int or files < 0 or type(rows) is not int or rows < 0 or
            not isinstance(candidates, list) or files != len(candidates) or (root is None) != (files == 0) or
            not isinstance(flags, dict) or any(not isinstance(k, str) or not k or type(v) is not int or v <= 0 for k, v in flags.items())):
        raise ValueError('invalid incremental index tree census')


def materialize(db, index_tree, candidates):
    from .composite_index import validate
    validate_header(index_tree, candidates)
    delta = {'files': entries(db, index_tree['root']), 'flag_census': dict(index_tree['flag_census'])}
    validate(delta, candidates)
    if len(delta['files']) != index_tree['file_count'] or sum(v['row_count'] for v in delta['files'].values()) != index_tree['row_count']:
        raise ValueError('incremental index tree counts mismatch')
    return delta


def from_overlay(db, delta, candidates):
    from .composite_index import validate
    validate(delta, candidates)
    root = None
    for key, value in sorted(delta['files'].items()):
        root = insert(db, root, key, value)
    return {'root': root, 'file_count': len(delta['files']),
            'row_count': sum(value['row_count'] for value in delta['files'].values()),
            'flag_census': dict(delta['flag_census'])}


class ReferenceTree:
    """Mutable transaction-local view of immutable, digest-valued references."""
    def __init__(self, db, header, allow_updates=False):
        validate_reference_header(header)
        self.db = db
        self.header = header
        self.allow_updates = allow_updates
        self._cache = {}

    def __getitem__(self, key):
        if key not in self._cache:
            value = lookup(self.db, self.header['root'], key)
            if value is None:
                raise KeyError(key)
            if set(value) != {'digest'} or not _digest(value['digest']):
                raise ValueError('invalid reference tree value')
            self._cache[key] = value['digest']
        return self._cache[key]

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __setitem__(self, key, digest):
        if not _digest(digest):
            raise ValueError('invalid reference tree digest')
        exists = self.get(key) is not None if self.allow_updates else False
        self.header['root'] = insert(self.db, self.header['root'], key, {'digest': digest}, replace=exists)
        if not exists:
            self.header['count'] += 1
        self._cache[key] = digest

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def validate_reference_header(header):
    if (not isinstance(header, dict) or set(header) != {'root', 'count'} or
            type(header['count']) is not int or header['count'] < 0 or
            (header['root'] is not None and not _digest(header['root'])) or
            (header['root'] is None) != (header['count'] == 0)):
        raise ValueError('invalid reference tree header')


def validate_reference_trees(trees, candidates):
    if not isinstance(trees, dict) or set(trees) != {'delta', 'evidence'} or not isinstance(candidates, list):
        raise ValueError('invalid reference tree census')
    for header in trees.values():
        validate_reference_header(header)
        if header['count'] != len(candidates):
            raise ValueError('reference tree candidate count mismatch')


def reference_dict(db, header):
    validate_reference_header(header)
    found = entries(db, header['root'])
    if len(found) != header['count']:
        raise ValueError('reference tree count mismatch')
    result = {}
    for key, value in found.items():
        if set(value) != {'digest'} or not _digest(value['digest']):
            raise ValueError('invalid reference tree value')
        result[key] = value['digest']
    return result


def reference_trees_from_payload(db, payload):
    from .composite_blobs import validate_references
    validate_references(payload)
    trees = {name: {'root': None, 'count': 0} for name in ('delta', 'evidence')}
    for name in ('delta', 'evidence'):
        view = ReferenceTree(db, trees[name])
        for key, digest in sorted(payload[name].items()):
            view[key] = digest
    return trees


DERIVED_NAMES = ('w2_delta', 'b2_delta', 'w2_overrides', 'b3_overrides')


def validate_derived_trees(trees):
    if not isinstance(trees, dict) or set(trees) != set(DERIVED_NAMES):
        raise ValueError('invalid derived reference tree census')
    for header in trees.values():
        validate_reference_header(header)
    if trees['w2_delta']['count'] > trees['w2_overrides']['count'] or trees['b2_delta']['count'] > trees['b3_overrides']['count']:
        raise ValueError('derived reference tree count mismatch')


def derived_trees_from_payload(db, payload):
    from .composite_blobs import validate_group_references, validate_override_references
    validate_group_references(payload)
    validate_override_references(payload)
    trees = {name: {'root': None, 'count': 0} for name in DERIVED_NAMES}
    for name in DERIVED_NAMES:
        view = ReferenceTree(db, trees[name])
        for key, digest in sorted(payload[name].items()):
            view[key] = digest
    return trees
