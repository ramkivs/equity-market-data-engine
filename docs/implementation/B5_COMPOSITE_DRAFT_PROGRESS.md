# B5 composite draft work — not a publication or closure

Continues from `e057af0` under the recorded owner authorization. The existing
staging and D21 registry remain in place. **B5/OW-10 is not complete and is
not closed.**

## Implemented

The existing manual registry CLI has additive `draft` and `drafts` commands,
using the same explicit package, registry, serving-state, saved/history and
source roots. `draft` requires an already valid baseline serving index and at
least one staged input. It captures a **DRAFT-NOT-SERVEABLE** snapshot in the
registry SQLite database; it does not accept an input, alter the accepted
registry, write the baseline/index, select an active generation, or enable
serving of the staged rows.

Within a single `BEGIN IMMEDIATE` transaction, the draft operation:

1. Checks staged record version bindings and baseline manifest identity;
   verifies the staged row and evidence hashes, evidence's determinism-view
   hash, row count, source dates and canonical provenance.
2. Captures a detached copy of the staged rows, evidence and metadata. It also
   records the existing baseline index digest and counts; index replacement
   during snapshot causes a failure. It neither scans baseline canonical rows
   nor reads historical source archives. If the baseline serving index is
   missing or stale the draft operation fails; it does not rebuild it.
3. Derives per-candidate index fragments, B2 row-level ticker observations,
   and a B3 **delta-only** derivation. These are not composite continuity:
   cross-baseline ticker reuse, overlapping intervals and other ambiguity can
   change the answer. They must not be exposed as canonical Q3/Q4/Q5 answers.
4. Inserts the draft manifest and all detached members in the same SQLite
   transaction; its deterministic ID is a digest of its manifest. Repeating an
   unchanged snapshot reuses the same draft after verifying its members.
   `drafts` rechecks the manifest digest and detached member hashes before
   listing it. These checks detect ordinary corruption; they are not signatures
   or a defense against an attacker who controls the local database.

A draft snapshot is bounded to 20,000 staged rows and 128 MiB of staged text;
the byte bound is checked in SQLite before loading the staged blobs into Python.
These are safety limits for this draft mechanism, not capacity claims for M2.
Existing drafts are not automatically deleted; their storage remains user data.

## Evidence and tests

`tests/test_incremental_drafts.py` covers draft determinism and idempotency,
detached snapshots, corrupted stage/member rejection, missing index and size
limits, CLI behavior, and preservation of synthetic baseline package bytes.
It tests an injected insertion error and an actual abrupt process exit inside a
SQLite transaction; reopening rolls back the incomplete **draft** and retry
succeeds. A concurrent SQLite reader sees either the old empty draft state or
complete committed draft rows, not an intermediate draft. This is a test of
SQLite draft isolation, **not** a composite serving-reader switch.

Existing Q3/Q4/Q5 results remain unchanged after creating a draft; this proves
that drafts are not accidentally served, not that composite queries work.
Synthetic fixture tests never access M2. The no-baseline-row-read assertion
applies to draft creation with a previously built index; ordinary existing
server startup still performs its documented package verification reads.

* Focused regression suite: **189 passed**.
* Full unittest discovery suite: **964 passed, 14 skipped**. Existing unrelated
  ResourceWarnings remain.
* Windows-specific behavior and real M2 were not tested.

## Unresolved acceptance criteria

No staged input has been published or accepted. There is no active composite
generation pointer, no application reader switch, no aggregate serving-index
update, no baseline-plus-delta W2/B2/B3 computation, no Q3/Q4/Q5 integration,
and no recovery test for an actual multi-artifact composite publication or
application restart against that publication. Q8/Q9/Q10/UI still do not expose
the registry conflict findings. The resulting draft artifacts must not be called
published records or used as effective continuity.

The outstanding technical work is to establish and validate a consistent
composite generation and atomically make all its components visible to readers,
including W2/B2/B3 semantics across historical and new observations, without
modifying M2 or reprocessing its source archives. Existing serving assumes a
single verified baseline package; the B3 full-evidence derivation is deliberately
bounded and is not validated at M2 scale. The isolated delta-only draft cannot
resolve this by itself. This is unfinished engineering, not an authorization
blocker or a claim that the task is impossible.
