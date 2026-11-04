\# EquiCore

**Equity Market Data Intelligence & Infrastructure Engine**

Authoritative repository: `https://github.com/ramkivs/equity-market-data-engine.git`.



10-year NSE historical market-data engine for Legacy Bhavcopy and CM-UDiFF archives, with governed normalization, security identity, equity analytics, and historical query capabilities.



\## Environment Boundary



This project operates across three separate environments.



\### Windows



Windows is the raw-data custody and full-dataset execution environment.



It has access to the local NSE historical archives:



\- `C:\\IIPS\_Data\\NSE\_Legacy\_Acquisition\\archives`

\- `C:\\IIPS\_Data\\NSE\_CM\_UDiFF\_10Y\\archives`



Windows is responsible for:



\- Raw archive custody

\- Full-dataset inventory and profiling

\- Full-dataset processing when required

\- Generation of evidence artifacts and controlled data extracts



\### GitHub



GitHub is the authoritative durable project record.



It contains:



\- Evidence artifacts

\- Specifications

\- Architecture and design decisions

\- Source-code

\- Tests

\- Development documentation

\- Controlled fixtures and extracts



The raw NSE archive files are not stored in this repository.



\### Arena



Arena is the investigation and development environment.



Arena does not have direct access to the Windows filesystem or the raw NSE archives.



Arena receives data and evidence through the Git repository and other explicitly controlled artifacts.



Arena is responsible for:



\- Read-only investigation

\- Architecture and specification development

\- Engine development

\- Automated testing

\- Documentation

\- Durable publication through Git



\### Raw NSE Archives



The raw NSE archives remain outside Git.



They are treated as source data and must not be modified by the engine development workflow.



\## Current Evidence Baseline



The initial archive inventory established:



\- Total files: 2,462

\- Legacy files: 1,919

\- UDiFF files: 543

\- Inventory errors: 0

\- Duplicate dates: 0

\- Duplicate checksums: 0

\- Schema variants: 3

\- Coverage: 2016-09-20 through 2026-09-18



The inventory was generated read-only.



\## Development Principle



The project follows a controlled evidence-to-development workflow:



Windows raw archives

→ evidence / controlled extracts

→ GitHub authoritative repository

→ Arena investigation and development

→ GitHub durable publication



No environment should assume direct filesystem access to another environment.



\## Status



Current stage:



\*\*D01 evidence baseline complete; D02 identity/eligibility investigation complete; D03 COMPLETE — Windows corpus execution published (evidence/d03/windows_run @ origin/main 094105b, 39 files, determinism PASS, post-run reconciliation in D03 record §15); D04 canonical-model decision investigation record committed; DEC-1/DEC-2 documented (D04B record + evidence/d04/); D05 CANONICAL MODEL SPECIFICATION authored (docs/specs/D05_CANONICAL_MODEL_SPEC.md); D06 DECISION RECORDED — D05 §13 ADOPTED set ADOPTED as governed canonical-model contract, DEC-1 master acquisition DEFERRED, ENGINE IMPLEMENTATION NOT AUTHORIZED (docs/investigations/D06_CANONICAL_MODEL_ADOPTION_DECISION.md); D07 CHARTER + IMPLEMENTATION AUTHORIZATION RECORDED — engine implementation AUTHORIZED within D07 scope (non-production), DEC-1 remains DEFERRED, D7.4 pointer restatement + D7.5 backfill applied (docs/investigations/D07_GATE_DEFINITION_AND_IMPLEMENTATION_AUTHORIZATION.md) — implementation proceeds only after D07 record is durable and remote-verified; D08 I3 OUTPUT/PERSISTENCE CONTRACT DECISION RECORDED (Ramki authorization 2026-10-06) — MD-02/MD-03 ACCEPT WITH AMENDMENT, MD-04–MD-07 and MD-10 ACCEPT, MD-11 I4 retained-output ACCEPT, MD-13 I4 execution AUTHORIZED (not executed), MD-14 publication exercised, MD-15 I3 closure conditional on remote verification; DOC-01 D05 §12 reference correction applied; STORAGE TECHNOLOGY = UNDECIDED; MD-08/MD-09 deferred by sequencing; MD-12 withhold / not authorized; DEC-1 (MD-16) deferred unchanged; I4 traceability claim = content-level under the adopted D05/W1 contract; D12 I4 CLOSURE RECORDED — I4 M2 execution complete (i4-20261008-M2: 2,462 members, 5,689,949 rows, 12 partitions, 0 gating divergences; D11 evidence durable at origin/main 1507b740, package sha256 8e78fcc8…), R6 replay qualification PASS (D11 gate; K1/K2/K3/G6; R0–R7), I4 = CLOSED / DURABLE / REMOTELY VERIFIED upon remote verification of this publication (D12 §9); I5 = 10-YEAR FULL QUALIFICATION ESTABLISHED AND DETERMINED (D14 authority decision — qualification determination PASS over the completed i4-20261008-M2 10-year result: completeness/integrity/determinism/memory/evidence/reconciliation criteria all met from durable, re-proven evidence; determination-only gate, no execution scope; I5 = CLOSED / DURABLE / REMOTELY VERIFIED upon remote verification of this publication (D14 §10); I5 authorizes no serving/API/UI/persistence/production/semantic or execution work).\*\*



- D02 investigation record: `docs/investigations/D02_EQUITY_ELIGIBILITY_AND_IDENTITY.md`
- D02 derived evidence artifacts: `evidence/identity/` (regenerate read-only with `python3 evidence/identity/d02_derivation.py`)
- D03 investigation record: `docs/investigations/D03_BOUNDED_FIXTURE_INVESTIGATION.md`
- D03 fixture tool (read-only, deterministic, selftested): `tools/d03_fixture_scan/` — Windows runbook in D03 record §12
- D03 Arena-side partial evidence: `evidence/d03/` (regenerate read-only with `python3 evidence/d03/d03_arena_evidence.py`)
- D03 Windows run evidence (durable on main): `evidence/d03/windows_run/` (RUN_INFO + MANIFEST; verify: `python tools/d03_fixture_scan/d03_fixtures.py verify --out evidence/d03/windows_run` — see D03 §15 CRLF packaging note)
- D04 investigation record (decision inputs only; no schema adopted): `docs/investigations/D04_CANONICAL_MODEL_DECISION_INVESTIGATION.md`
- D04B DEC-1/DEC-2 investigation record (official documentation + security-master scoping): `docs/investigations/D04B_DEC12_DOCUMENTATION_AND_MASTER_INVESTIGATION.md`; machine-readable evidence `evidence/d04/` (deterministic: `python3 evidence/d04/d04_arena_synthesis.py`)
- D05 canonical model specification (specification-only; ADOPTED/DEFERRED/OPEN/NON-ASSUMPTION tagged): `docs/specs/D05_CANONICAL_MODEL_SPEC.md`
- D06 canonical-model adoption decision record (D06 = ACCEPTED/ADOPTED; DEC-1 = DEFERRED; engine gate closed): `docs/investigations/D06_CANONICAL_MODEL_ADOPTION_DECISION.md`
- D07 gate charter + implementation authorization record (D07 decisions 1-4; pointer restatement D7.4; D06 §14 backfill D7.5; scope boundary §13; first work item W1 §14): `docs/investigations/D07_GATE_DEFINITION_AND_IMPLEMENTATION_AUTHORIZATION.md`
- D08 I3 output/persistence contract decision record (I3 contract closure + publication; MD-02/MD-03 accepted with amendment; MD-04–MD-07 and MD-10 accepted; MD-11/MD-13 I4 authorization — not executed; MD-14 publication exercised; MD-15 closure conditional on remote verification; DOC-01 D05 §12 reference correction applied; STORAGE TECHNOLOGY = UNDECIDED; MD-08/MD-09 deferred by sequencing; MD-12 withheld; DEC-1 unchanged): `docs/investigations/D08_I3_OUTPUT_PERSISTENCE_CONTRACT_DECISION.md`
- D12 I4 closure decision record (I4 = CLOSED / DURABLE / REMOTELY VERIFIED upon remote verification of this publication; cites D11 remote reconciliation ACCEPT, origin/main 1507b740, evidence/D11_REPLAY_QUALIFICATION_20261009/ package sha256 8e78fcc8…, R6 verdict, K1/K2/K3/G6, R0–R7, MD-11 #7, C.7 findings carried without suppression; publishes D11 + I4 replay/E2E records, the replay-qualification gate + tests, G6-corrected runner tests; aligns engine/runner bytes with the executed M2 revision d3269b73…/f3ebf624…): `docs/investigations/D12_I4_CLOSURE_DECISION.md`
- D13 post-I4 decision-input investigation record (investigation only: decided-fact inventory, A–H analysis of MD-08/MD-09/MD-12/MD-17, D07 §9 nine OPEN semantics, DEC-1/MD-16, W1-DIV-1, the three calendar dates, the monitor null anomaly, and the i4-20261007/M2/replay roots; decision matrix, dependency graph, open/deferred register, evidence requirements, and proposed decision questions for the future next-gate authority decision; **NO NEW GATE IS DEFINED OR AUTHORIZED BY THIS INVESTIGATION**; I5 remains UNDEFINED): `docs/investigations/D13_POST_I4_DECISION_INPUT_INVESTIGATION.md`
- D14 I5 authority decision record (I5 = 10-year full qualification ESTABLISHED and DETERMINED: original roadmap intent reconciled with repository state via repository evidence only; I5 constituted as a determination-only qualification gate over the completed i4-20261008-M2 10-year result (corpus 2016-09-20 through 2026-09-18, 2,462 members) — qualification determination PASS against the already-decided, already-passed criteria (completeness, verify/integrity, R6 byte-exact determinism, M2 memory ≤ 2.5 GB criterion, MD-11/E1–E10 evidence, D11 reconciliation ACCEPT with C.7 carried without suppression); content-level traceability boundary (D08 §4.3); NO execution scope; MD-08/MD-09/MD-12/MD-16/MD-17, D07 §9 nine OPEN semantics, DEC-1, W1-DIV-1, and the three calendar dates all remain exactly as carried; I5 authorizes no serving/API/UI/persistence/production/semantic/execution work): `docs/investigations/D14_I5_AUTHORITY_DECISION_10YEAR_FULL_QUALIFICATION.md`
- Post-I5 serving / incremental ingestion / product architecture investigation record (read-only investigation against the verified product & serving architecture intent artifact (TARGET/INTENT ONLY, SHA-256 7e4a14f4…): archive discovery/identity/fingerprint/dedup contracts EXISTS and reusable (D01 inventory sha256, PF-10/11/12, INPUT_MANIFEST per-archive records); per-archive processing mechanics reusable but composition is corpus-scale; durable serving store + serving/query layer + UI ABSENT (MD-12 UNDECIDED); provenance/evidence rich at file level; 13 unresolved decisions enumerated; requalification and changed-content policies deliberately undecided; NO implementation authorized; disposition: INVESTIGATION COMPLETE — ARCHITECTURE DECISION REQUIRED): `docs/investigations/POST_I5_SERVING_INCREMENTAL_PRODUCT_ARCHITECTURE_INVESTIGATION.md`
- Product & serving architecture intent artifact (TARGET / INTENT ONLY — prevents architectural/product drift; single-user personal-use scope with explicit non-goals; NOT implementation, persistence, API, UI, or production authority; must be explicitly adopted/modified/superseded by a future governance decision before substantive post-I5 implementation): `docs/product/HISTORICAL_ENGINE_PRODUCT_AND_SERVING_ARCHITECTURE_INTENT.md`



Canonical model finalized via D06 (§13-ADOPTED; F1–F17 and all OPEN/DEFERRED items carried forward unchanged). Equity eligibility governance and security-master scoping remain DEFERRED (D06 Decision B); engine implementation was authorized at gate D07 within its explicit scope (non-production; fail-closed on OPEN semantics) — see `docs/investigations/D07_GATE_DEFINITION_AND_IMPLEMENTATION_AUTHORIZATION.md`. D02 recommends D03 proceed as a fixtures-and-decisions gate against the Windows-side fixture requests in the D02 record (section 9).

