# B1 state safety execution record

## Baseline

At start, `arena/215cb93c-nse-historical-data-engine` was clean at
`69977017ffca944921f231d7904347bc582b6392`; remote `main` was at that
commit and `arena/9021d1a1-nse-historical-data-engine` was at
`5d5740d09c37b8e85b72f00f3921325a6328d3ed`. The remote session ref did not
exist. The feature tip was 23 commits ahead of main. Fetching the feature ref
and fast-forwarding the session branch preserved all 23 commits; main was not
changed.

## Changes and operating boundaries

Shared resolved-path checks reject overlapping known roots, including symlink
aliases. UI validates all four roots before index initialization; baseline-aware
index, rebuild, saved execution and history recording validate their known roots.
Root-only writers additionally reject paths under directories bearing package
markers. The index and sidecar are individually replaced atomically; a crash
between replacements produces a mismatched pair that is rejected and rebuilt
from the baseline on UI startup. Recovery preserves unknown files. Existing
index 1.2 and saved/history 1.0 formats are unchanged. User-owned stores are not
rebuilt by index recovery.

D01 inventory defaults to the repository containing the installed source rather
than CWD. UI `--repo` supplies its inventory context; CLI inventory accepts
`--repo`, and saved run/history record accept `--repository-root`. Q10 retains
explicit per-query `repo` precedence and absence when no context is provided.

## Verification and limitations

- Linux sandbox: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest
  discover -s tests -t .` — 908 tests, OK, 14 real-M2 gated skips. Existing
  tests emitted ResourceWarnings.
- `tests.test_b1_state_safety` covers synthetic package snapshots, equal and
  nested roots, symlink alias and destination-file symlink, UI/CLI/direct write
  rejection, external CWD, inventory root propagation, valid index reuse,
  interrupted publication, stale and non-UTF8 index recovery, and retention of
  saved/history 1.0 data. Q9 M2-context propagation is mocked, not a real-M2
  integration execution.
- No command accessed the Windows M2 package, and tests used temporary synthetic
  packages and disposable state. Its unchanged state is therefore not independently
  re-verified here; Windows package verification remains outstanding.
- Windows drive, case, junction and symlink behavior must be exercised on Windows;
  the implementation uses that platform's `realpath`, `normcase` and `commonpath`,
  but this Linux run does not establish Windows results.
- Standalone root-only store/index APIs do not receive all other configured roots:
  marker checks protect an identifiable package ancestor, but cannot establish
  pairwise separation from an unrelated state root that was never supplied. The
  UI and baseline-aware operations do supply the relevant roots. Nor are these
  path checks a defense against another process deliberately swapping directories
  between validation and writes. Treat full root-only/hostile-race isolation as
  remaining work rather than a verified guarantee.
- The two-file index publication is not a transactional pair or a power-loss
  durability guarantee. Sidecar validation detects an interrupted mismatch; it
  does not prevent all possible filesystem or hardware failures.
