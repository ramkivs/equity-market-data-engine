# TASK67 — I4 UI: Page-Exclusivity Correction (F-N1), Full Mockup-Parity Audit (Categories A–Z), and Navigation Scope Determination

**Task:** UI page exclusivity, mockup parity audit, and navigation scope decision
**Session branch:** `arena/9021d1a1-nse-historical-data-engine`
**Baseline:** TASK66 report commit `797966ccb2561ea11bf7521f25efe83f5cb67760` (verified, §1)
**Disposition:** F-N1 corrected under bounded implementation authority + focused regression tests added and passing (fresh Windows capture still required for visual confirmation); complete 26-category (A–Z) mockup-parity difference register completed (no remaining normative violations); six unavailable navigation items analyzed with recommendations (all: remain unavailable at first release); final UI acceptance **PENDING** fresh captures.
**M2 package:** read-only throughout; never modified. **No Windows access from Arena** — all UI claims from captures are cited to the published evidence artifacts, and final visual acceptance requires the fresh Windows capture set (§10, §12).

---

## 1. Starting baseline and identity verification (actual, at task start)

At task start the local session ref had been rolled back a **40th time** (HEAD at pre-fork
`89ce965c…`, all post-fork work untracked). Repaired by the established non-destructive
procedure before any work: value audit (218 files / 0 missing / 0 mismatched vs
`797966c…`), explicit-refspec fetch, guarded `git update-ref`, `git reset --hard` to the
verified value, worktree re-confirmed clean (only the standing untracked
`_transfer_delivery/` staging area).

Remote identities verified at task start (`git ls-remote origin`):

| Ref | SHA-1 | Role |
|---|---|---|
| `arena/9021d1a1-nse-historical-data-engine` | `797966ccb2561ea11bf7521f25efe83f5cb67760` | session HEAD (TASK66 report commit) |
| `evidence/i4-ui-visual-acceptance-2026-10-10` | `d9815dfcfe8f6f6428cf11feb2bb29ef728a4f42` | Windows acceptance evidence (parent `1b43e0d8…`) |
| `main` | `69977017ffca944921f231d7904347bc582b6392` | unchanged, never promoted |
| `docs/i4-ui-mockup-references` | `726b1c36…` | mockup reference branch |
| `docs/i4-historical-data-engine-ui-spec` | `20bf8238…` | spec branch |

TASK66 artifacts independently re-verified at baseline (not trusted from summaries):
report blob `57e49a5e8c31793dc7b9b77db539651cb8620173` (content SHA-256
`4c88a67b9200c69f860a878ffe82c68e82277cbc8c6cb6c665013b5959b05459`) present in
`797966c…`; evidence-branch screenshot blobs `0b29259c2b6b4135b2c1f9023c72f25579964d11`
(dashboard, 235,314 B) and `86437044598ea0795e64ebc6699a2615c4bd22b4` (explorer, 217,079 B)
re-fetched and hash-confirmed.

## 2. Authoritative mockups (repository-resident, inspected in full this task)

| Path | SHA-256 | Size | Content |
|---|---|---|---|
| `evidence/10y historical engine.png` | `fa11f0e867d0f8aa1df41b3ab88c51d27ce2ccd50e790e5181ecf45b2aa1af85` | 1,773,767 B | Dashboard mockup (1536×1024) |
| `evidence/10y historical engine-data explorer.png` | `53f20b6484f02ac28f4fdf5f80125b38e138e256ebf8ba5d26cfb3ee9b46bd19` | 1,842,012 B | Data Explorer mockup (1536×1024) |

Reference list: `evidence/I4_UI_MOCKUP_REFERENCES.txt` (670 B, at HEAD). Both images were
opened and inspected in full during this task (every region documented in §5). The
user-attached reference image from the task header was **not** used as a substitute for
this repository inspection. Per the UI spec §2.3/§15, the mockups are **non-authoritative
raster references** with illustrative data; the binding authorities are the governance
contracts (D23, D15, D16, D37/D38/D39, D05, D30B, D31, D11) and the approved UI spec to the
extent consistent with them (spec §15: "End of non-authoritative UI specification";
spec §6.5: "D23 §19's raw-content-serving restriction prevails over the screenshot").

## 3. F-N1 — root cause analysis and correction (implementation authority: granted, bounded)

**Defect (TASK66 F-N1):** Dashboard and Data Explorer page sections could render
simultaneously (stacked), and the nav active state could diverge from the displayed page.

**Root cause (verified in source before changing anything):**
- `src/ui/static/index.html:58` — `<section id="page-dashboard" class="page">` (visible by default);
- `src/ui/static/index.html:112` — `<section id="page-explorer" class="page" hidden>`;
- `src/ui/static/app.js:1454` — `switchPage()` was **already correct**: it sets
  `$("page-dashboard").hidden = page !== "dashboard"` and the same for explorer, toggles
  `aria-current="page"` on `.nav-item[data-page]` buttons, and loads the target page's data.
  No JS defect exists.
- `src/ui/static/app.css:128` — `.page { display: flex; }` (author origin, specificity
  0,1,0). The UA stylesheet's `[hidden] { display: none }` rule (specificity 0,1,0, UA
  origin) loses the cascade conflict to the author `.page` rule, so the `hidden`
  attribute was **inert**: the hidden page kept `display: flex` and rendered stacked
  under the visible one. There was no author `[hidden]` rule for `.page` anywhere in the
  stylesheet (the only other display rule touching a `.hidden` utility is
  `.field.hidden { display: none }` at app.css:315, which applies to builder fields, not
  page sections).

**Correction applied (smallest correct fix; the candidate rule):**
`src/ui/static/app.css` — immediately after the `.page` rule:

```css
.page[hidden] { display: none; }
```

Specificity 0,2,0 beats `.page` (0,1,0), so the `hidden` attribute set by the existing
correct `switchPage()` again hides the inactive page. **No JavaScript change** (the JS
mechanism was verified correct — changing it would have been wrong), no markup change,
no new page architecture/tabs/routing/redesign.

## 4. Focused regression tests (new) and test results (actual)

**New artifacts:**
1. `tests/ui_page_exclusivity_harness.js` — Node VM harness: loads the real
   `app.js` with a stub DOM, drives `switchPage()` dashboard→explorer→dashboard against
   all-OK API stubs (status, Q1, Q6, Q8, Q9, Q10), asserts after every state: exactly one
   of the two page sections has effective `display !== none` (never both, never none),
   and nav `aria-current` tracks the displayed page. Exit 0/1/3.
2. `tests/test_ui_page_exclusivity.py` — unittest wrapper: (a) CSS structural tests —
   `.page` flex rule present (documents the conflicting rule), `.page[hidden]` rule
   present with `display:none`, no later rule re-displays `.page[hidden]`, no
   higher-or-equal-specificity author rule re-displays both-class elements; (b) markup
   tests — both `.page` sections present, explorer starts `hidden`, dashboard does not,
   nav items carry `data-page`; (c) JS contract tests — `switchPage()` keeps driving
   visibility via the `hidden` attribute and nav `aria-current` (guards against drift to
   classes/inline styles the CSS rule would not cover); (d) subprocess behavior test —
   runs the Node harness (skipped if Node is absent).

**Negative control (test catches the defect):** against the pre-fix CSS at HEAD
(`git show HEAD:src/ui/static/app.css`) the `.page[hidden]` rule is absent while
`.page { display: flex }` is present — the regression assertion fails on pre-fix state.
Confirmed by direct inspection (see §11, output "pre-fix .page[hidden] rule present:
False").

**Results (actual, this task):**

- `node --check tests/ui_page_exclusivity_harness.js` → clean.
- `node tests/ui_page_exclusivity_harness.js src/ui/static/app.js` → **13/13 PASS**
  (S1 dashboard: visible/hidden/aria-current ×5; S2 explorer: ×5; S3 round-trip: ×3),
  prints `HARNESS OK`, exit 0.
- `PYTHONPATH=src python3 -m unittest tests.test_ui_page_exclusivity -v` → **Ran 8 tests … OK**.
- Full suite (justified: a shipped CSS file changed):
  `PYTHONPATH=src python3 -m unittest discover -s tests -t .` →
  **`Ran 900 tests in 81.775s — OK (skipped=14)`** (was 892 before this task; the 14
  skips are the standing D24_M2_ROOT disk-gated legs, unchanged).

**Caveat (standing rule):** none of this is a visual-acceptance claim. Page-exclusivity
*behavior* is verified by tests; that the rendered Windows page looks correct still
requires the fresh capture (§10/§12).

## 5. Complete mockup-vs-delivered difference register (categories A–Z)

**Method:** both mockups inspected region-by-region (this task); the delivered UI is
characterized from (a) the published Windows captures on the evidence branch
(`0b29259c…` dashboard, `86437044…` explorer — 1536×1024 each) as recorded in the TASK64
and TASK66 reports, and (b) direct source inspection of `src/ui/static/index.html`,
`app.js`, `app.css` and `src/ui/api.py` at the verified baseline. Every mockup value is
illustrative (spec §2.3); every delivered value is as-served or explicitly
"unavailable" (never zero, success, or a fake empty — TASK62 §5 rule).

**Classification taxonomy (per task):** 1 DEFECT · 2 AUTHORITY-CONTRACT LIMITATION ·
3 DATA-DRIVEN · 4 VISUAL PARITY GAP · 5 FUTURE PRODUCT ENHANCEMENT · 6 UNRESOLVED.
"Normative violation?" cites the binding instrument where a requirement is violated.

### A. Title bar and product identity

| ID | Mockup (expected) | Delivered (actual) | Evidence | Class | Sev | Normative violation? | Disposition / authorized? |
|---|---|---|---|---|---|---|---|
| MP-A1 | Settings + Help icons (title bar right) | none; a live service-state indicator ("connected · run i4-20261008-M2") instead | mockup title bar; index.html `#titlebar` (tb-mark/titles/tb-service only); spec §4.1 "Settings and Help affordances **if permitted**" | 2 | low | No — spec makes them conditional; no settings/help surface exists in the serving contract (api.py exposes only Q1–Q10, status, saved/history) | Leave as-is. A Settings/Help surface would need its own authorization (Q13, §6 roadmap P2). Not authorized. |
| MP-A2 | Window controls (min/max/close) in app title bar | browser chrome provides them; app adds a one-line subtitle "…read-only serving view" under the title | mockup; index.html `#titlebar`; spec §4.1 (host window controls "only if consistent with the actual host environment") | 4 | low | No — web host is the browser; the OS chrome owns window controls. Subtitle is an intentional read-only disclosure (TASK62) | Leave as-is. No action. |
| MP-A3 | User chip "R Ramki" with dropdown (explorer mockup) | no user chip anywhere | explorer mockup title bar; no user/identity markup in index.html | 2 | low | No — spec §4.1: "Do not create fictional identity, authentication, or user-management behavior"; no identity operation exists (single-user) | Leave as-is. Fictional identity would violate the spec. Not authorized. |
| MP-A4 | Title "I4 Historical Data Engine (10-Year NSE Corpus)" | identical (TASK65 F-C7, VERIFIED in TASK66) | both mockups; index.html `tb-title` | parity | — | No (resolved) | None. |

### B. Navigation rail and page exclusivity

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition / authorized? |
|---|---|---|---|---|---|---|---|
| MP-B1 | 8 nav items rendered enabled: Dashboard, Archives, Data Explorer, Reconciliation, Determinism & Replay, Reports, Engine Status, Configuration | 2 enabled (Dashboard, Data Explorer) + 6 unavailable items with explanatory badges (titles per §6) | both mockups; index.html:35–50 `.nav-unavailable` items | 2 | low | No — spec §4.2: a nav item's presence "does not prove the destination is implemented or authorized… omit it, or render a clear unavailable/placeholder state without exposing unauthorized operations". First-release scope = D16-12; TASK62 omission 3 | Leave as-is. Enabling any of the six is explicitly out of authority (§6). |
| MP-B2 | Nav order: Archives 2nd (between Dashboard and Data Explorer) | Data Explorer 2nd; "Archives" appears in the unavailable group | mockup rail vs index.html nav order | 4 | low | No (order not pinned) | Optional cosmetic reorder; not worth a change. |
| MP-B3 | Pages are mutually exclusive; nav active state matches the displayed page | **Was broken (F-N1): stacked pages + stale nav state** → **corrected this task** (§3) | TASK66 report F-N1; app.css/app.js/index.html per §3; new tests per §4 | 1→fixed | high→n/a | Was a violation of spec §4.2 ("nav tracks the active page") and §5/§6 single-page behavior; **corrected** | Fixed + regression-tested; visual confirmation requires the fresh capture (§10). Authorized (this task). |
| MP-B4 | "Saved Queries" list + New Query rendered in the left rail (explorer mockup) | Saved Queries is the Explorer **sidebar** (spec §6.9), not a rail element; nothing seeded (guided empty state) | explorer mockup; index.html `expl-saved` sidebar; spec §6.9/§16.5; TASK64 F-C8 fix | 2 | low | No — spec text (sidebar) governs over the mockup's placement | Leave as-is. |

### C. Dashboard page header and run summary

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition / authorized? |
|---|---|---|---|---|---|---|---|
| MP-C1 | Page title "10-Year NSE Historical Data" | identical | mockup; index.html; TASK66 F-C4 VERIFIED | parity | — | No (resolved) | None. |
| MP-C2 | Subtitle "Process • Explore • Verify • Compare • Report" | identical | mockup; index.html; TASK66 F-C5 VERIFIED | parity | — | No (resolved) | None. |
| MP-C3 | Green "COMPLETED" badge on Run ID | no badge; run ID `i4-20261008-M2` shown as served | mockup run block; app.js run summary renders served identity only; Q10 envelope (api.py) carries no status field | 2 | low | No — spec §5.2: status "only where a real status can be established"; none is served | Leave as-is. Displaying "COMPLETED" would be fabrication. |
| MP-C4 | Run Date "08 Oct 2026 14:27:18" | "unavailable" chip (no timestamp in the served run identity) | mockup; TASK64 D14 (AUTHORITY-DRIVEN); app.js | 2 | low | No — spec §8.6: unavailable shown explicitly, never faked | Leave as-is. |
| MP-C5 | "Engine: 14 \| Corpus: NSE (10 Years) \| Archives: 2,462" | "Engine nse-engine w2-1.0.0 / Corpus 2,462 archives / Package files 4,948 (19.67 GB)" — as-published engine identity string + as-served Q10 package-manifest facts | mockup; app.js run summary; TASK66 capture values | 3 (+4 label wording) | low | No — as-published identity is the contract-faithful display; mockup value is illustrative | Leave as-is. |

### D. KPI cards

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition / authorized? |
|---|---|---|---|---|---|---|---|
| MP-D1 | 2,462 / 5,689,949 / 2,462 / 2,462 / 0 | 2,462 / 5,689,949 / unavailable / 2,609 / 1,397 — as-served (Q1, Q10, Q8) | both mockups vs TASK66 capture; spec §2.3 (reference data is illustrative) | 3 | — | No | None — data-driven. |
| MP-D2 | "Identity Records 2,462" | "Identity Records — unavailable" (no count operation exists) | mockup; TASK62 omission 13; app.js Identity KPI | 2 | low | No — no count in the serving contract; a number would be fabricated | Leave as-is. |
| MP-D3 | "Errors 0" + green check | "Errors 1,397" + amber glyph (as-served Q8 `flagged_records_total`) | mockup; TASK66 F-C3 VERIFIED | 3 | — | No | None — data-driven. |
| MP-D4 | Blue per-card icons (db/doc/people/calendar/clock) | status glyph dot only (green/amber/muted); no pictorial icons | mockup KPI row; app.js `cards.push({…, glyph})`; spec §5.2 card anatomy lists "a simple icon" | 4 | low | No (no data/behavior impact); spec §5.2 card anatomy is presentation guidance, and the TASK62 implementation record deliberately renders status glyphs | Optional polish (roadmap P1): add the five simple card icons. Not authorized this task. |
| MP-D5 | Green success check on every card | glyphs only where a real status can be established | mockup; spec §5.2 "Do not display a green success glyph merely because a count is nonzero"; TASK66 capture | 2 (delivered is the compliant one) | low | No — the mockup's all-green is illustrative; the delivered behavior follows the spec rule | Leave as-is. |

### E. Rows-by-Year chart

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-E1 | 10 bars, 2016–2025 | 12 bars, 2016→2026 (11 years, 12 partitions, axis max 757.7K) | mockup; TASK66 capture (chart visible); Q1 `rows_by_year` as served | 3 | — | No | None — data-driven. |
| MP-E2 | Axis 0–1.0M | axis auto-scaled to served data | mockup; TASK66 capture | 3/4 | low | No | None — data-driven auto-scale. |

### F. Exchange-segment donut and legend

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-F1 | 4 clean segments with %: NSE Equity (CM) 1,842 (74.8%), NSE FO 412 (16.7%), NSE Currency 156 (6.3%), NSE Debt 52 (2.1%) | donut over the served `series_counts` (60+ as-published codes, long tail); legend renders every code and extends below the 1024 px capture (clip is capture-frame, not layout breakage) | mockup; TASK64 F-C2 (donut VERIFIED) + TASK66 F-N5 (legend tail below fold); app.js donut/legend over served codes | 3 (+4 presentation) | medium | No — no aggregation/segment-mapping operation exists; fabricating 4 friendly buckets would violate §2.3/§8.6 | Data-driven; optional P1 polish: top-N legend + "and N more codes" (or scrollable legend container) to restore visual calm. Not authorized this task. |
| MP-F2 | Center label "2,462 Archives" | "2,462 archives" (case) | mockup; TASK66 capture | 4 | low | No | None (trivial). |

### G. Data Coverage panel

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-G1 | Start 01 Jan 2016 / End 31 Dec 2025 | 2016-09-20 / 2026-09-18 (as-served coverage) | mockup; TASK66 capture | 3 | — | No | None — data-driven. |
| MP-G2 | Instruments 6,842; Exchange Segments 4 (friendly names) | Instruments 16,107 (zoom-verified against the coverage value); segments shown as the as-published series-code list (17 top-level segments in the served inventory) | mockup; TASK66 capture + zoom crops; app.js coverage panel | 3 (+4 naming) | low | No — no segment-name mapping operation exists; codes are the as-published identifiers | Data-driven; friendly-name aliasing is a future presentation option only (Q1). |
| MP-G3 | Trading Days 2,462 | 2,609 (as-served) | mockup; TASK66 capture | 3 | — | No | None — data-driven. |

### H. Archive Browser (table, search, filters, sort, export)

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-H1 | Columns: Archive Name / Date / Segment / Symbol / Status (✓ Processed) / Rows / File Size | Columns: # / Archive / Date / Segment / Symbols (count) / Status (chip "verified" or "d01 absent") / Rows / File Size — sortable | mockup; app.js:662–663 header row + :668–676 cells | 3 (+2 semantics) | low | No — the mockup's "Processed" is a processing-lifecycle state with no served counterpart; the delivered Status is a genuinely served fact (D01 inventory joined/verified or absent). A fabricated "Processed" would violate §8.6 | Leave as-is (truthful served state). |
| MP-H2 | Search box + All Segments + All Years dropdowns | search + segment select + year select + sortable headers — display-level over served rows | mockup; app.js `renderArchives` (filter/sort over `q9.archives`) | parity | — | No (functionally equivalent; sort added) | None. |
| MP-H3 | "Export List" button (blue) | no export affordance | mockup; TASK62 omission 10 ("Export actions — omitted"); no export operation in api.py | 2 | medium | No — export is not authorized and no export serving operation exists | Leave as-is; future feature (P2) requiring its own authorization. Not authorized. |

### I. Archive Detail panel

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-I1 | Fields: Archive Name / Date / Segment / Symbol / Status / Rows / File Size / SHA256 (truncated "a3f9…7c1d") | groups: "Archive (INPUT_MANIFEST, as published)" + "D01 inventory facts (joined, verified)" + "Archive hashes (served facts)" — full as-served hashes, no truncation; no per-archive "Status" (not served) | mockup; app.js:729–750 | 3 (+2) | low | No — superset of genuinely served facts; full hashes are the served values (spec: do not fabricate or truncate-as-if-sensitive what is served) | Leave as-is. |
| MP-I2 | Buttons: View Canonical Data / View Identity/Association / View Calendar Overlay / View Reconciliation — all enabled | "Canonical Data" (enabled → opens Explorer with the archive's segment pre-applied as a Q4 exact-value filter) / "Identity / Association" (enabled → Explorer, related records per selected record) / "Calendar Overlay" (**disabled**: "no authorized per-archive calendar overlay operation exists") / "Reconciliation" (enabled → Explorer Q8 view) | mockup; app.js:751–756 (exact titles in source) | 2 | medium | No — spec §6.5: "prohibited actions must not be exposed as active controls"; the three real navigations exist, the fourth has no authorized operation | Leave as-is. Calendar Overlay stays disabled unless a real operation is authorized. |

### J. Data Explorer page header and dataset context

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-J1 | Dataset dropdown "I4 10-Year NSE Historical Dataset (v1.0)" + Total Archives / Total Rows / Date Range / Last Updated | single fixed package label; no selector; no "last updated" (no contract timestamp exists) | mockup top-right panel; TASK62 omission 12 ("Dataset selector / last-updated — single dataset / no contract timestamp (explicit unavailable)"); index.html | 2 | medium | No — only one package is served; a selector would imply a non-existent operation | Leave as-is. A multi-dataset selector is a future authority item, not first release. |
| MP-J2 | Title "Data Explorer" + subtitle "Query and explore the I4 10-year NSE historical dataset" | "Data Explorer" + served-contract subtitle (Q2–Q10 reference) | mockup; TASK66 explorer capture; index.html | 4 | low | No (wording) | None (trivial). |

### K. Query builder

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-K1 | Unified 6-control grid: Date Range / Instrument / Segment / Series / Trading Status / Exchange Segment + optional Filters | mode-based builder: Query mode selector (Q2 date-range / Q3 instrument-snapshot / Q4 exact-value) + per-mode fields + optional exact-value filter block (Q4 mode) + Run/Reset/Save | mockup builder; app.js:777–782 (mode-driven field visibility); spec §6.2 "Query Builder uses the established query contract (Q1–Q10)"; TASK64 D9 (AUTHORITY-DRIVEN) stands | 2 | medium | No — the builder must bind the Q1–Q10 contract, which is mode-based; the grid is a reference layout | Leave as-is. |
| MP-K2 | Instrument = Symbol **dropdown** + value + search icon | Symbol exact-value text input ("as published") | mockup; app.js builder; no authorized instrument-list operation exists (Q5 is association, not an instrument catalog) | 2 | low | No — a dropdown would require an enumeration operation that does not exist; exact as-published string is the contract | Leave as-is. |
| MP-K3 | Segment / Series / Exchange Segment **dropdowns** | Series exact-value field; segment/source/instrument_type via Q4 exact-value filters | mockup; app.js q4-block (fields: series, segment, source, instrument_type) | 2 | low | No — no authorized enumeration operation for dropdown contents | Leave as-is. |
| MP-K4 | "Trading Status" filter control | omitted entirely | mockup; TASK62 omission 5; app.js:1114 inspector chip "not a canonical field — unavailable" | 2 | low | No — trading status is not a canonical field in the serving contract | Leave as-is. |

### L. Optional filters (field/operator/value)

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-L1 | "Filters (optional)" table: Field/Operator/Value with `=` and `between` operators, per-row delete, "+ Add Filter" | Q4 exact-value filters: AND-combined, **equality only**, 4 contract fields (series, segment, source, instrument_type), add/remove rows; block visible in Q4 mode | mockup; app.js q4-block + "no operators other than equality" note | 2 | low | No — the Q4 contract admits equality only; `between` is outside the contract | Leave as-is (contract-faithful). |

### M. Quick filters

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-M1 | Presets: EQ (CM), EQ (FO), Currency, Debt, Latest 1Y, Latest 3Y, Latest 5Y, Latest 10Y, Reliable Only | identical set (app.js:20 `QUICK_FILTERS`), labeled "deterministic presets — each maps to an explicit query; none fabricates data" | mockup; app.js:20, 817–819 | parity | — | No | None (label order differs trivially). |
| MP-M2 | "Reliable Only" rendered enabled | "Reliable Only" **disabled** with explanatory reason (app.js:207 "Reliable Only and unknowns: unavailable") | mockup; app.js; TASK62 omission 6 | 2 | medium | No — the four-bucket quality semantics (Reliable/Uncertain/Missing/Excluded) are not in the serving contract; enabling the preset would be fabrication | Leave as-is. A reliable-only view becomes possible only if the contract serves quality buckets (P2). |

### N. Results header (count, query summary, Export, Columns)

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-N1 | "1,243 records (TCS, 01-01-2020 to 31-12-2020)" | "<n> records (served)" + active-query banner (e.g., 1,679 for the TASK66 Q3 HDFC/EQ snapshot) | mockup; app.js `renderResults` (count from served envelope, never fabricated — spec §6.4) | 3 | — | No | None — data-driven. |
| MP-N2 | Export dropdown | none | mockup; TASK62 omission 10; no export operation in api.py | 2 | medium | No — "Export menu, if authorized" (spec §6.4) — it is not | Leave as-is (P2, own authorization). |
| MP-N3 | Columns dropdown | none (all 13 canonical columns always rendered) | mockup; spec §6.4 "Columns menu, if column selection is supported" — not supported at first release | 2 | low | No | Leave as-is (P2, presentation-only option). |
| MP-N4 | Rows per page default 20 | default 25 (selector 25/50/100) | mockup; app.js pagination | 4 | low | No (default not pinned by spec) | Optional trivial change if pixel parity is later demanded. |

### O. Results table (columns, status, selection, overflow)

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-O1 | 13 columns: #, Trade Date, Symbol, ISIN, Series, Segment, Open, High, Low, Close, Volume, Turnover (₹), Status | identical 13 columns in spec §16.3 order (app.js:973–977 `RESULT_COLUMNS`) | mockup; spec §16.3; source verified | parity | — | No | None — exact parity. |
| MP-O2 | Status cell "✓ Reliable" per row | flag-status chip from the as-published row flags (no "Reliable" bucket exists in the served data) | mockup; TASK62 omission 11; app.js row rendering | 2 | medium | No — a green "Reliable" would invent quality semantics the presentation layer is forbidden to create (spec §6.5: "Do not infer reliability from missing fields or apply new quality semantics in the presentation layer") | Leave as-is (truthful flag states). |
| MP-O3 | Selected row highlighted (blue fill) | selected row blue + drives the inspector | mockup; TASK66 capture (selection visible); spec §6.4 "Highlight the selected row with blue fill" | parity | — | No | None. |
| MP-O4 | Full width fits 1536 px | 13-column table wider than the panel → horizontal scroll (spec §6.4 requires usable horizontal scrolling that does not obscure row selection — satisfied); Turnover/Status off-frame in the 1024 px capture | mockup; TASK66 F-N8 (capture, not breakage) | 4 | low | No | None — compliant behavior; the fixed mockup viewport simply shows fewer columns. |

### P. Pagination

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-P1 | "1-20 of 1,243" + prev/next | "1–25 of 1,679 (served)" + prev/next; display-level over served rows, never implies more was fetched | mockup; app.js `renderPagination`; spec §6.4 pagination rule | parity (+3) | — | No | None. |

### Q. Record Details / Inspector

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-Q1 | Tabbed panel: Canonical Record / Source Evidence / Related Records + Prev/Next | single scrolling inspector with groups (Instrument / Trading Details / Data Quality / Provenance (D05 §8) / Related Records (Q5) / Reconciliation) + Prev/Next (ins-prev/ins-next) | mockup; app.js:1107–1152; spec §6.5 "Reference tabs" + "groups and labels are visual guidance; actual fields and semantics must come from the established contracts" + §16.4 grouping (delivered groups match §16.4 exactly) | 4 | low | No — the delivered grouping follows the spec's §16.4 contract-driven grouping; tabs were a reference form | Optional P1 cosmetic (tabs if demanded). Leave as-is. |
| MP-Q2 | "Source Evidence" tab (implying raw-source access) | no raw-evidence section; the authorized as-served provenance block is shown instead | mockup; spec §6.5 "Do not expose Source Evidence … until their exact permitted fields and operations are verified" + "D23 §19's raw-content-serving restriction prevails over the screenshot"; D23 §17/§19 | 2 | medium | No — withholding is the spec- and contract-mandated behavior | Leave as-is. |
| MP-Q3 | Prev/Next record navigation | present and functional (within the authorized result set) | mockup; index.html `ins-prev`/`ins-next`; app.js inspector nav | parity | — | No | None. |
| MP-Q4 | Actions: View Raw Record / View Archive / View Reconciliation — all enabled | View Raw Record **disabled** ("Withheld: raw-content serving is explicitly withheld in D23 §19 — the raw record is never served"); View Archive **disabled** ("Withheld: archive bytes are in Windows custody (D15 §14) — no archive-byte serving exists"); View Reconciliation **enabled** (shows served reconciliation records for the archive) | mockup; app.js:1148–1152 (exact source titles); spec §6.5 "prohibited actions must not be exposed as active controls" | 2 | medium | No — delivered behavior is the spec-compliant one | Leave as-is. |

### R. Canonical record fields

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-R1 | Instrument group includes Company ID / Company Name ("TCS Ltd") | not shown; explicit footnote: "Fields absent from the canonical row contract (e.g., company id/name) are not shown — they are not published, and no placeholder is substituted" | mockup; app.js:1129 footnote; spec §16.4 "If a field is not permitted, do not display a fake or placeholder value that resembles real provenance" | 2 | low | No — the canonical contract publishes no company id/name; the mockup's values are illustrative | Leave as-is (no fabrication). |
| MP-R2 | Trading Details "Trading Status: Normal" | chip "not a canonical field — unavailable" | mockup; app.js:1114 | 2 | low | No | Leave as-is. |
| MP-R3 | Data Quality group: Identity/Record/Association Status each "✓ Reliable" | group present with the as-published flag states (no "Reliable" bucket) | mockup; app.js:1116–1120; TASK62 omission 11 | 2 | medium | No — §6.5 forbids invented quality semantics | Leave as-is. |

### S. Provenance

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-S1 | 4 fields: Source Archive / Source Row / Archive Path / Raw Hash (truncated "3af9…7c1d") | full as-served D05 §8 block: Source Archive, Source Row, Archive Path, Archive SHA-256, SHA-256 basis, Member SHA-256 (raw), Format family, Run ID | mockup; app.js:1121–1129; D31 Q7 slice serves this block | 3 (superset) (+4 labels) | low | No — every field is genuinely served; labels follow the contract (spec: "actual fields and semantics must come from the established contracts") | Leave as-is. |

### T. Related records

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-T1 | "Related Records" tab (content not detailed in mockup) | "Related Records (Q5, as published)" group: dated association intervals with contributing rows; explicit empty state when none served ("the package carries no associations file — legitimate state") | mockup; app.js:1130–1138; Q5 slice (api.py) | parity (+2 empty-state) | — | No | None. |

### U. Saved Queries (sidebar + tab)

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-U1 | 7 seeded named shortcuts (TCS 2020 (EQ), TCS 10-Year History, All EQ 2020, Identity Uncertain, Missing Trading Dates, Reconciliation Exceptions, Corporate Action Candidates) | "+ New Query" + guided empty state; **nothing seeded** | mockup; spec §16.5 "These are illustrative names from the mockup, not guaranteed saved records… Do not seed these examples"; TASK62 "Mockup saved-query shortcut names are never seeded"; TASK64 F-C8 (sidebar + empty state VERIFIED) | 2 (spec-pinned) | low | No — seeding the examples would violate spec §16.5 | Leave as-is. |
| MP-U2 | + New Query | present, plus a full Saved Queries tab (Run/Update/Delete per entry — D38) | mockup; app.js:1331–1346; D38 | parity (+superset) | — | No | None (authorized D38 capability). |

### V. Query History

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-V1 | "Query History" tab (content not detailed) | Query History tab: explicit "Record current query execution" action only (D39; ordinary runs never write history), guided empty state | mockup; app.js:1403; D39 | parity (+superset) | — | No | None (authorized D39 capability). |

### W. Price chart

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-W1 | "Price Chart (TCS)" with Close Price dropdown, line + volume bars | "Price Chart" + field selector (Close Price / Open / High / Low / Last / Prev Close / Turnover) + Volume checkbox, rendered from the served result set | mockup; spec §6.6; app.js chart block | parity (+superset) | low | No (title omits the symbol — trivial) | Optional P1: include the symbol in the chart title. |
| MP-W2 | Monthly x-axis labels Jan–Dec 2020 | time axis auto-scaled to the served period | mockup; TASK66 capture | 3/4 | low | No | None — data-driven. |

### X. Yearly summary

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-X1 | "Yearly Summary (2020)": Records, Open (First), Close (Last), High (Year), Low (Year), Volume (Total), Turnover (Total ₹) | "Yearly Summary" + "Period summary (first – last) · over the served result set, in served order" + Records + first/last/high/low/volume/turnover statistics | mockup; spec §6.7 (derived, documented, deterministic period statistics are authorized); app.js yearly summary | parity (+3 values) | low | No (title omits the year — trivial; derivation is contract-faithful and documented in the UI) | Optional P1: label the period in the title. |

### Y. Data-quality summary

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-Y1 | Four-bucket donut + legend: Reliable 243 (100.0%) / Uncertain 0 / Missing 0 / Excluded 0 | explicit "not a served contract" message instead of the four buckets; the served Q8 census is shown (the real served quality view) | mockup; TASK62 omission 11; app.js Q8 census rendering; spec §6.8 | 2 | medium | No — the buckets are not served; rendering 100%/0/0/0 would be fabrication (spec §2.3/§8.6) | Leave as-is. A real four-bucket view requires the contract to serve buckets (P2). |

### Z. Status bar, global states, responsive clipping, telemetry

| ID | Mockup | Delivered | Evidence | Class | Sev | Normative violation? | Disposition |
|---|---|---|---|---|---|---|---|
| MP-Z1 | Status bar: "● I4 Engine Ready \| Run: … \| Status: Completed \| Archives \| Rows" + right side "Memory: 512 MB (current) \| Disk Free: 312 GB \| Windows 11" | "state: ready \| run i4-20261008-M2 \| engine … \| archives … \| rows … \| read-only serving view — no live data, no processing"; no Memory/Disk/OS values | mockup; TASK64 D24 (wording residual); spec §4.3 host values "only if genuinely available and appropriate" — the app deliberately reads no host telemetry | 4 (wording) + 2 (telemetry) | low | No — fabricating Memory/Disk/OS values is forbidden; wording is not pinned | Leave as-is; optional P1 wording polish. |
| MP-Z2 | Mockups show only populated states | delivered distinguishes loading / empty / unavailable / error everywhere; unavailable never renders as zero/success/fake-empty (Identity KPI, Reliable Only, Trading Status, Saved empty state, Q8 census, associations-empty) | spec §8.1–§8.8; TASK62 §5 rule; TASK66 captures | parity (delivered is more complete) | — | No | None. |
| MP-Z3 | Fixed 1536×1024 composition (all content fits) | internal scrolling (`#content` overflow-y:auto); the long-tail segment legend + coverage list extend below the capture frame — data volume at the fixed mockup height; the stacked-page artifact that amplified clipping (F-N1) is corrected | TASK66 F-N5/F-N8; app.css `#content`; §3 | 3 (+4) | medium | No | Data-driven; P1 compact-legend polish (§8). Fresh capture confirms post-fix clipping. |
| MP-Z4 | (n/a) | error states: API failures render a contained error state per page region, never a global blank; stale/corrupt handled per spec §8.4/§8.5 | spec §8; app.js error handling | parity | — | No | None. |

**Register summary.** 58 register lines across the 26 categories. **After the F-N1
correction, zero remaining items violate a normatively binding requirement.** The
distribution: 1 defect (F-N1, corrected this task, pending fresh-capture visual
confirmation) · ~30 AUTHORITY-CONTRACT LIMITATIONS (the delivered UI implementing the
serving contract more faithfully than the illustrative mockup — withholding raw content,
not fabricating statuses/timestamps/quality buckets/enumerations) · ~12 DATA-DRIVEN
(as-served values vs illustrative mockup numbers) · ~10 VISUAL PARITY GAPS (cosmetic:
icons, legend density, wording, title symbol, rows-per-page default) · 1 UNRESOLVED
class used only inside Q1/Q4. Every "expected" value taken from the mockups was treated
as illustrative per spec §2.3; none was assumed normative against a serving contract.

## 6. The six unavailable navigation items — evidence-based analysis

For each: mockup promise → current display → real serving contract → evidence →
first-release authorization → safety requirements → recommendation.

| # | Item | Mockup promise | Current display | Real serving contract | Evidence | First-release authorization | Safety requirements | Recommendation |
|---|---|---|---|---|---|---|---|---|
| 1 | **Archives** | Enabled nav destination | Unavailable badge: "Not in the first-release scope (D16-12). Archive inventory is served on the Dashboard (Q9)." | Q9 serves the full archive inventory (used by the Dashboard Archive Browser + Archive Detail) | index.html:35; api.py Q9; TASK62 omission 3 | **Not authorized** as a page (D16-12 scope = dashboard + explorer); the data is already served and presented | none (read-only) | **Remain unavailable.** The promise is already fulfilled in-place (Dashboard). A dedicated Archives page is a presentation duplicate of Q9 — a future optional page (P2), not a first-release gap. Do not enable. |
| 2 | **Reconciliation** | Enabled nav destination | Unavailable badge: "Not a first-release page. Reconciliation facts are served via record detail (Q7) and the quality view (Q8)." | Reconciliation facts ARE served: Q8 aggregates (dashboard quality panel + Explorer Q8 view) and per-archive reconciliation records (Q7 detail "Reconciliation" group + "View Reconciliation" button, enabled) | index.html:38; app.js:1141–1152, 751–756; api.py Q7/Q8 | **Not authorized** as a page; the underlying facts are in-scope and displayed in two authorized places | none (read-only) | **Remain unavailable as a first-release page.** Facts are accessible where they are served. A dedicated read-only Reconciliation page (aggregates + per-archive drill-down) is a legitimate **future presentation feature** (P2) over already-served data — no new backend needed, but its own scope decision. Do not enable now. |
| 3 | **Determinism & Replay** | Enabled nav destination | Unavailable badge: "Not in the first-release scope. No serving operation provides replay/verification views." | **No UI serving operation exists.** Determinism evidence exists only as maintenance artifacts (D11 byte-exact replay evidence; `serving verify` CLI) — neither is a UI serving slice | index.html:41; api.py (no replay/verify endpoint); D11; serving CLI | **Not authorized.** Creating a view would require a **new serving operation** (new endpoint/contract) — a separate authority decision per D23 §17/§19 ("each withheld item requires its own future explicit authority decision") | A future view must be read-only and byte-exact-evidence based; must never expose or trigger processing, ingestion, or engine alteration | **Remain unavailable.** A "Determinism & Replay evidence view" (read-only presentation of D11-style replay/verify evidence) is a **future feature (P2)** contingent on a new serving operation + authority decision. Do not enable. |
| 4 | **Reports** | Enabled nav destination | Unavailable badge: "Not in the first-release scope. No report-serving operation exists." | **No report-serving operation exists** in the serving contract (api.py has no report slice). D23 §… grants the UI ownership of "report presentation" as a presentation-layer capability, but with no report data source in the serving contract there is nothing authorized to present | index.html:44; api.py; D23 (UI-owns list) | **Not authorized** to invent report content; the first-release scope (D16-12) contains no report operation | any future report must be derived strictly from served envelopes; no fabricated metrics | **Remain unavailable.** "Reports" (e.g., a run-summary report assembled from Q1/Q8/Q10 envelopes, exportable) is a **future feature (P2)** requiring an explicit scope decision (and, if export is part of it, export authorization). Do not enable. |
| 5 | **Engine Status** | Enabled nav destination | Unavailable badge: "Not a first-release page. Run identity and status are served on the Dashboard (Q10)." | `/api/status` (service/run/m2 state) + Q10 (run identity, engine identity, corpus, package manifest) are served and already displayed: dashboard run summary + status bar + title-bar service indicator | index.html:47; api.py `/api/status` + Q10; TASK66 captures (run block, status bar, service indicator) | **Not authorized** as a page; all status facts it would show are already served and displayed | none (read-only) | **Remain unavailable.** A dedicated Engine Status page would re-present already-visible facts (redundant). Optional **low-priority future page** (P2) if the user wants a consolidated status screen — presentation only, no new data. Do not enable now. |
| 6 | **Configuration** | Enabled nav destination | Unavailable badge: "Not in the first-release scope. The UI exposes no configuration-changing operation." | **No configuration operation exists** in the serving contract; the serving/application operates against the durable qualified baseline (D23: no live data, no processing, no engine alteration; single-user) | index.html:50; api.py (no config endpoint); D23 §17 | **Not authorized** — and the prohibition is positive: the UI must not expose controls that imply mutating operations (D23 scope; TASK62; no auth/multi-user/enterprise infrastructure at all) | exposing a Configuration surface would imply mutation authority that does not exist; must not be presented as a "coming soon" active control | **Remain unavailable, permanently at first release.** Revisit only if a genuinely authorized read-only configuration **view** (e.g., displayed serving configuration) is ever scoped — which itself would be a new decision. Do not enable. |

**Net:** none of the six mockup-enabled destinations is a defect, and none may be
enabled "because the mockup shows it enabled" (explicit task prohibition; spec §4.2).
Three (Reconciliation, Determinism & Replay, Reports) are legitimate **future**
candidates with different maturity (P2 roadmap, §8); three (Archives, Engine Status,
Configuration) are redundant or affirmatively out of scope.

## 7. Defects vs intentional limitations vs future features (separation)

- **Defects (contract/spec violations):** exactly one was found and corrected — **F-N1**
  (page exclusivity + nav state; §3–§4). No other register line is a defect. Final
  defect-closure requires the fresh-capture visual confirmation (§10).
- **Intentional limitations (authority/contract-driven, correct as-is):** MP-A1/A3,
  B1, C3/C4, D2/D5, H3, I1/I2, J1, K1–K4, L1, M2, N2/N3, O2, Q1–Q4, R1–R3, U1, Y1, Z1
  (telemetry) — each cited to its withholding instrument (D23 §17/§19, D15 §14, D16-12,
  D38/D39, spec §4.1/§4.2/§5.2/§6.4/§6.5/§16.4/§16.5, TASK62 omissions 1–13).
- **Future product enhancements (roadmap, each its own authority decision):** P1 polish
  (KPI card icons; compact segment legend; status-bar wording; chart/summary titles;
  rows-per-page default) and P2 features (Export; Columns selector; four-bucket quality
  view if the contract ever serves buckets; dedicated Archives/Reconciliation/Engine
  Status read-only pages; Determinism & Replay evidence view behind a new read-only
  serving operation; Reports behind a new scope decision; Settings/Help surface;
  multi-dataset selector).
- **Data-driven (not differences to fix):** MP-D1/D3, E1/E2, F1 (values), G1–G3, H1
  (values), N1, P1, S1, W2, X1 (values), Z3 (volume).

## 8. Prioritized roadmap

| Priority | Item | Class | Authorization required | Rationale |
|---|---|---|---|---|
| **P0** | Fresh Windows capture set (§12) → visual confirmation of F-N1 fix + TASK66 gaps G1–G4 (Archive Browser/Detail in view, populated inspector, Q8 census, legend tail) → final UI acceptance determination | acceptance (no code) | none (evidence only) | The only remaining gate to acceptance; the code side is done and tested |
| **P1** | KPI card icons (spec §5.2 anatomy) · compact top-N segment legend (+ "and N more codes") · status-bar wording polish (D24 residual) · Price Chart / Yearly Summary titles incl. symbol/period · rows-per-page default 20 | VISUAL PARITY GAP | bounded presentation task (like TASK65), spec-cited, no data changes | Cheap, pure presentation, raises perceptual parity without touching any contract |
| **P2** | Export (results/archive list) · Columns selector · dedicated Archives / Reconciliation / Engine Status read-only pages · Determinism & Replay evidence view (new read-only serving operation first) · Reports (new scope decision) · Settings/Help surface · multi-dataset selector | FUTURE PRODUCT ENHANCEMENT | **each item a separate authority decision** (house pattern: decision input → explicit authorization → scoped implementation → evidence → remote verification) | None is first-release scope; several require new serving operations; all deferred deliberately |

## 9. Not authorized / not implemented in this task

- No mockup-parity implementation beyond the bounded F-N1 correction (investigate /
  classify / report only — per the granted authority).
- None of the six unavailable navigation pages was implemented or enabled.
- No export, columns selector, quality buckets, dataset selector, settings/help,
  user-identity, or host-telemetry behavior added.
- No new page architecture, tabs, routing infrastructure, or redesign.
- No JavaScript change (the JS mechanism was verified correct before touching CSS).
- M2 package: read-only; no regeneration/rerun. No corpus/archive/serving-state
  alteration. No fabricated mockup data or operational results. No overwriting of
  TASK66 or earlier acceptance records (this report is a new additive document). The
  Windows evidence screenshots were **not** replaced or touched (evidence branch
  `d9815dfc…` verified unchanged at task start; this commit adds no screenshot files).

## 10. Remaining acceptance gaps until final UI acceptance

1. **F-N1 visual confirmation** — a fresh dashboard load + nav round-trip capture
   showing a single visible page and matching nav active state (tests prove the DOM
   contract; only a rendered capture proves the visual).
2. **TASK66 open gaps G1–G4** still require in-view captures: Archive Browser +
   Archive Detail (with the actions group), Explorer with a selected row and the
   populated Record Inspector (canonical fields + provenance + related-records state),
   and the Q8 quality census panel.
3. **Legend/coverage tail** (Z3) — confirm below-the-fold content is reachable and
   readable at the target viewport (scroll capture).
4. Optional return bundle (raw captures + SHA-256 manifest) for the evidence branch,
   per the TASK66 pattern.
Until items 1–3 are captured on the user's Windows machine and inspected, the UI
acceptance disposition remains **PENDING** (the TASK66 CONDITIONAL disposition stands
open, with its two code conditions now discharged).

## 11. Actual commands and results (verbatim, from this task)

```
# rollback repair (40th)
$ python3 audit vs 797966c…        → 218 files / 0 missing / 0 mismatched
$ git fetch origin arena/9021d1a1-nse-historical-data-engine:refs/tmp/session-verify
$ git update-ref refs/heads/arena/9021d1a1-nse-historical-data-engine 797966ccb2561ea11bf7521f25efe83f5cb67760  (guarded)
$ git reset --hard                  → worktree clean (only untracked _transfer_delivery/)

# F-N1 fix
$ edit src/ui/static/app.css        → inserted ".page[hidden] { display: none; }" (+comment) after the .page rule

# focused tests
$ node --check tests/ui_page_exclusivity_harness.js   → OK (clean)
$ node tests/ui_page_exclusivity_harness.js src/ui/static/app.js
  → PASS S1 dashboard selected: dashboard visible
  → PASS S1 dashboard selected: explorer hidden
  → PASS S1 nav: dashboard aria-current
  → PASS S1 nav: explorer not current
  → PASS S1: exactly one page visible (never both, never none)
  → PASS S2 explorer selected: explorer visible
  → PASS S2 explorer selected: dashboard hidden
  → PASS S2 nav: explorer aria-current
  → PASS S2 nav: dashboard not current
  → PASS S2: exactly one page visible (never both, never none)
  → PASS S3 round-trip: dashboard visible again
  → PASS S3 round-trip: nav restored
  → PASS S3: exactly one page visible (never both, never none)
  → HARNESS OK   (exit 0)

$ PYTHONPATH=src python3 -m unittest tests.test_ui_page_exclusivity -v
  → Ran 8 tests in 0.066s — OK

# negative control (proves the test catches the pre-fix state)
$ git show HEAD:src/ui/static/app.css | python3 -c "…regex…"
  → pre-fix .page[hidden] rule present: False  (regression test would FAIL pre-fix: True)
  → pre-fix .page display rule: True

# full suite (justified: shipped CSS changed)
$ PYTHONPATH=src python3 -m unittest discover -s tests -t .
  → Ran 900 tests in 81.775s — OK (skipped=14)
    (14 = standing D24_M2_ROOT disk-gated legs; suite count 892 → 900 = +8 new)

# remote identities at task start
$ git ls-remote origin
  → arena/9021d1a1-…  797966ccb2561ea11bf7521f25efe83f5cb67760
  → evidence/i4-ui-visual-acceptance-2026-10-10  d9815dfcfe8f6f6428cf11feb2bb29ef728a4f42
  → main  69977017ffca944921f231d7904347bc582b6392
  → docs/i4-ui-mockup-references  726b1c36…
  → docs/i4-historical-data-engine-ui-spec  20bf8238…
```

No other test commands were run; no test result above is inferred or simulated.

## 12. Windows screenshot requirements for the next acceptance run (fresh capture set)

Viewport 1536×1024, same capture contract as TASK64/66 (PowerShell script pattern;
terminal stays open; fail-closed; no `exit`/`return`/`else`/`elseif`/`finally`):

1. **Dashboard, initial load** — after serving start, before any interaction. Proves:
   single visible page (no explorer content stacked below), nav Dashboard
   `aria-current`, KPI row, run summary, charts, archive browser top, status bar.
2. **Data Explorer after one nav click** — proves: exclusive visibility (dashboard gone),
   nav active state switched, builder + quick filters + empty-result state.
3. **Dashboard after second nav click** (round-trip) — proves state restoration.
4. **Explorer with a selected result row** — run a Q3 snapshot (any instrument present
   in the package, e.g., the TASK66 HDFC/EQ query), select a row; capture the Record
   Inspector fully in view: Instrument / Trading Details / Data Quality / Provenance
   (D05 §8) / Related Records state + the three action buttons (two visibly disabled
   with reasons).
5. **Explorer Q8 quality view** — the census panel in view (dashboard Q8 panel also
   acceptable if the explorer view is out of frame).
6. **Archive Browser + Archive Details** — select an archive row; capture the detail
   panel with the four action buttons (Calendar Overlay visibly disabled).
7. **Dashboard bottom (scrolled)** — status bar + segment-legend/coverage tail, proving
   below-fold content is readable (Z3).
Optional: return bundle (raw PNGs + SHA-256 manifest) pushed to the evidence branch per
the TASK66 pattern.

## 13. Unresolved questions

- **Q1:** Should the segment legend/coverage display as-published series codes with a
  friendly-name alias layer (the mockup's four CM/FO/Currency/Debt names)? No mapping
  operation exists in the serving contract; this is a presentation decision for the
  user (roadmap P1/P2). Not a defect.
- **Q2:** Should rows-per-page default to 20 to match the mockup? Cosmetic; spec does
  not pin a default (P1 candidate).
- **Q3:** Is a Settings/Help affordance desired? Not in the serving contract; would
  need its own authorization (P2). The delivered service-state indicator currently
  carries the only "live" status.
- **Q4:** Tabbed inspector (Canonical/Source Evidence/Related) vs the current
  contract-driven groups? Spec §6.5 calls tabs "reference" and the §16.4 groups the
  contract-driven grouping the delivered UI follows (P1 cosmetic if the user prefers
  tabs).
- **Q5 (open, external):** final UI acceptance determination — requires the §12 fresh
  captures on the user's Windows machine; Arena has no Windows access.

## 14. Baseline/remote verification record (publication state)

- Publication plan (this task): **one additive commit** on
  `arena/9021d1a1-nse-historical-data-engine` containing exactly:
  `src/ui/static/app.css` (F-N1 fix), `tests/ui_page_exclusivity_harness.js` (new),
  `tests/test_ui_page_exclusivity.py` (new), and this report
  (`docs/investigations/TASK67_I4_UI_PAGE_EXCLUSIVITY_MOCKUP_PARITY_NAVIGATION_SCOPE.md`,
  new). No screenshot files, no M2/corpus/archive bytes, no `_transfer_delivery/`
  content. Fast-forward push to the session branch only; main never promoted;
  post-push `git ls-remote` + FETCH_HEAD blob-identity re-verification before the final
  determination (standing publication contract).
- Evidence branch `evidence/i4-ui-visual-acceptance-2026-10-10` (`d9815dfc…`) and all
  prior acceptance records: untouched by this task (verified at start; commit staged
  files verified to contain no screenshot paths).

## 15. Prohibitions compliance statement

- M2 package: **read-only** — no modify/regenerate/rerun (no M2-touching command was executed).
- No corpus regeneration; no archive/serving-state alteration.
- No fabricated mockup data, dates, records, quality buckets, or operational results —
  every delivered value in §5 is cited to a served envelope or an "unavailable" state;
  every mockup value is marked illustrative.
- No navigation item enabled; the six pages not implemented; no new page
  architecture/tabs/routing/redesign; no JavaScript change.
- No authentication/multi-user/database/enterprise infrastructure.
- No overwriting of prior acceptance records (new additive report; TASK66 report blob
  `57e49a5e…` intact at HEAD and on the remote).
- No discarding of unrelated work (40th rollback repaired value-audit-first, non-destructively).
- No visual-acceptance claim from automated tests — final UI acceptance is explicitly
  **PENDING** the §12 fresh captures; the "UI matches mockup" claim is made **not** until
  those captures are inspected.
- The attached reference image was not used in place of repository-resident mockup
  inspection (both in-repo PNGs inspected in full, §2).
- No assumption of Arena access to the user's Windows filesystem.

**Report status:** complete and additive; publication per §14.
