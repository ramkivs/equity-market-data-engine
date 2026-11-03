# B5: owner authorization and incremental-registry progress

> Subsequent staging work is described in `B5_INCREMENTAL_STAGING_PROGRESS.md`.
> OW-10 remains incomplete.

## Decision and status

The owner, acting as Personal Application Principal, explicitly authorized
D16-13(2) / OW-10 and superseded D23's incremental implementation restriction
in the current task. Scope includes source registry/classification, D21 conflict
handling, delta ingestion, derived updates, recoverable publication and local
serving integration. M2 and historical evidence remain immutable; single-user
local scope remains. D21's unresolved conflict hold and its separate
per-instance resolution boundary remain in force. The prior gate assessment
in `B5_INCREMENTAL_GATE_AND_RESTART_VERIFICATION.md` is historical, not the
current authorization status.

**OW-10 is not complete.** This change supplies an explicit baseline registry
and conflict-inspection foundation, not a delta ingestion or publication system.
There is no remaining authorization gate for the authorized work; the remaining
work is engineering and validation, not an external approval dependency.

## Implemented

`python -m serving.incremental_registry` is a deliberately separate manual CLI
and library. It requires the package, registry, serving state, saved-state,
history-state, LEGACY and UDIFF roots to be explicitly provided and mutually
non-overlapping. It does not run at server startup. It opens/verifies the
baseline using the existing serving verifier (`--m2` pins the known M2
identity); this verification reads baseline package files, but no source archive
is read during registry initialization. It seeds accepted archive identities,
content hashes, result metadata and baseline version/run bindings from the
verified `INPUT_MANIFEST.jsonl` and `RUN_RECORD.json`. SQLite transactions and
exclusive registry creation prevent a normal repeated initialization from
replacing existing user state. The registry is local user data outside the
package, not an M2 modification.

`inspect` takes one explicit root-relative input path, an independently supplied
governed ISO date, scan identifier and complete current version bindings; it
hashes the input and compares it to baseline entries. It does not invent a date
from a filename. Results are:

* `UNCHANGED` only for matching apparent identity, original root/path, digest and
  current bindings; mismatched bindings are `STALE`.
* Same accepted identity with changed bytes becomes
  `CHANGED-CONFLICT-UNRESOLVED`, durably stored with prior manifest record,
  prior run/manifest, both binding contexts and first discovery scan ID. Later
  repeated scans do not erase that first observation. Prior accepted data is not
  modified. No conflict resolution is implemented.
* Repeated accepted content at a different identity/path is an anomaly.
* `NEW-UNVALIDATED` is only a preliminary classification: no ZIP structure,
  CRC, schema, reconciliation or eligibility check has been performed, and it
  is **not** entered as processed, ingested, published or served.

`conflicts` lists durable findings. These are currently visible only through
this CLI/library, **not** through Q8/Q9/Q10 or the UI. A SQLite transaction
rolls back an interrupted conflict write on next open; an existing or partially
initialized database is never overwritten or silently repaired. A failed first
initialization may leave an incomplete database which fails closed and requires
user inspection before retrying. This is not end-to-end publication recovery.
As with B1, root checks are practical local safeguards, not a guarantee against
concurrent adversarial path swaps; Windows filesystem-specific behavior is not
validated.

Example (set all paths and current version-binding JSON explicitly):

```text
PYTHONPATH=src python -m serving.incremental_registry \
  --package <pkg> --m2 --registry <registry> --state <state> \
  --saved-state <saved> --history-state <history> \
  --legacy-root <legacy> --udiff-root <udiff> init
# Use the same global options followed by `conflicts`, or
# `inspect --root LEGACY --relative-path <path> --date YYYY-MM-DD
#  --scan-id <id> --current-bindings <json>`.
```

The caller must obtain current bindings from the actual engine/runner context;
passing baseline bindings blindly cannot establish version applicability. The
CLI does not resolve or validate a proposed version migration.

## Remaining, not implemented or validated

Automated governed corpus discovery and anomaly/CRC checks; delta canonical
processing; acceptance/validation and incremental publication; atomic coupling
of registry with publications and crash recovery; composite index/serving
integration; incremental W2/association and other derived-state recomputation;
Q8/Q9/Q10/UI conflict visibility; and end-to-end new-input, duplicate,
interrupted-publication, deterministic-result and real-M2 validation. In
particular, B3's full evidence builder still has the large-M2 resource
limitation documented in B4; do not assume a materialized all-row rebuild is
safe or a merged W2 association is correct without a tested compositional
contract. No new archive is processed or represented as accepted by this change.

## Validation

* Synthetic focused registry, root-isolation, restart and B2/B3 tests: 35 passed.
* Full `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -t . -q`:
  944 passed, 14 skipped; existing unrelated ResourceWarnings remain.
* Tests include baseline-only bootstrap without source reads, unchanged/stale,
  candidate/duplicate/changed classification, explicit conflict persistence,
  repeated inspection, transaction failure/retry, root rejection and real CLI
  calls. They compare all synthetic baseline package bytes before and after.
* No real M2 archives or package were accessed, regenerated or modified;
  Windows validation remains pending B6.
