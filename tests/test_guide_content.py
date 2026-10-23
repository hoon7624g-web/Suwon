"""tools/guide_content.py: 작성자용 장소 목록(catalog), 개수(count), 가이드 검사(check-guide), 반영(merge).

The data folder is a tmp copy: this city's site.json (read, never written), four fake '[샘플]' places, one hidden
duplicate, one event and one stored guide, plus fake official data outside places: nearby.json + parking_lots.json
(근처 공영주차장·정류장·역), designations on the places with their raw lists (tmp/raw/data/designations), and
courses.json (two published courses, one draft). City words come from that site.json (CITY.admin_line, CITY.districts).
"""
import ast
import copy
import csv
import datetime as dt
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import city as citymod
from tests import test_no_city_literals as literals
from tools import guide_content as gc

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "tests" / "fixtures" / "metro" / "site.json"
CITY = citymod.of(json.loads(SITE.read_text("utf-8")))
ADMIN, GU = CITY.admin_line, CITY.districts[0]
TOUR = "한국관광공사 TourAPI"
MUSEUM, FOOD, MAK, CAFE = "[샘플] 한빛박물관", "[샘플] 누리식당", "[샘플] 다온막창", "[샘플] 별빛커피"
OVERVIEW = "옛 관청 건물을 고쳐 만든 전시관으로 2층 전시실에 오래된 지도와 생활 도구를 모아 두었다."


def src() -> dict:
    return {"provider": TOUR, "checked_at": "2026-10-10"}


def place(pid, slug, name, kind, lcls, lat, lng, **facts) -> dict:
    return {"id": pid, "slug": slug, "name": name, "kind": kind, "category": "음식점" if kind == "food" else "문화시설",
            "status": "draft", "summary": "", "facts": {"address": f"{ADMIN} {GU} 동성로2길 80 (공평동)", **facts},
            "facts_source": src(), "geo": {"lat": lat, "lng": lng},
            "tourapi": {"contentid": pid[2:], "title": name, "lcls": lcls, "overview": f"{name}은 오래된 가게다."}}


def places() -> list[dict]:
    museum = place("s-1001", "sample-museum", MUSEUM, "attraction", "VE070100", 35.0, 128.0,
                   usetime="09:00~18:00 (입장 마감 17:30)", restdate="매주 월요일 / 1월 1일", usefee="무료", parking="불가")
    museum["tourapi"]["overview"] = OVERVIEW
    museum["images"] = [{"url": "https://example.org/a.jpg", "license": "KOGL-1", "source": "TourAPI"}]
    food = place("s-1002", "sample-food", FOOD, "food", "FD010100", 35.001, 128.0, menu="따로국밥",
                 treatmenu="선지국 / 수육", usetime="11:00~22:00 (준비시간 15:00~17:00)", restdate="연중무휴",
                 infocenter="053-111-2222", parking="가능")
    food["fact_alternatives"] = {"usetime": [{"value": "11:00~21:00", "provider": "[샘플] 구청 누리집"}]}
    mak = place("s-1003", "sample-makchang", MAK, "food", "FD010100", 35.002, 128.0, menu="막창구이",
                usetime="17:00~익일 02:00", restdate="매주 월요일")
    cafe = place("s-1004", "sample-cafe", CAFE, "food", "FD050100", 35.0, 128.01, menu="아메리카노",
                 usetime="- 08:00~23:00\n- 마지막 주문 22:30", restdate="매주 화요일")
    old = {**place("s-1005", "sample-old", "[샘플] 옛 식당", "food", "FD010100", 35.0, 128.0), "duplicate_of": "s-1002"}
    food["designations"] = [designation("ansim", "안심식당", None, ANSIM_SRC, ANSIM_URL, "ansim_city#3"),
                            designation("mobeom", "모범음식점([샘플] 구 지정)", 2026,
                                        "[샘플] 구 · 공공데이터포털 모범음식점 현황(2026-09-19)", MOBEOM_URL, "mobeom_gu#5")]
    mak["designations"] = [designation("ansim", "안심식당", None, ANSIM_SRC, ANSIM_URL, "ansim_city#9", "low")]
    cafe["designations"] = [designation("goodprice", "착한가격업소([샘플] 시)", 2026,
                                        "[샘플] 시 · 공공데이터포털 착한가격업소 현황(2026-10-01)", GOODPRICE_URL,
                                        "goodprice_city#1")]
    return [museum, food, mak, cafe, old]


ANSIM_SRC, ANSIM_URL = "[샘플] 시 · 공공데이터포털 안심식당 현황(2025-05-09)", "https://www.data.go.kr/data/101/fileData.do"
MOBEOM_URL = "https://www.data.go.kr/data/102/fileData.do"
GOODPRICE_URL = "https://www.data.go.kr/data/103/fileData.do"
MATNA_URL = "https://www.data.go.kr/data/104/fileData.do"
LOT_A, LOT_B = "[샘플] 한빛공영주차장", "[샘플] 누리노상주차장"
STOP_A, STOP_B, STATION = "[샘플] 박물관앞", "[샘플] 박물관건너", "[샘플] 한빛역"
TOUR_COURSE = "[샘플] 시티투어 도심순환코스"


def designation(kind, label, year, source_name, url, row_ref, confidence="high") -> dict:
    return {"type": kind, "label": label, "year": year, "source_name": source_name, "url": url,
            "checked_at": "2026-10-11", "match": {"row_ref": row_ref, "confidence": confidence, "basis": "name+road"}}


def lot(lid, name, paid, spaces, phone, lat, lng, **extra) -> dict:
    return {"id": lid, "name": name, "operation": "공영", "type": "노외", "address": f"{ADMIN} {GU} 한빛로 10",
            "address_jibun": "", "lat": lat, "lng": lng, "spaces": spaces, "paid": paid,
            "hours": {"days": "평일+토요일", "weekday": ["09:00", "18:00"], "saturday": ["09:00", "13:00"]},
            "phone": phone, "manager": "[샘플] 시설관리공단", **extra}


def parking_lots() -> dict:
    fee = {"versions": [{"source": "standard", "label": "요금", "source_name": "[샘플] 표준데이터",
                         "url": "https://www.data.go.kr/data/15012896/standard.do", "checked_at": "2026-10-11",
                         "basic": {"minutes": 30, "won": 1000}, "extra": {"minutes": 10, "won": 300},
                         "day": {"won": 7000, "applies_raw": ""}, "month": {"won": 100000}}], "differs": False}
    contested = {"paid": {"value": "무료", "source": "standard", "label": "[샘플] 구 자료", "source_name": "[샘플] 구 자료"}}
    return {"source": {"standard": {"name": "[샘플] 전국주차장정보표준데이터"}}, "contacts": [], "lots": [
        lot("lot-a", LOT_A, "유료", 54, "053-741-1234", 35.001, 128.0, fee=fee),
        lot("lot-b", LOT_B, "무료", 20, "053-741-5678", 35.003, 128.0),
        lot("lot-c", "[샘플] 다툼주차장", "유료", 8, "053-741-9999", 35.004, 128.0, alt=contested),
        lot("lot-x", "[샘플] 민영주차장", "무료", 30, "053-741-0000", 35.0, 128.011, nearby=False,
            nearby_excluded="민영"),
    ]}


def nearby() -> dict:
    at = lambda lat, lng: {"lat": lat, "lng": lng}  # noqa: E731
    return {
        "_meta": {"parking": {"radius_m": 500, "max": 3}, "bus": {"radius_m": 500, "max": 2},
                  "rail": {"radius_m": 800, "max": 1}},
        "s-1001": {"measured_from": at(35.0, 128.0),
                   "parking": [{"lot_id": "lot-a", "meters": 120}, {"lot_id": "lot-b", "meters": 430}],
                   "bus": [{"stop_name": STOP_A, "meters": 80, "routes": ["401", "급행1"]},
                           {"stop_name": STOP_B, "meters": 140, "routes": ["401", "623"]}],
                   "rail": [{"station": STATION, "official_name": "[샘플] 한빛", "lines": ["2호선"], "exit": "3",
                             "meters": 350}]},
        "s-1002": {"measured_from": at(35.001, 128.0),
                   "parking": [{"lot_id": "lot-b", "meters": 260}, {"lot_id": "lot-c", "meters": 300}],
                   "bus": [{"stop_name": "[샘플] 누리시장", "meters": 210, "routes": ["623"]}], "rail": []},
        # measured before the place moved: its rows no longer fit the place (pipeline.validate warns) — never used
        "s-1003": {"measured_from": at(35.01, 128.0), "parking": [{"lot_id": "lot-a", "meters": 50}],
                   "bus": [{"stop_name": "[샘플] 옛 정류장", "meters": 60, "routes": ["777"]}], "rail": []},
        "s-1004": {"measured_from": at(35.0, 128.01), "parking": [{"lot_id": "lot-x", "meters": 90}], "bus": [],
                   "rail": [{"station": "[샘플] 별빛역", "official_name": "[샘플] 별빛", "lines": ["1호선", "2호선"],
                             "exit": "", "meters": 700}]},
    }


def courses() -> list[dict]:
    tour = {"id": "course-1", "slug": "sample-city-tour", "name": TOUR_COURSE, "group": "[샘플] 시티투어",
            "duration": "당일", "status": "published", "summary": "",
            "facts": [{"label": "첫 출발", "value": "[샘플] 역 광장 앞 09:30", "short": "09:30 출발", "hero": True},
                      {"label": "요금", "value": "성인 10,000원 · 청소년 8,000원", "short": "성인 10,000원"},
                      {"label": "문의", "value": "053-627-8900"}],
            "stops": [{"name": MUSEUM, "place_slug": "sample-museum"},
                      {"name": "[샘플] 골목 축제", "place_slug": "", "unlinked": "event"},
                      {"name": CAFE, "place_slug": "sample-cafe"}]}
    draft = {"id": "course-2", "slug": "sample-draft-course", "name": "[샘플] 초안 코스", "group": "[샘플] 시티투어",
             "duration": "", "status": "draft", "summary": "", "facts": [{"label": "요금", "value": "성인 12,000원"}],
             "stops": [{"name": FOOD, "place_slug": "sample-food"}]}
    walk = {"id": "course-3", "slug": "sample-walk", "name": "[샘플] 골목 힐링", "group": "[샘플] 걷기코스",
            "duration": "", "status": "published", "summary": "",
            "facts": [{"label": "거리", "value": "3.3km(동선 길이)"}, {"label": "소요시간", "value": "47분"}],
            "stops": [{"name": MAK, "place_slug": "sample-makchang"}]}
    return [tour, draft, walk]


LISTS = [  # (sources.json entry, CSV header, CSV rows)
    ({"key": "ansim_city", "use": "write", "type": "ansim", "label": "안심식당", "source_name": ANSIM_SRC,
      "url": ANSIM_URL, "base_date": "2025-05-09", "file": "ansim.csv"},
     ["업소명", "주소"], [[f"[샘플] 식당{i}", "한빛로 1"] for i in range(7)]),
    ({"key": "mobeom_gu", "use": "write", "type": "mobeom", "label": "모범음식점([샘플] 구 지정)",
      "source_name": "[샘플] 구 · 공공데이터포털 모범음식점 현황(2026-09-19)", "url": MOBEOM_URL,
      "base_date": "2026-09-19", "file": "mobeom.csv"},
     ["업소명", "주소"], [[f"[샘플] 모범{i}", "한빛로 2"] for i in range(4)] + [["", ""]]),   # a blank row is no row
    ({"key": "safe_gu", "use": "write", "type": "ansim", "label": "안심음식점([샘플] 구 지정)",
      "source_name": "[샘플] 구 · 공공데이터포털 지정음식점 — 안심음식점(2026-07-03)", "url": MATNA_URL,
      "base_date": "2026-07-03", "file": "matna.csv", "rows": {"구분": ["안심음식점"]}},
     ["업체명", "구분"], [["[샘플] 가", "안심음식점"]] * 12 + [["[샘플] 나", "나트륨음식점"]] * 2),
    ({"key": "goodprice_city", "use": "write", "type": "goodprice", "label": "착한가격업소([샘플] 시)",
      "source_name": "[샘플] 시 · 공공데이터포털 착한가격업소 현황(2026-10-01)", "url": GOODPRICE_URL,
      "base_date": "2026-10-01", "file": "goodprice.csv",
      "kinds": {"col": "업종", "food": ["한식"], "stay": ["숙박업"]}},
     ["업소명", "업종"], [["[샘플] 가", "한식"]] * 3 + [["[샘플] 나", "숙박업"]] + [["[샘플] 다", "미용업"]] * 2),
]


def write_lists(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write(root / "sources.json", {"checked_at": "2026-10-11", "lists": [src for src, _, _ in LISTS]})
    for src, head, rows in LISTS:
        with open(root / src["file"], "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([head, *rows])


STORED = {"id": "guide-old", "slug": "sample-old-guide", "label": "[샘플] 지난 가이드", "title": "[샘플] 지난 질문인가요?",
          "status": "published", "reviewed_at": "2026-10-09", "summary": "[샘플] 지난 답입니다.",
          "faq": [{"q": "[샘플] 박물관은 무료인가요?", "a": "무료입니다.", "source": TOUR}], "items": []}


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


@pytest.fixture
def data(tmp_path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy(SITE, d / "site.json")
    write(d / "places.json", places())
    write(d / "events.json", [{"id": "ev1", "name": "[샘플] 골목 축제", "start_date": "2026-11-01",
                               "end_date": "2026-11-02", "place_name": MUSEUM, "fee": "무료"}])
    write(d / "guides.json", [STORED])
    write(d / "parking_lots.json", parking_lots())
    write(d / "nearby.json", nearby())
    write(d / "courses.json", courses())
    write_lists(tmp_path / "raw" / "data" / "designations")
    return d


def good() -> dict:
    return copy.deepcopy({
        "id": "guide-t1", "slug": "sample-monday", "label": "[샘플] 월요일 식당",
        "title": "[샘플] 월요일에 문 여는 식당은 어디인가요?", "status": "draft", "checked_at": "2026-10-10",
        "summary": "[샘플] 음식점 3곳 가운데 월요일에 여는 곳은 2곳입니다. 연중무휴인 곳은 아래 1곳입니다.",
        "body": [{"heading": "[샘플] 월요일에 쉬는 곳은 다온막창입니다",
                  "text": f"{MAK}은 매주 월요일에 쉬고 화요일부터 17:00~익일 02:00에 엽니다. {MUSEUM}에서 직선 220m입니다."},
                 {"heading": "[샘플] 카페는 화요일에 쉽니다",
                  "text": f"{CAFE}은 매주 화요일에 쉬고 08:00~23:00에 엽니다(마지막 주문 22:30)."}],
        "items": [{"place_slug": "sample-food",
                   "reason": "따로국밥을 내고 11:00~22:00(준비시간 15:00~17:00)에 엽니다. 다른 출처 값은 11:00~21:00이라 "
                             "방문 전 전화 확인(053-111-2222)."}],
        "mentions": ["sample-makchang", "sample-cafe", "sample-museum"],
        "counts": [{"n": 3, "what": "음식점", "where": {"kind": "food"}},
                   {"n": 2, "what": "월요일에 여는 음식점", "where": {"kind": "food", "monday_open": True}},
                   {"n": 1, "what": "연중무휴 음식점", "where": {"kind": "food", "open_all_year": True}, "items": True}],
        "sources": [{"name": TOUR, "url": "https://api.visitkorea.or.kr"}],
        "faq": [{"q": "[샘플] 월요일 밤에 막창을 먹을 수 있나요?",
                 "a": f"{MAK}은 매주 월요일에 쉽니다. 화요일부터 17:00~익일 02:00에 엽니다.", "source": TOUR}],
    })


def issues(data: Path, g: dict) -> list[str]:
    return gc.check_guide(g, gc.Data(data))


# ------------------------------------------------------------------ hours and conditions
def test_hours_span_reads_primary_ranges_only():
    span = lambda raw: tuple(gc.hhmm(x) for x in gc.hours_span(raw))
    assert span("11:00~22:00 (준비시간 15:00~17:00)") == ("11:00", "22:00")
    assert span("- 11:30~22:00\n- 준비시간 15:00~17:00\n- 마지막 주문 21:00") == ("11:30", "22:00")
    assert span("11:30~21:30 (15:00~17:00 브레이크타임)") == ("11:30", "21:30")
    assert span("[평일]- 16:00~23:00[주말]- 10:30~22:00") == ("10:30", "23:00")
    assert gc.hours_span("17:00~익일 02:00") == (17 * 60, 26 * 60)
    assert gc.hours_span("12:00~24:00") == (12 * 60, 24 * 60)
    assert gc.hours_span("상시 영업") == (None, None)


def test_count_conditions(data):
    D = gc.Data(data)
    slugs = lambda w: [p["slug"] for p in gc.select(D, w)]
    assert slugs({"kind": "food"}) == ["sample-food", "sample-makchang", "sample-cafe"]   # the duplicate is not shown
    assert slugs({"kind": "food", "monday_open": True}) == ["sample-food", "sample-cafe"]
    assert slugs({"closed_on": "월"}) == ["sample-museum", "sample-makchang"]
    assert slugs({"kind": "food", "open_all_year": True}) == ["sample-food"]
    assert slugs({"kind": "food", "closes_after": "23:00"}) == ["sample-makchang", "sample-cafe"]
    assert slugs({"kind": "food", "closes_after": "24:00"}) == ["sample-makchang"]
    assert slugs({"opens_before": "09:00"}) == ["sample-museum", "sample-cafe"]
    assert slugs({"fact": {"menu|treatmenu": "선지|막창"}}) == ["sample-food", "sample-makchang"]
    assert slugs({"kind": "food", "not": {"lcls": "FD05"}, "not_fact": {"restdate": "월요일"}}) == ["sample-food"]
    assert slugs({"any": [{"lcls": "VE07"}, {"name": "커피"}]}) == ["sample-museum", "sample-cafe"]
    assert slugs({"near": {"slug": "sample-museum", "m": 150}}) == ["sample-food"]
    assert slugs({"district": GU, "photo": True}) == ["sample-museum"]
    assert slugs({"kind": "food", "geo": True}) == slugs({"kind": "food"}) and slugs({"geo": False}) == []
    assert slugs({"slugs": ["sample-cafe", "nowhere"]}) == ["sample-cafe"]
    with pytest.raises(ValueError, match="모르는 조건 'knd'"):
        gc.select(D, {"knd": "food"})
    with pytest.raises(ValueError, match="HH:MM"):
        gc.select(D, {"closes_after": "11pm"})


def test_nearby_count_keys(data):
    """lot_* / stop_within·bus_route / rail_*: recounted from nearby.json + parking_lots.json; the keys of one family hold
    for the same row; a lot taken off the nearby lists and an entry measured from other coordinates are never used."""
    D = gc.Data(data)
    slugs = lambda w: [p["slug"] for p in gc.select(D, w)]
    assert slugs({"lot_within": 150}) == ["sample-museum"]          # the moved place's 50 m row does not count
    assert slugs({"lot_within": 300}) == ["sample-museum", "sample-food"]   # the cafe's lot is private (nearby false)
    assert slugs({"lot_paid": False}) == ["sample-museum", "sample-food"]
    assert slugs({"lot_paid": True}) == ["sample-museum"]           # lot-c: the two sources differ on 유료/무료
    assert slugs({"lot_within": 300, "lot_paid": False}) == ["sample-food"]   # the museum's free lot is 430 m away
    assert slugs({"bus_route": "401"}) == ["sample-museum"]
    assert slugs({"bus_route": ["623", "777"]}) == ["sample-museum", "sample-food"]   # 777: only the moved place's
    assert slugs({"stop_within": 100}) == ["sample-museum"]
    assert slugs({"bus_route": "623", "stop_within": 150}) == ["sample-museum"]
    assert slugs({"bus_route": "623", "stop_within": 100}) == []    # the 80 m stop has no 623
    assert slugs({"rail_line": "2호선"}) == ["sample-museum", "sample-cafe"]
    assert slugs({"rail_within": 500}) == ["sample-museum"]
    assert slugs({"rail_station": "[샘플] 한빛"}) == slugs({"rail_station": STATION}) == ["sample-museum"]
    assert slugs({"rail_within": 800, "rail_line": "1호선"}) == ["sample-cafe"]
    assert slugs({"rail_within": 500, "rail_line": "1호선"}) == []
    assert slugs({"kind": "food", "not": {"lot_within": 500}}) == ["sample-makchang", "sample-cafe"]
    bad = [
        ({"lot_within": 900},"lot_within: 900m는 nearby.json 반경 500m 밖"), ({"stop_within": True}, "미터(양수)"),
        ({"lot_paid": "yes"}, "true 또는 false"), ({"bus_route": "402"}, "nearby.json에 없는 버스 노선 '402'"),
        ({"rail_line": "4호선"}, "nearby.json에 없는 도시철도 노선 '4호선'"), ({"bus_route": []}, "문자열 하나 또는"),
        ({"any": [{"rail_station": "[샘플] 없는역"}]}, "any[0].rail_station: nearby.json에 없는 역")]
    for where, msg in bad:
        with pytest.raises(ValueError, match=re.escape(msg)):
            gc.select(D, where)


def test_designation_and_course_count_keys(data):
    D = gc.Data(data)
    slugs = lambda w: [p["slug"] for p in gc.select(D, w)]
    assert slugs({"designation": "ansim"}) == ["sample-food"]       # the makchang's match is low confidence: not shown
    assert slugs({"designation": True}) == ["sample-food", "sample-cafe"]
    assert slugs({"designation": ["goodprice", "mobeom"]}) == ["sample-food", "sample-cafe"]
    assert slugs({"designation_source": "mobeom_gu"}) == ["sample-food"]
    assert slugs({"designation": "mobeom", "designation_source": "mobeom_gu"}) == ["sample-food"]
    assert slugs({"designation": "ansim", "designation_source": "mobeom_gu"}) == []   # the same designation
    assert slugs({"kind": "food", "not": {"designation": True}}) == ["sample-makchang"]
    assert slugs({"course": True}) == ["sample-museum", "sample-makchang", "sample-cafe"]   # not the draft course's
    assert slugs({"course": "sample-city-tour"}) == slugs({"course": "course-1"}) == ["sample-museum", "sample-cafe"]
    assert slugs({"course": "[샘플] 시티투어"}) == ["sample-museum", "sample-cafe"]   # group: its published courses
    for where, msg in [({"designation": "ansm"}, "모르는 지정 유형 'ansm'"),
                       ({"designation_source": "nope"}, "모르는 지정 목록 'nope'"),
                       ({"course": "sample-draft-course"}, "공개되지 않은 코스: sample-draft-course"),
                       ({"course": "nowhere"}, "courses.json에 없는 코스·group: nowhere"),
                       ({"course": False}, "문자열 하나·문자열 목록 또는 true")]:
        with pytest.raises(ValueError, match=re.escape(msg)):
            gc.select(D, where)
    # every new key is documented where writers read it
    for k in ("lot_within", "lot_paid", "stop_within", "bus_route", "rail_within", "rail_line", "rail_station",
              "designation", "designation_source", "course"):
        assert k in gc.COUNT_KEYS and k in gc.__doc__


def test_catalog_rows(data, tmp_path):
    out = tmp_path / "work" / "catalog.json"
    assert gc.catalog(data, out) == {"places": 4, "events": 1, "guides": 1, "courses": 2, "out": str(out)}
    doc = json.loads(out.read_text("utf-8"))
    assert set(doc) == {"rules", "count_keys", "places", "events", "guides", "courses", "nearby_radius",
                        "designation_lists"}
    assert [c["slug"] for c in doc["courses"]] == ["sample-city-tour", "sample-walk"]      # the draft course is not
    assert doc["nearby_radius"] == {"parking": 500, "bus": 500, "rail": 800}
    assert {x["key"]: (x["rows"], x["kinds"], x["file_rows"]) for x in doc["designation_lists"]} == {
        "ansim_city": (7, {}, None), "mobeom_gu": (4, {}, None), "safe_gu": (12, {}, 14),
        "goodprice_city": (6, {"food": 3, "stay": 1, "other": 2}, None)}
    rows = {r["slug"]: r for r in doc["places"]}
    food = rows["sample-food"]
    assert (food["district"], food["area"], food["road"], food["lcls"]) == (GU, "공평동", "동성로2길", "FD010100")
    assert food["facts"]["menu"] == "따로국밥" and food["provider"] == TOUR
    assert food["differs"] == {"usetime": [{"value": "11:00~21:00", "provider": "[샘플] 구청 누리집"}]}
    assert food["closed"] == {"text": "연중무휴", "contested": False, "days": "", "partial": "", "open_all_year": True,
                              "monday_open": True}
    assert food["hours"] == {"opens": "11:00", "closes": "22:00", "next_day": False}
    assert rows["sample-makchang"]["hours"] == {"opens": "17:00", "closes": "02:00", "next_day": True}
    assert rows["sample-museum"]["photo"] is True and rows["sample-museum"]["geo"] == [35.0, 128.0]
    near = rows["sample-museum"]["nearby"]
    assert [(x["name"], x["m"], x["paid"], x["fees"]) for x in near["lots"]] == [
        (LOT_A, 120, "유료", ["기본 30분 1,000원 · 이후 10분마다 300원 · 1일 주차권 7,000원"]), (LOT_B, 430, "무료", [])]
    assert near["stops"][0] == {"name": STOP_A, "m": 80, "routes": ["401", "급행1"]}
    assert near["rails"] == [{"name": STATION, "lines": ["2호선"], "exit": "3", "m": 350}]
    assert "nearby" not in rows["sample-makchang"]           # its entry was measured from other coordinates
    assert [x["list"] for x in food["designations"]] == ["mobeom_gu", "ansim_city"]   # display order (site.json)
    assert "designations" not in rows["sample-makchang"]     # a low-confidence match is not shown
    assert rows["sample-museum"]["courses"] == ["sample-city-tour"] and "courses" not in food
    assert "source_text" not in food
    assert doc["guides"][0]["faq"] == ["[샘플] 박물관은 무료인가요?"]
    gc.catalog(data, out, with_text=True, kinds=["attraction"])
    rows = json.loads(out.read_text("utf-8"))["places"]
    assert [r["slug"] for r in rows] == ["sample-museum"] and rows[0]["source_text"] == OVERVIEW


# ------------------------------------------------------------------ check-guide
def test_a_clean_guide_passes(data):
    assert issues(data, good()) == []


def test_references_must_exist(data):
    g = good()
    g["items"].append({"place_slug": "no-such-place", "reason": "없는 곳입니다."})
    g["items"].append({"place_slug": "sample-old", "reason": "중복 기록입니다."})
    g["mentions"].append("sample-ghost")
    g["event_ids"] = ["ev9"]
    found = issues(data, g)
    assert "items[1] places.json에 없는 장소: no-such-place" in found
    assert "items[2] 중복·제외된 장소: sample-old" in found
    assert "mentions places.json에 없는 장소: sample-ghost" in found
    assert "event_ids events.json에 없는 행사: ev9" in found
    g = good()
    g["body"][1]["text"] = "카페는 매주 화요일에 쉽니다."
    assert f"mentions의 장소 이름이 글에 없음: {CAFE} (sample-cafe)" in issues(data, g)


def test_numbers_must_come_from_data_or_a_recounted_count(data):
    g = good()
    g["body"][0]["text"] += " 좌석은 40석입니다."
    g["body"][1]["text"] += f" {MUSEUM}에서 직선 600m입니다."
    found = issues(data, g)
    assert "body[0].text 근거 없는 숫자 ['40']" in found
    assert "body[1].text 근거 없는 숫자 ['600']" in found
    # a distance between referenced places (rounded), a fact of a mentioned place and a count's n all pass
    g = good()
    g["body"][1]["text"] += f" {CAFE}은 {MUSEUM}에서 직선 0.9km(900m)이고, 박물관 관람은 09:00~18:00입니다."
    assert issues(data, g) == []
    # a number with no unit is not excused by a distance
    g["body"][1]["text"] += " 900번 버스가 섭니다."
    assert "body[1].text 근거 없는 숫자 ['900']" in issues(data, g)
    # a clock time and a phone number are checked whole: their digits alone (9·30, 053) do not make them true
    g = good()
    g["body"][1]["text"] += f" {MAK}은 일요일에 09:30에 열고 053-111-2223으로 예약합니다."
    found = issues(data, g)
    assert "body[1].text 참조 장소의 값에 없는 시각 ['09:30']" in found
    assert "body[1].text 참조 장소의 값에 없는 전화번호 ['053-111-2223']" in found
    g = good()
    g["counts"].append({"n": 1, "what": "자정 넘어 여는 곳", "where": {"kind": "food", "closes_after": "24:00"}})
    g["body"][0]["text"] += " 자정(24:00) 넘어서까지 여는 곳은 1곳입니다."    # the count's own time is allowed
    assert issues(data, g) == []


def test_nearby_rows_of_referenced_places_ground_numbers(data):
    """The referenced places' nearby rows as the page prints them (present.lot_row / rail_row) ground the guide's
    numbers, times and phones; a wrong route number, fee, time or phone is still flagged."""
    g = good()
    g["body"][1]["text"] += (
        f" {MUSEUM}에서 직선 120m에 {LOT_A}(노외주차장, 54면)이 있고 기본 30분 1,000원, 이후 10분마다 300원, "
        "1일 주차권 7,000원입니다. 평일 09:00~18:00·토요일 09:00~13:00에 운영하고 문의는 053-741-1234입니다."
        f" {LOT_B}은 무료이고 직선 0.4km(430m)입니다. {STOP_A} 정류장(직선 80m)에 401번·급행1번이 섭니다."
        f" {STATION}(2호선) 3번 출구까지 직선 350m입니다.")
    assert issues(data, g) == []
    wrong = [("401번·급행1번", "402번·급행1번", "근거 없는 숫자 ['402']"),
             ("기본 30분 1,000원", "기본 30분 1,200원", "근거 없는 숫자 ['1200']"),
             ("토요일 09:00~13:00", "토요일 09:00~14:00", "참조 장소의 값에 없는 시각 ['14:00']"),
             ("053-741-1234", "053-741-1235", "참조 장소의 값에 없는 전화번호 ['053-741-1235']"),
             ("3번 출구", "6번 출구", "근거 없는 숫자 ['6']")]
    for old, new, msg in wrong:
        bad = copy.deepcopy(g)
        bad["body"][1]["text"] = bad["body"][1]["text"].replace(old, new)
        assert f"body[1].text {msg}" in issues(data, bad), old
    # a month pass is stored but not printed on the page; a row of an entry measured from other coordinates (the
    # makchang's 50 m lot, its 777 bus) and a lot taken off the nearby lists (the cafe's private 90 m lot) ground nothing
    g = good()
    g["body"][0]["text"] += " 월 정기권은 100,000원이고 직선 50m에 주차장이, 777번 버스 정류장이 있습니다. 직선 90m입니다."
    assert "body[0].text 근거 없는 숫자 ['50', '90', '777', '100000']" in issues(data, g)
    # a place that is not referenced grounds nothing: without the museum, its lot's fee is unknown
    g = good()
    g["mentions"].remove("sample-museum")
    g["body"][1]["text"] += f" {LOT_A}은 기본 30분 1,000원입니다."
    assert "body[1].text 근거 없는 숫자 ['1000']" in issues(data, g)


RAIL_URL, BUS_URL = "https://www.data.go.kr/data/201/openapi.do", "https://www.data.go.kr/data/202/openapi.do"
BOARD = "[샘플] 역앞"


def transit() -> dict:
    stop = lambda n, name: [n, f"b{n}", name, 128.0, 35.0]  # noqa: E731
    return {
        "rail": {"source": {"provider": "[샘플] 열차정보", "url": RAIL_URL}, "runs": [
            {"date": "20261019", "from": "[샘플] 한빛역", "to": "[샘플] 누리역", "trains": [
                {"no": "101", "grade": "KTX", "dep": "0503", "arr": "0645", "fare": 43500},
                {"no": "1201", "grade": "무궁화호", "dep": "0610", "arr": "0950", "fare": 25000}]}]},
        "bus": {"source": {"provider": "[샘플] 버스정보", "url": BUS_URL}, "stops": [BOARD], "routes": {
            "r1": {"routeNo": "401", "note": "", "start": "[샘플] 갓바위", "end": "[샘플] 범물", "dir_note": {},
                   "stops": {"0": [stop(1, BOARD)] + [stop(n, f"[샘플] 가는 길{n}") for n in range(2, 30)] + [stop(30, STOP_A)],
                             "1": [stop(1, STOP_B)] + [stop(n, f"[샘플] 오는 길{n}") for n in range(2, 27)] + [stop(27, BOARD)]}}}},
    }


def test_transit_blocks_ground_only_when_their_source_is_cited(data):
    """transit.json (the city's transit import tool) grounds a timetable's date, counts, times, fares, train numbers
    and journey times, and a bus route's number and stop counts out from a boarding stop to a referenced place's
    nearby stop and back — each block only when the guide's sources name its url."""
    write(data / "transit.json", transit())
    g = good()
    g["sources"] += [{"name": "[샘플] 열차정보", "url": RAIL_URL}, {"name": "[샘플] 버스정보", "url": BUS_URL}]
    g["body"][1]["text"] += (
        " 2026년 10월 19일 [샘플] 한빛역에서 [샘플] 누리역까지 열차는 2대이고, 101 KTX는 05:03에 떠나 06:45에 닿아 "
        "1시간 42분(102분) 걸리며 요금은 43,500원입니다."
        f" {BOARD}에서 401번([샘플] 범물 방면)을 타고 29번째 정류장인 {STOP_A}에서 내리면 직선 80m이고, 돌아올 때는 "
        f"{STOP_B}에서 401번을 타면 26번째가 {BOARD}입니다.")
    assert issues(data, g) == []
    bad = copy.deepcopy(g)
    bad["body"][1]["text"] = bad["body"][1]["text"].replace("29번째 정류장", "14번째 정류장")
    assert "body[1].text 근거 없는 숫자 ['14']" in issues(data, bad)
    bad = copy.deepcopy(g)
    bad["sources"] = [s for s in bad["sources"] if s["url"] != RAIL_URL]
    found = issues(data, bad)
    assert "body[1].text 근거 없는 숫자 ['6', '42', '45', '101', '102', '43500']" in found
    assert "body[1].text 참조 장소의 값에 없는 시각 ['05:03', '06:45']" in found
    bad = copy.deepcopy(g)
    bad["sources"] = [s for s in bad["sources"] if s["url"] != BUS_URL]
    assert "body[1].text 근거 없는 숫자 ['26', '29']" in issues(data, bad)


def test_nearby_rows_ground_only_a_text_about_getting_there(data):
    """A referenced place carries up to six nearby rows; their values ground a text only when it is about getting
    there (an access word or a row's name), so they never ground an unrelated number, time or phone elsewhere."""
    g = good()
    g["body"][1]["text"] += " 전시 공간은 54석이고 관람료는 7,000원이며 토요일은 13:00까지, 문의는 053-741-1234입니다."
    found = issues(data, g)
    assert "body[1].text 근거 없는 숫자 ['13', '54', '741', '1234', '7000']" in found
    assert "body[1].text 참조 장소의 값에 없는 시각 ['13:00']" in found
    assert "body[1].text 참조 장소의 값에 없는 전화번호 ['053-741-1234']" in found
    g = good()
    g["body"][1]["text"] += " 근처 공영주차장은 54면이고 1일 주차권은 7,000원이며 토요일은 13:00까지, 문의는 053-741-1234입니다."
    assert issues(data, g) == []
    # a row's name is enough ('[샘플] 박물관건너' has no access word); without it the metres are unknown
    g = good()
    g["faq"][0]["a"] += " 직선 140m입니다."
    assert "faq[0].a 근거 없는 숫자 ['140']" in issues(data, g)
    g["faq"][0]["a"] = g["faq"][0]["a"].replace("직선 140m", f"{STOP_B}까지 직선 140m")
    assert issues(data, g) == []


def test_unprinted_station_list_name_grounds_nothing(data):
    """The page prints the station as stored ('…역'); the station list's official name (with its bracket) still
    matches rail_station but is no source of numbers."""
    rows = nearby()
    rows["s-1001"]["rail"][0]["official_name"] = "[샘플] 한빛(613·614기념)"
    write(data / "nearby.json", rows)
    assert [p["slug"] for p in gc.select(gc.Data(data), {"rail_station": "[샘플] 한빛(613·614기념)"})] == ["sample-museum"]
    g = good()
    g["body"][1]["text"] += f" {STATION}(2호선) 3번 출구까지 직선 350m이고 역 목록 이름에는 613·614가 붙습니다."
    assert "body[1].text 근거 없는 숫자 ['613', '614']" in issues(data, g)


def test_designations_of_referenced_places_ground_their_label_and_year(data):
    g = good()
    g["items"][0]["reason"] += " 모범음식점([샘플] 구 지정) 2026년 목록과 안심식당 목록에 있습니다."
    assert issues(data, g) == []
    g["items"][0]["reason"] += " 2027년에도 지정됐습니다."
    assert "items[0].reason 근거 없는 숫자 ['2027']" in issues(data, g)
    # the year comes from the shown designations: without them it is flagged too
    rows = places()
    for p in rows:
        p.pop("designations", None)
    write(data / "places.json", rows)
    assert "items[0].reason 근거 없는 숫자 ['2026', '2027']" in issues(data, g)


def test_designation_list_sizes_count_only_when_the_guide_cites_the_list(data):
    g = good()
    g["body"][0]["text"] += " 안심식당 목록에는 7곳이 있고, 지정음식점 14곳 가운데 안심음식점은 12곳입니다."
    found = issues(data, g)
    assert "body[0].text 근거 없는 숫자 ['7', '12', '14']" in found
    assert "body[0].text 'N곳' 개수 주장 ['7', '12', '14']이 counts·items 개수에 없음" in found
    g["sources"] += [{"name": ANSIM_SRC, "url": ANSIM_URL},                      # cited by name and url
                     {"name": "[샘플] 구 지정음식점", "url": MATNA_URL}]          # cited by url
    assert issues(data, g) == []
    g["body"][0]["text"] = g["body"][0]["text"].replace("7곳", "70곳")             # a wrong size is still flagged
    assert any(x.startswith("body[0].text 근거 없는 숫자 ['70']") for x in issues(data, g))
    # the screen label alone is no citation: '안심식당' with another url is another list (a national one, say)
    g = good()
    g["body"][0]["text"] += " 안심식당 목록에는 7곳이 있습니다."
    g["sources"].append({"name": "안심식당", "url": "https://www.example.org/ansim"})
    assert "body[0].text 근거 없는 숫자 ['7']" in issues(data, g)
    g["sources"][-1]["name"] = ANSIM_SRC                                           # its source_name cites it
    assert issues(data, g) == []
    # the 착한가격업소 list's rows per kind (a list sorted by 업종) count once it is cited
    g = good()
    g["body"][0]["text"] += " 착한가격업소 목록 6곳 가운데 음식 업종은 3곳, 숙박은 1곳입니다."
    assert "body[0].text 근거 없는 숫자 ['6']" in issues(data, g)
    g["sources"].append({"name": "[샘플] 시 · 공공데이터포털 착한가격업소 현황(2026-10-01)", "url": GOODPRICE_URL})
    assert issues(data, g) == []


def test_referenced_courses_ground_their_facts(data):
    g = good()
    text = (f" {TOUR_COURSE}는 09:30에 첫 출발하고 성인 요금은 10,000원, 청소년 8,000원입니다(문의 053-627-8900)."
            " 경유지는 3곳이고 걷기 코스 [샘플] 골목 힐링은 3.3km, 47분입니다.")
    g["body"][1]["text"] += text
    found = issues(data, g)
    assert "body[1].text 근거 없는 숫자 ['3.3', '47', '627', '8000', '8900', '10000']" in found
    assert "body[1].text 참조 장소의 값에 없는 시각 ['09:30']" in found
    assert "body[1].text 참조 장소의 값에 없는 전화번호 ['053-627-8900']" in found
    assert any(x.startswith("body[1].text 근거 없는 수식어") for x in found)          # '힐링' outside a course name
    g["courses"] = ["sample-city-tour", "course-3"]                                # by slug or id
    assert issues(data, g) == []
    bad = copy.deepcopy(g)
    bad["body"][1]["text"] = bad["body"][1]["text"].replace("10,000원", "12,000원")
    assert "body[1].text 근거 없는 숫자 ['12000']" in issues(data, bad)            # the draft course's fare
    bad["courses"].append("sample-draft-course")
    found = issues(data, bad)
    assert "courses 공개되지 않은 코스: sample-draft-course" in found
    assert "body[1].text 근거 없는 숫자 ['12000']" in found
    bad["courses"].append("no-such-course")
    assert "courses courses.json에 없는 코스: no-such-course" in issues(data, bad)
    # the course must be named in the guide (its name without the group word in front also counts)
    bad = copy.deepcopy(g)
    bad["body"][1]["text"] = bad["body"][1]["text"].replace(TOUR_COURSE, "도심순환코스")
    assert issues(data, bad) == []
    bad["body"][1]["text"] = bad["body"][1]["text"].replace("도심순환코스", "그 버스")
    assert f"courses의 코스 이름이 글에 없음: {TOUR_COURSE} (sample-city-tour)" in issues(data, bad)


def test_new_count_keys_ground_their_definition(data):
    assert {"150", "623"} <= gc.threshold_numbers({"stop_within": 150, "bus_route": "623"})
    assert {"2", "400", "0.4"} <= gc.threshold_numbers({"any": [{"rail_within": 400, "rail_line": "2호선"}]})
    g = good()
    g["counts"].append({"n": 1, "what": "직선 300m 안에 무료 공영주차장이 있는 곳",
                        "where": {"lot_within": 300, "lot_paid": False}})
    g["counts"].append({"n": 2, "what": "가까운 역이 2호선인 곳", "where": {"rail_line": "2호선"}})
    g["counts"].append({"n": 2, "what": "공개 코스의 경유지", "where": {"course": True, "kind": "food"}})
    g["body"][0]["text"] += " 직선 300m 안에 무료 공영주차장이 있는 곳은 1곳입니다."
    assert issues(data, g) == []
    g["counts"][-1]["n"] = 3
    assert "counts[5] '공개 코스의 경유지': 다시 센 값 2, 적은 값 3" in issues(data, g)
    g["counts"][-1]["where"] = {"course": "sample-draft-course"}
    assert "counts[5].where.course: 공개되지 않은 코스: sample-draft-course" in issues(data, g)


def test_counts_are_recounted_and_a_listed_count_lists_exactly_its_places(data):
    g = good()
    g["counts"][1]["n"] = 3
    assert "counts[1] '월요일에 여는 음식점': 다시 센 값 2, 적은 값 3" in issues(data, g)
    g = good()
    g["items"].append({"place_slug": "sample-cafe", "reason": "아메리카노를 냅니다."})
    found = issues(data, g)
    assert any(x.startswith("counts[2] items: true인데 items가 조건 결과와 다름 — 조건 밖 ['sample-cafe']") for x in found)
    g = good()
    g["counts"][0]["where"] = {"kind": "food", "colour": "red"}
    assert any("모르는 조건 'colour'" in x for x in issues(data, g))
    # a named list counts its own names, every one written in the guide
    g = good()
    g["counts"].append({"n": 2, "what": "[샘플] 대표 음식", "names": ["따로국밥", "막창구이"]})
    g["body"][0]["text"] += " 대표 음식 2가지는 따로국밥과 막창구이입니다."
    assert issues(data, g) == []
    g["counts"][-1]["names"] = ["따로국밥", "납작만두"]
    assert "counts[3] names가 글에 없음: 납작만두" in issues(data, g)


def test_a_place_count_claim_needs_a_count(data):
    g = good()
    g["body"][1]["text"] += " 같은 길에 카페가 22곳 있습니다."   # 22 is in the facts (22:00), not a count
    assert "body[1].text 'N곳' 개수 주장 ['22']이 counts·items 개수에 없음" in issues(data, g)
    g = good()
    g["body"][1]["text"] += " 두 곳 모두 주차할 수 있습니다."
    assert "body[1].text 'N곳' 개수 주장 ['2']이 counts·items 개수에 없음" not in issues(data, g)   # 2 is a count
    g["body"][1]["text"] += " 네 곳은 공평동입니다."
    assert "body[1].text 'N곳' 개수 주장 ['4']이 counts·items 개수에 없음" in issues(data, g)
    g = good()
    g["summary"] = "[샘플] 월요일에 문 여는 식당이 있습니다."
    assert "summary에 데이터에서 센 숫자(counts의 n 또는 items 개수)가 없음" in issues(data, g)


def test_wording_stock_and_copies_are_blocked(data):
    g = good()
    g["body"][0]["text"] += " 다양한 메뉴를 즐길 수 있어 추천합니다."
    g["body"][1]["text"] += " 인기 카페입니다."
    g["items"][0]["reason"] = f"{FOOD}은 {ADMIN} {GU} 공평동에 있는 음식점입니다."
    found = issues(data, g)
    assert any(x.startswith("body[0].text 상투어") for x in found)
    assert any(x.startswith("body[0].text 추천·권유") for x in found)
    assert any(x.startswith("body[1].text 근거 없는 수식어") for x in found)
    assert any(x.startswith("items[0].reason 첫 문장이 상투구") for x in found)
    g = good()
    g["body"][1]["text"] += " 2층 전시실에 오래된 지도와 생활 도구를 모아 두었습니다."
    found = issues(data, g)
    assert any(x.startswith(f"body[1].text TourAPI 소개문 복사") and MUSEUM in x for x in found)
    # a place name that carries a banned word is removed before the check
    assert gc.check_guide(good(), gc.Data(data)) == []


def test_shape_and_human_fields(data):
    g = good()
    g.update(title="[샘플] 월요일 식당", slug="월요일", status="published", reviewed_at="2026-10-11")
    g["body"] = g["body"][:1]
    found = issues(data, g)
    assert "title은 질문형('…?')" in found
    assert "slug 형식 오류: '월요일' (a-z·0-9·하이픈, 60자 이하)" in found
    assert "새 가이드의 status는 'draft'(지금 'published') — 공개는 사람이 정한다" in found
    assert "새 가이드의 reviewed_at는 비워 둔다 — 사람이 정한다" in found
    assert "body는 2절 이상(지금 1절)" in found
    g = good()
    g["slug"] = ""
    assert any(x.startswith("slug 없음") and "'woryoil-sikdang'" in x for x in issues(data, g))   # slugify(label)
    g = good()
    g.update(id="guide-old", slug="sample-old-guide")       # an update of the stored guide keeps its human fields
    assert "status를 바꿈('published' → 'draft') — 사람이 정한다" in issues(data, g)
    g.update(status="published", reviewed_at="2026-10-09")
    assert issues(data, g) == []
    g = good()
    g["slug"] = "sample-old-guide"
    assert "slug가 다른 가이드와 겹침: sample-old-guide" in issues(data, g)
    g = good()
    g["checked_at"] = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    assert any(x.startswith("checked_at이 미래") for x in issues(data, g))


def test_faq_rules(data):
    g = good()
    g["faq"] = [{"q": "[샘플] 월요일에 여나", "a": "엽니다.", "source": TOUR},
                {"q": "[샘플] 박물관은 무료인가요?", "a": "무료입니다.", "source": "https://blog.example.com"},
                {"q": "[샘플] 막창집은 몇 시까지 여나요?", "a": ""}]
    found = issues(data, g)
    assert "faq[0].q 존댓말 의문형('~나요?/~인가요?')이 아님: [샘플] 월요일에 여나" in found
    assert "faq[1].source는 sources의 url·name 중 하나: https://blog.example.com" in found
    assert "faq[1] 같은 질문이 가이드 guide-old에 있음: [샘플] 박물관은 무료인가요?" in found
    assert "faq[2] q·a가 비어 있음" in found


# ------------------------------------------------------------------ files, merge, cli
def test_review_and_merge(data, tmp_path, capsys):
    work = tmp_path / "work"
    clean, dirty = good(), {**good(), "id": "guide-t2", "slug": "sample-two", "summary": "[샘플] 인기 식당 3곳입니다."}
    write(work / "guide-t1.json", clean)
    write(work / "guide-t2.json", dirty)
    assert gc.main(["check-guide", "--data", str(data), str(work / "guide-t1.json")]) == 0
    assert "OK — 가이드 1편 통과" in capsys.readouterr().out
    assert gc.main(["check-guide", "--data", str(data), str(work / "guide-t2.json"), "--json"]) == 1
    rep = json.loads(capsys.readouterr().out)
    assert rep["ok"] is False and rep["issues"][0]["id"] == "guide-t2"

    before = (data / "guides.json").read_bytes()
    assert gc.main(["merge", "--data", str(data), str(work / "guide-t1.json"), str(work / "guide-t2.json"),
                    "--dry-run"]) == 1
    assert (data / "guides.json").read_bytes() == before
    res = gc.merge([work / "guide-t1.json", work / "guide-t2.json"], data=data)
    assert (res["merged"], res["refused"], res["merged_ids"]) == (1, 1, ["guide-t1"])
    stored = json.loads((data / "guides.json").read_text("utf-8"))
    assert [g["id"] for g in stored] == ["guide-old", "guide-t1"] and stored[1] == clean
    assert not list(data.glob(".*.tmp"))
    # the merged guide is now stored: checking it again is clean (its own FAQ is not a repeat)
    write(work / "stored.json", {"guides": [stored[1]]})
    assert gc.main(["check-guide", "--data", str(data), str(work / "stored.json")]) == 0
    capsys.readouterr()
    # two guides checked together may not share a FAQ question
    twin = {**good(), "id": "guide-t3", "slug": "sample-three"}
    write(work / "guide-t3.json", twin)
    rep = gc.review([work / "guide-t1.json", work / "guide-t3.json"], data=data)
    assert any("같은 질문이 가이드 guide-t1에 있음" in x for x in rep["rows"][1]["issues"])


def test_merge_writes_nothing_when_guides_json_changed_meanwhile(data, tmp_path, monkeypatch):
    write(tmp_path / "g.json", good())
    real = gc.review

    def review_then_someone_writes(*args, **kwargs):
        rep = real(*args, **kwargs)
        write(data / "guides.json", [STORED, {"id": "guide-x"}])
        return rep

    monkeypatch.setattr(gc, "review", review_then_someone_writes)
    with pytest.raises(SystemExit, match="바뀌었습니다"):
        gc.merge([tmp_path / "g.json"], data=data)
    assert [g["id"] for g in json.loads((data / "guides.json").read_text("utf-8"))] == ["guide-old", "guide-x"]


def test_count_cli(data, capsys):
    assert gc.main(["count", "--data", str(data), '{"kind": "food", "closes_after": "24:00"}', "--list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"n": 1, "places": [{"slug": "sample-makchang", "name": MAK, "district": GU, "area": "공평동"}]}
    assert gc.main(["count", "--data", str(data), '{"kinds": "food"}']) == 1
    assert "모르는 조건 'kinds'" in capsys.readouterr().out


def test_the_tool_names_no_city():
    path = ROOT / "tools" / "guide_content.py"
    consts = [(f"{path.name}:{n.lineno}", n.value) for n in ast.walk(ast.parse(path.read_text("utf-8")))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    patterns = [getattr(literals, n) for n in dir(literals) if n.endswith("_RX")]
    assert len(consts) > 50 and len(patterns) == 2
    assert [h for rx in patterns for h in literals.hits(rx, consts)] == []


def test_after_launch_only_published_places_count(data):
    """Once some place is published, a draft record (a new TourAPI place awaiting its summary and approval) is neither
    counted nor referable: the guide's '이 사이트에 실린 n곳' stays true when drafts arrive."""
    rows = places()
    for p in rows:
        if p["id"] in ("s-1001", "s-1002", "s-1003"):
            p["status"] = "published"
    write(data / "places.json", rows)
    D = gc.Data(data)
    assert sorted(p["slug"] for p in D.places) == ["sample-food", "sample-makchang", "sample-museum"]
    assert "sample-cafe" in D.hidden and "sample-cafe" not in D.by_slug
    # the new keys count published places only: the draft cafe's station, designation and course stop do not count,
    # and the draft course never counts (its stop, the published food place, is not on a published course)
    slugs = lambda w: [p["slug"] for p in gc.select(D, w)]
    assert slugs({"rail_line": "2호선"}) == ["sample-museum"]
    assert slugs({"designation": True}) == ["sample-food"]
    assert slugs({"designation": "goodprice"}) == []
    assert slugs({"course": True}) == ["sample-museum", "sample-makchang"]
    assert slugs({"course": "[샘플] 시티투어"}) == ["sample-museum"]
    assert slugs({"lot_paid": False}) == ["sample-museum", "sample-food"]
    # a guide citing the draft cafe is refused (not referable), so its nearby rows and designation ground nothing
    g = good()
    g["body"][1]["text"] += " 별빛역까지 직선 700m입니다."
    found = issues(data, g)
    assert "mentions places.json에 없는 장소: sample-cafe" not in found and "mentions 중복·제외된 장소: sample-cafe" in found
    assert any(x.startswith("body[1].text 근거 없는 숫자 [") and "'700'" in x for x in found)
