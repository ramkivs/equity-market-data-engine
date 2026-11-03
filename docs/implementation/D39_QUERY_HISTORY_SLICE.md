# D39 — Query history: the explicit-recording slice

**Status:** implementation record (query-history slice; follows D38 saved-query CRUD)
**Authority:** D16-10 item 5 ("Saved queries and query history are first-release
product features, persisted as serving state (4) (single-user; mechanism =
implementation detail)"); D22 E2 (READY BY EXISTING CONTRACT — scope);
**D37-DEC §7 (C2(a) APPROVED, binding)** — "Query history may be recorded only
through an explicit operation. Executing an ordinary query must not implicitly
mutate durable history."; **D37-DEC §8** — history is "a separate later
implementation slice (it requires its own design record under the same standing
authority once C1/C2 are in force)"; D23 §13/§17 (standing grant + technology
delegation with MD-10 grading). C1(a) remains binding (distinct-root discipline).
**Publication scope:** session branch only. No main promotion.

---

## 1. Contract reconciliation (history-specific unknowns only)

Governing lines re-verified verbatim at this task (D16-10 item 5; D22 E2;
D37-DEC §7/§8; D38 §1). The records fix: ownership (serving state (4)), scope
(first-release), the single-user boundary, the explicit-operation requirement
(C2(a)), and that "no record fixes the history mechanism, schema, or timing
beyond C2's explicit-operation requirement" (D37-DEC §8). Everything below is
the **narrowest design decision** consistent with those lines, documented as
such — not a new authority decision.

### A. Recording

**Decision.** One explicit operation: `serving history record --mode MODE
[params] --history-state H --package P --state S`. It (1) validates the
execution description against the SAME Q1–Q10 contract as saved-query
definitions, (2) executes it through the existing query layer, and (3) durably
records the **actual** outcome as the next entry.

Rationale (the decisive constraint): recording an execution that never happened
would fabricate the outcome (the task's "do not fabricate provenance" and the
house "never invent" discipline). The operation therefore executes — and that
execution is the explicit user request itself (an explicit operation, like
`saved save`), **not** a hidden side effect of any query. C2(a) is preserved:
the history store is written by exactly one code path, invoked by exactly one
CLI verb; `query`, `saved run`, and every Q1–Q10 command never touch it
(asserted byte-for-byte in tests).

### B. Record content

**Decision.** An entry is exactly `{seq, mode, params, outcome, check?}`:

* `mode` + `params` — the exact execution description (validated; same
  vocabulary and parameter contract as a saved definition — no new query
  semantics, no aliases, no normalization);
* `outcome` — `"success"` or `"error"`: the ACTUAL outcome of the explicitly
  requested execution;
* `check` — present iff outcome is `"error"`: the fail-closed check id of the
  query failure (the real error's check, never invented).

**Not stored (and why):** no result rows (the task's "never store full result
rows"; a history entry that stores rows would re-host class-(1) data in (4));
no result counts (no governing record prescribes a summary, and a uniform
count would need per-mode semantics no record fixes — a possible later
extension); no timestamps (the determinism contract admits no clock value into
durable state — see C); no provenance or qualification fields (never
invented). A query **failure IS recorded** (with its check id): the failure is
the actual outcome of the explicit request, and fail-closed errors carry the
check id by convention.

### C. Identity and ordering

**Decision.** `seq` = a 1-based monotonically increasing integer; stable for
the entry's life; **never reused** — the document carries a `next_seq` counter
(the next seq a recording may use) that increments on every recording and never
decrements, so deletion cannot free a seq. Entry order = ascending `seq` = the
order of the explicit recording operations. **Repeated identical descriptions
are NOT collapsed**: every explicit recording produces a new entry (no record
authorizes collapsing; collapsing would destroy the audit trail of explicit
operations). No wall-clock timestamp (determinism contract); ordering is by
explicit-operation order, which is the semantics a single-user local history
requires.

### D. Lifecycle

**Decision.** `history list` (ascending seq), `history show --seq N`,
`history delete --seq N` (explicit deletion; a deleted seq is never reused).
**No retention policy, no automatic pruning, no implicit cleanup** (the task's
constraint; C1(a) user-state philosophy). History is **separate from
saved-query definitions**: its own root; an entry's `mode`/`params` is a copy
of the execution description, not a reference to a saved-query id (no coupling
between the two stores).

### E. Persistence and isolation

**Decision.** A dedicated root (`--history-state`, gitignored `history-state/`),
distinct from the derived-state root and the saved-store root; a record
operation whose history root equals the derived-state root fails closed
(`history-state-conflict`). Mechanism: the D38 precedent — one canonical-JSON
document + sha256 sidecar on local disk, deterministic serialization, atomic
write/replace, fail-closed load (D23 §13 delegation; MD-10 grading below).
Format `serving-query-history/1.0`; document = exactly `{format, entries,
next_seq}`. A baseline or derived-state failure during `history record`
aborts with **no entry published** (no completed execution to record).
Fail-closed checks: `history-missing`, `history-corrupt`, `history-format`,
`history-schema`, `history-invalid`, `history-not-found`,
`history-state-conflict` (CLI exit 3 for store-state, 2 for not-found/invalid
description).

## 2. Persistence mechanism and rationale (D23 §13/§18(3))

**Selected:** single canonical-JSON document (`query_history.json`) + sha256
sidecar, stdlib only, atomic write/replace, fail-closed load — the same
convention as the D38 saved-query store.

**Evaluation (the D38 precedent is a precedent, not a mandate — considered
again):** the store holds small entries created only by explicit user
operations; there is no query workload against it beyond list/show/delete;
nothing in the approved scope requires a binary format, an index, transactions,
or locking. The JSON+sidecar convention therefore remains the **minimum
suitable mechanism**; SQLite/NDJSON-log/transactional alternatives were
rejected for the same recorded reasons as in D38 §2 (re-stated there).

**MD-10 grading (the 7 criteria, D08 §10):** (1) deterministic
representation/retrieval — canonical JSON, byte-identical for identical state
(tested); (2) provenance preservation — entries carry the real check id on
error and the exact description; nothing invented, no row values re-hosted;
(3) integrity verification — sha256 sidecar verified on every load;
corrupt/truncated/unknown-format state refused (tested); (4) replay/
reproducibility — entries are deterministic; the same explicit operations in
the same order yield byte-identical stores (tested); (5) durability (MD-05
classes) — class-(4) user state; loss is a user-visible event for history but
can never affect (1)–(3); atomic write/replace prevents torn files; (6)
corpus-scale operation — the store is bounded by explicit operations; no
corpus-scale read path exists; (7) required downstream consumption — single-
user CLI now; the D16-11 UI later reads through serving.

## 3. Implementation surface (files changed)

| File | Change |
|---|---|
| `src/serving/history.py` | **new** — store I/O (fail-closed load, atomic write/replace), document/entry validation, `record_execution` (the single explicit path that writes history), `list_history`/`get_history`/`delete_history`, isolation guard |
| `src/serving/saved.py` | the per-mode execution dispatch extracted from `execute_saved` into shared `execute_query_definition` (behavior identical — all D38 tests still pass); `execute_saved` is now guard + load + lookup + shared dispatch |
| `src/serving/cli.py` | `history` subcommand group: `record` / `list` / `show` / `delete`; reuses the saved-definition flag vocabulary and mapper; docstring updated. All existing subcommands unchanged |
| `src/serving/__init__.py` | boundary docstring (history is recorded ONLY via the explicit operation); curated exports |
| `.gitignore` | `history-state/` |
| `tests/test_serving_history.py` | **new** — 33 focused tests |
| `tests/test_serving_m2_integration.py` | one additional `D24_M2_ROOT`-gated real-package leg (explicit record over the real baseline; ordinary query leaves history untouched) |

No engine file, no fixture file, no evidence file, and no package file was
modified.

## 4. Tests executed (exact outcomes)

* **Focused** (`tests/test_serving_history.py`): **33 run, 33 passed, 0
  failed, 0 skipped.** Coverage: explicit recording creates durable success
  and error entries (with check id); an execution that never happened is never
  recorded (invalid description → no entry, baseline/state failure → no
  entry); recording reuses the existing Q1–Q10 execution layer (all ten
  modes); **C2(a): ordinary `query` CLI execution and `saved run` (API + CLI)
  never modify the history store** (byte-for-byte), and history stays absent
  until an explicit record; seq stable and **never reused** across deletion
  (`next_seq` monotonic); repeated identical descriptions NOT collapsed;
  ascending ordering; deterministic serialization; entries contain no rows/
  counts/timestamps/invented fields; fail-closed on missing/partial/corrupt/
  truncated/unknown-format state and on every schema violation (non-contract
  keys, seq ordering, outcome set, check presence/emptiness, stored
  mode/params contract, `next_seq` invariants); saved-query state unchanged by
  history operations; derived-state rebuild leaves history unchanged; package
  bytes unchanged after successful and failed operations; existing query and
  saved-run behavior intact (spot-checks vs direct calls); CLI record/list/
  show/delete flow and exit codes (record exits 0 when the entry is durably
  recorded — a recorded query failure is data in the entry, not an operation
  failure; 2 for invalid description/not-found; 3 for store-state and
  same-root conflict).
* **Full suite** (unittest discover, `PYTHONPATH=src`): **805 run, OK, 0
  failed, 14 skipped** (was 771/13 at D38: +33 focused + 1 new gated leg).
  **All 14 skips are `D24_M2_ROOT`-gated real-package legs** (13 pre-existing
  + the new history leg); they are PENDING baseline provisioning in this
  environment and are **not represented as passed**. The 4 ungated identity
  legs of the M2 integration file pass.
* **Gated real leg (staged, not executed here):**
  `test_history_record_over_real_baseline` — explicit record of a real Q2
  range (success, real rows), store digest matches, then a direct
  `query_date_range` leaves the history files byte-identical (C2(a) over the
  real baseline).

## 5. Explicit non-goals (NOT performed in this slice)

* No automatic recording from `query`, `saved run`, or any Q1–Q10 mode (the
  explicit operation is the only write path — asserted in tests).
* No UI or transport. No saved-query CRUD redesign (D38 surface unchanged;
  one internal refactor — shared dispatch — with all D38 tests passing).
* No Q1–Q10 semantic change, field alias, or undocumented normalization.
* No general-purpose database or enterprise storage; no authentication/RBAC/
  multi-user/synchronization/remote persistence (D16 §13; D23 §13).
* No result rows, counts, or timestamps stored; no invented provenance or
  qualification status.
* No retention policy, automatic pruning, or implicit cleanup.
* No real-M2 Windows qualification (track remains separate; re-pin to the
  then-current implementation commit before any later execution). No product
  E2E or release-readiness claim. **No main promotion** (main remains D24
  `69977017…`).

## 6. Publication

One additive implementation commit on the session branch
(`arena/9021d1a1-nse-historical-data-engine`), fast-forward only, followed by
independent remote verification (remote commit, parent, changed paths, blob
identities; main/evidence/unrelated refs unchanged). This record is part of
that commit; the exact full-suite counts are reported in the task report.
