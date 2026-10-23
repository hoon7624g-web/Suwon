// The site assistant's knowledge: the three files pipeline/chat_index.py writes under public/chat/ (catalog.txt,
// docs.json, index.json), and what the two tools do with them — search_site (token match over every page),
// get_pages (the full text of up to six pages) — plus the check of every link an answer carries (fixLinks): a link
// to this site must name a page that exists (and is turned into the reader's language version when there is one),
// an outside link must be an address the site's data itself links to, a phone link must be a phone number.
//
// The city's values — the public address, the site's and region's names, the assistant's name, the extra origins —
// are docs.json `meta` (pipeline/chat_index.py chat_meta, from site.json): nothing of a city is written here.
//
// Page paths, ids, queries and addresses come from the model (and so, indirectly, from the user): they are only ever
// looked up in the loaded maps — which have no prototype, so 'constructor' or '__proto__' is simply not a page — and
// matched with fixed patterns; never used as a file path or turned into a RegExp. The files are read once, by name.
import { readFile } from "node:fs/promises";
import path from "node:path";

const table = (obj) => Object.assign(Object.create(null), obj && typeof obj === "object" ? obj : {});
const ORIGIN = /^https:\/\/[a-z0-9-]+(\.[a-z0-9-]+)+$/;

/** docs.json meta, checked: {site, siteName, siteNameEn, region {lang: name}, assistant {lang: name}, origins [https
 *  origins], tel [short numbers], plan {hubs {key: {name, path?, g?}}, prefs {key: words}, resident}} — plan is the
 *  course planner's city values (pipeline/plan.py plan_meta). Missing values are empty, never another city's. */
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

const PLAN_KEY = /^[a-z0-9][a-z0-9-]{0,30}$/;

/** meta.plan, checked: hubs by key ({name, path?, g? [lat, lng]}), prefs by key (the words the model reads), the
 *  resident label of the combined tickets' tables ('' when none). */
function readPlan(p) {
  const o = p && typeof p === "object" ? p : {};
  const hubs = {};
  for (const [k, h] of Object.entries(o.hubs && typeof o.hubs === "object" ? o.hubs : {})) {
    if (!PLAN_KEY.test(k) || !h || typeof h.name !== "string" || !h.name.trim()) continue;
    const g = Array.isArray(h.g) && h.g.length === 2 && h.g.every((x) => typeof x === "number" && Number.isFinite(x)) ? h.g : null;
    hubs[k] = { name: h.name.trim(), ...(typeof h.path === "string" && h.path.startsWith("/") ? { path: h.path } : {}), ...(g ? { g } : {}) };
  }
  const prefs = {};
  for (const [k, v] of Object.entries(o.prefs && typeof o.prefs === "object" ? o.prefs : {})) {
    if (PLAN_KEY.test(k) && typeof v === "string" && v.trim()) prefs[k] = v.trim();
  }
  return { hubs, prefs, resident: typeof o.resident === "string" ? o.resident.trim() : "" };
}

// tokens(): pipeline/chat_index.py tokens() for queries — Hangul / kana / CJK runs as bigrams (one syllable alone as
// itself), Latin, Cyrillic and digit runs as words (one-letter Latin words dropped), NFKC, lower case. Keep in step.
const TOKEN_RX = /[가-힣]+|[぀-ヿ㐀-鿿]+|[a-z0-9À-ɏЀ-ӿ]+/gu;
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

/** A place's other names as docs.json gives them (a: [names]); [] for any other doc. */
function otherNames(d) {
  return Array.isArray(d && d.a) ? d.a.filter((x) => typeof x === "string" && x) : [];
}

/** A doc's title as the model reads it in search_site and get_pages results: with the place's other names, so an old
 *  and a new name read as one place ('<name> (다른 이름 <other>)'). Link titles the reader sees stay the page's own. */
function shownTitle(d) {
  const a = otherNames(d);
  return a.length ? `${d.t} (다른 이름 ${a.join(", ")})` : d.t;
}

/** ' · name in ja: …' — the page's name on the site's version in the language the answer is written in, so the model
 *  writes the name that page uses instead of translating the Korean one letter by letter. */
function langName(d, nameLang) {
  const n = nameLang && nameLang !== "ko" ? (d.n || {})[nameLang] : "";
  return n ? ` · name in ${nameLang}: ${n}` : "";
}

export class Knowledge {
  constructor({ catalog, docs, index }) {
    this.catalog = String(catalog || "");
    this.meta = readMeta(docs && docs.meta, docs && docs.site);
    this.site = this.meta.site;
    this.docs = table(docs && docs.docs);
    this.alias = table(docs && docs.alias);
    this.tel = new Set(this.meta.tel);
    // outside addresses the data links to, by their compared form → the address as the data has it (https first)
    this.ext = new Map();
    for (const u of (docs && docs.ext) || []) {
      const k = normUrl(u);
      const had = this.ext.get(k);
      if (!had || (/^http:/i.test(had) && /^https:/i.test(u))) this.ext.set(k, u);
    }
    // the combined tickets' tables (pipeline/tickets.py export): feeTotal
    this.tickets = Array.isArray(docs && docs.tickets) ? docs.tickets.filter((t) => t && t.name && t.prices) : [];
    this.keys = Object.keys(this.docs).sort();
    this.byTitle = new Map();
    for (const k of this.keys) {
      const t = this.docs[k].t;
      this.byTitle.set(t, this.byTitle.has(t) ? null : k);   // a title two pages share names neither
    }
    // a place's other names find its page too, unless a title or another place's other name is the same
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
    // is exactly one of them ranks that page first (the first site's review 2026-10-17 E03: a German or Japanese
    // name is in a guide's and an event's titles too)
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
   *  (a guide section: its guide's twin, same anchor), else the English page, else the Korean page — the site has no
   *  version at all yet, so every reader opens the Korean page; a video opens the topic page that lists it. */
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

  /** 'Names of these places on this site in de: <Korean name> = <its German name>; …' — the places a tool result's
   *  Korean text mentions (longest name first; a shorter name inside a longer one is not read again), with their names
   *  in `nameLang` (else English): the model writes those instead of translating the Korean one. Leaves out the pages
   *  in `skip` (their own lines name them already); at most NAMES_MAX names and `max` characters; '' for Korean, or
   *  when no place has such a name (no language version yet). */
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
   *  scaled by the share of query tokens found and by kind. */
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
      const text = d.x.length > DOC_CHARS ? `${d.x.slice(0, DOC_CHARS)}\n… (cut here: the rest is on the page)` : d.x;
      let part = `### ${shownTitle(d)}${langName(d, nameLang)}\nPath: ${where}${en}\n${text}`;
      if (part.length > left) {
        if (left < 400) {
          parts.push(`### ${shownTitle(d)}\n(not read: this question's reading limit is used up — answer with what you have)`);
          continue;
        }
        part = `${part.slice(0, left)}\n… (cut here: reading limit)`;
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
   *  [{count, age?, category?}]: each person's price from the table (the residents' prices with `resident` — their name is meta.plan.resident —, the 단체 table
   *  with `group`), the table's free-entry and age rules applied, a person the table has no rule for marked 확인 필요
   *  and left out of the total; `items` [{label, won, count}]: fees the pages give, multiplied and added. The result
   *  (Korean, as the data) names every line's basis and source, the sum written out and the total the answer is to use
   *  everywhere — or, when a person is 확인 필요, the known part only and no total. */
  feeTotal({ ticket = "", people = [], resident = false, group = false, items = [] } = {}, now = new Date()) {
    const won = (n) => `${n.toLocaleString("en-US")}원`;
    const out = [];
    const parts = [];   // [amount, label] of every line in the total
    const open = [];    // the persons the table gives no price for
    const conds = [];   // what a price in the total holds on
    const bare = (x) => String(x || "").replace(/\s+/g, "");
    if (ticket || people.length) {
      const t = this.tickets.find((x) => bare(x.name) === bare(ticket) || x.id === ticket)
        || (bare(ticket).length >= 3 && this.tickets.filter((x) => bare(x.name).includes(bare(ticket))).length === 1
          ? this.tickets.find((x) => bare(x.name).includes(bare(ticket))) : null);
      if (!t) {
        out.push(`'${String(ticket).slice(0, 60)}'은 이 사이트가 표로 가진 통합권이 아니다. 표가 있는 통합권: `
          + (this.tickets.map((x) => `${x.name}(${x.covers})`).join("; ") || "없음")
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
        out.push(`${t.name}(${t.covers}) — ${mode} 요금${modeNote}, ${resident ? `${who} 요금` : `${who} 아님`} — 요금 출처: ${t.src}`);
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
    for (const it of items) {
      const sub = it.won * it.count;
      out.push(`- ${String(it.label).slice(0, 80)}: ${won(it.won)} × ${it.count} = ${won(sub)} (페이지의 값)`);
      parts.push([sub, it.label]);
    }
    if (!parts.length && !open.length) return { text: out.join("\n") || "계산할 사람이나 항목이 없다.", total: null, known: null };
    const sum = parts.reduce((a, [v]) => a + v, 0);
    const formula = parts.length ? `${parts.map(([v]) => v.toLocaleString("en-US")).join(" + ")} = ${won(sum)}` : "0원";
    const on = conds.length ? ` 조건: ${conds.join("; ")} — 이 조건을 합계와 함께 첫 문장에 쓴다.` : "";
    if (open.length) {
      out.push(`확인된 사람만의 합계(식): ${formula}. 확인 필요: ${open.join(", ")} — 총액을 확정하지 않는다: `
        + `답의 첫 문장과 표와 끝에 '${won(sum)} + ${open.join(", ")} 요금 확인 필요'로 같은 값을 쓴다.${on}`);
      return { text: out.join("\n"), total: null, known: sum };
    }
    out.push(`합계(식): ${formula}. 답의 첫 문장·표·끝 어디서나 이 합계 ${won(sum)} 하나만 쓴다(같은 선택에 다른 합계를 쓰지 않는다).${on}`);
    return { text: out.join("\n"), total: sum, known: sum };
  }

  /** check_plan: a timed plan read against the site's data (the first city's review 2026-10-17 G01: one place until
   *  16:00, then another 5.7 km away from 16:00). For each stop: that day's regular closed days and the date's
   *  notices, the hours of the date's season with the last entry, and what the plan's times break; for each leg between
   *  two places: the straight-line distance (not a route, not a travel time), the minutes the plan leaves, and the bus
   *  routes the stops near both share (direction and times are the timetable's). Returns {text, flags}. */
  checkPlan({ date = "", stops = [], move = "" } = {}) {
    const WD = "일월화수목금토";
    const ORD = { 첫째: 1, 첫: 1, 둘째: 2, 셋째: 3, 넷째: 4, 다섯째: 5 };
    const min = (t) => { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; };
    const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
    const day = /^\d{4}-\d{2}-\d{2}$/.test(date) ? new Date(`${date}T12:00:00Z`) : null;
    const wd = day ? day.getUTCDay() : -1;
    const month = day ? day.getUTCMonth() + 1 : 0;
    const nth = day ? Math.ceil(day.getUTCDate() / 7) : 0;
    const lastWeek = day ? new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth() + 1, 0)).getUTCDate() - day.getUTCDate() < 7 : false;
    const dom = day ? day.getUTCDate() : 0;
    // the public holidays fixed to a date (관공서의 공휴일에 관한 규정): on one, a place's own holiday rule or the lack
    // of one is a thing to check — the lunar ones (설날·추석) move, so a rule naming them is checked in their months
    const HOLI = { "1-1": "신정", "3-1": "삼일절", "5-5": "어린이날", "6-6": "현충일", "8-15": "광복절", "10-3": "개천절",
      "10-9": "한글날", "12-25": "성탄절" };
    const holiday = day ? HOLI[`${month}-${dom}`] || "" : "";
    const out = [day ? `날짜: ${date} (${WD[wd]}요일)${holiday ? ` — 공휴일(${holiday})` : ""}` : "날짜 없음: 휴무와 계절별 시간은 맞춰 보지 않았다"];
    const flags = [];
    // the days the lunar holidays can fall on, with the days around them and a substitute holiday: 설 연휴 between
    // 1월 19일 and 2월 24일, 추석 연휴 between 9월 5일 and 10월 12일 (설날 falls on 1월 22일~2월 19일 and 추석 on 9월 8일~
    // 10월 6일 of the solar calendar in 2000~2050) — a 추석 rule on 10월 24일 is not a thing to check (operator 2026-10-18)
    const seollal = (month === 1 && dom >= 19) || (month === 2 && dom <= 24);
    const chuseok = (month === 9 && dom >= 5) || (month === 10 && dom <= 12);
    // a closed-day value's dated parts: '1월 1일' on that date is closed; '설날·추석 당일' or '명절' in the days they
    // can fall on, '공휴일' on a public holiday — whether that day is one is for the reader to check
    const datedOn = (text) => {
      const hits = [];
      for (const m of text.matchAll(/(1[0-2]|[1-9])\s*월\s*(3[01]|[12]\d|[1-9])\s*일/gu)) {
        if (+m[1] === month && +m[2] === dom) hits.push([true, `${m[1]}월 ${m[2]}일`]);
      }
      if (/설날|설\s*연휴|설\s*당일|구정/u.test(text) && seollal) hits.push([null, "설날 규칙 — 그날이 설 연휴인지"]);
      if (/추석/u.test(text) && chuseok) hits.push([null, "추석 규칙 — 그날이 추석 연휴인지"]);
      if (/명절/u.test(text) && (seollal || chuseok)) hits.push([null, "명절 규칙 — 그날이 명절 연휴인지"]);
      if (/공휴일|국경일/u.test(text) && holiday) hits.push([null, `공휴일 규칙 — 그날은 ${holiday}`]);
      return hits;
    };
    // a closed-day rule read for the date: [closed?, how] — only weekdays (every week, or the n-th of the month) are
    // judged; dates, holidays and 명절 rules are named for the reader to check
    const closedOn = (text) => {
      const hits = [];
      text = spell(text);
      for (const m of text.matchAll(/([월화수목금토일](?:\s*[·,、및]\s*[월화수목금토일])*)\s*요일/gu)) {
        const days = m[1].match(/[월화수목금토일]/gu);
        const before = text.slice(Math.max(0, m.index - 14), m.index);
        const ords = [...before.matchAll(/(첫째|둘째|셋째|넷째|다섯째|첫|마지막)/gu)].map((x) => x[1]);
        if (!days.includes(WD[wd])) continue;
        if (/격주/u.test(before)) hits.push([null, `격주 ${WD[wd]}요일 규칙`]);
        else if (ords.length) {
          const on = ords.some((o) => (o === "마지막" ? lastWeek : ORD[o] === nth));
          hits.push([on, `${ords.join("·")} ${WD[wd]}요일 규칙 — 그날은 ${nth}째 ${WD[wd]}요일${lastWeek ? "(마지막 주)" : ""}`]);
        } else hits.push([true, `매주 ${WD[wd]}요일`]);
      }
      return hits;
    };
    // '화요일~목요일', '토~일요일' → '화·수·목요일' (a range of weekdays named by its ends)
    const spell = (text) => text.replace(/([월화수목금토일])(?:요일)?\s*~\s*([월화수목금토일])요일/gu, (all, x, y) => {
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
        seg = text.slice(pick ? Math.max(from, ranges[pick].index - 12) : 0, to).replace(/[\s[(（]*(?:하절기|동절기|여름|겨울)?[\s[(（]*$/u, "");
      } else if (/하절기|동절기|여름|겨울|성수기|비수기/u.test(text)) {
        return { seg: text, why: "계절 구분의 달이 이 값에 없음" };
      }
      const TIME = /(\d{1,2}):(\d{2})\s*[~–-]\s*(\d{1,2}):(\d{2})/u;
      const byDay = [...seg.matchAll(/([월화수목금토일](?:\s*[·,、]\s*[월화수목금토일])*)\s*요일\s*[:：]?\s*(\d{1,2}:\d{2}\s*[~–-]\s*\d{1,2}:\d{2})/gu)];
      let range = TIME.exec(seg);
      if (byDay.length && day) {
        const hit = byDay.find((m) => m[1].includes(WD[wd]));
        if (!hit) return { seg, why: `${WD[wd]}요일 시간이 이 값에 없음` };
        range = TIME.exec(hit[2]);
        seg = hit[0];
      }
      if (!range) return { seg, why: "시각을 읽을 수 없음" };
      const open = +range[1] * 60 + +range[2];
      const close = +range[3] * 60 + +range[4];
      const last = /입장\s*마감\s*(\d{1,2}):(\d{2})|(\d{1,2}):(\d{2})\s*입장\s*마감|(?:라스트\s*오더|주문\s*마감|L\.?\s*O\.?)\s*[:：]?\s*(\d{1,2}):(\d{2})/iu.exec(seg);
      const before = /종료\s*(\d{1,3})\s*분\s*전/u.exec(text);   // '입장은 종료 30분 전까지' holds in every season
      const lastAt = last ? (last[1] ? +last[1] * 60 + +last[2] : last[3] ? +last[3] * 60 + +last[4] : +last[5] * 60 + +last[6])
        : before ? close - +before[1] : null;
      return { seg: seg.trim(), open, close, last: lastAt };
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
      let todayHours = null;   // a dated notice's own hours for that date
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
          for (const c of f.c || []) {
            const hits = [...closedOn(c.t), ...datedOn(c.t)];
            const yes = hits.filter((h) => h[0] === true);
            const maybe = hits.filter((h) => h[0] === null);
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
          if (!(f.c || []).length) {
            notes.push("쉬는 날: 사이트에 없음(확인 필요)");
            checks.push("쉬는 날이 사이트에 없음 — 그날 여는지 확인 필요");
            if (dayState === "open") dayState = "unknown";
          }
          if (holiday && dayState !== "closed" && !checks.some((x) => /공휴일/u.test(x))) {
            checks.push(`그날은 공휴일(${holiday}) — 공휴일 운영은 사이트 자료에 없음, 그날 여는지 확인 필요`);
          }
        }
        for (const h of todayHours ? [{ p: "날짜별 공지", t: "", r: todayHours }] : f.h || []) {
          const r = h.r || hoursFor(h.t);
          if (r.why) {
            notes.push(`이용시간 — ${h.p}: '${h.t}' (그날 시각을 하나로 읽지 않음: ${r.why} — 확인 필요)`);
            continue;
          }
          const bad = [];
          if (s !== null && s < r.open) bad.push(`시작 ${hhmm(s)}이 여는 시각 ${hhmm(r.open)}보다 이름`);
          if (e !== null && r.close > r.open && e > r.close) bad.push(`끝 ${hhmm(e)}이 닫는 시각 ${hhmm(r.close)}보다 늦음`);
          if (s !== null && r.last !== null && s > r.last) bad.push(`시작 ${hhmm(s)}이 입장·주문 마감 ${hhmm(r.last)}보다 늦음`);
          notes.push(`그날 시간 — ${h.p}: ${r.seg}${r.last !== null && !/마감/u.test(r.seg) ? ` (입장 마감 ${hhmm(r.last)})` : ""}${bad.length ? ` → ${bad.join(", ")}` : " → 계획한 시각은 이 시간 안"}`);
          if (bad.length) flag(`${h.p} 기준 ${bad.join(", ")}`);
        }
        if (!(f.h || []).length && !todayHours) {
          notes.push("이용시간: 사이트에 없음(확인 필요)");
          checks.push("이용시간이 사이트에 없음 — 그 시각에 여는지 확인 필요");
        }
      }
      for (const c of checks) notes.push(`확인 필요: ${c}`);
      out.push(`${head}\n   ${notes.join("\n   ") || "확인할 값 없음"}`);
      stopsOut.push({ key, name: d.t, day: dayState, notes, flags: mine, checks });
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
      let move = "";
      let legFlag = "";
      if (gap === null) move = "계획한 이동 시간: 시각이 없음";
      else if (gap <= 0) {
        move = `계획한 이동 0분 — 서로 다른 두 곳 사이에 이동 시간이 없다`;
        legFlag = `${dist}인데 이동 시간을 두지 않음`;
        flags.push(`${i + 1}→${i + 2}번 ${a.d.t} → ${b.d.t}: ${legFlag} — 이 구간을 따로 한 줄('이동: ${dist}, 소요 시간 사이트에 없음')로 두고, 다음 장소 시작을 앞 장소 끝과 같게 두지 않는다`);
      } else if (m !== null && m > gap * (move === "car" ? 1000 : m <= 1200 ? 100 : 400)) {
        // a bound, not a travel time: 60 km/h in a straight line by car, 24 km/h without one, 6 km/h on foot under
        // 1.2 km — a margin under it cannot cover the distance whatever the road (review 2026-10-17 CE09: 1 minute
        // for 5.7 km passed)
        move = `계획한 이동 ${gap}분 — 직선 거리만으로도 이 시간에 갈 수 없는 거리`;
        legFlag = `${dist}인데 여유 ${gap}분 — 직선 거리만으로도 갈 수 없는 시간`;
        flags.push(`${i + 1}→${i + 2}번 ${a.d.t} → ${b.d.t}: ${legFlag} — 여유를 늘리거나 가까운 곳으로 바꾼다`);
      } else move = `계획한 이동 ${gap}분 — 사이트에 이 구간의 소요 시간은 없다(직선거리는 이동 시간이 아님)`;
      out.push(`구간 ${i + 1}→${i + 2}: ${a.d.t} → ${b.d.t}: ${dist} · ${move} · ${bus}`);
      legsOut.push({ from: i, to: i + 1, m, gap, routes: shared, flag: legFlag,
        a: ga ? { name: a.d.t, lat: ga[0], lng: ga[1] } : null, b: gb ? { name: b.d.t, lat: gb[0], lng: gb[1] } : null });
    }
    out.push(flags.length ? `고칠 것 ${flags.length}건:\n- ${flags.join("\n- ")}\n고친 일정으로 답한다(고친 일정을 다시 check_plan으로 확인할 수 있으면 확인한다).`
      : "이 사이트 자료로 걸리는 것 없음. 이동 구간은 여전히 '이동 확인 필요'다(사이트에 소요 시간이 없음).");
    return { text: out.join("\n"), flags, stops: stopsOut, legs: legsOut };
  }

  titleOf(raw) {
    const key = this.keyFor(raw);
    return key ? this.docs[key].t : String(raw).slice(0, 40);
  }

  /** Every link in an answer, checked: {links: [{title, url, ext}] (site pages first seen first, then outside
   *  addresses; at most 8), fix: {as written: final address | null}}. null = not a page of this site, not an address
   *  the data links to: the reader sees its text without a link. An outside link becomes the address exactly as the
   *  data has it (the comparison ignores the scheme, 'www.', a trailing slash and case — the link never does). A
   *  phone link stays when it is a phone number, or a short number the site's data lists (meta.tel). */
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
        if (!title) title = url.replace(/^https?:\/\/(www\.)?/i, "").split("/")[0];
      }
      fix[raw] = url;
      if (url && !url.startsWith("tel:") && !seen.has(url) && links.length < 8) {
        seen.add(url);
        links.push({ title: title || url, url, ext });
      }
    }
    links.sort((a, b) => Number(a.ext) - Number(b.ext));
    return { links, fix };
  }
}

export async function loadKnowledge(dir) {
  const read = (name) => readFile(path.join(dir, name), "utf8");
  const [catalog, docs, index] = await Promise.all([read("catalog.txt"), read("docs.json"), read("index.json")]);
  return new Knowledge({ catalog, docs: JSON.parse(docs), index: JSON.parse(index) });
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
