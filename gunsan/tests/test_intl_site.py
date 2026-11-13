"""The seven language versions (/ja/ /zh-hans/ /zh-hant/ /de/ /fr/ /es/ /ru/, pipeline/en_site.py + pipeline/locales.py).

Built in production from a copy of data/gunsan with tiny fake translations written into tmp folders here (never into
data/gunsan): four places (one with two-source values and a designation, a restaurant, a stay, one below the index
rule), one more place whose record is stale (its ko_hash is not the current Korean's), the food hub guide, a course
and an event series with two-source values, and complete strings (labels from the Korean, the pages' own words from
pipeline/intl_text.py) — the records written exactly the way tools/en_content.py merge writes them. A second, small
build of the sample data (no English) has Japanese only, plus Spanish with incomplete strings (not built)."""
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from markupsafe import escape as esc

from pipeline import intl_text, present
from pipeline import locales as LC
from pipeline.build import build
from pipeline.en_source import (Glossary, _name_table, column_item, course_item, current_hashes, event_item,
                                event_series, guide_item, place_item, romanize)
from pipeline.validate import hreflang_problems, scan_file, validate
from conftest import without_one_value_prose
from tools.en_content import PLACEHOLDER, strings_items


@pytest.fixture(scope="module", autouse=True)
def _engine_both_values(engine_both_values):
    """This module checks the engine's both-values display on 군산각's data (tests/conftest.py)."""

ROOT = Path(__file__).resolve().parent.parent
GUNSAN, SAMPLE = ROOT / "data" / "gunsan", ROOT / "data" / "sample"
NEW = ("ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
PLACES = ("gunsan-305395", "gunsan-306687", "gunsan-307033", "gunsan-305362")   # conflict · food+designation · stay · noindex
# a dated notice of the facility (pipeline/notices.py) on PLACES[0], written into the copy: one still current, one ended
NOTICES = [{"id": "test-current", "place_ids": [PLACES[0]], "kind": "hours", "start": "2099-10-09", "end": "2099-10-11",
            "from": "18:00", "to": "22:00", "last_entry": "21:40", "provider": "군산근대역사박물관 홈페이지",
            "url": "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9999", "checked_at": "2026-10-15",
            "until": "2099-10-11"},
           {"id": "test-ended", "place_ids": [PLACES[0]], "kind": "closed", "date": "2000-01-03",
            "provider": "군산근대역사박물관 홈페이지", "url": "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9998",
            "checked_at": "1999-12-30", "until": "2000-01-03"}]
STALE = "gunsan-305373"
GUIDE, COURSE, SERIES = "guide-13", "gunsan-course-m2135-2", "군산-수제맥주블루스-페스티벌"
# columns (data/<code>/columns.json, en_source.column_item): two current in English and in every version (the first
# names PLACES[0] and quotes the foreign press; the second names the STALE place, which has no page in the versions),
# one current in English but stale in the versions, one in the versions only (no English record: its id is its slug)
COLUMNS = ("column-global-eyes-on-gunsan", "column-sinheungdong-wolsan-slope")
COL_STALE, COL_NO_EN = "column-haemangno-modern-architecture", "column-rainy-day-indoor-route"
EN_COLUMNS = {COLUMNS[0]: ("Gunsan through foreign eyes: five scenes the foreign press noticed", "Global views"),
              COLUMNS[1]: ("Roofs at 75 degrees and hillside alleys: time in Sinheung-dong", "History and architecture"),
              COL_STALE: ("A port remembered in red brick and granite: a walk along Haemang-ro", "History and architecture")}
WORD = {"ja": "情報", "zh-hans": "信息", "zh-hant": "資訊", "de": "Angabe", "fr": "Donnée", "es": "Dato", "ru": "Сведения"}
NAME = {"ja": "スポット", "zh-hans": "景点", "zh-hant": "景點", "de": "Ort", "fr": "Lieu", "es": "Lugar", "ru": "Место"}
PROSE = {"ja": "これは{n}番目の場所です。駐車場があります。",
         "zh-hans": "这是第{n}个地点。这里有停车场。",
         "zh-hant": "這是第{n}個地點。這裡有停車場。",
         "de": "Das ist der Ort Nummer {n}. Es gibt einen Parkplatz und die Halle ist für alle offen.",
         "fr": "C'est le lieu numéro {n}. Il y a un parking et la salle est ouverte pour tous.",
         "es": "Es el lugar número {n}. Hay un aparcamiento y la sala está abierta para todos.",
         "ru": "Это место номер {n}. Здесь есть парковка, и зал открыт для всех."}
QUESTION = {"ja": "{n}番目の質問ですか？", "zh-hans": "这是第{n}个问题吗？", "zh-hant": "這是第{n}個問題嗎？",
            "de": "Ist das die Frage {n}?", "fr": "Est-ce la question {n} ?", "es": "¿Es la pregunta {n}?",
            "ru": "Это вопрос {n}?"}
HANGUL = re.compile(r"[가-힣]")


def fake(code: str, text: str) -> str:
    """A value in the language: its words replaced, digits, times, phones and punctuation kept."""
    t = HANGUL.sub("", re.sub(r"[가-힣A-Za-z][가-힣A-Za-z'’]*", WORD[code], str(text or "")))
    return re.sub(r"\s+", " ", t).strip() or WORD[code]


def column_record(code: str, it: dict, n: int, ko_hash: str, name: str = "") -> dict:
    """A column's record in one version (en_source.column_item's fields), as en_content merge writes it; `name` (a
    place's name in the version) opens the first section's second paragraph."""
    loc = LC.get(code)
    colon, sp = ("：", "") if loc.cjk else (": ", " ")
    para = lambda k: PROSE[code].format(n=k)   # noqa: E731
    return {"slug": it["slug"], "category": f"{WORD[code]}{n}", "label": f"{WORD[code]}{n}",
            "title": f"{NAME[code]}{n}{colon}{WORD[code]}", "dek": para(8), "summary": para(1), "pull_quote": para(9),
            "body": [{"heading": f"{WORD[code]}{k}", "paras": [para(k), f"{name}{sp}{para(k + 1)}" if k == 1 and name
                                                               else para(k + 1)]} for k, _ in enumerate(it["body"], 1)],
            "items": [{"place_slug": x["place_slug"], "reason": para(k)} for k, x in enumerate(it["items"], 1)],
            "sources": [{"name": WORD[code], "url": s["url"]} for s in it["sources"]],
            "ko_hash": ko_hash, "translated_at": "2026-10-25"}


def write_translations(data: Path, codes, stale: str | None = STALE, places=PLACES, guide=GUIDE, course=COURSE,
                       series=SERIES, strings_ok: bool = True, columns=(*COLUMNS, COL_STALE, COL_NO_EN),
                       col_stale: str | None = COL_STALE) -> None:
    """data/<code>/{places,guides,courses,events,columns,strings}.json for each code, shaped as en_content merge writes
    them."""
    pl = [p for p in json.loads((data / "places.json").read_text("utf-8"))
          if p.get("status") == "published" and not p.get("duplicate_of")]
    by_id, by_slug = {p["id"]: p for p in pl}, {p["slug"]: p for p in pl}
    names_en = _name_table(data, pl)
    hashes = current_hashes(data)
    gl = Glossary(pl, names_en, [])
    labels = [r for r in strings_items(data, pl) if not r["id"].startswith("ui:")]
    for code in codes:
        loc = LC.get(code)
        d = data / code
        d.mkdir()
        recs = {}
        for i, pid in enumerate([*places, *([stale] if stale else [])], 1):
            item = place_item(by_id[pid], names_en[pid], gl, True)
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
            it = event_item(sr, None)
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
        cols = {}   # the data's own columns only (the sample has none)
        all_cols = {c["id"]: c for c in json.loads((data / "columns.json").read_text("utf-8"))} \
            if columns and (data / "columns.json").exists() else {}
        for n, cid in enumerate([c for c in columns or () if c in all_cols], 1):
            it = column_item(all_cols[cid], by_slug, names_en, None)
            cols[cid] = column_record(code, it, n, "0" * 16 if cid == col_stale else hashes["columns"][cid],
                                      f"{NAME[code]}1" if places else "")
        strings = {r["id"]: {"ko": r["ko"], loc.tag: f"{WORD[code]}{k}"} for k, r in enumerate(labels, 1)}
        keys = intl_text.keys_for(loc)
        for key in keys[: None if strings_ok else len(keys) // 2]:
            src = intl_text.source_for(key)
            strings[f"chrome.{key}"] = {"en": src, loc.tag: " ".join([WORD[code], *PLACEHOLDER.findall(src)])}
        for name, store in (("places", recs), ("guides", guides), ("courses", courses), ("events", events),
                            ("columns", cols), ("strings", strings)):
            (d / f"{name}.json").write_text(json.dumps(store, ensure_ascii=False, indent=1), "utf-8")


def write_en_columns(data: Path) -> None:
    """data/en/columns.json in the copy: EN_COLUMNS, current (English is the copy's real data otherwise)."""
    pl = [p for p in json.loads((data / "places.json").read_text("utf-8"))
          if p.get("status") == "published" and not p.get("duplicate_of")]
    by_slug, names_en, hashes = {p["slug"]: p for p in pl}, _name_table(data, pl), current_hashes(data)
    name = json.loads((data / "en" / "places.json").read_text("utf-8"))[PLACES[0]]["name_en"]
    cols = {c["id"]: c for c in json.loads((data / "columns.json").read_text("utf-8"))}
    recs = {}
    for cid, (title, category) in EN_COLUMNS.items():
        it = column_item(cols[cid], by_slug, names_en, None)
        recs[cid] = {"slug": it["slug"], "category": category, "label": title.split(": ")[1].capitalize(),
                     "title": title, "dek": "Where the column goes, in one line.",
                     "summary": "Five scenes keep coming back in what foreign writers say about the city. This column "
                                "walks through them one by one.",
                     "pull_quote": "The old port still sets the pace of a walk here.",
                     "body": [{"heading": f"Part {k}",
                               "paras": [f"Walk {k} starts by the water.",
                                         f"{name} is the next stop on this walk." if k == 1 else "Then the walk turns inland."]}
                              for k, _ in enumerate(it["body"], 1)],
                     "items": [{"place_slug": x["place_slug"], "reason": f"Reason number {k}."}
                               for k, x in enumerate(it["items"], 1)],
                     "sources": [{"name": "Source", "url": s["url"]} for s in it["sources"]],
                     "ko_hash": hashes["columns"][cid], "translated_at": "2026-10-25"}
    (data / "en" / "columns.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), "utf-8")
    # these English columns are the test's own: their slugs come from these titles, not from the slugs the real
    # columns were published under (en/slugs.json, en_site.published_slugs)
    pins = json.loads((data / "en" / "slugs.json").read_text("utf-8")) if (data / "en" / "slugs.json").exists() else {}
    pins["columns"] = {}
    (data / "en" / "slugs.json").write_text(json.dumps(pins, ensure_ascii=False), "utf-8")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("intl")
    data = tmp / "data"
    # the real data/gunsan/<code>/ folders (official TourAPI names so far) give way to this test's own translations
    shutil.copytree(GUNSAN, data, ignore=lambda d, names: [n for n in names if n == "cache" or
                                                           (Path(d) == GUNSAN and n in NEW)])
    write_translations(data, NEW)
    write_en_columns(data)
    (data / "notices.json").write_text(json.dumps(NOTICES, ensure_ascii=False), "utf-8")
    # this test's versions translate a few records and keep a stale one on purpose: the completeness rule (site.json
    # intl.require_complete; test_complete_policy_stops_the_build_and_validate_on_a_missing_translation) would stop
    # this build, so this copy turns it off
    s = json.loads((data / "site.json").read_text("utf-8"))
    s["intl"] = {"require_complete": False}
    (data / "site.json").write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    out = tmp / "dist"
    stats = build(data, out, "production")
    en = json.loads((data / "en" / "places.json").read_text("utf-8"))
    by_h1: dict[str, list[str]] = {}   # the English place pages by their H1 (name_en)
    for f in (out / "en" / "places").glob("*/index.html"):
        h1 = re.search(r'<h1 class="d1 vt-title">(.*?)</h1>', f.read_text("utf-8"), re.S)
        if h1:
            by_h1.setdefault(html.unescape(h1.group(1)), []).append(f.parent.name)
    return {"data": data, "out": out, "stats": stats, "en": en, "by_h1": by_h1}


def _slug(site, pid: str) -> str:
    """The English page slug of a place (every version uses it)."""
    hits = site["by_h1"].get(site["en"][pid]["name_en"], [])
    assert len(hits) == 1, (pid, hits)
    return hits[0]


def _ko_page(site, pid: str) -> Path:
    slug = next(p["slug"] for p in json.loads((site["data"] / "places.json").read_text("utf-8")) if p["id"] == pid)
    return site["out"] / "places" / slug / "index.html"


@pytest.mark.parametrize("code", NEW)
def test_routes_lang_and_names(site, code):
    out, loc = site["out"], LC.get(code)
    st = site["stats"]["intl"][code]
    assert st["places"] == len(PLACES) and st["guides"] == 1 and st["courses"] == 1 and st["event_series"] == 1
    assert st["columns"] == len(COLUMNS) + 1
    assert st["stale_skipped"] == {"places": 1, "guides": 0, "courses": 0, "events": 0, "columns": 1}
    for path in ("index.html", "places/index.html", "food/index.html", "stays/index.html", "guides/index.html",
                 "courses/index.html", "events/index.html", "about/index.html"):
        assert (out / code / path).exists(), (code, path)
    for i, pid in enumerate(PLACES, 1):
        f = out / code / "places" / _slug(site, pid) / "index.html"     # the English slug of the same record
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
    for c in NEW:   # gunsan-305373 is an attraction: the version's 'Things to do' list (its label is WORD here)
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
    ko_slug = next(g["slug"] for g in guides if g["id"] == "guide-01")   # English has it, the fixture's versions not
    items = _menu_items(out / "guides" / ko_slug / "index.html")
    assert items["en"][0].startswith("/en/guides/") and items["en"][0] != "/en/guides/" and not items["en"][1]
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
    of at all (this fixture's versions translate only a few; English, the real data, all)."""
    hashes = current_hashes(site["data"])
    assert site["stats"]["en"]["untranslated"] == {"places": 0, "guides": 0, "courses": 0, "events": 0,
                                                   "columns": len(hashes["columns"]) - len(EN_COLUMNS)}
    for c in NEW:
        st = site["stats"]["intl"][c]
        built = {"places": st["places"], "guides": st["guides"], "courses": st["courses"], "events": st["event_series"],
                 "columns": st["columns"]}
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


# ------------------------------------------------------------------ columns (2026-10-25: the Korean columns abroad)
def _col_slug(site, cid: str) -> str:
    """The English slug of a column (every version uses it): the English title before its colon, else its id."""
    from pipeline.en_site import en_slug
    return en_slug(EN_COLUMNS[cid][0].split(": ")[0]) if cid in EN_COLUMNS else cid


def _ko_column(site, cid: str) -> Path:
    slug = next(c["slug"] for c in json.loads((site["data"] / "columns.json").read_text("utf-8")) if c["id"] == cid)
    return site["out"] / "columns" / slug / "index.html"


def test_column_pages_and_lists_in_every_version(site):
    """Each version builds a page for every column whose record is current, at <home>columns/<English slug>/ (a
    column English lacks: its id), and its list <home>columns/; a stale record has no page; the bar links the list."""
    out = site["out"]
    assert site["stats"]["en"]["columns"] == len(EN_COLUMNS)
    assert _col_slug(site, COLUMNS[0]) == "gunsan-through-foreign-eyes"
    for code in ("en", *NEW):
        loc = LC.get(code)
        have = [*COLUMNS, COL_STALE] if code == "en" else [*COLUMNS, COL_NO_EN]
        for cid in have:
            f = out / code / "columns" / _col_slug(site, cid) / "index.html"
            p = scan_file(f)
            assert p.html_lang == loc.html and p.hangul == [], (code, cid, p.hangul[:3])
            assert f'data-record="column:{cid}"' in f.read_text("utf-8")
            assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", f.parent.name)
        gone = COL_NO_EN if code == "en" else COL_STALE
        assert not (out / code / "columns" / _col_slug(site, gone)).exists(), (code, gone)
        index = (out / code / "columns" / "index.html").read_text("utf-8")
        for cid in have:
            assert f'href="/{code}/columns/{_col_slug(site, cid)}/"' in index, (code, cid)
        assert f'href="/{code}/columns/{_col_slug(site, gone)}/"' not in index
        home = (out / code / "index.html").read_text("utf-8")
        bar = re.search(r'<nav class="side-nav".*?</nav>', home, re.S).group(0)   # the tab panel's main menu
        assert f'href="/{code}/columns/"' in bar
        assert 'class="sec sec-cols' in home and f'href="/{code}/columns/{_col_slug(site, COLUMNS[0])}/"' in home


@pytest.mark.parametrize("code", ("en", "ja", "de", "ru"))
def test_a_column_page_is_the_korean_column_in_the_version(site, code):
    """The Korean column's parts in the version's words: head (the list, category, label, reading time), H1, dek, the
    answer card, the sections with their paragraphs whole and the version's place page linked from the text, the
    section quote the Korean record gives — in its own language with its source, never translated — the pull quote,
    the place list (a place without a page here: its name and the Korean name, no link), sources, related columns."""
    out, loc = site["out"], LC.get(code)
    col = next(c for c in json.loads((site["data"] / "columns.json").read_text("utf-8")) if c["id"] == COLUMNS[0])
    rec = json.loads((site["data"] / code / "columns.json").read_text("utf-8"))[COLUMNS[0]]
    page = (out / code / "columns" / _col_slug(site, COLUMNS[0]) / "index.html").read_text("utf-8")
    p = scan_file(out / code / "columns" / _col_slug(site, COLUMNS[0]) / "index.html")
    assert p.h1 == rec["title"] and rec["dek"] in p.body and rec["category"] in p.body and rec["label"] in p.body
    assert f'<a href="/{code}/columns/">' in page
    n = col["reading_minutes"]
    assert (intl_text.EN["min_read"]["other"].format(n=n) if code == "en" else f"{WORD[code]} {n}") in p.body
    assert squash(rec["summary"]) in squash(p.blocks["summary"])
    for b in rec["body"]:   # each paragraph whole (figures and names marked up inside it)
        assert b["heading"] in p.body and all(squash(x) in squash(p.body) for x in b["paras"])
    place = f"/{code}/places/{_slug(site, PLACES[0])}/"
    first = page[page.index('id="h-b1"'):page.index('id="h-b2"')]
    assert f'<a class="gl" href="{place}"' in first      # the paragraph's mention of the place, linked here
    quotes = [b["quote"] for b in col["body"] if b.get("quote")]
    assert quotes
    for q in quotes:
        assert re.search(rf'<blockquote class="col-fquote" lang="{q["lang"]}" cite="{re.escape(str(esc(q["url"])))}">\s*'
                         rf'<p>{re.escape(str(esc(q["text"])))}</p>', page), q
        assert f'<a href="{esc(q["url"])}" rel="noopener" data-track="abroad_click">{esc(q["source"])}</a>' in page
    assert esc(rec["pull_quote"]) in page
    items = page[page.index('id="h-items"'):page.index('id="h-src"')]
    assert items.count('<li class="gitem">') == len(col["items"]) and f'href="{place}"' in items
    for s_ in rec["sources"]:
        assert html.escape(s_["url"]) in page
    rel = page[page.index('id="h-related"'):]
    others = [c for c in ([*COLUMNS, COL_STALE] if code == "en" else [*COLUMNS, COL_NO_EN]) if c != COLUMNS[0]]
    assert all(f'href="/{code}/columns/{_col_slug(site, c)}/"' in rel for c in others)
    # the second column names the stale place: no page in the versions, so its name with the Korean one, no link
    page2 = (out / code / "columns" / _col_slug(site, COLUMNS[1]) / "index.html").read_text("utf-8")
    ko_name = next(x["name"] for x in json.loads((site["data"] / "places.json").read_text("utf-8")) if x["id"] == STALE)
    if code != "en":
        name = LC.kontsevich(ko_name) if code == "ru" else romanize(ko_name)
        assert f'<b>{html.escape(name)}</b> <span lang="ko">{ko_name}</span>' in page2


def squash(text: str) -> str:
    return re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", text or "")))


def test_column_hreflang_language_menu_sitemap_llms_and_search(site):
    """A Korean column and each version's page of it are hreflang twins (only the versions with a current record), as
    are /columns/ and every <home>columns/; the language menu of a Korean column a version lacks links that version's
    column list, saying it is not translated; the pages are in sitemap.xml (indexed like the versions' guides), every
    version's llms.txt section names its column list, and its search finds the columns."""
    out = site["out"]
    ko = scan_file(_ko_column(site, COLUMNS[0]))
    assert [h for h, _ in ko.alternates] == ["ko", "en", "ja", "zh-Hans", "zh-Hant", "de", "fr", "es", "ru", "x-default"]
    assert dict(ko.alternates)["ja"].endswith(f"/ja/columns/{_col_slug(site, COLUMNS[0])}/")
    assert dict(scan_file(out / "ja" / "columns" / _col_slug(site, COLUMNS[0]) / "index.html").alternates) == dict(ko.alternates)
    assert [h for h, _ in scan_file(_ko_column(site, COL_STALE)).alternates] == ["ko", "en", "x-default"]
    assert [h for h, _ in scan_file(_ko_column(site, COL_NO_EN)).alternates] == \
        ["ko", "ja", "zh-Hans", "zh-Hant", "de", "fr", "es", "ru", "x-default"]
    idx = dict(scan_file(out / "columns" / "index.html").alternates)
    assert all(idx[LC.get(c).html].endswith(f"/{c}/columns/") for c in ("en", *NEW))
    items = _menu_items(_ko_column(site, COL_STALE))
    assert items["en"][0] == f"/en/columns/{_col_slug(site, COL_STALE)}/" and not items["en"][1]
    for c in NEW:
        assert items[LC.get(c).html] == (f"/{c}/columns/", html.escape(f"{WORD[c]} · {LC.get(c).untranslated}")), c
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = {unquote(urlsplit(el.text).path) for el in ET.parse(out / "sitemap.xml").getroot().iter(f"{ns}loc")}
    llms = (out / "llms.txt").read_text("utf-8")
    for code in ("en", *NEW):
        assert f"/{code}/columns/" in locs and f"/{code}/columns/{_col_slug(site, COLUMNS[0])}/" in locs
        assert f"/{code}/columns/{_col_slug(site, COL_STALE if code != 'en' else COL_NO_EN)}/" not in locs
        assert f"/{code}/columns/)" in llms
        rows = json.loads((out / code / "search" / "index.json").read_text("utf-8"))
        cols = [r for r in rows if r["k"] == "column"]
        assert len(cols) == (site["stats"]["en"] if code == "en" else site["stats"]["intl"][code])["columns"]
        assert any(r["p"] == f"/{code}/columns/{_col_slug(site, COLUMNS[0])}/" for r in cols)
    ja = next(r for r in json.loads((out / "ja" / "search" / "index.json").read_text("utf-8"))
              if r["k"] == "column" and r["p"].endswith(f"/{_col_slug(site, COLUMNS[0])}/"))
    ko_title = next(c["title"] for c in json.loads((site["data"] / "columns.json").read_text("utf-8")) if c["id"] == COLUMNS[0])
    assert ko_title in ja["o"] and EN_COLUMNS[COLUMNS[0]][0] in ja["o"]   # a Korean or English title finds it too


def test_validator_catches_a_translated_or_missing_column_quote(site, tmp_path):
    """A column's section quote stays the Korean record's, in its own language: a page that changed it is an error."""
    out = tmp_path / "dist"
    col = next(c for c in json.loads((site["data"] / "columns.json").read_text("utf-8")) if c["id"] == COLUMNS[0])
    q = next(b["quote"] for b in col["body"] if b.get("quote"))
    src = site["out"] / "de" / "columns" / _col_slug(site, COLUMNS[0]) / "index.html"
    dst = out / "de" / "columns" / _col_slug(site, COLUMNS[0]) / "index.html"
    dst.parent.mkdir(parents=True)
    dst.write_text(src.read_text("utf-8").replace(html.escape(q["text"]), "Eine Übersetzung des Zitats."), "utf-8")
    errors, _, _ = validate(site["data"], out, "production")
    assert any("/de/columns/" in x and "칼럼 인용문이 원문 언어 그대로" in x for x in errors), errors[:5]


def test_production_validate_passes(site):
    errors, warnings, stats = validate(site["data"], site["out"], "production")
    errors = without_one_value_prose(errors)   # tests/conftest.py
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
    """No data/<region>/<code>: no pages, no hreflang, no menu item. Incomplete UI words: not built (a warning).
    Without English, the slugs are what English would give (romanized). A version that lacks translations of
    published records gets a build warning with the count (QA 2026-10-15 SRC-03a)."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))   # the sample's contact is a Korean placeholder
    site["operator"]["contact"] = "corrections@test.invalid"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    pid = json.loads((data / "places.json").read_text("utf-8"))[0]["id"]
    write_translations(data, ["ja"], stale=None, places=(pid,), guide=None, course=None, series=None, columns=())
    write_translations(data, ["es"], stale=None, places=(pid,), guide=None, course=None, series=None, strings_ok=False,
                       columns=())
    out = tmp_path / "dist"
    capsys.readouterr()
    stats = build(data, out, "sample")
    assert stats["intl"]["ja"]["places"] == 1 and stats["intl_skipped"]["es"] > 0 and "en" not in stats
    untranslated = stats["intl"]["ja"]["untranslated"]
    published = sum(1 for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("status") == "published")
    assert untranslated["places"] == published - 1 > 0
    assert f"경고: ja 번역이 없는 공개 항목 {sum(untranslated.values())}건" in capsys.readouterr().err
    assert (out / "ja").exists() and not (out / "es").exists() and not (out / "en").exists()
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert 'hreflang="es"' not in html and 'hreflang="en"' not in html and 'lang="es"' not in html, f
    ko = next(f for f in (out / "places").glob("*/index.html"))
    menu = re.findall(r'class="mast-lang" href="([^"]*)" hreflang="([^"]*)"', ko.read_text("utf-8"))
    assert [h for _, h in menu] == ["ko", "ja"]
    slug = next(p.parent.name for p in (out / "ja" / "places").glob("*/index.html"))
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug)
    # no column in the version: no column pages and no 'Columns' in its bar
    assert not (out / "ja" / "columns").exists() and 'href="/ja/columns/"' not in (out / "ja" / "index.html").read_text("utf-8")
    errors, warnings, _ = validate(data, out, "sample")
    assert errors == [], errors[:5]
    assert any("/es/" in w and "chrome" in w for w in warnings)


def test_complete_policy_stops_the_build_and_validate_on_a_missing_translation(tmp_path, capsys):
    """site.json intl.require_complete (translation tables, 2026-11-01 port; off unless set): a required version
    without the translation of a published record stops the build and names what is missing — the record is not left
    out, its name not filled by sound; `languages` names the versions required (one with no data/<code> is listed);
    validate gives the same as errors. Without the switch the same data builds (test above)."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["operator"]["contact"] = "corrections@test.invalid"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    pid = json.loads((data / "places.json").read_text("utf-8"))[0]["id"]
    write_translations(data, ["ja"], stale=None, places=(pid,), guide=None, course=None, series=None, columns=())
    out = tmp_path / "dist"
    build(data, out, "sample")   # the switch off: the version is built with its one record
    site.update(languages=["ko", "ja", "de"], intl={"require_complete": True})
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    errors, _, _ = validate(data, out, "sample")
    assert any("외국어 판 번역 모자람: ja: 번역이 없는 places" in e for e in errors), errors[:5]
    assert any("외국어 판 번역 모자람: de: 판을 만들지 못함" in e for e in errors), errors[:5]
    assert any("현재 한국어의 번역이 없거나 낡음: places/" in e for e in errors), errors[:5]
    capsys.readouterr()
    with pytest.raises(SystemExit, match="외국어 판 번역이 모자라"):
        build(data, tmp_path / "dist2", "sample")
    err = capsys.readouterr().err
    assert "오류: ja: 번역이 없는 places" in err and "오류: de: 판을 만들지 못함" in err


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


def test_every_about_page_explains_the_assistant_in_its_own_language(site):
    """The site assistant's section (/<code>/about/#chatbot) was the English text on all seven non-English versions until
    2026-10-24 (the ask cards linked there as '(in English)'): now each version says it in its own words — the
    launcher's own label, the 12 messages sent with a question (chatbot/server.js LIMITS.messages 13), the model — and
    no English sentence is left in it."""
    import re as _re
    labels = {"en": "AI chat", "ja": "AIチャット", "zh-hans": "AI助手", "zh-hant": "AI助手", "de": "KI-Chat", "fr": "Chat IA",
              "es": "Chat IA", "ru": "ИИ-чат"}
    for code, label in labels.items():
        page = (site["out"] / code / "about" / "index.html").read_text("utf-8")
        sec = page[page.index('id="chatbot"'):]
        sec = sec[:sec.index("</section>")]
        assert label in sec and "12" in sec and "Claude Haiku 5.5" in sec and "Anthropic" in sec, code
        assert "‘Ask’" not in sec, code                                       # the launcher is not called 'Ask'
        if code != "en":
            body = sec.split("</h2>", 1)[1]
            assert not _re.search(r"\b(?:the|which|this site|answers only|button)\b", body), code   # no English left

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
    assert 'data-search data-index="/en/search/index.json" data-words="' in page and "Search Gunsan" in page
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
    assert diet.search("채식 메뉴") and not diet.search("철새의 핵심 채식지")   # 채식지: a feeding ground, not a diet
    assert diet.search("비건 빵") and not diet.search("장비건어물")   # 장비건어물: a dried-fish shop (장비 + 건어물)
    files = [*out.glob("**/search/index.json"), out / "chat" / "docs.json"]
    assert len(files) == 10
    for f in files:
        hit = diet.search(f.read_text("utf-8"))
        assert not hit, (f, hit and hit.group(0))


def test_every_version_says_what_its_search_covers_and_reads_the_query_words(site):
    """Evaluation 2026-10-18: under each version's search box one line in its language says what the search finds and
    that travel questions go to the AI chat (named as on the chat's launcher; the input's description). The form
    carries the query words (present.SEARCH_CONCEPTS: the rows here carry the Korean names, so a Korean query finds
    here as on /search/), the city in Korean and in this version (a word that only names it is no condition), and the
    words search.js prints for them ('관련 가이드', '함께 찾은 말') in this language; no planner (/plan/ is Korean only)."""
    out = site["out"]
    chat = {"en": "AI chat", "ja": "AIチャット", "zh-hans": "AI助手", "zh-hant": "AI助手", "de": "KI-Chat",
            "fr": "chat IA", "es": "chat IA", "ru": "ИИ-чат"}
    for code in ("en", *NEW):
        page = (out / code / "search" / "index.html").read_text("utf-8")
        note = re.search(r'<p class="search-note" id="q-note">([^<]+)</p>', page)
        assert note and html.unescape(note.group(1)) == LC.SEARCH_WORDS[code]["scope"], code
        assert chat[code] in note.group(1) and not HANGUL.search(note.group(1)), code
        assert 'aria-describedby="q-note"' in page, code
        form = re.search(r'<form class="search"[^>]*>', page).group(0)
        attrs = {k: html.unescape(v) for k, v in re.findall(r' data-([a-z-]+)="([^"]*)"', form)}
        assert json.loads(attrs["concepts"]) == present.SEARCH_CONCEPTS and "planner" not in attrs, code
        assert attrs["region"] == f"군산 {LC.get(code).city}", code
        w = _search_words(page)
        assert w["related"] and w["syn"] and not HANGUL.search(w["related"] + w["syn"]), code


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
    roman, korean = _found(en_rows, "Seonyudo"), _found(en_rows, "선유도")
    assert {r["p"] for r in roman} <= {r["p"] for r in korean}
    assert {"course", "guide", "event"} <= {r["k"] for r in korean}
    ko_rows = json.loads((out / "search" / "index.json").read_text("utf-8"))
    ko_name = {p["id"]: p["name"] for p in json.loads((site["data"] / "places.json").read_text("utf-8"))}
    ja_rows = json.loads((out / "ja" / "search" / "index.json").read_text("utf-8"))
    for pid in PLACES:
        name_en = site["en"][pid]["name_en"]
        row = next(r for r in ko_rows if r["n"] == ko_name[pid] and r["k"] in ("attraction", "food", "stay"))
        assert name_en in (row.get("o") or "").split(" · "), (pid, row)
        row = next(r for r in ja_rows if r["a"] == ko_name[pid])   # the Korean name finds it, the English one too
        assert name_en in (row.get("o") or "").split(" · "), (pid, row)
    assert {"attraction", "course", "guide", "event"} <= {r["k"] for r in _found(ko_rows, "Seonyudo")}
    assert {r["p"] for r in _found(ko_rows, "Seon-yu-do")} == {r["p"] for r in _found(ko_rows, "Seonyudo")}
    assert not any(r.get("o") == r["n"] for r in ko_rows + en_rows + ja_rows)


def test_every_language_place_page_has_the_nearby_chapter_markup(site):
    """The 주변·함께 가기 chapter (templates/_near.html.j2, locales.NEAR_WORDS) in the versions: the English place pages
    (real translations) carry the course segments (each course chip to its stop, #s<n>), the nearby rows on one
    straight-line scale and the guide cards, in English only; the other versions' chapters have no Hangul and the
    words of their own NEAR_WORDS."""
    out = site["out"]
    page = next(f for f in (out / "en" / "places").glob("*/index.html") if 'href="/places/동국사/"' in f.read_text("utf-8"))
    h = page.read_text("utf-8")
    b = h[h.index('data-block="nearby"'):h.index("</section>", h.index('data-block="nearby"'))]
    assert b.count('class="nb-seg"') == b.count('aria-current="location"') == 6
    chips = re.findall(r'<a class="crs" href="(/en/courses/[^"#]+/#s\d+)" data-track="course_click"', b)
    assert len(chips) == 8 and len(set(chips)) == 8
    assert 'class="nr-list"' in b and 'class="xc-list"' in b and "Full bar = straight-line 250 m" in b
    assert "straight-line 910 m" in b and not HANGUL.search(b)
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
        # the zero-result panel's buttons (a chip's label in {v}) and the map caption's places off the map ({n})
        assert "{v}" in w["clear_one"] and "{n}" in w["off_map"] and "{" not in w["clear_all"], code
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
    Korean ones), every row its filter keys, the condition chips (조건으로 찾기, in the check box's place since
    2026-10-31) with their labels from locales.COND_WORDS and the number of rows that meet each; the '지도 n' count of the list | map switch is the rows with coordinates (data-geo), which
    are exactly the map's points."""
    from markupsafe import escape
    out, loc, w = site["out"], LC.get(code), LC.LIST_WORDS[code]
    strings = json.loads((site["data"] / code / "strings.json").read_text("utf-8"))
    for seg, kind in (("places", "attraction"), ("food", "food"), ("stays", "stay")):
        h = (out / code / seg / "index.html").read_text("utf-8")
        bar = _bar(h)
        rows = re.findall(r'<li class="rec"[^>]*>', h)
        assert rows and all('data-region="' in r for r in rows), (code, seg)
        # 조건으로 찾기 (pipeline/conditions.py) took the check box's place: the condition chips in this version's words
        # (locales.COND_WORDS), each counting the rows that meet it (data-conds)
        assert 'data-f="check"' not in bar, (code, seg)
        conds = re.findall(r'<button type="button" data-cond="(\w+)" aria-pressed="false"><span class="c-ck" '
                           r'aria-hidden="true"></span>([^<]*?) <span class="tn">(\d+)</span></button>', bar)
        assert conds, (code, seg)
        for cid, lab, n in conds:
            words = LC.COND_WORDS[code]["labels"]
            assert html.unescape(lab) == words.get(f"{cid}_{kind}", words[cid]), (code, seg, cid)
            assert int(n) == sum(1 for r in rows if cid in (re.search(r'data-conds="([^"]*)"', r) or [None, ""])[1].split())
        if bar.count('data-f="type"') > 1:
            assert f'role="group" aria-label="{w["type"]}"' in bar, (code, seg)
        geo = sorted(re.search(r'id="(r\d+)"', r).group(1) for r in rows if 'data-geo="1"' in r)
        pts = re.search(r"data-points='([^']*)'", h)
        if pts:
            ids = sorted(p["id"] for p in json.loads(html.unescape(pts.group(1)))["list"])
            assert geo == ids, (code, seg)
            assert f'role="group" aria-label="{w["view"]}"' in bar and f'{w["map"]} <span class="tn">{len(ids)}</span>' in bar
            assert re.search(r'<span (?:class="muted" )?data-geo-cap data-forms="[^"]+">', h), (code, seg)
            # the caption names the rows without coordinates in this version's words (outside evaluation 2026-10-18)
            off = len(rows) - len(geo)
            if off:
                tail = " · " + w["off_map"]
                assert (f'<span data-geo-off data-tpl="{escape(tail)}">{escape(tail.replace("{n}", str(off)))}'
                        '</span>') in h, (code, seg)
        else:
            assert not geo and "data-view=" not in bar, (code, seg)
        assert f'<p class="empty" data-empty hidden>{html.escape(w["empty"], quote=False)}</p>' in h, (code, seg)
        # the zero-result panel under the bar: the '{v}' button template and the reset in this version's words
        assert (f'<div class="f-undo" data-f-undo data-one="{escape(w["clear_one"])}" hidden><button type="button" '
                f'data-f-reset>{escape(w["clear_all"])}</button></div>') in bar, (code, seg)
        assert not HANGUL.search(html.unescape(re.sub(r"<[^>]+>", " ", bar))), (code, seg)


def test_closed_day_cells_follow_the_korean_in_every_version(site):
    """QA 2026-10-15 SRC-04: the closed day inside a food place's hours value (gunsan-306687: '… / 4째주 일요일 휴무',
    another source's value differs) is in every version's list cell as on the Korean list — never 'not listed', both
    sources (is-conflict) — and the hours cell does not repeat it. The real English translations: no closed tile
    carries a 'more' the Korean tile lacks (경원아나고: the whole closed day, nothing behind it)."""
    out, pid = site["out"], PLACES[1]

    def cells(h: str, place: str) -> dict:
        row = next(x for x in h.split('<li class="rec"')[1:] if f'data-place="{place}"' in x)
        return {k: m for k, m in ((k, re.search(rf'<div class="c-{k}( is-conflict)?">(.*?)</div>', row, re.S))
                                  for k in ("hours", "closed")) if m}
    ko = cells((out / "food" / "index.html").read_text("utf-8"), pid)
    assert ko["closed"].group(1) and 'class="kf-na"' not in ko["closed"].group(2)
    for code in ("en", *NEW):
        c = cells((out / code / "food" / "index.html").read_text("utf-8"), pid)
        assert c["closed"].group(1) and 'class="kf-na"' not in c["closed"].group(2), code
        assert c["closed"].group(2).count('class="kf-alt"') == ko["closed"].group(2).count('class="kf-alt"') == 2, code
    en = cells((out / "en" / "food" / "index.html").read_text("utf-8"), "gunsan-306610")
    ko2 = cells((out / "food" / "index.html").read_text("utf-8"), "gunsan-306610")
    assert "kf-more" not in ko2["closed"].group(2) and "kf-more" not in en["closed"].group(2)
    assert "Sunday" in en["closed"].group(2) and "Sunday" not in en["hours"].group(2)


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
    slug = _slug(site, "gunsan-307033")    # 게스트하우스 이웃, 010-4891-5402
    for code in ("en", *NEW):
        page = (out / code / "places" / slug / "index.html").read_text("utf-8")
        tile = _kf_tel(page)
        assert 'href="tel:+821048915402"' in tile and '<span class="kf-sub tn">+82 10-4891-5402</span>' in tile, code
        row = _fact_row(page, "infocenter")
        assert row.index(">010-4891-5402</a>") < row.index('<span class="tel-intl tn"><span class="nw">+82 10-4891-5402'), code
        assert 'href="tel:01048915402"' not in page
    assert 'href="tel:01048915402"' in _ko_page(site, "gunsan-307033").read_text("utf-8")
    # list cells dial +82 but show no second number
    stays = (out / "en" / "stays" / "index.html").read_text("utf-8")
    assert 'href="tel:+821048915402"' in stays and "+82 10-4891-5402" not in stays


def test_validator_catches_a_domestic_call_link_on_a_foreign_page(site, tmp_path):
    out = tmp_path / "dist"
    slug = _slug(site, "gunsan-307033")
    src = site["out"] / "ja" / "places" / slug / "index.html"
    dst = out / "ja" / "places" / slug / "index.html"
    dst.parent.mkdir(parents=True)
    dst.write_text(src.read_text("utf-8").replace("tel:+821048915402", "tel:01048915402"), "utf-8")
    errors, _, _ = validate(site["data"], out, "production")
    assert any("/ja/" in x and "국제 형식이 아닌 전화 링크" in x for x in errors), errors[:5]


def test_transport_guide_links_the_official_booking_sites(site):
    """SRC-05b: the hosts the guide writes as text are links (Korail; the KSA ferry booking in its English page on
    the other versions; Kobus is not linked: not checked), never inside a heading or the table of contents; the
    Bustago source gets its English page next to it. The Korean page links the same hosts to their Korean pages."""
    page = (site["out"] / "en" / "guides" / "how-to-get-to-gunsan-from-seoul-incheon-airport-and-iksan" / "index.html").read_text("utf-8")
    hrefs = re.findall(r'<a class="xl" href="([^"]+)"', page)
    assert "https://www.korail.com/" in hrefs and "https://island.theksa.co.kr/page/booking?lang=en" in hrefs
    assert not any("kobus" in h for h in hrefs)
    for h2 in re.findall(r"<h2\b.*?</h2>", page, re.S):
        assert 'class="xl"' not in h2
    for nav in re.findall(r"<nav\b.*?</nav>", page, re.S):
        assert 'class="xl"' not in nav
    src = page[page.index('id="h-src"'):]
    assert src.count('href="https://www.bustago.or.kr/newweb/en/index.do" hreflang="en"') == 1
    k12 = (site["out"] / "guides" / "군산-가는-법-교통" / "index.html").read_text("utf-8")   # guide-12
    assert "코버스(www.kobus.co.kr)" in k12
    assert '<a class="xl" href="https://www.korail.com/"' in k12 and '<a class="xl" href="https://island.theksa.co.kr/"' in k12


@pytest.fixture(scope="module")
def real():
    """The real data/gunsan with every version, on a fixed build date (2026-10-13: the museum's weekend programme,
    '2026. 6. 6. ~ 10월', is running)."""
    from pipeline import en_site
    from pipeline.build import State, kakao_sdk_url, make_env
    S = State(GUNSAN, "production")
    S.today = "2026-10-13"
    S.intl = en_site.load_all(S, GUNSAN)
    S.en = S.intl.sites.get("en")
    env = make_env()
    env.globals["kakao_sdk"] = kakao_sdk_url(S.site)
    return {"S": S, "env": env}


def test_a_draft_place_in_a_guide_item_is_no_name_miss(real):
    """Gunsan preview 2026-11-02 (site.json intl.require_complete): published guides list places the preview shows as
    drafts (군산내항 in guide-05). The versions translate published places only, so such an item is built as in
    production, where the draft is no entity — no name written by its sound and no name miss that stops the build;
    a published place without the version's page still is one."""
    S = real["S"]
    hashes = current_hashes(GUNSAN)["places"]
    draft = next(e for e in S.entities_all if e.get("status") == "draft" and e["id"] not in hashes)
    pub = next(e for e in S.entities if e["id"] in hashes)
    assert draft["slug"] not in S.ent_by_slug
    S.ent_by_slug[draft["slug"]] = draft        # as the preview State has it
    try:
        for code, site in S.intl.sites.items():
            row = site.item_rows([{"place_slug": draft["slug"], "reason": "x"}])[0]
            assert row["p"] is None and row["name_ko"] == "" and draft["name"] not in site.name_misses, code
            assert row["name"] not in (romanize(draft["name"]), LC.kontsevich(draft["name"])), code
            mine = site.place_by_ko_slug.pop(pub["slug"])
            try:
                row = site.item_rows([{"place_slug": pub["slug"], "reason": "x"}])[0]
                assert pub["name"] in site.name_misses and row["name_ko"] == pub["name"], code
            finally:
                site.place_by_ko_slug[pub["slug"]] = mine
                site.name_misses.discard(pub["name"])
    finally:
        del S.ent_by_slug[draft["slug"]]


def test_a_published_slug_stays_when_the_english_title_is_translated_anew(real):
    """Gunsan 2026-11-02: the translation tables rewrote 13 English titles of guides, columns and courses (sound copies
    translated, 'Restaurants open on Monday in Gunsan' → 'Gunsan restaurants open on Monday'). A slug comes from the
    title, so those pages would have moved in all eight versions and vercel.json's /<code>/guides/guide-24/ would lead
    nowhere. en/slugs.json keeps each published slug; a record without one takes its title's slug, never a pinned one."""
    from pipeline import en_site
    S = real["S"]
    pins = en_site.published_slugs(GUNSAN)
    assert all(pins[k] for k in en_site.PINNED_KINDS)
    for code, site in S.intl.sites.items():
        assert site.guides["guide-24"]["slug"] == "restaurants-open-on-monday-in-gunsan", code
        for kind in en_site.PINNED_KINDS:
            for rid, x in getattr(site, kind).items():
                assert x["slug"] == pins[kind][rid], (code, kind, rid)
    items = [{"id": "guide-90", "t": "Island ferries in Gunsan"}, {"id": "guide-32", "t": "Gunsan island ferries"},
             {"id": "guide-91", "t": "Cafes by the sea"}]
    en_site.Site._slugs(None, items, lambda x: x["t"], lambda x: x["id"], lambda x: "",
                        {"guide-32": "island-ferries-in-gunsan"})
    assert [x["slug"] for x in items] == ["island-ferries-in-gunsan-90", "island-ferries-in-gunsan", "cafes-by-the-sea"]


MUSEUM_EV = "fest-군산근대역사박물관-주말상설행사-2026"


def test_an_end_given_only_as_a_month_stays_a_month_in_every_version(real, tmp_path):
    """SRC-06: an end the source gives only as a month ('~10월') is that month on every version's home card, its
    'Coming up' row and its events page — never the month's last day ('until Oct 31'); the card's chip says only that
    it is on. The month's last day still sorts the row among the upcoming ones."""
    from pipeline import en_site
    S, env = real["S"], real["env"]
    assert set(S.intl.sites) == {"en", *NEW}
    for code, site in S.intl.sites.items():
        loc, t = site.loc, site.t
        EV = site.events_vm()
        row = next(r for r in EV["upcoming"] if r["x"]["sr"]["newest"].get("id") == MUSEUM_EV)
        assert row["end_month"] == "2026-10" and row["end"] == "" and row["last"] == "2026-10-31", code
        pg = en_site.Pages(site, env, tmp_path, S.intl)
        # the home shows only the first few editions (2026-10-31: new exhibitions and the pinned fireworks came in
        # ahead of it), so its home card and row are checked where they are shown; the events page always lists it
        card = next((c for c in pg.home_news(EV) if c["key"] == "ev:" + MUSEUM_EV), None)
        assert card is None or (card["end_month"] == "2026-10" and "last" not in card), code
        pg.home()
        pg.events()
        month, day = html.escape(loc.mon("2026-10")), html.escape(loc.md("2026-10-31"))
        home = (tmp_path / code / "index.html").read_text("utf-8")
        anchor = f'events/#{row["anchor"]}"'
        if card is not None:
            i = home.index(anchor)
            nc = home[home.rindex('<article class="nc', 0, i):home.index("</article>", i)]
            assert f"–{month}</time>" in nc and day not in nc, (code, nc)
            assert f"<span>{html.escape(t.now_on)}</span>" in nc, code
        if anchor in home[home.index('id="h-ev"'):]:
            evr = home[home.index(anchor, home.index('id="h-ev"')):]
            evr = evr[:evr.index("</li>")]
            assert month in evr and day not in evr, code
        evp = (tmp_path / code / "events" / "index.html").read_text("utf-8")
        art = evp[evp.index(f'id="{row["anchor"]}"'):]
        head = art[:art.index("</h3>")]
        assert f"–{month}<span" in head and day not in head, code


def test_a_seat_count_alone_is_not_parking_in_every_version(real, tmp_path):
    """모트 '30석' (군산시 '주차 및 좌석수', seats only) in every version: no parking tile, parking once in each
    'Not listed' line, the facts row labelled seating, the list's parking cell 'Not listed' with the translated seats
    under it, no parking word in the title; 명동소바's two sources both on the first screen."""
    from pipeline import en_site, present
    S, env = real["S"], real["env"]
    motte, soba = S.ent_by_slug["모트"], S.ent_by_slug["명동소바"]
    for code, site in S.intl.sites.items():
        p = site.own(motte)
        park, seat = site.fact_label("parking"), site.fact_label("seat")
        k = site.key_facts(p, "hero")
        assert not [s for s in k["slots"] if s["key"] == "parking"], code
        assert k["missing"].count(park) == 1 and site.missing_facts(p).count(park) == 1, code
        assert [r["label"] for r in site.fact_rows(p, ["parking_seats"], present.Notes())] == [seat], code
        value = p["rec"]["facts"]["parking_seats"]["value"]
        cell = next(c for g in site.list_vm("food")["groups"] for r in g["recs"] if r["e"]["id"] == motte["id"]
                    for c in r["cells"] if c["key"] == "parking")
        assert cell["missing"] and cell["label"] == park and value in cell["sub"], code
        assert not HANGUL.search(cell["sub"]), code
        pg = en_site.Pages(site, env, tmp_path, S.intl)
        pg.place(p)
        page = (tmp_path / unquote(p["path"]).strip("/") / "index.html").read_text("utf-8")
        title = html.unescape(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
        assert site.T("TITLE_LABELS.parking_seats") not in title, (code, title)
        assert 'class="kf-i kf-parking' not in page and html.escape(value) in page, code
        s = next(s for s in site.key_facts(site.own(soba), "hero")["slots"] if s["key"] == "parking")
        assert s["conflict"] and len(s["vals"]) == 2, code


TICKET_PLACES = ("근대역사박물관", "구-일본-제18은행-군산지점", "군산근대건축관", "진포해양공원", "채만식-문학관",
                 "31운동-100주년-기념관", "금강미래체험관")


def test_the_fee_tile_sets_the_own_price_beside_the_combined_ticket_in_every_version(real, tmp_path):
    """Operator-forwarded evaluation 2026-10-18, review 2026-10-18 (the Korean tile: present.fee_with_ticket): every
    place the Korean tile sets beside a combined ticket shows the pair in every version, also where its own table does
    not name the ticket — this version's own price row as main (the row of the Korean's visitor group: never a
    residents' price, never behind a long group name), the ticket's price for the same visitor from tickets.json in this
    language's money after the ticket's translated name (strings ticket:<name>; the short name when the part would be
    longer than a tile's part) as sub; the ticket's provider joins those under the tiles. A place whose Korean tile has
    no ticket (two sources differ on its fee) has none here either."""
    from pipeline import present
    from pipeline.en_site import BRIEF_MAX, squash_ws
    S = real["S"]
    seen = 0
    for code, site in S.intl.sites.items():
        loc = site.loc
        for slug in TICKET_PLACES:
            e = S.ent_by_slug[slug]
            ko = present.slot_value(e, "fee")
            p = site.own(e)
            kf = site.key_facts(p, "hero")
            fee = next(s for s in kf["slots"] if s["key"] == "fee")
            if not ko.get("ticket"):
                assert not fee.get("ticket") and ko["conflict"] == fee["conflict"], (code, slug)
                continue
            t = ko["ticket"]
            own = present.own_fee_row(e["facts"]["usefee"])
            value = squash_ws(p["rec"]["facts"]["usefee"]["value"])   # a French thousands space stays as it is
            assert not fee["conflict"] and fee["more"] and fee.get("ticket") == t, (code, slug)
            assert fee["main"][:1].lower() + fee["main"][1:] in value or fee["main"] in value, (code, slug, fee["main"])
            assert re.sub(r"\D", "", fee["main"]) == re.sub(r"\D", "", own["price"]), (code, slug, fee["main"])
            assert fee["sub"].endswith(loc.money(t["price"])), (code, slug, fee["sub"])
            names = (site.T(f"ticket:{t['name']}"), site.T(f"ticket:{present.COMBINED}"))
            assert all(names) and fee["sub"].split(loc.colon.strip() or loc.colon, 1)[0].strip() in names, (code, slug)
            limit = BRIEF_MAX // 2 if loc.cjk else BRIEF_MAX
            assert len(fee["sub"]) <= limit or fee["sub"].startswith(names[1]), (code, slug, fee["sub"])
            assert site.short_provider(t["provider_full"]) in kf["providers"], (code, slug)
            # what the ticket opens is never the Korean table's words; the residents' price never stands alone
            assert not re.search(r"[가-힣]", f"{fee['main']} {fee['sub']}"), (code, slug)
            seen += 1
    # all seven: 진포해양공원 too since TourAPI gave the same fee as 군산시 (2026-11-05)
    assert seen == 7 * len(S.intl.sites) and len(S.intl.sites) == 8
    # 금강미래체험관 lists 군산시민 first: every version gives the visitor's 2,000 beside the ticket's 5,000
    for code, site in S.intl.sites.items():
        fee = next(s for s in site.key_facts(site.own(S.ent_by_slug["금강미래체험관"]), "hero")["slots"] if s["key"] == "fee")
        assert (re.sub(r"\D", "", fee["main"]), re.sub(r"\D", "", fee["sub"])) == ("2000", "5000"), code
    # the facts card (review 2026-10-18), as the Korean card's ticket rows (present.ticket_rows): every ticket that
    # opens the place right after its own fee — its name in this language, its places by their page names here (each
    # linked but this one), its table in this language's money and words, and the table's page as its note
    from markupsafe import escape

    from pipeline import en_site
    by_id = {x["id"]: x for x in S.entities}
    for code, site in S.intl.sites.items():
        loc = site.loc
        for slug in TICKET_PLACES:
            e = S.ent_by_slug[slug]
            p = site.own(e)
            vm = site.place_vm(p)
            keys = [r["key"] for r in vm["practical"]]
            at = keys.index("usefee")
            rows = vm["practical"][at + 1:at + 1 + len(e["_tickets"])]
            assert e["_tickets"] and keys.count("tickets") == len(e["_tickets"]) == len(rows), (code, slug)
            for r, t in zip(rows, e["_tickets"]):
                html_ = str(r["html"])
                assert r["key"] == "tickets" and r["label"] == site.T(f"ticket:{t['name']}"), (code, slug)
                for pid in t["places"]:
                    q = site.own(by_id[pid])
                    link = f'<a href="{q["path"]}">{escape(q["name"])}</a>'
                    assert escape(q["name"]) in html_ and (link in html_) == (pid != e["id"]), (code, slug, pid)
                for table in t["prices"].values():
                    for a, b in table.values():
                        assert loc.money(a) in r["text"] and loc.money(b) in r["text"], (code, slug, r["text"])
                assert not re.search(r"[가-힣]", f"{r['label']} {r['text']} {html_}"), (code, slug, r["text"])
                note = vm["notes"][r["n"] - 1]
                assert (note["provider"], note["url"]) == (site.provider(t["src"]["provider"]), t["src"]["url"]), code
            top = 0   # the notes stay numbered in the order the card shows them
            for r in vm["practical"]:
                for n in [r["n"], *(x["n"] for x in r["blocks"]), *(x["n"] for x in r["alts"])]:
                    assert not n or n <= top + 1, (code, slug, r["label"], n, top)
                    top = max(top, n or 0)
        p = site.own(S.ent_by_slug["근대역사박물관"])
        en_site.Pages(site, real["env"], tmp_path, S.intl).place(p)
        page = (tmp_path / unquote(p["path"]).strip("/") / "index.html").read_text("utf-8")
        dd = re.findall(r'<dd data-key="tickets">(.*?)</dd>', page, re.S)
        assert len(dd) == 2 and all("<a href=" in x and loc.money(5000 if i else 3000) in html.unescape(x)
                                    for i, x in enumerate(dd)), code


def test_a_conflicted_fee_tile_briefs_each_value_against_its_korean_value(real):
    """Review 2026-10-18: where two sources give a fee differently (진포해양공원), every version's tile shows each value
    as the Korean tile does (present.brief_fee) — the row of the translated table that states the Korean value's first
    amount as main, its group (a '[…]' header, or the words in front of the row) as sub — never a bare group header
    ('[Individuals', 'Einzelpersonen'): each value of a conflicted fee tile holds its price."""
    from pipeline import en_site, present
    S = real["S"]
    nums = lambda t: [re.sub(r"\D", "", n) for n in re.findall(r"\d+(?:[.,  ]\d{3})*", t)]   # noqa: E731
    seen, places = 0, 0
    for e in S.entities:
        ko = present.slot_value(e, "fee")
        if not (ko and ko["conflict"]):
            continue
        places += 1
        for code, site in S.intl.sites.items():
            p = site.own(e)
            s = next((s for s in site.key_facts(p, "hero")["slots"] if s["key"] == "fee"), None) if p else None
            if not s:
                continue
            assert s["conflict"] and len(s["vals"]) == len(ko["vals"]), (e["name"], code)
            for x, k in zip(s["vals"], ko["vals"]):
                assert nums(k["main"])[0] in nums(x["main"]), (e["name"], code, k["main"], x["main"])
                assert not x["main"].startswith(("[", "【", "［")) and "※" not in x["main"], (e["name"], code, x["main"])
            seen += 1
    assert places >= 1 and seen == places * len(S.intl.sites)   # every conflicted fee place, in every version
    # 진포해양공원 until TourAPI agreed on 2026-11-05: the Korean value was one flat line (no row marks), and English and
    # Japanese translated it as one line too (the table, 2026-11-02), so their tile's first value is that whole line —
    # it holds the Korean tile's amount, no bare header (its Korean values and translations as they were then)
    ko_flat = ("개인 단체(20인 이상) 성인 (군산시민) 1,000 (500) 700 (300) 청소년,군인 (군산시민) 700 (300) 400 (200) "
               "어린이 (군산시민) 300 (200) 200 (100)")
    ko_tour = ("[개인]- 성인 3,000원(500원)- 청소년,군인 2,000원(300원)- 어린이 1,000원(200원)[단체]- 성인 2,000원(300원)- "
               "청소년,군인 1,000원(200원)- 어린이 500원(100원)※ 군산시 거주자 요금")
    was = {"en": ("Individuals / groups (20 or more) · Adults (Gunsan residents): 1,000 (500) / 700 (300) · Teens and "
                  "soldiers (Gunsan residents): 700 (300) / 400 (200) · Children (Gunsan residents): 300 (200) / 200 (100)",
                  "[Individuals]\n- Adults 3,000 won (500 won)\n- Teens, soldiers 2,000 won (300 won)\n- Children 1,000 won "
                  "(200 won)\n[Groups]\n- Adults 2,000 won (300 won)\n- Teens, soldiers 1,000 won (200 won)\n- Children 500 "
                  "won (100 won)\n※ Gunsan resident rates in parentheses"),
           "ja": ("個人 団体（20人以上） 大人（群山市民） 1,000（500） 700（300） 青少年・軍人（群山市民） 700（300） 400（200） "
                  "子ども（群山市民） 300（200） 200（100）",
                  "【個人】 - 大人 3,000ウォン（500ウォン） - 青少年・軍人 2,000ウォン（300ウォン） - 子ども 1,000ウォン（200ウォン） "
                  "【団体】 - 大人 2,000ウォン（300ウォン） - 青少年・軍人 1,000ウォン（200ウォン） - 子ども 500ウォン（100ウォン） "
                  "※ 群山市居住者の料金"),
           "de": ("Einzelpersonen / Gruppen (ab 20 Personen): Erwachsene (Einwohner von Gunsan) 1.000 (500) / 700 (300); "
                  "Jugendliche, Soldaten (Einwohner von Gunsan) 700 (300) / 400 (200); Kinder (Einwohner von Gunsan) "
                  "300 (200) / 200 (100)", "")}
    tiles = {code: [(b["main"], b["sub"]) for b in (en_site.fee_brief(k, v, S.intl.sites[code].loc)
                                                     for k, v in zip((ko_flat, ko_tour), vals) if v)]
             for code, vals in was.items()}
    assert tiles["en"] == [("Individuals / groups (20 or more) · Adults (Gunsan residents): 1,000 (500) / 700 (300) · "
                            "Teens and soldiers (Gunsan residents): 700 (300) / 400 (200) · "
                            "Children (Gunsan residents): 300 (200) / 200 (100)", ""),
                           ("Adults 3,000 won (500 won)", "Individuals")]
    assert tiles["ja"] == [("個人 団体（20人以上） 大人（群山市民） 1,000（500） 700（300） 青少年・軍人（群山市民） 700（300） "
                            "400（200） 子ども（群山市民） 300（200） 200（100）", ""), ("大人 3,000ウォン（500ウォン）", "個人")]
    assert tiles["de"][0] == ("Erwachsene (Einwohner von Gunsan) 1.000 (500) / 700 (300)",
                              "Einzelpersonen / Gruppen (ab 20 Personen)")
    # a row's '- ' item marks and '※' notes inside one line, as the Korean lines read them (restore_lines)
    assert en_site.fee_brief("[개인]- 성인 3,000원(500원)※ 군산시 거주자 요금",
                             "[Individuals] - Adults 3,000 won (500 won) ※ Gunsan resident rates") == \
        {"main": "Adults 3,000 won (500 won)", "sub": "Individuals", "more": True}


def test_the_last_entry_the_korean_tile_shows_is_on_every_versions_tile(real):
    """Review 2026-10-18: a last entry the Korean hours tile shows — a time (kept whole: keep_last), a rule in words
    ('폐관 30분 전까지 입장': its translation from the value it translates, carry_last) or another source's (relation
    'also': its translated value, last_entry_tr) — is on the same value's tile in every version."""
    from pipeline import en_site, present
    S = real["S"]
    seen = set()
    for e in S.entities:
        v = present.slot_value(e, "hours")
        if not v:
            continue
        kv = v["vals"] if v["conflict"] else [v]
        for code, site in S.intl.sites.items():
            p = site.own(e)
            s = next((s for s in site.key_facts(p, "hero")["slots"] if s["key"] == "hours"), None) if p else None
            if not s:
                continue
            fv = s["vals"] if s["conflict"] else [s]
            for x, f in zip(kv, fv):
                k, t = f"{x['main']} {x['sub']}", f"{f['main']} {f['sub']}"
                if en_site.KO_RULE.search(k):
                    assert en_site.MINUTES_RULE.search(t), (e["name"], code, k, t)
                    seen.add(e["slug"])
                for tm in re.findall(r"(?:입장\s*(?:마감|종료)|마지막\s*입장)\s*(\d{1,2}:\d{2})", k):
                    assert tm in t, (e["name"], code, k, t)
                    seen.add(e["slug"])
            if v.get("also"):
                assert site.short_provider(v["also"]["provider_full"]) in site.key_facts(p, "hero")["providers"], code
    assert {"채만식-문학관", "진포해양공원", "일제강점기-군산역사관", "군산근대건축관", "군산신흥동일본식가옥"} <= seen
    arch = {code: next(s for s in site.key_facts(site.own(S.ent_by_slug["군산근대건축관"]), "hero")["slots"]
                       if s["key"] == "hours") for code, site in S.intl.sites.items()}
    assert arch["en"]["sub"] == "Summer (last entry 17:30), Winter (last entry 16:30)"
    assert (arch["ja"]["main"], arch["ja"]["sub"]) == ("冬季 09:00–17:00", "夏季 09:00–18:00 · 夏季（入場締切17:30）、冬季（入場締切16:30）")
    # 쌍용반점 (review 2026-10-18): the Korean tile leaves out the whole source line of a '※' note, the closed days
    # after its '/' with it (present.clean_lines); every version leaves out the same, never a cut closed day
    e = S.ent_by_slug["쌍용반점"]
    ko = [(x["main"], x["sub"]) for x in present.slot_value(e, "hours")["vals"]]
    assert ko == [("11:30–21:00", ""), ("11:30–19:00", "")]
    for code, site in S.intl.sites.items():
        s = next(s for s in site.key_facts(site.own(e), "hero")["slots"] if s["key"] == "hours")
        assert [(x["main"], x["sub"]) for x in s["vals"]] == ko, (code, s["vals"])
    assert en_site._segments("11:30–19:00 ※ Closes early / second Monday\n[Winter] 10:00–17:00 / 매일", True) == \
        [("", "11:30–19:00"), ("", "Winter 10:00–17:00"), ("", "매일")]
    # 초원사진관: the Korean tile reads the TourAPI value's two ranges one by one ('월요일 09:00–18:00' · '화요일~일요일
    # 09:00–21:30'); every version shows both, never Monday's alone (the translations joined the two lines)
    e = S.ent_by_slug["초원사진관"]
    ko = present.slot_value(e, "hours")["vals"][1]
    assert (ko["main"], ko["sub"]) == ("월요일 09:00–18:00", "화요일~일요일 09:00–21:30")
    for code, site in S.intl.sites.items():
        s = next(s for s in site.key_facts(site.own(e), "hero")["slots"] if s["key"] == "hours")
        assert s["conflict"] and "18:00" in s["vals"][1]["main"] and "21:30" in s["vals"][1]["sub"], (code, s["vals"][1])


def test_japanese_and_chinese_group_headers_label_their_rows():
    """A '【…】' header line in Japanese and Chinese is the group's name, as '[…]' is in the other versions: the fee tile
    shows the group's first row, never the bare header; the fee pair reads the Korean visitor's group in the
    translated table (review 2026-10-18: the price row as main, the ticket's name and price as sub)."""
    from pipeline import en_site
    ja = LC.get("ja")
    assert en_site.brief_en("usefee", "【個人】\n- 大人500ウォン\n- 子ども200ウォン\n【団体】\n- 大人300ウォン", ja) == \
        {"main": "大人500ウォン", "sub": "個人", "more": True}
    ko = "[박물관 통합권]\n- 성인 3,000원\n[개별권]\n- 성인 2,000원"
    names = ("博物館統合券", "統合券")
    assert en_site.fee_pair(ko, "【博物館統合券】\n- 大人3,000ウォン\n【個別券】\n- 大人2,000ウォン", 3000, names, ja) == \
        {"main": "大人2,000ウォン", "sub": "博物館統合券：大人3,000ウォン", "more": True}
    en = LC.get("en")
    names = ("Museum combined ticket", "Combined ticket")
    assert en_site.fee_pair(ko, "[Museum combined ticket]\n- Adults 3,000 won\n[Single-site ticket]\n- Adults 2,000 won",
                            3000, names, en) == \
        {"main": "Adults 2,000 won", "sub": "Museum combined ticket: Adults 3,000 won", "more": True}
    # a table without the ticket: its own row, the ticket's price from tickets.json
    assert en_site.fee_pair("- 성인 500원\n- 어린이 200원", "- Adults 500 won\n- Children 200 won", 3000, names, en) == \
        {"main": "Adults 500 won", "sub": "Museum combined ticket: Adults 3,000 won", "more": True}
    # residents first: the visitor's group, in the same place among the translated groups
    assert en_site.fee_pair("[군산시민]\n- 성인 1,000원\n[타지역]\n- 성인 2,000원",
                            "[Gunsan residents]\n- Adults 1,000 won\n[Other regions]\n- Adults 2,000 won", 5000,
                            ("Geumgang area combined ticket", "Combined ticket"), en) == \
        {"main": "Adults 2,000 won", "sub": "Combined ticket: Adults 5,000 won", "more": True}   # the name: too long
    assert en_site.fee_pair(ko, "- Adults 3,000 won\n- Adults 2,000 won", 3000, names, en) is None   # groups do not line up
    assert en_site.fee_pair(ko, "[A]\n- Adults 3,000 won\n[B]\n- Adults 1,000 won", 3000, names, en) is None  # not the amount
    assert en_site.fee_pair(ko, "[A]\n- Adults 3,000 won\n[B]\n- Adults 2,000 won", 3000, ("", ""), en) is None


def test_cjk_hours_tiles_cut_at_their_own_marks_and_keep_the_season():
    """Review 2026-10-18: a Japanese or Chinese hours value is cut at '／', at a '/' with no space before it and after
    a range another part follows (never inside brackets), as the Korean tile reads its ranges one by one; a long part
    loses its months in brackets before its season word; '[Season]' headers inside a line label their range in every
    version; a last entry the Korean tile shows stays."""
    from pipeline import en_site
    ja, zh, en = LC.get("ja"), LC.get("zh-hans"), LC.get("en")
    b = en_site.brief_en
    assert b("usetime", "3–10月 09:00–18:00（入場締切17:30）／11–2月 09:00–17:00（入場締切16:30）", ja, keep_last=True) == \
        {"main": "3–10月 09:00–18:00（入場締切17:30）", "sub": "11–2月 09:00–17:00（入場締切16:30）", "more": False}
    assert b("usetime", "3–10月 09:00–18:00（17:30停止入场）/ 11–2月 09:00–17:00（16:30停止入场）", zh, keep_last=True)["sub"] == \
        "11–2月 09:00–17:00（16:30停止入场）"
    assert b("usetime", "【夏季（3月–10月）】\n09:00–18:00（入場締切17:30）\n【冬季（11月–2月）】\n09:00–17:00（入場締切16:30）",
             ja, keep_last=True) == {"main": "夏季 09:00–18:00（入場締切17:30）", "sub": "冬季 09:00–17:00（入場締切16:30）",
                                     "more": True}
    v = "【夏季（3月–10月）】 09:00–18:00 【冬季（11月–2月）】 09:00–17:00 ※入場は終了30分前まで可能"
    assert (b("usetime", v, ja)["main"], b("usetime", v, ja)["sub"]) == ("夏季 09:00–18:00", "冬季 09:00–17:00")
    assert (b("usetime", "冬季 09:00–17:00 夏季 09:00–18:00", ja)["main"], b("usetime", "冬季09:00–17:00，夏季09:00–18:00", zh)["sub"]) \
        == ("冬季 09:00–17:00", "夏季09:00–18:00")
    # never cut inside brackets; a fee keeps its '／' (a price with its other price)
    assert en_site._segments("11:30–22:30（準備時間 15:00–17:00／ラストオーダー 21:30）", True, True) == \
        [("", "11:30–22:30（準備時間 15:00–17:00／ラストオーダー 21:30）")]
    assert len(en_site._segments("成人（群山市民）1,000（500）／700（300）", False, True)) == 1
    # a part that holds its only time in brackets keeps the time
    assert b("usetime", "時間旅行観光案内所（10:00–17:00）／チョウォン写真館（09:00–21:30）", ja)["main"] == "10:00–17:00"
    # inline '[Season]' headers in the other versions too; the rule of a '※' note is rule_part's
    v = "[Sommer (März–Oktober)] 09:00–18:00 [Winter (November–Februar)] 09:00–17:00 ※ Einlass bis 30 Minuten vor Schließung"
    assert (b("usetime", v, LC.get("de"))["main"], b("usetime", v, LC.get("de"))["sub"]) == \
        ("Sommer (März–Oktober) 09:00–18:00", "Winter (November–Februar) 09:00–17:00")
    assert en_site.rule_part(v) == "Einlass bis 30 Minuten vor Schließung"
    # the other versions cut after a range only where another part with a range of its own follows (never inside or
    # before brackets), and keep their own tile length
    de = LC.get("de")
    assert b("usetime", "Montag 09:00–18:00 Dienstag–Sonntag 09:00–21:30", de) == \
        {"main": "Montag 09:00–18:00", "sub": "Dienstag–Sonntag 09:00–21:30", "more": False}
    assert en_site._segments("09:00–18:00 daily (break 15:00–17:00)", True) == [("", "09:00–18:00 daily (break 15:00–17:00)")]
    assert en_site._segments("09:00–18:00 except Mondays", True) == [("", "09:00–18:00 except Mondays")]
    assert en_site._segments("Open (Mon 09:00–18:00 Tue 10:00–17:00)", True) == [("", "Open (Mon 09:00–18:00 Tue 10:00–17:00)")]
    assert en_site.rule_part("Summer 10:00–18:00 / winter 10:00–17:00, entry until 30 minutes before closing") == \
        "entry until 30 minutes before closing"
    assert en_site.last_entry_tr("[Summer (March–October)]\n09:00–18:00 (last entry 17:30)\n[Winter (November–February)]\n"
                                 "09:00–17:00 (last entry 16:30)", en) == "Summer (last entry 17:30), Winter (last entry 16:30)"
    assert en_site.last_entry_tr("【夏季（3–10月）】 09:00–18:00（入場締切17:30） 【冬季（11月–2月）】 09:00–17:00（入場締切16:30）", ja) \
        == "夏季（入場締切17:30）、冬季（入場締切16:30）"
    # the last entry the Korean tile shows: a part that ends in it stays whole, here and in Japanese
    v = "March–October 09:00–18:00 (last entry 17:30) / November–February 09:00–17:00 (last entry 16:30)"
    assert b("usetime", v, en, keep_last=True) == {
        "main": "March–October 09:00–18:00 (last entry 17:30)", "sub": "November–February 09:00–17:00 (last entry 16:30)",
        "more": False}
    assert b("usetime", v, en)["main"] == "March–October 09:00–18:00"
    assert b("usetime", "09:00–21:00（入場締切20:30）", ja, keep_last=True)["main"] == "09:00–21:00（入場締切20:30）"


HOME_H1 = {"en": "All About Gunsan Travel", "ja": "群山旅行のすべて", "zh-hans": "群山旅游全攻略", "zh-hant": "群山旅遊全攻略",
           "de": "Alles über Gunsan", "fr": "Tout sur Gunsan", "es": "Todo sobre Gunsan", "ru": "Всё о Кунсане"}


def test_every_home_opening_describes_the_site_and_keeps_the_name_gunsangak(real, tmp_path):
    """Operator 2026-10-16: the home's H1 describes the site — each version's own words for '군산 여행의 모든 것', the
    ones it used before the rename — while the name Gunsangak stays in the bar and in the WebSite JSON-LD."""
    from pipeline import en_site
    S, env = real["S"], real["env"]
    assert set(HOME_H1) == set(S.intl.sites)
    for code, site in S.intl.sites.items():
        en_site.Pages(site, env, tmp_path, S.intl).home()
        home = (tmp_path / code / "index.html").read_text("utf-8")
        h1 = re.search(r'<h1 id="h-home" class="op-h1 hk-h1">(.*?)</h1>', home).group(1)
        assert html.unescape(h1) == HOME_H1[code], (code, h1)
        assert 'class="wm-a">Gunsan<span class="wm-em">gak</span></span>' in home and '"@type":"WebSite"' in home, code
        assert re.search(r'"@type":"WebSite",[^}]*"name":"Gunsangak"', home), code


def test_a_parts_only_nearby_chapter_still_credits_its_photos_in_every_version(real, tmp_path):
    """야미도 and 어청도: once their own family leaves the nearby rows, the chapter holds only the places inside them
    (relations 'inside'), whose rows carry TourAPI photos — every version still prints the photo credit with each
    licence (CLAUDE.md 3절 4항), as the Korean page does."""
    from pipeline import en_site
    S, env = real["S"], real["env"]
    for slug in ("야미도", "어청도"):
        e = S.ent_by_slug[slug]
        for code, site in S.intl.sites.items():
            p = site.own(e)
            v = site.place_vm(p)
            assert v["parts"] and not (v["near_sights"] or v["near_biz"]) and v["photo_lics"], (slug, code)
            en_site.Pages(site, env, tmp_path, S.intl).place(p)
            page = (tmp_path / unquote(p["path"]).strip("/") / "index.html").read_text("utf-8")
            credit = html.escape(v["nw"]["credit"].format(lic=v["photo_lics"][0]).split("·")[0])
            assert 'class="note nb-credit"' in page and credit in page, (slug, code)
            assert all(html.escape(lic) in page for lic in v["photo_lics"]), (slug, code)


def test_place_guide_and_course_pages_have_one_share_button_in_every_version(real, tmp_path):
    """Operator 2026-10-17 (공유하기 + GA4): every version's place, guide and course pages hold one 공유 button in the
    local bar, naming the Korean record's id (GA4 item_id is the same in every language) with that version's words
    (locales.SHARE_WORDS, no Korean script)."""
    from markupsafe import escape

    from pipeline import en_site
    S, env = real["S"], real["env"]
    btn = re.compile(r'<button type="button" class="lnav-share" data-share data-share-id="([^"]*)" data-copied="([^"]*)" '
                     r'data-failed="([^"]*)" data-js-only>.*?<span class="lnav-share-t">([^<]*)</span></button>', re.S)
    motte = S.ent_by_slug["모트"]
    for code, site in S.intl.sites.items():
        w = LC.SHARE_WORDS[code]
        assert not HANGUL.search(" ".join(w.values())), code
        pg = en_site.Pages(site, env, tmp_path, S.intl)
        p = site.own(motte)
        pg.place(p)
        pg.guides()
        pg.courses()
        c = next(iter(site.courses.values()))
        for path, want in ((p["path"], motte["id"]), (site.guides["guide-01"]["path"], "guide-01"),
                           (c["path"], c["c"]["id"])):
            page = (tmp_path / unquote(path).strip("/") / "index.html").read_text("utf-8")
            assert btn.findall(page) == [(want, str(escape(w["copied"])), str(escape(w["failed"])), w["label"])], (code, path)


def test_cited_booking_sites_get_their_page_in_the_readers_language(real):
    """SRC-05b phase 2: a guide's Bustago source gets Bustago's own page in the reader's language next to it —
    Japanese for ja, Simplified Chinese for zh-hans and zh-hant, English otherwise — labelled with that language's
    name; once per site; other sources get none."""
    sites = real["S"].intl.sites
    want = {"en": ("en", "English"), "ja": ("jp", "日本語"), "zh-hans": ("cn", "中文(简体)"), "zh-hant": ("cn", "中文(简体)"),
            "de": ("en", "English"), "fr": ("en", "English"), "es": ("en", "English"), "ru": ("en", "English")}
    for code, (path, label) in want.items():
        G = sites[code].guide_vm(sites[code].guides["guide-12"])
        withe = [s for s in G["sources"] if s.get("entry")]
        bus = [s for s in withe if "bustago" in s["url"]]
        assert len(bus) == 1 and bus[0]["entry"] == f"https://www.bustago.or.kr/newweb/{path}/index.do", code
        assert bus[0]["entry_label"] == label, code
        assert all("bustago" in s["url"] or "theksa" in s["url"] for s in withe), code


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
    a = next(v for v in S.course_vms.values() if v["c"]["id"] == "gunsan-course-m2135-1")
    f, h = _course_page(site, "en", "gunsan-course-m2135-1")
    assert '<table class="wk">' in h and 'id="h-week"' in h and 'href="#h-week"' in h
    row = re.search(r'<tr><th scope="row" class="wk-name"><a href="[^"]+">Modern History Museum</a></th>(.*?)</tr>', h, re.S)
    assert row and row.group(1).split("</td>")[0].endswith('<span class="vh">closed on Monday</span>')
    days = dict(a["closed_by_day"])
    assert LC.course_word("en", "closed_n", days["월"], day="Mondays") in h
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
    assert '<span lang="ko">근대역사박물관</span>' in move and "Not listed: travel time per leg" in move
    assert not scan_file(f).hangul
    assert "https://www.google.com/maps/search/?api=1&amp;query=" in h and 'data-provider="google"' in h
    _, b = _course_page(site, "en", "gunsan-course-m2136-2")
    assert '<dt>Time needed</dt><dd class="tn">12 hours</dd>' in b
    heads = re.findall(r'<li class="stop-sep sep-day"><span class="sep-k">Itinerary</span><span class="sep-v">([^<]+)</span>', b)
    assert heads == ["Day 1", "Day 2, option 1", "Day 2, option 2"]
    # the fake-translated versions (one course each): the grid in their own weekday names, the note in their plural
    c = next(v for v in S.course_vms.values() if v["c"]["id"] == COURSE)
    day, cnt = max(c["closed_by_day"].items(), key=lambda kv: (kv[1], -"월화수목금토일".index(kv[0])))
    for code in ("ja", "ru"):
        _, p = _course_page(site, code, COURSE)
        w = LC.COURSE_WORDS[code]
        assert '<table class="wk">' in p and all(f'<th scope="col" class="wk-d">{d}</th>' in p for d in w["wd_short"])
        assert html.escape(LC.course_word(code, "closed_n", cnt, day=w["closed_day"]["월화수목금토일".index(day)])) in p
        assert w["move_h"] in p and 'data-provider="google_transit"' in p


def test_every_version_is_built_and_has_the_coordinate_source_words(real):
    """A missing UI word drops that whole version from the build (en_site.load_all): every version of the real data is
    built, and the words that name whose coordinates a page uses (map_loc, legs_measured_src) are in every version's
    strings with every plural form of its language, keeping their placeholders, without Korean script."""
    S = real["S"]
    assert S.intl.skipped == {} and set(S.intl.sites) == {"en", *NEW}
    for code in NEW:
        loc = LC.get(code)
        strings = json.loads((GUNSAN / code / "strings.json").read_text("utf-8"))
        for key in ["chrome.map_loc"] + [f"chrome.legs_measured_src.{f}" for f in loc.plural]:
            text = strings[key][loc.tag]
            assert text and not HANGUL.search(text), (code, key)
            want = {"{provider}"} if key == "chrome.map_loc" else {"{a}", "{b}", "{src}"}
            assert set(PLACEHOLDER.findall(text)) == want, (code, key, text)


def test_every_version_names_whose_points_a_page_uses(real, tmp_path):
    """A stop and place whose point comes from 군산시 문화관광 (tools/official_coords.py): in every version the course's
    sources name both providers of the measured legs (legs_measured_src) and the place's map caption and nearby note
    name theirs, in the version's words and never in Korean script; a TourAPI-only course keeps legs_measured."""
    from pipeline import en_site, present
    S, env = real["S"], real["env"]
    e = S.ent_by_slug["월명공원"]
    c = next(x for x in S.courses if x["id"] == "gunsan-course-m2107-1")
    saved = (e["geo"], e["_geo"], e.get("nearby_source"), S.course_vms[c["slug"]])
    city = {"lat": e["geo"]["lat"], "lng": e["geo"]["lng"], "source": "군산시 문화관광",
            "url": "https://www.gunsan.go.kr/tour/m2080/view/1", "checked_at": "2026-10-16"}
    try:
        e["geo"] = e["_geo"] = city
        e["nearby_source"] = {**(saved[2] or {}), "provider": "한국관광공사 TourAPI·군산시 문화관광 좌표",
                              "providers": ["한국관광공사 TourAPI", "군산시 문화관광"]}
        S.course_vms[c["slug"]] = present.course_vm(S, c)
        assert S.course_vms[c["slug"]]["geo_providers"] == ["한국관광공사 TourAPI", "군산시 문화관광"]
        for code, site in S.intl.sites.items():
            site._cv.pop(c["id"], None)
            kto, city_name = site.provider("한국관광공사 TourAPI"), site.provider("군산시 문화관광")
            assert kto and city_name and not HANGUL.search(kto + city_name), code
            pg = en_site.Pages(site, env, tmp_path, S.intl)
            pg.courses()
            x = site.courses[c["id"]]
            page = (tmp_path / x["path"].strip("/") / "index.html").read_text("utf-8")
            src = page[page.index('id="h-src"'):]
            dd = html.unescape(re.search(r"<dd>([^<]*)</dd></div>",
                                         src[src.index(f"<dt>{html.escape(site.t.s('distances'))}</dt>"):]).group(1))
            assert kto in dd and city_name in dd and not HANGUL.search(dd), (code, dd)
            other = next(y for y in site.courses.values() if y["c"]["id"] == "gunsan-course-m2135-1")
            op = (tmp_path / other["path"].strip("/") / "index.html").read_text("utf-8")
            C = site.course_vm(other)
            assert not C["geo_mixed"] and site.t.sn("legs_measured", C["legs_possible"], a=C["measured"],
                                                    b=C["legs_possible"]) in html.unescape(op), code
            p = site.own(e)
            pg.place(p)
            pp = (tmp_path / p["path"].strip("/") / "index.html").read_text("utf-8")
            cap = html.unescape(re.search(r'<figure class="mapfig place-map">.*?<figcaption>(.*?)</figcaption>',
                                          pp, re.S).group(1))
            assert site.t.s("map_loc", provider=city_name) in cap and not HANGUL.search(cap), (code, cap)
            note = html.unescape(re.search(r'<p class="note nb-note">(.*?)</p>', pp, re.S).group(1))
            assert kto in note and city_name in note and not HANGUL.search(note), (code, note)
    finally:
        e["geo"], e["_geo"], S.course_vms[c["slug"]] = saved[0], saved[1], saved[3]
        if saved[2] is None:
            e.pop("nearby_source", None)
        else:
            e["nearby_source"] = saved[2]
        for site in S.intl.sites.values():
            site._cv.pop(c["id"], None)


def test_the_about_page_says_what_robots_txt_does_with_training_crawlers(site):
    """Report 2026-10-17: the Korean about page said training crawlers were limited by robots.txt while robots.txt
    let them in (site.json crawler_policy, operator 2026-10-09). The sentence now follows the same setting."""
    about = (site["out"] / "about" / "index.html").read_text("utf-8")
    robots = (site["out"] / "robots.txt").read_text("utf-8")
    allowed = json.loads((site["data"] / "site.json").read_text("utf-8"))["crawler_policy"]["allow_training_bots"]
    group = robots[robots.index("User-agent: GPTBot"):].split("\n\n")[0]
    assert ("Allow: /" in group) is allowed
    assert ("AI 모델 학습용 수집기도 robots.txt에서 허용합니다" in about) is allowed
    assert ("robots.txt로 제한합니다" in about) is (not allowed)
