// POST /api/plan/ → text/event-stream: the AI course planner (the first city's operator 2026-10-17: 'AI 여행 코스
// 생성기', its own page /plan/, Korean only). The reader picks conditions (dates, hours, how they move, who comes, likes, needs, a fee
// budget); the model reads the site's catalog and pages and hands the plan over with submit_plan; the code then checks
// every day against the data (knowledge.js checkPlan: closed days, notices, hours, last entry, legs with no time left)
// and the conditions (the day's hours, a stay each night, the fee budget), adds the fees up once (feeTotal), and sends
// back what is wrong for one fix. The page draws the plan from the site's own place data (/plan/places.json): the
// model's words are only the title, the summary, a reason per stop and the notes.
//
// SSE events: {type:'status', step, text} while it works · {type:'plan', plan} at the end · {type:'error', code,
// message}. Logs: one JSON line per request with numbers only (rounds, tools, submits, flags, tokens) — never the
// reader's words or the plan. The same request checks as the assistant (chatbot/server.js): POST, the knowledge (its
// meta is the origin allow-list and the city's hubs and likes), an allowed Origin, a key, a rate limit of its own (a
// plan costs several calls), a small body that parses, then the conditions. Nothing of a city is written here: the
// region's name, the hubs and the likes are docs.json meta (knowledge.js readMeta), the tickets docs.json tickets.
import { QUERY_CHARS, defaultKnowledge } from "./knowledge.js";
import { planFees } from "./plan_fees.js";
import { MOVE, NEEDS, PLAN_STATUS, PLAN_TOOLS, WITH, buildPlanSystem, conditionsText, tripDates } from "./plan_prompt.js";
import { HARD_NEEDS, checksList, dropSentences, grounded, needAt, needMisses, needsTable, statusOf } from "./plan_state.js";
import { MODEL, dataBlock, neutralise, seoulNow } from "./prompt.js";
import {
  HttpError, SSE_HEADERS, clientIp, clientKey, createLimiter, json, limitCode, originAllowed, readBody, validInput,
} from "./server.js";

export const PLAN_LIMITS = {
  bodyBytes: 16 * 1024,
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
  stopsPerDay: 10,
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
  no_fit: "고른 조건에 모두 맞는 장소가 너무 적어 코스를 만들 수 없어요. 조건을 하나 줄여 주세요.",
  error: "코스를 만들지 못했습니다. 다시 시도해 주세요.",
};
export const planError = (code) => ERRORS[code] || ERRORS.error;

const HM = /^([01]\d|2[0-3]):([0-5]\d)$/;
const mins = (t) => {
  const m = HM.exec(t || "");
  return m ? +m[1] * 60 + +m[2] : null;
};
const str = (v, max) => (typeof v === "string" ? v.replace(/\s+/g, " ").trim().slice(0, max) : "");
const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const set = (v, keys, max) => Array.isArray(v) && v.length <= max && v.every((x) => keys.includes(x)) && new Set(v).size === v.length;

/** The reader's conditions, checked (every field from a fixed list or a bounded number; the hubs and the likes from the
 *  city's own lists — plan = meta.plan {hubs, prefs}; the note is text, cut and neutralised where it reaches the
 *  model). Throws HttpError 400 otherwise; a date in the past or too far: bad_date. */
export function validConditions(c, now, plan = {}) {
  const HUBS = (plan && plan.hubs) || {};
  const PREFS = (plan && plan.prefs) || {};
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
    && (c.from === undefined || c.from === "" || Object.hasOwn(HUBS, c.from))
    && (c.to === undefined || c.to === "" || Object.hasOwn(HUBS, c.to))
    && set(c.prefs ?? [], Object.keys(PREFS), 4) && set(c.needs ?? [], Object.keys(NEEDS), 6)
    && (c.budget === null || c.budget === undefined || isInt(c.budget, 0, 1000000))
    && (c.note === undefined || (typeof c.note === "string" && [...c.note].length <= PLAN_LIMITS.noteChars));
  if (!ok) throw new HttpError(400, "bad_request");
  return { date: c.date, days: c.days, start: c.start, end: c.end, move: c.move, with: c.with, adults: c.adults,
    seniors: c.seniors || 0, kids: [...c.kids], from: c.from || "", to: c.to || "", prefs: [...(c.prefs || [])],
    needs: [...(c.needs || [])], budget: c.budget ?? null, note: str(c.note, PLAN_LIMITS.noteChars) };
}

/** An edit: the plan the page shows (pages and times only) and the change the reader asks for. */
export function validEdit(plan, request, c) {
  if (plan === undefined && request === undefined) return null;
  if (!plan || typeof plan !== "object" || !Array.isArray(plan.days) || plan.days.length !== c.days) throw new HttpError(400, "bad_request");
  if (typeof request !== "string" || !request.trim() || [...request].length > PLAN_LIMITS.requestChars) throw new HttpError(400, "bad_request");
  const dates = tripDates(c.date, c.days);
  const days = plan.days.map((d, i) => {
    if (!d || d.date !== dates[i] || !Array.isArray(d.stops) || d.stops.length > PLAN_LIMITS.stopsPerDay) throw new HttpError(400, "bad_request");
    return { date: d.date, stops: d.stops.map((s) => {
      if (!s || typeof s.page !== "string" || s.page.length > 300 || mins(s.start) === null || mins(s.end) === null) throw new HttpError(400, "bad_request");
      // the role and the reason ride along, so the stops an edit keeps are copied, not read and written again
      return { page: s.page, start: s.start, end: s.end, role: ["visit", "meal", "cafe", "stay"].includes(s.role) ? s.role : "visit",
        why: str(s.why, 120) };
    }) };
  });
  return { plan: { days }, request: str(request, PLAN_LIMITS.requestChars) };
}

const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
const STAY_AFTER = 30;   // minutes between the day's last stop and the night's stay when the model's stay starts earlier

/** submit_plan's input checked against the conditions and the site: {plan, errors, salvaged, fixes} — errors (Korean,
 *  for the model) when a day, a page, a time or a field is not what it must be; the plan is trimmed to its bounds.
 *  salvaged: the same plan with what cannot stand taken out (a page the site lacks, times that are not times, more
 *  stops than a day holds) and every role made what the place is — finished as it is when the model has no turn left
 *  to fix it (a 1박 2일 plan sent back three times was thrown away whole: operator 2026-10-17, '코스를 만들지
 *  못했습니다'); fixes says, for the reader, what was taken out or changed. null when a day would have no stop.
 *  A night's stay is where the day ends: one that starts before the stop ahead of it is over (the page's check-in
 *  time, a review rule) starts after it, and an end before its start or past midnight is the start plus an hour. */
export function readSubmit(input, c, kb) {
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
    const stops = Array.isArray(d && d.stops) ? d.stops : [];
    if (!stops.length) errors.push(`${i + 1}일차에 장소가 없다`);
    if (stops.length > PLAN_LIMITS.stopsPerDay) {
      errors.push(`${i + 1}일차 장소는 ${PLAN_LIMITS.stopsPerDay}곳까지`);
      fixes.push(`${i + 1}일차: 하루 ${PLAN_LIMITS.stopsPerDay}곳을 넘는 장소를 뺐다`);
    }
    const out = [];
    const kept = [];
    let prevEnd = null;
    stops.slice(0, PLAN_LIMITS.stopsPerDay).forEach((s, j) => {
      const where = `${i + 1}일차 ${j + 1}번`;
      const key = s && typeof s.page === "string" ? kb.keyFor(s.page) : "";
      const doc = key ? kb.docs[key] : null;
      if (!doc || doc.k !== "place") {
        errors.push(`${where}: '${str(s && s.page, 80)}'은 이 사이트의 장소 페이지가 아니다 — 카탈로그의 P 줄 경로를 쓴다`);
        fixes.push(`${i + 1}일차: 이 사이트에 장소 페이지가 없는 곳 하나를 뺐다`);
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
        fixes.push(`${i + 1}일차 ${doc.t}: 시각이 올바르지 않아 뺐다`);
        return;
      }
      if (prevEnd !== null && a < prevEnd) errors.push(`${where} ${doc.t}: 앞 장소가 끝나기 전에 시작한다`);
      prevEnd = b;
      // a role is what the place is (review CE05: a park handed over as the night's stay passed)
      let fit = role;
      if (role === "stay" && kind !== "stay") {
        errors.push(`${where} ${doc.t}: role stay인데 숙소 페이지가 아니다 — 카탈로그의 숙소를 쓴다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 숙소가 아니라서 묵는 곳이 아닌 방문지로 두었다`);
        fit = "visit";
      }
      if ((role === "meal" || role === "cafe") && kind !== "food") {
        errors.push(`${where} ${doc.t}: role ${role}인데 음식점 페이지가 아니다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 음식점 페이지가 아니라서 ${role === "meal" ? "식사" : "카페"}가 아닌 방문지로 두었다`);
        fit = "visit";
      }
      if (role === "visit" && kind === "stay") {
        errors.push(`${where} ${doc.t}: 숙소는 role stay로만 넣는다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 숙소라서 묵는 곳으로 두었다`);
        fit = "stay";
      }
      const stop = { page: key, name: doc.t, start, end, role, why: str(s.why, 120) };
      out.push(stop);
      kept.push({ ...stop, role: fit });
    });
    plan.days.push({ date: dates[i], stops: out });
    safe.push({ date: dates[i], stops: kept });
  });
  const whole = safe.length === c.days && safe.every((d) => d.stops.length);
  const region = ((kb.meta && kb.meta.region) || {}).ko || "";
  const salvaged = whole ? { ...plan, title: plan.title || `${region ? `${region} ` : ""}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`,
    days: safe } : null;
  return { plan, errors, salvaged, fixes };
}

/** The straight-line distance in metres between two [lat, lng] points (knowledge.js checkPlan's formula). */
function metres(a, b) {
  const rad = (x) => (x * Math.PI) / 180;
  const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
}

/** Where the trip starts and ends when the reader named a station or a terminal: [{dir, name, stop, gap, url, m?}] —
 *  gap = minutes between the hub's time (the first day's start, the last day's end) and the first or last stop. A hub
 *  the city lists by name only (meta.plan.hubs without a point) has no point on the site: its leg is a directions
 *  link by names; a hub that is a place of the site (its point g) gets the straight-line distance m and a directions
 *  link between the two points, as a leg between two stops does. hubs = meta.plan.hubs; kb gives the stops' points. */
export function hubLegs(plan, c, hubs = {}, kb = null) {
  const out = [];
  const q = encodeURIComponent;
  const first = (plan.days[0] || { stops: [] }).stops[0];
  const lastDay = plan.days[plan.days.length - 1] || { stops: [] };
  const last = [...lastDay.stops].reverse().find((s) => s.role !== "stay");
  const point = (s) => (kb && ((kb.docs[s.page] || {}).f || {}).g) || null;
  const leg = (dir, hub, s) => {
    const a = hub.g || null;
    const b = point(s);
    if (a && b) {
      const m = metres(a, b);
      const [x, y] = dir === "from" ? [{ name: hub.name, lat: a[0], lng: a[1] }, { name: s.name, lat: b[0], lng: b[1] }]
        : [{ name: s.name, lat: b[0], lng: b[1] }, { name: hub.name, lat: a[0], lng: a[1] }];
      return { m, url: directionsUrl(x, y, c.move, m).url };
    }
    return { url: dir === "from" ? `https://map.kakao.com/?sName=${q(hub.name)}&eName=${q(s.name)}`
      : `https://map.kakao.com/?sName=${q(s.name)}&eName=${q(hub.name)}` };
  };
  if (c.from && hubs[c.from] && first) {
    out.push({ dir: "from", name: hubs[c.from].name, stop: first.name, at: c.start, gap: mins(first.start) - mins(c.start),
      ...leg("from", hubs[c.from], first) });
  }
  if (c.to && hubs[c.to] && last) {
    out.push({ dir: "to", name: hubs[c.to].name, stop: last.name, at: c.end, gap: mins(c.end) - mins(last.end),
      ...leg("to", hubs[c.to], last) });
  }
  return out;
}

/** The model's sentences read against the pages: numbers the pages do not have, words that claim a check. Returns
 *  errors (Korean, for the model). */
export function textIssues(plan, c, kb, fees) {
  const errors = [];
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const plain = [c.date, c.start, c.end, String(c.budget ?? ""), c.note, ...plan.days.flatMap((d) => d.stops.flatMap((s) => [s.start, s.end])),
    String(fees.known), String(fees.total ?? "")].join(" ");
  const all = `${plan.days.flatMap((d) => d.stops.map((s) => own(s.page))).join("\n")}\n${plain}`;
  plan.days.forEach((d, i) => d.stops.forEach((s, j) => {
    const g = grounded(s.why, `${own(s.page)}\n${plain}`);
    if (g.bad.length) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why의 숫자 ${g.bad.join("·")}가 그 장소 페이지에 없다 — 페이지에 있는 사실만 쓴다`);
    if (g.claim) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why: '확인됐다·보장·문제없다'는 말은 쓰지 않는다(확인 상태는 사이트가 보여 준다)`);
  }));
  for (const [what, text] of [["summary", plan.summary], ...plan.notes.map((n, k) => [`notes ${k + 1}`, n])]) {
    const g = grounded(text, all);
    if (g.bad.length) errors.push(`${what}의 숫자 ${g.bad.join("·")}가 일정의 장소 페이지에 없다 — 요금·합계·연도·거리는 쓰지 않는다(사이트가 계산해 보여 준다)`);
    if (g.claim) errors.push(`${what}: '확인됐다·보장·문제없다·모두 가능'은 쓰지 않는다 — 확인 상태는 사이트가 따로 보여 준다`);
  }
  return errors;
}

/** The last word on the model's sentences after its one fix: a reason, a note or a summary sentence that still has a
 *  number the pages lack or claims a check is left out. */
export function trimText(plan, c, kb, fees) {
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const plain = [c.date, c.start, c.end, String(c.budget ?? ""), c.note, ...plan.days.flatMap((d) => d.stops.flatMap((s) => [s.start, s.end])),
    String(fees.known), String(fees.total ?? "")].join(" ");
  const all = `${plan.days.flatMap((d) => d.stops.map((s) => own(s.page))).join("\n")}\n${plain}`;
  const ok = (text, src) => { const g = grounded(text, src); return !g.bad.length && !g.claim; };
  for (const d of plan.days) for (const s of d.stops) if (!ok(s.why, `${own(s.page)}\n${plain}`)) s.why = "";
  plan.summary = dropSentences(plan.summary, (x) => ok(x, all));
  plan.notes = plan.notes.filter((n) => ok(n, all));
  return plan;
}

/** The plan read against the data and the conditions: each day's checkPlan, the day's hours the reader set, a stay
 *  each night but the last, the fee total against the budget. {days: [checkPlan result], flags, fees}. */
// a planned café stop's type (pipeline/schema.py CAFE_TYPES: TourAPI's 카페/찻집 and 제과), and the reader's words that
// leave a meal or the café out ('점심은 먹고 갈게요', '카페는 빼 주세요') — in the note or an edit's request
const CAFE_TY = /^(?:카페|찻집|기타음료점|제과)$/u;
const SKIP = {
  lunch: /(?:점심|식사)[^.!?。\n]{0,12}(?:먹고|빼|없이|생략|말고|안\s*먹|제외|따로|알아서)/u,
  dinner: /(?:저녁|식사)[^.!?。\n]{0,12}(?:먹고|빼|없이|생략|말고|안\s*먹|제외|따로|알아서)/u,
  cafe: /(?:카페|커피|디저트)[^.!?。\n]{0,12}(?:빼|없이|생략|말고|안\s*(?:가|넣)|제외|싫)/u,
};

/** Restaurants for a meal (cafe false: not a 카페·찻집·제과) or a café near a day's plan at `slot` [start, end]: open
 *  then by the data (checkPlan: no closed day, hours that fit), none the data says breaks 휠체어·유모차·주차, nearest
 *  first to the stop before the slot (else after it). The fix gets names it can use without reading (operator
 *  2026-10-18: a plan sent back for its missing lunch and café came back without them). */
export function foodNear(plan, di, slot, cafe, c, kb, n = 5) {
  const d = plan.days[di];
  const ref = d.stops.filter((s) => s.role !== "stay" && mins(s.end) <= mins(slot[0])).at(-1)
    || d.stops.find((s) => s.role !== "stay" && mins(s.start) >= mins(slot[1])) || d.stops[0];
  const at = ref && ((kb.docs[ref.page] || {}).f || {}).g;
  if (!at) return [];
  const hard = c.needs.filter((x) => HARD_NEEDS.includes(x));
  const near = [];
  for (const key of kb.keys) {
    const doc = kb.docs[key];
    const f = doc && doc.k === "place" && doc.f;
    if (!f || f.kd !== "food" || !f.g || CAFE_TY.test(f.ty || "") !== cafe) continue;
    if (d.stops.some((s) => s.page === key)) continue;
    if (hard.some((x) => needAt(x, f, cafe ? "cafe" : "meal").state === "no")) continue;
    near.push({ key, t: doc.t, ty: f.ty || "", m: metres(at, f.g) });
  }
  near.sort((a, b) => a.m - b.m);
  const out = [];
  for (const x of near.slice(0, 25)) {
    const r = kb.checkPlan({ date: d.date, stops: [{ page: x.key, start: slot[0], end: slot[1] }], move: c.move });
    const st = r.stops[0] || {};
    if (st.day === "closed" || (st.flags || []).length) continue;
    out.push(x);
    if (out.length >= n) break;
  }
  return out;
}
const named = (xs) => xs.map((x) => `${x.t} ${x.key} (${x.ty}, ${x.m < 1000 ? `${x.m}m` : `${(x.m / 1000).toFixed(1)}km`})`).join("; ");

/** What a day must hold besides its visits (the same rule as mealFlags): {lunch, dinner, cafe} from the reader's hours
 *  and words — for the request, before any plan (a whole day for a day between the first and the last). */
export function mealsAsked(c, asked = "") {
  const said = `${c.note || ""} ${asked || ""}`;
  return [...Array(c.days)].map((_, i) => {
    const from = i === 0 ? mins(c.start) : mins("09:00");
    const to = i === c.days - 1 ? mins(c.end) : mins("21:00");
    return { lunch: !SKIP.lunch.test(said) && from <= mins("11:30") && to >= mins("13:30"),
      dinner: !SKIP.dinner.test(said) && from <= mins("17:30") && to >= mins("19:30"),
      cafe: !SKIP.cafe.test(said) && to - from >= 300 };
  });
}

/** Meals and a café (operator 2026-10-18: '점심이랑 카페도 일정에 넣어줘' — a plan came back with three museums and no
 *  meal): a day the reader's hours run through lunch (11:30–13:30) or dinner (17:30–19:30) has a meal stop then, a day
 *  of five hours or more one café stop at a 카페·찻집·제과 page — unless the reader's words leave it out. Flags, each
 *  with the restaurants near the plan open then (foodNear). */
function mealFlags(plan, c, kb, asked = "") {
  const flags = [];
  const said = `${c.note || ""} ${asked || ""}`;
  const offer = (di, slot, cafe) => {
    const xs = foodNear(plan, di, slot, cafe, c, kb);
    return xs.length ? ` — 후보(일정 장소에서 가까운 순, ${slot[0]}~${slot[1]}에 여는 곳): ${named(xs)}` : "";
  };
  plan.days.forEach((d, i) => {
    const stops = d.stops.filter((s) => s.role !== "stay");
    if (!stops.length) return;
    const first = i === 0, lastDay = i === plan.days.length - 1;
    const from = first ? mins(c.start) : Math.min(...stops.map((s) => mins(s.start)));
    const to = lastDay ? mins(c.end) : Math.max(...stops.map((s) => mins(s.end)));
    const meal = (a, b) => d.stops.some((s) => s.role === "meal" && mins(s.start) < mins(b) && mins(s.end) > mins(a));
    if (!SKIP.lunch.test(said) && from <= mins("11:30") && to >= mins("13:30") && !meal("11:30", "13:30")) {
      flags.push(`${i + 1}일차: 점심(11:30~13:30)에 식사(role meal, 음식점) 장소가 없다 — 그 시간에 음식점을 넣는다${offer(i, ["12:00", "13:00"], false)}`);
    }
    if (!SKIP.dinner.test(said) && from <= mins("17:30") && to >= mins("19:30") && !meal("17:30", "19:30")) {
      flags.push(`${i + 1}일차: 저녁(17:30~19:30)에 식사(role meal, 음식점) 장소가 없다 — 그 시간에 음식점을 넣는다${offer(i, ["18:00", "19:00"], false)}`);
    }
    if (!SKIP.cafe.test(said) && to - from >= 300 && !d.stops.some((s) => s.role === "cafe")) {
      const lunch = d.stops.find((s) => s.role === "meal" && mins(s.end) <= mins("15:00"));
      const at = lunch ? lunch.end : "14:00";
      const slot = [at, `${String(Math.floor((mins(at) + 40) / 60)).padStart(2, "0")}:${String((mins(at) + 40) % 60).padStart(2, "0")}`];
      flags.push(`${i + 1}일차: 카페(role cafe — 종류가 카페·찻집·제과인 음식점) 한 곳이 없다 — 30분~1시간, 보통 점심 뒤에 넣는다${offer(i, slot, true)}`);
    }
    for (const s of d.stops.filter((x) => x.role === "cafe")) {
      const ty = ((kb.docs[s.page] || {}).f || {}).ty || "";
      if (!CAFE_TY.test(ty)) flags.push(`${i + 1}일차 ${s.name}: 카페 역할인데 사이트 자료의 종류가 '${ty || "없음"}' — 종류가 카페·찻집·제과인 곳으로 바꾼다`);
    }
  });
  return flags;
}

const clock = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const dist = (m) => (m < 1000 ? `${m}m` : `${(m / 1000).toFixed(1)}km`);

/** The last word on meals and the café once the model's one fix has left them wrong (operator 2026-10-18: a café stop
 *  came back at a 한식 restaurant that opens later): a café stop at a page that is not a 카페·찻집·제과, or a meal or café
 *  stop the data says is closed or not open then, takes the nearest café / restaurant open then (foodNear) at the same
 *  time; a day still without its lunch or its café gets one in a free gap there (50 / 40 minutes, 10 minutes either
 *  side). The model's sentences naming a place taken out are dropped. Returns what it changed, one line each, for the
 *  plan's checks — the reader sees the site changed it, never the model. */
export function repairFood(plan, c, kb, asked = "") {
  const said = `${c.note || ""} ${asked || ""}`;
  const changed = [];
  const out = new Set();
  const ty = (page) => ((kb.docs[page] || {}).f || {}).ty || "";
  // a change stands only when the day's own check (closed days, hours, legs too short for the distance) has no flag
  // about the place it brings and no more flags than before
  const dayFlags = (d) => kb.checkPlan({ date: d.date, stops: d.stops.map((s) => ({ page: s.page, start: s.start, end: s.end })), move: c.move }).flags;
  const stands = (d, before, name) => {
    const now = dayFlags(d);
    return now.length <= before.length && !now.some((f) => f.includes(name));
  };
  const order = (d) => d.stops.sort((p, q) => (p.role === "stay") - (q.role === "stay") || mins(p.start) - mins(q.start));
  const swap = (i, s, cafe, why) => {
    const d = plan.days[i];
    const before = dayFlags(d);
    const was = { page: s.page, name: s.name, why: s.why };
    for (const x of foodNear(plan, i, [s.start, s.end], cafe, c, kb, 5)) {
      Object.assign(s, { page: x.key, name: x.t, why: "" });
      if (!stands(d, before, x.t)) continue;
      changed.push(`${i + 1}일차 ${s.start} ${cafe ? "카페" : "식사"}: ${was.name}(${why})을 그 시간에 여는 가까운 ${cafe ? "카페" : "음식점"} ${x.t}(${x.ty}, 직선 ${dist(x.m)})로 사이트가 바꿈`);
      out.add(was.name);
      return;
    }
    Object.assign(s, was);
  };
  const insert = (i, cafe, lo, hi, len) => {
    const d = plan.days[i];
    const before = dayFlags(d);
    const stops = d.stops.filter((s) => s.role !== "stay").sort((a, b) => mins(a.start) - mins(b.start));
    const bounds = [i === 0 ? mins(c.start) : null, ...stops.flatMap((s) => [mins(s.start), mins(s.end)]),
      i === plan.days.length - 1 ? mins(c.end) : null];
    for (let k = 0; k + 1 < bounds.length; k += 2) {
      const a = bounds[k], b = bounds[k + 1];
      if (a === null || b === null) continue;
      // the first start in the gap that leaves room for the legs either side (tried every 10 minutes)
      for (let start = Math.max(a + 10, lo); start + len <= Math.min(b - 10, hi); start += 10) {
        const slot = [clock(start), clock(start + len)];
        const probe = { days: plan.days.map((dd, j) => (j === i ? { ...dd, stops: [...dd.stops, { page: "", start: slot[0], end: slot[1], role: "visit" }] } : dd)) };
        for (const x of foodNear(probe, i, slot, cafe, c, kb, 3)) {
          const add = { page: x.key, name: x.t, start: slot[0], end: slot[1], role: cafe ? "cafe" : "meal", why: "" };
          d.stops.push(add);
          order(d);
          if (stands(d, before, x.t)) {
            changed.push(`${i + 1}일차 ${slot[0]}~${slot[1]} ${cafe ? "카페" : "점심"}: 빠져 있어 그 시간에 여는 가까운 ${cafe ? "카페" : "음식점"} ${x.t}(${x.ty}, 직선 ${dist(x.m)})를 사이트가 넣음`);
            return true;
          }
          d.stops.splice(d.stops.indexOf(add), 1);
        }
      }
    }
    return false;
  };
  const asks = mealsAsked(c, asked);
  plan.days.forEach((d, i) => {
    for (const s of d.stops) {
      if (s.role !== "cafe" && s.role !== "meal") continue;
      const cafe = s.role === "cafe";
      if (cafe && !CAFE_TY.test(ty(s.page))) { swap(i, s, true, `종류 ${ty(s.page) || "없음"}`); continue; }
      const st = (kb.checkPlan({ date: d.date, stops: [{ page: s.page, start: s.start, end: s.end }], move: c.move }).stops[0]) || {};
      if (st.day === "closed" || (st.flags || []).length) swap(i, s, cafe, st.day === "closed" ? "그날 휴무" : "그 시간에 열지 않음");
    }
    const meal = (a, b) => d.stops.some((s) => s.role === "meal" && mins(s.start) < mins(b) && mins(s.end) > mins(a));
    if ((asks[i] || {}).lunch && !SKIP.lunch.test(said) && !meal("11:30", "13:30")) insert(i, false, mins("11:00"), mins("14:00"), 50);
    if ((asks[i] || {}).cafe && !SKIP.cafe.test(said) && !d.stops.some((s) => s.role === "cafe")) {
      const lunch = d.stops.find((s) => s.role === "meal" && mins(s.end) <= mins("15:00"));
      insert(i, true, lunch ? mins(lunch.end) : mins("12:30"), mins(lunch ? "18:00" : "18:00"), 40)
        || insert(i, true, mins(c.start), mins("18:00"), 40);
    }
  });
  if (out.size) {
    const keep = (x) => ![...out].some((n) => x.includes(n));
    plan.summary = dropSentences(plan.summary, keep);
    plan.notes = plan.notes.filter(keep);
  }
  return changed;
}

export function verify(plan, c, kb, asked = "") {
  const flags = [];
  const days = plan.days.map((d, i) => {
    const r = kb.checkPlan({ date: d.date, stops: d.stops.map((s) => ({ page: s.page, start: s.start, end: s.end })), move: c.move });
    flags.push(...r.flags.map((f) => `${i + 1}일차 ${f}`));
    const first = i === 0, lastDay = i === plan.days.length - 1;
    for (const s of d.stops) {
      if (s.role === "stay") continue;
      if ((first || c.days === 1) && mins(s.start) < mins(c.start)) flags.push(`${i + 1}일차 ${s.name}: 독자가 정한 시작 ${c.start}보다 이르다`);
      if ((lastDay || c.days === 1) && mins(s.end) > mins(c.end)) flags.push(`${i + 1}일차 ${s.name}: 독자가 정한 끝 ${c.end}보다 늦다`);
    }
    if (!lastDay && !d.stops.some((s) => s.role === "stay")) flags.push(`${i + 1}일차: 묵을 숙소(role stay)가 없다`);
    if (c.needs.includes("rain")) {
      const out = d.stops.filter((s) => s.role === "visit" && /자연·야외|레포츠/u.test(((kb.docs[s.page] || {}).f || {}).ty || ""));
      if (out.length > 1) flags.push(`${i + 1}일차: '비 와도 실내 위주'인데 야외 장소가 ${out.length}곳(${out.map((s) => s.name).join("·")}) — 짧은 야외는 하루 한 곳까지`);
    }
    return r;
  });
  const fees = planFees(plan.days, c, kb, c.budget);
  if (fees.verdict === "over") {
    flags.push(`입장료(확인된 것만) ${fees.known.toLocaleString("en-US")}원이 예산 ${c.budget.toLocaleString("en-US")}원을 넘는다 — 무료이거나 더 싼 곳으로 바꾼다`);
  }
  const hubs = hubLegs(plan, c, kb.meta.plan.hubs, kb);
  for (const h of hubs) {
    if (h.gap <= 0) {
      flags.push(h.dir === "from"
        ? `${h.name} ${h.at} 출발인데 첫 장소 ${h.stop}이 ${h.at}보다 늦게 시작하지 않는다 — 출발지에서 오는 여유를 둔다`
        : `${h.name}에 ${h.at}까지 가야 하는데 마지막 장소 ${h.stop}이 그 전에 끝나지 않는다 — 돌아갈 여유를 둔다`);
    }
  }
  flags.push(...mealFlags(plan, c, kb, asked));
  const needs = needsTable(plan, c, kb, fees);
  // a stop the data says breaks a need the reader picked is sent back like a closed day (operator 2026-10-18: it sat
  // under '확인할 것' as '맞지 않음 1'): 휠체어·유모차·주차 at any stop; '입장료 없는 곳 위주' when a day has two or more
  // paid visits ('비 와도 실내 위주' is the outdoor rule above)
  for (const m of needMisses(needs)) {
    if (HARD_NEEDS.includes(m.need)) {
      const r = m.rows[0];
      flags.push(`${m.day + 1}일차 ${r.name}: '${NEEDS[m.need]}' 조건인데 사이트 자료는 '${r.text}' — 이 조건에 맞는 곳(needs 목록)으로 바꾼다`);
    } else if (m.need === "free") {
      flags.push(`${m.day + 1}일차: '${NEEDS.free}'인데 입장료 있는 곳이 ${m.rows.length}곳(${m.rows.map((r) => r.name).join("·")}) — 유료는 하루 한 곳까지`);
    }
  }
  const checks = checksList(plan, c, { days }, needs, fees, hubs, kb);
  return { days, flags, fees, hubs, needs, checks, text: textIssues(plan, c, kb, fees) };
}

/** Kakao Map directions between two points (the reader's map app works out the route and its time; pipeline/maplinks.py
 *  kakao_transit_url is the same address for 'traffic'): by car, on foot under 1.2 km for a reader without a car,
 *  else public transport. */
export function directionsUrl(a, b, move, m) {
  const mode = move === "car" ? "car" : m !== null && m <= 1200 ? "walk" : "traffic";
  const q = (s) => encodeURIComponent(s).replace(/%2C/gi, " ");
  return { mode, url: `https://map.kakao.com/link/by/${mode}/${q(a.name)},${a.lat},${a.lng}/${q(b.name)},${b.lat},${b.lng}` };
}

/** What the page gets: the plan with each stop's day state and notes from checkPlan, each leg's distance, routes and
 *  directions link, the fee lines and total against the budget, and what is still flagged. */
export function finish(plan, check, c, now = new Date()) {
  const WEEK = "일월화수목금토";
  const days = plan.days.map((d, i) => {
    const r = check.days[i];
    const dt = new Date(`${d.date}T12:00:00Z`);
    return {
      date: d.date, label: `${i + 1}일차 · ${dt.getUTCMonth() + 1}월 ${dt.getUTCDate()}일 (${WEEK[dt.getUTCDay()]})`,
      stops: d.stops.map((s, j) => {
        const st = r.stops[j] || { day: "unknown", notes: [], flags: [] };
        return { path: s.page, name: s.name, start: s.start, end: s.end, role: s.role, why: s.why, day: st.day,
          notes: st.notes, flags: st.flags, checks: st.checks || [] };
      }),
      legs: r.legs.map((l) => ({ from: l.from, to: l.to, m: l.m, gap: l.gap, routes: l.routes, flag: l.flag,
        ...(l.a && l.b ? directionsUrl(l.a, l.b, c.move, l.m) : {}) })),
      hubs: (check.hubs || []).filter((h) => (h.dir === "from" ? i === 0 : i === plan.days.length - 1)),
    };
  });
  const f = check.fees;
  const fees = { state: f.state, total: f.total, known: f.known, limit: f.limit, verdict: f.verdict, open: f.open,
    conds: f.conds, days: f.days.map((d) => ({ date: d.date, lines: d.lines.map((l) => ({ what: l.what, who: l.who,
      count: l.count, status: l.status, won: l.won ?? null, sub: l.sub, basis: l.basis })) })) };
  return { v: 2, made: now.toISOString(), title: plan.title, summary: plan.summary, notes: plan.notes, conditions: c,
    days, fees, needs: check.needs, checks: check.checks, flags: check.flags, status: statusOf(check.flags, check.checks) };
}

/** The places whose site data fits each need the reader picked (plan_state.needAt 'ok' or, for parking, 'near'),
 *  as catalog paths — handed over with the conditions so the model needs no reading round to find them. At most
 *  30 a need; the facts behind them are the pages' own (the page shows each in the needs table). */
export function needHints(c, kb, max = 30) {
  const needs = c.needs.filter((n) => n !== "lesswalk");
  if (!needs.length) return "고른 조건이 없다.";
  const L = [];
  // the places to visit whose data fits every need picked: the model picks its visits here first (operator
  // 2026-10-18: one list a need, each cut at 30 in slug order, left it a place that broke another need)
  if (needs.length > 1) {
    const all = attractionsFitting(needs, kb);
    L.push(`모든 조건(${needs.map((n) => NEEDS[n]).join(" + ")})에 맞는 관광지 — 방문지는 여기서 먼저 고른다${all.length > max * 2 ? `(앞 ${max * 2}곳)` : ""}: `
      + `${all.slice(0, max * 2).map((d) => `${d.t} ${d.key}`).join("; ") || "없음"}`);
  }
  for (const need of needs) {
    const fit = [];
    for (const key of kb.keys) {
      const d = kb.docs[key];
      if (!d || d.k !== "place" || !d.f) continue;
      if (need !== "parking" && d.f.kd !== "attraction") continue;   // the places to visit; parking matters everywhere
      if (fitsNeed(need, d.f)) fit.push(`${d.t} ${key}`);
      if (fit.length >= max) break;
    }
    L.push(`${NEEDS[need]} — 사이트 자료가 맞다고 하는 곳${fit.length >= max ? `(앞 ${max}곳)` : ""}: ${fit.join("; ") || "없음"}`);
  }
  const hard = needs.filter((n) => HARD_NEEDS.includes(n));
  if (hard.length) L.push(`${hard.map((n) => NEEDS[n]).join("·")}: 사이트 자료가 맞지 않는다고 하는 곳은 어느 역할로도 고르지 않는다(고치게 돌려보낸다).`);
  return L.join("\n");
}

/** Whether a place's data fits a need (plan_state.needAt 'ok', or 'near' for parking), read as the place it is. */
function fitsNeed(need, f) {
  const r = needAt(need, f, f.kd === "food" ? "meal" : f.kd === "stay" ? "stay" : "visit",
    need === "free" ? { how: "own", states: f.fee && f.fee.free ? { free: 1 } : f.fee && f.fee.tab ? { paid: 1 } : { unknown: 1 } } : null);
  return r.state === "ok" || r.state === "near";
}

/** The attractions whose data fits every one of `needs`: [{key, t}] in catalog order. */
export function attractionsFitting(needs, kb) {
  const out = [];
  for (const key of kb.keys) {
    const d = kb.docs[key];
    if (!d || d.k !== "place" || !d.f || d.f.kd !== "attraction") continue;
    if (needs.every((n) => fitsNeed(n, d.f))) out.push({ key, t: d.t });
  }
  return out;
}

/** A trip the data cannot fill: fewer attractions fit the needs a stop must meet (HARD_NEEDS) than two a day. The
 *  reader is told at once, without a model call (operator 2026-10-18: '조건 만족 못 하면 아예 생성하기를 못 누르게').
 *  Returns the message, or '' when the trip can be planned. */
export function noFit(c, kb) {
  const hard = c.needs.filter((n) => HARD_NEEDS.includes(n));
  if (!hard.length) return "";
  const n = attractionsFitting(hard, kb).length;
  if (n >= c.days * 2) return "";
  const each = hard.length > 1 ? ` (조건별: ${hard.map((x) => `${NEEDS[x]} ${attractionsFitting([x], kb).length}곳`).join(" · ")})` : "";
  return `고른 조건(${hard.map((x) => NEEDS[x]).join("·")})에 모두 맞는 관광지가 사이트 자료에 ${n}곳뿐이라 ${c.days === 1 ? "하루" : `${c.days}일`} 코스를 만들 수 없어요${each}. 조건을 하나 줄여 주세요.`;
}

/** Runs one plan to the end through send(). Returns the log record's numbers. */
export async function makePlan({ client, kb, conditions, edit = null, send, signal, now, clock = () => Date.now() }) {
  const c = conditions;
  const t0 = clock();
  const system = buildPlanSystem(kb.catalog, now, kb.meta, kb.tickets);
  // the meals and the café each day must hold, named with the conditions (the rules alone left a plan of three museums)
  const must = mealsAsked(c, edit ? edit.request : "").map((m, i) => {
    const xs = [m.lunch && "점심 식당 1곳(role meal, 11:30~13:30 사이)", m.cafe && "카페 1곳(role cafe, 카탈로그 종류가 카페·찻집·제과인 음식점)",
      m.dinner && "저녁 식당 1곳(role meal, 17:30~19:30 사이)"].filter(Boolean);
    return xs.length ? `${i + 1}일차: ${xs.join(", ")}` : "";
  }).filter(Boolean);
  const mustText = must.length ? `\n\n꼭 넣을 것(빠지면 돌려보낸다):\n- ${must.join("\n- ")}` : "";
  const convo = [{ role: "user", content: `${neutralise(conditionsText(c, edit, kb.meta.plan))}${mustText}\n\n${dataBlock("needs", needHints(c, kb))}` }];
  let reads = 0;
  const rec = { rounds: 0, tools: [], submits: 0, flags: 0, text: 0, in: 0, out: 0, cache_read: 0, cache_write: 0, stop: "", status_plan: "" };
  let outUsed = 0;
  let toolChars = PLAN_LIMITS.toolChars;
  let best = null;   // the latest submit_plan with what cannot stand taken out (readSubmit salvaged), for the end
  // a plan the model could not fix in time: finished as it is, with what was taken out or changed and every check's
  // flags on top — the reader sees it as 'unmet', never an empty page
  const asked = edit ? edit.request : "";
  // meals and the café the model left wrong: the site's own last fix (repairFood), shown among the checks
  const settle = (plan, check) => {
    if (!check.flags.some((f) => /점심|저녁|카페/u.test(f))) return check;
    const changed = repairFood(plan, c, kb, asked);
    if (!changed.length) return check;
    rec.repaired = changed.length;
    const again = verify(plan, c, kb, asked);
    again.checks.unshift(...changed.map((t) => ({ k: "fix", t })));
    return again;
  };
  const finishAsIs = (b) => {
    step("fees");
    const check = settle(b.plan, verify(b.plan, c, kb, asked));
    check.flags.unshift(...b.fixes);
    rec.flags = check.flags.length;
    rec.text = check.text.length;
    rec.salvaged = 1;
    if (check.text.length) trimText(b.plan, c, kb, check.fees);
    const done = finish(b.plan, check, c, now);
    rec.status_plan = done.status;
    return done;
  };
  const step = (key) => send({ type: "status", step: key, text: PLAN_STATUS[key] });
  const cannot = edit ? "" : noFit(c, kb);
  if (cannot) {
    send({ type: "error", code: "no_fit", message: cannot });
    return { ...rec, status: "no_fit" };
  }
  step("search");
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
        const { plan, errors, salvaged, fixes } = readSubmit(use.input, c, kb);
        if (errors.length) {
          if (salvaged && (!best || best.fixes.length)) best = { plan: salvaged, fixes };   // never over a whole plan
          // no turn left for a fix (the last call, or the time for fixing gone): the plan as it is
          if (best && (last || clock() - t0 >= PLAN_LIMITS.fixBy)) {
            done = finishAsIs(best);
            break;
          }
          results.push({ type: "tool_result", tool_use_id: use.id, is_error: true,
            content: `고칠 것:\n- ${errors.join("\n- ")}\n고친 일정으로 submit_plan을 다시 부른다.` });
          continue;
        }
        best = { plan, fixes: [] };
        step("fees");
        const check = verify(plan, c, kb, edit ? edit.request : "");
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
        const settled = settle(plan, check);
        if (settled.text.length) trimText(plan, c, kb, settled.fees);
        done = finish(plan, settled, c, now);
        rec.status_plan = done.status;
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
    if (done) {
      send({ type: "plan", plan: done });
      return { ...rec, status: "ok" };
    }
    convo.push({ role: "user", content: results });
  }
  if (best) {
    send({ type: "plan", plan: finishAsIs(best) });
    return { ...rec, status: "ok" };
  }
  send({ type: "error", code: "empty", message: planError("empty") });
  return { ...rec, status: "empty" };
}

// ------------------------------------------------------------------ the handler
export function createPlanHandler(deps = {}) {
  const env = deps.env ?? process.env;
  const now = deps.now ?? (() => new Date());
  const log = deps.log ?? ((rec) => console.log(JSON.stringify(rec)));
  const limiter = deps.limiter ?? createLimiter(PLAN_LIMITS.perMinute, 60000,
    { perDay: PLAN_LIMITS.perDay, allPerMinute: PLAN_LIMITS.allPerMinute, allPerDay: PLAN_LIMITS.allPerDay });
  const knowledge = deps.knowledge ?? defaultKnowledge;
  let client = deps.client ?? null;

  async function getClient() {
    if (!client) {
      const { default: Anthropic } = await import("@anthropic-ai/sdk");
      client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: PLAN_LIMITS.callMs });
    }
    return client;
  }

  return async function handle(request) {
    const t0 = Date.now();
    const done = (status, extra = {}) => log({ evt: "plan", status, ms: Date.now() - t0, ...extra });
    const fail = (status, code) => json(status, { code, message: planError(code) });
    if (request.method !== "POST") {
      done("method");
      return json(405, { code: "method_not_allowed" }, { Allow: "POST" });
    }
    // the knowledge first: its meta is the origin allow-list and the city's hubs and likes (one load per instance)
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
    if (!deps.client && !env.ANTHROPIC_API_KEY) {
      done("not_configured");
      return fail(503, "not_configured");
    }
    const key = clientKey(clientIp(request));
    const refuse = (gate) => {
      done("rate_limited", { limit: gate.limit });
      const code = limitCode(gate.limit);
      return json(429, { code, message: planError(code) }, { "Retry-After": String(gate.retry) });
    };
    let gate = limiter.check(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let conditions;
    let edit;
    try {
      const body = await readBody(request, PLAN_LIMITS.bodyBytes);
      if (!body || typeof body !== "object") throw new HttpError(400, "bad_request");
      conditions = validConditions(body.conditions, now(), kb.meta.plan);
      edit = validEdit(body.plan, body.request, conditions);
    } catch (err) {
      const e = err instanceof HttpError ? err : new HttpError(400, "bad_request");
      done(e.code);
      return fail(e.status, e.code);
    }
    gate = limiter.take(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let api;
    try {
      api = await getClient();
    } catch (err) {
      done("unavailable", { reason: err?.code || err?.name || "load" });
      return fail(503, "busy");
    }
    const ac = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ac.abort();
    }, PLAN_LIMITS.requestMs);
    const stop = () => ac.abort();
    request.signal?.addEventListener("abort", stop);
    const enc = new TextEncoder();
    let open = true;
    const body = new ReadableStream({
      async start(controller) {
        const send = (ev) => {
          if (!open || (ac.signal.aborted && ev.type !== "error")) return;
          controller.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`));
        };
        try {
          const rec = await makePlan({ client: api, kb, conditions, edit, send, signal: ac.signal, now: now() });
          done(rec.status, { rounds: rec.rounds, tools: rec.tools, submits: rec.submits, flags: rec.flags, text: rec.text,
            plan: rec.status_plan || undefined, salvaged: rec.salvaged || undefined, repaired: rec.repaired || undefined, in: rec.in, out: rec.out, cache_read: rec.cache_read,
            cache_write: rec.cache_write, stop: rec.stop, edit: !!edit, days: conditions.days });
        } catch (err) {
          const status = typeof err?.status === "number" ? err.status : 0;
          let code = "error";
          if (timedOut) code = "timeout";
          else if (ac.signal.aborted) code = "client_gone";
          else if (status === 429 || status === 529 || status >= 500 || !status) code = "busy";
          if (code !== "client_gone") send({ type: "error", code, message: planError(code) });
          done(code, { api_status: status || undefined });
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
    return new Response(body, { status: 200, headers: SSE_HEADERS });
  };
}
