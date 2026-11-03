"""Generation-pinned balanced proof tree for baseline ticker lookup groups."""
import json
from .composite_blobs import get, put, sha
from .identity_proof_tree import IdentityProofTree, _digest
from .incremental_registry import _json

FORMAT = 'baseline-ticker-proof-tree/1.0'


def validate_header(header, proof_meta):
    if (not isinstance(header, dict) or set(header) != {'root', 'count', 'group_sha256'} or
            not isinstance(proof_meta, dict) or type(header['count']) is not int or header['count'] < 0 or
            header['count'] != proof_meta.get('group_count') or header['group_sha256'] != proof_meta.get('group_sha256') or
            not _digest(header['group_sha256']) or
            (header['root'] is not None and not _digest(header['root'])) or
            (header['root'] is None) != (header['count'] == 0)):
        raise ValueError('invalid baseline ticker proof tree binding')


def _node(db, digest, lower=None, upper=None):
    if not _digest(digest):
        raise ValueError('invalid ticker proof node digest')
    try:
        node = json.loads(get(db, digest))
    except (ValueError, TypeError) as exc:
        raise ValueError('ticker proof tree node corrupt: %s' % exc) from exc
    if not isinstance(node, dict) or set(node) != {'format', 'kind', 'selector', 'series', 'row_count', 'group_sha256', 'left', 'right'}:
        raise ValueError('invalid ticker proof tree node')
    key = (node['kind'], node['selector'], node['series'])
    if (node['format'] != FORMAT or key[0] not in ('ticker', 'identity') or
            not isinstance(key[1], str) or not key[1] or not isinstance(key[2], str) or
            type(node['row_count']) is not int or node['row_count'] <= 0 or not _digest(node['group_sha256']) or
            any(child is not None and not _digest(child) for child in (node['left'], node['right'])) or
            (lower is not None and key <= lower) or (upper is not None and key >= upper)):
        raise ValueError('invalid ticker proof tree node ordering or value')
    return node, key


def build(db, proof_db, proof_meta):
    from .ticker_proofs import _manifest
    if not db.in_transaction or not proof_db.in_transaction:
        raise ValueError('ticker proof tree bootstrap requires bound transactions')
    digest, count, groups = _manifest(proof_db)
    if digest != proof_meta.get('group_sha256') or count != proof_meta.get('group_count'):
        raise ValueError('ticker lookup proof group manifest mismatch')
    items = sorted(groups.items())
    def subtree(lo, hi):
        if lo == hi:
            return None
        mid = (lo + hi) // 2
        (kind, selector, series), (n, group_digest) = items[mid]
        left, right = subtree(lo, mid), subtree(mid + 1, hi)
        text = _json({'format': FORMAT, 'kind': kind, 'selector': selector, 'series': series,
                      'row_count': n, 'group_sha256': group_digest, 'left': left, 'right': right})
        digest = sha(text); put(db, text, digest)
        return digest
    header = {'root': subtree(0, len(items)), 'count': count, 'group_sha256': digest}
    validate_header(header, proof_meta)
    return header


class TickerProofTree(IdentityProofTree):
    def __init__(self, header, proof_meta, db=None, path=None):
        validate_header(header, proof_meta)
        self.header, self.db, self.path = dict(header), db, path

    def get(self, key, default=None):
        if (not isinstance(key, tuple) or len(key) != 3 or key[0] not in ('ticker', 'identity') or
                not isinstance(key[1], str) or not isinstance(key[2], str)):
            raise ValueError('invalid ticker proof selector')
        with self._connection() as db:
            digest, lower, upper = self.header['root'], None, None
            while digest is not None:
                node, here = _node(db, digest, lower, upper)
                if key == here:
                    return node['row_count'], node['group_sha256']
                if key < here:
                    digest, upper = node['left'], here
                else:
                    digest, lower = node['right'], here
            return default

    def ticker_series(self, ticker):
        if not isinstance(ticker, str):
            raise ValueError('invalid ticker proof selector')
        prefix = ('ticker', ticker)
        result = set()
        with self._connection() as db:
            def visit(digest, lower, upper):
                if digest is None:
                    return
                node, key = _node(db, digest, lower, upper)
                if key[:2] >= prefix:
                    visit(node['left'], lower, key)
                if key[:2] == prefix:
                    result.add(key[2])
                if key[:2] <= prefix:
                    visit(node['right'], key, upper)
            visit(self.header['root'], None, None)
        return result

    def verify(self, proof_db, proof_meta):
        from .ticker_proofs import _manifest
        if not proof_db.in_transaction:
            raise ValueError('ticker proof tree verification requires bound proof transaction')
        validate_header(self.header, proof_meta)
        actual = {}
        with self._connection() as db:
            def visit(digest, lower, upper):
                if digest is None:
                    return
                node, key = _node(db, digest, lower, upper)
                visit(node['left'], lower, key)
                if key in actual:
                    raise ValueError('duplicate ticker proof key')
                actual[key] = node['row_count'], node['group_sha256']
                visit(node['right'], key, upper)
            visit(self.header['root'], None, None)
        digest, count, groups = _manifest(proof_db)
        if digest != proof_meta['group_sha256'] or count != proof_meta['group_count'] or actual != groups:
            raise ValueError('ticker proof tree disagrees with proof group manifest')
        return {'count': count, 'group_sha256': digest}


def recover(baseline, state, registry, saved, history, source_roots):
    """Restore missing bound nodes only; never replace existing content."""
    from .continuity_catalog import _metadata, open_catalog
    from .incremental_publication import _sha as generation_sha
    from .incremental_registry import _db_path, _open
    from .ticker_proofs import open_proofs
    path = _db_path(baseline, registry, state, saved, history, source_roots)
    db, _ = _open(baseline, path)
    cat = proofs = None
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT a.generation,g.payload FROM composite_active a JOIN composite_generations g ON g.id=a.generation WHERE a.singleton=1').fetchone()
        if row is None or generation_sha(row[1]) != row[0]:
            raise ValueError('active generation missing or invalid')
        payload = json.loads(row[1])
        if payload.get('format') != 'catalog-composite/14.0' or payload.get('baseline_manifest_sha256') != baseline.manifest_digest:
            raise ValueError('active generation has no ticker proof tree binding')
        cat, meta = open_catalog(baseline, state)
        cat.execute('BEGIN')
        if _metadata(cat) != meta or payload.get('catalog_binding') != meta or payload.get('baseline_index_sha256') != meta['baseline_index_sha256']:
            raise ValueError('active generation catalog binding mismatch')
        proofs, proof_meta, _ = open_proofs(state, meta, payload.get('ticker_proofs_binding'))
        expected = payload.get('ticker_proof_tree')
        validate_header(expected, proof_meta)
        actual = build(db, proofs, proof_meta)
        if actual != expected:
            raise ValueError('reconstructed ticker proof tree binding mismatch')
        db.commit()
        return {'status': 'VERIFIED-OR-RECOVERED', 'generation': row[0], 'binding': actual}
    finally:
        if proofs is not None:
            proofs.close()
        if cat is not None:
            cat.close()
        db.close()
