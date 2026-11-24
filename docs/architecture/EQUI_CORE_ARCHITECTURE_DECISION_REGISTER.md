# EquiCore — Architecture Decision Register

**Purpose.** A single durable index of the EquiCore architecture / authority decision records. Created 2026-11-24 by the D40 publication because **no register existed before** (it was a documented absence, not a silently filled one). The register lists records; it does not amend them — each record governs its own scope and non-drift terms.

**Scope.** This register indexes decisions adopted for **EquiCore / this repository** (`ramkivs/equity-market-data-engine`). IIPS-side artifacts, records, and the IRR integration loop are **not** in this repository and are not listed here; they belong to the IIPS application and its own records.

**Maintaining rule.** When a new authority/decision record is published, add exactly one row here in the same change. Do not edit historical rows except to fix factual errors, and note any correction in the commit message. Absence of a row is not evidence a decision is absent — verify by search before assuming.

**Legend.** Status = the record's own declared decision status, abbreviated. `Authority-only` = governance record granting/withholding authority, no implementation by itself.

| ID | Record | Date | Status (as declared) | Type / key effect |
|---|---|---|---|---|
| D05 | `docs/specs/D05_CANONICAL_MODEL_SPEC.md` | 2026-09-12 (as recorded in D06 §2) | Specification ADOPTED (per D06) | Canonical model; ISIN = correlation key (never identity); values as published; non-gating flags |
| D14 | `docs/investigations/D14_I5_AUTHORITY_DECISION_10YEAR_FULL_QUALIFICATION.md` | 2026-10 (I5) | I5 = ESTABLISHED/DETERMINED (PASS) | 10-year full qualification determination over `i4-20261008-M2`; determination-only gate |
| D16 | `docs/architecture/POST_I5_SERVING_INCREMENTAL_PRODUCT_ARCHITECTURE_AUTHORITY_DECISION.md` | 2026-10-09 | ARCHITECTURE DECISION = ESTABLISHED; IMPLEMENTATION AUTHORITY = NOT GRANTED | Post-I5 serving/incremental/product architecture; classes (1)–(4); first-release scope D16-12; later-authority enumeration D16-13 |
| D19 | `docs/architecture/D19_CHANGED_CONTENT_CONTROLLED_TEST_AUTHORITY_DECISION.md` | 2026-10-09 | Authority to run a controlled test GRANTED (no implementation) | Narrow changed-content synthetic experiment authority |
| D21 | `docs/architecture/D21_D16_03A_CHANGED_CONTENT_DISPOSITION_AUTHORITY_DECISION.md` | 2026-10-09 | Permanent CHANGED disposition = explicit conflict + fail-closed hold | Prior accepted record authoritative; durable conflict record; per-instance resolution only via D21 §22; no implementation authority |
| D23 | `docs/architecture/D23_FIRST_RELEASE_SERVING_IMPLEMENTATION_AUTHORITY_DECISION.md` | 2026-10-09 | DECISION = GRANTED WITH EXPLICIT BOUNDARIES/CONDITIONS | First-release read-only serving + first-release UI over M2; class-(4) serving state; technology delegation; D16-13 item (1) discharged |
| D37 | `docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md` | 2026-10-10 | C1(a) APPROVED; C2(a) APPROVED | Class-(4) saved-query state boundary; explicit history recording |
| D40 | `docs/architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md` | 2026-11-24 | EC-DEC-01..04 = APPROVED (governs authority; **no code-execution authority granted**; Phase B requires separate authorization referencing this record and D23) | IIPS–EquiCore **headless local loopback HTTP serving extension** (`D23` extension): headless read-only loopback API `serving.iips_serve` / `iips-equicore-historical/v1` on `127.0.0.1:8614`; rebuildable Class-(4) `(isin_normalized, series, business_date)` index; initial scope locked to the I5-qualified M2 baseline `i4-20261008-M2` / `NSE_EQ` / `1D` / `RAW_UNADJUSTED`; raw-archive and B5 composite exclusions (D21 `CHANGED-CONFLICT-UNRESOLVED` fail-closed). Approvals by Ramki, sole owner, 2026-11-24; personal-use single-user only (§1.1 of the record). Binding Phase B acceptance criteria `EC-AC-01..05` published in the record; **NOT yet verified — implementation not started** |

**Decision inputs / assessments (no authority — listed for traceability)**

| ID | Record | Date | Status | Purpose |
|---|---|---|---|---|
| ASI-1 | `docs/investigations/EQUICORE_D05_S5_EC_DEC_02_ISIN_INDEX_ELIGIBILITY_ASSESSMENT_2026-11-24.md` | 2026-11-24 | **AWAITING OWNER APPROVAL — grants no authority** | Evidence-based assessment of D05 §5 vs D40 EC-DEC-02: confirms EC-DEC-02 restricts only Class-(4) index membership; proposes owner clarification C-1 (retention unconditional; VALID-only index predicate; observation retrieval validity-agnostic; engine correlation scope unchanged; EC-DEC-02 `§6.1` citation correction) and binding Phase B acceptance conditions A1–A10. Not adopted until the owner approves; **D05 remains unamended**. |

**Standing gaps recorded in this register**

- **D05 §5 ↔ EC-DEC-02 tension: assessed 2026-11-24** (ASI-1). Recommended interpretation: EC-DEC-02 is index-membership-only; all canonical rows remain retained and servable; **no D05 amendment necessary**; an interpretive clarification to D40 (C-1) or a successor record (proposed D41) is required **upon owner approval**; Phase B acceptance A1–A10 drafted in ASI-1, not yet binding.
- Prepared in IRR (`ramkivs/iips-review-recovered`) and published here by the owner via PR; the record's own handoff notice retains the original IRR publication instruction verbatim.
- **Phase B acceptance (`EC-AC-01`..`EC-AC-05`) is not attested.** The record grants no code-execution authority; `serving.iips_serve`, the ISIN/series/date index, and the loopback API do not exist yet. Acceptance evidence comes from the Phase B implementation + verification run under a separate Phase B authorization referencing this record and D23.
- The D05 §5 ↔ EC-DEC-02 tension (see previous bullet) must be resolved **as an owner act before or during Phase B**; until C-1 is approved, Phase B ISIN-index work may not treat any row as unavailable via any path.
- No `.github/workflows/` exists; this repository has **no CI**. Verification for published records is local (compile/unittest spot checks) and remote (`gh`) inspection.
- No implementation tracker file exists; the README durable-record index is the publication index.
