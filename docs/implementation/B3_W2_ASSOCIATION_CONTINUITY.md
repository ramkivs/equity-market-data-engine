# B3 — versioned W2 trading-symbol associations

## Contract and compatibility

`serving.w2_continuity` is an additive association generator over qualified
canonical row evidence. It produces `w2-trading-symbol-associations/1.0`;
it does **not** alter the D05/1.0 canonical model, the existing W2 runner,
`w2/associations.jsonl`, the engine fingerprint or qualified package bytes.
The existing W2 output and Q5 reader remain compatible and as published. This
new contract is a separate, opt-in derived output: it is not automatically
inserted into a run package and Q5 does not consume this new document.

Run against a verified package, directing output to a location **outside** the
package, for example:

```
PYTHONPATH=src python -m serving.w2_continuity --package /path/to/package > /path/outside/package/continuity.json
```

Use `--m2` only with the pinned qualified M2 package. The command opens the
baseline read-only and reads its canonical row files, not raw archives; it
writes only JSON to stdout. Shell redirection is chosen by the caller; the
application cannot protect a path opened by the shell before it starts. Do not
redirect into the package. The output includes the baseline manifest digest.

## Association rules

* Uses B2's source projection: legacy `SYMBOL` and UDiFF cash-equity `TckrSymb`;
  a UDiFF `FinInstrmId` remains the as-published listing value, never an identity.
* Uses B2's valid normalized ISIN and valid business date correlation, keyed
  additionally by series. This is a correlation key, not an assertion of legal
  or exchange-authoritative identity. Source ISIN, symbol, file, line and D05
  provenance are retained in each evidence record.
* Intervals are contiguous **observations**, not effective-date or continuous
  validity assertions. An unambiguous sequence records only observed endpoints
  of a symbol transition; it does not invent the date of a rename.
* B2's ticker reuse and conservative overlapping-observed-bounds checks mark
  affected identity/series groups `ambiguous`; evidence remains, but no
  continuity transition is asserted. Unobserved gaps and same-day parallel
  symbols are not resolved by assumption.
* Blank/invalid ISIN, invalid/missing date, missing series and unavailable ticker
  are retained in `unresolved`. W2's overlay series are explicitly recorded as
  excluded rather than merged. Conflicting groups are not merged with other
  securities.
* Ordering and JSON serialization are deterministic; duplicate source-file/line
  references fail closed. The generator creates no mutable state or migration.

The implementation currently accumulates the derived document in memory. It was
validated with synthetic data only; its resource requirements and behavior on
real M2 have not been established. Real-M2/Windows validation remains pending;
no claim of such execution is made.

## Validation and preservation

Linux sandbox: focused W2/B2/serving regressions — 104 tests passed. Full suite:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -t .`
— 932 tests passed, 14 `D24_M2_ROOT`-gated tests skipped; existing resource
warnings were emitted.

Synthetic tests cover real-shaped symbol changes, ticker reuse, touching date
boundaries, overlapping ranges, invalid and missing identity, overlays,
determinism and replay, raw values and source lineage. A qualified synthetic
fixture's original W2 output was read before and after generation and all
package files were compared byte-for-byte; CLI output replayed byte-identically
from an external working directory. No real M2 files were accessed or modified,
so real Windows baseline integrity was not independently reverified here. No
historical archive re-ingestion or requalification was performed.
