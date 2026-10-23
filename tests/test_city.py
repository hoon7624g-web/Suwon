"""pipeline.city: site.json -> City (design 1.4, 3.1, 3.5, 3.6). The Daegu config (data/daegu), the sample's
(data/sample, the first city's values) and the metro fixture (tests/fixtures/metro) must all load without problems."""
import json
import re
from pathlib import Path

import pytest

from pipeline import city as citymod
from pipeline import schema
from pipeline.slugs import SLUG_RE
from pipeline.textutil import display_address

ROOT = Path(__file__).resolve().parent.parent
SITES = {"daegu": ROOT / "tests" / "fixtures" / "metro", "suwon": ROOT / "data" / "suwon", "sample": ROOT / "data" / "sample", "metro": ROOT / "tests" / "fixtures" / "metro"}


def site_of(name):
    return json.loads((SITES[name] / "site.json").read_text("utf-8"))


DAEGU = citymod.from_site(site_of("daegu"))
SAMPLE = citymod.from_site(site_of("sample"))
METRO = citymod.from_site(site_of("metro"))


# ---------------------------------------------------------------- loading
@pytest.mark.parametrize("name", sorted(SITES))
def test_configs_load_without_problems(name):
    c = citymod.from_site(site_of(name))
    assert c.problems() == []
    assert c.region and c.region_admin and c.locality


def test_daegu_config_values():
    assert DAEGU.districts == ("중구", "동구", "서구", "남구", "북구", "수성구", "달서구", "달성군", "군위군")
    assert DAEGU.region_mode == "district" and DAEGU.slug_collision == "district" \
        and DAEGU.languages == tuple(site_of("daegu")["languages"]) and DAEGU.languages[0] == "ko"   # the versions switched on (2026-10-16: en, ja)
    assert DAEGU.admin_line == "대구광역시" and SAMPLE.admin_line == "전북특별자치도 군산시"
    assert DAEGU.region_label == "구·군" and DAEGU.none_label == "구·군 미기재" and DAEGU.far is None
    assert SAMPLE.region_mode == "anchors" and SAMPLE.far == {"m": 12000, "label": "먼 섬"} and SAMPLE.anchors == ()
    assert DAEGU.site_url == "https://metro.test" and METRO.districts == DAEGU.districts
    assert DAEGU.view() == {"admin_line": "대구광역시", "region": "대구", "region_label": "구·군", "area_label": "동·읍·면",
                            "region_mode": "district", "search_examples": ["막창", "서문시장", "수성못"], "districts": list(DAEGU.districts),
                            "none_label": "구·군 미기재", "far_label": ""}


def test_required_keys_and_the_per_object_cache():
    base = {"site_url": "", "region": "OO", "region_admin": "OO광역시", "locality": "OO광역시"}
    minimal = citymod.from_site(base)                    # site_url may be '' (the production gate reports it)
    assert minimal.problems() == [] and minimal.region_mode == "anchors" and minimal.slug_collision == "number"
    assert minimal.languages == ("ko",) and minimal.none_label == "권역 미정"
    for key in ("site_url", "region", "region_admin", "locality"):
        with pytest.raises(citymod.CityConfigError):
            citymod.from_site({k: v for k, v in base.items() if k != key})
    with pytest.raises(citymod.CityConfigError):
        citymod.from_site({**base, "region": "  "})
    site = site_of("daegu")
    assert citymod.of(site) is citymod.of(site)
    assert citymod.of(site_of("daegu")) is not citymod.of(site)          # an equal dict is another object


def test_problems_catch_inconsistent_config():
    bad = {**site_of("daegu"), "districts": ["중구", "중구"], "languages": ["en"], "id_prefix": "Daegu_",
           "slug_policy": {"collision": "random"}, "video_topics": [{"title": "먹거리", "slug": "먹거리"}],
           "official_domains": [{"domain": "https://x.kr", "name": ""}], "categories": {"stay": {}},
           "regions": {"mode": "zones", "anchors": [{"key": "원도심", "name": "", "place_id": ""}], "far": {"m": 0}}}
    text = "\n".join(citymod.from_site(bad).problems())
    for part in ("districts 중복", "languages", "id_prefix", "slug_policy", "video_topics slug", "official_domains",
                 "categories 키", "regions.mode", "anchors key", "anchors name", "anchors place_id", "regions.far"):
        assert part in text, part
    empty = {**site_of("daegu"), "districts": []}
    assert "districts가 비어 있음" in "\n".join(citymod.from_site(empty).problems())


# ---------------------------------------------------------------- addresses (design 3.1)
# '○○로' of the design table is a placeholder; any road name stands for it ('샘플로').
ADDRESS_TABLE = [
    ("대구광역시 중구 동성로2길 80 (삼덕동1가)", "대구광역시", "중구", "삼덕동1가", "동성로2길"),
    ("대구광역시 중구 동성로 1 (동성로2가)", "대구광역시", "중구", "동성로2가", "동성로"),
    ("대구광역시 수성구 무학로 42", "대구광역시", "수성구", "", "무학로"),
    ("대구 동구 샘플로 5", "대구광역시", "동구", "", "샘플로"),
    ("대구광역시 군위군 군위읍 군청로 10", "대구광역시", "군위군", "군위읍", "군청로"),
    ("대구광역시 달성군 화원읍 사문진로 1", "대구광역시", "달성군", "화원읍", "사문진로"),
    ("대구광역시 달서구 성서공단로 1 나동 2층", "대구광역시", "달서구", "", "성서공단로"),
    # Q6 decided: the national table shows 군위군 under 대구광역시, so the old form parses the same
    ("경상북도 군위군 군위읍 군청로 10", "대구광역시", "군위군", "군위읍", "군청로"),
]


@pytest.mark.parametrize("raw, admin, district, area, road", ADDRESS_TABLE)
def test_parse_address_design_table(raw, admin, district, area, road):
    a = DAEGU.parse_address(raw)
    assert (a.admin, a.district, a.area, a.road) == (admin, district, area, road)


def test_parse_address_sample_and_edge_cases():
    a = SAMPLE.parse_address("전북특별자치도 군산시 경촌4길 14(경암동)")
    assert (a.admin, a.district, a.area, a.road) == ("전북특별자치도", "", "경암동", "경촌4길")
    a = SAMPLE.parse_address("전라북도 군산시 옥도면 선유도리 279-8")               # renamed, area by position
    assert (a.admin, a.area) == ("전북특별자치도", "옥도면")
    a = SAMPLE.parse_address("전북특별자치도군산시임피면 술산리 1")                  # written without spaces
    assert (a.admin, a.area) == ("전북특별자치도", "임피면")
    a = DAEGU.parse_address("대구시 북구 샘플로 3")
    assert (a.admin, a.district, a.road) == ("대구광역시", "북구", "샘플로")
    a = DAEGU.parse_address("대구광역시 샘플대로 9")                               # no 구·군 in the address
    assert (a.admin, a.district, a.area, a.road) == ("대구광역시", "", "", "샘플대로")
    a = DAEGU.parse_address("부산광역시 중구 중앙대로 1")                           # another city: nothing read
    assert (a.admin, a.district) == ("", "")
    assert DAEGU.parse_address("대구탕 골목 1").admin == ""                       # a homograph is not the city
    a = DAEGU.parse_address("대구광역시 서구 시험길 11 (내당동, 어느 빌딩)")
    assert (a.district, a.area) == ("서구", "내당동")
    assert DAEGU.parse_address(None) == citymod.Address()
    assert DAEGU.admin_words("대구광역시 중구 동성로2길 80 (삼덕동1가)") == {"중구", "삼덕동1가"}


def test_place_line_area_label_and_map_prefix():
    e = {"facts": {"address": "대구광역시 중구 동성로2길 80 (삼덕동1가)"}}
    assert DAEGU.place_line(e) == "대구광역시 중구 삼덕동1가" and DAEGU.area_label(e) == "중구 삼덕동1가"
    assert DAEGU.map_query_prefix(e) == "대구 중구"
    e = {"facts": {"address": "대구광역시 수성구 무학로 42"}}
    assert DAEGU.place_line(e) == "대구광역시 수성구" and DAEGU.area_label(e) == "수성구"
    e = {"facts": {"address": "대구광역시 샘플대로 9"}}
    assert DAEGU.place_line(e) == "대구광역시" and DAEGU.area_label(e) == "" and DAEGU.map_query_prefix(e) == "대구"
    ev = {"address": "대구 동구 샘플로 5"}                                         # an event's own address
    assert DAEGU.area_label(ev) == "동구"
    built = {"_district": "달성군", "_area": "화원읍", "facts": {"address": "엉뚱한 값"}}   # the build's fields win
    assert DAEGU.area_label(built) == "달성군 화원읍" and DAEGU.place_line(built) == "대구광역시 달성군 화원읍"
    g = {"facts": {"address": "전북특별자치도 군산시 경촌4길 14(경암동)"}}
    assert SAMPLE.place_line(g) == "군산시 경암동" and SAMPLE.area_label(g) == "경암동"   # today's kicker
    assert SAMPLE.map_query_prefix(g) == "군산"


def test_metro_fixture_addresses():
    places = {p["id"]: p for p in json.loads((SITES["metro"] / "places.json").read_text("utf-8"))}
    lines = {i: METRO.area_label(p) for i, p in places.items()}
    assert lines["metro-0001"] == "중구 삼덕동1가" and lines["metro-0002"] == "중구 동성로2가"
    assert lines["metro-0003"] == "수성구" and lines["metro-0004"] == "군위군 군위읍"
    assert lines["metro-0005"] == "달성군 가창면" and lines["metro-0006"] == "동구"
    assert lines["metro-0007"] == "달서구" and lines["metro-0008"] == ""
    assert lines["metro-0011"] == "서구 내당동" and lines["metro-0012"] == "군위군 효령면"
    assert display_address(places["metro-0012"]["facts"]["address"]).startswith("대구광역시 군위군 ")
    assert all(re.match(r"^\[샘플\] ", p["name"]) for p in places.values())
    for p in places.values():
        assert schema.check_entity(p) == [], p["id"]
        g = p.get("geo")
        assert not g or (35.5 < g["lat"] < 36.4 and 128.3 < g["lng"] < 128.9), p["id"]


def test_strip_city_prefix_keeps_the_district():
    assert DAEGU.strip_city_prefix("대구광역시 중구 동성로 1") == "중구 동성로 1"
    assert DAEGU.strip_city_prefix("대구 동구 샘플로 5") == "동구 샘플로 5"
    assert DAEGU.strip_city_prefix("대구시 북구 샘플로 3") == "북구 샘플로 3"
    assert DAEGU.strip_city_prefix("경상북도 군위군 군위읍 군청로 10") == "군위군 군위읍 군청로 10"
    assert DAEGU.strip_city_prefix("대구탕 골목 일원") == "대구탕 골목 일원"
    assert DAEGU.strip_city_prefix("대구광역시청 앞") == "대구광역시청 앞"
    assert SAMPLE.strip_city_prefix("전북특별자치도 군산시 구영7길 69 (신창동 )") == "구영7길 69 (신창동 )"
    assert SAMPLE.strip_city_prefix("전라북도 군산시 옥도면 선유도리 279-8") == "옥도면 선유도리 279-8"
    assert SAMPLE.strip_city_prefix("군산시간여행마을 일원") == "군산시간여행마을 일원"


def test_district_slugs_and_region_keys():
    assert DAEGU.district_slug("중구") == "jung-gu" and DAEGU.district_slug("달성군") == "dalseong-gun"
    assert DAEGU.district_slug("군위군") == "gunwi-gun"
    slugs = [DAEGU.district_slug(d) for d in DAEGU.districts]
    assert slugs == ["jung-gu", "dong-gu", "seo-gu", "nam-gu", "buk-gu", "suseong-gu", "dalseo-gu", "dalseong-gun",
                     "gunwi-gun"]
    assert DAEGU.region_key("수성구") == "suseong-gu" and DAEGU.region_key("구·군 미기재") == "none"
    anchored = citymod.from_site({**site_of("sample"), "regions": {
        "mode": "anchors", "anchors": [{"key": "old-town", "name": "원도심", "place_id": "p-1"}],
        "far": {"m": 12000, "label": "먼 섬"}, "none_label": "권역 미정"}})
    assert anchored.problems() == []
    assert [anchored.region_key(n) for n in ("원도심", "먼 섬", "권역 미정")] == ["old-town", "far", "none"]
    assert SLUG_RE.match(anchored.region_key("새 권역"))


# ---------------------------------------------------------------- names and sentences (design 3.6)
def test_homographs_do_not_name_the_city():
    assert DAEGU.names_city("대구 근대골목 투어") and DAEGU.names_city("대구광역시립 전시관")
    assert not DAEGU.names_city("대구탕 골목 식당") and not DAEGU.names_city("동인동 대구뽈찜")
    assert DAEGU.strip_region_prefix("대구 근대골목") == "근대골목"
    assert DAEGU.strip_region_prefix("대구탕집") == "대구탕집"
    assert SAMPLE.strip_region_prefix("군산 동국사") == "동국사"


def test_taut_metro_city():
    name = "[샘플] 전시관"
    rx = DAEGU.taut_rx(name)
    assert rx.match("[샘플] 전시관은 대구광역시 중구 삼덕동1가에 있는 전시관입니다.")
    assert rx.match("[샘플] 전시관은 중구 삼덕동1가에 있는 전시관입니다.")
    assert rx.match("[샘플] 전시관은 대구 수성구에 위치한 전시관입니다.")
    assert not rx.match("[샘플] 전시관은 대구에서 볼 수 있는 근대 건축 전시관입니다.")
    assert not rx.match("[샘플] 전시관은 1층과 2층에 전시실 6개를 둔 전시관입니다.")
    assert not DAEGU.taut_rx("따로국밥").match("따로국밥은 대구에서 오래 먹어 온 국밥으로 새벽에도 문을 여는 집이 있는 음식입니다.")
    # a name holding a homograph: the dish is not the city
    assert not DAEGU.taut_rx("대구탕 식당").match("대구탕 식당은 대구탕을 끓여 내는 집입니다.")
    assert DAEGU.taut_rx("대구탕 식당").match("대구탕 식당은 대구광역시 남구에 있는 식당입니다.")


def test_taut_sample_config():
    """The sample config (a 도 and its 시, no districts): W is the 시·도 and the 시, so the 시 alone or after its 도 is
    the stock sentence, and a sentence that gives a fact before naming the 시 is not."""
    rx = SAMPLE.taut_rx("근대관")
    sentences = {"근대관은 군산시 장미동에 있는 박물관입니다.": True,
                 "근대관은 전북특별자치도 군산시 장미동에 있는 박물관입니다.": True,
                 "근대관은 1층 해양물류역사관과 3층 근대생활관을 둔 군산시 박물관입니다.": False,
                 "근대관은 군산시에 위치한 박물관입니다.": True,
                 "근대관은 군산에서 오래된 건물을 고쳐 연 박물관입니다.": False}
    assert {s: bool(rx.match(s)) for s in sentences} == sentences


def test_locator_sentences():
    loc = DAEGU.locator_rx
    assert loc.match("[샘플] 전시관은 대구광역시 중구에 있는 전시관입니다.")
    assert loc.match("[샘플] 전시관은 중구 삼덕동1가에 있는 전시관입니다.")
    assert loc.match("[샘플] 전시관은 삼덕동에 있는 전시관입니다.")
    assert not loc.match("[샘플] 전시관은 1층과 2층에 전시실 6개를 둔 전시관입니다.")
    assert SAMPLE.locator_rx.match("철길마을은 군산시 경암동에 있는 마을입니다.")
    assert SAMPLE.locator_rx.match("철길마을은 경암동에 있는 마을입니다.")


def test_title_suffix():
    rx = DAEGU.title_suffix_rx
    for title in ("[샘플] 식당(대구)", "[샘플] 식당 (대구광역시)", "[샘플] 식당(대구 중구)", "[샘플] 식당(중구)"):
        assert rx.sub("", title) == "[샘플] 식당", title
    for title in ("[샘플] 식당(대구) 본점", "[샘플] 식당(대구탕)", "[샘플] 식당(서울)"):
        assert rx.sub("", title) == title, title
    assert SAMPLE.title_suffix_rx.sub("", "동국사(군산)") == "동국사"


# ---------------------------------------------------------------- sources, designations, categories
def test_short_provider_and_official_label():
    assert DAEGU.short_provider("한국관광공사 TourAPI") == "한국관광공사"
    assert DAEGU.short_provider("대구광역시 관광과") == "대구광역시"
    assert DAEGU.short_provider("대구시 관광과") == "대구광역시"
    assert DAEGU.short_provider("대구광역시 중구 문화관광과") == "대구광역시 중구 문화관광과"
    assert DAEGU.short_provider("어느 박물관 홈페이지") == "어느 박물관 홈페이지"
    assert SAMPLE.short_provider("군산시 문화관광") == "군산시"
    assert DAEGU.official_label("https://tour.daegu.go.kr/index.do?menu_id=1") == "대구관광"
    assert DAEGU.official_label("https://www.daegu.go.kr/") == "대구광역시"
    assert DAEGU.official_label("https://www.jung.daegu.kr/new/culture/") == "대구 중구"
    assert DAEGU.official_label("https://notdaegu.go.kr/") == "" and DAEGU.official_label("") == ""
    assert SAMPLE.official_label("https://www.gunsan.go.kr/tour") == "군산시 문화관광"


DESIGNATIONS = [
    {"type": t, "label": f"{t} 목록", "year": 2026, "url": "https://x.kr", "checked_at": "2026-10-09",
     "match": {"confidence": "high"}}
    for t in ("ansim", "hyangto", "gunsan_matjip", "goodprice", "mobeom", "baeknyeon", "jjamppong_street", "unknown")]


def test_designations_with_a_city():
    # the sample config: its own lists first in designations.order (national types among them), the year where
    # show_year says it is part of the designation, an unknown type last with its label
    e = {"designations": DESIGNATIONS}
    assert [(d["type"], d["short"]) for d in schema.designations(e, city=SAMPLE)] == [
        ("gunsan_matjip", "군산맛집 2026"), ("baeknyeon", "백년가게"), ("mobeom", "모범음식점"),
        ("hyangto", "향토음식점 2026"), ("jjamppong_street", "짬뽕 특화거리"), ("goodprice", "착한가격업소"),
        ("ansim", "안심식당"), ("unknown", "unknown 목록")]
    # Daegu: the national four in order with its own lists between them (site.json designations.order), every other
    # type last, its label without brackets
    got = schema.designations(e, city=DAEGU)
    assert [d["type"] for d in got][:4] == ["baeknyeon", "mobeom", "goodprice", "ansim"]
    assert [DAEGU.designation_rank(t) for t in ("baeknyeon", "mobeom", "good_stay", "goodprice", "women_safe_stay",
                                                "ansim", "low_sodium")] == list(range(7))
    assert DAEGU.designation_short_label("good_stay") == "우수숙박시설" and DAEGU.designation_rank("hyangto") == 7
    assert {d["type"] for d in got[4:]} == {"hyangto", "gunsan_matjip", "jjamppong_street", "unknown"}
    assert schema.designation_short({"type": "gunsan_matjip", "label": "OO맛집(2026, OO시 지정)", "year": 2026},
                                    city=DAEGU) == "OO맛집"
    assert DAEGU.designation_rank("baeknyeon") == 0 and DAEGU.designation_short_label("ansim") == "안심식당"
    assert SAMPLE.designation_show_year("hyangto") and not DAEGU.designation_show_year("hyangto")


def test_categories_with_a_city():
    st = lambda city, kind, cat, name="이름": schema.schema_type({"kind": kind, "category": cat, "name": name}, city=city)
    cuisine = lambda city, cat: schema.serves_cuisine({"kind": "food", "category": cat}, city=city)
    # the sample config's source words (categories.stay_schema, cuisine, heritage_buildings) over the national tables
    stays = ("관광호텔", "일반호텔", "여관/모텔", "펜션", "", "한식")
    assert [st(SAMPLE, "stay", c) for c in stays] == ["Hotel", "Hotel", "Motel", "LodgingBusiness", "LodgingBusiness",
                                                      "LodgingBusiness"]
    assert [cuisine(SAMPLE, c) for c in ("한식", "짬뽕 특화거리 ( 중식)", "음식점", "")] == ["한식", "중식", "", ""]
    assert st(SAMPLE, "attraction", "국가지정 문화유산 - 사적", "OO 고택") == ["LandmarksOrHistoricalBuildings",
                                                                       "TouristAttraction"]
    assert st(SAMPLE, "attraction", "국가지정 문화유산 - 사적", "불상 좌상") == "TouristAttraction"   # movable heritage
    assert st(SAMPLE, "attraction", "국가무형 문화유산", "OO 고택") == "TouristAttraction"
    # engine rules every city shares: the kind, the name's ending, the national category words
    for city in (SAMPLE, DAEGU):
        assert [st(city, "food", c) for c in ("관광호텔", "한식", "")] == ["Restaurant"] * 3
        assert st(city, "attraction", "국가지정 문화유산 - 사적", "한빛 박물관") == ["Museum", "TouristAttraction"]
        assert st(city, "attraction", "박물관/전시관", "불상 좌상") == ["Museum", "TouristAttraction"]
        assert st(city, "attraction", "산", "불상 좌상") == ["Mountain", "TouristAttraction"]
        assert st(city, "attraction", "관광명소 > 공원", "불상 좌상") == ["Park", "TouristAttraction"]
        assert st(city, "attraction", "한식", "작은 공원") == ["Park", "TouristAttraction"]
        assert st(city, "attraction", "한식", "불상 좌상") == "TouristAttraction"
        assert st(city, "stay", "박물관/전시관", "한빛 박물관") == "LodgingBusiness"
    assert schema.schema_type({"kind": "stay", "category": "관광호텔"}, city=DAEGU) == "Hotel"
    assert schema.schema_type({"kind": "stay", "category": "여관/모텔"}, city=DAEGU) == "LodgingBusiness"
    assert schema.serves_cuisine({"kind": "food", "category": "짬뽕 특화거리 ( 중식)"}, city=DAEGU) == ""
    assert schema.serves_cuisine({"kind": "food", "category": "한식"}, city=DAEGU) == "한식"
    assert schema.schema_type({"kind": "attraction", "category": "국가지정 문화유산 - 사적", "name": "OO 고택"},
                              city=DAEGU) == "TouristAttraction"
    assert SAMPLE.category("stay_type", "여관/모텔") == "모텔·여관" and DAEGU.category("stay_type", "여관/모텔") is None
    assert DAEGU.category("stay_type", "숙박", {"숙박": "숙박업소"}) == "숙박업소"


# ---------------------------------------------------------------- no city literals in the engine modules
def test_engine_modules_name_no_city():
    for name in ("city.py", "slugs.py", "romanize.py"):
        text = (ROOT / "pipeline" / name).read_text("utf-8")
        assert not re.search(r"군산|gunsan|대구|daegu", text, re.I), name
