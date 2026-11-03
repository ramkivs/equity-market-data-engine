"""Bounded application access to the optional B3 continuity derivation."""
from threading import Lock

from .w2_continuity import FORMAT, build_continuity, canonical_rows

# The B3 generator retains per-row evidence in memory. Never try to build its
# potentially multi-gigabyte document implicitly for the real M2 corpus.
MAX_AUTOMATIC_ROWS = 20000
_cache = {}
_lock = Lock()


def get_continuity(baseline, index):
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
