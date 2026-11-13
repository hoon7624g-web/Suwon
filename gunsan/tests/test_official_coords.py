"""tools/official_coords.py: coordinates from 군산시 문화관광 place pages (operator choice (가), 2026-10-16).

The page fixtures are the map script's coordinate block only, trimmed from two cached pages (tests/fixtures/
gunsan_tour_map_*.html); every other page here is that block with other values put in. Nothing is fetched: urlopen
is replaced wherever a GET could happen."""
import json
import urllib.error
from pathlib import Path

import pytest

from tools import official_coords as oc

FIX = Path(__file__).resolve().parent / "fixtures"
COORD = (FIX / "gunsan_tour_map_coord.html").read_text("utf-8")
EMPTY = (FIX / "gunsan_tour_map_empty.html").read_text("utf-8")
URL = "https://www.gunsan.go.kr/tour/m2080/view/{sid}"


def page(lat="35.9596090", lng="126.5317160", sid="305387", addr="전라북도 군산시 비응도동", swapped=True, quote="'"):
    """The fixture's block with these values (swapped: the page's own order — the latitude in `var lng`)."""
    a, b = ("lng", "lat") if swapped else ("lat", "lng")
    html = COORD.replace("var lng = '35.9596090';", f"var {a} = {quote}{lat}{quote};")
    html = html.replace("var lat = '126.5317160';", f"var {b} = {quote}{lng}{quote};")
    return html.replace("'305387'", f"'{sid}'").replace("'전라북도 군산시 비응도동'", f"'{addr}'")


# ------------------------------------------------------------------ parse
def test_parse_reads_the_point_by_value_whatever_the_variable_names_say():
    got = oc.parse(COORD)                      # the page as it is: the latitude sits in `var lng`
    assert got["status"] == "coord" and (got["lat"], got["lng"]) == (35.959609, 126.531716)
    assert got["sid"] == "305387" and got["page_address"] == "전라북도 군산시 비응도동"
    plain = page(lat="35.9596090", lng="126.5317160", swapped=False)   # labels the right way round
    assert "var lat = '35.9596090'" in plain
    assert (oc.parse(plain)["lat"], oc.parse(plain)["lng"]) == (35.959609, 126.531716)
    dq = page(quote='"')
    assert '"35.9596090"' in dq and (oc.parse(dq)["lat"], oc.parse(dq)["lng"]) == (35.959609, 126.531716)


def test_parse_never_takes_the_fallback_point():
    assert oc.parse(EMPTY)["status"] == "empty"                      # 대각산: no coordinates on the page
    assert oc.parse(EMPTY)["sid"] == "305400"
    assert oc.parse("<p>no map</p>")["status"] == "no_map_script"
    # the fallback block alone (no `var` declarations) is the city's default point: never read as a place
    fallback = "<script>if(lat==''||lat == ''){ lat = '126.73684'; lng = '35.96761'; }</script>"
    assert oc.parse(fallback)["status"] == "no_map_script"
    assert oc.parse(page(lat="35.96761", lng="126.73684"))["status"] == "default_point"
    assert oc.parse(page(lat="35.9x", lng="126.5"))["status"] == "unparseable"
    assert oc.parse(page(lat="35.95", lng="35.96"))["status"] == "unparseable"     # two latitudes


# ------------------------------------------------------------------ a small world on disk
def place(pid, name, address, kind="attraction", geo=None, **extra):
    p = {"id": pid, "slug": pid, "name": name, "kind": kind, "status": "published", "approved_at": "2026-10-08",
         "category": "관광지", "facts": {"address": address},
         "official": {"source_url": URL.format(sid=pid.split("-")[-1]) + "?s_idx=2"}, **extra}
    if geo:
        p["geo"] = {"lat": geo[0], "lng": geo[1], "source": "TourAPI"}
    return p


REFS = [  # TourAPI points (references): 경암동 · 해망로 · two island places · 성산면 road
    place("ref-1", "경암동 철길마을", "전북특별자치도 군산시 경촌4길 14 (경암동)", geo=(35.9799, 126.7244)),
    place("ref-2", "근대건축관", "전북특별자치도 군산시 해망로 214 (장미동)", geo=(35.98942, 126.71416)),
    place("ref-3", "선유도", "전북특별자치도 군산시 옥도면 선유도리", geo=(35.8130, 126.4130)),
    place("ref-4", "망주봉", "전북특별자치도 군산시 옥도면 선유도리 산1", geo=(35.8170, 126.4160)),
    place("ref-5", "철새조망대", "전북특별자치도 군산시 나포면 철새로 120", geo=(36.0080, 126.8600)),
]


def world(tmp_path, targets, pages, fetched_at="2026-10-15T20:00:00+00:00", lots=None, nearby=None):
    data, cache = tmp_path / "data", tmp_path / "cache"
    data.mkdir()
    cache.mkdir()
    (data / "site.json").write_text(json.dumps({"region": "군산"}, ensure_ascii=False), "utf-8")
    (data / "places.json").write_text(json.dumps(REFS + targets, ensure_ascii=False, indent=2) + "\n", "utf-8")
    nb = nearby if nearby is not None else {"_meta": {"parking": {"radius_m": 500, "max": 3}},
                                            "ref-1": {"parking": [{"lot_id": "lot-a", "meters": 10}]}}
    (data / "nearby.json").write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    (data / "parking_lots.json").write_text(json.dumps({"lots": lots or []}, ensure_ascii=False), "utf-8")
    for pid, html in pages.items():
        url = next(t for t in targets if t["id"] == pid)["official"]["source_url"]
        key = oc.cache_key(url)
        (cache / f"{key}.html").write_text(html, "utf-8")
        (cache / f"{key}.meta.json").write_text(json.dumps({"url": url, "place_id": pid, "http_status": 200,
                                                            "fetched_at": fetched_at}), "utf-8")
    return data, cache


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def refuse(*a, **k):
        calls.append(a)
        raise AssertionError("network")
    monkeypatch.setattr(oc.urllib.request, "urlopen", refuse)
    return calls


def run(data, cache, **kw):
    return oc.run(data, cache, offline=kw.pop("offline", True), report=None, today="2026-10-16", **kw)


def flags_of(out, pid):
    rows = [r for r in out["flagged"] if r["id"] == pid] + [r for r in out["accepted"] if r["id"] == pid]
    return rows[0]["flags"]


def test_cache_key_is_the_url_path():
    assert oc.cache_key("https://www.gunsan.go.kr/tour/m2080/view/305387?s_idx=2") == "tour_m2080_view_305387"
    assert oc.cache_key("https://www.gunsan.go.kr/tour/m2080/view/305387?") == "tour_m2080_view_305387"


def test_each_check_flags_its_case(tmp_path, no_network):
    T = [
        place("gunsan-1", "범위 밖", "전북특별자치도 군산시 경촌4길 20 (경암동)"),
        place("gunsan-2", "섬에 찍힌 육지", "전북특별자치도 군산시 경촌4길 30 (경암동)"),
        place("gunsan-3", "동네에서 먼 곳", "전북특별자치도 군산시 경촌4길 40 (경암동)"),
        place("gunsan-4", "같은 길 먼 곳", "전북특별자치도 군산시 성산면 철새로 300"),
        place("gunsan-5", "기준 없는 곳", "전북특별자치도 군산시 대야면 산월길 9"),
        place("gunsan-6", "주소 다름", "전북특별자치도 군산시 경촌4길 50 (경암동)"),
        place("gunsan-7", "번호 다름", "전북특별자치도 군산시 경촌4길 60 (경암동)"),
        place("gunsan-8", "거친 좌표", "전북특별자치도 군산시 경촌4길 70 (경암동)"),
        place("gunsan-9", "2층 가게", "전북특별자치도 군산시 해망로 214 (장미동)"),
        place("gunsan-10", "어청도 등대", "전북특별자치도 군산시 옥도면 어청도리 산2"),
        place("gunsan-11", "기준점 위", "전북특별자치도 군산시 해망로 300 (장미동)"),
    ]
    P = {
        "gunsan-1": page("36.5000000", "126.7244000", "1", "전북특별자치도 군산시 경촌4길 20"),
        "gunsan-2": page("35.8150000", "126.4150000", "2", "전북특별자치도 군산시 경촌4길 30"),
        "gunsan-3": page("36.0400000", "126.7244000", "3", "전북특별자치도 군산시 경촌4길 40"),
        "gunsan-4": page("36.0080000", "126.9100000", "4", "전북특별자치도 군산시 성산면 철새로 300"),
        "gunsan-5": page("35.9000000", "126.8000000", "5", "전북특별자치도 군산시 대야면 산월길 9"),
        "gunsan-6": page("35.9801000", "126.7246000", "6", "전북특별자치도 군산시 조촌로 1"),
        "gunsan-7": page("35.9802000", "126.7247000", "999", "전북특별자치도 군산시 경촌4길 60"),
        "gunsan-8": page("35.98", "126.7248", "8", "전북특별자치도 군산시 경촌4길 70"),
        "gunsan-9": page("35.9893000", "126.7140000", "9", "군산시 해망로 214, 2층"),
        "gunsan-10": page("36.1250000", "125.9680000", "10", "전북특별자치도 군산시 옥도면 어청도리 산2"),
        "gunsan-11": page("35.9894200", "126.7141600", "11", "전북특별자치도 군산시 해망로 300"),
    }
    data, cache = world(tmp_path, T, P)
    out = run(data, cache)
    assert no_network == [] and out["live_calls"] == 0 and out["by_status"] == {"coord": 11}
    assert "out_of_bounds" in flags_of(out, "gunsan-1")
    assert "island_mismatch" in flags_of(out, "gunsan-2")
    assert "far_from_area" in flags_of(out, "gunsan-3") and "island_mismatch" not in flags_of(out, "gunsan-3")
    assert flags_of(out, "gunsan-4") == ["far_from_road"]
    assert flags_of(out, "gunsan-5") == ["no_reference"]
    assert flags_of(out, "gunsan-6") == ["address_mismatch"]
    assert flags_of(out, "gunsan-7") == ["sid_mismatch"]
    assert flags_of(out, "gunsan-8") == ["low_precision"]
    assert flags_of(out, "gunsan-9") == []          # '해망로 214, 2층' is the same building as '해망로 214 (장미동)'
    assert flags_of(out, "gunsan-10") == []         # 어청도: inside the box, 옥도면 is exempt from the area distance
    assert flags_of(out, "gunsan-11") == ["shared_point"]   # on 근대건축관's point, another address
    assert {r["id"] for r in out["accepted"]} == {"gunsan-9", "gunsan-10"}
    row = next(r for r in out["flagged"] if r["id"] == "gunsan-5")
    assert row["nearest"]["name"] and row["nearest"]["m"] > 2000 and row["kind"] == "attraction"


def test_shared_point_needs_three_addresses_not_one_building(tmp_path, no_network):
    pt = ("35.9750000", "126.7300000")
    diff = [place(f"gunsan-{i}", f"가게 {i}", f"전북특별자치도 군산시 경촌4길 {i} (경암동)") for i in (101, 102, 103)]
    same = [place(f"gunsan-{i}", f"가게 {i}", "전북특별자치도 군산시 경촌4길 99 (경암동)") for i in (201, 202, 203)]
    pages = {p["id"]: page(*pt, p["id"].split("-")[1], p["facts"]["address"]) for p in diff}
    pages |= {p["id"]: page("35.9760000", "126.7310000", p["id"].split("-")[1], p["facts"]["address"]) for p in same}
    data, cache = world(tmp_path, diff + same, pages)
    out = run(data, cache)
    assert all(flags_of(out, p["id"]) == ["shared_point"] for p in diff)
    assert all(flags_of(out, p["id"]) == [] for p in same)


def test_dry_run_writes_nothing_and_offline_makes_no_request(tmp_path, no_network):
    T = [place("gunsan-9", "2층 가게", "전북특별자치도 군산시 해망로 214 (장미동)"),
         place("gunsan-12", "캐시 없음", "전북특별자치도 군산시 해망로 216 (장미동)")]
    data, cache = world(tmp_path, T, {"gunsan-9": page("35.9893000", "126.7140000", "9", "군산시 해망로 214")})
    before = {f.name: f.read_bytes() for f in data.iterdir()}
    out = run(data, cache)
    assert {f.name: f.read_bytes() for f in data.iterdir()} == before
    assert out["applied"] is False and out["by_status"] == {"coord": 1, "not_cached": 1}
    assert no_network == [] and out["live_calls"] == 0 and out["cache_hits"] == 1


def test_apply_writes_the_geo_record_nearby_and_parking(tmp_path, no_network):
    T = [place("gunsan-9", "2층 가게", "전북특별자치도 군산시 해망로 214 (장미동)", kind="food"),
         place("gunsan-13", "넓은 산", "전북특별자치도 군산시 옥도면 선유도리 일원"),
         place("gunsan-14", "표시된 곳", "전북특별자치도 군산시 해망로 400 (장미동)"),
         place("gunsan-15", "잠긴 곳", "전북특별자치도 군산시 해망로 500 (장미동)", locks=["geo"]),
         place("gunsan-16", "이미 있음", "전북특별자치도 군산시 해망로 600 (장미동)", geo=(35.99, 126.715))]
    P = {"gunsan-9": page("35.9893000", "126.7140000", "9", "군산시 해망로 214, 2층"),
         "gunsan-13": page("35.8150000", "126.4140000", "13", "전북특별자치도 군산시 옥도면 선유도리 일원"),
         "gunsan-14": page("35.9894200", "126.7141600", "14", "전북특별자치도 군산시 해망로 400"),   # shared_point
         "gunsan-15": page("35.9800000", "126.7200000", "15", "전북특별자치도 군산시 해망로 500"),
         "gunsan-16": page("35.9800000", "126.7200000", "16", "전북특별자치도 군산시 해망로 600")}
    lots = [{"id": "lot-b", "lat": 35.9895, "lng": 126.7142}, {"id": "lot-a", "lat": 35.9895, "lng": 126.7142},
            {"id": "lot-far", "lat": 35.999, "lng": 126.73}, {"id": "lot-off", "lat": 35.9893, "lng": 126.714,
                                                                "nearby": False}]
    data, cache = world(tmp_path, T, P, lots=lots)
    nb_before = (data / "nearby.json").read_text("utf-8")
    out = run(data, cache, apply=True)
    places = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    assert out["targets"] == 3                       # locked and existing geo are not targets
    assert places["gunsan-9"]["geo"] == {
        "lat": 35.9893, "lng": 126.714, "source": "군산시 문화관광", "url": "https://www.gunsan.go.kr/tour/m2080/view/9",
        "checked_at": "2026-10-16", "note": oc.NOTE}  # KST day of 2026-10-15T20:00Z
    assert places["gunsan-13"]["geo"]["note"] == oc.NOTE + " · 넓은 장소의 대표 지점"
    assert "geo" not in places["gunsan-14"] and [r["id"] for r in out["flagged"]] == ["gunsan-14"]
    assert "geo" not in places["gunsan-15"] and places["gunsan-16"]["geo"]["source"] == "TourAPI"
    # nearby lists recomputed: a list joining a 군산시 point names both providers, a TourAPI-only list one
    new, ref = places["gunsan-9"], places["ref-2"]
    assert [n["internal_slug"] for n in new["nearby"] if n["kind"] == "attraction"][0] == "ref-2"
    mixed = {"provider": "한국관광공사 TourAPI·군산시 문화관광 좌표", "providers": ["한국관광공사 TourAPI", "군산시 문화관광"]}
    assert {k: new["nearby_source"][k] for k in mixed} == mixed
    assert {k: ref["nearby_source"][k] for k in mixed} == mixed and "gunsan-9" in [n["internal_slug"] for n in ref["nearby"]]
    assert places["ref-5"]["nearby_source"]["provider"] == "한국관광공사 TourAPI 좌표"     # nothing within 2 km
    assert places["ref-5"]["nearby_source"]["providers"] == ["한국관광공사 TourAPI"]
    # nearby.json: parking-only entries for the published points without one, nearest then lot id, the excluded
    # lot left out; the existing entry stays as it was
    nb = json.loads((data / "nearby.json").read_text("utf-8"))
    m = round(oc.hav_m(35.9893, 126.714, 35.9895, 126.7142))
    assert nb["gunsan-9"] == {"parking": [{"lot_id": "lot-a", "meters": m}, {"lot_id": "lot-b", "meters": m}]}
    assert all("bus" not in nb[k] for k in out["nearby_json_added"])
    assert set(out["nearby_json_added"]) == {"gunsan-9", "gunsan-13", "gunsan-16", "ref-2", "ref-3", "ref-4", "ref-5"}
    old = json.loads(nb_before)
    assert nb["ref-1"] == old["ref-1"] and nb["_meta"] == old["_meta"]
    assert '"ref-1": {\n  "parking": [\n   {\n    "lot_id": "lot-a",\n    "meters": 10\n   }\n  ]\n }' \
        in (data / "nearby.json").read_text("utf-8")

    # a person looked at the flagged place: --accept writes it too
    out2 = run(data, cache, apply=True, accept=["gunsan-14"])
    places = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    assert places["gunsan-14"]["geo"]["source"] == "군산시 문화관광" and out2["accepted"][0]["accepted_by_person"]


class Reset(urllib.error.URLError):
    def __init__(self):
        super().__init__(ConnectionResetError(104, "Connection reset by peer"))


class Resp:
    status = 200

    def __init__(self, body: str):
        self.body = body.encode("utf-8")
        self.headers = self

    def get_content_charset(self):
        return "utf-8"

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def scripted(monkeypatch, answers):
    """urlopen answering from a list: an exception instance is raised, a str is a 200 page."""
    seen = []

    def fake(req, timeout=None):
        seen.append(req.full_url)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return Resp(a)
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake)
    return seen


def test_retries_count_against_the_budget_and_only_a_200_is_cached(tmp_path, monkeypatch):
    seen = scripted(monkeypatch, [Reset(), Reset(), COORD])
    f = oc.Fetcher(tmp_path, max_calls=5, interval=0, sleep=lambda s: None)
    st, html, meta = f.fetch(URL.format(sid="305387") + "?s_idx=2", "gunsan-305387")
    assert st == "live" and html == COORD and f.live_calls == 3 and len(seen) == 3
    assert meta["http_status"] == 200 and meta["place_id"] == "gunsan-305387"
    assert (tmp_path / "tour_m2080_view_305387.html").read_text("utf-8") == COORD
    st, _, _ = f.fetch(URL.format(sid="305387"), "gunsan-305387")          # the next run reads the cache
    assert st == "cached" and f.live_calls == 3

    scripted(monkeypatch, [Reset(), Reset(), COORD])
    g = oc.Fetcher(tmp_path / "b", max_calls=2, interval=0, sleep=lambda s: None)
    assert g.fetch(URL.format(sid="1"), "x")[0] == "budget" and g.live_calls == 2
    assert not (tmp_path / "b").exists()                                   # nothing cached on failure

    scripted(monkeypatch, [urllib.error.HTTPError("u", 404, "Not Found", {}, None)])
    h = oc.Fetcher(tmp_path / "c", max_calls=9, interval=0, sleep=lambda s: None)
    assert h.fetch(URL.format(sid="2"), "x")[0] == "error: HTTP 404" and h.live_calls == 1   # not retried


def test_a_failed_page_gets_a_second_pass(tmp_path, monkeypatch):
    T = [place("gunsan-9", "2층 가게", "전북특별자치도 군산시 해망로 214 (장미동)")]
    data, cache = world(tmp_path, T, {})
    body = page("35.9893000", "126.7140000", "9", "군산시 해망로 214")
    seen = scripted(monkeypatch, [Reset()] * (oc.RETRIES + 1) + [body])
    f = oc.Fetcher(cache, max_calls=20, interval=0, sleep=lambda s: None)
    out = oc.run(data, cache, report=None, fetcher=f)
    assert len(seen) == oc.RETRIES + 2 and out["live_calls"] == oc.RETRIES + 2
    assert out["by_status"] == {"coord": 1} and out["errors"] == [] and len(out["accepted"]) == 1
