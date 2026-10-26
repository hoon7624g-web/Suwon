// The quick edit '입장료 줄이기' (outside test 2026-10-23): '입장료 없는 곳 위주로 바꿔 주세요' came back with the same
// stops, the same times and the same known total (24,000원) under the title '무료 장소 위주', its changes '장소와 시각은
// 그대로예요' — the request only reached the model and nothing checked that the edit did what it asked. Now the code
// makes it true where the site's data allows (planner fewerFees: each paid visit, the dearest first, swapped for a free or
// cheaper place that fits its day and slot), says how much the fees went down — or why they did not — in the plan's
// 'edited' lines, and a title or sentence that calls a plan with paid visits free goes (freeClaim). The places are the
// site's own (tests/fixtures/plan_places.json: every place of public/chat, cut to the planner's fields); the model is a
// fake that hands the same submit_plan over on every call.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge } from "./first_city.js";
import { tokens } from "../../chatbot/knowledge.js";
import { asksFewerFees, editPlaces, makePlan, textIssues, validConditions, validEdit, verify } from "../../chatbot/planner.js";

const NOW = new Date("2026-10-23T01:00:00Z");   // 2026-10-23 (Fri) 10:00 KST
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
  return { messages: { stream(params) {
    calls.push(structuredClone(params.messages));
    const message = { role: "assistant", content: [{ type: "tool_use", id: `toolu_${calls.length}`, name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
const S = (name, start, end, role = "visit") => ({ page: P(name), start, end, role, why: "" });
// Saturday, two adults by bus — the tester's party
const RAW = { date: "2026-10-24", days: 1, start: "10:00", end: "18:00", move: "transit", with: "couple", adults: 2, seniors: 0, kids: [],
  from: "", to: "", prefs: ["history"], needs: [], budget: null, note: "" };
// the course on the reader's page: three paid museums (근대역사박물관 2,000원, 구 일본 제18은행 군산지점 500원,
// 테디베어박물관 12,000원 a person), a lunch and a free stop — 29,000원 for two
const PAID_DAY = [S("근대역사박물관", "10:30", "12:00"), S("구 일본 제18은행 군산지점", "12:15", "12:45"), S("한일옥", "13:00", "14:00", "meal"),
  S("테디베어박물관", "14:20", "15:50"), S("초원사진관", "16:05", "16:45")];
const PAID = ["근대역사박물관", "구 일본 제18은행 군산지점", "테디베어박물관"];
const QUICK = "입장료 없는 곳 위주로 바꿔 주세요";   // pipeline/present.py PLAN_QUICK_EDITS

/** The course the reader sees (makePlan with the model's day), then the edit `request` with a model that hands back the
 *  same stops and times under `title` and `summary` — the tester's run. */
async function editRun({ raw = RAW, day = PAID_DAY, request = QUICK, title = "원도심 무료 장소 위주 하루",
  summary = "입장료 부담 없이 무료 장소 위주로 원도심을 걷습니다.", back = null } = {}) {
  const c = validConditions(raw, NOW);
  const sent0 = [];
  await makePlan({ client: client({ title: "근대 원도심 박물관 하루", summary: "", notes: [], days: [{ date: c.date, stops: day }] }), kb: KB,
    conditions: c, send: (e) => sent0.push(e), now: NOW });
  const before = sent0.at(-1).plan;
  assert.ok(before, JSON.stringify(sent0.at(-1)));
  const page = { days: before.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, start: s.start, end: s.end, role: s.role, why: s.why })) })) };
  const edit = validEdit(page, request, c);
  editPlaces(edit, KB);
  const calls = [];
  const sent = [];
  await makePlan({ client: client({ title, summary, notes: [], days: back ? back(page.days) : page.days }, calls), kb: KB, conditions: c, edit,
    send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.ok(plan, JSON.stringify(sent.at(-1)));
  return { before, plan, calls, c };
}
const names = (plan) => plan.days.flatMap((d) => d.stops.map((s) => s.name));

test("the request: the quick edit's words and the reader's plain forms of it — not a free car park, not other edits", () => {
  for (const t of [QUICK, "입장료 줄여 주세요", "입장료를 줄이고 싶어요", "무료인 곳으로 바꿔 주세요", "입장료 없는 곳으로", "무료 장소 위주로 다시 짜 주세요",
    "입장료가 싼 곳으로 바꿔 주세요", "입장료 안 드는 곳으로", "공짜로 바꿔 줘", "돈 아끼게 입장료 덜 내는 곳으로", "무료 입장 가능한 곳으로 바꿔 주세요",
    "무료로 볼 수 있는 곳 위주로", "입장료 없는 곳 아니면 싼 곳으로 바꿔 주세요", "테디베어박물관 대신 입장료 없는 곳으로 바꿔 주세요"]) {
    assert.equal(asksFewerFees(t), true, t);
  }
  // (and the words turned down — review: '무료인 곳 말고 박물관 위주로' swapped the paid museums away)
  for (const t of ["카페나 빵집을 한 곳 넣어 주세요", "비가 오면 실내 위주로 바꿔 주세요", "무료 주차 되는 곳으로 바꿔 주세요", "입장료는 상관없어요",
    "점심 맛집을 다른 곳으로 바꿔 주세요", "걷는 거리를 줄여 주세요", "", "무료인 곳 말고 박물관 위주로 바꿔 주세요", "입장료 없는 곳 말고 원래대로 돌려 주세요",
    "입장료 줄이지 않아도 돼요", "입장료는 줄이지 마세요", "무료인 곳이 아니어도 괜찮아요", "입장료 없는 곳은 싫어요", "무료 장소 대신 박물관으로 바꿔 주세요"]) {
    assert.equal(asksFewerFees(t), false, t);
  }
});

test("the tester's case: the model hands back the same paid plan under a '무료' title — the code swaps every paid visit, the total drops, and the change says how much", async () => {
  const { before, plan, calls } = await editRun();
  assert.equal(before.fees.total, 29000);
  assert.deepEqual(PAID.filter((n) => names(before).includes(n)), PAID);
  assert.equal(plan.status, "ready");
  assert.deepEqual(plan.flags, []);
  // every paid visit swapped for a free place of the site that fits its slot; the lunch and the free stop as they were
  assert.deepEqual(PAID.filter((n) => names(plan).includes(n)), []);
  assert.equal(plan.fees.state, "free");
  assert.equal(plan.fees.known, 0);
  const stops = plan.days[0].stops;
  assert.equal(stops.length, 5);
  assert.deepEqual(stops.filter((s) => s.swapped).map((s) => s.swapped), ["other", "other", "other"]);
  assert.ok(stops.filter((s) => s.swapped).every((s) => FX.docs[s.path].f.fee && FX.docs[s.path].f.fee.free), JSON.stringify(stops));
  assert.deepEqual(stops.filter((s) => !s.swapped).map((s) => [s.name, s.start, s.end]), [["한일옥", "13:00", "14:00"], ["초원사진관", "16:05", "16:45"]]);
  // what the site did, one line a swap, the dearest first
  const swaps = plan.fixed.filter((t) => t.includes("입장료를 줄여 달라는 요청대로 가까운"));
  assert.equal(swaps.length, 3, plan.fixed.join("\n"));
  assert.match(swaps[0], /^테디베어박물관: /u);
  // the page's '바꾼 뒤 달라진 것': the fees before and after, from the site's own numbers
  assert.deepEqual(plan.edited, [{ k: "fee", t: "입장료 줄이기: 입장료 29,000원 → 0원(29,000원 줄었어요)" }]);
  // the model was told in its one fix round that a '무료' title over paid visits does not hold
  assert.equal(calls.length, 2);
  const fix = JSON.stringify(calls[1].at(-1));
  assert.match(fix, /title: 입장료를 내는 곳\(근대역사박물관·구 일본 제18은행 군산지점·테디베어박물관\)이 일정에 있는데 무료라고 쓴다\('무료 장소 위주'\)/u);
  // the title now holds: every visit of the plan is free by the site's fee values
  assert.equal(plan.title, "원도심 무료 장소 위주 하루");
});

test("a stop the request keeps stays — and with a paid visit left, the title and the summary do not call the plan free", async () => {
  const { plan } = await editRun({ request: "테디베어박물관은 그대로 두고 입장료 없는 곳 위주로 바꿔 주세요" });
  assert.ok(names(plan).includes("테디베어박물관"));
  assert.ok(!names(plan).includes("근대역사박물관") && !names(plan).includes("구 일본 제18은행 군산지점"), names(plan).join(","));
  assert.equal(plan.fees.total, 24000);
  assert.deepEqual(plan.edited, [{ k: "fee", t: "입장료 줄이기: 입장료 29,000원 → 24,000원(5,000원 줄었어요) — 테디베어박물관은 요청대로 그대로 두었어요" }]);
  // the model's '무료' title is the code's plain one, its claiming summary gone
  assert.equal(plan.title, "10월 24일(토) 군산 하루 코스");
  assert.doesNotMatch(`${plan.title} ${plan.summary} ${plan.notes.join(" ")}`, /무료|입장료 부담/u);
  // 'all but …' keeps it too; a stop named to be changed is no stop to keep ('테디베어박물관 대신')
  const allBut = await editRun({ request: "테디베어박물관만 빼고 나머지는 무료인 곳으로 바꿔 주세요" });
  assert.ok(names(allBut.plan).includes("테디베어박물관"));
  assert.equal(allBut.plan.fees.total, 24000);
  const swapped = await editRun({ request: "테디베어박물관 대신 무료인 곳으로 바꿔 주세요" });
  assert.ok(!names(swapped.plan).includes("테디베어박물관"));
  assert.equal(swapped.plan.fees.state, "free");
});

test("a stop named with the words of changing it is swapped, wherever those words are in its sentence; one named to stay stays", async () => {
  // (review: a window of 12 characters after the name read the first two as keeping it — the line said '요청대로 그대로
  // 두었어요' — and the third as changing it)
  for (const request of ["테디베어박물관은 입장료 없는 곳으로 바꿔 주세요", "근대역사박물관이랑 테디베어박물관은 무료인 곳으로 바꿔 주세요",
    "테디베어박물관, 근대역사박물관은 무료인 곳으로 바꿔 주세요"]) {
    const { plan } = await editRun({ request });
    assert.deepEqual(PAID.filter((n) => names(plan).includes(n)), [], request);
    assert.deepEqual(plan.edited, [{ k: "fee", t: "입장료 줄이기: 입장료 29,000원 → 0원(29,000원 줄었어요)" }], request);
  }
  for (const request of ["테디베어박물관은 두고 무료로 바꿔 주세요", "테디베어박물관은 빼고 나머지는 무료인 곳으로 바꿔 주세요", "테디베어박물관은 빼지 말고 입장료 줄여 주세요"]) {
    const { plan } = await editRun({ request });
    assert.ok(names(plan).includes("테디베어박물관"), request);
    assert.equal(plan.fees.total, 24000, request);
    assert.match(plan.edited[0].t, /테디베어박물관은 요청대로 그대로 두었어요$/u, request);
  }
});

test("a place the edit took out does not come back in a fee swap", async () => {
  // (review: '장미갤러리는 빼고 입장료 줄여 주세요' — the model took 장미갤러리 out, and the swap of 근대역사박물관 put it back)
  const day = [S("근대역사박물관", "10:30", "12:00"), S("장미갤러리", "12:10", "12:50"), S("한일옥", "13:00", "14:00", "meal"),
    S("테디베어박물관", "14:20", "15:50"), S("초원사진관", "16:05", "16:45")];
  const back = (days) => days.map((d) => ({ ...d, stops: d.stops.filter((s) => s.page !== P("장미갤러리")).map((s, j) => (j === 0 ? { ...s, end: "12:40" } : s)) }));
  const { before, plan } = await editRun({ day, request: "장미갤러리는 빼고 입장료 줄여 주세요", title: "원도심 하루", summary: "원도심을 걷습니다.", back });
  assert.ok(names(before).includes("장미갤러리"));
  assert.ok(!names(plan).includes("장미갤러리"), names(plan).join(","));
  assert.deepEqual(PAID.filter((n) => names(plan).includes(n)), []);
  assert.equal(plan.fees.state, "free");
});

test("a combined ticket's places of a day are swapped together — one alone lowers nothing while the ticket opens the others", async () => {
  // (review: 근대역사박물관·구 일본 제18은행 군산지점·군산근대건축관 on 박물관 통합권 with a child of 8 — each one alone
  // added nothing to the total, or left the child unpriced, so none was tried, the line saying no free place was near)
  const raw = { ...RAW, move: "car", with: "kids", kids: [8] };
  const day = [S("근대역사박물관", "10:00", "11:00"), S("구 일본 제18은행 군산지점", "11:10", "11:50"), S("군산근대건축관", "12:00", "12:40"),
    S("한일옥", "12:50", "13:50", "meal"), S("초원사진관", "15:20", "16:30")];
  const { before, plan } = await editRun({ raw, day });
  assert.equal(before.fees.state, "known");
  assert.ok(before.fees.known > 0);
  assert.deepEqual(["근대역사박물관", "구 일본 제18은행 군산지점", "군산근대건축관"].filter((n) => names(plan).includes(n)), []);
  assert.equal(plan.fees.state, "free");
  assert.deepEqual(plan.edited, [{ k: "fee", t: `입장료 줄이기: 입장료 ${before.fees.known.toLocaleString("en-US")}원 → 0원(${before.fees.known.toLocaleString("en-US")}원 줄었어요)` }]);
  // with one of them kept by name the ticket is still bought (the child has no price at 군산근대건축관 alone): the others
  // stay too — no museum given up for nothing — and the line says why, not that no free place was near
  const kept = await editRun({ raw, day, request: "군산근대건축관은 그대로 두고 입장료 없는 곳 위주로 바꿔 주세요" });
  assert.deepEqual(names(kept.plan), names(before));
  assert.equal(kept.plan.fees.known, before.fees.known);
  assert.deepEqual(kept.plan.edited, [{ k: "fee", t: "입장료 줄이기: 입장료가 있는 근대역사박물관·구 일본 제18은행 군산지점은 다른 곳으로 바꿔도 사이트 자료로 셈한 "
    + `입장료가 줄지 않아 그대로 두었어요, 군산근대건축관은 요청대로 그대로 두었어요 — 입장료는 ${before.fees.known.toLocaleString("en-US")}원 그대로예요` }]);
  assert.ok(!kept.plan.fixed.some((t) => t.includes("입장료를 줄여")), kept.plan.fixed.join("\n"));
});

test("no paid visit and one with no price for someone: no word that nothing is paid", async () => {
  // two 65+ visitors: the museums free for them, 테디베어박물관's table names no price for them
  const raw = { ...RAW, with: "parents", adults: 2, seniors: 2 };
  const day = [S("근대역사박물관", "10:30", "12:00"), S("한일옥", "13:00", "14:00", "meal"), S("테디베어박물관", "14:20", "15:50")];
  const { plan } = await editRun({ raw, day, title: "원도심 하루", summary: "원도심을 걷습니다." });
  assert.equal(plan.fees.state, "unknown");
  assert.equal(plan.edited.length, 1);
  assert.match(plan.edited[0].t, /^입장료 줄이기: 일정에 입장료를 낸다고 확인된 곳이 없어요\(입장료는 그대로 확인이 필요해요\) — 요금을 확인하지 못한 테디베어박물관(?:·[^·]+)*[은는] 사이트 자료로는 줄일 수 있는지 알 수 없어요$/u);
});

test("no free or cheaper place fits: the plan stays, the change says so and names the places, the title does not claim 무료", async () => {
  // a rainy Saturday afternoon by bus at 금강: 금강미래체험관 and 채만식 문학관 are the indoor places there; every free one
  // near is outdoor or of no type (never on a rainy day), the next museum is 4 km off
  const raw = { ...RAW, start: "14:00", end: "17:00", needs: ["rain"], prefs: [] };
  const day = [S("금강미래체험관", "14:00", "15:20"), S("채만식 문학관", "15:45", "16:45")];
  const { before, plan } = await editRun({ raw, day, title: "금강 무료 장소 위주 오후", summary: "입장료 없이 금강 쪽을 둘러봅니다." });
  assert.deepEqual(names(plan), names(before));
  assert.deepEqual(plan.days[0].stops.map((s) => [s.start, s.end]), before.days[0].stops.map((s) => [s.start, s.end]));
  assert.equal(plan.fees.known, before.fees.known);
  assert.ok(plan.fees.known > 0);
  const total = `${before.fees.known.toLocaleString("en-US")}원`;
  // (the rain the reader picked holds the place swapped in too: '고른 조건과')
  assert.deepEqual(plan.edited, [{ k: "fee", t: "입장료 줄이기: 입장료가 있는 금강미래체험관·채만식 문학관은 고른 조건과 그 시간에 맞는 무료·더 싼 장소가 그날 동선 "
    + `가까이에 없어 그대로 두었어요 — 입장료는 ${total} 그대로예요` }]);
  assert.ok(!plan.fixed.some((t) => t.includes("입장료를 줄여")), plan.fixed.join("\n"));
  assert.equal(plan.title, "10월 24일(토) 군산 하루 코스");
  assert.doesNotMatch(`${plan.title} ${plan.summary}`, /무료|입장료 없이/u);
});

test("other edits are unaffected: no fee swap, no fee line — the paid visits stay as the model kept them", async () => {
  for (const request of ["카페나 빵집을 한 곳 넣어 주세요", "점심 맛집을 다른 곳으로 바꿔 주세요", "비가 오면 실내 위주로 바꿔 주세요"]) {
    const { before, plan } = await editRun({ request, title: "근대 원도심 박물관 하루", summary: "원도심 박물관을 이어 봅니다." });
    assert.equal(plan.edited, undefined, request);
    assert.deepEqual(PAID.filter((n) => names(plan).includes(n)), PAID, request);
    assert.equal(plan.fees.total, before.fees.total, request);
    assert.ok(!plan.fixed.some((t) => t.includes("입장료를 줄여")), request);
    assert.equal(plan.title, "근대 원도심 박물관 하루", request);
  }
});

test("a plan called free is held to its fees in any plan: the title and a summary sentence over paid visits, not a sentence of free places", () => {
  const c = validConditions(RAW, NOW);
  const plan = { title: "원도심 무료 하루", summary: "모두 무료로 둘러봅니다. 초원사진관은 입장료 없이 들를 수 있어요.", notes: ["무료 주차가 되는 곳도 있어요."],
    days: [{ date: c.date, stops: PAID_DAY.map((s) => ({ ...s, name: FX.docs[s.page].t })) }] };
  const issues = textIssues(plan, c, KB, verify(plan, c, KB).fees).filter((t) => t.includes("무료라고 쓴다"));
  assert.deepEqual(issues.map((t) => t.split(":")[0]), ["title", "summary"]);
  // the plan as a whole called free whatever places the sentence names; parking and who enters free are no word on the
  // plan (review: the site's own '공영주차장은 모두 무료입니다' cost a fix round and went, while '해망굴 등 무료 명소 위주'
  // and '무료로 즐기는 원도심 하루' stood over paid visits)
  const said = (title) => textIssues({ ...plan, title, summary: "", notes: [] }, c, KB, verify(plan, c, KB).fees).some((t) => t.includes("무료라고 쓴다"));
  for (const t of ["해망굴 등 무료 명소 위주 하루", "무료로 즐기는 원도심 하루", "무료입장 명소 위주", "무료 관람 코스"]) assert.equal(said(t), true, t);
  for (const t of ["근대역사박물관 근처 공영주차장은 모두 무료입니다.", "세 곳 모두 무료 주차가 됩니다.", "아이는 모두 무료예요.", "65세 이상은 입장료 없이 들어가요.",
    "무료 투어 프로그램이 있어요.", "해망굴과 초원사진관은 모두 무료예요."]) assert.equal(said(t), false, t);
  // with every visit free, the same words hold
  const free = { ...plan, days: [{ date: c.date, stops: [S("초원사진관", "10:30", "11:30"), S("한일옥", "12:00", "13:00", "meal"), S("해망굴", "13:30", "14:30")]
    .map((s) => ({ ...s, name: FX.docs[s.page].t })) }] };
  assert.deepEqual(textIssues(free, c, KB, verify(free, c, KB).fees).filter((t) => t.includes("무료라고 쓴다")), []);
});
