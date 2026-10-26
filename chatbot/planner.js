// POST /api/plan/ → text/event-stream: the AI course planner (operator 2026-10-17: 'AI 여행 코스 생성기', its own page
// /plan/, one city). The reader picks conditions (dates, hours, how they move, who comes, likes, needs, a fee
// budget); the model reads the site's catalog and pages and hands the plan over with submit_plan; the code then checks
// every day against the data (knowledge.js checkPlan: closed days, notices, hours, last entry, legs with no time left)
// and the conditions (the day's hours, a stay each night, the fee budget), adds the fees up once (plan_fees.planFees), and sends
// back what is wrong for one fix. The page draws the plan from the site's own place data (/plan/places.json): the
// model's words are only the title, the summary, a reason per stop and the notes.
//
// SSE events: {type:'status', step, text} while it works · {type:'plan', plan} at the end · {type:'error', code,
// message}. Logs: one JSON line per request with numbers only (rounds, tools, submits, flags, tokens) — never the
// reader's words or the plan. The same request checks as the assistant (chatbot/server.js): POST, an allowed Origin,
// a key, a rate limit of its own (a plan costs several calls), a small body that parses, then the conditions.
import { QUERY_CHARS, defaultKnowledge } from "./knowledge.js";
import { city, hubName, hubNames, regionWord } from "./city.js";
import { MOVE, NEEDS, PLAN_STATUS, PLAN_TOOLS, WITH, buildPlanSystem, conditionsText, tripDates } from "./plan_prompt.js";
import {
  CUT, IDLE, SOFT_IDLE, hubMargin, MEAL_APART, MEAL_LONG, MEALS, prefLabel, PREF_TYPES, SNACK, checksList, dropSentences, eatsElsewhere, eatsWords, grounded, hm, idleGaps,
  inMealWindow, isCafe, isMeal, keptMeal, likeWords, liked, mealIn, mealKind, mealRoles, mealSlot, needAt, needsTable, prefFits, rainShut, readerDay, saysMealTime, span, spans, statusOf, wantsOther,
} from "./plan_state.js";
import {
  CAMP, CHECK_WORDS, FILL_MAX, closedWhy, FILL_MIN, hardNeeds, KEEP_MIN, MEAL_KEEP, MEAL_MIN, STAY_NEAR, STOPS_MAX, WEEK, cap, codeFits, codeLeast, dateWords, dayInfo, eul, farOnes,
  breakOf, breakWords, freeRank, gOf, hardState, hhmm, hubLegs as hubLegsOf, iga, inBreak, isOutdoor, jong, keepOf, km, knownFees, lastPoint, legFloor, legMargin, marginOf, metres, mins, near,
  nearestOpen, openWords, overBudget, placesOf, rainRank, regionOf, rideLeast, ro, softOf, stretchMax,
} from "./plan_geo.js";
import { WIDE, wideOf, buildDay, buildPlan, changed, codeText, planFlags, preflight, problemsOf, rainAsked, rainOutdoor, windowOf } from "./plan_build.js";
import { planFees } from "./plan_fees.js";
import { MODEL, dataBlock, neutralise, seoulNow } from "./prompt.js";
import {
  HttpError, SSE_HEADERS, clientIp, clientKey, createLimiter, json, limitCode, originAllowed, readBody, validInput,
} from "./server.js";
import {
  SECRET_MIN, SHARE_LIMITS, VIEW_ERRORS, baseValid, codeBuilt, conditionsOf, readView, secretShort, shareKey, signPlan, sigValid,
} from "./plan_share.js";

export { legMargin, preflight };

export const PLAN_LIMITS = {
  // a request's body: an edit of a plan at readSubmit's own bounds (3 days × 10 stops, a 120-character reason each,
  // the longest title, summary and notes in its base, a 300-character request, a 200-character note) is about 20 KB
  // (round-6 final verifier: 17,481 bytes over the 16 KB this was); a view bounds its own link (SHARE_LIMITS)
  bodyBytes: 32 * 1024,
  noteChars: 200,
  requestChars: 300,
  daysAhead: 180,        // a trip starts today (in Korea) or within this many days
  perMinute: 3,          // per client per minute (a plan is several model calls)
  perDay: 20,            // per client per 24 hours
  allPerMinute: 15,
  allPerDay: 400,
  // speed (operator 2026-10-17: '늦어도 1분 안에는 돼야', a plan took 160 s, an edit longer): no thinking — the code
  // checks every plan anyway —, the facts the reader's needs ask for handed over with the conditions, one reading
  // round at most, then submit_plan is forced; one fix only while there is time for it
  rounds: 4,             // model calls of one plan: one reading round, the plan, one fix, a forced last hand-over
  reads: 1,              // calls that only read (search_site / get_pages) before submit_plan is forced
  submits: 2,            // submit_plan calls the code checks: the first, and one fix
  maxTokens: 6000,       // one call
  outputTokens: 20000,   // all calls of one plan — a ceiling: each call asks for no more than what is left
  submitTokens: 6000,    // kept back for the last call, which must hand the plan over
  toolChars: 24000,      // all reading results of one plan
  requestMs: 55000,      // the whole plan (vercel.json maxDuration 60; the page gives up at 70 s)
  fixBy: 32000,          // a plan the check finds wrong is sent back for its fix only before this; later it is
                         // finished as it is, its flags shown (status 'unmet')
  readBy: 18000,         // after this the next call must hand the plan over
  callMs: 40000,
  refusedPerMinute: 10,  // conditions refused at the button (preflight), per client — not the plan's quota
  refusedPerDay: 100,
  refusedAllPerMinute: 120,
  refusedAllPerDay: 4000,
  stopsPerDay: STOPS_MAX,   // a day's stops, its night's stay counted (plan_geo.STOPS_MAX: the code adds no more)
};

const ERRORS = {
  not_configured: "코스 만들기가 아직 연결되지 않았습니다.",
  rate_limited: "요청이 너무 잦습니다. 1분 뒤에 다시 만들어 주세요.",
  daily_limit: "오늘 만들 수 있는 코스 수를 넘었습니다. 내일 다시 만들어 주세요.",
  busy: "지금은 코스를 만들 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
  bad_request: "조건을 다시 골라 주세요.",
  bad_date: "여행 날짜는 오늘부터 180일 안에서 골라 주세요.",
  too_large: "요청이 너무 깁니다.",
  timeout: "코스를 만드는 데 너무 오래 걸려 멈췄습니다. 다시 시도해 주세요.",
  refusal: "이 요청으로는 코스를 만들 수 없습니다.",
  empty: "코스를 만들지 못했습니다. 조건을 조금 바꿔 다시 시도해 주세요.",
  conditions: "이 조건으로는 코스를 끝까지 짤 수 없어요. 아래를 바꿔 주세요.",
  edit_failed: "요청한 변경으로는 코스를 끝까지 맞출 수 없어 보던 일정을 그대로 두었습니다. 요청을 조금 바꿔 다시 시도해 주세요.",
  error: "코스를 만들지 못했습니다. 다시 시도해 주세요.",
};
export const planError = (code) => ERRORS[code] || ERRORS.error;

// one line of text: every run of spaces, line breaks and control characters (C0, C1 — U+0085 too) one space, so no
// text the reader sends can start a line of its own where it reaches the model (round-6 final verifier)
const str = (v, max) => (typeof v === "string" ? v.replace(/[\s\p{Cc}]+/gu, " ").trim().slice(0, max) : "");
const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const set = (v, keys, max) => Array.isArray(v) && v.length <= max && v.every((x) => keys.includes(x)) && new Set(v).size === v.length;

/** The reader's conditions, checked (every field from a fixed list or a bounded number; the note is text, cut and
 *  neutralised where it reaches the model). Throws HttpError 400 otherwise; a date in the past or too far: bad_date. */
export function validConditions(c, now) {
  if (!c || typeof c !== "object" || Array.isArray(c)) throw new HttpError(400, "bad_request");
  const today = seoulNow(now).date;
  if (typeof c.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(c.date) || Number.isNaN(Date.parse(`${c.date}T12:00:00Z`))
    || new Date(`${c.date}T12:00:00Z`).toISOString().slice(0, 10) !== c.date) {   // 2027-02-30 is not a date
    throw new HttpError(400, "bad_request");
  }
  const ahead = (Date.parse(`${c.date}T12:00:00Z`) - Date.parse(`${today}T12:00:00Z`)) / 86400000;
  if (ahead < 0 || ahead > PLAN_LIMITS.daysAhead) throw new HttpError(400, "bad_date");
  const start = mins(c.start), end = mins(c.end);
  const ok = isInt(c.days, 1, 3) && start !== null && end !== null && start >= 6 * 60 && end <= 23 * 60 && end - start >= 180
    && Object.hasOwn(MOVE, c.move) && Object.hasOwn(WITH, c.with) && isInt(c.adults, 0, 10)
    && Array.isArray(c.kids) && c.kids.length <= 6 && c.kids.every((a) => isInt(a, 0, 17)) && c.adults + c.kids.length >= 1
    && (c.seniors === undefined || isInt(c.seniors, 0, c.adults))
    && (c.from === undefined || c.from === "" || Object.hasOwn(city().hubs, c.from))
    && (c.to === undefined || c.to === "" || Object.hasOwn(city().hubs, c.to))
    && set(c.prefs ?? [], Object.keys(city().prefs), 4) && set(c.needs ?? [], Object.keys(NEEDS), 6)
    && (c.budget === null || c.budget === undefined || isInt(c.budget, 0, 1000000))
    && (c.note === undefined || (typeof c.note === "string" && [...c.note].length <= PLAN_LIMITS.noteChars));
  if (!ok) throw new HttpError(400, "bad_request");
  return { date: c.date, days: c.days, start: c.start, end: c.end, move: c.move, with: c.with, adults: c.adults,
    seniors: c.seniors || 0, kids: [...c.kids], from: c.from || "", to: c.to || "", prefs: [...(c.prefs || [])],
    needs: [...(c.needs || [])], budget: c.budget ?? null, note: str(c.note, PLAN_LIMITS.noteChars) };
}

// an edit's stop: a place page of the site, as the server writes it (/places/<slug>/ — every place the site has) — no
// space, line break, control or format character, query or fragment (round-6 final verifier: a 'page' of up to 300
// characters with a line break wrote a whole stop line of its own, its reason included, into the prompt; the model
// copied it as rule 10 says and the server signed it). The handler then takes only a page the site has (editPlaces).
const PLACE_PAGE = /^\/places\/[^\s\p{C}/?#]+\/$/u;

// a stop's own buttons on the result (operator 2026-10-23, mockup A): 빼기 (drop) and 다른 곳으로 (swap), made by the
// code alone — no model call (makePlan actOn)
const ACTS = ["drop", "swap"];
const TRIED_MAX = 20;   // the places a slot was already swapped away from in the reader's tab (the page keeps the last 20)

/** An edit: the plan the page shows (pages and times only) and the change the reader asks for. Every field the prompt
 *  prints is of a fixed form: the date the trip's, the times HH:MM, the role one of four, the page a place path
 *  (PLACE_PAGE), the reason and the request one line (str).
 *  extra.act — a stop's own button instead of a request: {op: 'drop' | 'swap', day, page, tried?: [page]} on a page of
 *  that day of the plan sent (else 400); a drop that would leave its day without a stop but the night's stay, or a
 *  swap of a stay or of a pinned stop, is refused too (the page offers none of them). extra.pins — the stops the reader
 *  pinned (고정): [{day, page}], each kept on its day by the code (a pin on a page not on that day is let go). Returns
 *  {plan, request, act?, pins?: [[page] a day]}. */
export function validEdit(plan, request, c, { act, pins } = {}) {
  if (plan === undefined && request === undefined && act === undefined) return null;
  if (!plan || typeof plan !== "object" || !Array.isArray(plan.days) || plan.days.length !== c.days) throw new HttpError(400, "bad_request");
  const isAct = act !== undefined;
  if (isAct ? request !== undefined && request !== ""
    : typeof request !== "string" || !request.trim() || [...request].length > PLAN_LIMITS.requestChars) throw new HttpError(400, "bad_request");
  const dates = tripDates(c.date, c.days);
  const days = plan.days.map((d, i) => {
    if (!d || d.date !== dates[i] || !Array.isArray(d.stops) || d.stops.length > PLAN_LIMITS.stopsPerDay) throw new HttpError(400, "bad_request");
    return { date: d.date, stops: d.stops.map((s) => {
      if (!s || typeof s.page !== "string" || s.page.length > 300 || !PLACE_PAGE.test(s.page) || mins(s.start) === null || mins(s.end) === null) {
        throw new HttpError(400, "bad_request");
      }
      // the role and the reason ride along, so the stops an edit keeps are copied, not read and written again; and the
      // mark of an outdoor place asked for on a rainy day (makePlan's asked: true — plan_build.rainAsked keeps it)
      return { page: s.page, start: s.start, end: s.end, role: ["visit", "meal", "cafe", "stay"].includes(s.role) ? s.role : "visit",
        why: str(s.why, 120), ...(s.asked === true ? { asked: true } : {}) };
    }) };
  });
  const page = (p) => typeof p === "string" && p.length <= 300 && PLACE_PAGE.test(p);
  if (pins !== undefined && (!Array.isArray(pins) || pins.length > c.days * PLAN_LIMITS.stopsPerDay
    || pins.some((p) => !p || typeof p !== "object" || !isInt(p.day, 0, c.days - 1) || !page(p.page)))) throw new HttpError(400, "bad_request");
  const pinned = days.map((d, i) => [...new Set((pins || []).filter((p) => p.day === i && d.stops.some((s) => s.page === p.page)).map((p) => p.page))]);
  let a = null;
  if (isAct) {
    const tried = act && act.tried !== undefined ? act.tried : [];
    if (!act || typeof act !== "object" || Array.isArray(act) || !ACTS.includes(act.op) || !isInt(act.day, 0, c.days - 1) || !page(act.page)
      || !Array.isArray(tried) || tried.length > TRIED_MAX || !tried.every(page)) throw new HttpError(400, "bad_request");
    const day = days[act.day].stops;
    const at = day.find((s) => s.page === act.page);
    // (an act on a page not on that day of the plan sent; a day left with no stop but its stay; a stay or a pinned
    // stop swapped)
    if (!at || (act.op === "drop" && at.role !== "stay" && day.filter((s) => s.role !== "stay").length < 2)
      || (act.op === "swap" && (at.role === "stay" || pinned[act.day].includes(act.page)))) throw new HttpError(400, "bad_request");
    a = { op: act.op, day: act.day, page: act.page, tried: [...new Set(tried)] };
  }
  return { plan: { days }, request: isAct ? "" : str(request, PLAN_LIMITS.requestChars), ...(a ? { act: a } : {}),
    ...(pinned.some((x) => x.length) ? { pins: pinned } : {}) };
}

/** An edit's pages as the site has them: each the key the knowledge gives it (validEdit took only /places/<slug>/), a
 *  page the site does not have as a place left out — a tab's plan made before a build that dropped the place; a forged
 *  page never reaches the model. Changes the edit in place; returns how many stops went. A day all of whose stops
 *  went: HttpError 400 (nothing of it to change). */
export function editPlaces(edit, kb) {
  let gone = 0;
  for (const d of edit.plan.days) {
    const had = d.stops.length;
    d.stops = d.stops.filter((s) => {
      const key = kb.keyFor(s.page);
      const doc = key ? kb.docs[key] : null;
      if (!doc || doc.k !== "place" || !PLACE_PAGE.test(key)) {
        gone += 1;
        return false;
      }
      s.page = key;
      return true;
    });
    if (had && !d.stops.length) throw new HttpError(400, "bad_request");
  }
  // the act's page, the places its slot was swapped away from and the pins: the site's keys too — an act on a page
  // that went is no act
  const key = (p) => kb.keyFor(p) || "";
  if (edit.pins) {
    edit.pins = edit.pins.map((pages, i) => [...new Set(pages.map(key).filter((k) => edit.plan.days[i].stops.some((s) => s.page === k)))]);
    if (!edit.pins.some((x) => x.length)) delete edit.pins;
  }
  if (edit.act) {
    const a = edit.act;
    a.page = key(a.page);
    if (!a.page || !edit.plan.days[a.day].stops.some((s) => s.page === a.page)) throw new HttpError(400, "bad_request");
    a.tried = [...new Set(a.tried.map(key).filter(Boolean))];
  }
  return gone;
}

/** The pages day i of an edit pins (고정): [page]. */
const pinsOf = (edit, i) => (edit && edit.pins && edit.pins[i]) || [];
/** The pinned places (edit.pins) not on their day in `plan`: [{i, page, name}]. */
function lostPins(plan, edit, kb) {
  if (!edit || !edit.pins) return [];
  return edit.pins.flatMap((pages, i) => pages.filter((p) => !((plan.days[i] || {}).stops || []).some((s) => s.page === p))
    .map((p) => ({ i, page: p, name: (kb.docs[p] || {}).t || p })));
}
/** The site without some of its places, as the code puts places in: the knowledge base with those keys out of its
 *  places (plan_geo.placesOf, the stays repair reads) and every other part the same — a stop's own page is still read.
 *  An act's place the reader took out or swapped away (and those its slot was swapped away from before) never comes
 *  back in that same answer: not in a swap, a meal, a fill, a stay or a day built again. */
function without(kb, pages) {
  if (!pages.length) return kb;
  const out = Object.create(kb);
  out.gone = new Set(pages);
  out.keys = kb.keys.filter((k) => !out.gone.has(k));
  return out;
}
/** Whether the code may put `page` in (not a place an act took out — without): for the stays it takes from another
 *  night of the plan rather than from the site's places. */
const mayPut = (kb, page) => !(kb.gone && kb.gone.has(page));

const STAY_AFTER = 30;   // minutes between the day's last stop and the night's stay when the model's stay starts earlier

/** submit_plan's input checked against the conditions and the site: {plan, errors, salvaged, fixes} — errors (Korean,
 *  for the model) when a day, a page, a time or a field is not what it must be; the plan is trimmed to its bounds.
 *  salvaged: the same plan with what cannot stand taken out (a page the site lacks, times that are not times, more
 *  stops than a day holds) and every role made what the place is — finished as it is when the model has no turn left
 *  to fix it (a 1박 2일 plan sent back three times was thrown away whole: operator 2026-10-17, '코스를 만들지
 *  못했습니다'); fixes says, for the reader, what was taken out or changed. null when a day would have no stop.
 *  A night's stay is where the day ends: one that starts before the stop ahead of it is over (the page's check-in
 *  time, a review rule) starts after it, and an end before its start or past midnight is the start plus an hour. */
export function readSubmit(input, c, kb, edit = null) {
  const errors = [];
  const fixes = [];
  if (!input || typeof input !== "object") return { plan: null, errors: ["submit_plan의 입력이 객체가 아니다"], salvaged: null, fixes };
  const dates = tripDates(c.date, c.days);
  const days = Array.isArray(input.days) ? input.days : [];
  if (days.length !== c.days) errors.push(`days는 ${c.days}일이어야 한다(${dates.join(", ")})`);
  const plan = { title: str(input.title, 60), summary: str(input.summary, 300), days: [],
    notes: (Array.isArray(input.notes) ? input.notes : []).map((x) => str(x, 160)).filter(Boolean).slice(0, 3) };
  if (!plan.title) errors.push("title이 비어 있다");
  const safe = [];
  days.slice(0, c.days).forEach((d, i) => {
    const date = d && d.date;
    if (date !== dates[i]) errors.push(`${i + 1}일차 date는 ${dates[i]}이어야 한다`);
    const all = Array.isArray(d && d.stops) ? d.stops : [];
    if (!all.length) errors.push(`${i + 1}일차에 장소가 없다`);
    // an edit's place on a day already full (round-6 final verifier: a café added to a day of 9 places and its night's
    // stay lost the stay, then the café in the rebuilt day): the day keeps its night's stay and the places new to the
    // edit (s.asked); the last of the others go, said so
    const stops = fitDay(all, i, kb, edit, c);
    if (stops.length < all.length) {
      errors.push(`${i + 1}일차 장소는 숙소를 포함해 ${PLAN_LIMITS.stopsPerDay}곳까지 — 그날 장소를 더 넣으려면 다른 곳을 하나 뺀다`);
      const gone = all.filter((s) => !stops.includes(s)).map((s) => { const k = s && typeof s.page === "string" ? kb.keyFor(s.page) : ""; return k && kb.docs[k] ? kb.docs[k].t : ""; }).filter(Boolean);
      fixes.push(`${i + 1}일차: 하루 ${PLAN_LIMITS.stopsPerDay}곳(숙소 포함)을 넘어 ${gone.length ? `${gone.join("·")}${eul(gone.at(-1))}` : "장소를"} 뺐습니다`);
    }
    const out = [];
    const kept = [];
    let prevEnd = null;
    const had = editPages(edit, i, kb);
    stops.forEach((s, j) => {
      const where = `${i + 1}일차 ${j + 1}번`;
      const key = s && typeof s.page === "string" ? kb.keyFor(s.page) : "";
      const doc = key ? kb.docs[key] : null;
      if (!doc || doc.k !== "place") {
        errors.push(`${where}: '${str(s && s.page, 80)}'은 이 사이트의 장소 페이지가 아니다 — 카탈로그의 P 줄 경로를 쓴다`);
        fixes.push(`${i + 1}일차: 이 사이트에 장소 페이지가 없는 곳 하나를 뺐습니다`);
        return;
      }
      // a place on an island reached only by ferry (knowledge.ferry — round 7 review A03: OO섬길, on 방축도, as a
      // 30-minute drive from 섬): the site has no sailing times, so it is no stop
      if (kb.ferry && kb.ferry.has(key)) {
        errors.push(`${where} ${doc.t}: 배로만 가는 섬(${kb.ferry.get(key)})에 있다 — 배 시각이 사이트에 없어 일정에 넣지 않는다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 배로만 가는 섬(${kb.ferry.get(key)})에 있어 일정에서 뺐습니다 — 배 시각은 사이트에 없음(섬 여객선 가이드 참고)`);
        return;
      }
      const role = ["visit", "meal", "cafe", "stay"].includes(s.role) ? s.role : "visit";
      const kind = (doc.f || {}).kd;
      let a = mins(s.start), b = mins(s.end);
      let start = s.start, end = s.end;
      if (role === "stay" && kind === "stay" && a !== null) {
        if (prevEnd !== null && a < prevEnd) a = prevEnd + STAY_AFTER;
        if (a <= 23 * 60 + 29 && (b === null || b <= a)) b = Math.min(a + 60, 23 * 60 + 59);
        if (a <= 23 * 60 + 29) [start, end] = [hhmm(a), hhmm(b)];
      }
      if (a === null || b === null || b <= a) {
        errors.push(`${where} ${doc.t}: start·end는 HH:MM이고 end가 start보다 늦어야 한다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 시각이 올바르지 않아 뺐습니다`);
        return;
      }
      if (prevEnd !== null && a < prevEnd) errors.push(`${where} ${doc.t}: 앞 장소가 끝나기 전에 시작한다`);
      prevEnd = b;
      // a role is what the place is (review CE05: a park handed over as the night's stay passed)
      let fit = role;
      if (role === "stay" && kind !== "stay") {
        errors.push(`${where} ${doc.t}: role stay인데 숙소 페이지가 아니다 — 카탈로그의 숙소를 쓴다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 숙소가 아니라서 묵는 곳이 아닌 방문지로 두었습니다`);
        fit = "visit";
      }
      if ((role === "meal" || role === "cafe") && kind !== "food") {
        errors.push(`${where} ${doc.t}: role ${role}인데 음식점 페이지가 아니다`);
        if (kind !== "stay") fixes.push(`${i + 1}일차 ${doc.t}: 음식점 페이지가 아니라서 ${role === "meal" ? "식사" : "카페"}가 아닌 방문지로 두었습니다`);
        fit = "visit";
      }
      // (a stay handed over as a meal or a café too: round-5 verifier, a motel as a 'cafe' became a visit)
      if (role !== "stay" && kind === "stay") {
        if (role === "visit") errors.push(`${where} ${doc.t}: 숙소는 role stay로만 넣는다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 숙소라서 묵는 곳으로 두었습니다`);
        fit = "stay";
      }
      const stop = { page: key, name: doc.t, start, end, role, why: str(s.why, 120) };
      // (a place new to an edit — not on the reader's page that day — is what the request asked for: s.asked, its page
      // as the model gave it, kept through a swap; makePlan sends edit_failed when one is gone at the end)
      if (had && !had.has(key)) stop.asked = key;
      out.push(stop);
      kept.push({ ...stop, role: fit });
    });
    plan.days.push({ date: dates[i], stops: out });
    safe.push({ date: dates[i], stops: kept });
  });
  const whole = safe.length === c.days && safe.every((d) => d.stops.length);
  const salvaged = whole ? { ...plan, title: plan.title || `${regionWord()}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`, days: safe } : null;
  return { plan, errors, salvaged, fixes };
}

/** The places new to an edit in a plan readSubmit made (s.asked), day by day: [[page]]. */
const askedIn = (plan) => plan.days.map((d) => d.stops.filter((s) => s.asked).map((s) => s.asked));
/** The names of the places new to an edit (asked) no longer in the plan — neither the place nor one swapped in for it
 *  (swapIn keeps s.asked on the stop it changes). */
function lostAsked(plan, asked, kb) {
  return (asked || []).flatMap((pages, i) => pages.filter((p) => !((plan.days[i] || {}).stops || []).some((s) => s.page === p || s.asked === p))
    .map((p) => (kb.docs[p] || {}).t || p));
}
/** The pages of day i of the plan an edit was sent (the reader's page), or null when there is no edit. */
function editPages(edit, i, kb) {
  if (!edit) return null;
  return new Set(((edit.plan.days[i] || {}).stops || []).map((x) => (x && typeof x.page === "string" ? kb.keyFor(x.page) : "") || (x && x.page)));
}
/** The stops of a day the model handed over, cut to STOPS_MAX (the night's stay counted): a stay is never cut, nor a
 *  place new to an edit while another can go, nor a meal while a visit or a café can (round-6 final verifier). Of
 *  those that can go, the one whose going leaves the least empty time goes first — from the stop before it (the
 *  reader's start on the first day; on a later day the day begins at the next) to the stop after it (the reader's end
 *  on the last day, else the night's stay) — the later of equals (cutting the last stop of a day left 2 hours and more
 *  empty before the kept dinner or the stay, and the edit failed). */
function fitDay(stops, i, kb, edit, c) {
  if (stops.length <= PLAN_LIMITS.stopsPerDay) return stops;
  const had = editPages(edit, i, kb);
  const keyOf = (s) => (s && typeof s.page === "string" ? kb.keyFor(s.page) : "");
  // (a place new to the edit, and one the reader pinned — 고정 — on this day: kept like the night's stay)
  const isNew = (s) => (!!had && !!keyOf(s) && !had.has(keyOf(s))) || pinsOf(edit, i).includes(keyOf(s));
  const isStay = (s) => !!s && (s.role === "stay" || ((kb.docs[keyOf(s)] || {}).f || {}).kd === "stay");
  const timed = (s) => !!s && !isStay(s) && mins(s.start) !== null && mins(s.end) !== null;
  const out = [...stops];
  const emptyIf = (j) => {
    if (!timed(out[j])) return -Infinity;
    let p = j - 1, n = j + 1;
    while (p >= 0 && !timed(out[p])) p -= 1;
    while (n < out.length && !timed(out[n])) n += 1;
    const stay = out.find((s) => isStay(s) && mins(s && s.start) !== null);
    const lo = p >= 0 ? mins(out[p].end) : i === 0 ? mins(c.start) : null;
    const hi = n < out.length ? mins(out[n].start) : i === c.days - 1 || !stay ? mins(c.end) : mins(stay.start);
    return lo === null ? 0 : hi - lo;
  };
  for (const keep of [(s) => isStay(s) || isNew(s) || (s && s.role === "meal"), (s) => isStay(s) || isNew(s), (s) => isStay(s), () => false]) {
    while (out.length > PLAN_LIMITS.stopsPerDay) {
      let cut = -1, least = Infinity;
      for (let j = out.length - 1; j >= 0; j -= 1) if (!keep(out[j]) && emptyIf(j) < least) [cut, least] = [j, emptyIf(j)];
      if (cut < 0) break;
      out.splice(cut, 1);
    }
  }
  return out;
}

/** What the code puts right itself before a plan is checked — each a plain rule on the site's data, each said in the
 *  'fixed' list ('사이트가 바로잡은 것') in words for the reader (operator 2026-10-18: a 2박 3일 plan shown as '조건을
 *  다 맞추지 못한 초안' for a gallery closed that Monday and two nights without a stay; outside evaluation the same day:
 *  a Monday plan with five of six stops closed, then an edit left with one stop, no lunch and 340 minutes empty):
 *  0. a night's stay the model put ahead of another stop of its day, or before its check-in time, goes to the end of
 *     the day: after the last stop with the leg's margin (marginOf), not before its check-in time (final check
 *     2026-10-18: a stay at 11:40 ahead of a whole afternoon passed); past 23:29 it stays, flagged (verify);
 *  1. closed: a stop closed that day (its regular closed days or a dated notice: checkPlan 'closed') becomes the
 *     nearest place of its kind — the same type first; for rain an indoor type first and never an outdoor one — that
 *     is open that day within the same times, kept short of the stops next to it by the legs' margins (KEEP_MIN at
 *     least; opensAt: one that leaves that day to check, a holiday, only when no other fits, and said so), not in the
 *     plan, within NEAR.swap; taken out only when nothing fits (or the site has no point for it to search from, said
 *     so), and never the day's last stop;
 *  2. the station or terminal: its margin after the start, before the end (plan_state.hubMargin: HUB_MARGIN, more for
 *     a stop in another 권역);
 *  2b. a meal of the model's off the way (farther than the cap from both stops next to it, they within it of each
 *     other) becomes a restaurant near them (offWay);
 *  3. legs: a leg with no time left, or too little for its straight line (checkPlan's flags), and every leg next to a
 *     stop swapped in, gets its margin (widen);
 *  4. meals: a day that spans lunch or dinner (plan_state.readerDay, MEALS) with no meal stop in its window
 *     (plan_state.mealIn: never a café) gets the nearest restaurant (plan_state.isMeal: never a café, only a menu that
 *     names a meal) to the stop before the slot, open then, within NEAR.meal, for MEAL_MIN minutes, in a gap with the
 *     legs' margins or by shortening the stop next to it (KEEP_MIN); a day with no such slot gives the meal the place
 *     of a stop the code put in itself (mealInstead) — unless the reader wrote that they eat elsewhere; on an edit, a
 *     day that had a meal gets it back the same way;
 *  5. empty time: a stretch of the reader's day longer than IDLE gets the nearest place open then that fits what they
 *     like (plan_state.PREF_TYPES, the islands' 권역; a café for 카페·빵집) and what they need (rain: indoor), for
 *     FILL_MIN–FILL_MAX minutes with the margins, until no such stretch is left or nothing fits;
 *  6. stays, after the meals and the empty hours — so a stay never ends the reader's day before its meal and its
 *     hours are filled unless it says when (plan_state.endsDay, review 2026-10-18): a night with no stay gets the
 *     stay the plan has for another night when it can start by 23:29 after the leg's margin, else the nearest stay to
 *     the day's last stop that can (straight line, within STAY_NEAR; hotels, motels and guesthouses before camps),
 *     after that stop with the leg's margin and not before its check-in time; a stay that does not end the day (no
 *     check-in time on its page) and that the day's stops now run into starts the leg's margin after the last of them;
 *  7. last, every leg next to a stop the code put in, swapped in or moved gets its margin (widen) — and one of the
 *     model's without a car shorter than a walk or a bus with its wait (plan_geo.rideLeast) as much of it as it can;
 *     one that cannot keep it is flagged (verify).
 *  The plan is changed in place; a stop the code adds carries by: 'site', one it swaps in by: 'swap', a stay it moves
 *  moved: true. edit: the plan before the change and the request (makePlan's edit). Returns what was changed, in words
 *  for the reader. */
export function repair(plan, c, kb, edit = null) {
  const out = pinBack(plan, c, kb, edit);
  markKept(plan, edit, kb);
  const many = plan.days.length > 1;
  const dayW = (i) => (many ? `${i + 1}일차 ` : "");
  const check = (d) => kb.checkPlan({ date: d.date, stops: d.stops.map((s) => ({ page: s.page, start: s.start, end: s.end })), move: c.move });
  const ciOf = (page) => mins(((kb.docs[page] || {}).f || {}).ci);
  // the start a night's stay gets after the day's last stop: the leg's margin after it, not before its check-in
  // time; null past 23:29
  const stayAt = (last, page) => {
    const a = Math.max(mins(last.end) + marginOf(last.page, page, c, kb), ciOf(page) ?? 0);
    return a <= 23 * 60 + 29 ? a : null;
  };
  const putStay = (d, s, a) => {
    d.stops.splice(d.stops.indexOf(s), 1);
    d.stops.push(Object.assign(s, { start: hhmm(a), end: hhmm(Math.min(a + 60, 23 * 60 + 59)) }));
  };
  // 0. a night's stay ahead of its day's stops, or before its check-in time
  plan.days.forEach((d, i) => {
    if (i === plan.days.length - 1) return;
    for (const s of d.stops.filter((x) => x.role === "stay" && !x.by)) {
      const own = d.stops.filter((x) => x.role !== "stay");
      const last = own.at(-1);
      const ahead = !!last && d.stops.indexOf(s) < d.stops.indexOf(last);
      const ci = ciOf(s.page);
      if (!ahead && !(ci !== null && mins(s.start) < ci)) continue;
      const a = last ? stayAt(last, s.page) : ci;
      if (a === null) continue;
      out.push(ahead ? `${dayW(i)}밤 숙소 ${s.name}: 그날 다른 장소보다 앞에 있어 마지막 장소 ${last.name} 뒤 ${hhmm(a)}${ro(hhmm(a))} 옮겼습니다`
        : `${dayW(i)}밤 숙소 ${s.name}: 체크인 ${hhmm(ci)} 전이라 시작을 ${s.start}에서 ${hhmm(a)}${ro(hhmm(a))} 늦췄습니다`);
      putStay(d, s, a);
      s.moved = true;
    }
  });
  // 1. closed stops
  plan.days.forEach((d, i) => {
    const r = check(d);
    const closed = r.stops.map((x, j) => (x.day === "closed" && d.stops[j].role !== "stay" ? j : -1)).filter((j) => j >= 0);
    if (!closed.length) return;
    const gone = new Map();   // the stops taken out: index → whether the site has a point to search from
    for (const j of closed) {
      const said = swapIn(plan, d, j, c, kb, { why: closedWhy(kb, d.date, d.stops[j].page), closed: closedSure(kb, d.date, d.stops[j].page) });
      if (said) out.push(`${dayW(i)}${said}`);
      // (a stop the reader pinned stays: the edit then says why it cannot — makePlan pinWords)
      else if (!d.stops[j].pin) gone.set(j, !!gOf(kb, d.stops[j].page));
    }
    // nothing fits: taken out, as long as the day keeps a stop of its own (the stop's flag then says it is closed)
    if (!gone.size || gone.size >= d.stops.filter((s) => s.role !== "stay").length) return;
    for (const [j, point] of gone) {
      out.push(`${dayW(i)}${d.stops[j].name}: ${closedWhy(kb, d.date, d.stops[j].page, "and")}, ${point
        ? `직선 ${near(c, "swap") / 1000}km 안에 그 시각에 여는 같은 종류의 곳 가운데 고른 조건과 앞뒤 이동 여유에 맞는 곳이 없어`
        : "사이트에 이곳의 좌표가 없어 가까운 곳을 찾을 수 없어"} 일정에서 뺐습니다`);
    }
    d.stops = d.stops.filter((_, j) => !gone.has(j));
  });
  // 2. the station or terminal the reader starts from or goes back to: its margin after the start, before the end
  // (plan_state.hubMargin: HUB_MARGIN, more for a stop in another 권역 — review 2026-10-22) — before the legs, which then
  // make room around it
  const first = (plan.days[0] || { stops: [] }).stops[0];
  const fromM = first ? hubMargin(c, "from", kb.docs[first.page]) : 0;
  if (c.from && first && mins(first.start) - mins(c.start) < fromM && mins(first.end) - (mins(c.start) + fromM) >= keepOf(first, kb)) {
    const at = hhmm(mins(c.start) + fromM);
    out.push(`${many ? "1일차 " : ""}${first.name}: ${hubName(c.from)}에서 출발하는 여유 ${span(fromM)}을 두려고 시작을 ${first.start}에서 ${at}${ro(at)} 늦췄습니다`);
    first.start = at;
  }
  const lastDay = plan.days[plan.days.length - 1] || { stops: [] };
  const last = [...lastDay.stops].reverse().find((s) => s.role !== "stay");
  const toM = last ? hubMargin(c, "to", kb.docs[last.page]) : 0;
  if (c.to && last && mins(c.end) - mins(last.end) < toM && mins(c.end) - toM - mins(last.start) >= keepOf(last, kb)) {
    const at = hhmm(mins(c.end) - toM);
    out.push(`${many ? `${plan.days.length}일차 ` : ""}${last.name}: ${hubName(c.to)}${ro(hubName(c.to))} 돌아가는 여유 ${span(toM)}을 두려고 끝을 ${last.end}에서 ${at}${ro(at)} 당겼습니다`);
    last.end = at;
  }
  // 2b. a meal of the model's off the way: a restaurant near the stops next to it instead (offWay) — before the legs
  // get their margins, so no stop moves for a ride that then goes (wave B 2026-10-19)
  plan.days.forEach((d, i) => out.push(...offWay(plan, i, c, kb, edit).map((x) => `${dayW(i)}${x}`)));
  // 3. a leg with no time left, or too little for its straight line (checkPlan's leg flags), and the legs next to a
  // stop swapped in: widen
  plan.days.forEach((d, i) => {
    const flagged = new Set(check(d).legs.filter((x) => x.flag).map((x) => x.from));
    for (let j = 0; j + 1 < d.stops.length; j += 1) {
      const a = d.stops[j], b = d.stops[j + 1];
      // (a leg into the model's own stay too: the stay moves whole, by 23:29 — round-4 verifier)
      if (a.role === "stay" || (b.role === "stay" && b.by) || a.page === b.page || (!flagged.has(j) && !changed(a) && !changed(b))) continue;
      const said = widen(d, j, c, kb, flagged.has(j) && !changed(a) && !changed(b), boundsOf(plan, i, c, kb));
      if (said) out.push(`${dayW(i)}${said}`);
    }
  });
  // 4. meals — first the model's own as the reader eats them: one lunch and one dinner a day, none over MEAL_LONG, a
  // lunch or dinner outside its window moved into it or counted where it is (tidyMeals, round 7)
  out.push(...tidyMeals(plan, c, kb, edit));
  plan.days.forEach((d, i) => {
    for (const kind of ["lunch", "dinner"]) {
      const m = MEALS[kind];
      const day = readerDay(plan, c, i, kb);
      if (!day || mealIn(d.stops, m, kb) || eatsElsewhere(kind, ...eatsWords(c, edit))) continue;
      const had = edit && edit.plan.days[i] && mealIn(edit.plan.days[i].stops, m, kb);
      if (!spans(day, m) && !had) continue;
      // a day the edit kept a meal on but no longer spans it (a day between the first and the last): the meal's
      // window is part of that day again
      const dayOf = () => {
        const x = readerDay(plan, c, i, kb);
        if (x && had && !spans(x, m)) {
          if (i > 0) x.lo = Math.min(x.lo, m.first);
          if (i < plan.days.length - 1) x.hi = Math.max(x.hi, m.last + MEAL_MIN);
        }
        return x;
      };
      const said = addMeal(plan, d, dayOf(), m, c, kb) || mealInstead(plan, d, dayOf, m, c, kb);
      if (said) out.push(`${dayW(i)}${said}`);
    }
  });
  // 5. empty time
  plan.days.forEach((d, i) => {
    for (let n = 0; n < PLAN_LIMITS.stopsPerDay && d.stops.length < PLAN_LIMITS.stopsPerDay; n += 1) {
      const day = readerDay(plan, c, i, kb);
      if (!day) break;
      let said = "";
      // the stretches past IDLE first, then those of SOFT_IDLE or more when a place fits them (live check 2026-10-19:
      // holes of exactly two hours — 10:00–12:00, 13:00–15:00, 15:35–17:35 — were left as they were)
      const gaps = idleGaps(day);
      // (SOFT_IDLE only between two stops: the slack before the first and after the last — the way from the station,
      // back to it — stays the reader's)
      const inner = (x) => x.at > 0 && x.at < day.own.length;
      for (const g of [...gaps.filter((x) => x.minutes > IDLE), ...gaps.filter((x) => inner(x) && x.minutes >= SOFT_IDLE && x.minutes <= IDLE)]) {
        said = fillGap(plan, d, day, g, c, kb);
        if (said) break;
      }
      if (!said) break;
      out.push(`${dayW(i)}${said}`);
    }
  });
  // 6. a stay each night — after the meals and the empty hours, so a stay never ends the reader's day before them
  // unless it says when (plan_state.endsDay: the model's, with a check-in time; review 2026-10-18: one with no
  // check-in time put in at 13:00 after a stop ending at 12:30 left the day without its lunch). The one the code puts
  // in carries by: 'site'; one that does not end the day and that the day's stops now run into starts after them.
  plan.days.forEach((d, i) => {
    if (i === plan.days.length - 1) return;
    const last = [...d.stops].reverse().find((s) => s.role !== "stay");
    if (!last) return;
    const has = d.stops.find((s) => s.role === "stay");
    if (has) {
      const a = stayAt(last, has.page);
      // (a stay the day's stops now run into moves after them, whether or not it ends the day: plan_state.endsDay)
      if (a === null || mins(has.start) >= a) return;
      out.push(`${dayW(i)}밤 숙소 ${has.name}: 그날 마지막 장소 ${last.name} 뒤로 시작을 ${has.start}에서 ${hhmm(a)}${ro(hhmm(a))} 늦췄습니다`);
      putStay(d, has, a);
      return;
    }
    // the stay of another night, when it can start in the evening after the leg's margin (final check 2026-10-18: a
    // stay 22 km away put in 30 minutes after an island's last stop); else the nearest that can
    const other = [...plan.days.slice(0, i).reverse(), ...plan.days.slice(i + 1, -1)]
      .map((x) => x.stops.find((s) => s.role === "stay" && mayPut(kb, s.page) && codeFits(c, (kb.docs[s.page] || {}).f || {}, "stay"))).find(Boolean);
    if (makeRoom(d, (x) => out.push(`${dayW(i)}${x.name}: 밤 숙소를 넣을 자리를 내려고 일정에서 뺐습니다`)) === null) return;
    let pick = null;
    let a = other ? stayAt(last, other.page) : null;
    let how = "";
    if (a !== null) {
      pick = { page: other.page, name: other.name };
      how = `다른 밤과 같은 숙소 ${other.name}${eul(other.name)} 넣었습니다`;
    } else {
      const at = lastPoint(kb, d.stops);
      if (!at) return;
      const near = kb.keys.map((k) => [k, kb.docs[k]])
        .filter(([, x]) => x && x.k === "place" && (x.f || {}).kd === "stay" && (x.f || {}).g && codeFits(c, x.f, "stay"))
        .map(([k, x]) => ({ page: k, name: x.t, m: metres(at, x.f.g), camp: CAMP.test(x.f.ty || "") }))
        .filter((x) => x.m <= STAY_NEAR)
        .sort((x, y) => x.camp - y.camp || x.m - y.m || (x.name < y.name ? -1 : 1));
      const k = near.findIndex((x) => (a = stayAt(last, x.page)) !== null);
      if (k < 0) return;
      pick = near[k];
      how = `${last.name}에서 ${k ? "" : "가장 "}가까운 숙소 ${pick.name}(직선 ${km(pick.m)})${eul(pick.name)} 넣었습니다 — 객실·요금은 숙소에 확인`;
    }
    d.stops.push({ page: pick.page, name: pick.name, start: hhmm(a), end: hhmm(Math.min(a + 60, 23 * 60 + 59)), role: "stay", why: "", by: "site" });
    out.push(`${dayW(i)}밤 숙소: 일정에 없어 ${how}`);
  });
  // 7. every leg next to a stop the code put in, swapped in or moved (final check 2026-10-18: legs next to a place
  // swapped in were left under the code's own margin), and one of the model's without a car shorter than a walk or a
  // bus with its wait, which the check lets through (plan_geo.rideLeast — round 7 review: 10–15 minutes for 1.3–2.6
  // km; after the meals, so no leg widens for a meal that then goes): as much of its margin as it can get
  plan.days.forEach((d, i) => {
    for (let j = 0; j + 1 < d.stops.length; j += 1) {
      const a = d.stops[j], b = d.stops[j + 1];
      const ride = rideLeast(a.page, b.page, c, kb);
      const short = ride !== null && hm(b.start) - hm(a.end) < ride;
      if (a.role === "stay" || a.page === b.page || (!changed(a) && !changed(b) && !short)) continue;
      const said = widen(d, j, c, kb, short && !changed(a) && !changed(b), boundsOf(plan, i, c, kb));
      if (said) out.push(`${dayW(i)}${said}`);
    }
  });
  return out;
}


/** The stops the reader pinned (고정, edit.pins) that the model's plan left out of their day, put back where the reader's
 *  page has them (operator 2026-10-23: a pinned place stays whatever the edit): the model's stops in its way end before
 *  it or start after it when they keep their least (keepOf), else go; a full day gives up its shortest visit or café;
 *  a pinned night's stay is the night's. The stop put back is marked moved (repair 3 and 7 give the legs next to it
 *  their margins) and its name kept in edit.back (the page's line '고정한 …는 그대로 두었어요'). Returns the lines. */
function pinBack(plan, c, kb, edit) {
  const out = [];
  if (!edit || !edit.pins) return out;
  const many = plan.days.length > 1;
  plan.days.forEach((d, i) => {
    const dayW = many ? `${i + 1}일차 ` : "";
    for (const page of pinsOf(edit, i)) {
      if (d.stops.some((s) => s.page === page)) continue;
      const was = ((edit.plan.days[i] || {}).stops || []).find((x) => x.page === page);
      const doc = kb.docs[page];
      if (!was || !doc) continue;
      const a = hm(was.start), b = hm(was.end);
      const stop = { page, name: doc.t, start: was.start, end: was.end, role: was.role, why: was.why || "", moved: true, pin: true };
      const pinned = new Set(pinsOf(edit, i));
      const gone = (s, why) => {
        d.stops.splice(d.stops.indexOf(s), 1);
        out.push(`${dayW}${s.name}: ${why} 일정에서 뺐습니다`);
      };
      if (stop.role === "stay") {
        for (const s of d.stops.filter((x) => x.role === "stay" && !pinned.has(x.page))) gone(s, `독자가 고정한 밤 숙소 ${stop.name}${iga(stop.name)} 있어`);
        d.stops.push(stop);
      } else {
        for (const s of d.stops.filter((x) => x.role !== "stay" && !pinned.has(x.page) && hm(x.start) < b && hm(x.end) > a)) {
          if (hm(s.start) < a && a - hm(s.start) >= keepOf(s, kb)) s.end = hhmm(a);
          else if (hm(s.end) > b && hm(s.end) - b >= keepOf(s, kb)) s.start = hhmm(b);
          else gone(s, `독자가 고정한 ${stop.name}의 시각과 겹쳐`);
        }
        if (d.stops.length >= STOPS_MAX) {
          const short = d.stops.filter((x) => (x.role === "visit" || x.role === "cafe") && !pinned.has(x.page))
            .sort((x, y) => hm(x.end) - hm(x.start) - (hm(y.end) - hm(y.start)))[0];
          if (!short) continue;
          gone(short, `하루 ${STOPS_MAX}곳(숙소 포함)이라 독자가 고정한 ${stop.name}의 자리를 내려고`);
        }
        const k = d.stops.findIndex((x) => x.role === "stay" || hm(x.start) > a);
        d.stops.splice(k < 0 ? d.stops.length : k, 0, stop);
      }
      out.push(`${dayW}${stop.name}: 독자가 고정한 곳이라 그날 일정에 ${stop.start}~${stop.end}${ro(stop.end)} 다시 넣었습니다`);
      edit.back = [...new Set([...(edit.back || []), stop.name])];
    }
  });
  return out;
}

/** A day that holds STOPS_MAX stops (its night's stay counted) gives up a stop for one the code must add (a night's
 *  stay): the shortest the code put in that is not a meal — said through `said(stop)`. Returns '' when there was room,
 *  the stop taken out, or null when nothing can go (round-5 verifier: days of 13 stops). */
function makeRoom(d, said = () => {}) {
  if (d.stops.length < STOPS_MAX) return "";
  const mine = d.stops.filter((s) => s.by === "site" && s.role !== "meal" && s.role !== "stay")
    .sort((a, b) => hm(a.end) - hm(a.start) - (hm(b.end) - hm(b.start)));
  if (!mine.length) return null;
  d.stops.splice(d.stops.indexOf(mine[0]), 1);
  said(mine[0]);
  return mine[0];
}

// a place's kind within its kd: its type; a restaurant's cuisine, or 카페
const kindOf = (x) => ((x.f || {}).kd === "food" ? (isCafe(x) ? "카페" : x.f.ty || "") : (x.f || {}).ty || "");

/** Stop j of day d becomes the nearest place of its kind — the same type first; for rain an indoor type first and never
 *  an outdoor one — that is open that day within the same times, kept short of the stops next to it by the legs'
 *  margins (it gives way first, to SWAP_MIN — a visit 30 minutes, a meal 45; a slot shorter is no slot: round-4
 *  verifier, prefer dropping to a short visit; then the stops next to it, each keeping keepOf and its hours), not in the
 *  plan, within NEAR.swap (or `max`), not pushing the known fees over the budget (repair 1, planner.settle). opts: why
 *  (the reason, in the reader's words: '10월 19일(월)은 쉬는 날이라'), closed (the reason is the stop's closed day as
 *  every source has it — closedWhy, closedSure; the stop swapped in carries swap: 'closed', else 'other': review
 *  2026-10-22 S5, every swap read '그날 쉬는 곳 대신' — a budget's, a need's, a repeat's too), fits(doc, page) (more the
 *  place must be), rank (ranks it first: a number, lower first), max. Changes the stop and its neighbours; returns the
 *  reader's words, or ''. */
// a closed day the sources agree on (plan_geo.dayInfo: nothing disputed) — the only one a swap is 'closed' for: a day
// the sources differ on is said as that difference (closedWhy: '출처마다 쉬는 날이 달라 … 방문 전 전화 확인'), never as
// the closing as a fact (CLAUDE.md 3절 2항 — review 2026-10-22: 구 조선은행 OO지점 on a Monday, 한국관광공사 '1월 1일' ·
// 시 '매주 월요일', came back swapped: 'closed', '그날 쉬는 곳 대신')
const closedSure = (kb, date, page) => !dayInfo(kb, date, page).disputed;
// test(x): one more check of the whole plan with the swap made — the place, its times, the cuts of the stops next to it
// and by: 'swap' in place, all put back after (fewerFees: the fees lower and nothing flagged)
function swapIn(plan, d, j, c, kb, { why, closed = false, fits = () => true, rank = () => 0, max = near(c, "swap"), test = null } = {}) {
  const st = d.stops[j];
  const doc = kb.docs[st.page] || {};
  const f = doc.f || {};
  // (a stop the reader pinned is never swapped away: markKept)
  if (!f.g || st.pin) return "";
  const taken = new Set(plan.days.flatMap((x) => x.stops.map((s) => s.page)));
  const fees = knownFees(plan, c, kb);
  const prev = d.stops[j - 1], next = d.stops[j + 1];
  // the stops next to it with a point (not a night's stay): the place swapped in is within the cap of the nearer
  // (round 6, plan_geo.CAP)
  const nbs = [prev, next].filter((s) => s && s.role !== "stay" && gOf(kb, s.page)).map((s) => gOf(kb, s.page));
  const pick = nearestOpen({ kb, c, date: d.date, at: f.g, max, taken,
    // a meal stays a meal (a place that serves one: isMeal), a café stays a café; the hard needs the reader picked as
    // the code holds every place it puts in (plan_geo.codeFits: a visit the data says fits, else not 'no')
    fits: (x, page) => x.f.kd === f.kd && (st.role === "meal" ? isMeal(x) : st.role === "cafe" ? isCafe(x) : true) && codeFits(c, x.f, st.role) && fits(x, page)
      && (!nbs.length || Math.min(...nbs.map((g) => metres(g, x.f.g))) <= cap(c)),
    rank: (x) => { const rr = rainRank(c, x.f); return rr === null ? null : [rank(x), rr, kindOf(x.doc) === kindOf(doc) ? 0 : 1, freeRank(c, x.f)]; },
    // within the stop's times, short of the stops next to it by the legs' margins: the place swapped in gives way
    // first (to SWAP_MIN), then the stops next to it (cutP, cutN: each keeping keepOf and its hours) — final check
    // 2026-10-18: a place swapped in 2.8 km away kept the 10 minutes left for one 500 m away
    slot: (x) => {
      const P = prev && prev.role !== "stay" ? prev : null, N = next && next.role !== "stay" ? next : null;
      const a0 = hm(st.start), b0 = hm(st.end);
      const least = codeLeast(st.role, x.doc);   // its kind's floor, never under SWAP_MIN (round 6)
      if (b0 - a0 < least) return [];
      const d1 = P ? Math.max(0, hm(P.end) + marginOf(P.page, x.page, c, kb) - a0) : 0;
      const d2 = N ? Math.max(0, b0 + marginOf(x.page, N.page, c, kb) - hm(N.start)) : 0;
      const slack = b0 - a0 - least;
      const s1 = Math.min(d1, slack), s2 = Math.min(d2, slack - s1);
      const cutP = d1 - s1, cutN = d2 - s2;
      if ((P && hm(P.end) - cutP - hm(P.start) < keepOf(P, kb)) || (N && hm(N.end) - hm(N.start) - cutN < keepOf(N, kb))) return [];
      if (cutN && !holds(N, d.date, hm(N.start) + cutN, hm(N.end), c, kb)) return [];
      return [{ a: a0 + s1, b: b0 - s2, cutP, cutN }];
    },
    put: (x) => {
      const was = { ...st };
      Object.assign(st, { page: x.page, name: x.name });
      let ok = !overBudget(plan, c, kb, fees);
      if (ok && test) {
        const pEnd = prev && prev.end, nStart = next && next.start;
        Object.assign(st, { start: hhmm(x.a), end: hhmm(x.b), by: "swap" });
        delete st.wide;
        if (x.cutP) prev.end = hhmm(hm(prev.end) - x.cutP);
        if (x.cutN) next.start = hhmm(hm(next.start) + x.cutN);
        ok = test(x);
        if (prev) prev.end = pEnd;
        if (next) next.start = nStart;
        for (const k of Object.keys(st)) if (!Object.hasOwn(was, k)) delete st[k];
      }
      Object.assign(st, was);
      return ok;
    } });
  if (!pick) return "";
  const what = rainRank(c, pick.f) === 0 && c.needs.includes("rain") && f.kd === "attraction" ? `실내 유형 '${pick.f.ty}'`
    : kindOf(pick.doc) === kindOf(doc) && kindOf(doc) ? `같은 유형 '${kindOf(doc)}'` : "곳";
  // a place with something to check that day (a public holiday, a 명절 rule) is said to be no more than it is
  const said = pick.open === "open" ? `그날 여는 ${what}` : `${what === "곳" ? "" : `${what}, `}${CHECK_WORDS}`;
  const bits = pick.a !== hm(st.start) || pick.b !== hm(st.end) ? [`${hhmm(pick.a)}~${hhmm(pick.b)}에 두었습니다`] : [];
  if (pick.cutP) {
    const to = hhmm(hm(prev.end) - pick.cutP);
    bits.push(`${prev.name} 끝을 ${prev.end}에서 ${to}${ro(to)} 당겼습니다`);
    prev.end = to;
  }
  if (pick.cutN) {
    const to = hhmm(hm(next.start) + pick.cutN);
    bits.push(`${next.name} 시작을 ${next.start}에서 ${to}${ro(to)} 늦췄습니다`);
    next.start = to;
  }
  const line = `${st.name}: ${why} 가까운 ${pick.name}(직선 ${km(pick.m)}, ${said})${ro(pick.name)} 바꿨습니다`
    + `${bits.length ? ` — 앞뒤 장소와의 이동 여유를 두려고 ${bits.join(", ")}` : ""}`;
  Object.assign(st, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), why: "", by: "swap", swap: closed ? "closed" : "other" });
  delete st.wide;   // (a place the wide try put past the cap: the one swapped in is held to it)
  return line;
}

// whether a stop at the times x–y keeps to its hours that day as well as at its own times (checkPlan's flags, a
// restaurant's break)
// one stop's flags at given times on a date (checkPlan of that stop alone), kept per knowledge base — the moves of
// round 6 ask the same stop at the same times many times over (a size cap keeps a long-lived process small)
const STOP_FLAGS = new WeakMap();
function stopFlags(kb, date, page, a, b) {
  if (!STOP_FLAGS.has(kb)) STOP_FLAGS.set(kb, new Map());
  const memo = STOP_FLAGS.get(kb);
  const key = `${date}|${page}|${a}|${b}`;
  if (!memo.has(key)) {
    if (memo.size > 50000) memo.clear();
    memo.set(key, kb.checkPlan({ date, stops: [{ page, start: hhmm(a), end: hhmm(b) }] }).flags.length);
  }
  return memo.get(key);
}
function holds(s, date, x, y, c, kb) {
  const flags = (p, q) => stopFlags(kb, date, s.page, p, q);
  const f = (kb.docs[s.page] || {}).f || {};
  return flags(x, y) <= flags(hm(s.start), hm(s.end)) && (!inBreak(f, x, y) || inBreak(f, hm(s.start), hm(s.end)));
}

/** The bounds day i's stops may be moved within, whole (round 6, shiftPlan): {bottom, top} in minutes — every day
 *  the reader's 하루 시작·하루 끝 (2026-10-24 I07: planFlags holds every day to them), the first day's start after the
 *  station's margin and the last day's end before it. */
function boundsOf(plan, i, c, kb) {
  const own = plan.days[i].stops.filter((s) => s.role !== "stay");
  // (the station's margins by the 권역 of the stops next to it: plan_state.hubMargin)
  const docOf = (s) => (s && kb ? kb.docs[s.page] : null);
  return {
    // (every day keeps to the reader's 하루 시작·하루 끝: planFlags — a stop already outside them is not pushed further)
    bottom: i === 0 ? hm(c.start) + hubMargin(c, "from", docOf(own[0])) : hm(c.start),
    top: i === plan.days.length - 1 ? hm(c.end) - hubMargin(c, "to", docOf(own.at(-1))) : hm(c.end),
  };
}
/** Stops of day d moved whole, `by` minutes, as far as the stretches next to them take it up (round 6: rather than cut a
 *  stop below its floor, plan_geo.FLOORS) — dir 1: stop k and the ones after it later, dir -1: stop k and the ones
 *  before it earlier. Each moved stop keeps its length, its hours that date (holds), a meal where it was (plan_state
 *  mealSlot: in its window, only on its side — round 7 — or on neither; `into`, a meal tidyMeals moves into its
 *  window, from its side into that window); each leg past the last one moved keeps its margin (marginOf) or the gap it
 *  had when that was less; a night's stay after them moves whole by 23:29; nothing goes past the day's bounds
 *  (boundsOf). Returns the moves [{s, a, b}] (not made), or null when they cannot be. */
function shiftPlan(d, k, by, dir, c, kb, { bottom, top }, into = null, give = null) {
  const moves = [];
  let need = by;
  for (let j = k; j >= 0 && j < d.stops.length && need > 0; j += dir) {
    const s = d.stops[j];
    // a meal an edit left as the reader's page has it is an anchor no whole move crosses (markKept; round-6 final
    // verifier: '카페 하나 더' moved the lunch 50 minutes earlier with the four stops before the café)
    if (s.kept) return null;
    // give (widen, on an edit): the stop next to such a meal, past the first one moved, moves on the meal's side only
    // as far as the leg to the meal leaves room and gives up the rest of its time, down to give(s) — the move marked
    // cut (a café asked for before a kept dinner, the stops before it back to a kept lunch: the edit failed)
    const nx0 = d.stops[j + dir];
    if (give && j !== k && nx0 && nx0.kept && s.role !== "stay") {
      const gapK = dir > 0 ? hm(nx0.start) - hm(s.end) : hm(s.start) - hm(nx0.end);
      const far = Math.min(need, Math.max(0, gapK - Math.min(gapK, dir > 0 ? marginOf(s.page, nx0.page, c, kb) : marginOf(nx0.page, s.page, c, kb))));
      const a = dir > 0 ? hm(s.start) + need : hm(s.start) - far, b = dir > 0 ? hm(s.end) + far : hm(s.end) - need;
      const was = s.role === "meal" ? mealSlot(hm(s.start), hm(s.end)) : "";
      if ((dir > 0 ? b > top : a < bottom) || b - a < give(s) || !holds(s, d.date, a, b, c, kb)
        || (s.role === "meal" && mealSlot(a, b) !== was)) return null;
      moves.push({ s, a, b, cut: true });
      return apartKept(d, moves) ? moves : null;
    }
    const a = hm(s.start) + dir * need, b = hm(s.end) + dir * need;
    if (s.role === "stay") {
      if (dir < 0 || a > STAY_LATEST) return null;
      moves.push({ s, a, b: Math.min(a + 60, 23 * 60 + 59) });
      return apartKept(d, moves) ? moves : null;
    }
    const was = s.role === "meal" ? mealSlot(hm(s.start), hm(s.end)) : "";
    if ((dir > 0 ? b > top : a < bottom) || !holds(s, d.date, a, b, c, kb)
      || (s.role === "meal" && mealSlot(a, b) !== was && !(s === into && was === `~${mealSlot(a, b)}`))) return null;
    moves.push({ s, a, b });
    const nx = d.stops[j + dir];
    if (!nx) return moves;
    const gap = dir > 0 ? hm(nx.start) - hm(s.end) : hm(s.start) - hm(nx.end);
    const keep = Math.min(gap, dir > 0 ? marginOf(s.page, nx.page, c, kb) : marginOf(nx.page, s.page, c, kb));
    need = Math.max(0, need - (gap - keep));
  }
  return need > 0 || !apartKept(d, moves) ? null : moves;
}
// a whole move never brings a meal within MEAL_APART minutes of a meal the code added (round-6 verifier: the reader's
// start moved the model's lunch to 140 minutes before the dinner the code had put in 150 minutes after it) — nearer
// than it was, that is: a move that leaves them as near as before, or farther, is no change of the rule's
function apartKept(d, moves) {
  const at = new Map(moves.map((m) => [m.s, m.a]));
  const meals = d.stops.filter((s) => s.role === "meal");
  return meals.every((x, i) => meals.slice(i + 1).every((y) => {
    if ((x.by !== "site" && y.by !== "site") || (!at.has(x) && !at.has(y))) return true;
    const was = Math.abs(hm(x.start) - hm(y.start)), now = Math.abs((at.has(x) ? at.get(x) : hm(x.start)) - (at.has(y) ? at.get(y) : hm(y.start)));
    return now >= MEAL_APART || now >= was;
  }));
}
// the moves of shiftPlan made; the reader's words for the first stop moved (its times) and the ones moved with it
function shiftDone(moves, dir) {
  const [m0, ...more] = moves;
  const rest = more.filter((m) => !m.cut);
  const cut = more.find((m) => m.cut);
  const was = `${m0.s.start}~${m0.s.end}`;
  const wasCut = cut ? `${cut.s.start}~${cut.s.end}` : "";
  for (const m of moves) Object.assign(m.s, { start: hhmm(m.a), end: hhmm(m.b) });
  const to = `${m0.s.start}~${m0.s.end}`;
  const less = cut ? ` — ${cut.s.name}${eul(cut.s.name)} ${wasCut}에서 ${cut.s.start}~${cut.s.end}${ro(cut.s.end)} 줄였습니다` : "";
  const with_ = rest.length === 1 ? `${rest[0].s.role === "stay" ? "밤 숙소 " : ""}${rest[0].s.name}도` : `${dir > 0 ? "뒤" : "앞"} 장소 ${rest.length}곳도`;
  return (rest.length ? `${was}에서 ${to}${ro(m0.s.end)} 옮기고 ${with_} 함께 ${dir > 0 ? "늦췄습니다" : "당겼습니다"}` : `${was}에서 ${to}${ro(m0.s.end)} 옮겼습니다`) + less;
}

/** A leg of a day (stops j and j + 1) with less than its margin (marginOf) gets it: a stop the code put in, swapped
 *  in or moved gives way first, then the other — the stop before ends earlier, the stop after starts later (a night's
 *  stay moves whole, by 23:29) —, each keeping its least (plan_geo.keepOf: the floor of its kind, round 6) and,
 *  starting later, its hours that day; else (round 6, when `bounds` are given — boundsOf) the stop after it and the
 *  ones after that move later whole, or the stop before it and the ones before that earlier (shiftPlan), so no stop is
 *  cut below its floor. least: a leg of the model's own that checkPlan flags (or that is shorter than plan_geo.rideLeast),
 *  which gets as much as it can of the margin down to the bound it is held to (knowledge.legBound) when the whole
 *  margin does not fit. Returns the reader's words; '' when the leg has its
 *  margin or when it cannot get it (verify flags such a leg next to a stop the code changed; settle then drops one). */
function widen(d, j, c, kb, least = false, bounds = null) {
  const a = d.stops[j], b = d.stops[j + 1];
  const ga = gOf(kb, a.page), gb = gOf(kb, b.page);
  const m = ga && gb ? metres(ga, gb) : null;
  const need = marginOf(a.page, b.page, c, kb);
  const ae = hm(a.end), bs = hm(b.start);
  const to = `${b.name}${m !== null ? `(직선 ${km(m)})` : ""}`;
  // from the margin down, 5 minutes at a time, to the least it may have: a leg of the model's own the check flags,
  // its bound (legFloor); any other, the whole margin (round-4 verifier: only the margin and the bound were tried)
  const floor = least ? Math.min(need, legFloor(a.page, b.page, c, kb)) : need;
  // first each stop cut no further than softOf (30 minutes, its own length when shorter, its floor when longer) and the
  // whole moves; then, where neither makes the room, the cuts down to keepOf (round-6 verifier: a place with no type
  // went to its 20-minute floor before any whole move was tried)
  const deep = keepOf(a, kb) < softOf(a, kb) || keepOf(b, kb) < softOf(b, kb);
  for (const soft of deep ? [true, false] : [true]) for (let gap = need; gap >= floor; gap -= 5) {
    if (bs - ae >= gap) return "";
    const lessA = soft ? softOf(a, kb) : keepOf(a, kb), lessB = soft ? softOf(b, kb) : keepOf(b, kb);
    const pull = () => {
      if (a.role === "stay" || bs - gap - hm(a.start) < lessA) return "";
      const was = a.end;
      a.end = hhmm(bs - gap);
      return `${a.name}: 다음 장소 ${to}까지 여유 ${gap}분을 두려고 끝을 ${was}에서 ${a.end}${ro(a.end)} 당겼습니다`;
    };
    const push = () => {
      const x = ae + gap;
      if (b.role === "stay" ? x > 23 * 60 + 29 : hm(b.end) - x < lessB || !holds(b, d.date, x, hm(b.end), c, kb)) return "";
      const was = b.start;
      b.start = hhmm(x);
      if (b.role === "stay") b.end = hhmm(Math.min(x + 60, 23 * 60 + 59));
      return `${b.role === "stay" ? "밤 숙소 " : ""}${b.name}: 앞 장소 ${a.name}에서 여유 ${gap}분을 두려고 시작을 ${was}에서 ${b.start}${ro(b.start)} 늦췄습니다`;
    };
    // whole: the stop after it (and the ones after that) later, else the stop before it (and the ones before) earlier
    const later = () => {
      const moves = bounds && b.role !== "stay" && shiftPlan(d, j + 1, ae + gap - bs, 1, c, kb, bounds);
      return moves ? `${b.name}: 앞 장소 ${a.name}에서 여유 ${gap}분을 두려고 ${shiftDone(moves, 1)}` : "";
    };
    const sooner = () => {
      const moves = bounds && a.role !== "stay" && shiftPlan(d, j, ae + gap - bs, -1, c, kb, bounds);
      return moves ? `${a.name}: 다음 장소 ${to}까지 여유 ${gap}분을 두려고 ${shiftDone(moves, -1)}` : "";
    };
    // next to a meal an edit kept (markKept), which no whole move crosses: the other stop moves alone and the stop
    // beyond it gives up the time — its end sooner (or start later), down to its least (round-6 final verifier: a café
    // asked for before a kept dinner, the stops before it run back to a kept lunch)
    const alone = (s, o, dir) => {
      if (!bounds || s.role === "stay" || s.kept || !o || o.role === "stay" || o.kept || (dir < 0 ? !b.kept : !a.kept)) return "";
      const by = ae + gap - bs;
      const na = hm(s.start) + dir * by, nb = hm(s.end) + dir * by;
      if (na < bounds.bottom || nb > bounds.top || !holds(s, d.date, na, nb, c, kb)) return "";
      const leg = dir < 0 ? Math.min(hm(s.start) - hm(o.end), marginOf(o.page, s.page, c, kb)) : Math.min(hm(o.start) - hm(s.end), marginOf(s.page, o.page, c, kb));
      const oa = dir < 0 ? hm(o.start) : Math.max(hm(o.start), nb + leg), ob = dir < 0 ? Math.min(hm(o.end), na - leg) : hm(o.end);
      const lessO = soft ? softOf(o, kb) : keepOf(o, kb);
      if (ob - oa < lessO || (dir > 0 && !holds(o, d.date, oa, ob, c, kb))
        || (o.role === "meal" && mealSlot(oa, ob) !== mealSlot(hm(o.start), hm(o.end)))) return "";
      const was = `${s.start}~${s.end}`, wasO = dir < 0 ? o.end : o.start;
      Object.assign(s, { start: hhmm(na), end: hhmm(nb) });
      Object.assign(o, { start: hhmm(oa), end: hhmm(ob) });
      const cut = dir < 0 ? (wasO !== o.end ? `${o.name} 끝을 ${wasO}에서 ${o.end}${ro(o.end)} 당겼습니다` : "")
        : (wasO !== o.start ? `${o.name} 시작을 ${wasO}에서 ${o.start}${ro(o.start)} 늦췄습니다` : "");
      return dir < 0
        ? `${s.name}: 다음 장소 ${to}까지 여유 ${gap}분을 두려고 ${was}에서 ${s.start}~${s.end}${ro(s.end)} 옮겼습니다${cut ? ` — ${cut}` : ""}`
        : `${s.name}: 앞 장소 ${a.name}에서 여유 ${gap}분을 두려고 ${was}에서 ${s.start}~${s.end}${ro(s.end)} 옮겼습니다${cut ? ` — ${cut}` : ""}`;
    };
    const soonerAlone = () => alone(a, d.stops[j - 1], -1);
    const laterAlone = () => alone(b, d.stops[j + 2], 1);
    // a whole move a kept meal stops further on: the stops up to the one next to that meal move, and that one gives
    // up the rest of the time (shiftPlan give)
    const less = (s) => (soft ? softOf(s, kb) : keepOf(s, kb));
    const soonerGive = () => {
      const moves = bounds && a.role !== "stay" && shiftPlan(d, j, ae + gap - bs, -1, c, kb, bounds, null, less);
      return moves ? `${a.name}: 다음 장소 ${to}까지 여유 ${gap}분을 두려고 ${shiftDone(moves, -1)}` : "";
    };
    const laterGive = () => {
      const moves = bounds && b.role !== "stay" && shiftPlan(d, j + 1, ae + gap - bs, 1, c, kb, bounds, null, less);
      return moves ? `${b.name}: 앞 장소 ${a.name}에서 여유 ${gap}분을 두려고 ${shiftDone(moves, 1)}` : "";
    };
    const cuts = changed(b) && !changed(a) ? [push, pull] : [pull, push];
    for (const f of soft ? [...cuts, later, sooner, soonerAlone, laterAlone, soonerGive, laterGive] : [...cuts, soonerAlone, laterAlone, soonerGive, laterGive]) {
      const said = f();
      if (said) return said;
    }
  }
  return "";
}

// the latest a stop the code adds after the day's last stop may end: `to` (the reader's end), or the night's stay
// less the leg's margin to it from `page` (the added place)
function endBefore(day, to, page, c, kb) {
  if (!day.stay) return to;
  return Math.min(to, hm(day.stay.start) - marginOf(page, day.stay.page, c, kb));
}

// where a stop the code adds goes in d.stops: before `next` (a stop of day.own), else after `prev`, else at the end
// (a night's stay stays last)
function insertAt(d, prev, next, stop) {
  const j = next ? d.stops.indexOf(next) : prev ? d.stops.indexOf(prev) + 1 : d.stops.findIndex((s) => s.role === "stay");
  d.stops.splice(j < 0 ? d.stops.length : j, 0, stop);
}

/** A meal for one day that lacks it (repair 4): at every slot between two stops (or the day's ends), the restaurant
 *  nearest the stop before it (then the one after it) that opens at a start in the meal's window, for MEAL_MIN minutes
 *  or, where an hour does not fit, MEAL_KEEP. A slot keeps the legs' margins and may shorten the stop before it (its
 *  end) or after it (its start), each keeping its least (plan_geo.keepOf — its kind's floor, round 6). Of all the
 *  slots, the restaurant nearest the stop next to it wins, in steps of 500 m — moving the meal within its window comes
 *  before going farther (round 6: a meal added 5 km from both neighbours) —, then one that cuts nothing, an hour, the
 *  start nearest the aim; one sure to be open before one with something to check. freed: the stop mealInstead took
 *  out for it. Returns the reader's words, or '' when nothing fits. */
function addMeal(plan, d, day, m, c, kb, freed = null, max = near(c, "meal"), again = false, wide = false) {
  if (d.stops.length >= STOPS_MAX) return "";   // a full day: mealInstead makes room
  const own = day.own;
  const at = (s) => ((kb.docs[s.page] || {}).f || {}).g;
  // the slots nearest the meal's aim first (a pick within 500 m there that cuts and moves nothing ends the search)
  const slots = [];
  for (let p = 0; p <= own.length; p += 1) {
    const P = own[p - 1] || null, N = own[p] || null;
    const a = P ? hm(P.end) : day.lo, b = N ? hm(N.start) : day.hi;
    slots.push({ P, N, gap: a > m.at ? a - m.at : b < m.at + MEAL_MIN ? m.at + MEAL_MIN - b : 0 });
  }
  slots.sort((x, y) => x.gap - y.gap);
  const tries = slots.flatMap(({ P, N }) => [P, N].filter((s) => s && at(s)).map((anchor) => ({ P, N, anchor })));
  const taken = new Set(plan.days.flatMap((x) => x.stops.map((st) => st.page)));
  const bounds = boundsOf(plan, plan.days.indexOf(d), c, kb);
  // (round 6) where cutting would take the stop before or after below its floor, it moves whole instead — with the
  // stops before (after) it — when the day has room for that: the most each can move (shiftPlan, in 5s up to 4
  // hours, found by halving), then the exact moves of the one picked
  const most = new Map();
  const canMove = (s, by, dir) => {
    const key = `${d.stops.indexOf(s)}|${dir}`;
    if (!most.has(key)) {
      let lo = 0, hi = 48;
      while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (shiftPlan(d, d.stops.indexOf(s), mid * 5, dir, c, kb, bounds)) lo = mid; else hi = mid - 1;
      }
      most.set(key, lo * 5);
    }
    return by <= most.get(key);
  };
  const move = (s, by, dir) => shiftPlan(d, d.stops.indexOf(s), by, dir, c, kb, bounds);
  // never within MEAL_APART minutes, start to start, of another meal stop of the day (live check 2026-10-19: a lunch
  // added at 12:10 after the model's 10:30 one) — a move of the stops next to it only takes the others farther
  const meals = d.stops.filter((s) => s.role === "meal" && !isCafe(kb.docs[s.page])).map((s) => hm(s.start));
  const apart = (s) => meals.every((x) => Math.abs(x - s) >= MEAL_APART);
  const search = (taken) => {
    let best = null;
    for (const { P, N, anchor } of tries) {
      if (best && best.cost < 1e4 && !best.cutP && !best.cutN && !best.movP && !best.movN && Math.abs(best.a - m.at) <= 30) break;
      // (a cut that leaves the stop under softOf — 30 minutes, or its own length — only when it cannot move whole)
      const [pa, pb, pk, ps] = P ? [hm(P.start), hm(P.end), keepOf(P, kb), softOf(P, kb)] : [];
      const [na, nb, nk, ns] = N ? [hm(N.start), hm(N.end), keepOf(N, kb), softOf(N, kb)] : [];
      const pick = nearestOpen({ kb, c, date: d.date, at: at(anchor), max, taken,
        fits: (x) => isMeal(x) && codeFits(c, x.f, "meal"),
        slot: (x) => {
          const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
          const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
          const by = endBefore(day, day.hi, x.page, c, kb);
          const starts = [];
          for (const len of [MEAL_MIN, MEAL_KEEP]) {
            for (let s = m.first; s <= m.last; s += 5) {
              if (!apart(s)) continue;
              let cutP = P ? Math.max(0, pb + mP - s) : 0, cutN = N ? Math.max(0, s + len + mN - na) : 0;
              let movP = 0, movN = 0, under = 0;
              if (P && pb - cutP - pa < ps) {
                if (canMove(P, cutP, -1)) [movP, cutP] = [cutP, 0];
                else if (pb - cutP - pa < pk) continue;
                else under += 1;
              } else if (!P && s < day.lo) continue;
              if (N && nb - na - cutN < ns) {
                if (canMove(N, cutN, 1)) [movN, cutN] = [cutN, 0];
                else if (nb - na - cutN < nk) continue;
                else under += 1;
              } else if (!N && s + len > by) continue;
              starts.push({ a: s, b: s + len, cutP, cutN, movP, movN,
                score: (cutP + cutN ? 300 + cutP + cutN : 0) + (movP + movN ? 300 + movP + movN : 0) + under * 600 + (len < MEAL_MIN ? 300 : 0) + Math.abs(s - m.at) });
            }
          }
          return starts.sort((x, y) => x.score - y.score).slice(0, 12);
        } });
      if (!pick) continue;
      const far = Math.min(...[P, N].filter((s) => s && at(s)).map((s) => metres(at(s), pick.f.g)));
      const cost = (pick.open === "open" ? 0 : 1e7) + Math.floor(far / 500) * 1e4 + pick.score;
      if (!best || cost < best.cost) best = { ...pick, P, N, anchor, cost };
    }
    return best;
  };
  let best = search(taken);
  // again (settle 6, last): none — a restaurant of another day of the trip, never one of this day (live check
  // 2026-10-19: the far islands have three restaurants the data gives hours for — the first day's lunch and dinner
  // took two, the third shuts on Tuesdays — and the second and third days of an island trip by car, finding no meal,
  // were built again as town days)
  const twice = !best && again && !!(best = search(new Set(d.stops.map((st) => st.page))));
  if (best) {
    const { P, N, anchor } = best;
    const pick = best;
    // (a move found by halving is checked again exactly, before anything changes; one that does not hold after all
    // puts no meal in here)
    const movesP = pick.movP ? move(P, pick.movP, -1) : null, movesN = pick.movN ? move(N, pick.movN, 1) : null;
    if ((pick.movP && !movesP) || (pick.movN && !movesN)) return "";
    const bits = [];
    if (pick.cutP) {
      const to = hhmm(hm(P.end) - pick.cutP);
      bits.push(`${P.name} 끝을 ${P.end}에서 ${to}${ro(to)} 당겼습니다`);
      P.end = hhmm(hm(P.end) - pick.cutP);
    }
    if (pick.cutN) {
      const to = hhmm(hm(N.start) + pick.cutN);
      bits.push(`${N.name} 시작을 ${N.start}에서 ${to}${ro(to)} 늦췄습니다`);
      N.start = hhmm(hm(N.start) + pick.cutN);
    }
    if (movesP) bits.push(`${P.name}${eul(P.name)} ${shiftDone(movesP, -1)}`);
    if (movesN) bits.push(`${N.name}${eul(N.name)} ${shiftDone(movesN, 1)}`);
    // (wide: past the cap on purpose — plan_geo.farOnes lets it be)
    insertAt(d, P, N, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), role: "meal", why: "", by: "site", ...(wide ? { wide: true } : {}) });
    // (a swap for a closed day said as such, any other as a swap — review 2026-10-22 S5)
    const room = freed ? `자리를 내려고 ${freed.by ? `사이트가 ${freed.by === "swap" ? (freed.swap === "closed" ? "쉬는 곳 대신" : "바꿔") : "빈 시간에"} 넣었던 ` : ""}${freed.name}${eul(freed.name)} 빼고 ` : "";
    const again = twice ? `, 다른 날에도 가는 곳 — 가까이에 그 시각에 여는 다른 음식점이 사이트에 없음` : "";
    return `${m.label}: 식사할 곳이 없어 ${room}${anchor === P ? "앞" : "다음"} 장소 ${anchor.name}에서 가까운 음식점 ${pick.name}(직선 ${km(pick.m)}, ${openWords(pick.open)}${again})${eul(pick.name)} `
      + `${hhmm(pick.a)}~${hhmm(pick.b)}에 넣었습니다${bits.length ? ` — ${bits.join(", ")}` : ""}`;
  }
  return "";
}

/** The model's meals of day i off the way (repair 2b, wave B 2026-10-19: an edit to 'the town instead of the islands'
 *  kept the island's lunch, 33.5 km from the town stops before and after it): a meal farther than the cap
 *  (plan_geo.cap) from both stops next to it, and in another 권역 than both, while those two are within it of each
 *  other gives its place to a restaurant within the cap of them (addMeal, in the meal's window) — never one the
 *  reader's words name, nor on an edit one that was off the way on the page already (the reader saw it so); when none
 *  fits, it stays. Returns the reader's words for each. */
function offWay(plan, i, c, kb, edit) {
  const d = plan.days[i];
  const out = [];
  const likes = likeWords(c.note, edit && edit.request);
  const g = (s) => s && gOf(kb, s.page);
  // how far a meal at k of `own` is off the way: 0 when it is not
  // (and in another 권역 than both: a meal of the day's own area is no detour — the edit fuzz: a visit dropped left the
  // lunch between two rural places 8 km apart)
  const area = (s) => regionOf(kb.docs[s.page]);
  const offOf = (own, k) => {
    const P = own[k - 1], s = own[k], N = own[k + 1];
    if (!g(P) || !g(s) || !g(N) || metres(g(P), g(N)) > cap(c)) return 0;
    if (!area(s) || area(s) === area(P) || area(s) === area(N)) return 0;
    const off = Math.min(metres(g(P), g(s)), metres(g(s), g(N)));
    return off > cap(c) ? off : 0;
  };
  const was = edit && edit.plan.days[i] ? edit.plan.days[i].stops.filter((x) => x.role !== "stay") : [];
  for (const s of d.stops.filter((x) => x.role === "meal" && !x.by && !x.pin)) {
    const own = d.stops.filter((x) => x.role !== "stay");
    const P = own[own.indexOf(s) - 1], N = own[own.indexOf(s) + 1];
    const m = MEALS[mealKind(hm(s.start), hm(s.end))];
    const off = offOf(own, own.indexOf(s));
    if (!m || !off || liked(kb.docs[s.page], likes) || offOf(was, was.findIndex((x) => x.page === s.page && x.role === "meal")) > 0) continue;
    const k = d.stops.indexOf(s);
    const before = d.stops.map((x) => [x, x.start, x.end]);
    d.stops.splice(k, 1);
    const said = addMeal(plan, d, readerDay(plan, c, i, kb), m, c, kb);
    // (kept only when the restaurant put in is within the cap of a stop next to it — on the way after all)
    const put = said && d.stops.find((x) => x.role === "meal" && x.by === "site" && !before.some(([y]) => y.page === x.page));
    const near = put && (() => { const o = d.stops.filter((x) => x.role !== "stay"); const j = o.indexOf(put);
      return [o[j - 1], o[j + 1]].some((x) => g(x) && metres(g(x), g(put)) <= cap(c)); })();
    if (!near) { d.stops = before.map(([x, a, b]) => Object.assign(x, { start: a, end: b })); continue; }
    out.push(`${m.label}: 앞뒤 장소 ${P.name}·${N.name}에서 직선 ${km(off)} 넘게 떨어진 ${s.name}${eul(s.name)} 빼고, ${said.replace(/^[^:]+: 식사할 곳이 없어 /u, "")}`);
  }
  return out;
}

/** A meal for a day with no slot left for it (repair 4, when addMeal finds none — a packed day whose closed stops were
 *  all swapped): a stop the code put in itself (swapped in for a closed one, or added to an empty stretch; never a
 *  meal), inside the meal's window and nearest its aim, gives up its place when the meal then fits; the stops the
 *  model chose stay — unless `any` (planner.settle, the code's own first). dayOf: the reader's day, read again after
 *  the stop is out. Returns the reader's words, or ''. */
function mealInstead(plan, d, dayOf, m, c, kb, { max = near(c, "meal"), any = false, again = false, wide = false } = {}) {
  const own = dayOf().own;
  if (own.length < 2) return "";
  const mine = own.filter((s) => (any || s.by === "site" || s.by === "swap") && s.role !== "meal" && !s.pin && hm(s.start) < m.near[1] && hm(s.end) > m.near[0])
    .sort((a, b) => Number(!a.by) - Number(!b.by) || Math.abs(hm(a.start) - m.at) - Math.abs(hm(b.start) - m.at));
  for (const x of mine) {
    const j = d.stops.indexOf(x);
    d.stops.splice(j, 1);
    const said = addMeal(plan, d, dayOf(), m, c, kb, x, max, again, wide);
    if (said) return said;
    d.stops.splice(j, 0, x);
  }
  return "";
}

// ------------------------------------------------------------------ meals as the reader eats them (round 7)
// live check 2026-10-19 (the real model on the public server, 20 plans, all 'ready'): a day of 11:00–21:00 with four
// meals — the model's 15:00 아리랑 and 20:00 OO일식 sat outside the windows, so the code added 유정초밥 at 12:00
// (dropping 이당미술관) and 해담 at 18:00; a 국수 lunch at 10:30 and a lunch the code added at 12:10, the museum
// squeezed between; two two-hour meals on one day.
const HOLE = 60;   // a whole move of a meal into its window leaves no stretch longer than this that the code would not
                   // fill (IDLE) — or than the longest the day had

/** The meals a day must have (repair 4's rule): each lunch or dinner its reader's day spans — or, on an edit, the plan
 *  before had — unless the reader eats elsewhere. */
function mealNeeds(plan, c, kb, edit, i) {
  const day = readerDay(plan, c, i, kb);
  if (!day) return [];
  return ["lunch", "dinner"].filter((kind) => !eatsElsewhere(kind, ...eatsWords(c, edit))
    && (spans(day, MEALS[kind]) || !!(edit && edit.plan.days[i] && mealIn(edit.plan.days[i].stops, MEALS[kind], kb))));
}

/** The stretch a stop left between P and N (stops of day d, either may be null) taken up by the stops next to it: the
 *  one after it starts sooner (from P's end and the leg's margin, `lo` at the earliest), then the one before it ends
 *  later — each a visit or a café (a meal would move off its time, a stay is the night's), within its hours that date,
 *  its break and plan_geo.stretchMax. Changes them; returns the reader's words for each. */
function takeUp(d, P, N, c, kb, lo = 0) {
  const bits = [];
  const plain = (s) => s && (s.role === "visit" || s.role === "cafe");
  if (plain(N)) {
    const w = windowOf(dayInfo(kb, d.date, N.page));
    const na = Math.max(P ? hm(P.end) + marginOf(P.page, N.page, c, kb) : lo, hm(N.end) - stretchMax(N), w.open, lo);
    if (na < hm(N.start) && na <= w.last && !inBreak((kb.docs[N.page] || {}).f || {}, na, hm(N.end))) {
      bits.push(`${N.name} 시작을 ${N.start}에서 ${hhmm(na)}${ro(hhmm(na))} 당겼습니다`);
      N.start = hhmm(na);
    }
  }
  if (plain(P) && N) {
    const w = windowOf(dayInfo(kb, d.date, P.page));
    const nb = Math.min(hm(N.start) - marginOf(P.page, N.page, c, kb), hm(P.start) + stretchMax(P), w.close);
    if (nb > hm(P.end) && !inBreak((kb.docs[P.page] || {}).f || {}, hm(P.start), nb)) {
      bits.push(`${P.name} 끝을 ${P.end}에서 ${hhmm(nb)}${ro(hhmm(nb))} 늦췄습니다`);
      P.end = hhmm(nb);
    }
  }
  return bits;
}

// the longest stretch of day i with no stop that the code leaves as it is (IDLE or less: a longer one it fills —
// repair 5, settle 7), the reader's day read from lo to hi at least (the day before a change)
function holeOf(plan, c, i, kb, lo = Infinity, hi = -Infinity) {
  const day = readerDay(plan, c, i, kb);
  if (!day) return 0;
  return Math.max(0, ...idleGaps({ ...day, lo: Math.min(day.lo, lo), hi: Math.max(day.hi, hi) }).map((g) => g.minutes).filter((n) => n <= IDLE));
}

/** The day's lunch or dinner `s`, on its side but outside its window (plan_state.MEALS), moved whole into the window —
 *  to its first start from before it, to its last from after it — with the stops it pushes (shiftPlan: their lengths,
 *  hours, margins and meals kept, the day's bounds), the stretch it leaves behind taken up by the stop on that side
 *  (takeUp); kept only when no stretch of the day that the code leaves as it is grows past HOLE (or the longest the day
 *  had). Returns the reader's words, or '' (it then stays where it is: the meal all the same). */
function toWindow(plan, d, i, s, m, c, kb) {
  const later = (hm(s.start) + hm(s.end)) / 2 < m.near[0];
  const by = later ? m.first - hm(s.start) : hm(s.start) - m.last;
  if (by <= 0) return "";
  const day = readerDay(plan, c, i, kb);
  if (!day) return "";
  const before = holeOf(plan, c, i, kb);
  const snap = d.stops.map((x) => [x, x.start, x.end]);
  const moves = shiftPlan(d, d.stops.indexOf(s), by, later ? 1 : -1, c, kb, boundsOf(plan, i, c, kb), s);
  if (!moves) return "";
  const moved = shiftDone(moves, later ? 1 : -1);
  const own = d.stops.filter((x) => x.role !== "stay");
  const j = own.indexOf(s);
  const bits = later ? takeUp(d, own[j - 1] || null, s, c, kb) : takeUp(d, s, own[j + 1] || null, c, kb);
  if (holeOf(plan, c, i, kb, day.lo, day.hi) > Math.max(before, HOLE)) {
    for (const [x, a, b] of snap) Object.assign(x, { start: a, end: b });
    return "";
  }
  return `${s.name}: ${m.label} 시간에 맞춰 ${moved}${bits.length ? ` — ${bits.join(", ")}` : ""}`;
}

/** The meals an edit left as the reader's page has them (plan_state.keptMeal: the same place, start and end, the
 *  request not about that meal), marked on the stops (s.kept — never sent: finish lists a stop's fields): no whole
 *  move crosses one (shiftPlan, plan_build.shiftStops), no cut shortens one (plan_geo.keepOf, plan_build keepSeed),
 *  no stretch lengthens one (settle 7, plan_build lengthen), no leg's fix drops one (settle 5) — round-6 final
 *  verifier: a café request moved the lunch 50 minutes earlier as part of a whole move; a drop stretched the lunch
 *  next to it by 30 minutes. The marks are made afresh at each step (repair, settle): a meal moved is no longer one.
 *  The stops the reader pinned (고정 — edit.pins, operator 2026-10-23) are marked here too (s.pin, never sent either):
 *  no swap takes one out (swapIn), no fix drops one (repair 1, settle, noRepeats, tidyMeals, mealInstead, offWay), a
 *  day built again keeps it (settle) — its times may still move like any stop's; one that cannot stand makes the edit
 *  fail with the reason (makePlan pinWords). */
function markKept(plan, edit, kb) {
  plan.days.forEach((d, i) => {
    const kept = keptMeal(edit, i, kb);
    const pins = pinsOf(edit, i);
    for (const s of d.stops) {
      if (kept(s)) s.kept = true;
      else delete s.kept;
      if (pins.includes(s.page)) s.pin = true;
      else delete s.pin;
    }
  });
}

/** The meals of each day as the reader eats them — at most one lunch and one dinner (operator 2026-10-19, after the
 *  live check above), before the code adds any (repair 4) and again as settle starts (settleFit):
 *  1. a meal at a café or a bakery is a café stop;
 *  2. a meal longer than MEAL_LONG ends at MEAL_LONG (the model's own length stays up to it), its time to the stop
 *     after it (takeUp: it starts sooner) — what is left a stretch the code fills when it is long (repair 5, settle 7);
 *  3. a meal beyond the day's lunch and dinner (plan_state.mealRoles: a second on a side; a breakfast or a late snack
 *     on a day that has or needs both) goes, its time to the stops next to it (takeUp), else to a place (fillGap);
 *  4. the day's lunch or dinner outside its window moves whole into it when its hours and the stops next to it allow
 *     (toWindow) — else it is that meal where it is (plan_state.mealIn reads it so), and the code adds none.
 *  The code adds no meal within MEAL_APART minutes of another (addMeal, settle 6, plan_build.placeMeal). Changes plan;
 *  returns the reader's lines. */
function tidyMeals(plan, c, kb, edit = null, { fill = false } = {}) {
  const out = [];
  const many = plan.days.length > 1;
  const dayW = (i) => (many ? `${i + 1}일차 ` : "");
  // the reader's words of what they want to eat (plan_state.likeWords: '국수 먹고 싶어요' → 국수) — the place they name
  // is the day's meal before another on its side (round-6 verifier: the 국수 lunch went for the code's window lunch)
  const likes = likeWords(c.note, edit && edit.request);
  const asked = edit ? likeWords(edit.request) : [];
  plan.days.forEach((d, i) => {
    const own = () => d.stops.filter((s) => s.role !== "stay");
    const lo = i === 0 ? ((readerDay(plan, c, i, kb) || {}).lo ?? 0) : 0;
    // an edit's meal left as it was on the reader's page stays as it is — never moved, cut or dropped — unless the
    // request is about it (plan_state.keptMeal; round-6 verifier: '카페 하나 더' moved the dinner by an hour)
    const kept = keptMeal(edit, i, kb);
    // (a café stop read as a meal — 1b — comes after the meals the model gave as meals)
    const rank = (s) => (kept(s) || s.pin ? 0 : liked(kb.docs[s.page], likes) ? 1 : s.asMeal ? 3 : 2);
    // 1. a café or a bakery as a meal (settle 0's words)
    for (const s of d.stops.filter((x) => x.role === "meal" && isCafe(kb.docs[x.page]))) {
      s.role = "cafe";
      out.push(`${dayW(i)}${s.name}: 카페·빵집이라 식사가 아닌 카페로 두었습니다`);
    }
    // 1b. a restaurant that serves meals given as a café for longer than SNACK_MAX: a meal, so the rules below hold for
    // it (round-6 final verifier: '13:30-17:30 cafe 궁전갈치찜', '12:10-14:40 cafe 장가네' right after a lunch — no meal
    // rule read them) — not a snack an edit asks for, nor one the reader's page has as it is
    const sent = editPages(edit, i, kb) && new Set(((edit.plan.days[i] || {}).stops || []).map((x) => `${kb.keyFor(x.page) || x.page}|${x.start}|${x.end}|${x.role}`));
    for (const s of d.stops.filter((x) => x.role === "cafe" && isMeal(kb.docs[x.page]) && hm(x.end) - hm(x.start) > SNACK_MAX)) {
      if (edit && (SNACK.test(edit.request) || liked(kb.docs[s.page], asked) || edit.request.includes(s.name))) continue;
      if (sent && sent.has(`${s.page}|${s.start}|${s.end}|cafe`)) continue;
      s.role = "meal";
      s.asMeal = true;
      out.push(`${dayW(i)}${s.name}: 식사가 되는 음식점에서 ${span(hm(s.end) - hm(s.start))} 머물러 카페가 아닌 식사로 두었습니다`);
    }
    // (and one of SNACK_MAX or less in the window of a lunch or dinner the day needs and has none of: that meal — round 7
    // review A07: '갈비스토리' as a café before the dinner hour, a restaurant put in 289 m from it, then it went as a
    // second meal; in the window only: one before it, read as the meal, stayed a 16:00 dinner more often than it moved)
    for (const kind of ["lunch", "dinner"]) {
      const m = MEALS[kind];
      if (mealIn(d.stops, m, kb) || !mealNeeds(plan, c, kb, edit, i).includes(kind)) continue;
      const s = d.stops.find((x) => x.role === "cafe" && isMeal(kb.docs[x.page]) && !isCafe(kb.docs[x.page]) && inMealWindow(x, m)
        && !(edit && (SNACK.test(edit.request) || liked(kb.docs[x.page], asked) || edit.request.includes(x.name)))
        && !(sent && sent.has(`${x.page}|${x.start}|${x.end}|cafe`)));
      if (!s) continue;
      s.role = "meal";
      s.asMeal = true;
      out.push(`${dayW(i)}${s.name}: 그날 ${m.label}이 없어 식사가 되는 음식점인 이곳을 카페가 아닌 ${m.label}으로 두었습니다`);
    }
    // 1c. a restaurant given as a place to visit (live check 2026-10-19: '17:00–18:00 visit 진갈비', the day's dinner
    // shown as a sight): a café or a bakery a café, one that serves meals a meal — the rules below then hold for it
    for (const s of d.stops.filter((x) => x.role === "visit" && ((kb.docs[x.page] || {}).f || {}).kd === "food")) {
      if (sent && sent.has(`${s.page}|${s.start}|${s.end}|visit`)) continue;
      const doc = kb.docs[s.page];
      if (isCafe(doc)) s.role = "cafe";
      else if (isMeal(doc)) Object.assign(s, { role: "meal", asMeal: true });
      else continue;
      out.push(`${dayW(i)}${s.name}: 음식점이라 둘러볼 곳이 아닌 ${s.role === "cafe" ? "카페" : "식사"}로 두었습니다`);
    }
    // 2. a meal longer than MEAL_LONG
    for (const s of d.stops.filter((x) => x.role === "meal" && hm(x.end) - hm(x.start) > MEAL_LONG && !kept(x))) {
      const was = `${s.start}~${s.end}`;
      s.end = hhmm(hm(s.start) + MEAL_LONG);
      const list = own();
      const N = list[list.indexOf(s) + 1] || null;
      const bits = takeUp(d, s, N, c, kb);
      out.push(`${dayW(i)}${s.name}: 식사는 ${MEAL_LONG}분까지로 잡아 ${was}에서 ${s.start}~${s.end}${ro(s.end)} 줄였습니다${bits.length ? ` — ${bits.join(", ")}` : ""}`);
      // (the last pass, after settle: what is still a long stretch after it is filled here — nothing comes after)
      const day = fill && readerDay(plan, c, i, kb);
      const g = day && idleGaps(day).find((x) => x.at === (N ? day.own.indexOf(N) : day.own.length) && x.minutes > IDLE);
      const filled = g ? fillGap(plan, d, day, g, c, kb) : "";
      if (filled) out.push(`${dayW(i)}${filled}`);
    }
    // 3. a meal beyond the day's lunch and dinner
    const roles = mealRoles(d.stops, kb, mealNeeds(plan, c, kb, edit, i), wantsOther(c.note, edit && edit.request), rank);
    for (const s of roles.extra.filter((x) => !kept(x) && !x.pin)) {
      // a snack the edit asked for ('간식으로 칼국수 한 그릇', or the place its request names) is a stop of its own, not
      // a second meal: a café stop at that restaurant (round-6 verifier: the reader's 15:00 칼국수 was dropped)
      if (edit && (SNACK.test(edit.request) || liked(kb.docs[s.page], asked) || edit.request.includes(s.name))) {
        s.role = "cafe";
        out.push(`${dayW(i)}${s.name}: 바꿔 달라는 말대로 그날 식사가 아닌 간식 자리(카페)로 두었습니다`);
        continue;
      }
      const list = own();
      const j = list.indexOf(s);
      const P = list[j - 1] || null, N = list[j + 1] || null;
      const kind = mealKind(hm(s.start), hm(s.end));
      const keep = kind && roles[kind];
      // (else the day's meal it starts too soon after or before: MEAL_APART)
      const closest = ["lunch", "dinner"].map((k) => roles[k] && { k, x: roles[k], gap: Math.abs(hm(roles[k].start) - hm(s.start)) })
        .filter((y) => y && y.gap < MEAL_APART).sort((p, q) => p.gap - q.gap)[0];
      d.stops.splice(d.stops.indexOf(s), 1);
      const bits = takeUp(d, P, N, c, kb, i === 0 ? lo : hm(s.start));
      // what is still a long stretch: a place (repair 5's fill, from the stop before it)
      const day = readerDay(plan, c, i, kb);
      const g = day && idleGaps(day).find((x) => x.at === (N ? day.own.indexOf(N) : day.own.length) && x.minutes >= FILL_MIN + 30);
      const fill = g ? fillGap(plan, d, day, g, c, kb) : "";
      const why = keep ? `그날 ${MEALS[kind].label}은 ${keep.name}에서 먹어`
        : closest ? `${MEALS[closest.k].label}(${closest.x.name})과 시작이 ${span(closest.gap)}밖에 차이 나지 않아` : "하루 식사는 점심·저녁 한 번씩으로 잡아";
      out.push(`${dayW(i)}${s.name}: ${why} 일정에서 뺐습니다`
        + `${bits.length ? ` — ${bits.join(", ")}` : ""}`);
      if (fill) out.push(`${dayW(i)}${fill}`);
    }
    // 4. the lunch and the dinner into their windows
    for (const kind of ["lunch", "dinner"]) {
      const m = MEALS[kind];
      const s = mealIn(d.stops, m, kb, rank);
      // (a meal whose time the reader's words set — '점심은 2시쯤', '저녁을 늦게' — stays when the model put it there:
      // plan_state.saysMealTime; and an edit's meal left as it was)
      if (!s || inMealWindow(s, m) || kept(s) || saysMealTime(kind, c.note, edit && edit.request)) continue;
      const said = toWindow(plan, d, i, s, m, c, kb);
      if (said) out.push(`${dayW(i)}${said}`);
    }
    // 5. a lunch and a dinner the day needs, starting within MEAL_APART of each other where neither could move into
    // its window (a 15:00 lunch and a 16:10 dinner — round-6 verifier: two meals back to back): the one outside its
    // window (else the later; never one the reader's words name or an edit kept) gives way to that meal put in its
    // window by the code (addMeal: MEAL_APART from the other) — kept only when it can be, else both stay as they are
    const L = mealIn(d.stops, MEALS.lunch, kb, rank), D = mealIn(d.stops, MEALS.dinner, kb, rank);
    if (L && D && Math.abs(hm(L.start) - hm(D.start)) < MEAL_APART && !kept(L) && !kept(D)) {
      const needs = mealNeeds(plan, c, kb, edit, i);
      const free = [L, D].filter((x) => !x.pin && !liked(kb.docs[x.page], likes) && !saysMealTime(x === L ? "lunch" : "dinner", c.note, edit && edit.request));
      const go = free.find((x) => !inMealWindow(x, x === L ? MEALS.lunch : MEALS.dinner)) || free.sort((x, y) => hm(y.start) - hm(x.start))[0];
      if (go && needs.includes("lunch") && needs.includes("dinner")) {
        const kind = go === L ? "lunch" : "dinner", stay = go === L ? D : L;
        const was = d.stops.map((x) => ({ ...x }));
        const list = own();
        const j = list.indexOf(go);
        d.stops.splice(d.stops.indexOf(go), 1);
        const bits = takeUp(d, list[j - 1] || null, list[j + 1] || null, c, kb, i === 0 ? lo : hm(go.start));
        const day = readerDay(plan, c, i, kb);
        const added = day ? addMeal(plan, d, day, MEALS[kind], c, kb) : "";
        const put = mealIn(d.stops, MEALS[kind], kb);
        if (added && put && Math.abs(hm(put.start) - hm(stay.start)) >= MEAL_APART) {
          out.push(`${dayW(i)}${go.name}: ${MEALS[kind === "lunch" ? "dinner" : "lunch"].label}(${stay.name})과 시작이 ${span(Math.abs(hm(go.start) - hm(stay.start)))}밖에 차이 나지 않아 일정에서 뺐습니다${bits.length ? ` — ${bits.join(", ")}` : ""}`);
          out.push(`${dayW(i)}${added}`);
        } else d.stops = was;
      }
    }
  });
  return out;
}

/** One place for one empty stretch (repair 5): after the stop before it (or from the day's start), the places
 *  nearest that stop (then the one after it) that fit the reader's likings and needs, FILL_MAX minutes when the
 *  stretch holds them with the margins, else no fewer than FILL_MIN. Returns the reader's words, or '' when nothing
 *  fits. */
function fillGap(plan, d, day, g, c, kb, max = near(c, "fill")) {
  const at = (s) => ((kb.docs[s.page] || {}).f || {}).g;
  const P = day.own[g.at - 1] || null, N = day.own[g.at] || null;
  // (the stops next to it, else the nearest before and after it the site has a point for — round 7: a lunch with no
  // point before an empty afternoon left it empty)
  const next = [P, N].filter((s) => s && at(s));
  const anchors = next.length ? next : [day.own.slice(0, g.at).reverse().find(at), day.own.slice(g.at).find(at)].filter(Boolean);
  for (const anchor of anchors) {
    const said = fillFrom(plan, d, day, g, P, N, anchor, c, kb, max);
    if (said) return said;
  }
  return "";
}
function fillFrom(plan, d, day, g, P, N, anchor, c, kb, max = near(c, "fill")) {
  const at = (s) => ((kb.docs[s.page] || {}).f || {}).g;
  // the likings the data can read as places to visit (history, nature, islands, alleys, experience); none picked:
  // any place to visit. 카페·빵집 adds the cafés.
  const likes = c.prefs.filter((p) => PREF_TYPES[p] || city().prefRegions[p] || city().prefTypes[p]);
  const cafe = c.prefs.includes("cafe");
  const nextCafe = [P, N].some((s) => s && (s.role === "cafe" || isCafe(kb.docs[s.page])));
  const home = regionOf(kb.docs[anchor.page]);
  const fees = knownFees(plan, c, kb);
  const pick = nearestOpen({ kb, c, date: d.date, at: at(anchor), max, taken: new Set(plan.days.flatMap((x) => x.stops.map((st) => st.page))),
    // (a café never next to a café or a bakery: wave B 2026-10-19, OO중동호떡 then 리투스카페 filled an evening)
    fits: (x) => ((x.f.kd === "attraction" && (!likes.length || likes.some((p) => prefFits(p, x)))) || (cafe && isCafe(x) && !nextCafe))
      && codeFits(c, x.f, x.f.kd === "food" ? "cafe" : "visit"),
    // (without a car, a place in the 권역 of the stop it goes after first — round 7 review A02: a family sent 3 km from
    // OO공원 to OO문화원 in OO; first, not only: held to it, more days failed and were built again)
    rank: (x) => { const rr = rainRank(c, x.f); return rr === null ? null : [c.move !== "car" && home && regionOf(x.doc) !== home ? 1 : 0, rr, freeRank(c, x.f)]; },
    slot: (x) => {
      const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
      const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
      const a = Math.ceil((P ? hm(P.end) + mP : g.from) / 5) * 5;
      const room = Math.floor(((N ? hm(N.start) - mN : endBefore(day, g.to, x.page, c, kb)) - a) / 5) * 5;
      const long = isCafe(x.doc) ? FILL_MIN : FILL_MAX;
      return [...new Set([Math.min(long, room), FILL_MIN])].filter((n) => n >= FILL_MIN && n <= room).map((n) => ({ a, b: a + n }));
    },
    put: (x) => {
      const stop = { page: x.page, name: x.name, start: hhmm(x.a), end: hhmm(x.b), role: x.f.kd === "food" ? "cafe" : "visit" };
      insertAt(d, P, N, stop);
      const bad = overBudget(plan, c, kb, fees);
      d.stops.splice(d.stops.indexOf(stop), 1);
      return !bad;
    } });
  if (!pick) return "";
  const role = pick.f.kd === "food" ? "cafe" : "visit";
  insertAt(d, P, N, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), role, why: "", by: "site" });
  const why = [...likes.filter((p) => prefFits(p, pick.doc)).map((p) => prefLabel(p)), ...(role === "cafe" ? [prefLabel("cafe")] : []),
    ...(c.needs.includes("rain") && rainRank(c, pick.f) === 0 && pick.f.kd === "attraction" ? ["실내"] : []), openWords(pick.open)];
  return `빈 시간 ${hhmm(g.from)}~${hhmm(g.to)}(${span(g.minutes)}): ${day.own.indexOf(anchor) < g.at ? "앞" : "다음"} 장소 ${anchor.name}에서 가까운 ${pick.name}(직선 ${km(pick.m)}, `
    + `${why.join(" · ")})${eul(pick.name)} ${hhmm(pick.a)}~${hhmm(pick.b)}에 넣었습니다`;
}

// the longest a restaurant that serves meals stays a café stop (a snack): longer, it is a meal (tidyMeals 1b)
const SNACK_MAX = 60;

// a plan the code made whole from the site's data (no stop of the model's): its one line in 'fixed', always first and
// always alone, starting '일정 전체:' — and every stop of it added: true (the page tells such a plan by these;
// docs/handover/planner.md '화면과의 계약')
export const CODE_PLAN_LINE = "일정 전체: AI가 조건에 맞는 일정을 내지 못해 사이트 자료로 일정을 짰습니다";
export const CODE_PLAN_BUSY = "일정 전체: AI 응답을 받지 못해 사이트 자료로 일정을 짰습니다";
export const CODE_PLAN_SETTLE = "일정 전체: AI가 고른 곳으로는 조건을 다 맞출 수 없어 사이트 자료로 일정을 새로 짰습니다";
// (review 2026-10-22 S7) a plan the code made whole reads the reader's 하고 싶은 말 only for the meals (that they eat
// elsewhere, when — plan_state.eatsElsewhere, saysMealTime): a place or a dish it asks for is not looked for. Said once
// with what holds for the plan (aware, under the needs: the page shows the kinds it knows), on a course of the code's
// that stays the final one — the AI gave no plan, was busy, or its places could not be settled —, never on the course
// sent first (CODE_PLAN_EARLY: the AI is still at it) nor on a shared one (a link carries no note)
export const CODE_NOTE_LINE = "하고 싶은 말의 장소·음식 요청은 사이트가 짠 코스에 넣지 못했어요 — 바꾸고 싶은 점에 다시 적어 주세요";
const CODE_FINAL = new Set([CODE_PLAN_LINE, CODE_PLAN_BUSY, CODE_PLAN_SETTLE]);
/** aware with CODE_NOTE_LINE when the plan is the code's own as the final one (fixed: its one line) and the reader wrote
 *  a note — once; without it otherwise. */
export function noteAware(aware, c, fixed) {
  const rest = (aware || []).filter((x) => x.t !== CODE_NOTE_LINE);
  return c && c.note && codeBuilt({ fixed }) && CODE_FINAL.has(fixed[0]) ? [...rest, { k: "note", t: CODE_NOTE_LINE }] : rest;
}
/** A finished course of the code's (the one sent first) as the final plan: its one line and what holds for it. */
const codeFinal = (plan, line) => ({ ...plan, fixed: [line], aware: noteAware(plan.aware, plan.conditions, [line]) });

// ------------------------------------------------------------------ settle: every plan the page gets is finished
// (operator 2026-10-18: '이런 거 좀 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게 하라니까' — a 1-day result showed
// '확인할 것이 남은 초안이에요'; before it '조건을 다 맞추지 못한 초안' and '코스를 만들지 못했습니다')
const STAY_LATEST = 23 * 60 + 29;
const NEED_WORD = { wheelchair: "휠체어", stroller: "유모차", parking: "주차", free: "입장료 없는 곳", rain: "비 와도 실내 위주" };

/** The last step of every plan, after repair, align and the check: what the check still finds is put right by the
 *  code, the targeted fix of each kind first, until nothing is left —
 *  0. once, before the check: a night's stay on the trip's last day ahead of a stop goes; the same place twice in a
 *     row overlapping becomes one; a stop whose data says 'no' to a hard need the reader picked (휠체어, 유모차, 입장료
 *     없는 곳, 주차) becomes the nearest place of its kind the data says fits (swapIn) or goes; a visit whose data says
 *     nothing of such a need becomes one nearby the data says fits, when there is one; a stop a date rule may close
 *     that day (a 설·추석·공휴일 rule) becomes a place sure to be open nearby, when there is one;
 *  then, up to three rounds while the check finds something, by kind:
 *  1. closed that day: swapped (swapIn), else out; hours: cut to the hours that date, else swapped, else out;
 *  2. rain with a second outdoor visit: swapped for one that is not outdoor, else out — the ones the reader did not
 *     ask for (plan_build.rainAsked), all of them when one was asked for, and an outdoor place asked for stays
 *     (operator 2026-10-23); the budget: the dearest paid visit swapped for a free or cheaper one, else out;
 *  3. before the reader's start or after their end, and the station's margins: cut, else out;
 *  4. a night's stay: moved after the day's last stop (its leg's margin, its check-in, by 23:29), the last stop cut
 *     to the reader's end to make room; a night with none gets another night's or the nearest that can start by 23:29;
 *  5. a leg: its margin, from the whole margin down to the least the check allows, the earlier stop ending sooner or
 *     the later starting later (a stay moving whole) — else the stop the code put in goes, else the farther one;
 *  6. a meal: a restaurant the model gave as a visit or a café becomes the meal; else one is added nearer, then
 *     farther, then in place of a stop the code put in, then of a visit of the model's;
 *  7. an empty stretch: filled (NEAR.fill, then twice it), else the stop before it longer (its hours, 3 hours at most),
 *     else the one after it sooner;
 *  last, a day still flagged is built again around its own stops (plan_build.buildDay, the model's kept in order),
 *  else built again whole; a trip still flagged is the code's own plan (plan_build.buildPlan), which preflight has
 *  shown exists. stats: counts (rounds, rebuilt days, the code's plan). Changes plan; returns the reader's lines. */
export function settle(plan, c, kb, edit = null, stats = {}) {
  const out = [];
  markKept(plan, edit, kb);
  const many = plan.days.length > 1;
  const dayW = (i) => (many ? `${i + 1}일차 ` : "");
  stats.rounds = 0;
  stats.rebuilt = stats.rebuilt || 0;
  out.push(...settleFit(plan, c, kb, dayW, edit));
  // a place once a trip, a restaurant as a café never between meals (live check 2026-10-19) — before the rounds, which
  // fill what goes
  out.push(...noRepeats(plan, c, kb, edit, dayW));
  // the meals as the reader eats them again (round 7): a plan that skipped repair (a fix's plan finished as it is) or
  // that the fixes since changed
  out.push(...tidyMeals(plan, c, kb, edit));
  for (let round = 0; round < 3; round += 1) {
    if (!planFlags(plan, c, kb, edit).list.length && !plan.days.some((d) => farOnes(d.stops, c, kb).length)) break;
    stats.rounds += 1;
    const said = settleRound(plan, c, kb, edit, dayW);
    out.push(...said);
    if (!said.length) break;
  }
  // a day still flagged: built again around its stops, else whole
  let left = planFlags(plan, c, kb, edit).list;
  const whole = [];   // the days built again that kept none of the model's places
  stats.left = left.map((x) => x.kind);
  // (and a day where a place the code put in is still past the cap from both stops next to it: round 6)
  const far = plan.days.map((d, i) => (farOnes(d.stops, c, kb).length ? i : -1)).filter((i) => i >= 0);
  for (const i of [...new Set([...left.map((x) => x.day), ...far])].filter((x) => x >= 0)) {
    const d = plan.days[i];
    const others = plan.days.filter((_, k) => k !== i);
    const taken = new Set(others.flatMap((x) => x.stops.map((s) => s.page)));
    const prevStay = i > 0 ? plan.days[i - 1].stops.find((s) => s.role === "stay") : null;
    // (where the day before ends: its night's stay, else its last stop with a point — round 7 review A09: 섬 리조트
    // has none, and the day after it was built 32 km off in the old town)
    const opts = { taken, plan, edit, anchor: i > 0 ? (prevStay && gOf(kb, prevStay.page)) || lastPoint(kb, plan.days[i - 1].stops) : null,
      stay: d.stops.find((s) => s.role === "stay" && !s.by) || null, otherStay: others.map((x) => x.stops.find((s) => s.role === "stay" && mayPut(kb, s.page))).find(Boolean) || null };
    if (stats.trace) opts.trace = stats.trace;   // a debugging aid: why each try of the day builder failed
    // an edit keeps the day the model changed, or nothing: a day built anew would be a change the reader never asked
    // for (round-5 verifier: an edit came back as an unrelated trip)
    // (within the cap first — plan_geo.CAP —, then with the rings past it: round 6). The day around its own stops past
    // the cap comes before a day built anew within it when it keeps at least half the model's places of that day — a
    // farther meal rather than the AI's island day gone for the code's town day (round-6 verifier: 섬 권역 by car,
    // 'nature' then unmet)
    const model = d.stops.filter((s) => s.role !== "stay" && !s.by);
    // an edit's day built again keeps the places new to the edit (s.asked) — else it is no answer to the request
    // (round-6 final verifier: the café asked for went in the rebuild of a full day)
    // (and the places the reader pinned on that day: a day built again without one is no answer either)
    const asked = [...d.stops.filter((s) => s.asked), ...pinsOf(edit, i).map((page) => ({ page }))];
    const keeps = (x) => !x || !edit || asked.every((s) => x.stops.some((y) => y.page === s.page));
    const seededWide = () => { const x = buildDay(c, kb, i, d.date, { ...opts, seed: d.stops, wide: true }); return keeps(x) ? x : null; };
    let built = buildDay(c, kb, i, d.date, { ...opts, seed: d.stops });
    if (!keeps(built)) built = null;
    // none around the model's own stops within the cap — or one only because it ends at the night's stay: the stay ends
    // the day as it is after all, when that clears it (stayEnds — round 7), before the day goes for one past the cap or
    // the code's own
    if ((!built || built.stops.some((s) => s.role === "stay" && s.ends)) && stayEndsDay(plan, i, c, kb, edit)) continue;
    if (!built) {
      const around = model.length ? seededWide() : null;
      built = around && around.kept.filter((s) => !s.by).length * 2 >= model.length ? around
        : (edit ? null : buildDay(c, kb, i, d.date, opts)) || around || (model.length ? null : seededWide())
          || (edit ? null : buildDay(c, kb, i, d.date, { ...opts, wide: true }));
    }
    if (!built) continue;
    const before = d.stops;
    d.stops = built.stops;
    stats.rebuilt += 1;
    out.push(`${dayW(i)}${rebuiltWords(before, d.stops)}`);
    if (model.length && !built.kept.some((s) => !s.by)) whole.push(i);
  }
  // the model's sentences of a day built again with none of its places go (round 7 review A09: '둘째 날은 일출을 보기
  // 위해 이른 아침에 섬 전망과 해변을 돌며' stayed over a day of the old town)
  if (whole.length) {
    let n = 0;
    const keep = (x) => (whole.some((i) => namesDay(x, i, plan.days.length, plan.days[i].date)) ? (n += 1, false) : true);
    plan.summary = dropSentences(plan.summary, keep);
    plan.notes = plan.notes.map((x) => dropSentences(x, keep)).filter(Boolean);
    if (n) out.push(`AI 설명: 사이트 자료로 다시 짠 ${whole.map((i) => `${i + 1}일차`).join("·")}${eul(`${whole.at(-1) + 1}일차`)} 말하는 문장 ${n}개를 뺐습니다`);
    if (!plan.summary) plan.summary = codeText(plan, c, kb).summary;
    // (and the title, when half the days or more are the site's: round 7 review A16 — '봄 섬 바다와 야경, 섬 권역 2박 3일'
    // over two days of the old town)
    if (whole.length * 2 >= plan.days.length) {
      const title = codeText(plan, c, kb).title;
      if (title !== plan.title) out.push(`제목: 사이트 자료로 다시 짠 날이 많아 '${plan.title}'에서 '${title}'${ro(title)} 바꿨습니다`);
      plan.title = title;
    }
  }
  // (and a day built again around its night's stay, moved to its check-in: the stay ends it there — round 7)
  stayEnds(plan, c, kb, edit);
  // without a car, the evening near a night's stay the site has only far away (live check 2026-10-19: dinner on 섬
  // at 19:30, then a 16 km ride to the nearest stay the data has, at night)
  if (!planFlags(plan, c, kb, edit).list.length) out.push(...dinnerNearStay(plan, c, kb, edit, dayW));
  // the meals as the reader eats them once more, after the rounds (round-6 verifier: an hours move brought the model's
  // breakfast within MEAL_APART of the lunch the code added, the reader's end left two lunches, a restaurant made the
  // meal in round 6 ran 150 minutes) — kept only when it leaves the plan as finished as it was (a dropped meal may
  // leave a stretch nothing fills): else the plan as the rounds left it
  left = planFlags(plan, c, kb, edit).list;
  if (!left.length && !plan.days.some((d) => farOnes(d.stops, c, kb).length)) {
    markKept(plan, edit, kb);
    const was = plan.days.map((d) => d.stops.map((s) => ({ ...s })));
    const said = tidyMeals(plan, c, kb, edit, { fill: true });
    if (said.length && (planFlags(plan, c, kb, edit).list.length || plan.days.some((d) => farOnes(d.stops, c, kb).length))) {
      plan.days.forEach((d, i) => { d.stops = was[i]; });
    } else out.push(...said);
  }
  // the budget across the days, or anything else left: the trip as the code makes it (preflight's) — never on an edit
  // (makePlan then keeps the reader's plan and says the change could not be made)
  left = planFlags(plan, c, kb, edit).list;
  if (left.length && !edit) {
    const built = buildPlan(c, kb);
    if (built.plan) {
      // the model's words were for its own places: the code's title and summary, no notes (the code's plan alone)
      Object.assign(plan, { days: built.plan.days, title: built.plan.title, summary: built.plan.summary, notes: [] });
      stats.codePlan = 1;
      out.length = 0;
      out.push(CODE_PLAN_SETTLE);
    }
  }
  return out;
}

/** A day still flagged, with a night's stay the model put in: the stay ends the day where it stands after all
 *  (plan_state.endsDay's s.ends), when that leaves the day with nothing flagged — the code could not fill the day to
 *  the end the reader set (round 7: a stay ends the day only near that end or after the dinner). settle, before a day
 *  is built again; viewPlan, for a link made before that rule (a stay at its check-in time read as the day's end). */
function stayEnds(plan, c, kb, edit = null) {
  for (const i of [...new Set(planFlags(plan, c, kb, edit).list.map((x) => x.day))].filter((x) => x >= 0)) stayEndsDay(plan, i, c, kb, edit);
}
// day i's: whether it now ends at its stay with nothing flagged
function stayEndsDay(plan, i, c, kb, edit = null) {
  const st = plan.days[i].stops.find((s) => s.role === "stay" && !s.by && !s.ends);
  if (!st) return false;
  st.ends = true;
  if (!planFlags(plan, c, kb, edit).list.some((x) => x.day === i)) return true;
  delete st.ends;
  return false;
}

// the reader's line for a day built again: the places that went and came, and the night's stay when it moved
function rebuiltWords(was, after) {
  const before = was.filter((s) => s.role !== "stay");
  const now = new Set(after.map((s) => s.page));
  const had = new Set(before.map((s) => s.page));
  const kept = before.filter((s) => now.has(s.page)).map((s) => s.name);
  const gone = before.filter((s) => !now.has(s.page)).map((s) => s.name);
  const added = after.filter((s) => s.role !== "stay" && !had.has(s.page)).map((s) => s.name);
  const list = (xs) => `${xs.join("·")}${eul(xs.at(-1))}`;
  const stayWas = was.find((s) => s.role === "stay"), stay = after.find((s) => s.role === "stay");
  const moved = stay && stayWas && stay.page === stayWas.page && stay.start !== stayWas.start ? `밤 숙소 ${stay.name}${eul(stay.name)} ${stay.start}${ro(stay.start)} 옮기고 ` : "";
  // only what changed: the places that went and came (all of the day's own kept: what was added)
  if (!gone.length) return `조건을 모두 맞추려고 이날 일정에 사이트 자료로 ${added.length ? `${list(added)} 넣고 ` : ""}${moved}시각을 맞췄습니다`;
  return `조건을 모두 맞추려고 이날 일정을 사이트 자료로 다시 짰습니다 — ${list(gone)} 빼고 ${added.length ? `${list(added)} 넣고 ` : ""}${moved}시각을 맞췄습니다`
    + `${kept.length ? ` (${kept.length}곳은 그대로)` : ""}`;
}

/** A place once a trip (live check 2026-10-19: 섬 식당 the dinner three nights running, 남도밥상 two lunches,
 *  섬 해수욕장 on two days): a later visit, meal or café at a place the plan already has becomes the nearest place of
 *  its kind the plan does not have, else goes (the rounds fill its time; a meal with none near stays). A night's stay may repeat (another night in
 *  the same bed); a place the reader's note or request names may too; an edit keeps what the reader saw. And a
 *  restaurant set as a café (a 분식 between lunch and dinner) within MEAL_APART of a meal is a third meal: it goes. */
function noRepeats(plan, c, kb, edit, dayW) {
  const out = [];
  const seen = new Map();   // page → the day it is first in
  // (a place the reader pinned is first on its own day: the copy on another day is the repeat — review of the buttons:
  // the model moved a pinned day-2 visit to day 1, pinBack put it back and both stayed)
  for (const [i, pages] of ((edit && edit.pins) || []).entries()) for (const p of pages) seen.set(p, i);
  const asked = `${c.note || ""} ${(edit && edit.request) || ""}`;
  // a stop taken out: the stops next to it take up its stretch, and what is still SOFT_IDLE or more gets a place
  // (live check 2026-10-19: a café-restaurant taken out between 15:35 and 17:35 left the two hours empty)
  const drop = (d, i, j, st) => {
    const own = d.stops.filter((x) => x.role !== "stay");
    const k = own.indexOf(st);
    const P = own[k - 1] || null, N = own[k + 1] || null;
    d.stops.splice(j, 1);
    const lo = i === 0 ? ((readerDay(plan, c, i, kb) || {}).lo ?? 0) : hm(st.start);
    const bits = takeUp(d, P, N, c, kb, lo);
    const day = readerDay(plan, c, i, kb);
    const g = day && idleGaps(day).find((x) => x.at === (N ? day.own.indexOf(N) : day.own.length) && x.minutes >= (P && N ? SOFT_IDLE : IDLE + 1));
    const fill = g ? fillGap(plan, d, day, g, c, kb) : "";
    return { bits: bits.length ? ` — ${bits.join(", ")}` : "", fill };
  };
  plan.days.forEach((d, i) => {
    const sent = editPages(edit, i, kb) && new Set(((edit.plan.days[i] || {}).stops || []).map((x) => `${kb.keyFor(x.page) || x.page}|${x.start}|${x.end}`));
    for (let j = 0; j < d.stops.length; j += 1) {
      const st = d.stops[j];
      if (st.role === "stay") continue;
      const doc = kb.docs[st.page] || {};
      const asSent = !!sent && sent.has(`${st.page}|${st.start}|${st.end}`);
      if (st.role === "cafe" && isMeal(doc) && !isCafe(doc) && !asSent && !st.pin
        && d.stops.some((x) => x !== st && x.role === "meal" && Math.abs(hm(x.start) - hm(st.start)) < MEAL_APART)) {
        const { bits, fill } = drop(d, i, j, st);
        // (a place put in fills the stop's own index: it is no repeat — nearestOpen leaves the trip's pages out)
        if (fill) seen.set(d.stops[j].page, i); else j -= 1;
        out.push(`${dayW(i)}${st.name}: 식사 앞뒤에 또 먹는 곳이라 일정에서 뺐습니다${bits}`);
        if (fill) out.push(`${dayW(i)}${fill}`);
        continue;
      }
      // the same page again, or one that goes with a page of another day (a park and a place inside it, two pages of
      // one building: knowledge.kin)
      const kin = [...((kb.kin && kb.kin.get(st.page)) || [])].find((q) => seen.has(q) && seen.get(q) !== i);
      if (!seen.has(st.page) && !kin) { seen.set(st.page, i); continue; }
      if (asSent || st.pin || (doc.t && asked.includes(doc.t))) continue;
      const why = kin ? `앞날에 들른 ${kb.docs[kin].t}${jong(kb.docs[kin].t) > 0 ? "과" : "와"} 같은 곳이라`
        : seen.get(st.page) > i ? "독자가 다른 날에 고정한 곳이라" : "앞에서 이미 들른 곳이라";
      const said = swapIn(plan, d, j, c, kb, { why });
      if (said) {
        seen.set(d.stops[j].page, i);
        out.push(`${dayW(i)}${said}`);
        continue;
      }
      // a meal with no other restaurant near (the islands have few): it stays — a day made again without it lost the
      // reader's island for the town (replay of the live check)
      if (st.role === "meal") continue;
      const { bits, fill } = drop(d, i, j, st);
      if (fill) seen.set(d.stops[j].page, i); else j -= 1;
      out.push(`${dayW(i)}${st.name}: ${why} 일정에서 뺐습니다${bits}`);
      if (fill) out.push(`${dayW(i)}${fill}`);
    }
  });
  return out;
}

/** The restaurant nearest a day's night's stay (within the cap) open for a dinner of `len` minutes that starts the
 *  leg's margin after `prev` (and no sooner than `lo`), still a dinner by its middle, with the stay after it the same
 *  evening: nearestOpen's pick, or null (no stay with a point, nothing fits). */
function stayDinner(plan, d, prev, c, kb, { lo = 0, len = MEAL_MIN } = {}) {
  const stay = d.stops.find((x) => x.role === "stay");
  const sg = stay && gOf(kb, stay.page);
  if (!sg) return null;
  const taken = new Set(plan.days.flatMap((x) => x.stops.map((s) => s.page)));
  return nearestOpen({ kb, c, date: d.date, at: sg, max: cap(c), taken,
    fits: (x) => x.f.kd === "food" && isMeal(x) && !isCafe(x) && codeFits(c, x.f, "meal"),
    rank: () => [0],
    slot: (x) => {
      const a = Math.ceil(Math.max(lo, prev ? hm(prev.end) + marginOf(prev.page, x.page, c, kb) : 0) / 5) * 5;
      const b = a + len;
      // still the dinner (its middle on the dinner side), and the stay after it the same evening
      if (mealKind(a, b) !== "dinner" || b + marginOf(x.page, stay.page, c, kb) > 23 * 60 + 29) return [];
      return [{ a, b }];
    } });
}
// the night's stay after a dinner the code put before it: the leg's margin after it, not sooner than it was
function stayAfter(d, meal, c, kb) {
  const stay = d.stops.find((x) => x.role === "stay");
  const at = Math.max(hm(stay.start), hm(meal.end) + marginOf(meal.page, stay.page, c, kb));
  const len = hm(stay.end) - hm(stay.start);
  if (at !== hm(stay.start)) Object.assign(stay, { start: hhmm(at), end: hhmm(Math.min(at + len, 23 * 60 + 59)) });
}

/** settle 6, last: a day's dinner none of the restaurants near its stops gives (live check 2026-10-19: 섬 권역 on a
 *  Tuesday — one of its three restaurants open, the lunch's —, and the day went for a town day the code built): the
 *  restaurant nearest the night's stay, after the day's last stop (stayDinner). Not on an edit (a day the reader saw
 *  keeps its places). Returns the reader's words, or ''. */
function dinnerByStay(plan, d, c, kb, edit) {
  if (edit) return "";
  const own = d.stops.filter((x) => x.role !== "stay");
  const last = own.at(-1);
  const stay = d.stops.find((x) => x.role === "stay");
  if (!last || !stay || d.stops.length >= STOPS_MAX) return "";
  const pick = stayDinner(plan, d, last, c, kb, { lo: MEALS.dinner.first });
  if (!pick) return "";
  // (wide: past the cap from the stop before it on purpose — the ride to the night's stay is the point; farOnes lets it be)
  const meal = { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), role: "meal", why: "", by: "site", wide: true };
  d.stops.splice(d.stops.indexOf(stay), 0, meal);
  stayAfter(d, meal, c, kb);
  return `저녁: 그날 장소 가까이에 그 시각에 여는 음식점이 사이트에 없어 밤 숙소 ${stay.name}에서 가까운 ${pick.name}(직선 ${km(pick.m)}, ${openWords(pick.open)})${eul(pick.name)} ${hhmm(pick.a)}~${hhmm(pick.b)}에 넣었습니다`;
}

/** Without a car, a night's stay farther than the cap from the day's last stop, that stop a dinner: the dinner becomes
 *  the nearest restaurant to the stay that is open then (the ride is made before dinner, in daylight more often than
 *  after it), moved later within the dinner's side when the ride needs it, the stay after it. The reader's 하루 끝
 *  holds that day too (planFlags — 2026-10-24 I07): a dinner that would end past it ends there when it keeps MEAL_KEEP,
 *  else the last one or two places before the dinner — a visit or a café, never one pinned or asked for — give the
 *  ride their time, each said (review 2026-10-24: with them kept, the dinner stayed on 섬 and the 28 km ride came
 *  after it, at night — what round 7 had taken out). Nothing when no such restaurant fits, or on an edit (a meal the
 *  reader saw stays). */
function dinnerNearStay(plan, c, kb, edit, dayW) {
  const out = [];
  if (c.move === "car" || edit) return out;
  plan.days.forEach((d, i) => {
    const stay = d.stops.find((x) => x.role === "stay");
    const own = d.stops.filter((x) => x.role !== "stay");
    const last = own.at(-1);
    if (!stay || !last || last.role !== "meal") return;
    const sg = gOf(kb, stay.page), lg = gOf(kb, last.page);
    if (!sg || !lg || metres(sg, lg) <= cap(c)) return;
    const before = d.stops;
    const len = hm(last.end) - hm(last.start);
    for (let k = 0; k <= 2; k += 1) {
      // (k: the places before the dinner that give the ride their time)
      const gone = own.slice(own.length - 1 - k, own.length - 1);
      if (gone.some((x) => x.pin || x.asked || (x.role !== "visit" && x.role !== "cafe"))) break;
      const prev = own[own.length - 2 - k];
      if (k && !prev) break;
      d.stops = before.filter((x) => !gone.includes(x)).map((x) => ({ ...x }));
      const pick = stayDinner(plan, d, prev, c, kb, { lo: k ? MEALS.dinner.first : hm(last.start), len });
      if (!pick) { d.stops = before; continue; }
      // (a dinner past the reader's end ends at it, kept MEAL_KEEP and on the dinner's side)
      const b = pick.b > hm(c.end) && hm(c.end) - pick.a >= Math.min(MEAL_KEEP, len) && mealKind(pick.a, hm(c.end)) === "dinner" ? hm(c.end) : pick.b;
      const meal = d.stops[before.indexOf(last) - k];
      // (wide: past the cap from the stop before it on purpose — the ride is the point; plan_geo.farOnes lets it be)
      Object.assign(meal, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(b), why: "", by: "swap", swap: "other", wide: true });
      // the night's stay after it: the code's own right after it (the leg's margin, not before its check-in — it had
      // been put after the far dinner's ride), the model's not sooner than it was
      const st = d.stops.find((x) => x.role === "stay");
      if (st.by) {
        const at = Math.max(b + marginOf(pick.page, st.page, c, kb), mins(((kb.docs[st.page] || {}).f || {}).ci) ?? 0);
        const l = hm(st.end) - hm(st.start);
        Object.assign(st, { start: hhmm(at), end: hhmm(Math.min(at + l, 23 * 60 + 59)) });
      } else stayAfter(d, meal, c, kb);
      // the move stands only when it leaves nothing flagged (a long ride counts toward an empty stretch: the replay of the
      // live check made a 2-hour hole before the dinner, and the whole trip went to the code's)
      if (planFlags(plan, c, kb, edit).list.length) { d.stops = before; continue; }
      const why = `밤 숙소 ${stay.name}${iga(stay.name)} 직선 ${km(metres(sg, lg))} 떨어져 있어, 차 없이 밤에 이동하지 않도록`;
      for (const x of gone) out.push(`${dayW(i)}${x.name}: ${why} 저녁 전에 숙소 쪽으로 가는 시간을 두려고 일정에서 뺐습니다`);
      // (a dinner the code had put in goes unnamed: its line went with it — tidyFixed; the new one is said as put in)
      out.push(last.by === "site"
        ? `${dayW(i)}저녁: ${why} 숙소에서 가까운 음식점 ${pick.name}(직선 ${km(pick.m)}, 그날 그 시각에 여는 곳)${eul(pick.name)} ${hhmm(pick.a)}~${hhmm(b)}에 넣었습니다`
        : `${dayW(i)}${last.name}: ${why} 저녁을 숙소에서 가까운 ${pick.name}(직선 ${km(pick.m)}, 그날 그 시각에 여는 곳)${ro(pick.name)} ${hhmm(pick.a)}~${hhmm(b)}에 두었습니다`);
      return;
    }
  });
  return out;
}

/** settle 0: what the data says does not fit, said once — see settle. */
function settleFit(plan, c, kb, dayW, edit = null) {
  const out = [];
  const hard = hardNeeds(c);
  // the same kind as the stop (its type; a restaurant's cuisine, 카페): what a stop that may stay as it is becomes
  const same = (doc) => (x) => !kindOf(doc) || kindOf(x) === kindOf(doc);
  plan.days.forEach((d, i) => {
    const lastDay = i === plan.days.length - 1;
    // a stop of an edit's page as the reader has it (the same place, start and end): the soft swaps below (a need the
    // data says nothing of, a date rule) were the code's to make when the plan was made and are not made again — an
    // edit that changes nothing changes nothing (round-6 final verifier: a 'same' edit swapped a visit kept the first
    // time for '휠체어' and trimmed the meal next to it)
    const sent = editPages(edit, i, kb) && new Set(((edit.plan.days[i] || {}).stops || []).map((x) => `${kb.keyFor(x.page) || x.page}|${x.start}|${x.end}`));
    const asSent = (s) => !!sent && sent.has(`${s.page}|${s.start}|${s.end}`);
    // a stay on the trip's last day: no night follows it (round-5 verifier: a hotel at 17:30–19:30, after the reader's
    // 18:00 end, was sent)
    if (lastDay) {
      for (const s of d.stops.filter((x) => x.role === "stay")) {
        d.stops.splice(d.stops.indexOf(s), 1);
        out.push(`${dayW(i)}${s.name}: 마지막 날이라 묵지 않아 일정에서 뺐습니다`);
      }
    }
    // one stay a night: the first the day has (round-5 verifier: two stays on one night were sent) — a pinned one first
    for (const s of d.stops.filter((x) => x.role === "stay").sort((x, y) => Number(!!y.pin) - Number(!!x.pin)).slice(1)) {
      d.stops.splice(d.stops.indexOf(s), 1);
      out.push(`${dayW(i)}밤 숙소 ${s.name}: 그날 묵을 곳이 이미 있어 일정에서 뺐습니다`);
    }
    // a role is what the place is (readSubmit's rule, for any stop that reached here otherwise)
    for (const s of d.stops) {
      const kd = ((kb.docs[s.page] || {}).f || {}).kd;
      const fit = kd === "stay" ? "stay" : s.role === "stay" || ((s.role === "meal" || s.role === "cafe") && kd !== "food") ? "visit" : s.role;
      if (fit !== s.role) s.role = fit;
    }
    // a night's stay the data says does not fit a hard need the reader picked: out (step 4 puts in one that does)
    for (const s of d.stops.filter((x) => x.role === "stay" && !x.pin && hard.length && hardState(c, (kb.docs[x.page] || {}).f || {}, "stay") === "no")) {
      const f = (kb.docs[s.page] || {}).f || {};
      const need = hard.find((n) => hardState({ ...c, needs: [n] }, f, "stay") === "no");
      d.stops.splice(d.stops.indexOf(s), 1);
      out.push(`${dayW(i)}밤 숙소 ${s.name}: '${NEED_WORD[need]}' 조건에 맞지 않는다고 자료에 있어 일정에서 뺐습니다`);
    }
    // the same place twice in a row, overlapping: one stop
    for (let j = 0; j + 1 < d.stops.length; j += 1) {
      const a = d.stops[j], b = d.stops[j + 1];
      if (a.page !== b.page || hm(b.start) >= hm(a.end)) continue;
      if (hm(b.end) - hm(a.end) >= KEEP_MIN) b.start = a.end;
      else {
        a.end = hhmm(Math.max(hm(a.end), hm(b.end)));
        d.stops.splice(j + 1, 1);
        j -= 1;
      }
    }
    for (let j = d.stops.length - 1; j >= 0; j -= 1) {
      const s = d.stops[j];
      if (s.role === "stay") continue;
      const doc = kb.docs[s.page] || {};
      const f = doc.f || {};
      // a meal at a café or a bakery is a café stop (plan_state.mealIn never counts it as the day's meal; the check
      // then asks for a meal and settle adds one)
      if (s.role === "meal" && isCafe(doc)) {
        s.role = "cafe";
        out.push(`${dayW(i)}${s.name}: 카페·빵집이라 식사가 아닌 카페로 두었습니다`);
      }
      const state = hard.length ? hardState(c, f, s.role) : "ok";
      if (state === "no") {
        const need = hard.find((n) => hardState({ ...c, needs: [n] }, f, s.role) === "no");
        const why = `'${NEED_WORD[need]}' 조건에 맞지 않는다고 자료에 있어`;
        const said = swapIn(plan, d, j, c, kb, { why, fits: (x) => hardState(c, x.f, s.role) !== "no", rank: (x) => (hardState(c, x.f, s.role) === "ok" ? 0 : 1) });
        if (said) out.push(`${dayW(i)}${said}`);
        else if (!s.pin) {
          d.stops.splice(j, 1);
          out.push(`${dayW(i)}${s.name}: ${why} 일정에서 뺐습니다`);
        }
        continue;
      }
      // a visit the data says nothing of for a need the reader picked: one of the same kind nearby the data says
      // fits, when there is one; else it stays (its line to check stays at the stop)
      if (state === "unknown" && s.role === "visit" && !asSent(s)) {
        const need = hard.find((n) => hardState({ ...c, needs: [n] }, f, s.role) === "unknown");
        const said = swapIn(plan, d, j, c, kb, { why: `'${NEED_WORD[need]}' 자료가 없어`, fits: (x) => hardState(c, x.f, "visit") === "ok" && same(doc)(x) });
        if (said) { out.push(`${dayW(i)}${said}`); continue; }
      }
      // a date rule that may close it that day (a 설·추석·공휴일 rule): a place of the same kind sure to be open, when
      // one is near; else it stays with its line to check
      const info = dayInfo(kb, d.date, s.page);
      if (info.state === "check" && info.checks.some((t) => /규칙/u.test(t)) && !asSent(s)) {
        const said = swapIn(plan, d, j, c, kb, { why: "그날 쉬는지 규칙만으로 알 수 없어", fits: (x, page) => dayInfo(kb, d.date, page).state === "open"
          && same(doc)(x) && (!hard.length || hardState(c, x.f, s.role) !== "no") });
        if (said) out.push(`${dayW(i)}${said}`);
      }
    }
  });
  return out;
}

/** One round of settle 1–7 — see settle. Returns the reader's lines (none: nothing more it can do). */
function settleRound(plan, c, kb, edit, dayW) {
  const out = [];
  const flags = () => planFlags(plan, c, kb, edit).list;
  const drop = (i, j, why) => {
    // (a stop the reader pinned stays: what it leaves flagged makes the edit fail, saying so — makePlan pinWords)
    if (!plan.days[i].stops[j] || plan.days[i].stops[j].pin) return;
    const s = plan.days[i].stops.splice(j, 1)[0];
    out.push(`${dayW(i)}${s.name}: ${why} 일정에서 뺐습니다`);
  };
  // 0. a stay on the last day, a stay or a stop the data says does not fit a hard need, a day of more than STOPS_MAX
  const WHY0 = { "stay-last": "마지막 날이라 묵지 않아", "stay-two": "그날 묵을 곳이 이미 있어", role: "장소의 종류와 맞지 않아", need: "고른 조건에 맞지 않는다고 자료에 있어" };
  const at0 = new Map();   // one drop a stop
  for (const x of flags().filter((y) => ["stay-last", "stay-two", "role"].includes(y.kind) || (y.kind === "need" && plan.days[y.day].stops[y.j].role === "stay"))) {
    at0.set(`${x.day}|${x.j}`, x);
  }
  for (const x of [...at0.values()].sort((p, q) => q.day - p.day || q.j - p.j)) drop(x.day, x.j, WHY0[x.kind]);
  // a place the code put in that the changes since left farther than the cap from both stops next to it (round 6,
  // plan_geo.farOnes): out — 6 and 7 below put in what it leaves (a meal, an empty stretch) within the cap
  plan.days.forEach((d, i) => {
    for (const j of farOnes(d.stops, c, kb).reverse()) drop(i, j, `바뀐 일정에서 앞뒤 장소와 직선 ${km(cap(c))} 넘게 떨어져`);
  });
  for (const x of flags().filter((y) => y.kind === "need").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    if (!d.stops[x.j] || d.stops[x.j].role === "stay") continue;
    const why = "고른 조건에 맞지 않는다고 자료에 있어";
    const said = swapIn(plan, d, x.j, c, kb, { why });
    if (said) out.push(`${dayW(x.day)}${said}`);
    else drop(x.day, x.j, why);
  }
  for (const x of flags().filter((y) => y.kind === "many")) {
    const d = plan.days[x.day];
    while (d.stops.length > STOPS_MAX) {
      const own = d.stops.filter((y) => y.role !== "stay" && y.role !== "meal" && !y.pin);
      // (the code's own first, a place new to an edit last, then the shortest)
      const k = own.sort((p, q) => Number(!!p.asked) - Number(!!q.asked) || Number(!p.by) - Number(!q.by) || hm(p.end) - hm(p.start) - (hm(q.end) - hm(q.start)))[0];
      if (!k) break;
      drop(x.day, d.stops.indexOf(k), `하루 ${STOPS_MAX}곳을 넘어`);
    }
  }
  // 1. closed, hours — the stops from the last, so the indexes hold
  for (const x of flags().filter((y) => y.kind === "closed" || y.kind === "hours").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    const s = d.stops[x.j];
    if (!s || s.role === "stay") continue;
    if (x.kind === "hours") {
      const w = windowOf(dayInfo(kb, d.date, s.page));
      const a = Math.max(hm(s.start), w.open), b = Math.min(hm(s.end), w.close);
      // (a cut that changes nothing is no fix: the stop is swapped — round-5 verifier, '10:00~13:53에서 10:00~13:53으로')
      if ((a !== hm(s.start) || b !== hm(s.end)) && b - a >= keepOf(s, kb) && a <= w.last && !inBreak((kb.docs[s.page] || {}).f || {}, a, b)) {
        out.push(`${dayW(x.day)}${s.name}: 그날 이용시간에 맞춰 ${s.start}~${s.end}에서 ${hhmm(a)}~${hhmm(b)}${ro(hhmm(b))} 줄였습니다`);
        Object.assign(s, { start: hhmm(a), end: hhmm(b) });
        continue;
      }
      // a cut below its floor (round 6): the stop moves whole into its hours instead — later from before the opening,
      // earlier from past the closing — with the stops after (before) it as far as needed
      const late = hm(s.start) < w.open ? w.open - hm(s.start) : 0, soon = hm(s.end) > w.close && w.close > w.open ? hm(s.end) - w.close : 0;
      const moves = late && !soon ? shiftPlan(d, x.j, late, 1, c, kb, boundsOf(plan, x.day, c, kb))
        : soon && !late ? shiftPlan(d, x.j, soon, -1, c, kb, boundsOf(plan, x.day, c, kb)) : null;
      if (moves && kb.checkPlan({ date: d.date, stops: [{ page: s.page, start: hhmm(moves[0].a), end: hhmm(moves[0].b) }], move: c.move }).flags.length === 0) {
        out.push(`${dayW(x.day)}${s.name}: 그날 이용시간에 맞춰 ${shiftDone(moves, late ? 1 : -1)}`);
        continue;
      }
    }
    const why = x.kind === "closed" ? closedWhy(kb, d.date, s.page) : "그 시각에 열지 않는다고 자료에 있어";
    const said = swapIn(plan, d, x.j, c, kb, { why, closed: x.kind === "closed" && closedSure(kb, d.date, s.page) });
    if (said) out.push(`${dayW(x.day)}${said}`);
    else drop(x.day, x.j, why);
  }
  // 1b. a break of the place's day (round 7): a visit keeps the part before or after it when that is its least, else it
  // moves whole past it; a meal is the nearest restaurant serving then (its time is the meal's), else it moves whole —
  // else swapped, else out
  for (const x of flags().filter((y) => y.kind === "break").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    const s = d.stops[x.j];
    if (!s || s.role === "stay") continue;
    const f = (kb.docs[s.page] || {}).f || {};
    const a = hm(s.start), b = hm(s.end);
    const br = breakOf(f, a, b);
    if (!br) continue;
    const span2 = `${hhmm(br[0])}~${hhmm(br[1])}`;
    const words = breakWords(br);   // '쉬는 시간 15:00~17:00' or the gap between two sessions in its own words
    // (whose value it is: two sources may disagree — the plan keeps out of the break either way, CLAUDE.md 3절 2항)
    const why = `${br[2] ? `${br[2]} 자료에 ` : "자료에 "}${br[3] ? `그 시각이 ${br[3]}(${span2})에 걸려` : `그 시각이 쉬는 시간(${span2})으로 있어`}`;
    if (s.role === "meal") {
      const said = swapIn(plan, d, x.j, c, kb, { why });
      if (said) { out.push(`${dayW(x.day)}${said}`); continue; }
    } else {
      const part = [[a, Math.min(b, br[0])], [Math.max(a, br[1]), b]].filter(([p, q]) => q - p >= keepOf(s, kb) && !inBreak(f, p, q))
        .sort((u, v) => (v[1] - v[0]) - (u[1] - u[0]))[0];
      if (part) {
        out.push(`${dayW(x.day)}${s.name}: ${br[2] ? `${br[2]} 기준 ` : ""}${words}을 피해 ${s.start}~${s.end}에서 ${hhmm(part[0])}~${hhmm(part[1])}${ro(hhmm(part[1]))} 줄였습니다`);
        Object.assign(s, { start: hhmm(part[0]), end: hhmm(part[1]) });
        continue;
      }
    }
    const moves = shiftPlan(d, x.j, br[1] - a, 1, c, kb, boundsOf(plan, x.day, c, kb));
    if (moves && !inBreak(f, moves[0].a, moves[0].b)
      && kb.checkPlan({ date: d.date, stops: [{ page: s.page, start: hhmm(moves[0].a), end: hhmm(moves[0].b) }], move: c.move }).flags.length === 0) {
      out.push(`${dayW(x.day)}${s.name}: ${br[2] ? `${br[2]} 기준 ` : ""}${words}을 피해 ${shiftDone(moves, 1)}`);
      continue;
    }
    const said = s.role === "meal" ? "" : swapIn(plan, d, x.j, c, kb, { why });
    if (said) out.push(`${dayW(x.day)}${said}`);
    else drop(x.day, x.j, why);
  }
  // 2. rain, budget — a rainy day's outdoor visits past the first go, from the last; when the reader asked for one
  // (plan_build.rainAsked — operator 2026-10-23: '히로쓰가옥도 넣어 줘' came back with an indoor place in its stead),
  // every outdoor visit they did not ask for goes and those they asked for stay
  for (const x of flags().filter((y) => y.kind === "rain")) {
    const d = plan.days[x.day];
    const asked = rainAsked(kb, edit, x.day);
    const outdoor = d.stops.map((s, j) => ({ s, j })).filter(({ s }) => s.role === "visit" && isOutdoor((kb.docs[s.page] || {}).f || {}));
    // (a pinned one and those the reader asked for stay: the others go first)
    const stays = ({ s }) => !!s.pin || asked(s);
    const go = outdoor.some(stays) ? outdoor.filter((x) => !stays(x)) : outdoor.slice(1);
    for (const { j } of go.reverse()) {
      const why = "비 오는 날 야외는 하루 한 곳까지라";
      const said = swapIn(plan, d, j, c, kb, { why, fits: (y) => !isOutdoor(y.f) });
      if (said) out.push(`${dayW(x.day)}${said}`);
      else drop(x.day, j, why);
    }
  }
  const dear = (fee) => Math.max(0, ...Object.values((fee && fee.tab) || {}).filter(Number.isFinite));
  // what a visit adds to the known admissions (its own table, or a combined ticket that opens it): the known total
  // with it less the known total without it
  const costOf = (i, j) => {
    const total = knownFees(plan, c, kb);
    const st = plan.days[i].stops.splice(j, 1)[0];
    const without = knownFees(plan, c, kb);
    plan.days[i].stops.splice(j, 0, st);
    return total - without;
  };
  // each turn swaps the visit that costs most for a free or cheaper one or takes it out: at most one turn a stop
  const all = plan.days.reduce((n, d) => n + d.stops.length, 0);
  for (let n = 0; n < all && flags().some((y) => y.kind === "budget"); n += 1) {
    const paid = plan.days.flatMap((d, i) => d.stops.map((s, j) => ({ s, i, j })))
      .filter(({ s }) => s.role === "visit" && !s.pin)
      .map((y) => ({ ...y, won: costOf(y.i, y.j) }))
      .filter((y) => y.won > 0)
      .sort((p, q) => q.won - p.won || q.i - p.i || q.j - p.j);
    if (!paid.length) break;
    const { s, i, j, won } = paid[0];
    const why = "입장료 예산을 넘어";
    const own = dear(((kb.docs[s.page] || {}).f || {}).fee) || won;
    const cheaper = (y) => !!(y.f.fee && (y.f.fee.free || (y.f.fee.tab && dear(y.f.fee) < own)));
    const said = swapIn(plan, plan.days[i], j, c, kb, { why, fits: cheaper, rank: (y) => (y.f.fee && y.f.fee.free ? 0 : 1) });
    if (said) out.push(`${dayW(i)}${said}`);
    else drop(i, j, why);
  }
  // 3. the reader's start and end, the station's margins
  for (const x of flags().filter((y) => ["start", "end", "hub-from", "hub-to"].includes(y.kind)).sort((p, q) => q.day - p.day || (q.j ?? 0) - (p.j ?? 0))) {
    const d = plan.days[x.day];
    const own = d.stops.filter((s) => s.role !== "stay");
    const s = x.j !== undefined ? d.stops[x.j] : x.kind === "hub-from" ? own[0] : own.at(-1);
    if (!s || !d.stops.includes(s)) continue;
    const j = d.stops.indexOf(s);
    if (x.kind === "start" || x.kind === "hub-from") {
      // (the station's margin for this stop's 권역: plan_state.hubMargin — 0 with no station named)
      const a = hm(c.start) + (x.kind === "hub-from" || x.day === 0 ? hubMargin(c, "from", kb.docs[s.page]) : 0);
      if (hm(s.start) >= a) continue;
      const why = c.from ? `${hubName(c.from)}에서 출발하는 여유를 두려고` : `고른 시작 ${c.start}에 맞춰`;
      // (round 6: a cut below its floor moves the stop whole instead, the stops after it with it as far as needed)
      const moves = hm(s.end) - a < keepOf(s, kb) && shiftPlan(d, j, a - hm(s.start), 1, c, kb, boundsOf(plan, x.day, c, kb));
      if (hm(s.end) - a >= keepOf(s, kb)) {
        out.push(`${dayW(x.day)}${s.name}: ${why} 시작을 ${s.start}에서 ${hhmm(a)}${ro(hhmm(a))} 늦췄습니다`);
        s.start = hhmm(a);
      } else if (moves) out.push(`${dayW(x.day)}${s.name}: ${why} ${shiftDone(moves, 1)}`);
      else drop(x.day, j, c.from ? `${hubName(c.from)}에서 출발하는 여유를 두면 시간이 남지 않아` : `고른 시작 ${c.start} 전이라`);
    } else {
      const b = hm(c.end) - (x.kind === "hub-to" || x.day === plan.days.length - 1 ? hubMargin(c, "to", kb.docs[s.page]) : 0);
      if (hm(s.end) <= b) continue;
      const why = c.to ? `${hubName(c.to)}${ro(hubName(c.to))} 돌아가는 여유를 두려고` : `고른 끝 ${c.end}에 맞춰`;
      const moves = b - hm(s.start) < keepOf(s, kb) && shiftPlan(d, j, hm(s.end) - b, -1, c, kb, boundsOf(plan, x.day, c, kb));
      if (b - hm(s.start) >= keepOf(s, kb)) {
        out.push(`${dayW(x.day)}${s.name}: ${why} 끝을 ${s.end}에서 ${hhmm(b)}${ro(hhmm(b))} 당겼습니다`);
        s.end = hhmm(b);
      } else if (moves) out.push(`${dayW(x.day)}${s.name}: ${why} ${shiftDone(moves, -1)}`);
      else drop(x.day, j, c.to ? `${hubName(c.to)}${ro(hubName(c.to))} 돌아가는 여유를 두면 시간이 남지 않아` : `고른 끝 ${c.end} 뒤라`);
    }
  }
  // 4. stays
  for (const x of flags().filter((y) => ["stay-mid", "stay-ci", "stay-missing"].includes(y.kind))) {
    const said = settleStay(plan, plan.days[x.day], x, c, kb);
    if (said) out.push(`${dayW(x.day)}${said}`);
  }
  // 5. legs
  for (const x of flags().filter((y) => y.kind === "leg").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    const a = d.stops[x.j], b = d.stops[x.j + 1];
    if (!a || !b) continue;
    const said = widen(d, x.j, c, kb, !changed(a) && !changed(b), boundsOf(plan, x.day, c, kb));
    if (said) { out.push(`${dayW(x.day)}${said}`); continue; }
    // the stop that cannot be reached goes: the code's own first, else the one farther from its other neighbour
    const far = (s, o) => (o && gOf(kb, s.page) && gOf(kb, o.page) ? metres(gOf(kb, s.page), gOf(kb, o.page)) : 0);
    let k = changed(b) && !changed(a) ? x.j + 1 : changed(a) && !changed(b) ? x.j : far(b, d.stops[x.j + 2]) >= far(a, d.stops[x.j - 1]) ? x.j + 1 : x.j;
    // (never a night's stay, never a meal an edit kept — markKept)
    // (never a night's stay, never a meal an edit kept — markKept; a place new to the edit only when the other is one
    // of these or new too)
    const fixedAt = (y) => d.stops[y].role === "stay" || d.stops[y].kept || d.stops[y].pin;
    const other = k === x.j ? x.j + 1 : x.j;
    if (fixedAt(k) || (d.stops[k].asked && !d.stops[other].asked && !fixedAt(other))) k = other;
    if (fixedAt(k)) continue;
    drop(x.day, k, "앞뒤 장소와 이동 여유를 둘 수 없어");
  }
  // 6. meals
  for (const x of flags().filter((y) => y.kind === "meal")) {
    const d = plan.days[x.day];
    const m = MEALS[x.meal];
    // a restaurant given as a visit or a café inside the window: the meal
    const as = d.stops.find((s) => s.role !== "meal" && s.role !== "stay" && isMeal(kb.docs[s.page]) && (hm(s.start) + hm(s.end)) / 2 >= m.near[0]
      && (hm(s.start) + hm(s.end)) / 2 < m.near[1] && hm(s.end) - hm(s.start) >= MEAL_KEEP   // (a meal keeps its floor: round 6)
      && d.stops.every((y) => y.role !== "meal" || isCafe(kb.docs[y.page]) || Math.abs(hm(y.start) - hm(s.start)) >= MEAL_APART));   // (round 7)
    if (as) {
      as.role = "meal";
      out.push(`${dayW(x.day)}${as.name}: ${m.label} 시간의 음식점이라 식사 장소로 두었습니다`);
      continue;
    }
    const dayOf = () => readerDay(plan, c, x.day, kb);
    if (!dayOf()) continue;
    // nearer first, then twice as far, then as far as the cap (round 6, plan_geo.CAP: 3 km without a car, 8 km by
    // car — the day builder looks no farther)
    const far = Math.min(2 * near(c, "meal") + (c.move === "car" ? 0 : 1500), cap(c));
    const farthest = cap(c), widest = wideOf(c).at(-1);
    const said = addMeal(plan, d, dayOf(), m, c, kb) || addMeal(plan, d, dayOf(), m, c, kb, null, far)
      || mealInstead(plan, d, dayOf, m, c, kb, { max: far }) || (farthest > far && addMeal(plan, d, dayOf(), m, c, kb, null, farthest))
      // (then a restaurant of another day, before one of the model's places goes for a meal; then one near the night's
      // stay — live check 2026-10-19, the far islands)
      || addMeal(plan, d, dayOf(), m, c, kb, null, farthest, true)
      || mealInstead(plan, d, dayOf, m, c, kb, { max: farthest, any: true })
      || (x.meal === "dinner" && dinnerByStay(plan, d, c, kb, edit))
      // past the cap as far as the day builder's last ring (plan_build.WIDE) before the day is built again — the
      // reader's own places kept (live check 2026-10-19: 섬 권역 on a Tuesday by car, the dinner 18 km off at OO항)
      || (!edit && widest > farthest && (addMeal(plan, d, dayOf(), m, c, kb, null, widest, true, true)
        || mealInstead(plan, d, dayOf, m, c, kb, { max: widest, again: true, wide: true })));
    if (said) out.push(`${dayW(x.day)}${said}`);
  }
  // 7. empty stretches
  for (const x of flags().filter((y) => y.kind === "gap")) {
    const d = plan.days[x.day];
    const day = readerDay(plan, c, x.day, kb);
    if (!day) continue;
    const g = idleGaps(day).find((y) => y.from === x.from && y.to === x.to) || idleGaps(day).find((y) => y.minutes > IDLE);
    if (!g) continue;
    const wide = Math.min(2 * near(c, "fill"), cap(c));
    // (never past STOPS_MAX: a full day's stretch is taken up by the stops next to it — live replay 2026-10-19, a café
    // put in after a full day's dinner pushed one of the model's visits out)
    const room = d.stops.length < STOPS_MAX;
    const said = room && (fillGap(plan, d, day, g, c, kb) || (wide > near(c, "fill") && fillGap(plan, d, day, g, c, kb, wide)));
    if (said) { out.push(`${dayW(x.day)}${said}`); continue; }
    // the stop before it stays longer (its hours, 3 hours at most — a meal or a café 90 minutes), the one after it
    // starts sooner — each alone, else the two together (round 6: an edit's afternoon of 3 hours before an island 24 km
    // off — the lunch 30 minutes longer and the island 40 minutes sooner — went unsettled)
    const P = day.own[g.at - 1], N = day.own[g.at];
    const need = g.minutes - IDLE;
    let eP = 0, eN = 0;
    // (a meal an edit kept is never stretched: markKept — round-6 final verifier, '한일옥: 빈 시간을 줄이려고 끝을 …
    // 늦췄습니다' after a drop the request did not ask of it)
    if (P && !P.kept) {
      const w = windowOf(dayInfo(kb, d.date, P.page));
      const lim = Math.min(w.close, hm(P.start) + stretchMax(P), N ? hm(N.start) - marginOf(P.page, N.page, c, kb) : g.to);
      const nb = Math.min(lim, hm(P.end) + need);
      if (nb > hm(P.end) && !inBreak((kb.docs[P.page] || {}).f || {}, hm(P.start), nb)) eP = nb - hm(P.end);
    }
    if (N && !N.kept) {
      const w = windowOf(dayInfo(kb, d.date, N.page));
      const lim = Math.max(w.open, hm(N.end) - stretchMax(N), P ? hm(P.end) + marginOf(P.page, N.page, c, kb) : g.from);
      const na = Math.max(lim, hm(N.start) - need);
      if (na < hm(N.start) && na <= w.last && !inBreak((kb.docs[N.page] || {}).f || {}, na, hm(N.end))) eN = hm(N.start) - na;
    }
    // (a meal keeps its side and window — plan_state.mealSlot, shiftPlan's rule: round-6 final verifier, a dinner-side
    // meal stretched to start at 15:00 became a second lunch)
    eP = P ? slotRoom(P, eP, 1) : 0;
    eN = N ? slotRoom(N, eN, -1) : 0;
    if (eP + eN < need) continue;
    // the stop before first; the one after takes the rest (a later start keeps to its hours: the earliest was read)
    eP = Math.min(eP, need);
    eN = need - eP;
    if (eP) {
      const nb = hhmm(hm(P.end) + eP);
      out.push(`${dayW(x.day)}${P.name}: 빈 시간을 줄이려고 끝을 ${P.end}에서 ${nb}${ro(nb)} 늦췄습니다`);
      P.end = nb;
    }
    if (eN) {
      const na = hhmm(hm(N.start) - eN);
      out.push(`${dayW(x.day)}${N.name}: 빈 시간을 줄이려고 시작을 ${N.start}에서 ${na}${ro(na)} 당겼습니다`);
      N.start = na;
    }
  }
  return out;
}

/** The most a stop may be stretched, up to `by` minutes — its end later (dir 1) or its start sooner (-1) — keeping a
 *  meal where it is (plan_state.mealSlot: its side, in or out of its window; round-6 final verifier: a dinner-side meal
 *  stretched to 15:00 became a second lunch). Any other stop: `by`. */
function slotRoom(s, by, dir) {
  if (s.role !== "meal" || by <= 0) return by;
  const a = hm(s.start), b = hm(s.end), was = mealSlot(a, b);
  for (let x = by; x > 0; x -= 5) if (mealSlot(dir > 0 ? a : a - x, dir > 0 ? b + x : b) === was) return x;
  return 0;
}

/** settle 4: a night's stay out of place or missing — see settle. */
function settleStay(plan, d, x, c, kb) {
  const own = d.stops.filter((s) => s.role !== "stay");
  const last = own.at(-1);
  const ciOf = (page) => mins(((kb.docs[page] || {}).f || {}).ci);
  const at = (page) => {
    if (!last) return null;
    const a = Math.max(hm(last.end) + marginOf(last.page, page, c, kb), ciOf(page) ?? 0);
    return a <= STAY_LATEST ? a : null;
  };
  const put = (s, a) => {
    if (d.stops.includes(s)) d.stops.splice(d.stops.indexOf(s), 1);
    d.stops.push(Object.assign(s, { start: hhmm(a), end: hhmm(Math.min(a + 60, 23 * 60 + 59)) }));
  };
  const s = x.kind === "stay-missing" ? null : d.stops[x.j];
  if (s && s.role === "stay") {
    const a = at(s.page);
    if (a !== null) {
      const was = s.start;
      put(s, a);
      s.moved = true;
      return `밤 숙소 ${s.name}: 그날 마지막 장소 ${last.name} 뒤로 시작을 ${was}에서 ${hhmm(a)}${ro(hhmm(a))} 옮겼습니다`;
    }
  }
  if (!last) return "";
  // the day runs too late for any stay (none can start by 23:29 after it): the last stop is cut to the reader's end
  if (at(last.page) === null && hm(last.end) > hm(c.end) && hm(c.end) - hm(last.start) >= keepOf(last, kb)) {
    const was = last.end;
    last.end = c.end;
    return `${last.name}: 밤 숙소에 들어갈 여유를 두려고 끝을 ${was}에서 ${c.end}${ro(c.end)} 당겼습니다`;
  }
  // another night's stay, else the nearest that can start by 23:29 (STAY_NEAR, then farther); a full day first gives
  // up a stop the code put in — never in place of a stay the reader pinned
  if (s && s.pin) return "";
  if (!s && makeRoom(d) === null) return "";
  const other = plan.days.filter((y) => y !== d).map((y) => y.stops.find((z) => z.role === "stay" && mayPut(kb, z.page) && codeFits(c, (kb.docs[z.page] || {}).f || {}, "stay"))).find(Boolean);
  let pick = null;
  if (other && at(other.page) !== null) pick = { page: other.page, name: other.name, how: `다른 밤과 같은 숙소 ${other.name}${eul(other.name)} 넣었습니다` };
  const g = lastPoint(kb, d.stops);
  if (!pick && g) {
    const stays = placesOf(kb).filter((p) => p.doc.f.kd === "stay" && codeFits(c, p.doc.f, "stay"))
      .map((p) => ({ page: p.page, name: p.doc.t, m: metres(g, p.doc.f.g), camp: CAMP.test(p.doc.f.ty || "") }))
      .sort((p, q) => p.camp - q.camp || p.m - q.m || (p.name < q.name ? -1 : 1));
    for (const R of [STAY_NEAR, 10000, 20000, Infinity]) {
      const y = stays.find((z) => z.m <= R && at(z.page) !== null);
      if (y) { pick = { ...y, how: `${gOf(kb, last.page) ? last.name : "그날 장소"}에서 가까운 숙소 ${y.name}(직선 ${km(y.m)})${eul(y.name)} 넣었습니다 — 객실·요금은 숙소에 확인` }; break; }
    }
  }
  if (!pick) return "";
  if (s && d.stops.includes(s)) d.stops.splice(d.stops.indexOf(s), 1);
  put({ page: pick.page, name: pick.name, start: "", end: "", role: "stay", why: "", by: "site" }, at(pick.page));
  return `밤 숙소: ${s ? `${s.name}에 그날 들어갈 수 없어 ` : "일정에 없어 "}${pick.how}`;
}

// ------------------------------------------------------------------ an edit that asks for fewer admissions
// (outside test 2026-10-23: the quick edit '입장료 없는 곳 위주로 바꿔 주세요' came back with the same stops, the same
// times and the same known total of 24,000원 under the title '무료 장소 위주', its changes '장소와 시각은 그대로예요' —
// the request only reached the model, and nothing checked that the edit did what it asked)
/** The reader's words for fewer or no admissions: the quick edit's (pipeline/present.py PLAN_QUICK_EDITS) and the plain
 *  forms of it — '입장료 줄여', '입장료가 싼 곳', '무료인 곳으로', '무료 장소 위주', '무료 입장 가능한 곳', '무료로 볼 수 있는
 *  곳', '공짜로 바꿔' (not '무료 주차'). */
export const FEE_ASK = new RegExp(String.raw`입장료\s*(?:[가를는이도]\s*)?(?:없|안\s*(?:드|들|내)|들지\s*않|줄|낮|아끼|아껴|적[게은]|싼|싸|덜)`
  + String.raw`|(?:무료|공짜)\s*(?:인|입장|관람)?\s*(?:이?\s*가능한\s*)?(?:곳|장소|명소|관광지|위주)`
  + String.raw`|(?:무료|공짜)로\s*(?:볼|들어갈|구경할|관람할|즐길)\s*수\s*있는\s*(?:곳|장소)`
  + String.raw`|(?:무료|공짜)(?:인\s*곳)?\s*(?:으로|로)\s*(?:바꿔|바꾸|채워|채우|짜)`, "u");
// words just after those that turn them down ('무료인 곳 말고 박물관 위주로', '입장료 줄이지 않아도 돼요', '입장료는 줄이지
// 마세요', '무료인 곳이 아니어도', '입장료 없는 곳은 싫어요', '무료 장소 대신 …'): no such request (review of the fee edit:
// these swapped the reader's paid visits away, the opposite of what they asked)
const FEE_NOT = /^[^.!?。\n,]{0,10}?(?:말고|빼고|제외|아니(?!면)|않아도|안\s*해도|지\s*(?:마|말)|필요\s*없|상관\s*없|싫|(?<!로\s*)대신)/u;
export const asksFewerFees = (request) => {
  const t = String(request || "");
  return [...t.matchAll(new RegExp(FEE_ASK.source, "gu"))].some((m) => !FEE_NOT.test(t.slice(m.index + m[0].length)));
};
// what the request says of a stop it names: the first word after the name, within its sentence, that keeps it ('…은
// 그대로 두고', '…은 두고', '…은 남기고', '…에 가고 싶은데', '…을 넣고', '…만 빼고', '…은 빼고 나머지', '…, 나머지는') or changes
// it ('… 대신', '…은 입장료 없는 곳으로 바꿔', '…이랑 …은 무료로 바꿔', '…은 빼고') — the keeping word first where both
// start ('빼지 말고', '바꾸지 말고'); a name with neither stays (review of the fee edit: a window of 12 characters read
// '테디베어박물관은 입장료 없는 곳으로 바꿔 주세요' and the first of two names before '바꿔' as keeping them, and '…은 두고
// 무료로 바꿔' as changing it)
const NAME_DO = new RegExp(String.raw`^[^.!?。\n]*?(?:(만\s*(?:빼고|제외하고)|(?:빼고|제외하고)\s*(?:나머지|다른)|그대로|두고|둬|놔두|남기|남겨|유지|`
  + String.raw`가고\s*싶|넣고|넣어|빼지\s*말|바꾸지\s*말|나머지)|대신|말고|빼|뺀|바꿔|바꾸|바꿀|제외|없애|취소)`, "u");
const keepsName = (rest) => { const m = NAME_DO.exec(rest); return !m || m[1] !== undefined; };
const won = (n) => `${n.toLocaleString("en-US")}원`;
const eun = (w) => { const j = jong(w); return j < 0 ? "은(는)" : j ? "은" : "는"; };
const feesOf = (days, c, kb) => planFees(days, c, kb, c.budget);
/** The visits of a priced plan someone pays for — by their own table or a combined ticket that day — and those with
 *  no price for someone (plan_fees per visit): {paid: [name], open: [name]}. */
function feeNames(fees) {
  const paid = [], open = [];
  for (const d of fees.days) {
    for (const p of d.per) {
      if (p.how === "again") continue;
      const own = p.how === "own";
      const lines = own ? d.lines.filter((l) => l.path === p.path) : d.lines.filter((l) => l.ticket === p.how);
      if (lines.some((l) => l.status === "paid") && !paid.includes(p.name)) paid.push(p.name);
      else if (lines.some((l) => l.status === "unknown") && !open.includes(p.name)) open.push(p.name);
    }
  }
  return { paid, open };
}
/** The amount the page shows for a priced plan (plan.js feeHead): '29,000원', '0원', '5,000원 + 확인 필요'. */
function feeWords(f) {
  if (f.state === "none") return "입장료 내는 곳 없음";
  if (f.state === "free") return "0원";
  if (f.state === "known") return won(f.total);
  return f.state === "partial" ? `${won(f.known)} + 확인 필요` : "확인 필요";
}

/** An edit that asks for fewer admissions (asksFewerFees), made true by the code where the site's data allows, after
 *  settle — on a plan with nothing flagged: each paid visit, the one that adds most to the known total first (a
 *  combined ticket counted as plan_fees counts it), becomes the nearest free or cheaper place that fits its day and slot
 *  (swapIn, as settle's budget swap: free first; open that day at those times, the reader's needs, within NEAR.swap and
 *  the cap of the stops next to it, its kind's floor, the legs' margins) — kept only when it lowers the known total,
 *  leaves no more people unpriced and leaves nothing flagged (planFlags, farOnes); else the visit stays. A stop the
 *  request names, not to change it, stays, and a place the edit took out (on the reader's page, not in the plan now)
 *  does not come back in a swap. Changes plan; returns {fixed: the swaps' lines, asked: the names kept as the request
 *  said, noGain: the names kept as swapping them would not lower the fees}. */
function fewerFees(plan, c, kb, edit) {
  const out = { fixed: [], asked: [], noGain: [], pinned: [] };
  const request = String(edit.request || "");
  const many = plan.days.length > 1;
  const named = (page) => {
    const doc = kb.docs[page] || {};
    const names = [...new Set([doc.t, ...kb.placeNames.filter(([, k]) => k === page).map(([n]) => n)].filter(Boolean))];
    return names.some((n) => {
      for (let i = request.indexOf(n); i >= 0; i = request.indexOf(n, i + 1)) {
        const rest = request.slice(i + n.length);
        if (keepsName(rest)) return true;
      }
      return false;
    });
  };
  const clean = () => !planFlags(plan, c, kb, edit).list.length && !plan.days.some((d) => farOnes(d.stops, c, kb).length);
  if (!clean()) return out;
  const dear = (fee) => Math.max(0, ...Object.values((fee && fee.tab) || {}).filter(Number.isFinite));
  const keep = new Set();   // the stops the request names to stay
  // (review of the fee edit: '장미갤러리는 빼고 입장료 줄여 주세요' — the model took 장미갤러리 out, and the swap of
  // 역사박물관 put it back)
  const now = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.page)));
  const left = new Set(edit.plan.days.flatMap((d) => d.stops.map((s) => kb.keyFor(s.page) || s.page)).filter((p) => !now.has(p)));
  for (const d of plan.days) {
    for (const s of d.stops) {
      if (s.role !== "visit" || !(named(s.page) || s.pin)) continue;
      keep.add(s);
      // (a stop the reader pinned — 고정 — stays as the request's own do: said apart)
      const list = s.pin ? out.pinned : out.asked;
      if (!list.includes(s.name)) list.push(s.name);
    }
  }
  const tried = new Set(keep);
  // stop j of day i made a free place, or one dearer than `own` no more, when the plan with it passes ok(its fees)
  const swapOne = (i, j, own, ok) => {
    const said = swapIn(plan, plan.days[i], j, c, kb, { why: "입장료를 줄여 달라는 요청대로",
      fits: (y, page) => !left.has(page) && !!(y.f.fee && (y.f.fee.free || (y.f.fee.tab && dear(y.f.fee) < own))),
      rank: (y) => (y.f.fee && y.f.fee.free ? 0 : 1),
      test: () => ok(feesOf(plan.days, c, kb)) && clean() });
    if (said) out.fixed.push(`${many ? `${i + 1}일차 ` : ""}${said}`);
  };
  const all = plan.days.reduce((n, d) => n + d.stops.length, 0);
  for (let n = 0; n < all; n += 1) {
    const base = feesOf(plan.days, c, kb);
    // what each visit adds to the known total: the total with it less the total without it
    const costOf = (i, j) => {
      const st = plan.days[i].stops.splice(j, 1)[0];
      const without = feesOf(plan.days, c, kb).known;
      plan.days[i].stops.splice(j, 0, st);
      return base.known - without;
    };
    const paid = plan.days.flatMap((d, i) => d.stops.map((s, j) => ({ s, i, j })))
      .filter(({ s }) => s.role === "visit" && !tried.has(s))
      .map((y) => ({ ...y, won: costOf(y.i, y.j) }))
      .filter((y) => y.won > 0)
      .sort((p, q) => q.won - p.won || p.i - q.i || p.j - q.j);
    if (!paid.length) break;
    const { s, i, j, won: cost } = paid[0];
    tried.add(s);
    swapOne(i, j, dear(((kb.docs[s.page] || {}).f || {}).fee) || cost, (f) => f.known < base.known && f.open.length <= base.open.length);
  }
  // a combined ticket's places (박물관 통합권: 역사박물관·구 일본 제18은행 OO지점·OO근대건축관·진포해양공원 on one day):
  // one of them alone adds nothing to the total while the ticket opens the others (진포해양공원 has no table of its own),
  // or more people unpriced without it (a child's age its own table does not give), so the turns above never swap them
  // — a day's paid visits left are tried together, the dearest first, each swap not raising the known total, and all
  // put back unless the day's swaps lower it with no more people unpriced (review of the fee edit: a 원도심 museum day
  // kept all four, its line saying no free place was near)
  for (const [i, d] of plan.days.entries()) {
    const { paid } = feeNames(feesOf(plan.days, c, kb));
    const price = (s) => dear(((kb.docs[s.page] || {}).f || {}).fee);
    const rest = d.stops.filter((s) => s.role === "visit" && !keep.has(s) && paid.includes(s.name)).sort((p, q) => price(q) - price(p));
    if (!rest.length) continue;
    const start = feesOf(plan.days, c, kb), was = structuredClone(d.stops), lines = out.fixed.length;
    const had = rest.map((s) => [s, s.page, s.name]);
    for (const s of rest) {
      const base = feesOf(plan.days, c, kb);
      swapOne(i, d.stops.indexOf(s), price(s), (f) => f.known <= base.known);
    }
    const end = feesOf(plan.days, c, kb);
    if (!(end.known < start.known && end.open.length <= start.open.length)) {
      // (those a place was found for: kept as swapping them lowers nothing — said so, not 'no place near')
      out.noGain.push(...had.filter(([s, page]) => s.page !== page).map(([, , name]) => name));
      d.stops = was;
      out.fixed.length = lines;
    }
  }
  return out;
}

/** The reader's lines of a fewer-admissions edit, from the site's own fee numbers (the same the page shows): the
 *  plan before the edit (the reader's page) against the plan sent — how much went when the known total went down,
 *  else that it did not and why, the paid visits kept named. [{k: 'fee', t}]. */
function fewerFeesLines(edit, fees, res, c, kb) {
  const days = edit.plan.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => {
    const page = kb.keyFor(s.page) || s.page;
    return { page, name: (kb.docs[page] || {}).t || page, role: s.role };
  }) }));
  const before = feesOf(days, c, kb);
  const was = feeWords(before), now = feeWords(fees);
  const { paid, open } = feeNames(fees);
  const asked = res.asked.filter((n) => paid.includes(n));
  const pinned = (res.pinned || []).filter((n) => paid.includes(n) && !asked.includes(n));
  const noGain = res.noGain.filter((n) => paid.includes(n) && !asked.includes(n) && !pinned.includes(n));
  const noFit = paid.filter((n) => !asked.includes(n) && !noGain.includes(n) && !pinned.includes(n));
  const list = (xs) => xs.join("·");
  const keptAsked = [asked.length ? `${list(asked)}${eun(asked.at(-1))} 요청대로 그대로 두었어요` : "",
    pinned.length ? `고정한 ${list(pinned)}${eun(pinned.at(-1))} 그대로 두었어요` : ""].filter(Boolean).join(", ");
  // (with a need the reader picked, the place swapped in is held to it too: said — review of the fee edit, a stroller's
  // day kept its museums 'for want of a place at that time' with free places all round)
  const keptNoFit = noFit.length ? `입장료가 있는 ${list(noFit)}${eun(noFit.at(-1))} ${hardNeeds(c).length ? "고른 조건과 " : ""}그 시간에 맞는 무료·더 싼 장소가 `
    + "그날 동선 가까이에 없어 그대로 두었어요" : "";
  const keptNoGain = noGain.length ? `입장료가 있는 ${list(noGain)}${eun(noGain.at(-1))} 다른 곳으로 바꿔도 사이트 자료로 셈한 입장료가 줄지 않아 그대로 두었어요` : "";
  const kept = [keptNoFit, keptNoGain, keptAsked].filter(Boolean).join(", ");
  const down = fees.known < before.known && fees.open.length <= before.open.length;
  if (down) {
    return [{ k: "fee", t: `입장료 줄이기: 입장료 ${was} → ${now}(${fees.open.length || before.open.length ? "확인된 입장료 " : ""}${won(before.known - fees.known)} 줄었어요)${kept ? ` — ${kept}` : ""}` }];
  }
  const same = fees.known === before.known && fees.open.length === before.open.length;
  const amount = !same ? `입장료: ${was} → ${now}` : now === "확인 필요" ? "입장료는 그대로 확인이 필요해요" : `입장료는 ${now} 그대로예요`;
  if (!paid.length) {
    // (a visit with no price for someone may be paid: no '입장료를 내는 곳이 없어요' then — CLAUDE.md 3.1)
    const unpriced = open.length ? ` — 요금을 확인하지 못한 ${list(open)}${eun(open.at(-1))} 사이트 자료로는 줄일 수 있는지 알 수 없어요` : "";
    return [{ k: "fee", t: `입장료 줄이기: 일정에 입장료를 ${open.length ? "낸다고 확인된" : "내는"} 곳이 없어요(${amount})${unpriced}` }];
  }
  return [{ k: "fee", t: `입장료 줄이기: ${kept} — ${amount}` }];
}

// a title or a sentence that calls the plan free — what the site's fee numbers back only when no visit of the plan is
// paid or unpriced (plan_fees state 'free' or 'none'). Words on the plan as a whole ('무료 장소 위주', '무료 코스', '무료입장
// 명소 위주', '무료 하루'), whatever places the sentence names; words that call what they speak of free ('모두 무료', '입장료
// 부담 없이', '무료로 즐기는'): a sentence that names places of the site, all of them free by their fee value, speaks of
// those places and stands, and one of parking or of who enters free ('공영주차장은 모두 무료', '아이는 모두 무료', '65세
// 이상은 입장료 없이' — the site's own words) is no word on the plan (review of the fee edit: those cost a fix round and
// went, while '해망굴 등 무료 명소 위주' and '무료로 즐기는 원도심 하루' stood over paid visits)
const FREE_PLAN = new RegExp(String.raw`(?:무료|공짜|입장료\s*(?:가|이)?\s*없는)\s*(?:인|입장|관람)?\s*(?:곳|장소|명소|관광지|방문지)?\s*`
  + String.raw`(?:위주|중심|만으로|으로만|로만|만|코스|여행|일정|투어|나들이|산책|하루)(?!\s*프로그램)`, "u");
const FREE_SAID = new RegExp(String.raw`(?<![가-힣])(?:모두|전부|다)\s*무료(?!\s*(?:로\s*)?주차)|(?:무료|공짜)로\s*(?:즐기|둘러|돌아|구경|걷|다니|떠나)`
  + String.raw`|입장료\s*(?:없이|부담\s*(?:없|이\s*없|적|덜)|걱정\s*없|0원|들지\s*않|안\s*드|안\s*들)`, "u");
const NOT_PLAN = /주차|(?:아이|어린이|유아|아동|청소년|학생|어르신|경로|노인|장애인|유공자|이하|미만|이상)\s*(?:은|는|도)\s/u;
/** Whether a text calls the plan free when its fees do not back it, sentence by sentence: null when it does not (or
 *  they do), else {why: the reason for the model ('입장료를 내는 곳(테디베어박물관)이 일정에 있는데'), said: the words}. */
function freeClaim(text, fees, kb) {
  if (fees.state === "free" || fees.state === "none") return null;
  const free = (k) => !!((((kb.docs[k] || {}).f || {}).fee || {}).free);
  for (const t of String(text || "").split(/(?<=[.!?。])\s+/u)) {
    let m = FREE_PLAN.exec(t);
    if (!m) {
      m = FREE_SAID.exec(t);
      if (!m || NOT_PLAN.test(t.slice(0, m.index))) continue;
      const keys = kb.placeNames.filter(([n]) => t.includes(n)).map(([, k]) => k);
      if (keys.length && keys.every(free)) continue;
    }
    const { paid, open } = feeNames(fees);
    return { said: m[0], why: paid.length ? `입장료를 내는 곳(${paid.join("·")})이 일정에 있는데` : `요금을 확인하지 못한 곳(${open.join("·")})이 일정에 있는데` };
  }
  return null;
}

// the check's words for the model, as the reader reads them: no field names, no instruction to the planner
const FOR_MODEL = / — (?:일정에서 뺀다|출발지에서 오는 여유를 둔다|돌아갈 여유를 둔다|무료이거나 더 싼 곳으로 바꾼다|여유를 늘리거나 가까운 곳으로 바꾼다|이 구간을 따로 한 줄.*|그 시간에 여는 음식점을 넣는다|가까운 장소를 넣거나 앞뒤 장소를 늘린다|그날 마지막에 둔다|체크인 뒤로 둔다|맞는 곳으로 바꾼다|하루 \d+곳까지로 줄인다)$/u;
export const readerFlag = (t) => String(t).replace(/\(role stay\)/gu, "").replace(/독자가 정한 /gu, "고른 ").replace(FOR_MODEL, "")
  .replace(/\s{2,}/gu, " ").trim();

/** Where the trip starts and ends when the reader named a station or a terminal (plan_geo.hubLegs with the form's
 *  stations and terminals). */
export const hubLegs = (plan, c, kb = null) => hubLegsOf(plan, c, hubNames(), kb);

/** The model's sentences read against the pages: numbers the pages do not have, words that claim a check, a plan
 *  called free that its fees do not back (freeClaim). Returns errors (Korean, for the model). */
export function textIssues(plan, c, kb, fees) {
  const errors = [];
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const plain = [c.date, c.start, c.end, String(c.budget ?? ""), c.note, ...plan.days.flatMap((d) => d.stops.flatMap((s) => [s.start, s.end])),
    String(fees.known), String(fees.total ?? "")].join(" ");
  const all = `${plan.days.flatMap((d) => d.stops.map((s) => own(s.page))).join("\n")}\n${plain}`;
  plan.days.forEach((d, i) => d.stops.forEach((s, j) => {
    const g = grounded(s.why, `${own(s.page)}\n${plain}`);
    if (g.bad.length) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why의 숫자 ${g.bad.join("·")}가 그 장소 페이지에 없다 — 페이지에 있는 사실만 쓴다`);
    if (g.claim) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why: '확인됐다·보장·문제없다·걷는 거리를 줄였다'는 말은 쓰지 않는다(유모차·휠체어로 다니기 쉽다·편하다도 — 확인 상태는 사이트가 보여 주고, 걷는 거리와 다니기 쉬운지는 사이트에 없다)`);
    if (g.words.length) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why의 '${g.words.join("·")}'는 그 장소 페이지에 없다 — 페이지에 있는 접근 정보만 쓴다`);
  }));
  // (the title too — review 2026-10-22 S8: '휠체어 이동 확인된 원도심 하루, 엘리베이터·경사로 완비' stayed as the result's
  // heading while the same words left the summary and the notes)
  for (const [what, text] of [["title", plan.title], ["summary", plan.summary], ...plan.notes.map((n, k) => [`notes ${k + 1}`, n])]) {
    const g = grounded(text, all);
    if (g.bad.length) errors.push(`${what}의 숫자 ${g.bad.join("·")}가 일정의 장소 페이지에 없다 — 요금·합계·연도·거리는 쓰지 않는다(사이트가 계산해 보여 준다)`);
    if (g.claim) errors.push(`${what}: '확인됐다·보장·문제없다·모두 가능·걷는 거리를 줄였다'는 쓰지 않는다(유모차·휠체어로 다니기 쉽다·편하다도) — 확인 상태는 사이트가 따로 보여 주고, 걷는 거리와 다니기 쉬운지는 사이트에 없다`);
    if (g.words.length) errors.push(`${what}의 '${g.words.join("·")}'는 일정의 장소 페이지에 없다 — 페이지에 있는 접근 정보만 쓴다`);
    // (a plan called free with paid or unpriced visits — outside test 2026-10-23: '무료 장소 위주' over 24,000원)
    const free = freeClaim(text, fees, kb);
    if (free) errors.push(`${what}: ${free.why} 무료라고 쓴다('${free.said}') — 무료라는 말은 방문지가 모두 무료일 때만 쓴다(입장료를 줄여 달라면 입장료가 있는 곳을 무료이거나 더 싼 곳으로 바꾼다)`);
  }
  return errors;
}

/** The last word on the model's sentences after its one fix: a reason, a note or a summary sentence that still has a
 *  number the pages lack, an access word they do not back, or claims a check, little walking or a pram's or a
 *  wheelchair's easy way is left out, and so is a title, summary sentence or note that calls the plan free when its
 *  fees do not back it (freeClaim); such a title becomes the code's (codeText, as staleWords does — review
 *  2026-10-22 S8). */
export function trimText(plan, c, kb, fees) {
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const plain = [c.date, c.start, c.end, String(c.budget ?? ""), c.note, ...plan.days.flatMap((d) => d.stops.flatMap((s) => [s.start, s.end])),
    String(fees.known), String(fees.total ?? "")].join(" ");
  const all = `${plan.days.flatMap((d) => d.stops.map((s) => own(s.page))).join("\n")}\n${plain}`;
  const ok = (text, src) => { const g = grounded(text, src); return !g.bad.length && !g.words.length && !g.claim; };
  for (const d of plan.days) for (const s of d.stops) if (!ok(s.why, `${own(s.page)}\n${plain}`)) s.why = "";
  // (the plan's words — title, summary, notes — that call it free when its fees do not back it go too: freeClaim)
  const fair = (text) => ok(text, all) && !freeClaim(text, fees, kb);
  plan.summary = dropSentences(plan.summary, fair);
  plan.notes = plan.notes.filter(fair);
  if (plan.title && !fair(plan.title)) plan.title = codeText(plan, c, kb).title;
  return plan;
}

// a place said to be out of the plan: its name — alone or in a list ('A와 B는') — with a form of leaving it out a few
// characters after it ('A 대신', 'A는 빼고', 'A는 뺐습니다', 'A는 일정에서 제외했습니다', 'A는 제외하고 짰습니다'; no comma or
// full stop between), or a closed-day word next to it ('A는 월요일 휴관이라', '휴관인 A', '쉬는 날인 A') with a word of
// leaving it out later in the sentence ('… B로 바꿨습니다', '… 다음에 들르세요' — OUT_ANY: a closed day alone says
// nothing of the plan, round-6 verifier). Only such forms: '빼놓을 수 없는', '빼어난', '빼곡', '월요일을 제외하고 매일',
// '쉬는 날 없이', '휴관이 없다', '쉬는 날이 월요일이 아니지만' say nothing of the kind (reviews 2026-10-18, 10-19), and
// neither does a bare 쉬는·쉬어 ('쉬어 가는', '쉬는 시간').
const LOST = "\u0001";
const NOW_MARK = "\u0003";   // a place still in the plan (align's closed-day reading)
const OUT_AFTER = new RegExp(String.raw`^[^.!?,。\u0001]{0,10}?(?:대신|${CUT.source}|제외(?:했|하였|됐|되었)|일정에서\s*제외`
  + String.raw`|제외하고\s*(?:[^\s.!?,。\u0001]+\s+)?(?:넣|바꾸|바꿔|바꿨|짰|짜))`, "u");
// a closed day in words (round-6 final verifier: '쉽니다', '문을 닫습니다', '휴업', '휴장', '운영하지 않습니다',
// '정기휴일', '열지 않아요' went through as no closed day at all): the nouns on their own ('A는 수요일 휴장합니다'); the
// verbs — 쉬다, 문을 닫다, 운영·영업·개방하지 않다, 열지 않다 — only with a day before them in the clause ('수요일에 쉽니다',
// '오늘 문을 닫습니다'): '쉬어 가는 곳', '쉬는 시간', '공휴일에도 엽니다' are no closed day
const CLOSED_NOUN = String.raw`휴관|휴무|휴업|휴장|휴점|휴원|(?<!공)(?:정기\s*)?휴일(?!\s*에도)|쉬는\s*날`;
const CLOSED_VERB = String.raw`쉽니다|쉰다|쉬(?:어요|어서|어|고|며|는데|므로|니까|니)(?!\s*(?:가|갈|와|오|좋|쉬))|쉬기\s*때문|문을?\s*닫(?!지\s*않)`
  + String.raw`|(?:운영|영업|개방|개관)(?:을|를)?\s*(?:하지\s*않|안\s*하)|(?:문을?\s*)?열지\s*않|안\s*열`;
const DAYISH = String.raw`요일|오늘|내일|모레|그날|이날|당일|주말|평일|공휴일|명절|연휴|매주|매달|매월|격주|정기|[0-9]{1,2}\s*[월일]|동절기|겨울`;
const OUT_BEFORE = new RegExp(String.raw`(?:${CLOSED_NOUN})\s*(?:중)?인\s*$`, "u");
// a closed day denied ('휴관이 없다', '쉬는 날 없이', '휴관일이 아니', '쉬는 날이 월요일이 아니지만' — round-6 verifier: the
// last was read as a closed day and kept a sentence about a place that went)
const NOT_CLOSED = String.raw`\s*일?\s*(?:[이가은는도]\s*)?(?:[^\s.!?,。\u0001\u0003]{1,6}\s*[이가]\s*)?(?:없|아[니닙닌님])`;
// a closed day said of the place a few characters after its name ('A는 월요일 휴관이라') — a fact, held to the data
// (align): of a place that went, with OUT_ANY; of a place still in the plan, on its own
const CLOSED_AFTER = new RegExp(String.raw`^(?:[^.!?,。\u0001\u0003]{0,10}?(?:${CLOSED_NOUN})(?!${NOT_CLOSED})`
  + String.raw`|[^.!?,。\u0001\u0003]{0,10}?(?:${DAYISH})[^.!?,。\u0001\u0003]{0,8}?(?:${CLOSED_VERB}))`, "u");
// the same anywhere in a sentence: a stop's own reason that names no place speaks of its own stop ('매주 수요일에는
// 쉬는 날이라 짧게 둘러봅니다', '수요일 휴무입니다' — round-6 final verifier: kept on places open that Wednesday)
const CLOSED_ANY = new RegExp(String.raw`(?:${CLOSED_NOUN})(?!${NOT_CLOSED})|(?:${DAYISH})[^.!?,。]{0,8}?(?:${CLOSED_VERB})`, "u");
const OUT_ANY = new RegExp(String.raw`대신|${CUT.source}|제외|바꾸|바꿔|바꿨|바꾼|넣지\s*(?:않|못)|안\s*넣|못\s*넣|다음에|다음\s*기회|건너뛰|생략`, "u");
// a place that went is masked as LOST and a mark of its own (a private-use character: the n-th place that went); one
// still in the plan as NOW_MARK and its mark
const LOST_RUN = /\u0001[\uE000-\uF8FF](?:\s*(?:과|와|이랑|하고|및|[,·])\s*\u0001[\uE000-\uF8FF])*/gu;
const NOW_RUN = /\u0003[\uE000-\uF8FF](?:\s*(?:과|와|이랑|하고|및|[,·])\s*\u0003[\uE000-\uF8FF])*/gu;
/** The model's words read against the plan the code made of them (outside evaluation 2026-10-18: after an edit took
 *  the lunch out, the title still promised it): a sentence of the summary or a note, or a stop's reason, that names a
 *  place the plan had (`had`: the pages of every plan the model handed over in the run, and on an edit the plan before
 *  it — makePlan's `seen`) and no longer has is left
 *  out — unless every such name in it is said to be out (OUT_AFTER, OUT_BEFORE: 'A는 월요일 휴관이라 B로 바꿨습니다'
 *  stays, 'A 대신 C' goes when C went too); a summary or note sentence that names 점심 or 저녁 when the plan has no meal
 *  of that kind goes too, unless it says that meal is left out; a title that names a place that went, or promises a
 *  lunch or a dinner the plan lacks, becomes a plain one the code writes. The names are the site's own (each place's
 *  title and other names, kb.placeNames); the longer name is read first, a kept place's before a gone one's of the
 *  same length. Changes the plan in place; returns what it changed, in words for the reader. */
export function align(plan, c, kb, had, { final = false } = {}) {
  const out = [];
  const now = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.page)));
  // final (the last reading, after settle): a place of the site the words name that no plan of the run had (round-5
  // verifier: '점심은 한일옥에서' for a plan that never had it) is read as one that went, and said to be out or not, its
  // sentence goes (the model cannot have left out what it never had) — names of three characters or more, so a word
  // is not read as one
  const words = [plan.title, plan.summary, ...plan.notes, ...plan.days.flatMap((d) => d.stops.map((s) => s.why))].join("\n");
  const never = new Set(final ? kb.placeNames.filter(([n, k]) => [...n].length >= 3 && !now.has(k) && !had.has(k) && kb.docs[k] && words.includes(n)).map(([, k]) => k) : []);
  const gone = [...new Set([...had, ...never].filter((k) => !now.has(k) && kb.docs[k]))];
  const names = (keys) => [...new Set([...[...keys].map((k) => kb.docs[k].t), ...kb.placeNames.filter(([, k]) => keys.has(k)).map(([n]) => n)])];
  const marks = [...names(new Set([...now].filter((k) => kb.docs[k]))).map((n) => [n, " "]),
    ...gone.flatMap((k, i) => names(new Set([k])).map((n) => [n, `${LOST}${String.fromCharCode(0xe000 + (i % 6400))}`]))]
    .sort((a, b) => b[0].length - a[0].length);
  const masked = (text) => marks.reduce((t, [n, to]) => t.split(n).join(to), String(text || ""));
  const mentions = (text) => masked(text).includes(LOST);
  // a place said to be out because it is closed ('A는 월요일 휴관이라 뺐습니다') is so by the data on a date of the trip
  // (dayInfo: a closed day or a notice — the code's own swap of a closed stop is one); else the reason is the model's
  // own, not the site's, and the sentence goes (round-6 verifier: 'OO 철길마을은 월요일 휴관이라 뺐습니다' on a
  // Wednesday, for a place the data says is open every day)
  const dates = tripDates(c.date, c.days);
  const shut = (k) => dates.some((date) => dayInfo(kb, date, k).state === "closed");
  const unfounded = new Set();   // the places a sentence left out said closed against the data
  // the form a place that went is named in: said out (OUT_AFTER), or said closed (a closed-day word next to it) and out
  // somewhere after it (OUT_ANY) — 'closed' then
  const outForm = (after, before) => {
    if (CLOSED_AFTER.test(after) || OUT_BEFORE.test(before)) return OUT_ANY.test(after) ? "closed" : "";
    return OUT_AFTER.test(after) ? "out" : "";
  };
  // every place that went, named in the text, is said to be out — when it is for a closed day, by the data (`bad`:
  // where the places said closed against it go)
  const saysOut = (text, bad = []) => {
    const t = masked(text);
    return [...t.matchAll(LOST_RUN)].every((m) => {
      const form = outForm(t.slice(m.index + m[0].length), t.slice(0, m.index));
      if (form !== "closed") return form === "out";
      const keys = [...m[0].matchAll(/\u0001([\uE000-\uF8FF])/gu)].map((x) => gone[x[1].charCodeAt(0) - 0xe000]);
      bad.push(...keys.filter((k) => !shut(k)));
      return keys.every(shut);
    });
  };
  // a place still in the plan said to be closed ('역사박물관은 수요일 휴관이라 다른 곳으로 바꿨습니다', 'OO사진관은
  // 수요일 휴무입니다' — round-6 verifier: both sent with the places open that Wednesday by the data) is so by the data
  // on a date of the trip (closed, or a day it leaves to check: a 설·추석·공휴일 rule) — else the sentence goes
  const nowKeys = [...now].filter((k) => kb.docs[k]);
  const nowMarks = [...nowKeys.flatMap((k, i) => names(new Set([k])).map((n) => [n, `${NOW_MARK}${String.fromCharCode(0xe000 + (i % 6400))}`])),
    ...gone.flatMap((k) => names(new Set([k])).map((n) => [n, LOST]))].sort((a, b) => b[0].length - a[0].length);
  const shutOr = (k) => dates.some((date) => ["closed", "check"].includes(dayInfo(kb, date, k).state));
  // a sentence that names the weekdays a place still in the plan is closed on, every one of them a closed day by the
  // data ('매주 월요일에 쉽니다' of a museum closed on Mondays, on a Wednesday trip): the data's own rule, not a closed
  // day of the trip — it stays (the live check's true sentences, round-6 final verifier). Each weekday is read on its
  // first date from the trip's first day.
  const weekdaysShut = (whole, k) => {
    // (the weekdays of the closing itself: up to the closed-day word — '매주 월요일에 쉬고 수요일에는 엽니다')
    const hit = CLOSED_ANY.exec(String(whole || ""));
    const text = hit ? String(whole).slice(0, hit.index + hit[0].length) : "";
    const days = [...new Set([...text.matchAll(/([월화수목금토일](?:\s*[·,、및~]\s*[월화수목금토일])*)\s*요일/gu)].flatMap((m) => m[1].match(/[월화수목금토일]/gu)))];
    if (!days.length || /오늘|내일|그날|이날|당일/u.test(text)) return false;
    const d0 = new Date(`${dates[0]}T12:00:00Z`);
    return days.every((w) => {
      const date = new Date(d0.getTime() + ((WEEK.indexOf(w) - d0.getUTCDay() + 7) % 7) * 86400000).toISOString().slice(0, 10);
      return dayInfo(kb, date, k).state === "closed";
    });
  };
  // own: the stop whose reason this is — a reason naming no place of the site says its closed day of that stop
  const keepNow = (text, own = "") => {
    const t = nowMarks.reduce((x, [n, to]) => x.split(n).join(to), String(text || ""));
    if (!t.includes(NOW_MARK)) {
      if (!own || t.includes(LOST) || !CLOSED_ANY.test(t) || shutOr(own) || weekdaysShut(t, own) || kb.placeNames.some(([n]) => t.includes(n))) return true;
      unfounded.add(own);
      closedBad += 1;
      return false;
    }
    const bad = [];
    for (const m of t.matchAll(NOW_RUN)) {
      if (!CLOSED_AFTER.test(t.slice(m.index + m[0].length)) && !OUT_BEFORE.test(t.slice(0, m.index))) continue;
      bad.push(...[...m[0].matchAll(/\u0003([\uE000-\uF8FF])/gu)].map((x) => nowKeys[x[1].charCodeAt(0) - 0xe000]).filter((k) => !shutOr(k) && !weekdaysShut(t, k)));
    }
    if (!bad.length) return true;
    for (const k of bad) unfounded.add(k);
    closedBad += 1;
    return false;
  };
  const noMeal = ["lunch", "dinner"].filter((kind) => !plan.days.some((d) => mealIn(d.stops, MEALS[kind], kb)));
  let dropped = 0, closedBad = 0;
  const named = new Set();   // the places that went named in the sentences left out
  const meals = new Map();   // kind → sentences left out for promising it
  const keep = (s) => {
    const bad = [];
    if (mentions(s) && (!saysOut(s, bad) || [...masked(s).matchAll(/\u0001([\uE000-\uF8FF])/gu)].some((m) => never.has(gone[m[1].charCodeAt(0) - 0xe000])))) {
      // a sentence that goes only for a closed day the data does not have: said apart
      if (bad.length && saysOutAnyway(s)) {
        for (const k of bad) unfounded.add(k);
        closedBad += 1;
        return false;
      }
      dropped += 1;
      for (const m of masked(s).matchAll(/\u0001([\uE000-\uF8FF])/gu)) named.add(gone[m[1].charCodeAt(0) - 0xe000]);
      return false;
    }
    return true;
  };
  // the sentence says every place out (any form) and names none the run never had: what is wrong is the closed day
  const saysOutAnyway = (s) => {
    const t = masked(s);
    return [...t.matchAll(LOST_RUN)].every((m) => !!outForm(t.slice(m.index + m[0].length), t.slice(0, m.index)))
      && ![...t.matchAll(/\u0001([\uE000-\uF8FF])/gu)].some((m) => never.has(gone[m[1].charCodeAt(0) - 0xe000]));
  };
  // a sentence of the summary or a note that promises a meal the plan does not have
  const keepMeal = (s) => {
    const kinds = noMeal.filter((kind) => s.includes(MEALS[kind].label) && !eatsElsewhere(kind, s));
    for (const kind of kinds) meals.set(kind, (meals.get(kind) || 0) + 1);
    return !kinds.length;
  };
  // the places still in the plan said closed against the data first (their line is the one below)
  plan.summary = dropSentences(plan.summary, keepNow);
  plan.notes = plan.notes.map((n) => dropSentences(n, keepNow)).filter(Boolean);
  for (const d of plan.days) for (const s of d.stops) if (s.why) s.why = dropSentences(s.why, (x) => keepNow(x, s.page));
  if (gone.length) {
    plan.summary = dropSentences(plan.summary, keep);
    plan.notes = plan.notes.map((n) => dropSentences(n, keep)).filter(Boolean);
    for (const d of plan.days) for (const s of d.stops) if (s.why && !keep(s.why)) s.why = "";
    // the line names the places of the sentences left out, not every place that went: those the plan had, then those
    // it never had
    const went = gone.filter((k) => named.has(k) && !never.has(k)).map((k) => kb.docs[k].t);
    const not = gone.filter((k) => named.has(k) && never.has(k)).map((k) => kb.docs[k].t);
    const parts = [went.length ? `일정에서 빠진 ${went.join("·")}` : "", not.length ? `일정에 없는 ${not.join("·")}` : ""].filter(Boolean);
    const lastName = (not.length ? not : went).at(-1);
    if (dropped) out.push(`AI 설명: ${parts.length > 1 ? `${parts[0]}${jong(went.at(-1)) > 0 ? "과" : "와"} ${parts[1]}` : parts[0]}${eul(lastName)} 말하는 문장 ${dropped}개를 뺐습니다`);
  }
  if (closedBad) {
    const shutNames = [...gone, ...nowKeys].filter((k) => unfounded.has(k)).map((k) => kb.docs[k].t);
    out.push(`AI 설명: ${shutNames.join("·")}${iga(shutNames.at(-1))} 여행 날짜에 쉰다는 자료가 없어 쉰다고 말하는 문장 ${closedBad}개를 뺐습니다`);
  }
  if (noMeal.length) {
    plan.summary = dropSentences(plan.summary, keepMeal);
    plan.notes = plan.notes.map((n) => dropSentences(n, keepMeal)).filter(Boolean);
    for (const [kind, n] of meals) out.push(`AI 설명: 일정에 ${MEALS[kind].label}이 없어 ${MEALS[kind].label}${eul(MEALS[kind].label)} 말하는 문장 ${n}개를 뺐습니다`);
  }
  // a sentence that says the plan has no night's stay, or no meals, when every night has its stay or every day a meal
  // (round 7 review A02, A07, A08, A10: '1박 2일의 숙소와 식사 장소는 이 계획에 넣지 않았습니다', '요청하신 숙소는 이 일정에
  // 넣지 않았습니다', '밤에 머무는 곳은 따로 정해 주세요', '식사 단계는 음식점 페이지가 아니라 시장 리스트로 대체했습니다' — the
  // code had put the stays in, or the model the meals)
  const nights = plan.days.slice(0, -1);
  const stays = nights.length > 0 && nights.every((d) => d.stops.some((s) => s.role === "stay"));
  const eats = plan.days.every((d) => d.stops.some((s) => s.role === "meal" && !isCafe(kb.docs[s.page])));
  // (a sentence of the lunch or the dinner only when every day has that one: '점심은 넣지 않았습니다' of a trip whose
  // first day starts after lunch is true)
  const every = (m) => plan.days.every((d) => mealIn(d.stops, m, kb));
  const denied = { stay: false, meal: false, n: 0 };
  const denies = (x) => {
    const stay = stays && STAY_SAID.test(x) && (NOT_IN.test(x) || STAY_FIND.test(x));
    const meal = eats && MEAL_SAID.test(x) && (NOT_IN.test(x) || NOT_RESTAURANT.test(x))
      && (!/점심/u.test(x) || every(MEALS.lunch)) && (!/저녁/u.test(x) || every(MEALS.dinner));
    denied.stay ||= stay;
    denied.meal ||= meal;
    if (stay || meal) denied.n += 1;
    return !stay && !meal;
  };
  plan.summary = dropSentences(plan.summary, denies);
  plan.notes = plan.notes.map((n) => dropSentences(n, denies)).filter(Boolean);
  const what = [denied.stay ? "밤 숙소" : "", denied.meal ? "식사" : ""].filter(Boolean);
  if (what.length) out.push(`AI 설명: 일정에 있는 ${what.join("·")}${eul(what.at(-1))} 넣지 않았다고 말하는 문장 ${denied.n}개를 뺐습니다`);
  const lacks = (word, meal) => word.test(plan.title) && !plan.days.some((d) => mealIn(d.stops, meal, kb));
  if (mentions(plan.title) || lacks(/점심/u, MEALS.lunch) || lacks(/저녁/u, MEALS.dinner)) {
    const title = `${dateWords(c.date)} ${regionWord()}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`;
    out.push(`제목: 바뀐 일정과 맞지 않아 '${plan.title}'에서 '${title}'${ro(title)} 바꿨습니다`);
    plan.title = title;
  }
  return out;
}

// the words a sentence names day i of n by ('2일차', '둘째 날', '마지막 날', '11월 21일', '21일(토)', '토요일')
const ORDINAL = ["첫", "둘째", "셋째", "넷째", "다섯째", "여섯째", "일곱째"];
function namesDay(text, i, n, date) {
  const dt = new Date(`${date}T12:00:00Z`);
  const m = dt.getUTCMonth() + 1, dd = dt.getUTCDate(), wd = WEEK[dt.getUTCDay()];
  const words = [`(?<!\\d)${i + 1}\\s*일\\s*차`, `${ORDINAL[i]}(?:째)?\\s*날`, `${m}\\s*월\\s*${dd}\\s*일`, `(?<!\\d)${dd}\\s*일\\s*\\(${wd}`, `${wd}요일`,
    ...(i === n - 1 && n > 1 ? ["마지막\\s*날"] : [])];
  return new RegExp(words.join("|"), "u").test(text);
}

// a night's stay or meals in the AI's words, said not to be in the plan (align): not put in, left out, to be found by
// the reader ('따로 정해 주세요', '숙소를 정하세요'); meals that are no restaurant ('음식점 페이지가 아니라 … 대체했습니다').
// Booking is the reader's in any plan ('숙소 예약은 직접 하세요' stays).
const STAY_SAID = /숙소|숙박|머무(?:는|를)\s*곳|\d\s*박은/u;
const MEAL_SAID = /식사|식당|음식점|끼니/u;
const NOT_IN = /(?:넣|포함하|포함되|잡)지\s*(?:않|못)|안\s*넣|빠져\s*있|빠졌|(?:따로|직접|별도로?)\s*(?:정하|정해|잡|구하|구해|알아보)/u;
const STAY_FIND = /(?:숙소|머무(?:는|를)\s*곳)(?:을|를|은|는|도)?\s*(?:정하|정해|구하|구해|알아보)/u;
const NOT_RESTAURANT = /음식점[^.!?]{0,8}아니라|대체했|대체합/u;

// a clock time in the AI's words: HH:MM, or N시 (N시 M분, N시 반) with the part of the day before it read
// — the hour in digits or in words ('네 시', '오후 두 시 반': round-6 final verifier, '네 시에 저녁을 먹어요' was kept of a
// dinner moved to 17:30)
const CLOCK = /(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])|(?:(오전|아침|오후|낮|저녁|밤)\s*)?(?:(?<![\d.:])(\d{1,2})|(?<![가-힣])(열한|열두|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열))\s*시(?!간|대|각|절|기|작|청|장|내|민|설|점|즌|티|트|적)(?:\s*(\d{1,2})\s*분|\s*(반))?/gu;
const HOUR_WORDS = { 한: 1, 두: 2, 세: 3, 네: 4, 다섯: 5, 여섯: 6, 일곱: 7, 여덟: 8, 아홉: 9, 열: 10, 열한: 11, 열두: 12 };
/** The minutes a clock time of the AI's words may be: one, or two for a bare 'N시' (3시: 03:00 or 15:00). */
function clockTimes(m) {
  if (m[1] !== undefined) return [+m[1] * 60 + +m[2]];
  const h = m[4] !== undefined ? +m[4] : HOUR_WORDS[m[5]], min = m[6] !== undefined ? +m[6] : m[7] ? 30 : 0;
  if (h > 24 || min > 59) return [];
  if (/오후|저녁|밤/u.test(m[3] || "")) return [((h % 12) + 12) * 60 + min];
  if (m[3] === "낮") return [(h <= 6 ? h + 12 : h) * 60 + min];
  if (/오전|아침/u.test(m[3] || "")) return [(h % 12) * 60 + min];
  return h < 12 ? [h * 60 + min, (h + 12) * 60 + min] : [h * 60 + min];
}
/** The AI's words read against the times the plan now has (round-6 verifier: the code moved a model's meal into its
 *  window or cut it to MEAL_LONG, and its reason still said '15:30에 OO순두부에서 점심을 먹어요' on a stop at
 *  18:00–19:00 — signed, and shown to a link's reader as the site's): a sentence goes when it puts something at a
 *  clock time ('15:30에', '3시쯤에') that no stop of the plan starts or ends at (a reason: no stop of its day), nor the
 *  reader's start or end — or states any other time that neither those nor the place pages have (a page's hours,
 *  '10:00~17:00에 문을 엽니다', stand on the page); so does a sentence of a meal's reason that names the other meal
 *  (점심 for a meal the plan has as the dinner) and not its own. A title with such a time becomes the code's. Changes
 *  the plan in place; returns the reader's line, or none. */
export function staleWords(plan, c, kb) {
  const at = (stops, ends = true) => new Set([hm(c.start), hm(c.end), ...stops.flatMap((s) => (ends ? [hm(s.start), hm(s.end)] : [hm(s.start)]))].filter((x) => x !== null));
  // a page's times: its text and its hours lines
  const onPage = (stops) => new Set(stops.flatMap((s) => {
    const doc = kb.docs[s.page] || {};
    return [...[doc.x || "", ...((doc.f || {}).h || []).map((h) => h.t || "")].join("\n").matchAll(CLOCK)].flatMap(clockTimes);
  }));
  const all = plan.days.flatMap((d) => d.stops);
  const allAt = at(all), allStarts = at(all, false), allPage = onPage(all);
  // times: what a time may be at all; put: what a time something is put at may be — a stop's start (or the reader's
  // start or end): a stop's end would read '20:00에 저녁을 먹어요' of a dinner moved to 19:00–20:00 as true
  const fits = (text, times, page, put = times) => {
    const t = String(text || "");
    const ms = [...t.matchAll(CLOCK)];
    return ms.every((m, k) => {
      const xs = clockTimes(m);
      if (!xs.length) return true;
      const end = m.index + m[0].length;
      // a range (A~B, A부터 B까지): an hours line, of the plan or of a page
      const ranged = (k > 0 && /^\s*(?:~|-|–|부터)\s*$/u.test(t.slice(ms[k - 1].index + ms[k - 1][0].length, m.index)))
        || (k + 1 < ms.length && /^\s*(?:~|-|–|부터)\s*$/u.test(t.slice(end, ms[k + 1].index)));
      // a time something is put at ('15:30에', '3시쯤에', '17:00부터 식사해요' — not '10:00부터 영업해요', the page's
      // hours): the plan's own times only
      const rest = t.slice(end);
      const said = !ranged && (/^\s*(?:쯤|경)?\s*에(?!서)/u.test(rest)
        || /^\s*(?:쯤|경)\s*(?:도착|출발|들[러르어]|입장|시작|식사|먹)/u.test(rest)   // ('15:05쯤 도착해': round-6 final verifier)
        || (/^\s*(?:쯤|경)?\s*부터/u.test(rest) && !/^\s*(?:쯤|경)?\s*부터[^.!?]{0,12}?(?:영업|문을?\s*(?:열|엽|연)|열[어고며려]|엽니|연다|여는|개장|운영|오픈|입장|개방)/u.test(rest)));
      return xs.some((x) => (said ? put.has(x) : times.has(x) || page.has(x)));
    });
  };
  let n = 0;
  // a length the AI gives a stop ('두 시간 동안', '1시간 반') longer than the stop now has (round-6 final verifier: '두 시간
  // 동안 천천히 먹습니다' of a meal cut to MEAL_LONG) — not a leg's ('차로 1시간', '걸어서 …')
  const HOURS = /(?<![\d가-힣])(\d{1,2}|한|두|세|네|다섯|여섯)\s*시간(?:\s*(반)|\s*(\d{1,2})\s*분)?/gu;
  const longer = (x, s) => !!s && !/차로|차를|운전|걸어|걷|도보|버스|이동|거리|떨어/u.test(x)
    && [...x.matchAll(HOURS)].some((m) => (/\d/u.test(m[1]) ? +m[1] : HOUR_WORDS[m[1]]) * 60 + (m[2] ? 30 : m[3] ? +m[3] : 0) > hm(s.end) - hm(s.start));
  const keep = (times, page, meal = "", put = times, own = null) => (x) => {
    const other = meal && MEALS[meal === "lunch" ? "dinner" : "lunch"].label;
    if (fits(x, times, page, put) && !(other && x.includes(other) && !x.includes(MEALS[meal].label)) && !longer(x, own)) return true;
    n += 1;
    return false;
  };
  // a stop's reason speaks of that stop: the only times it may put a thing at are the stop's own start, the only
  // others its own start and end — or its page's (round-6 final verifier: '10:00에 들릅니다' was kept of a stop moved to
  // 10:30 as 10:00 was the reader's start; '18:30에 들릅니다' of a stop moved to 19:55 as 18:30 was another's start)
  for (const d of plan.days) {
    for (const s of d.stops) {
      if (!s.why) continue;
      const meal = s.role === "meal" ? mealKind(hm(s.start), hm(s.end)) : "";
      s.why = dropSentences(s.why, keep(new Set([hm(s.start), hm(s.end)]), onPage([s]), meal, new Set([hm(s.start)]), s));
    }
  }
  // a sentence of the summary or a note that names places of the plan puts a thing only at one of their starts ('점심은
  // 12:35에 란향에서 먹어요' of 란향 moved to 11:05 — round-6 final verifier); one that names none, at any stop's start or
  // the reader's start or end
  const named = plan.days.flatMap((d) => d.stops).flatMap((s) => [...new Set([s.name, ...kb.placeNames.filter(([, k]) => k === s.page).map(([x]) => x)])]
    .map((name) => ({ name, s }))).sort((p, q) => q.name.length - p.name.length);
  const general = (x) => {
    let rest = String(x || "");
    const own = [];
    for (const { name, s } of named) if (rest.includes(name)) { own.push(s); rest = rest.split(name).join(" "); }
    if (!own.length) return keep(allAt, allPage, "", allStarts)(x);
    // (a length longer than every place it names has: '셋째 날 저녁은 OO한우촌에서 두 시간 먹습니다' of a dinner of 90)
    if (own.every((s) => longer(x, s))) { n += 1; return false; }
    return keep(allAt, allPage, "", new Set(own.map((s) => hm(s.start))))(x);
  };
  plan.summary = dropSentences(plan.summary, general);
  plan.notes = (plan.notes || []).map((x) => dropSentences(x, general)).filter(Boolean);
  if (plan.title && !fits(plan.title, allAt, allPage, allStarts)) {
    plan.title = codeText(plan, c, kb).title;
    n += 1;
  }
  return n ? [`AI 설명: 바뀐 일정의 시각이나 끼니와 맞지 않는 문장 ${n}개를 뺐습니다`] : [];
}

/** The plan read against the data and the conditions: each day's checkPlan, the day's hours the reader set, a stay
 *  each night but the last — the day's last stop, not before its check-in time —, the code's own margin on every leg
 *  next to a stop it put in, swapped in or moved, the fee total against the budget, a meal when a day spans one and
 *  no empty stretch (plan_state.completeness). {days: [checkPlan result], flags, fees, complete, ...}. edit:
 *  makePlan's. */
export function verify(plan, c, kb, edit = null) {
  const r = planFlags(plan, c, kb, edit);
  const needs = needsTable(plan, c, kb, r.fees);
  const { aware, checks } = checksList(plan, c, { days: r.days }, needs, r.fees, r.hubs, kb);
  aware.push(...rainKept(plan, c, kb, edit).map((x) => ({ k: "need", t: x.t })));
  return { days: r.days, flags: r.list.map((x) => x.text), list: r.list, fees: r.fees, hubs: r.hubs, needs, checks, aware, complete: r.complete,
    text: textIssues(plan, c, kb, r.fees) };
}

/** The rainy days that keep more outdoor visits than the one because the reader asked for every one of them
 *  (plan_build.rainAsked — operator 2026-10-23): one line a day, '비 오는 날 야외 장소 2곳 — 요청대로 두었어요(OO공원·
 *  OO호수공원)', for '가기 전에 알아 둘 것' (verify's aware, k need) and, when this edit asked for one of them (now),
 *  for what the edit changed ('바꾼 뒤 달라진 것': makePlan's edited, k rain). [{t, now}] */
function rainKept(plan, c, kb, edit) {
  const many = plan.days.length > 1;
  return plan.days.flatMap((d, i) => {
    const r = rainOutdoor(d, i, c, kb, edit);
    if (!r || r.all.length < 2 || r.asked.length < r.all.length) return [];
    return [{ t: `${many ? `${i + 1}일차 ` : ""}비 오는 날 야외 장소 ${r.all.length}곳 — 요청대로 두었어요(${r.all.map((s) => s.name).join("·")})`,
      now: r.all.some((s) => s.asked) }];
  });
}

/** What is still wrong with a finished plan, by the kind of fix it needs (the page's quick fixes): closed (a stop
 *  closed that day), legs (a leg with no time or too little for its line), meal, gaps. */
export function todoOf(check) {
  const out = [];
  if (check.days.some((r) => r.stops.some((s) => s.day === "closed"))) out.push("closed");
  if (check.days.some((r) => r.legs.some((l) => l.flag))) out.push("legs");
  if (check.complete.meals.some((m) => m.state === "missing")) out.push("meal");
  if (check.complete.gaps.length) out.push("gaps");
  return out;
}

/** The reader's list of what the site put right, read against the plan they get (round-5 verifier: it was a running
 *  log — places put in that a later step took out again, cuts that changed nothing): a line that puts in a place no
 *  longer in the plan goes, and so does a later line of that place's; a swap whose place went says the stop it
 *  replaced was taken out; a time changed to itself goes; the same line twice is said once. */
export function tidyFixed(fixed, plan) {
  const names = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.name)));
  const many = plan.days.length > 1;
  // the names on the day a line is of ('2일차 …'; a one-day plan's lines have no day)
  const onDay = (t) => {
    const m = /^(\d+)일차 /u.exec(t);
    const d = plan.days[many && m ? +m[1] - 1 : 0];
    return new Set(d ? d.stops.map((s) => s.name) : []);
  };
  // the meal lines of tidyMeals (round-6 verifier: '금강해물칼국수: 그날 점심은 유성가든에서 먹어 일정에서 뺐습니다' on a day
  // 유성가든 had left again): the meal a stop gave way to, named, is on that day of the plan — else the reason is the
  // rule itself; a meal moved or cut that has left the day since says nothing
  const KEPT_MEAL = /^((?:\d+일차 )?.+?: )(?:그날 (?:점심|저녁)은 (.+?)에서 먹어|(?:점심|저녁)\((.+?)\)[과와] 시작이 .+?밖에 차이 나지 않아)( 일정에서 뺐습니다.*)$/u;
  const MEAL_MOVE = /^(?:\d+일차 )?(.+?): (?:(?:점심|저녁) 시간에 맞춰 |식사는 \d+분까지로 잡아 |바꿔 달라는 말대로 그날 식사가 아닌 간식 자리)/u;
  fixed = fixed.flatMap((t) => {
    const k = KEPT_MEAL.exec(t);
    if (k && !onDay(t).has(k[2] || k[3])) return [`${k[1]}하루 식사는 점심·저녁 한 번씩으로 잡아${k[4]}`];
    const mv = MEAL_MOVE.exec(t);
    if (mv && !onDay(t).has(mv[1])) return [];
    return [t];
  });
  const PUT = /가까운 (?:음식점 |숙소 )?(.+?)\(직선 [^)]*\)/u;
  const SAME = /같은 숙소 (.+?)[을를] 넣었습니다/u;
  const SWAP = /^((?:\d일차 )?)(.+?): (.+?) 가까운 (.+?)\(직선 [^)]*\)(?:으로|로|\(으\)로) 바꿨습니다/u;
  const ours = new Set();   // places the code put in that went again
  for (const t of fixed) {
    const m = PUT.exec(t) || SAME.exec(t);
    if (m && !names.has(m[1])) ours.add(m[1]);
  }
  const out = [];
  for (const t of fixed) {
    if (/(\d\d:\d\d~\d\d:\d\d)에서 \1(?:으로|로)/u.test(t) || /(?<![~\d])(\d\d:\d\d)에서 \1(?:으로|로) /u.test(t)) continue;
    const head = /^(?:\d일차 )?(?:밤 숙소 )?(.+?): /u.exec(t);
    if (head && ours.has(head[1])) continue;
    // (a margin kept to or from a place the code put in that went again: round 7 — '밤 숙소 …: 앞 장소 섬 식당에서
    // 여유 125분을 두려고 …' after that dinner moved near the stay)
    const gap = /(?:앞|다음) 장소 (.+?)(?:에서|까지) 여유 /u.exec(t);
    if (gap && ours.has(gap[1])) continue;
    const sw = SWAP.exec(t);
    if (sw && ours.has(sw[4])) {
      if (!names.has(sw[2])) out.push(`${sw[1]}${sw[2]}: ${sw[3]} 일정에서 뺐습니다`);
      continue;
    }
    const m = PUT.exec(t) || SAME.exec(t);
    if (m && ours.has(m[1])) continue;
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

/** Kakao Map directions between two points (the reader's map app works out the route and its time; pipeline/maplinks.py
 *  kakao_transit_url is the same address for 'traffic'): by car, on foot under 1.2 km for a reader without a car,
 *  else public transport. */
export function directionsUrl(a, b, move, m) {
  const mode = move === "car" ? "car" : m !== null && m <= 1200 ? "walk" : "traffic";
  const q = (s) => encodeURIComponent(s).replace(/%2C/gi, " ");
  return { mode, url: `https://map.kakao.com/link/by/${mode}/${q(a.name)},${a.lat},${a.lng}/${q(b.name)},${b.lat},${b.lng}` };
}

/** What the page gets: the plan with each stop's day state and notes from checkPlan (added: a stop the site put in;
 *  swapped: one the site chose for another — 'closed' for a stop closed that day by every source, 'other' for any
 *  other reason: a closed day the sources differ on, a budget, a need, a repeat, hours, a break, the rain, a dinner near
 *  the night's stay; review 2026-10-22 S5),
 *  each leg's distance, routes and directions link, the fee lines and total against the budget, what is still
 *  flagged, the completeness (plan_state.completeness) and what is left to fix by kind (todoOf). */
export function finish(plan, check, c, now = new Date(), fixed = []) {
  const days = plan.days.map((d, i) => {
    const r = check.days[i];
    const dt = new Date(`${d.date}T12:00:00Z`);
    return {
      date: d.date, label: `${i + 1}일차 · ${dt.getUTCMonth() + 1}월 ${dt.getUTCDate()}일 (${WEEK[dt.getUTCDay()]})`,
      stops: d.stops.map((s, j) => {
        const st = r.stops[j] || { day: "unknown", notes: [], flags: [] };
        return { path: s.page, name: s.name, start: s.start, end: s.end, role: s.role, why: s.why, day: st.day,
          notes: st.notes, flags: (st.flags || []).map(readerFlag), checks: st.checks || [],
          // a place whose inside is not open to visitors (checkPlan outside): the card says so with its sources
          ...(st.outside ? { outside: st.outside } : {}),
          ...(s.by === "site" ? { added: true } : s.by === "swap" ? { swapped: s.swap === "closed" ? "closed" : "other" } : {}) };
      }),
      // (open: a leg without a car the site cannot confirm — knowledge.checkPlan in a city whose data names no bus)
      legs: r.legs.map((l) => ({ from: l.from, to: l.to, m: l.m, gap: l.gap, routes: l.routes, flag: l.flag, ...(l.open ? { open: true } : {}),
        ...(l.a && l.b ? directionsUrl(l.a, l.b, c.move, l.m) : {}) })),
      hubs: (check.hubs || []).filter((h) => (h.dir === "from" ? i === 0 : i === plan.days.length - 1)),
      // a year the site's 설·추석·대체공휴일 table does not cover (checkPlan's noHolidayTable): the page's date rows
      // never read all-clear for that day (review 2026-10-22 S9)
      ...(r.noHolidayTable ? { noHolidayTable: true } : {}),
    };
  });
  const f = check.fees;
  const fees = { state: f.state, total: f.total, known: f.known, limit: f.limit, verdict: f.verdict, open: f.open,
    conds: f.conds, days: f.days.map((d) => ({ date: d.date, lines: d.lines.map((l) => ({ what: l.what, who: l.who,
      count: l.count, status: l.status, won: l.won ?? null, sub: l.sub, basis: l.basis })) })) };
  // status 'ready' and flags [] for every plan the page gets (makePlan never sends one with flags: operator
  // 2026-10-18); todo stays for pages of the old payload, always empty
  return { v: 2, made: now.toISOString(), title: plan.title, summary: plan.summary, notes: plan.notes, conditions: c,
    days, fees, needs: check.needs, checks: check.checks, aware: noteAware(check.aware, c, fixed), flags: check.flags.map(readerFlag), fixed,
    status: statusOf(check.flags), complete: check.complete, todo: [] };
}

/** The places closed on each date of the trip by their regular closed days or a dated notice — checkPlan's own
 *  reading, places to visit and restaurants — handed over with the conditions so the model does not pick them
 *  (outside evaluation 2026-10-18: five of six stops of a Monday plan were closed that day). One line a date: names
 *  and paths (the path alone when it is the name). */
export function closedHints(c, kb) {
  const keys = kb.keys.filter((k) => kb.docs[k] && kb.docs[k].k === "place" && ["attraction", "food"].includes((kb.docs[k].f || {}).kd));
  const label = (key) => (key === `/places/${kb.docs[key].t.replace(/\s+/gu, "-")}/` ? key : `${kb.docs[key].t} ${key}`);
  const days = tripDates(c.date, c.days).map((date) => {
    const shut = [];
    for (let k = 0; k < keys.length; k += 12) {   // checkPlan reads twelve stops a call
      const r = kb.checkPlan({ date, stops: keys.slice(k, k + 12).map((page) => ({ page, start: "", end: "" })) });
      r.stops.forEach((s, j) => { if (s.day === "closed") shut.push(keys[k + j]); });
    }
    return `${date}(${WEEK[new Date(`${date}T12:00:00Z`).getUTCDay()]}) 쉬는 곳 ${shut.length}곳 — 이날 일정에 넣지 않는다: ${shut.map(label).join("; ") || "없음"}`;
  });
  // '비 와도 실내 위주': the places whose closed days say they shut in the rain ('우천시 휴장' — plan_state.rainShut;
  // round-6 final verifier: the model kept OO어린이랜드 on rain trips and nothing told it)
  if (c.needs.includes("rain")) {
    const wet = keys.filter((k) => rainShut(kb.docs[k].f || {}));
    if (wet.length) days.push(`비 오는 날 쉰다고 자료에 있는 곳 ${wet.length}곳 — '비 와도 실내 위주'라 어느 날에도 넣지 않는다: ${wet.map(label).join("; ")}`);
  }
  return days.join("\n");
}

/** The places whose site data fits each need the reader picked (plan_state.needAt 'ok' or, for parking, 'near'),
 *  as catalog paths — handed over with the conditions so the model needs no reading round to find them. At most
 *  30 a need; the facts behind them are the pages' own (the page shows each in the needs table). */
export function needHints(c, kb, max = 30) {
  const needs = c.needs.filter((n) => n !== "lesswalk");
  if (!needs.length) return "고른 조건이 없다.";
  const L = [];
  for (const need of needs) {
    const fit = [];
    for (const key of kb.keys) {
      const d = kb.docs[key];
      if (!d || d.k !== "place" || !d.f) continue;
      if (need !== "parking" && d.f.kd !== "attraction") continue;   // the places to visit; parking matters everywhere
      const r = needAt(need, d.f, d.f.kd === "food" ? "meal" : d.f.kd === "stay" ? "stay" : "visit",
        need === "free" ? { how: "own", states: d.f.fee && d.f.fee.free ? { free: 1 } : d.f.fee && d.f.fee.tab ? { paid: 1 } : { unknown: 1 } } : null, c.move);
      if (r.state === "ok" || r.state === "near") fit.push(`${d.t} ${key}`);
      if (fit.length >= max) break;
    }
    L.push(`${NEEDS[need]} — 사이트 자료가 맞다고 하는 곳${fit.length >= max ? `(앞 ${max}곳)` : ""}: ${fit.join("; ") || "없음"}`);
  }
  return L.join("\n");
}

// ------------------------------------------------------------------ a stop's own buttons (operator 2026-10-23, mockup A)
/** After a stop is taken out of day d at j (빼기): the stops after it — the night's stay apart — move sooner as one,
 *  keeping their lengths and the legs between them, each its hours that date (holds) and a meal its side and window
 *  (plan_state.mealSlot), by as much as the leg from the stop before it then keeps its margin (marginOf) — from the
 *  reader's start and the station's margin when it was the first (bounds: boundsOf before it went) —, in steps of 5
 *  minutes, never below bounds.bottom. Returns {n: the stops moved, by: the minutes, first: the first one's name}. */
function closeGap(d, j, c, kb, bounds) {
  const tail = d.stops.slice(j).filter((s) => s.role !== "stay");
  const prev = j > 0 && d.stops[j - 1].role !== "stay" ? d.stops[j - 1] : null;
  if (!tail.length) return { n: 0, by: 0, first: "" };
  const from = prev ? hm(prev.end) + marginOf(prev.page, tail[0].page, c, kb) : bounds.bottom;
  const fits = (by) => tail.every((s) => {
    const a = hm(s.start) - by, b = hm(s.end) - by;
    return a >= bounds.bottom && holds(s, d.date, a, b, c, kb) && (s.role !== "meal" || mealSlot(a, b) === mealSlot(hm(s.start), hm(s.end)));
  });
  for (let by = Math.floor((hm(tail[0].start) - from) / 5) * 5; by > 0; by -= 5) {
    if (!fits(by)) continue;
    for (const s of tail) Object.assign(s, { start: hhmm(hm(s.start) - by), end: hhmm(hm(s.end) - by) });
    return { n: tail.length, by, first: tail[0].name };
  }
  return { n: 0, by: 0, first: "" };
}

/** A stop's own button (edit.act — 빼기 'drop', 다른 곳으로 'swap'), by the code alone (no model call): the plan on the
 *  reader's page (its stops as sent, its words as the signature proved them: edit.words — else the code's title and
 *  summary) with that stop taken out and the stops after it moved sooner (closeGap), or swapped for the nearest place
 *  of its kind that fits the same slot (swapIn: a visit the same type first, a meal a meal, a café a café; the trip's
 *  needs, that day's hours and closed days, the legs' margins, never a place in the plan) — then settled, checked and
 *  finished like any edit (conclude). kb is the site without the place taken out or swapped away and those the slot
 *  was swapped away from before (makePlan: without), so nothing in this answer puts one back. None fits a swap: the
 *  plan stays as it was, said so. Returns conclude's result with the page's lines first in plan.edited (k 'act': what
 *  the button did and every place the code then put in or took out) and act {op, day, from, to}. */
function actOn({ edit, c, kb, conclude, rec }) {
  const a = edit.act;
  const w = edit.words || {};
  const plan = { title: w.t || "", summary: w.s || "", notes: [...(w.n || [])], days: edit.plan.days.map((d) => ({ date: d.date,
    stops: d.stops.map((s) => ({ page: s.page, name: kb.docs[s.page].t, start: s.start, end: s.end, role: fitRole(s.role, kb.docs[s.page]), why: s.why })) })) };
  if (!plan.title) Object.assign(plan, codeText(plan, c, kb));
  markKept(plan, edit, kb);
  const many = plan.days.length > 1;
  const dayW = (i) => (many ? `${i + 1}일차 ` : "");
  const d = plan.days[a.day];
  const j = d.stops.findIndex((s) => s.page === a.page);
  const st = d.stops[j];
  const fixed = [];
  let head = "";
  let to = null;
  if (a.op === "drop") {
    const bounds = boundsOf(plan, a.day, c, kb);
    // (a lunch or a dinner the day needs: settle puts another restaurant in its slot, so the stops after it stay — the
    // gap closed first, the meal put back in cut the visit after it from 90 minutes to 30: review of the buttons)
    const meal = st.role === "meal" && mealNeeds(plan, c, kb, edit, a.day).includes(mealKind(hm(st.start), hm(st.end)));
    d.stops.splice(j, 1);
    const moved = meal ? { n: 0, by: 0, first: "" } : closeGap(d, j, c, kb, bounds);
    const who = moved.n === 1 ? `${moved.first}${eul(moved.first)}` : `${moved.n}곳을`;
    fixed.push(`${dayW(a.day)}${st.name}: 독자가 빼 달라고 해 일정에서 뺐습니다${moved.n ? ` — 뒤 장소 ${who} ${span(moved.by)} 당겼습니다` : ""}`);
    head = `${dayW(a.day)}${st.name}${eul(st.name)} 뺐어요`;
  } else {
    const was = { page: st.page, name: st.name };
    const said = swapIn(plan, d, j, c, kb, { why: "다른 곳으로 바꿔 달라는 요청대로" });
    if (said) {
      fixed.push(`${dayW(a.day)}${said}`);
      const now = d.stops[j];
      to = now.page;
      const ga = gOf(kb, was.page), gb = gOf(kb, now.page);
      const type = kindOf(kb.docs[now.page]) === kindOf(kb.docs[was.page]) ? kindOf(kb.docs[was.page]) : "";
      const bits = [ga && gb ? `직선 ${km(metres(ga, gb))}` : "", type ? `같은 유형 '${type}'` : ""].filter(Boolean);
      head = `${dayW(a.day)}${was.name}${eul(was.name)} 가까운 ${now.name}${bits.length ? `(${bits.join(", ")})` : ""}${ro(now.name)} 바꿨어요`;
    } else head = `${dayW(a.day)}${was.name}: 같은 시간에 맞는 비슷한 곳이 가까이에 없어요`;
  }
  const r = conclude(plan, fixed);
  rec.act = a.op;
  if (!r.plan) return r;
  // (a drop: the stops after it, when they all came sooner by the same minutes in the plan sent — a meal settle put in
  // for the one taken out may have moved them back)
  if (a.op === "drop") {
    const after = r.plan.days[a.day].stops;
    const tail = edit.plan.days[a.day].stops.slice(j + 1).filter((x) => x.role !== "stay");
    const by = tail.map((x) => { const y = after.find((s) => s.path === x.page); return y ? hm(x.start) - hm(y.start) : null; });
    if (by.length && by.every((v) => v !== null && v > 0 && v === by[0])) {
      const one = (kb.docs[tail[0].page] || {}).t || "";
      head += ` — 뒤 장소 ${tail.length === 1 ? `${one}${eul(one)}` : `${tail.length}곳을`} ${span(by[0])} 당겼어요`;
    }
  }
  // what else the code changed for it, place by place: what it put in (a meal the day needs again, a night's stay, a
  // place for a long empty stretch) and what it took out; the times that moved are the page's own lines
  const lines = [];
  r.plan.days.forEach((day, i) => {
    const sent = edit.plan.days[i].stops;
    for (const s of day.stops) {
      if (sent.some((x) => x.page === s.path) || (i === a.day && s.path === to)) continue;
      const why = s.role === "meal" ? `${(MEALS[mealKind(hm(s.start), hm(s.end))] || { label: "식사" }).label} 자리가 비어`
        : s.role === "stay" ? "묵을 곳이 빠져" : "빈 시간이 길어";
      lines.push(`${dayW(i)}${why} 사이트가 가까운 ${s.name}${eul(s.name)} ${s.start}~${s.end}에 넣었어요`);
    }
    for (const x of sent) {
      if (day.stops.some((s) => s.path === x.page) || (i === a.day && x.page === a.page)) continue;
      const name = (kb.docs[x.page] || {}).t || x.page;
      lines.push(`${dayW(i)}${name}${eul(name)} 사이트 자료에 맞추느라 뺐어요`);
    }
  });
  r.plan.edited = [{ k: "act", t: head }, ...lines.map((t) => ({ k: "act", t })), ...(r.plan.edited || [])];
  // (a course the site built itself stays one: the code made this change too — its title and summary the code's, of
  // the plan as it now is: align had cut the summary to the other day when a restaurant it named was taken out)
  if (w.code) {
    Object.assign(r.plan, codeText({ days: r.plan.days.map((d) => ({ stops: d.stops.map((s) => ({ ...s, page: s.path })) })) }, c, kb));
    r.plan.fixed = [CODE_PLAN_SHARED];
  }
  return { ...r, act: { op: a.op, day: a.day, from: a.page, to: to && r.plan.days[a.day].stops.some((s) => s.path === to) ? to : null } };
}

/** Runs one plan to the end through send(). Returns the log record's numbers. early: the plan the code built from the
 *  site's data and already sent ({type: 'early'}, the handler — a new plan only): when the model gives nothing usable
 *  (no plan, a refusal, one that settle cannot finish) the final plan is that same plan, its one line saying why — no
 *  second build, no error (operator 2026-10-19: '먼저 짠 코스'). */
export async function makePlan({ client, kb, conditions, edit = null, send, signal, now, clock = () => Date.now(), early = null }) {
  const c = conditions;
  const t0 = clock();
  // a stop's own button (edit.act): the place it takes out or swaps away, and those its slot was swapped away from
  // before, are not the site's to put in again in this answer (without)
  if (edit && edit.act) kb = without(kb, [edit.act.page, ...edit.act.tried]);
  // the places the plan had, which align reads the words against: every page of every plan the model handed over in
  // this run, and on an edit the plan the reader saw (final check 2026-10-18: a fix kept the first answer's words on
  // a lunch it no longer had)
  const seen = new Set();
  const saw = (days) => {
    for (const d of Array.isArray(days) ? days : []) {
      for (const st of Array.isArray(d && d.stops) ? d.stops : []) {
        const key = st && typeof st.page === "string" ? kb.keyFor(st.page) : "";
        if (key && kb.docs[key] && kb.docs[key].k === "place") seen.add(key);
      }
    }
  };
  if (edit) saw(edit.plan.days);
  let reads = 0;
  const rec = { rounds: 0, tools: [], submits: 0, flags: 0, text: 0, in: 0, out: 0, cache_read: 0, cache_write: 0, stop: "", status_plan: "" };
  let outUsed = 0;
  let toolChars = PLAN_LIMITS.toolChars;
  let best = null;   // the latest submit_plan with what cannot stand taken out (readSubmit salvaged), for the end
  // every plan ends here (operator 2026-10-18: '무조건 완성된 결과가 나오게'): settled until the check finds nothing
  // (settle), its words read against it again (align, trimText — a summary left empty is the code's), checked,
  // finished 'ready' — or, should anything still be flagged (preflight has shown a plan exists: never), not sent: an
  // error 'conditions' with the reasons. Returns {plan} or {error}.
  // asked: the places new to an edit, day by day, as the model handed them over (askedIn) — each must still be in the
  // plan at the end (or the place swapped in for it), else the edit fails, saying which (round-6 final verifier: a
  // café asked for on a full day was gone from a 'ready' plan, the line saying so never shown)
  const conclude = (plan, fixed, asked = null) => {
    const st = {};
    const settled = settle(plan, c, kb, edit, st);
    // the code's own plan: its one line alone (what was put right in the model's plan is of a plan not shown)
    if (st.codePlan) fixed.length = 0;
    // an edit that asks for fewer admissions: made true where the data allows, on the settled plan (fewerFees) — before
    // its words are read against it
    const fee = edit && !st.codePlan && asksFewerFees(edit.request) ? fewerFees(plan, c, kb, edit) : null;
    if (fee) rec.fee_swaps = fee.fixed.length;
    fixed.push(...settled, ...(fee ? fee.fixed : []), ...(st.codePlan ? [] : [...align(plan, c, kb, seen, { final: true }), ...staleWords(plan, c, kb)]));
    rec.settled = settled.length;
    rec.rebuilt = st.rebuilt || 0;
    if (st.codePlan) rec.code_plan = 1;
    if (!plan.summary) plan.summary = codeText(plan, c, kb).summary;
    let check = verify(plan, c, kb, edit);
    if (check.text.length) {
      trimText(plan, c, kb, check.fees);
      if (!plan.summary) plan.summary = codeText(plan, c, kb).summary;
      check = verify(plan, c, kb, edit);
    }
    rec.flags = check.flags.length;
    rec.text = check.text.length;
    fixed.splice(0, fixed.length, ...tidyFixed(fixed, plan));
    // a place the reader pinned (고정) that is not on its day, or that what is left flagged is about: the edit fails,
    // saying which and why (pinWords) — never a plan without it, never one around it that does not hold
    const pinned = edit ? pinWords(plan, check) : "";
    if (check.flags.length || pinned) {
      rec.status_plan = "unmet";
      if (pinned) rec.pin_lost = 1;
      // an edit: the reader's plan stays on the page, with the words that the change could not be made
      if (edit) return { error: { type: "error", code: "edit_failed", message: pinned || planError("edit_failed") } };
      const problems = preflight(c, kb, now);
      return { error: { type: "error", code: "conditions", message: planError("conditions"), problems: problems.length ? problems : problemsOf(check.list) } };
    }
    const lost = edit ? lostAsked(plan, asked, kb) : [];
    if (lost.length) {
      rec.status_plan = "unmet";
      rec.lost = lost.length;
      return { error: { type: "error", code: "edit_failed", message: `요청한 변경으로 넣은 ${lost.join("·")}${eul(lost.at(-1))} 그날 일정에 맞춰 둘 수 없어 `
        + "보던 일정을 그대로 두었습니다. 요청을 조금 바꿔 다시 시도해 주세요." } };
    }
    const done = finish(plan, check, c, now, fixed);
    // a rainy day's outdoor visits the reader asked for are marked (asked: true): the page sends the mark back with its
    // next edit, so a place asked for once stays through the edits after it (plan_build.rainAsked — review 2026-10-23:
    // 'OO공원 넣어 줘' then 'OO호수공원도 넣어 줘' swapped OO공원 for an indoor place)
    if (edit) plan.days.forEach((d, i) => {
      const r = rainOutdoor(d, i, c, kb, edit);
      if (r) d.stops.forEach((s, j) => { if (r.asked.includes(s)) done.days[i].stops[j].asked = true; });
    });
    // (said with what the edit changed — the page's '바꾼 뒤 달라진 것': the fees before and after, from the site's own
    // numbers, or why they stayed; a pinned place the model left out and the code put back)
    // (and the outdoor places a rainy day keeps because this edit asked for them — operator 2026-10-23)
    const rainy = edit ? rainKept(plan, c, kb, edit).filter((x) => x.now).map((x) => ({ k: "rain", t: x.t })) : [];
    const edited = [...(fee ? fewerFeesLines(edit, check.fees, fee, c, kb) : []), ...rainy,
      ...(edit && edit.back && edit.back.length ? [{ k: "pin", t: `고정한 ${edit.back.join("·")}${eun(edit.back.at(-1))} 그대로 두었어요` }] : [])];
    if (edited.length) done.edited = edited;
    rec.status_plan = done.status;
    return { plan: done };
  };
  // the reader's words for a pinned place that cannot stand in the edit (lostPins, or a flag left on it or on a leg next
  // to it): '' when every pin holds
  const pinWords = (plan, check) => {
    if (!edit.pins) return "";
    const named = lostPins(plan, edit, kb);
    for (const x of check.list) {
      const d = plan.days[x.day];
      if (!d || x.j === undefined) continue;
      for (const s of [d.stops[x.j], x.kind === "leg" ? d.stops[x.j + 1] : null]) {
        if (s && pinsOf(edit, x.day).includes(s.page) && !named.some((y) => y.i === x.day && y.page === s.page)) named.push({ i: x.day, page: s.page, name: s.name });
      }
    }
    if (!named.length) return "";
    const one = named[0];
    const date = plan.days[one.i].date;
    if (dayInfo(kb, date, one.page).state === "closed") {
      return `고정한 ${one.name}${eun(one.name)} ${closedWhy(kb, date, one.page)} 그날 일정에 둘 수 없어 보던 일정을 그대로 두었습니다. 고정을 풀고 다시 시도해 주세요.`;
    }
    const names = [...new Set(named.map((y) => y.name))];
    return `고정한 ${names.join("·")}${eul(names.at(-1))} 그날 일정에 맞춰 둘 수 없어 보던 일정을 그대로 두었습니다. 고정을 풀거나 요청을 조금 바꿔 다시 시도해 주세요.`;
  };
  // a plan the model could not fix in time: finished as it is — what readSubmit took out or changed said first, in
  // the list of what the site put right (never as flags: operator 2026-10-18) — and settled like any other
  const finishAsIs = (b) => {
    step("fees");
    const fixed = [...b.fixes, ...(b.fixed || []), ...repair(b.plan, c, kb, edit)];   // a plan repaired already keeps what was done
    fixed.push(...align(b.plan, c, kb, seen));
    rec.salvaged = 1;
    return conclude(b.plan, fixed, b.asked);
  };
  // the plan the code built first (early), as the final plan of a new plan: `line` says why the site's own plan stays
  const first = (line) => {
    rec.code_plan = 1;
    rec.early_final = 1;
    rec.status_plan = "ready";
    return { plan: codeFinal(early, line) };
  };
  const deliver = (r) => {
    // a new plan whose model plan settle could not finish (fuzz: never) ends as the course the reader already has
    if (r.error && early && !edit) r = first(CODE_PLAN_SETTLE);
    // the AI's words stand on the site's pages alone: what only the reader's note or request grounds goes (ownWords —
    // the plan is signed and passed on by a link that never carries the note)
    if (r.plan) {
      const n = ownWords(r.plan, c, kb, edit ? edit.request : "");
      if (n) rec.echo = n;
    }
    send(r.plan ? { type: "plan", plan: r.plan, ...(r.act ? { act: r.act } : {}) } : r.error, true);
    return { ...rec, status: r.plan ? "ok" : r.error.code };
  };
  const step = (key) => send({ type: "status", step: key, text: PLAN_STATUS[key] });
  // a stop's own button: the code alone, at once (actOn)
  if (edit && edit.act) {
    step("fees");
    return deliver(actOn({ edit, c, kb, conclude, rec }));
  }
  // the lines block (knowledge.js planLines): the full lines of the places that most likely fit this trip — the edit's
  // plan, the places the note names, the likings, needs, meals, cafés and stays across the 권역
  const system = buildPlanSystem(kb.catalog, now, typeof kb.planLines === "function" ? kb.planLines(c, { edit }) : "", kb.tickets);
  const convo = [{ role: "user", content: `${neutralise(conditionsText(c, edit))}\n\n${dataBlock("needs", needHints(c, kb))}\n\n`
    + `${dataBlock("closed", closedHints(c, kb))}` }];
  step("search");
  // a model call that fails once a plan is in hand (a timeout or the API in the fix round): that plan is finished, not
  // thrown away for the code's own (round-5 verifier) — unless the reader left
  try {
    for (let call = 0; call < PLAN_LIMITS.rounds; call += 1) {
      // the output budget is a ceiling (review CE08): a call asks for what is left after the share kept for the last
      // call, and the last call — forced to hand the plan over — gets that share and no more
      const left = PLAN_LIMITS.outputTokens - outUsed;
      const last = call === PLAN_LIMITS.rounds - 1 || left - PLAN_LIMITS.submitTokens < 2000;
      if (left < 1000) break;
      // the plan must come now: the last call, the reading round spent, or the time for reading gone
      const handOver = last || reads >= PLAN_LIMITS.reads || clock() - t0 > PLAN_LIMITS.readBy;
      const params = { model: MODEL, max_tokens: last ? Math.min(PLAN_LIMITS.maxTokens, left) : Math.min(PLAN_LIMITS.maxTokens, left - PLAN_LIMITS.submitTokens),
        system, tools: PLAN_TOOLS, messages: convo, thinking: { type: "disabled" }, output_config: { effort: "low" },
        tool_choice: handOver ? { type: "tool", name: "submit_plan" } : { type: "any" } };
      const stream = client.messages.stream(params, { signal, timeout: PLAN_LIMITS.callMs });
      for await (const ev of stream) {
        if (ev.type === "content_block_start" && ev.content_block?.type === "tool_use") {
          const name = ev.content_block.name;
          step(name === "search_site" ? "search" : name === "get_pages" ? "read" : rec.submits ? "fix" : "submit");
        }
      }
      const message = await stream.finalMessage();
      rec.rounds += 1;
      const u = message.usage || {};
      rec.in += u.input_tokens || 0;
      rec.out += u.output_tokens || 0;
      rec.cache_read += u.cache_read_input_tokens || 0;
      rec.cache_write += u.cache_creation_input_tokens || 0;
      rec.stop = message.stop_reason || "";
      outUsed += u.output_tokens || params.max_tokens;
      if (message.stop_reason === "refusal") {
        if (early && !edit) return { ...deliver(first(CODE_PLAN_LINE)), status: "refusal" };
        send({ type: "error", code: "refusal", message: planError("refusal") });
        return { ...rec, status: "refusal" };
      }
      const uses = (message.content || []).filter((b) => b.type === "tool_use");
      if (!uses.length) {
        // wrote text instead of handing the plan over (or ran out of tokens): asked once more
        if (message.stop_reason === "max_tokens" || (message.content || []).some((b) => b.type === "text")) {
          if (message.stop_reason !== "max_tokens") convo.push({ role: "assistant", content: message.content });
          if (message.stop_reason !== "max_tokens") convo.push({ role: "user", content: "일정은 글로 쓰지 말고 submit_plan으로 낸다." });
          continue;
        }
        break;
      }
      if (message.stop_reason === "max_tokens") continue;   // a tool input cut off: never run it
      convo.push({ role: "assistant", content: message.content });
      const results = [];
      let done = null;
      if (!uses.some((u) => u.name === "submit_plan")) reads += 1;
      for (const use of uses) {
        rec.tools.push(use.name);
        if (use.name === "submit_plan") {
          rec.submits += 1;
          saw(use.input && use.input.days);
          const { plan, errors, salvaged, fixes } = readSubmit(use.input, c, kb, edit);
          if (errors.length) {
            if (salvaged && (!best || best.fixes.length)) best = { plan: salvaged, fixes, asked: askedIn(salvaged) };   // never over a whole plan
            // no turn left for a fix (the last call, or the time for fixing gone): the plan as it is
            if (best && (last || clock() - t0 >= PLAN_LIMITS.fixBy)) {
              done = finishAsIs(best);
              break;
            }
            results.push({ type: "tool_result", tool_use_id: use.id, is_error: true,
              content: `고칠 것:\n- ${errors.join("\n- ")}\n고친 일정으로 submit_plan을 다시 부른다.` });
            continue;
          }
          step("fees");
          const asked = askedIn(plan);
          const fixed = repair(plan, c, kb, edit);
          fixed.push(...align(plan, c, kb, seen));
          rec.repaired = fixed.length;
          best = { plan, fixes: [], fixed, asked };
          const check = verify(plan, c, kb, edit);
          rec.flags = check.flags.length;
          rec.text = check.text.length;
          const wrong = [...check.flags, ...check.text];
          if (wrong.length && rec.submits < PLAN_LIMITS.submits && !last && clock() - t0 < PLAN_LIMITS.fixBy) {
            step("fix");
            results.push({ type: "tool_result", tool_use_id: use.id, is_error: true,
              content: dataBlock("check_plan", `사이트 자료로 확인하니 고칠 것 ${wrong.length}건:\n- ${wrong.join("\n- ")}\n`
                + "고쳐서 submit_plan을 다시 부른다(바꿀 필요 없는 부분은 그대로).") });
            continue;
          }
          done = conclude(plan, fixed, asked);
          break;
        }
        const input = validInput(use.name, use.input);
        if (!input) {
          results.push({ type: "tool_result", tool_use_id: use.id, is_error: true, content: "INVALID_INPUT" });
          continue;
        }
        let out;
        if (use.name === "search_site") out = kb.searchText(input.query.slice(0, QUERY_CHARS), { kind: input.kind, lang: "ko", nameLang: "ko" });
        else if (use.name === "get_pages") out = kb.pagesText(input.ids, { lang: "ko", budget: Math.max(0, toolChars) }).text;
        else out = "check_plan은 쓰지 않는다: submit_plan이 같은 검사를 한다.";
        if (out.length > toolChars) out = toolChars > 200 ? `${out.slice(0, toolChars)}\n… (읽기 한도)` : "읽기 한도를 다 썼다: 지금 아는 것으로 submit_plan을 낸다.";
        toolChars -= out.length;
        results.push({ type: "tool_result", tool_use_id: use.id, content: dataBlock(use.name, out) });
      }
      if (done) return deliver(done);
      convo.push({ role: "user", content: results });
    }
  } catch (err) {
    if (!best || (signal && signal.aborted && signal.reason !== "timeout")) throw err;
    rec.cut = signal && signal.aborted ? "timeout" : typeof err?.status === "number" ? err.status : err?.name || "error";
    return deliver(finishAsIs(best));
  }
  if (best) return deliver(finishAsIs(best));
  // an edit the model handed nothing usable for: the reader's plan stays, said so (as when the model is busy) — the
  // code cannot make the change asked for (round-5 verifier: an unrelated trip came back as the edit)
  if (edit) {
    rec.status_plan = "unmet";
    return deliver({ error: { type: "error", code: "edit_failed", message: planError("edit_failed") } });
  }
  // the model never handed over a plan that holds (operator 2026-10-17: '코스를 만들지 못했습니다'): the trip as the
  // code makes it from the site's data (plan_build.buildPlan — what preflight found), its title and summary the
  // code's, from the data alone — the one the reader already has when it was sent first (early)
  step("fees");
  if (early) return deliver(first(CODE_PLAN_LINE));
  const built = buildPlan(c, kb);
  if (built.plan) {
    rec.code_plan = 1;
    return deliver(conclude(built.plan, [CODE_PLAN_LINE]));
  }
  rec.status_plan = "unmet";
  return deliver({ error: { type: "error", code: "conditions", message: planError("conditions"), problems: preflight(c, kb, now) } });
}

/** The trip as the code makes it from the site's data alone (plan_build.buildPlan, preflight's), finished for the page:
 *  its title and summary the code's, no notes, `line` the one thing the site says it did — or null when no such plan
 *  exists (preflight refuses those conditions). */
export function codePlan(c, kb, now, line) {
  const built = buildPlan(c, kb);
  if (!built.plan) return null;
  const check = verify(built.plan, c, kb);
  return check.flags.length ? null : finish(built.plan, check, c, now, [line]);
}

// ------------------------------------------------------------------ the course sent first, a plan opened from a link
/** The one line of the course the code builds from the site's data and sends before the model's (SSE {type: 'early'},
 *  operator 2026-10-19: a new plan took 20–40 s of waiting); the page reads it as a plan the site built itself. */
export const CODE_PLAN_EARLY = "일정 전체: AI가 다듬기 전에 사이트 자료로 먼저 일정을 짰습니다";
/** The one line of a shared plan the site had built itself (a signed link with k: 1). */
export const CODE_PLAN_SHARED = "일정 전체: 사이트 자료로 일정을 짰습니다";

const daysBetween = (a, b) => (Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 86400000;

// the meals a shared plan's reader ate elsewhere (the compact form's e: what the note or an edit's request decided when
// the plan was made), said to the check as such a note would say it (plan_state.eatsElsewhere) — the view has no note
const EATS_NOTE = { "": "", l: "점심은 따로 먹어요", d: "저녁은 따로 먹어요", ld: "점심·저녁은 따로 먹어요" };

/** A role as the place is (readSubmit's rule): a stay page is the night's stay, a meal or a café only at a food page,
 *  a night's stay only at a stay page. */
function fitRole(role, doc) {
  const kind = ((doc && doc.f) || {}).kd;
  if (kind === "stay") return "stay";
  if (role === "stay") return "visit";
  if ((role === "meal" || role === "cafe") && kind !== "food") return "visit";
  return role;
}

/** A plan passed on by a link (chatbot/plan_share.js), read against today's data — no model call, no settle: the
 *  shared plan is shown as it was shared. view: the request's {compact, sig} (or {packed, sig}); key: the signature
 *  key (plan_share.shareKey) or null. The conditions are validConditions' own, a date gone by allowed up to
 *  SHARE_LIMITS.pastDays back (older: 'view_expired'); the days and stops within validEdit's bounds, every stop's times
 *  as the server writes them (HH:MM, ending after it starts, never before the stop ahead of it ends — else
 *  'bad_link'). A stop whose page the site no longer has is left out (counted, never named: a slug in a forged link is
 *  not the site's words). The words — title, summary, notes, reasons — are kept only when the signature checks out and
 *  no place was left out (a sentence may name it); else the code's title and summary from the data, written from the
 *  roles as the places are (readSubmit's rule, for a link not signed). The check knows the meals the reader ate
 *  elsewhere (the link's e, signed only — a link not signed eats nowhere else), as when the plan was made. Today's check (verify) and finish as for any plan: what it
 *  flags on a signed link is the data that changed since the plan was made — a view is not a new plan, so its status
 *  may be 'unmet' (the 'ready' contract is for the plans the server makes); on a link not signed it is what does not
 *  fit today's data, nothing more said. Malformed: HttpError 400 'bad_link'. Returns {plan, signed, words, past,
 *  during, dropped, sig} — past: the trip's last day is gone by; during: its first day is, its last not; sig: the
 *  returned plan's own signature when its words are the server's (so it can be passed on), else null. */
export function viewPlan(view, kb, now, key) {
  const { compact, sig } = readView(view);
  const signed = sigValid(compact, sig, key);
  const today = seoulNow(now).date;
  const raw = conditionsOf(compact);
  const date = typeof raw.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw.date) && !Number.isNaN(Date.parse(`${raw.date}T12:00:00Z`)) ? raw.date : null;
  if (!date) throw new HttpError(400, "bad_link");
  const back = daysBetween(date, today);
  if (back > SHARE_LIMITS.pastDays) throw new HttpError(400, "view_expired");
  let c;
  try {
    // a date gone by is read as of that date: validConditions keeps a new plan's dates from today on
    c = validConditions(raw, back > 0 ? new Date(`${date}T03:00:00Z`) : now);
  } catch {
    throw new HttpError(400, "bad_link");
  }
  if (compact.d.length !== c.days || compact.d.some((d) => !d.length || d.length > PLAN_LIMITS.stopsPerDay)) throw new HttpError(400, "bad_link");
  const dates = tripDates(c.date, c.days);
  let dropped = 0;
  const days = compact.d.map((day, i) => {
    let prev = null;
    const stops = [];
    for (const [path, start, end, role, why] of day) {
      const a = mins(start), b = mins(end);
      if (a === null || b === null || b <= a || (prev !== null && a < prev)) throw new HttpError(400, "bad_link");
      prev = b;
      const k = kb.keyFor(path);
      const doc = k ? kb.docs[k] : null;
      if (!doc || doc.k !== "place") {
        dropped += 1;
        continue;
      }
      stops.push({ page: k, name: doc.t, start, end, role: signed ? role : fitRole(role, doc), why });
    }
    return { date: dates[i], stops };
  });
  // a day none of whose places the site has any more: nothing to show for it
  if (days.some((d) => !d.stops.length)) throw new HttpError(400, "view_gone");
  const words = signed && !dropped;
  const plan = { title: words ? compact.t : "", summary: words ? compact.s : "", notes: words ? compact.n.filter(Boolean) : [],
    days: days.map((d) => ({ ...d, stops: d.stops.map((x) => ({ ...x, why: words ? x.why : "" })) })) };
  const code = codeText(plan, c, kb);
  if (!plan.title) plan.title = code.title;
  if (!plan.summary) plan.summary = code.summary;
  // the meals eaten elsewhere are a decision the server signed: a link not signed is read as saying none (round-6
  // final verifier: a forged link with no lunch and e 'l' showed '오늘 자료로도 맞는 코스예요')
  const cv = { ...c, note: (signed && EATS_NOTE[compact.e]) || "" };
  stayEnds(plan, cv, kb);
  // a signed link's rainy day with more than one outdoor visit: only the places a reader asked for in an edit keep more
  // than one (plan_build.rainAsked reads this plan as the page before an edit) — not said to be data that changed
  // (review 2026-10-23: such a plan opened as '공유된 뒤 자료가 바뀐 곳이 있어요'); a link not signed is checked as it is
  const check = verify(plan, cv, kb, signed ? { plan } : null);
  const out = finish(plan, check, c, now, signed && compact.k ? [CODE_PLAN_SHARED] : []);
  const ended = daysBetween(dates.at(-1), today) > 0;
  return { plan: out, signed, words, past: ended, during: back > 0 && !ended, dropped, sig: words ? signPlan(out, key) : null };
}

// ------------------------------------------------------------------ the reader's own text in the AI's words
const ECHO_RUN = 10;   // characters (no spaces or punctuation; a place's name counted as one) copied from the reader
// the text as compared: one Unicode form (NFKC — a note pasted from macOS comes decomposed, a phone may type full-width
// digits), with no space, punctuation, symbol or invisible character of any kind, nor the Korean middle dot 'ㆍ' (a
// letter, U+318D — NFKC makes it U+119E) — round-6 final verifier: runs joined by 'ㆍ', '…' or '。', and a decomposed
// note, were not caught
const squash = (t) => String(t || "").normalize("NFKC").replace(/[\s\p{P}\p{S}\p{Z}\p{C}ㆍᆞ]/gu, "");
/** Whether `text` copies a run of ECHO_RUN characters from `reader` (spaces and punctuation left out, each of `names`
 *  — longest first — read as one character, so a long place name both say is not a copy). */
export function echoes(text, reader, names = []) {
  if (!text || !reader) return false;
  const keys = names.map(squash).filter(Boolean);
  const mask = (t) => keys.reduce((x, n) => x.split(n).join("\u0002"), squash(t));
  const a = mask(text), b = mask(reader);
  for (let i = 0; i + ECHO_RUN <= a.length; i += 1) if (b.includes(a.slice(i, i + ECHO_RUN))) return true;
  return false;
}

/** The AI's words of a finished plan read once more against the site's pages alone — without the reader's note and an
 *  edit's request (round-6 verifier: textIssues counts the note's numbers as grounded, so a phone number the reader
 *  wrote came back in a reason, and a link — signed, without the note — showed it as the site's checked words). A
 *  reason, a sentence of the summary or a note, or the title that has a number (100 and up) only the reader's text has,
 *  or that copies ECHO_RUN characters of it (echoes), goes: the reason left empty, the sentence left out, the title the
 *  code's; a summary left empty is the code's. A plan the site built itself has no words of the AI's. Changes the plan
 *  in place, says so in its 'fixed' list; returns how many went. */
export function ownWords(plan, c, kb, request = "") {
  const reader = [c.note, request].filter(Boolean).join("\n");
  if (!reader || codeBuilt(plan)) return 0;
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const stops = plan.days.flatMap((d) => d.stops);
  const site = [c.date, c.start, c.end, String(c.budget ?? ""), ...stops.flatMap((s) => [s.start, s.end]),
    String((plan.fees || {}).known ?? ""), String((plan.fees || {}).total ?? "")].join(" ");
  const all = `${stops.map((s) => own(s.path)).join("\n")}\n${site}`;
  const keys = new Set(stops.map((s) => s.path));
  const names = [...new Set([...stops.map((s) => s.name), ...kb.placeNames.filter(([, k]) => keys.has(k)).map(([n]) => n)])]
    .filter(Boolean).sort((a, b) => b.length - a.length);
  const theirs = (t, src) => grounded(t, src).bad.length > 0 || echoes(t, reader, names);
  let n = 0;
  for (const s of stops) {
    if (s.why && theirs(s.why, `${own(s.path)}\n${site}`)) {
      s.why = "";
      n += 1;
    }
  }
  const keep = (x) => {
    if (!theirs(x, all)) return true;
    n += 1;
    return false;
  };
  plan.summary = dropSentences(plan.summary, keep);
  plan.notes = (plan.notes || []).map((x) => dropSentences(x, keep)).filter(Boolean);
  const code = () => codeText({ days: plan.days.map((d) => ({ stops: d.stops.map((s) => ({ ...s, page: s.path })) })) }, c, kb);
  if (theirs(plan.title, all)) {
    plan.title = code().title;
    n += 1;
  }
  if (!plan.summary) plan.summary = code().summary;
  if (n) {
    const what = [c.note && "하고 싶은 말", request && "바꿔 달라는 말"].filter(Boolean).join("·");
    plan.fixed = [...(plan.fixed || []), `AI 설명: ${what}에만 있는 숫자나 그 말을 그대로 옮긴 문장 ${n}개를 뺐습니다`];
  }
  return n;
}

// ------------------------------------------------------------------ the handler
export function createPlanHandler(deps = {}) {
  const env = deps.env ?? process.env;
  const now = deps.now ?? (() => new Date());
  const log = deps.log ?? ((rec) => console.log(JSON.stringify(rec)));
  const limiter = deps.limiter ?? createLimiter(PLAN_LIMITS.perMinute, 60000,
    { perDay: PLAN_LIMITS.perDay, allPerMinute: PLAN_LIMITS.allPerMinute, allPerDay: PLAN_LIMITS.allPerDay });
  // the conditions refused at the button: free of the plan's quota, counted in a looser one of their own (round-5
  // verifier: a refusal's reasons cost up to a second of the server's time)
  const refusals = deps.refusals ?? createLimiter(PLAN_LIMITS.refusedPerMinute, 60000,
    { perDay: PLAN_LIMITS.refusedPerDay, allPerMinute: PLAN_LIMITS.refusedAllPerMinute, allPerDay: PLAN_LIMITS.refusedAllPerDay });
  // shared plans opened (no model call): a limiter of their own, never the plan's quota
  const views = deps.views ?? createLimiter(SHARE_LIMITS.perMinute, 60000,
    { perDay: SHARE_LIMITS.perDay, allPerMinute: SHARE_LIMITS.allPerMinute, allPerDay: SHARE_LIMITS.allPerDay });
  // the key of the plans' signatures (plan_share.shareKey): kept here, never logged nor sent
  const sharing = deps.shareKey !== undefined ? deps.shareKey : shareKey(env);
  // a PLAN_SHARE_SECRET too short to use (plan_share.SECRET_MIN): said once, as the function starts — never its value;
  // the key is the one derived from the API key meanwhile
  if (deps.shareKey === undefined && secretShort(env)) log({ evt: "plan", status: "share_secret_short", min: SECRET_MIN });
  const knowledge = deps.knowledge ?? defaultKnowledge;
  let client = deps.client ?? null;

  async function getClient() {
    if (!client) {
      const { default: Anthropic } = await import("@anthropic-ai/sdk");
      client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: PLAN_LIMITS.callMs });
    }
    return client;
  }

  // POST {view: {compact, sig}}: a plan from a link, checked against today's data (viewPlan) — JSON, not a stream
  async function view(v, key, done) {
    const viewError = (status, code, extra = {}) => json(status, { code, message: VIEW_ERRORS[code] || VIEW_ERRORS.busy }, extra);
    const gate = views.take(key, now().getTime());
    if (!gate.ok) {
      done("view_limited", { limit: gate.limit });
      return viewError(429, limitCode(gate.limit), { "Retry-After": String(gate.retry) });
    }
    let kb;
    try {
      kb = await knowledge();
    } catch (err) {
      done("view_unavailable", { reason: err?.code || err?.name || "load" });
      return viewError(503, "busy");
    }
    try {
      const r = viewPlan(v, kb, now(), sharing);
      done("view", { signed: r.signed ? 1 : 0, past: r.past ? 1 : 0, during: r.during ? 1 : undefined, dropped: r.dropped || undefined,
        flags: r.plan.flags.length, days: r.plan.days.length });
      return json(200, { type: "view", plan: r.plan, sig: r.sig, signed: r.signed, words: r.words, past: r.past, during: r.during, dropped: r.dropped });
    } catch (err) {
      if (err instanceof HttpError) {
        done(err.code);
        return viewError(err.status, err.code);
      }
      done("view_exception", { reason: err?.name || "error" });
      return viewError(500, "busy");
    }
  }

  return async function handle(request) {
    const t0 = Date.now();
    const done = (status, extra = {}) => log({ evt: "plan", status, ms: Date.now() - t0, ...extra });
    const fail = (status, code) => json(status, { code, message: planError(code) });
    if (request.method !== "POST") {
      done("method");
      return json(405, { code: "method_not_allowed" }, { Allow: "POST" });
    }
    // the knowledge first: its meta is the origin allow-list and the city's hubs and likes (city.js — one load per
    // instance), which the conditions are read against
    let kb;
    try {
      kb = await knowledge();
    } catch (err) {
      done("unavailable", { reason: err?.code || err?.name || "load" });
      return fail(503, "busy");
    }
    if (!originAllowed(request, env, kb.meta)) {
      done("forbidden_origin");
      return json(403, { code: "forbidden_origin" });
    }
    const key = clientKey(clientIp(request));
    // the body first (at most PLAN_LIMITS.bodyBytes): a view goes its own way — no key, no plan quota
    let body;
    try {
      body = await readBody(request, PLAN_LIMITS.bodyBytes);
      if (!body || typeof body !== "object" || Array.isArray(body)) throw new HttpError(400, "bad_request");
    } catch (err) {
      const e = err instanceof HttpError ? err : new HttpError(400, "bad_request");
      done(e.code);
      return fail(e.status, e.code);
    }
    if (body.view !== undefined) return view(body.view, key, done);
    if (!deps.client && !env.ANTHROPIC_API_KEY) {
      done("not_configured");
      return fail(503, "not_configured");
    }
    const refuse = (gate) => {
      done("rate_limited", { limit: gate.limit });
      const code = limitCode(gate.limit);
      return json(429, { code, message: planError(code) }, { "Retry-After": String(gate.retry) });
    };
    // a stop's own button (body.act: 빼기, 다른 곳으로) is the code's alone, no model call: counted with the views (no
    // model call either), never in the plan's quota
    const quota = body.act !== undefined ? views : limiter;
    let gate = quota.check(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let conditions;
    let edit;
    try {
      conditions = validConditions(body.conditions, now());
      edit = validEdit(body.plan, body.request, conditions, { act: body.act, pins: body.pins });
      // an edit's reasons come from the page: kept only with the signature of the plan they were written for
      // (plan_share.baseValid: body.base, the plan on screen's compact form without its stops, and its signature) —
      // else dropped before the model reads them, so the server never signs a reason a reader wrote (round-6
      // verifier: one edit with a made-up plan had its sentences copied by the model and signed). No key, no
      // signature: the reasons stay.
      const proven = !!edit && (!sharing || baseValid(body.base, conditions, edit.plan.days, sharing));
      if (edit && !proven) {
        // (an act is made on the plan the server signed or on none: the page always sends it with its base)
        if (edit.act) throw new HttpError(400, "bad_request");
        edit.unproven = 1;
        for (const d of edit.plan.days) for (const st of d.stops) st.why = "";
      }
      // an act keeps the plan's own words (it makes no new ones): the title, the summary and the notes the signature
      // proved, and whether the site built that plan itself (k)
      if (edit && edit.act && body.base && typeof body.base === "object") {
        const b = body.base;
        edit.words = { t: str(b.t, 60), s: str(b.s, 300), n: (Array.isArray(b.n) ? b.n : []).map((x) => str(x, 160)).filter(Boolean).slice(0, 3), code: b.k === 1 };
      }
      // the meals the plan on screen was made without (its link's e: what the owner's note or an earlier request
      // decided — a link's reader has neither): read by the meal rules as the note would be (plan_state.eatsWords),
      // never by the model nor ownWords — round-6 verifier: a link's reader who asked for a café got the dinner the
      // owner had said to leave out. Only with the plan's signature checked — not on a server with no key, where
      // nothing is signed and so nothing proves it (round-6 final verifier).
      if (edit && sharing && proven && body.base && typeof body.base === "object" && Object.hasOwn(EATS_NOTE, body.base.e) && body.base.e) {
        edit.eats = EATS_NOTE[body.base.e];
      }
    } catch (err) {
      const e = err instanceof HttpError ? err : new HttpError(400, "bad_request");
      done(e.code);
      return fail(e.status, e.code);
    }
    // an edit's pages: only the site's own reach the prompt (editPlaces)
    if (edit) {
      try {
        edit.gone = editPlaces(edit, kb);
      } catch (err) {
        const e = err instanceof HttpError ? err : new HttpError(400, "bad_request");
        done(e.code);
        return fail(e.status, e.code);
      }
    }
    // conditions no plan can meet are said at the button, before the quota and any model call (operator 2026-10-18:
    // '문제가 있으면 아예 생성 버튼 누르는 단계에서 지적을 하고'): the reasons and the changes that make a plan. Not for
    // an edit: the plan on the page was made for these conditions, and a change that cannot be settled keeps it, said
    // so (makePlan 'edit_failed') — the button never refuses a change for the plan it changes (round-5 verifier: 7%
    // of the edits of sent plans were refused, with a date to change that an edit cannot change)
    if (!edit) {
      const pre = refusals.check(key, now().getTime());
      if (!pre.ok) return refuse(pre);
      let problems = [];
      try {
        problems = preflight(conditions, kb, now(), null, { today: seoulNow(now()).date, daysAhead: PLAN_LIMITS.daysAhead, valid: (x) => validConditions(x, now()) });
      } catch (err) {
        log({ evt: "plan", status: "preflight_error", reason: err?.name || "error" });   // the model path still runs
      }
      if (problems.length) {
        refusals.take(key, now().getTime());
        done("conditions", { problems: problems.length, fields: [...new Set(problems.map((p) => p.field))] });
        return json(422, { code: "conditions", message: planError("conditions"), problems });
      }
    }
    gate = quota.take(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let api = null;
    try {
      if (!edit || !edit.act) api = await getClient();
    } catch (err) {
      done("unavailable", { reason: err?.code || err?.name || "load" });
      return fail(503, "busy");
    }
    const ac = new AbortController();
    let timedOut = false;
    // the reason rides on the signal: makePlan finishes the plan it has on a timeout, never for a reader who left
    const timer = setTimeout(() => {
      timedOut = true;
      ac.abort("timeout");
    }, PLAN_LIMITS.requestMs);
    const stop = () => ac.abort("client");
    request.signal?.addEventListener("abort", stop);
    const enc = new TextEncoder();
    let open = true;
    const body$ = new ReadableStream({
      async start(controller) {
        // after the time is up only the end may go out: an error, or the plan (`final`: makePlan's last event)
        let last = false;
        // every plan the server makes goes with its signature (plan_share.signPlan) when there is a key: the page
        // puts it in the plan's share link, so the words of the plan are known to be the site's when it is opened
        const sign = (plan) => {
          try {
            return signPlan(plan, sharing);
          } catch {
            // a plan outside the link's bounds (plan_share.normalize — readSubmit's own, so not one the server makes
            // today) cannot be signed, and its link would not open (400 'bad_link'): it goes unsigned — never unsent
            return null;
          }
        };
        const send = (ev, final = false) => {
          if (!open || (ac.signal.aborted && ev.type !== "error" && !last && !final)) return;
          const sig = (ev.type === "plan" || ev.type === "early") && sharing ? sign(ev.plan) : null;
          controller.enqueue(enc.encode(`data: ${JSON.stringify(sig ? { ...ev, sig } : ev)}\n\n`));
        };
        // a new plan: the course the code builds from the site's data (the one preflight has just found), finished
        // like any other and sent at once (operator 2026-10-19: 20–40 s of waiting for the first course) — the model's
        // plan replaces it at the end; should the model give nothing, that same course is the final plan
        let early = null;
        if (!edit) {
          try {
            early = codePlan(conditions, kb, now(), CODE_PLAN_EARLY);
          } catch (err) {
            log({ evt: "plan", status: "early_error", reason: err?.name || "error" });
          }
          if (early) send({ type: "early", plan: early });
        }
        try {
          const rec = await makePlan({ client: api, kb, conditions, edit, send, signal: ac.signal, now: now(), early });
          done(rec.status, { rounds: rec.rounds, tools: rec.tools, submits: rec.submits, flags: rec.flags, text: rec.text,
            plan: rec.status_plan || undefined, salvaged: rec.salvaged || undefined, repaired: rec.repaired || undefined, settled: rec.settled || undefined,
            rebuilt: rec.rebuilt || undefined, code_plan: rec.code_plan || undefined, cut: rec.cut || undefined, in: rec.in, out: rec.out, cache_read: rec.cache_read,
            cache_write: rec.cache_write, stop: rec.stop, edit: !!edit, days: conditions.days, early: early ? 1 : undefined, early_final: rec.early_final || undefined,
            echo: rec.echo || undefined, unproven: edit && edit.unproven ? 1 : undefined, gone: edit && edit.gone ? edit.gone : undefined,
            fee_swaps: rec.fee_swaps, act: rec.act, pins: edit && edit.pins ? edit.pins.flat().length : undefined, pin_lost: rec.pin_lost });
        } catch (err) {
          const status = typeof err?.status === "number" ? err.status : 0;
          // the API's own errors (the SDK's: a status, or a connection that failed) apart from the code's
          const api = !!status || /^(?:APIConnection|APIUserAbort|APIConnectionTimeout|Anthropic|APIError)/u.test(err?.name || "") || err?.name === "AbortError";
          let code = "error";
          if (timedOut) code = "timeout";
          else if (ac.signal.aborted) code = "client_gone";
          else if (status === 429 || status === 529 || status >= 500 || (api && !status)) code = "busy";
          else if (!api) code = "exception";
          // the model did not answer in time or is busy for a while (timeout, 429, 529, 5xx, a connection that
          // failed): a new plan is still finished — the code's own, from the site's data (operator 2026-10-18: '무조건
          // 완성된 결과가 나오게'), the course sent first when there was one (no second build). Not for a fault that
          // stays (400, 401, 403, 404: a key or a request the API refuses) nor one of the code's own: those show, so
          // they are fixed (round-5 verifier) — the page keeps the course it was sent first. An edit keeps the error:
          // the code cannot make the change asked for.
          const own = (code === "timeout" || code === "busy") && !edit
            ? (early ? codeFinal(early, CODE_PLAN_BUSY) : codePlan(conditions, kb, now(), CODE_PLAN_BUSY)) : null;
          last = true;
          if (own) send({ type: "plan", plan: own });
          else if (code !== "client_gone") send({ type: "error", code, message: planError(code) });
          done(code, { api_status: status || undefined, ...(code === "exception" ? { reason: err?.name || "error" } : {}),
            ...(own ? { plan: own.status, code_plan: 1 } : {}), early: early ? 1 : undefined, early_final: own && early ? 1 : undefined });
        } finally {
          clearTimeout(timer);
          request.signal?.removeEventListener("abort", stop);
          if (open) {
            open = false;
            controller.close();
          }
        }
      },
      cancel() {
        open = false;
        ac.abort();
      },
    });
    return new Response(body$, { status: 200, headers: SSE_HEADERS });
  };
}
