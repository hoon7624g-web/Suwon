// Review 2026-10-22 (외부 리뷰 검증 — the planner's server side): an easy way for a pram or a wheelchair said by the AI
// (C1, also in the title: S8) and the stroller rental's '불가' read as strollers not allowed; the station's and
// terminals' margin flat at 30 minutes whatever the first stop's 권역, 선유도 too (C7a), with the site's own bus guides
// unlinked (S2); every stop the site swapped in labelled as a closed day's (S5); the site's own course silent about
// the reader's note (S7); and the prompt lines for 걷기 적게 (C6) and the other days' start (daybounds). The places are
// the site's own (tests/fixtures/plan_places.json: every place of public/chat, cut to the planner's fields).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { HUBS, HUB_REGION, ISLAND_FLOOR, Knowledge } from "./first_city.js";
import { regionFloor, regionOf, tokens } from "../../chatbot/knowledge.js";
import { HUB_MARGIN, grounded, hm, hubMargin, needAt } from "../../chatbot/plan_state.js";
import { conditionsText, planRules } from "../../chatbot/plan_prompt.js";
import { hubLegs } from "../../chatbot/plan_geo.js";
import { buildPlan, planFlags } from "../../chatbot/plan_build.js";
import {
  CODE_NOTE_LINE, CODE_PLAN_BUSY, CODE_PLAN_EARLY, CODE_PLAN_LINE, codePlan, makePlan, noteAware, preflight, readSubmit, repair, validConditions, verify,
} from "../../chatbot/planner.js";

const NOW = new Date("2026-10-22T01:00:00Z");   // 2026-10-22 (Thu) 10:00 KST
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_places.json", import.meta.url), "utf8"));
const LIVE = JSON.parse(readFileSync(new URL("../fixtures/plan_meals_live.json", import.meta.url), "utf8"));
// the site's bus guide sections the hub legs link to (docs.json has them; the fixture keeps places only)
const GUIDES = Object.fromEntries(["/guides/군산-시내버스-관광지/", "/guides/군산-시내버스-관광지/#h-b2", "/guides/군산-시내버스-관광지/#h-b5",
  "/guides/군산-시내버스-관광지/#h-b6", "/guides/군산-가는-법-교통/#h-b6", "/guides/군산-시외버스-고속버스-공항/#h-b6"]
  .map((k) => [k, { t: k, k: "guide", x: k }]));
const indexOf = (docs) => ({ v: 1, docs: Object.fromEntries(Object.entries(docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) });
const INDEX = indexOf(FX.docs);
const kbOf = (docs = FX.docs, index = INDEX) => new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs, alias: {}, ext: [], tickets: FX.tickets }, index });
const KB = kbOf();
const P = (name) => {
  const k = Object.keys(FX.docs).find((x) => FX.docs[x].t === name);
  if (!k) throw new Error(`no place ${name}`);
  return k;
};
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
// a model that hands the same submit_plan over on every call; calls: what each call was sent
function client(input, calls = []) {
  return { messages: { stream(params) {
    calls.push(structuredClone(params.messages));
    const message = { role: "assistant", content: [{ type: "tool_use", id: `toolu_${calls.length}`, name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
const BASE = { days: 1, start: "10:00", end: "18:00", move: "transit", with: "couple", adults: 2, seniors: 0, kids: [], from: "", to: "", prefs: [], needs: [], budget: null, note: "" };
async function run(input, raw, kb = KB, calls = []) {
  const c = validConditions(raw, NOW);
  const sent = [];
  await makePlan({ client: client(input, calls), kb, conditions: c, send: (e) => sent.push(e), now: NOW });
  const last = sent.at(-1);
  assert.equal(last.type, "plan", JSON.stringify(last).slice(0, 400));
  return { plan: last.plan, c };
}

test("C1, S8: a pram's or a wheelchair's easy way is a claim — in the summary, a note, a reason and the title, which becomes the code's", async () => {
  // the review's summary, the round-7 example, the live plan of 2026-10-19 (tests/fixtures/plan_meals_live.json), and
  // the forms the challenge found; the plan_test.js:332 sentence is pinned there
  for (const t of ["유모차로 이동하기 쉬운 장미동·월명동 일대를 걷고, 점심은 실내 음식점에서 먹습니다.", "빨간 벽돌 건물이라 유모차로 다니기 편합니다",
    LIVE.cases[0].input.summary, "휠체어로 이동하기 쉽습니다", "유모차 접근이 쉬운 곳만 골랐습니다", "유모차로 둘러보기 좋습니다", "휠체어로 다니기 무난한 길입니다",
    "유모차 친화적인 박물관입니다", "편한 유모차 동선", "무장애 동선으로 묶었습니다", "배리어프리 코스입니다", "휠체어로 다녀도 어려움이 없는 곳"]) {
    assert.equal(grounded(t, "").claim, true, t);
  }
  // a page's own access words are no claim (the pages' words are read as before: ACCESS_WORDS)
  for (const t of ["유모차 대여가 가능합니다", "유모차 대여는 없지만 출입구 턱이 없습니다", "전망 좋은 곳에 있으며 휠체어 대여가 가능합니다", "휠체어 접근 정보는 사이트에 없습니다"]) {
    assert.equal(grounded(t, "유모차 대여 가능 휠체어 대여 가능 턱이 없음").claim, false, t);
  }
  // end to end: the code's own Monday for rain and a pram handed over with the claims, as the model wrote them
  const raw = { ...BASE, date: "2026-10-26", with: "kids", kids: [2], needs: ["rain", "stroller"] };
  const built = buildPlan(validConditions(raw, NOW), KB);
  assert.ok(built.plan);
  const input = { title: "유모차로 편한 비 오는 월요일 원도심 하루",
    summary: "월요일 하루, 원도심의 실내 시설 위주로 엮었습니다. 유모차로 이동하기 쉬운 장미동·월명동 일대를 걷고, 점심은 실내 음식점에서 먹습니다.",
    notes: ["유모차로 다니기 편한 동선입니다.", "시장 두 곳은 가까이 붙어 있습니다."],
    days: built.plan.days.map((d) => ({ date: d.date, stops: d.stops.map((s, i) => ({ page: s.page, start: s.start, end: s.end, role: s.role,
      why: i === 0 ? "유모차로 둘러보기 좋습니다." : "" })) })) };
  const calls = [];
  const { plan } = await run(input, raw, KB, calls);
  assert.equal(plan.status, "ready");
  // the one fix round names the title and the access ease for the model
  assert.equal(calls.length, 2);
  const back = JSON.stringify(calls[1].at(-1).content);
  assert.match(back, /title: '확인됐다·보장·문제없다·모두 가능·걷는 거리를 줄였다'는 쓰지 않는다\(유모차·휠체어로 다니기 쉽다·편하다도\)/u);
  assert.match(back, /notes 1: /u);
  assert.match(back, /1일차 1번 [^"]+ why: /u);
  // then the last word: the sentence, the note and the reason go; the title is the code's
  assert.equal(plan.summary, "월요일 하루, 원도심의 실내 시설 위주로 엮었습니다.");
  assert.deepEqual(plan.notes, ["시장 두 곳은 가까이 붙어 있습니다."]);
  assert.equal(plan.days[0].stops[0].why, "");
  assert.equal(plan.title, "10월 26일(월) 군산 하루 코스");
});

test("the stroller's rental: '불가' reads '유모차 대여 불가', never '유모차 불가'; a value with 대여 keeps one label", () => {
  const f = (t) => ({ ac: [{ k: "babycarriage", p: "군산시 문화관광", t }] });
  assert.equal(needAt("stroller", f("불가"), "visit").text, "출입구 접근 정보 없음 · 유모차 대여 불가");
  assert.equal(needAt("stroller", f("대여 가능(예약 없이 박물관 안내소에서)"), "visit").text, "출입구 접근 정보 없음 · 유모차 대여 가능(예약 없이 박물관 안내소에서)");
  assert.equal(needAt("stroller", f("없음"), "visit").text, "출입구 접근 정보 없음 · 유모차 대여 없음");
  assert.equal(needAt("stroller", f("유모차 대여 가능"), "visit").text, "출입구 접근 정보 없음 · 유모차 대여 가능");
  // the site's own '불가' places (일제강점기 군산역사관 among them)
  const no = Object.keys(FX.docs).filter((k) => ((FX.docs[k].f || {}).ac || []).some((a) => a.k === "babycarriage" && a.t === "불가"));
  for (const k of no) assert.match(needAt("stroller", FX.docs[k].f, "visit").text, /유모차 대여 불가/u, k);
  for (const k of no) assert.doesNotMatch(needAt("stroller", FX.docs[k].f, "visit").text, /유모차 불가/u, k);
});

test("C7a: the station's margin by the 권역 of the stop next to it — 30, 45 across 권역 without a car, the islands 2 hours (1 by car)", () => {
  assert.deepEqual(HUB_REGION, { station: "금강", bus: "원도심", express: "원도심", airport: "은파" });
  const doc = (r) => ({ x: `곳 — 관광지\n위치: 어딘가 · ${r} 권역` });
  const m = (hub, r, move = "transit", dir = "from") => hubMargin({ from: hub, to: hub, move }, dir, r ? doc(r) : null);
  assert.equal(m("bus", "원도심"), HUB_MARGIN);
  assert.equal(m("express", "원도심", "car"), 30);
  assert.equal(m("station", "원도심"), 45);          // 군산역 is in 금강 (내흥동): the guide's '시내까지 30분 정도' and the wait
  assert.equal(m("station", "원도심", "car"), 30);
  assert.equal(m("station", "금강"), 30);
  assert.equal(m("airport", "원도심"), 45);
  assert.equal(m("airport", "은파"), 30);
  for (const hub of Object.keys(HUBS)) {
    assert.equal(m(hub, "고군산"), ISLAND_FLOOR.transit, hub);
    assert.equal(m(hub, "고군산", "car"), ISLAND_FLOOR.car, hub);
    assert.equal(m(hub, "고군산", "transit", "to"), 120, hub);
  }
  assert.deepEqual(ISLAND_FLOOR, { car: 60, transit: 120 });
  assert.equal(m("station", ""), HUB_MARGIN);        // a page with no 권역
  assert.equal(hubMargin({ from: "", to: "", move: "transit" }, "from", doc("고군산")), 0);
  // a leg with no point between places: the islands' floor too; across other 권역 30 by car, 45 without (as before)
  assert.equal(regionFloor(doc("원도심"), doc("고군산"), "transit"), 120);
  assert.equal(regionFloor(doc("고군산"), doc("새만금·비응"), "car"), 60);
  assert.equal(regionFloor(doc("원도심"), doc("새만금·비응"), "car"), 30);
  assert.equal(regionFloor(doc("원도심"), doc("새만금·비응"), "transit"), 45);
  assert.equal(regionFloor(doc("원도심"), doc("원도심"), "transit"), 0);
  // the check says the margin it holds
  const c = validConditions({ ...BASE, date: "2026-11-04", from: "station", prefs: ["islands"] }, NOW);
  const plan = { days: [{ date: c.date, stops: [{ page: P("선유도해수욕장"), name: "선유도해수욕장", start: "10:30", end: "12:00", role: "visit" }] }] };
  const f = planFlags(plan, c, KB).list.find((x) => x.kind === "hub-from");
  assert.equal(f.text, "군산역 10:00 출발인데 첫 장소 선유도해수욕장이 10:00 뒤 120분 안에 시작한다(30분) — 출발지에서 오는 여유를 둔다");
});

test("C7a: 섬·바다 from and back to every station and terminal, by bus and by car — always a finished plan, the islands after their margin", () => {
  for (const move of ["transit", "car"]) {
    for (const hub of Object.keys(HUBS)) {
      const c = validConditions({ ...BASE, date: "2026-11-04", move, from: hub, to: hub, prefs: ["islands"] }, NOW);
      assert.deepEqual(preflight(c, KB, NOW), [], `${move} ${hub}`);
      const p = codePlan(c, KB, NOW, CODE_PLAN_EARLY);
      assert.ok(p, `${move} ${hub}`);
      assert.equal(p.status, "ready");
      const stops = p.days[0].stops;
      const isle = stops.filter((s) => regionOf(KB.docs[s.path]) === "고군산");
      assert.ok(isle.length, `${move} ${hub}: no island stop`);
      const need = ISLAND_FLOOR[move];
      assert.ok(hm(isle[0].start) - hm(c.start) >= need, `${move} ${hub}: ${isle[0].name} at ${isle[0].start}`);
      assert.ok(hm(c.end) - hm(isle.at(-1).end) >= need, `${move} ${hub}: ${isle.at(-1).name} to ${isle.at(-1).end}`);
      for (const h of p.days[0].hubs) assert.ok(h.gap >= h.need, `${move} ${hub} ${h.dir} ${h.gap} < ${h.need}`);
      // the islands' day still has its lunch (the meals are read after the station's 30 minutes only)
      assert.ok(p.complete.meals.some((x) => x.kind === "lunch" && x.state !== "missing"), `${move} ${hub} ${JSON.stringify(p.complete.meals)}`);
    }
  }
  // two days, by bus, from 군산역 back to the airport: each end holds its own margin
  const c = validConditions({ ...BASE, date: "2026-11-07", days: 2, from: "station", to: "airport", prefs: ["islands"] }, NOW);
  assert.deepEqual(preflight(c, KB, NOW), []);
  const p = codePlan(c, KB, NOW, CODE_PLAN_EARLY);
  assert.equal(p.status, "ready");
  for (const d of p.days) for (const h of d.hubs) assert.ok(h.gap >= h.need && h.need >= HUB_MARGIN, JSON.stringify(h));
});

test("C7a: a model's 선유도 half an hour after the airport by bus is settled — its first island stop two hours after, back to 군산역 two hours before", async () => {
  const raw = { ...BASE, date: "2026-11-04", from: "airport", to: "station", prefs: ["islands"] };
  const input = { title: "섬 하루", summary: "고군산 섬을 하루 돕니다.", notes: [], days: [{ date: "2026-11-04", stops: [
    { page: P("선유도해수욕장"), start: "10:30", end: "12:00", role: "visit", why: "" },
    { page: P("남도밥상"), start: "12:10", end: "13:10", role: "meal", why: "" },
    { page: P("장자교 스카이워크"), start: "13:30", end: "15:00", role: "visit", why: "" },
    { page: P("장자도"), start: "15:15", end: "17:30", role: "visit", why: "" }] }] };
  const { plan } = await run(input, raw);
  assert.equal(plan.status, "ready");
  const own = plan.days[0].stops;
  assert.ok(hm(own[0].start) >= hm("12:00"), own[0].start);
  assert.ok(hm(own.at(-1).end) <= hm("16:00"), own.at(-1).end);
  assert.ok(plan.fixed.some((t) => /군산역으로 돌아가는 여유 2시간을 두려고/u.test(t)), plan.fixed.join("\n"));
});

test("S2: a hub's leg without a car names the site's own bus guide — by the stop's 권역, then the hub; none by car, none the site does not have", () => {
  const kb = kbOf({ ...FX.docs, ...GUIDES }, indexOf({ ...FX.docs, ...GUIDES }));
  const legs = (from, first, last = first, move = "transit", k = kb) => {
    const c = { from, to: from, move, start: "10:00", end: "18:00" };
    const plan = { days: [{ date: "2026-11-04", stops: [{ page: P(first), name: first, start: "12:00", end: "13:00" }, { page: P(last), name: last, start: "14:00", end: "15:00" }] }] };
    return hubLegs(plan, c, HUBS, k).map((h) => (h.guide ? h.guide.path : null));
  };
  assert.deepEqual(legs("station", "선유도해수욕장"), ["/guides/군산-시내버스-관광지/#h-b6", "/guides/군산-시내버스-관광지/#h-b6"]);   // the 99
  assert.deepEqual(legs("airport", "선유도해수욕장"), ["/guides/군산-시내버스-관광지/#h-b6", "/guides/군산-시내버스-관광지/#h-b6"]);
  assert.deepEqual(legs("airport", "초원사진관"), ["/guides/군산-시외버스-고속버스-공항/#h-b6", "/guides/군산-시외버스-고속버스-공항/#h-b6"]);
  assert.deepEqual(legs("station", "초원사진관"), ["/guides/군산-가는-법-교통/#h-b6", "/guides/군산-가는-법-교통/#h-b6"]);   // 01·18·19
  assert.deepEqual(legs("bus", "초원사진관"), ["/guides/군산-시내버스-관광지/#h-b2", "/guides/군산-시내버스-관광지/#h-b2"]);
  assert.deepEqual(legs("station", "초원사진관", "선유도해수욕장"), ["/guides/군산-가는-법-교통/#h-b6", "/guides/군산-시내버스-관광지/#h-b6"]);
  assert.deepEqual(legs("express", "비응도"), ["/guides/군산-시내버스-관광지/#h-b5", "/guides/군산-시내버스-관광지/#h-b5"]);   // 비응항's buses
  assert.deepEqual(legs("airport", "비응도"), ["/guides/군산-시외버스-고속버스-공항/#h-b6", "/guides/군산-시외버스-고속버스-공항/#h-b6"]);
  assert.deepEqual(legs("station", "은파호수공원"), ["/guides/군산-시내버스-관광지/", "/guides/군산-시내버스-관광지/"]);
  assert.deepEqual(legs("station", "선유도해수욕장", "선유도해수욕장", "car"), [null, null]);
  assert.deepEqual(legs("station", "선유도해수욕장", "선유도해수욕장", "transit", KB), [null, null]);   // no such section: no link
  const h = hubLegs({ days: [{ stops: [{ page: P("선유도해수욕장"), name: "선유도해수욕장", start: "12:00", end: "13:00" }] }] }, { from: "station", move: "transit", start: "10:00" }, HUBS, kb)[0];
  assert.deepEqual(h.guide, { path: "/guides/군산-시내버스-관광지/#h-b6", label: "99번 버스(섬) 안내" });
  assert.equal(h.need, 120);
});

test("S5: a stop swapped in for a closed day is 'closed'; for a budget or a need 'other'", async () => {
  const stops = (names) => names.map(([n, a, b, role]) => ({ page: P(n), start: a, end: b, role, why: "" }));
  const day = [["근대역사박물관", "10:00", "11:30", "visit"], ["복성루", "12:00", "13:00", "meal"], ["초원사진관", "13:20", "14:00", "visit"],
    ["군산 동국사 대웅전", "14:20", "15:30", "visit"], ["테디베어박물관", "15:50", "17:00", "visit"]];
  const swapped = (plan) => plan.days.flatMap((d) => d.stops).filter((s) => s.swapped).map((s) => s.swapped);
  // a Saturday, budget 0: the two paid museums open that day — swapped for the budget
  let { plan } = await run({ title: "t", summary: "s", notes: [], days: [{ date: "2026-10-24", stops: stops(day) }] }, { ...BASE, date: "2026-10-24", budget: 0 });
  assert.ok(plan.fixed.some((t) => /입장료 예산을 넘어/u.test(t)), plan.fixed.join("\n"));
  assert.deepEqual(swapped(plan), ["other", "other"]);
  // a Monday: 근대역사박물관 is closed — swapped for its closed day
  ({ plan } = await run({ title: "t", summary: "s", notes: [], days: [{ date: "2026-10-26", stops: stops(day) }] }, { ...BASE, date: "2026-10-26" }));
  assert.ok(plan.fixed.some((t) => /은 쉬는 날이라/u.test(t)), plan.fixed.join("\n"));
  assert.deepEqual(swapped(plan), ["closed"]);
  // the wheelchair: 말랭이마을's data says no — 'other'
  ({ plan } = await run({ title: "t", summary: "s", notes: [], days: [{ date: "2026-10-24", stops: stops([["말랭이마을", "10:00", "11:30", "visit"], ["복성루", "12:00", "13:00", "meal"],
    ["초원사진관", "13:20", "14:00", "visit"], ["근대역사박물관", "14:20", "15:30", "visit"]]) }] }, { ...BASE, date: "2026-10-24", needs: ["wheelchair"] }));
  assert.ok(plan.fixed.some((t) => /'휠체어' 조건에 맞지 않는다고 자료에 있어/u.test(t)), plan.fixed.join("\n"));
  assert.deepEqual(swapped(plan), ["other"]);
  // a Monday the sources differ on (구 조선은행 군산지점: 한국관광공사 '1월 1일' · 군산시 '매주 월요일'): swapped as the
  // closed-day rule says, but said as the difference — never 'closed', which the page reads as '그날 쉬는 곳 대신'
  // (CLAUDE.md 3절 2항; review of S5)
  ({ plan } = await run({ title: "t", summary: "s", notes: [], days: [{ date: "2026-10-26", stops: stops([["구 조선은행 군산지점", "10:00", "11:00", "visit"],
    ["복성루", "12:00", "13:00", "meal"], ["초원사진관", "13:20", "14:00", "visit"], ["군산 동국사 대웅전", "14:20", "15:40", "visit"]]) }] }, { ...BASE, date: "2026-10-26", end: "16:00" }));
  assert.ok(plan.fixed.some((t) => /^구 조선은행 군산지점: 10월 26일\(월\)은 출처마다 쉬는 날이 달라\(.+방문 전 전화 확인\) 가까운 /u.test(t)), plan.fixed.join("\n"));
  assert.deepEqual(swapped(plan), ["other"]);
});

test("C7a: across two other 권역 a leg the site has no distance for keeps its floor and repair — 30 minutes by car, 45 without (the islands' floor is 고군산's only)", () => {
  // (the plan.test.js case moved off 고군산: its 45 minutes there were the weakness the review found)
  const AREA = {
    "/places/a/": { t: "원도심관", k: "place", x: "원도심관 — 관광지 · 문화시설\n위치: 월명동 · 원도심 권역",
      f: { kd: "attraction", ty: "문화시설", g: [35.99, 126.71], c: [{ p: "공식", t: "연중무휴" }], h: [{ p: "공식", t: "09:00~18:00" }] } },
    "/places/n/": { t: "좌표없는집", k: "place", x: "좌표없는집 — 음식점 · 중식\n위치: 월명동 · 원도심 권역",
      f: { kd: "food", ty: "중식", c: [{ p: "공식", t: "연중무휴" }], h: [{ p: "공식", t: "09:00~21:00" }] } },
    "/places/b/": { t: "비응마을", k: "place", x: "비응마을 — 관광지 · 자연·야외\n위치: 비응도동 · 새만금·비응 권역",
      f: { kd: "attraction", ty: "자연·야외", g: [35.94, 126.52], c: [{ p: "공식", t: "연중무휴" }], h: [{ p: "공식", t: "상시 개방" }] } },
  };
  const k = new Knowledge({ catalog: "", docs: { v: 1, site: FX.site, docs: AREA, alias: {}, ext: [], tickets: [] }, index: indexOf(AREA) });
  const day = (c, at) => readSubmit({ title: "t", summary: "", notes: [], days: [{ date: c.date, stops: [{ page: "/places/a/", start: "10:00", end: "11:00", role: "visit" },
    { page: "/places/n/", start: "11:10", end: "12:10", role: "meal" }, { page: "/places/b/", start: at, end: "15:00", role: "visit" }] }] }, c, k).plan;
  const base = { date: "2026-10-24", days: 1, start: "10:00", end: "15:30", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null, note: "" };
  let c = validConditions({ ...base, move: "car" }, NOW);
  let p = day(c, "12:20");
  assert.deepEqual(verify(p, c, k).flags, ["1일차 2→3번 좌표없는집 → 비응마을: 좌표가 없어 거리를 모르는 다른 권역 사이(원도심 → 새만금·비응)인데 여유 10분 — 권역을 옮기는 구간의 계획 여유 30분보다 짧음 — 여유를 늘리거나 가까운 곳으로 바꾼다"]);
  assert.deepEqual(repair(p, c, k), ["비응마을: 앞 장소 좌표없는집에서 여유 30분을 두려고 시작을 12:20에서 12:40으로 늦췄습니다"]);
  assert.deepEqual(verify(p, c, k).flags, []);
  c = validConditions({ ...base, move: "transit" }, NOW);
  p = day(c, "12:40");
  assert.match(verify(p, c, k).flags.join(" "), /여유 30분 — 권역을 옮기는 구간의 계획 여유 45분보다 짧음/);
  assert.deepEqual(repair(p, c, k), ["좌표없는집: 다음 장소 비응마을까지 여유 45분을 두려고 끝을 12:10에서 11:55으로 당겼습니다"]);
  assert.deepEqual(verify(p, c, k).flags, []);
});

test("S7: the site's own course as the final plan says the note's places and dishes are not in it — never the course sent first, never with no note", async () => {
  const raw = { ...BASE, date: "2026-10-24", note: "짬뽕은 꼭 먹고 싶어요. 오후엔 바다를 보고 싶어요." };
  const c = validConditions(raw, NOW);
  const has = (p) => p.aware.filter((x) => x.t === CODE_NOTE_LINE);
  assert.deepEqual(has(codePlan(c, KB, NOW, CODE_PLAN_LINE)), [{ k: "note", t: CODE_NOTE_LINE }]);
  assert.deepEqual(has(codePlan(c, KB, NOW, CODE_PLAN_EARLY)), []);
  assert.deepEqual(has(codePlan(validConditions({ ...raw, note: "" }, NOW), KB, NOW, CODE_PLAN_LINE)), []);
  // the course sent first kept as the final one when the model refuses: the line comes with it, once
  const early = codePlan(c, KB, NOW, CODE_PLAN_EARLY);
  const sent = [];
  const refusing = { messages: { stream() {
    const message = { role: "assistant", content: [], stop_reason: "refusal", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
  await makePlan({ client: refusing, kb: KB, conditions: c, send: (e) => sent.push(e), now: NOW, early });
  const plan = sent.at(-1).plan;
  assert.deepEqual(plan.fixed, [CODE_PLAN_LINE]);
  assert.deepEqual(has(plan), [{ k: "note", t: CODE_NOTE_LINE }]);
  assert.deepEqual(has(early), []);
  // noteAware itself: the busy line too, and never twice
  assert.equal(noteAware(noteAware([], c, [CODE_PLAN_BUSY]), c, [CODE_PLAN_BUSY]).length, 1);
  assert.deepEqual(noteAware([{ k: "move", t: "x" }], c, ["다른 줄", CODE_PLAN_LINE]), [{ k: "move", t: "x" }]);
});

test("C6, daybounds, S8: the prompt — 걷기 적게 in rule 6, the other days' start, the title in rule 9, the stations' margins", () => {
  const PLAN_RULES = planRules();   // the first city's (its meta: the knowledge bases above)
  assert.match(PLAN_RULES, /Little walking \(걷기 적게\): keep each day in one 권역, with fewer and longer stops at places with more to do/u);
  assert.match(PLAN_RULES, /never write that the plan walks less/u);
  // (2026-10-24 I07: the reader's start and end hold every day — the check's rule, said as it is)
  assert.match(PLAN_RULES, /every day from the start they set to the end they set — no stop but the night's stay starts before that start or ends after that end, on any day —/u);
  assert.match(PLAN_RULES, /or that a pram or a wheelchair gets around easily \(유모차로 다니기 편한, 휠체어로 이동하기 쉬운 — the site has no data on getting around\), in the title, the summary, a why or a note\./u);
  assert.match(PLAN_RULES, /2 hours without a car, 1 hour by car, to or from 고군산/u);
  const two = conditionsText(validConditions({ ...BASE, date: "2026-10-24", days: 2 }, NOW));
  assert.match(two, /하루 일정 시간: 10:00~18:00 \(날마다 이 시간 안 — 숙소만 끝 뒤에\)/u);
});
