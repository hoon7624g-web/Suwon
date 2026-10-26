"""The seven language versions (/ja/ /zh-hans/ /zh-hant/ /de/ /fr/ /es/ /ru/, pipeline/en_site.py + pipeline/locales.py).

Built in production from a tmp copy of tests/fixtures/gunsan_subset with tests/fixtures/en_min laid over it (the real
English records: tests/test_en_site.py), site.json `languages` switching every version on, and tiny fake
translations written here: four places (one with two-source hours, a restaurant with a designation and its closed day
inside the hours, a stay, one below the index rule), one more place whose record is stale (its ko_hash is not the
current Korean's), the food hub guide, a course and an event series with two-source values, and complete strings
(labels from the Korean, the pages' own words from pipeline/intl_text.py) — the records written exactly the way
tools/en_content.py merge writes them. Every version's pages use the slug the Korean record stores. A second, small
build of the sample data (no English) has Japanese only, plus Spanish with incomplete strings (not built).
Removed with the port (they read the first city's own data, which this repository does not hold): the transport
guide's booking links, the month-only event end, the seat-count parking, the parts-only nearby chapter, the cited
booking sites and the coordinate-source words of the real translations; the engine paths they cover are tested on
fixtures in tests/test_booking.py, tests/test_present.py and here."""
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline import intl_text
from pipeline import locales as LC
from pipeline.build import build
from pipeline.city import of as city_of
from pipeline.en_source import (Glossary, _name_table, course_item, current_hashes, event_item, event_series,
                                guide_item, place_item, romanize)
from pipeline.validate import hreflang_problems, scan_file, validate
from tools.en_content import PLACEHOLDER, strings_items

ROOT = Path(__file__).resolve().parent.parent
SUBSET, SAMPLE = ROOT / "tests" / "fixtures" / "gunsan_subset", ROOT / "data" / "sample"
NEW = ("ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
# hours from two sources · food with a designation and its closed day in the hours · stay · below the index rule
PLACES = ("gunsan-1379526", "gunsan-306591", "gunsan-307082", "gunsan-305401")
# a dated notice of the facility (pipeline/notices.py) on PLACES[0], written into the copy: one still current, one ended
NOTICES = [{"id": "test-current", "place_ids": [PLACES[0]], "kind": "hours", "start": "2099-10-09", "end": "2099-10-11",
            "from": "18:00", "to": "22:00", "last_entry": "21:40", "provider": "군산근대역사박물관 홈페이지",
            "url": "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9999", "checked_at": "2026-10-15",
            "until": "2099-10-11"},
           {"id": "test-ended", "place_ids": [PLACES[0]], "kind": "closed", "date": "2000-01-03",
            "provider": "군산근대역사박물관 홈페이지", "url": "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9998",
            "checked_at": "1999-12-30", "until": "2000-01-03"}]
STALE = "gunsan-305372"   # current in English (en_min), stale in every other version
GUIDE, COURSE = "guide-13", "gunsan-course-m2135-2"
SERIES = sorted({e["slug"] for e in json.loads((ROOT / "tests" / "fixtures" / "en_min" / "events.json").read_text("utf-8"))})[0]
# site.json emergency as the first city configured it (national numbers, KTO VisitKorea): the about pages' #emergency
EMERGENCY = {
    "checked_at": "2026-10-15",
    "sources": {"kto_safety": {"provider": "한국관광공사 VisitKorea", "label": "외국인 관광객 재난안전 안내",
                               "url": "https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=248145"},
                "kto_1330": {"provider": "한국관광공사 VisitKorea", "label": "1330 관광통역안내",
                             "url": "https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=140632&menuSn=454"}},
    "lines": [{"tel": "119", "what": "fire_ambulance", "ko": "소방·구급차", "src": "kto_safety"},
              {"tel": "112", "what": "police", "ko": "경찰", "src": "kto_safety"},
              {"tel": "1330", "what": "travel_helpline", "ko": "관광안내·통역(전화·채팅)", "abroad": "+82-2-1330",
               "src": "kto_1330"}],
    "phrases": ["English please", "Interpreter please"],
    "steps": [{"id": "interpreter", "src": "kto_safety",
               "ko": "한국어를 못 하면 전화가 연결된 뒤 'English please' 또는 'Interpreter please'라고 말하세요. 통역사와 이어 줍니다."},
              {"id": "location", "src": "kto_safety", "ko": "있는 곳은 근처 건물 이름이나 휴대전화가 보여 주는 위치(GPS)로 알리세요."}]}
WORD = {"ja": "情報", "zh-hans": "信息", "zh-hant": "資訊", "de": "Angabe", "fr": "Donnée", "es": "Dato", "ru": "Сведения"}
NAME = {"ja": "スポット", "zh-hans": "景点", "zh-hant": "景點", "de": "Ort", "fr": "Lieu", "es": "Lugar", "ru": "Место"}
PROSE = {"ja": "これは{n}番目の場所です。駐車場があります。",
         "zh-hans": "这是第{n}个地点。这里有停车场。",
         "zh-hant": "這是第{n}個地點。這裡有停車場。",
         "de": "Das ist der Ort Nummer {n}. Es gibt einen Parkplatz und die Halle ist für alle offen.",
         "fr": "C'est le lieu numéro {n} de cette page. Il y a un parking et la salle est ouverte pour tous.",
         "es": "Es el lugar número {n} de esta página. Hay un aparcamiento y la sala está abierta para todos.",
         "ru": "Это место номер {n} на этой странице. Здесь есть парковка, и зал открыт для всех."}
# (the first sentence of a summary is the page's lede; structured data repeats the whole summary and the validator
# looks for its first 25 characters on screen, so the fixture's first sentences are longer than that: a real
# translation's are — the German one runs on, '3.' reading as an ordinal)
QUESTION = {"ja": "{n}番目の質問ですか？", "zh-hans": "这是第{n}个问题吗？", "zh-hant": "這是第{n}個問題嗎？",
            "de": "Ist das die Frage {n}?", "fr": "Est-ce la question {n} ?", "es": "¿Es la pregunta {n}?",
            "ru": "Это вопрос {n}?"}
HANGUL = re.compile(r"[가-힣]")


def fake(code: str, text: str) -> str:
    """A value in the language: its words replaced, digits, times, phones and punctuation kept."""
    t = HANGUL.sub("", re.sub(r"[가-힣A-Za-z][가-힣A-Za-z'’]*", WORD[code], str(text or "")))
    return re.sub(r"\s+", " ", t).strip() or WORD[code]


def write_translations(data: Path, codes, stale: str | None = STALE, places=PLACES, guide=GUIDE, course=COURSE,
                       series=SERIES, strings_ok: bool = True) -> None:
    """data/<code>/{places,guides,courses,events,strings}.json for each code, shaped as en_content merge writes them."""
    pl = [p for p in json.loads((data / "places.json").read_text("utf-8"))
          if p.get("status") == "published" and not p.get("duplicate_of")]
    by_id, by_slug = {p["id"]: p for p in pl}, {p["slug"]: p for p in pl}
    names_en = _name_table(data, pl)
    city = city_of(json.loads((data / "site.json").read_text("utf-8")))
    hashes = current_hashes(data, city=city)
    gl = Glossary(pl, names_en, [])
    labels = [r for r in strings_items(data, pl) if not r["id"].startswith("ui:")]
    for code in codes:
        loc = LC.get(code)
        d = data / code
        d.mkdir()
        recs = {}
        for i, pid in enumerate([*places, *([stale] if stale else [])], 1):
            item = place_item(by_id[pid], names_en[pid], gl, True, city=city)
            facts = {}
            for f in item["facts"]:
                row = {"value": fake(code, f["value"])}
                if f.get("alternatives"):
                    row["alternatives"] = [{"value": fake(code, a["value"]), "provider": a["provider"]} for a in f["alternatives"]]
                    row["note"] = loc.conflict
                if f.get("also"):
                    row["also"] = [{"value": fake(code, a["value"]), "provider": a["provider"]} for a in f["also"]]
                facts[f["key"]] = row
            src = by_id[pid]
            recs[pid] = {"slug": item["slug"], "kind": item["kind"], "name_ko": item["name"],
                         loc.name_key: f"{NAME[code]}{i}", f"{loc.name_key}_source": "translated",
                         "summary": PROSE[code].format(n=i), "facts": facts,
                         "details": [{"heading": WORD[code], "text": PROSE[code].format(n=i), "source": x.get("source", "")}
                                     for x in src.get("details") or []],
                         "faq": [{"q": QUESTION[code].format(n=j), "a": PROSE[code].format(n=j), "source": x.get("source", "")}
                                 for j, x in enumerate(src.get("faq") or [], 1)],
                         "ko_hash": "0" * 16 if pid == stale else item["ko_hash"], "translated_at": "2026-10-13"}
        guides = {}
        if guide:
            g = next(x for x in json.loads((data / "guides.json").read_text("utf-8")) if x["id"] == guide)
            it = guide_item(g, by_slug, names_en, None)
            colon = "：" if loc.cjk else ": "
            guides[guide] = {"slug": it["slug"], "label": WORD[code],
                             "title": f"{NAME[code]}{colon}{WORD[code]}{loc.list_sep}{NAME[code]}",
                             "summary": PROSE[code].format(n=1), "body": [{"heading": WORD[code], "text": PROSE[code].format(n=k)}
                                                                         for k, _ in enumerate(it["body"], 1)],
                             "items": [{"place_slug": x["place_slug"], "reason": PROSE[code].format(n=k)}
                                       for k, x in enumerate(it["items"], 1)],
                             "faq": [{"q": QUESTION[code].format(n=k), "a": PROSE[code].format(n=k), "source": ""}
                                     for k, _ in enumerate(it["faq"], 1)],
                             "sources": [{"name": WORD[code], "url": s["url"]} for s in it["sources"]],
                             "ko_hash": hashes["guides"][guide], "translated_at": "2026-10-13"}
        courses = {}
        if course:
            c = next(x for x in json.loads((data / "courses.json").read_text("utf-8")) if x["id"] == course)
            it = course_item(c, by_slug, names_en, None)
            courses[course] = {"slug": it["slug"], "name": f"{NAME[code]} 1", "group": WORD[code],
                               "duration": WORD[code] if it["duration"] else "", "summary": PROSE[code].format(n=1),
                               "stops": [{"name": f"{NAME[code]}{k}", "note": "", "place_slug": s["place_slug"]}
                                         for k, s in enumerate(it["stops"], 1)],
                               "ko_hash": hashes["courses"][course], "translated_at": "2026-10-13"}
        events = {}
        if series:
            sr = next(x for x in event_series(json.loads((data / "events.json").read_text("utf-8"))) if x["slug"] == series)
            it = event_item(sr, None, city=city)
            newest = {k: fake(code, v) for k, v in it["newest"].items() if isinstance(v, str) and k not in ("id",)}
            newest.pop("address_en_candidate", None)
            newest.update(id=it["newest"]["id"], notes=[PROSE[code].format(n=k) for k, _ in enumerate(it["newest"]["notes"], 1)])
            events[series] = {"series_name": f"{NAME[code]} {WORD[code]}", "newest": newest,
                              "alternatives": {f: {"values": [fake(code, a["value"]) for a in vals],
                                                   "providers": [a["provider"] for a in vals], "note": loc.event_conflict}
                                               for f, vals in it["alternatives"].items()},
                              "highlights": [PROSE[code].format(n=k) for k, _ in enumerate(it["highlights"], 1)],
                              "program_notes": [PROSE[code].format(n=k) for k, _ in enumerate(it["program_notes"], 1)],
                              "usual": [{"text": WORD[code], "place": WORD[code]} for _ in it["usual"]],
                              "editions": [{"id": e["id"], "name": WORD[code], "period_text": WORD[code], "place_name": WORD[code]}
                                           for e in it["editions"]],
                              "sources": {s: WORD[code] for s in it["sources"]},
                              "ko_hash": it["ko_hash"], "translated_at": "2026-10-13"}
        strings = {r["id"]: {"ko": r["ko"], loc.tag: f"{WORD[code]}{k}"} for k, r in enumerate(labels, 1)}
        keys = intl_text.keys_for(loc)
        for key in keys[: None if strings_ok else len(keys) // 2]:
            src = intl_text.source_for(key)
            strings[f"chrome.{key}"] = {"en": src, loc.tag: " ".join([WORD[code], *PLACEHOLDER.findall(src)])}
        for name, store in (("places", recs), ("guides", guides), ("courses", courses), ("events", events),
                            ("strings", strings)):
            (d / f"{name}.json").write_text(json.dumps(store, ensure_ascii=False, indent=1), "utf-8")


def switch_on(data: Path, codes, **more) -> None:
    """site.json `languages` lists ko and these codes (the operator's switch), plus more site.json values."""
    s = json.loads((data / "site.json").read_text("utf-8"))
    s.update(languages=["ko", *codes], **more)
    (data / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    from tests.fixtures.build_en_min import overlay
    tmp = tmp_path_factory.mktemp("intl")
    data = tmp / "data"
    shutil.copytree(SUBSET, data)
    overlay(data)
    switch_on(data, ["en", *NEW], emergency=EMERGENCY)
    write_translations(data, NEW)
    (data / "notices.json").write_text(json.dumps(NOTICES, ensure_ascii=False), "utf-8")
    out = tmp / "dist"
    stats = build(data, out, "production")
    en = json.loads((data / "en" / "places.json").read_text("utf-8"))
    return {"data": data, "out": out, "stats": stats, "en": en}


def _slug(site, pid: str) -> str:
    """The page slug of a place in every version: the one its Korean record stores."""
    return next(p["slug"] for p in json.loads((site["data"] / "places.json").read_text("utf-8")) if p["id"] == pid)


def _ko_page(site, pid: str) -> Path:
    slug = next(p["slug"] for p in json.loads((site["data"] / "places.json").read_text("utf-8")) if p["id"] == pid)
    return site["out"] / "places" / slug / "index.html"


@pytest.mark.parametrize("code", NEW)
def test_routes_lang_and_names(site, code):
    out, loc = site["out"], LC.get(code)
    st = site["stats"]["intl"][code]
    assert st["places"] == len(PLACES) and st["guides"] == 1 and st["courses"] == 1 and st["event_series"] == 1
    assert st["stale_skipped"] == {"places": 1, "guides": 0, "courses": 0, "events": 0}
    for path in ("index.html", "places/index.html", "food/index.html", "stays/index.html", "guides/index.html",
                 "courses/index.html", "events/index.html", "about/index.html"):
        assert (out / code / path).exists(), (code, path)
    for i, pid in enumerate(PLACES, 1):
        f = out / code / "places" / _slug(site, pid) / "index.html"     # the Korean record's slug
        p = scan_file(f)
        assert p.h1 == f"{NAME[code]}{i}"
        assert p.html_lang == loc.html and p.meta["og:locale"] == loc.og
        assert p.hangul == [], (code, p.hangul[:3])
        page = f.read_text("utf-8")
        ko_name = next(x["name"] for x in json.loads((site["data"] / "places.json").read_text("utf-8")) if x["id"] == pid)
        assert f'<span lang="ko">{html.escape(ko_name)}</span>' in page   # the Korean name, for a taxi or a map
        assert f'"inLanguage":"{loc.html}"' in page
        assert f"{loc.home}places/" in page
    for f in (out / code).rglob("*.html"):
        p = scan_file(f)
        assert p.html_lang == loc.html and p.hangul == [], (f, p.hangul[:3])
    assert not (out / code / "places" / _slug(site, STALE)).exists()   # stale: no page


def test_hreflang_every_version_and_reciprocal(site):
    out = site["out"]
    pages = {}
    for f in sorted(out.rglob("*.html")):
        p = scan_file(f)
        pages["/" + str(f.relative_to(out)).replace("\\", "/")] = (p.canonical, p.alternates)
    assert hreflang_problems(pages) == []
    ko = scan_file(_ko_page(site, PLACES[0]))
    assert [h for h, _ in ko.alternates] == ["ko", "en", "ja", "zh-Hans", "zh-Hant", "de", "fr", "es", "ru", "x-default"]
    d = dict(ko.alternates)
    for code in NEW:
        assert d[LC.get(code).html].endswith(f"/{code}/places/{_slug(site, PLACES[0])}/")
        other = scan_file(out / code / "places" / _slug(site, PLACES[0]) / "index.html")
        assert dict(other.alternates) == d
    stale = scan_file(_ko_page(site, STALE))   # translated only in English (current) — the stale records add nothing
    assert [h for h, _ in stale.alternates] == ["ko", "en", "x-default"]


def test_language_menu_links_counterparts_or_homes(site):
    out = site["out"]
    html = _ko_page(site, PLACES[0]).read_text("utf-8")
    menu = re.search(r'<details class="lang-menu" data-langmenu>.*?</details>', html, re.S).group(0)
    items = re.findall(r'<a class="mast-lang" href="([^"]*)" hreflang="([^"]*)" lang="([^"]*)"( aria-current="true")?>([^<]*)</a>', menu)
    assert [i[4] for i in items] == ["한국어", "English", "日本語", "中文(简体)", "中文(繁體)", "Deutsch", "Français", "Español", "Русский"]
    assert items[0][3] and not any(i[3] for i in items[1:])
    slug = _slug(site, PLACES[0])
    assert [i[0] for i in items[2:]] == [f"/{c}/places/{slug}/" for c in NEW]
    assert "lang-note" not in menu
    # a Korean page without a twin in those versions: each version's list of the same kind, saying it is not translated
    # there in that version's words (QA 2026-10-15 SRC-03b; until then each version's home, with no note)
    stale = re.search(r'<details class="lang-menu".*?</details>', _ko_page(site, STALE).read_text("utf-8"), re.S).group(0)
    for c in NEW:   # the stale place is an attraction: the version's 'Things to do' list (its label is WORD here)
        assert (f'<a class="mast-lang" href="/{c}/places/" hreflang="{LC.get(c).html}" lang="{LC.get(c).html}">'
                f'{LC.get(c).label}<small class="lang-note">{WORD[c]} · {LC.get(c).untranslated}</small></a>'
                ) in stale, c
    # the phone panel and the footer carry the same note
    assert len(re.findall(r'<li><a href="/ru/places/" hreflang="ru" lang="ru">Русский<small class="lang-note">',
                          _ko_page(site, STALE).read_text("utf-8"))) == 2
    # a version's page: its own item current, Korean = the Korean twin, the others their twins
    ja = (out / "ja" / "places" / slug / "index.html").read_text("utf-8")
    jm = re.search(r'<details class="lang-menu".*?</details>', ja, re.S).group(0)
    assert 'href="/ja/places/%s/" hreflang="ja" lang="ja" aria-current="true">日本語' % slug in jm
    assert f'hreflang="ko" lang="ko">한국어' in jm and _ko_page(site, PLACES[0]).parent.name in unquote(jm)
    assert f'href="/ru/places/{slug}/" hreflang="ru" lang="ru">Русский' in jm
    assert f'<span class="vh">{WORD["ja"]}: </span>' in jm   # 'Language' in the version's own words
    # the phone panel and the footer list the other versions
    assert len(re.findall(r'<li><a href="[^"]*" hreflang="ru" lang="ru">Русский</a></li>', ja)) == 2


def _menu(page: Path) -> str:
    return re.search(r'<details class="lang-menu".*?</details>', page.read_text("utf-8"), re.S).group(0)


def _menu_items(page: Path) -> dict:
    """{hreflang: (href, note)} of a page's language menu."""
    return {h: (href, note) for href, h, note in re.findall(
        r'<a class="mast-lang" href="([^"]*)" hreflang="([^"]*)" lang="[^"]*"(?: aria-current="true")?>[^<]*'
        r'(?:<small class="lang-note">([^<]*)</small>)?</a>', _menu(page))}


def test_language_menu_sends_a_missing_page_to_the_list_with_a_note(site):
    """QA 2026-10-15 SRC-03b: a version without this page links its list of the same kind (guides here), else its
    home, with '<that page> · not translated' in its own words; a version with the page links it with no note.
    The 404 page has no notes."""
    out, data = site["out"], site["data"]
    guides = json.loads((data / "guides.json").read_text("utf-8"))
    ko_slug = next(g["slug"] for g in guides if g["id"] == "guide-02")   # no version translates it (en_min: guide-13)
    items = _menu_items(out / "guides" / ko_slug / "index.html")
    assert items["en"] == ("/en/guides/", "Guides · not translated")
    for c in NEW:
        assert items[LC.get(c).html] == (f"/{c}/guides/", html.escape(f"{WORD[c]} · {LC.get(c).untranslated}")), c
    hub = next(g["slug"] for g in guides if g["id"] == GUIDE)                 # every version has it: no note
    assert all(not note and href != f"/{c}/guides/" for c, (href, note) in
               ((c, _menu_items(out / "guides" / hub / "index.html")[LC.get(c).html]) for c in NEW))
    # a Korean-only page: each version's home, with the word for home
    items = _menu_items(out / "map" / "index.html")
    assert items["en"] == ("/en/", "Home · not translated")
    for c in NEW:
        assert items[LC.get(c).html] == (f"/{c}/", html.escape(f"{WORD[c]} · {LC.get(c).untranslated}")), c
    assert "lang-note" not in (out / "404.html").read_text("utf-8")


def test_search_pages_pair_in_the_language_menu_without_hreflang(site):
    """QA 2026-10-15 SRC-03d: every version's search page links the others' search pages (they were each version's
    home); the search pages stay noindex with no hreflang and out of the sitemap."""
    out = site["out"]
    ja = _menu_items(out / "ja" / "search" / "index.html")
    assert ja["ko"] == ("/search/", "") and ja["en"] == ("/en/search/", "") and ja["ru"] == ("/ru/search/", "")
    ko = _menu_items(out / "search" / "index.html")
    assert ko["en"] == ("/en/search/", "") and all(ko[LC.get(c).html] == (f"/{c}/search/", "") for c in NEW)
    for page in (out / "search" / "index.html", out / "ja" / "search" / "index.html"):
        assert scan_file(page).alternates == [] and "lang-note" not in _menu(page)
    assert "/search/" not in (out / "sitemap.xml").read_text("utf-8")


def test_untranslated_records_are_counted_per_version(site):
    """QA 2026-10-15 SRC-03a guard: the build counts, per version, the published Korean records it has no translation
    of at all (every fixture version, English too, translates only a few)."""
    city = city_of(json.loads((site["data"] / "site.json").read_text("utf-8")))
    hashes = current_hashes(site["data"], city=city)
    for c in ("en", *NEW):
        st = site["stats"]["en"] if c == "en" else site["stats"]["intl"][c]
        built = {"places": st["places"], "guides": st["guides"], "courses": st["courses"], "events": st["event_series"]}
        assert st["untranslated"]["guides"] == len(hashes["guides"]) - 1 > 0
        for kind in built:
            assert built[kind] + st["stale_skipped"][kind] + st["untranslated"][kind] == len(hashes[kind]), (c, kind)


def test_index_rule_sitemap_and_llms(site):
    out = site["out"]
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = {unquote(urlsplit(el.text).path) for el in ET.parse(out / "sitemap.xml").getroot().iter(f"{ns}loc")}
    llms = (out / "llms.txt").read_text("utf-8")
    for code in NEW:
        ok = f"/{code}/places/{_slug(site, PLACES[0])}/"
        low = f"/{code}/places/{_slug(site, PLACES[3])}/"
        assert ok in locs and low not in locs
        assert scan_file(out / low.strip("/") / "index.html").meta["robots"].startswith("noindex")
        assert not scan_file(out / ok.strip("/") / "index.html").meta.get("robots", "").startswith("noindex")
        assert f"## {LC.get(code).label}" in llms and f"/{code}/" in llms and low not in llms
        assert f"/{code}/food/" in llms


def test_production_validate_passes(site):
    errors, warnings, stats = validate(site["data"], site["out"], "production")
    assert errors == [], errors[:10]
    for code in NEW:
        assert stats[f"{code}_pages"] == site["stats"]["intl"][code]["pages"]


def test_conflicts_formats_and_fallback_names(site):
    out = site["out"]
    for code in ("ja", "zh-hant", "de", "ru"):
        loc = LC.get(code)
        page = scan_file(out / code / "places" / _slug(site, PLACES[0]) / "index.html")
        assert loc.conflict in page.blocks["facts"]
        ev = scan_file(out / code / "events" / "index.html").body   # the note as read (a flag span + the rest)
        assert loc.event_conflict in ev
        sr = next(x for x in event_series(json.loads((site["data"] / "events.json").read_text("utf-8"))) if x["slug"] == SERIES)
        assert loc.md(sr["newest"]["start_date"]) in ev
    # decimals: the English course page's straight-line distances, with a comma in German and Russian, a point in
    # Japanese (the same stored numbers: present.course_vm)
    def course_html(code):
        return " ".join(f.read_text("utf-8") for f in (out / code / "courses").rglob("index.html")
                        if f.parent.name != "courses")
    en_course = next(f for f in (out / "en" / "courses").rglob("index.html")
                     if f.parent.name == next(p.parent.name for p in (out / "de" / "courses").rglob("index.html")
                                              if p.parent.name != "courses"))
    kms = re.findall(r"(\d+)\.(\d) km", en_course.read_text("utf-8"))
    assert kms
    for a, b in kms:
        assert f"{a},{b} km" in course_html("de") and f"{a},{b} км" in course_html("ru") and f"{a}.{b} km" in course_html("ja")
    assert not re.search(r"\d+\.\d km", course_html("de"))
    # a guide item without a page in the version: the name in Kontsevich (Russian), romanized (German)
    g = next(x for x in json.loads((site["data"] / "guides.json").read_text("utf-8")) if x["id"] == GUIDE)
    by_slug = {p["slug"]: p for p in json.loads((site["data"] / "places.json").read_text("utf-8"))}
    own = {by_slug[p]["slug"] for p in by_slug if by_slug[p]["id"] in PLACES}
    others = [by_slug[it["place_slug"]]["name"] for it in g.get("items") or []
              if it.get("place_slug") in by_slug and it["place_slug"] not in own]
    assert others

    def guide_html(code):
        return " ".join(f.read_text("utf-8") for f in (out / code / "guides").rglob("index.html") if f.parent.name != "guides")
    ru_html, de_html = guide_html("ru"), guide_html("de")
    for ko_name in others:
        assert html.escape(LC.kontsevich(ko_name)) in ru_html and html.escape(romanize(ko_name)) in de_html


def test_facility_notice_in_every_version_until_its_end_date(site):
    """A current notice is under the key facts on the Korean page and on every version's page, in the version's own
    words with its dates and the provider's post; an ended one is on none (operator decision 2026-10-15)."""
    out = site["out"]
    ko = _ko_page(site, PLACES[0]).read_text("utf-8")
    assert 'data-notice="test-current"' in ko and "18:00–22:00 운영(입장 마감 21:40)" in ko and "test-ended" not in ko
    for code in ("en", *NEW):
        loc = LC.get(code)
        page = (out / code / "places" / _slug(site, PLACES[0]) / "index.html").read_text("utf-8")
        notes = page.split('class="kf-notes"', 1)[1].split("</div>", 1)[0]
        assert 'data-notice="test-current"' in notes and "test-ended" not in page, code
        assert html.escape(loc.date("2099-10-09")) in notes and html.escape(loc.date("2099-10-11")) in notes, code
        assert "18:00" in notes and "22:00" in notes and "21:40" in notes and "bbs_id=1&amp;id=9999" in notes, code
    en = (out / "en" / "places" / _slug(site, PLACES[0]) / "index.html").read_text("utf-8")
    assert "October 9, 2099 – October 11, 2099: open 18:00–22:00 (last entry 21:40)" in en


def test_locale_formats():
    d = "2026-10-13"   # a Tuesday
    assert [LC.get(c).date(d) for c in NEW] == ["2026年10月13日（火）", "2026年10月13日（周二）", "2026年10月13日（週二）",
                                               "13. Oktober 2026 (Di.)", "13 octobre 2026 (mar.)",
                                               "13 de octubre de 2026 (mar.)", "13 октября 2026 г. (вт)"]
    assert [LC.get(c).money(3000) for c in NEW] == ["3,000ウォン", "3,000韩元", "3,000韓元", "3.000 Won",
                                                   "3\u202f000 wons", "3.000 wones", "3\u202f000 вон"]
    assert [LC.get(c).dist(1234) for c in NEW] == ["1.2 km", "1.2 km", "1.2 km", "1,2 km", "1,2 km", "1,2 km", "1,2 км"]
    assert LC.get("en").date(d) == "October 13, 2026" and LC.get("en").md(d) == "Oct 13"
    # a month standing alone (an end the source gives only as a month): Russian in the nominative
    assert [LC.get(c).mon("2026-10") for c in ("en", "de", "ja", "ru")] == ["Oct", "Okt.", "10月", "окт."]
    assert LC.get("ru").mon("2026-05") == "май" and LC.get("ru").md("2026-05-01") == "1 мая"
    ru = LC.get("ru")
    assert [ru.plural_form(n) for n in (1, 2, 5, 11, 21, 22, 25)] == ["one", "few", "many", "many", "one", "few", "many"]
    assert LC.get("ja").sentences("一つ目です。二つ目です！三つ目？") == ["一つ目です。", "二つ目です！", "三つ目？"]
    assert LC.get("de").sentences("Am 13. Oktober ist es offen. Nr. 5 ist zu.") == ["Am 13. Oktober ist es offen.", "Nr. 5 ist zu."]
    assert LC.kontsevich("군산") == "Кунсан" and LC.kontsevich("신라") == "Силла" and LC.kontsevich("선유도") == "Сонюдо"
    assert LC.area_name("장미동", "ru") == "Чанми-дон" and LC.area_name("장미동", "de") == "Jangmi-dong"


def test_missing_language_and_incomplete_strings(tmp_path, capsys):
    """No data/<city>/<code>: no pages, no hreflang, no menu item. Incomplete UI words: not built (a warning). Without
    English, a version's slugs are the Korean records' own. A version whose folder exists while site.json `languages`
    leaves it out is not built either (Intl.off). A version that lacks translations of published records gets a build
    warning with the count (QA 2026-10-15 SRC-03a)."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))   # the sample's contact is a Korean placeholder
    site["operator"]["contact"] = "corrections@test.invalid"
    site["languages"] = ["ko", "ja", "es"]   # de has its records but stays off (not listed)
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    pid = json.loads((data / "places.json").read_text("utf-8"))[0]["id"]
    write_translations(data, ["ja"], stale=None, places=(pid,), guide=None, course=None, series=None)
    write_translations(data, ["es"], stale=None, places=(pid,), guide=None, course=None, series=None, strings_ok=False)
    write_translations(data, ["de"], stale=None, places=(pid,), guide=None, course=None, series=None)
    out = tmp_path / "dist"
    capsys.readouterr()
    stats = build(data, out, "sample")
    assert stats["intl"]["ja"]["places"] == 1 and stats["intl_skipped"]["es"] > 0 and "en" not in stats
    untranslated = stats["intl"]["ja"]["untranslated"]
    published = sum(1 for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("status") == "published")
    assert untranslated["places"] == published - 1 > 0
    assert f"경고: ja 번역이 없는 공개 항목 {sum(untranslated.values())}건" in capsys.readouterr().err
    assert (out / "ja").exists() and not (out / "es").exists() and not (out / "en").exists() and not (out / "de").exists()
    assert "de" not in stats["intl"]
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert 'hreflang="es"' not in html and 'hreflang="en"' not in html and 'lang="es"' not in html, f
        assert 'hreflang="de"' not in html, f
    ko = next(f for f in (out / "places").glob("*/index.html"))
    menu = re.findall(r'class="mast-lang" href="([^"]*)" hreflang="([^"]*)"', ko.read_text("utf-8"))
    assert [h for _, h in menu] == ["ko", "ja"]
    slug = next(p.parent.name for p in (out / "ja" / "places").glob("*/index.html"))
    assert slug == json.loads((data / "places.json").read_text("utf-8"))[0]["slug"]   # the Korean record's slug
    errors, warnings, _ = validate(data, out, "sample")
    assert errors == [], errors[:5]
    assert any("/es/" in w and "chrome" in w for w in warnings)


def test_complete_policy_stops_the_build_on_a_missing_translation(tmp_path, capsys):
    """site.json intl.require_complete (user instruction 2026-10-24): a version without the translation of a published
    record stops the build and names what is missing — the record is not left out, its name not filled by sound."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["operator"]["contact"] = "corrections@test.invalid"
    site["languages"] = ["ko", "ja"]
    site["intl"] = {"require_complete": True}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    pid = json.loads((data / "places.json").read_text("utf-8"))[0]["id"]
    write_translations(data, ["ja"], stale=None, places=(pid,), guide=None, course=None, series=None)
    capsys.readouterr()
    with pytest.raises(SystemExit, match="외국어 판 번역이 모자라"):
        build(data, tmp_path / "dist", "sample")
    assert "오류: ja: 번역이 없는 places" in capsys.readouterr().err


def test_validator_catches_wrong_script_on_a_page(site, tmp_path):
    """The rendered-text check: Simplified characters on a Traditional page, a Chinese-only answer on a Japanese one
    (validated in an output folder with only these two pages, so only their findings matter here)."""
    out = tmp_path / "dist"
    slug = _slug(site, PLACES[0])
    for code, bad in (("zh-hant", PROSE["zh-hans"].format(n=1)), ("ja", "这是第一个地点停车场开放时间很长。")):
        src = site["out"] / code / "places" / slug / "index.html"
        dst = out / code / "places" / slug / "index.html"
        dst.parent.mkdir(parents=True)
        dst.write_text(src.read_text("utf-8").replace(PROSE[code].format(n=1), bad), "utf-8")
    errors, _, _ = validate(site["data"], out, "production")
    assert any("zh-hant" in x and "Simplified characters" in x for x in errors), errors[:5]
    assert any("/ja/" in x and "no kana" in x for x in errors), errors[:5]


def test_validator_reads_japanese_citations_and_unspaced_sentences():
    """2026-10-14 (first /ja/ build): a citation line '出典：群山市文化観光' is a label of names, not a kana-less
    sentence; and Japanese/Chinese structured-data text is compared without whitespace, sentence by sentence (the
    page joins elements with a space and the first sentence is often under 25 characters) — every sentence must
    still be on screen."""
    from pipeline.validate import PageScan, jsonld_visibility
    html = ('<html lang="ja"><body><div data-block="faq"><div class="qa"><h3>予約できますか？</h3><p>はい、予約できます。'
            '</p></div><p class="ch-notes">出典：群山市文化観光</p></div>'
            '<div data-block="summary"><p class="lede">メロディは体験施設です。</p></div><dl><dt>電話</dt><dd>010</dd></dl>'
            '<p class="lede-more">ブドウ収穫の体験を予約制で運営しています。</p></body></html>')
    p = PageScan()
    p.feed(html)
    assert "出典：群山市文化観光" in "".join(p.notes) and "出典" in p.blocks["faq"]
    node = {"@type": "Place", "description": "メロディは体験施設です。ブドウ収穫の体験を予約制で運営しています。"}
    assert jsonld_visibility([node], p) == []
    node["description"] += "画面にない文です。"
    assert jsonld_visibility([node], p) and "画面にない" in jsonld_visibility([node], p)[0]


def test_every_about_page_lists_the_emergency_numbers(site):
    """Operator 2026-10-15 (QA C16/C21): /about/#emergency in Korean and every version, in its own words — the numbers
    of site.json emergency as call links and the KTO VisitKorea pages they come from (the date this site checked them
    stays in the data: operator 2026-10-09), before the assistant's section (the assistant links it: prompt rule 14)."""
    heads = {"": "긴급 연락처", "en": "Emergency numbers", "ja": "緊急連絡先", "zh-hans": "紧急联系电话", "zh-hant": "緊急聯絡電話",
             "de": "Notrufnummern", "fr": "Numéros d’urgence", "es": "Números de emergencia", "ru": "Экстренные номера"}
    for code, head in heads.items():
        page = (site["out"] / code / "about" / "index.html").read_text("utf-8")
        assert page.index('id="emergency"') < page.index('id="chatbot"'), code
        sec = page[page.index('id="emergency"'):]
        sec = sec[:sec.index("</section>")]
        assert f">{html.escape(head)}</h2>" in sec, code
        for n in ("119", "112", "1330", "+82-2-1330"):
            assert f'href="tel:{n}"' in sec, (code, n)
        assert "vcontsId=248145" in sec and "vcontsId=140632" in sec and "2026-10-15" not in sec, code
        assert "English please" in sec and "Interpreter please" in sec, code
        if code:
            assert not HANGUL.search(sec), (code, HANGUL.findall(sec)[:5])


def test_every_language_version_has_its_own_site_search(site):
    """Owner 2026-10-14 ('이 언어들도 다 검색이 되는 거지?'): each version searches in its own language — the bar's
    field (a GET form to <home>search/), the search page (noindex, not in the sitemap) with this version's words for
    search.js, and <home>search/index.json with this version's names (a place's Korean name finds it too)."""
    import json as _json
    import re as _re
    out = site["out"]
    en = out / "en"
    home = (en / "index.html").read_text("utf-8")
    assert '<form class="hs" id="hs" action="/en/search/" method="get" role="search" data-hs>' in home
    assert 'placeholder="Search places, dishes, areas"' in home and 'href="/en/search/" data-hs-open' in home
    page = (en / "search" / "index.html").read_text("utf-8")
    assert '<meta name="robots" content="noindex, follow">' in page or 'content="noindex' in page
    region_en = json.loads((site["data"] / "site.json").read_text("utf-8"))["region_en"]
    assert 'data-search data-index="/en/search/index.json" data-words="' in page and f"Search {region_en}" in page
    words = _json.loads(_re.search(r'data-words="([^"]+)"', page).group(1).replace("&#34;", '"').replace("&quot;", '"'))
    assert words["kinds"]["food"] and "{q}" in words["none"]
    rows = _json.loads((en / "search" / "index.json").read_text("utf-8"))
    assert rows and all(r["p"].startswith("/en/") for r in rows)
    places = [r for r in rows if r["k"] in ("attraction", "food", "stay")]
    assert places and all(not _re.search(r"[가-힣]", r["n"]) for r in places)
    # the Korean name finds it too (a few Korean names are Latin letters only, 'MCL')
    assert all(r["a"] for r in places) and sum(bool(_re.search(r"[가-힣]", r["a"])) for r in places) > .9 * len(places)
    sitemap = (out / "sitemap.xml").read_text("utf-8")
    assert "/search/" not in sitemap
    for code in NEW:                                                   # every other version the same, in its words
        loc = LC.get(code)
        assert (out / code / "search" / "index.json").exists(), code
        page = (out / code / "index.html").read_text("utf-8")
        assert f'action="/{code}/search/"' in page and f'placeholder="{LC.SEARCH_WORDS[code]["bar"]}"' in page, code


def _search_words(page: str) -> dict:
    return json.loads(html.unescape(re.search(r'data-words="([^"]+)"', page).group(1)))


SEARCH_STRIP = re.compile(r"[\s·\-()（）\[\]|,]")


def _found(rows: list[dict], query: str) -> list[dict]:
    """assets/search.js score() replayed: the rows a query finds (any of n, a, o, v, m, g, or 동·권역·type)."""
    def norm(s):
        return SEARCH_STRIP.sub("", str(s or "").lower())
    q = norm(query)
    return [r for r in rows if any(q in norm(r.get(f)) for f in ("n", "a", "o", "v", "m", "g"))
            or q in norm(" ".join([r.get("d") or "", r.get("r") or "", r.get("t") or ""]))]


def test_nothing_found_helps_in_every_version_without_naming_a_place(site):
    """QA 2026-10-15 F08: a search that finds nothing no longer unfolds every place. Each version's page carries the
    words for it (one 'nothing matches' sentence, 'did you mean', the diet note) and the help search.js shows — the
    list pages, the AI chat asked the query, every place only on request — hidden in the markup (without JS the
    directory answers). The diet note says the site has no halal/vegetarian/allergy data: no search row and nothing
    the chat knows may carry such a word (else the note must change)."""
    out = site["out"]
    for code in ("en", *NEW):
        page = (out / code / "search" / "index.html").read_text("utf-8")
        w = _search_words(page)
        assert {"sug", "diet"} <= set(w) and "{q}" in w["none"], code
        assert len(re.findall(r"[.。！!]", w["none"].replace("{q}", "x"))) <= 1, (code, w["none"])
        help_ = re.search(r'<div class="res-help" data-none-help hidden>(.*?)\n    </div>', page, re.S)
        assert help_, code
        h = help_.group(1)
        assert re.search(r'<button type="button" class="btn" data-chat-open data-chat-q="">[^<]+</button>', h), code
        assert "data-show-all" in h and h.count(f'href="/{code}/') >= 3, code
        assert 'id="h-dir" tabindex="-1"' in page, code
        assert not HANGUL.search(html.unescape(re.sub(r"<[^>]+>", " ", h)) + " ".join(str(v) for v in w.values())), code
    ko = (out / "search" / "index.html").read_text("utf-8")
    h = re.search(r'<div class="res-help" data-none-help hidden>(.*?)\n    </div>', ko, re.S).group(1)
    assert 'data-chat-q=""' in h and "data-show-all" in h and 'href="/places/"' in h and 'href="/videos/"' not in h
    # one source for the diet words: the regex of search.js, read the way JS reads it (Latin words at a word start)
    js = (ROOT / "templates" / "assets" / "search.js").read_text("utf-8")
    diet = re.compile(re.search(r"var DIET = /(.+?)/i;", js).group(1), re.I)
    assert diet.search("Halal food") and diet.search("할랄") and diet.search("веганская") and not diet.search("navegan")
    files = [*out.glob("**/search/index.json"), out / "chat" / "docs.json"]
    assert len(files) == 10
    for f in files:
        hit = diet.search(f.read_text("utf-8"))
        assert not hit, (f, hit and hit.group(0))


def test_other_language_names_find_the_same_places_courses_guides_and_events(site):
    """QA 2026-10-15 U10 / F-latin-on-ko: every search row carries its names in the other versions (o; a course's
    stops there: v) — '선유도' on /en/search/ finds what 'Seonyudo' finds (courses, guides and events too, not only
    the places), the Korean /search/ finds the romanised names, and a version other than English has the English
    names as well."""
    out = site["out"]
    en_rows = json.loads((out / "en" / "search" / "index.json").read_text("utf-8"))
    for r in en_rows:
        if r["k"] in ("course", "guide", "event"):
            assert HANGUL.search(r.get("o") or ""), r
        if r["k"] == "course":
            assert HANGUL.search(r.get("v") or ""), r
    # a stop of the English course that has an English page: its Korean name finds the place and the course, its
    # English name finds no more than the Korean one does
    course = next(c for c in json.loads((site["data"] / "courses.json").read_text("utf-8")) if c["id"] == COURSE)
    by_slug = {p["slug"]: p for p in json.loads((site["data"] / "places.json").read_text("utf-8"))}
    stop = next(by_slug[s["place_slug"]] for s in course["stops"] if by_slug.get(s.get("place_slug") or "", {}).get("id") in site["en"])
    roman, korean = _found(en_rows, site["en"][stop["id"]]["name_en"]), _found(en_rows, stop["name"])
    assert {r["p"] for r in roman} <= {r["p"] for r in korean}
    assert {"attraction", "course"} <= {r["k"] for r in korean} or {"food", "course"} <= {r["k"] for r in korean}
    ko_rows = json.loads((out / "search" / "index.json").read_text("utf-8"))
    ko_name = {p["id"]: p["name"] for p in json.loads((site["data"] / "places.json").read_text("utf-8"))}
    ja_rows = json.loads((out / "ja" / "search" / "index.json").read_text("utf-8"))
    for pid in PLACES:
        name_en = site["en"][pid]["name_en"]
        row = next(r for r in ko_rows if r["n"] == ko_name[pid] and r["k"] in ("attraction", "food", "stay"))
        assert name_en in (row.get("o") or "").split(" · "), (pid, row)
        row = next(r for r in ja_rows if r["a"] == ko_name[pid])   # the Korean name finds it, the English one too
        assert name_en in (row.get("o") or "").split(" · "), (pid, row)
    en_name = site["en"][stop["id"]]["name_en"]
    assert "course" in {r["k"] for r in _found(ko_rows, en_name)}   # the Korean search finds the romanised name too
    assert not any(r.get("o") == r["n"] for r in ko_rows + en_rows + ja_rows)


def test_every_language_place_page_has_the_nearby_chapter_markup(site):
    """The 주변·함께 가기 chapter (templates/_near.html.j2, locales.NEAR_WORDS) in the versions: an English place page on
    the English course (en_min) carries the course segment (its course chip to its stop, #s<n>) in English only; every
    version's chapters have no Hangul and the words of their own NEAR_WORDS."""
    out = site["out"]
    stop = next(f for f in (out / "en" / "places").glob("*/index.html") if 'class="nb-seg"' in f.read_text("utf-8"))
    h = stop.read_text("utf-8")
    b = h[h.index('data-block="nearby"'):h.index("</section>", h.index('data-block="nearby"'))]
    assert b.count('class="nb-seg"') == b.count('aria-current="location"') >= 1
    assert re.findall(r'<a class="crs" href="(/en/courses/[^"#]+/#s\d+)" data-track="course_click"', b)
    assert not HANGUL.search(b) and LC.NEAR_WORDS["en"]["order"] in html.unescape(b)
    for code in NEW:
        w = LC.NEAR_WORDS[code]
        for f in (out / code / "places").glob("*/index.html"):
            h = f.read_text("utf-8")
            if 'data-block="nearby"' not in h:
                continue
            b = h[h.index('data-block="nearby"'):h.index("</section>", h.index('data-block="nearby"'))]
            assert not HANGUL.search(b), (code, f)
            if 'class="nb-seg"' in b:
                assert w["order"] in html.unescape(b) and w["key"] in html.unescape(b), (code, f)


def test_list_filter_words_cover_every_version():
    """QA 2026-10-15 SRC-01: the list filter bar's own words (locales.LIST_WORDS) exist for Korean and every version,
    each with the same keys, hand-written (no English stand-in for a version that lacks them)."""
    assert set(LC.LIST_WORDS) >= {"ko", *LC.ORDER}
    for code, w in LC.LIST_WORDS.items():
        assert set(w) == set(LC.LIST_WORDS["ko"]), code
        assert all(str(v).strip() for v in w.values()) and "{m}" in w["of"], code
        if code != "ko":
            assert not HANGUL.search(" ".join(w.values())), code


def _bar(h: str) -> str:
    m = re.search(r'<div class="filters" data-filters hidden>.*?<div class="ledger" data-ledger>', h, re.S)
    assert m, "no filter bar"
    return m.group(0)


@pytest.mark.parametrize("code", NEW)
def test_every_version_list_has_the_filter_bar_and_the_map_count(site, code):
    """QA 2026-10-15 SRC-01 / F04: every version's places, food and stays lists carry the Korean list's filter bar in
    their own words (no Korean script once the tags and data-* attributes are stripped — the filter values are the
    Korean ones), every row its filter keys, the kind's check box with its label from strings.json and the number of
    rows that carry its flag; the '지도 n' count of the list | map switch is the rows with coordinates (data-geo), which
    are exactly the map's points."""
    out, loc, w = site["out"], LC.get(code), LC.LIST_WORDS[code]
    strings = json.loads((site["data"] / code / "strings.json").read_text("utf-8"))
    for seg, kind in (("places", "attraction"), ("food", "food"), ("stays", "stay")):
        h = (out / code / seg / "index.html").read_text("utf-8")
        bar = _bar(h)
        rows = re.findall(r'<li class="rec"[^>]*>', h)
        assert rows and all('data-region="' in r for r in rows), (code, seg)
        check = re.search(r'<input type="checkbox" data-f="check" value="(\w+)"> ([^<]*?) <span class="tn">(\d+)</span>', bar)
        assert check and html.unescape(check.group(2)) == strings[f"LIST_CFG.{kind}.check"][loc.tag], (code, seg)
        assert int(check.group(3)) == sum(1 for r in rows if f'data-{check.group(1)}="1"' in r), (code, seg)
        if bar.count('data-f="type"') > 1:
            assert f'role="group" aria-label="{w["type"]}"' in bar, (code, seg)
        geo = sorted(re.search(r'id="(r\d+)"', r).group(1) for r in rows if 'data-geo="1"' in r)
        pts = re.search(r"data-points='([^']*)'", h)
        if pts:
            ids = sorted(p["id"] for p in json.loads(html.unescape(pts.group(1)))["list"])
            assert geo == ids, (code, seg)
            assert f'role="group" aria-label="{w["view"]}"' in bar and f'{w["map"]} <span class="tn">{len(ids)}</span>' in bar
            assert re.search(r'<span (?:class="muted" )?data-geo-cap data-forms="[^"]+">', h), (code, seg)
        else:
            assert not geo and "data-view=" not in bar, (code, seg)
        assert f'<p class="empty" data-empty hidden>{html.escape(w["empty"], quote=False)}</p>' in h, (code, seg)
        assert not HANGUL.search(html.unescape(re.sub(r"<[^>]+>", " ", bar))), (code, seg)


def test_closed_day_cells_follow_the_korean_in_every_version(site):
    """QA 2026-10-15 SRC-04: the closed day inside a food place's hours value (복성루: '10:00~16:00 일요일,공휴일 휴무') is in
    every version's list cell as on the Korean list — never 'not listed' — and the hours cell does not repeat it."""
    out, pid = site["out"], PLACES[1]

    def cells(h: str, place: str) -> dict:
        row = next(x for x in h.split('<li class="rec"')[1:] if f'data-place="{place}"' in x)
        return {k: m for k, m in ((k, re.search(rf'<div class="c-{k}( is-conflict)?">(.*?)</div>', row, re.S))
                                  for k in ("hours", "closed")) if m}
    ko = cells((out / "food" / "index.html").read_text("utf-8"), pid)
    assert 'class="kf-na"' not in ko["closed"].group(2)
    for code in ("en", *NEW):
        c = cells((out / code / "food" / "index.html").read_text("utf-8"), pid)
        assert 'class="kf-na"' not in c["closed"].group(2), code
        assert bool(c["closed"].group(1)) == bool(ko["closed"].group(1)), code
        closed = re.sub(r"<[^>]+>", " ", c["closed"].group(2)).split()
        assert not any(w in re.sub(r"<[^>]+>", " ", c["hours"].group(2)).split() for w in closed if len(w) > 3), code


def test_validate_reports_a_closed_day_a_version_cannot_place(site):
    """validate.key_fact_problems: a version whose hours value lost its times (so the closed day cannot be found
    where the Korean parse finds it) is an error, not a silent 'not listed'."""
    from pipeline import en_site
    from pipeline.build import State
    from pipeline.validate import key_fact_problems
    S = State(site["data"], "production")
    ja = en_site.load_all(S, site["data"]).sites["ja"]
    p = ja.own(next(x for x in S.entities if x["id"] == PLACES[1]))
    assert key_fact_problems(ja, p) == []
    f = p["rec"]["facts"]["usetime_restdate"]
    f["value"] = re.sub(r"\d{1,2}:\d{2}", "", f["value"])
    problems = key_fact_problems(ja, p)
    assert problems and problems[0].startswith("쉬는 날: 한국어 첫 화면·목록에 있는데"), problems
# ------------------------------------------------------------------ QA 2026-10-15: call links, booking sites, dates
def _kf_tel(page: str) -> str:
    """The place opening's call tile (kf-tel) as markup."""
    i = page.index('class="kf-i kf-tel')
    return page[i:page.index("</div>", i)]


def _fact_row(page: str, key: str) -> str:
    i = page.index(f'<dd data-key="{key}">')
    return page[i:page.index("</dd>", i)]


def test_foreign_call_links_dial_plus82_and_show_the_form_on_place_pages(site):
    """SRC-05a: every version but Korean dials +82 and the number without its trunk 0 (a nationwide 15xx/16xx number
    keeps its digits); the place page shows the '+82 …' form under the call tile and after the contact row's value
    (that value stays whole); the Korean page keeps the domestic digits."""
    out = site["out"]
    for code in ("en", *NEW):
        for f in (out / code).rglob("*.html"):
            assert 'href="tel:0' not in f.read_text("utf-8"), (code, f)
    for t in re.findall(r'href="(tel:[^"]+)"', (out / "en" / "stays" / "index.html").read_text("utf-8")):
        assert re.fullmatch(r"tel:(\+82[1-9]\d{7,10}|1\d{7})", t), t
    slug = _slug(site, PLACES[2])    # 라마다 군산호텔, 063-441-8000
    for code in ("en", *NEW):
        page = (out / code / "places" / slug / "index.html").read_text("utf-8")
        tile = _kf_tel(page)
        assert 'href="tel:+82634418000"' in tile and '<span class="kf-sub tn">+82 63-441-8000</span>' in tile, code
        row = _fact_row(page, "infocenter")
        assert row.index(">063-441-8000</a>") < row.index('<span class="tel-intl tn"><span class="nw">+82 63-441-8000'), code
        assert 'href="tel:0634418000"' not in page
    assert 'href="tel:0634418000"' in _ko_page(site, PLACES[2]).read_text("utf-8")
    # list cells dial +82 but show no second number
    stays = (out / "en" / "stays" / "index.html").read_text("utf-8")
    assert 'href="tel:+82634418000"' in stays and "+82 63-441-8000" not in stays


def test_validator_catches_a_domestic_call_link_on_a_foreign_page(site, tmp_path):
    out = tmp_path / "dist"
    slug = _slug(site, PLACES[2])
    src = site["out"] / "ja" / "places" / slug / "index.html"
    dst = out / "ja" / "places" / slug / "index.html"
    dst.parent.mkdir(parents=True)
    dst.write_text(src.read_text("utf-8").replace("tel:+82634418000", "tel:0634418000"), "utf-8")
    errors, _, _ = validate(site["data"], out, "production")
    assert any("/ja/" in x and "국제 형식이 아닌 전화 링크" in x for x in errors), errors[:5]


def test_course_words_cover_every_version():
    """QA 2026-10-15 F09: the course pages' words (locales.COURSE_WORDS) exist for Korean and every version with the
    same keys, hand-written; a plural value has exactly the language's plural forms, a weekday tuple seven entries;
    no Korean script outside Korean."""
    assert set(LC.COURSE_WORDS) == {"ko", *LC.ORDER}
    keys = set(LC.COURSE_WORDS["ko"])
    for code, w in LC.COURSE_WORDS.items():
        assert set(w) == keys, (code, set(w) ^ keys)
        for k, v in w.items():
            if isinstance(v, dict):
                assert code != "ko" and set(v) == set(LC.get(code).plural), (code, k)
                vals = list(v.values())
            else:
                vals = list(v) if isinstance(v, tuple) else [v]
            assert all(str(x).strip() for x in vals), (code, k)
            if code != "ko":
                assert not HANGUL.search(" ".join(map(str, vals))), (code, k)
        assert all(len(w[k]) == 7 for k in ("closed_day", "wd_short")) and len(w["missing_items"]) == 2, code
        assert LC.course_word(code, "closed_n", 5, day=w["closed_day"][0])
        assert "{n}" in str(w["runs"]) and "{nos}" in w["routes_more"] and "{m}" in w["past_hour"], code
    assert LC.course_word("ru", "runs", 2) == "2 рейса" and LC.course_word("en", "hours_n", 12) == "12 hours"


def _course_page(site, code: str, cid: str) -> tuple[Path, str]:
    for f in (site["out"] / code / "courses").glob("*/index.html"):
        h = f.read_text("utf-8")
        if f'data-record="course:{cid}"' in h:
            return f, h
    raise AssertionError((code, cid))


def test_language_course_pages_have_the_closed_day_grid_and_the_move_block(site):
    """QA 2026-10-15 F09-a / F09 / F09-b / F09-c on the other versions: the Korean page's weekday grid of closed days
    (the same cells, the busiest day as the datarow note in the version's words and plural), the '차 없이 다니기'
    block with a Google Maps public-transport link per measured leg between the two stored coordinates, the bus-stop
    names in Korean only inside lang="ko", an unlinked stop's map search, the source's day / option headings and its
    one duration."""
    from pipeline.build import State
    S = State(site["data"], "production")
    a = next(v for v in S.course_vms.values() if v["c"]["id"] == COURSE)
    f, h = _course_page(site, "en", COURSE)   # en_min's English course
    assert '<table class="wk">' in h and 'id="h-week"' in h and 'href="#h-week"' in h
    days = dict(a["closed_by_day"])
    for i, d in enumerate("월화수목금토일"):
        if days.get(d):
            assert f'{LC.COURSE_WORDS["en"]["wd_short"][i]} <b class="tn">{days[d]}</b>' in h
    move = re.search(r'data-block="move">(.*?)</section>', h, re.S).group(1)
    links = re.findall(r'href="(https://www\.google\.com/maps/dir/\?[^"]+)"[^>]*data-provider="google_transit"', move)
    pairs = [(x, y) for x, y in a["pairs"] if x["next_m"] is not None and x["next_m"] >= 10]
    assert len(links) == len(pairs) == a["measured"]
    for x, y in pairs:
        assert html.escape(f"origin={x['geo']['lat']}%2C{x['geo']['lng']}&destination={y['geo']['lat']}%2C{y['geo']['lng']}"
                           "&travelmode=transit") in move
    assert "Not listed: travel time per leg" in move
    assert not scan_file(f).hangul
    # the fake-translated versions (one course each): the grid in their own weekday names, the note in their plural
    c = next(v for v in S.course_vms.values() if v["c"]["id"] == COURSE)
    day, cnt = max(c["closed_by_day"].items(), key=lambda kv: (kv[1], -"월화수목금토일".index(kv[0])))
    for code in ("ja", "ru"):
        _, p = _course_page(site, code, COURSE)
        w = LC.COURSE_WORDS[code]
        assert '<table class="wk">' in p and all(f'<th scope="col" class="wk-d">{d}</th>' in p for d in w["wd_short"])
        assert html.escape(LC.course_word(code, "closed_n", cnt, day=w["closed_day"]["월화수목금토일".index(day)])) in p
        assert w["move_h"] in p and 'data-provider="google_transit"' in p


def test_place_guide_and_course_pages_have_one_share_button_in_every_version(site):
    """Operator 2026-10-17 (공유하기 + GA4, as on the 군산 site): every version's place, guide and course pages hold
    one 공유 button in the local bar, naming the Korean record's id (GA4 item_id is the same in every language) with
    that version's words (locales.SHARE_WORDS, no Korean script)."""
    from markupsafe import escape
    btn = re.compile(r'<button type="button" class="lnav-share" data-share data-share-id="([^"]*)" data-copied="([^"]*)" '
                     r'data-failed="([^"]*)" data-js-only>.*?<span class="lnav-share-t">([^<]*)</span></button>', re.S)
    rec = re.compile(r'data-record="(?:place|guide|course):([^"]+)"')
    for code in ("en", *NEW):
        w = LC.SHARE_WORDS[code]
        assert not HANGUL.search(" ".join(w.values())), code
        seen = set()
        for kind in ("places", "guides", "courses"):
            for f in (site["out"] / code / kind).glob("*/index.html"):
                h = f.read_text("utf-8")
                found = btn.findall(h)
                assert len(found) == 1, (code, f)
                bid, copied, failed, label = found[0]
                assert (copied, failed, label) == (str(escape(w["copied"])), str(escape(w["failed"])), w["label"]), (code, f)
                m = rec.search(h)
                assert m is None or m.group(1) == bid, (code, f, bid)
                seen.add(kind)
        assert seen == {"places", "guides", "courses"}, (code, seen)



@pytest.mark.parametrize("code", NEW)
def test_home_h1_is_the_sites_own_sentence_in_the_version(site, code):
    """The other versions' home opening reads like the Korean one ('대구 여행의 모든 것'): the version's own sentence with
    the city's name (Locale.home_h1), not the bare site name."""
    loc = LC.get(code)
    nm = LC.names(json.loads((site["data"] / "site.json").read_text("utf-8")), code)
    h1 = scan_file(site["out"] / code / "index.html").h1
    assert nm["city"] and h1 == loc.home_h1.replace("{city}", nm["city"]) and h1 != nm["site_name"]
