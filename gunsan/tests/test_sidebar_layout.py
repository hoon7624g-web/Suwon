"""The tab panel (operator 2026-10-31 '적용하자': the approved layout after travel.webforai.kr; templates/_side.html.j2,
base.html.j2, en/_chrome.html.j2, css/80-side.css, present.side_vm, en_site Pages.side, locales.SIDE_WORDS) and
날씨각's weather module (assets/weather.js, the same day).

From 1200px the header is a panel at the left: wordmark, language menu, site search, the day card (weather, sunrise ·
sunset, next event), the two actions and the tab groups — every link of the old bar's nav in one of them, in the panel
and in the phone menu alike; the page's group open and its link aria-current; the panel never covers the page, stays
while the page scrolls and scrolls inside itself; nothing scrolls sideways at 360–1440px; the phone bar stays ≤ 15% of
the screen and its menu opens without JavaScript; the other versions carry the same groups in their own words. The
weather card — 날씨각's own first-screen card (operator 2026-10-31 '날씨각 실제 디자인으로'; 날씨각 is the operator's: no
source words in any version) — holds no value in the HTML, asks after the page has loaded, is drawn from the feed and
the day's slots in its kept room (nothing moves), shows 날씨각's Korean words only on Korean pages, is one link to
weather.o2o.kr, and leaves that link when an answer fails or JS is off. Browser checks: Playwright + Chromium (skipped
where missing), every request answered here."""
import json
import mimetypes
import re
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline import locales as LC
from pipeline.build import build
from conftest import feed_answer, route_weather, weather_answer

ROOT = Path(__file__).resolve().parent.parent
DATA, SAMPLE = ROOT / "data" / "gunsan", ROOT / "data" / "sample"
HANGUL = re.compile(r"[가-힣]")
# the words 'source' and the service's name, in every version (operator 2026-10-31 '출처: 날씨각 표기 필요없어 우리 회사 거야')
SOURCE = re.compile(r"날씨각|Nalssigak|출처|[Ss]ource|Quelle|Fuente|Источник|出典|来源|來源")
PLACE = "/places/이성당/"
PAGES = ("/", PLACE, "/food/", "/guides/", "/courses/", "/map/", "/plan/", "/abroad/", "/events/", "/sun/", "/en/", "/ja/")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    import os
    if os.environ.get("SIDE_BUILT"):   # a preview build of data/gunsan made with this code (a quicker local rerun)
        return Path(os.environ["SIDE_BUILT"])
    out = tmp_path_factory.mktemp("side") / "preview"
    build(DATA, out, "preview")
    return out


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    out = tmp_path_factory.mktemp("side") / "sample"
    build(SAMPLE, out, "sample")
    return out


def page_html(out: Path, path: str) -> str:
    return (out / unquote(path).strip("/") / "index.html").read_text("utf-8")


def block(html: str, start: str, end: str = "</nav>") -> str:
    i = html.index(start)
    return html[i:html.index(end, i)]


def hrefs(fragment: str) -> list[str]:
    return [unquote(h) for h in re.findall(r'<a [^>]*href="([^"#]+)"', fragment)]


def side_nav(html: str) -> str:
    return block(html, '<nav class="side-nav"')


def menu_panel(html: str) -> str:
    return block(html, '<nav class="menu-panel"', "</details>\n  </div>")


# ------------------------------------------------------------------ the markup
def test_every_main_nav_link_is_in_the_panel_and_the_phone_menu(built):
    """Nothing of the old bar is lost: the footer's 둘러보기 is the main nav (nav_items), and every one of its links —
    plus 소개·출처, the timetables and the planner — is in the panel's groups and in the phone menu's, each a page of
    this build; the counts are the ones the lists show."""
    home = page_html(built, "/")
    nav = [h for h in hrefs(block(home, '<nav class="foot-col foot-nav"')) if h != "/search/"]
    assert len(nav) == 11 and "/blog/" in nav and "/abroad/" in nav
    want = [*nav, "/about/", "/sun/", "/transport/"]
    for path in PAGES[:10]:
        html = page_html(built, path)
        side, menu = side_nav(html), menu_panel(html)
        for h in want:
            assert h in hrefs(side), (path, h)
            assert h in hrefs(menu), (path, h)
        acts = block(html, '<div class="side">', '<nav class="side-nav"')
        assert re.search(r'<a class="sd-act is-pri" href="/plan/"[^>]* data-track="plan_cta">', acts), path
        assert re.search(r'<a class="sd-act" href="/courses/"[^>]* data-track="course_click">', acts), path
        for h in set(hrefs(side)):
            assert (built / h.strip("/") / "index.html").is_file(), h
    # the groups, in the approved order, and the counts the list pages print
    labels = re.findall(r'<span class="sg-t">([^<]+)</span>', side_nav(home))
    assert labels == ["찾기", "여행 계획", "행사 달력", "읽을거리", "해외에서 본 군산", "소개·출처"]
    for path in ("/places/", "/food/", "/stays/"):
        n = re.search(r'class="count tn">(\d+)곳', page_html(built, path)).group(1)
        assert f'href="{path}"><span class="sg-n">' in side_nav(home)
        assert re.search(rf'href="{path}"><span class="sg-n">[^<]+</span><span class="sg-c tn">{n}곳</span>', side_nav(home)), path
    assert re.findall(r'<span class="sg-n">([^<]+)</span>', block(side_nav(home), "여행 계획</span>", "</ul>")) == [
        "코스", "가이드", "지도", "가는 법·시간표", "해 뜨고 지는 시각"]
    # the panel is the header (a nav landmark with its name), after the skip link; the page's main is untouched
    assert home.index('<a class="skip-link" href="#main-content">') < home.index('<header class="mast"') < home.index(
        '<nav class="side-nav" aria-label="주 메뉴">') < home.index('<main id="main-content"')
    assert home.count('<main id="main-content"') == 1 and "side-nav" not in home[home.index("<main"):home.index("</main>")]


def test_the_pages_group_is_open_and_its_link_current(built):
    def _groups(nav):
        out = {}
        for li in nav.split('<li class="sg')[1:]:   # one piece per group (its links' <li> carry no class)
            lab = re.search(r'<span class="sg-t">([^<]+)</span>', li).group(1)
            out[lab] = {"open": '<details class="sg-d" open>' in li, "cur": li.startswith(' is-cur"'),
                        "current": re.findall(r'href="([^"]+)" aria-current="page"', li)}
        return out

    home = _groups(side_nav(page_html(built, "/")))
    assert home["찾기"]["open"] and home["여행 계획"]["open"] and not home["읽을거리"]["open"]   # no page: 찾기 · 여행 계획
    assert all(not g["current"] for g in home.values())
    place = _groups(side_nav(page_html(built, PLACE)))   # 이성당 is a restaurant: 찾기 › 음식점
    assert place["찾기"]["open"] and place["찾기"]["cur"] and [unquote(h) for h in place["찾기"]["current"]] == ["/food/"]
    assert not place["여행 계획"]["open"] and not place["읽을거리"]["open"]
    sun = _groups(side_nav(page_html(built, "/sun/")))
    assert sun["여행 계획"]["open"] and sun["여행 계획"]["current"] == ["/sun/"] and not sun["찾기"]["open"]
    events = page_html(built, "/events/")
    assert '<a class="sg-s sg-1" href="/events/" aria-current="page">' in side_nav(events)
    blog = _groups(side_nav(page_html(built, "/blog/")))
    assert blog["읽을거리"]["open"] and blog["읽을거리"]["current"] == ["/blog/"]
    # the phone menu marks the same page
    assert 'href="/food/" aria-current="page"' in menu_panel(page_html(built, PLACE))


def test_the_other_versions_carry_the_groups_in_their_words(built):
    """Every version: the same groups (Find · Plan · Events calendar · Read · About and sources), in its words
    (locales.SIDE_WORDS — every version has every key, or it would not build), linking its own pages; the Korean-only
    pages (/plan/, the map, /abroad/, the blog, videos, the timetables) are not there; no Hangul in the panel."""
    assert set(LC.SIDE_WORDS) == {"ko", *LC.ORDER}
    for code, words in LC.SIDE_WORDS.items():
        assert set(LC.SIDE_KEYS) <= set(words), code
        assert {"sun", "sun_cloud", "cloud", "rain", "snow", "moon"} <= set(words["sky"]), code
        assert set(words["wx_slots"]) == {"morning", "day", "sunset", "night", "now"} and all(words["wx_slots"].values()), code
        assert "{r}" in words["wx_title"] and "{r}" in words["wx_go"] and "{t}" in words["wx_feels"] and "{p}" in words["wx_hum"], code
        assert words["wx_more"] and words["wx_score"], code
        wx = json.dumps({k: v for k, v in words.items() if k.startswith("wx_") or k == "sky"}, ensure_ascii=False)
        assert not SOURCE.search(wx), (code, wx)
        if code != "ko":
            assert not HANGUL.search(wx), code
    for code in LC.ORDER:
        loc, W = LC.get(code), LC.SIDE_WORDS[code]
        html = page_html(built, f"/{code}/")
        side = side_nav(html)
        labels = re.findall(r'<span class="sg-t">([^<]+)</span>', side)
        assert labels[:4] == [W["find"], W["plan"], W["events"], W["read"]], code
        assert all(h.startswith(f"/{code}/") for h in hrefs(side)), code
        for seg in ("places/", "food/", "stays/", "courses/", "guides/", "events/", "columns/", "about/"):
            assert f"/{code}/{seg}" in hrefs(side) and f"/{code}/{seg}" in hrefs(menu_panel(html)), (code, seg)
        nav = [h for h in hrefs(block(html, '<nav class="foot-col foot-nav"')) if h.startswith(f"/{code}/")]
        assert set(nav) <= set(hrefs(side)), code
        panel = block(html, '<div class="side">', "</header>")
        assert not HANGUL.search(re.sub(r"<[^>]+>", " ", panel)), code
        assert "/plan/" not in panel and "/map/" not in panel and "/sun/" not in panel and "sd-acts" not in panel
        assert '<nav class="side-nav" aria-label="' in html
        # a place page: its list's tab is current, its group open
        place = next((built / code / "places").glob("*/index.html")).read_text("utf-8")
        assert re.search(rf'<details class="sg-d" open>.*?href="/{code}/(?:places|food|stays)/" aria-current="page"',
                         side_nav(place), re.S), code


def test_the_weather_module_holds_no_value_in_the_html(built):
    """날씨각's card (operator 2026-10-31): the panel's (every page) and the home's (under the first screen) carry the two
    API addresses (the feed, the day's slots), the words and the link to weather.o2o.kr ('군산 날씨 보기' — no source
    words, in no version) — never a temperature, a score or a sentence of 날씨각's: the page is static and would grow
    stale. Nor does anything else the build writes (llms.txt, the chat's files)."""
    for path in ("/", PLACE, "/en/", "/ja/"):
        html = page_html(built, path)
        mods = re.findall(r'<div class="wx wx-(side|home) wx-(ko|intl)" data-wx="([^"]+)" data-wx-day="([^"]+)" '
                          r'data-wx-w="([^"]+)">(.*?data-wx-go>.*?</a>)', html, re.S)
        assert [m[0] for m in mods] == (["side", "home"] if path in ("/", "/en/", "/ja/") else ["side"]), path
        code = path.strip("/").split("/")[0] if path.startswith(("/en/", "/ja/")) else "ko"
        for kind, lang, feed, api, words, inner in mods:
            assert feed == "https://weather.o2o.kr/v1/feed?region=5213000000"
            assert api == "https://weather.o2o.kr/v1/weather/today?region=5213000000"
            assert lang == ("ko" if path in ("/", PLACE) else "intl")
            w = json.loads(unescape(words))
            assert w["ko"] is (lang == "ko") and w["slots"] == LC.SIDE_WORDS[code]["wx_slots"] and w["lang"]
            assert "°" not in inner and "%" not in inner and "지금은" not in inner, (path, inner)
            assert '<a class="wx-go" href="https://weather.o2o.kr/" rel="noopener" data-wx-go>' in inner
            assert not SOURCE.search(unescape(inner) + unescape(words)), (path, inner)
        region = "군산" if code == "ko" else LC.get(code).city if code != "en" else "Gunsan"
        assert LC.SIDE_WORDS[code]["wx_go"].format(r=region) in unescape(html), path
    for f in ("llms.txt", "llms-full.txt"):
        if (built / f).exists():
            assert "weather.o2o.kr" not in (built / f).read_text("utf-8"), f
    home = page_html(built, "/")
    assert "weather.js" not in home   # attached by site.js after load, never in the HTML
    # 날씨각's icons go out with the build (copied from 날씨각, small webp)
    for ic in ("sun", "sun_cloud", "cloud", "rain", "snow", "moon"):
        f = built / "assets" / "wx" / f"{ic}.webp"
        assert f.is_file() and f.stat().st_size < 6000, ic


def test_the_sample_build_keeps_its_menu(sample):
    """A build without the other versions, timetables or blog: the panel has what this build writes."""
    html = page_html(sample, "/")
    side = side_nav(html)
    assert set(hrefs(side)) == {"/places/", "/food/", "/stays/", "/courses/", "/guides/", "/map/", "/events/", "/about/"}
    assert "/sun/" not in html.split("<main")[0] and "lang-menu" not in html.split("<main")[0]


# ------------------------------------------------------------------ in a browser
sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error as err:
            pytest.skip(f"Chromium is not installed for Playwright: {err}")
        yield b
        b.close()


def open_page(browser, out: Path, path: str, width: int, height: int = 900, js: bool = True, weather="ok",
              reduce: bool = False):
    """A context serving the build at http://site.test (everything else refused), 날씨각 answered (weather='ok'),
    refused ('fail') or late ('slow': never answered in the test's time). Returns (ctx, page, errors, wx_calls)."""
    calls: list[str] = []

    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        p = unquote(urlsplit(url).path)
        f = out / p.strip("/")
        f = f / "index.html" if p.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    ctx = browser.new_context(viewport={"width": width, "height": height}, java_script_enabled=js, locale="ko-KR",
                              is_mobile=width < 600, has_touch=width < 1024,
                              reduced_motion="reduce" if reduce else "no-preference")
    ctx.route("**/*", serve)
    if weather == "ok":
        route_weather(ctx)
    ctx.on("request", lambda r: calls.append(r.url) if "weather.o2o.kr" in r.url else None)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script("""window.__ls = []; new PerformanceObserver(l => { for (const e of l.getEntries())
      if (!e.hadRecentInput) window.__ls.push({v: e.value, src: (e.sources || []).map(s => s.node && s.node.className || '')}); })
      .observe({type: 'layout-shift', buffered: true});
      const f = window.fetch; window.__wx = [];
      window.fetch = function (u) { if (String(u).indexOf('weather.o2o.kr') > -1) window.__wx.push(document.readyState); return f.apply(this, arguments); };""")
    page.goto("http://site.test" + path, wait_until="load")
    return ctx, page, errors, calls


def own(errors: list[str]) -> list[str]:
    """The page's own errors: a refused outside request (a picture from another host: everything outside the build is
    refused here) logs 'Failed to load resource' — the browser's line, not the page's."""
    return [e for e in errors if not e.startswith("Failed to load resource")]


GEOM = """() => { const m = document.querySelector('.mast').getBoundingClientRect(), main = document.querySelector('main');
  const r = main.getBoundingClientRect(), cs = getComputedStyle(document.querySelector('.mast'));
  return {mL: m.left, mR: m.right, mT: m.top, mB: m.bottom, mainL: r.left, pos: cs.position, vw: innerWidth, vh: innerHeight,
          over: document.documentElement.scrollWidth - innerWidth,
          scroll: document.querySelector('.mast').scrollHeight > document.querySelector('.mast').clientHeight}; }"""


def test_on_a_wide_screen_the_panel_stays_at_the_left_and_never_covers_the_page(browser, built):
    for path in ("/", PLACE, "/food/", "/en/"):
        ctx, page, errors, _ = open_page(browser, built, path, 1440)
        g = page.evaluate(GEOM)
        assert g["pos"] == "fixed" and g["mL"] == 16 and g["mT"] == 16 and g["mB"] == 900 - 16, (path, g)
        assert g["mR"] + 16 <= g["mainL"] and g["over"] == 0, (path, g)
        # nothing of the page sits under the panel: the point right of it is the page's, the panel's is the panel's
        for y in (100, 450, 850):
            assert page.evaluate(f"!!document.elementFromPoint({g['mR'] + 8}, {y}).closest('.mast')") is False, (path, y)
        # it stays while the page scrolls, and scrolls inside itself when taller than the window (Lenis leaves it be)
        page.mouse.wheel(0, 2400)
        page.wait_for_timeout(600)
        assert page.evaluate("scrollY") > 0 and page.evaluate(GEOM)["mT"] == 16, path
        assert page.get_attribute(".mast", "data-lenis-prevent") is not None
        if g["scroll"]:
            page.mouse.move(150, 600)
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(500)
            assert page.evaluate("document.querySelector('.mast').scrollTop") > 0, path
        # the bar's own buttons step back; the search field and the language menu are in the panel
        assert page.locator(".mast #hs-q").is_visible() and page.locator(".mast-search").is_hidden()
        assert page.locator(".menu > summary").is_hidden() and page.locator(".side-nav").is_visible()
        assert own(errors) == [], (path, errors)
        ctx.close()
    # a page's local bar sticks at the column's top, right of the panel
    ctx, page, errors, _ = open_page(browser, built, PLACE, 1440)
    page.mouse.wheel(0, 1600)
    page.wait_for_timeout(600)
    bar = page.locator(".lnav").bounding_box()
    assert bar["y"] == 0 and bar["x"] >= 320 - 0.5, bar
    ctx.close()


def test_tab_order_is_the_order_on_screen(browser, built):
    """The skip link first; then the panel top to bottom (wordmark, language, search, the day card, the actions, the
    groups), then the page."""
    ctx, page, errors, _ = open_page(browser, built, "/", 1440)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    seen = []
    for _ in range(14):
        page.keyboard.press("Tab")
        seen.append(page.evaluate("""(() => { const e = document.activeElement, r = e.getBoundingClientRect();
          return [e.className || e.tagName, Math.round(r.top), !!e.closest('.mast')]; })()"""))
    inside = [s for s in seen if s[2]]
    assert len(inside) >= 10 and [s[1] for s in inside] == sorted(s[1] for s in inside), seen
    assert inside[0][0] == "wordmark" and inside[1][0] == "lang-btn" and seen.index(inside[-1]) == len(inside) - 1, seen
    ctx.close()


@pytest.mark.parametrize("width", (360, 390))
def test_on_a_phone_the_bar_stays_small_and_its_menu_opens_without_js(browser, built, width):
    for js in (True, False):
        ctx, page, errors, calls = open_page(browser, built, PLACE, width, 844, js=js)
        bar = page.locator(".mast").bounding_box()
        assert bar["height"] == 52 and bar["height"] / 844 <= 0.15 and page.locator(".side").is_hidden()
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        page.click(".menu > summary")
        panel = page.locator(".menu-panel")
        assert panel.is_visible()
        # the same groups: 찾기 open with 음식점 current, the others folded until pressed
        assert page.locator('.menu-panel a[href="/food/"][aria-current="page"]').is_visible()
        folded = page.locator(".menu-panel .sg-d:not([open]) > summary").first
        folded.click(force=not js)   # without JS Playwright's own wait for a still element never ends
        assert page.locator(".menu-panel .sg-d[open]").count() >= 2
        for sel in (".menu-panel .sg-a", ".menu-panel .sg-s", ".menu-panel .sd-act"):
            box = page.locator(sel).first.bounding_box()
            assert box["height"] >= 44 and box["x"] >= 0 and box["x"] + box["width"] <= width, sel
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert calls == []   # the panel's weather module is not on a phone's screen: nothing is asked
        if js:               # …nor is its script fetched (a phone page without the home's module)
            page.wait_for_timeout(2600)
            assert not page.evaluate("[...document.scripts].some(s => s.src.endsWith('/weather.js'))")
        assert own(errors) == [], errors
        ctx.close()


def test_nothing_scrolls_sideways(browser, built):
    for width in (360, 390, 768, 1024, 1200, 1440):
        ctx, page, errors, _ = open_page(browser, built, "/", width, 900)
        for path in PAGES:
            page.goto("http://site.test" + path, wait_until="load")
            over = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert over <= 0, (width, path, over)
        ctx.close()


CARD = """sel => { const b = document.querySelector(sel), r = b.getBoundingClientRect();
  return {h: r.height, t: b.getAttribute('data-t'), sky: b.getAttribute('data-sky'), ready: b.classList.contains('is-ready'),
          inside: [...b.querySelectorAll('*')].every(e => { const q = e.getBoundingClientRect();
            return !q.height || getComputedStyle(e).position === 'absolute' || q.bottom <= r.bottom + .5; }),
          link: (() => { const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height * .6);
            return e && e.closest('a') ? e.closest('a').href : ''; })()}; }"""


def cells(page, sel):
    return page.evaluate(f"""[...document.querySelectorAll('{sel} .wx-strip li')].map(li => [li.querySelector('.wx-cn').textContent,
      li.querySelector('.wx-tc').textContent, li.classList.contains('is-now'), li.querySelector('img').getAttribute('src'),
      li.querySelector('img').alt])""")


def test_the_weather_module_fills_its_room_after_load(browser, built):
    """The panel's card (1440) and the home's (390, under the first screen): asked once each (the feed and the day's
    slots), after the page has loaded (a card asks when it nears the screen); drawn as 날씨각 draws it — the night sky
    (the feed's sky_mode) with the moon in its phase, '지금 날씨 점수' and the score, the bubble (the home: the summary
    and the status line too), the four cells 아침 · 낮 · 저녁 · 지금 (the slot 날씨각 takes for each — the last at or
    before 7 · 13 · 18 h; '지금' the feed's temperature, white) with 날씨각's icons; the card is one link to
    weather.o2o.kr; no source words; its box keeps its height, so nothing moves; no console error."""
    ctx, page, errors, calls = open_page(browser, built, "/", 1440)
    page.wait_for_selector(".wx-side.is-ready", timeout=8000)
    box = page.locator(".wx-side")
    assert page.evaluate("window.__wx") == ["complete", "complete"] and len(calls) == 2, calls
    assert {c.split("?")[0] for c in calls} == {"https://weather.o2o.kr/v1/feed", "https://weather.o2o.kr/v1/weather/today"}
    c = page.evaluate(CARD, ".wx-side")
    assert c["t"] == "night" and c["h"] == 246 and c["inside"] and c["link"] == "https://weather.o2o.kr/", c
    assert box.locator(".wx-sc small").inner_text() == "지금 날씨 점수" and box.locator(".wx-sc b").inner_text() == "60"
    assert box.locator(".wx-moon .wx-mo").count() == 1   # the moon (기우는 달, 64%) at night
    assert box.locator(".wx-bub").inner_text() == "지금은 러닝각!" and box.locator(".wx-sum, .wx-st").count() == 0
    sky = LC.SIDE_WORDS["ko"]["sky"]
    got = cells(page, ".wx-side")
    assert [(g[0], g[1], g[2]) for g in got] == [("아침", "12°", False), ("낮", "14°", False), ("저녁", "16°", False),
                                                 ("지금", "10°", True)], got
    assert all(g[3].startswith("/assets/wx/") and g[3].endswith(".webp") and g[4] in sky.values() for g in got), got
    go = box.locator(".wx-go")
    assert go.get_attribute("href") == "https://weather.o2o.kr/" and "자세히 보기" in go.inner_text()
    assert not SOURCE.search(box.inner_text()), box.inner_text()
    # the panel is the first screen: its card floats, but does not drop in
    assert page.evaluate("getComputedStyle(document.querySelector('.wx-side .wx-ob')).animationName") == "none"
    assert page.evaluate("getComputedStyle(document.querySelector('.wx-side .wx-orb')).animationName") == "wx-float"
    assert [x for x in page.evaluate("window.__ls") if x["v"] > 0.001] == [], page.evaluate("window.__ls")
    assert own(errors) == [], errors
    ctx.close()
    # the home on a phone (the card right under the first screen): asked after load, drawn in the room it kept
    ctx, page, errors, calls = open_page(browser, built, "/", 390, 844)
    h0 = page.evaluate(CARD, ".wx-home")
    page.wait_for_selector(".wx-home.is-ready", timeout=8000)
    page.wait_for_timeout(300)
    assert page.evaluate("window.__wx") == ["complete", "complete"] and len(calls) == 2
    page.evaluate("window.scrollTo(0, document.querySelector('.wx-home').getBoundingClientRect().top + scrollY - 100)")
    page.wait_for_timeout(1300)   # past the drop-in
    c = page.evaluate(CARD, ".wx-home")
    assert c["h"] == 401 and (h0["ready"] or h0["h"] == 401) and c["inside"] and c["link"] == "https://weather.o2o.kr/", (h0, c)
    home = page.locator(".wx-home")
    assert home.locator(".wx-bub").inner_text() == "지금은 러닝각!"
    assert home.locator(".wx-sum").inner_text() == "오후 7시 10°, 바람 살랑"
    assert re.sub(r"\s+", " ", home.locator(".wx-st").inner_text()) == "습도 보통 · 불쾌지수 쾌적 · 미세먼지 나쁨"
    assert home.locator(".wx-si.is-warn").inner_text() == "미세먼지 나쁨"
    assert [(g[0], g[1]) for g in cells(page, ".wx-home")] == [("아침", "12°"), ("낮", "14°"), ("저녁", "16°"), ("지금", "10°")]
    assert re.search(r"\d+월 \d+일 [월화수목금토일]요일", home.locator(".wx-dt").inner_text())
    assert not SOURCE.search(home.inner_text())
    assert [x for x in page.evaluate("window.__ls") if x["v"] > 0.001] == [], page.evaluate("window.__ls")
    assert own(errors) == [], errors
    ctx.close()


def test_the_card_takes_the_sky_of_the_hour(browser, built):
    """By day (the feed's sky_mode 'day'): the day sky, the round sun (no moon), the 낮 cell '지금' and the night's
    cell 밤; a cloudy slot now draws 날씨각's clouds."""
    ctx, page, errors, calls = open_page(browser, built, "/", 1440, weather=None)
    slots = weather_answer()
    for x in slots["slots"]:
        x["sky"] = 3   # cloudy all day
    route_weather(ctx, slots, feed=feed_answer(sky_mode="day"))
    page.reload(wait_until="load")
    page.wait_for_selector(".wx-side.is-ready", timeout=8000)
    c = page.evaluate(CARD, ".wx-side")
    assert c["t"] == "day" and c["sky"] == "cloudy" and c["h"] == 246, c
    assert page.locator(".wx-side .wx-mo").count() == 0 and page.locator(".wx-side .wx-cl").count() == 3
    got = cells(page, ".wx-side")
    assert [(g[0], g[2]) for g in got] == [("아침", False), ("지금", True), ("저녁", False), ("밤", False)], got
    assert all(g[3].endswith("/cloud.webp") for g in got), got
    assert own(errors) == [], errors
    ctx.close()


@pytest.mark.parametrize("code", ("en", "ja"))
def test_the_other_versions_show_figures_and_icons_only(browser, built, code):
    """The other versions: the score, the figures, the icons and the cells' names in their words — none of 날씨각's
    Korean words (bubble, summary, status), no source words."""
    W = LC.SIDE_WORDS[code]
    ctx, page, errors, _ = open_page(browser, built, f"/{code}/", 1440)
    page.wait_for_selector(".wx-side.is-ready", timeout=8000)
    text = page.locator(".wx-side").inner_text()
    assert not HANGUL.search(text) and not SOURCE.search(text) and page.locator(".wx-side .wx-bub").count() == 0, text
    assert page.locator(".wx-side .wx-sc small").inner_text() == W["wx_score"]
    assert [g[0] for g in cells(page, ".wx-side")] == [W["wx_slots"][k] for k in ("morning", "day", "sunset", "now")]
    assert page.evaluate(CARD, ".wx-side")["h"] == 220
    page.evaluate("window.scrollTo(0, document.querySelector('.wx-home').getBoundingClientRect().top + scrollY - 300)")
    page.wait_for_selector(".wx-home.is-ready", timeout=8000)
    home = page.locator(".wx-home").inner_text()
    assert not HANGUL.search(home) and not SOURCE.search(home), home
    assert page.locator(".wx-home .wx-bub").inner_text() == "10°"
    assert page.locator(".wx-home .wx-sum").inner_text() == W["wx_feels"].format(t="10°") + " · " + W["wx_hum"].format(p=60)
    assert page.evaluate(CARD, ".wx-home")["h"] == 356
    assert own(errors) == [], errors
    ctx.close()


def test_without_an_answer_or_js_the_link_stays(browser, built):
    # refused (a console line from the refused request is the browser's own, not the page's)
    ctx, page, errors, calls = open_page(browser, built, "/", 1440, weather="fail")
    page.wait_for_selector(".wx-side.is-failed", timeout=8000)
    go = page.locator(".wx-side .wx-go")
    assert go.is_visible() and go.inner_text().strip() == "군산 날씨 보기" and page.locator(".wx-side .wx-tc").count() == 0
    assert page.locator(".wx-side").bounding_box()["height"] == 246
    box = go.bounding_box()
    assert box["height"] >= 44, box
    assert own(errors) == [], errors
    ctx.close()
    # answers that are not today's: the same
    ctx, page, errors, calls = open_page(browser, built, "/", 1440, weather=None)
    route_weather(ctx, weather_answer("2000-01-01"), feed=feed_answer("2000-01-01"))
    page.reload(wait_until="load")
    page.wait_for_selector(".wx-side.is-failed", timeout=8000)
    assert page.locator(".wx-side .wx-tc").count() == 0
    ctx.close()
    # a feed without its hero (one answer only): the same
    ctx, page, errors, calls = open_page(browser, built, "/", 1440, weather=None)
    route_weather(ctx, feed=weather_answer())
    page.reload(wait_until="load")
    page.wait_for_selector(".wx-side.is-failed", timeout=8000)
    ctx.close()
    # no JS: the name and the link, no kept room, nothing asked
    ctx, page, errors, calls = open_page(browser, built, "/", 1440, js=False)
    page.wait_for_timeout(800)
    assert calls == [] and page.locator(".wx-side .wx-go").is_visible()
    assert page.locator(".wx-side .wx-go").inner_text().strip() == "군산 날씨 보기"
    assert page.locator(".wx-side").bounding_box()["height"] < 100
    assert page.locator(".side-nav").is_visible() and page.locator(".mast #hs-q").is_visible()
    ctx.close()


def test_the_panels_sunrise_follows_the_visitors_day(browser, built):
    """The HTML says the build day's sunrise and sunset with its date written out; on another day the list holds,
    weather.js shows that day's (the visitor's date in Korea)."""
    html = page_html(built, "/")
    days = re.search(r'data-sd-days="([^"]+)"', html).group(1).split(";")
    assert len(days) >= 2 and "오늘" not in block(html, '<a class="sd-sun"', "</a>")
    iso, rise, sset, lab = days[1].split("|")
    ctx, page, errors, _ = open_page(browser, built, "/", 1440)
    page.add_init_script(f"""(() => {{ const T = new Date('{iso}T09:00:00+09:00').getTime(), D = Date;
      class F extends D {{ constructor(...a) {{ super(...(a.length ? a : [T])); }} static now() {{ return T; }} }}
      window.Date = F; }})();""")
    page.reload(wait_until="load")
    page.wait_for_function("t => document.querySelector('.side [data-sd-lab]').textContent === t", arg=lab, timeout=10000)
    assert page.locator(".side [data-sd-lab]").inner_text() == lab
    assert page.locator(".side [data-sd-rise]").inner_text() == rise and page.locator(".side [data-sd-set]").inner_text() == sset
    ctx.close()


def test_reduced_motion_and_the_menu_pieces_keep_their_targets(browser, built):
    ctx, page, errors, _ = open_page(browser, built, "/", 1440, reduce=True)
    page.wait_for_selector(".wx-side.is-ready", timeout=8000)
    # no fade, float, drop-in, shooting star or twinkle
    for sel in (".wx-side .wx-b", ".wx-side .wx-orb", ".wx-side .wx-cb", ".wx-side .wx-ob", ".wx-side .wx-stars i"):
        if page.locator(sel).count():
            assert page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).animationName") == "none", sel
    assert page.evaluate("[...document.querySelectorAll('.wx-side .wx-shoot')].every(e => getComputedStyle(e).display === 'none')")
    for sel in (".side .sg-a", ".side .sg-s", ".side .sd-act", ".side .sd-sun", ".side .sd-ev", ".mast .lang-btn"):
        box = page.locator(sel).first.bounding_box()
        assert box and box["height"] >= 44, sel
    assert own(errors) == [], errors
    ctx.close()
