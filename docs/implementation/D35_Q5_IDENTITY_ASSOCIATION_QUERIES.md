# D35 — Q5 identity/association queries (serving slice)

**Status:** implementation record (Q5 of the D16-10 query categories; follows D34/Q4)
**Authority:** D23 §17 item 1 (Q1–Q10 read-only serving/query layer over the qualified M2
baseline); D16-10 Q5; D22 §6 Q5 classification ("READY BY EXISTING CONTRACT"); D23 §8 item 1
(identity/association data MAY be exposed). D24 §18 vertical-slice conventions (read-only,
deterministic canonical JSON, fail-closed, byte identity of the package, no new index/store).
**Publication scope:** session branch only. No main promotion. No Q6.

---

## 1. Contract investigation (authoritative records only)

### 1.1 The Q5 line (D16-10, verbatim)

> **Q5** identity/association query ("related records" = the instrument's dated-association
> intervals; no overlay aggregation — D05).

D22 §6 classifies Q5 **READY BY EXISTING CONTRACT** with contract basis:
`w2/associations.jsonl`; D05 §3.3 append-only intervals; overlay restriction D05 §3.5.

### 1.2 The governed data record (D05 §3.2/§3.3, verified against engine emission)

`w2/associations.jsonl` is a class-(2) derived output (runner-written via the engine's single
identity stream; `tools/i4_runner/i4_runner.py::_write_w2`): **one `SecurityIdentity` document
per line, in engine-governed order — ascending normalized-ISIN key**
(`AssociationAccumulator.identity_keys()`: "Active identity keys … sorted").

`SecurityIdentity` (D05 §3.2; `nse_engine.identity.SecurityIdentity.to_dict()`) — 10 keys:

| key | semantics |
|---|---|
| `security_id` | the D05 §6.1 adopted correlation key: normalized ISIN (upper-trim). **NOT** exchange-authoritative identity (D05 §3.2 NON-ASSUMPTION; carried in `non_promotion_note`). |
| `identity_basis` | constant `"isin_correlation_key_upper_trim"` (D05 §6.1 [ADOPTED]). |
| `isin_list` | normally one; list of as-published ISIN strings for the identity. |
| `is_valid_isin_format` | `true` only when **every** observation is classified VALID; otherwise `null` (UNDETERMINED — never asserted false; the flag is informational and never gates or de-keys, D05 §5). |
| `first_observed` / `last_observed` | min/max business date over the identity's keyed observations (ISO dates). |
| `associations` | the dated-association intervals (below). |
| `provenance` | deduplicated D05 §8 provenance blocks for the identity's observations. |
| `observations` | governed census facts (associations, observation_rows, same_day_parallel_states, series_observed, symbols_observed, isin_validity_values). |
| `non_promotion_note` | the standing D05 §3.2 non-assumption text (correlation key never promoted; boundary continuity OPEN; master-snapshot/ETF-register DEC-1-deferred). |

`DatedAssociation` (D05 §3.3; `nse_engine.identity.DatedAssociation.to_dict()`) — 10 keys:
`association_type` (present set: **only** `corpus-observed`; master-snapshot /
etf-register-membership are DEC-1-deferred and absent), `contributing_rows`
(`{business_date, line_number, member_name}` traceability), `interval_basis`
(constant `observed-range` — the interval is the **observed first/last presence, not official
validity**), `observations`, `observed_from` / `observed_to` (ISO dates), `provenance`,
`security_id`, `series`, `symbol`.

**Interval rule (governed):** one `DatedAssociation` per contiguous run of an identical
(symbol, series) state in `(business_date, line_number)` observation order; a state recurring
after a different state starts a new association (EQ → BE → EQ yields three dated rows;
append-only — transitions are events, never mutations of an existing interval).

**Overlay restriction (D05 §3.5):** overlay-series rows (observed set `BL, BO, T0, IT, IL`) are
excluded at engine ingestion and appear in **no** identity document — "no overlay aggregation"
is enforced upstream; Q5 neither aggregates nor exposes overlay observations.

**Unkeyed rows:** a blank (post-normalization) ISIN yields no identity document (grouped as
`blank_isin_no_correlation_key` in `w2/identity_summary.json`, which Q5 does not read). An
ISIN that is invalid as a format is still a correlation key (informational flag only).

**Directionality/reciprocity:** none is defined. A `DatedAssociation` is a dated observation
that the identity carried (symbol, series); there is no inverse relation record and no
governed "from the instrument to the identity" table — the lookup below is an exact-match
scan over the published documents, not a relationship inference.

**Duplicates:** the engine emits exactly one document per active key (sorted, unique); a file
with a repeated `security_id` is a contract violation (corruption), not a governed state.

**Missing/null semantics:** absent file = a legitimate package state (no derived identities —
served as explicitly absent, never fabricated, never an error). A document's
`is_valid_isin_format: null` = UNDETERMINED (distinct from `true`). No other nullable serving
fields exist in the Q5 view.

### 1.3 Serving-boundary conventions carried over (D24/D30a/D31/D32/D33/D34)

* read-only, no writes into the package, no serving state, no new index entries (the serving
  index format `serving-index/1.2` is unchanged — it indexes class-(1) row files; Q5's file
  set is fixed: the single class-(2) file, already recognized by `serving.baseline`'s
  durability-class table);
* a class-(2) file **absent** is legitimate; a class-(2) file **present but malformed** fails
  closed (Q8's `w2/unresolved.jsonl` precedent);
* records served **as published, in file order** (deterministic; the engine's sorted-key order
  is preserved — never re-sorted, never normalized);
* exact-value selectors only (no case/whitespace folding, no expression language, no
  aliasing — D23 §10);
* malformed input or malformed record → fail closed with the exact check id, no partial
  output, existing CLI error envelope and exit codes (0 ok / 2 usage-query failure /
  3 baseline-index failure).

### 1.4 Conflicts / unresolved issues

None. D05, D16-10, D22 §6, D23 and the engine emission code agree. One documented boundary:
the D16-10 Q5 line's parenthetical ("related records" = the instrument's dated-association
intervals) and the word "identity" together cover exactly the two selector forms below; no
other Q5 capability is evidenced in any governing record.

---

## 2. Proposed Q5 slice (recorded BEFORE code)

**Smallest coherent slice of the Q5 category:** one query function, two governed selector
forms (identity lookup + instrument "related records"), both of which the single D16-10 Q5
line covers, served from `w2/associations.jsonl` with zero new state.

### 2.1 Selectors and parameters

`query_associations(baseline, index, security_id=None, symbol=None, series=None)`

| mode | request | semantics |
|---|---|---|
| **identity** | `security_id` only | the identity document for that exact as-published key (all of its dated-association intervals, as published). |
| **instrument** | `symbol` **and** `series` (both, exact as-published strings) | the instrument's dated-association intervals ("related records"): every `DatedAssociation` in every identity document whose (symbol, series) matches exactly, across identities. |
| **combined** | all three | the identity's dated-association intervals restricted to that (symbol, series) — the single contract-supported composition (Q4 AND precedent). |

Validation (fail closed, before anything is served):

* at least one selector required;
* each supplied selector must be a string;
* exactly one of `symbol`/`series` supplied → error (an instrument is an ordered pair; a
  single field is not a Q5 selector — no single-field inference is invented);
* `index` is accepted for boundary consistency (every Q path takes the verified index) but
  supplies no Q5 file narrowing — the Q5 file set is fixed and the index format is unchanged.

### 2.2 Output schema

API: `Tuple[dict, ...]`. Each served element is the **published document plus a `serving`
envelope** (Q3 precedent — the record exactly as stored, nothing re-shaped):

* identity mode — the 10-key `SecurityIdentity` document as published, plus
  `serving = {query: "Q5-association", security_id, source_file: "w2/associations.jsonl",
  source_line_number}`;
* instrument mode (incl. combined) — the matching 10-key `DatedAssociation` document as
  published (it carries its own `security_id`), plus
  `serving = {query: "Q5-association", symbol, series, security_id (of the containing
  identity), source_file, source_line_number}` (combined mode also repeats the requested
  `security_id` — it is the same value).

`source_line_number` is the 1-based line of the containing identity document in
`w2/associations.jsonl` (the document, not the association — the file is one document per
line).

CLI envelope: `{"query": "Q5-association", "security_id": <str|null>, "symbol": <str|null>,
"series": <str|null>, "associations_present": <bool>, "record_count": <int>,
"records": [...]}`.

### 2.3 Ordering

File order, always: identity documents in the engine's sorted-key order, associations in the
published (observation-run) order within each document. Never re-sorted by the query.

### 2.4 Absent / unknown / missing-data behavior

* **absent file** → legitimate: empty result, `associations_present: false` (CLI); never an
  error, never fabricated;
* **unknown `security_id`** → empty result (valid — exactly like Q3's unknown instrument);
* **unknown (symbol, series)** → empty result;
* **present file, zero documents** → empty result with `associations_present: true` (the
  absent-vs-empty distinction is served, matching Q8's `present` convention);
* `is_valid_isin_format: null` served as `null` (UNDETERMINED) — never coerced to `false`
  and never dropped.

### 2.5 Fail-closed behavior

Malformed selectors (2.1) → `QueryError("query-input")`. A **present**
`w2/associations.jsonl` that is malformed fails closed with
`QueryError("associations-scan")` (line-numbered detail), including: unparseable JSON line;
line not an object; missing/duplicate/unknown top-level key (exact 10-key set, both levels —
10 identity keys, 10 association keys; nested provenance 13-key set and contributing-row
3-key set); non-string `security_id`/`symbol`/`series`; non-ISO `observed_from`/`observed_to`;
`association_type` outside the present set; `interval_basis != "observed-range"`;
`identity_basis != "isin_correlation_key_upper_trim"`; `is_valid_isin_format` outside
{`true`, `null`}; empty `isin_list` or non-string entries; an association whose
`security_id` differs from its containing identity (corruption); duplicate identity
`security_id` (the engine emits one per key). **No partial output is ever produced** — the
file is parsed and validated before a result is returned; the CLI prints only the existing
JSON error envelope and exits 2.

Pinned schema constants are literals in `serving/query.py` with the contract citation (the
serving layer does not import `nse_engine`, per the D24 boundary).

### 2.6 Implementation boundaries (A–E per the task)

* **A read-only:** streams `w2/associations.jsonl`; no mutation; no new store; no canonical
  write-path change; no new class-(4) state.
* **B contract fidelity:** governed identifiers only (normalized-ISIN `security_id`, as
  published); no normalization/guessing/aliasing/inference of relationships; absent ≠
  explicit; published duplicate/ordering semantics preserved (file order; one document per
  key enforced, not repaired).
* **C deterministic canonical JSON:** CLI via the existing `_print_json` (sorted keys,
  indent 2, `allow_nan=False`); API results are plain published dicts.
* **D fail-closed:** as in 2.5, using the existing `QueryError` envelope and exit codes.
* **E no regression:** Q1/Q2/Q3/Q4/Q7/Q8/Q9/Q10, baseline/manifest/index verification, and
  package immutability untouched; serving-index format unchanged (1.2).

### 2.7 CLI surface

`query` subcommand gains `--identity KEY` (identity selector) and
`--instrument-symbol SYM` / `--instrument-series SER` (instrument selector; both or neither —
one alone is a usage error, exit 2). Q5 is the fifth mutually exclusive query mode
(Q3 positional `symbol series`, Q2 `--from/--to`, Q4 `--field`, Q7 `--file/--line`);
"exactly one mode" is extended to five. New flag dests avoid the Q3 positional dests
(`symbol`/`series` are untouched).

### 2.8 Fixture extension (contract-supported only)

`tests/serving_fixtures.py` adds `w2/associations.jsonl` to the synthetic package by feeding
the fixture's **actual engine-built canonical rows** (`build.rows`, from the same
`build_canonical` call that writes the row files) through the **engine's own**
`AssociationAccumulator` (default observed overlay exclusion) in member build order, and
serializing each yielded document with `canonical_json` — the engine's writer convention.
The fixture therefore contains the engine's own W2 output over its own synthetic rows: no
hand-crafted identity, no invented relationship, no data modification. Expected result
(5 identity documents / 6 associations; verified in tests):

* `INE000000006` — TATA CONSULTANCY legacy 2016-01-04 row (invalid-check-digit ISIN kept as
  key, `is_valid_isin_format: null`), 1 association;
* `INE002A01018` — RELIANCE, **2 associations** (the EQ→…→EQ run rule): `RELIANCE/EQ`
  2016-01-04…2017-02-06, then `500325/EQ` 2024-03-05 (UDiff numeric listing symbol),
  `is_valid_isin_format: true`;
* `INE009A01021` — INFY, 1 association;
* `INE123` — TATA CONSULTANCY legacy 2016-01-05 row (invalid-length ISIN kept as key,
  `null` validity), 1 association;
* `INE467B01029` — TATA CONSULTANCY UDiff row, 1 association, `true` validity;
* WIPRO rows (blank ISIN) — unkeyed, **no document** (exercises the unkeyed boundary).

### 2.9 Expected tests (task 16-item list mapping)

`tests/test_serving_associations.py` (focused) + one `D24_M2_ROOT`-gated real-baseline leg in
`tests/test_serving_m2_integration.py`:

1. valid identity lookup (document + published fields, incl. non-promotion note);
2. valid instrument association lookup (dated interval, observed_from/to, contributing rows);
3. multiple records/relationships (multi-association identity; same instrument across
   multiple identities; combined mode intersection);
4. unknown identity → empty (not an error);
5. missing optional identity data (`is_valid_isin_format: null` served as `null`);
6. absent file vs present-but-empty file (`associations_present` distinction);
7. duplicates + governed semantics (duplicate `security_id` → fail closed; association/
   identity key mismatch → fail closed);
8. directionality: none is defined or invented (documented; no inverse selector exists);
9. malformed records (non-object line; wrong key set; bad ISO date; foreign association
   type; false validity flag) → fail closed with line context;
10. invalid params (no selector; single-field instrument; non-string selectors);
11. fail-closed no partial output (failure mid-file serves nothing; CLI exit 2, error
    envelope only);
12. deterministic ordering (file order preserved; two runs byte-identical);
13. canonical-JSON CLI output (re-parse + byte-repeat identity);
14. byte identity of the package after a successful Q5;
15. byte identity of the package after a failed Q5;
16. Q1–Q10 regression (full suite; fixture gains `w2/` — all prior slices unaffected).

Gated leg (real M2, Windows-held; skipped ≠ passed): serving-behavior assertions only —
`w2/associations.jsonl` present in the qualified package; identity lookup by the first
published key returns that key's document; instrument lookup by a published (symbol, series)
returns only matching intervals; no served association carries an overlay series (D05 §3.5);
determinism. No corpus counts assumed; no re-qualification.

### 2.10 Remaining Q5 scope (documented, not implemented here)

* the `w2/identity_summary.json` surface (totals, unkeyed groups, overlay-row exclusion
  counts) — a summary view, not part of the D16-10 Q5 query line;
* any overlay-series query capability — D05 §3.5 forbids aggregation and the engine excludes
  overlay rows; there is nothing contract-supported to serve;
* master-snapshot / ETF-register association types — DEC-1-deferred, absent from the
  qualified baseline; no path is invented for them;
* UI/transport rendering and saved-query persistence (D16-10 E2) — separate authorization
  items, out of scope.

---

## 3. Results

### 3.1 What was implemented (matches §2; no drift)

* `src/serving/query.py` — `ASSOCIATIONS_QUERY_ID` / `ASSOCIATIONS_FILE`, the
  pinned schema constants (10 identity keys, 10 association keys, 13 provenance
  keys, 3 contributing-row keys; `identity_basis` = `isin_correlation_key_upper_trim`,
  `interval_basis` = `observed-range`, present association types = `corpus-observed`
  only, `is_valid_isin_format` ∈ {true, null}), `parse_associations`
  (absent → None legitimate; present-malformed → fail closed, line-numbered;
  duplicate `security_id` and association/identity key mismatch fail closed),
  and `query_associations` (identity / instrument / combined modes; exact-value
  selectors; unknown → empty; file order preserved; single pass via the
  `documents` sentinel parameter).
* `src/serving/cli.py` — `--identity KEY`, `--instrument-symbol SYMBOL`,
  `--instrument-series SERIES` on the `query` subcommand; Q5 is the fifth
  mutually exclusive mode; half-pair is a usage error (exit 2); envelope
  `{query, security_id, symbol, series, associations_present, record_count,
  records}`; existing error envelope and exit codes unchanged.
* `src/serving/__init__.py` — exports `ASSOCIATIONS_QUERY_ID`,
  `ASSOCIATIONS_FILE`, `parse_associations`, `query_associations`; module
  boundary statement extended with the Q5 line.
* `tests/serving_fixtures.py` — the fixture package now carries
  `w2/associations.jsonl`: the engine's own `AssociationAccumulator`
  (default observed-overlay exclusion) over the fixture's actual
  `build_canonical` rows, serialized with `canonical_json` per line (the
  runner's writer convention). No hand-crafted identity, no data modification.
* `tests/test_serving_associations.py` — 35 focused tests (task 16-item list,
  §2.9).
* `tests/test_serving_m2_integration.py` — one `D24_M2_ROOT`-gated
  real-baseline leg (`test_q5_associations_over_real_baseline`): serving
  behavior only (first published key lookup, published-pair instrument
  lookup, no overlay series served, determinism); skipped ≠ passed.

### 3.2 Test results (actual)

* Focused: `python3 -m unittest tests.test_serving_associations` — **Ran 35
  OK** (0.3 s).
* CLI smoke (real CLI over the fixture): identity lookup 1 record (2
  intervals); instrument lookup TCS/EQ 2 records (INE000000006, INE123);
  half-pair → exit 2; no mode → exit 2 (message now lists all five modes).
* Full suite: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` —
  **Ran 666 OK (skipped=11)**. Prior baseline 630 (skipped=10); +35 focused +
  1 gated leg. All 11 skips are the D24_M2_ROOT-gated real-baseline legs
  (10 prior + the new Q5 leg) — PENDING baseline provisioning, never passed.
* Fixture W2 facts (engine-produced, verified by the tests): 5 documents /
  6 intervals — INE000000006 (null validity), INE002A01018 (2 intervals:
  RELIANCE/EQ 2016-01-04…2017-02-06 then 500325/EQ 2024-03-05), INE009A01021,
  INE123 (null validity), INE467B01029; WIPRO unkeyed (no document).
* Package byte identity after success and after failure: asserted
  (`test_package_byte_identity_after_success_and_failure`).
* Index unchanged: rebuild byte-identical; `w2/associations.jsonl` not an
  index entry (`test_index_is_unchanged_by_q5`).

### 3.3 Changed files (one bounded commit)

| file | role |
|---|---|
| `src/serving/query.py` | Q5 query + pinned schema + fail-closed parse |
| `src/serving/cli.py` | Q5 CLI mode (flags, dispatch, envelope) |
| `src/serving/__init__.py` | exports + boundary statement |
| `tests/serving_fixtures.py` | engine-produced `w2/associations.jsonl` in the fixture |
| `tests/test_serving_associations.py` | 35 focused Q5 tests (new) |
| `tests/test_serving_m2_integration.py` | 1 gated real-baseline leg |
| `docs/implementation/D35_Q5_IDENTITY_ASSOCIATION_QUERIES.md` | this record (new) |

### 3.4 Boundaries confirmed

* Read-only over the baseline; no new store, no class-(4) state, no index
  format change (serving-index/1.2 untouched); no canonical write-path
  change; package byte-identical after success and failure.
* No relationship inference, no aliasing/normalization, no overlay
  aggregation (D05 §3.5), no invented fallbacks for absent records;
  absent ≠ explicit served throughout.
* Q1/Q2/Q3/Q4/Q7/Q8/Q9/Q10 and all verification paths: full-suite green.
* No Q6, no saved-query/history, no UI/transport, no product E2E, no main
  promotion. STOP after this task.
