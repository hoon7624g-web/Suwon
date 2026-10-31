// What a checked plan states about itself — review 2026-10-17 (AI 코스 만들기 집중 평가 CE05·CE06, R09·R13): the
// result said '휴무·운영시간 확인 6/6곳 · 걸리는 것 없음' above a list that left two places' New Year's Day unconfirmed,
// and a summary said a wheelchair route was confirmed where the list below did not know. The code now writes every
// such statement itself, from the site's data, and the model's words carry none of them:
//   - needsTable: each need the reader picked, at each stop — the data's own words, and one of ok (the data says it
//     fits), near (parking: none of its own, a public lot close by), no (the data says it does not), unknown;
//   - checksList: everything the reader is to check before going, one line each, by kind;
//   - grounded: a number in the model's sentences that the place pages do not have, and words that claim a check;
//   - status: 'ready' (nothing flagged, nothing to check), 'check' (nothing flagged, things to check), 'unmet'
//     (flags left after the fix the model had);
//   - completeness (outside evaluation 2026-10-18, a Monday by train 10:00→17:00 in the rain: after an edit one stop
//     was left at 10:20–11:20, the lunch gone and 340 minutes with nothing before the train): the reader's day as
//     they set it, a meal when it spans lunch or dinner, no stretch of more than IDLE minutes without a stop, each
//     liking they picked against the stops, and on an edit what the plan had and must keep.
import { regionOf, regionsFloor } from "./knowledge.js";
import { HUBS } from "./plan_prompt.js";

export { regionOf };

export const NEED_LABEL = { rain: "실내", stroller: "유모차", wheelchair: "휠체어", parking: "주차", free: "입장료", lesswalk: "걷기" };
const INDOOR = /박물관|전시|문화시설|미술관/u;
const OUTDOOR = /자연·야외|레포츠/u;
// the access route's own words (TourAPI barrier-free 'accessible_route'): a ramp, a lift or no step at the door. A
// sentence that says one is NOT there is read first — '출입구까지 경사로가 설치되어 있지 않음' was read as a ramp
// because it names one (live check 2026-10-19: 말랭이마을 shown to a wheelchair user as reachable)
const ROUTE_OK = /턱이\s*없|단차가?\s*없|무단차|경사로|엘리베이터\s*설치|휠체어\s*접근\s*가능|평지/u;
const ROUTE_NO = /(?:경사로|엘리베이터|승강기)[^·,]*?(?:있지\s*않|없음|없어)|계단만|접근\s*불가|턱이\s*있/u;
// a route a wheelchair may not take though the data names a ramp or level ground: a steep ramp, earth or stones, gravel,
// works — read as something to check, never as fitting (round-6 verifier: 3.1운동 100주년 기념관's '경사로가 설치되어
// 있음(완만하지 않음)' and 월명공원's '평지로 되어 있으나 흙(돌) 구간 있음' were read as reachable); a stroller keeps ok on
// those, not on a route said to be steep or hard (STROLLER_ROUGH)
// (2026-10-24 I03: 세종 고운뜰공원 '경사로가 가파른 편으로 휠체어와 유모차 접근은 다소 어려울 수 있으나 … 차량으로 접근 할 수
// 있어 휠체어도 함께 올라 전망 관람 가능' read as fitting — '가파르' missed '가파른', and '어려울 수'·'다소'·'차량으로 접근'
// were not read)
const ROUTE_ROUGH = /완만하지\s*않|가파[르른]|흙|돌\)?\s*구간|자갈|비포장|공사|어려울\s*수|어렵|다소|일부\s*구간|차량으로\s*(?:만\s*)?접근/u;
// a route a stroller may not take either: steep or said to be hard (earth, gravel or a ramp not gentle it takes)
const STROLLER_ROUGH = /가파[르른]|어려울\s*수|어렵/u;
// a route the data says is reached by car: conditional for a reader who comes by car, not known for one who does not
const BY_CAR = /차량으로\s*(?:만\s*)?접근/u;

const access = (f, key) => (f.ac || []).filter((a) => a.k === key);
// a place whose inside is not open to visitors by its own data (docs.json f.ex — pipeline/chat_index.outside_only;
// outside tester 2026-10-23: 구 제일사료주식회사 공장 went in a course as a 30-minute stop, its card '내부 관람 불가' and the
// check only that its hours could not be read): an outdoor stop for the rain (plan_geo.isOutdoor — never indoor, never a
// rain swap-in), and said as what it is — the check where its hours would read as not known, the stop card, the
// '가기 전에 알아 둘 것' box — with the sources that say so
export const OUTSIDE_WORDS = "외관만 볼 수 있는 곳 — 내부 관람 불가";
export const OUTSIDE_LABEL = "외관 감상 · 내부 관람 불가";
export const isOutside = (f) => !!(f.ex && f.ex.length);
/** The sources that say the inside is not open ('군산시 문화관광 · 한국관광공사 TourAPI'; '자료' when none is named). */
export const outsideSrc = (f) => [...new Set((f.ex || []).map((x) => x.p).filter(Boolean))].join(" · ") || "자료";
// a closed-day value that shuts the place in the rain ('우천시 휴장'): for '비 와도 실내 위주' the place is 'no' at any
// role — the code neither puts it in nor keeps it (round-6 final verifier: 새만금어린이랜드, '매년 12월 ~ 2월, 우천시
// 휴장', kept 67 times and added 15 times for trips with the rain need)
const RAIN_SHUT = /(?:우천|강우|비\s*(?:가|이)?\s*오는\s*날)\s*(?:시|때)?\s*(?:에는?|엔)?\s*(?:휴장|휴무|휴관|휴업|휴원|미운영|운영\s*(?:하지\s*않|중단|안\s*함)|쉼|쉽니다|쉬)/u;
/** The closed-day value ({p, t}) that says the place shuts in the rain, or null. */
export const rainShut = (f) => (f.c || []).find((c) => RAIN_SHUT.test(c.t || "")) || null;

/** One stop against one need: {state, text}. role: the stop's role in the plan; fee: plan_fees per-visit entry; move:
 *  the reader's way of moving (car | transit) — an access route the data says is reached by car is 'cond' (조건부,
 *  차량 접근 시) for a reader by car, 'unknown' for any other. */
export function needAt(need, f, role, fee, move = "") {
  if (need === "rain") {
    const shut = rainShut(f);
    if (shut) return { state: "no", text: `비 오는 날 쉼(${shut.p} '${shut.t}')` };
    if (role !== "visit" || f.kd === "food" || f.kd === "stay") return { state: "ok", text: "실내(음식점·숙소)" };
    // (before the type: an exhibition hall whose inside is not open is no indoor stop)
    if (isOutside(f)) return { state: "no", text: `${OUTSIDE_WORDS}(${outsideSrc(f)})` };
    if (INDOOR.test(f.ty || "")) return { state: "ok", text: `실내(${f.ty})` };
    if (OUTDOOR.test(f.ty || "")) return { state: "no", text: `야외(${f.ty})` };
    return { state: "unknown", text: `실내인지 자료 없음${f.ty ? `(${f.ty})` : ""}` };
  }
  if (need === "stroller" || need === "wheelchair") {
    const route = access(f, "accessible_route");
    // the rental and the toilet as every source has them — '없음' too; values that differ each with its source and the
    // phone check (CLAUDE.md 3절 2항 — round 7 review A18: one source's '없음' was left out and the other's '있음' shown
    // alone, the row read 'ok' with nothing to check)
    // (pre: the label put before a value that does not name it — a function of the value for the stroller, whose field
    // is its rental (pipeline/schema.py '유모차 대여'): '불가' reads '유모차 대여 불가', never '유모차 불가' as if a
    // stroller may not come in — review 2026-10-22; a value starting with 대여 gets '유모차' alone)
    const extraOf = (key, word, pre, no) => {
      const all = access(f, key);
      if (!all.length) return [];
      const say = (a) => (a.t === "없음" ? no : a.t.includes(word) ? a.t : `${typeof pre === "function" ? pre(a.t) : pre} ${a.t}`);
      const many = new Set(all.map((a) => a.p || "")).size > 1;
      if (new Set(all.map((a) => /없음|없어|불가/u.test(a.t))).size > 1) return [`${all.map((a) => `${say(a)}${a.p ? `(${a.p})` : ""}`).join(" / ")} — 출처마다 달라 방문 전 전화 확인`];
      return [all.map((a) => `${say(a)}${many && a.p ? `(${a.p})` : ""}`).join(" · ")];
    };
    const extra = need === "wheelchair"
      ? [...extraOf("wheelchair", "휠체어", "휠체어", "휠체어 대여 없음"), ...extraOf("accessible_toilet", "화장실", "장애인 화장실", "장애인 화장실 없음")]
      : extraOf("babycarriage", "유모차", (t) => (/^대여/u.test(t) ? "유모차" : "유모차 대여"), "유모차 대여 없음");
    const tail = extra.length ? ` · ${extra.join(" · ")}` : "";
    // each line read on its own; lines that read differently are all shown, to be checked by phone (CLAUDE.md 3절 2항),
    // and the code goes by the least fitting ('no' before 'unknown' before 'ok': it never puts in or keeps a place for a
    // hard need on the word of one line when another says otherwise)
    const read = (t) => {
      if (ROUTE_NO.test(t)) return "no";
      if (need === "wheelchair" ? ROUTE_ROUGH.test(t) : STROLLER_ROUGH.test(t)) return BY_CAR.test(t) && move === "car" ? "cond" : "unknown";
      return ROUTE_OK.test(t) ? "ok" : "unknown";
    };
    const reads = route.map((a) => ({ ...a, s: read(a.t) }));
    if (new Set(reads.map((a) => a.s)).size > 1) {
      const worst = ["no", "unknown", "cond", "ok"].find((x) => reads.some((a) => a.s === x));
      const sources = new Set(reads.map((a) => a.p || "")).size > 1;
      return { state: worst, text: `출입구: ${reads.map((a) => `${a.t}${sources && a.p ? `(${a.p})` : ""}`).join(" / ")} — ${sources ? "출처마다 달라 " : ""}방문 전 전화 확인${tail}` };
    }
    if (reads.length && reads[0].s === "cond") return { state: "cond", text: `출입구: ${reads[0].t} — 조건부(차량으로 접근할 때)${tail}` };
    if (reads.length && reads[0].s !== "unknown") return { state: reads[0].s, text: `출입구: ${reads[0].t}${tail}` };
    if (reads.length) return { state: "unknown", text: `출입구: ${reads[0].t} — 확인 필요${tail}` };
    return { state: "unknown", text: `출입구 접근 정보 없음${tail}` };
  }
  if (need === "parking") {
    const near = f.pkn && f.pkn.m !== undefined ? `근처 공영주차장 ${f.pkn.n} 직선 ${f.pkn.m}m` : "";
    if (f.pk && /불가/u.test(f.pk)) return near ? { state: "near", text: `자체 주차 불가 · ${near}` } : { state: "no", text: "자체 주차 불가" };
    if (f.pk && /가능|구비|있음|무료/u.test(f.pk)) return { state: "ok", text: `주차 ${f.pk.split("\n")[0].slice(0, 30)}` };
    return near ? { state: "near", text: `주차 정보 없음 · ${near}` } : { state: "unknown", text: "주차 정보 없음" };
  }
  if (need === "free") {
    if (role !== "visit") return { state: "na", text: "입장료 없음(식사·카페·숙소)" };
    if (!fee) return { state: "unknown", text: "요금 정보 없음" };
    if (fee.how === "again") return { state: "ok", text: "같은 날 두 번째 방문" };
    if (fee.how !== "own") return { state: "no", text: "통합권으로 입장(유료)" };
    const st = fee.states || {};
    if (st.paid) return { state: "no", text: "입장료 있음" };
    if (st.unknown) return { state: "unknown", text: "요금 정보 없음·일부 확인 필요" };
    return { state: "ok", text: "무료" };
  }
  return { state: "unknown", text: "" };
}

/** {key, label, rows: [{day, i, name, state, text}]} for each need but lesswalk (no data reads walking). */
export function needsTable(plan, c, kb, fees) {
  return c.needs.filter((n) => n !== "lesswalk").map((need) => ({
    key: need, label: NEED_LABEL[need],
    rows: plan.days.flatMap((d, di) => d.stops.map((s, i) => {
      const f = ((kb.docs[s.page] || {}).f) || {};
      const fee = ((fees.days[di] || {}).per || []).find((p) => p.i === i);
      return { day: di, i, name: s.name, ...needAt(need, f, s.role, fee, c.move) };
    })),
  }));
}

/** What the reader is told about the plan, from the code's own checks (operator 2026-10-18: '이런 거 좀 안 뜨게 할 수
 *  없어? 무조건 완성된 결과가 나오게' — a finished plan's standing notes read as things left undone): {aware, checks}.
 *  aware: [{k, t}] — what holds for any plan of its kind and never makes it less finished: k 'move' (one line: the times
 *  between places are margins from straight-line distance, with the legs the site has no distance for), 'hub' (one line
 *  naming the station or terminal legs the site has no distance for), 'end' (one line a day before a night that puts
 *  its dinner or its stay after the reader's 하루 끝: what, and when — afterEnd), 'stay' (one line a stay: its check-in by the
 *  data, rooms and booking for the stay to confirm), 'walk' (걷기 적게: no data measures walking), 'outside' (one line a
 *  place whose inside is not open to visitors: what it is, with the sources that say so — knowledge.checkPlan outside).
 *  checks: [{k, t}] — this plan's own gaps in the data, shown at the stop: k 'day' (no closed days or hours on the
 *  site, a date rule the code cannot resolve, a public holiday, a second visit), 'fee' (a person or a place with no
 *  price), 'need' (a need the reader picked that the data at a stop does not say). */
export function checksList(plan, c, check, needs, fees, hubs, kb) {
  const aware = [];
  const checks = [];
  const many = plan.days.length > 1;
  const stays = new Set();
  const outside = new Set();
  plan.days.forEach((d, di) => {
    const r = check.days[di];
    d.stops.forEach((s, i) => {
      const st = r.stops[i] || {};
      for (const t of st.checks || []) checks.push({ k: "day", t: `${many ? `${di + 1}일차 ` : ""}${s.name}: ${t}` });
      // a place whose inside is not open (knowledge.checkPlan outside): what it is, once — never a gap in the data
      if (st.outside && !outside.has(s.page)) {
        outside.add(s.page);
        aware.push({ k: "outside", t: `${s.name}: ${OUTSIDE_LABEL}(자료: ${st.outside.p})` });
      }
      if (s.role === "stay" && !stays.has(s.page)) {
        stays.add(s.page);
        const ci = (((kb.docs[s.page] || {}).f) || {}).ci;
        aware.push({ k: "stay", t: `${s.name}: ${ci ? `체크인 ${ci}(사이트 값)` : "체크인 시각은 사이트에 없어요"} — 객실·예약은 숙소에 확인하세요` });
      }
    });
    // what a day before a night puts after the reader's 하루 끝 — its dinner, the night's stay (afterEnd, operator
    // 2026-10-24) —, said as it is: '1일차 하루 끝 18:00 뒤까지: 저녁 콩뜰 18:10~19:10 · 밤 숙소 … 19:20부터'
    const end = hm(c.end);
    if (di === plan.days.length - 1 || end === null) return;
    const dinner = mealIn(d.stops.filter((s) => s.role === "meal" && hm(s.end) > end), MEALS.dinner, kb);
    const stay = d.stops.find((s) => s.role === "stay" && hm(s.start) >= end);
    const bits = [...(dinner ? [`저녁 ${dinner.name} ${dinner.start}~${dinner.end}`] : []), ...(stay ? [`밤 숙소 ${stay.name} ${stay.start}부터`] : [])];
    if (bits.length) aware.push({ k: "end", t: `${di + 1}일차 하루 끝 ${c.end} 뒤까지: ${bits.join(" · ")} — 둘러볼 곳·카페는 날마다 하루 끝 안에 넣어요` });
  });
  for (const t of fees.open) checks.push({ k: "fee", t: `입장료 ${t}` });
  for (const n of needs) {
    for (const row of n.rows.filter((x) => x.state === "unknown" || x.state === "no" || x.state === "cond")) {
      checks.push({ k: "need", t: `${n.label}: ${many ? `${row.day + 1}일차 ` : ""}${row.name} — ${row.text}` });
    }
  }
  if (c.needs.includes("lesswalk")) aware.push({ k: "walk", t: "걷기: 걷는 거리는 사이트 자료로 잴 수 없어요 — 구간마다 직선거리를 적었어요" });
  if (hubs.length) {
    aware.push({ k: "hub", t: `${hubs.map((h) => (h.dir === "from" ? `${h.name} → ${h.stop}` : `${h.stop} → ${h.name}`)).join(", ")}: 사이트에 거리가 없는 구간이에요 — 지도 앱으로 확인하세요` });
  }
  if (plan.days.some((d) => d.stops.length > 1)) {
    // the legs the site has no distance for (a place without a point), named once in the same line
    const blind = plan.days.flatMap((d, di) => ((check.days[di] || {}).legs || []).filter((l) => l.m === null)
      .map((l) => `${many ? `${di + 1}일차 ` : ""}${d.stops[l.from].name} → ${d.stops[l.to].name}`));
    aware.push({ k: "move", t: `장소 사이 시간은 직선거리로 잡은 계획상 여유예요 — 실제 이동 시간은 지도 앱 길찾기로 확인하세요${blind.length ? ` (좌표가 없어 거리를 모르는 구간: ${blind.join(", ")})` : ""}` });
  }
  return { aware, checks };
}

const NUM = /\d[\d,]*(?:\.\d+)?/gu;
const CLAIM = /확인(?:된|됐|했|되었|됨|해\s*두)|보장|문제\s*없|걸리는\s*것\s*없|모두\s*(?:가능|열)/u;

// (round 7 review) what the site has no data on, said as done: little walking ('걷는 거리를 줄였', '걷기 적게 짰') —
// the site cannot measure walking
// ('걷는 거리가 짧은 실내·평지 위주로 골랐습니다' — round 7 A07)
const WALK_CLAIM = /걷(?:는|기)\s*(?:거리|구간|양|동선)?[^.!?]{0,12}?(?:줄였|줄인|줄여|적게\s*(?:했|잡|짰|두|구성)|최소|짧게\s*(?:했|잡|짰)|짧은)/u;
// access words a reason may use only when the place's own page has them (round 7 review: '신영시장은 휠체어를
// 대여해 줍니다' — no rental on the page; '빨간 벽돌 건물이라 유모차로 다니기 편합니다' — no access data): the word, and
// what the page must say for it
const ACCESS_WORDS = [[/대여/u, /대여\s*가능|대여가능|무료\s*대여|대여\s*(?:해|합|됩)/u], [/계단/u, /계단/u], [/엘리베이터|승강기/u, /엘리베이터|승강기/u],
  [/경사로/u, /경사로/u], [/문턱|턱이\s*없|턱\s*없/u, /문턱|턱이\s*없|턱\s*없|무단차/u], [/평지|평탄/u, /평지|평탄|경사\s*없/u]];
// a pram or a wheelchair said to get around easily — '유모차로 이동하기 쉬운 장미동·월명동 일대', '유모차로 다니기
// 편합니다', '휠체어로 다니기 좋은 곳', '유모차 친화적인', '무장애 동선', '배리어프리' (review 2026-10-22: the AI's summary
// said so above a needs table of '정보 없음' rows; the round-7 example above passed as no access word names it): the site
// has no data on getting around a street or an area, and a page's own words (a ramp, a step-free door, a rental) are
// the words above — read as a claim, whatever the page says. The ease word after the need (within the clause), or an
// ease adjective before it; never '전망 좋은 곳에 있으며 휠체어 대여가 가능합니다' (the adjective is of another thing,
// and 좋은 is not read before it)
const NEED_EASE = /(?:유모차|휠체어)[^.!?,]{0,20}?(?:쉬운|쉽|편[한하합해히리]|수월|좋[은습아]|무난|알맞|적합|다닐\s*수\s*있|무리\s*없|불편\s*없|어렵지\s*않|어려움\s*(?:이|은)?\s*없|친화)|(?:쉬운|편한|편리한|수월한|무난한)[^.!?,]{0,12}?(?:유모차|휠체어)|무장애\s*(?:동선|코스|길|경로)|배리어\s*프리/u;
/** The numbers of `text` (100 and up: years, prices, counts of rooms, distances in metres) that `source` does not
 *  have, the access words it uses that `source` does not back (words), and whether it claims a check, little walking
 *  or a pram's or a wheelchair's easy way (NEED_EASE). Numbers under 100 (people, ages, hours, minutes, days) are not
 *  read. */
export function grounded(text, source) {
  const src = String(source || "").replace(/(\d),(?=\d{3})/gu, "$1");
  const t = String(text || "");
  const bad = [];
  for (const [raw] of t.matchAll(NUM)) {
    const n = raw.replace(/,/gu, "").replace(/\.$/u, "");
    if (Number(n) < 100) continue;
    if (!new RegExp(`(?<![\\d.])${n.replace(".", "\\.")}(?![\\d])`, "u").test(src)) bad.push(raw);
  }
  const words = ACCESS_WORDS.filter(([w, backed]) => w.test(t) && !backed.test(src)).map(([w]) => w.exec(t)[0]);
  return { bad, words, claim: CLAIM.test(t) || WALK_CLAIM.test(t) || NEED_EASE.test(t) };
}

/** The sentences of a text without the ones a test rejects. */
export function dropSentences(text, keep) {
  return String(text || "").split(/(?<=[.!?。])\s+/u).filter((s) => s && keep(s)).join(" ").trim();
}

// what holds for any plan of its kind — the times between places are planned margins, a hub's leg has no distance
// on the site, a stay's room is the stay's to confirm, walking cannot be measured — never makes a plan a draft: the
// page keeps these apart ('가기 전에 알아 둘 것'), not as something left to fix (operator 2026-10-18: '이런 거 좀 안
// 뜨게 할 수 없어? 무조건 완성된 결과가 나오게'). checksList returns them as 'aware'.
export const AWARE = new Set(["move", "hub", "end", "stay", "walk", "note", "outside"]);

/** A plan the page gets is 'ready' (operator 2026-10-18): its checks and standing notes never make it less so. A plan
 *  with flags left is never sent (planner.makePlan: an error 'conditions' instead) — 'unmet' names it in the log. */
export function statusOf(flags) {
  return flags.length ? "unmet" : "ready";
}

// ------------------------------------------------------------ the day as the reader lives it
export const HUB_MARGIN = 30;   // minutes kept after the station or terminal the trip starts from, and before the one it ends at — at least
export const IDLE = 120;        // a stretch longer than this with no stop inside the reader's day is empty time
// the 권역 of each station and terminal (plan_prompt.HUBS), by its address on the site's guides and the 읍·면·동 → 권역
// rule the place pages' 위치 lines follow (docs.json: every 내흥동 page 금강, every 경암동 page 원도심, every 옥서면 page
// 은파): 군산역 내흥2길 197, 내흥동 (/guides/차-없이-군산-당일여행/#h-b5; the page 구불1길 비단강길, 금강 권역, has the same
// address); the express terminal 해망로 30, 경암동, and the intercity one 해망로 18 beside it (/guides/군산-가는-법-교통/
// #h-b5); 군산공항 옥서면 산동길 2 (#h-b4)
export const HUB_REGION = { station: "금강", bus: "원도심", express: "원도심", airport: "은파" };
/** The minutes kept between the station or terminal and the stop next to it — after the start before the first stop
 *  (dir 'from'), after the last stop before the end ('to') — a planned allowance, never a travel time (review
 *  2026-10-22 C7a: 30 minutes from 군산역 to 선유도해수욕장 by bus passed): HUB_MARGIN, or the floor between the hub's 권역
 *  and the stop's page's (knowledge.regionsFloor — 45 minutes without a car across 권역, 30 by car; into or out of 고군산
 *  2 hours without a car, 1 by car) when that is more. 0 when the reader named no hub that way; HUB_MARGIN for a stop
 *  whose page names no 권역 (doc null too). */
export function hubMargin(c, dir, doc) {
  const key = dir === "from" ? c.from : c.to;
  if (!key) return 0;
  return Math.max(HUB_MARGIN, regionsFloor(HUB_REGION[key], regionOf(doc), c.move));
}
export const SOFT_IDLE = 105;   // a stretch this long between two stops the code fills when a place fits it (never flagged: IDLE is the check's)
// lunch and dinner: the hours a day must span to need one (from–to), the window a meal stop is the meal in (near, by
// its middle), the start the code aims a meal it adds at, and the earliest and latest start it gives one; side: the
// hours a meal stop is still read as that meal by its middle when it is outside the window (live check 2026-10-19 —
// the model put 아리랑 at 15:00–16:00 and 군산일식 at 20:00–21:00, the code read neither as a meal and added two more:
// four meals in a day; a 짬뽕 lunch at 10:30 got a second lunch at 12:10). The sides meet at 16:00 and leave the
// morning before 10:30 and the night from 22:00 to neither, by the site's restaurants (147 that serve a meal, their
// hours read for a weekday): 49 are open at 10:30 (14 at 09:30, 120 at noon); 34 give a break, 33 of them over the
// whole of 15:00–16:00 (15:00–17:00 the most common; the other 15:10–17:00) — the fewest are open at 15:30–16:00
// (77–82, 110 at 18:00); 13 at 21:30, 10 at 22:00. A meal on neither side is a breakfast or a late snack, never the day's lunch or dinner.
export const MEALS = {
  lunch: { label: "점심", from: 690, to: 810, near: [660, 870], side: [630, 960], at: 720, first: 690, last: 780 },
  dinner: { label: "저녁", from: 1050, to: 1170, near: [1020, 1230], side: [960, 1320], at: 1080, first: 1050, last: 1140 },
};
// a meal longer than this the code shortens to it (a model's two-hour lunch: the live check's third day); the code
// adds no meal that starts within MEAL_APART minutes of another meal stop (a 10:30 lunch and one the code added at
// 12:10). Both are the code's planning rules, not facts of a restaurant — never said as the time a meal takes.
export const MEAL_LONG = 90;
export const MEAL_APART = 150;
const midOf = (s) => (hm(s.start) + hm(s.end)) / 2;
/** The meal (MEALS key) a meal stop at a–b is read as, by its middle — the side it is on — or '' (a breakfast before
 *  10:30, a late snack from 22:00). */
export const mealKind = (a, b) => Object.keys(MEALS).find((k) => (a + b) / 2 >= MEALS[k].side[0] && (a + b) / 2 < MEALS[k].side[1]) || "";
/** Where a meal stop at a–b sits: in its meal's window ('lunch', 'dinner'), only on its side ('~lunch', '~dinner'), or
 *  on neither (''). A stop moved whole keeps it (planner.shiftPlan, plan_build.shiftStops). */
export function mealSlot(a, b) {
  const k = mealKind(a, b);
  if (!k) return "";
  return (a + b) / 2 >= MEALS[k].near[0] && (a + b) / 2 < MEALS[k].near[1] ? k : `~${k}`;
}
/** Whether a meal stop is in its meal's window (near, by its middle). */
export const inMealWindow = (s, meal) => midOf(s) >= meal.near[0] && midOf(s) < meal.near[1];
// 빼다 as leaving something out: 빼고, 빼서, 빼기로, 빼었·뺐, 빼놓았, 빼 주세요, 빼 드렸습니다 — never 빼놓을 수 없는,
// 빼놓지 말고, 빼지 마, 빼먹지, 빼어난, 빼곡 (review 2026-10-18). Read here and in planner.align.
// a form of leaving something out: any form of 빼다 except those that keep it (빼먹지 마, 빼놓을 수 없는, 빼지 마) or are other words (빼어나다, 빼곡하다) — listing the forms that drop it missed
// '빼줘', '빼요', '빼도', '빼면' (review 2026-10-18, third round)
export const CUT = /빼(?!먹|놓(?:을|지)|\s*지\s*(?:마|말|않)|어|곡)|뺐|뺀|뺄|뺍/u;
// the reader wrote that they eat elsewhere ('점심은 빼 주세요', '저녁은 따로 먹어요', '점심·저녁은 따로'): conservative — the
// meal words and a word of leaving them out within a few characters, no other meal word between. 점심 is the lunch and
// 저녁 the dinner (아침 neither); 식사·밥·끼니 are both only on their own — next to a meal word they are that meal's
// ('저녁 식사는 따로' leaves the lunch in), and inside a word they are no meal ('비빔밥은 빼'). Only a form of leaving it
// out counts: '빼먹지 말아', '빼지 마', '없이는 안 돼', '제외하지 마' want the meal.
const SAID_OUT = new RegExp(String.raw`(?:((?:점심|저녁|아침)(?:\s*(?:과|와|이랑|하고|및|[,·])\s*(?:점심|저녁|아침))*)\s*(?:식사|밥|끼니)?|(?<!(?:점심|저녁|아침)[^.!?\n]{0,4})(?<![가-힣])(?:식사|밥|끼니))(?:(?!점심|저녁|아침)[^.!?\n]){0,8}?`
  + String.raw`(?:${CUT.source}|없이(?!는?\s*(?:안|못))|안\s*먹|따로|제외(?!하지)|생략(?!하지))`, "gu");
export function eatsElsewhere(kind, ...texts) {
  const word = MEALS[kind].label;
  return texts.some((t) => [...String(t || "").matchAll(SAID_OUT)].some((m) => (m[1] ? m[1].includes(word) : true)));
}

export const hm = (t) => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(t || "");
  return m ? +m[1] * 60 + +m[2] : null;
};
export const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
/** 340 → '5시간 40분' */
export const span = (n) => [Math.floor(n / 60) ? `${Math.floor(n / 60)}시간` : "", n % 60 ? `${n % 60}분` : ""].filter(Boolean).join(" ") || "0분";

/** The stop of `stops` that is the day's lunch or dinner, or undefined: one with the role meal at a place that is not
 *  a café or a bakery (isCafe, read with kb — final check 2026-10-18: a 'meal' at a bakery counted as the day's lunch)
 *  whose middle falls on the meal's side (MEALS side — live check 2026-10-19: a model's 15:00 lunch is the lunch; before,
 *  only the window counted and the code added another); of several, one in the window first, then the model's own (not
 *  added by the code), then the one nearest the meal's aim. One that only touches the window from the morning (a
 *  breakfast to 11:10) is no meal. */
export function mealIn(stops, meal, kb = null, rank = null) {
  const all = (stops || []).filter((s) => s.role === "meal" && !(kb && isCafe(kb.docs[s.page])) && midOf(s) >= meal.side[0] && midOf(s) < meal.side[1]);
  if (all.length < 2) return all[0];
  // (rank: the caller's own order first — planner.tidyMeals: a meal an edit left as it was, then the place the reader's
  // words name; round-6 verifier: the 짬뽕 the reader asked for went for the code's window lunch. The model's own
  // before one the code swapped in or added: a swapped-in place may go again later)
  const r = rank || (() => 0);
  return [...all].sort((a, b) => r(a) - r(b) || Number(!inMealWindow(a, meal)) - Number(!inMealWindow(b, meal)) || Number(!!a.by) - Number(!!b.by)
    || Math.abs(hm(a.start) - meal.at) - Math.abs(hm(b.start) - meal.at))[0];
}
/** The meal stops of a day by what they are (live check 2026-10-19: at most one lunch and one dinner a day): {lunch,
 *  dinner, extra} — lunch, dinner: the day's (mealIn); extra: the meal stops beyond them that are no café (a café or a
 *  bakery as a meal is a café stop: planner.tidyMeals) — a second on a side; one on neither side (a breakfast, a late
 *  snack) when the day has or needs both a lunch and a dinner, or when it starts within MEAL_APART minutes of the
 *  day's lunch or dinner (a 10:00 meal and a noon lunch); and a lunch or a dinner the day does not need (its reader's
 *  day does not span it, or they eat it elsewhere) that starts within MEAL_APART minutes of the other (a 15:00 lunch
 *  and a 15:40 'dinner' on a day that ends at 16:40). needs: the meals the day must have; other: the reader asked for
 *  a breakfast or a late meal of their own (wantsOther) — a meal on neither side then stays. */
export function mealRoles(stops, kb, needs = [], other = false, rank = null) {
  let lunch = mealIn(stops, MEALS.lunch, kb, rank), dinner = mealIn(stops, MEALS.dinner, kb, rank);
  const close = (x, y) => !!(x && y) && Math.abs(hm(x.start) - hm(y.start)) < MEAL_APART;
  if (close(lunch, dinner) && !needs.includes("dinner")) dinner = undefined;
  else if (close(lunch, dinner) && !needs.includes("lunch")) lunch = undefined;
  const both = !!(lunch || needs.includes("lunch")) && !!(dinner || needs.includes("dinner"));
  // (other: {early, late} — wantsOther; true for both)
  const theirs = (s) => (other === true ? true : !!other && (midOf(s) < MEALS.lunch.side[0] ? other.early : other.late));
  const extra = (stops || []).filter((s) => s.role === "meal" && s !== lunch && s !== dinner && !isCafe(kb.docs[s.page])
    && (mealKind(hm(s.start), hm(s.end)) || (!theirs(s) && (both || close(s, lunch) || close(s, dinner)))));
  return { lunch, dinner, extra };
}
// the reader's words asking for a meal besides lunch and dinner (a breakfast, a brunch, a late-night one): the model's
// meal on neither side is then theirs, not one too many — a breakfast only as a meal ('아침도 먹고 싶어요', '아침 식사',
// '조식'), never the morning ('아침 일찍 출발해요': round-6 verifier, a third meal stayed)
// — a morning one and a late one apart: '야식도 먹어요' keeps no breakfast (round-6 verifier: a breakfast kept for it
// grew into a second lunch)
const EARLY_MEAL = /아침\s*(?:식사|밥)|아침\s*(?:을|를|도|은|는|에)?\s*(?:먹|드시|챙기)|조식|브런치|breakfast|brunch/iu;
const LATE_MEAL = /야식|late[- ]?night|supper/iu;
/** {early, late}: whether the reader's words ask for a breakfast (a meal before the lunch's side) or a late meal (after
 *  the dinner's). */
export const wantsOther = (...texts) => ({ early: texts.some((t) => EARLY_MEAL.test(String(t || ""))), late: texts.some((t) => LATE_MEAL.test(String(t || ""))) });
/** Whether the reader's words set the time of a meal of theirs ('점심은 2시 넘어서', '저녁을 늦게', '늦은 점심', '저녁은
 *  4시쯤 일찍'): the model's lunch or dinner then stays at its time (planner.tidyMeals). A bare 점심·저녁 does not
 *  ('저녁 기차', '점심은 따로' — round-6 verifier). */
export function saysMealTime(kind, ...texts) {
  const w = MEALS[kind].label;
  const at = new RegExp(`${w}(?:\\s*(?:식사|밥))?\\s*[은는을를도이가]?\\s*(?:(?:오전|오후|낮|밤)\\s*)?(?:\\d|한\\s*시|두\\s*시|세\\s*시|네\\s*시|다섯\\s*시|여섯\\s*시|일곱\\s*시|여덟\\s*시|늦|이르|이른|일찍|느지막|조금\\s*(?:늦|일찍))|(?:늦은|이른|늦게|일찍|느지막이)\\s*${w}`, "u");
  return texts.some((t) => at.test(String(t || "")));
}
// an edit's request that is about the meals (planner.tidyMeals, plan_build.cleanSeeds: a meal an edit left as it was
// stays unless the request is about it — round-6 verifier: '카페 하나 더' moved the dinner an hour). A lunch or a dinner
// by its word; any meal by a word for meals at all. A snack ('간식으로 칼국수 한 그릇') is not a meal.
const ASK_LUNCH = /점심|런치|lunch/iu;
const ASK_DINNER = /저녁|디너|dinner/iu;
const ASK_MEAL = /식사|끼니|아침|조식|브런치|야식|식당|음식점|맛집|breakfast|brunch|\bmeals?\b/iu;
export function asksMeal(kind, request) {
  const t = String(request || "");
  return ASK_MEAL.test(t) || (kind === "lunch" && ASK_LUNCH.test(t)) || (kind === "dinner" && ASK_DINNER.test(t));
}
// a request for a snack stop rather than a meal (round-6 verifier: '오후 3시쯤 간식으로 칼국수 한 그릇 먹을 곳을 넣어
// 주세요' — the model's 15:00 칼국수 as a meal was dropped as a second lunch)
export const SNACK = /간식|요기|디저트|한\s*그릇|가볍게|snack/iu;
// the reader's own words (note, request) read for what they want to eat: the words of two characters or more, their
// particles left off, without the words of asking and of time — '짬뽕 먹고 싶어요' → 짬뽕
const LIKE_STOP = new Set(["점심", "저녁", "아침", "식사", "끼니", "브런치", "야식", "조식", "간식", "먹고", "먹을", "먹어", "먹는", "먹으러", "먹기",
  "싶어요", "싶어", "싶다", "싶은", "주세요", "넣어", "넣고", "해주세요", "해", "좋아요", "좋겠어요", "좋아해요", "가고", "보고", "오후", "오전", "둘째",
  "첫째", "셋째", "하루", "일찍", "늦게", "하나", "카페", "장소", "코스", "일정", "여행", "아이", "가족", "시간", "맛집", "음식점", "식당", "군산",
  "그릇", "가볍게", "따로", "빼고", "빼", "주로", "위주", "위주로", "근처", "가까운", "곳", "날", "정도", "쯤", "있는", "없는", "먹을게요", "할게요",
  "그리고", "그냥", "꼭", "많이", "조금", "같이", "함께", "바꿔", "바꾸고", "바꿔서", "추가", "추가해", "빼줘", "넣어줘", "원해요", "원합니다",
  "드시", "드실", "가볍게", "넣을", "넣는", "다른", "대신", "더", "요리", "음식", "먹어요", "먹을래요", "먹었으면", "해요", "가요",
  "먹고싶어요", "있어요", "없어요", "좋은", "맛있는", "유명한"]);
const PARTICLE = /(?:으로|에서|이랑|하고|까지|부터|은|는|이|가|을|를|도|만|로|에|과|와|랑)$/u;
export function likeWords(...texts) {
  const out = new Set();
  for (const t of texts) {
    for (const [w] of String(t || "").replace(/\d+\s*[가-힣]*/gu, " ").matchAll(/[가-힣A-Za-z]{2,}/gu)) {
      let x = w.replace(PARTICLE, "");
      // ('짬뽕집', '해산물 요리' → 짬뽕, 해산물: the summary names the dish)
      if ([...x.replace(/(?:집|가게|전문점|요리)$/u, "")].length >= 2) x = x.replace(/(?:집|가게|전문점|요리)$/u, "");
      if ([...x].length >= 2 && !LIKE_STOP.has(x) && !LIKE_STOP.has(w)) out.add(x);
    }
  }
  return [...out];
}
/** The meals of day i that an edit left as they were — the same place, start and end as on the reader's page — unless
 *  its request is about that meal (asksMeal): a test of a stop. planner.tidyMeals and plan_build.cleanSeeds leave such
 *  a meal alone, as an edit makes no change the reader did not ask for (round-6 verifier: '카페 하나 더 넣어 주세요'
 *  moved a dinner and the stops before it by an hour; a link's reader lost the breakfast the owner's note kept). */
export function keptMeal(edit, i, kb) {
  const before = edit ? ((edit.plan.days[i] || {}).stops || []).filter((x) => x.role === "meal") : [];
  if (!before.length) return () => false;
  const keys = before.map((x) => ({ page: (kb && kb.keyFor ? kb.keyFor(x.page) : "") || x.page, start: x.start, end: x.end }));
  return (s) => !!s && s.role === "meal" && keys.some((x) => x.page === s.page && x.start === s.start && x.end === s.end)
    && !asksMeal(mealKind(hm(s.start), hm(s.end)), edit.request);
}
/** The reader's words that say which meals they eat elsewhere: the note, an edit's request, and the meals a shared
 *  plan's link decided (edit.eats — planner.createPlanHandler, from a signed base's e). */
export const eatsWords = (c, edit) => [c && c.note, edit && edit.request, edit && edit.eats];
/** Whether a place is one the reader's words name (likeWords): in its name, its type, the first line of its page, its
 *  summary line or its menu lines ('- 대표 메뉴: …', '- 취급 메뉴: …') — not the rest of the page (addresses, hours,
 *  sources). */
export function liked(doc, words) {
  if (!doc || !words.length) return false;
  const lines = String(doc.x || "").split("\n");
  const hay = [doc.t || "", ((doc.f || {}).ty) || "", lines[0] || "", ...lines.filter((l) => /^(?:요약:|-\s*(?:대표|취급)\s*메뉴)/u.test(l))].join(" ");
  return words.some((w) => hay.includes(w));
}

// ------------------------------------------------------------ the reader's 하루 시작·하루 끝
// (operator 2026-10-24: '하루 시작·끝은 여러 날 일정의 모든 날에 적용하되 관람만 제한한다' — the places to visit and the cafés keep
// to the reader's start and end every day; on a day before a night the dinner and the night's stay may come after the
// end. 2026-10-24 I07 had held the dinner to the end too, and a day before a night set to the form's 18:00 lost its
// dinner.)
/** Whether stop s may run past the reader's 하루 끝 on its day — last: the day is the trip's last (a one-day trip's
 *  too), which ends at the end for every stop, no night following it. The night's stay; on a day before a night the
 *  day's dinner: a meal at a restaurant (never a café or a bakery — isCafe) in the dinner's window (MEALS.dinner.near,
 *  by its middle: mealSlot 'dinner' — the code's own dinner hours; the restaurant's hours and last order are
 *  checkPlan's, as for any stop). a, b: the times it is read at (minutes; its own by default). Every other stop keeps
 *  to the end. */
export const afterEnd = (s, last, kb = null, a = hm(s.start), b = hm(s.end)) => s.role === "stay"
  || (!last && s.role === "meal" && !(kb && isCafe(kb.docs[s.page])) && mealSlot(a, b) === "dinner");
/** Whether day i of a plan takes a dinner after the reader's 하루 끝 when one fits (operator 2026-10-24): a day before a
 *  night whose end reaches the dinner's hour (MEALS.dinner.from, 17:30) but comes before the dinner's end
 *  (MEALS.dinner.to, 19:30 — a later end spans the dinner, which the day then must have: spans), unless the reader eats
 *  it elsewhere or the day ends at its night's stay before its end (readerDay stay — the model's, at its check-in — or
 *  one the code ended it at, s.ends). The code puts one in when a restaurant open then fits (plan_build's day,
 *  planner.repair 4 on a new plan; the stay moves after it); none is no fault — the day the reader set ends before the
 *  dinner. */
export function nightDinner(plan, c, i, kb = null, edit = null) {
  const end = hm(c.end);
  if (i >= plan.days.length - 1 || end === null || end < MEALS.dinner.from || end >= MEALS.dinner.to || eatsElsewhere("dinner", ...eatsWords(c, edit))) return false;
  const day = readerDay(plan, c, i, kb);
  return !day || !day.stay || (!day.stay.ends && hm(day.stay.start) >= end);
}

/** Whether a night's stay ends the reader's day: one the model put in whose page gives a check-in time. A stay the
 *  code put in (by, planner.repair 6) or one with no check-in time says nothing of when the day ends (review
 *  2026-10-18: a stay with no check-in time put in at 13:00 after a stop ending at 12:30 left the day without its
 *  lunch). Without kb, every stay the model put in. */
export const endsDay = (s, kb = null, c = null, stops = []) => !s.by && (!kb || !!(((kb.docs[s.page] || {}).f || {}).ci))
  // (and only one that leaves no more than IDLE minutes of the reader's day after it, or that comes after the day's
  // dinner, or that the code could not fill the day past — s.ends, planner.settle — live check 2026-10-19: the model's stays at 15:00, 16:20, 17:00 and 19:00 of days the reader set to end
  // at 18:00–22:00 ended them there, with no dinner, the afternoon or the night empty, on 5 of 12 trips of two and
  // three days; a stay after the dinner ends a full day as before)
  // (near the reader's end only past the dinner's window when their day runs past it — wave B 2026-10-19: a stay at
  // 19:10 of a day to 21:00 ended it with no dinner)
  && (!c || s.ends || (hm(s.start) >= hm(c.end) - IDLE && (hm(c.end) < MEALS.dinner.to || hm(s.start) >= MEALS.dinner.to))
    || stops.some((x) => x.role === "meal" && !(kb && isCafe(kb.docs[x.page])) && mealKind(hm(x.start), hm(x.end)) === "dinner" && hm(x.end) <= hm(s.start)));

/** The evening after a day's dinner is the reader's own: the latest their day runs to when it has one (the dinner's end,
 *  not before the dinner's window ends) — no stretch after it is empty time, and the code puts nothing in it (wave B
 *  2026-10-19: days set to end at 23:00 got a park, a wind farm, a street and a bridge from 19:00 in the dark).
 *  dinner: its [start, end] in minutes, or null. */
export const eveningFrom = (dinner) => (dinner ? Math.max(dinner[1], MEALS.dinner.to) : Infinity);

/** Day i as the reader lives it: {lo, hi, mlo, mhi, own, stay} in minutes — the first day from the start they set
 *  (after the station's margin, hubMargin), the last day to the end they set (before it), a day before a night to the
 *  night's stay when it ends the day (endsDay; no later than the end they set) and else to that end, as with no stay
 *  (a first day ending at 12:30 with the stay at 15:00 spans the lunch, as a last day would), and none past the
 *  evening after the day's dinner (eveningFrom); every day at least its
 *  first stop's start to its last stop's end (a stay that ends the day before that: the last stop's end, as nothing
 *  can go after it); own: the stops but the night's stay, in order; stay: that night's stay after them when it ends
 *  the day (else null, and always on the last day). null when there are no stops. */
export function readerDay(plan, c, i, kb = null) {
  const own = plan.days[i].stops.filter((s) => s.role !== "stay");
  if (!own.length) return null;
  const lastDay = i === plan.days.length - 1;
  const a = hm(own[0].start), z = Math.max(...own.map((s) => hm(s.end)));
  const stays = lastDay ? [] : plan.days[i].stops.filter((s) => s.role === "stay" && endsDay(s, kb, c, plan.days[i].stops));
  const stay = stays.find((s) => hm(s.start) >= z) || null;
  // (the station's margin for the stop the day starts at and the one it ends at: hubMargin, by their 권역)
  const docOf = (s) => (kb ? kb.docs[s.page] : null);
  const lo = i === 0 ? hm(c.start) + hubMargin(c, "from", docOf(own[0])) : a;
  const hi = lastDay ? hm(c.end) - hubMargin(c, "to", docOf(own.at(-1))) : stays.length && !stay ? z : Math.min(hm(c.end), stay ? hm(stay.start) : hm(c.end));
  // (mlo, mhi: the day as its meals are read — spans —, after the station's HUB_MARGIN only: the longer ride to another
  // 권역 or the islands never takes the day's lunch away — review 2026-10-22, a 10:00 train to the islands, there at
  // 12:00, still has its lunch, as with the 30 minutes before)
  const mlo = i === 0 ? hm(c.start) + (c.from ? HUB_MARGIN : 0) : a;
  const mhi = lastDay ? hm(c.end) - (c.to ? HUB_MARGIN : 0) : hi;
  // (not past the evening after the day's dinner: eveningFrom)
  const dinner = mealIn(own, MEALS.dinner, kb);
  const evening = eveningFrom(dinner && [hm(dinner.start), hm(dinner.end)]);
  return { lo: Math.min(lo, a), hi: Math.max(Math.min(hi, evening), z), mlo: Math.min(mlo, a), mhi: Math.max(Math.min(mhi, evening), z), own, stay };
}
/** Whether a reader's day (readerDay; or {lo, hi}) spans a meal (MEALS) — read on mlo–mhi when the day has them. */
export const spans = (day, meal) => (day.mlo ?? day.lo) <= meal.from && (day.mhi ?? day.hi) >= meal.to;

/** The stretches of the reader's day with no stop: [{from, to, minutes, at}] — at: the index in day.own the stretch
 *  ends before (day.own.length: after the last stop). */
export function idleGaps(day, travel = null) {
  const out = [];
  let t = day.lo;
  day.own.forEach((s, j) => {
    const a = hm(s.start);
    // travel(P, N): the minutes of the leg between two stops, taken off the stretch between them (completeness)
    const ride = travel && j > 0 ? travel(day.own[j - 1], s) : 0;
    if (a > t) out.push({ from: t, to: a, minutes: Math.max(0, a - t - ride), raw: a - t, at: j });
    t = Math.max(t, hm(s.end));
  });
  if (day.hi > t) out.push({ from: t, to: day.hi, minutes: day.hi - t, at: day.own.length });
  return out;
}

// ------------------------------------------------------------ what the reader likes, read from the data
export const PREF_LABEL = { history: "역사·문화", food: "맛집", islands: "섬·바다", nature: "자연·힐링", alleys: "골목 산책",
  cafe: "카페·빵집", experience: "체험", night: "야경", photo: "사진 명소" };
// the place types (docs.json f.ty, the site's own classes) a liking reads as; islands by the 권역 the page names
export const PREF_TYPES = { history: ["문화유산", "박물관·전시", "골목과 문화", "문화시설"], nature: ["자연·야외"], alleys: ["골목과 문화"],
  experience: ["체험"] };
const ISLANDS = ["고군산", "섬"];
// a café or bakery: a food page with no cuisine type whose menu lines (대표 메뉴·취급 메뉴) name coffee, tea, bread or a
// sweet — TourAPI files cafés under 음식점 like any restaurant (MCL, 이성당, 물밀소's 사워도우, 미제리's 크레마); the code
// never adds one as a meal. 차 is a tea at the end of a word ('대추차', '탱자차'), never '차돌' or '녹차밥'.
const CAFE_MENU = /커피|아메리카노|라떼|에스프레소|콜드브루|카푸치노|크레마|베이커리|빵|케이크|디저트|와플|스콘|크루아상|크로와상|마카롱|빙수|사워도우|바게트|베이글|타르트|호떡|간식|말차|에이드|찻집|차(?![가-힣])/u;
// a meal on an untyped food page's menu: a dish of rice, soup, noodles, grilled or raw fish and meat, a set meal
const MEAL_MENU = /밥|국|탕|면|정식|찌개|구이|회|짜장|짬뽕|돈까스|돈가스|카츠|국수|냉면|덮밥|백반|해장|찜|전골|소바|우동|라멘|피자|파스타|버거|리조또|스테이크|커리|카레|치킨|갈비|불고기|삼겹|곱창|막창|족발|보쌈|샤브|초밥|스시|게장|텐동|수제비/u;

// a food page's menu lines (대표 메뉴·취급 메뉴), each without its source
const menuLines = (doc) => String((doc && doc.x) || "").split("\n").filter((l) => /^- (?:대표|취급) 메뉴/u.test(l)).map((l) => l.split(" — ")[0]);
// each page read once (the planner asks of every place many times a plan)
const CAFE = new WeakMap();
const MEAL = new WeakMap();
const once = (cache, doc, read) => {
  if (!doc || typeof doc !== "object") return read(doc);
  if (!cache.has(doc)) cache.set(doc, read(doc));
  return cache.get(doc);
};
export function isCafe(doc) {
  return once(CAFE, doc, (d) => {
    const f = (d && d.f) || {};
    if (f.kd !== "food" || f.ty) return false;
    return CAFE_MENU.test(menuLines(d).join(" "));
  });
}
/** Whether the code may give a food page as a meal: not a café, and a cuisine type or a menu line that names a meal
 *  (MEAL_MENU) — an untyped page with no menu (a tea house in a temple) or a menu of other things (a brunch's 세트,
 *  샌드위치) says nothing of a meal. */
export function isMeal(doc) {
  return once(MEAL, doc, (d) => {
    const f = (d && d.f) || {};
    if (f.kd !== "food" || isCafe(d)) return false;
    return !!f.ty || menuLines(d).some((l) => MEAL_MENU.test(l));
  });
}
/** Whether a place fits a liking by its data: true, false, or null when the data cannot tell (night views, photo
 *  spots: no field says so). */
export function prefFits(key, doc) {
  const f = (doc && doc.f) || {};
  if (key === "night" || key === "photo") return null;
  if (key === "food") return f.kd === "food" && !isCafe(doc);
  if (key === "cafe") return isCafe(doc);
  if (f.kd !== "attraction") return false;
  if (key === "islands") return ISLANDS.includes(regionOf(doc));
  return (PREF_TYPES[key] || []).includes(f.ty || "");
}
/** Whether the plan holds a liking: a meal for 맛집, a café for 카페·빵집, a stop of the liking's types for the rest;
 *  null for what the data cannot tell. */
export function prefMet(key, plan, kb) {
  if (key === "night" || key === "photo") return null;
  const stops = plan.days.flatMap((d) => d.stops).filter((s) => s.role !== "stay");
  if (key === "food") return stops.some((s) => s.role === "meal");
  if (key === "cafe") return stops.some((s) => s.role === "cafe" || isCafe(kb.docs[s.page]));
  return stops.some((s) => s.role === "visit" && prefFits(key, kb.docs[s.page]));
}

/** The plan read as an itinerary the reader can follow, after the code's repairs: {meals: [{day, kind, state, note?}],
 *  gaps: [{day, from, to, minutes}], prefs: [{key, label, met}], edit?: [{what, state}]}.
 *  meals — each day that spans lunch or dinner (or, on an edit, had one): ok (the plan's own meal), added (the site
 *  added it), skip (the reader eats elsewhere), missing — with a note when a 'meal' in the window is not one (mealIn:
 *  a café or a bakery, or one only touching the window). gaps — the empty stretches left; a day with no stop of its
 *  own (a night's stay alone) is empty from the reader's start to their end. edit — what the plan before
 *  the change had and must keep: its lunch and dinner (kept, restored by the site, dropped as asked, lost) and the
 *  margins at the station or terminal (kept, lost). */
export function completeness(plan, c, kb, edit = null, travel = null) {
  const meals = [];
  const gaps = [];
  const request = edit ? edit.request : "";
  const said = eatsWords(c, edit);
  plan.days.forEach((d, i) => {
    const day = readerDay(plan, c, i, kb);
    if (!day) {
      // no stop of its own (final check 2026-10-18: a day with a night's stay alone passed)
      const lo = hm(c.start) + (i === 0 && c.from ? HUB_MARGIN : 0), hi = hm(c.end) - (i === plan.days.length - 1 && c.to ? HUB_MARGIN : 0);
      if (hi > lo) gaps.push({ day: i, from: hhmm(lo), to: hhmm(hi), minutes: hi - lo });
      return;
    }
    const before = edit && edit.plan.days[i] ? edit.plan.days[i].stops : [];
    for (const kind of ["lunch", "dinner"]) {
      const m = MEALS[kind];
      // (a day before a night's dinner after the reader's end, when it has one: said as any — nightDinner)
      const night = kind === "dinner" && !!mealIn(d.stops, m, kb) && nightDinner(plan, c, i, kb, edit);
      if (!spans(day, m) && !mealIn(before, m, kb) && !night) continue;
      const meal = mealIn(d.stops, m, kb);
      const state = meal ? (meal.by === "site" ? "added" : "ok") : eatsElsewhere(kind, ...said) ? "skip" : "missing";
      // a 'meal' in the window that is not the day's meal says why
      const not = state === "missing" && d.stops.find((s) => s.role === "meal" && hm(s.start) < m.near[1] && hm(s.end) > m.near[0]);
      meals.push({ day: i, kind, state, ...(not ? { note: `${not.name}: ${isCafe(kb.docs[not.page]) ? "카페·빵집이라" : `${m.label} 시간에 걸치기만 해`} 식사로 세지 않음` } : {}) });
    }
    // (decided net of the leg, said whole: '13:00~16:30 3시간 30분')
    for (const g of idleGaps(day, travel)) if (g.minutes > IDLE) gaps.push({ day: i, from: hhmm(g.from), to: hhmm(g.to), minutes: g.raw ?? g.minutes });
  });
  const out = { meals, gaps, prefs: c.prefs.map((key) => ({ key, label: PREF_LABEL[key], met: prefMet(key, plan, kb) })) };
  if (edit) {
    const many = plan.days.length > 1;
    out.edit = [];
    plan.days.forEach((d, i) => {
      const was = (edit.plan.days[i] || { stops: [] }).stops;
      for (const kind of ["lunch", "dinner"]) {
        if (!mealIn(was, MEALS[kind], kb)) continue;
        const now = mealIn(d.stops, MEALS[kind], kb);
        out.edit.push({ what: `${many ? `${i + 1}일차 ` : ""}${MEALS[kind].label}`,
          state: now ? (now.by === "site" ? "restored" : "kept") : eatsElsewhere(kind, request) ? "dropped" : "lost" });
      }
    });
    // the station or terminal: the margin after the start and before the end the plan kept before the change
    const gapAt = (stops, dir) => {
      const own = stops.filter((s) => s.role !== "stay");
      if (!own.length) return null;
      return dir === "from" ? hm(own[0].start) - hm(c.start) : hm(c.end) - Math.max(...own.map((s) => hm(s.end)));
    };
    // (the margin the stop next to the hub now needs: hubMargin, by its 권역)
    const endOf = (stops, dir) => { const own = stops.filter((s) => s.role !== "stay"); return own.length ? (dir === "from" ? own[0] : own.at(-1)) : null; };
    for (const [dir, key, i, at] of [["from", c.from, 0, c.start], ["to", c.to, plan.days.length - 1, c.end]]) {
      if (!key) continue;
      const was = gapAt((edit.plan.days[i] || { stops: [] }).stops, dir), now = gapAt(plan.days[i].stops, dir);
      if (was === null || now === null) continue;
      const end = endOf(plan.days[i].stops, dir);
      out.edit.push({ what: dir === "from" ? `${HUBS[key]} ${at} 출발 뒤 여유` : `${HUBS[key]} ${at} 도착 전 여유`,
        state: now >= Math.min(hubMargin(c, dir, kb.docs[end.page]), was) ? "kept" : "lost" });
    }
  }
  return out;
}
