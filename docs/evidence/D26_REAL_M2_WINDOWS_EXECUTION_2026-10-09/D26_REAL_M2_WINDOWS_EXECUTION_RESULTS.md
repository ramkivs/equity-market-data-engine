# D26 Real-M2 Windows Execution — Consolidated Results Record

**Record type:** Evidence consolidation for transfer; not a repository acceptance decision.  
**Prepared:** 2026-10-10  
**Implementation under test:** D24, `69977017ffca944921f231d7904347bc582b6392`  
**Package run ID:** `i4-20261008-M2`

## Result matrix

| Step | Operation | Result | Exit code | Evidence status |
|---|---|---|---:|---|
| 1 | Readiness / pinned identity | PASS (reported) | Not separately preserved | Summary only |
| 2 | Full M2 verification | PASS (reported) | 0 (reported) | Summary only |
| 3 | Real-M2 integration suite | PASS, 7/7 | 0 | User-pasted test summary |
| 4 | Build serving index | PASS | 0 | User-pasted JSON |
| 5 | Query `RELIANCE EQ` | PASS | 0 | User-pasted result and partial raw output fragments |
| 6 | Rebuild reproducibility | PASS; `identical: true` | 0 | User-pasted JSON |
| 7 | Post-run M2 verification | PASS; 7 checks | 0 | User-pasted JSON |
| Final | Handoff message | Commands completed | — | User-pasted final line |

## Pinned identity

- Repository: `ramkivs/nse-historical-data-engine`
- D24 commit: `69977017ffca944921f231d7904347bc582b6392`
- M2 package: `G:\My Engines\I4_RUNS\i4-20261008-M2`
- State directory: `G:\My Engines\I4_RUNS\d26_serving_state_20261009`
- Run ID: `i4-20261008-M2`
- Manifest SHA-256: `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`
- Total package bytes: `21119807344`
- Post-run manifest entries: `4946`

## Step 3 — Test results

`Ran 7 tests in 1792.186s — OK`

Tests reported:
1. `test_pin_file_count_and_total_bytes`
2. `test_pin_manifest_digest`
3. `test_pin_row_count_matches_run_record`
4. `test_pin_run_and_tool_identity`
5. `test_full_verification_passes_with_pinned_spec`
6. `test_q3_query_over_real_baseline`
7. `test_rebuild_reproducibility`

## Step 4 — Index build

- Result: `pass`
- Instrument pairs: `16107`
- Row count: `5689949`
- Row files: `2462`
- Index SHA-256: `08cad8ce80f6b531700a0adc48af83e434f896df287c219f278daf0acbb19996`
- Manifest SHA-256: `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`
- Partitions: `legacy13/2016` through `legacy13/2024`; `udiff34/2024` through `udiff34/2026`.

## Step 5 — Q3 query

- Query: `RELIANCE EQ`
- Exit code: `0`
- Dated results and provenance fields appear in the supplied partial query-output fragments.
- Full output was not preserved as a single complete raw transcript in this bundle.
- Observed multi-minute runtime; cause unknown.

## Step 6 — Rebuild

- Result: `pass`
- `identical: true`
- Before hash: `08cad8ce80f6b531700a0adc48af83e434f896df287c219f278daf0acbb19996`
- After hash: `08cad8ce80f6b531700a0adc48af83e434f896df287c219f278daf0acbb19996`
- Files scanned: `2462`
- Rows scanned: `5689949`
- Instrument pairs: `16107`

## Step 7 — Post-run verification

- Result: `pass`
- Checks: `verify-01` through `verify-07`
- Manifest entries: `4946`
- Manifest SHA-256: `e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc`
- Total bytes: `21119807344`

## Interpretation boundary

This record consolidates results that the user pasted or reported. It is not a cryptographically signed execution attestation and does not claim Arena independently witnessed the Windows process. The two raw files under `raw_user_supplied/` are partial query-output fragments. The full standalone Step 1 and Step 2 transcripts, and a complete Step 5 transcript, are not present here.

This bundle does not itself close D23 acceptance criteria, publish to Git, or authorize D24 promotion. Arena must reconcile the transferred evidence against the governing repository records and record any gaps explicitly.
