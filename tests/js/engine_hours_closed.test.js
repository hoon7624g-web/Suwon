// The hours and closed days as the data writes them (영주·세종 집중 분석 2026-10-24, the same engine): a day of two
// sessions (SJ-D02), the last entry said as 'N시간 전' (YJ-03; 군산's own '마감시간 30분 전' and '폐관 30분 전' too) and a
// closed-day value with an exception, a 설·추석 clause and n-th words written '첫 번째' (SJ-D03). The values are the
// sites' own (세종·영주 /chat/docs.json, 군산 data/gunsan), each with its source.
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge } from "./first_city.js";
import { entryBefore, sessionsIn } from "../../chatbot/knowledge.js";
import { breakOf, fitsHours } from "../../chatbot/plan_geo.js";
import { readSubmit, settle, validConditions } from "../../chatbot/planner.js";

const NOW = new Date("2026-10-24T01:00:00Z");   // 2026-10-24 (Sat) 10:00 KST
const place = (t, f) => ({ t, k: "place", x: `${t} — 관광지 · 박물관`, f: { kd: "attraction", ty: "박물관", g: [36.5, 127.27], ...f } });
// 세종 /places/gungnibeorinibangmulgwan/ (한국관광공사 TourAPI)
const CHILD = place("국립어린이박물관", {
  h: [{ p: "한국관광공사 TourAPI", t: "[1회차]- 09:30~13:00 (입장 마감 12:30) [2회차]- 14:00~17:30 (입장 마감 17:00) ※ 사전 온라인 예약 필수 (잔여석에 한해 현장 발권)" }],
  c: [{ p: "한국관광공사", t: "매주 월요일 (단 ,월요일이 공휴일인 경우 그 다음 첫 번째 평일), 1월 1일, 설·추석 전날, 당일" }] });
// 세종 /places/gungnipsejongdoseogwan/, /places/geumgangsumogwon/ (closed days: 한국관광공사)
const LIBRARY = place("국립세종도서관", { h: [{ p: "한국관광공사 TourAPI", t: "09:00~18:00" }],
  c: [{ p: "한국관광공사", t: "매월 둘째, 넷째 월요일, 일요일을 제외한 관공서의 공휴일 (단, 설·추석 연휴 기간 중 일요일은 휴관), 기타 관장이 필요하다고 인정하는 날" }] });
const ARBORETUM = place("금강수목원", { h: [{ p: "한국관광공사 TourAPI", t: "- 하절기(3월~10월) 09:00~18:00 (입장 마감 17:00)- 동절기(11월~2월) 09:00~17:00 (입장 마감 16:00)" }],
  c: [{ p: "한국관광공사", t: "매월 첫 번째, 세 번째 수요일" }] });
// 영주 /places/yeongju-sosuseowon/, /places/k-munhwatemapakeu-seonbisesang/ (한국관광공사 TourAPI)
const SOSU = place("영주 소수서원", { h: [{ p: "한국관광공사 TourAPI", t: "[11월~2월]09:00~17:00[3월~5월/9월~10월]09:00~18:00[6월~8월]09:00~19:00※ 입장시간은 관람종료 1시간 전까지 가능※ 자세한 사항은 전화문의 요망" }],
  c: [{ p: "한국관광공사", t: "연중무휴" }] });
// 군산 /places/일제강점기-군산역사관/ (한국관광공사 TourAPI), /places/채만식-문학관/ (군산시 문화관광 상세 정보표)
const ILJE = place("일제강점기 군산역사관", { h: [{ p: "한국관광공사 TourAPI", t: "[하절기(3월~10월)] 09:00~18:00[동절기(11월~2월)] 09:00~17:00※ 입장마감은 마감시간 30분 전" }],
  c: [{ p: "한국관광공사", t: "매주 월요일" }] });
const CHAE = place("채만식 문학관", { h: [{ p: "군산시 문화관광 상세 정보표", t: "하절기 10:00~18:00 / 동절기 10:00~17:00, 폐관 30분 전까지 입장" }],
  c: [{ p: "군산시", t: "매주 월요일" }] });
// 군산 /places/압강옥/, /places/군산-공설시장/ (closed days: 한국관광공사)
const APGANG = place("압강옥", { kd: "food", h: [{ p: "한국관광공사 TourAPI", t: "11:40~20:30 - 준비시간 14:30~17:00 - 마지막 주문 19:30" }], c: [{ p: "한국관광공사", t: "매달 2, 4번째 화요일" }] });
const MARKET = place("군산 공설시장", { h: [{ p: "한국관광공사 TourAPI", t: "상시 개방" }], c: [{ p: "한국관광공사", t: "매월 첫째 / 셋째 일요일" }] });

const DOCS = { "/places/child/": CHILD, "/places/library/": LIBRARY, "/places/arboretum/": ARBORETUM, "/places/sosu/": SOSU,
  "/places/ilje/": ILJE, "/places/chae/": CHAE, "/places/apgang/": APGANG, "/places/market/": MARKET };
const kb = new Knowledge({ catalog: "# c", docs: { v: 1, site: "https://gunsan.webforai.kr", docs: DOCS, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
const one = (page, date, start = "", end = "") => kb.checkPlan({ date, stops: [{ page, start, end }], move: "transit" }).stops[0];

test("SJ-D02: every session of the day is read, each with its own last entry", () => {
  assert.deepEqual(sessionsIn(CHILD.f.h[0].t), [{ open: 570, close: 780, last: 750, name: "1회차" }, { open: 840, close: 1050, last: 1020, name: "2회차" }]);
  // ranges that are weekdays', seasons' or a break's are no sessions (군산 values)
  for (const t of ["[평일]- 09:00~19:30 - 마지막 주문 18:20 [주말] - 08:30~20:00", "시간여행관광안내소(10:00~17:00) / 초원사진관(09:00~21:30)",
    "10:00~17:00 (점심시간 12:00~13:00)", "평일 10:00~12:00 / 주말 13:00~18:00", "[하절기]08:00~19:00[동절기]08:00~18:00"]) {
    assert.equal(sessionsIn(t), null, t);
  }
});

test("SJ-D02: a visit in the second session passes; one between the two is the gap the data shows; sessions are a check", () => {
  const ses = "이용시간 — 한국관광공사 TourAPI: 하루 2회차(09:30~13:00 · 14:00~17:30)·예약 안내 있음 — 들어갈 회차와 예약·발권 마감 확인 필요";
  // (before: '끝 16:00가 닫는 시각 13:00보다 늦음, 시작 14:00가 입장·주문 마감 12:30보다 늦음')
  let s = one("/places/child/", "2026-10-25", "14:00", "16:00");
  assert.deepEqual([s.day, s.flags, s.checks], ["open", [], [ses]]);
  s = one("/places/child/", "2026-10-25", "13:30", "15:30");
  assert.deepEqual(s.flags, ["한국관광공사 TourAPI 기준 시작 13:30이 1회차(09:30~13:00)·2회차(14:00~17:30) 사이 — 2회차 시작 14:00"]);
  s = one("/places/child/", "2026-10-25", "12:40", "13:30");
  assert.deepEqual(s.flags, ["한국관광공사 TourAPI 기준 끝 13:30이 1회차(09:30~13:00) 끝 13:00보다 늦음, 시작 12:40이 1회차 입장·주문 마감 12:30보다 늦음"]);
  // (the ticket times — 발권 마감 10:30 — are not in the data: the check says to look them up, never a time of its own)
  s = one("/places/child/", "2026-10-25", "11:00", "12:30");
  assert.deepEqual([s.flags, s.checks], [[], [ses]]);
  // the planner's own test keeps to one session; its breaks hold the gap from the first one's last entry
  const info = { hours: s.hours };
  assert.equal(fitsHours(kb, info, "/places/child/", 840, 960), true);
  assert.equal(fitsHours(kb, info, "/places/child/", 810, 930), false);
  assert.equal(fitsHours(kb, info, "/places/child/", 760, 780), false);
  assert.deepEqual(breakOf(CHILD.f, 810, 930), [750, 840, "한국관광공사 TourAPI", "1회차 입장 마감부터 2회차 시작 전까지"]);
  assert.equal(breakOf(CHILD.f, 810, 930, { sessions: false }), null);
});

test("SJ-D02: the planner moves a visit planned between the sessions into one, never swaps it for its closing", () => {
  const c = validConditions({ date: "2026-10-25", days: 1, start: "09:00", end: "18:00", move: "car", with: "kids", adults: 1, kids: [7],
    prefs: [], needs: [], budget: null, note: "" }, NOW);
  const mini = new Knowledge({ catalog: "# c", docs: { v: 1, site: "https://gunsan.webforai.kr", docs: { "/places/child/": CHILD }, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
  const ask = (start, end) => {
    const r = readSubmit({ title: "t", summary: "", notes: [], days: [{ date: c.date, stops: [{ page: "/places/child/", start, end, role: "visit", why: "" }] }] }, c, mini);
    const said = settle(r.plan, c, mini);
    return { stop: r.plan.days[0].stops.map((s) => [s.name, s.start]), said: said.join("\n") };
  };
  let r = ask("13:30", "15:30");
  assert.deepEqual(r.stop, [["국립어린이박물관", "14:00"]]);
  assert.match(r.said, /1회차 입장 마감부터 2회차 시작 전까지 12:30~14:00을 피해 13:30~15:30에서 14:00~15:30으로 줄였습니다/u);
  r = ask("12:40", "13:30");
  assert.deepEqual(r.stop, [["국립어린이박물관", "14:00"]]);
});

test("YJ-03: the last entry said as 'N시간 전' or 'N분 전' before the closing, in every wording the data has", () => {
  for (const [t, n] of [["※ 입장시간은 관람종료 1시간 전까지 가능", 60], ["※ 입장 마감 : 운영 종료 1시간 전", 60], ["※ 입장마감은 마감시간 30분 전", 30],
    ["폐관 30분 전까지 입장", 30], ["※ 입장은 종료 30분 전까지 가능", 30], ["종료 1시간 30분 전까지 입장", 90], ["09:00~18:00", null]]) {
    assert.equal(entryBefore(t), n, t);
  }
  // (before: all of these passed as '계획한 시각은 이 시간 안')
  assert.deepEqual(one("/places/sosu/", "2026-10-27", "17:30", "18:00").flags, ["한국관광공사 TourAPI 기준 시작 17:30이 입장·주문 마감 17:00보다 늦음"]);
  assert.deepEqual(one("/places/sosu/", "2026-11-03", "16:30", "17:00").flags, ["한국관광공사 TourAPI 기준 시작 16:30이 입장·주문 마감 16:00보다 늦음"]);
  assert.deepEqual(one("/places/sosu/", "2026-10-27", "16:50", "17:50").flags, []);
  assert.deepEqual(one("/places/ilje/", "2026-10-27", "17:45", "18:00").flags, ["한국관광공사 TourAPI 기준 시작 17:45이 입장·주문 마감 17:30보다 늦음"]);
  // a season with no months: the hours every season keeps, the last entry before the earliest closing
  assert.deepEqual(one("/places/chae/", "2026-11-03", "16:45", "17:00").flags, ["군산시 문화관광 상세 정보표 기준 시작 16:45이 입장·주문 마감 16:30보다 늦음"]);
});

test("SJ-D03: '일요일을 제외한' is an exception, a 설·추석 clause holds in that 연휴 only, '첫 번째·세 번째' are read", () => {
  // 국립세종도서관 (before: every Sunday closed, the Monday's '둘째, 넷째' given to it)
  assert.equal(one("/places/library/", "2026-10-25").day, "open");
  assert.equal(one("/places/library/", "2026-11-01").day, "open");
  assert.equal(one("/places/library/", "2026-10-26").day, "closed");   // 넷째 월요일
  assert.equal(one("/places/library/", "2026-10-19").day, "open");     // 셋째 월요일
  const seol = one("/places/library/", "2027-02-07");                  // 설 연휴의 일요일
  assert.equal(seol.day, "unknown");
  assert.ok(seol.checks.some((x) => x.startsWith("설 연휴 중 일요일 규칙 — 그날은 설 연휴의 일요일")), seol.checks.join("\n"));
  // 금강수목원 (before: 10-21, the third Wednesday, open)
  assert.deepEqual(["2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28"].map((d) => one("/places/arboretum/", d).day), ["closed", "open", "closed", "open"]);
  // 군산: a list of n-th split by a comma or a slash still belongs to its weekday
  assert.deepEqual(["2026-11-03", "2026-11-10", "2026-11-17", "2026-11-24"].map((d) => one("/places/apgang/", d).day), ["open", "closed", "open", "closed"]);
  assert.deepEqual(["2026-11-01", "2026-11-08", "2026-11-15"].map((d) => one("/places/market/", d).day), ["closed", "open", "closed"]);
});

test("SJ-D03: an n-th belongs to its own weekday, never to the one after it (영주 아테네레스토랑 '5째주 일요일, 4째주 월요일 휴무')", () => {
  const f = place("아테네레스토랑", { kd: "food", h: [{ p: "영주시", t: "11:00~21:00" }], c: [{ p: "영주시", t: "5째주 일요일, 4째주 월요일 휴무, 1, 3, 2" }] });
  const k = new Knowledge({ catalog: "# c", docs: { v: 1, site: "https://gunsan.webforai.kr", docs: { "/places/a/": f }, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
  const at = (date) => k.checkPlan({ date, stops: [{ page: "/places/a/", start: "", end: "" }] }).stops[0].day;
  assert.equal(at("2026-11-23"), "closed");   // 넷째 월요일
  assert.equal(at("2026-11-30"), "open");     // 다섯째 월요일 (before: closed — the Sunday's '5째주')
  assert.equal(at("2026-11-29"), "closed");   // 다섯째 일요일
});
