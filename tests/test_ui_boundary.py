"""D23 §18(9) — UI boundary proof (structural + static-asset level).

Proves the presentation layer's boundary by inspection of the code the UI
ships with, complementing the behavioral tests (test_ui_api.py /
test_ui_http.py):

1. NO DIRECT DURABLE-DATA ACCESS — ``ui/api.py`` and ``ui/derive.py`` never
   open files, never resolve paths, and never call ``baseline.path``;
   every value flows through the serving operations. ``ui/serve.py``
   touches the package only through the serving entry points
   (open_baseline / build_index / write_index / load_index /
   rebuild_state) — the same entry points the CLI uses.
2. NO ALTERNATE QUERY PATH — the UI's only query address is the exact
   Q1–Q10 mode set (``serving.saved.SAVED_MODES``); the route table
   contains no other data route.
3. NO ACTIVE CONTROLS FOR WITHHELD CAPABILITIES — the static frontend
   references no log/export/raw/processing endpoints, never renders
   ``raw_line``, and carries explicit unavailable markers for every
   withheld mockup control.
4. DETERMINISTIC RESPONSES — API bodies are canonical JSON (no wall-clock,
   no randomness in derived output: ``ui/derive.py`` imports no
   clock/random/os modules).
"""

from __future__ import annotations

import ast
import os
import re
import unittest

from serving.saved import SAVED_MODES
from ui.api import QUERY_MODES

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "ui")
STATIC_DIR = os.path.join(UI_DIR, "static")


def _source(filename):
    with open(os.path.join(UI_DIR, filename), "r", encoding="utf-8") as handle:
        return handle.read()


def _static(filename):
    with open(os.path.join(STATIC_DIR, filename), "r", encoding="utf-8") as handle:
        return handle.read()


def _imports(filename):
    """The set of module names imported by one ui source file (top-level of each import)."""
    tree = ast.parse(_source(filename))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class NoDirectDurableAccessTests(unittest.TestCase):
    def test_api_never_opens_baseline_data(self):
        source = _source("api.py")
        # no direct file I/O anywhere in the adapter
        self.assertNotIn("open(", source)
        # never resolves a baseline path itself (the serving layer owns that)
        self.assertNotIn("baseline.path", source)
        self.assertNotIn(".path(", source)
        self.assertNotIn("makedirs", source)
        self.assertNotIn("os.walk", source)
        self.assertNotIn("shutil", source)
        # the ONLY os.path usage is the store-root freshness helper, which
        # inspects the UI's own class-(4) user-state root — never the baseline
        tree = ast.parse(source)
        store_absent_nodes = [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_store_absent"
        ]
        self.assertEqual(len(store_absent_nodes), 1)
        store_absent_range = (store_absent_nodes[0].lineno, store_absent_nodes[0].end_lineno)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("isfile", "join", "exists"):
                value = node.value
                is_os_path = (
                    isinstance(value, ast.Attribute)
                    and value.attr == "path"
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "os"
                )
                if is_os_path:
                    self.assertTrue(
                        store_absent_range[0] <= node.lineno <= store_absent_range[1],
                        "os.path.* used outside _store_absent at line %d" % node.lineno,
                    )

    def test_api_imports_only_serving_and_stdlib(self):
        names = _imports("api.py")
        stdlib = {"re", "os", "threading", "typing", "__future__"}
        self.assertTrue(names <= ({"serving"} | stdlib), names)

    def test_derive_is_pure(self):
        names = _imports("derive.py")
        self.assertTrue(names <= {"re", "typing", "__future__"}, names)
        tree = ast.parse(_source("derive.py"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
        forbidden = {"open", "makedirs", "walk", "now", "utcnow", "time", "random", "randint", "shuffle", "system"}
        self.assertFalse(called & forbidden, called & forbidden)

    def test_serve_uses_only_serving_entry_points(self):
        source = _source("serve.py")
        # the package is touched only through the serving boundary entry points
        for entry in ("open_baseline(", "build_index(", "write_index(", "load_index(", "rebuild_state("):
            self.assertIn(entry, source)
        self.assertNotIn("baseline.path", source)
        # static serving is an exact whitelist — no open() of arbitrary paths
        self.assertNotIn("os.path.join(STATIC_DIR, self.path)", source)

    def test_no_ui_module_reaches_into_nse_engine_or_raw_storage(self):
        for filename in ("api.py", "serve.py", "derive.py", "__init__.py"):
            names = _imports(filename)
            self.assertNotIn("nse_engine", names, filename)
            self.assertNotIn("nse", names, filename)


class NoAlternateQueryPathTests(unittest.TestCase):
    def test_query_modes_are_exactly_q1_q10(self):
        self.assertEqual(QUERY_MODES, tuple(sorted(SAVED_MODES)))
        self.assertEqual(len(QUERY_MODES), 10)

    def test_route_table_contains_only_authorized_routes(self):
        source = _source("api.py")
        # every string-literal route the dispatcher knows
        routes = set(re.findall(r'path == "([^"]+)"', source)) | set(re.findall(r'["\'](/api/[^"\']+)["\']', source))
        allowed = {"/api/status", "/api/query", "/api/saved", "/api/history"}
        for route in routes:
            base = route
            self.assertTrue(
                base in allowed or base.startswith("/api/saved") or base.startswith("/api/history"),
                "unexpected route: %r" % route,
            )

    def test_single_dispatch_reuse(self):
        # the query path calls the CLI's shared dispatch — the same function
        source = _source("api.py")
        self.assertIn("execute_query_definition(", source)
        self.assertIn("from serving.saved import", source)


class WithheldCapabilityTests(unittest.TestCase):
    def test_frontend_references_no_withheld_endpoint(self):
        js = _static("app.js")
        html = _static("index.html")
        for forbidden in ("/api/logs", "/api/export", "/api/raw", "/api/process", "raw_line", "XMLHttpRequest", "WebSocket"):
            self.assertNotIn(forbidden, js, forbidden)
            self.assertNotIn(forbidden, html, forbidden)

    def test_frontend_carries_explicit_unavailable_markers(self):
        html = _static("index.html")
        # withheld operations are present as UNAVAILABLE, never as active controls
        self.assertIn("Run New Processing", html)
        self.assertIn('disabled', html.split("Run New Processing")[0].rsplit("<button", 1)[1])
        self.assertIn("Verify Existing Run", html)
        self.assertIn("Advanced Query", html)
        self.assertIn("unavailable", html)
        self.assertIn("Engine Logs", html)
        self.assertIn("no authorized log-serving operation", html)
        js = _static("app.js")
        self.assertIn("no reliability classification", js)  # Reliable Only preset
        self.assertIn("raw-content serving is explicitly withheld", js)  # View Raw Record
        self.assertIn("Windows custody", js)  # View Archive
        self.assertIn("not a canonical field", js)  # Trading Status / company fields

    def test_frontend_uses_only_authorized_api_routes(self):
        js = _static("app.js")
        used = set(re.findall(r'["\'](/api/[^"\']*)["\']', js))
        allowed_prefixes = ("/api/status", "/api/query", "/api/saved", "/api/history")
        for route in used:
            self.assertTrue(any(route == p or route.startswith(p + "/") or route == p for p in allowed_prefixes), route)


class DeterminismTests(unittest.TestCase):
    def test_no_clock_or_randomness_in_derive(self):
        tree = ast.parse(_source("derive.py"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
        self.assertFalse(called & {"now", "time", "random", "randint", "shuffle", "utcnow"}, called)

    def test_response_encoding_is_canonical_json(self):
        from serving.index import canonical_json
        from ui.api import encode

        document = {"b": 1, "a": [1, 2], "c": {"z": None, "y": "x"}}
        self.assertEqual(encode(document), canonical_json(document) + "\n")


if __name__ == "__main__":
    unittest.main()
