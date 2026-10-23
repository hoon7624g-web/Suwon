"""tools/kakao_places.py — the matcher accepts a Kakao place only when it is clearly the same place. City words come
from site.json (the metro fixture: 대구-shaped config with 9 구·군; names and roads here are made up, only the
administrative names are real). Kakao writes the short 시·도 name ('대구 중구 …'), our data the full one."""
import json
from pathlib import Path

import pytest

from pipeline import city as city_mod
from tools import kakao_places as K

ROOT = Path(__file__).resolve().parent.parent
SITE = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))
CITY = city_mod.from_site(SITE)
# 35.8700, 128.6000 is our point; 0.0009° of latitude is about 100 m
LAT, LNG = 35.8700, 128.6000


def place(name, kind="food", address="대구광역시 중구 샘플로 177 (샘플동1가)", geo=True, **extra):
    p = {"id": "p1", "name": name, "kind": kind, "category": extra.pop("category", "음식점"), "status": "published",
         "facts": {"address": address}}
    if geo:
        p["geo"] = {"lat": LAT, "lng": LNG, "source": "TourAPI"}
    p.update(extra)
    return p


def doc(name, dlat=0.0, road="대구 중구 샘플로 177", jibun="대구 중구 샘플동1가 12-3",
        id="100", group="FD6", category="음식점 > 제과,베이커리"):
    return {"id": id, "place_name": name, "x": str(LNG), "y": str(LAT + dlat), "road_address_name": road,
            "address_name": jibun, "category_group_code": group, "category_name": category,
            "category_group_name": {"FD6": "음식점", "CE7": "카페", "AD5": "숙박"}.get(group, "")}


def decide(p, docs, city=CITY):
    return K.decide(p, docs, city)


def test_accepts_exact_name_nearby_with_the_same_building_number():
    r = decide(place("샘플당"), [doc("샘플당", 0.0002)])
    assert r["status"] == "accepted" and r["doc"]["id"] == "100"
    assert r["judge"]["name"]["cls"] == "exact" and round(r["judge"]["dist"]) == 22
    assert "도로명 건물번호 일치(샘플로 177)" in K.basis_text(r["judge"])


def test_accepts_branch_or_region_suffix_only_with_address_agreement():
    # '샘플당 본점' (본점 is safe), '소담촌 대구점' (a branch: the building number must agree)
    assert decide(place("샘플당"), [doc("샘플당 본점")])["status"] == "accepted"
    assert decide(place("소담촌"), [doc("소담촌 대구점")])["status"] == "accepted"
    far_street = doc("소담촌 대구점", road="대구 중구 시험4길 3")
    r = decide(place("소담촌"), [far_street])
    assert r["status"] == "none" and r["reason"].startswith("건물번호 불일치")
    # a branch whose road address we cannot compare is not taken on the name alone
    r = decide(place("소담촌"), [doc("소담촌 대구점", road="")])
    assert r["status"] == "none" and r["reason"].startswith("이름에 업종·지점어")


def test_rejects_a_chain_branch_with_the_same_name_far_away():
    r = decide(place("돔베초밥"), [doc("돔베초밥", 0.0045, road="대구 중구 시험남로 2")])  # ~500 m
    assert r["status"] == "none" and r["reason"].startswith("거리 초과")
    # another numbered branch next door is a different shop
    r = decide(place("돔베초밥"), [doc("돔베초밥 2호점", 0.0001)])
    assert r["status"] == "none" and r["reason"].startswith("이름 일부만 같음")


def test_rejects_a_name_contained_but_different_thing():
    for other in ("샘플당 주차장", "샘플사 대웅전", "샘플해수욕장", "샘플마을 관광안내소", "샘플당 전기차충전소"):
        r = decide(place(other.split()[0] if " " in other else "샘플", kind="attraction"), [doc(other)])
        assert r["status"] == "none", other
        assert r["reason"].startswith("이름 일부만 같음"), (other, r["reason"])
    # unrelated names are never matched however close
    assert decide(place("신가네칼국수"), [doc("신가네해물칼국수")])["reason"] == "이름 불일치"


def test_rejects_building_number_mismatch():
    r = decide(place("스위트인디아", address="대구광역시 중구 시험거리1길 14-1 (샘플동) 1층"),
               [doc("스위트인디아", road="대구 중구 시험거리1길 14")])
    assert r["status"] == "none" and r["reason"] == "건물번호 불일치(시험거리1길 14-1 ≠ 시험거리1길 14)"


def test_an_exact_name_and_the_same_phone_stand_in_for_the_building_number():
    # ours 시험길 27, Kakao 시험길 29, both 053-452-4044 — no coordinates, same road
    p = place("샘플반점", address="대구광역시 중구 시험길 27(샘플동)", geo=False)
    p["facts"]["infocenter"] = "053-452-4044"
    same = {**doc("샘플반점", road="대구 중구 시험길 29"), "phone": "053-452-4044"}
    r = decide(p, [same])
    assert r["status"] == "accepted"
    assert "건물번호 다름(시험길 27 / 시험길 29) · 전화 일치(053-452-4044)" in K.basis_text(r["judge"])
    # another number, or no number on one side: still rejected
    for phone in ("053-452-4045", ""):
        r = decide(p, [{**same, "phone": phone}])
        assert r["status"] == "none" and r["reason"].startswith("건물번호 불일치"), phone
    # without our coordinates the road name must agree; with them, the distance check is what places it
    other_road = {**same, "road_address_name": "대구 중구 다른길 29"}
    assert decide(p, [other_road])["reason"].startswith("건물번호 불일치")
    near = place("사골뚝배기", address="대구광역시 중구 다른길 29 (샘플동)")
    near["facts"]["infocenter"] = "053-445-1107"
    corner = {**doc("사골뚝배기", 0.00005, road="대구 중구 시험거리1길 7"), "phone": "053-445-1107"}
    assert decide(near, [corner])["status"] == "accepted"
    assert decide(near, [{**corner, "y": str(LAT + 0.0045)}])["reason"].startswith("거리 초과")
    # a name that is not exact does not get the exception (a branch needs the building number)
    branch = {**doc("샘플반점 역전점", road="대구 중구 시험길 29"), "phone": "053-452-4044"}
    assert decide(p, [branch])["status"] == "none"


def test_phone_numbers():
    assert K.phone_numbers("053-452-4044") == {"0534524044"}
    assert K.phone_numbers("0507-1315-5312") == {"050713155312"}
    assert K.phone_numbers("구청 관광과 053-454-3333\n010-1234-5678, 452-1234") == {"0534543333", "01012345678"}
    assert K.phone_numbers("") == set() and K.phone_numbers(None) == set()


def test_large_places_get_400_m_and_small_ones_150_m():
    hill = place("샘플산", kind="attraction", category="산", address="대구광역시 달성군 샘플면 샘플리")
    assert decide(hill, [doc("샘플산", 0.0030, road="", jibun="대구 달성군 샘플면 샘플리 산 1",
                             category="여행 > 관광,명소 > 산")])["status"] == "accepted"
    assert decide(hill, [doc("샘플산", 0.0040, road="", jibun="대구 달성군 샘플면 샘플리 산 1",
                             category="여행 > 관광,명소 > 산")])["reason"].startswith("거리 초과(445m > 400m)")
    museum = place("샘플대학교 박물관", kind="attraction", category="문화시설", address="대구광역시 북구 대학로 558")
    r = decide(museum, [doc("샘플대학교 박물관", 0.0023, road="대구 북구 대학로 558")])
    assert r["status"] == "none" and r["reason"].startswith("거리 초과(256m > 150m)")


def test_several_passing_candidates_need_one_clearly_better():
    near_exact, farther_branch = doc("샘플당", 0.0001, id="1"), doc("샘플당 본점", 0.0005, id="2")
    r = decide(place("샘플당"), [farther_branch, near_exact])
    assert r["status"] == "accepted" and r["doc"]["id"] == "1"
    # the exact one is not the nearest: hold it
    r = decide(place("샘플당"), [doc("샘플당", 0.0005, id="1"), doc("샘플당 본점", 0.0001, id="2")])
    assert r["status"] == "ambiguous"
    # two exact names: hold it
    r = decide(place("샘플당"), [doc("샘플당", 0.0001, id="1"), doc("샘플당", 0.0002, id="2")])
    assert r["status"] == "ambiguous"


def test_kind_conflict_and_one_letter_names():
    gh = place("달", kind="stay", address="대구광역시 중구 시험3길 21-2 (샘플동 12-10)")
    cafe = doc("달", road="대구 중구 시험3길 21-2", id="cafe", group="CE7", category="음식점 > 카페")
    stay = doc("게스트하우스 달", road="대구 중구 시험3길 21-2", id="gh", group="AD5",
               category="여행 > 숙박 > 게스트하우스")
    r = decide(gh, [cafe, stay])
    assert r["status"] == "accepted" and r["doc"]["id"] == "gh"
    assert decide(gh, [cafe])["reason"].startswith("유형 불일치")
    # a one-letter name never matches a longer name by containment alone
    assert decide(place("틈"), [doc("틈새라면")])["reason"] == "이름 불일치"


def test_word_order_and_region_differences_need_the_address():
    hotel = place("파라다이스 호텔", kind="stay", address="대구광역시 중구 시험1길 21 (샘플동)")
    same = doc("호텔파라다이스", road="대구 중구 시험1길 21", group="AD5", category="여행 > 숙박 > 호텔")
    assert decide(hotel, [same])["status"] == "accepted"
    elsewhere = doc("호텔파라다이스", road="대구 중구 시험2길 9", group="AD5", category="여행 > 숙박 > 호텔")
    assert decide(hotel, [elsewhere])["status"] == "none"
    # the city's name in front, short or full ('대구' / '대구광역시'), is not a difference
    park = place("대구어린이교통공원", kind="attraction", category="관광지", address="대구광역시 북구 시험산로 135 (샘플동)")
    r = decide(park, [doc("대구광역시 어린이교통공원", road="대구 북구 시험산로 135", category="여행 > 공원")])
    assert r["status"] == "accepted" and r["judge"]["name"]["cls"] == "safe"
    # a 구·군 is a region word too: '수성구 샘플도서관' is our '샘플도서관' in the same building
    lib = place("샘플도서관", kind="attraction", category="문화시설", address="대구광역시 수성구 시험로 12")
    r = decide(lib, [doc("수성구 샘플도서관", road="대구 수성구 시험로 12", category="문화,예술 > 도서관")])
    assert r["status"] == "accepted" and r["judge"]["name"] == {"cls": "safe", "extra": "수성구", "how": "name"}


def test_site_json_region_words_and_homographs():
    # site.json kakao_places.region_words: a word of the region that is not an administrative name
    words = city_mod.from_site({**SITE, "kakao_places": {"region_words": ["영남"]}})
    museum = place("영남관세박물관", kind="attraction", category="문화시설", address="대구광역시 중구 시험로 244-7(샘플동)")
    hit = doc("관세박물관", 0.0004, road="대구 중구 시험로 244-7", category="문화,예술 > 문화시설 > 박물관")
    r = decide(museum, [hit], words)
    assert r["status"] == "accepted" and r["judge"]["name"] == {"cls": "safe", "extra": "영남", "how": "name"}
    assert decide(museum, [hit])["status"] == "none"                        # not a word of the plain fixture
    # a name that starts with a homograph of the city ('대구뽈찜': the fish) does not lose '대구' as a region word
    fish = place("대구뽈찜")
    r = decide(fish, [doc("뽈찜")])
    assert r["status"] == "none" and r["reason"].startswith("이름 일부만 같음")
    assert K.strip_region("대구뽈찜", CITY) == "대구뽈찜" and K.strip_region("대구광역시샘플관", CITY) == "샘플관"


def test_places_without_coordinates_need_name_city_and_building_number():
    p = place("호텔나운", kind="stay", address="대구광역시 중구 시험충로 84 (샘플동)", geo=False)
    ok = doc("호텔나운", road="대구 중구 시험충로 84", group="AD5")
    assert decide(p, [ok])["status"] == "accepted"
    assert decide(p, [doc("호텔나운", road="대구 중구 시험충로 86", group="AD5")])["status"] == "none"
    other_city = doc("호텔나운", road="경북 경산시 시험충로 84", jibun="경북 경산시 샘플동 1", group="AD5")
    assert decide(p, [other_city])["reason"] == "지역 밖(대구광역시)"
    # a road named after the city in another city is still outside
    named = doc("호텔나운", road="경북 경산시 대구대로 84", jibun="경북 경산시 샘플동 2", group="AD5")
    assert decide(p, [named])["reason"] == "지역 밖(대구광역시)"
    # the same road and number in another 구·군 is another address
    other_district = doc("호텔나운", road="대구 수성구 시험충로 84", jibun="대구 수성구 샘플동 3", group="AD5")
    assert decide(p, [other_district])["reason"] == "구·군 불일치(중구 ≠ 수성구)"
    no_road = place("샘플봉", kind="attraction", category="산", address="대구광역시 달성군 샘플면 일원", geo=False)
    assert decide(no_road, [doc("샘플봉", road="", jibun="대구 달성군 샘플면 샘플리 산 1",
                                category="여행 > 산")])["reason"].startswith("좌표 없음")


def test_queries_put_the_city_and_district_first_without_coordinates():
    p = place("샘플 식당 (역전점)", address="대구광역시 수성구 시험로 1", geo=False)
    assert K.queries(p, CITY) == ["대구 수성구 샘플 식당", "샘플 식당", "대구 수성구 샘플식당",
                                  "대구 수성구 샘플 식당 역전점"]
    near = place("대구 샘플관")                       # the name already says the city: no prefix
    assert K.queries(near, CITY) == ["대구 샘플관", "대구샘플관"]
    assert K.queries(place("샘플관"), CITY) == ["샘플관", "대구 중구 샘플관"]


def test_address_parsers():
    assert K.parse_road("대구광역시 달성군 샘플면 축산 1길 8") == ("축산1길", "8")
    assert K.parse_road("대구광역시 중구 시험로 43, 1,2층(샘플동)") == ("시험로", "43")
    assert K.parse_road("대구광역시 중구 번영로 12번길 3") == ("번영로12번길", "3")
    assert K.parse_road("대구광역시 중구 샘플로1가 12-3") is None
    assert K.parse_jibun("대구광역시 중구 샘플로1가 12-3") == ("샘플로1가", "12-3")
    assert K.parse_jibun("대구광역시 달성군 샘플면 샘플리 산 66") == ("샘플리", "산66")
    assert K.parse_jibun("대구광역시 중구 샘플동 34-5번지 일원(약 1만㎡)") == ("샘플동", "34-5")


def test_collisions_hold_the_alias_match():
    a = {"status": "accepted", "doc": {"id": "9"}, "judge": {"name": {"cls": "exact", "how": "name"}}}
    b = {"status": "accepted", "doc": {"id": "9"}, "judge": {"name": {"cls": "exact", "how": "alternate"}}}
    results = {"a": a, "b": b}
    K.resolve_collisions(results)
    assert results["a"]["status"] == "accepted" and results["b"]["status"] == "ambiguous"


def test_apply_writes_id_and_source_and_removes_its_own_stale_id():
    p1, p2, p3 = place("샘플당"), place("돔베초밥"), place("수동")
    p2["id"], p3["id"] = "p2", "p3"
    p2["map_ids"] = {"kakao_place_id": "old"}
    p2["map_id_sources"] = {"kakao_place_id": {"provider": K.PROVIDER, "checked_at": "2026-10-01"}}
    p3["map_ids"] = {"kakao_place_id": "manual"}
    d = {**doc("샘플당 본점", 0.0001), "_fetched": "2026-10-14", "_query": "샘플당"}
    results = {"p1": decide(p1, [d]), "p2": {"status": "none"}, "p3": {"status": "none"}}
    changes = K.apply([p1, p2, p3], results)
    assert p1["map_ids"]["kakao_place_id"] == "100"
    src = p1["map_id_sources"]["kakao_place_id"]
    assert src["provider"] == "Kakao Local API" and src["checked_at"] == "2026-10-14"
    assert src["matched_name"] == "샘플당 본점" and src["distance_m"] == 11 and src["url"] == "https://place.map.kakao.com/100"
    assert "kakao_place_id" not in p2["map_ids"] and "map_id_sources" not in p2
    assert p3["map_ids"]["kakao_place_id"] == "manual"
    assert changes == {"added": 1, "removed": 1, "kept_manual": 1}


def test_run_reads_the_city_from_the_data_folder(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "site.json").write_text(json.dumps(SITE, ensure_ascii=False), "utf-8")
    (data / "places.json").write_text(json.dumps([place("샘플당")], ensure_ascii=False), "utf-8")
    cache = tmp_path / "cache"
    client = K.KakaoClient("", cache)
    params = {"query": "샘플당", "sort": "accuracy", "size": 15, "page": 1, "x": f"{LNG:.7f}", "y": f"{LAT:.7f}",
              "radius": 1000}
    cache.mkdir()
    client._path(params).write_text(json.dumps({"params": params, "fetched_at": "2026-10-14",
                                                "response": {"documents": [doc("샘플당", 0.0001)]}},
                                               ensure_ascii=False), "utf-8")
    assert K.main(["--data", str(data), "--offline", "--cache", str(cache), "--apply",
                   "--report", str(tmp_path / "r.json")]) == 0
    got = json.loads((data / "places.json").read_text("utf-8"))[0]
    assert got["map_ids"]["kakao_place_id"] == "100"
    with pytest.raises(SystemExit):
        K.main(["--offline"])                                                 # --data is required
    capsys.readouterr()


def test_client_masks_the_key_and_uses_the_cache(tmp_path, monkeypatch):
    key = "abcdef1234567890"
    client = K.KakaoClient(key, tmp_path, max_calls=1)

    class Boom(K.urllib.error.HTTPError):
        def __init__(self):
            super().__init__("u", 401, "Unauthorized", {}, None)

        def read(self):
            return f'{{"errorType":"AccessDeniedError","message":"wrong appkey {key}"}}'.encode()

    def fail(req, timeout=0):
        assert req.get_header("Authorization") == f"KakaoAK {key}"
        raise Boom()
    monkeypatch.setattr(K.urllib.request, "urlopen", fail)
    with pytest.raises(K.KakaoError) as e:
        client.search("샘플당", 128.6, 35.87)
    assert key not in str(e.value) and "«KEY»" in str(e.value) and "AccessDeniedError" in str(e.value)
    # a cached answer costs no call, and the per-run cap stops the next live one
    params = {"query": "샘플당", "sort": "accuracy", "size": 15, "page": 1, "x": "128.6000000", "y": "35.8700000",
              "radius": 1000}
    client._path(params).write_text(json.dumps({"params": params, "fetched_at": "2026-10-14",
                                                "response": {"documents": [doc("샘플당")]}}), "utf-8")
    docs, fetched = client.search("샘플당", 128.6, 35.87)
    assert docs[0]["place_name"] == "샘플당" and fetched == "2026-10-14" and client.cache_hits == 1
    with pytest.raises(K.KakaoStop):
        client.search("다른 곳", 128.6, 35.87)
    assert all(key not in f.read_text("utf-8") for f in tmp_path.iterdir())
