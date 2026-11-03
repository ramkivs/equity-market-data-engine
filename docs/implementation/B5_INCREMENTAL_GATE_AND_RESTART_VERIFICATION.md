# B5: second-gate assessment and independent restart verification

> Historical assessment: subsequently superseded by the owner’s explicit
> D16-13(2) / D23 authorization. See `B5_AUTHORIZED_INCREMENTAL_PROGRESS.md`.
> That authorization removes the gate; it does not itself complete OW-10.

Status: **OW-10 / incremental ingestion not implemented; B5 remains blocked.**
This record and its tests do not authorize the withheld operation, modify a
governing decision, or create an incremental registry or publication.

## Gate finding

* D16-12 and D16-13(2), in
  `docs/architecture/POST_I5_SERVING_INCREMENTAL_PRODUCT_ARCHITECTURE_AUTHORITY_DECISION.md`,
  separate incremental-ingestion implementation from the first release and
  require a later explicit, scoped authority decision. D16 §20 describes the
  decision-input → explicit-authorization → scoped-implementation → evidence →
  remote-verification pattern.
* `docs/architecture/D23_FIRST_RELEASE_SERVING_IMPLEMENTATION_AUTHORITY_DECISION.md`
  §2, §8, §17 and §19 expressly discharge item (1), not item (2); incremental
  ingestion and the physical choices for the registry remain withheld for a
  separate decision. Repository searches found no later decision discharging
  D16-13(2). This finding is about the documented prerequisite; the B5 request
  explicitly instructs not to bypass it or invent authorization.
* `docs/architecture/D21_D16_03A_CHANGED_CONTENT_DISPOSITION_AUTHORITY_DECISION.md`
  §14–19 resolves the **policy** for changed content, not the implementation
  gate: CHANGED-CONFLICT-UNRESOLVED must be durable and visible as a finding,
  the changed candidate is held out of canonical processing and serving, and
  prior accepted data stays authoritative. Per-instance conflict resolution is
  independently withheld by §22.

The exact outstanding condition is a **separate explicit, recorded authority
 decision for incremental-ingestion implementation under D16-13(2)**, with the
scope and relevant physical registry/publication decisions addressed under
D16-13(5), as applicable. The authority must preserve D16-01–06 and D21 §14–19.
No separate approval is needed for the read-only verification below; it does
not satisfy or replace that gate. Do not treat this assessment as the decision.

## Work completed independently of the gate

`tests/test_b5_existing_restart.py` uses disposable synthetic packages and no
source archives. It verifies:

1. A valid existing serving index is loaded without build, write, or rebuild;
   its byte snapshot and an unrelated user-owned sentinel remain unchanged.
2. Both real module entry points are started sequentially against the same
   package and existing state. Q1 results agree; pre-existing saved query and
   history records remain visible. Package, index, saved and history file bytes
   are unchanged after each shutdown.

Existing startup **does verify the package files and their hashes** and may
build/rebuild a missing or stale serving index. It does not process historical
source archives at startup; this is not a claim that restart performs no file
reads, or that an incremental lifecycle exists. The synthetic package is not
qualified M2. No M2 package was accessed or changed.

## Work remaining after the second gate

The requested source registry/bootstrap, new/unchanged/duplicate/changed
classification, durable conflict findings, processing of eligible new inputs,
publication/recovery, composite serving indexes and associations, and the
corresponding delta/failure-recovery/determinism tests remain **unimplemented
and unvalidated**. In particular, the existing Q8/Q9/Q10 absence markers do not
represent a functioning conflict registry, and ordinary restart tests cannot
establish delta-ingestion recovery.

A future scoped implementation must retain the content and version bindings of
D16-02/04, D16-03's anomaly treatment, D21's prior/candidate relationship and
unresolved hold, D16-05's reproducibility from all processed canonical rows,
separate validated incremental publications, and B1 root isolation. Updating
only affected derivations must still be demonstrably equivalent to the required
corpus-wide deterministic result; the current B3 full-evidence derivation has
its own documented large-M2 limitation. How registry initialization from the
qualified baseline and publication/registry crash consistency meet those
contracts must be established within that authorized work, not assumed here.

## Validation

* `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_b5_existing_restart -q` — 2 passed.
* Full suite: 939 passed, 14 skipped; existing unrelated ResourceWarnings remain.
* Real M2 and Windows-specific testing were not performed.
