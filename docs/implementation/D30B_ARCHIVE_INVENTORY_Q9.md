# D30B — Q9 ARCHIVE INVENTORY (SLICE 1 OF THE D30b PLAN)

## 1. Task identity and purpose

**D30B** — the next serving slice under the standing **D23** authority (D24 §18
"remaining authorized work (b) Q1–Q2, Q4–Q10 and saved-query state per D16-10 —
no new authority required"), as scoped by the D30b investigation (report A–G;
Q9 selected as the smallest viable slice: one JSONL parser + one JSON parse +
the in-repo D01 join; no index extension; no w2).

This slice implements:

* **Q9** — the archive inventory query: one entry per `INPUT_MANIFEST.jsonl`
  record (as-published fields preserved) extended with the joined per-archive
  **D01 inventory facts** (`d01`) and the exact **registry-absent**
  representation, plus a summary (archive count, archive-set digest, D01
  inventory status).
* the **`inventory`** CLI subcommand (`--package`, optional `--m2`; no
  `--state`, no index dependency).
* **fixture alignment** — the test-only fixture's `INPUT_MANIFEST.jsonl` and
  `GOVERNED_INPUTS.json` writers now emit the runner's own schemas (honest
  synthetic values; the D01 basis is never claimed for the fixture).

No new authority is requested. Q7/Q8/Q10/Q4–Q6, w2 parsing/fixtures, saved
queries, index changes, UI/transport, incremental ingestion, D21 machinery,
raw-content serving, and every other boundary remain untouched. The D21
changed-content machinery is **not** part of Q9: Q9 serves archive identity +
D01 facts + the explicit M2-only registry absence — never changed-content
disposition.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged by this task |
| Session branch at work | `arena/9021d1a1-nse-historical-data-engine` at `47323161ecf6c4d5f4fa812e4cd3acfb59770ff0` (D30a); this slice commits on top |
| Evidence branch | `evidence/d26-real-m2-execution-20261009` at `0dda72bef051aa769340badda56997b42a1723f8` — untouched |
| D30a remote verification (pre-task) | commit `47323161…`, parent `8d58bac…`, tree `1de51e39…` — previously remote-verified, re-confirmed by `ls-remote` at task start |
| Local state | 21st sandbox `.git` rollback found at task start (HEAD `89ce965…`, re-shallow, stale `M` tracked files). Hash audit showed the stale bytes were identical to their `4732316` (D30a) versions for all three modified files (`.gitignore`, `README.md`, `docs/specs/D05*`), ancestry `89ce965… → 4732316…` = YES after `git fetch --unshallow origin`; recovered with the established non-destructive procedure (`update-ref` → `read-tree` → mixed `reset`); no clean/restore/force/branch-switch; worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed) |

## 3. D23 authority and scope

Implemented within D23 §8/§10/§17(a) (first-release serving/query layer over
the qualified M2 baseline; Q1–Q10 semantics fixed by D16-10; no arbitrary
query semantics beyond the Q1–Q10/saved-query boundary) and the standing D24
§18(b) remainder list. D23 §9 exposure boundary respected — Q9 serves package
*metadata* (`INPUT_MANIFEST.jsonl`, `GOVERNED_INPUTS.json`) and committed
in-repository D01 evidence; canonical row files and source archive bytes are
**never opened** (proved by test: a handle with no partition files listed in
its manifest still answers Q9). D23 §12 class-(4) rules: Q9 produces no
serving state at all (pure function of the verified baseline; the `inventory`
CLI takes no `--state`). D21 boundaries untouched (M2-only scope: class-(2)
incremental publications and the class-(3) registry are absent and are never
fabricated — the served `registry` value is the explicit absence
representation, nothing more).

## 4. Q9 — exact contract

Public API: `serving.query_archive_inventory(baseline, d01=None) -> dict`
(query id `Q9-archive-inventory`), plus `serving.load_d01_inventory(path=None)
-> dict` and `serving.D01InventoryError`.

**Inputs (verified baseline only):**

* `INPUT_MANIFEST.jsonl` — per-archive records, the runner's own 20-field
  record schema (the package owner `tools/i4_runner/i4_runner.py` writes
  exactly these keys; see §5). Parsed **as published**: every as-published
  field is preserved verbatim in the result; no invented defaults. A
  non-record line, unparseable line, or record missing any contract key
  raises `QueryError("input-manifest-scan", …)` before any output is produced.
* `GOVERNED_INPUTS.json` — parsed as published; `corpus.archive_count` must be
  an integer (fail closed). **Count cross-check:** the INPUT_MANIFEST record
  count must equal `corpus.archive_count`; disagreement raises
  `QueryError("inventory-count", …)` — no partial output.
* `corpus.archive_set_digest` is passed through **as published** (never
  recomputed or re-derived).

**D01 join (in-repo evidence, never package data):**

* `load_d01_inventory` reads `evidence/inventory/file_inventory.json`
  (cwd-relative, house convention), verifies its sha256 against the pinned
  `D01_INVENTORY_SHA256 = 336b9531cd34f48e9a2e7e7593cc4e9c2736b3864d8213bc65d6ab8b488729d2`
  and its record count against the pinned `D01_INVENTORY_RECORD_COUNT = 2462`
  **before** trusting it; any identity failure raises `D01InventoryError`
  (fail closed, no fallback, no repair). Returns a mapping keyed by
  `(root, relative_path)`.
* **Pinned M2 baseline** (`spec == serving.baseline.DEFAULT_M2_SPEC`): the D01
  inventory is **required** (`d01-required` otherwise). For every archive the
  join key `(root, relative_path)` must hit the inventory (`d01-join-miss`
  otherwise) and the D01 record `sha256` must equal the as-published
  `archive_sha256_d01` (`d01-identity-mismatch` otherwise) — a join miss or
  mismatch on the pinned baseline is an identity inconsistency, fail closed.
  On success each archive gains `d01` = the D01 facts
  (`sha256`, `size_bytes`, `date_from_filename`, `row_count`, `bad_rows`,
  `series_counts`, `symbol_count`, `isin_count`, `header_signature`).
* **Any other baseline** (synthetic/unpinned): `d01` must not be supplied
  (`d01-mismatch` if it is); each archive gains `d01: null` and the summary
  reports the D01 inventory as `{"present": false, "status": "absent"}` — the
  in-repo evidence is never misrepresented as package-embedded data.

**Registry (exact M2-only representation):**

* Every archive and the summary carry
  `registry = {"present": false, "status": "absent-in-m2-only-release"}` —
  the class-(3) registry does not exist in the M2-only first release (D22 §6
  Q9; D16-02); no records, statuses, or version bindings are fabricated.

**Result document** (canonical JSON at the CLI boundary):

* `query: "Q9-archive-inventory"`;
* `archives` — one entry per INPUT_MANIFEST record, ordered by
  `(sequence, relative_path)` (deterministic; identical repeated output),
  each = the as-published record + `d01` + `registry`;
* `summary` — `archive_count` (cross-checked), `archive_set_digest` (as
  published), `d01_inventory` (pinned M2: `present/path/record_count/sha256`;
  otherwise `{"present": false, "status": "absent"}`), `registry` (the exact
  absence representation).

**Read-only:** the query opens exactly the two package metadata files; the
package is byte-identical before/after (proved by test, including after a
failing call).

## 5. Runner schema references (package owner is authoritative)

From `tools/i4_runner/i4_runner.py` @ `4732316…` (the package owner; no
independent re-implementation of its formats):

* **`INPUT_MANIFEST.jsonl`** record — 20 fields (the D30b report's "19-field"
  count was a miscount; the source is authoritative):
  `sequence, root, relative_path, file_name, member_name, date_from_filename,
  detected_format, engine_family, partition, archive_sha256_d01,
  archive_sha256_basis, archive_sha256_observed_raw_bytes,
  member_sha256_raw_bytes, member_sha256_lf_text, member_size_bytes,
  header_physical_width, header_tolerance_applied, data_lines, rows,
  quarantined`. `root` ∈ `ROOT_LABELS = ("LEGACY", "UDIFF")`
  (`tools/i4_runner/i4_inputs.py:75`).
* **`GOVERNED_INPUTS.json`** — `contract_version, run_id, files[],
  corpus{root_labels, archive_count, archive_set_digest, hash_basis},
  engine_identity, runner_identity, governed_config, config_fingerprint,
  partition_definition, composite_run_identity, declared_expectations`. Q9
  consumes `corpus.archive_count` and `corpus.archive_set_digest` as
  published; no fabricated identity/config is asserted for them.
* **D01 inventory** (`evidence/inventory/file_inventory.json`, in-repo
  evidence) — record keys include `root, relative_path, file_name,
  size_bytes, date_from_filename, sha256, detected_format, row_count,
  bad_rows, headers, header_signature, date_values, series_counts,
  symbol_count, isin_count`; join key `(root, relative_path)` matches
  `INPUT_MANIFEST`.
* **RECONCILIATION.jsonl** (runner shared 14-field schema) — *not* parsed by
  Q9; it belongs to the later Q7/Q8 slice (fixture alignment for it is
  deliberately deferred there).

## 6. Fixture alignment (test-only)

`tests/serving_fixtures.py` — only the two writers Q9 consumes were aligned to
the runner's schemas; no w2/RECONCILIATION alignment, no new fixtures:

* **`INPUT_MANIFEST.jsonl`** — now emits the runner's 20-field record per
  member: `sequence` (1-based over sorted members), `root` = `"LEGACY"`/
  `"UDIFF"`, `relative_path`/`file_name`/`member_name` = member name,
  `date_from_filename` = the member's governed source date,
  `detected_format` = root label, `engine_family` = engine `format_family`,
  `partition` = `(family, year)`, member digests from the engine parse report
  (`member_sha256_raw_bytes`, `member_sha256_lf_text`,
  `member_size_bytes`, `header_physical_width`,
  `header_tolerance_applied`, `data_lines`), `rows`/`quarantined` from the
  canonical build. **Honest synthetic identity:** `archive_sha256_d01` and
  `archive_sha256_observed_raw_bytes` are computed from the fixture member
  bytes and `archive_sha256_basis` stays
  `"computed-fixture-member-bytes"` — the fixture never claims
  `"D01-inventory"` basis (it has no D01 inventory).
* **`GOVERNED_INPUTS.json`** — now emits the runner's schema:
  `contract_version` (`D24-fixture/1.0`), `run_id`, `files[]` (role
  `archive`, `path_label`, `sha256`), `corpus{root_labels: ["LEGACY","UDIFF"],
  archive_count, archive_set_digest, hash_basis}` (the fixture's actual digest
  basis stated honestly), `engine_identity`, `runner_identity` (fixture
  builder), `governed_config` = `DEFAULT_CONFIG.to_dict()`,
  `config_fingerprint`, plus an explicit `"note": "d24 synthetic fixture
  (never the M2 corpus)"`.

The fixture package remains deterministic (byte-identical rebuilds); its
pinned identity (`BaselineSpec`) is recomputed from the rebuilt package by the
builder as before, so all D24/D30a fixture tests continue to pin it.

## 7. CLI — `inventory` subcommand

`python3 -m serving.cli inventory --package <root> [--m2]`

* `--package` required; `--m2` optional (pin to the qualified M2 identity —
  in that case the in-repo D01 inventory is loaded from the repository
  working directory and the join is mandatory); **no `--state`** — Q9 has no
  serving state and no index dependency.
* Exit codes follow the CLI conventions: `0` = ok (canonical JSON on
  stdout); `2` = usage/verification/query failure (baseline verification
  failure, D01 inventory identity failure, or any `QueryError` — JSON
  `{"result": "fail", "detail": …}` and nothing else); `3` remains index/stale
  (never produced by `inventory`). No partial results on failure.
* Read-only vs the package (only the two metadata files are opened; verified
  byte-identical after use).

## 8. Changed-file inventory (content digests, git blob identity)

| File | Content SHA-256 | Lines | Change |
|---|---|---|---|
| `src/serving/archive.py` | `268ee536cb1a639363cc26751ca888172cb590f233d79db31029c38fe50bcfc9` | 266 | **new** — Q9 query, D01 loader (pinned), contract constants, registry-absent representation |
| `src/serving/__init__.py` | `65dd067d17ea67bf6c81af78f2f3150b779f92facdeefafdc32d99e5d1c74b74` | 90 | exports Q9 API + `D01InventoryError` + D01 constants; boundary docstring mentions Q9 |
| `src/serving/cli.py` | `3affcadf4c4eebeaaa564645d2bdc77f756cf53148ff238a856d697aa63e81dd` | 248 | `inventory` subcommand (`--package`, optional `--m2`, no `--state`); docstring command list + exit-code line |
| `tests/serving_fixtures.py` | `1d61a7229e16cc48fd041003a8e239326cfac1aa5e32d8abdfec317dffa7827f` | 378 | INPUT_MANIFEST → runner 20-field schema; GOVERNED_INPUTS → runner schema (honest synthetic values) |
| `tests/test_serving_archive.py` | `aed0c675cb1855b70303bacdfa1166f5a2f4040df65087b9a331776589638c8b` | 317 | **new** — 15 tests (Q9 semantics, fail-closed gates, D01 identity, read-only discipline) |
| `tests/test_serving_m2_integration.py` | `13516b0d73718ff225d1b25e733f5685b1941b6e823f637f49d069a2ab72fd9a` | 187 | +1 `D24_M2_ROOT`-gated real-package test (Q9 over the actual M2 baseline) |
| this record | `docs/implementation/D30B_ARCHIVE_INVENTORY_Q9.md` | — | new |

Nothing else changed: no engine (`src/nse_engine`), runner (`tools/`), spec,
governance, D01 evidence, or index file was modified. `.gitignore` unchanged.
No serving state file is committed. The D01 inventory is **consumed, never
modified**.

## 9. D01 inventory identity (in-repo evidence, verified before use)

| Item | Value |
|---|---|
| Path | `evidence/inventory/file_inventory.json` |
| Raw file SHA-256 (pinned in `serving.archive`) | `336b9531cd34f48e9a2e7e7593cc4e9c2736b3864d8213bc65d6ab8b488729d2` |
| Record count (pinned) | 2,462 |
| Root census (pinned, test-verified) | LEGACY 1,919 + UDIFF 543 = 2,462 |
| Verification | `load_d01_inventory` verifies digest + record count before use; `D01InventoryIdentityTests` re-verifies the in-repo file against the pin and the root census; `D01InventoryLoadFailClosedTests` proves wrong-digest and missing-path loads fail closed |

The D01 join against the *real* M2 package (all 2,462 archives hitting the
inventory with `archive_sha256_d01 == D01 sha256`) is asserted by the
`D24_M2_ROOT`-gated test — see §11.

## 10. Tests executed and exact results (actual, this session)

Runner: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (house
runner; pytest not installed).

* **Focused (new module)** — `PYTHONPATH=src python3 -m unittest
  tests.test_serving_archive -v`: **Ran 15 tests — OK** (15/15 pass):
  per-archive schema + as-published pass-through; deterministic ordering +
  identical repeated output; summary count/digest + exact
  registry-absent representation; synthetic D01 absence; count-mismatch
  rejection; pinned-M2 `d01-required`; pinned-M2 `d01-join-miss` and
  `d01-identity-mismatch`; `d01-mismatch` (supplied for non-M2 baseline);
  malformed INPUT_MANIFEST rejection (unparseable line + missing contract
  key), no partial output; metadata-only access (handle with no partition
  files); read-only byte identity (including after a failing call); D01
  in-repo identity (2,462 = 1,919 LEGACY + 543 UDIFF, pinned digest);
  D01 load fail-closed (wrong digest, missing path).
* **CLI smoke** — `inventory` on the fixture package: exit 0, canonical JSON,
  per-archive as-published + `d01: null` + registry absence; `inventory
  --m2` on the (non-M2) fixture fails closed at `verify-07` (run identity),
  exit 2, JSON failure envelope only.
* **Full suite** — `PYTHONPATH=src python3 -m unittest discover -s tests -t .`:
  **Ran 552 tests in 76.3s — OK (skipped=6)** (final run, after the last
  fixture byte change). 552 = 536 (D30a) + 15 (new
  module) + 1 (new gated M2 test). Skipped = 6: the five pre-existing
  `D24_M2_ROOT`-gated real-package legs **plus the new Q9 real-package leg** —
  all gated because `D24_M2_ROOT` is unset in this environment; they are
  reported as skipped, never as passed, and the fixture tests never stand in
  for them (D24 record §13). No unrelated qualification suite was rerun.

## 11. Real-M2 status — staged, gated, NOT executed here

The qualified M2 baseline (21.12 GB package, D11-qualified identity
`DEFAULT_M2_SPEC`) is **not provisioned in this environment** (sandbox disk
≈ 20.66 GB available < package size; no Windows/PowerShell execution from
Arena; the Windows-held package is not transferred). The real-package Q9 leg
is implemented and gated in
`tests/test_serving_m2_integration.py::M2RealPackageIntegrationTests::test_q9_archive_inventory_over_real_baseline`
(D24_M2_ROOT-gated like its siblings) and asserts: 2,462 archives; complete
D01 join (every `archive_sha256_d01` equal to its D01 inventory `sha256`);
the exact registry absence; deterministic identical repeated output. It will
execute only where the environment provides the package via `D24_M2_ROOT`;
until then it is reported **skipped (pending baseline provisioning), not
passed**.

## 12. Non-drift statement (D23 §18 item 5 / item 12)

* **Read-only vs the package:** Q9 opens only `INPUT_MANIFEST.jsonl` and
  `GOVERNED_INPUTS.json`; `test_inventory_leaves_the_package_byte_identical`
  digests every package file before and after a successful **and** a failing
  Q9 call — byte-identical.
* **No canonical-data mutation:** no engine, runner, spec, governance,
  evidence, or D01 file was modified (diff inspection: only the six
  implementation files + this record). The D01 inventory was read and
  verified, never written.
* **No new serving state:** Q9 produces no class-(4) state; the `inventory`
  CLI has no `--state`; the existing class-(4) index (format `serving-index/1.1`)
  is untouched and still rebuilds identically (full suite green).
* **M2-only contract preserved:** the served `registry` is the exact absence
  representation; no changed-content/disposition machinery was introduced
  (D21 boundary intact).

## 13. D23 §18 closure-battery delta

* **Item 4 (contract conformance):** Q9 semantics are exactly D16-10 Q9 as
  scoped by D22 §6 (per-archive D01 + INPUT_MANIFEST facts; registry status
  = the explicit M2-only absence; deterministic; no invented defaults;
  fail-closed on every contract violation). D05 consumer obligation (MD-09):
  Q9 serves no rows, so no row-level provenance is required; where D01 facts
  are joined, the in-repo D01 evidence is the authority and is served as
  published (never recomputed). D16-07 class-(4) rules: Q9 creates no state.
* **Item 8 (query-boundary):** the only new query path is `Q9-archive-inventory`
  inside `serving.archive`; no other query surface exists in this slice
  (Q7/Q8/Q10/Q4–Q6 and saved queries remain unimplemented; the CLI exposes
  exactly the existing subcommands + `inventory`).
* **Item 10 (tests):** §10 — focused 15/15 OK; full suite 552 executed, OK,
  6 skipped (all `D24_M2_ROOT`-gated real-package legs, reported skipped,
  never passed).
* **Item 11 (complete artifact inventory):** §8 — all artifacts with path and
  content digest; nothing else changed.
* **Item 12 (remote durability):** this commit is fast-forward-only onto
  `47323161…` on the session branch and is independently remote-verified
  (commit/parent/tree/changed paths/blobs) before this task is declared
  complete; `origin/main` remains `69977017…` (promotion is the user's
  separate step — not performed).

## 14. Final status

D30B slice 1 (Q9) **COMPLETE** — implementation, fixture alignment, tests,
record, single fast-forward commit, remote verification. Remaining D30b
slices (Q7/Q8 — including RECONCILIATION/w2 parsing and fixture alignment for
them; Q10; Q4–Q6; saved-query state) are **not started** and require their
own separately-scoped tasks under the same standing authority.
