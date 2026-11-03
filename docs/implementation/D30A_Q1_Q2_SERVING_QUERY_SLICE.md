# D30A — Q1 + Q2 SERVING QUERIES

## 1. Task identity and purpose

**D30A** — the second serving slice under the standing **D23** authority (D24 §18
"remaining authorized work (b) Q1–Q2, Q4–Q10 and saved-query state per D16-10 —
no new authority required"). This slice implements, on top of the D24 vertical
slice:

* **Q1** — dataset/partition selection (family × year) and yearly summaries;
* **Q2** — date-range query over canonical rows;
* the minimal **class-(4) index extension** (per-file `business_date` min/max,
  format `serving-index/1.1`) that keeps date-range queries off full-package
  scans.

No new authority is requested. No other query category, saved-query state, w2
parser, or UI/transport is implemented here.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 (D23 `01612f7…` promoted by the user's separate step; D23 parent of D24) |
| Session branch at work | `arena/9021d1a1-nse-historical-data-engine` at `8d58bac46b7047cc72e54af3b1a76088832fde89` (D26); this slice commits on top |
| Evidence branch | `evidence/d26-real-m2-execution-20261009` at `0dda72bef051aa769340badda56997b42a1723f8` — untouched |
| Local state | 19th sandbox `.git` rollback found at task start (HEAD `89ce965…`, re-shallow, stale modified tracked files whose bytes matched D26 exactly); recovered with the established procedure (unshallow → ancestry YES → `update-ref` → `read-tree` → mixed `reset`); worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, 257 files, never committed) |

## 3. D23 authority and scope

Implemented within D23 §8/§10/§17(a) (first-release serving/query layer over the
qualified M2 baseline; Q1–Q10 semantics fixed by D16-10; no arbitrary query
semantics beyond the Q1–Q10/saved-query boundary). D23 §9 exposure boundary
respected (canonical rows + their as-published fields only; no raw bytes). D23 §12
class-(4) rules respected (pure derivation, rebuildable, never a source of truth,
distinct from class (1)). D21 boundaries untouched (no registry/resolution
machinery; M2-only scope: class-(2) incremental publications and class-(3)
registry absent, never fabricated).

## 4. Q1 — exact contract

Public API: `serving.query_dataset_summary(index, family=None, year=None) -> dict`
(query id `Q1-dataset`).

* **Pure derivation over the class-(4) index** — the signature takes the index
  document alone (no baseline handle); **no canonical row is scanned**. A
  missing (non-dict) index fails closed with `QueryError`.
* **Selection:** no argument = all partitions; `family` = exact as-published
  family name (string); `year` = 4-digit integer. Unknown selection → **empty
  result** (`partitions: []`, zeroed summary), never an error.
* **Result document:** `partitions` — selected partitions sorted by (family,
  year), each with `row_files`, `row_count`, `instrument_pairs` (union of the
  per-file instrument sets, counted once per partition); `summary` — totals over
  the selection, `instrument_pairs` = union over the selected files; `selection`
  — the applied selection (served envelope).
* A pair present in two partitions (e.g. `(RELIANCE, EQ)` in legacy13 and as
  distinct `listing_symbol` values in udiff34) is counted once per partition and
  once in the summary union — the index's own `counts.instrument_pairs` is
  reproduced by the full selection.

## 5. Q2 — exact contract

Public API: `serving.query_date_range(baseline, index, date_from, date_to) ->
tuple of rows` (query id `Q2-date-range`).

* **Bounds:** both inclusive ISO business dates (`YYYY-MM-DD`); malformed
  bounds (non-string, non-ISO, not a calendar date) fail closed with
  `QueryError("query-input", …)`; `date_from > date_to` is an empty range →
  empty result, not an error.
* **Narrowing + re-check:** candidate files come from the index's per-file
  `business_date` min/max (disjoint or unknown bounds → skipped); every row of a
  candidate file is re-checked against its **exact as-published**
  `business_date` (ISO string, exact comparison, no normalisation). A row whose
  `business_date` is absent/blank/non-ISO can never match — it is skipped,
  never modified, never defaulted.
* **Served row:** the canonical row exactly as stored (`source_values`
  as-published text — `None` = absent in that family, `""` = blank as
  published, neither defaulted; non-gating flags; the row's own D05 §8
  provenance block) plus the serving envelope
  `{query, date_from, date_to, source_file, source_file_family,
  source_file_year}`. **`raw_line` is never served.**
* **Ordering:** the established deterministic 5-tuple
  `(business_date, format_family, source_file_year, source_file,
  source_line_number)` shared with Q3.
* **Read-only:** candidate files streamed, nothing written; a query failure can
  never corrupt durable data (D16-09 invariant).
* Unparseable row / row without contract keys → `QueryError("query-scan", …)`
  fail closed (same behaviour as Q3).

## 6. Index format change — `serving-index/1.0` → `serving-index/1.1`

* Per file entry, two derived values only: `business_date_min`,
  `business_date_max` — min/max over the file's as-published `business_date`
  values, computed in the **same single linear read-only build pass** (no second
  pass, no row content stored; a file without a dated row carries `null`
  bounds). No clock/absolute-path/host value; canonical JSON; byte-identical
  across independent builds (order-independent min/max).
* **Compatibility/refusal:** `load_index` requires `format == "serving-index/1.1"`
  exactly — documents with `serving-index/1.0` (or any unknown marker) are
  refused fail-closed (`ServingIndexError("index-load", …)`); the remedy is a
  rebuild (deleting class (4) is never a data event). Stale-package refusal
  (package-identity check) and digest-sidecar verification are unchanged.
* No second index, no new persistence mechanism, no full-package row scan per
  date-range query.

## 7. Technology note (D23 §13/§18 item 3)

No new technology is selected, named, or implied: the slice reuses D24's
recorded mechanism — Python 3 standard library only, one canonical-JSON
class-(4) index file in the caller-supplied state dir (outside the package),
in-process streaming, CLI consumer. Constraint 7 (MD-10 grading of a physical
persistence selection) is not triggered: no new physical persistence was
selected. D23 §13 constraints 1–6 and 8–9 remain satisfied (single-user, no
auth/RBAC/multi-user, no PostgreSQL/enterprise, class-(4) consistency, no
canonical reinterpretation, rebuildable, recorded, no live market-data access).

## 8. Changed-file inventory (content digests, git blob identity)

| File | Blob SHA-256 | Lines | Change |
|---|---|---|---|
| `src/serving/__init__.py` | `6dbdd694be2861e982d8b706afb89063927fa23b` | 72 | exports Q1/Q2 API + query ids; boundary docstring updated |
| `src/serving/index.py` | `f6f04a626e0ac64f04ced188c19ade984bdb4c47` | 204 | format 1.1; per-file business_date min/max in the single build pass |
| `src/serving/query.py` | `da8bfdd84326af79e66bfb3d35d31e67fc857785` | 299 | `query_dataset_summary` (Q1), `query_date_range` (Q2), ISO-date validation, `QueryError` check/detail house-style constructor |
| `src/serving/cli.py` | `0b92c8d36d5be935f3640a52308c605f4e12bb01` | 226 | `dataset` subcommand; `query` Q3/Q2 mode exclusivity + `--from`/`--to`; `QueryError` → fail-closed JSON, exit 2 |
| `tests/test_serving_query.py` | `4af540ec9d9ac0f956f860fe90f88d0fe2e6ece7` | 468 | +20 fixture tests: Q1 (6), Q2 (10), index 1.1 (3), incl. format refusal |
| `tests/test_serving_baseline.py` | `1fdccbe4599f38c32716a50e62ccbfe97db3a69a` | 197 | +1 read-only discipline test over Q1/Q2 operations |
| `tests/test_serving_m2_integration.py` | `8fee03cc7bfc45b031742393001126c052211208` | 168 | +2 `D24_M2_ROOT`-gated real-package tests (Q1 summaries, Q2 date range) |
| this record | `docs/implementation/D30A_Q1_Q2_SERVING_QUERY_SLICE.md` | — | new |

Nothing else changed: no engine (`src/nse_engine`), runner (`tools/`), spec,
governance, fixture builder, or evidence file was modified. `.gitignore`
unchanged. No serving state file is committed.

## 9. Tests executed and exact results

Command (house runner): `PYTHONPATH=src python3 -m unittest discover -s tests -t .`

* Focused (before full suite): `tests.test_serving_query tests.test_serving_baseline
  tests.test_serving_m2_integration` → **55 run, OK, 5 skipped** (the 5 skips are
  the `D24_M2_ROOT`-gated real-package tests — 3 pre-existing + 2 new — skipped
  with the recorded reason, never represented as passed).
* Full suite: **536 run, OK, 5 skipped, 0 failures** (531 passed). Baseline was
  514 run / 511 passed / 3 skipped → +22 tests, all new.
* CLI smoke (fixture package, manual): `build` → index built (counts 4 files / 9
  rows / 6 pairs); `dataset` (all / `--family legacy13 --year 2016`) → correct
  partition table and summaries; `query --from 2016-01-04 --to 2017-02-06` → 7
  rows in deterministic order; `query RELIANCE EQ` (Q3) unchanged (3 rows);
  mode conflict / neither mode / malformed date → fail-closed JSON, exit 2.
* Index determinism (executed): two independent builds byte-identical incl. the
  new fields; `serving-index/1.0` and unknown-format documents refused
  fail-closed; stale-package refusal unchanged; read-only discipline: package
  bytes byte-identical before/after all Q1/Q2 operations (per-file digest
  comparison).

## 10. Non-drift statement

No governance artifact was modified (D16/D21/D22/D23/D05/D08/D12/D14/intent
unchanged). No canonical historical data, qualification record, inventory, or
evidence artifact was created, modified, or re-qualified. No engine or runner
module changed. No technology beyond the recorded class-(4) file mechanism was
selected, named, or implied. No live NSE/provider access exists or is attempted.
Single-user personal-use scope and all D16 §13 non-goals preserved (no
authentication, RBAC, multi-user, PostgreSQL, or enterprise architecture). No
D21 CHANGED-resolution machinery, no registry, no incremental ingestion, no
raw-byte/raw_line serving, no eligibility/DEC-1, no computed analytics beyond
derived state. M2-only scoping preserved: class-(2) incremental publications and
class-(3) registry are absent and are never fabricated.

## 11. D23 §18 closure-battery delta

Affected items (no new closure items invented):

* **Item 3 (technology decisions recorded):** no new selection — §7 above
  records that the existing recorded mechanism is reused and constraint 7 is
  not triggered.
* **Item 4 (contract conformance):** D16-10 Q1/Q2 semantics demonstrated by the
  new fixture tests (exact as-published comparison, None-vs-blank, provenance,
  fail-closed inputs); D16-08/09/12/16-07 obligations preserved (raw_line
  excluded, read-only, class-(4) derivation, rebuildable).
* **Item 7 (deterministic/rebuildable serving state):** extended — the 1.1
  index is byte-identical across independent builds and rebuilds; deletion/
  rebuild of the state dir remains never a data event.
* **Item 8 (query-boundary proof):** public query surface is now
  `query_instrument` (Q3) + `query_dataset_summary` (Q1) +
  `query_date_range` (Q2) — all within the fixed Q1–Q10/saved-query boundary;
  no other query path exists.
* **Item 10 (tests):** §9 — 536 run / 531 passed / 5 skipped (all skips the
  gated real-package legs).
* **Item 11 (complete artifact inventory):** §8 — every changed file with
  path and digest.
* **Item 12 (remote durability + independent remote verification):** completed
  by this task's publication step (commit/tree/blob/path verified against the
  remote; prior governing blobs intact).

Items 1, 2, 5, 6, 9, and the D23-level closure assessment stand as established
by D24/D26 (real-M2 legs closed by the user-executed Windows evidence,
reconciled in D26). The real-M2 legs of Q1/Q2 specifically are **staged**
(`D24_M2_ROOT`-gated tests in §8/§9) and **not yet executed** against the
qualified package — that execution is a separate user Windows step per the
established D26 handoff pattern; it is not claimed here.

## 12. Final status

> **D30A = COMPLETE / DURABLE / REMOTELY VERIFIED** (subject to this task's
> publication-step verification: single FF commit to the session branch, remote
> commit/parent/tree/blob/path verified, `main` unchanged at
> `69977017ffca944921f231d7904347bc582b6392`).
>
> Q1 and Q2 are implemented, fixture-tested, and CLI-exposed under the standing
> D30a slice boundary. The real-package Q1/Q2 tests are **staged/gated, not
> passed** (never executed in this environment). No promotion of this commit or
> of D25/D26/evidence to main was performed. Remaining authorized work
> (later slices, no new authority): Q4–Q10 (Q7/Q8/Q9/Q10 metadata parsers next
> in dependency order, then Q4/Q5/Q6), saved-query state, Dashboard/Explorer
> presentation + transport/frontend selection (D23 §13/§14).
