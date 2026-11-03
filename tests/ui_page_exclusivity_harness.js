"use strict";
/* Focused page-exclusivity regression harness (TASK67, F-N1).
 *
 * Loads the real src/ui/static/app.js in a sandboxed vm context with DOM
 * stubs that track `hidden` and nav `aria-current`, drives switchPage()
 * both ways, and asserts the JS half of the page-exclusivity contract:
 *   - exactly one page section is visible at a time (never both, never none);
 *   - the nav aria-current tracks the displayed page;
 *   - round-trips are stable.
 * The CSS half of the F-N1 fix (`.page[hidden] { display: none }` in
 * app.css, which overrides `.page { display: flex }`) is verified
 * structurally by tests/test_ui_page_exclusivity.py; together the two
 * suites pin the contract end to end.
 */

const fs = require("fs");
const vm = require("vm");

const appPath = process.argv[2];
if (!appPath) {
  console.error("usage: node ui_page_exclusivity_harness.js <path-to-app.js>");
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

/* ---------------- minimal serving responses (all-ok; nothing may reject) ---------------- */

const STATUS_DOC = { result: "pass", service: "i4-ui/1.0", package_run_id: "i4-fixture", m2: true, repo_root: null, query_modes: ["Q1-dataset"] };
const Q1_DOC = { result: "pass", query: { summary: { row_count: 100, instrument_pairs: 2 }, partitions: [{ partition: "p", year: "2020", row_count: 100, members: 1 }] } };
const Q6_DOC = { result: "pass", query: { calendar_present: true, record_count: 2, records: [{ trade_date: "2020-01-01" }, { trade_date: "2020-01-02" }] } };
const Q8_DOC = { result: "pass", query: { flag_census: {}, quarantine: { count: 0 }, unresolved: { present: false, record_count: 0, records: [] }, reconciliation: { record_count: 0, by_result: {}, by_tier: {} }, changed: { present: false, findings: [], note: "absent" } } };
const Q9_DOC = { result: "pass", query: { summary: { archive_count: 1, d01_inventory: { present: true } }, archives: [{ member_name: "a.csv.gz", date_from_filename: "2020-01-01", member_size_bytes: 10, data_lines: 1, d01: { series_counts: { EQ: 1 } } }] } };
const Q10_DOC = { result: "pass", query: { package: { run_identity: { run_id: "i4-fixture" }, engine_identity: { tool_name: "nse_engine", tool_version: "1" }, corpus: { archive_count: 1 }, manifests: { file_count: 1, total_bytes: 10 } } } };

function makeContext() {
  const elements = {};
  function makeEl(id) {
    const el = {
      id: id,
      innerHTML: "",
      textContent: "",
      value: "",
      hidden: false,
      className: "",
      attrs: {},
      setAttribute(k, v) { el.attrs[k] = v; },
      removeAttribute(k) { delete el.attrs[k]; },
      getAttribute(k) { return k in el.attrs ? el.attrs[k] : null; },
      addEventListener() {},
      querySelectorAll: () => [],
      focus() {},
      scrollIntoView() {},
    };
    return el;
  }
  const navDash = makeEl("nav-dashboard");
  navDash.attrs["data-page"] = "dashboard";
  const navExpl = makeEl("nav-explorer");
  navExpl.attrs["data-page"] = "explorer";
  const document = {
    getElementById: (id) => elements[id] || (elements[id] = makeEl(id)),
    querySelectorAll: (sel) => (sel === ".nav-item[data-page]" ? [navDash, navExpl] : []),
    addEventListener: () => {},
  };
  const fetchStub = async (path, opts) => {
    const o = opts || {};
    if (o.method === "GET" && path === "/api/status") {
      return { ok: true, status: 200, json: async () => STATUS_DOC };
    }
    if (path === "/api/query") {
      const body = o.body ? JSON.parse(o.body) : null;
      const doc = {
        "Q1-dataset": Q1_DOC,
        "Q6-calendar": Q6_DOC,
        "Q8-data-quality": Q8_DOC,
        "Q9-archive-inventory": Q9_DOC,
        "Q10-qualification": Q10_DOC,
      }[body && body.mode];
      if (!doc) throw new Error("unstubbed query mode " + (body && body.mode));
      return { ok: true, status: 200, json: async () => doc };
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
  return { ctx, elements, navDash, navExpl };
}

function dashState(elements, navDash, navExpl) {
  return {
    dashHidden: elements["page-dashboard"].hidden,
    explHidden: elements["page-explorer"].hidden,
    dashAria: navDash.getAttribute("aria-current"),
    explAria: navExpl.getAttribute("aria-current"),
  };
}

function assertExclusive(name, st) {
  const visible = [st.dashHidden === false, st.explHidden === false];
  check(
    name + ": exactly one page visible (never both, never none)",
    visible.filter(Boolean).length === 1,
    JSON.stringify(st)
  );
}

async function main() {
  const { ctx, elements, navDash, navExpl } = makeContext();

  /* initial app state: dashboard active (index.html: dashboard unhidden, explorer hidden) */
  vm.runInContext('switchPage("dashboard")', ctx);
  let st = dashState(elements, navDash, navExpl);
  check("S1 dashboard selected: dashboard visible", st.dashHidden === false, JSON.stringify(st));
  check("S1 dashboard selected: explorer hidden", st.explHidden === true, JSON.stringify(st));
  check("S1 nav: dashboard aria-current", st.dashAria === "page", JSON.stringify(st));
  check("S1 nav: explorer not current", st.explAria === null, JSON.stringify(st));
  assertExclusive("S1", st);

  /* switch to explorer */
  vm.runInContext('switchPage("explorer")', ctx);
  st = dashState(elements, navDash, navExpl);
  check("S2 explorer selected: explorer visible", st.explHidden === false, JSON.stringify(st));
  check("S2 explorer selected: dashboard hidden", st.dashHidden === true, JSON.stringify(st));
  check("S2 nav: explorer aria-current", st.explAria === "page", JSON.stringify(st));
  check("S2 nav: dashboard not current", st.dashAria === null, JSON.stringify(st));
  assertExclusive("S2", st);

  /* round-trip back */
  vm.runInContext('switchPage("dashboard")', ctx);
  st = dashState(elements, navDash, navExpl);
  check("S3 round-trip: dashboard visible again", st.dashHidden === false && st.explHidden === true, JSON.stringify(st));
  check("S3 round-trip: nav restored", st.dashAria === "page" && st.explAria === null, JSON.stringify(st));
  assertExclusive("S3", st);

  console.log(failures === 0 ? "HARNESS OK" : "HARNESS FAILED (" + failures + " failures)");
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("HARNESS ERROR: " + (e && e.stack ? e.stack : e));
  process.exit(3);
});
