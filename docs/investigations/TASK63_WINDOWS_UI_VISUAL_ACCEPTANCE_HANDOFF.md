# TASK63 — WINDOWS UI VISUAL-ACCEPTANCE HANDOFF (EVIDENCE RECORD)

## 1. Task identity and purpose

**TASK63** prepares the Windows visual-acceptance handoff for the completed first-release
Dashboard + Data Explorer (TASK62, published `1f86d88…`). Mode: **handoff preparation and
verification only**. It (a) verifies the published TASK62 commit and its implementation
record, (b) inspects the existing Windows transfer package and its current pin, (c)
identifies the exact handoff artifact whose pin is stale, (d) establishes the exact
Windows repository/package/state paths from existing evidence (no guessing), (e) produces
the smallest safe Windows execution procedure, and (f) records the acceptance checklist
and next action. **No implementation change, no M2 qualification, no production activity,
no main promotion, no parity claim** (parity is issued only after Arena inspects the
returned Windows captures).

## 2. Verified identities (re-verified live this task, remote + local)

| Item | Value |
|---|---|
| Session branch (local HEAD = remote) | `1f86d88749357cad15f22c94c648d3e6d0f7a294` on `arena/9021d1a1-nse-historical-data-engine` |
| TASK62 commit parent | `c60b15d…` (TASK60); 16 files added, +5,371/−0, no modifications |
| Design references (re-hashed live in the worktree, all match the TASK62 record) | dashboard PNG `fa11f0e867d0f8aa1df41b3ab88c51d27ce2ccd50e790e5181ecf45b2aa1af85` (1,773,767 B); explorer PNG `53f20b6484f02ac28f4fdf5f80125b38e138e256ebf8ba5d26cfb3ee9b46bd19` (1,842,012 B); spec `aca5eca905b151e0f98f045f5b34bbb232e5af27e828acf725cad92ad6d62165`; manifest `b83ff8a141f65fabd28c7ab10eebf390809a3a28906e7017c4b206878d6b9f27` |
| Blob IDs at the pin (remote-verified in TASK62, re-listed here) | spec `6caae93b…`, dashboard `58394744…`, explorer `c66ec98b…`, manifest `81daa197…` — identical to the dedicated reference branches |
| `origin/main` (untouched) | `69977017ffca944921f231d7904347bc582b6392` (D24) |
| D01 inventory at the pin | `evidence/inventory/file_inventory.json`, blob `033a583b…`, 4,731,552 B, sha256 `336b9531cd34f48e9a2e7e7593cc4e9c2736b3864d8213bc65d6ab8b488729d2` (required by the `--m2` join) |
| `src/ui/` at the pin | present (`serve.py` blob `6476f86f…`, `api.py` blob `4eb24c6f…` + static + 4 test modules, 83 tests) |

## 3. Existing Windows transfer package inspected (untracked `_transfer_delivery/`)

Layout (all untracked staging; **nothing here was modified by this task**):

- Root: D08 transfer (commit `a1f0b58…`, 2026-10-06) + `SHA256SUMS.txt` +
  `I4_RUNNER_WINDOWS_*` + `I4_WINDOWS_APPLICATION_PROCEDURE.md`.
- `m2/` — G-I4-M2 execution package **v1** (tar.gz `45643f28…`, 141,788 B, 29 payload
  files, transfer revision `8ade8372…`; superseded per its `SUPERSEDED_BY_M2_FIX.md`).
- `m2_fix/` — corrected self-test generations; **latest = `m2_fix/I4_M2_WINDOWS_v3/`**
  (v2/v3 tar.gz + sha256; `SUPERSEDED_BY_V3.md`).
- `exposure/` — download channel (b64 packages, `served/` mirror, how-to docs).
- `package_tree/`, `reports/G_I4_M2_HANDOFF_REPORT.md` — D08 tree + M2 gate report
  (frozen `G-I4-M2 BLOCKED`-until-Windows classification record; the gate was later
  closed by the Windows execution whose evidence is D11 in-repo).
- These artifacts carry the **M2 execution gate** pins: Windows base `main`
  `6a60583f62905c1fbda9cc7529019e2a9ed0b097` ("must remain" for the runner gate) and
  transfer revision `8ade8372…`. That gate is complete; those pins stay frozen as
  historical evidence. They are **not** the UI handoff pin.

## 4. The exact handoff artifact with the stale pin (identified)

The operating handoff for Windows serving work is
`docs/investigations/D26_REAL_M2_WINDOWS_EXECUTION_READINESS.md` §8 (Phase-3 script),
whose checkout pin is:

```powershell
$PinnedHead = '69977017ffca944921f231d7904347bc582b6392'   # D24
```

That pin is **stale for UI work**: `src/ui/` (the Dashboard + Data Explorer host) exists
only from `1f86d88…` onward; a checkout at `6997701…` has no UI at all. The D26
document is a **frozen evidence record** (its §10 states its only mutation was itself),
so it is not edited. The authorized change is therefore **additive only**: this record
plus the new Windows handoff files under `_transfer_delivery/m2/ui/` (untracked staging,
the established download channel), which carry the re-pinned identity:

> **UI handoff pin (supersedes D26 §8 `$PinnedHead` for UI visual acceptance):
> `1f86d88749357cad15f22c94c648d3e6d0f7a294`** — the session tip, remotely verified in
> TASK62 (FF push, ref/parent/paths/design-blob verification) and re-verified at TASK63
> start.

Required verification of the re-pin (executed by the handoff script itself, fail-closed):
`git fetch` of the session branch + `git checkout <pin>` + `HEAD` equality check, plus
sha256 verification of the five reference/inventory files at the pin.

## 5. Windows facts established from evidence (no guessing)

| Item | Value | Source |
|---|---|---|
| M2 package root | `G:\My Engines\I4_RUNS\i4-20261008-M2` | D26 §4 (documented run-root convention + pinned `RUN_RECORD` run id); D11 in-repo identity |
| Package identity | run id `i4-20261008-M2`; manifest file sha256 `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`; 4,948 files / 21,119,807,344 B; 5,689,949 rows; 2,462 members; 12 partitions | D26 §3/§7; `serving.baseline.DEFAULT_M2_SPEC` (identical constants in code at the pin) |
| Never-touch sibling | `G:\My Engines\I4_RUNS\i4-20261007` | D26 §4; M2 runbook |
| Repository checkout pattern | scratch clone in `%USERPROFILE%\<name>` at the exact pin, `-c core.autocrlf=false`, never touching the governed "My Engines" repo or D26's scratch | D26 §6/§8 pattern, extended with a new scratch name `%USERPROFILE%\I4_UI_acceptance` |
| Derived state (index) | `G:\My Engines\I4_RUNS\i4_ui_serving_state` — **outside** the package (serving contract; D26 §6) | new root, sibling convention `G:\My Engines\I4_RUNS\*` |
| Saved-query store | `G:\My Engines\I4_RUNS\i4_ui_saved_state` (class-(4) user state, distinct from index) | D23 §17(b)/D39; new root |
| Query-history store | `G:\My Engines\I4_RUNS\i4_ui_history_state` (class-(4) user state) | D39; new root |
| Runtime | Python 3 stdlib only; `python -B`; `PYTHONPATH=src` from the checkout root | D26 §6; `src/ui/serve.py` docstring |
| Bind/port | loopback `127.0.0.1:8613` (default; personal single-user hosting per D23 §13/§14) | `src/ui/serve.py` |

## 6. The smallest safe Windows execution procedure

Delivered as two untracked files in `_transfer_delivery/m2/ui/` (download channel):

1. **`I4_UI_VISUAL_ACCEPTANCE_WINDOWS.md`** — runbook: pinned identity table, Phase A–D,
   stop rules, return bundle.
2. **`I4_UI_VISUAL_ACCEPTANCE_WINDOWS.ps1`** — one fail-closed script (PowerShell
   contract honored: no `exit`/`return`/`else`/`elseif`/`finally`; terminal stays open):
   - Phase A: fresh scratch clone + checkout of `1f86d88…` with `HEAD` equality gate;
     sha256 gates on both mockups, spec, mockup manifest, D01 inventory; package-root
     + manifest-hash + run-id gates; state-roots-absent gate; port-8613-free gate.
   - Phase B: foreground
     `python -B -m ui.serve --package 'G:\My Engines\I4_RUNS\i4-20261008-M2' --m2
     --state 'G:\My Engines\I4_RUNS\i4_ui_serving_state' --saved-state
     'G:\My Engines\I4_RUNS\i4_ui_saved_state' --history-state
     'G:\My Engines\I4_RUNS\i4_ui_history_state' --repo %USERPROFILE%\I4_UI_acceptance
     --bind 127.0.0.1 --port 8613`
     — first start performs the full 4,948-file digest verification (existing serving
     boundary behavior, NOT re-qualification) + one-time 5,689,949-row index build
     (≈3–15 min); prints the `{"result": "ready", …, "package_run_id": "i4-20261008-M2"}`
     line; terminal stays open while the server runs.
   - Phase C (user, browser at 1536×1024 DevTools device): Dashboard capture →
     `I4_UI_CAPTURE_dashboard_1536x1024.png`; Data Explorer (no filters) capture →
     `I4_UI_CAPTURE_explorer_1536x1024.png`; verify both PNGs are exactly 1536×1024;
     collect the ready line + `/api/status` JSON.
   - Phase D: optional post-capture `python -B -m serving verify --package <root> --m2`
     immutability proof (expected exit 0).

## 7. Acceptance checklist

**Pre (script-enforced, fail-closed):**
- [ ] scratch checkout `HEAD` == `1f86d88749357cad15f22c94c648d3e6d0f7a294`
- [ ] 5/5 reference/inventory sha256 PASS (2 mockups, spec, manifest, D01 inventory)
- [ ] package root present; `PACKAGE_MANIFEST.sha256` == `e7c7e4c8…`; `RUN_COMPLETE.run_id` == `i4-20261008-M2`
- [ ] 3 state roots absent (created outside the package by the server)
- [ ] port 8613 free; server prints the ready line with `package_run_id: i4-20261008-M2`, `m2: true`
- [ ] `/api/status` returns `{"result": "pass", "service": …, "package_run_id": "i4-20261008-M2", "m2": true, "repo_root": …, "query_modes": […]}`
- [ ] the Dashboard KPI panel shows the real corpus counts (rows 5,689,949 per the pinned package identity) — visual check

**Capture (user):**
- [ ] viewport exactly 1536×1024 (device mode, scale 1)
- [ ] Dashboard + Data Explorer (unfiltered) full-size screenshots, each verified 1536×1024
- [ ] ready line + `/api/status` JSON captured
- [ ] post-capture `serving verify` exit 0 (package byte-identical to its manifest)

**Comparison (user → Arena):**
- [ ] every visual difference recorded and classified: (1) expected authority-driven
      deviation (the 13 documented omissions), (2) data-driven (real corpus values vs
      mockup illustrative values), (3) unexpected
- [ ] no source modification attempted to "fix" a difference in this task

**Arena-side (after return):**
- [ ] captures inspected; parity NOT claimed until then; comparison transcribed into a
      follow-up record; any unexpected deviation routed as a finding, not a silent fix

## 8. Explicit scope and non-drift statement

- **No implementation change**: the only tracked mutation of this task is this record;
  `src/`, `tests/` untouched; full suite state unchanged (888 OK, 14 gated skips).
- **No M2 qualification / no production / no runner execution** on Windows: the script
  never runs `tools/i4_runner`; the digest verification at server start is the existing
  serving-boundary mechanism, not a re-qualification act.
- **No main promotion** (`origin/main` remains `6997701…` D24); session scope only.
- **No unrelated artifact touched**: `_transfer_delivery/` content unchanged except the
  new `m2/ui/` subfolder (untracked, consistent with that folder's never-commit rule);
  D26, M2 gate artifacts, failed-run evidence, D08/D10 staging all byte-identical.
- **No parity claim** before the Windows captures are inspected by Arena.

## 9. Next action

1. User downloads `_transfer_delivery/m2/ui/` (runbook + script) to the Windows machine.
2. User runs `I4_UI_VISUAL_ACCEPTANCE_WINDOWS.ps1`, performs Phase C capture, returns the
   bundle (2 PNGs + ready line + `/api/status` JSON + console output + written
   comparison).
3. Arena inspects the captures, issues the visual-acceptance verdict (parity or
   findings) and transcribes the results into the repository as a follow-up record.
