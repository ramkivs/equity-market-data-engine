# B5 OW-10: targeted continuity-catalog integrity

**B5 remains open. Delta-only publication is not implemented by this
increment.** This is a prerequisite for the approved publication increment:
the format-1 catalog required a full observation-catalog verification before
trusting an indexed identity lookup, since a corrupted key could hide a row.
The current bounded publisher, 20,000-total-row guard, Q6/Q8/Q9 limitations,
and registry migration remain unchanged.

Format 2 adds W2-keyed and B2-valid-identity-keyed group counts and digests,
plus a digest of the compact group manifest, while retaining the existing
baseline and serving-index bindings. A lookup validates that compact manifest
and all projections for the selected identity in one pinned SQLite read
transaction. It rejects altered, deleted or miskeyed selected rows, including
rows moved into an identity absent from the manifest. W2 still uses normalized
raw ISIN independently of validity; B2 keys remain valid-ISIN/date only. A
missing identity is an empty result only after its group manifest has been
checked. Lookup reads group metadata for all identities, but only observation
rows for the requested identity; it does not open canonical rows or source
archives. It buffers the selected identity's projections so no partial result is
returned before the digest check completes.

A pre-existing format-1 catalog can be upgraded with `catalog-upgrade` under
the existing registry CLI root arguments. The migration first fully verifies
the existing catalog and its baseline/index binding, then creates the group
proofs and switches metadata in one SQLite transaction. It reads the existing
catalog once and does not open historical canonical rows. Errors or process
termination roll back; a retry is safe. Repeated upgrades verify and return
`ALREADY-CURRENT`. A corrupt v1 catalog is refused, not rebuilt or replaced.
New bootstraps write format 2. Both versions remain readable for explicit full
catalog verification; format 1 fails closed on targeted lookups until upgraded.

The integrity checks detect accidental inconsistencies, not a malicious party
able to rewrite the catalog and all digest metadata. The baseline catalog is
not yet updated with new delta projections, and identity proofs are not yet
referenced by any active composite generation. Application reader generation
pinning and transactionality for future delta publication are therefore **not
established by this increment**.

`tests/test_b5_catalog_identity_proofs.py` uses disposable fixtures to compare
identity lookup behavior, inspect the SQL to ensure unrelated observations are
not scanned, detect omitted/miskeyed rows and group-manifest corruption, verify
W2 invalid-ISIN versus B2 semantics, demonstrate one-snapshot lookup under a
concurrent writer, and test v1 migration, refusal of corruption, exception and
abrupt-process rollback, retry and CLI operation. M2 was not accessed; Windows
validation remains pending.

Linux suite: **1003 tests run, 14 skipped**; existing unrelated
ResourceWarnings remain.
