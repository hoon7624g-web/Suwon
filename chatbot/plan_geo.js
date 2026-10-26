// The course planner's shared ground (chatbot/planner.js repairs, chatbot/plan_build.js builds): times, straight
// lines, the margin a leg gets, the places with a point, and whether a place opens on a date at given times by the
// site's own data (knowledge.checkPlan's reading, cached per date). Moved out of planner.js (2026-10-18, fifth round)
// so the day builder and the repairs read the same rules.
import { city } from "./city.js";
import { WALK_M, iga, eul, jong, legBound, regionFloor, regionOf, ro, sessionGaps } from "./knowledge.js";
import { planFees } from "./plan_fees.js";
import { hubMargin, isCafe, isOutside, needAt, rainShut } from "./plan_state.js";

export { eul, iga, jong, legBound, regionOf, ro };

const HM = /^([01]\d|2[0-3]):([0-5]\d)$/;
export const mins = (t) => {
  const m = HM.exec(t || "");
  return m ? +m[1] * 60 + +m[2] : null;
};
export const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;

export const metres = (a, b) => {
  const rad = (x) => (x * Math.PI) / 180;
  const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
};
export const km = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`);
export const STAY_NEAR = 5000;   // a stay the code adds for a night is within this straight-line distance of the day's last stop
// a place the code puts in — for a stop closed that day, a missing meal, an empty stretch — is within this straight
// line of the stop it goes next to: [without a car, by car]
export const NEAR = { swap: [3000, 5000], meal: [1500, 5000], fill: [3000, 5000] };
// the farthest a place the code adds or swaps in may be from the nearer of the stops next to it (not a night's stay),
// straight line: [without a car, by car] (operator 2026-10-19, round 6: 25 of 600 plans had a meal the code added more
// than 5 km from both neighbours — the car day builder looked 15 km out). From the data (docs.json, places with a point:
// 121 places to visit with hours, 129 restaurants that serve a meal), the straight line from a place to visit to the
// nearest such restaurant: p50 868 m, p75 2.1 km, p90 4.6 km, p95 6.9 km — every 원도심 place within 1.2 km, every
// 해안 권역 place within 2.4 km, 섬 권역 up to 9.0 km, the far islands 18–52 km. Without a car 3 km: 81% of places to
// visit have such a restaurant within it, the whole of 원도심 and 해안 권역 — a walk or one short bus ride (legMargin
// 30 minutes); by car 8 km: 97% — all but a few 섬 권역 shores and the far islands, which no car reaches. A night's stay
// is not held to it (a night needs a bed: STAY_NEAR first, then farther, and the line says how far).
export const CAP = [3000, 8000];
// (a walk's — knowledge.WALK_M — on the code's first try without a car in a city whose data names no bus for its
// places: c.walk, plan_build.buildPlan — every leg then one the site confirms)
export const cap = (c) => (c.walk ? Math.min(WALK_M, CAP[0]) : CAP[c.move === "car" ? 1 : 0]);
/** The stops of a day the code put in or swapped in (by; not a night's stay) farther than the cap from the nearer of
 *  the stops next to them (not a night's stay; with a point) — what later changes can leave (round 6: a dinner put in
 *  next to a stop the rain then took out ended 8.3 km from both its new neighbours). A place the day builder's wide try
 *  put past the cap on purpose (s.wide: nothing within it built that day) is not one (round-6 verifier). Returns their
 *  indexes in stops. */
export function farOnes(stops, c, kb, max = cap(c)) {
  const own = stops.map((s, j) => ({ s, j })).filter(({ s }) => s.role !== "stay");
  const out = [];
  own.forEach(({ s, j }, n) => {
    const g = s.by && !s.wide && gOf(kb, s.page);
    if (!g) return;
    const nb = [own[n - 1], own[n + 1]].filter((x) => x && gOf(kb, x.s.page)).map((x) => metres(gOf(kb, x.s.page), g));
    if (nb.length && Math.min(...nb) > max) out.push(j);
  });
  return out;
}
export const KEEP_MIN = 20;      // the least a stop of a kind with no floor of its own (FLOORS 관광지) keeps
export const MEAL_KEEP = 45;     // a meal the code shortens keeps at least this (one the model gave shorter is not shortened)
// the least a place the code swaps in for a stop gets (round-4 verifier: a place swapped in kept 20 minutes — the
// stop goes instead): a visit or a café 30 minutes, a meal MEAL_KEEP — and never under its kind's floor (FLOORS)
export const SWAP_MIN = { visit: 30, meal: 45, cafe: 30 };
// the least time a stop keeps by what the place is — a planning floor the code holds, never a time the site states
// (operator 2026-10-19, round 6: the model's visits were cut to exactly 20 minutes in 584 of 600 plans to fit a lunch
// or a leg's margin). Kinds are the data's own: a place to visit by its type (docs.json f.ty, the catalog's type
// label — 160 places to visit: 46 with none, shown as 관광지), a restaurant by what it is in the plan. Counts are of
// the catalog (2026-10-19).
export const FLOORS = {
  "박물관·전시": 60,    // 11: halls of exhibits — the one 관람 소요시간 the data gives for such a place is 약 1시간 (국립OO대학교 박물관)
  "체험": 45,           // 28: a programme someone runs (a farm, a craft, a ride) takes its session, not a glance
  "레포츠": 45,         // 6: a trail or a ride — a sport is not done in 20 minutes
  "문화유산": 30,       // 22: an old building's rooms or a temple's grounds, walked through
  "문화시설": 30,       // 5: a gallery, a cultural centre, a bookshop — rooms to walk through
  "골목과 문화": 30,    // 5: a lane or a village walked end to end
  "시장·쇼핑": 30,      // 11: a market walked through
  "자연·야외": 30,      // 25: a park, a lake path, an island's shore — a walk
  "산업·회의 시설": 20, // 1: a wind farm seen from where it is seen
  "관광지": KEEP_MIN,   // 46: no type in the data (a viewpoint, a bridge, a port, a street — or not known): the old least
  meal: MEAL_KEEP,      // 147 restaurants that serve a meal (plan_state.isMeal): a meal
  cafe: 30,             // 23 cafés and bakeries (plan_state.isCafe): a sitting
};
/** The floor of a stop of `role` at the place `doc` (FLOORS): a meal; a café, or a restaurant given as a visit — a
 *  café or a bakery as a café, any other as a meal —; else the place's type, else 관광지; a night's stay KEEP_MIN (it is
 *  never shortened: it moves whole). */
export function floorOf(role, doc) {
  const f = (doc && doc.f) || {};
  if (role === "stay") return KEEP_MIN;
  if (role === "meal") return FLOORS.meal;
  if (role === "cafe") return FLOORS.cafe;
  if (f.kd === "food") return isCafe(doc) ? FLOORS.cafe : FLOORS.meal;
  return FLOORS[f.ty] ?? FLOORS["관광지"];
}
/** The least a place the code puts in or swaps in as `role` gets: its floor, and never under SWAP_MIN. */
export const codeLeast = (role, doc) => Math.max(floorOf(role, doc), SWAP_MIN[role] || SWAP_MIN.visit);
/** The least a stop may be shortened to (round 6): a stop the code put in or swapped in its codeLeast (round-5
 *  verifier: a visit swapped in was cut to 20 minutes; it goes instead); one of the model's its kind's floor, or its own
 *  length when the model gave it less (the code keeps what the model chose and never cuts it further) — a meal
 *  MEAL_KEEP (round-4 verifier: a lunch cut to 20 minutes for a leg's margin). A night's stay KEEP_MIN (it moves
 *  whole). kb: the knowledge base (the place's type). */
export function keepOf(s, kb) {
  if (s.role === "stay") return KEEP_MIN;
  // a meal an edit left as the reader's page has it (s.kept — planner.markKept) keeps its whole length: never cut
  if (s.kept) return mins(s.end) - mins(s.start);
  const doc = kb.docs[s.page];
  return s.by ? codeLeast(s.role, doc) : Math.min(floorOf(s.role, doc), mins(s.end) - mins(s.start));
}
// the least the code cuts a stop to before it moves stops whole instead (round-6 verifier: the places with no type —
// islands, temples, beaches, the cruise — still went down to their 20-minute floor before any whole move was tried):
// SOFT_MIN minutes, or the stop's own length when the model gave it less, or its floor when that is more (keepOf).
// Below it, down to keepOf, only where no whole move makes the room (planner.widen, planner.addMeal,
// plan_build.placeMeal).
export const SOFT_MIN = 30;
export function softOf(s, kb) {
  const least = keepOf(s, kb);
  return s.role === "stay" ? least : Math.max(least, Math.min(SOFT_MIN, mins(s.end) - mins(s.start)));
}
// the most stops a day has, its night's stay counted: what readSubmit takes from the model and validEdit takes back
// from the page (planner.PLAN_LIMITS.stopsPerDay) — the code adds no more (round-5 verifier: days of 13 stops, the
// 13th beyond checkPlan's reading and none of them editable)
export const STOPS_MAX = 10;
// the longest a stop the code lengthens to close an empty stretch gets: a visit 3 hours, a meal or a café 90 minutes
// (2026-10-18: a lunch stretched to three hours to close an afternoon)
export const stretchMax = (s) => (s.role === "meal" || s.role === "cafe" ? 90 : 180);
export const MEAL_MIN = 60;      // a meal the code adds
export const FILL_MIN = 60;      // a place the code adds to an empty stretch: 60–90 minutes
export const FILL_MAX = 90;
export const CANDIDATES = 20;    // places read (each one's day checked) for one stop the code puts in
export const CAMP = /캠핑|야영|글램핑|카라반|찜질방/u;
export const WEEK = "일월화수목금토";
export const near = (c, what) => (c.walk ? Math.min(WALK_M, NEAR[what][0]) : NEAR[what][c.move === "car" ? 1 : 0]);
export const dateWords = (date) => {
  const dt = new Date(`${date}T12:00:00Z`);
  return `${dt.getUTCMonth() + 1}월 ${dt.getUTCDate()}일(${WEEK[dt.getUTCDay()]})`;
};

/** The margin the code leaves for a leg — a planned allowance, never a travel time (the page says so): by car 1.5 ×
 *  the straight line at 60 km/h and 5 minutes to park; without one 1.5 × the faster of walking (100 m a minute) and
 *  a bus (10 minutes' wait, then 400 m a minute); at least 10 minutes, rounded up to 5. It never shrinks as a leg
 *  grows (final check 2026-10-18: 1.2 km on foot had 20 minutes, 1.3 km by bus 10). m: metres, or null when a point
 *  is missing (10 minutes; marginOf reads the 권역 then). */
export function legMargin(m, move) {
  if (m === null) return 10;
  const t = move === "car" ? (1.5 * m) / 1000 + 5 : 1.5 * Math.min(m / 100, 10 + m / 400);
  return Math.ceil(Math.max(10, t) / 5) * 5;
}
export const gOf = (kb, page) => ((kb.docs[page] || {}).f || {}).g;
/** The point of the last of `stops` (a night's stay left out) the site has one for, or null — where a stay or a place
 *  the code adds after them is looked for when the last stop has no point (2026-10-18: a day ending at a place with no
 *  point got no stay). */
export function lastPoint(kb, stops) {
  for (let j = stops.length - 1; j >= 0; j -= 1) if (stops[j].role !== "stay" && gOf(kb, stops[j].page)) return gOf(kb, stops[j].page);
  return null;
}
/** The margin between two places (pages): legMargin of their straight line; with a point missing, at least the floor
 *  between two 권역 (knowledge.regionFloor, the one checkPlan holds such a leg to). */
export function marginOf(pa, pb, c, kb) {
  const ga = gOf(kb, pa), gb = gOf(kb, pb);
  return ga && gb ? legMargin(metres(ga, gb), c.move) : Math.max(legMargin(null, c.move), regionFloor(kb.docs[pa], kb.docs[pb], c.move));
}
/** The least minutes a leg over 1.2 km without a car takes, unpadded: on foot, or by bus with its wait (10 minutes) —
 *  what checkPlan's bound (a bus's speed, no wait: knowledge.legBound) lets through (round 7 review A04, A08, A10, A17:
 *  10–15 minutes for 1.3–2.6 km with no bus listed). null with a car, a point missing, or 1.2 km and under (on foot:
 *  the bound is the walk). */
export function rideLeast(pa, pb, c, kb) {
  const ga = gOf(kb, pa), gb = gOf(kb, pb);
  if (c.move === "car" || !ga || !gb) return null;
  const m = metres(ga, gb);
  return m > 1200 ? Math.min(m / 100, 10 + m / 400) : null;
}
/** The least a leg between two places the model put next to each other may have and pass the check (checkPlan: more
 *  than nothing, not under the straight line's bound, not under the floor between two 권역 with no point), in 5s and
 *  never under 10 minutes (what widen held a flagged leg to before). */
export function legFloor(pa, pb, c, kb) {
  const ga = gOf(kb, pa), gb = gOf(kb, pb);
  const bound = ga && gb ? legBound(metres(ga, gb), c.move) : regionFloor(kb.docs[pa], kb.docs[pb], c.move);
  return Math.max(10, Math.ceil(bound / 5) * 5);
}
// the places with a point, once per knowledge base: [{page, doc}]
const PLACES = new WeakMap();
export function placesOf(kb) {
  if (!PLACES.has(kb)) {
    // (never one on an island reached only by ferry: knowledge.ferry — the site has no sailing times)
    PLACES.set(kb, kb.keys.filter((k) => kb.docs[k] && kb.docs[k].k === "place" && (kb.docs[k].f || {}).g && !(kb.ferry && kb.ferry.has(k)))
      .map((k) => ({ page: k, doc: kb.docs[k] })));
  }
  return PLACES.get(kb);
}
// a restaurant's break in the day ('준비시간 14:00~16:30', '브레이크타임 15:00~17:00'): a meal the code adds stays out of it
const BREAK = /(?:준비\s*시간|브레이크\s*타임|break\s*time)\s*[:：]?\s*(\d{1,2}):(\d{2})\s*[~∼～〜–-]\s*(\d{1,2}):(\d{2})/giu;
// a place to visit's own break ('점심시간 12:00~13:00', '휴게시간 11:30~12:30' — round-7 review: 구 조선식량영단 OO출장소);
// never a restaurant's, whose 점심시간 is when it serves
const REST = /(?:점심\s*시간|휴게\s*시간)\s*[:：]?\s*(\d{1,2}):(\d{2})\s*[~∼～〜–-]\s*(\d{1,2}):(\d{2})/giu;
// (the breaks read once per place's data: [[from, to, source, words?]] in minutes)
const BREAKS = new WeakMap();
/** The break of a place's day (its data f) that a–b runs into: [from, to, source, words] (minutes, the value's source;
 *  words only for the gap between two sessions of the day — knowledge.sessionGaps: from the first one's last entry to
 *  the next one's start, '1회차 입장 마감부터 2회차 시작 전까지'), or null. Every value the data has is read (two sources,
 *  one with a break: the break holds — the plan keeps out of it, and says whose it is). `sessions` false: the breaks the
 *  value names only (checkPlan reads the sessions itself). */
export function breakOf(f, a, b, { sessions = true } = {}) {
  if (!BREAKS.has(f)) {
    BREAKS.set(f, (f.h || []).flatMap((h) => [...[...String(h.t || "").matchAll(BREAK), ...(f.kd === "food" ? [] : String(h.t || "").matchAll(REST))]
      .map((m) => [+m[1] * 60 + +m[2], +m[3] * 60 + +m[4], h.p || ""]),
    ...sessionGaps(String(h.t || "")).map(([x, y, w]) => [x, y, h.p || "", w])]));
  }
  return BREAKS.get(f).find((br) => a < br[1] && b > br[0] && (sessions || !br[3])) || null;
}
export const inBreak = (f, a, b) => !!breakOf(f, a, b);
/** A break's words: '쉬는 시간 15:00~17:00', or for the gap between two sessions its own words and times. */
export const breakWords = (br) => `${br[3] || "쉬는 시간"} ${hhmm(br[0])}~${hhmm(br[1])}`;
export const ALWAYS = /상시\s*(?:개방|이용)|24\s*시간/u;

// one place's day by the site's data, once per knowledge base, date and page (a checkPlan reading with no times):
// {state: 'open' | 'check' | 'closed' | null, day, checks, hours: [{open, close, last}], read, always}
const DAYS = new WeakMap();
export function dayInfo(kb, date, page) {
  if (!DAYS.has(kb)) DAYS.set(kb, new Map());
  const byDate = DAYS.get(kb);
  if (!byDate.has(date)) byDate.set(date, new Map());
  const cache = byDate.get(date);
  if (cache.has(page)) return cache.get(page);
  const r = kb.checkPlan({ date, stops: [{ page, start: "", end: "" }] });
  const s = r.stops[0] || { day: "unknown", checks: [], hours: [] };
  const f = (kb.docs[page] || {}).f || {};
  const always = (f.h || []).some((h) => ALWAYS.test(h.t || ""));
  // flags with no times: closed that day (a closed day, a notice) or a fortnightly rule — never a stop to put in
  // (a season's hours read as the ones every season keeps — '이용시간 — …: 계절마다 시간이 달라' — say nothing of the day:
  // the place is as open as it was)
  const dayChecks = (s.checks || []).filter((x) => !/^이용시간 — /u.test(x));
  const state = r.flags.length || s.day === "closed" ? "closed"
    : s.day === "open" && !dayChecks.length ? "open"
      : (s.day === "open" || s.day === "unknown") && (f.c || []).length ? "check" : null;
  const info = { state, day: s.day, checks: s.checks || [], hours: s.hours || [], read: (s.hours || []).length > 0 || always, always,
    disputed: s.disputed || "" };
  cache.set(page, info);
  return info;
}
/** Whether a–b keeps to every hours line the site gives for that date (checkPlan's own test: not before opening, not
 *  after closing when it closes the same day, not starting after the last entry) and, for a restaurant, its break. */
export function fitsHours(kb, info, page, a, b) {
  for (const h of info.hours) {
    if (a < h.open || (h.close > h.open && b > h.close) || (h.last !== null && a > h.last)) return false;
    // (a day of sessions: the visit keeps to one of them — in, by its last entry, out by its closing)
    if (h.sessions && !h.sessions.some((x) => a >= x.open && b <= x.close && (x.last === null || a <= x.last))) return false;
  }
  return !inBreak((kb.docs[page] || {}).f || {}, a, b);
}

/** Whether a place opens that day at those times by the site's data — nothing flagged (a closed day, a notice, hours,
 *  the last entry), hours the check could read for that date holding the times (or a value that says it is always
 *  open — '상시 개방', '24시간'; never '내부 관람 불가' or a season with no months), and for a restaurant outside its
 *  break — and then how far the data goes: 'open' (checkPlan 'open', nothing to check that day), 'check' (not a regular
 *  closed day, but the day leaves something to check: a public holiday, a 설·추석·명절 or 공휴일 rule), or null (not
 *  that, or no closed days on the site at all). The reader's words say only what is known (openWords). */
export function opensAt(kb, date, page, a, b) {
  const info = dayInfo(kb, date, page);
  if (!info.state || info.state === "closed" || !info.read || b <= a || !fitsHours(kb, info, page, a, b)) return null;
  return info.state;
}
/** The reason a stop goes or is swapped for its closed day, in the reader's words: '10월 19일(월)은 쉬는 날이라' — or,
 *  when the sources disagree on that day (dayInfo disputed), that disagreement, never the closing as a fact (round-6
 *  verifier: '완주옥: 1월 20일(수)은 쉬는 날이라' where 시 says 연중무휴): '1월 20일(수)은 출처마다 쉬는 날이 달라(시
 *  '연중무휴' · 한국관광공사 '매주 수요일' — 방문 전 전화 확인)'. form 'and': '…쉬는 날이고' / '…달라 확인이 필요하고'. */
export function closedWhy(kb, date, page, form = "as") {
  const when = dateWords(date);
  const d = dayInfo(kb, date, page).disputed;
  if (!d) return form === "and" ? `${when}은 쉬는 날이고` : `${when}은 쉬는 날이라`;
  return `${when}은 출처마다 쉬는 날이 달라(${d} — 방문 전 전화 확인)${form === "and" ? " 확인이 필요하고" : ""}`;
}
// what the code says of a place it puts in, by opensAt: 'open' — it opens then; 'check' — only what is known
export const CHECK_WORDS = "정기 휴무가 아닌 곳 — 그날 운영은 확인 필요";
export const openWords = (open) => (open === "open" ? "그날 그 시각에 여는 곳" : CHECK_WORDS);
// a change that would push the admissions the code prices over the reader's budget (and above what they were) is
// not made: before = the known total before the change (knownFees)
export function overBudget(plan, c, kb, before) {
  if (c.budget === null || c.budget === undefined) return false;
  const f = planFees(plan.days, c, kb, c.budget);
  return f.verdict === "over" && f.known > before;
}
export const knownFees = (plan, c, kb) => (c.budget === null || c.budget === undefined ? 0 : planFees(plan.days, c, kb, c.budget).known);
// rain (비 와도 실내 위주): an indoor type first (plan_state.needAt 'ok'), then a typed place that is not outdoor;
// never an outdoor type (자연·야외·레포츠) and never a place with no type — whether it is indoors is not known
export function rainRank(c, f) {
  if (!c.needs.includes("rain") || f.kd !== "attraction") return 0;
  const st = needAt("rain", f, "visit").state;
  return st === "ok" ? 0 : st === "unknown" && f.ty ? 1 : null;
}
// (a budget: a place to visit with no fee data after one free or priced — round 7 review A05: a swap for a free
// place put in one with no fee data and the budget's verdict went from 'within' to 'open'; plan_build's feeKnown)
export const freeRank = (c, f) => ((c.needs.includes("free") && !(f.fee && f.fee.free))
  || (c.budget != null && f.kd === "attraction" && !(f.fee && (f.fee.free || f.fee.tab))) ? 1 : 0);
// the needs a stop must not fail (the data says 'no'): wheelchair, stroller, free (a visit), parking
export const HARD = ["wheelchair", "stroller", "free", "parking"];
/** The needs the reader picked that a stop must not fail: HARD, and the rain need for a place that shuts in the rain
 *  ('우천시 휴장' — plan_state.rainShut; the rain need is otherwise soft: rainRank, one outdoor place a day). */
export const hardNeeds = (c) => c.needs.filter((n) => HARD.includes(n) || n === "rain");
/** A place's state for each hard need the reader picked: 'ok' (or 'near' for parking), 'unknown', 'no' — the worst.
 *  fee: a free page is 'ok', a table 'no', anything else 'unknown' (needHints' reading; plan_fees prices the plan). */
// (read once per place's data, needs and role: the day builder asks it of every candidate at every slot)
const HARD_STATES = new WeakMap();
const HARD_KEYS = new WeakMap();   // a needs list → the hard needs in it, as one key ('' for none)
export function hardState(c, f, role) {
  let key = HARD_KEYS.get(c.needs);
  if (key === undefined) {
    key = hardNeeds(c).sort().join(",");
    HARD_KEYS.set(c.needs, key);
  }
  if (!key) return "ok";
  let memo = HARD_STATES.get(f);
  if (!memo) HARD_STATES.set(f, (memo = new Map()));
  const k = `${key}|${role}`;
  let st = memo.get(k);
  if (st === undefined) memo.set(k, (st = hardStateOf(c, f, role)));
  return st;
}
function hardStateOf(c, f, role) {
  let worst = "ok";
  for (const need of hardNeeds(c)) {
    if (need === "rain") {
      if (rainShut(f)) return "no";
      continue;
    }
    const fee = need === "free" ? { how: "own", states: f.fee && f.fee.free ? { free: 1 } : f.fee && f.fee.tab ? { paid: 1 } : { unknown: 1 } } : null;
    const st = needAt(need, f, role, fee, c.move).state;
    if (st === "no") return "no";
    // (a route only by car is not one the code puts in on its own: the reader's to check, as one the data does not know)
    if (st === "unknown" || st === "cond") worst = "unknown";
  }
  return worst;
}
// an outdoor type (자연·야외, 레포츠), a place TourAPI's own class puts outdoors (f.od — pipeline/plan.outdoor_lcls: 폭포,
// 계곡, 도시공원, 분수, 다리 …), or a place whose inside is not open to visitors by its own data (plan_state.isOutside:
// '내부 관람 불가', '외부,정원만 관람') — for the rain it is the day's one short
// outdoor stop at most, never an indoor one and never one the code swaps in
export const isOutdoor = (f) => /자연·야외|레포츠/u.test(f.ty || "") || !!f.od || isOutside(f);
/** Whether a place may go in where the code puts one, for the hard needs the reader picked: a visit only when the data
 *  says it fits every one ('ok' — what buildDay adds), a meal, a café or a stay when the data does not say 'no'
 *  (round-5 verifier: a paid museum and a place the data says nothing of for the wheelchair went in as fills). */
export function codeFits(c, f, role) {
  if (!hardNeeds(c).length) return true;
  const st = hardState(c, f, role);
  return role === "visit" ? st === "ok" : st !== "no";
}

/** Whether a place is in `taken` (the pages of a plan) or goes with one that is — a park and a place inside it, two
 *  pages of one building (knowledge.kin): the code puts neither in where the other is (live check 2026-10-19). */
export const isTaken = (kb, taken, page) => taken.has(page) || [...((kb.kin && kb.kin.get(page)) || [])].some((q) => taken.has(q));

/** The place nearest a stop that fits `fits`, open that day at the times `slot` gives it: {page, name, m, f, open,
 *  ...slot} or null — fits(doc, page); open: opensAt's 'open' or 'check'; one with nothing to check comes first, one with something to
 *  check only when no other fits. Candidates: places of the site with a point, not in the plan, within `max` metres
 *  of `at`; ranked by rank() then distance; each one's day checked (opensAt) and, with a budget, its fee (overBudget
 *  after put()). */
export function nearestOpen({ kb, c, date, at, max, fits, rank = () => [0], slot, taken, put, limit = CANDIDATES }) {
  const list = placesOf(kb).filter((p) => !isTaken(kb, taken, p.page) && fits(p.doc, p.page))
    .map((p) => ({ page: p.page, name: p.doc.t, f: p.doc.f, doc: p.doc, m: metres(at, p.doc.f.g) }))
    .filter((x) => x.m <= max)
    .map((x) => ({ ...x, r: rank(x) }))
    .filter((x) => x.r !== null)
    .sort((a, b) => {
      for (let k = 0; k < a.r.length; k += 1) if (a.r[k] !== b.r[k]) return a.r[k] - b.r[k];
      return a.m - b.m || (a.name < b.name ? -1 : 1);
    })
    .slice(0, limit);
  let checked = null;
  for (const x of list) {
    for (const t of slot(x)) {
      const open = opensAt(kb, date, x.page, t.a, t.b);
      if (!open || (open === "check" && checked)) continue;
      if (put && !put({ ...x, ...t })) continue;
      if (open === "open") return { ...x, ...t, open };
      checked = { ...x, ...t, open };
    }
  }
  return checked;
}

// the site's own bus guidance for a hub's leg without a car (the first site's review 2026-10-22 S2: the hub row linked
// only a map search by names, though the guides have the buses for these very legs): the city's list (site.json
// plan.hub_guides — docs.json meta.plan.hubGuides, city.js), in its order, each for a hub, a travel area of the stop,
// both or neither (the city-bus guide last)
/** The guide for a hub's leg (hubLegs): {path, label} — the first of the city's hub guides whose hub and area (when it
 *  names them) are the leg's —, or null: by car (a bus guide does nothing for a driver), or when the knowledge base has
 *  no such section (a guide renamed: no link to nowhere). */
export function hubGuide(c, key, doc, kb) {
  if (c.move === "car" || !kb) return null;
  const r = regionOf(doc);
  const pick = city().hubGuides.find((g) => (!g.hub || g.hub === key) && (!g.region || g.region === r));
  return pick && kb.docs[pick.path] ? { path: pick.path, label: pick.label } : null;
}

/** Where the trip starts and ends when the reader named a station or a terminal: [{dir, name, stop, gap, need,
 *  url, guide?}] — gap = minutes between the hub's time (the first day's start, the last day's end) and the first or
 *  last stop; need = the margin the code holds there (plan_state.hubMargin, by the stop's 권역); guide = the site's
 *  bus guide for the leg without a car (hubGuide). The site has no point for a hub, so its leg is a directions link by
 *  names only. hubs: plan_prompt.HUBS; kb: the knowledge base (without it, need is HUB_MARGIN and no guide). */
export function hubLegs(plan, c, hubs, kb = null) {
  const out = [];
  const q = encodeURIComponent;
  const first = (plan.days[0] || { stops: [] }).stops[0];
  const lastDay = plan.days[plan.days.length - 1] || { stops: [] };
  const last = [...lastDay.stops].reverse().find((s) => s.role !== "stay");
  const docOf = (s) => (kb ? kb.docs[s.page] : null);
  const guide = (key, s) => { const g = hubGuide(c, key, docOf(s), kb); return g ? { guide: g } : {}; };
  if (c.from && first) {
    out.push({ dir: "from", name: hubs[c.from], stop: first.name, at: c.start, gap: mins(first.start) - mins(c.start),
      need: hubMargin(c, "from", docOf(first)), url: `https://map.kakao.com/?sName=${q(hubs[c.from])}&eName=${q(first.name)}`, ...guide(c.from, first) });
  }
  if (c.to && last) {
    out.push({ dir: "to", name: hubs[c.to], stop: last.name, at: c.end, gap: mins(c.end) - mins(last.end),
      need: hubMargin(c, "to", docOf(last)), url: `https://map.kakao.com/?sName=${q(last.name)}&eName=${q(hubs[c.to])}`, ...guide(c.to, last) });
  }
  return out;
}
