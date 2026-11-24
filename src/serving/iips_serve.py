"""D40 EC-DEC-01..04 — ``iips-equicore-historical/v1`` headless local loopback serving API.

Phase B of the IIPS–EquiCore integration (D40; owner authorization 2026-11-24).
A read-only, single-user, personal-use HTTP service over the qualified M2
baseline, exposed **only** on the local loopback:

* binds by default to ``127.0.0.1:8614`` (distinct from ``src/ui/serve.py:8613``);
  ``--bind 0.0.0.0`` and any non-loopback bind are refused at startup;
* every request requires ``Authorization: Bearer <token>`` (constant-time compare);
  a non-loopback ``Host`` header is refused with 403;
* no CORS headers are ever emitted; ``Cache-Control: no-store`` on all responses;
* every JSON response is canonical (sorted keys, compact separators, LF) and
  carries a ``responseDigest`` (SHA-256 of the canonical payload, verifiable by
  stripping the field and re-hashing); identical requests produce byte-identical
  bodies and digests — no wall clock, no host, no environment values anywhere;
* the class-(4) ``(isin_normalized, series, business_date)`` index is used
  **exclusively** for ISIN identity correlation (D40 Addendum C-1 §5.4-5);
  historical observation retrieval is **validity-agnostic** (§5.4-4) and serves
  INVALID_CHECKDIGIT / INVALID_LEN / BLANK rows verbatim with their flags;
* scope is locked to the I5-qualified M2 baseline (``i4-20261008-M2``),
  ``NSE_EQ``, ``1D``, ``RAW_UNADJUSTED`` (EC-DEC-03) — everything else is
  rejected fail-closed with the D40 codes (422 UNSUPPORTED_EXCHANGE /
  UNSUPPORTED_FREQUENCY / ADJUSTMENT_UNAVAILABLE).

Standard library only (``http.server.ThreadingHTTPServer``). No network egress,
no writes to the package, no processing invocation; class-(4) state files are
read at startup and never mutated.

Run:

    PYTHONPATH=src python3 -m serving.iips_serve --package /path/to/i4-20261008-M2 \
        --state /path/to/state --token "$IIPS_EQUICORE_TRANSPORT_TOKEN" [--bind 127.0.0.1] [--port 8614]
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from typing import Optional, Tuple

from .baseline import DEFAULT_M2_SPEC, Baseline, open_baseline
from .index import canonical_json, load_index
from .isin_index import load_isin_index
from .paths import validate_roots
from .query import QueryError, query_calendar
from .symbols import observed_trading_symbol

CONTRACT = "iips-equicore-historical/v1"
SERVICE_VERSION = "1.0.0"
DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 8614
LOOPBACK_BINDS = frozenset({"127.0.0.1", "localhost"})
MAX_BODY_BYTES = 65536
MAX_LIMIT = 10000
DEFAULT_LIMIT = 1000

SCOPE = {
    "dataset": "i4-20261008-M2",
    "exchange": "NSE_EQ",
    "frequency": "1D",
    "adjustmentMode": "RAW_UNADJUSTED",
}
PINNED_GENERATION = "PINNED_GENERATION_EOD_SNAPSHOT"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISIN_SYNTAX = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")
SERIES_RE = re.compile(r"^[A-Z0-9]{1,12}$")

QUEUE_INSTRUMENT_PRICE_KEYS = (
    "price_open",
    "price_high",
    "price_low",
    "price_close",
    "price_last",
    "price_prev_close",
    "traded_quantity",
    "traded_value",
    "trades_count",
)


# ---------------------------------------------------------------- responses
def canonical_digest(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def make_response(payload: dict) -> Tuple[bytes, str]:
    """Attach responseDigest; return (body_bytes, digest). Deterministic."""
    body_payload = dict(payload)
    body_payload["responseDigest"] = canonical_digest(payload)
    return canonical_json(body_payload).encode("utf-8"), body_payload["responseDigest"]


def error_payload(code: str, message: str) -> dict:
    return {"contract": CONTRACT, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------- rows
def _serve_row(obj: dict, relative: str, line_number: int) -> dict:
    values = obj.get("source_values") or {}
    source_values = {key: values.get(key) for key in QUEUE_INSTRUMENT_PRICE_KEYS}
    observed = observed_trading_symbol(obj)
    provenance = obj.get("provenance") or {}
    served = {
        "business_date": obj.get("business_date"),
        "format_family": obj.get("format_family"),
        "series": values.get("series"),
        "observed_symbol": observed["observed_symbol"],
        "security_isin": values.get("security_isin"),
        "isin_normalized": obj.get("isin_normalized"),
        "isin_validity": obj.get("isin_validity"),
        "flags": obj.get("flags") or [],
        "source_values": source_values,
        "provenance": {
            "source_archive": provenance.get("source_archive"),
            "member_name": provenance.get("member_name"),
            "format_family": provenance.get("format_family"),
            "spec_version": provenance.get("spec_version"),
            "run_id": provenance.get("run_id"),
            "tool_name": provenance.get("tool_name"),
            "tool_sha256": provenance.get("tool_sha256"),
            "member_sha256_lf_text": provenance.get("member_sha256_lf_text"),
        },
        "source_file": relative,
        "source_line_number": obj.get("source_line_number", line_number),
    }
    return served


def _iter_rows(baseline: Baseline):
    for relative in baseline.row_files():
        with open(baseline.path(relative), "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                obj = json.loads(line)
                yield relative, line_number, obj


def _completeness(baseline: Baseline, index: dict, date_from: str, date_to: str, matched: int) -> dict:
    try:
        days = query_calendar(baseline, index, date_from, date_to)
    except QueryError as exc:
        raise QueryError("calendar-inconsistent", str(exc))
    if days == ():
        return {
            "tradingDaysWithArchive": None,
            "returnedBarCount": matched,
            "securityAbsentOnTradingDaysCount": None,
            "unexplainedCalendarDates": None,
            "notRetrievedCalendarDates": None,
            "officialHolidayDates": None,
            "status": "calendar-unavailable",
        }
    trading_days = sum(1 for day in days if day["file_present"])
    unexplained = [d["trade_date"] for d in days if d["label_status"] == "unexplained-by-obtained-circulars"]
    not_retrieved = [d["trade_date"] for d in days if d["label_status"] == "not-retrieved"]
    official = [
        {"trade_date": d["trade_date"], "official_holiday_label": d["official_holiday_label"]}
        for d in days
        if d["label_status"] == "official-holiday"
    ]
    return {
        "tradingDaysWithArchive": trading_days,
        "returnedBarCount": matched,
        "securityAbsentOnTradingDaysCount": trading_days - matched,
        "unexplainedCalendarDates": unexplained,
        "notRetrievedCalendarDates": not_retrieved,
        "officialHolidayDates": official,
        "status": "exact",
    }


def collect_bars(
    baseline: Baseline,
    index: dict,
    *,
    isin: Optional[str],
    symbol: Optional[str],
    series: str,
    date_from: str,
    date_to: str,
    limit: int,
    offset: int,
) -> Tuple[list, dict]:
    rows = []
    for relative, line_number, obj in _iter_rows(baseline):
        values = obj.get("source_values") or {}
        if values.get("series") != series:
            continue
        business_date = obj.get("business_date") or ""
        if not (date_from <= business_date <= date_to):
            continue
        if isin is not None:
            if (obj.get("isin_normalized") or "") != isin:
                continue
        elif symbol is not None:
            observed = observed_trading_symbol(obj)["observed_symbol"]
            if observed != symbol:
                continue
        else:  # pragma: no cover - caller enforces selector presence
            raise AssertionError("selector missing")
        rows.append(_serve_row(obj, relative, line_number))
    rows.sort(key=lambda row: (row["business_date"], row["format_family"] or "", row["source_file"], row["source_line_number"] or 0))
    total = len(rows)
    completeness = _completeness(baseline, index, date_from, date_to, total)
    page = rows[offset : offset + limit]
    return page, {"total": total, "limit": limit, "offset": offset, "completeness": completeness}


# ---------------------------------------------------------------- associations
def assemble_associations(index_document: dict, norm_isin: str) -> dict:
    entries = index_document.get("entries", {})
    by_series = entries.get(norm_isin) or {}
    if not by_series:
        return {
            "contract": CONTRACT,
            "query": {"isin": norm_isin},
            "is_valid_isin_format": None,
            "ambiguity": "none",
            "series": [],
            "basis": "exact-observation-only",
            "note": "no indexed observation (index eligibility: isin_validity == 'VALID'); exact-observation retrieval unchanged",
        }

    series_blocks = []
    ambiguous = False
    for series in sorted(by_series):
        day_map = by_series[series]
        cells = []  # (date, symbols, count)
        for date, cell in day_map.items():
            symbols = list(cell.get("symbols") or [])
            cells.append((date, symbols, int(cell.get("count", 0))))
        cells.sort(key=lambda cell: cell[0])
        # Any same-date parallel states across distinct symbols are ambiguous.
        if any(len(symbols) > 1 for _date, symbols, _count in cells):
            ambiguous = True
        # One observed span per symbol: [first, last] across its dates. Series
        # key isolation: symbols never mix across EQ/BE/BL.
        spans_by_symbol = {}
        days_by_symbol = {}
        for date, symbols, _count in cells:
            for symbol in symbols:
                span = spans_by_symbol.get(symbol)
                if span is None:
                    spans_by_symbol[symbol] = [date, date]
                    days_by_symbol[symbol] = 1
                else:
                    if date < span[0]:
                        span[0] = date
                    if date > span[1]:
                        span[1] = date
                    days_by_symbol[symbol] += 1
        observed = []
        spans = []
        for symbol in sorted(spans_by_symbol, key=lambda s: (spans_by_symbol[s][0], s)):
            start, end = spans_by_symbol[symbol]
            observed.append(
                {
                    "symbol": symbol,
                    "series": series,
                    "observed_from": start,
                    "observed_to": end,
                    "observation_days": days_by_symbol[symbol],
                }
            )
            spans.append((symbol, start, end))
        # Overlapping spans of distinct symbols (e.g. alternating A/B/A usage)
        # are ambiguous — never silently resolved as a rename (D05 §3.3).
        for i, (_sym_a, start_a, end_a) in enumerate(spans):
            for _sym_b, start_b, end_b in spans[i + 1:]:
                if start_a <= end_b and start_b <= end_a:
                    ambiguous = True
        series_blocks.append(
            {
                "series": series,
                "observedSymbols": observed,
                "observations": len(cells),
                "indexed_rows": sum(cell[2] for cell in cells),
            }
        )
    return {
        "contract": CONTRACT,
        "query": {"isin": norm_isin},
        "is_valid_isin_format": True,
        "ambiguity": "ambiguous" if ambiguous else "none",
        "series": series_blocks,
        "basis": "isin_correlation_key_upper_trim",
    }


# ---------------------------------------------------------------- handler
class ServerState:
    def __init__(self, baseline: Baseline, package_root: str, state_dir: str, token: str):
        self.baseline = baseline
        self.package_root = package_root
        self.state_dir = state_dir
        self.token = token
        self.index_document, self.index_digest = load_index(state_dir, baseline)
        self.isin_document, self.isin_digest = load_isin_index(state_dir, package_root, baseline)


def _host_ok(host_header: Optional[str]) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    base = host.split(":", 1)[0].strip("[]")
    return base in LOOPBACK_BINDS


def _parse_iso(value, field: str):
    if not isinstance(value, str) or not ISO_DATE.match(value):
        raise ValueError("%s must be an ISO date YYYY-MM-DD" % field)
    import datetime

    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError("%s is not a real calendar date" % field)
    return value


def _validate_scope_fields(data: dict):
    exchange = data.get("exchange")
    if exchange != SCOPE["exchange"]:
        return ("UNSUPPORTED_EXCHANGE", "exchange %r is outside the initial serving scope (only NSE_EQ permitted)" % (exchange,))
    frequency = data.get("frequency")
    if frequency != SCOPE["frequency"]:
        return ("UNSUPPORTED_FREQUENCY", "frequency %r is outside the initial serving scope (only 1D permitted)" % (frequency,))
    mode = data.get("adjustmentMode")
    if mode != SCOPE["adjustmentMode"]:
        return ("ADJUSTMENT_UNAVAILABLE", "adjustmentMode %r is not available (only RAW_UNADJUSTED is served)" % (mode,))
    return None


def _validate_isin(value):
    if not isinstance(value, str):
        return None
    norm = value.strip().upper()
    if len(norm) == 12 and norm.startswith("IN") and ISIN_SYNTAX.match(norm):
        return norm
    return ""  # malformed syntax



def make_handler(state: ServerState):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # ---------- plumbing ----------
        def log_message(self, fmt, *args):  # noqa: D401 (stderr diagnostics only)
            sys.stderr.write("iips_serve %s\n" % (fmt % args))

        def _send_json(self, status: int, payload: dict, extra_headers=None):
            body, digest = make_response(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Response-Digest", digest)
            # Deliberately: no Access-Control-* header, ever (EC-DEC-01 / EC-AC-01).
            if extra_headers:
                for name, value in extra_headers.items():
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: int, code: str, message: str, extra_headers=None):
            self._send_json(status, error_payload(code, message), extra_headers)

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            expected = "Bearer " + state.token
            return hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8"))

        def _preflight(self) -> bool:
            if not _host_ok(self.headers.get("Host")):
                self._send_error(403, "HOST_FORBIDDEN", "Host must be a loopback address (127.0.0.1/localhost)")
                return False
            if not self._authorized():
                self._send_error(
                    401,
                    "UNAUTHORIZED",
                    "missing or invalid bearer token",
                    {"WWW-Authenticate": "Bearer realm=\"iips-equicore-historical\""},
                )
                return False
            return True

        def _read_json_body(self):
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                self._send_error(400, "CONTENT_LENGTH_REQUIRED", "POST requires Content-Length")
                return None
            try:
                length = int(length_header)
            except ValueError:
                self._send_error(400, "CONTENT_LENGTH_INVALID", "Content-Length must be an integer")
                return None
            if length < 0 or length > MAX_BODY_BYTES:
                self._send_error(413, "PAYLOAD_TOO_LARGE", "request body exceeds %d bytes" % MAX_BODY_BYTES)
                return None
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeError, ValueError):
                self._send_error(400, "BODY_NOT_JSON", "request body is not valid JSON")
                return None
            if not isinstance(data, dict):
                self._send_error(400, "BODY_NOT_OBJECT", "request body must be a JSON object")
                return None
            return data

        # ---------- routes ----------
        def do_GET(self):
            if not self._preflight():
                return
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/v1/health":
                self._health()
            elif path == "/v1/calendar":
                self._calendar()
            elif re.fullmatch(r"/v1/instruments/[^/]+/associations", path):
                isin = path.split("/")[3]
                self._associations(isin)
            else:
                self._send_error(404, "NOT_FOUND", "unknown route %s" % path)

        def do_POST(self):
            if not self._preflight():
                return
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path in ("/v1/historical/bars", "/v1/historical/eod-observation"):
                data = self._read_json_body()
                if data is not None:
                    self._historical(path, data)
            else:
                self._send_error(404, "NOT_FOUND", "unknown route %s" % path)

        def do_PUT(self):
            self._method_not_allowed("PUT")

        def do_DELETE(self):
            self._method_not_allowed("DELETE")

        def do_PATCH(self):
            self._method_not_allowed("PATCH")

        def do_OPTIONS(self):
            self._method_not_allowed("OPTIONS")

        def _method_not_allowed(self, method):
            if not self._preflight():
                return
            self._send_error(405, "METHOD_NOT_ALLOWED", "%s is not supported on this route" % method, {"Allow": "GET, POST"})

        # ---------- endpoints ----------
        def _health(self):
            spec = state.baseline.spec
            payload = {
                "contract": CONTRACT,
                "service": "iips-equicore-historical",
                "version": SERVICE_VERSION,
                "status": "ok",
                "scope": SCOPE,
                "package": {
                    "name": spec.package_name if spec else "unpinned",
                    "manifest_sha256": state.baseline.manifest_digest,
                    "run_id": state.baseline.marker.get("run_id"),
                    "archive_count": (state.baseline.run_record.get("corpus") or {}).get("archive_count"),
                },
                "state": {
                    "serving_index": state.index_digest,
                    "isin_index": state.isin_digest,
                },
                "auth": "bearer",
            }
            self._send_json(200, payload)

        def _historical(self, path: str, data: dict):
            # Presence/shape of required fields first (400), then scope (422).
            for field in ("exchange", "frequency", "adjustmentMode"):
                if not isinstance(data.get(field), str) or not data[field]:
                    self._send_error(400, "MISSING_FIELD", "%s is required and must be a non-empty string" % field)
                    return
            if not isinstance(data.get("series"), str) or not SERIES_RE.match(data["series"]):
                self._send_error(400, "INVALID_SERIES", "series must match ^[A-Z0-9]{1,12}$")
                return
            scope_error = _validate_scope_fields(data)
            if scope_error:
                code, message = scope_error
                self._send_error(422, code, message)
                return
            raw_isin = data.get("isin")
            raw_symbol = data.get("symbol")
            isin = None
            if raw_isin is not None:
                isin = _validate_isin(raw_isin)
                if isin == "":
                    self._send_error(400, "INVALID_ISIN", "isin must be a 12-character IN ISIN (IN[A-Z0-9]{9}[0-9])")
                    return
            if isin is None and raw_symbol is None:
                self._send_error(400, "SELECTOR_REQUIRED", "provide at least one instrument selector: isin and/or symbol")
                return
            if raw_symbol is not None and (not isinstance(raw_symbol, str) or not raw_symbol.strip()):
                self._send_error(400, "INVALID_SYMBOL", "symbol must be a non-empty string")
                return
            symbol = raw_symbol.strip() if isinstance(raw_symbol, str) else None
            try:
                date_from = _parse_iso(data.get("from"), "from")
                date_to = _parse_iso(data.get("to"), "to")
            except ValueError as exc:
                self._send_error(400, "INVALID_DATE", str(exc))
                return
            try:
                limit = int(data.get("limit", DEFAULT_LIMIT))
                offset = int(data.get("offset", 0))
            except (TypeError, ValueError):
                self._send_error(400, "INVALID_PAGINATION", "limit/offset must be integers")
                return
            if limit < 1 or limit > MAX_LIMIT:
                self._send_error(400, "INVALID_LIMIT", "limit must be within 1..%d" % MAX_LIMIT)
                return
            if offset < 0:
                self._send_error(400, "INVALID_OFFSET", "offset must be >= 0")
                return
            series = data["series"]
            try:
                page, meta = collect_bars(
                    state.baseline, state.index_document,
                    isin=isin, symbol=symbol, series=series,
                    date_from=date_from, date_to=date_to, limit=limit, offset=offset,
                )
            except QueryError:
                self._send_error(500, "FAIL_CLOSED", "calendar validation failed; nothing served (fail closed)")
                return
            payload = {
                "contract": CONTRACT,
                "query": {
                    "exchange": SCOPE["exchange"],
                    "frequency": SCOPE["frequency"],
                    "adjustmentMode": SCOPE["adjustmentMode"],
                    "isin": isin,
                    "symbol": symbol,
                    "series": series,
                    "from": date_from,
                    "to": date_to,
                    "limit": limit,
                    "offset": offset,
                },
                "scope": SCOPE,
                "total": meta["total"],
                "returnedBarCount": len(page),
                "complete": (offset + len(page)) >= meta["total"],
                "completeness": meta["completeness"],
                "rows": page,
            }
            if path == "/v1/historical/eod-observation":
                payload["pinnedGeneration"] = PINNED_GENERATION
                payload["bitemporalKnowledgeAsOf"] = False
            self._send_json(200, payload)

        def _calendar(self):
            from urllib.parse import urlparse, parse_qs

            params = parse_qs(urlparse(self.path).query)
            try:
                date_from = _parse_iso(params.get("from", [None])[0], "from") if "from" in params else None
                date_to = _parse_iso(params.get("to", [None])[0], "to") if "to" in params else None
            except ValueError as exc:
                self._send_error(400, "INVALID_DATE", str(exc))
                return
            if (date_from is None) != (date_to is None):
                self._send_error(400, "INVALID_RANGE", "from and to must be provided together")
                return
            try:
                days = query_calendar(state.baseline, state.index_document, date_from, date_to)
            except QueryError:
                self._send_error(500, "FAIL_CLOSED", "calendar validation failed; nothing served (fail closed)")
                return
            present = [d for d in days if d["file_present"]]
            unexplained = [d["trade_date"] for d in days if d["label_status"] == "unexplained-by-obtained-circulars"]
            not_retrieved = [d["trade_date"] for d in days if d["label_status"] == "not-retrieved"]
            official = [
                {
                    "trade_date": d["trade_date"],
                    "official_holiday_label": d["official_holiday_label"],
                    "label_circular": d["label_circular"],
                    "label_registry_id": d["label_registry_id"],
                }
                for d in days if d["label_status"] == "official-holiday"
            ]
            payload = {
                "contract": CONTRACT,
                "query": {"from": date_from, "to": date_to},
                "calendar_present": bool(days),
                "totals": {
                    "days": len(days),
                    "tradingDaysWithArchive": len(present),
                    "officialHolidays": len(official),
                    "unexplainedCalendarDates": len(unexplained),
                    "notRetrievedCalendarDates": len(not_retrieved),
                },
                "officialHolidays": official,
                "unexplainedCalendarDates": unexplained,
                "notRetrievedCalendarDates": not_retrieved,
                "days": list(days),
            }
            self._send_json(200, payload)

        def _associations(self, raw_isin: str):
            norm = _validate_isin(raw_isin)
            if norm == "":
                self._send_error(400, "INVALID_ISIN", "isin must be a 12-character IN ISIN (IN[A-Z0-9]{9}[0-9])")
                return
            assert norm is not None
            payload = assemble_associations(state.isin_document, norm)
            if payload["ambiguity"] == "ambiguous":
                self._send_error(409, "IDENTITY_AMBIGUOUS", "overlapping observed ranges across symbols for %s" % norm)
                return
            self._send_json(200, payload)

    return Handler


# ---------------------------------------------------------------- startup
def load_state(package: str, state_dir: str, token: str, spec=DEFAULT_M2_SPEC) -> ServerState:
    package_root = os.path.realpath(os.path.abspath(package))
    validate_roots(package=package_root, state=state_dir)
    baseline = open_baseline(package_root, spec=spec)
    return ServerState(baseline, package_root, state_dir, token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="D40 iips-equicore-historical/v1 — headless loopback serving API")
    parser.add_argument("--package", required=True, help="path to the qualified M2 package (read-only)")
    parser.add_argument("--state", required=True, help="state root with serving_index + ISIN index (outside the package)")
    parser.add_argument("--bind", default=DEFAULT_BIND, help="bind address (loopback only; 0.0.0.0 refused)")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="bind port (default 8614)")
    parser.add_argument("--token", default=os.environ.get("IIPS_EQUICORE_TRANSPORT_TOKEN"), help="bearer token (or IIPS_EQUICORE_TRANSPORT_TOKEN)")
    return parser


def main(argv: Optional[list] = None) -> int:
    from http.server import ThreadingHTTPServer

    args = build_parser().parse_args(argv)

    bind = (args.bind or "").strip().lower()
    if bind not in LOOPBACK_BINDS:
        print(
            "REFUSING TO START: --bind %r is not loopback. D40 EC-DEC-01/EC-AC-01 prohibit anything "
            "other than 127.0.0.1/localhost (--bind 0.0.0.0 is prohibited)." % args.bind,
            file=sys.stderr,
        )
        return 2
    if not args.token:
        print("REFUSING TO START: a bearer token is mandatory (--token or IIPS_EQUICORE_TRANSPORT_TOKEN).", file=sys.stderr)
        return 2
    try:
        state = load_state(args.package, args.state, args.token, DEFAULT_M2_SPEC)
    except Exception as exc:  # startup must fail closed with a clean line
        print("REFUSING TO START: %s" % exc, file=sys.stderr)
        return 2

    handler = make_handler(state)
    server = ThreadingHTTPServer((bind, args.port), handler)
    sys.stderr.write(
        "serving iips-equicore-historical/v1 on http://%s:%d (package %s, manifest %s…, pid %d)\n"
        % (bind, args.port, state.baseline.spec.package_name if state.baseline.spec else "unpinned",
           state.baseline.manifest_digest[:8], os.getpid())
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
