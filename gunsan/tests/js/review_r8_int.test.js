// node --test tests/js/ — review 2026-10-22, the seam between clusters: checkPlan's noHolidayTable (chat tools) reaches
// the page's day (planner.finish), where plan.js reads it so a year without the 설·추석·대체공휴일 table never reads
// all-clear (S9).
import assert from "node:assert/strict";
import { test } from "node:test";

import { finish } from "../../chatbot/planner.js";

const check = (dayExtra) => ({
  days: [{ stops: [{ day: "open", notes: [], flags: [], checks: [] }], legs: [], ...dayExtra }],
  hubs: [], needs: [], checks: [], aware: [], flags: [], complete: {},
  fees: { state: "none", total: 0, known: 0, limit: null, verdict: "open", open: 0, conds: [], days: [] },
});
const plan = (date) => ({ title: "t", summary: "", notes: [], days: [{ date, stops: [{ page: "/places/a/", name: "a", start: "10:00", end: "11:00", role: "visit" }] }] });
const c = { date: "2028-01-26", days: 1, move: "transit", with: "couple", needs: [], prefs: [] };

test("finish carries checkPlan's noHolidayTable onto the day the page reads, and only then", () => {
  const withFlag = finish(plan("2028-01-26"), check({ noHolidayTable: true }), c);
  assert.equal(withFlag.days[0].noHolidayTable, true);
  const without = finish(plan("2027-01-26"), check({}), { ...c, date: "2027-01-26" });
  assert.equal("noHolidayTable" in without.days[0], false);
});
