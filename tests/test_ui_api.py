"""UI presentation layer — serving adapter (src/ui/api.py), in-process.

Runs the ``UiApi.dispatch`` surface against the synthetic fixture package
(tests/serving_fixtures.py) — never against, and never represented as, the
qualified M2 baseline. Covers:

* every authorized Q1–Q10 mode through the single query path, with EXACT
  envelope parity to the corresponding serving operation (no new query
  semantics — D23 §18(8));
* fail-closed request handling (invalid modes/params, unknown routes,
  wrong methods) with canonical error documents;
* D38 saved-query and D39 query-history dispatch, including C2(a):
  ordinary queries and saved runs never write history;
* determinism: identical requests produce byte-identical bodies;
* determinism: withheld operations (logs, export, raw content, processing)
  have no route at all.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from tests import serving_fixtures
from serving.archive import query_archive_inventory
from serving.baseline import open_baseline
from serving.detail import query_record_detail
from serving.index import build_index, canonical_json, write_index
from serving.qualification import query_qualification
from serving.quality import query_data_quality
from serving.query import (
    QueryError,
    parse_associations,
    parse_calendar,
    query_associations,
    query_calendar,
    query_date_range,
    query_dataset_summary,
    query_filters,
    query_instrument,
)
from ui.api import UiApi, encode


class UiApiBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d62-ui-api-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.handle = open_baseline(self.pkg, spec=self.facts["spec"])
        self.index = build_index(self.handle)
        self.state = os.path.join(self.root, "state")
        write_index(self.state, self.index)
        self.saved = os.path.join(self.root, "saved-state")
        self.history = os.path.join(self.root, "history-state")
        self.api = UiApi(self.handle, self.state, self.saved, self.history, m2=False, repo_root=None)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def dispatch(self, method, path, body=None):
        return self.api.dispatch(method, path, body)

    def query(self, mode, params):
        status, document = self.dispatch("POST", "/api/query", {"mode": mode, "params": params})
        return status, document


class StatusTests(UiApiBase):
    def test_status_document(self):
        status, document = self.dispatch("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(document["result"], "pass")
        self.assertEqual(document["service"], "i4-ui-serving-adapter/1.0")
        self.assertEqual(document["package_run_id"], serving_fixtures.FIXTURE_RUN_ID)
        self.assertFalse(document["m2"])
        self.assertIsNone(document["repo_root"])
        self.assertEqual(len(document["query_modes"]), 10)
        self.assertEqual(document['registry_binding']['status'], 'location-not-identified')
        self.assertEqual(document['registry_binding']['scope'], 'baseline-only')

    def test_status_method_only_get(self):
        status, _ = self.dispatch("POST", "/api/status")
        self.assertEqual(status, 405)


class QueryPathTests(UiApiBase):
    def test_q1_parity(self):
        status, document = self.query("Q1-dataset", {})
        self.assertEqual(status, 200)
        expected = query_dataset_summary(self.index)
        self.assertEqual(document["query"], expected)

    def test_q2_parity(self):
        status, document = self.query("Q2-date-range", {"date_from": "2016-01-01", "date_to": "2016-12-31"})
        self.assertEqual(status, 200)
        rows = query_date_range(self.handle, self.index, "2016-01-01", "2016-12-31")
        self.assertEqual(document["query"], {"query": "Q2-date-range", "date_from": "2016-01-01", "date_to": "2016-12-31", "result_count": len(rows), "rows": list(rows)})

    def test_q3_parity(self):
        status, document = self.query("Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        self.assertEqual(status, 200)
        rows = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        self.assertEqual(len(rows), 4)
        self.assertEqual(document["query"], {"query": "Q3-instrument", "result_count": len(rows), "rows": list(rows)})
        # raw_line is never served
        for row in document["query"]["rows"]:
            self.assertNotIn("raw_line", row)

    def test_q4_parity(self):
        status, document = self.query("Q4-filter", {"filters": {"series": "EQ"}})
        self.assertEqual(status, 200)
        rows = query_filters(self.handle, self.index, {"series": "EQ"})
        self.assertEqual(document["query"], {"query": "Q4-filter", "filters": {"series": "EQ"}, "result_count": len(rows), "rows": list(rows)})

    def test_q5_parity(self):
        status, document = self.query("Q5-association", {"symbol": "RELIANCE", "series": "EQ"})
        self.assertEqual(status, 200)
        documents = parse_associations(self.handle)
        rows = query_associations(self.handle, self.index, symbol="RELIANCE", series="EQ", documents=documents)
        self.assertEqual(
            document["query"],
            {
                "query": "Q5-association",
                "security_id": None,
                "series": "EQ",
                "symbol": "RELIANCE",
                "associations_present": documents is not None,
                "continuity": {"format": "w2-trading-symbol-associations/1.0", "baseline_manifest_sha256": self.handle.manifest_digest, "availability": "available", "reason": None},
                "record_count": len(rows),
                "records": list(rows),
            },
        )

    def test_q6_parity(self):
        status, document = self.query("Q6-calendar", {})
        self.assertEqual(status, 200)
        documents = parse_calendar(self.handle)
        rows = query_calendar(self.handle, self.index, documents=documents)
        self.assertEqual(
            document["query"],
            {
                "query": "Q6-calendar",
                "date_from": None,
                "date_to": None,
                "calendar_present": documents is not None,
                "record_count": len(rows),
                "records": list(rows),
            },
        )

    def test_q7_parity(self):
        row0 = query_instrument(self.handle, self.index, "RELIANCE", "EQ")[0]
        source_file = row0["serving"]["source_file"]
        line = row0["source_line_number"]
        status, document = self.query("Q7-record-detail", {"source_file": source_file, "source_line_number": line})
        self.assertEqual(status, 200)
        self.assertEqual(document["query"], query_record_detail(self.handle, self.index, source_file, line))
        self.assertNotIn("raw_line", document["query"]["row"])

    def test_q8_parity(self):
        status, document = self.query("Q8-data-quality", {})
        self.assertEqual(status, 200)
        self.assertEqual(document["query"], query_data_quality(self.handle, self.index))

    def test_q9_parity(self):
        status, document = self.query("Q9-archive-inventory", {})
        self.assertEqual(status, 200)
        self.assertEqual(document["query"], query_archive_inventory(self.handle, d01=None))

    def test_q10_parity(self):
        status, document = self.query("Q10-qualification", {})
        self.assertEqual(status, 200)
        self.assertEqual(document["query"], query_qualification(self.handle, repo_root=None))

    def test_q10_with_repo_param(self):
        status, document = self.query("Q10-qualification", {"repo": self.root})
        self.assertEqual(status, 200)
        self.assertEqual(document["query"], query_qualification(self.handle, repo_root=self.root))

    def test_unknown_mode(self):
        status, document = self.query("Q11-nonsense", {})
        self.assertEqual(status, 400)
        self.assertEqual(document["result"], "fail")
        self.assertEqual(document["check"], "saved-query-invalid")

    def test_q4_unknown_field_fail_closed(self):
        status, document = self.query("Q4-filter", {"filters": {"trading_status": "ACTIVE"}})
        self.assertEqual(status, 400)
        self.assertEqual(document["check"], "query-input")

    def test_q2_malformed_date_fail_closed(self):
        # the D38 definition contract validates dates at the boundary
        status, document = self.query("Q2-date-range", {"date_from": "01/01/2016", "date_to": "2016-12-31"})
        self.assertEqual(status, 400)
        self.assertEqual(document["result"], "fail")
        self.assertEqual(document["check"], "saved-query-invalid")

    def test_q3_missing_selector(self):
        status, document = self.query("Q3-instrument", {"symbol": "RELIANCE"})
        self.assertEqual(status, 400)
        self.assertEqual(document["check"], "saved-query-invalid")

    def test_non_object_params(self):
        status, document = self.dispatch("POST", "/api/query", {"mode": "Q1-dataset", "params": "nope"})
        self.assertEqual(status, 400)
        self.assertEqual(document["check"], "saved-query-invalid")

    def test_no_body(self):
        status, document = self.dispatch("POST", "/api/query")
        self.assertEqual(status, 400)

    def test_query_method_only_post(self):
        status, _ = self.dispatch("GET", "/api/query")
        self.assertEqual(status, 405)


class WhatedRouteTests(UiApiBase):
    """Withheld operations have no route at all (D16-12 scope; D23 §19)."""

    def test_withheld_routes_404(self):
        for path in ("/api/logs", "/api/export", "/api/raw", "/api/process", "/api/verify", "/fs/row", "/api/query/extra"):
            status, document = self.dispatch("GET", path)
            self.assertEqual(status, 404, path)
            self.assertEqual(document["check"], "route-not-found", path)

    def test_unknown_route(self):
        status, document = self.dispatch("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(document["check"], "route-not-found")


class SavedQueryTests(UiApiBase):
    def _create(self, query_id="tcs-2016", mode="Q3-instrument", params=None):
        return self.dispatch("POST", "/api/saved", {"id": query_id, "mode": mode, "params": params or {"symbol": "RELIANCE", "series": "EQ"}})

    def test_crud_lifecycle(self):
        status, document = self._create()
        self.assertEqual(status, 201)
        self.assertEqual(document["entry"]["id"], "tcs-2016")
        self.assertIn("store_sha256", document)

        status, document = self.dispatch("GET", "/api/saved")
        self.assertEqual(status, 200)
        self.assertEqual(document["count"], 1)

        status, document = self.dispatch("GET", "/api/saved/tcs-2016")
        self.assertEqual(status, 200)
        self.assertEqual(document["entry"]["mode"], "Q3-instrument")

        status, document = self.dispatch("PUT", "/api/saved/tcs-2016", {"mode": "Q2-date-range", "params": {"date_from": "2016-01-01", "date_to": "2016-12-31"}})
        self.assertEqual(status, 200)
        self.assertEqual(document["entry"]["mode"], "Q2-date-range")

        status, document = self.dispatch("DELETE", "/api/saved/tcs-2016")
        self.assertEqual(status, 200)
        status, document = self.dispatch("GET", "/api/saved")
        self.assertEqual(document["count"], 0)

    def test_duplicate_create_conflict(self):
        self._create()
        status, document = self._create()
        self.assertEqual(status, 409)
        self.assertEqual(document["check"], "saved-query-duplicate")

    def test_invalid_identifier(self):
        status, document = self.dispatch("POST", "/api/saved", {"id": "UPPER CASE!", "mode": "Q1-dataset", "params": {}})
        self.assertEqual(status, 400)
        self.assertEqual(document["check"], "saved-query-invalid")

    def test_not_found(self):
        status, document = self.dispatch("GET", "/api/saved/missing")
        self.assertEqual(status, 404)
        self.assertEqual(document["check"], "saved-query-not-found")

    def test_run_parity_and_no_history(self):
        self._create()
        self._create("range-2016", "Q2-date-range", {"date_from": "2016-01-01", "date_to": "2016-12-31"})
        status, document = self.dispatch("POST", "/api/saved/range-2016/run")
        self.assertEqual(status, 200)
        rows = query_date_range(self.handle, self.index, "2016-01-01", "2016-12-31")
        self.assertEqual(document["query"], {"query": "Q2-date-range", "date_from": "2016-01-01", "date_to": "2016-12-31", "result_count": len(rows), "rows": list(rows)})
        # C2(a): a saved run never writes history
        status, document = self.dispatch("GET", "/api/history")
        self.assertEqual(status, 200)
        self.assertEqual(document["count"], 0)

    def test_run_unknown(self):
        status, document = self.dispatch("POST", "/api/saved/nope/run")
        self.assertEqual(status, 404)
        self.assertEqual(document["check"], "saved-query-not-found")


class HistoryTests(UiApiBase):
    def test_record_success_and_error(self):
        # success
        status, document = self.dispatch("POST", "/api/history", {"mode": "Q3-instrument", "params": {"symbol": "RELIANCE", "series": "EQ"}})
        self.assertEqual(status, 201)
        self.assertEqual(document["result"], "recorded")
        self.assertEqual(document["outcome"], "success")
        self.assertEqual(document["entry"]["seq"], 1)
        self.assertIn("query", document)
        # error outcome is recorded too (the failure IS the actual outcome)
        status, document = self.dispatch("POST", "/api/history", {"mode": "Q4-filter", "params": {"filters": {"trading_status": "ACTIVE"}}})
        self.assertEqual(status, 201)
        self.assertEqual(document["outcome"], "error")
        self.assertEqual(document["entry"]["seq"], 2)
        self.assertEqual(document["entry"]["check"], "query-input")

        status, document = self.dispatch("GET", "/api/history")
        self.assertEqual(document["count"], 2)
        status, document = self.dispatch("GET", "/api/history/1")
        self.assertEqual(status, 200)
        self.assertEqual(document["entry"]["mode"], "Q3-instrument")
        status, document = self.dispatch("DELETE", "/api/history/2")
        self.assertEqual(status, 200)
        status, document = self.dispatch("GET", "/api/history")
        self.assertEqual(document["count"], 1)

    def test_seq_validation(self):
        status, document = self.dispatch("GET", "/api/history/abc")
        self.assertEqual(status, 400)
        self.assertEqual(document["check"], "history-invalid")
        status, document = self.dispatch("GET", "/api/history/99")
        self.assertEqual(status, 404)
        self.assertEqual(document["check"], "history-not-found")

    def test_ordinary_query_never_writes_history(self):
        for _ in range(3):
            self.query("Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        self.query("Q1-dataset", {})
        status, document = self.dispatch("GET", "/api/history")
        self.assertEqual(document["count"], 0)
        # and the store root was never created
        self.assertFalse(os.path.exists(self.history))

    def test_invalid_mode(self):
        status, document = self.dispatch("POST", "/api/history", {"mode": "Q99", "params": {}})
        self.assertEqual(status, 400)
        self.assertEqual(document["check"], "history-invalid")


class DeterminismTests(UiApiBase):
    def test_identical_requests_byte_identical(self):
        bodies = []
        for _ in range(2):
            status, document = self.query("Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
            self.assertEqual(status, 200)
            bodies.append(encode(document))
        self.assertEqual(bodies[0], bodies[1])
        # the body is canonical JSON
        self.assertEqual(bodies[0], canonical_json(document) + "\n")

    def test_error_documents_canonical(self):
        status, document = self.query("Q4-filter", {"filters": {"bogus": "x"}})
        self.assertEqual(status, 400)
        self.assertEqual(encode(document), canonical_json(document) + "\n")


if __name__ == "__main__":
    unittest.main()
