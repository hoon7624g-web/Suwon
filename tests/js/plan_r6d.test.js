// The round-6 final verifier's engine findings (2026-10-19): closed days that name months, a season or the weather; the
// AI's closure sentences; the meals an edit was sent; a full day an edit adds to; a stretch that makes a second lunch;
// the AI's times the code changed; a restaurant given as a café; an edit that changes nothing. Each test fails on
// e50aeeec9 and passes after. The places are the site's own (tests/fixtures/plan_places.json: every place of public/chat, cut to the planner's fields).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge } from "./first_city.js";
import { eul, iga, tokens } from "../../chatbot/knowledge.js";
import { asksMeal, hm, isMeal, mealKind, needAt } from "../../chatbot/plan_state.js";
import { closedHints, codePlan, makePlan, readSubmit, staleWords, validConditions, validEdit } from "../../chatbot/planner.js";
import { buildPlan } from "../../chatbot/plan_build.js";
import { dayInfo, hardState } from "../../chatbot/plan_geo.js";

const NOW = new Date("2026-10-17T01:00:00Z");   // 2026-10-17 (Sat) 10:00 KST
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_places.json", import.meta.url), "utf8"));
const indexOf = (docs) => ({ v: 1, docs: Object.fromEntries(Object.entries(docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) });
const INDEX = indexOf(FX.docs);
const winterKb = () => new Knowledge({ catalog: "# catalog", docs: { v: 1, site: FX.site, docs: FX.docs, alias: {}, ext: [], tickets: FX.tickets }, index: INDEX });
const P = (name) => {
  const k = Object.keys(FX.docs).find((x) => FX.docs[x].t === name);
  if (!k) throw new Error(`no place ${name}`);
  return k;
};
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
// a model that hands the same submit_plan over on every call
function client(input) {
  return { messages: { stream() {
    const message = { role: "assistant", content: [{ type: "tool_use", id: "toolu_1", name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    const events = [{ type: "message_start", message: { usage } }, { type: "content_block_start", index: 0, content_block: { type: "tool_use", id: "toolu_1", name: "submit_plan", input: {} } }];
    return { async *[Symbol.asyncIterator]() { for (const e of events) yield e; }, async finalMessage() { return message; } };
  } } };
}
async function run(kb, input, cond, edit = null) {
  const c = validConditions(cond, NOW);
  const sent = [];
  await makePlan({ client: client(input), kb, conditions: c, edit, send: (e) => sent.push(e), now: NOW });
  const last = sent.at(-1);
  return { plan: last.type === "plan" ? last.plan : null, err: last.type === "error" ? last : null, c };
}
const stop = (name, start, end, role = "visit", why = "") => ({ page: P(name), start, end, role, why });
const pages = (plan) => plan.days.flatMap((d) => d.stops.map((s) => s.path || s.page));

// ------------------------------------------------------------------ 1. closed days that name months or the weather
const WINTER = ["새만금어린이랜드", "선유 스카이썬라인", "군산평화박물관"];

test("closed days with months: the three places the data closes in winter are closed on December–February dates, open or to check outside", () => {
  const kb = winterKb();
  for (const date of ["2026-12-17", "2027-01-21", "2027-02-18", "2026-12-20"]) {
    for (const name of WINTER) assert.equal(dayInfo(kb, date, P(name)).state, "closed", `${name} ${date}`);
  }
  // March and November (Thursdays): 선유 스카이썬라인 and 군산평화박물관 open; 새만금어린이랜드 shuts in the rain — never 'open'
  for (const date of ["2026-11-19", "2027-03-18"]) {
    assert.equal(dayInfo(kb, date, P("선유 스카이썬라인")).state, "open", date);
    assert.equal(dayInfo(kb, date, P("군산평화박물관")).state, "open", date);
    const kids = dayInfo(kb, date, P("새만금어린이랜드"));
    assert.equal(kids.state, "check", date);
    assert.match(kids.checks.join(" "), /날씨에 따라/u);
  }
  // the check says why, with the source's words, and closes the place for the date
  const r = kb.checkPlan({ date: "2027-01-21", stops: [{ page: P("새만금어린이랜드"), start: "13:30", end: "15:30" }] });
  assert.equal(r.stops[0].day, "closed");
  assert.match(r.flags[0], /정기 휴무\(한국관광공사 '매년 12월 ~ 2월, 우천시 휴장'\)/u);
  // the model is told: each winter date lists all three
  const hints = closedHints(validConditions({ date: "2026-12-17", days: 1, start: "10:00", end: "18:00", move: "car", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null }, NOW), kb);
  for (const name of WINTER) assert.ok(hints.includes(P(name)) || hints.includes(name), name);
});

test("closed days: a month range across the year end, within a part; a season with no months and the weather are to check, never 'open'", () => {
  const doc = (c) => ({ t: "곳", k: "place", x: "곳 — 관광지", f: { kd: "attraction", ty: "체험", g: [35.98, 126.71], c: [{ p: "군산시", t: c }], h: [{ p: "군산시", t: "09:00~18:00" }] } });
  const kbOf = (c) => new Knowledge({ catalog: "# c", docs: { v: 1, site: FX.site, docs: { "/places/a/": doc(c) }, alias: {}, ext: [], tickets: [] }, index: indexOf({ "/places/a/": doc(c) }) });
  const at = (c, date) => dayInfo(kbOf(c), date, "/places/a/").state;
  // 11월~3월 wraps the year end; 6~8월 is a summer range
  assert.equal(at("11월~3월", "2027-03-10"), "closed");
  assert.equal(at("11월~3월", "2027-04-10"), "open");
  assert.equal(at("6~8월 휴장", "2027-03-10"), "open");
  // a weekday inside a part with months holds in those months only
  assert.equal(at("12월~2월 매주 화요일", "2026-12-15"), "closed");
  assert.equal(at("12월~2월 매주 화요일", "2026-11-17"), "open");
  // a season the data names without its months: that weekday is to check, other days are not closed by it
  assert.equal(at("동절기(일요일 휴무)", "2026-11-22"), "check");
  assert.equal(at("동절기(일요일 휴무)", "2026-11-23"), "open");
  assert.equal(at("동절기 휴무", "2026-06-10"), "check");
  // the weather: every day is to check, though the rest of the value opens it (the cruise's '연중무휴 (기상상황에 따라…)')
  assert.equal(at("연중무휴 (기상상황에 따라 출항하지 못할 수도 있음)", "2026-11-23"), "check");
  assert.equal(at("우천시 휴장", "2026-11-23"), "check");
  // a date ('12월 31일') is not a month range
  assert.equal(at("12월 31일", "2026-12-30"), "open");
});

test("closed days with months: the code's own plan (the early course) never puts the winter places in on a December–February date", () => {
  const kb = winterKb();
  const seen = [];
  let built = 0;
  for (const date of ["2026-12-17", "2027-01-09", "2027-01-21", "2027-02-18"]) {
    for (const prefs of [["experience"], ["nature"], ["experience", "nature"]]) {
      for (const move of ["car", "transit"]) {
        for (const days of [1, 2]) {
          const c = validConditions({ date, days, start: "10:00", end: "18:00", move, with: "kids", adults: 2, kids: [6], prefs, needs: [], budget: null }, NOW);
          // the early course is codePlan — buildPlan, checked and finished
          const p = codePlan(c, kb, NOW, "일정 전체: AI가 다듬기 전에 사이트 자료로 먼저 일정을 짰습니다");
          if (!p) continue;
          built += 1;
          assert.equal(p.status, "ready");
          for (const d of p.days) for (const s of d.stops) if (WINTER.includes(s.name)) seen.push(`${date} ${move} ${days} ${prefs} ${s.name}`);
        }
      }
    }
  }
  assert.ok(built >= 40, `built ${built}`);
  assert.deepEqual(seen, []);
});

test("closed days with months: a model's stop at 새만금어린이랜드 in January is taken out, and nothing closed is swapped in", async () => {
  const kb = winterKb();
  const cond = { date: "2027-01-09", days: 1, start: "10:00", end: "18:00", move: "car", with: "kids", adults: 2, kids: [3, 7], prefs: ["experience"], needs: [], budget: null };
  const input = { title: "새만금 아이와 하루", summary: "아이와 새만금 쪽을 돕니다.", notes: [], days: [{ date: "2027-01-09", stops: [
    stop("군산어린이교통공원", "10:00", "11:30"), stop("오구이", "12:00", "13:00", "meal"), stop("새만금어린이랜드", "13:30", "15:30"), stop("새만금비응공원", "16:00", "17:00")] }] };
  const { plan } = await run(kb, input, cond);
  assert.equal(plan.status, "ready");
  assert.deepEqual(plan.flags, []);
  for (const name of WINTER) assert.ok(!pages(plan).includes(P(name)), name);
  assert.ok(plan.fixed.some((t) => /새만금어린이랜드: 1월 9일\(토\)은 쉬는 날이라/u.test(t)), plan.fixed.join("\n"));
  // every stop is open (or to check) that day by the data
  for (const d of plan.days) for (const s of d.stops) assert.notEqual(dayInfo(kb, d.date, s.path).state, "closed", s.name);
});

test("the rain need: a place whose closed days say it shuts in the rain is 'no' — out of the model's plan, never put in, and the model is told", async () => {
  const kb = winterKb();
  const f = FX.docs[P("새만금어린이랜드")].f;
  assert.equal(needAt("rain", f, "visit").state, "no");
  assert.match(needAt("rain", f, "visit").text, /우천시 휴장/u);
  const rain = validConditions({ date: "2026-11-18", days: 1, start: "10:00", end: "18:00", move: "car", with: "kids", adults: 2, kids: [6], prefs: ["experience"], needs: ["rain"], budget: null }, NOW);
  assert.equal(hardState(rain, f, "visit"), "no");
  assert.equal(hardState({ ...rain, needs: [] }, f, "visit"), "ok");
  assert.match(closedHints(rain, kb), /비 오는 날 쉰다고 자료에 있는 곳 1곳 — '비 와도 실내 위주'라 어느 날에도 넣지 않는다: \/places\/새만금어린이랜드\//u);
  assert.doesNotMatch(closedHints({ ...rain, needs: [] }, kb), /비 오는 날/u);
  const input = { title: "비 오는 날 새만금", summary: "비가 와도 아이와 놉니다.", notes: [], days: [{ date: "2026-11-18", stops: [
    stop("군산어린이교통공원", "10:00", "11:00"), stop("오구이", "12:00", "13:00", "meal"), stop("새만금어린이랜드", "13:30", "15:30")] }] };
  const { plan } = await run(kb, input, { ...rain, kids: [6] });
  assert.equal(plan.status, "ready");
  assert.ok(!pages(plan).includes(P("새만금어린이랜드")));
  assert.ok(plan.fixed.some((t) => /새만금어린이랜드: '비 와도 실내 위주' 조건에 맞지 않는다고 자료에 있어/u.test(t)), plan.fixed.join("\n"));
  // the code's own plans for rain days never put it in
  for (const date of ["2026-11-18", "2026-11-21", "2027-03-20"]) {
    for (const move of ["car", "transit"]) {
      const b = buildPlan(validConditions({ ...rain, date, move }, NOW), kb);
      if (b.plan) assert.ok(!pages(b.plan).includes(P("새만금어린이랜드")), `${date} ${move}`);
    }
  }
});

// ------------------------------------------------------------------ 2. the AI's closure sentences, in any form
// 2026-10-21 is a Wednesday: 근대역사박물관 (closed Mondays), 경암동 철길마을, 초원사진관 and 동국사 are open by the data
const WED = { date: "2026-10-21", days: 1, start: "10:00", end: "18:00", move: "transit", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null };
const wedDay = (why = {}) => [stop("근대역사박물관", "10:00", "11:30", "visit", why.museum || ""), stop("호남관세박물관", "11:40", "12:20"),
  stop("아리랑", "12:30", "13:30", "meal"), stop("경암동 철길마을", "14:00", "15:00", "visit", why.rail || ""), stop("초원사진관", "15:20", "16:00", "visit", why.photo || ""),
  stop("동국사", "16:20", "17:20")];

test("closure sentences: '쉽니다', '문을 닫습니다', '휴업', '운영하지 않습니다', '휴장', '정기휴일', '열지 않아요' of a place open that day all go", async () => {
  const kb = winterKb();
  const S = ["경암동 철길마을은 수요일에 쉽니다.", "초원사진관은 오늘 문을 닫습니다.", "동국사는 수요일 휴업입니다.", "근대역사박물관은 수요일에 운영하지 않습니다.",
    "경암동 철길마을은 매주 수요일 휴장합니다.", "초원사진관은 수요일이 정기휴일입니다.", "동국사는 오늘 휴관일입니다.", "근대역사박물관은 수요일엔 열지 않아요."];
  const KEEP = ["경암동 철길마을은 쉬어 가기 좋은 골목입니다.", "근대역사박물관은 공휴일에도 문을 엽니다.", "동국사는 휴관일이 없습니다.", "초원사진관은 연중무휴입니다."];
  const { plan } = await run(kb, { title: "수요일 군산", summary: [...S, ...KEEP].join(" "), notes: [], days: [{ date: WED.date, stops: wedDay() }] }, WED);
  for (const s of S) assert.ok(!plan.summary.includes(s), s);
  for (const s of KEEP) assert.ok(plan.summary.includes(s), s);
  assert.ok(plan.fixed.some((t) => /여행 날짜에 쉰다는 자료가 없어 쉰다고 말하는 문장 8개를 뺐습니다/u.test(t)), plan.fixed.join("\n"));
  // a trip of Sunday and Monday: the museum is closed on its Monday by the data — the same words of it stay
  const SUN = { ...WED, date: "2026-10-25", days: 2 };
  const sun = await run(kb, { title: "일요일 군산", summary: "근대역사박물관은 월요일에 쉽니다. 경암동 철길마을은 월요일에 쉽니다.", notes: [], days: [
    { date: "2026-10-25", stops: [stop("근대역사박물관", "10:00", "11:30"), stop("아리랑", "12:00", "13:00", "meal"), stop("경암동 철길마을", "13:30", "14:30")] },
    { date: "2026-10-26", stops: [stop("초원사진관", "10:00", "11:00"), stop("동국사", "11:20", "12:00")] }] }, SUN);
  assert.equal(sun.plan.summary, "근대역사박물관은 월요일에 쉽니다.");
});

test("closure sentences: a stop's own reason that names no place speaks of that stop — held to the data like any other", async () => {
  const kb = winterKb();
  const { plan } = await run(kb, { title: "수요일 군산", summary: "원도심을 걷는 하루입니다.", notes: [], days: [{ date: WED.date, stops: wedDay({
    museum: "매주 수요일 휴관이지만 오늘은 특별 개방합니다.", rail: "매주 수요일에는 쉬는 날이라 짧게 둘러봅니다. 기찻길을 따라 걷습니다.", photo: "수요일 휴무입니다." }) }] }, WED);
  const why = (name) => plan.days[0].stops.find((s) => s.name === name).why;
  assert.equal(why("근대역사박물관"), "");
  assert.equal(why("경암동 철길마을"), "기찻길을 따라 걷습니다.");
  assert.equal(why("초원사진관"), "");
  assert.ok(plan.fixed.some((t) => /근대역사박물관·경암동 철길마을·초원사진관이 여행 날짜에 쉰다는 자료가 없어 쉰다고 말하는 문장 3개를 뺐습니다/u.test(t)), plan.fixed.join("\n"));
  // a reason that rests ('쉬어 가는') is no closed day
  const rest = await run(kb, { title: "수요일 군산", summary: "원도심을 걷는 하루입니다.", notes: [], days: [{ date: WED.date, stops: wedDay({ rail: "걷다가 쉬어 가는 곳입니다." }) }] }, WED);
  assert.equal(rest.plan.days[0].stops.find((s) => s.name === "경암동 철길마을").why, "걷다가 쉬어 가는 곳입니다.");
});

test("closure sentences: a place an edit took out said closed ('오늘 휴장이라 제외했습니다') is held to the data too", async () => {
  const kb = winterKb();
  const first = await run(kb, { title: "수요일 군산", summary: "원도심을 걷습니다.", notes: [], days: [{ date: WED.date, stops: wedDay() }] }, WED);
  const body = { days: first.plan.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, start: s.start, end: s.end, role: s.role, why: s.why })) })) };
  const e = validEdit(body, "경암동 철길마을은 빼 주세요", first.c);
  const days = body.days.map((d) => ({ ...d, stops: d.stops.filter((x) => x.page !== P("경암동 철길마을")) }));
  for (const s of ["경암동 철길마을은 오늘 휴장이라 제외했습니다.", "경암동 철길마을은 수요일에 쉬어서 뺐습니다.", "경암동 철길마을은 매주 수요일 정기휴일이라 다음에 가세요."]) {
    const sent = [];
    await makePlan({ client: client({ title: "수요일 군산", summary: s, notes: [], days }), kb, conditions: first.c, edit: e, send: (x) => sent.push(x), now: NOW });
    const p = sent.at(-1).plan;
    assert.ok(!p.summary.includes(s), s);
    assert.ok(p.fixed.some((t) => /경암동 철길마을이 여행 날짜에 쉰다는 자료가 없어/u.test(t)), p.fixed.join("\n"));
  }
});

// ------------------------------------------------------------------ 3–4. edits: the meals sent, a full day
// The verifier's edit fuzz cases (tests/fixtures/plan_r6d_edits.json: the plan the page sends back — made by e50aeeec9 —,
// the request and the scripted model's plan for it): a café put in an afternoon, a visit dropped, a café on a full day.
const EDITS = JSON.parse(readFileSync(new URL("../fixtures/plan_r6d_edits.json", import.meta.url), "utf8"));
async function editRun(name, input = null) {
  const x = EDITS.find((y) => y.name === name);
  const now = new Date(x.now);
  const c = validConditions(x.conditions, now);
  const edit = validEdit(x.body, x.request, c);
  const sent = [];
  await makePlan({ client: client(input || x.input), kb: winterKb(), conditions: c, edit, send: (e) => sent.push(e), now });
  return { x, last: sent.at(-1), c };
}
const newCafe = (x) => x.input.days[0].stops.find((s) => s.role === "cafe" && !x.body.days[0].stops.some((y) => y.page === s.page));
// the meals of the page's plan the request is not about: the same place, start and end after the edit
async function mealsKept(name) {
  const { x, last } = await editRun(name);
  assert.equal(last.type, "plan", JSON.stringify(last));
  assert.equal(last.plan.status, "ready");
  assert.deepEqual(last.plan.flags, []);
  x.input.days.forEach((d, i) => {
    for (const s of d.stops.filter((y) => y.role === "meal")) {
      if (asksMeal(mealKind(hm(s.start), hm(s.end)) || "lunch", x.request)) continue;
      // (a meal past the reader's 하루 끝 is the check's to take out: the end holds every day — 2026-10-24 I07)
      if (hm(s.end) > hm(x.conditions.end) || hm(s.start) < hm(x.conditions.start)) continue;
      const now = last.plan.days[i].stops.find((y) => y.path === s.page && y.role === "meal");
      assert.ok(now, `${name} day ${i + 1} ${s.page} gone`);
      assert.deepEqual([now.start, now.end], [s.start, s.end], `${name} day ${i + 1} ${now.name}`);
    }
  });
  return { x, plan: last.plan };
}

test("edits: a café asked for never moves the lunch or dinner the page has — no whole move crosses it (the verifier's three cases)", async () => {
  for (const name of ["cafe_1111_105", "cafe_5150_29", "cafe_1111_91"]) {
    const { x, plan } = await mealsKept(name);
    assert.ok(plan.days[0].stops.some((s) => s.path === newCafe(x).page), `${name}: the café`);
  }
});

test("edits: a visit dropped never stretches or moves the meal next to it", async () => {
  for (const name of ["drop_1111_75", "drop_1111_136"]) {
    const { plan } = await mealsKept(name);
    const meals = plan.days.flatMap((d) => d.stops.filter((s) => s.role === "meal").map((s) => s.name));
    assert.ok(!plan.fixed.some((t) => /빈 시간을 줄이려고/u.test(t) && meals.some((n) => t.includes(`${n}:`))), plan.fixed.join("\n"));
  }
});

test("edits: a café on a day already full keeps the night's stay and the café — another place goes, said so", async () => {
  for (const name of ["full_1111_58", "full_meals707_61"]) {
    const { x, last } = await editRun(name);
    assert.equal(last.type, "plan", `${name}: ${JSON.stringify(last)}`);
    const d = last.plan.days[0];
    assert.ok(d.stops.some((s) => s.path === newCafe(x).page), `${name}: the café`);
    assert.ok(d.stops.at(-1).role === "stay" && x.body.days[0].stops.some((s) => s.role === "stay" && s.page === d.stops.at(-1).path), `${name}: the night's stay`);
    assert.ok(d.stops.length <= 10);
    assert.ok(last.plan.fixed.some((t) => /^1일차: 하루 10곳\(숙소 포함\)을 넘어 .+ 뺐습니다$/u.test(t)), last.plan.fixed.join("\n"));
    assert.ok(!last.plan.fixed.some((t) => /다시 짰습니다/u.test(t)), last.plan.fixed.join("\n"));
  }
});

test("edits: a full day loses the place whose going leaves the least empty time, not its last — the café and the page's meals stay", async () => {
  // gate edit fuzz (meals 606 n23, 808 noisy n86): cutting the day's last visit left 18:55–21:00 and 18:00–20:45 empty
  // next to the kept dinner, and the edit failed; e50aeeec9 moved the meals instead
  for (const [name, gone] of [["full_meals606_23", "군산항1981"], ["full_meals808n_86", "동국사"]]) {
    const { x, plan } = await mealsKept(name);
    assert.ok(plan.days[0].stops.some((s) => s.path === newCafe(x).page), `${name}: the café`);
    assert.ok(plan.fixed.includes(`1일차: 하루 10곳(숙소 포함)을 넘어 ${gone}${eul(gone)} 뺐습니다`), `${name}: ${plan.fixed.join("\n")}`);
  }
});

test("edits: a whole move a kept meal stops further on — the stops up to it move and the one next to the meal gives up the time", async () => {
  // gate edit fuzz (1111 noisy n17): the café before a kept dinner needs its leg; the three stops before it run back to
  // a kept lunch — the edit failed; e50aeeec9 moved the lunch 30 minutes earlier with six stops
  const { x, plan } = await mealsKept("chain_1111n_17");
  assert.ok(plan.days[0].stops.some((s) => s.path === newCafe(x).page), "the café");
  assert.ok(plan.fixed.some((t) => /^리즈리: 다음 장소 삼풍식당\(직선 [\d.]+km\)까지 여유 \d+분을 두려고 .+ 함께 당겼습니다 — 깐치멀식생활체험관을 13:15~15:15에서 13:15~\d\d:\d\d(으)?로 줄였습니다$/u.test(t)), plan.fixed.join("\n"));
});

test("edits: readSubmit cuts a full day from its other places, never the stay or a place new to the edit; the model is told the day is full", () => {
  const x = EDITS.find((y) => y.name === "full_1111_58");
  const c = validConditions(x.conditions, new Date(x.now));
  const r = readSubmit(x.input, c, winterKb(), { plan: x.body, request: x.request });
  assert.ok(r.errors.some((e) => /1일차 장소는 숙소를 포함해 10곳까지 — 그날 장소를 더 넣으려면 다른 곳을 하나 뺀다/u.test(e)), r.errors.join("\n"));
  const day = r.salvaged.days[0].stops;
  assert.equal(day.length, 10);
  assert.equal(day.at(-1).role, "stay");
  assert.ok(day.some((s) => s.asked === newCafe(x).page));
  // without an edit: the stay still stays; the last other place goes
  const r0 = readSubmit(x.input, c, winterKb());
  assert.equal(r0.salvaged.days[0].stops.length, 10);
  assert.equal(r0.salvaged.days[0].stops.at(-1).role, "stay");
});

test("edits: a place asked for that cannot be kept fails the edit, naming it — never a 'ready' plan without it", async () => {
  // 2026-11-17 is a Tuesday: 당골 한옥카페 is closed ('매주 화요일') and no other café opens within 3 km that afternoon
  const kb = winterKb();
  const now = new Date("2026-10-18T01:00:00Z");
  const c = validConditions({ date: "2026-11-17", days: 1, start: "10:00", end: "17:00", move: "transit", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null }, now);
  const day = [stop("채만식 문학관", "10:00", "11:30"), stop("유성가든", "12:00", "13:00", "meal"), stop("킹콩놀이터", "13:30", "14:30"), stop("오성산", "15:30", "16:30")];
  const sent0 = [];
  await makePlan({ client: client({ title: "오성산 쪽 하루", summary: "오성산 쪽을 돕니다.", notes: [], days: [{ date: c.date, stops: day }] }), kb, conditions: c, send: (e) => sent0.push(e), now });
  const page = sent0.at(-1).plan;
  assert.equal(page.status, "ready");
  const body = { days: page.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, start: s.start, end: s.end, role: s.role, why: s.why })) })) };
  const edit = validEdit(body, "오후에 카페 하나 더 넣어 주세요", c);
  const k = body.days[0].stops.findIndex((s) => s.page === P("킹콩놀이터"));
  const stops = [...body.days[0].stops];
  stops.splice(k + 1, 0, { page: P("당골 한옥카페"), start: "14:40", end: "15:10", role: "cafe", why: "" });
  const sent = [];
  await makePlan({ client: client({ title: page.title, summary: page.summary, notes: page.notes, days: [{ date: c.date, stops }] }), kb, conditions: c, edit, send: (e) => sent.push(e), now });
  const last = sent.at(-1);
  assert.equal(last.type, "error", JSON.stringify(last.plan && last.plan.fixed));
  assert.equal(last.code, "edit_failed");
  assert.equal(last.message, "요청한 변경으로 넣은 당골 한옥카페를 그날 일정에 맞춰 둘 수 없어 보던 일정을 그대로 두었습니다. 요청을 조금 바꿔 다시 시도해 주세요.");
});

// ------------------------------------------------------------------ 5. a stretch never makes a second lunch
test("a meal stretched to close a stretch keeps its side: the dinner-side meal swapped in on day 2 never becomes a second lunch (meal fuzz 909 n165)", async () => {
  const kb = winterKb();
  const now = new Date("2026-10-18T01:00:00Z");
  const cond = { date: "2026-11-09", days: 2, start: "09:00", end: "17:00", move: "car", with: "kids", adults: 1, kids: [2], seniors: 0, from: "", to: "",
    prefs: ["food", "nature"], needs: ["rain", "parking"], budget: 5000, note: "" };
  const s = (page, start, end, role = "visit", why = "") => ({ page, start, end, role, why });
  const input = { title: "다이도 점심과 군산 여행", summary: "선유도 리조트에서 시작해 일품회집까지 돕니다.", notes: [], days: [
    { date: "2026-11-09", stops: [s("/places/선유도밤바다/", "09:00", "09:30", "meal"), s("/places/대장도/", "09:30", "10:00"), s("/places/장자도여객터미널/", "11:00", "11:30"),
      s("/places/선유도해수욕장/", "11:35", "12:20"), s("/places/남도밥상/", "13:20", "15:50", "meal"), s("/places/선유도/", "16:10", "18:10"),
      s("/places/국립신시도자연휴양림/", "18:25", "19:10"), s("/places/선유도-리조트/", "20:10", "21:10", "stay")] },
    { date: "2026-11-10", stops: [s("/places/일품회집/", "10:30", "13:30", "meal"), s("/places/다이도/", "13:40", "15:40", "meal"), s("/places/미주옥/", "15:40", "16:30", "meal")] }] };
  const { plan } = await run(kb, input, cond);
  assert.equal(plan.status, "ready");
  plan.days.forEach((d, i) => {
    const kinds = d.stops.filter((x) => x.role === "meal").map((x) => mealKind(hm(x.start), hm(x.end)));
    assert.ok(kinds.filter((k) => k === "lunch").length <= 1 && kinds.filter((k) => k === "dinner").length <= 1,
      `day ${i + 1}: ${d.stops.map((x) => `${x.start}-${x.end} ${x.role} ${x.name}`).join(" | ")}`);
    for (const x of d.stops.filter((y) => y.role === "meal")) assert.ok(hm(x.end) - hm(x.start) <= 90, `${x.name} ${x.start}-${x.end}`);
  });
  assert.ok(!plan.fixed.some((t) => /빈 시간을 줄이려고 시작을 15:40에서 15:00로/u.test(t)), plan.fixed.join("\n"));
});

// ------------------------------------------------------------------ 6. the AI's times the code changed
test("stale times: a reason names only its own stop's time; a sentence naming a place, that place's start; hours in words and lengths too", () => {
  const kb = winterKb();
  const c = validConditions({ date: "2026-10-21", days: 1, start: "10:00", end: "20:00", move: "transit", with: "couple", adults: 2, kids: [], prefs: [], needs: [], budget: null }, NOW);
  const st = (name, start, end, role, why) => ({ page: P(name), name, start, end, role, why });
  const plan = { title: "수요일 군산", notes: ["오후에는 18:30에 동국사를 봅니다."],
    summary: "점심은 12:35에 란향에서 먹어요. 저녁은 17:30에 군산한우촌에서 먹어요. 셋째 날 저녁은 군산한우촌에서 두 시간 먹습니다. 10:00에 출발합니다.",
    days: [{ date: "2026-10-21", stops: [
      // moved by the code from 10:00 to 10:30 (10:00 is the reader's start), and from 18:30 to 19:55
      st("우체통거리", "10:30", "11:30", "visit", "10:00에 들릅니다. 골목을 걷습니다."),
      st("란향", "11:40", "12:40", "meal", "11:40에 점심을 먹어요."),
      st("동국사", "13:00", "14:00", "visit", "14:00까지 둘러봅니다."),
      st("초원사진관", "14:20", "15:00", "visit", "15:05쯤 도착해 머뭅니다."),
      // a dinner moved from 16:00–18:00 and cut to 90 minutes
      st("군산한우촌", "17:30", "19:00", "meal", "네 시에 저녁을 먹어요. 오후 네 시 이른 저녁입니다. 두 시간 동안 천천히 먹습니다. 한우를 굽습니다."),
      st("월명공원", "19:20", "19:55", "visit", "18:30에 들릅니다.")] }] };
  const out = staleWords(plan, c, kb);
  const why = (n) => plan.days[0].stops.find((s) => s.name === n).why;
  assert.equal(why("우체통거리"), "골목을 걷습니다.");
  assert.equal(why("란향"), "11:40에 점심을 먹어요.");
  assert.equal(why("동국사"), "14:00까지 둘러봅니다.");
  assert.equal(why("초원사진관"), "");
  assert.equal(why("군산한우촌"), "한우를 굽습니다.");
  assert.equal(why("월명공원"), "");
  assert.equal(plan.summary, "저녁은 17:30에 군산한우촌에서 먹어요. 10:00에 출발합니다.");
  assert.deepEqual(plan.notes, []);
  assert.match(out[0], /^AI 설명: 바뀐 일정의 시각이나 끼니와 맞지 않는 문장 \d+개를 뺐습니다$/u);
});

test("closure sentences: a place's own closed weekdays said as the data has them stay on another day's trip ('매주 월요일에 쉽니다' on a Wednesday)", async () => {
  const kb = winterKb();
  const { plan } = await run(kb, { title: "수요일 군산", summary: "근대역사박물관은 매주 월요일에 쉬고 수요일에는 엽니다. 동국사는 수요일에 쉽니다.", notes: [], days: [{ date: WED.date, stops: wedDay({
    museum: "매주 월요일 휴관이라 오늘은 엽니다.", photo: "수요일 휴무입니다." }) }] }, WED);
  assert.equal(plan.summary, "근대역사박물관은 매주 월요일에 쉬고 수요일에는 엽니다.");
  assert.equal(plan.days[0].stops.find((s) => s.name === "근대역사박물관").why, "매주 월요일 휴관이라 오늘은 엽니다.");
  assert.equal(plan.days[0].stops.find((s) => s.name === "초원사진관").why, "");
});

// ------------------------------------------------------------------ 7. a restaurant given as a café
// The verifier's meal fuzz plans (tests/fixtures/plan_r6d_models.json: the generator's conditions and model plan)
const MODELS = JSON.parse(readFileSync(new URL("../fixtures/plan_r6d_models.json", import.meta.url), "utf8"));
const modelRun = (name) => {
  const x = MODELS.find((y) => y.name === name);
  return run(winterKb(), x.input, x.conditions);
};

test("a restaurant that serves meals given as a café for more than an hour is a meal — the meal rules hold for it", async () => {
  const kb = winterKb();
  for (const name of ["cafe_808_113", "cafe_707_3", "cafe_606_23"]) {
    const { plan } = await modelRun(name);
    assert.equal(plan.status, "ready", name);
    plan.days.forEach((d, i) => {
      for (const s of d.stops.filter((x) => x.role === "cafe" && isMeal(kb.docs[x.path]))) {
        assert.ok(hm(s.end) - hm(s.start) <= 60, `${name} day ${i + 1}: ${s.start}-${s.end} cafe ${s.name}`);
      }
      const kinds = d.stops.filter((x) => x.role === "meal").map((x) => mealKind(hm(x.start), hm(x.end)));
      assert.ok(kinds.filter((k) => k === "lunch").length <= 1 && kinds.filter((k) => k === "dinner").length <= 1, `${name} day ${i + 1}`);
      for (const x of d.stops.filter((y) => y.role === "meal")) assert.ok(hm(x.end) - hm(x.start) <= 90, `${name} ${x.name} ${x.start}-${x.end}`);
    });
  }
  // the model's own lunch stays the lunch; the café read as a meal is the one that gives way (606 n23: 장가네 12:10–14:40
  // as a café right after the lunch at 등대로)
  const { plan } = await modelRun("cafe_606_23");
  assert.ok(plan.fixed.some((t) => /^장가네: 식사가 되는 음식점에서 2시간 30분 머물러 카페가 아닌 식사로 두었습니다$/u.test(t)), plan.fixed.join("\n"));
  assert.ok(!plan.days[0].stops.some((s) => s.name === "장가네"));
});

// ------------------------------------------------------------------ 8. an edit that changes nothing
test("a sent plan sent back unchanged as an edit comes back unchanged — no soft swap made again, no meal trimmed", async () => {
  for (const name of ["same_808_195", "same_808_63"]) {
    const x = MODELS.find((y) => y.name === name);
    const now = new Date("2026-10-18T01:00:00Z");
    const c = validConditions(x.conditions, now);
    // the plan sent for the model's plan, then that plan sent back as it is
    const sent0 = [];
    await makePlan({ client: client(x.input), kb: winterKb(), conditions: c, send: (e) => sent0.push(e), now });
    const page = sent0.at(-1).plan;
    const body = { days: page.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, start: s.start, end: s.end, role: s.role, why: s.why })) })) };
    const sent = [];
    await makePlan({ client: client({ title: page.title, summary: page.summary, notes: page.notes, days: body.days }), kb: winterKb(), conditions: c,
      edit: validEdit(body, "걷는 거리를 조금 줄여 주세요", c), send: (e) => sent.push(e), now });
    const back = sent.at(-1).plan;
    const rows = (p) => p.days.map((d) => d.stops.map((s) => `${s.path}|${s.start}|${s.end}|${s.role}`));
    assert.deepEqual(rows(back), rows(page), name);
  }
});

test("a name ending in brackets takes the particle of the last word inside them ('…가옥(히로쓰가옥)이', '…(월명호수)가')", () => {
  assert.equal(iga("군산신흥동일본식가옥(히로쓰가옥)"), "이");
  assert.equal(iga("군산 제1수원지제방 (월명호수)"), "가");
  assert.equal(iga("MCL"), "이(가)");
});
