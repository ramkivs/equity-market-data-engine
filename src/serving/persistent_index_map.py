"""Immutable SHA-256 trie for generation-pinned incremental file metadata.

Only the changed key path is rewritten. The root and every child are
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


def insert(db, root, key, value):
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
