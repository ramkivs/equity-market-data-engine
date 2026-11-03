# TASK53 — NEXT-MILESTONE READINESS (roadmap reconciliation, Q4–Q6/saved-query assessment, execution plans)

**Mode:** read-only investigation and governance reconciliation. No
implementation authority is granted or exercised by this record. The D33 stop
on further implementation slices is preserved; this record plans, it does not
start.

## 1. Verified baseline and checkout disposition

| Item | Verified value |
|---|---|
| Repository / remote | `ramkivs/nse-historical-data-engine` @ GitHub `origin` (public) |
| `origin/main` | `69977017ffca944921f231d7904347bc582b6392` = D24 — **unchanged** (ls-remote, before and after this task) |
| Session branch `arena/9021d1a1-nse-historical-data-engine` | `059590b632b7e6b0aa4c0bc29381c5b36e87b0ab` = D33 — remote = local HEAD |
| Evidence branch `evidence/d26-real-m2-execution-20261009` | `0dda72bef051aa769340badda56997b42a1723f8` — unchanged |
| Unrelated session branch `arena/01a10c83-nse-historical-data-engine` | `db604063…` (PR #1) — observed, **not touched** |
| Chain verified | D24 `6997701…` → D25 `5c6a38f…` → D26 `8d58bac…` → D30a `4732316…` → D30b `14843ac…` → D31 `7bb8ebe…` → D32 `3af1a6a…` → D33 `059590b…` (each `merge-base --is-ancestor` = YES) |
| Checkout at task start | **25th sandbox `.git` rollback** (HEAD `89ce965…` shallow boundary, stale `M` files, lost remote-ref cache). Established non-destructive procedure: `fetch --unshallow` → D33 object present → full chain ancestry YES → **full worktree byte audit vs D33 tree (179 files: 0 missing, 0 differing)** → `update-ref`/`read-tree`/mixed `reset` (ref/index only). No clean/restore/force/branch-switch; no remote ref moved. Worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed) |

## 2. Sources examined (verified at this task; committed records)

- `docs/architecture/D23_FIRST_RELEASE_SERVING_IMPLEMENTATION_AUTHORITY_DECISION.md` — §7 decision, §8 authorized scope, §17 granted/withheld, §18 closure battery, §19 excluded/deferred.
- `docs/architecture/POST_I5_SERVING_INCREMENTAL_PRODUCT_ARCHITECTURE_AUTHORITY_DECISION.md` — D16-10 (Q1–Q10 + saved queries), D16-12 (first-release product scope).
- `docs/investigations/D22_FIRST_RELEASE_SERVING_IMPLEMENTATION_READINESS_INVESTIGATION.md` — §5 E-table (Q1–Q10 data backing), §6 (E2 saved-query scope).
- `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md` — §18 (remaining authorized work (a)–(d); withheld list).
- `docs/implementation/D30A…`, `D30B…`, `D31…`, `D32…`, `D33…` — slice contracts, test totals, remaining-slice statements.
- `docs/investigations/D25_REAL_M2_INTEGRATION_VERIFICATION.md`, `D26_REAL_M2_WINDOWS_EXECUTION_READINESS.md` — package-absence block (shortfall 462,417,776 B), G1/G2, Phase 1–3 handoff, `D24_M2_ROOT` gate.
- `docs/specs/D05_CANONICAL_MODEL_SPEC.md` — §3 field table (Q4 filterable fields; NON-ASSUMPTION on descriptive attributes).
- `tests/test_serving_m2_integration.py`, `src/serving/baseline.py` — gated-test inventory, `DEFAULT_M2_SPEC` pins.
- `docs/product/HISTORICAL_ENGINE_PRODUCT_AND_SERVING_ARCHITECTURE_INTENT.md` — §16 lifecycle.

**Reused (not re-investigated):** D24 qualification facts (not repeated — no
contradiction surfaced); D11/R6/D12/D14 evidence identities (verified in D33);
all prior slice test totals (reused from the records; no suite rerun — no
evidentiary reason).

**Newly verified this task:** the full session chain ancestry; remote ref
state; D23 §17/§18/§19 text; D22 E-table Q4–Q6/saved-query classification;
D05 §3 Q4 field vocabulary; the current gated-test inventory (9 legs);
D26 §8 handoff pin (still D24 `6997701…` — now stale, §6 below).

## 3. Current product/serving status (three dimensions kept separate)

| Capability | Implementation | Real-M2 qualification | Promotion |
|---|---|---|---|
| Baseline verify, class-(4) index (now 1.2), op-b rebuild, CLI (verify/build/query/dataset/quality/qualification/inventory/rebuild) | DONE (D24 + D30a/D30b/D31/D32/D33) | staged, gated (leg: full verify + rebuild reproducibility) | D24 promoted; rest not |
| **Q1** dataset/partition summaries | DONE (D30a) | gated leg present | not promoted |
| **Q2** date-range query | DONE (D30a) | gated leg present | not promoted |
| **Q3** instrument query | DONE (D24) | gated leg present | **promoted** (on main) |
| **Q4** segment/market-type/series/trading-status filtering | **NOT STARTED** (next slice, §5) | — | — |
| **Q5** identity/association query (w2/associations.jsonl) | NOT STARTED | — | — |
| **Q6** calendar query (w2/calendar.jsonl + metrics) | NOT STARTED | — | — |
| **Q7** record detail | DONE (D31) | gated leg present | not promoted |
| **Q8** data-quality views | DONE (D32) | gated leg present | not promoted |
| **Q9** archive inventory | DONE (D30b) | gated leg present | not promoted |
| **Q10** qualification/evidence views | DONE (D33) | gated leg present | not promoted |
| Saved queries / query history (D16-10; D22 E2: scope READY; state class (4), single-user, mechanism = implementation detail) | NOT STARTED | — | — |
| Dashboard / Data Explorer presentation (D16-11/12; D23 §17(b) authorized; technology UNDECIDED, selection delegated D23 §13/§14) | NOT STARTED | — | — |
| Product E2E acceptance / final release readiness (D23 §18 closure battery — items 2/5/7 pending real-package execution; item 9 UI-boundary proof pending UI) | NOT STARTED | pending G1/G2 | promotion = user's step |

Suite state at D33: **613 run / 604 passed / 9 skipped** (all 9 skips =
`D24_M2_ROOT`-gated real-package legs — never claimed passed). D23 closure
battery: items 2/5/7 PARTIALLY VERIFIED (G1/G2), remainder FULLY VERIFIED as
of D25/D26.

## 4. Smallest unresolved blocker

**No unresolved contract or authority blocker exists for the next serving
slice.**

* Q4, Q5, Q6 are each classified **READY BY EXISTING CONTRACT** (D22 §5 E1:
  as-published canonical-row fields / `w2/associations.jsonl` /
  `w2/calendar.jsonl` + `metrics.calendar_totals`).
* Saved queries/history: **READY BY EXISTING CONTRACT (scope)** (D22 §6 E2);
  D16-10/D16-12 fix them as first-release features persisted as serving state
  (4), single-user, mechanism = implementation detail.
* All of the above are inside D23 §8's authorized scope and D24 §18(b)'s
  standing remainder list — **no new authority decision is required** to
  implement them (same standing authority as D30a/D30b/D31/D32/D33).
* The only outstanding *environmental* blocker is the qualified M2 package's
  absence from Arena (D25 §6.2: 20,657,389,568 B available < 21,119,807,344 B
  required; Windows-held; not transferred). It blocks closure-battery items
  2/5/7 and therefore final release readiness, but it does **not** block the
  next implementation slice, which is fully testable on the fixture package
  with the real-package leg staged and gated (established pattern).
* Promotion to main remains the **user's separate step** (D23 §19 pattern;
  standing constraint) — not a blocker for continued session-branch work.

## 5. Next incomplete milestone

**Q4 — segment / market-type / series / trading-status filtering** is the
smallest justified next slice, by the same minimum-viable-slice precedent
D30b used to select Q9 ("one JSONL parser + one JSON parse … no index
extension; no w2"):

* Q4 filters on **as-published field values already present on canonical
  rows** — no new file class, no new parser, no w2 access: the D05 §3 field
  table pins the filterable vocabulary — `series` (both families), and the
  UDiFF-only descriptive attributes `segment` (`Sgmt`), `source` (`Src`),
  `instrument_type` (`FinInstrmTp`), subject to D05's NON-ASSUMPTION ("do not
  use as type filters beyond exact stored value") — plus the D16-10
  correlation-key fields (`listing_symbol` etc.). Semantics = exact-value
  equality/allowlist over as-published values; no inferred type semantics.
* Q5 (new w2/associations parser + D05 §3.3 interval semantics) and Q6
  (w2/calendar.jsonl + `metrics.calendar_totals` + `label_status` three-state
  semantics) are strictly larger slices. Saved queries require a class-(4)
  store design step (mechanism = implementation detail, but a design step
  nonetheless).
* No index extension is expected (candidate files are narrowed by the
  existing Q2 mechanism; filtering is a bounded row scan). If the
  implementation proves a per-file field census necessary, that is a minimal
  class-(4) extension under the D32 pattern (deterministic single pass,
  format version bump, fail-closed on unsupported formats) — decided at
  implementation time, not pre-committed here.

## 6. Plans (plan only — nothing implemented by this task)

### Plan 1 — next serving/API milestone (Q4 slice, new task under standing D23 authority)

* **Contract/authority:** D16-10 Q4; D23 §8/§9/§10/§17(a); D24 §18(b); D22 E1; D05 §3 (exact stored values only). No new authority.
* **Preconditions/dependencies:** session branch at D33 `059590b…`; standing D23 authority; fixture package (rows already carry the as-published fields).
* **Sources:** `src/serving/query.py` (new Q4 entry point beside Q2/Q3), `src/serving/cli.py` (Q4 mode of the existing `query` subcommand, mutually exclusive with the Q2/Q3/Q7 modes), `tests/` (new focused module; one `D24_M2_ROOT`-gated real-package leg), `docs/implementation/D34_…` record.
* **Acceptance (exact):** filters over as-published values only (exact-value equality / allowlist; no normalization, no inferred type semantics; absent values stay absent and never match); deterministic ordering; fail-closed envelopes (no partial results); Q1/Q2/Q3/Q7/Q8/Q9/Q10 regression (all unchanged); package byte identity before/after successful and failing operations; canonical JSON + deterministic ordering; full house suite with actual totals reported.
* **Focused tests:** filter correctness per field (legacy rows: `series`; UDiFF rows: `segment`/`source`/`instrument_type` + absent-value behavior on legacy rows), combined-filter semantics, empty-result validity, no-match vs malformed-input distinction, determinism, regression, byte identity.
* **Real-M2:** required as a **staged, gated** leg (`D24_M2_ROOT`), never claimed passed in Arena.
* **Publication:** one focused FF commit to the session branch; independent remote verification (commit/parent/tree/paths/blobs); main untouched.
* **Out of scope:** Q5, Q6, saved queries, UI/transport, index changes unless proven necessary (per §5), incremental ingestion, D21 machinery, raw content, any promotion.

### Plan 2 — real-M2 qualification (reuses D24/D25/D26; no re-creation)

* **Gated legs now staged (9):** `M2RealPackageIntegrationTests` — full verify with `DEFAULT_M2_SPEC`; Q1; Q2; Q3; Q7; Q8; Q9; Q10; rebuild reproducibility. Plus the four `PinIdentityTests` (run without the package — pass in Arena).
* **Mechanism:** `tests/test_serving_m2_integration.py` is `@unittest.skipIf(not D24_M2_ROOT)`; `setUpClass` opens `os.environ["D24_M2_ROOT"]` with the pinned `DEFAULT_M2_SPEC` (full verify-01..07 incl. per-file digests) into a temp state dir. D33 added the optional `D24_REPO_ROOT` (evidence association for the Q10 leg).
* **Inputs:** the 21,119,807,344-byte qualified package at `G:\My Engines\I4_RUNS\i4-20261008-M2` (Windows; runbook run-root convention; failed run root `i4-20261007` preserved evidence — do not touch); ~21 GB free disk; state dir outside the package; Python 3 stdlib only.
* **Execution domain:** **Windows only.** Arena cannot host the package (capacity block, D25 §6.2); no Windows/PowerShell execution from Arena (standing constraint); the package is not transferred into Arena.
* **Stale pin — must be re-pinned at execution:** D26 §8 Phase 3 pins the scratch checkout to D24 `69977017ffca944921f231d7904347bc582b6392`. The current serving implementation is D33 `059590b632b7e6b0aa4c0bc29381c5b36e87b0ab` (five serving slices beyond D24). The handoff must pin the scratch checkout to the session HEAD (fetch the session branch, checkout `059590b…`, verify HEAD) so all 9 legs exercise the current implementation.
* **Evidence preservation (D26 convention):** full console output + each step's exit code; pre/post package identity re-verification (manifest `e7c7e4c8…`, 4,948 files, 21,119,807,344 B, run/composite/engine/runner/corpus identities) as the immutability proof; direct read access, no package copy.
* **Independent verification & publication:** results recorded in a durable evidence commit (evidence-branch pattern per D25/D26) with package identity re-pinned from the in-repo D11 evidence; closure-battery items 2/5/7 become FULLY VERIFIED only from that evidence; no gated test is described as passed until actually executed against the qualified package.

## 7. Settled decisions (must not be reopened)

* D23 §17 WITHHELD (each requires its own future explicit authority): incremental ingestion (D16-13(2)); requalification migration (D16-13(4)); per-instance CHANGED resolution (D21 §22); raw-content serving (D16-13(6)); any engine/canonical/contract alteration; any scope change away from single-user.
* D21 §14 permanent disposition of the D21-03a CHANGED record (registry absent in the M2-only release; explicitly-absent representations in Q8/Q9/Q10).
* D05 semantics (as-published values; non-gating flags; descriptive-attribute NON-ASSUMPTION; `GATING_FLAG_NAMES = ()`).
* DEC-1/eligibility features: DEFERRED (D16-10).
* TECHNOLOGY for UI/transport: UNDECIDED; selection is delegated within D23 §13/§14 bounded criteria and recorded at implementation — it is not a pending user decision.
* Promotion of session-branch work to main: the user's separate step.

## 8. Authority and scope boundaries (this task)

Read-only investigation; the only mutation is this record. No implementation
files, package, fixture, or evidence file changed. Main and the evidence
branch untouched. No unrelated branch touched. No Q4–Q6/saved-query/UI
implementation started. No real-M2 test executed or claimed passed. No
production activity.

## 9. Remaining uncertainties

* Whether Q4 needs an index extension (decided at implementation time; §5).
* The exact Q4 mode interface on the shared `query` subcommand (CLI detail;
  established mutual-exclusion convention applies).
* Windows-side execution scheduling for Plan 2 (user environment; not an
  Arena decision).
* UI technology selection (implementation-time, delegated, recorded).

## 10. Disposition

**READY FOR NEXT INVESTIGATION** — the next serving slice (Q4) is fully
authorized under standing D23 authority with no unresolved contract or
authority decision; it is defined and planned in §6 Plan 1 for a separate
implementation task. Two user-side tracks are explicitly separate and not
blockers to that slice: (a) Plan 2 real-M2 execution on the Windows
environment (re-pin the D26 handoff to D33 `059590b…` first), and (b)
promotion of the session branch to main (user's step).
