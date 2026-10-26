// A stop's own buttons on the result (operator 2026-10-23, mockup A — '니 추천대로 진행하고 배포해'): 빼기 and 다른 곳으로
// are made by the code alone (planner actOn, no model call) on the plan the page shows, sent as an edit with an act, and
// 고정 pins a stop the server then keeps on its day in every later edit (pins). The places are the site's own
// (tests/fixtures/plan_places.json: every place of public/chat, cut to the planner's fields); the model, where there is
// one, is a fake that hands the same submit_plan over on every call.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge } from "./first_city.js";
import { tokens } from "../../chatbot/knowledge.js";
import { codePlan, createPlanHandler, editPlaces, makePlan, validConditions, validEdit, verify } from "../../chatbot/planner.js";
import { codeText } from "../../chatbot/plan_build.js";
import { compactOf } from "../../chatbot/plan_share.js";
import { createLimiter } from "../../chatbot/server.js";

const NOW = new Date("2026-10-23T01:00:00Z");   // 2026-10-23 (Fri) 10:00 KST
const SITE = "https://gunsan.webforai.kr";
const SECRET = "test-share-secret-0123456789abcdef";
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_places.json", import.meta.url), "utf8"));
const indexOf = (docs) => ({ v: 1, docs: Object.fromEntries(Object.entries(docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) });
const KB = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs: FX.docs, alias: {}, ext: [], tickets: FX.tickets }, index: indexOf(FX.docs) });
const P = (name) => {
  const k = Object.keys(FX.docs).find((x) => FX.docs[x].t === name);
  if (!k) throw new Error(`no place ${name}`);
  return k;
};
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
// a model that hands the same submit_plan over on every call; calls: the messages each call was sent
function client(input, calls = []) {
  return { calls, messages: { stream(params) {
    calls.push(structuredClone(params.messages));
    const message = { role: "assistant", content: [{ type: "tool_use", id: `toolu_${calls.length}`, name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
// no model at all: an act never calls one
const NONE = { messages: { stream() { throw new Error("an act called the model"); } } };
const S = (name, start, end, role = "visit") => ({ page: P(name), start, end, role, why: "" });
// a Saturday in the old town, two adults by bus
const RAW = { date: "2026-10-24", days: 1, start: "10:00", end: "18:00", move: "transit", with: "couple", adults: 2, seniors: 0, kids: [],
  from: "", to: "", prefs: ["history"], needs: [], budget: null, note: "" };
const DAY = [S("근대역사박물관", "10:00", "11:30"), S("초원사진관", "11:50", "12:30"), S("쌍용반점", "12:40", "13:40", "meal"),
  S("군산신흥동일본식가옥(히로쓰가옥)", "14:00", "14:50"), S("동국사", "15:00", "15:40"), S("경암동 철길마을", "16:10", "17:10")];

/** The course the reader sees (makePlan with the model's day): {c, plan, page — its stops as the page sends them}. */
async function shown({ raw = RAW, day = DAY, title = "원도심 근대 골목 하루", summary = "근대역사박물관에서 시작해 원도심 골목을 걷습니다." } = {}) {
  const c = validConditions(raw, NOW);
  const sent = [];
  await makePlan({ client: client({ title, summary, notes: [], days: [{ date: c.date, stops: day }] }), kb: KB, conditions: c, send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.ok(plan && plan.status === "ready", JSON.stringify(sent.at(-1)));
  return { c, plan, page: pageOf(plan) };
}
const pageOf = (plan) => ({ days: plan.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, start: s.start, end: s.end, role: s.role, why: s.why })) })) });
/** An act on the plan shown: the last event the server sends ({type: 'plan', plan, act} or an error). */
async function act(c, plan, a, pins) {
  const edit = validEdit(pageOf(plan), undefined, c, { act: a, pins });
  editPlaces(edit, KB);
  edit.words = { t: plan.title, s: plan.summary, n: plan.notes };
  const sent = [];
  const t0 = Date.now();
  await makePlan({ client: NONE, kb: KB, conditions: c, edit, send: (e) => sent.push(e), now: NOW });
  return { ev: sent.at(-1), ms: Date.now() - t0, steps: sent.filter((e) => e.type === "status").map((e) => e.step) };
}
/** A typed edit with the fake model handing `back` over. */
async function edit(c, plan, request, back, pins) {
  const e = validEdit(pageOf(plan), request, c, { pins });
  editPlaces(e, KB);
  const calls = [];
  const sent = [];
  await makePlan({ client: client({ title: plan.title, summary: "", notes: [], days: back }, calls), kb: KB, conditions: c, edit: e, send: (x) => sent.push(x), now: NOW });
  return { ev: sent.at(-1), calls };
}
const pages = (plan) => plan.days.flatMap((d) => d.stops.map((s) => s.path));
const at = (plan, page) => plan.days[0].stops.find((s) => s.path === page);
const hm = (t) => +t.slice(0, 2) * 60 + +t.slice(3);

test("빼기: the stop goes, the stops after it come sooner as far as their hours, meals and legs allow — by the code alone, at once", async () => {
  const { c, plan } = await shown();
  const { ev, ms, steps } = await act(c, plan, { op: "drop", day: 0, page: P("초원사진관") });
  assert.equal(ev.type, "plan", JSON.stringify(ev));
  const out = ev.plan;
  assert.equal(out.status, "ready");
  assert.deepEqual(out.flags, []);
  assert.ok(!pages(out).includes(P("초원사진관")));
  assert.deepEqual(steps, ["fees"]);   // no search, no model round
  assert.ok(ms < 2000, `${ms} ms`);
  // the gap closes: the four after it an hour sooner — the lunch still the lunch (11:40, in its window, after the
  // museum's leg margin), the rest the same lengths and legs
  assert.deepEqual(out.days[0].stops.map((s) => [s.name, s.start, s.end]), [["근대역사박물관", "10:00", "11:30"], ["쌍용반점", "11:40", "12:40"],
    ["군산신흥동일본식가옥(히로쓰가옥)", "13:00", "13:50"], ["동국사", "14:00", "14:40"], ["경암동 철길마을", "15:10", "16:10"]]);
  assert.ok(out.days[0].legs.every((l) => l.gap >= 10 && !l.flag), JSON.stringify(out.days[0].legs));
  // the page's lines: what the button did; the page adds the times that moved
  assert.deepEqual(out.edited, [{ k: "act", t: "초원사진관을 뺐어요 — 뒤 장소 4곳을 1시간 당겼어요" }]);
  assert.deepEqual(ev.act, { op: "drop", day: 0, from: P("초원사진관"), to: null });
  // the plan's own words stay
  assert.equal(out.title, plan.title);
});

test("빼기 never puts the place back: the day's only dinner taken out gets a different restaurant, said so — where a typed edit the model left the dinner out of gets the very same one back", async () => {
  const raw = { ...RAW, end: "20:00" };
  const day = [S("근대역사박물관", "10:00", "11:30"), S("아리랑", "11:40", "12:40", "meal"), S("초원사진관", "13:00", "13:40"),
    S("군산신흥동일본식가옥(히로쓰가옥)", "14:00", "14:50"), S("동국사", "15:00", "15:40"), S("경암동 철길마을", "16:10", "17:10"),
    S("전주우족설렁탕", "17:40", "18:40", "meal")];
  const { c, plan, page } = await shown({ raw, day });
  // (the rule that puts a dinner back: the nearest restaurant open then — 전주우족설렁탕 itself, when nothing keeps it out)
  const typed = await edit(c, plan, "저녁 식당은 다른 데 가고 싶어요", [{ date: c.date, stops: page.days[0].stops.filter((s) => s.page !== P("전주우족설렁탕")) }]);
  assert.ok(pages(typed.ev.plan).includes(P("전주우족설렁탕")), "the meal rule's own pick");
  const { ev } = await act(c, plan, { op: "drop", day: 0, page: P("전주우족설렁탕") });
  const out = ev.plan;
  assert.equal(out.status, "ready");
  assert.ok(!pages(out).includes(P("전주우족설렁탕")), pages(out).join(","));
  const dinner = out.days[0].stops.filter((s) => s.role === "meal" && hm(s.start) >= 17 * 60);
  assert.equal(dinner.length, 1, JSON.stringify(out.days[0].stops));
  assert.equal(out.edited[0].t, "전주우족설렁탕을 뺐어요");
  assert.equal(out.edited[1].k, "act");
  assert.equal(out.edited[1].t.replace(/[을를] /u, " "), `저녁 자리가 비어 사이트가 가까운 ${dinner[0].name} ${dinner[0].start}~${dinner[0].end}에 넣었어요`);
  assert.equal(dinner[0].added, true);
  // and a lunch taken out: another restaurant at lunch, the stops after it moved as the meal rule needs
  const lunch = await act(c, plan, { op: "drop", day: 0, page: P("아리랑") });
  assert.ok(!pages(lunch.ev.plan).includes(P("아리랑")));
  const l = lunch.ev.plan.days[0].stops.filter((s) => s.role === "meal" && hm(s.start) < 15 * 60);
  assert.equal(l.length, 1);
  assert.ok(hm(l[0].start) >= 11 * 60 && hm(l[0].end) <= 14 * 60 + 30, JSON.stringify(l));
});

test("빼기 of the day's last stop: the long end of the day is filled as any plan's — never with the place taken out", async () => {
  const { c, plan } = await shown();
  const { ev } = await act(c, plan, { op: "drop", day: 0, page: P("경암동 철길마을") });
  assert.equal(ev.plan.status, "ready");
  assert.ok(!pages(ev.plan).includes(P("경암동 철길마을")));
  assert.equal(ev.plan.edited[0].t, "경암동 철길마을을 뺐어요");
  // 15:40–18:00 would be more than two hours with nothing: a place the code put in, said so
  assert.ok(ev.plan.edited.slice(1).some((x) => /^빈 시간이 길어 사이트가 가까운 .+ 넣었어요$/u.test(x.t)), JSON.stringify(ev.plan.edited));
});

test("빼기 of a night's stay the next night shares: that night gets another stay, said so — never the same one from the other night", async () => {
  const raw = { ...RAW, days: 3 };
  const stay = S("행복을 꿈꾸는 게스트하우스", "20:00", "21:00", "stay");
  const day = (date, ...stops) => ({ date, stops });
  const days = [day("2026-10-24", S("근대역사박물관", "10:00", "11:30"), S("쌍용반점", "11:40", "12:40", "meal"), S("초원사진관", "13:00", "13:40"),
    S("동국사", "14:00", "15:00"), S("경암동 철길마을", "15:30", "17:00"), S("한일옥", "17:30", "18:30", "meal"), stay),
  day("2026-10-25", S("군산항1981", "10:00", "11:30"), S("아리랑", "11:40", "12:40", "meal"), S("테디베어박물관", "13:00", "14:30"),
    S("말랭이마을", "15:00", "16:00"), S("월명공원", "16:20", "17:20"), S("명월갈비", "17:40", "18:40", "meal"), { ...stay }),
  day("2026-10-26", S("은파호수공원", "10:00", "11:30"), S("전주우족설렁탕", "12:00", "13:00", "meal"), S("진포해양공원", "13:30", "15:00"))];
  const c = validConditions(raw, NOW);
  const sent = [];
  await makePlan({ client: client({ title: "군산 2박 3일", summary: "", notes: [], days }), kb: KB, conditions: c, send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.ok(plan, JSON.stringify(sent.at(-1)));
  const night = (p, i) => p.days[i].stops.find((s) => s.role === "stay");
  assert.equal(night(plan, 0).path, P("행복을 꿈꾸는 게스트하우스"));
  assert.equal(night(plan, 1).path, P("행복을 꿈꾸는 게스트하우스"));
  const { ev } = await act(c, plan, { op: "drop", day: 0, page: P("행복을 꿈꾸는 게스트하우스") });
  assert.equal(ev.plan.status, "ready");
  assert.ok(night(ev.plan, 0) && night(ev.plan, 0).path !== P("행복을 꿈꾸는 게스트하우스"), JSON.stringify(night(ev.plan, 0)));
  assert.equal(night(ev.plan, 1).path, P("행복을 꿈꾸는 게스트하우스"));   // the other night as it was
  assert.equal(ev.plan.edited[0].t, "1일차 행복을 꿈꾸는 게스트하우스를 뺐어요");
  assert.match(ev.plan.edited[1].t, /^1일차 묵을 곳이 빠져 사이트가 가까운 .+ 넣었어요$/u);
});

test("다른 곳으로: a different place of the same kind in the same slot, nearby — and never one the slot was swapped away from", async () => {
  const { c, plan } = await shown();
  const one = await act(c, plan, { op: "swap", day: 0, page: P("근대역사박물관") });
  const out = one.ev.plan;
  assert.equal(out.status, "ready");
  const to = one.ev.act.to;
  assert.ok(to && to !== P("근대역사박물관"));
  const s = out.days[0].stops[0];
  assert.equal(s.path, to);
  assert.deepEqual([s.start, s.end, s.role], ["10:00", "11:30", "visit"]);
  assert.equal(FX.docs[to].f.ty, FX.docs[P("근대역사박물관")].f.ty);   // 박물관·전시 for 박물관·전시
  assert.equal(s.swapped, "other");
  assert.ok(!pages(out).includes(P("근대역사박물관")));
  assert.match(out.edited[0].t, new RegExp(`^근대역사박물관을 가까운 ${FX.docs[to].t}\\(직선 \\d+m, 같은 유형 '박물관·전시'\\)(?:으로|로) 바꿨어요$`, "u"));
  // the other stops as they were
  assert.deepEqual(out.days[0].stops.slice(1).map((x) => [x.path, x.start, x.end]), plan.days[0].stops.slice(1).map((x) => [x.path, x.start, x.end]));
  // again on the slot: neither the place swapped in nor the one before it
  const two = await act(c, out, { op: "swap", day: 0, page: to, tried: [P("근대역사박물관")] });
  assert.ok(two.ev.act.to && ![to, P("근대역사박물관")].includes(two.ev.act.to), JSON.stringify(two.ev.act));
  assert.equal(FX.docs[two.ev.act.to].f.ty, "박물관·전시");
  // a meal becomes a meal (a restaurant that serves one)
  const meal = await act(c, plan, { op: "swap", day: 0, page: P("쌍용반점") });
  const m = meal.ev.plan.days[0].stops.find((x) => x.path === meal.ev.act.to);
  assert.equal(m.role, "meal");
  assert.equal(FX.docs[m.path].f.kd, "food");
});

test("다른 곳으로 with nothing that fits: the plan stays as it was, one line says so", async () => {
  // the islands without a car: one other restaurant near 선유도 at lunch, and once it is tried, none
  const raw = { ...RAW, prefs: ["islands"] };
  const day = [S("선유대교", "10:00", "11:30"), S("남도밥상", "12:00", "13:00", "meal"), S("선유도해수욕장", "13:10", "14:40")];
  const { c, plan } = await shown({ raw, day, title: "선유도 하루", summary: "" });
  const first = await act(c, plan, { op: "swap", day: 0, page: P("남도밥상") });
  const to = first.ev.act.to;
  assert.ok(to, JSON.stringify(first.ev));
  const { ev } = await act(c, first.ev.plan, { op: "swap", day: 0, page: to, tried: [P("남도밥상")] });
  assert.equal(ev.type, "plan");
  assert.equal(ev.act.to, null);
  assert.deepEqual(ev.plan.days[0].stops.map((s) => [s.path, s.start, s.end]), first.ev.plan.days[0].stops.map((s) => [s.path, s.start, s.end]));
  assert.deepEqual(ev.plan.edited, [{ k: "act", t: `${FX.docs[to].t}: 같은 시간에 맞는 비슷한 곳이 가까이에 없어요` }]);
});

test("고정: a pinned stop the model leaves out of a typed edit is put back where it was, said so; the model is told it is pinned", async () => {
  const { c, plan, page } = await shown();
  const pins = [{ day: 0, page: P("초원사진관") }];
  const back = [{ date: c.date, stops: page.days[0].stops.filter((s) => s.page !== P("초원사진관")) }];
  const { ev, calls } = await edit(c, plan, "초원사진관은 빼 주세요", back, pins);
  assert.equal(ev.type, "plan", JSON.stringify(ev));
  assert.equal(ev.plan.status, "ready");
  assert.deepEqual([at(ev.plan, P("초원사진관")).start, at(ev.plan, P("초원사진관")).end], ["11:50", "12:30"]);
  assert.deepEqual(ev.plan.edited, [{ k: "pin", t: "고정한 초원사진관은 그대로 두었어요" }]);
  const said = calls[0][0].content;
  assert.match(said, /- 11:50–12:30 \/places\/초원사진관\/ \(role visit\) \[고정\] why:/u);
  assert.match(said, /\[고정\] 표시한 곳은 독자가 고정한 곳이다: 바꿔 달라는 것이 무엇이든 그날 일정에 그대로 둔다/u);
  // (a pin on a page not on that day is let go; no pin, no word of it)
  const none = await edit(c, plan, "카페 하나 넣어 주세요", page.days, [{ day: 0, page: "/places/없는-곳/" }]);
  assert.doesNotMatch(none.calls[0][0].content, /고정/u);
});

test("고정: the fee quick edit swaps the paid visits but a pinned one, and says so", async () => {
  const { c, plan, page } = await shown();
  const free = await edit(c, plan, "입장료 없는 곳 위주로 바꿔 주세요", page.days);
  assert.ok(!pages(free.ev.plan).includes(P("근대역사박물관")), "unpinned: swapped for a free place");
  const { ev } = await edit(c, plan, "입장료 없는 곳 위주로 바꿔 주세요", page.days, [{ day: 0, page: P("근대역사박물관") }]);
  assert.ok(pages(ev.plan).includes(P("근대역사박물관")));
  assert.equal(ev.plan.fees.known, plan.fees.known);
  assert.match(ev.plan.edited[0].t, /^입장료 줄이기: 고정한 근대역사박물관은 그대로 두었어요 — 입장료는 [\d,]+원 그대로예요$/u);
});

test("고정 with a stop's own button: the code's changes for 빼기 elsewhere keep the pinned stop", async () => {
  const { c, plan } = await shown();
  // the lunch taken out: the meal put in moves the stops around it, never the pinned museum out
  const { ev } = await act(c, plan, { op: "drop", day: 0, page: P("쌍용반점") }, [{ day: 0, page: P("근대역사박물관") }, { day: 0, page: P("초원사진관") }]);
  assert.equal(ev.plan.status, "ready");
  assert.ok(pages(ev.plan).includes(P("근대역사박물관")) && pages(ev.plan).includes(P("초원사진관")));
  assert.ok(!pages(ev.plan).includes(P("쌍용반점")));
});

test("고정 that cannot stand — the place closed that day: the edit fails and says which and why, the reader's plan stays", async () => {
  // a Monday: 근대역사박물관 closes on Mondays (a plan opened from an old tab, or the data changed since)
  const c = validConditions({ ...RAW, date: "2026-10-26" }, NOW);
  const page = { days: [{ date: c.date, stops: [{ page: P("근대역사박물관"), start: "10:00", end: "11:30", role: "visit", why: "" },
    { page: P("초원사진관"), start: "11:50", end: "12:30", role: "visit", why: "" }, { page: P("쌍용반점"), start: "12:40", end: "13:40", role: "meal", why: "" },
    { page: P("동국사"), start: "14:00", end: "15:00", role: "visit", why: "" }, { page: P("경암동 철길마을"), start: "15:30", end: "17:00", role: "visit", why: "" }] }] };
  const e = validEdit(page, "카페 하나 넣어 주세요", c, { pins: [{ day: 0, page: P("근대역사박물관") }] });
  editPlaces(e, KB);
  const sent = [];
  await makePlan({ client: client({ title: "원도심 월요일", summary: "", notes: [], days: page.days }), kb: KB, conditions: c, edit: e, send: (x) => sent.push(x), now: NOW });
  const ev = sent.at(-1);
  assert.equal(ev.type, "error");
  assert.equal(ev.code, "edit_failed");
  assert.equal(ev.message, "고정한 근대역사박물관은 10월 26일(월)은 쉬는 날이라 그날 일정에 둘 수 없어 보던 일정을 그대로 두었습니다. 고정을 풀고 다시 시도해 주세요.");
  // unpinned, the same edit swaps it for a place open that Monday
  const free = validEdit(page, "카페 하나 넣어 주세요", c);
  editPlaces(free, KB);
  const ok = [];
  await makePlan({ client: client({ title: "원도심 월요일", summary: "", notes: [], days: page.days }), kb: KB, conditions: c, edit: free, send: (x) => ok.push(x), now: NOW });
  assert.equal(ok.at(-1).type, "plan");
  assert.ok(!pages(ok.at(-1).plan).includes(P("근대역사박물관")));
});

test("validEdit: an act on a page not on that day, a day left without a stop, a swap of a stay or of a pinned stop, an act with a request — refused", () => {
  const c = validConditions({ ...RAW, days: 2, date: "2026-10-24" }, NOW);
  const page = { days: [{ date: "2026-10-24", stops: [{ page: P("근대역사박물관"), start: "10:00", end: "11:30", role: "visit" },
    { page: P("쌍용반점"), start: "12:00", end: "13:00", role: "meal" }, { page: "/places/베스트웨스턴-군산호텔/", start: "20:00", end: "21:00", role: "stay" }] },
  { date: "2026-10-25", stops: [{ page: P("동국사"), start: "10:00", end: "11:00", role: "visit" }] }] };
  const no = (extra, request) => assert.throws(() => validEdit(page, request, c, extra), (e) => e.status === 400 && e.code === "bad_request", JSON.stringify(extra));
  no({ act: { op: "drop", day: 0, page: P("동국사") } });            // on the other day
  no({ act: { op: "drop", day: 0, page: "/places/없는-곳/" } });
  no({ act: { op: "drop", day: 1, page: P("동국사") } });            // the day's only stop
  no({ act: { op: "swap", day: 0, page: "/places/베스트웨스턴-군산호텔/" } });   // a stay
  no({ act: { op: "swap", day: 0, page: P("근대역사박물관") }, pins: [{ day: 0, page: P("근대역사박물관") }] });
  no({ act: { op: "move", day: 0, page: P("근대역사박물관") } });
  no({ act: { op: "drop", day: 2, page: P("동국사") } });
  no({ act: { op: "swap", day: 0, page: P("근대역사박물관"), tried: "x" } });
  no({ act: { op: "swap", day: 0, page: P("근대역사박물관"), tried: Array.from({ length: 21 }, (_, i) => `/places/p${i}/`) } });
  no({ act: { op: "drop", day: 0, page: P("근대역사박물관") } }, "그리고 카페도");
  no({ pins: [{ day: 0, page: "/places/a/\n" }] }, "카페 하나");
  no({ pins: "x" }, "카페 하나");
  // what passes: the act, its tried list, the pins of the plan's own pages (one not on its day let go)
  const ok = validEdit(page, undefined, c, { act: { op: "swap", day: 0, page: P("쌍용반점"), tried: [P("아리랑"), P("아리랑")] },
    pins: [{ day: 0, page: P("근대역사박물관") }, { day: 1, page: P("근대역사박물관") }] });
  assert.deepEqual(ok.act, { op: "swap", day: 0, page: P("쌍용반점"), tried: [P("아리랑")] });
  assert.equal(ok.request, "");
  assert.deepEqual(ok.pins, [[P("근대역사박물관")], []]);
  // a drop of a stay is no day left empty
  assert.equal(validEdit(page, undefined, c, { act: { op: "drop", day: 0, page: "/places/베스트웨스턴-군산호텔/" } }).act.op, "drop");
});

// ------------------------------------------------------------------ the review of the buttons (2026-10-23)
test("빼기 of a lunch the day needs: another restaurant in its slot, the stops after it where they were", async () => {
  const { c, plan } = await shown();
  const { ev } = await act(c, plan, { op: "drop", day: 0, page: P("쌍용반점") });
  assert.equal(ev.plan.status, "ready");
  const now = ev.plan.days[0].stops;
  const lunch = now.find((s) => s.role === "meal");
  assert.ok(lunch && lunch.path !== P("쌍용반점") && lunch.added, JSON.stringify(now));
  assert.deepEqual([lunch.start, lunch.end], ["12:40", "13:40"]);
  // (the gap closed first, the meal put back cut the visit after it short: none of the others moved)
  assert.deepEqual(now.filter((s) => s !== lunch).map((s) => [s.path, s.start, s.end]),
    plan.days[0].stops.filter((s) => s.path !== P("쌍용반점")).map((s) => [s.path, s.start, s.end]));
  assert.equal(ev.plan.edited[0].t, "쌍용반점을 뺐어요");
  assert.equal(ev.plan.edited[1].t.replace(/[을를] /u, " "), `점심 자리가 비어 사이트가 가까운 ${lunch.name} 12:40~13:40에 넣었어요`);
  assert.equal(ev.plan.edited.length, 2);
});

test("고정: a pinned stop the model moves to another day stays on its own day, the copy goes — no place on two days", async () => {
  // (a day till 19:00: the model's 18:00–18:50 on the first day is inside the reader's day — 2026-10-24 I07, the end holds
  // every day — so what sends it back is the pin alone)
  const c = validConditions({ ...RAW, days: 2, end: "19:00" }, NOW);
  const built = codePlan(c, KB, NOW, "일정 전체: x");
  const page = pageOf(built);
  const sent = [];
  await makePlan({ client: client({ title: "원도심 1박 2일", summary: "", notes: [], days: page.days }), kb: KB, conditions: c, send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  const moved = plan.days[1].stops.find((s) => s.role === "visit");
  // the model takes day 2's pinned visit to the end of day 1, before the night's stay
  const back = pageOf(plan).days.map((d) => ({ ...d, stops: [...d.stops] }));
  back[1].stops = back[1].stops.filter((s) => s.page !== moved.path);
  back[0].stops.splice(back[0].stops.findIndex((s) => s.role === "stay"), 0, { page: moved.path, start: "18:00", end: "18:50", role: "visit", why: "" });
  const { ev } = await edit(c, plan, "둘째 날 첫 곳을 첫날 저녁으로 옮겨 주세요", back, [{ day: 1, page: moved.path }]);
  assert.equal(ev.type, "plan", JSON.stringify(ev));
  assert.equal(ev.plan.status, "ready");
  const on = ev.plan.days.map((d) => d.stops.some((s) => s.path === moved.path));
  assert.deepEqual(on, [false, true], ev.plan.days.map((d) => d.stops.map((s) => s.name).join(",")).join(" | "));
  assert.deepEqual(ev.plan.edited.map((x) => [x.k, x.t.replace(/[은는] 그대로/u, " 그대로")]), [["pin", `고정한 ${moved.name} 그대로 두었어요`]]);
});

test("a course the site built itself: after a button its title and summary are the code's for the plan as it now is", async () => {
  const c = validConditions({ ...RAW, days: 2 }, NOW);
  const built = codePlan(c, KB, NOW, "일정 전체: x");
  const meal = built.days[0].stops.find((s) => s.role === "meal");
  assert.ok(built.summary.includes(meal.name));
  const e = validEdit(pageOf(built), undefined, c, { act: { op: "drop", day: 0, page: meal.path } });
  editPlaces(e, KB);
  e.words = { t: built.title, s: built.summary, n: [], code: true };
  const sent = [];
  await makePlan({ client: NONE, kb: KB, conditions: c, edit: e, send: (x) => sent.push(x), now: NOW });
  const out = sent.at(-1).plan;
  assert.equal(out.status, "ready");
  assert.deepEqual(out.fixed, ["일정 전체: 사이트 자료로 일정을 짰습니다"]);
  assert.ok(!out.summary.includes(meal.name));
  // both days said (align had cut the summary to day 2's sentence)
  assert.match(out.summary, /^1일차는 .+ 2일차는 /u);
  assert.equal(out.summary, codeText({ days: out.days.map((d) => ({ stops: d.stops.map((s) => ({ ...s, page: s.path })) })) }, c, KB).summary);
});

// ------------------------------------------------------------------ through the handler
async function events(res) {
  return (await res.text()).split("\n\n").filter(Boolean).map((b) => JSON.parse(b.slice(6)));
}
const post = (body) => new Request(`${SITE}/api/plan/`, { method: "POST",
  headers: { "content-type": "application/json", origin: SITE, "x-real-ip": "203.0.113.9" }, body: JSON.stringify(body) });
function handler(model, logs = []) {
  return createPlanHandler({ client: model, knowledge: async () => KB, log: (r) => logs.push(r), now: () => NOW,
    // the plan's own quota: one a minute — an act is not in it
    limiter: createLimiter(1), refusals: createLimiter(100), views: createLimiter(100), env: { PLAN_SHARE_SECRET: SECRET } });
}
// what the page sends with an act: the plan on screen, its words' signature (base), the act and the pins
const actBody = (plan, sig, a, extra = {}) => {
  const cp = compactOf(plan);
  return { conditions: plan.conditions, plan: pageOf(plan), base: { k: cp.k, e: cp.e, t: cp.t, s: cp.s, n: cp.n, sig }, act: a, ...extra };
};

test("handler: an act is answered by the code from the signed plan on screen — no model call, not the plan's quota, signed again, the act said", async () => {
  const logs = [];
  const model = client({ title: "원도심 근대 골목 하루", summary: "근대역사박물관에서 시작해 원도심 골목을 걷습니다.", notes: [],
    days: [{ date: "2026-10-24", stops: DAY }] });
  const handle = handler(model, logs);
  const made = (await events(await handle(post({ conditions: RAW })))).at(-1);
  assert.equal(made.type, "plan");
  assert.ok(made.sig);
  assert.equal(model.calls.length, 1);
  const res = await handle(post(actBody(made.plan, made.sig, { op: "drop", day: 0, page: P("초원사진관") }, { pins: [{ day: 0, page: P("동국사") }] })));
  assert.equal(res.status, 200);
  const ev = (await events(res)).at(-1);
  assert.equal(ev.type, "plan", JSON.stringify(ev));
  assert.equal(model.calls.length, 1, "no model call");
  assert.ok(ev.sig && ev.sig !== made.sig);
  assert.deepEqual(ev.act, { op: "drop", day: 0, from: P("초원사진관"), to: null });
  assert.equal(ev.plan.title, made.plan.title);   // the words the signature proved
  assert.equal(ev.plan.edited[0].t, "초원사진관을 뺐어요 — 뒤 장소 4곳을 1시간 당겼어요");
  const log = logs.at(-1);
  assert.equal(log.status, "ok");
  assert.equal(log.act, "drop");
  assert.equal(log.pins, 1);
  assert.equal(log.rounds, 0);
  // the plan's quota (one a minute) is spent: a new plan is refused, an act is not
  assert.equal((await handle(post({ conditions: RAW }))).status, 429);
  const again = await handle(post(actBody(ev.plan, ev.sig, { op: "swap", day: 0, page: P("근대역사박물관") })));
  assert.equal((await events(again)).at(-1).type, "plan");
});

test("handler: an act on a page not in the plan, on a forged base, or with no base when the server signs — 400 bad_request", async () => {
  const model = client({ title: "원도심 근대 골목 하루", summary: "근대역사박물관에서 시작해 원도심 골목을 걷습니다.", notes: [],
    days: [{ date: "2026-10-24", stops: DAY }] });
  const handle = handler(model);
  const made = (await events(await handle(post({ conditions: RAW })))).at(-1);
  const bad = async (body, why) => {
    const res = await handle(post(body));
    assert.equal(res.status, 400, why);
    assert.equal((await res.json()).code, "bad_request", why);
  };
  await bad(actBody(made.plan, made.sig, { op: "drop", day: 0, page: P("테디베어박물관") }), "a page not in the plan");
  const forged = actBody(made.plan, made.sig, { op: "drop", day: 0, page: P("초원사진관") });
  forged.base.t = "무료 장소 위주 하루";
  await bad(forged, "the words changed under the signature");
  const moved = actBody(made.plan, made.sig, { op: "drop", day: 0, page: P("초원사진관") });
  moved.plan.days[0].stops[0].start = "09:00";
  await bad(moved, "the stops changed under the signature");
  const none = actBody(made.plan, made.sig, { op: "drop", day: 0, page: P("초원사진관") });
  delete none.base;
  await bad(none, "no base");
  await bad(actBody(made.plan, "A".repeat(43), { op: "swap", day: 0, page: P("근대역사박물관") }), "a signature that is not the plan's");
  assert.equal(model.calls.length, 1);
});

test("the plan an act sends holds what every plan holds: verify finds nothing on it", async () => {
  const { c, plan } = await shown();
  for (const a of [{ op: "drop", day: 0, page: P("근대역사박물관") }, { op: "drop", day: 0, page: P("동국사") }, { op: "swap", day: 0, page: P("동국사") },
    { op: "swap", day: 0, page: P("군산신흥동일본식가옥(히로쓰가옥)") }, { op: "drop", day: 0, page: P("쌍용반점") }]) {
    const { ev } = await act(c, plan, a);
    assert.equal(ev.type, "plan", JSON.stringify(a));
    const back = { title: ev.plan.title, summary: ev.plan.summary, notes: ev.plan.notes,
      days: ev.plan.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, name: s.name, start: s.start, end: s.end, role: s.role, why: s.why })) })) };
    assert.deepEqual(verify(back, c, KB).flags, [], JSON.stringify(a));
  }
});
