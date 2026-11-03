# B5 bounded composite publication and application integration

Continues from `9c6990c` under the owner's recorded authorization. **B5 remains
open.** This is an actual, opt-in application integration for bounded
synthetic-sized datasets, not completion of the qualified M2 workflow.

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

Start the actual application with its normal roots **and** `--registry <root>`
to opt in to the active composite. Each request reads the active pointer and
one complete generation payload together, verifies its digest and baseline
manifest/index binding, then pins that payload for the entire request. A
publication concurrent with a request cannot switch that request midway. A
server restart selects the durable pointer again without reading or reprocessing
source archives. With no selected generation the configured app uses the
baseline; a corrupt or inconsistent selected generation fails closed. Symbol
catalog caching is serialized and keyed by generation to avoid cross-generation
reader races.

In the selected composite, normal and saved-query UI requests for Q1–Q5 use
the selected index and canonical rows. Q3/Q4's B2 resolution scans the whole
selected baseline-plus-delta corpus; Q5 uses the recomputed W2 identities plus
the baseline-plus-delta B3 derivation. Q5 serving annotations identify the
composite W2 source rather than pretending it is the original qualified W2
file. The UI status response reports the selected generation and supported
modes. Existing server behavior without `--registry` is unchanged.

## Scope limits — B5 is not complete

* **Hard capacity limit:** publication refuses a baseline or composite above
  20,000 canonical rows, or baseline/staged content above their respective
  128 MiB safety limits. This bounded implementation cannot publish the
  approximately 5.7-million-row qualified M2 baseline. B3 materializes row
  evidence and the current implementation reads and re-derives all canonical
  rows for each changed generation. No real-M2 resource claim is made.
* Only Q1–Q5 are implemented for a selected composite. Q6–Q10 and history
  recording explicitly fail closed, rather than mixing qualified-baseline
  calendar, detail, quality, inventory or qualification data with the new
  generation. In particular, the Inspector's Q7 detail is unavailable.
  Conflict findings remain visible through the registry CLI, not Q8/Q9/Q10/UI.
* The serving CLI's existing Q3/Q4/Q5 commands still address the baseline;
  composite selection currently exists only in the opt-in local UI adapter.
  Servers launched without `--registry` continue to show the baseline, so
  selection is not yet a globally authoritative application-wide switch.
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

* Focused suite: **248 passed**.
* Full suite: **977 passed, 14 skipped**; pre-existing unrelated
  ResourceWarnings remain.
* Synthetic fixture runner identity is patched for publication tests, because
  it is not an I4 runner package. Actual current engine/runner fingerprints were
  compared to the recorded M2 pins in the prior staging work. Qualified M2 was
  not accessed or modified; Windows-specific tests remain pending.
