# D34 — Q4 SERVING QUERY FILTERS (segment / series / source / instrument_type)

## 1. Task identity and purpose

**D34** — the next serving slice under the standing **D23** authority (D24 §18
"remaining authorized work (b) Q1–Q2, Q4–Q10 and saved-query state per D16-10 —
no new authority required"), selected as the smallest justified next milestone
by the Task 53 readiness investigation
(`docs/investigations/TASK53_NEXT_MILESTONE_READINESS.md`), building on
D30a (Q1/Q2), D30b (Q9), D31 (Q7), D32 (Q8), and D33 (Q10).

This slice implements **Q4** (D16-10 Q4: "segment / market-type / series /
trading-status filtering (as-published field values)") as governed, exact-value
filtering over the D05-established filterable fields:

* `series` — both format families (D05 §3.1 "string, always");
* `segment` (`Sgmt`), `source` (`Src`), `instrument_type` (`FinInstrmTp`) —
  UDiFF-only descriptive attributes (D05 §3.1 NON-ASSUMPTION: exact stored
  value only; never inferred type semantics).

No new authority is requested. Q1/Q2/Q3/Q7/Q8/Q9/Q10 semantics are unchanged;
Q5, Q6, saved queries, UI/transport, index changes, incremental ingestion, D21
machinery, raw-content serving, and every other boundary remain untouched.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged by this task |
| Session branch at work | `arena/9021d1a1-nse-historical-data-engine` at `3a0fd6ec01c8a62ae1c2b75204033e5387d1392f` (Task 53 record, parent D33 `059590b…`); this slice commits on top |
| Evidence branch (remote-verified) | `evidence/d26-real-m2-execution-20261009` at `0dda72bef051aa769340badda56997b42a1723f8` — unchanged |
| Local state | 26th sandbox `.git` rollback found at task start (HEAD `89ce965…`, re-shallow, stale `M` files). Established non-destructive procedure: `fetch --unshallow origin` → Task-53 object present → ancestry D33 → Task 53 = YES → **full worktree byte audit vs the Task-53 tree (180 files: 0 missing, 0 differing)** → `update-ref` → `read-tree` → mixed `reset` (ref/index only). No clean/restore/force/branch-switch; no remote ref moved; worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed) |

## 3. Governing contract and exact supported fields

* **D16-10 Q4** — "segment / market-type / series / trading-status filtering
  (as-published field values)" (D22 §5 E1: **READY BY EXISTING CONTRACT** —
  as-published field values on canonical rows).
* **D05 §3.1 field table** — pins the filterable vocabulary: `series`
  (both families, always present), `segment`/`source`/`instrument_type`
  (UDiff-only descriptive attributes; legacy rows carry them absent, `None`;
  NON-ASSUMPTION: "do not use as type filters beyond exact stored value" —
  exact-value filtering is exactly what is permitted; type inference is not).
* **Unmapped D16-10 dimension — documented, not invented:** "trading status"
  has **no** corresponding D05 canonical field (verified: zero occurrences of
  a trading-status field in the D05 spec; it appears only as a UI filter
  concept in the intent §9 Data-Explorer direction list). Per the Task 54
  contract rule ("if an apparent requirement cannot be mapped to an
  established field without inventing semantics, stop that specific mapping,
  document the evidence, and report the smallest unresolved issue"), that
  dimension is **not implemented and not mapped**: a requested
  `trading_status` filter fails closed as an unknown Q4 field. "Market type"
  is covered by the exact-value filters on the two established market
  attributes (`segment`, `source`) — the serving layer exposes as-published
  field filters; any UI label mapping is a presentation concern (D16-11), not
  a serving semantic.
* **D23 §10** — no computed analytics beyond as-published values + derived
  state; no arbitrary query semantics. Q4 is exact-value equality on
  as-published values only: no normalisation, no case/whitespace folding, no
  expression language, no aliases.

## 4. Q4 — exact contract

Public API: `serving.query_filters(baseline, index, filters) -> tuple` (query
id `Q4-filter`; `serving.Q4_FILTER_FIELDS` = the governed vocabulary).

* **`filters`** — a mapping of one or more of `series`/`segment`/`source`/
  `instrument_type` to the exact as-published value (a string; the empty
  string is a legal value matching exactly-blank stored values). Malformed
  requests fail closed with `QueryError("query-input")` **before any row is
  served**: non-dict, empty mapping, unknown field (no undocumented aliases —
  including `trading_status`, `market_type`, `isin`), non-string value.
* **Exact-value equality only** — `source_values[field] == value`; no
  normalisation/inference/coercion. **Absent never matches**: a row whose
  field value is absent (`None` — the legacy family for the UDiFF-only
  fields) can never match any requested value, including `""`; blank (`""`)
  matches exactly-blank stored values and nothing else. The absent/null/blank/
  populated distinctions of the canonical rows are preserved as-is (D05 §2
  rule 3).
* **AND semantics** — a row is served only when **every** requested field
  matches exactly (the single contract-supported composition; one value per
  field — no per-field allowlists, which would be invented semantics).
* **Format-family handling** — `series` is checked on every row of both
  families; `segment`/`source`/`instrument_type` match only where the family
  stores them, by the same absent-never-matches rule (legacy rows never
  match those fields).
* **Results** — the canonical row exactly as stored (`raw_line` never served)
  plus the Q4 serving envelope (`query`, `filters`, `source_file`,
  `source_file_family`, `source_file_year`). An empty result is a valid
  result (not an error).
* **Determinism** — the established 5-tuple ordering shared with Q2/Q3
  ((business_date, format_family, year, source file, source line number));
  identical requests over identical inputs produce identical canonical JSON.
* **Read-only** — row files are streamed; nothing is written; no new data
  store or mutable serving state.

**CLI:** the existing `query` subcommand gains a Q4 mode: repeatable
`--field NAME=VALUE` (AND semantics). The four modes remain mutually
exclusive (Q3 `symbol series`, Q2 `--from/--to`, Q4 `--field`, Q7
`--file/--line`); a wrong combination is a usage failure (exit 2) with the
JSON envelope. Duplicate field, or a `--field` value without `=`, is a usage
failure (exit 2); an unknown field / malformed filter value is a query-input
failure (exit 2, `query-input` check). Success: exit 0, canonical JSON
`{query, filters, result_count, rows}`. Baseline/index failures: exit 3 as
established.

## 5. Index decision

**No index change.** Q4 operates on the canonical rows and the existing
class-(4) index (serving-index/1.2): the index supplies the row-file set;
there is no per-field census, so every row file is a candidate and each row is
re-checked against its exact as-published values — the same bounded-scan cost
class as a Q2 query without date narrowing. No class-(4) data is added, so
deterministic rebuild, stale-index refusal, and format refusal are untouched
(regression-verified). An index extension (e.g., per-file field censuses)
would be a future optimization requiring the D32 pattern (version bump,
fail-closed on unsupported formats) — not required by the contract and not
done.

## 6. Reuse (no duplicate mechanisms)

* Q2/Q3 row-streaming, `QueryError`, the 5-tuple ordering, and the CLI
  `query` subcommand / mutual-exclusion / envelope conventions;
* `open_baseline` + class-(4) index loading (no change);
* the established resigned-variant test pattern (D31/D32) — extended here to
  re-sign per-partition manifests as well, because this slice's blank-value
  test variant modifies a partition row file (covered by `manifests/*.sha256`,
  verify-05).

## 7. Fixture alignment

**No fixture data was modified.** The existing fixture already exercises the
contract surface: all 9 rows `series='EQ'`; the 7 legacy rows carry
`segment`/`source`/`instrument_type` absent (`None`); the 2 UDiff rows carry
`CM`/`NSE`/`STK`. The blank-value distinction is tested with an in-test
re-signed variant (one UDiff row's `segment` set to exactly `""`), not by
changing the fixture.

## 8. Changed-file inventory (content digests, git blob identity)

| File | Content SHA-256 | Lines | Change |
|---|---|---|---|
| `src/serving/query.py` | `685f0c36d99213a440df7910597876aa6a9404acb8c3e35be97ae4575abc8d98` | 396 | `query_filters` (Q4) + `FILTER_QUERY_ID` + `Q4_FILTER_FIELDS` with the D05 contract basis documented |
| `src/serving/cli.py` | `1e4cc8c942a1873d4a1af98c7237d1b48ca06216e9c10ff1846f82ae6a03f97e` | 357 | Q4 mode of `query` (`--field NAME=VALUE`, repeatable); mutual exclusion over four modes; docstring |
| `src/serving/__init__.py` | `41081b5183c4037f6dc421259b4a5446821f2d115f7f52feffa61359c47a026f` | 124 | exports `query_filters`; boundary docstring mentions Q4 |
| `tests/test_serving_filters.py` | `d2a47b3c537493c645503075b6f2bc91d204e3bbae32edbe35662f3405765282` | 301 | **new** — 16 focused tests |
| `tests/test_serving_m2_integration.py` | `2af7aaae3af62c2896c97634144e62cb4a0bd8e86d0ab566dc155869d256f3cf` | 310 | +1 `D24_M2_ROOT`-gated real-package test (Q4 over the actual M2 baseline) |
| this record | `docs/implementation/D34_Q4_SERVING_QUERY_FILTERS.md` | — | new |

Nothing else changed: no engine, runner, spec, governance, fixture, index
format, D01, or evidence file was modified. No serving state file is
committed.

## 9. Tests executed and exact results (actual, this session)

Runner: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (house
runner; pytest not installed).

* **Focused (new module)** — `PYTHONPATH=src python3 -m unittest
  tests.test_serving_filters`: **Ran 16 tests — OK** (16/16 pass): governed
  field vocabulary; exact-value match (9/9 rows for `series=EQ`, as-published
  values round-trip, `raw_line` never served); non-match for different values
  (empty result valid, not an error); no normalisation/inference (`eq`,
  `"EQ "`, `cm`, `nse` never match); missing-field behavior (legacy rows never
  match the UDiFF-only fields, for no value including `""`); absent-vs-blank
  distinction (re-signed variant: `""` matches exactly the blanked row, the
  blanked row no longer matches `CM`, absent rows still match nothing);
  format-family-specific field handling (`series` both families; the UDiff
  fields only where stored); multiple simultaneous filters (AND semantics; one
  disagreeing field empties the result); deterministic result ordering
  (5-tuple sorted; canonical-JSON round-trip); invalid-filter handling
  (unknown field — including `trading_status`/`market_type`/`isin` — empty
  set, non-string values, non-dict mapping); fail-closed with no partial
  output (validation precedes any row serving; a later valid request still
  succeeds); package byte identity after successful and failing operations;
  Q1/Q2/Q3/Q7/Q8/Q9 regression (all unchanged after Q4 operations).
* **CLI smoke** — `query --field series=EQ`: exit 0, canonical JSON
  (`Q4-filter`, 9 rows, deterministic round-trip); combined
  `--field segment=CM --field source=NSE --field instrument_type=STK`: exit
  0, 2 rows; unknown field / duplicate field / mode conflict / no mode: exit
  2 JSON fail envelopes.
* **Full suite** — **Ran 630 tests in 78.2s — OK (skipped=10)**. 630 = 613
  (Task 53/D33) + 16 (new module) + 1 (new gated M2 test). Skipped = 10: the
  nine pre-existing `D24_M2_ROOT`-gated real-package legs **plus the new Q4
  real-package leg** — all gated because `D24_M2_ROOT` is unset in this
  environment; reported as skipped, never as passed. No unrelated
  qualification suite was rerun.

## 10. Real-M2 status — staged, gated, NOT executed here

The qualified M2 baseline (21.12 GB package) is not provisioned in this
environment (D25 §6.2 capacity block; Windows-held; not transferred). The
real-package Q4 leg is implemented and gated in
`tests/test_serving_m2_integration.py::M2RealPackageIntegrationTests::test_q4_filters_over_real_baseline`
(D24_M2_ROOT-gated like its siblings) and asserts **serving behavior only**
(no counts beyond contract facts, no corpus re-qualification): every served
row carries exactly the requested value; UDiFF-only fields match only
`udiff34` rows (absent-never-matches at corpus scale); AND semantics hold on
the combined filter; an impossible value yields the empty result; output is
deterministic. It executes only where the environment provides the package;
until then it is reported **skipped (pending baseline provisioning), not
passed** — and remains part of the Task 53 Plan 2 Windows execution track
(handoff pin to be re-pinned to the session HEAD at execution time).

## 11. Package immutability and non-drift (D23 §18 items 5/7/8)

* **Read-only:** Q4 streams row files only; `test_package_byte_identity`
  digests every package file before and after a successful **and** a failing
  Q4 operation — byte-identical. No serving state is created by a query.
* **Index discipline preserved:** no index format change; the existing
  rebuild-determinism, stale-index, and format-refusal behavior is
  regression-covered by the unchanged D30a/D32 suites (full suite green).
* **Query boundary preserved:** the only new query path is `Q4-filter`
  (D23 §18 item 8); Q1/Q2/Q3/Q7/Q8/Q9/Q10 are regression-verified unchanged.
* **No canonical-data mutation:** no engine, runner, spec, governance,
  fixture, or evidence file modified (diff inspection: only the five
  implementation/test files + this record).
* **M2-only contract preserved:** no registry entries, no D21 findings, no
  raw content, no computed analytics, no invented filter semantics.

## 12. D23 §18 closure-battery delta

* **Item 4 (contract conformance):** Q4 is exactly D16-10 Q4 over the D05
  §3.1 as-published field vocabulary, with the NON-ASSUMPTION honored (exact
  stored value only); the unmapped "trading status" dimension is documented
  and fail-closed, not silently redefined.
* **Item 8 (query-boundary):** one new query path (`Q4-filter`), one CLI mode
  on the existing `query` subcommand; Q5/Q6/saved queries remain
  unimplemented.
* **Item 10 (tests):** §9 — focused 16/16 OK; full suite 630 executed, OK,
  10 skipped (all `D24_M2_ROOT`-gated real-package legs, reported skipped,
  never passed).
* **Item 11 (complete artifact inventory):** §8 — all artifacts with path
  and content digest; nothing else changed.
* **Item 12 (remote durability):** this commit is fast-forward-only onto
  `3a0fd6ec…` on the session branch and is independently remote-verified
  (commit/parent/tree/changed paths/blobs) before this task is declared
  complete; `origin/main` remains `69977017…` (promotion is the user's
  separate step — not performed).

## 13. Final status

D34 (Q4 serving query filters) **COMPLETE** — implementation, tests, record,
single fast-forward commit, remote verification. **Smallest unresolved issue
reported (per Task 54 §3):** the D16-10 "trading status" dimension has no
D05 canonical field and is deliberately unmapped/unimplemented (fail-closed
as an unknown field); if it is ever required, it needs an explicit
contract/authority decision defining which governed field or derivation it
maps to. Remaining D30b/D31-plan slices (Q5 identity/association; Q6
calendar; saved-query state; UI/presentation) are **not started** and require
their own separately-scoped tasks under the same standing authority.
