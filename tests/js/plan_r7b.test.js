// Round 7, the live check's second wave (2026-10-19, 9b1da8fdc on the public server, 10 plans) and what the review of
// the first wave left: the evening after the dinner filled with a park, a wind farm and a street in the dark (B04); an
// edit to 'the town instead of the islands' that kept the island's lunch 33 km off (B09); the model's sentences that
// said the plan had no stay or no meals when it had them; one source's '없음' left out of the wheelchair row; a
// '예약제' hours value taken as a place open then; a swap for a budget that put in a place with no fee data. The model's
// own plans of B04 and B09 and the site's places around them are in tests/fixtures/plan_r7b_live.json (public/chat,
// cut to the planner's fields).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { Knowledge } from "./first_city.js";
import { regionOf, tokens } from "../../chatbot/knowledge.js";
import { freeRank, placesOf } from "../../chatbot/plan_geo.js";
import { endsDay, hm, needAt } from "../../chatbot/plan_state.js";
import { makePlan, readSubmit, validConditions, validEdit } from "../../chatbot/planner.js";

const NOW = new Date("2026-10-19T01:00:00Z");   // 2026-10-19 (Mon) 10:00 KST
const FX = JSON.parse(readFileSync(new URL("../fixtures/plan_r7b_live.json", import.meta.url), "utf8"));
const R7 = JSON.parse(readFileSync(new URL("../fixtures/plan_r7_live.json", import.meta.url), "utf8"));
const knowledge = (fx) => new Knowledge({ catalog: "# catalog", docs: { v: 1, site: fx.site, docs: fx.docs, alias: {}, ext: [], tickets: fx.tickets },
  index: { v: 1, docs: Object.fromEntries(Object.entries(fx.docs).map(([key, d]) => [key, [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")]])) } });
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
function client(input) {
  return { messages: { stream() {
    const message = { role: "assistant", content: [{ type: "tool_use", id: "toolu_1", name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
async function run(fx, x, input = x.input) {
  const c = validConditions(x.conditions, NOW);
  const edit = x.plan ? validEdit(x.plan, x.request, c) : null;
  const sent = [];
  await makePlan({ client: client(input), kb: knowledge(fx), conditions: c, edit, send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.equal(plan.status, "ready");
  assert.deepEqual(plan.flags, []);
  assert.ok(!plan.fixed.some((t) => /^일정 전체:/u.test(t)), "never the code's own trip");
  return plan;
}

test("the evening after the dinner is the reader's own: no place the code puts in after it, the night's stay right after it", async () => {
  // 혼자 2박 3일 by car, 06:00–23:00 (B04): the model's days end at 17:30–18:00 — before, the code put in the dinner and
  // then 19:15–23:00 a park and a wind farm, a supermarket and a street, a bridge and a hillside village
  const plan = await run(FX, FX.cases.find((x) => x.name === "B04"));
  for (const [i, d] of plan.days.entries()) {
    const dinner = d.stops.find((s) => s.role === "meal" && hm(s.start) >= 16 * 60);
    assert.ok(dinner, `day ${i + 1} has its dinner`);
    const after = d.stops.filter((s) => s.role !== "stay" && hm(s.start) >= hm(dinner.end));
    assert.deepEqual(after.filter((s) => s.added).map((s) => s.name), [], `day ${i + 1}: nothing the code put in after the dinner`);
    const stay = d.stops.find((s) => s.role === "stay");
    if (i < plan.days.length - 1) assert.ok(stay && hm(stay.start) < 21 * 60, `day ${i + 1}: the stay in the evening, ${stay && stay.start}`);
  }
  assert.ok(!plan.fixed.some((t) => /빈 시간 19:00~23:00/u.test(t)), plan.fixed.join("\n"));
});

test("a night's stay near the reader's end ends the day only past the dinner's window when the day runs past it", () => {
  // (no page to read: the model's stay, its check-in taken as given)
  const stay = (start) => ({ role: "stay", start, end: "23:00" });
  assert.equal(endsDay(stay("19:10"), null, { end: "21:00" }, []), false);   // wave B: B06's stay at 19:10, no dinner
  assert.equal(endsDay(stay("19:40"), null, { end: "21:00" }, []), true);
  assert.equal(endsDay(stay("17:30"), null, { end: "19:00" }, []), true);    // a day to 19:00 has no dinner to wait for
  assert.equal(endsDay(stay("19:10"), null, { end: "21:00" }, [{ role: "meal", start: "17:30", end: "18:30" }]), true);
});

test("an edit's meal off the way — the island's lunch between two stops in town — is a restaurant near them instead", async () => {
  // B09: '둘째 날은 섬 대신 시내 위주로' — the model kept 남도밥상 (선유도) between 군산 공설시장 and 군산 영화의 거리
  const fx = FX;
  const plan = await run(fx, fx.cases.find((x) => x.name === "B09"));
  const d = plan.days[1];
  assert.ok(!d.stops.some((s) => s.name === "남도밥상"), d.stops.map((s) => s.name).join(" | "));
  const line = plan.fixed.find((t) => t.startsWith("2일차 점심: 앞뒤 장소 군산 공설시장·군산 영화의 거리에서 직선"));
  assert.match(line || "", /km 넘게 떨어진 남도밥상을 빼고, 앞 장소 군산 공설시장에서 가까운 음식점 /u, plan.fixed.join("\n"));
  const lunch = d.stops.find((s) => s.role === "meal" && hm(s.start) < 15 * 60);
  assert.equal(regionOf(fx.docs[lunch.path]), regionOf(fx.docs["/places/군산-공설시장/"]));
  // the ride that went with it went too: 군산 영화의 거리 is not pushed to 15:20 for a leg from the island
  assert.ok(hm(d.stops.find((s) => s.name === "군산 영화의 거리").start) < 15 * 60);
  // a meal the page had off the way already stays (the reader saw it so)
  const page = structuredClone(fx.cases.find((x) => x.name === "B09"));
  page.plan.days[1].stops = page.input.days[1].stops.map((s) => ({ ...s }));
  page.request = "첫날 저녁을 조금 늦춰 주세요";
  const kept = await run(fx, page);
  assert.ok(kept.days[1].stops.some((s) => s.name === "남도밥상"), kept.days[1].stops.map((s) => s.name).join(" | "));
});

test("the model's sentences that say the plan has no night's stay or no meals go when it has them", async () => {
  // A10 (round 7 review): '요청하신 숙소는 이 일정에 넣지 않았습니다', and the stays the code put in
  const x = R7.cases.find((y) => y.name.startsWith("A10"));
  const input = { ...structuredClone(x.input), summary: "섬과 바다를 도는 2박 3일입니다.",
    notes: ["요청하신 숙소는 이 일정에 넣지 않았습니다. 숙소 예약은 직접 하세요.", "식사 단계는 음식점 페이지가 아니라 시장 리스트로 대체했습니다."] };
  const plan = await run(R7, x, input);
  assert.ok(plan.days.slice(0, -1).every((d) => d.stops.some((s) => s.role === "stay")));
  const text = [plan.summary, ...plan.notes].join(" ");
  assert.ok(!/넣지 않았습니다|대체했습니다/u.test(text), text);
  assert.ok(text.includes("숙소 예약은 직접 하세요."), text);
  // (the meals are the model's from the first: their sentence goes when the text is first read; the stays the code put
  // in later, theirs then)
  assert.ok(plan.fixed.includes("AI 설명: 일정에 있는 식사를 넣지 않았다고 말하는 문장 1개를 뺐습니다"), plan.fixed.join("\n"));
  assert.ok(plan.fixed.includes("AI 설명: 일정에 있는 밤 숙소를 넣지 않았다고 말하는 문장 1개를 뺐습니다"), plan.fixed.join("\n"));
});

test("the wheelchair row has every source's toilet and rental, '없음' too — values that differ with their sources and the phone check", () => {
  // 진포해양공원 (round 7 review A18): 군산시 '없음', TourAPI '장애인 화장실 있음' — the row read '장애인 화장실 있음' alone
  const f = { ac: [{ k: "accessible_route", p: "한국관광공사 무장애 여행 정보(TourAPI)", t: "출입구까지 경사로가 설치되어 있음(완만함)" },
    { k: "wheelchair", p: "군산시 문화관광", t: "없음" }, { k: "accessible_toilet", p: "군산시 문화관광", t: "없음" },
    { k: "accessible_toilet", p: "한국관광공사 무장애 여행 정보(TourAPI)", t: "장애인 화장실 있음" }] };
  assert.deepEqual(needAt("wheelchair", f, "visit"), { state: "ok", text: "출입구: 출입구까지 경사로가 설치되어 있음(완만함) · 휠체어 대여 없음 · "
    + "장애인 화장실 없음(군산시 문화관광) / 장애인 화장실 있음(한국관광공사 무장애 여행 정보(TourAPI)) — 출처마다 달라 방문 전 전화 확인" });
});

test("an hours value with no time in it beside another source's times is a check — '예약제' is no place open then", () => {
  const doc = (h) => ({ t: "온새미로", k: "place", x: "온새미로 — 음식점 · 한식", f: { kd: "food", ty: "한식", g: [35.98, 126.71], c: [{ p: "군산시", t: "연중무휴" }], h } });
  const kb = (h) => new Knowledge({ catalog: "# c", docs: { v: 1, site: FX.site, docs: { "/places/온새미로/": doc(h) }, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
  const at = (h) => kb(h).checkPlan({ date: "2026-11-09", stops: [{ page: "/places/온새미로/", start: "12:40", end: "13:40" }], move: "transit" }).stops[0].checks;
  assert.deepEqual(at([{ p: "군산시 문화관광", t: "예약제 / 특별한 휴무없음" }, { p: "한국관광공사 TourAPI", t: "12:00~21:30" }]),
    ["군산시 문화관광 이용시간 '예약제 / 특별한 휴무없음' — 다른 출처의 시각과 달라 방문 전 전화 확인"]);
  // a value whose times the check cannot read by day says no other hours; '상시 개방' is open
  assert.deepEqual(at([{ p: "군산시 문화관광", t: "09:00~21:00" }, { p: "한국관광공사 TourAPI", t: "월요일 09:00~18:00 화요일~일요일 09:00~21:30" }]), []);
  assert.deepEqual(at([{ p: "군산시 문화관광", t: "09:00~21:00" }, { p: "한국관광공사 TourAPI", t: "상시 개방" }]), []);
});

test("with a budget, a place with no fee data comes after one free or priced", () => {
  const c = { needs: [], budget: 10000 };
  assert.equal(freeRank(c, { kd: "attraction" }), 1);
  assert.equal(freeRank(c, { kd: "attraction", fee: { free: true } }), 0);
  assert.equal(freeRank(c, { kd: "attraction", fee: { tab: { 성인: 1000 } } }), 0);
  assert.equal(freeRank({ needs: [], budget: null }, { kd: "attraction" }), 0);
});

test("a place on an island reached only by ferry is no stop: the site's ferry guide names the islands, the address the place", () => {
  // round 7 review A03: 고군산섬잇길 (옥도면 방축도길) as a 30-minute drive from 선유도 — 방축도 is reached by 고군산카훼리호
  const place = (t, addr, g) => ({ t, k: "place", x: `${t} — 관광지 · 자연·야외\n위치: 옥도면 · 고군산 권역\n- 주소: 전북특별자치도 군산시 옥도면 ${addr} — 한국관광공사 TourAPI (출처 확인 2026-10-08)`,
    f: { kd: "attraction", ty: "자연·야외", g, c: [{ p: "한국관광공사", t: "연중무휴" }], h: [{ p: "한국관광공사 TourAPI", t: "상시 개방" }] } });
  const docs = {
    "/guides/군산-섬-여객선/": { t: "군산 섬 여객선", k: "guide", x: "군산 섬 여객선 — 가이드\n요약: 군산의 섬 여객선은 군산 연안여객터미널(임해로 378-8)에서 어청도·개야도·연도로, 장자도 선착장에서 관리도·방축도·명도·말도를 도는 순환 항로로 다닙니다." },
    "/places/고군산섬잇길/": place("고군산섬잇길", "방축도길 23-1", [35.849313, 126.376547]),
    "/places/선유도/": place("선유도", "선유도리 산 1", [35.810205, 126.412405]),
    "/places/장자도/": place("장자도", "장자도1길 10", [35.8086, 126.4017]),
  };
  const kb = new Knowledge({ catalog: "# c", docs: { v: 1, site: FX.site, docs, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
  assert.deepEqual([...kb.ferry], [["/places/고군산섬잇길/", "방축도"]]);
  assert.deepEqual(placesOf(kb).map((p) => p.doc.t).sort(), ["선유도", "장자도"]);
  const c = validConditions({ ...FX.cases[0].conditions, date: "2026-11-15", days: 1, start: "09:00", end: "18:00" }, NOW);
  const r = readSubmit({ title: "t", summary: "", notes: [], days: [{ date: c.date, stops: [
    { page: "/places/고군산섬잇길/", start: "09:00", end: "10:00", role: "visit", why: "" }, { page: "/places/선유도/", start: "10:30", end: "12:00", role: "visit", why: "" }] }] }, c, kb);
  assert.deepEqual(r.plan.days[0].stops.map((s) => s.name), ["선유도"]);
  assert.ok(r.fixes.includes("1일차 고군산섬잇길: 배로만 가는 섬(방축도)에 있어 일정에서 뺐습니다 — 배 시각은 사이트에 없음(섬 여객선 가이드 참고)"), r.fixes.join("\n"));
  assert.ok(r.errors.some((e) => /배로만 가는 섬\(방축도\)/u.test(e)));
});
