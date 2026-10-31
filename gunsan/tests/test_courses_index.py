"""The courses page as cards (operator 2026-10-31: '이런 곳들 UI도 좀 더 고도화할 방안 없나?' with a capture of the text-only
rows): present.route_band / route_rows / course_regions / course_cover / stops_range / course_card / course_index_vm,
en_site Site.course_index, templates/_courses.html.j2, css/79-courses.css, locales.COURSES_WORDS.

A card shows one stop's licensed TourAPI photo (KOGL-1/3, the first stop whose photo no earlier card shows), the length or
theme chip, the name as the card's one link, a route band (the first three stops, '외 n곳', the last), the 권역 it passes
through, its figures from data only (stops, the straight-line sum only when every leg is measured, the source's time, the
busiest closed day) and its source — never the internal '좌표 있는 구간 n/m'. Every version gets the same markup."""
import re
from html import unescape
from pathlib import Path

import pytest

from pipeline import build as B
from pipeline import en_site, present
from pipeline import locales as LC

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"
HANGUL = re.compile(r"[가-힣]")


def stops(n, extra=None):
    return [{"n": i, "name": f"S{i}", "short": f"S{i}", "t": None, **(extra or {}).get(i, {})} for i in range(1, n + 1)]


# ---------------------------------------------------------------- the route band
def test_route_band_names_the_first_three_and_the_last():
    for n in range(1, 6):   # up to ROUTE_HEAD + 2: every stop (a '외 1곳' row would take a stop's room)
        shown, more = present.route_band(stops(n))
        assert [s["n"] for s in shown] == list(range(1, n + 1)) and more == 0
    shown, more = present.route_band(stops(10))
    assert [s["n"] for s in shown] == [1, 2, 3, 10] and more == 6
    rows = present.route_rows(stops(10, {10: {"optional": True}}), lambda s: s["short"], lambda k: f"외 {k}곳")
    assert [r.get("name") or r["text"] for r in rows] == ["S1", "S2", "S3", "외 6곳", "S10"]
    assert [r["pos"] for r in rows if not r["more"]] == ["a", "", "", "z"]
    assert [r["opt"] for r in rows if not r["more"]] == [False, False, False, True]   # 어청도 (선택사항)
    assert [r["pos"] for r in present.route_rows(stops(1), lambda s: s["short"], str)] == ["a"]


def test_regions_in_order_of_first_appearance_without_unknown():
    t = lambda r: {"_region": r}
    places = [t("원도심"), None, t(present.NONE_LABEL), t("새만금·비응"), t("원도심"), t("고군산"), t(present.FAR_LABEL)]
    assert present.course_regions(places) == ["원도심", "새만금·비응", "고군산", present.FAR_LABEL]
    assert present.course_regions([None, t(present.NONE_LABEL)]) == []


def test_cover_skips_a_place_an_earlier_card_shows_and_falls_back_to_the_first():
    a, b = {"id": "a"}, {"id": "b"}
    ss = [{"n": 1, "t": a}, {"n": 2, "t": None}, {"n": 3, "t": b}]
    ph = {"a": {"url": "A"}, "b": {"url": "B"}}
    of = lambda s: ph.get(s["t"]["id"])
    used = set()
    assert present.course_cover(ss, used, of) == (ss[0], ph["a"]) and used == {"a"}
    assert present.course_cover(ss, used, of) == (ss[2], ph["b"]) and used == {"a", "b"}
    assert present.course_cover(ss, used, of) == (ss[0], ph["a"])        # every one shown: the first stop's photo
    assert present.course_cover(ss, set(), lambda s: None) == (None, None)


def test_stops_range_and_words_of_every_version():
    w = lambda key, n=None, **kw: LC.courses_word("ko", key, n, **kw)
    assert present.stops_range([8, 11, 10], w) == "경유지 8~11곳" and present.stops_range([20], w) == "경유지 20곳"
    assert present.stops_range([], w) == ""
    ru = lambda key, n=None, **kw: LC.courses_word("ru", key, n, **kw)
    assert ru("range", 11, a=8) == "8–11 пунктов маршрута" and ru("range_one", 22) == "22 пункта маршрута"
    assert LC.courses_word("en", "range_one", 1) == "1 stop"
    keys = set(LC.COURSES_WORDS["ko"])
    assert set(LC.COURSES_WORDS) == {"ko", *LC.ORDER}
    for code, words in LC.COURSES_WORDS.items():
        assert set(words) == keys, code
        for k, v in words.items():
            if isinstance(v, dict):
                assert set(v) == set(LC.LOCALES[code].plural), (code, k)
        assert not any("좌표 있는 구간" in str(v) for v in words.values())
        if code != "ko":
            assert not HANGUL.search(str(words)), code


# ---------------------------------------------------------------- the view model on 군산각's data
@pytest.fixture(scope="module")
def S():
    return B.State(GUNSAN, "production")


def test_index_cards_come_from_the_course_data(S):
    CV = present.course_index_vm(S)
    cards = [k for g in CV["groups"] for k in g["cards"]]
    assert sorted(k["id"] for k in cards) == sorted(c["id"] for c in S.courses)        # every course, once
    assert [g["title"] for g in CV["groups"][:3]] == ["당일", "1박 2일", "2박 3일"]
    assert [g["heading"] for g in CV["groups"][:3]] == ["당일 코스", "1박 2일 코스", "2박 3일 코스"]
    by_id = {cv["c"]["id"]: cv for cv in S.course_vms.values()}
    used = set()
    for k in cards:
        cv = by_id[k["id"]]
        assert k["path"] == cv["path"] and k["chip"] == (cv["duration"] or cv["group"])
        shown = [r for r in k["rows"] if not r["more"]]
        assert shown[0]["n"] == 1 and shown[-1]["n"] == cv["n_places"]
        assert sum(r["n"] for r in k["rows"] if r["more"]) + len(shown) == cv["n_places"]
        assert present.NONE_LABEL not in k["areas"]
        facts = {f["k"]: f["v"] for f in k["facts"]}
        assert facts["경유지"] == f"{cv['n_places']}곳"
        assert ("직선 합" in facts) == bool(cv["complete"] and cv["measured"])
        assert ("소요시간" in facts) == bool(cv["taketime"])
        assert facts.get("쉬는 날", "") == cv["closed_note"]
        assert not any("좌표 있는 구간" in str(v) for v in k.values())
        # the photo: a licensed TourAPI photo of the first stop no earlier card shows (else the first with a photo)
        with_photo = [s for s in cv["stops"] if s["t"] and s["t"].get("_photos")]
        if not with_photo:
            assert k["photo"] is None
            continue
        pick = next((s for s in with_photo if s["t"]["id"] not in used), with_photo[0])
        used.add(pick["t"]["id"])
        assert k["photo"] is pick["t"]["_photos"][0] and k["photo"]["type"] in (1, 3)
        assert k["photo"]["url"].startswith("https://tong.visitkorea.or.kr/")
        assert k["photo_cap"] == f"사진: {pick['t']['name']}" and k["credit"] == "출처: 한국관광공사"
    # seven courses start at the same museum: the page does not show its photo seven times
    shown_places = [k["photo_cap"] for k in cards if k["photo"]]
    assert len(set(shown_places)) >= len(shown_places) - 2
    assert CV["lics"] and all(lab.startswith("공공누리 제") for lab in CV["lics"])


# ---------------------------------------------------------------- the pages
@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("courses")
    S = B.State(GUNSAN, "production")
    S.intl = en_site.load_all(S, GUNSAN)
    env = B.make_env()
    env.globals["kakao_sdk"] = B.kakao_sdk_url(S.site)
    path = "/courses/"
    page = B._simple_page(S, path, "코스", "코스", [("홈", S.site_url + "/"), ("여행 코스", S.abs(path))])
    B._render(env, S, out, "courses_index.html.j2", path, page, "courses", None, groups=B.course_groups(S.courses),
              CV=present.course_index_vm(S))
    for code in ("en", "ru"):
        en_site.Pages(S.intl.sites[code], env, out, S.intl).courses()
    return {"out": out, "S": S}


def _main(html: str) -> str:
    return html[html.index("<main"):html.index("</main>")]


def test_korean_page_shows_a_card_per_course(pages):
    S, html = pages["S"], (pages["out"] / "courses" / "index.html").read_text("utf-8")
    main = _main(html)
    n = len(S.courses)
    assert main.count('<li class="cc') == n and main.count('class="cc-route"') == n
    assert main.count('data-track="course_click"') == n
    for c in S.courses:
        assert f'<a href="{c["_path"]}" data-track="course_click">' in main
    # motion: the cards are reveal tiles, the band draws (motion.js; below the first screen only); no line rows left
    assert main.count("data-reveal") == n and main.count("data-draw") == n and "line-row" not in main
    text = " ".join(unescape(re.sub(r"<[^>]+>", " ", main)).split())
    assert "좌표 있는 구간" not in text
    assert "좌표 출처는 코스마다 표시" in text                       # the straight-line note (tests/test_round3_index)
    assert "사진 출처: 한국관광공사" in text and "지나는 권역" in text and "군산시 문화관광 공식 코스" in text
    # every group pill points at its section
    nav = re.search(r'<nav class="cc-nav"[^>]*>.*?</nav>', main, re.S).group(0)
    gids = re.findall(r'href="#([^"]+)"', nav)
    assert len(gids) == len(present.course_groups_vm(S)) and all(f'<section class="cc-sec" id="{g}"' in main for g in gids)
    # a KOGL-3 photo keeps its class (the img.t3 guard keeps it whole) and only KOGL-1 zooms on hover
    for box, cls in re.findall(r'<div class="cc-media t(\d)">.*?<img[^>]*class="(t\d)[^"]*"', main, re.S):
        assert cls == f"t{box}"
    css = (ROOT / "templates" / "assets" / "css" / "79-courses.css").read_text("utf-8")
    assert "scale(1.04)" in css and not re.search(r"t3[^{]*\{[^}]*(transform|scale)", css)


def test_every_version_gets_the_same_cards_in_its_words(pages):
    S, out = pages["S"], pages["out"]
    for code in ("en", "ru"):
        site = S.intl.sites[code]
        main = _main((out / code / "courses" / "index.html").read_text("utf-8"))
        n = len(site.courses)
        assert main.count('<li class="cc') == n and main.count('class="cc-route"') == n, code
        text = " ".join(unescape(re.sub(r"<[^>]+>", " ", main)).split())
        assert not HANGUL.search(text), code
        w = LC.COURSES_WORDS[code]
        assert w["areas"] in text and w["note_line"] in text, code
        assert re.search(r'<li class="cr cr-a" value="1"><i class="tn">1</i><span class="cr-nm">[^<]+</span>', main), code
        assert '<span class="cr-nm"></span>' not in main, code      # a stop whose name is missing: the place's name
