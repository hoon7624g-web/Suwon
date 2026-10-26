// Hours by weekday as TourAPI writes them for this city's restaurants (data/suwon, 2026-10-26): '평일'·'주중'·'주말', a
// list joined by '/' and a 공휴일 beside a weekday list are read as the date's own hours — never '하나로 읽지 못해'.
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge } from "./first_city.js";

const food = (t, h) => ({ t, k: "place", x: `${t} — 음식점`, f: { kd: "food", ty: "한식", g: [37.28, 127.01], h: [{ p: "한국관광공사 TourAPI", t: h }],
  c: [{ p: "한국관광공사 TourAPI", t: "연중무휴" }] } });
const DOCS = {
  "/places/a/": food("가보정갈비", "- 평일 11:30~21:30 - 토요일 11:00~22:00 - 일요일 11:00~21:30"),
  "/places/b/": food("경안당", "- 월요일 10:30~19:00 - 화요일~금요일 / 일요일 10:00~21:00 - 토요일 10:30~22:00"),
  "/places/c/": food("윤돈", "주중 11:30~20:30 (15:00~17:00 브레이크타임) 14:30 라스트오더 토요일 11:30~20:00 (15:30~17:00 브레이크타임) 15:00 라스트오더"),
  "/places/d/": food("플라잉", "평일 13:00~22:00 주말/공휴일 11:00~22:00"),
};
const kb = new Knowledge({ catalog: "# c", docs: { v: 1, site: "https://suwon.webforai.kr", docs: DOCS, alias: {}, ext: [], tickets: [] }, index: { v: 1, docs: {} } });
const checks = (page, date, start, end) => {
  const s = kb.checkPlan({ date, stops: [{ page, start, end }] }).stops[0];
  return [...(s.checks || []), ...(s.flags || [])].join(" | ");
};

test("weekday words in hours: 평일·주중·주말, lists joined by '/', 공휴일 beside them", () => {
  // 2026-10-28 is a Wednesday, 2026-11-01 a Sunday
  for (const p of ["/places/a/", "/places/b/", "/places/c/", "/places/d/"]) {
    assert.doesNotMatch(checks(p, "2026-10-28", "12:00", "13:00"), /하나로 읽지 못해/u, p);
  }
  assert.match(checks("/places/a/", "2026-10-28", "21:00", "22:00"), /21:30/u);          // 평일 closes 21:30
  assert.doesNotMatch(checks("/places/a/", "2026-10-31", "21:00", "21:50"), /21:30/u);   // 토요일 to 22:00
  assert.doesNotMatch(checks("/places/b/", "2026-10-28", "20:00", "20:50"), /19:00/u);   // 수 is 화~금: to 21:00
  assert.match(checks("/places/b/", "2026-10-26", "20:00", "20:50"), /19:00/u);          // 월요일 to 19:00
  assert.match(checks("/places/d/", "2026-10-28", "11:00", "12:00"), /13:00/u);          // 평일 opens 13:00
  assert.doesNotMatch(checks("/places/d/", "2026-11-01", "11:00", "12:00"), /13:00/u);   // 주말 opens 11:00
});
