"""Display-level derivations for the I4 first-release UI (presentation).

Every function here is a PURE function over values that authorized serving
operations (Q1–Q10) actually return. Constraints (D16-11; D23 §18(9)):

* no file access, no baseline access, no storage of any kind — inputs are
  the served documents alone;
* canonical values are never reinterpreted or mutated: a value that is not
  a valid number in its as-published text form is reported as such (and
  excluded from numeric aggregates with an explicit count) — never
  defaulted, never coerced by locale rules;
* deterministic: same inputs give byte-identical outputs (no clock, no
  randomness, no environment reads).

The documented definitions implemented here are the single source of truth
for the UI's derived presentation values (mirrored 1:1 by the static
frontend; see the TASK62 implementation record).
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

#: Strict as-published decimal/integer text form. No locale parsing, no
#: thousands separators, no currency symbols, no exponents — the corpus
#: publishes plain decimal text (D05 §3.1 "decimal as-published").
_NUMBER_RE = re.compile(r"^[+-]?(0|[1-9]\d*)(\.\d+)?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Q2 "Latest N years" quick-filter presets (data-relative: the window is
#: anchored on the MAX calendar year present in the served Q1 partition
#: listing — never on the wall clock).
LATEST_YEARS_PRESETS = (1, 3, 5, 10)


def is_iso_date(value: object) -> bool:
    """True iff ``value`` is a non-empty ISO business-date string (YYYY-MM-DD)."""
    return isinstance(value, str) and bool(_ISO_DATE_RE.match(value))


def to_number(value: object) -> Optional[float]:
    """Parse an as-published numeric text value to float, else None.

    None means "not a number in its as-published form" (absent, blank, or
    non-numeric text) — the caller must treat that as an explicit state,
    never as zero.
    """
    if not isinstance(value, str):
        return None
    if not _NUMBER_RE.match(value):
        return None
    return float(value)


def _sv(row: dict, field: str) -> Optional[str]:
    """The row's as-published value for canonical field ``field`` (None if absent)."""
    values = row.get("source_values")
    if not isinstance(values, dict):
        return None
    return values.get(field)


def _business_date(row: dict) -> Optional[str]:
    date = row.get("business_date")
    return date if is_iso_date(date) else None


def period_summary(rows: Tuple[dict, ...]) -> dict:
    """The explorer's period/yearly summary over a served result set.

    Documented definition (deterministic; the rows are used in the EXACT
    order the serving operation returned them — never re-sorted):

    * ``records`` — the row count (the served result set, as returned);
    * ``date_min`` / ``date_max`` — the min/max as-published
      ``business_date`` over rows carrying a valid ISO business date
      (``None`` when no row does — never inferred);
    * ``single_year`` / ``year`` — True (and the year) when every present
      business date belongs to one calendar year; the UI labels the panel
      "yearly" only in that case, otherwise "period";
    * ``open_first`` — the first numeric ``price_open`` in served order
      (``None`` when absent); ``close_last`` — the last numeric
      ``price_close`` in served order;
    * ``high`` / ``low`` — the max/min numeric ``price_high`` /
      ``price_low`` (``None`` when none are numeric);
    * ``volume_total`` / ``turnover_total`` — the sum of the numeric
      ``traded_quantity`` / ``traded_value``; each carries its
      ``numeric_count`` so the UI can state how many of the rows
      contributed (non-numeric as-published values are never counted as
      zero);
    * every value is the as-published magnitude (no rescaling, no rounding
      beyond float parsing).
    """
    records = len(rows)
    dates = [d for d in (_business_date(row) for row in rows) if d is not None]
    date_min = min(dates) if dates else None
    date_max = max(dates) if dates else None
    years = {int(d[0:4]) for d in dates}
    single_year = len(years) == 1
    open_first = None
    close_last = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume_total: Optional[float] = None
    turnover_total: Optional[float] = None
    volume_count = 0
    turnover_count = 0
    for row in rows:
        value = to_number(_sv(row, "price_open"))
        if value is not None and open_first is None:
            open_first = value
        value = to_number(_sv(row, "price_close"))
        if value is not None:
            close_last = value
        value = to_number(_sv(row, "price_high"))
        if value is not None and (high is None or value > high):
            high = value
        value = to_number(_sv(row, "price_low"))
        if value is not None and (low is None or value < low):
            low = value
        value = to_number(_sv(row, "traded_quantity"))
        if value is not None:
            volume_total = (volume_total or 0.0) + value
            volume_count += 1
        value = to_number(_sv(row, "traded_value"))
        if value is not None:
            turnover_total = (turnover_total or 0.0) + value
            turnover_count += 1
    return {
        "records": records,
        "date_min": date_min,
        "date_max": date_max,
        "single_year": single_year,
        "year": years.pop() if single_year else None,
        "open_first": open_first,
        "close_last": close_last,
        "high": high,
        "low": low,
        "volume_total": volume_total,
        "volume_count": volume_count,
        "turnover_total": turnover_total,
        "turnover_count": turnover_count,
    }


def rows_by_year(partitions: list) -> list:
    """Rows-by-year chart data from the served Q1 partition listing.

    Documented definition: one point per calendar year present in the
    served ``partitions``; ``row_count`` = the sum of the partitions'
    served ``row_count`` values sharing that year (a display grouping of
    served counts — never a re-derivation). Years in ascending order.
    """
    by_year: dict = {}
    for partition in partitions:
        if not isinstance(partition, dict):
            continue
        year = partition.get("year")
        count = partition.get("row_count")
        if not (isinstance(year, str) and year.isdigit() and isinstance(count, int) and not isinstance(count, bool)):
            continue
        by_year[int(year)] = by_year.get(int(year), 0) + count
    return [{"year": year, "row_count": by_year[year]} for year in sorted(by_year)]


def segment_archive_counts(archives: list) -> list:
    """Archives-by-segment chart data from the served Q9 archive records.

    Documented definition: for each served archive whose ``d01`` fact block
    is present and whose as-published ``series_counts`` is a non-empty
    string->int mapping, the archive contributes to EVERY segment it
    contains (one archive per segment present), and the segment's row count
    accumulates the as-published ``series_counts`` magnitudes. Segments in
    ascending name order. Archives without a ``d01`` block contribute to
    nothing (the segment breakdown is then simply not available for them —
    never guessed).
    """
    by_segment: dict = {}
    for record in archives:
        if not isinstance(record, dict):
            continue
        d01 = record.get("d01")
        if not isinstance(d01, dict):
            continue
        counts = d01.get("series_counts")
        if not isinstance(counts, dict) or not counts:
            continue
        for segment, count in counts.items():
            if not isinstance(segment, str) or not (isinstance(count, int) and not isinstance(count, bool)):
                continue
            entry = by_segment.setdefault(segment, {"segment": segment, "archive_count": 0, "row_count": 0})
            entry["archive_count"] += 1
            entry["row_count"] += count
    return [by_segment[segment] for segment in sorted(by_segment)]


def coverage_summary(partitions: list, calendar_days: list, archives: list, q1_summary: dict) -> dict:
    """The dashboard Data-Coverage key/value list.

    Every value is a served magnitude or an explicit ``None`` (unavailable)
    — nothing is inferred:

    * ``start_date`` / ``end_date`` — the first/last ``trade_date`` of the
      served Q6 calendar records (the engine's ascending derivation order);
      ``None`` when the package carries no calendar (never inferred from
      partition years);
    * ``trading_days`` — the number of served Q6 calendar records, else None;
    * ``total_archives`` — the number of served Q9 archive records;
    * ``total_rows`` — the served Q1 ``summary.row_count``;
    * ``instruments`` — the served Q1 ``summary.instrument_pairs``;
    * ``exchange_segments`` — the sorted union of the as-published
      ``series_counts`` keys across the served Q9 ``d01`` fact blocks, else
      None.
    """
    dates = [day.get("trade_date") for day in calendar_days if isinstance(day, dict) and is_iso_date(day.get("trade_date"))]
    segments = set()
    for record in archives:
        if not isinstance(record, dict):
            continue
        d01 = record.get("d01")
        if isinstance(d01, dict) and isinstance(d01.get("series_counts"), dict):
            segments.update(key for key in d01["series_counts"] if isinstance(key, str))
    return {
        "start_date": min(dates) if dates else None,
        "end_date": max(dates) if dates else None,
        "trading_days": len(dates) if dates else None,
        "total_archives": len(archives),
        "total_rows": q1_summary.get("row_count") if isinstance(q1_summary, dict) else None,
        "instruments": q1_summary.get("instrument_pairs") if isinstance(q1_summary, dict) else None,
        "exchange_segments": sorted(segments) if segments else None,
        "partition_years": sorted({int(p["year"]) for p in partitions if isinstance(p, dict) and isinstance(p.get("year"), str) and p["year"].isdigit()}),
    }


def flag_status(flags: object) -> dict:
    """The row's display status from its served non-gating flag list.

    Empty/absent flags -> ``{"state": "clean", "text": "no flags"}``;
    otherwise the sorted, de-duplicated flag names (as published). Flag
    names are descriptive attributes — their presence is shown, never
    reinterpreted as a severity ranking.
    """
    if not isinstance(flags, list) or not flags:
        return {"state": "clean", "text": "no flags"}
    names = sorted({f.get("name") for f in flags if isinstance(f, dict) and isinstance(f.get("name"), str)})
    return {"state": "flagged", "text": ", ".join(names) if names else "unknown flags"}


def price_points(rows: Tuple[dict, ...], field: str) -> dict:
    """Chart points for one as-published price field over a served result set.

    Documented definition: one point per row carrying a valid ISO
    ``business_date`` AND a numeric as-published value for ``field``;
    points keep the served order (never re-sorted, never interpolated);
    rows that are excluded (no business date, or a non-numeric as-published
    value) are counted explicitly so the UI can state what was omitted —
    they are never plotted as zero or dropped silently.
    """
    points = []
    omitted = 0
    for row in rows:
        date = _business_date(row)
        value = to_number(_sv(row, field))
        if date is None or value is None:
            omitted += 1
            continue
        points.append({"date": date, "value": value})
    return {"points": points, "omitted": omitted, "field": field}


def latest_years_params(max_year: Optional[int], n: int) -> Optional[dict]:
    """The "Latest N years" quick-filter params, data-relative to the corpus.

    The window is anchored on the maximum calendar year present in the
    served Q1 partition listing (``max_year``): ``date_from`` = the first
    day of ``max_year - n + 1``, ``date_to`` = the last day of
    ``max_year`` (both inclusive ISO dates — Q2 semantics). Returns None
    when ``max_year`` is unknown (no served partitions) or ``n`` is not one
    of the supported presets — the UI must then mark the preset
    unavailable, never approximate it.
    """
    if n not in LATEST_YEARS_PRESETS or max_year is None or not (1000 <= max_year <= 9999):
        return None
    start = max_year - n + 1
    if start < 1000:
        return None
    return {"date_from": "%04d-01-01" % start, "date_to": "%04d-12-31" % max_year}


#: The deterministic quick-filter preset table. Each preset maps to an
#: exact (mode, params) pair over the authorized query surface — or None
#: (unavailable) when the governing contract defines no such query.
#: * "EQ (all)" — Q4 series EQ, including legacy rows without a segment.
#: * "CM segment" — exact UDiFF segment value, not a series code.
#: * "FO segment" — unavailable: no verified published value in this corpus.
#: * "Debt" / "Currency" — unavailable: no verified mapping.
#: * "Latest 1Y/3Y/5Y/10Y" — Q2 date range per :func:`latest_years_params`
#:   (data-relative; requires the served partition years at call time).
#: * "Reliable Only" — None: no reliability classification exists in the
#:   first-release serving contract; the preset is unavailable, never
#:   approximated.
QUICK_FILTERS = (
    "EQ (all)",
    "CM segment",
    "FO segment",
    "Debt",
    "Currency",
    "Latest 1Y",
    "Latest 3Y",
    "Latest 5Y",
    "Latest 10Y",
    "Reliable Only",
)


def quick_filter_params(name: str, max_year: Optional[int] = None) -> Optional[dict]:
    """Resolve a quick-filter preset to ``(mode, params)`` or None.

    None means the preset is unavailable under the governing contracts (the
    UI renders it as an explicit unavailable state — it is never silently
    approximated or invented).
    """
    if name == "EQ (all)":
        return {"mode": "Q4-filter", "params": {"filters": {"series": "EQ"}}}
    if name == "CM segment":
        return {"mode": "Q4-filter", "params": {"filters": {"segment": "CM"}}}
    if name in ("Latest 1Y", "Latest 3Y", "Latest 5Y", "Latest 10Y"):
        n = int(name[len("Latest "):-1])
        params = latest_years_params(max_year, n)
        if params is None:
            return None
        return {"mode": "Q2-date-range", "params": params}
    if name == "Reliable Only":
        return None
    return None
