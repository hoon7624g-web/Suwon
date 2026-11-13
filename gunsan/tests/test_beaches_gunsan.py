"""tools/beaches_gunsan.py — 해양수산부 해수욕장정보·수질적합 여부를 장소에 잇는 규칙(contentid 또는 이름 + 좌표, 후보가
하나일 때만)과 수질 값을 원문 그대로 두는 규칙. 네트워크 없이 작은 고정 응답으로만 본다."""
import pytest

from tools import beaches_gunsan as B

# 2026-10-31 getOceansBeachInfo1(SIDO_NM=전북) 응답의 군산 행과 부안 행 하나
INFO = [
    {"num": 3, "sido_nm": "전북", "gugun_nm": "군산시", "sta_nm": "선유도", "beach_wid": 20.0, "beach_len": 2000.0,
     "beach_knd": "모래", "link_addr": "http://korean.visitkorea.or.kr/kor/bz15/where/where_main_search.jsp?cid=2022531",
     "link_nm": "군산문화관광", "beach_img": None, "link_tel": "선유도보건지소(063-466-2348)",
     "lat": "35.8195890000", "lon": "126.4122090000"},
    {"num": 4, "sido_nm": "전북", "gugun_nm": "부안군", "sta_nm": "격포", "link_addr": "", "lat": "35.6289520000",
     "lon": "126.4700790000"},
]
PLACES = [
    {"id": "tourapi-2022531", "name": "선유도해수욕장", "tourapi": {"contentid": "2022531"},
     "geo": {"lat": 35.8161291406, "lng": 126.4110512809}},
    {"id": "gunsan-static-m2201", "name": "선유도", "geo": {"lat": 35.8102049733, "lng": 126.4124052922}},
    {"id": "tourapi-2759671", "name": "몽돌해수욕장 (몽돌해변)", "tourapi": {"contentid": "2759671"},
     "geo": {"lat": 35.8284888289, "lng": 126.4022890673}},
]


def water(n, loc, yn="적합", knd="개장중", ms=1724684400000, year="2024", res1="23", res2="&lt;1"):
    return {"num": 1, "sido_nm": "전북", "gugun_nm": "군산시", "sta_nm": "선유도", "res_num": n, "res_loc": loc,
            "res1": res1, "res2": res2, "res_yn": yn, "res_year": year, "res_date": ms, "res_knd": knd,
            "res_loc_detail": f"w-{loc}", "lat": "35.8195890000", "lon": "126.4122090000"}


def test_a_beach_joins_the_one_place_its_contentid_and_point_name():
    pid, how = B.match(INFO[0], PLACES)
    assert pid == "tourapi-2022531" and how["by"] == "TourAPI contentid + 이름" and how["distance_m"] < B.MATCH_M
    # a name alone, far from the beach's point, is not a match; nor is the island place of the same name
    far = [{**PLACES[0], "tourapi": {}, "geo": {"lat": 35.95, "lng": 126.7}}, PLACES[1]]
    assert B.match(INFO[0], far) == (None, {"reason": "후보 없음"})
    # two places that both fit: not joined, both named
    two = PLACES + [{"id": "x", "name": "선유도 해수욕장", "geo": {"lat": 35.817, "lng": 126.411}}]
    pid, how = B.match(INFO[0], two)
    assert pid is None and "tourapi-2022531" in how["reason"] and "x" in how["reason"]


def test_water_keeps_the_latest_year_and_the_words_as_written():
    rows = [water("1", "A", knd="개장전", ms=1717686000000), water("1", "B", knd="개장전", ms=1717686000000),
            water("2", "A", ms=1724684400000), water("2", "B", yn="부적합", ms=1724684400000),
            water("1", "A", year="2023", ms=1685890800000)]
    w = B.water_block(rows)
    assert w["year"] == "2024" and w["checked"] == "2024-08-27"   # res_date: 밀리초, 한국 시각 자정 → 날짜
    assert [s["round"] for s in w["surveys"]] == ["1", "2"]
    assert w["surveys"][0] == {"round": "1", "date": "2024-06-07", "kinds": ["개장전"], "points": 2,
                               "results": {"적합": 2}}
    # the last survey's points disagree: no one-word result, the counts say it
    assert w["result"] is None and w["surveys"][1]["results"] == {"적합": 1, "부적합": 1}
    assert w["last"][0] == {"res_loc": "A", "res_loc_detail": "w-A", "res1": "23", "res2": "<1", "res_yn": "적합"}
    assert B.water_block([]) is None


def test_the_file_is_keyed_by_place_id_with_its_sources():
    data = B.build(INFO, [water("1", "A"), {**water("1", "A"), "sta_nm": "비응"}], PLACES, "2026-10-31",
                   [2026, 2025, 2024])
    assert set(data) == {"_about", "sources", "places", "unmatched"}
    b = data["places"]["tourapi-2022531"]
    assert b["info"]["link_tel"] == "선유도보건지소(063-466-2348)" and "num" not in b["info"]
    assert b["water"]["result"] == "적합" and "open_period" not in b   # 개장 기간은 두 API에 없다
    assert data["sources"]["info"]["url"] == "https://www.data.go.kr/data/15058519/openapi.do"
    assert data["sources"]["water"]["url"] == "https://www.data.go.kr/data/15056705/openapi.do"
    assert data["sources"]["info"]["rows_gunsan"] == 1   # 부안 행은 쓰지 않는다
    assert data["unmatched"] == [{"source": "water", "sta_nm": "비응", "reason": "해수욕장정보에 같은 정점명 없음"}]


def test_a_provider_refusal_in_the_body_is_an_error():
    with pytest.raises(B.ApiError):
        B.items_of({"getOceansBeachInfo": {"header": {"code": "03", "message": "NODATA_ERROR"}}}, "getOceansBeachInfo")
    rows, total = B.items_of({"getOceansBeachInfo": {"header": {"code": "00"}, "item": INFO[0], "totalCount": 1}},
                             "getOceansBeachInfo")
    assert rows == [INFO[0]] and total == 1
