# D37 — Saved-Query & Query-History Governance Decision (C1(a) / C2(a))

## 1. Title / identifier

**D37-DEC** — The governance decision that resolves the two interpretive contradictions (C1, C2)
identified by the D37 readiness investigation
(`docs/investigations/D37_SAVED_QUERY_HISTORY_READINESS.md`) for the first-release
saved-query / query-history feature (D16-10 item 5, D16-12 item 5). This record publishes
**approved decisions** for the class-(4) saved-query state boundary (C1) and for
query-history recording timing (C2). It grants no new implementation authority: the
saved-query store implementation authority is the standing D23 grant (§17(c) grants "serving state class (4) (indexes/rollups/
saved-query store), rebuildable per D16-07"; §13/§14 delegate the technology
selection).

## 2. Status

**DECISION = C1(a) APPROVED; C2(a) APPROVED.** History is **DEFERRED** and excluded from
the current implementation slice. Saved-query CRUD is the authorized next slice under the
standing D23 grant, bounded by §6 below.

## 3. Date

2026-10-10.

## 4. Authority boundary

This record is a decision input consumed by the saved-query implementation slice. It
records the user's explicit approval of the two rulings identified by the D37 readiness
investigation (§5.3 of that record). It does not rewrite, amend or supersede D16, D22,
D23, D24 or the D37 readiness record; it interprets D16-07 and D16-09 where they are in
tension, and it changes the authority or scope of no other decision. The decision
authority is the product owner (Ramki), exercised as an explicit user approval of the
rulings as documented in the D37 readiness record; this record is the durable
publication of that approval.

## 5. Verified baseline (before decision)

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged |
| Session branch `arena/9021d1a1-nse-historical-data-engine` | `ae3ea7ebd237aecf477dd72b1b9e2a35952437f3` = D37 readiness record |
| D36 implementation commit | `4e0afde6f7fe499fa3e81d7596a2c62a4b63d2eb` (parent of the D37 readiness record) |
| Evidence branch `evidence/d26-real-m2-execution-20261009` | `0dda72bef051aa769340badda56997b42a1723f8` — unchanged |
| Unrelated session branch `arena/01a10c83-nse-historical-data-engine` | `db604063b305f9a96d2ac038ed001ff7344c17c8` — observed, not touched |
| Local state at task start | 30th sandbox `.git` rollback; repaired non-destructively (unshallow → 12-commit ancestry chain to the D37 readiness record all YES → **full worktree byte audit vs the D37 record tree: 187 files, 0 missing, 0 differing** → `update-ref`/`read-tree`/mixed `reset`, ref/index only); `_transfer_delivery/` preserved; no remote ref moved |

## 6. C1 — APPROVED (option (a) of the D37 readiness record §5.3)

**DECISION.** Saved queries are **serving-owned user state**, not state derivable from
the qualified baseline.

Requirements fixed by this decision:

1. **Separate root.** The saved-query store is placed in a **distinct root outside the
   existing derived-state rebuild operation's scope** (delegated operation (b), D16-11).
   The derived-state rebuild continues to operate on exactly its known derived state
   files inside the dedicated derived-state directory and to fail closed (
   `rebuild-refuse`) on anything else; it neither deletes nor modifies saved queries.
2. **No silent loss.** Rebuilding derived serving state must not silently delete or
   modify saved queries. The saved store is outside that operation's reach by
   construction (distinct root), and the implementation must verify isolation in tests.
3. **Explicit user-visible deletion.** Deleting a saved query is an explicit
   user-visible operation (an explicit delete command). There is no retention policy and
   no automatic cleanup (the D37 readiness record item 7: NOT REQUIRED beyond explicit
   user deletion).
4. **Derived-state behavior preserved.** The existing derived-state rebuild behavior
   (`KNOWN_STATE_FILES` = the two derived state files; delete-and-rebuild;
   fail-closed guard) and all package-immutability guarantees are preserved unchanged.
5. **Interpretation of D16-07 (recorded, binding for this feature):** the D16-07
   class-(4) clauses "always a pure derivation of (1)+(2)+registry; rebuildable at any
   time from them with no loss — deleting (4) is never a data event" and the associated
   conflict rule **govern the derived class-(4) state** (indexes, rollups, query
   accelerants). The **saved-query store is independently owned serving state within
   class (4)**: it is named in D16-07's class-(4) list but is not a pure derivation of
   (1)+(2)+(3), and its deletion **is** a user-visible event. The D16-07
   pure-derivation invariant does not make independently owned saved-query state
   derivable. The conflict rule applies where derived state can disagree with the
   baseline; the saved-query store is never an input to queries or to processing runs
   (D16-09 invariants continue to apply to it as to all serving state).

## 7. C2 — APPROVED (option (a) of the D37 readiness record §5.3)

**DECISION.** Query history **may be recorded only through an explicit operation**.
Executing an ordinary query must not implicitly mutate durable history. This keeps the
D16-09 invariant "a query never mutates durable data" intact without exception and is
consistent with delegated operations being "never query side effects".

## 8. History: deferred and excluded

Query history is a **separate later implementation slice** (it requires its own design
record under the same standing authority once C1/C2 are in force). **This task does not
implement** history recording, history storage, or history UI. No record fixes the
history mechanism, schema, or timing beyond C2's explicit-operation requirement.

## 9. Selected implementation boundary for saved-query CRUD

The next slice is **saved-query CRUD** (smallest useful product capability; D37
readiness record §5.2), bounded to:

* **Scope:** a versioned saved-query store holding definitions that reference one
  currently implemented and supported Q1–Q10 query contract with exactly the parameters
  required to reproduce the definition; explicit **create / read / update / delete /
  list** operations; **load-and-execute** = run the referenced query through the
  existing serving query layer (no new query semantics, no new query path — D23 §18(8)).
* **Exclusions (explicit):** query history and any history writes on query execution;
  UI or transport changes; any Q1–Q10 semantic change, field alias, or undocumented
  normalization; full result rows persisted as saved definitions; any new query mode.
* **Durability / failure:** the established class-(4) discipline — deterministic
  serialization, integrity sidecar, fail-closed load (missing/incomplete/corrupt/
  unknown-version/duplicate-identifier/invalid-reference → refuse, no partial output),
  safe write/replace behavior; a saved-store failure never affects the baseline
  (D16-09).
* **Identity / lifecycle:** stable, documented, deterministic saved-query identifier
  contract; explicit, testable create/update/delete semantics; no retention policy
  beyond explicit deletion.
* **Boundary:** single-user, local, no authentication/RBAC/multi-user/synchronization/
  remote persistence (D16 §13, D16-10 E2, D23 §13 constraints 1–2).

## 10. Technology selection

The saved-store technology selection **remains an implementer decision under the
existing D23 delegation** (§13/§14, §17(e)): bounded by the nine D23 §13 constraints,
with constraint-compliance rationale and the **MD-10 grading** recorded per D23 §18(3).
Nothing in this record names, ranks, prefers or implies a technology. D24's
JSON-plus-sidecar convention is a precedent, not a pre-selection; the D24 §5 explicit
opening ("a persistent read-model store beyond the single JSON file") is discharged by
the implementer's recorded selection for this store.

## 11. Non-implications

This decision implies **no main promotion** (main remains D24 `69977017…`; promotion is
the user's separate step), **no production authorization**, **no real-M2 qualification
change** (the Windows track stays separate and must be re-pinned to the then-current
implementation commit before any later execution), **no Q1–Q10 semantic change**, and
**no product E2E / release-readiness claim**.

## 12. Disposition

**C1(a) APPROVED; C2(a) APPROVED; HISTORY DEFERRED.** The saved-query CRUD slice is
implementation-ready under the standing D23 grant, bounded by §9. This record grants no
implementation authority of its own; it resolves the decision inputs blocking that
slice.
