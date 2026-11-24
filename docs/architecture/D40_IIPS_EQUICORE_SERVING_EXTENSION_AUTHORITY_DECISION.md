# D40 — IIPS / EQUICORE SERVING EXTENSION AUTHORITY DECISION

## 1. Title / identifier

**D40** — **EquiCore D40 — IIPS Historical Serving Extension Authority Decision** ("D40").

D40 is the authoritative EquiCore governance record for the **IIPS Historical Serving Extension**: the owner-approved extension of EquiCore serving to the IIPS historical serving context. It records the publication, as APPROVED, of four previously approved EquiCore decisions identified **EC-DEC-01 … EC-DEC-04** (§7), under the ownership and personal-use scope of §4.

D40 is a governance/authority decision record only. It creates **no implementation**: no code, no serving index, no IIPS-side change, no configuration, no registry, no migration, no test, and no CI change is created by D40. Where the four decisions describe indexes, serving scope, and exclusions, D40 **approves the authority** to have those implemented under their owning contracts and acceptance gates; it does not itself implement, verify, or permanently freeze their physical realization. Implementation remains bounded by D23, D37, D39, D21, D16, D05, and the non-drift statement of §10.

### 1.1 Publication completeness notice (binding on this publication)

The execution note for this publication directed inspection of the **prepared IRR handoff artifact**:

`docs/integration/artifacts/EQUICORE-D40-IIPS-SERVING-EXTENSION-PREPARED-2026-11-24.md`

**That artifact does not exist in the repository.** A fresh verification at baseline (§5) found:

- no `docs/integration/` directory and no file of that name anywhere in the working tree (tracked or untracked);
- no occurrence of `EC-DEC-01`, `EC-DEC-02`, `EC-DEC-03`, `EC-DEC-04`, `EC-AC-…`, or `D40` in any tracked file;
- no architecture decision register or implementation tracker file (see §9.4).

Accordingly, and deliberately:

1. The four decisions are published as **APPROVED** because their approval is the owner's own explicit instruction of 2026-11-24 (§4, §7); that authorization is honored verbatim.
2. **The original wording of the four decisions beyond their titles, the artifact's conditions, and the full original wording of acceptance criteria `EC-AC-01..05` are not recoverable from this repository or from the execution instruction, and are NOT reproduced, paraphrased as if verbatim, or invented in this record.** They are recorded here as **NOT RECOVERABLE — PENDING RESTORATION** (§8).
3. The repository-grounded readings in §7.1–§7.4 are **derived operational readings** (evidence anchors from the durable repository). They are labeled as derived and carry the authority of this record only to the extent they are consistent with the approved titles; they are **not** the missing artifact's text.
4. Publication of this record is **not** evidence of acceptance-closure. Acceptance under `EC-AC-01..05` remains unverified (§8) until the artifact is supplied or its content is otherwise durably restored.

## 2. Status

**EC-DEC-01 = APPROVED. EC-DEC-02 = APPROVED. EC-DEC-03 = APPROVED. EC-DEC-04 = APPROVED.**

Approval date: **2026-11-24 (24 November 2026)**. Approval authority: **the sole owner and decision-maker of both IIPS and EquiCore** (§4). Approval means the four authorities are granted at the architecture/governance level, subject to the ownership scope of §4 and to the conditions and acceptance criteria of §8. **EC-AC-01..05 are not yet satisfied or verifiable from the repository** (§8). No decision in this record authorises production, hosted, commercial, or multi-user use — ever, under this record.

Record status: **PUBLISHED WITH DECLARED GAPS — NOT ACCEPTANCE-CLOSED.** The known gap is the missing prepared artifact and, consequently, the missing verbatim decision wording, conditions, and `EC-AC-01..05` text (§1.1, §8). This gap is recorded openly and is carried to §11.

## 3. Date

2026-11-24.

## 4. Authority boundary — ownership and application scope (verbatim from the owner, Section 1)

> IIPS and EquiCore are local, single-user applications.
>
> I am the sole owner and decision-maker for both.
>
> The authorization is strictly for personal-use integration.
>
> No production, hosted, commercial, or multi-user deployment is authorized or required.

This boundary is a **hard constraint on every decision in this record**, not a recitation. It means, without exception:

- **Personal-use integration only.** D40 authorises the integration of EquiCore serving into the owner's local IIPS application for the owner's own use.
- **No production use.** No hosted service, no commercial offering, no v1/v2 customer boundary, no SLA, no multi-user access control, no tenancy, no deployment to any shared infrastructure.
- **No multi-user semantics.** D16 §13 non-goals remain in force: no multi-user operational concepts, no roles/permissions, no audit-of-users, no concurrency model beyond the single-user case.
- **Single decision-maker.** There is no committee, no IRR review board, and no second approver. The owner's written instruction of 2026-11-24 is the approving instrument for this record.
- **No authority beyond the four decisions.** D40 does not open any other gate, and grants no authority that D23/D37/D39/D21 withheld.

IRR in this record refers to the **integration readiness / acceptance review loop for the IIPS–EquiCore integration** as designated by the owner; the prepared IRR handoff artifact that normally carries the packaged decision content and its acceptance criteria is the missing artifact identified in §1.1. No IRR role, body, or process beyond what the owner has stated is assumed.

## 5. Authoritative baseline (verified 2026-11-24, read-only)

| Item | Value |
|---|---|
| Repository | `https://github.com/ramkivs/equity-market-data-engine.git` |
| Branch | `arena/ddcaa938-equity-market-data-engine` (EquiCore-owned working branch; not `main`) |
| `HEAD` | `b79cf1d0561c388d0fcd0000503dc93f5a56e584` = Merge pull request #5 into `main`; `main` at same commit |
| Worktree | clean before this publication (`git status --porcelain` empty) |
| Tracked files | 308 |
| MR handoff artifact | **absent** — no `docs/integration/` tree; no `EQUICORE-D40-*` file; no `EC-DEC`/`EC-AC`/`D40` occurrences in tracked content or filenames |
| Register / tracker | **no `EQUI_CORE_ARCHITECTURE_DECISION_REGISTER.md` and no implementation tracker existed** before this publication; the README durable-record index (§9.4) was the only index |
| CI configuration | **no `.github/workflows/` exists** — there is no CI in this repository to run or to fail |
| M2 baseline (as recorded) | package `i4-20261008-M2`; 4,948 files / 21,119,807,344 bytes; manifest `e7c7e4c8271f…`; 5,689,949 rows; 12 partitions; families `legacy13` / `udiff34` (I4/D12, I5/D14) |
| Serving baseline | `serving-index/1.2` (`src/serving/index.py`); `DEFAULT_M2_SPEC` pin (`src/serving/baseline.py`); serving tests 327 passed, 14 skipped (integration fixtures absent) |
| Verification of this publication | this repository's own files only; the physical M2 package (21 GB) and the Windows corpus are not reachable from this sandbox; no claim below depends on them |

## 6. Source records (re-read at baseline)

1. **D23** `docs/architecture/D23_FIRST_RELEASE_SERVING_IMPLEMENTATION_AUTHORITY_DECISION.md` — §15–§17 (safety constraints; GRANTED exhaustive: (a) first-release read-only serving over the qualified M2 baseline, (b) first-release presentation/UI, (c) serving state class (4) — indexes/rollups/saved-query store — rebuildable per D16-07, (d) serving-state rebuild as delegated operation (b), (e) technology selections §12–§14; WITHHELD exhaustive: incremental ingestion, requalification migration, per-instance CHANGED resolution, raw archive content serving, scope change from single-user); §18 (closure evidence requirements); §20 (non-drift). **This is the operative instrument EC-DEC-01 extends.**
2. **D16** `docs/architecture/POST_I5_SERVING_INCREMENTAL_PRODUCT_ARCHITECTURE_AUTHORITY_DECISION.md` — D16-07 (classes (1)–(4); class (4) = serving/derived state, pure derivation of (1)+(2)+(3), rebuildable, conflict rule (1)/(2)/(3) win), D16-08 (five-class exposure; **raw archive content NOT exposed by default**), D16-09 (serving read-only consumer; invariants), D16-10 (Q1–Q10; ISIN = non-identity attribute), D16-12 (first-release scope), D16-13 (implementation authority NOT GRANTED at D16; later-authority enumeration).
3. **D21** `docs/architecture/D21_D16_03A_CHANGED_CONTENT_DISPOSITION_AUTHORITY_DECISION.md` — §14/§15 (permanent explicit-conflict disposition for CHANGED archives), §16 (prior accepted record remains authoritative, intact and in force), §17 (registry CHANGED-CONFLICT-UNRESOLVED state requirements), §18 (serving/trust semantics), §22 (per-instance resolution only by future explicit authority decision), §23 (no implementation authority), §24 (non-goal preservation).
4. **D05** `docs/specs/D05_CANONICAL_MODEL_SPEC.md` — §3.2 (ISIN = **correlation key**, never identity, upper/trim match), §3.3 (DATED symbol/series associations, `observed-range` intervals), §5 (non-gating flags), §6 (identifier treatment), §10 (units/as-published), §11/§12 (registry; non-assumption register).
5. **D37** `docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md` (class-(4) saved-query state boundary) · **D38** `docs/implementation/D38_SAVED_QUERY_CRUD.md` · **D39** `docs/implementation/D39_QUERY_HISTORY_SLICE.md` (saved queries / history are class-(4), rebuildable, single-user).
6. **D24** `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md` and the serving implementation under `src/serving/` (`index.py` class-(4) read model; `baseline.py` M2 pin; `query.py`, `saved.py`, `history.py`, `cli.py`, `rebuild.py`).
7. **D19** `docs/architecture/D19_CHANGED_CONTENT_CONTROLLED_TEST_AUTHORITY_DECISION.md` and **D20** (CHANGED-hold evidence only, no resolution ever observed) — the D21 analogues against which EC-DEC-04 must be read.
8. **README durable-record index** and the audits `docs/implementation/PUBLICATION_AUDIT_2026-11-03.md` and `docs/implementation/EQUICORE_BRANDING_AUDIT.md` (EquiCore product identity, 2026-11-04).

No IIPS-side repository artifact is available to, or cited from, this record. IIPS is referenced only as the owner's local single-user application named in §4.

## 7. Decision statement (the approved decisions — verbatim titles, verbatim status)

> **EC-DEC-01 — D23 serving extension — APPROVED**
>
> **EC-DEC-02 — Class-(4) ISIN/series/date index — APPROVED**
>
> **EC-DEC-03 — Initial M2/NSE_EQ/1D/RAW_UNADJUSTED serving scope — APPROVED**
>
> **EC-DEC-04 — Archive and D21 conflict exclusions — APPROVED**
>
> **Approval date: 24 November 2026. Approval authority: sole owner and decision-maker of both IIPS and EquiCore, for personal-use integration only (§4).**

The wording above is exactly the wording supplied in the owner's execution authorization of 2026-11-24. No other wording of the decisions is claimed.

### 7.1 EC-DEC-01 — D23 serving extension

**Original wording (title-level, as authorized):** "EC-DEC-01 — D23 serving extension — APPROVED".

**Status:** APPROVED, 2026-11-24.

**Operational reading (derived, not verbatim artifact text):** the D23 grant (§17 — GRANTED exhaustive: read-only serving over the qualified M2 baseline; class-(4) serving state) is **extended** to the IIPS historical-serving integration context, subject to every D23 safety constraint (§15–§16) and closure requirement (§18), to the single-user/personal-use boundary of §4, and to the exclusions of EC-DEC-04. The extension enlarges *serving reach* (EquiCore serving consumed by IIPS), not the data granted:

- class (1) remains immutable; no mutation, re-derivation, or re-qualification (D16-07, D23 §15);
- serving remains a **read-only consumer** (D16-09); no query side effect may ever trigger processing, requalification, or publication;
- class (4) remains a **rebuildable derived state** (D16-07); conflict rule (1)/(2)/(3) win — any disagreement against the baseline resolves in favour of the baseline and (4) is rebuilt;
- single-user; personal use; no hosted/commercial/multi-user scope (D23 §16, D16 §13, §4 above);
- **not** authorized by this decision: incremental ingestion, requalification migration, per-instance CHANGED-conflict resolution, raw archive serving, engine/contract mutation, any scope change from single-user (D23 §17 WITHHELD stands), and any promotion of IIPS consuming EquiCore into a shared service.

**Conditions (derived, repository-grounded; artifact conditions NOT RECOVERABLE — §8):** serving consumed by IIPS must identify the M2 baseline by its pinned identifiers; must not weaken D05 as-published semantics or non-gating flags; must not promote ISIN to identity; must not treat D21-unresolved archives as servable; and must remain byte-reproducible class-(4) state (D05 §9, D24).

**Evidence anchors:** D23 §17, §18; D16-08/09/10/12; D24; `src/serving/index.py` INDEX_FORMAT `serving-index/1.2`; `src/serving/baseline.py` DEFAULT_M2_SPEC `i4-20261008-M2`.

### 7.2 EC-DEC-02 — Class-(4) ISIN/series/date index

**Original wording (title-level, as authorized):** "EC-DEC-02 — Class-(4) ISIN/series/date index — APPROVED".

**Status:** APPROVED, 2026-11-24.

**Operational reading (derived):** EquiCore may maintain a **serving state class-(4) index keyed by (ISIN, series, date)** — a derived, rebuildable read model over the qualified baseline and any approved incremental publication — serving ISIN-keyed historical lookup with the series and date dimensions explicit (the exact grain required for as-published daily rows: `(security_isin, series, business_date)`). Binding semantics fixed by D05 and unchanged by this approval:

- **ISIN is a correlation key, never an identity** (D05 §3.2/§6): match normalization = **uppercase + trim only** (`isin_correlation_key_upper_trim`); ISIN↔ISIN only; never a join to other namespaces;
- **series is a dated attribute, not identity** — multi-series ISINs across eras are proven (2,431/7,633); the index must key by series, never collapse it (D05 §3.3);
- **date is the business date as published** (`TradDt` / date-part of `TIMESTAMP`), stored verbatim (D05 §3.1);
- the index is **class (4)**: a pure derivation of (1)+(2)+(3), rebuildable at any time with no loss; deleting it is **never a data event**; disagreement with (1)/(2)/(3) resolves in favour of (1)/(2)/(3) and the index is rebuilt (D16-07);
- values remain **as published** — no rescaling, no defaulting of zeros, non-gating flags carried through (D05 §3.1, §5, §10);
- index construction is an implementation matter recorded elsewhere; this record approves the *authority* for the class-(4) index, not a particular file format, schema, or build schedule.

**Conditions (derived):** index must be checksummed/versioned and rebuildable from the pinned baseline; must refuse to serve against an unidentified or mismatched baseline; must not gate serving on ISIN validity; must not introduce a second source of truth.

**Evidence anchors:** D16-07; D05 §3.1–3.3, §5, §6; D16-10 Q3/Q5; D24 (canonical-JSON class-(4) index + sha256 sidecar as the working pattern); `src/serving/index.py`; D37 (other class-(4) stores follow the same boundary).

**Not authorized:** promotion of ISIN to durable identity; master-snapshot joins (DEC-1 DEFERRED — D06/D13/D16-13); cross-namespace entity resolution; series harmonization across eras; any re-processing of rows to construct the index.

### 7.3 EC-DEC-03 — Initial M2/NSE_EQ/1D/RAW_UNADJUSTED serving scope

**Original wording (title-level, as authorized):** "EC-DEC-03 — Initial M2/NSE_EQ/1D/RAW_UNADJUSTED serving scope — APPROVED".

**Status:** APPROVED, 2026-11-24.

**Operational reading (derived):** the **initial** IIPS–EquiCore serving scope (the first served corpus for the personal-use integration) is bounded to:

- **source dataset: the qualified M2 baseline** — `i4-20261008-M2` (5,689,949 rows; 12 partitions; families `legacy13`/`udiff34`), identified by pinned manifest `e7c7e4c8…` / composite identity `9609c7fc…`; no unapproved publication is served;
- **`NSE_EQ`** — the owner's designation for the NSE equity segment scope. **`NSE_EQ` (and `RAW_UNADJUSTED`) appear nowhere in this repository** (verified: zero occurrences across `src/`, `docs/`, `tests/`). They are IIPS-side scope tokens carried into this approval by the owner, not EquiCore vocabulary. In EquiCore they are honoured **opaquely**: this record does not equate `NSE_EQ` with `Sgmt=CM` or with any stored field, and does not infer eligibility from segment/type (D05 §3.1 `[NON-ASSUMPTION]`: Sgmt/Src/FinInstrmTp are stored descriptively, never as type gates). Any concrete mapping from `NSE_EQ` to canonical field-value sets requires its own explicit, evidence-backed decision — not this record;
- **`1D`** — the daily (end-of-day) frequency scope (one record per instrument per business date). No intraday/minute grain is authorized;
- **`RAW_UNADJUSTED`** — verbatim as-published, unadjusted prices/values, consistent with the standing as-published contract (D05 §3.1, §10; no rescaling, no corporate-action adjustment, no derived return series, no backfill). **`RAW_UNADJUSTED` does not appear in this repository** and authorizes nothing beyond the as-published obligation that already binds EquiCore serving;
- the scope is **initial and exclusive** until the owner extends it by a further explicit decision.

**Conditions (derived):** serve only rows verifiably from the pinned M2 package (or an approved publication under the identical contracts); no raw archive bytes exposed (EC-DEC-04; D16-08); no adjusted/derived series; no performance of adjustment as serving-time computation; non-gating flags shown, never hidden; unknown/blank stays as published.

**Evidence anchors:** D16-12; D23 §8 (read-only serving over M2); D05 §3.1/§10; D24; `src/serving/baseline.py` (pin); `docs/implementation/D24_FIRST_SERVING_VERTICAL_SLICE.md` (M2 identifiers and partition counts).

**Not authorized:** adjusted-close or total-return series; intraday grain; non-M2 sources in the initial scope; other exchanges/segments; any widening of scope without a further explicit owner decision.

### 7.4 EC-DEC-04 — Archive and D21 conflict exclusions

**Original wording (title-level, as authorized):** "EC-DEC-04 — Archive and D21 conflict exclusions — APPROVED".

**Status:** APPROVED, 2026-11-24.

**Operational reading (derived):** the served IIPS historical scope **excludes**, by approval and by standing contract together:

**(a) Archive exclusion.** Raw archive content — archive bytes, member-level raw text, zip/tar payloads — is **never served**. Serving exposes canonical rows and their provenance metadata (archive name, sha256, INPUT_MANIFEST facts), never the archive itself. This restates D16-08 (raw not by default; OUT OF SCOPE absent a future explicit decision plus cross-environment mechanism) and the Windows/Arena environment boundary (raw corpus is in Windows custody; this repository never rewrote it and this record does not change that).

**(b) D21 conflict exclusion.** Any archive in the **CHANGED-CONFLICT-UNRESOLVED** state under D21 is **excluded from serving** and from any automatic processing, publication, or index build. Specifically: a changed candidate that fails to match the previously accepted record by content sha256 is (i) not served, (ii) not indexed by EC-DEC-02, (iii) never a query result, and (iv) the **previously accepted canonical data remains authoritative, intact, and fully in force and visible** under its own qualification record. No requalification, replacement, superseding, or invalidation occurs except through the D21 §22 per-instance explicit authority decision. No such conflict has ever been observed or resolved (D20; D21 §14 position 1) — the exclusion is preventive governance.

**(c) Derived consequence.** Serving never fabricates coverage across exclusions: absent rows caused by exclusions remain absent; unresolved-state records remain visible as quality views (Q8) per D16-10; exclusion is never silently papered over in the UI/API.

**Conditions (derived):** index builds must skip excluded archives fail-closed; serving must expose the exclusion state (conflict census/unresolved-state view) rather than hide it; an excluded archive cannot re-enter scope without (1) an explicit owner authority decision and (2) the qualification evidence for its replacement publication.

**Evidence anchors:** D16-08; D21 §14–§22; D20; D23 §17 (WITHHELD raw-content serving and CHANGED resolution); D16-10 Q8/Q9; `src/serving/index.py` (serving-index built over the qualified package only).

## 8. Conditions and acceptance criteria EC-AC-01..05 — NOT RECOVERABLE, NOT INVENTED

The execution instruction directs this publication to record "their original wording, conditions and acceptance criteria `EC-AC-01..05`." **The original wording of `EC-AC-01..05` is not available** to this publication: the artifact carrying it (§1.1) does not exist, and no tracked file mentions it. Consistent with the repository's own discipline — *a gap is recorded, never filled silently* — the following holds:

- **No `EC-AC-01..05` text is reproduced or paraphrased.** None is present here, and none may be cited by reference to this record as if it had been published.
- The four decisions remain **APPROVED** as owner-instructed (§2, §7). Approval of authority is distinct from acceptance of delivery; **acceptance under `EC-AC-01..05` is not attested by this record and nothing in this record closes, waives, or self-certifies any acceptance criterion.**
- The **conditions** binding the four decisions are, in this publication, those derived from D23/D21/D16/D05 and the ownership boundary (§4, §7.x). If the artifact's conditions are narrower/different, the artifact (once restored) governs and this record must be amended accordingly — see §11.
- **To close:** supply `docs/integration/artifacts/EQUICORE-D40-IIPS-SERVING-EXTENSION-PREPARED-2026-11-24.md`, or re-state `EC-AC-01..05` verbatim in writing; then D40 must be **amended in a follow-up commit/PR** with the verbatim criteria, their mapping to EC-DEC-01..04, the original conditions, and the verification evidence. Until then, any statement that "EC-AC-01..05 are met" is false.

## 9. Decision register and tracker updates

### 9.1 Register

A new, durable register is created by this publication:

`docs/architecture/EQUI_CORE_ARCHITECTURE_DECISION_REGISTER.md`

It indexes the EquiCore authority/decision records present on this branch as of 2026-11-24 (D05 spec; D16; D19; D21; D23; D37; D40) with identifiers, dates, statuses and paths, and records the standing absences (no IIPS-side artifact; no CI). It is the reference the execution instruction called "the EquiCore architecture decision register"; it did not exist before, and its creation is part of this publication.

### 9.2 Tracker

**No EquiCore implementation tracker file exists in the repository** and none is silently fabricated by this publication. The durable, in-repo index of record status is the README ("Durable project record index"), which is updated by this publication with the D40 line (§9.3). If a dedicated publication/acceptance tracker is wanted for the IRR loop (tracking EC-AC-01..05 to closure), it should be specified by the owner and created when the artifact is restored — it cannot truthfully contain acceptance evidence yet.

### 9.3 README durable-record index

`README.md` gains one bullet referencing D40 (and the register). No historical entry is altered.

### 9.4 Nothing else changed

No engine, serving, spec, evidence, or test file is modified. No `.github/workflows/` is added (and nothing herein constitutes an authorization to add CI; `§12.4`). Exact file list in §11.

## 10. Non-drift statement

D40 does **not** modify, reinterpret, or re-open D16, D21, D22, D23, D37, D38, D39, D05, D08, D12, D14, D19, D20, or the intent record. D14's non-authorizations stand. D16-13 stands (implementation authority granted only by later decisions — D23 granted the first release; D40 grants the four authorities of §7 and no others). D21 §22 stands (per-instance CHANGED resolution only by its own explicit authority decision). D05 stands (ISIN is never identity; values as published; flags non-gating). The environment boundary stands (raw corpus in Windows custody; no IIPS repository is reachable or modified from here). Single-user personal-use scope stands universally (§4). No canonical data, package, inventory, or evidence artifact was touched. The only mutations are the three files listed in §11.

## 11. Artifact inventory

This publication creates or modifies **exactly three files**:

1. `docs/architecture/D40_IIPS_EQUICORE_SERVING_EXTENSION_AUTHORITY_DECISION.md` — this record (**new**).
2. `docs/architecture/EQUI_CORE_ARCHITECTURE_DECISION_REGISTER.md` — the architecture decision register (**new**).
3. `README.md` — durable-record index gains exactly one bullet (**modified**).

Not created/modified: the prepared artifact (missing), any engine/serving/UI code, any test, any CI workflow, any evidence/data artifact, any IIPS-side file, any historical record.

## 12. Verification record

### 12.1 Presence and negative searches (at baseline, before changes)

- `ls docs/integration/artifacts/EQUICORE-D40-IIPS-SERVING-EXTENSION-PREPARED-2026-11-24.md` → **No such file or directory**.
- `find . -type d -name integration` and `-name artifacts` → none.
- `find /home/user -iname '*D40*' -o -iname '*EQUICORE-D40*' -o -iname '*SERVING-EXTENSION*'` → none.
- `grep -ri "EC-DEC\|EC-AC\|D40"` over tracked text files → **zero** D40/EC-DEC/EC-AC hits (only unrelated `*_integration.py` filenames matched).
- `git ls-files | grep -i "d40\|integration"` → none.
- `find . -iname '*tracker*' -o -iname '*register*'` → no register/tracker file (only unrelated mentions).

### 12.2 Repository state

- `git status --porcelain` clean at baseline; branch `arena/ddcaa938-equity-market-data-engine`; `HEAD` `b79cf1d0…` (= `main`).
- CI: `.github/workflows/` **absent** — nothing to run; no CI result is claimed. See §12.4.

### 12.3 Build/test spot checks (non-mutating, at baseline)

- `python3 -m compileall -q src` → OK.
- `PYTHONPATH=src python3 -m unittest discover -s tests -t . -p "test_serving_*.py"` → **Ran 327 tests — OK (skipped=14)** (14 skips: integration fixtures requiring the physical M2 package, which is not in this sandbox).

### 12.4 CI

**No CI exists in this repository** (`.github/` absent). Consequently step-7 "verify CI results" has no local artifact; the PR will show no checks. Adding CI is out of scope of the execution instruction and is not authorized here. Any CI observed on the PR (e.g., repository defaults) is reported as observed, not as a D40 claim.

### 12.5 Post-change verification

Completed after commit — see §13 and the PR body: (1) committed file present with expected content; (2) register and README reference D40; (3) PR diff contains exactly §11's three files; (4) working tree clean.

## 13. Remaining steps / acceptance (owner actions)

1. **Restore the missing artifact** (or re-state its content in writing) at the exact expected path; verify `EC-AC-01..05` verbatim.
2. **Amend D40** with verbatim criteria/original wording/conditions and record acceptance evidence; until then D40 remains PUBLISHED WITH DECLARED GAPS (§2), and no acceptance/closure claim may cite it.
3. **Create/specify the IRR publication tracker** if wanted (§9.2).
4. **Merge the PR** targeting `main` (owner action; this publication does not merge).
5. **IIPS-side steps** (outside this repository): wire IIPS to consume the class-(4) ISIN/series/date index under the pinned M2 baseline with EC-DEC-04 exclusions enforced; verification there is the IRR loop's responsibility.
6. Any widening beyond EC-DEC-03's initial scope, any adjusted series, any per-instance CHANGED resolution — each requires its own explicit owner decision recorded in this house pattern.
