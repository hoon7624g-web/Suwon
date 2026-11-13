// The access route's words read as the data says them (live check 2026-10-19: '출입구까지 경사로가 설치되어 있지
// 않음' was read as a ramp, so 말랭이마을 went into a wheelchair user's plan as reachable).
import test from "node:test";
import assert from "node:assert/strict";
import { needAt } from "../../chatbot/plan_state.js";

const at = (...routes) => ({ ac: routes.map((t) => ({ k: "accessible_route", t })) });

test("a ramp, a lift or no step at the door is 'ok'; a sentence that says there is none is 'no'", () => {
  for (const t of ["출입구까지 경사로가 설치되어 있음(완만함)", "출입구까지 턱이 없어 휠체어 접근 가능함", "주출입구 경사로 완만함",
    "출입구에 엘리베이터 설치되어 있음", "무단차 공원", "주출입구까지 평지로 연결되어 휠체어 접근 가능함"]) {
    assert.equal(needAt("wheelchair", at(t), "visit").state, "ok", t);
    assert.equal(needAt("stroller", at(t), "visit").state, "ok", t);
  }
  for (const t of ["출입구까지 경사로가 설치되어 있지 않음", "엘리베이터 없음", "계단만 있음", "출입구 접근 불가"]) {
    const r = needAt("wheelchair", at(t), "visit");
    assert.equal(r.state, "no", t);
    assert.equal(r.text, `출입구: ${t}`);
  }
  // a 'no' sentence is read before an 'ok' one; words that say neither stay unknown
  assert.equal(needAt("wheelchair", at("주출입구 경사로 완만함", "후문 경사로가 설치되어 있지 않음"), "visit").state, "no");
  assert.equal(needAt("wheelchair", at("공사중"), "visit").state, "unknown");
  assert.equal(needAt("wheelchair", {}, "visit").state, "unknown");
});

test("round-6 verifier: a steep ramp or earth and stones are something a wheelchair user checks; two sources that read differently are both shown", () => {
  for (const t of ["출입구까지 경사로가 설치되어 있음(완만하지 않음)", "출입구까지 평지로 되어 있으나 흙(돌) 구간 있음", "공사중"]) {
    const r = needAt("wheelchair", at(t), "visit");
    assert.equal(r.state, "unknown", t);
    assert.equal(r.text, `출입구: ${t} — 확인 필요`);
  }
  // a stroller goes on a steep ramp or a path of earth: as before
  assert.equal(needAt("stroller", at("출입구까지 경사로가 설치되어 있음(완만하지 않음)"), "visit").state, "ok");
  // 3.1운동 100주년 기념관: 군산시's words and TourAPI's, read differently — both, to be checked by phone; never 'ok'
  const two = { ac: [{ k: "accessible_route", t: "출입구까지 경사로가 설치되어 있음(완만하지 않음)", p: "군산시 문화관광" },
    { k: "accessible_route", t: "출입구까지 턱이 없어 휠체어 접근 가능함", p: "한국관광공사 TourAPI" }] };
  assert.deepEqual(needAt("wheelchair", two, "visit"), { state: "unknown",
    text: "출입구: 출입구까지 경사로가 설치되어 있음(완만하지 않음)(군산시 문화관광) / 출입구까지 턱이 없어 휠체어 접근 가능함(한국관광공사 TourAPI) — 출처마다 달라 방문 전 전화 확인" });
  assert.equal(needAt("stroller", two, "visit").state, "ok");
});
