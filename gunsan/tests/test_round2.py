"""Round 2 structure: maps only with coordinates, filterable lists, duplicates, withheld conflicts, content checks."""
import json
import shutil
from pathlib import Path

from pipeline.build import build, category_group, web_url
from pipeline.textutil import area_from_address, josa, road_from_address
from tools import round2_content, round2_data

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


def sample_copy(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    return data, json.loads((data / "places.json").read_text("utf-8"))


def save(data, places):
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")


def test_map_and_kakao_sdk_load_only_where_coordinates_exist(tmp_path):
    # map provider: Kakao Maps (owner decision 2026-10-14) — the box names the SDK (key from site.json), the page
    # credits '지도: 카카오맵'; a page without coordinates has no box and never names the SDK
    data, places = sample_copy(tmp_path)
    places[0]["geo"] = {"lat": 35.98, "lng": 126.72, "source": "TourAPI"}
    save(data, places)
    out = tmp_path / "out"
    build(data, out, "preview")
    with_geo = (out / "places" / places[0]["slug"] / "index.html").read_text("utf-8")
    without = (out / "places" / places[1]["slug"] / "index.html").read_text("utf-8")
    assert 'class="map"' in with_geo and "data-points=" in with_geo and "지도: 카카오맵" in with_geo
    assert 'data-kakao-sdk="https://dapi.kakao.com/v2/maps/sdk.js?appkey=' in with_geo
    assert 'class="map"' not in without and "dapi.kakao.com" not in without
    for html in (with_geo, without):
        assert "leaflet" not in html.lower() and "openstreetmap" not in html.lower()
    assert not (out / "assets" / "vendor" / "leaflet").exists()
    assert (out / "assets" / "vendor" / "pretendard" / "LICENSE.txt").exists()


def test_lists_filter_without_js_and_skip_duplicates(tmp_path):
    data, places = sample_copy(tmp_path)
    dup = dict(places[0], id="dup-1", slug="dup-1", duplicate_of=places[0]["id"])
    save(data, places + [dup])
    out = tmp_path / "out"
    build(data, out, "preview")
    listing = (out / "places" / "index.html").read_text("utf-8")
    assert "data-filters hidden" in listing          # filters appear only when site.js runs
    # a mouse cannot swipe the type chips' sideways row (its scrollbar is hidden): with a fine pointer they wrap, every
    # one in view (operator 2026-10-18 on /food/); touch keeps the one row
    from pipeline.build import site_css
    css = site_css()
    rule = css[css.index("@media (hover: hover) and (pointer: fine)"):]
    rule = rule[:rule.index("}}") + 2]
    assert ".f-row{flex-wrap:wrap;overflow-x:visible" in rule.replace(" ", "") and "mask-image:none" in rule.replace(" ", "")
    assert 'data-group="' in listing and 'data-area="' in listing
    assert (out / "stays" / "index.html").exists() and (out / "food" / "index.html").exists()
    assert not (out / "places" / "dup-1").exists()
    assert "/places/dup-1/" not in listing


def test_conflicting_source_values_are_withheld_and_explained(tmp_path):
    data, places = sample_copy(tmp_path)
    place = places[0]
    place["facts"].pop("usetime", None)
    place["fact_conflicts"] = {"usetime": "상세 정보표 '09:00~21:00'와 본문의 시간(09:00·18:00)이 서로 다름"}
    save(data, places)
    out = tmp_path / "out"
    build(data, out, "preview")
    html = (out / "places" / place["slug"] / "index.html").read_text("utf-8")
    assert "같은 출처 안에서 값이 달라 싣지 않았습니다" in html
    assert html.count("확인 필요:") == 1


def test_time_conflict_and_area_helpers():
    assert round2_data.time_conflict("09:00~21:00", "이용시간 09:00 ~ 18:00")
    assert not round2_data.time_conflict("09:00~18:00", "이용시간 09:00 ~ 18:00 매주 월요일 휴관")
    assert area_from_address("전북특별자치도 군산시 경촌4길 14(경암동)") == "경암동"
    assert area_from_address("전북특별자치도 군산시 해망로 240") == ""
    assert road_from_address("전북특별자치도 군산시 내항2길 32") == "내항2길"
    assert road_from_address("군산시 월명로 2길 3") == "월명로2길"
    assert josa("코스여행", "으로/로") == "코스여행으로" and josa("당일 코스", "으로/로") == "당일 코스로"


def test_course_stop_links_keep_compound_stops_unlinked():
    places = [{"id": "p1", "slug": "대장도", "name": "대장도", "kind": "attraction"},
              {"id": "p2", "slug": "선유도", "name": "선유도", "kind": "attraction"}]
    courses = [{"stops": [{"name": "대장도대장봉등반"}, {"name": "선유도,대장도일원"}, {"name": "선유도"}]}]
    counts = round2_data.link_course_stops(courses, places)
    stops = courses[0]["stops"]
    assert stops[0]["place_slug"] == "대장도" and stops[0]["link_basis"] == "part_of"
    assert "place_slug" not in stops[1]
    assert stops[2]["link_basis"] == "exact" and counts["linked"] == 2


def test_content_checker_flags_copying_commentary_and_unsourced_facts():
    source = "경암동 철길마을은 1944년 페이퍼 코리아 공장과 군산역을 연결하는 철로 주변의 마을을 총괄하여 붙인 이름이다."
    inp = {"id": "x", "name": "경암동 철길마을", "tier": "basic", "area": "경암동", "facts": {},
           "evidence": [{"url": "https://example.org/1", "text": source, "fields": {}}]}
    copied = {"id": "x", "summary": "페이퍼 코리아 공장과 군산역을 연결하는 철로 주변의 마을입니다."}
    assert any("원문 복사" in i for i in round2_content.check_place_item(copied, inp))
    commentary = {"id": "x", "summary": "원문은 이곳을 최고의 마을로 소개합니다."}
    found = round2_content.check_place_item(commentary, inp)
    assert any("해설체" in i for i in found) and any("수식어" in i for i in found)
    unsourced = {"id": "x", "summary": "경암동 철길마을은 경암동에 있는 마을입니다.",
                 "facts_add": [{"key": "usetime", "value": "09:00~18:00", "evidence_url": "https://example.org/1"}]}
    assert any("그대로 없음" in i for i in round2_content.check_place_item(unsourced, inp))
    ok = {"id": "x", "summary": "경암동 철길마을은 경암동에 있는 마을로, 1944년에 놓인 철로를 따라 집들이 늘어서 있습니다."}
    assert round2_content.check_place_item(ok, inp) == []


def test_mountain_keyword_does_not_match_gunsan_or_industry():
    group = lambda category, name: category_group({"kind": "attraction", "category": category, "name": name})
    assert group("산업/회의 시설", "비응도 풍력발전단지") == "테마 여행지"
    assert group("나이트투어", "군산밤 푸드존") == "테마 여행지"
    assert group("감성여행", "군산내항") == "테마 여행지"
    assert group("산", "오성산") == "자연·야외"
    assert group("나이트투어", "오성산 정상") == "자연·야외"


def test_homepage_without_scheme_links_to_https():
    assert web_url("www.suair.kr") == "https://www.suair.kr"
    assert web_url("http://example.org/a") == "http://example.org/a"
    assert web_url("전화문의") == ""
