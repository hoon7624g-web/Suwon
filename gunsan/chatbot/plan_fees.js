// The course planner's admission fees, priced by the code from the site's data — review 2026-10-17 (AI 코스 만들기
// 집중 평가 CE01·CE02·CE03·CE10). The model used to hand over the fees: one plan added the same 박물관 통합권 twice
// (9,000 + 9,000), another left a paid museum out, a third priced three people of four and called the budget kept.
// Now every visit of the plan is priced here, for every person of the party, from what the site has:
//   - a place's own fee value read as a table at build time (docs.json f.fee, pipeline/fee_table.py): free, a
//     visitor's price per category, who enters free (ages, a weekday), the ages of a category when the value says;
//   - the combined tickets (docs.json tickets, data/<region>/tickets.json): the places each opens, its prices and rules.
// Each person at each visit is one of three: paid (a price the data gives for them), free (the data says so), or
// unknown (the data has no price for them — a child's age the table gives no category for, a place with no fee, a
// value that is not a table, a free weekday one source gives and another source's months leave out). A day's
// combined ticket is bought once per person and opens the places it covers that day; the code picks, for each day,
// the way to pay that leaves the fewest people unknown and then costs least, and names in the conditions another way
// that leaves fewer people unknown. The total is a total only when nobody is unknown; the budget is kept only then —
// otherwise 'open' with the known part.
// Meals, cafes and stays are not admissions: the page says so (식비·숙박비는 사이트에 확인된 값이 없음).

import { bornCategory, bornWords } from "./knowledge.js";

const won = (n) => `${n.toLocaleString("en-US")}원`;
const SENIOR_AGE = 65;   // the form's '65세 이상' counter: a rule 'N세 이상' applies when N ≤ 65
const ADULT1 = { key: "adult", label: "어른", kind: "adult", count: 1 };

/** The party as groups of people priced alike: [{key, label, kind: 'adult'|'senior'|'kid', age?, count}]. */
export function partyGroups({ adults = 0, seniors = 0, kids = [] } = {}) {
  const out = [];
  const plain = Math.max(0, adults - seniors);
  if (plain) out.push({ key: "adult", label: "어른", kind: "adult", count: plain });
  if (seniors) out.push({ key: "senior", label: "65세 이상 어른", kind: "senior", count: seniors });
  const byAge = new Map();
  for (const a of kids) byAge.set(a, (byAge.get(a) || 0) + 1);
  for (const [age, count] of [...byAge].sort((x, y) => y[0] - x[0])) {
    out.push({ key: `kid${age}`, label: `아이 ${age}살`, kind: "kid", age, count });
  }
  return out;
}

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

/** Whether a day (month, year) is in the months a text gives ('4~12월', '2026년 4~12월'): null when it gives none;
 *  false in another year than the one it names (review 2026-10-22: '2026년 4~12월' was read for January 2027 too). */
const monthIn = (text, month, year) => {
  const m = /(?:(20\d\d)\s*년\s*)?(1[0-2]|[1-9])\s*월?\s*~\s*(1[0-2]|[1-9])\s*월/u.exec(text || "");
  if (!m) return null;
  const x = +m[2], y = +m[3];
  const inYear = (yy) => !m[1] || yy === +m[1];
  return x <= y ? month >= x && month <= y && inYear(year)
    : (month >= x && inYear(year)) || (month <= y && inYear(year - 1));
};

/** One group at one place, by the place's own table: {status, won?, basis} — status 'paid' | 'free' | 'unknown'. */
function placePrice(fee, g, date) {
  if (!fee || (!fee.free && !fee.tab)) {
    return { status: "unknown", basis: fee && fee.t ? `요금 값이 표가 아님('${fee.t.slice(0, 40)}')` : "사이트에 요금 정보 없음" };
  }
  if (fee.free) return { status: "free", basis: `무료${fee.note ? ` (${fee.note})` : ""}` };
  const day = new Date(`${date}T12:00:00Z`);
  const wd = day.getUTCDay(), month = day.getUTCMonth() + 1, year = day.getUTCFullYear();
  let wdOpen = "";   // a weekday's free entry one source gives for this day and another source's months leave out
  for (const r of fee.fr || []) {
    if (r.wd === undefined || r.wd !== wd) continue;
    const own = monthIn(r.w, month, year);
    if (own === false) continue;   // the rule's own months leave this day out
    // '2026년 4~12월 매주 수요일 무료 관람' written by another source about the same weekday: free when both sources
    // say so; outside its months the sources differ, and the day is neither free nor the table's price for sure (3.2)
    const dated = (fee.alt || []).filter((a) => a.t.includes(`${WEEKDAY[wd]}요일`))
      .map((a) => ({ a, v: monthIn(a.t, month, year) })).find((x) => x.v !== null) ?? null;
    if (!dated) return { status: "free", basis: `${r.w}${own === null ? "" : ` (${year}년 ${month}월)`}` };
    const both = `${fee.p} '${r.w}' / ${dated.a.p} '${dated.a.t}'`;
    if (dated.v) return { status: "free", basis: `${both} — 두 출처 모두 이날 무료` };
    wdOpen = `무료 관람일인지 출처마다 다름: ${both}`;
  }
  // not free that day by one source only: the age rules still apply; a price is the most it costs (hi), not a total
  const either = (n, what) => (n === undefined ? { status: "unknown", basis: `${wdOpen} — 방문 전 전화 확인` }
    : { status: "unknown", hi: n, basis: `${wdOpen} — 무료가 아니면 ${what} ${won(n)}, 방문 전 전화 확인` });
  if (g.kind === "kid") {
    const freeAge = (fee.fr || []).find((r) => r.max !== undefined && g.age <= r.max);
    if (freeAge) return { status: "free", basis: `무료 '${freeAge.w}'` };
    const cat = Object.entries(fee.ag || {}).find(([, [a, b]]) => g.age >= a && g.age <= b);
    if (cat && fee.tab[cat[0]] !== undefined) {
      const what = `요금표 '${cat[0]}(${cat[1][0]}~${cat[1][1]}세)'`;
      return wdOpen ? either(fee.tab[cat[0]], what) : { status: "paid", won: fee.tab[cat[0]], basis: what };
    }
    return { status: "unknown", basis: `${g.age}살이 어느 요금 구분인지 요금표에 나이 기준이 없음` };
  }
  if (g.kind === "senior") {
    const freeOld = (fee.fr || []).find((r) => r.min !== undefined && r.min <= SENIOR_AGE);
    if (freeOld) return { status: "free", basis: `무료 '${freeOld.w}'` };
    return { status: "unknown", basis: "65세 이상 요금(경로 할인·무료)이 요금표에 없음" };
  }
  const what = `요금표 '성인'${fee.tl ? ` (${fee.tl})` : ""}`;
  return wdOpen ? either(fee.tab["성인"], what) : { status: "paid", won: fee.tab["성인"], basis: what };
}

/** One group with a combined ticket on `date`: the ticket's own prices (개인, 군산시민 아님) and its own rules only. A
 *  child's category comes from the table's ages and its birth years (that year's table only); when they do not give
 *  one category — two sources apart, or a birthday deciding — the child is unknown, with both readings. */
function ticketPrice(t, g, date) {
  const rules = t.rules || [];
  const table = (t.prices || {})["개인"] || {};
  if (g.kind === "kid") {
    const freeAge = rules.find((r) => r.kind === "free" && r.age_max !== undefined && g.age <= r.age_max);
    if (freeAge) return { status: "free", basis: `무료 '${freeAge.who}' (${freeAge.src})` };
    const year = +String(date || "").slice(0, 4);
    const reads = rules.filter((r) => r.kind === "age" && g.age >= r.from && g.age <= r.to)
      .map((r) => ({ cat: r.category, what: `'${r.text}' (${r.src})` }));
    const born = bornCategory(rules, g.age, year);
    if (born && born.rule) reads.push({ cat: born.rule.category, what: `'${born.rule.category} ${born.rule.text}' (${born.rule.src})` });
    if (born && born.split) return { status: "unknown", basis: bornWords(born, g.age, year) };
    const cats = new Set(reads.map((x) => x.cat));
    if (cats.size > 1) return { status: "unknown", basis: `요금 구분이 출처마다 다름: ${reads.map((x) => x.what).join(" / ")} — 방문 전 확인` };
    if (cats.size === 1 && table[reads[0].cat]) {
      return { status: "paid", won: table[reads[0].cat][0], basis: `요금표 ${reads.map((x) => x.what).join(" · ")}` };
    }
    if (born && (born.stale || born.none)) return { status: "unknown", basis: bornWords(born, g.age, year) };
    return { status: "unknown", basis: `${g.age}살이 어느 요금 구분인지 이 통합권 요금표에 나이 기준이 없음` };
  }
  if (g.kind === "senior") {
    const freeOld = rules.find((r) => r.kind === "free" && r.age_min !== undefined && r.age_min <= SENIOR_AGE);
    if (freeOld) return { status: "free", basis: `무료 '${freeOld.who}' (${freeOld.src})` };
    return { status: "unknown", basis: "65세 이상 요금(경로 할인·무료)이 이 통합권 요금표에 없음" };
  }
  return table["성인"] ? { status: "paid", won: table["성인"][0], basis: "요금표 '성인'" }
    : { status: "unknown", basis: "이 통합권 요금표에 성인 요금이 없음" };
}

/** A day priced one way: tickets (ids, may be empty) and every other visit one by one. */
function priceDay(day, groups, kb, use) {
  const lines = [];
  const per = [];   // per visit: {i, path, name, how: 'own' | ticket id | 'again', states: {status: count}}
  const covered = new Map();   // path → ticket id
  for (const id of use) {
    const t = kb.tickets.find((x) => x.id === id);
    const paths = new Set(t.places.map((p) => p.path));
    const visits = day.stops.filter((s) => paths.has(s.page));
    if (!visits.length) return null;
    for (const s of visits) if (!covered.has(s.page)) covered.set(s.page, id);
    const names = [...new Set(visits.map((s) => s.name))];
    for (const g of groups) {
      const p = ticketPrice(t, g, day.date);
      lines.push({ what: `${t.name} — ${names.join("·")}`, ticket: t.id, who: g.label, count: g.count, ...p,
        sub: p.status === "paid" ? p.won * g.count : 0, src: t.src });
    }
  }
  const seen = new Set();
  day.stops.forEach((s, i) => {
    if (s.role !== "visit") return;
    if (seen.has(s.page)) {
      per.push({ i, path: s.page, name: s.name, how: "again" });
      return;
    }
    seen.add(s.page);
    if (covered.has(s.page)) {
      per.push({ i, path: s.page, name: s.name, how: covered.get(s.page) });
      return;
    }
    const doc = kb.docs[s.page] || {};
    const fee = (doc.f || {}).fee;
    const states = {};
    for (const g of groups) {
      const p = placePrice(fee, g, day.date);
      states[p.status] = (states[p.status] || 0) + g.count;
      lines.push({ what: s.name, path: s.page, who: g.label, count: g.count, ...p, sub: p.status === "paid" ? p.won * g.count : 0,
        src: fee && fee.p ? fee.p : "" });
    }
    per.push({ i, path: s.page, name: s.name, how: "own", states, tickets: kb.tickets.filter((t) => t.places.some((p) => p.path === s.page)).map((t) => t.name) });
  });
  const unknown = lines.filter((l) => l.status === "unknown").reduce((a, l) => a + l.count, 0);
  const known = lines.reduce((a, l) => a + l.sub, 0);
  // open: people with no price at all; most: the known part plus, for people whose price may be 0 (hi), that price
  const open = lines.filter((l) => l.status === "unknown" && l.hi === undefined).reduce((a, l) => a + l.count, 0);
  const most = known + lines.filter((l) => l.hi !== undefined).reduce((a, l) => a + l.hi * l.count, 0);
  return { lines, per, unknown, known, use, open, most };
}

const noUrl = (text) => text.replace(/\s*https?:\/\/\S+/gu, "");

// an adult's price another source writes in its own words ('어른 3,000원', '- 성인 3,000원(500원)'), outside a part
// headed for groups or residents ('[단체]', '[영주시민/단체]'): the number, or null
const ADULT_WON = /(?:성인|어른|일반|대인)\s*(?:\([^)]{0,12}\))?\s*[:：]?\s*(\d{1,3}(?:,\d{3})+|\d+)\s*원/u;
function adultWon(text) {
  const parts = String(text || "").split(/\[([^\]]{1,40})\]/u);
  for (let i = 0; i < parts.length; i += 2) {
    if (i && /단체|시민|거주자/u.test(parts[i - 1])) continue;
    const m = ADULT_WON.exec(parts[i]);
    if (m) return Number(m[1].replace(/,/gu, ""));
  }
  return null;
}
/** The sources that disagree on what an adult pays for a day's visits as priced (YJ-04, 2026-10-24: 영주 소수서원 —
 *  한국관광공사 TourAPI 성인 2,000원, 영주시 문화관광 '어른 3,000원 (소수서원·선비촌·소수박물관 통합 관람권)' — was priced
 *  2,000원 as certain, a budget of 10,000원 'within'): a combined ticket with another ticket for the same places whose
 *  adult price differs, a place priced by its own table whose other source (fee.alt, never an added value) writes
 *  another adult price, and a place a ticket opens whose other source writes a combined price other than the ticket's.
 *  {lines: [text] — each said with both values and the phone check (CLAUDE.md 3절 2항), lower: whether a value the day
 *  was not priced by may cost less (a lower price, or a combined ticket that may open the day's other places too: the
 *  known sum is then no floor — a budget 'over' is not certain)}. `said` gets each other-source value said here
 *  (path + its text), so the conditions list does not drop one no line says (a party with no adult under 65). */
function disputes(best, kb, said = new Set()) {
  const out = [];
  let lower = false;
  const same = (a, b) => a.places.length === b.places.length && a.places.every((p) => b.places.some((q) => q.path === p.path));
  const adultOf = (t) => (((t.prices || {})["개인"] || {})["성인"] || [])[0];
  const srcOf = (t) => noUrl(String(t.src || "")).replace(/\s*\(출처 확인[^)]*\)/u, "");
  // (only where an adult of the party pays by that price: a party of children and 65+ is priced by other rows)
  const adultPays = (pred) => best.lines.some((l) => pred(l) && l.who === "어른" && l.status === "paid");
  for (const id of best.use) {
    const t = kb.tickets.find((x) => x.id === id);
    if (!adultPays((l) => l.ticket === id)) continue;
    for (const o of kb.tickets.filter((x) => x !== t && same(x, t) && adultOf(x) !== undefined && adultOf(x) !== adultOf(t))) {
      if (adultOf(o) < adultOf(t)) lower = true;
      out.push(`${t.name}: 출처마다 성인 요금이 다름 — ${srcOf(t)} ${won(adultOf(t))} / ${srcOf(o)} ${won(adultOf(o))} — 방문 전 전화 확인`);
    }
  }
  for (const p of best.per.filter((x) => x.how !== "again")) {
    const fee = ((kb.docs[p.path] || {}).f || {}).fee || {};
    const t = p.how === "own" ? null : kb.tickets.find((x) => x.id === p.how);
    const mine = t ? adultOf(t) : (fee.tab || {})["성인"];
    if (mine === undefined || fee.free || !adultPays((l) => (t ? l.ticket === t.id : l.path === p.path))) continue;
    for (const a of (fee.alt || []).filter((x) => !x.a)) {
      const v = adultWon(a.t);
      // (a place a ticket opens: only another source's combined price is the ticket's to compare)
      if (v === null || v === mine || (t && !/통합/u.test(a.t))) continue;
      if (v < mine || (/통합/u.test(a.t) && best.per.some((q) => q.path !== p.path && q.how !== "again"))) lower = true;
      said.add(`${p.path}\n${a.t}`);
      out.push(`${p.name}: 출처마다 성인 요금이 다름 — ${t ? `${t.name} ${srcOf(t)}` : fee.p || "자료"} ${won(mine)} / ${a.p} ${won(v)} — 방문 전 전화 확인`);
    }
  }
  return { lines: [...new Set(out)], lower };
}

/** One condition line when another way to pay that day leaves fewer people 확인 필요 than the chosen one and can cost
 *  less (review 2026-10-22: two 65+ visitors at 근대역사박물관 — its own table has no 65+ rule, the 박물관 통합권's
 *  source makes them free): that way, what it gives the people left unknown, and its total. Never applied by itself. */
function otherWay(priced, best, kb) {
  if (!best.unknown) return "";
  const x = priced.map((p) => p.full).filter((f) => f !== best && f.unknown < best.unknown && (best.open > 0 || f.known < best.most))
    .sort((a, b) => a.unknown - b.unknown || a.known - b.known)[0];
  if (!x) return "";
  const left = new Set(best.lines.filter((l) => l.status === "unknown").map((l) => l.who));
  const gives = [...new Set(x.lines.filter((l) => left.has(l.who) && l.status !== "unknown")
    .map((l) => `${l.who} ${l.count}명 ${won(l.sub)}(${noUrl(l.basis)})`))];
  const how = x.use.length ? `${x.use.map((id) => kb.tickets.find((t) => t.id === id).name).join("·")}으로 사면` : "장소마다 따로 사면";
  const still = x.lines.filter((l) => l.status === "unknown").length;
  return `${how}${gives.length ? ` ${gives.join(", ")}` : ""} — ${still ? `확인된 입장료 ${won(x.known)} + 확인 필요 ${still}건` : `합계 ${won(x.known)}`}`;
}

/** The plan's admission fees: {days: [{date, lines, per}], open: [text], conds: [text], total, known, state, limit,
 *  verdict, text}. days = [{date, stops: [{page (a doc key), name, role}]}]; party = {adults, seniors, kids};
 *  limit = the reader's budget (null: none). */
export function planFees(days, party, kb, limit = null) {
  const groups = partyGroups(party);
  const out = { days: [], open: [], conds: [], total: null, known: 0, state: "none", limit, verdict: "none" };
  let visits = 0;
  let unknown = 0;
  let paid = 0;
  const others = [];
  const said = new Set();   // the other sources' values a dispute line says (disputes)
  let lower = false;        // a disputed value may cost less than the day was priced by: no 'over' (disputes)
  for (const [i, day] of days.entries()) {
    visits += day.stops.filter((s) => s.role === "visit").length;
    const options = [[]];
    for (const t of kb.tickets) {
      if (day.stops.some((s) => s.role === "visit" && t.places.some((p) => p.path === s.page))) options.push([t.id]);
    }
    // the way to pay is chosen as for one adult (every table has an adult's price, a child's often has no ages): the
    // fewest visits with no adult price, then the cheapest for an adult (at most: a price one source may waive), then
    // the fewest people unknown — so a ticket whose table happens to name children's ages is never picked over a
    // cheaper one only for that. A party with no adult under 65 is priced as one 65+ adult first (review 2026-10-22:
    // two 65+ visitors were priced by an adult who was not there, and the 통합권 whose source makes them free lost),
    // the adult's order still deciding between ways that leave the 65+ adult alike (a 65+ adult free either way with
    // a 9-year-old: no 금강권 통합권 3,000원 only for the child's ages)
    const old = !groups.some((g) => g.kind === "adult") && groups.find((g) => g.kind === "senior");
    const priced = options.map((use) => ({ full: priceDay(day, groups, kb, use), adult: priceDay(day, [ADULT1], kb, use),
      senior: old ? priceDay(day, [{ ...old, count: 1 }], kb, use) : null })).filter((x) => x.full);
    const order = (x) => [...(x.senior ? [x.senior.open, x.senior.most] : []), x.adult.open, x.adult.most, x.full.unknown,
      x.full.use.length];
    priced.sort((a, b) => {
      const p = order(a), q = order(b), k = p.findIndex((v, j) => v !== q[j]);
      return k < 0 ? 0 : p[k] - q[k];
    });
    const best = priced[0].full;
    const other = otherWay(priced, best, kb);
    if (other) others.push(`${days.length > 1 ? `${i + 1}일차 ` : ""}${other}`);
    out.days.push({ date: day.date, lines: best.lines, per: best.per });
    out.known += best.known;
    unknown += best.unknown;
    paid += best.lines.filter((l) => l.status === "paid").length;
    for (const l of best.lines.filter((x) => x.status === "unknown")) out.open.push(`${l.what}: ${l.who} ${l.count}명 — ${l.basis}`);
    // (sources that disagree on a price: no total is certain — each is one more thing to check)
    const apart = disputes(best, kb, said);
    unknown += apart.lines.length;
    lower = lower || apart.lower;
    out.open.push(...apart.lines.map((t) => (days.length > 1 ? `${i + 1}일차 ${t}` : t)));
  }
  const rules = new Set();
  for (const d of out.days) {
    for (const p of d.per.filter((x) => x.how === "own")) {
      const fee = ((kb.docs[p.path] || {}).f || {}).fee || {};
      for (const r of (fee.fr || []).filter((x) => /장애인|유공자/u.test(x.w))) rules.add(`${p.name}: ${r.w} 무료(증빙 필요) — 해당하면 줄어듦`);
      // (an added value, a:1 — e.g. a notice's months for a free weekday — does not contradict the fee: not a condition)
      // (one a dispute line says is in out.open — disputes; any other stays a condition, its adult price differing or not)
      for (const a of (fee.alt || []).filter((x) => !x.a && !said.has(`${p.path}\n${x.t}`))) {
        rules.add(`${p.name}: 다른 출처의 요금 값 '${a.t.slice(0, 60)}'(${a.p}) — 방문 전 확인`);
      }
    }
    for (const id of new Set(d.per.map((x) => x.how).filter((h) => h !== "own" && h !== "again"))) {
      const t = kb.tickets.find((x) => x.id === id);
      for (const r of (t.rules || []).filter((x) => x.kind === "free" && x.age_max === undefined && x.age_min === undefined)) {
        rules.add(`${t.name}: ${r.who} 무료(증빙 필요) — 해당하면 줄어듦`);
      }
      for (const r of (t.rules || []).filter((x) => x.kind === "note")) rules.add(`${t.name}: ${r.text}`);
    }
  }
  out.conds = [...others, ...rules];
  if (!visits) {
    out.state = "none";
  } else if (unknown) {
    out.state = paid || out.known ? "partial" : "unknown";
  } else {
    out.total = out.known;
    out.state = out.known ? "known" : "free";
  }
  if (limit !== null && limit !== undefined) {
    // (over: what is known already passes the budget — unless a source the day was not priced by may cost less)
    if (out.known > limit && !lower) out.verdict = "over";
    else if (out.total !== null) out.verdict = "within";
    else if (out.state === "none") out.verdict = "within";
    else out.verdict = "open";
  }
  const T = [];
  for (const [i, d] of out.days.entries()) {
    for (const l of d.lines) {
      T.push(`${days.length > 1 ? `${i + 1}일차 ` : ""}${l.what} · ${l.who} ${l.count}명: ${l.status === "paid" ? `${won(l.won)} × ${l.count} = ${won(l.sub)}`
        : l.status === "free" ? "0원" : "확인 필요"} (${l.basis})`);
    }
  }
  T.push(out.state === "none" ? "입장료를 내는 방문지가 없다(식사·카페·숙소는 입장료 계산에 넣지 않는다)"
    : out.total !== null ? `입장료 합계 ${won(out.total)}` : `확인된 입장료 ${won(out.known)} + 확인 필요 ${out.open.length}건(합계 확정 안 됨)`);
  out.text = T.join("\n");
  return out;
}
