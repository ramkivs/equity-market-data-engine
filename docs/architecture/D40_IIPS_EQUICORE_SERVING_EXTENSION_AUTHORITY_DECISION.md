# D40 — IIPS–EquiCore Headless Local Loopback Serving Extension Authority Decision (`D23` Extension) [PREPARED FOR `ramkivs/equity-market-data-engine`]

> **HANDOFF / PUBLICATION NOTICE (STRICT REPOSITORY OWNERSHIP):**
> This document is **PREPARED IN IRR (`ramkivs/iips-review-recovered`)** because the IRR-scoped sandbox session receives `HTTP 403` (`Permission denied`) when attempting to push to `ramkivs/equity-market-data-engine`.
> It is **NOT YET PUBLISHED** in `ramkivs/equity-market-data-engine`. To complete EquiCore-side durable publication, commit this text to `docs/architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md` on a branch of `ramkivs/equity-market-data-engine` and merge via PR.

---

## 1. Title, Identifier & Authoritative Ownership / Scope

**D40 (`EC-DEC-01` – `EC-DEC-04`)** — Explicit `D23` extension authority decision recording sole-owner approvals for EquiCore's headless local loopback HTTP serving interface (`serving.iips_serve`, `iips-equicore-historical/v1`) and rebuildable Class-(4) `(isin_normalized, series, business_date)` index for personal-use integration with IIPS (`ramkivs/iips-review-recovered`).

### 1.1 Explicit Ownership, Personal-Use, and Application Scope (Authoritative)

- **IIPS and EquiCore are local, single-user applications.**
- **Ramki is the sole owner and decision-maker for both applications.**
- **Both applications are strictly for personal use.**
- **The authorization is exclusively for personal-use integration between these applications.**
- **There is no production environment or production deployment requirement.**
- **No hosted, commercial, multi-user, or production deployment is authorized or required.**

No production-readiness gates, separate production-owner approvals, or multi-user deployment assumptions apply or may be introduced.

---

## 2. Status & Baseline

- **Owner Disposition:** **`EC-DEC-01` – `EC-DEC-04` = `APPROVED`** by **Ramki** (sole owner and decision-maker) on **2026-11-24**.
- **EquiCore Baseline Verified Read-Only:** `ramkivs/equity-market-data-engine` `origin/main` at `b79cf1d0` (`D23` `docs/architecture/D23_FIRST_RELEASE_SERVING_IMPLEMENTATION_AUTHORITY_DECISION.md`, `D14` `I5` qualified M2 package `i4-20261008-M2`, `2,462` NSE archives, `5,689,949` rows, `2016-09-20`..`2026-09-18`, manifest `e7c7e4c8...`, engine `d3269b73...`).
- **Governing Cross-Repo Inputs (IRR `main`):**
  - `IIPS-EQUICORE-REQUEST-RESPONSE-ARCHITECTURE-ASSESSMENT-2026-11-23.md` (Revision `1.1`)
  - `IIPS-EQUICORE-SERVING-AUTHORIZATION-PROPOSAL-2026-11-23.md`
  - `IIPS-EQUICORE-PA-APPROVAL-RECORD-2026-11-24.md`
- **Implementation Authorization Notice:** This governance approval record grants **no** code-execution authority by itself. Phase B implementation in `ramkivs/equity-market-data-engine` requires separate Phase B implementation authorization referencing this record and `D23`.

---

## 3. Approved Decisions (`EC-DEC-01` – `EC-DEC-04`)

| Decision ID | Decision Statement (Original Wording Preserved) | Binding Bounds & Conditions (Verbatim) | Status |
|---|---|---|---|
| **`EC-DEC-01`** | **Extend `D23` to authorize a headless, local loopback HTTP serving API (`serving.iips_serve`, `iips-equicore-historical/v1`)** | • Runs as a separate headless read-only Python 3 stdlib `ThreadingHTTPServer` entrypoint on `127.0.0.1:8614` (distinct from `src/ui/serve.py:8613`; `--bind 0.0.0.0` prohibited).
• Exposes only `GET /v1/health`, `POST /v1/historical/bars`, `POST /v1/historical/eod-observation`, `GET /v1/instruments/:isin/associations`, and `GET /v1/calendar`.
• Enforces mandatory `Authorization: Bearer <token>`, loopback `Host` header check, zero CORS headers, `Cache-Control: no-store`, and SHA-256 `responseDigest`. | **`APPROVED`** (2026-11-24) |
| **`EC-DEC-02`** | **Authorize the rebuildable Class-(4) `(isin_normalized, series, business_date)` index** | • Strictly `D16-07` Class-(4) derived state stored outside the M2 package (`--state` root; deleting it is never a data event and rebuild reproduces identical bytes).
• Indexes **only** rows with `isin_validity === 'VALID'` per `D05 §6.1` — the adopted exact-string upper/trim correlation-key rule — **read together with `D05 §5` (validity flags informational; non-gating); the `VALID`-only predicate originates from this record's `EC-DEC-02` and Clarification **C-1** (2026-11-24 addendum, §5), not from D05 (`BLANK` and invalid-ISIN rows never form cross-symbol correlation links).**
• Preserves `D05/1.0` verbatim `Decimal` values, `D05 §8` row provenance, and `nse_engine` (`d3269b73...`) immutability. | **`APPROVED`** (2026-11-24) |
| **`EC-DEC-03`** | **Lock initial serving scope to the qualified M2 baseline, `NSE_EQ`, daily EOD (`1D`), `RAW_UNADJUSTED`** | • Initial dataset is strictly the `I5`-qualified M2 baseline (`i4-20261008-M2`, `2,462` NSE archives, `2016-09-20`..`2026-09-18`).
• Rejects `BSE_EQ` (`422 UNSUPPORTED_EXCHANGE`), intraday `1m..1h` (`422 UNSUPPORTED_FREQUENCY`), and adjusted modes (`422 ADJUSTMENT_UNAVAILABLE`).
• Exposes `POST /v1/historical/eod-observation` strictly as `PINNED_GENERATION_EOD_SNAPSHOT` (`bitemporalKnowledgeAsOf: false`), not bitemporal `knownAsOf` PIT. | **`APPROVED`** (2026-11-24) |
| **`EC-DEC-04`** | **Confirm exclusions & `B5` boundary** | • Raw archive bytes stay excluded (`D16-08` Class 5).
• Post-M2 `B5` composite generations (`catalog-composite`) remain **out of initial serving scope** until `B5`/`B6` close; when later enabled, `D21` `CHANGED-CONFLICT-UNRESOLVED` quarantine (`D21 §18`) remains fail-closed (`409 D21_CONFLICT_HELD`). | **`APPROVED`** (2026-11-24) |

---

## 4. Binding Phase B Acceptance Criteria (`EC-AC-01` – `EC-AC-05`) & Non-Drift

1. **`EC-AC-01` (Security):** Missing/bad bearer token → `401`; non-loopback `Host` → `403`; `--bind 0.0.0.0` refused at startup; zero `Access-Control-Allow-Origin` headers.
2. **`EC-AC-02` (Identity & Invalid ISIN):** Invalid ISIN syntax → `400`; `BLANK`/invalid-ISIN rows excluded from ISIN index; overlapping symbol ambiguity → `409 IDENTITY_AMBIGUOUS`; sequential symbol renames returned with `observedSymbols[]`; `EQ`/`BE`/`BL` strictly isolated.
3. **`EC-AC-03` (Scope & EOD Semantics):** `BSE_EQ` → `422 UNSUPPORTED_EXCHANGE`; `1m..1h` → `422 UNSUPPORTED_FREQUENCY`; adjusted mode → `422 ADJUSTMENT_UNAVAILABLE`; `/v1/historical/eod-observation` stamps `PINNED_GENERATION_EOD_SNAPSHOT` & `bitemporalKnowledgeAsOf: false`.
4. **`EC-AC-04` (Calendar & Completeness):** Exact accounting across official holidays, `unexplainedCalendarDates[]` (e.g. `2024-11-20`, `2025-10-20`), `notRetrievedCalendarDates[]`, and `securityAbsentOnTradingDaysCount` (`tradingDaysWithArchive === returnedBarCount + securityAbsentOnTradingDaysCount`).
5. **`EC-AC-05` (Determinism & M2 Immutability):** Identical queries produce byte-identical JSON & `responseDigest`; deleting and rebuilding Class-(4) ISIN index produces identical index digest; M2 manifest digest `e7c7e4c8...` unchanged; Windows `M2` smoke queries pass.

**Non-Drift Preservation:** `D40` preserves `D14`, `D16`, `D21`, `D22`, `D23` §15–§16 (canonical/engine safety & D21 fail-closed constraints), `D05`, `D08`, `D12`, `src/ui/serve.py:8613`, and Windows M2 custody unchanged.

---

## 5. Addendum C-1 — Owner Clarification of `EC-DEC-02` (published 2026-11-24)

### 5.1 Approval authority, date and scope

This addendum records the **sole application owner's** approval of **Clarification C-1**, an interpretive clarification of `EC-DEC-02`, approved **2026-11-24**. IIPS and EquiCore remain local, single-user applications; **Ramki is the sole owner and decision-maker of both**; both applications are strictly for personal use; this clarification concerns **only their personal-use integration**. No production, hosted, commercial or multi-user deployment is authorized or required (restating §1.1). Publication channel: Arena PR **#7** (branch `arena/ddcaa938-equity-market-data-engine`), authorized by the owner to merge to `main` upon completion of the verification steps recorded in the PR; the merge commit is recorded by GitHub on merge (see PR #7 / `main` history). This addendum **grants no code-execution authority**: Phase B implementation and Phase C implementation remain subject to separate implementation authorization referencing this record (including this addendum) and D23. The evidence basis is the assessment record `docs/investigations/EQUICORE_D05_S5_EC_DEC_02_ISIN_INDEX_ELIGIBILITY_ASSESSMENT_2026-11-24.md` (ASI-1), whose technical findings were verified against D05, D16, D40 and the serving implementation at the time of drafting.

### 5.2 Original record preserved; scope of edits

The original D40 decision text and the `EC-DEC-01`..`EC-DEC-04` approvals are **preserved unamended**. `EC-AC-01`..`EC-AC-05` are **preserved verbatim** in §4. Exactly one in-place edit was made to the original record, authorized by the owner on 2026-11-24 (§5.6 citation correction). Nothing else in the original record is altered; any residual ambiguity in the original text is superseded by this addendum only to the extent stated here.

### 5.3 Owner decision (restated)

1. **D05 requires unconditional retention of canonical historical rows regardless of ISIN validity.**
2. **EC-DEC-02's `isin_validity == 'VALID'` predicate applies exclusively to membership in the derived Class-(4) `(isin_normalized, series, business_date)` correlation index.**
3. **Invalid and blank ISIN rows remain in the canonical dataset** and remain available through the applicable historical observation retrieval paths.
4. **Index exclusion must never cause deletion, rejection, reprocessing, de-ranking, general filtering or suppression of historical observations.**
5. **The VALID-only index supports ISIN identity correlation, not general historical observation retrieval.**
6. **Engine W2 non-blank ISIN keying remains unchanged.**
7. **D05 is not amended.**
8. **Citation correction:** D05 §6.1 denotes exact-string upper/trim ISIN correlation, read together with D05 §5; the VALID-only predicate originates from EC-DEC-02 and this clarification. (Applied in §3 and recorded in §5.6.)

### 5.4 C-1 as published (adopted clarification text)

> **1.** **Retention is unconditional.** No row of the qualified M2 baseline (`i4-20261008-M2`, `5,689,949` rows, `2,462` archives) is deleted, rejected, reprocessed, de-ranked, hidden, or rewritten by reason of its ISIN validity classification or blankness. All canonical rows remain retained in class (1) and are carried into serving outputs with their D05 §5 flags and `isin_validity` verbatim.
>
> **2.** **Index membership predicate (exclusive).** The derived Class-(4) `(isin_normalized, series, business_date)` correlation index contains a row **iff** `isin_validity == 'VALID'` — i.e. the normalized (upper/trim) ISIN is non-blank, exactly 12 characters, starts with `IN`, matches `IN[A-Z0-9]{9}[0-9]`, and its ISO 6166 mod-10 check digit equals the 12th digit (the engine rule, `src/nse_engine/rows.py:37-118`). No other condition is added; no canonical row is altered to satisfy it.
>
> **3.** **Scope of the predicate.** It applies **exclusively** to membership in this derived index. It authorizes **no** deletion, rejection, re-processing, rewrite, general serving filter, de-ranking, or suppression of any canonical row anywhere; class-(4) state other than this index's membership set is unaffected; deletion/rebuild of this index is never a data event (D16-07); on disagreement, classes (1)/(2)/(3) win and the index is rebuilt (D16-07 conflict rule).
>
> **4.** **Observation retrieval is validity-agnostic.** Historical-observation retrieval (`/v1/historical/bars`, `/v1/historical/eod-observation`, and any symbol/series/date path) returns **all** as-published rows for the requested scope regardless of ISIN validity; flagged/BLANK rows appear with their flags. The VALID-only predicate is **never** applied to observation retrieval.
>
> **5.** **Correlation evidence only.** The index is used solely for ISIN↔ISIN correlation evidence (`/v1/instruments/:isin/associations`; identity basis `isin_correlation_key_upper_trim`). Requests naming an ISIN whose rows are all BLANK/invalid yield an empty correlation with basis note `exact-observation`-only — never a fabricated identity, never `is_valid_isin_format: false` (the field is true-or-null only), never a 409 ambiguity verdict derived from invalid links. Invalid/BLANK rows remain individually retrievable as exact observations.
>
> **6.** **Engine scope unchanged.** The W2 identity/association build (`nse_engine/identity.py`) continues to key **all non-blank** rows regardless of validity (D05 §5), with blank rows recorded as `UnkeyedRowGroup`. This clarification changes nothing in the engine; the two correlation scopes (engine: non-blank; Phase-B index: VALID-only) coexist deliberately and are documented as such.
>
> **7.** **Citation correction.** `EC-DEC-02`'s reference to `D05 §6.1` denotes the adopted exact-string upper/trim correlation-key rule (D05 §6 item 1) read together with D05 §5's non-gating hard rule; the `VALID` predicate is this clarification's binding definition, not a D05 requirement. **D05 is not amended**; F1 (ISIN is never promoted to exchange-authoritative identity) stands unchanged.
>
> **8.** **Failure semantics.** Any path found applying the predicate beyond item 2's membership set is a defect: fail closed, report, no silent truncation; the index is rebuilt, never patched in place.

### 5.5 Binding Phase B acceptance framework — `EC-AC-B1`..`EC-AC-B10` (A1–A10 as approved, with refinements)

These ten conditions are the **binding Phase B acceptance framework** referenced by this record. They refine the proposed A1–A10 exactly as follows; all are testable and checkable against the implementation at Phase B closure; none of them is satisfied or attested by this addendum.

- **A1 (refined).** M2 baseline identity pinned and recorded **completely**: package `i4-20261008-M2`; manifest SHA-256 **`e7c7e4c8…`** (full digest `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`); **4,948 files**; **21,119,807,344** bytes; **5,689,949** rows; **12** partitions; composite run identity `9609c7fc…` (`9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d`); engine tool SHA-256 `d3269b73…` (`d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9`); runner SHA-256 `f3ebf624…` (`f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a`); **and the full engine and runner commit hashes** that produced/qualify the served instance. Build/serve refuses to proceed on any mismatch (fail closed); the pin and any change to it are recorded in the Phase B evidence.
- **A2.** **M2 package and provenance verification.** Pre/post serving byte-identity of the class-(1) package (manifest digest unchanged); provenance blocks (D05 §8) present and verbatim; no write path to M2 exists anywhere in the serving codebase; `verify --package`-equivalent evidence attached to Phase B closure.
- **A3.** **Canonical row-retention and count parity.** Canonical row counts before/after serving are identical per partition; rows with `isin_validity` ∈ {`INVALID_CHECKDIGIT`, `INVALID_LEN`, `INVALID_PREFIX`, `INVALID_CHARSET`, `BLANK`} remain present in exactly the same counts; flags and `isin_validity` are carried verbatim in served payloads; `raw_line` never appears; zero rows are dropped, de-ranked or merged.
- **A4 (refined).** **VALID-only membership enforced exclusively at the Class-(4) index boundary.** The `isin_validity == 'VALID'` predicate may appear only in the class-(4) ISIN-index build and nowhere else. **Executable tests must prove that historical observation retrieval preserves `INVALID_CHECKDIGIT`, `INVALID_LEN` and `BLANK` observations** (count parity and content parity against the package). A grep/lint conformance check may supplement these tests but **may not replace them**.
- **A5.** **Deterministic index generation and rebuild.** Two independent index builds produce byte-identical canonical-JSON output and identical SHA-256 digest; deleting and rebuilding the class-(4) index from M2 reproduces the identical digest; membership predicate, upper/trim normalization, `(series, business_date)` grain, and canonical-JSON (D05 §9) key ordering/separators are unit-tested; stale-package refusal remains effective.
- **A6.** **ISIN association semantics.** `/v1/instruments/:isin/associations` for an ISIN whose observations are all BLANK/invalid returns an **empty correlation** with `is_valid_isin_format` ∈ {true, null} (never false); sequential renames surface only through `observedSymbols[]` from VALID-linked observations; `EQ`/`BE`/`BL` series are strictly isolated; `409 IDENTITY_AMBIGUOUS` is returned only for overlapping ranges **across VALID-linked observations**; no rename inference is ever derived from invalid/blank links.
- **A7.** **Quality visibility / Q8 census parity.** The flag census (`isin_invalid_checkdigit`, `isin_invalid_length`) served through Q8 equals the engine-computed census; excluding flagged rows from the correlation index does not alter, suppress, or de-count them anywhere.
- **A8.** **Response digest reproducibility.** Identical requests produce byte-identical JSON bodies and identical `responseDigest` (SHA-256); `/v1/historical/eod-observation` stamps `PINNED_GENERATION_EOD_SNAPSHOT` and `bitemporalKnowledgeAsOf: false` under all conditions (unchanged from EC-DEC-03).
- **A9.** **Windows M2 smoke testing.** Against the live Windows `M2` package, smoke queries pass, including at least one Legacy instrument known to carry an invalid check digit; its flagged rows are returned with flags — not omitted, not de-ranked.
- **A10.** **No CI claim without authorization.** This repository has no `.github/workflows/`; unless separately authorized and added, no CI result may be claimed from Phase B; verification consists of recorded local/Windows evidence and remote `gh` inspection.

### 5.6 Citation correction applied (in-place, §3 EC-DEC-02 cell)

Original text: `Indexes **only** rows with \`isin_validity === 'VALID'\` per \`D05 §6.1\` (\`BLANK\` and invalid-ISIN rows never form cross-symbol correlation links).`

Text as corrected 2026-11-24 (this addendum's §3/§5.4(7)): `Indexes **only** rows with \`isin_validity === 'VALID'\` per \`D05 §6.1\` — the adopted exact-string upper/trim correlation-key rule — read together with \`D05 §5\` (validity flags informational; non-gating); the \`VALID\`-only predicate originates from this record's \`EC-DEC-02\` and Clarification **C-1** (2026-11-24 addendum, §5), not from D05 (\`BLANK\` and invalid-ISIN rows never form cross-symbol correlation links).`

No other wording in the original record was altered; `EC-AC-01`..`EC-AC-05` are byte-identical to their 2026-11-24 publication.

### 5.7 Non-drift preservation (restated with effect)

This addendum modifies none of `D14`, `D16`, `D21`, `D22`, `D23` §15–§16, `D05`, `D08`, `D12`, `src/ui/serve.py:8613`, `nse_engine`, or Windows M2 custody. **D05 is not amended.** The architecture register (`EQUI_CORE_ARCHITECTURE_DECISION_REGISTER.md`) and README durable-record index are updated to reference this addendum; ASI-1 is marked adopted. The ownership boundary (§1.1 / §5.1) continues to bind this record and all successors.

### 5.8 Record relationship and cross-references

- Original record: `docs/architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md` §§1–4 (this file).
- Evidence basis: `docs/investigations/EQUICORE_D05_S5_EC_DEC_02_ISIN_INDEX_ELIGIBILITY_ASSESSMENT_2026-11-24.md` (ASI-1) — findings adopted by this clarification; not amended by it.
- Related: D05 §5, §6.1, §3.1, §12 (F1); D16-07 (class (4)); D16-08; D16-09; D16-10 (Q3/Q5/Q8); D23 §15–§19; D21 §18 (unchanged, not touched by Phase B); `src/nse_engine/rows.py:37-118`, `src/nse_engine/identity.py`, `src/nse_engine/contract.py:236`, `src/serving/index.py`, `src/serving/symbols.py`, `src/serving/query.py`, `src/serving/quality.py`.
- This addendum is part of the D40 record; it does not create a new decision record and does not renumber any existing record.
