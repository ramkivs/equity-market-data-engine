# D25 — QUALIFIED M2 RE-PROVISIONING AND REAL-PACKAGE INTEGRATION VERIFICATION (EVIDENCE RECORD)

## 1. Task identity and purpose

**D25** is the narrowly scoped evidence-completion task for D24: close (or precisely
bound) the outstanding real-M2 integration evidence gap without changing the D24
implementation or the qualified canonical dataset. Mode:
INVESTIGATE → VERIFY → RE-PROVISION IF AUTHORIZED → TEST → PROVE. This is not a new
implementation-authority decision; it consumes the standing D23 authority and the D24
staged `D24_M2_ROOT` integration tests. This record describes **actual evidence only**.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| Repository / remote | `ramkivs/nse-historical-data-engine` (public) @ `origin` (GitHub) |
| `origin/main` (remote-verified, exact) | `01612f7f983ed2ac70e17d6814d02968aae845c7` = D23 — **exact match with the expected baseline**; no later publication discovered |
| Session branch `arena/9021d1a1-nse-historical-data-engine` | `69977017ffca944921f231d7904347bc582b6392` = D24 (HEAD) |
| D24 full SHA (resolved from the remote, not assumed) | `69977017ffca944921f231d7904347bc582b6392` (the task's `6997701` prefix resolves uniquely to this commit) |
| D24 ancestry (remote compare `01612f7……6997701…`) | ahead **1** / behind **0**, status `ahead`; parent = D23 |
| D24 changed-file inventory (remote compare) | exactly 13 files: 12 added (`src/serving/` ×7, `tests/` ×4, `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md`) + `.gitignore` modified (+3, `serving-state/`) — matches D24 §7/§16 exactly |
| D24 remote blobs (spot-verified in the D24 tree) | record `b50a820e43b6` (27,374 B); `baseline.py` `46897d7e4a1e`; `index.py` `3c86df266e1d`; `query.py` `236503c1665b`; `rebuild.py` `33946f58a38b`; `cli.py` `cc658f39da58`; `test_serving_m2_integration.py` `5c14f5141bf0` (5,613 B); … all present at D24 |
| D22 + D23 on main | D23 blob `db4645e90adc` (29,694 B); D22 blob `962cda557977` (27,900 B) — verified present in the main tree |
| Local state at task start | sandbox `.git` rollback (15th in sequence; HEAD at stale `89ce965`), **plus** the D24 worktree files (all 12 D24 additions) missing from disk; repaired non-destructively (unshallow → ancestry YES → `update-ref` → `read-tree` → `git restore --worktree` of the committed D24 paths only); worktree verified clean (`git status` = untracked `_transfer_delivery/` only) before any D25 action |
| Egress environment (standing) | GitHub-only network reach; the Windows corpus/package origin is not reachable from this sandbox |

## 3. D23 authority and D24 scope consumed

- **Consumed:** D23 §17 GRANTED (first-release read-only serving over the qualified M2
  baseline; class-(4) rebuildable serving state; delegated operation (b); technology
  delegation exercised in D24 §5). D25 performs no new implementation: it investigates
  recovery of the qualified package, re-verifies identity, executes the staged D24
  tests, and records the closure-matrix reconciliation.
- **Not touched (D23 §17/§19, D25 task scope):** incremental ingestion/processing;
  delegated operation (a); requalification; per-instance CHANGED resolution; raw-content
  serving; DEC-1; any engine/canonical/governance change; any D24 code change.
- **Explicit task rules honored:** no substitution of reconstructed/partial/synthetic/
  rerun packages; no regeneration or requalification of the historical corpus; no 21 GB
  package committed to the repository; no deletion or cleaning of unrelated data; the
  D24 implementation commit is not altered.

## 4. M2 package identity (re-verified in this task from in-repo durable evidence)

Source of truth for identity: the repository-durable D11 transfer evidence
`evidence/D11_REPLAY_QUALIFICATION_20261009/D11_E1_E10_TRANSFER_20261009.tar.gz`
(708,001 B tracked; extracted read-only for inspection). Independently recomputed in this
task (not copied from D24):

| Identity | Value | Re-verified here |
|---|---|---|
| `package_manifest_sha256` | `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc` | sha256 of the `PACKAGE_MANIFEST.sha256` bytes (667,405 B) — **exact match** |
| file count | 4,948 | `A.PACKAGE_FILES.tsv` = 4,949 lines = header + 4,948 data rows — exact |
| total bytes | 21,119,807,344 | Σ `size_bytes` over all 4,948 rows — **exact match** |
| manifest entries | 4,946 | `PACKAGE_MANIFEST.sha256` entry count (4,948 − manifest − `RUN_COMPLETE.json` marker) — consistent |
| run id | `i4-20261008-M2` | `RUN_RECORD.json` `run_id` — exact |
| composite run identity | `9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d` | `RUN_RECORD.json` — exact |
| engine `tool_sha256` | `d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9` (nse-engine w2-1.0.0, 17 modules, spec D05/1.0) | `RUN_RECORD.json` `engine_identity` — exact |
| runner `runner_sha256` | `f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a` (i4-runner-1.0.0) | `RUN_RECORD.json` `runner_identity` — exact |
| archive count / set digest | 2,462 / `54d8150706ccf5d813a6f0af668e8230e147a7e370db20ea15dda1b72bf8b100` | `RUN_RECORD.json` `corpus` — exact |
| row count | 5,689,949 | `RUN_RECORD.json` `counts.rows` — exact |
| partitions | 12 (legacy13 2016–2024; udiff34 2024–2026) | `RUN_RECORD.json` `corpus.partitions` — consistent with D24 §4 |
| completion marker | `RUN_COMPLETE.json` present in the transfer evidence, carrying the same `package_manifest_sha256`; "written last … a package without it is incomplete by construction" | verified |

The D24 pinned spec (`serving.baseline.DEFAULT_M2_SPEC`) agrees with all of the above —
re-executed by `M2BaselineIdentityTests` (§8).

## 5. M2 source provenance and recovery-source investigation

**Provenance of the qualified package:** built on the Windows machine (G-I4 boundary:
Arena never executed the 2,462-member corpus), self-checked at the origin, and delivered
to this sandbox by the user's manual transfer process into the untracked
`_transfer_delivery/m2_fix/` (the v3 corrected transfer revision). That directory held
the physical 21 GB package until the sandbox rollback at the start of D24 removed it
(D24 §4 "Environment fact"). D25 confirms the directory is **absent** at D25 start.

**All candidate sources inspected and classified (evidence vs package):**

| Candidate | What it is | Package? |
|---|---|---|
| `_transfer_delivery/m2/I4_M2_WINDOWS_PACKAGE.tar.gz` (141,788 B; sha256 `45643f28…` per its sidecar) + manifest/facts/scripts | **Windows build-transfer** (v1, SUPERSEDED per its own `SUPERSEDED_BY_M2_FIX.md`): 47 entries = engine source (17 modules), runner (6 modules), PowerShell build/verify scripts, docs (`I4_M2_TRANSFER_FACTS.json` payload: 29 payload files by role doc/engine/runner/test). Contains what is needed to *build* the package on Windows — not the package | **NO** — metadata/source, not the qualified output |
| `_transfer_delivery/m2_fix/` | the delivered v3 transfer that held the 21 GB package (D24 §4) | **ABSENT** — removed by the rollback; not recovered |
| `_transfer_delivery/exposure/I4_M2_WINDOWS_PACKAGE{,_v2,_v3}.tar.gz.b64` + `EXTRACT_M2_PACKAGE.ps1` / HOW-TO docs | base64 copies of the Windows build-transfers (v1–v3) + the manual exposure procedure | **NO** — build-transfer copies, not the qualified output |
| `_transfer_delivery/D08_*`, `I4_RUNNER_WINDOWS_*` | older D08/runner build-transfers | **NO** |
| in-repo `evidence/D11_REPLAY_QUALIFICATION_20261009/D11_E1_E10_TRANSFER_20261009.tar.gz` (708,001 B → 2.3 MB extracted) | D11 replay-qualification **evidence transfer**: A/B.PACKAGE_FILES.tsv (file list + sizes + per-file sha256), PACKAGE_MANIFEST.sha256 (4,946 per-file digests), RUN_RECORD.json, RUN_COMPLETE.json, R6 verdict, memory-monitor data | **NO** — the complete package *metadata* (the identity source of §4), not the package bytes |
| `evidence/` (rest of repo; largest tracked blob 4,731,552 B = `evidence/inventory/file_inventory.json`) | historical engine evidence | **NO** |
| filesystem search (`/home/user`, `/tmp`, `/var/tmp`, `/opt`, `/srv`, `/mnt`, `/data`, maxdepth 6, for `RUN_COMPLETE.json` / `PACKAGE_MANIFEST.sha256` / `i4-20261008-M2*`) | only hits = the D11 evidence files extracted in this task to `/tmp` for inspection | **NO** |
| GitHub repository | 3 branches; 1 release (`d08-transfer-2026-10-06`) with **zero assets**; largest tracked blob 4.7 MB (a 21 GB package could never be committed — platform file limits) | **NO** |

**Transfer evidence in this task: none applicable** — no transfer occurred; nothing was
moved, copied, reconstructed, or regenerated.

## 6. Trustworthy-source determination (Phase 1 result)

> **No trustworthy, complete, byte-identical copy of the qualified M2 package is
> available in this environment.** Two independent, verified reasons:
>
> 1. **Absence:** no copy exists in the sandbox (full search §5) or on GitHub (§5);
>    the only origin of the exact package is the Windows machine, which is unreachable
>    from this sandbox (egress = GitHub only), and re-delivery is a user-side action.
> 2. **Capacity (new, material):** this sandbox's root filesystem had
>    **20,657,389,568 bytes available** at measurement (`df -k /`: 20,173,232 KB, after
>    clearing this task's temporary inspection files) against a required
>    **21,119,807,344 bytes** — a shortfall of **462,417,776 bytes (≈ 441 MiB)**. The
>    qualified package **cannot be provisioned in this sandbox at all**, even if it were
>    re-transferred; the D24 slice itself (worktree + state) is the only other consumer
>    of the 21 GB volume.

Consequently **Phase 2 (re-provisioning) was NOT executed**: its precondition ("if a
trustworthy, complete, byte-identical qualified M2 package is available") is false. Per
the task rule, D25 **STOPs the re-provisioning path and reports the precise missing
source/evidence** (§12). No package was substituted, reconstructed, partially restored,
regenerated, or re-qualified.

## 7. Package verification results

- **Identity level (executed, this task):** §4 — every identity field of the qualified
  baseline re-verified by independent recomputation from in-repo durable evidence; all
  exact. The D24 pinned spec agrees (re-executed, §8).
- **Byte level (full 4,948-file digest verification, verify-02): NOT EXECUTABLE** in
  this environment — no package bytes exist here and none can fit (§6). It remains
  implemented (`serving.baseline.open_baseline`, verify-01..07) and fixture-tested, and
  is staged as `M2RealPackageIntegrationTests.test_full_verification_passes_with_pinned_spec`
  for execution where the package is present.

## 8. Executed tests: actual commands and results

1. **Full house suite** (D24 implementation restored intact; worktree clean before run):
   - Command: `PYTHONPATH=src python3 -m unittest discover -s tests -t .`
   - Result: **`Ran 514 tests in 69.116s` — `OK (skipped=3)`** — 511 passed, 3 skipped.
     Exactly the state D24 reported (no drift since D24). The pre-existing 2
     `ResourceWarning`s in `tests/test_i4_runner.py` are present and untouched (D24 §13).
2. **Serving M2 module, verbose** (explicit skip-reason evidence):
   - Command: `PYTHONPATH=src python3 -m unittest tests.test_serving_m2_integration -v`
   - Result: `Ran 7 tests — OK (skipped=3)`:
     - `M2BaselineIdentityTests`: **4/4 passed** (`test_pin_file_count_and_total_bytes`,
       `test_pin_manifest_digest`, `test_pin_run_and_tool_identity`,
       `test_pin_row_count_matches_run_record`).
     - `M2RealPackageIntegrationTests`: **3/3 skipped**, each with the recorded reason
       "qualified M2 package not present in this environment (D24_M2_ROOT unset);
       real-package integration is PENDING baseline provisioning, **not passed**".
- **No fixture test is represented as a real-package test.** No implementation code was
  modified to make any test pass (worktree diff = 0 for all tracked files, §9).

## 9. Canonical-data immutability evidence (this task)

- **This task modified no tracked file at all**: pre-artifact `git status` clean except
  untracked `_transfer_delivery/`; the only D25 mutation is this artifact (§14). No D01
  inventory, D05 spec, qualification record, archive, or M2 evidence file was touched;
  the in-repo D11 evidence tarball was read-only (extracted to `/tmp` for inspection).
- The D24 immutability mechanism stands: `open_baseline` opens package files read-only
  (verify-02 per-file digests before any serving); the executed fixture proof (18/18
  files byte-identical across verify/build/query/rebuild, D24 §9) is unchanged; the
  real-package leg (package byte-identical before/after serving operations) remains the
  staged `D24_M2_ROOT` execution, blocked per §6.

## 10. Rebuild reproducibility evidence (this task)

- D24's executed fixture proofs stand (two independent builds byte-identical;
  delete-and-rebuild reproduces exact prior bytes; `identical: true`; stale-index
  refusal — D24 §12).
- The real-package leg (`test_rebuild_reproducibility`: rebuild over the unchanged M2
  baseline byte-identical with `rows_scanned == 5,689,949`) is **not executed** — no
  package present; reported skipped, never passed.

## 11. D23 closure-matrix reconciliation (D23 §18; independent re-classification)

| # | D23 requirement | D25 classification | Evidence |
|---|---|---|---|
| 1 | Authoritative source/repo/ref | **FULLY VERIFIED** | repo/remote identity, branch, D23-on-main baseline, D24 commit/parent/ancestry/blob inventory — all independently remote-verified in this task (§2) |
| 2 | Baseline identity verified unchanged | **PARTIALLY VERIFIED** | identity layer: re-executed and passed in this task (4 pin tests + independent recomputation, §4/§8); mechanism (verify-02, 4,948-file digest check) implemented and fixture-tested; **real-package execution: BLOCKED** (§6) |
| 3 | Technology decisions recorded | **FULLY VERIFIED** | D24 §5 (selections, rationale, MD-10 grading, MD-12 deferral) — unchanged, still the operative record |
| 4 | Contract conformance | **FULLY VERIFIED** (slice level) | D16-08/09/10-Q3/11, D16-07 class-(4), D05 as-published semantics, D21 slice-level semantics — each fixture-test-demonstrated (D24 §13; re-executed in §8); the real-data leg of Q3 rides on item 2's block, not on a contract gap |
| 5 | Canonical-data immutability proof | **PARTIALLY VERIFIED** | fixture 18/18 byte-identical (D24 §9) + this task's zero-tracked-diff (§9); **real-package leg: BLOCKED** (§6) |
| 6 | D21 changed-content handling proof | **FULLY VERIFIED** (slice level) | unlisted-content package fails closed wholesale; no candidate path to serving; no resolution mechanism/registry/workflow; no CHANGED state possible in an M2-only first release (D24 §11; D21 §14–§19 consumed unchanged) |
| 7 | Deterministic/rebuildable serving state proof | **PARTIALLY VERIFIED** | fixture byte-identical rebuilds + stale-index refusal (D24 §12); **real-package leg: BLOCKED** (§6) |
| 8 | Query-boundary proof | **FULLY VERIFIED** | public query surface is `serving.query_instrument` (Q3) alone (D24 §8/§15; code unchanged at D24) |
| 9 | UI boundary proof | **FULLY VERIFIED** (slice level) | no UI implemented; consumer (CLI/importable API) reads only through the verified baseline + query layer; no direct durable-data access path (D24 §15) |
| 10 | Tests | **FULLY VERIFIED** | re-executed in this task: 514 run / 511 passed / 3 skipped with recorded skip reasons (§8) |
| 11 | Complete artifact inventory | **FULLY VERIFIED** | D24 §16 inventory intact at D24 (remote blobs, §2); D25 adds exactly this artifact (§14) |
| 12 | Remote durability + independent remote verification | **FULLY VERIFIED** | D24 publication (its Phase 6) + this task's remote verification (§2) + D25 publication (its Phase 5) |

**Net: 9 of 12 FULLY VERIFIED; items 2/5/7 PARTIALLY VERIFIED** with the real-package
byte-level leg **BLOCKED** by environment (§6) — the block is environmental
(no trustworthy source; filesystem capacity), not a defect of the implementation or the
contracts. No requirement is manufactured closed.

## 12. Unresolved evidence gaps (precise)

- **G1 — the physical qualified M2 package is absent and unprovisionable here.** Exact
  missing object: the 4,948-file / 21,119,807,344-byte package `i4-20261008-M2` with
  `PACKAGE_MANIFEST.sha256` digest `e7c7e4c8…` and `RUN_COMPLETE.json` marker. Only
  origin: the Windows machine (package built and self-checked there). Re-delivery is a
  user-side transfer action; and **this sandbox cannot host it** (capacity shortfall
  462,417,776 B, §6.2). Closing G1 requires executing the staged tests **in an
  environment that already holds (or can host) the exact package** — e.g. the Windows
  origin machine, or a larger-capacity sandbox after re-transfer.
- **G2 — the real-package legs of D23 battery items 2/5/7** (derivative of G1), i.e.
  exactly: `M2RealPackageIntegrationTests` (3 tests: full verification with the pinned
  spec; Q3 over the real baseline; rebuild reproducibility with `rows_scanned == 5,689,949`)
  plus the CLI `verify/build/query/rebuild` smoke over the real baseline and
  before/after byte-identity of the package. The staged tests define the exact
  remaining execution; `D24_M2_ROOT=<package root>` is the documented configuration.

**Original package identity:** `i4-20261008-M2` exactly as §4 (manifest digest
`e7c7e4c8…`, 4,948 files, 21,119,807,344 B, `RUN_COMPLETE.json` marker) — built and
self-checked on the Windows origin, delivered here as the v3 transfer in
`_transfer_delivery/m2_fix/`, and lost when the sandbox rollback at D24 start removed
that untracked directory. **Recovered package identity: NONE** — no package copy of any
kind was recovered, reconstructed, or regenerated in this task (explicit; §6).

## 13. Explicit scope and non-drift statement

Scope: investigate recovery sources; re-verify package identity from durable evidence;
execute the D24 staged tests in this environment; reconcile the D23 closure matrix;
record the result. Non-drift: **no D24 implementation change** (D24 commit
`6997701…` unaltered; worktree diff = 0 for all tracked files at all times during this
task); **no canonical historical data, D01 inventory, qualification record, or M2
evidence changed** (read-only inspection only); **no governance artifact changed**
(D16/D21/D22/D23/D05/D08/D12/D14/intent unchanged); **no requalification, regeneration,
reprocessing, or re-provisioning performed** (precondition false — §6); **no package
substitution** of any kind; **no new authority granted or requested**; **no promotion**:
`main` remains exactly `01612f7…` (D23), D24 remains on the session branch, D25 does not
promote anything. Single-user personal-use scope and all D16 §13 non-goals preserved.

## 14. Artifact inventory

- **This record:** `docs/investigations/D25_REAL_M2_INTEGRATION_VERIFICATION.md`
  (exactly ONE new artifact; no other file changed).
- **Consumed (verified, unmodified):** D23 (main, blob `db4645e90adc…`); D24 record
  (session, blob `b50a820e43b6…`) + all `src/serving/` and serving test blobs (§2);
  in-repo D11 evidence tarball (tracked, read-only); D22 (main, blob `962cda557977…`).
- **Inspected (untracked, unchanged):** `_transfer_delivery/` (7.9 MB of
  build-transfer artifacts — §5).
- **Not created:** no package copy, no reconstructed/partial/synthetic package, no
  implementation code, no test, no state file, no registry, no migration.

## 15. Final determination

> **D25 = BLOCKED — EVIDENCE REQUIRED.**
>
> The qualified M2 package cannot be recovered in this environment (no trustworthy
> source exists — §5/§6 — and the sandbox filesystem cannot host the package even if
> re-transferred — §6.2). The D24 implementation and its staged `D24_M2_ROOT`
> integration tests are intact and re-executed: identity layer re-verified exact
> (independent recomputation, §4), full suite 514/511 passed/3 skipped (§8), no
> drift of any kind (§13). The D23 closure battery stands at **9 of 12 FULLY VERIFIED**;
> items 2/5/7 carry the real-package byte-level leg, precisely defined by the staged
> tests and blocked by G1 (§12). Full D24 closure is **not** claimed: it requires the
> staged real-package execution in an environment that holds (or can host) the exact
> qualified package.
