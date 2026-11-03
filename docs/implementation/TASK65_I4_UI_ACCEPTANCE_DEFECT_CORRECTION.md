# TASK65 — I4 UI acceptance defect correction (bounded)

Authoritative baseline: `1f86d88…` (TASK62 first-release UI implementation).
Defect authority: `docs/investigations/TASK64_I4_UI_VISUAL_ACCEPTANCE_COMPARISON.md`
(commit `c38c481…`; evidence `1b43e0d8…` on
`evidence/i4-ui-visual-acceptance-2026-10-10`), UNEXPECTED rows D1–D8 + D24.
Implementation authority: D23 §17(a) (Q8 serving-side correction, no
canonical-data change) + §17(b) (dashboard error containment) + §17(c)
(explorer: exact spec §4.1 title; §6.9 saved-query sidebar over the existing
D38 API). Scope is bounded to those listed defects; nothing else was changed.

## Phase 1 — authority verification (no code)

Safety battery (rollback value-audit 0/0, unshallow, ref + tree repair)
performed; TASK64 report and evidence refs re-verified (hash `350194adc2…`);
D23 §17 re-read and confirmed sufficient for all four phases; no withheld
capability is implicated; remote branches/commits preserved.

## Phase 2 — Q8 serving parser contract correction

Root cause (proven in TASK64): the pinned runner revision (fingerprint
`f3ebf624…`, in-repo code byte-matches the executed revision) publishes the
terminal `cross-era-boundary-residual` record in `w2/unresolved.jsonl`
**without** a `state` field; the serving Q8 parser (D32) required `kind` +
string `state` on every record — so Q8 could never succeed over a
runner-produced package, and the real M2 package's line 11 always failed.

Correction (`src/serving/quality.py`): `parse_unresolved` now validates
against the runner-published schema — every line must be a JSON record with a
non-empty string `kind`; the published stateless kind
`cross-era-boundary-residual` (constant `CROSS_ERA_RESIDUAL`) is accepted in
its stateless form (a present-but-non-string `state` on it, including an
explicit JSON null, still fails closed); every other kind still requires a
string `state`. Non-record lines, missing `kind`, and any other malformed
shape fail closed exactly as before. No canonical data was altered,
regenerated, or rerun.

Regression (`tests/test_serving_quality.py`, class
`Q8RunnerProducedFileTests`): runs the **real** `i4_runner` over the
authorized fixture corpus, re-signs the package with the serving baseline
identity, and serves Q8 through the real `handle_query` path — asserting the
runner-produced file parses, the Q8 view is served as published (11 records,
terminal record stateless), and both adjacent malformed shapes
(non-string `state` on cross-era; absent `state` on an ordinary kind) still
fail closed.

## Phase 3 — dashboard error containment

`src/ui/static/app.js` (`loadDashboard` / renderers): the five dashboard
queries now settle independently (`Promise.allSettled`); a failed query
records its error in `S.dash.<q>Error` + `S.dash.errors` and renders it in
the region(s) that depend on it, while unrelated regions render from their
own successful responses. No fabricated data: a value whose source failed
renders as explicitly unavailable with the failure named (coverage
`Total rows`/dates null on Q1/Q6 failure, `Total archives` null on Q9
failure; KPI cards "unavailable — Qx failed: …"); the run summary carries a
consolidated per-query failure list; a failed load stays retryable
(`S.dash.loaded` true only when zero queries failed). If `/api/status`
itself fails, every query is marked failed together and no region renders.

Focused tests: `tests/ui_render_harness.js` (Node vm sandbox loading the real
`app.js` with DOM/fetch stubs; scenarios: all-5-fail, Q8-only-fail — the
TASK64 defect shape — Q1-only-fail, all-ok, adapter-unreachable; 38
assertions on per-region innerHTML) driven by
`tests/test_ui_dashboard_render.py` (unittest wrapper; skipped when Node is
absent).

## Phase 4 — spec §4.1 title + §6.9 saved-query sidebar

- `index.html`: document title and visible title bar restored to the exact
  spec string `I4 Historical Data Engine (10-Year NSE Corpus)` (the former
  "Local Historical Data Console" text was defect D1); `tests/test_ui_http.py`
  updated to assert the spec title.
- Saved-query sidebar: the explorer page now carries a compact
  `Saved Queries` sidebar (spec §6.9) beside the tabs, built exclusively on
  the existing D38 serving API (`/api/saved` list/show) — compact list with
  the selected entry shown distinctly, a `New Query` action that starts the
  authorized create flow (Query Builder → Save Query; no prefill, no
  fabricated definitions), and a guided empty state ("Nothing is seeded").
  Clicking an entry loads its definition into the Query Builder through the
  same `loadSavedIntoBuilder` path the Saved Queries tab's Update action now
  uses (single shared loader; no alternate query path). Entering the explorer
  page loads the list once. All authority-driven unavailable controls are
  preserved unchanged.

## Changed files

- `src/serving/quality.py` — parser contract correction (docstring,
  `CROSS_ERA_RESIDUAL`, `parse_unresolved`)
- `tests/test_serving_quality.py` — `Q8RunnerProducedFileTests` (3 tests)
- `src/ui/static/app.js` — error containment; sidebar state/rendering/hooks;
  shared `loadSavedIntoBuilder`
- `src/ui/static/index.html` — spec title ×2; sidebar structure
- `src/ui/static/app.css` — sidebar + failure-list styles (existing tokens)
- `tests/test_ui_http.py` — title assertion corrected to the spec string
- `tests/ui_render_harness.js` (new), `tests/test_ui_dashboard_render.py` (new)

## Test evidence (this commit's tree)

- `tests.test_serving_quality`: 22 OK (was 19; +3 runner-through-parser)
- harness: 38/38 PASS (`node tests/ui_render_harness.js src/ui/static/app.js`)
- full suite: **892 tests OK (14 skipped)** — the same standing
  D24_M2_ROOT-gated skips; UI-boundary suite (determinism, no direct durable
  access, no alternate query path, withheld-capability markers) passes
  unchanged; `node --check src/ui/static/app.js` clean.

## Not changed

M2 package (no modification/regeneration/rerun); the runner; Q1–Q10 query
semantics beyond the Q8 parser contract; all other pages/controls; the
evidence branch and the mockup branch; publication scope (this commit is
additive on the session branch only; no main promotion).

## Limitations

No visual acceptance: automated tests prove the error-containment and
sidebar contracts and the exact title string, not pixels. The D24_M2_ROOT
package legs remain gated in this environment (package absent; byte-exact
replay is the only authorized re-verification path).

## Next Windows acceptance steps

1. Re-pin the untracked `_transfer_delivery/m2/ui/` handoff to this commit
   (the runbook's stale-pin check then verifies this identity, not `1f86d88`).
2. Fresh 1536×1024 captures of Dashboard + Data Explorer from the re-pinned
   code over the qualified M2 baseline.
3. Compare against the original mockups per the TASK64 protocol; the
   previously-UNEXPECTED rows D1–D8 + D24 must no longer appear;
   AUTHORITY-DRIVEN rows remain expected.
4. Only after that comparison can visual acceptance be claimed (or not).
