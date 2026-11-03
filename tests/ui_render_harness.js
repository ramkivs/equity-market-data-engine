"use strict";
/* Focused rendering tests for the Dashboard error-containment contract
 * (TASK65 Phase 3; D23 §17(b)). Loads the real src/ui/static/app.js in a
 * sandboxed vm context with DOM/fetch stubs, drives loadDashboard() under
 * partial-failure scenarios, and asserts per-region rendering:
 *
 *   - a failed query's error is visible in the region(s) that depend on it;
 *   - unrelated successful regions still render from their own responses;
 *   - nothing is fabricated: a value whose source failed renders as
 *     unavailable/error, never as zero, success, or an empty result;
 *   - a fully successful load renders without any error state.
 *
 * The query documents are minimal but valid shapes of the Q1/Q6/Q8/Q9/Q10
 * serving responses (synthetic — never the qualified M2 baseline).
 */

const fs = require("fs");
const vm = require("vm");

const appPath = process.argv[2];
if (!appPath) {
  console.error("usage: node ui_render_harness.js <path-to-app.js>");
  process.exit(2);
}
const src = fs.readFileSync(appPath, "utf8");

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log("PASS " + name);
  else {
    failures++;
    console.log("FAIL " + name + (detail ? " — " + detail : ""));
  }
}
function count(haystack, needle) {
  let n = 0, i = 0;
  while ((i = haystack.indexOf(needle, i)) !== -1) n++, i += needle.length;
  return n;
}

/* ---------------- stubbed DOM + fetch ---------------- */

function makeContext(handlers) {
  const elements = {};
  /* ids the harness asserts on, even when the app never touches them */
  ["sb-state", "sb-run", "sb-engine", "sb-archives", "sb-rows", "tb-service"].forEach((id) => makeEl0(id));
  function makeEl0(id) {
    elements[id] = elements[id] || makeEl(id);
  }
  function makeEl(id) {
    return {
      id: id,
      innerHTML: "",
      textContent: "",
      value: "",
      hidden: false,
      className: "",
      addEventListener(type, fn) { this["on" + type] = fn; },
      setAttribute() {},
      removeAttribute() {},
      querySelectorAll: () => [],
      focus() {},
      scrollIntoView() {},
    };
  }
  const document = {
    getElementById: (id) => elements[id] || (elements[id] = makeEl(id)),
    querySelectorAll: () => [],
    addEventListener: () => {},
  };
  function respond(h) {
    if (h && h.err) {
      return {
        ok: false,
        status: h.status || 409,
        json: async () => ({ result: "fail", check: h.err.check, detail: h.err.message }),
      };
    }
    return { ok: true, status: 200, json: async () => h };
  }
  const fetchStub = async (path, opts) => {
    const o = opts || {};
    const body = o.body ? JSON.parse(o.body) : null;
    if (o.method === "GET" && path === "/api/status") return respond(handlers.status);
    if (path === "/api/query") {
      const h = handlers.query[body && body.mode];
      if (!h) throw new Error("unstubbed query mode " + (body && body.mode));
      return respond(typeof h === "function" ? await h() : h);
    }
    throw new Error("unstubbed fetch " + path);
  };
  const ctx = {
    document: document,
    window: { confirm: () => true, prompt: () => null },
    fetch: fetchStub,
    alert: () => {},
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx, { filename: "app.js" });
  return { ctx, elements };
}

/* ---------------- synthetic serving responses ---------------- */

const Q1_DOC = {
  result: "pass",
  query: {
    summary: { row_count: 5689949, instrument_pairs: 4321 },
    partitions: [
      { partition: "legacy13_2016", year: "2016", row_count: 116723, members: 69 },
      { partition: "legacy13_2017", year: "2017", row_count: 435547, members: 247 },
    ],
  },
};
const Q6_DOC = {
  result: "pass",
  query: {
    calendar_present: true,
    record_count: 2462,
    records: [{ trade_date: "2016-01-04" }, { trade_date: "2026-09-18" }],
  },
};
const Q8_DOC = {
  result: "pass",
  query: {
    flag_census: { "st-anomaly": 3 },
    quarantine: { count: 0 },
    unresolved: { present: true, record_count: 11, records: [] },
    reconciliation: { record_count: 4, by_result: { match: 4 }, by_tier: { E: 4 } },
    changed: { present: false, findings: [], note: "absent in the M2-only release" },
  },
};
const Q9_DOC = {
  result: "pass",
  query: {
    summary: { archive_count: 2462, d01_inventory: { present: true } },
    archives: [
      {
        member_name: "NSE_EQ_20160101_RELIANCE.csv.gz",
        date_from_filename: "2016-01-01",
        member_size_bytes: 1200000,
        data_lines: 2341,
        d01: { series_counts: { EQ: 10 } },
      },
      {
        member_name: "NSE_FO_20160101_NIFTY.csv.gz",
        date_from_filename: "2016-01-01",
        member_size_bytes: 2800000,
        data_lines: 5421,
        d01: { series_counts: { FO: 5 } },
      },
    ],
  },
};
const Q10_DOC = {
  result: "pass",
  query: {
    package: {
      run_identity: { run_id: "i4-fixture" },
      engine_identity: { tool_name: "nse_engine", tool_version: "14" },
      corpus: { archive_count: 2462 },
      manifests: { file_count: 4948, total_bytes: 21119807344 },
    },
  },
};
const STATUS_DOC = {
  result: "pass",
  service: "i4-ui/1.0",
  package_run_id: "i4-fixture",
  m2: true,
  repo_root: null,
  query_modes: ["Q1-dataset"],
};
const Q8_ERR = { check: "unresolved-scan", message: "unresolved-scan: w2/unresolved.jsonl line 11 without a state" };
const Q1_ERR = { check: "query-input", message: "query-input: synthetic fixture failure" };
const err = (e) => ({ err: e });

function allOk() {
  return {
    status: STATUS_DOC,
    query: {
      "Q1-dataset": Q1_DOC,
      "Q6-calendar": Q6_DOC,
      "Q8-data-quality": Q8_DOC,
      "Q9-archive-inventory": Q9_DOC,
      "Q10-qualification": Q10_DOC,
    },
  };
}

/* ---------------- scenarios ---------------- */

async function main() {
  /* A: every query fails — every dependent region shows the error; no data
     is rendered anywhere; no KPI card shows a fabricated value */
  {
    const { ctx, elements } = makeContext({
      status: STATUS_DOC,
      query: {
        "Q1-dataset": err(Q1_ERR),
        "Q6-calendar": err({ check: "c6", message: "m6" }),
        "Q8-data-quality": err(Q8_ERR),
        "Q9-archive-inventory": err({ check: "q9c", message: "m9" }),
        "Q10-qualification": err({ check: "q10c", message: "m10" }),
      },
    });
    await vm.runInContext("loadDashboard()", ctx);
    const el = elements;
    check("A1 rows-year error region", el["dash-rows-year"].innerHTML.includes("state-error"));
    check("A2 segments error region", el["dash-segments"].innerHTML.includes("state-error"));
    check("A3 coverage error region", el["dash-coverage"].innerHTML.includes("state-error"));
    check("A4 archives error region", el["dash-archives"].innerHTML.includes("state-error"));
    check("A5 run summary error region", el["dash-run"].innerHTML.includes("state-error"));
    const kpis = el["dash-kpis"].innerHTML;
    check("A6 KPI row still renders (5 cards)", count(kpis, 'class="kpi"') === 5, "cards=" + count(kpis, 'class="kpi"'));
    check("A7 no KPI card shows a data value", !/kpi-value">[^u]/.test(kpis) || !/(kpi-value">)\d/.test(kpis));
    check("A8 failures named per query", kpis.includes("Q1 failed") || el["dash-run"].innerHTML.includes("Q1 · query-input"));
    check("A9 no data leaked into rows-year", !el["dash-rows-year"].innerHTML.includes("5,689,949"));
    check("A10 status bar values untouched", el["sb-engine"].textContent === "" && el["sb-rows"].textContent === "");
    check("A11 failed load stays retryable", vm.runInContext("S.dash.loaded", ctx) === false);
  }

  /* B: only Q8 fails (the TASK64 defect shape) — every other region renders
     from its own successful response; the Q8 error is visible in the run
     summary and the Q8-dependent KPI card shows unavailable, not a value */
  {
    const h = allOk();
    h.query["Q8-data-quality"] = err(Q8_ERR);
    const { ctx, elements } = makeContext(h);
    await vm.runInContext("loadDashboard()", ctx);
    const el = elements;
    check("B1 rows-year renders the chart", el["dash-rows-year"].innerHTML.includes("<svg") && !el["dash-rows-year"].innerHTML.includes("state-error"));
    check("B2 segments render from Q9", el["dash-segments"].innerHTML.includes("seg-legend"));
    const cov = el["dash-coverage"].innerHTML;
    /* coverage rows render raw served values (Total rows is not comma-formatted by design) */
    check("B3 coverage renders values from successful sources", cov.includes("5689949") && cov.includes("2016-01-04") && cov.includes("2026-09-18"));
    check("B4 coverage has no error (its sources succeeded)", !cov.includes("state-error"));
    check("B5 archive table renders from Q9", el["dash-archives"].innerHTML.includes("<table"));
    const kpis = el["dash-kpis"].innerHTML;
    check("B6 KPI values render from Q1/Q6/Q9", kpis.includes("2,462") && kpis.includes("5,689,949"));
    check("B7 Errors card is unavailable with the Q8 failure named", kpis.includes("unavailable — Q8 failed") && kpis.includes("unresolved-scan"));
    check("B8 Identity card remains authority-driven unavailable", kpis.includes("Identity Records"));
    check("B9 run summary renders with the Q10 data", el["dash-run"].innerHTML.includes("i4-fixture"));
    check("B10 run summary names the Q8 failure", el["dash-run"].innerHTML.includes("Q8 · unresolved-scan"));
    check("B11 status bar populated from Q10/Q1", el["sb-engine"].textContent === "engine: nse_engine 14" && el["sb-archives"].textContent === "archives: 2,462" && el["sb-rows"].textContent === "rows: 5,689,949");
    /* the load keeps its failure record: retryable until Q8 succeeds */
    check("B12 load stays retryable with the Q8 failure recorded", JSON.stringify(vm.runInContext("({loaded: S.dash.loaded, errors: S.dash.errors.map((e) => e.name)})", ctx)) === JSON.stringify({ loaded: false, errors: ["q8"] }));
  }

  /* C: Q1 fails — its region errors; coverage's Q1-derived values are
     explicitly unavailable (never zero); unrelated Q9 regions still render */
  {
    const h = allOk();
    h.query["Q1-dataset"] = err(Q1_ERR);
    const { ctx, elements } = makeContext(h);
    await vm.runInContext("loadDashboard()", ctx);
    const el = elements;
    check("C1 rows-year error region", el["dash-rows-year"].innerHTML.includes("state-error") && el["dash-rows-year"].innerHTML.includes("query-input"));
    const cov = el["dash-coverage"].innerHTML;
    check("C2 coverage Total rows is unavailable, not zero", cov.includes("Total rows") && !cov.includes("5,689,949") && cov.includes("chip unavail"));
    check("C3 no partition-years line without Q1", !cov.includes("partition years"));
    check("C4 coverage names the Q1 failure", cov.includes("Q1 · query-input"));
    check("C5 coverage Q6/Q9 values still render", cov.includes("2016-01-04") && cov.includes("Total archives"));
    check("C6 Canonical Rows card unavailable with Q1 named", el["dash-kpis"].innerHTML.includes("unavailable — Q1 failed"));
    check("C7 segments still render from Q9", el["dash-segments"].innerHTML.includes("seg-legend"));
    check("C8 archive table still renders from Q9", el["dash-archives"].innerHTML.includes("<table"));
    check("C9 status bar rows untouched", el["sb-rows"].textContent === "");
  }

  /* D: everything succeeds — no error state anywhere */
  {
    const { ctx, elements } = makeContext(allOk());
    await vm.runInContext("loadDashboard()", ctx);
    const el = elements;
    const anyError = Object.keys(el).some((id) => el[id].innerHTML.includes("state-error"));
    check("D1 no error state anywhere", !anyError);
    const kpis = el["dash-kpis"].innerHTML;
    check("D2 all five KPI cards render", count(kpis, 'class="kpi"') === 5);
    check("D3 Errors card shows the served flag total", /kpi-value">3</.test(kpis));
    check("D4 chart + table + coverage render", el["dash-rows-year"].innerHTML.includes("<svg") && el["dash-archives"].innerHTML.includes("<table") && el["dash-coverage"].innerHTML.includes("partition years"));
    check("D5 load complete", vm.runInContext("S.dash.loaded", ctx) === true);
  }

  /* E: the adapter is unreachable — every query fails together, no region
     renders data */
  {
    const { ctx, elements } = makeContext({ status: err({ check: "adapter", message: "adapter unreachable" }), query: {} });
    await vm.runInContext("loadDashboard()", ctx);
    const el = elements;
    check("E1 all four regions error", ["dash-rows-year", "dash-segments", "dash-coverage", "dash-archives"].every((id) => el[id].innerHTML.includes("state-error")));
    check("E2 no data rendered", !el["dash-rows-year"].innerHTML.includes("5,689,949"));
  }

  /* B4: real inspector markup, escaping, and async Explorer summary. */
  {
    const handlers = allOk();
    const { ctx, elements: el } = makeContext(handlers);
    vm.runInContext(`S.expl.results.selected = 0; S.expl.results.rows = [{}];
      S.expl.inspector.detail = {row: {source_values: {listing_symbol: '<img src=x>'}, flags: [], units_provenance_note: '<actual note>'}, archive: {}};
      renderInspector()`, ctx);
    let html = el["expl-inspector"].innerHTML;
    check("B4 inspector chip markup is live", html.includes('<span class="chip unavail">') && html.includes('<span class="chip ok">'));
    check("B4 source and units escaped", html.includes('&lt;img src=x&gt;') && html.includes('&lt;actual note&gt;') && !html.includes('<img src=x>'));
    vm.runInContext("S.expl.inspector.detail.row.units_provenance_note = null; renderInspector()", ctx);
    check("B4 missing units unavailable", el["expl-inspector"].innerHTML.includes('Units and provenance</td><td class="v "><span class="chip unavail">unavailable'));
    check("B4 EQ legacy preset no segment", vm.runInContext('JSON.stringify(quickFilterParams("EQ (all)"))', ctx).includes('"series":"EQ"}') );
    vm.runInContext(`S.page = 'explorer'; S.dash.loading = true; renderDatasetSummary()`, ctx);
    check("B4 summary loading", el["expl-dataset"].innerHTML.includes('state-loading'));
    vm.runInContext(`S.dash.loading = false; S.dash.q1Error = {check:'Q1', message:'bad <error>'}; renderDatasetSummary()`, ctx);
    check("B4 summary error and retry", el["expl-dataset"].innerHTML.includes('&lt;error&gt;') && el["expl-dataset"].innerHTML.includes('dataset-retry'));
    el["dataset-retry"].onclick();
    check("B4 retry loading", el["expl-dataset"].innerHTML.includes('state-loading'));
    await new Promise((resolve) => setTimeout(resolve, 0));
    check("B4 retry updates explorer", !el["expl-dataset"].innerHTML.includes('state-error') && !el["expl-dataset"].innerHTML.includes('state-loading'));
    vm.runInContext(`S.dash.q9 = {archives:[{sequence:1, member_name:'a', d01:{series_counts:{'EQ':1, '<img src=x>':1}}}]}; S.dash.q9Error = null; renderArchives()`, ctx);
    check("B4 archive series escaped", el["dash-archives"].innerHTML.includes('&lt;img src=x&gt;') && !el["dash-archives"].innerHTML.includes('<img src=x>'));
    check("B4 archive options individual", el["archive-segment"].innerHTML.includes('>EQ</option>') && el["archive-segment"].innerHTML.includes('&lt;img src=x&gt;'));
  }

  {
    const handlers = allOk();
    const q1 = handlers.query["Q1-dataset"];
    let release;
    handlers.query["Q1-dataset"] = () => new Promise((resolve) => { release = resolve; });
    const {ctx, elements: el} = makeContext(handlers);
    vm.runInContext("S.page = 'explorer'", ctx);
    const loading = vm.runInContext("loadDashboard()", ctx);
    vm.runInContext("renderDatasetSummary()", ctx);
    check("B4 delayed Q1 shows loading", el["expl-dataset"].innerHTML.includes('state-loading'));
    await new Promise((resolve) => setTimeout(resolve, 0));
    release(q1);
    await loading;
    check("B4 delayed Q1 completes Explorer", !el["expl-dataset"].innerHTML.includes('state-loading') && el["expl-dataset"].innerHTML.includes('Total rows'));
  }
  {
    const handlers = allOk();
    const q1 = handlers.query["Q1-dataset"];
    handlers.query["Q1-dataset"] = err({check:'Q1', message:'failed'});
    const {ctx, elements: el} = makeContext(handlers);
    vm.runInContext("S.page = 'explorer'", ctx);
    await vm.runInContext("loadDashboard()", ctx);
    check("B4 real failed Q1 shows retry", el["expl-dataset"].innerHTML.includes('dataset-retry'));
    handlers.query["Q1-dataset"] = q1;
    el["dataset-retry"].onclick();
    await new Promise((resolve) => setTimeout(resolve, 0));
    check("B4 real failure retry recovers", el["expl-dataset"].innerHTML.includes('Total rows'));
  }
  {
    const {ctx} = makeContext(allOk());
    vm.runInContext(`S.dash.q9 = {archives:[{sequence:1, member_name:'a', d01:{series_counts:{EQ:1}}}]};
      S.dash.archiveSelection = 0;
      switchPage = () => {}; setBuilderMode = () => {}; renderQ4Rows = () => {}; renderArchiveDetail();
      document.getElementById('adv-canonical').onclick();`, ctx);
    check("B4 archive action uses series", vm.runInContext("S.expl.builder.q4[0].field === 'series' && S.expl.builder.q4[0].value === 'EQ'", ctx));
  }

  console.log(failures === 0 ? "HARNESS OK" : "HARNESS FAILED (" + failures + " failures)");
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("HARNESS ERROR: " + (e && e.stack ? e.stack : e));
  process.exit(3);
});
