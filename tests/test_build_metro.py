"""A metropolitan city (tests/fixtures/metro: nine 구·군, address aliases, regions.mode district — design 3): the
preview build validates, every published path is ASCII, places carry their 구·군 and 동·읍·면 from the address, the
structured data's address names the 시·도 and the 구·군, neighbours and map searches stay inside the 구·군, and an
empty city (data/daegu's site.json alone) builds with only the operator's production errors left. WP7: the built HTML, scripts and
data name nothing of the first city (the engine's origin), and every path, fragment id, canonical, og:url, sitemap
<loc>, JSON-LD @id / url and search-index path is ASCII."""
import json
import shutil
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

import pytest

from pipeline import city as city_mod
from pipeline.build import State, assign_record_slugs, build
from pipeline.validate import scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
METRO = ROOT / "tests" / "fixtures" / "metro"
DAEGU = ROOT / "data" / "suwon"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("metro") / "out"
    stats = build(METRO, out, "preview")
    return out, stats


def place_node(path: Path) -> dict:
    for raw in scan_file(path).jsonld_raw:
        doc = json.loads(raw)
        for n in doc.get("@graph", [doc]):
            if str(n.get("@id", "")).endswith("#place"):
                return n
    raise AssertionError(f"no place node in {path}")


def test_metro_preview_validates_and_every_path_is_ascii(built):
    out, stats = built
    assert stats["entities"] == 12 and "slug_problems" not in stats
    errors, warns, _ = validate(METRO, out, "preview")
    assert errors == [], errors
    assert [p for p in out.rglob("*") if not p.relative_to(out).as_posix().isascii()] == []
    assert (out / "events" / "sample-festival" / "index.html").exists()      # the series' stored slug
    sitemap = (out / "sitemap.xml").read_text("utf-8")
    assert "%" not in sitemap and "https://metro.test/events/sample-festival/" in sitemap


FIRST_CITY = re.compile(r"군산|고군산|선유도|짬뽕|gunsan|전북특별자치도", re.I)
TEXT_FILES = (".html", ".js", ".json", ".xml", ".txt", ".css", ".svg", ".md")


def test_metro_output_names_nothing_of_the_first_city(built):
    out, _ = built
    files = [p for p in out.rglob("*") if p.is_file() and p.suffix in TEXT_FILES]
    kinds = {p.suffix for p in files}
    assert {".html", ".js", ".json", ".xml", ".txt"} <= kinds            # pages, scripts, the search index, sitemap
    found = [f"{p.relative_to(out).as_posix()}: {m.group(0)}" for p in files
             for m in [FIRST_CITY.search(p.read_text("utf-8", errors="replace"))] if m]
    assert found == []


def _ascii_path(url: str) -> bool:
    path = urlsplit(url).path
    return path.isascii() and "%" not in path


def _jsonld_urls(node) -> list[str]:
    """Every @id and url value of a JSON-LD tree."""
    if isinstance(node, dict):
        return [v for k, v in node.items() if k in ("@id", "url") and isinstance(v, str)] + \
            [u for v in node.values() for u in _jsonld_urls(v)]
    if isinstance(node, list):
        return [u for v in node for u in _jsonld_urls(v)]
    return []


def test_metro_ids_urls_and_fragments_are_ascii(built):
    out, _ = built
    pages = sorted(out.rglob("*.html"))
    assert len(pages) > 20
    bad = []
    for page in pages:
        rel, raw, scan = page.relative_to(out).as_posix(), page.read_text("utf-8"), scan_file(page)
        bad += [(rel, "id", i) for i in re.findall(r'\sid="([^"]*)"', raw) if not i.isascii()]
        for href in scan.hrefs:
            parts = urlsplit(href)
            if not parts.scheme and not href.startswith("//"):       # internal: the path and the fragment
                if not _ascii_path(href) or not parts.fragment.isascii():
                    bad.append((rel, "href", href))
        for url in (scan.canonical, scan.meta.get("og:url", "")):
            if not _ascii_path(url):
                bad.append((rel, "canonical/og:url", url))
        for doc in scan.jsonld_raw:
            bad += [(rel, "json-ld", u) for u in _jsonld_urls(json.loads(doc))
                    if u.startswith(("https://metro.test", "/", "#")) and not (_ascii_path(u) and u.isascii())]
    assert bad == []
    assert all(scan_file(p).canonical.startswith("https://metro.test/") for p in pages
               if p.name == "index.html" and p.parent != out / "search")
    locs = re.findall(r"<loc>(.*?)</loc>", (out / "sitemap.xml").read_text("utf-8"))
    assert locs and all(loc.isascii() and "%" not in loc for loc in locs)
    index = json.loads((out / "search" / "index.json").read_text("utf-8"))
    assert index and all(_ascii_path(r["p"]) for r in index)


def test_place_fields_come_from_the_address():
    S = State(METRO, "preview")
    assert S.city is city_mod.of(S.site)
    by = {e["slug"]: e for e in S.entities}
    got = {s: (by[s]["_district"], by[s]["_area"], by[s]["_road"], by[s]["_place_label"]) for s in (
        "jung-gu-jeonsigwan-a", "jung-gu-sikdang-b", "suseong-gu-gongwon-c", "gunwi-gun-cheheomgwan-d",
        "dong-gu-sikdang-f", "dalseo-gu-jeonsisil-g", "gu-gun-eomneun-jangso-h", "gunwi-gun-yet-juso-jangso-l")}
    assert got == {
        "jung-gu-jeonsigwan-a": ("중구", "삼덕동1가", "샘플로2길", "중구 삼덕동1가"),    # 법정동 'N가' whole (Q5)
        "jung-gu-sikdang-b": ("중구", "동성로2가", "샘플로", "중구 동성로2가"),
        "suseong-gu-gongwon-c": ("수성구", "", "시험로", "수성구"),
        "gunwi-gun-cheheomgwan-d": ("군위군", "군위읍", "예시로", "군위군 군위읍"),
        "dong-gu-sikdang-f": ("동구", "", "샘플길", "동구"),                            # '대구 동구 …' (an alias)
        "dalseo-gu-jeonsisil-g": ("달서구", "", "모형로", "달서구"),                     # '나동 2층' is no 동
        "gu-gun-eomneun-jangso-h": ("", "", "샘플대로", ""),
        "gunwi-gun-yet-juso-jangso-l": ("군위군", "효령면", "예시길", "군위군 효령면"),  # renamed old address (Q6)
    }
    # neighbours share the 구·군: two places on '샘플로' in 북구 and 남구 are not each other's neighbours
    buk = by["gateun-ireum-sikdang"]
    assert buk["_road"] == by["gateun-ireum-sikdang-nam-gu"]["_road"] == by["jung-gu-sikdang-b"]["_road"] == "샘플로"
    assert S.area_neighbours(buk) == {"attraction": [], "stay": [], "food": [], "label": "북구 도로명 주소(샘플로)"}
    assert S.area_neighbours(by["jung-gu-jeonsigwan-a"])["label"] == "중구 삼덕동1가"


def test_jsonld_address_names_the_si_do_and_the_gu_gun(built):
    out, _ = built
    S = State(METRO, "preview")
    for e in S.entities:
        node = place_node(out / "places" / e["slug"] / "index.html")
        assert node["containedInPlace"] == {"@id": "https://metro.test/#city", "@type": "City", "name": "대구광역시"}
        address = node["address"]
        if e["slug"] == "dong-gu-sikdang-f":                  # '대구 동구 …' is shown as written: one streetAddress
            assert "addressRegion" not in address and address["streetAddress"] == "대구 동구 샘플길 5"
            continue
        assert address["addressRegion"] == "대구광역시"
        assert address.get("addressLocality", "") == e["_district"], e["slug"]
    node = place_node(out / "places" / "jung-gu-jeonsigwan-a" / "index.html")
    assert node["address"] == {"@type": "PostalAddress", "addressRegion": "대구광역시", "addressLocality": "중구",
                               "streetAddress": "샘플로2길 80 (삼덕동1가)", "addressCountry": "KR"}


def test_page_place_line_title_and_map_search_use_the_district(built):
    out, _ = built
    page = scan_file(out / "places" / "jung-gu-jeonsigwan-a" / "index.html")
    assert page.meta["geo.placename"] == "대구광역시 중구 삼덕동1가 [샘플] 중구 전시관 A"
    assert page.title.startswith("대구 [샘플] 중구 전시관 A ")
    # map searches start with the region and the 구·군 (City.map_query_prefix)
    html = (out / "places" / "jung-gu-jeonsigwan-a" / "index.html").read_text("utf-8")
    assert "https://map.naver.com/p/search/" + quote("대구 중구 ", safe="") in html
    # a name that only holds a homograph of the city ('대구탕', site.json region_homographs) still gets the prefix
    from pipeline.maplinks import search_link
    assert search_link("대구탕 골목", "대구", ("대구탕",)).endswith(quote("대구 대구탕 골목", safe=""))
    assert search_link("대구 근대골목", "대구", ("대구탕",)).endswith(quote("대구 근대골목", safe=""))


def test_new_place_slugs_take_the_district_on_a_clash_and_hyphenate_admin_words():
    metro = city_mod.of(json.loads((METRO / "site.json").read_text("utf-8")))
    items = [{"id": "p1", "name": "한빛 식당", "facts": {"address": "대구광역시 북구 샘플로 3"}},
             {"id": "p2", "name": "한빛 식당", "facts": {"address": "대구광역시 남구 샘플로 7"}},
             {"id": "p3", "name": "삼덕동 골목", "facts": {"address": "대구광역시 중구 샘플로2길 1 (삼덕동1가)"}},
             {"id": "p4", "slug": "kept-as-stored", "name": "한빛 식당"}]
    assert assign_record_slugs(items, "place", metro) == []
    assert [x["slug"] for x in items] == ["hanbit-sikdang", "hanbit-sikdang-nam-gu", "samdeok-dong-golmok",
                                          "kept-as-stored"]
    assert [bool(x.get("_slug_generated")) for x in items] == [True, True, True, False]


def test_empty_city_builds_and_passes_production_with_the_operator_values(tmp_path):
    data = tmp_path / "daegu"                     # the Daegu config with no data files (data/daegu itself now has data)
    data.mkdir()
    shutil.copy(DAEGU / "site.json", data / "site.json")
    out = tmp_path / "preview"
    build(data, out, "preview")
    errors, warns, _ = validate(data, out, "preview")
    assert errors == [] and warns == []
    out = tmp_path / "prod"
    build(data, out, "production")
    errors, _, _ = validate(data, out, "production")
    # the operator set operator.contact and the GA4 launch exception on 2026-10-11 (site.json launch_exceptions):
    # the config alone now passes production validation
    assert errors == []
    places = (out / "places" / "index.html").read_text("utf-8")       # (Q10) the empty list: noindex, no sitemap
    assert '<meta name="robots" content="noindex, follow">' in places
    assert "/places/" not in (out / "sitemap.xml").read_text("utf-8")
    home = scan_file(out / "index.html")
    assert "0곳" not in home.title + home.meta["description"] and "0편" not in home.meta["description"]
