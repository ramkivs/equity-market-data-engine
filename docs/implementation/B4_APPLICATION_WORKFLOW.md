# B4 — application correctness and bounded continuity workflow

B4 is additive to the published B1–B3 work. No canonical D05/1.0 fields,
qualified W2 documents, saved/history formats, or serving-index format are
rewritten. No M2 package, archive, or historical evidence was regenerated.

## Application corrections

* DEF-04 / DEF-11: Inspector chips are actual markup, while all source values
  and the actual `units_provenance_note` are escaped. A missing note is
  unavailable, not a substituted unit claim.
* DEF-05: `EQ (all)` is exact `series=EQ`, including legacy rows whose segment
  is absent. `CM segment` is exact `segment=CM`. The FO, Debt, Currency and
  Reliable Only presets are disabled: this repository does not establish the
  requested exact mappings/classification for those controls. No inference is
  made from a series code to an exchange segment.
* DEF-06: D01 `series_counts` is presented as published series codes. Archive
  filters use individual codes. The canonical-data action uses a series filter
  only for an archive with exactly one code; it is not a filter by archive.
* DEF-07: Explorer's summary shows loading, Q1 failure and retry, and updates
  after an asynchronous Dashboard load finishes. DEF-08A error containment and
  DEF-08B page exclusivity remain covered by their existing behavioral tests.
* DEF-13: both `python -m ui` and `python -m ui.serve` use the same entry point;
  subprocess tests start each against a disposable synthetic package and call
  its HTTP status endpoint.

## B3 integration and explicit limitation

Q5 CLI, saved/history dispatch and UI now expose a `continuity` availability
record with the version and baseline manifest digest. For packages with a
validated serving-index row count at most 20,000, Q5 automatically derives the
B3 view from canonical rows, with a second hard streaming row-count limit. It
caches one package's derived groups in process and exposes per-identity/series
observed interval summaries, ambiguity and transitions in `serving.continuity`.
These are additive serving annotations: original W2 records and interval fields
remain unchanged. The Inspector displays continuity availability and observed
summaries, not asserted validity periods. The complete evidence remains in the
B3 standalone output described in `B3_W2_ASSOCIATION_CONTINUITY.md`.

**The large qualified M2 workflow is not fully integrated.** B3 currently
retains all evidence in memory; automatic construction of its full document on
approximately 5.7 million rows has not been measured and could exhaust a local
laptop. If the index count exceeds the cap or is unknown, Q5 explicitly reports
`unavailable` and does not scan for B3; original Q5 continues to work. A
mismatched low count cannot bypass the streaming cap. Errors are reported as
`error`, not as empty successful continuity. No externally supplied JSON is
accepted as authoritative merely because it repeats a manifest digest. A
bounded, verifiable large-package generation/storage strategy and real-M2
resource validation remain necessary before claiming full integration there.
B2's existing symbol catalog behavior is unchanged and independent of this cap.

## Validation

* Focused UI, serving, saved, B2/B3, and workflow suite: 248 tests passed.
* Full `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -t . -q`:
  937 tests passed, 14 skipped. Existing unrelated ResourceWarnings remain.
* Synthetic package tests compare the Q5 summaries with B3 derivation, verify
  qualified package bytes and original W2 are unchanged, check limit handling,
  and exercise both module server invocations. JS VM tests exercise escaped
  Inspector/archive values, async Q1 failure/retry and the series action.
* These results do not assert real-M2 access or Windows filesystem validation;
  the latter remains pending B6.
