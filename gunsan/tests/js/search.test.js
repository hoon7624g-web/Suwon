// node --test tests/js/ — the site search (templates/assets/search.js) on a built site's search pages and indexes
// (SEARCH_SITE_DIR: tests/test_present.py runs this file on its preview build of data/gunsan; otherwise public/, the
// deployed build — there the tests that need the query words on the form are skipped until a build has them), run in
// Node through tests/js/search_dom.js. Review round 3 (2026-10-18): two rounds of query words dropped words — '빵
// 맛집' listed every restaurant (빵 dropped), '섬여행'·'마을'·'사랑' vanished through their endings, '주차할 곳' found
// nothing, 'cafe' missed 'Cafes'. So: the rows found are never fewer than those the script before the query words
// found (tests/fixtures/search_99a303949.js, commit 99a303949's search.js) for every name, menu word, 동·권역 and
// guide-title word of each version's index and the review's queries, in Korean and six other versions; a word next
// to a concept stays a condition; a concept word reads as one only where it stands as a word or a word start; the
// related guides.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { loadSearch, sitePages } from "./search_dom.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SITE = process.env.SEARCH_SITE_DIR || path.join(ROOT, "public");
const BASE = readFileSync(path.join(ROOT, "tests", "fixtures", "search_99a303949.js"), "utf8");
const NEW = readFileSync(path.join(ROOT, "templates", "assets", "search.js"), "utf8");
const CODES = ["ko", "en", "de", "fr", "es", "ja", "zh-hans"];
const PAGES = Object.fromEntries(sitePages(SITE, [...CODES, "ru"]).map((p) => [p.code, p]));
const ROWS = Object.fromEntries(Object.keys(PAGES).map((c) => [c, JSON.parse(PAGES[c].rows)]));
// the query words (present.SEARCH_CONCEPTS) are on the search form of a build since 2026-10-18
const WORDS = "data-concepts" in PAGES.ko.attrs ? false : "this build's search form has no query words (data-concepts)";
// the review's queries, in every version
const REVIEW = ["빵", "회", "섬", "배", "섬여행", "마을", "사랑", "주차할 곳", "숙박할 곳", "cafe", "cafes", "gyeongamdong",
  "Gyeongam-dong", "rain", "비 오는 날 아이랑", "비오는날 아이랑 갈만한곳 추천해줘"];
const SPLIT = /[\s·\-()（）\[\]|,\/、，:：—–]+/;
const flat = (s) => String(s || "").toLowerCase().replace(/[\s·\-()（）\[\]|,]/g, "");
const text = (row) => ["n", "a", "o", "v", "m", "g", "d", "r", "t"].map((f) => flat(row[f])).join("\n");

// a version's queries: each name (and its names in the other versions), menu word, 동, 권역 and guide-title word
function corpus(rows) {
  const out = new Set(REVIEW);
  for (const r of rows) {
    [r.n, r.d, r.r].forEach((w) => out.add(w));
    String(r.m || "").split(/\s*[,\/·、，]\s*/).forEach((w) => out.add(w));
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
  assert.deepEqual(lost, []);
});

test("a word next to another stays a condition: every row found has it (or the query whole)", async () => {
  // the review's nouns, a few more of one syllable and every dish of one or two on the menus, before and after a
  // concept word; a noun that is a concept word itself ('밤') is left out
  const said = new Set(WORDS ? [] : JSON.parse(PAGES.ko.attrs["data-concepts"]).flatMap((c) => c.say.map(flat)));
  const nouns = new Set(["빵", "회", "섬", "배", "섬여행", "마을", "사랑", "떡", "집", "물", "밥", "차", "도로"]);
  ROWS.ko.forEach((r) => String(r.m || "").split(/\s*[,\/·、，]\s*/).forEach((w) => /^[가-힣]{1,2}$/.test(w) && nouns.add(w)));
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
  assert.ok(nouns.size > 20);
  assert.deepEqual(wrong, []);
  // plain words as before, inside the row's text: 'cafe' is in 'Cafes', 'gyeongam' and 'dong' in 'Gyeongam-dong'
  for (const q of ["cafe eunpa", "cafe Naun-dong", "gyeongam dong"]) {
    const ws = q.split(SPLIT).map(flat), want = ROWS.en.filter((r) => ws.every((w) => text(r).includes(w))).map((r) => r.p);
    assert.ok(want.length, q);
    assert.deepEqual(new Set((await search("en")(q)).hits), new Set(want), q);
  }
});

test("a concept word reads as one where it stands as a word or a word start", { skip: WORDS }, async () => {
  const ko = search("ko"), base = search("ko", "base");
  for (const [q, ws] of [["주차할 곳", ["주차"]], ["주차 가능한 곳", ["주차"]], ["주차장 있는 곳", ["주차"]],
    ["숙박할 곳", ["숙소", "숙박", "펜션", "민박"]], ["아이랑 놀만한곳 추천해줘", ["아이와", "어린이", "가족"]]]) {
    const r = await ko(q);
    assert.ok(r.hits.length, q);
    assert.deepEqual(r.hits.filter((h) => !ws.some((w) => text(rowOf("ko", h)).includes(w))), [], q);
  }
  // a run inside a longer word is no concept: found as typed, nothing also searched, no related guides
  for (const q of ["아이스크림", "버스킹", "가족사진관", "밤바다"]) {
    const r = await ko(q);
    assert.equal(r.syn, "", q);
    assert.deepEqual(r.related, [], q);
    assert.deepEqual(r.hits, (await base(q)).hits, q);
  }
  const night = await ko("밤에");
  assert.ok(night.hits.length && night.syn.startsWith("함께 찾은 말: 밤 → 야경"), night.syn);
});

test("the related guides: the evaluation query, the most parts first, Latin words at a word start, stop words",
  { skip: WORDS }, async () => {
    const rain = guide("ko", (r) => r.a === "비 오는 날"), kids = guide("ko", (r) => r.a === "가족여행");
    for (const q of ["비 오는 날 아이랑", "비오는날아이랑", "비오는날 아이랑 갈만한곳 추천해줘"]) {
      const r = await search("ko")(q);
      assert.deepEqual([r.hits, r.related], [[], [rain, kids]], q);
      assert.ok(r.none && r.syn.includes("실내") && r.syn.includes("아이와"), q);
    }
    const ja = await search("ja")("비 오는 날 아이랑");
    assert.deepEqual(ja.related, [guide("ja", (r) => /비 오는 날/.test(r.o)), guide("ja", (r) => /아이와 함께/.test(r.o))]);
    // a query of three parts: the guides that have two of them (선유도 and 장자도), not the rainy-day guide's one
    const isle = await search("ko")("비 오는 날 선유도 장자도");
    assert.ok(isle.related.length && !isle.related.includes(rain), isle.related);
    assert.deepEqual(isle.related.filter((h) => !["선유도", "장자도"].every((w) => text(rowOf("ko", h)).includes(w))), []);
    const go = await search("ko")("고군산군도가볼만한곳");
    assert.ok(go.related.length && go.related.every((h) => text(rowOf("ko", h)).includes("고군산군도")), go.related);
    const en = await search("en")("things to do in the rain");
    assert.deepEqual([en.hits, en.related], [[], [guide("en", (r) => r.a === "Rainy day")]]);
    // clause words are no part of the related guides' search: 'quand', 'cuándo', 'wann', 'когда' bring no guide
    // 'where and when to eat jjamppong' ('où et quand en manger', '¿dónde y cuándo comerlos?')
    for (const [code, q, want] of [["fr", "que faire quand il pleut", []], ["es", "qué hacer cuándo llueve", []],
      ["es", "qué hacer cuando llueve", []], ["de", "wann regnet es", []],
      ["ru", "что делать когда дождь", [guide("ru", (r) => /비 오는 날/.test(r.o))]]]) {
      const r = await search(code)(q);
      assert.deepEqual([r.hits, r.related], [[], want], `${code} ${q}`);
    }
  });

test("the related guides: a query of two or more parts lists the guides that have two or more while any does",
  { skip: WORDS }, async () => {
    // review 2026-10-18, fourth round: 'rainy day with kids' listed 'A car-free day trip …' second and 'Raw fish
    // restaurants … closing days' fifth, each for the one word 'day'. The guides that have more of the query's parts
    // come first, concepts and plain words alike, then those with more concepts; while one guide has two or more
    // parts, a guide with one is not listed. UI review 2026-10-19: 'day' is no part (as 날 is not), so the query asks
    // for rain and kids as '비 오는 날 아이랑' does — no guide has both: the two guides of one, the earliest in its
    // title first; the same in the other versions
    const en = await search("en")("rainy day with kids");
    assert.deepEqual([en.hits, en.related], [[], [guide("en", (r) => r.a === "Family trip"), guide("en", (r) => r.a === "Rainy day")]]);
    for (const [code, q] of [["fr", "jour de pluie avec enfants"], ["es", "día de lluvia con niños"],
      ["ru", "дождливый день с детьми"]]) {
      const r = await search(code)(q);
      assert.deepEqual(new Set(r.related), new Set([guide(code, (x) => /비 오는 날/.test(x.o)), guide(code, (x) => /아이와 함께/.test(x.o))]), q);
    }
    // no guide has two parts: those with one, and the first one is about what was asked — a part in its title; a
    // plain word a title names ranks with the concept's guides (UI review 2026-10-19: '빵집 주차' listed five 주차
    // guides and no 빵집 one)
    for (const [q, first] of [["빵집 주차", /^군산 관광지 근처 공영주차장/], ["아이스크림 맛집", /^군산 맛집, 메뉴별로/]]) {
      const r = await search("ko")(q);
      assert.ok(r.related.length && r.hits.length === 0, q);
      assert.match(rowOf("ko", r.related[0]).n, first, q);
      assert.deepEqual(r.related.filter((h) => !/주차|빵집|맛집|음식점|식당|먹거리/.test(rowOf("ko", h).n)), [], q);
    }
    const bread = (await search("ko")("빵집 주차")).related.map((h) => rowOf("ko", h).n);
    assert.ok(bread.slice(0, 3).some((n) => n.includes("빵집")), bread);
    // four parts (two concepts): the guides that have two or more, the most parts first, then the most concepts — the
    // rainy-day guide (one part) is not listed
    const lot = await search("ko")("비 오는 날 선유도 장자도 주차");
    const has = (h) => [/선유도/, /장자도/, /주차/, /비오는|실내/].map((rx) => rx.test(text(rowOf("ko", h))));
    const order = lot.related.map((h) => { const x = has(h); return [x.filter(Boolean).length, +x[2] + +x[3]]; });
    assert.ok(lot.hits.length === 0 && lot.related.length > 2 && order.every(([n]) => n >= 2), order);
    assert.deepEqual(order, [...order].sort((a, b) => b[0] - a[0] || b[1] - a[1]));
    assert.ok(order[0][0] > order.at(-1)[0] && order.some(([n, c]) => n === 2 && c === 0), order);
    assert.ok(!lot.related.includes(guide("ko", (r) => r.a === "비 오는 날")));
    // the cases before stay: two concepts no guide has together, each guide of one; a word inside a longer one none
    const kids = await search("ko")("비 오는 날 아이랑");
    assert.deepEqual(kids.related, [guide("ko", (r) => r.a === "비 오는 날"), guide("ko", (r) => r.a === "가족여행")]);
    for (const q of ["아이스크림", "버스킹"]) assert.deepEqual((await search("ko")(q)).related, [], q);
  });
