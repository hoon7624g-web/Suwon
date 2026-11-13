"""The English site (/en/, pipeline/en_site.py): built in production from a copy of data/gunsan in which one Korean
summary was edited after translation (its English record is then stale and must not be rendered)."""
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline.build import build
from pipeline.en_site import en_slug, sentences_en
from pipeline.validate import PageScan, hreflang_problems, scan_file, validate
from conftest import without_one_value_prose


@pytest.fixture(scope="module", autouse=True)
def _engine_both_values(engine_both_values):
    """This module checks the engine's both-values display on 군산각's data (tests/conftest.py)."""

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"
SAMPLE = ROOT / "data" / "sample"
STALE_ID = "gunsan-305395"      # 근대역사박물관: its Korean summary is edited in the copy
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("en")
    data = tmp / "data"
    shutil.copytree(GUNSAN, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = next(x for x in places if x["id"] == STALE_ID)
    p["summary"] = p["summary"] + " 번역 뒤에 바뀐 문장입니다."
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    # a stale record on purpose: the completeness rule (site.json intl.require_complete) would stop this build with
    # it (tests/test_intl_site.py checks that rule), so this copy turns it off
    s = json.loads((data / "site.json").read_text("utf-8"))
    s["intl"] = {"require_complete": False}
    (data / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    out = tmp / "dist"
    stats = build(data, out, "production")
    return {"data": data, "out": out, "stats": stats, "ko_slug": p["slug"]}


def _html_files(out: Path, prefix: str = "en"):
    return sorted((out / prefix).rglob("*.html"))


def test_english_routes_and_counts(site):
    out, en = site["out"], site["stats"]["en"]
    for path in ("en/index.html", "en/places/index.html", "en/food/index.html", "en/stays/index.html",
                 "en/guides/index.html", "en/courses/index.html", "en/events/index.html", "en/about/index.html",
                 "en/places/eunpa-lake-park/index.html", "en/guides/where-to-eat-in-gunsan-by-dish/index.html"):
        assert (out / path).exists(), path
    published = sum(1 for x in json.loads((site["data"] / "places.json").read_text("utf-8"))
                    if x.get("status") == "published" and not x.get("duplicate_of"))
    assert en["stale_skipped"]["places"] == 1 and en["places"] == published - 1   # every published place but the stale one
    assert en["pages"] == len(_html_files(out))
    for f in (out / "en" / "places").iterdir():   # slugs: lowercase ASCII words
        assert f.name == "index.html" or re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", f.name), f.name
    # QA 2026-10-15 SRC-03a: English has every published guide, and every version has a record (current or stale)
    # of every published Korean item — a version missing one is the gap English had (15 of 36 guides)
    guides = sum(1 for g in json.loads((site["data"] / "guides.json").read_text("utf-8")) if g.get("status") == "published")
    assert en["guides"] == guides == len([d for d in (out / "en" / "guides").iterdir() if d.is_dir()])
    zero = {"places": 0, "guides": 0, "courses": 0, "events": 0}
    sts = {"en": en, **site["stats"]["intl"]}
    assert len(sts) == 8 and all({k: st["untranslated"][k] for k in zero} == zero for st in sts.values()), \
        {c: st["untranslated"] for c, st in sts.items()}
    # columns (2026-10-25): their translations come after their pages' engine; until then no version has a column page
    # — one built before English had every column would take its id as slug there (SlugBook) and move later
    assert all(st["untranslated"]["columns"] == 0 for st in sts.values()) or not any(st["columns"] for st in sts.values()), \
        {c: (st["columns"], st["untranslated"]["columns"]) for c, st in sts.items()}


def test_no_id_slug_guide_pages_and_redirects_from_the_old_ones(site):
    """QA 2026-10-15 SRC-03c: the guides that had no English record were served at /<code>/guides/guide-NN/ in the
    other versions; with English records they take English slugs, and vercel.json sends each old address to the page
    of the same guide."""
    out = site["out"]
    assert not list(out.glob("*/guides/guide-*")) and not list(out.glob("guides/guide-*"))
    redirects = json.loads((ROOT / "vercel.json").read_text("utf-8"))["redirects"]
    old = [r for r in redirects if re.search(r"/guides/guide-\d+/$", r["source"])]
    assert len(old) == 21
    for r in old:
        gid = re.search(r"(guide-\d+)/$", r["source"]).group(1)
        assert r["source"] == f"/:lang(ja|zh-hans|zh-hant|de|fr|es|ru)/guides/{gid}/" and r["permanent"] is True
        slug = re.fullmatch(r"/:lang/guides/([a-z0-9-]+)/", r["destination"]).group(1)
        for code in ("en", "ja", "ru"):
            page = out / code / "guides" / slug / "index.html"
            assert f'data-record="guide:{gid}"' in page.read_text("utf-8"), (code, gid, slug)


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
    assert checked == len(list((site["out"] / "en" / "places").glob("*/index.html"))) > 300


def test_lang_and_no_hangul_outside_lang_ko(site):
    for f in _html_files(site["out"]):
        p = scan_file(f)
        assert p.html_lang == "en", f
        assert p.hangul == [], (f, p.hangul[:3])
    page = (site["out"] / "en" / "places" / "eunpa-lake-park" / "index.html").read_text("utf-8")
    assert '<span lang="ko">은파호수공원</span>' in page          # the Korean name, for a taxi or a Korean map
    assert '<meta property="og:locale" content="en_US">' in page


def test_hreflang_pairs_are_reciprocal(site):
    out = site["out"]
    pages = {}
    for f in sorted(out.rglob("*.html")):
        p = scan_file(f)
        pages["/" + f.relative_to(out).as_posix()] = (p.canonical, p.alternates)
    assert hreflang_problems(pages) == []
    ko = scan_file(out / "places" / "은파호수공원" / "index.html")
    assert dict(ko.alternates)["en"].endswith("/en/places/eunpa-lake-park/")
    assert dict(ko.alternates)["x-default"] == dict(ko.alternates)["ko"] == ko.canonical
    en = scan_file(out / "en" / "places" / "eunpa-lake-park" / "index.html")
    assert dict(en.alternates) == dict(ko.alternates)
    assert sum(1 for _, (_, a) in pages.items() if a) >= 2 * 400


def test_stale_record_is_not_rendered(site):
    out = site["out"]
    assert not (out / "en" / "places" / "modern-history-museum").exists()
    ko_page = out / "places" / site["ko_slug"] / "index.html"
    p = scan_file(ko_page)
    assert p.alternates == []                                          # no English twin: no hreflang
    # the English link falls back to the place's own English list, saying so (QA 2026-10-15 SRC-03b; it was /en/)
    assert ('<a class="mast-lang" href="/en/places/" hreflang="en" lang="en">English'
            '<small class="lang-note">Things to do · not translated</small></a>') in ko_page.read_text("utf-8")
    lists = (out / "en" / "places" / "index.html").read_text("utf-8")
    assert "/en/places/modern-history-museum/" not in lists
    for f in _html_files(out):
        assert f"place:{STALE_ID}" not in scan_file(f).records


def test_sitemap_has_only_indexable_english_urls(site):
    out = site["out"]
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [el.text for el in ET.parse(out / "sitemap.xml").getroot().iter(f"{ns}loc")]
    en_locs = [u for u in locs if urlsplit(u).path.startswith("/en/")]
    assert len(en_locs) == site["stats"]["en"]["indexable"] > 300
    for u in en_locs:
        p = scan_file(out / unquote(urlsplit(u).path).lstrip("/") / "index.html")
        assert not p.meta.get("robots", "").startswith("noindex"), u
    noindex = [f for f in (out / "en" / "places").glob("*/index.html")
               if scan_file(f).meta.get("robots", "").startswith("noindex")]
    assert noindex and site["stats"]["en"]["places"] - site["stats"]["en"]["places_indexable"] == len(noindex)
    llms = (out / "llms.txt").read_text("utf-8")
    assert "## English" in llms and "/en/guides/where-to-eat-in-gunsan-by-dish/" in llms
    for f in noindex:
        assert "/en/places/" + f.parent.name + "/" not in llms


def test_conflicting_values_show_both_with_the_note(site):
    # 진포해양공원: 군산시 09:00–21:00 against TourAPI's seasonal 09:00–18:00 / 09:00–17:00 — a real conflict (QA
    # 2026-10-15 J16 moved this test off 군산근대건축관, whose two sources state the same hours)
    page = scan_file(site["out"] / "en" / "places" / en_slug("Jinpo Marine Park") / "index.html")
    facts = page.blocks["facts"]
    assert "Sources differ — call before visiting" in facts
    assert "Gunsan City Culture and Tourism" in facts and "Korea Tourism Organization TourAPI" in facts
    rows = [r for r in page.fact_rows if "usetime" in r["keys"]]
    assert rows and "09:00–21:00 (last entry 20:30)" in rows[0]["exact"] and "09:00–18:00" in rows[0]["exact"]


def test_same_hours_from_two_sources_show_both_without_the_conflict_note(site):
    """J16: 군산근대건축관's two sources state the same opening and closing times (TourAPI adds last entry): both values
    and both sources are on the page, joined as 'or', and no 'Sources differ' line."""
    page = scan_file(site["out"] / "en" / "places" / "gunsan-modern-architecture-museum" / "index.html")
    facts = page.blocks["facts"]
    assert "Sources differ" not in facts and "Sources differ" not in page.body
    assert "Gunsan City Culture and Tourism" in facts and "Korea Tourism Organization TourAPI" in facts
    rows = [r for r in page.fact_rows if "usetime" in r["keys"]]
    assert rows and "Winter 09:00–17:00, summer 09:00–18:00" in rows[0]["exact"]
    assert "09:00–18:00 (last entry 17:30)" in rows[0]["exact"]


def test_production_validate_passes(site):
    errors, _, stats = validate(site["data"], site["out"], "production")
    errors = without_one_value_prose(errors)   # tests/conftest.py
    assert errors == [], errors[:10]
    assert stats["en_pages"] == site["stats"]["en"]["pages"]


def test_designations_in_english_with_list_link_and_no_checked_date(site):
    """The Korean page's official designations (schema.designations) on the English twin: a chip linking to the list,
    the 'Designations' row with the list's English name as a link — never its checked date (operator decision
    2026-10-09) — and JSON-LD award."""
    f = site["out"] / "en" / "places" / "bokseongnu" / "index.html"
    page = scan_file(f)
    label = "Gunsan Good Restaurant (2026, designated by Gunsan City)"   # strings rows from the table (2026-11-02)
    assert label in page.blocks["designations"]
    assert "https://www.gunsan.go.kr/tour/m2555" in page.block_hrefs["designations"]
    rows = [r for r in page.fact_rows if "designations" in r["keys"]]
    assert rows and f"{label} Gunsan Culture and Tourism: 'Gunsan Good Restaurant' designations (2026)" in rows[0]["text"]
    assert "2026-10-09" not in rows[0]["text"] and not re.search(r"\bchecked\b", page.visible, re.I)  # "rechecked with …" stays
    ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                             f.read_text("utf-8"), re.S)]
    node = next(n for g in ld for n in g.get("@graph", []) if str(n.get("@id", "")).endswith("#place"))
    assert node["award"] == label
    plain = scan_file(site["out"] / "en" / "places" / "eunpa-lake-park" / "index.html")
    assert "designations" not in plain.blocks and not [r for r in plain.fact_rows if "designations" in r["keys"]]


def test_english_photos_carry_creator_and_licence_page(site):
    """Search Console image metadata: every English place photo names its creator (the visible credit) and the
    page with its terms (the KOGL type page, as `license`) — the same fields as the Korean twin."""
    seen = 0
    for f in sorted((site["out"] / "en" / "places").glob("*/index.html")):
        ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                                 f.read_text("utf-8"), re.S)]
        node = next((n for g in ld for n in g.get("@graph", []) if str(n.get("@id", "")).endswith("#place")), {})
        for im in node.get("image") or []:
            assert im["creator"] == {"@type": "Organization", "name": im["creditText"]}
            assert im["acquireLicensePage"] == im["license"]
            seen += 1
    assert seen


def test_validator_catches_a_missing_english_designation_or_a_shown_date(site, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(site["data"], data)
    strings = json.loads((data / "en" / "strings.json").read_text("utf-8"))
    del strings["designation:안심식당"]
    (data / "en" / "strings.json").write_text(json.dumps(strings, ensure_ascii=False), "utf-8")
    f = site["out"] / "en" / "places" / "bokseongnu" / "index.html"
    html = f.read_text("utf-8")
    url = "https://www.gunsan.go.kr/tour/m2555"
    try:
        # the 'Designations' row loses its list link, then shows the list's checked date again
        f.write_text(html.replace(f'<span class="dz-s"><a href="{url}"', '<span class="dz-s"><a href="#"'), "utf-8")
        errors, _, _ = validate(data, site["out"], "production")
        row_end = "Gunsan Good Restaurant&#39; designations (2026)</a></span></li>"
        assert row_end in html
        f.write_text(html.replace(row_end, row_end.replace(
            "</a></span>", '</a> · checked <span class="tn">2026-10-09</span></span>')), "utf-8")
        dated, _, _ = validate(site["data"], site["out"], "production")
    finally:
        f.write_text(html, "utf-8")
    assert any("Bokseongnu" in x and "Designations 줄에 목록 이름·링크와 함께 없음" in x for x in errors), errors[:5]
    assert any("영어 이름·목록 이름" in x for x in errors), errors[:5]
    assert any("Bokseongnu" in x and "확인일(2026-10-09)이 Designations 줄에 보임" in x for x in dated), dated[:5]
    assert any("확인·갱신 날짜가 화면에 보임" in x and "checked 2026-10-09" in x for x in dated), dated[:5]


def test_sample_build_has_no_english_site(tmp_path):
    out = tmp_path / "s"
    stats = build(SAMPLE, out, "sample")
    assert "en" not in stats and not (out / "en").exists()
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert "hreflang" not in html and 'class="mast-lang"' not in html, f
    errors, _, _ = validate(SAMPLE, out, "sample")
    assert errors == []


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
    (one URL vocabulary: /food/?type=중식 and /en/food/?type=중식 show the same restaurants)."""
    out = site["out"]
    ko = _filter_bar((out / seg / "index.html").read_text("utf-8"))
    en_html = (out / "en" / seg / "index.html").read_text("utf-8")
    en = _filter_bar(en_html)
    for k in ("type", "region", "theme"):
        kv = {v for v, _, _ in ko["chips"].get(k, [])}
        ev = {v for v, _, _ in en["chips"].get(k, [])}
        assert ev <= kv and len(ev) >= len(kv) - 1, (k, kv - ev)   # the stale place may drop one chip below 2
        for v, lab, n in en["chips"].get(k, []):
            assert lab and not HANGUL.search(lab), (k, v, lab)
            if v:   # each chip counts the rows that carry its value
                attr = {"type": "data-types", "region": "data-region", "theme": "data-themes"}[k]
                sep = {"type": r"\|", "region": r"$^", "theme": r"\s+"}[k]   # site.js has(): "|a|b|", one value, "a b"
                vals = lambda r: re.split(sep, html_unescape((re.search(rf'{attr}="([^"]*)"', r) or [None, ""])[1]))
                hits = [r for r in en["rows"] if v in vals(r)]
                assert len(hits) == n, (k, v, n, len(hits))
    # 조건으로 찾기 (pipeline/conditions.py) took the check box's place: the Korean list's condition chips in this
    # version's words, each counting the rows that meet it (data-conds)
    assert en["check"] is None and ko["check"] is None
    assert en["conds"] and {c for c, _, _ in en["conds"]} <= {c for c, _, _ in ko["conds"]}
    for cid, lab, n in en["conds"]:
        assert lab and not HANGUL.search(lab), (cid, lab)
        assert int(n) == sum(1 for r in en["rows"] if cid in (re.search(r'data-conds="([^"]*)"', r) or [None, ""])[1].split())
    assert en["views"] == ["list", "map"] == ko["views"]
    assert all('data-region="' in r for r in en["rows"]) and len(en["rows"]) > 50
    forms = json.loads(html_unescape(en["result"].group(1)))
    assert set(forms) == {"one", "other"} and all("{n}" in f for f in forms.values()) and "{m}" in en["result"].group(2)
    assert '<p class="empty" data-empty hidden>' in en_html
    # the zero-result panel (outside evaluation 2026-10-18): site.js fills 'Remove filter: {v}' per filter, then the reset
    assert ('<div class="f-undo" data-f-undo data-one="Remove filter: {v}" hidden><button type="button" data-f-reset>'
            'Clear all filters</button></div>') in en_html
    off = sum(1 for r in en["rows"] if 'data-geo="1"' not in r)
    if off:
        assert f'> · Not on the map: {off} (see the list)</span>' in en_html
    # the desktop band's count per area links to its group (site.js keeps each number to the group's shown rows, and
    # an entry whose group shows none faint and no link): every entry names a group section and starts at its rows
    for h in ((out / seg / "index.html").read_text("utf-8"), en_html):
        band = re.search(r'<ol class="band-data only-wide"[^>]*>(.*?)</ol>', h, re.S)
        entries = re.findall(r'<a href="#([^"]+)"><b class="num tn">(\d+)</b>', band.group(1)) if band else []
        assert len(entries) > 1, seg
        for gid, n in entries:
            sec = re.search(rf'<section class="lg-group[^"]*" id="{re.escape(gid)}".*?</section>', h, re.S)
            assert sec and len(re.findall(r'<li class="rec"', sec.group(0))) == int(n), (seg, gid, n)


# ------------------------------------------------------------------ 예약하기 (pipeline/booking.py, ui.book)
BOOK_RX = re.compile(r'<div class="book[^"]*" data-block="booking">.*?</div>', re.S)
BOOK_A = re.compile(r'<a [^>]*data-track="booking_click"[^>]*>')


def _with(out: Path, code: str, needle: str, subs=("places", "food", "stays", "guides", "courses")) -> list[str]:
    """The pages of a version (ko: the root) under subs whose HTML contains needle."""
    base = out if code == "ko" else out / code
    return [t for s in subs for f in sorted((base / s).glob("*/index.html")) if needle in (t := f.read_text("utf-8"))]


def test_booking_button_on_the_place_s_first_screen(site):
    """A place with an official booking page in the data: one outlined 예약하기 link in data-block="booking" right after
    the route row, inside the opening (before the facts card), a plain link (no script, no hidden state), the note
    once; the Korean page opens the Korean booking page with no hreflang."""
    out = site["out"]
    [ko] = _with(out, "ko", 'data-entity-id="tourapi-2737403"', ("places",))
    links = BOOK_A.findall(ko)
    assert len(links) == 1 and 'class="btn btn-ol btn-book"' in links[0] and 'data-provider="forest"' in links[0]
    assert 'href="https://www.foresttrip.go.kr/indvz/main.do?hmpgId=0301"' in links[0] and "hreflang" not in links[0]
    block = BOOK_RX.search(ko).group(0)
    assert '<span class="book-t">예약하기</span>' in block and block.count("이 사이트는 예약을 받지 않습니다") == 1
    assert ko.index('class="route-row"') < ko.index('data-block="booking"') < ko.index('class="pl-side"')
    assert ko.count("이 사이트는 예약을 받지 않습니다") == 1 and not re.search(r"\shidden[\s>=]|motion-pending", block)
    # the German twin: the Korean page, said so; the ferry terminal in English and Japanese: the KSA English page
    [de] = _with(out, "de", 'data-entity-id="tourapi-2737403"', ("places",))
    assert "(auf Koreanisch)" in BOOK_RX.search(de).group(0) and 'hreflang="ko"' in BOOK_A.findall(de)[0]
    for code in ("en", "ja"):
        [p] = _with(out, code, 'data-entity-id="tourapi-2748799"', ("places",))
        [a] = BOOK_A.findall(p)
        assert 'href="https://island.theksa.co.kr/page/booking?lang=en"' in a and 'hreflang="en"' in a, code
    # an OTA (오블로모프: airbnb) or a client stay: no button in any version
    for code in ("ko", "en", "fr"):
        for pid in ("tourapi-3103191", "official-stay-meomum"):
            [p] = _with(out, code, f'data-entity-id="{pid}"', ("places", "stays"))   # Korean: every place is /places/
            # (the partner stay's own homepage link is direct_booking_click, operator 2026-11-04 — not this button)
            assert 'data-track="booking_click"' not in p and 'data-block="booking"' not in p, (code, pid)


def test_booking_boxes_on_guides_and_courses_only_where_the_data_has_targets(site):
    """6 guides and 3 courses carry the '예약·예매' box (h2#h-book, linked from the page nav) in every version; guide-12
    has bus, rail and ferry — the Japanese page opens Bustago's Japanese page; list, home and search pages none."""
    out = site["out"]
    for code in ("ko", "en", "ja", "ru"):
        guides = _with(out, code, 'data-block="booking"', ("guides",))
        courses = _with(out, code, 'data-block="booking"', ("courses",))
        assert (len(guides), len(courses)) == (6, 3), code
        assert all('<h2 id="h-book" class="book-h">' in t and 'href="#h-book"' in t for t in guides + courses), code
        places = _with(out, code, 'data-block="booking"', ("places", "food", "stays"))
        assert len(places) == 13, code
    [ko12] = _with(out, "ko", 'data-track="booking_click" data-provider="rail"', ("guides",))
    assert [re.search(r'data-provider="(\w+)"', a).group(1) for a in BOOK_A.findall(ko12)] == ["bus", "rail", "ferry"]
    [ja12] = _with(out, "ja", 'data-record="guide:guide-12"', ("guides",))
    assert 'href="https://www.bustago.or.kr/newweb/jp/index.do"' in BOOK_RX.search(ja12).group(0)
    [en_c] = _with(out, "en", 'data-record="course:gunsan-course-m2137-1"', ("courses",))
    assert 'data-provider="ferry"' in BOOK_RX.search(en_c).group(0)
    for rel in ("index.html", "stays/index.html", "places/index.html", "search/index.html", "guides/index.html",
                "courses/index.html", "about/index.html", "en/index.html", "en/stays/index.html", "ja/guides/index.html"):
        assert "booking_click" not in (out / rel).read_text("utf-8"), rel
    # the about pages say it once, in their own words (locales.BOOK_WORDS, no strings.json key)
    from html import unescape
    from pipeline import locales as LC
    for code in ("ko", *LC.ORDER):
        about = unescape((out / ("" if code == "ko" else code) / "about" / "index.html").read_text("utf-8"))
        assert about.count(LC.BOOK_WORDS[code]["about"]) == 1, code


def test_every_english_place_page_keeps_its_address_in_jsonld(site):
    """A place with event cards kept its address, phone and hours out of the English JSON-LD (the event loop's
    record replaced the place's: evaluation 2026-10-21, 29 places x 8 versions). Every English place page whose Korean
    page has a PostalAddress has one too."""
    out = site["out"]
    missing, checked = [], 0
    for ko in sorted((out / "places").glob("*/index.html")):
        s = ko.read_text("utf-8")
        m = re.search(r'<link rel="alternate" hreflang="en" href="https?://[^/]+(/en/places/[^"]+)"', s)
        if not m or "PostalAddress" not in s:
            continue
        en = out / m.group(1).strip("/") / "index.html"
        if not en.exists():
            continue
        checked += 1
        if "PostalAddress" not in en.read_text("utf-8"):
            missing.append(m.group(1))
    assert checked > 300 and not missing, missing[:5]
