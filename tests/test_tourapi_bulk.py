"""tools/tourapi_bulk.py — local matching keys and licensed list photos, with the metro fixture's city (names and roads
are made up; only the 구·군 names are real)."""
import json
from pathlib import Path

from pipeline import city as city_mod
from tools.tourapi_bulk import fill, match, name_key, photo_title, road_key

ROOT = Path(__file__).resolve().parent.parent
METRO = city_mod.from_site(json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8")))


def _index(items):
    by_name, by_road = {}, {}
    for it in items:
        by_name.setdefault(name_key(it["title"], METRO), []).append(it)
        by_road.setdefault(road_key(it["addr1"], METRO), []).append(it)
    return by_name, by_road


def test_bulk_match_rules_and_licensed_photo_only():
    items = [
        {"contentid": "1", "contenttypeid": "12", "title": "샘플사(대구)", "addr1": "대구광역시 중구 샘플사길 16"},
        {"contentid": "2", "contenttypeid": "32", "title": "게스트하우스 소설여행", "addr1": "대구 중구 샘플로 516-1"},
        {"contentid": "3", "contenttypeid": "32", "title": "히노키잠(1호점)", "addr1": "대구광역시 중구 샘플6길 54-1"},
    ]
    by_name, by_road = _index(items)
    place = lambda name, kind, addr: {"name": name, "kind": kind, "facts": {"address": addr}}
    assert match(place("샘플사", "attraction", "대구광역시 중구 샘플사길 16(샘플동)"), by_name, by_road, METRO)[1] == "same_name"
    assert match(place("소설여행", "stay", "대구광역시 중구 샘플로 516-1 (샘플동)"), by_name, by_road, METRO)[0]["contentid"] == "2"
    assert match(place("히노키잠 게스트하우스 2호점", "stay", "대구광역시 중구 샘플6길 54-1"), by_name, by_road, METRO)[0] is None
    assert match(place("샘플사", "food", "대구광역시 중구 샘플사길 16"), by_name, by_road, METRO)[0] is None  # kind must agree
    # the same road and number in another 구·군 is another address: no address-based match
    assert match(place("소설여행", "stay", "대구광역시 수성구 샘플로 516-1"), by_name, by_road, METRO)[0] is None

    p = {"name": "샘플사", "images": []}
    fill(p, {**items[0], "mapx": "128.6", "mapy": "35.87", "firstimage": "http://x/a.jpg", "cpyrhtDivCd": "Type3",
             "ldong_signgu_cd": "99101", "ldong_signgu_name": "중구"}, "same_name", ["KOGL-1", "KOGL-3"], METRO)
    assert p["images"][0] == {"url": "https://x/a.jpg", "alt": "샘플사", "credit": "한국관광공사",
                              "license": "KOGL-3", "source": "TourAPI"}
    assert p["tourapi"]["ldong_signgu_cd"] == "99101" and p["tourapi"]["ldong_signgu_name"] == "중구"
    q = {"name": "샘플사", "images": []}
    fill(q, {**items[0], "firstimage": "http://x/b.jpg", "cpyrhtDivCd": "Type2"}, "same_name", ["KOGL-1", "KOGL-3"],
         METRO)
    assert q["images"] == [] and "ldong_signgu_cd" not in q["tourapi"]


def test_road_key_carries_the_district_and_a_lot_number_ga_is_not_a_road():
    assert road_key("대구광역시 중구 샘플로2길 80 (삼덕동1가)", METRO) == "중구|샘플로2길80"
    assert road_key("대구 수성구 시험로 42", METRO) == "수성구|시험로42"            # the short alias form
    assert road_key("대구광역시 중구 샘플로2가 88-1", METRO) == ""                 # 법정동 'N가' + 지번, not road no. 2
    assert road_key("샘플로 7", METRO) == "|샘플로7"                                # no 구·군 in the address
    assert road_key("대구광역시 중구", METRO) == ""


def test_name_key_and_photo_title_use_the_city():
    assert name_key("대구 샘플 골목", METRO) == name_key("샘플 골목", METRO) == "샘플골목"
    assert name_key("대구탕 골목", METRO) == "대구탕골목"                  # a dish named like the city is not the city
    assert photo_title("[백년가게]샘플반점(대구 중구)", METRO) == "샘플반점"
    assert photo_title("샘플관(대구) 별관", METRO) == "샘플관(대구) 별관"   # the tail is removed at the end only


def test_barrier_free_run_merges_checked_titles_only_and_reports(tmp_path, monkeypatch):
    """--barrier-free (the first site's QA 2026-10-15): KorWithService2 for published places with a contentid; an answer is merged
    only when the same service's detailCommon2 title is our TourAPI title; per-run cap; a report for a person."""
    import io
    import urllib.parse
    from pipeline import tourapi
    from tools.tourapi_bulk import main
    from tools.tourapi_details import BARRIER_FREE

    def ok(items):
        return json.dumps({"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": items}}}})

    answers = {("detailWithTour2", "1"): [{"contentid": "1", "wheelchair": "대여 가능(5대/안내데스크)",
                                           "parking": "장애인 주차장 있음_무장애 편의시설", "stroller": ""}],
               ("detailCommon2", "1"): [{"contentid": "1", "title": "샘플근대역사관(대구 중구)"}],
               ("detailWithTour2", "2"): [{"contentid": "2", "wheelchair": "", "restroom": ""}],
               ("detailWithTour2", "3"): [{"contentid": "3", "restroom": "장애인 화장실 있음"}],
               ("detailCommon2", "3"): [{"contentid": "3", "title": "다른 곳"}]}
    seen = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=20):
        url = urllib.parse.urlsplit(req.full_url)
        op, cid = url.path.rsplit("/", 1)[1], urllib.parse.parse_qs(url.query)["contentId"][0]
        seen.append((url.path.split("/")[2], op, cid))
        return Resp(ok(answers[(op, cid)]).encode("utf-8"))

    monkeypatch.setattr(tourapi.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(tourapi.time, "sleep", lambda s: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOURAPI_KEY", "synthetic-key")
    data = tmp_path / "data" / "x"
    data.mkdir(parents=True)
    site = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))
    site["tourapi"] = {**(site.get("tourapi") or {}), "min_interval": 0}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    base = {"kind": "attraction", "status": "published", "facts_source": {"provider": "대구관광"}}
    # the city tail of a provider title ('(대구 중구)', City.title_suffix_rx) does not make the titles differ
    places = [{**base, "id": "a", "name": "샘플근대역사관", "facts": {"wheelchair": "대여가능( 8 대)"},
               "tourapi": {"contentid": "1", "title": "샘플근대역사관"}},
              {**base, "id": "b", "name": "빈 곳", "facts": {}, "tourapi": {"contentid": "2", "title": "빈 곳"}},
              {**base, "id": "c", "name": "엉뚱한 곳", "facts": {}, "tourapi": {"contentid": "3", "title": "엉뚱한 곳"}},
              {**base, "id": "d", "name": "초안", "status": "draft", "facts": {}, "tourapi": {"contentid": "4"}},
              {**base, "id": "e", "name": "번호 없음", "facts": {}}]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    assert main(["--data", str(data), "--barrier-free", "--max-calls", "10"]) == 0
    assert {s[0] for s in seen} == {"KorWithService2"} and ("KorWithService2", "detailCommon2", "2") not in seen
    out = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    a = out["a"]
    assert a["facts"]["wheelchair"] == "대여가능( 8 대)"                       # ours stays; KTO's beside it
    assert a["fact_alternatives"]["wheelchair"][0]["value"] == "대여 가능(5대/안내데스크)"
    assert a["fact_alternatives"]["wheelchair"][0]["provider"] == BARRIER_FREE
    assert a["facts"]["accessible_parking"] == "장애인 주차장 있음"
    assert a["fact_sources"]["accessible_parking"]["provider"] == BARRIER_FREE
    assert out["c"]["facts"] == {} and out["b"]["facts"] == {} and out["d"]["facts"] == {}
    report = (tmp_path / "reports" / "tourapi_barrier_free.md").read_text("utf-8")
    assert "샘플근대역사관 · wheelchair · 값이 다름: 기존 '대여가능( 8 대)' / 무장애 '대여 가능(5대/안내데스크)'" in report
    assert "엉뚱한 곳 (3): 무장애 '다른 곳' ≠ TourAPI '엉뚱한 곳'" in report
    stats = json.loads((tmp_path / "reports" / "tourapi_barrier_free.json").read_text("utf-8"))
    assert stats["targets"] == 3 and stats["with_data"] == 1 and stats["no_data"] == ["빈 곳"]
    assert stats["live_calls"] == 5 and (data.parent / "cache" / "tourapi" / "barrier_free").is_dir()
    # the per-run cap stops the run and says so; the next run continues from the cache
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    import shutil
    shutil.rmtree(data.parent / "cache")
    assert main(["--data", str(data), "--barrier-free", "--max-calls", "1"]) == 0
    stats = json.loads((tmp_path / "reports" / "tourapi_barrier_free.json").read_text("utf-8"))
    assert "호출 상한 1회" in stats["stopped"] and stats["live_calls"] == 1


def test_nearby_skips_the_family_and_fills_the_slots(tmp_path, monkeypatch):
    """compute_nearby (pipeline/relations.py, 2026-10-16): a place's own family — its parent, its parts, the other page
    for its building — is never its nearby place, an alias never shows while its parent can; the next places fill the
    three slots. --nearby-only recomputes from stored coordinates without a TourAPI client."""
    import tools.tourapi_bulk as tb

    def p(i, lat, part_of=None):
        r = {"id": i, "name": i.upper(), "slug": i, "kind": "attraction", "status": "published",
             "geo": {"lat": 35.87 + lat, "lng": 128.6}, "tourapi": {"contentid": f"c{i}"}}
        if part_of:
            r["part_of"] = {"id": part_of[0], "rel": part_of[1], "basis": ["geo"], "checked_at": "2026-10-16"}
        return r
    temple = p("temple", 0)
    hall = p("hall", 0.00001, ("temple", "inside"))
    bank = p("bank", 0.0002)
    museum = p("museum", 0.0002, ("bank", "same_building"))
    others = [p(f"o{k}", 0.001 * (k + 1)) for k in range(4)]
    places = [temple, hall, bank, museum, *others]
    assert tb.compute_nearby(places, "2026-10-16") == len(places)
    near = lambda x: [n["internal_slug"] for n in x["nearby"]]  # noqa: E731
    assert near(temple) == ["bank", "o0", "o1"]            # not its hall; the bank once (its alias museum skipped)
    assert near(hall) == ["bank", "o0", "o1"]              # not its temple
    assert near(bank) == ["hall", "temple", "o0"]          # not museum, its own building (hall is the nearer)
    assert near(museum) == ["hall", "temple", "o0"]
    assert "museum" not in near(others[0])
    # the same run from the file: no TourAPI client is created
    monkeypatch.setattr(tb, "from_site_config", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API")))
    data = tmp_path / "data"
    data.mkdir()
    for x in places:
        x.pop("nearby"), x.pop("nearby_source")
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    assert tb.main(["--data", str(data), "--nearby-only"]) == 0
    got = {x["id"]: x for x in json.loads((data / "places.json").read_text("utf-8"))}
    assert [n["internal_slug"] for n in got["temple"]["nearby"]] == ["bank", "o0", "o1"]


def test_barrier_free_and_nearby_only_run_alone(tmp_path, capsys):
    """The two stand-alone modes refuse the gathering options (exit 2, configuration error) before any call."""
    from tools.tourapi_bulk import main

    data = tmp_path / "data"
    data.mkdir()
    (data / "site.json").write_text((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"), "utf-8")
    (data / "places.json").write_text("[]", "utf-8")
    assert main(["--data", str(data), "--barrier-free", "--details"]) == 2
    assert main(["--data", str(data), "--barrier-free", "--courses"]) == 2
    assert main(["--data", str(data), "--nearby-only", "--district", "중구"]) == 2
    assert main(["--data", str(data), "--nearby-only", "--offline"]) == 2
    assert "따로 실행" in capsys.readouterr().err
