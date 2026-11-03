# D38 — Saved-query CRUD (serving slice)

**Status:** implementation record (first slice under the D37-DEC governance decision; follows D36/Q6)
**Authority:** D23 §17(c) (serving state class (4), including the "saved-query store"),
D23 §13/§14 (technology-selection delegation with binding constraints + MD-10 grading),
D24 §18 remaining-authorized-work item (b) (saved-query state); decisions C1(a)/C2(a)
per `docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md` (user-approved rulings,
published on this branch as `b39e866…` before this implementation began).
**Publication scope:** session branch only. No main promotion.

---

## 1. Decisions implemented (as approved)

* **C1(a)** — saved queries are serving-owned *user* state, distinct from the
  qualified baseline. Implemented as a **distinct store root** (`--saved-state`)
  outside the derived-state rebuild operation's scope; the rebuild (b) code is
  **unchanged** (its scope remains exactly `KNOWN_STATE_FILES =
  {serving_index.json, serving_index.sha256}` inside the derived-state directory,
  with its fail-closed `rebuild-refuse` guard); a run whose saved root equals the
  derived-state root fails closed (`saved-query-conflict`); deleting a saved query
  is an explicit `saved delete` operation (no retention policy, no automatic
  cleanup); the D16-07 pure-derivation interpretation is recorded in the decision
  record (§6 of that record) and honored here (derived state and saved state never
  share a root).
* **C2(a)** — query history may be recorded only through an explicit operation.
  Implemented as: **`execute_saved` is read-only against the store** — it never
  writes the store (asserted byte-for-byte in tests, including after repeated and
  failing executions). **History itself is not implemented** (no history storage,
  no history surface, no history writes anywhere) — it is deferred to a later
  slice (D37-DEC §8).

## 2. Storage technology selection and MD-10 assessment (D23 §13/§18(3))

**Selected:** one canonical-JSON document (`saved_queries.json`) + a sha256 sidecar
(`saved_queries.sha256`) on local disk; Python 3 standard library only;
deterministic serialization (sorted keys, compact, LF); **atomic write/replace**
(temp file in the same directory + `os.replace`, so a crash mid-write can never
leave a partial store file or sidecar); fail-closed load (missing/incomplete,
sidecar mismatch, unparseable JSON, unknown format version, or any schema/contract
violation is refused, never silently repaired). State lives in a caller-supplied
root **outside the qualified package** (`saved-state/` is gitignored) and outside
the derived-state rebuild scope (C1(a)).

**Considered and rejected (recorded rationale):**

| Candidate | Verdict |
|---|---|
| SQLite (`sqlite3`, stdlib) | Rejected: binary file format with its own schema/migration surface and engine-internal state; no capability it adds is required at single-user, local-disk scale; the D23 §13 constraint 1 simplicity bar is met by the file convention; nothing in the approved scope requires it |
| Append-only NDJSON log | Rejected: unbounded growth, no deterministic compact rewrite, weaker integrity story than the digest-verified single document |
| General-purpose transactional store | Rejected: explicitly excluded — the approved scope (explicit single-user CRUD) requires no concurrency control, no transactions, no locking |

**MD-10 grading (the 7 store-selection criteria, D08 §10) for the selected store:**

1. **Deterministic representation/retrieval** — satisfied: canonical JSON;
   identical store content yields byte-identical files (tested: two independent
   builds of the same definitions are byte-identical; the temp-file name is never
   persisted).
2. **Provenance preservation** — satisfied: the store holds *definitions only*
   (mode + exact as-published parameters); it stores no row values and reinterprets
   nothing; a saved-query execution carries the normal row-level D05 §8 provenance
   emitted by the existing query layer.
3. **Integrity verification** — satisfied: sha256 sidecar verified on every load;
   mismatch, truncation, and unparseable state fail closed (tested).
4. **Replay / reproducibility** — satisfied: a saved definition is a complete
   reproduction statement — execution replays through the existing deterministic
   query layer; repeated runs are byte-identical (tested).
5. **Durability (per MD-05 classes)** — satisfied for its class: class-(4)
   serving-owned user state; loss of the store is a user-visible event for saved
   definitions (per the C1(a) interpretation) but can never affect (1)–(3);
   atomic write/replace prevents torn files; single-user local disk, no further
   durability class required.
6. **Corpus-scale operation** — satisfied: the store holds definitions only
   (bounded, small); execution streams the baseline exactly as the corresponding
   direct query does (no extra corpus-scale cost); **no full result rows are
   persisted**.
7. **Required downstream consumption** — satisfied: consumed by the single-user
   CLI in this slice; the D16-11 UI (later) reads saved-query management only
   through serving, which this store supports by construction.

## 3. Schema, identity, lifecycle, and failure semantics (the contract)

* **Document** (format `serving-saved-queries/1.0`): exactly
  `{"format", "queries"}`; `queries` maps identifier → record; a record is exactly
  `{"id", "mode", "params"}`. No other keys are accepted at create/update or on
  load (fail closed).
* **`mode`** — exactly one of the ten currently implemented and supported Q1–Q10
  query ids: `Q1-dataset`, `Q2-date-range`, `Q3-instrument`, `Q4-filter`,
  `Q5-association`, `Q6-calendar`, `Q7-record-detail`, `Q8-data-quality`,
  `Q9-archive-inventory`, `Q10-qualification`. No other query path exists (D23
  §18(8)); an unknown mode fails closed at save, update, and load.
* **`params`** — exactly the parameters of that mode's contract, with exact,
  as-published values: Q1 `family`/`year`; Q2 `date_from`+`date_to` (required); Q3
  `symbol`+`series` (+`year`); Q4 `filters` (non-empty str→str; field validity is
  enforced at execution by the existing Q4 check, not re-validated here); Q5
  `security_id`/`symbol`/`series` (≥1 selector); Q6 `date_from`/`date_to`
  (both-or-neither); Q7 `source_file`+`source_line_number`; Q8/Q9 none; Q10
  `repo`. Absent parameter = missing key (never null, never blank — blank/null
  values are rejected; no normalization, no aliases, no result rows persisted).
* **Identifier** — 1–64 chars of `[a-z0-9_-]`, starting with `[a-z0-9]`;
  case-sensitive exact; unique in the store; user-chosen at create; stable;
  referenced by exact value on update/delete/run.
* **Lifecycle** — create (first create bootstraps the store; duplicate id fails
  closed); read by id; list sorted by id; update = **full replacement** (new
  mode+params exactly replace the old — no merge); delete = explicit removal, the
  only removal path.
* **Failure checks (fail closed)** — `saved-query-missing`, `saved-query-corrupt`,
  `saved-query-format`, `saved-query-schema`, `saved-query-invalid`,
  `saved-query-duplicate`, `saved-query-not-found`, `saved-query-conflict`
  (saved root == derived-state root). CLI exit codes: 2 for usage-level failures
  (invalid/duplicate/not-found), 3 for store-state failures and for
  baseline/index/d01 failures (mirroring the established command exit codes); no
  partial output on failure.
* **Execute** — `saved run` opens the verified baseline, loads the derived index
  (all modes, mirroring the established verify → build → query flow), and executes
  the definition through the **existing** query functions with **exactly** the
  corresponding CLI result envelope (byte-parity asserted against the `query`
  command output in tests). A stored definition is executed with its mode's
  existing runtime validation (e.g., an unknown Q4 field stored shape-validly
  still fails closed at execution with the established Q4 check).

## 4. Implementation surface (files changed)

| File | Change |
|---|---|
| `src/serving/saved.py` | **new** — store I/O (load/save, atomic write/replace), validation (document/record/definition contract), CRUD, `assert_separate_roots` (C1(a) guard), `execute_saved` (C2(a) read-only execution) |
| `src/serving/cli.py` | `saved` subcommand group: `save` / `show` / `list` / `update` / `delete` / `run`; shared definition-flag mapper; exit-code mapping; module docstring updated. **`cmd_query` and all existing subcommands are byte-unchanged** (no Q1–Q10 semantic change) |
| `src/serving/__init__.py` | package boundary docstring (saved state is class-(4) user state, distinct root, C1(a)/C2(a)); curated exports |
| `.gitignore` | `saved-state/` (the saved-store root; never committed) |
| `tests/test_serving_saved.py` | **new** — 59 focused tests (below) |
| `tests/test_serving_m2_integration.py` | one additional `D24_M2_ROOT`-gated real-package leg (saved-run parity + store immutability over the real baseline) |

No engine file, no fixture file, no evidence file, and no package file was
modified (verified: `git status` shows only the files above).

## 5. Tests executed (exact outcomes)

* **Focused** (`tests/test_serving_saved.py`): **59 run, 59 passed, 0 failed,
  0 skipped.** Coverage: lifecycle (create/read/list/update-full-replacement/
  delete), deterministic store bytes and sorted listing, identifier contract,
  duplicate-id and invalid-update handling, corrupted/truncated/unknown-format/
  non-contract/null-value/unknown-mode persisted state, per-mode parameter
  contract violations, **execution parity with the direct query contracts for
  all ten modes** (Q1–Q10), unknown-id execution, **execution never mutates the
  store (C2(a))**, existing Q4 runtime semantics preserved, **rebuild isolation
  (C1(a)): rebuild leaves the saved store byte-identical, `KNOWN_STATE_FILES`
  unchanged, rebuild-refuse preserved, same-root run fails closed**, package
  byte-immutability after successful and failed operations, CLI output
  **byte-parity with the `query` command** and CLI exit codes.
* **Full suite** (unittest discover, `PYTHONPATH=src`): **771 run, OK, 13
  skipped** (was 711/12 at D36: +59 focused +1 new gated leg; +1 skip = the new
  gated leg). **All 13 skips are `D24_M2_ROOT`-gated real-package legs**
  (12 pre-existing + the new saved leg); they are PENDING baseline provisioning
  in this environment and are **not represented as passed**. The 4 ungated
  identity legs of the M2 integration file pass.
* **Gated real leg (staged, not executed here):**
  `test_saved_query_run_over_real_baseline` — saved Q3/Q2 definitions over the
  real qualified baseline: exact parity with the direct queries, non-empty
  results, store byte-identical after execution.

## 6. Package immutability and rebuild isolation (results)

* `test_package_bytes_unchanged_after_saved_operations`: the qualified package's
  full file set (path → sha256) is unchanged after save×3, show, list, update,
  a successful run, three failing operations, and delete — **PASS**.
* `test_rebuild_does_not_touch_saved_store`: `rebuild_state` over the
  derived-state directory leaves the saved store's file set and bytes identical —
  **PASS**.
* `test_rebuild_known_state_files_unchanged`: the rebuild's scope is still
  exactly the two derived files — **PASS** (derived-state behavior preserved,
  D37-DEC §6.4).
* `test_rebuild_still_refuses_unknown_files`: fail-closed `rebuild-refuse`
  preserved — **PASS**.
* `test_same_root_execution_fails_closed` / `test_cli_run_same_root_exit_3`:
  C1(a) guard fires before any load — **PASS**.

## 7. Explicit non-goals (NOT performed in this slice)

* No query-history implementation, storage, UI, or any implicit history write on
  query execution (C2(a): history is a later slice under its own design record).
* No UI or transport changes. No authentication/RBAC/multi-user/synchronization/
  remote persistence (D16 §13; D23 §13 constraints).
* No Q1–Q10 semantic change, field alias, or undocumented normalization (the
  `query` subcommand and all existing subcommands are byte-unchanged; saved
  execution reuses the existing query functions and envelopes).
* No full result rows persisted as saved definitions.
* No general-purpose database or transactional platform.
* No real-M2 Windows qualification (that track remains separate and must be
  re-pinned to the then-current implementation commit before any later
  execution). No product E2E or release-readiness claim.
* **No main promotion** (main remains D24 `69977017…`; promotion is the user's
  separate step).

## 8. Publication

One additive implementation commit on the session branch
(`arena/9021d1a1-nse-historical-data-engine`), fast-forward only, followed by
independent remote verification (remote commit, parent, changed paths, blob
identities; main/evidence/unrelated refs unchanged). This record is part of that
commit.
