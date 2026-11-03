"""Serving query surface over an immutable qualified baseline.

Q3 and the optional Q4 symbol selector use observed trading symbols and
valid-ISIN correlations. Reuse and conflicting observed bounds fail closed.
Q5 keeps published association data intact and adds serving-side annotations.
Raw canonical source fields and provenance are never remapped.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from threading import Lock
from typing import Optional, Tuple

from .baseline import Baseline, BaselineError
from .index import ServingIndexError
from .symbols import observed_trading_symbol, build_symbol_catalog, resolve_symbol, row_matches, resolution_metadata
from .continuity_view import get_continuity, group_summary


def _open_source(baseline, relative):
    if hasattr(baseline, 'open_text'):
        return baseline.open_text(relative)
    return open(baseline.path(relative), 'r', encoding='utf-8')

QUERY_ID = "Q3-instrument"
DATASET_QUERY_ID = "Q1-dataset"
DATE_RANGE_QUERY_ID = "Q2-date-range"
FILTER_QUERY_ID = "Q4-filter"
ASSOCIATIONS_QUERY_ID = "Q5-association"
CALENDAR_QUERY_ID = "Q6-calendar"

#: Q5's single source: the class-(2) W2 derived output the runner writes from the
#: engine's identity stream (one SecurityIdentity document per line, in the engine's
#: sorted normalized-ISIN key order). Already a recognized durability-class pattern
#: in ``serving.baseline``; verified at open by verify-02/verify-03.
ASSOCIATIONS_FILE = "w2/associations.jsonl"

#: Q6's sources: the class-(2) W2 calendar (one CalendarDay document per line, in
#: ascending trade_date order — the engine's derivation order) and the runner's
#: metrics document (the calendar cross-check blocks). The runner always writes
#: both; the durability-class patterns are already recognized in
#: ``serving.baseline``; both are verified at open by verify-02/verify-03.
CALENDAR_FILE = "w2/calendar.jsonl"
METRICS_FILE = "w2/metrics.json"

# ---------------------------------------------------------------------------
# Pinned schema for Q5's source (D05 §3.2/§3.3; nse_engine.identity
# ``SecurityIdentity.to_dict()`` / ``DatedAssociation.to_dict()`` /
# ``Provenance.to_dict()``). Literals, with the contract citation: the serving
# layer does not import nse_engine (D24 boundary). Malformed present data
# fails closed against exactly these sets — a schema drift is a contract
# violation, never silently absorbed.
IDENTITY_DOC_KEYS = frozenset(
    (
        "associations",  # [DatedAssociation] — the dated-association intervals
        "first_observed",  # ISO business date (min over the identity's keyed observations)
        "identity_basis",  # "isin_correlation_key_upper_trim" (D05 §6.1 [ADOPTED])
        "is_valid_isin_format",  # true only when every observation is VALID; else null
        "isin_list",  # list of as-published ISIN strings (normally one)
        "last_observed",  # ISO business date (max)
        "non_promotion_note",  # D05 §3.2 NON-ASSUMPTION standing note
        "observations",  # governed census facts (str -> str)
        "provenance",  # [D05 §8 provenance block]
        "security_id",  # the D05 §6.1 correlation key (normalized ISIN; NOT identity)
    )
)
ASSOCIATION_ENTRY_KEYS = frozenset(
    (
        "association_type",  # present set: corpus-observed only (others DEC-1-deferred)
        "contributing_rows",  # [{business_date, line_number, member_name}]
        "interval_basis",  # "observed-range" (observed first/last presence, NOT validity)
        "observations",  # str -> str
        "observed_from",  # ISO business date
        "observed_to",  # ISO business date
        "provenance",  # [D05 §8 provenance block]
        "security_id",  # must equal the containing identity's security_id
        "series",
        "symbol",
    )
)
PROVENANCE_BLOCK_KEYS = frozenset(
    (
        "archive_sha256",
        "archive_sha256_basis",
        "evidence_refs",
        "format_family",
        "member_name",
        "member_sha256_lf_text",
        "member_sha256_raw_bytes",
        "run_id",
        "source_archive",
        "spec_version",
        "tool_name",
        "tool_sha256",
        "tool_version",
    )
)
CONTRIBUTING_ROW_KEYS = frozenset(("business_date", "line_number", "member_name"))
IDENTITY_KEY_BASIS = "isin_correlation_key_upper_trim"  # D05 §6.1 adopted basis
INTERVAL_BASIS_OBSERVED_RANGE = "observed-range"  # D05 §3.3
#: D05 §3.3: "Only the first exists today." master-snapshot / etf-register-membership
#: are DEC-1-deferred; a document carrying either is a contract violation here.
ASSOCIATION_TYPES_PRESENT = ("corpus-observed",)

# ---------------------------------------------------------------------------
# Pinned schema for Q6's source (D05 §3.4; nse_engine.calendar
# ``CalendarDay.to_dict()``). Literals, with the contract citation (serving
# does not import nse_engine, D24 boundary).
CALENDAR_DAY_KEYS = frozenset(
    (
        "file_present",  # bool — the trading-session signal (D05 §3.4)
        "formats_present",  # [format root] with a file on the date; [] for missing days
        "label_circular",  # str|null — sourcing circular; only for official-holiday
        "label_registry_id",  # str|null — circular-registry id; only for official-holiday
        "label_status",  # one of CALENDAR_LABEL_STATUSES
        "member_names",  # [member file name] on the date; [] for missing days
        "missing_weekday",  # bool — true iff the weekday has no file
        "notes",  # [governance annotation string] as published
        "official_holiday_label",  # str|null — null for unexplained / not-retrieved
        "trad_dt_eq_biz_dt",  # true (UDiff, corpus-proven) | null (legacy N/A / missing)
        "trade_date",  # ISO date; weekday-only (D03: zero weekend files)
        "weekday",  # weekday name, derived from the date
    )
)
#: D05 §3.4 label states — exactly four; the three first are missing-day states,
#: not-applicable is the present-day default (or a circular-holiday divergence).
CALENDAR_LABEL_OFFICIAL_HOLIDAY = "official-holiday"
CALENDAR_LABEL_UNEXPLAINED = "unexplained-by-obtained-circulars"
CALENDAR_LABEL_NOT_RETRIEVED = "not-retrieved"
CALENDAR_LABEL_NOT_APPLICABLE = "not-applicable"
CALENDAR_LABEL_STATUSES = (
    CALENDAR_LABEL_OFFICIAL_HOLIDAY,
    CALENDAR_LABEL_UNEXPLAINED,
    CALENDAR_LABEL_NOT_RETRIEVED,
    CALENDAR_LABEL_NOT_APPLICABLE,
)
#: D03: the corpus has zero weekend files; the calendar covers weekdays only.
CALENDAR_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
#: w2/metrics.json calendar blocks (runner-derived published facts; served as
#: published, cross-checked — never recomputed-and-replaced).
CALENDAR_TOTALS_KEYS = frozenset(
    (
        "days",
        "files",
        "first_date",
        "last_date",
        "missing_weekdays",
        "present_days",
        "span_weekdays",
        "unresolved_dates",
    )
)

#: Q4's filterable fields, pinned by the D05 §3.1 field table (as-published
#: values only; D05 NON-ASSUMPTION: descriptive attributes are never used for
#: inferred type semantics — exact stored-value equality only):
#: * ``series`` — present in both format families (D05 §3.1 "string, always");
#: * ``segment`` (``Sgmt``), ``source`` (``Src``), ``instrument_type``
#:   (``FinInstrmTp``) — UDiFF-only descriptive attributes; on legacy rows the
#:   values are absent (``None``) and can never match any requested value.
#: No other field is a Q4 filter: a requested name outside this tuple fails
#: closed (no undocumented aliases, no synonyms).
Q4_FILTER_FIELDS = ("series", "segment", "source", "instrument_type", "symbol")

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class QueryError(Exception):
    """Fail-closed query failure (bad input/contract violation; nothing served)."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


def _validate_iso_date(label: str, value: object) -> str:
    """Fail closed unless ``value`` is a valid ISO calendar date (YYYY-MM-DD)."""
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        raise QueryError("query-input", "%s must be an ISO date (YYYY-MM-DD), got %r" % (label, value))
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise QueryError("query-input", "%s is not a valid calendar date: %r" % (label, value))
    return value



_symbol_catalog_cache = {}
_symbol_catalog_lock = Lock()

def _symbol_catalog(baseline, index):
    if hasattr(baseline, 'payload') and baseline.payload.get('format') in ('catalog-composite/1.0', 'catalog-composite/2.0', 'catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0', 'catalog-composite/7.0', 'catalog-composite/8.0', 'catalog-composite/9.0'):
        return baseline.payload['symbol_catalog']
    key = (baseline.root, baseline.manifest_digest, tuple(sorted(index.get("files", {}))))
    with _symbol_catalog_lock:
        if key not in _symbol_catalog_cache:
            catalog = build_symbol_catalog(baseline, index)
            _symbol_catalog_cache.clear()
            _symbol_catalog_cache[key] = catalog
        return _symbol_catalog_cache[key]

def _resolve(catalog, symbol, series):
    try:
        return resolve_symbol(catalog, symbol, series)
    except ValueError as exc:
        raise QueryError("symbol-ambiguous", str(exc))


def query_instrument(
    baseline: Baseline,
    index: dict,
    symbol: str,
    series: str,
    year: Optional[int] = None,
) -> Tuple[dict, ...]:
    """Return observed ticker matches and unambiguous valid-ISIN correlations.

    A symbol not observed as a ticker remains an exact published listing_symbol
    selector for compatibility. Years restrict output, not ambiguity detection.
    """
    if not isinstance(symbol, str) or not isinstance(series, str):
        raise QueryError("query-input", "symbol and series must be strings")
    year_str: Optional[str] = None
    if year is not None:
        if not (isinstance(year, int) and not isinstance(year, bool) and 1000 <= year <= 9999):
            raise QueryError("query-input", "year must be a 4-digit integer")
        year_str = str(year)

    catalog = _symbol_catalog(baseline, index)
    selection = _resolve(catalog, symbol, series)
    pair = [symbol, series]
    candidates = []
    for relative, meta in index.get("files", {}).items():
        if selection["kind"] == "raw" and pair not in meta.get("instruments", []):
            continue
        if year_str is not None and meta.get("year") != year_str:
            continue
        candidates.append(relative)

    results = []
    for relative in sorted(candidates):
        meta = index["files"][relative]
        with _open_source(baseline, relative) as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise QueryError("query-scan", "unparseable canonical row in %s: %s" % (relative, exc))
                values = obj.get("source_values")
                if not isinstance(values, dict):
                    raise QueryError("query-scan", "canonical row without contract keys in %s" % relative)
                if not row_matches(obj, selection):
                    continue
                served = {key: value for key, value in obj.items() if key != "raw_line"}
                served["serving"] = {
                    "trading_symbol": observed_trading_symbol(obj),
                    "symbol_resolution": resolution_metadata(obj, selection),
                    "query": QUERY_ID,
                    "series": series,
                    "source_file": relative,
                    "source_file_family": meta.get("family"),
                    "source_file_year": meta.get("year"),
                    "symbol": symbol,
                }
                results.append(served)
    results.sort(
        key=lambda row: (
            row.get("business_date") or "",
            row.get("format_family") or "",
            row["serving"]["source_file_year"] or "",
            row["serving"]["source_file"],
            row.get("source_line_number") or 0,
        )
    )
    return tuple(results)


def query_date_range(
    baseline: Baseline,
    index: dict,
    date_from: str,
    date_to: str,
) -> Tuple[dict, ...]:
    """Q2 date-range query over canonical rows (D16-10 Q2).

    Both bounds are **inclusive** ISO business dates (YYYY-MM-DD) compared by
    exact as-published value — no normalisation, no expression language.
    Candidate files are narrowed with the per-file ``business_date`` bounds
    stored in the class-(4) index (serving-index/1.2); a file whose bounds are
    unknown (no dated row) or disjoint from the range cannot match and is
    skipped. Every row of a candidate file is then re-checked against its exact
    as-published ``business_date``: a row whose business_date is absent, blank,
    or not an ISO date can never match (it is never served by a date-range
    query, and never modified). ``date_from > date_to`` is an empty range and
    returns an empty result (not an error); malformed bounds fail closed with
    :class:`QueryError`.

    Results carry the canonical row exactly as stored (``source_values``
    as-published text, non-gating flags, the row's own D05 §8 provenance block)
    plus the Q2 serving envelope; ``raw_line`` is never served. Ordering is the
    established deterministic 5-tuple shared with Q3. Read-only: candidate files
    are streamed and nothing is written.
    """
    _validate_iso_date("date_from", date_from)
    _validate_iso_date("date_to", date_to)
    if date_from > date_to:
        return ()

    candidates = []
    for relative, meta in index.get("files", {}).items():
        lo = meta.get("business_date_min")
        hi = meta.get("business_date_max")
        if lo is None or hi is None:
            continue
        if hi < date_from or lo > date_to:
            continue
        candidates.append(relative)

    results = []
    for relative in sorted(candidates):
        meta = index["files"][relative]
        with _open_source(baseline, relative) as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise QueryError("query-scan", "unparseable canonical row in %s: %s" % (relative, exc))
                values = obj.get("source_values")
                if not isinstance(values, dict):
                    raise QueryError("query-scan", "canonical row without contract keys in %s" % relative)
                business_date = obj.get("business_date")
                if not isinstance(business_date, str) or not _ISO_DATE_RE.match(business_date):
                    continue
                if not (date_from <= business_date <= date_to):
                    continue
                served = {key: value for key, value in obj.items() if key != "raw_line"}
                served["serving"] = {
                    "trading_symbol": observed_trading_symbol(obj),
                    "query": DATE_RANGE_QUERY_ID,
                    "date_from": date_from,
                    "date_to": date_to,
                    "source_file": relative,
                    "source_file_family": meta.get("family"),
                    "source_file_year": meta.get("year"),
                }
                results.append(served)
    results.sort(
        key=lambda row: (
            row.get("business_date") or "",
            row.get("format_family") or "",
            row["serving"]["source_file_year"] or "",
            row["serving"]["source_file"],
            row.get("source_line_number") or 0,
        )
    )
    return tuple(results)


def query_filters(
    baseline: Baseline,
    index: dict,
    filters: dict,
) -> Tuple[dict, ...]:
    """Q4 exact field filters; optional symbol uses the Q3 resolver.

    Other field values remain exact and AND-composed; absent values never match.
    """
    if not isinstance(filters, dict):
        raise QueryError("query-input", "filters must be a mapping of Q4 field -> exact value")
    if not filters:
        raise QueryError("query-input", "Q4 requires at least one filter (an unfiltered scan is not a Q4 request)")
    for field in filters:
        if field not in Q4_FILTER_FIELDS:
            raise QueryError(
                "query-input",
                "unknown Q4 filter field %r (supported: %s)" % (field, ", ".join(Q4_FILTER_FIELDS)),
            )
    for field, value in filters.items():
        if not isinstance(value, str):
            raise QueryError("query-input", "Q4 filter value for %r must be a string (as-published value), got %r" % (field, value))

    symbol_selections = None
    if "symbol" in filters:
        catalog = _symbol_catalog(baseline, index)
        series_values = {filters["series"]} if "series" in filters else (
            (catalog.ticker_series(filters['symbol']) if hasattr(catalog, 'ticker_series') else {o[1] for o in catalog['observations'] if o[0] == filters['symbol']}) |
            {pair[1] for meta in index.get('files', {}).values() for pair in meta.get('instruments', []) if pair[0] == filters['symbol']})
        symbol_selections = {series: _resolve(catalog, filters['symbol'], series) for series in series_values}
    results = []
    for relative in sorted(index.get("files", {})):
        meta = index["files"][relative]
        with _open_source(baseline, relative) as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise QueryError("query-scan", "unparseable canonical row in %s: %s" % (relative, exc))
                values = obj.get("source_values")
                if not isinstance(values, dict):
                    raise QueryError("query-scan", "canonical row without contract keys in %s" % relative)
                if any(values.get(field) != value for field, value in filters.items() if field != "symbol"):
                    continue
                if symbol_selections is not None and (values.get("series") not in symbol_selections or not row_matches(obj, symbol_selections[values.get("series")])):
                    continue
                served = {key: value for key, value in obj.items() if key != "raw_line"}
                served["serving"] = {
                    "trading_symbol": observed_trading_symbol(obj),
                    "query": FILTER_QUERY_ID,
                    "filters": dict(filters),
                    "source_file": relative,
                    "source_file_family": meta.get("family"),
                    "source_file_year": meta.get("year"),
                }
                if symbol_selections is not None:
                    served["serving"]["symbol_resolution"] = resolution_metadata(obj, symbol_selections[values["series"]])
                results.append(served)
    results.sort(
        key=lambda row: (
            row.get("business_date") or "",
            row.get("format_family") or "",
            row["serving"]["source_file_year"] or "",
            row["serving"]["source_file"],
            row.get("source_line_number") or 0,
        )
    )
    return tuple(results)


def _require_iso_date_in_scan(value: object, context: str) -> None:
    """ISO business-date check under the associations-scan check id (a malformed
    present record is a scan failure, not a request-input failure)."""
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        raise QueryError("associations-scan", "field must be an ISO business date (YYYY-MM-DD), got %r in %s" % (value, context))
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise QueryError("associations-scan", "field is not a valid calendar date: %r in %s" % (value, context))


def _validate_provenance_block(block: object, context: str) -> None:
    if not isinstance(block, dict) or set(block) != PROVENANCE_BLOCK_KEYS:
        raise QueryError("associations-scan", "provenance block with a non-contract key set in %s" % context)
    for name in ("archive_sha256_basis", "format_family", "member_name", "source_archive", "spec_version", "tool_name", "tool_sha256", "tool_version"):
        if not isinstance(block.get(name), str):
            raise QueryError("associations-scan", "provenance block field %r must be a string in %s" % (name, context))
    if block.get("archive_sha256") is not None and not isinstance(block["archive_sha256"], str):
        raise QueryError("associations-scan", "provenance field archive_sha256 must be null or a string in %s" % context)
    if block.get("run_id") is not None and not isinstance(block["run_id"], str):
        raise QueryError("associations-scan", "provenance field run_id must be null or a string in %s" % context)
    refs = block.get("evidence_refs")
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise QueryError("associations-scan", "provenance field evidence_refs must be a list of strings in %s" % context)


def _validate_association_entry(entry: object, context: str, parent_key: str) -> None:
    if not isinstance(entry, dict) or set(entry) != ASSOCIATION_ENTRY_KEYS:
        raise QueryError("associations-scan", "dated-association entry with a non-contract key set in %s" % context)
    for name in ("association_type", "interval_basis", "series", "symbol"):
        if not isinstance(entry.get(name), str):
            raise QueryError("associations-scan", "dated-association field %r must be a string in %s" % (name, context))
    security_id = entry.get("security_id")
    if not isinstance(security_id, str) or not security_id:
        raise QueryError("associations-scan", "dated-association field security_id must be a non-empty string in %s" % context)
    if security_id != parent_key:
        raise QueryError(
            "associations-scan",
            "dated-association for identity %r belongs to a different identity %r in %s" % (security_id, parent_key, context),
        )
    if entry["association_type"] not in ASSOCIATION_TYPES_PRESENT:
        raise QueryError(
            "associations-scan",
            "dated-association carries association_type %r outside the present set %s in %s"
            % (entry["association_type"], "/".join(ASSOCIATION_TYPES_PRESENT), context),
        )
    if entry["interval_basis"] != INTERVAL_BASIS_OBSERVED_RANGE:
        raise QueryError(
            "associations-scan",
            "dated-association carries interval_basis %r (the contract pins %r) in %s"
            % (entry["interval_basis"], INTERVAL_BASIS_OBSERVED_RANGE, context),
        )
    for name in ("observed_from", "observed_to"):
        _require_iso_date_in_scan(entry.get(name), "%s.%s" % (context, name))
    rows = entry.get("contributing_rows")
    if not isinstance(rows, list):
        raise QueryError("associations-scan", "dated-association field contributing_rows must be a list in %s" % context)
    for row in rows:
        if not isinstance(row, dict) or set(row) != CONTRIBUTING_ROW_KEYS:
            raise QueryError("associations-scan", "contributing row with a non-contract key set in %s" % context)
        _require_iso_date_in_scan(row.get("business_date"), "%s.contributing_rows.business_date" % context)
        if not isinstance(row.get("line_number"), int) or isinstance(row["line_number"], bool):
            raise QueryError("associations-scan", "contributing row line_number must be an integer in %s" % context)
        if not isinstance(row.get("member_name"), str):
            raise QueryError("associations-scan", "contributing row member_name must be a string in %s" % context)
    observations = entry.get("observations")
    if not isinstance(observations, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in observations.items()
    ):
        raise QueryError("associations-scan", "dated-association observations must map strings to strings in %s" % context)
    provenance = entry.get("provenance")
    if not isinstance(provenance, list):
        raise QueryError("associations-scan", "dated-association field provenance must be a list in %s" % context)
    for block in provenance:
        _validate_provenance_block(block, context)


def _validate_identity_document(doc: object, context: str) -> str:
    if not isinstance(doc, dict) or set(doc) != IDENTITY_DOC_KEYS:
        raise QueryError("associations-scan", "identity document with a non-contract key set in %s" % context)
    security_id = doc.get("security_id")
    if not isinstance(security_id, str) or not security_id:
        raise QueryError("associations-scan", "identity document field security_id must be a non-empty string in %s" % context)
    if doc.get("identity_basis") != IDENTITY_KEY_BASIS:
        raise QueryError(
            "associations-scan",
            "identity document carries identity_basis %r (the contract pins %r) in %s"
            % (doc.get("identity_basis"), IDENTITY_KEY_BASIS, context),
        )
    if doc.get("is_valid_isin_format") not in (True, None):
        raise QueryError(
            "associations-scan",
            "identity document field is_valid_isin_format must be true or null (never asserted false) in %s" % context,
        )
    isin_list = doc.get("isin_list")
    if not isinstance(isin_list, list) or not isin_list or any(not isinstance(isin, str) for isin in isin_list):
        raise QueryError("associations-scan", "identity document field isin_list must be a non-empty list of strings in %s" % context)
    _require_iso_date_in_scan(doc.get("first_observed"), "%s.first_observed" % context)
    _require_iso_date_in_scan(doc.get("last_observed"), "%s.last_observed" % context)
    if not isinstance(doc.get("non_promotion_note"), str):
        raise QueryError("associations-scan", "identity document field non_promotion_note must be a string in %s" % context)
    observations = doc.get("observations")
    if not isinstance(observations, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in observations.items()
    ):
        raise QueryError("associations-scan", "identity document observations must map strings to strings in %s" % context)
    provenance = doc.get("provenance")
    if not isinstance(provenance, list):
        raise QueryError("associations-scan", "identity document field provenance must be a list in %s" % context)
    for block in provenance:
        _validate_provenance_block(block, context)
    associations = doc.get("associations")
    if not isinstance(associations, list):
        raise QueryError("associations-scan", "identity document field associations must be a list in %s" % context)
    for entry in associations:
        _validate_association_entry(entry, context, security_id)
    return security_id


def parse_associations(baseline: Baseline) -> Optional[list]:
    """Parse ``w2/associations.jsonl`` (class-(2) W2 output) or report it absent.

    Returns ``None`` when the file is **absent** — a legitimate package state
    (no derived identities; served as explicitly absent, never fabricated,
    never an error). Returns a list of ``(line_number, document)`` pairs, in
    file order, when the file is present. A **present** file that is malformed
    fails closed with ``QueryError("associations-scan")`` — including a
    non-object line, a non-contract key set, a non-ISO interval bound, an
    association_type outside the present set, an association belonging to a
    different identity, or a duplicate ``security_id`` (the engine emits
    exactly one document per active key, sorted; a repeat is corruption).
    Read-only: the file is streamed and nothing is written.
    """
    if hasattr(baseline, 'payload'):
        if baseline.payload.get('format') in ('catalog-composite/1.0', 'catalog-composite/2.0', 'catalog-composite/3.0', 'catalog-composite/4.0', 'catalog-composite/5.0', 'catalog-composite/6.0', 'catalog-composite/7.0', 'catalog-composite/8.0', 'catalog-composite/9.0'):
            return _catalog_associations(baseline)
        return list(enumerate(baseline.payload['w2'], start=1))
    path = baseline.path(ASSOCIATIONS_FILE)
    if not os.path.exists(path):
        return None
    documents = []
    seen = set()
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            context = "%s line %d" % (ASSOCIATIONS_FILE, line_number)
            try:
                doc = json.loads(line)
            except ValueError as exc:
                raise QueryError("associations-scan", "unparseable identity document in %s: %s" % (context, exc))
            security_id = _validate_identity_document(doc, context)
            if security_id in seen:
                raise QueryError(
                    "associations-scan",
                    "duplicate identity document for security_id %r in %s (the engine emits one document per key)" % (security_id, context),
                )
            seen.add(security_id)
            documents.append((line_number, doc))
    return documents


def _catalog_associations(baseline):
    """Stream original W2 documents with the pinned affected-ID overrides."""
    overrides = baseline.payload['w2_overrides']
    path = baseline.original.path(ASSOCIATIONS_FILE)
    def documents():
        seen = set()
        last_line = 0
        with open(path, encoding='utf8') as handle:
            for line_number, text in enumerate(handle, 1):
                if not text.strip():
                    continue
                try:
                    doc = json.loads(text)
                except ValueError as exc:
                    raise QueryError('associations-scan', 'unparseable original association') from exc
                identity = _validate_identity_document(doc, '%s line %d' % (ASSOCIATIONS_FILE, line_number))
                if identity in seen:
                    raise QueryError('associations-scan', 'duplicate original identity')
                seen.add(identity)
                last_line = line_number
                selected = overrides.get(identity, doc)
                if selected is not None:
                    if _validate_identity_document(selected, 'catalog generation override') != identity:
                        raise QueryError('associations-scan', 'override identity mismatch')
                    yield line_number, selected
        for identity in sorted(set(overrides) - seen):
            selected = overrides[identity]
            if selected is not None:
                if _validate_identity_document(selected, 'catalog generation override') != identity:
                    raise QueryError('associations-scan', 'override identity mismatch')
                last_line += 1
                yield last_line, selected
    return documents()


_UNPARSE = object()  # sentinel: documents not supplied by the caller


def query_associations(
    baseline: Baseline,
    index: dict,
    security_id: Optional[str] = None,
    symbol: Optional[str] = None,
    series: Optional[str] = None,
    documents: object = _UNPARSE,
) -> Tuple[dict, ...]:
    """Return published W2 identity or association records with serving annotations.

    A ticker selector uses the shared ISIN resolver, returning published
    intervals within the selected identity. Invalid-ISIN records may be
    returned only as separate exact observations. Observed bounds do not
    assert a symbol's validity between observation dates.
    """
    if security_id is not None and not isinstance(security_id, str):
        raise QueryError("query-input", "security_id must be a string (exact as-published correlation key)")
    for label, value in (("symbol", symbol), ("series", series)):
        if value is not None and not isinstance(value, str):
            raise QueryError("query-input", "%s must be a string (exact as-published value)" % label)
    if (symbol is None) != (series is None):
        raise QueryError(
            "query-input", "the Q5 instrument selector requires both symbol and series (an ordered pair; a single field is not a selector)"
        )
    if security_id is None and symbol is None:
        raise QueryError(
            "query-input",
            "Q5 requires at least one selector: security_id, or symbol and series",
        )

    if documents is _UNPARSE:
        documents = parse_associations(baseline)
    if documents is None:
        return ()

    _, continuity_doc = get_continuity(baseline, index)
    catalog = _symbol_catalog(baseline, index) if symbol is not None else None
    selection = _resolve(catalog, symbol, series) if catalog is not None else None
    results = []
    for line_number, doc in documents:
        if security_id is not None and doc["security_id"] != security_id:
            continue
        if symbol is not None:
            for entry in doc["associations"]:
                if entry["series"] != series:
                    continue
                if selection["kind"] == "raw":
                    if entry["symbol"] != symbol:
                        continue
                elif selection["identity"]:
                    if doc["security_id"] != selection["identity"] and not (entry["symbol"] == symbol and doc.get("is_valid_isin_format") is not True):
                        continue
                elif entry["symbol"] != symbol:
                    continue
                identity_observations = catalog.identity_observations(doc['security_id'], entry['series']) if hasattr(catalog, 'identity_observations') else catalog['observations']
                evidence = sorted({o[0] for o in identity_observations
                                   if o[2] == doc['security_id'] and o[1] == entry['series']
                                   and o[3] == entry['symbol'] and o[4] and o[5]
                                   and (entry['observed_from'] <= o[4] <= entry['observed_to'] or entry['observed_from'] <= o[5] <= entry['observed_to'])})
                served = dict(entry)
                served["serving"] = {
                    "query": ASSOCIATIONS_QUERY_ID,
                    "trading_symbol": {"observed_symbols": evidence, "status": "observed" if len(evidence) == 1 else ("ambiguous" if evidence else "unavailable"), "basis": "dated-source-observations-not-validity"},
                    "symbol_resolution": {"selector": symbol, "correlation_identity": selection["identity"] if selection["identity"] == doc["security_id"] else None, "basis": "valid-isin-correlation" if selection["identity"] and selection["identity"] == doc["security_id"] else "exact-observation"},
                    "security_id": doc["security_id"],
                    "series": series,
                    "source_file": ("composite/" + baseline.manifest_digest + "/w2/associations.jsonl") if hasattr(baseline, "payload") else ASSOCIATIONS_FILE,
                    "source_line_number": line_number,
                    "symbol": symbol,
                }
                served["serving"]["continuity"] = group_summary(continuity_doc, doc["security_id"], series)
                results.append(served)
        else:
            served = dict(doc)
            served["serving"] = {
                "query": ASSOCIATIONS_QUERY_ID,
                "security_id": security_id,
                "source_file": ("composite/" + baseline.manifest_digest + "/w2/associations.jsonl") if hasattr(baseline, "payload") else ASSOCIATIONS_FILE,
                "source_line_number": line_number,
            }
            served["serving"]["continuity"] = group_summary(continuity_doc, doc["security_id"])
            results.append(served)
    return tuple(results)


def _require_nonempty_str(value: object, context: str, field: str) -> None:
    # The engine emits null or a non-empty string in these fields; a blank string
    # is not a published value (D05 §2 rule 3: blank and absent are distinct — and
    # neither is ever produced blank here), so it is corruption.
    if not isinstance(value, str) or not value:
        raise QueryError(
            "calendar-scan", "%s must be null or a non-empty string, got %r in %s" % (field, value, context)
        )


def _validate_calendar_day(doc: object, context: str) -> None:
    if not isinstance(doc, dict) or set(doc) != CALENDAR_DAY_KEYS:
        raise QueryError("calendar-scan", "calendar day with a non-contract key set in %s" % context)
    _require_iso_date_in_scan(doc.get("trade_date"), "%s.trade_date" % context)
    date = datetime.date.fromisoformat(doc["trade_date"])
    if date.weekday() > 4:
        raise QueryError(
            "calendar-scan",
            "weekend date %r in %s (D03: the corpus has zero weekend files; the calendar covers weekdays only)"
            % (doc["trade_date"], context),
        )
    if doc.get("weekday") != CALENDAR_WEEKDAY_NAMES[date.weekday()]:
        raise QueryError(
            "calendar-scan",
            "weekday %r is inconsistent with the date %r in %s" % (doc.get("weekday"), doc["trade_date"], context),
        )
    file_present = doc.get("file_present")
    if not isinstance(file_present, bool):
        raise QueryError("calendar-scan", "file_present must be a boolean in %s" % context)
    missing_weekday = doc.get("missing_weekday")
    if not isinstance(missing_weekday, bool):
        raise QueryError("calendar-scan", "missing_weekday must be a boolean in %s" % context)
    if missing_weekday != (not file_present):
        raise QueryError(
            "calendar-scan",
            "missing_weekday %r contradicts file_present %r in %s" % (missing_weekday, file_present, context),
        )
    label_status = doc.get("label_status")
    if label_status not in CALENDAR_LABEL_STATUSES:
        raise QueryError(
            "calendar-scan",
            "label_status %r outside the governed states %s in %s"
            % (label_status, "/".join(CALENDAR_LABEL_STATUSES), context),
        )
    official_holiday_label = doc.get("official_holiday_label")
    label_circular = doc.get("label_circular")
    label_registry_id = doc.get("label_registry_id")
    if label_status == CALENDAR_LABEL_OFFICIAL_HOLIDAY:
        _require_nonempty_str(official_holiday_label, context, "official_holiday_label")
        for field, value in (("label_circular", label_circular), ("label_registry_id", label_registry_id)):
            if value is not None:
                _require_nonempty_str(value, context, field)
    else:
        if official_holiday_label is not None:
            raise QueryError(
                "calendar-scan",
                "label_status %r must carry official_holiday_label null (the cause is never filled in) in %s"
                % (label_status, context),
            )
        if label_circular is not None or label_registry_id is not None:
            raise QueryError(
                "calendar-scan",
                "label_circular/label_registry_id are populated only for %s in %s"
                % (CALENDAR_LABEL_OFFICIAL_HOLIDAY, context),
            )
    if label_status == CALENDAR_LABEL_NOT_APPLICABLE and not file_present:
        raise QueryError(
            "calendar-scan",
            "label_status %r occurs only on file-present days in %s" % (CALENDAR_LABEL_NOT_APPLICABLE, context),
        )
    for field in ("formats_present", "member_names", "notes"):
        values = doc.get(field)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
            raise QueryError("calendar-scan", "%s must be a list of non-empty strings in %s" % (field, context))
    if file_present:
        if not doc["formats_present"] or not doc["member_names"]:
            raise QueryError(
                "calendar-scan",
                "a file-present day must list its formats_present and member_names in %s" % context,
            )
    else:
        if doc["formats_present"] or doc["member_names"]:
            raise QueryError(
                "calendar-scan",
                "a missing weekday must carry empty formats_present and member_names in %s" % context,
            )
    trad_dt_eq_biz_dt = doc.get("trad_dt_eq_biz_dt")
    if trad_dt_eq_biz_dt not in (True, None):
        raise QueryError(
            "calendar-scan",
            "trad_dt_eq_biz_dt must be true (UDiff, corpus-proven) or null (never defaulted) in %s" % context,
        )
    if trad_dt_eq_biz_dt is True and not file_present:
        raise QueryError("calendar-scan", "trad_dt_eq_biz_dt true on a missing weekday in %s" % context)


def parse_calendar(baseline: Baseline) -> Optional[list]:
    """Parse ``w2/calendar.jsonl`` (class-(2) W2 output) or report it absent.

    Returns ``None`` when the file (and its runner-emitted pair
    ``w2/metrics.json``) is absent — a legitimate class-(2)-absent state
    (served as explicitly absent, never fabricated, never an error). Returns
    a list of ``(line_number, document)`` pairs in file order when present.
    A **present** file that is malformed fails closed with
    ``QueryError("calendar-scan")`` — including a non-object line, a
    non-contract key set, a weekend date, a weekday/date mismatch, a
    missing-weekday/file-present contradiction, a foreign label status, a
    label populated on an unexplained/not-retrieved day, blank label values,
    an empty file, or duplicate / non-ascending ``trade_date`` (the engine
    derives strictly ascending weekday spans). Read-only: the file is
    streamed and nothing is written.
    """
    path = baseline.path(CALENDAR_FILE)
    if not os.path.exists(path):
        if os.path.exists(baseline.path(METRICS_FILE)):
            raise QueryError(
                "calendar-metrics",
                "%s present without %s: the runner writes both (incomplete W2 output)" % (METRICS_FILE, CALENDAR_FILE),
            )
        return None
    documents = []
    previous_date = None
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            context = "%s line %d" % (CALENDAR_FILE, line_number)
            try:
                doc = json.loads(line)
            except ValueError as exc:
                raise QueryError("calendar-scan", "unparseable calendar day in %s: %s" % (context, exc))
            _validate_calendar_day(doc, context)
            trade_date = doc["trade_date"]
            if previous_date is not None and trade_date <= previous_date:
                raise QueryError(
                    "calendar-scan",
                    "trade_date %r is not strictly ascending after %r in %s (the engine derives a strictly "
                    "ascending weekday span; a duplicate or reorder is corruption)"
                    % (trade_date, previous_date, context),
                )
            previous_date = trade_date
            documents.append((line_number, doc))
    if not documents:
        raise QueryError(
            "calendar-scan",
            "an empty %s is not a state the engine can produce (a corpus has at least one file)" % CALENDAR_FILE,
        )
    return documents


def _load_calendar_metrics(baseline: Baseline) -> dict:
    """Load the Q6 cross-check blocks from ``w2/metrics.json`` (published,
    runner-derived facts). Fails closed with ``QueryError("calendar-metrics")``
    when the file is absent while the calendar is present (the runner writes
    both) or its calendar blocks are missing/non-contract."""
    path = baseline.path(METRICS_FILE)
    if not os.path.exists(path):
        raise QueryError(
            "calendar-metrics",
            "%s present without %s: the runner writes both (incomplete W2 output)" % (CALENDAR_FILE, METRICS_FILE),
        )
    with open(path, "r", encoding="utf-8") as handle:
        try:
            metrics = json.load(handle)
        except ValueError as exc:
            raise QueryError("calendar-metrics", "unparseable %s: %s" % (METRICS_FILE, exc))
    if not isinstance(metrics, dict):
        raise QueryError("calendar-metrics", "%s must be a JSON document" % METRICS_FILE)
    totals = metrics.get("calendar_totals")
    if not isinstance(totals, dict) or set(totals) != CALENDAR_TOTALS_KEYS:
        raise QueryError(
            "calendar-metrics", "%s without its governed calendar_totals block" % METRICS_FILE
        )
    label_status_counts = metrics.get("label_status_counts")
    if not isinstance(label_status_counts, dict) or any(
        not isinstance(status, str) or not isinstance(count, int) or isinstance(count, bool) or count < 0
        for status, count in label_status_counts.items()
    ):
        raise QueryError(
            "calendar-metrics", "%s without a governed label_status_counts block" % METRICS_FILE
        )
    return {"totals": totals, "label_status_counts": label_status_counts}


def _cross_check_calendar(documents: list, metrics: dict) -> None:
    """Validate the published calendar blocks against the served records.

    The published values are what the package declares (never recomputed and
    replaced); a material contradiction is a package inconsistency and fails
    closed (Q8 reconciliation cross-check precedent). Checks: the D03
    arithmetic (span weekdays = present + missing; files = present days, or
    greater where a day carries several members), the span bounds, the
    unresolved-date list, and the label-status census.
    """
    days = [doc for _line, doc in documents]
    totals = metrics["totals"]
    present = sum(1 for day in days if day["file_present"])
    missing = len(days) - present
    for field, expected in (
        ("days", len(days)),
        ("span_weekdays", len(days)),
        ("present_days", present),
        ("missing_weekdays", missing),
        ("first_date", days[0]["trade_date"]),
        ("last_date", days[-1]["trade_date"]),
    ):
        if totals.get(field) != expected:
            raise QueryError(
                "calendar-metrics",
                "published calendar_totals.%s %r contradicts the served calendar records (%r)"
                % (field, totals.get(field), expected),
            )
    unresolved = [day["trade_date"] for day in days if day["label_status"] == CALENDAR_LABEL_UNEXPLAINED]
    if totals.get("unresolved_dates") != unresolved:
        raise QueryError(
            "calendar-metrics",
            "published calendar_totals.unresolved_dates %r contradicts the served records (%r)"
            % (totals.get("unresolved_dates"), unresolved),
        )
    files = totals.get("files")
    if not isinstance(files, int) or isinstance(files, bool) or files < present:
        raise QueryError(
            "calendar-metrics",
            "published calendar_totals.files %r violates the D03 arithmetic (files >= present days %d)" % (files, present),
        )
    if files != present and not any(len(day["member_names"]) > 1 for day in days):
        raise QueryError(
            "calendar-metrics",
            "published calendar_totals.files %r exceeds the %d present days without a multi-member day"
            % (files, present),
        )
    counts = {}
    for day in days:
        counts[day["label_status"]] = counts.get(day["label_status"], 0) + 1
    if metrics["label_status_counts"] != counts:
        raise QueryError(
            "calendar-metrics",
            "published label_status_counts %r contradicts the served records (%r)"
            % (metrics["label_status_counts"], counts),
        )


def query_calendar(
    baseline: Baseline,
    index: dict,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    documents: object = _UNPARSE,
    metrics: object = _UNPARSE,
) -> Tuple[dict, ...]:
    """Q6 calendar query (D16-10 Q6: "trading days from file-presence;
    sourced holiday labels; the three unexplained dates shown as
    unexplained-by-obtained-circulars; legacy era not-retrieved").

    Read-only serving of ``w2/calendar.jsonl`` (the class-(2) W2 output;
    D05 §3.4), with the ``w2/metrics.json`` calendar blocks cross-checked
    against the served records:

    * **full** — no bounds: every calendar day as published, in file order
      (the engine's strictly ascending ``trade_date`` order — never
      re-sorted);
    * **range** — ``date_from`` and ``date_to`` (both, inclusive, ISO
      YYYY-MM-DD, exact as-published string comparison — Q2 semantics):
      the days with ``date_from <= trade_date <= date_to``; ``date_from >
      date_to`` is an empty range → empty result, not an error.

    Display semantics, per the governing contract (D05 §3.4; D16-10 Q6;
    D23 §8 item 1):

    * the four ``label_status`` states are served exactly as published and
      kept distinct: a sourced ``official-holiday`` carries its
      ``official_holiday_label`` / ``label_circular`` / ``label_registry_id``;
      ``unexplained-by-obtained-circulars`` and ``not-retrieved`` keep
      ``official_holiday_label: null`` — the cause is **never filled in**,
      never defaulted, never inferred from the status or the date;
    * ``trad_dt_eq_biz_dt: null`` (legacy N/A / missing) served as null,
      never defaulted to false;
    * ``notes`` served as published text, never reinterpreted;
    * the file-presence/circular divergence (a present day labelled
      official-holiday) is served as stored — the calendar stores the
      divergence, it does not reconcile it.

    Absence and failure (D16-08: serving never fabricates class-(2)
    content): both W2 calendar files absent → a legitimate empty result
    (served with ``calendar_present`` at the CLI level); a present
    malformed file or a metrics/records contradiction fails closed before
    anything is served (no partial output). ``index`` is accepted for
    boundary consistency (every Q path takes the verified class-(4) index)
    but supplies no Q6 file narrowing — the file set is fixed and the index
    format is unchanged. ``documents`` / ``metrics`` may carry results
    already returned by :func:`parse_calendar` (and the metrics loader) so
    the CLI serves the ``calendar_present`` marker from the same single
    pass. Read-only: the files are streamed and nothing is written.
    """
    if date_from is not None:
        _validate_iso_date("date_from", date_from)
    if date_to is not None:
        _validate_iso_date("date_to", date_to)
    if (date_from is None) != (date_to is None):
        raise QueryError(
            "query-input", "the Q6 calendar range requires both date_from and date_to (inclusive ISO business dates)"
        )
    if date_from is not None and date_from > date_to:
        return ()
    if documents is _UNPARSE:
        documents = parse_calendar(baseline)
    if documents is None:
        return ()
    if metrics is _UNPARSE:
        metrics = _load_calendar_metrics(baseline)
    _cross_check_calendar(documents, metrics)

    results = []
    for line_number, doc in documents:
        if date_from is not None and not (date_from <= doc["trade_date"] <= date_to):
            continue
        served = dict(doc)
        served["serving"] = {
            "query": CALENDAR_QUERY_ID,
            "date_from": date_from,
            "date_to": date_to,
            "source_file": CALENDAR_FILE,
            "source_line_number": line_number,
        }
        results.append(served)
    return tuple(results)


def partitions_listing(index: dict) -> dict:
    """Diagnostic partition table (raw class-(4) partition data; the product Q1
    query is :func:`query_dataset_summary`, which shapes this data per D16-10)."""
    return dict(index.get("partitions", {}))


def query_dataset_summary(
    index: dict,
    family: Optional[str] = None,
    year: Optional[int] = None,
) -> dict:
    """Q1 dataset/partition selection and yearly summaries (D16-10 Q1).

    Pure derivation over the class-(4) index (a D16-06 derived view): **no
    canonical row is scanned** — the function takes the index document alone
    and never receives a baseline handle.

    Selection: no argument selects all partitions; ``family`` (exact,
    as-published family name) and/or ``year`` (4-digit integer) narrow the
    selection. An unknown selection yields an **empty result** (no partitions,
    zeroed summary), never an error. A missing (``None``) or non-document
    index fails closed with :class:`QueryError`.

    Returns a document shaped for canonical-JSON serving:

    * ``partitions`` — the selected partitions sorted by (family, year), each
      with ``row_files``, ``row_count`` and ``instrument_pairs`` (the union of
      the per-file instrument sets, counted once per partition);
    * ``summary`` — totals over the selection, where ``instrument_pairs`` is
      the union over the selected files (a pair present in two partitions is
      counted once);
    * ``selection`` — the selection that was applied (for the served envelope
      of the result).
    """
    if not isinstance(index, dict):
        raise QueryError("query-input", "index must be the class-(4) index document (serving-index/1.2)")
    if family is not None and not isinstance(family, str):
        raise QueryError("query-input", "family must be a string")
    year_str: Optional[str] = None
    if year is not None:
        if not (isinstance(year, int) and not isinstance(year, bool) and 1000 <= year <= 9999):
            raise QueryError("query-input", "year must be a 4-digit integer")
        year_str = str(year)

    partitions: dict = {}
    for meta in index.get("files", {}).values():
        if family is not None and meta.get("family") != family:
            continue
        if year_str is not None and meta.get("year") != year_str:
            continue
        key = "%s/%s" % (meta.get("family"), meta.get("year"))
        partition = partitions.setdefault(
            key,
            {
                "family": meta.get("family"),
                "year": meta.get("year"),
                "row_files": 0,
                "row_count": 0,
                "instruments": set(),
            },
        )
        partition["row_files"] += 1
        partition["row_count"] += meta.get("row_count", 0)
        partition["instruments"].update(tuple(pair) for pair in meta.get("instruments", []))

    listed = [
        {
            "family": partition["family"],
            "year": partition["year"],
            "row_files": partition["row_files"],
            "row_count": partition["row_count"],
            "instrument_pairs": len(partition["instruments"]),
        }
        for key, partition in sorted(partitions.items())
    ]
    union = set()
    for partition in partitions.values():
        union.update(partition["instruments"])
    return {
        "query": DATASET_QUERY_ID,
        "selection": {"family": family, "year": int(year_str) if year_str is not None else None},
        "partitions": listed,
        "summary": {
            "row_files": sum(partition["row_files"] for partition in listed),
            "row_count": sum(partition["row_count"] for partition in listed),
            "instrument_pairs": len(union),
        },
    }
