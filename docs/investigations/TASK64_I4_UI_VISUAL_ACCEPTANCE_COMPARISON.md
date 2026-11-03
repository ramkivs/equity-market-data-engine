# TASK64 — I4 UI VISUAL-ACCEPTANCE COMPARISON (EVIDENCE RECORD)

## 1. Task identity and mode

**TASK64** compares the published Windows UI captures against the original mockup
references for the first-release Dashboard + Data Explorer. **Mode: read-only
investigation and verification.** No implementation authority. No M2 mutation. No
merge to main. No authoritative product decision is published by this record; the
final disposition below is an **acceptance-evidence determination** (whether the
returned captures meet the spec + reference acceptance bar), not a product
acceptance/rejection decision. Arena did **not** inspect the Windows filesystem and
does not claim to; all package facts below come from in-repo evidence plus the
user-reported Windows script result.

Sandbox note: the 36th sandbox `.git` rollback was repaired at task start
(non-destructive, per the established pattern: value-audit → `update-ref` →
`read-tree` → mixed reset; byte audit vs the prior session tip: 212 files,
0 missing, 0 differing; worktree clean except the pre-existing untracked
`_transfer_delivery/`).

## 2. Verified repository refs and commits

| Item | Value | Verification |
|---|---|---|
| UI implementation baseline | `1f86d88749357cad15f22c94c648d3e6d0f7a294` | published in TASK62; re-verified as the evidence commit's parent (below) |
| Evidence branch | `evidence/i4-ui-visual-acceptance-2026-10-10` | remote ref = `1b43e0d86c9f605d1c33b6a47b37865496043c9a` (ls-remote + explicit fetch) |
| Evidence commit | `1b43e0d86c9f605d1c33b6a47b37865496043c9a` | author Ramaki, 2026-10-10 19:47:38 +0530, subject "Add I4 UI visual acceptance screenshots" |
| Evidence commit parent | `1f86d88749357cad15f22c94c648d3e6d0f7a294` | exactly the declared UI baseline; `1f86d88` is an ancestor of the evidence commit |
| Evidence commit changed paths | exactly 2 additions: `evidence/I4_UI_CAPTURE_dashboard_1536x1024.png` (195,150 B), `evidence/I4_UI_CAPTURE_explorer_1536x1024.png` (193,027 B) | `git diff --name-status` parent→commit; the rest of the tree is byte-identical to `1f86d88` |
| Mockup reference branch | `docs/i4-ui-mockup-references` | remote ref = `726b1c3611e77640c67d86a4ee72a09cd3415b56` (unchanged since TASK62) |
| `origin/main` | `69977017ffca944921f231d7904347bc582b6392` (D24) | untouched; no merge performed |

## 3. Screenshot dimensions and SHA-256 (independently computed from the fetched blobs)

| File | Bytes | Dimensions | SHA-256 | Expected | Result |
|---|---|---|---|---|---|
| `evidence/I4_UI_CAPTURE_dashboard_1536x1024.png` | 195,150 | 1536×1024 | `05e6bc0f3dadd6d4d0664632d50e6e1499eb990426e8d76c0e1e62374932f1c4` | `05e6bc0f…f1c4` | **MATCH** |
| `evidence/I4_UI_CAPTURE_explorer_1536x1024.png` | 193,027 | 1536×1024 | `35401ce4e82a82c516ce29ca3fe68ce1e95281a441669a53a0188b77f4ed0eed` | `35401ce4…eed` | **MATCH** |

Dimensions read from the PNG IHDR of the exact published blobs. Both captures
conform to the required 1536×1024 canvas.

## 4. Mockup provenance and hashes (inspected from `726b1c36`, `evidence/`)

| File | Bytes | SHA-256 | Manifest cross-check |
|---|---|---|---|
| `evidence/10y historical engine.png` (Dashboard reference) | 1,773,767 | `fa11f0e867d0f8aa1df41b3ab88c51d27ce2ccd50e790e5181ecf45b2aa1af85` | matches `I4_UI_MOCKUP_REFERENCES.txt` and the TASK62 record; non-authoritative design reference |
| `evidence/10y historical engine-data explorer.png` (Data Explorer reference) | 1,842,012 | `53f20b6484f02ac28f4fdf5f80125b38e138e256ebf8ba5d26cfb3ee9b46bd19` | matches the manifest and the TASK62 record; non-authoritative design reference |
| `evidence/I4_UI_MOCKUP_REFERENCES.txt` | 670 | `b83ff8a141f65fabd28c7ab10eebf390809a3a28906e7017c4b206878d6b9f27` | pins the two mockups with byte counts + hashes; base commit `6997701…`, spec commit `20bf8238…` |

The authoritative specification is `docs/design/I4_HISTORICAL_DATA_ENGINE_UI_SPEC.md`
(blob `6caae93b…`, sha256 `aca5eca9…2165`, byte-identical in both the evidence and
mockup trees). Per the manifest's own declaration, the mockups are design references
only; classifications below cite the spec where it is normative.

## 5. Dashboard comparison (capture vs `10y historical engine.png`)

**What the capture shows (observed):** title bar "Local Historical Data Console" +
subtitle; top-right "connected · run i4-20261008-M2" (green) **and** a red alert
`unresolved-scan — unresolved-scan: w2/unresolved.jsonl line 11 without a state`;
header "10-Year NSE Historical Data" + read-only subtitle; "Run New Processing" and
"Verify Existing Run" disabled with "unavailable — withheld in the first release";
the three regions **Rows by Year**, **Archives by Exchange Segment**, **Data
Coverage** and the **Archive Browser** table each contain the same red
unresolved-scan error box instead of data; **no KPI card row is rendered at all**;
the run-identity block (Run ID / Run Date / Engine / Archives) from the mockup
header is absent; Engine Logs shows the correct authority-driven unavailable
message; Archive Detail is empty; status bar: `state: ready | run: i4-20261008-M2 |
engine: … | archives: … | rows: …` with literal `…` placeholders for the last three
values, right side "read-only serving view — no live data, no processing".

**Why (code-verified, `src/ui/static/app.js` `loadDashboard()`):** the dashboard
issues `Promise.all([Q1, Q6, Q8, Q9, Q10])`; any single rejection rejects the whole
batch, after which (a) all four regions are set to the error box, (b) the top alert
is set, (c) `renderDashboard()` never runs — so `renderRunSummary()`, `renderKpis()`
and `renderArchives()` are skipped (hence no KPI row, no run block, no table), and
(d) `updateStatusBar()` finds `S.dash.q10`/`S.dash.q1` unpopulated, leaving the
`…` placeholders. Only Q8 actually failed (the error text is the Q8 check); Q1/Q6/
Q9/Q10 are contract-valid queries over this package but their results were never
stored or rendered.

**Mockup-only content in the reference:** 5 KPI cards (2,462 / 5,689,949 / 2,462 /
2,462 / 0 — illustrative), run-identity block with "COMPLETED" badge, populated bar
chart, segment donut with legend, data-coverage list, archive table with rows,
archive-detail panel with SHA256 + four view buttons, populated engine-log panel
with "Open Log Folder", and a status bar with Memory/Disk Free/Windows 11
telemetry.

## 6. Data Explorer comparison (capture vs `10y historical engine-data explorer.png`)

**What the capture shows (observed, initial/unfiltered state):** page heading +
subtitle "Contract-driven queries (Q1–Q10), record detail, provenance, and quality
over the served package"; right meta panel: "Datasets: single qualified package (no
dataset selector — one authorized dataset)", **"Partitions: unavailable"**,
**"Total rows: unavailable"**, "Last updated: unavailable — the serving contract
publishes no last-updated timestamp (never fabricated)"; tabs Query Builder (active)
/ Advanced Query (unavailable) / Saved Queries / Query History; **no saved-query
sidebar** (the mockup's left list with 7 shortcut names + "New Query" is absent);
MAIN FILTERS = Query mode dropdown (Instrument (Q3) selected) + Symbol (exact) +
Series (exact) + Year (optional) + Run/Reset/Save Query; QUICK FILTERS pills match
the mockup set with "Reliable Only" disabled; Query Results empty state ("Run a
query to see served rows."); Record Inspector empty state; Price Chart / Yearly
Summary empty states; **Data Quality (Q8) panel shows the unresolved-scan error
box**.

**Why the "Partitions/Total rows: unavailable" pills:** `renderDatasetSummary()`
(`app.js:1351`) computes the summary from `S.dash.q1/q6/q9` — the dashboard state
that was never populated because of the same Q8 rejection (Q1's `row_count` and
partitions are contract-valid and servable; the values are suppressed by error
propagation, not by the serving contract). "Last updated: unavailable" is correct
authority-driven behavior (no contract timestamp exists).

**Mockup-only content in the reference:** the mockup depicts a mid-query state (TCS,
2020; 1,243 records; populated table, record-details panel with Provenance/Raw
Hash, price chart, yearly summary, quality donut, dataset dropdown, user chip
"Ramki", Settings/Help affordances, populated status bar). The acceptance protocol
took the capture in the initial unfiltered state, so the data-populated Explorer
states (result table columns, record detail, chart) are **not yet visually
verified** — a coverage gap recorded in §10.

## 7. Material differences and classifications

Legend: AUTHORITY-DRIVEN = required/allowed by the governing spec/contract (the
mockup is non-authoritative); DATA-DRIVEN = real corpus values vs mockup
illustratives, or capture-state differences; UNEXPECTED = not supported by
authority or data — a defect or gap; UNDETERMINED = evidence insufficient.

| # | Difference (capture vs mockup) | Classification | Evidence |
|---|---|---|---|
| D1 | All four Dashboard regions + top alert show `unresolved-scan … line 11 without a state` instead of data | **UNEXPECTED** (defect; see §8) | reproduced on the authorized fixture run (§8.3); root cause = serving Q8 parser vs runner-published record schema |
| D2 | KPI card row (spec §5.2: five cards, "missing metrics should show Unavailable") entirely absent | **UNEXPECTED** (error-driven consequence of D1: `renderKpis()` never runs) | `app.js` `loadDashboard()` catch path; spec §5.2 |
| D3 | Run-identity header block (Run ID/Run Date/Engine/Archives) absent | **UNEXPECTED** (error-driven consequence of D1) | `renderRunSummary()` never runs |
| D4 | Status bar `engine: … / archives: … / rows: …` literal placeholders | **UNEXPECTED** (error-driven consequence of D1; values exist in Q10/Q1) | `updateStatusBar()` guarded on `S.dash.q10`/`S.dash.q1` |
| D5 | Explorer "Data Quality (Q8)" panel shows the error box | **UNEXPECTED** (D1 root cause, independent Q8 call) | `loadQuality()` → same Q8 check |
| D6 | Explorer meta "Partitions: unavailable", "Total rows: unavailable" | **UNEXPECTED** (error-driven: dashboard state never populated; values servable via Q1) | `renderDatasetSummary()` source |
| D7 | Title bar reads "Local Historical Data Console" (+subtitle) instead of the spec's `I4 Historical Data Engine (10-Year NSE Corpus)` | **UNEXPECTED** (spec §4.1 specifies the title string literally; mockup matches the spec) | spec §4.1; both images |
| D8 | Saved-query sidebar (spec §6.9: list + New Query, D38 behavior, empty state that guides) absent in the Explorer | **UNEXPECTED** (spec §6.9 requires it incl. its empty state; TASK62 omission #13-style seeding rules only forbid the mockup's shortcut names, not the sidebar) | spec §6.9; capture |
| D9 | Query Builder is mode-based (Query mode dropdown over the Q1–Q10 contract + per-mode fields) vs the mockup's integrated filter grid (Date Range/Segment/Trading Status/Exchange Segment + optional Filters table) | **AUTHORITY-DRIVEN** (spec §6.2: "Query Builder uses the established query contract"; §6.3's grid is "reference controls"; the mockup's exact presentation is non-authoritative; no alternate query path introduced) | spec §6.2/§6.3; `app.js` MODE map = Q1–Q10 |
| D10 | "Run New Processing" / "Verify Existing Run" disabled + "unavailable — withheld in the first release" | **AUTHORITY-DRIVEN** (TASK62 omissions #1/#2) | TASK62 record §5 |
| D11 | Six non-first-release nav items carry "unavailable" badges | **AUTHORITY-DRIVEN** (TASK62 omission #3) | both images |
| D12 | Engine Logs panel: "Unavailable — no authorized log-serving operation exists in the first-release serving contract (D16-12; D23 §19). Log contents are never fabricated." | **AUTHORITY-DRIVEN** (TASK62 omission #7) | both images |
| D13 | No dataset selector (single qualified package label instead) | **AUTHORITY-DRIVEN** (spec §6.1: selector only if multiple datasets; TASK62 omission #12) | spec §6.1 |
| D14 | "Last updated: unavailable — the serving contract publishes no last-updated timestamp (never fabricated)" | **AUTHORITY-DRIVEN** (no contract timestamp; never fabricated) | both images |
| D15 | "Reliable Only" quick filter disabled | **AUTHORITY-DRIVEN** (TASK62 omission #6) | both images |
| D16 | "Advanced Query" tab marked unavailable | **AUTHORITY-DRIVEN** (TASK62 omission #4; spec §6.2 forbids an alternate path) | both images |
| D17 | No Memory/Disk Free/OS telemetry in the status bar | **AUTHORITY-DRIVEN** (spec §4.3: such values only "if genuinely available and appropriate"; never invented) | spec §4.3 |
| D18 | No user chip "Ramki", no Settings/Help affordances | **AUTHORITY-DRIVEN** (spec §4.1: no fictitious identity/user-management behavior; "if permitted") | spec §4.1 |
| D19 | Data Quality area: mockup's 4-bucket donut (Reliable/Uncertain/Missing/Excluded) replaced by the served Q8 flag census (currently error state, D5) | **AUTHORITY-DRIVEN** (TASK62 omission #11) + **UNEXPECTED** overlay (D5 error state) | `renderQuality()` text; TASK62 record §5 |
| D20 | Explorer capture is the initial unfiltered state vs the mockup's mid-query state (TCS 2020, 1,243 records) | **DATA-DRIVEN** (capture protocol: filters left empty; the mockup illustrates a query state, not the initial state) | protocol + both images |
| D21 | All numeric content (KPI values, chart, table rows, counts) absent in the capture | **DATA-DRIVEN** where data-driven rendering is intended, but **UNEXPECTED** insofar as it is caused by D1 (values are servable; see D2/D4/D6) | §5/§6 |
| D22 | Capture format: single-page application — each 1536×1024 viewport capture contains both the Dashboard and Data Explorer regions (overlapping content between the two PNGs) | **UNDETERMINED/minor** (no spec violation found; the spec does not pin capture mechanics; noted for the record) | both images |
| D23 | Top-right "connected · run i4-20261008-M2" service indicator (absent in mockup) | **AUTHORITY-DRIVEN** (shows only authorized values from `/api/status`; within spec §4.1 discretion) | `/api/status` shape |
| D24 | Status-bar wording "state: ready / read-only serving view — no live data, no processing" vs "I4 Engine Ready" | **UNEXPECTED (minor, wording)** — spec §4.3 does not pin strings; no functional impact | both images |
| D25 | No UNDETERMINED items beyond D22 — every material difference is accounted for by evidence | — | — |

## 8. The observed Dashboard error: `unresolved-scan … w2/unresolved.jsonl line 11 without a state`

### 8.1 Where the error comes from (exact code path)

`src/serving/quality.py` (Q8 data-quality view, D32 slice) — `parse_unresolved()`:
`w2/unresolved.jsonl` (runner-written, class-(3) provenance/evidence) is parsed
**only when present and valid**; absence is a legitimate no-records state. A present
file whose line is unparseable, not a record, lacks a non-empty string `kind`, or
lacks a string `state` fails closed. The exact raised message is
`QueryError("unresolved-scan", "w2/unresolved.jsonl line %d without a state")`
(`quality.py:114`) — byte-identical to the captured text.

### 8.2 Why the real package's line 11 triggers it (evidence chain, no assumption)

1. **The file is a manifest-authorized member of the qualified package.**
   In-repo D11 evidence (`evidence/D11_REPLAY_QUALIFICATION_20261009/D11_E1_E10_TRANSFER_20261009.tar.gz`,
   tracked; package A = `G:\My Engines\I4_RUNS\i4-20261008-M2` per
   `A.EVIDENCE_FACTS.json` `out_root`): `A.PACKAGE_FILES.tsv` lists
   `w2/unresolved.jsonl` — 2,527 bytes, sha256
   `62B2BC0CF0C1B97C24EB46EAB4978228050F3C9DAD1A8A9E1975E8BE8E3006A9`; the replay
   package B lists byte-identical size+hash. So the file's presence is
   canonical, not corruption.
2. **The code that wrote it is the code in this repository.** The package's
   `RUN_RECORD` pins `runner_sha256 = f3ebf624…` and `engine tool_sha256 =
   d3269b73…`; live-computed in-repo fingerprints at the session tip
   (`i4_identity.runner_fingerprint()`, `engine_fingerprint()`) **match both
   exactly**. The writer is `tools/i4_runner/i4_runner.py::_write_w2` /
   `_unresolved_records`.
3. **The runner's record set contains exactly one record kind without a `state`
   key.** `_unresolved_records()` appends, in order: N × `governance-dependency`
   (has state), 1 × `calendar-label-status-counts` (has state), M ×
   `calendar-unresolved-date` (has state), 1 × `identity-non-promotion` (has
   state), and — last, when the calendar is non-empty (always, for a real corpus) —
   1 × **`cross-era-boundary-residual`, which has only `kind`, `first_date`,
   `last_date`, `note` — no `state`** (`i4_runner.py:641-652`). The runner's own
   test (`tests/test_i4_runner.py:533`, `test_w2_outputs_and_unresolved_state_are_present`)
   asserts the presence of that kind — and never asserts `state` on it.
4. **The observed line number is the file's last line.** The scan fails at the
   *first* violating line; the only kind that can lack `state` is the last
   appended record. "line 11 without a state" ⟹ the file has exactly 11 lines:
   N + 1 + M + 1 + 1 = 11 ⟹ N + M = 8. Contract `D07-OPEN-8`
   (`src/nse_engine/contract.py`) names exactly **three** unexplained calendar
   dates for this corpus (2024-11-20, 2025-10-20, 2026-01-15) ⟹ M = 3 ⟹
   N = 5 governance dependencies with non-zero row counts (the exact five ids are
   not verifiable from in-repo evidence — the file bytes are not published — and
   are not needed for the diagnosis).
5. **Reproduced on the authorized fixture corpus (not the real corpus).**
   Driving the repository's own runner fixture
   (`tests/test_i4_runner.py` `RunPackageTests`) to a temp run root produced a
   4-line `w2/unresolved.jsonl` whose line 4 is `cross-era-boundary-residual`
   without `state`; pointing the serving Q8 `parse_unresolved()` at that fixture
   package raised `QueryError(check='unresolved-scan',
   'w2/unresolved.jsonl line 4 without a state')` — the identical failure mode,
   with the line number tracking the final line (4 in the fixture, 11 in the real
   corpus).

**Diagnosis (evidence-backed, not a product decision):** this is a
**serving/runner contract mismatch introduced by the D32 Q8 slice**. The Q8 parser
codifies "every record carries `kind` + `state`", but the canonical,
replay-qualified package (immutable; never to be modified or requalified)
publishes one record kind without `state`. The mismatch was invisible in both
test suites: the serving fixtures never contain `w2/unresolved.jsonl`
(`tests/test_serving_quality.py:221` asserts absence; the present-file tests
hand-craft valid records at `:245`), and the runner fixtures assert the stateless
kind without checking the serving parse. Consequence: **the Q8 data-quality view
can never succeed over any run package the pinned runner produces**, and — via
the dashboard's `Promise.all` — one Q8 failure blanks the KPI row, run block,
archive table and status-bar values and turns four Dashboard regions plus the
Explorer Q8 panel into error boxes.

**Does existing evidence support the expected (data-populated) behavior?** No —
the expected behavior (Dashboard regions rendered from authorized Q1/Q6/Q9/Q10
results; Q8 panel showing the served census) is currently unachievable over the
qualified M2 baseline. Further investigation is *not* needed for the diagnosis
(the chain above is closed and reproduced); what is needed is a follow-up task
with implementation authority (see §10).

## 9. Package-verification status and limitations

**Existing read-only package-verification evidence IS available (in-repo,
tracked):** the D11 replay-qualification verdict
(`evidence/D11_REPLAY_QUALIFICATION_20261009/D11_R6_REPLAY_QUALIFICATION_VERDICT.json`,
2026-10-09) — all checks PASS, including: RQ-01 `verify_package` (verify-01..07,
full per-file digests) on package A = `G:\My Engines\I4_RUNS\i4-20261008-M2`;
RQ-13 byte-exact replay A↔B (4,948 files, `first_difference: null`); identity
bindings RQ-03..08 (run id `i4-20261008-M2`; engine `d3269b73…`; runner
`f3ebf624…`; composite `9609c7fc…`; corpus `54d81507…`; manifest `e7c7e4c8…`;
4,948 files / 21,119,807,344 B; counts 2,462 members / 3,692 observations / 0
quarantined / 5,689,949 rows). The D11 package listing additionally pins
`w2/unresolved.jsonl` (size + sha256) as a manifest member (§8.2.1).
Corroborating capture-time evidence: the UI server's `open_baseline(verify_files=True)`
full verification necessarily passed before the server bound (the captures show
`state: ready` / "connected · run i4-20261008-M2"), and the user reports the
TASK63 Windows script gates (root, manifest sha256, run id, port) all passed.

**Limitations (recorded, not assumed away):**
- Arena has no Windows access and did not inspect the Windows filesystem; the
  capture-time verifications above rest on the user-reported script result and the
  server's ready state, not on an Arena-executed check.
- The evidence branch contains only the two PNGs — the TASK63 return bundle
  (server ready line, `/api/status` JSON, full console output incl. the
  post-capture `serving verify`) was not published to the branch.
- The actual bytes of `w2/unresolved.jsonl` (2,527 B) are not published in-repo
  (only its size + hash in the D11 listing), so N = 5 / the exact dependency ids
  are derived, not read.

**Minimum additional evidence to close the gap** (optional; the D11 verdict
already establishes package verification): one Windows console capture of
`python -B -m serving verify --package 'G:\My Engines\I4_RUNS\i4-20261008-M2' --m2`
(expected: exit 0; `checks_passed` verify-01..07; `manifest_sha256 e7c7e4c8…`;
`total_bytes 21,119,807,344`; `run_id i4-20261008-M2`) — exactly the TASK63
runbook Phase D step.

## 10. Final disposition and next action

**Disposition: FAIL — as an acceptance-evidence determination (not a product
decision).** The returned captures do not meet the spec + reference acceptance
bar. Dominant cause: the Q8 contract mismatch (§8), which renders the Dashboard
in an error state over the qualified M2 baseline (reproduced; spec-required KPI
row, run block, archive table and data regions never render — D1–D6). Additional
independent findings: title-bar string deviates from spec §4.1 (D7); the spec
§6.9 saved-query sidebar is absent (D8). DATA-DRIVEN and AUTHORITY-DRIVEN
differences (D9–D20, D23–D24) are correctly implemented per the governing
contracts. No code was modified; the M2 package was not touched; no merge was
performed; no parity is claimed.

**Smallest necessary next actions (require implementation authority; none granted
here):**
1. Reconcile the Q8 parser with the runner-published record schema — the package
   is canonical/immutable, so the conforming side is the serving parser (accept
   the published `cross-era-boundary-residual` record as-is, served as published);
   add a regression test that runs the Q8 scan against a **runner-produced**
   fixture package (the exact gap that let the mismatch through).
2. Isolate dashboard region errors: a failed Q8 must not suppress Q1/Q6/Q9/Q10
   rendering (KPI row, run block, archive table, status-bar values) — per-query
   error containment in `loadDashboard()`.
3. Restore spec §4.1 title text and the spec §6.9 saved-query sidebar (D38
   behavior, guided empty state, no seeded mockup names).
4. Fresh Windows capture set after the fix: initial state **plus** a data-populated
   Explorer state (e.g. a Q3 instrument query) to verify the result table, record
   detail (Q7), price chart and Q8 census rendering.
5. Optional: publish the TASK63 Phase D `serving verify` console output to close
   the §9 limitation.

## 11. Explicit non-drift statement

No application code, test, or mockup was modified; no M2 package operation was
performed (the only runner execution was the repository's own fixture test
mechanism, on the fixture corpus, in a temp dir, per the standing G-I4 boundary);
the evidence and mockup branches were fetched read-only and not merged or moved;
`origin/main` remains `6997701…` (D24); the only tracked mutation of this task is
this record; no authoritative product decision is published; visual parity is not
claimed.
