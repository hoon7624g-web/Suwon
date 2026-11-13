"""tools/tourapi_related.py — 연관 관광지·집중률의 장소 잇기와 변환, 공용 클라이언트(키 가림·재시도·상한). 네트워크 없음."""
import gzip
import json
import urllib.error

import pytest

from pipeline.tourapi import TourAPIStopError
from tools.tourapi_related import (ApiError, Client, Places, branch_word, build_crowd, build_related, kinds_of, norm,
                                   split_name)

PLACES = [
    {"id": "a1", "name": "동국사", "kind": "attraction", "facts": {"address": "전북특별자치도 군산시 동국사길 16"}},
    {"id": "a2", "name": "군산 동국사 대웅전", "kind": "attraction", "part_of": {"id": "a1", "rel": "inside"},
     "tourapi": {"title": "동국사(군산)"}},
    {"id": "a3", "name": "테디베어박물관", "kind": "attraction", "alternate_names": ["테디베어뮤지엄 군산"]},
    {"id": "a4", "name": "아리랑", "kind": "attraction"},
    {"id": "a5", "name": "몽돌해수욕장 (몽돌해변)", "kind": "attraction"},
    {"id": "a6", "name": "경암동철길마을", "kind": "attraction"},
    {"id": "a7", "name": "불주사 대웅전", "kind": "attraction", "tourapi": {"title": "불주사(군산)"}},
    {"id": "a8", "name": "변산해수욕장", "kind": "attraction"},
    {"id": "w1", "name": "월명공원", "kind": "attraction"},
    {"id": "w2", "name": "월명 공원", "kind": "attraction"},
    {"id": "c1", "name": "무녀도오토캠핑장", "kind": "attraction", "category": "레포츠"},
    {"id": "f1", "name": "고래면옥", "kind": "food", "facts": {"address": "전북특별자치도 군산시 나운5길 8 (나운동)"}},
    {"id": "f2", "name": "이성당", "kind": "food", "facts": {"address": "전북특별자치도 군산시 중앙로 177"}},
    {"id": "f3", "name": "아리랑", "kind": "food"},
    {"id": "f4", "name": "현대옥(미장점)", "kind": "food"},
    {"id": "f5", "name": "가야장", "kind": "food"},
    {"id": "f6", "name": "계곡가든", "kind": "food", "map_id_sources": {"kakao_place_id": {
        "matched_name": "계곡가든꽃게장 군산본부점", "basis": "이름 포함(+군산본부점)·별칭 · 35m(기준 150m) · 도로명 건물번호 일치(금강로 470)"}}},
    {"id": "f7", "name": "장미칼국수", "kind": "food", "map_id_sources": {"kakao_place_id": {
        "matched_name": "장미칼국수 수송직영점", "basis": "이름 포함 · 0m(기준 400m) · 주소 대조 불가(한쪽 없음)"}}},
    {"id": "s1", "name": "에이본 호텔", "kind": "stay"},
    {"id": "s1-dup", "name": "에이본호텔 본관", "kind": "stay", "duplicate_of": "s1"},
    {"id": "n1", "name": "아리랑 코스", "kind": "attraction", "exclude": "not_a_place"},
]


@pytest.fixture(scope="module")
def places():
    return Places(PLACES)


def test_name_forms():
    assert norm("동국사(군산)") == "동국사" and norm("동국사(군산)", keep_brackets=True) == "동국사군산"
    assert split_name("가야장/[중식]") == ("가야장", "")
    assert split_name("보배반점/수송점 [중식]") == ("보배반점", "수송점")
    assert branch_word("군산미장점") == "미장" and branch_word("나운점") == "나운"
    assert branch_word("수송직영점") == "수송" and branch_word("군산나운DT점") == "나운"
    assert branch_word("본점") == ""          # cannot be checked against a name or an address


def test_match_by_name_alternate_and_tourapi_title(places):
    assert places.match("동국사")[0] == "a1"                   # 대웅전 (part_of 동국사) folds into its building
    assert places.match("동국사(군산)")[0] == "a1"
    assert places.match("테디베어뮤지엄/군산")[0] == "a3"       # alternate name, '/군산' read as part of the name
    assert places.match("몽돌해수욕장/몽돌해변")[0] == "a5"
    assert places.match("군산시 경암동 철길마을")[0] == "a6"    # a leading '군산시 ' dropped
    pid, basis, _ = places.match("불주사(불지사)")
    assert (pid, basis) == ("a7", "tourapi_title")
    assert places.match("에이본호텔 본관", {"stay"})[0] == "s1"  # a duplicate's name → the original place
    assert places.match("에이본호텔/군산", {"stay"})[0] == "s1"  # '/군산' is no branch
    assert places.match("가야장/[중식]", {"food"})[0] == "f5"
    assert places.match("아리랑 코스")[0] is None               # not a place


def test_branch_suffix_needs_a_name_or_address_that_says_so(places):
    pid, basis, _ = places.match("고래면옥/나운점", {"food"})
    assert pid == "f1" and basis.endswith("+branch")             # 나운5길 · (나운동)
    assert places.match("현대옥/군산미장점", {"food"})[0] == "f4"
    assert places.match("이성당/본점", {"food"}) == (None, "none", [])
    assert places.match("이성당/수송점", {"food"})[0] is None    # address does not say 수송
    assert places.match("동국사/5부두")[0] is None


def test_kakao_name_only_when_its_road_address_agreed(places):
    assert places.match("계곡가든꽃게장/군산본부점", {"food"})[:2] == ("f6", "kakao_name")
    assert places.match("장미칼국수/수송직영점", {"food"})[0] is None


def test_kind_and_ambiguity(places):
    assert places.match("아리랑", {"food"})[0] == "f3"
    assert places.match("아리랑", {"attraction"})[0] == "a4"
    assert places.match("아리랑") == (None, "ambiguous", ["a4", "f3"])
    assert places.match("월명공원")[:2] == (None, "ambiguous")
    assert places.match("무녀도오토캠핑장", kinds_of("숙박", "캠핑"))[0] == "c1"
    assert places.match("무녀도오토캠핑장", kinds_of("숙박", "모텔"))[0] is None
    assert places.match("고래면옥/나운점", kinds_of("관광지"))[0] is None


def _rel(center, rank, name, large="관광지", mid="자연관광", small="자연경관(하천/해양)", sg="군산시", center_sg="군산시"):
    return {"baseYm": "202609", "tAtsNm": center, "signguNm": center_sg, "rlteTatsNm": name, "rlteRank": str(rank),
            "rlteRegnNm": "전북특별자치도", "rlteSignguNm": sg, "rlteCtgryLclsNm": large, "rlteCtgryMclsNm": mid,
            "rlteCtgrySclsNm": small}


def test_build_related(places):
    items = [_rel("동국사", 3, "이성당/본점", "음식", "음식", "간이음식"),
             _rel("동국사", 1, "변산해수욕장", sg="부안군"),
             _rel("동국사", 2, "고래면옥/나운점", "음식", "음식", "한식"),
             _rel("임피역/폐역", 1, "동국사", "관광지", "문화관광", "역사유적지")]
    data, rep = build_related(items, places, "202609", "2026-10-31")
    assert data["base_ym"] == "202609" and data["source"]["base_date"] == "2026-09"
    assert data["source"]["url"] == "https://www.data.go.kr/data/15128560/openapi.do"
    assert data["centers"] == {"a1": {"name": "동국사", "match": "name"}}
    got = data["places"]["a1"]
    assert [e["rank"] for e in got] == [1, 2, 3]
    assert got[0] == {"rank": 1, "name": "변산해수욕장", "place_id": None, "category": "관광지",
                      "subcategory": "자연관광 > 자연경관(하천/해양)", "region": "전북특별자치도 부안군"}  # outside 군산: no link
    assert got[1]["place_id"] == "f1" and got[2]["place_id"] is None
    assert data["unmatched_centers"] == [{"name": "임피역/폐역", "reason": "이름이 같은 장소 없음", "rows": 1}]
    assert rep["related_matched"] == {"고래면옥/나운점"} and rep["related_unmatched"] == {"이성당/본점"}


def test_build_related_two_centres_on_one_place_are_not_used(places):
    items = [_rel("동국사", 1, "아리랑", "음식", "음식", "한식"), _rel("동국사(군산)", 1, "아리랑", "음식", "음식", "한식")]
    data, _ = build_related(items, places, "202609", "2026-10-31")
    assert data["places"] == {} and len(data["unmatched_centers"]) == 2


def test_build_crowd_keeps_the_numbers(places):
    row = lambda name, day, v: {"baseYmd": day, "areaCd": "52", "signguCd": "52130", "signguNm": "군산시",
                                "tAtsNm": name, "cnctrRate": v}
    items = [row("동국사(군산)", "20261101", "75.5"), row("동국사(군산)", "20261031", "100"),
             row("옥돌해수욕장", "20261031", "5.12")]
    data, rep = build_crowd(items, places, "2026-10-31")
    assert data["places"] == {"a1": {"name": "동국사(군산)", "match": "name",
                                     "days": {"2026-10-31": 100, "2026-11-01": 75.5}}}
    assert data["period"] == {"start": "2026-10-31", "end": "2026-11-01"} and data["range_seen"] == [5.12, 100]
    assert data["unmatched"] == [{"name": "옥돌해수욕장", "reason": "이름이 같은 장소 없음"}]
    assert data["source"]["url"] == "https://www.data.go.kr/data/15128555/openapi.do"
    assert "가장 붐비는 시기를 100" in data["_about"] and rep == {"rows": 3, "names": 2, "matched": 1}


# ---- client ------------------------------------------------------------------------------------------------------
KEY = "abc+def/ghi=="
OK = {"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                   "body": {"items": {"item": [{"x": "1"}]}, "numOfRows": 1, "pageNo": 1, "totalCount": 1}}}


def test_client_retries_a_reset_connection_and_caches(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))
        return json.dumps(OK)
    c = Client(KEY, "Svc", tmp_path, fetch=fetch, min_interval=0, wait=0)
    assert c.page("op", a=1) == ([{"x": "1"}], 1)
    assert len(calls) == 3 and c.calls == 3
    assert "MobileOS=ETC" in calls[0] and "MobileApp=WebforAI" in calls[0] and "_type=json" in calls[0]
    assert c.page("op", a=1) == ([{"x": "1"}], 1) and len(calls) == 3 and c.cache_hits == 1
    assert all(KEY not in gzip.decompress(p.read_bytes()).decode("utf-8") for p in tmp_path.iterdir())


def test_client_masks_the_key_and_shows_the_provider_message(tmp_path):
    def gw_error(url):
        return json.dumps({"responseTime": "2026-10-31T09:09:34", "resultCode": "10",
                           "resultMsg": "INVALID_REQUEST_PARAMETER_ERROR(signguCode)"})
    with pytest.raises(ApiError, match=r"resultCode=10 INVALID_REQUEST_PARAMETER_ERROR\(signguCode\)"):
        Client(KEY, "Svc", tmp_path, fetch=gw_error, min_interval=0).page("op")

    def down(url):
        raise urllib.error.URLError(f"cannot reach {url}")
    with pytest.raises(ApiError) as err:
        Client(KEY, "Svc", tmp_path, fetch=down, min_interval=0, wait=0).page("op")
    assert "«KEY»" in str(err.value) and "abc" not in str(err.value)


def test_client_stops_at_the_call_cap(tmp_path):
    c = Client(KEY, "Svc", tmp_path, fetch=lambda url: json.dumps(OK), max_calls=1, min_interval=0)
    c.page("op", p=1)
    with pytest.raises(TourAPIStopError):
        c.page("op", p=2)


def test_confirmed_names_join_the_real_places():
    """2026-10-31: the five names a person confirmed as other names of the same place (tools/tourapi_related.CONFIRMED)."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "data" / "gunsan"
    rel = json.loads((root / "related.json").read_text("utf-8"))
    crowd = json.loads((root / "crowd.json").read_text("utf-8"))
    assert rel["centers"]["gunsan-305951"]["match"] == "confirmed" and not rel.get("unmatched_centers")
    assert crowd["places"]["tourapi-2748431"]["match"] == "confirmed"   # 옥돌해수욕장 → 옥돌해변
