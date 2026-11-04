# EquiCore rebranding audit

Date: 2026-11-04. Applied on top of the PR #3 merge commit
`fa526078d12a42a9d0a1e4befa1787411e8785c9` on the authoritative `main` line.

Product name: **EquiCore**.
Product description: **Equity Market Data Intelligence & Infrastructure Engine**.
Target repository: `ramkivs/equity-market-data-engine`
(`https://github.com/ramkivs/equity-market-data-engine.git`).

Scope: presentation and product identity only. No market-data functionality,
architecture, persistence, ingestion, serving or API redesign.

## 1. Method

Repository-wide search over every tracked text file (plus the new favicon),
case-insensitive, for the exact old product/repository names and their clearly
branded variations:

```
git grep -i -n -E 'nse[-_ ]historical[-_ ]data[-_ ]engine|historical data engine|NSE Historical|Local Historical Data Console' -- .
git grep -i -n -F 'NSE-Historical-Data-Engine' -- .
git grep -i -n -F 'nse-historical-data-engine' -- .
git grep -n -F 'github.com/ramkivs/nse-historical-data-engine' -- .
```

Pre-change census: **140 lines** containing a matched pattern.
Product-brand literals: **25 occurrences in 14 files**. Repository-slug
literals: **102 occurrences in 53 files** (`docs/` 89, `evidence/` 5,
`tests/` 4, `tools/` 4). NSE exchange / market-data terminology: **24
occurrences in 11 files**.

## 2. Classification and disposition

| Class | Pre-change | Action | Reason |
|---|---|---|---|
| Live product identity in the application shell (`src/ui/static/index.html`, 3 occurrences: browser title, title-bar title, title-bar subtitle) | 3 | **Replaced with EquiCore + product description** | User-visible application branding |
| Live product identity in `README.md` (heading / tagline) | 1 | **Replaced**; added product description and the new authoritative repository URL | Current, forward-facing product documentation |
| Old title literal asserted by `tests/test_ui_http.py` and the historical D1 defect comment | 2 | **Removed**; replaced by stronger EquiCore assertions plus negative old-brand guards | Test carried the old identity as an expectation |
| Historic decision / investigation / design / implementation records under `docs/` (16 occurrences incl. the literal I4 UI spec strings, TASK62/64/65/66/67 records, product & serving architecture intent) | 16 | **Retained** | Historical factual records. They quote the UI strings and repository identity that existed at the time of each decision; rewriting them would falsify the evidence trail |
| `src/nse_engine/__init__.py`, `src/nse_engine/contract.py` docstrings (2) | 2 | **Retained** | `contract.py` is one of the governed `ENGINE_MODULES` covered by the pinned `GOVERNED_TOOL_FINGERPRINT` (`d3269b73…`). Any byte change — even a docstring — would alter a governed fingerprint. Changing the fingerprint is explicitly out of scope |
| `evidence/` files (5 slug occurrences + 1 product-brand occurrence) | 6 | **Retained** | Hash-pinned evidence fixtures and the original visual-reference manifest; absolute Windows/Arena paths and historical repository identity are factual source material |
| `tests/test_i4_runner.py::WINDOWS_PATH_RAW`, `tests/test_i4_replay_qualification.py` synthetic revision fixture / assertion, `tools/i4_m2/` replay-qualification example and tool README | 8 | **Retained** | Canonical identifiers in replay-qualification evidence (`--expect-repository`, `--expect-ref`), a Windows path leakage fixture, and dated tool records. `--expect-repository` is a required caller-supplied argument with no default, so the rename does not change runtime behaviour |
| `docs/` session-branch names (`arena/9021d1a1-…`, `arena/215cb93c-…`, `arena/01a10c83-…`) and dated repository / `origin` URL tables (89 slug occurrences) | 89 | **Retained** | Git ref names and recorded remote URLs are historical facts; GitHub redirects the old repository URL after the in-place rename |
| NSE as exchange / data source / official document (`10-Year NSE Historical Data`, `NSE Corpus`, `NSE historical archives`, `NSE Historical Data Dissemination doc`) | 24 | **Retained** | Market-data terminology and technical specification, not product branding. Retained verbatim in the rebranded UI so the corpus description stays accurate |
| `i4-ui` HTTP `Server` header, `i4-ui/1.0` startup service value, `i4-ui-serving-adapter/1.0` adapter `SERVICE`, `STATIC_FILES`/`STATIC_TYPES` keys, CSS class and DOM ids, `nse_engine` package/import path | n/a | **Retained** | Technical identifiers and API/serving contracts, not product branding; pinned by existing tests |

Post-change literal count (before this audit document was added) is 24
product-brand strings: 16 retained in historical `docs/` records, 1 in the
original visual-reference evidence manifest, 2 in the governed engine
docstrings, and **5 newly added negative assertions** in
`tests/test_ui_http.py` that deliberately spell the old strings to prove they
are absent from the served application. The search-pattern literals quoted in
this audit document are documentation of the audit, not product branding.
Zero old product branding remains in any user-visible application surface
(`src/ui/static/*`): `git grep -i -E 'NSE Historical Data Engine|I4 Historical Data Engine|Historical Data Engine|Local Historical Data Console' -- src/ui/static` returns nothing.

## 3. Files changed and purpose

| File | Purpose |
|---|---|
| `README.md` | Product heading → EquiCore; product description; authoritative repository URL |
| `src/ui/static/index.html` | Browser `<title>`, `<meta name="description">`, favicon `<link>`, `EC` wordmark, header title/subtitle, sidebar wordmark + nav label/tooltip, dashboard heading/subtitle, Data Explorer subtitle, connecting/startup state, service tooltip, status bar |
| `src/ui/static/equicore.svg` (new) | EquiCore SVG favicon: `EC` monogram in the existing dark-navy/accent palette, with `<title>EquiCore</title>` and the product description |
| `src/ui/static/app.css` | One `.nav-brand` rule using existing design tokens; header comment rebranded. No colour, typography, layout or component change |
| `src/ui/static/app.js` | Startup/connecting and adapter-error service strings prefixed with EquiCore; header comment rebranded. No query, rendering or data logic change |
| `src/ui/serve.py` | Added `/equicore.svg` → `equicore.svg` to the exact static whitelist and `.svg` → `image/svg+xml` to `STATIC_TYPES`. This is the only new route; `version_string()`, the adapter and all API routes are unchanged |
| `tests/test_ui_http.py` | Replaced the old-title expectation with EquiCore assertions for title, metadata, wordmark, sidebar, dashboard, status bar and startup state; added favicon, product-description, NSE-terminology, no-old-brand and served CSS/JS checks; updated the static whitelist expectation |
| `docs/implementation/EQUICORE_BRANDING_AUDIT.md` (new) | This classification record |

No file under `evidence/`, `src/nse_engine/`, `src/serving/`, `tools/` or any
historical `docs/` decision/spec/investigation record was modified.

## 4. Technical compatibility

No change to: package/module identifiers or import paths (`nse_engine`,
`serving`, `ui`); canonical market-data contracts and schemas; historical
archive formats or parser identifiers; database schemas; registry, index,
binding or persisted-state formats; CLI commands or configuration; data
provenance, lineage and qualification evidence; API/serving contracts
(`SERVICE`, `QUERY_MODES`, route table, JSON documents); user data and file
formats; pinned hashes, fingerprints, inventory manifests or evidence
fixtures.

The single surface addition is the static GET route `/equicore.svg`. It is a
presentation asset in the same exact whitelist; it is not a data route, carries
no adapter interaction, and is covered by
`tests/test_ui_http.py::test_favicon_identifies_equicore` and
`::test_static_table_is_the_whitelist`. Backward compatibility is preserved:
`version_string()` still returns `i4-ui`, `/api/status` still reports
`i4-ui-serving-adapter/1.0`, and all pre-existing static paths are unchanged.

## 5. Repository rename — target, not yet executed

Target: `ramkivs/nse-historical-data-engine` →
`ramkivs/equity-market-data-engine`, as an in-place GitHub rename (no
replacement repository, no history migration). `README.md` already carries the
target URL.

**The rename has not been performed.** `gh repo rename`, the REST
`PATCH /repos/{owner}/{repo}` endpoint and the GraphQL `updateRepository`
mutation all return HTTP 403 `Resource not accessible by integration`, with
response header `X-Accepted-Github-Permissions: administration=write`. The
Arena GitHub App installation token reports `admin: true` on the repository but
the installation itself lacks the "Administration: write" permission required
for repository settings changes. The credential used by `git` is the same
token, so no alternative path exists in this environment.

The local `origin` URL therefore deliberately remains the working old URL
(`https://github.com/ramkivs/nse-historical-data-engine.git`); pointing it at
the target URL before the rename would make every fetch and push fail (the
target URL currently returns "Repository not found"). The target name does not
exist as a separate repository (API 404) — no replacement repository was
created.

Once the GitHub connection is reconnected with administration permission (or
the owner performs the rename in GitHub Settings), the two remaining steps are:

```
gh repo rename equity-market-data-engine --repo ramkivs/nse-historical-data-engine --yes
git remote set-url origin https://github.com/ramkivs/equity-market-data-engine.git
```

Historical records keep the recorded old URL verbatim; GitHub's rename redirect
keeps those links resolvable. An in-place rename preserves PR history,
branches, tags, commits, releases, issues and repository contents.

## 6. Validation (Linux, Python 3.11.2, Node v22.22.3 already installed)

| Command | Result |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests -t .` | **Ran 1140 tests in 97.938s — OK (skipped=14)**, 0 failures, 0 errors |
| `PYTHONPATH=src python3 -B -m unittest tests.test_ui_http tests.test_ui_api tests.test_ui_boundary tests.test_ui_dashboard_render tests.test_ui_derive tests.test_ui_page_exclusivity` | **Ran 94 tests — OK** (0 failures, 0 errors, 0 skips) |
| Real `python -B -m ui.serve ...` subprocess startup smoke (one-off `/tmp/equicore_startup_smoke.py`, synthetic fixture package) | **PASS**: ready line, `GET /`, `/equicore.svg`, `/app.css`, `/app.js`, `/api/status`; browser title, metadata, favicon link + SVG payload, `EC` wordmark, sidebar/nav, dashboard heading, connecting state, status bar, both `data-page` nav targets, NSE terminology, no old brand; `service=i4-ui-serving-adapter/1.0` unchanged |
| `node tests/ui_render_harness.js src/ui/static/app.js` | **HARNESS OK** (existing Dashboard error-containment / loading / empty-state / retry rendering checks) |
| `node tests/ui_page_exclusivity_harness.js src/ui/static/app.js` | **HARNESS OK** (existing navigation / single-visible-page checks) |
| `python3 -B -m compileall -q src tests` | **OK** (syntax check; not a build or type check) |
| `git diff --name-only -- evidence src/nse_engine src/serving` | empty — no evidence, engine or serving bytes changed |

No `package.json`, `pyproject.toml`, `setup.py`, `Makefile`, CI workflow,
mypy/flake8/ruff configuration or dependency manifest exists in this
repository. **No configured build or type-check was run, and none is claimed.**
No new dependencies were introduced. No headless browser was available in the
Linux environment, so visual pixel rendering was not performed; browser title,
favicon, navigation and page rendering were verified at the HTTP/markup level,
through the existing JS rendering harnesses and through the existing UI unittest
modules.

## 7. Boundaries

This is a presentation-only change. PR #3's Windows corrections and all 1,138
previously verified tests are preserved. The complete Windows suite evidence
used for PR #3 remains the only full Windows run; no new Windows full-suite run
is claimed here, and no B5/B7 gate is advanced by this rebranding record.
