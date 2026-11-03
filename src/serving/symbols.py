"""Read-only ticker observations and conservative ISIN correlation.

This does not change canonical identity or assert exchange-validity intervals.
In D05/1.0 the UDiFF
listing_symbol is FinInstrmId; TckrSymb is carried as underlying_symbol.
Only cash equity rows are projected here: TckrSymb for derivatives can denote
an underlying and must not be represented as the instrument's trading symbol.
"""

import datetime
import json


def observed_trading_symbol(row):
    values = row.get("source_values") or {}
    family = row.get("format_family")
    symbol = None
    source = None
    if family == "legacy13":
        symbol, source = values.get("listing_symbol"), "SYMBOL"
    elif family == "udiff34" and values.get("segment") == "CM" and values.get("instrument_type") == "STK":
        symbol, source = values.get("underlying_symbol"), "TckrSymb"
    if not isinstance(symbol, str) or not symbol.strip():
        symbol = None
    return {
        "observed_symbol": symbol,
        "effective_symbol": symbol,
        "source_column": source if symbol is not None else None,
        "status": "observed" if symbol is not None else "unavailable",
        "basis": "row-source-value",
    }


def _identity(row):
    """Valid ISIN correlation only; invalid/blank values never create links."""
    if row.get("isin_validity") != "VALID":
        return None
    date = row.get("business_date")
    try:
        if not isinstance(date, str) or datetime.date.fromisoformat(date).isoformat() != date:
            return None
    except (ValueError, TypeError):
        return None
    value = row.get("isin_normalized")
    return value if isinstance(value, str) and value else None


def build_symbol_catalog(baseline, index):
    """Derive dated observations without altering the package or index format.

    Dates are observations, not asserted validity intervals. The catalog stores
    compact per-symbol observed bounds, not canonical records or archive content.
    """
    observations = {}
    for relative in index.get('files', {}):
        with (baseline.open_text(relative) if hasattr(baseline, 'open_text') else open(baseline.path(relative), encoding='utf-8')) as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                values = row.get('source_values') or {}
                series, raw = values.get('series'), values.get('listing_symbol')
                ticker = observed_trading_symbol(row)['observed_symbol']
                identity, date = _identity(row), row.get('business_date')
                if identity is None:
                    date = None
                if not ticker or not isinstance(series, str):
                    continue
                key = (ticker, series, identity, raw)
                span = observations.setdefault(key, [None, None])
                if isinstance(date, str) and date:
                    span[0] = date if span[0] is None else min(span[0], date)
                    span[1] = date if span[1] is None else max(span[1], date)
    return {'observations': tuple((k[0], k[1], k[2], k[3], v[0], v[1]) for k, v in observations.items())}


def resolve_symbol(catalog, symbol, series):
    """Resolve only valid-ISIN correlations; reject reuse and conflicting spans.

    Ranges are observed bounds, not claimed validity. Overlaps are treated
    conservatively as ambiguous, including the boundary day.
    """
    matches = catalog.ticker_observations(symbol, series) if hasattr(catalog, 'ticker_observations') else [o for o in catalog['observations'] if o[0] == symbol and o[1] == series]
    if not matches:
        return {'kind': 'raw', 'identity': None, 'symbol': symbol, 'series': series}
    identities = {o[2] for o in matches if o[2]}
    if len(identities) > 1:
        raise ValueError('ticker %r series %r has multiple valid ISINs: %s' % (symbol, series, sorted(identities)))
    identity = next(iter(identities)) if identities else None
    if identity:
        observations = catalog.identity_observations(identity, series) if hasattr(catalog, 'identity_observations') else catalog['observations']
        spans = [(o[0], o[4], o[5]) for o in observations
                 if o[2] == identity and o[1] == series and o[4] and o[5]]
        for i, (ticker, start, end) in enumerate(spans):
            for other, other_start, other_end in spans[i+1:]:
                if ticker != other and start <= other_end and other_start <= end:
                    raise ValueError('ISIN %s series %s has overlapping observed ticker ranges (%s, %s)' % (identity, series, ticker, other))
    return {'kind': 'ticker', 'identity': identity, 'symbol': symbol, 'series': series}


def row_matches(row, selection):
    values = row.get('source_values') or {}
    if values.get('series') != selection['series']:
        return False
    if selection['kind'] == 'raw':
        return values.get('listing_symbol') == selection['symbol']
    ticker = observed_trading_symbol(row)['observed_symbol']
    # Unknown/invalid ISINs remain exact individual observations, not linked.
    return ticker == selection['symbol'] or bool(ticker and selection['identity'] and _identity(row) == selection['identity'])


def resolution_metadata(row, selection):
    correlated = bool(selection['identity'] and _identity(row) == selection['identity'])
    return {"selector": selection['symbol'],
            "correlation_identity": selection['identity'] if correlated else None,
            "basis": "valid-isin-correlation" if correlated else "exact-observation"}
