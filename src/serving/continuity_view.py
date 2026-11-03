"""Bounded application access to the optional B3 continuity derivation."""
from threading import Lock
import sqlite3

from .w2_continuity import FORMAT, build_continuity, canonical_rows

# The B3 generator retains per-row evidence in memory. Never try to build its
# potentially multi-gigabyte document implicitly for the real M2 corpus.
MAX_AUTOMATIC_ROWS = 20000
_cache = {}
_lock = Lock()


def get_continuity(baseline, index):
    if hasattr(baseline, 'payload'):
        if baseline.payload.get('format') in ('catalog-composite/1.0', 'catalog-composite/2.0', 'catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0', 'catalog-composite/7.0', 'catalog-composite/8.0', 'catalog-composite/9.0', 'catalog-composite/10.0', 'catalog-composite/11.0', 'catalog-composite/12.0', 'catalog-composite/13.0'):
            return {'format': FORMAT, 'baseline_manifest_sha256': baseline.original.manifest_digest,
                    'availability': 'available', 'reason': None}, _CatalogGroups(baseline)
        document = baseline.payload['b3']
        groups = {}
        for group in document['identities']:
            groups.setdefault(group['security_id'], []).append(group)
        return {'format': FORMAT, 'baseline_manifest_sha256': document['baseline_manifest_sha256'], 'availability': 'available', 'reason': None}, groups
    count = index.get('counts', {}).get('row_count') if isinstance(index, dict) else None
    info = {'format': FORMAT, 'baseline_manifest_sha256': baseline.manifest_digest}
    if type(count) is not int or count < 0 or count > MAX_AUTOMATIC_ROWS:
        return dict(info, availability='unavailable', reason='automatic derivation exceeds safe row limit or row count is unknown'), None
    key = (baseline.root, baseline.manifest_digest)
    with _lock:
        if key not in _cache:
            def bounded():
                for number, item in enumerate(canonical_rows(baseline), 1):
                    if number > MAX_AUTOMATIC_ROWS:
                        raise ValueError('automatic continuity row limit exceeded')
                    yield item
            try:
                result = build_continuity(bounded(), baseline.manifest_digest)
            except (ValueError, OSError) as exc:
                return dict(info, availability='error', reason=str(exc)), None
            groups = {}
            for group in result['identities']:
                groups.setdefault(group['security_id'], []).append(group)
            _cache.clear()
            _cache[key] = groups
        return dict(info, availability='available', reason=None), _cache[key]


class _CatalogGroups:
    """Lazily load unaffected baseline identities from the pinned catalog."""
    def __init__(self, baseline):
        self.baseline = baseline

    def get(self, identity, default=None):
        overrides = self.baseline.payload['b3_overrides']
        if identity in overrides:
            return overrides[identity]
        from .continuity_catalog import _metadata, open_catalog, observations_for_identity
        db = None
        try:
            db, meta = open_catalog(self.baseline.original, self.baseline.state)
            db.execute('BEGIN')
            if meta != self.baseline.payload['catalog_binding'] or _metadata(db) != meta:
                raise ValueError('continuity catalog changed since publication')
            if self.baseline.payload.get('format') == 'catalog-composite/13.0':
                from .identity_proof_tree import IdentityProofTree
                from .continuity_catalog import _pin_indexed_identity_manifest
                proofs = IdentityProofTree(self.baseline.payload['identity_proof_tree'], meta, path=self.baseline.registry_path)
                pinned = _pin_indexed_identity_manifest(db, meta, proofs)
                rows = list(observations_for_identity(db, identity, 'b2', pinned_groups=pinned))
            else:
                rows = list(observations_for_identity(db, identity, 'b2'))
            rows.extend((source, row) for source, row in self.baseline.payload['b2_delta'].get(identity, []))
            document = build_continuity(rows, self.baseline.original.manifest_digest,
                                        catalog_override=self.baseline.payload['symbol_catalog'])
            return document['identities'] or default
        except (ValueError, OSError, sqlite3.Error) as exc:
            from .query import QueryError
            raise QueryError('composite-unavailable', 'continuity catalog read failed: %s' % exc) from exc
        finally:
            if db is not None:
                db.close()


def group_summary(document, security_id, series=None):
    if document is None:
        return []
    return [{'security_id': group['security_id'], 'series': group['series'],
             'status': group['status'], 'ambiguities': group['ambiguities'],
             'intervals': [{key: interval[key] for key in ('symbol', 'observed_from', 'observed_to')}
                           for interval in group['intervals']],
             'transitions': group['transitions']}
            for group in document.get(security_id, [])
            if series is None or group['series'] == series]
