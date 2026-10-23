"""pipeline/present.py (redesign view models), textutil.display_value and the validator's row check.

Real Gunsan data, as a fixture (tests/fixtures/gunsan_subset, built by tests/fixtures/build_gunsan_subset.py from the
Gunsan repository; tests/fixtures/fact_values.json: every distinct stored value): 빈해원's TourAPI hours,
근대역사박물관's fee table, '가능요금 (무료)', 0507 phone numbers, the meal stops of the 2박 3일 course and menu search.
The engine's city values come from site.json (pipeline.city): the subset's anchors-mode 권역, the metro fixture's
구·군 (tests/fixtures/metro), the sample's empty home. Places are looked up by name or id, never by slug."""
import json
import re
import shutil
import struct
from pathlib import Path
from urllib.parse import quote

import pytest

from pipeline import city, jsonld, present
from pipeline.build import State, build, entity_ctx
from pipeline.schema import fact_label, parking_seats_half, parking_seats_part
from pipeline.textutil import dash_times, display_value, value_shown, value_tokens
from pipeline.validate import PageScan, fact_shown, seat_only_parking_problems, validate
from tools.image_sizes import image_size

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "fixtures" / "gunsan_subset"
METRO = ROOT / "tests" / "fixtures" / "metro"
SAMPLE = ROOT / "data" / "sample"
FACT_VALUES = json.loads((ROOT / "tests" / "fixtures" / "fact_values.json").read_text("utf-8"))["pairs"]
ASCII_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@pytest.fixture(scope="module")
def S():
    return State(DATA, "preview")


# the home's question box comes with data/<city>/ask.json (pipeline/ask.py): the subset has none, so the build gets two
# starters — the box, its '#' tags and the launcher stepping aside below 1024px are on the home as on the real site
ASK = {"starters": [{"q": {"ko": "차 없이 하루 여행", "en": "A day without a car"}, "guide": "guide-02"},
                    {"q": {"ko": "이번 달 행사", "en": "Events this month"}, "page": "events"}]}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("present")
    data = tmp / "data"
    shutil.copytree(DATA, data)
    (data / "ask.json").write_text(json.dumps(ASK, ensure_ascii=False), "utf-8")
    out = tmp / "preview"
    build(data, out, "preview")
    return out


@pytest.fixture(scope="module")
def built_en(tmp_path_factory):
    """built with the English fixture laid over it (tests/fixtures/build_en_min.overlay): the launcher test reads /en/."""
    from tests.fixtures.build_en_min import overlay
    tmp = tmp_path_factory.mktemp("present_en")
    data = tmp / "data"
    shutil.copytree(DATA, data)
    overlay(data)
    (data / "ask.json").write_text(json.dumps(ASK, ensure_ascii=False), "utf-8")
    out = tmp / "preview"
    build(data, out, "preview")
    return out


@pytest.fixture(scope="module")
def M():
    return State(METRO, "preview")


def place(S, name):
    """The one place of that name (a test never names a place by its slug)."""
    found = [e for e in S.entities if e["name"] == name]
    assert len(found) == 1, (name, len(found))
    return found[0]


def page_of(out, e):
    return (out / e["_path"].strip("/") / "index.html").read_text("utf-8")


def all_values(S):
    """(entity, key, value) for every stored fact and every other source's value of the build."""
    for e in S.entities:
        for k, v in (e.get("facts") or {}).items():
            yield e, k, v
        for k, alts in (e.get("fact_alternatives") or {}).items():
            for a in alts or []:
                if a.get("value"):
                    yield e, k, a["value"]


def data_copy(tmp_path, src=DATA, edit_site=None, edit=None):
    """A copy of a data folder with site.json (edit_site(site)) and the other files (edit(name, rows)) changed."""
    data = tmp_path / "data"
    shutil.copytree(src, data)
    if edit_site:
        site = json.loads((data / "site.json").read_text("utf-8"))
        edit_site(site)
        (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    if edit:
        for f in data.glob("*.json"):
            if f.name in ("site.json", "image_sizes.json"):
                continue
            rows = json.loads(f.read_text("utf-8"))
            new = edit(f.name, rows)
            if new is not None:
                f.write_text(json.dumps(new, ensure_ascii=False), "utf-8")
    return data


# ------------------------------------------------------------------ display_value
def test_display_value_normalises_presentation_only():
    assert display_value("parking", "가능요금 (무료)") == "가능, 요금 무료"
    assert display_value("parking", "가능\n요금 (무료)") == "가능, 요금 무료"
    assert display_value("parking", "주차장이 구비") == "가능"
    assert display_value("parking", "주차가능") == "가능"
    assert display_value("parking", "불가능") == "불가"
    assert display_value("usetime", "10:00 ~ 21:00,  휴무일 : 매주 월요일") == "10:00–21:00, 휴무일 : 매주 월요일"
    assert display_value("usetime", "[하절기]09:00~18:00[동절기] 09:00~17:00 ※ 매표마감 17:00") == \
        "[하절기]\n09:00–18:00\n[동절기]\n09:00–17:00\n※ 매표마감 17:00"
    assert display_value("homepage", "http://www.gunsandal.kr/") == "gunsandal.kr"
    assert display_value("homepage", "https://www.instagram.com/some.place/") == "instagram.com/some.place"
    assert display_value("course_name", "A코스 | 근대~고군산") == "A코스 근대~고군산"
    assert display_value("address", "전라북도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"


def test_display_value_never_drops_or_changes_a_word():
    """Except the time-range dash, every word of every stored value (fact_values.json: every distinct value of the
    Gunsan places) survives display_value unchanged."""
    checked = 0
    for k, v in FACT_VALUES:
        if k in ("parking", "homepage", "reservationurl", "address"):
            continue
        assert value_tokens(display_value(k, v)) == value_tokens(dash_times(str(v))), (k, v)
        checked += 1
    assert checked == 1188


def test_every_parsed_form_prints_the_display_words_in_order():
    """A timetable, price table or fee grid keeps every source word in source order, so a template printing the
    view model passes the validator's row check (value_shown) against display_value."""
    parsed = {"tt": 0, "fees": 0, "grid": 0}
    for k, v in FACT_VALUES:
        view = present.value_view(k, v)
        for form in ("tt", "fees", "grid"):
            if view[form]:
                parsed[form] += 1
                assert value_shown(display_value(k, v), present.linear_text(view)), (k, v)
    assert parsed == {"tt": 109, "fees": 7, "grid": 1}


# ------------------------------------------------------------------ 빈해원: TourAPI hours vs the city's tourism site
def test_binhaewon_hours_conflict_shows_both_sources_flag_first(S):
    e = place(S, "빈해원")
    notes = present.Notes()
    tel = present.first_phone(e["facts"].get("infocenter"))
    row = present.fact_rows(e, ["usetime_restdate"], notes, tel)[0]
    assert row["conflict"] and row["flag"] == "영업시간만 다름"        # both sources: 매주 월요일
    assert row["flag_text"] == "영업시간만 다름 · 방문 전 전화 확인"
    # the city's own source is named by its locality (City.short_provider from site.json, nothing in the code)
    assert [b["provider"] for b in row["blocks"]] == [city.of(S.site).locality, "한국관광공사"]
    assert row["tel"] == ("063-445-2429", "0634452429")
    tour = row["blocks"][1]["tt"]
    assert [r["group"] for r in tour["rows"] if r["kind"] == "time"][:3] == ["평일", "평일", "평일"]
    assert any(r["group"] == "평일" and r["label"] == "준비시간" and r["value"] == "15:00–16:30" for r in tour["rows"])
    assert any(r["group"] == "주말" and r["label"] == "준비시간" and r["value"] == "17:00–18:00" for r in tour["rows"])
    assert tour["rows"][-1] == {"group": "", "label": "", "kind": "closed", "closed": True, "value": "매주 월요일", "note": ""}
    status = present.status_items(e, full=True)
    texts = [x["text"] for x in status]
    assert "매주 월요일 휴무" in texts and "영업시간 출처마다 다름" in texts
    flag = next(x for x in status if x["text"] == "영업시간 출처마다 다름")
    assert flag["href"] == "#h-facts" and flag["cls"] == "st-flag"
    # no 확인일 item at the end of the line any more (operator decision 2026-10-09: check dates stay in the data)
    assert all(x["key"] != "date" for x in status) and not any("2026-10-08" in x["text"] for x in status)


# ------------------------------------------------------------------ 근대역사박물관: fees and seasons
def test_stroller_rental_from_the_homepage_and_tourapi_none_show_two_blocks():
    """QA 2026-10-15 F02: a facility homepage says strollers can be borrowed, TourAPI says 없음 — both shown, the
    homepage's block first, with the flag and the call line; neither value is picked."""
    e = {"id": "x", "name": "박물관", "kind": "attraction",
         "facts": {"babycarriage": "대여 가능(예약 없이 박물관 안내소에서)", "infocenter": "063-454-7870"},
         "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"},
         "fact_sources": {"babycarriage": {"provider": "군산근대역사박물관 홈페이지", "checked_at": "2026-10-15",
                                           "url": "https://museum.example/qna/2166"}},
         "fact_alternatives": {"babycarriage": [{"value": "없음", "provider": "한국관광공사 TourAPI",
                                                 "checked_at": "2026-10-08", "contentid": "1684836"}]}}
    rows = present.fact_rows(e, present.FIT, present.Notes(), ("063-454-7870", "0634547870"))
    row = next(r for r in rows if r["key"] == "babycarriage")
    assert row["conflict"] and row["flag_text"] == "출처마다 다름 · 방문 전 전화 확인"
    assert [b["provider_full"] for b in row["blocks"]] == ["군산근대역사박물관 홈페이지", "한국관광공사 TourAPI"]
    assert [b["text"] for b in row["blocks"]] == ["대여 가능(예약 없이 박물관 안내소에서)", "없음"]
    assert row["tel"] == ("063-454-7870", "0634547870")
    site = json.loads((SAMPLE / "site.json").read_text("utf-8"))   # the engine reads the city from a whole site.json
    assert not any(f["name"] == "유모차 대여" for f in
                   jsonld.entity_node(e, site, "https://x", "https://x/p/", [], []).get("amenityFeature", []))


def test_modern_history_museum_fee_table_and_season_hours(S):
    e = place(S, "근대역사박물관")
    fees = present.value_view("usefee", e["facts"]["usefee"])["fees"]
    assert [g["label"] for g in fees["groups"]] == ["박물관 통합권", "개별권"]
    assert fees["groups"][0]["rows"] == [{"who": "성인", "price": "3,000원"}, {"who": "청소년·군인", "price": "2,000원"},
                                         {"who": "어린이", "price": "1,000원"}]
    assert fees["groups"][1]["rows"][-1] == {"who": "어린이", "price": "500원"}
    assert fees["foot"] == ["자세한 사항은 홈페이지 참조"]
    tt = present.value_view("usetime", e["facts"]["usetime"])["tt"]
    assert [(r["label"], r["value"], r["note"]) for r in tt["rows"]] == [
        ("3~10월", "09:00–18:00", "입장마감 17:30"), ("11~2월", "09:00–17:00", "입장마감 16:30")]
    texts = [x["text"] for x in present.status_items(e, full=True)]
    # the 27-character closed day now fits (≤48); the contested hours are flagged, not picked
    assert "매주 월요일, 1월 1일, 시장이 휴관일로 정한 날" in texts and "이용시간 출처마다 다름" in texts


# ------------------------------------------------------------------ '가능요금 (무료)'
def test_free_parking_value_reads_the_same_in_page_status_and_markup():
    site = json.loads((SAMPLE / "site.json").read_text("utf-8"))
    e = {"id": "x-1", "name": "[샘플] 공원", "kind": "attraction", "facts": {"parking": "가능요금 (무료)"}}
    assert display_value("parking", e["facts"]["parking"]) == "가능, 요금 무료"
    assert "주차 가능(무료)" in [x["text"] for x in present.status_items(e)]
    node = jsonld.entity_node(e, site, "https://x", "https://x/p/", [], [])
    assert {"@type": "PropertyValue", "name": "주차", "value": "가능, 요금 무료"} in node["additionalProperty"]
    assert jsonld.amenity_value("parking", "가능요금 (무료)") is None          # not a plain Y/N value
    assert jsonld.amenity_value("parking", "주차장이 구비") is True             # shown as '가능'


# ------------------------------------------------------------------ phones
def test_0507_numbers_stay_whole_and_tel_dials_the_visible_number(S):
    e = place(S, "링스모텔")
    assert present.first_phone(e["facts"]["infocenter"]) == ("0507-1302-6070", "050713026070")
    html = str(present.tel_markup("예약 0507-1302-6070"))
    assert html == '예약 <a class="tel" data-track="tel_click" href="tel:050713026070">0507-1302-6070</a>'  # tracked like every call link
    links = 0
    for k, v in FACT_VALUES:
        for m in re.finditer(r'href="tel:(\d+)">([^<]+)</a>', str(present.tel_markup(v))):
            assert m.group(1) == re.sub(r"\D", "", m.group(2)), (k, v)
            links += 1
    for x in S.entities:
        for it in present.status_items(x, full=True):
            if it["key"] == "tel":
                assert it["href"] == "tel:" + re.sub(r"\D", "", it["text"])
    assert links == 411
    assert "07-1364-9263" not in str(present.tel_markup("0507-1364-9263")).replace("0507-1364-9263", "")


def test_other_versions_dial_the_international_form(S):
    """QA 2026-10-15 SRC-05a: on the other versions (intl) a call link dials +82 and the number without its trunk 0;
    a nationwide 15xx/16xx number keeps its digits (no international form); the visible text never changes; Korean
    pages keep the domestic digits."""
    links = 0
    for k, v in FACT_VALUES:      # every distinct stored value (tests/fixtures/fact_values.json)
        ko, intl = str(present.tel_markup(v)), str(present.tel_markup(v, intl=True))
        assert re.sub(r"<[^>]+>", "", intl) == re.sub(r"<[^>]+>", "", ko)
        for m in re.finditer(r'href="tel:([+\d]+)">([^<]+)</a>', intl):
            digits = re.sub(r"\D", "", m.group(2))
            want = digits if digits.startswith("1") else "+82" + digits[1:]
            assert m.group(1) == want, (k, v)
            links += 1
    assert links == 411          # the same numbers the Korean pages link (test_0507_numbers_stay_whole…)
    assert 'href="tel:+82634433077"' in present.rich("문의 063-443-3077로 합니다", "en")
    assert 'href="tel:0634433077"' in present.rich("문의 063-443-3077로 합니다", "ko")
    assert 'href="tel:15447788"' in present.rich("Korail (www.korail.com, 1544-7788)", "en")


def test_official_hosts_in_the_text_are_links_and_the_text_stays():
    """QA 2026-10-15 SRC-05b: an official site the text writes as a bare host is a link (only OFFICIAL_WEB's hosts);
    the text of the result is the input, character for character."""
    t = "예매는 한국해운조합(island.theksa.co.kr), 문의는 1644-8774"
    h = str(present.tel_markup(t))
    assert h.count('class="xl"') == 1 and h.count('class="tel"') == 1
    assert re.sub(r"<[^>]+>", "", h) == t
    assert 'href="https://island.theksa.co.kr/"' in h and 'data-track="official_click"' in h
    # the other versions: the English booking page of the same site
    assert 'href="https://island.theksa.co.kr/page/booking?lang=en"' in str(present.tel_markup(t, intl=True))
    for plain in ("gsmg-marathon.com은 열리지 않았습니다", "홈페이지 주소는 funvillage.kr입니다", "xwww.korail.com",
                  "https://www.korail.com/", "abc.mndcamp.com", "www.kobus.co.kr"):
        assert 'class="xl"' not in str(present.tel_markup(plain)), plain
    # an FAQ answer (skip): no link starts in its head, which FAQPage repeats and the validator compares as one run
    a = "It is 063-454-7870. Booking is at island.theksa.co.kr or 063-454-7871."
    h = str(present.tel_markup(a, intl=True, skip=present.PLAIN_HEAD))
    assert h.startswith("It is 063-454-7870. ") and h.count('class="tel"') == 1 and 'href="tel:+82634547871"' in h
    assert h.count('class="xl"') == 1 and re.sub(r"<[^>]+>", "", h) == a


# ------------------------------------------------------------------ courses
def test_two_night_course_meals_and_activities_are_not_stations(S):
    cv = next(v for v in S.course_vms.values() if v["c"]["name"] == "2박 3일 코스")
    seps = [(r["kind"], r["name"]) for r in cv["seps"]]
    assert ("meal", "중식") in seps and ("meal", "석식") in seps and ("activity", "유람선관광") in seps
    names = [s["name"] for s in cv["stops"]]
    assert "중식" not in names and "석식" not in names
    assert cv["n_places"] == len(cv["stops"]) == len(cv["c"]["stops"]) - len(seps)
    assert [s["code"] for s in cv["stops"]] == [f"{i:02d}" for i in range(1, cv["n_places"] + 1)]
    assert all("next_m" not in r and "cum" not in r for r in cv["seps"])
    # under 80% of legs measured: no distance sum, the measured share instead
    assert cv["measured"] < 0.8 * cv["legs_possible"] and not cv["show_total"]
    assert cv["measure_note"] == f"좌표 있는 구간 {cv['measured']}/{cv['legs_possible']}"
    assert re.fullmatch(r"월요일 휴관 \d+곳", cv["closed_note"])
    # equal spacing when a leg is unmeasured; a stop's distance from the start only while every leg before it is
    assert [round(s["x"], 6) for s in cv["stops"]] == [round(i / (cv["n_places"] - 1), 6) for i in range(cv["n_places"])]
    first_gap = next(i for i, s in enumerate(cv["stops"]) if s["next_m"] is None)
    assert all(s["cum"] is None for s in cv["stops"][first_gap + 1:])


def test_measured_course_shows_its_sum_and_a_computed_lede(S):
    cv = next(v for v in S.course_vms.values() if v["display"] == "B코스 근대~금강권")
    assert cv["complete"] and cv["show_total"]
    assert cv["lede"].startswith("처음 5곳은 출발지에서 직선 1km 안에 모여 있고, 가장 긴 구간은")
    arirang = next(v for v in S.course_vms.values() if v["display"] == "아리랑 코스")
    assert arirang["lede"] == " ".join(arirang["c"]["summary"].split())     # a written summary is kept


def test_course_page_shows_the_lede_that_jsonld_describes(S, built):
    page = built / "courses"
    found = 0
    for f in page.glob("*/index.html"):
        p = PageScan()
        p.feed(f.read_text("utf-8"))
        trip = next(n for raw in p.jsonld_raw for n in json.loads(raw)["@graph"] if n.get("@type") == "TouristTrip")
        assert "|" not in trip["name"] and trip["name"] in p.h1
        assert trip["description"] in p.plain
        assert "이 안내하는" not in p.blocks.get("summary", "")
        assert all(i["item"].get("name") not in ("중식", "석식", "숙소") for i in trip["itinerary"]["itemListElement"])
        found += 1
    assert found == len(S.courses) == 5


def test_course_source_is_official_only_on_an_official_domain(S, built):
    """'공식' only when the course's source URL is on a site.json official_domains domain (course_source)."""
    cv = next(v for v in S.course_vms.values() if v["display"] == "B코스 근대~금강권")
    name = cv["c"]["original"]["source_name"]
    assert cv["official"] and cv["src_label"] == f"{name} 공식 코스" and cv["group_id"] == "g-day-trip"
    other = present.course_source(S, {**cv["c"], "original": {**cv["c"]["original"], "source_url": "https://example.org/x"}})
    assert not other["official"] and other["src_label"] == f"{name} 코스"
    assert present.course_source(S, {**cv["c"], "original": {}})["src_label"] == \
        f"{S.site['source']['name']} 코스"                                   # the site's source, not official
    html = page_of(built, {"_path": cv["path"]})
    assert f">{name} 공식 코스</a>" in html and 'href="/courses/#g-day-trip"' in html
    index = (built / "courses" / "index.html").read_text("utf-8")
    assert 'id="g-day-trip"' in index and f'<p class="eyebrow">{name} 공식 코스</p>' in index


def test_course_map_needs_half_the_stops_and_numbers_them_as_the_list(S, built):
    """present.course_map: drawn only when at least half of the stops (and two or more) have coordinates; each
    marker carries its number in the stop list (meals and lodging are not stops). The course page shows the map
    with the factual caption, or none; the course lines name their first stops (ui.stoprow), no ring diagram."""
    drawn = 0
    for cv in S.course_vms.values():
        stops, m = cv["stops"], present.course_map(cv["stops"])
        # QA 2026-10-15 F09-c: an optional stop (어청도 (선택사항)) is neither drawn nor counted for the share
        n_geo = sum(1 for s in stops if s["geo"] and not s["optional"])
        assert (m is not None) == (n_geo >= 2 and 2 * n_geo >= sum(1 for s in stops if not s["optional"]))
        html = (built / "courses" / cv["slug"] / "index.html").read_text("utf-8")
        assert "rt-dot" not in html and "route-fig" not in html and 'class="ng"' not in html   # no dashed rings
        if m:
            drawn += 1
            assert all(present.map_name(stops[p["n"] - 1]) == p["name"] and stops[p["n"] - 1]["geo"] for p in m["points"])
            assert f"경유지 {len(stops)}곳 중 좌표가 있는 {n_geo}곳 · 순서대로 직선 연결" in html and "data-map=" in html
        else:
            assert "data-map=" not in html and "co-grid no-map" in html
    assert drawn == 4 and len(S.course_vms) == 5
    two = next(v for v in S.course_vms.values() if v["c"]["name"] == "2박 3일 코스")   # meals sit between its stops
    assert len(two["c"]["stops"]) > len(two["stops"]) and present.course_map(two["stops"])["points"][-1]["n"] <= len(two["stops"])
    index = (built / "courses" / "index.html").read_text("utf-8")
    assert index.count('class="line-stops"') == len(S.course_vms) and 'class="mini' not in index


def _course(S, cid):
    return next(v for v in S.course_vms.values() if v["c"]["id"] == cid)


def _move_block(built, cv) -> str:
    html = (built / "courses" / cv["slug"] / "index.html").read_text("utf-8")
    m = re.search(r'<section class="wrap chapter chapter-mid co-move"[^>]*data-block="move">(.*?)</section>', html, re.S)
    assert m, cv["slug"]
    return m.group(1)


# '차 없이 다니기', day / option headings, optional and 'see' stops (QA 2026-10-15 F09) on a copy of the fixture: the
# subset predates those course fields, nearby.json and transit.json, so the world below adds them in the first city's
# shapes — the bus stops of two places, a timetable with its guide (transit.json _meta.guide_id), site.json course_move,
# the source's day headings with a second option, an optional stop, a stop naming two places and a stop's guide.
TIMETABLE_URL = "https://www.gunsan.go.kr/upload_data/timetable.xlsx"


@pytest.fixture(scope="module")
def mv_world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("move")

    def edit_site(site):
        site["course_move"] = {"guides_first": ["guide-02"], "guides_last": ["guide-13"],
                               "route_by_guide": {"guide-03": "99"}}

    def edit(name, rows):
        if name == "courses.json":
            for c in rows:
                if c["id"] == "gunsan-course-m2135-1":
                    c["transit_guides"] = ["guide-03#h-b1"]
                    c["taketime"] = {"value": "8시간", "source_name": "군산시 문화관광", "checked_at": "2026-10-15",
                                     "source_url": "https://www.gunsan.go.kr/tour/m2135"}
                    for s in c["stops"]:
                        if s["name"] == "선유도,대장도일원":
                            s["see"] = ["seonyudo", "daejangdo"]
                if c["id"] == "gunsan-course-m2137-1":
                    for i, s in enumerate(c["stops"]):
                        s["day"] = "1일차" if i <= 10 else "2일차(1안)" if i <= 16 else "2일차(2안)"
                        if s.get("place_slug") == "jangjado":
                            s["guide"] = "guide-02#h-b2"
                    c["stops"][-1]["optional"] = True             # 방축도출렁다리 (선택사항)
            return rows
        if name == "guides.json":
            for g in rows:
                if g["id"] == "guide-02":
                    g["sources"] = list(g.get("sources") or []) + [{"name": "군산시내버스시간표", "url": TIMETABLE_URL}]
                    g["_number_sources"] = ["기준 정류장 횟수 — 01 한빛체험 평일 17(06:29~22:14)·주말 9; "
                                            "99 비응(환) 평일 15(07:45~21:45)"]
                    g["body"] = list(g.get("body") or []) + [{"heading": "섬 버스", "text": "99번은 시간표에 매시 35분, "
                                                              "버스정보시스템에 매시 40분으로 나옵니다."}]
            return rows
    data = data_copy(tmp, edit_site=edit_site, edit=edit)
    nearby = {"_meta": {"bus": {"radius_m": 500, "max": 2, "source_name": "한빛시_버스정류장현황"}},
              "gunsan-305395": {"parking": [], "bus": [{"stop_name": "근대역사박물관", "meters": 100, "routes": ["01", "08"]}]},
              "gunsan-992578": {"parking": [], "bus": [{"stop_name": "비응항", "meters": 300, "routes": []}]}}
    (data / "nearby.json").write_text(json.dumps(nearby, ensure_ascii=False), "utf-8")
    times = lambda stop, wd, n, we, m: {"dir": "out", "stop": stop, "weekday": wd, "weekday_n": n,  # noqa: E731
                                         "weekend": we, "weekend_n": m}
    transit = {"_meta": {"guide_id": "guide-02", "url": TIMETABLE_URL, "source_name": "군산시내버스시간표",
                         "contact": {"tel": "063-443-3077"}},
               "routes": [{"no": "01", "times": [times("한빛체험", "06:29~22:14", 17, "06:29~22:14", 9)]},
                          {"no": "99", "times": [{**times("비응(환)", "07:45~21:45", 15, "07:45~21:45", 15),
                                                  "every": "매시 35분",
                                                  "alt": {"provider": "한빛시 버스정보시스템", "value": "매시 40분"}}]}]}
    (data / "transit.json").write_text(json.dumps(transit, ensure_ascii=False), "utf-8")
    out = tmp / "preview"
    build(data, out, "preview")
    return State(data, "preview"), out


def test_course_move_block_from_sourced_data(mv_world):
    """QA 2026-10-15 F09: '차 없이 다니기' from data the site holds — the nearest bus stops of the first and last
    stops with data (nearby.json, routes as stored; an empty list prints no route), a 카카오맵 대중교통 길찾기 link per
    measured leg between the two stored coordinates (never a place ID; long legs first), the timetable routes the bus
    rows name plus the route site.json course_move gives a transit guide (first), the configured guides around the
    course's own, and once '확인 필요: 구간별 이동 시간' (the source states the total) — never a time of ours."""
    W, built_w = mv_world
    cv = _course(W, "gunsan-course-m2135-1")
    mv = present.course_move(W, cv)
    first = mv["lead"][0]
    assert first["s"]["name"] == "근대역사박물관"
    assert first["bus"][0] == {"name": "근대역사박물관", "m": 100, "routes": ["01", "08"], "routes_text": "01·08"}
    assert [r["n"] for r in mv["lead"]] == [1, 7] and all(not b["routes"] for b in mv["lead"][1]["bus"])
    measured = [d for d in cv["legs"] if d is not None and d >= 10]
    assert len(mv["legs"]) == len(measured) and [x["long"] for x in mv["legs"]] == sorted(
        (x["long"] for x in mv["legs"]), reverse=True)
    for leg in mv["legs"]:
        a, b = leg["a"]["geo"], leg["b"]["geo"]
        assert leg["url"].startswith("https://map.kakao.com/link/by/traffic/")
        assert leg["url"].endswith(f",{a['lat']},{a['lng']}/{quote(leg['b']['name'], safe='')},{b['lat']},{b['lng']}")
    assert [(r["no"], r["first"]) for r in mv["routes"]] == [("99", True), ("01", False)]
    assert [g["path"] for g in mv["guides"]] == [W.guide_by_id["guide-02"]["_path"],
                                                  W.guide_by_id["guide-03"]["_path"] + "#h-b1",
                                                  W.guide_by_id["guide-13"]["_path"]]
    assert mv["missing"] == ["구간별 이동 시간"] and mv["tel"] == "063-443-3077"
    block = _move_block(built_w, cv)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block))
    assert "확인 필요: 구간별 이동 시간" in text and text.count("확인 필요") == 1
    assert "실제 이동" not in text and not re.search(r"\d+\s*분\s*(?:걸|소요)|도보|걸어서", text)
    assert block.count('data-provider="kakao_transit"') == len(mv["legs"])
    assert re.search(r"data-bus=\"비응항\"[^>]*>[^<]*정류장 <span class=\"tn\">300m</span></p>", block)   # no routes
    assert "비응(환) 07:45~21:45" in text and "매시 40분" in text
    assert "방문 전 전화 확인" in text and 'href="tel:0634433077"' in block


def test_move_block_without_configuration_names_the_course_guides_only(mv_world, tmp_path):
    """Without site.json course_move the block names only the course's own transit guides and no extra route."""
    W, _ = mv_world
    saved = W.city.raw.pop("course_move")
    try:
        mv = present.course_move(W, _course(W, "gunsan-course-m2135-1"))
        assert [g["path"] for g in mv["guides"]] == [W.guide_by_id["guide-03"]["_path"] + "#h-b1"]
        assert [r["no"] for r in mv["routes"]] == ["01"]
    finally:
        W.city.raw["course_move"] = saved


def test_course_days_options_and_the_source_duration(mv_world):
    """QA 2026-10-15 F09-b: the source's day / option headings in source order; no leg between the last stop of
    '2일차(1안)' and the first of '2일차(2안)' (not counted, not measured, no neighbour on the boards); a day change
    keeps its leg; the one source duration with its source."""
    W, built_w = mv_world
    b = _course(W, "gunsan-course-m2137-1")
    assert b["days"] == ["1일차", "2일차(1안)", "2일차(2안)"]
    brk = [s for s in b["stops"] if s["brk"]]
    assert len(brk) == 1 and brk[0]["day"] == "2일차(2안)"
    k = b["stops"].index(brk[0])
    before, after = b["stops"][k - 1], brk[0]
    assert before["next"] is None and after["prev"] is None and before["next_m"] is None and after["prev_m"] is None
    assert (before, after) not in b["pairs"]
    # one break and one optional (last) stop: two legs fewer than the stops would give
    assert b["legs_possible"] == len(b["stops"]) - 1 - 2
    first2 = next(s for s in b["stops"] if s["day"] == "2일차(1안)")
    last1 = b["stops"][b["stops"].index(first2) - 1]
    assert last1["day"] == "1일차" and (last1["next_m"] is not None or not (last1["geo"] and first2["geo"]))
    a = _course(W, "gunsan-course-m2135-1")
    assert a["taketime"]["value"] == "8시간" and a["taketime"]["hours"] == 8
    html = (built_w / "courses" / b["slug"] / "index.html").read_text("utf-8")
    seps = re.findall(r'<li class="stop-sep sep-day"><span class="sep-k">[^<]*</span><span class="sep-v">([^<]*)</span>', html)
    assert seps == b["days"]
    assert "2일차(1안) 끝" in html and "2일차(2안) 시작" in html
    pts = (present.course_map(b["stops"]) or {}).get("points") or []
    assert all(p.get("seg", 0) == (1 if p["n"] >= after["n"] else 0) for p in pts)
    # plain schedule numbers (a stop's `day` 1, 2) read '일정 1', '일정 2'
    c = {**a["c"], "stops": [{**s, "day": 1 if i < 4 else 2} for i, s in enumerate(a["c"]["stops"])]}
    assert present.course_vm(W, c)["days"] == ["일정 1", "일정 2"]


def test_course_optional_and_see_stops(mv_world):
    """QA 2026-10-15 F09-c: an optional stop ('… (선택사항)') — no leg into it, not on the map; a stop's guide (the
    island ferry) on its card and on the leg into it; a stop that names two places ('선유도,대장도일원') links both,
    with no coordinates and no leg."""
    W, built_w = mv_world
    two = _course(W, "gunsan-course-m2137-1")
    opt = two["stops"][-1]
    assert opt["optional"] and opt["prev_m"] is None and all(opt not in pair for pair in two["pairs"])
    m = present.course_map(two["stops"])
    assert m is None or opt["n"] not in [p["n"] for p in m["points"]]
    jang = next(s for s in two["stops"] if s["t"] and s["t"]["slug"] == "jangjado")
    assert jang["guide"]["path"] == W.guide_by_id["guide-02"]["_path"] + "#h-b2"
    leg = next((x for x in present.course_move(W, two)["legs"] if x["b"] is jang), None)
    assert leg is None or leg["guide"]["path"].startswith(W.guide_by_id["guide-02"]["_path"])
    html = (built_w / "courses" / two["slug"] / "index.html").read_text("utf-8")
    assert "선택 경유지" in html and f'href="{jang["guide"]["path"]}"' in html
    a = _course(W, "gunsan-course-m2135-1")
    see = next(s for s in a["stops"] if s["see"])
    assert [x["name"] for x in see["see"]] == ["선유도", "대장도"] and see["t"] is None and see["geo"] is None
    page = (built_w / "courses" / a["slug"] / "index.html").read_text("utf-8")
    assert all(f'href="{x["path"]}"' in page for x in see["see"])


def test_validate_checks_the_move_block_and_the_timetable_copy(mv_world):
    """pipeline.validate: course_move_problems reads the block's bus rows against nearby.json (a changed route number
    is a finding) and its transit links against the stops' coordinates; transit_problems checks transit.json against
    the timetable record of the guide transit.json _meta.guide_id names (a changed '21:45' is a finding)."""
    import copy
    from pipeline.validate import course_move_problems, scan_file, transit_problems
    W, built_w = mv_world
    c = next(x for x in W.courses if x["id"] == "gunsan-course-m2135-1")
    page = scan_file(built_w / "courses" / c["slug"] / "index.html")
    assert course_move_problems(W, c, page) == []
    pid = "gunsan-305395"
    saved = W.nearby[pid]
    try:
        W.nearby[pid] = {**saved, "bus": [{**saved["bus"][0], "routes": ["01", "72"]}]}
        assert any("근대역사박물관" in p and "72" in p for p in course_move_problems(W, c, page))
    finally:
        W.nearby[pid] = saved
    leg = next(r for r in page.access_rows if r["kind"] == "leg")
    leg_hrefs = list(leg["hrefs"])
    leg["hrefs"][:] = [h.replace("/link/by/traffic/", "/link/to/") for h in leg_hrefs]
    try:
        assert any("대중교통 길찾기 링크" in p for p in course_move_problems(W, c, page))
    finally:
        leg["hrefs"][:] = leg_hrefs
    assert transit_problems(W) == []
    saved_tr = W.transit
    try:
        tr = copy.deepcopy(saved_tr)
        t = tr["routes"][-1]["times"][-1]
        assert (tr["routes"][-1]["no"], t["weekday"]) == ("99", "07:45~21:45")
        t["weekday"] = t["weekend"] = "07:45~21:46"
        W.transit = tr
        assert any("99번" in p for p in transit_problems(W))
        W.transit = {**copy.deepcopy(saved_tr), "_meta": {**saved_tr["_meta"], "guide_id": ""}}
        assert transit_problems(W) == ["transit.json: 대조할 가이드(_meta.guide_id 없음)가 없음"]
    finally:
        W.transit = saved_tr


# ------------------------------------------------------------------ search
def test_menu_search_finds_binhaewon_and_alternate_names(S, built):
    index = json.loads((built / "search" / "index.json").read_text("utf-8"))
    row = next(r for r in index if r["n"] == "빈해원")
    assert "짜장면" in row["m"] and row["s"]
    norm = lambda s: re.sub(r"\s+", "", (s or "").lower())
    hits = [r["n"] for r in index if norm("짜장면") in norm(r.get("m"))]
    assert "빈해원" in hits
    assert any("군산근대역사박물관" in r["a"] for r in index if r["n"] == "근대역사박물관")
    js = (ROOT / "templates" / "assets" / "search.js").read_text("utf-8")
    assert "row.m" in js and "?q=" in js and "focus" in js
    html = (built / "search" / "index.html").read_text("utf-8")
    assert 'action="/search/"' in html and "빈해원" in html                    # no-JS: the 가나다 directory
    assert sum(1 for r in index if r["k"] in ("attraction", "stay", "food")) == len(S.entities)
    # the area words (d) are the place's 동 as the city reads it (City.area_label); the 권역 (r) its group
    assert row["d"] == "장미동" and row["r"] == place(S, "빈해원")["_region"]
    # the search placeholder is the site's own examples (site.json search_examples)
    assert 'placeholder="예: ' + ", ".join(S.site["search_examples"]) + '"' in html


def test_metro_search_index_and_place_line_carry_the_district(M, tmp_path):
    """District city (tests/fixtures/metro): the place line reads '<광역시> 중구 삼덕동1가', cards and the index the
    '중구 삼덕동1가' area (or '수성구 <road>' without a 동), and '수성구' finds the 수성구 places."""
    out = tmp_path / "metro"
    build(METRO, out, "preview")
    index = json.loads((out / "search" / "index.json").read_text("utf-8"))
    by = {r["n"]: r for r in index}
    assert by["[샘플] 중구 전시관 A"]["d"] == "중구 삼덕동1가" and by["[샘플] 중구 전시관 A"]["r"] == "중구"
    assert by["[샘플] 수성구 공원 C"]["d"] == "수성구 시험로"
    assert by["[샘플] 구·군 없는 장소 H"]["r"] == city.of(M.site).none_label
    assert [r["n"] for r in index if "수성구" in r["d"]] == ["[샘플] 수성구 공원 C"]
    e = place(M, "[샘플] 중구 전시관 A")
    html = page_of(out, e)
    kicker = html.split('<p class="kicker">')[1].split("</p>")[0]
    assert kicker.endswith("<span>대구광역시 중구 삼덕동1가</span>")
    assert present.card_vm(e)["meta"].endswith(" · 중구 삼덕동1가")
    home = (out / "index.html").read_text("utf-8")
    # UI4 home: the opening's kicker names the region once ('지금 대구 · 10월'), never '대구광역시 대구광역시'
    kick = re.search(r'<p class="ho-k"><span class="ho-dot" aria-hidden="true"></span>([^<]+)</p>', home)
    assert kick and kick.group(1) == present.home_opening(M)["kicker"] and "대구광역시 대구광역시" not in home


def test_other_names_keep_only_what_the_search_would_not_find_anyway():
    """present.other_names (QA 2026-10-15 U10): the names in the other versions, ' · '-joined in their order, each
    once — without one search.js finds anyway (inside n, a or a longer name kept, compared as search.js does)."""
    row = {"n": "선유도", "a": "선유도 해수욕장"}
    present.other_names(row, "Seonyudo Island", "", None, "seonyudo island", "선유 도", "2026 Seonyudo Island Festival")
    assert row["o"] == "2026 Seonyudo Island Festival"
    row = {"n": "군산시간여행축제", "a": ""}
    present.other_names(row, "2026 군산시간여행축제", "Gunsan Time Travel Festival")
    assert row["o"] == "2026 군산시간여행축제 · Gunsan Time Travel Festival"
    row = {"n": "A", "a": ""}
    present.other_names(row, "", None, "A")
    assert "o" not in row
    present.other_names(row, "선유도", "Seonyudo Island", key="v")
    assert row["v"] == "선유도 · Seonyudo Island"


def test_the_index_has_no_other_language_names_without_the_english_version():
    """A build without an English version (the sample data): no row carries o or v, and nothing breaks."""
    S = State(ROOT / "data" / "sample", "sample")
    assert getattr(S, "en", None) is None
    rows = present.search_index(S)
    assert rows and not any("o" in r or "v" in r for r in rows)


# ------------------------------------------------------------------ status line, stays, regions, home
def test_status_line_is_never_empty_and_shows_no_check_date():
    # rule change (operator decision 2026-10-09): the line used to end with the earliest 확인일 of its items; now
    # no item is a date and no item text carries a check date (validate.visible_check_dates)
    from pipeline.validate import visible_check_dates
    S0 = State(SAMPLE, "sample")
    for e in S0.entities:
        items = present.status_items(e, full=True)
        assert items, e["name"]
        assert all(x["key"] != "date" for x in items), e["name"]
        assert not visible_check_dates(" ".join(x["text"] for x in items)), e["name"]
    bare = present.status_items(next(e for e in S0.entities if e["id"] == "sample-0003"))   # an address and nothing else
    assert bare[0]["text"].startswith("확인 필요: ") and bare[0]["href"].endswith("#h-facts")


def test_stay_ask_line_only_where_it_can_differ(S):
    asked = []
    assert len(S.lists["stay"]) == 5
    for e in S.lists["stay"]:
        vm = present.place_vm(S, e, entity_ctx(e, S))
        rooms = (e.get("facts") or {}).get("roomcount", "")
        if vm["ask"]:
            asked.append(e)
            assert any(w in e["_type"] for w in present.SMALL_STAY) or (str(rooms).isdigit() and int(rooms) <= 3)
    assert [e["name"] for e in asked] == ["게스트하우스 이웃"] and len(asked) < len(S.lists["stay"]) / 2
    big = place(S, "베스트웨스턴 군산호텔")
    assert not present.place_vm(S, big, entity_ctx(big, S))["ask"]


def test_regions_follow_the_configured_anchors(S):
    """anchors mode (the subset's site.json regions): the nearest anchor place by id, the far group beyond far.m,
    a place without coordinates by its (구·군, 동), every id ASCII."""
    C = city.of(S.site)
    assert [a["name"] for a in S.anchors] == [a["name"] for a in C.anchors] == ["원도심", "은파", "고군산", "새만금·비응", "금강"]
    assert [a["id"] for a in S.anchors] == [f"r-{a['key']}" for a in C.anchors]
    assert S.region_names == [a["name"] for a in C.anchors] + [C.far["label"], C.none_label]
    assert place(S, "근대역사박물관")["_region"] == "원도심" and place(S, "선유도")["_region"] == "고군산"
    assert place(S, "어청도")["_region"] == C.far["label"]
    for e in S.entities:
        assert e["_region"] in S.region_names
        if not e["_geo"]:
            assert e["_region_basis"] in ("읍·면·동", "") and (e["_region_basis"] or e["_region"] == C.none_label)
    vm = present.map_vm(S)
    ids = [r["id"] for r in vm["regions"]] + [d["id"] for r in vm["regions"] for d in r["dongs"]]
    assert all(ASCII_ID.match(i) for i in ids) and len(ids) == len(set(ids))
    assert sum(len(r["members"]) for r in vm["regions"]) == len(S.entities)
    assert (vm["far_m"], vm["far_label"], vm["none_label"], vm["mode"]) == (12000, "먼 섬", "권역 미정", "anchors")
    L = present.list_vm(S, "attraction")
    assert [g["name"] for g in L["groups"]] == [r for r in S.region_names if any(g["name"] == r for g in L["groups"])]
    assert all(ASCII_ID.match(g["id"]) and g["id"].startswith("g-") for g in L["groups"])
    assert [rid for _, _, rid in L["regions"]] == [g["id"] for g in L["groups"]]


def test_anchor_missing_and_no_far_group(tmp_path):
    """An anchor place the build does not have is skipped with a warning; with regions.far null there is no far
    group (the far island joins its nearest anchor)."""
    def edit_site(site):
        site["regions"]["far"] = None
        site["regions"]["anchors"][0]["place_id"] = "no-such-place"
    S2 = State(data_copy(tmp_path, edit_site=edit_site), "preview")
    assert any("no-such-place" in w and "원도심" in w for w in S2.warnings)
    assert "원도심" not in [a["name"] for a in S2.anchors] and "먼 섬" not in S2.region_names
    assert place(S2, "어청도")["_region"] in [a["name"] for a in S2.anchors]


def test_district_regions_follow_the_address(M):
    """district mode (the metro fixture): the 구·군 of the address, in the official order of site.json districts
    (only those with places), then '구·군 미기재'; list and map groups follow it; ids are 'g-jung-gu', 'r-jung-gu'."""
    C = city.of(M.site)
    assert M.anchors == [] and M.warnings == []
    assert M.region_names == list(C.districts) + [C.none_label]          # the fixture has a place in all nine
    for e in M.entities:
        district = C.address_parts(e)[0]
        assert e["_region"] == (district or C.none_label)
        assert e["_region_basis"] == ("주소" if district else "")
    vm = present.map_vm(M)
    assert [r["name"] for r in vm["regions"]] == M.region_names and vm["mode"] == "district"
    assert [r["id"] for r in vm["regions"]][:3] == ["r-jung-gu", "r-dong-gu", "r-seo-gu"]
    jung = vm["regions"][0]
    assert [d["name"] for d in jung["dongs"]] == ["동성로2가", "삼덕동1가"]
    assert next(r for r in vm["regions"] if r["name"] == "수성구")["dongs"][0]["name"] == "수성구 동 미기재"
    ids = [r["id"] for r in vm["regions"]] + [d["id"] for r in vm["regions"] for d in r["dongs"]]
    assert all(ASCII_ID.match(i) for i in ids) and len(ids) == len(set(ids))
    assert vm["n_regions"] == 9 and vm["label_pts"] and all("geo" not in x for x in vm["label_pts"])
    L = present.list_vm(M, "attraction")
    order = [g["name"] for g in L["groups"]]
    assert order == [r for r in M.region_names if r in order] and order[0] == "중구" and order[-1] == C.none_label
    # the home: the 구·군 tiles (no none group, no map, no invented coordinates)
    h = present.home_vm(M)
    assert [r["name"] for r in h["regions2"]] == list(C.districts) and h["region_map"] is None
    assert all(r["anchor"] is None and r["id"] == present.region_id(M, r["name"]) for r in h["regions2"])


def test_twins_need_the_same_district(M):
    """Two places of one name in two 구·군 are two places, not one building (design 3.3)."""
    same = [e for e in M.entities if e["name"] == "[샘플] 같은 이름 식당"]
    assert len(same) == 2 and all(e["_twins"] == [] for e in same)


def test_home_answer_figures_have_a_referent(S):
    h = present.home_vm(S)
    assert "h1" not in h and "lede" not in h                     # the unused Gunsan-only opening is gone
    assert [a["key"] for a in h["answers"]] == ["당일", "아이와 함께", "비 오는 날", "숙소 찾기"]
    for a in h["answers"]:
        assert not a["fig"] or a["fig"].replace(",", "") in present.figures(a["answer"]) or a["fig_label"], a
    assert present.answer_row("x", "/", "숫자가 없는 문장", "12", "곳")["fig"] == ""
    assert h["answers"][0]["href"] == "/courses/#g-day-trip"
    assert S.warnings == []


def test_guide_answer_fields_are_checked_against_the_guide(S):
    """guides.json `answer` (the copy that used to live in code) is used only while every figure in it is written
    in the guide; otherwise a warning and the guide's first heading."""
    g = next(x for x in S.guides if x["id"] == "guide-03")
    a = present.guide_answer(g, S)
    assert a["answer"] == g["answer"]["answer"] and a["fig"] == "4" and a["unit"] == "곳" and a["closed"]
    warnings = []
    S2 = type("S2", (), {"warnings": warnings, "lists": S.lists})()
    bad = {**g, "answer": {**g["answer"], "answer": g["answer"]["answer"].replace("350m", "777m")}}
    a2 = present.guide_answer(bad, S2)
    assert a2["answer"] == g["body"][0]["heading"] and any("777" in w for w in warnings)
    tile = present.guide_tile(S2, {**g, "answer_short": {**g["answer_short"], "short": "실내 전시관 99곳"}}, "answer_short")
    assert tile is None and any("99" in w for w in warnings)


def test_home_focus_follows_dish_festivals(S, tmp_path):
    """The first city's owner 2026-10-13 ('왜 아직도 짬뽕 요리가 메인이지?'), as data (site.json home.focus): a dish
    leads the home — the food hub tile, the last answer row, the search example — only while a festival named after it
    runs or starts within home.focus.days; otherwise the tile leads with its own hub_short (the restaurant count) and
    the dishes are equal pills. Without home.focus (the fixture) there is no focus at all."""
    assert present.home_focus(S) is None

    def edit_site(site):
        site["search_examples"] = ["선유도", "철길마을", "주차"]
        site["home"]["focus"] = {"days": 21, "dishes": [{
            "dish": "짬뽕", "answer": ["짬뽕", "guide-02"],
            "hub": {"key": "맛집", "short": "짬뽕 요리 20곳 · 게장 12곳 · 아귀 9곳 · 떡갈비 6곳",
                    "tiny": "게장 12곳 · 아귀 9곳", "fig": "20", "unit": "곳", "lead": "짬뽕 요리"}}]}

    def edit(name, rows):
        if name == "guides.json":    # the hub tile outside the festival: the restaurant count leads
            for g in rows:
                if g["id"] == "guide-13":
                    g["hub_short"] = {"key": "맛집", "short": "음식점 172곳 · 짬뽕 20곳 · 게장 12곳 · 아귀 9곳 · 떡갈비 6곳",
                                      "tiny": "짬뽕 20곳 · 게장 12곳", "fig": "172", "unit": "곳"}
                    g["hub_lead"] = "음식점"
            return rows
        if name == "events.json":
            return rows + [{"id": "event-fixture-dish", "slug": "sample-dish-festival", "status": "published",
                            "series": "[샘플] 짬뽕 축제", "name": "[샘플] 2026 짬뽕 축제", "start_date": "2026-10-09",
                            "end_date": "2026-10-11", "place_name": "[샘플] 광장", "source_name": "한국관광공사 TourAPI",
                            "checked_at": "2026-10-08"}]
    S2 = State(data_copy(tmp_path, edit_site=edit_site, edit=edit), "preview")
    S2.today = "2026-10-13"                                   # two days after the festival (10-09–10-11)
    assert present.home_focus(S2) is None
    food = present.purposes_vm(S2)[0]
    assert (food["key"], food["lead"], food["fig"]) == ("맛집", "음식점", "172")
    assert food["pills"] == ["짬뽕 20곳", "게장 12곳", "아귀 9곳", "떡갈비 6곳"]
    assert "짬뽕" not in present.search_example(S2)
    assert "짬뽕" not in [a["key"] for a in present.home_vm(S2)["answers"]]
    S2.today = "2026-09-25"                                   # 14 days before it
    assert present.home_focus(S2)["dish"] == "짬뽕"
    food = present.purposes_vm(S2)[0]
    assert (food["lead"], food["fig"]) == ("짬뽕 요리", "20") and present.search_example(S2).startswith("예: 짬뽕")
    assert [a["key"] for a in present.home_vm(S2)["answers"]][-2:] == ["짬뽕", "숙소 찾기"]   # the configured rows, then it
    S2.today = "2026-09-10"                                   # 29 days before: out of the window
    assert present.home_focus(S2) is None


def test_home_accent_points(S, built):
    """Accent points (owner 2026-10-09, after masstige.io; role names since the review of 2026-10-14): the list hubs'
    guides (site.json list_hubs) lead the purposes as the lead tile and two pale sea tints, the 당일 courses are the
    one brand-sea tile, the rest stay grey. UI4 (owner 2026-10-14): the homes show them as the question card's icon
    menu — no colour bento and no black band on either home any more."""
    rows = present.purposes_vm(S)
    tones = [(p["key"], p.get("tone", "")) for p in rows]
    assert tones[:4] == [("맛집", "lead"), ("숙소·펜션", "tint"), ("가볼만한 곳", "mist"), ("당일", "sea")]
    assert tones[4:] == [("아이와 함께", ""), ("비 오는 날", "")]
    assert [p["href"] for p in rows[:3]] == [S.guide_by_id[city.of(S.site).list_hubs[k]["guide_id"]]["_path"]
                                             for k in ("food", "stay", "attraction")]
    # review 2026-10-09: the lead figure names what it counts (the guide's hub_lead); the other parts become pills
    food = rows[0]
    g13 = S.guide_by_id["guide-13"]
    assert food["lead"] == g13["hub_lead"] and food["short"].startswith(f"{food['lead']} {food['fig']}{food['unit']} · ")
    assert food["pills"] and not any(p.startswith(food["lead"]) for p in food["pills"])
    # the phone line and the pills are the desktop line's other parts (nothing the lead already says, nothing new)
    assert food["pills"] == food["short"].split(" · ")[1:]
    assert all(part in food["pills"] for part in food["tiny"].split(" · "))
    day = rows[3]
    assert day["pill"] == "공식 코스" and day["short"].endswith("공식 당일 코스 A·B") and day["href"] == "/courses/#g-day-trip"
    pages = ["index.html"] + (["en/index.html"] if (built / "en" / "index.html").exists() else [])
    for page in pages:
        html = (built / page).read_text("utf-8")
        assert re.search(r'<h1 id="h-home" class="op-h1[^"]*">[^<]+</h1>', html) and 'class="mkr"' not in html, page
        # the big-numerals band is retired (owner 2026-10-14: 'AI 같고 촌스럽다'), no heading ends in a full stop
        assert 'id="h-nums"' not in html and not re.search(r'class="h2"[^>]*>[^<]*[가-힣a-z]\.</h2>', html), page
    if (built / "en" / "index.html").exists():   # a build with an English version (data/<region>/en)
        en = (built / "en" / "index.html").read_text("utf-8")
        # owner 2026-10-14 ('외국어 사이트들은 UI UX가 아직 업데이트가 안 됐네'): the English home takes the Korean home's
        # design — no bento tiles, no black band, no oversized word; the counts under the icon menu's pictures
        assert "band-dk" not in en and "on-dark" not in en and 'class="dk-word"' not in en
        assert 'class="bt ' not in en and '<section class="abar"' not in en and 'class="hq-n tn"' in en
        assert '<section class="sec sec-co tone-2" aria-labelledby="h-co">' in en
    ko = (built / "index.html").read_text("utf-8")
    assert 'class="hq-n tn"' in ko   # the counts sit under the menu's pictures instead
    assert 'class="bt ' not in ko and "band-dk" not in ko and '<section class="abar"' not in ko
    assert '<section class="story" data-story' in ko and ko.count('class="dk-word"') <= 1
    css = (built / "assets" / "style.css").read_text("utf-8")
    assert "--lime:var(--tint2)" in css.replace(" ", "")   # the lime / lavender / sky roles are retired to sea tints


def test_home_story_and_gallery_come_from_site_json(S, tmp_path):
    """home.story chapters: whole summary sentences of the configured places; a chapter whose own fact is gone from
    the data is left out with a warning (the others stay). The gallery and its figures follow home.gallery /
    home.center / home.far; the region tiles the anchors."""
    h = present.home_vm(S)
    assert [c["id"] for c in h["chapters"]] == ["ch-1899", "ch-1908", "ch-1909", "ch-today"]
    port = place(S, "군산내항")
    assert h["chapters"][0]["text"][0] in port["summary"] and "1899년에 개항" in h["chapters"][0]["text"][0]
    steps = h["chapters"][2]
    assert steps["title"] == "1909–1936, 근대 도시의 흔적" and [s["y"] for s in steps["steps"]] == ["1909", "1936"]
    today = h["chapters"][3]
    customs, seonyu = place(S, "구 군산세관 본관"), place(S, "선유도")
    assert [f["label"] for f in today["figs"]] == [f"{customs['name']}에서 직선 1km 안의 관광지",
                                                   f"{customs['name']}에서 {seonyu['name']}까지 직선"]
    assert h["gallery_cfg"]["region"] == "고군산" and len(h["gallery"]) == 4
    assert h["gallery_fact"]["n"] == sum(1 for e in S.lists["attraction"] if e["_region"] == "고군산")
    assert h["gallery_fact"]["km"] == today["figs"][1]["n"]
    assert [r["name"] for r in h["regions2"]] == [a["name"] for a in S.anchors] and h["region_map"]["anchors"]
    assert h["teaser"]["cv"]["c"]["id"] == "gunsan-course-m2135-2"

    def edit(name, rows):   # the port's summary loses the 1899 sentence
        if name == "places.json":
            for p in rows:
                if p["id"] == port["id"]:
                    p["summary"] = "항구입니다."
            return rows
    S2 = State(data_copy(tmp_path, edit=edit), "preview")
    h2 = present.home_vm(S2)
    assert [c["id"] for c in h2["chapters"]] == ["ch-1908", "ch-1909", "ch-today"]
    assert any("1899년에 개항" in w and "1899 장 생략" in w for w in S2.warnings)


def test_home_survives_missing_places(tmp_path):
    """Every home block site.json configures may point at a place, guide or course the build does not have: the
    block is left out with a warning, nothing breaks, and the computed rows stay (sample data)."""
    def edit_site(site):
        site["regions"]["anchors"] = [{"key": "a", "name": "가", "place_id": "sample-0001"},   # no coordinates
                                      {"key": "b", "name": "나", "place_id": "no-place-1"}]
        site["dist_anchors"] = ["no-place-2"]
        site["home"].update({"answers": [["없는 가이드", "guide-x"]], "teaser_course": "no-course",
                             "center": {"place_id": "no-place-3"}, "far": {"place_id": "no-place-4"},
                             "gallery": {"eyebrow": "e", "title": "t", "region": "가"},
                             "media": {"cover": ["no-place-5", 0], "hero": [["sample-0002", 0]], "gallery": [["no-place-6", 1]]},
                             "story": [{"id": "ch-x", "big": "1900", "sources": [{"place_id": "no-place-7", "needle": "x"}]}]})
    data = data_copy(tmp_path, SAMPLE, edit_site=edit_site)
    S2 = State(data, "sample")
    h = present.home_vm(S2)
    assert h["answers"] and h["answers"][0]["key"] == "당일"            # the computed row stays
    assert not h["chapters"] and not h["gallery"] and not h["cover"] and not h["hero"] and h["teaser"] is None
    assert S2.anchors == [] and h["regions2"] == [] and h["region_map"] is None
    for what in ("sample-0001", "no-place-1", "no-place-2", "guide-x", "no-course", "no-place-3", "no-place-4",
                 "no-place-5", "no-place-6", "no-place-7"):
        assert any(what in w for w in S2.warnings), what
    out = tmp_path / "out"
    build(data, out, "sample")                                         # and the whole build still runs
    assert (out / "index.html").exists()


def test_empty_home_config_has_no_warnings_and_no_filler(tmp_path):
    """The sample configures no home block: no warning, no story, no gallery. The live city's configured home
    (data/daegu site.json home) points only at places, photos and summary sentences that exist: no warning either."""
    S0 = State(SAMPLE, "sample")
    h = present.home_vm(S0)
    assert S0.warnings == []
    assert not (h["chapters"] or h["gallery"] or h["hero"] or h["cover"])
    S1 = State(ROOT / "data" / "suwon", "production")
    present.home_vm(S1)
    assert [w for w in S1.warnings if "홈" in w or "답 " in w] == []


def test_home_course_lines_without_durations(tmp_path):
    """Courses whose source states no duration still fill the home course section (in file order), never an empty
    list under the heading."""
    def drop(name, rows):
        if name == "courses.json":
            return [{**c, "duration": ""} for c in rows]
    data = data_copy(tmp_path, SAMPLE, edit=drop)
    S2 = State(data, "sample")
    h = present.home_vm(S2)
    assert S2.courses and [cv["slug"] for cv in h["lines"]] == [c["slug"] for c in S2.courses]


# ------------------------------------------------------------------ home opening (owner 2026-10-13, specs/home_redesign.md)
NEWS_ORDER = ("festival", "event", "abroad", "guide", "video")


def _check_news(S, day: str) -> list[dict]:
    """The ranking rule (the comment above present.NEWS_MAX) checked against the data itself on one build date."""
    S.today = day
    news = present.home_news(S)
    kinds = [c["kind"] for c in news]
    assert present.NEWS_MIN <= len(news) <= present.NEWS_MAX, (day, kinds)
    assert len({c["key"] for c in news}) == len(news) and all(c["href"] and c["title"] for c in news)
    assert kinds == sorted(kinds, key=NEWS_ORDER.index), (day, kinds)    # focus → events → abroad → guides → video
    # events: the running / coming editions within 30 days, in ranked_events order; nothing past
    rows = [r for r in present.ranked_events(S) if r["days"] <= present.NEWS_EVENT_DAYS]
    want = ["ev:" + str(r["ev"].get("id")) for r in rows]
    got = [c["key"] for c in news if c["kind"] in ("festival", "event")]
    assert got == [k for k in want if k in got] and all(r["last"] >= day for r in rows)
    if "festival" not in kinds:
        assert got == want[:3]
    # foreign press: the newest articles dated on or before the build date (date, then id)
    dated = sorted((a for a in S.abroad if a.get("kind") == "article" and a.get("date")
                    and present.iso_floor(a["date"]) <= day), key=lambda a: a["id"])
    dated.sort(key=lambda a: present.iso_floor(a["date"]), reverse=True)
    ab = [c["key"] for c in news if c["kind"] == "abroad"]
    assert ab and ab == ["ab:" + a["id"] for a in dated[:len(ab)]]
    # guides: approved_at, then the guide number, both newest first
    guides = [c["href"] for c in news if c["kind"] == "guide"]
    top = sorted(S.guides, key=present._guide_rank, reverse=True)
    assert guides and guides == [g["_path"] for g in top[:len(guides)]]
    return news


# The home's news cards on fixed dates (spec 1·5·8a), on a copy of the fixture with the first city's kinds of records
# (the subset predates them): a dish festival (site.json home.focus), an exhibition running to a day the source
# gives, a museum programme whose source gives only its end month, and two /abroad/ articles (one with the outlet's
# own preview image).
NEWS_DISH, NEWS_RUN, MUSEUM_EV = "event-news-dish", "event-news-run", "event-news-month"


@pytest.fixture(scope="module")
def news_world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("news")

    def edit_site(site):
        site["home"]["focus"] = {"dishes": [{"dish": "짬뽕", "answer": ["짬뽕", "guide-02"]}]}

    def ev(eid, slug, name, start, **kw):
        return {"id": eid, "slug": slug, "status": "published", "series": f"[샘플] {name}", "name": f"[샘플] 2026 {name}",
                "start_date": start, "source_name": "한국관광공사 TourAPI", "checked_at": "2026-10-08", **kw}

    def edit(name, rows):
        if name == "events.json":
            return rows + [ev(NEWS_DISH, "sample-dish-festival", "짬뽕 축제", "2026-10-09", end_date="2026-10-11",
                              place_name="[샘플] 광장"),
                           ev(NEWS_RUN, "sample-harbour-art", "항구 예술전", "2026-10-02", end_date="2026-10-31",
                              place_name="진포해양공원", place_slugs=["jinpohaeyanggongwon"]),
                           ev(MUSEUM_EV, "sample-museum-weekend", "박물관 주말 행사", "2026-06-06", end_month="2026-10",
                              period_text="2026. 6. 6. ~ 10월", place_name="근대역사박물관",
                              place_slugs=["geundaeyeoksabangmulgwan"])]
    data = data_copy(tmp, edit_site=edit_site, edit=edit)
    art = lambda aid, date, **kw: {"id": aid, "kind": "article", "status": "published", "url": f"https://example.org/{aid}",  # noqa: E731
                                   "note": "[샘플] 우리가 쓴 한 줄 소개", "outlet": "Example Times", "title": f"[샘플] {aid}",
                                   "date": date, "lang": "en", "checked_at": "2026-10-01", "source_type": "press", **kw}
    abroad = {"items": [art("ab-news-1", "2026-09-01", place_slugs=["jinpohaeyanggongwon"]),
                        art("ab-news-2", "2026-08-01", image="https://example.org/og.jpg")]}
    (data / "abroad.json").write_text(json.dumps(abroad, ensure_ascii=False), "utf-8")
    return State(data, "preview")


def test_home_news_ranking_on_fixed_dates(news_world):
    """Spec 1·5·8a: one rule over the data and the build date. 2026-10-10: the dish festival runs, so its card leads;
    2026-10-13: no dish festival, the exhibition (10.2–10.31) is among the running events; 2026-11-01: the October
    editions are over and none of them is a card. The chip is a date that stays true on any day (site.js turns it into
    the reader's day)."""
    S = news_world
    n10 = _check_news(S, "2026-10-10")
    assert n10[0]["kind"] == "festival" and "짬뽕" in n10[0]["title"] and n10[0]["status"] == "10월 11일까지"
    assert n10[0]["chip"] == "축제" and n10[0]["href"].startswith("/events/")
    n13 = _check_news(S, "2026-10-13")
    assert "festival" not in [c["kind"] for c in n13]
    run = next(c for c in n13 if c["key"] == "ev:" + NEWS_RUN)
    assert run["kind"] == "event" and run["status"] == "10월 31일까지" and run["when"] == "10. 2.–10. 31."
    place = next(e for e in S.entities if e["name"] == "진포해양공원")
    if n13.index(run) and place["_photos"]:     # the first slide takes a light KOGL-1 photo only (the LCP)
        assert run["photo"]["place"] == "진포해양공원"
    assert [c["chip"] for c in n13 if c["kind"] == "abroad"][0] == f"해외에서 본 {S.city.region}"
    n11 = _check_news(S, "2026-11-01")
    assert not any(c["key"] in ("ev:" + NEWS_RUN, "ev:" + MUSEUM_EV) for c in n11)
    assert not any(c["kind"] == "event" for c in n11)


def test_an_end_given_only_as_a_month_is_never_shown_as_its_last_day(news_world):
    """QA 2026-10-15 SRC-06: the museum's weekend programme runs '2026. 6. 6. ~ 10월' — the source gives no end day.
    The month's last day (build.event_last_day) only sorts and splits upcoming / past: the chip, the big date, the home
    card and the event page say '10월', never '10.31.'; the page asks for the end day; JSON-LD has no endDate. The
    exhibition (end_date 2026-10-31 in its source) keeps its day."""
    from pipeline.build import event_end_month, event_last_day
    S = news_world
    saved = S.today
    try:
        S.today = "2026-10-13"
        ev = next(x for x in S.events if x.get("id") == MUSEUM_EV)
        assert event_end_month(ev) == "2026-10" and event_last_day(ev) == "2026-10-31"
        r = next(x for x in present.ranked_events(S) if x["ev"] is ev)
        assert r["chip"] == "10월 중 끝남"
        assert r["dp"]["b"] is None and r["dp"]["end_month"] == "10"
        card = next(c for c in present.home_news(S) if c["key"] == "ev:" + MUSEUM_EV)
        assert card["status"] == "10월 중 끝남" and card["when"] == "6. 6.–10월"
        assert "10.31" not in json.dumps(card, ensure_ascii=False, default=str)
        assert "10. 31." not in json.dumps(card, ensure_ascii=False, default=str)
        sr = next(x for x in S.series if x["newest"] is ev)
        vm = present.event_vm(S, sr)
        assert vm["need"][0] == "끝나는 날" and vm["chip"] == "10월 중 끝남" and vm["dp"]["b"] is None
        assert "endDate" not in json.dumps(jsonld.event_graph(ev, "https://x/events/a/", [], S.site), default=str)
        # an end day the source gives stays a day
        y = next(x for x in present.ranked_events(S) if x["ev"].get("id") == NEWS_RUN)
        assert y["chip"] == "10월 31일까지" and y["dp"]["b"]["md"] == "10. 31."
        assert "끝나는 날" not in present.event_vm(S, next(x for x in S.series if x["newest"] is y["ev"]))["need"]
    finally:
        S.today = saved


def test_event_places_split_the_place_name_and_match_contentid(S):
    """Spec 8a: '군산회관, 진포해양공원' (a string, no contentid) finds 진포해양공원 by name; a TourAPI contentid finds its
    place; the city's own prefix (City.strip_city_prefix), brackets and a trailing 일원 are dropped."""
    place = next(e for e in S.entities if e["name"] == "진포해양공원")
    assert present.event_places(S, {"place_name": "군산회관, 진포해양공원"}) == [place]
    assert present.event_places(S, {"place_name": f"전북특별자치도 군산시 {place['name']}(장미동) 일원"}) == [place]
    cid, by_cid = next(iter(S.ent_by_cid.items()))
    assert present.event_places(S, {"place_name": "", "contentid": cid}) == [by_cid]
    assert present.event_places(S, {"place_name": "어딘가 없는 곳"}) == []


def test_home_news_pictures_are_allowed_ones(news_world):
    """Spec 1·5: a card's picture is a licensed TourAPI photo of an attraction it is about (KOGL-1/3, never a
    business's), an /abroad/ article's own preview image on that article's card, or the kind's AI picture; a video
    card never shows a YouTube thumbnail; no photo is shown twice."""
    from pipeline.validate import TOURAPI_IMAGE_HOSTS
    S = news_world
    saved = S.today
    by_name = {e["name"]: e for e in S.entities}
    images = {a["id"]: a.get("image") for a in S.abroad}
    try:
        for day in ("2026-10-10", "2026-10-13", "2026-11-01"):
            S.today = day
            shown = []
            for c in present.home_news(S):
                ph = c["photo"]
                if ph:
                    e = by_name[ph["place"]]
                    assert e["kind"] == "attraction" and ph["type"] in (1, 3)
                    assert ph["url"].startswith(TOURAPI_IMAGE_HOSTS) and ph["url"] in [p["url"] for p in e["_photos"]]
                    shown.append(ph["url"])
                if c["og"]:
                    assert c["kind"] == "abroad" and not ph and c["og"] == images[c["key"][3:]]
                    assert c["og"].startswith("https://") and c["outlet"]
                if c["art"]:
                    assert not (ph or c["og"])
                    kind = (f"events.kind.{c['ev_kind']}",) if c["kind"] in ("event", "festival") else ()   # K
                    assert c["art"]["slot"] in (f"home.card.{c['kind']}", "home.card.event", "home.card.festival-jjamppong",
                                                *kind)
                if c["kind"] == "video":
                    assert not (ph or c["og"])
            assert len(shown) == len(set(shown)), day
    finally:
        S.today = saved


# The homes' opening (UI4) on a copy of the fixture with the English version (tests/fixtures/en_min), the question
# card's starters (ask.json), a KOGL-1 cover photo, the 'getting there' guide (site.json home.getting_here), one video
# and one /abroad/ article — the subset alone has none of them. City words come from its site.json.
@pytest.fixture(scope="module")
def home_world(tmp_path_factory):
    from tests.fixtures.build_en_min import overlay
    tmp = tmp_path_factory.mktemp("home")
    data = tmp / "data"
    shutil.copytree(DATA, data)
    overlay(data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["home"]["media"]["cover"] = ["gunsan-305372", 0]   # 은파호수공원's first photo: KOGL-1
    site["home"]["getting_here"] = {"label": "가는 법", "guide_id": "guide-13"}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    q = lambda ko, en: {"ko": ko, "en": en}  # noqa: E731
    ask = {"starters": [{"q": q("메뉴별 맛집은 어디인가요?", "Restaurants by dish"), "guide": "guide-13"},
                        {"q": q("아이와 갈 만한 곳", "Places for children"), "guide": "guide-02"},
                        {"q": q("비 오는 날 갈 곳", "Places for a rainy day"), "guide": "guide-03"},
                        {"q": q("이번 달 행사·축제", "Events this month"), "page": "events"}]}
    (data / "ask.json").write_text(json.dumps(ask, ensure_ascii=False), "utf-8")
    video = {"youtube_id": "aaaaaaaaaaa", "title": "[샘플] 항구 영상", "channel": "[샘플] 채널", "channel_kind": "official",
             "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "published_date": "2026-09-01", "topics": ["기타"],
             "lang": "ko", "checked_at": "2026-10-11", "verified_by": "YouTube oEmbed", "place_slugs": []}
    (data / "videos.json").write_text(json.dumps([video], ensure_ascii=False), "utf-8")
    abroad = {"items": [{"id": "ab-home-1", "kind": "article", "status": "published", "url": "https://example.org/a",
                         "note": "[샘플] 우리가 쓴 한 줄 소개", "outlet": "Example Times", "title": "[샘플] Harbour city",
                         "date": "2026-09-01", "lang": "en", "checked_at": "2026-10-01", "source_type": "press"}]}
    (data / "abroad.json").write_text(json.dumps(abroad, ensure_ascii=False), "utf-8")
    out = tmp / "preview"
    build(data, out, "preview")
    return State(data, "preview"), out


def test_home_opening_markup_carousel_and_links(home_world):
    """UI4 (owner 2026-10-14, '참고 사이트처럼 밝게'): the Korean home opens LIGHT — no full-bleed photo, no scrim. The
    opening holds the eyebrow pill, the H1, one lede, the sea pill button and the slide controls (the pause button
    first, previous / next, the counter 'n / N' not live while it turns, the progress line, '소식 전체'), and at the
    right one big card per news item (present.home_news): a labelled carousel of groups 'i / N', each with exactly one
    working link and an allowed picture with its credit (an illustration: alt only, no label). The first slide's photo
    is eager, high priority and preloaded; the others lazy. Then the white card, the AI assistant only (owner
    2026-10-14: '페이지 상단에는 검색, 중앙 부분에는 AI챗봇'): its heading, one GET form to /search/ (without JS it
    searches) with ONE button '물어보기' and no '검색', the starter questions as '#' tags linking to pages of this
    build, and the 3D icon menu of the service links (no 물어보기 item: the card above it is the assistant; pictures by
    registry ID); the conversation panel right after the card, empty and hidden. The site search is the header's: a
    GET form to /search/ in the bar, and no '물어보기' button in the bar."""
    from urllib.parse import unquote
    S, built = home_world
    region = S.city.region
    html = (built / "index.html").read_text("utf-8")
    # the big title (2026-10-16, as 군산각·해남각): '<region> 여행의 모든 것', the site's name only without a region
    title = f"{region} 여행의 모든 것" if region else S.site["site_name"]
    assert re.search(rf'<h1 id="h-home" class="op-h1 hk-h1">{re.escape(title)}</h1>', html)
    start = html.index('<div class="hk" data-chat-dock>')
    top = html[start:html.index('<section class="sec ', start)]
    opening = top[:top.index('<section class="hq"')]
    # owner 2026-10-14 ('고화질 실사 배경'): the official KOGL-1 cover photo (site.json home.media.cover) behind the
    # opening (cropping allowed), credited — once it has its AVIF derivatives (tools/kogl1_media.py); without them (the
    # fixture's photo) the opening keeps its soft gradient and names no photo
    cover = present.media.slot_photos(S)["cover"]
    ph = bool(cover and cover["type"] == 1 and cover.get("avif"))
    assert re.match(rf'<div class="hk" data-chat-dock>\s*<section class="ho{" ho-ph" if ph else ""}" aria-labelledby="h-home">',
                    opening)
    assert "hx-ph" not in opening and "hk-open" not in opening and "rgba(4, 9, 16" not in html
    if ph:
        bg = opening[opening.index('<div class="ho-bg" aria-hidden="true">'):]
        assert 'data-kogl="1"' in bg.split("</div>", 1)[0] and 'class="ho-cap"' in opening and "공공누리 제1유형" in opening
    else:
        assert 'class="ho-bg"' not in opening
    assert '<p class="ho-k"><span class="ho-dot" aria-hidden="true"></span>' in opening
    assert 'href="/courses/" data-track="course_click">' in opening
    # the carousel: the box holds the controls and the cards
    assert re.search(rf'<div class="wrap ho-in" data-hcar aria-roledescription="carousel" aria-label="지금 {re.escape(region)} 소식">',
                     opening)
    n = opening.count('aria-roledescription="slide"')
    assert present.NEWS_MIN <= n <= present.NEWS_MAX
    assert re.findall(r'role="group" aria-roledescription="slide" aria-label="(\d+) / (\d+)"', opening) == \
        [(str(i), str(n)) for i in range(1, n + 1)]
    ctl = opening[opening.index('<div class="ho-ctl">'):opening.index('<div class="ho-news">')]
    buttons = re.findall(r"<button [^>]*>", ctl)
    assert len(buttons) == 3 and "data-hcar-pause" in buttons[0] and 'aria-label="소식 자동 넘김 멈추기"' in buttons[0]
    assert 'data-hcar-dir="-1" aria-controls="hv-track" aria-label="이전 소식"' in buttons[1]
    assert 'data-hcar-dir="1" aria-controls="hv-track" aria-label="다음 소식"' in buttons[2]
    assert f'data-hcar-count aria-live="off"><span class="vh">소식 </span><span data-hcar-cur>1</span> / {n}</p>' in ctl
    assert '<i data-hcar-prog></i>' in ctl and '<a class="ho-all" href="/events/">' in ctl
    news = opening[opening.index('<div class="ho-news">'):]
    news = news.split('<p class="ho-cap">', 1)[0]    # the cover photo's credit line follows the cards
    assert not re.search(r'<link rel="preload" as="image" href="https?://', html[:html.index("</head>")])   # no outside photo
    assert 'aria-live="polite"' not in news and 'id="hv-track"' in news
    for i, card in enumerate(news.split('<article class="nc nc-')[1:]):
        links = re.findall(r'<a href="([^"]+)"([^>]*)>', card)
        assert len(links) == 1, card[:120]
        href, attrs = links[0]
        if href.startswith("/"):
            assert (built / unquote(href).strip("/") / "index.html").exists(), href
        else:
            assert href.startswith("https://") and 'rel="noopener"' in attrs, href
        for img in re.findall(r"<img [^>]*>", card):
            src = re.search(r' src="([^"]+)"', img).group(1)
            if src.startswith("/assets/art/") and i == 0:    # a first slide without a light photo: its picture, preloaded
                head = html[:html.index("</head>")]
                pre = re.findall(r'<link rel="preload" as="image"[^>]*>', head)
                assert 'alt="일러스트: ' in img and 'fetchpriority="high"' in img and 'loading="lazy"' not in img
                arts = [x for x in pre if 'imagesrcset="/assets/art/' in x]
                assert len(arts) == 1 and 'type="image/avif"' in arts[0], pre
                # the other one: the opening's KOGL-1 cover photo (owner 2026-10-14), a local derivative
                assert all('imagesrcset="/assets/media/' in x for x in pre if x not in arts) and len(pre) <= 2, pre
                continue
            if src.startswith("/assets/art/"):    # the card kind's picture; an event's may be its event kind's (K)
                kind_art = card.startswith(("event", "festival")) and 'data-art="evkind-' in card
                assert ('data-art="card-' in card or kind_art) and 'alt="일러스트: ' in img
                assert "AI 생성 이미지" not in card and "<figcaption" not in card   # owner 2026-10-13: no label
            elif 'class="nc-og"' in img:
                assert card.startswith("abroad") and "미리보기 이미지</p>" in card
                assert 'referrerpolicy="no-referrer"' in img and 'alt=""' in img
            elif src.startswith("/assets/icons/"):
                assert 'alt=""' in img
            else:
                assert src.startswith("https://tong.visitkorea.or.kr/") and "출처: 한국관광공사" in card
                if i == 0:     # the first slide's photo: the LCP candidate on wide screens
                    assert 'loading="eager"' in img and 'fetchpriority="high"' in img
                    # light and local (review 2026-10-14: a KOGL-3 original first made the home's LCP 5.8 s): a
                    # KOGL-1 photo whose same-origin AVIF derivative is preloaded; no outside photo is preloaded
                    assert card.split(">", 1)[0] and 'class="nc-frame t1"' in card, card[:200]
                    head = html[:html.index("</head>")]
                    pre = re.findall(r'<link rel="preload" as="image"[^>]*>', head)
                    assert len(pre) == 1 and 'type="image/avif"' in pre[0], pre
                    assert re.search(r'imagesrcset="/assets/[^"]+\.avif \d+w', pre[0]), pre
                    continue
            assert 'loading="lazy"' in img and "width=" in img and "height=" in img
    card = top[top.index('<section class="hq"'):]
    assert card.startswith('<section class="hq" aria-labelledby="h-ask">')
    assert f'<h2 id="h-ask" class="hk-h"><span class="hk-hn">{region} 여행 도우미에게</span> 물어보세요</h2>' in card
    form = card[card.index('<form class="hk-box"'):card.index("</form>")]
    assert form.startswith('<form class="hk-box" action="/search/" method="get" data-ask-form="search" data-empty="')
    assert 'id="ask-q" name="q"' in form and 'maxlength="800"' in form and 'data-ask-q' in form
    buttons = re.findall(r"<button [^>]*>", form)
    assert buttons == ['<button type="submit" class="ask-go hk-go" data-ask-go>']   # one button, no '검색'
    assert '<span class="ask-go-l">물어보기</span><span class="ask-go-l ask-go-s">멈추기</span>' in form
    assert "data-ask-search" not in html and "formaction" not in card
    # the header: the site search (a GET form to /search/), no '물어보기' button in the bar
    mast = html[html.index('<header class="mast"'):html.index("</header>")]
    assert '<form class="hs" id="hs" action="/search/" method="get" role="search" data-hs>' in mast
    assert 'placeholder="장소·음식·지역 검색"' in mast and 'name="q" type="search"' in mast
    assert '<a class="mast-search" href="/search/" data-hs-open>' in mast
    assert "data-chat-open" not in mast and "mast-ask" not in mast and "물어보기" not in mast
    chips = re.findall(r'<a class="hk-pill" href="([^"]+)" data-ask="([^"]+)">', card)
    assert 3 <= len(chips) <= 5
    for href, q in chips:
        assert (built / unquote(href).strip("/") / "index.html").exists(), href
    assert 'class="hk-mascot"' in card and 'alt=""' in card.split('class="hk-mascot"', 1)[1][:400]
    # the 3D icon menu: every service link, each with its picture ID — no '물어보기' item (the card above is the
    # assistant, and the launcher is on screen too)
    menu = card[card.index('<nav class="hq-menu"'):card.index("</nav>")]
    assert "data-chat-open" not in menu and "icon-ask" not in menu and "<button" not in menu
    for href, pid in (("/food/", "icon-food"), ("/stays/", "icon-stay"), ("/places/", "icon-sights"),
                      ("/courses/", "icon-course"), ("/events/", "icon-events"), ("/map/", "icon-map"),
                      ("/videos/", "icon-video"), ("/abroad/", "icon-abroad")):
        assert re.search(rf'<a class="hq-i" href="{href}"[^>]*><span class="pic [^"]*" data-pic="{pid}"', menu), href
    services = present.home_services(S)
    assert menu.count("<li ") == len(services)
    assert '<a class="hq-i" href="/guides/' in menu and 'data-pic="icon-getting-here"' in menu
    # operator 2026-10-15: the core four lead (one row of four tiles on phones, css/46-home-open.css), then the rest
    labels = re.findall(r'<span class="hq-l">([^<]+)</span>', menu)
    assert labels == [s["label"] for s in services]
    assert labels[:4] == ["가볼만한 곳", "맛집", "숙소", "가는 법"]
    assert labels[4:] == ["코스", "지도", "행사 달력", "영상", f"해외에서 본 {region}"]
    assert re.findall(r'<li class="(hq-core|hq-more)">', menu) == ["hq-core"] * 4 + ["hq-more"] * 5
    assert '<ul class="hq-row" style="--core:4">' in menu
    # the conversation: right after the card, hidden and empty until the reader asks (chat.js draws into it)
    rest = card[card.index("</section>") + len("</section>"):]
    assert rest.startswith('\n<div class="wrap hk-conv"><div class="ask-log ask-panel" data-ask-log hidden '
                           'data-ask-more="이어서 물어보기" data-note="AI가 이 사이트의 정보로 쓴 답입니다. 틀릴 수 있으니 '
                           '방문 전에 확인하세요."')
    assert "AI 생성 이미지" not in html and 'class="hv ' not in html and "hv-top" not in html and 'class="svc' not in html


def test_english_home_takes_the_korean_opening(home_world):
    """Owner 2026-10-14 ('외국어 사이트들은 UI UX가 아직 업데이트가 안 됐네'): the English home opens as the Korean one —
    media.HOME_COVER full-bleed under its scrim with its credit, the H1, the course button, the news cards (this
    version's events and guides, Pages.home_news) and the white card with the assistant and the icon menu, all in
    English; the old light opening (.hx) and its see-through masthead rules are gone."""
    S, built = home_world
    en = (built / "en" / "index.html").read_text("utf-8")
    cover = present.media.slot_photos(S)["cover"]   # site.json home.media.cover: a KOGL-1 photo (cropped full-bleed)
    assert cover and cover["type"] == 1
    assert '<body data-page-kind="home" class="pg-home pg-intl-home pg-h4 has-ask">' in en
    assert '<section class="ho ho-ph" aria-labelledby="h-home">' in en and f'src="{cover["url"]}"' in en
    # the cover is preloaded when it has its same-origin AVIF derivatives (tools/kogl1_media.py; the fixture's has none)
    assert ('rel="preload" as="image" type="image/avif"' in en) == bool(cover.get("avif"))
    assert "Start with an official course" in en
    assert '<p class="ho-cap">Photo: ' in en and 'class="hx' not in en
    top = en[en.index('<div class="hk" data-chat-dock>'):en.index('<section class="sec ')]
    cards = re.findall(r'<article class="nc nc-(\w+)"', top)
    # this version's cards only: en_min translates one guide and its events are past — one guide card
    assert cards == ["guide"] and set(cards) <= {"festival", "event", "guide"}
    for href in re.findall(r'<h3 class="nc-t"><a href="([^"]+)"', top):
        assert href.startswith("/en/"), href
    assert "data-hcar" in top and '<nav class="hq-menu"' in top and not re.search(r"[가-힣]", top)
    # operator 2026-10-15: the core four lead the menu as on the Korean home — attractions, restaurants, stays and
    # the 'getting there' guide (its long label has a short one for phones) — then courses, events, guides
    menu = top[top.index('<nav class="hq-menu"'):]
    menu = menu[:menu.index("</nav>")]
    items = re.findall(r'<li class="(hq-core|hq-more)"><a class="hq-i" href="([^"]+)"', menu)
    assert [c for c, _ in items] == ["hq-core"] * 4 + ["hq-more"] * (len(items) - 4)
    assert [h for _, h in items][:3] == ["/en/places/", "/en/food/", "/en/stays/"]
    assert items[3][1].startswith("/en/guides/") and [h for _, h in items][4:] == ["/en/courses/", "/en/events/",
                                                                                      "/en/guides/"]
    # the long label is the city's own (the first city: 'Getting to Gunsan and around'), the short one for phones fixed
    assert re.search(r'<span class="hq-l"><span class="hq-lw">[^<]+</span><span class="hq-ls">Getting here</span></span>',
                     menu)
    css = (built / "assets" / "style.css").read_text("utf-8")
    assert ".pg-en-home" not in css and "html:not(.is-scrolled) .pg-home .mast{" not in css


def test_homes_ask_in_place(home_world):
    """Owner 2026-10-13: ask the site assistant from the home itself. The Korean home asks from its question card (UI4,
    owner 2026-10-14: the white card under the light opening) — one dock (data-chat-dock on the home's top), the box in
    the card, the conversation panel right under it, no centre card; the English home the same (owner 2026-10-14).
    Every starter links to a page of this build, in the page's language."""
    from urllib.parse import unquote
    S, built = home_world
    ko = (built / "index.html").read_text("utf-8")
    assert ko.count("data-chat-dock") == 1 and '<div class="hk" data-chat-dock>' in ko
    assert '<section class="ask' not in ko and 'class="ask-card"' not in ko
    start = ko.index('<div class="hk" data-chat-dock>')
    top = ko[start:ko.index('<section class="sec ', start)]
    assert top.index('<section class="ho') < top.index('data-hcar-item') < top.index('<section class="hq"') \
        < top.index('<form class="hk-box"') < top.index('<nav class="hq-menu"') < top.index("data-ask-log")
    en = (built / "en" / "index.html").read_text("utf-8")
    # owner 2026-10-14: the English home asks from the same white card (_ask.html.j2 box_intl): no search page in
    # English, so its form shows with JS only (data-js-only); no centre card any more
    assert en.count("data-chat-dock") == 1 and '<div class="hk" data-chat-dock>' in en and 'class="ask-card"' not in en
    start = en.index('<div class="hk" data-chat-dock>')
    en_top = en[start:en.index('<section class="sec ', start)]
    assert en_top.index('<section class="ho') < en_top.index('<section class="hq"') \
        < en_top.index('<form class="hk-box" method="get" data-ask-form data-js-only data-empty="') \
        < en_top.index('<nav class="hq-menu"') < en_top.index("data-ask-log")
    assert f"Ask the {S.city.region_en} travel helper" in en_top and not re.search(r"[가-힣]", en_top)
    # the world's four starters on the Korean home; the English one has the two whose page is translated there
    # (en_min: the food hub guide and /en/events/)
    for html, prefix, n in ((top, "/", 4), (en_top, "/en/", 2)):
        chips = re.findall(r'<a class="hk-pill" href="([^"]+)" data-ask="([^"]+)">', html)
        assert len(chips) == n, prefix
        for href, q in chips:
            assert href.startswith(prefix) and (built / unquote(href).strip("/") / "index.html").exists(), href


def test_home_news_row_turns_by_itself_and_stops_for_the_reader(built):
    """UI4 in a browser (Playwright + Chromium; the build is served through page.route, nothing leaves the
    machine): exactly one news card is in view at a time — at 1440 at the right of the opening's text, in the first
    screen, and at 390 under the H1 and above the question box, which is in the first screen at both sizes; the row
    advances by itself, a control press stops it (the play button
    restarts it, the counter is live only while stopped), focus inside stops it; with reduced motion there is no
    autoplay and no pause button; without JS the controls are hidden, one card is still in view, the cards still
    scroll and the question box searches."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            def open_home(width=1440, height=900, **kw):
                ctx = browser.new_context(viewport={"width": width, "height": height}, **kw)
                ctx.route("**/*", serve)
                page = ctx.new_page()
                page.goto("http://site.test/", wait_until="load")
                return ctx, page
            in_view = """(() => { const v = document.querySelector('[data-hcar-view]').getBoundingClientRect();
              return [...document.querySelectorAll('[data-hcar-item]')].filter(c => { const r = c.getBoundingClientRect();
                return r.right > v.left + 1 && r.left < v.right - 1 && r.width > 0; }).length; })()"""
            in_screen = """(sel => { const r = document.querySelector(sel).getBoundingClientRect();
              return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; })"""
            ctx, page = open_home(390, 844)                          # phones: H1, the question card, then the news card
            assert page.evaluate(in_view) == 1
            assert page.evaluate("document.querySelector('.hk-h1').getBoundingClientRect().bottom <= "
                                 "document.querySelector('.hk-box').getBoundingClientRect().top")
            assert page.evaluate("document.querySelector('.hq-card').getBoundingClientRect().bottom <= "
                                 "document.querySelector('[data-hcar-view]').getBoundingClientRect().top")
            assert page.evaluate(in_screen + "('.hk-box')")         # the question box in the 390x844 first screen
            # operator 2026-10-15: the course button under the lede, one compact card (a row, its frame at the
            # left), the '#' tags in the first screen too; the row waits on its first card (no autoplay below 768px)
            assert page.evaluate(in_screen + "('.ho-cta a')") and page.evaluate(in_screen + "('.hk-pills')")
            assert page.evaluate("document.querySelector('.ho-lede').getBoundingClientRect().bottom <= "
                                 "document.querySelector('.ho-cta a').getBoundingClientRect().top")
            assert page.evaluate("document.querySelector('[data-hcar-view]').getBoundingClientRect().height") < 200
            assert page.evaluate("(() => { const f = document.querySelector('[data-hcar-item] .nc-frame')"
                                 ".getBoundingClientRect(), t = document.querySelector('[data-hcar-item] .nc-t')"
                                 ".getBoundingClientRect(); return f.width <= 96 && f.right <= t.left; })()")
            assert "is-stopped" in page.get_attribute("[data-hcar]", "class")
            assert page.get_attribute("[data-hcar-pause]", "aria-label") == "소식 자동 넘김 시작"
            assert page.text_content("[data-hcar-cur]") == "1"
            ctx.close()
            ctx, page = open_home()
            box, cur = "[data-hcar]", "[data-hcar-cur]"
            # 1440: the card at the right of the opening's text, inside the first screen, one card in view; the
            # question box in the first screen too, the white card overlapping the opening's bottom edge
            card = page.locator(".ho-news").bounding_box()
            text = page.locator(".hk-h1").bounding_box()
            assert card["x"] >= text["x"] + text["width"] and card["y"] >= 0 and card["y"] + card["height"] <= 900
            assert page.evaluate(in_screen + "('.hk-box')")
            assert page.evaluate("document.querySelector('.hq-card').getBoundingClientRect().top < "
                                 "document.querySelector('.ho').getBoundingClientRect().bottom")
            assert page.evaluate(in_view) == 1
            assert page.text_content(cur) == "1"
            assert page.get_attribute("[data-hcar-pause]", "aria-label") == "소식 자동 넘김 멈추기"
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "off"
            page.wait_for_function("document.querySelector('[data-hcar-cur]').textContent === '2'", timeout=10000)
            page.wait_for_timeout(900)                               # let the smooth scroll settle
            assert page.evaluate(in_view) == 1                       # one card again, the next one
            page.click('[data-hcar-dir="1"]')                       # a control press: one on, autoplay stops
            page.wait_for_function("document.querySelector('[data-hcar-cur]').textContent === '3'", timeout=4000)
            assert "is-stopped" in page.get_attribute(box, "class")
            assert page.get_attribute("[data-hcar-pause]", "aria-label") == "소식 자동 넘김 시작"
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "polite"
            page.click("[data-hcar-pause]")                          # play again
            assert "is-stopped" not in page.get_attribute(box, "class")
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "off"
            page.focus(".nc-t a")                                     # focus inside: stops for good
            assert "is-stopped" in page.get_attribute(box, "class")
            ctx.close()
            ctx, page = open_home(reduced_motion="reduce")
            assert page.locator("[data-hcar-pause]").count() == 0 and "is-stopped" in page.get_attribute(box, "class")
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "polite"
            ctx.close()
            ctx, page = open_home(java_script_enabled=False)
            assert not page.is_visible(".hv-ctl") and page.evaluate(in_view) == 1
            assert page.evaluate("(() => { const v = document.querySelector('[data-hcar-view]');"
                                 " return v.scrollWidth > v.clientWidth; })()")
            # without JS the question box searches
            page.fill("#ask-q", "선유도")
            page.press("#ask-q", "Enter")
            page.wait_for_url("**/search/?q=*")
            ctx.close()
        finally:
            browser.close()


def test_launcher_and_quick_menu_are_there_at_load(built_en):
    """Owner 2026-10-14 ('첫 화면부터 우측 하단에 챗봇 잘 보이게 해주고. 지금은 스크롤 해야만 보이거든'): at load, without
    scrolling, the mascot launcher is visible at the bottom right — fully on screen, opaque, on top (the point at its
    centre is the launcher) — on the home, a place page and /en/, at 390×844 and 1440×900. On the Korean pages from
    1024px the floating quick menu sits above it (44px targets with their names; on a place page its third item is
    길찾기, the page's own block); phones show only the launcher; /en/ has no quick menu. No layout shift while the home
    loads (fonts cached, as on any second page), no console errors, and no 'AI 생성 이미지' anywhere on screen.
    Operator 2026-10-15: on the homes below 1024px the launcher steps aside while their own question box is on screen
    (hidden, out of the tab order) and is there as above once the box has left the screen."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built_en / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    shifts = """window.__ls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput)
      window.__ls.push(e.value); }).observe({type: 'layout-shift', buffered: true});"""
    fab_ok = """(() => { const b = document.querySelector('.chat-fab'), r = b.getBoundingClientRect(), cs = getComputedStyle(b);
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return r.width >= 54 && r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth
        && r.right > innerWidth - 60 && r.bottom > innerHeight - 60 && cs.visibility === 'visible' && cs.opacity === '1'
        && b.contains(hit); })()"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            for w, h in ((390, 844), (1440, 900)):
                for path in ("/", "/places/binhaewon/", "/en/"):   # a place of the subset (빈해원)
                    ctx = browser.new_context(viewport={"width": w, "height": h})
                    ctx.route("**/*", serve)
                    page = ctx.new_page()
                    errors = []
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script(shifts)
                    page.goto("http://site.test/about/", wait_until="load")
                    page.evaluate("document.fonts.ready.then(() => 1)")
                    page.goto("http://site.test" + path, wait_until="load")
                    page.wait_for_timeout(300)
                    assert page.evaluate("window.scrollY") == 0
                    qm = page.locator(".qm")
                    if path in ("/", "/en/"):
                        # on the homes the launcher (and quick menu from 1024px) steps aside while the page's own
                        # question box is on screen — out of the tab order and the pointer's way — and comes back
                        # once the box has left the screen
                        fab_style = "getComputedStyle(document.querySelector('.chat-fab'))"
                        assert page.evaluate(fab_style + ".visibility") == "hidden", (w, path)
                        assert page.evaluate(fab_style + ".pointerEvents") == "none", (w, path)
                        assert qm.count() == 0 or not qm.is_visible(), (w, path)
                        page.evaluate("window.scrollTo(0, document.querySelector('[data-ask-zone]')"
                                      ".getBoundingClientRect().bottom + scrollY + 40)")
                        page.wait_for_function("document.documentElement.classList.contains('ask-out')", timeout=3000)
                        page.wait_for_timeout(400)                         # the fade
                        assert page.evaluate(fab_ok), (w, path)
                    else:
                        assert page.evaluate(fab_ok), (w, path)
                    if path == "/en/" or w < 1024:
                        assert qm.count() == 0 or not qm.is_visible(), (w, path)
                    else:
                        assert qm.is_visible(), (w, path)
                        items = page.locator(".qm-i")
                        names = [items.nth(i).get_attribute("aria-label") for i in range(items.count())]
                        assert names[0] == "검색" and names[1] == "지도" and names[-1] == "맨 위로"
                        assert names[2] == ("길찾기" if path.startswith("/places/") else "행사 달력")
                        for i in range(items.count()):
                            bb = items.nth(i).bounding_box()
                            assert bb["width"] >= 44 and bb["height"] >= 44
                        q, f = qm.bounding_box(), page.locator(".chat-fab").bounding_box()
                        assert q["y"] + q["height"] <= f["y"]                     # above the launcher
                        if path.startswith("/places/"):
                            assert page.locator("#h-dir").count() == 1
                    if path in ("/", "/en/"):
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_function("!document.documentElement.classList.contains('ask-out')", timeout=3000)
                    if path == "/":
                        assert page.evaluate("window.__ls") == [], w           # nothing shifts while the home loads
                    assert "AI 생성 이미지" not in page.inner_text("body")
                    assert [e for e in errors if "ERR_FAILED" not in e] == [], (w, path, errors)
                    ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ events, photos
def test_events_split_upcoming_past_and_undated(S):
    ev = present.events_vm(S)
    assert ev["n_records"] == len(S.events) == 7 and ev["n_series"] == len(S.series) == 2
    assert all(r["last"] >= S.today for r in ev["upcoming"]) and all(r["last"] < S.today for r in ev["past"])
    assert all("매년" in r["period_text"] for r in ev["annual"])
    assert len(ev["upcoming"]) + len(ev["past"]) + len(ev["annual"]) + len(ev["textonly"]) + len(ev["past_undated"]) \
        == len(S.events)
    assert [r["ev"]["id"] for r in ev["annual"]] == ["event-fixture-4"]
    assert [r["ev"]["id"] for r in ev["past_undated"]] == ["event-fixture-6"]
    assert [r["ev"]["id"] for r in ev["textonly"]] == ["event-fixture-5"]
    assert next(r for r in ev["past"] if r["ev"]["id"] == "event-fixture-7")["text_dated"]
    sr = next(s for s in S.series if any(x.get("alternatives") for x in s["editions"] if x is s["newest"]))
    vm = present.event_vm(S, sr)
    assert vm["confirm_line"] == "방문 전 주최 측 확인" and any(r["flag"] for r in vm["rows"])
    flagged = next(r for r in vm["rows"] if r["flag"])
    assert len(flagged["blocks"]) >= 2 and all(b["provider"] for b in flagged["blocks"])


def test_event_place_and_kicker_lose_only_the_city_prefix(S):
    """The event's place name loses the city's own prefix (City.strip_city_prefix), the kicker reads the address line
    (City.place_line), the map search the city's short name (City.map_query_prefix)."""
    sr = next(s for s in S.series if s["newest"]["id"] == "event-fixture-1")
    vm = present.event_vm(S, sr)
    assert vm["place_short"] == "[샘플] 호수공원 일원"
    assert vm["place_label"] == f"{city.of(S.site).locality} 나운동"
    assert vm["front"][0]["url"].endswith("/" + quote(f"{S.site['region']} [샘플] 호수공원 일원", safe=""))
    row = next(r for r in present.events_vm(S)["past"] if r["ev"]["id"] == "event-fixture-7")
    assert row["place"] == "[샘플] 강변 무대"


def test_every_licensed_photo_has_its_measured_size(S):
    sizes = json.loads((DATA / "image_sizes.json").read_text("utf-8"))
    photos = [p for e in S.entities for p in e["_photos"]]
    assert photos and all(p["w"] and p["h"] and p["bytes"] for p in photos)
    assert all(sizes[p["url"]][:2] == [p["w"], p["h"]] for p in photos)
    assert all(p["type"] in (1, 3) and "_image3_1" not in p["url"] for p in photos)
    assert sum(1 for p in photos if p["th"]) > len(photos) * 0.9


def test_image_header_parser():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 940, 627) + b"\x08\x02\x00\x00\x00"
    assert image_size(png) == (940, 627)
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 626, 940) + b"\x03" + b"\x00" * 9
    assert image_size(b"\xff\xd8" + app0 + sof) == (940, 626)
    assert image_size(b"\xff\xd8" + app0) is None


# ------------------------------------------------------------------ validator row check
FACTS_PAGE = ('<section data-block="facts"><dl>'
              '<div><dt>쉬는 날</dt><dd data-key="restdate">{a}</dd></div>'
              '<div><dt>주차</dt><dd data-key="parking">{b}</dd></div></dl></section>')
CLOSED = "매주 월요일, 1월 1일, 시장이 휴관일로 정한 날"


def scan(a, b="가능"):
    p = PageScan()
    p.feed(FACTS_PAGE.format(a=a, b=b))
    return p


def old_probe(p, raw):
    return raw[:20] in " ".join(p.blocks["facts"].split())


def test_validator_row_check_is_stricter_than_the_old_prefix_probe():
    assert fact_shown(scan(CLOSED), "restdate", CLOSED)
    # line breaks, a table layout or a closed-day mark do not matter, the words and their order do
    assert fact_shown(scan("매주 월요일,<br>1월 1일, <b>시장이 휴관일로 정한 날</b>"), "restdate", CLOSED)
    cases = {"tail cut after 20 characters": scan(CLOSED[:21]),
             "shown in another row": scan("", CLOSED),
             "a word slipped in": scan(CLOSED.replace("휴관일로 정한", "휴관일로 임시로 정한")),
             "words reordered": scan("1월 1일, 매주 월요일, 시장이 휴관일로 정한 날")}
    for why, p in cases.items():
        assert not fact_shown(p, "restdate", CLOSED), why
    # the old probe (first 20 characters anywhere in the block) let the first three through
    assert all(old_probe(cases[k], CLOSED) for k in ("tail cut after 20 characters", "shown in another row",
                                                     "a word slipped in"))
    # parking compares against the displayed form, never the raw '가능요금 (무료)'
    assert fact_shown(scan("", "가능, 요금 무료"), "parking", "가능요금 (무료)")
    assert not fact_shown(scan("", "가능"), "parking", "가능요금 (무료)")


def test_preview_build_validates_with_the_row_check(S, built):
    errors, warns, _ = validate(DATA, built, "preview")
    assert errors == []
    assert not [w for w in warns if "facts." in w]
    html = page_of(built, place(S, "빈해원"))
    assert 'data-key="usetime_restdate"' in html and "10:00–21:00" in html


# ------------------------------------------------------------------ review fixes (r3-wpa review)
def row_page(key, inner):
    p = PageScan()
    p.feed(f'<section data-block="facts"><dl><div><dt>x</dt><dd data-key="{key}">{inner}</dd></div></dl></section>')
    return p


def test_row_check_keeps_symbols_and_the_whole_text():
    """Counter-examples to the first token check, which ignored every symbol: each one passed it while the old
    20-character probe failed. A symbol is a token now, and a value that prints as text must be there verbatim."""
    cases = [("usetime", "~21:00", "21:00"), ("usetime", "10:00~", "10:00"), ("discount", "단체 50%", "단체 50"),
             ("usefee", "₩3,000", "3,000"), ("expagerange", "만 3세+", "만 3세"),
             ("usefee", "성인 3,000원(청소년 2,000원)", "성인 3,000원 청소년 2,000원"),
             ("expguide", "A/B 체험", "A B 체험")]
    for key, value, page in cases:
        p = row_page(key, page)
        assert not fact_shown(p, key, value), (key, value, page)
        assert not old_probe(p, value)                   # the old probe failed these too: nothing is looser
        assert fact_shown(row_page(key, value), key, value)
    # a value inside a longer word is not shown (the old substring probe let '가능' pass in '불가능')
    assert not fact_shown(row_page("parking", "불가능"), "parking", "가능") and old_probe(row_page("parking", "불가능"), "가능")
    assert not fact_shown(row_page("parking", "불<b>가능</b>"), "parking", "가능")
    # a footnote mark right after the value does not hide it
    assert fact_shown(row_page("usetime", "09:00–18:00<sup>1</sup> — 한국관광공사"), "usetime", "09:00~18:00")
    # a value that parses into a price table may lose the layout punctuation its cells replace — nothing else
    fee = "[개별권]\n- 성인 2,000원\n- 어린이 500원"
    assert present.value_view("usefee", fee)["fees"]
    table = '<table data-form="fees"><tr><th>개별권</th></tr><tr><td>성인</td><td>2,000원</td></tr><tr><td>어린이</td><td>500원</td></tr></table>'
    assert fact_shown(row_page("usefee", table), "usefee", fee)
    assert not fact_shown(row_page("usefee", table.replace("<td>500원</td>", "")), "usefee", fee)
    # the same cells without the table mark are plain text and must match verbatim
    assert not fact_shown(row_page("usefee", table.replace(' data-form="fees"', "")), "usefee", fee)
    # a value that does not parse gets no table allowance, mark or not
    assert not fact_shown(row_page("usefee", '<table data-form="fees"><tr><td>성인 3,000원 청소년 2,000원</td></tr></table>'),
                          "usefee", "성인 3,000원(청소년 2,000원)")


def test_row_check_requires_the_full_homepage_link():
    url = "https://booking.naver.com/booking/3/bizes/60723"
    shown = display_value("homepage", url)
    assert shown == "booking.naver.com/booking"
    assert fact_shown(row_page("homepage", f'<a href="{url}">{shown}</a>'), "homepage", url)
    assert not fact_shown(row_page("homepage", shown), "homepage", url)                       # text only
    assert not fact_shown(row_page("homepage", f'<a href="https://booking.naver.com/">{shown}</a>'), "homepage", url)


def test_no_value_passes_the_row_check_that_the_old_probe_failed(S, built):
    """On every place page of the preview build, every stored value and every other source's value: a pass of
    fact_shown implies a pass of the round-2 probe (first 20 characters of the displayed value in the block)."""
    checked = 0
    for e in S.entities:
        p = PageScan()
        p.feed(page_of(built, e))
        block = " ".join(p.blocks.get("facts", "").split())
        values = list((e.get("facts") or {}).items()) + [(k, a["value"]) for k, al in (e.get("fact_alternatives") or {}).items()
                                                         for a in al or [] if a.get("value")]
        for k, v in values:
            shown = fact_shown(p, k, v)
            assert shown, (e["name"], k, v)
            assert " ".join(display_value(k, v).split())[:20] in block, (e["name"], k, v)
            checked += 1
    assert checked == 522


def test_every_dropped_character_is_caught():
    """Delete any one non-space character of a displayed value: the row check fails, except a layout mark
    (/ , : ( ) [ ] ※ -) inside a value that prints as a table."""
    from pipeline.textutil import LAYOUT, link_url
    import html as _html
    mutations = 0
    for k, v in FACT_VALUES:
        d = display_value(k, v)
        url = link_url(v) if k in ("homepage", "reservationurl") else ""
        view = present.value_view(k, v)
        table = bool(view["tt"] or view["fees"] or view["grid"])

        def page(text):
            inner = _html.escape(text).replace("\n", "<br>")
            inner = f'<a href="{_html.escape(url)}">{inner}</a>' if url else inner
            return row_page(k, f'<div data-form="t">{inner}</div>' if table else inner)
        assert fact_shown(page(d), k, v), (k, v)
        for i, ch in enumerate(d):
            cut = d[:i] + d[i + 1:]
            if ch.isspace() or " ".join(cut.split()) == " ".join(d.split()) or (table and ch in LAYOUT):
                continue
            mutations += 1
            assert not fact_shown(page(cut), k, v), (k, d, i, ch)
    assert mutations == 31567


def test_alternative_homepages_are_linked(tmp_path):
    """Another source's homepage (fact_alternatives) is linked beside the stored one, each to its own address."""
    alt = "https://booking.naver.com/booking/3/bizes/60723"

    def edit(name, rows):
        if name == "places.json":
            for p in rows:
                if p["id"] == "sample-0101":
                    p["facts"]["homepage"] = "https://www.example.com/stay-a/view/index.do"
                    p["fact_alternatives"] = {"homepage": [{"value": alt, "provider": "[샘플] 예약 안내", "relation": "also"}]}
            return rows
    data = data_copy(tmp_path, SAMPLE, edit=edit)
    out = tmp_path / "out"
    build(data, out, "sample")
    html = (out / "places" / "sample-stay-a" / "index.html").read_text("utf-8")
    assert f'href="{alt}"' in html and 'href="https://www.example.com/stay-a/view/index.do"' in html


def test_contested_phone_is_never_the_call_number(S):
    sr = next(s for s in S.series if (s["newest"].get("alternatives") or {}).get("tel"))
    vm = present.event_vm(S, sr)
    row = next(r for r in vm["rows"] if r["field"] == "tel")
    assert row["flag"] and len(row["blocks"]) == 2
    assert all('href="tel:' in str(b["html"]) for b in row["blocks"])        # both numbers, neither picked
    assert not vm["tel"] and not any(r["tel"] for r in vm["rows"])
    # a place whose phone is contested: no call number in the status line, the list cell or a flag line
    e = place(S, "빈해원")
    e2 = {**e, "fact_alternatives": {**(e.get("fact_alternatives") or {}),
                                     "infocenter": [{"value": "063-000-0000", "provider": "x"}]}}
    assert present.settled_phone(e2) == ("", "")
    assert not [x for x in present.status_items(e2, full=True) if x["key"] == "tel"]
    assert present.cell(e2, "tel")["text"] == "출처마다 다름"


def test_event_rows_do_not_settle_contested_values(S):
    ev = present.events_vm(S)
    beer = next(r for r in ev["past"] + ev["upcoming"] if r["ev"]["id"] == "event-fixture-3")
    assert beer["fee"] == "요금 출처마다 다름" and beer["place"] == "장소 출처마다 다름"
    assert set(beer["contested"]) >= {"fee", "place_name"}


def test_status_keeps_the_label_of_a_bare_open_value(S):
    texts = [x["text"] for x in present.status_items(place(S, "홍영장"))]
    assert "없음" not in texts and "휴무일 없음" in texts


def test_open_every_day_inside_the_hours_value_is_read():
    """'11:00~20:00(연중무휴)' and '10:00~21:30 / 연중무휴' are open every day, not 'no data' in the week grid."""
    for raw in ("11:00~20:00(연중무휴)", "10:00~21:30 / 연중무휴", "10:00~20:00 연중무휴"):
        text, _ = present.closed_text({"facts": {"usetime_restdate": raw}})
        assert text == "연중무휴" and present.week_closure(text)["open"]


def test_glued_weekday_closures_are_read(S):
    """'매주월요일' (no space) is a Monday closure; '공휴일 휴무' is not a Sunday ('일') closure."""
    assert present.closed_days(place(S, "군산 임피역사")) == {"월"}
    assert present.week_closure("휴무일: 매주목요일")["days"] == {"목"}
    assert present.closed_text(place(S, "복성루"))[0] == "일요일,공휴일 휴무"
    assert present.closed_days(place(S, "복성루")) == {"일"}
    g = next(x for x in S.guides if x["id"] == "guide-03")
    week = present.guide_vm(S, g)["week"]
    row = next(r for r in week["rows"] if r["name"] == "일제강점기 군산역사관")
    assert row["cells"][0] == "closed"                      # the guide says all 8 halls close on Mondays
    # a text with no weekday information is unknown in the grid, never 'open every day'
    sky = present.week_grid([place(S, "선유 스카이썬라인"), place(S, "동국사"), place(S, "근대역사박물관"),
                             place(S, "진포해양공원")])
    assert sky["rows"][0]["cells"] == ["na"] * 7


def test_monday_open_filter_needs_every_source_to_say_so(S):
    L = present.list_vm(S, "food")
    flags = {it["name"]: it["flags"]["open_mon"] for g in L["groups"] for it in g["recs"]}
    assert flags["쌍용반점"] is False          # 연중무휴 vs 둘째·넷째주 월요일 (TourAPI)
    assert flags["궁전갈치찜"] is False        # '전화문의' states no closed day
    assert flags["완주옥"] is True             # 연중무휴 vs 매주 수요일: Monday open in both
    assert flags["장국명가"] is True           # '매주일요일 휴무'


def test_guide_figure_is_never_part_of_a_compound_amount():
    g = {"body": [{"heading": "서울 센트럴시티→군산 고속버스는 2시간30분, 금호고속 운행분은 하루 23회"}], "title": "t"}
    a = present.guide_answer(g)
    assert (a["fig"], a["unit"]) == ("23", "회")


# ------------------------------------------------------------------ city values (design 3.5, 3.6)
def test_locator_and_providers_follow_the_city():
    """The locator sentence and the short provider names come from the City (site.json), not from the code."""
    metro = city.of(json.loads((METRO / "site.json").read_text("utf-8")))
    sample = city.of(json.loads((SAMPLE / "site.json").read_text("utf-8")))
    text = "한빛관은 대구광역시 중구 삼덕동1가에 있는 전시관입니다. 1930년대 창고를 고쳐 2019년에 열었습니다."
    assert present.distinct_line(text, metro.locator_rx) == "1930년대 창고를 고쳐 2019년에 열었습니다."
    assert present.distinct_line("한빛관은 중구에 있는 전시관입니다. 매주 월요일에 쉽니다.", metro.locator_rx) == "매주 월요일에 쉽니다."
    assert present.short_provider("한국관광공사 TourAPI", city=metro) == "한국관광공사"
    assert present.short_provider("대구광역시 중구 문화관광과", city=metro) == "대구광역시 중구 문화관광과"
    assert present.short_provider("군산시 문화관광", city=sample) == "군산시"
    assert present.slot_provider("공식 홈페이지", city=metro) == "공식 홈페이지"
    assert present.short_src("군산시 보도자료", city=sample) == "군산시 보도자료"
    assert present.short_src("한국관광공사 TourAPI 보도자료", city=sample) == "한국관광공사"
    assert present.short_src("행사 누리집 안내", city=metro) == "행사 누리집"
    assert present.event_place("대구광역시 중구 [샘플] 광장", city=metro) == "중구 [샘플] 광장"
    assert present.event_place("전북특별자치도 군산시 [샘플] 광장", city=sample) == "[샘플] 광장"
    assert present.frag("당일") == "day-trip" and present.frag("먼 섬") == "meon-seom"


def test_thumb_uses_the_smallest_kogl1_derivative_when_the_provider_has_no_small_copy():
    # a TourAPI photo-gallery picture (KOGL-1, 1280 px) has no provider small copy: a list row gets our 480w WebP
    base = {"url": "https://tong.visitkorea.or.kr/cms2/website/28/3587128.jpg", "w": 1280, "h": 850, "alt": "한빛군도",
            "type": 1, "webp": "/assets/media/3587128-940.webp 940w, /assets/media/3587128-480.webp 480w", "th": None}
    assert present.thumb(base) == {"url": "/assets/media/3587128-480.webp", "w": 480, "h": 319, "alt": "한빛군도",
                                   "type": 1}
    # the provider's own small copy still wins; KOGL-3 (never re-encoded) and photos without derivatives keep the original
    own = {**base, "th": {"url": "https://tong.visitkorea.or.kr/x_image3_1.jpg", "w": 160, "h": 106}}
    assert present.thumb(own)["url"] == "https://tong.visitkorea.or.kr/x_image3_1.jpg"
    assert present.thumb({**base, "type": 3})["url"] == base["url"]
    assert present.thumb({**base, "webp": ""})["url"] == base["url"]
    assert present.thumb(None) is None


# ------------------------------------------------------------------ a city's '주차 및 좌석수' with one half only
# The fixture's seat-only place is 째보식당 본점 ('40석', the city source only); the two-source conflict and the
# '좌석 100석' spelling are built from it in memory (no fixture record has them).
SEAT_ONLY = "째보식당 본점"


def test_parking_seats_part_reads_each_half():
    for raw in ("40석", "좌석 100석", "1,200석"):
        assert parking_seats_part(raw) == "seats", raw
    for raw in ("20대", "공영주차장", "불가"):
        assert parking_seats_part(raw) == "parking", raw
    for raw in ("20대/80석", "좌석 40석/ 주차 15대", "30 ~ 40대/100석", "불가능 / 70석", "전화문의", ""):
        assert parking_seats_part(raw) == "", raw


def _seat_only(S) -> list[dict]:
    out = [e for e in S.entities if parking_seats_half(e) == "seats"]
    assert SEAT_ONLY in {e["name"] for e in out}
    return out


def test_seat_only_parking_is_listed_missing_once_per_block(S):
    """A seat count alone ('40석') answers no parking question: no 주차 tile, 주차 once in each block's '확인 필요'
    line, the facts row reads 좌석, the list's 주차 cell reads '확인 필요' with '좌석 40석' under it, and neither the
    status line, the title nor the description calls the seats 주차."""
    for e in _seat_only(S):
        kf = present.key_facts(e, "hero")
        assert not [s for s in kf["slots"] if s["key"] == "parking"], e["name"]
        assert kf["missing"].count("주차") == 1, e["name"]
        assert "주차" in present.missing_keys(e)
        ctx = entity_ctx(e, S)
        assert ctx["missing"].count("주차") == 1, e["name"]
        assert [r["label"] for r in present.fact_rows(e, ["parking_seats"], present.Notes())] == ["좌석"]
        cell = present.slot_cell(e, "parking", "주차")
        assert cell["missing"] and cell["label"] == "주차" and cell["sub"].startswith("좌석 "), e["name"]
        assert not [x for x in present.status_items(e) if x["text"].startswith("주차")], e["name"]
        assert "주차" not in ctx["page"]["title"] and "주차·좌석" not in ctx["page"]["description"], e["name"]
    e = place(S, SEAT_ONLY)
    assert present.slot_cell(e, "parking", "주차")["sub"] == "좌석 40석"
    assert "좌석 40석" in [x["text"] for x in present.status_items(e)]
    spelled = {**e, "facts": {**e["facts"], "parking_seats": "좌석 100석"}}
    assert present.seats_note(spelled) == "좌석 100석"          # '좌석 100석', never '좌석 좌석 100석'


def test_combined_parking_seats_keeps_its_label(S):
    e = place(S, "쌍용반점")
    s = present.slot_value(e, "parking")
    assert (s["label"], s["main"], s["conflict"]) == ("주차·좌석", "7대/40석", False)
    assert "주차" not in present.key_facts(e, "hero")["missing"] and "주차" not in present.missing_keys(e)
    assert [r["label"] for r in present.fact_rows(e, ["parking_seats"], present.Notes())] == ["주차·좌석"]
    assert present.seats_note(e) == "" and "주차" in entity_ctx(e, S)["page"]["title"]
    # a note for the whole field stays the combined field
    assert present.slot_value(place(S, "궁전갈치찜"), "parking")["label"] == "주차·좌석"
    # a parking-only value (none in the data so far) is labelled 주차 and answers it
    one = {**e, "facts": {**e["facts"], "parking_seats": "20대"}}
    assert present.slot_value(one, "parking")["label"] == "주차" and fact_label(one, "parking_seats") == "주차"
    assert "주차" not in present.missing_keys(one)


def test_parking_seats_conflict_on_first_screen(S):
    """Two sources' '주차 및 좌석수' differ (the city source '인근 공영주차장/70석', 한국관광공사 '불가능 / 70석'): the tile and
    the list cell show both with their providers (CLAUDE.md 3.2), never the city's value alone."""
    base = place(S, SEAT_ONLY)
    e = {**base, "facts": {**base["facts"], "parking_seats": "인근 공영주차장/70석"},
         "fact_sources": {**(base.get("fact_sources") or {}),
                          "parking_seats": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"}},
         "fact_alternatives": {"parking_seats": [{"value": "불가능 / 70석", "provider": "한국관광공사 TourAPI",
                                                  "checked_at": "2026-10-08"}]}}
    # the short provider names prepare() stores for a place's sources (present._short), for the two named here
    e["_providers"] = {**(base.get("_providers") or {}),
                       **{p: present.short_provider(p, city=S.city) for p in ("군산시 문화관광", "한국관광공사 TourAPI")}}
    s = present.slot_value(e, "parking")
    assert s["conflict"] and [(v["provider"], v["main"]) for v in s["vals"]] == \
        [("군산시", "인근 공영주차장/70석"), ("한국관광공사", "불가능 / 70석")]
    kf = present.key_facts(e, "hero")
    assert kf["conflict"] and [x["label"] for x in kf["slots"] if x["conflict"]] == ["주차·좌석"]
    cell = present.slot_cell(e, "parking", "주차")
    assert cell["conflict"] and len(cell["vals"]) == 2


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def test_seat_only_markup(S, built):
    e0 = place(S, SEAT_ONLY)
    html = page_of(built, e0)
    assert 'class="kf-i kf-parking' not in html
    i = html.index('<div class="kf-notes">')
    notes = _text(html[i:html.index("</div>", i)])
    assert notes.count("확인 필요") == 1 and "주차" in notes.split("확인 필요", 1)[1], notes
    page = PageScan()
    page.feed(html)
    rows = [r for r in page.fact_rows if "parking_seats" in r["keys"]]
    assert [r["dt"] for r in rows] == ["좌석"] and rows[0]["text"].startswith("40석")
    assert squash(page.blocks["facts"]).count("확인 필요") == 1
    for e in _seat_only(S):
        p = PageScan()
        p.feed(page_of(built, e))
        assert seat_only_parking_problems(e, p) == [], e["name"]
    # the validator catches the old tile and a page that drops 주차 from its '확인 필요' lines
    old = PageScan()
    old.feed(html.replace("<dt>좌석</dt>", "<dt>주차·좌석</dt>").replace("확인 필요: 주차", "확인 필요: ")
             .replace("<b>확인 필요</b> 주차", "<b>확인 필요</b> "))
    problems = seat_only_parking_problems(e0, old)
    assert len(problems) == 3, problems
    food = (built / "food" / "index.html").read_text("utf-8")
    rec = next(r for r in food.split('<li class="rec"')[1:] if f'data-place="{e0["id"]}"' in r)
    j = rec.index('<div class="c-parking')
    cell = rec[j:rec.index("</div>", j)]
    assert 'class="kf-na"' in cell and "좌석 40석" in _text(cell), cell


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def test_event_time_keeps_each_range_whole_and_lets_the_rest_wrap():
    """An event's time tile: a time range never breaks, but a long text around it may (a phone's half-width tile)."""
    h = str(present.nowrap_times("5.15: 19:30–21:00 5.16: 11:00–20:00"))
    assert h == '5.15: <span class="nw">19:30–21:00</span> 5.16: <span class="nw">11:00–20:00</span>'
    assert str(present.nowrap_times("공연 별로 상이")) == "공연 별로 상이"
    assert str(present.nowrap_times("10:00~18:00")) == '<span class="nw">10:00~18:00</span>'


SHARE_BTN = re.compile(r'<button type="button" class="lnav-share" data-share data-share-id="([^"]*)" '
                       r'data-copied="([^"]*)" data-failed="([^"]*)" data-js-only>.*?<span class="lnav-share-t">([^<]*)</span>'
                       r'</button>', re.S)


def _food(S):
    return next(e for e in S.ent_by_slug.values() if e.get("kind") == "food")


def test_place_guide_course_and_event_pages_have_one_share_button(S, built):
    """Operator 2026-10-17 (공유하기 + GA4, as on the 군산 site): the local bar of every place, guide, course and event
    page holds one 공유 button naming the page's id (the place, guide, course or event series id) with the Korean
    words, before the bar's action; the home and the lists have none."""
    from urllib.parse import unquote
    e = _food(S)
    pages = {e["_path"]: e["id"]}
    for xs, key in ((S.guides, "id"), (S.courses, "id"), (S.series, "key")):
        pages[xs[0]["_path"]] = xs[0][key]
    for path, want in pages.items():
        html = (built / unquote(path).strip("/") / "index.html").read_text("utf-8")
        assert SHARE_BTN.findall(html) == [(want, "링크를 복사했습니다", "링크를 복사하지 못했습니다", "공유")], path
        assert html.index('class="lnav-share"') < html.index('class="lnav-cta"'), path
    for path in ("index.html", "places/index.html", "food/index.html", "guides/index.html"):
        assert "data-share" not in (built / path).read_text("utf-8"), path


def _serve(built):
    """A page.route handler serving the built site at http://site.test/ (nothing leaves the machine)."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return serve


# the browser's share sheet, clipboard and GA4 sender stood in for: what the page hands them is recorded
SHARE_STUBS = """
window.__events = []; window.__copied = []; window.__shared = [];
window.siteTrack = function (name, params) { window.__events.push([name, params]); };
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function (t) {
  window.__copied.push(t); return Promise.resolve(); }}});
var mode = (location.search.match(/share=(\\w+)/) || [])[1];
Object.defineProperty(navigator, 'share', {configurable: true, value: mode === 'none' ? undefined : function (data) {
  window.__shared.push(data);
  if (mode === 'abort') return Promise.reject(new DOMException('closed', 'AbortError'));
  if (mode === 'deny') return Promise.reject(new DOMException('no', 'NotAllowedError'));
  return Promise.resolve(); }});
"""


def test_share_opens_the_sheet_or_copies_and_counts_in_ga4(S, built):
    """In a browser (Playwright + Chromium): the 공유 button hands the phone's share sheet the page title and its
    canonical address with utm_source=share&utm_medium=web_share, and GA4 gets 'share' {method, content_type,
    item_id} only once it went through; a closed sheet sends nothing; a refused sheet, or a browser without one,
    copies the link (utm_medium=copy_link) and says so in the note. On phones the button is the 44px icon alone, its
    word kept for screen readers; on desktop the word shows."""
    sync_api = pytest.importorskip("playwright.sync_api")
    e = _food(S)
    path = f"http://site.test{quote(e['_path'])}"
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            ctx.add_init_script(SHARE_STUBS)
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            want_ev = {"content_type": "place-food", "item_id": e["id"]}
            for mode, method, copied in (("ok", "web_share", False), ("abort", None, False), ("deny", "copy_link", True),
                                         ("none", "copy_link", True)):
                page.goto(f"{path}?share={mode}", wait_until="load")   # a new document each time
                canon = page.get_attribute('link[rel="canonical"]', "href")
                btn = page.locator(".lnav [data-share]")
                box = btn.bounding_box()
                assert box["width"] >= 44 and box["height"] >= 44 and box["x"] + box["width"] <= 390, mode
                assert btn.evaluate("b => getComputedStyle(b.querySelector('.lnav-share-t')).clip") != "auto", mode
                btn.click()
                page.wait_for_timeout(300)
                ev = page.evaluate("window.__events")
                shared, cop = page.evaluate("window.__shared"), page.evaluate("window.__copied")
                if mode != "none":
                    assert shared == [{"title": page.title(), "url": f"{canon}?utm_source=share&utm_medium=web_share"}], mode
                assert ev == ([["share", {"method": method, **want_ev}]] if method else []), mode
                assert cop == ([f"{canon}?utm_source=share&utm_medium=copy_link"] if copied else []), mode
                note = page.locator(".share-note")
                if copied:
                    assert note.inner_text() == "링크를 복사했습니다" and "is-on" in note.get_attribute("class"), mode
                    assert note.get_attribute("role") == "status"
            ctx.close()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            page.goto(path, wait_until="load")
            assert page.locator(".lnav [data-share] .lnav-share-t").is_visible()
            assert page.locator(".lnav [data-share]").inner_text().strip() == "공유"
            ctx.close()
        finally:
            browser.close()



def test_food_list_has_a_dish_row_from_site_json(tmp_path):
    """Evaluation 2026-10-17 (narrow by dish in one tap): site.json food_dishes groups the food list by words of each
    place's name, 대표 메뉴 and 취급 메뉴; a group with DISH_MIN places or more is a 메뉴 chip (the Korean key is the
    URL value every version shares, ?dish=…), each row carries its groups (data-dishes) and a version shows the
    group's name in its language."""
    from pipeline import locales as LC
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["food_dishes"] = {"groups": [
        {"key": "짜장·짬뽕", "words": ["짜장", "짬뽕"], "names": {"en": "Jjajang & jjamppong"}},
        {"key": "게장", "words": ["게장"], "names": {}},
        {"key": "없는메뉴", "words": ["피자"], "names": {"en": "Pizza"}}]}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    S = State(data, "preview")
    v = present.list_vm(S, "food")
    chips = {k: n for k, _, n in v["filters"]["dishes"]}
    rows = [it for g in v["groups"] for it in g["recs"]]
    want = {k: sum(1 for it in rows if k in it["dishes"]) for k in ("짜장·짬뽕", "게장")}
    assert chips == {k: n for k, n in want.items() if n >= present.DISH_MIN} and chips
    assert "없는메뉴" not in chips
    one = next(it for it in rows if "짬뽕" in (it["e"]["facts"].get("menu") or ""))
    assert "짜장·짬뽕" in one["dishes"]
    out = tmp_path / "out"
    build(data, out, "preview")
    html = (out / "food" / "index.html").read_text("utf-8")
    assert f'aria-label="{LC.LIST_WORDS["ko"]["dish"]}"' in html and 'data-f="dish" data-v="짜장·짬뽕"' in html
    assert 'data-dishes="|' in html and "짜장·짬뽕" in html
    # a version names a group in its language; a group without that language's name stays out of it
    en = present.dish_chips(rows, present.dish_groups(site), lambda g: (g.get("names") or {}).get("en", ""))
    assert [k for k, _, _ in en] == [k for k in ("짜장·짬뽕",) if k in chips]


def test_the_site_name_and_the_logo(tmp_path):
    """Operator 2026-10-17 (logo study A '골목 책갈피'): the bar's and the footer's name keeps its text and puts its end
    in .wm-em (대구<각>, Daegu<gak>) in the symbol's brick; site.json brand_symbol names the symbol tools/brand_kit.py
    draws (brick bookmark, the alley cut out, the yellow dot), the icons are that symbol in white on brick, and the tool
    still writes the committed SVGs byte for byte."""
    assert str(present.wordmark("대구각")) == '대구<span class="wm-em">각</span>'
    assert str(present.wordmark("Daegugak")) == 'Daegu<span class="wm-em">gak</span>'
    assert str(present.wordmark("각")) == "각" and str(present.wordmark("<b>")) == "&lt;b&gt;"
    brand = ROOT / "templates" / "assets" / "brand"
    site = json.loads((ROOT / "data" / "suwon" / "site.json").read_text("utf-8"))
    sym = (brand / site["brand_symbol"]).read_text("utf-8")
    assert "#7A2328" in sym and 'aria-hidden="true"' in sym
    css = (ROOT / "templates" / "assets" / "css").glob("*.css")
    css = "".join(p.read_text("utf-8") for p in css)
    assert ".wm-em { color: var(--brand); }" in css and "--brand: #7A2328;" in css
    from PIL import Image
    for n in (48, 96, 180, 192, 512):
        im = Image.open(brand / f"icon-{n}.png").convert("RGB")
        assert im.size == (n, n), n
    ico = Image.open(brand / "favicon.ico")
    assert ico.info["sizes"] == {(16, 16), (32, 32), (48, 48)} and ico.convert("RGBA").getpixel((0, 0))[3] == 0
    import runpy
    runpy.run_path(str(ROOT / "tools" / "brand_kit.py"), run_name="brand_kit")["main"](tmp_path)
    for name in ("suwongak-symbol.svg", "suwongak-app-icon.svg"):
        assert (tmp_path / name).read_bytes() == (brand / name).read_bytes(), name


def test_the_story_stage_keeps_its_text_years_and_photo_together_on_tall_windows(built):
    """Operator 2026-10-17 ('군산처럼'): the home story's text sat at the top, its photo in the middle and its years at
    the bottom of the window. Now the window's spare height goes to the margins: the heading, the text and the years are
    one block, the photo on its centre line, on short and tall windows (the first site's fix)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    measure = """() => {
      const box = document.querySelector('[data-story]'), r = el => el.getBoundingClientRect();
      const on = box.querySelector('.st-ch.is-on') || box.querySelector('.st-ch');
      const kids = [...on.querySelector('.st-text').children];
      const ph = [...box.querySelectorAll('.st-ph')].reduce((a, p) => +getComputedStyle(p).opacity >= .5 ? p : a);
      return {head: r(box.querySelector('.st-head')).top, text: r(kids[kids.length - 1]).bottom,
              rail: [r(box.querySelector('.st-rail')).top, r(box.querySelector('.st-rail')).bottom],
              photo: [r(ph).top, r(ph).bottom]}; }"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            gaps = {}
            for w, h in ((1440, 900), (1900, 1840)):
                ctx = browser.new_context(viewport={"width": w, "height": h}, reduced_motion="no-preference")
                ctx.route("**/*", _serve(built))
                page = ctx.new_page()
                page.goto("http://site.test/", wait_until="load")
                page.wait_for_function("!!document.querySelector('[data-story].is-staged')", timeout=15000)
                top, height = page.evaluate("(() => { const s = document.querySelector('[data-stage]').getBoundingClientRect();"
                                            " return [s.top + scrollY, s.height]; })()")
                n = page.evaluate("document.querySelectorAll('[data-story] .st-ch').length")
                for k in range(n):
                    page.evaluate("y => window.scrollTo(0, y)", top + (height - h) * (k / n + .12))
                    page.wait_for_timeout(700)
                    m = page.evaluate(measure)
                    gaps[(h, k)] = m["rail"][0] - m["text"]
                    assert 0 < gaps[(h, k)] <= 160, (w, h, k, m)    # the years right under the text (its row holds the longest)
                    block, photo = (m["head"] + m["rail"][1]) / 2, sum(m["photo"]) / 2
                    assert abs(block - photo) <= 60 and m["rail"][1] <= h, (w, h, k, m)
                ctx.close()
        finally:
            browser.close()
    for (h, k), gap in gaps.items():   # a taller window adds no gap between the text and the years
        if h == 1840:
            assert gap - gaps[(900, k)] <= 24, gaps


def test_season_ahead_is_the_same_day_one_or_two_years_back_within_three_months():
    """/events/ 'held around this time' (the first site's review 2026-10-17): the series whose newest dated edition —
    one or two years ago — began in the next three months of the year."""
    assert present.season_ahead("2025-10-30", "2026-10-17") == 13
    assert present.season_ahead("2024-11-21", "2026-10-17") == 35
    assert present.season_ahead("2026-03-01", "2026-10-17") is None      # this year's: finished, not 'around this time'
    assert present.season_ahead("2023-11-01", "2026-10-17") is None      # three years back
    assert present.season_ahead("2025-04-01", "2026-10-17") is None      # outside the next three months
    assert present.season_ahead("2024-02-29", "2025-12-30") == 60        # 2월 29일 → 28일
    assert present.season_ahead("2025-01-10", "2026-12-20") == 21        # into next January


def test_nowrap_address_keeps_short_hyphenated_words_whole():
    """A 360px phone broke '1길-12' between the hyphen's halves (the first site's review): short hyphenated words are
    kept on one line, long ones still wrap."""
    out = str(present.nowrap_address("대구광역시 중구 동성로2길 80-1 (삼덕동1가)"))
    assert '<span class="nw">80-1</span>' in out and "대구광역시 중구" in out
    long = "a" * 10 + "-" + "b" * 10
    assert '<span class="nw">' not in str(present.nowrap_address(long))
    assert str(present.nowrap_address("<b>")) == "&lt;b&gt;"                # escaped, never markup from data
