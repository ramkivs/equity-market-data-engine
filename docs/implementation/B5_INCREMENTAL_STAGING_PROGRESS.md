# B5 incremental staging progress (OW-10 not complete)

> Subsequent non-serveable draft work is documented in
> `B5_COMPOSITE_DRAFT_PROGRESS.md`; OW-10 remains incomplete.

This work continues the owner-authorized B5 effort from `591119b`; it does not
replace the baseline registry or D21 conflict handling. **B5 is not closed.**

## What works

The existing `serving.incremental_registry` CLI has two additive commands:

* `prepare --root LEGACY|UDIFF --relative-path <path> --date YYYY-MM-DD
  --scan-id <id>` validates and stages an explicitly supplied NEW candidate.
* `staged` lists staged metadata, explicitly marked
  `VALIDATED-STAGED-NOT-PUBLISHED`.

Both require the existing global package, registry, state, saved/history and
source-root arguments. The caller supplies the governed date: it is not inferred
from the filename. The engine's own fingerprint, runner fingerprint, spec and
processing-contract version, plus its default configuration fingerprint, must
match the verified baseline. A mismatch fails closed; the tool does not perform
migration or requalification. The current checked-out fingerprints match the
published M2 engine and runner pins, but **M2 was not accessed**.

The staged path delegates initial classification and D21 conflict recording to
the existing registry. Only NEW candidates proceed. ZIP bytes are rehashed and
compared with the inspection result; the archive must contain exactly one CSV
member, be CRC-readable and unencrypted, and meet the explicit 128 MiB archive
and uncompressed-member limits. The existing canonical engine parses the new
member, checks family and business date, requires at least one row and rejects
quarantine. Duplicate governed dates and duplicate contents, including staged
entries, are rejected. The archive's canonical rows, evidence, their digests,
version bindings and deterministic run identity are inserted together in a
SQLite transaction under the separate registry root. A repeated identical
candidate returns `ALREADY-STAGED` without re-running the canonical parser.
Concurrent insertion is rechecked in the insertion transaction. Changed accepted
content remains a D21 conflict, never a replacement.

**Staging is not ingestion publication.** Staged entries are not inserted into
the processed registry, are not canonical serving state, are not used by Q1–Q10,
and do not update any serving index, W2, B2 or B3 data. The original qualified
baseline is never written by this path. A user must not treat a staged record as
accepted or available for querying. Staging currently stores rows/evidence in
SQLite, not a separately verified incremental package; before a future
publication, all stored digests, source/version bindings and consistency must be
verified again.

The staging transaction is restart-safe at its SQLite insertion boundary; an
injected INSERT failure rolls back and retry succeeds. It does **not** implement
or prove recovery of a multi-artifact publication. Initial registry creation's
previously documented interrupted-initialization limitation remains. No
Windows-specific validation has been performed.

## Unfinished requirements and technical limitations

There is no automatic corpus discovery; candidate date and identity must be
provided. There is no acceptance or durable incremental publication, no atomic
registry/publication/serving switch, no composite serving integration, and no
updated index, W2 association, B2 symbol resolution, B3 continuity, Q3/Q4/Q5,
quality/calendar/metrics, or UI result for staged rows. Conflict findings also
remain outside Q8/Q9/Q10 and the UI. Thus the requested end-to-end ingestion,
restart recovery of publication, and corresponding end-to-end validation have
not been delivered.

The concrete correctness problem still to solve is how to construct and verify a
single consistent composite generation (registry, original baseline plus
incremental rows, indexes, W2 and serving metadata) and switch readers to it
atomically, while keeping prior generations and M2 immutable. Existing serving
assumes one verified package and indexes keyed to its manifest; W2 association
intervals and B2/B3 ambiguity can change across an identity's entire history,
including ticker reuse and out-of-order observations. The existing B3 full
builder buffers all evidence and its large-M2 path is deliberately unavailable;
a delta-only shortcut has not been shown equivalent to the published contracts.
Treating staged rows or a forged manifest as a completed generation would risk
silent inconsistent serving. This is unfinished engineering and validation, not
an unsatisfied owner-authorization gate or a claim that implementation is
impossible.

## Validation

* Focused tests: 177 passed, covering staged new input, no-op retry, invalid and
  corrupt ZIPs, duplicate date, changed conflict, version mismatch,
  deterministic replay, SQLite insertion rollback/retry, registry/root safety,
  B2/B3 and saved/serving regressions. Synthetic package bytes are compared
  before/after. The synthetic fixture's runner binding is patched in staging
  tests because it deliberately does not use the I4 runner; real current engine
  and runner fingerprints were separately checked against the recorded M2 pins.
* Full suite: 952 passed, 14 skipped; unrelated pre-existing ResourceWarnings
  remain. Real M2/Windows validation was not performed.
