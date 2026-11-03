# I4 Historical Data Engine — UI Presentation Specification

**Proposed repository destination:** `docs/design/I4_HISTORICAL_DATA_ENGINE_UI_SPEC.md`  
**Specification status:** Non-authoritative design reference  
**Product:** I4 Historical Data Engine — 10-Year NSE Corpus  
**Reference material:** Two user-supplied UI mockups (Dashboard / archive operations workspace and Data Explorer / record investigation workspace), supplemented by the user-provided Google Gemini UI specification as secondary design input  
**Purpose:** Provide one consolidated visual, layout, interaction, and acceptance reference for implementation of the presentation layer. The screenshots are the visual source of truth; the Gemini document contributes component-level detail but does not override the screenshots or governing contracts.

> **Authority and precedence:** This document describes the intended user experience represented by the supplied mockups. It is not an implementation authorization, a serving/API contract, a persistence contract, or evidence of operational capability. Existing authoritative governance and serving contracts prevail. In particular, follow D16-11, D16-12, D23 (including §13, §14, §17(b), §18 and §19), and the established D30a–D39 serving behavior. Do not expose a control or data path merely because it appears in a mockup. Where a capability is unsupported, unapproved, or explicitly withheld, preserve the visual intent where useful but disable, omit, or clearly mark the operation unavailable.

---

## 1. Goals and non-goals

### 1.1 Goals

1. Reproduce the supplied mockups as closely as practical on a desktop Windows application.
2. Provide a consistent shared application shell for Dashboard and Data Explorer.
3. Preserve the mockups' information hierarchy, density, dark visual theme, navigation, tables, detail panels, charts, and status indicators.
4. Make the visible controls correspond to real, authorized behavior rather than decorative or fabricated functionality.
5. Reuse the established serving layer, query semantics, saved-query behavior, and query-history behavior.
6. Preserve fail-closed behavior for invalid, stale, corrupt, missing, or unavailable data.
7. Make visual fidelity and functional correctness separately testable.

### 1.2 Non-goals

This specification does not authorize or require:
- New processing, verification, build, or engine-control operations.
- Raw source-record, raw archive, or archive-byte access.
- Direct UI access to durable storage.
- New query or persistence semantics.
- Live market data or external data-provider integration.
- Authentication/RBAC or multi-user architecture.
- PostgreSQL or other infrastructure solely to support the presentation.
- Fabricated sample metrics, hard-coded “successful” states, or synthetic operational claims.
- Promotion to `main` or Windows real-M2 qualification.

---

## 2. Reference screenshots and interpretation

### 2.1 Reference A — Dashboard

The first screenshot depicts a dark desktop operations dashboard with:
- A narrow application title bar and top-right Settings/Help/window controls.
- A fixed left navigation rail.
- A primary heading and run summary.
- A top-right action area.
- Five KPI cards.
- Two analytical charts and a data-coverage summary.
- A large archive browser with search and filters.
- A selected archive detail panel.
- A recent engine-log panel.
- A persistent bottom status bar.

### 2.2 Reference B — Data Explorer

The second screenshot depicts a similarly styled application shell with:
- Branding and user/settings area.
- A left navigation rail with Data Explorer active.
- Dataset context and aggregate counts.
- Four query-mode tabs.
- Query-builder fields, optional filter rows, quick filters, and actions.
- A large query-result table.
- A record-detail inspector on the right.
- A saved-query list in the left region.
- Price, yearly-summary, and data-quality panels below the result grid.
- Provenance and record-navigation actions.
- A persistent bottom status bar.

### 2.3 Reference-data rule

Numbers, names, dates, symbols, status labels, log lines, chart series, and provenance values visible in the screenshots are illustrative visual content, not authoritative engine results. Populate the application from verified serving responses. Never hard-code screenshot values as live operational truth. If a metric is not supplied by an authorized operation, render an explicit unavailable state.

---

## 3. Visual design system

The screenshot pixels are the ultimate visual reference. The numeric values below are **implementation starting tokens inferred from the screenshots**, not measurements extracted from source design files. Tune them by side-by-side comparison with the supplied images.

### 3.1 Overall appearance

- Theme: dark, high-contrast, data-dense desktop workspace.
- Main canvas: very dark blue/navy.
- Panels: slightly lighter blue/navy with subtle blue-gray borders.
- Primary action/accent: vivid blue.
- Secondary text: cool, muted blue-gray.
- Primary text: near-white.
- Positive/success: green.
- Warning/uncertain: amber/yellow.
- Error/missing: red/coral.
- Chart colors: blue as dominant series, with orange, yellow and coral secondary categories.
- Avoid large whitespace, oversized rounded cards, bright white surfaces, excessive gradients, or mobile-first stacking at the target desktop size.

### 3.2 Color tokens

Use centralized design tokens/CSS variables or equivalent theme constants. Suggested initial palette:

| Token | Suggested value | Intended use |
|---|---|---|
| `--app-bg` | `#0B1329` | Main application background |
| `--titlebar-bg` | `#081725` | Top/title bar |
| `--sidebar-bg` | `#0A1B2B` | Navigation rail |
| `--sidebar-active` | `#123F6A` | Active navigation background |
| `--panel-bg` | `#0F2237` | Primary cards and panels |
| `--panel-bg-alt` | `#132B40` | Nested panels / secondary regions |
| `--panel-header-bg` | `#173249` | Table headers and section headers |
| `--input-bg` | `#0A1A29` | Inputs, select controls, filter cells |
| `--border` | `#203A50` | Panel/table borders |
| `--border-strong` | `#2A4B65` | Focused/stronger separators |
| `--text-primary` | `#F2F6FC` | Headings, primary values |
| `--text-secondary` | `#C0D0E0` | Labels and normal supporting text |
| `--text-muted` | `#8FA7BD` | Hints, metadata, inactive text |
| `--accent` | `#3B82F6` | Primary buttons, links, selected rows |
| `--accent-hover` | `#60A5FA` | Hover state for primary action |
| `--accent-soft` | `#1D4F85` | Subtle selected/active surfaces |
| `--success` | `#20D18A` | Success/reliable/complete |
| `--warning` | `#F5C542` | Uncertain/warning |
| `--error` | `#FF665F` | Error/missing/failure |
| `--chart-orange` | `#FF813D` | Secondary chart category |
| `--chart-yellow` | `#F4C83D` | Secondary chart category |
| `--chart-coral` | `#FF716D` | Secondary chart category |
| `--scrollbar-track` | `#0A1B2A` | Scrollbar track |
| `--scrollbar-thumb` | `#39556B` | Scrollbar thumb |

**Color rules**
- Use the same token for the same semantic purpose across both screens.
- Never use green solely to make a result look successful; derive status from real response data.
- Distinguish “unavailable” from “zero.” Use muted text and an explicit unavailable label for unknown values.
- Do not encode quality only by color; include text labels or accessible names.
- Keep borders understated. The visual separation should come primarily from small background-value differences and fine borders.
- Verify contrast after implementation, especially muted text, table rows, disabled controls and focus indicators.

### 3.3 Typography

Use a clean system sans-serif stack for application UI, with a monospace face for logs and code-like provenance.

Suggested stacks:
- UI: `Inter, "Segoe UI", Arial, sans-serif`
- Monospace: `Consolas, "Cascadia Mono", monospace`

| Element | Starting size | Weight | Notes |
|---|---:|---:|---|
| Application title | 16–18 px | 600 | Compact title-bar label |
| Page heading | 26–30 px | 650–700 | Dashboard/Data Explorer heading |
| Section heading | 16–18 px | 600 | Cards, tables and inspector |
| KPI value | 25–29 px | 650–700 | Large, prominent number |
| KPI label | 12–14 px | 400–500 | Supporting descriptor |
| Body/control text | 13–14 px | 400–500 | Dense desktop UI |
| Table header | 12–13 px | 500–600 | High legibility at compact height |
| Table cell | 12–13 px | 400 | Numeric columns right-aligned where appropriate |
| Metadata/secondary | 11–13 px | 400 | Must remain legible |
| Status bar | 11–12 px | 400 | Single-line compact status |
| Engine logs | 11–12 px | 400 | Monospace |

Typography rules:
- Prefer compact line-height: approximately 1.25–1.4 for controls and tables.
- Avoid excessive bold. Use weight and color to establish hierarchy.
- Use tabular numerals for KPI values, counts, and aligned numeric columns where available.
- Keep date/time formatting consistent across the application and follow the engine's established convention.
- Truncate long archive paths and hashes visually, but make the full value inspectable through an approved interaction such as copy/details. Do not fabricate hash fragments.

### 3.4 Spacing and geometry

Use an 8 px base spacing system with 4 px half-steps for dense areas.

Suggested tokens:
- `space-1`: 4 px
- `space-2`: 8 px
- `space-3`: 12 px
- `space-4`: 16 px
- `space-5`: 20 px
- `space-6`: 24 px
- `space-8`: 32 px

Desktop layout starting points:
- Target comparison viewport: **1536 × 1024 px** (matching the supplied screenshots' displayed canvas).
- Application top bar: approximately 40–48 px high.
- Left navigation rail: approximately 224–232 px wide.
- Bottom status bar: approximately 28–34 px high.
- Main content padding: approximately 10–16 px.
- Gap between major panels: approximately 8–12 px.
- Panel corner radius: approximately 4–7 px.
- Input/button height: approximately 32–38 px.
- Table header height: approximately 32–36 px.
- Table row height: approximately 28–32 px.
- Border width: 1 px.
- Avoid large shadows; use subtle separation only where needed.

These are initial targets. Compare rendered screenshots at the target viewport and adjust to the actual reference rather than treating these estimates as immutable pixel measurements.

### 3.5 Layering and surfaces

Recommended surface hierarchy, from back to front:
1. Application canvas.
2. Sidebar and title/status bars.
3. Main cards and content panels.
4. Nested regions such as chart plot areas, filter grids and table containers.
5. Inputs, selects, tabs and buttons.
6. Selected table rows and active controls.
7. Popovers, menus, tooltips and dialogs.
8. Keyboard focus indicator.

Rules:
- Keep the sidebar and bottom status bar visually stable while main content scrolls, unless the chosen framework makes this impractical.
- Avoid nested scrollbars where possible. Tables may scroll internally; the whole page should not acquire a second unnecessary horizontal scrollbar.
- Menus/popovers must appear above cards and tables without being clipped by overflow containers.
- Dialogs, if needed, should use a restrained dark overlay and remain consistent with the theme.
- Selected rows should use an accent-blue fill and retain readable text and status icons.
- Hover is a subtle tint change; it must not resemble selection.
- Focus must be visibly distinct from hover and selection.

### 3.6 Controls, borders, and icons

- Buttons: compact rectangular controls with modest corner radius; primary actions use the accent blue, secondary actions use a dark panel fill and border.
- Inputs/selects: dark fill, thin blue-gray border, clear labels, visible keyboard focus.
- Tabs: compact horizontal strip; selected tab uses a blue fill or strong blue underline consistent with the reference.
- Tables: fine horizontal and vertical separators; dense but readable rows.
- Icons: consistent stroke/fill style, typically 16–22 px in navigation and 18–24 px in KPI cards. Use the project's existing icon library if one exists; do not add a large dependency solely for icons.
- Status indicators: combine a small icon/dot with explicit text such as Reliable, Uncertain, Missing, Processed, Unavailable or Error.
- Scrollbars: narrow, subdued, visible enough to indicate overflow.
- Avoid emoji as substitutes for application icons.

---

## 4. Shared application shell

### 4.1 Top/title bar

Provide a compact top strip across the application. Include:
- Product icon/mark and `I4 Historical Data Engine (10-Year NSE Corpus)` title.
- Right-aligned Settings and Help affordances if permitted.
- User/environment or window controls only if consistent with the actual host environment and existing contract.
- A fine bottom border separating the title bar from content.

The two supplied references vary slightly in their right-side header controls. Prefer one consistent implementation aligned to the actual host application; do not create fictitious identity or user-management behavior.

### 4.2 Left navigation

Provide a consistent navigation rail with the items shown in the reference:

1. Dashboard
2. Archives
3. Data Explorer
4. Reconciliation
5. Determinism & Replay
6. Reports
7. Engine Status
8. Configuration

Use a left icon plus label, compact vertical spacing, and a strong active-state background. Dashboard is active in Reference A; Data Explorer is active in Reference B.

The presence of a navigation item does not prove the destination is implemented or authorized. For an unsupported destination, either omit it from the active release or render a clear unavailable/placeholder state without exposing unauthorized operations. Do not add fake pages containing fabricated data.

### 4.3 Bottom status bar

Use a persistent, compact strip across the bottom, showing only values actually available from an authorized source, for example:
- Engine readiness/state.
- Selected or most recent run identifier.
- Run status.
- Archive and canonical-row counts.
- Memory/disk/OS information only if genuinely available and appropriate to the application.

Do not invent health, run, resource, or environment data. Unknown values must be explicit and visually distinct from zero.

---

## 5. Dashboard specification

### 5.1 Page header and run summary

At the top of the content area:
- Large heading: `10-Year NSE Historical Data`.
- Short supporting line describing available product areas, but list only features actually exposed and authorized.
- Run summary to the right: run ID, date/time, engine/version, corpus, and archive count when available.
- A separate action region at the upper right.

The screenshot shows “Run New Processing” and “Verify Existing Run.” These are reference controls only. They must remain absent or disabled unless the corresponding operation is explicitly authorized and supported. A presentation task must not implement or expose processing/verification authority by implication.

### 5.2 KPI row

Display five similarly sized cards across one row:
1. Archives Processed
2. Canonical Rows
3. Identity Records
4. Trading Calendars
5. Errors

Each card has:
- A large value.
- A compact descriptive label.
- A simple icon.
- A status glyph only where a real status can be established.

Rules:
- Use consistent heights, inner padding and value alignment.
- Keep values visually prominent.
- Counts must derive from authorized responses.
- Do not display a green success glyph merely because a count is nonzero.
- Missing metrics should show `Unavailable` or an equivalent explicit state.

### 5.3 Charts and data coverage

Arrange three adjacent regions beneath the KPI row:
- A wider `Rows by Year` chart.
- A medium `Archives by Exchange Segment` chart.
- A narrower `Data Coverage` summary.

Approximate width ratio at the target viewport: **46 : 36 : 18**, adjusted to fit available content width.

#### Rows by Year
- Vertical bar chart.
- Year labels along the horizontal axis.
- Row counts along the vertical axis.
- Muted gridlines and axis labels.
- Blue primary bars.
- Axis units formatted compactly only when the underlying values support it.
- Empty/unavailable state when no suitable authorized data is returned.

#### Archives by Exchange Segment
- Doughnut chart with the total count centered inside.
- Legend containing segment name, count, and percentage when all required values are available.
- Blue dominant segment; orange, yellow, and coral for additional segments.
- Colors must be stable by segment, not arbitrarily reshuffled on each render.
- Percentages must be computed from the same returned population as the displayed total.

#### Data Coverage
Compact key/value rows for:
- Start date.
- End date.
- Total archives.
- Total rows.
- Instruments.
- Exchange segments.
- Trading days.

Use right-aligned values, consistent row heights and subtle separators where useful. Do not infer missing coverage dates or treat calendar weekdays as confirmed trading days.

### 5.4 Archive browser

Place the archive browser in a large panel below the chart row. In the reference it occupies most of the lower content width, leaving a right-hand detail panel.

Header controls:
- Title and result count.
- Search field.
- Exchange-segment filter.
- Year filter.
- Export action, only if an authorized export operation exists.

Table columns shown in the reference:
- Archive Name
- Date
- Segment
- Symbol
- Status
- Rows
- File Size

Requirements:
- Use compact rows with clear column boundaries.
- Support horizontal or internal vertical scrolling only as needed.
- Numeric values should align consistently.
- Status includes an icon and label.
- Selected row uses a vivid blue fill.
- Search/filter actions must actually affect the displayed data.
- Sorting indicators must reflect real sorting behavior.
- Do not expose archive bytes or unrestricted filesystem access through the table.

### 5.5 Archive detail panel

Selecting a row should update a companion detail panel.

Reference fields:
- Archive Name
- Date
- Segment
- Symbol
- Status
- Rows
- File Size
- SHA-256

Requirements:
- Present only fields returned by an authorized operation.
- Truncate long hashes for layout only; preserve exact source values.
- Do not present a partial hash as if it were a full hash.
- Do not add an archive path or raw-content action unless explicitly permitted.
- The selected archive should remain visually obvious in the table.

The screenshot contains buttons for Canonical Data, Identity/Association, Calendar Overlay, and Reconciliation. Each button requires an individually verified permitted operation. Where allowed, navigate or filter within the existing presentation; do not bypass the serving boundary.

### 5.6 Engine logs

Provide a bottom panel with a compact title and a scrollable, monospace log view if authorized log-serving functionality exists.

Requirements:
- Display only actual log records from an authorized source.
- Preserve timestamps, severity and message text.
- Do not fabricate a successful run or substitute mock logs in a live state.
- A file-system action such as `Open Log Folder` must not be exposed unless the environment and authority explicitly support it.
- Empty and unavailable states must be clear.

---

## 6. Data Explorer specification

### 6.1 Page heading and dataset summary

Show:
- Page title: `Data Explorer`.
- A concise subtitle.
- Dataset selector only if multiple authorized datasets are available.
- Summary panel with total archives, total rows, date range and last-updated timestamp when provided.

Do not imply the existence of multiple datasets if the serving layer exposes only one. Dataset/version labels must come from a trusted source.

### 6.2 Query-mode tabs

Reference tabs:
1. Query Builder
2. Advanced Query
3. Saved Queries
4. Query History

Use a compact horizontal tab strip directly above the query area.

- Selected tab is visibly highlighted.
- Switching tabs preserves state where reasonable and contractually safe.
- Query Builder uses the established query contract.
- Advanced Query must not introduce an alternate query path or a more powerful language unless explicitly authorized.
- Saved Queries reuses D38 semantics.
- Query History reuses D39 semantics.
- Do not duplicate saved-query or history persistence logic in the UI.

### 6.3 Query Builder

Organize controls into a dense, labeled grid.

#### Main filters

Reference controls:
- Date Range: From and To.
- Instrument selector/type and instrument value.
- Segment.
- Series / Market Type.
- Trading Status.
- Exchange Segment.

Use appropriate date, text, search, and select controls. Each control must reflect the accepted field types and values from the existing query contract.

Validation:
- Reject invalid dates and invalid ranges using existing contract behavior.
- Do not silently change the user's requested dates.
- Distinguish invalid input from an empty result.
- Do not submit a request until required fields pass validation.

#### Optional filters

Display rows with:
- Field
- Operator
- Value
- Remove control

Include an `Add Filter` action if the serving contract supports the filter construction. Field names, operators and value types must be contract-driven, not arbitrary strings that the backend cannot honor.

#### Quick filters

Reference examples:
- EQ (CM)
- EQ (FO)
- Currency
- Debt
- Latest 1Y
- Latest 3Y
- Latest 5Y
- Latest 10Y
- Reliable Only

These are presets, not new query semantics. Each preset must map deterministically to a supported query. Do not invent the meaning of “Latest” or “Reliable” if the governing contract does not define it. Where a preset cannot be supported exactly, omit it or mark it unavailable rather than approximate silently.

#### Actions

Reference actions:
- Run Query
- Reset
- Save Query

Requirements:
- Run Query invokes the authorized serving operation and reports its actual result state.
- Reset resets the visible query form according to a consistent rule.
- Save Query uses the established saved-query contract.
- Disable controls while an operation is pending where appropriate, preventing duplicate submissions.
- Show validation and failure feedback in the same visual language as the rest of the application.

### 6.4 Query results

Show a results header with:
- Number of records, if known.
- A compact summary of the active query.
- Export menu, if authorized.
- Columns menu, if column selection is supported.
- Rows-per-page selector, if supported.
- Current range and pagination controls.

Reference table columns:
- Row number
- Trade Date
- Symbol
- ISIN
- Series
- Segment
- Open
- High
- Low
- Close
- Volume
- Turnover (₹)
- Status

Implementation rules:
- Bind columns to actual returned fields.
- Use consistent date and number formatting.
- Align numeric values consistently.
- Use compact row heights and fine separators.
- Highlight the selected row with blue fill.
- Make horizontal scrolling usable without obscuring row selection.
- Do not fabricate a record count, page range or total when the serving response does not provide it.
- Preserve deterministic ordering according to the established contract.
- Pagination must not imply that all records were fetched when only a page is available.

### 6.5 Record-detail inspector

The right-hand inspector updates when a result is selected. Include only fields returned through authorized operations.

Reference tabs:
- Canonical Record
- Source Evidence
- Related Records

Potential canonical-record groups shown in the reference:
- Instrument: Symbol, ISIN, Series, Company ID, Company Name.
- Trading Details: Trade Date, Segment, Open, High, Low, Close, Volume, Turnover, Trading Status.
- Data Quality: Identity Status, Record Status, Association Status.
- Provenance: Source Archive, Source Row, Archive Path, Raw Hash.

The groups and labels are visual guidance; actual fields and semantics must come from the established contracts.

**Critical access constraints**
- Do not expose Source Evidence or Related Records until their exact permitted fields and operations are verified.
- Do not expose raw archive paths, raw hashes, raw source records or archive bytes unless expressly permitted.
- D23 §19's raw-content-serving restriction prevails over the screenshot.
- Do not infer reliability from missing fields or apply new quality semantics in the presentation layer.
- Show unknown values explicitly rather than filling them with plausible examples.

Reference actions:
- Previous / Next record.
- View Raw Record.
- View Archive.
- View Reconciliation.

Previous/Next may navigate within the current authorized result set if implemented correctly. The other actions require independent authorization and serving-capability checks; prohibited actions must not be exposed as active controls.

### 6.6 Price chart

Show a compact `Price Chart` panel beneath the results table.

- A selectable price field such as Close Price, only if supported.
- Date axis with compact time labels.
- Price axis with legible gridlines.
- A line for the selected series.
- Optional volume bars only if supported by returned data.
- Empty/unavailable state when no valid series is available.

Chart data must be derived from the query results or a specifically authorized serving operation. Do not add a new broad data retrieval path solely for charting.

### 6.7 Yearly summary

Show a compact summary for the selected year or period:
- Records.
- Open (First).
- Close (Last).
- High (Year).
- Low (Year).
- Volume (Total).
- Turnover (₹).

Each calculation must have a documented and tested definition consistent with the returned records and established ordering. Do not label a period summary “yearly” if the data covers a different period. Do not present unavailable aggregates as zero.

### 6.8 Data-quality summary

A doughnut chart or similarly compact visualization may show:
- Reliable.
- Uncertain.
- Missing.
- Excluded.

Requirements:
- Use the existing data-quality classification and semantics.
- Percentages and total counts must reconcile.
- Do not reinterpret missing data as unreliable or excluded unless the contract says so.
- Accessible text labels must accompany colors.
- If the source does not supply the classifications, show unavailable rather than inventing them.

### 6.9 Saved-query sidebar

The reference has a compact list of named saved queries and a `New Query` action.

Requirements:
- Use the established D38 behavior.
- Show the selected saved query distinctly.
- Support only authorized create, select, update, or delete behavior.
- Do not invent new identity, ownership, sharing, or collaboration semantics.
- Empty state should guide the user without suggesting unsupported capabilities.

### 6.10 Query history

Use the established D39 behavior:
- Display real recorded query-history entries.
- Make selection and replay/navigation consistent with the existing contract.
- Distinguish a historical record from a new query execution.
- Do not manufacture history entries merely because a query form was opened.
- Preserve explicit history-recording semantics.

---

## 7. Responsive behavior and desktop target

The references are dense desktop layouts. Primary visual acceptance should use a **1536 × 1024 px** viewport and compare against the supplied images at equivalent scale.

Suggested behavior:
- At the target desktop size, preserve the side-by-side chart, archive/details and result/inspector compositions.
- At narrower widths, reduce main-content gaps and allow panels to reflow without overlapping.
- On narrow windows, the details panel may move below the primary table; it must remain discoverable.
- Avoid shrinking table text below a comfortable readable size merely to force every column into the viewport.
- Keep navigation usable if the window narrows.
- Do not require a mobile layout to the detriment of the desktop reference.
- Preserve keyboard access and visible focus states at every size.

If the real host application has a fixed minimum window size, document and test that minimum rather than pretending to support arbitrary resizing.

---

## 8. Interaction and state rules

All controls must have real, coherent behavior. No decorative-only actions should appear enabled.

### 8.1 Loading
- Indicate the operation or panel being loaded.
- Preserve the surrounding layout to avoid large jumps.
- Prevent duplicate submissions where appropriate.
- Do not show a success state before the serving operation completes.

### 8.2 Empty
- Explain that no records/results are available for the current selection.
- Keep the query and filters visible so the user can adjust them.
- Do not conflate empty results with backend failure.

### 8.3 Invalid
- Identify the invalid field or action.
- Preserve valid user input.
- Follow existing contract validation.
- Do not silently broaden or alter the query.

### 8.4 Stale
- Mark data as stale only when the existing contract or source metadata establishes staleness.
- Keep timestamps and status labels truthful.
- Do not infer freshness from UI render time.

### 8.5 Corrupt
- Fail closed.
- Do not render malformed data as a normal record.
- Show a clear, non-destructive error state without leaking raw content.

### 8.6 Unavailable
- Explicitly distinguish unavailable information from a numeric zero, empty string, or confirmed absence.
- Keep unaffected panels usable when possible.
- Do not invent fallback values.

### 8.7 Error
- Display concise, actionable feedback.
- Preserve diagnostic detail only where authorized.
- Never claim a successful operation when it failed or could not be verified.

### 8.8 Status semantics
Status labels and colors must be consistent throughout the application:
- Success/complete/reliable: green, when established by actual data.
- Warning/uncertain: amber.
- Error/missing/failure: red/coral.
- Unknown/unavailable/inactive: muted blue-gray.
- Selected/focused: blue, with focus distinguished from selection.

---

## 9. Accessibility and usability

- All controls must be keyboard-operable.
- Provide visible focus indicators with adequate contrast.
- Associate labels with inputs.
- Provide accessible names for icon-only controls.
- Do not use color as the sole indicator of status.
- Ensure selected rows and active tabs are conveyed beyond color where feasible.
- Use semantic table headers and sensible reading order.
- Provide chart titles, axis labels, legends and a text summary of essential values.
- Support tooltips or equivalent inspection for truncated long values, without relying on hover alone.
- Avoid rapid animations or visual transitions that interfere with dense data work.
- Keep click targets practical even in the compact reference layout.

---

## 10. Serving boundary and governance requirements

This section is binding as a design constraint only insofar as it restates the existing authoritative contracts; it does not grant new authority.

1. The UI consumes data only through the authorized serving boundary.
2. The UI must not read durable storage directly.
3. Do not introduce an alternate query path.
4. Expose only authorized serving operations, including the specific limits on delegated operation (b).
5. Do not expose processing triggers, source-row access, raw-record access, archive-byte access or any other prohibited operation.
6. Respect the explicit withholding of raw-content serving in D23 §19.
7. Reuse established D30a–D39 query, saved-query and history behavior.
8. Preserve existing canonical-JSON failure semantics.
9. Do not change the serving, persistence, identity, quality, or query contracts merely to match a mockup.
10. Treat unsupported UI elements as a design-to-contract gap, not as permission to invent a backend operation.
11. Do not include actual sensitive raw content in logs, error messages, screenshots, fixtures or generated evidence.
12. Do not claim that a screenshot proves the real engine's run, data population, provenance or qualification.

---

## 11. Visual-fidelity acceptance criteria

At the 1536 × 1024 target viewport, compare each implemented screen side by side with its reference screenshot.

### 11.1 Shared shell
- [ ] Application title, header, sidebar and status bar have consistent dimensions and alignment.
- [ ] Dark navy palette, blue accents and restrained borders are visually close to the reference.
- [ ] Typography hierarchy and density are comparable.
- [ ] Active navigation is immediately recognizable.
- [ ] Panels align to a consistent grid with compact spacing.

### 11.2 Dashboard
- [ ] Page heading and run-summary region match the reference hierarchy.
- [ ] Five KPI cards appear in one aligned row where the viewport permits.
- [ ] Chart/coverage panels use the same three-region composition.
- [ ] Archive browser and selected-item inspector appear side by side.
- [ ] Archive rows, selected state, status labels and details hierarchy are consistent.
- [ ] Logs occupy a compact bottom panel.
- [ ] No hard-coded reference metrics are represented as real values.

### 11.3 Data Explorer
- [ ] Query tabs and filter area occupy the upper workspace.
- [ ] Optional filters and quick filters are clearly separated.
- [ ] Query results occupy the main lower-left area.
- [ ] Record inspector is visible alongside the results at the target viewport.
- [ ] Chart, yearly summary and quality summary occupy the lower region.
- [ ] Saved queries are discoverable without obscuring the main workflow.
- [ ] Long provenance fields are handled cleanly without fabricating data.
- [ ] Prohibited actions are absent or visibly unavailable.

### 11.4 Functional fidelity
- [ ] Query controls map to actual supported query fields/operators.
- [ ] Query execution, reset, saved-query and history interactions work as specified.
- [ ] Record selection updates the inspector.
- [ ] Charts and summaries derive from real authorized data.
- [ ] Loading, empty, invalid, stale, corrupt, unavailable and error states are distinguishable.
- [ ] No enabled control is decorative-only.
- [ ] No direct durable-storage access or alternate query path is introduced.

### 11.5 Verification evidence
- [ ] Capture screenshots at the target viewport for Dashboard and Data Explorer.
- [ ] Compare screenshots against the two supplied references.
- [ ] Record visible differences and justify any deviation caused by authority, unavailable data, or host limitations.
- [ ] Run focused interaction tests and existing serving tests justified by the change.
- [ ] Independently verify the serving boundary and final diff.
- [ ] Do not claim pixel-perfect parity without actual screenshot comparison.

---

## 12. Recommended implementation order

1. Verify the authoritative baseline and the Task 60 readiness record.
2. Map the reference components to existing serving operations and classify every gap/restriction.
3. Implement the shared shell, theme tokens, navigation and status bar.
4. Implement Dashboard layout and supported data bindings.
5. Implement Data Explorer layout and supported query interactions.
6. Implement saved-query/history screens using existing behavior.
7. Add permitted record-detail panels and summary visualizations.
8. Add explicit unsupported/unavailable states for withheld operations.
9. Verify the UI-boundary proof and prohibited-path checks.
10. Run focused tests, capture comparison screenshots and document visual deviations.
11. Publish implementation and evidence additively on the authorized session branch.
12. Independently verify the remote commit and tree.

Do not reopen already-completed investigations unless new evidence or a concrete contradiction makes it necessary. Reuse existing results and investigate only unknowns or changes.

---

## 13. Design-to-contract mapping template

Before implementing each component, maintain a mapping with at least these fields:

| Field | Meaning |
|---|---|
| Screen/component | Visible UI component |
| Reference | Dashboard or Data Explorer screenshot |
| Contract/operation | Authoritative contract and serving operation |
| Data source | Authorized serving response or presentation-only state |
| Disposition | Supported / presentation-only / capability gap / prohibited |
| Interaction | What the user can do |
| Failure behavior | Empty/invalid/stale/corrupt/unavailable/error behavior |
| Test evidence | Focused test or manual verification |
| Notes | Any visual deviation or contract limitation |

Every visible interactive component must have a disposition. A capability gap must not be silently converted into a new endpoint or storage read.

---

## 14. Delivery and change control

- Keep this file as a **non-authoritative design reference**.
- Do not edit governing contracts as part of creating or applying this specification.
- Do not treat adding this file to Git as implementation authorization.
- Use an additive commit on the already-authorized session branch.
- Preserve existing work and unrelated changes.
- Use fast-forward publication and independently verify the remote branch, commit, parent, changed path, blob and resulting tree.
- Do not promote to `main` or run Windows real-M2 qualification under this specification.
- If the implementation cannot satisfy a visual requirement without violating the authoritative contract, preserve the contract and record the specific deviation.


---

## 16. Consolidated component inventory and interaction contract

This section adds component-level precision to the screenshot-derived layout. It does not supersede the authoritative serving contract.

### 16.1 Dashboard component inventory

| Component | Reference behavior | Data/authority requirement | Required presentation states |
|---|---|---|---|
| Run summary | Run ID, run date/time, engine/corpus label, archive count | Use actual authorized run metadata | Available, unavailable, failed lookup |
| Processing action | Prominent primary action in the mockup | Do not expose unless processing-trigger authority exists | Omitted or visibly unavailable when unauthorized |
| Verify action | Secondary action beside processing | Do not expose unless the verification operation is authorized | Omitted or visibly unavailable when unauthorized |
| KPI cards | Five aligned cards: archives, rows, identity, calendars, errors | Bind each value and status to an authorized result | Loading, value, unavailable, error |
| Rows-by-year chart | Blue bars; year axis; row-count axis; muted gridlines | Use a verified aggregate or authorized response; do not derive from inaccessible storage | Populated, empty, unavailable, error |
| Segment doughnut | Doughnut, total in centre, legend with count and percentage | Counts and denominator must refer to the same population | Populated, empty, unavailable, inconsistent-data error |
| Coverage summary | Compact label/value list | Dates and counts must come from trusted serving metadata | Populated, partial, unavailable |
| Archive search | Search archive/symbol/date/segment terms as supported | Must filter through an authorized serving capability | Idle, searching, results, no results, error |
| Segment/year filters | Compact dropdowns | Options and semantics must be supported | Default, selected, empty, unavailable |
| Archive grid | Dense rows and seven reference columns | Values come from serving results; sorting must be real | Loading, populated, empty, error |
| Archive inspector | Selection-dependent metadata and related authorized navigation | Never infer missing fields; no unauthorized path/raw-byte access | No selection, selected, partial, unavailable |
| Log console | Scrollable monospace lines | Real authorized log source only | Loading, populated, empty, unavailable |
| Status bar | Engine/run/count/environment summary | Each value must be sourced; do not invent resource telemetry | Ready, busy, degraded, unavailable, error |

### 16.2 Data Explorer control inventory

| Control | Visual/interaction requirement | Contract constraint |
|---|---|---|
| Dataset selector | Compact select in header | Show only if more than one authorized dataset is available |
| Query Builder tab | Active blue tab in the reference state | Use the established query contract |
| Advanced Query tab | Same tab treatment as other modes | Must not create an alternate or more powerful query path without authority |
| Saved Queries tab | Opens saved-query management | Reuse D38 behavior |
| Query History tab | Opens actual query-history entries | Reuse D39 behavior |
| From/To dates | Paired date inputs with calendar affordance | Validate without silently rewriting requested dates |
| Instrument type | Select control (reference shows Symbol) | Only supported selectors/operators |
| Instrument value | Searchable text/value input | Do not invent search semantics |
| Segment | Select control | Values must be contract-supported |
| Series/market type | Select control | Values must be contract-supported |
| Trading status | Select control | Values must be contract-supported |
| Exchange segment | Select control | Values must be contract-supported |
| Optional-filter field | Select supported field | No arbitrary backend field access |
| Optional-filter operator | Operator select | Only operators supported for the chosen field |
| Optional-filter value | Type-appropriate input | Validate using established semantics |
| Add Filter | Adds a new valid filter row | Only if filter composition is supported |
| Remove Filter | Removes the selected optional filter row | Must not silently alter other filters |
| Quick-filter pills | Compact grouped buttons | Each preset must map deterministically to supported query semantics |
| Run Query | Primary blue button | Invokes only the authorized serving operation |
| Reset | Secondary button | Consistent reset behavior; no hidden data mutation |
| Save Query | Secondary button | Uses D38; no duplicate persistence logic |
| Export | Compact dropdown | Expose only if an authorized export operation exists |
| Columns | Compact dropdown | Only if column selection is implemented and supported |
| Rows per page | Compact select | Must match actual pagination behavior |
| Pagination | Current range plus previous/next | Do not imply a total if the response does not provide one |
| Results grid | Dense, selected row blue | Preserve real response ordering and truthful field values |
| Record inspector | Right-side pane updates with selected record | Data obtained only through authorized serving |
| Previous/Next record | Compact navigation in inspector | Navigate only within the permitted result set/operation |
| Chart selector | Selects a supported value series | Do not add a broad retrieval path solely for charting |
| Saved-query shortcuts | Compact sidebar list | Real saved entries only; D38 semantics |
| Query-history entries | Actual recorded entries | D39 semantics; do not manufacture history |

### 16.3 Reference query-result column order

Where the contract supplies these fields, preserve the screenshot's column order:

1. `#`
2. `Trade Date`
3. `Symbol`
4. `ISIN`
5. `Series`
6. `Segment`
7. `Open`
8. `High`
9. `Low`
10. `Close`
11. `Volume`
12. `Turnover (₹)`
13. `Status`

Numeric columns should be right-aligned and use consistent formatting. Use locale-appropriate grouping only where it does not obscure the underlying value. A formatted display value must not replace or mutate the canonical value.

### 16.4 Record-inspector grouping

Where authorized fields exist, group the inspector as follows:

**Instrument**
- Symbol
- ISIN
- Series
- Company ID
- Company Name

**Trading Details**
- Trade Date
- Segment
- Open, High, Low, Close
- Volume
- Turnover
- Trading Status

**Data Quality**
- Identity Status
- Record Status
- Association Status

**Provenance**
- Source Archive
- Source Row
- Archive Path
- Hash

This is a presentation grouping only. The field list is not permission to expose the fields. In particular, raw source content, raw records, archive bytes, paths or hashes must be omitted or restricted where the governing contract withholds them. If a field is not permitted, do not display a fake or placeholder value that resembles real provenance.

### 16.5 Saved-query shortcut area

The reference shows a `+ New Query` action and named shortcuts, including:
- `TCS 2020 (EQ)`
- `TCS 10-Year History`
- `All EQ 2020`
- `Identity Uncertain`
- `Missing Trading Dates`
- `Reconciliation Exceptions`
- `Corporate Action Candidates`

These are illustrative names from the mockup, not guaranteed saved records. Display actual saved queries returned by the established D38 capability. Do not seed these examples as live saved queries unless the user explicitly requests demo fixtures and they are kept separate from real application state.

### 16.6 Density, row states and micro-interactions

- Use compact financial-data density: approximately 28–32 px rows at the target desktop viewport, subject to legibility.
- Row hover uses a restrained background tint (starting reference: `#1E293B`); selected rows use the stronger accent-blue treatment.
- Hover, selected and keyboard-focus states must remain visually distinct.
- Filter removal controls should be small, aligned consistently, and have accessible labels.
- Icons should use the existing project icon system where available; do not substitute emoji for production icons or add a heavy icon dependency for a handful of symbols.
- Numeric columns should use tabular numerals where available.
- Long values may be visually truncated but must never be silently altered in the underlying data.
- Keep the application visually dense without clipping labels, controls, focus rings or status text.

---

## 17. Canonical token use and visual tuning protocol

The palette in §3 is the single canonical starting palette for implementation. Earlier or external palette proposals are not parallel themes. The supplied screenshots remain the final visual reference.

### 17.1 Token discipline

- Define each token once in the application's theme.
- Use semantic tokens rather than scattering literal hex values through components.
- If screenshot comparison demonstrates that a token needs adjustment, update the token centrally.
- Do not introduce one-off colors for individual screens unless a genuine semantic distinction requires them.
- Use the hover color `#1E293B` as a starting point for table-row hover, then compare against the reference.
- Preserve the semantic mapping of success, warning, error, unavailable, selected and focus states.

### 17.2 Screenshot comparison protocol

For each iteration:
1. Render Dashboard at 1536 × 1024.
2. Render Data Explorer at 1536 × 1024.
3. Capture both screens using the same viewport and comparable scale as the supplied references.
4. Compare the title bar, sidebar width, page heading, card geometry, panel gaps, table density, inspector width, chart proportions, bottom status bar, typography and colors.
5. Record material deviations and their causes.
6. Correct layout/token issues centrally before making local exceptions.
7. Repeat until the remaining differences are explained by real data availability, authority constraints, host-environment limits or documented design trade-offs.

Do not claim pixel-perfect parity unless actual screenshots have been captured and compared. Do not distort content or fabricate data merely to make the image resemble the reference.

---


---

## 15. Explicit limitation of this specification

This document is a detailed interpretation of the two supplied screenshots and the governance constraints described in the accompanying task context. The color values, font sizes, spacing and geometry are reasoned starting points because the screenshots are raster references rather than original design-source files. They must be tuned through rendered screenshot comparison.

The document does not independently verify the current repository, serving implementation, operation schemas, or remote publication state. Arena must verify component-to-contract mappings against the authoritative repository before implementation.

**End of non-authoritative UI specification.**
