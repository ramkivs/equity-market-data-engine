# B5 Windows / Python 3.14.3 test-failure investigation and correction (evidence record)

**Date:** 2026-11-04 · **Baseline:** `95c69f3000be636f70e34e031522c2b056662c98` (`origin/main`)
· **Branch:** `arena/732ff99d-nse-historical-data-engine`
· **Scope:** the recorded Windows Python 3.14.3 run of 2026-11-03 in the user's
`H:\EquiCore\equity-market-data-engine` checkout: 124 failed, 42 passed, 2 skipped,
106 errors, 17 subtests passed, interrupted after 147.34 s.

This record is an **Arena/Linux source investigation plus targeted correction**.
It does not claim to have executed Windows or Python 3.14.3, does not claim B6
Windows validation, does not declare B5 closed, does not promote B7, and does not
touch qualified historical data. Section 7 gives the narrow Windows diagnostic
that remains necessary.

## 1. Environment support evidence (no assumption either way)

| Source | Recorded fact |
|---|---|
| `README.md` §Environment Boundary | Windows = "raw-data custody and full-dataset execution environment"; GitHub = authoritative durable record; Arena = development/testing. Windows is a historically used/expected environment, not an unqualified test platform. |
| `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md` §5 | "Language/runtime: **Python 3, standard library only**"; no minor version pinned, no dependency manifest. |
| `docs/investigations/D26_REAL_M2_WINDOWS_EXECUTION_READINESS.md` §5/§6 | "Python 3, standard library only — no pip installs"; `python -B`; the Windows machine already ran the governed runner on Python 3; "no implementation change needed to run existing tests on Windows" — a D24 readiness statement, **not** B5/B6 validation. |
| `docs/implementation/B1_FINAL_CLOSURE.md`, `B1_ROOT_CONFIGURATION_FOLLOWUP.md`, `B5_CATALOG_PUBLICATION.md` §"Disposable validation", `PUBLICATION_AUDIT_2026-11-03.md` | Linux validation only; "Windows validation remains pending"; the audit explicitly does "not ... perform B6 Windows validation or promote B7". |
| Repository inventory | No `pyproject.toml`, `setup.py`, requirements file, pinned Python version, Python-version CI matrix, or `.github/workflows` exists. |

**Conclusion:** there is no repository-declared support matrix and no pinned Python
version. Windows is documented for governed execution, but **Windows + Python
3.14.3 is not an officially validated/supported B5 test combination**. Conversely,
Python 3.14 is **not** shown to be unsupported: the `Errno 9` defect below is
generic CPython-on-Windows behavior documented for all versions with `os.fsync`,
not a 3.14 regression. Python 3.14 `os.fsync` documentation states that on Windows
it calls the MS CRT `_commit()`; Microsoft documents `_commit` returning `EBADF`
for an invalid descriptor. The repository declares only "Python 3, stdlib only".

## 2. Category 1 — `OSError: [Errno 9] Bad file descriptor` (application defect)

**Originating fd.** At baseline, `src/serving/continuity_catalog.py:406-407`
(`bootstrap`) and `src/serving/ticker_proofs.py:79-80` (`build`) each wrote a
temporary SQLite database, closed the writer, then reopened that temporary file
**read-only** purely to flush it:

```python
with open(temporary, 'rb') as handle:
    os.fsync(handle.fileno())
```

`os.fsync` on Windows is `FlushFileBuffers` via CRT `_commit()` and requires a
writable descriptor; a read-only (`O_RDONLY`) descriptor yields
`OSError: [Errno 9] Bad file descriptor`. POSIX permits the same call, so the
Linux suite cannot detect it. Linux emulation of the Windows rule (reject
`fsync` on a read-only regular-file descriptor) reproduced the exact failure:
`tests/test_b5_catalog_bootstrap.py:29` → `continuity_catalog.py:407`,
`OSError: [Errno 9] Bad file descriptor`.

**Correction.** `src/serving/atomic.py` gains `sync_file(path)`, which opens the
already-written file with `"r+b"` and fsyncs that writable descriptor. Both
call sites now use it. No assertion, durability step, atomic `os.link`
publication, directory fsync (POSIX-only branch), or integrity check was removed
or weakened; the flush is preserved with a descriptor that Windows accepts.
This is an OS-specific behavior exposing a real ownership/access-mode defect in
application code, not an unsupported-runtime failure.

## 3. Category 2 — `PermissionError: [WinError 32]` at temp-dir cleanup (harness + one production defect)

**Ownership defect.** `sqlite3.Connection` used as a context manager performs
commit/rollback only; it **does not close** the connection. Handles are released
when CPython happens to collect the object, which is not ordered relative to
`tempfile.TemporaryDirectory.cleanup()`. POSIX `unlink` succeeds while a handle
is open; Windows rejects deletion of an open SQLite file with `WinError 32`.

**Measured on Linux before correction.** An fd-inspection harness hooking
`TemporaryDirectory.cleanup` found open files inside the temp root in
**114 of 152** cleanups across the B5 modules (9 of 12 for
`tests.test_b5_derived_reference_trees`), predominantly
`registry/source_registry.sqlite3` and `state/ticker_lookup_proofs.sqlite3`.
A descriptor-origin tracker attributed them to test
`with sqlite3.connect(...)` sites (e.g. `test_b5_derived_reference_trees.py:182,194`;
`test_b5_targeted_tickers.py:64,112,150,157`), i.e. **in-process** handles in the
test process, not a subprocess. `gc.collect()` before cleanup reduced but did not
eliminate them (3 of 12), so GC is not a deterministic fix.

**Subprocess / inherited-handle / cleanup-order examination.** All B1/B4/B5
subprocess tests start `Popen` with `stdout=PIPE, stderr=PIPE` and reap with
`proc.terminate(); proc.communicate(timeout=...)`; `close_fds` is `True` by
default on Windows, so SQLite descriptors are not inherited by children. The
fd-origin evidence found no retained handle attributable to a live child; the
cleanup order (`StagingTests.tearDown` → package-unchanged assertion →
`self.tmp.cleanup()`) is sound once connections are closed. No evidence supports
a child-process or inherited-handle cause for the recorded `WinError 32`.

**Correction.**

* New `tests/sqlite_support.py::sqlite_connection()` — a context manager with
  identical transaction semantics (`with db:` → commit/rollback) plus an
  **unconditional** `db.close()` in `finally`.
* 177 direct `with sqlite3.connect(` sites in 21 B5/incremental test modules
  now use `sqlite_connection`; `tests/test_incremental_drafts.py::db()` returns
  it (covering 11 `with self.db()` sites), with its one deliberately long-lived
  reader connection still explicitly opened and `close()`d in `finally`.
  No `with sqlite3.connect(` site remains in `src/` or `tests/`.
* `src/serving/incremental_registry.py::initialize()` had the identical
  production ownership defect (`with sqlite3.connect(path) as db:`); it now uses
  `contextlib.closing(...)`, preserving the transaction context and schema.

**Measured after correction.** The same harness reports **0 of 158** B5 cleanups
and **0 of 74** non-B5 cleanups with open files (232 cleanups total).

## 4. Category 3 — `b3_overrides` `AssertionError` (cascade, not an independent product defect)

`tests/test_b5_derived_reference_trees.py::test_each_corrupt_tree_fails_selection_and_affected_publication`
loops over `DERIVED_NAMES = ('w2_delta','b2_delta','w2_overrides','b3_overrides')`
and calls `self.tearDown(); self.setUp()` at the start of every subtest after the
first (`line 179`). `b3_overrides` is the last subtest, so a failure raised by
the *previous* iteration's teardown is reported under `b3_overrides`.

`StagingTests.tearDown` (`tests/test_incremental_staging.py:43-46`) asserts the
whole fixture package is unchanged, comparing `self.before` (the `setUp`
inventory) against a fresh `self.pkg.rglob('*')` inventory, then calls
`self.tmp.cleanup()`. On Windows a leaked SQLite handle makes that cleanup fail
with `WinError 32` after `shutil.rmtree` has already removed part of the tree.
The next teardown therefore compares the full expected inventory against `{}`
(or a partial inventory), producing an `AssertionError` at line 45 whose diff
includes `GOVERNED_INPUTS.json`.

**Why `GOVERNED_INPUTS.json` appears.** It is a legitimate **class-3
provenance/evidence** file created by `tests/serving_fixtures.py` (and classified
as such in `src/serving/baseline.py`). It belongs in `self.before` — the expected
package inventory — and is **not** an output of `b3_overrides`, an overrides
value, or anything the application wrote into the package. The "empty" side of
the assertion is the *current* snapshot of a package tree that a failed Windows
cleanup had partially deleted. Linux emulation of a partially completed
Windows `rmtree` reproduced the exact shape: `FAIL: ... (name='b3_overrides')`
at `tests/test_incremental_staging.py:45`, with
`AssertionError: {'PREFLIGHT.jsonl': ...} != {}` and a diff containing
`GOVERNED_INPUTS.json`.

No assertion was weakened, no skip added, and no expected behavior changed. With
deterministic connection closure, a conditional Windows-cleanup emulation (fail
only while an SQLite handle is open) records **0** emulated `WinError 32`
failures for that test, and the `b3_overrides` subtest passes.

## 5. Corrections applied (exact files)

| File | Reason |
|---|---|
| `src/serving/atomic.py` | add `sync_file(path)` (writable `r+b` fsync) |
| `src/serving/continuity_catalog.py` | replace read-only fsync in `bootstrap()` |
| `src/serving/ticker_proofs.py` | replace read-only fsync in `build()` |
| `src/serving/incremental_registry.py` | close the initialized registry connection deterministically |
| `tests/sqlite_support.py` (new) | transaction-preserving, closing SQLite context manager |
| 19 `tests/test_b5_*.py` plus `test_incremental_publication.py`, `test_incremental_staging.py` | 177 `with sqlite_connection(` replacements of the non-closing connection context manager |
| `tests/test_incremental_drafts.py` | same via `db()` (11 sites); preserve explicit long-lived reader close |
| `tests/test_b5_windows_sync_handles.py` (new) | 6 focused regressions: read-only `EBADF` rule + `sync_file`, catalog/publication under the Windows fsync rule, connection commit/rollback/close, and Linux `/proc/self/fd` check that no handle remains at cleanup |

No production data, unrelated repositories, workflows, CI infrastructure,
deployment services, Node/npm, or frontend dependencies were changed. No B5
persistence, transaction, rollback, migration, integrity, publication, or
pinned-reader guarantee was removed.

## 6. Verification performed (Linux only)

| Check | Result |
|---|---|
| Pre-change baseline, `PYTHONPATH=src python3 -m unittest discover -s tests -t .` | `Ran 1129 tests in 118.021s` — `OK (skipped=14)` |
| Post-change full Linux suite (same command) | `Ran 1135 tests in 111.987s` — `OK (skipped=14)`; 6 new tests; pre-existing unrelated `ResourceWarning`s in `test_i4_runner.py` / `test_serving_filters.py` unchanged |
| New focused module | `Ran 6 tests` — `OK` |
| All 160 B5 tests under emulated Windows `os.fsync` rule | `Ran 160 tests in 31.850s` — `OK` |
| Open-fd-at-cleanup harness, all modules | `0 / 232` cleanups with open files (was `114 / 152` for B5 alone) |
| Category 3 focused test under conditional `WinError 32` emulation | `Ran 1 test` — `OK`, 0 emulated cleanup failures |
| Category 3 negative control (partially deleted package) | reproduces the `b3_overrides` `AssertionError` with `GOVERNED_INPUTS.json` in the diff |

**These are Linux results plus emulation only.** They establish the source
defects and that Linux behavior is intact; they do **not** establish Windows or
Python 3.14.3 compatibility.

## 7. Narrow Windows diagnostic (prepared, not executed)

Run in the existing `H:\EquiCore\equity-market-data-engine` checkout with the
correction applied, from the repository root, using Python 3.14.3. Do **not**
rerun the full suite first:

```powershell
$env:PYTHONPATH = "src"
python -B -m unittest -v tests.test_b5_windows_sync_handles
python -B -m unittest -v tests.test_b5_catalog_bootstrap.CatalogBootstrapTests.test_bootstrap_reuse_and_b2_catalog_parity
python -B -m unittest -v tests.test_b5_catalog_publication.CatalogPublicationTests
python -B -m unittest -v tests.test_b5_derived_reference_trees.DerivedReferenceTreesTests.test_each_corrupt_tree_fails_selection_and_affected_publication
python -B -m unittest -v tests.test_incremental_staging tests.test_incremental_drafts
```

If anything fails, capture the full traceback (including `winerror`/`errno` and
the subtest name) rather than a summarized count. Only after these pass should a
full `python -B -m unittest discover -s tests -t .` be considered.

## 8. Remaining limitations / unverified

1. Actual Windows + Python 3.14.3 execution has not been performed here; no
   Windows filesystem, no Python 3.14.3 binary in Arena. Windows compatibility
   remains unverified until §7 is run.
2. The recorded Windows run was interrupted after 147.34 s. Categories outside
   B5 in the remaining, unobserved tests have not been attributed; the fd
   harness found no open handles at cleanup in the non-B5 modules, but a real
   Windows run could still surface other OS-specific issues.
3. `proc.communicate(timeout=...)` would leak a child if it ever times out; no
   evidence of that in the recorded run, and no change was made (scope).
4. There is still no official Python-version/OS support matrix; declaring one is
   an owner decision, not an inference from this correction.
