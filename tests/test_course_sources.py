"""Courses from several official sources (and the engine parts they rely on): a stop's
stored kind, the source's 일정 numbers, a stop outside the city searched under its own area, a part_of stop shown by
its own name, a bus tour's facts (departures, fares, booking) under '이용 안내', groups in file order, the public-data
licence label, the home's 대표 장소 counted per course, and this city's courses.json against the official course pages
it was made from (data/raw/<city>/info_pages.json)."""
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote

import pytest

from pipeline import present
from pipeline.build import State, build
from pipeline.schema import LICENSE_LABELS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "fixtures" / "gunsan_subset"

TEST_COURSE = {
    "id": "t-course-1", "slug": "test-two-schedules", "name": "시험 두 일정 코스", "duration": "", "group": "시험 그룹",
    "status": "published", "summary": "시험 코스입니다.",
    "stops": [
        {"name": "말랭이마을", "note": "", "place_slug": "mallaengimaeul", "link_basis": "exact", "day": 1},
        {"name": "말랭이마을 전망 마당", "note": "", "place_slug": "mallaengimaeul", "link_basis": "part_of: 시험", "day": 1},
        {"name": "시험 프로그램", "note": "장소가 아닌 일정", "place_slug": "", "link_basis": "", "kind": "activity", "day": 1},
        {"name": "청암산 둘레 정자", "note": "", "place_slug": "cheongamsan", "link_basis": "part_of: 같은 주소", "day": 2},
        {"name": "불국사", "note": "", "place_slug": "", "link_basis": "", "unlinked": "outside",
         "search_area": "경북 경주시", "day": 2},
    ],
    "facts": [{"label": "첫 출발", "value": "시험역 09:30", "short": "09:30 시험역", "hero": True},
              {"label": "요금", "value": "성인 10,000원 · 청소년 8,000원", "short": "성인 10,000원", "hero": True},
              {"label": "예약", "value": "15명 이상 모이면 운행"}],
    "facts_sources": [{"label": "시험 운영사 안내", "url": "https://tour.example/guide"}],
    "original": {"source_name": "시험 관광과", "source_url": "https://www.data.example/1", "license": "OPEN",
                 "portal": "공공데이터포털", "dataset": "시험_관광코스 정보", "collected_at": "2026-10-11"},
    "question_ids": [],
}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    d = tmp_path_factory.mktemp("courses") / "data"
    shutil.copytree(DATA, d)
    courses = json.loads((d / "courses.json").read_text("utf-8"))
    (d / "courses.json").write_text(json.dumps(courses + [TEST_COURSE], ensure_ascii=False), "utf-8")
    site = json.loads((d / "site.json").read_text("utf-8"))
    site.setdefault("home", {})["featured_min_courses"] = 1     # every attraction on a course is 대표 장소
    (d / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    return d


@pytest.fixture(scope="module")
def S(data):
    return State(data, "preview")


@pytest.fixture(scope="module")
def built(data, tmp_path_factory):
    out = tmp_path_factory.mktemp("courses-out") / "preview"
    build(data, out, "preview")
    return out


def test_a_stored_kind_wins_over_the_name_patterns():
    assert present.stop_kind("시험 프로그램", None, "activity") == "activity"
    assert present.stop_kind("중식", None) == "meal"
    assert present.stop_kind("시험 프로그램", None, "") == "place"
    assert present.stop_kind("시험 프로그램", {"name": "x"}, "activity") == "place"   # a linked stop is a place
    assert present.stop_kind("시험", None, "no-such-kind") == "place"


def test_schedule_rows_outside_search_and_part_of_name(S):
    cv = S.course_vms["test-two-schedules"]
    rows = [(r["kind"], r.get("kind_label"), r["name"]) for r in cv["rows"]]
    assert rows == [("day", "일정", "1"), ("place", None, "말랭이마을"), ("place", None, "말랭이마을 전망 마당"),
                    ("activity", "일정", "시험 프로그램"), ("day", "일정", "2"), ("place", None, "청암산 둘레 정자"),
                    ("place", None, "불국사")]
    assert [s["n"] for s in cv["stops"]] == [1, 2, 3, 4]                      # the programme is not a stop
    part = cv["stops"][2]
    assert part["name"] == "청암산 둘레 정자" and part["part_of"] and part["t"]["slug"] == "cheongamsan"
    assert part["label"] == ""                                                # its own name, not '코스 원문 표기'
    assert unquote(cv["stops"][3]["search"]).endswith("/경북 경주시 불국사")       # outside the city: its own area
    gunsan = [s for v in S.course_vms.values() if v["slug"] != "test-two-schedules" for s in v["stops"] if not s["t"]]
    assert gunsan and all(unquote(s["search"]).split("/")[-1].startswith(S.city.map_query_prefix({})) for s in gunsan)


def test_groups_keep_the_file_order_after_the_durations(S):
    titles = [g["title"] for g in present.course_groups_vm(S)]
    assert titles[:2] == ["당일", "2박 3일"]
    assert titles[2:] == list(dict.fromkeys(c.get("group") or "여행 코스" for c in S.courses
                                            if not c.get("duration")))
    assert titles[-1] == "시험 그룹"


def test_course_page_shows_the_facts_their_sources_and_the_dataset(built):
    html = (built / "courses" / "test-two-schedules" / "index.html").read_text("utf-8")
    hero = html.split('class="datarow"', 1)[1].split("</dl>", 1)[0]
    assert "<dt>첫 출발</dt><dd class=\"tn\">09:30 시험역</dd>" in hero and "성인 10,000원" in hero
    use = html.split('id="h-use"', 1)[1].split("</section>", 1)[0]
    assert re.findall(r"<dt>([^<]+)</dt>", use) == ["첫 출발", "요금", "예약"]
    assert "성인 10,000원 · 청소년 8,000원" in use and 'href="https://tour.example/guide"' in use
    assert ">이용 안내<" in html.split("</header>", 1)[0] or "#h-use" in html          # the local nav links to it
    src = html.split('id="h-src"', 1)[1]
    assert "시험 관광과 · 공공데이터포털 시험_관광코스 정보에서 보기" in src
    assert LICENSE_LABELS["OPEN"] in src and "이용조건 확인 전" not in src
    # the source's 일정 numbers as day separators (the first site's day split: '코스 원문 일정' · '일정 2')
    assert re.search(r'class="stop-sep sep-day"><span class="sep-k">[^<]+</span><span class="sep-v">일정 2</span>', html)
    assert "청암산 안의 경유지" in html
    plain = (built / "courses" / "gunsan-course-m2135-1" / "index.html").read_text("utf-8")
    assert 'id="h-use"' not in plain                                          # no facts, no section


def test_featured_counts_courses_not_stops(S):
    """A place that one course passes twice (an exact and a part_of stop) counts once for that course."""
    cnt = {}
    for c in S.courses:
        for slug in {s["t"]["slug"] for s in S.course_vms[c["slug"]]["stops"] if s["t"] and s["t"]["kind"] == "attraction"}:
            cnt[slug] = cnt.get(slug, 0) + 1
    h = present.home_showcase(S, present.home_vm(S))
    got = {f["e"]["slug"]: f["n_courses"] for f in h["featured"]}
    assert got and got == cnt
    on_test = sum(1 for c in S.courses if any(s.get("place_slug") == "mallaengimaeul" for s in c["stops"]))
    assert got["mallaengimaeul"] == on_test                                  # not on_test + 1
    # the card calls them '공식 코스' only when every course has one official source (here: 군산시 + a test source)
    src = present.courses_source(S, [S.course_vms[c["slug"]] for c in S.courses])
    assert not src["official"] and {f["n_courses_label"] for f in h["featured"]} == {"코스"}
    one = [c for c in S.courses if c["slug"] != "test-two-schedules"]
    assert present.courses_source(S, [S.course_vms[c["slug"]] for c in one])["official"]   # 군산시 alone: official


# ------------------------------------------------------------------ the Daegu courses file
@pytest.mark.skipif(not (ROOT / "data" / "raw" / "daegu").exists(), reason="Daegu raw course CSVs not in Suwon repo")
def test_daegu_courses_are_what_the_importer_makes():
    """data/daegu/courses.json is regenerated from data/raw/daegu only (tools/import_courses_daegu.py): every stop has
    a checked decision, a published course keeps its approval, a new course is a draft, every link is to a
    published place, and the 대구명품코스 stops keep the file's 코스번호 — the tour.daegu.go.kr pages number no stops
    (a photo grid), so no stop carries a note claiming another order, and an unlinked stop never says a place is missing
    when a published place of that name exists."""
    from tools import import_courses_daegu as imp
    problems: list = []
    made = imp.build(problems)
    assert problems == []
    stored = json.loads((ROOT / "data" / "daegu" / "courses.json").read_text("utf-8"))
    assert made == stored
    places = {p["slug"]: p for p in json.loads((ROOT / "data" / "daegu" / "places.json").read_text("utf-8"))}
    for c in stored:
        for s in c["stops"]:
            if s["place_slug"]:
                assert places[s["place_slug"]]["status"] == "published", (c["id"], s["name"])
                assert s["link_basis"]
            else:
                assert s["unlinked"] and s["unlinked_reason"], (c["id"], s["name"])
        assert c["status"] == "published" or not c.get("approved_at")
        if c.get("duration"):
            assert c["duration"] == "당일" and c["duration_basis"].startswith("당일:")
    import csv
    rows = list(csv.DictReader((ROOT / "data/raw/daegu/daegu_tour_courses_15087234.csv").open(encoding="utf-8")))
    for c in stored[:5]:
        nos = [int(r["코스번호"]) for r in rows if r["코스타이틀"].strip() == c["name"]]
        kept = [n for n in nos if n not in {r["source_no"] for r in c.get("removed_stops") or []}]
        assert [s["source_no"] for s in c["stops"]] == kept, c["id"]
    assert not any(c.get("order_alternative") for c in stored)
    assert not any("누리집" in s.get("note", "") and "번째" in s.get("note", "") for c in stored for s in c["stops"])
    # an unlinked stop whose name (without the city prefix) is a published place's is either linked or says why not
    def bare(x: str) -> str:
        return re.sub(r"^대구", "", re.sub(r"\s|\(.*?\)", "", x))
    published = {bare(p["name"]): p["slug"] for p in places.values() if p["status"] == "published"}
    for c in stored:
        for s in c["stops"]:
            slug = published.get(bare(s["name"])) or published.get(bare(s["name"]) + "거리")
            if not s["place_slug"] and slug and s["unlinked"] == "not_collected":
                assert slug in s["unlinked_reason"] or slug in s.get("link_candidate", ""), (c["id"], s["name"], slug)
    dong = [s for c in stored for s in c["stops"] if s["name"] in ("동성로", "동성로·중앙로역")]
    assert dong and all(s["place_slug"] == "daegu-dongseongnogeori" for s in dong)


@pytest.mark.skipif(not (ROOT / "data" / "raw" / "daegu").exists(), reason="Daegu raw course CSVs not in Suwon repo")
def test_daegu_bukgu_courses_and_the_city_bus_map():
    """북구 관광코스(15095883): one course per CSV row, stops in the row's order, its distance and time as the two
    opening figures (the importer checks them against the portal's own description). The 도심순환코스's source is
    the city's open course map (15114536), whose 12 stops equal the operator's timetable; the operator's pages stay
    as the facts' sources."""
    import csv
    stored = {c["id"]: c for c in json.loads((ROOT / "data" / "daegu" / "courses.json").read_text("utf-8"))}
    rows = list(csv.DictReader((ROOT / "data/raw/daegu/courses/daegu_bukgu_courses_15095883.csv").open(encoding="utf-8")))
    bukgu = [c for c in stored.values() if c.get("group") == "북구 관광코스"]
    assert len(bukgu) == len(rows) == 8
    for c, r in zip(bukgu, rows):
        assert [s["name"] for s in c["stops"]] == [" ".join(x.split()) for x in r["관광코스"].split(">")]
        hero = {f["label"]: f["short"] for f in c["facts"] if f.get("hero")}
        assert hero == {"거리": f"{r['거리(km)']}km", "소요시간": " ".join(r["소요시간"].split())}
        assert c["duration"] == "" and c["original"]["license"] == "OPEN"
        # new courses come in as draft; the operator's approval (approved_at) is the only way to published
        assert c["status"] == "draft" or (c["status"] == "published" and c.get("approved_at"))
    circ = stored["daegu-course-citytour-circular"]
    assert circ["original"]["dataset_id"] == "15114536" and circ["original"]["license"] == "OPEN"
    assert circ["original"]["operator_pages"] and any("daegucitytour.com" in x["url"] for x in circ["facts_sources"])
    city = json.loads((ROOT / "data/raw/daegu/courses/daegu_citytour_map_15114536.json").read_text("utf-8"))
    assert len(city["stops"]) == len(circ["stops"]) == 12


@pytest.mark.skipif(not (ROOT / "data" / "raw" / "daegu").exists(), reason="Daegu raw course CSVs not in Suwon repo")
def test_daegu_city_tour_costs_follow_each_course_image():
    """The theme guide's own-cost list (lunch, admission, activities 'when they arise') names lunch only on a tour
    whose course image has a lunch stop: the night tours (18:00/18:30) have none."""
    stored = {c["id"]: c for c in json.loads((ROOT / "data" / "daegu" / "courses.json").read_text("utf-8"))}
    themes = [c for k, c in stored.items() if k.startswith("daegu-course-citytour-tour-")]
    assert len(themes) == 10
    for c in themes:
        cost = next(f["value"] for f in c["facts"] if f["label"] == "따로 내는 돈")
        lunch = any(s.get("kind") == "meal" or "점심" in s.get("note", "") for s in c["stops"])
        assert ("점심" in cost) == lunch, (c["id"], cost)
        assert cost.endswith("(생기면 본인 부담)")
    assert not any("점심" in next(f["value"] for f in stored[k]["facts"] if f["label"] == "따로 내는 돈")
                   for k in ("daegu-course-citytour-tour-6-1", "daegu-course-citytour-tour-6-2"))
# ------------------------------------------------------------------ this city's courses file
CITY = ROOT / "data" / "suwon"


def _city_courses():
    courses = json.loads((CITY / "courses.json").read_text("utf-8"))
    places = {p["slug"]: p for p in json.loads((CITY / "places.json").read_text("utf-8"))}
    return courses, places


def test_city_courses_link_published_places_and_keep_their_source():
    """Every stop of this city's courses links a published place with its link basis (or says why it is unlinked);
    a published course has the operator's approval; a course from a source names it and its licence (none for
    the courses this site made from its places — TourAPI holds no 여행코스 for this city)."""
    courses, places = _city_courses()
    assert courses
    for c in courses:
        for st in c["stops"]:
            if st.get("place_slug"):
                assert st["place_slug"] in places, (c["id"], st["name"], st["place_slug"])
                assert places[st["place_slug"]]["status"] == "published", (c["id"], st["name"])
                assert st["link_basis"], (c["id"], st["name"])
            else:
                assert st.get("unlinked") and st.get("unlinked_reason"), (c["id"], st["name"])
        assert c["status"] != "published" or c.get("approved_at"), c["id"]
        # a course from a source names it and its licence; a course this site made from its places names none
        orig = c.get("original") or {}
        assert not orig or (orig.get("source_name") and orig.get("license") in LICENSE_LABELS), c["id"]


def test_city_day_courses_name_no_day():
    """A 당일 course's stops carry no 1일차·2일차; an overnight one carries them in order (never back)."""
    courses, _ = _city_courses()
    for c in courses:
        days = [st.get("day") or "" for st in c["stops"]]
        if c["duration"] == "당일":
            assert set(days) == {""}, c["id"]
        else:
            assert days == sorted(days) and "" not in days, c["id"]
