// The site assistant's knowledge: the files pipeline/chat_index.py writes under public/chat/ (catalog.txt — the core
// catalog the cached prompt holds: every page, places as a directory —, lines.json — every place's and article's full
// catalog line, of which relevantLines and planLines pick the ones a question or a trip most likely needs —, docs.json,
// index.json), and what the two tools do with them — search_site (token match over every page),
// get_pages (the full text of up to six pages) — plus the check of every link an answer carries (fixLinks): a link
// to this site must name a page that exists (and is turned into the reader's language version when there is one),
// an outside link must be an address the site's data itself links to, a phone link must be a phone number.
//
// Page paths, ids, queries and addresses come from the model (and so, indirectly, from the user): they are only ever
// looked up in the loaded maps — which have no prototype, so 'constructor' or '__proto__' is simply not a page — and
// matched with fixed patterns; never used as a file path or turned into a RegExp. The files are read once, by name.
//
// The city's values — the public address, the site's and region's names, the assistant's name, the extra origins,
// the short phone numbers the site lists, the course planner's hubs, likes and travel areas — are docs.json `meta`
// (pipeline/chat_index.py chat_meta, pipeline/plan.py plan_meta, from site.json): nothing of a city is written here.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { city, readPlan, useCity } from "./city.js";
import { OUTSIDE_WORDS, isCafe, isMeal, isOutside, needAt, outsideSrc, prefFits, rainShut } from "./plan_state.js";

const table = (obj) => Object.assign(Object.create(null), obj && typeof obj === "object" ? obj : {});
/** The dates of a trip of `days` days from `date` (plan_prompt.tripDates — written here too: prompt.js reads this
 *  module's KINDS, so this one does not import the planner's prompt). */
const tripDates = (date, days) => [...Array(days)].map((_, i) => new Date(Date.parse(`${date}T12:00:00Z`) + i * 86400000).toISOString().slice(0, 10));
const ORIGIN = /^https:\/\/[a-z0-9-]+(\.[a-z0-9-]+)+$/;

/** docs.json meta, checked: {site, siteName, siteNameEn, region {lang: name}, assistant {lang: name}, origins [https
 *  origins], tel [short numbers], plan (city.js readPlan: the course planner's city values, pipeline/plan.py
 *  plan_meta)}. Missing values are empty, never another city's. */
export function readMeta(meta, site = "") {
  const m = meta && typeof meta === "object" ? meta : {};
  const words = (o) => Object.fromEntries(Object.entries(o && typeof o === "object" ? o : {})
    .filter(([k, v]) => typeof k === "string" && typeof v === "string" && v.trim()).map(([k, v]) => [k, v.trim()]));
  const s = String((typeof m.site === "string" && m.site) || site || "").trim().replace(/\/+$/, "");
  return {
    site: s,
    siteName: typeof m.site_name === "string" ? m.site_name.trim() : "",
    siteNameEn: typeof m.site_name_en === "string" ? m.site_name_en.trim() : "",
    region: words(m.region),
    assistant: words(m.assistant),
    origins: (Array.isArray(m.origins) ? m.origins : []).filter((o) => typeof o === "string" && ORIGIN.test(o)),
    tel: (Array.isArray(m.tel) ? m.tel : []).filter((t) => typeof t === "string" && /^\+?\d{3,15}$/.test(t)),
    plan: readPlan(m.plan),
  };
}

// tokens(): pipeline/chat_index.py tokens() for queries — Hangul / kana / CJK runs as bigrams (one syllable alone as
// itself), Latin, Cyrillic and digit runs as words (one-letter Latin words dropped), NFKC, lower case. Keep in step.
const TOKEN_RX = /[가-힣]+|[\u3040-\u30ff\u3400-\u9fff]+|[a-z0-9\u00c0-\u024f\u0400-\u04ff]+/gu;
const WIDE_START = 0x3040;

export function tokens(text) {
  const t = String(text ?? "").normalize("NFKC").toLowerCase();
  const out = [];
  const seen = new Set();
  for (const [run] of t.matchAll(TOKEN_RX)) {
    let grams;
    if (run.codePointAt(0) >= WIDE_START) {
      const chars = [...run];
      grams = chars.length === 1 ? [run] : chars.slice(0, -1).map((c, i) => c + chars[i + 1]);
    } else {
      grams = run.length > 1 || /^\d+$/.test(run) ? [run] : [];
    }
    for (const g of grams) {
      if (!seen.has(g)) {
        seen.add(g);
        out.push(g);
      }
    }
  }
  return out;
}

/** pipeline/chat_index.py estimate_tokens: a deliberately high, tokenizer-free estimate — every code point above 127
 *  (a Hangul syllable, kana, a CJK character, any other non-ASCII letter) 1, ASCII 1 per 2.5 characters, rounded up.
 *  The budgets below are counted with it. Keep in step. */
export function estimateTokens(text) {
  let wide = 0;
  let all = 0;
  for (const ch of String(text ?? "")) {
    all += 1;
    if (ch.codePointAt(0) > 127) wide += 1;
  }
  return Math.ceil(wide + (all - wide) / 2.5);
}

// The prompt's site data in three parts (operator 2026-10-23: catalog diet, a higher ceiling, only the part a question
// needs): the core catalog — rules and catalog.txt, cached, the same bytes for every request —, the lines block — the
// full lines of the places and articles this question (relevantLines) or this trip (planLines) most likely needs,
// cached for the later calls of the same question —, and the uncached context. Estimated tokens (estimateTokens):
// CORE_BUDGET is pipeline/chat_index.py's for catalog.txt; LINES_BUDGET its ceiling for all of lines.json (the whole
// catalog, never sent whole); a question's lines block holds at most SLICE_TOKENS, a trip's PLAN_SLICE_TOKENS — so the
// cached prefix stays far below the 100K-token price tier (RULES + CORE_BUDGET + SLICE_TOKENS <= PREFIX_BUDGET).
export const CORE_BUDGET = 32_000;
export const LINES_BUDGET = 600_000;
export const SLICE_TOKENS = 12_000;
export const PLAN_SLICE_TOKENS = 20_000;
export const PREFIX_BUDGET = 56_000;

const KIND_LABEL = { place: "장소", guide: "가이드", section: "가이드 본문", course: "코스", event: "행사", video: "영상", page: "페이지",
  abroad: "해외 기사·SNS" };
// a video title matches many words, a guide section repeats its guide: both rank a little below a page of their own
const KIND_WEIGHT = { place: 1, guide: 1, course: 1, event: 1, page: 0.95, section: 0.85, video: 0.6, abroad: 0.6 };
const KIND_FILTER = { place: ["place"], guide: ["guide", "section"], course: ["course"], event: ["event"], video: ["video"],
  abroad: ["abroad"], page: ["page"] };
export const KINDS = ["any", ...Object.keys(KIND_FILTER)];
export const PAGE_LIMIT = 6;       // pages per get_pages call
export const DOC_CHARS = 6000;     // characters of one page in a get_pages result
export const SNIPPET_CHARS = 150;
export const QUERY_CHARS = 200;    // a search query is read up to this length (server.js refuses longer tool input)
export const NAMES_CHARS = 800;    // the line naming, in the answer's language, the places a tool result mentions
const NAMES_MAX = 20;

function decode(s) {
  try {
    return decodeURI(s);
  } catch {
    return s;
  }
}

function normUrl(u) {
  // outside addresses compare without the scheme's case, a trailing slash, a 'www.' or a '#fragment' (the same page);
  // the link itself is always the address exactly as the data has it
  return String(u).trim().replace(/#.*$/, "").replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/+$/, "")
    .toLowerCase();
}

/** A person's fee category by a combined ticket's birth-year rules (tickets.json kind 'born', each the table of its
 *  source's year): someone `age` in `year` was born in year − age − 1 or year − age, and both years must fall in one
 *  category. {rule} — that category; {split: [[birth year, rule | null], …]} — the birthday decides; {stale: the
 *  table's year} — a visit in another year than the table's; {none: true} — neither year is in the table; null — the
 *  ticket has no such rule or no age is given. */
export function bornCategory(rules, age, year) {
  const born = (rules || []).filter((r) => r && r.kind === "born");
  if (!born.length || !Number.isInteger(age) || !Number.isInteger(year)) return null;
  const now = born.filter((r) => r.year === year);
  if (!now.length) return { stale: born[0].year };
  const two = [year - age - 1, year - age].map((y) => [y, now.find((r) => y >= r.from && y <= r.to) || null]);
  const [a, b] = two.map((x) => x[1]);
  if (a && b && a.category === b.category) return { rule: a };
  if (!a && !b) return { none: true };
  return { split: two };
}

/** The words of a bornCategory result that is not one category: '12살은 생일에 따라 2013년생(청소년·군인) 또는
 *  2014년생(어린이)', '…은 2026년 요금표의 출생 연도 — 2027년 방문의 구분은 확인 필요'. */
export function bornWords(born, age, year) {
  if (born.split) {
    return `${age}살은 생일에 따라 ${born.split.map(([y, r]) => `${y}년생(${r ? r.category : "요금표에 없음"})`).join(" 또는 ")}`
      + ` — 요금표 구분이 출생 연도라 확인 필요 (${(born.split.find((x) => x[1]) || [])[1].src})`;
  }
  if (born.stale) return `요금표의 구분은 ${born.stale}년 표의 출생 연도 — ${year}년 방문의 구분은 확인 필요`;
  return `${age}살의 출생 연도가 요금표 구분에 없음`;
}

// fee_total's check of an item's price (Knowledge.itemFee) — what a place's fee value writes, never a price of its own
const clip = (t, max) => {
  const s = String(t || "").replace(/\s+/gu, " ").trim();
  return s.length > max ? `${s.slice(0, max)}…` : s;
};
/** The amounts a fee value writes, as numbers: '성인 2,000원', '1만원', a table with no unit ('1,000 (500) 700'); 0 when
 *  it says 무료. A count of people, an age, a month, a time or a room is not one ('20인 이상', '6세', '4인실', '2회'). */
export function amountsIn(text) {
  const s = String(text || "");
  const out = new Set();
  for (const m of s.matchAll(/(\d+(?:\.\d+)?)\s*만\s*원/gu)) out.add(Math.round(+m[1] * 10000));
  for (const m of s.matchAll(/(?<![\d.,:-])(\d{1,3}(?:,\d{3})+|\d{3,})(?!\d|,\d{3}|\s*(?:만|인|세|개월|시|분|월|일|년|명|회|박|층|호|번|곳|대|석|실|%|:|k?m\b))/gu)) {
    const v = Number(m[1].replace(/,/gu, ""));
    if (v >= 100) out.add(v);
  }
  if (/무료/u.test(s)) out.add(0);
  return out;
}
/** The amounts a page's own text writes in won — '20,000원', '16,000~18,000원', '1만원', '5천원' — for a price the
 *  fee value does not give (선유 스카이썬라인's 20,000원 is in its page's text, not in f.fee). Never 0: a page's
 *  '무료' may be anything's (parking, a tool to borrow). */
export function wonIn(text) {
  const s = String(text || "");
  const out = new Set();
  for (const m of s.matchAll(/(\d+(?:\.\d+)?)\s*만\s*원/gu)) out.add(Math.round(+m[1] * 10000));
  for (const m of s.matchAll(/(?<![\d.,])(\d+)\s*천\s*원/gu)) out.add(+m[1] * 1000);
  for (const m of s.matchAll(/(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?=\s*원|\s*[~∼～-]\s*(?:\d{1,3}(?:,\d{3})+|\d+)\s*원)/gu)) {
    const v = Number(m[1].replace(/,/gu, ""));
    if (v > 0) out.add(v);
  }
  return out;
}
/** A combined ticket's prices (every table, a visitor's and a resident's), and 0 when it has a free-entry rule. */
const ticketAmounts = (t) => new Set([...Object.values(t.prices || {}).flatMap((cats) => Object.values(cats || {}).flat()),
  ...((t.rules || []).some((r) => r.kind === "free") ? [0] : [])].filter(Number.isInteger));
// the category an item's label names, as the place's visitor table (f.fee.tab) has it; never for a free entry's price
// ('65세 이상 어른 무료' is not the 성인 price), nor for a label that names two categories
const LABEL_CATS = [[/성인|어른|일반|대인/u, ["성인"]], [/청소년|군인/u, ["청소년·군인", "청소년"]], [/어린이|아동|초등/u, ["어린이"]],
  [/소인/u, ["소인"]]];
const FREE_LABEL = /무료|유아|경로|노인|장애|유공|보호자|\d+\s*(?:세|개월)\s*(?:이상|이하|미만)/u;
function labelCat(label, tab) {
  if (FREE_LABEL.test(label)) return "";
  const named = LABEL_CATS.filter(([rx]) => rx.test(label));
  if (named.length !== 1) return "";
  return named[0][1].find((c) => tab[c] !== undefined) || "";
}
// a category's words in a fee value (pipeline/fee_table.py CATS), and the parts of it that are not a visitor's price
const CAT_WORDS = { 성인: ["성인", "어른", "일반", "대인"], "청소년·군인": ["청소년·군인", "청소년,군인", "청소년, 군인", "청소년/군인", "청소년 / 군인", "청소년", "군인"],
  청소년: ["청소년"], 어린이: ["어린이"], 소인: ["소인"] };
const NOT_VISITOR = /통합권|단체|거주자|시민|주민/u;
/** '일반 20,000원' when the value writes the category with that price in a part of it that is not a resident's, a
 *  group's or a combined ticket's ('[시민] - 성인 1,000원' is not a visitor's 성인 price); '' when it does not. */
function visitorPair(text, cat, n) {
  const parts = String(text || "").split(/\[([^\]]{1,40})\]/u);
  for (let i = 0; i < parts.length; i += 2) {
    if (i && NOT_VISITOR.test(parts[i - 1])) continue;
    for (const w of CAT_WORDS[cat] || []) {
      const rx = new RegExp(`${w}\\s*(?:\\([^)]{0,12}\\))?\\s*[:：]?\\s*(\\d{1,3}(?:,\\d{3})+|\\d+)\\s*원`, "gu");
      for (const m of parts[i].matchAll(rx)) if (Number(m[1].replace(/,/gu, "")) === n) return `${w} ${m[1]}원`;
    }
  }
  return "";
}

/** A place's other names as docs.json gives them (a: [names]); [] for any other doc. */
function otherNames(d) {
  return Array.isArray(d && d.a) ? d.a.filter((x) => typeof x === "string" && x) : [];
}

/** A doc's title as the model reads it in search_site and get_pages results: with the place's other names, so a
 *  building and the museum in it read as one place ('구 일본 제18은행 OO지점 (다른 이름 OO근대미술관)'). Link
 *  titles the reader sees stay the page's own title. */
function shownTitle(d) {
  const a = otherNames(d);
  return a.length ? `${d.t} (다른 이름 ${a.join(", ")})` : d.t;
}

/** ' · name in ja: 群山近代歴史博物館' — the page's name on the site's version in the language the answer is written
 *  in, so the model writes the name that page uses instead of translating the Korean one letter by letter. */
function langName(d, nameLang) {
  const n = nameLang && nameLang !== "ko" ? (d.n || {})[nameLang] : "";
  return n ? ` · name in ${nameLang}: ${n}` : "";
}

// a Korean particle after a name or a time: 으로/로, 을/를, 이/가 by the last sound read aloud — a syllable's final
// consonant; a digit as it is read (1 일, 3 삼, 6 육, 7 칠, 8 팔; 0 ends 십·백·천·영); a time 'HH:MM' as 'H시 M분'
// ('12:00' 시, '11:40' 분). A name ending in a letter gets both.
const DIGIT = { 0: 17, 1: 8, 2: 0, 3: 16, 4: 0, 5: 0, 6: 1, 7: 8, 8: 8, 9: 0 };
export const jong = (w) => {
  // (a name ending in brackets is read by the last word inside them: 'OO신흥동일본식가옥(히로쓰가옥)이')
  const t = String(w).trim().replace(/[)\]）」』"'’”]+$/u, "");
  if (/\d:\d\d$/u.test(t)) return t.endsWith(":00") ? 0 : 4;
  if (/\d$/u.test(t)) return DIGIT[t.slice(-1)];
  const code = t.slice(-1).charCodeAt(0) - 0xac00;
  return code >= 0 && code <= 11171 ? code % 28 : -1;
};
export const ro = (w) => { const j = jong(w); return j < 0 ? "(으)로" : j === 0 || j === 8 ? "로" : "으로"; };
export const eul = (w) => { const j = jong(w); return j < 0 ? "을(를)" : j ? "을" : "를"; };
export const iga = (w) => { const j = jong(w); return j < 0 ? "이(가)" : j ? "이" : "가"; };

// the last entry said as a span before the closing ('입장은 종료 30분 전까지', '입장시간은 관람종료 1시간 전까지', '입장 마감 :
// 운영 종료 1시간 전', '※ 입장마감은 마감시간 30분 전', '폐관 30분 전까지 입장'): its minutes, or null (2026-10-24 YJ-03: '1시간
// 전' went unread, so a visit at 17:30 to a place closing at 18:00 passed; the first city's own '마감시간 30분 전' and '폐관 30분 전'
// were never read either)
const ENTRY_BEFORE = /(?:종료|마감\s*시간|마감|폐관|폐장)\s*(?:(\d{1,2})\s*시간(?:\s*(\d{1,2})\s*분)?|(\d{1,3})\s*분)\s*전/u;
export function entryBefore(text) {
  const m = ENTRY_BEFORE.exec(String(text || ""));
  return m ? (m[3] ? +m[3] : +m[1] * 60 + (+m[2] || 0)) : null;
}
// a last entry or last order written as a time ('입장 마감 12:30', '17:30 입장마감', '라스트오더 21:00', 'L.O 20:30')
const LAST_AT = /입장\s*마감\s*[:：]?\s*(\d{1,2}):(\d{2})|(\d{1,2}):(\d{2})\s*입장\s*마감|(?:라스트\s*오더|주문\s*마감|L\.?\s*O\.?)\s*[:：]?\s*(\d{1,2}):(\d{2})/iu;
export function lastAt(text) {
  const m = LAST_AT.exec(String(text || ""));
  return !m ? null : m[1] ? +m[1] * 60 + +m[2] : m[3] ? +m[3] * 60 + +m[4] : +m[5] * 60 + +m[6];
}
const RANGE_G = /(\d{1,2}):(\d{2})\s*[~–-]\s*(\d{1,2}):(\d{2})/gu;
// a range that is a break of the day, never a session ('준비시간 14:00~16:30', '점심시간 12:00~13:00', '쉬는시간 …')
const BREAK_HEAD = /(?:준비|브레이크|break|점심|휴게|쉬는)\s*(?:시간|타임|time)?\s*[:：]?\s*[-–]?\s*$/iu;
// words between two ranges that make them alternatives (by weekday, by season, by month), never sessions of one day
const SPLIT_LABEL = /[월화수목금토일]\s*요일|[월화수목금토일]\s*[~,·]\s*[월화수목금토일]|평일|주말|휴일|하절기|동절기|춘추|여름|겨울|성수기|비수기|\d\s*월|시즌/u;
/** The sessions of one day an hours value gives ('[1회차]- 09:30~13:00 (입장 마감 12:30) [2회차]- 14:00~17:30 (입장 마감
 *  17:00)', '11:00~15:00, 17:00~21:00'): two or more ranges one after another, none of them a break's and nothing between
 *  them that makes them a weekday's or a season's — [{open, close, last, name?}] in minutes (name '1회차' when the value
 *  names it; last: the entry time after that range, else the value's 'N분/N시간 전' before that range's closing), or
 *  null (2026-10-24 SJ-D02: only the first range was read, so every afternoon visit to 국립어린이박물관 was flagged as
 *  past its 13:00 closing). `before`: entryBefore of the whole value. */
export function sessionsIn(seg, before = null) {
  const text = String(seg || "").replace(/[∼～〜]/gu, "~");
  const all = [...text.matchAll(RANGE_G)].filter((m) => !BREAK_HEAD.test(text.slice(Math.max(0, m.index - 14), m.index)))
    .map((m) => ({ at: m.index, end: m.index + m[0].length, open: +m[1] * 60 + +m[2], close: +m[3] * 60 + +m[4] }));
  if (all.length < 2 || all.some((x) => x.close <= x.open)) return null;
  for (let k = 1; k < all.length; k += 1) {
    if (all[k].open < all[k - 1].close || SPLIT_LABEL.test(text.slice(all[k - 1].end, all[k].at))) return null;
  }
  return all.map((x, k) => {
    const tail = text.slice(x.end, k + 1 < all.length ? all[k + 1].at : text.length);
    const head = text.slice(k ? all[k - 1].end : 0, x.at);
    const named = [...head.matchAll(/(\d{1,2})\s*회차/gu)].pop();
    const own = lastAt(tail);
    const last = own !== null ? own : before !== null ? x.close - before : null;
    return { open: x.open, close: x.close, last, ...(named ? { name: `${+named[1]}회차` } : {}) };
  });
}
// one range of an hours value, anywhere in it
const RANGE_1 = /\d{1,2}:\d{2}\s*[~–-]\s*\d{1,2}:\d{2}/u;
// a day word of an hours value — 평일·주중, 주말, 공휴일, a weekday with or without 요일 — standing as a word, never inside
// one ('일반자료실', '수목원', '요금', '3월', '매일'), a particle after it allowed ('일요일만', '주말은', '주말 및 공휴일')
const DAY_TOKEN_G = /(?<![가-힣0-9])(평일|주중|주말|공휴일|[월화수목금토일](?:요일)?)(?=$|[^가-힣]|(?:만|은|는|및|에|엔|부터|까지)(?![가-힣]))/gu;
const WD_ORDER = "일월화수목금토";   // getUTCDay order
/** The day groups of an hours value: [{at, end, words, days: Set of getUTCDay numbers, holiday}] — a run of day words
 *  with only separators between them ('평일, 일요일', '목. 금. 토. 일 요일', '주말/공휴일', '[평일]'); two weekdays with a
 *  tilde between them are the days from one to the other ('화 ~ 일'). */
export function dayGroups(text) {
  const t = String(text || "");
  const out = [];
  for (const m of t.matchAll(DAY_TOKEN_G)) {
    const w = m[1];
    const one = (x) => WD_ORDER.indexOf(x[0]);
    const days = w === "평일" || w === "주중" ? [1, 2, 3, 4, 5] : w === "주말" ? [0, 6] : w === "공휴일" ? [] : [one(w)];
    const last = out[out.length - 1];
    const gap = last ? t.slice(last.end, m.index) : "";
    if (last && /^\s*[~∼～〜]\s*$/u.test(gap) && days.length === 1 && w !== "공휴일" && last.single !== undefined) {
      for (let d = (last.single + 1) % 7, n = 0; n < 7; d = (d + 1) % 7, n += 1) {
        last.days.add(d);
        if (d === days[0]) break;
      }
    } else if (last && /^[\s,·/、.및&+]*$/u.test(gap)) {
      days.forEach((d) => last.days.add(d));
      last.holiday ||= w === "공휴일";
    } else {
      out.push({ at: m.index, end: m.index + w.length, words: w, days: new Set(days), holiday: w === "공휴일",
        ...(days.length === 1 && w !== "공휴일" ? { single: days[0] } : {}) });
      continue;
    }
    last.end = m.index + w.length;
    last.words = t.slice(last.at, last.end);
    last.single = days.length === 1 && w !== "공휴일" ? days[0] : undefined;
  }
  return out;
}
// what follows a day group that makes it no hours of its own: a closed day, a day left out, the only days it opens
const DAY_NOTE = /^\s*(?:요일)?\s*(?:은|는|에는|엔|에)?\s*(?:만\s*(?:영업|운영|개방|개관|오픈)|제외|휴무|휴관|휴업|휴장|휴점|휴일|쉼|쉽|정기)/u;
/** The weekdays a value says the place opens on only ('(매주 목. 금. 토. 일 요일만 영업)', '주말만 운영'): the day group
 *  (dayGroups) or null — QA 2026-10-26 F05: 카페, 선비꽃 went in a Monday at 12:10, its hours read and the '만 영업' not. */
export function onlyDays(text) {
  const t = String(text || "");
  return dayGroups(t).find((g) => /^\s*(?:요일)?\s*(?:에)?\s*만\s*(?:영업|운영|개방|개관|오픈)/u.test(t.slice(g.end))) || null;
}
/** The part of an hours value for one day when it gives hours by day group — '- 평일 09:00~21:00- 주말 09:00~18:00',
 *  '[평일]- 11:30~22:00 - 준비시간 … [주말]- …', '10:30 ~ 22:00(평일), 10:00 ~ 22:00(주말)', '- 평일, 일요일 10:00~18:00 -
 *  토요일 10:00~19:00', '월요일 09:00~18:00 화·수·목·금·토·일요일 09:00~21:30': {seg} the day's part (its group and what
 *  follows to the next group; the hours before the first group for a day no group names), {why} when the value has
 *  hours by day and none for that day, or null when it has none by day. wd: getUTCDay of the date; holiday: a public
 *  holiday (a group naming 공휴일 holds then). QA 2026-10-26 F03: 국립세종도서관 '평일 09:00~21:00 / 주말 09:00~18:00' was
 *  read as 09:00~21:00 on a Sunday — the first range, whatever the day. */
export function dayPart(text, wd, holiday = false) {
  const t = String(text || "");
  const heads = dayGroups(t).filter((g) => !DAY_NOTE.test(t.slice(g.end)));
  const parts = [];
  heads.forEach((g, i) => {
    const trail = /(\d{1,2}:\d{2}\s*[~–-]\s*\d{1,2}:\d{2})\s*[(（]\s*$/u.exec(t.slice(0, g.at));
    if (trail && /^\s*[)）]/u.test(t.slice(g.end))) {
      parts.push({ g, at: trail.index, seg: `${g.words} ${trail[1]}` });
      return;
    }
    const body = t.slice(g.end, i + 1 < heads.length ? heads[i + 1].at : t.length);
    if (RANGE_1.test(body)) parts.push({ g, at: g.at, seg: g.words + body });
  });
  if (!parts.length) return null;
  const tidy = (x) => x.replace(/[\s\-–/|,·[(（※]+$/u, "").trim();
  if (holiday) {
    const own = parts.find((p) => p.g.holiday);
    if (own) return { seg: tidy(own.seg) };
    // (a holiday on a value by the week's halves alone — '평일 …/주말 …': which half holds then is not in it, to check)
    if (parts.some((p) => /평일|주중|주말/u.test(p.g.words))) return { why: "공휴일 — 평일·주말 어느 쪽 시간인지 이 값에 없음" };
  }
  // (a weekday named on its own comes before the group it is also in: '- 평일 11:30~22:00 … - 금요일 11:30~22:30' on a Friday)
  const pick = parts.filter((p) => p.g.days.has(wd)).sort((a, b) => a.g.days.size - b.g.days.size)[0];
  if (pick) return { seg: tidy(pick.seg) };
  // the hours before the first day group hold on the days no group names ('11:00 ~ 17:00 / 토요일 12:00 ~ 19:00') — never
  // when that part names a day, a closed day or a season itself
  const lead = t.slice(0, Math.min(...parts.map((p) => p.at)));
  if (RANGE_1.test(lead) && !dayGroups(lead).length && !/하절기|동절기|여름|겨울|성수기|비수기|휴무|휴관|휴일|휴업|휴장/u.test(lead)) {
    return { seg: tidy(lead) };
  }
  return { why: `${WD_ORDER[wd]}요일${holiday ? "(공휴일)" : ""} 시간이 이 값에 없음` };
}
// a room's or hall's own hours in a value ('[인문예술자료실/일반자료실]- 평일 … [어린이자료실]-09:00~18:00'): a bracketed name
// ending as a room or a hall does — never a day, a season, a session, a break or a heading of the value
const ROOM_HEAD_G = /\[([^\]\d]{2,40})\]/gu;
const ROOM_NAME = /(?:실|관|장|원|센터|홀|존|코너|라운지|매장|카페|식당)$/u;
const ROOM_NOT = /시간|타임|마감|주문|휴무|휴관|안내|참고|요금|주차/u;
/** The rooms of a value with hours of their own: [{name, seg}] (two or more, each with a range), or null. */
export function roomParts(text) {
  const t = String(text || "");
  const heads = [...t.matchAll(ROOM_HEAD_G)].filter((m) => {
    const name = m[1].replace(/\s+/gu, "");
    return ROOM_NAME.test(name) && !ROOM_NOT.test(name) && !dayGroups(m[1]).length;
  });
  if (heads.length < 2) return null;
  const parts = heads.map((m, i) => ({ name: m[1].trim(), seg: t.slice(m.index + m[0].length, i + 1 < heads.length ? heads[i + 1].index : t.length) }))
    .filter((x) => RANGE_1.test(x.seg));
  return parts.length >= 2 ? parts : null;
}
/** The gaps between the sessions of a value (sessionsIn), as breaks the planner keeps out of: [from, to, words] — from
 *  the session's last entry when it has one (a visit starting after it cannot get in), to the next session's start. */
export function sessionGaps(text) {
  const ss = sessionsIn(text, entryBefore(text));
  if (!ss) return [];
  const hm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
  const nm = (x) => x.name || `운영 시간 ${hm(x.open)}~${hm(x.close)}`;
  return ss.slice(1).map((b, k) => {
    const a = ss[k];
    return [a.last !== null && a.last < a.close ? a.last : a.close, b.open, `${nm(a)}${a.last !== null && a.last < a.close ? " 입장 마감" : " 끝"}부터 ${nm(b)} 시작 전까지`];
  });
}

/** The 권역 a place page names on its 위치 line ('위치: 옥도면 · 섬 권역'), or ''. */
export function regionOf(doc) {
  const m = /^위치: .*?(\S+) 권역\s*$/mu.exec((doc && doc.x) || "");
  return m ? m[1] : "";
}
/** The minutes under which a leg of m metres in a straight line cannot be made whatever the road — a bound, not a
 *  travel time: 60 km/h by car, 24 km/h without one, 6 km/h on foot under 1.2 km (review 2026-10-17 CE09: 1 minute
 *  for 5.7 km passed). checkPlan flags a leg left less. */
export const legBound = (m, move) => m / (move === "car" ? 1000 : m <= 1200 ? 100 : 400);
// the longest straight line between two stops a reader without a car walks (legBound's walk): in a city whose data
// names no bus stop or route for its places (city.js transitStrict) a longer leg has no way the site can confirm
// (outside review 2026-10-24 C05·C08: legs across the city handed to a transit link as if they worked)
export const WALK_M = 1200;
// the farthest a leg without a car may go in such a city, the site having no bus for it (plan_geo.CAP's without a car):
// a longer one is sent back; one between WALK_M and this is a way to check (the plan a candidate, never finished)
export const RIDE_M = 3000;
/** Whether the city's data names no bus for its places and the reader comes without a car (city.js transitStrict):
 *  then a leg is confirmed only as a walk (WALK_M) or a bus route both places' stops share. */
export const walkOnly = (move) => move !== "car" && city().transitStrict;
// a leg into or out of the far islands — a planned allowance, not a travel time (review 2026-10-22 C7a: 역 10:00 →
// 섬 해수욕장 10:30 passed by bus): by the site's own bus guide (/guides/<bus guide>/#h-b6, the same values
// at /guides/<getting-here guide>/#h-b7) the 99 is the only bus to 섬·장자도·무녀도, once an hour from 대학 정문 (09:10–
// 20:10 at :10), 65 minutes to 섬 and 70 to 장자도 and 40 from OO항(환) — and from 역, the terminals or the
// airport a first bus to 대학 or OO항 comes before it: 2 hours without a car (the longest ride, 70 minutes, and up to
// most of an hour's wait for the next 99); by car 60 minutes, what the code's own leg margin (plan_geo.legMargin: 1.5 ×
// the straight line at 60 km/h and 5 minutes to park) gives the 33–37 km from the town to the islands (55–65)
// — the city's far travel areas and their floors are site.json plan.far (docs.json meta.plan.far: {area: {car,
// transit}}); farFloor is the longest of them for the move ('' areas: the plain 30 / 45 between two 권역)
export const farFloor = (move) => Math.max(move === "car" ? 30 : 45, ...Object.values(city().far).map((x) => x[move === "car" ? "car" : "transit"]));
/** regionFloor of two 권역 by name (plan_state.hubMargin reads a station's or a terminal's this way). */
export function regionsFloor(ra, rb, move) {
  if (!ra || !rb || ra === rb) return 0;
  const far = city().far;
  const k = move === "car" ? "car" : "transit";
  const floors = [far[ra], far[rb]].filter(Boolean).map((x) => x[k]);
  return floors.length ? Math.max(...floors) : move === "car" ? 30 : 45;
}
/** The least margin the planner leaves for a leg the site has no distance for (a place without a point) between two
 *  places whose pages name different 권역 — a planned allowance, not a travel time: 30 minutes by car, 45 without
 *  one, into or out of 섬 권역 ISLAND_FLOOR; 0 when the 권역 are the same or a page names none. */
export function regionFloor(a, b, move) {
  return regionsFloor(regionOf(a), regionOf(b), move);
}

// ------------------------------------------------------------ the lines block: which full lines a question needs
// a name as a question may write it: NFKC, lower case, without spaces, punctuation or symbols ('OO 신흥동 일본식
// 가옥(히로쓰 가옥)' and 'OO신흥동일본식가옥(히로쓰가옥)' read the same)
const squash = (t) => String(t ?? "").normalize("NFKC").toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, "");
// a name is looked for in a question when it is at least this long (squashed): 3 for Hangul, kana or CJK, 5 for a
// Latin one ('Iut', 'MCL' are words too often)
const nameMin = (s) => (/[^\u0000-\u007f]/u.test(s) ? 3 : 5);
// a place path in a page's text ('이 가이드의 장소 12곳: - 역사박물관 /places/역사박물관/: …', '가까운 장소: …')
const PLACE_REF = /\/places\/[^\s/;:,()]+\//gu;
// the key-fact slots of a full place line ('시간 …; 휴무 …; 요금 …'), by their short labels (chat_index.py SHORT_LABEL;
// '연중무휴' stands alone)
const SLOT_HEAD = /^(?:(?:시간|휴무|요금|주차|주차요금|전화|메뉴|체크인|체크아웃|객실) |연중무휴(?:;|$))/u;
const slotCount = (line) => {
  const f = String(line).split(" | ").slice(4).find((x) => SLOT_HEAD.test(x));
  return f ? f.split("; ").length : 0;
};
const summaryOf = (d) => (/^요약: (.*)$/mu.exec((d && d.x) || "") || [])[1] || "";
// a food page's menu lines (대표 메뉴·취급 메뉴), without their sources
const menuOf = (d) => String((d && d.x) || "").split("\n").filter((l) => /^- (?:대표|취급) 메뉴/u.test(l)).map((l) => l.split(" — ")[0]).join(" ");
/** The words of a place's 위치 line ('위치: OO동 · 원도심 권역' → OO동, 원도심): what a question names an area by. */
const areaWords = (d) => {
  const m = /^위치: (.*)$/mu.exec((d && d.x) || "");
  return m ? m[1].replace(/권역/gu, " ").split(/[\s·]+/u).filter((w) => [...w].length >= 2) : [];
};
// a question about the foreign articles and posts of /abroad/ (or a page or a conversation about them): only then
// does the lines block carry A lines. Words of coverage and of foreigners writing — not of foreigners travelling
// ('외국인이 가기 좋은 곳', '外国人可以去吗', 'I came from abroad', 'I'm a foreign tourist', 'overseas visitor discounts',
// 'aus dem Ausland', 'touriste étranger' are trips), nor of social media in general ('인스타 감성 카페'), nor a driver
// (택시·버스 기사, 운전기사, 대리기사, 기사님, 기사 아저씨) or a 기사식당, nor a word that only holds 보도 (정보도, 홍보도, a
// sidewalk: '보도로 걸어서', 보도블록) — review 2026-10-23: each of these put all 90 article lines in the block
const FOREIGN = new RegExp([
  "/abroad", "외신", "해외\\s*(?:매체|언론|기사|반응|보도|여행기|블로그|게시물|유튜버|에서\\s*본)",
  "외국\\s*(?:매체|언론|기사|블로그|유튜버)",
  "(?:외국|해외|일본|중국|대만|홍콩|미국|영국|프랑스|독일|스페인|러시아|베트남|태국)\\s*(?:사람|인|관광객|여행자|여행객|유튜버|블로거|계정|매체|언론)들?(?:이|가)?[^.?!\\n]{0,15}?(?:쓴|올린|본|소개한|소개했|찍은|남긴|썼)",
  "(?<![가-힣])(?<!(?:택시|버스|운전|대리|화물)\\s*)기사(?!식당|님|분|\\s*(?:아저씨|아주머니))", "(?:신문|뉴스)\\s*기사",
  "(?<![가-힣])보도(?:된|한|했|자료|기사)?(?![가-힣])", "언론", "매체",
  "\\bforeign\\s+(?:press|media|news|newspapers?|outlets?|coverage|articles?|reporters?|journalists?|bloggers?)\\b",
  "\\b(?:overseas|international)\\s+(?:press|media|news|newspapers?|coverage)\\b", "\\b(?:news\\s+)?articles?\\s+(?:about|on)\\b",
  "\\bnews\\s+articles?\\b", "\\b(?:travel\\s+)?blogs?\\s+(?:about|on|posts?|wrote|written)\\b", "\\bblog\\s*posts?\\b",
  "\\b(?:artikel|artículos?)\\b", "ausländische[nrs]?\\s+(?:medien|presse|zeitungen)", "(?:presse|médias|journaux)\\s+étrang[eè]r",
  "prensa\\s+extranjera", "medios\\s+extranjeros",
  "外媒", "海外(?:の|的)?\\s*(?:メディア|記事|報道|ブログ|媒体|媒體|报道|博客|网友|網友)", "外国(?:的)?\\s*(?:媒体|媒體|报道|報道|记者|記者)",
  "外國(?:的)?\\s*(?:媒體|報道|記者)", "記事", "报道", "報道", "иностранн\\S*\\s*(?:сми|медиа|пресс)", "стать[яиюей]", "пресс[аеуы]",
].join("|"), "iu");
// an outlet's name as a question writes it (NFKC, lower case, punctuation as spaces): the outlets of the articles'
// A lines are a question's sign too ('What did CNN say about the city?', 'CNN에 나온 OO 섬' — review 2026-10-23: the
// core no longer carries the A lines, and no FOREIGN word is in these). The words of an outlet's name that do not tell
// it apart ('CNN Travel' → cnn; 'The Korea Times' → its whole name only)
const plainWords = (t) => String(t ?? "").normalize("NFKC").toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, " ").trim();
const OUTLET_GENERIC = new Set(["the", "of", "and", "korea", "korean", "seoul", "travel", "travels", "traveler", "traveller",
  "news", "daily", "times", "post", "journal", "magazine", "monthly", "weekly", "net", "com", "english", "international",
  "guide", "blog", "note", "tv", "today", "online", "media", "press", "eats", "food", "life", "world", "asia", "asian",
  "studies", "soul", "jp"]);
const LATIN = /[\p{Script=Latin}\p{Script=Cyrillic}\p{N}]/u;
/** Whether `text` (plainWords) holds `term` (plainWords) as whole words where the term starts or ends with a Latin
 *  letter or a digit ('cnn' in 'cnn에 나온', not in 'cnnx'); a Hangul, kana or CJK edge needs no boundary. */
const hasTerm = (text, term) => {
  const [a, b] = [LATIN.test(term[0]), LATIN.test(term[term.length - 1])];
  for (let i = text.indexOf(term); i >= 0; i = text.indexOf(term, i + 1)) {
    if ((!a || !LATIN.test(text[i - 1] || " ")) && (!b || !LATIN.test(text[i + term.length] || " "))) return true;
  }
  return false;
};
// a question that points at the reader's page — a guide's, a course's or an event's places ('여기 나온 식당', 'Is
// parking free at these?')
const DEICTIC = /여기|이\s*중|이곳|이\s*코스|이\s*가이드|이\s*행사|이\s*목록|\b(?:these|those|here|this\s+(?:course|guide|event|list|page))\b|ここ|この|これら|这些|這些|这里|這裡|diese[nrs]?\b|\bici\b|\bestos?\b|\bestas?\b/iu;
// a ranked line counts only when its reading of the question (its score without the small priority term) is above
// this: a question nothing matches (an injection, an emergency) gets a small block, not ~12K of padding; a question
// that names its places (or follows one up) and no kind, area or need gets at most NARROW_MAX lines besides them
const LINE_FLOOR = 0.1;
const NARROW_MAX = 20;
// words for kinds, types, areas and needs, in Korean, English, Japanese and Chinese (and the other site languages
// where a word is short and safe), each with the test of the data's own fields a place passes for it; plan: the
// planner reads it in the note and an edit's request too (planSelect: a dish, a cuisine, a kind or a type — the needs
// are its conditions, and the generic food words fit every restaurant)
const INDOOR_TYPE = /박물관|전시|문화시설|미술관/u;
const LINE_FILTERS = [
  { rx: /박물관|미술관|전시|기념관|역사관|문학관|\b(?:museums?|galler(?:y|ies)|exhibitions?|musée|museo|museum)|美術館|美术馆|博物館|博物馆|展示|展览|展覽|музей/iu,
    fit: (d, f) => INDOOR_TYPE.test(f.ty || ""), plan: true },
  { rx: /카페|커피|빵|베이커리|디저트|\b(?:cafes?|cafés?|coffee|bakery|bakeries|bread|desserts?|kaffee|bäckerei|boulangerie|panader)|カフェ|パン|咖啡|面包|麵包|甜点|甜點|кафе/iu,
    fit: (d) => isCafe(d), plan: true },
  { rx: /맛집|식당|음식|먹(?:을|거리|고|는|으)|밥|점심|저녁|아침\s*식사|해산물|\b(?:restaurants?|food|eat|eating|lunch|dinner|meals?|essen|manger|comer|comida|repas)\b|食|レストラン|ランチ|餐|饭|飯|еда|ресторан/iu,
    fit: (d, f) => f.kd === "food" && !isCafe(d) },
  { rx: /숙소|호텔|펜션|게스트하우스|모텔|민박|숙박|캠핑|글램핑|묵(?:을|는|어|고)|\b(?:hotels?|stay|accommodations?|hostels?|guest\s*houses?|lodging|camping|unterkunft|hébergement|alojamiento)\b|ホテル|宿|酒店|住宿|отель|жиль/iu,
    fit: (d, f) => f.kd === "stay" },
  { rx: /공원|호수|수목원|숲|산책|자연|\b(?:parks?|lakes?|arboretum|forests?|walks?|nature)\b|公園|公园|湖|樹木園|树木园|парк/iu,
    fit: (d, f) => f.kd === "attraction" && /공원|호수|수목원|자연|야외/u.test(f.ty || "") },
  { rx: /비\s*(?:가|오|와|올|내리)|우천|실내|\b(?:rain|rainy|indoors?|regen|pluie|lluvia)\b|雨|室内|室內|дожд/iu,
    fit: (d, f) => f.kd === "attraction" && needAt("rain", f, "visit").state === "ok" },
  { rx: /무료|공짜|입장료\s*(?:가|는)?\s*없|\b(?:free|kostenlos|gratuit|gratis)\b|無料|免费|免費|бесплатн/iu,
    fit: (d, f) => !!(f.fee && f.fee.free) },
  { rx: /주차|\b(?:parking|park the car|parken|parkplatz|stationnement|aparcamiento)\b|駐車|停车|停車|парков/iu,
    fit: (d, f) => ["ok", "near"].includes(needAt("parking", f, "visit").state) },
  { rx: /아이|어린이|아기|유아|초등|가족|\b(?:kids?|child|children|family|kinder|enfants?|niñ[oa]s?)\b|子供|子ども|こども|儿童|兒童|孩子|小孩|親子|亲子|дет/iu,
    fit: (d, f) => f.kd === "attraction" && (f.ty === "체험" || /어린이|아이(?:와|들|가)|가족|체험/u.test(summaryOf(d))) },
  // cuisines, by the page's type or its menu lines ('고깃집' is not '고기집' to the search's bigrams)
  { rx: /고기|고깃집|갈비|삼겹|곱창|숯불|한우|\b(?:bbq|barbecue|grill|galbi|korean beef)\b|焼肉|烤肉|燒肉/iu,
    fit: (d, f) => f.kd === "food" && (f.ty === "고기구이" || /갈비|삼겹|곱창|막창|한우|불고기|고기|숯불/u.test(menuOf(d))), plan: true },
  { rx: /횟집|회집|물회|생선회|회덮밥|해산물|해물|수산|\b(?:seafood|sashimi|raw fish)\b|刺身|海鲜|海鮮|魚介/iu,
    fit: (d, f) => f.kd === "food" && /회|해물|생선|매운탕|조개|수산/u.test(`${d.t} ${menuOf(d)}`), plan: true },
  { rx: /짜장|짜장면|중국집|중식|\b(?:jajang|chinese)\b|中華|中华|中餐/iu,
    fit: (d, f) => f.kd === "food" && (f.ty === "중식" || /짜장|탕수육/u.test(menuOf(d))), plan: true },
  { rx: /한식|백반|정식|국밥|찌개|\b(?:korean food|korean meal)\b|韓国料理|韩餐|韓餐/iu,
    fit: (d, f) => f.kd === "food" && f.ty === "한식", plan: true },
];
// a question about what is near a place: the places its page lists as near count for more
const NEAR = /근처|주변|가까|인근|\b(?:near|nearby|around|close to)\b|近く|周辺|附近|周边|周邊|nähe|près|cerca|рядом/iu;
// how much each reading of the question counts (relevantLines); tuned on tools/chat_lines_eval.mjs
const LINE_WEIGHT = { line: 1, search: 2, expand: 1.8, filter: 1, near: 0.8, prio: 0.15, abroad: 2.5 };
// how much of a trip's lines block each kind of place gets (planLines), by the share of tokens taken so far
const PLAN_WEIGHT = { visit: 4, meal: 2.5, cafe: 1.2, stay: 1.5, rest: 2 };
// at most this many lines of a kind: restaurants (a day; half as many again each further day), cafés, stays (two
// days; more for each further night)
const PLAN_MAX = { meal: 28, mealFood: 60, cafe: 20, cafeDay: 8, stay: 24, stayNight: 8 };
// at most this many places that fit what the note or an edit's request asks for go ahead of the turns (planSelect)
const PLAN_ASK_MAX = 12;
/** The straight-line distance in metres between two [lat, lng] points (plan_geo.metres, which reads this module). */
const straight = (a, b) => {
  const rad = (x) => (x * Math.PI) / 180;
  const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
};
// the needs the planner's code holds to (plan_geo.HARD; rain by its closures)
const PLAN_HARD = ["wheelchair", "stroller", "free", "parking"];

export class Knowledge {
  #li = null;              // the lines' index (lineIndex), built on first use
  #closed = new Map();     // date → the places closed that day (closedOn)

  constructor({ catalog, docs, index, lines = {} }) {
    this.catalog = String(catalog || "");
    this.meta = readMeta(docs && docs.meta, docs && docs.site);
    this.site = this.meta.site;
    useCity(this.meta);   // the course planner's city values (city.js): one deployment, one city
    this.tel = new Set(this.meta.tel);
    this.docs = table(docs && docs.docs);
    // lines.json {v, lines: {doc key: full catalog line}, core: [keys the core catalog lists]} (or the lines map
    // alone): only a line of a page the site has
    const ln = lines && typeof lines === "object" ? lines : {};
    const map = ln.lines && typeof ln.lines === "object" && !Array.isArray(ln.lines) ? ln.lines : ln;
    this.lines = table();
    for (const [k, v] of Object.entries(map)) if (typeof v === "string" && v && this.docs[k]) this.lines[k] = v;
    this.core = new Set(Array.isArray(ln.core) ? ln.core.filter((k) => typeof k === "string" && this.lines[k]) : []);
    this.alias = table(docs && docs.alias);
    // outside addresses the data links to, by their compared form → the address as the data has it (https first)
    this.ext = new Map();
    for (const u of (docs && docs.ext) || []) {
      const k = normUrl(u);
      const had = this.ext.get(k);
      if (!had || (/^http:/i.test(had) && /^https:/i.test(u))) this.ext.set(k, u);
    }
    // 예약하기 (pipeline/booking.py, docs.json 'book'): every address of an official booking page — the Korean one and
    // each version's — by its compared form → {url: the Korean page, k: the service, p: {hreflang: that version's
    // page}, l: {page: its language}}
    this.book = new Map();
    for (const [u, b] of Object.entries((docs && docs.book) || {})) {
      if (!b || typeof b !== "object") continue;
      const entry = { url: u, k: String(b.k || ""), p: table(b.p), l: table(b.l) };
      for (const v of [u, ...Object.values(entry.p)]) if (typeof v === "string") this.book.set(normUrl(v), entry);
    }
    // the combined tickets' tables (pipeline/tickets.py export): feeTotal
    this.tickets = Array.isArray(docs && docs.tickets) ? docs.tickets.filter((t) => t && t.name && t.prices) : [];
    this.keys = Object.keys(this.docs).sort();
    this.byTitle = new Map();
    for (const k of this.keys) {
      const t = this.docs[k].t;
      this.byTitle.set(t, this.byTitle.has(t) ? null : k);   // a title two pages share names neither
    }
    // a place's other names find its page too ('OO근대미술관' → 구 일본 제18은행 OO지점), unless a title or another
    // place's other name is the same
    const other = new Map();
    for (const k of this.keys) {
      for (const a of otherNames(this.docs[k])) other.set(a, other.has(a) ? null : k);
    }
    for (const [a, k] of other) if (k && !this.byTitle.has(a)) this.byTitle.set(a, k);
    // every place's Korean names (title and other names, 3 characters or more), longest first: namesIn finds them in a
    // guide's or a section's Korean text and gives their names in the answer's language
    this.placeNames = [];
    for (const k of this.keys) {
      const d = this.docs[k];
      if (d.k !== "place") continue;
      for (const name of new Set([d.t, ...otherNames(d)])) if ([...name].length >= 3) this.placeNames.push([name, k]);
    }
    this.placeNames.sort((a, b) => b[0].length - a[0].length || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    // places that belong together (pipeline/relations.py — the page's own lines '속한 곳: …', '같은 건물: …', '<name> 안에
    // 있는 곳: …'): page → the pages it goes with, both ways. The planner reads them as one place across a trip's days
    // (live check 2026-10-19: OO호수공원 물빛다리 one night, OO호수공원 put in the next)
    this.kin = new Map();
    const tie = (a, b) => {
      if (a === b || !this.docs[b]) return;
      for (const [x, y] of [[a, b], [b, a]]) (this.kin.get(x) || this.kin.set(x, new Set()).get(x)).add(y);
    };
    for (const k of this.keys) {
      const d = this.docs[k];
      if (d.k !== "place") continue;
      for (const line of String(d.x || "").split("\n")) {
        if (!/^(?:속한 곳|같은 건물): /u.test(line) && !line.startsWith(`${d.t} 안에 있는 곳: `)) continue;
        for (const m of line.matchAll(/(\/places\/[^\s;]+\/)/gu)) tie(k, m[1]);
      }
    }
    // the islands reached only by ferry, as the site's ferry guide names them in its summary ('…에서 어청도·개야도·
    // 연도로, 장자도 선착장에서 관리도·방축도·명도·말도를 …'), and the places on them — the island's own page, or one whose
    // address names it ('옥도면 방축도길 23-1'): page → island. The site has no sailing times, so the planner puts none of
    // them in a plan (round 7 review A03: OO섬길, on 방축도, planned as a 30-minute drive from 섬)
    this.ferry = new Map();
    const guide = this.keys.find((k) => /^\/guides\/[^#]*여객선[^#]*\/$/u.test(k));
    const summary = guide ? (/^요약: (.*)$/mu.exec(this.docs[guide].x || "") || [])[1] || "" : "";
    const isles = [...summary.matchAll(/에서\s+((?:[가-힣]+도·)*[가-힣]+도)(?:로|를)/gu)].flatMap((m) => m[1].split("·"));
    for (const k of isles.length ? this.keys : []) {
      const d = this.docs[k];
      if (d.k !== "place") continue;
      const addr = (/^- 주소: ([^—\n]+)/mu.exec(d.x || "") || [])[1] || "";
      const isle = isles.find((i) => d.t === i || new RegExp(`(?:면|동)\\s+${i}(?:길|리)?(?:\\s|\\d|$)`, "u").test(addr));
      if (isle) this.ferry.set(k, isle);
    }
    const idx = (index && index.docs) || {};
    this.head = new Map();
    this.body = new Map();
    const df = new Map();
    for (const k of this.keys) {
      const [h = "", b = ""] = idx[k] || [];
      const hs = new Set(h ? h.split(" ") : tokens(this.docs[k].t));
      const bs = new Set(b ? b.split(" ") : []);
      this.head.set(k, hs);
      this.body.set(k, bs);
      for (const t of new Set([...hs, ...bs])) df.set(t, (df.get(t) || 0) + 1);
    }
    this.df = df;
    // a page's own names — its title, other names and its names on the other versions — by their tokens: a query that
    // is exactly one of them ranks that page first ('Museum für moderne Geschichte' is in a guide's and an
    // event's German titles too; review 2026-10-17 E03)
    this.exact = new Map();
    for (const k of this.keys) {
      const d = this.docs[k];
      if (k.includes("#")) continue;
      for (const name of [d.t, ...otherNames(d), ...Object.values(d.n || {})]) {
        const key = tokens(name).join(" ");
        if (!key) continue;
        if (!this.exact.has(key)) this.exact.set(key, new Set());
        this.exact.get(key).add(k);
      }
    }
  }

  idf(t) {
    return Math.log(1 + this.keys.length / (1 + (this.df.get(t) || 0)));
  }

  /** The doc key a page path, an English path, an absolute site URL or an exact page title refers to; '' if none. */
  keyFor(raw) {
    let s = decode(String(raw ?? "").trim()).normalize("NFC");
    if (!s) return "";
    if (this.site && s.startsWith(this.site)) {
      const rest = s.slice(this.site.length);
      if (rest && !"/?#".includes(rest[0])) return "";   // <site>.example.com is another site
      s = rest || "/";
    }
    if (this.docs[s]) return s;
    if (this.byTitle.get(s)) return this.byTitle.get(s);
    let [base, frag = ""] = s.split("#");
    base = base.split("?")[0];
    if (base.startsWith("/") && !base.endsWith("/")) base += "/";
    const tries = [base, base.toLowerCase()];
    for (const b of tries) {
      const k = this.docs[b] ? b : this.alias[b] || "";
      if (!k) continue;
      if (frag && this.docs[`${k}#${frag}`]) return `${k}#${frag}`;
      return k;
    }
    return "";
  }

  /** The path a reader of `lang` should open for a doc key: the page of that language's version when it has one
   *  (a guide section: its guide's twin, same anchor), else the English page, else the Korean page; an article or a
   *  video opens the page that lists it. */
  pathFor(key, lang = "ko") {
    const d = this.docs[key];
    if (!d) return "";
    const [base, frag] = key.split("#");
    if (!base.startsWith("/")) return d.u || "/";
    if (lang !== "ko") {
      const own = ((this.docs[base] || d).l || {})[lang] || d.e;
      if (own) return frag && !own.includes("#") ? `${own}#${frag}` : own;
    }
    return frag ? `${base}#${frag}` : base;
  }

  /** The name a reader of `lang` sees for a doc on a link card: the version's own name (a guide section: its
   *  guide's), else the English one (pathFor opens the English page then), else '' (the caller keeps what it has). */
  nameFor(key, lang) {
    const base = key.split("#")[0];
    if (lang === "ko") return "";
    const n = (this.docs[base] || this.docs[key] || {}).n || {};
    return n[lang] || n.en || "";
  }

  /** 'Names of these places on this site in de: 역사박물관 = Museum für moderne Geschichte; …' — the places a
   *  tool result's Korean text mentions (longest name first; a shorter name inside a longer one is not read again),
   *  with their names in `nameLang` (else English): the model writes those instead of translating the Korean one.
   *  Leaves out the pages in `skip` (their own lines name them already); at most NAMES_MAX names and `max`
   *  characters; '' for Korean, or when no place has such a name. */
  namesIn(text, nameLang, skip = new Set(), max = NAMES_CHARS) {
    if (!nameLang || nameLang === "ko") return "";
    const head = `Names of these places on this site in ${nameLang}: `;
    let t = String(text ?? "");
    const seen = new Set();
    const out = [];
    let len = head.length;
    for (const [name, key] of this.placeNames) {
      if (out.length >= NAMES_MAX) break;
      if (!t.includes(name)) continue;
      t = t.split(name).join(" ");   // its shorter names and words inside it are not other places
      if (seen.has(key) || skip.has(key)) continue;
      seen.add(key);
      const d = this.docs[key];
      const v = (d.n || {})[nameLang] || (d.n || {}).en;
      if (!v) continue;
      const item = `${d.t}${name !== d.t ? ` (${name})` : ""} = ${v}`;
      if (len + item.length + 2 > max) continue;
      out.push(item);
      len += item.length + 2;
    }
    return out.length ? head + out.join("; ") : "";
  }

  url(pathname) {
    return this.site + encodeURI(pathname);
  }

  /** The reader's page for the prompt, from the site's own data; '' when it is not a catalog page (the browser's text
   *  never reaches the prompt). */
  describePage(page, nameLang = "") {
    const key = this.keyFor(page);
    if (!key) return "";
    const d = this.docs[key];
    return `${key} — ${shownTitle(d)} (${KIND_LABEL[d.k] || d.k})${langName(d, nameLang)}`;
  }

  /** search_site: pages ranked by matched query tokens (idf-weighted; a title / first-line match counts three times),
   *  scaled by the share of query tokens found and by kind, doubled for a page whose own name the query is. */
  search(query, { kind = "any", limit = 8 } = {}) {
    const q = tokens(String(query ?? "").slice(0, QUERY_CHARS));
    if (!q.length) return [];
    const kinds = KIND_FILTER[kind] || null;
    const named = this.exact.get(q.join(" ")) || new Set();
    const hits = [];
    for (const k of this.keys) {
      const d = this.docs[k];
      if (kinds && !kinds.includes(d.k)) continue;
      const head = this.head.get(k);
      const body = this.body.get(k);
      let score = 0;
      let found = 0;
      for (const t of q) {
        if (head.has(t)) {
          score += 3 * this.idf(t);
          found += 1;
        } else if (body.has(t)) {
          score += this.idf(t);
          found += 1;
        }
      }
      if (!found) continue;
      score *= (0.4 + 0.6 * (found / q.length)) * (KIND_WEIGHT[d.k] ?? 1) * (named.has(k) ? 2 : 1);
      hits.push({ key: k, score });
    }
    hits.sort((a, b) => b.score - a.score || (a.key < b.key ? -1 : 1));
    return hits.slice(0, limit).map((h) => ({ ...h, title: this.docs[h.key].t, kind: this.docs[h.key].k,
      snippet: this.snippet(h.key, q) }));
  }

  snippet(key, q) {
    const lines = this.docs[key].x.split("\n");
    let best = lines[0];
    let bestN = -1;
    for (const line of lines.slice(1)) {
      const ts = new Set(tokens(line));
      const n = q.filter((t) => ts.has(t)).length;
      if (n > bestN) {
        best = line;
        bestN = n;
      }
    }
    return best.length > SNIPPET_CHARS ? `${best.slice(0, SNIPPET_CHARS)}…` : best;
  }

  /** search_site's result as the model reads it; for an answer in another language than Korean, then the line naming
   *  the places its snippets mention in that language (namesIn). */
  searchText(query, opts = {}) {
    const hits = this.search(query, opts);
    if (!hits.length) return `No page of this site matches "${String(query ?? "").slice(0, QUERY_CHARS)}". Try other words (Korean place names or dishes), or say the site has no information on it.`;
    const lines = hits.map((h, i) => {
      const d = this.docs[h.key];
      const where = h.key.startsWith("/") ? h.key : `${h.key} (on ${d.u || "/"})`;
      const en = opts.lang && opts.lang !== "ko" && d.e ? ` · English page ${d.e}` : "";
      return `${i + 1}. ${shownTitle(d)}${langName(d, opts.nameLang)} — ${KIND_LABEL[d.k] || d.k} — ${where}${en}\n   ${h.snippet}`;
    });
    const names = this.namesIn(hits.map((h) => h.snippet).join("\n"), opts.nameLang, new Set(hits.map((h) => h.key)));
    return (names ? [...lines, names] : lines).join("\n");
  }

  /** get_pages: the full text of up to PAGE_LIMIT pages, each cut at DOC_CHARS, all of it within `budget`
   *  characters — for an answer in another language than Korean, the pages within the budget less the room of the
   *  line that names the places they mention in that language (namesIn), which comes last. Returns {text, keys,
   *  missing}. */
  pagesText(ids, { lang = "ko", budget = Infinity, nameLang = "" } = {}) {
    const keys = [];
    const missing = [];
    const parts = [];
    const room = nameLang && nameLang !== "ko" ? Math.min(NAMES_CHARS, Math.floor(budget / 4)) : 0;
    let left = budget - room;
    for (const raw of ids.slice(0, PAGE_LIMIT)) {
      const key = this.keyFor(raw);
      if (!key) {
        missing.push(String(raw).slice(0, 120));
        continue;
      }
      if (keys.includes(key)) continue;
      keys.push(key);
      const d = this.docs[key];
      const where = key.startsWith("/") ? key : `${key} (listed on ${d.u || "/"})`;
      const en = d.e ? ` · English page ${d.e}` : "";
      let text = d.x.length > DOC_CHARS ? `${d.x.slice(0, DOC_CHARS)}\n… (cut here: the rest is on the page)` : d.x;
      let part = `### ${shownTitle(d)}${langName(d, nameLang)}\nPath: ${where}${en}\n${text}`;
      if (part.length > left) {
        if (left < 400) {
          // said as what this result holds, never as a limit the answer could pass on (server.js, 2026-10-18)
          parts.push(`### ${shownTitle(d)}\n(not given here: link this page for its details)`);
          continue;
        }
        part = `${part.slice(0, left)}\n… (cut here: the rest is on the page)`;
      }
      left -= part.length + 2;   // and the blank line before the next part
      parts.push(part);
    }
    if (room) {
      const names = this.namesIn(parts.join("\n"), nameLang, new Set(keys), room);
      if (names) parts.push(names);
    }
    if (ids.length > PAGE_LIMIT) parts.push(`(only the first ${PAGE_LIMIT} pages were read)`);
    if (missing.length) parts.push(`Not pages of this site: ${missing.join(", ")} — use paths from the catalog or search_site.`);
    return { text: parts.join("\n\n"), keys, missing };
  }

  /** fee_total: a group's admission fees added up once (review 2026-10-17 G02: one answer gave 8,000, 5,000 and
   *  4,000 won for the same family and ticket). `ticket` — a combined ticket the site keeps as a table — with `people`
   *  [{count, age?, category?}]: each person's price from the table (시민 prices with `resident`, the 단체 table
   *  with `group`), the table's free-entry and age rules applied, a person the table has no rule for marked 확인 필요
   *  and left out of the total; `items` [{label, won, count, page?}]: fees the pages give, multiplied and added — with
   *  `page`, only a price that page gives for it (itemFee), any other marked 확인 필요 and left out; without, added
   *  as '(대조 안 됨)'. The result
   *  (Korean, as the data) names every line's basis and source, the sum written out and the total the answer is to use
   *  everywhere — or, when a person is 확인 필요, the known part only and no total. */
  feeTotal({ ticket = "", people = [], resident = false, group = false, items = [] } = {}, now = new Date()) {
    const won = (n) => `${n.toLocaleString("en-US")}원`;
    const out = [];
    const parts = [];   // [amount, label] of every line in the total
    const open = [];    // the persons the table gives no price for
    const conds = [];   // what a price in the total holds on
    const bare = (x) => String(x || "").replace(/\s+/g, "");
    // what a ticket opens: its places' page names, never the table's own words for them (CLAUDE.md 3.3)
    const opens = (x) => `${x.places.length}곳: ${x.places.map((p) => p.name).join(" · ")}`;
    if (ticket || people.length) {
      const t = this.tickets.find((x) => bare(x.name) === bare(ticket) || x.id === ticket)
        || (bare(ticket).length >= 3 && this.tickets.filter((x) => bare(x.name).includes(bare(ticket))).length === 1
          ? this.tickets.find((x) => bare(x.name).includes(bare(ticket))) : null);
      if (!t) {
        out.push(`'${String(ticket).slice(0, 60)}'은 이 사이트가 표로 가진 통합권이 아니다. 표가 있는 통합권: `
          + (this.tickets.map((x) => `${x.name}(${opens(x)})`).join("; ") || "없음")
          + ". 다른 요금은 장소 페이지의 값으로 items에 넣어 계산한다.");
      } else {
        const rules = t.rules || [];
        const free = rules.filter((r) => r.kind === "free");
        const ages = rules.filter((r) => r.kind === "age");
        // a table by birth years is read for this year (Korea's): someone of an age falls in one category or two
        const year = new Date(now.getTime() + 9 * 3600e3).getUTCFullYear();
        const n = people.reduce((a, p) => a + p.count, 0);
        const twenty = rules.some((r) => r.kind === "note" && /20인/.test(r.text));
        let mode = group ? "단체" : "개인";
        let modeNote = "";
        if (group && twenty && n < 20) {
          mode = "개인";
          modeNote = ` (단체할인은 20인 이상 — 이 질문은 ${n}명이라 개인 요금)`;
        } else if (group && !twenty) modeNote = " (단체 기준 인원은 이 요금표에 없음 — 확인 필요)";
        const table = (t.prices || {})[mode] || {};
        const at = resident ? 1 : 0;
        const who = this.meta.plan.resident || "거주자";
        out.push(`${t.name}(${opens(t)}) — ${mode} 요금${modeNote}, ${resident ? `${who} 요금` : `${who} 아님`} — 요금 출처: ${t.src}`);
        out.push(`시설: ${t.places.map((p) => `${p.name} ${p.path}`).join("; ")}`);
        const CAT = { 성인: "성인", 어른: "성인", 청소년: "청소년·군인", 군인: "청소년·군인", "청소년·군인": "청소년·군인", 어린이: "어린이",
          아동: "어린이", 초등학생: "어린이" };
        const FREE_WORD = { 유아: /유아|6세/, 영유아: /유아|6세/, 경로: /65세/, "65세 이상": /65세/, 노인: /65세/, 장애인: /장애인/,
          국가유공자: /유공자/, 유공자: /유공자/ };
        for (const p of people) {
          const who = `${p.category ? p.category : ""}${p.age !== undefined ? `${p.category ? " " : ""}${p.age}살` : ""}` || "구분 없음";
          const label = `${who} ${p.count}명`;
          const byAge = p.age !== undefined ? free.find((r) => (r.age_max !== undefined && p.age <= r.age_max)
            || (r.age_min !== undefined && p.age >= r.age_min)) : null;
          const byWord = p.category && FREE_WORD[p.category] ? free.find((r) => FREE_WORD[p.category].test(r.who)) : null;
          const freeRule = byAge || byWord;
          if (freeRule) {
            out.push(`- ${label}: 0원 (무료입장 '${freeRule.who}' — ${freeRule.src})`);
            parts.push([0, label]);
            continue;
          }
          let cat = CAT[p.category] || "";
          let basis = cat ? `요금표 '${cat}', 질문의 구분` : "";
          const ageRule = p.age !== undefined ? ages.find((r) => p.age >= r.from && p.age <= r.to) : null;
          const born = p.age !== undefined ? bornCategory(rules, p.age, year) : null;
          const bornRule = born && born.rule;
          const bornText = bornRule ? `'${bornRule.category} ${bornRule.text}' (${bornRule.src})` : "";
          if (cat && p.age !== undefined) {
            const own = ages.find((r) => r.category === cat);
            if (own && (p.age < own.from || p.age > own.to)) {
              out.push(`- ${label}: 확인 필요 — 질문의 구분 '${cat}'와 요금표의 '${own.text}'가 맞지 않음 (${own.src})`);
              open.push(label);
              continue;
            }
            if (bornRule && bornRule.category !== cat) {
              out.push(`- ${label}: 확인 필요 — 질문의 구분 '${cat}'와 요금표의 ${bornText}가 맞지 않음`);
              open.push(label);
              continue;
            }
            if (own) basis = `요금표 '${own.text}' (${own.src})`;
            else if (bornRule) basis = `요금표 ${bornText}`;
            if (born && born.split) {
              basis += ` — ${bornWords(born, p.age, year)}`;
              conds.push(`${p.age}살을 '${cat}'로 본 값(출생 연도에 따라 구분이 다름)`);
            }
          }
          // without the reader's category: the table's ages and birth years must give one category
          if (!cat && born && born.split) {
            out.push(`- ${label}: 확인 필요 — ${bornWords(born, p.age, year)}`);
            open.push(label);
            continue;
          }
          if (!cat && ageRule && bornRule && ageRule.category !== bornRule.category) {
            out.push(`- ${label}: 확인 필요 — 요금 구분이 출처마다 다름: '${ageRule.text}' (${ageRule.src}) / ${bornText}`);
            open.push(label);
            continue;
          }
          if (!cat && ageRule) {
            cat = ageRule.category;
            basis = `요금표 '${ageRule.text}' (${ageRule.src})`;
          } else if (!cat && bornRule) {
            cat = bornRule.category;
            basis = `요금표 ${bornText}`;
          } else if (!cat && born && born.stale) {
            out.push(`- ${label}: 확인 필요 — ${bornWords(born, p.age, year)}`);
            open.push(label);
            continue;
          }
          if (!cat || !table[cat]) {
            const why = FREE_WORD[p.category] ? `무료 대상 '${p.category}'이 이 요금표에 없음`
              : p.age !== undefined ? `${p.age}살이 어느 구분인지(연령 기준·무료 대상) 이 요금표에 없음` : "요금 구분을 알 수 없음";
            out.push(`- ${label}: 확인 필요 — ${why}`);
            open.push(label);
            continue;
          }
          const price = table[cat][at];
          // a category the reader's words gave for an age the table has no rule for: the price holds only on that
          // reading, and the answer says so with the total
          if (!ages.some((r) => r.category === cat) && p.age !== undefined && !(born && (born.rule || born.split))) {
            const why = born && born.stale ? `이 요금표의 출생 연도는 ${born.stale}년 표` : "이 요금표에 연령 기준 없음";
            basis = `요금표 '${cat}' — ${p.age}살을 '${cat}'로 본 값, ${why}`;
            conds.push(`${p.age}살을 '${cat}'로 본 값(${why})`);
          }
          out.push(`- ${label}: ${won(price)} × ${p.count} = ${won(price * p.count)} (${basis})`);
          parts.push([price * p.count, label]);
        }
        const kinds = new Set(rules.map((r) => r.kind));
        if (!(kinds.has("age") || kinds.has("born")) || !kinds.has("free")) {
          const other = this.tickets.filter((x) => x !== t && t.places.every((p) => x.places.some((q) => q.path === p.path))
            && (x.rules || []).some((r) => r.kind !== "note"));
          const missing = [!(kinds.has("age") || kinds.has("born")) ? "연령 기준" : "", !kinds.has("free") ? "무료 대상" : ""].filter(Boolean).join("·");
          // another table that covers every place of this one and has the rules this one lacks: named as that table's
          // rules, by their own sources — never applied to this ticket
          const ref = (x) => {
            const bySrc = new Map();
            for (const r of x.rules.filter((y) => y.kind !== "note")) {
              if (!bySrc.has(r.src)) bySrc.set(r.src, []);
              bySrc.get(r.src).push(r.kind === "free" ? `무료입장 ${r.who}` : r.kind === "born" ? `${r.category} ${r.text}` : r.text);
            }
            return [...bySrc].map(([src, what]) => `${what.join(", ")} (${src})`).join("; ");
          };
          out.push(`이 요금표에 없는 것: ${missing} — 이 통합권의 값으로 쓰지 않는다.`
            + other.map((x) => ` 참고로 같은 시설을 포함하는 '${x.name}' 요금표의 규칙: ${ref(x)}`).join(""));
        }
        for (const r of rules.filter((x) => x.kind === "note")) out.push(`조건: ${r.text} (${r.src})`);
      }
    }
    // items: prices the model read off the pages. With its place's page each is checked against that page's fee value
    // (itemFee); only a price the page gives keeps '(페이지의 값)', any other is 확인 필요 and out of the total, as a
    // person the ticket's table has no rule for (review 2026-10-21 T-chat-fee-tool-unit-price: a made-up 1,234원, the
    // 시민 1,000원 for a visitor and 7,000원 for a free place went into one total as '페이지의 값')
    let openItems = 0;
    for (const it of items) {
      const label = String(it.label).slice(0, 80);
      const sub = it.won * it.count;
      const line = `- ${label}: ${won(it.won)} × ${it.count}`;
      const c = it.page ? this.itemFee(it, { resident, group }) : null;
      if (c && !c.ok) {
        out.push(`${line} — ${c.why} — 확인 필요 (${c.basis})`);
        open.push(label);
        openItems += 1;
        continue;
      }
      out.push(`${line} = ${won(sub)} ${c ? `(페이지의 값: ${c.basis})` : "(대조 안 됨)"}`);
      parts.push([sub, it.label]);
    }
    if (!parts.length && !open.length) return { text: out.join("\n") || "계산할 사람이나 항목이 없다.", total: null, known: null };
    const sum = parts.reduce((a, [v]) => a + v, 0);
    const formula = parts.length ? `${parts.map(([v]) => v.toLocaleString("en-US")).join(" + ")} = ${won(sum)}` : "0원";
    const on = conds.length ? ` 조건: ${conds.join("; ")} — 이 조건을 합계와 함께 첫 문장에 쓴다.` : "";
    if (open.length) {
      out.push(`확인된 ${openItems ? "값" : "사람"}만의 합계(식): ${formula}. 확인 필요: ${open.join(", ")} — 총액을 확정하지 않는다: `
        + `답의 첫 문장과 표와 끝에 '${won(sum)} + ${open.join(", ")} 요금 확인 필요'로 같은 값을 쓴다.${on}`);
      return { text: out.join("\n"), total: null, known: sum };
    }
    out.push(`합계(식): ${formula}. 답의 첫 문장·표·끝 어디서나 이 합계 ${won(sum)} 하나만 쓴다(같은 선택에 다른 합계를 쓰지 않는다).${on}`);
    return { text: out.join("\n"), total: sum, known: sum };
  }

  /** fee_total's check of one item's price against its place's fee value (docs.json f.fee, pipeline/fee_table.py):
   *  {ok, basis} — ok when the page gives that price for it, else {ok: false, why, basis}. A free place gives 0원; a
   *  visitor's table (tab, its heading tl) gives the price of the one category the label names — unless the reader
   *  lives in the city or asks for group prices, or the label names a resident's, a group's, a combined ticket's or a
   *  free entry's price (the table is none of those) — or that category written with this price in a part of the value
   *  that is not a resident's, a group's or a combined ticket's ('현장 … 온라인 - 일반 20,000원'). Any other price is
   *  looked for among the amounts the place's values and the combined tickets that open it write — at a place with no
   *  fee value, among the won amounts its page's text writes (wonIn). A price where the
   *  sources differ (f.fee.alt) that not every source gives is both sources' words and 방문 전 전화 확인 (CLAUDE.md
   *  3절 2항). Never a price of its own: only whether the page gives this one. */
  itemFee(it, { resident = false, group = false } = {}) {
    const key = this.keyFor(it.page);
    const d = key ? this.docs[key] : null;
    if (!d || d.k !== "place") return { ok: false, why: "대조 안 됨", basis: `'${String(it.page).slice(0, 80)}'은 이 사이트의 장소 페이지가 아님` };
    const fee = (d.f || {}).fee || {};
    const srcs = [...(fee.free || fee.t ? [{ p: fee.p || "", t: fee.t || "무료" }] : []), ...(fee.alt || []).filter((a) => a && a.t)];
    const n = it.won;
    // no fee value: the page's own text may still write the price (a zipline's 20,000원, an experience's, a menu's);
    // only a page that writes no such amount has no price for it
    if (!srcs.length) {
      const onPage = wonIn(d.x);
      if (onPage.has(n)) return { ok: true, basis: `${d.t} 페이지에 쓰인 금액, 어느 항목·구분의 값인지는 대조 안 함` };
      return { ok: false, why: "대조 안 됨", basis: onPage.size ? `${d.t} 페이지에 ${n.toLocaleString("en-US")}원이 없음(요금 값 없음)`
        : `${d.t} 페이지에 요금 정보 없음` };
    }
    const label = String(it.label);
    const by = (p) => (p ? ` — ${p}` : "");
    const differ = () => ({ ok: false, why: "출처마다 요금이 다름",
      basis: `${srcs.map((s) => `${s.p ? `${s.p} ` : ""}'${clip(s.t, 120)}'`).join(" / ")} — 방문 전 전화 확인` });
    const cat = fee.tab && !resident && !group && !/시민|거주|단체|통합/u.test(label) ? labelCat(label, fee.tab) : "";
    const exp = fee.free ? 0 : cat ? fee.tab[cat] : null;
    if (exp !== null) {
      const basis = fee.free ? `${d.t} '무료'${fee.note ? ` (${fee.note})` : ""}${by(fee.p)}`
        : `${d.t} 요금표 '${cat}'${fee.tl ? ` (${fee.tl})` : ""}${by(fee.p)}`;
      const pair = n !== exp && cat ? visitorPair(fee.t, cat, n) : "";
      if (n === exp || pair) {
        // the other sources must give the same: 무료, or that category at that price
        const agree = srcs.slice(1).every((s) => (fee.free ? amountsIn(s.t).has(0) : !!visitorPair(s.t, cat, n)));
        return agree ? { ok: true, basis: pair ? `${d.t} 요금 값의 '${pair}'${by(fee.p)}` : basis } : differ();
      }
      if (srcs.slice(1).some((s) => amountsIn(s.t).has(n))) return differ();
      return { ok: false, why: `페이지 값 ${exp.toLocaleString("en-US")}원과 다름`, basis };
    }
    // no one price to compare with: the amount among what the place's value and its combined tickets write — where the
    // sources differ, which of their prices this is cannot be told
    const own = srcs.filter((s) => amountsIn(s.t).has(n));
    if (own.length) return srcs.length > 1 ? differ() : { ok: true, basis: `${d.t} 요금 값에 있는 금액, 어느 구분의 값인지는 대조 안 함${by(fee.p)}` };
    const t = this.tickets.find((x) => x.places.some((p) => p.path === key) && ticketAmounts(x).has(n));
    if (t) return { ok: true, basis: `'${t.name}' 요금표에 있는 금액 — ${t.src}` };
    return { ok: false, why: "대조 안 됨", basis: `${d.t} 요금 값에 ${n.toLocaleString("en-US")}원이 없음: '${clip(srcs[0].t, 120)}'${by(srcs[0].p)}` };
  }

  /** check_plan: a timed plan read against the site's data (review 2026-10-17 G01: OO항1981 until 16:00, then
   *  국립OO대학교 박물관 from 16:00 — 5.7 km apart). For each stop: that day's regular closed days and the date's
   *  notices, the hours of the date's season with the last entry, and what the plan's times break (a place whose inside
   *  is not open to visitors: said so — stop outside {p sources, only: its hours are only those words}); for each leg between
   *  two places: the straight-line distance (not a route, not a travel time), the minutes the plan leaves, and the bus
   *  routes the stops near both share (direction and times are the timetable's). Returns {text, flags}. */
  checkPlan({ date = "", stops = [], move = "" } = {}) {
    const WD = "일월화수목금토";
    // the n-th of a month, by its word without '째'/'번째' ('첫째', '첫 번째' → 첫; '세 번째' → 세)
    const ORD = { 첫: 1, 둘: 2, 두: 2, 셋: 3, 세: 3, 넷: 4, 네: 4, 다섯: 5 };
    const ORD_G = /((?:첫|두|세|네|다섯)\s*번\s*째|첫째|둘째|셋째|넷째|다섯째|첫|마지막)|([1-5](?:\s*[,·、및]\s*[1-5])*)\s*(?:번\s*)?째|제\s*([1-5])\s*주/gu;
    // a part of a closed-day value that holds only n-th words ('매월 둘째', '매월 첫째주 ', '매달 2' of '매달 2, 4번째 화요일'):
    // the weekday after it takes them
    const ORD_ONLY = /^\s*(?:매\s*(?:월|달|주)\s*)?(?:(?:(?:첫|두|세|네|다섯)\s*번\s*째|첫째|둘째|셋째|넷째|다섯째|마지막|[1-5]\s*(?:번\s*)?(?:째)?|제\s*[1-5])\s*주?\s*(?:[,·、및]\s*)?)+$/u;
    const min = (t) => { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; };
    const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
    const day = /^\d{4}-\d{2}-\d{2}$/.test(date) ? new Date(`${date}T12:00:00Z`) : null;
    const wd = day ? day.getUTCDay() : -1;
    const month = day ? day.getUTCMonth() + 1 : 0;
    const nth = day ? Math.ceil(day.getUTCDate() / 7) : 0;
    const lastWeek = day ? new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth() + 1, 0)).getUTCDate() - day.getUTCDate() < 7 : false;
    const dom = day ? day.getUTCDate() : 0;
    // the public holidays fixed to a date (관공서의 공휴일에 관한 규정): on one, a place with no holiday rule of its own is
    // a thing to check (datedOn reads the rules); the lunar ones (설날·추석) move: LUNAR; the dated ones of the years
    // the code knows (부처님오신날, the substitute days): DATED. Checked (2026-10-18) against 한국천문연구원 천문우주지식정보
    // 달력자료 2027 (astro.kasi.re.kr/kor/life/post/calendarData?year=2027, 자료생성 2026-06-30, '국경일과 공휴일') and the
    // 2027년도 월력요항 우주항공청 announced on 2026-06-29 (파이낸셜뉴스 2026-06-29 lists its long weekends): 노동절 (5.1)
    // and 제헌절 (7.17) are 관공서의 공휴일 from 2026 ('올해부터 관공서의 공휴일로 지정된 노동절·제헌절'); in 2027 부처님오신날
    // (음 4.8) is 5.13 (Thu) and the 대체공휴일 are 2.9 (설날 2.7 a Sunday — in LUNAR), 5.3 (노동절 5.1 a Saturday), 7.19
    // (제헌절 7.17 a Saturday), 8.16 (광복절 8.15 a Sunday), 10.4 (개천절 10.3 a Sunday), 10.11 (한글날 10.9 a Saturday)
    // and 12.27 (기독탄신일 12.25 a Saturday); 현충일 (6.6, a Sunday) has none. 2026 is known from the planner's first day
    // (2026-10-18) on: its one public holiday left is 12.25, a Friday.
    const HOLI = { "1-1": "신정", "3-1": "삼일절", "5-1": "노동절", "5-5": "어린이날", "6-6": "현충일", "7-17": "제헌절", "8-15": "광복절",
      "10-3": "개천절", "10-9": "한글날", "12-25": "성탄절" };
    const NATIONAL = ["3-1", "7-17", "8-15", "10-3", "10-9"];   // the 국경일 among them
    const DATED = { "2027-05-03": "노동절 대체공휴일", "2027-05-13": "부처님오신날", "2027-07-19": "제헌절 대체공휴일",
      "2027-08-16": "광복절 대체공휴일", "2027-10-04": "개천절 대체공휴일", "2027-10-11": "한글날 대체공휴일", "2027-12-27": "성탄절 대체공휴일" };
    // the lunar holidays of the years the planner reaches, day by day (월력요항, 한국천문연구원: 2026 설 2.16–18 · 추석
    // 9.24–26, 2027 설 2.6–8 and the substitute 2.9 · 추석 9.14–16): public holidays ('설 연휴', '추석 연휴'), and the
    // only days a 설날·추석·명절 rule speaks of (operator 2026-10-18: '추석 연휴인지 확인' on 26 October). Each 연휴 is the
    // day before, the day itself (the second) and the day after, then a substitute day. A year here is one whose public
    // holidays the code knows; a year not here falls back to the months they can fall in, and none of its days is
    // known to be one.
    const LUNAR = { 2026: { 설날: ["2026-02-16", "2026-02-17", "2026-02-18"], 추석: ["2026-09-24", "2026-09-25", "2026-09-26"] },
      2027: { 설날: ["2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09"], 추석: ["2027-09-14", "2027-09-15", "2027-09-16"] } };
    const year = day ? LUNAR[day.getUTCFullYear()] : null;
    // the public holiday on any date (ISO), '' when none — and null in a year the code does not know (its 설·추석 and
    // substitute days are not known), unless a fixed one falls on it
    const holidayOf = (iso) => {
      const dt = new Date(`${iso}T12:00:00Z`);
      const ly = LUNAR[dt.getUTCFullYear()];
      const fixed = HOLI[`${dt.getUTCMonth() + 1}-${dt.getUTCDate()}`] || DATED[iso];
      if (fixed) return fixed;
      if (!ly) return null;
      return ly.설날.includes(iso) ? "설 연휴" : ly.추석.includes(iso) ? "추석 연휴" : "";
    };
    const holiday = !day ? "" : holidayOf(date) || "";
    // a hit of a closed-day value followed, before any word of closing, by a word of opening ('명절 정상영업', '설·추석
    // 당일 정상 운영', '공휴일 정상영업', '일요일, 공휴일 정상 영업'): the value says the place opens then — never closed,
    // to check (round-4 verifier's lunaredge: such values read closed)
    const opensAfter = (text, end) => {
      const rest = text.slice(end, end + 14);
      const cut = rest.search(/[/;]|휴무|휴관|휴업|휴점|쉼|쉬|닫|폐관|제외/u);
      return /정상|영업|운영|개관|(?<![가-힣])열(?:고|어|며|림|립|린|리)|여는|엽니다/u.test(cut < 0 ? rest : rest.slice(0, cut));
    };
    const out = [day ? `날짜: ${date} (${WD[wd]}요일)${holiday ? ` — 공휴일(${holiday})` : ""}` : "날짜 없음: 휴무와 계절별 시간은 맞춰 보지 않았다"];
    // a year LUNAR does not have: its 설·추석 and substitute days are not known, so a day of it is never known to be
    // one — said once for the date (review 2026-10-21 S9: 설날 2028 went through as '걸리는 것 없음'); the result's
    // noHolidayTable tells the planner page the same. Never a check per stop (plan_geo.dayInfo would make every place
    // of that year 'check'): the operational fix is the next year's 월력요항 in LUNAR and DATED
    const noTable = !!day && !year;
    if (noTable) out.push("그해 설·추석·대체공휴일 날짜는 사이트 표에 없음 — 공휴일이면 운영 확인");
    const flags = [];
    // a closed-day value's dated parts: '1월 1일' on that date is closed. On a public holiday of a year the code knows,
    // '공휴일'·'법정공휴일' named as a closed day ('일요일,공휴일 휴무', '… / 법정공휴일') is closed, '국경일' on 삼일절·광복절·
    // 개천절·한글날; any other wording of it ('공휴일이면 문을 열고') and a year the code does not know leave the day to
    // check. 설·추석 are read out of their lists (lunarOn).
    const datedOn = (text) => {
      const hits = [];
      for (const m of text.matchAll(/(1[0-2]|[1-9])\s*월\s*(3[01]|[12]\d|[1-9])\s*일/gu)) {
        if (+m[1] === month && +m[2] === dom) hits.push([true, `${m[1]}월 ${m[2]}일`]);
      }
      hits.push(...lunarOn(text));
      const word = /공휴일/u.test(text) ? "공휴일" : /국경일/u.test(text) ? "국경일" : "";
      if (word && holiday && (word === "공휴일" || NATIONAL.includes(`${month}-${dom}`))) {
        const at = new RegExp(`${word}(?=\\s*(?:$|[,·/、)]|및|과|와|휴무|휴관|휴업))`, "u").exec(text);   // '공휴일 및 일요일 휴무'
        const listed = !!at && !opensAfter(text, at.index + word.length);
        hits.push(year && listed ? [true, `${word}(${holiday})`] : [null, `${word} 규칙 — 그날은 ${holiday}`]);
      }
      return hits;
    };
    const dayBefore = (iso) => new Date(Date.parse(`${iso}T12:00:00Z`) - 86400000).toISOString().slice(0, 10);
    // 설·추석 out of a list ('설·추석 당일', '설날, 추석', '설날·추석 연휴', '명절연휴', '설날, 추석 전날 당일만'; 설날·설·구정 is
    // 설, 한가위 추석, 명절 both): in a year the code knows, '연휴' is closed every day of it; '당일' or the bare name is
    // closed on the day itself, '전날' on the day before, and the other days of that 연휴 are to check; a year it does
    // not know: to check in the months they can fall in
    const FEAST = /(?:설날|구정|추석|한가위|명절|(?<![가-힣])설(?=\s|[·,、/]|연휴|당일|전날|$))/u;
    // '연휴 전날' (m[3]) is the day before the 연휴's first day; a list followed by a word of opening ('명절 정상영업') is
    // never closed (opensAfter)
    const FEASTS = new RegExp(String.raw`${FEAST.source}(?:\s*(?:[·,、/및]|과|와)\s*${FEAST.source})*\s*(전날)?\s*(?:[·,]|및|과|와)?\s*(당일|연휴)?(\s*전날)?`, "gu");
    const lunarOn = (text) => {
      const seen = new Map();   // 설날 | 추석 → [closed?, how]
      for (const m of text.matchAll(FEASTS)) {
        // (a 연휴 that only says when a weekday rule holds — '설·추석 연휴 기간 중 일요일은 휴관' — closes nothing by itself:
        // closedOn reads that weekday in it)
        if (/^\s*(?:기간\s*)?(?:중|동안)에?\s*[월화수목금토일]/u.test(text.slice(m.index + m[0].length))) continue;
        const names = new Set(m[0].match(new RegExp(FEAST.source, "gu")).flatMap((w) => (w === "명절" ? ["설날", "추석"] : /추석|한가위/u.test(w) ? ["추석"] : ["설날"])));
        const open = opensAfter(text, m.index + m[0].length);
        for (const name of names) {
          const short = name === "설날" ? "설" : "추석";
          const eve = year && m[2] === "연휴" && m[3] ? dayBefore(year[name][0]) : "";
          let hit = null;
          if (!year) {
            if ((name === "설날" ? [1, 2] : [9, 10]).includes(month)) hit = [null, `${name} 규칙 — 그날이 ${short} 연휴인지`];
          } else if (eve) {
            if (date === eve) hit = [!open || null, `${short} 연휴 전날`];
            else if (year[name].includes(date)) hit = [null, `${name} 규칙 — 그날은 ${short} 연휴(연휴 전날 아님)`];
          } else if (year[name].includes(date)) {
            const shut = m[2] === "연휴" ? year[name] : [...(m[1] ? [year[name][0]] : []), ...(m[2] === "당일" || !m[1] ? [year[name][1]] : [])];
            hit = shut.includes(date) && !open ? [true, date === year[name][0] && m[2] !== "연휴" ? `${name} 전날` : m[2] === "연휴" ? `${short} 연휴` : `${name} 당일`]
              : [null, `${name} 규칙 — 그날은 ${short} 연휴${shut.includes(date) ? "" : `(${name} 당일 아님)`}`];
          }
          if (hit && !(seen.has(name) && seen.get(name)[0] === true)) seen.set(name, hit);
        }
      }
      return [...seen.values()];
    };
    // a closed-day rule read for the date: [closed?, how] — only weekdays (every week, or the n-th of the month) are
    // judged; dates, holidays and 명절 rules are named for the reader to check. On a public holiday a weekday rule that
    // opens on one ('월요일이 공휴일이면 문을 열고', '월요일이 공휴일인 경우 정상 영업') does not close it.
    // '월요일(공휴일 제외)' too: a holiday Monday is not that rule's
    const HOLI_OPEN = /공휴일\s*(?:이면|인\s*경우|일\s*경우)[^,/]{0,8}?(?:열|정상|개관|운영|영업)|공휴일\s*(?:은|는)?\s*제외/u;
    // '매주 월요일(월요일이 공휴일이면 문을 열고 다음 평일 휴관)': the closed day moves to the first 평일 after that
    // holiday (round-5 verifier: 2027-02-10, the Wednesday after the 설 Monday and its substitute Tuesday, read 'open').
    // m[1]: the weekday the rule moves (else the rule's own weekdays)
    const NEXT_WEEKDAY = /(?:([월화수목금토일])요일이?\s*)?공휴일\s*(?:이면|인\s*경우|일\s*경우)[^,/]{0,16}?(?:다음|익일|이튿날)\s*(?:평일|날)\s*(?:에\s*)?(?:휴관|휴무|휴업|쉼|쉽|닫)/u;
    const WEEKEND = (iso) => [0, 6].includes(new Date(`${iso}T12:00:00Z`).getUTCDay());
    // the day `date` is the first 평일 after a holiday on one of `days` (weekday letters): [closed?, how] or null — the
    // days between are holidays or weekends; a year the code does not know leaves it to check
    const movedOn = (text, days) => {
      if (!day || [0, 6].includes(wd) || holiday) return null;
      for (let k = 1; k <= 7; k += 1) {
        const iso = new Date(Date.parse(`${date}T12:00:00Z`) - k * 86400000).toISOString().slice(0, 10);
        const h = holidayOf(iso);
        const w = WD[new Date(`${iso}T12:00:00Z`).getUTCDay()];
        if (h === null && !WEEKEND(iso)) return days.includes(w) ? [null, `${w}요일이 공휴일이면 다음 평일 휴관 — 그날이 그 다음 평일인지`] : null;
        if (h && days.includes(w)) return [true, `${w}요일 공휴일(${iso.slice(5).replace("-", ".")} ${h}) 다음 평일`];
        if (!h && !WEEKEND(iso)) return null;   // a 평일 before it: not the first one after
      }
      return null;
    };
    // a closed-day value's parts (split at , / ; outside brackets), each {at, end, text}: the months, a season or the
    // weather a part names holds for that part only ('매주 월요일~수요일, 공휴일, 12월~2월': the months are a part of
    // their own — closed all of them)
    const partsOf = (text) => {
      const parts = [];
      let depth = 0, from = 0;
      for (let k = 0; k <= text.length; k += 1) {
        const ch = text[k];
        if (ch === "(" || ch === "[" || ch === "（") depth += 1;
        else if ((ch === ")" || ch === "]" || ch === "）") && depth) depth -= 1;
        else if (k === text.length || (!depth && /[,/;，、]/u.test(ch))) {
          parts.push({ at: from, end: k, text: text.slice(from, k) });
          from = k + 1;
        }
      }
      return parts;
    };
    // the months a part names, as ranges ('12월 ~ 2월', '12월~2월', '3~11월'; across the year end: 12 → 2), never a
    // date ('12월 31일 ~ 1월 2일')
    const MONTH_RANGE = /(?<!\d)(1[0-2]|[1-9])\s*(?:월\s*)?[~\-–]\s*(1[0-2]|[1-9])\s*월(?!\s*\d{1,2}\s*일)/gu;
    const inMonths = (x, y) => (x <= y ? month >= x && month <= y : month >= x || month <= y);
    // a season the data names with no months ('동절기(일요일 휴무)'): which days it covers is not known
    const SEASON = /동절기|하절기|겨울철?|여름철?|성수기|비수기/u;
    // the weather (round-6 final verifier: '매년 12월 ~ 2월, 우천시 휴장' read as open on every date): which days it
    // closes cannot be known ahead — every day is to check
    const WEATHER = /우천|강우|기상|날씨|강풍|태풍|폭우|폭설|폭염|한파|풍랑|(?<![가-힣])(?:비|눈)\s*(?:이|가)?\s*(?:오는|오면|올|내리는|내리면)/u;
    // a part that only says the place opens ('연중무휴', '정상 운영') — never a closing
    const OPEN_ONLY = (t) => /무휴|정상\s*(?:운영|영업|개관)/u.test(t) && !/휴무|휴관|휴장|휴업|쉬|쉼|닫|않|중단|폐/u.test(t);
    // a closed-day value's months, seasons and weather (round-6 final verifier: OO어린이랜드 '매년 12월 ~ 2월, 우천시 휴장',
    // 섬 스카이썬라인 '동절기(12월 ~ 2월)는 운영하지 않으며…' and OO평화박물관 '…, 12월~2월' were '그날 운영' all winter):
    // [{part, months: [[x, y]], season, inside}] per part, and the hits of the parts with no weekday — a month range that
    // covers the date closes it; a season with no months is to check ('규칙': settle swaps such a place for one sure to
    // open); the weather is to check (no '규칙': a place open on a dry day is not swapped for it)
    const scopeOf = (text) => {
      const hits = [];
      const parts = partsOf(text).map((p) => {
        const months = [...p.text.matchAll(MONTH_RANGE)].map((m) => [+m[1], +m[2]]);
        const season = months.length ? "" : (SEASON.exec(p.text) || [""])[0];
        const inside = months.find(([x, y]) => inMonths(x, y));
        const weekday = /[월화수목금토일]\s*요일/u.test(p.text);
        if (!weekday && !OPEN_ONLY(p.text)) {
          if (inside) hits.push([true, `${inside[0]}월~${inside[1]}월`]);
          else if (season) hits.push([null, `${season} 규칙(그 달이 자료에 없음)`]);
        }
        if (WEATHER.test(p.text)) hits.push([null, "날씨에 따라 쉬거나 운영하지 않을 수 있음"]);
        return { ...p, months, season, inside };
      });
      return { hits, parts };
    };
    const closedOn = (text) => {
      text = spell(text);
      const scope = scopeOf(text);
      const hits = [...scope.hits];
      const partAt = (k) => scope.parts.find((p) => k >= p.at && k < p.end) || { months: [], season: "" };
      const moved = NEXT_WEEKDAY.exec(text);
      if (moved) {
        const days = moved[1] ? [moved[1]] : [...text.matchAll(/([월화수목금토일])요일/gu)].map((x) => x[1]);
        const hit = movedOn(text, days);
        if (hit) hits.push(hit);
      }
      let prevEnd = 0;   // the end of the weekday named before this one: its n-th words are its own
      for (const m of text.matchAll(/([월화수목금토일](?:\s*[·,、및]\s*[월화수목금토일])*)\s*요일/gu)) {
        const days = m[1].match(/[월화수목금토일]/gu);
        const end = m.index + m[0].length;
        // the n-th a weekday takes are the ones of its own part of the value ('매월 둘째, 넷째 월요일, 일요일을 제외한 …':
        // '둘째, 넷째' are 월요일's, never 일요일's — 2026-10-24 SJ-D03, a 14-character window gave a Sunday the Monday's
        // n-th), with the parts before it that hold only n-th words ('매월 첫째 / 셋째 일요일'), never past another weekday
        const part = partAt(m.index);
        let from = part.at ?? 0;
        for (let q = scope.parts.indexOf(part) - 1; q >= 0 && ORD_ONLY.test(scope.parts[q].text); q -= 1) from = scope.parts[q].at;
        const before = text.slice(Math.max(from, prevEnd), m.index);
        prevEnd = end;
        // (the n-th written in words or digits: '넷째 주', '첫 번째', '4째주', '2, 4번째', '1·3번째', '제4주' — round-7 review:
        // 갈비스토리 '4째주 일요일 휴무' was read as every Sunday; 2026-10-24 SJ-D03: '매월 첫 번째, 세 번째 수요일' as every
        // first one only)
        const ords = [];
        for (const x of before.matchAll(ORD_G)) {
          if (x[1]) ords.push(x[1].replace(/\s+/gu, ""));
          else ords.push(...(x[2] || x[3]).match(/[1-5]/gu));
        }
        if (!days.includes(WD[wd])) continue;
        // a weekday the value takes out ('일요일을 제외한 관공서의 공휴일', '공휴일(일요일 제외)') is no closed day of its own —
        // unless the part says the place opens ('연중 운영(월요일 제외)'): then which way it goes is the reader's to check
        if (/^\s*(?:을|를|은|는)?\s*제외/u.test(text.slice(end))) {
          if (/무휴|개방|운영|영업|개관/u.test(part.text || "")) hits.push([null, `${WD[wd]}요일 '제외' 규칙 — 쉬는 날인지 자료로 알 수 없음`]);
          continue;
        }
        // a weekday a 설·추석 clause holds ('(단, 설·추석 연휴 기간 중 일요일은 휴관)'): only on the days of that 연휴 — then to
        // check; on any other day it is no rule (2026-10-24 SJ-D03: every Sunday of 국립세종도서관 read as closed)
        const lead = text.slice(Math.max(...["(", "（", "[", ",", "/", ";", "，"].map((ch) => text.lastIndexOf(ch, m.index - 1) + 1)), m.index);
        if (FEAST.test(lead) && /(?:기간|연휴)\s*(?:중|동안)|중에?\s*$|경우|이면/u.test(lead)) {
          const names = [...new Set(lead.match(new RegExp(FEAST.source, "gu")).flatMap((w) => (w === "명절" ? ["설날", "추석"] : /추석|한가위/u.test(w) ? ["추석"] : ["설날"])))];
          const inside = names.filter((n) => (year ? year[n].includes(date) : (n === "설날" ? [1, 2] : [9, 10]).includes(month)));
          const said = inside.map((n) => (n === "설날" ? "설" : n)).join("·");
          if (inside.length) hits.push([null, `${said} 연휴 중 ${WD[wd]}요일 규칙 — ${year ? `그날은 ${said} 연휴의 ${WD[wd]}요일` : `그날이 ${said} 연휴인지`}`]);
          continue;
        }
        if (holiday && HOLI_OPEN.test(text)) continue;   // datedOn names the holiday to check
        // a weekday rule inside a part with months holds in those months only; inside a season with no months
        // ('동절기(일요일 휴무)') whether the date is in it is not known
        if (part.months.length && !part.inside) continue;
        const when = part.inside ? `${part.inside[0]}월~${part.inside[1]}월 ` : "";
        if (part.season) hits.push([null, `${part.season} ${WD[wd]}요일 규칙(그 달이 자료에 없음)`]);
        else if (/격주/u.test(before)) hits.push([null, `${when}격주 ${WD[wd]}요일 규칙`]);
        else if (ords.length) {
          const on = ords.some((o) => (o === "마지막" ? lastWeek : (ORD[o.replace(/번째$|째$/u, "")] ?? +o) === nth));
          hits.push([on, `${when}${ords.join("·")} ${WD[wd]}요일 규칙 — 그날은 ${nth}째 ${WD[wd]}요일${lastWeek ? "(마지막 주)" : ""}`]);
        } else hits.push([true, `${when}매주 ${WD[wd]}요일`]);
      }
      return hits;
    };
    // '화요일~목요일', '토~일요일' → '화·수·목요일' (a range of weekdays named by its ends); the tildes the data also writes
    // ('09:00∼18:00' — U+223C, U+FF5E, U+301C) read as '~' (round-7 review: 구 일본 제18은행's hours went unread)
    const spell = (text) => text.replace(/[∼～〜]/gu, "~").replace(/([월화수목금토일])(?:요일)?\s*~\s*([월화수목금토일])요일/gu, (all, x, y) => {
      const order = "월화수목금토일";
      let i = order.indexOf(x);
      const out = [];
      for (let n = 0; n < 7; n += 1) {
        out.push(order[i]);
        if (order[i] === y) break;
        i = (i + 1) % 7;
      }
      return `${out.join("·")}요일`;
    });
    // the hours that hold on the date: the season whose months cover it (a value with 하절기/동절기 and no months is
    // not read), then the weekday's own hours when the value gives hours by weekday; {seg, open, close, last} or
    // {seg, why} when the date's hours cannot be read from it
    const hoursFor = (raw) => {
      const text = spell(raw);
      // the weekdays only it opens on ('(매주 목. 금. 토. 일 요일만 영업)'): another day is no day it opens (QA 2026-10-26 F05)
      const only = day ? onlyDays(text) : null;
      if (only && !only.days.has(wd) && !(holiday && only.holiday)) return { seg: text, shut: `${only.words}만 영업` };
      let seg = text;
      const ranges = [...text.matchAll(/(1[0-2]|[1-9])월\s*~\s*(1[0-2]|[1-9])월/gu)];
      if (ranges.length) {
        const pick = ranges.findIndex((m) => {
          const x = +m[1], y = +m[2];
          return x <= y ? month >= x && month <= y : month >= x || month <= y;
        });
        if (pick < 0) return { seg: text, why: `${month}월이 든 계절 시간이 없음` };
        const from = Math.max(0, text.lastIndexOf("[", ranges[pick].index), pick ? ranges[pick - 1].index + ranges[pick - 1][0].length : 0);
        const to = pick + 1 < ranges.length ? ranges[pick + 1].index : text.length;
        // (the season's own part: from its '[' or the last break before its months — '/', '|', a line, '※' — never the
        // end of the season before it: round-7 review, '마감 17:30) / 11월~2월 …' in the reader's note)
        const at = pick ? Math.max(from, ...["/", "|", "\n", "※"].map((ch) => text.lastIndexOf(ch, ranges[pick].index - 1) + 1)) : 0;
        seg = text.slice(at, to).replace(/[\s[(（]*(?:하절기|동절기|여름|겨울)?[\s[(（]*$/u, "").replace(/[\s/|]+$/u, "").trim();
      } else if (/하절기|동절기|여름|겨울|성수기|비수기/u.test(text)) {
        // a time for each season and no months (OO근대건축관 '동절기 09:00 - 17:00 하절기 09:00 - 18:00'): the hours
        // every season keeps — the latest opening, the earliest closing — with a check (round-7 review: a visit
        // planned 17:30–18:10 on a November day passed, unread)
        const all = [...text.matchAll(/(\d{1,2}):(\d{2})\s*[~–-]\s*(\d{1,2}):(\d{2})/gu)].map((m) => [+m[1] * 60 + +m[2], +m[3] * 60 + +m[4]]).filter(([a, b]) => b > a);
        if (all.length < 2) return { seg: text, why: "계절 구분의 달이 이 값에 없음" };
        const open = Math.max(...all.map((x) => x[0])), close = Math.min(...all.map((x) => x[1]));
        if (close <= open) return { seg: text, why: "계절 구분의 달이 이 값에 없음" };
        // (the last entry the value says as a span before closing holds in every season: '폐관 30분 전까지 입장')
        const before = entryBefore(text);
        return { seg: text.trim(), open, close, last: before !== null ? close - before : null, season: `${hhmm(open)}~${hhmm(close)}` };
      }
      // ('입장은 종료 30분 전까지', '관람종료 1시간 전까지' hold in every season, every session and every room)
      const before = entryBefore(text);
      // one day's hours of a part of the value: the part for the date's day when it gives hours by day group (평일·주말·
      // 공휴일·weekdays — dayPart; never the first range whatever the day: QA 2026-10-26 F03), then its sessions or its range
      const readDay = (part) => {
        let s = part;
        const byDay = day ? dayPart(s, wd, !!holiday) : null;
        if (byDay && byDay.why) return { seg: s, why: byDay.why };
        if (byDay) s = byDay.seg;
        const range = /(\d{1,2}):(\d{2})\s*[~–-]\s*(\d{1,2}):(\d{2})/u.exec(s);
        if (!range) return { seg: s, why: "시각을 읽을 수 없음" };
        // the sessions of the day ('[1회차] 09:30~13:00 (입장 마감 12:30) [2회차] 14:00~17:30 …'): every range, each with its
        // own last entry — never only the first (never for a day group's own hours: one range)
        const sessions = byDay ? null : sessionsIn(s, before);
        if (sessions) {
          const z = sessions[sessions.length - 1];
          return { seg: s.trim(), open: sessions[0].open, close: z.close, last: z.last, sessions };
        }
        const open = +range[1] * 60 + +range[2];
        const close = +range[3] * 60 + +range[4];
        const own = lastAt(s);
        return { seg: s.trim(), open, close, last: own !== null ? own : before !== null ? close - before : null };
      };
      // rooms with hours of their own ('[인문예술자료실/일반자료실]- 평일 09:00~21:00- 주말 09:00~18:00[어린이자료실]-09:00~18:00'):
      // each room's hours that day; the place is open from the earliest opening to the latest closing, and a visit
      // outside one room's hours is the reader's to check (QA 2026-10-26 F03: a weekday visit after 18:00 passed with
      // nothing said of the children's room closing then)
      const rooms = roomParts(seg);
      if (!rooms) return readDay(seg);
      const read = rooms.map((x) => ({ name: x.name, ...readDay(x.seg) })).filter((x) => !x.why);
      if (!read.length) return { seg, why: `시설별 시간 가운데 ${day ? `${WD[wd]}요일` : "그날"} 시간을 읽을 수 없음` };
      const open = Math.min(...read.map((x) => x.open));
      const close = Math.max(...read.map((x) => x.close));
      const z = read.find((x) => x.close === close);
      return { seg: seg.trim(), open, close, last: z.last, rooms: read.map((x) => ({ name: x.name, open: x.open, close: x.close, last: x.last })) };
    };
    const rows = [];
    const stopsOut = [];   // per stop: {key, name, day: 'open' | 'closed' | 'unknown', notes, flags, checks}
    const legsOut = [];    // per leg: {from, to, m, gap, routes, flag}
    stops.slice(0, 12).forEach((st, i) => {
      const key = this.keyFor(st.page);
      const d = key ? this.docs[key] : null;
      const s = min(st.start), e = min(st.end);
      const head = `${i + 1}. ${st.start || "?"}–${st.end || "?"} ${d ? `${d.t} ${key}` : `${String(st.page).slice(0, 80)} (이 사이트의 장소가 아님)`}`;
      rows.push({ d, key, s, e });
      if (!d) {
        out.push(head);
        flags.push(`${i + 1}번: 사이트의 장소 경로가 아니다`);
        stopsOut.push({ key: "", name: String(st.page).slice(0, 80), day: "unknown", notes: [], flags: ["사이트의 장소 경로가 아님"] });
        return;
      }
      const f = d.f || {};
      const notes = [];
      const mine = [];       // this stop's flags (without the stop number)
      const checks = [];     // what the reader is to check for this stop on that date (not a fault of the plan)
      let dayState = day ? "open" : "unknown";
      let disputed = "";       // the sources' rules, when they disagree on whether that day is closed
      let todayHours = null;   // a dated notice's own hours for that date
      const hours = [];        // the hours read for that date: [{open, close, last}] (the planner's own fit test)
      // a place whose inside is not open to visitors by its own data (f.ex — plan_state.isOutside): said as what it is,
      // and an hours value that is only those words ('내부 관람 불가 ※ 자세한 사항은 전화 문의 요망') is no hours left
      // unread (outside tester 2026-10-23: the check said only that 구 제일사료주식회사 공장's hours could not be read)
      const outside = isOutside(f) ? { p: outsideSrc(f) } : null;
      const outsideWords = (t) => !!outside && !/\d{1,2}\s*:\s*\d{2}|\d{1,2}\s*시/u.test(t) && f.ex.some((x) => x.w && String(t).includes(x.w));
      const flag = (text) => { flags.push(`${i + 1}번 ${d.t}: ${text}`); mine.push(text); };
      if (rows.slice(0, -1).some((r) => r.key === key)) {
        notes.push("같은 날 두 번째 방문");
        checks.push("같은 날 다시 들어갈 수 있는지(재입장) 확인 필요");
      }
      if (s !== null && e !== null && e <= s) {
        notes.push("끝 시각이 시작 시각보다 이르다");
        flag("끝 시각이 시작보다 이르다");
      }
      if (day) {
        const dated = (f.n || []).filter((n) => n.s <= date && date <= n.e);
        for (const n of dated) {
          const what = n.k === "closed" ? "휴관" : n.k === "open" ? "개관" : `운영 ${n.f || ""}–${n.t || ""}${n.l ? `, 입장마감 ${n.l}` : ""}`;
          notes.push(`그날의 날짜별 공지: ${what} (get_pages의 '날짜별 공지' 줄)`);
          if (n.k === "closed") {
            flag("그날 날짜별 공지로 휴관 — 일정에서 뺀다");
            dayState = "closed";
          } else if (n.f && n.t) {
            todayHours = { open: min(n.f), close: min(n.t), last: n.l ? min(n.l) : null, seg: `날짜별 공지 ${n.f}–${n.t}${n.l ? ` 입장마감 ${n.l}` : ""}` };
          }
        }
        if (!dated.length) {
          const said = [];   // each source's rule and whether it closes the place that day (true, false, null)
          for (const c of f.c || []) {
            const hits = [...closedOn(c.t), ...datedOn(c.t)];
            const yes = hits.filter((h) => h[0] === true);
            const maybe = hits.filter((h) => h[0] === null);
            said.push({ c, shut: yes.length ? true : maybe.length ? null : false });
            if (yes.length) {
              notes.push(`그날 정기 휴무 — ${c.p}: '${c.t}' (${yes.map((h) => h[1]).join(", ")})`);
              flag(`${date}(${WD[wd]})은 정기 휴무(${c.p} '${c.t}') — 일정에서 뺀다`);
              dayState = "closed";
            } else if (maybe.length) {
              notes.push(`그날 휴무인지 규칙만으로 알 수 없음 — ${c.p}: '${c.t}'`);
              if (maybe.some((h) => /격주/u.test(h[1]))) flag(`${maybe.map((h) => h[1]).join(", ")} — 그날 휴무인지 확인 필요`);
              else checks.push(`${maybe.map((h) => h[1]).join(", ")} — 그날 쉬는지 확인 필요 ('${c.t}')`);
              if (dayState === "open") dayState = "unknown";
            } else {
              notes.push(`그 요일은 정기 휴무 요일이 아님 — ${c.p}: '${c.t}'${/공휴일|명절|설|추석|\d+월\s*\d+일|시장이|임시/u.test(c.t) ? " (날짜·공휴일 규칙은 그날이 해당하는지 따로 확인)" : ""}`);
            }
          }
          // sources that disagree on that day (one closes it, another does not — 완주옥: 시 '연중무휴', 한국관광공사
          // '매주 수요일'): both said, to be checked by phone (CLAUDE.md 3절 2항); the planner still keeps the place out
          // and words its reason as the disagreement, never as a fact (round-6 verifier)
          if (said.some((x) => x.shut === true) && said.some((x) => x.shut === false)) {
            disputed = said.map((x) => `${x.c.p} '${x.c.t}'`).join(" · ");
            notes.push(`출처마다 쉬는 날이 다름: ${disputed} — 방문 전 전화 확인`);
          }
          if (!(f.c || []).length && f.kd !== "stay") {
            notes.push("쉬는 날: 사이트에 없음(확인 필요)");
            checks.push("쉬는 날이 사이트에 없음 — 그날 여는지 확인 필요");
            if (dayState === "open") dayState = "unknown";
          }
          // (not for a place whose own rule names that day — '공휴일', '설날·추석 당일', '명절': that rule's line says it —
          // nor for a stay: a night's stay has no day to check)
          if (holiday && f.kd !== "stay" && dayState !== "closed" && !checks.some((x) => /(?:공휴일|국경일|설날|추석) 규칙/u.test(x))) {
            checks.push(`그날은 공휴일(${holiday}) — 공휴일 운영은 사이트 자료에 없음, 그날 여는지 확인 필요`);
          }
        }
        // (a value read as no hours: a check when another source's hours were read or it says 예약 — round 7 review
        // A07: 온새미로's 시 '예약제' beside TourAPI's times went as a place open then, with nothing to check)
        const unread = [];
        for (const h of todayHours ? [{ p: "날짜별 공지", t: "", r: todayHours }] : f.h || []) {
          const r = h.r || hoursFor(h.t);
          // (a weekday the value says it does not open on — '목·금·토·일요일만 영업': closed that day, as a closed day is)
          if (r.shut) {
            flag(`${date}(${WD[wd]})은 영업하는 요일이 아님(${h.p} '${h.t}') — 일정에서 뺀다`);
            dayState = "closed";
            continue;
          }
          if (r.why && outsideWords(h.t)) {
            notes.push(`이용시간 — ${h.p}: ${OUTSIDE_WORDS}(자료: '${h.t}')`);
            continue;
          }
          if (r.why) {
            notes.push(`이용시간 — ${h.p}: '${h.t}' (그날 시각을 하나로 읽지 않음: ${r.why} — 확인 필요)`);
            unread.push(h);
            continue;
          }
          hours.push({ open: r.open, close: r.close, last: r.last, ...(r.sessions ? { sessions: r.sessions } : {}) });
          if (r.season) checks.push(`이용시간 — ${h.p}: 계절마다 시간이 달라(달 구분은 사이트에 없음) 모든 계절에 맞는 ${r.season}로 봄 — 그날 시간 확인 필요`);
          const bad = [];
          const at = (x) => `${hhmm(x)}${iga(hhmm(x))}`;   // '10:00가', '17:40이'
          if (r.sessions) {
            // a visit keeps to one session: it starts inside one, by that one's last entry, and ends by its closing; a
            // start between two is said as the gap it is (2026-10-24 SJ-D02: 14:00–16:00 at 국립어린이박물관's 2회차 read as
            // past its 13:00 closing, 13:30 as nothing but that)
            const ss = r.sessions;
            const nm = (x) => (x.name ? `${x.name}(${hhmm(x.open)}~${hhmm(x.close)})` : `운영 시간 ${hhmm(x.open)}~${hhmm(x.close)}`);
            const k = s === null ? -1 : ss.findIndex((x) => s >= x.open && s < x.close);
            const next = s === null ? -1 : ss.findIndex((x) => x.open > s);
            if (s !== null && s < ss[0].open) bad.push(`시작 ${at(s)} 여는 시각 ${hhmm(ss[0].open)}보다 이름`);
            else if (s !== null && k < 0 && next > 0) {
              const b = ss[next];
              bad.push(`시작 ${at(s)} ${nm(ss[next - 1])}·${nm(b)} 사이 — ${b.name || "다음 운영 시간"} 시작 ${hhmm(b.open)}`);
            } else if (k >= 0) {
              const x = ss[k];
              if (e !== null && e > x.close) bad.push(`끝 ${at(e)} ${nm(x)} 끝 ${hhmm(x.close)}보다 늦음`);
              if (x.last !== null && s > x.last) bad.push(`시작 ${at(s)} ${x.name ? `${x.name} ` : ""}입장·주문 마감 ${hhmm(x.last)}보다 늦음`);
            } else {
              if (e !== null && e > r.close) bad.push(`끝 ${at(e)} 닫는 시각 ${hhmm(r.close)}보다 늦음`);
              if (s !== null && r.last !== null && s > r.last) bad.push(`시작 ${at(s)} 입장·주문 마감 ${hhmm(r.last)}보다 늦음`);
            }
            // (sessions a value names as 회차, or with a booking: which one and its ticket times are the reader's to check)
            if (/회차|예약|발권|매표/u.test(h.t)) {
              checks.push(`이용시간 — ${h.p}: 하루 ${ss.length}회차(${ss.map((x) => `${hhmm(x.open)}~${hhmm(x.close)}`).join(" · ")})${/예약/u.test(h.t) ? "·예약 안내 있음" : ""} — 들어갈 회차와 예약·발권 마감 확인 필요`);
            }
          } else {
            if (s !== null && s < r.open) bad.push(`시작 ${at(s)} 여는 시각 ${hhmm(r.open)}보다 이름`);
            if (e !== null && r.close > r.open && e > r.close) bad.push(`끝 ${at(e)} 닫는 시각 ${hhmm(r.close)}보다 늦음`);
            if (s !== null && r.last !== null && s > r.last) bad.push(`시작 ${at(s)} 입장·주문 마감 ${hhmm(r.last)}보다 늦음`);
            // (rooms with hours of their own: the visit within the place's hours but outside a room's — that room's
            // hours to check, never a flag: which room the reader goes to is not known)
            const outRooms = (r.rooms || []).filter((x) => (s !== null && (s < x.open || (x.last !== null && s > x.last))) || (e !== null && e > x.close));
            if (!bad.length && outRooms.length) {
              checks.push(`이용시간 — ${h.p}: 시설마다 시간이 다름 — ${outRooms.map((x) => `${x.name} ${hhmm(x.open)}~${hhmm(x.close)}`).join(" · ")}은 계획한 시각과 맞지 않음, 갈 시설의 그날 시간 확인 필요`);
            }
          }
          notes.push(`그날 시간 — ${h.p}: ${r.seg}${r.last !== null && !/마감/u.test(r.seg) ? ` (입장 마감 ${hhmm(r.last)})` : ""}${bad.length ? ` → ${bad.join(", ")}` : " → 계획한 시각은 이 시간 안"}`);
          if (bad.length) flag(`${h.p} 기준 ${bad.join(", ")}`);
        }
        // (only a value with no clock time in it — '예약제', '전화문의'; one whose times the reader cannot read by day,
        // '월요일 09:00~18:00 화요일~일요일 09:00~21:30', says no other hours)
        for (const h of unread.filter((x) => !/상시|24\s*시간|연중\s*개방|\d{1,2}\s*:\s*\d{2}|\d{1,2}\s*시/u.test(x.t))) {
          if (hours.length) checks.push(`${h.p} 이용시간 '${h.t}' — 다른 출처의 시각과 달라 방문 전 전화 확인`);
          else if (/예약/u.test(h.t)) checks.push(`${h.p} 이용시간 '${h.t}' — 그 시각에 여는지 방문 전 확인 필요`);
        }
        // (no hours read for that date at all — '11:00~20:00 / 동절기(일요일 휴무)', '10:30~재료 소진 시…전화 문의', '입도
        // 2회 / 일': whether it opens at the planned time is to check (review 2026-10-21 S13: 20:30 at a place whose
        // value says 11:00~20:00 went as '그날 운영' with nothing to check). Worded '이용시간 — …' so plan_geo.dayInfo
        // keeps the day's state; not for a value that says it is always open, one the 예약 line above has, or a stay)
        // (nor on a day the place is closed: a value with no hours for its closed weekday says nothing to check)
        if (!hours.length && !todayHours && f.kd !== "stay" && dayState !== "closed") {
          for (const h of unread.filter((x) => !/상시|24\s*시간|연중\s*개방/u.test(x.t)
            && !(/예약/u.test(x.t) && !/\d{1,2}\s*:\s*\d{2}|\d{1,2}\s*시/u.test(x.t)))) {
            checks.push(`이용시간 — ${h.p}: '${h.t}' — 그날 시각을 하나로 읽지 못해 계획한 시각에 여는지 확인 필요`);
          }
        }
        if (!(f.h || []).length && !todayHours && f.kd !== "stay") {
          notes.push("이용시간: 사이트에 없음(확인 필요)");
          checks.push("이용시간이 사이트에 없음 — 그 시각에 여는지 확인 필요");
        }
      }
      if (outside) {
        notes.push(`관람: ${OUTSIDE_WORDS}(자료: ${outside.p})`);
        // (only: every hours value is only those words — the page's card then shows them in place of the hours)
        if ((f.h || []).length && f.h.every((h) => outsideWords(h.t))) outside.only = 1;
      }
      for (const c of checks) notes.push(`확인 필요: ${c}`);
      out.push(`${head}\n   ${notes.join("\n   ") || "확인할 값 없음"}`);
      stopsOut.push({ key, name: d.t, day: dayState, notes, flags: mine, checks, hours, ...(disputed ? { disputed } : {}),
        ...(outside ? { outside } : {}) });
    });
    const rad = (x) => (x * Math.PI) / 180;
    for (let i = 0; i + 1 < rows.length; i += 1) {
      const a = rows[i], b = rows[i + 1];
      if (!a.d || !b.d || a.key === b.key) continue;
      const ga = (a.d.f || {}).g, gb = (b.d.f || {}).g;
      const gap = a.e !== null && b.s !== null ? b.s - a.e : null;
      let dist = "";
      let m = null;
      if (ga && gb) {
        const h = Math.sin(rad(gb[0] - ga[0]) / 2) ** 2 + Math.cos(rad(ga[0])) * Math.cos(rad(gb[0])) * Math.sin(rad(gb[1] - ga[1]) / 2) ** 2;
        m = Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
        dist = m >= 1000 ? `직선 ${(m / 1000).toFixed(1)}km` : `직선 ${m}m`;
      } else dist = "좌표 없음: 거리 모름";
      const shared = ((a.d.f || {}).b || []).filter((r) => ((b.d.f || {}).b || []).includes(r));
      const bus = (a.d.f || {}).b && (b.d.f || {}).b
        ? (shared.length ? `두 곳 근처 정류장에 같은 노선 ${shared.join("·")} (방향·시각·정류장 순서는 시간표와 교통 가이드로 확인)` : "두 곳 근처 정류장에 같은 노선 없음")
        : "근처 정류장 노선: 한쪽 또는 양쪽에 자료 없음";
      let said = "";        // the leg's words (a name of its own: 'move' is the reader's way of moving)
      let legFlag = "";
      let open = false;     // a leg without a car the site cannot confirm that is no flag (into or out of a stay)
      if (gap === null) said = "계획한 이동 시간: 시각이 없음";
      else if (gap <= 0) {
        said = `계획한 이동 0분 — 서로 다른 두 곳 사이에 이동 시간이 없다`;
        legFlag = `${dist}인데 이동 시간을 두지 않음`;
        flags.push(`${i + 1}→${i + 2}번 ${a.d.t} → ${b.d.t}: ${legFlag} — 이 구간을 따로 한 줄('이동: ${dist}, 소요 시간 사이트에 없음')로 두고, 다음 장소 시작을 앞 장소 끝과 같게 두지 않는다`);
      } else if (m !== null && gap < legBound(m, move)) {
        said = `계획한 이동 ${gap}분 — 직선 거리만으로도 이 시간에 갈 수 없는 거리`;
        legFlag = `${dist}인데 여유 ${gap}분 — 직선 거리만으로도 갈 수 없는 시간`;
        flags.push(`${i + 1}→${i + 2}번 ${a.d.t} → ${b.d.t}: ${legFlag} — 여유를 늘리거나 가까운 곳으로 바꾼다`);
      } else if (walkOnly(move) && !shared.length && (m === null || m > WALK_M)) {
        // without a car, in a city whose data names no bus for its places (outside review 2026-10-24 C05·C08): a leg
        // longer than a walk is one the site cannot confirm — longer than RIDE_M between two places it is sent back;
        // shorter, or into or out of a night's stay, or with a point missing, it stays as a way to check (open)
        const stay = (a.d.f || {}).kd === "stay" || (b.d.f || {}).kd === "stay";
        said = `계획한 이동 ${gap}분 — 차 없이 ${m === null ? "좌표가 없어 걸어서 갈 수 있는지 모르는" : `${dist}로 걷기엔 먼`} 구간이고 사이트에 두 곳을 잇는 버스 노선이 없음(이동 확인 필요)`;
        if (stay || m === null || m <= RIDE_M) open = true;
        else {
          legFlag = `차 없이 ${dist} — 사이트에 두 곳을 잇는 버스 노선이 없고 걸어서 갈 거리도 아니다`;
          flags.push(`${i + 1}→${i + 2}번 ${a.d.t} → ${b.d.t}: ${legFlag} — 가까운 곳(직선 ${RIDE_M / 1000}km 안, 걸어서 갈 곳이면 ${WALK_M / 1000}km 안)으로 바꾼다`);
        }
      } else if (m === null && gap < regionFloor(a.d, b.d, move)) {
        // no distance, but the pages name two 권역 (final check 2026-10-18: 동국사 → a place with no point → 섬
        // with 10 minutes passed): under the floor, a leg across the city is not one
        const floor = regionFloor(a.d, b.d, move);
        said = `계획한 이동 ${gap}분 — 좌표가 없어 거리를 모르는 다른 권역 사이(${regionOf(a.d)} → ${regionOf(b.d)})`;
        legFlag = `좌표가 없어 거리를 모르는 다른 권역 사이(${regionOf(a.d)} → ${regionOf(b.d)})인데 여유 ${gap}분 — 권역을 옮기는 구간의 계획 여유 ${floor}분보다 짧음`;
        flags.push(`${i + 1}→${i + 2}번 ${a.d.t} → ${b.d.t}: ${legFlag} — 여유를 늘리거나 가까운 곳으로 바꾼다`);
      } else said = `계획한 이동 ${gap}분 — 사이트에 이 구간의 소요 시간은 없다(직선거리는 이동 시간이 아님)`;
      out.push(`구간 ${i + 1}→${i + 2}: ${a.d.t} → ${b.d.t}: ${dist} · ${said} · ${bus}`);
      legsOut.push({ from: i, to: i + 1, m, gap, routes: shared, flag: legFlag, ...(open ? { open: true } : {}),
        a: ga ? { name: a.d.t, lat: ga[0], lng: ga[1] } : null, b: gb ? { name: b.d.t, lat: gb[0], lng: gb[1] } : null });
    }
    // nothing to fix is not nothing to check (review 2026-10-21 S12: three stops '확인 필요: 그날은 공휴일(성탄절)…' closed
    // with '이 사이트 자료로 걸리는 것 없음')
    const checkN = stopsOut.reduce((a, x) => a + (x.checks || []).length, 0);
    const moveLine = "이동 구간은 여전히 '이동 확인 필요'다(사이트에 소요 시간이 없음).";
    out.push(flags.length ? `고칠 것 ${flags.length}건:\n- ${flags.join("\n- ")}\n고친 일정으로 답한다(고친 일정을 다시 check_plan으로 확인할 수 있으면 확인한다).`
      : checkN || noTable ? `고칠 것 없음.${checkN ? ` ‘확인 필요’ ${checkN}건은 답의 표에 ‘확인 필요’로 남긴다.` : ""}`
        + `${noTable ? " 그해 공휴일 표가 없어 그날이 공휴일인지 알 수 없다 — 답에 ‘공휴일이면 운영 확인’을 적는다." : ""} ${moveLine}`
        : `이 사이트 자료로 걸리는 것 없음. ${moveLine}`);
    return { text: out.join("\n"), flags, stops: stopsOut, legs: legsOut, ...(noTable ? { noHolidayTable: true } : {}) };
  }

  titleOf(raw) {
    const key = this.keyFor(raw);
    return key ? this.docs[key].t : String(raw).slice(0, 40);
  }

  // ---------------------------------------------------------------- the lines block (relevantLines, planLines)
  /** The lines' index, built once: {keys (sorted), post: token → keys, cost: key → estimated tokens with its line
   *  break, prio: key → 0..1 (more key-fact slots, a place with two or more of them in the core catalog more),
   *  names: [[squashed name, place key]] longest first, orig: an article's original address (compared form) → its
   *  key, areas: area word → keys, outlets: the articles' outlets as a question names them (plainWords), strong: the
   *  idf from which a word of an article's title tells it apart (the median of the titles' words)}. */
  lineIndex() {
    if (this.#li) return this.#li;
    const keys = Object.keys(this.lines).sort();
    const post = new Map();
    const cost = new Map();
    const prio = new Map();
    const names = [];
    const orig = new Map();
    const areas = new Map();
    const outletNames = new Set();
    const titleWords = new Set();
    for (const k of keys) {
      const line = this.lines[k];
      const d = this.docs[k];
      cost.set(k, estimateTokens(line) + 1);
      // (every place is in the core catalog while its budget allows, a thin one too: the core alone no longer marks
      // the places with key facts)
      const slots = slotCount(line);
      prio.set(k, (this.core.has(k) && slots >= 2 ? 0.5 : 0) + Math.min(slots, 5) / 10);
      for (const t of new Set(tokens(line))) (post.get(t) || post.set(t, []).get(t)).push(k);
      if (d.k === "place") {
        for (const n of new Set([d.t, ...otherNames(d), ...Object.values(d.n || {})])) {
          const s = squash(n);
          if ([...s].length >= nameMin(s)) names.push([s, k]);
        }
        for (const w of new Set(areaWords(d))) (areas.get(w) || areas.set(w, []).get(w)).push(k);
      } else if (d.k === "abroad") {
        const m = /^원문: (\S+)/mu.exec(d.x || "");
        if (m) orig.set(normUrl(m[1]), k);
        // the outlet: the A line's second field without its date and language (chat_index.py abroad: 'CNN Travel
        // 2017-07-12 en', 'Lonely Planet 날짜 없음 en'; an SNS post has none)
        const outlet = (line.split(" | ")[1] || "").replace(/\s*(?:\d{4}(?:-\d{2}){0,2}|날짜 없음)(?:\s+[a-z]{2}(?:-[a-z]+)?)?\s*$/iu, "").trim();
        if (outlet) outletNames.add(outlet);
        for (const t of tokens(d.t)) titleWords.add(t);
      }
    }
    names.sort((a, b) => b[0].length - a[0].length || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : 1));
    // by their first two characters, so a text is matched only against the names that can start in it
    const heads = new Map();
    names.forEach(([n, k], i) => (heads.get(n.slice(0, 2)) || heads.set(n.slice(0, 2), []).get(n.slice(0, 2))).push([n, k, i]));
    // an outlet as a question names it: its whole name (and without 'the'), a name in brackets ('コレポ (Korepo)'), and
    // the one word of a name that is not generic ('CNN Travel' → cnn, 'The Korea Herald' → herald) unless a page of
    // the site has it in its title ('Gwangju News' → not gwangju: the bus guide's 광주) — a single word is at least 3
    // letters, a Hangul, kana or CJK name at least 3 characters
    const titled = (w) => this.keys.some((k) => !["abroad", "video"].includes(this.docs[k].k) && this.head.get(k).has(w));
    const outlets = new Set();
    for (const o of [...outletNames].sort()) {
      for (const name of [o.replace(/\s*\([^)]*\)\s*/gu, " "), ...[...o.matchAll(/\(([^)]*)\)/gu)].map((m) => m[1])]) {
        const p = plainWords(name);
        if (!p) continue;
        const words = p.split(" ");
        const single = (w) => w.length >= 3 && !/^\d+$/u.test(w) && !OUTLET_GENERIC.has(w) && !titled(w);
        const ok = (v) => (v.includes(" ") ? true                         // several words: the name as written
          : /^[\p{Script=Latin}\p{Script=Cyrillic}\p{N}]+$/u.test(v) ? single(v)   // one Latin word: as a word of its own
            : [...v].length >= 3);                                         // Hangul, kana, CJK (トラベルjp)
        for (const v of new Set([p, p.replace(/^the /u, "")])) if (ok(v)) outlets.add(v);
        const rest = words.filter((w) => /^[\p{Script=Latin}\p{Script=Cyrillic}]+$/u.test(w) && !OUTLET_GENERIC.has(w));
        if (words.length > 1 && rest.length === 1 && single(rest[0])) outlets.add(rest[0]);
      }
    }
    const idfs = [...titleWords].map((t) => this.idf(t)).sort((a, b) => a - b);
    const strong = idfs.length ? idfs[Math.floor(idfs.length / 2)] : Infinity;
    this.#li = { keys, post, cost, prio, names, heads, orig, areas, outlets: [...outlets], strong, refs: new Map(),
      min: Math.min(...cost.values()) };
    return this.#li;
  }

  /** Whether a text names one of the foreign articles' outlets (lineIndex outlets). */
  namesOutlet(text) {
    const t = plainWords(String(text ?? "").slice(0, 2000));
    return !!t && this.lineIndex().outlets.some((o) => hasTerm(t, o));
  }

  /** The places with a line that `text` names — by title, other name or the name of another version of the site,
   *  spaces and punctuation aside — in the order the text names them; a shorter name inside a longer one found is not
   *  read again ('OO호수공원 물빛다리' is not also OO호수공원). */
  namedPlaces(text) {
    let t = squash(text);
    if (!t) return [];
    const { heads } = this.lineIndex();
    const cand = [];
    for (const h of new Set(Array.from({ length: Math.max(0, t.length - 1) }, (_, i) => t.slice(i, i + 2)))) {
      if (heads.has(h)) cand.push(...heads.get(h));
    }
    cand.sort((a, b) => a[2] - b[2]);   // longest first, as the names are
    const at = new Map();
    for (const [n, k] of cand) {
      const i = t.indexOf(n);
      if (i < 0) continue;
      t = t.split(n).join("\u0000".repeat(n.length));
      if (!at.has(k) || at.get(k) > i) at.set(k, i);
    }
    return [...at].sort((a, b) => a[1] - b[1] || (a[0] < b[0] ? -1 : 1)).map(([k]) => k);
  }

  /** The places a page's text points to: its place paths in order (a guide's list, a course's stops, an event's
   *  venues, a place's 가까운 장소), else the place names its Korean text gives (a guide section). Only places with a
   *  line, the page itself left out. */
  refsOf(key) {
    const d = this.docs[key];
    if (!d) return [];
    const { refs } = this.lineIndex();
    if (refs.has(key)) return refs.get(key);
    let out = [];
    for (const [p] of String(d.x || "").matchAll(PLACE_REF)) {
      const k = this.keyFor(p);
      if (k && k !== key && this.lines[k] && !out.includes(k)) out.push(k);
    }
    // (the text get_pages would give: a long page's names past it are not what it is about)
    if (!out.length && d.k !== "place") out = this.namedPlaces(String(d.x || "").slice(0, DOC_CHARS)).filter((k) => k !== key);
    refs.set(key, out);
    return out;
  }

  /** The pages the last two exchanges of a conversation ([{role, content}], oldest first) link or name, the latest
   *  message first, and whether its last exchange is about the foreign articles. */
  convoKeys(convo) {
    const msgs = (Array.isArray(convo) ? convo : []).slice(-4);
    const text = (m) => (typeof m?.content === "string" ? m.content
      : Array.isArray(m?.content) ? m.content.filter((b) => b && b.type === "text").map((b) => String(b.text || "")).join("\n") : "");
    const keys = [];
    const add = (k) => { if (k && this.lines[k] && !keys.includes(k)) keys.push(k); };
    let foreign = false;
    msgs.forEach((m, i) => {
      const t = text(m);
      if (i >= msgs.length - 2 && (FOREIGN.test(t) || this.namesOutlet(t))) foreign = true;
    });
    for (const m of [...msgs].reverse()) {
      const t = text(m);
      for (const [, u] of t.matchAll(/\]\(\s*<?([^)\s>]+)>?\s*\)/gu)) {
        const k = this.keyFor(u);
        const article = k ? "" : this.lineIndex().orig.get(normUrl(u)) || "";
        // a link to /abroad/ or to an article's original in the last exchange: the conversation is about them
        if ((k === "/abroad/" || article) && msgs.indexOf(m) >= msgs.length - 2) foreign = true;
        add(k || article);
      }
      for (const k of this.namedPlaces(t)) add(k);
    }
    return { keys, foreign };
  }

  /** The lines a question most likely needs, within `budget` estimated tokens: {keys, must, text, tokens, foreign
   *  (an article's line may be in it), articles ('all' | 'matched' | 'top' | ''), ranked: [[key, score]] (the order
   *  after the must-haves, for tools/chat_lines_eval.mjs)}.
   *  First what it must have — the reader's page when it is a place or an article, the places the question names,
   *  the pages the last two exchanges link or name, on a guide's, a course's or an event's page the places it lists
   *  when the question points at them or names no place of its own (up to half the budget) —, then the rest by rank:
   *  the question's tokens matched in the lines (idf-weighted), search_site's ranking over the pages (a guide, a course
   *  or an event hit counts for the places it points to), the kinds, types, areas and needs it names (LINE_FILTERS,
   *  위치 words) and the places near or tied to what it must have; a line only when its reading is above LINE_FLOOR,
   *  and at most NARROW_MAX of them when the question has must-haves and names no kind, area or need. An article's
   *  line only for a question, page or conversation about the foreign articles (FOREIGN words, an outlet's name), or
   *  the articles that rank first in search_site by a strong word of their own title. Deterministic; a line is never
   *  cut. */
  selectLines({ question = "", convo = [], page = "", budget = SLICE_TOKENS, weights = LINE_WEIGHT } = {}) {
    const li = this.lineIndex();
    const q = String(question ?? "").slice(0, 1000);
    const none = { keys: [], must: [], text: "", tokens: 0, foreign: false, articles: "" };
    if (!li.keys.length) return none;
    const hits = q.trim() ? this.search(q, { limit: 30 }) : [];
    const pageKey = page ? this.keyFor(page) : "";
    const pageDoc = pageKey ? this.docs[pageKey] : null;
    const conv = this.convoKeys(convo);
    const qt = tokens(q);
    const named = this.namedPlaces(q);
    const asked = LINE_FILTERS.filter((x) => x.rx.test(q));
    const sq = squash(q);
    const areas = [...li.areas.keys()].filter((w) => sq.includes(squash(w)));
    const nf = asked.length + (areas.length ? 1 : 0);
    // the foreign articles (review 2026-10-23). 'all': the question is about them, or the reader's page or the last
    // exchange is and the question names nothing more specific ('그거 어디야?' on /abroad/) — every article a
    // candidate with the flat W.abroad. 'matched': only the page or the conversation is about them and the question
    // names a kind, a need, an area or a place ('OO 맛집 추천' on /abroad/) — the articles it matches (a reading above
    // LINE_FLOOR) get W.abroad, the best first, up to a third of the budget; the places keep the rest, and an article
    // it does not match comes in only by its own reading. 'top': an article ranks first in search_site
    // by a word of its own title that tells it apart ('Korea's 33 most beautiful islands'; not the city's name, 'what', 'is',
    // 'free' — idf below the median of the titles' words): it and the articles about as high are must-haves, and no
    // other article comes in
    const qForeign = FOREIGN.test(q) || this.namesOutlet(q);
    const ctxForeign = conv.foreign || pageKey === "/abroad/" || !!(pageDoc && pageDoc.k === "abroad");
    const topStrong = hits.length > 0 && hits[0].kind === "abroad"
      && qt.some((t) => this.head.get(hits[0].key).has(t) && this.idf(t) >= li.strong);
    const top = !qForeign && !ctxForeign && topStrong
      ? hits.filter((h) => h.kind === "abroad" && h.score >= 0.8 * hits[0].score).map((h) => h.key) : [];
    const mode = qForeign || (ctxForeign && !nf && !named.length) ? "all" : ctxForeign ? "matched" : top.length ? "top" : "";
    const allowed = (k) => !!this.lines[k] && (this.docs[k].k !== "abroad" || mode === "all" || mode === "matched" || top.includes(k));
    const searchMax = 3 * tokens(q.slice(0, QUERY_CHARS)).reduce((a, t) => a + this.idf(t), 0);
    // (a) what the question must have
    const must = [];
    const need = (k) => { if (k && allowed(k) && !must.includes(k)) must.push(k); };
    if (pageDoc && (pageDoc.k === "place" || pageDoc.k === "abroad")) need(pageKey);
    for (const k of named) need(k);
    for (const k of conv.keys) need(k);
    for (const k of top) need(k);
    const seeds = must.length;   // the places whose near and tied places count (not a page's list below)
    // the reader is on a guide, a course or an event and asks about it ('여기 나온 식당 중 주차 되는 곳?', '이 중 주차 되는
    // 곳은?', 'Is parking free at these?'): its places, in its order, up to half the budget (review 2026-10-23: a
    // course's stops dropped out behind the cafés of an unrelated search hit)
    const pageRefs = pageDoc && ["guide", "section", "course", "event"].includes(pageDoc.k) ? this.refsOf(pageKey) : [];
    if (pageRefs.length && (DEICTIC.test(q) || !named.length)) {
      let used = 0;
      for (const k of pageRefs) {
        if (!allowed(k) || must.includes(k)) continue;
        if (used + li.cost.get(k) > budget / 2) break;
        must.push(k);
        used += li.cost.get(k);
      }
    }
    // (b) the rest, by rank
    const L = new Map();
    const S = new Map();
    const E = new Map();
    const F = new Map();
    const N = new Map();
    const up = (m, k, v) => { if (allowed(k) && v > (m.get(k) || 0)) m.set(k, v); };
    const found = new Map();
    // the readings are scaled by what a perfect match would score (every token of the question; in search_site, every
    // token in a title), not by the best match there is: a question nothing matches well gets no line for its
    // common words, and its kinds, types and needs decide
    let lineMax = 0;
    for (const t of qt) {
      const ks = li.post.get(t);
      const w = Math.log(1 + li.keys.length / (1 + (ks ? ks.length : 0)));
      lineMax += w;
      if (!ks) continue;
      for (const k of ks) {
        L.set(k, (L.get(k) || 0) + w);
        found.set(k, (found.get(k) || 0) + 1);
      }
    }
    for (const [k, v] of L) L.set(k, v * (0.4 + 0.6 * (found.get(k) / qt.length)));
    for (const h of hits) {
      const kind = this.docs[h.key].k;
      if (kind === "place" || kind === "abroad") up(S, h.key, h.score);
      else if (kind !== "video") this.refsOf(h.key).forEach((k, j) => up(E, k, h.score / (1 + 0.04 * j)));
    }
    // the reader's page's places count as a full expansion each (in its order), whatever the question's top hit scored
    if (pageDoc && pageDoc.k !== "place") this.refsOf(pageKey).forEach((k, j) => up(E, k, searchMax / (1 + 0.04 * j)));
    if (nf) {
      for (const k of li.keys) {
        const d = this.docs[k];
        if (d.k !== "place") continue;
        const f = d.f || {};
        let n = asked.filter((x) => x.fit(d, f)).length;
        if (areas.length && areas.some((w) => li.areas.get(w).includes(k))) n += 1;
        if (n) F.set(k, n / nf);
      }
    }
    const near = NEAR.test(q);
    for (const k of must.slice(0, seeds)) {
      if (this.docs[k].k !== "place") continue;
      for (const r of this.kin.get(k) || []) up(N, r, 1);
      for (const [p] of this.lines[k].matchAll(PLACE_REF)) up(N, this.keyFor(p), 1);   // a combined ticket's places
      const nearLine = (/^가까운 장소: (.*)$/mu.exec(this.docs[k].x || "") || [])[1] || "";
      [...nearLine.matchAll(PLACE_REF)].forEach(([p], j) => up(N, this.keyFor(p), (near ? 1 : 0.4) / (1 + 0.05 * j)));
    }
    const norm = (m, mx) => (k) => (mx ? Math.min(1, (m.get(k) || 0) / mx) : 0);
    const [l, s, e] = [norm(L, lineMax), norm(S, searchMax), norm(E, searchMax)];
    const W = weights;
    // the articles: every one a candidate when the question, page or conversation is about them; which get W.abroad
    const articles = mode === "all" || mode === "matched" ? li.keys.filter((k) => this.docs[k].k === "abroad") : [];
    const reading = (k) => W.line * l(k) + W.search * s(k) + W.expand * e(k) + W.filter * (F.get(k) || 0) + W.near * (N.get(k) || 0);
    const bonus = new Set(mode === "all" ? articles : []);
    if (mode === "matched") {   // the articles the question itself matches (above LINE_FLOOR), the best first
      let used = 0;
      for (const k of articles.filter((x) => reading(x) > LINE_FLOOR).sort((a, b) => reading(b) - reading(a) || (a < b ? -1 : 1))) {
        if (used + li.cost.get(k) > budget / 3) break;
        bonus.add(k);
        used += li.cost.get(k);
      }
    }
    const ranked = [];
    for (const k of new Set([...L.keys(), ...S.keys(), ...E.keys(), ...F.keys(), ...N.keys(), ...articles])) {
      if (!allowed(k) || must.includes(k)) continue;
      const r = reading(k) + (bonus.has(k) ? W.abroad : 0);
      if (r > LINE_FLOOR) ranked.push([k, r + W.prio * li.prio.get(k)]);
    }
    ranked.sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
    // a question about the places it must have (named, followed up, the reader's place or page): a few more lines
    // only — not when its must-haves are only the articles search_site ranks first
    const narrow = !nf && must.some((k) => !top.includes(k));
    const offered = narrow ? ranked.slice(0, NARROW_MAX) : ranked;
    return this.#fill([...must, ...offered.map(([k]) => k)], budget,
      { must, foreign: articles.length > 0 || top.length > 0, articles: mode, ranked: offered });
  }

  /** The lines of `order` that fit in `budget`, in that order, a line that does not fit skipped (a shorter one after
   *  it may) — never cut: their estimated tokens, line breaks counted, are at most the budget. */
  #fill(order, budget, extra = {}) {
    const li = this.lineIndex();
    const keys = [];
    const seen = new Set();
    let used = 0;
    for (const k of order) {
      if (budget - used < li.min) break;
      if (seen.has(k) || !this.lines[k]) continue;
      seen.add(k);
      const c = li.cost.get(k);
      if (used + c > budget) continue;
      keys.push(k);
      used += c;
    }
    const text = keys.map((k) => this.lines[k]).join("\n");
    return { keys, text, tokens: estimateTokens(text), ...extra, must: (extra.must || []).filter((k) => seen.has(k) && keys.includes(k)) };
  }

  /** The lines block of a question (selectLines): the full lines joined, '' when none was selected. */
  relevantLines(opts = {}) {
    return this.selectLines(opts).text;
  }

  /** The places closed on `date` by their regular closed days or a dated notice — checkPlan's own reading, places to
   *  visit and restaurants (planner.closedHints reads the same) —, once per date and instance. */
  closedOn(date) {
    if (this.#closed.has(date)) return this.#closed.get(date);
    const keys = this.keys.filter((k) => this.docs[k].k === "place" && ["attraction", "food"].includes((this.docs[k].f || {}).kd));
    const shut = new Set();
    for (let i = 0; i < keys.length; i += 12) {   // checkPlan reads twelve stops a call
      const r = this.checkPlan({ date, stops: keys.slice(i, i + 12).map((page) => ({ page, start: "", end: "" })) });
      r.stops.forEach((st, j) => { if (st.day === "closed") shut.add(keys[i + j]); });
    }
    if (this.#closed.size >= 16) this.#closed.delete(this.#closed.keys().next().value);
    this.#closed.set(date, shut);
    return shut;
  }

  /** The lines a trip most likely needs (the course planner), within `budget`: {keys, must, text, tokens}. First the
   *  places of the plan an edit changes and the places the reader's note or the edit's request names; then up to
   *  PLAN_ASK_MAX places that fit a dish, a kind or a type the note or the request asks for (nearest the edit's stops
   *  first); then, shared by
   *  how many tokens each has taken (PLAN_WEIGHT), the places to visit by what the reader likes (plan_state.prefFits;
   *  islands by the 섬 권역), needs (plan_state.needAt as planner.needHints reads it), children and travel without
   *  a car, the meals (plan_state.isMeal), the cafés when the reader likes them, the stays for a trip of more than one
   *  day and the rest of the places — each kind spread across the 권역. Places closed on every date of the trip, the
   *  islands reached only by ferry and, for '비 와도 실내 위주', places that shut in the rain are left out. */
  planSelect(c, { edit = null, budget = PLAN_SLICE_TOKENS } = {}) {
    const li = this.lineIndex();
    const prefs = Array.isArray(c && c.prefs) ? c.prefs : [];
    const needs = Array.isArray(c && c.needs) ? c.needs : [];
    const days = Number.isInteger(c && c.days) && c.days > 0 ? c.days : 1;
    const place = (k) => !!k && !!this.lines[k] && this.docs[k].k === "place";
    const must = [];
    const need = (k) => { if (place(k) && !must.includes(k)) must.push(k); };
    for (const d of (edit && edit.plan && Array.isArray(edit.plan.days) ? edit.plan.days : [])) {
      for (const st of Array.isArray(d && d.stops) ? d.stops : []) need(this.keyFor(st && st.page));
    }
    for (const k of this.namedPlaces((c && c.note) || "")) need(k);
    for (const k of this.namedPlaces((edit && edit.request) || "")) need(k);
    const dates = c && typeof c.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(c.date) ? tripDates(c.date, days) : [];
    const shut = dates.map((date) => this.closedOn(date));
    const closedAll = (k) => shut.length > 0 && shut.every((s) => s.has(k));
    const kids = (c && c.with === "kids") || (Array.isArray(c && c.kids) && c.kids.length > 0);
    const transit = c && c.move === "transit";
    // the likings read by travel area (city.js prefRegions): a place in one of their areas counts for more
    const areaLikes = prefs.flatMap((p) => city().prefRegions[p] || []);
    const hard = needs.filter((n) => n !== "lesswalk");
    if (c && c.budget === 0 && !hard.includes("free")) hard.push("free");
    const feeOf = (f) => ({ how: "own", states: f.fee && f.fee.free ? { free: 1 } : f.fee && f.fee.tab ? { paid: 1 } : { unknown: 1 } });
    const needScore = (f, role) => hard.reduce((a, n) => {
      const st = needAt(n, f, role, n === "free" ? feeOf(f) : null, c && c.move).state;
      return a + (st === "ok" ? 1 : st === "near" ? 0.5 : st === "no" ? -2 : 0);
    }, 0);
    // a place the code would never put in for a hard need (plan_geo.hardState: a wheelchair, a pram, free entry —
    // a budget of 0 too —, parking, a rain closure) is left out
    const strict = hard.filter((n) => PLAN_HARD.includes(n));
    const ruledOut = (f, role) => (hard.includes("rain") && !!rainShut(f))
      || strict.some((n) => needAt(n, f, role, n === "free" ? feeOf(f) : null, c && c.move).state === "no");
    // what the note or the edit's request asks for by a dish, a cuisine, a kind or a type ('저녁은 국수으로', '꽃게장 먹고
    // 싶어요', '빵집 투어', '박물관 위주': the LINE_FILTERS marked plan), an area it names (위치 words) counting too: the
    // places that fit it best, up to PLAN_ASK_MAX, ahead of the turns — on an edit the nearest (straight line) to its
    // stops first, else spread across the 권역 (review 2026-10-23: '저녁은 꽃게장 …' on a 원도심 plan got no 원도심 crab
    // restaurant). The generic food words ('먹을', '저녁') fit every restaurant and are not read here
    const askText = `${(c && c.note) || ""} ${(edit && edit.request) || ""}`;
    const asked = LINE_FILTERS.filter((x) => x.plan && x.rx.test(askText));
    const askSq = squash(askText);
    const askAreas = asked.length ? [...li.areas.keys()].filter((w) => askSq.includes(squash(w))) : [];
    const A = [];
    const G = { visit: [], meal: [], cafe: [], stay: [], rest: [] };
    for (const k of li.keys) {
      if (!place(k) || must.includes(k) || this.ferry.has(k) || closedAll(k)) continue;
      const d = this.docs[k];
      const f = d.f || {};
      if (ruledOut(f, f.kd === "food" ? (isCafe(d) ? "cafe" : "meal") : f.kd === "stay" ? "stay" : "visit")) continue;
      const fits = asked.filter((x) => x.fit(d, f)).length;
      if (fits) A.push([k, fits + (askAreas.some((w) => li.areas.get(w).includes(k)) ? 1 : 0)]);
      const isle = areaLikes.includes(regionOf(d)) ? 1 : 0;
      const bus = transit && Array.isArray(f.b) && f.b.length ? 0.5 : 0;
      if (f.kd === "attraction") {
        let sc = 3 * prefs.filter((p) => prefFits(p, d) === true).length + needScore(f, "visit") + bus;
        if (kids && (f.ty === "체험" || /어린이|아이(?:와|들|가)|가족|체험/u.test(summaryOf(d)))) sc += 1;
        (sc > 0 || (!prefs.length && sc >= 0) ? G.visit : G.rest).push([k, sc]);
      } else if (f.kd === "food") {
        const cafe = isCafe(d);
        const sc = needScore(f, cafe ? "cafe" : "meal") + isle + bus;
        if (cafe) (prefs.includes("cafe") ? G.cafe : G.rest).push([k, sc]);
        else (isMeal(d) ? G.meal : G.rest).push([k, sc]);
      } else if (f.kd === "stay") {
        if (days > 1) G.stay.push([k, needScore(f, "stay") + isle + bus]);
      } else G.rest.push([k, 0]);
    }
    // the places the request asks for: the best fit only, nearest the edit's stops first
    const best = Math.max(0, ...A.map(([, n]) => n));
    const fit = A.filter(([, n]) => n === best);
    const at = (edit && edit.plan && Array.isArray(edit.plan.days) ? edit.plan.days : [])
      .flatMap((d) => (Array.isArray(d && d.stops) ? d.stops : [])).map((st) => (this.docs[this.keyFor(st && st.page)] || {}).f || {})
      .map((f) => f.g).filter((g) => Array.isArray(g) && g.length === 2);
    const away = (k) => {
      const g = (this.docs[k].f || {}).g;
      return Array.isArray(g) && at.length ? Math.min(...at.map((p) => straight(p, g))) : Infinity;
    };
    const askOrder = at.length
      ? this.#spread(fit).map((k, i) => [k, away(k), i]).sort((a, b) => a[1] - b[1] || a[2] - b[2]).map(([k]) => k)
      : this.#spread(fit);
    const order = [...must];
    let total = must.reduce((a, k) => a + li.cost.get(k), 0);
    for (const k of askOrder) {
      if (order.length - must.length >= PLAN_ASK_MAX) break;
      if (total + li.cost.get(k) > budget) continue;
      order.push(k);
      total += li.cost.get(k);
    }
    const asks = new Set(order.slice(must.length));
    const W = PLAN_WEIGHT;
    const food = prefs.includes("food");
    // a kind the trip needs only so many of stops there (PLAN_MAX: restaurants for two meals a day across the 권역,
    // cafés, stays for the nights); the places to visit and the rest take what is left
    const M = PLAN_MAX;
    const spread = (items) => this.#spread(items.filter(([k]) => !asks.has(k)));
    const groups = [
      { items: spread(G.visit), w: food ? W.visit - 1 : W.visit, max: Infinity },
      { items: spread(G.meal), w: food ? W.meal + 1 : W.meal, max: Math.round((food ? M.mealFood : M.meal) * (1 + 0.5 * (days - 1))) },
      { items: spread(G.cafe), w: W.cafe, max: M.cafe + M.cafeDay * (days - 1) },
      { items: spread(G.stay), w: W.stay, max: M.stay + M.stayNight * (days - 2) },
      { items: spread(G.rest), w: W.rest, max: Infinity },
    ].filter((g) => g.items.length);
    // the groups take turns by the share each has taken, so none crowds out the others and what one cannot use goes
    // to the rest
    const pos = groups.map(() => 0);
    const used = groups.map(() => 0);
    const taken = groups.map(() => 0);
    for (;;) {
      let gi = -1;
      for (let i = 0; i < groups.length; i += 1) {
        const open = pos[i] < groups[i].items.length && taken[i] < groups[i].max;
        if (open && (gi < 0 || used[i] / groups[i].w < used[gi] / groups[gi].w)) gi = i;
      }
      if (gi < 0 || budget - total < li.min) break;
      const k = groups[gi].items[pos[gi]];
      pos[gi] += 1;
      const cost = li.cost.get(k);
      if (total + cost > budget) continue;
      order.push(k);
      used[gi] += cost;
      taken[gi] += 1;
      total += cost;
    }
    return this.#fill(order, budget, { must });
  }

  /** [[key, score]] in the order a kind's places are offered: by score (in halves), and within the same score each
   *  권역 in turn (by the place's priority, then its key), so every area has its candidates. */
  #spread(items) {
    const li = this.lineIndex();
    const area = (k) => regionOf(this.docs[k]) || "";
    const band = (sc) => Math.floor(sc * 2);
    const sorted = [...items].sort((a, b) => band(b[1]) - band(a[1]) || li.prio.get(b[0]) - li.prio.get(a[0]) || (a[0] < b[0] ? -1 : 1));
    const rank = new Map();
    const count = new Map();
    for (const [k, sc] of sorted) {
      const g = `${band(sc)}|${area(k)}`;
      rank.set(k, count.get(g) || 0);
      count.set(g, (count.get(g) || 0) + 1);
    }
    const cmp = (x, y) => (x < y ? -1 : x > y ? 1 : 0);
    return sorted.sort((a, b) => band(b[1]) - band(a[1]) || rank.get(a[0]) - rank.get(b[0]) || cmp(area(a[0]), area(b[0]))
      || cmp(a[0], b[0])).map(([k]) => k);
  }

  /** The lines block of a trip (planSelect): the full lines joined, '' when none was selected. */
  planLines(c, opts = {}) {
    return this.planSelect(c, opts).text;
  }

  /** Every link in an answer, checked: {links: [{title, url, ext, book?}] (site pages first seen first, then outside
   *  addresses; at most 8), fix: {as written: final address | null}}. null = not a page of this site, not an address
   *  the data links to: the reader sees its text without a link. An outside link becomes the address exactly as the
   *  data has it (the comparison ignores the scheme, 'www.', a trailing slash and case — the link never does). An
   *  official booking page (this.book) becomes the page the reader's version of the site opens for it — its own
   *  language, else the one its button opens, else the Korean page — whichever of them the answer wrote; book = the
   *  service (the card is a booking_click), hl = that page's language. */
  fixLinks(text, lang = "ko") {
    const found = [];
    const md = /\[([^\]\n]{1,200})\]\(\s*<?([^)\s>]+)>?\s*\)/g;
    for (const m of String(text).matchAll(md)) found.push({ label: m[1].trim(), raw: m[2] });
    const bare = String(text).replace(md, " ");
    for (const m of bare.matchAll(/https?:\/\/[^\s<>()[\]"'`]+/g)) found.push({ label: "", raw: m[0].replace(/[.,;:!?。、]+$/u, "") });
    const fix = Object.create(null);
    const links = [];
    const seen = new Set();
    for (const { label, raw } of found) {
      if (raw in fix) continue;
      let url = null;
      let title = label;
      let ext = false;
      let book = "";
      let hl = "";
      if (/^tel:\+?[\d-]{7,16}$/.test(raw) || (/^tel:\+?\d{3,15}$/.test(raw) && this.tel.has(raw.slice(4)))) {
        url = raw;
      } else if (raw.startsWith("/") || (this.site && raw.startsWith(this.site))) {
        const key = this.keyFor(raw);
        if (key) {
          url = this.url(this.pathFor(key, lang));
          // Korean readers get the page's own title (a guide section: its heading); others keep the answer's words,
          // unless those are the Korean name: then the name of the page they open, in their language
          if (lang === "ko" || !label) title = this.docs[key].h || this.docs[key].t;
          if (lang !== "ko" && /[가-힣]/u.test(title)) title = this.nameFor(key, lang) || title;
        }
      } else if (/^https?:\/\//i.test(raw) && this.ext.has(normUrl(raw))) {
        url = this.ext.get(normUrl(raw));
        ext = true;
        const b = this.book.get(normUrl(raw));
        if (b) {
          book = b.k;
          url = (lang !== "ko" && b.p[lang]) || b.url;
          hl = typeof b.l[url] === "string" ? b.l[url] : "";
        }
        if (!title) title = url.replace(/^https?:\/\/(www\.)?/i, "").split("/")[0];
      }
      fix[raw] = url;
      if (url && !url.startsWith("tel:") && !seen.has(url) && links.length < 8) {
        seen.add(url);
        links.push(book ? { title: title || url, url, ext, book, ...(hl ? { hl } : {}) } : { title: title || url, url, ext });
      }
    }
    links.sort((a, b) => Number(a.ext) - Number(b.ext));
    return { links, fix };
  }
}

export async function loadKnowledge(dir) {
  const read = (name) => readFile(path.join(dir, name), "utf8");
  // lines.json is newer than the other three: a directory without it loads with no lines (every place by its page)
  const optional = (name) => read(name).catch((err) => {
    if (err && err.code === "ENOENT") return "{}";
    throw err;
  });
  const [catalog, docs, index, lines] = await Promise.all([read("catalog.txt"), read("docs.json"), read("index.json"),
    optional("lines.json")]);
  return new Knowledge({ catalog, docs: JSON.parse(docs), index: JSON.parse(index), lines: JSON.parse(lines) });
}

// The deployed function reads the files bundled from public/chat/ (vercel.json functions."api/chat.js".includeFiles);
// one load per instance.
let cached = null;
export function defaultKnowledge() {
  if (!cached) {
    cached = loadKnowledge(path.join(process.cwd(), "public", "chat")).catch((err) => {
      cached = null;
      throw err;
    });
  }
  return cached;
}
