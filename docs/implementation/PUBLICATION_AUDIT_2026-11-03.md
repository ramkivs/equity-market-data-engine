# Workspace publication audit — 2026-11-03

This record inventories the feature branch against remote `main` at audit time
(`69977017ffca944921f231d7904347bc582b6392`). It does not declare B5 complete,
perform B6 Windows validation, promote B7, or alter qualified historical data.
The audited feature tip before this evidence-consolidation commit was
`2fec7a9819aaa39959f66b61920de7b65921be7c` (including the later Q5 work beyond
the previously reported `5cf05a2`).

## Workspace and history

* Git metadata had reset to `6997701` while feature files remained in the
  workspace. A temporary alternate index loaded from the remote feature tip
  found no changed, missing, or additional untracked non-ignored files. The
  current branch/index were restored to that tip without modifying file contents.
* `/home/user` contained only this checkout and standard shell files; no extra
  non-ignored workspace deliverables were found. Git stash/worktree checks found
  no other worktrees or stashed changes. No unreachable Git objects were reported
  by `git fsck --no-reflogs --unreachable` at audit time.
* The D02 feature branch is already an ancestor of the feature tip; the older
  TASK67 feature branch is also an ancestor. The UI-spec and UI-mockup branches
  are not ancestry ancestors, but every branch-specific file is byte-identical
  to the version already in the feature tree. They were not duplicated.
* Two evidence branches contained distinct artifacts not in the feature tree.
  Their evidence is preserved in this consolidation, without accessing M2 or
  rerunning historical Windows validation.

## Completed work carried by the feature history

* D25/D26 readiness investigations; D30–D36 Q1–Q10 serving slices; D37 decision,
  D38 saved-query CRUD, D39 explicit query history; UI specification, mockups,
  TASK60/62/63/64/65/66/67 UI work and associated investigations.
* B1 state/root safeguards; B2 observed-symbol correlation; B3 additive W2
  continuity; B4 application corrections and bounded continuity integration.
* B5 authority and D21 hold, registry and staging, composite publication and
  readers, explicit existing-registry binding, continuity and ticker proofs,
  persistent generation structures, pending-index sealing and recovery, and
  exact-identity Q5 selected-path checks. B5 remains open.

The file inventory below enumerates the complete current feature diff against
`main`, not just the new evidence copied during this audit. Existing base files
and the repository's pre-existing evidence remain tracked on `main` and are not
relisted as additions. The feature history contains 57 commits before this audit.

## Preserved evidence and provenance

* `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/` is copied unchanged
  from `origin/evidence/d26-real-m2-execution-20261009` (`0dda72bef051aa769340badda56997b42a1723f8`).
  All five entries in its original SHA256/size list were checked. Its README
  explicitly distinguishes user-reported/pasted results and partial fragments
  from a complete raw transcript or independently witnessed attestation. These
  historical records concern D24; they are not B5/B6 validation.
* `evidence/I4_UI_CAPTURE_{dashboard,explorer}_1536x1024.png` contains the later
  capture pair from `d9815dfcfe8f6f6428cf11feb2bb29ef728a4f42`, with SHA-256
  `f2b2b98688681582fa90092a6413476b0c73c8cdb2d8fd05fac6dae9ebde076c`
  and `38d8e7c2b770d0e6c82e88bc505752a3a20987c3ef3d88d72d378d2ea6c3fc28`.
* The earlier pair from `1b43e0d8` is also retained, under
  `evidence/i4-ui-visual-acceptance-2026-10-10-original/`, with SHA-256
  `05e6bc0f3dadd6d4d0664632d50e6e1499eb990426e8d76c0e1e62374932f1c4`
  and `35401ce4e82a82c516ce29ca3fe68ce1e95281a441669a53a0188b77f4ed0eed`.
  This is the TASK64 pair, not the separately identified excluded v1.0 image.
  Historical comparisons and their stated acceptance limitations are unchanged.

## Deferred and incomplete

B5 remains open: (1) affected identity/ticker groups still grow and are rewritten
as whole groups; (2) candidate and composed-index metadata are still materialized
on selected snapshots; (3) ticker-only Q5 still validates complete derived
reference censuses; (4) no safe obsolete-node reclamation protocol exists for all
pinned readers. B3 large-data resource behavior, long-run storage bounds,
Windows/B6 validation, and B7 promotion remain unproven or out of scope. D21
changed-content holds remain binding. Registry location must be explicitly known;
no unbound registry location was inferred. See `B5_CATALOG_PUBLICATION.md`.

Audit-time full Linux test run on the feature and staged evidence: 1,129 run, 14 skipped, OK;
the skipped real-M2-gated tests were not run here. Prior one-off 30-publication
synthetic experiment is not a qualified-M2 or long-duration scale proof. The
repository has no `.github` workflow files; hosted required-check status must be
read from the pull request and must not be inferred from this local run.
Historical evidence retains its original CRLF bytes and Markdown hard-break
spaces, which `git diff --check` reports as whitespace; these bytes are kept
unchanged to preserve the original evidence hashes.

## Changed-file inventory

- `.gitignore`
- `docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md`
- `docs/design/I4_HISTORICAL_DATA_ENGINE_UI_SPEC.md`
- `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/D26_REAL_M2_WINDOWS_EXECUTION_RESULTS.md`
- `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/README.md`
- `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/SHA256SUMS.txt`
- `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/execution_summary.json`
- `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/raw_user_supplied/step5_query_output_fragment_A.txt`
- `docs/evidence/D26_REAL_M2_WINDOWS_EXECUTION_2026-10-09/raw_user_supplied/step5_query_output_fragment_B.txt`
- `docs/implementation/B1_FINAL_CLOSURE.md`
- `docs/implementation/B1_ROOT_CONFIGURATION_FOLLOWUP.md`
- `docs/implementation/B1_STATE_SAFETY_EXECUTION.md`
- `docs/implementation/B2_SERVING_SYMBOL_CONTINUITY.md`
- `docs/implementation/B3_W2_ASSOCIATION_CONTINUITY.md`
- `docs/implementation/B4_APPLICATION_WORKFLOW.md`
- `docs/implementation/B5_AUTHORIZED_INCREMENTAL_PROGRESS.md`
- `docs/implementation/B5_BOUNDED_COMPOSITE_APPLICATION.md`
- `docs/implementation/B5_CATALOG_BOOTSTRAP.md`
- `docs/implementation/B5_CATALOG_IDENTITY_PROOFS.md`
- `docs/implementation/B5_CATALOG_PUBLICATION.md`
- `docs/implementation/B5_COMPOSITE_DRAFT_PROGRESS.md`
- `docs/implementation/B5_INCREMENTAL_GATE_AND_RESTART_VERIFICATION.md`
- `docs/implementation/B5_INCREMENTAL_STAGING_PROGRESS.md`
- `docs/implementation/D30A_Q1_Q2_SERVING_QUERY_SLICE.md`
- `docs/implementation/D30B_ARCHIVE_INVENTORY_Q9.md`
- `docs/implementation/D31_Q7_RECORD_DETAIL.md`
- `docs/implementation/D32_Q8_DATA_QUALITY_VIEWS.md`
- `docs/implementation/D33_Q10_QUALIFICATION_EVIDENCE.md`
- `docs/implementation/D34_Q4_SERVING_QUERY_FILTERS.md`
- `docs/implementation/D35_Q5_IDENTITY_ASSOCIATION_QUERIES.md`
- `docs/implementation/D36_Q6_CALENDAR_QUERIES.md`
- `docs/implementation/D38_SAVED_QUERY_CRUD.md`
- `docs/implementation/D39_QUERY_HISTORY_SLICE.md`
- `docs/implementation/PUBLICATION_AUDIT_2026-11-03.md`
- `docs/implementation/TASK62_FIRST_RELEASE_UI_IMPLEMENTATION.md`
- `docs/implementation/TASK65_I4_UI_ACCEPTANCE_DEFECT_CORRECTION.md`
- `docs/investigations/D25_REAL_M2_INTEGRATION_VERIFICATION.md`
- `docs/investigations/D26_REAL_M2_WINDOWS_EXECUTION_READINESS.md`
- `docs/investigations/D37_SAVED_QUERY_HISTORY_READINESS.md`
- `docs/investigations/TASK53_NEXT_MILESTONE_READINESS.md`
- `docs/investigations/TASK60_UI_PRESENTATION_READINESS.md`
- `docs/investigations/TASK63_WINDOWS_UI_VISUAL_ACCEPTANCE_HANDOFF.md`
- `docs/investigations/TASK64_I4_UI_VISUAL_ACCEPTANCE_COMPARISON.md`
- `docs/investigations/TASK66_TASK65_HANDOFF_REVERIFICATION_WINDOWS_TRANSFER.md`
- `docs/investigations/TASK66_WINDOWS_I4_UI_VISUAL_ACCEPTANCE_RERUN_COMPARISON.md`
- `docs/investigations/TASK67_I4_UI_PAGE_EXCLUSIVITY_MOCKUP_PARITY_NAVIGATION_SCOPE.md`
- `evidence/10y historical engine-data explorer.png`
- `evidence/10y historical engine.png`
- `evidence/I4_UI_CAPTURE_dashboard_1536x1024.png`
- `evidence/I4_UI_CAPTURE_explorer_1536x1024.png`
- `evidence/I4_UI_MOCKUP_REFERENCES.txt`
- `evidence/i4-ui-visual-acceptance-2026-10-10-original/I4_UI_CAPTURE_dashboard_1536x1024.png`
- `evidence/i4-ui-visual-acceptance-2026-10-10-original/I4_UI_CAPTURE_explorer_1536x1024.png`
- `src/serving/__init__.py`
- `src/serving/archive.py`
- `src/serving/atomic.py`
- `src/serving/baseline.py`
- `src/serving/candidate_tree.py`
- `src/serving/catalog_publication.py`
- `src/serving/cli.py`
- `src/serving/composite_binding.py`
- `src/serving/composite_blobs.py`
- `src/serving/composite_index.py`
- `src/serving/composite_readers.py`
- `src/serving/continuity_catalog.py`
- `src/serving/continuity_view.py`
- `src/serving/detail.py`
- `src/serving/history.py`
- `src/serving/identity_proof_tree.py`
- `src/serving/incremental_drafts.py`
- `src/serving/incremental_publication.py`
- `src/serving/incremental_registry.py`
- `src/serving/incremental_staging.py`
- `src/serving/index.py`
- `src/serving/paths.py`
- `src/serving/pending_queue.py`
- `src/serving/persistent_index_map.py`
- `src/serving/qualification.py`
- `src/serving/quality.py`
- `src/serving/query.py`
- `src/serving/rebuild.py`
- `src/serving/saved.py`
- `src/serving/symbols.py`
- `src/serving/ticker_delta_trees.py`
- `src/serving/ticker_proof_tree.py`
- `src/serving/ticker_proofs.py`
- `src/serving/w2_continuity.py`
- `src/ui/__init__.py`
- `src/ui/__main__.py`
- `src/ui/api.py`
- `src/ui/derive.py`
- `src/ui/serve.py`
- `src/ui/static/app.css`
- `src/ui/static/app.js`
- `src/ui/static/index.html`
- `tests/serving_fixtures.py`
- `tests/test_b1_atomic_directory.py`
- `tests/test_b1_root_configuration.py`
- `tests/test_b1_state_safety.py`
- `tests/test_b2_continuity.py`
- `tests/test_b2_symbol_observation.py`
- `tests/test_b3_w2_continuity.py`
- `tests/test_b4_workflow.py`
- `tests/test_b5_application_readers.py`
- `tests/test_b5_candidate_tree.py`
- `tests/test_b5_catalog_bootstrap.py`
- `tests/test_b5_catalog_identity_proofs.py`
- `tests/test_b5_catalog_publication.py`
- `tests/test_b5_composite_scoped_readers.py`
- `tests/test_b5_derived_reference_trees.py`
- `tests/test_b5_detached_delta.py`
- `tests/test_b5_detached_identity_groups.py`
- `tests/test_b5_detached_overrides.py`
- `tests/test_b5_existing_restart.py`
- `tests/test_b5_identity_proof_tree.py`
- `tests/test_b5_index_overlay.py`
- `tests/test_b5_lifecycle_e2e.py`
- `tests/test_b5_pending_queue.py`
- `tests/test_b5_persistent_index_tree.py`
- `tests/test_b5_reference_trees.py`
- `tests/test_b5_registry_binding.py`
- `tests/test_b5_targeted_tickers.py`
- `tests/test_b5_ticker_delta.py`
- `tests/test_b5_ticker_delta_trees.py`
- `tests/test_b5_ticker_proof_tree.py`
- `tests/test_incremental_drafts.py`
- `tests/test_incremental_publication.py`
- `tests/test_incremental_registry.py`
- `tests/test_incremental_staging.py`
- `tests/test_serving_archive.py`
- `tests/test_serving_associations.py`
- `tests/test_serving_baseline.py`
- `tests/test_serving_calendar.py`
- `tests/test_serving_detail.py`
- `tests/test_serving_filters.py`
- `tests/test_serving_history.py`
- `tests/test_serving_m2_integration.py`
- `tests/test_serving_qualification.py`
- `tests/test_serving_quality.py`
- `tests/test_serving_query.py`
- `tests/test_serving_saved.py`
- `tests/test_ui_api.py`
- `tests/test_ui_boundary.py`
- `tests/test_ui_dashboard_render.py`
- `tests/test_ui_derive.py`
- `tests/test_ui_http.py`
- `tests/test_ui_page_exclusivity.py`
- `tests/ui_page_exclusivity_harness.js`
- `tests/ui_render_harness.js`
