# B5 OW-10: catalog-backed composite publication

**B5 remains open.** This increment adds an actual catalog-backed publication
and reader path, including scoped Q6/Q8/Q9 and bounded-generation migration.
It does not close the accumulated-delta scalability or lifecycle gaps below.

## Publication and selected readers

When a state directory contains a valid format-2 continuity catalog,
`serving.incremental_registry ... publish` selects the catalog-backed path. A
pending batch is limited to 20,000 incoming canonical rows and 128 MiB of staged
record/row/evidence data; these are **batch limits, not a limit on baseline or
baseline-plus-delta row count**. It verifies the existing catalog binding and
compact ticker census, validates and rehashes pending inputs only, and derives
W2 and B3 for affected identities using catalog group proofs plus the affected
previous and new delta projections. Ticker reuse causes other valid identities
sharing a new ticker/series to be re-evaluated. It updates the composite index
and preserves original historical canonical rows and provenance.

Accepted registry entries, the immutable generation and the active pointer are
committed together in one SQLite transaction. The catalog itself remains
baseline-only and read-only. A pinned catalog read transaction is used during
publication. The publisher does not read historical canonical row files; prior
accepted source archives are not required when publishing a later delta. An
unchanged batch returns the prior generation without reprocessing old sources.
The existing D21 changed-content hold and duplicate-content detection remain
in force.

Normal UI startup reads the durable binding and pins a selected generation per
request. Q1–Q5, Q7 and scoped Q10 use the selected generation; saved queries,
history execution and the existing serving CLI query path share it. Q3/Q4 use
the generation's baseline-plus-delta ticker census. Q5 streams the original W2
association file, replacing affected identities with generation-bound W2
results; B3 summaries for affected identities are stored in the generation and
unaffected identities are derived on demand from verified catalog groups. The
original W2 file is checked when accessed in metadata/on-access mode. An
in-flight request keeps its prior payload if a concurrent publication switches
the active pointer. Q7 delta rows retain their staged provenance and explicitly
report unavailable incremental reconciliation.

Without a catalog the original bounded publication path remains for existing
small fixtures/installations. If a format-1 catalog exists, it must first be
upgraded with `catalog-upgrade`; malformed or mismatched catalogs fail closed.
The catalog-backed publisher migrates an active `bounded-composite/1.0`
generation in its publication transaction, with or without pending new inputs.
It validates the retained incremental rows and evidence, checks their accepted
registry identities and reconstructs and compares the bounded serving index.
It derives affected identities from the catalog and the retained deltas, without
reading historical canonical rows or accepted source archives. The prior
generation, accepted entries and staging remain intact; the new generation and
any new accepted entries become active atomically. Invalid or inconsistent
evidence fails closed, leaving the old pointer in place. This is a one-time
bounded-delta migration, not a solution to accumulated-delta rematerialization.

## Scope limits — no B5 completion claim

* Catalog-backed generation format 7 stores incremental canonical rows and
  evidence once as content-addressed SQLite blobs. Later publications refer to
  existing blobs without reading or copying their contents. Readers verify each
  accessed blob against its generation-pinned digest; old blobs remain available
  to in-flight readers. The active pointer, new blobs, new accepted records and
  generation commit in the same transaction. Existing format-1 catalog composites
  migrate once from their retained inline deltas, with digest/accepted checks and
  no historical canonical or accepted source archive reads. Format-2 generations
  migrate their inline identity projections, and format-3 generations migrate
  their inline W2/B3 overrides, transactionally. Format-4 ticker snapshots
  migrate by streaming retained incremental blobs and verifying the reconstructed
  baseline-plus-delta census against the old snapshot; no old source archive or
  historical canonical row is read. Format-5 generations migrate their inline
  composite indexes to format 6 after checking the baseline portion and
  reconstructing delta file metadata and flags from verified retained deltas.
  A format-6 generation migrates its binding to format 7 without replaying
  its prior incremental rows or source archives.
* W2 and B2 incremental projections are stored as content-addressed per-identity
  groups. Later publication reads and rewrites only groups affected by the new
  rows or ticker ambiguity; unaffected group contents are not copied or read.
  Group hashes and identity/source checks are verified when accessed, and prior
  versions remain available to pinned readers. A single heavily updated identity
  can still grow without bound within its individual group blob.
* W2/B3 overrides are also retained as verified per-identity blobs. A later
  publication writes only re-derived overrides; unaffected override bytes are
  neither copied nor read. Readers resolve the generation-pinned digest on
  access, and old versions remain available to pinned readers. Explicit
  registry binding verifies all retained override blobs.
* Generation JSON keeps the incremental ticker census only, not another copy
  of the baseline census. A one-time, no-replace proof bootstrap copies the
  already-verified compact baseline ticker census to a separate bound SQLite
  lookup file, without canonical-row or archive reads. Format-7 readers and
  publishers verify its group manifest, then load and verify only the selected
  ticker/series and identity/series groups. Ticker resolution and overlap/reuse
  ambiguity retain their existing semantics. `catalog-verify` fully verifies the
  proof file when present. Missing or corrupt proofs fail closed; the explicit
  `ticker-proof-recover` registry command can recreate a missing file only if
  its calculated binding matches the active generation, and never overwrites
  an existing file.
* Generation JSON stores only incremental index file metadata and flag counts,
  bound to the separately verified baseline index. Publication updates that
  overlay without copying or recomposing the full baseline index. Readers
  reconstruct the existing complete index contract (including partition and
  distinct-instrument counts) from baseline metadata and the pinned overlay.
* This is **not yet fully delta-only**: the incremental index file metadata,
  ticker census, candidate references, and identity-group and override reference
  maps remain together in each generation JSON. Publication still validates
  and scans the compact ticker-group manifest, and copies/serializes accumulated
  incremental structures; targeted lookups also filter the incremental ticker
  census. Readers still compose and scan the complete index metadata, though
  neither path rereads historical canonical rows for this work. Very large or numerous deltas can still hit memory or SQLite
  single-value limits. No scalable long-running lifecycle is established.
* The original qualified historical canonical baseline is not reread during
  catalog-backed publication. Q3/Q4 still scan candidate historical row files
  to serve a query, and Q5 streams the original W2 association file; these are
  query reads, not historical archive ingestion or publication replay.
* An existing unbound registry is not discoverable from the package/state
  alone. No filesystem search or location guess is performed. UI status explicitly
  reports `location-not-identified` and baseline-only scope when neither binding
  nor guard exists; this cannot prove that no unbound registry exists. Supply a
  known registry path with the registry CLI `bind` operation or UI `--registry`.
  Explicit binding validates the baseline accepted manifest records, existing
  staged and published delta evidence, active generation and D21 identities;
  it never replaces or deletes registry records. It does not read historical
  canonical rows or source archives. It refuses inconsistent or missing state.
  A separate checksummed guard is created before the binding; if the binding
  disappears while the guard remains, readers fail closed and explicit binding
  of the same validated registry repairs it. This protects against one missing
  file and interrupted creation, not simultaneous deletion of both files or a
  hostile coordinated rewrite. Pre-guard installations acquire a guard at the
  next explicit binding or publication; until then missing legacy bindings
  remain indistinguishable from never-bound state.
* Q6 overlays incremental file presence on the qualified calendar without
  replacing sourced labels or explaining unknown days. If the qualified W2
  calendar is absent, Q6 explicitly labels a presence-only reconstruction from
  the input manifest; missing-day holiday labels and baseline UDiFF date-equality
  evidence remain unknown. Q8 includes selected index flag counts and incremental
  quarantine, while unresolved and reconciliation evidence is baseline-only;
  incremental reconciliation is unavailable, and D21 findings are captured with
  the selected request snapshot. Q9 joins original D01 evidence only to original
  inputs and reports incremental provenance separately, with no fabricated D01
  or combined archive-set digest. Q10 remains baseline-only.
* Q6/Q8/Q9 are wired through selected UI, saved/history and CLI paths. CLI
  inventory requires `--state` to select the bound generation; omitting it is
  explicitly baseline-only. D21 findings reflect the request's registry snapshot,
  which can change without a new published generation.
* The catalog and selected generation integrity checks detect accidental
  corruption, not an adversary able to rewrite both state and checksums; local
  concurrent hostile path swaps are outside the documented B1 guarantees.
  Windows validation remains pending.

## Disposable validation

`tests/test_b5_catalog_publication.py` exercises the actual registry publisher,
normal selected UI/CLI/saved/history paths, W2/B3 parity on a small complete
fixture, ticker transitions and reused-ticker ambiguity, Q3/Q4/Q5/Q7, a retained
in-flight request, D21 and duplicate detection, first and second publication
rollback/retry, abrupt subprocess exit before pointer commit, restart without
source archives or `--registry`, catalog corruption, and bounded-generation
migration including missing old source archives, corruption and rollback/retry.

A separate *actual persisted synthetic baseline* contains **20,009 canonical
rows**. Its catalog is bootstrapped once; a three-row delta is then published
while historical canonical-file access is blocked and is served through Q3.
This exceeds the former total 20,000-row guard, but is **not** an M2-scale test
or a resource claim for approximately 5.7 million rows. No qualified M2 data was
accessed or modified, and no historical archive was ingested.

Linux disposable-fixture suite: **1061 tests run, 14 skipped**; existing
unrelated ResourceWarnings remain. Windows validation remains pending.

The scoped-reader tests exercise calendar gap/holiday preservation, UDiFF date
observations, D21 request pinning, original versus incremental provenance,
saved/history execution, and both bounded and catalog-backed selections. The
holiday preservation check uses synthetic mocked calendar evidence; it is not
a validation against the qualified M2 package.

### Explicit existing-registry binding

Run `python -m serving.incremental_registry` with the existing complete
`--package`, `--registry`, `--state`, `--saved-state`, `--history-state`,
`--legacy-root` and `--udiff-root` arguments, followed by `bind`. The operation
validates the explicitly named registry and reports active generation and
accepted/staged counts. It neither initializes a missing registry nor chooses
among potential locations. A known prior location is necessary; an unknown or
ambiguous location requires user identification, not automatic replacement.

`tests/test_b5_registry_binding.py` uses disposable registries to cover explicit
legacy adoption, staged/published evidence validation, no historical canonical
reads, missing-binding detection and repair, conflicting locations, interruption,
and preservation of registry contents. It does not establish where any real
user registry is located.

`tests/test_b5_detached_delta.py` checks immutable-blob reuse, old-reader pins,
on-access row/evidence corruption, reference mismatch, inline-generation
migration with and without pending inputs, rollback/retry, missing old source
archives, and blocking historical canonical reads during migration. It does not
prove the remaining accumulated reference/derived/index structures scale to M2.

`tests/test_b5_detached_identity_groups.py` tests affected-only group access,
pinned unaffected groups, on-access corruption, format-2 migration with and
without pending deltas, rollback/retry, corrupt group identities and reference
validation. The identity groups and derived overrides are not yet sharded within
a single heavily updated identity.

`tests/test_b5_detached_overrides.py` covers detached override reuse, pinned
readers, selected corruption, explicit binding verification, format-3 migration
with and without pending inputs, rollback/retry, and unaffected baseline
identity continuity. It does not establish full delta-only scaling.

`tests/test_b5_ticker_delta.py` tests baseline/delta ticker-census parity with
a complete small synthetic fixture, normal publication without old delta blob or
historical canonical reads, pinned census behavior, format-4 migration and
rollback, and corruption checks. Migration tests emulate old generation formats
in disposable SQLite state; they do not use or prove behavior on qualified M2.

`tests/test_b5_index_overlay.py` covers selected index/count parity, ordinary
publication without composing or reading baseline canonical rows, pinned
readers, malformed overlays, and transactional format-5 migration with source
archives absent and corrupt flag evidence. Old formats are simulated in
disposable SQLite state; this is not an M2-scale resource validation.

`tests/test_b5_targeted_tickers.py` exercises actual selected-group publication
and readers with full baseline ticker-census access blocked after bootstrap,
miskeyed and corrupt groups, proof loss and explicit recovery, full verification,
and transactional format-6 migration. The proof bootstrap reads the compact
existing ticker census once; it does not read the qualified canonical rows.
