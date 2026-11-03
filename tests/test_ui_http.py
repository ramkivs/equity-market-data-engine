"""UI presentation layer — HTTP host (src/ui/serve.py), end-to-end.

Starts the real ``ThreadingHTTPServer`` on an ephemeral loopback port
against the synthetic fixture package and exercises the full request path:
static assets, the JSON adapter, error documents, determinism over the
wire, saved/history flows, and the withheld-operation surface.

Synthetic fixture only — never the qualified M2 baseline.
"""

from __future__ import annotations

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
from serving.baseline import open_baseline
from ui.api import UiApi
from ui.serve import STATIC_FILES, _Handler, _ensure_index


class UiHttpBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d62-ui-http-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.handle = open_baseline(self.pkg, spec=self.facts["spec"])
        self.state = os.path.join(self.root, "state")
        _ensure_index(self.handle, self.state)
        self.saved = os.path.join(self.root, "saved-state")
        self.history = os.path.join(self.root, "history-state")
        self.api = UiApi(self.handle, self.state, self.saved, self.history, m2=False, repo_root=None)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.ui_api = self.api  # type: ignore[attr-defined]
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.root, ignore_errors=True)

    def http(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def http_json(self, method, path, body=None):
        status, headers, payload = self.http(method, path, body)
        return status, headers, json.loads(payload.decode("utf-8"))


class StaticAssetTests(UiHttpBase):
    def test_index_served(self):
        status, headers, payload = self.http("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type"))
        text = payload.decode("utf-8")
        # spec §4.1 exact title (TASK65 Phase 4 restored it; the former
        # "Local Historical Data Console" text was the D1 defect)
        self.assertIn("I4 Historical Data Engine (10-Year NSE Corpus)", text)
        self.assertIn("Data Explorer", text)

    def test_css_and_js_served(self):
        for path in ("/app.css", "/app.js"):
            status, headers, _ = self.http("GET", path)
            self.assertEqual(status, 200, path)
        self.assertIn("text/css", self.http("GET", "/app.css")[1].get("Content-Type"))
        self.assertIn("javascript", self.http("GET", "/app.js")[1].get("Content-Type"))

    def test_no_directory_traversal(self):
        for path in ("/..%2f..%2fetc%2fpasswd", "/%2e%2e/app.py", "/static/app.js", "/ui/serve.py"):
            status, _, _ = self.http("GET", path)
            self.assertEqual(status, 404, path)

    def test_static_table_is_the_whitelist(self):
        self.assertEqual(set(STATIC_FILES), {"/", "/index.html", "/app.css", "/app.js"})

    def test_deterministic_headers(self):
        status, headers, _ = self.http("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Server"), "i4-ui")
        # the Date header is fixed (no wall-clock in responses)
        self.assertEqual(headers.get("Date"), "Thu, 01 Jan 1970 00:00:00 GMT")


class AdapterOverHttpTests(UiHttpBase):
    def test_status(self):
        status, headers, document = self.http_json("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type").split(";")[0], "application/json")
        self.assertEqual(document["package_run_id"], serving_fixtures.FIXTURE_RUN_ID)

    def test_q3_over_http_and_determinism(self):
        body = {"mode": "Q3-instrument", "params": {"symbol": "RELIANCE", "series": "EQ"}}
        first = self.http("POST", "/api/query", body)
        second = self.http("POST", "/api/query", body)
        self.assertEqual(first[0], 200)
        self.assertEqual(first[2], second[2])  # byte-identical bodies
        document = json.loads(first[2])
        self.assertEqual(document["query"]["result_count"], 4)

    def test_invalid_request_error_document(self):
        status, _, document = self.http_json("POST", "/api/query", {"mode": "Q4-filter", "params": {"filters": {"trading_status": "X"}}})
        self.assertEqual(status, 400)
        self.assertEqual(document["result"], "fail")
        self.assertEqual(document["check"], "query-input")

    def test_malformed_json_body(self):
        request = urllib.request.Request(self.base + "/api/query", data=b"{not json", method="POST")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        self.assertEqual(status, 400)

    def test_withheld_operations_have_no_route(self):
        for path in ("/api/logs", "/api/export", "/api/raw", "/api/process"):
            status, _, document = self.http_json("GET", path)
            self.assertEqual(status, 404, path)
            self.assertEqual(document["check"], "route-not-found", path)

    def test_saved_and_history_over_http(self):
        status, _, _ = self.http_json(
            "POST",
            "/api/saved",
            {"id": "tcs-2016", "mode": "Q3-instrument", "params": {"symbol": "RELIANCE", "series": "EQ"}},
        )
        self.assertEqual(status, 201)
        status, _, document = self.http_json("POST", "/api/saved/tcs-2016/run", {})
        self.assertEqual(status, 200)
        self.assertEqual(document["query"]["result_count"], 4)
        # C2(a): the saved run wrote no history
        status, _, document = self.http_json("GET", "/api/history")
        self.assertEqual(document["count"], 0)
        # explicit recording
        status, _, document = self.http_json(
            "POST",
            "/api/history",
            {"mode": "Q3-instrument", "params": {"symbol": "RELIANCE", "series": "EQ"}},
        )
        self.assertEqual(status, 201)
        self.assertEqual(document["outcome"], "success")
        status, _, document = self.http_json("GET", "/api/history")
        self.assertEqual(document["count"], 1)


class IndexStartupTests(unittest.TestCase):
    def test_ensure_index_builds_when_missing(self):
        self.root = tempfile.mkdtemp(prefix="d62-ui-index-")
        try:
            self.pkg = os.path.join(self.root, "pkg")
            facts = serving_fixtures.build_fixture_package(self.pkg)
            handle = open_baseline(self.pkg, spec=facts["spec"])
            state = os.path.join(self.root, "state")
            document = _ensure_index(handle, state)
            self.assertEqual(document["format"], "serving-index/1.2")
            self.assertTrue(os.path.isfile(os.path.join(state, "serving_index.json")))
            # idempotent reload
            again = _ensure_index(handle, state)
            self.assertEqual(again, document)
        finally:
            shutil.rmtree(self.root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
