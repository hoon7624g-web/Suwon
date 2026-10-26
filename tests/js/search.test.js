// node --test tests/js/ — the site search (templates/assets/search.js) on a built site's search pages and indexes
// (SEARCH_SITE_DIR: tests/test_desc80.py runs this file on its production build of this city's data; otherwise
// public/, the deployed build — there the tests that need the query words on the form are skipped until a build has
// them), run in Node through tests/js/search_dom.js. The query words came from the first site (2026-10-18, 0ae47895e ·
// 387a53773): its review found that query words had dropped words ('빵 맛집' listed every restaurant, '주차할 곳' found
// nothing). So: the rows found are never fewer than those the script before the query words found
// (tests/fixtures/search_before_concepts.js, this site's search.js before them) for every name, menu item, area and
// guide-title word of each version's index; a word next to a concept stays a condition; a concept word reads as one
// only where it stands as a word or a word start; the related guides; a menu's price is shown whole.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { loadSearch, sitePages } from "./search_dom.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SITE = process.env.SEARCH_SITE_DIR || path.join(ROOT, "public");
const BASE = readFileSync(path.join(ROOT, "tests", "fixtures", "search_before_concepts.js"), "utf8");
const NEW = readFileSync(path.join(ROOT, "templates", "assets", "search.js"), "utf8");
const CODES = ["ko", "en", "de", "fr", "es", "ja", "zh-hans", "zh-hant", "ru"]
  .filter((c) => existsSync(path.join(SITE, c === "ko" ? "" : c, "search", "index.json")));
const PAGES = Object.fromEntries(sitePages(SITE, CODES).map((p) => [p.code, p]));
const ROWS = Object.fromEntries(Object.keys(PAGES).map((c) => [c, JSON.parse(PAGES[c].rows)]));
// the query words (present.SEARCH_CONCEPTS) are on the search form of a build since this port
const WORDS = "data-concepts" in PAGES.ko.attrs ? false : "this build's search form has no query words (data-concepts)";
const REVIEW = ["빵", "회", "마을", "주차할 곳", "숙박할 곳", "cafe", "cafes", "rain", "비 오는 날 아이랑",
  "비오는날 아이랑 갈만한곳 추천해줘"];
const SPLIT = /[\s·\-()（）\[\]|,\/、，:：—–]+/;
const MENU = /\s*(?:,(?!\d{3}(?:\D|$))|[\/·、，])\s*/;
const flat = (s) => String(s || "").toLowerCase().replace(/[\s·\-()（）\[\]|,]/g, "");
const text = (row) => ["n", "a", "o", "v", "m", "g", "d", "r", "t"].map((f) => flat(row[f])).join("\n");

// a version's queries: each name (and its names in the other versions), menu item, area, travel area and guide-title word
function corpus(rows) {
  const out = new Set(REVIEW);
  for (const r of rows) {
    [r.n, r.d, r.r].forEach((w) => out.add(w));
    String(r.m || "").split(MENU).forEach((w) => out.add(w));
    String([r.a, r.o].filter(Boolean).join(" · ")).split(/\s+·\s+/).forEach((w) => out.add(w));
    if (r.k === "guide") r.n.split(SPLIT).forEach((w) => out.add(w));
  }
  return [...out].filter((q) => q && q.trim());
}

const scripts = {};
function search(code, which = "new") {
  const key = code + which;
  if (!scripts[key]) scripts[key] = loadSearch(which === "new" ? NEW : BASE, { ...PAGES[code], limit: 100000 });
  return (q) => scripts[key].search(q);
}
const rowOf = (code, href) => ROWS[code].find((r) => r.p === href);
const guide = (code, f) => (ROWS[code].find((r) => r.k === "guide" && f(r)) || {}).p;

test("the rows found are never fewer than those the script before the query words found, in every version", async () => {
  const lost = [];
  for (const code of CODES) {
    const base = search(code, "base"), now = search(code);
    for (const q of corpus(ROWS[code])) {
      const was = (await base(q)).hits, is = new Set((await now(q)).hits);
      const gone = was.filter((h) => !is.has(h));
      if (gone.length) lost.push(`${code} ‘${q}’: ${gone.slice(0, 3).join(" ")}`);
    }
  }
  assert.ok(CODES.length >= 1);
  assert.deepEqual(lost, []);
});

test("a word next to another stays a condition: every row found has it (or the query whole)", async () => {
  const said = new Set(WORDS ? [] : JSON.parse(PAGES.ko.attrs["data-concepts"]).flatMap((c) => c.say.map(flat)));
  const nouns = new Set(["빵", "회", "마을", "떡", "집", "물", "밥", "차", "도로"]);
  ROWS.ko.forEach((r) => String(r.m || "").split(MENU).forEach((w) => /^[가-힣]{1,2}$/.test(w) && nouns.add(w)));
  const ko = search("ko"), wrong = [];
  for (const w of [...nouns].filter((n) => !said.has(n))) {
    for (const c of ["맛집", "카페", "주차"]) {
      for (const q of [`${w} ${c}`, `${c} ${w}`]) {
        const r = await ko(q), whole = flat(q);
        const without = r.hits.filter((h) => !text(rowOf("ko", h)).includes(w) && !text(rowOf("ko", h)).includes(whole));
        if (without.length) wrong.push(`‘${q}’: ${without.length} of ${r.hits.length} without ${w}`);
      }
    }
  }
  assert.ok(nouns.size > 10);
  assert.deepEqual(wrong, []);
});

test("a concept word reads as one where it stands as a word or a word start", { skip: WORDS }, async () => {
  const ko = search("ko"), base = search("ko", "base");
  for (const [q, ws] of [["숙박할 곳", ["숙소", "숙박", "펜션", "민박", "호텔", "캠핑"]], ["잘 곳 추천해줘", ["숙소", "숙박", "펜션", "민박", "호텔", "캠핑"]],
    ["아이랑 놀만한곳 추천해줘", ["아이와", "어린이", "가족", "키즈"]], ["카페 갈만한 곳", ["카페", "커피"]]]) {
    const r = await ko(q);
    assert.ok(r.hits.length, q);
    assert.deepEqual(r.hits.filter((h) => !ws.some((w) => text(rowOf("ko", h)).includes(w))), [], q);
  }
  // a run inside a longer word is no concept: found as typed, nothing also searched, no related guides
  for (const q of ["아이스크림", "버스킹", "가족사진관"]) {
    const r = await ko(q);
    assert.equal(r.syn, "", q);
    assert.deepEqual(r.related, [], q);
    assert.deepEqual(r.hits, (await base(q)).hits, q);
  }
});

test("the evaluation query: rows with both concepts first; nothing found whole, the guides of each part; the planner",
  { skip: WORDS }, async () => {
    const RAIN = ["비오는", "실내", "박물관"], KIDS = ["아이와", "어린이", "가족", "키즈"];
    const hasBoth = (row) => RAIN.some((w) => text(row).includes(w)) && KIDS.some((w) => text(row).includes(w));
    const together = ROWS.ko.filter(hasBoth).length;   // this city's data: rows with both, or none
    for (const q of ["비 오는 날 아이랑", "비오는날아이랑", "비오는날 아이랑 갈만한곳 추천해줘"]) {
      const r = await search("ko")(q);
      const both = (h) => hasBoth(rowOf("ko", h));
      if (together) {
        assert.ok(r.hits.length, q);
        assert.deepEqual(r.hits.filter((h) => !both(h)), [], q);
      } else {   // no row has both: nothing found whole, the guides of the parts instead
        assert.deepEqual(r.hits, [], q);
        assert.ok(r.none && r.related.length, q);
      }
      assert.match(r.syn, /^함께 찾은 말: 비 오는 → /, q);
    }
    // two concepts no row has together: the guides of each, as '관련 가이드' (the first site's '비 오는 날 아이랑' case)
    const rain = guide("ko", (r) => /비 오는 날/.test(`${r.a} ${r.n}`)), pet = guide("ko", (r) => /반려동물/.test(`${r.a} ${r.n}`));
    if (rain && pet) {
      const r = await search("ko")("비 오는 날 반려동물");
      assert.deepEqual([r.hits, new Set(r.related)], [[], new Set([rain, pet])]);
      assert.ok(r.none);
    }
    // a query that plans a trip links to the planner on the Korean page only
    assert.equal((await search("ko")("1박 2일 일정")).plan, "data-planner" in PAGES.ko.attrs);
    if (PAGES.en) assert.equal((await search("en")("1박 2일 일정")).plan, false);
  });

test("a menu item is shown with its price whole ('7,500원', never '7')", async () => {
  const row = ROWS.ko.find((r) => /\d,\d{3}원/.test(r.m || ""));
  if (!row) return;
  const item = String(row.m).split(MENU).find((x) => /\d,\d{3}원/.test(x));
  const dish = item.replace(/\s*\d[\d,]*\s*원.*$/, "").trim();
  const r = await search("ko")(dish);
  const shown = [...r.html.matchAll(/메뉴: ([^<]*)/g)].map((m) => m[1]);
  assert.ok(shown.length, dish);
  assert.deepEqual(shown.filter((s) => /\d,$|\s\d{1,2}$/.test(s.trim())), [], shown.join(" | "));
});
