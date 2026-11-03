# B5 bounded composite publication and application integration

Continues from `9c6990c` under the owner's recorded authorization. **B5 remains
open.** This is an actual application integration for bounded synthetic-sized
datasets, not completion of the qualified M2 workflow. The continuation after
`84e2b4c` adds normal-startup binding and several reader paths, but does not
satisfy the requested 5.7-million-row or all-reader acceptance criteria.

## Publication and reader switch

The existing registry CLI gains a `publish` command. It takes the same explicit
package, registry, state, saved, history and LEGACY/UDIFF roots as staging. It
validates current engine/runner/config bindings, rechecks the staged source hash
and staged rows/evidence/provenance, and applies existing D21 classification.
Changed previously accepted input is a durable unresolved conflict, never an
implicit replacement. A previously published identical candidate is a no-op;
no canonical parsing, W2 replay or B3 derivation occurs on that no-op.

For a new publication the operation reads canonical baseline rows, **not source
archives**, and replays the existing W2 accumulator. It refuses publication
unless the replayed baseline W2 identity documents exactly match the original
published W2 documents. It then derives W2 and B3 over baseline plus staged
rows, constructs a composite index using the existing verified baseline index
and staged contributions, and retains canonical rows, evidence and derived
artifacts in a single content-digested SQLite generation. Existing historical
canonical fields and provenance are not rewritten. The accepted registry rows,
generation, and active pointer are committed together in one SQLite transaction;
older generations and staged data are retained. Prior conflict provenance now
correctly references the incremental generation/run rather than attributing a
published delta to the baseline run.

Before committing a new active generation, publication creates a durable,
content-checksummed state-to-registry binding in the serving state directory.
Normal UI startup with the ordinary package/state/saved/history roots then
selects the active generation without `--registry`. The shared saved-query
executor, history recorder, direct serving `query` and `dataset` CLI also select
that generation. A request takes one verified generation snapshot; a concurrent
publication cannot switch it midway. The UI status response identifies the
selected generation. A malformed, mismatched, incomplete or corrupt binding or
generation fails closed. An explicit `--registry` must agree with an existing
binding. The binding is created before the pointer transaction; a crash during
its creation can leave an incomplete binding, which requires diagnosis and is
not automatically deleted. Its digest catches accidental corruption, not an
adversary able to recompute it.

Q1–Q5 continue to use the recomputed index, rows, W2 and B3. Q7 now reads the
selected generation: qualified baseline rows use the original manifest and
reconciliation; incremental rows carry the committed candidate digest and
published generation, and explicitly say reconciliation was not published for
that input. The UI inspector displays this availability rather than implying an
empty reconciliation result. Q10 intentionally evaluates the original baseline
qualification and labels it baseline-only; it does not assert the composite is
qualified. History records execute via the shared selected-generation executor.
However, history's existing entry schema does not record the generation ID, so
history alone is not a complete generation provenance record.

Compatibility migration: an existing registry published by `84e2b4c` has no
binding. Starting once with its prior explicit `--registry` validates and binds
it; subsequent normal startup works without the option. There is no safe
registry discovery from package/state alone for an unbound old installation.
Similarly, a binding file that is completely removed is indistinguishable from
an installation never bound, so ordinary readers can revert to the baseline;
this remaining failure mode prevents an application-wide guarantee. Do not
manually remove it as a recovery mechanism.

## Scope limits — B5 is not complete

* **Hard capacity limit:** publication refuses a baseline or composite above
  20,000 canonical rows, or baseline/staged content above their respective
  128 MiB safety limits. This bounded implementation cannot publish the
  approximately 5.7-million-row qualified M2 baseline. B3 materializes row
  evidence and the current implementation reads and re-derives all canonical
  rows for each changed generation. No real-M2 resource claim is made.
* Q6 calendar, Q8 quality and Q9 inventory still fail closed in selected
  UI/saved/history execution. In particular, selected-generation reconciliation,
  unresolved state, conflict findings and archive inventory are not exposed as
  complete UI views. Registry CLI still reports D21 conflicts. Direct CLI
  `quality` and `query --calendar` fail closed with an active composite.
* CLI `inventory` and `qualification` take no serving-state argument and remain
  explicitly labelled original-baseline-only, not selected-generation views.
  `info` labels its index metadata baseline-only when a binding exists. These
  distinct commands and pre-binding installations mean the application-wide
  selection requirement is not fully met. A normal state rebuild currently
  refuses the additional binding file rather than deleting it.
* Normal discovery is still manual and dates are supplied as governed input;
  this is not an automated corpus watcher. Publication rechecks retained
  staged source files, including already published deltas, so missing sources
  can prevent a later publication. A normal application restart/query does not
  require those source files.
* Version/config mismatch, inconsistent W2 replay, invalid staged evidence,
  changed candidate or corrupt generation fails closed. Local path checks do
  not eliminate concurrent hostile source swaps, and SQLite crash tests do not
  establish Windows power-loss guarantees. No automatic cleanup of prior
  generations or user data is performed.

Therefore this is not the requested complete M2-scale publication, W2/calendar/
metrics integration, or full application-wide reader switch. Those acceptance
criteria and B5 remain unresolved; no additional owner authorization is needed.

## Synthetic validation

`tests/test_incremental_publication.py` exercises staging → bounded
publication → live HTTP application Q3/Q4/Q5 → restart, including a legacy-to-
UDiFF ticker change, original W2 replay, direct B3 baseline-plus-delta parity,
canonical lineage, saved-query selection and unchanged/no-op behavior. Tests
also inject first/second publication failures, terminate a subprocess during the
pointer transaction, verify rollback/retry and prior generation preservation,
pin an in-flight application request while switching the pointer, detect
corrupt payloads, retain D21 conflicts, and compare original synthetic package
bytes. After publication the server restart test removes source fixture files
and still serves the committed rows.

* Earlier `84e2b4c` evidence: focused suite 248 passed; full suite reported
  977 tests and 14 skips.
* Continuation synthetic tests cover ordinary startup without `--registry`,
  restart without source archives, Q7 baseline/delta provenance, scoped Q10,
  saved queries, history, direct CLI selection, corrupt/mismatched bindings and
  one-time legacy binding. Existing publication tests cover in-flight pinning,
  rollback/retry, crash and D21. See `tests/test_b5_application_readers.py`.
* The continuation suite ran **983 tests, 14 skipped**; pre-existing unrelated
  ResourceWarnings remain. Windows-specific validation remains pending.
* A 5,700,000-row **count sentinel** in a tiny synthetic index is rejected by
  the existing 20,000-row guard before row processing. It is not a 5.7-million-
  row fixture, a scale test, or evidence of M2-scale compatibility. No full-size
  synthetic lifecycle was performed. Removing the guard alone would still leave
  baseline rows, W2/B3 evidence and the single SQLite JSON generation payload
  materialized in memory; a scalable representation/reader path remains to be
  implemented and validated.
* Synthetic fixture runner identity is patched for publication tests, because
  it is not an I4 runner package. Actual current engine/runner fingerprints were
  compared to the recorded M2 pins in the prior staging work. Qualified M2 was
  not accessed or modified; Windows-specific tests remain pending.
