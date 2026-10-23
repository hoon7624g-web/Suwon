"""tools/tourapi_bulk.py --courses: TourAPI 여행코스 (contentTypeId 25) into <data>/tourapi_courses.json, end to end through
the real client (pipeline.tourapi.TourAPI: cache, call cap) against a fake TourAPI server. No network, no key.
The metro fixture's city; region codes are synthetic and course and place names made up."""
import io
import json
import urllib.parse
from pathlib import Path

import pytest

from pipeline import city as city_mod
from pipeline import tourapi
from tools import tourapi_bulk

ROOT = Path(__file__).resolve().parent.parent
METRO_SITE = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))
METRO = city_mod.from_site(METRO_SITE)
DISTRICTS = list(METRO.districts)
REGN = "990"
SIGNGU = {d: str(99101 + i) for i, d in enumerate(DISTRICTS)}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items} if items else ""}}}).encode()


COURSES = [  # (contentid, title, 구·군 of the list, photo licence type)
    ("7001", "[샘플] 골목 한 바퀴 코스", "중구", "Type1"),
    ("7001", "[샘플] 골목 한 바퀴 코스", "동구", "Type1"),          # the provider lists it under two 구·군
    ("7002", "샘플 호숫가 반나절 코스(대구 수성구)", "수성구", "Type2"),
]
SUBS = {"7001": [{"subnum": "1", "subname": "샘플 전시관", "subcontentid": "100", "subdetailoverview": "<p>전시관 소개</p>"},
                 {"subnum": "0", "subname": "샘플 시장", "subcontentid": "200"},
                 {"subnum": "2", "subname": "이름만 같은 곳", "subcontentid": ""}],
        "7002": [{"subnum": "0", "subname": "샘플 호수", "subcontentid": "999"}]}


class Server:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def answer(self, op: str, q: dict) -> list[dict]:
        if op == "ldongCode":
            if "lDongRegnCd" not in q:
                return [{"code": REGN, "name": "대구광역시"}]
            return [{"code": c, "name": d} for d, c in SIGNGU.items()]
        if op == "areaBasedList":
            rows, page = int(q.get("numOfRows", 10)), int(q.get("pageNo", 1))
            pool = [{"contentid": cid, "contenttypeid": "25", "title": t, "addr1": f"대구광역시 {d}",
                     "cat1": "C01", "cat2": "C0112", "cat3": "C01120001", "modifiedtime": "20260101000000",
                     "firstimage": f"http://img.test/{cid}.jpg", "cpyrhtDivCd": lic}
                    for cid, t, d, lic in COURSES
                    if q.get("contentTypeId") == "25" and q.get("lDongSignguCd") == SIGNGU[d]]
            return pool[(page - 1) * rows:page * rows]
        if op == "detailCommon":
            return [{"contentid": q["contentId"], "overview": "<b>코스 소개</b> 문장", "modifiedtime": "20260202000000"}]
        if op == "detailIntro":
            assert q["contentTypeId"] == "25"
            return [{"distance": "2.5km", "taketime": "당일", "schedule": "", "theme": "도보코스",
                     "infocentertourcourse": "053-000-0000"}]
        if op == "detailInfo":
            assert q["contentTypeId"] == "25"
            return SUBS.get(q["contentId"], [])
        return []

    def urlopen(self, req, timeout=20):
        url = urllib.parse.urlsplit(req.full_url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items() if k != "serviceKey"}
        op = url.path.rsplit("/", 1)[1][:-1]
        self.calls.append((op, q))
        return FakeResp(_ok(self.answer(op, q)))

    def ops(self, op):
        return [q for o, q in self.calls if o == op]


PLACES = [{"id": "m-1", "slug": "saempeul-jeonsigwan", "name": "샘플 전시관", "kind": "attraction", "status": "published",
           "tourapi": {"contentid": "100"}},
          {"id": "m-2", "slug": "saempeul-sijang", "name": "샘플 시장", "kind": "attraction", "status": "draft",
           "tourapi": {"contentid": "200"}},
          {"id": "m-3", "slug": "ireumman-gateun-got", "name": "이름만 같은 곳", "kind": "attraction",
           "status": "published"}]


@pytest.fixture
def city_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOURAPI_KEY", "synthetic-test-key")
    data = tmp_path / "data" / "metro"
    data.mkdir(parents=True)
    site = json.loads(json.dumps(METRO_SITE))
    site["tourapi"]["min_interval"] = 0
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    (data / "places.json").write_text(json.dumps(PLACES, ensure_ascii=False), "utf-8")
    return data


def _serve(monkeypatch):
    server = Server()
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", server.urlopen)
    return server


def test_courses_lists_type_25_per_district_and_keeps_the_provider_values(city_dir, monkeypatch):
    server = _serve(monkeypatch)
    places_before = (city_dir / "places.json").read_bytes()
    stats = tourapi_bulk.run_courses(city_dir, max_calls=500, offline=False)
    assert stats["list_complete"] and not stats.get("stopped")
    area = server.ops("areaBasedList")
    assert {q["contentTypeId"] for q in area} == {"25"}                       # the course type only
    assert sorted(q["lDongSignguCd"] for q in area) == sorted(SIGNGU.values())  # every 구·군, by ldongCode2's codes
    assert stats["courses"] == stats["done"] == 2 and stats["list"]["duplicates"] == 1
    assert len(server.ops("detailCommon")) == len(server.ops("detailIntro")) == len(server.ops("detailInfo")) == 2
    out = json.loads((city_dir / "tourapi_courses.json").read_text("utf-8"))
    assert out["_meta"]["content_type"] == "25" and out["_meta"]["courses_detailed"] == 2
    by = {c["contentid"]: c for c in out["courses"]}
    c = by["7001"]
    assert c["title"] == "골목 한 바퀴 코스" and c["ldong_signgu_name"] == "중구"   # the first list it came in
    assert c["intro"] == {"distance": "2.5km", "taketime": "당일", "schedule": "", "theme": "도보코스",
                          "infocenter": "053-000-0000"}
    # sub-stops in subnum order; matched by contentid only (status recorded), never by name
    assert [(s["subnum"], s["subname"], s["place_slug"], s["place_status"], s["match"]) for s in c["stops"]] == [
        (0, "샘플 시장", "saempeul-sijang", "draft", "contentid"),
        (1, "샘플 전시관", "saempeul-jeonsigwan", "published", "contentid"),
        (2, "이름만 같은 곳", "", "", "")]
    assert c["stops"][1]["overview"] == "전시관 소개" and c["overview"] == "코스 소개 문장"   # tags stripped, kept for checks
    assert c["image"] == {"url": "https://img.test/7001.jpg", "license": "KOGL-1", "credit": "한국관광공사",
                          "source": "TourAPI"}
    assert by["7002"]["title"] == "샘플 호숫가 반나절 코스" and "image" not in by["7002"]   # Type2: no photo
    assert by["7002"]["stops"][0]["place_slug"] == ""                         # contentid 999 is not one of ours
    assert (city_dir / "places.json").read_bytes() == places_before
    assert not (city_dir / "courses.json").exists()
    report = (Path("reports") / "tourapi_courses.md").read_text("utf-8")
    assert "상세 2" in report and "saempeul-jeonsigwan(published)" in report


def test_courses_call_cap_writes_what_is_done_and_says_where_it_stopped(city_dir, monkeypatch):
    _serve(monkeypatch)
    # 2 ldongCode + 9 lists + one course's 3 details = 14: the second course is cut off
    stats = tourapi_bulk.run_courses(city_dir, max_calls=14, offline=False)
    assert stats["stopped_at"] == "course_details" and stats["done"] == 1
    out = json.loads((city_dir / "tourapi_courses.json").read_text("utf-8"))
    assert [c["contentid"] for c in out["courses"]] == ["7001"] and "호출 상한" in out["_meta"]["stopped"]
    # the next run goes on from the cache
    stats = tourapi_bulk.run_courses(city_dir, max_calls=3, offline=False)
    assert not stats.get("stopped") and stats["done"] == 2 and stats["live_calls"] == 3


def test_courses_without_the_list_write_nothing(city_dir, monkeypatch, capsys):
    _serve(monkeypatch)
    code = tourapi_bulk.main(["--data", str(city_dir), "--courses", "--max-calls", "5"])
    err = capsys.readouterr().err
    assert code == 1 and "tourapi_courses.json을 쓰지 않았습니다" in err and "Traceback" not in err
    assert not (city_dir / "tourapi_courses.json").exists()


def test_courses_district_filter_keeps_the_other_districts_courses(city_dir, monkeypatch):
    server = _serve(monkeypatch)
    kept = {"contentid": "6000", "title": "북구 코스", "ldong_signgu_name": "북구", "stops": [],
            "intro": {"distance": "", "taketime": "", "schedule": "", "theme": "", "infocenter": ""}}
    (city_dir / "tourapi_courses.json").write_text(json.dumps({"_meta": {}, "courses": [kept]}, ensure_ascii=False),
                                                    "utf-8")
    stats = tourapi_bulk.run_courses(city_dir, max_calls=500, offline=False, districts=["수성구"])
    assert [q["lDongSignguCd"] for q in server.ops("areaBasedList")] == [SIGNGU["수성구"]]
    assert stats["done"] == 1
    out = json.loads((city_dir / "tourapi_courses.json").read_text("utf-8"))
    assert {c["contentid"] for c in out["courses"]} == {"6000", "7002"}


def test_courses_is_its_own_run(city_dir, capsys):
    assert tourapi_bulk.main(["--data", str(city_dir), "--courses", "--details"]) == 2
    assert "--courses는" in capsys.readouterr().err
