// Places you can only see from outside (outside tester 2026-10-23): a Monday course had 구 제일사료주식회사 공장 as a
// 30-minute stop whose card said '내부 관람 불가' while the check only said its hours could not be read. The data says
// so (docs.json f.ex — pipeline/chat_index.outside_only, tests/test_chat_index.py on the real export): such a place is an
// outdoor stop for '비 와도 실내 위주' — never indoor, never one a rain repair puts in, never a second outdoor visit a
// day — and the check says what it is ('외관만 볼 수 있는 곳 — 내부 관람 불가(자료 …)') where its hours read as not known.
// The places are the site's own (tests/fixtures/plan_places.json, cut to the planner's fields); the flags are those the
// pipeline writes on the real data, put on the fixture's two places here (and read from the real export with
// CHAT_KB_DIR).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge, loadKnowledge } from "./first_city.js";
import { tokens } from "../../chatbot/knowledge.js";
import { isOutdoor, rainRank } from "../../chatbot/plan_geo.js";
import { checksList, needAt } from "../../chatbot/plan_state.js";
import { codePlan, makePlan, validConditions } from "../../chatbot/planner.js";

const NOW = new Date("2026-10-23T01:00:00Z");   // 2026-10-23 (Fri) 10:00 KST
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_places.json", import.meta.url), "utf8"));
const JEIL = "/places/구-제일사료주식회사-공장/", HIRO = "/places/군산신흥동일본식가옥/";
const PARK = "/places/진포해양공원/", MUSEUM = "/places/근대역사박물관/", PORT = "/places/군산항1981/";
// what pipeline/chat_index.outside_only writes for them from the real data
const EX = {
  [JEIL]: [{ p: "한국관광공사 TourAPI", w: "내부 관람 불가" }],
  [HIRO]: [{ p: "군산시 문화관광", w: "외부,정원만 관람" }, { p: "한국관광공사 TourAPI", w: "실내 개방은 하지 않" }, { p: "군산시 문화관광", w: "실내는 공개하지 않" }],
};
const indexOf = (docs) => ({ v: 1, docs: Object.fromEntries(Object.entries(docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) });
const INDEX = indexOf(FX.docs);
// flag: the export with f.ex (now); false — the export before it. drop: the places left out (a narrower town)
function kbOf(flag = true, drop = null) {
  const docs = structuredClone(FX.docs);
  if (drop) for (const k of Object.keys(docs).filter(drop)) delete docs[k];
  if (flag) for (const [k, ex] of Object.entries(EX)) docs[k].f.ex = ex;
  return new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs, alias: {}, ext: [], tickets: FX.tickets }, index: INDEX });
}
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
function client(input) {
  return { messages: { stream() {
    const message = { role: "assistant", content: [{ type: "tool_use", id: "toolu_1", name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
async function run(kb, input, cond) {
  const c = validConditions(cond, NOW);
  const sent = [];
  await makePlan({ client: client(input), kb, conditions: c, send: (e) => sent.push(e), now: NOW });
  const last = sent.at(-1);
  assert.equal(last.type, "plan", JSON.stringify(last).slice(0, 400));
  assert.equal(last.plan.status, "ready");
  return last.plan;
}
const stop = (page, start, end, role = "visit") => ({ page, name: FX.docs[page].t, start, end, role, why: "" });
const cond = (date, needs = []) => ({ date, days: 1, start: "10:00", end: "17:00", move: "car", with: "couple", adults: 2, seniors: 0,
  kids: [], prefs: ["history"], needs, budget: null, note: "" });

test("the data's flag: an outdoor stop for the rain — never indoor, never ranked for a rain swap-in; a museum stays indoor", () => {
  const kb = kbOf();
  for (const k of [JEIL, HIRO]) {
    const f = kb.docs[k].f;
    assert.equal(isOutdoor(f), true, k);
    assert.equal(needAt("rain", f, "visit").state, "no", k);
    assert.equal(rainRank({ needs: ["rain"] }, f), null, k);
    assert.equal(rainRank({ needs: [] }, f), 0, k);   // nothing changes without the rain
  }
  assert.equal(needAt("rain", kb.docs[JEIL].f, "visit").text, "외관만 볼 수 있는 곳 — 내부 관람 불가(한국관광공사 TourAPI)");
  assert.equal(needAt("rain", kb.docs[HIRO].f, "visit").text, "외관만 볼 수 있는 곳 — 내부 관람 불가(군산시 문화관광 · 한국관광공사 TourAPI)");
  assert.deepEqual(needAt("rain", kb.docs[MUSEUM].f, "visit"), { state: "ok", text: "실내(박물관·전시)" });
  assert.equal(isOutdoor(kb.docs[MUSEUM].f), false);
  // before: the factory, typed 문화유산, was a place the rain could take (rank 1) and its row '?'
  const old = kbOf(false);
  assert.equal(needAt("rain", old.docs[JEIL].f, "visit").state, "unknown");
  assert.equal(rainRank({ needs: ["rain"] }, old.docs[JEIL].f), 1);
});

test("the check line: the factory's hours value is what it is — seen from outside — never hours left unread to check", () => {
  const r = kbOf().checkPlan({ date: "2026-10-26", stops: [{ page: JEIL, start: "10:00", end: "10:30" }] });
  const s = r.stops[0];
  assert.deepEqual(r.flags, []);
  assert.equal(s.day, "open");   // 연중무휴
  assert.deepEqual(s.checks, []);
  assert.ok(s.notes.includes("이용시간 — 한국관광공사 TourAPI: 외관만 볼 수 있는 곳 — 내부 관람 불가(자료: '내부 관람 불가 ※ 자세한 사항은 전화 문의 요망')"), s.notes.join("\n"));
  assert.ok(s.notes.includes("관람: 외관만 볼 수 있는 곳 — 내부 관람 불가(자료: 한국관광공사 TourAPI)"), s.notes.join("\n"));
  assert.deepEqual(s.outside, { p: "한국관광공사 TourAPI", only: 1 });
  assert.doesNotMatch(r.text, /읽지 (?:못|않)/u);
  // before: '그날 시각을 하나로 읽지 못해 계획한 시각에 여는지 확인 필요'
  const before = kbOf(false).checkPlan({ date: "2026-10-26", stops: [{ page: JEIL, start: "10:00", end: "10:30" }] }).stops[0];
  assert.match(before.checks.join("\n"), /그날 시각을 하나로 읽지 못해/u);
  assert.equal(before.outside, undefined);
  // 히로쓰가옥: its hours are hours (10:00~17:00, read as such) and it is said to be seen from outside
  const h = kbOf().checkPlan({ date: "2026-10-27", stops: [{ page: HIRO, start: "10:00", end: "10:40" }] }).stops[0];
  assert.deepEqual(h.outside, { p: "군산시 문화관광 · 한국관광공사 TourAPI" });
  assert.deepEqual(h.hours, [{ open: 600, close: 1020, last: null }]);
  assert.deepEqual(h.checks, []);
  // on its closed day it is closed as before
  assert.equal(kbOf().checkPlan({ date: "2026-10-26", stops: [{ page: HIRO, start: "10:00", end: "10:40" }] }).stops[0].day, "closed");
});

test("the tester's Monday: the factory's stop says what one can do there, with its source, and keeps its time", async () => {
  // a Monday by car 10:00–17:00: the factory 10:00–10:30, 군산항1981 (closed on Wednesdays), lunch at 홍영장 (no closed day)
  const input = { title: "월요일 원도심", summary: "", notes: [], days: [{ date: "2026-10-26", stops: [
    stop(JEIL, "10:00", "10:30"), stop(PORT, "10:45", "12:00"), stop("/places/홍영장/", "12:15", "13:15", "meal"),
    stop("/places/테디베어박물관/", "13:45", "15:15"), stop("/places/초원사진관/", "15:45", "16:30")] }] };
  const plan = await run(kbOf(), input, cond("2026-10-26"));
  const s = plan.days[0].stops.find((x) => x.path === JEIL);
  assert.ok(s, plan.days[0].stops.map((x) => x.name).join(", "));
  assert.deepEqual(s.outside, { p: "한국관광공사 TourAPI", only: 1 });
  assert.deepEqual(s.checks, []);
  assert.ok(plan.aware.some((x) => x.k === "outside" && x.t === "구 제일사료주식회사 공장: 외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)"),
    JSON.stringify(plan.aware));
  assert.ok(!plan.checks.some((x) => x.t.includes("구 제일사료주식회사 공장")), JSON.stringify(plan.checks));
  // its time is the code's as before: the flag changes no length
  const old = await run(kbOf(false), input, cond("2026-10-26"));
  const was = old.days[0].stops.find((x) => x.path === JEIL);
  assert.deepEqual([s.start, s.end], [was.start, was.end]);
  assert.match(old.checks.map((x) => x.t).join("\n"), /구 제일사료주식회사 공장: 이용시간 — .*읽지 못해/u);
  assert.ok(!old.aware.some((x) => x.k === "outside"));
});

test("rain: a second outdoor visit that day is the factory — it does not stay, and nothing outdoor takes its place", async () => {
  // a Tuesday in the rain: 진포해양공원 (자연·야외) first, the factory next — before, the factory (typed 문화유산) stayed
  const input = { title: "비 오는 화요일", summary: "", notes: [], days: [{ date: "2026-10-27", stops: [
    stop(PARK, "10:00", "10:50"), stop(JEIL, "11:05", "11:35"), stop("/places/빈해원/", "12:00", "13:00", "meal"),
    stop(MUSEUM, "13:30", "15:00"), stop(PORT, "15:20", "16:30")] }] };
  const plan = await run(kbOf(), input, cond("2026-10-27", ["rain"]));
  const kb = kbOf();
  const visits = plan.days[0].stops.filter((x) => x.role === "visit");
  assert.ok(!visits.some((x) => x.path === JEIL), visits.map((x) => x.name).join(", "));
  assert.ok(visits.filter((x) => isOutdoor(kb.docs[x.path].f)).length <= 1, visits.map((x) => x.name).join(", "));
  for (const x of plan.days[0].stops.filter((y) => y.added || y.swapped)) assert.equal(isOutdoor(kb.docs[x.path].f || {}), false, x.name);
  const old = await run(kbOf(false), input, cond("2026-10-27", ["rain"]));
  assert.ok(old.days[0].stops.some((x) => x.path === JEIL), "before: kept as a typed place");
  // the needs table says why at a stop that stays outdoors
  const row = plan.needs.find((n) => n.key === "rain").rows.find((x) => x.name === "진포해양공원");
  assert.equal(row.state, "no");
});

test("rain: a place seen only from outside is never a fill where it is the nearest, and the code's own course counts it outdoor", async () => {
  const at = (plan, pages) => plan.days.flatMap((d) => d.stops).filter((x) => pages.includes(x.path)).map((x) => x.name);
  // the course the site builds itself for a reader who likes 골목 산책 (히로쓰가옥's type) in the rain: before, 히로쓰가옥
  // (typed '골목과 문화', not known to be outdoors) was in it on every one of these dates. (On these fixture places,
  // by transit, it is not now; the builder ranks likings first, so on the real data — by car, two days — it can still
  // be a day's one outdoor visit, as a park is for a reader who likes 자연: the real-knowledge test below)
  for (const date of ["2026-10-24", "2026-10-27"]) {
    const c = validConditions({ ...cond(date, ["rain"]), days: 2, end: "18:00", move: "transit", prefs: ["alleys"] }, NOW);
    const kb = kbOf();
    const plan = codePlan(c, kb, NOW, "일정 전체: 사이트 자료로 짰습니다");
    assert.ok(plan, date);
    assert.deepEqual(at(plan, [JEIL, HIRO]), [], date);
    for (const d of plan.days) assert.ok(d.stops.filter((x) => x.role === "visit" && isOutdoor(kb.docs[x.path].f)).length <= 1, date);
    assert.deepEqual(at(codePlan(c, kbOf(false), NOW, "일정 전체: 사이트 자료로 짰습니다"), [HIRO]), [FX.docs[HIRO].t], `${date} before`);
  }
  // a stretch to fill after lunch at 한일옥 (224 m from 히로쓰가옥), the other places of the neighbourhood left out so
  // that 히로쓰가옥 is the nearest that fits: in the rain the fill takes another place; before, and without the rain, it
  // took 히로쓰가옥
  const near = (k) => { const f = FX.docs[k].f || {}; return f.kd === "attraction" && !!f.g && ![MUSEUM, "/places/말랭이마을/", HIRO, JEIL].includes(k)
    && Math.hypot((f.g[0] - FX.docs[HIRO].f.g[0]) * 111000, (f.g[1] - FX.docs[HIRO].f.g[1]) * 90000) < 2500; };
  const input = { title: "비 오는 화요일", summary: "", notes: [], days: [{ date: "2026-10-27", stops: [
    stop(MUSEUM, "10:00", "11:30"), stop("/places/한일옥/", "12:00", "13:00", "meal"), stop("/places/말랭이마을/", "15:30", "16:30")] }] };
  const rain = { ...cond("2026-10-27", ["rain"]), prefs: ["alleys"] };
  const plan = await run(kbOf(true, near), input, rain);
  assert.ok(plan.days[0].stops.some((x) => x.added), "a stop filled the stretch");
  assert.deepEqual(at(plan, [JEIL, HIRO]), []);
  for (const x of plan.days[0].stops.filter((y) => y.added || y.swapped)) assert.equal(isOutdoor(kbOf().docs[x.path].f || {}), false, x.name);
  assert.deepEqual(at(await run(kbOf(false, near), input, rain), [HIRO]), [FX.docs[HIRO].t], "before");
  assert.deepEqual(at(await run(kbOf(true, near), input, { ...rain, needs: [] }), [HIRO]), [FX.docs[HIRO].t], "without the rain");
});

test("the 'outside' line is said once a place, under what holds for the plan, never as a check", () => {
  const kb = kbOf();
  const plan = { days: [{ date: "2026-10-26", stops: [{ page: JEIL, name: "구 제일사료주식회사 공장", role: "visit", start: "10:00", end: "10:30" }] },
    { date: "2026-10-27", stops: [{ page: JEIL, name: "구 제일사료주식회사 공장", role: "visit", start: "10:00", end: "10:30" },
      { page: HIRO, name: FX.docs[HIRO].t, role: "visit", start: "11:00", end: "11:40" }] }] };
  const check = { days: plan.days.map((d) => kb.checkPlan({ date: d.date, stops: d.stops })) };
  const { aware, checks } = checksList(plan, { needs: [] }, check, [], { open: [] }, [], kb);
  assert.deepEqual(aware.filter((x) => x.k === "outside").map((x) => x.t), [
    "구 제일사료주식회사 공장: 외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)",
    "군산신흥동일본식가옥(히로쓰가옥): 외관 감상 · 내부 관람 불가(자료: 군산시 문화관광 · 한국관광공사 TourAPI)"]);
  assert.ok(!checks.some((x) => /외관|읽지 못해/u.test(x.t)), JSON.stringify(checks));
});

// (the first city's real knowledge, when a directory of it is given: FIRST_CITY_KB_DIR — this city's own is CHAT_KB_DIR)
const REAL = process.env.FIRST_CITY_KB_DIR;
test("real knowledge: the export flags the factory and 히로쓰가옥 from their own data, and no museum", { skip: !REAL && "FIRST_CITY_KB_DIR not set" }, async () => {
  const k = await loadKnowledge(REAL);
  assert.deepEqual(k.docs[JEIL].f.ex, EX[JEIL]);
  assert.deepEqual(k.docs[HIRO].f.ex, EX[HIRO]);
  const flagged = Object.keys(k.docs).filter((x) => ((k.docs[x].f || {}).ex || []).length).sort();
  assert.deepEqual(flagged, [JEIL, HIRO].sort());
  assert.equal(needAt("rain", k.docs[MUSEUM].f, "visit").state, "ok");
  const r = k.checkPlan({ date: "2026-10-26", stops: [{ page: JEIL, start: "10:00", end: "10:30" }] }).stops[0];
  assert.deepEqual(r.checks, []);
  assert.deepEqual(r.outside, { p: "한국관광공사 TourAPI", only: 1 });
  // the code's own rain course (likes 골목 산책, by car, two days): the flagged places are outdoor visits — one a day at
  // most, the stop saying what it is
  for (const date of ["2026-10-24", "2026-10-27"]) {
    const c = validConditions({ ...cond(date, ["rain"]), days: 2, end: "18:00", prefs: ["alleys"] }, NOW);
    const plan = codePlan(c, k, NOW, "일정 전체: 사이트 자료로 짰습니다");
    assert.ok(plan, date);
    for (const d of plan.days) {
      assert.ok(d.stops.filter((x) => x.role === "visit" && isOutdoor(k.docs[x.path].f)).length <= 1, date);
      for (const x of d.stops.filter((y) => [JEIL, HIRO].includes(y.path))) assert.ok(x.outside, `${date} ${x.name}`);
    }
  }
});
