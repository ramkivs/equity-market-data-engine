"""Focused page-exclusivity regression tests (TASK67, F-N1).

F-N1 (TASK66 finding): ``app.css`` sets ``.page { display: flex }`` (author
origin), which overrides the UA rule ``[hidden] { display: none }`` — so the
``hidden`` attribute that ``switchPage()`` toggles on the two page sections
was inert, both pages rendered stacked, and the nav active state could
diverge from the displayed page.

These tests pin the corrected contract end to end:
  * the CSS hides ``.page[hidden]`` with a rule that cannot be shadowed by
    the ``.page`` layout rule (selector specificity 0,2,0 > 0,1,0);
  * the markup keeps the two ``.page`` sections with the initial
    ``hidden`` state;
  * ``switchPage()`` keeps using the ``hidden`` attribute + nav
    ``aria-current`` as its visibility mechanism (the contract the CSS
    rule relies on);
  * the Node harness (same app.js, stubbed DOM) proves the behavioral
    half: exactly one page visible at a time, nav tracking the page.
Skipped where Node is unavailable; the CSS/markup/contract checks always
run.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CSS = os.path.join(REPO_ROOT, "src", "ui", "static", "app.css")
APP_JS = os.path.join(REPO_ROOT, "src", "ui", "static", "app.js")
INDEX_HTML = os.path.join(REPO_ROOT, "src", "ui", "static", "index.html")
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_page_exclusivity_harness.js")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class PageExclusivityCssTests(unittest.TestCase):
    def test_page_layout_rule_present(self):
        """Documents the conflicting author rule the fix must override."""
        css = read(APP_CSS)
        m = re.search(r"\.page\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m, "expected the .page layout rule to exist")
        self.assertRegex(m.group(1), r"display\s*:\s*flex")

    def test_page_hidden_rule_overrides_page_display(self):
        """F-N1 regression: `.page[hidden]` must force display:none."""
        css = read(APP_CSS)
        m = re.search(r"\.page\[hidden\]\s*\{([^}]*)\}", css)
        self.assertIsNotNone(
            m,
            "F-N1 regression: no .page[hidden] rule — the UA [hidden]"
            " rule is overridden by .page{display:flex}, so hidden page"
            " sections would render simultaneously",
        )
        self.assertRegex(
            m.group(1),
            r"display\s*:\s*none",
            ".page[hidden] must set display: none",
        )
        later = css[m.end():]
        self.assertIsNone(
            re.search(
                r"\.page\[hidden\]\s*\{[^}]*display\s*:\s*(?!none)[a-z-]+",
                later,
            ),
            "a later rule re-displays .page[hidden]",
        )

    def test_no_weaker_hidden_rule_masks_the_fix(self):
        """No author rule may re-display elements carrying both .page and
        the hidden attribute via a selector of specificity >= (0,2,0)."""
        css = read(APP_CSS)
        for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
            selector, body = m.group(1).strip(), m.group(2)
            if ".page" in selector and "[hidden]" in selector and re.search(
                r"display\s*:\s*(?!none)[a-z-]+", body
            ):
                self.fail("rule %s re-displays .page[hidden]" % selector)


class PageExclusivityMarkupTests(unittest.TestCase):
    def test_index_page_sections_and_initial_hidden(self):
        html = read(INDEX_HTML)
        m_dash = re.search(r'<section id="page-dashboard" class="page"[^>]*>', html)
        m_expl = re.search(r'<section id="page-explorer" class="page"[^>]*>', html)
        self.assertIsNotNone(m_dash, "dashboard page section missing")
        self.assertIsNotNone(m_expl, "explorer page section missing")
        self.assertNotIn("hidden", m_dash.group(0), "dashboard must not start hidden")
        self.assertIn("hidden", m_expl.group(0), "explorer must start hidden")

    def test_nav_items_carry_data_page(self):
        html = read(INDEX_HTML)
        self.assertRegex(html, r'<button class="nav-item" data-page="dashboard"')
        self.assertRegex(html, r'<button class="nav-item" data-page="explorer"')


class SwitchPageContractTests(unittest.TestCase):
    """The JS mechanism the CSS rule relies on: switchPage() must keep
    driving visibility through the `hidden` attribute and the nav
    aria-current (no drift to classes/inline styles that the regression
    CSS would not cover)."""

    def test_switchpage_toggles_hidden_on_both_sections(self):
        js = read(APP_JS)
        self.assertRegex(js, r'\$\("page-dashboard"\)\.hidden\s*=\s*page\s*!==\s*"dashboard"')
        self.assertRegex(js, r'\$\("page-explorer"\)\.hidden\s*=\s*page\s*!==\s*"explorer"')

    def test_switchpage_owns_nav_aria_current(self):
        js = read(APP_JS)
        self.assertRegex(js, r'\.nav-item\[data-page\]')
        self.assertRegex(js, r'setAttribute\("aria-current",\s*"page"\)')
        self.assertRegex(js, r'removeAttribute\("aria-current"\)')


@unittest.skipIf(shutil.which("node") is None, "node not installed — JS page-exclusivity harness unavailable")
class PageExclusivityBehaviorTests(unittest.TestCase):
    def test_page_exclusivity_and_nav_tracking(self):
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
        self.assertGreaterEqual(
            len([l for l in lines if l.startswith("PASS ")]), 9, "\n".join(lines)
        )
        self.assertIn("HARNESS OK", lines)


if __name__ == "__main__":
    unittest.main()
