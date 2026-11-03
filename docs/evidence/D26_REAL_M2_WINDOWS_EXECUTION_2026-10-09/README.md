# D26 Serving Evidence Bundle

Bundle name: `D26_serving_evidence`
Prepared: 2026-10-10
Purpose: Consolidate the D26 real-M2 Windows execution evidence supplied in the conversation, for transfer into the Arena workspace.

## Important provenance limitation

This bundle is **not** a complete raw PowerShell transcript. It consolidates:
1. Results and process observations explicitly pasted by the user in the conversation.
2. Two user-uploaded query-output text fragments, preserved byte-for-byte under `raw_user_supplied/`.
3. A normalized evidence summary and transfer manifest generated for this bundle.

No missing console output has been reconstructed as if it were original. The Step 2 output and full Step 4 output were not supplied as standalone raw transcript files in this bundle; their results below reflect the user's reported/pasted execution outcomes in the conversation. Arena should retain this distinction when reconciling D23 acceptance criteria.

## Intended transfer

Extract this folder into a temporary Windows directory, for example:

`C:\Users\USER\D26_serving_evidence`

Then transfer the extracted directory or its files to the Arena environment using the supported upload/transfer mechanism. Do not assume Arena can read this Windows path directly.

## Pinned implementation and package

- Repository: `ramkivs/nse-historical-data-engine`
- D24 implementation commit: `69977017ffca944921f231d7904347bc582b6392`
- Package root on Windows: `G:\My Engines\I4_RUNS\i4-20261008-M2`
- Run ID: `i4-20261008-M2`
- State directory: `G:\My Engines\I4_RUNS\d26_serving_state_20261009`
- Package manifest SHA-256: `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`
- Package total bytes: `21119807344`
- Post-run verifier manifest entries: `4946`

## Consolidated step results

### Step 1 — Readiness / pinned package identity
Reported PASS before the execution steps. Pinned identity and package structure were checked. The detailed Step 1 console output was not preserved as a standalone raw transcript in this bundle.

### Step 2 — Full verification against pinned M2
Reported PASS; exit code `0` per the execution status shared during the conversation. The full standalone Step 2 output was not preserved as a raw file in this bundle.

### Step 3 — Real-M2 integration tests
User-pasted result:
- `Ran 7 tests in 1792.186s`
- `OK`
- `STEP 3 exit code: 0`
- Tests shown as passing:
  - `test_pin_file_count_and_total_bytes`
  - `test_pin_manifest_digest`
  - `test_pin_row_count_matches_run_record`
  - `test_pin_run_and_tool_identity`
  - `test_full_verification_passes_with_pinned_spec`
  - `test_q3_query_over_real_baseline`
  - `test_rebuild_reproducibility`
- Zero failures, errors, or skips were reported by the `OK` summary.

### Step 4 — Serving-index build
User-pasted JSON:
- `result: pass`
- `STEP 4 exit code: 0`
- `instrument_pairs: 16107`
- `row_count: 5689949`
- `row_files: 2462`
- `index_sha256: 08cad8ce80f6b531700a0adc48af83e434f896df287c219f278daf0acbb19996`
- `package_manifest_sha256: e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`
- Partitions:
  - `legacy13/2016`
  - `legacy13/2017`
  - `legacy13/2018`
  - `legacy13/2019`
  - `legacy13/2020`
  - `legacy13/2021`
  - `legacy13/2022`
  - `legacy13/2023`
  - `legacy13/2024`
  - `udiff34/2024`
  - `udiff34/2025`
  - `udiff34/2026`

### Step 5 — Q3 query for RELIANCE EQ
User-reported/pasted:
- Query returned dated `RELIANCE` EQ records with source provenance.
- `STEP 5 exit code: 0`
- Query output fragments are preserved byte-for-byte under `raw_user_supplied/`.
- The fragments show business dates, published source values, source-file paths, source line numbers, format family, run ID, and engine identity.
- The supplied fragments are partial output, not a complete query transcript.
- The query took several minutes. Root cause is not established; record as a performance observation, not a functional failure.

### Step 6 — Rebuild reproducibility
User-pasted JSON:
- `result: pass`
- `STEP 6 exit code: 0`
- `identical: true`
- `before_sha256: 08cad8ce80f6b531700a0adc48af83e434f896df287c219f278daf0acbb19996`
- `after_sha256: 08cad8ce80f6b531700a0adc48af83e434f896df287c219f278daf0acbb19996`
- `files_scanned: 2462`
- `rows_scanned: 5689949`
- `instrument_pairs: 16107`
- `package_manifest_sha256: e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`

### Step 7 — Post-run package verification
User-pasted JSON:
- `result: pass`
- `STEP 7 exit code: 0`
- `checks_passed`: `verify-01` through `verify-07`
- `pinned: m2`
- `run_id: i4-20261008-M2`
- `manifest_entries: 4946`
- `manifest_sha256: e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`
- `total_bytes: 21119807344`

### Final handoff
User-pasted final line:
`HANDOFF RESULT: COMMANDS COMPLETED. Review all expected results before declaring D26 integration verification successful.`

## Current evidence disposition

- Reported Windows execution: Steps 1–7 completed; each reported successful.
- Step 3 integration tests: 7/7 passed.
- Step 6 rebuild: identical index digest before/after.
- Step 7 post-run package verification: all seven verifier checks passed; manifest digest matches the pinned digest.
- Full raw transcript availability: incomplete.
- Independent Arena reconciliation and durable repository publication: not performed by this bundle.
- D23 acceptance closure / D24 promotion: not asserted by this bundle.
