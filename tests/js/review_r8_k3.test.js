// Review 2026-10-22 (fees): a free weekday one source dates and the other does not, and a 65+ party's way to pay.
// - 금강미래체험관: TourAPI '매주 수요일 문화가 있는 날 무료 관람' (no months) beside the facility's notice '2026년 4~12월
//   매주 수요일 무료 관람' (an added value, a:1 in docs.json f.fee.alt). A Wednesday in those months is free by both; a
//   Wednesday outside them (another year too) is neither 0원 nor the table's price for sure: both sources and 방문 전
//   전화 확인 (CLAUDE.md 3.2), the total open — never the 금강권 통합권 picked only because it looks certain.
// - Two 65+ visitors at 근대역사박물관: its own table has no 65+ rule, the 박물관 통합권's source makes them free; the way to
//   pay is chosen for them, not for an adult who is not there, and a mixed party is told the other way in the conditions.
// With CHAT_KB_DIR (tests/test_chat_node.py: the knowledge exported from the real data) the same on the real export.
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge, loadKnowledge } from "./first_city.js";
import { tokens } from "../../chatbot/knowledge.js";
import { planFees } from "../../chatbot/plan_fees.js";

const SITE = "https://gunsan.webforai.kr";
const TOUR = "한국관광공사 TourAPI";
const NOTICE = "금강미래체험관 홈페이지 공지";
const GEUMGANG_FEE = { tab: { 성인: 2000, "청소년·군인": 1000, 어린이: 500 }, tl: "타지역", t: "[타지역] - 성인 2,000원", p: TOUR,
  fr: [{ w: "6세 이하 유아", max: 6 }, { w: "65세 이상 경로대상자", min: 65 }, { w: "매주 수요일 문화가 있는 날 무료 관람", wd: 3 }],
  alt: [{ p: NOTICE, t: "2026년 4~12월 매주 수요일 무료 관람(문화가 있는 날)", a: 1 }] };
const MUSEUM_FREE = "군산근대역사박물관 홈페이지 관람안내 페이지의 관람료 면제대상 https://museum.gunsan.go.kr/new/contents/userInfo101.jsp (출처 확인 2026-10-17)";
const DOCS = {
  "/places/금강미래체험관/": { t: "금강미래체험관", k: "place", x: "금강미래체험관", f: { kd: "attraction", fee: GEUMGANG_FEE } },
  "/places/근대역사박물관/": { t: "근대역사박물관", k: "place", x: "근대역사박물관",
    f: { kd: "attraction", fee: { tab: { 성인: 2000, "청소년·군인": 1000, 어린이: 500 }, tl: "개별권", t: "[개별권] - 성인 2,000원", p: TOUR } } },
  "/places/구-일본-제18은행-군산지점/": { t: "구 일본 제18은행 군산지점", k: "place", x: "구 일본 제18은행 군산지점",
    f: { kd: "attraction", fee: { tab: { 성인: 500, "청소년·군인": 300, 어린이: 200 }, t: "성인 500원", p: "군산시 문화관광" } } },
};
const TICKETS = [
  { id: "museum-combined", name: "박물관 통합권", src: "군산시 문화관광 표",
    places: [{ path: "/places/근대역사박물관/", name: "근대역사박물관" }, { path: "/places/구-일본-제18은행-군산지점/", name: "구 일본 제18은행 군산지점" }],
    prices: { 개인: { 성인: [3000, 2000], "청소년·군인": [2000, 1000], 어린이: [1000, 500] } },
    rules: [{ kind: "free", who: "6세 이하 유아", age_max: 6, src: MUSEUM_FREE }, { kind: "free", who: "65세 이상 경로대상자", age_min: 65, src: MUSEUM_FREE }] },
  { id: "geumgang-combined", name: "금강권 통합권", src: "군산시 문화관광 표",
    places: [{ path: "/places/근대역사박물관/", name: "근대역사박물관" }, { path: "/places/금강미래체험관/", name: "금강미래체험관" }],
    prices: { 개인: { 성인: [5000, 3000], "청소년·군인": [4000, 2000], 어린이: [3000, 1000] } }, rules: [] },
];
const kb = () => new Knowledge({ catalog: "# catalog", docs: { v: 1, site: SITE, docs: DOCS, alias: {}, ext: [], tickets: TICKETS },
  index: { v: 1, docs: Object.fromEntries(Object.entries(DOCS).map(([k, d]) => [k, [tokens(`${d.t} ${k}`).join(" "), tokens(d.x).join(" ")]])) } });
const visit = (date, paths, party, k, limit = 10000) =>
  planFees([{ date, stops: paths.map((p) => ({ page: p, name: k.docs[p].t, role: "visit" })) }], party, k, limit);
const G = "/places/금강미래체험관/", M = "/places/근대역사박물관/", B = "/places/구-일본-제18은행-군산지점/";

test("a Wednesday in the notice's months is free by both sources, with both named", () => {
  const f = visit("2026-10-28", [G], { adults: 2, kids: [] }, kb(), 0);
  assert.equal(f.total, 0);
  assert.equal(f.verdict, "within");
  assert.match(f.days[0].lines[0].basis, new RegExp(`${TOUR} '매주 수요일 .*' / ${NOTICE} '2026년 4~12월 .*' — 두 출처 모두 이날 무료`));
  // an added value does not contradict the fee: no '다른 출처의 요금 값' condition for it
  assert.ok(!f.conds.some((x) => /다른 출처의 요금 값/.test(x)), f.conds.join("\n"));
});

test("a Wednesday outside the notice's months, or in another year, is open: both sources and 방문 전 전화 확인", () => {
  for (const date of ["2027-01-06", "2027-04-07", "2026-03-04"]) {
    const f = visit(date, [G], { adults: 2, kids: [] }, kb(), 5000);
    assert.equal(f.total, null, date);
    assert.equal(f.verdict, "open", date);
    // its own fee, not the 금강권 통합권 (5,000원 × 2 certain): at most 4,000원
    assert.equal(f.days[0].per[0].how, "own", date);
    const [line] = f.days[0].lines;
    assert.equal(line.status, "unknown");
    assert.match(line.basis, new RegExp(`무료 관람일인지 출처마다 다름: ${TOUR} '매주 수요일 .*' / ${NOTICE} '2026년 4~12월 .*' — `
      + "무료가 아니면 요금표 '성인' \\(타지역\\) 2,000원, 방문 전 전화 확인"));
    assert.ok(!/\(\d+월\)/.test(line.basis), "no month as if the period were matched");
  }
  // the age rules still apply that day: the 65+ and the 5-year-old free, the adult open
  const f = visit("2027-01-06", [G], { adults: 2, seniors: 1, kids: [5] }, kb(), 10000);
  const by = Object.fromEntries(f.days[0].lines.map((l) => [l.who, l]));
  assert.equal(by["65세 이상 어른"].status, "free");
  assert.equal(by["아이 5살"].status, "free");
  assert.equal(by["어른"].status, "unknown");
  assert.equal(f.total, null);
  // a Tuesday is the table's price as before
  assert.equal(visit("2027-01-05", [G], { adults: 2, kids: [] }, kb()).total, 4000);
});

test("the weekday rule with no dated notice beside it: free that weekday, no month in the basis", () => {
  const k = kb();
  const plain = structuredClone(k.docs[G]);
  delete plain.f.fee.alt;
  const k2 = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: SITE, docs: { ...DOCS, [G]: plain }, alias: {}, ext: [], tickets: TICKETS },
    index: { v: 1, docs: {} } });
  const f = visit("2027-01-06", [G], { adults: 2, kids: [] }, k2, 0);
  assert.equal(f.total, 0);
  assert.equal(f.days[0].lines[0].basis, "매주 수요일 문화가 있는 날 무료 관람");
});

test("a 65+ party is priced as itself: the 박물관 통합권 its source makes free", () => {
  for (const paths of [[M], [M, B]]) {
    const f = visit("2026-10-27", paths, { adults: 2, seniors: 2, kids: [] }, kb());
    assert.equal(f.total, 0, paths.join());
    assert.equal(f.verdict, "within");
    assert.ok(f.days[0].per.every((p) => p.how === "museum-combined"), JSON.stringify(f.days[0].per));
    assert.match(f.days[0].lines[0].basis, /무료 '65세 이상 경로대상자'/);
  }
  // a child alone is still priced as one adult would be (the comment's case: no ticket picked only for its ages)
  const kid = visit("2026-10-27", [M], { adults: 0, seniors: 0, kids: [9] }, kb());
  assert.equal(kid.days[0].per[0].how, "own");
});

test("a mixed party keeps the adult's cheaper way and is told the way that leaves no one 확인 필요", () => {
  const f = visit("2026-10-27", [M], { adults: 2, seniors: 1, kids: [] }, kb());
  assert.equal(f.days[0].per[0].how, "own");                  // 2,000원 for the adult, the 65+ 확인 필요
  assert.equal(f.total, null);
  assert.equal(f.known, 2000);
  const other = f.conds[0];
  assert.match(other, /^박물관 통합권으로 사면 65세 이상 어른 1명 0원\(무료 '65세 이상 경로대상자' \(군산근대역사박물관 홈페이지 .*\(출처 확인 2026-10-17\)\)\) — 합계 3,000원$/);
  assert.ok(!/https?:/.test(other), "the source named without its address");
  // the conditions only name it: the 통합권's exemption is never applied to the museum's own admission
  assert.equal(f.days[0].lines.find((l) => l.who === "65세 이상 어른").status, "unknown");
  // no such line when the chosen way leaves nobody unknown, nor for a way that costs more than the most it can be
  assert.ok(!visit("2026-10-27", [M], { adults: 2, kids: [] }, kb()).conds.some((x) => /으로 사면/.test(x)));
  assert.ok(!visit("2027-01-06", [G], { adults: 2, kids: [] }, kb()).conds.some((x) => /으로 사면/.test(x)));
});

test("a 65+ adult free either way with a child: the adult's cheaper way stays, the 통합권 only named", () => {
  // the 금강권 통합권 as the real one: 65+ free, children by age — the 65+ adult is free both ways at 금강미래체험관, and
  // only the child's ages (no ages in the place's own table) would pick the 통합권 at 3,000원 as certain
  const T = structuredClone(TICKETS);
  T[1].rules = [{ kind: "free", who: "65세 이상 어른", age_min: 65, src: "군산시 문화관광 표" },
    { kind: "age", category: "어린이", text: "어린이(7~12세)", from: 7, to: 12, src: "군산시 문화관광 표" }];
  const k = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: SITE, docs: DOCS, alias: {}, ext: [], tickets: T },
    index: { v: 1, docs: {} } });
  for (const date of ["2026-10-27", "2027-01-06"]) {
    const f = visit(date, [G], { adults: 1, seniors: 1, kids: [9] }, k, 1000);
    assert.equal(f.days[0].per[0].how, "own", date);
    assert.equal(f.total, null, date);
    assert.equal(f.verdict, "open", date);   // never 'over' a 1,000원 budget by a ticket nobody needs to buy
    assert.match(f.conds[0], /^금강권 통합권으로 사면 아이 9살 1명 3,000원\(요금표 '어린이\(7~12세\)' \(군산시 문화관광 표\)\) — 합계 3,000원$/, date);
  }
  // where the ways differ for the 65+ adult, they decide: the 박물관 통합권 makes them free at the museum
  assert.equal(visit("2026-10-27", [M], { adults: 1, seniors: 1, kids: [9] }, k).days[0].per[0].how, "museum-combined");
});

test("a notice's months written '4월~12월' are read as '4~12월'", () => {
  const docs = structuredClone(DOCS);
  docs[G].f.fee.alt[0].t = "2026년 4월~12월 매주 수요일 무료 관람";
  const k = new Knowledge({ catalog: "# catalog", docs: { v: 1, site: SITE, docs, alias: {}, ext: [], tickets: TICKETS },
    index: { v: 1, docs: {} } });
  assert.equal(visit("2027-01-06", [G], { adults: 2, kids: [] }, k).total, null);
  assert.equal(visit("2026-10-28", [G], { adults: 2, kids: [] }, k).total, 0);
});

// (the first city's real knowledge, when a directory of it is given: FIRST_CITY_KB_DIR — this city's own is CHAT_KB_DIR)
const REAL = process.env.FIRST_CITY_KB_DIR;
test("real knowledge: 금강미래체험관's notice reaches the planner, and a 2027 Wednesday stays open", { skip: !REAL && "FIRST_CITY_KB_DIR not set" }, async () => {
  const k = await loadKnowledge(REAL);
  const fee = k.docs[G].f.fee;
  assert.ok((fee.alt || []).some((a) => a.a === 1 && /2026년 4~12월 매주 수요일/.test(a.t)), JSON.stringify(fee));
  assert.ok(fee.fr.some((r) => r.wd === 3));
  assert.equal(visit("2026-10-28", [G], { adults: 2, kids: [] }, k, 0).total, 0);
  const f = visit("2027-01-06", [G], { adults: 2, kids: [] }, k, 5000);
  assert.equal(f.total, null);
  assert.equal(f.verdict, "open");
  assert.match(f.open.join("\n"), /출처마다 다름: .*2026년 4~12월.*방문 전 전화 확인/);
  // the 65+ party on the real tickets
  assert.equal(visit("2026-10-27", [M, B], { adults: 2, seniors: 2, kids: [] }, k).total, 0);
  // a 65+ adult with a 9-year-old, free either way at 금강미래체험관: not the 금강권 통합권 only for the child's ages
  const mixed = visit("2026-10-27", [G], { adults: 1, seniors: 1, kids: [9] }, k, 1000);
  assert.equal(mixed.days[0].per[0].how, "own");
  assert.notEqual(mixed.verdict, "over");
});
