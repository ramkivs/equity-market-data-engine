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
  (re-aligned 2026-11-24 to merged `origin/main` = **`5101714…`** = PR #8 merge; earlier in this
  engagement it sat at the PR #7 merge `a4e298f…`; see §10 and PR #9 process note).
- Personal-use, single-user, IIPS+EquiCore loopback integration only (D40 §1.1). No production,
  hosted, commercial, or multi-user deployment is authorized or claimed.
- Raw-archive serving stays excluded (D40 EC-DEC-04 / D16-08; B5 `CHANGED-CONFLICT-UNRESOLVED`
  fail-closed). B5/B6 composites remain out of scope. Phase C is **not** authorized.
- **Honesty binding:** no acceptance criterion in this record is claimed beyond what the recorded
  evidence shows. The owner-executed Windows M2 smoke evidence **has been received and verified**
  (§4B; branch `evidence/d40b-windows-m2-smoke-2026-11-25` @ `0127134`). The one exception is **A9,
  which is unmet as worded on the qualified M2** (zero `INVALID_CHECKDIGIT` rows under the governed
  ISO 6166 classifier — W1-DIV-1; census verbatim in §4B). A9 is **not** reported as passed; its
  disposition is an owner decision (§8 item 0/9). Final acceptance remains with the owner (Ramki).

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

## 4. Windows M2 verification handoff — owner-executed (A9 disposition open)

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
8. Verification that flagged observations are returned with their validity flags — §7–§8
   (as executed for the package's single INVALID_LEN row; the original INVALID_CHECKDIGIT premise is
   superseded — §8 items 0/9).
9. Digest and completeness verification (EC-AC-04/A8) — §9. 10. Final provenance/acceptance
   evidence capture incl. before/after `verify --m2` — §10–§12.

It also specifies the evidence file location policy, the exact files the owner must return to
Arena, and the rule that raw row-level payloads are not committed to this public repository
(only JSON responses, logs and digests are returned).

**Current status: owner Windows M2 evidence RECEIVED AND VERIFIED (see §4B).** The M2-dependent
portions of A2, A5, A7 and EC-AC-05 are verified and recorded in §5–§6. **A9 is not attested**:
on the qualified M2 it is unmet as worded (W1-DIV-1; §4B/§8). Phase B acceptance is **not** claimed
complete by this record; final acceptance is reserved to the owner (Ramki).

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

## 4B. Owner-returned Windows M2 smoke evidence — verification record (2026-11-25)

**Source:** branch `evidence/d40b-windows-m2-smoke-2026-11-25`, commit `0127134`
(`01271347715a4fd78e4408b88571f7334d77107a`), directory `evidence/D40B-Windows-M2-Smoke-2026-11-25/`
(publication commit `0127134`, based on merged `main` `5101714` — i.e. PR #8; the docs-only PR #9/
`089fb63` corrected runbook carries no behavior delta). Evidence was captured on the owner Windows
host on **2026-11-24** (HTTP `Date` headers; the directory name carries `2026-11-25`), against repo
`HEAD` recorded in `head.txt` = `51017148f051fdbd5f3aef57032147bb0cc50379`.

### 4B.1 Integrity verification (SHA-256)

- `SHA256SUMS.txt` (33 entries, CRLF, parse-verified): **all 33 files present and byte-exact**,
  including `SHA256SUMS-owner-capture.txt` (`c71f77b0…`) itself.
- `SHA256SUMS-owner-capture.txt` (35 entries, the capture-time manifest): **30 of 35 present and
  byte-exact.** The 5 absent files are the raw bars response bodies (`bars-specimen.json`,
  `bars-specimen-2.json`, `bars-1.json`, `bars-2.json`, `bars-wide.json`), intentionally **not**
  published — consistent with the runbook rule that raw payloads stay owner-side; only their
  `X-Response-Digest` headers and capture-time hashes are recorded. `q8-quality.json`,
  `verdict-counts.txt` and `SHA256SUMS.txt` were added at publication time and are hashed in
  `SHA256SUMS.txt` (`29b4bb54…`, `132eaa4d…`).
- No integrity failure is present. Files were hashed from the Git checkout of `0127134`, not from
  the owner host; identity transfer relies on git + SHA-256 both.
- Observation: the published `eod-observation.json` **does** contain the specimen row's complete
  `source_values` payload (owner-published; see §8 item 12 — awareness note for the owner, not altered here).

### 4B.2 What the evidence shows (criterion-level detail in §5–§6)

1. **Repository/revision identity** — `head.txt` (`5101714…`), `rev-type.txt` (`commit`),
   `rev-tree.txt` (`8e1557de766d4c952be7261c4f72aa743f81de0b` — matches the record's §5-A1 derivation),
   `rev-fingerprints.txt` (engine `d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9`,
   runner `f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a` — both match the A1 pins).
2. **M2 package intact pre/post serving** — `verify-pre.txt` / `verify-post.txt`: `result: pass`,
   pinned `m2`, `run_id i4-20261008-M2`, `manifest_entries: 4946`,
   `manifest_sha256: e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc` (matches the A1 pin),
   `total_bytes: 21119807344` (matches pin), `verification: full`, 7/7 checks; exit codes **0**
   (`verify-pre-exitcode.txt`, `verify-post-exitcode.txt`). The two verifier outputs are
   byte-identical (deterministic verifier).
3. **Package serving integrity / index build determinism** — `index-build-a.txt` ≡
   `index-build-b.txt` (same counts `isins: 7632`, `keys: 5689948`, `rows_indexed: 5689948`,
   `rows_scanned: 5689949`; digest `8095982136ed4ba0f9c0b3577ff145245ac3e83d39e80b381ac955f8f86ad398`);
   `index-sha-a.txt` ≡ `index-sha-b.txt` (`80959821…  serving_isin_index.json`); `index-compare.txt`
   (`INDEX DIGEST MATCH d1==d2`); `index-info-a.txt` (`format: serving-isin-index/1.0`; package block:
   run `i4-20261008-M2`, manifest pin match, `file_count: 4948`, `archive_count: 2462`,
   `total_bytes: 21119807344`, engine/runner hashes match pins).
4. **Health / auth contract on the live server** — `health-ok.json` (200; `status: ok`; package
   pin manifest `e7c7e4c8…`, `archive_count: 2462`; contract `iips-equicore-historical/v1`;
   `auth: bearer`; `state.isin_index` `80959821…` matches the index digest); `health-headers.txt`
   (200; `X-Response-Digest: 12dfbeef…` matches the body's `responseDigest`; **no
   `Access-Control-*` headers**; `no-store`; `nosniff`); `server.log` (startup line on
   `127.0.0.1:8614`; request sequence `401`, `401`, `403`, `200`, then `200` for the serving calls).
   `health-noauth.json` / `health-wrong.json` (both `401 UNAUTHORIZED`, **byte-identical bodies**,
   same `responseDigest d923fc2b…`); `health-badhost.txt` (`403 HOST_FORBIDDEN`,
   `X-Response-Digest: 65e42f46…` matching its body).
5. **Flagged specimen served verbatim (A4 objective)** — `verdict-counts.txt`:
   `validity_counts {"BLANK": 0, "INVALID_CHARSET": 0, "INVALID_CHECKDIGIT": 0, "INVALID_LEN": 1,
   "INVALID_PREFIX": 0, "VALID": 5689948}`, `total_flag_entries 1397` — sums to the pinned
   **5,689,949** rows; `INVALID_CHECKDIGIT = 0`. The INVALID_LEN row was located by whole-package
   sweep and retrieved through the API: `eod-observation.json` (HTTP 200;
   `pinnedGeneration: PINNED_GENERATION_EOD_SNAPSHOT`, `bitemporalKnowledgeAsOf: false`;
   `completeness` exact — `tradingDaysWithArchive: 1 = returnedBarCount: 1 +
   securityAbsentOnTradingDaysCount: 0`; route query `ABFRLPP1`/`E1`, date `2021-02-16`; row:
   `isin_normalized: DUMMY`, `isin_validity: INVALID_LEN`, flag `isin_invalid_length`
   (severity `informational`, reference `D05 §5`), provenance `legacy13`/`cm16FEB2021bhav.csv`
   (line 27), archive `cm16FEB2021bhav.csv.zip`, tool sha `d3269b73…`, member sha `16a73062…`;
   **no `raw_line` key**); `specimen-check.txt` (`total: 1`, `rows_on_date: 1`, flag triple
   confirmed, `raw_line_present: false`). `X-Response-Digest 428b72f8…` equals the body
   `responseDigest`, and `digest-recompute.txt` independently recomputed `428b72f8…` → **MATCH**.
6. **Q8 census parity (A7)** — `q8-quality.json`: `flag_census {"isin_invalid_length": 1,
   "orphan_no_base_row": 336, "overlay_qty_gt_base": 1060}` sums to **1397** — exactly the engine
   sweep `total_flag_entries` (`verdict-counts.txt`); `isin_invalid_length: 1` matches the sweep's
   `INVALID_LEN: 1`; the checkdigit census is `0` on both sides; `quarantine.count: 0`;
   `changed.status: absent-in-m2-only-release` (carried honestly); `reconciliation.record_count:
   39402` (matches the D32/D33 baseline); `unresolved.record_count: 11` (D07-OPEN items carried).
7. **Calendar accounting (EC-AC-04, sampled window)** — `calendar-window.json` for
   `2024-11-15..2024-11-30`: 11 days accounted — 9 with archives (UDIFF), 1 official holiday
   (`2024-11-15`, Gurunanak Jayanti), 1 unexplained (`2024-11-20`, consistent with the Q8
   `D07-OPEN-8` record), `notRetrievedCalendarDates: []`; `totals` arithmetic closes
   (9 + 1 holiday + 1 unexplained = 11).
8. **Bars retrieval determinism** — two independent calls, `bars-headers-1.txt` (18:27:09Z) and
   `bars-headers-2.txt` (18:16:34Z): identical `X-Response-Digest: 61076e32…`, identical
   `Content-Length: 1727`; `bars-identity.txt` (Windows `fc.exe /b`: `no differences encountered`).
   The response bodies live owner-side only (§4B.1); their capture-time hashes are identical in
   `SHA256SUMS-owner-capture.txt` (`c765d86e…` for the specimen query across `bars-specimen.json`,
   `bars-specimen-2.json`, `bars-1.json`, `bars-2.json`; `380f4bfc…` for the wider
   `bars-wide.json` capture, not published).

### 4B.3 Not shown by this evidence (honest scope)

- The A9 **"invalid check digit"** leg: the qualified M2 contains **zero** `INVALID_CHECKDIGIT`
  rows (governed ISO 6166 classifier; W1-DIV-1); the 215,393 figure is a D03-tool artifact of a
  non-governed Luhn variant (`tools/d03_fixture_scan/d03_fixtures.py:82-118`). A9's smoke-pass leg
  is satisfied; the instrument leg is **unsatisfiable on this package**. A disposition decision
  (accept evidence-qualified result as unmet-as-worded, or re-word A9 by owner addendum) is
  reserved to Ramki — see §8 item 0/9 and §10.
- Per-partition row counts on Windows (sweep was whole-package aggregated; sum-to-pin is the
  retention witness). The `manifest_entries: 4946` (verifier) vs `file_count: 4948` (index-info)
  difference is the same package (manifest digest pin match); count semantics to be confirmed by
  the owner (§8 item 11). Associations endpoint and error-path 422s were not exercised in this
  smoke (fixture/test-verified only). `2025-10-20` and `2026-01-15` unexplained dates appear in
  Q8 `unresolved`, not in the sampled calendar window.

## 5. Acceptance matrix A1–A10 (D40 §5.5; refinements applied)

Evidence references of the form `SMOKE/<file>` point into branch `evidence/d40b-windows-m2-smoke-2026-11-25` @ `0127134`, `evidence/D40B-Windows-M2-Smoke-2026-11-25/`; review provenance in §4B.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | M2 pin complete (package/manifest/file count/bytes/rows/partitions/composite/engine/runner hashes + full commit hashes); fail-closed | **MET — owner Windows evidence (2026-11-24/25)** | On-host revision identity re-derived by owner: `SMOKE/rev-type.txt` (`commit`), `SMOKE/rev-tree.txt` (`8e1557de766d4c952be7261c4f72aa743f81de0b` — matches §5-A1 derivation), `SMOKE/rev-fingerprints.txt` (engine `d3269b73…`, runner `f3ebf624…` — match pins), `SMOKE/head.txt` (`5101714…`). Package re-verified on-host pre/post: `SMOKE/verify-pre.txt` + `verify-post.txt` (full verify, 7/7 checks, `manifest_sha256 e7c7e4c8…`, `manifest_entries 4946`, `total_bytes 21119807344`, pinned `m2`) + exit codes 0 (`verify-*-exitcode.txt`). `SMOKE/index-info-a.txt` package block: run `i4-20261008-M2`, manifest pin match, `file_count 4948`, `archive_count 2462`, `total_bytes 21119807344`, `composite_run_identity 9609c7fc…`, engine/runner hashes match. Pins (test-verified): manifest `e7c7e4c8…`; 21,119,807,344 B; 5,689,949 rows; 12 partitions; engine `d3269b73…`; runner `f3ebf624…`. Tests: `test_m2_pin_constants_match_recorded_identity`; `test_fixture_package_fails_m2_pin`; CLI `verify-07` refusal. Note: `manifest_entries 4946` (verifier) vs `file_count 4948` (index-info) — same manifest digest; count semantics confirmed by owner (§8 item 11), not a pin mismatch. |
| A2 | Package + provenance byte-identity; no write path | **MET — owner Windows evidence** | Pre/post `verify --m2` pass with exit 0 both (`SMOKE/verify-pre.txt`, `verify-post.txt`); verifier outputs byte-identical (SHA256SUMS: same digest `b3624a6f…`); manifest digest unchanged after all serving. Provenance blocks present and verbatim in served rows (`SMOKE/eod-observation.json`: `format_family legacy13`, `member_name cm16FEB2021bhav.csv`, `member_sha256_lf_text 16a73062…`, `source_archive cm16FEB2021bhav.csv.zip`, `run_id i4-20261008-M2`, `spec_version D05/1.0`, `tool_name nse-engine`, `tool_sha256 d3269b73…`). No write path to M2 exists anywhere in the serving codebase (code inspection; serving/index/quality unchanged; class-(4) index written only to caller `--state` root outside the package). Fixture backstop: `test_serving_does_not_mutate_package_and_reopen_verifies`; `test_full_package_byte_snapshot_unchanged_after_serving`. |
| A3 | Canonical row-retention & count parity | **MET — owner Windows evidence (total-package level)** | Whole-package sweep: `SMOKE/verdict-counts.txt` (`VALID 5,689,948` + `INVALID_LEN 1` = **5,689,949**, the A1 pin; every other literal 0) — no canonical row dropped; index `rows_scanned 5,689,949` == pin == sweep total; `rows_indexed 5,689,948` == VALID count exactly (the single INVALID_LEN row excluded from the index only). Flags and `isin_validity` carried verbatim in the served payload (`SMOKE/eod-observation.json`, `SMOKE/specimen-check.txt`); `raw_line` absent (`raw_line_present: false`; no `raw_line` key in `eod-observation.json`). Per-partition breakdown not separately published — sum-to-pin is the retention witness. Fixture backstop: `test_count_parity_all_series_and_dates`; `test_per_partition_retention_count_parity`; `test_served_payloads_never_carry_raw_line`; `test_invalid_checkdigit_and_len_rows_are_served_verbatim`. |
| A4 | VALID-only exclusively at Class-(4) boundary + executable retrieval tests | **MET — fixture-executable + owner Windows evidence** | M2 boundary proof: `SMOKE/index-build-a.txt`/`-b.txt` (`rows_scanned 5,689,949 → rows_indexed 5,689,948`, delta exactly the one `INVALID_LEN` row; `isins 7632`, `keys 5,689,948`); the excluded row **is served**, not omitted: `SMOKE/eod-observation.json` (`isin_validity INVALID_LEN`, flag `isin_invalid_length`, severity `informational`) and `SMOKE/specimen-check.txt` (`total 1`). `isin_index.py` remains the only module carrying the `isin_validity == 'VALID'` membership predicate; observation retrieval never imports it. Executable: `test_invalid_checkdigit_and_len_rows_are_served_verbatim`, `test_blank_isin_row_is_served`, `test_retrieving_by_invalid_isin_still_returns_rows`, `test_count_parity_all_series_and_dates`. |
| A5 | Deterministic index generation & rebuild | **MET — fixture + owner Windows evidence** | Two independent on-host builds byte-identical (`SMOKE/index-build-a.txt` ≡ `index-build-b.txt`; SHA256SUMS same digest; digest `80959821…`); sidecar SHAs identical (`SMOKE/index-sha-a.txt` ≡ `index-sha-b.txt`, `80959821…`); `SMOKE/index-compare.txt` (`INDEX DIGEST MATCH d1==d2`); rebuild reproduces the identical digest. Response determinism on M2: identical digests across repeated bars calls (`SMOKE/bars-headers-1.txt`/`bars-headers-2.txt`, `X-Response-Digest 61076e32…`, `Content-Length 1727`; `SMOKE/bars-identity.txt` `fc.exe` no differences; capture-time specimen hashes identical in `SHA256SUMS-owner-capture.txt`). Fixture backstop: `test_two_builds_are_byte_identical`; `test_delete_and_rebuild_reproduces_identical_digest`; `test_valid_only_membership_and_counts`; `test_stale_index_is_refused`. |
| A6 | Association semantics | **MET — unit + HTTP (not exercised in the returned Windows smoke; no M2-specific claim made)** | `test_invalid_isin_returns_empty_correlation_not_error` (200 + `is_valid_isin_format: null`, basis `exact-observation-only`); `test_sequential_rename_spans_unit` + `observedSymbols[]` from VALID links; `test_series_isolation_unit` (EQ/BE/BL isolation); `test_overlapping_span_is_ambiguous_unit`; `test_same_date_parallel_states_are_ambiguous_unit`; `test_overlapping_valid_links_yield_409` (HTTP 409 `IDENTITY_AMBIGUOUS`); `is_valid_isin_format` true-or-null only; `test_eq_be_bl_isolation_in_serving`. The Associations endpoint was **not called** in the returned Windows evidence (§4B.3); fixture/HTTP coverage stands unamended. |
| A7 | Q8 census parity | **MET — fixture + owner Windows evidence** | `SMOKE/q8-quality.json` `flag_census {isin_invalid_length: 1, orphan_no_base_row: 336, overlay_qty_gt_base: 1060}` sums to **1397** — byte-equal to the engine-side sweep `total_flag_entries 1397` (`SMOKE/verdict-counts.txt`); `isin_invalid_length: 1` == sweep `INVALID_LEN: 1`; checkdigit census `0` on both sides; `quarantine.count: 0`; `changed.status: absent-in-m2-only-release` (never fabricated); `reconciliation.record_count: 39402` (D32/D33 baseline). The excluded-from-index flagged row remains fully counted and served — the class-(4) construction did not alter, suppress or de-count it. No quality/Q8 code was modified. Fixture backstop: `test_q8_census_parity_and_index_non_interference`. |
| A8 | Response digest reproducibility; eod-observation stamps | **MET — fixture + owner Windows evidence** | `SMOKE/eod-headers.txt` `X-Response-Digest: 428b72f8…` == body `responseDigest` (`SMOKE/eod-observation.json`); `SMOKE/digest-recompute.txt` independently recomputed `428b72f8…` → **MATCH**; repeated bars calls byte-identical (`61076e32…`, §5-A5); `SMOKE/health-headers.txt` `X-Response-Digest: 12dfbeef…` == `health-ok.json` `responseDigest`; byte-identical 401 bodies (`SMOKE/health-noauth.json` ≡ `health-wrong.json`, digest `d923fc2b…`); `health-badhost.txt` 403 with matching digest `65e42f46…`. EOD stamps present verbatim: `PINNED_GENERATION_EOD_SNAPSHOT`, `bitemporalKnowledgeAsOf: false`. Fixture backstop: `test_eod_observation_stamps_and_reproducibility`; `test_health_is_byte_reproducible`; `test_digest_matches_body`. |
| A9 | Windows M2 smoke incl. invalid-checkdigit instrument | **NOT MET AS WORDED — unmet on the qualified M2 (owner disposition required; NOT to be reported passed)** | Smoke itself **passed** on the live Windows M2 (health/bars/eod-observation/calendar all `200`; auth matrix `401`/`403` honored; `SMOKE/server.log`). The instrument leg is **impossible on this package**: whole-package census `SMOKE/verdict-counts.txt` shows `INVALID_CHECKDIGIT: 0` (governed ISO 6166; W1-DIV-1 — the 215,393 figure is a D03-tool parity artifact, `d03_fixtures.py:82-118`). The **A4/A9 objective** is nonetheless demonstrated on the package's only ISIN-validity flagged row — `INVALID_LEN`, `ABFRLPP1`/`E1`, `2021-02-16`, `DUMMY`, `legacy13/2021/cm16FEB2021bhav.csv` line 27 — served **verbatim with flags, not omitted, not de-ranked** (`SMOKE/eod-observation.json`, `SMOKE/specimen-check.txt`). Per §8 item 0 and the corrected runbook, A9 must be recorded as unmet-as-worded / unmet-on-qualified-package, or **re-worded by owner decision (D40 addendum)**. No package or serving change may be made to manufacture a specimen. **Final acceptance of/on this criterion is reserved to Ramki.** |
| A10 | No CI without authorization | **MET** | No `.github/workflows/` exists; none was added in this work or in PR #8/#9; no CI result is claimed anywhere in this record or in the evidence branch. Verification = recorded local execution + recorded Windows owner execution + remote `gh` inspection. Evidence branch `evidence/d40b-windows-m2-smoke-2026-11-25` is a plain git publication of owner-returned files (commit `0127134`), not CI. |

## 6. Acceptance matrix EC-AC-01..05 (preserved verbatim; D40 §4)

Evidence references as in §5.

| # | EC-AC wording (as published) | Status | Evidence |
|---|---|---|---|
| EC-AC-01 | `401` missing/bad token; non-loopback `Host` → `403`; `--bind 0.0.0.0` refused; zero `Access-Control-*` | **MET — fixture + owner Windows M2 evidence** | Windows: `SMOKE/health-noauth.json` & `SMOKE/health-wrong.json` (`401 UNAUTHORIZED`, byte-identical); `SMOKE/health-badhost.txt` (`403 HOST_FORBIDDEN`, non-loopback `Host`); `SMOKE/health-headers.txt` (200, **no `Access-Control-*` headers**, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`); `SMOKE/server.log` (401/401/403/200 sequence). `--bind 0.0.0.0` startup refusal is enforced fail-closed and test-pinned (`test_bind_zero_is_refused_at_startup`; exit 2). Tests: `test_missing_or_bad_bearer_is_401`; `test_non_loopback_host_is_403_and_zero_cors`; `test_every_response_has_no_store_and_no_cors`; `test_missing_token_is_refused`; `test_unknown_route_404_and_method_405`. |
| EC-AC-02 | Invalid ISIN syntax → `400`; BLANK/invalid rows excluded from index only; overlapping-symbol ambiguity → `409 IDENTITY_AMBIGUOUS`; sequential renames via `observedSymbols[]`; EQ/BE/BL isolated | **MET — tests; M2 index-membership leg evidenced** | M2: BLANK/invalid rows excluded from the class-(4) index **only** (`rows_scanned 5,689,949` vs `rows_indexed 5,689,948`; keys == VALID count; `SMOKE/index-build-a.txt`); observation retrieval remains validity-agnostic (specimen served, §5-A4). The `400`/`409`/`observedSymbols[]`/EQ-BE-BL clauses are fixture/HTTP-test-verified (`test_invalid_isin_syntax_is_400`; `test_overlapping_valid_links_yield_409`; `test_sequential_rename_spans_unit`; `test_eq_be_bl_isolation_in_serving`; `test_series_isolation_unit`; `test_valid_only_membership_and_counts`); not exercised in the returned Windows smoke (§4B.3). |
| EC-AC-03 | `BSE_EQ` → `422 UNSUPPORTED_EXCHANGE`; `1m..1h` → `422 UNSUPPORTED_FREQUENCY`; adjusted → `422 ADJUSTMENT_UNAVAILABLE`; eod-observation stamps | **MET — tests; M2 eod stamps evidenced** | `SMOKE/eod-observation.json` (200): `pinnedGeneration: PINNED_GENERATION_EOD_SNAPSHOT`, `bitemporalKnowledgeAsOf: false` — verbatim on the live M2. The 422 clauses are test-verified only (`test_bse_eq_is_422`; `test_intraday_is_422`; `test_adjusted_mode_is_422`); not exercised in the returned Windows smoke (§4B.3). Tests: `test_eod_observation_stamps_and_reproducibility`. |
| EC-AC-04 | Exact accounting: holidays, `unexplainedCalendarDates[]`, `notRetrievedCalendarDates[]`, `securityAbsentOnTradingDaysCount` with `tradingDaysWithArchive === returnedBarCount + securityAbsentOnTradingDaysCount` | **MET — fixture + owner Windows M2 evidence (sampled window; not a full-corpus accounting)** | eod-observation completeness is **exact**: `tradingDaysWithArchive: 1 = returnedBarCount: 1 + securityAbsentOnTradingDaysCount: 0` (`SMOKE/eod-observation.json`). Calendar window `2024-11-15..2024-11-30`: 11 days accounted — 9 with archives (UDIFF), 1 official holiday (`2024-11-15`, Gurunanak Jayanti), `unexplainedCalendarDates: ["2024-11-20"]` (consistent with the Q8 `D07-OPEN-8` record), `notRetrievedCalendarDates: []`; totals close (9 + 1 + 1 = 11) (`SMOKE/calendar-window.json`). Scope: one sampled window for date semantics + the exact-equation check on the specimen day — not an end-to-end accounting of every calendar-exact day in M2. Tests: `test_completeness_equation_holds_with_calendar`; `test_absent_security_is_counted_not_hidden`; `test_calendar_endpoint_lists_unexplained`. |
| EC-AC-05 | Identical queries → byte-identical JSON + `responseDigest`; delete/rebuild ISIN index → identical digest; M2 digest unchanged; Windows smoke pass | **MET — fixture + owner Windows M2 evidence** | Windows: identical digests across repeated bars calls (`SMOKE/bars-headers-1.txt` ≡ `bars-headers-2.txt`, `61076e32…`); `SMOKE/bars-identity.txt` (`fc.exe` no differences); `SMOKE/digest-recompute.txt` (`428b72f8…` **MATCH**); rebuild → identical digest (`SMOKE/index-build-a/b.txt`, `index-sha-a/b.txt`, `index-compare.txt`); M2 manifest digest unchanged (`SMOKE/verify-pre.txt` + `verify-post.txt`, exit 0); smoke queries all pass (`SMOKE/server.log`). Tests: `test_eod_observation_stamps_and_reproducibility`; `test_health_is_byte_reproducible`; `test_delete_and_rebuild_reproduces_identical_digest`; `test_serving_does_not_mutate_package_and_reopen_verifies`. |

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

0. **A9 specimen premise superseded by W1-DIV-1 (corrected runbook, 2026-11-24).** The D05 §5
   parenthetical (215,393 Legacy INVALID_CHECKDIGIT, ~5.4%) is a D03-tool census of a non-governed
   Luhn variant (`tools/d03_fixture_scan/d03_fixtures.py:82-118`, `v[1:11]` parity bug, selftest
   round-trip). W1 (M2's engine) implements the governed ISO 6166 check and finds ZERO invalid check
   digits on the published sample (`src/nse_engine/contract.py` W1-DIV-1). Consequently the canonical
   M2 very likely contains **zero** INVALID_CHECKDIGIT rows — consistent with the owner's 2026-11-24
   Windows searches returning zero matches across `legacy13`. The runbook's Step 7 was corrected
   (verdict_census whole-package sweep + Q8 `serving quality` + specimen discovery for whichever
   flagged population exists, expected: the single INVALID_LEN row). A9 as originally worded
   ("at least one Legacy instrument known to carry an invalid check digit") is expected NOT to be
   satisfiable on the qualified M2; if the verdict census confirms zero, A9 must be recorded as
   unmet-on-qualified-package (or re-worded by owner decision) — never reported as passed, and no
   package/serving change may be made to manufacture a specimen. **Update 2026-11-25: the
   owner-executed census confirmed zero** (`SMOKE/verdict-counts.txt`; §4B) — see item 9.
1. ~~**A9 (Windows M2 smoke) not executed**~~ **EXECUTED by the owner and verified in this record
   (2026-11-25; §4B, branch `evidence/d40b-windows-m2-smoke-2026-11-25` @ `0127134`).** All
   M2-dependent legs (A2, A5, A7, EC-AC-01/03/04/05-M2, EC-AC-05) are evidenced and recorded in
   §5–§6. **A9 remains the one criterion not attested**: its invalid-checkdigit instrument leg is
   unsatisfiable on the qualified M2 (§4B.2/§4B.3; §8 item 0) and its disposition is reserved to
   the owner. Phase B acceptance is **not** claimed complete against A9 by this record.
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

9. **A9 disposition open — owner decision required (blocker for any Phase B completion claim).**
   The owner-executed census proves the qualified M2 carries zero `INVALID_CHECKDIGIT` rows and one
   `INVALID_LEN` row; the latter is served verbatim with `isin_invalid_length` (A4/A9 objective
   met on the real population). A9 as worded in D40 §5.5 cannot be attested. Options, owner's sole
   prerogative: (i) accept the A9 evidence as unmet-as-worded/unmet-on-qualified-package with the
   W1-DIV-1 citation, or (ii) issue a D40 addendum re-wording A9 to the governed flagged-population
   objective (e.g. "at least one canonical row carrying a governed ISIN-validity flag is served
   verbatim with flags — not omitted, not de-ranked"). This record implements neither and claims
   neither; nothing here manufactures a checkdigit specimen.
10. **Evidence provenance/custody notes (non-blocking, owner awareness).** (a) Evidence was captured
    2026-11-24 (HTTP `Date`), published 2026-11-25 as commit `0127134` on
    `evidence/d40b-windows-m2-smoke-2026-11-25` (based on merged `main` `5101714`); repo `HEAD` at
    capture = `5101714`. (b) `SHA256SUMS.txt` passes 33/33; the owner capture manifest
    (`SHA256SUMS-owner-capture.txt`, 35 entries) passes 30/35 — the 5 absent files are raw bars
    response bodies, intentionally unpublished (raw-payload policy); publication additions
    (`q8-quality.json`, `verdict-counts.txt`) are hashed in `SHA256SUMS.txt`.
11. **`manifest_entries` vs `file_count`.** Verifier reports `manifest_entries: 4946`;
    `index-info-a.txt` reports `file_count: 4948`. Both reference the same manifest
    (`manifest_sha256 e7c7e4c8…` matches the A1 pin; `total_bytes 21119807344` matches). The
    two-entry difference is a counting-semantics question for the owner to confirm (e.g. manifest
    records vs files present), not an integrity failure — recorded transparently, not reconciled
    by invention.
12. **Raw payload balance.** The published `eod-observation.json` contains the specimen row's full
    `source_values` and provenance (owner-published; it is a single synthetic-`DUMMY` legacy row,
    line 27 of `cm16FEB2021bhav.csv`). This slightly exceeds the "counts/flags/digests only"
    guardrail; it was published by the owner. No serving code or package change is implied; the
    owner may redact/republish at discretion (the API responses themselves are unchanged). Also
    note: `server.log`'s manifest truncation renders as `e7c7e4c8à` (cosmetic mojibake), and the
    evidence directory name (`2026-11-25`) post-dates the capture date (`2026-11-24`).

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

- Branch `arena/ddcaa938-equity-market-data-engine` (based on merged `origin/main` = `5101714…` at
  re-alignment 2026-11-24; see PR #9 process note); commits are the delivery vehicle for this record;
  the PR targets `main`.
- PR: **#8** (`https://github.com/ramkivs/equity-market-data-engine/pull/8`, **MERGED** 2026-11-24
  into `main` as `5101714`) and PR: **#9** (`https://github.com/ramkivs/equity-market-data-engine/pull/9`,
  open — Step 7/W1-DIV-1 runbook correction and this Windows-evidence acceptance-matrix update).
- Evidence publication: branch `evidence/d40b-windows-m2-smoke-2026-11-25` @ `0127134`
  (`01271347715a4fd78e4408b88571f7334d77107a`), directory `evidence/D40B-Windows-M2-Smoke-2026-11-25/`.
- **M2 acceptance is not attested by this record.** The smoke evidence is received and verified
  (§4B) and all A1–A10/EC-AC legs except A9 are recorded in §5–§6 — but A9 is unmet as worded on the
  qualified M2 (§8 item 9) and its disposition, like any final Phase B acceptance/closure
  declaration, is **reserved to the owner (Ramki)**. No statement in this record constitutes
  acceptance.
