# D32 — Q8 DATA-QUALITY VIEWS

## 1. Task identity and purpose

**D32** — the next serving slice under the standing **D23** authority (D24 §18
"remaining authorized work (b) Q1–Q2, Q4–Q10 and saved-query state per D16-10 —
no new authority required"), building on D30a (Q1/Q2), D30b (Q9), and D31
(Q7), reusing the D30b Q8 contract assessment.

This slice implements **Q8 data-quality views** (D16-10 Q8):

* **flag censuses** — per governed D05 §5 flag name, the number of canonical
  rows carrying that flag (derived in the class-(4) index build pass);
* **unresolved-state records** — `w2/unresolved.jsonl` served as published,
  with an absent file as a legitimate no-records state;
* **quarantined counts** — the governed `RUN_RECORD` count, corroborated by
  the `RUN_COMPLETE` marker;
* **reconciliation aggregates** — by `result` and by `tier`, re-computed from
  the as-published `RECONCILIATION.jsonl` (D31 parser) and corroborated
  against the completion marker;
* **D21 CHANGED findings** — explicitly absent (the class-(3) registry does
  not exist in the M2-only release; nothing is ever fabricated).

No new authority is requested. Q1/Q2/Q3/Q9/Q7 semantics are unchanged; Q10,
Q4–Q6, saved queries, UI/transport, incremental ingestion, D21 machinery,
raw-content serving, and every other boundary remain untouched.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged by this task |
| Session branch at work | `arena/9021d1a1-nse-historical-data-engine` at `7bb8ebe22a0a1296b8d3c896c9ed889a22668a05` (D31, parent Q9 `14843ac8…`); this slice commits on top |
| Evidence branch | `evidence/d26-real-m2-execution-20261009` at `0dda72bef051aa769340badda56997b42a1723f8` — untouched |
| Local state | 23rd sandbox `.git` rollback found at task start (HEAD `89ce965…`, re-shallow, three stale `M` files). Established non-destructive procedure: `fetch --unshallow origin` → D31 object present → ancestry `89ce965… → 7bb8ebe…` = YES → hash audit: all three stale files byte-identical to their D31 versions, spot-checked "untracked" files byte-identical to the D31 tree → `update-ref` → `read-tree` → mixed `reset`. No clean/restore/force/branch-switch; no remote ref moved; worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed). Stale `__pycache__` cleared before testing |

Real-M2 facts used (verified from the repository-durable D11 transfer
evidence, `evidence/D11_REPLAY_QUALIFICATION_20261009/…tar.gz`):
`RUN_RECORD.counts = {data_lines, members, observations, quarantined, rows}`
with `quarantined = 0`; the `RUN_COMPLETE` marker carries
`quarantined = 0` and a pre-computed `reconciliation` block
(`by_result`, `by_tier`, `records = 39402`); the real package contains
`w2/unresolved.jsonl` (runner-written, class-(3) "provenance / evidence —
never resolved").

## 3. D23 authority and scope

Implemented within D23 §8/§10/§17(a) and the standing D24 §18(b) remainder
list. D23 §9 exposure boundary respected — Q8 serves aggregate data-quality
facts and the as-published unresolved-state records (evidence class, never
canonical row values; `raw_line` never involved). D23 §12 class-(4) rules
respected — the flag census lives in the index (pure derivation, deterministic,
rebuildable, deletable without a data event); Q8 itself creates no state. M2-
only scope preserved — no registry entries or D21 findings fabricated.

## 4. Q8 — exact contract

Public API: `serving.query_data_quality(baseline, index) -> dict` (query id
`Q8-data-quality`), plus `serving.parse_unresolved(baseline) -> list`.

**A. Flag census.** Derived in the index build pass (one linear scan, same
pass as the instruments/date bounds): per row, each entry of the row's
`flags` list (D05 §5; the governed per-row flag records with `name`,
`severity`, `detail`, `reference`) is counted under its `name`. No flag gates
anything (`GATING_FLAG_NAMES = ()` in `contract`, D05 §5 hard rule) — the
census is informational. A row without a `flags` list carries none; a flag
entry that is not a record with a non-empty string `name` is a package
integrity failure (`ServingIndexError("index-scan")`). The census counts what
the canonical rows publish — no invented flags, no normalization.

**B. Unresolved-state records.** `w2/unresolved.jsonl` is parsed **only when
present and valid**: each line must be a JSON record carrying a non-empty
string `kind` and a string `state` (the fields every runner record kind
carries — `governance-dependency`, `calendar-label-status-counts`,
`calendar-unresolved-date`, `identity-non-promotion`,
`cross-era-boundary-residual`, per `tools/i4_runner/i4_runner.py`). An absent
file is a legitimate state meaning no unresolved records: served as
`{"present": false, "record_count": 0, "records": []}` — never an error,
never fabricated. A present file with an unparseable line or a record missing
`kind`/`state` fails closed (`QueryError("unresolved-scan")`). Records are
served as published, in file order.

**C. Quarantined count.** Primary source: `RUN_RECORD` `counts.quarantined`
(runner-written, post-processing). Corroborated by the `RUN_COMPLETE` marker's
`quarantined`. Missing/non-integer on either side, or disagreement between
the two governed records, fails closed (`QueryError("quarantine-count")`).
Zero is preserved as zero; a missing value is never substituted with zero.

**D. Reconciliation aggregates.** The package's `RECONCILIATION.jsonl` is
parsed with the shared D31 parser (`serving.parse_reconciliation` — the
runner's 14-field schema, as published, fail closed) and aggregated into
`by_result` (governed match/divergence/not-comparable/observed semantics) and
`by_tier` (governed A/G/C/E semantics), plus `record_count`. When the
`RUN_COMPLETE` marker carries its own `reconciliation` block (the runner
writes one — the real M2 marker has `by_result`, `by_tier`, `records =
39402`), the re-computed aggregates must agree with it (each field the marker
carries is checked; disagreement fails closed,
`QueryError("reconciliation-aggregate")`). Historical findings are never
reinterpreted or rewritten.

**E. D21 CHANGED findings.** Served as
`{"present": false, "status": "absent-in-m2-only-release", "findings": [],
"note": …}` — the same explicit absence status the Q9 registry
representation uses (constant reused from `serving.archive`), extended with
an empty findings list. No CHANGED finding is ever fabricated and no D21
resolution machinery is implemented.

**Result document** (canonical JSON at the CLI boundary):
`{"query": "Q8-data-quality", "flag_census": {…}, "quarantine": {"count": n},
"unresolved": {"present", "record_count", "records"}, "reconciliation":
{"record_count", "by_result", "by_tier"}, "changed": {…}}`.

Read-only: the query opens at most `w2/unresolved.jsonl` and
`RECONCILIATION.jsonl` (row files are read only by the index build); it
writes nothing. Deterministic: all aggregates are order-independent
counts; the document is canonical JSON at the CLI boundary.

## 5. Index-format change — `serving-index/1.1` → `serving-index/1.2`

* `build_index` (the existing single deterministic pass) now also collects the
  global `flag_census` (top-level document field).
* `INDEX_FORMAT` is `serving-index/1.2`; `load_index` fails closed on any
  other format — including `1.1` (older) and unknown formats.
* Rebuild determinism and stale-index refusal (package-identity check) are
  unchanged and test-verified; the class-(4) state remains deletable without
  a canonical-data event.
* `src/serving/query.py` docstring/error-message references updated 1.1 → 1.2.

## 6. Reuse (no duplicate parsers)

* Q9: the serving layer's metadata discipline and the
  `absent-in-m2-only-release` representation (`REGISTRY_ABSENT`, reused for
  the D21 CHANGED absence).
* D31: `parse_reconciliation` (runner 14-field schema) is the sole
  RECONCILIATION parser; Q8 aggregates from it.
* Existing `open_baseline` (RUN_RECORD/RUN_COMPLETE parsing + verify-04/07),
  canonical-row access discipline, error (`QueryError`/`ServingIndexError`)
  and canonical-JSON conventions.

## 7. Fixture changes (test-only, minimal)

`tests/serving_fixtures.py`:

* **Two deliberate data-quality rows** for the flag census: TCS 2016-01-04
  ISIN → `INE000000006` (12-char IN ISIN failing the ISO 6166 mod-10 check
  digit → governed `isin_invalid_checkdigit` flag) and TCS 2016-01-05 ISIN →
  `INE123` (invalid length → governed `isin_invalid_length` flag). Both are
  informational, never gating (D05 §5); the rows are retained.
* **Base ISINs corrected to be genuinely valid** (one digit each): the
  fixture's RELIANCE ISIN `INE002A01017` → `INE002A01018` (4 rows) and the
  udiff TCS ISIN `INE467B01024` → `INE467B01029` (1 row). The D24-era values
  silently failed the mod-10 check (the engine had been flagging them all
  along); the fixture now matches its documented intent — base rows valid,
  only the two deliberate rows flagged — and the census isolates them exactly.
* No w2 fixture in the base package (absence is the base state); the
  populated-unresolved test builds a re-signed variant package in-test.
  No GOVERNED_INPUTS or reconciliation-content changes beyond D31.
* The fixture package remains deterministic (byte-identical rebuilds); the
  marker/manifest/RUN_RECORD digests are recomputed by the builder.

## 8. Changed-file inventory (content digests, git blob identity)

| File | Content SHA-256 | Lines | Change |
|---|---|---|---|
| `src/serving/quality.py` | `92090361c430ad402c1a19ef1ae0e08823cc0a200c31b3471c00a5bdbfa140db` | 208 | **new** — Q8 query, `parse_unresolved`, quarantine cross-check, reconciliation aggregation + marker corroboration, D21 absence |
| `src/serving/index.py` | `9b13e5c79e60479a1e94f1007d1d7aac30bcf0f66e407fca0acbe0fe8a6dafe7` | 221 | format 1.2; global `flag_census` in the single deterministic build pass; malformed-flag fail-closed |
| `src/serving/query.py` | `4e6e871c6ae2ac79423a7b48f07d1f7792e15f2ffd41f035ddf388d4722b9053` | 299 | docstring/error-message format references 1.1 → 1.2 |
| `src/serving/__init__.py` | `b6cd94bd099a56430e2845381b1e7b0796be20414646339673464bd1256827a5` | 111 | exports Q8 API + `parse_unresolved`; boundary docstring mentions Q8 |
| `src/serving/cli.py` | `6a94195425571b247d3bf23ece1cd6ccddb96cd09608078b71908b87a9e174b8` | 295 | `quality` subcommand (`--package`, `--state`, optional `--m2`); docstring |
| `tests/serving_fixtures.py` | `31ef7f8ad04e4a23bdd1febf26aa8b9590fb6e7876ba07828d02b701ed38fa8d` | 449 | two deliberate ISIN defects (Q8 census); base ISINs corrected to valid; ISIN policy documented |
| `tests/test_serving_query.py` | `1a1cc5a3e1b15d79d4595bbf6bfafcb768f860b1cc1a4e3540554788990065b1` | 470 | index-format test class updated to 1.2 (1.1 now in the refusal list) |
| `tests/test_serving_quality.py` | `e610df6ddd93173110295a052d510214b829ad750e59df9e053a8f33bcb4c365` | 376 | **new** — 19 tests (census, determinism, format/stale refusal, quarantine, unresolved states, reconciliation aggregates, D21 absence, discipline, regression) |
| `tests/test_serving_m2_integration.py` | `dd66e8faa5892b5c3340541cdc320d787f4ffd78ee0ac06a25b8df6d3df081ec` | 248 | +1 `D24_M2_ROOT`-gated real-package test (Q8 over the actual M2 baseline) |
| this record | `docs/implementation/D32_Q8_DATA_QUALITY_VIEWS.md` | — | new |

Nothing else changed: no engine (`src/nse_engine`), runner (`tools/`), spec,
governance, D01 evidence, or w2 evidence file was modified. `.gitignore`
unchanged. No serving state file is committed.

## 9. CLI — `quality` subcommand

`python3 -m serving.cli quality --package <root> --state <state> [--m2]`

* Requires the class-(4) index (`--state`) — the flag census is an index
  fact, so Q8 follows the `dataset` subcommand conventions exactly: exit
  `0` = ok (canonical JSON on stdout); exit `3` = baseline verification /
  index (missing, stale, format) / query failure with the JSON fail
  envelope; exit `2` = argparse usage. No partial results on failure.
* Read-only vs the package.

## 10. Tests executed and exact results (actual, this session)

Runner: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (house
runner; pytest not installed).

* **Focused (new module)** — `PYTHONPATH=src python3 -m unittest
  tests.test_serving_quality`: **Ran 19 tests — OK** (19/19 pass): flag
  census counts the governed flags exactly (`{isin_invalid_checkdigit: 1,
  isin_invalid_length: 1}` for the fixture) and matches a direct stored-row
  scan; census determinism + rebuild byte-identity; index format 1.2 +
  1.1/unknown format refusal; stale-index refusal still enforced; quarantine
  zero preserved (both governed records agree) + inconsistent-count and
  missing-count fail-closed; absent unresolved file → explicit empty state;
  populated unresolved variant served as published (2 records); malformed
  unresolved (unparseable line / missing kind / non-string state) fails
  closed; reconciliation aggregates by result and tier match the as-published
  records; empty reconciliation a valid state (marker updated to agree);
  marker-agreement mismatch fails closed; D21 CHANGED explicit absence
  (exact document, empty findings); canonical JSON + deterministic ordering;
  package byte identity before/after successful and failing operations;
  Q1/Q2/Q3/Q7/Q9 regression coverage (all unchanged after a Q8 operation).
* **CLI smoke** — `quality` on the fixture: exit 0, canonical JSON (census
  `{isin_invalid_checkdigit: 1, isin_invalid_length: 1}`, quarantine 0,
  unresolved absent, reconciliation 4/`match`/tier E, changed absent);
  missing state → exit 3 JSON fail envelope.
* **Full suite** — **Ran 592 tests in 86.5s — OK (skipped=8)**. 592 = 572
  (D31) + 19 (new module) + 1 (new gated M2 test). Skipped = 8: the seven
  pre-existing `D24_M2_ROOT`-gated real-package legs **plus the new Q8
  real-package leg** — all gated because `D24_M2_ROOT` is unset in this
  environment; reported as skipped, never as passed, and the fixture tests
  never stand in for them (D24 record §13). No unrelated qualification
  suite was rerun.

## 11. Real-M2 status — staged, gated, NOT executed here

The qualified M2 baseline (21.12 GB package, `DEFAULT_M2_SPEC`) is **not
provisioned in this environment** (sandbox disk ≈ 20.66 GB available <
package size; no Windows execution from Arena; the Windows-held package is
not transferred). The real-package Q8 leg is implemented and gated in
`tests/test_serving_m2_integration.py::M2RealPackageIntegrationTests::test_q8_data_quality_over_real_baseline`
(D24_M2_ROOT-gated like its siblings) and asserts: the census is a census of
non-negative counts; the quarantine count is preserved as published (0); the
reconciliation aggregates corroborate the completion marker (39,402 records,
`by_result`/`by_tier` equality); the real `w2/unresolved.jsonl` is parsed as
published with `kind`/`state` on every record; D21 CHANGED findings are
explicitly absent; output is deterministic. It executes only where the
environment provides the package via `D24_M2_ROOT`; until then it is
reported **skipped (pending baseline provisioning), not passed**.

## 12. Non-drift statement (D23 §18 items 5/12)

* **Read-only vs the package:** Q8 opens at most `w2/unresolved.jsonl` and
  `RECONCILIATION.jsonl`; `test_package_byte_identity` digests every package
  file before and after a successful **and** a failing Q8 call —
  byte-identical.
* **No canonical-data mutation:** no engine, runner, spec, governance,
  evidence, or D01 file was modified (diff inspection: only the nine
  implementation/test files + this record). The D24-era fixture ISIN values
  were corrected **in the fixture only** (test-only synthetic data) to match
  the fixture's documented intent — no package, engine, or runner change.
* **Class-(4) discipline preserved:** the index remains a pure, deterministic,
  rebuildable derivation (rebuild byte-identity test-verified); stale-index
  refusal test-verified; format refusal now covers 1.0, 1.1, and unknown
  formats; deleting the state is never a data event.
* **M2-only contract preserved:** the D21 CHANGED block is the explicit
  absence representation; no registry entries, no resolution machinery, no
  raw content exposed.

## 13. D23 §18 closure-battery delta

* **Item 4 (contract conformance):** Q8 semantics are exactly D16-10 Q8 as
  scoped by D22 §§5A/6 (data-quality views: flag censuses, unresolved-state
  records, quarantined counts, reconciliation aggregates, registry/CHANGED
  absence) under D21 §14 (candidate/CHANGED content is never
  canonical-serving-eligible — represented as explicitly absent while the
  registry is absent). D05 consumer obligation (MD-09): aggregates are
  derived from the canonical rows' governed fields (D05 §5 flags,
  §8 provenance untouched); as-published values preserved throughout.
* **Item 8 (query-boundary):** the only new query path is
  `Q8-data-quality` inside `serving.quality`, exposed as the `quality` CLI
  subcommand. Q10, Q4–Q6, and saved queries remain unimplemented.
* **Item 10 (tests):** §10 — focused 19/19 OK; full suite 592 executed, OK,
  8 skipped (all `D24_M2_ROOT`-gated real-package legs, reported skipped,
  never passed).
* **Item 11 (complete artifact inventory):** §8 — all artifacts with path
  and content digest; nothing else changed.
* **Item 12 (remote durability):** this commit is fast-forward-only onto
  `7bb8ebe2…` on the session branch and is independently remote-verified
  (commit/parent/tree/changed paths/blobs) before this task is declared
  complete; `origin/main` remains `69977017…` (promotion is the user's
  separate step — not performed).

## 14. Final status

D32 (Q8 data-quality views) **COMPLETE** — implementation, index format 1.2,
fixture alignment, tests, record, single fast-forward commit, remote
verification. Remaining D30b/D31-plan slices (Q10 qualification/evidence
views; Q4 filtering; Q5/Q6 w2 query features; saved-query state) are **not
started** and require their own separately-scoped tasks under the same
standing authority.
