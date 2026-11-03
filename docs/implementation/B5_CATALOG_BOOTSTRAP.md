# B5 OW-10: catalog bootstrap and startup integrity increment

**B5 remains open.** This increment follows `224b862` and implements the first
of the approved stages. It does not implement delta-only publication: the
existing bounded composite publisher still rereads baseline rows, still has its
20,000-total-row limit, and does not consume this catalog. Q6, Q8 and Q9 still
fail closed for a selected composite. The registry migration described in the
later stage remains outstanding.

## One-time catalog

`serving.continuity_catalog` creates `continuity_catalog.sqlite3` in the
existing serving state directory, bound to the baseline manifest and the
existing serving index digests. Bootstrap requires the existing matching source
registry and the normal root-isolation checks. It never modifies the registry,
archives, or baseline. It streams the already-qualified canonical row files;
no entire row corpus is loaded into memory, and no raw line or source archive is
stored in the catalog. This is an explicit one-time operation, not part of
normal UI startup or delta publication.

Each catalog observation stores a minimal canonical projection: source file and
line, date, format, listing symbol, series, raw and normalized ISIN, validity,
UDiFF ticker/underlying field, segment and instrument type, and provenance.
The separately indexed W2 identity is normalized from the raw ISIN without
requiring validity; the B2 identity is present only when the existing B2
valid-ISIN/date rule accepts it. A compact ticker/series/identity/raw-symbol
census carries observed date bounds, allowing the existing ambiguity and reuse
rules to be evaluated without claiming exchange validity. The current bootstrap
is a baseline-only catalog: staged or published delta contributions are not yet
added to it.

The database is built at a unique temporary path, committed and fsynced, then
published with a no-replace hard link. A failed or interrupted build does not
replace an existing catalog. An abrupt process exit can leave a uniquely named
`.part` file, which is retained rather than silently deleted; it is not selected
as the active catalog. A subsequent bootstrap retries safely. Existing catalog
bootstrap calls perform a **full catalog** verification and do not reread
baseline rows. Windows filesystem behavior has not been validated.

From a shell using an already initialized registry and an existing serving index:

```text
PYTHONPATH=src python -m serving.incremental_registry \
  --package PACKAGE --registry REGISTRY --state STATE \
  --saved-state SAVED --history-state HISTORY \
  --legacy-root LEGACY --udiff-root UDIFF bootstrap
```

Add `--m2` only when operating on the user's actual pinned package; no such
operation was performed here. Replace `bootstrap` with `catalog-verify` to run
an explicit SQLite integrity check and a streaming check of observation and
ticker digests, indexed fields and counts without opening canonical row files.
The command checks the catalog's baseline/index binding. A corrupt or mismatched
catalog is rejected and never automatically replaced.

`open_catalog` checks metadata and binding only; it does **not** prove that all
catalog rows and indexes are intact. Catalog format 2 adds a digested compact
identity-group manifest and per-identity counts and digests. A targeted W2 or
B2 lookup validates that manifest and its selected observations under one SQLite
read snapshot, detecting missing, miskeyed or corrupted selected rows without
scanning unrelated historical observations. It reads all compact group
metadata, not all canonical rows. `catalog-verify` remains available for a full
catalog check. Checksums detect accidental corruption, not a hostile actor who
can rewrite the catalog and checksum metadata.

Existing format-1 catalogs are not discarded or silently replaced. Their
identity lookup fails closed until the `catalog-upgrade` operation verifies the
existing catalog and adds the group proofs in a single SQLite transaction. It
scans existing catalog projections once, not canonical rows or archives; an
interrupted upgrade rolls back. Use the same arguments shown above with
`catalog-upgrade` in place of `bootstrap`. The existing composite publisher and
application readers **do not yet use** these proofs or this catalog.

## Startup verification policy

Normal UI startup now opens the baseline in metadata/on-access mode: it checks
the manifest, manifest-to-partition-manifest consistency, completion marker,
run-record digest, pinned identity when supplied, file presence and root layout
without hashing historical canonical row files. A manifested file requested
through `Baseline.path()` is SHA-256 checked against its qualified manifest
entry before its path is returned; a missing or changed accessed file fails
closed. An untouched corrupt file can remain undetected until it is accessed.
The local path check and subsequent open are not a defense against a concurrent
hostile file swap.

`python -m serving verify --package PACKAGE [--m2]` retains full file hashing;
`--fast` reports `metadata-and-on-access` and labels the presence-only checks
rather than claiming all file digests passed. Registry `init` and a first
`bootstrap` perform full package verification; repeated bootstrap and ordinary
registry operations use metadata/on-access mode. If the serving index is
missing or stale, the existing UI setup/recovery
behavior can still build or rebuild it; the no-row-hashing startup proof below
uses an already-persisted valid index. This increment does not change direct
serving CLI commands other than explicit `verify` reporting.

## Validation and limits

`tests/test_b5_catalog_bootstrap.py` uses disposable fixtures only. It covers
catalog vs B2 census parity, UDiFF ticker and provenance, invalid ISIN's W2/B2
distinction, catalog reopen and idempotent reuse without baseline reads,
observation/index and ticker corruption, index-binding mismatch, a failed link
and abrupt process exit followed by retry, registry CLI bootstrap/verify, UI
startup with a persisted catalog and no canonical-file hashing, and rejection
of a changed historical row on actual UI access. Existing publication tests
remain unchanged. Qualified M2 was not accessed. No large-M2 resource or Windows
claim is made.

Linux disposable-fixture suite: **994 tests run, 14 skipped**. Existing
unrelated ResourceWarnings were emitted.
