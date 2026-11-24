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
| D40 | `docs/architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md` | 2026-11-24 | EC-DEC-01..04 = APPROVED (PUBLISHED WITH DECLARED GAPS — see D40 §1.1/§8) | IIPS historical-serving extension authority: D23 serving extension; class-(4) ISIN/series/date index; initial M2/NSE_EQ/1D/RAW_UNADJUSTED scope; archive and D21 conflict exclusions. Personal-use single-user scope only (D40 §4). Acceptance EC-AC-01..05 NOT attested (D40 §8) |

**Standing gaps recorded in this register**

- The prepared IRR handoff artifact `docs/integration/artifacts/EQUICORE-D40-IIPS-SERVING-EXTENSION-PREPARED-2026-11-24.md` is **absent**; D40 carries the verbatim decision wording, conditions, and `EC-AC-01..05` text as **NOT RECOVERABLE — PENDING RESTORATION**.
- No `.github/workflows/` exists; this repository has **no CI**. Verification for published records is local (compile/unittest spot checks) and remote (`gh`) inspection.
- No implementation tracker file exists; the README durable-record index is the publication index (D40 §9.2–§9.3).
