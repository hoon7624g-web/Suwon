// A plan passed on by a link (/plan/#p=…, operator 2026-10-19: '동행이 자기 휴대폰으로 열 수 있는 링크' — with no
// server storage: no accounts, no stored conversations, CLAUDE.md 3절 10항). The whole plan rides in the address
// fragment, which never reaches a server log: the page packs a compact form of the plan on screen (deflate-raw JSON,
// base64url), and whoever opens the link sends that compact form back to /api/plan/ {view: {compact, sig}} to have it
// read against today's data (planner.js createPlanHandler, no model call).
//
// The compact form: {v: 1, c: the conditions without the reader's note (the free text is theirs — never in a link;
// a condition at its default left out), k: 1 for a plan the site built itself, e: the meals the reader eats elsewhere
// ('l' lunch, 'd' dinner — what the note or an edit's request decided, so a view reads the plan as it was made), t:
// title, s: summary, n: notes, d: per day the stops [slug, start, end, role, why]} — a place page's slug for
// /places/<slug>/ (every place of the site; another path is kept whole), the role one letter, a stop's empty reason
// left out. The words (title, summary, notes, reasons) are the AI's and must not be
// forgeable on the site's domain: the server signs every plan it finishes — HMAC-SHA256 over the canonical form
// (normalize: fixed key order, the defaults written out, every stop's path whole) — keyed by PLAN_SHARE_SECRET if set
// (32 characters at least), else by a key derived from ANTHROPIC_API_KEY (HMAC(apiKey, SHARE_SALT)); no key, no signature. The key
// is never logged nor sent. A link whose signature does not check out is still shown, its words dropped (the code's
// title and summary from the data instead) and said so. See docs/handover/plan_share.md.
import { createHmac, timingSafeEqual } from "node:crypto";
import { inflateRawSync } from "node:zlib";

import { HttpError } from "./server.js";

export const SHARE_VERSION = 1;
export const SHARE_LIMITS = {
  linkChars: 16000,      // a packed link the server inflates (the page sends the compact form when it can read it)
  unpacked: 32 * 1024,   // its JSON
  title: 60,             // the words' bounds: readSubmit's own (planner.js), so every plan the server finishes fits
  summary: 300,
  notes: 3,
  note: 160,
  why: 120,
  days: 3,
  stops: 10,             // a day's stops, its stay counted (plan_geo.STOPS_MAX)
  path: 300,
  pastDays: 365,         // a shared plan opens up to a year after its date (the plan's own dates: up to 180 days ahead)
  perMinute: 30,         // views: their own limiter (no model call) — never the plan quota
  perDay: 300,
  allPerMinute: 600,
  allPerDay: 20000,
};
export const SHARE_SALT = "plan-share-v1";
const ROLE = { visit: "v", meal: "m", cafe: "c", stay: "s" };
const ROLE_OF = { v: "visit", m: "meal", c: "cafe", s: "stay" };
// the meals the reader eats elsewhere (plan.complete.meals, state 'skip'): one letter each, lunch first
const EAT = { lunch: "l", dinner: "d" };
const EATS = ["", "l", "d", "ld"];
const COND_KEYS = ["date", "days", "start", "end", "move", "with", "adults", "seniors", "kids", "from", "to", "prefs", "needs", "budget"];
const PLACE = /^\/places\/([^/?#]+)\/$/u;
const SIG = /^[A-Za-z0-9_-]{43}$/;

const bad = () => {
  throw new HttpError(400, "bad_link");
};

// the shortest PLAN_SHARE_SECRET used (characters): any signed link publishes a plan and its signature, so a short
// secret could be found offline and every link forged (round-6 final verifier) — a shorter one is not used
export const SECRET_MIN = 32;
const secretOf = (env) => (typeof env.PLAN_SHARE_SECRET === "string" ? env.PLAN_SHARE_SECRET.trim() : "");

/** Whether PLAN_SHARE_SECRET is set but shorter than SECRET_MIN characters (shareKey does not use it; the handler says
 *  so once in its log, without the value). */
export const secretShort = (env = {}) => {
  const secret = secretOf(env);
  return !!secret && [...secret].length < SECRET_MIN;
};

/** The key the signatures use, or null: PLAN_SHARE_SECRET when it is set (SECRET_MIN characters at least), else
 *  HMAC(ANTHROPIC_API_KEY, SHARE_SALT) — a key of its own, so a signature never says anything about the
 *  API key. */
export function shareKey(env = {}) {
  const secret = secretOf(env);
  if (secret && !secretShort(env)) return Buffer.from(secret, "utf8");
  const api = typeof env.ANTHROPIC_API_KEY === "string" ? env.ANTHROPIC_API_KEY.trim() : "";
  return api ? createHmac("sha256", api).update(SHARE_SALT).digest() : null;
}

/** A plan the site built itself from its data: one 'fixed' line starting '일정 전체:' (planner CODE_PLAN_*; the page's
 *  codeBuilt reads it the same way). */
export const codeBuilt = (plan) => !!(plan && Array.isArray(plan.fixed) && plan.fixed.length === 1 && /^일정 전체:/u.test(String(plan.fixed[0])));

const slugOf = (path) => {
  const m = PLACE.exec(path);
  return m ? m[1] : path;
};
const pathOf = (slug) => (slug.startsWith("/") ? slug : `/places/${slug}/`);

/** The compact form of a finished plan (planner.finish, v 2) — what a link carries. The page builds the same from the
 *  plan it shows (plan.js compactOf); the server signs this one. */
export function compactOf(plan) {
  const out = { v: SHARE_VERSION, c: compactConditions(plan.conditions) };
  if (codeBuilt(plan)) out.k = 1;
  const e = eatsOf(plan);
  if (e) out.e = e;
  out.t = plan.title || "";
  out.s = plan.summary || "";
  out.n = Array.isArray(plan.notes) ? plan.notes : [];
  out.d = (plan.days || []).map((d) => (d.stops || []).map((s) => {
    const row = [slugOf(String(s.path || s.page || "")), s.start, s.end, ROLE[s.role] || "v"];
    if (s.why) row.push(s.why);
    return row;
  }));
  return out;
}

// a condition at its default is left out of a link (normalize writes it back)
const DEFAULTS = { seniors: 0, kids: [], from: "", to: "", prefs: [], needs: [], budget: null };
const isDefault = (k, v) => Object.hasOwn(DEFAULTS, k) && JSON.stringify(DEFAULTS[k]) === JSON.stringify(v);

/** The conditions as a link carries them: never the note, the defaults left out. */
export function compactConditions(c = {}) {
  const cond = {};
  for (const k of COND_KEYS) if (c[k] !== undefined && !isDefault(k, c[k])) cond[k] = c[k];
  return cond;
}

/** The meals the reader eats elsewhere in a finished plan ('', 'l', 'd' or 'ld'): what the note or the edit's request
 *  decided (plan_state.completeness, state 'skip') — a view has neither, so the link carries the decision. */
export function eatsOf(plan) {
  const meals = ((plan && plan.complete) || {}).meals || [];
  return ["lunch", "dinner"].filter((k) => meals.some((m) => m.kind === k && m.state === "skip")).map((k) => EAT[k]).join("");
}

const text = (v, max) => {
  if (v === undefined || v === null) return "";
  if (typeof v !== "string" || v.length > max) bad();
  return v;
};
const list = (v, max) => {
  if (v === undefined || v === null) return [];
  if (!Array.isArray(v) || v.length > max) bad();
  return v;
};

/** A compact form checked for its shape and written out in full, in a fixed order: {v, c: {date … budget}, k, e, t, s,
 *  n, d: [[[path, start, end, role, why]]]}. What it says is checked by the handler (validConditions, the site's
 *  pages); anything not of the format's shape is a malformed link (HttpError 400 'bad_link'). */
export function normalize(x) {
  if (!x || typeof x !== "object" || Array.isArray(x) || x.v !== SHARE_VERSION) bad();
  const c = x.c;
  if (!c || typeof c !== "object" || Array.isArray(c)) bad();
  const scalar = (v) => v === null || typeof v === "string" || (typeof v === "number" && Number.isFinite(v));
  const nums = (v) => list(v, 6).map((a) => (typeof a === "number" && Number.isFinite(a) ? a : bad()));
  const keys = (v, max) => list(v, max).map((a) => (typeof a === "string" && a.length <= 20 ? a : bad()));
  for (const k of ["date", "days", "start", "end", "move", "with", "adults", "seniors", "from", "to", "budget"]) {
    if (c[k] !== undefined && !scalar(c[k])) bad();
    if (typeof c[k] === "string" && c[k].length > 20) bad();
  }
  const cond = { date: c.date ?? null, days: c.days ?? null, start: c.start ?? null, end: c.end ?? null, move: c.move ?? null,
    with: c.with ?? null, adults: c.adults ?? null, seniors: c.seniors ?? 0, kids: nums(c.kids), from: c.from ?? "", to: c.to ?? "",
    prefs: keys(c.prefs, 9), needs: keys(c.needs, 9), budget: c.budget ?? null };
  if (x.k !== undefined && x.k !== 0 && x.k !== 1) bad();
  if (x.e !== undefined && !EATS.includes(x.e)) bad();
  const days = list(x.d, SHARE_LIMITS.days);
  return {
    v: SHARE_VERSION, c: cond, k: x.k === 1 ? 1 : 0, e: x.e || "",
    t: text(x.t, SHARE_LIMITS.title), s: text(x.s, SHARE_LIMITS.summary),
    n: list(x.n, SHARE_LIMITS.notes).map((a) => text(a, SHARE_LIMITS.note)),
    d: days.map((day) => list(day, SHARE_LIMITS.stops).map((st) => {
      if (!Array.isArray(st) || st.length < 4 || st.length > 5) bad();
      const [slug, start, end, role, why] = st;
      if (typeof slug !== "string" || !slug || slug.length > SHARE_LIMITS.path || /[\s?#]/u.test(slug)) bad();
      if (!slug.startsWith("/") && slug.includes("/")) bad();
      if (typeof start !== "string" || typeof end !== "string" || start.length > 5 || end.length > 5 || !ROLE_OF[role]) bad();
      return [pathOf(slug), start, end, ROLE_OF[role], text(why, SHARE_LIMITS.why)];
    })),
  };
}

/** The string the signature is over: the normalized form as JSON (its keys in normalize's order). */
export const canonical = (x) => JSON.stringify(normalize(x));

/** The signature of a compact form (base64url, 43 characters), or null without a key. */
export function signCompact(compact, key) {
  if (!key) return null;
  return createHmac("sha256", key).update(canonical(compact)).digest("base64url");
}

/** The signature of a finished plan (planner.finish), or null without a key — sent with every plan the server makes. */
export const signPlan = (plan, key) => (key ? signCompact(compactOf(plan), key) : null);

/** Whether `sig` is the signature of the (normalized) compact form under `key`. Constant time; false without a key or
 *  a signature of the right shape. */
export function sigValid(compact, sig, key) {
  if (!key || typeof sig !== "string" || !SIG.test(sig)) return false;
  const want = createHmac("sha256", key).update(JSON.stringify(compact)).digest();
  const got = Buffer.from(sig, "base64url");
  return got.length === want.length && timingSafeEqual(got, want);
}

/** A packed link's payload — 'z.<base64url of deflate-raw JSON>' or 'j.<base64url of JSON>' (plan.js packs it; a
 *  browser that cannot inflate sends it as it is) — read back to the compact object. Bounded: the packed text, the
 *  inflated bytes. Malformed → HttpError 400 'bad_link'. */
export function unpack(packed) {
  if (typeof packed !== "string" || packed.length > SHARE_LIMITS.linkChars) bad();
  const m = /^([zj])\.([A-Za-z0-9_-]+)$/.exec(packed);
  if (!m) bad();
  let raw;
  try {
    const bytes = Buffer.from(m[2], "base64url");
    raw = m[1] === "z" ? inflateRawSync(bytes, { maxOutputLength: SHARE_LIMITS.unpacked }) : bytes;
    if (raw.length > SHARE_LIMITS.unpacked) bad();
    return JSON.parse(raw.toString("utf8"));
  } catch (err) {
    if (err instanceof HttpError) throw err;
    return bad();
  }
}

/** A view request's body part {compact, sig} (or {packed, sig}) checked: {compact: normalized, sig} — sig null when
 *  missing or not of a signature's shape (then the words are dropped, never refused). */
export function readView(v) {
  if (!v || typeof v !== "object" || Array.isArray(v)) bad();
  const compact = normalize(v.compact !== undefined ? v.compact : unpack(v.packed));
  const sig = typeof v.sig === "string" && SIG.test(v.sig) ? v.sig : null;
  return { compact, sig };
}

/** Whether the stops of an edit (validEdit's plan: [{page, start, end, role, why}] a day) come with the words the
 *  server wrote for them: `base` is what the page sends with an edit — the plan on screen's compact form without its
 *  stops ({k, e, t, s, n}) and its signature — and the compact form is made again from the edit's own stops and
 *  conditions (`c`, validConditions'). True only when that signature checks out under `key` (a reader cannot have the
 *  server sign reasons they wrote: planner.createPlanHandler drops every reason of an edit that is not proven). */
export function baseValid(base, c, days, key) {
  if (!key || !base || typeof base !== "object" || Array.isArray(base)) return false;
  try {
    const compact = normalize({ v: SHARE_VERSION, c: compactConditions(c), k: base.k, e: base.e, t: base.t, s: base.s, n: base.n,
      d: days.map((d) => d.stops.map((st) => [st.page, st.start, st.end, ROLE[st.role] || "v", st.why || ""])) });
    return sigValid(compact, base.sig, key);
  } catch {
    return false;
  }
}

/** The conditions of a normalized compact form, as validConditions reads them (no note). */
export function conditionsOf(n) {
  const c = { ...n.c, kids: [...n.c.kids], prefs: [...n.c.prefs], needs: [...n.c.needs] };
  for (const k of ["date", "days", "start", "end", "move", "with", "adults"]) if (c[k] === null) delete c[k];
  return c;
}

/** Messages for a link that cannot be opened (the page shows them as they are). */
export const VIEW_ERRORS = {
  bad_link: "공유 링크를 읽을 수 없어요. 링크가 잘렸는지 확인해 주세요.",
  view_expired: "1년 넘게 지난 코스라 열 수 없어요.",
  view_gone: "이 코스의 장소가 사이트에서 빠져 열 수 없어요.",
  rate_limited: "링크를 너무 자주 열었어요. 1분 뒤에 다시 열어 주세요.",
  daily_limit: "오늘 열 수 있는 공유 링크 수를 넘었어요. 내일 다시 열어 주세요.",
  busy: "지금은 공유 링크를 열 수 없어요. 잠시 뒤 다시 시도해 주세요.",
};
