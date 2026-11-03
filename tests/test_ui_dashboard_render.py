"""Focused Dashboard rendering tests (TASK65 Phase 3; D23 §17(b)).

Runs ``tests/ui_render_harness.js`` (Node) against the real
``src/ui/static/app.js``: the harness loads the app in a sandboxed vm context
with DOM/fetch stubs and asserts per-region rendering under partial query
failure (error containment, no fabricated values). Skipped when Node is not
installed (the suite must stay runnable in minimal environments).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(REPO_ROOT, "src", "ui", "static", "app.js")
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_render_harness.js")


@unittest.skipIf(shutil.which("node") is None, "node not installed — JS rendering harness unavailable")
class UiDashboardRenderTests(unittest.TestCase):
    def test_dashboard_error_containment_scenarios(self):
        completed = subprocess.run(
            ["node", HARNESS, APP_JS],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        lines = [l for l in completed.stdout.splitlines() if l.startswith(("PASS ", "FAIL ", "HARNESS"))]
        self.assertEqual(
            completed.returncode,
            0,
            "harness output:\n" + completed.stdout + "\n" + completed.stderr,
        )
        passed = [l for l in lines if l.startswith("PASS ")]
        self.assertGreaterEqual(len(passed), 30, "expected a full scenario battery:\n" + "\n".join(lines))
        self.assertIn("HARNESS OK", lines)


if __name__ == "__main__":
    unittest.main()
