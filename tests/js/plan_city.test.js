// The course planner on a city of its own (the engine came from the first city: tests/js/plan*.test.js keep its cases
// with its meta, tests/js/first_city.js). Here the made-up city of chat.test.js ('한빛', ASCII slugs as the engine
// writes them) proves that every city value the planner uses comes from docs.json meta (chatbot/city.js): the hubs and
// their travel areas, the likes, the region's name in titles, the site's name in the rules, the combined tickets'
// names; and this city's own rule for a trip without a car (site.json plan.transit_strict — the outside review
// 2026-10-24 C05·C08): a leg is confirmed only as a walk or a bus route both places' stops share, a longer one is the
// reader's to check (the plan a candidate, never '코스 완성'), one past a short ride is sent back. At the end, the real
// knowledge (CHAT_KB_DIR, tests/test_chat_node.py): this city's meta and the paid review's two courses of 2026-10-24.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { city } from "../../chatbot/city.js";
import { Knowledge, RIDE_M, WALK_M, loadKnowledge, tokens } from "../../chatbot/knowledge.js";
import { buildPlan, codeText } from "../../chatbot/plan_build.js";
import { cap, hubGuide } from "../../chatbot/plan_geo.js";
import { buildPlanSystem, conditionsText, planRules } from "../../chatbot/plan_prompt.js";
import { checksList, hubMargin, isCafe, isMeal, prefFits } from "../../chatbot/plan_state.js";
import { codePlan, hubLegs, preflight, readSubmit, validConditions, verify } from "../../chatbot/planner.js";

const SITE = "https://travel.hanbit.kr";
// docs.json meta (pipeline/chat_index.py chat_meta + pipeline/plan.py plan_meta): the city's words the planner uses
const META = { site: SITE, site_name: "한빛 여행", site_name_en: "Hanbit Travel", region: { ko: "한빛", en: "Hanbit" },
  assistant: { ko: "한빛 여행 도우미" }, origins: [], tel: [],
  plan: { hubs: { station: { name: "한빛역" }, bus: { name: "한빛버스터미널" },
    harbour: { name: "한빛항", path: "/places/port-1981/", g: [35.9885, 126.7095] } },
  prefs: { history: "역사·문화(박물관·문화유산·근대 건물)", food: "맛집", nature: "자연·힐링(공원·산·호수)", night: "야경" }, resident: "" } };
const NOW = new Date("2026-10-17T01:00:00Z");   // 2026-10-17 (Sat) 10:00 KST

const MUSEUM_FEE = { tab: { 성인: 2000, "청소년·군인": 1000, 어린이: 500 }, tl: "개별권", t: "[개별권] - 성인 2,000원", p: "한국관광공사 TourAPI" };
const DOCS = {
  "/places/history-museum/": { t: "한빛역사박물관", k: "place", x: "한빛역사박물관 — 관광지 · 박물관·전시. 2011년 9월 문을 열었다. 문의 053-000-0000",
    f: { kd: "attraction", ty: "박물관·전시", g: [35.99082, 126.712123], b: ["01", "08"], c: [{ p: "공식 홈페이지", t: "매주 월요일, 1월 1일" }],
      h: [{ p: "박물관 홈페이지", t: "3월~10월 09:00~18:00(입장마감 17:30) / 11월~2월 09:00~17:00(입장마감 16:30)" }], fee: MUSEUM_FEE,
      ac: [{ k: "accessible_route", t: "출입구까지 경사로가 설치되어 있음(완만함)", p: "무장애" }, { k: "babycarriage", t: "대여 가능(예약 없이 박물관 안내소에서)", p: "공식" }],
      pk: "가능", ci: undefined } },
  "/places/old-bank/": { t: "옛 은행 건물", k: "place", x: "옛 은행 건물 — 관광지 · 문화유산. 근대미술관",
    f: { kd: "attraction", ty: "문화유산", g: [35.9897, 126.7128], c: [{ p: "한빛시", t: "매주 월요일" }], h: [{ p: "한빛시", t: "09:00~18:00" }],
      fee: { tab: { 성인: 500, "청소년·군인": 300, 어린이: 200 }, t: "성인 500원", p: "한빛시" } } },
  "/places/architecture-hall/": { t: "근대건축관", k: "place", x: "근대건축관 — 관광지 · 박물관·전시",
    f: { kd: "attraction", ty: "박물관·전시", g: [35.9893, 126.7136], c: [{ p: "한빛시", t: "매주 월요일" }], h: [{ p: "한빛시", t: "09:00~18:00" }],
      fee: { tab: { 성인: 500, "청소년·군인": 300, 어린이: 200 }, t: "성인 500원", p: "한빛시" } } },
  "/places/marine-park/": { t: "해양공원", k: "place", x: "해양공원 — 관광지 · 자연·야외",
    f: { kd: "attraction", ty: "자연·야외", g: [35.9885, 126.7095], c: [{ p: "한빛시", t: "매주 월요일" }], h: [{ p: "한빛시", t: "09:00~18:00" }],
      fee: { t: "개인 단체 성인 1,000 (500)", p: "한빛시" } } },
  "/places/port-1981/": { t: "항구1981", k: "place", x: "항구1981 — 관광지 · 체험",
    f: { kd: "attraction", ty: "체험", g: [35.989023, 126.71779], b: ["01", "07"], c: [{ p: "한국관광공사", t: "매주 수요일" }], h: [{ p: "한국관광공사 TourAPI", t: "09:00~20:00" }],
      fee: { free: true, t: "무료", p: "한국관광공사" } } },
  "/places/university-museum/": { t: "한빛대학교 박물관", k: "place", x: "한빛대학교 박물관 — 관광지 · 박물관·전시",
    f: { kd: "attraction", ty: "박물관·전시", g: [35.945516, 126.685134], b: ["99"], c: [{ p: "한국관광공사", t: "매주 토요일, 일요일, 공휴일" }], h: [{ p: "한국관광공사 TourAPI", t: "10:00~17:00" }] } },
  "/places/doll-museum/": { t: "인형박물관", k: "place", x: "인형박물관 — 관광지 · 박물관·전시",
    f: { kd: "attraction", ty: "박물관·전시", g: [35.98, 126.70], c: [{ p: "공식", t: "연중무휴" }], h: [{ p: "공식", t: "10:00~18:00" }],
      fee: { tab: { 성인: 12000, 청소년: 11000, 어린이: 10000 }, tl: "개인", fr: [{ w: "만 36개월 미만", max: 2 }], t: "[개인] 성인 12,000원", p: "공식" } } },
  "/places/river-future-hall/": { t: "강변미래체험관", k: "place", x: "강변미래체험관 — 관광지 · 박물관·전시",
    f: { kd: "attraction", ty: "박물관·전시", g: [36.01, 126.75], c: [{ p: "공식", t: "매주 월요일" }], h: [{ p: "공식", t: "09:00~18:00" }],
      fee: { tab: { 성인: 2000, "청소년·군인": 1000, 어린이: 500 }, tl: "타지역", t: "[타지역] 성인 2,000원",
        fr: [{ w: "6세 이하 유아", max: 6 }, { w: "65세 이상 경로대상자", min: 65 }, { w: "매주 수요일 문화가 있는 날 무료 관람", wd: 3 }],
        alt: [{ p: "한빛시", t: "2026년 4~12월 매주 수요일 무료 관람(문화가 있는 날)" }], p: "공식" } } },
  "/places/lake-park/": { t: "호수공원", k: "place", x: "호수공원 — 관광지 · 자연·야외",
    f: { kd: "attraction", ty: "자연·야외", g: [35.95, 126.70], c: [{ p: "한빛시", t: "연중무휴" }], h: [{ p: "한빛시", t: "상시 개방" }], fee: { free: true, t: "무료", p: "한빛시" },
      pk: "불가능", pkn: { n: "호수공원 주차장", m: 120 } } },
  // a gallery reached by stairs only (a need it breaks, operator 2026-10-18) with a 설날·추석 closing rule
  "/places/stair-gallery/": { t: "계단갤러리", k: "place", x: "계단갤러리 — 관광지 · 박물관·전시",
    f: { kd: "attraction", ty: "박물관·전시", g: [35.9890, 126.7120], c: [{ p: "공식", t: "매주 월요일, 설날·추석 당일" }], h: [{ p: "공식", t: "10:00~18:00" }],
      fee: { free: true, t: "무료", p: "공식" }, ac: [{ k: "accessible_route", t: "계단만 있음", p: "무장애" }] } },
  // a café (TourAPI class 카페: pipeline/schema.py FOOD_LCLS) for the day's café stop (operator 2026-10-18)
  "/places/cafe-bom/": { t: "봄카페", k: "place", x: "봄카페 — 음식점 · 카페. 메뉴 아메리카노",
    f: { kd: "food", ty: "카페", g: [35.9880, 126.7130], c: [{ p: "한국관광공사", t: "연중무휴" }], h: [{ p: "한국관광공사 TourAPI", t: "10:00~20:00" }] } },
  "/places/hanok-gukbap/": { t: "한옥국밥", k: "place", x: "한옥국밥 — 음식점 · 중식. 국밥",
    f: { kd: "food", ty: "중식", g: [35.978208, 126.715771], c: [{ p: "한빛시", t: "일요일,공휴일 휴무" }], h: [{ p: "한빛시 문화관광", t: "10:00~16:00" }] } },
  "/places/hotel/": { t: "호텔", k: "place", x: "호텔 — 숙소", f: { kd: "stay", ty: "호텔", g: [35.98, 126.71], ci: "15:00" } },
  "/guides/transport/": { t: "교통", k: "guide", x: "교통 — 가이드" },
};
const P = (name) => Object.keys(DOCS).find((k) => DOCS[k].t === name);
const TICKETS = [
  { id: "museum-combined", name: "박물관 통합권", covers: "박물관+미술관+건축관+위봉함",
    places: ["한빛역사박물관", "옛 은행 건물", "근대건축관", "해양공원"].map((n) => ({ path: P(n), name: n })),
    src: "한빛시 문화관광 표 (출처 확인 2026-10-08)", prices: { 개인: { 성인: [3000, 2000], "청소년·군인": [2000, 1000], 어린이: [1000, 500] } }, rules: [] },
  { id: "river-combined", name: "강변권 통합권", covers: "박물관4개소+강변권1개소",
    places: ["한빛역사박물관", "옛 은행 건물", "근대건축관", "해양공원", "강변미래체험관"].map((n) => ({ path: P(n), name: n })),
    src: "한빛시 문화관광 표", prices: { 개인: { 성인: [5000, 3000], "청소년·군인": [4000, 2000], 어린이: [3000, 1000] } },
    rules: [{ kind: "age", category: "어린이", from: 7, to: 12, text: "어린이(7~12세)", src: "강변미래체험관" },
      { kind: "free", who: "6세 이하 유아", age_max: 6, src: "기념관" }, { kind: "free", who: "65세 이상 어른", age_min: 65, src: "기념관" },
      { kind: "free", who: "장애인", src: "기념관" }, { kind: "note", text: "입장권은 발행 당일에만 사용", src: "기념관" }] },
];

function indexOf(docs) {
  const out = {};
  for (const [key, d] of Object.entries(docs)) out[key] = [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")];
  return { v: 1, docs: out };
}
const kb = () => new Knowledge({ catalog: "# catalog\nP /places/history-museum/ | 한빛역사박물관",
  docs: { v: 1, site: SITE, meta: META, docs: DOCS, alias: {}, ext: [], tickets: TICKETS }, index: indexOf(DOCS) });


const strictKb = (extra = {}) => new Knowledge({ catalog: "# catalog", index: indexOf(DOCS), docs: { v: 1, site: SITE, docs: DOCS, alias: {}, ext: [], tickets: [],
  meta: { ...META, plan: { ...META.plan, transit_strict: true,
    hubs: { ...META.plan.hubs, station: { name: "한빛역", region: "역앞" } },
    hub_guides: [{ path: "/guides/transport/", label: "한빛 시내버스 안내" }], ...extra } } } });
const COND = { date: "2026-10-20", days: 1, start: "10:00", end: "18:00", move: "transit", with: "couple", adults: 2, kids: [],
  prefs: ["history"], needs: [] };
const stop = (name, start, end, role = "visit", why = "") => ({ page: P(name), start, end, role, why });
const leg = (k, a, b, gap = 60, move = "transit") => k.checkPlan({ date: "2026-10-20", move,
  stops: [{ page: P(a), start: "10:00", end: "11:00" }, { page: P(b), start: `${String(11 + Math.floor(gap / 60)).padStart(2, "0")}:${String(gap % 60).padStart(2, "0")}`, end: "13:30" }] });

test("the city's values come from meta: hubs, likes, the region's name, the site's — none is the engine's", () => {
  const k = kb();
  assert.deepEqual(Object.keys(city().hubs).sort(), ["bus", "harbour", "station"]);
  const c = validConditions({ ...COND, from: "station", to: "bus", prefs: ["history", "night"] }, NOW);
  assert.throws(() => validConditions({ ...COND, from: "airport" }, NOW), /bad_request/);   // a hub the city does not list
  assert.throws(() => validConditions({ ...COND, prefs: ["islands"] }, NOW), /bad_request/); // a like it does not offer
  const text = conditionsText(c);
  assert.match(text, /- 출발: 한빛역에서 10:00/);
  assert.match(text, /- 도착: 18:00까지 한빛버스터미널/);
  assert.match(text, /- 좋아하는 것: 역사·문화\(박물관·문화유산·근대 건물\), 야경/);
  const rules = planRules(k.tickets);
  assert.match(rules, /^You are the course planner of the travel website 한빛 여행 \(Hanbit Travel, https:\/\/travel\.hanbit\.kr\)\. You build a day-by-day travel plan for Hanbit, South Korea/);
  assert.match(rules, /the combined tickets' tables \(박물관 통합권, 강변권 통합권 — it picks the cheaper way each day\)/);
  // no far area, no strict rule, no city line: none of them said
  assert.doesNotMatch(rules, /to or from |names no bus stop or route|This city:/);
  assert.match(buildPlanSystem("# c", NOW, "", k.tickets)[0].text, /한빛 여행/);
  assert.equal(codeText({ days: [{ date: "2026-10-20", stops: [] }] }, c, k).title.slice(0, 22), "10월 20일(화) 한빛 하루 코스");
});

test("a far area, a hub's area and the city's own lines are the meta's: the margins and the rules follow them", () => {
  const k = strictKb({ far: { 섬: { car: 60, transit: 120 } }, rules: ["Ferries are not on this site."] });
  const doc = (r) => ({ x: `곳 — 관광지\n위치: 어딘가 · ${r} 권역` });
  assert.equal(hubMargin({ from: "station", move: "transit" }, "from", doc("역앞")), 30);
  assert.equal(hubMargin({ from: "station", move: "transit" }, "from", doc("구도심")), 45);
  assert.equal(hubMargin({ from: "station", move: "car" }, "from", doc("섬")), 60);
  assert.equal(hubMargin({ from: "station", move: "transit" }, "from", doc("섬")), 120);
  assert.equal(hubMargin({ from: "bus", move: "transit" }, "from", doc("구도심")), 30);   // a hub with no area: the plain margin
  const rules = planRules([]);
  assert.match(rules, /2 hours without a car, 1 hour by car, to or from 섬/);
  assert.match(rules, /This city:\n- Ferries are not on this site\./);
  assert.match(rules, /Without a car this site names no bus stop or route for its places/);
  // the hub guide: the city's list, first match — and none by car, none the site does not have
  const c = { move: "transit" };
  assert.deepEqual(hubGuide(c, "station", doc("구도심"), k), { path: "/guides/transport/", label: "한빛 시내버스 안내" });
  assert.equal(hubGuide({ move: "car" }, "station", doc("구도심"), k), null);
  assert.equal(hubGuide(c, "station", doc("구도심"), kb()), null);   // the plain city lists no guide
});

test("without a car, no bus data (transit_strict): a walk is a leg, a short ride a check, a longer one sent back — by car nothing", () => {
  const k = strictKb();
  assert.equal(city().transitStrict, true);
  let r = leg(k, "한빛역사박물관", "옛 은행 건물");                  // ~130 m: a walk
  assert.deepEqual([r.flags, r.legs[0].open], [[], undefined]);
  r = leg(k, "한빛역사박물관", "인형박물관");                        // ~1.6 km: past a walk, under a ride
  assert.ok(r.legs[0].m > WALK_M && r.legs[0].m <= RIDE_M, String(r.legs[0].m));
  assert.deepEqual([r.flags, r.legs[0].open], [[], true]);
  assert.match(r.text, /차 없이 직선 1\.\dkm로 걷기엔 먼 구간이고 사이트에 두 곳을 잇는 버스 노선이 없음\(이동 확인 필요\)/);
  r = leg(k, "한빛역사박물관", "한빛대학교 박물관");                 // ~5.4 km, an hour's margin: sent back
  assert.equal(r.flags.length, 1);
  assert.match(r.flags[0], /차 없이 직선 5\.\dkm — 사이트에 두 곳을 잇는 버스 노선이 없고 걸어서 갈 거리도 아니다/);
  assert.deepEqual(leg(k, "한빛역사박물관", "한빛대학교 박물관", 60, "car").flags, []);
  // two places whose stops share a route: a leg the data confirms
  r = leg(k, "한빛역사박물관", "항구1981");
  assert.deepEqual(r.legs[0].routes, ["01"]);
  // the plain city (no transit_strict) as before: no check, no flag
  const plain = kb();
  assert.equal(city().transitStrict, false);
  r = leg(plain, "한빛역사박물관", "한빛대학교 박물관");
  assert.deepEqual([r.flags, r.legs[0].open], [[], undefined]);
});

test("without a car (transit_strict): the way to the first stop, a short ride and the next day's start are checks — the plan a candidate", () => {
  const k = strictKb();
  const c = validConditions({ ...COND, from: "station", to: "station" }, NOW);
  const { plan } = readSubmit({ title: "t", summary: "s", notes: [], days: [{ date: "2026-10-20", stops: [
    stop("한빛역사박물관", "10:40", "11:40"), stop("한옥국밥", "12:00", "13:00", "meal"), stop("인형박물관", "13:40", "15:00"),
    stop("옛 은행 건물", "15:50", "17:00")] }] }, c, k);
  const v = verify(plan, c, k);
  const tr = v.checks.filter((x) => x.k === "transit").map((x) => x.t);
  assert.ok(tr.some((t) => /^한빛역 → 한빛역사박물관: 차 없이 갈 확인된 대중교통이 사이트에 없어요 — 한빛 시내버스 안내의 시간표나 택시로 확인하세요$/.test(t)), tr.join("\n"));
  assert.ok(tr.some((t) => /^옛 은행 건물 → 한빛역: /.test(t)), tr.join("\n"));
  assert.ok(tr.some((t) => /^한옥국밥 → 인형박물관: 차 없이 갈 확인된 대중교통이 사이트에 없어요\(직선 1\.\dkm\)/.test(t)), tr.join("\n"));
  assert.ok(!v.aware.some((x) => x.k === "hub"));   // the hub's leg is a check here, not a standing note
  // the page's heading: a candidate to check, never '코스 완성' (templates/assets/plan.js headOf)
  const PLAN_JS = readFileSync(new URL("../../templates/assets/plan.js", import.meta.url), "utf8");
  assert.match(PLAN_JS, /x\.k === "transit"[\s\S]{0,200}이동 확인이 필요한 후보 일정 · 가기 전 확인 /);
  // by car none of them
  const car = validConditions({ ...COND, move: "car", from: "station", to: "station" }, NOW);
  const v2 = verify(readSubmit({ title: "t", summary: "s", notes: [], days: [{ date: "2026-10-20", stops: [stop("한빛역사박물관", "10:40", "11:40")] }] }, car, k).plan, car, k);
  assert.deepEqual(v2.checks.filter((x) => x.k === "transit"), []);
});

test("without a car (transit_strict): the code's own course tries walks only first, then short rides it marks to check", () => {
  const k = strictKb();
  const c = validConditions({ ...COND, start: "10:00", end: "15:00", prefs: [] }, NOW);
  assert.equal(cap({ ...c, walk: true }), WALK_M);
  const built = buildPlan(c, k);
  assert.ok(built.plan, "a course");
  const g = (s) => DOCS[s.page].f.g;
  const m = (a, b) => {
    const rad = (x) => (x * Math.PI) / 180;
    const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(h));
  };
  for (const d of built.plan.days) {
    for (let j = 0; j + 1 < d.stops.length; j += 1) assert.ok(m(g(d.stops[j]), g(d.stops[j + 1])) <= RIDE_M, `${d.stops[j].name} → ${d.stops[j + 1].name}`);
  }
  assert.deepEqual(preflight(c, k, NOW), []);
});

test("roles by the place's type: a typed café (카페·제과) is a café, never a meal or a visit; a liking read by the city's labels", () => {
  const doc = (kd, ty, menu = "") => ({ t: "x", k: "place", x: `x — 음식점${menu ? `\n- 대표 메뉴: ${menu}` : ""}`, f: { kd, ...(ty ? { ty } : {}) } });
  assert.equal(isCafe(doc("food", "카페")), true);
  assert.equal(isCafe(doc("food", "제과")), true);
  assert.equal(isMeal(doc("food", "카페")), false);
  assert.equal(isCafe(doc("food", "한식")), false);
  assert.equal(isMeal(doc("food", "한식")), true);
  assert.equal(isCafe(doc("food", "", "아메리카노")), true);   // an untyped page by its menu, as before
  // the city's own list label (docs.json f.ct) read for a liking only when site.json plan.pref_types names it
  strictKb({ pref_types: { nature: ["숲·계곡"] } });
  const forest = { t: "숲", k: "place", x: "숲 — 관광지", f: { kd: "attraction", ct: "숲·계곡" } };
  assert.equal(prefFits("nature", forest), true);
  assert.equal(prefFits("history", forest), false);
  kb();
  assert.equal(prefFits("nature", forest), false);
});

// ------------------------------------------------------------------ the real knowledge (tests/test_chat_node.py sets it)
const REAL = process.env.CHAT_KB_DIR;
const RNOW = new Date("2026-10-24T01:00:00Z");   // 2026-10-24 (Sat) 10:00 KST, the paid review's day

test("real knowledge: the city's meta — hubs with their areas, likes, the strict way without a car, the planner's classes", { skip: !REAL && "CHAT_KB_DIR not set" }, async () => {
  const k = await loadKnowledge(REAL);
  const C = city();
  assert.ok(Object.values(C.hubs).length >= 1 && Object.values(C.hubs).every((h) => h.name));
  assert.ok(Object.keys(C.prefs).length >= 4 && !("islands" in C.prefs));
  assert.equal(C.transitStrict, true);
  assert.ok(planRules(k.tickets).includes(k.meta.siteName));
  const places = Object.values(k.docs).filter((d) => d.k === "place");
  // a place to visit carries the engine's class only (pipeline/plan.py PLAN_CLASSES), its own label beside it
  const CLASSES = ["박물관·전시", "체험", "레포츠", "문화유산", "문화시설", "골목과 문화", "시장·쇼핑", "자연·야외", "산업·회의 시설"];
  assert.ok(places.filter((d) => d.f.kd === "attraction" && d.f.ty).every((d) => CLASSES.includes(d.f.ty)));
  assert.ok(places.some((d) => d.f.ct));
  // hours written in clock words are read (pipeline/textutil.clock_hours): none of the restaurants' is left unread
  const unread = places.filter((d) => d.f.kd === "food" && (d.f.h || []).length).filter((d) => {
    const key = Object.keys(k.docs).find((x) => k.docs[x] === d);
    const r = k.checkPlan({ date: "2026-10-28", stops: [{ page: key, start: "14:00", end: "15:00" }] });
    return (r.stops[0].checks || []).some((x) => /하나로 읽지 못해/u.test(x));
  }).map((d) => d.t);
  assert.deepEqual(unread, []);
});

test("real knowledge: the paid review's two courses (2026-10-24) — by car, and 1박 2일 without a car from the station", { skip: !REAL && "CHAT_KB_DIR not set" }, async () => {
  const k = await loadKnowledge(REAL);
  const base = { days: 1, start: "10:00", end: "18:00", seniors: 0, needs: [] };
  const a = validConditions({ ...base, date: "2026-10-31", move: "car", with: "kids", adults: 2, kids: [7], prefs: ["history", "nature"] }, RNOW);
  const b = validConditions({ ...base, date: "2026-10-31", days: 2, move: "transit", with: "couple", adults: 2, kids: [], prefs: ["food", "cafe"],
    from: "station", to: "station" }, RNOW);
  for (const c of [a, b]) {
    const plan = codePlan(c, k, RNOW, "일정 전체: 사이트 자료로 짰습니다");
    assert.ok(plan, JSON.stringify(c));
    assert.equal(plan.status, "ready");
    const pages = plan.days.flatMap((d) => d.stops.filter((s) => s.role !== "stay").map((s) => s.path));
    assert.equal(new Set(pages).size, pages.length, "a place once");
    plan.days.forEach((d, i) => {
      // a night's stay every night but the last, a restaurant never a place to visit, a café never a meal
      assert.equal(d.stops.filter((s) => s.role === "stay").length, i < plan.days.length - 1 ? 1 : 0, d.date);
      for (const s of d.stops) {
        const f = k.docs[s.path].f;
        if (f.kd === "food") assert.notEqual(s.role, "visit", s.name);
        if (isCafe(k.docs[s.path])) assert.notEqual(s.role, "meal", s.name);
      }
    });
    if (c.move === "transit") {
      // every leg of a day a walk or a ride of RIDE_M at most, each ride and the station's legs a check
      const tr = plan.checks.filter((x) => x.k === "transit");
      assert.ok(tr.some((x) => x.t.startsWith(`${city().hubs.station.name} → `)), JSON.stringify(tr));
      for (const d of plan.days) for (const l of d.legs || []) assert.ok(l.m === null || l.m <= RIDE_M || l.open, JSON.stringify(l));
    } else assert.deepEqual(plan.checks.filter((x) => x.k === "transit"), []);
  }
});
