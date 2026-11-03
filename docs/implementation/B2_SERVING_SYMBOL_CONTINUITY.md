# B2 — serving trading-symbol continuity

## Scope and semantics

This serving-only projection leaves D05/1.0 and the qualified package intact.
For legacy rows the observed ticker is source `SYMBOL`; for UDiFF cash-equity
(`CM`/`STK`) rows it is source `TckrSymb`, carried by D05/1.0 as
`source_values.underlying_symbol`. In other UDiFF markets that field can be an
underlying rather than the instrument ticker, so the projection is unavailable.
The published `listing_symbol` (UDiFF `FinInstrmId`), original ISIN and all
source values and provenance are retained unmodified.

Q3 and Q4's `symbol` filter resolve exact observed ticker/series values to a
valid normalized ISIN correlation and include observed ticker changes for that
same ISIN and series. The ISIN is a correlation key, not a claim of exchange-
authoritative legal identity. Ticker reuse across multiple valid ISINs and
conflicting/overlapping observed ticker bounds for one identity and series
fail closed with `symbol-ambiguous`. Overlap detection is deliberately
conservative: bounds are observed first/last dates, not validity intervals;
an overlap can therefore be ambiguous even when intermediate days were not
observed. Blank, invalid or undated identities never establish a correlation;
exact observed matches remain separate and are labelled `exact-observation`.
When no ticker matches, the published `listing_symbol` remains an exact-match
selector, retaining numeric FinInstrmId saved-query behavior. A year restriction
filters returned rows after ambiguity is evaluated against the whole baseline.

Q2/Q3/Q4/Q7 expose a row-local `serving.trading_symbol` with observed/effective
value, source and status; Q3 and symbol-filtered Q4 additionally label selection
basis and, only for correlated rows, the ISIN correlation key. Q5 returns the
unchanged W2 published association entries for the resolved identity and
series, with separate source-observation annotations; invalid-ISIN associations
are included only as individually exact published-symbol matches, not linked.
Q5's observed bounds are not exchange validity intervals. The UI displays the
observed ticker alongside the canonical field in the inspector and uses the
projected ticker for related-record lookup. Saved-query definitions and formats
are unchanged and execute through the same query paths.

The catalog is derived in memory from verified canonical row files on first
symbol lookup, keyed by baseline manifest identity, and kept for the process;
no package or persisted index is modified. This preserves existing
`serving-index/1.2` compatibility and avoids a forced index rebuild. A fresh
process recomputes the catalog on its first symbol lookup; no archive ingestion
or W2 association generation is performed. This has not been measured against
real M2 and no performance assertion is made.

## Validation and limits

Linux sandbox: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest
 discover -s tests -t .` — 926 tests, OK, 14 `D24_M2_ROOT`-gated skips;
existing ResourceWarnings were emitted. Synthetic regressions exercise rename,
valid-ISIN correlation, reuse, overlapping bounds and shared boundaries,
blank/invalid/undated identity, Q3/Q4/Q5, Q7 row projection, numeric raw-ID
compatibility, saved Q3/Q4/Q5 execution and package-byte preservation.

The Windows M2 package was not accessed or modified. Its current integrity and
real-M2 behavior of this change were not verified here; Windows integration
and visual evidence remain for B6. `W2` association generation is unchanged and
its own continuity work remains B3. A ticker outside supported cash-equity
source evidence, or an ambiguous identity, is not fabricated or silently
joined.
