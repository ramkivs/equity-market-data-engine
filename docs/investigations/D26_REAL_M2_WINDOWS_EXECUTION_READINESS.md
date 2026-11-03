# D26 — REAL-M2 INTEGRATION VERIFICATION READINESS AND WINDOWS EXECUTION HANDOFF (EVIDENCE RECORD)

## 1. Task identity and purpose

**D26** prepares the remaining real-M2 integration verification (D25 gaps G1/G2) for
execution on the original Windows package origin, using the **existing** D24
implementation and its staged `D24_M2_ROOT` tests. It (a) verifies the governing state,
(b) produces a minimal read-only, fail-closed PowerShell block for the user to run on
Windows, (c) analyzes execution readiness (runtime, paths, capacity, portability),
(d) prepares the exact handoff commands with expected results, and (e) records the
remaining evidence requirements. **No implementation change, no canonical-data
modification, no main promotion.** Arena has no Windows/PowerShell access (standing
constraint): the Windows commands in §7/§8 are **prepared, not executed** here; the
integration tests are **not** claimed passed.

## 2. Governing baseline (remote-verified before any action)

| Item | Value |
|---|---|
| Repository / remote | `ramkivs/nse-historical-data-engine` (public) @ `origin` (GitHub) |
| `origin/main` (exact) | `01612f7f983ed2ac70e17d6814d02968aae845c7` = D23 — matches the expected authoritative main; no later publication |
| D24 implementation commit (full) | `69977017ffca944921f231d7904347bc582b6392` (parent = D23) — the serving implementation identity this handoff targets |
| D25 evidence commit (full) | `5c6a38f8aa8e752c5d22a3f2e10635140fab1730` (parent = D24) — session branch HEAD at task start |
| D25 → session state | D25 adds exactly one documentation artifact over D24 (verified by its remote compare: 1 file, +250); the serving implementation is therefore **byte-identical between D24 and the session HEAD** — pinning execution to D24 `6997701…` executes exactly the current implementation |
| D23 authority (consumed, unchanged) | first-release read-only serving over the qualified M2 baseline; class-(4) rebuildable state; delegated operation (b); technology constraints §13 |
| Local state at task start | 16th sandbox `.git` rollback (HEAD at stale `89ce965`); repaired non-destructively (unshallow → ancestry YES → `update-ref` → `read-tree`); worktree clean except pre-existing untracked `_transfer_delivery/` |

## 3. Governing records re-verified (read at baseline)

- **D24 record** `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md` (blob
  `b50a820e43b6…`): implementation inventory (§7), Q3 contract (§8), D23 closure matrix
  (§15, items 2/5/7 PENDING real-package execution), staged integration tests (§13).
- **D25 record** `docs/investigations/D25_REAL_M2_INTEGRATION_VERIFICATION.md` (blob
  `a8d8fa17…`): package identity re-verification (§4, all exact), source investigation
  (§5: only origin = the Windows machine; `_transfer_delivery/m2_fix/` absent),
  sandbox capacity block (§6.2), gaps G1/G2 (§12), closure matrix (§11).
- **Windows runbook** (untracked `_transfer_delivery/m2/README_I4_M2_WINDOWS.md` +
  `I4_M2_PACKAGE_BUILD_INFO.json` + `I4_M2_TRANSFER_FACTS.json`): Windows base repo
  `main` = `6a60583f62905c1fbda9cc7529019e2a9ed0b097` ("My Engines"); run-root
  convention `G:\My Engines\I4_RUNS\<run-id>` (README §Phase D: "Output root:
  `G:\My Engines\I4_RUNS\<run-id>`"); failed run root `G:\My Engines\I4_RUNS\i4-20261007`
  is preserved evidence — do not touch; the M2 run used run id `i4-20261008-M2`.
- **D11 in-repo evidence** (identity source, D25 §4): run id `i4-20261008-M2`; composite
  `9609c7fc…`; engine `d3269b73…`; runner `f3ebf624…`; 2,462 archives /
  `54d81507…`; 5,689,949 rows; 12 partitions; manifest digest `e7c7e4c8…`;
  4,948 files / 21,119,807,344 B.

## 4. Verified package-source facts (Windows origin)

- **Expected package root (documented convention + run id):**
  `G:\My Engines\I4_RUNS\i4-20261008-M2` — the run root of the governed M2 execution
  (runbook: output root = `G:\My Engines\I4_RUNS\<run-id>`; the run's id, per the pinned
  `RUN_RECORD.json`, is `i4-20261008-M2`). The package is the **contents of that
  directory** (4,948 files incl. `PACKAGE_MANIFEST.sha256` and the last-written
  `RUN_COMPLETE.json` marker); monitor/evidence files live *outside* the root
  (`<root>.MEMORY_MONITOR*`), so the root itself must contain exactly the 4,948 files.
- **Provenance:** built and self-checked on the Windows machine by the governed runner
  (G-I4 boundary: Arena never executed the corpus); delivered to the former sandbox copy
  by the user's transfer; the only remaining source of the exact package is this
  directory on the Windows machine.
- **Known sibling (do not touch):** `G:\My Engines\I4_RUNS\i4-20261007` — preserved
  failed-run evidence; the handoff reads nothing from it.
- The Phase 1 block (§7) treats the expected root as the default candidate and, only if
  it is absent, lists the **direct children of `G:\My Engines\I4_RUNS` alone** (the
  documented run-root convention) and stops for the minimum missing path information —
  no indiscriminate filesystem scanning.

## 5. Serving implementation and test entry points (verified; no changes needed)

Re-read at baseline from the D24 implementation (byte-identical at session HEAD, §2):

- **Real-package gate:** `tests/test_serving_m2_integration.py` — class
  `M2RealPackageIntegrationTests` is `@unittest.skipIf(not os.environ.get("D24_M2_ROOT"),
  …)`; `setUpClass` takes `os.environ["D24_M2_ROOT"]` as the package root, opens the
  baseline with the pinned `DEFAULT_M2_SPEC` (full verify-01..07 incl. per-file digests),
  builds the class-(4) index into a `tempfile.mkdtemp` state dir (removed in
  `tearDownClass`). Three tests: full verification with the pinned spec; Q3 query
  (`RELIANCE`/`EQ`, expects >0 rows, sorted dates, provenance present, `raw_line`
  absent); rebuild reproducibility (`identical: true`, `rows_scanned == 5,689,949`).
  Plus `M2BaselineIdentityTests` (4 tests, always run, in-repo evidence only).
- **CLI consumer boundary:** `python -m serving {verify|build|query|rebuild|info}`
  (`PYTHONPATH=src`); `--package <root>` on all but `info`; `--state <dir>` (must be
  **outside** the package) on build/query/rebuild; `--m2` pins the M2 identity;
  exit codes 0 = ok, 2 = usage/verification failure (fail closed), 3 = index/stale
  failure.
- **API:** `serving.baseline.open_baseline(root, spec=DEFAULT_M2_SPEC,
  verify_files=True)` → verify-01..07, `BaselineError(check, detail)` on any failure.
- **Portability (code inspection — the only way available to Arena):** Windows-safe as
  written: index write uses `open(..., "w", encoding="utf-8", newline="")` (no CRLF
  translation → byte-stable cross-platform); all package-relative paths joined via
  `.replace("/", os.sep)` / `os.path.relpath(...).replace(os.sep, "/")`; all package
  reads are `"rb"` or `encoding="utf-8"` text; **no** `subprocess`, `symlink`,
  `realpath`, `chmod`, or POSIX-only construct in `src/serving/`; tests use
  `tempfile.mkdtemp` (portable). The engine import via `tests/support.py` succeeded on
  Windows during the governed M2 run itself. **Conclusion: no implementation change is
  needed to run the existing tests on Windows** (task Phase 0.5).

## 6. Windows execution constraints (readiness analysis)

- **Runtime:** Python 3, **standard library only** — no pip installs. The Windows
  machine already ran the governed runner on Python 3 (runbook Phase D: `python -B
  "$Repo\tools\i4_runner\i4_runner.py"`); `python -B` is used throughout to avoid
  `__pycache__` byproducts (D20 rectification lesson).
- **Repository requirement:** the tests import `tests.support` → `nse_engine` and read
  in-repo evidence, so a **full repo checkout** is required. Least-disruptive: a scratch
  clone of the public repo at the exact D24 commit `6997701…` into a scratch directory —
  this does **not** touch the governed "My Engines" repo (whose `main` must remain
  `6a60583f…` per the runbook) and does not push or modify any remote. Clone with
  `-c core.autocrlf=false` to preserve byte-exact source (LF).
- **Package access:** **direct read access, no copy.** The serving code opens package
  files read-only only; nothing in the test path writes into the package (the only
  writes are the class-(4) state files in the caller-supplied/temp state dir).
- **Capacity for derived state:** the class-(4) index is a single JSON document bounded
  by 2,462 per-file instrument-pair entries + counts (D24 §14: compact, low single-digit
  MB) plus a 64-byte sha256 sidecar — in a `tempfile`/state dir on any local drive. The
  scratch repo clone is ~25 MB. Nothing material is added to the package drive; the
  Phase 1 block reports the drive's free space as evidence regardless.
- **Expected wall time:** every `serving` command and the test's `setUpClass` re-run the
  full 4,948-file digest verification (by design — verify-before-operate, fail closed):
  ≈ 6 full passes over 21 GB plus one 5,689,949-row index build across steps 2–7 and the
  test — on a local NVMe expect roughly 10–25 minutes total. This is normal, not a
  stall; preserve the full session output.
- **Cross-environment note:** the class-(4) index built on Windows is byte-stable
  (newline-disabled write, canonical JSON) and is **derived state only** — it is
  evidence for the rebuild-reproducibility proof, never a substitute for the package.

## 7. Phase 1 — Windows-side evidence request (prepared for the user; read-only; fail-closed)

Run on the original Windows machine. **Read-only** (no file created/modified/copied; no
git operation; the source package is preserved). **Fail-closed** (once any check fails,
dependent checks are skipped and the verdict is FAIL). Preserved console output **is**
the Phase 1 evidence. House PowerShell contract honored: no `else`/`elseif`/`finally`,
no `exit`/`return`; state initialized and validated before dependent operations.
(Pure-PowerShell structural identity checks here; the full per-file digest verification
is the existing repository mechanism — Phase 3 step 2.)

```powershell
# D26 Phase 1 — read-only identification + structural verification of the qualified M2 package
$ErrorActionPreference = 'Stop'

$PinnedRunId          = 'i4-20261008-M2'
$PinnedCompositeRunId = '9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d'
$PinnedManifestSha256 = 'e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc'
$PinnedEngineSha256   = 'd3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9'
$PinnedRunnerSha256   = 'f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a'
$PinnedFileCount      = 4948
$PinnedTotalBytes     = 21119807344
$PinnedRows           = 5689949
$PinnedMembers        = 2462
$PinnedPartitions     = 12

Write-Output '=== D26 M2 package verification (READ-ONLY) ==='
Write-Output ('timestamp: ' + (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'))
Write-Output ('hostname: ' + $env:COMPUTERNAME)

$ExpectedRoot = 'G:\My Engines\I4_RUNS\i4-20261008-M2'
$PackageRoot = $ExpectedRoot
if ($args.Count -ge 1) { $PackageRoot = $args[0] }
Write-Output ('expected root: ' + $ExpectedRoot)
Write-Output ('package root:  ' + $PackageRoot)

$Failed = $false
try {
    if (Test-Path -LiteralPath $PackageRoot -PathType Container) {
        Write-Output 'CHECK root: PASS'
    }
    if (-not (Test-Path -LiteralPath $PackageRoot -PathType Container)) {
        $Failed = $true
        Write-Output 'CHECK root: FAIL - directory not found'
        if (Test-Path 'G:\My Engines\I4_RUNS' -PathType Container) {
            Write-Output 'direct children of G:\My Engines\I4_RUNS (scoped listing only):'
            Get-ChildItem -LiteralPath 'G:\My Engines\I4_RUNS' -Directory | ForEach-Object { Write-Output ('  ' + $_.Name) }
        }
        Write-Output 'ACTION REQUIRED: rerun with the actual package root as the first argument, then stop the handoff until verified.'
    }

    $ManifestPath = Join-Path $PackageRoot 'PACKAGE_MANIFEST.sha256'
    $MarkerPath   = Join-Path $PackageRoot 'RUN_COMPLETE.json'
    $RecordPath   = Join-Path $PackageRoot 'RUN_RECORD.json'
    if (-not $Failed) {
        foreach ($p in @($ManifestPath, $MarkerPath, $RecordPath)) {
            if (Test-Path -LiteralPath $p -PathType Leaf) {
                Write-Output ('CHECK present: PASS  ' + (Split-Path $p -Leaf))
            }
            if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
                $Failed = $true
                Write-Output ('CHECK present: FAIL  ' + $p)
            }
        }
    }

    if (-not $Failed) {
        $h = Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256
        $mh = $h.Hash.ToLower()
        Write-Output ('manifest file sha256: ' + $mh)
        if ($mh -ceq $PinnedManifestSha256) { Write-Output 'CHECK manifest-digest: PASS' }
        if (-not ($mh -ceq $PinnedManifestSha256)) { $Failed = $true; Write-Output ('CHECK manifest-digest: FAIL - expected ' + $PinnedManifestSha256) }
    }

    if (-not $Failed) {
        $marker = Get-Content -LiteralPath $MarkerPath -Raw | ConvertFrom-Json
        Write-Output ('RUN_COMPLETE: run_id=' + $marker.run_id + ' manifest=' + $marker.package_manifest_sha256 + ' rows=' + $marker.rows + ' members=' + $marker.members + ' partitions=' + $marker.partitions + ' status=' + $marker.status)
        if ($marker.run_id -ceq $PinnedRunId) { Write-Output 'CHECK marker run-id: PASS' }
        if ($marker.run_id -cne $PinnedRunId) { $Failed = $true; Write-Output 'CHECK marker run-id: FAIL' }
        if ($marker.package_manifest_sha256.ToLower() -ceq $PinnedManifestSha256) { Write-Output 'CHECK marker manifest: PASS' }
        if ($marker.package_manifest_sha256.ToLower() -cne $PinnedManifestSha256) { $Failed = $true; Write-Output 'CHECK marker manifest: FAIL' }
        if ([string]$marker.rows -ceq [string]$PinnedRows) { Write-Output 'CHECK marker rows: PASS' }
        if ([string]$marker.rows -cne [string]$PinnedRows) { $Failed = $true; Write-Output 'CHECK marker rows: FAIL' }
        if ([string]$marker.members -ceq [string]$PinnedMembers) { Write-Output 'CHECK marker members: PASS' }
        if ([string]$marker.members -cne [string]$PinnedMembers) { $Failed = $true; Write-Output 'CHECK marker members: FAIL' }
        if ([string]$marker.partitions -ceq [string]$PinnedPartitions) { Write-Output 'CHECK marker partitions: PASS' }
        if ([string]$marker.partitions -cne [string]$PinnedPartitions) { $Failed = $true; Write-Output 'CHECK marker partitions: FAIL' }
    }

    if (-not $Failed) {
        $rec = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
        Write-Output ('RUN_RECORD: run_id=' + $rec.run_id + ' composite=' + $rec.composite_run_identity + ' engine=' + $rec.engine_identity.tool_sha256 + ' runner=' + $rec.runner_identity.runner_sha256 + ' rows=' + $rec.counts.rows)
        if ($rec.run_id -ceq $PinnedRunId) { Write-Output 'CHECK record run-id: PASS' }
        if ($rec.run_id -cne $PinnedRunId) { $Failed = $true; Write-Output 'CHECK record run-id: FAIL' }
        if ($rec.composite_run_identity -ceq $PinnedCompositeRunId) { Write-Output 'CHECK composite-run-identity: PASS' }
        if ($rec.composite_run_identity -cne $PinnedCompositeRunId) { $Failed = $true; Write-Output 'CHECK composite-run-identity: FAIL' }
        if ($rec.engine_identity.tool_sha256 -ceq $PinnedEngineSha256) { Write-Output 'CHECK engine sha256: PASS' }
        if ($rec.engine_identity.tool_sha256 -cne $PinnedEngineSha256) { $Failed = $true; Write-Output 'CHECK engine sha256: FAIL' }
        if ($rec.runner_identity.runner_sha256 -ceq $PinnedRunnerSha256) { Write-Output 'CHECK runner sha256: PASS' }
        if ($rec.runner_identity.runner_sha256 -cne $PinnedRunnerSha256) { $Failed = $true; Write-Output 'CHECK runner sha256: FAIL' }
        if ([string]$rec.counts.rows -ceq [string]$PinnedRows) { Write-Output 'CHECK record rows: PASS' }
        if ([string]$rec.counts.rows -cne [string]$PinnedRows) { $Failed = $true; Write-Output 'CHECK record rows: FAIL' }
    }

    if (-not $Failed) {
        $files = @(Get-ChildItem -LiteralPath $PackageRoot -Recurse -File)
        $bytes = 0
        foreach ($f in $files) { $bytes = $bytes + $f.Length }
        Write-Output ('file count: ' + $files.Count + ' (expected ' + $PinnedFileCount + ')')
        Write-Output ('total bytes: ' + $bytes + ' (expected ' + $PinnedTotalBytes + ')')
        if ($files.Count -ceq $PinnedFileCount) { Write-Output 'CHECK file-count: PASS' }
        if ($files.Count -cne $PinnedFileCount) { $Failed = $true; Write-Output 'CHECK file-count: FAIL' }
        if ($bytes -ceq $PinnedTotalBytes) { Write-Output 'CHECK total-bytes: PASS' }
        if ($bytes -cne $PinnedTotalBytes) { $Failed = $true; Write-Output 'CHECK total-bytes: FAIL' }
    }

    $drive = $PackageRoot.Substring(0, 1)
    $disk = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='" + $drive + "':")
    Write-Output ('drive ' + $drive + ': size_bytes=' + $disk.Size + ' free_bytes=' + $disk.FreeSpace)
    Write-Output ('adjacent evidence (outside the root, listed only): ' + ((Get-ChildItem -LiteralPath (Split-Path $PackageRoot -Parent) -File | Where-Object { $_.Name -like ($PinnedRunId + '.*') } | ForEach-Object { $_.Name }) -join ', '))
}
catch {
    $Failed = $true
    Write-Output ('UNEXPECTED ERROR (fail-closed): ' + $_.Exception.Message)
}

if ($Failed) {
    Write-Output 'VERDICT: FAIL - package NOT verified. Do not run the D24 integration tests against this root; report this output and stop the handoff.'
}
if (-not $Failed) {
    Write-Output 'VERDICT: PASS - structural identity verified against the pinned M2 identity. Proceed to Phase 3 (full per-file digest verification is performed there by the existing serving verify command).'
}
```

**How to run:** save as `D26_VERIFY_M2_PACKAGE.ps1` and run
`powershell -NoProfile -ExecutionPolicy Bypass -File D26_VERIFY_M2_PACKAGE.ps1`
(add the actual package root as the first argument if it differs from the expected
root). **If VERDICT: FAIL or the root is missing:** stop; send the full console output
as evidence; do not reconstruct, requalify, or "repair" the package. **If PASS:**
proceed to §8 and preserve both outputs.

## 8. Phase 3 — test execution handoff (prepared; run on Windows after §7 PASS)

All commands are read-only with respect to the package. Preserve the full console
output and each step's exit code as evidence. Do not modify any source file.

```powershell
# D26 Phase 3 — real-M2 integration execution (Windows) — fail-closed: a failed step stops the rest
$ErrorActionPreference = 'Stop'
$PinnedHead = '69977017ffca944921f231d7904347bc582b6392'
$HandoffFailed = $false

# 1) Scratch checkout at the exact D24 implementation commit (does NOT touch the governed My Engines repo)
$Repo = "$env:USERPROFILE\D26_serving_check"
if (Test-Path -LiteralPath $Repo) {
    $HandoffFailed = $true
    Write-Output ('scratch checkout already present: ' + $Repo + ' - inspect/remove it manually, then rerun. Stopping (fail-closed).')
}
if (-not $HandoffFailed) { git clone -c core.autocrlf=false https://github.com/ramkivs/nse-historical-data-engine.git $Repo }
if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output ('clone failed (exit ' + $LASTEXITCODE + ') - stopping (fail-closed).') }
if (-not $HandoffFailed) { Set-Location $Repo }
if (-not $HandoffFailed) { git fetch origin arena/9021d1a1-nse-historical-data-engine }
if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output ('fetch failed (exit ' + $LASTEXITCODE + ') - stopping (fail-closed).') }
if (-not $HandoffFailed) { git checkout $PinnedHead }
if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output ('checkout failed (exit ' + $LASTEXITCODE + ') - stopping (fail-closed).') }
$Head = (git rev-parse HEAD)
Write-Output ('checkout HEAD: ' + $Head + ' (pinned ' + $PinnedHead + ')')
if ($Head -cne $PinnedHead) { $HandoffFailed = $true; Write-Output 'HEAD mismatch - stopping (fail-closed).' }

# 2) Existing repository mechanism: full verify-01..07 with the pinned M2 identity (expect exit 0)
if (-not $HandoffFailed) {
    $env:D24_M2_ROOT = 'G:\My Engines\I4_RUNS\i4-20261008-M2'
    $env:PYTHONPATH = 'src'
    python -B -m serving verify --package $env:D24_M2_ROOT --m2
    Write-Output ('step2 exit: ' + $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output 'serving verify failed - preserve output, stopping (fail-closed).' }
}

# 3) The staged D24 real-M2 integration tests (7 tests: 4 identity + 3 real-package; expect 0 failures, 0 skipped)
if (-not $HandoffFailed) {
    python -B -m unittest tests.test_serving_m2_integration -v
    Write-Output ('step3 exit: ' + $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output 'integration tests failed/skipped - preserve output, stopping (fail-closed).' }
}

# 4) Class-(4) index build - state directory OUTSIDE the package
if (-not $HandoffFailed) {
    python -B -m serving build --package $env:D24_M2_ROOT --state 'G:\My Engines\I4_RUNS\d26_serving_state'
    Write-Output ('step4 exit: ' + $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output 'build failed - preserve output, stopping (fail-closed).' }
}

# 5) Q3 instrument query (D16-10) over the real baseline
if (-not $HandoffFailed) {
    python -B -m serving query --package $env:D24_M2_ROOT --state 'G:\My Engines\I4_RUNS\d26_serving_state' RELIANCE EQ
    Write-Output ('step5 exit: ' + $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output 'query failed - preserve output, stopping (fail-closed).' }
}

# 6) Delegated operation (b): serving-state rebuild (expect "identical": true)
if (-not $HandoffFailed) {
    python -B -m serving rebuild --package $env:D24_M2_ROOT --state 'G:\My Engines\I4_RUNS\d26_serving_state'
    Write-Output ('step6 exit: ' + $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output 'rebuild failed - preserve output, stopping (fail-closed).' }
}

# 7) Post-run immutability proof: full verification again - every per-file digest must still match the original manifest
if (-not $HandoffFailed) {
    python -B -m serving verify --package $env:D24_M2_ROOT --m2
    Write-Output ('step7 exit: ' + $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) { $HandoffFailed = $true; Write-Output 'post-run verify failed - package state changed or mismatched - preserve output, stopping (fail-closed).' }
}

if ($HandoffFailed) {
    Write-Output 'HANDOFF RESULT: STOPPED at the failing step - no later step ran. Report the full output; do not modify source to make a test pass.'
}
if (-not $HandoffFailed) {
    Write-Output 'HANDOFF RESULT: ALL STEPS COMPLETED - preserve this full console output as the D26/G2 evidence.'
}
```

**Expected results (contract-fixed by D24 §4/§8/§12 and the pinned identity, §3/§4):**
- step 2: exit 0; `checks_passed` = verify-01..verify-07; `manifest_sha256` =
  `e7c7e4c8…`; `total_bytes` = 21,119,807,344; `run_id` = `i4-20261008-M2`; `pinned` = m2.
- step 3: `Ran 7 tests` — 7 passed, **0 skipped** (the three real-package tests must
  actually execute), 0 failures.
- step 4: exit 0; `counts.rows` = 5,689,949; 12 partitions.
- step 5: exit 0; `result_count` > 0; every row carries its D05 §8 `provenance` block;
  no `raw_line` key in any served row.
- step 6: exit 0; `identical` = true; `rows_scanned` = 5,689,949.
- step 7: exit 0 with the same pass profile as step 2 — **this is the executed
  canonical-data immutability proof** (package byte-identical to its original manifest
  after verify + test + build + query + rebuild).
- Any non-zero exit or skipped test ⇒ stop, preserve the exact output, and record the
  failure; do not modify source to make a test pass.

## 9. Remaining evidence requirements (what the handoff closes)

- **G1 (package availability):** closed by a §7 `VERDICT: PASS` output from the Windows
  machine (or, if the root differs, a PASS after rerun with the correct root).
- **G2 / D23 battery items 2/5/7 (real-package legs):** closed by the §8 output set —
  item 2 (baseline identity + full 4,948-file digest verification: steps 2+3+7), item 5
  (canonical-data immutability: step 7 vs step 2 manifest match), item 7
  (deterministic/rebuildable serving state: step 3 rebuild test + step 6 `identical`
  true). Items 1, 3, 4, 6, 8, 9, 10, 11, 12 remain FULLY VERIFIED per D25 §11.
- A subsequent Arena-side evidence record (after the user returns the Windows outputs)
  will transcribe the actual outputs into the repository; until then the integration
  tests are **prepared and staged, not executed**.

## 10. Explicit scope and non-drift statement

Scope: verify governing state; re-read D24/D25/D23; verify the serving entry points and
their portability; prepare the read-only Windows verification block and the exact
execution handoff; record the remaining evidence requirements. Non-drift: **no
implementation file changed** (worktree diff = 0 for all tracked files; the only D26
mutation is this artifact); **no canonical data, D01 inventory, qualification record, or
M2 evidence changed**; **no governance artifact changed** (D16/D21/D22/D23/D05/D08/D12/
D14/intent unchanged); **no Windows command was executed by Arena** (no Windows/
PowerShell access — standing constraint); **no package was copied, reconstructed, or
requalified**; **no promotion**: `main` remains exactly `01612f7…` (D23); the D24 and
D25 commits are unaltered on the session branch; D26 promotes nothing. Single-user
personal-use scope and all D16 §13 non-goals preserved. No test is claimed passed that
was not executed here.

## 11. Final status

> **D26 = COMPLETE / DURABLE / REMOTELY VERIFIED** (this readiness/handoff record,
> subject to the Phase 5 remote verification reported in the task's final report).
> The real-M2 integration verification itself remains **PENDING the Windows execution**:
> the package source is identified and its verification path is prepared end-to-end
> (§7/§8); the integration tests are **not** claimed passed — only the in-repo
> identity-layer and fixture evidence (D24/D25) is currently executed.
