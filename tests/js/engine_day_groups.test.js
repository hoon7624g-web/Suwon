// Hours by day group, the days only a place opens, rooms with hours of their own, outdoors by TourAPI's class and a
// plan's words read against its stops (QA 2026-10-26 영주각·세종각 감사 F01·F03·F04·F05). The values are the sites' own
// (세종·영주 /chat/docs.json, each with its source); the last tests read the real knowledge (CHAT_KB_DIR, the city's).
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge, loadKnowledge } from "./first_city.js";
import { dayGroups, dayPart, onlyDays, roomParts } from "../../chatbot/knowledge.js";
import { isOutdoor } from "../../chatbot/plan_geo.js";
import { needAt } from "../../chatbot/plan_state.js";
import { planClaim } from "../../chatbot/planner.js";

const place = (t, x, f) => ({ t, k: "place", x: `${t} — ${x}`, f: { g: [36.5, 127.27], ...f } });
// 세종 /places/gungnipsejongdoseogwan/ (한국관광공사 TourAPI)
const LIBRARY_HOURS = "[인문예술자료실/일반자료실]- 평일 09:00~21:00- 주말 09:00~18:00[어린이자료실]-09:00~18:00※ 시설별 이용시간 상이하므로 홈페이지 참조";
const LIBRARY = place("국립세종도서관", "관광지 · 문화시설\n위치: 어진동 · 신도심·호수공원 권역", { kd: "attraction", ty: "문화시설",
  h: [{ p: "한국관광공사 TourAPI", t: LIBRARY_HOURS }],
  c: [{ p: "한국관광공사", t: "매월 둘째, 넷째 월요일 / 일요일을 제외한 관공서의 공휴일 (단, 설·추석 연휴 기간 중 일요일은 휴관) / 기타 관장이 필요하다고 인정하는 날" }] });
// 영주 /places/kape-seonbikkot/ (한국관광공사 TourAPI)
const CAFE = place("카페, 선비꽃", "음식점 · 카페\n위치: 순흥면 · 소수서원·순흥 권역", { kd: "food", ty: "카페",
  h: [{ p: "한국관광공사 TourAPI", t: "(매주 목. 금. 토. 일 요일만 영업) 오전 11:00 ~ 오후 8시 30분" }] });
// 영주 /places/huibangpokpo/ (TourAPI lclsSystm3 NA010300 폭포 — docs.json f.od), /places/sosubakmulgwan/
const FALLS = place("희방폭포", "관광지\n위치: 풍기읍 · 풍기·소백산 권역", { kd: "attraction", od: "폭포" });
const MUSEUM = place("소수박물관", "관광지 · 박물관·전시\n위치: 순흥면 · 소수서원·순흥 권역", { kd: "attraction", ty: "박물관·전시",
  h: [{ p: "한국관광공사 TourAPI", t: "09:00~19:00" }], c: [{ p: "한국관광공사", t: "연중무휴" }] });
const DOCS = { "/places/library/": LIBRARY, "/places/cafe/": CAFE, "/places/falls/": FALLS, "/places/museum/": MUSEUM };
const kb = new Knowledge({ catalog: "# c", docs: { v: 1, site: "https://gunsan.webforai.kr", docs: DOCS, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
const one = (page, date, start = "", end = "") => kb.checkPlan({ date, stops: [{ page, start, end }], move: "car" }).stops[0];

test("F03: an hours value by day group gives each day its own part — never the first range whatever the day", () => {
  const W = "- 평일 09:00~21:00- 주말 09:00~18:00";
  assert.deepEqual([dayPart(W, 0), dayPart(W, 3)], [{ seg: "주말 09:00~18:00" }, { seg: "평일 09:00~21:00" }]);
  // labels after the range, weekdays in a list, a day no part names (said, never the first range), a weekday range
  assert.deepEqual(dayPart("10:30 ~ 22:00(평일), 10:00 ~ 22:00(주말)", 6), { seg: "주말 10:00 ~ 22:00" });
  assert.deepEqual(dayPart("- 평일, 일요일 10:00~18:00 - 토요일 10:00~19:00", 0), { seg: "평일, 일요일 10:00~18:00" });
  assert.deepEqual(dayPart("- 평일 10:20~19:40 - 토요일 10:20~15:30", 0), { why: "일요일 시간이 이 값에 없음" });
  assert.deepEqual(dayPart("월요일 09:00~18:00 화·수·목·금·토·일요일 09:00~21:30", 2), { seg: "화·수·목·금·토·일요일 09:00~21:30" });
  assert.deepEqual(dayPart("화 ~ 일 10:00~18:00", 3), { seg: "화 ~ 일 10:00~18:00" });
  assert.equal(dayPart("[평일]- 11:30~22:00 - 준비시간 15:30~17:00[주말]- 11:30~22:00- 준비시간 16:00~17:00", 2).seg, "평일]- 11:30~22:00 - 준비시간 15:30~17:00");
  // a weekday on its own line before its group; a holiday on the week's halves alone (to check) or with its own line;
  // the hours before the first group on the other days — not when that part names a closed day
  const M = "- 평일 11:30~22:00 - 금요일 11:30~22:30 - 토요일 11:30~22:30";
  assert.deepEqual([dayPart(M, 5), dayPart(M, 3)], [{ seg: "금요일 11:30~22:30" }, { seg: "평일 11:30~22:00" }]);
  assert.deepEqual(dayPart("- 평일 09:00~18:00- 주말 09:00~17:00", 3, true), { why: "공휴일 — 평일·주말 어느 쪽 시간인지 이 값에 없음" });
  assert.deepEqual(dayPart("월·화·수·목·금요일 10:00~21:00 / 토·일요일 및 공휴일 11:00~22:00", 3, true), { seg: "토·일요일 및 공휴일 11:00~22:00" });
  assert.deepEqual(dayPart("11:00 ~ 17:00 / 토요일 12:00 ~ 19:00", 2), { seg: "11:00 ~ 17:00" });
  assert.deepEqual(dayPart("09:00~18:00 (월요일 휴무) / 토요일 10:00~15:00", 2), { why: "화요일 시간이 이 값에 없음" });
  // a closed day, a word inside a word, months: no hours by day
  for (const t of ["09:00~18:00 (월요일 휴무)", "매일 10:00~18:00", "3월~10월 09:00~18:00", "일반자료실 09:00~18:00"]) assert.equal(dayPart(t, 1), null, t);
  assert.deepEqual([...dayGroups("목. 금. 토. 일 요일만")[0].days].sort(), [0, 4, 5, 6]);
});

test("F03: rooms with hours of their own — a Sunday after 18:00 is past every room's closing; a weekday after 18:00 a room's check", () => {
  assert.deepEqual(roomParts(LIBRARY_HOURS).map((x) => x.name), ["인문예술자료실/일반자료실", "어린이자료실"]);
  // (before: 09:00~21:00 on every day, and 2026-11-15 (Sun) 19:10–20:40 passed)
  let s = one("/places/library/", "2026-11-15", "19:10", "20:40");
  assert.deepEqual(s.flags, ["한국관광공사 TourAPI 기준 끝 20:40이 닫는 시각 18:00보다 늦음"]);
  s = one("/places/library/", "2026-11-12", "19:10", "20:40");
  assert.deepEqual(s.flags, []);
  assert.ok(s.checks.some((x) => /어린이자료실 09:00~18:00은 계획한 시각과 맞지 않음/u.test(x)), s.checks.join("\n"));
  s = one("/places/library/", "2026-11-12", "10:00", "11:30");
  assert.deepEqual([s.flags, s.checks.filter((x) => /시설마다/u.test(x))], [[], []]);
});

test("a closed weekday the hours by day group do not name is no hours to check", () => {
  // 단양 /places/maneulseokgalbimakguksu/ (한국관광공사 TourAPI): every day's hours but Wednesday's, its closed day
  const k2 = new Knowledge({ catalog: "# c", docs: { v: 1, site: "https://gunsan.webforai.kr", alias: {}, ext: [], tickets: [], docs: {
    "/places/m/": place("마늘석갈비막국수", "음식점", { kd: "food", c: [{ p: "한국관광공사", t: "매주 수요일" }],
      h: [{ p: "한국관광공사 TourAPI", t: "[목요일~월요일] - 11:00~20:00 - 준비시간 14:00~17:00 - 마지막 주문 19:00 [화요일] - 11:00~16:00 - 마지막 주문 15:00" }] }) } },
  index: { v: 1, docs: {} } });
  const s = k2.checkPlan({ date: "2026-10-28", stops: [{ page: "/places/m/", start: "14:00", end: "15:00" }] }).stops[0];
  assert.deepEqual([s.day, s.checks.filter((x) => /하나로 읽지 못해/u.test(x))], ["closed", []]);
  const t = k2.checkPlan({ date: "2026-10-27", stops: [{ page: "/places/m/", start: "16:30", end: "17:00" }] }).stops[0];   // a Tuesday: to 16:00
  assert.ok(t.flags.length, JSON.stringify(t));
});

test("F05: a weekday the value says it does not open on is a closed day; a day it names is not", () => {
  assert.deepEqual([...onlyDays(CAFE.f.h[0].t).days].sort(), [0, 4, 5, 6]);
  assert.equal(onlyDays("09:00~18:00 (월요일 휴무)"), null);
  // (before: 2026-10-26 (Mon) 12:10–13:10 kept, '쉬는 날이 사이트에 없음' its only line)
  let s = one("/places/cafe/", "2026-10-26", "12:10", "13:10");
  assert.equal(s.day, "closed");
  assert.match(s.flags[0], /^2026-10-26\(월\)은 영업하는 요일이 아님\(한국관광공사 TourAPI /u);
  s = one("/places/cafe/", "2026-10-29", "12:10", "13:10");
  assert.notEqual(s.day, "closed");
  assert.equal(s.flags.length, 0);
});

test("F01: a place TourAPI's class puts outdoors is outdoors for the rain — the one outdoor stop a day — never 'not known'", () => {
  assert.deepEqual(needAt("rain", FALLS.f, "visit"), { state: "no", text: "야외(한국관광공사 분류: 폭포)" });
  assert.equal(isOutdoor(FALLS.f), true);
  assert.equal(needAt("rain", MUSEUM.f, "visit").state, "ok");
  assert.equal(isOutdoor(MUSEUM.f), false);
});

test("F04: a café, one 권역 or indoor places only, said of a plan whose stops do not hold it", () => {
  const stop = (page, name, role) => ({ page, name, role, start: "10:00", end: "11:00" });
  const plan = { days: [{ stops: [stop("/places/museum/", "소수박물관", "visit"), stop("/places/falls/", "희방폭포", "visit")] }] };
  assert.equal(planClaim("부석사와 소수서원을 보고 점심과 카페를 거쳐 돌아갑니다.", plan, kb).said, "카페");
  assert.equal(planClaim("카페는 영업 정보가 없어 넣지 않았어요.", plan, kb), null);
  assert.match(planClaim("하루를 한 권역에서 보냅니다.", plan, kb).why, /소수서원·순흥·풍기·소백산 권역에 걸치는데|풍기·소백산·소수서원·순흥 권역에 걸치는데/u);
  assert.match(planClaim("비가 와도 실내 장소만 둘러봅니다.", plan, kb).why, /희방폭포/u);
  // a plan that holds it: nothing said
  const indoor = { days: [{ stops: [stop("/places/museum/", "소수박물관", "visit"), stop("/places/cafe/", "카페, 선비꽃", "cafe")] }] };
  assert.equal(planClaim("한 권역에서 실내 장소만 보고 카페에 들릅니다.", indoor, kb), null);
});

// ------------------------------------------------------------------ the real knowledge (exported by pytest)
const REAL = process.env.CHAT_KB_DIR;

test("real knowledge: every place TourAPI's class puts outdoors reads outdoors; every value by day group gives a weekend day its own closing; every 'only' day closes the rest",
  { skip: !REAL && "CHAT_KB_DIR not set" }, async () => {
    const k = await loadKnowledge(REAL);
    const docs = Object.entries(k.docs).filter(([, d]) => d.k === "place");
    for (const [key, d] of docs.filter(([, x]) => x.f && x.f.od)) {
      assert.equal(needAt("rain", d.f, "visit").state, "no", key);
      assert.equal(isOutdoor(d.f), true, key);
    }
    // (a range that runs past midnight — '주말 09:00~03:00' — has no closing on that day to pass)
    const close = (seg) => {
      const m = /(\d{1,2}):(\d{2})\s*[~–-]\s*(\d{1,2}):(\d{2})/u.exec(seg);
      return m && +m[3] * 60 + +m[4] > +m[1] * 60 + +m[2] ? +m[3] * 60 + +m[4] : null;
    };
    let n = 0;
    for (const [key, d] of docs) {
      for (const h of (d.f || {}).h || []) {
        if (roomParts(h.t) || /\d{1,2}\s*월|하절기|동절기|여름|겨울|성수기|비수기/u.test(h.t)) continue;
        const sun = dayPart(h.t, 0), wed = dayPart(h.t, 3);
        if (!sun || !wed || sun.why || wed.why || close(sun.seg) === null || close(wed.seg) === null || close(sun.seg) >= close(wed.seg)) continue;
        // a Sunday visit ending after the Sunday part's closing and before the weekday's: that source flags it
        const end = close(sun.seg) + 10, z = `${String(Math.floor(end / 60)).padStart(2, "0")}:${String(end % 60).padStart(2, "0")}`;
        const s = k.checkPlan({ date: "2026-11-15", stops: [{ page: key, start: "", end: z }], move: "car" }).stops[0];
        if (s.day === "closed") continue;
        assert.ok(s.flags.some((x) => x.startsWith(`${h.p} 기준 끝 ${z}`)), `${key} ${h.t} ${s.flags.join(" / ")}`);
        n += 1;
      }
      for (const h of ((d.f || {}).h || []).filter((x) => onlyDays(x.t))) {
        const days = onlyDays(h.t).days;
        const date = ["2026-11-15", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21"].find((_, i) => !days.has(i));
        if (!date) continue;
        assert.equal(k.checkPlan({ date, stops: [{ page: key, start: "", end: "" }], move: "car" }).stops[0].day, "closed", `${key} ${h.t}`);
      }
    }
    assert.ok(n >= 0, n);
  });
