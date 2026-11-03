# D37 — Saved queries & query history: contract, persistence design, and implementation readiness

**Mode:** read-only investigation and governance reconciliation. **No implementation
authority is granted or exercised by this record.** No code, no store, no fixture or
package file was modified by this task.
**Publication scope:** session branch only. No main promotion.

---

## 1. Verified baseline and checkout disposition

| Item | Verified value |
|---|---|
| Repository / remote | `ramkivs/nse-historical-data-engine` @ GitHub `origin` (public) |
| `origin/main` | `69977017ffca944921f231d7904347bc582b6392` = D24 — **unchanged** (ls-remote, before and after) |
| Session branch `arena/9021d1a1-nse-historical-data-engine` | `4e0afde6f7fe499fa3e81d7596a2c62a4b63d2eb` = D36 — remote = expected |
| D36 parent | `1a7c713cfb36b15df4315eb7fa36f972bbb27c28` = D35 |
| Task 53 readiness record | `3a0fd6ec01c8a62ae1c2b75204033e5387d1392f` |
| Evidence branch `evidence/d26-real-m2-execution-20261009` | `0dda72bef051aa769340badda56997b42a1723f8` — unchanged |
| Unrelated session branch `arena/01a10c83-nse-historical-data-engine` | `db604063…` (PR #1) — observed, **not touched** |
| Chain verified | D24 `6997701…` → D25 `5c6a38f…` → D26 `8d58bac…` → D30a `4732316…` → D30b `14843ac…` → D31 `7bb8ebe…` → D32 `3af1a6a…` → D33 `059590b…` → Task 53 `3a0fd6e…` → D34 `922e26c…` → D35 `1a7c713…` → D36 `4e0afde…` (each `merge-base --is-ancestor` = YES) |
| Checkout at task start | **29th sandbox `.git` rollback** (HEAD `89ce965…` shallow boundary, stale `M` files, lost remote-ref cache). Established non-destructive procedure: `fetch --unshallow` → D36/D35/T53 objects present → full chain ancestry YES → **full worktree byte audit vs D36 tree (186 files: 0 missing, 0 differing)** → `update-ref`/`read-tree`/mixed `reset` (ref/index only). No clean/restore/force/branch-switch; no remote ref moved. Worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed) |

## 2. Sources examined (verified verbatim at this task; committed records)

- `docs/architecture/POST_I5_SERVING_INCREMENTAL_PRODUCT_ARCHITECTURE_AUTHORITY_DECISION.md` — **D16-07** (durable persistence boundary; class-(4) definition), **D16-09** (serving/query boundary + invariants), **D16-10 item 5** (Q1–Q10 + saved queries), **D16-11** (UI boundary), **D16-12 item 5** (first-release scope), §12/§13 (query/product scope, non-goals), §14 (TECHNOLOGY = UNDECIDED).
- `docs/architecture/D23_FIRST_RELEASE_SERVING_IMPLEMENTATION_AUTHORITY_DECISION.md` — §8 (authorized scope), §13/§14 (technology-selection delegation + 9 binding constraints), §17 (granted/withheld), §18 (closure battery, items 3/7/8/11), §19 (excluded/deferred).
- `docs/investigations/D22_FIRST_RELEASE_SERVING_IMPLEMENTATION_READINESS_INVESTIGATION.md` — §6 **E2** (saved-query scope assessment), §7 (delegated operations).
- `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md` — §5 (technology selection exercised, incl. MD-10 grading and the explicitly-open persistent-store concern), §18 (remaining authorized work (b)).
- `docs/investigations/D08_I3_OUTPUT_PERSISTENCE_CONTRACT_DECISION.md` — **MD-10** (the 7 store-selection criteria; STORAGE TECHNOLOGY = UNDECIDED).
- `docs/investigations/TASK53_NEXT_MILESTONE_READINESS.md` — §3/§4 (saved-query status: NOT STARTED; "requires a class-(4) store design step"; no new authority required).
- Current implementation (read-only): `src/serving/index.py` (state layout, `write_index`/`load_index` conventions, `INDEX_FORMAT` versioning, fail-closed stale/corrupt handling), `src/serving/rebuild.py` (delegated operation (b): `KNOWN_STATE_FILES = {serving_index.json, serving_index.sha256}`; refuses unknown files; delete-and-rebuild), `src/serving/cli.py` (the six `query` modes + Q1/Q8/Q9/Q10 subcommands), `src/serving/__init__.py` (boundary statement), `.gitignore` (`serving-state/`, `*.db`, `*.duckdb`).
- `docs/product/HISTORICAL_ENGINE_PRODUCT_AND_SERVING_ARCHITECTURE_INTENT.md` — §9 (Data Explorer direction lists "saved queries; query history" — product surface, no further semantics).
- `docs/implementation/D36_Q6_CALENDAR_QUERIES.md` — current Q6 state (the prior milestone; next authorized slice per D24 §18(b) is saved-query state).

**Reused (not re-investigated):** D24 qualification facts; D11/R6/D12/D14 evidence
identities; all prior slice test totals; the historical-engine record (no material
contradiction surfaced that affects the persistence decision).

## 3. Contract findings (what the governing records actually fix)

### 3.1 Governing statements, verbatim (key excerpts)

* **D16-10 item 5:** "**Saved queries and query history** are first-release product
  features, persisted as serving state (4) (single-user; mechanism = implementation
  detail)."
* **D16-12 item 5:** "**Saved queries + query history** (serving state 4)." (first-release
  scope)
* **D16-07 (class (4)):** "**(4) Serving/derived state** — indexes, rollups,
  query accelerants, **saved-query stores**. Owner: the serving boundary. **Always a
  pure derivation of (1)+(2)+registry; rebuildable at any time from them with no loss —
  deleting (4) is never a data event.** Conflict rule: if (4) ever disagrees with
  (1)/(2)/(3), (1)/(2)/(3) win and (4) is rebuilt. Technology: NONE selected —
  TECHNOLOGY = UNDECIDED (MD-12 stands) … the qualified M2 package (1) and any future
  serving persistence (4) remain **distinct**."
* **D16-09:** the serving layer "owns query execution, result shaping, and derived
  serving state (4)"; invariants: "**a query never mutates durable data**; a processing
  run never reads (4) as an input; **a query failure can never corrupt (1)–(3)**";
  delegated operations "are **never query side effects**".
* **D16-11:** the UI owns presentation, "query construction (Q1–Q10)" and
  "**saved-query management**"; the UI reads only through serving; only the two
  delegated operations may be surfaced as user-initiated operations.
* **D22 E2:** "the boundary is fully defined (**ownership = serving state; exposure =
  Q-result shapes**; no engine-state ownership by the UI beyond the delegated
  operations). No evidence gap; **no implementation designed**. Classification:
  **READY BY EXISTING CONTRACT (scope); mechanism = implementation detail.**"
* **D23 §17 (granted, exhaustive):** "(c) serving state class (4) (**indexes/rollups/
  saved-query store**), rebuildable per D16-07" and "(e) the technology selections of
  §13/§14, made within bounded criteria and recorded."
* **D23 §18(3):** "Technology decisions recorded — each §13/§14 selection, its
  constraint-compliance rationale, and the **MD-10 grading** (item 7) where a physical
  persistence technology was selected." §18(8): "serving executes only **Q1–Q10 +
  saved-query semantics**; no other query path exists."
* **D24 §5 (delegation exercised):** class-(4) read-model = "single canonical-JSON
  index file + sha256 sidecar on local disk", state "outside the package", MD-10
  grading recorded; and — verbatim — "**Physical concerns left open under MD-12 / not
  selected:** … **a persistent read-model store beyond the single JSON file (re-grade
  under MD-10 if a later slice needs it)**".
* **Task 53 §4:** "Saved queries require a class-(4) store design step (mechanism =
  implementation detail, but a design step nonetheless)"; "no new authority decision is
  required to implement them (same standing authority as D30a/D30b/D31/D32/D33)."
* **MD-10 (D08 §10):** any storage-technology selection must demonstrably satisfy the 7
  criteria (deterministic representation/retrieval; provenance preservation; integrity
  verification; replay/reproducibility; durability per MD-05 classes; corpus-scale
  operation; required downstream consumption). **STORAGE TECHNOLOGY = UNDECIDED.**

### 3.2 Current implementation conventions (verified in code)

* Serving state lives in a caller-supplied directory **outside the package**
  (`serving-state/` git-ignored); the package's own verify-03 rejects unlisted files
  inside it, so state is never written into the baseline.
* Class-(4) convention = **single canonical-JSON document + sha256 sidecar**, written
  on build; loaded fail-closed (missing/incomplete, sidecar mismatch, unknown `format`
  version, or stale package identity → refuse; the remedy is a rebuild, never a silent
  serve).
* Delegated operation (b) `rebuild`: deletes **exactly** `KNOWN_STATE_FILES =
  {serving_index.json, serving_index.sha256}` inside the dedicated state directory and
  **refuses to run if anything else is present** (fail-closed `rebuild-refuse`).
* The `query` subcommand currently has six machine-reproducible modes (Q2 range, Q3
  instrument, Q4 filter, Q5 identity/association, Q6 calendar, Q7 detail); Q1/Q8/Q9/Q10
  are separate summary-view subcommands.

## 4. Persistence / authority decision matrix

Disposition key: **SETTLED** (governed by an existing record), **OPEN** (design input
required at implementation; within delegated authority), **CONTRADICTORY** (records in
tension; explicit decision required before implementing), **NOT REQUIRED**.

| # | Decision / requirement | Governing source | Disposition | Consequence for implementation |
|---|---|---|---|---|
| 1 | Storage ownership & boundary | D16-07 ((4) owner = serving boundary; distinct from (1)); D16-09; D24 §5 (state outside package) | **SETTLED** | Saved store is serving-owned, local-disk, outside the qualified package; never inside it (verify-03) |
| 2 | Durable record format & schema/versioning | none (D22 E2: "no implementation designed"; D16-10: mechanism = implementation detail) | **OPEN** | Implementation must define a versioned record format (precedent: index `format` field + fail-closed on unknown version) and record it per D23 §18(11) |
| 3 | Transaction / atomicity requirements | not explicitly governed; existing class-(4) convention = canonical JSON + sidecar digest, fail-closed load, rebuild as remedy (D24 §5); D16-09 invariants protect (1)–(3) from query failure | **SETTLED (by convention)** | Minimum bar: canonical JSON + sidecar + fail-closed load + rebuild; no locking/transactions (single-user, no server); crash consistency beyond the sidecar check is not a governed requirement |
| 4 | Stable saved-query identifiers | none | **OPEN** | CRUD requires a stable identifier (create/read/update/delete/list); the scheme is a recorded design choice |
| 5 | Query-history record identity & ordering | none | **OPEN** | depends on the C2 ruling (item 13); ordering (e.g., monotonic sequence) is a recorded design choice |
| 6 | Create / read / update / delete semantics | D16-11 (UI owns "saved-query management" = presentation); serving owns the store (D16-07); no CLI surface designed | **OPEN** | serving-side store + explicit CLI/API operations; UI exposure is the later D16-11 presentation item |
| 7 | Retention & cleanup | none beyond D16-07 "deleting (4) is never a data event" (for derived state) | **NOT REQUIRED** (beyond explicit user deletion) | no automatic retention policy is required; deletion is an explicit user operation |
| 8 | Failure & recovery behavior, incl. rebuild interplay | convention: fail-closed load + rebuild (b); **but** rebuild (b) today deletes its known state files and **refuses unknown files**, while a saved store is non-derivable user state | **CONTRADICTORY (C1)** | explicit ruling required before implementation (see §5.3) |
| 9 | Package immutability & separation | D16-07 ((1) immutable; (4) distinct); D24 §5; verify-03 | **SETTLED** | saved store outside the package; no package or fixture modification by this task or the slice |
| 10 | Local / single-user boundary (no principal/owner id, no auth/RBAC/multi-user) | D16-10 E2 (single-user); D16 §13 non-goals (no auth/RBAC/multi-user/PostgreSQL); D23 §13 constraints 1–2, §19 | **SETTLED** | no principal or owner identifier; no authentication; local disk; single user |
| 11 | Testability & migration / version-compatibility | none explicit; discipline: deterministic tests, format version + fail-closed on unsupported formats (serving-index/1.2 precedent), D23 §18(10) | **SETTLED (by convention)** | versioned format; fail-closed on unknown version; deterministic byte-level tests |
| 12 | Which query modes are savable; definition parameters | D22 E2 ("exposure = Q-result shapes"); D23 §18(8) ("only Q1–Q10 + saved-query semantics"); D23 §10/§14 (no query semantics beyond Q1–Q10/saved queries) | **SETTLED** | a saved definition = one existing Q1–Q10 mode + its exact, as-accepted parameters; no new query semantics is invented; an obsolete/unknown definition fails closed (the existing CLI convention for unknown fields/modes) |
| 13 | History recording: does query execution update history automatically? | D16-09 invariant "a query never mutates durable data" (durable = classes (1)–(4)) vs D16-10 E2 (history is a first-release feature); D22 E2 silent on timing; D16-09 also fixes delegated operations as "never query side effects" | **CONTRADICTORY (C2)** | explicit ruling required before any history implementation (see §5.3) |
| 14 | History content (full rows vs metadata; success vs failure outcomes) | none | **OPEN** | depends on C2; the design must state exactly what is retained (MD-10 criterion 6 — corpus-scale — bears directly if full result rows are retained) |
| 15 | Store technology selection | MD-12 UNDECIDED; D23 §13 delegates within 9 binding constraints + MD-10 grading; D24 §5 explicitly leaves open "a persistent read-model store beyond the single JSON file" | **OPEN (bounded selection inside the delegated authority — not a separate gate)** | the implementation makes and records a selection (constraint-compliance rationale + MD-10 grading per D23 §18(3)); nothing is pre-selected by any record |
| 16 | Scope of the D16-07 "pure derivation / rebuildable with no loss" clause for user-saved (4) state | D16-07 names "saved-query stores" in class (4) while class (4) is "always a pure derivation of (1)+(2)+registry; rebuildable at any time from them with no loss" — saved definitions are not derivable from (1)+(2)+(3) | **CONTRADICTORY (part of C1)** | the interpretation must be explicitly ruled and recorded (see §5.3) |

### 4.1 Authority reconciliation (what is and is not a gate)

* **Implementation authority: GRANTED, standing.** D23 §17(c) names the "saved-query
  store" explicitly as authorized class-(4) work; §17(e) delegates the technology
  selection; D24 §18(b) lists saved-query state as remaining authorized work; Task 53
  reached the same conclusion and this task re-verified it. **No new authority decision
  is required to implement the slice.**
* **Technology selection: delegated, not yet exercised.** D24's selection covered the
  index read-model only and explicitly left any other persistent store open. The
  implementer selects within the nine D23 §13 constraints and records the MD-10 grading —
  a record obligation, not a new authority gate.
* **Interpretive contradictions C1/C2: NOT delegated.** "Mechanism = implementation
  detail" (D16-10 E2) covers *how* the store works; it does not cover *which side of a
  governing invariant* a behavior sits on. Per house discipline (records in tension →
  document the smallest unresolved issue; do not silently choose), these are decision
  inputs, recorded below with the options and the recommendation.

## 5. Smallest implementation-ready slice

### 5.1 Candidate assessment

| Candidate | Verdict |
|---|---|
| Persistence contract only | This record starts it; on its own it delivers no product capability |
| Versioned saved-query record model only | No behavior without a store; not useful alone |
| **Saved-query CRUD** | **Recommended first slice** — the smallest coherent product capability; needs only the C1 ruling; no C2 dependency |
| Query-history recording | **Second slice** — needs C2 (and C1); not started |
| A general transactional class-(4) store | Over-engineered: D23 §13 constraint 1 (single-user simplicity) and no evidenced need beyond saved queries; not proposed |

### 5.2 Recommended slice: saved-query CRUD (scope and exclusions)

* **Scope:** a versioned saved-query store holding definitions that reference one of the
  existing `query` subcommand modes (Q2/Q3/Q4/Q5/Q6/Q7) with that mode's exact,
  as-accepted parameters; explicit create / read / update / delete / list operations;
  load-and-execute = run the referenced query through the **existing** serving layer
  (no new query semantics, no new query path — D23 §18(8)); a saved definition that no
  longer matches the current CLI vocabulary fails closed (the existing unknown-field /
  unknown-mode convention).
* **Exclusions (explicit):** query history; UI/transport; any Q1–Q10 behavior change;
  saved Q1/Q8/Q9/Q10 summary-view subcommands (a possible later extension — the six
  `query` modes are the natural first vocabulary because each is a machine-reproducible
  selector; this is a scope choice of the slice, recorded here, not a contract fix);
  any engine/canonical change; any promotion.
* **Data & identity semantics:** stable identifier per saved definition (scheme recorded
  at implementation); the definition pins mode + exact parameter values as published to
  the CLI (no normalization); single-user; no principal/owner identifier; no
  authentication.
* **Durability & atomicity:** the established class-(4) convention — canonical JSON +
  sha256 sidecar, fail-closed load (missing/incomplete/sidecar mismatch/unknown format
  version → refuse), deterministic byte-identical rewrites; no locking or transactions
  (single-user, no server).
* **Failure behavior:** fail closed on corrupt or unknown-version state; a saved-store
  failure never affects the baseline (D16-09); no partial list/create output.
* **Test acceptance conditions:** focused suite (round-trip CRUD; versioned-format
  pinning; fail-closed on corrupt/sidecar-mismatch/unknown-version/unknown-mode
  definitions; determinism + byte identity of the store file; package byte identity
  before/after success and failure; the six query modes' behavior unchanged — full-suite
  regression; CLI canonical-JSON output; one `D24_M2_ROOT`-gated leg: a saved
  definition executed over the real qualified baseline, serving-behavior assertions
  only, staged and gated — skipped ≠ passed); full suite totals reported.
* **Dependencies:** the C1 ruling (§5.3). Everything else is within standing authority
  and existing conventions.
* **Required authority:** none beyond the standing D23 grant (§17(c)); the technology
  selection is a bounded, recorded implementation item (§17(e)/§18(3)).
* **Evidence for durable publication:** implementation record (contract conformance,
  technology selection + MD-10 grading, artifact inventory with digests), focused +
  full-suite results, package-immutability digests, one bounded commit, FF push to the
  session branch, full independent remote verification, main/evidence/unrelated refs
  unchanged.

### 5.3 The two decision inputs (contradictions to rule before code)

**C1 — rebuild scope and the "pure derivation" clause for non-derivable (4) user state.**
D16-07 names "saved-query stores" inside class (4) while stating class (4) is "always a
pure derivation of (1)+(2)+registry; rebuildable at any time from them with no loss —
deleting (4) is never a data event." A saved definition is user state: it is not
derivable from the corpus, and deleting it *is* a user-visible event. The current
rebuild operation (b) deletes exactly its two known state files and **refuses to run if
anything else is present**. Options:

* **(a) recommended — a separate saved-store root outside the rebuild (b) scope.** The
  saved store lives in its own caller-supplied directory (the established `--state`
  convention), so operation (b) is untouched (no code change to its fail-closed
  guard), and the interpretation to be recorded is: the D16-07 "pure derivation /
  rebuildable with no loss / conflict rule" clauses govern the *derived* class-(4)
  state (indexes, rollups); the saved-query store is serving-owned *user* state within
  class (4) whose deletion is a user-visible event and which is therefore outside the
  destructive rebuild scope.
* (b) extend operation (b) to explicitly preserve the saved store (a documented
  exception to its delete-known-files semantics; more invasive to an existing
  delegated operation).
* (c) rebuild wipes the saved store — rejected: contradicts the "never a data event"
  spirit for user state.

**C2 — history recording timing (required only for the history slice).**
Does executing a query automatically write a history entry? Read strictly, D16-09's
invariant "a query never mutates durable data" covers class (4), and D16-09/§11 fix
user-initiated delegated operations as "never query side effects"; the records do not
carve out a (4)-history exception, and D22 E2 does not address timing. Options:

* **(a) recommended — history is recorded only by an explicit user operation** (e.g., an
  explicit "record this execution" step, or as part of an explicit saved-query run
  operation), keeping query execution mutation-free exactly as D16-09 states it;
* (b) an explicit interpretive ruling that the invariant protects (1)–(3) (the
  invariant's next sentence scopes failure to (1)–(3)) and that automatic (4)-history
  as a query side effect is permitted — this must be an explicit decision, not an
  implementation interpretation;
* (c) defer the history feature (implement saved queries first; history later under its
  own record) — permissible: no record fixes the mechanism or timing.

## 6. Explicit blockers and required decision input

1. **C1 ruling** (blocker for any saved-state implementation): which rebuild-scope
   option — recommendation (a), with the §5.3 interpretation recorded in the
   implementation record.
2. **C2 ruling** (blocker for history only): recommendation (a) or (c); option (b) only
   as an explicit decision.
3. **Technology selection** (not a blocker — a record obligation inside the delegated
   authority): the implementer's bounded selection + constraint-compliance rationale +
   MD-10 grading per D23 §18(3). Note the D24 precedent (single canonical-JSON file +
   sidecar, local disk, stdlib-only) is the natural conforming candidate and would be
   re-graded under MD-10 for the saved-store use; it is a precedent, not a pre-selection.

Nothing else blocks the recommended slice: scope, ownership, single-user boundary,
package separation, fail-closed discipline, and implementation authority are all
settled by the records cited above.

## 7. Test and durability acceptance conditions (for the slice)

As §5.2 "Test acceptance conditions", plus the standing publication battery: one bounded
commit (record + code + tests); FF push to the session branch only; independent remote
verification (session HEAD, parent/tree, changed paths and blob identities, record
present remotely, main = D24 unchanged, evidence branch unchanged, unrelated branch
untouched); post-push full suite; no force/rewrite; package byte identity before/after
success and failure; gated real-baseline leg staged and **not** claimed passed;
`_transfer_delivery/` preserved.

## 8. Serving and real-M2 qualification boundaries (kept separate)

* **D24 remains the promoted serving baseline** (main). D30a–D36 are session-branch
  implementation milestones, not promoted.
* Q1–Q10 implementation status does **not** imply real-M2 integration qualification:
  the real-package legs are `D24_M2_ROOT`-gated (12 gated legs after D36; all skipped
  in this environment — **never represented as passed**).
* The Windows qualification track (D26) is independent and was not touched by this
  task; its handoff pin is stale (D24 `6997701…`) and must be re-pinned to the
  then-current implementation commit (currently D36 `4e0afde…`) before execution. No
  Windows execution occurred or was started here.
* No Q1–Q10 suite was rerun in this investigation (no evidentiary reason — read-only
  task, no code change).

## 9. Disposition

**DECISION INPUT REQUIRED.**

* Saved queries / query history: scope **READY BY EXISTING CONTRACT** (D22 E2,
  re-verified); implementation authority **GRANTED and standing** (D23 §17(c)/(e));
  technology selection **delegated** (D23 §13; D24 left the store open).
* The recommended smallest slice — **saved-query CRUD** (no history) — is otherwise
  implementation-ready, but **not** implementation-ready as-is: it requires the **C1
  ruling** (rebuild scope / "pure derivation" interpretation for non-derivable (4)
  user state; recommendation: option (a) — a separate saved-store root outside the
  rebuild (b) scope, with the interpretation recorded).
* The **history** feature additionally requires the **C2 ruling** (recording timing;
  recommendation: option (a) explicit operation, or option (c) defer).
* No implementation, store, technology selection, or fixture/package change is made by
  this record. **STOP** after this investigation and reconciliation.
