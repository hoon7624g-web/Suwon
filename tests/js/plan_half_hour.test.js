// Half-hour start and end (outside tester 2026-10-23: '10:30 기차' could not be entered — /plan/'s form offered the
// day's start and end on the hour only). The form now offers every half hour (templates/plan.html.j2: a start
// 07:00–14:00, an end 15:00–22:00); every option is a time the server takes (planner.validConditions: any HH:MM
// 06:00–23:00, three hours or more apart by the minute), and a 10:30 start goes through as it is — the conditions,
// the course the site builds from its data (the course sent first, and the final one when the model gives nothing),
// the station's margin after it, and a share link that carries it and opens again. The places are the site's own
// (tests/fixtures/plan_places.json: every place of public/chat, cut to the planner's fields).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { deflateRawSync } from "node:zlib";

import { Knowledge } from "./first_city.js";
import { tokens } from "../../chatbot/knowledge.js";
import { hm, hubMargin } from "../../chatbot/plan_state.js";
import { CODE_PLAN_BUSY, CODE_PLAN_EARLY, CODE_PLAN_LINE, codePlan, createPlanHandler, preflight, validConditions } from "../../chatbot/planner.js";
import { compactOf, normalize, signPlan } from "../../chatbot/plan_share.js";
import { createLimiter } from "../../chatbot/server.js";

const SITE = "https://gunsan.webforai.kr";
const NOW = new Date("2026-10-22T01:00:00Z");   // 2026-10-22 (Thu) 10:00 KST
const SECRET = "half-hour-test-secret-0123456789abcdef";   // plan_share.SECRET_MIN 32 characters at least
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_places.json", import.meta.url), "utf8"));
const INDEX = { v: 1, docs: Object.fromEntries(Object.entries(FX.docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) };
const KB = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs: FX.docs, alias: {}, ext: [], tickets: FX.tickets }, index: INDEX });
const BASE = { date: "2026-10-24", days: 1, start: "10:30", end: "17:30", move: "transit", with: "couple", adults: 2, seniors: 0, kids: [],
  from: "", to: "", prefs: [], needs: [], budget: null, note: "" };

// the form's selects as the template writes them: the minute of the day from the first hour to the last, every 30
const PLAN_HTML = readFileSync(new URL("../../templates/plan.html.j2", import.meta.url), "utf8");
const options = (name) => {
  const m = PLAN_HTML.match(new RegExp(`<select name="${name}">\\{% for m in range\\((\\d+) \\* 60, (\\d+) \\* 60 \\+ 1, 30\\) %\\}`));
  assert.ok(m, `the form's ${name} select`);
  const out = [];
  for (let t = +m[1] * 60; t <= +m[2] * 60; t += 30) out.push(`${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`);
  return out;
};

test("the form: every half hour, a start 07:00–14:00 and an end 15:00–22:00 — each a time the server takes, three hours apart by the minute", () => {
  const starts = options("start"), ends = options("end");
  assert.deepEqual(starts, ["07:00", "07:30", "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00"]);
  assert.deepEqual(ends, ["15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00", "21:30", "22:00"]);
  // the defaults stay 10:00 and 18:00
  assert.match(PLAN_HTML, /<select name="start">[^\n]*\{% if m == 10 \* 60 %\} selected/);
  assert.match(PLAN_HTML, /<select name="end">[^\n]*\{% if m == 18 \* 60 %\} selected/);
  // every pair the form can send: taken when three hours or more apart, a 400 otherwise (plan.js says so first)
  for (const start of starts) {
    for (const end of ends) {
      const apart = hm(end) - hm(start);
      if (apart >= 180) assert.equal(validConditions({ ...BASE, start, end }, NOW).start, start, `${start}–${end}`);
      else assert.throws(() => validConditions({ ...BASE, start, end }, NOW), (e) => e.status === 400, `${start}–${end}`);
    }
  }
  // 12:30–15:00 is two hours and a half: on the hour it read as three (15 − 12)
  assert.throws(() => validConditions({ ...BASE, start: "12:30", end: "15:00" }, NOW), (e) => e.status === 400);
  assert.equal(validConditions({ ...BASE, start: "12:00", end: "15:00" }, NOW).end, "15:00");
});

test("a 10:30 start: the conditions keep it, the course the site builds starts at it and ends by 17:30 — 'ready', nothing flagged", () => {
  const c = validConditions(BASE, NOW);
  assert.deepEqual([c.start, c.end], ["10:30", "17:30"]);
  assert.deepEqual(preflight(c, KB, NOW), [], "no condition to change at the button");
  const plan = codePlan(c, KB, NOW, CODE_PLAN_LINE);
  assert.ok(plan, "the site's own course");
  assert.equal(plan.status, "ready");
  assert.deepEqual(plan.flags, []);
  assert.deepEqual([plan.conditions.start, plan.conditions.end], ["10:30", "17:30"]);
  const stops = plan.days[0].stops;
  assert.equal(stops[0].start, "10:30", "the first stop at the reader's start — not 10:00, not 11:00");
  assert.ok(stops.every((s) => hm(s.start) >= hm("10:30") && hm(s.end) <= hm("17:30")), stops.map((s) => `${s.start}-${s.end}`).join(" "));

  // from 군산역 at 10:30 back to 군산역 by 17:30: the station's margin after the half hour, the hubs at the reader's times
  const cs = validConditions({ ...BASE, from: "station", to: "station" }, NOW);
  const viaStation = codePlan(cs, KB, NOW, CODE_PLAN_LINE);
  assert.ok(viaStation);
  assert.equal(viaStation.status, "ready");
  assert.deepEqual(viaStation.flags, []);
  const day = viaStation.days[0];
  assert.deepEqual(day.hubs.map((x) => [x.dir, x.at]), [["from", "10:30"], ["to", "17:30"]]);
  const first = day.stops[0], last = day.stops.at(-1);
  assert.ok(hm(first.start) >= hm("10:30") + hubMargin(cs, "from", KB.docs[first.path]), `${first.name} ${first.start}`);
  assert.ok(hm(last.end) <= hm("17:30") - hubMargin(cs, "to", KB.docs[last.path]), `${last.name} ${last.end}`);

  // two days: the first held to 10:30, the last to 17:30
  const two = codePlan(validConditions({ ...BASE, days: 2, from: "station", to: "station" }, NOW), KB, NOW, CODE_PLAN_LINE);
  assert.ok(two);
  assert.equal(two.status, "ready");
  assert.deepEqual(two.flags, []);
  assert.ok(hm(two.days[0].stops[0].start) >= hm("10:30") + 30);
  assert.ok(hm(two.days[1].stops.at(-1).end) <= hm("17:30") - 30);
});

// the handler as the page asks it: SSE events of one request
const busyClient = () => ({ messages: { stream() { throw Object.assign(new Error("overloaded"), { status: 529 }); } } });
const neverClient = () => ({ messages: { stream() { throw new Error("a view never calls the model"); } } });
const handler = (client) => createPlanHandler({ client, knowledge: () => KB, log: () => {}, now: () => NOW, limiter: createLimiter(100),
  env: { PLAN_SHARE_SECRET: SECRET } });
const post = (body) => new Request(`${SITE}/api/plan/`, { method: "POST",
  headers: { "content-type": "application/json", origin: SITE, "x-real-ip": "203.0.113.30" }, body: JSON.stringify(body) });
const events = async (res) => (await res.text()).split("\n\n").filter(Boolean).map((b) => JSON.parse(b.slice(6)));

test("a 10:30 start through the handler: the course sent first and the final one (the model busy) both start at 10:30, signed", async () => {
  const evs = await events(await handler(busyClient())(post({ conditions: { ...BASE, from: "station" } })));
  const early = evs.find((e) => e.type === "early"), final = evs.at(-1);
  assert.ok(early, evs.map((e) => e.type).join(","));
  assert.equal(final.type, "plan");
  assert.deepEqual(early.plan.fixed, [CODE_PLAN_EARLY]);
  assert.deepEqual(final.plan.fixed, [CODE_PLAN_BUSY]);
  for (const p of [early.plan, final.plan]) {
    assert.equal(p.status, "ready");
    assert.deepEqual(p.flags, []);
    assert.deepEqual([p.conditions.start, p.conditions.end, p.conditions.from], ["10:30", "17:30", "station"]);
    assert.equal(p.days[0].hubs[0].at, "10:30");
    assert.ok(hm(p.days[0].stops[0].start) >= hm("10:30") + 30);
  }
  assert.equal(final.sig, signPlan(final.plan, Buffer.from(SECRET)));
});

test("a share link with 10:30: the compact form carries '10:30' and '17:30', the link opens again with them — signed, the same stops, 'ready'", async () => {
  const evs = await events(await handler(busyClient())(post({ conditions: BASE })));
  const { plan, sig } = evs.at(-1);
  const cp = compactOf(plan);
  assert.deepEqual([cp.c.start, cp.c.end], ["10:30", "17:30"]);
  assert.deepEqual([normalize(cp).c.start, normalize(cp).c.end], ["10:30", "17:30"]);
  assert.equal(cp.d[0][0][1], "10:30");
  // as the page packs it (deflate-raw, base64url) and as it sends it when it can read it itself
  const packed = `z.${deflateRawSync(Buffer.from(JSON.stringify(cp))).toString("base64url")}`;
  for (const view of [{ packed, sig }, { compact: cp, sig }]) {
    const res = await handler(neverClient())(post({ view }));
    assert.equal(res.status, 200);
    const v = await res.json();
    assert.equal(v.type, "view");
    assert.equal(v.signed, true);
    assert.deepEqual([v.plan.conditions.start, v.plan.conditions.end], ["10:30", "17:30"]);
    assert.deepEqual(v.plan.days.map((d) => d.stops.map((s) => [s.path, s.start, s.end, s.role])),
      plan.days.map((d) => d.stops.map((s) => [s.path, s.start, s.end, s.role])));
    assert.equal(v.plan.status, "ready");
    assert.deepEqual(v.plan.flags, []);
    assert.equal(v.sig, sig, "the same plan, the same signature: it passes on again");
  }
});
