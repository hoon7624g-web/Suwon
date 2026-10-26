"""Site assistant knowledge (pipeline/chat_index.py), exported from the real data the way the public build does: every
published place, guide (and its sections), course, event series and video is there; a place line carries the
first-screen facts it is meant to (CATALOG_SLOTS) with both values where sources differ; every fact names its source
and the date this site checked it; nearby parking, stops and stations name their sources and the link check allows
their addresses; dates are named for what they are; the about page says what the chat sends where; the city's words
come from site.json (chat_config, chat_meta, ui_config) and reach the function as docs.json meta; no TourAPI overview;
the bytes do not depend on the build date; the catalog stays under its token budget (the cached prefix's price tier)."""
import datetime as dt
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.romanize import romanize
from pipeline import build as B
from pipeline import chat_index, en_site, present
from pipeline.build import State, build
from pipeline.schema import FACT_ORDER, FIT_ORDER

ROOT = Path(__file__).resolve().parent.parent
CITY = ROOT / "data" / "suwon"
SAMPLE = ROOT / "data" / "sample"
LETTERS = ("P ", "G ", "C ", "E ", "V ", "T ", "S ")


def _state(data: Path, mode: str = "production") -> State:
    S = State(data, mode)
    S.en = en_site.load(S, data)   # as pipeline.build does
    return S


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    S = _state(CITY)
    out = tmp_path_factory.mktemp("chat")
    stats = chat_index.export(S, out)
    d = out / "chat"
    return {"S": S, "stats": stats, "dir": d, "catalog": (d / "catalog.txt").read_text("utf-8"),
            "docs": json.loads((d / "docs.json").read_text("utf-8")), "index": json.loads((d / "index.json").read_text("utf-8")),
            "lines": json.loads((d / "lines.json").read_text("utf-8"))}


def _lines(catalog: str) -> dict[str, str]:
    """catalog line by its path (the second field)."""
    return {line.split(" | ")[0][2:]: line for line in catalog.splitlines() if line[:2] in LETTERS}


def test_every_published_record_is_in_the_catalog_and_the_docs(real):
    S, docs = real["S"], real["docs"]["docs"]
    lines = _lines(real["catalog"])
    for e in S.entities:
        assert e["_path"] in lines and e["_path"] in docs, e["id"]
    for x in S.guides + S.courses + S.series:
        assert x["_path"] in lines and x["_path"] in docs, x["_path"]
    for g in S.video_groups:
        assert g["_path"] in lines and g["_path"] in docs, g["_path"]
    for v in S.videos:
        assert docs[f"video:{v['youtube_id']}"]["u"].startswith("/videos/")
    for path in ("/", "/about/", "/map/", "/search/", "/places/", "/food/", "/stays/", "/guides/", "/courses/", "/events/",
                 "/videos/"):
        assert path in lines and path in docs, path
    assert real["stats"]["places"] == len(S.entities) == sum(1 for x in real["catalog"].splitlines() if x.startswith("P "))
    # guide sections: one doc per body section, keyed by the section's anchor on the guide page (h-b1 …)
    for g in S.guides:
        for i, b in enumerate(g.get("body") or [], 1):
            sec = docs[f"{g['_path']}#h-b{i}"]
            assert sec["k"] == "section" and sec["h"] == chat_index._clean(b.get("heading"))
            assert sec["x"].split("\n")[-1].startswith("가이드 날짜: "), (g["id"], i)


def test_place_lines_carry_their_facts_and_both_values_where_sources_differ(real):
    S = real["S"]
    lines = _lines(real["catalog"])
    seen = 0
    for e in S.entities:
        line = lines[e["_path"]]
        slots = {s["key"]: s for s in present.key_facts(e, "hero")["slots"]}
        for name in chat_index.CATALOG_SLOTS[e["kind"]]:
            s = slots.get(name)
            if not s:
                continue
            seen += 1
            label = chat_index.SHORT_LABEL.get(s["label"], s["label"])
            text = chat_index._slot_text(s)
            # every slot with its short label, but '연중무휴' that names itself (the catalog header says so)
            assert text == "연중무휴" or text.startswith(f"{label} "), (e["id"], text)
            assert chat_index.month_ranges(text) in line, (e["id"], text)   # '3~8월' is '3월~8월' there
            if s.get("conflict"):
                assert f"{label} 두 출처 다름: " in line
                for v in s["vals"]:
                    assert v["provider"] in line, (e["id"], v["provider"])
        # the hours, phone and parking are the page's (get_pages), not the line's: the line stays short
        assert not re.search(r"(?:\| |; )(?:전화|문의|시간|주차|체크인) ", line), e["id"]
        if e.get("_district"):
            assert f" | {e['_district']}" in line
        # the place's own doc names both values of every differing fact and the call line
        doc = real["docs"]["docs"][e["_path"]]["x"]
        for k in (e.get("fact_alternatives") or {}):
            row = B.fact_row(e, k)
            if row and any(not a["also"] for a in row["alternatives"]):
                assert "다른 출처 값" in doc and "방문 전 전화 확인" in doc, e["id"]
    assert seen > len(S.entities)    # more slots than places: most places show several


def test_every_fact_names_its_source_and_check_date(real):
    """Each value carries its source, the address it came from when the data has one, and the date this site checked
    that source; the link check (docs.json ext) allows that address."""
    S, docs, ext = real["S"], real["docs"]["docs"], set(real["docs"]["ext"])
    with_url = 0
    for e in S.entities:
        doc = docs[e["_path"]]["x"]
        for k in FACT_ORDER + FIT_ORDER:
            row = B.fact_row(e, k)
            if not row:
                continue
            for src in ([row["source"]] if row["value"] else []) + row["alternatives"]:
                url = chat_index._fact_url(e, src, S.site)
                said = f" — {chat_index._src(src, url)}"
                assert said in doc, (e["id"], k, said)
                if url:
                    with_url += 1
                    assert url in ext, (e["id"], url)
        # the page's own dates, each named for what it is
        dates = chat_index._dates(B.facts_checked_date(e), e.get("reviewed_at") or "", e.get("approved_at") or "")
        assert dates in doc.split("\n"), e["id"]
        assert "페이지 검수" in dates and (not e.get("approved_at") or f"운영자 공개 승인 {e['approved_at']}" in dates)
        kf = present.key_facts(e, "hero")
        if kf["missing"]:
            assert "사이트에 없는 값(확인 필요): " + "·".join(kf["missing"]) in doc
    assert with_url >= 1   # most values are TourAPI's (an API, no page of its own); a facility's own page is linked


def _nearby_city(tmp_path: Path) -> Path:
    """tests/test_guide_content's fake city (four '[샘플]' places of a 구·군 city, nearby.json + parking_lots.json),
    its places published: this city has no nearby files yet (data/<city> without nearby.json, parking_lots.json)."""
    import shutil
    from tests import test_guide_content as G
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy(G.SITE, d / "site.json")
    places = G.places()
    for p in places:
        if not p.get("duplicate_of"):
            p.update(status="published", approved_at="2026-10-20")
    G.write(d / "places.json", places)
    G.write(d / "parking_lots.json", G.parking_lots())
    near = G.nearby()   # each dataset's address and the day this site checked it, as a real nearby.json _meta has them
    for k, url in (("parking", "https://www.data.go.kr/data/15012896/standard.do"),
                   ("bus", "https://www.data.go.kr/data/15067528/fileData.do"), ("rail", "https://www.data.go.kr/x")):
        near["_meta"][k].update(url=url, checked_at="2026-10-11")
    G.write(d / "nearby.json", near)
    return d


def test_nearby_parking_stops_and_stations_name_their_sources(real, tmp_path):
    data = _nearby_city(tmp_path)
    S = _state(data, "preview")
    chat_index.export(S, tmp_path / "out")
    exported = json.loads((tmp_path / "out" / "chat" / "docs.json").read_text("utf-8"))
    docs, ext = exported["docs"], set(exported["ext"])
    kinds = {"lots": 0, "stops": 0, "rails": 0}
    for e in S.entities:
        acc = present.access_vm(S, e)
        if not acc:
            continue
        doc = docs[e["_path"]]["x"]
        if acc["lots"]:
            kinds["lots"] += 1
            assert f"근처 공영주차장(직선 {acc['radius']}m 안): " in doc
            assert all(l["name"] in doc for l in acc["lots"])
        if acc["stops"]:
            kinds["stops"] += 1
            for s in acc["stops"]:
                assert f"{s['name']} {s['m']}m" in doc and (not s["routes_text"] or f"(노선 {s['routes_text']})" in doc)
        if acc["rails"]:
            kinds["rails"] += 1
            assert any(f"{r['name']}" in doc and f"{r['m']}m" in doc for r in acc["rails"])
        src = next(x for x in doc.split("\n") if x.startswith("출처: "))
        for url in re.findall(r"https?://\S+", src):
            assert url in ext, url
        assert "(출처 확인 " in src, e["id"]
    assert all(n >= 1 for n in kinds.values()), kinds
    # this city's places without nearby files: no doc claims a nearby lot, stop or station
    assert not [k for k, d in real["docs"]["docs"].items() if d["k"] == "place" and "근처 공영주차장(" in d["x"]]


def test_dates_by_kind_and_course_values(real):
    S, docs, ext = real["S"], real["docs"]["docs"], set(real["docs"]["ext"])
    for g in S.guides:
        doc = docs[g["_path"]]["x"]
        dates = chat_index._dates(g.get("checked_at") or "", g.get("reviewed_at") or "", g.get("approved_at") or "")
        assert dates in doc and doc.index(dates) < 3000, g["id"]   # before the body: a long guide is cut
    for c in S.courses:
        doc = docs[c["_path"]]["x"]
        assert "날짜: " in doc and "페이지 검수" in doc
        if (c.get("original") or {}).get("collected_at"):
            assert f"원문 수집 {c['original']['collected_at']}" in doc
        # travel between stops is never a time of ours
        assert "구간별 소요시간·총 소요시간은 자료에 없다(이동 미확인)" in doc
        for f in c.get("facts") or []:
            assert f"- {chat_index._clean(f['label'])}: {chat_index._clean(f['value'])}" in doc
        for x in c.get("facts_sources") or []:
            assert x["url"] in doc and x["url"] in ext
    # a tour bus course (tests/test_course_sources TEST_COURSE on the gunsan_subset fixture; this city's courses have no
    # fares or departures): its values in the doc, its hero values on the catalog line
    import shutil
    import tempfile
    from tests.test_course_sources import DATA as SUBSET, TEST_COURSE
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        shutil.copytree(SUBSET, data)
        courses = json.loads((data / "courses.json").read_text("utf-8"))
        (data / "courses.json").write_text(json.dumps(courses + [TEST_COURSE], ensure_ascii=False), "utf-8")
        T = _state(data, "preview")
        chat_index.export(T, Path(tmp) / "out")
        catalog = (Path(tmp) / "out" / "chat" / "catalog.txt").read_text("utf-8")
        tdocs = json.loads((Path(tmp) / "out" / "chat" / "docs.json").read_text("utf-8"))["docs"]
    tour = next(c for c in T.courses if c["id"] == TEST_COURSE["id"])
    line = _lines(catalog)[tour["_path"]]
    for f in tour["facts"]:
        assert f"- {chat_index._clean(f['label'])}: {chat_index._clean(f['value'])}" in tdocs[tour["_path"]]["x"]
        if f.get("hero"):
            assert f"{f['label']} {f.get('short') or f['value']}" in line


def test_the_about_doc_says_what_the_chat_sends_where(real):
    about = real["docs"]["docs"]["/about/"]["x"]
    for words in ("sessionStorage", "서버 함수(/api/chat/)", "최근 12개 메시지", "Anthropic API", "Anthropic의 정책",
                  "이미 보낸 내용을 지울 수 없다", "자동으로 가리는 기능은 없다", "'새 대화'", "Claude Haiku 5.5", "틀릴 수 있어"):
        assert words in about, words
    # the page says the same (templates/about.html.j2)
    page = (ROOT / "templates" / "about.html.j2").read_text("utf-8")
    for words in ('id="chatbot"', "사이트 안내 챗봇", "최근 12개 메시지", "Anthropic API", "지울 수 없습니다",
                  "자동으로 가려 주는 기능은 없습니다", "‘새 대화’", "이 사이트의 데이터로 만듭니다", "틀릴 수 있으니"):
        assert words in page, words


def test_the_city_s_words_come_from_site_json(real):
    """chat_config / chat_meta / ui_config: the region and the assistant in each language, the example questions,
    the extra origins — from site.json chatbot; a city without that object gets neutral fallbacks, never another's."""
    site = json.loads((CITY / "site.json").read_text("utf-8"))
    cfg = chat_index.chat_config(site)
    assert set(cfg["region"]) == set(chat_index.LANGS) and cfg["region"]["ko"] == site["region"]
    assert cfg["assistant"]["ko"] == site["chatbot"]["assistant_name"]["ko"]
    assert set(cfg["chips"]) == set(chat_index.LANGS) and all(1 <= len(q) <= chat_index.CHIPS_MAX for q in cfg["chips"].values())
    assert cfg["origins"] == site["chatbot"]["production_aliases"] + site["chatbot"]["previous_sites"]
    meta = real["docs"]["meta"]
    assert {k: v for k, v in meta.items() if k != "plan"} == chat_index.chat_meta(site)
    # the course planner's city values (site.json plan, pipeline/plan.py plan_meta): the hubs by name only (no hub is a
    # place record of the site) with the travel area site.json gives them, the engine's likes, the resident label
    # site.json gives (none: ''), the strict way without a car and the hubs' bus guides as site.json has them
    assert meta["plan"]["hubs"] == {h["key"]: {"name": h["name"], **({"region": h["region"]} if h.get("region") else {})}
                                    for h in site["plan"]["hubs"]}
    assert meta["plan"].get("transit_strict", False) == site["plan"].get("transit_strict", False)
    assert meta["plan"].get("hub_guides", []) == site["plan"].get("hub_guides", [])
    assert "islands" not in meta["plan"]["prefs"] and meta["plan"]["prefs"]["history"].startswith("역사·문화")
    assert meta["plan"]["resident"] == site["plan"].get("resident_label", "") and "tickets" not in real["docs"]
    # the short numbers of site.json emergency (this city lists 119·112·1330), none without one
    tels = [re.sub(r"[^\d+]", "", str(x.get("tel") or "")) for x in (site.get("emergency") or {}).get("lines") or []]
    assert meta["site"] == site["site_url"] and meta["site_name"] == site["site_name"] and meta["tel"] == tels
    assert real["docs"]["site"] == meta["site"]
    # the browser's part, in the page's language (else English)
    ko, de, xx = (chat_index.ui_config(site, x) for x in ("ko", "de", "xx"))
    # Korean pages carry the planner's hubs (key → name, site.json plan.hubs) for the planner's door (chat.js planQuery)
    assert ko == {"site": site["site_url"], "name": cfg["assistant"]["ko"], "region": site["region"], "chips": cfg["chips"]["ko"],
                  "hubs": {h["key"]: h["name"] for h in site["plan"]["hubs"]}}
    assert de["name"] == cfg["assistant"]["de"] and de["chips"] == cfg["chips"]["de"] and "hubs" not in de
    assert xx == chat_index.ui_config(site, "en")
    assert chat_index.ui_config(site, "zh-hant")["chips"] == cfg["chips"]["zh-Hant"]
    # the sample data (no chatbot object): its own region, no chips, no extra origin
    sample = json.loads((SAMPLE / "site.json").read_text("utf-8"))
    s = chat_index.chat_config(sample)
    assert s["region"] == {"ko": sample["region"], "en": sample["region_en"]}
    assert s["assistant"] == {"ko": f"{sample['region']} 여행 도우미", "en": f"{sample['region_en']} travel helper"}
    assert s["chips"] == {} and s["origins"] == []
    # an origin is https://host and nothing else; blank names and unknown languages are dropped
    odd = chat_index.chat_config({**site, "chatbot": {"production_aliases": ["https://Ok-1.example.com/", "http://x.example",
                                                                             "https://x.example/path", "javascript:1", 7],
                                                      "region_names": {"xx": "?", "ja": " "}, "chips": {"ko": ["", "  q  "], "xx": ["a"]}}})
    assert odd["origins"] == ["https://ok-1.example.com"] and odd["chips"] == {"ko": ["q"]}
    assert set(odd["region"]) == {"ko", "en"}


def test_emergency_numbers_when_the_site_lists_them():
    """site.json emergency (none on this site yet; the first city has one): one short catalog line without addresses,
    a doc with each number's source and 출처 확인, and the short numbers in meta.tel (the only short tel: links kept)."""
    S = _state(SAMPLE, "sample")
    assert not S.site.get("emergency")
    k = chat_index.Knowledge(S).build()
    assert not any("#emergency" in x for x in k.lines) and "/about/#emergency" not in k.docs and k.meta["tel"] == []
    S.site["emergency"] = {"checked_at": "2026-10-15", "sources": {"v": {"provider": "한국관광공사", "url": "https://x.example/e"}},
                           "lines": [{"tel": "119", "ko": "화재·구급", "src": "v"}, {"tel": "1330", "ko": "관광 통역",
                                                                               "abroad": "+82-2-1330", "src": "v"}],
                           "phrases": ["English please"]}
    k = chat_index.Knowledge(S).build()
    line = next(x for x in k.lines if x.startswith("S /about/#emergency"))
    assert "119 화재·구급" in line and "+82-2-1330" in line and "English please" in line and "http" not in line
    doc = k.docs["/about/#emergency"]
    assert doc["h"] == "긴급 연락처" and doc["x"].count("(출처 확인 2026-10-15)") == 2 and "https://x.example/e" in k.ext
    assert k.meta["tel"] == ["119", "1330"]


def test_english_twins_are_known_for_link_mapping(tmp_path):
    """With an English site (tests/fixtures/en_min), a doc carries its English path and name and every English path
    maps back to its key — the fallback order chatbot/knowledge.js uses (the language's page, else English, else
    Korean)."""
    from tests.test_en_site import en_min_data
    data = en_min_data(tmp_path / "data")
    S = _state(data)
    assert S.en is not None and S.en.places
    k = chat_index.Knowledge(S).build()
    d = k.docs_json()
    for p in S.en.places.values():
        doc = d["docs"][p["e"]["_path"]]
        assert doc["e"] == p["path"] and doc["l"]["en"] == p["path"] and doc["n"]["en"] == p["name"]
        assert d["alias"][p["path"]] == p["e"]["_path"]
        # the English name on the line where it is more than the Korean romanized (an attraction's English generic,
        # the provider's own title — CATALOG_BUDGET); the doc has it always (above)
        on_line = (p["e"]["kind"] == "attraction" or str(p["rec"].get("name_en_source", "")).startswith("TourAPI")) \
            and re.sub(r"[^a-z0-9]", "", p["name"].lower()) != re.sub(r"[^a-z0-9]", "", romanize(p["e"]["name"]).lower())
        assert (f"({p['name']})" in _lines(k.catalog())[p["e"]["_path"]]) == on_line, p["name"]
    for x in S.en.guides.values():
        assert d["docs"][x["g"]["_path"]]["e"] == x["path"]
    # sections open their guide's twin + anchor (chatbot/knowledge.js pathFor): no twin of their own
    assert all("l" not in v for key, v in d["docs"].items() if "#h-b" in key)


def test_no_tourapi_overview_text(real):
    blob = real["catalog"] + json.dumps(real["docs"], ensure_ascii=False)
    checked = 0
    for e in real["S"].entities_all:
        for text in ((e.get("tourapi") or {}).get("overview"), (e.get("original") or {}).get("text")):
            for sentence in re.split(r"(?<=[.!?다])\s+", re.sub(r"<[^>]+>", " ", str(text or ""))):
                sentence = sentence.strip()
                if len(sentence) >= 40:
                    checked += 1
                    assert sentence not in blob, (e["id"], sentence[:60])
    assert checked > 100


def test_outside_links_are_the_data_s_own_addresses(real):
    ext = set(real["docs"]["ext"])
    S = real["S"]
    assert all(u.startswith(("http://", "https://")) and not u.startswith(S.site_url) for u in ext)
    for v in S.videos:
        assert v["url"] in ext
    for link in S.site.get("official_links") or []:
        assert link["url"] in ext


def test_bytes_do_not_depend_on_the_build_date(real, tmp_path, monkeypatch):
    class Later(dt.date):
        @classmethod
        def today(cls):
            return cls(2031, 7, 1)
    monkeypatch.setattr(B, "dt", SimpleNamespace(date=Later, timedelta=dt.timedelta, datetime=dt.datetime))
    # a dated facility notice ends on its `until` day by design (pipeline/notices.py): read them as on the real build
    # day, so everything else is still checked for the build date leaking in
    real_active, real_day = B.notices.active, real["S"].today
    monkeypatch.setattr(B.notices, "active", lambda items, today: real_active(items, real_day))
    S = _state(CITY)
    assert S.today == "2031-07-01"
    chat_index.export(S, tmp_path)
    for name in ("catalog.txt", "docs.json", "index.json"):
        data = (tmp_path / "chat" / name).read_bytes()
        assert data == (real["dir"] / name).read_bytes(), name
        assert b"\r\n" not in data
    assert "2031" not in real["catalog"]


def test_catalog_token_budget(real):
    """The catalog stays within the operator's budget (CATALOG_BUDGET: 100K estimated tokens, 2026-10-17;
    estimate_tokens runs about a third under the real count). Measured 2026-10-17 on the production data (1,005 places):
    the public build's catalog 97,259 characters, 55,673 estimated (this test's state builds no English site, so its
    lines carry no English names: about 50.3K)."""
    est = real["stats"]["catalog_tokens_est"]
    assert est == chat_index.estimate_tokens(real["catalog"])
    assert est <= chat_index.CATALOG_BUDGET, f"catalog {est} estimated tokens > {chat_index.CATALOG_BUDGET}: shorten fields"
    assert chat_index.CATALOG_BUDGET <= 100_000   # the operator's ceiling (2026-10-17); not to be raised without them
    # every line is short enough to read: a long value is cut after an item, never mid-value
    for line in real["catalog"].splitlines():
        if line.startswith("P "):
            assert len(line) <= 300, line[:80]


def test_estimate_and_tokens():
    assert chat_index.estimate_tokens("가나다") == 3
    assert chat_index.estimate_tokens("abcde") == 2
    assert chat_index.estimate_tokens("누리공원 09:00") == 4 + 3   # 4 Hangul + ceil(6 ASCII / 2.5)
    # the same vector as tests/js/chat.test.js (chatbot/knowledge.js tokens)
    assert chat_index.tokens("누리섬 가는 법 Nuri 063-454-3337 a 江城 カフェ Ханбит café") == [
        "누리", "리섬", "가는", "법", "nuri", "063", "454", "3337", "江城", "カフ", "フェ", "ханбит", "café"]


def test_search_tokens_cover_names_and_menus_and_leave_out_web_addresses(real):
    idx, S = real["index"]["docs"], real["S"]
    for e in S.entities:
        head, body = (set(x.split()) for x in idx[e["_path"]])
        assert set(chat_index.tokens(e["name"])) <= head, e["id"]
        menu = (e.get("facts") or {}).get("menu")
        if menu:
            assert set(chat_index.tokens(menu)) <= head | body, e["id"]
    # source addresses are not words a reader searches for ('…/data/15050946/fileData.do')
    for key, (head, body) in idx.items():
        assert not ({"filedata", "15050946", "15012896"} & set(body.split())), key


def test_other_names_count_as_titles(real, monkeypatch):
    """A place's other names (the page lists them under its name): on its catalog line, in docs.json `a`, and as
    title words for search."""
    S = real["S"]
    e = dict(next(x for x in S.entities if x["kind"] == "attraction"))
    e["alternate_names"] = ["옛 이름 공원"]
    k = chat_index.Knowledge(S)
    line = k.place(e)
    assert " · 다른 이름 옛 이름 공원 | " in line
    assert k.docs[e["_path"]]["a"] == ["옛 이름 공원"] and "\n다른 이름: 옛 이름 공원\n" in k.docs[e["_path"]]["x"]
    head = set(k.index_json()["docs"][e["_path"]][0].split())
    assert set(chat_index.tokens("옛 이름 공원")) <= head


def test_the_build_writes_the_knowledge_in_every_mode(tmp_path):
    stats = build(SAMPLE, tmp_path / "out", "sample")
    chat = tmp_path / "out" / "chat"
    assert stats["chat"]["places"] == stats["entities"]
    assert all((chat / n).exists() for n in ("catalog.txt", "docs.json", "index.json"))
    docs = json.loads((chat / "docs.json").read_text("utf-8"))
    assert docs["site"] and docs["meta"]["site"] == docs["site"]


def test_validate_checks_the_knowledge(tmp_path, monkeypatch):
    """pipeline.validate chat_problems: the files are there in production, docs.json meta names this site_url, every
    catalog line's page is a doc; over the token budget is a warning (the price tier), not an error."""
    from pipeline import validate as V
    S = _state(SAMPLE, "sample")
    assert V.chat_problems(S, tmp_path, strict=True)[0] and V.chat_problems(S, tmp_path, strict=False) == ([], [])
    chat_index.export(S, tmp_path)
    assert V.chat_problems(S, tmp_path, strict=True) == ([], [])
    monkeypatch.setattr(chat_index, "CATALOG_BUDGET", 10)
    errors, warns = V.chat_problems(S, tmp_path, strict=True)
    assert errors == [] and len(warns) == 1 and "예산 10" in warns[0]
    assert V.chat_problems(S, tmp_path, strict=False) == ([], [])
    S.site_url = "https://elsewhere.example"
    assert any("meta.site" in e for e in V.chat_problems(S, tmp_path, strict=False)[0])


def test_abroad_items_are_in_the_knowledge(real):
    """Report 2026-10-17 D27: the assistant said the site had no Japanese travel piece while /abroad/ listed nine. Every
    published foreign article and post is a doc (kind abroad) with its original title, outlet or account, language,
    date and address; /abroad/ is a catalog line with the counts and a page listing every item, newest first."""
    S, docs = real["S"], real["docs"]["docs"]
    if not S.abroad:   # 2026-10-24: the city's unverified items were withdrawn — no abroad docs
        assert not any(k.startswith("abroad:") for k in docs)
        return
    line = _lines(real["catalog"])["/abroad/"]
    arts = [a for a in S.abroad if a["kind"] == "article"]
    # a reference work in another language (source_type reference — an encyclopedia entry, a heritage listing; QA
    # 2026-10-24 item 06) is counted and labelled apart: not a foreign outlet's piece
    refs = [a for a in arts if a.get("source_type") == "reference"]
    assert f"해외 기사 {len(arts) - len(refs)}건" in line and "search_site kind abroad" in line
    assert (f"외국어 참고자료(백과사전·세계유산 등재 문서) {len(refs)}건" in line) == bool(refs)
    for a in S.abroad:
        d = docs[f"abroad:{a['id']}"]
        assert d["k"] == "abroad" and d["u"] == "/abroad/" and f"원문 주소: {a['url']}" in d["x"]
        assert ("매체 기사가 아님" in d["x"]) == (a in refs)
        assert f"게시일: {a.get('date') or '모름'}" in d["x"] and f"언어: {a.get('lang') or '모름'}" in d["x"]
    ja = [a for a in arts if a.get("lang") == "ja"]
    if ja:
        newest = max(ja, key=lambda a: a.get("date") or "")
        title = " ".join(newest["title"].split())   # spaces normalised, as every doc line
        assert f"원문 제목(원문 그대로): {title}" in docs[f"abroad:{newest['id']}"]["x"]
        assert f"abroad:{newest['id']}" in docs["/abroad/"]["x"]


def test_a_long_guide_gives_each_place_and_its_faq_a_doc_of_their_own(real, tmp_path, monkeypatch):
    """QA 2026-10-17: asked for the bus back from the cable car, the assistant said the site had no way back — the bus
    guide's place reasons and FAQ came after the 6,000 characters get_pages reads. A guide doc that would pass
    GUIDE_DOC_FIT lists its places by name; each place's reason (with the place's link) and the FAQ are docs
    of their own, keyed by the page's own anchors (li#gi-<slug>, #h-faq). A short guide keeps everything in its doc.
    This city's guides are all short at GUIDE_DOC_FIT: the fit is lowered to 2,500 characters so they fall on both
    sides (1,700–3,200 characters of doc each)."""
    S = real["S"]
    monkeypatch.setattr(chat_index, "GUIDE_DOC_FIT", 2500)
    chat_index.export(S, tmp_path)
    docs = json.loads((tmp_path / "chat" / "docs.json").read_text("utf-8"))["docs"]
    split = short = 0
    for g in S.guides:
        d = docs[g["_path"]]
        assert len(d["x"]) <= chat_index.GUIDE_DOC_FIT + 400, g["id"]   # + the sources line
        places = [(S.ent_by_slug[it["place_slug"]], it) for it in g.get("items") or []
                  if it.get("place_slug") in S.ent_by_slug and it.get("reason")]
        if any(k.startswith(g["_path"] + "#gi-") for k in docs):
            split += 1
            for t, it in places:
                sub = docs[f"{g['_path']}#gi-{t['slug']}"]
                assert sub["k"] == "section" and sub["h"] == t["name"] and t["_path"] in sub["x"], (g["id"], t["slug"])
                assert t["name"] in d["x"]
            if any(f.get("q") for f in g.get("faq") or []):
                assert docs[g["_path"] + "#h-faq"]["x"].startswith("자주 묻는 질문")
        else:
            short += 1
            for t, _ in places:
                assert t["_path"] in d["x"], (g["id"], t["slug"])
    assert split and short


def test_service_notices_are_catalog_lines_with_their_post(real, tmp_path):
    """An official notice that belongs to no place page (data/<city>/service_notices.json, pipeline/notices.py) is a
    catalog line with its dates, our note and the post's address (kept as a link the answer may carry); a malformed
    entry is a validate finding."""
    from pipeline import notices
    S = real["S"]
    for n in S.service_notices:
        line = next(x for x in real["catalog"].splitlines() if x.startswith("N " + n["subject"]))
        assert n["url"] in line and notices.span(n)[0] in line and n["note"] in line
    bad = [{"id": "x", "kind": "gone", "subject": "앱", "note": "", "provider": "시", "url": "ftp://a", "checked_at": "2026-10-17",
            "date": "2026-13-01"}]
    found = notices.service_problems(bad)
    assert any("kind" in f for f in found) and any("note 없음" in f for f in found)
    assert any("ISO" in f for f in found) and any("url" in f for f in found)


def test_month_ranges_name_both_months_for_the_search():
    """'3~10월' was read as days of October in a Spanish answer (the first site's review 2026-10-17 L08): the chatbot's
    knowledge names both months; dates, times and ranges already named stay as they are."""
    assert chat_index.month_ranges("운영 기간 3~10월") == "운영 기간 3월~10월"
    assert chat_index.month_ranges("11 ~ 2월 휴장") == "11월~2월 휴장"
    for same in ("3월~10월", "2026.3~10월", "10-3~5월", "09:00~18:00", "1~2층"):
        assert chat_index.month_ranges(same) == same, same


def test_place_docs_carry_what_the_planner_checks_with(real):
    """f (Knowledge.plan_facts): the point, hours and closed days as each source writes them, the fee value read as a
    table (pipeline/fee_table.py) with the other sources' values beside it, the kind and type — chatbot/knowledge.js
    checkPlan and the course planner read these, never the page text."""
    docs = real["docs"]["docs"]
    by_title = {d["t"]: d for k, d in docs.items() if d["k"] == "place"}
    places = [d for d in docs.values() if d["k"] == "place"]
    assert all(d["f"]["kd"] in ("attraction", "food", "stay") for d in places)
    assert sum(1 for d in places if "g" in d["f"]) > 0.9 * len(places)
    fees = [d["f"]["fee"] for d in places if d["f"].get("fee")]
    tables = [f for f in fees if f.get("tab")]
    # a table: an adult's price the value itself writes, its source named
    assert tables and all("성인" in f["tab"] and f"{f['tab']['성인']:,}원" in f["t"].replace("\n", " ") and f["p"] for f in tables)
    # another source's differing value beside it (the planner checks against both); a free value is no table
    assert any(f.get("alt") and all(a["p"] and a["t"] for a in f["alt"]) for f in fees)
    assert any(f.get("free") is True and "tab" not in f for f in fees)
    # a value that reads as no table (a range, a programme's fees): its text and source only, 확인 필요 for a plan
    assert any(set(f) == {"t", "p"} for f in fees)
    # month ranges name both months ('3~10월' → '3월~10월', the form checkPlan reads a season by)
    assert not [x["t"] for d in places for x in d["f"].get("h", []) if chat_index.MONTH_RANGE.search(x["t"])]
    assert chat_index.month_ranges("3~10월 09:00~18:00 / 11~2월 09:00~17:00") == "3월~10월 09:00~18:00 / 11월~2월 09:00~17:00"
    assert any(x["t"] for d in places for x in d["f"].get("c", []))


def test_a_restaurant_carries_its_tourapi_class_so_a_plan_can_pick_a_cafe(real):
    """Operator 2026-10-18 ('점심이랑 카페도 일정에 넣어줘'): the source's category is the generic '음식점', so the
    catalog and the planner's facts (f.ty) read TourAPI's own class (schema.FOOD_LCLS) — a café stop needs a 카페·찻집·제과."""
    from pipeline.schema import CAFE_TYPES, FOOD_LCLS
    docs = real["docs"]["docs"]
    food = [(k, d) for k, d in docs.items() if d["k"] == "place" and d["f"]["kd"] == "food"]
    assert food and all(d["f"].get("ty") in FOOD_LCLS.values() for _, d in food)
    cafes = [(k, d) for k, d in food if d["f"]["ty"] in CAFE_TYPES]
    assert len(cafes) >= 5      # 6 of this city's 56 restaurants (2026-10-24)
    for path, d in cafes:       # the catalog line names the class the planner picks a café by
        assert re.search(rf"^P {re.escape(path)} \| {re.escape(d['t'])}(?: \([^)]*\))? \| {d['f']['ty']}(?: \||$)",
                         real["catalog"], re.M), d["t"]


def by_title(docs, title):
    return next(d for d in docs.values() if d["k"] == "place" and d["t"] == title)


def test_lines_json_holds_every_place_s_full_line_with_every_first_screen_fact(real):
    """lines.json (the first site's catalog diet, 41ac859b5): every place's full line, keyed by its page path, in the
    catalog's order as core — the catalog's short line keeps only CATALOG_SLOTS, the full line every hero slot (hours,
    parking, phone …) exactly as the first screen gives it, both values where sources differ; under LINES_BUDGET."""
    S, docs, L = real["S"], real["docs"]["docs"], real["lines"]
    full, catalog = L["lines"], _lines(real["catalog"])
    assert L["v"] == chat_index.VERSION and set(full) == {e["_path"] for e in S.entities}
    assert L["core"] == [p for p, line in catalog.items() if line.startswith("P ")]
    assert all(k in docs for k in full)
    longer = 0
    for e in S.entities:
        line = full[e["_path"]]
        assert line.startswith(f"P {e['_path']} | {e['name']}"), line
        slots = present.key_facts(e, "hero")["slots"]
        assert chat_index.month_ranges("; ".join(chat_index._slot_text(x) for x in slots)) in line or not slots, line
        longer += len(line) > len(catalog[e["_path"]])
    assert longer > len(S.entities) // 2    # most places have more facts than their short catalog line shows
    assert real["stats"]["lines"] == len(full) and real["stats"]["lines_tokens_est"] == chat_index.lines_tokens(full)
    assert chat_index.lines_tokens(full) < chat_index.LINES_BUDGET
    # the catalog's header says where the full lines come from
    assert 'site_data block whose source is "lines"' in real["catalog"]



def test_event_lines_carry_the_newest_hours_and_phone(real):
    """The paid check of 2026-10-24: asked for this weekend's events, the model answered from the catalog alone and
    called the hours and the phone '사이트에 없음' — the newest edition's hours and phone are on the event's line."""
    lines = _lines(real["catalog"])
    timed = 0
    for sr in real["S"].series:
        ev, line = sr["newest"], lines[sr["_path"]]
        if ev.get("playtime"):
            timed += 1
            assert f" · 시간 {chat_index._cap(chat_index._clean(ev['playtime']), chat_index.SLOT_MAX)}" in line, line
        if ev.get("tel"):
            assert f" · 문의 {chat_index._clean(ev['tel'])}" in line, line
    assert timed >= 1


def test_a_guide_names_both_values_of_a_place_whose_sources_differ(real):
    """The paid check of 2026-10-24: through the rainy-day guide the answer gave 소수박물관's TourAPI hours alone — a
    guide's reason was written from one source, so a place whose first-screen facts differ by source has both values,
    with their providers and the call line, beside its reason in the guide's doc (or its own section doc)."""
    S, docs = real["S"], real["docs"]["docs"]
    seen = 0
    for g in S.guides:
        for it in g.get("items") or []:
            t = S.ent_by_slug.get(it.get("place_slug") or "")
            differ = [x for x in present.key_facts(t, "hero")["slots"] if x.get("conflict")] if t else []
            if not differ:
                continue
            seen += 1
            text = docs.get(f"{g['_path']}#gi-{t['slug']}", docs[g["_path"]])["x"]
            for x in differ:
                assert chat_index.month_ranges(chat_index._slot_text(x)) in text, (g["id"], t["slug"])
                for v in x["vals"]:
                    assert v["provider"] in text
            assert "출처마다 값이 달라 방문 전 전화 확인" in text
    assert seen >= 1
