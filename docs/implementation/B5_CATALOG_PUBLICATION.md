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

* Catalog-backed generations currently store the baseline serving index, compact
  ticker census, and **all previously published incremental rows, projections,
  evidence and overrides** in one checksummed SQLite JSON payload. Each later
  publication loads, copies and serializes that accumulated delta snapshot.
  Only pending staged rows are revalidated and only affected W2/B3 identities
  are re-derived, but prior delta state is still rematerialized. Large or many
  accumulated deltas may exhaust memory or hit SQLite's single-value limit;
  this implementation has not established a scalable long-running lifecycle.
* The original qualified historical canonical baseline is not reread during
  catalog-backed publication. Q3/Q4 still scan candidate historical row files
  to serve a query, and Q5 streams the original W2 association file; these are
  query reads, not historical archive ingestion or publication replay.
* Existing unbound registry discovery and migration remain incomplete; a
  completely missing binding is still indistinguishable from never-bound state.
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

Linux disposable-fixture suite: **1023 tests run, 14 skipped**; existing
unrelated ResourceWarnings remain. Windows validation remains pending.

The scoped-reader tests exercise calendar gap/holiday preservation, UDiFF date
observations, D21 request pinning, original versus incremental provenance,
saved/history execution, and both bounded and catalog-backed selections. The
holiday preservation check uses synthetic mocked calendar evidence; it is not
a validation against the qualified M2 package.
