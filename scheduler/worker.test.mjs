// Run with:  node --test scheduler/      (no packages needed)
import test from "node:test";
import assert from "node:assert/strict";
import { plan, dispatch } from "./worker.mjs";

const ist = (iso) => Date.parse(iso + "+05:30");                 // an IST wall-clock time to epoch milliseconds
// 2026-11-02 is a Monday, 2026-11-07 a Saturday, 2026-11-08 a Sunday.

test("weekday morning: 06:00 to 09:30 until a build has run, nothing from 10:00", () => {
  for (const t of ["06:00", "06:30", "07:00", "08:30", "09:30"]) assert.equal(plan(ist(`2026-11-03T${t}:00`)), "daily", t);
  for (const t of ["05:30", "10:00", "12:00", "15:30", "18:30"]) assert.equal(plan(ist(`2026-11-03T${t}:00`)), null, t);
});

test("weekday evening runs 19:00 to 01:00 IST, including after midnight", () => {
  for (const t of ["2026-11-02T19:00", "2026-11-02T22:30", "2026-11-02T23:30", "2026-11-03T00:00", "2026-11-03T00:30", "2026-11-03T01:00"])
    assert.equal(plan(ist(t + ":00")), "retry", t);
  assert.equal(plan(ist("2026-11-03T01:30:00")), null);
});

test("Friday evening continues to 01:00 on Saturday; Saturday and Sunday night do not", () => {
  assert.equal(plan(ist("2026-11-06T19:00:00")), "retry");        // Friday
  assert.equal(plan(ist("2026-11-07T01:00:00")), "retry");        // Saturday 01:00 is still Friday's session
  assert.equal(plan(ist("2026-11-07T20:00:00")), "daily");        // Saturday evening is the weekend backup, not a session retry
  assert.equal(plan(ist("2026-11-08T00:30:00")), null);           // Sunday 00:30 belongs to Saturday: no session
  assert.equal(plan(ist("2026-11-09T00:30:00")), null);           // Monday 00:30 belongs to Sunday
  assert.equal(plan(ist("2026-11-09T19:30:00")), "retry");        // Monday evening is a session again
});

test("weekend: 08:00 refresh and a 20:00 backup, nothing else", () => {
  for (const d of ["2026-11-07", "2026-11-08"]) {
    assert.equal(plan(ist(`${d}T08:00:00`)), "daily", d);
    assert.equal(plan(ist(`${d}T20:00:00`)), "daily", d);
    for (const t of ["06:00", "09:00", "12:00", "19:00", "21:00"]) assert.equal(plan(ist(`${d}T${t}:00`)), null, `${d} ${t}`);
  }
});

test("over a whole week the number of starts is as designed", () => {
  const week = ist("2026-11-02T00:00:00");
  const counts = {};
  for (let i = 0; i < 7 * 48; i++) { const m = plan(week + i * 30 * 60000); if (m) counts[m] = (counts[m] || 0) + 1; }
  // weekdays: 8 morning slots (06:00-09:30) + 13 evening slots (19:00-01:00 next day); weekend days: 2 slots each
  assert.equal(counts.always, undefined);                         // "always" is only for starting a build by hand
  assert.equal(counts.daily, 5 * 8 + 2 * 2);
  assert.equal(counts.retry, 5 * 13);
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
