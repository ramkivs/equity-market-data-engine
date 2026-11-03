# D31 — Q7 RECORD DETAIL AND ARCHIVE RECONCILIATION

## 1. Task identity and purpose

**D31** — the next serving slice under the standing **D23** authority (D24 §18
"remaining authorized work (b) Q1–Q2, Q4–Q10 and saved-query state per D16-10 —
no new authority required"), building on the D30a (Q1/Q2) and D30b (Q9)
slices.

This slice implements **Q7 record detail** (D16-10 Q7): a result that provides,
for exactly one canonical row:

1. the selected canonical row (served exactly as Q2/Q3 serve rows —
   as-published values, the row's own D05 §8 provenance block, serving
   envelope, `raw_line` excluded);
2. the applicable archive facts from `INPUT_MANIFEST.jsonl` (as published);
3. the reconciliation records applicable to that archive from
   `RECONCILIATION.jsonl` (as published; `[]` when none apply).

No new authority is requested. The Q2/Q3 query contracts are unchanged; Q8
quality views, Q10 evidence views, Q4 filtering, Q5/Q6 w2 parsing, saved
queries, UI/transport, incremental ingestion, D21 machinery, raw-content
serving, and every other boundary remain untouched.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged by this task |
| Session branch at work | `arena/9021d1a1-nse-historical-data-engine` at `14843ac887eb9bf91fcd10b4e40fdf71dbb148e3` (D30b/Q9, parent D30a `47323161…`); this slice commits on top |
| Evidence branch | `evidence/d26-real-m2-execution-20261009` at `0dda72bef051aa769340badda56997b42a1723f8` — untouched |
| Local state | 22nd sandbox `.git` rollback found at task start (HEAD `89ce965…`, re-shallow, three stale `M` files). Established non-destructive procedure: `fetch --unshallow origin` → Q9 object present → ancestry `89ce965… → 14843ac…` = YES → hash audit: all three stale files byte-identical to their `14843ac` versions, spot-checked "untracked" files byte-identical to the Q9 tree → `update-ref` → `read-tree` → mixed `reset`. No clean/restore/force/branch-switch; no remote ref moved; worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed). Stale `__pycache__` (invalidated by the rollback's mtime reset) was cleared before testing |

## 3. D23 authority and scope

Implemented within D23 §8/§10/§17(a) and the standing D24 §18(b) remainder
list. D23 §9 exposure boundary respected — Q7 serves the canonical row
(as-published values + the row's own D05 §8 provenance block) and package
metadata; `raw_line` (L1 retention) is never served, and no source archive
bytes are opened. D23 §12 class-(4) rules respected — Q7 reads the index and
produces no serving state (no rebuild, no write). M2-only scope preserved —
no registry entries or D21 findings are fabricated (Q7 serves no registry
field; the Q9 registry-absence representation is untouched).

## 4. Q7 — exact contract

Public API: `serving.query_record_detail(baseline, index, source_file,
source_line_number) -> dict` (query id `Q7-record-detail`), plus
`serving.parse_reconciliation(baseline) -> list`.

**Row identity (established; no new identifier introduced):**

* `(source_file, source_line_number)` — `source_file` is the row file exactly
  as served in the Q2/Q3 `serving` envelope (`serving.source_file`), and
  `source_line_number` is the row's canonical D05 §8 field (`source_line_number`
  — its line number within the source member, as stored on the row). Within
  one row file the field is unique (each member data line produces at most
  one row), so the pair selects exactly one row — stably, even where
  quarantined lines make the row's *position* in the file differ from its
  member line number (the engine assigns member line numbers
  `enumerate(lines[1:], start=2)`; quarantined lines leave no row).

**Row-to-archive join (schema-supported, digest-verified; no inference from
display symbols, dates, or file ordering):**

* The runner constructs row provenance strictly from governed D01 inventory
  facts (`tools/i4_runner/i4_inputs.build_source`: `source_archive =
  record["file_name"]`, `member_name = member_name`, `archive_sha256 =
  record["sha256"]`, basis `D01-inventory`), and the same runner writes those
  same facts into the `INPUT_MANIFEST` record. The join key is the provenance
  triple `(source_archive, member_name, archive_sha256)` matched against the
  record's `(file_name, member_name, archive_sha256_d01)`, corroborated by
  `row.format_family == record.engine_family`.
* Fail closed (no arbitrary archive, no fabricated facts) on: absent
  provenance block; absent identity fields (any triple element null); no
  matching record (identity inconsistency); more than one matching record
  (ambiguity); or a family inconsistency.
* An archive with no applicable reconciliation records returns `reconciliation: []`
  (absence is a valid state, not an error).

**Reconciliation applicability:**

* A `RECONCILIATION.jsonl` record applies to an archive exactly when its
  `input_identity` is a member scope (`scope == "member"`,
  `tools/i4_runner/i4_reconcile.member_scope`) whose `(root, relative_path)`
  equals the archive's. Corpus-scoped records apply to no single archive and
  are not served per-archive (they belong to the corpus-level Q8/Q10 views —
  out of scope). Applicable records are returned as published, in file order.

**Result document** (canonical JSON at the CLI boundary):

* `query: "Q7-record-detail"`;
* `row` — the selected canonical row minus `raw_line`, plus the Q7 serving
  envelope `{query, source_file, source_file_family, source_file_year,
  source_line_number}` (same envelope structure as Q2/Q3, Q7 selector fields);
* `archive` — the applicable INPUT_MANIFEST record, as published verbatim;
* `reconciliation` — the applicable records, as published, in file order.

**Metadata handling (reuse, not duplication):**

* INPUT_MANIFEST: the Q9 parser is reused — `parse_input_manifest` was made
  public in `serving.archive` (one INPUT_MANIFEST parser in the serving layer);
  its contract checks (unparseable line / non-record / missing contract key →
  `QueryError("input-manifest-scan")`) apply unchanged to Q7.
* RECONCILIATION: `parse_reconciliation` parses as published with the runner's
  shared 14-key schema as the contract (`tier, tier_description, check,
  input_identity, comparison_basis, governing_definition, expected, observed,
  delta, result, disposition, unresolved_state, note`); unparseable line,
  non-record, missing key, or non-record `input_identity` →
  `QueryError("reconciliation-scan")`. No values are invented, defaulted, or
  normalised; null and as-published strings pass through.

**Fail-closed:** unknown row file (`record-detail`), unknown row
(`record-detail`), malformed metadata (`reconciliation-scan` /
`input-manifest-scan`), input validation (`record-input`), and every identity
inconsistency all raise before any partial output is produced. Read-only: the
query streams one class-(1) row file and opens the two package metadata
documents; it writes nothing.

## 5. CLI — Q7 mode of the existing `query` subcommand

`python3 -m serving.cli query --package <root> --state <state> --file <row file>
--line <source_line_number>`

* `--file` = the row file exactly as served in a Q2/Q3 result
  (`serving.source_file`); `--line` = the row's canonical `source_line_number`.
* Mode exclusivity follows the existing convention: exactly one of symbol+
  series (Q3), `--from`/`--to` (Q2), or `--file`/`--line` (Q7) per invocation;
  a partial Q7 selector fails closed with its own message.
* Exit codes and the fail-closed JSON envelope are the established behavior:
  `0` = ok (canonical JSON), `2` = usage/verification/query failure, `3` =
  index/stale (as before). Existing Q2/Q3 results and semantics are
  unchanged (test-verified).

## 6. Fixture alignment (test-only, minimal)

`tests/serving_fixtures.py`:

* **RECONCILIATION writer** now emits the runner's shared 14-field schema
  (`_reconciliation_record` helper): honest **Tier E** records — "evidence-
  only observation (non-gating; no governing counterpart)" — with
  `input_identity` in the runner's `member_scope` shape and the fixture's own
  identity values, `comparison_basis`/`governing_definition` stating
  explicitly that this is a synthetic fixture with no governed counterpart,
  and `expected`/`observed`/`delta`/`result` as a real corroboration
  comparison (fixture-declared expected row count vs the engine's observed
  canonical row count; the build asserts agreement). Distribution across the
  four members: 2 + 1 + 1 + **0** records — the udiff member deliberately
  carries none (exercises the empty-list state); the first member carries two
  (exercises multi-record association). The completion marker's
  `reconciliation.by_result` now counts the actual records.
* **Explicit per-member expected row count** added to the `MEMBERS`
  declarations (5th tuple element; legacy members 3/2/2, udiff 2). This is
  the fixture's own construction intent, asserted against the engine
  observation. (The udiff member's body list is as-committed since D24 —
  two physical lines, one canonical row each; the explicit declaration makes
  the fixture correct under that shape and self-asserting if the shape
  changes.)
* No GOVERNED_INPUTS or w2 changes (no demonstrated Q7 requirement).
* The fixture package remains deterministic (byte-identical rebuilds).

## 7. Changed-file inventory (content digests, git blob identity)

| File | Content SHA-256 | Lines | Change |
|---|---|---|---|
| `src/serving/detail.py` | `a66a81961e5bcac86261e3703eed87108364ca37689b748fa5367f9e69413d28` | 227 | **new** — Q7 query, reconciliation parser (runner 14-key contract), row loader, digest-verified row-to-archive join |
| `src/serving/archive.py` | `fd16b046f62d26a917aaadd9e5174a67de0a26e8fc2fc083aa536e55d49c119d` | 271 | `_parse_input_manifest` → public `parse_input_manifest` (reused by Q7; Q9 behavior unchanged) |
| `src/serving/__init__.py` | `b23cf1731a12a9628a4a585759c81430702781a37f82989ae88d7b36dc49c33b` | 101 | exports Q7 API + `parse_reconciliation` + `parse_input_manifest`; boundary docstring mentions Q7 |
| `src/serving/cli.py` | `28852b9755924892f03b2b34af1d3e3710f070b51b4aaad69841ad09f8b189c3` | 273 | `query` Q7 mode (`--file`/`--line`) with the established mode exclusivity; docstring |
| `tests/serving_fixtures.py` | `6c479dc61b31a1eb42c66aa2860d837bbea920f39f7be6ac9dd3dae0538c5950` | 438 | RECONCILIATION → runner 14-field schema (2+1+1+0 member distribution); explicit per-member expected row count; marker census |
| `tests/test_serving_detail.py` | `072b1add4aeb2c67410cfcc350cd9fd7d9f8d6396222b3ba8371835c68eaae12` | 389 | **new** — 19 tests (selection, provenance/envelope, join, reconciliation association, fail-closed gates, null/as-published preservation, raw_line exclusion, determinism, Q2/Q3 invariance, byte identity, fixture schema) |
| `tests/test_serving_m2_integration.py` | `32f14d405b30c115d23a3fac9c2844b4e48cf1de15ff30055ba02a737ba24af8` | 215 | +1 `D24_M2_ROOT`-gated real-package test (Q7 over the actual M2 baseline) |
| this record | `docs/implementation/D31_Q7_RECORD_DETAIL.md` | — | new |

Nothing else changed: no engine (`src/nse_engine`), runner (`tools/`), spec,
governance, D01 evidence, or index file was modified. `.gitignore` unchanged.
No serving state file is committed.

## 8. Tests executed and exact results (actual, this session)

Runner: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (house
runner; pytest not installed).

* **Focused (new module)** — `PYTHONPATH=src python3 -m unittest
  tests.test_serving_detail`: **Ran 19 tests — OK** (19/19 pass): row
  selection + detail response vs stored row; D05 §8 provenance block +
  serving envelope preservation; correct INPUT_MANIFEST archive join
  (verbatim as-published record + digest triple equality); reconciliation
  association (as-published, file order); multiple reconciliation records
  for one archive (2); an archive with no reconciliation records (`[]`);
  unknown row identity (unknown file; unknown line) and input validation
  failing closed; ambiguous identity failing closed (duplicated manifest
  triple); inconsistent identity failing closed (family mismatch);
  malformed RECONCILIATION failing closed (unparseable line, missing key,
  non-record `input_identity`) with no partial output; malformed manifest
  failing closed via the reused Q9 parser; null + as-published value
  preservation (blank ISIN `""`, null fields untouched); `raw_line`
  exclusion (value absent from the served document); deterministic output;
  Q2/Q3 results unchanged after a Q7 operation; package byte identity
  before/after successful and failing operations; fixture RECONCILIATION
  schema conformance (14 keys, member scopes, 4 records, 0-record member);
  empty RECONCILIATION file → valid empty list.
* **CLI smoke** — `query --file … --line 2` on the fixture package: exit 0,
  canonical JSON (row + archive + reconciliation); unknown line: exit 2,
  JSON fail envelope; Q3+Q7 mode conflict: exit 2; partial Q7 selector
  (`--file` only): exit 2.
* **Full suite** — **Ran 572 tests in 62.7s — OK (skipped=7)**. 572 = 552
  (D30b) + 19 (new module) + 1 (new gated M2 test). Skipped = 7: the six
  pre-existing `D24_M2_ROOT`-gated real-package legs **plus the new Q7
  real-package leg** — all gated because `D24_M2_ROOT` is unset in this
  environment; reported as skipped, never as passed, and the fixture tests
  never stand in for them (D24 record §13). No unrelated qualification
  suite was rerun.

## 9. Real-M2 status — staged, gated, NOT executed here

The qualified M2 baseline (21.12 GB package, `DEFAULT_M2_SPEC`) is **not
provisioned in this environment** (sandbox disk ≈ 20.66 GB available <
package size; no Windows execution from Arena; the Windows-held package is
not transferred). The real-package Q7 leg is implemented and gated in
`tests/test_serving_m2_integration.py::M2RealPackageIntegrationTests::test_q7_record_detail_over_real_baseline`
(D24_M2_ROOT-gated like its siblings) and asserts: the join succeeds on
authoritative package data (member/file/digest/family equalities between the
row provenance and the INPUT_MANIFEST record); applicable reconciliation
records are non-empty and member-scoped to the joined archive; `raw_line`
stays excluded; output is deterministic. It executes only where the
environment provides the package via `D24_M2_ROOT`; until then it is
reported **skipped (pending baseline provisioning), not passed**.

## 10. Non-drift statement (D23 §18 items 5/12)

* **Read-only vs the package:** Q7 streams one row file and opens
  `INPUT_MANIFEST.jsonl` + `RECONCILIATION.jsonl`;
  `test_package_byte_identity` digests every package file before and after a
  successful **and** a failing Q7 call — byte-identical. No source archive
  byte is opened.
* **No canonical-data mutation:** no engine, runner, spec, governance,
  evidence, or D01 file was modified (diff inspection: only the six
  implementation/test files + this record).
* **No new serving state:** Q7 produces no class-(4) state and never rebuilds
  the index; the existing `serving-index/1.1` is read as-is (full suite
  green, including the D24/D30a determinism and rebuild tests).
* **Q2/Q3 contracts unchanged:** `test_q2_q3_unchanged_after_detail` plus the
  full D30a suite prove existing results/semantics are untouched; the CLI
  `query` subcommand's Q2/Q3 modes behave as before (mode exclusivity now
  covers three mutually exclusive modes).
* **M2-only contract preserved:** no registry entries, D21 findings, or
  changed-content machinery introduced; `raw_line` never served.

## 11. D23 §18 closure-battery delta

* **Item 4 (contract conformance):** Q7 semantics are exactly D16-10 Q7 as
  scoped by D22 §6 (record detail: row + provenance + archive facts +
  applicable reconciliation records; deterministic; fail closed). D05
  consumer obligation (MD-09): the row is served with its own D05 §8
  provenance block intact and as-published values (nulls and blank strings
  preserved, never defaulted — test-verified). No new query semantics beyond
  the Q1–Q10 boundary.
* **Item 8 (query-boundary):** the only new query path is
  `Q7-record-detail` inside `serving.detail`; the CLI exposes it as a mode of
  the existing `query` subcommand (exclusivity preserved). Q8/Q10/Q4–Q6 and
  saved queries remain unimplemented.
* **Item 10 (tests):** §8 — focused 19/19 OK; full suite 572 executed, OK,
  7 skipped (all `D24_M2_ROOT`-gated real-package legs, reported skipped,
  never passed).
* **Item 11 (complete artifact inventory):** §7 — all artifacts with path
  and content digest; nothing else changed.
* **Item 12 (remote durability):** this commit is fast-forward-only onto
  `14843ac8…` on the session branch and is independently remote-verified
  (commit/parent/tree/changed paths/blobs) before this task is declared
  complete; `origin/main` remains `69977017…` (promotion is the user's
  separate step — not performed).

## 12. Final status

D31 (Q7 record detail) **COMPLETE** — implementation, Q9-parser reuse,
reconciliation parsing + fixture alignment, tests, record, single
fast-forward commit, remote verification. Remaining D30b/D31-plan slices
(Q8 quality views — including flag-census index work and corpus-scoped
reconciliation views; Q10; Q4–Q6; saved-query state) are **not started** and
require their own separately-scoped tasks under the same standing authority.
