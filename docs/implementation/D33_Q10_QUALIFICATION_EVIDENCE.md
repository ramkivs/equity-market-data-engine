# D33 — Q10 QUALIFICATION AND EVIDENCE VIEWS

## 1. Task identity and purpose

**D33** — the next serving slice under the standing **D23** authority (D24 §18
"remaining authorized work (b) Q1–Q2, Q4–Q10 and saved-query state per D16-10 —
no new authority required"), building on D30a (Q1/Q2), D30b (Q9), D31 (Q7),
and D32 (Q8), reusing the D30b Q10 contract assessment and the published
implementations.

This slice implements **Q10 qualification/evidence views** (D16-10 Q10:
"qualification/evidence views (run identity, fingerprints, manifests,
R6/D11/D12/D14 records)"):

* **Package-provided data** — run identity, composite identity, engine/runner
  identities (fingerprints), configuration fingerprints, manifest digest and
  archive-set information, `RUN_RECORD`/`RUN_COMPLETE` as published, and
  `GOVERNED_INPUTS` — only fields actually present, with absent values kept
  distinct from zero/empty/null;
* **Pinned identity** — the evidence-derived pins enforced by
  `open_baseline` (verify-07), composed, not recomputed;
* **Durable in-repository evidence** — the R6 replay-qualification verdict,
  the D11 replay-qualification evidence (transfer + publication pin), the D12
  I4 closure decision, and the D14 I5 authority decision, identified at their
  pinned in-repository locations and associated with the selected
  package/run **by verified identity only**;
* an explicit **package-versus-repository-evidence boundary** in the response
  schema — repository evidence is never claimed to be embedded in the
  package, and no synthetic/unpinned package is ever represented as
  qualification evidence for the M2 baseline.

No new authority is requested. Q1/Q2/Q3/Q7/Q8/Q9 semantics are unchanged;
Q4–Q6, saved queries, UI/transport, incremental ingestion, D21 machinery,
raw-content serving, and every other boundary remain untouched.

## 2. Authoritative baseline and repository identity

| Item | Value |
|---|---|
| `origin/main` (remote-verified) | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged by this task |
| Session branch at work | `arena/9021d1a1-nse-historical-data-engine` at `3af1a6a78f00a2ea6f0385348355af78b3792df3` (D32, parent D31 `7bb8ebe2…`); this slice commits on top |
| Evidence branch (remote-verified via `ls-remote`) | `evidence/d26-real-m2-execution-20261009` at `0dda72bef051aa769340badda56997b42a1723f8` — unchanged |
| Local state | 24th sandbox `.git` rollback found at task start (HEAD `89ce965…`, re-shallow, stale `M` files, lost remote-ref cache). Established non-destructive procedure: `git fetch --unshallow origin` → D32/D31 objects present → ancestry D31→D32 = YES → **full worktree byte audit** (every file of the D32 tree via `hash-object` vs remote blob) = 0 missing, 0 differing → `update-ref` → `read-tree` → mixed `reset` (ref/index only). No clean/restore/force/branch-switch; no remote ref moved; worktree clean except pre-existing untracked `_transfer_delivery/` (preserved, never committed). A second, unrelated session branch (`arena/01a10c83…`, PR #1) appeared on the remote and was left untouched |

Real-M2 facts used (verified from the repository-durable D11 transfer
evidence and the I4 runner): `RUN_RECORD` carries `run_id`,
`composite_run_identity`, `config` (`config_fingerprint`, `spec_version`),
`engine_identity` (17 modules, `tool_sha256 d3269b73…`),
`runner_identity` (6 modules, `runner_sha256 f3ebf624…`), `corpus`
(`archive_count 2462`, `archive_set_digest 54d81507…`, partition definition),
`counts`, `authority`, `boundary`, `verification` (artifact classes, 14
preflight checks, reconciliation 39,402); `GOVERNED_INPUTS.json` carries
`contract_version`, `run_id`, `files`, `corpus`, `engine_identity`,
`runner_identity`, `governed_config`, `config_fingerprint`,
`partition_definition`, `composite_run_identity`, `declared_expectations`,
`hash_basis_notes`.

## 3. D23 authority and scope

Implemented within D23 §8/§10/§17(a) and the standing D24 §18(b) remainder
list. D23 §9 exposure boundary respected — Q10 serves processing metadata and
evidence (the D16-08 evidence class); no canonical row values or raw content
are involved. D23 §12 class-(4) rules respected — Q10 creates no state; it
reads package records and in-repository evidence only.

## 4. Q10 — exact contract

Public API: `serving.query_qualification(baseline, repo_root=None) -> dict`
(query id `Q10-qualification`). CLI: `qualification --package <root> [--m2]
[--repo <root>]` (no `--state`; `--repo` optional).

**Package section** (as published, key-driven — absent fields stay absent,
never zero/empty/null):

* `run_identity` — `run_id`, `composite_run_identity`, `contract_version`,
  `config` (configuration fingerprint + spec version);
* `engine_identity`, `runner_identity` — fingerprints exactly as published
  (module facts, tool/runner sha256, versions);
* `corpus` (archive count, archive-set digest, partition definition/list,
  root labels when present), `counts`, `authority`, `boundary`,
  `verification` (as present);
* `run_complete` — the completion marker as published;
* `governed_inputs` — `{present, data}` (data as published; absent file =
  `{present: false}`, no substitution);
* `manifests` — `package_manifest_sha256` (the verified manifest digest),
  `archive_set_digest` (as present), `package_name` (pinned spec only),
  `file_count` (verified: manifest entries + manifest + marker),
  `total_bytes` (verified).

**Pinned-identity section** — the `BaselineSpec` pin values (evidence-derived,
"never from the package being opened") exactly as `open_baseline` enforces
them (verify-07). Unpinned handle → explicit `pinned: false` with the note
that it must not be treated as the qualified M2 baseline.

**Evidence section** — each of the four durable records:

* **R6** — `D11_R6_REPLAY_QUALIFICATION_VERDICT.json` inside the pinned D11
  transfer tarball. Identity taken from the verdict's `packages.a` (run id,
  composite run identity) and `revision` (engine fingerprint, corpus
  archive-set digest, revision commit) blocks; `result`/`failures` served as
  published; association by identity against the verified package RUN_RECORD.
* **D11** — `evidence/D11_REPLAY_QUALIFICATION_20261009/` (publication pin +
  transfer tarball). Publication pin parsed label-anchored (tarball sha256,
  engine revision, engine/runner fingerprints, M2 run, replay run); the
  tarball's computed sha256 is verified against the published pin;
  association by run id + engine/runner fingerprints.
* **D12** — `docs/investigations/D12_I4_CLOSURE_DECISION.md`. Label-anchored
  extraction of the full 64-hex identity pins it carries (composite run
  identity, corpus archive-set digest, R6 verdict sha256); the pinned R6
  verdict sha256 is cross-verified against the verdict bytes read from the
  D11 tarball.
* **D14** — `docs/investigations/D14_I5_AUTHORITY_DECISION_10YEAR_FULL_QUALIFICATION.md`
  — an **authority record** (it governed the execution); it carries no
  run-identity binding, so its state is `not-identity-bound` (applicability
  by governance, never by identity).

**Association states** (every state derived from verified record content;
never from filenames): `associated` (present + all parseable identity
bindings agree, at least one parseable), `not-associated` (present + a
parseable binding disagrees, or no binding parseable), `absent` (record not
found at its pinned location), `integrity-mismatch` (present + the record's
own pinned digest disagrees with its bytes), `unreadable` (present + not
parseable), `not-identity-bound` (D14). Without `--repo`, every record is
explicitly `absent` — never inferred.

**Fail-closed** (no partial output; all checks before any result):

* `run-identity` — RUN_RECORD without usable `run_id`/
  `composite_run_identity`; RUN_COMPLETE `run_id`/`contract_version`
  disagreeing with RUN_RECORD;
* `identity-binding` — GOVERNED_INPUTS identity (run id, composite, corpus
  digest, engine/runner fingerprints, config fingerprint) disagreeing with
  RUN_RECORD; `engine_module_count` vs `len(engine_modules)`;
  `corpus.archive_count` vs `counts.members` or the partition member sum;
* `manifest-digest` — RUN_COMPLETE `package_manifest_sha256` vs the verified
  manifest digest;
* `reconciliation-aggregate` — RUN_RECORD `verification.reconciliation`
  disagreeing with the RUN_COMPLETE marker block;
* `governed-inputs` — malformed present GOVERNED_INPUTS;
* `qualification` — bad `repo_root`.

Contradictory **pinned** identities (manifest digest, run id, composite,
fingerprints, archive count, file count/bytes) are rejected at open
(verify-07) before any Q10 output can exist. Read-only: Q10 opens at most
`GOVERNED_INPUTS.json` from the package and the pinned in-repository evidence
files; it writes nothing. Deterministic for a given package + repository
state; no clock/host/randomness.

## 5. Reuse (no duplicate parsers)

* `open_baseline` — package verification (verify-01..07) and the pinned
  identity enforcement; Q10 composes `Baseline.manifest_digest`,
  `manifest_entries`, `run_record`, `marker`, `spec`, `total_bytes` —
  nothing recomputed.
* `verify` CLI — the pinned values Q10 reports are the same values
  `verify`/open enforce.
* Q8/Q9/D31 error (`QueryError`), envelope, and canonical-JSON conventions;
  `sha256_file` from the baseline module.
* No fixture changes were needed: the D30b-aligned fixture already publishes
  a RUN_RECORD, RUN_COMPLETE, GOVERNED_INPUTS, and manifests; Q10's
  presence-guarded design works over both the fixture's (subset) schema and
  the real M2 schema.

## 6. Changed-file inventory (content digests, git blob identity)

| File | Content SHA-256 | Lines | Change |
|---|---|---|---|
| `src/serving/qualification.py` | `b31f3948b427617f8ebba0a860ddfcee7e53e4a9f93c8fd32e8fd005f3c95801` | 541 | **new** — Q10 query, package/pinned/evidence sections, fail-closed bindings, evidence association |
| `src/serving/__init__.py` | `2d7b17547589839db6969af240c2392c19a85fa86838f7f1a1b2bbb4d206fd99` | 120 | exports Q10 API; boundary docstring mentions Q10 |
| `src/serving/cli.py` | `e98bff374ea258de30c653aa2b4803ca4f9cbfc502cfdced6eb455e685a8e055` | 321 | `qualification` subcommand (`--package`, optional `--m2`, optional `--repo`); docstring |
| `tests/test_serving_qualification.py` | `679834fa64a8546eebec1b2fe73c31a7657afd775ef1f3e649fab7dd1ce98b0d` | 424 | **new** — 20 tests (identity composition, fingerprints/manifests, pinned/unpinned, absent-vs-null, GOVERNED_INPUTS, fail-closed bindings, repository-evidence association (real checkout), synthetic-run non-association, D11 integrity mismatch, discipline, regression) |
| `tests/test_serving_m2_integration.py` | `5e26c035aee1690d24150f5e8b20f3000d23b8f19bb28d825b7e4944268b29fe` | 285 | +1 `D24_M2_ROOT`-gated real-package test (Q10 over the actual M2 baseline; evidence association when `D24_REPO_ROOT` is provided, explicit absence otherwise) |
| this record | `docs/implementation/D33_Q10_QUALIFICATION_EVIDENCE.md` | — | new |

Nothing else changed: no engine (`src/nse_engine`), runner (`tools/`), spec,
governance, fixture, D01 evidence, or w2 evidence file was modified.
`tests/serving_fixtures.py` is byte-identical to D32 (digest
`31ef7f8a…`, unchanged). No serving state file is committed.

## 7. CLI — `qualification` subcommand

`python3 -m serving.cli qualification --package <root> [--m2] [--repo <root>]`

* Exit `0` = ok (canonical JSON on stdout); exit `3` = baseline
  verification / Q10 query failure with the JSON fail envelope; exit `2` =
  argparse usage. No partial results on failure.
* `--repo` omitted → every evidence record explicitly `absent` (no inference
  from the package's location or name).
* Read-only vs both the package and the repository.

## 8. Tests executed and exact results (actual, this session)

Runner: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` (house
runner; pytest not installed).

* **Focused (new module)** — `PYTHONPATH=src python3 -m unittest
  tests.test_serving_qualification`: **Ran 20 tests — OK** (20/20 pass):
  package identity composition (all as-published RUN_RECORD blocks + marker);
  fingerprint and manifest values (engine tool_sha256, manifest digest,
  archive-set digest, file count/bytes); pinned identity composed (verify-07
  enforcement noted); unpinned handle explicit (never treated as the M2
  baseline); absent fields stay absent (no `data_lines`/`observations`/
  `verification` fabricated; no JSON nulls in the document);
  GOVERNED_INPUTS present-as-published + explicit absence; contradictory
  RUN_RECORD run id → fail closed (`run-identity`, no partial output);
  contradictory fingerprint binding (GOVERNED_INPUTS vs RUN_RECORD) → fail
  closed (`identity-binding`); engine module count mismatch → fail closed;
  malformed GOVERNED_INPUTS → fail closed (`governed-inputs`); manifest
  digest conflict rejected at open (verify-07); evidence explicitly absent
  without `--repo`; synthetic fixture run vs the real checkout's durable
  evidence → present but `not-associated` (association by identity, never by
  filename; the document never marks the synthetic package qualified); a
  package carrying the M2 run identity associates to the real R6/D11/D12
  records by verified identity (with the D12-pinned R6 verdict sha256
  cross-verified against the verdict bytes); D11 tarball corruption →
  `integrity-mismatch` fail closed; deterministic canonical JSON; package
  byte identity before/after successful and failing operations; Q2/Q3/Q7/
  Q8/Q9 regression coverage (all unchanged after a Q10 operation).
* **CLI smoke** — unpinned fixture: exit 0 (explicit unpinned, evidence
  absent); with `--repo` (this checkout): exit 0 (d11/r6/d12
  `not-associated` for the synthetic run, d14 `not-identity-bound`, tarball
  and R6-sha integrity matches true); bad `--repo` path: exit 3 JSON fail
  envelope.
* **Full suite** — **Ran 613 tests in 75.5s — OK (skipped=9)**. 613 = 592
  (D32) + 20 (new module) + 1 (new gated M2 test). Skipped = 9: the eight
  pre-existing `D24_M2_ROOT`-gated real-package legs **plus the new Q10
  real-package leg** — all gated because `D24_M2_ROOT` is unset in this
  environment; reported as skipped, never as passed. No unrelated
  qualification suite was rerun.

## 9. Real-M2 status — staged, gated, NOT executed here

The qualified M2 baseline (21.12 GB package, `DEFAULT_M2_SPEC`) is **not
provisioned in this environment** (sandbox disk < package size; no Windows
execution from Arena; the Windows-held package is not transferred). The
real-package Q10 leg is implemented and gated in
`tests/test_serving_m2_integration.py::M2RealPackageIntegrationTests::test_q10_qualification_over_real_baseline`
(D24_M2_ROOT-gated like its siblings) and asserts: run identity
(`i4-20261008-M2`, composite `9609c7fc…`), fingerprints (`d3269b73…` /
`f3ebf624…`), corpus (2,462 archives), counts (quarantined 0), manifest
facts, pinned identity, GOVERNED_INPUTS present; and — when `D24_REPO_ROOT`
points at the durable repository — D11/R6/D12 `associated` (tarball sha256
verified, R6 verdict sha256 cross-verified) and D14 `not-identity-bound`;
otherwise the evidence section is explicitly `absent`. Output determinism is
asserted. It executes only where the environment provides the package; until
then it is reported **skipped (pending baseline provisioning), not passed**.

## 10. Non-drift statement (D23 §18 items 5/12)

* **Read-only vs the package:** Q10 opens at most `GOVERNED_INPUTS.json`;
  `test_package_byte_identity` digests every package file before and after a
  successful **and** a failing Q10 call — byte-identical. The repository is
  opened read-only (evidence files only) and never written.
* **No canonical-data mutation:** no engine, runner, spec, governance,
  evidence, D01, or fixture file was modified (diff inspection: only the
  five implementation/test files + this record; `tests/serving_fixtures.py`
  unchanged vs D32).
* **Package-versus-repository boundary:** the response schema keeps
  `package` and `evidence` in separate sections with an explicit boundary
  note; repository evidence is never claimed to be embedded in the package;
  the synthetic fixture run is never represented as qualification evidence
  for the M2 baseline (test-verified); no qualification status is ever
  inferred from a filename (test-verified).
* **M2-only contract preserved:** no registry entries, no D21 findings, no
  raw content, no computed analytics beyond as-published values.

## 11. D23 §18 closure-battery delta

* **Item 4 (contract conformance):** Q10 semantics are exactly D16-10 Q10
  (qualification/evidence views: run identity, fingerprints, manifests,
  R6/D11/D12/D14 records) under the D16-08 evidence-class exposure and D21's
  candidate-ineligibility (nothing fabricated; D21 CHANGED resolution
  machinery untouched).
* **Item 8 (query-boundary):** the only new query path is
  `Q10-qualification` inside `serving.qualification`, exposed as the
  `qualification` CLI subcommand. Q4–Q6 and saved queries remain
  unimplemented.
* **Item 10 (tests):** §8 — focused 20/20 OK; full suite 613 executed, OK,
  9 skipped (all `D24_M2_ROOT`-gated real-package legs, reported skipped,
  never passed).
* **Item 11 (complete artifact inventory):** §6 — all artifacts with path
  and content digest; nothing else changed.
* **Item 12 (remote durability):** this commit is fast-forward-only onto
  `3af1a6a7…` on the session branch and is independently remote-verified
  (commit/parent/tree/changed paths/blobs) before this task is declared
  complete; `origin/main` remains `69977017…` (promotion is the user's
  separate step — not performed).

## 12. Final status

D33 (Q10 qualification and evidence views) **COMPLETE** — implementation,
API/CLI, tests, record, single fast-forward commit, remote verification.
Remaining D30b/D31-plan slices (Q4 filtering; Q5 identity/association
queries; Q6 calendar queries; saved-query state) are **not started** and
require their own separately-scoped tasks under the same standing authority.
