# TASK 60 — Serving UI / presentation readiness

**Mode:** read-only investigation and implementation readiness. **No implementation**
(no UI code, no transport, no technology selection, no fixture/package change).
**Publication scope:** session branch only. No main promotion.

---

## 1. Verified baseline and checkout disposition

| Item | Value |
|---|---|
| `origin/main` | `69977017ffca944921f231d7904347bc582b6392` = D24 — unchanged (ls-remote, before and after) |
| Session branch `arena/9021d1a1-nse-historical-data-engine` | `d9d32ab0b91c6ca732ed0dcdd4bdecbd5d1ff50b` = D39 (remote = expected) |
| D37 governance decision | `b39e8660c609c91dbf9c8fb84613eecc4b23dc9b` (present, ancestor) |
| D38 saved-query CRUD | `504f628e59a42d28086834d9f965ee50fdb60426` (present, ancestor) |
| Evidence branch `evidence/d26-real-m2-execution-20261009` | `0dda72bef051aa769340badda56997b42a1723f8` — unchanged |
| Unrelated session branch `arena/01a10c83-nse-historical-data-engine` | `db604063…` — observed, not touched |
| Checkout at task start | **32nd sandbox `.git` rollback** (HEAD `89ce965…` shallow, stale `M`); established non-destructive procedure: `fetch --unshallow` → key objects present → 16-commit ancestry chain D24→D39 all YES → **full worktree byte audit vs the D39 tree (194 files: 0 missing, 0 differing)** → ref/index-only recovery; `_transfer_delivery/` preserved; no remote ref moved |

## 2. Governing sources inspected (verbatim where decision-relevant; prior findings reused)

* **D16-11 (UI/product boundary):** UI owns "presentation, navigation, query
  construction (Q1–Q10), result display, status/evidence display, report
  presentation, user interaction, **saved-query management**"; must NOT own parsing,
  classification, processing, validation, evidence generation, publication, registry
  mutation, derived-state re-derivation, or direct durable-data access (always via
  serving); may expose exactly two delegated operations — (a) archive
  discovery/processing trigger, (b) **serving-state rebuild** — "everything else is
  read-only through serving"; "**Target presentation: the demonstrated I4 application
  (non-drift #12)**"; implementation boundary = "Ownership boundary only — no UI
  technology, no screens, no code."
* **D16-12 (first-release scope):** first release = "**read-only serving +
  presentation over the qualified M2 baseline**": Dashboard = the demonstrated
  reference tiles whose data backing D15 verified; Data Explorer = "query categories
  Q1–Q10 with record detail + provenance, quality views, yearly summaries, and
  as-published price/field display (charts over as-published values)"; "Saved queries
  + query history (serving state 4)"; explicitly excluded: incremental-processing
  operation, raw-content serving, DEC-1/eligibility.
* **D22 §8 (UI-readiness assessment):** no UI of any kind exists in-repo; the
  data backing for every demonstrated tile/capability EXISTS at durable level;
  "its mockups exist **outside the repository** (another environment/conversation) …
  D15 states it explicitly: it 'does not claim to have inspected the mockups
  themselves.' The target reference (non-drift #12) and the first-release scope
  (D16-12) are therefore fixed by governing records … **a known, accepted boundary,
  not an evidence gap**"; "No frontend technology is selected (TECHNOLOGY =
  UNDECIDED, D16 §14)".
* **D23 §13/§14 (delegation):** technology selection is DELEGATED to implementation
  "for every technology selection within the authorized scope (serving store/
  read-model; query mechanism; **frontend/presentation technology;
  hosting/runtime**)"; nine binding constraints (single-user/personal-use; no
  auth/RBAC/multi-user; no PostgreSQL/enterprise DB; class-(4) consistency; canonical
  data not reinterpreted/mutated; rebuildable state; MD-10 grading for physical
  persistence; recording with constraint-compliance rationale; no live market-data
  access). §14: "Frontend: bounded by D16-11/12 (Dashboard tiles + Data Explorer
  Q1–Q10 + saved queries); target intent = the demonstrated I4 application."
* **D23 §17 (GRANTED, exhaustive):** includes "**(b) the first-release
  presentation/UI within D16-11/12** (target intent: the demonstrated I4
  application)" and "(e) the technology selections of §13/§14, made within bounded
  criteria and recorded".
* **D23 §18 (closure battery):** item 3 (technology decisions recorded), item 8
  ("serving executes only Q1–Q10 + saved-query semantics; **no other query path
  exists**"), item 9 ("**UI boundary proof** — the UI reads only through serving; no
  direct durable-data access; no engine-state ownership; only delegated operation (b)
  is exposed"), item 10 (tests), item 11 (artifact inventory with digests), item 12
  (remote durability + independent verification).
* **D23 §19 (excluded/deferred):** incremental ingestion; per-instance CHANGED
  resolution; requalification migration; MD-12 physical concerns other than
  class-(4); **raw archive content serving** (requires a future explicit decision +
  cross-environment mechanism); DEC-1; any single-user scope change.
* **D15 §14 (UI/presentation findings, POST_I5 investigation):** the data-availability
  mapping for every Dashboard tile and Data Explorer capability ("data EXISTS" at
  durable level); explicit boundaries: "**source row → not recorded** (row offsets
  never adopted)"; "**raw record access → verbatim field values + pinned hashes; raw
  bytes stay in Windows custody** (environment boundary)"; "archive access →
  inventory + hash facts (metadata EXISTS; bytes out of Arena reach)".
* **Intent §9 (Presentation / UI Target):** "The supplied I4 application mockups
  establish the target presentation direction. The future presentation layer should
  remain **close to the demonstrated application**"; Dashboard direction (16
  reference bullets); Data Explorer direction (27 reference bullets) — "presentation/
  product reference points, not a claim that every element is already contractually
  defined".
* **Task 53 (readiness):** "Dashboard / Data Explorer presentation (D16-11/12;
  **D23 §17(b) authorized**; technology UNDECIDED, selection delegated D23 §13/§14) —
  NOT STARTED"; "TECHNOLOGY for UI/transport: UNDECIDED; selection is delegated …
  **it is not a pending user decision**"; D23 §18 item 9 "UI-boundary proof pending
  UI".
* **D30a–D39 (implementation contracts, reused — not re-investigated):** the current
  serving surface (verified live in this task): CLI subcommands
  `{verify, build, query, saved, history, dataset, qualification, quality,
  inventory, rebuild, info}`; `query` = Q2 range / Q3 instrument / Q4 filter /
  Q5 identity / Q6 calendar / Q7 detail (exactly one mode); `dataset` = Q1 with
  `--family`/`--year` **and yearly summaries** (D30a); `quality` = Q8 (D32);
  `inventory` = Q9 (D30b); `qualification` = Q10 (D33); `saved` = save/show/
  list/update/delete/run (D38); `history` = record/list/show/delete (D39). All
  output is canonical JSON; all failures are fail-closed `{"result": "fail",
  "detail": …}` with a check id; every Q1–Q10 mode has a deterministic empty/
  absent-state representation (e.g. `calendar_present: false`,
  `associations_present: false`, empty partitions/rows, explicit D01/D21/D11
  absences).
* **Negative search (fresh, this task):** zero frontend files in the tree (no
  html/css/vue/jsx/tsx/ts, no package.json); **no dependency manifest of any kind**
  (pure Python-3-stdlib project); no transport/server code in `src/` (the serving
  boundary is in-process + CLI).

## 3. UI capability → serving-contract matrix

Serving operations exist and are tested for everything below (D30a–D39). "UI must
expose" = named in D16-11/12/intent §9; "UI may expose" = permitted, not required;
"not a UI capability" = outside the D16-12 first-release scope or outside D16-11's
ownership (CLI-only maintenance surface).

| UI capability (D16-11/12, intent §9) | Serving contract that backs it (implemented) | Disposition |
|---|---|---|
| **Dashboard — run identity/status** | Q10 (`qualification`): run identity, fingerprints, manifests, R6/D11/D12/D14 evidence (explicit absence when `--repo` omitted) | MUST — backed, no gap |
| **Dashboard — archive count** | Q9 (`inventory`): per-archive INPUT_MANIFEST + D01 facts (2,462 on the real baseline) | MUST — backed |
| **Dashboard — canonical rows** | Q1 (`dataset`) yearly summaries + Q10 package identity (row counts as published) | MUST — backed |
| **Dashboard — identity-record count** | Q5 (`query --identity`/`--instrument-symbol/series`): identity documents + dated-association intervals from `w2/associations.jsonl` | MUST — backed |
| **Dashboard — trading-calendar count** | Q6 (`query --calendar`): full calendar as published + `calendar_totals` cross-check | MUST — backed |
| **Dashboard — error count** | Q8 (`quality`): flag census, quarantine count (0), unresolved-state records, reconciliation aggregates, explicit D21 absence | MUST — backed |
| **Dashboard — rows by year** | Q1 (`dataset`) yearly summaries (family × year partitions) | MUST — backed (D30a) |
| **Dashboard — archives by exchange segment** | Q9 (`inventory`): per-archive `series_counts` + as-published segment fields | MUST — backed (display-level aggregation of served values) |
| **Dashboard — data coverage** | Q9 (per-archive manifest dates) + Q10 (run/manifest identity) | MUST — backed |
| **Dashboard — archive inventory + details** | Q9 (`inventory`) | MUST — backed |
| **Dashboard — reconciliation summary** | Q8 (`quality`) reconciliation aggregates + Q7 reconciliation facts per row | MUST — backed |
| **Explorer — dataset selection** | Q1 (`dataset --family --year`) | MUST — backed |
| **Explorer — date-range query** | Q2 (`query --from --to`) | MUST — backed |
| **Explorer — instrument selection** | Q3 (`query SYMBOL SERIES [--year]`) | MUST — backed |
| **Explorer — segment / series-market-type / trading-status / optional filters** | Q4 (`query --field NAME=VALUE`, exact as-published values; unknown field fails closed) | MUST — backed |
| **Explorer — identity/association + related records** | Q5 (`query --identity` / `--instrument-symbol --instrument-series`) | MUST — backed |
| **Explorer — calendar view (overlay concepts)** | Q6 (`query --calendar [--from --to]`) — file presence as the session signal; the four label states as published; divergence days as stored | MUST — backed |
| **Explorer — canonical-record details + provenance + source evidence** | Q7 (`query --file --line`): row + archive facts + member-scoped reconciliation records, D05 §8 provenance; `raw_line` never served | MUST — backed |
| **Explorer — data-quality status / quality summaries** | Q8 (`quality`) | MUST — backed |
| **Explorer — yearly summaries** | Q1 (`dataset`) | MUST — backed |
| **Explorer — as-published price/field display (charts over as-published values)** | Q2/Q3/Q4 row values as published (no re-derivation; D16-12 "as-published") | MUST — backed (charts are display-level over served values) |
| **Explorer — saved queries (create/read/update/delete/list/run)** | D38 `saved` operations (class-(4) user state; distinct root; full-replacement update; run = exact CLI envelope parity) | MUST — backed (D38) |
| **Explorer — query history (explicit recording; list/show/delete)** | D39 `history` operations (C2(a): recorded ONLY via the explicit `history record` operation, which executes the given mode+params and records the actual outcome) | MUST — backed (D39) |
| **Delegated op (b) — serving-state rebuild trigger** | `rebuild` (op (b): delete-and-rebuild the derived state; fail-closed `rebuild-refuse`; saved/history roots untouched — D38/D39 isolation proven) | MAY — permitted (D16-11; D22 §7 "within first-release scope"); not required in v1 (CLI already provides it) |
| **Delegated op (a) — archive discovery/processing trigger** | — | **NOT in first release** (D16-12 explicit exclusion; D23 §19 withholds ingestion) |
| **verify / build / info (package verification, index build, state summary)** | `verify`, `build`, `info` CLI subcommands | **Not a UI capability** — CLI/maintenance surface; no D16-12 tile or intent §9 reference point; the UI's "state" needs are covered by Q10 (run identity/status) |
| **source row (row offsets)** | — | **Out of scope** — "row offsets never adopted" (D15 §14); not contractually defined |
| **raw record access (raw bytes)** | — | **Out of scope** — D16-12 excludes raw-content serving; D23 §19 withholds it (future explicit decision + cross-environment mechanism); raw bytes stay in Windows custody (D15 §14) |
| **archive byte access** | Q9 serves inventory + hash facts only | Metadata only — bytes out of reach by environment boundary (D15 §14) |
| **DEC-1 / eligibility / master-data queries** | — | **Deferred** (D16-10; D16-12 exclusion) |

**State/edge behavior the UI must render (all already served deterministically by the
existing contracts — no new semantics required):**

* **Loading** — queries stream class-(1) files in-process (Q2/Q3/Q4); the CLI prints
  once, on completion; a UI loading indicator is presentation-level (no progress
  contract exists or is required by any record).
* **Empty result** — empty rows/records with the mode's envelope (`result_count: 0`);
  unknown selectors are empty, never errors (Q3/Q5 convention).
* **Unavailable data (legitimate absence)** — the established explicit-absence
  representations: `calendar_present: false` (Q6), `associations_present: false`
  (Q5), empty Q1 partitions, Q9 explicit D01/registry absence, Q10 explicit
  R6/D11/D12/D14 absence without `--repo`, Q8 explicit D21 absence. The UI displays
  these as explicit absences — never filled in, never invented (the standing
  "never invent" discipline).
* **Invalid input** — fail-closed `{"result": "fail", "detail": …}` with the check id
  (query-input / saved-query-invalid / history contract violations, etc.); no
  partial output. The UI must surface the check + detail verbatim.
* **Stale state** — `index-stale` / `index-load` refusals: the index's package
  identity no longer matches the verified baseline; the served remedy is rebuild (the
  delegated op (b) surface).
* **Corrupt derived/user state** — `rebuild-refuse`, `saved-query-corrupt/
  format/schema/…`, `history-corrupt/format/schema/…` — fail closed; the UI must not
  attempt repair (repair = explicit user operation only).

**Data-class separation the UI must preserve (D16-07, D37-DEC, D38/D39):** package
data (1) is immutable and served read-only; derived serving state (4-derived) is
rebuildable and never a source of truth; the saved-query store and the history store
are serving-owned **user** state in their own distinct roots, outside the rebuild
scope, with explicit-only mutation. The UI never owns any of these classes; it reads
only through serving.

## 4. Settled presentation requirements vs unresolved decisions

**Settled by governing records (no decision input needed):**

1. **Authority: GRANTED and standing** — D23 §17(b) grants "the first-release
   presentation/UI within D16-11/12"; Task 53 re-verified; this task re-verified.
2. **Scope** — D16-12 (Dashboard tiles + Data Explorer Q1–Q10 + saved queries +
   history; explicit exclusions) + D16-11 (ownership split, two-operation whitelist).
3. **Target presentation** — the demonstrated I4 application (non-drift #12; intent
   §9 "remain close to the demonstrated application"). Concrete screens =
   implementation-level detail bounded by D16-12 (D23: "no screens are specified by
   this decision").
4. **Mockup availability** — the supplied mockups exist **outside the repository**
   (another environment/conversation); the governing in-repo references are intent §9
   (the reference-point summary), D16-12 (scope), D15 §14 (data backing), non-drift
   #12 (target). D22 §8 classifies this as "a known, accepted boundary, not an
   evidence gap." If the implementer needs the mockups themselves, that is an
   environment/access matter for the user — **not** an authority gap and **not** a
   blocker to the contract (the scope is fixed without them).
5. **Data backing** — every in-scope tile/capability is served by an implemented,
   tested Q1–Q10/saved/history operation (§3 matrix); D15's only "EXTENSION REQUIRED"
   note (flat per-year rollup) is served by Q1's yearly summaries (D30a).
6. **UI technology/transport selection** — delegated to implementation within D23
   §13's nine constraints, recorded per §18(3) (Task 53: "not a pending user
   decision").
7. **Edge behavior** — §3 state/edge table (all served by existing fail-closed
   contracts; no new semantics).

**Unresolved (implementer-level selections to be recorded at implementation — NOT
user decisions, NOT blockers):**

1. **Frontend/presentation technology** (e.g., the concrete rendering approach for a
   single-user, stdlib-consistent, personal-use product) — must satisfy D23 §13
   constraints 1–3/9 and be recorded with its rationale.
2. **Hosting/runtime + the UI↔serving boundary mechanism** — D23 §14 delegates
   "hosting/runtime" and "query mechanism". The UI must read only through serving
   (D16-11; D23 §18(9)): no direct durable-data access, no engine-state ownership,
   no new query path (D23 §18(8)). Any mechanism that drives the existing serving
   layer (its functions or its CLI canonical-JSON surface) conforms; a mechanism
   that adds parallel query semantics does not.
3. **Concrete screens/layout** — bounded by D16-12 + intent §9 + the demonstrated
   application (non-drift #12).

## 5. Existing framework/transport findings

* **No UI framework or transport is selected or present**: zero frontend files; no
  dependency manifest (the repository is pure Python 3 stdlib); no server/transport
  code in `src/` (fresh negative search, this task).
* **The existing consumer boundary is the CLI** (D24 technology selection, recorded):
  in-process stdlib serving + a canonical-JSON CLI; every operation is
  machine-consumable (stable subcommands, canonical JSON output, documented exit
  codes 0/2/3).
* **D16 §14: TECHNOLOGY = UNDECIDED** for every physical concern; D23 §13 delegates
  the frontend/hosting selection under the nine constraints — no record names, ranks,
  or implies a technology (this record does not either).
* No general-purpose framework or service is justified by the established contract:
  single-user, personal-use, local, no auth/RBAC/multi-user, no PostgreSQL, no live
  market data (D23 §13 constraints 1–3/9; D16 §13 non-goals).

## 6. Smallest implementation-ready UI slice (assessment — proposal, not decision)

**Candidate scope (smallest useful, all within the standing D23 §17(b) grant):**

1. **Dashboard** — the D16-12 tile list rendered from the existing Q1/Q5/Q6/Q8/Q9/Q10
   operations (read-only; explicit absences displayed as served).
2. **Data Explorer** — the six `query` modes (Q2/Q3/Q4/Q5/Q6/Q7) + Q1 dataset
   selection with the established empty/invalid/stale behavior; saved-query
   management (D38 operations) and explicit history recording (D39 operations) wired
   to the same serving surface.
3. **Delegated op (b)** surfaced as an explicit user-initiated maintenance action (or
   left CLI-only in v1 — permitted either way).

**Explicit exclusions (per §3/§4):** processing trigger, raw content, source-row
access, DEC-1, verify/build/info as product capabilities, any new query semantics,
any re-derivation of class-(1)–(3) facts beyond display-level aggregation of served
outputs.

**Dependencies (all already satisfied):** implemented + tested serving surface
(D30a–D39); distinct roots for derived/saved/history state (D38/D39); fail-closed
canonical-JSON contract; no new authority, no new persistence technology (the UI
adds no durable state of its own — all four state classes remain serving-owned).

**Tests/durability requirements (D23 §18 closure battery, UI-relevant items):**
item 3 — frontend/hosting technology selection + constraint-compliance rationale
recorded; item 8 — no other query path exists; **item 9 — UI boundary proof (the UI
reads only through serving; no direct durable-data access; no engine-state ownership;
only delegated operation (b) is exposed) — currently PENDING the UI (Task 53) and is
the defining closure gate for this slice**; item 10 — test suite passing under the
established discipline (deterministic; the suite states runner/results; any
real-baseline leg stays `D24_M2_ROOT`-gated — skipped ≠ passed); item 11 — complete
artifact inventory with digests; item 12 — remote durability + independent
verification; plus the standing publication battery (additive commits, FF-only
session-branch push, package byte identity, no promotion).

## 7. Authority gaps

**None.** Implementation authority for the first-release presentation/UI is granted
(D23 §17(b)); technology/transport selection is delegated (D23 §13/§14) and is an
implementer record obligation, not a user decision (Task 53); every in-scope
capability is backed by an implemented serving contract; the mockup boundary is an
accepted, documented boundary (D22 §8), not a gap. No decision input is required
before a UI slice can proceed.

## 8. Qualification separation

Real-M2 integration qualification remains PENDING (gated legs never claimed passed);
the Windows track was not executed or touched in this task and its handoff pin is
stale — it **must be re-pinned to D39 `d9d32ab0b91c6ca732ed0dcdd4bdecbd5d1ff50b`**
before any later qualification execution. No main promotion.

## 9. Final status

**READY FOR IMPLEMENTATION** — the smallest UI slice (§6) is implementation-ready
under the standing D23 §17(b) authority: scope, target reference, capability-to-
contract mapping, edge behavior, isolation, and closure requirements are all fixed
by governing records; the only open items are implementer-level, delegated, recorded
at implementation (frontend technology, hosting/UI-serving boundary mechanism,
concrete screens). **STOP** — no implementation in this task.
