"""Unit tests: text helpers, map links, TourAPI parsing, importer."""
import csv
import json

import pytest

from pipeline import importer
from pipeline.maplinks import build_links, precision_summary
from pipeline.slugs import slugify
from pipeline.textutil import (area_from_address, display_address, extract_phone, extract_phones, extract_url,
                               first_sentence, normalize_name, phone_domestic, phone_e164, phone_intl, phone_intl_shown,
                               sha256_text, strip_html)
from pipeline.tourapi import TourAPIError, parse_items


def test_strip_html_keeps_line_breaks():
    assert strip_html("09:00~18:00<br />매주 월요일 휴무&nbsp;") == "09:00~18:00\n매주 월요일 휴무"


def test_extract_url_from_anchor_and_text():
    assert extract_url('<a href="https://www.gunsan.go.kr" target="_blank">군산시</a>') == "https://www.gunsan.go.kr"
    assert extract_url("홈페이지 http://example.org/x 참고") == "http://example.org/x"
    assert extract_url("") == ""


def test_phone_and_names():
    assert extract_phone("문의 063-454-1234 (평일)") == "063-454-1234"
    assert normalize_name("신흥동 일본식 가옥(히로쓰 가옥)") == "신흥동일본식가옥"
    # URL slugs are ASCII (pipeline.slugs): the place's 동 hyphenated when the caller names it (from the address)
    assert slugify("경암동 철길마을", admin_words={"경암동"}) == "gyeongam-dong-cheolgilmaeul"
    assert slugify("경암동 철길마을") == "gyeongamdong-cheolgilmaeul"
    assert len(sha256_text("가")) == 64


def test_phone_extraction_never_truncates_or_merges():
    # P0-1: the old pattern turned 0507-1302-6070 into 07-1302-6070 and read two glued numbers as one
    assert extract_phone("0507-1302-6070") == "0507-1302-6070"
    assert extract_phone("1577-4050") == "1577-4050"
    assert extract_phone("063-443-1981063-443-4819") == ""
    assert extract_phone("군산시청 063-454-3337") == "063-454-3337"
    assert extract_phone("010-9267-4166") == "010-9267-4166"
    assert extract_phones("063-443-1981, 063-443-4819") == ["063-443-1981", "063-443-4819"]
    # P2-6: +82 form for markup, and back to the visible domestic form; a nationwide number has no +82 form (QA
    # 2026-10-15 SRC-05a: structured data keeps 1577-4050 as written)
    assert phone_intl("063-454-7870") == "+82-63-454-7870" and phone_intl("1577-4050") == "1577-4050"
    for n in ("063-454-7870", "0507-1302-6070", "010-9267-4166", "1577-4050"):
        assert phone_domestic(phone_intl(n)) == n


def test_phone_international_forms_only_for_numbers_that_answer_from_abroad():
    # QA 2026-10-15 SRC-05a: the +82 form a caller abroad dials; never for a domestic-only number
    assert phone_e164("063-454-7870") == "+82-63-454-7870"
    assert phone_e164("02-530-6311") == "+82-2-530-6311"
    assert phone_e164("010-4891-5402") == "+82-10-4891-5402"
    assert phone_e164("070-4064-1517") == "+82-70-4064-1517"
    assert phone_e164("0507-1394-3390") == "+82-507-1394-3390"
    for n in ("1577-4050", "1644-8774", "080-123-4567", "060-123-4567"):
        assert phone_e164(n) == "" and phone_intl(n) == n, n
    # the visible '+82 …' form: area codes, mobiles, 070 — not 0507 (reach from abroad unverified), 15xx, 080, 060
    assert phone_intl_shown("02-530-6311") == "+82 2-530-6311"
    assert phone_intl_shown("063-454-7870") == "+82 63-454-7870"
    assert phone_intl_shown("010-4891-5402") == "+82 10-4891-5402"
    assert phone_intl_shown("070-4064-1517") == "+82 70-4064-1517"
    for n in ("0507-1394-3390", "1577-4050", "080-123-4567", "060-123-4567", "050-123-4567"):
        assert phone_intl_shown(n) == "", n


def test_display_address_rewrites_only_the_province_prefix():
    assert display_address("전라북도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"
    assert display_address("전북 군산시 평화길 123-5 (장미동)") == "전북특별자치도 군산시 평화길 123-5 (장미동)"
    assert display_address("전북 특별자치도 군산시 동국사길 16 (금광동)") == "전북특별자치도 군산시 동국사길 16 (금광동)"
    assert display_address("전북특별자치도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"
    assert display_address("군산시 미장남로 111-5(미장동)") == "군산시 미장남로 111-5(미장동)"   # nothing derived
    assert display_address("  ") == "" and display_address(None) == ""
    # the national table also holds 군위군 (경상북도 -> 대구광역시, 2023-07-01); a city's own short form is shown as written
    assert display_address("경상북도 군위군 군위읍 군청로 10") == "대구광역시 군위군 군위읍 군청로 10"
    assert display_address("경북 군위군 효령면 예시길 3") == "대구광역시 군위군 효령면 예시길 3"
    assert display_address("대구 동구 샘플로 5") == "대구 동구 샘플로 5"
    assert display_address("대구광역시 중구 동성로2길 80 (삼덕동1가)") == "대구광역시 중구 동성로2길 80 (삼덕동1가)"
    assert display_address("경상북도 경주시 태종로 1") == "경상북도 경주시 태종로 1"


def test_area_from_address_keeps_a_beopjeong_dong_ga_whole():
    assert area_from_address("군산시 경촌4길 14(경암동)") == "경암동"
    assert area_from_address("대구광역시 중구 동성로2길 80 (삼덕동1가)") == "삼덕동1가"
    assert area_from_address("대구광역시 중구 동성로 1 (동성로2가, 어느 빌딩)") == "동성로2가"
    assert area_from_address("전북특별자치도 군산시 옥도면 선유도리 279-8") == "옥도면"
    assert area_from_address("대구광역시 수성구 무학로 42") == ""


def test_event_series_key_is_one_rule():
    """The series of an events.json record: its `series`, else its name, without a leading year, normalised — one
    function (textutil.series_key) for the build's series, the English records, the slug check and new records."""
    from pipeline import build, en_source, enrich, textutil, validate
    assert build.series_key is en_source.series_key is enrich.series_key is validate.series_key is textutil.series_key
    assert textutil.series_key({"name": "2026 한빛 축제"}) == textutil.series_key({"name": "한빛축제"}) == "한빛축제"
    assert textutil.series_key({"series": "한빛 축제", "name": "2025 다른 이름"}) == "한빛축제"
    assert textutil.event_name_key("2025 한빛축제(가을)") == "한빛축제"


def test_first_sentence_korean():
    assert first_sentence("철길 옆 마을입니다. 산책하기 좋습니다.") == "철길 옆 마을입니다."
    assert first_sentence("") == ""


def test_links_without_geo_are_marked_search():
    links = build_links("경암동 철길마을", region="군산")
    assert all(not l["precise"] for l in links if l["role"] == "map")
    assert all("(검색)" in l["label"] for l in links if l["role"] == "map")
    assert precision_summary(links) == "none"
    assert not any(l["role"] == "route" for l in links)


def test_links_with_geo_and_ids_are_precise():
    links = build_links("경암동 철길마을", 35.98, 126.72, region="군산", address="군산시 경촌4길 14",
                        naver_place_id="123", google_place_id="ChIJabc")
    by = {l["key"]: l for l in links}
    assert by["naver"]["url"].endswith("/p/entry/place/123") and by["naver"]["precise"]
    assert "query_place_id=ChIJabc" in by["google"]["url"]
    assert by["kakao"]["url"].startswith("https://map.kakao.com/link/map/")
    assert "destination_place_id=ChIJabc" in by["google_route"]["url"]
    assert by["tmap"]["url"].startswith("tmap://route?")
    assert precision_summary(links) == "all"


def _payload(items, code="0000"):
    return {"response": {"header": {"resultCode": code, "resultMsg": "OK"},
                         "body": {"items": items, "numOfRows": 10, "pageNo": 1, "totalCount": 1}}}


def test_parse_items_shapes():
    assert parse_items(_payload({"item": [{"a": 1}, {"a": 2}]})) == [{"a": 1}, {"a": 2}]
    assert parse_items(_payload({"item": {"a": 1}})) == [{"a": 1}]
    assert parse_items(_payload("")) == []
    with pytest.raises(TourAPIError):
        parse_items(_payload("", code="22"))
    with pytest.raises(TourAPIError):
        parse_items({"unexpected": True})


SITE = {"site_url": "https://example.com", "region": "군산", "region_admin": "전북특별자치도", "locality": "군산시",
        "source": {"name": "군산시 문화관광"}}


def _import(tmp_path, existing, rows, site=None):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "site.json").write_text(json.dumps(site or SITE, ensure_ascii=False), "utf-8")
    (data / "places.json").write_text(json.dumps(existing, ensure_ascii=False), "utf-8")
    csv_path = tmp_path / "in.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=importer.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    code = importer.run(csv_path, data)
    return code, {e["id"]: e for e in json.loads((data / "places.json").read_text("utf-8"))}


def test_importer_merge_keeps_enrichment(tmp_path):
    existing = [{"id": "g-1", "name": "경암동 철길마을", "slug": "gyeongamdong-cheolgilmaeul", "kind": "attraction",
                 "status": "reviewed", "summary": "기존 요약", "facts": {"usetime": "상시"}, "original": {"sha256": "old"}}]
    code, out = _import(tmp_path, existing, [
        {"id": "g-1", "name": "경암동 철길마을", "kind": "attraction", "original_text": "새 원문",
         "original_license": "KOGL-1", "collected_at": "2026-10-07", "source_url": "https://x"},
        {"id": "g-2", "name": "경암동 철길마을", "kind": "attraction", "original_text": "다른 항목",
         "original_license": "UNKNOWN"}])
    assert code == 0
    assert out["g-1"]["summary"] == "기존 요약" and out["g-1"]["facts"] == {"usetime": "상시"}
    assert out["g-1"]["status"] == "reviewed"            # review state is not reset by re-import
    assert out["g-1"]["original"]["text"] == "새 원문"
    assert out["g-2"]["slug"] == "gyeongamdong-cheolgilmaeul-2"   # unique ASCII slug fixed at import time
    assert "_slug_generated" not in out["g-2"]                    # the memory-only mark is not written


def test_importer_takes_a_checked_slug_column_and_never_renames(tmp_path):
    existing = [{"id": "g-1", "name": "철길마을", "slug": "railroad-village", "kind": "attraction", "status": "draft",
                 "original": {"sha256": "x"}}]
    code, out = _import(tmp_path, existing, [
        {"id": "g-1", "name": "철길마을", "slug": "another-slug", "original_text": "x"},   # stored slug stays
        {"id": "g-3", "name": "바다 게스트하우스", "slug": "sea-guesthouse", "original_text": "x"},
        {"id": "g-4", "name": "大邱", "original_text": "x"},                              # nothing to romanize
        {"id": "g-5", "name": "바다 게스트하우스", "original_text": "x"}])
    assert code == 0
    assert out["g-1"]["slug"] == "railroad-village" and out["g-3"]["slug"] == "sea-guesthouse"
    assert out["g-4"]["slug"] == "place-4" and out["g-5"]["slug"] == "bada-geseuteuhauseu"
    # a malformed or taken CSV slug is a problem (exit 1), reported and kept as given — never silently rewritten
    code, out = _import(tmp_path, list(out.values()), [
        {"id": "g-6", "name": "골목", "slug": "골목길", "original_text": "x"},
        {"id": "g-7", "name": "골목", "slug": "sea-guesthouse", "original_text": "x"}])
    assert code == 1 and out["g-6"]["slug"] == "골목길" and out["g-7"]["slug"] == "sea-guesthouse"


def test_importer_needs_a_city_config(tmp_path):
    code, _ = _import(tmp_path, [], [{"id": "g-1", "name": "철길마을", "original_text": "x"}],
                      site={"source": {"name": "x"}})
    assert code == 2


def test_week_closure_reads_weekday_ranges():
    """'월요일~목요일' closes every day of the range, not just its two ends (the week grid, monday_open and the
    guides' closed-day counts all read week_closure)."""
    from pipeline.present import monday_open, week_closure
    days = lambda t: "".join(d for d in "월화수목금토일" if d in week_closure(t)["days"])
    assert days("매주 월요일~목요일") == "월화수목"
    assert days("월~금요일 휴무") == "월화수목금"
    assert days("토요일~월요일") == "월토일"                       # wraps past Sunday
    assert days("매주 월요일") == "월" and days("월·화요일") == "월화"
    assert week_closure("둘째·넷째 월요일")["partial"] == {"월"}
    assert monday_open("화요일~목요일") and not monday_open("월요일~수요일")
