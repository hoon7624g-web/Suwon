"""tools/ferry_gunsan.py — 한국해양교통안전공단 여객선 운항상태에서 군산 항로를 고르는 규칙(기항지가 군산시인 면허항로),
섬 장소는 대응표로만 잇는 규칙, 실시간 값·인원 수를 ferry.json에 넣지 않는 규칙. 네트워크 없이 작은 고정 응답으로만 본다."""
import datetime as dt
import json

import pytest

from tools import ferry_gunsan as F


def row(ship, code, name, port, stts, when, sail="900", drc="정방향", sea=("03", "군산어청(직)"), emkt=None):
    return {"psnshp_cd": "J37", "psnshp_nm": ship, "rlvt_ymd": when[:10].replace("-", ""), "sail_tm": sail,
            "lcns_seawy_cd": code, "lcns_seawy_nm": name, "nvg_seawy_cd": sea[0], "nvg_seawy_nm": sea[1],
            "nvg_drc_cd": "1", "nvg_drc_nm": drc, "nvg_stts_cd": {"출항중": "4", "운항중": "2", "완료": "3"}[stts],
            "nvg_stts_nm": stts, "nvg_stts_chg_dt": when, "portcl_cd": {"군산": "J000", "어청": "J014", "격포": "J019",
                                                                      "인천": "D000", None: ""}[port],
            "portcl_nm": port, "emkt_nope": emkt, "lvsp_nope": None, "vsl_no": "KSR175806"}


# 2026-10-30 응답에서 줄인 표본: 군산-어청 한 번 왕복 사건, 격포-위도(부안) 한 행, 인천 항로 한 행
DAY = [
    row("고군산카훼리호", "J03", "군산-어청", "군산", "출항중", "2026-10-30T08:58:00", emkt=41),
    row("고군산카훼리호", "J03", "군산-어청", None, "운항중", "2026-10-30T09:02:00"),
    row("고군산카훼리호", "J03", "군산-어청", "어청", "완료", "2026-10-30T11:40:00"),
    row("고군산카훼리호", "J03", "군산-어청", "어청", "출항중", "2026-10-30T13:01:00", sail="1300", drc="역방향"),
    row("파장금카페리", "J05", "격포-위도", "격포", "출항중", "2026-10-30T09:35:00", sail="935", sea=("01", "격포위도")),
    row("코리아스타", "D05", "인천-이작", "인천", "출항중", "2026-10-30T08:31:16", sail="830", sea=("01", "자이-승-자")),
]


def test_a_route_is_gunsan_when_it_calls_at_a_gunsan_port():
    assert F.gunsan_routes(DAY) == {"J03"}
    # the raw file keeps the routes of the same 운항관리센터 letter (격포-위도), never another center's
    assert {r["lcns_seawy_cd"] for r in F.keep_rows(DAY)} == {"J03", "J05"}
    assert F.hm("830") == "08:30" and F.hm("1300") == "13:00"


def test_ferry_json_keeps_structure_not_live_status_or_passenger_counts():
    data = F.build({"2026-10-30": F.keep_rows(DAY)}, "2026-10-31")
    assert set(data) == {"_about", "source", "params", "fields", "status", "routes", "other_routes", "places"}
    assert data["source"]["url"] == "https://www.data.go.kr/data/15142304/openapi.do"
    rt = data["routes"]["J03"]
    assert rt["ports"] == [{"code": "J000", "name": "군산"}, {"code": "J014", "name": "어청"}]
    assert rt["ships"] == [{"code": "J37", "name": "고군산카훼리호", "vsl_no": "KSR175806"}]
    assert rt["samples"]["2026-10-30"] == [
        {"ship": "고군산카훼리호", "direction": "정방향", "sail": "09:00", "sea_route": "군산어청(직)",
         "calls": ["군산", "어청"], "last_status": "완료"},
        {"ship": "고군산카훼리호", "direction": "역방향", "sail": "13:00", "sea_route": "군산어청(직)",
         "calls": ["어청"], "last_status": "출항중"}]
    assert data["other_routes"] == {"J05": {"name": "격포-위도", "ports": ["격포"], "why": "기항지가 군산시가 아니다"}}
    assert data["status"] == {"2": "운항중", "3": "완료", "4": "출항중"}
    # 섬 장소는 대응표로만: 어청 → 어청도 장소; 군산(육지 터미널)은 장소가 없다
    assert rt["places"] == F.ISLAND_PLACES["어청"] and data["places"] == {"tourapi-126297": ["J03"]}
    assert "41" not in json.dumps(data["routes"]) and "emkt_nope" not in json.dumps(data["routes"])


def test_only_past_days_are_cached_and_every_page_is_read(tmp_path, monkeypatch):
    pages = {1: DAY[:4], 2: DAY[4:]}
    asked = []

    def fake(url, params, key, budget, timeout=60):
        budget.spend()
        asked.append(params["pageNo"])
        body = {"response": {"header": {"resultCode": "200", "resultMsg": "NORMAL_SERVICE"},
                             "body": {"items": {"item": pages[params["pageNo"]]}, "totalCount": 6}}}
        return json.dumps(body, ensure_ascii=False)
    monkeypatch.setattr(F, "ROWS", 4)
    monkeypatch.setattr(F, "api_get", fake)
    b = F.Budget(10)
    assert len(F.fetch_day("20261030", "k", b, tmp_path, dt.date(2026, 10, 31))) == 6 and asked == [1, 2]
    assert len(F.fetch_day("20261030", "k", b, tmp_path, dt.date(2026, 10, 31))) == 6 and b.used == 2   # cached
    F.fetch_day("20261031", "k", b, tmp_path, dt.date(2026, 10, 31))
    assert b.used == 4 and not list(tmp_path.glob("20261031-*"))   # today is never cached


def test_a_provider_refusal_in_the_body_is_an_error():
    with pytest.raises(F.ApiError):
        F.items_of({"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}})
    one = {"response": {"header": {"resultCode": "200"}, "body": {"items": {"item": DAY[0]}, "totalCount": 1}}}
    assert F.items_of(one) == ([DAY[0]], 1)
    assert F.items_of({"response": {"header": {"resultCode": "200"}, "body": {"items": "", "totalCount": 0}}}) == ([], 0)
