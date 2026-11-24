# D40 ↔ D05 §5 / EC-DEC-02 — ISIN Index Eligibility: Evidence-Based Assessment & Proposed Owner Clarification

**Date:** 2026-11-24
**Type:** Decision-input / technical-governance assessment. **This record grants no authority.** It is prepared for the sole owner's approval; the proposed clarification (§6) takes effect only if the owner approves it, by publication as a D40 addendum or a successor decision record (proposed: D41).
**Task:** Resolve the relationship between D05 §5 (ISIN validity flags informational, non-gating) and D40 EC-DEC-02 (Class-(4) `(isin_normalized, series, business_date)` index over `VALID` ISIN rows only).
**Repository:** `ramkivs/equity-market-data-engine`; branch `arena/ddcaa938-equity-market-data-engine`; baseline `origin/main` = `d0a329f` (PR #6 merged, D40 published).
**No code, tests, data, or engine artifacts were changed by this assessment.**

---

## 1. The two requirements, precisely

**D05 §5 — Validity flags [ADOPTED — non-gating]** (`docs/specs/D05_CANONICAL_MODEL_SPEC.md:144-160`):
- Invalid-checkdigit ISIN rows: Legacy era ~215,393 rows ≈ 5.4% (`:148`); invalid length: 1 row corpus-proven.
- **Hard rule (`:156`):** validity flags *"NEVER gate, filter, reject or de-rank a row for identity, eligibility, or aggregation purposes; ISIN validity is informational only [ADOPTED — this is the governing disposition for the legacy invalid-checkdigit population: keep, flag, never assume defect implies non-security]."*
- Quarantine applies **only** to structural parse failures; quarantined raw lines remain in L1 evidence.

**D05 §3.1** (`:59`): `security_isin` stored **verbatim**; normalization for matching = uppercase+strip only; *"Validity is a flag (§5), never a gate."*

**D40 EC-DEC-02** (`docs/architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md`, §3 EC-DEC-02, §4 EC-AC-02):
> Authorize the rebuildable Class-(4) `(isin_normalized, series, business_date)` index … Indexes **only** rows with `isin_validity === 'VALID'` per `D05 §6.1` (`BLANK` and invalid-ISIN rows never form cross-symbol correlation links). Preserves `D05/1.0` verbatim `Decimal` values, `D05 §8` row provenance, and `nse_engine` (`d3269b73...`) immutability.

**EC-AC-02 (binding):** *"Invalid ISIN syntax → 400; BLANK/invalid-ISIN rows excluded from ISIN index; overlapping symbol ambiguity → 409 IDENTITY_AMBIGUOUS; sequential symbol renames returned with `observedSymbols[]`; EQ/BE/BL strictly isolated."*

**Apparent tension:** one document appears to forbid filtering on ISIN validity at all; the other appears to require a validity filter somewhere.

---

## 2. The actual architecture (what the code does today)

### 2.1 Engine (`src/nse_engine/`) — validity is computed, rows are kept
- `rows.py:104-118` — `isin_validity()` returns an informational classification only: `BLANK | VALID | INVALID_LEN | INVALID_PREFIX | INVALID_CHARSET | INVALID_CHECKDIGIT` (ISO 6166 mod-10 check-digit verification; non-IN prefixes rejected as INVALID_PREFIX).
- `rows.py:342-365` — flags `isin_invalid_checkdigit` / `isin_invalid_length` are emitted; the row is **retained** ("row retained", "validity never implies non-security").
- `rows.py:227-228` — canonical rows carry `isin_normalized` (upper/trim) and `isin_validity` as stored attributes.
- `contract.py:216-236` — `GATING_FLAG_NAMES = ()` — **"no flag gates anything. Deliberately empty."** `FLAG_SEVERITY` labels `isin_invalid_*` as `informational`.
- `identity.py:14-24, 282-360` — rows with **any non-blank ISIN are keyed for correlation regardless of validity flags** (D05 §5); blank-ISIN rows cannot key an identity and are recorded in `UnkeyedRowGroup` (with member, line numbers, reason) — **never dropped, never assigned a fabricated identity**.

### 2.2 Serving read model (`src/serving/`) — correlation is VALID-only; observations are not
- `symbols.py:33-41` — `_identity()`: **"Valid ISIN correlation only; invalid/blank values never create links."** Requires `isin_validity == "VALID"` + ISO date + non-blank `isin_normalized`.
- `symbols.py:101-109` — `row_matches()`: **"Unknown/invalid ISINs remain exact individual observations, not linked."** An invalid/blank-ISIN row still matches a query as an exact `(symbol, series)` observation — it is served.
- `symbols.py:111-115` — `resolution_metadata()`: correlated rows carry `basis = "valid-isin-correlation"`; otherwise `"exact-observation"`.
- `index.py` — `serving-index/1.2`: one linear read-only pass over class-(1) row files; collects per-file `(listing_symbol, series)` pairs, row counts, min/max `business_date`, and a global **flag census** (`D05 §5`); unparseable/contract-key-missing rows fail closed, **no row is filtered on validity**, deleted-index is never a data event; stale package identity refused.
- `query.py:103` — `IDENTITY_KEY_BASIS = "isin_correlation_key_upper_trim"  # D05 §6.1 adopted basis` (identity document basis; verified on load, `:523-532`).
- `query.py:62, 529-532, 710` — association documents carry `is_valid_isin_format` as `true`-or-`null` only — **never asserted `false`** (missing values surface as null, never as a negative identity claim).
- `query.py:214-283` — `query_instrument` (Q3): serves as-published rows by symbol/series; flags and `isin_validity` included verbatim (blank WIPRO row is served with `isin_validity="BLANK"` — test below).
- `quality.py:1-8` and `:72-92` — Q8 flag censuses read the §5 census; `"no flag gates anything — GATING_FLAG_NAMES is"` (empty) is carried into the view.

### 2.3 Tests and fixtures — the intended behavior is already exercised and green
- `tests/serving_fixtures.py:50-75` — fixtures deliberately contain: TCS 2016-01-04 (failing mod-10 check digit), TCS 2016-01-05 (invalid length, `"INE123"`), WIPRO 2016-01-04 (BLANK ISIN).
- `tests/test_flags_and_validity.py:74-110` — flag emitted, row retained, `test_isin_validity_never_gates_row_retention`.
- `tests/test_serving_query.py:139-150` — Q3 serves the BLANK-ISIN WIPRO row with `isin_validity == "BLANK"`; invalid-TCS rows remain queryable (`TCS` appears in the RELIANCE/TCS/WIPRO union tests).
- `tests/test_canonical_rows.py:67`; `tests/test_flags_and_validity.py:61-188` (`US0378331005` → `INVALID_PREFIX`; invalid checkdigit → row retained).
- Full serving suite at baseline: **327 tests OK, 14 skipped** (skips require the physical M2 package).

---

## 3. Answers to the six required questions

**Q1. Does D05 require invalid and blank ISIN rows to remain in the canonical dataset?**
**Yes, unconditionally.** D05 §3.1 stores `security_isin` verbatim, validity as flag only; D05 §5's hard rule prohibits gating/filtering/rejection/de-ranking for identity, eligibility or aggregation; quarantine is reserved for structural parse failures; §14 prohibits re-interpretation. M2 class (1) is immutable (D16-07). Engine tests enforce retention (`test_isin_validity_never_gates_row_retention`). Blank-ISIN rows remain as canonical rows with `isin_validity="BLANK"` (and, in the engine's identity build, as `UnkeyedRowGroup` entries); they are never deleted or rewritten.

**Q2. Does EC-DEC-02 restrict only membership in the derived Class-(4) index?**
**Yes — that is the only coherent reading of its own words and its context.** EC-DEC-02 authorizes "the rebuildable Class-(4) … index". The operative verb is **indexes**. Class (4) is by definition (D16-07) a *pure derivation of (1)+(2)+(3), rebuildable at any time, deletion never a data event, conflict rule (1)/(2)/(3) win*. The EC-DEC-02 bound "stored outside the M2 package (`--state` root; deleting it is never a data event and rebuild reproduces identical bytes)" confirms index-scoped authority — it cannot, and does not, touch the package. Nothing in EC-DEC-02 or EC-AC-02 authorizes deletion, rejection, re-processing, or general filtering of canonical rows. **At most, EC-DEC-02 narrows the membership predicate of one derived artifact.**

**Q3. Does excluding invalid ISIN rows from that index affect their availability through other historical query paths?**
**No — provided retrieval paths are implemented as in the current serving design (they must be; see §5-acceptance).** The paths do not route through a VALID-only predicate:
- Observation retrieval (Q3/date-range/filters; Phase-B `/v1/historical/bars`, `/v1/historical/eod-observation`): exact as-published `(symbol, series[, date])` matching; invalid/blank rows are served with flags verbatim (`symbols.py:101-109`; `tests/test_serving_query.py:139-150`).
- Associations / identity evidence (`query_associations`, Phase-B `/v1/instruments/:isin/associations`): this is where VALID-only applies — invalid/blank ISINs form no correlation links, carry no rename inference, no `observedSymbols[]` rename chains, no ambiguity verdicts based on linked identity; rows remain individually retrievable as exact observations (`resolution_metadata` basis `exact-observation`).
- Quality visibility: Q8 flag censuses surface `isin_invalid_checkdigit` counts (D16-10 Q8; `quality.py`) — exclusion from the index is never silent.
- Calendar/comparison paths (Q2/Q4/Q6): untouched by ISIN validity.
**Caveat (must be pinned in acceptance):** if any Phase-B endpoint implemented row retrieval by scanning the VALID-only ISIN index, ~5.4% of Legacy-era rows would vanish from observations — an availability loss, contradicting D05 §5 and EC-DEC-02's index-scoped reach. This must be expressly prohibited (§6/§7 A4).

**Q4. Can the proposed serving API preserve canonical row retention while using VALID-only ISIN correlation?**
**Yes — the exact hybrid is already implemented and tested in the current first-release slice** (`_identity()` VALID-only; `row_matches()` exact-observation fallback; flag census exposure). Applying the same pattern in Phase-B: bars/eod endpoints resolve the instrument scope from as-published rows (symbol/series/date), while the class-(4) ISIN index (a distinct derived store) is used solely for ISIN↔ISIN correlation evidence. Retention is fully preserved: every canonical row is retrievable; flags verbatim.

**Q5. Does any existing implementation or data transformation violate D05?**
**No.** Every ISIN-validity application in the tree is either (i) informational flag computation with row retention (engine), (ii) correlation-link formation scoped to VALID rows with unlinked exact-observation access preserved (serving `symbols.py`), or (iii) census/visibility (index.py, quality.py). `GATING_FLAG_NAMES == ()` is enforced by tests. The engine's identity build (non-blank keying, `identity.py`) is **broader** than EC-DEC-02's VALID-only scope — a permissible, documented divergence between canonical-adjacent W2 association building and the Phase-B derived index; the two must not be conflated (see §6). No transformation deletes, filters, or rewrites canonical bytes; M2 unchanged; serving read-only.
**One real defect found (citation only, not behavior):** D40 says "per `D05 §6.1`". See Q6.

**Q6. Is the EC-DEC-02 reference to D05 §6.1 accurate and correctly interpreted?**
**Imprecise and open to mis-reading, though directionally close.** D05 §6 item 1 (often cited "§6.1"; `D05:162-165`) adopts exactly this: *"`security_isin` is the only cross-format/cross-era correlation key; matching is exact-string after uppercase/trim."* That rule supports the **`isin_normalized` (upper/trim) key** used by the index. But §6.1 does **not** define `isin_validity`, the `VALID` enum, or any eligibility predicate — those come from the engine contract (`src/nse_engine/rows.py:37-118`; stored per §3.1) under D05 §5's informational-flag schema. Reading "VALID-only because §6.1" could be mis-interpreted as "D05 mandates VALID-only correlation" or "D05 prohibits ISIN use for flagged rows" — neither is true; **D05 itself never gates on validity.** Correct citation: *"per D05 §6.1 (upper/trim exact-string correlation key) together with D05 §5 (flags are informational); predicate is an owner-approved index-membership bound, not a D05 requirement."*

---

## 4. Impact on EquiCore indexing and serving (actual)

| Component | Impact of EC-DEC-02 as clarified | Action |
|---|---|---|
| M2 package (`i4-20261008-M2`) | **None.** Immutable class (1); manifest `e7c7e4c8…` unchanged; no rewrite | pin unchanged |
| `serving-index/1.2` (`src/serving/index.py`) | **None required.** `(symbol, series)` pairs + flag census already records invalid counts; delete/rebuild remains byte-identical | none |
| W2 identity / association build (`nse_engine/identity.py`) | **None.** Remains non-blank-keyed per D05 §5; Phase-B index diverges deliberately — must be documented | documentation only |
| New class-(4) `(isin_normalized, series, business_date)` index (Phase B) | Membership = `VALID` rows only. Deterministic rebuild; stored at `--state` root outside the package; digest-pinned; contains no values/never alters M2 | build under Phase B acceptance |
| Observation retrieval endpoints (Phase B `/v1/historical/bars`, `/v1/historical/eod-observation`) | **Must not use the index as the row source.** Return all as-published rows for the instrument scope incl. flagged/BLANK, flags verbatim | acceptance condition A4/A6 |
| Associations endpoint (`/v1/instruments/:isin/associations`) | VALID-link scope: invalid/BLANK ISIN → no correlation links, `is_valid_isin_format` null-or-true (never false), empty correlation result with basis note; exact-observation symbols still individually served | acceptance A5 |
| EQ/BE/BL series isolation, 409 ambiguity, `observedSymbols[]` | Unchanged; under VALID-only links, rename chains only asserted across VALID observations | acceptance per EC-AC-02 |
| Q8 quality views (`quality.py`, index flag census) | Flagged rows remain counted and visible; cannot be hidden by index exclusion | unchanged behavior; keep tests |
| Corpus coverage | ~215,393 Legacy rows (~5.4%) and BLANK/invalid-len rows absent from the *correlation index* only; full observation availability preserved | measure in Phase-B evidence |

---

## 5. Verdict on the owner's proposed interpretation

> **"All canonical historical rows remain retained regardless of ISIN validity. The VALID-only condition applies exclusively to membership in the derived ISIN/series/date correlation index. It does not authorize deletion, rejection, general filtering or loss of historical observations."**

**Technically correct and compatible with the existing architecture** — with the mandatory pinning below. It is also the only reading compatible with D05 §5, D16-07 (class (4)), D23 (withheld raw/engine changes), D40's own non-drift clause (preserves D05), and the already-implemented/tested serving slice. **It is insufficient as bare prose only in that it does not (a) define the exact VALID predicate, (b) prohibit routing observation retrieval through the index, (c) state what happens to W2 engine identity scope, or (d) correct the §6.1 citation.** The proposed clarification adds exactly those four pins — no more.

---

## 6. Proposed owner clarification (exact wording; publish as D40 addendum or D41 ONLY upon owner approval)

> **D40 EC-DEC-02 — Clarification C-1 (interpretive; no D05 amendment)**
>
> 1. **Retention is unconditional.** No row of the qualified M2 baseline (`i4-20261008-M2`, `5,689,949` rows, `2,462` archives) is deleted, rejected, reprocessed, de-ranked, hidden, or rewritten by reason of its ISIN validity classification or blankness. All canonical rows remain retained in class (1) and are carried into serving outputs with their D05 §5 flags and `isin_validity` verbatim.
> 2. **Index membership predicate (exclusive).** The derived Class-(4) `(isin_normalized, series, business_date)` correlation index contains a row **iff** `isin_validity == 'VALID'` — i.e. normalized (upper/trim) ISIN is non-blank, exactly 12 chars, starts with `IN`, matches `IN[A-Z0-9]{9}[0-9]`, and its ISO 6166 mod-10 check digit equals the 12th digit (the engine rule, `src/nse_engine/rows.py:37-118`). No other condition is added; no canonical row is altered to satisfy it.
> 3. **Scope of the predicate.** It applies **exclusively** to membership in this derived index. It authorizes **no** deletion, rejection, re-processing, rewrite, general serving filter, de-ranking, or suppression of any canonical row anywhere; class-(4) state other than this index's membership set is unaffected; deletion/rebuild of this index is never a data event (D16-07); on disagreement, (1)/(2)/(3) win and the index is rebuilt.
> 4. **Observation retrieval is validity-agnostic.** Historical-observation retrieval (`/v1/historical/bars`, `/v1/historical/eod-observation`, and any symbol/series/date path) returns **all** as-published rows for the requested scope regardless of ISIN validity; flagged/BLANK rows appear with their flags. The VALID-only predicate is **never** applied to observation retrieval.
> 5. **Correlation evidence only.** The index is used solely for ISIN↔ISIN correlation evidence (`/v1/instruments/:isin/associations`; identity basis `isin_correlation_key_upper_trim`). Requests naming an ISIN whose rows are all BLANK/invalid yield an empty correlation with basis note `exact-observation`-only — and **never** a fabricated identity, never `is_valid_isin_format: false` (true-or-null only), never a 409 ambiguity verdict derived from invalid links. Invalid/BLANK rows remain individually retrievable as exact observations.
> 6. **Engine scope unchanged.** The W2 identity/association build (`nse_engine/identity.py`) continues to key **all non-blank** rows regardless of validity (D05 §5), with blank rows recorded as `UnkeyedRowGroup`. This clarification changes nothing in the engine; the two correlation scopes (engine: non-blank; Phase-B index: VALID-only) coexist deliberately and are documented as such.
> 7. **Citation correction.** EC-DEC-02's "per `D05 §6.1`" denotes the adopted exact-string upper/trim correlation-key rule (D05 §6 item 1) together with D05 §5's non-gating hard rule; the `VALID` predicate is this clarification's binding definition, not a D05 requirement. D05 is **not amended**; F1 (ISIN is never promoted to exchange-authoritative identity) stands unchanged.
> 8. **Failure semantics.** Any path found applying the predicate beyond item 2's membership set is a defect: fail closed, report, no silent truncation; the index is rebuilt, never patched in place.

**Publication mechanics (owner's choice, needs one explicit approval):** (a) append C-1 to D40 as an addendum section in a follow-up commit/PR, or (b) publish as `docs/architecture/D41_EC_DEC_02_ISIN_INDEX_ELIGIBILITY_CLARIFICATION_DECISION.md` in the D23/D37/D40 house pattern. Either way, **no other record is reinterpreted.**

---

## 7. Is a D05 amendment, an EC-DEC-02 clarification, or both necessary?

**EC-DEC-02 clarification only; D05 amendment: NO (do not amend D05).**
- D05 §5's hard rule, §6.1's key rule, §3.1 verbatim storage, and F1 together already yield C-1's semantics; the defect is a **citation and an absence of pinning**, not a conflict of substance.
- Amending D05 would weaken a frozen, evidence-backed spec (215,393-row census) to fix a wording issue — exactly what D05 §12/§14 exist to prevent. If the owner nonetheless wants the enum to live in the spec, the minimal D05 change would be one informative sentence (not a rule change): *"`isin_validity` (engine-computed) is informational; a derived artifact may define a narrower membership predicate (e.g., VALID-only) without affecting retention."* — **not required**; recommended against unless the owner prefers it.
- EC-AC-02 ("BLANK/invalid-ISIN rows excluded from ISIN index") requires **no change** once C-1(2)/(4) pin the predicate to index membership and observation retrieval is excluded. The 400-on-invalid-syntax clause is unchanged. If the owner wants EC-AC-02 tightened to name the exact predicate, that is a D40 amendment line, adopted with the same approval act.

---

## 8. Exact acceptance conditions binding Phase B (owner sign-off requested)

> **A1.** M2 manifest digest pinned at `e7c7e4c8…` (and engine `d3269b73…`, runner `f3ebf624…`); build/serve refuses on mismatch; tampering fails closed.
> **A2.** Pre/post serving byte-identity of the class-(1) package; no write path to M2 anywhere in serving code.
> **A3.** Fixture suite: rows with `isin_validity` = `INVALID_CHECKDIGIT`, `INVALID_LEN`, `BLANK` **and** VALID all served by symbol/series/date retrieval with flags/`isin_validity` verbatim and `raw_line` absent; zero dropped rows (count parity pre/post).
> **A4.** The VALID predicate appears **only** in the class-(4) ISIN-index build; a grep/lint conformance test fails the build if the predicate (or `isin_validity`) guards any observation-retrieval path.
> **A5.** Index build: unit tests prove VALID-only membership, correct upper/trim normalization, series and `business_date` grain, byte-identical canonical-JSON digest across two builds, and identical digest after delete+rebuild from M2 (EC-AC-05 rebuild leg).
> **A6.** Associations: request for an ISIN with all-invalid/BLANK observations returns empty correlation, `is_valid_isin_format` ∈ {true, null} (never false), no rename/ambiguity inference; EQ/BE/BL never mixed; overlap → 409 `IDENTITY_AMBIGUOUS` only across VALID-linked observations.
> **A7.** Q8 views report the flag census including `isin_invalid_checkdigit` with counts identical to the engine census; excluding flagged rows from the index does not alter the census.
> **A8.** Determinism: identical request → byte-identical JSON and `responseDigest`; eod-observation stamps `PINNED_GENERATION_EOD_SNAPSHOT` / `bitemporalKnowledgeAsOf: false` (unchanged from EC-AC-03).
> **A9.** Windows M2 smoke (EC-AC-05): include at least one known legacy invalid-checkdigit-bearing instrument; fetch its bars for a business date and verify flagged rows are returned with flags — not omitted.
> **A10.** `.github/workflows` remains absent unless separately authorized; no CI claim may be made from this record.

---

## 9. Disposition & remaining steps

- **Interpretation:** EC-DEC-02 is index-membership-scoped; D05 §5 stands verbatim; no D05 amendment.
- **Action required:** owner approves/edits C-1 (§6) and choice of publication mechanics (addendum vs D41), and signs off on A1–A10.
- Until then: **no Phase B ISIN-index work may treat any row as unavailable**; any implementation returning fewer canonical rows than the package contains, by any path, is a defect against both D05 §5 and this assessment.
