// The course planner by the data's own words (영주·세종 집중 분석 2026-10-24, the same engine): an access route the data
// says is steep, hard or reached by car (I03), the reader's 하루 시작·하루 끝 on every day (I07) — for the places to visit
// and the cafés only, a day before a night having its dinner and its stay after the end (operator 2026-10-24) — and
// sources that price a combined ticket or a place differently (YJ-04). The values are the sites' own (세종·영주 /chat/docs.json, 군산
// tests/fixtures/plan_places.json — public/chat cut to the planner's fields).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge, tokens } from "../../chatbot/knowledge.js";
import { planFees } from "../../chatbot/plan_fees.js";
import { hardState } from "../../chatbot/plan_geo.js";
import { hm, isCafe, mealSlot, needAt } from "../../chatbot/plan_state.js";
import { preflight } from "../../chatbot/plan_build.js";
import { codePlan, makePlan, readSubmit, validConditions, verify } from "../../chatbot/planner.js";

const NOW = new Date("2026-10-24T01:00:00Z");   // 2026-10-24 (Sat) 10:00 KST
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_places.json", import.meta.url), "utf8"));
const indexOf = (docs) => ({ v: 1, docs: Object.fromEntries(Object.entries(docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) });
const KB = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs: FX.docs, alias: {}, ext: [], tickets: FX.tickets }, index: indexOf(FX.docs) });
const P = (name) => Object.keys(FX.docs).find((k) => FX.docs[k].t === name);

// 세종 /places/gountteulgongwon/ (한국관광공사 무장애 여행 정보(TourAPI))
const GOUNTTEUL = "경사로가 가파른 편으로 휠체어와 유모차 접근은 다소 어려울 수 있으나 고운뜰전망대 방향쪽으로는 차량으로 접근 할 수 있어 휠체어도 함께 올라 전망 관람 가능";
const route = (t) => ({ kd: "attraction", ac: [{ k: "accessible_route", p: "한국관광공사 무장애 여행 정보(TourAPI)", t }] });

test("I03: a route the data calls steep or hard is no fit; one reached by car is conditional by car, not known without one", () => {
  // (before: 'ok' for both — '가파르' missed '가파른', '어려울 수'·'다소'·'차량으로 접근' were not read)
  const f = route(GOUNTTEUL);
  assert.deepEqual(needAt("wheelchair", f, "visit", null, "transit"), { state: "unknown", text: `출입구: ${GOUNTTEUL} — 확인 필요` });
  assert.deepEqual(needAt("wheelchair", f, "visit", null, "car"), { state: "cond", text: `출입구: ${GOUNTTEUL} — 조건부(차량으로 접근할 때)` });
  assert.equal(needAt("stroller", f, "visit", null, "transit").state, "unknown");
  assert.equal(needAt("stroller", f, "visit", null, "car").state, "cond");
  // a sentence that says there is no ramp is 'no'; a gentle ramp is 'ok' for both (군산 values)
  assert.equal(needAt("wheelchair", route("출입구에 경사로가 설치되어 있지 않음"), "visit").state, "no");
  assert.equal(needAt("wheelchair", route("출입구까지 경사로가 설치되어 있음(완만함)"), "visit", null, "car").state, "ok");
  // the code never puts a conditional route in on its own: it is the reader's to check, as one the data does not know
  for (const move of ["car", "transit"]) assert.equal(hardState({ needs: ["wheelchair"], move }, f, "visit"), "unknown");
});

test("I03: the needs table and the checks say a conditional route with its condition", () => {
  const docs = { "/places/gounteul/": { t: "고운뜰공원", k: "place", x: "고운뜰공원 — 관광지", f: { ...route(GOUNTTEUL), g: [36.5, 127.25], h: [{ p: "한국관광공사 TourAPI", t: "상시 개방" }],
    c: [{ p: "한국관광공사", t: "연중무휴" }], fee: { free: true, p: "한국관광공사 TourAPI", t: "무료" } } } };
  const kb = new Knowledge({ catalog: "# c", docs: { v: 1, site: FX.site, docs, alias: {}, ext: [], tickets: [] }, index: indexOf(docs) });
  const c = validConditions({ date: "2026-10-25", days: 1, start: "10:00", end: "13:00", move: "car", with: "parents", adults: 2, kids: [], prefs: [], needs: ["wheelchair"], budget: null }, NOW);
  const { plan } = readSubmit({ title: "t", summary: "", notes: [], days: [{ date: c.date, stops: [{ page: "/places/gounteul/", start: "10:00", end: "11:00", role: "visit", why: "" }] }] }, c, kb);
  const v = verify(plan, c, kb);
  assert.equal(v.needs[0].rows[0].state, "cond");
  assert.ok(v.checks.some((x) => x.k === "need" && x.t === `휠체어: 고운뜰공원 — 출입구: ${GOUNTTEUL} — 조건부(차량으로 접근할 때)`), JSON.stringify(v.checks));
});

test("I07: the reader's 하루 시작·하루 끝 hold every day — a stop past the end of the first day, before the start of the second", () => {
  // (before: a 2-day trip 10:00~18:00 passed with a visit 18:00–19:00 on the first day and 08:00–09:00 on the second)
  const c = validConditions({ date: "2026-11-03", days: 2, start: "10:00", end: "18:00", move: "car", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null }, NOW);
  const day = (date, stops) => ({ date, stops: stops.map(([name, start, end, role = "visit"]) => ({ page: P(name), start, end, role, why: "" })) });
  const { plan } = readSubmit({ title: "t", summary: "", notes: [], days: [
    day("2026-11-03", [["근대역사박물관", "10:00", "11:30"], ["군산항1981", "18:00", "19:00"]]),
    day("2026-11-04", [["진포해양공원", "08:00", "09:00"], ["테디베어박물관", "10:00", "11:00"]])] }, c, KB);
  const v = verify(plan, c, KB);
  const said = v.list.filter((x) => x.kind === "start" || x.kind === "end").map((x) => x.text);
  assert.deepEqual(said, ["1일차 군산항1981: 독자가 정한 끝 18:00보다 늦다", "2일차 진포해양공원: 독자가 정한 시작 10:00보다 이르다"]);
});

// (operator 2026-10-24: '하루 시작·끝은 여러 날 일정의 모든 날에 적용하되 관람만 제한한다' — I07 had held the dinner to the
// end too, and a day before a night set to the form's 18:00 lost its dinner)
const C2 = { date: "2026-11-03", days: 2, start: "10:00", end: "18:00", move: "car", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null };
const dayOf = (date, stops) => ({ date, stops: stops.map(([name, start, end, role = "visit"]) => ({ page: P(name), start, end, role, why: "" })) });
const TUE = [["근대역사박물관", "10:00", "11:30"], ["한일옥", "12:00", "13:00", "meal"], ["군산근대건축관", "13:20", "14:40"], ["진포해양공원", "15:00", "16:20"], ["군산항1981", "16:40", "17:45"]];
const WED = [["테디베어박물관", "10:00", "11:30"], ["복성루", "12:00", "13:00", "meal"], ["은파호수공원", "13:30", "15:30"], ["초원사진관", "16:00", "17:30"]];
const rows = (d) => d.stops.map((s) => [s.name, s.start, s.end, s.role]);

test("operator 2026-10-24: the end holds the places to visit and the cafés every day — a day before a night has its dinner in its window and its stay after it, the last day ends at the end", () => {
  const c = validConditions(C2, NOW);
  const ends = (d1, d2 = WED) => {
    const { plan } = readSubmit({ title: "t", summary: "", notes: [], days: [dayOf("2026-11-03", d1), dayOf("2026-11-04", d2)] }, c, KB);
    return verify(plan, c, KB).list.filter((x) => x.kind === "end").map((x) => x.text);
  };
  const stay = ["베스트웨스턴 군산호텔", "19:25", "20:25", "stay"];
  // the dinner 18:00–19:00 after the 18:00 end of the first day, the night's stay after it: nothing past the end to fix
  assert.deepEqual(ends([...TUE, ["유락식당", "18:00", "19:00", "meal"], stay]), []);
  // a café there, or a place to visit, is past the end on any day
  assert.deepEqual(ends([...TUE, ["이성당", "18:00", "18:40", "cafe"], stay]), ["1일차 이성당: 독자가 정한 끝 18:00보다 늦다"]);
  assert.deepEqual(ends([...TUE.slice(0, -1), ["초원사진관", "16:40", "18:30"], stay], WED.slice(0, -1)), ["1일차 초원사진관: 독자가 정한 끝 18:00보다 늦다"]);
  // a dinner past the dinner's window (20:00–21:00: its middle at 20:30) is past the end too
  assert.deepEqual(ends([...TUE, ["한일옥", "20:00", "21:00", "meal"], ["베스트웨스턴 군산호텔", "21:20", "22:20", "stay"]].filter((x, j) => j !== 1)), ["1일차 한일옥: 독자가 정한 끝 18:00보다 늦다"]);
  // the last day: no night follows it — its dinner keeps to the end as every stop does
  assert.deepEqual(ends([...TUE, stay.map((x, j) => (j === 1 ? "18:10" : j === 2 ? "19:10" : x))], [...WED, ["콩뜰", "18:00", "19:00", "meal"]]), ["2일차 콩뜰: 독자가 정한 끝 18:00보다 늦다"]);
});

test("operator 2026-10-24: the site's own course puts a day before a night's dinner after an 18:00 end and says so — none when the end is before 17:30, the reader eats elsewhere or no restaurant is open then", () => {
  const c = validConditions(C2, NOW);
  const built = codePlan(c, KB, NOW, "일정 전체: x");
  const [d1, d2] = built.days;
  const dinner = d1.stops.find((s) => s.role === "meal" && hm(s.start) >= 16 * 60);
  assert.ok(dinner && hm(dinner.end) > hm("18:00") && mealSlot(hm(dinner.start), hm(dinner.end)) === "dinner", JSON.stringify(rows(d1)));
  // every place to visit by 18:00, the stay after the dinner; the last day by 18:00 for every stop
  assert.ok(d1.stops.filter((s) => s.role === "visit" || s.role === "cafe").every((s) => hm(s.end) <= hm("18:00")), JSON.stringify(rows(d1)));
  assert.equal(d1.stops.at(-1).role, "stay");
  assert.ok(hm(d1.stops.at(-1).start) >= hm(dinner.end));
  assert.ok(d2.stops.every((s) => hm(s.end) <= hm("18:00")), JSON.stringify(rows(d2)));
  // said as it is, once for the day
  const stay = d1.stops.at(-1);
  assert.deepEqual(built.aware.filter((x) => x.k === "end").map((x) => x.t),
    [`1일차 하루 끝 18:00 뒤까지: 저녁 ${dinner.name} ${dinner.start}~${dinner.end} · 밤 숙소 ${stay.name} ${stay.start}부터 — 둘러볼 곳·카페는 날마다 하루 끝 안에 넣어요`]);
  assert.ok(built.complete.meals.some((m) => m.day === 0 && m.kind === "dinner" && m.state === "added"));
  // a day to 17:00 goes to the night's stay with no dinner of the code's; one whose reader eats dinner elsewhere too
  for (const x of [{ end: "17:00" }, { note: "저녁은 따로 먹어요" }]) {
    const p = codePlan(validConditions({ ...C2, ...x }, NOW), KB, NOW, "일정 전체: x");
    assert.ok(!p.days[0].stops.some((s) => s.role === "meal" && hm(s.start) >= 16 * 60), JSON.stringify(rows(p.days[0])));
    assert.ok(!p.complete.meals.some((m) => m.state === "missing"));
  }
  // no restaurant open in the evening: the dinner after the end is no fault — the trip is built, nothing missing
  const docs = Object.fromEntries(Object.entries(FX.docs).map(([k, d]) => [k, d.f && d.f.kd === "food" ? { ...d, f: { ...d.f, h: [{ p: "t", t: "10:00~16:00" }] } } : d]));
  const day = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs, alias: {}, ext: [], tickets: FX.tickets }, index: indexOf(docs) });
  assert.deepEqual(preflight(c, day, NOW), []);
  const p = codePlan(c, day, NOW, "일정 전체: x");
  assert.ok(p && !p.days[0].stops.some((s) => s.role === "meal" && hm(s.start) >= 16 * 60), p && JSON.stringify(rows(p.days[0])));
  assert.ok(!p.complete.meals.some((m) => m.state === "missing"));
});

test("operator 2026-10-24: a model's day before a night that ends at 18:00 with no dinner gets one after the end — the night's stay moves after it", async () => {
  const c = validConditions(C2, NOW);
  const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
  const input = { title: "t", summary: "", notes: [], days: [dayOf("2026-11-03", [...TUE, ["베스트웨스턴 군산호텔", "18:10", "19:10", "stay"]]), dayOf("2026-11-04", WED)] };
  const client = { messages: { stream() {
    const message = { role: "assistant", content: [{ type: "tool_use", id: "toolu_1", name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
  const sent = [];
  await makePlan({ client, kb: KB, conditions: c, send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.deepEqual([plan.status, plan.flags], ["ready", []]);
  const d1 = plan.days[0];
  const dinner = d1.stops.find((s) => s.role === "meal" && !isCafe(KB.docs[s.path]) && hm(s.start) >= 16 * 60);
  assert.ok(dinner && hm(dinner.start) >= hm("17:45") && mealSlot(hm(dinner.start), hm(dinner.end)) === "dinner", JSON.stringify(rows(d1)));
  assert.deepEqual(rows(d1).at(-1).slice(0, 1).concat(rows(d1).at(-1).slice(3)), ["베스트웨스턴 군산호텔", "stay"]);
  assert.ok(hm(d1.stops.at(-1).start) > hm(dinner.end));
  assert.ok(plan.fixed.some((t) => t.startsWith(`1일차 저녁: 식사할 곳이 없어 `) && t.includes(`${dinner.name}(`) && t.includes(`${dinner.start}~${dinner.end}에 넣었습니다`)), plan.fixed.join("\n"));
  assert.ok(plan.fixed.some((t) => t.startsWith(`1일차 밤 숙소 베스트웨스턴 군산호텔: 그날 마지막 장소 ${dinner.name} 뒤로 시작을 18:10에서 `)), plan.fixed.join("\n"));
  // the last day is the model's as it was: nothing past its end
  assert.deepEqual(rows(plan.days[1]), WED.map(([n, a, b, r = "visit"]) => [n, a, b, r]));
});

test("review 2026-10-24: a model's dinner the check takes out after the end of a day before a night — past the restaurant's hours or the dinner's window — gives way to one in the window", async () => {
  const c = validConditions(C2, NOW);
  const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
  // 유락식당 closes at 20:30 (20:00–21:00 past its hours); 콩뜰 is open till 21:00 but 20:00–21:00 is past the window
  for (const [din, gone] of [[["유락식당", "20:00", "21:00", "meal"], "1일차 유락식당: 그 시각에 열지 않는다고 자료에 있어 일정에서 뺐습니다"],
    [["콩뜰", "20:00", "21:00", "meal"], "1일차 콩뜰: 고른 끝 18:00 뒤라 일정에서 뺐습니다"]]) {
    const input = { title: "t", summary: "", notes: [], days: [dayOf("2026-11-03", [...TUE, din, ["베스트웨스턴 군산호텔", "21:20", "22:20", "stay"]]), dayOf("2026-11-04", WED)] };
    const client = { messages: { stream() {
      const message = { role: "assistant", content: [{ type: "tool_use", id: "toolu_1", name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
      return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
    } } };
    const sent = [];
    await makePlan({ client, kb: KB, conditions: c, send: (e) => sent.push(e), now: NOW });
    const plan = sent.at(-1).plan;
    assert.deepEqual([plan.status, plan.flags], ["ready", []]);
    const d1 = plan.days[0];
    const dinner = d1.stops.find((s) => s.role === "meal" && !isCafe(KB.docs[s.path]) && hm(s.start) >= 16 * 60);
    assert.ok(dinner && hm(dinner.start) >= hm("17:45") && mealSlot(hm(dinner.start), hm(dinner.end)) === "dinner", JSON.stringify(rows(d1)));
    // (the model's restaurant back in the window says only where it went in: the page's lines of one place merge)
    if (dinner.name !== din[0]) assert.ok(plan.fixed.includes(gone), plan.fixed.join("\n"));
    assert.ok(plan.fixed.some((t) => t.startsWith("1일차 저녁: 식사할 곳이 없어 ") && t.includes(`${dinner.start}~${dinner.end}에 넣었습니다`)), plan.fixed.join("\n"));
    assert.ok(d1.stops.filter((s) => s.role !== "meal" && s.role !== "stay").every((s) => hm(s.end) <= hm("18:00")), JSON.stringify(rows(d1)));
    assert.equal(d1.stops.at(-1).role, "stay");
    assert.ok(hm(d1.stops.at(-1).start) > hm(dinner.end));
  }
});

// 영주 /places/yeongju-sosuseowon/, /places/seonbichon/, /places/sosubangmulgwan/ (fee values as the site has them)
const YJ = {
  "/places/yeongju-sosuseowon/": { t: "영주 소수서원", k: "place", x: "영주 소수서원", f: { kd: "attraction", g: [36.92, 128.58],
    fee: { p: "한국관광공사 TourAPI", t: "[개인]- 어른 2,000원- 청소년, 군인 1,330원- 어린이 660원 [단체(20인 이상)]- 어른 1,660원- 청소년, 군인 1,000원- 어린이 530원 ※ 자세한 사항은 전화문의 요망",
      tab: { 성인: 2000, 어린이: 660, "청소년·군인": 1330 }, tl: "개인",
      alt: [{ p: "영주시 문화관광", t: "어른 3,000원 / 청소년·군인 2,000원 / 어린이 1,000원 (소수서원·선비촌·소수박물관 통합 관람권)" }] } } },
  "/places/seonbichon/": { t: "선비촌", k: "place", x: "선비촌", f: { kd: "attraction", g: [36.92, 128.58],
    fee: { p: "한국관광공사 TourAPI", t: "[개인]- 어른 3,000원- 청소년·군인 2,000원- 어린이 1,000원[단체]- 어른 2,500원- 청소년·군인 1,500원- 어린이 800원",
      tab: { 성인: 3000, 어린이: 1000, "청소년·군인": 2000 }, tl: "개인",
      alt: [{ p: "영주시 문화관광", t: "어른 3,000원 / 청소년·군인 2,000원 / 어린이 1,000원 (소수서원·선비촌 통합, 한옥숙박 45,000원~140,000원)" }] } } },
  "/places/sosubangmulgwan/": { t: "소수박물관", k: "place", x: "소수박물관", f: { kd: "attraction", g: [36.92, 128.58],
    fee: { p: "한국관광공사 TourAPI", t: "- 성인 3,000원 - 청소년, 군인 2,000원 - 어린이 (초등학생) 1,000원 ※ 이용요금은 변동될 수 있으므로 홈페이지 참고", tab: { 성인: 3000, 어린이: 1000, "청소년·군인": 2000 } } } },
};
const yjKb = (tickets = []) => new Knowledge({ catalog: "# c", docs: { v: 1, site: FX.site, docs: YJ, alias: {}, ext: [], tickets }, index: indexOf(YJ) });
const visit = (page) => ({ page, name: YJ[page].f && YJ[page].t, role: "visit" });

test("YJ-04: a place two sources price differently is no known total — both values, the phone check, the budget open", () => {
  // (before: 10,000원 'known', a budget of 10,000원 'within')
  const fees = planFees([{ date: "2026-10-25", stops: [visit("/places/yeongju-sosuseowon/"), visit("/places/seonbichon/")] }], { adults: 2, seniors: 0, kids: [] }, yjKb(), 10000);
  assert.equal(fees.state, "partial");
  assert.equal(fees.total, null);
  assert.equal(fees.verdict, "open");
  assert.deepEqual(fees.open, ["영주 소수서원: 출처마다 성인 요금이 다름 — 한국관광공사 TourAPI 2,000원 / 영주시 문화관광 3,000원 — 방문 전 전화 확인"]);
  // 선비촌's other source writes the same adult price: no dispute, its line stays a condition
  assert.ok(fees.conds.some((t) => t.startsWith("선비촌: 다른 출처의 요금 값")), fees.conds.join("\n"));
});

test("YJ-04: the other source's value is never lost, and a combined price that may cost less leaves the budget open", () => {
  // (review 2026-10-24) two 65+ visitors: no adult under 65 pays by the table, so no dispute line — the other source's
  // value stays a condition (before: dropped from the conditions with no line saying it)
  const old = planFees([{ date: "2026-10-25", stops: [visit("/places/yeongju-sosuseowon/")] }], { adults: 2, seniors: 2, kids: [] }, yjKb(), null);
  assert.ok(old.conds.some((t) => t.startsWith("영주 소수서원: 다른 출처의 요금 값 '어른 3,000원")), old.conds.join("\n"));
  // the three places by their own tables are 16,000원 for two adults, past a 10,000원 budget — but 영주시 문화관광 writes
  // one combined ticket of 3,000원 for all three: 'over' is not certain (before: 'over')
  const stops = [visit("/places/yeongju-sosuseowon/"), visit("/places/seonbichon/"), visit("/places/sosubangmulgwan/")];
  const fees = planFees([{ date: "2026-10-25", stops }], { adults: 2, seniors: 0, kids: [] }, yjKb(), 10000);
  assert.deepEqual([fees.state, fees.total, fees.known, fees.verdict], ["partial", null, 16000, "open"]);
  // a higher price only, from the other source: what is known is a floor — past the budget is 'over'
  const high = { ...YJ, "/places/sosubangmulgwan/": { ...YJ["/places/sosubangmulgwan/"], f: { ...YJ["/places/sosubangmulgwan/"].f,
    fee: { ...YJ["/places/sosubangmulgwan/"].f.fee, alt: [{ p: "영주시 문화관광", t: "어른 4,000원" }] } } } };
  const k = new Knowledge({ catalog: "# c", docs: { v: 1, site: FX.site, docs: high, alias: {}, ext: [], tickets: [] }, index: indexOf(high) });
  const over = planFees([{ date: "2026-10-25", stops: [visit("/places/sosubangmulgwan/")] }], { adults: 2, seniors: 0, kids: [] }, k, 5000);
  assert.deepEqual([over.state, over.known, over.verdict], ["partial", 6000, "over"]);
});

test("YJ-04: a combined ticket two sources price differently is no known total either — never one picked as certain", () => {
  // the two tables the analysis read (2026-10-24): 소수서원 관람안내 (영주시, 어른 2,000원) and the city's tour portal
  // (어른 3,000원) for the same three places
  const places = [{ name: "영주 소수서원", path: "/places/yeongju-sosuseowon/" }, { name: "선비촌", path: "/places/seonbichon/" }, { name: "소수박물관", path: "/places/sosubangmulgwan/" }];
  const tickets = [
    { id: "sosu-a", name: "통합 관람권", places, prices: { 개인: { 성인: [2000], "청소년·군인": [1330], 어린이: [660] } }, rules: [], src: "영주시 소수서원 관람안내" },
    { id: "sosu-b", name: "통합 관람권", places, prices: { 개인: { 성인: [3000], "청소년·군인": [2000], 어린이: [1000] } }, rules: [], src: "영주시 문화관광" }];
  const stops = [visit("/places/yeongju-sosuseowon/"), visit("/places/seonbichon/"), visit("/places/sosubangmulgwan/")];
  const fees = planFees([{ date: "2026-10-25", stops }], { adults: 2, seniors: 0, kids: [] }, yjKb(tickets), 10000);
  assert.equal(fees.known, 4000);   // the ticket once, by the lower table
  assert.deepEqual([fees.state, fees.total, fees.verdict], ["partial", null, "open"]);
  assert.ok(fees.open.includes("통합 관람권: 출처마다 성인 요금이 다름 — 영주시 소수서원 관람안내 2,000원 / 영주시 문화관광 3,000원 — 방문 전 전화 확인"), fees.open.join("\n"));
  // 소수서원's other source writes a combined price other than the ticket's: said too
  assert.ok(fees.open.includes("영주 소수서원: 출처마다 성인 요금이 다름 — 통합 관람권 영주시 소수서원 관람안내 2,000원 / 영주시 문화관광 3,000원 — 방문 전 전화 확인"), fees.open.join("\n"));
  // one table only: the total is known
  const one = planFees([{ date: "2026-10-25", stops: [visit("/places/seonbichon/"), visit("/places/sosubangmulgwan/")] }], { adults: 2, seniors: 0, kids: [] }, yjKb([tickets[1]]), 10000);
  assert.deepEqual([one.state, one.total, one.verdict], ["known", 6000, "within"]);
});

test("YJ-04 on 군산's own tickets: the 박물관 통합권 with its places is priced as before — one table, no dispute", () => {
  const stops = ["근대역사박물관", "진포해양공원"].map((name) => ({ page: P(name), name, role: "visit" }));
  const fees = planFees([{ date: "2026-11-03", stops }], { adults: 2, seniors: 0, kids: [] }, KB, 10000);
  assert.ok(!fees.open.some((t) => /출처마다 성인 요금이 다름/u.test(t)), fees.open.join("\n"));
});
