"""D40 Phase B — iips-equicore-historical/v1 loopback serving API tests (A1–A10, EC-AC-01..05).

All package-dependent cases run against the synthetic fixture package
(tests/serving_fixtures.py) — never against, or represented as, the qualified
M2 baseline. The M2 pin (A1) is verified against the recorded constants of
:class:`serving.baseline.BaselineSpec`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tests import serving_fixtures
from serving.baseline import DEFAULT_M2_SPEC, open_baseline, BaselineError
from serving.index import build_index, write_index
from serving.isin_index import (
    ISIN_INDEX_FILENAME,
    ISIN_INDEX_DIGEST_FILENAME,
    build_isin_index,
    write_isin_index,
    load_isin_index,
    IsinIndexError,
)
from serving.iips_serve import (
    CONTRACT,
    PINNED_GENERATION,
    ServerState,
    assemble_associations,
    make_handler,
    main,
    canonical_digest,
)

TOKEN = "test-token-phase-b"
WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


class FixtureServer(unittest.TestCase):
    """Boots the real HTTP handler on an ephemeral loopback port per test."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="phaseb-iips-")
        self.pkg = os.path.join(self.root, "pkg")
        self.state = os.path.join(self.root, "state")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        index = build_index(self.handle)
        write_index(self.state, index)
        isin_index = build_isin_index(self.handle)
        write_isin_index(self.state, self.pkg, isin_index)
        self.server_state = ServerState(self.handle, self.pkg, self.state, TOKEN)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.server_state))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.root, ignore_errors=True)

    # ---------- HTTP helpers ----------
    def req(self, method, path, body=None, headers=None):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + TOKEN)
        if headers:
            for name, value in headers.items():
                req.add_header(name, value)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def req_no_auth(self, method, path):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", "Bearer wrong-token")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def bars(self, **overrides):
        body = {
            "exchange": "NSE_EQ",
            "frequency": "1D",
            "adjustmentMode": "RAW_UNADJUSTED",
            "series": "EQ",
            "from": "2016-01-04",
            "to": "2024-03-05",
        }
        body.update(overrides)
        return self.req("POST", "/v1/historical/bars", body)


class SecurityTests(FixtureServer):
    def test_health_requires_bearer(self):
        status, headers, body = self.req("GET", "/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["contract"], CONTRACT)

    def test_missing_or_bad_bearer_is_401(self):
        status, headers, body = self.req_no_auth("GET", "/v1/health")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"]["code"], "UNAUTHORIZED")
        self.assertIn("WWW-Authenticate", headers)

        status, headers, body = self.req("GET", "/v1/health", headers={"Authorization": "Bearer"})
        self.assertEqual(status, 401)

    def test_non_loopback_host_is_403_and_zero_cors(self):
        status, headers, body = self.req("GET", "/v1/health", headers={"Host": "192.0.2.5"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "HOST_FORBIDDEN")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_every_response_has_no_store_and_no_cors(self):
        for method, path, body in (
            ("GET", "/v1/health", None),
            ("POST", "/v1/historical/bars", {"exchange": "BSE_EQ", "frequency": "1D", "adjustmentMode": "RAW_UNADJUSTED", "series": "EQ", "from": "2016-01-04", "to": "2016-01-05", "symbol": "TCS"}),
        ):
            status, headers, raw = self.req(method, path, body)
            self.assertEqual(headers.get("Cache-Control"), "no-store")
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_bind_zero_is_refused_at_startup(self):
        code = main(["--package", self.pkg, "--state", self.state, "--token", TOKEN, "--bind", "0.0.0.0", "--port", "8619"])
        self.assertEqual(code, 2)

    def test_missing_token_is_refused(self):
        code = main(["--package", self.pkg, "--state", self.state, "--bind", "127.0.0.1", "--port", "8620"])
        self.assertEqual(code, 2)

    def test_unknown_route_404_and_method_405(self):
        status, _headers, body = self.req("GET", "/v1/nope")
        self.assertEqual(status, 404)
        status, headers, body = self.req("OPTIONS", "/v1/health")
        self.assertEqual(status, 405)

    def test_digest_matches_body(self):
        status, headers, body = self.req("GET", "/v1/health")
        payload = json.loads(body)
        digest = payload.pop("responseDigest")
        self.assertEqual(headers.get("X-Response-Digest"), digest)
        self.assertEqual(canonical_digest(payload), digest)


class ScopeTests(FixtureServer):
    def test_bse_eq_is_422(self):
        status, _h, body = self.bars(exchange="BSE_EQ", symbol="TCS")
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "UNSUPPORTED_EXCHANGE")

    def test_intraday_is_422(self):
        status, _h, body = self.bars(frequency="1m", symbol="TCS")
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "UNSUPPORTED_FREQUENCY")

    def test_adjusted_mode_is_422(self):
        status, _h, body = self.bars(adjustmentMode="ADJUSTED_CLOSE", symbol="TCS")
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "ADJUSTMENT_UNAVAILABLE")

    def test_missing_fields_are_400(self):
        status, _h, body = self.req("POST", "/v1/historical/bars", {"exchange": "NSE_EQ"})
        self.assertEqual(status, 400)


class ObservationRetrievalTests(FixtureServer):
    """A4: retrieval is validity-agnostic; INVALID_*/BLANK rows are preserved."""

    def _package_row_count(self, symbol=None, isin=None, series="EQ", date_from=None, date_to=None):
        count = 0
        for relative in self.handle.row_files():
            with open(self.handle.path(relative), "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    values = obj.get("source_values") or {}
                    if values.get("series") != series:
                        continue
                    day = obj.get("business_date") or ""
                    if date_from is not None and day < date_from:
                        continue
                    if date_to is not None and day > date_to:
                        continue
                    if isin is not None and (obj.get("isin_normalized") or "") != isin:
                        continue
                    if symbol is not None:
                        from serving.symbols import observed_trading_symbol

                        if observed_trading_symbol(obj)["observed_symbol"] != symbol:
                            continue
                    count += 1
        return count

    def test_invalid_checkdigit_and_len_rows_are_served_verbatim(self):
        status, _h, body = self.bars(symbol="TCS", series="EQ", **{"from": "2016-01-04", "to": "2016-01-05"})
        self.assertEqual(status, 200)
        payload = json.loads(body)
        rows = payload["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["isin_validity"] for r in rows], ["INVALID_CHECKDIGIT", "INVALID_LEN"])
        self.assertEqual([r["business_date"] for r in rows], ["2016-01-04", "2016-01-05"])
        # flags are carried verbatim — never hidden
        flag_names = [f["name"] for r in rows for f in r["flags"]]
        self.assertIn("isin_invalid_checkdigit", flag_names)
        self.assertIn("isin_invalid_length", flag_names)
        self.assertNotIn("raw_line", rows[0])
        # count parity against the package (A3)
        self.assertEqual(payload["total"], self._package_row_count(symbol="TCS", date_from="2016-01-04", date_to="2016-01-05"))

    def test_blank_isin_row_is_served(self):
        status, _h, body = self.bars(symbol="WIPRO", **{"from": "2016-01-04", "to": "2016-01-04"})
        self.assertEqual(status, 200)
        rows = json.loads(body)["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["isin_validity"], "BLANK")

    def test_retrieving_by_invalid_isin_still_returns_rows(self):
        status, _h, body = self.bars(**{"isin": "INE000000006", "from": "2016-01-04", "to": "2016-01-04", "series": "EQ"})
        self.assertEqual(status, 200)
        rows = json.loads(body)["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["isin_validity"], "INVALID_CHECKDIGIT")

    def test_count_parity_all_series_and_dates(self):
        status, _h, body = self.bars(symbol="RELIANCE", **{"from": "2016-01-01", "to": "2024-12-31"})
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["total"], self._package_row_count(symbol="RELIANCE", date_from="2016-01-01", date_to="2024-12-31"))
        self.assertEqual(payload["total"], 4)

    def test_missing_from_or_to_is_400(self):
        status, _h, body = self.req("POST", "/v1/historical/bars",
                                     {"exchange": "NSE_EQ", "frequency": "1D", "adjustmentMode": "RAW_UNADJUSTED", "series": "EQ", "symbol": "TCS"})
        self.assertEqual(status, 400)

    def test_invalid_isin_syntax_is_400(self):
        status, _h, body = self.bars(**{"isin": "INE123"})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "INVALID_ISIN")

    def test_eod_observation_stamps_and_reproducibility(self):
        body1 = {"exchange": "NSE_EQ", "frequency": "1D", "adjustmentMode": "RAW_UNADJUSTED", "series": "EQ",
                 "symbol": "RELIANCE", "from": "2016-01-04", "to": "2016-01-05"}
        status, _h, raw1 = self.req("POST", "/v1/historical/eod-observation", body1)
        self.assertEqual(status, 200)
        payload = json.loads(raw1)
        self.assertEqual(payload["pinnedGeneration"], PINNED_GENERATION)
        self.assertIs(payload["bitemporalKnowledgeAsOf"], False)
        # identical request → identical bytes (A8/EC-AC-05)
        status2, _h2, raw2 = self.req("POST", "/v1/historical/eod-observation", body1)
        self.assertEqual(raw1, raw2)

    def test_health_is_byte_reproducible(self):
        _s1, _h1, raw1 = self.req("GET", "/v1/health")
        _s2, _h2, raw2 = self.req("GET", "/v1/health")
        self.assertEqual(raw1, raw2)


class IndexDeterminismTests(FixtureServer):
    def test_valid_only_membership_and_counts(self):
        document, digest = load_isin_index(self.state, self.pkg, self.handle)
        # 6 of 9 fixture rows are VALID (3 RELIANCE legacy + INFY + RELIANCE udiff + TCS udiff)
        self.assertEqual(document["counts"]["rows_indexed"], 6)
        self.assertEqual(document["counts"]["rows_scanned"], 9)
        self.assertEqual(document["counts"]["isins"], 3)
        # BLANK / INVALID rows never indexed
        self.assertNotIn("INE000000006", document["entries"])   # TCS invalid checkdigit
        self.assertNotIn("INE123", document["entries"])          # TCS invalid length (stored normalized "INE123")
        for isin, series_map in document["entries"].items():
            for series, days in series_map.items():
                for date, cell in days.items():
                    self.assertGreaterEqual(cell["count"], 1)
                    self.assertEqual(cell["symbols"], sorted(cell["symbols"]))

    def test_two_builds_are_byte_identical(self):
        first = build_isin_index(self.handle)
        second = build_isin_index(self.handle)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )
        d1 = write_isin_index(os.path.join(self.root, "s1"), self.pkg, first)
        d2 = write_isin_index(os.path.join(self.root, "s2"), self.pkg, second)
        self.assertEqual(d1, d2)

    def test_delete_and_rebuild_reproduces_identical_digest(self):
        state = os.path.join(self.root, "rebuild-state")
        document = build_isin_index(self.handle)
        d1 = write_isin_index(state, self.pkg, document)
        for name in (ISIN_INDEX_FILENAME, ISIN_INDEX_DIGEST_FILENAME):
            os.remove(os.path.join(state, name))
        d2 = write_isin_index(state, self.pkg, build_isin_index(self.handle))
        self.assertEqual(d1, d2)

    def test_stale_index_is_refused(self):
        from tests.test_serving_query import make_variant_package

        state = os.path.join(self.root, "stale-state")
        variant = os.path.join(self.root, "variant-pkg")
        variant_spec = make_variant_package(self.pkg, variant, self.spec)
        variant_handle = open_baseline(variant, spec=variant_spec)
        write_isin_index(state, variant, build_isin_index(variant_handle))
        # digest sidecar matches (written together) but package identity differs
        with self.assertRaises(IsinIndexError):
            load_isin_index(state, self.pkg, self.handle)


class AssociationTests(FixtureServer):
    def test_reliance_associations_single_sequential_symbol(self):
        status, _h, body = self.req("GET", "/v1/instruments/INE002A01018/associations")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["is_valid_isin_format"])
        self.assertEqual(len(payload["series"]), 1)
        block = payload["series"][0]
        self.assertEqual(block["series"], "EQ")
        self.assertEqual([s["symbol"] for s in block["observedSymbols"]], ["RELIANCE"])
        self.assertEqual(block["observedSymbols"][0]["observed_from"], "2016-01-04")
        self.assertEqual(block["observedSymbols"][0]["observed_to"], "2024-03-05")

    def test_invalid_isin_returns_empty_correlation_not_error(self):
        status, _h, body = self.req("GET", "/v1/instruments/INE000000006/associations")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIsNone(payload["is_valid_isin_format"])
        self.assertEqual(payload["series"], [])
        self.assertEqual(payload["ambiguity"], "none")

    def test_malformed_isin_is_400(self):
        status, _h, body = self.req("GET", "/v1/instruments/INE123/associations")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "INVALID_ISIN")

    def test_series_isolation_unit(self):
        document = {
            "entries": {
                "INE000X01011": {
                    "EQ": {"2024-01-02": {"count": 1, "symbols": ["AAA"]}},
                    "BE": {"2024-01-03": {"count": 1, "symbols": ["BBB"]}},
                }
            }
        }
        payload = assemble_associations(document, "INE000X01011")
        self.assertEqual([b["series"] for b in payload["series"]], ["BE", "EQ"])
        self.assertEqual(payload["ambiguity"], "none")

    def test_sequential_rename_spans_unit(self):
        document = {
            "entries": {
                "INE000X01011": {
                    "EQ": {
                        "2024-01-02": {"count": 1, "symbols": ["AAA"]},
                        "2024-01-05": {"count": 1, "symbols": ["AAA"]},
                        "2024-01-08": {"count": 1, "symbols": ["BBB"]},
                        "2024-01-09": {"count": 1, "symbols": ["BBB"]},
                    }
                }
            }
        }
        payload = assemble_associations(document, "INE000X01011")
        symbols = payload["series"][0]["observedSymbols"]
        self.assertEqual([s["symbol"] for s in symbols], ["AAA", "BBB"])
        self.assertEqual([(s["observed_from"], s["observed_to"]) for s in symbols],
                         [("2024-01-02", "2024-01-05"), ("2024-01-08", "2024-01-09")])
        self.assertEqual(payload["ambiguity"], "none")

    def test_overlapping_span_is_ambiguous_unit(self):
        document = {
            "entries": {
                "INE000X01011": {
                    "EQ": {
                        "2024-01-02": {"count": 1, "symbols": ["AAA"]},
                        "2024-01-05": {"count": 1, "symbols": ["BBB"]},
                        "2024-01-09": {"count": 1, "symbols": ["AAA"]},
                    }
                }
            }
        }
        payload = assemble_associations(document, "INE000X01011")
        self.assertEqual(payload["ambiguity"], "ambiguous")

    def test_same_date_parallel_states_are_ambiguous_unit(self):
        document = {
            "entries": {
                "INE000X01011": {
                    "EQ": {"2024-01-02": {"count": 2, "symbols": ["AAA", "BBB"]}},
                }
            }
        }
        payload = assemble_associations(document, "INE000X01011")
        self.assertEqual(payload["ambiguity"], "ambiguous")


def _make_calendar_package(src_pkg: str, dst_pkg: str, spec):
    """Copy the fixture package and add a small, self-consistent W2 calendar.

    Span 2024-03-04..2024-03-08 (all weekdays): 2024-03-05 file-present
    (not-applicable), the other four days missing → unexplained per D16-10/D05
    §3.4 (UDiFF era label). Metrics are cross-check-consistent by construction.
    The package manifest and completion marker are regenerated so the copy
    verifies with a different identity; the returned spec pins the copy.
    """
    import datetime
    import hashlib
    import json as _json
    import shutil
    from dataclasses import replace

    def sha256_file(path):
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    shutil.copytree(src_pkg, dst_pkg)
    days = []
    for day in range(4, 9):
        date = "2024-03-%02d" % day
        wd = datetime.date(2024, 3, day).weekday()
        present = date == "2024-03-05"
        days.append(
            {
                "file_present": present,
                "formats_present": ["udiff34"] if present else [],
                "label_circular": None,
                "label_registry_id": None,
                "label_status": "not-applicable" if present else "unexplained-by-obtained-circulars",
                "member_names": ["fix-udf-2024-03-05.csv"] if present else [],
                "missing_weekday": not present,
                "notes": [],
                "official_holiday_label": None,
                "trad_dt_eq_biz_dt": True if present else None,
                "trade_date": date,
                "weekday": WEEKDAY[wd],
            }
        )
    w2_dir = os.path.join(dst_pkg, "w2")
    os.makedirs(w2_dir, exist_ok=True)
    with open(os.path.join(w2_dir, "calendar.jsonl"), "w", encoding="utf-8", newline="") as handle:
        for doc in days:
            handle.write(_json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
    present = sum(1 for d in days if d["file_present"])
    unexplained = [d["trade_date"] for d in days if d["label_status"] == "unexplained-by-obtained-circulars"]
    metrics = {
        "calendar_totals": {
            "days": len(days),
            "files": present,
            "first_date": days[0]["trade_date"],
            "last_date": days[-1]["trade_date"],
            "missing_weekdays": len(days) - present,
            "present_days": present,
            "span_weekdays": len(days),
            "unresolved_dates": unexplained,
        },
        "label_status_counts": {
            "not-applicable": present,
            "unexplained-by-obtained-circulars": len(unexplained),
        },
    }
    with open(os.path.join(w2_dir, "metrics.json"), "w", encoding="utf-8", newline="") as handle:
        handle.write(_json.dumps(metrics, sort_keys=True, separators=(",", ":")) + "\n")

    # regenerate the package manifest + completion marker over every retained file
    manifest_path = os.path.join(dst_pkg, "PACKAGE_MANIFEST.sha256")
    marker_path = os.path.join(dst_pkg, "RUN_COMPLETE.json")
    entries = []
    for dirpath, dirnames, filenames in os.walk(dst_pkg):
        dirnames.sort()
        for name in sorted(filenames):
            relative = os.path.relpath(os.path.join(dirpath, name), dst_pkg).replace(os.sep, "/")
            if relative in ("PACKAGE_MANIFEST.sha256", "RUN_COMPLETE.json"):
                continue
            entries.append("%s  %s" % (sha256_file(os.path.join(dirpath, name)), relative))
    manifest_text = "".join(line + "\n" for line in sorted(entries))
    with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(manifest_text)
    manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()

    with open(marker_path, "r", encoding="utf-8") as handle:
        marker = _json.load(handle)
    marker["package_manifest_sha256"] = manifest_digest
    with open(marker_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(_json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n")

    file_count = 0
    total_bytes = 0
    for dirpath, _dirnames, filenames in os.walk(dst_pkg):
        for name in filenames:
            total_bytes += os.path.getsize(os.path.join(dirpath, name))
            file_count += 1
    return replace(spec, manifest_sha256=manifest_digest, file_count=file_count, total_bytes=total_bytes)


class CalendarAccountingTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="phaseb-calendar-")
        self.pkg = os.path.join(self.root, "pkg")
        self.cal_pkg = os.path.join(self.root, "pkg-cal")
        self.state = os.path.join(self.root, "state")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        # build a calendar-carrying copy pinned to its own identity
        self.cal_spec = _make_calendar_package(self.pkg, self.cal_pkg, self.spec)
        self.handle = open_baseline(self.cal_pkg, spec=self.cal_spec, verify_files=True)
        index = build_index(self.handle)
        write_index(self.state, index)
        self.isin_index = build_isin_index(self.handle)
        write_isin_index(self.state, self.cal_pkg, self.isin_index)
        self.server_state = ServerState(self.handle, self.cal_pkg, self.state, TOKEN)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.server_state))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.root, ignore_errors=True)

    def req(self, method, path, body=None):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + TOKEN)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def test_completeness_equation_holds_with_calendar(self):
        status, _h, raw = self.req("POST", "/v1/historical/bars", {
            "exchange": "NSE_EQ", "frequency": "1D", "adjustmentMode": "RAW_UNADJUSTED",
            "series": "EQ", "symbol": "RELIANCE", "from": "2024-03-04", "to": "2024-03-08",
        })
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        completeness = payload["completeness"]
        self.assertEqual(completeness["status"], "exact")
        self.assertEqual(completeness["tradingDaysWithArchive"], 1)
        self.assertEqual(completeness["returnedBarCount"], 1)
        self.assertEqual(completeness["securityAbsentOnTradingDaysCount"], 0)
        self.assertEqual(
            completeness["tradingDaysWithArchive"],
            completeness["returnedBarCount"] + completeness["securityAbsentOnTradingDaysCount"],
        )
        self.assertEqual(completeness["unexplainedCalendarDates"], ["2024-03-04", "2024-03-06", "2024-03-07", "2024-03-08"])
        self.assertEqual(completeness["notRetrievedCalendarDates"], [])
        self.assertEqual(completeness["officialHolidayDates"], [])

    def test_absent_security_is_counted_not_hidden(self):
        status, _h, raw = self.req("POST", "/v1/historical/bars", {
            "exchange": "NSE_EQ", "frequency": "1D", "adjustmentMode": "RAW_UNADJUSTED",
            "series": "EQ", "symbol": "INFY", "from": "2024-03-04", "to": "2024-03-08",
        })
        self.assertEqual(status, 200)
        completeness = json.loads(raw)["completeness"]
        self.assertEqual(completeness["tradingDaysWithArchive"], 1)
        self.assertEqual(completeness["returnedBarCount"], 0)
        self.assertEqual(completeness["securityAbsentOnTradingDaysCount"], 1)

    def test_calendar_endpoint_lists_unexplained(self):
        status, _h, raw = self.req("GET", "/v1/calendar?from=2024-03-04&to=2024-03-08")
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertEqual(payload["unexplainedCalendarDates"], ["2024-03-04", "2024-03-06", "2024-03-07", "2024-03-08"])
        self.assertEqual(payload["notRetrievedCalendarDates"], [])
        self.assertTrue(payload["totals"]["tradingDaysWithArchive"] == 1)


class PinAndLayoutTests(unittest.TestCase):
    def test_m2_pin_constants_match_recorded_identity(self):
        self.assertEqual(DEFAULT_M2_SPEC.package_name, "i4-20261008-M2")
        self.assertEqual(DEFAULT_M2_SPEC.manifest_sha256,
                         "e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc")
        self.assertEqual(DEFAULT_M2_SPEC.file_count, 4948)
        self.assertEqual(DEFAULT_M2_SPEC.total_bytes, 21119807344)
        self.assertEqual(DEFAULT_M2_SPEC.engine_tool_sha256,
                         "d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9")
        self.assertEqual(DEFAULT_M2_SPEC.runner_sha256,
                         "f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a")

    def test_fixture_package_fails_m2_pin(self):
        root = tempfile.mkdtemp(prefix="phaseb-pin-")
        try:
            pkg = os.path.join(root, "pkg")
            serving_fixtures.build_fixture_package(pkg)
            with self.assertRaises(BaselineError):
                open_baseline(pkg, spec=DEFAULT_M2_SPEC)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

class RetentionAndQualityTests(FixtureServer):
    """A2/A3/A7: retention, package byte-identity at fixture level, Q8 census parity."""

    def test_serving_does_not_mutate_package_and_reopen_verifies(self):
        digest_before = self.facts["manifest_sha256"]
        for _ in range(3):
            status, _h, _body = self.bars(symbol="TCS", **{"from": "2016-01-04", "to": "2016-01-05"})
            self.assertEqual(status, 200)
        reopened = open_baseline(self.pkg, spec=self.spec)
        self.assertEqual(reopened.manifest_digest, digest_before)
        total = sum(1 for _, _l, _o in _iter_rows(reopened))
        self.assertEqual(total, self.facts["rows_total"])

    def test_per_partition_retention_count_parity(self):
        counts = {}
        for relative in self.handle.row_files():
            partition = "/".join(relative.split("/")[1:3])
            with open(self.handle.path(relative), "r", encoding="utf-8") as handle:
                counts[partition] = counts.get(partition, 0) + sum(1 for line in handle if line.strip())
        self.assertEqual(sum(counts.values()), self.facts["rows_total"])
        self.assertEqual(counts["legacy13/2016"], 5)
        self.assertEqual(counts["legacy13/2017"], 2)
        self.assertEqual(counts["udiff34/2024"], 2)
        # flags verbatim + validity mix preserved
        invalid_checkdigit = invalid_len = blank = valid = 0
        for _rel, _ln, obj in _iter_rows(self.handle):
            validity = obj.get("isin_validity")
            if validity == "INVALID_CHECKDIGIT":
                invalid_checkdigit += 1
            elif validity == "INVALID_LEN":
                invalid_len += 1
            elif validity == "BLANK":
                blank += 1
            elif validity == "VALID":
                valid += 1
        self.assertEqual((invalid_checkdigit, invalid_len, blank, valid), (1, 1, 1, 6))

    def test_served_payloads_never_carry_raw_line(self):
        status, _h, body = self.bars(symbol="TCS", **{"from": "2016-01-04", "to": "2016-01-05"})
        self.assertEqual(status, 200)
        for row in json.loads(body)["rows"]:
            self.assertNotIn("raw_line", row)
            self.assertIn("flags", row)
            self.assertIn("isin_validity", row)

    def test_q8_census_parity_and_index_non_interference(self):
        from serving.quality import _flag_census

        serving_index = build_index(self.handle)
        census = _flag_census(serving_index)
        self.assertEqual(census, {"isin_invalid_checkdigit": 1, "isin_invalid_length": 1})
        # class-(4) index construction is additive-only: the serving index bytes
        # are unchanged by building the ISIN index.
        build_isin_index(self.handle)
        self.assertEqual(_flag_census(build_index(self.handle)), census)

    def test_eq_be_bl_isolation_in_serving(self):
        for series in ("BE", "BL"):
            status, _h, body = self.bars(symbol="TCS", series=series, **{"from": "2016-01-04", "to": "2024-03-05"})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["total"], 0)


class HttpAmbiguityTests(FixtureServer):
    """EC-AC-02/A6 over HTTP: 409 is returned only across VALID-linked overlaps."""

    def test_overlapping_valid_links_yield_409(self):
        state = os.path.join(self.root, "ambiguity-state")
        document = build_isin_index(self.handle)
        cell = document["entries"]["INE002A01018"]["EQ"]["2024-03-05"]
        cell["symbols"] = ["RELIANCE", "RIL2"]
        cell["count"] = 2
        write_isin_index(state, self.pkg, document)
        from serving.isin_index import write_isin_index as _w, load_isin_index

        _doc, digest = load_isin_index(state, self.pkg, self.handle)
        ambiguous_state = ServerState.__new__(ServerState)
        ambiguous_state.baseline = self.handle
        ambiguous_state.package_root = self.pkg
        ambiguous_state.state_dir = state
        ambiguous_state.token = TOKEN
        ambiguous_state.index_document = self.server_state.index_document
        ambiguous_state.index_digest = self.server_state.index_digest
        ambiguous_state.isin_document = _doc
        ambiguous_state.isin_digest = digest
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ambiguous_state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/v1/instruments/INE002A01018/associations" % server.server_address[1]
            )
            req.add_header("Authorization", "Bearer " + TOKEN)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                    body = resp.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read()
            self.assertEqual(status, 409)
            self.assertEqual(json.loads(body)["error"]["code"], "IDENTITY_AMBIGUOUS")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _iter_rows(baseline):
    for relative in baseline.row_files():
        with open(baseline.path(relative), "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                yield relative, line_number, json.loads(line)

class TokenContractRegressionTests(unittest.TestCase):
    """D40 EC-DEC-01 / transport contract: the ONLY environment variable is
    IIPS_EQUICORE_TRANSPORT_TOKEN. The earlier IIPS_EQUI_CORE_TOKEN name is
    rejected as a configuration source (no silent dual-read)."""

    def _parse(self, argv, env):
        import os

        from serving.iips_serve import build_parser

        old = {key: os.environ.get(key) for key in ("IIPS_EQUICORE_TRANSPORT_TOKEN", "IIPS_EQUI_CORE_TOKEN")}
        try:
            for key in old:
                if key in env:
                    os.environ[key] = env[key]
                elif key in os.environ:
                    del os.environ[key]
            return build_parser().parse_args(argv)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transport_token_env_var_is_the_default(self):
        args = self._parse(["--package", "/p", "--state", "/s"], {"IIPS_EQUICORE_TRANSPORT_TOKEN": "contract-token"})
        self.assertEqual(args.token, "contract-token")

    def test_old_env_var_name_is_not_read(self):
        args = self._parse(["--package", "/p", "--state", "/s"], {"IIPS_EQUI_CORE_TOKEN": "legacy-token"})
        self.assertIsNone(args.token)

    def test_explicit_flag_still_wins(self):
        args = self._parse(["--package", "/p", "--state", "/s", "--token", "flag-token"],
                           {"IIPS_EQUICORE_TRANSPORT_TOKEN": "contract-token"})
        self.assertEqual(args.token, "flag-token")


class AuthEnforcementMatrixTests(FixtureServer):
    """Every route — known and unknown, GET/POST/PUT/PATCH/DELETE/OPTIONS —
    rejects a missing/invalid bearer token with 401 before any other work."""

    ROUTES = [
        ("GET", "/v1/health"),
        ("GET", "/v1/calendar"),
        ("GET", "/v1/instruments/INE002A01018/associations"),
        ("POST", "/v1/historical/bars"),
        ("POST", "/v1/historical/eod-observation"),
        ("GET", "/v1/nope"),
        ("POST", "/v1/nope"),
        ("PUT", "/v1/health"),
        ("PATCH", "/v1/health"),
        ("DELETE", "/v1/health"),
        ("OPTIONS", "/v1/health"),
    ]

    def test_every_route_requires_the_bearer_token(self):
        for method, path in self.ROUTES:
            with self.subTest(method=method, path=path):
                body = {"exchange": "NSE_EQ", "frequency": "1D", "adjustmentMode": "RAW_UNADJUSTED",
                        "series": "EQ", "from": "2016-01-04", "to": "2016-01-05", "symbol": "TCS"} if method == "POST" else None
                status, headers, raw = self._unauthenticated_request(method, path, body)
                self.assertEqual(status, 401, "%s %s returned %d, expected 401" % (method, path, status))
                self.assertNotIn("Access-Control-Allow-Origin", headers)

    def _unauthenticated_request(self, method, path, body):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer definitely-wrong")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def test_missing_bearer_header_is_401(self):
        url = "http://127.0.0.1:%d/v1/health" % self.port
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                headers = dict(resp.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            headers = dict(exc.headers.items())
        self.assertEqual(status, 401)
        self.assertIn("WWW-Authenticate", headers)

    def test_old_env_var_does_not_authenticate_against_default_token(self):
        # the service was constructed with TOKEN ("test-token-phase-b"); a header
        # carrying the retired env-var name's *value* semantics is irrelevant —
        # only the configured bearer token authorizes (constant-time compare).
        status, _headers, _body = self.req("GET", "/v1/health", headers={"Authorization": "Bearer IIPS_EQUI_CORE_TOKEN"})
        self.assertEqual(status, 401)

class FailClosedStartupTests(FixtureServer):
    """A1/A2 at the serving boundary: the service cannot be opened against a
    non-M2 identity, and serving never mutates the package bytes."""

    def test_load_state_refuses_non_m2_package(self):
        from serving.baseline import BaselineError, DEFAULT_M2_SPEC

        with self.assertRaises(BaselineError):
            from serving.iips_serve import load_state

            load_state(self.pkg, os.path.join(self.root, "state2"), TOKEN, DEFAULT_M2_SPEC)

    def test_full_package_byte_snapshot_unchanged_after_serving(self):
        def snapshot():
            sums = {}
            for dirpath, _dirnames, filenames in os.walk(self.pkg):
                for name in filenames:
                    path = os.path.join(dirpath, name)
                    with open(path, "rb") as handle:
                        sums[os.path.relpath(path, self.pkg).replace(os.sep, "/")] = hashlib.sha256(handle.read()).hexdigest()
            return sums

        before = snapshot()
        for _ in range(2):
            self.bars(symbol="TCS", **{"from": "2016-01-04", "to": "2016-01-05"})
            self.req("GET", "/v1/health")
            self.req("GET", "/v1/calendar")
            self.req("GET", "/v1/instruments/INE002A01018/associations")
        build_index(self.handle)
        build_isin_index(self.handle)
        after = snapshot()
        self.assertEqual(before, after)
