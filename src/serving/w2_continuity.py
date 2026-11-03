"""Versioned W2 trading-symbol association derivation over canonical evidence.

This additive contract does not alter D05/1.0, the W2 runner, or a qualified
package. It generates observed ranges, never exchange-effective validity dates.
Run ``python -m serving.w2_continuity --package PATH [--m2]`` to emit JSON to
stdout. The caller chooses where to store it; this module writes no files.
"""
from __future__ import annotations

import argparse
import json
import sys

from nse_engine.contract import OVERLAY_SERIES_OBSERVED
from .baseline import BaselineError, DEFAULT_M2_SPEC, open_baseline
from .symbols import _identity, observed_trading_symbol, resolve_symbol

FORMAT = 'w2-trading-symbol-associations/1.0'


class ContinuityError(ValueError):
    """Malformed or duplicate evidence; no partial result is returned."""


def build_continuity(rows, manifest_sha256, catalog_override=None):
    """Derive deterministic associations from (canonical source path, row) pairs.

    Identity is the B2 valid-ISIN/date correlation, not exchange-authoritative
    security identity. Invalid, unkeyed, overlay, and unsupported records are
    returned explicitly as unresolved evidence. Ambiguous groups have observed
    ranges but no continuity transitions.
    """
    groups, catalog, unresolved, seen = {}, {}, [], set()
    for source_file, row in rows:
        if not isinstance(source_file, str) or not source_file or not isinstance(row, dict):
            raise ContinuityError('source must be a non-empty path and row an object')
        values, provenance = row.get('source_values'), row.get('provenance')
        line = row.get('source_line_number')
        if not isinstance(values, dict) or not isinstance(provenance, dict) or type(line) is not int or line < 1:
            raise ContinuityError('canonical row lacks source values, provenance or source line')
        location = (source_file, line)
        if location in seen:
            raise ContinuityError('duplicate source location %s:%s' % location)
        seen.add(location)
        ticker = observed_trading_symbol(row)
        identity, series = _identity(row), values.get('series')
        evidence = {'source_file': source_file, 'source_line_number': line,
                    'business_date': row.get('business_date'),
                    'published_listing_symbol': values.get('listing_symbol'),
                    'raw_isin': values.get('security_isin'),
                    'observed_symbol': ticker['observed_symbol'],
                    'symbol_source': ticker['source_column'],
                    'provenance': provenance}
        if series in OVERLAY_SERIES_OBSERVED:
            unresolved.append(dict(evidence, reason='overlay-excluded'))
            continue
        if not isinstance(series, str) or not series:
            unresolved.append(dict(evidence, reason='missing-series'))
            continue
        if identity is None:
            unresolved.append(dict(evidence, reason='invalid-missing-isin-or-date'))
            continue
        if ticker['observed_symbol'] is None:
            unresolved.append(dict(evidence, reason='ticker-unavailable'))
            continue
        symbol, date = ticker['observed_symbol'], row['business_date']
        groups.setdefault((identity, series), []).append(evidence)
        key = (symbol, series, identity, values.get('listing_symbol'))
        bounds = catalog.setdefault(key, [date, date])
        bounds[0], bounds[1] = min(bounds[0], date), max(bounds[1], date)

    # Same observed-bounds and reuse logic as serving B2.
    symbol_catalog = catalog_override if catalog_override is not None else {'observations': tuple((k[0], k[1], k[2], k[3], v[0], v[1]) for k, v in catalog.items())}
    identities = []
    for (identity, series), evidence in sorted(groups.items()):
        evidence.sort(key=lambda e: (e['business_date'], e['source_file'], e['source_line_number']))
        reasons = set()
        for symbol in sorted({e['observed_symbol'] for e in evidence}):
            try:
                resolve_symbol(symbol_catalog, symbol, series)
            except ValueError as exc:
                reasons.add(str(exc))
        intervals = []
        for item in evidence:
            symbol = item['observed_symbol']
            if not intervals or intervals[-1]['symbol'] != symbol:
                intervals.append({'symbol': symbol, 'observed_from': item['business_date'],
                                  'observed_to': item['business_date'], 'evidence': []})
            interval = intervals[-1]
            interval['observed_to'] = item['business_date']
            interval['evidence'].append(item)
        transitions = []
        if not reasons:
            for previous, following in zip(intervals, intervals[1:]):
                transitions.append({'from_symbol': previous['symbol'], 'to_symbol': following['symbol'],
                                    'from_last_observed': previous['observed_to'],
                                    'to_first_observed': following['observed_from'],
                                    'basis': 'observed-transition-not-validity'})
        identities.append({'security_id': identity, 'series': series,
                           'status': 'ambiguous' if reasons else 'observed',
                           'ambiguities': sorted(reasons), 'intervals': intervals,
                           'transitions': transitions})
    unresolved.sort(key=lambda e: (e['source_file'], e['source_line_number']))
    return {'format': FORMAT, 'baseline_manifest_sha256': manifest_sha256,
            'interval_basis': 'observed-range-not-validity',
            'identities': identities, 'unresolved': unresolved}


def canonical_rows(baseline):
    """Read qualified canonical rows, never raw archives or output state."""
    for relative in baseline.row_files():
        with open(baseline.path(relative), encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    try:
                        yield relative, json.loads(line)
                    except ValueError as exc:
                        raise ContinuityError('invalid JSON in %s: %s' % (relative, exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--package', required=True)
    parser.add_argument('--m2', action='store_true')
    args = parser.parse_args(argv)
    try:
        baseline = open_baseline(args.package, spec=DEFAULT_M2_SPEC if args.m2 else None)
        result = build_continuity(canonical_rows(baseline), baseline.manifest_digest)
        json.dump(result, sys.stdout, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        sys.stdout.write('\n')
        return 0
    except (BaselineError, ValueError, OSError) as exc:
        print('continuity: %s' % exc, file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
