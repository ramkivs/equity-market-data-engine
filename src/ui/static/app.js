/* I4 first-release UI — frontend (vanilla JS; no dependencies; no clock,
 * no randomness). All data arrives from the local serving adapter, which is
 * the single path over the authorized serving operations (Q1–Q10 via the
 * shared execute_query_definition dispatch; D38 saved queries; D39 query
 * history). Nothing here is a query path of its own: the UI only assembles
 * (mode, params) pairs the serving contract already defines.
 *
 * Display-level derivations below mirror src/ui/derive.py 1:1 (the same
 * documented definitions; see the TASK62 implementation record). */
"use strict";

/* ============================ constants ============================ */

const MODE = {
  Q1: "Q1-dataset", Q2: "Q2-date-range", Q3: "Q3-instrument", Q4: "Q4-filter",
  Q5: "Q5-association", Q6: "Q6-calendar", Q7: "Q7-record-detail",
  Q8: "Q8-data-quality", Q9: "Q9-archive-inventory", Q10: "Q10-qualification",
};
const Q4_FIELDS = ["series", "segment", "source", "instrument_type", "symbol"];
const QUICK_FILTERS = ["EQ (all)", "CM segment", "FO segment", "Debt", "Currency", "Latest 1Y", "Latest 3Y", "Latest 5Y", "Latest 10Y", "Reliable Only"];
const SEGMENT_COLORS = ["#3B82F6", "#FF813D", "#F4C83D", "#FF716D", "#20D18A", "#8FA7BD"];
const COMPACT_NUM = (n) => {
  if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
};

/* ============================ helpers ============================ */

function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Deterministic grouping for integers (locale-independent). */
function fmtInt(n) {
  if (typeof n !== "number" || !isFinite(n)) return "—";
  const neg = n < 0 ? "-" : "";
  const s = String(Math.trunc(Math.abs(n)));
  const grouped = s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return neg + grouped;
}

/* Trim float to a stable decimal text (derived aggregates only). */
function fmtNum(v) {
  if (v === null || v === undefined) return "unavailable";
  const rounded = Math.round(v * 1e4) / 1e4;
  return String(rounded);
}

function fmtBytes(n) {
  if (typeof n !== "number" || !isFinite(n)) return "—";
  if (n >= 1073741824) return (n / 1073741824).toFixed(2) + " GB";
  if (n >= 1048576) return (n / 1048576).toFixed(2) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}

/* Strict as-published numeric text form (mirrors derive.py). */
const NUMBER_RE = /^[+-]?(0|[1-9]\d*)(\.\d+)?$/;
function toNumber(value) {
  return typeof value === "string" && NUMBER_RE.test(value) ? parseFloat(value) : null;
}
function isIsoDate(v) {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
}

/* Deterministic day-number from a civil date (integer math; no clock, no TZ). */
function daysFromCivil(y, m, d) {
  let yy = y - (m <= 2 ? 1 : 0);
  const era = Math.floor(yy / 400);
  const yoe = yy - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 1721425;
}
function dateToDay(iso) {
  return daysFromCivil(parseInt(iso.slice(0, 4), 10), parseInt(iso.slice(5, 7), 10), parseInt(iso.slice(8, 10), 10));
}

function sv(row, field) {
  const values = row && row.source_values;
  return values && typeof values === "object" ? values[field] : null;
}
function businessDate(row) {
  return row && isIsoDate(row.business_date) ? row.business_date : null;
}

/* ============================ derivations (mirror of src/ui/derive.py) ============================ */

function periodSummary(rows) {
  const out = {
    records: rows.length, date_min: null, date_max: null, single_year: false, year: null,
    open_first: null, close_last: null, high: null, low: null,
    volume_total: null, volume_count: 0, turnover_total: null, turnover_count: 0,
  };
  const years = new Set();
  for (const row of rows) {
    const d = businessDate(row);
    if (d) {
      if (out.date_min === null || d < out.date_min) out.date_min = d;
      if (out.date_max === null || d > out.date_max) out.date_max = d;
      years.add(parseInt(d.slice(0, 4), 10));
    }
  }
  if (years.size === 1) { out.single_year = true; out.year = [...years][0]; }
  for (const row of rows) {
    const open = toNumber(sv(row, "price_open"));
    if (open !== null && out.open_first === null) out.open_first = open;
    const close = toNumber(sv(row, "price_close"));
    if (close !== null) out.close_last = close;
    const high = toNumber(sv(row, "price_high"));
    if (high !== null && (out.high === null || high > out.high)) out.high = high;
    const low = toNumber(sv(row, "price_low"));
    if (low !== null && (out.low === null || low < out.low)) out.low = low;
    const vol = toNumber(sv(row, "traded_quantity"));
    if (vol !== null) { out.volume_total = (out.volume_total || 0) + vol; out.volume_count += 1; }
    const turn = toNumber(sv(row, "traded_value"));
    if (turn !== null) { out.turnover_total = (out.turnover_total || 0) + turn; out.turnover_count += 1; }
  }
  return out;
}

function rowsByYear(partitions) {
  const byYear = {};
  for (const p of partitions || []) {
    if (!p || typeof p.year !== "string" || !/^\d{4}$/.test(p.year) || typeof p.row_count !== "number") continue;
    byYear[p.year] = (byYear[p.year] || 0) + p.row_count;
  }
  return Object.keys(byYear).sort().map((year) => ({ year: parseInt(year, 10), row_count: byYear[year] }));
}

function segmentCounts(archives) {
  const bySeg = Object.create(null);
  for (const rec of archives || []) {
    const d01 = rec && rec.d01;
    if (!d01 || typeof d01.series_counts !== "object" || d01.series_counts === null) continue;
    for (const [segment, count] of Object.entries(d01.series_counts)) {
      if (typeof segment !== "string" || typeof count !== "number") continue;
      const entry = (bySeg[segment] = bySeg[segment] || { segment, archive_count: 0, row_count: 0 });
      entry.archive_count += 1;
      entry.row_count += count;
    }
  }
  return Object.keys(bySeg).sort().map((s) => bySeg[s]);
}

function coverageSummary(partitions, calendarDays, archives, q1Summary) {
  const dates = [];
  for (const day of calendarDays || []) {
    if (day && isIsoDate(day.trade_date)) dates.push(day.trade_date);
  }
  dates.sort();
  const segments = new Set();
  for (const rec of archives || []) {
    const d01 = rec && rec.d01;
    if (d01 && typeof d01.series_counts === "object" && d01.series_counts !== null) {
      for (const key of Object.keys(d01.series_counts)) segments.add(key);
    }
  }
  const years = new Set();
  for (const p of partitions || []) {
    if (p && typeof p.year === "string" && /^\d{4}$/.test(p.year)) years.add(parseInt(p.year, 10));
  }
  return {
    start_date: dates.length ? dates[0] : null,
    end_date: dates.length ? dates[dates.length - 1] : null,
    trading_days: dates.length ? dates.length : null,
    total_archives: archives ? archives.length : 0,
    total_rows: q1Summary && q1Summary.row_count !== undefined ? q1Summary.row_count : null,
    instruments: q1Summary && q1Summary.instrument_pairs !== undefined ? q1Summary.instrument_pairs : null,
    exchange_segments: segments.size ? [...segments].sort() : null,
    partition_years: [...years].sort((a, b) => a - b),
  };
}

function flagStatus(flags) {
  if (!Array.isArray(flags) || flags.length === 0) return { state: "clean", text: "no flags" };
  const names = [...new Set(flags.filter((f) => f && typeof f.name === "string").map((f) => f.name))].sort();
  return { state: "flagged", text: names.length ? names.join(", ") : "unknown flags" };
}

function pricePoints(rows, field) {
  const points = [];
  let omitted = 0;
  for (const row of rows) {
    const date = businessDate(row);
    const value = toNumber(sv(row, field));
    if (date === null || value === null) { omitted += 1; continue; }
    points.push({ date, value });
  }
  return { points, omitted, field };
}

function quickFilterParams(name, maxYear) {
  if (name === "EQ (all)") return { mode: MODE.Q4, params: { filters: { series: "EQ" } } };
  if (name === "CM segment") return { mode: MODE.Q4, params: { filters: { segment: "CM" } } };
  if (name.startsWith("Latest ")) {
    const n = parseInt(name.slice("Latest ".length, -1), 10);
    if (![1, 3, 5, 10].includes(n) || maxYear === null || maxYear === undefined) return null;
    const start = maxYear - n + 1;
    if (start < 1000) return null;
    return { mode: MODE.Q2, params: { date_from: String(start).padStart(4, "0") + "-01-01", date_to: String(maxYear).padStart(4, "0") + "-12-31" } };
  }
  return null; /* Reliable Only and unknowns: unavailable */
}

/* ============================ API client ============================ */

const api = {
  async req(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined && body !== null) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    let doc = null;
    try { doc = await res.json(); } catch (e) { doc = null; }
    if (!res.ok || !doc || doc.result === undefined) {
      const err = new Error((doc && doc.detail) || ("HTTP " + res.status));
      err.check = doc && doc.check;
      err.status = res.status;
      throw err;
    }
    return doc;
  },
  query(mode, params) { return this.req("POST", "/api/query", { mode, params }); },
  status() { return this.req("GET", "/api/status"); },
  savedList() { return this.req("GET", "/api/saved"); },
  savedShow(id) { return this.req("GET", "/api/saved/" + encodeURIComponent(id)); },
  savedCreate(def) { return this.req("POST", "/api/saved", def); },
  savedUpdate(id, def) { return this.req("PUT", "/api/saved/" + encodeURIComponent(id), def); },
  savedDelete(id) { return this.req("DELETE", "/api/saved/" + encodeURIComponent(id)); },
  savedRun(id) { return this.req("POST", "/api/saved/" + encodeURIComponent(id) + "/run", {}); },
  historyList() { return this.req("GET", "/api/history"); },
  historyShow(seq) { return this.req("GET", "/api/history/" + encodeURIComponent(seq)); },
  historyDelete(seq) { return this.req("DELETE", "/api/history/" + encodeURIComponent(seq)); },
  historyRecord(def) { return this.req("POST", "/api/history", def); },
};

/* ============================ app state ============================ */

const S = {
  page: "dashboard",
  service: null,
  server: null,          /* /api/status document */
  dash: {
    loaded: false, loading: false, error: null,
    q1: null, q6: null, q8: null, q9: null, q10: null,
    q1Error: null, q6Error: null, q8Error: null, q9Error: null, q10Error: null,
    errors: [],          /* per-query failures: [{name, check, message}] */
    archiveSelection: -1,
    archiveSearch: "", archiveSegment: "", archiveYear: "",
    sortKey: "sequence", sortDir: 1,
  },
  expl: {
    tab: "builder",
    busy: false,
    builder: { mode: MODE.Q3, quick: null, q4: [] },
    results: { doc: null, rows: [], meta: null, page: 0, perPage: 25, selected: -1, banner: null },
    inspector: { loading: false, error: null, detail: null, related: null, relatedError: null },
    quality: { loaded: false, loading: false, error: null, doc: null },
    saved: { loaded: false, loading: false, error: null, entries: [], selected: null },
    history: { loaded: false, loading: false, error: null, entries: [], detail: null },
    q1Cache: null,        /* dataset summary used by "Latest N years" presets */
  },
};

const $ = (id) => document.getElementById(id);

/* ============================ charts (SVG) ============================ */

function svgEl(tag, attrs, inner) {
  const a = Object.entries(attrs).map(([k, v]) => k + '="' + esc(v) + '"').join(" ");
  return inner === undefined ? "<" + tag + " " + a + "/>" : "<" + tag + " " + a + ">" + inner + "</" + tag + ">";
}

function barChart(data) {
  const W = 460, H = 220, padL = 44, padB = 24, padT = 10, padR = 8;
  if (!data.length) return "";
  const max = Math.max(...data.map((d) => d.row_count)) || 1;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const bw = plotW / data.length;
  let out = "";
  for (let i = 0; i <= 4; i++) {
    const v = (max * i) / 4;
    const y = padT + plotH - (plotH * i) / 4;
    out += svgEl("line", { x1: padL, y1: y, x2: W - padR, y2: y, class: "grid-line" });
    out += svgEl("text", { x: padL - 5, y: y + 3, "text-anchor": "end", class: "axis-label" }, COMPACT_NUM(Math.round(v)));
  }
  data.forEach((d, i) => {
    const h = (d.row_count / max) * plotH;
    const x = padL + i * bw + Math.max(1, bw * 0.12);
    const w = Math.max(2, bw * 0.76);
    const y = padT + plotH - h;
    out += svgEl("rect", { x, y, width: w, height: Math.max(1, h), fill: "#3B82F6", rx: 1 });
    if (data.length <= 14 || i % 2 === 0) {
      out += svgEl("text", { x: padL + i * bw + bw / 2, y: H - 8, "text-anchor": "middle", class: "axis-label" }, String(d.year));
    }
  });
  return "<svg viewBox=\"0 0 " + W + " " + H + "\" width=\"100%\" role=\"img\" aria-label=\"Rows by year bar chart\">" + out + "</svg>";
}

function donutChart(entries) {
  const W = 200, H = 150, cx = 100, cy = 75, r = 52, r0 = 32;
  const total = entries.reduce((s, e) => s + e.row_count, 0);
  if (!total) return "";
  let angle = -Math.PI / 2;
  let out = "";
  entries.forEach((e, i) => {
    const frac = e.row_count / total;
    const a1 = angle + frac * 2 * Math.PI;
    const large = frac > 0.5 ? 1 : 0;
    const x0 = cx + r * Math.cos(angle), y0 = cy + r * Math.sin(angle);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const xi1 = cx + r0 * Math.cos(a1), yi1 = cy + r0 * Math.sin(a1);
    const xi0 = cx + r0 * Math.cos(angle), yi0 = cy + r0 * Math.sin(angle);
    out += svgEl("path", {
      d: "M " + x0.toFixed(2) + " " + y0.toFixed(2) + " A " + r + " " + r + " 0 " + large + " 1 " + x1.toFixed(2) + " " + y1.toFixed(2) +
         " L " + xi1.toFixed(2) + " " + yi1.toFixed(2) + " A " + r0 + " " + r0 + " 0 " + large + " 0 " + xi0.toFixed(2) + " " + yi0.toFixed(2) + " Z",
      fill: SEGMENT_COLORS[i % SEGMENT_COLORS.length],
    });
    angle = a1;
  });
  out += svgEl("text", { x: cx, y: cy - 2, "text-anchor": "middle", fill: "#F2F6FC", "font-size": 15, "font-weight": 650 }, COMPACT_NUM(total));
  out += svgEl("text", { x: cx, y: cy + 12, "text-anchor": "middle", class: "axis-label" }, "rows");
  return "<svg viewBox=\"0 0 " + W + " " + H + "\" width=\"100%\" role=\"img\" aria-label=\"Rows by published series code donut chart\">" + out + "</svg>";
}

function lineChart(points, volume) {
  const W = 560, H = 240, padL = 52, padB = 22, padT = 10, padR = 10;
  if (points.length < 2) {
    return "<div class=\"state-empty\">Insufficient numeric points to plot (" + points.length + "). Non-numeric as-published values are never plotted as zero.</div>";
  }
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const days = points.map((p) => dateToDay(p.date));
  const dmin = days[0], dmax = days[days.length - 1];
  const span = Math.max(1, dmax - dmin);
  const volH = volume ? 42 : 0;
  const priceH = plotH - volH - (volume ? 8 : 0);
  let vmin = Math.min(...points.map((p) => p.value));
  let vmax = Math.max(...points.map((p) => p.value));
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  const pad = (vmax - vmin) * 0.06;
  vmin -= pad; vmax += pad;
  const X = (d) => padL + ((d - dmin) / span) * plotW;
  const Y = (v) => padT + priceH - ((v - vmin) / (vmax - vmin)) * priceH;
  let out = "";
  for (let i = 0; i <= 4; i++) {
    const v = vmin + ((vmax - vmin) * i) / 4;
    const y = Y(v);
    out += svgEl("line", { x1: padL, y1: y, x2: W - padR, y2: y, class: "grid-line" });
    out += svgEl("text", { x: padL - 5, y: y + 3, "text-anchor": "end", class: "axis-label" }, COMPACT_NUM(Math.round(v)));
  }
  const first = points[0].date, last = points[points.length - 1].date;
  out += svgEl("text", { x: padL, y: H - 6, class: "axis-label" }, first);
  out += svgEl("text", { x: W - padR, y: H - 6, "text-anchor": "end", class: "axis-label" }, last);
  let dpath = "";
  points.forEach((p, i) => { dpath += (i === 0 ? "M " : " L ") + X(days[i]).toFixed(2) + " " + Y(p.value).toFixed(2); });
  out += svgEl("path", { d: dpath, fill: "none", stroke: "#3B82F6", "stroke-width": 1.5 });
  if (volume) {
    const vols = points.map((p) => toNumber(sv(p.row, "traded_quantity")));
    const vmaxv = Math.max(...vols.filter((v) => v !== null).map((v) => Math.abs(v))) || 1;
    const base = padT + plotH;
    points.forEach((p, i) => {
      const v = vols[i];
      if (v === null) return;
      const h = (Math.abs(v) / vmaxv) * (volH - 4);
      out += svgEl("rect", { x: X(days[i]).toFixed(2) - 0.75, y: base - h, width: 1.5, height: Math.max(0.5, h), fill: "#2A4B65" });
    });
  }
  return "<svg viewBox=\"0 0 " + W + " " + H + "\" width=\"100%\" role=\"img\" aria-label=\"Price line chart\">" + out + "</svg>";
}

/* ============================ shared render helpers ============================ */

function stateHtml(kind, text) {
  if (kind === "error") return "<div class=\"state-error\"><span class=\"check\">" + esc(text.check || "") + "</span> — " + esc(text.detail) + "</div>";
  if (kind === "unavailable") return "<div class=\"state-unavailable\">" + esc(text) + "</div>";
  if (kind === "empty") return "<div class=\"state-empty\">" + esc(text) + "</div>";
  return "<div class=\"state-loading\">" + esc(text) + "</div>";
}

function kvRow(k, v, cls) {
  const val = v === null || v === undefined ? '<span class="chip unavail">unavailable</span>' : esc(v);
  return "<div class=\"row\"><span class=\"k\">" + esc(k) + "</span><span class=\"v " + (cls || "") + "\">" + val + "</span></div>";
}

function setError(el, err) {
  el.innerHTML = stateHtml("error", { check: err.check || "", detail: err.message });
}

/* ============================ status bar ============================ */

function setService(ok, err) {
  const el = $("tb-service");
  el.textContent = ok ? ("connected · run " + (S.server ? S.server.package_run_id : "")) : ("adapter unreachable" + (err ? " — " + err.message : ""));
  el.className = "tb-service " + (ok ? "ok" : "err");
  const sb = $("sb-state");
  sb.textContent = ok ? "state: ready" : "state: error";
  sb.className = "sb-item " + (ok ? "ready" : "err");
}

function updateStatusBar() {
  if (S.server) {
    $("sb-run").textContent = "run: " + (S.server.package_run_id || "unknown");
  }
  if (S.dash.q10) {
    const pkg = S.dash.q10.package || {};
    const engine = pkg.engine_identity || {};
    $("sb-engine").textContent = "engine: " + (engine.tool_name || "?") + " " + (engine.tool_version || "");
    const corpus = pkg.corpus || {};
    if (corpus.archive_count !== undefined) $("sb-archives").textContent = "archives: " + fmtInt(corpus.archive_count);
  }
  if (S.dash.q1 && S.dash.q1.summary) $("sb-rows").textContent = "rows: " + fmtInt(S.dash.q1.summary.row_count);
}

/* ============================ dashboard ============================ */

/* Error containment contract (TASK65 / D23 §17(b)): each dashboard query is
   contained independently — a failing query surfaces its error in the
   region(s) that depend on it while the other regions render from their own
   successful responses. Nothing is fabricated: a value whose source failed
   renders as unavailable/error, never as zero, success, or an empty result. */
async function loadDashboard() {
  const d = S.dash;
  if (d.loaded || d.loading) return;
  d.loading = true;
  d.q1Error = d.q6Error = d.q8Error = d.q9Error = d.q10Error = null;
  d.errors = [];
  for (const id of ["dash-rows-year", "dash-segments", "dash-coverage", "dash-archives"]) {
    $(id).innerHTML = stateHtml("loading", "Loading…");
  }
  const names = ["q1", "q6", "q8", "q9", "q10"];
  try {
    const server = S.server || (S.server = await api.status());
    const q10Params = server.repo_root ? { repo: server.repo_root } : {};
    const results = await Promise.allSettled([
      api.query(MODE.Q1, {}),
      api.query(MODE.Q6, {}),
      api.query(MODE.Q8, {}),
      api.query(MODE.Q9, {}),
      api.query(MODE.Q10, q10Params),
    ]);
    results.forEach((r, i) => {
      if (r.status === "fulfilled") d[names[i]] = r.value.query;
      if (r.status === "rejected") {
        d[names[i] + "Error"] = r.reason;
        d.errors.push({ name: names[i], check: r.reason && r.reason.check, message: r.reason && r.reason.message });
      }
    });
  } catch (err) {
    /* the /api/status call itself failed: the adapter is unreachable, so every
       query is failed together — no region may render */
    d.q1Error = d.q6Error = d.q8Error = d.q9Error = d.q10Error = err;
    d.errors = names.map((n) => ({ name: n, check: err.check, message: err.message }));
  }
  d.error = d.errors.length ? d.errors[0] : null;
  d.loading = false;
  d.loaded = d.errors.length === 0;  /* a failed load stays retryable */
  renderDashboard();
  if (S.page === "explorer") renderDatasetSummary();
  updateStatusBar();
}

function errText(err) {
  return (err && err.check ? err.check + " — " : "") + (err && err.message ? err.message : "");
}

function dashFailureHtml(errors, withModes) {
  if (!errors.length) return "";
  const lines = errors.map((e) =>
    '<div class="state-error"><span class="check">' + esc((withModes && e.name ? e.name.toUpperCase() + " · " : "") + (e.check || "")) + "</span> — " + esc(e.message || "") + "</div>"
  );
  return '<div class="dash-failures">' + lines.join("") + "</div>";
}

function renderRunSummary() {
  const el = $("dash-run");
  const d = S.dash;
  const q10 = d.q10;
  if (!q10) {
    el.innerHTML = (d.q10Error ? stateHtml("error", { check: d.q10Error.check || "", detail: d.q10Error.message }) : "") +
      dashFailureHtml(d.errors, true);
    return;
  }
  const pkg = q10.package || {};
  const runId = (pkg.run_identity || {}).run_id || "unavailable";
  const engine = pkg.engine_identity || {};
  const corpus = pkg.corpus || {};
  const manifests = pkg.manifests || {};
  el.innerHTML =
    kvRow("Run ID", runId) +
    kvRow("Run date/time", null) +
    kvRow("Engine", engine.tool_name ? engine.tool_name + " " + (engine.tool_version || "") : null) +
    kvRow("Corpus", corpus.archive_count !== undefined ? fmtInt(corpus.archive_count) + " archives" : null) +
    kvRow("Package files", manifests.file_count !== undefined ? fmtInt(manifests.file_count) + " (" + fmtBytes(manifests.total_bytes || 0) + ")" : null) +
    (S.server && S.server.registry_binding ? kvRow("Registry", S.server.registry_binding.detail || S.server.registry_binding.scope) : "") +
    dashFailureHtml(d.errors, true);
}

function renderKpis() {
  const d = S.dash;
  const cards = [];
  const q9 = d.q9, q1 = d.q1, q6 = d.q6, q8 = d.q8;
  /* a card whose source query failed renders as explicitly unavailable with
     the failure named — never a zero value, never a success glyph */
  if (q9 && q9.summary && q9.summary.archive_count !== undefined) {
    const d01ok = q9.summary.d01_inventory && q9.summary.d01_inventory.present;
    cards.push({ label: "Archives Processed", value: fmtInt(q9.summary.archive_count), glyph: d01ok ? "ok" : "muted", detail: q9.summary.composite_generation ? (d01ok ? "D01 verified for baseline only; incremental inputs have no D01 join" : "D01 absent for baseline and incremental inputs") : (d01ok ? "D01 join verified (Q9)" : "D01 inventory absent (non-pinned baseline)") });
  } else if (d.q9Error) {
    cards.push({ label: "Archives Processed", value: null, glyph: "muted", detail: "unavailable — Q9 failed: " + errText(d.q9Error) });
  } else {
    cards.push({ label: "Archives Processed", value: null, glyph: "muted", detail: "unavailable" });
  }
  if (q1 && q1.summary) {
    cards.push({ label: "Canonical Rows", value: fmtInt(q1.summary.row_count), glyph: "muted", detail: q1.partitions.length + " partitions · " + fmtInt(q1.summary.instrument_pairs) + " instrument pairs" });
  } else if (d.q1Error) {
    cards.push({ label: "Canonical Rows", value: null, glyph: "muted", detail: "unavailable — Q1 failed: " + errText(d.q1Error) });
  } else {
    cards.push({ label: "Canonical Rows", value: null, glyph: "muted", detail: "unavailable" });
  }
  cards.push({ label: "Identity Records", value: null, glyph: "muted", detail: "No authorized count operation in the first release (Q5 is selector-scoped)" });
  if (q6) {
    if (q6.calendar_present) cards.push({ label: "Trading Calendars", value: fmtInt(q6.record_count), glyph: "muted", detail: q6.scope && q6.scope.includes("baseline-calendar-absent") ? "file presence from baseline manifest and incremental inputs; original calendar absent" : "served calendar days (Q6)" });
    else cards.push({ label: "Trading Calendars", value: "absent", glyph: "muted", detail: "package carries no calendar (legitimate state)" });
  } else if (d.q6Error) {
    cards.push({ label: "Trading Calendars", value: null, glyph: "muted", detail: "unavailable — Q6 failed: " + errText(d.q6Error) });
  } else {
    cards.push({ label: "Trading Calendars", value: null, glyph: "muted", detail: "unavailable" });
  }
  if (q8) {
    const flagTotal = Object.values(q8.flag_census || {}).reduce((s, n) => s + n, 0);
    cards.push({ label: "Errors", value: fmtInt(flagTotal), glyph: flagTotal > 0 ? "warn" : "muted", detail: "row flags (Q8) · quarantined " + fmtInt((q8.quarantine || {}).count || 0) });
  } else if (d.q8Error) {
    cards.push({ label: "Errors", value: null, glyph: "muted", detail: "unavailable — Q8 failed: " + errText(d.q8Error) });
  } else {
    cards.push({ label: "Errors", value: null, glyph: "muted", detail: "unavailable" });
  }
  $("dash-kpis").innerHTML = cards.map((c) =>
    "<div class=\"kpi\"><span class=\"kpi-glyph glyph-" + c.glyph + "\" title=\"" + esc(c.detail) + "\"></span>" +
    (c.value === null ? "<div class=\"kpi-value unavailable\">unavailable</div>" : "<div class=\"kpi-value\">" + c.value + "</div>") +
    "<div class=\"kpi-label\">" + esc(c.label) + "</div>" +
    "<div class=\"kpi-detail\" title=\"" + esc(c.detail) + "\">" + esc(c.detail) + "</div></div>"
  ).join("");
}

function renderDashboard() {
  const d = S.dash;
  renderRunSummary();
  renderKpis();

  /* rows by year (Q1) */
  if (d.q1Error) {
    setError($("dash-rows-year"), d.q1Error);
  } else {
    const byYear = rowsByYear(d.q1 ? d.q1.partitions : []);
    $("dash-rows-year").innerHTML = byYear.length ? barChart(byYear) : stateHtml("empty", "No partitions served.");
  }

  /* segments (Q9) */
  if (d.q9Error) {
    setError($("dash-segments"), d.q9Error);
  } else {
    const segs = segmentCounts(d.q9 ? d.q9.archives : []);
    if (!segs.length) {
    $("dash-segments").innerHTML = stateHtml("unavailable", "Series breakdown unavailable — no served D01 series_counts for this baseline.");
  } else {
    const total = segs.reduce((s, e) => s + e.row_count, 0);
    $("dash-segments").innerHTML = donutChart(segs) + "<div class=\"seg-legend\">" + segs.map((e, i) =>
      "<div class=\"row\"><span class=\"seg-dot\" style=\"background:" + SEGMENT_COLORS[i % SEGMENT_COLORS.length] + "\"></span>" +
      "<span>" + esc(e.segment) + "</span><span class=\"muted\">· " + fmtInt(e.archive_count) + " archive" + (e.archive_count === 1 ? "" : "s") + " · " + fmtInt(e.row_count) + " rows</span>" +
      "<span class=\"pct\">" + ((e.row_count / total) * 100).toFixed(1) + "%</span></div>"
      ).join("") + "</div>";
    }
  }

  /* coverage */
  const cov = coverageSummary(
    d.q1 ? d.q1.partitions : [],
    d.q6 && d.q6.calendar_present ? d.q6.records : [],
    d.q9 ? d.q9.archives : [],
    d.q1 ? d.q1.summary : null
  );
  if (d.q9Error) cov.total_archives = null;  /* no zero substitute for a failed source */
  const covFailures = [
    d.q1Error ? { name: "q1", check: d.q1Error.check, message: d.q1Error.message } : null,
    d.q6Error ? { name: "q6", check: d.q6Error.check, message: d.q6Error.message } : null,
    d.q9Error ? { name: "q9", check: d.q9Error.check, message: d.q9Error.message } : null,
  ].filter(Boolean);
  $("dash-coverage").innerHTML = "<div class=\"coverage-list\">" +
    kvRow("Start date", cov.start_date) +
    kvRow("End date", cov.end_date) +
    kvRow("Trading days", cov.trading_days !== null ? fmtInt(cov.trading_days) : null) +
    kvRow("Total archives", cov.total_archives) +
    kvRow("Total rows", cov.total_rows) +
    kvRow("Instruments", cov.instruments) +
    kvRow("Published series codes", cov.exchange_segments ? cov.exchange_segments.join(", ") : null) +
    "</div>" + (cov.partition_years.length ? "<div class=\"muted\" style=\"font-size:10.5px;margin-top:6px\">partition years: " + cov.partition_years.join(", ") + "</div>" : "") +
    dashFailureHtml(covFailures, true);

  renderArchives();
  renderArchiveDetail();
}

function archiveSegmentOf(rec) {
  const d01 = rec && rec.d01;
  if (!d01 || typeof d01.series_counts !== "object" || d01.series_counts === null) return "";
  return Object.keys(d01.series_counts).sort().join("+");
}
function archiveYearOf(rec) {
  const d = rec && rec.date_from_filename;
  return typeof d === "string" && /^\d{4}/.test(d) ? d.slice(0, 4) : "";
}

function renderArchives() {
  const d = S.dash;
  if (d.q9Error) {
    $("archive-count").textContent = "unavailable";
    setError($("dash-archives"), d.q9Error);
    return;
  }
  const archives = d.q9 ? d.q9.archives : [];
  /* filter + search + sort (display-level over served rows) */
  let rows = archives.slice();
  if (d.archiveSearch) {
    const q = d.archiveSearch.toLowerCase();
    rows = rows.filter((r) => (
      String(r.member_name || "").toLowerCase().includes(q) ||
      String(r.date_from_filename || "").toLowerCase().includes(q) ||
      archiveSegmentOf(r).toLowerCase().includes(q) ||
      String(r.sequence !== undefined ? r.sequence : "").includes(q)
    ));
  }
  if (d.archiveSegment) rows = rows.filter((r) => Object.keys((r.d01 && r.d01.series_counts) || {}).includes(d.archiveSegment));
  if (d.archiveYear) rows = rows.filter((r) => archiveYearOf(r) === d.archiveYear);
  const key = d.sortKey, dir = d.sortDir;
  rows.sort((a, b) => {
    let va, vb;
    if (key === "sequence") { va = a.sequence; vb = b.sequence; }
    else if (key === "date") { va = a.date_from_filename || ""; vb = b.date_from_filename || ""; }
    else if (key === "rows") { va = (a.d01 && a.d01.row_count) || a.data_lines || 0; vb = (b.d01 && b.d01.row_count) || b.data_lines || 0; }
    else if (key === "size") { va = a.member_size_bytes || 0; vb = b.member_size_bytes || 0; }
    else if (key === "segment") { va = archiveSegmentOf(a); vb = archiveSegmentOf(b); }
    else if (key === "symbols") { va = (a.d01 && a.d01.symbol_count) || 0; vb = (b.d01 && b.d01.symbol_count) || 0; }
    else { va = a.member_name || ""; vb = b.member_name || ""; }
    if (va === vb) return 0;
    return (va < vb ? -1 : 1) * dir;
  });

  /* filter options (from served values only) */
  const segSet = [...new Set(archives.flatMap((r) => Object.keys((r.d01 && r.d01.series_counts) || {})))].sort();
  const yearSet = [...new Set(archives.map(archiveYearOf).filter(Boolean))].sort();
  const segSel = $("archive-segment");
  segSel.innerHTML = '<option value="">All series codes</option>' + segSet.map((s) => '<option' + (d.archiveSegment === s ? " selected" : "") + ">" + esc(s) + "</option>").join("");
  const yearSel = $("archive-year");
  yearSel.innerHTML = '<option value="">All years</option>' + yearSet.map((s) => '<option' + (d.archiveYear === s ? " selected" : "") + ">" + esc(s) + "</option>").join("");
  $("archive-count").textContent = rows.length + " of " + archives.length + " archives";

  if (!rows.length) { $("dash-archives").innerHTML = stateHtml("empty", "No archives match the current search/filters."); return; }
  const ind = (k) => d.sortKey === k ? '<span class="sort-ind">' + (dir > 0 ? "▲" : "▼") + "</span>" : "";
  const head = (label, key, cls) => '<th class="sortable ' + (cls || "") + '" data-sort="' + key + '" title="Sort by ' + label + '">' + label + " " + ind(key) + "</th>";
  let html = "<table class=\"data\" id=\"archive-table\"><thead><tr>" +
    "<th>#</th>" + head("Archive", "name") + head("Date", "date") + head("Series codes", "segment") +
    head("Symbols", "symbols", "num") + "<th>Status</th>" + head("Rows", "rows", "num") + head("File Size", "size", "num") +
    "</tr></thead><tbody>";
  rows.forEach((r, i) => {
    const seg = archiveSegmentOf(r);
    const verified = r.d01 && Object.keys(r.d01).length > 0;
    html += "<tr data-idx=\"" + i + "\" class=\"" + (i === d.archiveSelection ? "selected" : "") + '" tabindex="0">' +
      "<td class=\"num muted\">" + (i + 1) + "</td>" +
      "<td class=\"mono\" title=\"" + esc(r.member_name || "") + "\">" + esc(r.member_name || "") + "</td>" +
      "<td>" + esc(r.date_from_filename || "—") + "</td>" +
      "<td>" + (seg ? esc(seg) : '<span class="muted">—</span>') + "</td>" +
      "<td class=\"num\">" + (r.d01 && r.d01.symbol_count !== undefined ? fmtInt(r.d01.symbol_count) : '<span class="muted">—</span>') + "</td>" +
      "<td>" + (verified ? '<span class="chip ok">verified</span>' : '<span class="chip unavail">d01 absent</span>') + "</td>" +
      "<td class=\"num\">" + fmtInt(r.data_lines || 0) + "</td>" +
      "<td class=\"num\">" + fmtBytes(r.member_size_bytes) + "</td>" +
      "</tr>";
  });
  html += "</tbody></table>";
  $("dash-archives").innerHTML = html;
  const table = $("archive-table");
  if (table) {
    table.querySelectorAll("th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const k = th.getAttribute("data-sort");
        if (d.sortKey === k) d.sortDir = -d.sortDir; else { d.sortKey = k; d.sortDir = 1; }
        renderArchives();
      });
    });
    table.querySelectorAll("tbody tr").forEach((tr) => {
      const pick = () => { d.archiveSelection = parseInt(tr.getAttribute("data-idx"), 10); renderArchives(); renderArchiveDetail(); };
      tr.addEventListener("click", pick);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    });
  }
}

function renderArchiveDetail() {
  const d = S.dash;
  const el = $("dash-archive-detail");
  const archives = d.q9 ? d.q9.archives : [];
  /* the selection indexes the filtered table; recompute the same filter to map it */
  let rows = archives.slice();
  if (d.archiveSearch) {
    const q = d.archiveSearch.toLowerCase();
    rows = rows.filter((r) => (
      String(r.member_name || "").toLowerCase().includes(q) ||
      String(r.date_from_filename || "").toLowerCase().includes(q) ||
      archiveSegmentOf(r).toLowerCase().includes(q)
    ));
  }
  if (d.archiveSegment) rows = rows.filter((r) => Object.keys((r.d01 && r.d01.series_counts) || {}).includes(d.archiveSegment));
  if (d.archiveYear) rows = rows.filter((r) => archiveYearOf(r) === d.archiveYear);
  rows.sort((a, b) => {
    let va, vb;
    const key = d.sortKey, dir = d.sortDir;
    if (key === "sequence") { va = a.sequence; vb = b.sequence; }
    else if (key === "date") { va = a.date_from_filename || ""; vb = b.date_from_filename || ""; }
    else if (key === "rows") { va = (a.d01 && a.d01.row_count) || a.data_lines || 0; vb = (b.d01 && b.d01.row_count) || b.data_lines || 0; }
    else if (key === "size") { va = a.member_size_bytes || 0; vb = b.member_size_bytes || 0; }
    else if (key === "segment") { va = archiveSegmentOf(a); vb = archiveSegmentOf(b); }
    else if (key === "symbols") { va = (a.d01 && a.d01.symbol_count) || 0; vb = (b.d01 && b.d01.symbol_count) || 0; }
    else { va = a.member_name || ""; vb = b.member_name || ""; }
    return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
  });
  const rec = rows[d.archiveSelection];
  if (!rec) { el.innerHTML = stateHtml("empty", "Select an archive row to view its served metadata."); return; }
  const d01 = rec.d01;
  let html = "<div class=\"insp-group\"><div class=\"insp-group-title\">Archive (INPUT_MANIFEST, as published)</div><table class=\"kv-table\">";
  const kv = (k, v) => "<tr><td class=\"k\">" + esc(k) + "</td><td class=\"v\">" + (v === null || v === undefined ? '<span class="chip unavail">unavailable</span>' : esc(String(v))) + "</td></tr>";
  html += kv("Archive Name", rec.member_name) + kv("File Name", rec.file_name) + kv("Date", rec.date_from_filename) +
    kv("Format", rec.detected_format) + kv("Engine family", rec.engine_family) + kv("Partition", rec.partition) +
    kv("Sequence", rec.sequence) + kv("Root", rec.root) + kv("Relative path", rec.relative_path) +
    kv("Member size", rec.member_size_bytes !== undefined ? fmtBytes(rec.member_size_bytes) : null) +
    kv("Data lines", rec.data_lines) + kv("Header width", rec.header_physical_width) + kv("Header tolerance", rec.header_tolerance_applied);
  html += "</table></div>";
  if (d01) {
    html += "<div class=\"insp-group\"><div class=\"insp-group-title\">D01 inventory facts (joined, verified)</div><table class=\"kv-table\">" +
      kv("SHA-256 (D01)", d01.sha256) + kv("Size (D01)", d01.size_bytes !== undefined ? fmtBytes(d01.size_bytes) : null) +
      kv("Rows (D01)", d01.row_count) + kv("Bad rows (D01)", d01.bad_rows) + kv("Symbols", d01.symbol_count) + kv("ISINs", d01.isin_count) +
      kv("Series counts", d01.series_counts ? Object.entries(d01.series_counts).map(([k, v]) => k + ": " + v).join(", ") : null) +
      kv("Header signature", d01.header_signature) + "</table></div>";
  } else {
    html += "<div class=\"state-unavailable\" style=\"margin-bottom:12px\">D01 inventory facts unavailable — this baseline is not the pinned M2 baseline, so the D01 join is explicitly absent (never fabricated).</div>";
  }
  html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Archive hashes (served facts)</div><table class=\"kv-table\">" +
    kv("archive_sha256_d01", rec.archive_sha256_d01) + kv("archive_sha256_observed_raw_bytes", rec.archive_sha256_observed_raw_bytes) +
    kv("basis", rec.archive_sha256_basis) + kv("member_sha256_raw_bytes", rec.member_sha256_raw_bytes) + kv("member_sha256_lf_text", rec.member_sha256_lf_text) +
    "</table></div>";
  const segs = d01 && d01.series_counts ? Object.keys(d01.series_counts).sort() : [];
  html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Actions</div><div class=\"insp-actions\">" +
    '<button class="btn btn-small" id="adv-canonical" title="Open the Data Explorer with a series filter only when this archive has exactly one published series code; this is not an archive filter">Canonical Data</button>' +
    '<button class="btn btn-small" id="adv-identity" title="Open the Data Explorer — related records (Q5) are shown per selected record">Identity / Association</button>' +
    '<button class="btn btn-small" disabled title="Unavailable — no authorized per-archive calendar overlay operation exists.">Calendar Overlay</button>' +
    '<button class="btn btn-small" id="adv-recon" title="Open the Data Explorer quality view (Q8 reconciliation aggregates)">Reconciliation</button>' +
    "</div></div>";
  el.innerHTML = html;
  $("adv-canonical").addEventListener("click", () => {
    const seg = segs.length === 1 ? segs[0] : null;
    switchPage("explorer");
    if (seg) {
      setBuilderMode(MODE.Q4);
      S.expl.builder.q4 = [{ field: "series", value: seg }];
      renderQ4Rows();
    }
  });
  $("adv-identity").addEventListener("click", () => { switchPage("explorer"); });
  $("adv-recon").addEventListener("click", () => { switchPage("explorer"); setTimeout(() => $("panel-quality").scrollIntoView({ block: "nearest" }), 60); });
}

/* ============================ explorer: builder ============================ */

function setBuilderMode(mode) {
  S.expl.builder.mode = mode;
  S.expl.builder.quick = null;
  $("q-mode").value = mode;
  $("fld-date-from").classList.toggle("hidden", mode !== MODE.Q2);
  $("fld-date-to").classList.toggle("hidden", mode !== MODE.Q2);
  $("fld-symbol").classList.toggle("hidden", mode !== MODE.Q3);
  $("fld-series").classList.toggle("hidden", mode !== MODE.Q3);
  $("fld-year").classList.toggle("hidden", mode !== MODE.Q3);
  $("q4-block").style.display = mode === MODE.Q4 ? "" : "none";
  renderQuickPills();
}

function renderQ4Rows() {
  const box = $("q4-rows");
  box.innerHTML = S.expl.builder.q4.map((f, i) =>
    '<div class="q4-row">' +
    '<select class="input" data-i="' + i + '" data-k="field" aria-label="Filter field">' +
      Q4_FIELDS.map((field) => '<option' + (f.field === field ? " selected" : "") + ">" + esc(field) + "</option>").join("") +
    "</select>" +
    '<span class="muted" style="align-self:center">=</span>' +
    '<input class="input" data-i="' + i + '" data-k="value" type="text" value="' + esc(f.value) + '" placeholder="exact as-published value" aria-label="Filter value">' +
    '<button class="q4-remove" data-i="' + i + '" title="Remove filter" aria-label="Remove filter">✕</button>' +
    "</div>"
  ).join("");
  box.querySelectorAll("[data-k]").forEach((el) => {
    el.addEventListener("change", () => {
      const i = parseInt(el.getAttribute("data-i"), 10);
      S.expl.builder.q4[i][el.getAttribute("data-k")] = el.value;
      S.expl.builder.quick = null;
      renderQuickPills();
    });
  });
  box.querySelectorAll(".q4-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      S.expl.builder.q4.splice(parseInt(btn.getAttribute("data-i"), 10), 1);
      S.expl.builder.quick = null;
      renderQ4Rows();
      renderQuickPills();
    });
  });
}

function renderQuickPills() {
  const box = $("q-quick");
  box.innerHTML = QUICK_FILTERS.map((name) => {
    const unavailable = ["Reliable Only", "Debt", "Currency", "FO segment"].includes(name);
    const reason = name === "Reliable Only" ? "Unavailable — no reliability classification exists." : "Unavailable — no verified exact mapping is published for this preset.";
    return '<button class="quick-pill' + (S.expl.builder.quick === name ? " active" : "") + '" data-quick="' + esc(name) + '"' +
      (unavailable ? ' disabled title="' + esc(reason) + '"' :
        ' title="Latest N years" data-note="data-relative to the served partition years"') + ">" + esc(name) + "</button>";
  }).join("");
  box.querySelectorAll(".quick-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      applyQuickFilter(pill.getAttribute("data-quick"));
    });
  });
}

async function applyQuickFilter(name) {
  let spec = null;
  if (name.startsWith("Latest ")) {
    if (!S.expl.q1Cache) {
      const doc = await api.query(MODE.Q1, {});
      S.expl.q1Cache = doc.query;
    }
    const years = (S.expl.q1Cache.partitions || []).map((p) => p.year).filter((y) => /^\d{4}$/.test(y)).map((y) => parseInt(y, 10));
    spec = quickFilterParams(name, years.length ? Math.max(...years) : null);
  } else {
    spec = quickFilterParams(name, null);
  }
  if (!spec) {
    showBuilderError(new Error("Preset unavailable: no authorized query maps to it (the contract defines no such semantics)."));
    return;
  }
  S.expl.builder.quick = name;
  if (spec.mode === MODE.Q4) {
    setBuilderMode(MODE.Q4);
    S.expl.builder.q4 = Object.entries(spec.params.filters).map(([field, value]) => ({ field, value }));
    renderQ4Rows();
  } else {
    setBuilderMode(MODE.Q2);
    $("q-date-from").value = spec.params.date_from;
    $("q-date-to").value = spec.params.date_to;
  }
  renderQuickPills();
  hideBuilderError();
}

function builderParams() {
  const b = S.expl.builder;
  const err = $("builder-error");
  if (b.mode === MODE.Q2) {
    const from = $("q-date-from").value, to = $("q-date-to").value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) {
      return { error: "Q2 requires both inclusive ISO dates (YYYY-MM-DD)." };
    }
    return { params: { date_from: from, date_to: to } };
  }
  if (b.mode === MODE.Q3) {
    const symbol = $("q-symbol").value.trim(), series = $("q-series").value.trim();
    const yearRaw = $("q-year").value;
    if (!symbol || !series) return { error: "Q3 requires both trading symbol (or published listing symbol) and series." };
    const params = { symbol, series };
    if (yearRaw !== "") {
      const year = parseInt(yearRaw, 10);
      if (!Number.isInteger(year) || year < 1000 || year > 9999) return { error: "Year must be a 4-digit integer." };
      params.year = year;
    }
    return { params };
  }
  if (b.mode === MODE.Q4) {
    const filters = {};
    for (const f of b.q4) {
      if (!f.field || !Q4_FIELDS.includes(f.field)) return { error: "Every Q4 filter needs a supported field (series/segment/source/instrument_type/symbol)." };
      if (f.value === "") return { error: "Every Q4 filter needs an exact as-published value (blank is not a value)." };
      if (f.value !== f.field && filters[f.field] !== undefined) return { error: "One value per field (AND semantics; equality only)." };
      filters[f.field] = f.value;
    }
    if (!Object.keys(filters).length) return { error: "Q4 requires at least one filter." };
    return { params: { filters } };
  }
  return { error: "Unknown query mode." };
}

function showBuilderError(err) {
  const el = $("builder-error");
  el.textContent = (err.check ? "[" + err.check + "] " : "") + err.message;
  el.hidden = false;
}
function hideBuilderError() { $("builder-error").hidden = true; }

async function runQuery() {
  const b = S.expl.builder;
  const built = builderParams();
  if (built.error) { showBuilderError(new Error(built.error)); return; }
  hideBuilderError();
  S.expl.busy = true;
  $("builder-busy").hidden = false;
  $("btn-run").disabled = true;
  $("expl-results").innerHTML = stateHtml("loading", "Running " + b.mode + "…");
  try {
    const doc = await api.query(b.mode, built.params);
    const rows = (doc.query.rows || doc.query.records || []).slice();
    S.expl.results = {
      doc: doc.query, rows,
      meta: { mode: b.mode, params: built.params },
      page: 0, perPage: S.expl.results.perPage, selected: -1,
      banner: null,
    };
    S.expl.inspector = { loading: false, error: null, detail: null, related: null, relatedError: null };
    renderResults();
    renderInspector();
    renderPriceChart();
    renderYearly();
  } catch (err) {
    S.expl.results = { doc: null, rows: [], meta: null, page: 0, perPage: S.expl.results.perPage, selected: -1, banner: null };
    $("expl-results").innerHTML = stateHtml("error", { check: err.check || "", detail: "Query failed — nothing was served. " + err.message });
    renderInspector();
  } finally {
    S.expl.busy = false;
    $("builder-busy").hidden = true;
    $("btn-run").disabled = false;
  }
}

function saveCurrentQuery() {
  const b = S.expl.builder;
  const built = builderParams();
  if (built.error) { showBuilderError(new Error(built.error)); return; }
  hideBuilderError();
  const id = window.prompt("Saved-query identifier (1–64 chars, [a-z0-9_-], starts with [a-z0-9]):");
  if (id === null) return;
  const trimmed = id.trim();
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(trimmed)) {
    showBuilderError(new Error("Invalid identifier: 1–64 chars of [a-z0-9_-], starting with [a-z0-9]."));
    return;
  }
  api.savedCreate({ id: trimmed, mode: b.mode, params: built.params })
    .then(() => {
      S.expl.saved.loaded = false;
      S.expl.saved.entries = [];
      switchTab("saved");
    })
    .catch((err) => showBuilderError(new Error((err.check ? "[" + err.check + "] " : "") + err.message)));
}

function resetBuilder() {
  S.expl.builder = { mode: MODE.Q3, quick: null, q4: [] };
  $("q-date-from").value = "";
  $("q-date-to").value = "";
  $("q-symbol").value = "";
  $("q-series").value = "";
  $("q-year").value = "";
  setBuilderMode(MODE.Q3);
  renderQ4Rows();
  hideBuilderError();
}

/* ============================ explorer: results ============================ */

const RESULT_COLUMNS = [
  ["#", "#", "num"], ["Trade Date", "date", ""], ["Observed ticker", "symbol", ""], ["ISIN", "isin", ""],
  ["Series", "series", ""], ["Segment", "segment", ""], ["Open", "open", "num"], ["High", "high", "num"],
  ["Low", "low", "num"], ["Close", "close", "num"], ["Volume", "volume", "num"], ["Turnover (₹)", "turnover", "num"], ["Status", "status", ""],
];

function renderResults() {
  const R = S.expl.results;
  const el = $("expl-results");
  const count = R.doc && (R.doc.result_count !== undefined ? R.doc.result_count : R.rows.length);
  $("results-count").textContent = R.doc ? fmtInt(count) + " records (served)" : "";
  if (R.banner) $("results-title").textContent = "Query Results — " + R.banner;
  else $("results-title").textContent = "Query Results";
  if (!R.doc) { el.innerHTML = stateHtml("empty", "Run a query to see served rows."); renderPagination(); return; }
  if (!R.rows.length) {
    el.innerHTML = stateHtml("empty", "The query succeeded and the served result is empty (no matching rows) — this is distinct from a query failure.");
    renderPagination();
    return;
  }
  const per = R.perPage;
  const pages = Math.max(1, Math.ceil(R.rows.length / per));
  R.page = Math.min(R.page, pages - 1);
  const start = R.page * per;
  const slice = R.rows.slice(start, start + per);
  $("results-range").textContent = (start + 1) + "–" + Math.min(start + per, R.rows.length) + " of " + fmtInt(R.rows.length);
  let html = "<table class=\"data\" id=\"results-table\"><thead><tr>" +
    RESULT_COLUMNS.map((c) => "<th class=\"" + (c[2] || "") + "\">" + esc(c[0]) + "</th>").join("") +
    "</tr></thead><tbody>";
  slice.forEach((row, i) => {
    const gi = start + i;
    const vs = row.source_values || {};
    const fs = flagStatus(row.flags);
    const cell = (v, cls) => "<td class=\"" + (cls || "") + "\">" + (v === null || v === undefined || v === "" ? '<span class="muted">—</span>' : esc(v)) + "</td>";
    html += "<tr data-gi=\"" + gi + '" class="' + (gi === R.selected ? "selected" : "") + '"' + (fs.state === "flagged" ? " flagged" : "") + ' tabindex="0" title="' + esc(row.serving ? (row.serving.source_file || "") + ":" + (row.serving.source_line_number !== undefined ? row.serving.source_line_number : row.source_line_number) : "") + '">' +
      cell(gi + 1, "num muted") +
      cell(row.business_date, "mono") +
      cell(((row.serving || {}).trading_symbol || {}).observed_symbol, "mono") +
      cell(vs.security_isin, "mono") +
      cell(vs.series) +
      cell(vs.segment) +
      cell(vs.price_open, "num mono") +
      cell(vs.price_high, "num mono") +
      cell(vs.price_low, "num mono") +
      cell(vs.price_close, "num mono") +
      cell(vs.traded_quantity, "num mono") +
      cell(vs.traded_value, "num mono") +
      '<td>' + (fs.state === "flagged" ? '<span class="chip warn" title="' + esc(fs.text) + '">flags: ' + esc(fs.text.split(",")[0]) + (fs.text.split(",").length > 1 ? "…" : "") + "</span>" : '<span class="chip ok">clean</span>') + "</td>" +
      "</tr>";
  });
  html += "</tbody></table>";
  el.innerHTML = html;
  const table = $("results-table");
  if (table) {
    table.querySelectorAll("tbody tr").forEach((tr) => {
      const gi = parseInt(tr.getAttribute("data-gi"), 10);
      const pick = () => selectRow(gi);
      tr.addEventListener("click", pick);
      tr.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
        else if (e.key === "ArrowDown") { e.preventDefault(); selectRow(Math.min(R.rows.length - 1, gi + 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); selectRow(Math.max(0, gi - 1)); }
      });
    });
  }
  renderPagination();
}

function renderPagination() {
  const R = S.expl.results;
  const per = R.perPage;
  const pages = Math.max(1, Math.ceil((R.rows.length || 0) / per));
  R.page = Math.min(R.page, pages - 1);
  $("results-prev").disabled = R.page <= 0;
  $("results-next").disabled = R.page >= pages - 1 || !R.rows.length;
  if (R.rows.length) $("results-range").textContent = (R.page * per + 1) + "–" + Math.min(R.page * per + per, R.rows.length) + " of " + fmtInt(R.rows.length);
}

async function selectRow(gi) {
  const R = S.expl.results;
  R.selected = gi;
  renderResults();
  const row = R.rows[gi];
  const insp = S.expl.inspector;
  const serving = row.serving || {};
  const sourceFile = serving.source_file || row.source_file;
  const sourceLine = serving.source_line_number !== undefined ? serving.source_line_number : row.source_line_number;
  insp.loading = true;
  insp.error = null;
  insp.detail = null;
  insp.related = null;
  insp.relatedError = null;
  renderInspector();
  try {
    const [detailDoc, relatedDoc] = await Promise.all([
      api.query(MODE.Q7, { source_file: sourceFile, source_line_number: sourceLine }),
      ((((row.serving || {}).trading_symbol || {}).effective_symbol || sv(row, "listing_symbol")) && sv(row, "series"))
        ? api.query(MODE.Q5, { symbol: ((row.serving || {}).trading_symbol || {}).effective_symbol || sv(row, "listing_symbol"), series: sv(row, "series") })
        : Promise.resolve(null),
    ]);
    if (R.selected !== gi) return; /* a newer selection superseded this fetch */
    insp.detail = detailDoc.query;
    insp.related = relatedDoc ? relatedDoc.query : null;
  } catch (err) {
    if (R.selected !== gi) return;
    insp.error = err;
  } finally {
    insp.loading = false;
    renderInspector();
  }
}

/* ============================ explorer: inspector ============================ */

function renderInspector() {
  const el = $("expl-inspector");
  const R = S.expl.results;
  const insp = S.expl.inspector;
  $("ins-prev").disabled = R.selected <= 0;
  $("ins-next").disabled = R.selected < 0 || R.selected >= R.rows.length - 1;
  if (R.selected < 0) {
    el.innerHTML = stateHtml("empty", "Select a result row to view its served detail (Q7), related records (Q5), and reconciliation facts.");
    return;
  }
  if (insp.loading) { el.innerHTML = stateHtml("loading", "Loading record detail (Q7) and related records (Q5)…"); return; }
  if (insp.error) { el.innerHTML = stateHtml("error", { check: insp.error.check || "", detail: insp.error.message }); return; }
  if (!insp.detail) { el.innerHTML = stateHtml("empty", "No detail."); return; }
  const d = insp.detail;
  const row = d.row || {};
  const vs = row.source_values || {};
  const prov = row.provenance || {};
  const archive = d.archive || {};
  const fs = flagStatus(row.flags);
  const assocCount = insp.related && insp.related.record_count !== undefined ? insp.related.record_count : null;
  const kv = (k, v, cls) => "<tr><td class=\"k\">" + esc(k) + "</td><td class=\"v " + (cls || "") + "\">" + (v === null || v === undefined ? '<span class="chip unavail">unavailable</span>' : esc(String(v))) + "</td></tr>";
  const chip = (k, text, type) => "<tr><td class=\"k\">" + esc(k) + "</td><td class=\"v\"><span class=\"chip " + type + "\">" + esc(text) + "</span></td></tr>";
  let html = "<div class=\"insp-group\"><div class=\"insp-group-title\">Instrument</div><table class=\"kv-table\">" +
    kv("Observed ticker", ((d.row.serving || {}).trading_symbol || {}).observed_symbol, "mono") +
    kv("Ticker source", ((d.row.serving || {}).trading_symbol || {}).source_column) +
    kv("Published listing_symbol", vs.listing_symbol, "mono") + kv("ISIN", vs.security_isin, "mono") + kv("Series", vs.series, "mono") +
    "</table></div>";
  html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Trading Details</div><table class=\"kv-table\">" +
    kv("Trade Date", row.business_date, "mono") + kv("Segment", vs.segment) +
    kv("Open", vs.price_open, "mono") + kv("High", vs.price_high, "mono") + kv("Low", vs.price_low, "mono") + kv("Close", vs.price_close, "mono") +
    kv("Volume", vs.traded_quantity, "mono") + kv("Turnover (₹)", vs.traded_value, "mono") +
    chip("Trading Status", "not a canonical field — unavailable", "unavail") +
    "</table></div>";
  html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Data Quality</div><table class=\"kv-table\">" +
    kv("Identity Status", (row.isin_validity || "unavailable") + (row.isin_normalized ? " (" + row.isin_normalized + ")" : ""), "mono") +
    chip("Record Status", fs.state === "flagged" ? fs.text : "no flags", fs.state === "flagged" ? "warn" : "ok") +
    (assocCount === null ? chip("Association Status", "unavailable (no selector pair on row)", "unavail") : kv("Association Status", assocCount > 0 ? assocCount + " interval" + (assocCount === 1 ? "" : "s") : "none for this instrument")) +
    "</table></div>";
  html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Provenance (D05 §8 block, as served)</div><table class=\"kv-table\">" +
    kv("Source Archive", prov.member_name, "mono") + kv("Source Row", row.source_line_number, "mono") +
    kv("Archive Path", archive.relative_path, "mono") +
    kv("Archive SHA-256", prov.archive_sha256, "mono") +
    kv("SHA-256 basis", prov.archive_sha256_basis) +
    kv("Member SHA-256 (raw)", prov.member_sha256_raw_bytes, "mono") +
    kv("Format family", prov.format_family) + kv("Run ID", prov.run_id, "mono") +
    kv("Units and provenance", row.units_provenance_note) +
    "</table><div class=\"muted\" style=\"font-size:10.5px;margin-top:4px\">Fields absent from the canonical row contract (e.g., company id/name) are not shown — they are not published, and no placeholder is substituted.</div></div>";
  if (insp.related && insp.related.continuity) {
    const c = insp.related.continuity;
    html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Trading-symbol continuity (" + esc(c.format) + ")</div>" +
      "<div>" + esc(c.availability) + (c.reason ? " — " + esc(c.reason) : "") + "</div>";
    for (const rec of (insp.related.records || [])) {
      for (const group of ((rec.serving || {}).continuity || [])) {
        html += "<div class=\"rel-item\">" + esc(group.series) + " · " + esc(group.status) + ": " +
          group.intervals.map((i) => esc(i.symbol) + " (" + esc(i.observed_from) + " → " + esc(i.observed_to) + ")").join(", ") +
          (group.ambiguities.length ? " · " + group.ambiguities.map(esc).join("; ") : "") + "</div>";
      }
    }
    html += "</div></div>";
  }
  if (insp.related && insp.related.record_count > 0) {
    html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Related Records (Q5, as published)</div><div class=\"rel-list\">";
    for (const rec of insp.related.records.slice(0, 8)) {
      const projected = ((rec.serving || {}).trading_symbol || {}).observed_symbols || [];
      const tickerText = projected.length ? projected.join(", ") : "ticker unavailable";
      html += "<div class=\"rel-item\"><b>" + esc(tickerText) + "</b> " + esc(rec.series || "") +
        " <span class=\"meta\">published symbol: " + esc(rec.symbol || "") + " · " + esc(rec.observed_from || "") + " → " + esc(rec.observed_to || "") + " · " + esc(rec.interval_basis || "") +
        " · " + (rec.contributing_rows ? rec.contributing_rows.length + " contributing rows" : "") + "</span></div>";
    }
    html += "</div></div>";
  } else if (insp.related && insp.related.record_count === 0) {
    html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Related Records (Q5)</div><div class=\"state-empty\">No dated-association intervals served for this instrument" + (insp.related.associations_present === false ? " (the package carries no associations file — legitimate state)" : "") + ".</div></div>";
  }
  if (d.reconciliation_availability) {
    html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Reconciliation</div><div class=\"state-unavailable\">" + esc(d.reconciliation_availability) + "</div></div>";
  }
  if (d.reconciliation && d.reconciliation.length) {
    html += "<div class=\"insp-group\"><div class=\"insp-group-title\">Reconciliation (served records for this archive)</div><div class=\"recon-list\">";
    for (const r of d.reconciliation.slice(0, 6)) {
      const summary = Object.entries(r).filter(([k]) => !["serving"].includes(k)).slice(0, 4).map(([k, v]) => k + "=" + (typeof v === "object" ? JSON.stringify(v) : v)).join(" ");
      html += "<div class=\"recon-item\">" + esc(summary) + "</div>";
    }
    html += "</div></div>";
  }
  html += "<div class=\"insp-actions\">" +
    '<button class="btn btn-small" disabled title="Withheld: raw-content serving is explicitly withheld in D23 §19 — the raw record is never served.">View Raw Record</button>' +
    '<button class="btn btn-small" disabled title="Withheld: archive bytes are in Windows custody (D15 §14) — no archive-byte serving exists.">View Archive</button>' +
    '<button class="btn btn-small" id="insp-view-recon">View Reconciliation</button>' +
    "</div>";
  el.innerHTML = html;
  const v = $("insp-view-recon");
  if (v) v.addEventListener("click", () => el.querySelector(".recon-list") && el.querySelector(".recon-list").scrollIntoView({ block: "nearest" }));
}

/* ============================ explorer: charts & summaries ============================ */

function renderPriceChart() {
  const el = $("expl-price");
  const R = S.expl.results;
  if (!R.doc || !R.rows.length) { el.innerHTML = stateHtml("empty", "Runs with the active query results (as-published values only)."); return; }
  const field = $("price-field").value;
  /* points with row references (volume bars read the row's traded_quantity) */
  const pts = [];
  let omitted = 0;
  R.rows.forEach((row) => {
    const date = businessDate(row);
    const value = toNumber(sv(row, field));
    if (date === null || value === null) { omitted += 1; return; }
    pts.push({ date, value, row });
  });
  el.innerHTML = (pts.length < 2
    ? stateHtml("empty", "Insufficient numeric points to plot (" + pts.length + " of " + R.rows.length + " rows; " + omitted + " rows omitted — non-numeric or dateless as-published values are never plotted as zero).")
    : lineChart(pts, $("price-volume").checked)) +
    (omitted ? '<div class="muted" style="font-size:10.5px;margin-top:4px">' + omitted + " of " + R.rows.length + " rows omitted from the plot (no valid business date, or non-numeric as-published value — never defaulted).</div>" : "");
}

function renderYearly() {
  const el = $("expl-yearly");
  const R = S.expl.results;
  if (!R.doc || !R.rows.length) { el.innerHTML = stateHtml("empty", "Derived from the active query results (documented, deterministic definitions)."); return; }
  const s = periodSummary(R.rows);
  const label = s.single_year ? "Yearly summary (" + s.year + ")" : "Period summary (" + (s.date_min || "?") + " – " + (s.date_max || "?") + ")";
  const row = (k, v) => "<div class=\"row\"><span class=\"k\">" + esc(k) + "</span><span class=\"v\">" + (v === null || v === undefined ? '<span class="chip unavail">unavailable</span>' : esc(String(v))) + "</span></div>";
  el.innerHTML = "<div class=\"muted\" style=\"font-size:11px;margin-bottom:6px\">" + label + " — over the served result set, in served order.</div><div class=\"coverage-list\">" +
    row("Records", fmtInt(s.records)) +
    row("Open (First)", s.open_first !== null ? fmtNum(s.open_first) : null) +
    row("Close (Last)", s.close_last !== null ? fmtNum(s.close_last) : null) +
    row("High (Year)", s.high !== null ? fmtNum(s.high) : null) +
    row("Low (Year)", s.low !== null ? fmtNum(s.low) : null) +
    row("Volume (Total)", s.volume_total !== null ? fmtNum(s.volume_total) + " (" + s.volume_count + "/" + s.records + " numeric)" : null) +
    row("Turnover (₹)", s.turnover_total !== null ? fmtNum(s.turnover_total) + " (" + s.turnover_count + "/" + s.records + " numeric)" : null) +
    "</div>";
}

async function loadQuality() {
  const Q = S.expl.quality;
  if (Q.loaded || Q.loading) return;
  Q.loading = true;
  $("expl-quality").innerHTML = stateHtml("loading", "Loading…");
  try {
    const doc = await api.query(MODE.Q8, {});
    Q.doc = doc.query;
    Q.loaded = true;
    renderQuality();
  } catch (err) {
    Q.error = err;
    setError($("expl-quality"), err);
  } finally {
    Q.loading = false;
  }
}

function renderQuality() {
  const Q = S.expl.quality;
  if (!Q.doc) return;
  const d = Q.doc;
  const census = d.flag_census || {};
  let html = "<div class=\"state-unavailable\" style=\"margin-bottom:10px\">The mockup's Reliable/Uncertain/Missing/Excluded buckets are unavailable — the serving contract does not supply that classification; the served Q8 census is shown instead (never reinterpreted).</div>";
  html += "<table class=\"census-table\"><thead><tr><th style=\"text-align:left;font-size:11px\">Flag census (rows carrying flag)</th><th style=\"text-align:right;font-size:11px\">count</th></tr></thead><tbody>";
  const names = Object.keys(census).sort();
  if (!names.length) html += "<tr><td class=\"muted\">no flags in the served census</td><td class=\"num\">0</td></tr>";
  for (const name of names) html += "<tr><td>" + esc(name) + "</td><td class=\"num\">" + fmtInt(census[name]) + "</td></tr>";
  html += "</tbody></table>";
  html += "<table class=\"census-table\" style=\"margin-top:8px\"><tbody>" +
    "<tr><td>Quarantined rows</td><td class=\"num\">" + fmtInt((d.quarantine || {}).count || 0) + "</td></tr>" +
    "<tr><td>Unresolved state</td><td class=\"num\">" + (d.unresolved && d.unresolved.present ? fmtInt(d.unresolved.record_count) + " records" : "absent") + "</td></tr>" +
    "<tr><td>Reconciliation records</td><td class=\"num\">" + fmtInt((d.reconciliation || {}).record_count || 0) + "</td></tr>" +
    "</tbody></table>";
  if (d.reconciliation && d.reconciliation.by_result) {
    html += "<div class=\"muted\" style=\"font-size:10.5px;margin-top:6px\">by result: " + Object.entries(d.reconciliation.by_result).sort().map(([k, v]) => esc(k) + " " + fmtInt(v)).join(" · ") + "</div>";
  }
  if (d.unresolved && d.unresolved.incremental_availability) html += '<div class="muted" style="font-size:10.5px;margin-top:6px">Unresolved records: baseline only; incremental evidence ' + esc(d.unresolved.incremental_availability) + '.</div>';
  if (d.reconciliation && d.reconciliation.incremental_availability) html += '<div class="muted" style="font-size:10.5px;margin-top:6px">Reconciliation records: baseline only; incremental evidence ' + esc(d.reconciliation.incremental_availability) + '.</div>';
  if (d.changed && d.changed.note) html += '<div class="muted" style="font-size:10.5px;margin-top:6px">' + esc(d.changed.note) + "</div>";
  $("expl-quality").innerHTML = html;
}

/* ============================ explorer: saved & history ============================ */

/* Load a saved definition into the Query Builder (D38 — the same definitions
   the Saved Queries tab runs; no separate path, no new semantics). */
async function loadSavedIntoBuilder(rec) {
  switchTab("builder");
  S.expl.builder.quick = null;
  if (rec.mode === MODE.Q2) {
    setBuilderMode(MODE.Q2);
    $("q-date-from").value = rec.params.date_from || "";
    $("q-date-to").value = rec.params.date_to || "";
  } else if (rec.mode === MODE.Q3) {
    setBuilderMode(MODE.Q3);
    $("q-symbol").value = rec.params.symbol || "";
    $("q-series").value = rec.params.series || "";
    $("q-year").value = rec.params.year !== undefined ? rec.params.year : "";
  } else if (rec.mode === MODE.Q4) {
    setBuilderMode(MODE.Q4);
    S.expl.builder.q4 = Object.entries(rec.params.filters || {}).map(([field, value]) => ({ field, value }));
    renderQ4Rows();
  } else {
    setBuilderMode(MODE.Q3);
  }
}

/* Saved-query sidebar (spec §6.9): compact D38 list with a New Query action;
   the selected entry is shown distinctly; empty state guides without
   suggesting unsupported capabilities; nothing is ever seeded. */
function renderSavedSidebar() {
  const Sv = S.expl.saved;
  const el = $("saved-sidebar-list");
  if (!el) return;
  if (Sv.error && !Sv.loaded) { setError(el, Sv.error); return; }
  if (!Sv.loaded && !Sv.error) { el.innerHTML = stateHtml("loading", "Loading…"); return; }
  if (!Sv.entries.length) {
    el.innerHTML = stateHtml("empty", "No saved queries yet — run a query in the Query Builder, then Save Query. Nothing is seeded.");
    return;
  }
  el.innerHTML = Sv.entries.map((e) => {
    const sel = Sv.selected === e.id ? " selected" : "";
    return '<div class="side-item' + sel + '" data-sid="' + esc(e.id) + '" title="' + esc(e.mode + " " + JSON.stringify(e.params)) + '">' +
      '<div class="side-id">' + esc(e.id) + "</div>" +
      '<div class="side-mode">' + esc(e.mode) + "</div></div>";
  }).join("");
  el.querySelectorAll(".side-item").forEach((item) => {
    item.addEventListener("click", async () => {
      const id = item.getAttribute("data-sid");
      const entry = Sv.entries.find((e) => e.id === id);
      if (!entry) return;
      try {
        Sv.selected = id;
        renderSavedSidebar();
        await loadSavedIntoBuilder(entry);
      } catch (err) {
        alert((err.check ? "[" + err.check + "] " : "") + err.message);
      }
    });
  });
}

async function loadSaved() {
  const Sv = S.expl.saved;
  if (Sv.loaded || Sv.loading) return;
  Sv.loading = true;
  $("expl-saved").innerHTML = stateHtml("loading", "Loading…");
  try {
    const doc = await api.savedList();
    Sv.entries = doc.entries;
    Sv.loaded = true;
    renderSaved();
  } catch (err) {
    Sv.error = err;
    setError($("expl-saved"), err);
    renderSavedSidebar();
  } finally {
    Sv.loading = false;
  }
}

function renderSaved() {
  const Sv = S.expl.saved;
  const el = $("expl-saved");
  renderSavedSidebar();
  $("saved-count").textContent = Sv.entries.length + " saved";
  if (!Sv.entries.length) {
    el.innerHTML = stateHtml("empty", "No saved queries. Save one from the Query Builder (Save Query) — definitions are persisted under D38 semantics; nothing is seeded.");
    return;
  }
  el.innerHTML = "<div class=\"store-list\">" + Sv.entries.map((e) =>
    "<div class=\"store-item\"><span class=\"sid\">" + esc(e.id) + "</span><span class=\"smode\">" + esc(e.mode) + "</span>" +
    "<span class=\"spams\" title=\"" + esc(JSON.stringify(e.params, null, 0)) + "\">" + esc(JSON.stringify(e.params)) + "</span>" +
    '<span class="sactions">' +
    '<button class="btn btn-small" data-act="run" data-id="' + esc(e.id) + '">Run</button>' +
    '<button class="btn btn-small" data-act="update" data-id="' + esc(e.id) + '">Update</button>' +
    '<button class="btn btn-small btn-danger" data-act="delete" data-id="' + esc(e.id) + '">Delete</button>' +
    "</span></div>"
  ).join("") + "</div>";
  el.querySelectorAll("button[data-act]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-id");
      const act = btn.getAttribute("data-act");
      try {
        if (act === "run") {
          S.expl.saved.selected = id;
          renderSavedSidebar();
          S.expl.busy = true;
          $("expl-results").innerHTML = stateHtml("loading", "Executing saved query " + id + "…");
          const doc = await api.savedRun(id);
          const rows = (doc.query.rows || doc.query.records || []).slice();
          S.expl.results = {
            doc: doc.query, rows,
            meta: { mode: doc.query.query || id, params: null },
            page: 0, perPage: S.expl.results.perPage, selected: -1,
            banner: "saved: " + id,
          };
          S.expl.inspector = { loading: false, error: null, detail: null, related: null, relatedError: null };
          renderResults();
          renderInspector();
          renderPriceChart();
          renderYearly();
        } else if (act === "update") {
          const doc = await api.savedShow(id);
          S.expl.saved.selected = id;
          renderSavedSidebar();
          await loadSavedIntoBuilder(doc.entry);
        } else if (act === "delete") {
          if (!window.confirm("Delete saved query " + id + "? (the only removal path — D37-DEC §6.3)")) return;
          await api.savedDelete(id);
          Sv.loaded = false;
          Sv.entries = [];
          Sv.selected = null;
          await loadSaved();
        }
      } catch (err) {
        alert((err.check ? "[" + err.check + "] " : "") + err.message);
      } finally {
        S.expl.busy = false;
      }
    });
  });
}

async function loadHistory() {
  const H = S.expl.history;
  if (H.loaded || H.loading) return;
  H.loading = true;
  $("expl-history").innerHTML = stateHtml("loading", "Loading…");
  try {
    const doc = await api.historyList();
    H.entries = doc.entries;
    H.loaded = true;
    renderHistory();
  } catch (err) {
    H.error = err;
    setError($("expl-history"), err);
  } finally {
    H.loading = false;
  }
}

function renderHistory() {
  const H = S.expl.history;
  const el = $("expl-history");
  if (!H.entries.length) {
    el.innerHTML = stateHtml("empty", "No recorded executions. History entries are created only by the explicit \"Record current query execution\" action below (D39; C2(a): ordinary runs never write history).");
    return;
  }
  el.innerHTML = "<div class=\"store-list\">" + H.entries.map((e) =>
    "<div class=\"store-item hist-entry\"><span class=\"sid\">#" + e.seq + "</span>" +
    '<span class="outcome ' + (e.outcome === "success" ? "success" : "error") + '">' + (e.outcome === "success" ? "success" : "error" + (e.check ? " · " + esc(e.check) : "")) + "</span>" +
    "<span class=\"smode\">" + esc(e.mode) + "</span><span class=\"spams\">" + esc(JSON.stringify(e.params)) + "</span>" +
    '<span class="sactions"><button class="btn btn-small" data-hact="show" data-seq="' + e.seq + '">Show</button>' +
    '<button class="btn btn-small btn-danger" data-hact="delete" data-seq="' + e.seq + '">Delete</button></span></div>'
  ).join("") + "</div>";
  el.querySelectorAll("button[data-hact]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const seq = btn.getAttribute("data-seq");
      try {
        if (btn.getAttribute("data-hact") === "show") {
          const doc = await api.historyShow(seq);
          H.detail = doc.entry;
          $("hist-detail").innerHTML = '<div class="hist-detail">' + esc(JSON.stringify(doc.entry, null, 2)) + "</div>";
        } else {
          if (!window.confirm("Delete history entry #" + seq + "?")) return;
          await api.historyDelete(seq);
          H.loaded = false;
          H.entries = [];
          H.detail = null;
          $("hist-detail").innerHTML = "";
          await loadHistory();
        }
      } catch (err) {
        alert((err.check ? "[" + err.check + "] " : "") + err.message);
      }
    });
  });
}

async function recordCurrentQuery() {
  const b = S.expl.builder;
  const built = builderParams();
  if (built.error) { alert("The current query is invalid: " + built.error); return; }
  try {
    const doc = await api.historyRecord({ mode: b.mode, params: built.params });
    alert("Recorded execution #" + doc.entry.seq + " — outcome: " + doc.entry.outcome + (doc.entry.check ? " (" + doc.entry.check + ")" : ""));
    S.expl.history.loaded = false;
    S.expl.history.entries = [];
    await loadHistory();
  } catch (err) {
    alert((err.check ? "[" + err.check + "] " : "") + err.message);
  }
}

/* ============================ navigation ============================ */

function switchPage(page) {
  S.page = page;
  document.querySelectorAll(".nav-item[data-page]").forEach((b) => {
    if (b.getAttribute("data-page") === page) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  $("page-dashboard").hidden = page !== "dashboard";
  $("page-explorer").hidden = page !== "explorer";
  if (page === "dashboard") loadDashboard();
  if (page === "explorer") {
    loadQuality();
    if (!S.dash.loaded && !S.dash.loading) loadDashboard();
    renderDatasetSummary();
    if (!S.expl.saved.loaded && !S.expl.saved.loading && !S.expl.saved.error) loadSaved();
  }
}

function renderDatasetSummary() {
  const el = $("expl-dataset");
  if (S.dash.loading) { el.innerHTML = stateHtml("loading", "Loading dataset summary…"); return; }
  if (S.dash.q1Error) {
    el.innerHTML = stateHtml("error", {check: S.dash.q1Error.check || "", detail: S.dash.q1Error.message}) +
      '<button class="btn btn-small" id="dataset-retry">Retry dataset summary</button>';
    $("dataset-retry").addEventListener("click", () => { loadDashboard(); renderDatasetSummary(); });
    return;
  }
  if (!S.dash.q1) { el.innerHTML = stateHtml("unavailable", "Dataset summary unavailable."); return; }
  S.expl.datasetLoaded = true;
  const cov = coverageSummary(
    S.dash.q1 ? S.dash.q1.partitions : [],
    S.dash.q6 && S.dash.q6.calendar_present ? S.dash.q6.records : [],
    S.dash.q9 ? S.dash.q9.archives : [],
    S.dash.q1 ? S.dash.q1.summary : null
  );
  el.innerHTML = kvRow("Dataset", "single qualified package (no dataset selector — one authorized dataset)") +
    kvRow("Partitions", cov.partition_years.length ? cov.partition_years.length + " years" : "unavailable") +
    kvRow("Total rows", cov.total_rows) +
    kvRow("Last updated", null) +
    '<div class="muted" style="font-size:10px;margin-top:3px">the serving contract publishes no last-updated timestamp (never fabricated)</div>';
}

function switchTab(tab) {
  S.expl.tab = tab;
  document.querySelectorAll(".tab[data-tab]").forEach((t) => {
    t.setAttribute("aria-selected", t.getAttribute("data-tab") === tab ? "true" : "false");
  });
  for (const name of ["builder", "saved", "history"]) {
    $("tabpane-" + name).hidden = name !== tab;
  }
  if (tab === "saved") loadSaved();
  if (tab === "history") loadHistory();
}

/* ============================ init ============================ */

function wire() {
  document.querySelectorAll(".nav-item[data-page]").forEach((b) => {
    b.addEventListener("click", () => switchPage(b.getAttribute("data-page")));
  });
  document.querySelectorAll(".tab[data-tab]").forEach((t) => {
    t.addEventListener("click", () => { if (!t.disabled) switchTab(t.getAttribute("data-tab")); });
  });
  $("q-mode").addEventListener("change", () => setBuilderMode($("q-mode").value));
  $("q4-add").addEventListener("click", () => { S.expl.builder.q4.push({ field: "series", value: "" }); S.expl.builder.quick = null; renderQ4Rows(); renderQuickPills(); });
  $("btn-run").addEventListener("click", runQuery);
  $("btn-reset").addEventListener("click", resetBuilder);
  $("btn-save").addEventListener("click", saveCurrentQuery);
  $("archive-search").addEventListener("input", (e) => { S.dash.archiveSearch = e.target.value; renderArchives(); });
  $("archive-segment").addEventListener("change", (e) => { S.dash.archiveSegment = e.target.value; S.dash.archiveSelection = -1; renderArchives(); renderArchiveDetail(); });
  $("archive-year").addEventListener("change", (e) => { S.dash.archiveYear = e.target.value; S.dash.archiveSelection = -1; renderArchives(); renderArchiveDetail(); });
  $("results-perpage").addEventListener("change", (e) => { S.expl.results.perPage = parseInt(e.target.value, 10); S.expl.results.page = 0; renderResults(); });
  $("results-prev").addEventListener("click", () => { S.expl.results.page = Math.max(0, S.expl.results.page - 1); renderResults(); });
  $("results-next").addEventListener("click", () => { S.expl.results.page += 1; renderResults(); });
  $("ins-prev").addEventListener("click", () => selectRow(S.expl.results.selected - 1));
  $("ins-next").addEventListener("click", () => selectRow(S.expl.results.selected + 1));
  $("price-field").addEventListener("change", renderPriceChart);
  $("price-volume").addEventListener("change", renderPriceChart);
  $("hist-record").addEventListener("click", recordCurrentQuery);
  $("saved-new").addEventListener("click", () => {
    S.expl.saved.selected = null;
    switchTab("builder");
    const f = $("q-symbol");
    if (f && f.focus) f.focus();
  });
}

async function init() {
  wire();
  setBuilderMode(MODE.Q3);
  renderQ4Rows();
  try {
    S.server = await api.status();
    setService(true, null);
  } catch (err) {
    setService(false, err);
  }
  switchPage("dashboard");
}

document.addEventListener("DOMContentLoaded", init);
