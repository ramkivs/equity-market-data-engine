# D36 — Q6 calendar queries (serving slice)

**Status:** implementation record (Q6 of the D16-10 query categories; follows D35/Q5)
**Authority:** D23 §8/§17 (Q1–Q10 read-only serving/query layer over the qualified M2
baseline); D16-10 Q6; D22 §6 Q6 ("READY BY EXISTING CONTRACT"); D23 §8 item 1 (calendar
MAY be exposed, with `label_status`, the three unexplained dates displayed as
unexplained — never filled in). D24 §18 remaining-authorized-work item (b) (Q4–Q10).
**Publication scope:** session branch only. No main promotion.

---

## 1. Contract investigation (authoritative records only)

### 1.1 The Q6 lines (verbatim)

D16-10 (POST_I5 authority decision, Q-category list):

> **Q6** calendar query (trading days from file-presence; sourced holiday labels; the three
> unexplained dates shown as `unexplained-by-obtained-circulars`; legacy era `not-retrieved`).

D22 §6: Q6 = **READY BY EXISTING CONTRACT**, contract basis: `w2/calendar.jsonl` +
`metrics.calendar_totals`; `label_status`; the three unexplained dates displayed as
`unexplained-by-obtained-circulars`; legacy era `not-retrieved`.

D23 §8 item 1 (exposure boundary): the calendar MAY be exposed "with `label_status`;
the three unexplained dates displayed as unexplained — never filled in".

### 1.2 The governed calendar record (D05 §3.4, verified against engine emission)

`w2/calendar.jsonl` is a class-(2) W2 derived output (runner-written;
`tools/i4_runner/i4_runner.py::_write_w2`): **one `CalendarDay` document per line, in
ascending `trade_date` order** (the engine derives the weekday span between the first and
last corpus file date, `derive_calendar`).

`CalendarDay` (D05 §3.4; `nse_engine.calendar.CalendarDay.to_dict()`) — 12 keys:

| key | semantics |
|---|---|
| `trade_date` | ISO date (the corpus file-date span, weekday-only — the corpus has zero weekend files, D03). |
| `file_present` | boolean — **the trading-session signal** (D05 §3.4: the annual circular is a label only and MUST NOT be used to predict file presence). |
| `weekday` | the day's weekday name (Monday…Friday; derived from the date). |
| `missing_weekday` | true iff the weekday has no file. |
| `official_holiday_label` | nullable; populated **only** where a sourced circular names the date (registry §11) or where the engine marks a circular-holiday-with-file-present divergence (label = the date). |
| `label_status` | one of exactly four: `official-holiday`, `unexplained-by-obtained-circulars`, `not-retrieved`, `not-applicable`. |
| `label_circular` | nullable; the sourcing circular reference (only for `official-holiday`). |
| `label_registry_id` | nullable; the circular-registry id (only for `official-holiday`). |
| `formats_present` | sorted list of format roots with a file on the date (empty for missing days). |
| `member_names` | sorted list of member file names on the date (empty for missing days). |
| `trad_dt_eq_biz_dt` | UDiFF days: true (corpus-proven); legacy days: null (N/A — never defaulted). |
| `notes` | governance annotation strings as published (presence rule; missing-weekday rule; divergence note; unresolved-dependency note; trad-dt note) — served as published, never reinterpreted. |

**Label-state semantics (governed, engine-enforced):**

* `not-applicable` — a present day with no circular holiday (the common case). Present
  only on `file_present` days.
* `official-holiday` — a missing weekday named by a retrieved circular (sourced:
  `official_holiday_label` = the circular's name or "official holiday (circular)",
  `label_circular`/`label_registry_id` populated), **or** a present day that a circular
  names as a holiday (both-direction divergence — e.g. the documented 2025-10-21 Muhurat
  special session: file present WITH a normal-scale file; `official_holiday_label` = the
  date, the divergence note stored, never reconciled away).
* `unexplained-by-obtained-circulars` — a missing weekday inside the labelled scope that
  the obtained circulars do NOT explain: `official_holiday_label` stays null, the cause is
  never assigned, the dependency (D07-OPEN-8) is carried as unresolved. Documented M2
  instances: 2024-11-20, 2025-10-20, 2026-01-15 (exactly three).
* `not-retrieved` — a missing weekday before the labelling scope (legacy era, 2016–2023):
  cause NOT retrieved and MUST NOT be invented [NON-ASSUMPTION].

Labels apply to missing weekdays only (a governed label for a file-present date is a
contradiction the engine rejects); `label_circular`/`label_registry_id` are populated only
for `official-holiday` days.

**Calendar arithmetic (governed, D03):** the span's weekdays = present days + missing
weekdays; files = present days (a day may carry several members — duplicate dates count
once per date, the extra members visible in `member_names`).

**Documented M2 facts (used only by the gated real-baseline leg):** 2,462 files +
147 missing weekdays = 2,609 span weekdays; the three unresolved dates above; the
2025-10-21 divergence; legacy-era present days carry `trad_dt_eq_biz_dt: null`.

### 1.3 Calendar metrics (governance status)

`w2/metrics.json` (class-(2), runner-written): `{row_metrics, calendar_totals,
label_status_counts, d01_metric_fold}`.

* `calendar_totals` = `{days, files, first_date, last_date, missing_weekdays,
  present_days, span_weekdays, unresolved_dates[]}` — **published, runner-derived facts**
  over the calendar (D22 §6 lists `metrics.calendar_totals` as part of the Q6 contract
  basis). Served as published — never replaced by a re-computation.
* `label_status_counts` = the label-status census, **published**.
* Q6 **cross-checks** the published totals against the served records (the Q8
  reconciliation cross-check precedent): a material contradiction is a package
  inconsistency and fails closed. The published values are what is served; the
  check validates, it does not recompute-and-replace.

### 1.4 File-set coupling (runner-emitted pair)

The runner writes `w2/calendar.jsonl` and `w2/metrics.json` together; an empty
`calendar.jsonl` is not a state the engine can produce (`derive_calendar` requires at
least one inventory file). Therefore:

* **both absent** → a legitimate class-(2)-absent state (served as explicitly absent);
* **calendar present, metrics absent (or missing its calendar blocks)** → package
  inconsistency → fail closed;
* **metrics present, calendar absent** → package inconsistency → fail closed;
* **calendar present but empty** → not producible → fail closed.

### 1.5 Ordering and duplicates

File order is ascending `trade_date` (the engine's derivation order); a served file that is
not strictly ascending (duplicate or reordered dates) is corruption → fail closed. The
query never re-sorts.

### 1.6 Conflicts / unresolved issues

None. D05 §3.4, D16-10, D22 §6, D23 and the engine agree. One documented boundary:
D16-10 Q6 fixes the *display* semantics of the label states (show unexplained as
unexplained; never fill in; legacy as not-retrieved) — it does not name a
`label_status` filter; the smallest slice therefore serves the full calendar with an
optional date range and represents the states exactly as published (no label filter is
invented; deferred, §2.9).

---

## 2. Proposed Q6 slice (recorded BEFORE code)

**Smallest coherent slice:** one read-only query over `w2/calendar.jsonl` (+ the
`w2/metrics.json` calendar blocks for the cross-check and the summary), zero new state.

### 2.1 Selectors and parameters

`query_calendar(baseline, index, date_from=None, date_to=None)`:

| mode | request | semantics |
|---|---|---|
| full | no bounds | every calendar day, as published, file order (ascending `trade_date`). |
| range | `date_from` **and** `date_to` (both, inclusive, ISO YYYY-MM-DD) | the days with `date_from <= trade_date <= date_to`, exact as-published string comparison (Q2 inclusive-bound semantics; `date_from > date_to` is an empty range → empty result, not an error). |

Validation (fail closed, before anything is served): each supplied bound must be a valid
ISO calendar date string; exactly one bound supplied → `QueryError("query-input")`.
`index` is accepted for boundary consistency (as in Q5); Q5/Q6 alike, the class-(2) file
set is fixed and the index format is unchanged (serving-index/1.2).

### 2.2 Response schema

API: `Tuple[dict, ...]`. Each element = the **published 12-key `CalendarDay` document plus
a `serving` envelope** `{query: "Q6-calendar", source_file: "w2/calendar.jsonl",
source_line_number, date_from, date_to}` (Q3/Q5 precedent: the record exactly as stored).

CLI envelope: `{"query": "Q6-calendar", "date_from": <str|null>, "date_to": <str|null>,
"calendar_present": <bool>, "record_count": <int>, "records": [...]}`. The published
`calendar_totals`/`label_status_counts` are **not** duplicated into the response: they are
validated against the records and remain consumable as published files (no re-shaping, no
second source of truth).

### 2.3 Served semantics for the label states (D16-10 display contract)

* `official_holiday_label: null` served as `null` for `unexplained-by-obtained-circulars`
  and `not-retrieved` — the cause is never filled in, never defaulted, never inferred from
  the label status or the date;
* `label_status` served exactly as published (all four states distinct);
* the divergence day (present + `official-holiday`) served as published (file_present true,
  the divergence note carried in `notes`);
* `trad_dt_eq_biz_dt: null` (legacy/N-A) served as `null`, never defaulted to false;
* `notes` served as published text.

### 2.4 Absent / unknown / missing-data behavior

* **both W2 calendar files absent** → legitimate: empty result,
  `calendar_present: false`; never an error, never fabricated;
* **range with no matching days** → empty result (valid);
* null fields (labels, registry id, trad-dt) served as `null`; blank strings are never a
  published value in these fields (the engine emits null or non-empty strings) — a blank
  is corruption (§2.5);
* unknown dates simply do not appear (the calendar is the span; there is no "unknown
  date" request — the range bounds are filters, not lookups).

### 2.5 Fail-closed behavior

A **present** `w2/calendar.jsonl` fails closed with `QueryError("calendar-scan")`
(line-numbered detail) including: unparseable JSON line; non-object line; a non-contract
12-key set; non-ISO `trade_date`; a weekend date (the corpus has zero weekend files, D03);
`weekday` inconsistent with the date; `missing_weekday` != `!file_present`;
`label_status` outside the four governed states; `official-holiday` with a null
`official_holiday_label`; `unexplained-by-obtained-circulars` or `not-retrieved` with a
non-null `official_holiday_label`; `not-applicable` on a missing day or with a populated
`label_circular`/`label_registry_id`; a populated `label_circular`/`label_registry_id`
outside `official-holiday`; blank (empty-string) label/circular/registry values (the
engine emits null or non-empty); non-list or non-string-list `formats_present` /
`member_names` / `notes`; `file_present`/`missing_weekday` not boolean;
`trad_dt_eq_biz_dt` outside {true, null} or true on a missing day; duplicate or
non-ascending `trade_date`. Metrics failures use `QueryError("calendar-metrics")`:
metrics file absent while the calendar is present; a missing calendar while metrics is
present; an empty calendar file; `calendar_totals` disagreeing with the served records
(`days`, `span_weekdays`, `present_days`, `missing_weekdays`, `first_date`, `last_date`,
`unresolved_dates`, and the D03 files arithmetic: `files` == present days, or greater with
a multi-member day); `label_status_counts` disagreeing with the records. **No partial
output is ever produced** — the file is fully parsed and validated before a result is
returned; the CLI prints only the existing JSON error envelope and exits 2.

Pinned schema constants are literals in `serving/query.py` with the contract citation
(serving does not import `nse_engine`, D24 boundary).

### 2.6 Implementation boundaries (per the task)

* **A read-only:** streams the two class-(2) files; no mutation; no new store; no
  canonical write-path change; no class-(4) state.
* **B contract fidelity:** governed states only; no normalization/inference/aliasing;
  null stays null; no fabricated causes; published ordering preserved.
* **C deterministic canonical JSON:** CLI via the existing `_print_json`; API results are
  plain published dicts.
* **D fail-closed:** §2.5, existing `QueryError` envelope and exit codes (0 ok / 2
  usage-query failure / 3 baseline-index failure).
* **F no regression:** Q1–Q5, Q7–Q10, baseline/manifest/index verification, package
  immutability, index format (1.2) untouched.

### 2.7 CLI surface

`query` subcommand gains `--calendar` (the sixth mutually exclusive mode). With
`--calendar`, the existing `--from`/`--to` flags carry the (both-or-neither) inclusive
date range; without `--calendar` they remain Q2's. `--calendar` combined with any other
mode flag is a usage error (exit 2), as is a half-supplied range.

### 2.8 Fixture strategy (contract-supported only)

The base fixture package gains **no** calendar: an engine-derived calendar over the
fixture's actual file set would span 2016-01-04…2024-03-05 and its ~2,000 in-scope
missing weekdays would each require fabricated circular evidence (prohibited — D05 §3.4
"never invent"; the engine itself fails closed without governed labels). The absent state
is the base fixture's legitimate Q6 state (the qualified M2 package carries the real
calendar — exercised by the gated leg).

The present-state cases are exercised by **test variants** (copy the base package, add
`w2/calendar.jsonl` + `w2/metrics.json`, re-sign — the established D34/D35 variant
pattern). The variant calendars are fixture-declared miniatures in the exact 12-key
schema, self-describing (their own declared span and member names; fixture-prefixed
circular references `FIX-CIRC-*`/`FIX-REG-*`; the engine's own note strings where the
note is era-neutral), never an authoritative calendar fact:

* **Variant A (present era, 10 weekdays, 2024-02-26…2024-03-08):** one present day
  (2024-03-05 — the fixture's real UDiff member; declared a fixture circular holiday with
  file present — the divergence case, `trad_dt_eq_biz_dt: true`); nine missing days: two
  `official-holiday` (sourced, circular + registry), one
  `unexplained-by-obtained-circulars` (null label), six `not-retrieved` (no circulars
  obtained for those dates); consistent `calendar_totals` + `label_status_counts`.
* **Variant B (legacy era, 2016-01-04…2017-02-06):** the fixture's three real legacy
  member dates as present days (`trad_dt_eq_biz_dt: null` — legacy N/A; `formats_present:
  ["LEGACY"]`); every other weekday in the span missing and `not-retrieved` (before the
  labelling scope — exactly the engine's own rule; the engine's era-appropriate
  not-retrieved note); consistent totals.

### 2.9 Deferred Q6 scope (documented, not implemented)

* a `label_status` selector/filter (D16-10 fixes display semantics, not a filter —
  no filter is invented);
* a `file_present` selector (the full calendar already carries the per-day signal; the
  Dashboard tile derivation is presentation work, D16-12);
* the `w2/metrics.json` blocks outside the calendar (row_metrics, d01_metric_fold —
  other views' contracts);
* UI/transport rendering and saved-query persistence (separate authorization items).

### 2.10 Expected tests (task 19-item list mapping)

`tests/test_serving_calendar.py` (focused) + one `D24_M2_ROOT`-gated real-baseline leg in
`tests/test_serving_m2_integration.py`:

1. valid calendar lookup (full + range, variant A);
2. multiple records (A: 10 days; B: the legacy span);
3. date-boundary behavior (inclusive bounds; single-day range; `from > to` → empty;
   out-of-span bounds → empty);
4. sourced-label behavior (official-holiday with circular + registry + non-null label);
5. unexplained-state behavior (null label; status; carried in totals.unresolved_dates);
6. not-retrieved behavior (A: 6 days; B: the scale case, legacy present days trad null);
7. unexplained vs not-retrieved distinction (both served distinct, never conflated);
8. absent calendar files (base fixture: API + CLI, `calendar_present: false`);
9. present-but-malformed calendar (duplicate date; non-ascending; wrong key set; weekend
   date; weekday mismatch; missing-weekday contradiction; foreign status;
   unexplained-with-label; not-applicable-missing; blank label; empty file; metrics
   absent; metrics-without-calendar);
10. missing/null/blank/unknown values (null label/registry/trad-dt served as null; blank
    → fail closed; absent file → explicit absent);
11. duplicates and ordering (duplicate/non-ascending fail closed; served order = file
    order = ascending);
12. metrics behavior and consistency (cross-check passes for A/B; totals mismatch →
    fail; label_status_counts mismatch → fail);
13. invalid selectors/parameters (one bound; non-ISO; non-string);
14. fail-closed without partial output (failure mid-file serves nothing; stateless);
15. canonical-JSON CLI behavior (envelope; sorted keys; byte-repeat);
16. deterministic repeated queries;
17. package byte identity after success;
18. package byte identity after failure;
19. Q1–Q10 regression (focused regression test + full suite).

Gated leg (real M2, Windows-held; skipped ≠ passed): serving-behavior assertions over the
documented M2 facts only — calendar present; ascending order; the three documented
unresolved dates (2024-11-20, 2025-10-20, 2026-01-15) served with null labels; 147
missing weekdays; 2,462 present days; the 2025-10-21 divergence day present +
official-holiday; a legacy present day with `trad_dt_eq_biz_dt: null`; single-day range
2024-11-20; determinism. No corpus fact is assumed that is not documented; no
re-qualification.

---

## 3. Results

### 3.1 What was implemented (matches §2; no drift)

* `src/serving/query.py` — `CALENDAR_QUERY_ID` / `CALENDAR_FILE` /
  `METRICS_FILE`; pinned schema constants (12 day keys; the four governed
  label states; the five weekday names; the 8-key `calendar_totals` set);
  `parse_calendar` (absent → None legitimate, with the pair-consistency
  check that `w2/metrics.json` cannot exist without the calendar;
  present-malformed → fail closed, line-numbered; weekend date, weekday/date
  mismatch, missing-weekday contradiction, foreign label state,
  label-populated unexplained/not-retrieved days, blank label values, empty
  file, and duplicate/non-ascending `trade_date` all rejected);
  `_load_calendar_metrics` + `_cross_check_calendar` (published
  `calendar_totals`/`label_status_counts` validated against the served
  records — D03 arithmetic, span bounds, unresolved-date list, label census;
  the published values are served, never recomputed-and-replaced);
  `query_calendar` (full + inclusive range modes; `date_from > date_to` →
  empty; file order preserved; documents/metrics sentinel parameters for a
  single CLI pass).
* `src/serving/cli.py` — `--calendar` (sixth mutually exclusive mode); with
  `--calendar`, `--from`/`--to` carry the both-or-neither inclusive Q6 range;
  without, they remain Q2's; half-range is a usage error (exit 2); envelope
  `{query, date_from, date_to, calendar_present, record_count, records}`;
  existing error envelope and exit codes unchanged. (A mid-implementation
  regression of the Q5 mode detection — the `q5` binding dropped from the
  mutual-exclusion sum — was caught by the Q6+Q5 exclusivity test and the
  focused Q5 suite before publication and restored.)
* `src/serving/__init__.py` — exports `CALENDAR_QUERY_ID`, `CALENDAR_FILE`,
  `parse_calendar`, `query_calendar`; module boundary statement extended with
  the Q6 line.
* `tests/test_serving_calendar.py` — 44 focused tests (task 19-item list,
  §2.10) over the base fixture (absent state) and the two fixture-declared
  variant calendars (A: present era, 10 days, all four label states + the
  divergence; B: legacy era, 2016-01-04…2017-02-06, 3 present legacy days
  with `trad_dt_eq_biz_dt: null` + the not-retrieved scale case).
* `tests/test_serving_m2_integration.py` — one `D24_M2_ROOT`-gated
  real-baseline leg (`test_q6_calendar_over_real_baseline`): documented M2
  facts only (2,462 present / 147 missing / 2,609 span; the three unresolved
  dates with null labels; the 2025-10-21 divergence; legacy present days
  trad-null; single-day range; determinism); skipped ≠ passed.

The base fixture package is **unchanged** (no calendar added — §2.8: an
engine-derived fixture calendar is infeasible without fabricated circular
evidence; the absent state is its legitimate Q6 state).

### 3.2 Test results (actual)

* Focused: `python3 -m unittest tests.test_serving_calendar` — **Ran 44 OK**
  (0.7 s).
* Focused regression (after the Q5 mode-detection fix):
  `tests.test_serving_associations` **Ran 35 OK**; `tests.test_serving_filters`
  **Ran 16 OK**.
* CLI smoke (real CLI over a variant package): full calendar (10 records,
  `calendar_present: true`); range 2024-03-04…06 (3 records with the three
  distinct label states); half-range → exit 2; `--calendar` + Q3 positional →
  exit 2; Q5 identity lookup over the same package still succeeds.
* Full suite: `PYTHONPATH=src python3 -m unittest discover -s tests -t .` —
  **Ran 711 OK (skipped=12)**. Prior baseline 666 (skipped=11); +44 focused +
  1 gated leg. All 12 skips are the D24_M2_ROOT-gated real-baseline legs
  (11 prior + the new Q6 leg) — PENDING baseline provisioning, never passed.
* Package byte identity after success and after failure: asserted
  (`test_package_byte_identity_after_success_and_failure`).
* Index unchanged: rebuild byte-identical; neither `w2/calendar.jsonl` nor
  `w2/metrics.json` is an index entry (`test_index_is_unchanged_by_q6`).

### 3.3 Changed files (one bounded commit)

| file | role |
|---|---|
| `src/serving/query.py` | Q6 query + pinned schema + fail-closed parse + metrics cross-check |
| `src/serving/cli.py` | Q6 CLI mode (`--calendar` + range; six-way mutual exclusion) |
| `src/serving/__init__.py` | exports + boundary statement |
| `tests/test_serving_calendar.py` | 44 focused Q6 tests (new) |
| `tests/test_serving_m2_integration.py` | 1 gated real-baseline leg |
| `docs/implementation/D36_Q6_CALENDAR_QUERIES.md` | this record (new) |

### 3.4 Boundaries confirmed

* Read-only over the baseline; no new store, no class-(4) state, no index
  format change (serving-index/1.2 untouched); no canonical write-path
  change; package byte-identical after success and failure.
* No fabricated causes/labels/holidays anywhere: base fixture gains no
  calendar; variant calendars are fixture-declared miniatures with
  fixture-prefixed circular references; the gated leg asserts only
  documented M2 facts.
* `label_status` states served exactly as published and kept distinct;
  `official_holiday_label: null` preserved for unexplained/not-retrieved;
  `trad_dt_eq_biz_dt: null` never defaulted.
* Q1–Q5, Q7–Q10 and all verification paths: full-suite green.
* No saved-query/history, no UI/transport, no product E2E, no main
  promotion. STOP after this task.
