# D40 Phase B — IIPS–EquiCore Headless Local Loopback Serving Extension: IMPLEMENTATION RECORD

## 1. Task identity and authority

**D40B** implements Phase B ("EQUICORE HISTORICAL SERVING IMPLEMENTATION") under the explicit
owner authorization granted **2026-11-24** (recorded in the tasking message): one-pass implementation,
verification and PR publication, referencing
[`D40`](../architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md) (as amended by
**Addendum C-1**, §5) and `D23`. `EC-DEC-01..04` are `APPROVED` (2026-11-24); `EC-DEC-02` is
clarified by C-1 (VALID-only membership exclusively at the Class-(4) index boundary; observation
retrieval validity-agnostic; D05 unamended).

- Repository: `ramkivs/equity-market-data-engine`; branch `arena/ddcaa938-equity-market-data-engine`
  based on `origin/main` at **`a4e298f529106cadaa8014918b4064b67f6f1f91`** (PR #7 merge of D40 +
  Addendum C-1; local base commit `aec7e75…`, an ancestor of `a4e298f`).
- Personal-use, single-user, IIPS+EquiCore loopback integration only (D40 §1.1). No production,
  hosted, commercial, or multi-user deployment is authorized or claimed.
- Raw-archive serving stays excluded (D40 EC-DEC-04 / D16-08; B5 `CHANGED-CONFLICT-UNRESOLVED`
  fail-closed). B5/B6 composites remain out of scope. Phase C is **not** authorized.
- **Honesty binding:** no acceptance criterion in this record is claimed beyond what the recorded
  evidence shows. Two evidence legs (Windows M2 smoke; M2-level byte-identity/rebuild) are
  **blocked** in this execution environment and are reported as such, not as passing.

## 2. What was implemented

### 2.1 Modules

| Module | New? | Role |
|---|---|---|
| `src/serving/iips_serve.py` | new | Headless read-only HTTP API `serving.iips_serve`, contract `iips-equicore-historical/v1`: `GET /v1/health`, `POST /v1/historical/bars`, `POST /v1/historical/eod-observation`, `GET /v1/instruments/:isin/associations`, `GET /v1/calendar`. Python 3 stdlib `ThreadingHTTPServer`; binds `127.0.0.1:8614` by default; **any non-loopback `--bind` (incl. `0.0.0.0`) is refused at startup (exit 2)**; mandatory `Authorization: Bearer <token>`; non-loopback `Host` → `403`; zero CORS headers ever; `Cache-Control: no-store` + `X-Content-Type-Options: nosniff`; canonical JSON (sorted keys, compact separators, LF); every response carries `responseDigest` (SHA-256 of the canonical body with the field stripped) and `X-Response-Digest` header; no wall clock anywhere — identical requests produce byte-identical bodies and digests. |
| `src/serving/isin_index.py` | new | The **Class-(4)** `(isin_normalized, series, business_date)` correlation index: exclusive membership predicate `isin_validity == 'VALID'` (D40 C-1 §5.4-2); stored outside the package at the caller `--state` root (D16-07); one linear read-only pass; canonical JSON + SHA-256 sidecar; constant-time verification on load; **stale-package refusal** (manifest/file-count/total-bytes/run-id vs `open_baseline`); CLI `python -m serving.isin_index build|info` pinned to `DEFAULT_M2_SPEC`. |
| `src/serving/symbols.py` | unchanged | `observed_trading_symbol(row)` reused verbatim (Legacy → `SYMBOL`/`listing_symbol`; UDiFF `CM`/`STK` → `TckrSymb`). No engine change; W2 non-blank keying unchanged. |
| `src/serving/baseline.py` | unchanged | `open_baseline` pin/verify path reused; `DEFAULT_M2_SPEC` is the A1 pin source (test-verified). |
| `src/serving/index.py` / `query.py` / `quality.py` | unchanged | Serving index (`serving-index/1.2`), calendar/completeness (`query_calendar`), Q8 census reused as-is; the ISIN index imports **no** observation-retrieval filtering. |
| `tests/test_serving_iips_serve.py` | new | 42 API/contract/security/determinism/association/retention/census-parity tests against the deterministic synthetic fixture (`tests/serving_fixtures.py`); never against, or represented as, M2. |

### 2.2 Behavior highlights (each bound to tests)

- **Observation retrieval is validity-agnostic.** `INVALID_CHECKDIGIT`, `INVALID_LEN`, `BLANK`
  (and every other validity) rows are served verbatim for the requested scope — same rows, same
  flags, same counts as the package (A4; `ObservationRetrievalTests`). `raw_line` is never served.
- **VALID-only membership exists in exactly one place**: `build_isin_index`'s `isin_validity == 'VALID'`
  test. No other module gates observation retrieval by validity. (A4)
- **Associations** (`/v1/instruments/:isin/associations`): empty correlation with `is_valid_isin_format: null`
  (never `false`) and `basis: "exact-observation-only"` for all-invalid/blank selectors; otherwise
  `basis: "isin_correlation_key_upper_trim"`, `observedSymbols[]` from VALID-linked observations only,
  EQ/BE/BL strictly isolated (series-keyed), `409 IDENTITY_AMBIGUOUS` only for overlapping observed
  ranges **of VALID-linked observations** (A6; `AssociationTests`, `HttpAmbiguityTests`).
- **Completeness accounting (`EC-AC-04`).** `bars`/`eod-observation` responses carry
  `completeness: {tradingDaysWithArchive, returnedBarCount, securityAbsentOnTradingDaysCount,
  unexplainedCalendarDates[], notRetrievedCalendarDates[], officialHolidayDates[], status}` — exactly
  satisfying `tradingDaysWithArchive === returnedBarCount + securityAbsentOnTradingDaysCount` on
  calendar-exact days (calendar validated by `query_calendar`, fail-closed). `/v1/calendar` returns the
  same accounting surface explicitly (`unexplainedCalendarDates[]`, `notRetrievedCalendarDates[]`,
  `officialHolidays[]`, `totals`, `days[]`). When the class-(2) calendar pair is absent, completeness is
  reported as `calendar-unavailable` with null counts — never fabricated.
- **EOD observation semantics.** `/v1/historical/eod-observation` stamps
  `pinnedGeneration: PINNED_GENERATION_EOD_SNAPSHOT` and `bitemporalKnowledgeAsOf: false`; byte-identical
  responses with SUT-pinned digest across repeated calls (A8/EC-AC-03/EC-AC-05).
- **Scope lock.** `BSE_EQ` → `422 UNSUPPORTED_EXCHANGE`; `1m..1h` → `422 UNSUPPORTED_FREQUENCY`;
  adjusted modes → `422 ADJUSTMENT_UNAVAILABLE`; malformed ISIN syntax → `400 INVALID_ISIN`; scope
  validation runs after presence/shape validation (400), before any serving (422).
- **Health.** `GET /v1/health` reports contract, service, version, package pin (manifest digest,
  run id, archive count), both index digests, `auth: bearer`; byte-reproducible (A8).
- **M2 immutability.** No serving module writes to the package; fixture-level pre/post manifest
  re-verification is test-executed (`RetentionAndQualityTests`). The class-(4) ISIN index is deleted
  and rebuilt to an identical digest in tests (`IndexDeterminismTests`).

## 3. Test results (this environment)

- `PYTHONPATH=src python3 -m unittest discover -s tests -t .` → **Ran 1190 tests — OK (skipped=14)**.
- `PYTHONPATH=src python3 -m unittest discover -s tests -t . -p "test_serving_*.py"` → **Ran 377 tests — OK (skipped=14)**.
- `tests/test_serving_iips_serve.py` alone → **Ran 50 tests — OK**.
- After the `IIPS_EQUICORE_TRANSPORT_TOKEN` authentication-contract correction: the full suite was
  re-run (1190 OK); new regression coverage: `TokenContractRegressionTests` (env var default,
  retired `IIPS_EQUI_CORE_TOKEN` not read, explicit `--token` precedence),
  `AuthEnforcementMatrixTests` (401 on **every** route incl. unknown routes, PUT/PATCH/DELETE/OPTIONS),
  `FailClosedStartupTests` (`load_state` refuses a non-M2 identity; full-package byte snapshot
  identical across serving + index builds).
- Pin fail-closed demonstrated live: `python3 -m serving.isin_index build --package <synthetic> …`
  refuses with `FAIL verify-07: … marker run_id 'D24-FIXTURE-RUN' != pinned 'i4-20261008-M2'` (exit 2) —
  the serving boundary cannot be opened against a non-M2 package, silently or otherwise.
- No `.github/workflows/` exists; **no CI was added or claimed** (A10); verification is local
  execution plus remote `gh` inspection only.
- 14 skipped tests are pre-existing skips unrelated to this change (present at baseline).

## 4. Windows M2 verification handoff (A9 and M2 legs of A2/A5/A7/EC-AC-05)

**Physical M2 verification must be performed by the owner on the local Windows machine.** The
complete, executable PowerShell runbook is a standalone document:
[`D40B_WINDOWS_M2_SMOKE_RUNBOOK.md`](D40B_WINDOWS_M2_SMOKE_RUNBOOK.md). It covers, with exact
commands, expected outputs and failure interpretations for every step:

1. M2 package and manifest verification (`serving verify --m2`) — §1.
2. Engine and runner revision verification — executed revision `8ade8372e150e541a52206baa377a02249a308f4`,
   tree `8e1557de766d4c952be7261c4f72aa743f81de0b`, fingerprints recomputed on-host — §2.
3. Class-(4) index build — §3. 4. Independent rebuild and digest comparison — §4.
5. Server startup on `127.0.0.1:8614` — §5. 6. Authentication verification using
   `IIPS_EQUICORE_TRANSPORT_TOKEN` — §6. 7. TCS historical observation retrieval — §7.
8. Verification that INVALID_CHECKDIGIT observations are returned with their validity flags — §7–§8.
9. Digest and completeness verification (EC-AC-04/A8) — §9. 10. Final provenance/acceptance
   evidence capture incl. before/after `verify --m2` — §10–§12.

It also specifies the evidence file location policy, the exact files the owner must return to
Arena, and the rule that raw row-level payloads are not committed to this public repository
(only JSON responses, logs and digests are returned).

**Current status: `PENDING OWNER WINDOWS VERIFICATION`.** A9 and the M2-dependent portions of A2,
A5, A7 and EC-AC-05 are **not** claimed or attested until the owner executes the runbook and the
returned evidence is verified in this record.

## 4A. Authentication configuration — discrepancy resolved

The original Phase B implementation and report used `IIPS_EQUICORE_TRANSPORT_TOKEN`; the approved transport
contract specifies **`IIPS_EQUICORE_TRANSPORT_TOKEN`**. No document in this repository establishes any
other name (D40 §3 EC-DEC-01 mandates mandatory bearer auth and does not name the variable), so the
contract name is authoritative and is now used consistently. Changes:

- `src/serving/iips_serve.py`: `--token` default now reads `IIPS_EQUICORE_TRANSPORT_TOKEN`
  exclusively; the retired name is **not read anywhere** (no silent dual-read); parser extracted to
  `build_parser()` for testability; startup failure message names the contract variable.
- Regression tests pin the behavior (`TokenContractRegressionTests`), pin authentication on every
  route (`AuthEnforcementMatrixTests`), and pin the fail-closed startup boundary
  (`FailClosedStartupTests`).
- All documentation (this record, the Windows runbook, startup instructions) uses
  `IIPS_EQUICORE_TRANSPORT_TOKEN`; residual `IIPS_EQUICORE_TRANSPORT_TOKEN` references: none (verified by
  repository-wide search at commit time).
- Behavior unchanged: bearer comparison is constant-time; auth is enforced before routing on every
  request including unknown routes and non-GET methods (401 precedes 404/405).

## 5. Acceptance matrix A1–A10 (D40 §5.5; refinements applied)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | M2 pin complete (package/manifest/file count/bytes/rows/partitions/composite/engine/runner hashes + full commit hashes); fail-closed | **MET for pin + derivation; bytes-leg still via Windows runbook Step 1–2 (A9 handoff)** | `test_m2_pin_constants_match_recorded_identity`; `test_fixture_package_fails_m2_pin`; CLI `verify-07` refusal. Pins (test-verified): manifest `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`; 4,948 files; 21,119,807,344 B; 5,689,949 rows; 12 partitions; composite `9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d`; engine `d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9` (nse-engine w2-1.0.0, 17 modules); runner `f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a` (i4-runner-1.0.0, 6 modules). **Executed revision re-derived and verified in-session 2026-11-24:** commit `8ade8372e150e541a52206baa377a02249a308f4` fetched from origin; `git rev-parse <commit>^{tree}` = `8e1557de766d4c952be7261c4f72aa743f81de0b`; fingerprints recomputed by materializing the tree (LF) and running the repo's own `tools/i4_runner/i4_identity.py` construction → engine **d3269b73…** ✓ and runner **f3ebf624…** ✓ (match pins and M2 evidence exactly). Engine and runner share the single executed revision (mono-repository); the D11/D12 recorded `repo_head` divergence (`6a60583f…`, RQ-12 non-strict) is carried transparently, not re-interpreted. On-host recomputation remains in the Windows runbook (Step 2) to guard against host checkout drift. |
| A2 | Package + provenance byte-identity; no write path | PARTIAL — fixture-level verified (open/verify before and after serving; zero writes in serving code); M2-level re-verification **PENDING OWNER WINDOWS VERIFICATION** | `test_serving_does_not_mutate_package_and_reopen_verifies`; `test_full_package_byte_snapshot_unchanged_after_serving` (per-file sha256 snapshot identical across serving + index builds); grep-able fact: serving layer contains no write path into the package; M2-level re-verification via runbook §1/§10. |
| A3 | Canonical row-retention & count parity | FIXTURE-VERIFIED (M2 leg **PENDING OWNER WINDOWS VERIFICATION**) | `test_invalid_checkdigit_and_len_rows_are_served_verbatim`; `test_count_parity_all_series_and_dates`; `test_per_partition_retention_count_parity` (legacy13/2016: 5, legacy13/2017: 2, udiff34/2024: 2; total 9 = `rows_total`); `test_served_payloads_never_carry_raw_line`; validity mix preserved (1 INVALID_CHECKDIGIT + 1 INVALID_LEN + 1 BLANK + 6 VALID). |
| A4 | VALID-only exclusively at Class-(4) boundary + executable retrieval tests | **MET (fixture-executable)** | `isin_index.py` is the only module containing the `isin_validity == 'VALID'` index predicate; retrieval path never imports it. Executable: `test_invalid_checkdigit_and_len_rows_are_served_verbatim`, `test_blank_isin_row_is_served`, `test_retrieving_by_invalid_isin_still_returns_rows`, `test_count_parity_all_series_and_dates`. grep/lint supplementary: this record notes the predicate appears once, in `build_isin_index`. |
| A5 | Deterministic index generation & rebuild | FIXTURE-VERIFIED (M2 leg **PENDING OWNER WINDOWS VERIFICATION**) | `test_two_builds_are_byte_identical`; `test_delete_and_rebuild_reproduces_identical_digest`; `test_valid_only_membership_and_counts` (rows_scanned 9 / rows_indexed 6 / isins 3; BLANK/INVALID absent); `test_stale_index_is_refused` (variant package identity → `IsinIndexError index-stale`); canonical-JSON key order covered by build comparison in-process. |
| A6 | Association semantics | **MET (unit + HTTP)** | `test_invalid_isin_returns_empty_correlation_not_error` (200 + `is_valid_isin_format: null`, basis `exact-observation-only`); `test_sequential_rename_spans_unit` + `observedSymbols[]` from VALID links; `test_series_isolation_unit` (EQ/BE/BL isolation); `test_overlapping_span_is_ambiguous_unit`; `test_same_date_parallel_states_are_ambiguous_unit`; `test_overlapping_valid_links_yield_409` (HTTP 409 `IDENTITY_AMBIGUOUS`); `is_valid_isin_format` is true-or-null only (code inspection + tests); EQ/BE/BL isolation in serving path (`test_eq_be_bl_isolation_in_serving`). |
| A7 | Q8 census parity | FIXTURE-VERIFIED (M2 census **PENDING OWNER WINDOWS VERIFICATION**) | `test_q8_census_parity_and_index_non_interference`: serving-index `flag_census` `{isin_invalid_checkdigit: 1, isin_invalid_length: 1}` equals the package-derived census and is unchanged by class-(4) index construction. No quality/Q8 code was modified. |
| A8 | Response digest reproducibility; eod-observation stamps | **MET** | `test_eod_observation_stamps_and_reproducibility` (byte-identical bodies + `pinnedGeneration`/`bitemporalKnowledgeAsOf: false`); `test_health_is_byte_reproducible`; `test_digest_matches_body` (`X-Response-Digest` == SHA-256 of canonical payload, verified independently in test); `responseDigest` on all responses (`canonical_digest` unit path). |
| A9 | Windows M2 smoke incl. invalid-checkdigit instrument | **PENDING OWNER WINDOWS VERIFICATION — NOT EXECUTED** | None. Complete PowerShell runbook: `D40B_WINDOWS_M2_SMOKE_RUNBOOK.md`; no result claimed until owner executes and evidence is verified. |
| A10 | No CI without authorization | **MET** | No `.github/workflows/` exists; none was added; no CI result is claimed anywhere in this record. Verification = recorded local/Windows evidence + remote `gh` inspection. |

## 6. Acceptance matrix EC-AC-01..05 (preserved verbatim; D40 §4)

| # | EC-AC wording (as published) | Status | Evidence |
|---|---|---|---|
| EC-AC-01 | `401` missing/bad token; non-loopback `Host` → `403`; `--bind 0.0.0.0` refused; zero `Access-Control-*` | **MET** | `test_missing_or_bad_bearer_is_401`; `test_non_loopback_host_is_403_and_zero_cors`; `test_bind_zero_is_refused_at_startup`; `test_every_response_has_no_store_and_no_cors`; `test_missing_token_is_refused`; `test_unknown_route_404_and_method_405`. |
| EC-AC-02 | Invalid ISIN syntax → `400`; BLANK/invalid rows excluded from index only; overlapping-symbol ambiguity → `409 IDENTITY_AMBIGUOUS`; sequential renames via `observedSymbols[]`; EQ/BE/BL isolated | **MET** | `test_invalid_isin_syntax_is_400`; `test_valid_only_membership_and_counts`; `test_overlapping_valid_links_yield_409`; `test_sequential_rename_spans_unit`; `test_eq_be_bl_isolation_in_serving`; `test_series_isolation_unit`. |
| EC-AC-03 | `BSE_EQ` → `422 UNSUPPORTED_EXCHANGE`; `1m..1h` → `422 UNSUPPORTED_FREQUENCY`; adjusted → `422 ADJUSTMENT_UNAVAILABLE`; eod-observation stamps | **MET** | `test_bse_eq_is_422`; `test_intraday_is_422`; `test_adjusted_mode_is_422`; `test_eod_observation_stamps_and_reproducibility`. |
| EC-AC-04 | Exact accounting: holidays, `unexplainedCalendarDates[]`, `notRetrievedCalendarDates[]`, `securityAbsentOnTradingDaysCount` with `tradingDaysWithArchive === returnedBarCount + securityAbsentOnTradingDaysCount` | MET (fixture, calendar-exact); M2-level accounting **PENDING OWNER WINDOWS VERIFICATION** | `test_completeness_equation_holds_with_calendar`; `test_absent_security_is_counted_not_hidden`; `test_calendar_endpoint_lists_unexplained` (2024-03-04..2024-03-08 span: present day 2024-03-05; unexplained `2024-03-04/06/07/08`); `calendar-unavailable` honest empty state (fixture default without W2 pair). |
| EC-AC-05 | Identical queries → byte-identical JSON + `responseDigest`; delete/rebuild ISIN index → identical digest; M2 digest unchanged; Windows smoke pass | **PARTIAL — everything except the Windows leg verified here; Windows leg **PENDING OWNER WINDOWS VERIFICATION** | `test_eod_observation_stamps_and_reproducibility`; `test_health_is_byte_reproducible`; `test_delete_and_rebuild_reproduces_identical_digest`; `test_serving_does_not_mutate_package_and_reopen_verifies`; M2 manifest `e7c7e4c8…` **not re-verified in this run** (no M2 bytes present); Windows smoke **PENDING OWNER WINDOWS VERIFICATION** (§4/runbook). |

## 7. Files changed

- new `src/serving/iips_serve.py`
- new `src/serving/isin_index.py`
- new `tests/test_serving_iips_serve.py`
- new `docs/implementation/D40B_PHASE_B_IIPS_EQUICORE_SERVING_IMPLEMENTATION.md` (this record)
- new `docs/implementation/D40B_WINDOWS_M2_SMOKE_RUNBOOK.md` (owner-side Windows M2 verification runbook)
- `README.md` — durable-record index line for this record (+ D40 entry status tail updated)
- `docs/architecture/EQUI_CORE_ARCHITECTURE_DECISION_REGISTER.md` — D40/Phase-B rows updated to the same effect

No engine, runner, canonical-data, D05, D03 fixture, UI (`src/ui/serve.py`, port 8613 untouched),
or historical-record changes. `git diff --stat` at commit time is the binding file list.

## 8. Remaining defects / blockers / honesty notes

1. **A9 (Windows M2 smoke) not executed; M2-level A2/A5/A7/EC-AC-05 legs unexecuted.** Blocked by
   absence of the physical package in this environment (bounded search; §4). No claim is made that
   they pass. The owner must run §4 and record outputs; until then Phase B acceptance is **not
   fully attested** and must not be reported as complete against M2.
2. **A1 executed-revision leg is re-recorded, not re-attested.** Commit `8ade8372e150…` / tree
   `8e1557de766d4c952be7261c4f72aa743f81de0b` come from D11/D12 durable evidence; this run cannot
   re-derive them from M2 bytes. The package's own recorded `repo_head` (`6a60583f…`) differs from
   the declared executed revision by recorded design (RQ-12, non-strict) — carried transparently, not
   papered over.
3. **`is_valid_isin_format` for a syntactically valid ISIN with zero VALID-linked observations is
   `null`** (empty correlation), never `false` — as C-1 §5.4-5 requires. Callers wanting
   syntax-validation semantics independent of index content should use retrieval, not associations.
4. **Span semantics:** one observed `[first, last]` span per symbol (observed bounds, not validity
   intervals); overlapping spans across distinct symbols on the same series → ambiguity (409).
   Non-contiguous observations of the same symbol are merged into one span (D05-consistent: dates
   are observations; the caller owns any rename disposition). This is deliberate.
5. **Performance:** bars/eod-observation scan row files linearly per request (O(N) over the pinned
   window) and re-validate the calendar per request. Correct and deterministic; not optimized for
   high-volume use; no caching layer exists by design (no wall-clock memoization).
6. **Completeness when the class-(2) calendar pair is absent** reports `status: calendar-unavailable`
   with null counts — explicit, never fabricated. A package without `w2/calendar.jsonl` +
   `w2/metrics.json` cannot yield holiday accounting until those are published in M2-or-successor.
7. Cosmetic (carried): D40 §5.5 heading reads "EC-AC-B1..EC-AC-B10" while the criteria are A1–A10;
   noted to owner; left unedited here (D40 is preserved verbatim except §3's authorized §5.6 edit).
8. `.github/workflows/` remains absent; no CI is claimed (A10).

## 9. Exact endpoint and startup instructions

Service: `iips-equicore-historical/v1` on **`http://127.0.0.1:8614`** (default; `--bind` accepts only
`127.0.0.1`/`localhost`; `--bind 0.0.0.0` is refused at startup; distinct from the UI on 8613).

```bash
# from the repository root, with the M2 package path on the Windows/Linux host that holds it
export PYTHONPATH=src
# (one-time) build/refresh the class-(4) correlation index into a state root OUTSIDE the package
python3 -m serving.isin_index build --package /path/to/i4-20261008-M2 --state /path/to/state
# run the service (bearer token mandatory)
export IIPS_EQUICORE_TRANSPORT_TOKEN='<one-time token>'
python3 -m serving.iips_serve --package /path/to/i4-20261008-M2 --state /path/to/state \
    [--bind 127.0.0.1] [--port 8614]
```

Routes (all require `Authorization: Bearer <token>`; all responses canonical JSON + `responseDigest`):

- `GET /v1/health`
- `POST /v1/historical/bars` — body `{exchange:"NSE_EQ", frequency:"1D", adjustmentMode:"RAW_UNADJUSTED",
  series, from, to, [isin], [symbol], [limit], [offset]}`; response includes `rows[]` (verbatim, flags
  included), `total`, and `completeness` (accounting block, §2.2).
- `POST /v1/historical/eod-observation` — identical, plus `pinnedGeneration: PINNED_GENERATION_EOD_SNAPSHOT`
  and `bitemporalKnowledgeAsOf: false`.
- `GET /v1/instruments/:isin/associations` — VALID-linked correlation only (see §2.2, A6).
- `GET /v1/calendar[?from=YYYY-MM-DD&to=YYYY-MM-DD]` — accounting surface incl.
  `unexplainedCalendarDates[]`, `notRetrievedCalendarDates[]`, `officialHolidays[]`, `days[]`.

State files: `<state>/serving_index.json` + `serving_index.sha256` (class-4, existing) and
`<state>/serving_isin_index.json` + `serving_isin_index.sha256` (class-4, new). Deleting either is
never a data event; rebuild reproduces identical digests (A5).

## 10. Branch / commit / PR

- Branch `arena/ddcaa938-equity-market-data-engine` (based on `origin/main` = `a4e298f…`); commits are
  the delivery vehicle for this record; the PR targets `main`.
- PR: **#8** (`https://github.com/ramkivs/equity-market-data-engine/pull/8`), targeting `main`; evidence limitations carried in the PR body verbatim (A9 / M2 legs pending owner Windows verification). Authentication-contract correction and Windows runbook landed as follow-up commits on the same branch.
- M2 acceptance is **not** attested by this record beyond §5–§6 as written; A9 and the Windows legs
  remain open until the owner executes §4 on the Windows host.
