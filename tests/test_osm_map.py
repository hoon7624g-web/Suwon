"""Map provider 'osm' (operator 2026-10-16: Leaflet + OpenStreetMap until the domain move; since 2026-11-05 this city
draws Kakao — '카카오맵으로 바꿔' — and the sample data keeps 'osm'; ported from 해남각's tests).

site.json map_provider 'osm' draws the same map boxes with Leaflet (self-hosted, assets/vendor/leaflet/) on
OpenStreetMap tiles until the site's domain is registered for the Kakao key: every box names the Leaflet folder
(data-osm-lib) and never the Kakao SDK, the credits read OpenStreetMap, and assets/map.js answers the Kakao calls it
makes with Leaflet (osmKit). Without the value the provider stays Kakao (tests/test_kakao_map.py)."""
import json
import re
import shutil
from pathlib import Path

from pipeline import intl_text
from pipeline.build import OSM_LIB, build, map_provider

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates" / "assets"
MAP_BOX = re.compile(r'<div class="map"[^>]*>')


def osm_build(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["kakao_js_key"] = "test-key-123"
    site["map_provider"] = "osm"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["geo"] = {"lat": 35.98, "lng": 126.72, "source": "test"}
    places[1]["geo"] = {"lat": 35.9805, "lng": 126.7215, "source": "test"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    return out, {p: p.read_text("utf-8") for p in out.rglob("*.html")}


def test_provider_value():
    assert map_provider({"map_provider": "osm"}) == "osm" and map_provider({"map_provider": " OSM "}) == "osm"
    assert map_provider({}) == map_provider({"map_provider": "kakao"}) == map_provider({"map_provider": "x"}) == "kakao"
    assert map_provider(json.loads((ROOT / "data" / "suwon" / "site.json").read_text("utf-8"))) == "kakao"
    assert map_provider(json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8"))) == "osm"


def test_boxes_name_leaflet_and_never_the_kakao_sdk(tmp_path):
    out, pages = osm_build(tmp_path)
    with_map = {p: h for p, h in pages.items() if 'class="map"' in h}
    assert len(with_map) >= 2
    for path, html in with_map.items():
        for box in MAP_BOX.findall(html):
            assert f'data-osm-lib="{OSM_LIB}"' in box and "data-kakao-sdk" not in box, path
        assert "dapi.kakao.com" not in html and "test-key-123" not in html, path
        assert "지도: © OpenStreetMap 기여자" in html and "지도: 카카오맵" not in html, path
        assert html.count("<script src=") == 1, path   # Leaflet comes with map.js near the screen, never in the markup
    # every page's footer credits the map it draws
    assert all("지도: 카카오맵" not in h for h in pages.values())
    # the course planner's day maps (drawn by plan.js once a plan comes back) load the same Leaflet: its root names it
    plan = pages[out / "plan" / "index.html"]
    assert f'data-osm-lib="{OSM_LIB}"' in re.search(r'<div class="trp" data-plan [^>]*>', plan).group(0)
    assert "data-kakao-sdk" not in plan and "dapi.kakao.com" not in plan and "map.js" not in plan
    # the self-hosted Leaflet (and its licence) is published where the boxes say
    lib = out / OSM_LIB.strip("/")
    assert (lib / "leaflet.js").is_file() and (lib / "leaflet.css").is_file() and (lib / "LICENSE").is_file()


def test_credit_strings_in_every_language():
    assert intl_text.EN["foot_maps_osm"].endswith("OpenStreetMap contributors")
    assert intl_text.EN["map_credit_osm"].endswith("OpenStreetMap contributors")
    for code in ("ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru"):
        strings = json.loads((ROOT / "data" / "suwon" / code / "strings.json").read_text("utf-8"))
        tag = code.replace("-", "_")
        for key in ("chrome.foot_maps_osm", "chrome.map_credit_osm"):
            rec = strings[key]
            assert rec["en"] == intl_text.EN[key.split(".", 1)[1]] and "OpenStreetMap" in rec[tag], (code, key)


def test_map_js_answers_the_kakao_calls_with_leaflet():
    js = (ASSETS / "map.js").read_text("utf-8")
    # the box's Leaflet folder decides; its stylesheet and script are fetched like the SDK (after load, near the screen)
    assert 'attr("data-osm-lib")' in js and 'base + "leaflet.js"' in js and 'base + "leaflet.css"' in js
    # the Kakao surface the file uses, each answered by the Leaflet kit
    for name in ("Map:", "LatLng:", "Coords:", "Polyline:", "Circle:", "CustomOverlay:", "CopyrightPosition:", "event:"):
        assert name in js[js.index("function osmKit"):], name
    for call in re.findall(r"K\.([A-Za-z]+)", js):
        assert call in ("Map", "LatLng", "Coords", "CustomOverlay", "Polyline", "Circle", "event", "CopyrightPosition"), call
    # OpenStreetMap's tiles, credited in the map's corner (its tile policy)
    assert "https://tile.openstreetmap.org/{z}/{x}/{y}.png" in js and "openstreetmap.org/copyright" in js
