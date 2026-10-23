"""Engine fixes from the full audit of the live site (2026-10-11): URL extraction, restored line breaks, the key-fact
briefs (hours · closed days · fee · parking · phone), weekly closures, check-in times, event chips that stay true
without a daily rebuild, titles, sameAs, telephone, llms.txt events, the 404 page, list cards and the nearby lists.
Each test names the behaviour, not a city: the values are shaped like the source values that showed the bug."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import jsonld, present
from pipeline.build import State, build, city_site, titled_name
from pipeline.textutil import (clock_text, contact_org, display_value, extract_url, homepage_url, link_url,
                               restore_lines)
from pipeline.validate import validate
from tools.tourapi_bulk import compute_nearby

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DATA = ROOT / "tests" / "fixtures" / "gunsan_subset"


def facts_place(**facts):
    return {"id": "t-1", "name": "한빛관", "kind": "attraction", "facts": facts, "fact_sources": {}}


def kf(e, name):
    return present.slot_value(e, name)


# ------------------------------------------------------------------ URLs (textutil.extract_url / homepage_url)
def test_extract_url_keeps_a_query_that_looks_like_a_legacy_entity():
    raw = '<a href="https://www.example.go.kr/x.do?culPageNo=1&region=1&reg=2&amp;b=3" target="_blank">상세</a>'
    assert extract_url(raw) == "https://www.example.go.kr/x.do?culPageNo=1&region=1&reg=2&b=3"
    assert extract_url("http://example.org/a?x=1&region=2") == "http://example.org/a?x=1&region=2"


def test_extract_url_skips_a_malformed_nested_anchor_and_a_map_page_is_no_homepage():
    raw = ('<a href="<a href="https://map.naver.com/v5/entry/place/1943162816?c=1,2&placePath=%2Fhome"_blank">'
           '<a href="https://map.naver.com/v5/entry/place/1943162816?c=1</a>')
    assert extract_url(raw).startswith("https://map.naver.com/v5/entry/place/1943162816")   # never '<a href='
    assert homepage_url(raw) == ""
    assert homepage_url('<a href="https://www.example.kr/">x</a>') == "https://www.example.kr/"


def test_extract_url_drops_a_label_glued_onto_the_address_but_keeps_hangul_hosts_and_paths():
    assert extract_url("공식 블로그 https://blog.naver.com/abc168공식 인스타그램 https://x.com/y") == "https://blog.naver.com/abc168"
    assert extract_url("맛집 hhttps://food.example.kr한빛시장 골목 https://www.b.co.kr") == "https://food.example.kr"
    assert extract_url("http://한빛걷기대회.com//") == "http://한빛걷기대회.com//"
    assert extract_url("한빛관 http://hanbit.com/index.php/한빛관 인스타") == "http://hanbit.com/index.php/한빛관"


# ------------------------------------------------------------------ restored lines (display)
def test_restore_lines_breaks_before_an_inline_group_label_and_a_glued_day_label():
    assert restore_lines("[평일]- 11:00~19:00 (입장 마감 18:00) [주말/공휴일]- 11:00~19:30") == \
        ["[평일]", "- 11:00~19:00 (입장 마감 18:00)", "[주말/공휴일]", "- 11:00~19:30"]
    assert display_value("usetime", "평일 10:30~19:00주말 10:30~19:30") == "평일 10:30–19:00\n주말 10:30–19:30"
    assert display_value("usetime", "하절기 10:00~19:00동절기 10:00~18:00") == "하절기 10:00–19:00\n동절기 10:00–18:00"
    assert display_value("usetime", "09:00~18:00까지") == "09:00–18:00까지"          # not a label: no break


def test_check_in_time_reads_without_zero_seconds():
    assert clock_text("15:00:00") == "15:00" and clock_text("15:00:30") == "15:00:30"
    assert display_value("checkin", "15:00:00") == "15:00" and display_value("usetime", "15:00:00") == "15:00:00"
    e = {"id": "s", "name": "한빛스테이", "kind": "stay", "facts": {"checkin": "15:00:00", "checkout": "11:00:00"}}
    assert kf(e, "checkin")["main"] == "15:00" and kf(e, "checkout")["main"] == "11:00"
    assert [x["text"] for x in present.status_items(e)][:2] == ["체크인 15:00", "체크아웃 11:00"]


# ------------------------------------------------------------------ hours brief
def test_hours_inline_group_label_belongs_to_the_next_range():
    b, _ = present.brief_hours("[평일]- 11:00~19:00 (입장 마감 18:00) [주말/공휴일]- 11:00~19:30 (입장 마감 18:30)")
    assert (b["main"], b["sub"]) == ("평일 11:00–19:00", "주말/공휴일 11:00–19:30")
    b, _ = present.brief_hours("[주중]- 17:00~24:00- 마지막 주문 23:30 [주말]- 15:00~24:00- 마지막 주문 23:30")
    assert (b["main"], b["sub"]) == ("주중 17:00–24:00", "주말 15:00–24:00")


def test_hours_range_to_the_next_day_is_read():
    b, _ = present.brief_hours("[평일]- 10:00~익일 01:30- 준비시간 15:00~16:00- 마지막 주문 00:30"
                               "[주말]- 08:30~익일 01:30- 준비시간 15:00~16:00")
    assert (b["main"], b["sub"], b["more"]) == ("평일 10:00–익일 01:30", "주말 08:30–익일 01:30", True)


def test_hours_break_inside_a_bracket_is_labelled_and_no_note_leaks_into_the_next_condition():
    b, _ = present.brief_hours("11:30~21:00 (15:30~16:30 브레이크타임)")
    assert (b["main"], b["sub"], b["more"]) == ("11:30–21:00", "15:30–16:30 브레이크타임", False)
    b, _ = present.brief_hours("10:00~21:00 (준비 시간 16:00~17:00, 마지막 주문 20:30)")
    assert (b["sub"], b["more"]) == ("준비 시간 16:00–17:00", True)
    b, _ = present.brief_hours("월~토요일 10:00~21:30 (21:00 라스트오더) 일요일 10:00~20:30 (20:00 라스트오더)")
    assert (b["main"], b["sub"], b["more"]) == ("월~토요일 10:00–21:30", "일요일 10:00–20:30", True)


def test_hours_season_label_keeps_its_brackets_whole():
    b, _ = present.brief_hours("하절기(4월~10월) 10:00~19:00 / 동절기(11월~3월) 10:00~18:00")
    assert (b["main"], b["sub"]) == ("하절기(4월~10월) 10:00–19:00", "동절기(11월~3월) 10:00–18:00")
    b, _ = present.brief_hours("11:00~21:00 / 준비시간(평일) 14:00~16:30")
    assert b["sub"] == "준비시간(평일) 14:00–16:30"
    b, _ = present.brief_hours("상시 개방(능성세가에 현손 거주/ 사전 양해)")
    assert (b["main"], b["more"]) == ("상시 개방(능성세가에 현손 거주/ 사전 양해)", False)
    for raw in ("하절기 (4~10월) 09:00~19:00 / 동절기 (11~3월) 09:00~18:00", "상시 개방(능성세가에 현손 거주/ 사전 양해)"):
        for part in present.brief_hours(raw)[0].values():
            if isinstance(part, str):
                assert part.count("(") == part.count(")"), part


def test_hours_day_words_after_a_range_are_its_condition_not_a_closed_day():
    b, closed = present.brief_hours("[스파]\n06:00~23:00\n[한증막]\n06:00~22:00 월요일~목요일\n00:00~24:00 금요일~토요일, 공휴일")
    assert (b["main"], b["sub"], closed) == ("스파 06:00–23:00", "한증막 06:00–22:00 월요일~목요일", "")
    assert present.brief_hours("09:00~18:00 매주 월요일 휴관")[1] == "매주 월요일 휴관"


def test_meta_description_fact_has_no_list_dashes():
    from pipeline.build import answer_description
    rows = [{"key": "usetime", "label": "이용시간", "value": "- 11:00~22:00- 마지막 주문 21:30", "alternatives": []}]
    out = answer_description("한빛식당은 국수를 파는 식당입니다.", "", rows)
    assert out.endswith("이용시간: 11:00–22:00, 마지막 주문 21:30.") and ": -" not in out


def test_hours_day_words_split_by_slashes_stay_one_condition():
    b, _ = present.brief_hours("- 수요일~목요일 / 일요일 16:00~24:00 (마지막 주문 23:00)- 금요일~토요일 16:00~01:00")
    assert (b["main"], b["sub"]) == ("수요일~목요일·일요일 16:00–24:00", "금요일~토요일 16:00–01:00")


# ------------------------------------------------------------------ closed-day brief
def test_closed_day_split_never_cuts_inside_brackets():
    b = present.brief_closed("매주 월요일 (매월 2주, 4주) / 국정공휴일")
    assert (b["main"], b["sub"]) == ("매주 월요일 (매월 2주, 4주)", "국정공휴일")
    b = present.brief_closed("매주 월요일 / 국경일 / 정부지정 법정공휴일(단, 공휴일과 일요일이 겹칠 경우 휴관)")
    assert b["main"] == "매주 월요일" and b["more"] and "(" not in b["main"]


def test_closed_day_groups_by_season_or_facility():
    b = present.brief_closed("[3월~7월 / 9월~12월] - 월요일 / 공휴일[1월 / 2월 / 8월] - 일요일 / 공휴일")
    assert (b["main"], b["sub"]) == ("3월~7월·9월~12월 월요일·공휴일", "1월·2월·8월 일요일·공휴일")
    b = present.brief_closed("[한빛시장] - 연중무휴 (단, 점포 별로 상이할 수 있음) [한빛야시장] - 매주 화요일~수요일")
    assert (b["main"], b["sub"], b["more"]) == ("한빛시장 연중무휴", "한빛야시장 매주 화요일~수요일", True)
    b = present.brief_closed("- 한빛시장 매월 첫째주·셋째주 일요일 - 한빛 야시장 매주 월요일~목요일")
    assert (b["main"], b["sub"]) == ("한빛시장 매월 첫째주·셋째주 일요일", "한빛 야시장 매주 월요일~목요일")


# ------------------------------------------------------------------ fee, parking, notes, phone
def test_free_entry_row_wins_over_a_programme_price():
    b = present.brief_fee("[입장료/나무놀이터] - 무료 [체험료] - 초급 1,000원 - 중급 3,000원 - 고급 5,000원")
    assert (b["main"], b["sub"], b["more"]) == ("무료", "입장료/나무놀이터", True)


def test_parking_brief_splits_outside_brackets_and_drops_a_trailing_comma():
    b = present.brief_parking("가능요금 (최초 30분 500원 추가 이후 10분당 250원 씩 추가, 요금 발생)")
    assert (b["main"], b["sub"], b["more"]) == ("가능", "", True)
    b = present.brief_parking("가능 (소형 132대)요금 (1시간 무료, 최초 30분 600원, 1일 6000원)")
    assert b["main"] == "가능 (소형 132대)" and b["more"]
    b = present.brief_parking("가능, 요금 (공영주차장 1시간 1,000원, 이후 10분당 300원)")
    assert b["main"] == "가능" and not b["main"].endswith(",")
    assert present.brief_parking("불가능※ 옆 공영주차장(유료) 이용")["main"] == "불가"


def test_a_note_left_to_the_facts_table_marks_the_slot_more():
    e = facts_place(usetime="10:30~17:00※ 눈썰매장은 2월까지만 운영됨", restdate="연중무휴※ 눈썰매장은 2월까지만 운영됨")
    assert kf(e, "hours")["main"] == "10:30–17:00" and kf(e, "hours")["more"]
    assert kf(e, "closed")["main"] == "연중무휴" and kf(e, "closed")["more"]
    only = facts_place(restdate="※ 점포별 상이하므로 홈페이지 참고", parking="※ 점포별 상이하므로 홈페이지 참고")
    assert kf(only, "closed")["main"] == "점포별 상이하므로 홈페이지 참고" and kf(only, "closed")["more"]
    assert "쉬는 날" not in present.key_facts(only)["missing"]


def test_another_organisations_number_is_labelled_and_not_the_places_telephone():
    assert contact_org("OO관광정보센터 053-000-1337", "한빛 골목") == "OO관광정보센터"
    assert contact_org("한빛구청 문화관광과 053-000-2161", "한빛서원") == "한빛구청 문화관광과"
    assert contact_org("053-000-2161", "한빛서원") == ""
    assert contact_org("한빛국립공원동부사무소 053-000-8300", "한빛국립공원(동부지구)") == ""   # its own office
    e = facts_place(infocenter="한빛구청 문화관광과 053-000-2161")
    slot = kf(e, "tel")
    assert (slot["label"], slot["main"], slot["sub"], slot["tel"]) == ("문의", "053-000-2161", "한빛구청 문화관광과", "0530002161")
    assert present.status_items(e, full=True)[-1]["text"] == "문의 한빛구청 문화관광과 053-000-2161"
    site = json.loads((SAMPLE / "site.json").read_text("utf-8"))
    node = jsonld.entity_node(e, site, "https://example.com", "https://example.com/p/", [], [])
    assert "telephone" not in node
    own = jsonld.entity_node(facts_place(infocenter="053-000-2161"), site, "https://example.com", "https://example.com/p/", [], [])
    assert own["telephone"] == "+82-53-000-2161"


def test_a_market_has_no_fee_slot_to_ask_for():
    e = {"id": "m", "name": "한빛시장", "kind": "attraction", "category": "쇼핑", "facts": {"usetime": "08:00~21:00"}}
    assert "요금" not in present.key_facts(e)["missing"] and "주차" in present.key_facts(e)["missing"]
    assert [s["key"] for s in present.key_facts(e, "card")["slots"]] == ["hours", "closed"]
    cell = present.slot_cell(e, "fee", "요금")
    assert cell["none"] and not cell["missing"]


def test_closed_word_labels_a_value_that_does_not_end_in_a_day():
    assert present._closed_word("주말", "food") == "쉬는 날 주말"
    assert present._closed_word("매년 12월~3월", "food") == "쉬는 날 매년 12월~3월"
    assert present._closed_word("매주 월요일", "food") == "매주 월요일 휴무"
    assert present._closed_word("매주 월요일 휴관", "attraction") == "매주 월요일 휴관"


# ------------------------------------------------------------------ weekly closures
def wc(text):
    w = present.week_closure(text)
    order = present.WEEK
    return "".join(d for d in order if d in w["days"]), "".join(d for d in order if d in w["partial"]), w["open"]


def test_weekend_is_saturday_and_sunday():
    assert wc("주말 / 공휴일") == ("토일", "", False)
    assert wc("매주 주말 / 1월 1일") == ("토일", "", False)
    assert present.monday_open("주말")


def test_season_and_facility_groups_are_not_every_week():
    assert wc("[3월~7월 / 9월~12월] - 월요일 / 공휴일[1월 / 2월 / 8월] - 일요일 / 공휴일") == ("", "월일", False)
    assert wc("- 한빛시장 매월 첫째주·셋째주 일요일 - 한빛 야시장 매주 월요일~목요일") == ("", "월화수목일", False)
    assert wc("[한빛시장] 연중무휴 (단, 점포 별로 상이할 수 있음) [한빛야시장] - 매주 화요일~수요일") == ("", "화수", False)
    assert wc("[한빛못] 연중무휴 [음악분수] 매주 월요일") == ("", "월", False)
    assert wc("[북카페]- 일요일[북키즈 / 다목적홀]- 주말") == ("일", "토", False)
    assert wc("- 매주 월요일\n- 설날·추석 당일") == ("월", "", False)        # a plain list is not a group


def test_a_day_named_only_in_a_condition_is_no_weekly_closure():
    assert wc("매주 월요일 / 국경일 / 법정공휴일(단, 공휴일과 일요일이 겹칠 경우 휴관)") == ("월", "", False)
    assert wc("매주 월요일 / 일요일을 제외한 법정공휴일") == ("월", "", False)
    assert wc("매주 일요일과 공휴일") == ("일", "", False)
    assert wc("매주 월요일 (매월 2주, 4주)") == ("", "월", False)


def test_a_season_only_facility_is_not_open_all_year():
    assert wc("연중무휴※ 눈썰매장은 2월까지만 운영됨") == ("", "", False)
    assert not present.weekly_stated("연중무휴※ 눈썰매장은 2월까지만 운영됨")
    assert wc("연중무휴") == ("", "", True)


def test_new_years_day_only_states_the_weekdays():
    assert present.weekly_stated("1월 1일") and present.monday_open("1월 1일")
    assert not present.weekly_stated("비정기 휴무")


# ------------------------------------------------------------------ events
def test_event_text_restores_the_lost_separators():
    assert present.ev_text("5.16: 11:00~20:005.17: 11:00~17:00") == "5.16: 11:00–20:00 5.17: 11:00–17:00"
    assert present.ev_text("- 평일 12:00~21:00- 주말 10:00~21:00") == "평일 12:00–21:00 · 주말 10:00–21:00"
    assert present.ev_text("무료") == "무료"


def test_event_chips_are_dates_that_stay_true_and_a_past_edition_says_it_ended():
    S = State(DATA, "preview")
    S.today = "2026-10-11"
    events = {"run": ("2026-09-11", "2026-10-11"), "soon": ("2026-10-16", "2026-10-17"), "far": ("2026-11-20", ""),
              "past": ("2025-12-24", "2026-01-04")}
    S.events = [{"id": k, "name": f"2026 한빛 {k}", "start_date": a, "end_date": b} for k, (a, b) in events.items()]
    chips = {r["ev"]["id"]: r["chip"] for r in present.ranked_events(S)}
    assert chips == {"run": "10월 11일까지", "soon": "10월 16일 시작", "far": "11월 20일 시작"}
    assert not any(re.search(r"\d일 뒤|진행 중|오늘|내일", c) for c in chips.values())
    js = (ROOT / "templates" / "assets" / "site.js").read_text("utf-8")
    assert "[data-ev-start]" in js and "끝난 행사" in js and "일 뒤 시작" in js


def test_cumulative_course_distance_is_labelled_as_the_sum_of_legs():
    ui = (ROOT / "templates" / "_ui.html.j2").read_text("utf-8")
    assert "출발부터 구간 직선 합 {{ s.cum|pdist }}" in ui and "출발부터 직선 {{" not in ui


# ------------------------------------------------------------------ nearby, launch check, sameAs helpers
def test_nearby_lists_only_records_with_a_public_or_reviewed_page():
    places = [{"name": n, "slug": n, "kind": "attraction", "status": st, "geo": {"lat": 35.98 + d, "lng": 126.71}}
              for n, st, d in (("a", "published", 0), ("b", "draft", 0.001), ("c", "reviewed", 0.002),
                               ("d", "published", 0.003))]
    compute_nearby(places, "2026-10-11")
    assert [n["name"] for n in places[0]["nearby"]] == ["c", "d"]


def test_launch_check_robots_line_follows_the_training_bot_policy():
    from tools import launch_check
    base = {"site": {"crawler_policy": {"allow_training_bots": True}}, "noindex_rules": [], "host_conditioned": False}
    rows = launch_check.launch_items(base, {"published": {}}, {})
    line = next(r for r in rows if "robots.txt" in r)
    assert "명시 허용" in line and "학습 전용" not in line and "GPTBot" in line
    base["site"]["crawler_policy"]["allow_training_bots"] = False
    line = next(r for r in launch_check.launch_items(base, {"published": {}}, {}) if "robots.txt" in r)
    assert "학습 전용 GPTBot" in line and "을 막는다" in line


def test_city_site_is_the_official_host_itself_not_a_dedicated_subdomain():
    from pipeline import city as citymod
    c = citymod.from_site({**json.loads((SAMPLE / "site.json").read_text("utf-8")),
                           "official_domains": [{"domain": "tour.example.go.kr", "name": "관광"},
                                                {"domain": "example.go.kr", "name": "시"}]})
    assert city_site("https://tour.example.go.kr/index.do?menu_id=1", c) and city_site("https://www.example.go.kr/", c)
    assert not city_site("https://festival.example.go.kr/", c) and not city_site("https://library.example.go.kr/x/", c)
    assert not city_site("https://www.hanbit-museum.kr/", c) and not city_site("", c)


# ------------------------------------------------------------------ builds
def data_copy(tmp_path, edit=None, edit_site=None):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    if edit_site:
        site = json.loads((data / "site.json").read_text("utf-8"))
        edit_site(site)
        (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    if edit:
        places = json.loads((data / "places.json").read_text("utf-8"))
        edit(places)
        (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    return data


def jsonld_place(html):
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        for n in json.loads(raw).get("@graph", []):
            if str(n.get("@id", "")).endswith("#place"):
                return n
    return {}


@pytest.fixture(scope="module")
def prod(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("audit")

    def edit(places):
        by = {p["slug"]: p for p in places}
        a, b = by["gyeongam-railroad-village"], by["chowon-photo-studio"]
        b["name"] = a["name"]   # two pages of one name in two 구·군… here: one address each
        a["facts"]["homepage"] = "https://www.gunsan.go.kr/tour/hanbit"   # a city official page: not sameAs
        a["official"] = {"homepage": "https://www.gunsan.go.kr/tour/hanbit"}
        by["eunpa-lake-park"]["facts"]["homepage"] = "https://www.eunpa-example.kr/"   # its own site: sameAs
        # a fact from the facility's own homepage: only then does /about/ name such sources
        by["eunpa-lake-park"].setdefault("fact_sources", {})["homepage"] = {"provider": "은파 공식 누리집",
                                                                            "checked_at": "2026-10-11"}
    data = data_copy(tmp, edit)
    out = tmp / "prod"
    build(data, out, "production")
    return data, out


def test_404_is_noindex_with_a_description(prod):
    _, out = prod
    html = (out / "404.html").read_text("utf-8")
    assert '<meta name="robots" content="noindex, follow">' in html
    assert re.search(r'<meta name="description" content="[^"]{20,}">', html)


def test_same_as_leaves_out_city_portal_pages_and_keeps_a_place_s_own_site(prod):
    _, out = prod
    a = jsonld_place((out / "places/gyeongam-railroad-village/index.html").read_text("utf-8"))
    assert not any("gunsan.go.kr/tour/hanbit" in u for u in a.get("sameAs") or [])
    c = jsonld_place((out / "places/eunpa-lake-park/index.html").read_text("utf-8"))
    assert "https://www.eunpa-example.kr/" in (c.get("sameAs") or [])


def test_about_and_events_pages_print_no_zero_counts_and_chips_carry_their_days(prod):
    _, out = prod
    about = (out / "about/index.html").read_text("utf-8")
    assert "(0장)" not in about and "시설 공식 누리집 같은 공식 안내에서" in about   # a fact names such a source
    plain = State(SAMPLE, "production")
    assert present.about_vm(plain)["n_other_sources"] == 0 and present.about_vm(plain)["n_thumb"] == 0
    events = (out / "events/index.html").read_text("utf-8")
    assert not re.search(r"<span class=\"tn\">0</span>건", events)
    for chip in re.findall(r'<span class="(?:evr-chip|chip[^"]*)"[^>]*>', events + (out / "index.html").read_text("utf-8")):
        assert "data-ev-start=" in chip and "data-ev-last=" in chip


def test_llms_txt_lists_the_events(prod):
    _, out = prod
    short = (out / "llms.txt").read_text("utf-8")
    full = (out / "llms-full.txt").read_text("utf-8")
    assert "## 행사·축제" in short and "/events/" in short
    assert "(행사·축제)" in full


def test_titled_name_adds_the_district_only_for_a_shared_name():
    S = State(ROOT / "tests" / "fixtures" / "metro", "preview")
    e = {**next(x for x in S.entities if S.city.address_parts(x)[0]), "name": "벙글식당", "alt_names": []}
    dist = S.city.address_parts(e)[0]
    plain = titled_name(e, S.city, set())
    shared = titled_name(e, S.city, {"벙글식당"})
    assert dist not in plain and shared == f"{S.city.region} {dist} 벙글식당"


def test_list_and_card_rows_say_missing_values_once_per_block(tmp_path):
    def edit(places):
        for p in places:
            p["facts"] = {"address": p.get("facts", {}).get("address", "")} if p["kind"] == "attraction" else p["facts"]
    data = data_copy(tmp_path, edit)
    out = tmp_path / "out"
    build(data, out, "sample")
    html = (out / "places/index.html").read_text("utf-8")
    recs = re.findall(r'<li class="rec".*?</li>', html, re.S)
    assert recs
    for rec in recs:
        assert rec.count("확인 필요") <= 1
        assert '<span class="kf-na">' not in rec
    assert any('<p class="rec-need">확인 필요: ' in r for r in recs)


def test_validate_reports_a_homepage_that_is_not_an_address(tmp_path):
    def edit(places):
        places[0]["facts"]["homepage"] = "<a href="
    data = data_copy(tmp_path, edit)
    out = tmp_path / "out"
    build(data, out, "sample")
    errors, warns, _ = validate(data, out, "sample")
    assert any("facts.homepage 값이 웹 주소가 아님" in x for x in warns)          # a preview reports it
    build(data, tmp_path / "prod", "production")
    errors, _, _ = validate(data, tmp_path / "prod", "production")
    assert any("facts.homepage 값이 웹 주소가 아님" in x for x in errors)         # production refuses it
    page = (out / "places/gyeongam-railroad-village/index.html").read_text("utf-8")
    assert 'href=""' not in page
    assert link_url("<a href=") == ""
