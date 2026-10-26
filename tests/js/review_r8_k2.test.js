// node --test tests/js/ — review 2026-10-21, cluster K2 (the assistant's tools, chatbot/knowledge.js · server.js ·
// prompt.js): fee_total checks each item's price against its place's page (T-chat-fee-tool-unit-price), check_plan
// says when the date's year has no 설·추석·대체공휴일 table (S9), never closes with an all-clear above its own
// '확인 필요' lines (S12), and asks to check a time at a place whose hours it could not read for that date (S13).
import assert from "node:assert/strict";
import { test } from "node:test";

import { Knowledge } from "./first_city.js";
import { amountsIn } from "../../chatbot/knowledge.js";
import { dayInfo } from "../../chatbot/plan_geo.js";
import { TOOLS, rules } from "../../chatbot/prompt.js";
import { FIRST_META } from "./first_city.js";
import { validFees, validInput } from "../../chatbot/server.js";

const SITE = "https://gunsan.webforai.kr";
const TOUR = "한국관광공사 TourAPI";
const place = (t, f) => ({ t, k: "place", x: `${t} — 관광지`, f });
const DOCS = {
  "/places/근대역사박물관/": place("근대역사박물관", { kd: "attraction", fee: { p: TOUR, tl: "개별권", tab: { 성인: 2000, "청소년·군인": 1000, 어린이: 500 },
    t: "[박물관 통합권] - 성인 3,000원 - 청소년·군인 2,000원 - 어린이 1,000원 [개별권] - 성인 2,000원 - 청소년·군인 1,000원 - 어린이 500원" } }),
  "/places/금강미래체험관/": place("금강미래체험관", { kd: "attraction", fee: { p: TOUR, tl: "타지역", tab: { 성인: 2000, "청소년·군인": 1000, 어린이: 500 },
    fr: [{ max: 6, w: "6세 이하 유아" }],
    t: "[군산시민] - 성인 1,000원 - 청소년/군인 500원 - 어린이 300원 [타지역] - 성인 2,000원 - 청소년/군인 1,000원 - 어린이 500원 ※ 무료 : 6세 이하 유아" } }),
  "/places/경암동-철길마을/": place("경암동 철길마을", { kd: "attraction", fee: { p: TOUR, free: true, t: "무료" } }),
  "/places/유람선/": place("유람선", { kd: "attraction", fee: { p: TOUR, tab: { 성인: 22000, 소인: 11000 },
    t: "현장 - 일반 22,000원 - 소인 11,000원 온라인 - 일반 20,000원 - 소인 9,000원" } }),
  "/places/기념관/": place("기념관", { kd: "attraction", fee: { p: TOUR, tl: "개인", tab: { 성인: 500, 어린이: 200, "청소년·군인": 300 },
    t: "[개인]- 성인 500원- 청소년, 군인 300원- 어린이 200원[단체]- 성인 300원- 청소년, 군인 200원- 어린이 100원" } }),
  "/places/연도/": place("연도", { kd: "attraction", fee: { p: TOUR, t: "[배편요금]- 입도 13,050원 / 출도 12,000원 (성인기준)" } }),
  "/places/진포해양공원/": place("진포해양공원", { kd: "attraction", fee: { p: "군산시 문화관광",
    t: "개인 단체(20인 이상) 성인 (군산시민) 1,000 (500) 700 (300) 어린이 (군산시민) 300 (200) 200 (100)",
    alt: [{ p: TOUR, t: "[개인]- 성인 3,000원(500원)- 어린이 1,000원(200원)[단체]- 성인 2,000원(300원)- 어린이 500원(100원)" }] } }),
  "/places/요금없음/": place("요금없음", { kd: "attraction" }),
  // a fee only the page's text writes (선유 스카이썬라인: no f.fee, its prices in a section and the FAQ)
  "/places/짚라인/": { t: "짚라인", k: "place", f: { kd: "attraction" }, x: "짚라인 — 체험\n"
    + "요금: 1인 1회 만 13세 이상 20,000원, 만 7세~만 12세 어린이 16,000원입니다. 거주자는 성인 16,000~18,000원을 냅니다.\n"
    + "- 주차요금: 60분 무료, 60~90분 1,000원, 1일 1만원 — 한국관광공사 TourAPI (출처 확인 2026-10-08)\n- 전화: 063-468-8602" },
  // check_plan: closed days and hours as the sources write them
  "/places/테디베어박물관/": place("테디베어박물관", { kd: "attraction", g: [35.99, 126.71], c: [{ p: "한국관광공사", t: "연중무휴" }],
    h: [{ p: TOUR, t: "10:00~19:00 (입장 마감 18:00)" }] }),
  "/places/명동소바/": place("명동소바", { kd: "food", g: [35.988, 126.712], c: [{ p: "군산시", t: "동절기(일요일 휴무)" }],
    h: [{ p: "군산시 문화관광", t: "11:00~20:00 / 동절기(일요일 휴무)" }] }),
  "/places/아서원/": place("아서원", { kd: "food", g: [35.987, 126.713], c: [{ p: "한국관광공사", t: "매주 목요일" }],
    h: [{ p: TOUR, t: "10:30~재료 소진 시※ 자세한 영업시간은 방문 전 전화 문의 요망" }] }),
  "/places/공원/": place("공원", { kd: "attraction", g: [35.98, 126.72], c: [{ p: "한국관광공사", t: "연중무휴" }], h: [{ p: TOUR, t: "상시 개방" }] }),
  "/places/예약집/": place("예약집", { kd: "food", g: [35.981, 126.721], c: [{ p: "군산시", t: "연중무휴" }], h: [{ p: "군산시", t: "예약제" }] }),
  "/places/두출처집/": place("두출처집", { kd: "food", g: [35.982, 126.722], c: [{ p: "군산시", t: "연중무휴" }],
    h: [{ p: "군산시", t: "재료 소진 시 마감" }, { p: TOUR, t: "11:00~15:00" }] }),
  "/places/호텔/": { t: "호텔", k: "place", x: "호텔 — 숙박", f: { kd: "stay", g: [35.983, 126.723], h: [{ p: TOUR, t: "입실 15:00 / 퇴실 11:00" }] } },
};
const TICKETS = [{ id: "geumgang-combined", name: "금강권 통합권", src: "기념관 표",
  places: [{ name: "근대역사박물관", path: "/places/근대역사박물관/" }, { name: "기념관", path: "/places/기념관/" }],
  prices: { 개인: { 성인: [5000, 3000], 어린이: [3000, 1000] } }, rules: [{ kind: "free", who: "6세 이하 유아", age_max: 6, src: "기념관 표" }] }];
const kb = () => new Knowledge({ catalog: "", docs: { v: 1, site: SITE, docs: DOCS, alias: { "/en/places/modern-history-museum/": "/places/근대역사박물관/" },
  ext: [], tickets: TICKETS }, index: { v: 1, docs: {} } });
const fee = (k, items, opts = {}) => k.feeTotal(validFees({ ...opts, items }));

test("fee_total items with a page: the review's three prices are 확인 필요 and out of the total, the page's own pass", () => {
  const k = kb();
  // the challenge's repro: a made-up price, the 군산시민 price for a visitor, a price at a free place
  let r = fee(k, [{ label: "근대역사박물관 성인", won: 1234, count: 2, page: "/places/근대역사박물관/" },
    { label: "금강미래체험관 성인", won: 1000, count: 2, page: "/places/금강미래체험관/" },
    { label: "경암동 철길마을 입장료", won: 7000, count: 2, page: "/places/경암동-철길마을/" }]);
  assert.equal(r.total, null);
  assert.equal(r.known, 0);
  assert.match(r.text, /^- 근대역사박물관 성인: 1,234원 × 2 — 페이지 값 2,000원과 다름 — 확인 필요 \(근대역사박물관 요금표 '성인' \(개별권\) — 한국관광공사 TourAPI\)$/mu);
  assert.match(r.text, /^- 금강미래체험관 성인: 1,000원 × 2 — 페이지 값 2,000원과 다름 — 확인 필요/mu);
  assert.match(r.text, /^- 경암동 철길마을 입장료: 7,000원 × 2 — 페이지 값 0원과 다름 — 확인 필요 \(경암동 철길마을 '무료'/mu);
  assert.match(r.text, /확인된 값만의 합계\(식\): 0원\. 확인 필요: 근대역사박물관 성인, 금강미래체험관 성인, 경암동 철길마을 입장료 — 총액을 확정하지 않는다/u);
  assert.doesNotMatch(r.text, /페이지의 값/u);
  // the page's own prices: one total, each line '(페이지의 값: …)' with its basis
  r = fee(k, [{ label: "근대역사박물관 성인", won: 2000, count: 2, page: "/places/근대역사박물관/" },
    { label: "금강미래체험관 어린이", won: 500, count: 1, page: "/places/금강미래체험관/" },
    { label: "경암동 철길마을", won: 0, count: 3, page: "/places/경암동-철길마을/" },
    { label: "연도 배편 입도", won: 13050, count: 2, page: "/places/연도/" }]);
  assert.equal(r.total, 4000 + 500 + 0 + 26100);
  assert.match(r.text, /- 근대역사박물관 성인: 2,000원 × 2 = 4,000원 \(페이지의 값: 근대역사박물관 요금표 '성인' \(개별권\) — 한국관광공사 TourAPI\)/u);
  assert.match(r.text, /- 연도 배편 입도: 13,050원 × 2 = 26,100원 \(페이지의 값: 연도 요금 값에 있는 금액, 어느 구분의 값인지는 대조 안 함/u);
  assert.match(r.text, /합계\(식\): 4,000 \+ 500 \+ 0 \+ 26,100 = 30,600원\. 답의 첫 문장·표·끝 어디서나 이 합계 30,600원 하나만 쓴다/u);
  // an English path finds the same page
  assert.equal(fee(k, [{ label: "Museum adult", won: 2000, count: 1, page: "/en/places/modern-history-museum/" }]).total, 2000);
});

test("fee_total items: which prices the page gives — sections, residents, groups, tickets, free entry, two sources", () => {
  const k = kb();
  const one = (it, opts) => fee(k, [{ count: 1, ...it }], opts);
  // another price of the same category in a visitor's part of the value ('온라인 - 일반 20,000원')
  assert.match(one({ label: "유람선 온라인 성인", won: 20000, page: "/places/유람선/" }).text, /페이지의 값: 유람선 요금 값의 '일반 20,000원'/u);
  // the group's price for a visitor; with group, or the label saying 단체, it is looked for in the value
  assert.match(one({ label: "기념관 성인", won: 300, page: "/places/기념관/" }).text, /페이지 값 500원과 다름 — 확인 필요/u);
  assert.equal(one({ label: "기념관 성인", won: 300, page: "/places/기념관/" }, { group: true }).total, 300);
  assert.equal(one({ label: "기념관 단체 성인", won: 300, page: "/places/기념관/" }).total, 300);
  // a combined ticket's price under the place's name is not the place's 성인 price; named as the ticket, it is the table's
  assert.match(one({ label: "근대역사박물관 성인", won: 3000, page: "/places/근대역사박물관/" }).text, /페이지 값 2,000원과 다름/u);
  assert.match(one({ label: "기념관 금강권 통합권 성인", won: 5000, page: "/places/기념관/" }).text, /페이지의 값: '금강권 통합권' 요금표에 있는 금액/u);
  // a resident: the visitor's table says nothing of it, the value's amounts do
  assert.equal(one({ label: "금강미래체험관 성인", won: 1000, page: "/places/금강미래체험관/" }, { resident: true }).total, 1000);
  assert.equal(one({ label: "금강미래체험관 성인(군산시민)", won: 1000, page: "/places/금강미래체험관/" }).total, 1000);
  // free entry is never read as the 성인 price ('65세 이상 어른'); a 0 the value or a ticket's rule gives passes
  assert.equal(one({ label: "금강미래체험관 6세 이하 유아", won: 0, page: "/places/금강미래체험관/" }).total, 0);
  assert.equal(one({ label: "근대역사박물관 유아", won: 0, page: "/places/근대역사박물관/" }).total, 0);
  // an amount the page does not write; a page with no fee; not a place of the site
  assert.match(one({ label: "연도 배편", won: 15000, page: "/places/연도/" }).text, /15,000원 × 1 — 대조 안 됨 — 확인 필요 \(연도 요금 값에 15,000원이 없음: '\[배편요금\]/u);
  assert.match(one({ label: "요금없음", won: 1000, page: "/places/요금없음/" }).text, /대조 안 됨 — 확인 필요 \(요금없음 페이지에 요금 정보 없음\)/u);
  // no fee value, but the page's text writes the price: never '페이지에 요금 정보 없음' for it (review of K2: the zipline's
  // 20,000원 went 확인 필요 as a page with no fee); an amount the text does not write stays 확인 필요
  for (const won of [20000, 16000, 18000, 1000, 10000]) {
    const r = one({ label: "짚라인 성인", won, page: "/places/짚라인/" });
    assert.equal(r.total, won, String(won));
    assert.match(r.text, /\(페이지의 값: 짚라인 페이지에 쓰인 금액, 어느 항목·구분의 값인지는 대조 안 함\)/u);
  }
  for (const won of [25000, 13, 468, 8602, 2026, 0]) {
    const r = one({ label: "짚라인 성인", won, page: "/places/짚라인/" });
    assert.equal(r.total, null, String(won));
    assert.match(r.text, new RegExp(`대조 안 됨 — 확인 필요 \\(짚라인 페이지에 ${won.toLocaleString("en-US")}원이 없음\\(요금 값 없음\\)\\)`, "u"));
  }
  assert.match(one({ label: "x", won: 1000, page: "/places/없는곳/" }).text, /대조 안 됨 — 확인 필요 \('\/places\/없는곳\/'은 이 사이트의 장소 페이지가 아님\)/u);
  // two sources that differ (CLAUDE.md 3절 2항): both, 방문 전 전화 확인, out of the total — whichever source's price it is
  for (const won of [1000, 3000]) {
    const r = one({ label: "진포해양공원 성인", won, page: "/places/진포해양공원/" });
    assert.equal(r.total, null);
    assert.match(r.text, /출처마다 요금이 다름 — 확인 필요 \(군산시 문화관광 '개인 단체.*' \/ 한국관광공사 TourAPI '\[개인\].*' — 방문 전 전화 확인\)/u);
  }
  // the known part of a total with an open item is '값만의' (an open person of a ticket stays '사람만의': chat.test.js)
  assert.match(fee(k, [{ label: "연도 배편", won: 15000, count: 1, page: "/places/연도/" }]).text, /확인된 값만의 합계/u);
});

test("fee_total items without a page: calculated as before, said to be unchecked", () => {
  const r = fee(kb(), [{ label: "근대역사박물관 성인", won: 1234, count: 2 }, { label: "어린이", won: 7000, count: 1 }]);
  assert.equal(r.total, 9468);
  assert.match(r.text, /- 근대역사박물관 성인: 1,234원 × 2 = 2,468원 \(대조 안 됨\)/u);
  assert.doesNotMatch(r.text, /페이지의 값/u);
});

test("fee_total input: a page must be a place's path; the schema and the rules say what the tool does with it", () => {
  const ok = { label: "근대역사박물관 성인", won: 2000, count: 1 };
  assert.deepEqual(validFees({ items: [{ ...ok, page: " /places/근대역사박물관/ " }] }).items, [{ ...ok, page: "/places/근대역사박물관/" }]);
  assert.deepEqual(validFees({ items: [ok] }).items, [ok]);
  assert.ok(validFees({ items: [{ ...ok, page: "/zh-hans/places/modern-history-museum/" }] }));
  for (const page of ["근대역사박물관", "/guides/x/", "/places/", "https://gunsan.webforai.kr/places/x/", "/places/a b/", "", 3, "/places/x/?q=1"]) {
    assert.equal(validFees({ items: [{ ...ok, page }] }), null, String(page));
  }
  assert.equal(validInput("fee_total", { items: [{ ...ok, page: "/guides/x/" }] }), null);
  const tool = TOOLS.find((t) => t.name === "fee_total");
  const item = tool.input_schema.properties.items.items;
  assert.equal(item.properties.page.type, "string");
  assert.deepEqual(item.required, ["label", "won", "count"]);
  assert.equal(item.additionalProperties, false);
  assert.match(tool.description, /checks each price against that page's fee value/u);
  assert.match(rules(FIRST_META), /when it marks a person or a price 확인 필요/u);
  // the amounts a value writes: not counts, ages, rooms or times
  assert.deepEqual([...amountsIn("4인실 45,000원 / 1만원 / 20인 이상 700 (300) 09:00~18:00 6세 무료")].sort((a, b) => a - b), [0, 300, 700, 10000, 45000]);
  assert.deepEqual([...amountsIn("1박 198,000원~350,000원")].sort((a, b) => a - b), [198000, 350000]);
});

test("check_plan in a year with no 설·추석·대체공휴일 table: one date line, the field the planner page reads, no per-stop check", () => {
  const k = kb();
  const stops = [{ page: "/places/테디베어박물관/", start: "10:00", end: "11:00" }];
  let r = k.checkPlan({ date: "2028-01-26", stops });
  assert.equal(r.noHolidayTable, true);
  assert.match(r.text, /^날짜: 2028-01-26 \(수요일\)\n그해 설·추석·대체공휴일 날짜는 사이트 표에 없음 — 공휴일이면 운영 확인\n/u);
  assert.deepEqual(r.stops[0].checks, []);   // the planner's day state stays as it was (plan_geo.dayInfo)
  assert.equal(dayInfo(k, "2028-01-26", "/places/테디베어박물관/").state, "open");
  assert.match(r.text.split("\n").at(-1), /^고칠 것 없음\. 그해 공휴일 표가 없어 그날이 공휴일인지 알 수 없다 — 답에 ‘공휴일이면 운영 확인’을 적는다\. 이동 구간은/u);
  assert.doesNotMatch(r.text, /걸리는 것 없음/u);
  // a year the table has, and no date: neither
  for (const date of ["2027-01-26", ""]) {
    r = k.checkPlan({ date, stops });
    assert.equal(r.noHolidayTable, undefined);
    assert.doesNotMatch(r.text, /사이트 표에 없음/u);
  }
});

test("check_plan's last line: 고칠 것 없음 with the 확인 필요 count when stops carry checks; the all-clear only when nothing is left", () => {
  const k = kb();
  // 성탄절: every stop '확인 필요: 그날은 공휴일(성탄절)…'
  let r = k.checkPlan({ date: "2026-12-25", stops: [{ page: "/places/테디베어박물관/", start: "10:00", end: "11:00" },
    { page: "/places/공원/", start: "11:20", end: "12:00" }] });
  assert.equal(r.flags.length, 0);
  assert.equal(r.stops.reduce((a, s) => a + s.checks.length, 0), 2);
  assert.equal(r.text.split("\n").at(-1), "고칠 것 없음. ‘확인 필요’ 2건은 답의 표에 ‘확인 필요’로 남긴다. 이동 구간은 여전히 '이동 확인 필요'다(사이트에 소요 시간이 없음).");
  r = k.checkPlan({ date: "2026-12-24", stops: [{ page: "/places/테디베어박물관/", start: "10:00", end: "11:00" }] });
  assert.equal(r.text.split("\n").at(-1), "이 사이트 자료로 걸리는 것 없음. 이동 구간은 여전히 '이동 확인 필요'다(사이트에 소요 시간이 없음).");
  // flags first, as before
  r = k.checkPlan({ date: "2026-12-24", stops: [{ page: "/places/테디베어박물관/", start: "08:00", end: "09:00" }] });
  assert.match(r.text.split("\n").slice(-3).join("\n"), /^고칠 것 1건:/u);
});

test("check_plan: a stop whose hours it could not read for that date gets a time check, its day state unchanged", () => {
  const k = kb();
  const one = (page, start = "20:30", end = "21:30", date = "2026-11-07") => k.checkPlan({ date, stops: [{ page, start, end }] });
  for (const [page, value] of [["/places/명동소바/", "11:00~20:00 / 동절기(일요일 휴무)"], ["/places/아서원/", "10:30~재료 소진 시※ 자세한 영업시간은 방문 전 전화 문의 요망"]]) {
    const r = one(page);
    assert.equal(r.stops[0].day, "open");
    assert.deepEqual(r.flags, []);
    assert.ok(r.stops[0].checks.includes(`이용시간 — ${DOCS[page].f.h[0].p}: '${value}' — 그날 시각을 하나로 읽지 못해 계획한 시각에 여는지 확인 필요`), page);
    assert.equal(dayInfo(k, "2026-11-07", page).state, "open");   // '이용시간 — ' checks leave the planner's day as it was
    assert.equal(dayInfo(k, "2026-11-07", page).read, false);     // and the code still never picks it
  }
  // always open; a 예약 value (its own check, once); another source's hours read; a stay — none
  assert.deepEqual(one("/places/공원/").stops[0].checks, []);
  assert.deepEqual(one("/places/예약집/").stops[0].checks, ["군산시 이용시간 '예약제' — 그 시각에 여는지 방문 전 확인 필요"]);
  assert.deepEqual(one("/places/두출처집/", "12:00", "13:00").stops[0].checks, ["군산시 이용시간 '재료 소진 시 마감' — 다른 출처의 시각과 달라 방문 전 전화 확인"]);
  assert.deepEqual(one("/places/호텔/").stops[0].checks, []);
});
