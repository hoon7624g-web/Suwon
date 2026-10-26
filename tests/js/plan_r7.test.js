// Round 7 (live check 2026-10-19 on the public server, 20 plans of one to three days with the real model): a night's
// stay the model put at its check-in ended the day — no dinner, the afternoon or the night empty; 고군산 by car on a
// Tuesday built again as town days (the islands have three restaurants); a park and a place inside it on two days; a
// restaurant given as a place to visit; without a car, a 28 km ride at night after an island dinner. The model's own
// plans of those trips (each final plan without the stops the code added) and the site's places around them are in
// tests/fixtures/plan_r7_live.json (public/chat, cut to the planner's fields). Each test fails on 0d30bd6c2 but the
// last, which holds what that code did for a link made before.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge } from "./first_city.js";
import { tokens } from "../../chatbot/knowledge.js";
import { hm, isCafe, mealKind } from "../../chatbot/plan_state.js";
import { makePlan, validConditions, viewPlan } from "../../chatbot/planner.js";
import { compactOf, signCompact } from "../../chatbot/plan_share.js";

const NOW = new Date("2026-10-19T01:00:00Z");   // 2026-10-19 (Mon) 10:00 KST
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_r7_live.json", import.meta.url), "utf8"));
const INDEX = { v: 1, docs: Object.fromEntries(Object.entries(FX.docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) };
const kb = () => new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs: FX.docs, alias: {}, ext: [], tickets: FX.tickets }, index: INDEX });
const CASE = (name) => FX.cases.find((x) => x.name.startsWith(name));
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
// a model that hands the same submit_plan over on every call
function client(input) {
  return { messages: { stream() {
    const message = { role: "assistant", content: [{ type: "tool_use", id: "toolu_1", name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
async function run(name) {
  const x = CASE(name);
  const sent = [];
  await makePlan({ client: client(x.input), kb: kb(), conditions: validConditions(x.conditions, NOW), send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.equal(plan.status, "ready");
  assert.deepEqual(plan.flags, []);
  assert.ok(!plan.fixed.some((t) => /^일정 전체:/u.test(t)), "never the code's own trip");
  return plan;
}
const rows = (d) => d.stops.map((s) => [s.name, s.start, s.end, s.role]);
const dinnerOf = (d, k) => d.stops.find((s) => s.role === "meal" && !isCafe(k.docs[s.path]) && mealKind(hm(s.start), hm(s.end)) === "dinner");

test("a night's stay the model put at its check-in no longer ends the day: the afternoon is filled, the dinner goes in, the stay after them", async () => {
  // 부모님과 1박 2일 by car, 09:00–19:00: the model's day 1 was 은파 and a lunch, then the hotel at 15:00 (its check-in) —
  // four hours of the reader's day left out. The lunch has no point on the site: the places are looked for from the
  // stop before it that has one
  let plan = await run("A03");
  const d1 = plan.days[0];
  assert.deepEqual(rows(d1).slice(0, 2), [["은파호수공원", "09:00", "11:00", "visit"], ["은파아리울", "11:30", "13:00", "meal"]]);
  assert.ok(d1.stops.filter((s) => s.role === "visit" && hm(s.start) >= 13 * 60).length >= 2);
  assert.equal(d1.stops.at(-1).name, "호텔 은파 팰리스");
  assert.ok(hm(d1.stops.at(-1).start) > hm(d1.stops.at(-2).end), "the stay after the day's last stop");
  assert.match(plan.fixed.find((t) => t.startsWith("1일차 빈 시간 13:00~19:00")), /: 앞 장소 은파호수공원에서 가까운 /u);
  // 혼자 1박 2일 without a car, 11:00–22:00: the guesthouse at 19:00 left the day with no dinner
  plan = await run("A04");
  const k = kb();
  const dinner = dinnerOf(plan.days[0], k);
  assert.ok(dinner, "day 1 has its dinner");
  const stay = plan.days[0].stops.at(-1);
  assert.equal(stay.role, "stay");
  assert.ok(hm(stay.start) >= hm(dinner.end));
  assert.ok(plan.fixed.includes(`1일차 밤 숙소 게스트하우스 이웃: 그날 마지막 장소 ${dinner.name} 뒤로 시작을 19:00에서 ${stay.start}${hm(stay.start) % 60 ? "으로" : "로"} 늦췄습니다`));
});

test("고군산 by car on a Tuesday keeps its island days: a restaurant of another day when the islands have no other, a dinner off them before a day built anew", async () => {
  const plan = await run("A16");
  assert.ok(!plan.fixed.some((t) => /다시 짰습니다/u.test(t)), plan.fixed.join("\n"));
  const d2 = plan.days[1];
  for (const name of ["대장봉 전망대", "장자도", "장자도선착장", "장자교 스카이워크", "옥돌해변"]) assert.ok(d2.stops.some((s) => s.name === name), name);
  // the lunch: 남도밥상, the first day's, said so; 선유도밤바다 shuts on Tuesdays
  const lunch = plan.fixed.find((t) => t.startsWith("2일차 점심:"));
  assert.match(lunch, /남도밥상\(직선 [\d.]+km, 그날 그 시각에 여는 곳, 다른 날에도 가는 곳 — 가까이에 그 시각에 여는 다른 음식점이 사이트에 없음\)/u);
  // the dinner: nothing on the islands, past the cap by car (비응항, 18 km) — the day keeps its places
  const k = kb();
  const dinner = dinnerOf(d2, k);
  assert.ok(dinner && !["남도밥상", "선유도밤바다"].includes(dinner.name), dinner && dinner.name);
  assert.ok(hm(d2.stops[0].start) >= 9 * 60, "the day starts when the reader's does");
  // the third day too (its dinner the first day's lunch, said so)
  assert.ok(plan.days[2].stops.some((s) => s.name === "선유대교") && plan.days[2].stops.some((s) => s.name === "무녀도"));
});

test("a park and a place inside it, two pages of one building, are one place across a trip's days", async () => {
  // 구 조선은행 군산지점 on day 1 and 군산근대건축관 (the museum in that building) on day 2: the second goes for the nearest
  // place of its kind
  let plan = await run("A04");
  assert.ok(plan.fixed.some((t) => /^2일차 군산근대건축관: 앞날에 들른 구 조선은행 군산지점과 같은 곳이라 가까운 .+로 바꿨습니다$/u.test(t)), plan.fixed.join("\n"));
  assert.ok(!plan.days[1].stops.some((s) => s.name === "군산근대건축관"));
  // 은파호수공원 물빛다리 the first night: the empty evening of day 2 never gets 은파호수공원
  plan = await run("A05");
  assert.ok(plan.days[0].stops.some((s) => s.name === "은파호수공원 물빛다리"));
  assert.ok(!plan.days[1].stops.some((s) => s.name === "은파호수공원"));
  const k = kb();
  for (const [i, d] of plan.days.entries()) {
    for (const s of d.stops.filter((x) => x.role !== "stay")) {
      const kin = [...(k.kin.get(s.path) || [])];
      assert.ok(!plan.days.some((o, j) => j !== i && o.stops.some((y) => kin.includes(y.path))), `${s.name} with a page of another day`);
    }
  }
});

test("a restaurant given as a place to visit is the meal", async () => {
  // 설날 연휴, day 2: '17:00–18:00 visit 진갈비'
  const plan = await run("A12");
  const s = plan.days[1].stops.find((x) => x.name === "진갈비");
  assert.deepEqual([s.start, s.end, s.role], ["17:00", "18:00", "meal"]);
  assert.ok(plan.fixed.includes("2일차 진갈비: 음식점이라 둘러볼 곳이 아닌 식사로 두었습니다"));
});

test("without a car, the island day's dinner goes near the night's stay 28 km off — the ride before it, the dinner by the day's end", async () => {
  // A10 as the model sent it: its island day runs to 18:00 with a café; the reader's 20:00 holds every day (2026-10-24
  // I07), so the café gives the ride its time — never the island dinner with the 28 km ride after it, at night (round 7)
  const plan = await run("A10");
  const k = kb();
  for (const d of plan.days) for (const s of d.stops.filter((y) => y.role !== "stay")) assert.ok(hm(s.end) <= hm("20:00") && hm(s.start) >= hm("09:00"), `${s.name} ${s.start}–${s.end}`);
  const d1 = plan.days[0];
  const dinner = dinnerOf(d1, k);
  const stay = d1.stops.at(-1);
  assert.equal(stay.name, "호텔 은파 팰리스");
  assert.notEqual(dinner.name, "선유도밤바다");
  // (the island dinner was the code's own: the line says the new one went in, and none names the margin to the old one)
  assert.ok(plan.fixed.some((t) => /^1일차 저녁: 밤 숙소 호텔 은파 팰리스가 직선 [\d.]+km 떨어져 있어, 차 없이 밤에 이동하지 않도록 숙소에서 가까운 음식점 .+ 넣었습니다$/u.test(t)), plan.fixed.join("\n"));
  assert.ok(!plan.fixed.some((t) => /선유도밤바다/u.test(t)), plan.fixed.join("\n"));
  assert.ok(plan.fixed.includes("1일차 카페라파르: 밤 숙소 호텔 은파 팰리스가 직선 28.6km 떨어져 있어, 차 없이 밤에 이동하지 않도록 저녁 전에 숙소 쪽으로 가는 시간을 두려고 일정에서 뺐습니다"), plan.fixed.join("\n"));
  assert.ok(hm(stay.start) - hm(dinner.end) <= 60, "the stay right after the dinner");
  // the island day ending at 16:30 with the model's dinner on the island at 17:30: the ride comes before the dinner, the
  // dinner near the stay, the stay right after it — no place taken out
  const x = structuredClone(CASE("A10"));
  const P = (name) => Object.keys(FX.docs).find((key) => FX.docs[key].t === name);
  x.input.days[0].stops = [["선유도해수욕장", "09:00", "11:30", "visit"], ["남도밥상", "11:45", "13:15", "meal"], ["선유도", "13:30", "15:00", "visit"],
    ["장자도", "15:15", "16:30", "visit"], ["선유도밤바다", "17:30", "18:30", "meal"]].map(([name, start, end, role]) => ({ page: P(name), start, end, role, why: "" }));
  const sent = [];
  await makePlan({ client: client(x.input), kb: k, conditions: validConditions(x.conditions, NOW), send: (e) => sent.push(e), now: NOW });
  const early = sent.at(-1).plan;
  assert.deepEqual([early.status, early.flags], ["ready", []]);
  const dinner2 = dinnerOf(early.days[0], k);
  const stay2 = early.days[0].stops.at(-1);
  assert.equal(stay2.name, "호텔 은파 팰리스");
  assert.notEqual(dinner2.name, "선유도밤바다");
  assert.ok(early.fixed.some((t) => /^1일차 선유도밤바다: 밤 숙소 호텔 은파 팰리스가 직선 [\d.]+km 떨어져 있어, 차 없이 밤에 이동하지 않도록 저녁을 숙소에서 가까운 .+ 두었습니다$/u.test(t)), early.fixed.join("\n"));
  assert.ok(!early.fixed.some((t) => /일정에서 뺐습니다/u.test(t)), early.fixed.join("\n"));
  assert.ok(hm(dinner2.end) <= hm("20:00"), "inside the reader's day");
  assert.ok(hm(stay2.start) - hm(dinner2.end) <= 60, "the stay right after the dinner");
});

test("a link to a plan made before round 7 — the night's stay at its check-in, the afternoon after it free — is no problem when opened", () => {
  const x = CASE("A03");
  const c = validConditions(x.conditions, NOW);
  const P = (name) => Object.keys(FX.docs).find((k) => FX.docs[k].t === name);
  const S = (name, start, end, role) => ({ path: P(name), name, start, end, role });
  const plan = { title: "부모님과 군산 1박 2일", summary: "", notes: [], conditions: c, fixed: [], complete: { meals: [] }, days: [
    { stops: [S("은파호수공원", "09:00", "11:00", "visit"), S("은파아리울", "11:30", "13:00", "meal"), S("호텔 은파 팰리스", "15:00", "16:00", "stay")] },
    { stops: [S("고군산섬잇길", "09:00", "10:00", "visit"), S("선유도", "10:30", "12:20", "visit"), S("남도밥상", "12:30", "13:30", "meal"),
      S("선유도 둘레길", "14:00", "16:00", "visit"), S("선유1구항", "16:10", "17:40", "visit")] }] };
  const key = Buffer.from("k".repeat(32));
  const compact = compactOf(plan);
  const view = viewPlan({ compact, sig: signCompact(compact, key) }, kb(), NOW, key);
  assert.equal(view.plan.status, "ready");
  assert.deepEqual(view.plan.flags, []);
});
