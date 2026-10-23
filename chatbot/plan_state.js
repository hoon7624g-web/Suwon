// What a checked plan states about itself — the first city's review 2026-10-17 (AI 코스 만들기 집중 평가 CE05·CE06, R09·R13): the
// result said '휴무·운영시간 확인 6/6곳 · 걸리는 것 없음' above a list that left two places' New Year's Day unconfirmed,
// and a summary said a wheelchair route was confirmed where the list below did not know. The code now writes every
// such statement itself, from the site's data, and the model's words carry none of them:
//   - needsTable: each need the reader picked, at each stop — the data's own words, and one of ok (the data says it
//     fits), near (parking: none of its own, a public lot close by), no (the data says it does not), unknown;
//   - checksList: everything the reader is to check before going, one line each, by kind;
//   - grounded: a number in the model's sentences that the place pages do not have, and words that claim a check;
//   - status: 'ready' (nothing flagged, nothing to check), 'check' (nothing flagged, things to check), 'unmet'
//     (flags left after the fix the model had).

export const NEED_LABEL = { rain: "실내", stroller: "유모차", wheelchair: "휠체어", parking: "주차", free: "입장료", lesswalk: "걷기" };
// needs a stop must meet when the data says it does not (a plan with one is sent back for its fix, then 'unmet'), and
// the '위주' needs (비 와도 실내 위주, 입장료 없는 곳 위주) that allow one stop a day the data says does not fit
// (operator 2026-10-18: a plan showed '맞지 않음 1' under '확인할 것이 남은 초안' — the mismatch was never sent back)
export const HARD_NEEDS = ["wheelchair", "stroller", "parking"];
export const SOFT_NEEDS = ["rain", "free"];
const INDOOR = /박물관|전시|문화시설|미술관/u;
const OUTDOOR = /자연·야외|레포츠/u;
const ROUTE_OK = /턱이\s*없|단차가?\s*없|경사로|휠체어\s*접근\s*가능|평지/u;
const ROUTE_NO = /계단만|접근\s*불가|턱이\s*있/u;
const RENT = /대여\s*가능/u;

const access = (f, key) => (f.ac || []).filter((a) => a.k === key);

/** One stop against one need: {state, text}. role: the stop's role in the plan; fee: plan_fees per-visit entry. */
export function needAt(need, f, role, fee) {
  if (need === "rain") {
    if (role !== "visit" || f.kd === "food" || f.kd === "stay") return { state: "ok", text: "실내(음식점·숙소)" };
    if (INDOOR.test(f.ty || "")) return { state: "ok", text: `실내(${f.ty})` };
    if (OUTDOOR.test(f.ty || "")) return { state: "no", text: `야외(${f.ty})` };
    return { state: "unknown", text: `실내인지 자료 없음${f.ty ? `(${f.ty})` : ""}` };
  }
  if (need === "stroller" || need === "wheelchair") {
    const route = access(f, "accessible_route");
    const extra = need === "wheelchair"
      ? [...access(f, "wheelchair").filter((a) => RENT.test(a.t)).map((a) => `휠체어 ${a.t}`),
        ...access(f, "accessible_toilet").filter((a) => a.t !== "없음").map((a) => a.t)]
      : access(f, "babycarriage").filter((a) => RENT.test(a.t)).map((a) => `유모차 ${a.t}`);
    const tail = extra.length ? ` · ${extra.join(" · ")}` : "";
    if (route.some((a) => ROUTE_OK.test(a.t))) return { state: "ok", text: `출입구: ${route.find((a) => ROUTE_OK.test(a.t)).t}${tail}` };
    if (route.some((a) => ROUTE_NO.test(a.t))) return { state: "no", text: `출입구: ${route[0].t}${tail}` };
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

/** {key, label, rows: [{day, i, name, state, text, allowed?}]} for each need but lesswalk (no data reads walking). A
 *  '위주' need's one stop a day the data says does not fit is `allowed` (two or more that day: none is). */
export function needsTable(plan, c, kb, fees) {
  return c.needs.filter((n) => n !== "lesswalk").map((need) => {
    const rows = plan.days.flatMap((d, di) => d.stops.map((s, i) => {
      const f = ((kb.docs[s.page] || {}).f) || {};
      const fee = ((fees.days[di] || {}).per || []).find((p) => p.i === i);
      return { day: di, i, name: s.name, ...needAt(need, f, s.role, fee) };
    }));
    if (SOFT_NEEDS.includes(need)) {
      plan.days.forEach((d, di) => {
        const no = rows.filter((r) => r.day === di && r.state === "no");
        if (no.length === 1) no[0].allowed = true;
      });
    }
    return { key: need, label: NEED_LABEL[need], rows };
  });
}

/** The stops the data says break a need (HARD_NEEDS: any; SOFT_NEEDS: two or more in a day): [{need, day, rows}]. */
export function needMisses(needs) {
  const out = [];
  for (const n of needs) {
    const no = n.rows.filter((r) => r.state === "no" && !r.allowed);
    if (!no.length) continue;
    if (HARD_NEEDS.includes(n.key)) for (const r of no) out.push({ need: n.key, day: r.day, rows: [r] });
    else for (const day of [...new Set(no.map((r) => r.day))]) out.push({ need: n.key, day, rows: no.filter((r) => r.day === day) });
  }
  return out;
}

/** Everything to check before going, from the code's own checks: [{k, t}] — k: day, hub, fee, need, stay, move. */
export function checksList(plan, c, check, needs, fees, hubs, kb) {
  const out = [];
  const many = plan.days.length > 1;
  plan.days.forEach((d, di) => {
    const r = check.days[di];
    d.stops.forEach((s, i) => {
      const st = r.stops[i] || {};
      for (const t of st.checks || []) out.push({ k: "day", t: `${many ? `${di + 1}일차 ` : ""}${s.name}: ${t}` });
      if (s.role === "stay") {
        const ci = (((kb.docs[s.page] || {}).f) || {}).ci;
        out.push({ k: "stay", t: `${s.name}: ${ci ? `체크인 ${ci}(사이트 값)` : "체크인 시각이 사이트에 없음"} — 객실·예약은 숙소에 확인` });
      }
    });
  });
  for (const t of fees.open) out.push({ k: "fee", t: `입장료 ${t}` });
  for (const n of needs) {
    for (const row of n.rows.filter((x) => x.state === "unknown" || x.state === "no")) {
      out.push({ k: "need", t: `${n.label}: ${many ? `${row.day + 1}일차 ` : ""}${row.name} — ${row.text}${row.allowed ? " (‘위주’ 조건이라 하루 한 곳까지 둔 곳)" : ""}` });
    }
  }
  if (c.needs.includes("lesswalk")) out.push({ k: "need", t: "걷기: 걷는 거리는 사이트 자료로 잴 수 없음 — 구간 직선거리를 참고" });
  for (const h of hubs) out.push({ k: "hub", t: `${h.dir === "from" ? `${h.name} → ${h.stop}` : `${h.stop} → ${h.name}`}: 이동 시간·거리는 사이트에 없음 — 지도 앱으로 확인` });
  if (plan.days.some((d) => d.stops.length > 1)) out.push({ k: "move", t: "장소 사이 시간은 계획상 여유이고, 실제 이동 시간은 확인되지 않음(직선거리만 있음)" });
  return out;
}

const NUM = /\d[\d,]*(?:\.\d+)?/gu;
const CLAIM = /확인(?:된|됐|했|되었|됨|해\s*두)|보장|문제\s*없|걸리는\s*것\s*없|모두\s*(?:가능|열)/u;

/** The numbers of `text` (100 and up: years, prices, counts of rooms, distances in metres) that `source` does not
 *  have, and whether it claims a check. Numbers under 100 (people, ages, hours, minutes, days) are not read. */
export function grounded(text, source) {
  const src = String(source || "").replace(/(\d),(?=\d{3})/gu, "$1");
  const bad = [];
  for (const [raw] of String(text || "").matchAll(NUM)) {
    const n = raw.replace(/,/gu, "").replace(/\.$/u, "");
    if (Number(n) < 100) continue;
    if (!new RegExp(`(?<![\\d.])${n.replace(".", "\\.")}(?![\\d])`, "u").test(src)) bad.push(raw);
  }
  return { bad, claim: CLAIM.test(String(text || "")) };
}

/** The sentences of a text without the ones a test rejects. */
export function dropSentences(text, keep) {
  return String(text || "").split(/(?<=[.!?。])\s+/u).filter((s) => s && keep(s)).join(" ").trim();
}

export function statusOf(flags, checks) {
  return flags.length ? "unmet" : checks.length ? "check" : "ready";
}
