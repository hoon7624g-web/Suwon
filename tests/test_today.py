"""오늘의 상태 · 오늘의 바다 — the place page's day card (present.today_vm, templates/_today.html.j2, assets/today.js;
operator 2026-10-31). The parsers place an hours value and a closed-day value on dates and never guess: a season word
without its months, a facility's name or an n-th week day is left to '확인 필요'. The card's HTML is the build day in
absolute dates with its sources (no check date: operator decision 2026-10-09); the other versions print no Korean.
almanac.json / crowd.json / beaches.json are made by other tools: the tests write small files of their shape in a
temporary folder (never into data/gunsan)."""
import datetime as dt
import json
from pathlib import Path
import re
import types

import pytest

from pipeline import build as B
from pipeline import locales as LC
from pipeline import present as P
from pipeline.validate import visible_check_dates

D = dt.date
HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")


# ----------------------------------------------------------------------------- the hours' conditions
@pytest.mark.parametrize("cond,months,days", [
    ("", None, None),
    ("이용시간", None, None),
    ("3~10월", set(range(3, 11)), None),
    ("11~2월", {11, 12, 1, 2}, None),
    ("하절기(3월~10월)", set(range(3, 11)), None),
    ("동절기(11~2월)", {11, 12, 1, 2}, None),
    ("3월~5월/9월~10월", {3, 4, 5, 9, 10}, None),
    ("평일", None, {0, 1, 2, 3, 4}),
    ("주말", None, {5, 6}),
    ("주말·공휴일", None, {5, 6}),      # holidays are not dated here (the card says so)
    ("월~금", None, {0, 1, 2, 3, 4}),
    ("토·일", None, {5, 6}),
    ("월요일~토요일", None, {0, 1, 2, 3, 4, 5}),
    ("토요일~목요일", None, {5, 6, 0, 1, 2, 3}),   # a range past Sunday
    ("금", None, {4}),
    ("매일", None, None),
])
def test_cond_scope_reads_seasons_and_weekdays(cond, months, days):
    s = P.cond_scope(cond)
    assert s is not None
    assert (set(s[0]) if s[0] else None) == months and (set(s[1]) if s[1] else None) == days


@pytest.mark.parametrize("cond", ["하절기", "동절기", "공휴일", "숙박시설", "초원사진관", "입실", "1부"])
def test_cond_scope_never_guesses(cond):
    assert P.cond_scope(cond) is None   # a season without its months, a name: no date can be matched


# ----------------------------------------------------------------------------- one day's hours
MUSEUM = "3~10월 09:00~18:00(입장마감 17:30) / 11~2월 09:00~17:00(입장마감 16:30)"


def test_day_hours_picks_the_season_of_the_date():
    H = P.hours_rows(MUSEUM)
    oct31, nov1 = P.day_hours(H, D(2026, 10, 31)), P.day_hours(H, D(2026, 11, 1))
    assert oct31["ranges"] == [[540, 1080]] and oct31["cond"] == "3~10월"
    assert [(r["label"], r["a"]) for r in oct31["secs"]] == [("입장마감", 1050)]
    assert nov1["ranges"] == [[540, 1020]] and [r["a"] for r in nov1["secs"]] == [990]


def test_day_hours_weekdays_groups_and_overnight():
    H = P.hours_rows("[화요일~토요일]- 11:00~21:00- 준비시간 15:00~17:00[일요일]- 11:00~20:00")
    assert P.day_hours(H, D(2026, 10, 31))["ranges"] == [[660, 1260]]          # Saturday
    assert P.day_hours(H, D(2026, 11, 1))["ranges"] == [[660, 1200]]           # Sunday
    assert P.day_hours(H, D(2026, 11, 2))["ranges"] == []                      # Monday: no hours that day
    H = P.hours_rows("월~목 11:00~23:00 (주문마감 22:00)금 11:00~익일02:00 (주문마감 01:00)토~일 10:00~익일02:00")
    fri = P.day_hours(H, D(2026, 11, 6))
    assert fri["ranges"] == [[660, 1560]] and [(r["sec"], r["a"]) for r in fri["secs"]] == [("order", 60)]
    assert P.hm_text(1560) == "익일 02:00"


def test_day_hours_cuts_the_break_out_of_the_bar():
    H = P.hours_rows("11:30~21:00 (준비시간 15:00~17:00)")
    d = P.day_hours(H, D(2026, 10, 31))
    breaks = [[r["a"], r["b"]] for r in d["secs"] if r["sec"] == "break"]
    assert d["ranges"] == [[690, 1260]] and P.cut_breaks(d["ranges"], breaks) == [[690, 900], [1020, 1260]]


@pytest.mark.parametrize("raw", [
    "동절기 09:00 - 17:00 하절기 09:00 - 18:00",               # seasons without months
    "시간여행관광안내소(10:00~17:00) / 초원사진관(09:00~21:30)",  # two facilities
    "10:30~재료 소진 시",                                     # a time not understood
    "평일 10:00~18:00 / 3~10월 09:00~19:00",                   # two conditions fit a weekday in October
])
def test_day_hours_leaves_what_it_cannot_settle(raw):
    assert P.day_hours(P.hours_rows(raw), D(2026, 10, 27)) is None


def test_hours_rows_always_open():
    assert P.hours_rows("상시 개방")["always"] == "always"
    assert P.hours_rows("년중 무휴 하루 24시간")["always"] == "h24"
    assert P.hours_rows("24시간 예약가능")["always"] == ""    # a booking line, not the opening


# ----------------------------------------------------------------------------- closed days on dates
def test_closures_weekly_dates_and_months():
    C = P.day_closures("매주 월요일, 1월 1일, 시장이 휴관일로 정한 날")
    assert P.closure_on(C, D(2026, 11, 2)) == "closed"       # Monday
    assert P.closure_on(C, D(2027, 1, 1)) == "closed"        # 1월 1일 (a Friday)
    assert P.closure_on(C, D(2026, 11, 3)) == "" and C["stated"] and C["undated"]
    C = P.day_closures("매주 월요일~수요일/공휴일/12월~2월")
    assert P.closure_on(C, D(2026, 11, 3)) == "closed"       # Tuesday, inside the weekday range
    assert P.closure_on(C, D(2026, 12, 4)) == "closed"       # a Friday in December
    assert P.closure_on(C, D(2026, 11, 6)) == ""
    C = P.day_closures("연중무휴")
    assert C["stated"] and C["open"] and P.closure_on(C, D(2026, 11, 2)) == ""


def test_closures_nth_week_is_to_check():
    C = P.day_closures("매월 첫째, 셋째 일요일")
    assert P.closure_on(C, D(2026, 11, 1)) == "check" and P.closure_on(C, D(2026, 11, 2)) == ""
    C = P.day_closures("매주 월요일(월요일이 공휴일이면 문을 열고 다음 평일 휴관)")
    assert C["days"] == {0}                                    # the condition is not a closed day


# ----------------------------------------------------------------------------- the card's view model
def state(tmp_path, almanac=None, crowd=None, beaches=None, today="2026-10-31"):
    """A build State's parts the card reads, loaded the way build.State loads them (files that may not exist)."""
    for name, doc in (("almanac", almanac), ("crowd", crowd), ("beaches", beaches)):
        if doc is not None:
            (tmp_path / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False), "utf-8")
    load = lambda n: B._load(tmp_path / f"{n}.json", {}) or {}   # noqa: E731
    # the city values come from the sample site (data/sample: the first site's shape — its region names the tide
    # station and the sun point these cases use)
    site = json.loads((Path(__file__).resolve().parent.parent / "data" / "sample" / "site.json").read_text("utf-8"))
    from pipeline.city import of as city_of
    return types.SimpleNamespace(today=today, almanac=load("almanac"), crowd=load("crowd"),
                                 beaches=load("beaches"), ferry={}, site=site, city=city_of(site))


def place(pid="p1", name="박물관", kind="attraction", geo=None, themes=(), **facts):
    return {"id": pid, "name": name, "kind": kind, "themes": list(themes), "facts": facts, "_geo": geo,
            "facts_source": {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-26"}}


def test_card_days_states_and_words(tmp_path):
    T = P.today_vm(state(tmp_path), place(usetime=MUSEUM, restdate="매주 월요일, 1월 1일, 시장이 휴관일로 정한 날"))
    d = {x["iso"]: x for x in T["days"]}
    assert len(T["days"]) == P.TODAY_DAYS and len(T["strip"]) == P.TODAY_STRIP
    assert d["2026-10-31"]["lab"] == "10월 31일(토)" and d["2026-10-31"]["head"] == "문 엽니다 · 09:00–18:00"
    assert d["2026-10-31"]["sub"] == "입장마감 17:30 · 3~10월 시간"
    assert d["2026-11-02"]["st"] == "closed" and d["2026-11-02"]["short"] == "휴관"
    assert d["2026-11-03"]["head"] == "문 엽니다 · 09:00–17:00"
    assert T["ax"]["lo"] == 360 and T["ax"]["hi"] == 1320 and d["2026-10-31"]["bar"] == [[0.1875, 0.75]]
    assert T["notes"] == [LC.TODAY_WORDS["ko"]["note_undated"]]
    js = json.loads(str(T["json"]))
    assert js["start"] == "2026-10-31" and len(js["days"]) == P.TODAY_DAYS and js["ax"] == [360, 1320]


def test_card_nth_week_day_from_a_combined_value(tmp_path):
    # closed_text reads '…/둘째,넷째주 일요일 휴무' as '일요일 휴무'; the card keeps the n-th words: every Sunday is not closed
    T = P.today_vm(state(tmp_path), place(kind="food", usetime_restdate="11:30~21:00/둘째,넷째주 일요일 휴무"))
    sun = T["days"][1]
    assert sun["iso"] == "2026-11-01" and sun["st"] == "check" and "둘째,넷째주 일요일 휴무" in sun["sub"]


def test_card_without_bar_prints_the_brief_words(tmp_path):
    T = P.today_vm(state(tmp_path), place(usetime="동절기 09:00 - 17:00 하절기 09:00 - 18:00", restdate="매주 월요일"))
    assert T["ax"] is None and T["days"][0]["st"] == "open"
    assert T["days"][0]["sub"] == "이용시간 동절기 09:00–17:00 · 하절기 09:00–18:00"


def test_no_card_for_a_stay_or_without_data(tmp_path):
    S = state(tmp_path)
    assert P.today_vm(S, place(kind="stay", checkin="15:00")) is None
    assert P.today_vm(S, place(address="군산시")) is None


ALMANAC = {
    "sources": {"sun": {"provider": "한국천문연구원", "dataset": "한국천문연구원_출몰시각 정보", "location": "군산",
                        "url": "https://www.data.go.kr/data/15012688/openapi.do", "checked_at": "2026-10-31"},
                "tide": {"provider": "국립해양조사원", "dataset": "조석예보", "url": "https://www.khoa.go.kr/"}},
    "sun": {"2026-10-31": {"sunrise": "06:54", "sunset": "17:39"}, "2026-11-01": {"sunrise": "0655", "sunset": "1738"}},
    "tide": {"DT_0018": {"name": "군산", "lat": 35.975, "lng": 126.563, "days": {
        "2026-10-30": [{"time": "21:40", "type": "간조", "level_cm": 120}],
        "2026-10-31": [{"time": "03:12", "type": "만조", "level_cm": 612}, {"time": "09:30", "type": "간조", "level_cm": 98},
                       {"time": "15:40", "type": "만조", "level_cm": 640}, {"time": "21:58", "type": "간조", "level_cm": 110}],
        "2026-11-01": [{"time": "03:50", "type": "고조", "level_cm": 600}]}}},
}
SEA = {"lat": 35.81, "lng": 126.41}   # 선유도: about 23 km from the 군산 station


def test_tides_for_a_seaside_place_within_reach(tmp_path):
    S = state(tmp_path, almanac=ALMANAC)
    T = P.today_vm(S, place(name="선유도해수욕장", geo=SEA, usetime="상시 개방", restdate="연중무휴"))
    assert T["sea"] and T["tide"]["at"].startswith("군산 관측소 · 직선 2")
    d0 = T["days"][0]
    assert [(p["t"], p["w"], p["cm_t"]) for p in d0["tide"]][:2] == [("03:12", "만조", "612cm"), ("09:30", "간조", "98cm")]
    line, area = d0["curve"]
    assert line.startswith("M-") and line.count("C") == 5 and area.endswith("Z")   # from the day before to the next
    assert d0["sun"] == {"rise": "06:54", "set": "17:39"} and T["days"][1]["sun"]["set"] == "17:38"
    # a place inland, or a seaside one too far from every station: no tides (the whole tide block is left out)
    assert not P.today_vm(S, place(name="박물관", geo=SEA, usetime="상시 개방"))["tide"]
    assert not P.today_vm(S, place(name="어청도", geo={"lat": 36.6, "lng": 125.6}, usetime="상시 개방"))["tide"]


def test_crowd_forecast_meaning_bands_and_day_received(tmp_path):
    crowd = {"_about": "그 관광지가 가장 붐비는 시기를 100으로 본 상대 수치", "source": {
        "provider": "한국관광공사", "dataset": "한국관광공사_관광지 집중률 방문자 추이 예측 정보", "base_date": "2026-10-31",
        "url": "https://www.data.go.kr/data/15128555/openapi.do"},
        "places": {"p1": {"days": {"2026-10-31": 77.98, "2026-11-01": 39.3, "2026-11-02": 55}}}}
    T = P.today_vm(state(tmp_path, crowd=crowd), place())   # no hours: the forecast alone makes the card
    assert [x["crowd"]["w"] for x in T["days"][:3]] == ["붐빔", "여유", "보통"] and T["days"][0]["crowd"]["v"] == "77.98"
    assert T["crowd"]["got"] == "한국관광공사 예측 · 10월 31일 받음" and T["crowd"]["scale"]
    assert any("70 이상" in n for n in T["notes"])
    assert T["sources"][-1]["items"][0]["name"] == "한국관광공사 관광지 집중률 방문자 추이 예측 정보"


def test_beach_water_always_with_its_year(tmp_path):
    beaches = {"sources": {"water": {"provider": "해양수산부", "dataset": "해양수산부_해수욕장 수질적합 여부 서비스",
                                     "url": "https://www.data.go.kr/data/15056705/openapi.do"}},
               "places": {"p1": {"info": {"beach_knd": "모래", "beach_len": 2000.0, "beach_wid": 20.0},
                                 "water": {"year": "2024", "result": "적합", "checked": "2024-08-27"}}}}
    S = state(tmp_path, beaches=beaches)
    T = P.today_vm(S, place(name="선유도해수욕장", usetime="상시 개방"))
    assert T["sea"] and T["beach"] == [{"label": "해변", "value": "모래 · 길이 2,000m · 폭 20m"},
                                       {"label": "수질", "value": "2024년 조사 · 적합 (8월 27일)"}]
    en = P.today_vm(S, place(name="선유도해수욕장", usetime="상시 개방"), "en", lambda p: "Source")
    assert en["beach"][1]["value"] == "2024 survey · Suitable (Aug 27)"


@pytest.mark.parametrize("code", [c for c in LC.TODAY_WORDS if c != "ko"])
def test_other_versions_print_no_korean(tmp_path, code):
    crowd = {"_about": "가장 붐비는 시기를 100으로", "source": {"provider": "한국관광공사", "base_date": "2026-10-31"},
             "places": {"p1": {"days": {"2026-10-31": 50}}}}
    S = state(tmp_path, almanac=ALMANAC, crowd=crowd)
    for e in (place(name="선유도해수욕장", geo=SEA, usetime=MUSEUM, restdate="매주 월요일, 설·추석 당일"),
              place(kind="food", usetime_restdate="11:30~21:00/둘째,넷째주 일요일 휴무"),
              place(usetime="동절기 09:00 - 17:00 하절기 09:00 - 18:00 외부만 관람", restdate="매주 월요일")):
        T = P.today_vm(S, e, code, lambda p: "Source")
        blob = json.dumps({k: v for k, v in T.items() if k != "w"}, ensure_ascii=False, default=str)
        assert not HANGUL.findall(blob), (code, HANGUL.findall(blob)[:10])
    assert set(LC.TODAY_WORDS[code]) == set(LC.TODAY_WORDS["ko"])


# ----------------------------------------------------------------------------- the card's HTML
def render(T, nm="근대역사박물관"):
    env = B.make_env()
    return env.from_string('{% import "_today.html.j2" as td %}{{ td.card(T, nm) }}').render(T=T)


def visible(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", html, flags=re.S)))


def test_html_reads_whole_in_absolute_dates_with_sources(tmp_path):
    S = state(tmp_path, almanac=ALMANAC)
    T = P.today_vm(S, place(usetime=MUSEUM, restdate="매주 월요일, 1월 1일, 시장이 휴관일로 정한 날"))
    html = render(T)
    text = visible(html)
    assert "10월 31일(토)" in text and "문 엽니다 · 09:00–18:00" in text and "입장마감 17:30" in text
    assert "11월 2일(월) 휴관" in text                          # a date button's name
    assert re.search(r'role="tab"[^>]*aria-selected="true"', html) and html.count('role="tab"') == P.TODAY_STRIP
    assert "17:39" in text and "해 뜨는 시각 06:54" in text
    assert "한국천문연구원 출몰시각 정보(군산 지점 값" in text and "이용시간·쉬는 날 한국관광공사" in text
    assert 'href="https://www.data.go.kr/data/15012688/openapi.do"' in html
    assert "오늘 ·" not in text and not visible_check_dates(text)   # '오늘' only by script; no check date
    assert "data-today" in html and "data-reveal" in html and html.count("data-draw") == 2   # the bar, the sun's arc
    js = re.search(r'<script type="application/json" data-today-json>(.*?)</script>', html, re.S).group(1)
    assert json.loads(js)["days"][2]["st"] == "closed"


def test_html_sea_card_and_its_tide_table(tmp_path):
    S = state(tmp_path, almanac=ALMANAC)
    html = render(P.today_vm(S, place(name="선유도해수욕장", geo=SEA, usetime="상시 개방", restdate="연중무휴")), "선유도해수욕장")
    text = visible(html)
    assert 'class="td td-sea"' in html and "오늘의 바다" in text and html.count('class="td-wave') == 2
    assert "만조 03:12 612cm" in text and "간조 09:30 98cm" in text and "30km 안일 때" in text
    assert 'class="td-cl" d="M' in html and "물때 국립해양조사원 조석예보" in text


def test_html_without_tides_has_no_tide_block(tmp_path):
    html = render(P.today_vm(state(tmp_path), place(name="선유도해수욕장", geo=SEA, usetime="상시 개방")))
    assert "td-tide" not in html and "td-curve" not in html and "td-sea" not in html


def test_assets_are_wired():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    site = (root / "templates" / "assets" / "site.js").read_text("utf-8")
    assert 'attach("today.js")' in site and (root / "templates" / "assets" / "today.js").exists()
    css = (root / "templates" / "assets" / "css" / "74-today.css").read_text("utf-8")
    assert "prefers-reduced-motion" in css and "var(--p, 1)" in css
    tpl = (root / "templates" / "place.html.j2").read_text("utf-8")
    assert "tdy.card(p.today, nm)" in tpl
    assert "tdy.card(v.today, nm)" in (root / "templates" / "en" / "place.html.j2").read_text("utf-8")


# ----------------------------------------------------------------------------- closed-day readers, fixed (2026-10-31)
def test_closed_text_keeps_the_nth_words_of_a_combined_value():
    # '…/둘째,넷째주 일요일 휴무' read as '일요일 휴무' put every Sunday closed in week tables and counts
    e = {"facts": {"usetime_restdate": "11:30~21:00/둘째,넷째주 일요일 휴무"}}
    assert P.closed_text(e) == ("둘째,넷째주 일요일 휴무", False)
    assert P.closed_days(e) == set() and P.week_closure(P.closed_text(e)[0])["partial"] == {"일"}
    assert str(P.mark_closed("11:30~21:00/첫째,셋째주 월요일 휴무")) == \
        '11:30~21:00/<span class="closed">첫째,셋째주 월요일 휴무</span>'
    e = {"facts": {"usetime_restdate": "10:00~21:00 매주 화요일 휴무"}}
    assert P.closed_days(e) == {"화"}


def test_week_closure_counts_every_day_of_a_range():
    assert P.week_closure("매주 월요일~수요일/공휴일/12월~2월")["days"] == {"월", "화", "수"}
    assert P.week_closure("매주 월~수요일")["days"] == {"월", "화", "수"}
    assert P.week_closure("매주 금요일~일요일")["days"] == {"금", "토", "일"}
    assert P.week_closure("매주 토요일~일요일")["days"] == {"토", "일"}
    assert P.monday_open("매주 일요일~화요일") is False   # '월요일' is inside the range, not written
