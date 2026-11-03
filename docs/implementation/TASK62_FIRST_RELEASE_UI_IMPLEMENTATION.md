# TASK62 — I4 First-Release UI Implementation Record

**Status:** COMPLETE (bounded implementation under existing D23 §17(b) authority).
**Scope:** first-release presentation layer — shared shell, Dashboard, Data Explorer —
backed exclusively by authorized serving operations (Q1–Q10 via the single shared
dispatch, D38 saved queries, D39 query history). No production activity, no Windows
real-M2 qualification, no main promotion performed.

---

## 1. Baseline

- Repository: `ramkivs/nse-historical-data-engine`
- Session branch: `arena/9021d1a1-nse-historical-data-engine`
- Baseline session tip (parent of this record's commit):
  `c60b15defc45f14db49117e9f045fd465d86b437` (TASK60 readiness record; tree `1af473dcb8bae03d0d8821c24fe988e09db34e9f`, 195 files)
- Authoritative main baseline: `69977017ffca944921f231d7904347bc582b6392` (D24, unchanged)
- Pre-mutation recovery: the 34th rollback recurred at task start (HEAD pinned to
  D24 `89ce965c…`, shallow). Repaired with the established battery: `fetch --unshallow`
  + explicit `git fetch origin` of the two reference branches (a newly created remote
  branch is NOT fetched by unshallow), byte audit of all 195 working-tree files vs
  the TASK60 tree (0 missing / 0 differing / 0 extra), then `update-ref` +
  `read-tree` + mixed reset. Worktree clean except pre-existing
  `?? _transfer_delivery/` (Windows handoff material — preserved untouched).

## 2. Design references (non-authoritative; carried into this commit, hashes verified)

| Artifact | Source branch @ commit | Path in this commit | Bytes | SHA-256 |
|---|---|---|---:|---|
| UI specification | `docs/i4-historical-data-engine-ui-spec` @ `20bf823842bb7209bea0cf5a0f53adb0c43869b8` | `docs/design/I4_HISTORICAL_DATA_ENGINE_UI_SPEC.md` | 48,186 | `ACA5ECA905B151E0F98F045F5B34BBB232E5AF27E828ACF725CAD92AD6D62165` |
| Dashboard mockup | `docs/i4-ui-mockup-references` @ `726b1c3611e77640c67d86a4ee72a09cd3415b56` | `evidence/10y historical engine.png` | 1,773,767 | `FA11F0E867D0F8AA1DF41B3AB88C51D27CE2CCD50E790E5181ECF45B2AA1AF85` |
| Data Explorer mockup | same | `evidence/10y historical engine-data explorer.png` | 1,842,012 | `53F20B6484F02AC28F4FDF5F80125B38E138E256EBF8BA5D26CFB3EE9B46BD19` |
| Mockup manifest | same | `evidence/I4_UI_MOCKUP_REFERENCES.txt` | 670 | `B83FF8A141F65FABD28C7AB10EEBF390809A3A28906E7017C4B206878D6B9F27` |

All four were verified byte-for-byte against their committed blobs before carrying
them in, and re-verified in the working tree after copy (`sha256sum`). Neither
reference branch was merged into `main`; the files are carried additively into the
session-branch implementation commit with their exact paths and hashes preserved.

Governing contracts (prevail over both references): D16-11/D16-12, D23
(§§13/14/17(b)/18/19), D15 §14, D22 §8, D30a–D39, TASK53, TASK60, TASK61.

## 3. Technology and transport decision (implementer-delegated, D23 §13/§14)

**Decision.**
- **UI technology:** Python 3 **stdlib-only** local HTTP host
  (`http.server.ThreadingHTTPServer`) serving a **vanilla HTML/CSS/JS**
  single-page frontend (no framework, no build step, no third-party runtime
  dependencies).
- **Transport:** HTTP/1.1 JSON on loopback. Default bind `127.0.0.1:8613`
  (`--bind`/`--port` configurable for supervised hosting only). The browser is a
  same-origin client of the local server (relative `/api/*` calls; no CORS surface).
- **UI↔serving boundary:** the HTTP layer maps each request to the existing
  `serving` operations only. Every query executes through
  `serving.saved.execute_query_definition` — the **single shared dispatch the CLI
  uses** — addressed by its exact Q1–Q10 mode name with parameters validated by
  `serving.saved.validate_saved_definition`. Saved-query and query-history state is
  touched only through `serving.saved` / `serving.history` at their own store roots.
  Response bodies are `serving.index.canonical_json` (deterministic bytes);
  headers are fixed (no wall-clock `Date`).

**Rationale.** The repository is stdlib-only (no dependency manifest; the D24
boundary even keeps `serving` from importing `nse_engine`), and D23 §13 requires
reusing existing technology and adding no infrastructure without demonstrated need.
A local loopback server + browser satisfies the personal single-user hosting model
(D23 §14), requires no new runtime, is rebuildable (restarting the process is the
entire deployment), and puts the rendering host (a browser) on every machine that
matters — including the Windows host where the corpus and the M2 package live.
Hand-rolled SVG charts avoid a charting dependency; the deterministic token theme
implements spec §3 exactly.

**Trade-offs (recorded).** The app requires the local server process to be running
(no standalone desktop shell); visual fidelity is tuned via the spec §17.2
screenshot-comparison protocol on the rendering host (not claimable from Arena);
`ThreadingHTTPServer` is a personal-use host, not a network product (loopback bind
is the hosting control — no auth/RBAC by contract).

**Run it.** From the repository root (with `PYTHONPATH=src`):

```
python -m ui.serve --package <qualified run package> [--m2] \
    --state <derived-state dir, OUTSIDE the package> \
    --saved-state <saved-query store dir> \
    --history-state <query-history store dir> [--repo <in-repo evidence root for Q10>]
# then open http://127.0.0.1:8613/
```

Startup mirrors the established CLI verify → build → query flow:
`open_baseline` (package verified before anything is served), then the class-(4)
index is loaded, built when missing, or rebuilt when stale (the delegated rebuild
operation, D16-11 item (b)).

## 4. Implemented surfaces and contract mappings

| Surface | Data source (authorized operation) | Notes |
|---|---|---|
| Title bar | static | "Local Historical Data Console"; no fictitious identity/user management |
| Navigation rail | static | Dashboard + Data Explorer active; the six other mockup destinations rendered as explicit **unavailable** items (reasons in tooltips) — no fake pages |
| Status bar | `/api/status` (verified package run record), Q10, Q1, Q9 | run id, engine tool name/version, archive count, row count; service state; unknown values explicit |
| Run summary | Q10 `package` section | run id, engine/version, corpus archive count, package files; **run date/time = unavailable** (not published by the contract) |
| KPI: Archives Processed | Q9 `summary.archive_count` | status glyph from Q9 D01-join verification (real data, not a nonzero heuristic) |
| KPI: Canonical Rows | Q1 `summary.row_count` | partition/instrument-pair detail |
| KPI: Identity Records | — | **unavailable**: no authorized count operation exists (Q5 is selector-scoped); explicit unavailable state per spec §5.2 |
| KPI: Trading Calendars | Q6 `record_count` / `calendar_present` | legitimate absent state shown when the package carries no calendar |
| KPI: Errors | Q8 flag census total + quarantine count | real flag counts, documented |
| Rows by Year | Q1 partitions | documented year grouping (sum of served partition `row_count` per calendar year) |
| Archives by Segment | Q9 `d01.series_counts` | documented aggregation; unavailable when no D01 facts (non-pinned baseline) |
| Data Coverage | Q6 first/last `trade_date`, Q9, Q1 | **start/end dates unavailable without a calendar** (never inferred from years) |
| Archive browser + detail | Q9 records (INPUT_MANIFEST as published + joined D01 facts + hash facts) | search/segment/year filters and sorting are display-level over served rows; export = omitted (no authorized export operation) |
| Engine logs | — | **explicit unavailable**: no authorized log-serving operation exists (D16-12; D23 §19); no endpoint, no fabricated logs |
| "Run New Processing" / "Verify Existing Run" | — | **disabled** with withholding reasons (processing trigger excluded D16-12 / withheld D23 §19; verify = CLI maintenance function) |
| Query Builder | Q2 date-range / Q3 instrument / Q4 exact-value filters | mode selector (the mockup's combined form is not a single authorized query — no combined semantics invented); contract-driven fields/operators (Q4 = equality only, four fields); invalid input distinguished from empty result |
| Quick filters | deterministic presets → Q4/Q2 | EQ (CM), EQ (FO), Debt, Currency = exact Q4 filters; Latest 1Y/3Y/5Y/10Y = data-relative Q2 range anchored on the max served partition year (no clock); **Reliable Only = unavailable** (no reliability classification in the contract) |
| Results grid | served rows (Q2/Q3/Q4 envelopes) | 13 columns bound to as-published fields (spec §16.3 order); truthful served count; display-level pagination (never implies more was fetched); flag status chips |
| Record inspector | Q7 (row + INPUT_MANIFEST archive record + reconciliation) + Q5 related records | provenance group from the served D05 §8 block (source archive, source row = `source_line_number`, archive path, hash facts); "Trading Status" = unavailable (not a canonical field); company id/name omitted (not published — no placeholders) |
| Inspector actions | — | View Reconciliation = authorized (Q7 reconciliation facts); **View Raw Record / View Archive = disabled** (raw-content serving withheld D23 §19; archive bytes in Windows custody D15 §14); Previous/Next within the served result set |
| Price chart | served rows (as-published price fields) | hand-rolled SVG line chart; non-numeric/dateless rows omitted and **counted explicitly** (never plotted as zero); volume bars optional |
| Yearly summary | served result set | documented, tested `period_summary` (served order preserved; single-year labeling rule; numeric-only sums with contributing counts) |
| Data quality | Q8 | served flag census + quarantine + unresolved + reconciliation aggregates; the mockup's Reliable/Uncertain/Missing/Excluded donut = **explicitly unavailable** (contract supplies no such classification — never reinterpreted) |
| Saved Queries | D38 (`serving.saved`) | create/show/list/update/delete/run; no seeded mockup shortcut names; no duplicate persistence logic (serving functions called directly) |
| Query History | D39 (`serving.history`) | list/show/delete; the **only** write path is the explicit "Record current query execution" action (C2(a): ordinary runs and saved runs never write history) |
| Advanced Query tab | — | **unavailable**: an alternate/more powerful query path would violate D23 §18(8) |

**Documented display-level definitions** (single source of truth: `src/ui/derive.py`,
mirrored 1:1 by `src/ui/static/app.js`; both tested):
`period_summary`, `rows_by_year`, `segment_archive_counts`, `coverage_summary`,
`flag_status`, `price_points`, `latest_years_params`, `quick_filter_params`.
All are pure, deterministic (no clock/randomness), and never reinterpret or mutate
canonical values (non-numeric as-published text is an explicit state, never zero).

## 5. Explicit omissions and unavailable states (per TASK61 reconciliation)

1. "Run New Processing" — disabled (excluded/withheld). 2. "Verify Existing Run" —
   disabled. 3. Six non-first-release nav destinations — unavailable items. 4.
   Advanced Query — unavailable. 5. Trading Status filter — omitted (not in the Q4
   field set). 6. "Reliable Only" preset — unavailable. 7. Engine logs —
   unavailable. 8. "View Raw Record" — disabled (D23 §19). 9. "View Archive" —
   disabled (D15 §14). 10. Export actions — omitted. 11. Four-bucket quality donut
   — unavailable (served census shown instead). 12. Dataset selector / last-updated
   — single dataset / no contract timestamp (explicit unavailable). 13. Identity
   Records KPI — unavailable (no count operation). Mockup saved-query shortcut names
   are never seeded. No fake timestamps or metrics anywhere; unavailable is never
   rendered as zero, success, or a valid empty result.

## 6. Tests executed (exact)

Command (from the repository root):

```
PYTHONPATH=src python3 -m unittest tests.test_ui_derive tests.test_ui_boundary tests.test_ui_api tests.test_ui_http
```

- **Focused UI suites: 83 tests, OK (0 failures, 0 errors).**
  - `tests/test_ui_derive.py` (37) — the documented display-level definitions,
    determinism, and the non-numeric-never-zero rule.
  - `tests/test_ui_api.py` (34) — in-process adapter: exact envelope parity for all
    ten Q modes vs the direct serving operations; fail-closed request handling;
    D38 CRUD + run; D39 record/list/show/delete; C2(a) (ordinary queries and saved
    runs never write history); withheld routes 404; byte-identical determinism.
  - `tests/test_ui_http.py` (8) — real HTTP server on an ephemeral loopback port:
    static assets, traversal whitelist, deterministic headers, adapter over the
    wire, saved/history flows, withheld-operation 404s, index startup (build when
    missing, idempotent reload).
  - `tests/test_ui_boundary.py` (structural, D23 §18(9)) — see §7.
- **Full suite:** `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"`
  → **Ran 888 tests — OK (skipped=14)**. The 14 skips are the pre-existing
  `D24_M2_ROOT`-gated real-baseline legs (unchanged; the real corpus is not present
  in this environment — 21.12 GB requirement, disk ~20.66 GB). 888 = 805 pre-TASK62
  + 83 new.
- **JS verification:** `node --check` (syntax OK) plus a Node harness executing the
  frontend's derivations against the same documented cases as
  `tests/test_ui_derive.py` (parity OK, including the "Latest 10Y" parse and the
  2016 leap-year day-number math).
- Live smoke: server started against the synthetic fixture package;
  `/api/status`, `/` (16,712 B HTML), `/app.css`, `/app.js`, Q3 (3 rows), Q4
  unknown-field fail-closed, saved create/list/run, history-after-run = 0 (C2(a)),
  explicit history record (seq 1, success), Q9 (4 archives), Q6 (absent calendar
  served as explicit state) — all correct.

No test claims anything beyond executed results. The fixture is synthetic
(`D24-FIXTURE-RUN`); nothing here represents the qualified M2 baseline.

## 7. D23 §18(9) UI-boundary proof (closing gate) — PASSED

1. **All UI data access uses authorized serving operations.** Every query executes
   through `execute_query_definition` (the CLI's single dispatch); saved/history
   through `serving.saved`/`serving.history`. Proven by exact envelope-parity tests
   for all ten Q modes (`test_ui_api`).
2. **No direct durable-data access in the presentation layer.** Structural proof
   (`test_ui_boundary`): `ui/api.py` contains no `open(`, no `baseline.path`, no
   file I/O; the only `os.path` usage is the store-root freshness helper
   (the UI's own class-(4) user-state root, AST-scoped); `ui/derive.py` is pure
   (no file/OS/clock/random imports or calls); `ui/serve.py` touches the package
   only through `open_baseline`/`build_index`/`write_index`/`load_index`/
   `rebuild_state` — the same serving entry points the CLI uses.
3. **No alternate query path.** `QUERY_MODES == sorted(SAVED_MODES)` (exactly ten,
   `test_ui_boundary`); the route table contains only `/api/status`,
   `/api/query`, `/api/saved[/…]`, `/api/history[/…]`; `ui/api.py` imports only
   `serving.*` + stdlib.
4. **No withheld capability exposed as active.** No route for logs/export/raw/
   processing exists (404 `route-not-found`, runtime-tested); the frontend contains
   no references to such endpoints and no `raw_line` rendering; every withheld
   mockup control carries an explicit disabled/unavailable marker (static-checked).
5. **No canonical data reinterpreted or mutated.** Rows are served as-is (parity
   tests); all display derivations are pure functions with documented definitions
   (tested); response bodies are canonical JSON (byte-identical determinism tests).
6. **Derived presentation values are deterministic and documented.** No
   clock/randomness in `ui/derive.py` (AST-proven) or the JS derivations
   (Node-parity smoke); documented definitions in §4.
7. **Existing contracts and persistence semantics remain intact.** The full
   pre-existing suite passes unchanged (888 total, 14 gated skips identical to
   pre-TASK62); no file under `src/serving/` was modified by this task.

## 8. Windows screenshot-acceptance handoff (explicitly NOT performed here)

Screenshot acceptance at 1536 × 1024 (spec §11.5/§17.2) requires a display and the
real corpus; the Arena environment has neither. **No screenshot-parity claim is
made from Arena-only inspection.** Handoff:

- **Screens to capture:** Dashboard, Data Explorer — at 1536 × 1024.
- **References:** Dashboard ↔ `evidence/10y historical engine.png`
  (SHA-256 `FA11F0E8…`); Data Explorer ↔
  `evidence/10y historical engine-data explorer.png`
  (SHA-256 `53F20B64…`).
- **Procedure (Windows host, repo checkout at the published session tip):**
  1. Set `PYTHONPATH=src`.
  2. Run `python -m ui.serve --package <M2 run root> --m2 --state <dir OUTSIDE the package> --saved-state <dir> --history-state <dir> --repo <repo root>` (the `--m2` pin joins the in-repo D01 inventory for Q9 and enables the verified status glyph; `--repo` enables Q10 evidence association).
  3. Open `http://127.0.0.1:8613/` in a browser at the 1536 × 1024 viewport.
  4. Capture both screens at equivalent scale and compare per spec §17.2
     (title bar, sidebar width, page heading, card geometry, panel gaps, table
     density, inspector width, chart proportions, status bar, typography, colors).
  5. Record material deviations and their causes; correct tokens centrally
     (`app.css`) before local exceptions; repeat.
- **Expected documented deviations (authority/data-driven, per spec §11.5):** the
  13 omissions/unavailable states in §5; dashboard values from the real served
  responses (never the mockup's illustrative values); identity-records KPI,
  run date/time, last-updated timestamp, export, logs, advanced query, reliable
  preset, raw/archive actions, four-bucket quality donut, and company id/name
  fields explicitly unavailable or disabled.
- **What remains to be verified on Windows:** visual comparison and token tuning
  for both screens; density/legibility at the target viewport; keyboard/focus
  review on the real host. The Windows M2 handoff pin in `_transfer_delivery/` was
  deliberately NOT changed by this task (per instruction); it must be re-pinned to
  the then-current session tip before any Windows qualification.

## 9. Changed files (this commit)

New (implementation):
- `src/ui/__init__.py`, `src/ui/derive.py`, `src/ui/api.py`, `src/ui/serve.py`
- `src/ui/static/index.html`, `src/ui/static/app.css`, `src/ui/static/app.js`
- `tests/test_ui_derive.py`, `tests/test_ui_api.py`, `tests/test_ui_http.py`,
  `tests/test_ui_boundary.py`
- `docs/implementation/TASK62_FIRST_RELEASE_UI_IMPLEMENTATION.md` (this record)

Carried in (design references, paths and hashes preserved; verified in §2):
- `docs/design/I4_HISTORICAL_DATA_ENGINE_UI_SPEC.md`
- `evidence/10y historical engine.png`
- `evidence/10y historical engine-data explorer.png`
- `evidence/I4_UI_MOCKUP_REFERENCES.txt`

Commit identity: the first commit published on the session branch carrying this
record (verified remotely after publication — see the TASK62 completion report).
No serving, engine, contract, or fixture files were modified.
