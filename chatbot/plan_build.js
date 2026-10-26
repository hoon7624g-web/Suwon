// The course planner's own ground rules, day builder and the check before the model (operator 2026-10-18: '이런 거 좀
// 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게 하라니까. 문제가 있으면 아예 생성 버튼 누르는 단계에서 지적을 하고'):
//   - planFlags: what is wrong with a plan, each with the day and stop it is at (planner.verify's flags, word for word);
//   - buildDay: a whole day from the site's data alone — or around the stops a day already has (the model's, kept in
//     their order) — that passes every check: places open that date by the data, inside their hours and the reader's,
//     the picked needs the data says fit (a visit's data 'ok'), at most one outdoor visit on a rainy day, a meal in its
//     window, no empty stretch, the code's margin on every leg, the station's margins, a stay at the end of a night;
//   - buildPlan: every day of the trip that way, no place twice;
//   - preflight: before any model call, whether such a plan exists; if not, the reasons in the reader's words and the
//     changes to the conditions that make one (each change checked).
// Facts only from the site's data: a stop is a place page; a time is a margin from straight-line distance, never a
// travel time; a place's day and hours are knowledge.checkPlan's reading (plan_geo.dayInfo).
import { city, hubName, hubNames, regionWord } from "./city.js";
import { farFloor, walkOnly } from "./knowledge.js";
import { NEEDS, tripDates } from "./plan_prompt.js";
import { planFees } from "./plan_fees.js";
import {
  CAMP, HARD, hardNeeds, KEEP_MIN, MEAL_KEEP, MEAL_MIN, SOFT_MIN, STAY_NEAR, STOPS_MAX, cap, codeLeast, dateWords, dayInfo, eul, farOnes, fitsHours, floorOf, gOf, hardState, hhmm, hubLegs,
  breakOf, iga, ro, inBreak, isOutdoor, isTaken, lastPoint, legFloor, legMargin, stretchMax, marginOf, metres, mins, placesOf, regionOf,
} from "./plan_geo.js";
import {
  HUB_MARGIN, IDLE, MEAL_APART, MEAL_LONG, MEALS, PREF_TYPES, completeness, hubMargin, eatsElsewhere, eveningFrom, eatsWords, hm, isCafe, isMeal, keptMeal, likeWords, liked, mealIn, mealRoles, mealSlot, needAt, prefFits, readerDay, span, spans, wantsOther,
} from "./plan_state.js";

// a stop the code put in (by: 'site'), swapped in (by: 'swap') or moved (a night's stay: moved)
export const changed = (s) => !!(s.by || s.moved);

const outdoorVisit = (kb, s) => s.role === "visit" && isOutdoor((kb.docs[s.page] || {}).f || {});
/** The outdoor visits of day i a rainy day keeps past its one (operator 2026-10-23 — '히로쓰가옥도 넣어 줘' on a 비 와도
 *  실내 위주 trip came back with an indoor place in its stead, since the day had another outdoor stop): a place the
 *  edit asked for (s.asked — new to the edit, readSubmit), and, on an edit, the outdoor visits of the reader's own page
 *  that day when it has more than one (only an earlier request keeps more: the next edit keeps them too) or that the
 *  page marks asked (x.asked: true — the mark makePlan puts on a rainy day's asked outdoor visit and the page sends
 *  back with its next edit: review 2026-10-23, 'OO공원 넣어 줘' then 'OO호수공원도 넣어 줘' swapped OO공원 away). The
 *  others go first (planner.settle 2, cleanSeeds); every outdoor visit over the one being asked for, none is flagged.
 *  (s) → boolean. */
export function rainAsked(kb, edit, i) {
  const own = edit && edit.plan.days[i] ? edit.plan.days[i].stops : [];
  const out = own.map((x) => ({ ...x, page: (kb.keyFor && kb.keyFor(x.page)) || x.page })).filter((x) => outdoorVisit(kb, x));
  const before = new Set(out.filter((x) => out.length > 1 || x.asked === true).map((x) => x.page));
  return (s) => !!s.asked || before.has(s.page);
}
/** Day d's outdoor visits on a rainy day: {all, asked} (rainAsked), or null when the rain is not a need. */
export function rainOutdoor(d, i, c, kb, edit) {
  if (!c.needs.includes("rain")) return null;
  const all = d.stops.filter((s) => outdoorVisit(kb, s));
  const asked = rainAsked(kb, edit, i);
  return { all, asked: all.filter(asked) };
}

/** What is wrong with a plan by the site's data and the reader's conditions — the same rules and words as
 *  planner.verify: {days: [checkPlan result], list: [{day, kind, text, j?, meal?}], fees, hubs, complete}. kind:
 *  'closed' | 'hours' (a stop, j), 'leg' (the leg from stop j), 'start' | 'end' (a stop before the reader's start
 *  or after their end, j), 'stay-missing', 'stay-mid' | 'stay-ci' | 'stay-last' (j: a stay on the trip's last day),
 *  'stay-two' (j: a second stay that night), 'role' (j: a role that is not what the place is), 'need' (j: the data
 *  says 'no' to a hard need the reader picked), 'many' (more than STOPS_MAX stops), 'rain',
 *  'budget', 'hub-from' | 'hub-to' (less than the hub's margin, plan_state.hubMargin), 'meal' (meal: lunch | dinner), 'gap'. day: the day's
 *  index, or -1 for the whole trip. */
export function planFlags(plan, c, kb, edit = null) {
  const list = [];
  const days = plan.days.map((d, i) => {
    const r = kb.checkPlan({ date: d.date, stops: d.stops.map((s) => ({ page: s.page, start: s.start, end: s.end })), move: c.move });
    // checkPlan's flags in its own order: each stop's, then each leg's
    let n = 0;
    r.stops.forEach((st, j) => {
      // (a stop between two sessions of the day or past one's last entry — '1회차(09:30~13:00)·2회차(14:00~17:30) 사이':
      // the break repair moves it into a session, as for a break the value names)
      const s = d.stops[j] || {};
      const gap = breakOf((kb.docs[s.page] || {}).f || {}, mins(s.start), mins(s.end));
      for (const t of st.flags || []) {
        const kind = st.day === "closed" || /격주/u.test(t) ? "closed" : gap && gap[3] && /회차|운영 시간/u.test(t) ? "break" : "hours";
        list.push({ day: i, j, kind, text: `${i + 1}일차 ${r.flags[n]}` });
        n += 1;
      }
    });
    for (const l of r.legs) {
      if (!l.flag) continue;
      list.push({ day: i, j: l.from, kind: "leg", text: `${i + 1}일차 ${r.flags[n]}` });
      n += 1;
    }
    // a stop in a break of the place's day ('브레이크타임 15:00~17:00', a place's '점심시간 12:00~13:00') — round 7: the
    // check read none (a lunch at 15:20 in 아리랑's 15:00–17:00, a visit over 구 조선식량영단 OO출장소's 점심시간)
    d.stops.forEach((s, j) => {
      if (s.role === "stay" || mins(s.start) === null || mins(s.end) === null) return;
      // (the gaps between sessions are checkPlan's: a visit inside one session is no fault)
      const br = breakOf((kb.docs[s.page] || {}).f || {}, mins(s.start), mins(s.end), { sessions: false });
      if (br) list.push({ day: i, j, kind: "break", text: `${i + 1}일차 ${s.name}: ${br[2] ? `${br[2]} 기준 ` : ""}쉬는 시간 ${hhmm(br[0])}~${hhmm(br[1])}에 걸친다 — 앞이나 뒤로 옮기거나 줄인다` });
    });
    const lastDay = i === plan.days.length - 1;
    // the reader's 하루 시작·하루 끝 hold every day, for every stop but the night's stay (2026-10-24 I07: a 2-day trip
    // 10:00~18:00 passed with 금강보행교 18:00–19:00 on the first day and 08:00–09:00 on the second)
    d.stops.forEach((s, j) => {
      if (s.role === "stay") return;
      if (mins(s.start) < mins(c.start)) list.push({ day: i, j, kind: "start", text: `${i + 1}일차 ${s.name}: 독자가 정한 시작 ${c.start}보다 이르다` });
      if (mins(s.end) > mins(c.end)) list.push({ day: i, j, kind: "end", text: `${i + 1}일차 ${s.name}: 독자가 정한 끝 ${c.end}보다 늦다` });
    });
    // the hard needs the reader picked: a stop the data says does not fit one (round-5 verifier: a paid museum the
    // code put in for '입장료 없는 곳' was sent)
    if (hardNeeds(c).length) {
      d.stops.forEach((s, j) => {
        const f = (kb.docs[s.page] || {}).f || {};
        if (hardState(c, f, s.role) !== "no") return;
        const need = hardNeeds(c).find((n) => hardState({ ...c, needs: [n] }, f, s.role) === "no");
        list.push({ day: i, j, kind: "need", text: `${i + 1}일차 ${s.name}: 고른 조건 '${NEEDS[need]}'에 맞지 않는다고 자료에 있다 — 맞는 곳으로 바꾼다` });
      });
    }
    if (d.stops.length > STOPS_MAX) list.push({ day: i, kind: "many", text: `${i + 1}일차: 장소가 ${d.stops.length}곳 — 하루 ${STOPS_MAX}곳까지로 줄인다` });
    // a stay on the trip's last day: no night follows it (round-5 verifier: a hotel at 17:30–19:30 after an 18:00 end)
    if (lastDay) {
      d.stops.forEach((s, j) => {
        if (s.role === "stay") list.push({ day: i, j, kind: "stay-last", text: `${i + 1}일차 ${s.name}: 마지막 날에는 묵는 곳이 없다 — 일정에서 뺀다` });
      });
    }
    if (!lastDay && !d.stops.some((s) => s.role === "stay")) list.push({ day: i, kind: "stay-missing", text: `${i + 1}일차: 묵을 숙소(role stay)가 없다` });
    // one stay a night; a role that is what the place is (a stay page as the stay, a meal or a café at a food page)
    d.stops.forEach((s, j) => {
      const kd = ((kb.docs[s.page] || {}).f || {}).kd;
      if (s.role === "stay" && d.stops.slice(0, j).some((x) => x.role === "stay")) list.push({ day: i, j, kind: "stay-two", text: `${i + 1}일차 ${s.name}: 그날 밤 숙소가 이미 있다 — 일정에서 뺀다` });
      if ((kd === "stay") !== (s.role === "stay") || ((s.role === "meal" || s.role === "cafe") && kd !== "food")) {
        list.push({ day: i, j, kind: "role", text: `${i + 1}일차 ${s.name}: role ${s.role}이 장소의 종류와 맞지 않는다 — 일정에서 뺀다` });
      }
    });
    // a night's stay is where the day ends: never ahead of another stop, never before its check-in time (repair 0
    // moves it when it can)
    d.stops.forEach((s, j) => {
      if (lastDay || s.role !== "stay") return;
      const ci = ((kb.docs[s.page] || {}).f || {}).ci;
      if (d.stops.slice(j + 1).some((x) => x.role !== "stay")) list.push({ day: i, j, kind: "stay-mid", text: `${i + 1}일차 ${s.name}: 밤 숙소인데 그날 마지막 장소가 아니다 — 그날 마지막에 둔다` });
      else if (ci && mins(s.start) < mins(ci)) list.push({ day: i, j, kind: "stay-ci", text: `${i + 1}일차 ${s.name}: 밤 숙소가 체크인 ${ci}보다 이른 ${s.start}에 시작한다 — 체크인 뒤로 둔다` });
    });
    // a leg next to a stop the code put in, swapped in or moved holds the code's own margin (marginOf; repair 7 widens
    // it when it can)
    for (const l of r.legs) {
      const a = d.stops[l.from], b = d.stops[l.to];
      if (l.flag || l.gap === null || a.role === "stay" || (!changed(a) && !changed(b))) continue;
      const need = marginOf(a.page, b.page, c, kb);
      if (l.gap >= need) continue;
      l.flag = `사이트가 넣거나 옮긴 곳이 있는 구간인데 여유 ${l.gap}분 — 계획 여유 ${need}분보다 짧음`;
      list.push({ day: i, j: l.from, kind: "leg", text: `${i + 1}일차 ${l.from + 1}→${l.to + 1}번 ${a.name} → ${b.name}: ${l.flag} — 여유를 늘리거나 가까운 곳으로 바꾼다` });
    }
    // (the outdoor places the reader asked for do not count against the one: rainAsked)
    const rain = rainOutdoor(d, i, c, kb, edit);
    if (rain && rain.all.length > Math.max(1, rain.asked.length)) {
      const names = (xs) => xs.map((s) => s.name).join("·");
      list.push({ day: i, kind: "rain", text: `${i + 1}일차: '비 와도 실내 위주'인데 야외 장소가 ${rain.all.length}곳(${names(rain.all)}) — ${rain.asked.length
        ? `독자가 요청한 곳(${names(rain.asked)})은 두고, 그 밖의 야외 장소(${names(rain.all.filter((s) => !rain.asked.includes(s)))})는 실내 장소로 바꾼다`
        : "짧은 야외는 하루 한 곳까지"}` });
    }
    return r;
  });
  const fees = planFees(plan.days, c, kb, c.budget);
  if (fees.verdict === "over") {
    list.push({ day: -1, kind: "budget", text: `입장료(확인된 것만) ${fees.known.toLocaleString("en-US")}원이 예산 ${c.budget.toLocaleString("en-US")}원을 넘는다 — 무료이거나 더 싼 곳으로 바꾼다` });
  }
  const hubs = hubLegs(plan, c, hubNames(), kb);
  // the station or terminal: its margin after the start, before the end (round-5 verifier: a first stop a minute after
  // the train passed) — HUB_MARGIN, more for a stop in another 권역 (plan_state.hubMargin; review 2026-10-22: 섬
  // 30 minutes after 역 by bus passed)
  for (const h of hubs) {
    if (h.gap >= h.need) continue;
    list.push(h.dir === "from"
      ? { day: 0, kind: "hub-from", text: `${h.name} ${h.at} 출발인데 첫 장소 ${h.stop}${iga(h.stop)} ${h.at} 뒤 ${h.need}분 안에 시작한다(${h.gap}분) — 출발지에서 오는 여유를 둔다` }
      : { day: plan.days.length - 1, kind: "hub-to", text: `${h.name}에 ${h.at}까지 가야 하는데 마지막 장소 ${h.stop}${iga(h.stop)} ${h.at} 전 ${h.need}분 안에 끝난다(${h.gap}분) — 돌아갈 여유를 둔다` });
  }
  // (a long ride is not empty time: a stretch over a leg of an hour's margin or more — 섬 권역 and the town without a
  // car — is what is left of it after the part of the margin past the least any leg has; shorter legs count whole, as
  // before. Live check 2026-10-19: a dinner moved near a stay 28 km away after an island café read the 2-hour ride as
  // a hole)
  const least = legMargin(null, c.move);
  const complete = completeness(plan, c, kb, edit, (a, b) => {
    const m = marginOf(a.page, b.page, c, kb);
    return m >= IDLE / 2 ? m - least : 0;
  });
  for (const m of complete.meals.filter((x) => x.state === "missing")) {
    const w = MEALS[m.kind];
    list.push({ day: m.day, kind: "meal", meal: m.kind,
      text: `${m.day + 1}일차: ${w.label} 시간(${hhmm(w.from)}~${hhmm(w.to)})이 일정 안인데 식사할 곳이 없다${m.note ? `(${m.note})` : ""} — 그 시간에 여는 음식점을 넣는다` });
  }
  for (const g of complete.gaps) {
    list.push({ day: g.day, kind: "gap", from: hm(g.from), to: hm(g.to), text: `${g.day + 1}일차: ${g.from}~${g.to} ${span(g.minutes)} 동안 들르는 곳이 없다 — 가까운 장소를 넣거나 앞뒤 장소를 늘린다` });
  }
  return { days, list, fees, hubs, complete };
}

// ------------------------------------------------------------------ the day builder
const VISIT_MIN = 45;      // a visit the code puts in: at least this, 90 when there is more to fill, up to 120 to fill a stretch whole
const VISIT_WANT = 90;
const VISIT_MAX = 120;
const CAFE_MIN = 30;
const CAFE_MAX = 60;
const FILL_FROM = 70;      // an empty stretch longer than this gets a place when one fits (the check allows IDLE)
const STAY_LATEST = 23 * 60 + 29;
const ceil5 = (x) => Math.ceil(x / 5) * 5;
const floor5 = (x) => Math.floor(x / 5) * 5;
// straight lines a place the builder adds is looked for in from the stop next to it, nearest first, ending at the cap
// (round 6, plan_geo.CAP: 3 km without a car, 8 km by car — before, 6 km and 15 km)
const RADII = { transit: [1500], car: [3000, 6000] };
const radii = (c) => [...RADII[c.move === "car" ? "car" : "transit"].filter((r) => r < cap(c)), cap(c)];
// the rings past the cap (the old ones: 6 km without a car, 15 km by car), for a day — or a trip — nothing within the
// cap builds (opts.wide, buildPlan's last try): only where the alternative is no plan for these conditions at all
// (by car 20 km last: the far islands to the nearest restaurant open for a dinner off them, OO항, is 18 km — live
// check 2026-10-19, an island day on a Tuesday)
export const WIDE = { transit: [1500, 3000, 6000], car: [3000, 6000, 15000, 20000] };
// (without a car in a city whose data names no bus for its places, no ring past a walk: knowledge.walkOnly)
export const wideOf = (c) => (c.walk ? [cap(c)] : WIDE[c.move === "car" ? "car" : "transit"]);
const ringsOf = (ctx) => (ctx.wide ? wideOf(ctx.c) : radii(ctx.c));
// the least a visit the builder puts in gets: VISIT_MIN, or its kind's floor when that is more (a museum an hour)
const visitMin = (x) => Math.max(VISIT_MIN, floorOf("visit", x.doc));

// the hours a place keeps that date: the latest opening, the earliest closing (a line that closes the same day), the
// earliest last entry
export function windowOf(info) {
  let open = 0, close = 24 * 60, last = Infinity;
  for (const h of info.hours) {
    open = Math.max(open, h.open);
    if (h.close > h.open) close = Math.min(close, h.close);
    if (h.last !== null) last = Math.min(last, h.last);
  }
  return { open, close, last };
}
// the places a day may use on a date, once per knowledge base and date: open or to check by the data, hours read
const POOLS = new WeakMap();
function poolOf(kb, date) {
  if (!POOLS.has(kb)) POOLS.set(kb, new Map());
  const byDate = POOLS.get(kb);
  if (byDate.has(date)) return byDate.get(date);
  const pool = { visits: [], meals: [], cafes: [], stays: [] };
  for (const { page, doc } of placesOf(kb)) {
    const f = doc.f;
    if (f.kd === "stay") {
      pool.stays.push({ page, doc, f, g: f.g, camp: CAMP.test(f.ty || "") });
      continue;
    }
    const info = dayInfo(kb, date, page);
    if (!info.state || info.state === "closed" || !info.read) continue;
    const x = { page, doc, f, g: f.g, info, win: windowOf(info), region: regionOf(doc) };
    if (f.kd === "attraction") pool.visits.push(x);
    else if (f.kd === "food" && isMeal(doc)) pool.meals.push(x);
    else if (f.kd === "food" && isCafe(doc)) pool.cafes.push(x);
  }
  byDate.set(date, pool);
  return pool;
}
const fits = (x, a, b) => a >= x.win.open && b <= x.win.close && a <= x.win.last && b > a && !inBreak(x.f, a, b);

// the least a seed may be shortened to (plan_geo.keepOf, in minutes, round 6): a place the code put in its codeLeast
// (its kind's floor, never under SWAP_MIN), one of the model's its kind's floor or its own length when that is less;
// len: the length it is held to (the seed as given, before the builder moved it)
// (a meal an edit left as the reader's page has it — s.kept, planner.markKept — keeps its whole length)
const keepSeed = (s, kb, len = s.b - s.a) => (s.role === "stay" ? KEEP_MIN : s.kept ? len : s.by ? codeLeast(s.role, kb.docs[s.page]) : Math.min(floorOf(s.role, kb.docs[s.page]), len));
// the stops a day may still take before its night's stay (STOPS_MAX counts the stay)
const roomLeft = (ctx, stops) => STOPS_MAX - (ctx.lastDay ? 0 : 1) - stops.filter((s) => s.role !== "stay").length;
// the visits a day the builder makes must hold (round 6): two when the reader's day (lo–hi) is VISITS_LONG minutes or
// more, else one; a day around the model's own stops (seed) one — a seed of the code's stops only (a day of the code's
// plan built again) is no seed of the model's: the same two (round-6 verifier: such a day came back as 1 visit and 3
// cafés in 9 hours)
export const VISITS_LONG = 360;
const visitsWanted = (ctx, seed = []) => (seed.some((s) => !s.by) ? 1 : ctx.hi - ctx.lo >= VISITS_LONG ? 2 : 1);

/** The builder's stops from k on moved `by` minutes whole (dir 1: k and the ones after it later; -1: k and the ones
 *  before it earlier), each within its hours that date and the day's bounds, a meal where it was (plan_state.mealSlot),
 *  as far as the stretches next to them take it up — each leg past the last one moved keeps its margin, or what it had
 *  when that was less (planner.shiftPlan's rule — round 6: rather than cut a stop below its floor). Returns the moves
 *  [[stop, a, b]] (not made), or null. A night's stay is not among the builder's stops until the day's end. */
function shiftStops(ctx, stops, k, by, dir) {
  const { c, kb, date } = ctx;
  const lower = ctx.first ? ctx.lo : ctx.bottom, upper = ctx.lastDay ? ctx.hi : ctx.top;
  const moves = [];
  let need = by;
  for (let q = k; q >= 0 && q < stops.length && need > 0; q += dir) {
    const s = stops[q];
    if (s.role === "stay" || s.kept) return null;   // (a meal an edit kept never moves: planner.markKept)
    const a = s.a + dir * need, b = s.b + dir * need;
    const w = windowOf(dayInfo(kb, date, s.page));
    if (a < Math.max(w.open, lower) || b > Math.min(w.close, upper) || a > w.last || inBreak((kb.docs[s.page] || {}).f || {}, a, b)
      || (s.role === "meal" && mealSlot(s.a, s.b) !== mealSlot(a, b))) return null;
    moves.push([s, a, b]);
    const nx = stops[q + dir];
    if (!nx) return moves;
    const gap = dir > 0 ? nx.a - s.b : s.a - nx.b;
    need = Math.max(0, need - (gap - Math.min(gap, dir > 0 ? marginOf(s.page, nx.page, c, kb) : marginOf(nx.page, s.page, c, kb))));
  }
  return need > 0 ? null : moves;
}

/** The stops a day already has, cleaned so that each holds on its own and with the ones next to it: a place closed
 *  that day, a stay on the trip's last day ahead of a stop, a need the data says 'no', a second outdoor visit in the
 *  rain go; times are cut to the place's hours and the reader's, then each leg gets its margin — the earlier stop
 *  ends sooner, the later starts later, each keeping keepSeed — or, when it cannot, the stop the code put in goes
 *  first, else the one farther from the rest. Returns [{...stop, a, b}] in minutes, and what went. */
function cleanSeeds(ctx, seeds) {
  const { c, kb, date } = ctx;
  const out = [];
  const gone = [];
  let outdoor = 0;
  // (an outdoor place the reader asked for stays: then every other outdoor visit goes — rainAsked)
  const asked = rainAsked(kb, ctx.edit, ctx.i);
  const askedOut = c.needs.includes("rain") && seeds.some((s) => outdoorVisit(kb, s) && asked(s));
  for (const s of seeds) {
    const f = (kb.docs[s.page] || {}).f || {};
    if (s.role === "stay") continue;
    let a = hm(s.start), b = hm(s.end);
    const info = dayInfo(kb, date, s.page);
    if (info.state === "closed" || ctx.taken.has(s.page) || out.some((x) => x.page === s.page) || hardState(c, f, s.role) === "no") {
      gone.push(s);
      continue;
    }
    if (c.needs.includes("rain") && s.role === "visit" && isOutdoor(f) && !asked(s) && (askedOut || (outdoor += 1) > 1)) {
      gone.push(s);
      continue;
    }
    // the place's hours that date (only the lines the check reads) and the reader's bounds
    const w = windowOf(info);
    const len = b - a;
    const lo = Math.max(w.open, ctx.first ? ctx.lo : 0), hi = Math.min(w.close, ctx.lastDay ? ctx.hi : 24 * 60);
    const keep = keepSeed(s, kb, len);
    a = Math.max(a, lo);
    b = Math.min(b, hi);
    if (a > w.last) a = b;   // past the last entry
    // a cut below its floor (round 6): the stop moves whole into the hours instead, when it fits there
    if (b - a < keep) {
      const sa = hm(s.start) < lo ? lo : hi - len;
      if (sa >= lo && sa + len <= hi && sa <= w.last && !inBreak(f, sa, sa + len)) [a, b] = [sa, sa + len];
    }
    if (b - a < keep || inBreak(f, a, b)) {
      gone.push(s);
      continue;
    }
    out.push({ ...s, a, b, len });
  }
  // the meals as planner.tidyMeals leaves them (round 7): a café as a meal a café stop, no meal over MEAL_LONG, no
  // meal beyond the day's lunch and dinner
  // (a meal an edit left as it was stays as it is: plan_state.keptMeal; the place the reader's words name is the day's
  // meal before another on its side — round-6 verifier)
  const kept = keptMeal(ctx.edit, ctx.i, kb);
  const likes = likeWords(c.note, ctx.edit && ctx.edit.request);
  for (const s of out) {
    if (s.role === "meal" && isCafe(kb.docs[s.page])) s.role = "cafe";
    if (s.role === "meal" && s.b - s.a > MEAL_LONG && !kept(s)) s.b = s.a + MEAL_LONG;
  }
  const view = out.map((s) => ({ ...s, start: hhmm(s.a), end: hhmm(s.b), seed: s }));
  const rank = (x) => (kept(x.seed) ? 0 : liked(kb.docs[x.page], likes) ? 1 : 2);
  for (const x of mealRoles(view, kb, mealsFor(ctx, out), wantsOther(c.note, ctx.edit && ctx.edit.request), rank).extra.filter((y) => !kept(y.seed))) {
    gone.push(x.seed);
    out.splice(out.indexOf(x.seed), 1);
  }
  // no more than the day holds with its night's stay (STOPS_MAX): the code's own shortest go first, then the shortest
  // (a place new to an edit — s.asked — goes last: planner.readSubmit)
  while (roomLeft(ctx, out) < 0) {
    const k = out.reduce((best, x, n) => (best < 0 || Number(!x.asked) > Number(!out[best].asked)
      || (!x.asked === !out[best].asked && (Number(!!x.by) > Number(!!out[best].by)
        || (!!x.by === !!out[best].by && x.role !== "meal" && (out[best].role === "meal" || x.b - x.a < out[best].b - out[best].a)))) ? n : best), -1);
    gone.push(...out.splice(k, 1));
  }
  const shift = (k, by, dir) => {
    const moves = shiftStops(ctx, out, k, by, dir);
    for (const [s, a, b] of moves || []) Object.assign(s, { a, b });
    return !!moves;
  };
  // the legs: from the margin down to what the check allows (the code's own stops keep the whole margin)
  for (let j = 0; j + 1 < out.length;) {
    const x = out[j], y = out[j + 1];
    const need = marginOf(x.page, y.page, c, kb);
    const least = changed(x) || changed(y) ? need : legFloor(x.page, y.page, c, kb);
    let ok = y.a - x.b >= least;
    for (let g = need; !ok && g >= least; g -= 5) {
      if (y.a - x.b >= g) { ok = true; break; }
      const wy = windowOf(dayInfo(kb, date, y.page));
      // the earlier one ends sooner, then the later one starts later (each keeping its floor), then the later one and
      // the ones after it move later whole, then the earlier one and the ones before it earlier
      if (y.a - g - x.a >= keepSeed(x, kb, x.len)) { x.b = Math.min(x.b, y.a - g); ok = true; break; }
      const ny = x.b + g;
      if (y.b - ny >= keepSeed(y, kb, y.len) && ny <= wy.last && !inBreak((kb.docs[y.page] || {}).f || {}, ny, y.b)) { y.a = ny; ok = true; break; }
      if (shift(j + 1, x.b + g - y.a, 1) || shift(j, x.b + g - y.a, -1)) { ok = true; break; }
    }
    if (ok) { j += 1; continue; }
    // one of them goes: the code's own first, else the one farther from its other neighbour
    const far = (s, other) => (gOf(kb, s.page) && other && gOf(kb, other.page) ? metres(gOf(kb, s.page), gOf(kb, other.page)) : 0);
    // (a place new to an edit and a meal an edit kept go last: planner.readSubmit, planner.markKept)
    const stays = (s) => (s.asked ? 1 : 0) + (s.kept ? 2 : 0);
    const dropY = stays(x) !== stays(y) ? stays(y) < stays(x) : changed(y) && !changed(x) ? true : changed(x) && !changed(y) ? false : far(y, out[j + 2]) >= far(x, out[j - 1]);
    gone.push(...out.splice(dropY ? j + 1 : j, 1));
    if (j > 0) j -= 1;
  }
  return { stops: out, gone };
}

// a place for the reader's likings: 0 fits one they picked (the data can tell), 1 not
const likeRank = (ctx, x) => {
  const likes = ctx.c.prefs.filter((p) => PREF_TYPES[p] || city().prefRegions[p] || city().prefTypes[p]);
  return likes.length && likes.some((p) => prefFits(p, x.doc)) ? 0 : likes.length ? 1 : 0;
};
// rain: an indoor type first, a typed place next, a place with no type, an outdoor one last
const rainRank = (ctx, x) => {
  if (!ctx.c.needs.includes("rain")) return 0;
  const st = needAt("rain", x.f, "visit").state;
  return st === "ok" ? 0 : st === "unknown" ? (x.f.ty ? 1 : 2) : 3;
};
const feeKnown = (x) => (x.f.fee && (x.f.fee.free || x.f.fee.tab) ? 0 : 1);
function rank(ctx, x) {
  return [likeRank(ctx, x), x.info.state === "open" ? 0 : 1, rainRank(ctx, x), feeKnown(x)];
}
const byRank = (p, q) => {
  for (let k = 0; k < p.r.length; k += 1) if (p.r[k] !== q.r[k]) return p.r[k] - q.r[k];
  return p.m - q.m || (p.x.page < q.x.page ? -1 : 1);
};

// the day as checkPlan reads it: the builder's stops in minutes → the plan's stops
const asStops = (stops) => stops.map((s) => {
  const { a, b, len, ...rest } = s;   // (len: the length a seed is held to — the builder's own)
  return { ...rest, start: hhmm(a), end: hhmm(b) };
});
// a plan with day i as the builder has it (for the fee and the check)
const withDay = (ctx, stops) => ({ ...ctx.plan, days: ctx.plan.days.map((d, k) => (k === ctx.i ? { date: ctx.date, stops: asStops(stops) } : d)) });
function feeOk(ctx, stops) {
  const { c, kb } = ctx;
  if (c.budget === null || c.budget === undefined) return true;
  const f = planFees(withDay(ctx, stops).days, c, kb, c.budget);
  return f.verdict !== "over";
}
function outdoorUsed(ctx, stops) {
  return stops.some((s) => s.role === "visit" && isOutdoor((ctx.kb.docs[s.page] || {}).f || {}));
}
// whether a place may go in as a visit the code adds: not in the trip, every hard need the data says fits, the
// rain's one outdoor visit, its fee within the budget (checked when placed)
function visitOk(ctx, stops, x) {
  if (isTaken(ctx.kb, ctx.taken, x.page) || isTaken(ctx.kb, new Set(stops.map((s) => s.page)), x.page)) return false;
  if (hardState(ctx.c, x.f, "visit") !== "ok") return false;
  if (ctx.c.needs.includes("rain") && isOutdoor(x.f) && outdoorUsed(ctx, stops)) return false;
  return true;
}
// a restaurant may go in when it is in no day of the trip and the data does not say 'no' to a need (round-5: the spec's
// 'no repeats across days'); again: one of another day too, when none of the trip's own fits (live check 2026-10-19:
// the far islands have three restaurants with hours — placeMeal tries it last)
const mealOk = (ctx, stops, x, again = false) => (again || !ctx.taken.has(x.page)) && !stops.some((s) => s.page === x.page) && hardState(ctx.c, x.f, "meal") !== "no";

/** A visit for the stretch between stops k-1 and k (P, N; either may be missing — the day's ends): the place nearest
 *  the stop next to it that fits, open from the leg's margin after P (or from the stretch's start) until the margin
 *  before N (or the stretch's end) for VISIT_MIN–VISIT_MAX minutes. dir 'before': it ends at the margin before N. */
function pickVisit(ctx, stops, k, from, until, cafe = false) {
  const { c, kb } = ctx;
  const P = stops[k - 1] || null, N = stops[k] || null;
  const at = (P && gOf(kb, P.page)) || (N && gOf(kb, N.page)) || ctx.anchor;
  const dir = P ? "after" : "before";
  const list = cafe ? ctx.pool.cafes : ctx.pool.visits;
  const role = cafe ? "cafe" : "visit";
  for (const R of at ? ringsOf(ctx) : [Infinity]) {
    const cands = list.filter((x) => (cafe ? mealOk(ctx, stops, x) : visitOk(ctx, stops, x)))
      .map((x) => ({ x, m: at ? metres(at, x.g) : 0 }))
      .filter((y) => y.m <= R)
      .map((y) => ({ ...y, r: at ? rank(ctx, y.x) : [...rank(ctx, y.x), -density(ctx, y.x)] }))
      .sort(byRank)
      .slice(0, 40);
    for (const { x } of cands) {
      const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
      const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
      const a0 = ceil5(Math.max(from + mP, x.win.open));
      const bMax = floor5(Math.min(until - mN, x.win.close));
      const room = bMax - a0;
      const min = cafe ? CAFE_MIN : visitMin(x);
      if (room < min || a0 > x.win.last) continue;
      // (frugal: a trip whose later days run short of places spends fewer — longer visits, 2 hours, up to 3 to fill)
      let d = cafe ? Math.min(CAFE_MAX, room) : ctx.frugal ? Math.min(room, room <= 180 ? room : 120) : room <= VISIT_MAX ? room : VISIT_WANT;
      d = floor5(d);
      let a = a0, b = a0 + d;
      if (dir === "before") { b = bMax; a = Math.max(a0, b - d); }
      if (!fits(x, a, b)) continue;
      const stop = { page: x.page, name: x.doc.t, a, b, role, why: "", by: "site" };
      const next = [...stops.slice(0, k), stop, ...stops.slice(k)];
      if (x.f.fee && x.f.fee.tab && !feeOk(ctx, next)) continue;
      return { stop, next };
    }
  }
  return null;
}
// how many places to visit or eat at are near a place (where a day without a stop of its own starts)
function density(ctx, x) {
  const R = radii(ctx.c)[0];
  return [...ctx.pool.visits, ...ctx.pool.meals].filter((y) => metres(x.g, y.g) <= R).length;
}

/** The stretches of the day with no stop, as the check reads them (plan_state.idleGaps on the reader's day; none past
 *  the evening after the day's dinner: plan_state.eveningFrom). */
function stretches(ctx, stops) {
  const out = [];
  let t = ctx.lo;
  stops.forEach((s, k) => {
    if (s.a > t) out.push({ k, from: t, to: s.a });
    t = Math.max(t, s.b);
  });
  const dinner = mealIn(asStops(stops), MEALS.dinner, ctx.kb);
  const hi = Math.min(ctx.hi, eveningFrom(dinner && [hm(dinner.start), hm(dinner.end)]));
  if (hi > t) out.push({ k: stops.length, from: t, to: hi });
  return out;
}

/** Each stretch longer than FILL_FROM gets the visits that fit, nearest the stop before it first; a stretch longer
 *  than IDLE that nothing fits gets a café, then the stop next to it lengthened (within its hours, under
 *  plan_geo.stretchMax). Changes stops; returns whether every stretch is within IDLE. */
function fillStretches(ctx, stops) {
  const dead = new Set();
  // frugal: the stops lengthen first (to FILL_FROM), then the places go in
  if (ctx.frugal) lengthen(ctx, stops, FILL_FROM);
  for (let guard = 0; guard < 24 && roomLeft(ctx, stops) > 0; guard += 1) {
    const g = stretches(ctx, stops).find((x) => x.to - x.from > FILL_FROM && !dead.has(`${x.from}-${x.to}`));
    if (!g) break;
    const pick = pickVisit(ctx, stops, g.k, g.from, g.to) || (g.to - g.from > IDLE ? pickVisit(ctx, stops, g.k, g.from, g.to, true) : null);
    if (pick) stops.splice(0, stops.length, ...pick.next);
    else dead.add(`${g.from}-${g.to}`);
  }
  // what is still longer than IDLE: lengthen the stop before it (then the one after it)
  lengthen(ctx, stops);
  return stretches(ctx, stops).every((x) => x.to - x.from <= IDLE);
}
// each stretch longer than `most` (IDLE): the stop before it ends later (its hours, plan_geo.stretchMax), then the one
// after it starts sooner
function lengthen(ctx, stops, most = IDLE) {
  for (const g of stretches(ctx, stops).filter((x) => x.to - x.from > most)) {
    const P = stops[g.k - 1], N = stops[g.k];
    let need = g.to - g.from - most;
    if (P && P.role !== "stay" && !P.kept) {
      const w = windowOf(dayInfo(ctx.kb, ctx.date, P.page));
      const lim = Math.min(w.close, P.a + stretchMax(P), N ? N.a - marginOf(P.page, N.page, ctx.c, ctx.kb) : g.to);
      let nb = Math.min(lim, P.b + need);
      // (a meal keeps its side and window: plan_state.mealSlot — round-6 final verifier)
      while (nb > P.b && P.role === "meal" && mealSlot(P.a, nb) !== mealSlot(P.a, P.b)) nb -= 5;
      if (nb > P.b && !inBreak((ctx.kb.docs[P.page] || {}).f || {}, P.a, nb)) { need -= nb - P.b; P.b = nb; }
    }
    if (need > 0 && N && N.role !== "stay" && !N.kept) {
      const w = windowOf(dayInfo(ctx.kb, ctx.date, N.page));
      const lim = Math.max(w.open, N.b - stretchMax(N), P ? P.b + marginOf(P.page, N.page, ctx.c, ctx.kb) : g.from, ctx.first ? ctx.lo : 0);
      let na = Math.max(lim, N.a - need);
      while (na < N.a && N.role === "meal" && mealSlot(na, N.b) !== mealSlot(N.a, N.b)) na += 5;
      if (na < N.a && na <= w.last && !inBreak((ctx.kb.docs[N.page] || {}).f || {}, na, N.b)) N.a = na;
    }
  }
}

/** A meal for the day (MEALS[kind]) where none is: every place between two stops (or the day's ends) the meal's window
 *  reaches, the restaurants nearest the stop before it (then after it), each start from the window's first to its
 *  last, nearest the aim first; the stop before may end sooner and the one after start later (each keeping its
 *  least: a meal 45, one the code added VISIT_MIN or its floor, one of the model's its floor — keepSeed, round 6). When
 *  no place has room, a visit inside the window — the code's own first — gives up its place. Of the places that fit,
 *  the one nearest the stop next to it in steps of 500 m comes first (round 6: moving the meal within its window before
 *  going farther), then one outside the meal's own window last, one that cuts nothing, an hour, the start nearest the
 *  aim. Changes stops; returns whether the meal went in. */
function placeMeal(ctx, stops, kind, depth = 0) {
  const { c, kb } = ctx;
  const m = MEALS[kind];
  const least = (s) => (s.kept ? s.b - s.a : s.role === "meal" ? Math.min(MEAL_KEEP, s.b - s.a) : s.by ? Math.max(keepSeed(s, kb), s.role === "visit" ? VISIT_MIN : 0) : keepSeed(s, kb, s.len));
  // a cut that leaves a stop under SOFT_MIN (or its own length) only where it cannot move whole (round-6 verifier)
  const soft = (s) => Math.max(least(s), Math.min(SOFT_MIN, s.len ?? s.b - s.a));
  // the starts a meal may take: its window (m.first–m.last), then any whose middle falls where the check counts that
  // meal (m.near) — an edit's dinner on a day that ends at 18:00 (round-5 verifier: such edits were refused)
  const early = ceil5(m.near[0] - MEAL_KEEP / 2), late = floor5(m.near[1] - MEAL_KEEP / 2 - 1);
  // never within MEAL_APART minutes, start to start, of another meal of the day (round 7 — planner.addMeal's rule)
  const meals = stops.filter((s) => s.role === "meal" && !isCafe(kb.docs[s.page])).map((s) => s.a);
  const apart = (s) => meals.every((x) => Math.abs(x - s) >= MEAL_APART);
  const search = (again, rings) => {
    let best = null;
    for (let k = 0; k <= stops.length && roomLeft(ctx, stops) > 0; k += 1) {
      const P = stops[k - 1] || null, N = stops[k] || null;
      // the day's ends: the reader's start on the first day (else the day may start earlier) and their end on the last
      // (else it runs to ctx.top — a night's stay follows it), as the check reads them
      const pLo = P ? P.a + least(P) : ctx.bottom;
      const nHi = N ? N.b - least(N) : ctx.top;
      const pSoft = P ? P.a + soft(P) : ctx.bottom, nSoft = N ? N.b - soft(N) : ctx.top;
      // (round 6) where cutting would take a stop below its floor, it moves whole instead — the stop before (and the
      // ones before it) earlier, the stop after (and the ones after it) later — when the day has room for that
      const moved = new Map();
      const move = (j, by, dir) => {
        const key = `${j}|${by}|${dir}`;
        if (!moved.has(key)) moved.set(key, shiftStops(ctx, stops, j, by, dir));
        return moved.get(key);
      };
      // a slot no meal fits even with the stops next to it cut to their least — when neither of them can move at all
      if ((!P || !move(k - 1, 5, -1)) && (!N || !move(k, 5, 1)) && Math.min(late, nHi - MEAL_KEEP) < Math.max(early, pLo)) continue;
      // the restaurants nearest the stop before the slot or the one after it (either may be far out)
      const pts = [P && gOf(kb, P.page), N && gOf(kb, N.page)].filter(Boolean);
      if (!pts.length && ctx.anchor) pts.push(ctx.anchor);
      const wN = N ? windowOf(dayInfo(kb, ctx.date, N.page)) : null;
      for (const R of pts.length ? rings : [Infinity]) {
        const cands = ctx.pool.meals.filter((x) => mealOk(ctx, stops, x, again)).map((x) => ({ x, m: pts.length ? Math.min(...pts.map((g) => metres(g, x.g))) : 0 }))
          .filter((y) => y.m <= R).sort((p, q) => p.m - q.m || (p.x.page < q.x.page ? -1 : 1)).slice(0, 25);
        for (const { x, m: dist } of cands) {
          const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
          const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
          // an hour, or 45 minutes where an hour does not fit
          for (const len of [MEAL_MIN, MEAL_KEEP]) {
            for (let s = early; s <= late; s += 5) {
              const mid = s + len / 2;
              if (mid < m.near[0] || mid >= m.near[1] || !apart(s) || !fits(x, s, s + len)) continue;
              let pEnd = P ? Math.min(P.b, s - mP) : null, movP = null, under = 0;
              if (P && pEnd < pSoft) {
                movP = move(k - 1, P.b - (s - mP), -1);
                if (movP) pEnd = P.b;
                else if (pEnd < pLo) continue;
                else under += 1;
              } else if (!P && s < ctx.bottom) continue;
              let nStart = N ? Math.max(N.a, s + len + mN) : null, movN = null;
              const nBad = (x) => x > nHi || x > wN.last || inBreak(((kb.docs[N.page] || {}).f) || {}, x, N.b);
              if (N && (nStart > nSoft || nBad(nStart))) {
                movN = move(k, s + len + mN - N.a, 1);
                if (movN) nStart = N.a;
                else if (nBad(nStart)) continue;
                else under += 1;
              } else if (!N && s + len > ctx.top) continue;
              const cut = (P ? P.b - pEnd : 0) + (N ? nStart - N.a : 0);
              const shifted = (movP ? P.b - (s - mP) : 0) + (movN ? s + len + mN - N.a : 0);
              const out = s < m.first || s > m.last ? 1e6 : 0;   // outside the meal's own window: only when nothing inside fits
              const cost = out + Math.floor(dist / 500) * 1e4 + (cut ? 300 + cut : 0) + (shifted ? 300 + shifted : 0) + under * 600 + (len < MEAL_MIN ? 300 : 0) + Math.abs(s - m.at);
              if (!best || cost < best.cost) best = { cost, k, x, s, len, pEnd, nStart, movP, movN };
            }
          }
        }
        if (best && best.k === k) break;   // the nearest ring that has one
      }
    }
    return best;
  };
  // within the cap, the trip's own restaurants first, then one of another day; past the cap (opts.wide) the same —
  // a restaurant of another day 700 m off before a new one 18 km off (live check 2026-10-19: 섬 권역 on a Tuesday)
  const inner = radii(c);
  const best = search(false, inner) || search(true, inner) || (ctx.wide ? search(false, ringsOf(ctx)) || search(true, ringsOf(ctx)) : null);
  if (best) {
    const P = stops[best.k - 1], N = stops[best.k];
    if (P && !best.movP) P.b = best.pEnd;
    if (N && !best.movN) N.a = best.nStart;
    for (const [s, a, b] of [...(best.movP || []), ...(best.movN || [])]) Object.assign(s, { a, b });
    stops.splice(best.k, 0, { page: best.x.page, name: best.x.doc.t, a: best.s, b: best.s + best.len, role: "meal", why: "", by: "site" });
    return true;
  }
  if (depth >= 2) return false;
  // a visit inside the meal's window gives up its place: the code's own first, nearest the aim
  const inWin = stops.map((s, k) => ({ s, k })).filter(({ s }) => s.role !== "stay" && s.role !== "meal" && s.a < m.near[1] && s.b > m.near[0])
    .sort((p, q) => Number(!p.s.by) - Number(!q.s.by) || Math.abs(p.s.a - m.at) - Math.abs(q.s.a - m.at));
  for (const { k } of inWin) {
    const was = stops.splice(k, 1)[0];
    if (placeMeal(ctx, stops, kind, depth + 1)) return true;
    stops.splice(k, 0, was);
  }
  return false;
}

/** A night's stay after the day's last stop: the stay given (the plan's, kept when it can start by 23:29 after the
 *  leg's margin and not before its check-in time), else the other nights' stay when near enough, else the nearest
 *  that can (hotels, motels and guesthouses before camps), within STAY_NEAR first and farther only when none can. */
function placeStay(ctx, stops) {
  const { c, kb } = ctx;
  const last = stops.at(-1);
  if (!last) return null;
  const startOf = (page) => {
    const ci = mins(((kb.docs[page] || {}).f || {}).ci);
    const a = Math.max(last.b + marginOf(last.page, page, c, kb), ci ?? 0);
    return a <= STAY_LATEST ? a : null;
  };
  const okStay = (page) => hardState(c, (kb.docs[page] || {}).f || {}, "stay") !== "no";
  for (const s of [ctx.stay, ctx.otherStay].filter(Boolean)) {
    const a = startOf(s.page);
    const lp = lastPoint(kb, stops);
    const near = !lp || !gOf(kb, s.page) || metres(lp, gOf(kb, s.page)) <= STAY_NEAR;
    if (a !== null && okStay(s.page) && (s === ctx.stay || near)) {
      return { page: s.page, name: s.name, a, b: Math.min(a + 60, 23 * 60 + 59), role: "stay", why: s.why || "", ...(s === ctx.stay && !s.by ? { moved: true } : { by: "site" }) };
    }
  }
  const at = lastPoint(kb, stops);
  if (!at) return null;
  const list = ctx.pool.stays.filter((x) => okStay(x.page)).map((x) => ({ x, m: metres(at, x.g) }))
    .sort((p, q) => p.x.camp - q.x.camp || p.m - q.m || (p.x.page < q.x.page ? -1 : 1));
  for (const R of [STAY_NEAR, 10000, 20000, Infinity]) {
    for (const { x } of list.filter((y) => y.m <= R)) {
      const a = startOf(x.page);
      if (a !== null) return { page: x.page, name: x.doc.t, a, b: Math.min(a + 60, 23 * 60 + 59), role: "stay", why: "", by: "site" };
    }
  }
  return null;
}

/** The flags of day i of a plan with that day as the builder has it — the trip-wide budget too. */
function dayFlags(ctx, stops) {
  const plan = withDay(ctx, stops);
  const r = planFlags(plan, ctx.c, ctx.kb, ctx.edit);
  return r.list.filter((x) => x.day === ctx.i || x.day === -1);
}

/** The meals day i must have: each lunch or dinner its reader's day spans (or, on an edit, the plan before had), unless
 *  the reader eats elsewhere. */
function mealsFor(ctx, stops) {
  const plan = withDay(ctx, stops);
  const day = readerDay(plan, ctx.c, ctx.i, ctx.kb) || { lo: ctx.mlo, hi: ctx.mhi };
  // (the meals by the day after the station's HUB_MARGIN only: plan_state.readerDay mlo–mhi)
  const lo = Math.min(day.mlo ?? day.lo, ctx.mlo), hi = Math.max(day.mhi ?? day.hi, ctx.mhi);
  const before = ctx.edit && ctx.edit.plan.days[ctx.i] ? ctx.edit.plan.days[ctx.i].stops : [];
  return ["lunch", "dinner"].filter((kind) => (spans({ lo, hi }, MEALS[kind]) || mealIn(before, MEALS[kind], ctx.kb))
    && !eatsElsewhere(kind, ...eatsWords(ctx.c, ctx.edit)));
}

/** A day's bounds as the check reads them (planFlags, plan_state.readerDay): the reader's 하루 시작·하루 끝 hold every
 *  day for every stop but the night's stay (2026-10-24 I07; before, the start held on the first day only and the end
 *  on the last only, and a day before a night ran to 21:00). lo–hi: the stretch the builder fills (the first day from
 *  the start after the station's margin, a later day from opts.lo when given, the last day to the end before the
 *  station's margin, any other to the end); bottom–top: where a stop may go at all (a later day from the reader's
 *  start). */
function makeCtx(c, kb, i, date, opts) {
  const lastDay = i === c.days - 1;
  return {
    c, kb, i, date, lastDay, first: i === 0, edit: opts.edit || null, optLo: opts.lo || 0,
    ...boundsFor(c, i, opts.lo || 0, null, null),
    pool: poolOf(kb, date), taken: opts.taken || new Set(), anchor: opts.anchor || null,
    stay: opts.stay || null, otherStay: opts.otherStay || null,
    plan: opts.plan || { days: tripDates(c.date, c.days).map((d) => ({ date: d, stops: [] })) }, frugal: !!opts.frugal, wide: !!opts.wide,
  };
}
/** makeCtx's bounds with the station's or terminal's margins (plan_state.hubMargin) for the stop the day starts at
 *  (startDoc, its page) and the one it ends at (endDoc) — HUB_MARGIN, more for a stop in another 권역 (review 2026-10-22
 *  C7a: the builder sent every reader with 섬·바다 from 역 to 섬 해수욕장 30 minutes after the train); null docs:
 *  HUB_MARGIN. */
function boundsFor(c, i, optLo, startDoc, endDoc) {
  const lastDay = i === c.days - 1;
  const lo = i === 0 ? hm(c.start) + hubMargin(c, "from", startDoc) : Math.max(hm(c.start), optLo);
  const hi = hm(c.end) - (lastDay ? hubMargin(c, "to", endDoc) : 0);
  // (mlo, mhi: the day its meals are read on — after the station's HUB_MARGIN only, plan_state.readerDay)
  const mlo = i === 0 ? hm(c.start) + (c.from ? HUB_MARGIN : 0) : lo, mhi = hm(c.end) - (lastDay && c.to ? HUB_MARGIN : 0);
  // (every day keeps to the reader's 하루 시작·하루 끝 — the night's stay alone comes after the end: planFlags)
  return { lo, hi, mlo, mhi, bottom: i === 0 ? lo : hm(c.start), top: hi };
}
const withEnds = (ctx, startDoc, endDoc) => ({ ...ctx, ...boundsFor(ctx.c, ctx.i, ctx.optLo, startDoc, endDoc) });

// the first stop of a day with none of its own: at the day's start (or the place's opening), 90 minutes or what the
// place's hours and the day leave; null when that is under visitMin (its floor), past its last entry or over the budget
function firstStop(ctx, x) {
  const a = ceil5(Math.max(ctx.lo, x.win.open));
  const room = floor5(Math.min(x.win.close, ctx.hi) - a);
  if (room < visitMin(x) || a > x.win.last || inBreak(x.f, a, a + Math.min(VISIT_WANT, room))) return null;
  const stop = { page: x.page, name: x.doc.t, a, b: a + Math.min(VISIT_WANT, room), role: "visit", why: "", by: "site" };
  if (x.f.fee && x.f.fee.tab && !feeOk(ctx, [stop])) return null;
  return stop;
}
// how many restaurants that serve a meal are open that date within the first ring of a place
function mealsNear(ctx, x) {
  const R = radii(ctx.c)[1];
  return ctx.pool.meals.filter((y) => metres(x.g, y.g) <= R).length;
}
/** The places a day with no stop of its own may start at, best first and each another 권역 (or place with none) while
 *  there are: the reader's likings first, near the night's stay before it (else where most places are), with a
 *  restaurant near, sure to be open, indoors on a rainy day, a known fee; then the same without the likings, then the
 *  places where most others are (the town's centre) — so a day the likings or the night's stay lead nowhere still
 *  gets its tries. Each can start there (firstStop). */
function firstsOf(base, tries) {
  // (each from the station's margin for its own 권역: withEnds)
  const ok = base.pool.visits.filter((x) => visitOk(base, [], x) && firstStop(withEnds(base, x.doc, x.doc), x));
  const near = (x) => (base.anchor ? Math.floor(metres(base.anchor, x.g) / 3000) : 0);
  const dense = new Map(ok.map((x) => [x.page, density(base, x)]));
  const fed = new Map(ok.map((x) => [x.page, mealsNear(base, x) ? 0 : 1]));
  const order = (keys) => ok.map((x) => ({ x, m: 0, r: keys(x) })).sort(byRank).map((y) => y.x);
  const r = (x) => rank(base, x);
  const lists = [
    order((x) => [r(x)[0], fed.get(x.page), near(x), ...r(x).slice(1), -dense.get(x.page)]),
    order((x) => [fed.get(x.page), near(x), ...r(x).slice(1), -dense.get(x.page)]),
    order((x) => [fed.get(x.page), -dense.get(x.page), ...r(x).slice(1)]),
  ];
  const out = [];
  const per = [Math.ceil(tries / 2), Math.ceil(tries / 4), tries];
  lists.forEach((list, t) => {
    const regions = new Set(out.map((x) => x.region));
    let n = 0;
    for (const x of list) {
      if (out.length >= tries || n >= per[t]) break;
      if (out.includes(x) || (regions.has(x.region) && list.some((y) => !out.includes(y) && !regions.has(y.region)))) continue;
      regions.add(x.region);
      out.push(x);
      n += 1;
    }
  });
  return out;
}

/** One day built in code: {stops, kept, gone} — stops as the plan has them (start/end), kept: the seeds still in it,
 *  gone: the seeds taken out — or null when no such day passes the check. opts: seed (the day's stops, kept as far
 *  as they hold), taken (the pages of the trip's other days), plan (the trip, for the budget and the check), edit,
 *  anchor (where the day starts: the night's stay before it), stay (the night's stay to keep), otherStay (the
 *  trip's other stay), tries (first stops tried when the day has none). */
export function buildDay(c, kb, i, date, opts = {}) {
  const seed = (opts.seed || []).filter((s) => s.role !== "stay");
  // a later day keeps no start of the reader's (the check holds it to the first day): its seeds' own start, else the
  // reader's start, then 09:00, 10:00, 11:00 — a long day that the places that fit cannot fill from 07:00 may from 10:00
  // (round-5 verifier: such conditions were refused)
  const s0 = hm(c.start), e0 = hm(c.end);
  if (seed.length) {
    // the seeds as they are, then without the one farthest from the rest (up to three tries, one left out each): a
    // place across the city from the others leaves a leg whose margin is itself longer than an empty stretch may be
    // (an edit that left 불주사 대웅전 30 km from the rest of its day could not be settled otherwise)
    const far = (x) => {
      const g = gOf(kb, x.page);
      if (!g) return 0;
      const d = seed.filter((y) => y !== x && gOf(kb, y.page)).map((y) => metres(g, gOf(kb, y.page)));
      return d.length ? Math.min(...d) : 0;
    };
    const lone = seed.filter((x) => far(x) > radii(c)[0]).sort((x, y) => far(y) - far(x)).slice(0, 3);
    for (const sd of [seed, ...lone.map((x) => seed.filter((y) => y !== x))]) {
      const lo = i === 0 ? 0 : Math.min(...sd.map((s) => hm(s.start)));
      const day = buildFrom(c, kb, i, date, { ...opts, lo }, sd);
      if (day) {
        const kept = seed.filter((s) => day.stops.some((x) => x.page === s.page));
        return { ...day, kept, gone: seed.filter((s) => !kept.includes(s)) };
      }
    }
    return null;
  }
  for (const lo of i === 0 ? [0] : [s0, ...[540, 600, 660].filter((t) => t > s0 && e0 - t >= 180)]) {
    const day = buildFrom(c, kb, i, date, { ...opts, lo }, seed);
    if (day) return day;
  }
  return null;
}
function buildFrom(c, kb, i, date, opts, seed) {
  const base = makeCtx(c, kb, i, date, opts);
  // opts.trace: an array the tries that fail are said in (a debugging aid)
  const trace = (first, why, stops, flags = [], meal = "") => opts.trace && opts.trace.push({ first: first ? first.doc.t : "(seed)", why, meal, lo: hhmm(base.lo),
    stops: asStops(stops).map((s) => `${s.start}-${s.end} ${s.role} ${s.name}`), flags: flags.map((x) => x.text), kinds: flags.map((x) => x.kind) });
  const firsts = seed.length ? [null] : firstsOf(base, opts.tries || 8);
  if (!firsts.length) {
    if (opts.trace) opts.trace.push({ first: "", why: "none", lo: hhmm(base.lo), stops: [], flags: [], kinds: [] });
    return null;
  }
  // one try of the day from a first stop (or the seeds) with the day's bounds (ctx): {day} — the day built — or {stops}
  // — what the try left, said in the trace
  const attempt = (ctx, first) => {
    const stops = first ? [firstStop(ctx, first)] : cleanSeeds(ctx, seed).stops;
    if (first && !stops[0]) { trace(first, "first", []); return { stops: [] }; }
    // meals first (their windows are fixed), then the empty stretches, then the night's stay
    let ok = "";
    for (const kind of mealsFor(ctx, stops)) {
      if (!mealIn(asStops(stops), MEALS[kind], kb) && !placeMeal(ctx, stops, kind)) { ok = kind; break; }
    }
    if (ok) { trace(first, "meal", stops, [], ok); return { stops }; }
    if (!stops.length) { trace(first, "empty", stops); return { stops }; }
    fillStretches(ctx, stops);
    // a meal the stretches made needed (a day that now spans it)
    for (const kind of mealsFor(ctx, stops)) if (!mealIn(asStops(stops), MEALS[kind], kb)) placeMeal(ctx, stops, kind);
    if (!ctx.lastDay) {
      const stay = placeStay(ctx, stops);
      if (!stay) { trace(first, "stay", stops); return { stops }; }
      stops.push(stay);
    }
    let flags = dayFlags(ctx, stops);
    // a place the code put in left farther than the cap from both stops next to it (round 6, plan_geo.farOnes — not
    // on the wide try, which may go past the cap)
    const far = () => (ctx.wide ? [] : farOnes(stops, c, kb));
    // what the check still finds: a stretch (lengthen, fill), a stop the code put in that it flags or that is far (out,
    // then fill)
    for (let n = 0; (flags.length || far().length) && n < 3; n += 1) {
      const bad = new Set([...flags.filter((x) => x.j !== undefined && ["closed", "hours", "leg"].includes(x.kind)).map((x) => stops[x.j]), ...far().map((j) => stops[j])]
        .filter((s) => s && s.by && s.role !== "stay"));
      if (bad.size) stops.splice(0, stops.length, ...stops.filter((s) => !bad.has(s)));
      const stay = stops.at(-1) && stops.at(-1).role === "stay" ? stops.pop() : null;
      for (const kind of mealsFor(ctx, stops)) if (!mealIn(asStops(stops), MEALS[kind], kb)) placeMeal(ctx, stops, kind);
      fillStretches(ctx, stops);
      if (stay || !ctx.lastDay) {
        const again = placeStay(ctx, stops);
        if (again) stops.push(again);
      }
      flags = dayFlags(ctx, stops);
    }
    // (round 7) what is still flagged with the model's night's stay last: the stay ends the day where it stands after
    // all, when that clears the day (planner.stayEnds — nothing fills it to the end the reader set)
    const last = stops.at(-1);
    if (flags.length && last && last.role === "stay" && !last.by && !last.ends) {
      last.ends = true;
      flags = dayFlags(ctx, stops);
      if (flags.length) delete last.ends;
    }
    if (flags.length) { trace(first, "flags", stops, flags); return { stops }; }
    if (far().length) { trace(first, "far", stops); return { stops }; }
    // a day the code builds has places to visit, never only cafés and meals (round 6: on hard conditions a day of a
    // café and two meals was sent): one, two when the reader's day is 6 hours or more; a day around the model's own
    // stops one — else this try fails, and when every try does so does the day (preflight then says so at the button)
    if (stops.filter((s) => s.role === "visit").length < visitsWanted(ctx, seed)) { trace(first, "visits", stops); return { stops }; }
    const kept = seed.filter((s) => stops.some((x) => x.page === s.page));
    // a day built past the cap (the wide try: nothing within it builds the day): the code's places past it are marked,
    // so a later check (plan_geo.farOnes — settle on the code's own plan) does not take them out as if a change had left
    // them far, and put them back (round-6 verifier: '…8.0km 넘게 떨어져 일정에서 뺐습니다' then '…넣고' on a code plan)
    if (ctx.wide) for (const j of farOnes(stops, c, kb)) stops[j].wide = true;
    return { day: { stops: asStops(stops), kept, gone: seed.filter((s) => !kept.includes(s)) } };
  };
  // the station's or terminal's margins by the 권역 of the stops next to it (plan_state.hubMargin, review 2026-10-22
  // C7a): the day's bounds from the first stop it is tried with (or the first seed) at both ends — then once more to
  // the end of the stop the try ended at, when that 권역 keeps another margin before the end (a day that went back to
  // town from the islands, or out to them)
  const toHub = base.lastDay && !!c.to;
  for (const first of seed.length ? [null] : firsts) {
    // a budget of tries (opts.work: {left}, preflight's diagnosis — the same work on any server, so the same reasons)
    if (opts.work && opts.work.left-- <= 0) return null;
    const startDoc = first ? first.doc : kb.docs[seed[0].page] || null;
    let endDoc = first ? first.doc : kb.docs[seed.at(-1).page] || null;
    for (let again = 0; again < 2; again += 1) {
      if (again && opts.work && opts.work.left-- <= 0) return null;
      const r = attempt(withEnds(base, startDoc, endDoc), first);
      if (r.day) return r.day;
      const end = r.stops.filter((s) => s.role !== "stay").at(-1);
      if (!toHub || !end || hubMargin(c, "to", kb.docs[end.page]) === hubMargin(c, "to", endDoc)) break;
      endDoc = kb.docs[end.page] || null;
    }
  }
  return null;
}

/** Every day of a trip built in code (buildDay with no seed): {plan, failed: null, wide, wideDays} or {plan: null,
 *  failed: day index, taken: the pages of the days before it}; trace (an array): the failing day's tries, why each
 *  failed. No place twice; a day after a night starts near that night's stay; the trip's nights share a stay when it is
 *  near enough. title and summary are the code's, from the data only (codeText). The passes, each until one makes every
 *  day: within the cap (plan_geo.CAP); a later day short of places — the trip spending fewer places a day (frugal, longer
 *  visits); then the same two with a day nothing within the cap builds built once more with the rings past it (wide,
 *  round 6) — that day only, the others within the cap (round-6 verifier: the whole trip was built wide for one day);
 *  wideDays: the days so built, wide: whether any was. opts.noWide: the passes within the cap only. */
export function buildPlan(c, kb, edit = null, trace = null, opts = {}) {
  // without a car in a city whose data names no bus for its places (knowledge.walkOnly): first a trip whose every leg
  // is a walk (c.walk — plan_geo.cap), the only legs the site confirms; else the plain one, its longer legs the
  // reader's to check (the plan then a candidate: plan_state.checksList 'transit')
  if (walkOnly(c.move) && !c.walk) {
    const walk = buildTrip({ ...c, walk: true }, kb, edit, trace, { ...opts, noWide: true });
    if (walk.plan) return walk;
  }
  return buildTrip(c, kb, edit, trace, opts);
}
function buildTrip(c, kb, edit = null, trace = null, { noWide = false, work = null } = {}) {
  const dates = tripDates(c.date, c.days);
  // one pass, going on from `failed` — a pass within the cap that failed on a day: its days before that day are the same
  // days this pass would build (each of its days tries within the cap first), and that day itself fails within the cap
  const pass = (frugal, widen, failed = null) => {
    const days = failed ? failed.days : [];
    const plan = { title: "", summary: "", notes: [], days: dates.map((date, i) => days[i] || { date, stops: [] }) };
    const wideDays = [];
    for (let i = days.length; i < dates.length; i += 1) {
      const taken = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.page)));
      const prevStay = i > 0 ? plan.days[i - 1].stops.find((s) => s.role === "stay") : null;
      if (trace) trace.length = 0;   // the failing day's tries only
      // (where the day before ends: its night's stay, else its last stop with a point — round 7 review A09)
      const opts = { taken, plan, edit, anchor: i > 0 ? (prevStay && gOf(kb, prevStay.page)) || lastPoint(kb, plan.days[i - 1].stops) : null, otherStay: prevStay, trace, frugal, work };
      let day = failed && i === days.length ? null : buildDay(c, kb, i, dates[i], opts);
      if (!day && widen) {
        day = buildDay(c, kb, i, dates[i], { ...opts, wide: true });
        if (day) wideDays.push(i);
      }
      if (!day) return { plan: null, failed: i, taken, days: plan.days.slice(0, i) };
      plan.days[i] = { date: dates[i], stops: day.stops };
    }
    Object.assign(plan, codeText(plan, c, kb));
    return { plan, failed: null, wide: wideDays.length > 0, wideDays };
  };
  const strict = pass(false, false);
  if (strict.plan) return tidy(strict);
  const frugal = strict.failed > 0 ? pass(true, false) : null;
  if ((frugal && frugal.plan) || noWide) return tidy(frugal || strict);
  const wide = pass(false, true, strict);
  if (wide.plan || wide.failed === 0) return tidy(wide);
  return tidy(pass(true, true, frugal));
}
// a pass's result without its partial days
const tidy = ({ days, ...r }) => (r.plan ? r : { plan: null, failed: r.failed, taken: r.taken });

/** A title and a summary the code writes from the data alone (a plan with no words of the model's): the date, the
 *  trip's length, the 권역 its pages name and the places' own names. */
export function codeText(plan, c, kb) {
  const title = `${dateWords(c.date)} ${regionWord()}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`;
  const parts = plan.days.map((d, i) => {
    const own = d.stops.filter((s) => s.role !== "stay");
    const visits = own.filter((s) => s.role === "visit").map((s) => s.name);
    const meals = own.filter((s) => s.role === "meal").map((s) => s.name);
    const cafes = own.filter((s) => s.role === "cafe").map((s) => s.name);
    const regions = [...new Set(own.map((s) => regionOf(kb.docs[s.page])).filter(Boolean))];
    const where = regions.length ? `${regions.join(", ")} 권역에서 ` : "";   // ('해안 권역' is one 권역's name)
    const head = plan.days.length > 1 ? `${i + 1}일차는 ` : "";
    const seen = visits.slice(0, 3);
    const what = `${seen.join("·")}${visits.length > 3 ? " 등" : ""}`;
    // each clause [joined, last]: what is seen, where they eat, the café (round-5 verifier: a day of one café had no
    // summary)
    const bits = [visits.length && [`${what}${visits.length > 3 ? "을" : eul(seen.at(-1))} 둘러보고`, `${what}${visits.length > 3 ? "을" : eul(seen.at(-1))} 둘러봐요`],
      meals.length && [`${meals.join("·")}에서 식사하고`, `${meals.join("·")}에서 식사해요`],
      cafes.length && [`${cafes.join("·")}에서 쉬고`, `${cafes.join("·")}에서 쉬어요`]].filter(Boolean);
    if (!bits.length) return "";
    return `${head}${where}${[...bits.slice(0, -1).map((b) => b[0]), bits.at(-1)[1]].join(" ")}.`;
  }).filter(Boolean);
  const summary = parts.join(" ").slice(0, 300) || `${title}예요.`;
  return { title, summary };
}

// ------------------------------------------------------------------ before the model: the conditions themselves
const md = dateWords;
const shift = (iso, n) => new Date(Date.parse(`${iso}T12:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
const won = (n) => `${n.toLocaleString("en-US")}원`;

/** Whether a plan can be made for these conditions at all, before any model call (operator 2026-10-18: '문제가 있으면
 *  아예 생성 버튼 누르는 단계에서 지적을 하고'): [] when buildPlan makes every day — then the pipeline always ends with a
 *  plan that has nothing flagged (planner.settle falls back to buildDay and buildPlan) —; else [{field, text, fixes:
 *  [{label, set?, focus?}]}]: field, the condition to change (a key of the conditions); text, the cause in the reader's
 *  words (해요체) for that date and the site's data; each fix's set (full new values of condition fields, as
 *  validConditions reads them) makes buildPlan pass — checked here, and by opts.valid (planner.validConditions) when
 *  given; focus, the field the reader is to choose. Pure code: buildPlan once when it passes. opts: today (YYYY-MM-DD
 *  in Korea), daysAhead (the dates a fix may offer), valid. The handler runs it for a new plan only (an edit changes a
 *  plan made for these conditions). */
export function preflight(c, kb, now = new Date(), edit = null, opts = {}) {
  const trace = [];
  const built = buildPlan(c, kb, edit, trace);
  if (built.plan) return [];
  return diagnose(c, kb, now, edit, built, trace, opts);
}

// a refusal's reasons build the trip again for each change they offer: no more than DIAG_RUNS builds, DIAG_TRIES tries
// of a day in all and DIAG_CHECK for one change (buildFrom's tries, ~3 ms each here — round-5 verifier: up to a second
// of the server's time for one refusal); a change not checked within them is not offered. A count, not a clock
// (round-6 verifier: with a 300 ms clock the same conditions got other reasons and fixes when the server was busy) —
// on the 12 hard conditions refused of 1,500 (2026-10-19): 0.44–0.87 s a refusal with its first builds (those 0.12–0.47
// s), each with a fix, 24 in all (every one checked; with no bound 1.05–3.55 s, 63)
const DIAG_RUNS = 24;
const DIAG_TRIES = 100;
const DIAG_CHECK = 40;
const BUDGET_MAX = 1000000;

function diagnose(c, kb, now, edit, built, trace, opts) {
  const memo = new Map();
  const work = { left: DIAG_TRIES };
  let runs = 0;
  const passes = (patch) => {
    const key = JSON.stringify(patch);
    if (memo.has(key)) return memo.get(key);
    if (runs >= DIAG_RUNS || work.left <= 0) return false;
    const next = { ...c, ...patch };
    let ok = true;
    if (opts.valid) { try { opts.valid(next); } catch { ok = false; } }
    if (ok) {
      runs += 1;
      const one = { left: Math.min(work.left, DIAG_CHECK) };
      const had = one.left;
      ok = !!buildPlan(next, kb, edit, null, { work: one }).plan;
      work.left -= had - Math.max(0, one.left);
    }
    memo.set(key, ok);
    return ok;
  };
  const failed = built.failed;
  const dates = tripDates(c.date, c.days);
  const date = dates[failed];
  const when = c.days > 1 ? `${failed + 1}일차 ${md(date)}` : md(date);
  const today = opts.today || new Date(now.getTime() + 9 * 3600e3).toISOString().slice(0, 10);
  const lastDate = shift(today, opts.daysAhead ?? 180);
  const pool = poolOf(kb, date);
  const rain = c.needs.includes("rain");
  const hard = c.needs.filter((n) => HARD.includes(n));
  const why = new Set(trace.flatMap((t) => (t.why === "flags" ? t.kinds : [t.why])));
  const taken = built.taken || new Set();
  // the places to visit open that date the builder may use for the needs picked: the data says each hard need fits,
  // and in the rain not outdoors — one outdoor place a day still may (round-5 verifier: the count left it out)
  const okHard = pool.visits.filter((x) => hardState(c, x.f, "visit") === "ok");
  const fitAll = okHard.filter((x) => !rain || !isOutdoor(x.f));
  const fitN = fitAll.length + (rain && okHard.some((x) => isOutdoor(x.f)) ? 1 : 0);
  const used = fitAll.filter((x) => taken.has(x.page)).length;
  const theDay = failed > 0 ? `${failed + 1}일차를` : "하루를";
  const hardWords = hard.map((n) => `'${NEEDS[n]}'`).join("·");
  const needWords = [...hard, ...(rain ? ["rain"] : [])].map((n) => `'${NEEDS[n]}'`).join("·");
  const span = `${c.start}~${c.end}`;   // (every day's: the reader's start and end hold every day — I07)
  const fix = (label, set) => ({ label, set });
  const groups = [];   // [{field, fixes}] in the order offered
  const group = (field, fixes) => { if (fixes.length) groups.push({ field, fixes }); };

  // the changes, each checked: the needs, the budget, the way they move, the trip's length, the hours, the stations
  // (the widest change of a kind first — every need out, no budget —: when even that builds nothing, the narrower ones
  // of that kind are not tried, so the count goes to the other kinds)
  if (hard.length || rain) {
    const all = [...hard, ...(rain ? ["rain"] : [])];
    const none = { needs: c.needs.filter((x) => !all.includes(x)) };
    const fixes = all.length > 1 && !passes(none) ? [] : all.filter((n) => passes({ needs: c.needs.filter((x) => x !== n) }))
      .map((n) => fix(`'${NEEDS[n]}' 조건 빼기`, { needs: c.needs.filter((x) => x !== n) }));
    if (!fixes.length && all.length > 1 && passes(none)) fixes.push(fix(`${needWords} 조건 빼기`, none));
    group("needs", fixes);
  }
  if (c.budget !== null && c.budget !== undefined) {
    const up = [...new Set([c.budget * 2, c.budget + 10000, c.budget + 30000].map((x) => Math.min(BUDGET_MAX, Math.max(5000, Math.ceil(x / 5000) * 5000))))]
      .filter((x) => x > c.budget);
    const free = passes({ budget: null });
    const ok = free && up.find((b) => passes({ budget: b }));
    group("budget", [...(ok ? [fix(`예산 ${won(ok)}으로`, { budget: ok })] : []), ...(free ? [fix("예산 정하지 않기", { budget: null })] : [])]);
  }
  if (c.move === "transit") group("move", passes({ move: "car" }) ? [fix("자가용으로 바꾸기", { move: "car" })] : []);
  if (c.days > 1 && failed > 0) {
    for (let days = failed; days >= 1; days -= 1) {
      if (passes({ days })) { group("days", [fix(`${days > 1 ? `${days - 1}박 ${days}일` : "당일"}로 줄이기`, { days })]); break; }
    }
  }
  {
    const s0 = hm(c.start), e0 = hm(c.end);
    const starts = [], ends = [];
    for (const start of ["09:00", "10:00", "11:00", "12:00"].filter((t) => hm(t) > s0 && e0 - hm(t) >= 180)) {
      if (passes({ start })) { starts.push(fix(`시작을 ${start}${ro(start)}`, { start })); break; }
    }
    for (const end of ["20:00", "19:00", "18:00", "17:00", "16:00"].filter((t) => hm(t) < e0 && hm(t) >= 15 * 60 && hm(t) - s0 >= 180)) {
      if (passes({ end })) { ends.push(fix(`끝을 ${end}${ro(end)}`, { end })); break; }
    }
    group("start", starts);
    group("end", ends);
    if (c.from) group("from", passes({ from: "" }) ? [fix(`출발을 ${hubName(c.from)}${ro(hubName(c.from))} 두지 않기`, { from: "" })] : []);
    if (c.to) group("to", passes({ to: "" }) ? [fix(`도착을 ${hubName(c.to)}${ro(hubName(c.to))} 두지 않기`, { to: "" })] : []);
  }

  // the cause, in the reader's words: one field — that field's reason from the data and the builder's own failure;
  // several — the conditions together, as none of them alone is the cause (round-5 verifier: '25곳뿐이라' beside a
  // budget and an hours problem, each of which alone made a plan)
  const missed = [...new Set(trace.filter((t) => t.why === "meal").map((t) => MEALS[t.meal].label))].join("·");
  // the station's margins as the code holds them (plan_state.hubMargin): HUB_MARGIN, up to the far islands' floor
  const mm = (n) => (n % 60 ? `${n}분` : `${n / 60}시간`);
  const hubWords = `가는 곳의 권역에 따라 ${mm(HUB_MARGIN)}~${mm(farFloor(c.move))}`;
  const one = {
    needs: () => (why.has("stay") && !why.has("meal") && failed < c.days - 1 && hard.length
      ? `${when} 밤에 ${hardWords} 조건에 맞지 않는다고 자료에 있는 숙소를 빼면 그날 마지막 장소 뒤에 묵을 곳이 없어요.`
      : `${when}에 여는 곳 가운데 ${hard.length ? `${hardWords}${hard.length > 1 ? "에 모두" : "에"} 맞는다고 자료에 있${rain ? "고 " : "는 "}` : ""}`
        + `${rain ? "야외가 아닌 " : ""}곳이 ${fitN ? `${fitN}곳뿐이라` : "없어"}${rain ? "(비 오는 날 야외는 하루 한 곳까지)" : ""}`
        + `${used ? ` 앞선 날에 넣은 ${used}곳을 빼면` : ""} ${theDay} 채울 수 없어요.`
        // (UI-A01: what the count means — the same words as the form's)
        + `${hard.length ? " 자료가 없는 곳은 조건에 맞지 않는다는 뜻이 아니라 사이트에 그 정보가 없다는 뜻이에요 — 방문 전 전화로 확인할 수 있어요." : ""}`),
    budget: () => `입장료 예산 ${won(c.budget)}으로는 ${when}에 무료라고 자료에 있는 곳(${pool.visits.filter((x) => x.f.fee && x.f.fee.free).length}곳)과 예산 안에 드는 곳만으로 ${theDay} 채울 수 없어요.`,
    move: () => `대중교통·걷기로는 ${when}에 고른 조건에 맞는 곳이 서로 멀어 가까운 곳만으로 ${theDay} 채울 수 없어요.`,
    days: () => `고른 조건에 맞는 곳을 앞선 날에 넣고 나면 ${when}에 넣을 곳이 모자라요.`,
    hours: () => (why.has("stay") && failed < c.days - 1 ? `${when} 밤에 묵을 숙소를 그날 마지막 장소 뒤 23:29까지 넣을 수 없어요.`
      : missed && !why.has("gap") ? `${when}의 ${span}에는 ${missed} 시간에 고른 곳 가까이에서 여는 음식점을 찾을 수 없어요.`
        : why.has("visits") && !why.has("gap") ? `${when}의 ${span}에는 식사·카페 말고 들를 곳을 고른 조건에 맞게 넣을 수 없어요.`
          : `${when}의 ${span}${eul(span)} 고른 조건에 맞는 곳만으로 채우면 2시간 넘게 비는 시간이 남아요.`),
    hubs: () => `${[c.from && `${hubName(c.from)}에서 출발한 뒤`, c.to && `${hubName(c.to)}에 도착하기 전`].filter(Boolean).join("와 ")}에 여유(${hubWords})를 두면 ${when}에 고른 조건에 맞는 곳을 넣을 시간이 모자라요.`,
  };
  const kindOf = (field) => (field === "start" || field === "end" ? "hours" : field === "from" || field === "to" ? "hubs" : field);
  // a condition the places must meet, as a clause: [joined, last] — '…에 맞는다고 자료에 있고', '…에 맞는다고 자료에 있는'
  const clause = {
    needs: () => (hard.length ? [`${hardWords}에 맞는다고 자료에 있${rain ? "고 야외가 아니" : ""}고`, `${hardWords}에 맞는다고 자료에 있${rain ? "고 야외가 아닌" : "는"}`]
      : ["야외가 아니고", "야외가 아닌"]),
    budget: () => [`입장료 예산 ${won(c.budget)} 안에 들고`, `입장료 예산 ${won(c.budget)} 안에 드는`],
    move: () => ["대중교통·걷기로 가까이 오갈 수 있고", "대중교통·걷기로 가까이 오갈 수 있는"],
    days: () => ["앞선 날과 겹치지 않고", "앞선 날과 겹치지 않는"],
  };
  const other = { needs: `${needWords} 조건을 빼도 짤 수 있어요.`, budget: "입장료 예산을 바꿔도 짤 수 있어요.", move: "자가용으로 바꿔도 짤 수 있어요.",
    days: "기간을 줄여도 짤 수 있어요.", start: "시작을 늦춰도 짤 수 있어요.", end: "끝을 당겨도 짤 수 있어요.",
    from: "출발 역·터미널을 두지 않아도 짤 수 있어요.", to: "도착 역·터미널을 두지 않아도 짤 수 있어요." };
  const problems = [];
  const kinds = [...new Set(groups.map((g) => kindOf(g.field)))];
  if (kinds.length === 1) {
    for (const g of groups) problems.push({ field: g.field, text: problems.length ? other[g.field] : one[kinds[0]](), fixes: g.fixes });
  } else if (kinds.length > 1) {
    const places = kinds.filter((k) => clause[k]).map((k) => clause[k]());
    const where = places.length ? `${[...places.slice(0, -1).map((x) => x[0]), places.at(-1)[1]].join(" ")} 곳만으로 ` : "고른 조건에 맞는 곳만으로 ";
    const time = kinds.includes("hours") ? `${span}${eul(span)} ` : "";
    const hubs = kinds.includes("hubs") ? `${[c.from && hubName(c.from), c.to && hubName(c.to)].filter(Boolean).join("·")}에 여유(${hubWords})를 두고 ` : "";
    const cause = `${when}에는 ${where}${hubs}${time || theDay + " "}채울 수 없어요 — 아래 조건 가운데 하나를 바꾸면 짤 수 있어요.`;
    for (const g of groups) problems.push({ field: g.field, text: problems.length ? other[g.field] : cause, fixes: g.fixes });
  }
  // nothing else does it: the nearest dates that do (설·추석 당일 and the like), and the date to choose
  if (!problems.length) {
    const near = [];
    for (let n = 1; n <= 7 && near.length < 2; n += 1) {
      for (const d of [shift(c.date, n), shift(c.date, -n)]) {
        if (d < today || d > lastDate || near.includes(d)) continue;
        if (passes({ date: d })) near.push(d);
        if (near.length >= 2) break;
      }
    }
    const few = pool.visits.length < 12;
    problems.push({ field: "date", text: few
      ? `${when}에는 여는 곳이 ${pool.visits.length ? `${pool.visits.length}곳뿐이라` : "없어"} ${theDay} 채울 수 없어요 — 다른 날을 골라 주세요.`
      : `${when}에는 고른 조건을 모두 맞추는 코스를 짤 수 없어요${hard.length || rain ? ` (그날 여는 곳 가운데 ${needWords}에 맞는 곳 ${fitN}곳)` : ""} — 다른 날을 고르거나 조건을 줄여 주세요.`,
    fixes: [...near.map((d) => fix(`${md(d)}${ro(md(d).slice(0, -1))}`, { date: d })), { label: "날짜 다시 고르기", focus: "date" }] });
  }
  // an edit keeps its dates and length: a change of either is the reader's to choose, never a button that sets it
  if (edit) {
    for (const p of problems) p.fixes = p.fixes.map((f) => (f.set && (f.set.date !== undefined || f.set.days !== undefined) ? { label: f.label, focus: f.set.date !== undefined ? "date" : "days" } : f));
  }
  return problems;
}

/** The reader's problems for a plan that still has flags after everything (planner.makePlan: never sent): the flags'
 *  kinds as fields, in the reader's words — what preflight would say when it can, else the flags themselves. */
export function problemsOf(list) {
  const FIELD = { closed: "date", hours: "start", leg: "move", start: "start", end: "end", "stay-missing": "days", "stay-mid": "days", "stay-ci": "days",
    rain: "needs", budget: "budget", "hub-from": "from", "hub-to": "to", meal: "start", gap: "prefs", need: "needs", "stay-last": "days", "stay-two": "days",
    role: "note", many: "note" };
  const seen = new Set();
  const out = [];
  for (const x of list) {
    const field = FIELD[x.kind] || "note";
    if (seen.has(field)) continue;
    seen.add(field);
    out.push({ field, text: `${x.text.replace(/ — [^—]*$/u, "")} — 이 조건으로는 사이트가 고칠 수 없어요.`, fixes: [{ label: "조건 다시 고르기", focus: field }] });
  }
  return out;
}

export { hubLegs, needAt, isCafe, fitsHours };
