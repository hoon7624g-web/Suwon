"""tools/tourapi_bulk.py over a metropolitan city (tests/fixtures/metro/site.json: 9 구·군), end to end through the
real client (pipeline.tourapi.TourAPI: cache, call cap) against a fake TourAPI server. No network, no key.

The region codes are synthetic (REGN, SIGNGU): the provider's codes are only ever read from ldongCode2 at run time.
Place names and roads are made up; only the 구·군 names are real."""
import io
import json
import shutil
import urllib.parse
from pathlib import Path

import pytest

from pipeline import city as city_mod
from pipeline import tourapi
from pipeline.slugs import is_slug
from pipeline.tourapi import LDong, RegionCodeError, fetch_festivals, resolve_ldong
from tools import tourapi_bulk
from tools.tourapi_bulk import LIST_TYPES

ROOT = Path(__file__).resolve().parent.parent
METRO_DIR = ROOT / "tests" / "fixtures" / "metro"
METRO_SITE = json.loads((METRO_DIR / "site.json").read_text("utf-8"))
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


def _item(cid, ctype, title, district, road):
    return {"contentid": cid, "contenttypeid": ctype, "title": title, "addr1": f"대구광역시 {district} {road}",
            "mapx": "128.6", "mapy": "35.87", "_signgu": SIGNGU[district]}


def _world_items():
    items = [_item(str(100 + i), "12", f"[샘플] {d} 전시관", d, f"샘플로 {i + 1}") for i, d in enumerate(DISTRICTS)]
    items += [
        {**_item("100", "12", "[샘플] 중구 전시관", "중구", "샘플로 1"), "_signgu": SIGNGU["동구"]},  # listed twice
        _item("501", "32", "바다 게스트하우스", "중구", "샘플길 1"),
        _item("502", "32", "바다 게스트하우스", "수성구", "시험길 2"),
        _item("503", "32", "바다 게스트하우스", "중구", "샘플길 3"),
        _item("504", "14", "샘플 미술관(대구 중구)", "중구", "샘플길 4"),
        _item("505", "39", "博物館", "북구", "샘플로 5"),
    ]
    return items


def _festivals():
    out = [{"contentid": f"9{i:03d}", "title": f"2026 샘플 축제 {i}", "eventstartdate": "20261009",
            "eventenddate": "20261011", "addr1": "대구광역시 중구 샘플로 1"} for i in range(100)]
    out += [dict(out[0]), dict(out[1])]  # the provider repeats two on the next page
    out += [{"contentid": "8001", "title": "2026 이어지는 축제", "eventstartdate": "20261101",
             "eventenddate": "20261102", "addr1": "대구광역시 수성구 시험로 1"}]
    return out


class Server:
    """A fake TourAPI answering by operation and parameters; it records every request."""

    def __init__(self, missing=()):
        self.items = _world_items()
        self.festivals = _festivals()
        self.missing = set(missing)
        self.calls: list[tuple[str, dict]] = []

    def answer(self, op: str, q: dict) -> list[dict]:
        rows, page = int(q.get("numOfRows", 10)), int(q.get("pageNo", 1))
        if op == "ldongCode":
            if "lDongRegnCd" not in q:
                return [{"code": "980", "name": "다른광역시"}, {"code": REGN, "name": "대구광역시"}]
            return [{"code": c, "name": d} for d, c in SIGNGU.items() if d not in self.missing] \
                if q["lDongRegnCd"] == REGN else []
        if op == "areaBasedList":
            pool = [{k: v for k, v in it.items() if k != "_signgu"} for it in self.items
                    if it["contenttypeid"] == q.get("contentTypeId")
                    and q.get("lDongRegnCd") == REGN and q.get("lDongSignguCd") in (None, it["_signgu"])]
            return pool[(page - 1) * rows:page * rows]
        if op == "searchFestival":
            return self.festivals[(page - 1) * rows:page * rows]
        if op == "detailCommon":
            it = next((x for x in self.items + self.festivals if x["contentid"] == q["contentId"]), {})
            return [{"contentid": q["contentId"], "title": it.get("title", ""), "addr1": it.get("addr1", ""),
                     "tel": "053-000-0000", "modifiedtime": "20261001000000"}]
        if op == "detailIntro":
            return [{"checkintime": "15:00"}] if q.get("contentTypeId") == "32" else [{}]
        if op == "detailImage":
            it = next((x for x in self.items if x["contentid"] == q["contentId"]), {})
            return [{"originimgurl": f"http://img.test/{q['contentId']}.jpg", "imgname": it.get("title", ""),
                     "cpyrhtDivCd": "Type1"}]
        return []

    def urlopen(self, req, timeout=20):
        url = urllib.parse.urlsplit(req.full_url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items() if k != "serviceKey"}
        op = url.path.rsplit("/", 1)[1][:-1]  # 'areaBasedList2' -> 'areaBasedList'
        self.calls.append((op, q))
        return FakeResp(_ok(self.answer(op, q)))

    def ops(self, op):
        return [q for o, q in self.calls if o == op]


@pytest.fixture
def city_dir(tmp_path, monkeypatch):
    """A data folder with the metro site.json (no places.json: it starts as []) in a scratch working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOURAPI_KEY", "synthetic-test-key")
    data = tmp_path / "data" / "metro"
    data.mkdir(parents=True)
    site = json.loads(json.dumps(METRO_SITE))
    site["tourapi"]["min_interval"] = 0
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    (data / "events.json").write_text(json.dumps([
        {"id": "e-x", "name": "[샘플] 다른 시리즈", "start_date": "2026-05-01", "slug": "saempeul-chukje-2"}],
        ensure_ascii=False), "utf-8")
    return data


def _serve(monkeypatch, server):
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", server.urlopen)
    return server


def test_metro_run_loops_every_district_dedupes_and_stores_ascii_slugs(city_dir, monkeypatch):
    server = _serve(monkeypatch, Server())
    stats = tourapi_bulk.run(city_dir, max_calls=5000, offline=False, add_new=True, events=True)
    assert stats["list_complete"] and not stats.get("stopped")
    # every 구·군 of site.json, every list type, by the codes ldongCode2 gave — never the whole 시·도 at once
    area = server.ops("areaBasedList")
    assert {(q["lDongSignguCd"], q["contentTypeId"]) for q in area} == \
        {(c, t) for c in SIGNGU.values() for t in LIST_TYPES}
    assert all(q["lDongRegnCd"] == REGN for q in area) and len(area) == 9 * len(LIST_TYPES)
    assert [q.get("lDongRegnCd") for q in server.ops("ldongCode")] == [None, REGN]
    assert list(stats["list"]["by_district"]) == DISTRICTS and stats["list"]["duplicates"] == 1
    assert stats["list_items"] == 14
    places = json.loads((city_dir / "places.json").read_text("utf-8"))
    by_cid = {p["tourapi"]["contentid"]: p for p in places}
    assert len(places) == len(by_cid) == 14                                  # contentid 100 added once
    assert by_cid["100"]["tourapi"]["ldong_signgu_name"] == "중구"            # the first list it came in
    assert by_cid["108"]["tourapi"]["ldong_signgu_name"] == "군위군"
    assert by_cid["108"]["tourapi"]["ldong_signgu_cd"] == SIGNGU["군위군"]
    assert by_cid["501"]["slug"] == "bada-geseuteuhauseu"
    assert by_cid["503"]["slug"] == "bada-geseuteuhauseu-jung-gu"            # collision: the 구·군 first …
    assert by_cid["502"]["slug"] == "bada-geseuteuhauseu-suseong-gu"
    assert by_cid["504"]["name"] == "샘플 미술관" and by_cid["504"]["slug"] == "saempeul-misulgwan"
    assert by_cid["505"]["slug"] == "place-505"                              # no ASCII from the name
    assert by_cid["100"]["name"] == "중구 전시관" and by_cid["100"]["slug"] == "jung-gu-jeonsigwan"
    assert all(is_slug(p["slug"]) and "_slug_generated" not in p for p in places)
    assert len({p["slug"] for p in places}) == len(places)
    # --add-new order: site.json districts, then type, then title
    order = [p["tourapi"]["ldong_signgu_name"] for p in places]
    assert order == sorted(order, key=DISTRICTS.index)
    # festivals: the whole 시·도, every page until a short one, duplicates dropped, a stored slug each
    fest = server.ops("searchFestival")
    assert [(q["lDongRegnCd"], q.get("lDongSignguCd"), q["pageNo"]) for q in fest] == \
        [(REGN, None, "1"), (REGN, None, "2")]
    events = json.loads((city_dir / "events.json").read_text("utf-8"))
    new = [e for e in events if e.get("contentid")]
    assert stats["events"]["festival_items"] == len(new) == 101
    assert len({e["contentid"] for e in new}) == 101 and all(is_slug(e["slug"]) for e in new)
    slugs = {e["contentid"]: e["slug"] for e in new}
    assert slugs["9000"] == "saempeul-chukje-0" and slugs["9002"] == "saempeul-chukje-2-2"  # -2 is another series
    assert slugs["8001"] == "ieojineun-chukje"
    report = (Path("reports") / "tourapi_bulk.md").read_text("utf-8")
    assert "군위군 1" in report and "중복 제거 1" in report


def test_a_district_missing_from_ldongcode_is_an_explicit_error_and_nothing_is_written(city_dir, monkeypatch, capsys):
    server = _serve(monkeypatch, Server(missing={"군위군"}))
    (city_dir / "places.json").write_text("[]\n", "utf-8")
    events_before = (city_dir / "events.json").read_bytes()
    code = tourapi_bulk.main(["--data", str(city_dir), "--add-new", "--events"])
    err = capsys.readouterr().err
    assert code == 1 and "군위군이 대구광역시 코드 아래에 없음 — docs/rights.md 4절" in err and "Traceback" not in err
    assert not server.ops("areaBasedList")                                    # no list without every code
    assert (city_dir / "places.json").read_text("utf-8") == "[]\n"
    assert (city_dir / "events.json").read_bytes() == events_before
    report = json.loads((Path("reports") / "tourapi_bulk.json").read_text("utf-8"))
    assert report["stopped_at"] == "ldong" and not report["list_complete"] and "군위군" in report["stopped"]


@pytest.mark.parametrize("cap,stage", [(1, "ldong"), (10, "list"), (57, "gallery")])
def test_the_call_cap_is_reported_at_every_stage_without_a_partial_write(city_dir, monkeypatch, capsys, cap, stage):
    server = _serve(monkeypatch, Server())
    ours = [{"id": "metro-a", "slug": "jung-gu-jeonsigwan", "name": "[샘플] 중구 전시관", "kind": "attraction",
             "facts": {"address": "대구광역시 중구 샘플로 1"}},
            {"id": "metro-b", "slug": "suseong-gu-jeonsigwan", "name": "[샘플] 수성구 전시관", "kind": "attraction",
             "facts": {"address": "대구광역시 수성구 샘플로 6"}}]
    before = json.dumps(ours, ensure_ascii=False, indent=2) + "\n"
    (city_dir / "places.json").write_text(before, "utf-8")
    code = tourapi_bulk.main(["--data", str(city_dir), "--gallery", "--max-calls", str(cap)])
    out, err = capsys.readouterr()
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary["stopped_at"] == stage and "호출 상한" in summary["stopped"] and "Traceback" not in err
    report = (Path("reports") / "tourapi_bulk.md").read_text("utf-8")
    assert "중단" in report and "호출 상한" in report
    saved = (city_dir / "places.json").read_text("utf-8")
    if stage in ("ldong", "list"):  # the list is incomplete: nothing changes, the next run continues from the cache
        assert code == 1 and saved == before and not summary["list_complete"]
        assert len(server.calls) == cap
        server.calls.clear()
        assert tourapi_bulk.main(["--data", str(city_dir), "--max-calls", "5000"]) == 0
        assert len(server.calls) == 2 + 9 * len(LIST_TYPES) - cap
    else:  # matching and fills are whole; the gallery stopped after its first place
        assert code == 0 and summary["list_complete"]
        places = json.loads(saved)
        assert [p["tourapi"]["match_basis"] for p in places] == ["same_name", "same_name"]
        assert len(server.ops("detailImage")) == 1 and summary["gallery_added"] == 1


def test_district_filter_limits_new_places_and_rejects_unknown_names(city_dir, monkeypatch, capsys):
    _serve(monkeypatch, Server())
    stats = tourapi_bulk.run(city_dir, max_calls=5000, offline=False, add_new=True, districts=["수성구", "군위군"])
    places = json.loads((city_dir / "places.json").read_text("utf-8"))
    assert sorted(p["tourapi"]["ldong_signgu_name"] for p in places) == ["군위군", "수성구", "수성구"]
    assert stats["districts"] == ["수성구", "군위군"]
    assert tourapi_bulk.main(["--data", str(city_dir), "--district", "없는구"]) == 2
    assert "없는구" in capsys.readouterr().err


def test_offline_without_a_cache_exits_cleanly(city_dir, monkeypatch, capsys):
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network prohibited"))
    assert tourapi_bulk.main(["--data", str(city_dir), "--offline"]) == 1
    err = capsys.readouterr().err
    assert "오프라인 모드인데 캐시가 없습니다" in err and "Traceback" not in err
    assert not (city_dir / "places.json").exists()


# ------------------------------------------------------------------ unit: region codes and festival pages
class CodesAPI:
    def __init__(self, regions, under):
        self.regions, self.under = regions, under

    def ldong_code(self, regn=None, rows=100):
        return self.regions if regn is None else self.under.get(regn, [])


def test_resolve_ldong_takes_exact_names_only():
    under = {REGN: [{"code": c, "name": d} for d, c in SIGNGU.items()]}
    ld = resolve_ldong(CodesAPI([{"code": "980", "name": "대구광역시청"}, {"code": REGN, "name": "대구광역시"}], under), METRO)
    assert ld.regn_cd == REGN and [n for _, n in ld.signgu] == DISTRICTS and ld.whole_region
    assert ld.name_of(SIGNGU["군위군"]) == "군위군"
    with pytest.raises(RegionCodeError, match="0개"):
        resolve_ldong(CodesAPI([{"code": "980", "name": "대구"}], under), METRO)
    with pytest.raises(RegionCodeError, match="2개"):
        resolve_ldong(CodesAPI([{"code": REGN, "name": "대구광역시"}, {"code": "991", "name": "대구광역시"}], under), METRO)
    twice = {REGN: under[REGN] + [{"code": "99199", "name": "중구"}]}
    with pytest.raises(RegionCodeError, match=r"중구\(2개\)"):
        resolve_ldong(CodesAPI([{"code": REGN, "name": "대구광역시"}], twice), METRO)
    # a city inside a province (no districts): its locality, by exact name
    sample = city_mod.from_site(json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8")))
    ld = resolve_ldong(CodesAPI([{"code": "70", "name": sample.region_admin}],
                                {"70": [{"code": "7001", "name": sample.locality + "청"},
                                        {"code": "7002", "name": sample.locality}]}), sample)
    assert ld.signgu == (("7002", sample.locality),) and not ld.whole_region


def test_fetch_festivals_reads_every_page_and_dedupes():
    class Pages:
        def __init__(self, pages):
            self.pages, self.asked = pages, []

        def search_festival(self, start, regn=None, signgu=None, rows=100, page=1):
            self.asked.append((regn, signgu, page))
            return self.pages[page - 1] if page <= len(self.pages) else []

    f = lambda c: {"contentid": c}
    api = Pages([[f("a"), f("b"), f("c")], [f("c"), f("d"), f("e")], [f("f")]])
    whole = LDong(REGN, "대구광역시", (("1", "중구"), ("2", "동구")), whole_region=True)
    assert [x["contentid"] for x in fetch_festivals(api, "20260101", whole, rows=3)] == list("abcdef")
    assert api.asked == [(REGN, None, 1), (REGN, None, 2), (REGN, None, 3)]
    stuck = Pages([[f("a"), f("b")]] * 50)                    # a server that ignores pageNo: stop when nothing is new
    assert [x["contentid"] for x in fetch_festivals(stuck, "20260101", whole, rows=2)] == ["a", "b"]
    assert len(stuck.asked) == 2
    one_city = LDong("70", "OO도", (("7002", "OO시"),), whole_region=False)
    api = Pages([[f("a")]])
    fetch_festivals(api, "20260101", one_city, rows=3)
    assert api.asked == [("70", "7002", 1)]
