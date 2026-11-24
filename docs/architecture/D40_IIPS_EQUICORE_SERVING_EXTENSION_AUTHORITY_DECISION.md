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
• Indexes **only** rows with `isin_validity === 'VALID'` per `D05 §6.1` (`BLANK` and invalid-ISIN rows never form cross-symbol correlation links).
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
