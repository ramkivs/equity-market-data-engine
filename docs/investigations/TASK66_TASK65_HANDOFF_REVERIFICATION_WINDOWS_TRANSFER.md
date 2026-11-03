# TASK66 — TASK65 handoff re-verification and Windows transfer preparation

**Mode: investigate → verify → re-verify → rectify (authorized) → act → prove.**
Handoff investigation and preparation only: no Windows UI acceptance, no M2
modification or rerun, no server start, no captures, no acceptance script
execution from Arena.

## 1. Verified Arena repository identity (inspected, not inferred)

| Item | Verified value | How |
|---|---|---|
| Repository root | `/home/user/nse-historical-data-engine` | `git rev-parse --show-toplevel` |
| Branch | `arena/9021d1a1-nse-historical-data-engine` | `git branch --show-current` |
| Local HEAD | `6da7c6fe4ad84deb4823a9c75ffead14a01b9447` | `git rev-parse HEAD` (post-repair; see §2) |
| Remote | `https://github.com/ramkivs/nse-historical-data-engine.git` | `git remote -v` |
| Remote session branch | `6da7c6fe4ad84deb4823a9c75ffead14a01b9447` | `git ls-remote origin` (independent of local ref) |
| Remote `main` | `69977017ffca944921f231d7904347bc582b6392` (unchanged) | `git ls-remote origin` |
| Remote `evidence/i4-ui-visual-acceptance-2026-10-10` | `1b43e0d86c9f605d1c33b6a47b37865496043c9a` (unchanged) | `git ls-remote origin` |
| Remote `docs/i4-ui-mockup-references` | `726b1c3611e77640c67d86a4ee72a09cd3415b56` (unchanged) | `git ls-remote origin` |

The required TASK65 implementation commit **is** the local HEAD and the
remote session-branch tip — independently verified from both sides.

### 2. Recurring rollback found and repaired before any verification

At task start the local branch ref had been rolled back to the fork-point
`89ce965c7961088950faf08b83a31f961e6fc214` ("D07 gate charter…") and every
post-fork path (`src/`, `tests/`, `tools/`, most of `docs/`, and the whole
`_transfer_delivery/`) appeared untracked; the local commit object
`6da7c6fe…` was missing (38th occurrence of this recurring rollback).
Repair, value-audit-first:

1. `git ls-remote` — remote session branch confirmed still at
   `6da7c6fe…` (publication intact; `main`/evidence/mockup untouched).
2. Explicit-refspec fetch of the session branch — commit object restored.
3. **Value audit: all 216 files in the commit's tree vs the working tree →
   0 missing, 0 byte mismatches** (`git hash-object` per path). No
   uncommitted work could be lost.
4. Guarded `git update-ref` (only from the rollback value) + mixed
   `git reset` — branch ref and index restored; working tree untouched.
5. Post-repair: `git status --porcelain` clean except the standing
   untracked `_transfer_delivery/` (by convention, never committed — see §5).

All verification in this report was performed **after** the repair.

## 3. TASK 63 / 64 / 65 reconciliation

- **TASK63 (D41, `5e26949…`)** created the two handoff artifacts in untracked
  `_transfer_delivery/m2/ui/` (runbook + one fail-closed script), pinned to
  the then-tip `1f86d88…` (TASK62). Transfer channel documented: the user
  downloads the folder from Arena to the Windows machine ("download channel";
  never-commit rule).
- **TASK64 (`c38c481…`)** ran the visual-acceptance comparison over the
  published Windows captures (`1b43e0d8…`); disposition FAIL as an
  acceptance-evidence determination; UNEXPECTED rows D1–D8 + D24 listed the
  exact defects; root causes proven (Q8 parser contract drift; `Promise.all`
  blanking).
- **TASK65 (`6da7c6fe…`)** corrected those defects (Q8 parser contract;
  dashboard error containment; spec §4.1 title; §6.9 saved-query sidebar),
  892 OK / 14 gated-skipped, published additively, and **re-pinned both
  handoff artifacts to `6da7c6fe…`** (script `$PinnedHead`; runbook pin
  table row).

**Why the Windows copy is stale (established facts, distinguished from
assumptions):**
- *Verified in Arena:* the authoritative artifacts now pin
  `6da7c6fe…` (script line 9; runbook table); the artifacts are untracked,
  so a fresh Windows `git clone`/checkout of any commit **can never**
  contain `_transfer_delivery/` — Windows can only hold what was manually
  downloaded.
- *Observed on Windows (user-supplied, not Arena-inspectable):* the Windows
  files carry the stale `1f86d88…` pin and fingerprints
  (ps1 15,947 B / `503A1849…`; md 3,040 B / `BD99C98E…`) that do not match
  the authoritative files (sizes differ far beyond any CRLF conversion —
  they are earlier-generation copies, pre-TASK65 re-pin at the latest).
- *Not established:* what the Windows files' exact provenance/version is
  (Arena cannot and did not inspect the Windows filesystem). This does not
  affect the plan: the incoming authoritative bytes are verified
  byte-for-byte before anything runs (§6).
- *Context:* the observed Windows HEAD `9b5f0ec43383d54ab17fb995d41327ece34c3e9a`
  is not the tip of any remote ref of this repository (checked against the
  full `git ls-remote` listing; object absent locally) — a local/foreign
  commit of that checkout. The acceptance script does **not** depend on it:
  Phase A1 clones a fresh scratch into `%USERPROFILE%\I4_UI_acceptance` and
  checks out the pin; the existing checkout `G:\My Engines\10yhistoriclengine`
  is only the destination of the two handoff files and is otherwise
  untouched.

## 4. Script and runbook review (read in full; semantic, not textual)

**Script (`I4_UI_VISUAL_ACCEPTANCE_WINDOWS.ps1`, 127 lines) — all gates
verified against the actual code:**

| Required control | Present | Evidence |
|---|---|---|
| Pin = required TASK65 commit | yes | `$PinnedHead = '6da7c6fe…'` (line 9); `HEAD -cne $PinnedHead` gate (line 39) |
| Safe repo/worktree preconditions | yes | scratch dir must be absent (fail-closed if present); fresh clone with `-c core.autocrlf=false`; fetch of the pinned branch only; existing checkouts/branches never referenced |
| Mockup references + integrity gated | yes | five sha256 gates on the two mockups, spec, mockup manifest, D01 inventory (lines 42–63) — **each re-verified this task against the actual files at the pinned commit: all five match** |
| M2 package identity + manifest hash | yes | package-root existence; `PACKAGE_MANIFEST.sha256` hash `e7c7e4c8…`; `RUN_COMPLETE.json` run id `i4-20261008-M2` (lines 66–84) |
| State roots absent pre-run | yes | three roots must not pre-exist, all outside the package (lines 87–96) |
| Port 8613 free | yes | `Get-NetTCPConnection` gate (lines 99–103) |
| Foreground server, terminal stays open | yes | direct `python -B -m ui.serve …` invocation; instructions keep the terminal open (lines 106–112) |
| Capture names/viewport | yes (runbook Phase C) | `I4_UI_CAPTURE_dashboard_1536x1024.png` / `I4_UI_CAPTURE_explorer_1536x1024.png`, exactly 1536×1024, PNG dimension self-check |
| Post-capture verification read-only | yes | `python -B -m serving verify --package … --m2` — verified in `src/serving/cli.py` (`cmd_verify`): opens the baseline with full digest verification, prints JSON, writes nothing |
| Evidence + failure handling explicit | yes | per-gate PASS/FAIL lines; `$Failed` stops all later phases; RESULT line; "preserve the full console output" |
| No M2 modify/rebuild/regenerate/rerun | yes | package opened only via the read-only serving boundary; the runner is never executed (stated in runbook header) |
| No destructive reset/cleanup/deletion | yes | destructive-command scan: none (no reset/clean/Remove-Item/rebase/amend/force) |
| PowerShell restrictions honored | yes | case-insensitive scan: the only occurrences of the forbidden words are the header contract comment and descriptive "(exit N)" strings; zero `else`/`elseif`/`finally`/`exit`/`return` statements |

The `ui.serve` CLI flags used by the script were verified against
`src/ui/serve.py` (`--package --m2 --state --saved-state --history-state
--repo --bind --port` all exist), and the documented ready JSON line
matches the server's actual `sort_keys=True` emission exactly
(`{"bind": "127.0.0.1", "m2": true, "package_run_id": "i4-20261008-M2",
"port": 8613, "result": "ready", "service": "i4-ui/1.0",
"url": "http://127.0.0.1:8613/"}` — key order and values).

**Runbook (`I4_UI_VISUAL_ACCEPTANCE_WINDOWS.md`, 126 lines):** describes
Phases A–D accurately, stop rules, return bundle, and the authority-driven
deviation list (TASK64 classifications). **One discrepancy found and
corrected (see §5): body step 1 still named the old `1f86d88…` pin** while
the pin table and the script pin `6da7c6fe…`.

## 5. Discrepancies and the authorized rectification

1. **Runbook body pin reference stale** (line 36: "checkout of the pinned
   commit `1f86d88…`"). Minimum correction: that reference now reads
   "`6da7c6fe…` (the TASK65 corrected UI)". Authority: TASK66's explicit
   purpose ("re-establish the authoritative TASK65 Windows UI
   visual-acceptance handoff") with its RECTIFY phase; the target is the
   untracked delivery artifact itself — no implementation code, no M2, no
   published file touched. The script required no change (already re-pinned
   in TASK65; its hash is unchanged by this task).
2. **Windows-side copies stale** (user-observed): resolved by the verified
   byte-exact re-transfer in §6; no Arena action can or will touch Windows
   files directly.
3. **Rollback of the local ref** (§2): repaired value-audit-first; no
   content impact.

No other discrepancy found; no further change made or needed.

## 6. Authoritative artifacts, transfer mechanism, and status

**Authoritative identity (measured directly from the Arena files after the
§5 rectification):**

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `_transfer_delivery/m2/ui/I4_UI_VISUAL_ACCEPTANCE_WINDOWS.ps1` | **7,976** | **`c5e653bf5a513fbadbd4cd4a914ace27d6a8a71df9bcfdeaeb039610fefcbb20`** |
| `_transfer_delivery/m2/ui/I4_UI_VISUAL_ACCEPTANCE_WINDOWS.md` | **7,919** | **`7dac5182b9f83f6afda739117ebbff4d709d257e4c7ebeed751ff6c00d868933`** |

(Runbook pre-rectification: 7,892 B / `70f94b29a114137ef7a40a1ce163fbb1236f18f638249f5e55a4743b93af70e2` — recorded for the audit trail.)

**Transfer mechanism (the established, supported one):** `_transfer_delivery/`
is untracked delivery staging under a never-commit rule (documented in
`_transfer_delivery/README.md`; the folder holds multi-GB base64 payloads
and is excluded from the public repository by convention — it is not
`.gitignore`d, it is simply never committed). The channel is therefore the
**download channel**: bytes cross the boundary via the user, with
byte-for-byte verification on arrival (manifest + sha256 + verify-script
pattern used by every prior transfer: D08, I4_RUNNER, m2/m2_fix).

To make the transfer paste-able and byte-exact without a manual copy step,
the block below embeds the exact authoritative bytes as base64 (generated
from the verified files; round-trip re-hashed to the two authoritative
SHA-256s before embedding). It stages as `*.incoming`, verifies size +
sha256, and replaces the existing files **only after** both verify —
existing Windows files are preserved until the incoming artifacts are
independently verified (TASK66 rule: preserve, then replace).

**Transfer status: PREPARED.** The mechanism is fully specified and the
embedded bytes are verified here; completion will be established only by
the block's own GATE G3 PASS output on Windows (which is the transfer
evidence to send back). It is NOT claimed complete.

### Next Windows step 1 — transfer + verify (run this block as-is)

```powershell
# TASK66 — transfer + verify of the authoritative TASK65 handoff artifacts (byte-exact)
# Contract honored: no exit/return/else/elseif/finally; the terminal stays open;
# existing Windows files are preserved until the incoming files verify (fail-closed).
$ErrorActionPreference = 'Stop'

$Checkout = 'G:\My Engines\10yhistoriclengine'
$Dir = Join-Path $Checkout '_transfer_delivery\m2\ui'
$Ps1Name = 'I4_UI_VISUAL_ACCEPTANCE_WINDOWS.ps1'
$MdName  = 'I4_UI_VISUAL_ACCEPTANCE_WINDOWS.md'
$Ps1Exp  = 'c5e653bf5a513fbadbd4cd4a914ace27d6a8a71df9bcfdeaeb039610fefcbb20'
$MdExp   = '7dac5182b9f83f6afda739117ebbff4d709d257e4c7ebeed751ff6c00d868933'
$Ps1Size = 7976
$MdSize  = 7919
$Failed = $false

Write-Output '=== TASK66 handoff transfer (staged, verified, then replaced) ==='
Write-Output ('timestamp: ' + (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'))

# --- G0: the Windows checkout must exist (nothing outside _transfer_delivery is touched) ---
if (-not (Test-Path -LiteralPath (Join-Path $Checkout '.git'))) {
    $Failed = $true
    Write-Output 'GATE G0: FAIL - ' + $Checkout + '\.git not found. Stop; do not run anything further; send this output to Arena.'
}
if (-not $Failed) {
    if (-not (Test-Path -LiteralPath $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null }
    Write-Output 'GATE G0: PASS (Windows checkout present; handoff dir ' + $Dir + ' ready)'
}

$Ps1B64 = 'IyBUQVNLNjMg4oCUIEk0IGZpcnN0LXJlbGVhc2UgVUkgdmlzdWFsIGFjY2VwdGFuY2UgKFdpbmRvd3MpIOKAlCBmYWlsLWNsb3NlZAojIENvbnRyYWN0IGhvbm9yZWQ6IG5vIGV4aXQvcmV0dXJuL2Vsc2UvZWxzZWlmL2ZpbmFsbHk7IHRoZSB0ZXJtaW5hbCBzdGF5cyBvcGVuOwojIHRoZSBNMiBwYWNrYWdlIGlzIG9wZW5lZCByZWFkLW9ubHkgKG5vIGZpbGUgY3JlYXRlZC9tb2RpZmllZC9jb3BpZWQgaW5zaWRlIGl0KS4KIyBUaGlzIHNjcmlwdCBkb2VzIE5PVCBleGVjdXRlIHRoZSBNMiBydW5uZXIgYW5kIGRvZXMgTk9UIHJlLXF1YWxpZnkgdGhlIHBhY2thZ2U6CiMgdGhlIGZ1bGwgNCw5NDgtZmlsZSBkaWdlc3QgdmVyaWZpY2F0aW9uIGF0IHNlcnZlciBzdGFydCBpcyB0aGUgZXhpc3Rpbmcgc2VydmluZwojIGJvdW5kYXJ5IG1lY2hhbmlzbSAoc2VydmluZy5iYXNlbGluZS5vcGVuX2Jhc2VsaW5lLCB2ZXJpZnlfZmlsZXM9VHJ1ZSkuCiRFcnJvckFjdGlvblByZWZlcmVuY2UgPSAnU3RvcCcKCiRQaW5uZWRIZWFkICAgICAgICAgICAgPSAnNmRhN2M2ZmU0YWQ4NGRlYjQ4MjNhOWM3NWZmZWFkMTRhMDFiOTQ0NycKJFBpbm5lZEJyYW5jaCAgICAgICAgICA9ICdhcmVuYS85MDIxZDFhMS1uc2UtaGlzdG9yaWNhbC1kYXRhLWVuZ2luZScKJFBpbm5lZERhc2hib2FyZFBuZyAgICA9ICdmYTExZjBlODY3ZDBmOGFhMWRmNDFiM2FiODhjNTFkMjdjZTJjY2Q1MGU3OTBlNTE4MWVjZjQ1YjJhYTFhZjg1JwokUGlubmVkRXhwbG9yZXJQbmcgICAgID0gJzUzZjIwYjY0ODRmMDJhYzI4ZjRmZGY1ZjgwMTI1YjM4ZTEzOGUyNTZlYmY4YmE1ZDI2Y2ZiM2VlOWI0NmJkMTknCiRQaW5uZWRTcGVjTWQgICAgICAgICAgPSAnYWNhNWVjYTkwNWIxNTFlMGY5OGYwNDVmNWIzNGJiYjIzMmU1YWYyN2U4MjhhY2Y3MjVjYWQ5MmFkNmQ2MjE2NScKJFBpbm5lZE1hbmlmZXN0VHh0ICAgICA9ICdiODNmZjhhMTQxZjY1ZmFiZDI4YzdhYjEwZWViZjM5MDgwOWEzYTI4OTA2ZTcwMTdjNGIyMDY4NzhkNmI5ZjI3JwokUGlubmVkRDAxSW52ZW50b3J5ICAgID0gJzMzNmI5NTMxY2QzNGY0OGU5YTJlN2U3NTkzY2M0ZTljMjczNmIzODY0ZDgyMTNiYzY1ZDZhYjhiNDg4NzI5ZDInCiRQaW5uZWRNYW5pZmVzdFNoYTI1NiAgPSAnZTdjN2U0YzgyNzFmM2ExYzhlZjQyZDc2YjkyNmZlMDQ4YTg5OTdhMzQyYzkyZDg5ODE5ZWVjZDc5ZTczYjlkYycKCiRGYWlsZWQgPSAkZmFsc2UKCldyaXRlLU91dHB1dCAnPT09IFRBU0s2MyBJNCBVSSB2aXN1YWwgYWNjZXB0YW5jZSAoV2luZG93cykgPT09JwpXcml0ZS1PdXRwdXQgKCd0aW1lc3RhbXA6ICcgKyAoR2V0LURhdGUgLUZvcm1hdCAneXl5eS1NTS1kZFRISDptbTpzc3p6eicpKQpXcml0ZS1PdXRwdXQgKCdob3N0bmFtZTogJyArICRlbnY6Q09NUFVURVJOQU1FKQoKIyAtLS0gUGhhc2UgQTE6IHNjcmF0Y2ggY2hlY2tvdXQgcGlubmVkIHRvIHRoZSBzZXNzaW9uIHRpcCAoZG9lcyBOT1QgdG91Y2ggdGhlIGdvdmVybmVkCiMgIk15IEVuZ2luZXMiIHJlcG9zaXRvcnksIHRoZSBEMjYgc2NyYXRjaCwgb3IgYW55IHJlbW90ZSByZWYpIC0tLQokUmVwbyA9ICIkZW52OlVTRVJQUk9GSUxFXEk0X1VJX2FjY2VwdGFuY2UiCmlmIChUZXN0LVBhdGggLUxpdGVyYWxQYXRoICRSZXBvKSB7CiAgICAkRmFpbGVkID0gJHRydWUKICAgIFdyaXRlLU91dHB1dCAoJ3NjcmF0Y2ggY2hlY2tvdXQgYWxyZWFkeSBwcmVzZW50OiAnICsgJFJlcG8gKyAnIC0gaW5zcGVjdC9yZW1vdmUgaXQgbWFudWFsbHksIHRoZW4gcmVydW4uIFN0b3BwaW5nIChmYWlsLWNsb3NlZCkuJykKfQppZiAoLW5vdCAkRmFpbGVkKSB7IGdpdCBjbG9uZSAtYyBjb3JlLmF1dG9jcmxmPWZhbHNlIGh0dHBzOi8vZ2l0aHViLmNvbS9yYW1raXZzL25zZS1oaXN0b3JpY2FsLWRhdGEtZW5naW5lLmdpdCAkUmVwbyB9CmlmICgkTEFTVEVYSVRDT0RFIC1uZSAwKSB7ICRGYWlsZWQgPSAkdHJ1ZTsgV3JpdGUtT3V0cHV0ICgnY2xvbmUgZmFpbGVkIChleGl0ICcgKyAkTEFTVEVYSVRDT0RFICsgJykgLSBzdG9wcGluZyAoZmFpbC1jbG9zZWQpLicpIH0KaWYgKC1ub3QgJEZhaWxlZCkgeyBnaXQgLUMgJFJlcG8gZmV0Y2ggb3JpZ2luICRQaW5uZWRCcmFuY2ggfQppZiAoJExBU1RFWElUQ09ERSAtbmUgMCkgeyAkRmFpbGVkID0gJHRydWU7IFdyaXRlLU91dHB1dCAoJ2ZldGNoIGZhaWxlZCAoZXhpdCAnICsgJExBU1RFWElUQ09ERSArICcpIC0gc3RvcHBpbmcgKGZhaWwtY2xvc2VkKS4nKSB9CmlmICgtbm90ICRGYWlsZWQpIHsgZ2l0IC1DICRSZXBvIGNoZWNrb3V0ICRQaW5uZWRIZWFkIH0KaWYgKCRMQVNURVhJVENPREUgLW5lIDApIHsgJEZhaWxlZCA9ICR0cnVlOyBXcml0ZS1PdXRwdXQgKCdjaGVja291dCBmYWlsZWQgKGV4aXQgJyArICRMQVNURVhJVENPREUgKyAnKSAtIHN0b3BwaW5nIChmYWlsLWNsb3NlZCkuJykgfQokSGVhZCA9IChnaXQgLUMgJFJlcG8gcmV2LXBhcnNlIEhFQUQpCldyaXRlLU91dHB1dCAoJ2NoZWNrb3V0IEhFQUQ6ICcgKyAkSGVhZCArICcgKHBpbm5lZCAnICsgJFBpbm5lZEhlYWQgKyAnKScpCmlmICgkSGVhZCAtY25lICRQaW5uZWRIZWFkKSB7ICRGYWlsZWQgPSAkdHJ1ZTsgV3JpdGUtT3V0cHV0ICdIRUFEIG1pc21hdGNoIC0gc3RvcHBpbmcgKGZhaWwtY2xvc2VkKS4nIH0KCiMgLS0tIFBoYXNlIEEyOiBkZXNpZ24gcmVmZXJlbmNlcyArIEQwMSBpbnZlbnRvcnkgaWRlbnRpdHkgKHNoYTI1NiBvZiB0aGUgY2hlY2tlZC1vdXQgZmlsZXMpIC0tLQppZiAoLW5vdCAkRmFpbGVkKSB7CiAgICAkcmVmRmlsZXMgPSBAKAogICAgICAgIEAoJ2V2aWRlbmNlXDEweSBoaXN0b3JpY2FsIGVuZ2luZS5wbmcnLCAgICAgICAgICAgICAgICAgJFBpbm5lZERhc2hib2FyZFBuZyksCiAgICAgICAgQCgnZXZpZGVuY2VcMTB5IGhpc3RvcmljYWwgZW5naW5lLWRhdGEgZXhwbG9yZXIucG5nJywgICAkUGlubmVkRXhwbG9yZXJQbmcpLAogICAgICAgIEAoJ2RvY3NcZGVzaWduXEk0X0hJU1RPUklDQUxfREFUQV9FTkdJTkVfVUlfU1BFQy5tZCcsICAgJFBpbm5lZFNwZWNNZCksCiAgICAgICAgQCgnZXZpZGVuY2VcSTRfVUlfTU9DS1VQX1JFRkVSRU5DRVMudHh0JywgICAgICAgICAgICAgICAkUGlubmVkTWFuaWZlc3RUeHQpLAogICAgICAgIEAoJ2V2aWRlbmNlXGludmVudG9yeVxmaWxlX2ludmVudG9yeS5qc29uJywgICAgICAgICAgICAgJFBpbm5lZEQwMUludmVudG9yeSkKICAgICkKICAgIGZvcmVhY2ggKCRwYWlyIGluICRyZWZGaWxlcykgewogICAgICAgIGlmICgtbm90ICRGYWlsZWQpIHsKICAgICAgICAgICAgJHAgPSBKb2luLVBhdGggJFJlcG8gJHBhaXJbMF0KICAgICAgICAgICAgaWYgKFRlc3QtUGF0aCAtTGl0ZXJhbFBhdGggJHAgLVBhdGhUeXBlIExlYWYpIHsKICAgICAgICAgICAgICAgICRoID0gKEdldC1GaWxlSGFzaCAtTGl0ZXJhbFBhdGggJHAgLUFsZ29yaXRobSBTSEEyNTYpLkhhc2guVG9Mb3dlcigpCiAgICAgICAgICAgICAgICBpZiAoJGggLWNlcSAkcGFpclsxXSkgeyBXcml0ZS1PdXRwdXQgKCdDSEVDSyByZWY6IFBBU1MgICcgKyAkcGFpclswXSkgfQogICAgICAgICAgICAgICAgaWYgKC1ub3QgKCRoIC1jZXEgJHBhaXJbMV0pKSB7ICRGYWlsZWQgPSAkdHJ1ZTsgV3JpdGUtT3V0cHV0ICgnQ0hFQ0sgcmVmOiBGQUlMICAnICsgJHBhaXJbMF0gKyAnIC0gZXhwZWN0ZWQgJyArICRwYWlyWzFdICsgJyBnb3QgJyArICRoKSB9CiAgICAgICAgICAgIH0KICAgICAgICAgICAgaWYgKC1ub3QgKFRlc3QtUGF0aCAtTGl0ZXJhbFBhdGggJHAgLVBhdGhUeXBlIExlYWYpKSB7ICRGYWlsZWQgPSAkdHJ1ZTsgV3JpdGUtT3V0cHV0ICgnQ0hFQ0sgcmVmOiBGQUlMICAnICsgJHBhaXJbMF0gKyAnIC0gZmlsZSBtaXNzaW5nJykgfQogICAgICAgIH0KICAgIH0KfQoKIyAtLS0gUGhhc2UgQTM6IE0yIHBhY2thZ2Ugcm9vdCBpZGVudGl0eSAoc3RydWN0dXJlIGhlcmU7IHRoZSBmdWxsIHBlci1maWxlIGRpZ2VzdAojIHZlcmlmaWNhdGlvbiBydW5zIGluc2lkZSB0aGUgc2VydmluZyBiYXNlbGluZSBjaGVjayBhdCBzZXJ2ZXIgc3RhcnQpIC0tLQokUGFja2FnZVJvb3QgPSAnRzpcTXkgRW5naW5lc1xJNF9SVU5TXGk0LTIwMjYxMDA4LU0yJwppZiAoLW5vdCAkRmFpbGVkKSB7CiAgICBpZiAoVGVzdC1QYXRoIC1MaXRlcmFsUGF0aCAkUGFja2FnZVJvb3QgLVBhdGhUeXBlIENvbnRhaW5lcikgeyBXcml0ZS1PdXRwdXQgJ0NIRUNLIHBhY2thZ2Ugcm9vdDogUEFTUyAgJyArICRQYWNrYWdlUm9vdCB9CiAgICBpZiAoLW5vdCAoVGVzdC1QYXRoIC1MaXRlcmFsUGF0aCAkUGFja2FnZVJvb3QgLVBhdGhUeXBlIENvbnRhaW5lcikpIHsKICAgICAgICAkRmFpbGVkID0gJHRydWUKICAgICAgICBXcml0ZS1PdXRwdXQgKCdDSEVDSyBwYWNrYWdlIHJvb3Q6IEZBSUwgLSAnICsgJFBhY2thZ2VSb290ICsgJyBub3QgZm91bmQuIFJ1biBEMjZfVkVSSUZZX00yX1BBQ0tBR0UucHMxIGZpcnN0IGFuZCBzdG9wIHRoZSBoYW5kb2ZmIHVudGlsIFZFUkRJQ1Q6IFBBU1MuJykKICAgIH0KfQppZiAoLW5vdCAkRmFpbGVkKSB7CiAgICAkbWggPSAoR2V0LUZpbGVIYXNoIC1MaXRlcmFsUGF0aCAoSm9pbi1QYXRoICRQYWNrYWdlUm9vdCAnUEFDS0FHRV9NQU5JRkVTVC5zaGEyNTYnKSAtQWxnb3JpdGhtIFNIQTI1NikuSGFzaC5Ub0xvd2VyKCkKICAgIFdyaXRlLU91dHB1dCAoJ3BhY2thZ2UgbWFuaWZlc3QgZmlsZSBzaGEyNTY6ICcgKyAkbWgpCiAgICBpZiAoJG1oIC1jZXEgJFBpbm5lZE1hbmlmZXN0U2hhMjU2KSB7IFdyaXRlLU91dHB1dCAnQ0hFQ0sgcGFja2FnZSBtYW5pZmVzdDogUEFTUycgfQogICAgaWYgKC1ub3QgKCRtaCAtY2VxICRQaW5uZWRNYW5pZmVzdFNoYTI1NikpIHsgJEZhaWxlZCA9ICR0cnVlOyBXcml0ZS1PdXRwdXQgKCdDSEVDSyBwYWNrYWdlIG1hbmlmZXN0OiBGQUlMIC0gZXhwZWN0ZWQgJyArICRQaW5uZWRNYW5pZmVzdFNoYTI1NikgfQogICAgJHJrID0gKEdldC1Db250ZW50IC1MaXRlcmFsUGF0aCAoSm9pbi1QYXRoICRQYWNrYWdlUm9vdCAnUlVOX0NPTVBMRVRFLmpzb24nKSAtUmF3IHwgQ29udmVydEZyb20tSnNvbikucnVuX2lkCiAgICBXcml0ZS1PdXRwdXQgKCdSVU5fQ09NUExFVEUgcnVuX2lkOiAnICsgJHJrKQogICAgaWYgKCRyayAtY2VxICdpNC0yMDI2MTAwOC1NMicpIHsgV3JpdGUtT3V0cHV0ICdDSEVDSyBwYWNrYWdlIHJ1biBpZDogUEFTUycgfQogICAgaWYgKC1ub3QgKCRyayAtY2VxICdpNC0yMDI2MTAwOC1NMicpKSB7ICRGYWlsZWQgPSAkdHJ1ZTsgV3JpdGUtT3V0cHV0ICdDSEVDSyBwYWNrYWdlIHJ1biBpZDogRkFJTCcgfQp9CgojIC0tLSBQaGFzZSBBNDogZGVyaXZlZC91c2VyLXN0YXRlIHJvb3RzIG11c3Qgbm90IHByZS1leGlzdCAoYWxsIE9VVFNJREUgdGhlIHBhY2thZ2UpIC0tLQokU3RhdGVSb290ICAgPSAnRzpcTXkgRW5naW5lc1xJNF9SVU5TXGk0X3VpX3NlcnZpbmdfc3RhdGUnCiRTYXZlZFJvb3QgICA9ICdHOlxNeSBFbmdpbmVzXEk0X1JVTlNcaTRfdWlfc2F2ZWRfc3RhdGUnCiRIaXN0b3J5Um9vdCA9ICdHOlxNeSBFbmdpbmVzXEk0X1JVTlNcaTRfdWlfaGlzdG9yeV9zdGF0ZScKZm9yZWFjaCAoJHIgaW4gQCgkU3RhdGVSb290LCAkU2F2ZWRSb290LCAkSGlzdG9yeVJvb3QpKSB7CiAgICBpZiAoLW5vdCAkRmFpbGVkKSB7CiAgICAgICAgaWYgKFRlc3QtUGF0aCAtTGl0ZXJhbFBhdGggJHIpIHsKICAgICAgICAgICAgJEZhaWxlZCA9ICR0cnVlCiAgICAgICAgICAgIFdyaXRlLU91dHB1dCAoJ3N0YXRlIHJvb3QgYWxyZWFkeSBleGlzdHMgLSBpbnNwZWN0L3JlbW92ZSBpdCBtYW51YWxseSwgdGhlbiByZXJ1bjogJyArICRyICsgJyAoZmFpbC1jbG9zZWQpLicpCiAgICAgICAgfQogICAgfQp9CgojIC0tLSBQaGFzZSBBNTogcG9ydCA4NjEzIG11c3QgYmUgZnJlZSBvbiBsb29wYmFjayAtLS0KaWYgKC1ub3QgJEZhaWxlZCkgewogICAgJGluVXNlID0gR2V0LU5ldFRDUENvbm5lY3Rpb24gLUxvY2FsUG9ydCA4NjEzIC1TdGF0ZSBMaXN0ZW4gLUVycm9yQWN0aW9uIFNpbGVudGx5Q29udGludWUKICAgIGlmICgkaW5Vc2UpIHsgJEZhaWxlZCA9ICR0cnVlOyBXcml0ZS1PdXRwdXQgJ3BvcnQgODYxMyBpcyBhbHJlYWR5IGluIHVzZSAtIHN0b3AgdGhlIGhvbGRpbmcgcHJvY2VzcyBvciByZXJ1biB3aXRoIGEgZGlmZmVyZW50IC0tcG9ydCAoZmFpbC1jbG9zZWQpLicgfQogICAgaWYgKC1ub3QgJGluVXNlKSB7IFdyaXRlLU91dHB1dCAnQ0hFQ0sgcG9ydCA4NjEzOiBQQVNTIChmcmVlKScgfQp9CgojIC0tLSBQaGFzZSBCOiBzdGFydCB0aGUgVUkgc2VydmVyIGluIHRoZSBGT1JFR1JPVU5EICh0aGUgdGVybWluYWwgc3RheXMgb3BlbiB3aGlsZSBpdCBydW5zKSAtLS0KaWYgKC1ub3QgJEZhaWxlZCkgewogICAgU2V0LUxvY2F0aW9uICRSZXBvCiAgICAkZW52OlBZVEhPTlBBVEggPSAnc3JjJwogICAgV3JpdGUtT3V0cHV0ICdTdGFydGluZyBVSSBzZXJ2ZXIuIEZJUlNUIFNUQVJUIHBlcmZvcm1zIHRoZSBmdWxsIDQsOTQ4LWZpbGUgcGFja2FnZSBkaWdlc3QgdmVyaWZpY2F0aW9uIHBsdXMgYSBvbmUtdGltZSBpbmRleCBidWlsZCBvdmVyIDUsNjg5LDk0OSByb3dzOiBleHBlY3Qgcm91Z2hseSAzLTE1IG1pbnV0ZXMgZGVwZW5kaW5nIG9uIHRoZSBkcml2ZS4gVGhpcyBpcyBub3JtYWwsIG5vdCBhIHN0YWxsLiBEbyBub3QgY2xvc2UgdGhlIHRlcm1pbmFsLicKICAgIHB5dGhvbiAtQiAtbSB1aS5zZXJ2ZSAtLXBhY2thZ2UgJFBhY2thZ2VSb290IC0tbTIgLS1zdGF0ZSAkU3RhdGVSb290IC0tc2F2ZWQtc3RhdGUgJFNhdmVkUm9vdCAtLWhpc3Rvcnktc3RhdGUgJEhpc3RvcnlSb290IC0tcmVwbyAkUmVwbyAtLWJpbmQgMTI3LjAuMC4xIC0tcG9ydCA4NjEzCiAgICBXcml0ZS1PdXRwdXQgKCd1aS5zZXJ2ZSBleGl0OiAnICsgJExBU1RFWElUQ09ERSArICcgKHRoZSBzZXJ2ZXIgc3RvcHMgb25seSB3aGVuIHlvdSBwcmVzcyBDdHJsK0MgaW4gdGhpcyB0ZXJtaW5hbCknKQogICAgV3JpdGUtT3V0cHV0ICdOb3cgcGVyZm9ybSB0aGUgUGhhc2UgQyBjYXB0dXJlIGluIHRoZSBicm93c2VyIChzZWUgSTRfVUlfVklTVUFMX0FDQ0VQVEFOQ0VfV0lORE9XUy5tZCksIHRoZW4gcHJlc3MgQ3RybCtDIGhlcmUgdG8gc3RvcCB0aGUgc2VydmVyLicKfQoKIyAtLS0gUGhhc2UgRCAoYWZ0ZXIgeW91IGhhdmUgY2FwdHVyZWQgYW5kIHByZXNzZWQgQ3RybCtDKTogb3B0aW9uYWwgaW1tdXRhYmlsaXR5IHByb29mIC0tLQppZiAoLW5vdCAkRmFpbGVkKSB7CiAgICBXcml0ZS1PdXRwdXQgJ09wdGlvbmFsIGZpbmFsIHByb29mIChleGlzdGluZyByZXBvc2l0b3J5IG1lY2hhbmlzbSk6IHRoZSBwYWNrYWdlIG11c3Qgc3RpbGwgdmVyaWZ5IGJ5dGUtaWRlbnRpY2FsIHRvIGl0cyBvcmlnaW5hbCBtYW5pZmVzdC4nCiAgICBweXRob24gLUIgLW0gc2VydmluZyB2ZXJpZnkgLS1wYWNrYWdlICRQYWNrYWdlUm9vdCAtLW0yCiAgICBXcml0ZS1PdXRwdXQgKCdwb3N0LWNhcHR1cmUgdmVyaWZ5IGV4aXQ6ICcgKyAkTEFTVEVYSVRDT0RFICsgJyAoZXhwZWN0ZWQgMCknKQp9CgppZiAoJEZhaWxlZCkgewogICAgV3JpdGUtT3V0cHV0ICdSRVNVTFQ6IFNUT1BQRUQgYXQgYSBmYWlsZWQgY2hlY2sgLSBubyBsYXRlciBwaGFzZSByYW4uIFByZXNlcnZlIHRoaXMgZnVsbCBjb25zb2xlIG91dHB1dCBhcyBldmlkZW5jZTsgZG8gbm90IG1vZGlmeSBhbnkgc291cmNlIG9yIHBhY2thZ2UgZmlsZTsgcmVwb3J0IHRoZSBvdXRwdXQgYW5kIHN0b3AgdGhlIGhhbmRvZmYuJwp9CmlmICgtbm90ICRGYWlsZWQpIHsKICAgIFdyaXRlLU91dHB1dCAnUkVTVUxUOiBhbGwgYXV0b21hdGVkIGNoZWNrcyBwYXNzZWQgLSBwcmVzZXJ2ZSB0aGlzIGZ1bGwgY29uc29sZSBvdXRwdXQgcGx1cyB0aGUgdHdvIGNhcHR1cmUgUE5HcywgdGhlIHJlYWR5IEpTT04gbGluZSBhbmQgdGhlIC9hcGkvc3RhdHVzIEpTT04gYXMgdGhlIFRBU0s2MyBXaW5kb3dzIGV2aWRlbmNlLicKfQo='
$MdB64  = 'IyBUQVNLNjMg4oCUIEk0IGZpcnN0LXJlbGVhc2UgVUkgdmlzdWFsIGFjY2VwdGFuY2U6IFdpbmRvd3MgcnVuYm9vawoKKipNb2RlOiB2aXN1YWwgYWNjZXB0YW5jZSBvZiB0aGUgY29tcGxldGVkIGZpcnN0LXJlbGVhc2UgRGFzaGJvYXJkICsgRGF0YSBFeHBsb3JlciBhZ2FpbnN0IHRoZQpxdWFsaWZpZWQgTTIgYmFzZWxpbmUuKiogVGhpcyBpcyBOT1QgTTIgcXVhbGlmaWNhdGlvbiAodGhlIHJ1bm5lciBpcyBuZXZlciBleGVjdXRlZCBoZXJlKSBhbmQgTk9UCnByb2R1Y3Rpb24gYWN0aXZpdHkuIFRoZSBNMiBwYWNrYWdlIGlzIG9wZW5lZCAqKnJlYWQtb25seSoqIHRocm91Z2ggdGhlIGV4aXN0aW5nIHNlcnZpbmcgYm91bmRhcnksCndoaWNoIGJ5IGRlc2lnbiB2ZXJpZmllcyBhbGwgNCw5NDggcGFja2FnZSBkaWdlc3RzIGJlZm9yZSBzZXJ2aW5nIGFueXRoaW5nLgoKKipQaW5uZWQgaGFuZG9mZiBpZGVudGl0eSAodGhlIHJlLXBpbm5lZCBzZXNzaW9uIHRpcCDigJQgc3VwZXJzZWRlcyB0aGUgRDI2IFBoYXNlLTMgcGluCmA2OTk3NzAxN+KApmAgZm9yIHRoaXMgVUkgd29yaywgd2hpY2ggcHJlZGF0ZXMgYHNyYy91aWApOioqCgp8IEl0ZW0gfCBWYWx1ZSB8CnwtLS18LS0tfAp8IFNlc3Npb24gYnJhbmNoIHwgYGFyZW5hLzkwMjFkMWExLW5zZS1oaXN0b3JpY2FsLWRhdGEtZW5naW5lYCB8CnwgKipQaW5uZWQgY29tbWl0KiogfCBgNmRhN2M2ZmU0YWQ4NGRlYjQ4MjNhOWM3NWZmZWFkMTRhMDFiOTQ0N2AgKFRBU0s2NSBjb3JyZWN0ZWQgVUk7IGFkZGl0aXZlIG92ZXIgYGMzOGM0ODHigKZgIFRBU0s2NCByZXBvcnQsIHdoaWNoIGlzIG92ZXIgYDVlMjY5NDnigKZgIEQ0MSwgb3ZlciBgMWY4NmQ4OOKApmAgVEFTSzYyKSB8CnwgRGFzaGJvYXJkIG1vY2t1cCAoY29tcGFyZSB0YXJnZXQpIHwgYGV2aWRlbmNlLzEweSBoaXN0b3JpY2FsIGVuZ2luZS5wbmdgIOKAlCAxLDc3Myw3NjcgQiDigJQgc2hhMjU2IGBmYTExZjBlODY3ZDBmOGFhMWRmNDFiM2FiODhjNTFkMjdjZTJjY2Q1MGU3OTBlNTE4MWVjZjQ1YjJhYTFhZjg1YCB8CnwgRGF0YSBFeHBsb3JlciBtb2NrdXAgKGNvbXBhcmUgdGFyZ2V0KSB8IGBldmlkZW5jZS8xMHkgaGlzdG9yaWNhbCBlbmdpbmUtZGF0YSBleHBsb3Jlci5wbmdgIOKAlCAxLDg0MiwwMTIgQiDigJQgc2hhMjU2IGA1M2YyMGI2NDg0ZjAyYWMyOGY0ZmRmNWY4MDEyNWIzOGUxMzhlMjU2ZWJmOGJhNWQyNmNmYjNlZTliNDZiZDE5YCB8CnwgUHVibGlzaGVkIHNwZWMgKGF1dGhvcml0eSkgfCBgZG9jcy9kZXNpZ24vSTRfSElTVE9SSUNBTF9EQVRBX0VOR0lORV9VSV9TUEVDLm1kYCDigJQgc2hhMjU2IGBhY2E1ZWNhOTA1YjE1MWUwZjk4ZjA0NWY1YjM0YmJiMjMyZTVhZjI3ZTgyOGFjZjcyNWNhZDkyYWQ2ZDYyMTY1YCB8CnwgTW9ja3VwIHJlZmVyZW5jZSBtYW5pZmVzdCB8IGBldmlkZW5jZS9JNF9VSV9NT0NLVVBfUkVGRVJFTkNFUy50eHRgIOKAlCBzaGEyNTYgYGI4M2ZmOGExNDFmNjVmYWJkMjhjN2FiMTBlZWJmMzkwODA5YTNhMjg5MDZlNzAxN2M0YjIwNjg3OGQ2YjlmMjdgIHwKfCBNMiBwYWNrYWdlIHJvb3QgfCBgRzpcTXkgRW5naW5lc1xJNF9SVU5TXGk0LTIwMjYxMDA4LU0yYCAocnVuIGlkIGBpNC0yMDI2MTAwOC1NMmA7IG1hbmlmZXN0IGZpbGUgc2hhMjU2IGBlN2M3ZTRjODI3MWYzYTFjOGVmNDJkNzZiOTI2ZmUwNDhhODk5N2EzNDJjOTJkODk4MTllZWNkNzllNzNiOWRjYDsgNCw5NDggZmlsZXMgLyAyMSwxMTksODA3LDM0NCBCKSB8CnwgRDAxIGludmVudG9yeSAoaW4tcmVwbywgYXQgdGhlIHBpbikgfCBgZXZpZGVuY2UvaW52ZW50b3J5L2ZpbGVfaW52ZW50b3J5Lmpzb25gIOKAlCBzaGEyNTYgYDMzNmI5NTMxY2QzNGY0OGU5YTJlN2U3NTkzY2M0ZTljMjczNmIzODY0ZDgyMTNiYzY1ZDZhYjhiNDg4NzI5ZDJgIHwKCioqRG8gbm90IHRvdWNoOioqIGBHOlxNeSBFbmdpbmVzXEk0X1JVTlNcaTQtMjAyNjEwMDdgIChwcmVzZXJ2ZWQgZmFpbGVkLXJ1biBldmlkZW5jZSksIHRoZQpnb3Zlcm5lZCAiTXkgRW5naW5lcyIgcmVwb3NpdG9yeSwgdGhlIEQyNiBzY3JhdGNoIChgJVVTRVJQUk9GSUxFJVxEMjZfc2VydmluZ19jaGVja2ApLCBhbmQgYW55CmZpbGUgaW5zaWRlIHRoZSBNMiBwYWNrYWdlLgoKIyMgUGhhc2UgQStCIOKAlCBhdXRvbWF0ZWQgKG9uZSBzY3JpcHQsIGZhaWwtY2xvc2VkKQoKU2F2ZSBgSTRfVUlfVklTVUFMX0FDQ0VQVEFOQ0VfV0lORE9XUy5wczFgICh0aGlzIGZvbGRlcikgYW5kIHJ1bjoKCmBgYHBvd2Vyc2hlbGwKcG93ZXJzaGVsbCAtTm9Qcm9maWxlIC1FeGVjdXRpb25Qb2xpY3kgQnlwYXNzIC1GaWxlIEk0X1VJX1ZJU1VBTF9BQ0NFUFRBTkNFX1dJTkRPV1MucHMxCmBgYAoKV2hhdCBpdCBkb2VzIChhbnkgZmFpbHVyZSBzdG9wcyBldmVyeXRoaW5nOyBwcmVzZXJ2ZSB0aGUgZnVsbCBjb25zb2xlIG91dHB1dCk6CjEuIEZyZXNoIHNjcmF0Y2ggY2xvbmUgb2YgdGhlIHB1YmxpYyByZXBvc2l0b3J5IGludG8gYCVVU0VSUFJPRklMRSVcSTRfVUlfYWNjZXB0YW5jZWAKICAgKGAtYyBjb3JlLmF1dG9jcmxmPWZhbHNlYCkgYW5kIGNoZWNrb3V0IG9mIHRoZSBwaW5uZWQgY29tbWl0IGA2ZGE3YzZmZeKApmAKICAgKHRoZSBUQVNLNjUgY29ycmVjdGVkIFVJKTsgdmVyaWZpZXMgYEhFQURgIGVxdWFscyB0aGUgcGluLgoyLiBzaGEyNTYtdmVyaWZpZXMgdGhlIHR3byBtb2NrdXBzLCB0aGUgc3BlYywgdGhlIG1vY2t1cCBtYW5pZmVzdCBhbmQgdGhlIEQwMSBpbnZlbnRvcnkKICAgaW4gdGhlIGNoZWNrb3V0LgozLiBDaGVja3MgdGhlIE0yIHBhY2thZ2Ugcm9vdCBleGlzdHMsIGl0cyBgUEFDS0FHRV9NQU5JRkVTVC5zaGEyNTZgIGhhc2ggYW5kCiAgIGBSVU5fQ09NUExFVEUuanNvbmAgcnVuIGlkIG1hdGNoIHRoZSBwaW5uZWQgaWRlbnRpdHkuCjQuIFJlcXVpcmVzIHRoZSB0aHJlZSBzdGF0ZSByb290cyB0byBiZSBhYnNlbnQgKHRoZXkgYXJlIGNyZWF0ZWQgYnkgdGhlIHNlcnZlciwgYWxsCiAgICoqb3V0c2lkZSoqIHRoZSBwYWNrYWdlKTogYEc6XE15IEVuZ2luZXNcSTRfUlVOU1xpNF91aV9zZXJ2aW5nX3N0YXRlYCAoY2xhc3MtKDQpIGluZGV4KSwKICAgYOKAplxpNF91aV9zYXZlZF9zdGF0ZWAgKHNhdmVkIHF1ZXJpZXMpLCBg4oCmXGk0X3VpX2hpc3Rvcnlfc3RhdGVgIChxdWVyeSBoaXN0b3J5KS4KNS4gUmVxdWlyZXMgcG9ydCA4NjEzIGZyZWU7IHRoZW4gc3RhcnRzIHRoZSBVSSBzZXJ2ZXIgKippbiB0aGUgZm9yZWdyb3VuZCoqOgoKYGBgCnB5dGhvbiAtQiAtbSB1aS5zZXJ2ZSAtLXBhY2thZ2UgJ0c6XE15IEVuZ2luZXNcSTRfUlVOU1xpNC0yMDI2MTAwOC1NMicgLS1tMiBeCiAgICAtLXN0YXRlICdHOlxNeSBFbmdpbmVzXEk0X1JVTlNcaTRfdWlfc2VydmluZ19zdGF0ZScgXgogICAgLS1zYXZlZC1zdGF0ZSAnRzpcTXkgRW5naW5lc1xJNF9SVU5TXGk0X3VpX3NhdmVkX3N0YXRlJyBeCiAgICAtLWhpc3Rvcnktc3RhdGUgJ0c6XE15IEVuZ2luZXNcSTRfUlVOU1xpNF91aV9oaXN0b3J5X3N0YXRlJyBeCiAgICAtLXJlcG8gJVVTRVJQUk9GSUxFJVxJNF9VSV9hY2NlcHRhbmNlIC0tYmluZCAxMjcuMC4wLjEgLS1wb3J0IDg2MTMKYGBgCgogICBGaXJzdCBzdGFydCA9IGZ1bGwgcGFja2FnZSBkaWdlc3QgdmVyaWZpY2F0aW9uICh2ZXJpZnktMDEuLjA3KSArIG9uZS10aW1lIGluZGV4IGJ1aWxkIG92ZXIKICAgNSw2ODksOTQ5IHJvd3Mg4oCUIHJvdWdobHkgM+KAkzE1IG1pbnV0ZXMgb24gYSBsb2NhbCBkcml2ZS4gTm9ybWFsLCBub3QgYSBzdGFsbC4KNi4gV2hlbiBpdCBzdWNjZWVkcyB0aGUgdGVybWluYWwgcHJpbnRzIG9uZSBKU09OIGxpbmU6CgpgYGAKeyJiaW5kIjogIjEyNy4wLjAuMSIsICJtMiI6IHRydWUsICJwYWNrYWdlX3J1bl9pZCI6ICJpNC0yMDI2MTAwOC1NMiIsICJwb3J0IjogODYxMywgInJlc3VsdCI6ICJyZWFkeSIsICJzZXJ2aWNlIjogImk0LXVpLzEuMCIsICJ1cmwiOiAiaHR0cDovLzEyNy4wLjAuMTo4NjEzLyJ9CmBgYAoKICAgKipLZWVwIHRoZSB0ZXJtaW5hbCBvcGVuKiog4oCUIHRoZSBzZXJ2ZXIgcnVucyB1bnRpbCB5b3UgcHJlc3MgQ3RybCtDIGluIGl0LgoKIyMgUGhhc2UgQyDigJQgY2FwdHVyZSAoeW91ciBzdGVwLCBpbiBhIGJyb3dzZXIgb24gdGhlIHNhbWUgbWFjaGluZSkKCjEuIE9wZW4gYGh0dHA6Ly8xMjcuMC4wLjE6ODYxMy9gIGluIENocm9tZS9FZGdlLgoyLiBTZXQgdGhlIHJlbmRlcmluZyB2aWV3cG9ydCB0byAqKmV4YWN0bHkgMTUzNsOXMTAyNCoqICh0aGUgbW9ja3VwcycgZGlzcGxheSBjYW52YXMpOgogICBEZXZUb29scyAoRjEyKSDihpIgZGV2aWNlIHRvb2xiYXIgKEN0cmwrU2hpZnQrTSkg4oaSIGFkZCBhIGN1c3RvbSBkZXZpY2UgKioxNTM2IMOXIDEwMjQsCiAgIGRldmljZSBzY2FsZSBmYWN0b3IgMSoqLiBUaGUgYXBwbGljYXRpb24gZmlsbHMgdGhlIHZpZXdwb3J0ICgxMDB2aCksIHNvIHRoZSBhcHAgY2FudmFzCiAgIGlzIGV4YWN0bHkgMTUzNsOXMTAyNC4KMy4gKipEYXNoYm9hcmQgY2FwdHVyZToqKiBsZWF2ZSB0aGUgZGVmYXVsdCBEYXNoYm9hcmQgdmlldyAobm8gZmlsdGVycywgbm8gaW50ZXJhY3Rpb24KICAgYmV5b25kIHNjcm9sbGluZykuIERldlRvb2xzIGNvbW1hbmQgbWVudSAoQ3RybCtTaGlmdCtQKSDihpIgKipDYXB0dXJlIGZ1bGwgc2l6ZQogICBzY3JlZW5zaG90KiouIFNhdmUgYXMgYEk0X1VJX0NBUFRVUkVfZGFzaGJvYXJkXzE1MzZ4MTAyNC5wbmdgLgo0LiAqKkRhdGEgRXhwbG9yZXIgY2FwdHVyZToqKiBjbGljayB0aGUgKipEYXRhIEV4cGxvcmVyKiogdGFiOyBsZWF2ZSBhbGwgZmlsdGVycyBlbXB0eTsKICAgc2FtZSBjYXB0dXJlIGNvbW1hbmQuIFNhdmUgYXMgYEk0X1VJX0NBUFRVUkVfZXhwbG9yZXJfMTUzNngxMDI0LnBuZ2AuCjUuIFZlcmlmeSBlYWNoIFBORyBpcyBleGFjdGx5ICoqMTUzNsOXMTAyNCoqIGJlZm9yZSByZXR1cm5pbmc6CiAgIGBBZGQtVHlwZSAtQXNzZW1ibHlOYW1lIFN5c3RlbS5EcmF3aW5nOyBbU3lzdGVtLkRyYXdpbmcuSW1hZ2VdOjpGcm9tRmlsZSgnPHBuZz4nKS5XaWR0aCwgW1N5c3RlbS5EcmF3aW5nLkltYWdlXTo6RnJvbUZpbGUoJzxwbmc+JykuSGVpZ2h0YAo2LiBDYXB0dXJlIHRoZSBzZXJ2ZXIncyAqKnJlYWR5IEpTT04gbGluZSoqIChmcm9tIHRoZSB0ZXJtaW5hbCkgYW5kIHRoZSAqKmAvYXBpL3N0YXR1c2AqKgogICBKU09OOiBvcGVuIGBodHRwOi8vMTI3LjAuMC4xOjg2MTMvYXBpL3N0YXR1c2AgaW4gdGhlIGJyb3dzZXIgYW5kIGNvcHkgdGhlIEpTT04KICAgKG9yIGBHZXQtQ29udGVudGAgdGhlIHJlbmRlcmVkIHRleHQpLiBgcGFja2FnZV9ydW5faWRgIG11c3QgcmVhZCBgaTQtMjAyNjEwMDgtTTJgLgo3LiBTdG9wIHRoZSBzZXJ2ZXIgd2l0aCBDdHJsK0MgaW4gdGhlIHRlcm1pbmFsICh0aGUgc2NyaXB0IHRoZW4gcnVucyB0aGUgb3B0aW9uYWwKICAgcG9zdC1jYXB0dXJlIGBzZXJ2aW5nIHZlcmlmeWAgaW1tdXRhYmlsaXR5IHByb29mIOKAlCBleHBlY3RlZCBleGl0IDApLgoKIyMgUGhhc2UgRCDigJQgY29tcGFyaXNvbiAoeW91ciBzdGVwOyByZXBvcnQsIGRvIG5vdCBmaXgpCgpPcGVuIGVhY2ggY2FwdHVyZSBzaWRlIGJ5IHNpZGUgd2l0aCBpdHMgbW9ja3VwIGF0IGVxdWl2YWxlbnQgc2NhbGUgKGJvdGggY2FudmFzZXMgYXJlCjE1MzbDlzEwMjQsIHNvIDE6MSkuIFJlY29yZCAqKmV2ZXJ5KiogdmlzdWFsIGRpZmZlcmVuY2UsIGNsYXNzaWZpZWQ6CgoxLiAqKkV4cGVjdGVkIGF1dGhvcml0eS1kcml2ZW4gZGV2aWF0aW9ucyoqIChwZXIgdGhlIFRBU0s2MiBpbXBsZW1lbnRhdGlvbiByZWNvcmQgwqc1IOKAlAogICB0aGVzZSBhcmUgY29ycmVjdCBhcyBidWlsdDsgbGlzdCBlYWNoIG9uZSB5b3UgY2FuIHNlZSk6CiAgIDEuICJSdW4gTmV3IFByb2Nlc3NpbmciIGRpc2FibGVkOyAyLiAiVmVyaWZ5IEV4aXN0aW5nIFJ1biIgZGlzYWJsZWQ7IDMuIHNpeAogICAgIG5vbi1maXJzdC1yZWxlYXNlIG5hdiBkZXN0aW5hdGlvbnMgdW5hdmFpbGFibGU7IDQuIEFkdmFuY2VkIFF1ZXJ5IHVuYXZhaWxhYmxlOwogICA1LiBUcmFkaW5nIFN0YXR1cyBmaWx0ZXIgb21pdHRlZDsgNi4gIlJlbGlhYmxlIE9ubHkiIHByZXNldCB1bmF2YWlsYWJsZTsgNy4gRW5naW5lCiAgICAgbG9ncyB1bmF2YWlsYWJsZTsgOC4gIlZpZXcgUmF3IFJlY29yZCIgZGlzYWJsZWQgKEQyMyDCpzE5KTsgOS4gIlZpZXcgQXJjaGl2ZSIKICAgZGlzYWJsZWQgKEQxNSDCpzE0KTsgMTAuIEV4cG9ydCBhY3Rpb25zIG9taXR0ZWQ7IDExLiBmb3VyLWJ1Y2tldCBxdWFsaXR5IGRvbnV0CiAgIHVuYXZhaWxhYmxlIChzZXJ2ZWQgY2Vuc3VzIHNob3duIGluc3RlYWQpOyAxMi4gZGF0YXNldCBzZWxlY3RvciAvIGxhc3QtdXBkYXRlZAogICB1bmF2YWlsYWJsZSAoc2luZ2xlIGRhdGFzZXQsIG5vIGNvbnRyYWN0IHRpbWVzdGFtcCk7IDEzLiBJZGVudGl0eSBSZWNvcmRzIEtQSQogICB1bmF2YWlsYWJsZS4gTW9ja3VwIHNhdmVkLXF1ZXJ5IHNob3J0Y3V0IG5hbWVzIGFyZSBuZXZlciBzZWVkZWQ7IG5vIGZha2UKICAgdGltZXN0YW1wcyBvciBtZXRyaWNzOyB1bmF2YWlsYWJsZSBpcyBuZXZlciByZW5kZXJlZCBhcyB6ZXJvL3N1Y2Nlc3MvZW1wdHkuCjIuICoqRGF0YS1kcml2ZW4gZGlmZmVyZW5jZXMqKiAoZXhwZWN0ZWQg4oCUIHRoZSBtb2NrdXAgc2hvd3MgaWxsdXN0cmF0aXZlIHZhbHVlcywgdGhlIGFwcAogICBzaG93cyB0aGUgcmVhbCBjb3JwdXMpOiBLUEkgbnVtYmVycywgbGF0ZXN0IGRhdGEgZGF0ZSAoY29ycHVzIGVuZHMgMjAyNi0wOS0xOCksCiAgIHNhdmVkLXF1ZXJ5IG5hbWVzIChub25lIHVudGlsIHlvdSBjcmVhdGUgb25lKSwgcm93IGNvdW50cywgY2Vuc3VzIHBlcmNlbnRhZ2VzLAogICBkYXRlLXJhbmdlIGxhYmVscy4KMy4gKipVbmV4cGVjdGVkIGRldmlhdGlvbnMqKiAobGF5b3V0IHN0cnVjdHVyZSwgcmVnaW9ucywgY29sb3IsIHR5cG9ncmFwaHksIHNwYWNpbmcsCiAgIGludGVyYWN0aW9uIHN0YXRlcyB0aGF0IGRpZmZlciBmcm9tIHNwZWMvbW9ja3MgYmV5b25kIDHigJMyKTogcmVwb3J0IGVhY2ggd2l0aCBhIHNob3J0CiAgIGRlc2NyaXB0aW9uLiAqKkRvIG5vdCBtb2RpZnkgYW55IHNvdXJjZSB0byAiZml4IiB0aGVtIGluIHRoaXMgdGFzayoqIOKAlCB0aGV5IGFyZSB0aGUKICAgYWNjZXB0YW5jZSBmaW5kaW5ncy4KCiMjIFJldHVybiBidW5kbGUgKHNlbmQgYmFjayB0byBBcmVuYSkKCi0gYEk0X1VJX0NBUFRVUkVfZGFzaGJvYXJkXzE1MzZ4MTAyNC5wbmdgCi0gYEk0X1VJX0NBUFRVUkVfZXhwbG9yZXJfMTUzNngxMDI0LnBuZ2AKLSB0aGUgc2VydmVyICoqcmVhZHkgSlNPTiBsaW5lKiogKyAqKmAvYXBpL3N0YXR1c2AgSlNPTioqCi0gdGhlIGZ1bGwgUGhhc2UgQStCK0QgY29uc29sZSBvdXRwdXQKLSBhIHNob3J0IHdyaXR0ZW4gY29tcGFyaXNvbiAoYW55IGZvcm1hdCkgd2l0aCB0aGUgdGhyZWUgY2xhc3NpZmljYXRpb25zIGFib3ZlCgojIyBTdG9wIHJ1bGVzCgotIEFueSBgQ0hFQ0sg4oCmOiBGQUlMYCBvciBub24temVybyBleGl0OiBzdG9wLCBwcmVzZXJ2ZSB0aGUgZXhhY3Qgb3V0cHV0LCBzZW5kIGl0OyBkbyBub3QKICBtb2RpZnkgc291cmNlIG9yIHBhY2thZ2UgZmlsZXM7IGRvIG5vdCByZXJ1biBwYXN0IGEgZmFpbHVyZSB3aXRob3V0IHRoZSBvdXRwdXQgcmV2aWV3ZWQuCi0gTWlzc2luZyBwYWNrYWdlIHJvb3Q6IHJ1biBgRDI2X1ZFUklGWV9NMl9QQUNLQUdFLnBzMWAgKEQyNiDCpzcpIGZpcnN0OyBpZiBpdCBkb2VzIG5vdAogIHJldHVybiBgVkVSRElDVDogUEFTU2AsIHN0b3AgdGhlIHdob2xlIGhhbmRvZmYuCi0gVGhpcyB0YXNrIG1ha2VzICoqbm8gcGFyaXR5IGNsYWltKio6IHZpc3VhbCBhY2NlcHRhbmNlIGlzIGlzc3VlZCBvbmx5IGJ5IEFyZW5hIGFmdGVyIGl0CiAgaW5zcGVjdHMgdGhlIHJldHVybmVkIGNhcHR1cmVzLgo='

# --- G1: stage the incoming bytes (existing files untouched until they verify) ---
$Ps1In = Join-Path $Dir ($Ps1Name + '.incoming')
$MdIn  = Join-Path $Dir ($MdName + '.incoming')
if (-not $Failed) {
    [System.IO.File]::WriteAllBytes($Ps1In, [System.Convert]::FromBase64String($Ps1B64))
    [System.IO.File]::WriteAllBytes($MdIn, [System.Convert]::FromBase64String($MdB64))
    Write-Output 'GATE G1: PASS (incoming bytes staged as *.incoming; existing files untouched)'
}

# --- G2: byte-exact verification of the incoming files (size + sha256) ---
if (-not $Failed) {
    $hPs1 = (Get-FileHash -LiteralPath $Ps1In -Algorithm SHA256).Hash.ToLower()
    $sPs1 = (Get-Item -LiteralPath $Ps1In).Length
    $hMd  = (Get-FileHash -LiteralPath $MdIn -Algorithm SHA256).Hash.ToLower()
    $sMd  = (Get-Item -LiteralPath $MdIn).Length
    Write-Output ('incoming ps1: size ' + $sPs1 + ' sha256 ' + $hPs1)
    Write-Output ('incoming md : size ' + $sMd + ' sha256 ' + $hMd)
    if ($hPs1 -ceq $Ps1Exp -and $sPs1 -eq $Ps1Size) { Write-Output 'GATE G2 ps1: PASS (byte-exact vs authoritative c5e653bf...)' }
    if (-not ($hPs1 -ceq $Ps1Exp -and $sPs1 -eq $Ps1Size)) { $Failed = $true; Write-Output ('GATE G2 ps1: FAIL - expected size ' + $Ps1Size + ' sha256 ' + $Ps1Exp) }
    if ($hMd -ceq $MdExp -and $sMd -eq $MdSize) { Write-Output 'GATE G2 md: PASS (byte-exact vs authoritative 7dac5182...)' }
    if (-not ($hMd -ceq $MdExp -and $sMd -eq $MdSize)) { $Failed = $true; Write-Output ('GATE G2 md: FAIL - expected size ' + $MdSize + ' sha256 ' + $MdExp) }
}

# --- G3: replace the existing files ONLY after both incoming files verify, then re-hash ---
if (-not $Failed) {
    Move-Item -LiteralPath $Ps1In -Destination (Join-Path $Dir $Ps1Name) -Force
    Move-Item -LiteralPath $MdIn  -Destination (Join-Path $Dir $MdName) -Force
    $hPs1F = (Get-FileHash -LiteralPath (Join-Path $Dir $Ps1Name) -Algorithm SHA256).Hash.ToLower()
    $hMdF  = (Get-FileHash -LiteralPath (Join-Path $Dir $MdName) -Algorithm SHA256).Hash.ToLower()
    if ($hPs1F -ceq $Ps1Exp -and $hMdF -ceq $MdExp) { Write-Output 'GATE G3: PASS (authoritative artifacts in place; post-move re-hash verified)' }
    if (-not ($hPs1F -ceq $Ps1Exp -and $hMdF -ceq $MdExp)) { $Failed = $true; Write-Output 'GATE G3: FAIL (post-move re-hash mismatch - inspect the directory and stop)' }
}

if ($Failed) {
    Write-Output 'RESULT: TRANSFER FAILED (fail-closed). Any pre-existing files remain in place; the staged *.incoming files remain for inspection. Preserve this full output and send it to Arena. Do NOT run the acceptance script.'
}
if (-not $Failed) {
    Write-Output 'RESULT: TRANSFER VERIFIED. Both authoritative TASK65 handoff artifacts are in place, byte-exact. Preserve this full output as transfer evidence. Only now run the next Windows step from the TASK66 report (the acceptance script).'
}
```

### Next Windows step 2 — acceptance run (ONLY after step 1 printed `RESULT: TRANSFER VERIFIED`)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'G:\My Engines\10yhistoriclengine\_transfer_delivery\m2\ui\I4_UI_VISUAL_ACCEPTANCE_WINDOWS.ps1'
```

Step 2 then proceeds exactly per the runbook (Phase A+B automated gates →
foreground server → Phase C 1536×1024 captures → Phase D comparison →
return bundle). Nothing in step 2 may run until step 1's verification
succeeded; on any FAIL, preserve the output and send it — do not continue.

## 7. Non-drift and standing constraints honored

- No Windows UI acceptance performed; no screenshots; no acceptance script
  executed; no UI server started (from either domain).
- No M2 package modification, rebuild, regeneration, or rerun; the package
  identity pins are unchanged.
- No implementation code changed; the only file touched is the untracked
  runbook (one-line pin reference); no commit exists for it by the
  never-commit rule — its durable publication is this record (hash above).
- No `main` promotion; session branch only; evidence and mockup branches
  unchanged (re-verified via `ls-remote` before and after any action).
- No visual-acceptance claim; acceptance is issued only by Arena after it
  inspects fresh captures taken from the re-pinned, re-transferred
  artifacts.
- PowerShell contract honored in the block above (no exit/return/else/
  elseif/finally; terminal stays open; fail-closed at every gate).

## 8. Stop conditions evaluated

All stop conditions were checked and none triggered: repository + TASK65
publication verified; both artifacts present and now internally consistent;
the script pins the required commit; the runbook accurately describes the
script; all safety/integrity controls verified effective; the transfer
mechanism and destination are established; nothing proposed exceeds
existing authority or risks M2, the existing checkout, unrelated branches,
or preserved evidence.
