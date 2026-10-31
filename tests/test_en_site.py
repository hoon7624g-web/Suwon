"""The English site (/en/, pipeline/en_site.py): built in production from gunsan_subset with tests/fixtures/en_min laid
over it (tests/fixtures/build_en_min.py: 8 English place records, the food hub guide, one course, one event series),
in which one Korean summary was edited after translation (its English record is then stale and must not be
rendered). Places and records are looked up by id; every English page uses the slug its Korean record stores. Also:
the English site is off without site.json languages "en" or without data/<city>/en/places.json (this city's data, the
sample), the city words come from site.json, and a 구·군 city (tests/fixtures/metro) gets its groups and place lines in
English. The other versions: tests/test_intl_site.py."""
import json
import re
import shutil
import types
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline import build as B
from pipeline import city as citymod
from pipeline import en_site
from pipeline.build import State, build
from pipeline.en_site import en_slug, sentences_en
from pipeline.en_source import address_en, current_hashes, event_series
from pipeline.validate import PageScan, hreflang_problems, scan_file, validate
from tests.fixtures.build_en_min import overlay

ROOT = Path(__file__).resolve().parent.parent
SUBSET = ROOT / "tests" / "fixtures" / "gunsan_subset"
EN_MIN = ROOT / "tests" / "fixtures" / "en_min"
SAMPLE = ROOT / "data" / "sample"
CITY = ROOT / "data" / "suwon"          # this city's data (its English records, all 9 versions)
METRO = ROOT / "tests" / "fixtures" / "metro"   # a 구·군 city config
STALE_ID = "gunsan-305395"      # 근대역사박물관: its Korean summary is edited in the copy
PLAIN_ID = "gunsan-305372"      # 은파호수공원: no designation
CONFLICT_ID = "gunsan-1379526"  # 군산근대건축관: hours two sources give differently
NOINDEX_ID = "gunsan-305401"    # 청암산: below the index rule
DZ_ID = "gunsan-306591"         # 복성루: 군산맛집(2026)
DZ2_ID = "gunsan-1305918"       # 빈해원: 짬뽕 특화거리
HUB_GUIDE = "guide-13"          # site.json list_hubs.food
KO_PLACES = {p["id"]: p for p in json.loads((SUBSET / "places.json").read_text("utf-8"))}
EN_PLACES = json.loads((EN_MIN / "en" / "places.json").read_text("utf-8"))
HANGUL = re.compile(r"[가-힣]")
# the en_min build: 7 current place records (8 less the stale one), 3 lists, the hub guide and /en/guides/, the course
# and /en/courses/, /en/events/, /en/about/, /en/, /en/search/ (noindex, out of the sitemap)
EN_PAGES = 7 + 3 + 2 + 2 + 1 + 1 + 1 + 1
EN_INDEXABLE = EN_PAGES - 2   # all but the one noindex place and the search page
# ko ↔ en pairs: home, about, the 3 lists, 7 places, guides index + guide, courses index + course, events index
PAIRS = 1 + 1 + 3 + 7 + 2 + 2 + 1


def en_min_data(dst: Path, **site) -> Path:
    """gunsan_subset with en_min laid over it in dst; site: more site.json values."""
    shutil.copytree(SUBSET, dst)
    overlay(dst)
    if site:
        s = json.loads((dst / "site.json").read_text("utf-8"))
        s.update(site)
        (dst / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    return dst


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("en")
    data = en_min_data(tmp / "data")
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = next(x for x in places if x["id"] == STALE_ID)
    p["summary"] = p["summary"] + " 번역 뒤에 바뀐 문장입니다."
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp / "dist"
    stats = build(data, out, "production")
    return {"data": data, "out": out, "stats": stats, "ko_slug": p["slug"]}


def _html_files(out: Path, prefix: str = "en"):
    return sorted((out / prefix).rglob("*.html"))


def en_page(out: Path, record: str) -> Path:
    """The English leaf page (/en/<section>/<slug>/) that renders a record ('place:<id>', 'guide:<id>')."""
    hits = [f for f in sorted((out / "en").glob("*/*/index.html")) if record in scan_file(f).records]
    assert len(hits) == 1, (record, hits)
    return hits[0]


def ko_page(out: Path, pid: str) -> Path:
    return out / "places" / KO_PLACES[pid]["slug"] / "index.html"


def test_english_routes_and_counts(site):
    out, en = site["out"], site["stats"]["en"]
    for path in ("en/index.html", "en/places/index.html", "en/food/index.html", "en/stays/index.html",
                 "en/guides/index.html", "en/courses/index.html", "en/events/index.html", "en/about/index.html"):
        assert (out / path).exists(), path
    assert en_page(out, f"place:{PLAIN_ID}").parent.name == KO_PLACES[PLAIN_ID]["slug"]   # the Korean record's slug
    assert en_page(out, f"guide:{HUB_GUIDE}").parent.parent.name == "guides"
    assert en["stale_skipped"] == {"places": 1, "guides": 0, "courses": 0, "events": 0}
    assert en["places"] == len(EN_PLACES) - 1 == 7      # every English place record but the stale one
    assert (en["guides"], en["courses"], en["event_series"]) == (1, 1, 1)
    assert en["pages"] == len(_html_files(out)) == EN_PAGES
    for f in (out / "en" / "places").iterdir():   # slugs: lowercase ASCII words
        assert f.name == "index.html" or re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", f.name), f.name
    # QA 2026-10-15 SRC-03a: a published Korean item with no record at all (current or stale) in a version is counted
    # (render stats 'untranslated', a build warning): en_min translates 8 places, one guide and one course
    published = {k: sum(1 for x in json.loads((site["data"] / f"{k}.json").read_text("utf-8")) if x.get("status") == "published")
                 for k in ("places", "guides", "courses")}
    assert en["untranslated"] == {"places": published["places"] - len(EN_PLACES), "guides": published["guides"] - 1,
                                  "courses": published["courses"] - 1, "events": 0}
    assert en["guides"] == len([d for d in (out / "en" / "guides").iterdir() if d.is_dir()]) == 1
    assert "intl" not in site["stats"]   # en_min has no other version (they: tests/test_intl_site.py)


def test_place_page_lists_under_its_own_kind(site):
    """The breadcrumb and the current menu item name the place's own list, whatever kinds its nearby places are
    (place_vm once let the nearby loop overwrite the page's kind: a museum showed under Food)."""
    seg = {"attraction": "places", "food": "food", "stay": "stays"}
    places = json.loads((site["data"] / "places.json").read_text("utf-8"))
    kinds = {x["slug"]: x["kind"] for x in places}
    checked = 0
    for f in (site["out"] / "en" / "places").glob("*/index.html"):   # every kind's page lives under places/
        html = f.read_text("utf-8")
        ko = re.search(r'hreflang="ko" href="[^"]*/places/([^"/]+)/"', html)   # the Korean page names the place
        crumb = re.search(r'<nav class="crumbs"[^>]*>.*?<a href="[^"]*/en/([a-z]+)/">', html)
        assert ko and crumb, f
        want = seg[kinds[unquote(ko.group(1))]]
        assert crumb.group(1) == want, f
        assert re.search(rf'href="/en/{want}/"[^>]*aria-current="page"|aria-current="page"[^>]*href="/en/{want}/"', html), f
        checked += 1
    assert checked == len(list((site["out"] / "en" / "places").glob("*/index.html"))) == 7


def test_lang_and_no_hangul_outside_lang_ko(site):
    for f in _html_files(site["out"]):
        p = scan_file(f)
        assert p.html_lang == "en", f
        assert p.hangul == [], (f, p.hangul[:3])
    page = en_page(site["out"], f"place:{PLAIN_ID}").read_text("utf-8")
    assert f'<span lang="ko">{KO_PLACES[PLAIN_ID]["name"]}</span>' in page   # the Korean name, for a taxi or a Korean map
    assert '<meta property="og:locale" content="en_US">' in page


def test_hreflang_pairs_are_reciprocal(site):
    out = site["out"]
    pages = {}
    for f in sorted(out.rglob("*.html")):
        p = scan_file(f)
        pages["/" + f.relative_to(out).as_posix()] = (p.canonical, p.alternates)
    assert hreflang_problems(pages) == []
    ko = scan_file(ko_page(out, PLAIN_ID))
    en_path = "/" + str(en_page(out, f"place:{PLAIN_ID}").parent.relative_to(out)) + "/"
    assert dict(ko.alternates)["en"].endswith(en_path)
    assert dict(ko.alternates)["x-default"] == dict(ko.alternates)["ko"] == ko.canonical
    en = scan_file(out / en_path.strip("/") / "index.html")
    assert dict(en.alternates) == dict(ko.alternates)
    assert sum(1 for _, (_, a) in pages.items() if a) == 2 * PAIRS


def test_stale_record_is_not_rendered(site):
    out = site["out"]
    stale = f"/en/places/{KO_PLACES[STALE_ID]['slug']}/"
    assert not (out / stale.strip("/")).exists()
    ko = ko_page(out, STALE_ID)
    assert ko.parent.name == site["ko_slug"]
    p = scan_file(ko)
    assert p.alternates == []                                          # no English twin: no hreflang
    # the English link falls back to the place's own English list, saying so (QA 2026-10-15 SRC-03b; it was /en/)
    assert ('<a class="mast-lang" href="/en/places/" hreflang="en" lang="en">English'
            '<small class="lang-note">Things to do · not translated</small></a>') in ko.read_text("utf-8")
    lists = (out / "en" / "places" / "index.html").read_text("utf-8")
    assert stale not in lists
    for f in _html_files(out):
        assert f"place:{STALE_ID}" not in scan_file(f).records


def test_sitemap_has_only_indexable_english_urls(site):
    out = site["out"]
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [el.text for el in ET.parse(out / "sitemap.xml").getroot().iter(f"{ns}loc")]
    en_locs = [u for u in locs if urlsplit(u).path.startswith("/en/")]
    assert len(en_locs) == site["stats"]["en"]["indexable"] == EN_INDEXABLE
    for u in en_locs:
        p = scan_file(out / unquote(urlsplit(u).path).lstrip("/") / "index.html")
        assert not p.meta.get("robots", "").startswith("noindex"), u
    noindex = [f for f in (out / "en" / "places").glob("*/index.html")
               if scan_file(f).meta.get("robots", "").startswith("noindex")]
    assert noindex == [en_page(out, f"place:{NOINDEX_ID}")]
    assert site["stats"]["en"]["places"] - site["stats"]["en"]["places_indexable"] == len(noindex) == 1
    llms = (out / "llms.txt").read_text("utf-8")
    hub = "/" + str(en_page(out, f"guide:{HUB_GUIDE}").parent.relative_to(out)) + "/"
    assert "## English" in llms and hub in llms
    for f in noindex:
        assert "/en/places/" + f.parent.name + "/" not in llms


def test_conflicting_values_show_both_with_the_note(site):
    page = scan_file(en_page(site["out"], f"place:{CONFLICT_ID}"))
    facts = page.blocks["facts"]
    assert "Sources differ — call before visiting" in facts
    assert "Gunsan City Culture and Tourism" in facts and "Korea Tourism Organization TourAPI" in facts
    rows = [r for r in page.fact_rows if "usetime" in r["keys"]]
    assert rows and "09:00–18:00 (last entry 17:30)" in rows[0]["exact"]


def test_production_validate_passes(site):
    errors, _, stats = validate(site["data"], site["out"], "production")
    assert errors == [], errors[:10]
    assert stats["en_pages"] == site["stats"]["en"]["pages"]


def test_designations_in_english_with_list_link_and_no_checked_date(site):
    """The Korean page's official designations (schema.designations) on the English twin: a chip linking to the list,
    the 'Designations' row with the list's English name as a link — never its checked date (operator decision
    2026-10-09) — and JSON-LD award."""
    f = en_page(site["out"], f"place:{DZ_ID}")
    page = scan_file(f)
    label = "2026 Gunsan Matjip (designated by Gunsan City)"
    assert label in page.blocks["designations"]
    assert "https://www.gunsan.go.kr/tour/m2555" in page.block_hrefs["designations"]
    rows = [r for r in page.fact_rows if "designations" in r["keys"]]
    assert rows and f"{label} Gunsan Culture and Tourism: Gunsan Matjip designations (2026)" in rows[0]["text"]
    assert "2026-10-09" not in rows[0]["text"] and not re.search(r"\bchecked\b", page.visible, re.I)  # "rechecked with …" stays
    ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                             f.read_text("utf-8"), re.S)]
    node = next(n for g in ld for n in g.get("@graph", []) if str(n.get("@id", "")).endswith("#place"))
    assert node["award"] == label
    plain = scan_file(en_page(site["out"], f"place:{PLAIN_ID}"))
    assert "designations" not in plain.blocks and not [r for r in plain.fact_rows if "designations" in r["keys"]]


def test_english_photos_carry_creator_and_licence_page(site):
    """Search Console image metadata: every English place photo names its creator (the visible credit) and the
    page with its terms (the KOGL type page, as `license`) — the same fields as the Korean twin."""
    S = State(site["data"], "production")
    shown = {r.partition(":")[2] for f in (site["out"] / "en" / "places").glob("*/index.html")
             for r in scan_file(f).records if r.startswith("place:")}
    seen = 0
    for f in sorted((site["out"] / "en" / "places").glob("*/index.html")):
        ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                                 f.read_text("utf-8"), re.S)]
        node = next((n for g in ld for n in g.get("@graph", []) if str(n.get("@id", "")).endswith("#place")), {})
        for im in node.get("image") or []:
            assert im["creator"] == {"@type": "Organization", "name": im["creditText"]}
            assert im["acquireLicensePage"] == im["license"]
            seen += 1
    # the place pages mark up their first 7 photos (en_site.Pages.place)
    assert seen == sum(min(7, len(e["_photos"])) for e in S.entities if e["id"] in shown) > 0


def test_validator_catches_a_missing_english_designation_or_a_shown_date(site, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(site["data"], data)
    strings = json.loads((data / "en" / "strings.json").read_text("utf-8"))
    del strings["designation:짬뽕 특화거리(군산시)"]          # 빈해원's designation loses its English name
    (data / "en" / "strings.json").write_text(json.dumps(strings, ensure_ascii=False), "utf-8")
    f = en_page(site["out"], f"place:{DZ_ID}")
    html = f.read_text("utf-8")
    url = "https://www.gunsan.go.kr/tour/m2555"
    try:
        # the 'Designations' row loses its list link, then shows the list's checked date again
        f.write_text(html.replace(f'<span class="dz-s"><a href="{url}"', '<span class="dz-s"><a href="#"'), "utf-8")
        errors, _, _ = validate(data, site["out"], "production")
        f.write_text(html.replace("Gunsan Matjip designations (2026)</a></span></li>",
                                  'Gunsan Matjip designations (2026)</a> · checked <span class="tn">2026-10-09</span></span></li>'),
                     "utf-8")
        dated, _, _ = validate(site["data"], site["out"], "production")
    finally:
        f.write_text(html, "utf-8")
    assert any(DZ_ID in x and "Designations 줄에 목록 이름·링크와 함께 없음" in x for x in errors), errors[:5]
    assert any(DZ2_ID in x and "영어 이름·목록 이름" in x for x in errors), errors[:5]
    assert any(DZ_ID in x and "확인일(2026-10-09)이 Designations 줄에 보임" in x for x in dated), dated[:5]
    assert any("확인·갱신 날짜가 화면에 보임" in x and "checked 2026-10-09" in x for x in dated), dated[:5]


def test_event_series_share_the_korean_slug(site):
    """A series' English record is keyed by the Korean page's slug (/events/<slug>/, the stored series slug); the
    Korean page links to that series on /en/events/ by the same slug, and the English page carries it as the id."""
    out = site["out"]
    events = json.loads((site["data"] / "events.json").read_text("utf-8"))
    slug = {e["slug"] for e in events}.pop()
    assert list(json.loads((site["data"] / "en" / "events.json").read_text("utf-8"))) == [slug]
    assert (out / "events" / slug / "index.html").exists()
    ko = (out / "events" / slug / "index.html").read_text("utf-8")
    assert f'href="/en/events/#{slug}"' in ko
    assert f'id="{slug}"' in (out / "en" / "events" / "index.html").read_text("utf-8")


def test_event_series_slugs_match_the_build():
    """pipeline.en_source.event_series names a series as pipeline.build.event_series does (slugs.series_slug): every
    stored series slug is reserved first, so a series without one never takes it — the Korean and English pages of a
    series share its slug."""
    evs = [{"id": "e1", "status": "published", "name": "2030 봄 장터", "start_date": "2030-04-01"},
           {"id": "e2", "status": "published", "name": "2029 가을 장터", "start_date": "2029-10-01", "slug": "bom-jangteo"},
           {"id": "e3", "status": "draft", "name": "2031 여름 장터", "start_date": "2031-07-01", "slug": "yeoreum"},
           {"id": "e4", "status": "published", "name": "2030 여름 장터", "start_date": "2030-07-01"}]
    S = types.SimpleNamespace(events_all=evs, slug_problems=[], abs=lambda path: path)
    published = sorted((e for e in evs if e["status"] == "published"),
                       key=lambda e: (e.get("start_date") or "9999", e.get("name", "")))
    ko = {sr["key"]: sr["slug"] for sr in B.event_series(published, S)}
    en = {sr["key"]: sr["slug"] for sr in event_series(evs)}
    assert en == ko and sorted(en.values()) == ["bom-jangteo", "bom-jangteo-2", "yeoreum-jangteo"]


def test_english_addresses_from_the_city_config():
    """address_en reads the address with the city's configuration (City.parse_address) and ends it with the city's
    English names; '' when a part is not read — never a guessed one."""
    daegu = citymod.from_site(json.loads((METRO / "site.json").read_text("utf-8")))
    city = citymod.from_site(json.loads((CITY / "site.json").read_text("utf-8")))
    gunsan = citymod.from_site(json.loads((SUBSET / "site.json").read_text("utf-8")))
    assert address_en("대구광역시 중구 동성로2길 80 (삼덕동1가)", daegu) == \
        "80 Dongseong-ro 2-gil (Samdeok-dong 1-ga), Jung-gu, Daegu"
    assert address_en("대구광역시 달성군 화원읍 사문진로 1", daegu) == "1 Samunjin-ro, Hwawon-eup, Dalseong-gun, Daegu"
    assert address_en("대구광역시 달서구 성서공단로 1 나동 2층", daegu) == ""          # a building part: not read
    assert address_en("전북특별자치도 군산시 월명로 382(미원동)", gunsan) == \
        "382 Wolmyeong-ro (Miwon-dong), Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 임피면 임피향교길 46", gunsan) == ""            # the 시 is not written
    assert address_en("대구광역시 중구 동성로2길 80", gunsan) == ""                   # another city
    # a 시 in a 도 (this city's config): its 읍·면 and 동, then the 시 and the 도 in the config's English names
    site = json.loads((CITY / "site.json").read_text("utf-8"))
    tail = f"{site['locality_en']}, {site['region_admin_en']}"
    admin = f"{site['region_admin']} {site['locality']}"
    assert address_en(f"{admin} 샘플로103번길 31-32 (가흥동)", city) == f"31-32 Saempeul-ro 103beon-gil (Gaheung-dong), {tail}"
    assert address_en(f"{admin} 풍기읍 샘플로 57-21", city) == f"57-21 Saempeul-ro, Punggi-eup, {tail}"
    assert address_en(f"{admin} 샘플로 1 샘플 건물", city) == ""                     # a building name: not read
    assert address_en("대구광역시 중구 동성로2길 80", city) == ""                     # another city


def test_city_words_come_from_site_json(tmp_path):
    """Without region_admin_en, locality_en and source.name_en the English pages leave out the sentence that needs
    them (never a guessed name); without English courses there is no link to /en/courses/."""
    data = en_min_data(tmp_path / "data", region_admin_en="", locality_en="",
                       source={**json.loads((SUBSET / "site.json").read_text("utf-8"))["source"], "name_en": ""})
    (data / "en" / "courses.json").write_text("{}", "utf-8")
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert stats["en"]["courses"] == 0 and not (out / "en" / "courses").exists()
    home = (out / "en" / "index.html").read_text("utf-8")
    assert '<p class="ho-k"><span class="ho-dot" aria-hidden="true"></span>Gunsan, Korea</p>' in home
    for f in _html_files(out):
        html = f.read_text("utf-8")
        assert 'href="/en/courses/' not in html, f
        assert "Official tourism site" not in html and "independently of" not in html, f
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]


def test_district_city_english_pages(tmp_path):
    """A 구·군 city (tests/fixtures/metro, regions.mode district) with three English place records written here for
    its '[샘플]' places: the list groups are the 구·군 in English with the Korean list's ids, the kicker reads
    '<region_en>, <구·군>, <동>' (법정동 'N가' kept), the 'none' group has the engine's English word, and the home names
    no province (the city is its own 시·도)."""
    data = tmp_path / "data"
    shutil.copytree(ROOT / "tests" / "fixtures" / "metro", data)
    s = json.loads((data / "site.json").read_text("utf-8"))
    s.update(languages=["ko", "en"], operator={**(s.get("operator") or {}), "contact": "corrections@fixture.test"})
    (data / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    (data / "en").mkdir()
    for k in ("places", "guides", "courses", "events", "strings"):
        (data / "en" / f"{k}.json").write_text("{}", "utf-8")
    hashes = current_hashes(data, city=citymod.of(s))
    names = {"metro-0001": "[Sample] Jung-gu Exhibition Hall A", "metro-0003": "[Sample] Suseong-gu Park C",
             "metro-0008": "[Sample] Place H"}
    ko = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    # the closed day the Korean first screen shows is translated too (a version that drops it fails validate:
    # key_fact_problems / list_closed_problems)
    closed = {pid: {"restdate": {"value": "[Sample] Mondays"}} for pid in names if (ko[pid].get("facts") or {}).get("restdate")}
    recs = {pid: {"slug": ko[pid]["slug"], "kind": ko[pid]["kind"], "name_ko": ko[pid]["name"], "name_en": name,
                  "name_en_source": "romanized", "summary": "[Sample] A fixture record.", "facts": closed.get(pid, {}),
                  "details": [], "faq": [], "ko_hash": hashes["places"][pid], "translated_at": "2026-10-10"}
            for pid, name in names.items()}
    (data / "en" / "places.json").write_text(json.dumps(recs, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert stats["en"]["places"] == 3 and stats["en"]["stale_skipped"]["places"] == 0
    kicker = re.search(r'<p class="kicker">(.*?)</p>', en_page(out, "place:metro-0001").read_text("utf-8")).group(1)
    assert re.sub(r"<[^>]+>", " ", kicker).split() == ["Things", "to", "do", "Daegu,", "Jung-gu,", "Samdeok-dong", "1-ga"]
    groups = re.findall(r'<h2 class="lg-g" id="([a-z0-9-]+)-h">([^<]+?) <span', (out / "en" / "places" / "index.html").read_text("utf-8"))
    assert groups == [("g-jung-gu", "Jung-gu"), ("g-suseong-gu", "Suseong-gu"), ("g-none", "District not listed")]
    assert ('<p class="ho-k"><span class="ho-dot" aria-hidden="true"></span>Daegu, Korea</p>'
            in (out / "en" / "index.html").read_text("utf-8"))
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]


def test_sample_build_has_no_english_site(tmp_path):
    out = tmp_path / "s"
    stats = build(SAMPLE, out, "sample")
    assert "en" not in stats and not (out / "en").exists()
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert "hreflang" not in html and 'class="mast-lang"' not in html, f
    errors, _, _ = validate(SAMPLE, out, "sample")
    assert errors == []


@pytest.mark.parametrize("case", ["city", "city_empty_en", "en_records_without_switch", "switch_without_places"])
def test_english_site_is_off_without_the_switch_and_records(case, tmp_path):
    """/en/ is built only when site.json languages lists "en" and data/<city>/en/places.json exists: a copy of
    this city's data with its English records and the switch off (languages ["ko"]), a copy with an en/ folder without
    places.json and "en" switched on, the en_min records with the switch off, and the switch on without
    en/places.json — no /en/ pages, no hreflang, no English link (an outside link to an English page — the
    emergency notice's VisitKorea pages — may say hreflang="en" on its <a>)."""
    if case == "city":
        data = tmp_path / "data"
        shutil.copytree(CITY, data)
        s = json.loads((data / "site.json").read_text("utf-8"))
        s["languages"] = ["ko"]
        (data / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    elif case == "city_empty_en":
        data = tmp_path / "data"
        shutil.copytree(CITY, data)
        (data / "en").mkdir(exist_ok=True)              # the city holds en/names.json and its records …
        (data / "en" / "places.json").unlink(missing_ok=True)   # … but without places.json there is no English site
        s = json.loads((data / "site.json").read_text("utf-8"))
        s["languages"] = ["ko", "en"]
        # the switch alone, not the completeness rule (site.json intl.require_complete stops this build with the list
        # of what is missing: tests/test_intl_site.py::test_complete_policy_stops_the_build_on_a_missing_translation)
        s["intl"] = {"require_complete": False}
        (data / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    elif case == "en_records_without_switch":
        data = en_min_data(tmp_path / "data", languages=["ko"])
    else:
        data = en_min_data(tmp_path / "data")
        (data / "en" / "places.json").unlink()
    assert en_site.load(State(data, "preview"), data) is None
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert "en" not in stats and not (out / "en").exists()
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert not re.search(r"<link[^>]*hreflang=", html) and 'class="mast-lang"' not in html, f
        assert 'href="/en/' not in html and "data-langmenu" not in html, f
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]


def test_page_scan_finds_hangul_outside_lang_ko():
    p = PageScan()
    p.feed('<html lang="en"><head><title>Hello</title></head><body><p>Hi 안녕</p><p><span lang="ko">군산</span></p>'
           '<img alt="사진" src="x.jpg"><a href="/places/동국사/" lang="ko">한국어</a></body></html>')
    assert p.html_lang == "en"
    assert p.hangul == ["Hi 안녕", "<img alt> 사진"]


def test_hreflang_problems_catch_one_sided_pairs():
    ko, en = "https://x.test/a/", "https://x.test/en/a/"
    both = [("ko", ko), ("en", en), ("x-default", ko)]
    assert hreflang_problems({"/a/index.html": (ko, both), "/en/a/index.html": (en, both)}) == []
    assert hreflang_problems({"/a/index.html": (ko, both), "/en/a/index.html": (en, [])})
    wrong = [("ko", ko), ("en", en), ("x-default", en)]
    assert hreflang_problems({"/a/index.html": (ko, wrong), "/en/a/index.html": (en, wrong)})


def test_slugs_and_sentences():
    assert en_slug("Eunpa Lake Park") == "eunpa-lake-park"
    assert en_slug("Course A Modern–Gogunsan") == "course-a-modern-gogunsan"
    assert en_slug("Where and when to eat jjamppong, marinated blue crab and bakdae in Gunsan") == \
        "where-and-when-to-eat-jjamppong-marinated-blue-crab"
    assert sentences_en("It is Registered Cultural Heritage No. 64. Dr. Lee built it. Open daily.") == \
        ["It is Registered Cultural Heritage No. 64.", "Dr. Lee built it.", "Open daily."]
    assert not HANGUL.search(en_slug("동국사 Dongguksa Temple"))


def _filter_bar(html: str) -> dict:
    """The list page's filter bar: {key: [(value, label, n)]}, the check box, the view switch and the rows' keys."""
    bar = re.search(r'<div class="filters" data-filters hidden>.*?<div class="ledger" data-ledger>', html, re.S)
    assert bar, "no filter bar"
    bar = bar.group(0)
    chips = {}
    for k, v, lab, n in re.findall(r'<button type="button" data-f="(\w+)" data-v="([^"]*)" aria-pressed="[^"]*">([^<]*?)\s*(?:<span class="tn">(\d+)</span>)?</button>', bar):
        chips.setdefault(k, []).append((html_unescape(v), lab.strip(), int(n or 0)))
    check = re.search(r'<input type="checkbox" data-f="check" value="(\w+)"> ([^<]*?) <span class="tn">(\d+)</span>', bar)
    conds = re.findall(r'<button type="button" data-cond="(\w+)" aria-pressed="false"><span class="c-ck" aria-hidden="true">'
                       r'</span>([^<]*?) <span class="tn">(\d+)</span></button>', bar)
    rows = re.findall(r'<li class="rec"[^>]*>', html)
    return {"chips": chips, "check": check.groups() if check else None, "conds": conds,
            "views": re.findall(r'data-view="(\w+)"', bar),
            "rows": rows, "result": re.search(r'<span data-result data-forms="([^"]*)" data-of="([^"]*)">', bar)}


def html_unescape(s: str) -> str:
    import html as H
    return H.unescape(s)


@pytest.mark.parametrize("seg", ["places", "food", "stays"])
def test_lists_have_the_korean_filters_in_english(site, seg):
    """QA 2026-10-15 SRC-01: every version's list has the Korean list's filter bar — type chips, 권역 and (attractions)
    theme chips, the condition chips (in the check box's place since 2026-10-31) and the list | map switch — with its own words and the Korean filter values
    (one URL vocabulary: /food/?type=중식 and /en/food/?type=중식 show the same restaurants). Over the English rows
    (en_min: a few places per list) the bar has exactly the chips the rule gives: a type carried by two rows or more,
    every region and theme of a row, a group shown only with more than one chip (themes: any)."""
    from collections import Counter
    out = site["out"]
    ko = _filter_bar((out / seg / "index.html").read_text("utf-8"))
    en_html = (out / "en" / seg / "index.html").read_text("utf-8")
    en = _filter_bar(en_html)
    attrs = {"type": ("data-types", r"\|"), "region": ("data-region", r"$^"), "theme": ("data-themes", r"\s+")}
    for k in ("type", "region", "theme"):
        kv = {v for v, _, _ in ko["chips"].get(k, [])}
        ev = {v for v, _, _ in en["chips"].get(k, [])}
        assert ev <= kv, (k, ev - kv)
        attr, sep = attrs[k]   # site.js has(): "|a|b|", one value, "a b"
        vals = lambda r: [x for x in re.split(sep, html_unescape((re.search(rf'{attr}="([^"]*)"', r) or [None, ""])[1])) if x]  # noqa: E731
        carried = Counter(v for r in en["rows"] for v in vals(r))
        want = {v for v, n in carried.items() if n >= (2 if k == "type" else 1) and v in kv}
        shown = {v for v in ev if v}
        assert shown == (want if (k == "theme" or len(want) > 1) else set()), (k, shown, want)
        for v, lab, n in en["chips"].get(k, []):
            assert lab and not HANGUL.search(lab), (k, v, lab)
            if v:   # each chip counts the rows that carry its value
                assert n == carried[v], (k, v, n, carried[v])
    # 조건으로 찾기 (pipeline/conditions.py) took the check box's place: the Korean list's condition chips in this
    # version's words, each counting the rows that meet it (data-conds)
    # (a list none of whose rows meets a condition keeps the check box: present.filter_vm)
    assert (en["check"] is None) == bool(en["conds"]) and (ko["check"] is None) == bool(ko["conds"])
    assert {c for c, _, _ in en["conds"]} <= {c for c, _, _ in ko["conds"]}
    for cid, lab, n in en["conds"]:
        assert lab and not HANGUL.search(lab), (cid, lab)
        assert int(n) == sum(1 for r in en["rows"] if cid in (re.search(r'data-conds="([^"]*)"', r) or [None, ""])[1].split())
    assert en["views"] == ko["views"] and set(en["views"]) <= {"list", "map"}
    assert all('data-region="' in r for r in en["rows"]) and len(en["rows"]) >= 1
    forms = json.loads(html_unescape(en["result"].group(1)))
    assert set(forms) == {"one", "other"} and all("{n}" in f for f in forms.values()) and "{m}" in en["result"].group(2)
    assert '<p class="empty" data-empty hidden>' in en_html


# ------------------------------------------------------------------ 예약하기 (pipeline/booking.py, ui.book)
def test_about_page_says_once_that_the_site_takes_no_bookings(site):
    """The about pages say it once, in their own words (locales.BOOK_WORDS, no strings.json key); en_min has no booking
    registry, so no page carries a booking button. (The buttons themselves: tests/test_booking.py.)"""
    from html import unescape
    from pipeline import locales as LC
    out = site["out"]
    for code in ("ko", "en"):
        about = unescape((out / ("" if code == "ko" else code) / "about" / "index.html").read_text("utf-8"))
        assert about.count(LC.BOOK_WORDS[code]["about"]) == 1, code
    assert not [f for f in out.rglob("*.html") if "booking_click" in f.read_text("utf-8")]


def test_every_english_place_page_keeps_its_address_in_jsonld(tmp_path):
    """A place with event cards kept its address, phone and hours out of its English JSON-LD (the event loop's
    record replaced the place's: the first site's evaluation 2026-10-21; this city's buseoksa and 7 more places × 8
    versions). Here the en_min event series is held at 근대역사박물관: every English place page whose Korean page has
    a PostalAddress has one too, that place's page (with its event card) among them, with its phone and hours."""
    data = en_min_data(tmp_path / "data")
    slug = KO_PLACES[STALE_ID]["slug"]
    events = json.loads((data / "events.json").read_text("utf-8"))
    for ev in events:
        ev["place_slug"] = slug
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    missing, checked, carded = [], 0, []
    for ko in sorted((out / "places").glob("*/index.html")):
        s = ko.read_text("utf-8")
        m = re.search(r'<link rel="alternate" hreflang="en" href="https?://[^/]+(/en/places/[^"]+)"', s)
        if not m or "PostalAddress" not in s:
            continue
        en = out / m.group(1).strip("/") / "index.html"
        if not en.exists():
            continue
        checked += 1
        html = en.read_text("utf-8")
        if 'href="/en/events/#' in html:
            carded.append(html)
        if "PostalAddress" not in html:
            missing.append(m.group(1))
    assert checked >= 5 and len(carded) == 1 and not missing, (checked, len(carded), missing[:5])
    node = next(n for raw in scan_file(en_page(out, f"place:{STALE_ID}")).jsonld_raw
                for n in json.loads(raw).get("@graph", [json.loads(raw)]) if str(n.get("@id", "")).endswith("#place"))
    ko_node = next(n for raw in scan_file(ko_page(out, STALE_ID)).jsonld_raw
                   for n in json.loads(raw).get("@graph", [json.loads(raw)]) if str(n.get("@id", "")).endswith("#place"))
    for key in ("address", "telephone", "openingHours"):
        assert bool(node.get(key)) == bool(ko_node.get(key)), key
