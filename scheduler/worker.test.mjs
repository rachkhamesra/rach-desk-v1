// Run with:  node --test scheduler/worker.test.mjs      (no packages needed)
import test from "node:test";
import assert from "node:assert/strict";
import { plan, dispatch } from "./worker.mjs";

const ist = (iso) => Date.parse(iso + "+05:30");                 // an IST wall-clock time to epoch milliseconds
// 2026-11-02 is a Monday, 2026-11-07 a Saturday, 2026-11-08 a Sunday.

test("morning: 06:00 to 07:00 IST every day, nothing before or after", () => {
  for (const d of ["2026-11-02", "2026-11-04", "2026-11-07", "2026-11-08"]) {
    for (const t of ["06:00", "06:30", "07:00"]) assert.equal(plan(ist(`${d}T${t}:00`)), "daily", `${d} ${t}`);
    for (const t of ["05:30", "07:30", "08:00", "09:30", "12:00"]) assert.equal(plan(ist(`${d}T${t}:00`)), null, `${d} ${t}`);
  }
});

test("weekday evening: 19:00 to 22:00 IST every 30 minutes, nothing after", () => {
  for (const d of ["2026-11-02", "2026-11-03", "2026-11-06"]) {
    for (const t of ["19:00", "19:30", "20:00", "21:00", "21:30", "22:00"]) assert.equal(plan(ist(`${d}T${t}:00`)), "retry", `${d} ${t}`);
    for (const t of ["18:30", "22:30", "23:30"]) assert.equal(plan(ist(`${d}T${t}:00`)), null, `${d} ${t}`);
  }
  for (const t of ["2026-11-03T00:00", "2026-11-03T00:30", "2026-11-03T01:00"]) assert.equal(plan(ist(t + ":00")), null, t);   // no after-midnight runs
});

test("weekend evening: only the 20:00 backup", () => {
  for (const d of ["2026-11-07", "2026-11-08"]) {
    assert.equal(plan(ist(`${d}T20:00:00`)), "daily", d);
    for (const t of ["19:00", "19:30", "20:30", "21:00", "22:00"]) assert.equal(plan(ist(`${d}T${t}:00`)), null, `${d} ${t}`);
  }
});

test("over a whole week the number of starts is as designed", () => {
  const week = ist("2026-11-02T00:00:00");
  const counts = {};
  for (let i = 0; i < 7 * 48; i++) { const m = plan(week + i * 30 * 60000); if (m) counts[m] = (counts[m] || 0) + 1; }
  assert.equal(counts.always, undefined);                         // "always" is only for starting a build by hand
  assert.equal(counts.daily, 7 * 3 + 2);                          // three morning slots every day, plus the weekend evening backup
  assert.equal(counts.retry, 5 * 7);                              // seven evening slots on each weekday
});

test("every moment the Worker acts on is covered by a cron trigger in wrangler.toml (weekends wake it a few extra times, which do nothing)", async () => {
  const { readFileSync } = await import("node:fs");
  const toml = readFileSync(new URL("./wrangler.toml", import.meta.url), "utf8");
  const crons = [...toml.matchAll(/"([^"]+)"/g)].map((m) => m[1]).filter((c) => c.split(" ").length === 5);
  const fires = (cron, h, m) => {                                  // tiny matcher for the minute/hour lists and ranges used there
    const [cm, ch] = cron.split(" ");
    const has = (field, v) => field.split(",").some((p) => (p.includes("-") ? v >= +p.split("-")[0] && v <= +p.split("-")[1] : +p === v));
    return has(cm, m) && has(ch, h);
  };
  const week = ist("2026-11-02T00:00:00");
  for (let i = 0; i < 7 * 48; i++) {
    const t = new Date(week + i * 30 * 60000);
    const listed = crons.some((c) => fires(c, t.getUTCHours(), t.getUTCMinutes()));
    if (plan(t.getTime()) !== null) assert.ok(listed, `${t.toISOString()} would never fire`);
    if (!listed) assert.equal(plan(t.getTime()), null, t.toISOString());
  }
});

test("dispatch posts the right request and treats 204 as success", async () => {
  let seen;
  const fetchImpl = async (url, init) => { seen = { url, init }; return { status: 204, text: async () => "" }; };
  await dispatch({ GITHUB_TOKEN: "tok", REPO: "o/r", WORKFLOW: "daily.yml", REF: "main" }, "retry", fetchImpl);
  assert.equal(seen.url, "https://api.github.com/repos/o/r/actions/workflows/daily.yml/dispatches");
  assert.equal(seen.init.method, "POST");
  assert.equal(seen.init.headers.Authorization, "Bearer tok");
  assert.deepEqual(JSON.parse(seen.init.body), { ref: "main", inputs: { mode: "retry" } });
});

test("dispatch retries a GitHub 5xx once, then reports failures with GitHub's reply", async () => {
  let n = 0;
  const flaky = async () => (++n === 1 ? { status: 502, text: async () => "bad gateway" } : { status: 204, text: async () => "" });
  await dispatch({ GITHUB_TOKEN: "t", REPO: "o/r", WORKFLOW: "w.yml" }, "always", flaky);
  assert.equal(n, 2);
  const denied = async () => ({ status: 403, text: async () => "Resource not accessible by personal access token" });
  await assert.rejects(dispatch({ GITHUB_TOKEN: "t", REPO: "o/r", WORKFLOW: "w.yml" }, "always", denied), /403.*not accessible/);
  await assert.rejects(dispatch({ REPO: "o/r", WORKFLOW: "w.yml" }, "always", denied), /GITHUB_TOKEN secret is not set/);
});
