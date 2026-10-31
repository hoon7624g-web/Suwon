"""The AI course planner's page /plan/ (operator 2026-10-17: its own page, very visible, many cute 3D pictures;
chatbot/planner.js answers /api/plan/). The build writes the page — noindex, not in the sitemap — and /plan/places.json,
each place's first-screen values, TourAPI photo and point; the page's choices are real inputs; in a browser
(Playwright, /api/plan/ mocked with scripted SSE, nothing leaves the machine) the form asks with the conditions, the
steps light up, the plan is drawn from the site's own data with day tabs, legs with directions links, the fee card and
what to check, an edit sends the plan and the change, an error offers a retry, a reload shows the plan again, and no
phone width scrolls sideways."""
import copy
import datetime
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline.build import build
from conftest import weather_answer

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
FIRST_PLAN = {
    "hubs": [{"key": "station", "name": "군산역", "region": "금강"}, {"key": "bus", "name": "군산시외버스터미널", "region": "원도심"},
             {"key": "express", "name": "군산고속버스터미널", "region": "원도심"}, {"key": "airport", "name": "군산공항", "region": "은파"}],
    "prefs": [{"key": "history", "label": "역사·문화", "prompt": "역사·문화(근대 건물·박물관)", "pic": "theme-modern-history", "glyph": "building"},
              {"key": "food", "label": "맛집", "pic": "icon-food", "glyph": "bowl"},
              {"key": "islands", "label": "섬·바다", "pic": "theme-islands-sea", "glyph": "wave"},
              {"key": "nature", "label": "자연·힐링", "prompt": "자연·힐링(공원·호수)", "pic": "theme-parks-nature", "glyph": "tree"},
              {"key": "alleys", "label": "골목 산책", "pic": "theme-alleys-culture", "glyph": "lamp"},
              {"key": "cafe", "label": "카페·빵집", "pic": "kind-cafe", "glyph": "cup"},
              {"key": "experience", "label": "체험", "pic": "kind-experience", "glyph": "spark"},
              {"key": "night", "label": "야경", "pic": "sit-night", "glyph": "moon"},
              {"key": "photo", "label": "사진 명소", "pic": "pref-photo", "glyph": "camera"}],
    "resident_label": "군산시민", "far": {"고군산": {"car": 60, "transit": 120}}, "pref_regions": {"islands": ["고군산", "섬"]},
}
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


# the bottom of the bar at the top of the window: the header below 1200px; from 1200px the header is the tab panel at
# the left (operator 2026-10-31, css/80-side.css) and nothing sits across the top — 0
TOP_BAR = """(() => { const r = document.querySelector('.mast').getBoundingClientRect();
  return r.width < innerWidth / 2 ? 0 : r.bottom; })()"""


def plan_build(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    # the first city's planner values (its site.json plan, as tests/js/first_city.js has them): the sample is that city
    site["plan"] = FIRST_PLAN
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    pub = [p for p in places if p.get("status") in ("published", "reviewed")]
    for i, p in enumerate(pub[:4]):
        p["geo"] = {"lat": 35.98 + i * 0.01, "lng": 126.72 + i * 0.012, "source": "TourAPI"}
    pub[0]["images"] = [{"url": "https://tong.visitkorea.or.kr/cms/resource/00/1_image2_1.jpg", "license": "KOGL-3",
                         "source": "TourAPI", "credit": "한국관광공사", "alt": "사진"}]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return plan_build(tmp_path_factory.mktemp("plan"))


def test_the_page_is_a_noindex_utility_page_with_real_inputs_and_its_place_data(site):
    html = (site / "plan" / "index.html").read_text("utf-8")
    assert '<meta name="robots" content="noindex' in html
    assert "/plan/" not in (site / "sitemap.xml").read_text("utf-8")
    assert '<link rel="stylesheet" href="/assets/plan.css">' in html
    assert (site / "assets" / "plan.js").is_file() and (site / "assets" / "plan.css").is_file()
    assert 'data-plan data-api="/api/plan/" data-places="/plan/places.json" data-site="https://example.com" data-site-name="' in html
    # (the map is this site's own Leaflet map: nothing of it before a plan; the city's hubs from site.json plan.hubs)
    assert "data-kakao-sdk" not in html and "leaflet" not in html
    assert html.count('<option value="station">군산역</option>') == 2
    # every choice is a real radio or check box inside its card's label
    for name, kind, n in (("days", "radio", 3), ("move", "radio", 2), ("with", "radio", 4), ("prefs", "checkbox", 9),
                          ("needs", "checkbox", 6)):
        assert len(re.findall(rf'<label class="trp-card[^"]*"><input type="{kind}" name="{name}"', html)) == n, name
    assert html.count('<fieldset class="trp-step">') == 6 and html.count("<legend>") == 6
    assert 'aria-label="어른 한 명 더하기"' in html and 'type="date" name="date" required' in html
    # without JS the page says so and points to the courses and guides
    assert re.search(r"<noscript><p class=\"wrap trp-nojs\">코스 만들기는 자바스크립트가 켜져 있어야 동작합니다\. <a href=\"/courses/\">", html)
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    first = next(v for v in places.values() if v.get("img"))
    assert first["img"]["u"].startswith("https://tong.visitkorea.or.kr/") and first["img"]["t"] == 3
    assert all({"n", "k", "t", "ic"} <= set(v) for v in places.values())
    assert sum(1 for v in places.values() if "g" in v) == 4


def test_a_share_link_leaves_the_address_before_the_analytics_tags_read_it(site):
    """A share link carries the plan in the fragment (/plan/#p=…, operator 2026-10-19: nothing stored): the page's
    first script takes it out of the address (window.__trpLink, history.replaceState) before any tag can read it — the
    people, ages and needs of a plan are not the analytics' to keep. It is the first thing in <head> (base.html.j2
    head_first): ahead of the tag manager's snippet, whose script, once it has come (from the cache: at once), runs
    without waiting for the stylesheets, and ahead of every stylesheet, which an inline script after it waits for
    (round-6 verifier: the tag manager read the plan's address when the fragment script sat after the stylesheets).
    In a browser, with a stylesheet that takes its time and a tag manager that answers at once, the tag manager reads
    the address without the plan; with the old order it reads the plan. A link pasted into a tab already on /plan/
    changes only the fragment: the same script takes it out on popstate and hashchange, ahead of the tag manager's own
    history listeners (a history-change page view), and plan.js still opens it (round-6 final verifier: a later
    popstate listener read the plan); a script without those listeners lets them read it."""
    html = (site / "plan" / "index.html").read_text("utf-8")
    # the block sits on its own line so every other page prints exactly as before (trim_blocks takes its newline)
    first = ("<meta charset=\"utf-8\">\n<script>(function(){function t(){if(location.hash.indexOf('#p=')===0){window.__trpLink=location.hash;"
             "try{history.replaceState(")
    assert first in html
    head = html[:html.index("</head>")]
    assert head.index(first) < head.index("<link rel=\"stylesheet\"") and head.count("window.__trpLink=") == 1
    assert "t();addEventListener('popstate',t);addEventListener('hashchange',t)})()</script>" in head
    base = (ROOT / "templates" / "base.html.j2").read_text("utf-8")
    assert '<meta charset="utf-8">\n{% block head_first %}{% endblock %}\n{% if site.gtm_id and mode == \'production\' %}' in base
    assert base.index("{% block head_first %}") < base.index("googletagmanager.com/gtm.js") < base.index("{% block head %}") \
        < base.index("gtag('config'") < base.index('<script src="/assets/track.js"')
    assert base.index("{% block head_first %}") < base.index('rel="stylesheet"')

    # the tag manager's snippet as base.html.j2 prints it in production, where it prints it: right after head_first
    snippet = re.search(r"\{% if site\.gtm_id and mode == 'production' %\}(.*?)\{% endif %\}", base, re.S).group(1)
    snippet = snippet.replace("{{ site.gtm_id }}", "GTM-TEST")
    end_first = html.index("</script>", html.index(first)) + len("</script>")
    pages = {"now": html[:end_first] + "\n" + snippet + html[end_first:]}
    # the old order (the fragment script in the page's head block, after the stylesheets): the test can tell
    script = html[html.index(first) + len("<meta charset=\"utf-8\">\n"):end_first]
    old = html.replace(script, "", 1)
    old = old[:old.index("<meta charset=\"utf-8\">") + len("<meta charset=\"utf-8\">")] + "\n" + snippet + old[old.index("<meta charset=\"utf-8\">") + len("<meta charset=\"utf-8\">"):]
    pages["old"] = old.replace("</head>", script + "</head>", 1)
    # the first script as it was before (on load only): a pasted link's fragment stays for the tags' history listeners
    once = "<script>if(location.hash.indexOf('#p=')===0){window.__trpLink=location.hash;try{history.replaceState(history.state,'',location.pathname+location.search)}catch(e){}}</script>"
    pages["once"] = pages["now"].replace(script, once, 1)
    async_api = pytest.importorskip("playwright.async_api")
    import asyncio
    import mimetypes
    from urllib.parse import unquote, urlsplit

    async def run(which):
        async def serve(route):
            url = route.request.url
            if "googletagmanager.com/gtm.js" in url:   # the container: at once, reading the address as a tag would
                # …and its history listeners (a history-change page view), added after the page's first script
                return await route.fulfill(status=200, content_type="application/javascript", body=(
                    "window.__gtmSaw = location.href; window.__gtmHist = [];"
                    "addEventListener('popstate', function () { __gtmHist.push(['popstate', location.href]); });"
                    "addEventListener('hashchange', function () { __gtmHist.push(['hashchange', location.href]); });"))
            if not url.startswith("http://site.test/"):
                return await route.abort()
            path = unquote(urlsplit(url).path)
            if path == "/plan/":
                return await route.fulfill(status=200, body=pages[which], content_type="text/html; charset=utf-8")
            if path.endswith("/assets/style.css"):
                await asyncio.sleep(0.4)   # a phone's slow stylesheet
            f = site / path.strip("/")
            if not f.is_file():
                return await route.fulfill(status=404, body="")
            await route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

        async with async_api.async_playwright() as p:
            try:
                browser = await p.chromium.launch()
            except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
                pytest.skip(f"Chromium 없음: {ex}")
            try:
                ctx = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, locale="ko-KR")
                await ctx.route("**/*", serve)
                page = await ctx.new_page()
                await page.goto("http://site.test/plan/#p=z.AAAAexample", wait_until="load")
                saw = await page.evaluate("window.__gtmSaw")
                link = await page.evaluate("window.__trpLink === null ? 'taken' : String(window.__trpLink)")
                # a link pasted into this tab: only the fragment changes (popstate, then hashchange)
                await page.goto("http://site.test/plan/#p=z.BBBBexample", wait_until="commit")
                await page.wait_for_function("() => window.__gtmHist.length >= 2")
                hist = await page.evaluate("window.__gtmHist")
                if which == "once":
                    return saw, page.url, link, hist, None
                await page.wait_for_function("() => (document.querySelector('#h-result') || {}).textContent === '공유받은 코스를 열지 못했어요'")
                pasted = await page.evaluate("[window.__trpLink === null ? 'taken' : String(window.__trpLink), location.href]")
                return saw, page.url, link, hist, pasted
            finally:
                await browser.close()

    for _ in range(2):
        saw, url, link, hist, pasted = asyncio.run(run("now"))
        assert saw == "http://site.test/plan/" and url == "http://site.test/plan/", (saw, url)
        assert link == "taken", "plan.js took the link from window.__trpLink"
        assert hist == [["popstate", "http://site.test/plan/"], ["hashchange", "http://site.test/plan/"]], hist
        # plan.js opened it (the made-up link cannot be read: it says so) and took it from window.__trpLink
        assert pasted == ["taken", "http://site.test/plan/"], pasted
    saw, _, _, _, _ = asyncio.run(run("old"))
    assert saw == "http://site.test/plan/#p=z.AAAAexample", "the old order lets the tag manager read the plan"
    _, _, _, hist, _ = asyncio.run(run("once"))
    assert hist[0] == ["popstate", "http://site.test/plan/#p=z.BBBBexample"], f"a script on load only lets a history listener read it: {hist}"


def test_a_city_without_hubs_has_no_hub_choice(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    out = tmp_path / "out"
    build(data, out, "sample")
    html = (out / "plan" / "index.html").read_text("utf-8")
    assert 'name="from"' not in html and 'name="to"' not in html and "trp-hubs" not in html
    assert '<textarea name="note"' in html and 'placeholder="예: ' in html


def test_the_new_pictures_are_registered_and_fall_back_to_line_glyphs():
    icons = json.loads((ROOT / "data" / "suwon" / "icons.json").read_text("utf-8"))["icons"]
    ui = (ROOT / "templates" / "_ui.html.j2").read_text("utf-8")
    plan = [pid for pid, v in icons.items() if v.get("group") == "plan"]
    assert sorted(plan) == sorted(("icon-plan", "plan-dur-day", "plan-dur-1n2d", "plan-dur-2n3d", "plan-with-solo", "plan-with-couple",
                                   "plan-with-parents", "pref-photo", "cond-stroller", "cond-wheelchair", "cond-parking", "plan-budget", "plan-swap"))
    manifest = json.loads((ROOT / "templates" / "assets" / "icons" / "manifest.json").read_text("utf-8"))
    for pid in plan:
        g = icons[pid]["glyph"]
        assert f"name == '{g}'" in ui, (pid, g)
        assert pid in manifest, pid   # its 3D picture's renditions are committed
    # the hero illustration and the link preview are registered but not shown: a seaside harbour does not fit the city
    # (data/daegu/art.json _notes — the operator decides); the page then opens on its pictureless layout
    art = json.loads((ROOT / "data" / "suwon" / "art.json").read_text("utf-8"))["images"]
    for k, slot in (("plan-hero", "plan.head"), ("og-plan", "og.plan")):   # 2026-10-24: none (the art was withdrawn)
        if k in art:
            assert art[k]["slot"] == slot and art[k]["alt"].startswith("일러스트: ") and art[k]["langs"] == ["ko"], k


def test_every_picture_the_result_draws_is_on_the_page(site):
    """plan.js clones the result's pictures by ID from the page's <template id="trp-pics"> (plan.PLAN_RESULT_PICS);
    one not there is drawn as an empty pale circle (review 2026-10-18, fourth round: the status row '필요한 조건' asked
    for cond-wheelchair and the tile '들르는 곳' for icon-course). Every registered picture plan.js names, and every
    kind's picture a stop may carry (places.json ic), is in the template as its 3D picture."""
    from pipeline import plan
    icons = json.loads((ROOT / "data" / "suwon" / "icons.json").read_text("utf-8"))["icons"]
    js = (ROOT / "templates" / "assets" / "plan.js").read_text("utf-8")
    named = set(re.findall(r'"([a-z]+-[a-z0-9-]+)"', js)) & set(icons)
    assert {"cond-wheelchair", "icon-course", "transit-bus", "plan-budget"} <= named
    wanted = named | set(plan.KIND_PIC.values())
    assert wanted <= set(plan.PLAN_RESULT_PICS), wanted - set(plan.PLAN_RESULT_PICS)
    html = (site / "plan" / "index.html").read_text("utf-8")
    pics = html[html.index('<template id="trp-pics">'):]
    pics = pics[:pics.index("</template>")]
    for pid in wanted:
        assert f'<span data-id="{pid}"><span class="pic pic-3d" data-pic="{pid}"' in pics, pid


SITE = "https://example.com"


def sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


def a_plan(paths, days=2):
    """A checked plan as chatbot/planner.js finish (v 2) sends it."""
    stop = lambda p, a, b, role="visit", day="open", checks=(): {"path": p, "name": p.split("/")[2], "start": a, "end": b,  # noqa: E731
                                                               "role": role, "why": "1층에 어린이박물관이 있습니다", "day": day,
                                                               "notes": [], "flags": [], "checks": list(checks)}
    d1 = {"date": "2026-10-24", "label": "1일차 · 10월 24일 (토)",
          "stops": [stop(paths[0], "10:00", "11:30"), stop(paths[1], "12:00", "13:00", "meal"),
                    stop(paths[2], "13:00", "14:30", "visit", "unknown", ["쉬는 날이 사이트에 없음 — 그날 여는지 확인 필요"]),
                    stop(paths[3], "20:00", "21:00", "stay")],
          "legs": [{"from": 0, "to": 1, "m": 1430, "gap": 30, "routes": ["07", "99"], "flag": "", "mode": "traffic",
                    "url": "https://map.kakao.com/link/by/traffic/a,35.98,126.72/b,35.99,126.73"},
                   {"from": 1, "to": 2, "m": 400, "gap": 0, "routes": [], "flag": "직선 400m인데 이동 시간을 두지 않음", "mode": "walk",
                    "url": "https://map.kakao.com/link/by/walk/b,35.99,126.73/c,36.0,126.74"}],
          "hubs": [{"dir": "from", "name": "군산역", "stop": "a", "at": "09:00", "gap": 60, "url": "https://map.kakao.com/?sName=a&eName=b"}]}
    d2 = {"date": "2026-10-25", "label": "2일차 · 10월 25일 (일)", "stops": [stop(paths[2], "10:00", "12:00")], "legs": [], "hubs": []}
    return {"v": 2, "made": "2026-10-17T01:00:00Z", "title": "아이와 원도심 박물관 1박 2일", "summary": "실내 위주로 돕니다.",
            "notes": ["구간 시간은 여유입니다"], "conditions": {}, "days": [d1, d2][:days],
            "fees": {"state": "known", "total": 3000, "known": 3000, "limit": 10000, "verdict": "within", "open": [], "conds": [],
                     "days": [{"date": "2026-10-24", "lines": [{"what": "근대역사박물관", "who": "어른", "count": 1, "status": "paid",
                                                                "won": 3000, "sub": 3000, "basis": "요금표 '성인'"}]}]},
            "needs": [{"key": "stroller", "label": "유모차", "rows": [
                {"day": 0, "i": 0, "name": "a", "state": "ok", "text": "출입구: 경사로"},
                {"day": 0, "i": 1, "name": "b", "state": "unknown", "text": "출입구 접근 정보 없음"}]}],
            "checks": [{"k": "need", "t": "유모차: b — 출입구 접근 정보 없음"}, {"k": "move", "t": "장소 사이 시간은 계획상 여유"}],
            "flags": ["1일차 2→3번 b → c: 직선 400m인데 이동 시간을 두지 않음"], "status": "unmet",
            "fixed": ["1일차 장미갤러리: 10월 26일(월)은 쉬는 날이라 일정에서 뺐습니다"],
            "complete": {"meals": [{"day": 0, "kind": "lunch", "state": "ok"}], "gaps": [],
                         "prefs": [{"key": "history", "label": "역사·문화", "met": True}, {"key": "islands", "label": "섬·바다", "met": False}]},
            "todo": ["legs"]}


def plan_paths(site):
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    shot = next(p for p in places if places[p].get("img"))   # the place with a TourAPI photo comes first
    return [shot, next(p for p in places if places[p]["k"] == "food" and p != shot),
            next(p for p in places if places[p]["k"] == "attraction" and p != shot),
            next(p for p in places if places[p]["k"] == "stay" and p != shot)]


def server(site, plan, calls, script):
    """The browser's whole network: the built site from disk, /api/plan/ answered from `script` (then `plan`), the
    Kakao SDK's stand-in, a TourAPI photo; anything else is refused."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if url.endswith("/api/plan/"):
            calls.append(route.request.post_data_json)
            body = script["next"].pop(0) if script["next"] else sse({"type": "plan", "plan": plan})
            if isinstance(body, tuple):   # (status, JSON body): an answer before any streaming (422 preflight, 429 …)
                return route.fulfill(status=body[0], body=json.dumps(body[1], ensure_ascii=False), content_type="application/json")
            return route.fulfill(status=200, body=body, headers={"content-type": "text/event-stream; charset=utf-8"})
        if "dapi.kakao.com" in url:   # the Kakao SDK's stand-in (tests/js/kakao_stub.js)
            return route.fulfill(status=200, body=(ROOT / "tests" / "js" / "kakao_stub.js").read_text("utf-8"),
                                 content_type="application/javascript")
        if "tong.visitkorea.or.kr" in url or "tile.openstreetmap.org" in url:   # (the map's tiles too: Leaflet + OSM)
            return route.fulfill(status=200, body=PNG, content_type="image/png")
        if url.startswith("https://weather.o2o.kr/"):   # the tab panel's weather module (tests/conftest.py)
            return route.fulfill(status=200, body=json.dumps(weather_answer()), content_type="application/json",
                                 headers={"access-control-allow-origin": "*"})
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = site / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return serve


def test_in_a_browser_the_planner_asks_draws_edits_recovers_and_comes_back(site):
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    calls = []
    script = {"next": [sse({"type": "status", "step": "search", "text": "장소를 찾고 있어요"},
                           {"type": "status", "step": "check", "text": "휴무·운영시간을 확인하고 있어요"},
                           {"type": "plan", "plan": plan})]}
    serve = server(site, plan, calls, script)

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto("http://site.test/plan/", wait_until="load")
            page.wait_for_function("() => document.querySelector('[data-plan-sum]').textContent.length > 0")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            page.click('label.trp-card:has(input[name="days"][value="2"])')
            page.click('label.trp-card:has(input[name="with"][value="kids"])')   # adds a child (age 7)
            page.select_option("[data-ages] select", "4")
            for v in ("history", "food", "islands", "nature", "night"):
                page.click(f'label.trp-card:has(input[name="prefs"][value="{v}"])')
            assert page.evaluate("() => document.querySelectorAll('input[name=prefs]:checked').length") == 4
            page.click('label.trp-card:has(input[name="needs"][value="rain"])')
            page.click('[data-budget="10000"]')
            page.fill("textarea[name=note]", "짬뽕 먹고 싶어요")
            assert "1박 2일" in page.text_content("[data-plan-sum]") and "아이 4살" in page.text_content("[data-plan-sum]")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[0]["conditions"]
            assert c["days"] == 2 and c["with"] == "kids" and c["kids"] == [4] and c["adults"] == 2
            assert c["prefs"] == ["history", "food", "islands", "nature"] and c["needs"] == ["rain"] and c["budget"] == 10000
            assert c["note"] == "짬뽕 먹고 싶어요" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["date"])
            # what the code says first (review 2026-10-17: a '6/6 확인' badge above unconfirmed places): the status, each
            # check in its own state, the first things to check
            assert "is-bad" in page.get_attribute(".trp-status", "class") and "조건을 다 맞추지 못한" in page.text_content(".trp-status h3")
            assert page.locator(".trp-flags li").all_text_contents() == ["1일차 2→3번 b → c: 직선 400m인데 이동 시간을 두지 않음"]
            # what the site put right itself (planner.repair) is not listed (operator 2026-10-18: '이런 거 좀 안 뜨게')
            assert page.locator(".trp-fixed").count() == 0 and "바로잡은" not in page.text_content(".trp-result")
            rows = page.locator(".trp-st4 li")
            assert rows.count() == 6
            # what the data does not say is information, not a check (operator 2026-10-18)
            assert "공휴일·특별 운영" in rows.nth(1).text_content() and "그날 운영 자료가 없는 곳 1곳" in rows.nth(1).text_content()
            assert "is-info" in rows.nth(1).get_attribute("class")
            # per need (review 2026-10-22 C1: one sum over every need hid which one was unknown)
            assert "유모차: 자료 있음 1 · 정보 없음 1" in rows.nth(2).text_content()
            assert "3,000원 · 예산 안" in rows.nth(3).text_content()
            assert "구간마다 계획상 여유를 두었어요 · 실제 이동 시간은 지도 앱에서" in rows.nth(4).text_content()
            assert "is-info" in rows.nth(4).get_attribute("class")
            assert page.locator(".trp-st4 li.is-check, .trp-top").count() == 0
            # how complete the day is (outside evaluation 2026-10-18): meals, likings, empty time
            assert rows.nth(5).locator(".trp-st4-l").text_content() == "일정 완성도"
            assert "1일차 점심 포함 · 역사·문화 반영 / 섬·바다 미반영 · 2시간 넘게 빈 시간 없음" in rows.nth(5).text_content()
            assert "is-info" in rows.nth(5).get_attribute("class")
            # an unmet plan: one-tap fixes for what is left (the flagged leg)
            assert page.locator(".trp-qfix .trp-qf").all_text_contents() == ["이동 구간 다시 짜기"]
            # the travel-time line once above the day, under a leg only when it is flagged
            assert page.locator(".trp-tl-note").count() == 1 and "실제 이동 시간은 확인되지 않았어요" in page.text_content(".trp-tl-note")
            assert page.locator(".trp-leg:not(.trp-hub) .trp-leg-note").count() == 1
            assert "직선 400m인데 이동 시간을 두지 않음" in page.text_content(".trp-leg-bad .trp-leg-note")
            # the plan: title, day tabs, stops from the site's data, legs, the start, fees, checks
            assert page.text_content("#h-result") == "아이와 원도심 박물관 1박 2일"
            assert page.locator(".trp-days [role=tab]").count() == 2
            assert page.locator(".trp-stop").count() == 4
            assert page.locator(".trp-stop .trp-ai").first.text_content() == "AI"
            assert page.locator(".trp-ph figcaption").first.text_content() == "출처: 한국관광공사"
            assert page.locator(".trp-ph.t3 img").count() == 1   # KOGL-3: framed whole
            assert page.locator(".trp-stop[data-day=unknown] .trp-day").text_content().endswith("운영 확인 필요")
            assert "확인: 쉬는 날이 사이트에 없음" in page.text_content(".trp-stop[data-day=unknown] .trp-warn")
            assert page.locator(".trp-leg").count() == 3 and page.locator(".trp-leg-bad").count() == 1 and page.locator(".trp-hub").count() == 1
            assert "군산역 09:00 출발" in page.text_content(".trp-hub") and "계획상 여유 60분" in page.text_content(".trp-hub")
            assert page.get_attribute(".trp-leg:not(.trp-hub) .trp-leg-go >> nth=0", "href").startswith("https://map.kakao.com/link/by/traffic/")
            assert "같은 번호 노선 07·99번" in page.text_content(".trp-leg:not(.trp-hub) >> nth=0")
            assert "계획상 여유 30분" in page.text_content(".trp-leg:not(.trp-hub) >> nth=0")
            assert page.text_content(".trp-total") == "3,000원" and "예산 안" in page.text_content(".trp-verdict")
            assert "근대역사박물관 · 어른 1명:" in page.text_content(".trp-budget-c .trp-lines")
            assert "유모차: b — 출입구 접근 정보 없음" in page.text_content(".trp-check-c")
            assert page.locator(".trp-map .map[data-map]").count() == 1
            # the day map: map.js (window.GSMapStart) and Leaflet come with the plan
            page.wait_for_selector(".trp-map .map .leaflet-container, .trp-map .map.leaflet-container", timeout=15000)
            # on a phone the charts are folded; the reader opens them
            assert page.locator(".trp-fold[open]").count() == 0 and page.is_visible(".trp-fine-s")
            for summary in page.locator(".trp-fold > summary").all():
                summary.click()
            # the diagrams, every number from the checked plan: tiles, the day clock, the needs, the stations, the bars
            kpis = page.locator(".trp-kpi")
            assert kpis.count() == 4
            assert kpis.nth(0).locator(".trp-kpi-v").text_content() == "5곳" and "관람 3 · 식사 1 · 숙소 1" in kpis.nth(0).text_content()
            # 1,430m + 400m, straight lines — and the start at 군산역, a leg with no distance on the site: no total
            # (review 2026-10-22 movement S1: the hub legs were left out of the sum)
            assert kpis.nth(1).locator(".trp-kpi-v").text_content() == "전체 이동거리 계산 안 됨"
            assert kpis.nth(1).locator(".trp-kpi-n").text_content() == "3개 구간 중 2개만 거리 있음"
            assert kpis.nth(2).locator(".trp-kpi-v").text_content() == "3,000원"
            assert page.get_attribute(".trp-meter", "aria-label") == "확인된 입장료 3,000원 / 예산 10,000원"
            assert page.evaluate("() => document.querySelector('.trp-meter span').style.width") == "30%"
            # the stop whose closed days the site does not have is not counted '방문 가능' (review 2026-10-22 S1)
            assert kpis.nth(3).locator(".trp-kpi-v").text_content() == "4/5" and "그날 운영 확인 필요 1곳" in kpis.nth(3).text_content()
            assert page.locator(".trp-tlx-row").count() == 2
            day1 = page.locator(".trp-tlx-track >> nth=0")
            assert day1.locator(".trp-seg:not(.trp-seg-gap)").count() == 4 and day1.locator(".trp-seg-gap").count() == 2
            assert day1.locator(".trp-seg-flag").count() == 1
            assert page.locator(".trp-tlx-ticks span").all_text_contents() == ["10시", "12시", "14시", "16시", "18시", "20시"]
            assert page.locator(".trp-legend li").all_text_contents() == [
                "관람 5시간", "식사 1시간", "숙소 1시간", "계획상 여유 6시간", "이동이 빠듯한 곳 1곳"]
            first = day1.locator(".trp-seg >> nth=0")
            assert first.get_attribute("role") == "img" and first.get_attribute("tabindex") == "0"
            assert first.get_attribute("aria-label").endswith("관람 10:00~11:30 (1시간 30분)")
            first.hover()
            assert page.is_visible(".trp-tip") and page.text_content(".trp-tip") == first.get_attribute("aria-label")
            page.mouse.move(2, 2)
            assert page.is_hidden(".trp-tip")
            assert page.locator(".trp-ndt tbody tr").count() == 5 and page.locator(".trp-ndt thead th").all_text_contents() == ["장소", "유모차"]
            assert page.locator(".trp-nd.is-ok").count() == 1 and page.locator(".trp-nd.is-unknown").count() == 1
            assert page.locator(".trp-metro .trp-st").count() == 5 and page.locator(".trp-metro .trp-st-hub").count() == 1
            assert page.locator(".trp-metro .trp-link:not(.trp-link-hub) .tn").all_text_contents() == ["1.4km", "400m"]
            assert page.locator(".trp-metro .trp-link.bad").count() == 1
            assert page.locator(".trp-bars li").count() == 2 and page.locator(".trp-bar.bad").count() == 1
            assert page.locator(".trp-bar-v").all_text_contents() == ["1.4km", "400m ⚠"]
            # passing it on: a text file with the whole plan, every day and what to check
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            # a draft still unmet says so on its first line (outside evaluation 2026-10-18)
            assert text.startswith("[수정이 필요한 초안] 아이와 원도심 박물관 1박 2일") and "■ 2일차 · 10월 25일 (일)" in text
            assert "유모차: b — 출입구 접근 정보 없음" in text and "일정 완성도: 1일차 점심 포함" in text
            assert "09:00 군산역 출발" in text and "입장료: 3,000원" in text
            assert "구간 직선거리: 전체 이동거리 계산 안 됨(3개 구간 중 2개만 거리 있음)" in text
            assert "trp-print" in page.inner_html(".trp-result")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            # the second day by keyboard
            page.focus("#trp-tab-0")
            page.keyboard.press("ArrowRight")
            assert page.evaluate("() => document.activeElement.id") == "trp-tab-1"
            assert page.locator(".trp-stop").count() == 1
            # an edit: a quick chip fills the box; the request carries the plan and the change
            page.click(".trp-qe >> nth=0")
            assert page.input_value("#trp-ask") == "비가 오면 실내 위주로 바꿔 주세요"
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            e = calls[1]
            assert e["request"] == "비가 오면 실내 위주로 바꿔 주세요" and e["conditions"] == calls[0]["conditions"]
            assert e["plan"]["days"][0]["stops"][0] == {"page": paths[0], "start": "10:00", "end": "11:30", "role": "visit",
                                                         "why": "1층에 어린이박물관이 있습니다"}
            assert page.locator(".trp-diff li").all_text_contents() == ["장소와 시각은 그대로예요."]
            # a reload shows the plan again (this tab's storage) and the form holds its conditions (review: the form
            # went back to its defaults)
            page.reload(wait_until="load")
            page.wait_for_selector("#h-result")
            assert page.input_value("textarea[name=note]") == "짬뽕 먹고 싶어요" and page.input_value("input[name=budget]") == "10000"
            assert page.is_checked('input[name="days"][value="2"]') and page.locator("[data-ages] select").count() == 1
            assert page.input_value("[data-ages] select") == "4"
            # a change that fails keeps the plan and says so above the edit box
            script["next"] = [sse({"type": "error", "code": "busy", "message": "지금은 코스를 만들 수 없습니다."})]
            page.fill("#trp-ask", "덜 걷게 해 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-fail-edit")
            assert page.locator(".trp-stop").count() == 4 and page.evaluate("() => document.activeElement.textContent") == "바꾸지 못했어요"
            # an error offers a retry
            script["next"] = [sse({"type": "error", "code": "busy", "message": "지금은 코스를 만들 수 없습니다."})]
            page.click(".trp-submit")
            page.wait_for_selector(".trp-fail")
            assert "지금은 코스를 만들 수 없습니다." in page.text_content(".trp-fail")
            page.click(".trp-fail .btn")
            page.wait_for_selector("#h-result")
            assert errors == [], errors
            ctx.close()
            for width in (360, 1440):
                ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="ko-KR")
                ctx.route("**/*", serve)
                page = ctx.new_page()
                page.goto("http://site.test/plan/", wait_until="load")
                page.click(".trp-submit")
                page.wait_for_selector("#h-result")
                assert page.evaluate("() => document.documentElement.scrollWidth") <= width, width
                ctx.close()
        finally:
            browser.close()


def test_in_a_browser_conditions_come_from_the_address_and_an_unmet_plan_is_honest_about_what_is_left(site):
    """Outside evaluation 2026-10-18: the assistant hands a reader over with conditions in the address (never sent by
    themselves); a plan still 'unmet' shows no distance total over legs without one, never reads all-clear beside a
    closed stop, says how complete the day is, offers one-tap fixes that send an edit, and its text says it is a draft."""
    import datetime
    from urllib.parse import quote
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    d1 = plan["days"][0]
    d1["stops"][1]["added"] = True                                    # the lunch the site put in
    d1["stops"][3]["added"] = True                                    # the night's stay the site put in
    d1["stops"][2].update({"day": "closed", "checks": [], "flags": ["2026-10-24(토)은 정기 휴무"]})
    d1["legs"][1].update({"m": None, "flag": "", "gap": 20, "url": None})   # a place with no point: no distance
    plan.update({"status": "unmet", "flags": ["1일차 3번 c: 2026-10-24(토)은 정기 휴무", "1일차: 14:30~18:00 3시간 30분 동안 들르는 곳이 없다"],
                 "todo": ["closed", "legs", "meal", "gaps"],
                 "complete": {"meals": [{"day": 0, "kind": "lunch", "state": "missing"}, {"day": 1, "kind": "lunch", "state": "missing"}],
                              "gaps": [{"day": 0, "from": "14:30", "to": "18:00", "minutes": 210}],
                              "prefs": [{"key": "history", "label": "역사·문화", "met": True}, {"key": "night", "label": "야경", "met": None}],
                              "edit": [{"what": "점심", "state": "lost"}]}})
    calls: list = []
    serve = server(site, plan, calls, {"next": []})
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    address = (f"/plan/?date={day}&days=2&start=09:00&end=20:00&move=car&with=kids&adults=3&seniors=1&kids=8,5"
               f"&needs=rain,stroller,bogus&prefs=history,food,islands,nature,night&from=station&to=bus&note={quote('짬뽕 먹고 싶어요')}")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # values that are not the form's own choices are left out: the defaults stay
            page.goto("http://site.test/plan/?days=9&move=plane&adults=99&kids=40&prefs=bogus&start=05:00&from=harbour", wait_until="load")
            assert page.is_checked('input[name="days"][value="1"]') and page.is_checked('input[name="move"][value="transit"]')
            assert page.text_content('[data-count="adults"] [data-count-value]') == "2" and page.locator("[data-ages] select").count() == 0
            assert page.input_value("select[name=start]") == "10:00" and page.input_value("select[name=from]") == ""
            assert page.locator('input[name="prefs"]:checked').count() == 0 and page.get_attribute("[data-plan]", "data-prefilled") is None
            # the assistant's hand-over: every condition in the form, nothing sent
            page.goto("http://site.test" + address, wait_until="load")
            assert page.get_attribute("[data-plan]", "data-prefilled") == ""
            assert page.input_value("input[name=date]") == day and page.is_checked('input[name="days"][value="2"]')
            assert page.input_value("select[name=start]") == "09:00" and page.input_value("select[name=end]") == "20:00"
            assert page.is_checked('input[name="move"][value="car"]') and page.is_checked('input[name="with"][value="kids"]')
            assert page.text_content('[data-count="adults"] [data-count-value]') == "3"
            assert page.text_content('[data-count="seniors"] [data-count-value]') == "1"
            assert [page.input_value(f"[data-ages] select >> nth={i}") for i in range(2)] == ["8", "5"]
            assert page.eval_on_selector_all('input[name="needs"]:checked', "els => els.map(e => e.value)") == ["rain", "stroller"]
            assert page.eval_on_selector_all('input[name="prefs"]:checked', "els => els.map(e => e.value)") == ["history", "food", "islands", "nature"]
            assert page.input_value("select[name=from]") == "station" and page.input_value("select[name=to]") == "bus"
            assert page.input_value("textarea[name=note]") == "짬뽕 먹고 싶어요" and "1박 2일" in page.text_content("[data-plan-sum]")
            page.wait_for_timeout(300)
            assert calls == []                                        # never sent by itself
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[0]["conditions"]
            assert (c["date"], c["days"], c["start"], c["end"], c["move"], c["with"]) == (day, 2, "09:00", "20:00", "car", "kids")
            assert (c["adults"], c["seniors"], c["kids"], c["from"], c["to"]) == (3, 1, [8, 5], "station", "bus")
            assert c["needs"] == ["rain", "stroller"] and c["prefs"] == ["history", "food", "islands", "nature"]
            # the distance tile: no total over legs without a distance
            tile = page.locator(".trp-kpi >> nth=1")
            assert tile.locator(".trp-kpi-v").text_content() == "전체 이동거리 계산 안 됨"
            assert tile.locator(".trp-kpi-n").text_content() == "3개 구간 중 1개만 거리 있음"   # the start at 군산역 too
            assert "좌표가 없어 거리를 모르는 구간 1개는 막대에 없어요." in page.text_content(".trp-bars")
            assert page.locator(".trp-kpi >> nth=3").locator(".trp-kpi-n").text_content() == "그날 휴무 1곳"
            # a closed stop: the holiday row never reads all-clear beside it
            rows = page.locator(".trp-st4 li")
            assert "그날 휴무인 곳 1곳" in rows.nth(0).text_content()
            assert "is-bad" in rows.nth(1).get_attribute("class") and "그날 쉬는 곳 1곳이 남아 있음" in rows.nth(1).text_content()
            done = rows.nth(5)
            assert "is-bad" in done.get_attribute("class")
            # every picture of the result is a picture: none is the empty circle of an ID the page does not carry
            assert page.locator("[data-plan-result] .pic").count() > 10
            assert page.locator("[data-plan-result] .pic:empty").count() == 0
            assert done.locator(".trp-st4-v").text_content().endswith(
                "1·2일차 점심 빠짐 · 역사·문화 반영 / 자료로 판단 못 함: 야경 · 1일차 14:30~18:00 3시간 30분 비어 있음 · 고치기 전 일정의 점심: 빠짐")
            # the stop the site put in says so where the AI's reason would be
            assert page.text_content(".trp-stop[data-by=site] .trp-site") == "사이트"
            assert "식사할 곳이 없어 사이트가 넣은 가까운 음식점이에요" in page.text_content(".trp-stop[data-role=meal][data-by=site] .trp-by")
            assert "묵을 곳이 없어 사이트가 넣은 숙소예요" in page.text_content(".trp-stop[data-role=stay][data-by=site] .trp-by")
            # the text passed on starts as a draft
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert text.startswith("[수정이 필요한 초안] 아이와 원도심 박물관 1박 2일")
            assert "구간 직선거리: 전체 이동거리 계산 안 됨(3개 구간 중 1개만 거리 있음)" in text and "· 사이트가 넣음]" in text
            # one-tap fixes: each sends the edit request with fixed words and the plan on screen
            assert page.locator(".trp-qfix .trp-qf").all_text_contents() == ["휴무 장소 바꾸기", "이동 구간 다시 짜기", "빠진 점심 넣기", "빈 시간 채우기"]
            page.click(".trp-qf[data-fix=gaps]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            e = calls[-1]
            assert e["request"] == "비어 있는 시간에 가까운 장소를 넣어 주세요" and e["conditions"] == calls[0]["conditions"]
            assert [s["page"] for s in e["plan"]["days"][0]["stops"]] == paths
            page.click(".trp-qf[data-fix=meal]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            assert calls[-1]["request"] == "빠진 점심을 그 시간에 여는 가까운 음식점으로 넣어 주세요"
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_finished_plan_reads_as_finished(site):
    """Operator 2026-10-18 ('이런 거 좀 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게'): a plan that breaks nothing reads
    as a finished course. What holds for any plan (planned margins, a hub's leg, a stay's booking — finish 'aware') and
    what the data does not say (finish 'checks') sit in one closed box, '가기 전에 알아 둘 것', never on top as something
    left to check; what the site put right itself is not listed; no '초안', no '?' mark. Its heading counts the status
    rows that are to check before going (operator 2026-10-23 — an outside tester read '완성된 코스예요' as 'meets every
    condition' above such rows): '코스 완성 · 가기 전 확인 N가지', N the rows the box marks i or !, the same in the text
    passed on."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    plan.update({"status": "ready", "flags": [], "todo": [],
                 "checks": [{"k": "need", "t": "유모차: b — 출입구 접근 정보 없음"}],
                 "aware": [{"k": "move", "t": "장소 사이 시간은 계획상 여유이고, 실제 이동 시간은 확인되지 않음(직선거리만 있음)"},
                           {"k": "stay", "t": "d: 체크인 15:00(사이트 값) — 객실·예약은 숙소에 확인"}]})
    calls: list = []
    serve = server(site, plan, calls, {"next": [sse({"type": "plan", "plan": plan})]})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            assert "is-ok" in page.get_attribute(".trp-status", "class")
            # the rows marked i (a stop its rule cannot decide, a day with no data, 유모차 정보 없음, the map app's times, 섬·바다
            # 미반영) — their number in the heading; the fees row (✓) is not one
            to_check = page.locator(".trp-st4 li.is-info, .trp-st4 li.is-bad")
            assert to_check.locator(".trp-st4-l").all_text_contents() == ["정기 휴무·운영시간", "공휴일·특별 운영", "필요한 조건", "이동", "일정 완성도"]
            assert page.locator(".trp-st4 li.is-ok .trp-st4-l").all_text_contents() == ["입장료"]
            assert page.text_content(".trp-status h3") == "✓코스 완성 · 가기 전 확인 5가지"
            assert page.text_content(".trp-status h3 .trp-mark") == "✓"
            assert "완성된 코스예요" not in page.text_content(".trp-result")
            assert page.text_content(".trp-r-head .trp-eyebrow") == "AI가 짜고 사이트 자료와 코드로 검사한 코스"
            res = page.text_content(".trp-result")
            for word in ("초안", "바로잡은", "가기 전에 확인할 것", "확인할 것이 남은"):
                assert word not in res, word
            assert page.locator(".trp-st4 li.is-check, .trp-st4 li.is-bad, .trp-flags, .trp-qfix, .trp-top, .trp-fixed").count() == 0
            assert page.locator(".trp-mark").all_text_contents().count("?") == 0
            # the box: closed, the data's gaps and what holds for any plan, by kind
            box = page.locator("details#trp-checks")
            assert box.count() == 1 and box.get_attribute("open") is None
            assert page.text_content("#trp-checks summary").strip() == "가기 전에 알아 둘 것"
            assert page.locator("#trp-checks .trp-qg h4").all_text_contents() == ["필요한 조건", "숙소", "이동"]
            page.click("#trp-checks summary")
            assert page.is_visible("#trp-checks .trp-qs") and "객실·예약은 숙소에 확인" in page.text_content("#trp-checks")
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert text.startswith("아이와 원도심 박물관 1박 2일") and "\n상태: 코스 완성 · 가기 전 확인 5가지\n" in text
            assert "완성된 코스예요" not in text and "상태: 코스 완성 · 가기 전 확인 5가지" in page.text_content(".trp-print")
            assert "가기 전에 알아 둘 것:\n- 유모차: b — 출입구 접근 정보 없음\n- 장소 사이 시간은 계획상 여유" in text
            assert "\n- d: 체크인 15:00(사이트 값) — 객실·예약은 숙소에 확인" in text
            assert "바로잡은" not in text and "초안" not in text
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_the_finished_heading_counts_what_the_box_marks_to_check(site):
    """'코스 완성 · 가기 전 확인 N가지' (operator 2026-10-23): N is exactly the status rows the box marks i or ! — a ! row
    (a need the data says a stop does not meet) counts, a ✓ row and the '–' of 고른 조건 없음 do not; the status (ready)
    and its ✓ stay the server's. An edit that turns a draft into a finished plan says so in the heading's own words in
    '바꾼 뒤 달라진 것'; the text passed on carries the same heading."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    draft = a_plan(paths)                                   # status unmet (a leg with no time)
    done = copy.deepcopy(draft)
    done["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    for s in done["days"][0]["stops"]:
        s.update({"day": "open", "checks": []})
    done["needs"] = [{"key": "rain", "label": "실내", "rows": [
        {"day": 0, "i": 0, "name": "a", "state": "ok", "text": "실내(박물관·전시)"},
        {"day": 0, "i": 2, "name": "c", "state": "no", "text": "야외(자연·야외)"}]}]
    done["complete"]["prefs"] = [{"key": "history", "label": "역사·문화", "met": True}]
    done.update({"status": "ready", "flags": [], "todo": [], "checks": [{"k": "need", "t": "실내: c — 야외(자연·야외)"}],
                 "aware": [{"k": "move", "t": "장소 사이 시간은 직선거리로 잡은 계획상 여유예요"}]})
    done["days"][0]["stops"][2]["asked"] = True   # an outdoor place asked for on a rainy day (planner makePlan)
    calls: list = []
    serve = server(site, draft, calls, {"next": [sse({"type": "plan", "plan": draft}), sse({"type": "plan", "plan": done})]})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            assert page.text_content(".trp-status h3") == "!조건을 다 맞추지 못한 초안이에요"   # a draft: as before
            page.fill("#trp-ask", "이동이 빠듯한 구간에 여유를 두어 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-diff")
            marks = page.locator(".trp-st4 li")
            states = [marks.nth(i).get_attribute("class") for i in range(marks.count())]
            labels = page.locator(".trp-st4 .trp-st4-l").all_text_contents()
            # the rows: 정기 휴무 ✓, 공휴일 ✓, 필요한 조건 ! (실내: 맞지 않음 1), 입장료 ✓, 이동 i, 일정 완성도 ✓
            assert list(zip(labels, states)) == [("정기 휴무·운영시간", "is-ok"), ("공휴일·특별 운영", "is-ok"), ("필요한 조건", "is-bad"),
                                                 ("입장료", "is-ok"), ("이동", "is-info"), ("일정 완성도", "is-ok")]
            assert page.text_content(".trp-status h3") == "✓코스 완성 · 가기 전 확인 2가지"
            assert "is-ok" in page.get_attribute(".trp-status", "class")
            assert "상태: 조건을 다 맞추지 못한 초안이에요 → 코스 완성 · 가기 전 확인 2가지" in page.locator(".trp-diff li").all_text_contents()
            assert "상태: 코스 완성 · 가기 전 확인 2가지" in page.text_content(".trp-print")
            assert "완성된 코스예요" not in page.text_content(".trp-result")
            # the next edit sends the mark of the place asked for on it (review 2026-10-23: the next edit swapped it away)
            page.fill("#trp-ask", "점심을 조금 늦춰 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            sent = calls[2]["plan"]["days"][0]["stops"]
            assert [s.get("asked") for s in sent] == [None, None, True, None]
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_place_seen_only_from_outside_says_so_with_its_source(site):
    """Outside tester 2026-10-23: 구 제일사료주식회사 공장 went in a course as a 30-minute stop whose card said only '시간
    내부 관람 불가' and whose check said its hours could not be read. A stop whose data says its inside is not open
    (planner finish 'outside': the sources; only — its hours value is only those words) shows '관람: 외관 감상 · 내부 관람
    불가(자료: …)' in its card, in place of that hours row when the value is only those words; the box '가기 전에 알아 둘
    것' has it under '외관만 보는 곳' (finish 'aware' k 'outside'), never as something to check; the text keeps both."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    plan = a_plan(paths, days=1)
    d = plan["days"][0]
    d["legs"][1].update({"gap": 10, "flag": ""})
    d["stops"][0]["outside"] = {"p": "한국관광공사 TourAPI", "only": 1}
    d["stops"][2].update({"outside": {"p": "군산시 문화관광 · 한국관광공사 TourAPI"}, "checks": []})
    a, c = d["stops"][0]["name"], d["stops"][2]["name"]
    plan.update({"status": "ready", "flags": [], "todo": [], "checks": [],
                 "aware": [{"k": "outside", "t": f"{a}: 외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)"},
                           {"k": "outside", "t": f"{c}: 외관 감상 · 내부 관람 불가(자료: 군산시 문화관광 · 한국관광공사 TourAPI)"},
                           {"k": "move", "t": "장소 사이 시간은 계획상 여유"}]})
    calls: list = []
    serve = server(site, plan, calls, {"next": [sse({"type": "plan", "plan": plan})]})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            cards = page.locator(".trp-stop")

            def rows(i):
                return [(li.locator(".trp-fl").text_content(), li.locator("span").nth(1).text_content())
                        for li in cards.nth(i).locator(".trp-facts li").all()]
            first, third = rows(0), rows(2)
            assert ("관람", "외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)") in first, first
            assert "시간" not in [k for k, _ in first], first   # its hours value is only those words
            assert ("관람", "외관 감상 · 내부 관람 불가(자료: 군산시 문화관광 · 한국관광공사 TourAPI)") in third, third
            assert ("시간" in [k for k, _ in third]) == bool(places[paths[2]].get("h")), third   # real hours stay
            assert cards.nth(0).locator(".trp-warn").count() == 0   # never a line to check
            assert "is-ok" in page.get_attribute(".trp-status", "class")
            assert page.locator("#trp-checks .trp-qg h4").all_text_contents() == ["외관만 보는 곳", "이동"]
            page.click("#trp-checks summary")
            assert f"{a}: 외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)" in page.text_content("#trp-checks")
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert "\n     관람: 외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)\n" in text
            assert f"가기 전에 알아 둘 것:\n- {a}: 외관 감상 · 내부 관람 불가(자료: 한국관광공사 TourAPI)" in text
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


PROBLEMS = {"code": "conditions", "message": "이 조건으로는 코스를 끝까지 짤 수 없어요. 아래를 바꿔 주세요.", "problems": [
    {"field": "needs", "text": "10월 24일(토)에 여는 곳 가운데 '휠체어'에 맞는다고 자료에 있는 곳이 1곳뿐이라 하루를 채울 수 없어요.",
     "fixes": [{"label": "'휠체어' 조건 빼기", "set": {"needs": []}}]},
    {"field": "date", "text": "다른 날을 고르면 짤 수 있을 수 있어요.", "fixes": [{"label": "날짜 바꾸기", "focus": "date"}]}]}


@pytest.mark.parametrize("width", [390, 1440])
def test_in_a_browser_conditions_no_plan_can_meet_are_said_by_the_button_with_their_fixes(site, width):
    """Operator 2026-10-18 ('문제가 있으면 아예 생성 버튼 누르는 단계에서 지적을 하고'): the planner's preflight answers
    422 {code: 'conditions', problems} before any model call — the page stays on the form, says why right above the
    button and offers the fixes; a fix sets the form (the summary follows) and the next press sends the new conditions.
    The same comes as an SSE error at the end; a hand change makes the box go. No failure page, no working view."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    plan.update({"status": "ready", "flags": [], "todo": []})
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    calls: list = []
    script = {"next": [(422, PROBLEMS), sse({"type": "plan", "plan": plan}),
                       sse({"type": "status", "step": "search", "text": "…"}, {"type": "error", **PROBLEMS})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 844}, locale="ko-KR",
                                      is_mobile=width < 900, has_touch=width < 900)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click('label.trp-card:has(input[name="needs"][value="wheelchair"])')
            assert "휠체어" in page.text_content("[data-plan-sum]")
            page.click(".trp-submit")
            page.wait_for_selector(".trp-prob:not([hidden])")
            assert calls[0]["conditions"]["needs"] == ["wheelchair"]
            # the form, not a failure page; the working view is gone; the box sits right above the button's bar
            assert page.locator("#h-result").count() == 0 and page.locator(".trp-fail").count() == 0
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            assert page.evaluate("() => document.querySelector('.trp-prob').nextElementSibling.classList.contains('trp-go')")
            assert page.get_attribute(".trp-prob", "role") == "alert"
            assert page.evaluate("() => document.activeElement.matches('.trp-prob h3')")
            assert page.text_content(".trp-prob h3") == "이 조건으로는 코스를 끝까지 짤 수 없어요"
            assert page.text_content(".trp-prob-m") == "아래를 바꿔 주세요."
            assert page.locator(".trp-prob-l > li").count() == 2
            assert "'휠체어'에 맞는다고 자료에 있는 곳이 1곳뿐" in page.text_content(".trp-prob-l")
            assert page.locator(".trp-prob-fix").all_text_contents() == ["'휠체어' 조건 빼기", "날짜 바꾸기"]
            box = page.locator(".trp-prob").bounding_box()
            assert box["y"] >= 0 and box["y"] < 844 and box["width"] <= width
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            # a fix that puts the cursor on a field
            page.click(".trp-prob-fix:has-text('날짜 바꾸기')")
            assert page.evaluate("() => document.activeElement.name") == "date"
            # a fix that sets the form: the box says what changed and offers to make the plan with it
            page.click(".trp-prob-fix:has-text('조건 빼기')")
            assert not page.is_checked('input[name="needs"][value="wheelchair"]')
            assert "휠체어" not in page.text_content("[data-plan-sum]")
            assert page.text_content(".trp-prob-done") == "조건을 바꿨어요. 바꾼 조건은 아래 요약 줄에 있어요."
            assert page.is_visible(".trp-prob-go") and page.evaluate("() => document.activeElement.matches('.trp-prob-go')")
            # in view and clear of the button's bar (on phones it stays at the screen's foot)
            # (the bar at the foot is .trp-go-bar since review 2026-10-22: on phones only the button's bar is sticky)
            assert page.evaluate("""() => { const g = document.querySelector('.trp-prob-go').getBoundingClientRect();
              const bar = document.querySelector('.trp-go-bar').getBoundingClientRect();
              return g.top >= 0 && (g.bottom <= bar.top || getComputedStyle(document.querySelector('.trp-go-bar')).position !== 'sticky'); }""")
            page.click(".trp-prob-go")
            page.wait_for_selector("#h-result")
            assert calls[1]["conditions"]["needs"] == []
            assert page.is_hidden(".trp-prob")
            # the same at the end of a stream; a change by hand makes the box go
            page.click(".trp-submit")
            page.wait_for_selector(".trp-prob:not([hidden])")
            page.click('label.trp-card:has(input[name="prefs"][value="food"])')
            assert page.is_hidden(".trp-prob")
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


# the server's own label for a fix that leaves several needs out (planner preflight) — four needs in one button
WIDE_PROBLEMS = {"code": "conditions", "message": "이 조건으로는 코스를 끝까지 짤 수 없어요. 아래를 바꿔 주세요.", "problems": [
    {"field": "needs", "text": "3일차 10월 28일(수)에 여는 곳 가운데 '유모차'·'휠체어'·'주차 편한 곳'·'입장료 없는 곳 위주'에 모두 맞는다고 "
                                "자료에 있는 곳이 10곳뿐이라 앞선 날에 넣은 5곳을 빼면 3일차를 채울 수 없어요.",
     "fixes": [{"label": "'유모차'·'휠체어'·'주차 편한 곳'·'입장료 없는 곳 위주' 조건 빼기", "set": {"needs": []}}]}]}


@pytest.mark.parametrize("width", [360, 390])
def test_in_a_browser_the_conditions_box_never_scrolls_sideways_on_a_phone(site, width):
    """Round-6 final verifier: a fix that leaves four needs out kept the buttons' one-line rule and, as a grid item, made
    the form 476–494px wide at 390 (the page scrolled sideways, the box's text and the label cut at the edge). The box's
    buttons wrap inside the column."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    calls: list = []
    serve = server(site, plan, calls, {"next": [(422, WIDE_PROBLEMS)]})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 800}, locale="ko-KR", is_mobile=True, has_touch=True)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/plan/", wait_until="load")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            page.click(".trp-submit")
            page.wait_for_selector(".trp-prob:not([hidden])")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            fix = page.locator(".trp-prob-fix")
            assert fix.text_content() == WIDE_PROBLEMS["problems"][0]["fixes"][0]["label"]
            b = fix.bounding_box()
            assert b["x"] >= 0 and b["x"] + b["width"] <= width, b
            assert b["height"] > 50, "the label wraps onto a second line"
            # the box and every line in it inside the screen
            assert page.evaluate("""(w) => [...document.querySelectorAll('.trp-prob, .trp-prob *')].every((e) => {
              const r = e.getBoundingClientRect(); return !r.width || (r.left >= 0 && r.right <= w); })""", width)
            # the label is whole (not cut): its text fits the button's box
            assert page.evaluate("() => { const x = document.querySelector('.trp-prob-fix'); return x.scrollWidth <= x.clientWidth; }")
            fix.click()
            assert page.is_visible(".trp-prob-go")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_plan_the_site_built_itself_says_so_and_a_change_that_cannot_be_finished_keeps_the_plan(site):
    """When the AI gives no plan it can use, the planner sends one built from the site's data (one 'fixed' line starting
    '일정 전체:', every stop put in by the site): the page says so above the course, not 'AI가 짜고' and not '빈 시간이
    길어 사이트가 넣은 곳' on every stop. A change the planner cannot finish ('edit_failed') keeps the plan on screen."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    for d in plan["days"]:
        for st in d["stops"]:
            st.update({"added": True, "why": ""})
    plan.update({"status": "ready", "flags": [], "todo": [], "notes": [], "summary": "원도심 박물관을 돕니다.",
                 "fixed": ["일정 전체: AI 응답을 받지 못해 사이트 자료로 일정을 짰습니다"]})
    calls: list = []
    msg = "요청한 변경으로는 코스를 끝까지 맞출 수 없어 보던 일정을 그대로 두었습니다. 요청을 조금 바꿔 다시 시도해 주세요."
    script = {"next": [sse({"type": "plan", "plan": plan}), sse({"type": "error", "code": "edit_failed", "message": msg})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            assert page.text_content(".trp-r-head .trp-eyebrow") == "사이트 자료로 짜고 코드로 검사한 코스"
            assert page.text_content(".trp-r-code") == "사이트 AI 응답을 받지 못해 사이트 자료로 일정을 짰어요"
            assert page.locator(".trp-by").count() == 0
            assert page.text_content(".trp-foot").startswith("사이트 자료로 고른 순서와 시각을")
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert "사이트가 넣음" not in text and "AI(Claude)가 고른" not in text
            assert "AI 응답을 받지 못해 사이트 자료로 일정을 짰어요. 군산 여행 · WebforAI (샘플)(" in text
            # a change that cannot be finished: the plan stays, the message sits above the edit box
            page.fill("#trp-ask", "비 오면 실내로 바꿔 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-fail-edit")
            assert msg in page.text_content(".trp-fail-edit") and page.text_content("#h-result") == plan["title"]
            assert page.locator(".trp-prob:not([hidden])").count() == 0
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_an_edit_for_fewer_fees_says_what_it_did_to_them(site):
    """The quick edit '입장료 줄이기' (outside test 2026-10-23: it came back '장소와 시각은 그대로예요' under a '무료'
    title): what the server says of the request itself (planner 'edited', [{k, t}]) joins '바꾼 뒤 달라진 것' — the fees
    before and after once (not the page's own '입장료: … → …' as well), or, when nothing could be swapped, that the
    places and times stayed and why."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    other = next(p for p in places if places[p]["k"] == "attraction" and p not in paths)
    plan = a_plan(paths, days=1)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    plan.update({"status": "ready", "flags": [], "todo": []})
    swapped = json.loads(json.dumps(plan))
    swapped["days"][0]["stops"][0].update({"path": other, "name": other.split("/")[2], "why": "", "swapped": "other"})
    swapped["fees"] = {"state": "free", "total": 0, "known": 0, "limit": 10000, "verdict": "within", "open": [], "conds": [], "days": []}
    down = "입장료 줄이기: 입장료 3,000원 → 0원(3,000원 줄었어요)"
    swapped["edited"] = [{"k": "fee", "t": down}]
    kept = json.loads(json.dumps(plan))
    stay = "입장료 줄이기: 입장료가 있는 a는 그 시간에 맞는 무료·더 싼 장소가 그날 동선 가까이에 없어 그대로 두었어요 — 입장료는 3,000원 그대로예요"
    kept["edited"] = [{"k": "fee", "t": stay}]
    calls: list = []
    script = {"next": [sse({"type": "plan", "plan": plan}), sse({"type": "plan", "plan": kept}), sse({"type": "plan", "plan": swapped})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            page.click(".trp-qe:has-text('입장료 줄이기')")
            assert page.input_value("#trp-ask") == "입장료 없는 곳 위주로 바꿔 주세요"
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-diff")
            assert calls[1]["request"] == "입장료 없는 곳 위주로 바꿔 주세요"
            # nothing could be swapped: the places and times stayed, and why the fees did
            assert page.locator(".trp-diff li").all_text_contents() == ["장소와 시각은 그대로예요.", stay]
            # a swap: what came and went, and the fees before and after once (not the page's '입장료: 3,000원 → 0원' too)
            page.fill("#trp-ask", "입장료 줄여 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_function("(t) => [...document.querySelectorAll('.trp-diff li')].some((x) => x.textContent === t)", arg=down)
            name = other.split("/")[2]
            assert page.locator(".trp-diff li").all_text_contents() == [f"1일차: {name} 추가(10:00~11:30)", f"1일차: {paths[0].split('/')[2]} 뺌", down]
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_an_address_starts_from_the_defaults_and_never_shows_what_the_form_could_not(site):
    """The review of the hand-over (2026-10-18): conditions in the address were laid over the tab's kept conditions and
    its plan stayed on screen under them; with=solo&adults=3 showed three people travelling alone. Now the address
    starts from the form's defaults, the kept plan is not shown, a reload comes back to the address's conditions, and
    who comes and how many follow the rules the form's own buttons keep."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    calls: list = []
    serve = server(site, plan, calls, {"next": []})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def who():
                return (page.eval_on_selector('input[name="with"]:checked', "e => e.value"),
                        page.text_content('[data-count="adults"] [data-count-value]'),
                        page.text_content('[data-count="seniors"] [data-count-value]'),
                        [page.input_value(f"[data-ages] select >> nth={i}") for i in range(page.locator("[data-ages] select").count())])
            # a plan made in this tab, with likings and a budget
            page.goto("http://site.test/plan/", wait_until="load")
            for v in ("history", "food"):
                page.click(f'label.trp-card:has(input[name="prefs"][value="{v}"])')
            page.click('[data-budget="10000"]')
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            # the hand-over: the form's defaults with the address's values; the kept plan is not shown under them
            page.goto("http://site.test/plan/?move=car&prefs=nature", wait_until="load")
            page.wait_for_timeout(300)
            assert page.locator("#h-result").count() == 0 and page.get_attribute("[data-plan]", "data-prefilled") == ""
            assert page.is_checked('input[name="move"][value="car"]')
            assert page.eval_on_selector_all('input[name="prefs"]:checked', "els => els.map(e => e.value)") == ["nature"]
            assert page.input_value("input[name=budget]") == "" and who() == ("couple", "2", "0", [])
            assert page.url == "http://site.test/plan/"                    # the address is spent: a reload keeps these
            assert page.input_value("input[name=date]") == ""              # no date came: none (review 2026-10-22)
            page.reload(wait_until="load")
            page.wait_for_timeout(300)
            assert page.locator("#h-result").count() == 0 and page.is_checked('input[name="move"][value="car"]')
            assert page.eval_on_selector_all('input[name="prefs"]:checked', "els => els.map(e => e.value)") == ["nature"]
            assert page.input_value("input[name=date]") == ""
            # who comes and how many, as the form's buttons keep them
            page.goto("http://site.test/plan/?with=solo&adults=3&seniors=2", wait_until="load")
            assert who() == ("solo", "1", "1", [])
            assert "혼자(어른 1(65세 이상 1))" in page.text_content("[data-plan-sum]")
            assert page.locator('input[name="prefs"]:checked').count() == 0 and page.is_checked('input[name="move"][value="transit"]')
            page.goto("http://site.test/plan/?with=solo&kids=8", wait_until="load")
            assert who() == ("kids", "2", "0", ["8"])
            page.goto("http://site.test/plan/?with=couple&adults=1&kids=5,3", wait_until="load")
            assert who() == ("kids", "1", "0", ["5", "3"])
            page.goto("http://site.test/plan/?with=kids", wait_until="load")
            assert who() == ("kids", "2", "0", ["7"])
            # no date came over (review 2026-10-22: it was the coming Saturday, a day the reader never chose): the
            # button asks for one and sends nothing until it is picked
            sent = len(calls)
            page.click(".trp-submit")
            assert page.text_content("[data-plan-formerr]") == "날짜를 골라 주세요."
            assert page.evaluate("document.activeElement.name") == "date" and len(calls) == sent
            page.fill("input[name=date]", page.get_attribute("input[name=date]", "min"))
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[-1]["conditions"]
            assert (c["with"], c["adults"], c["seniors"], c["kids"]) == ("kids", 2, 0, [7])
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


PHONE = {"is_mobile": True, "has_touch": True}


@pytest.mark.parametrize("dev", [pytest.param({"viewport": {"width": 360, "height": 740}, **PHONE}, id="360"),
                                 pytest.param({"viewport": {"width": 375, "height": 667}, **PHONE}, id="375"),
                                 pytest.param({"viewport": {"width": 390, "height": 844}, **PHONE}, id="390"),
                                 pytest.param({"viewport": {"width": 1440, "height": 900}}, id="1440")])
def test_in_a_browser_a_hand_over_lands_on_the_form_under_a_line_that_says_so(site, dev):
    """Review 2026-10-18, fourth round: the assistant's hand-over opened /plan/ at its top, the filled form out of sight.
    Now the page opens at the form, under one line in a status region ('대화에서 말한 조건을 채웠어요 …', read out: its
    words come after it is in the page); nothing is sent. A plain visit has no line, stays at the top and moves
    nothing (no layout shift). The line's room is laid out from the first paint (plan.html.j2's head script marks
    <html> when the address carries the form's keys): here plan.js comes well after the paint, as on a slow phone, and
    its words move nothing (put in after the paint, the line pushed the form down: CLS 0.11–0.13 at 360–390px)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import time
    calls: list = []
    serve = server(site, a_plan(plan_paths(site)), calls, {"next": []})

    def slow(route):   # plan.js arrives after the first paint
        if route.request.url.endswith("/assets/plan.js"):
            time.sleep(0.4)
        serve(route)
    shifts = """() => new Promise(r => { let s = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) s += e.value; })
      .observe({ type: 'layout-shift', buffered: true }); setTimeout(() => r(s), 400); })"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(**dev, locale="ko-KR")
            ctx.route("**/*", slow)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            assert page.evaluate(shifts) == 0
            assert page.locator(".trp-handed").is_hidden() and page.evaluate("scrollY") == 0
            assert page.evaluate("document.querySelector('.trp-handed-w').getBoundingClientRect().height") == 0
            page.goto("http://site.test/plan/?days=2&move=car&needs=rain", wait_until="commit")
            # the room is there before plan.js; the words come with it
            page.wait_for_selector("[data-plan-form]", state="attached")
            assert page.evaluate("document.documentElement.classList.contains('trp-handing')")
            line = page.locator(".trp-handed")
            page.wait_for_function("document.querySelector('.trp-handed').textContent !== ''")
            assert line.get_attribute("role") == "status"
            # no date in the address: the words that ask for one and say what was not read is a default (review
            # 2026-10-22: one line claimed every value came from the conversation)
            assert line.text_content() == ("대화에서 읽은 조건만 채웠어요. 날짜는 읽지 못해 비워 뒀으니 골라 주세요. "
                                           "그 밖에 읽지 못한 조건(인원·아이 나이·예산 등)은 기본값이에요.")
            assert page.locator(".trp-handed-ghost").get_attribute("aria-hidden") == "true"
            page.wait_for_timeout(200)
            assert page.evaluate(shifts) == 0
            box = line.bounding_box()
            mast = page.evaluate(TOP_BAR)
            assert page.evaluate("scrollY") > 0 and mast <= box["y"] <= mast + 60, (box, mast)
            # the line sits right above the form's first step, both in view
            step = page.locator(".trp-step").first.bounding_box()
            assert box["y"] + box["height"] <= step["y"] < dev["viewport"]["height"] - 100, (box, step)
            assert page.is_checked('input[name="days"][value="2"]') and page.is_checked('input[name="needs"][value="rain"]')
            assert calls == [] and page.locator("[data-plan-work]").is_hidden()
            assert page.evaluate("() => document.documentElement.scrollWidth") <= dev["viewport"]["width"]
            # keys the form has no choice for: no line, no room
            page.goto("http://site.test/plan/?days=9", wait_until="load")
            page.wait_for_function("!document.documentElement.classList.contains('trp-handing')")
            assert page.locator(".trp-handed").is_hidden() and page.locator(".trp-handed").text_content() == ""
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ the share link and the course sent first (2026-10-19)
SHARE_SECRET = "plan-page-test-secret-0123456789abcdef"  # 37 characters (plan_share.SECRET_MIN 32)
SHARE_COND = {"date": "2026-10-24", "days": 2, "start": "10:00", "end": "21:00", "move": "transit", "with": "kids", "adults": 2,
              "seniors": 0, "kids": [4], "from": "", "to": "", "prefs": ["history"], "needs": ["stroller"], "budget": 10000,
              "note": "짬뽕 먹고 싶어요"}
# the real view handler (chatbot/planner.js createPlanHandler, the knowledge the sample build exported) behind the
# browser's /api/plan/ {view}: one node process, a JSON line in, a JSON line out
NODE_HELPER = r"""
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
const [root, kbDir, secret] = process.argv.slice(2);
const imp = (p) => import(pathToFileURL(`${root}/${p}`).href);
const { createPlanHandler } = await imp("chatbot/planner.js");
const { loadKnowledge } = await imp("chatbot/knowledge.js");
const { canonical, compactOf, signPlan } = await imp("chatbot/plan_share.js");
const kb = await loadKnowledge(kbDir);
for await (const line of createInterface({ input: process.stdin })) {
  const m = JSON.parse(line);
  let out;
  try {
    if (m.op === "sign") out = { sig: signPlan(m.plan, Buffer.from(secret)), canonical: canonical(compactOf(m.plan)) };
    else if (m.op === "canonical") out = { canonical: canonical(m.compact) };
    else {
      const handle = createPlanHandler({ knowledge: async () => kb, env: { PLAN_SHARE_SECRET: secret }, log: () => {},
        now: () => new Date(m.now), client: {} });
      // (the site's own address: docs.json meta.site, the origin the handler allows)
      const res = await handle(new Request(`${kb.site}/api/plan/`, { method: "POST", body: m.body,
        headers: { origin: kb.site, "content-type": "application/json", "x-real-ip": "198.51.100.1" } }));
      out = { status: res.status, body: await res.text() };
    }
  } catch (e) { out = { error: String((e && e.stack) || e) }; }
  process.stdout.write(JSON.stringify(out) + "\n");
}
"""


class NodeView:
    def __init__(self, site, tmp):
        import subprocess
        node = shutil.which("node")
        if not node:
            pytest.skip("Node.js 없음")
        script = Path(tmp) / "view_helper.mjs"
        script.write_text(NODE_HELPER, "utf-8")
        self.proc = subprocess.Popen([node, str(script), str(ROOT), str(site / "chat"), SHARE_SECRET], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.now = "2026-10-19T03:00:00Z"
        self.views: list = []

    def call(self, msg):
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        out = json.loads(self.proc.stdout.readline())
        assert "error" not in out, out.get("error")
        return out

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


# The share-link course is for 2026-10-24 and the view handler's 'today' is 2026-10-19 (NodeView.now): each phone's
# clock starts that same morning, or once the real date passes the trip the page reads it as a course gone by
PHONE_DAY = datetime.datetime(2026, 10, 19, 3, tzinfo=datetime.timezone.utc)


def phone(browser, **kw):
    ctx = browser.new_context(**kw)
    ctx.clock.install(time=PHONE_DAY)   # starts there and flows: timers run as usual
    return ctx


def link_compact(url):
    """The compact form a share link carries (#p=z.<deflate-raw base64url>.<sig>)."""
    import base64
    import zlib
    frag = url.split("#p=", 1)[1]
    kind, data = frag.split(".")[:2]
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return json.loads(zlib.decompress(raw, -15) if kind == "z" else raw)


def pack_link(compact, sig=None):
    import base64
    import zlib
    z = zlib.compressobj(9, zlib.DEFLATED, -15)
    data = z.compress(json.dumps(compact, ensure_ascii=False).encode("utf-8")) + z.flush()
    b64 = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return f"http://site.test/plan/#p=z.{b64}" + (f".{sig}" if sig else "")


def ready_plan(paths):
    plan = a_plan(paths)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    plan.update({"status": "ready", "flags": [], "todo": [], "conditions": dict(SHARE_COND), "aware": []})
    return plan


# GA4 as the page sends it (window.siteTrack; with track.js on the page, through gtag)
GA_STUB = """window.__ga = []; window.gtag = function (kind, name, params) { window.__ga.push([name, params]); };
window.siteTrack = function (name, params) { window.__ga.push([name, params]); };"""
# http://site.test is not a secure context (no navigator.clipboard): a clipboard that keeps what is written
CLIP_STUB = """Object.defineProperty(navigator, 'clipboard', { configurable: true,
  value: { writeText: (t) => { window.__clip = t; return Promise.resolve(); } } });"""


@pytest.mark.parametrize("width", [390, 1440])
def test_in_a_browser_a_plan_passes_on_as_a_link_that_opens_on_another_phone(site, tmp_path, width):
    """Operator 2026-10-19 ('동행이 자기 휴대폰으로 열 수 있는 링크', no server storage): '링크 복사' puts the plan on screen
    in the address fragment with the server's signature — the reader's note never in it, the compact form the server
    signs; a fresh browser opens it (the fragment leaves the address), the server reads it against today's data (the
    real view handler here) and the page shows it as a shared plan: '공유받은 코스예요 · 오늘 자료로 다시 검사했어요',
    its words kept, '이 조건으로 내 코스 만들기'. A tampered link keeps the course and drops the words, saying so — what
    today's data flags on it is '오늘 자료와 맞지 않는 곳', never said to have changed since it was shared; a past date
    says so, and so does a trip under way (its second day: '여행 중인 코스예요', not gone by); a broken link, one past the
    link's bounds or one that inflates past them says it cannot be opened (nothing blown up in the tab, nothing sent).
    An edit of the opened plan sends the plan's base with its signature, so its reasons stay. No sideways scroll."""
    sync_api = pytest.importorskip("playwright.sync_api")
    helper = NodeView(site, tmp_path)
    paths = plan_paths(site)
    plan = ready_plan(paths)
    signed = helper.call({"op": "sign", "plan": plan})
    calls: list = []
    base = server(site, plan, calls, {"next": [sse({"type": "plan", "plan": plan, "sig": signed["sig"]})]})

    def serve(route):
        req = route.request
        if req.url.endswith("/api/plan/") and req.method == "POST" and "view" in (req.post_data_json or {}):
            helper.views.append(req.post_data_json)
            out = helper.call({"op": "view", "body": req.post_data, "now": helper.now})
            return route.fulfill(status=out["status"], body=out["body"], content_type="application/json")
        return base(route)

    dev = {"viewport": {"width": width, "height": 844}, "is_mobile": width < 900, "has_touch": width < 900}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            helper.close()
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.add_init_script(GA_STUB)
            ctx.add_init_script(CLIP_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            assert page.locator(".trp-x-row .trp-x").first.text_content() == "링크 복사"
            assert "링크 복사" in page.text_content(".trp-x-bar .trp-hint")
            page.click(".trp-x-link")
            page.wait_for_function("document.querySelector('.trp-x-msg').textContent.includes('링크를 복사했어요')")
            link = page.evaluate("window.__clip")
            assert link.startswith("http://site.test/plan/#p=z.") and link.endswith("." + signed["sig"])
            assert len(link) < 2000, len(link)
            compact = link_compact(link)
            # the reader's note never rides in a link; what the page packs is what the server signed
            assert "짬뽕 먹고 싶어요" not in json.dumps(compact, ensure_ascii=False) and "note" not in compact["c"]
            assert helper.call({"op": "canonical", "compact": compact})["canonical"] == signed["canonical"]
            assert ["plan_share", {"how": "link"}] in page.evaluate("window.__ga")
            ctx.close()

            # a companion's phone: nothing in its storage
            other = phone(browser, **dev, locale="ko-KR")
            other.add_init_script(GA_STUB)
            other.route("**/*", serve)
            page = other.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(link, wait_until="load")
            page.wait_for_selector("#h-result")
            assert "#p=" not in page.url, "the fragment leaves the address"
            sent = helper.views[-1]["view"]
            assert sent["sig"] == signed["sig"] and sent["compact"]["v"] == 1 and isinstance(sent["compact"]["d"], list)
            bar = page.locator(".trp-shared")
            assert "공유받은 코스예요 · 오늘 자료로 다시 검사했어요" in bar.text_content()
            assert page.get_attribute(".trp-shared-in", "role") == "status"
            assert page.text_content("#h-result") == plan["title"]
            assert page.locator(".trp-r-sum .trp-ai").count() == 1 and "확인할 수 없어" not in bar.text_content()
            assert page.text_content(".trp-r-head .trp-eyebrow") == "공유받은 코스 · 오늘 사이트 자료와 코드로 다시 검사함"
            assert page.locator(".trp-stop").count() == len(plan["days"][0]["stops"])
            res = page.text_content(".trp-result")
            assert "초안" not in res and page.locator(".trp-qfix, .trp-flags").count() == 0
            # what today's data flags (the sample's own pages) is a neutral notice, never a fault
            if page.locator(".trp-changed").count():
                assert page.text_content(".trp-changed h3") == "공유된 뒤 자료가 바뀐 곳"
                assert "is-info" in page.get_attribute(".trp-status", "class")
            assert ["plan_shared_open", {"sig": 1}] in page.evaluate("window.__ga")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            # passed on again from here (no clipboard on this phone: the link in a field) — the same signed link
            page.click(".trp-x-link")
            page.wait_for_function("document.querySelector('.trp-x-url') && document.querySelector('.trp-x-url').value !== ''")
            again = page.input_value(".trp-x-url")
            assert again.endswith("." + signed["sig"]) and link_compact(again) == compact
            assert page.text_content(".trp-x-msg") == "아래 링크를 길게 눌러 복사하세요."
            # a reload shows this tab's state: the shared plan, the address without the fragment
            page.reload(wait_until="load")
            page.wait_for_selector(".trp-shared")
            assert page.text_content("#h-result") == plan["title"] and len(helper.views) == 1
            # an edit of the opened plan carries its base: the compact form without the stops and the signature
            asked = len(calls)
            page.fill("#trp-ask", "카페 하나 넣어 주세요")
            page.click(".trp-edit-f button[type=submit]")
            for _ in range(50):
                if len(calls) > asked:
                    break
                page.wait_for_timeout(100)
            sent = calls[-1]
            assert sent["base"]["sig"] == signed["sig"] and sent["base"]["t"] == plan["title"] and "d" not in sent["base"]
            assert sent["plan"]["days"][0]["stops"][0]["why"] == plan["days"][0]["stops"][0]["why"]
            page.wait_for_selector("#h-result")
            page.reload(wait_until="load")
            page.wait_for_selector("#h-result")
            # its conditions into the form, on a tap (the shared plan opened afresh)
            page.goto(link, wait_until="load")
            page.wait_for_selector(".trp-shared")
            page.click(".trp-shared .trp-early-b")
            assert page.input_value("[data-plan-date]") == "2026-10-24"
            assert page.is_checked('input[name="days"][value="2"]') and page.is_checked('input[name="needs"][value="stroller"]')
            assert page.input_value("textarea[name=note]") == ""
            assert page.evaluate("() => document.activeElement.classList.contains('trp-submit')")
            other.close()

            # a tampered link: the course shown, the words dropped and said so; what today's data flags on it (a stop
            # before the day's start, put there by whoever made the link) is not said to have changed since
            first = compact["d"][0][0]
            forged = dict(compact, t="군산각 공식 추천 맛집 코스", n=["https://evil.example 에서 예약하세요"],
                          d=[[[first[0], "08:00", "09:00", *first[3:]], *compact["d"][0][1:]], *compact["d"][1:]])
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.add_init_script(GA_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(pack_link(forged, signed["sig"]), wait_until="load")
            page.wait_for_selector("#h-result")
            assert "확인할 수 없어 빼고" in page.text_content(".trp-shared")
            assert page.text_content("#h-result") == "10월 24일(토) 군산 1박 2일 코스"
            res = page.text_content(".trp-result")
            assert "evil.example" not in res and "공식 추천" not in res
            assert page.locator(".trp-r-sum .trp-site").count() == 1
            assert page.locator(".trp-r-sum .trp-ai, .trp-why .trp-ai, .trp-notes").count() == 0
            assert page.text_content(".trp-changed h3") == "오늘 자료와 맞지 않는 곳"
            assert page.text_content("#h-status").endswith("오늘 자료와 맞지 않는 곳이 있어요")
            assert "공유된 뒤" not in res and "바뀌어" not in res
            assert ["plan_shared_open", {"sig": 0}] in page.evaluate("window.__ga")
            # an edit of it: '바꾼 뒤 달라진 것' starts from the heading this reader saw (review 2026-10-23: it read
            # '조건을 다 맞추지 못한 초안이에요', a heading a shared plan never shows)
            page.fill("#trp-ask", "카페 하나 넣어 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-diff")
            now = page.text_content("#h-status")[1:]   # (its mark first)
            assert now.startswith("코스 완성 · 가기 전 확인 ")
            assert [x for x in page.locator(".trp-diff li").all_text_contents() if x.startswith("상태: ")] == [
                f"상태: 오늘 자료와 맞지 않는 곳이 있어요 → {now}"]
            ctx.close()

            # the trip under way (its second day): not gone by, no edit box (an edit takes no date gone by)
            helper.now = "2026-10-25T03:00:00Z"
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(link, wait_until="load")
            page.wait_for_selector("#h-result")
            assert "여행 중인 코스예요" in page.text_content(".trp-shared") and "이미 지난" not in page.text_content(".trp-shared")
            assert page.locator(".trp-edit").count() == 0
            page.click(".trp-shared .trp-early-b")
            assert page.text_content("[data-plan-formerr]") == "공유받은 코스는 이미 시작한 여행이에요. 날짜를 다시 골라 주세요."
            ctx.close()

            # a date gone by: shown, said so, no edit box; its conditions go to the form without the date (the link
            # pasted with the sentence's full stop on its end opens all the same)
            helper.now = "2026-11-02T03:00:00Z"
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(link + ".", wait_until="load")
            page.wait_for_selector("#h-result")
            assert helper.views[-1]["view"]["sig"] == signed["sig"]
            assert "이미 지난 날짜의 코스예요" in page.text_content(".trp-shared")
            assert "확인할 수 없어" not in page.text_content(".trp-shared")
            assert page.text_content("#h-result") == plan["title"] and page.locator(".trp-edit").count() == 0
            page.click(".trp-shared .trp-early-b")
            assert page.text_content("[data-plan-formerr]") == "공유받은 코스의 날짜는 이미 지났어요. 날짜를 다시 골라 주세요."
            assert page.evaluate("document.activeElement.name") == "date"
            assert page.is_checked('input[name="days"][value="2"]')
            # a link cut short
            page.goto("http://site.test/plan/#p=z.abc!", wait_until="load")
            page.wait_for_selector(".trp-fail")
            assert page.text_content(".trp-fail h2") == "공유받은 코스를 열지 못했어요"
            page.goto("http://site.test/plan/#p=z.AAAA", wait_until="load")
            page.wait_for_function("document.querySelector('.trp-fail h2') && document.querySelector('.trp-fail p').textContent.includes('링크')")
            # past the link's bounds: refused in the page — longer than 16,000 characters, or inflating past 32 KB
            import base64
            import zlib
            z = zlib.compressobj(9, zlib.DEFLATED, -15)
            bomb = base64.urlsafe_b64encode(z.compress(b" " * 400_000) + z.flush()).decode("ascii").rstrip("=")
            sent_before = len(helper.views)
            for bad in ["http://site.test/plan/#p=z." + "A" * 16_100, "http://site.test/plan/#p=z." + bomb]:
                page.goto("about:blank")
                page.goto(bad, wait_until="load")
                page.wait_for_selector(".trp-fail")
                assert page.text_content(".trp-fail h2") == "공유받은 코스를 열지 못했어요"
            assert len(helper.views) == sent_before, "nothing sent for a link refused in the page"
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()
            helper.close()


# the browser's /api/plan/ for a new plan as a stream the test feeds event by event (window.__streams[i].push(ev))
STREAM_STUB = """(() => {
  const real = window.fetch.bind(window);
  window.__streams = [];
  window.fetch = (url, opts) => {
    let body = null;
    try { body = opts && opts.body ? JSON.parse(opts.body) : null; } catch (e) { /* not JSON */ }
    if (!String(url).endsWith('/api/plan/') || !body || body.view) return real(url, opts);
    let ctl;
    const s = { body, aborted: false };
    const stream = new ReadableStream({ start(c) { ctl = c; } });
    s.push = (ev) => ctl.enqueue(new TextEncoder().encode('data: ' + JSON.stringify(ev) + '\\n\\n'));
    s.end = () => ctl.close();
    if (opts.signal) opts.signal.addEventListener('abort', () => {
      s.aborted = true;
      try { ctl.error(new DOMException('aborted', 'AbortError')); } catch (e) { /* closed */ }
    });
    // the network cut: what a browser's fetch rejects with when the page goes (a reload, a link followed) or the
    // connection drops — a TypeError, not an AbortError (round-6 verifier)
    s.fail = () => { try { ctl.error(new TypeError('network error')); } catch (e) { /* closed */ } };
    window.__streams.push(s);
    return Promise.resolve(new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } }));
  };
  window.addEventListener('pagehide', () => { for (const s of window.__streams) s.fail(); });
  window.__ls = 0;
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__ls += e.value; })
    .observe({ type: 'layout-shift', buffered: true });
})();"""


def early_and_final(paths):
    early = ready_plan(paths)
    early.update({"title": "10월 24일(토) 군산 1박 2일 코스", "summary": "원도심을 둘러보고 식사해요.", "notes": [],
                  "fixed": ["일정 전체: AI가 다듬기 전에 사이트 자료로 먼저 일정을 짰습니다"]})
    for d in early["days"]:
        for st in d["stops"]:
            st.update({"added": True, "why": ""})
    final = ready_plan(paths)
    final["fixed"] = []
    final["days"][0]["stops"][2].update({"start": "13:30", "end": "15:00"})   # the AI moved one stop
    return early, final


@pytest.mark.parametrize("width", [390, 1440])
def test_in_a_browser_the_course_sent_first_then_the_ai_course(site, width):
    """Operator 2026-10-19 (20–40 s of waiting): the site's course comes at once (SSE 'early') under a status line
    with a progress mark and '멈추기', the working view gone. The AI's plan replaces it in place when the reader has
    not touched the result ('AI가 다듬은 코스로 바꿨어요' and what changed), else nothing moves under them — the line
    offers 'AI가 다듬은 코스 보기' (and a fixed toast); '먼저 보여 드린 코스 보기' brings the first back. '멈추기' keeps
    the first course, and so does an error. The line keeps its size in every phase; no layout shift — the course
    coming in place of the working view moves nothing the reader saw (round-6 verifier: the banner and footer under
    the working view were pushed out); no sideways scroll; the tab keeps the plan on screen. After a swap in place
    the focus is where it was (the heading, the line's button) and the line's words are read out; when the AI gave
    nothing (the same course back, built by the site) and the reader is reading, the tab keeps and links the course
    on screen."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    early, final = early_and_final(paths)
    serve = server(site, final, [], {"next": []})
    dev = {"viewport": {"width": width, "height": 844}, "is_mobile": width < 900, "has_touch": width < 900}
    push = lambda page, i, ev: page.evaluate("([i, ev]) => window.__streams[i].push(ev)", [i, ev])  # noqa: E731
    bar_h = "document.querySelector('.trp-early').getBoundingClientRect().height"
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(**dev, locale="ko-KR")
            ctx.add_init_script(GA_STUB)
            ctx.add_init_script(STREAM_STUB)
            ctx.add_init_script(CLIP_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            words = lambda t: page.wait_for_function("t => document.querySelector('.trp-early p.trp-early-t').textContent === t", arg=t)  # noqa: E731

            # 1. nobody touches the course sent first: the AI's replaces it in place
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 1")
            page.wait_for_timeout(800)   # past the click's input window: a shift from here on counts
            page.evaluate("window.__ls = 0")
            push(page, 0, {"type": "early", "plan": early, "sig": "a" * 43})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            assert page.locator("[data-plan-work]").is_hidden()
            assert page.text_content(".trp-early p.trp-early-t") == "사이트 자료로 먼저 짠 코스예요 · AI가 조건에 맞게 다듬는 중"
            assert page.get_attribute(".trp-early p.trp-early-t", "role") == "status"
            assert page.locator(".trp-early .trp-early-m").get_attribute("aria-hidden") == "true"
            assert page.text_content(".trp-early button") == "멈추기" and page.is_visible(".trp-early button")
            assert page.text_content("#h-result") == early["title"]
            assert page.text_content(".trp-r-head .trp-eyebrow") == "사이트 자료로 짜고 코드로 검사한 코스"
            assert page.locator(".trp-r-sum .trp-ai").count() == 0, "the site's summary is not marked AI"
            # the stops' own buttons wait while the AI refines it (operator 2026-10-23): their room kept, out of sight
            # and reach (inert), so nothing moves when they come
            assert page.locator(".trp-acts").count() > 0 and page.locator(".trp-acts:not([inert])").count() == 0
            assert not page.is_visible(".trp-acts .trp-act >> nth=0")
            assert ["plan_early", {"days": 1}] in page.evaluate("window.__ga")   # the form's days (the stub's plan has two)
            page.wait_for_timeout(700)   # the page's own smooth scroll to the result
            assert page.evaluate("window.__ls") < 0.01, page.evaluate("window.__ls")
            assert page.evaluate("document.activeElement.id") == "h-result"
            h0, y0 = page.evaluate(bar_h), page.evaluate("scrollY")
            push(page, 0, {"type": "status", "step": "submit", "text": "…"})
            push(page, 0, {"type": "plan", "plan": final, "sig": "b" * 43})
            page.evaluate("window.__streams[0].end()")
            page.wait_for_selector(".trp-early[data-phase=swapped]")
            words("AI가 다듬은 코스로 바꿨어요")
            assert page.evaluate("document.activeElement.id") == "h-result", "the focus is where it was"
            assert page.text_content("#h-result") == final["title"]
            assert page.text_content("#h-diff") == "먼저 보여 드린 코스와 달라진 것"
            assert any("13:30~15:00" in x for x in page.locator(".trp-diff li").all_text_contents())
            assert page.evaluate(bar_h) == h0 and abs(page.evaluate("scrollY") - y0) <= 1
            assert page.locator(".trp-acts[inert]").count() == 0 and page.is_visible(".trp-acts .trp-act >> nth=0")
            assert ["plan_swap", {"auto": 1}] in page.evaluate("window.__ga")
            kept = page.evaluate("JSON.parse(sessionStorage.getItem('gs-plan'))")
            assert kept["plan"]["title"] == final["title"] and kept["early"]["plan"]["title"] == early["title"]
            # back to the first and again
            page.click(".trp-early button")
            assert page.text_content("#h-result") == early["title"]
            words("먼저 보여 드린 코스예요")
            assert page.evaluate("document.activeElement.textContent") == "AI가 다듬은 코스 보기", "the line's button keeps the focus"
            assert page.locator(".trp-diff").count() == 0 and page.evaluate(bar_h) == h0
            assert page.evaluate("JSON.parse(sessionStorage.getItem('gs-plan')).plan.title") == early["title"]
            page.click(".trp-early button")
            assert page.text_content("#h-result") == final["title"]
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            # an edit: the working view (a screen tall) goes before the changed course is scrolled to, so the course's
            # top lands at the window's top, not a screen above it
            page.fill("#trp-ask", "카페 하나 넣어 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_function("window.__streams.length === 2")
            page.wait_for_timeout(700)
            assert page.locator("[data-plan-work]").is_visible()
            assert page.evaluate("document.querySelector('[data-plan-work]').getBoundingClientRect().height") >= 844 - 1
            push(page, 1, {"type": "plan", "plan": final, "sig": "e" * 43})
            page.evaluate("window.__streams[1].end()")
            page.wait_for_selector("#h-diff")
            page.wait_for_timeout(1200)
            top = page.evaluate("document.querySelector('.trp-result').getBoundingClientRect().top")
            mast = page.evaluate(TOP_BAR)
            assert abs(top - mast) <= 40, (top, mast)
            assert page.locator("[data-plan-work]").is_hidden()
            page.evaluate("window.__streams.length = 1")   # the indices below count the new plans only

            # 2. the reader is reading further down: nothing moves; the line and a toast offer the AI's course
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 2")
            push(page, 1, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.wait_for_timeout(700)
            page.evaluate("document.querySelector('.trp-edit').scrollIntoView({block: 'center'})")
            page.wait_for_timeout(150)
            before = page.evaluate("[scrollY, document.querySelector('.trp-edit').getBoundingClientRect().top]")
            page.evaluate("window.__ls = 0")
            push(page, 1, {"type": "plan", "plan": final})
            page.evaluate("window.__streams[1].end()")
            page.wait_for_selector(".trp-early[data-phase=ready]")
            assert page.text_content(".trp-early p.trp-early-t") == "AI가 다듬은 코스가 왔어요"
            assert page.text_content(".trp-early button") == "AI가 다듬은 코스 보기"
            assert page.text_content("#h-result") == early["title"], "not replaced under the reader"
            page.wait_for_timeout(150)
            assert page.evaluate("[scrollY, document.querySelector('.trp-edit').getBoundingClientRect().top]") == before
            assert page.evaluate("window.__ls") == 0 and page.evaluate(bar_h) == h0
            toast = page.locator(".trp-toast")
            assert toast.is_visible() and "AI가 다듬은 코스가 왔어요" in toast.text_content()
            tb = toast.bounding_box()
            assert tb["x"] >= 0 and tb["x"] + tb["width"] <= width and tb["y"] + tb["height"] <= 844
            page.click(".trp-toast-go")
            assert page.text_content("#h-result") == final["title"] and page.locator(".trp-toast").count() == 0
            assert page.evaluate("document.activeElement.id") == "h-result"
            assert ["plan_swap", {"auto": 0}] in page.evaluate("window.__ga")

            # 3. 멈추기 keeps the course sent first (and a reload shows it)
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 3")
            push(page, 2, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.click(".trp-early button")
            page.wait_for_selector(".trp-early[data-phase=stopped]")
            assert page.evaluate("window.__streams[2].aborted")
            assert page.text_content(".trp-early p.trp-early-t") == "다듬기를 멈췄어요 · 먼저 짠 코스를 그대로 둬요"
            assert page.text_content("#h-result") == early["title"] and page.locator(".trp-fail").count() == 0
            assert page.evaluate("getComputedStyle(document.querySelector('.trp-early button')).visibility") == "hidden"
            assert page.evaluate(bar_h) == h0
            page.reload(wait_until="load")
            page.wait_for_selector("#h-result")
            assert page.text_content("#h-result") == early["title"]
            assert page.text_content(".trp-early p.trp-early-t") == "다듬기를 멈췄어요 · 먼저 짠 코스를 그대로 둬요"

            # 4. the AI's course fails (an error at the end): the first stays, no failure page
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 1")
            push(page, 0, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            push(page, 0, {"type": "error", "code": "error", "message": "코스를 만들지 못했습니다. 다시 시도해 주세요."})
            page.evaluate("window.__streams[0].end()")
            page.wait_for_selector(".trp-early[data-phase=kept]")
            assert page.text_content("#h-result") == early["title"] and page.locator(".trp-fail").count() == 0
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width

            # 5. the AI gave nothing (the server's final plan is the same course, its line saying why) while the reader
            # reads further down: the tab keeps — and links — the course on screen, not the one behind the line
            failed = dict(early, fixed=["일정 전체: AI가 조건에 맞는 일정을 내지 못해 사이트 자료로 일정을 짰습니다"])
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 2")
            push(page, 1, {"type": "early", "plan": early, "sig": "c" * 43})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.wait_for_timeout(700)
            page.evaluate("document.querySelector('.trp-edit').scrollIntoView({block: 'center'})")
            page.wait_for_timeout(150)
            push(page, 1, {"type": "plan", "plan": failed, "sig": "d" * 43})
            page.evaluate("window.__streams[1].end()")
            page.wait_for_selector(".trp-early[data-phase=kept]")
            assert page.text_content(".trp-early p.trp-early-t") == "AI가 다듬지 못해 먼저 짠 코스를 그대로 둬요"
            assert "AI가 다듬기 전에" in page.text_content(".trp-r-code")
            kept = page.evaluate("JSON.parse(sessionStorage.getItem('gs-plan'))")
            assert kept["plan"]["fixed"] == early["fixed"] and kept["sig"] == "c" * 43 and kept["final"]["sig"] == "d" * 43
            page.click(".trp-x-link")
            page.wait_for_function("document.querySelector('.trp-x-msg').textContent.includes('링크를 복사했어요')")
            assert page.evaluate("window.__clip").endswith("." + "c" * 43)
            assert page.locator(".trp-toast").count() == 0
            # an AI course with the same stops and its own words is the AI's: offered, not 'kept'
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 3")
            push(page, 2, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.wait_for_timeout(700)
            push(page, 2, {"type": "plan", "plan": dict(early, title="AI가 쓴 제목", fixed=[])})
            page.evaluate("window.__streams[2].end()")
            page.wait_for_selector(".trp-early[data-phase=swapped]")
            assert page.text_content("#h-result") == "AI가 쓴 제목"
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


# what a layout shift without input adds up to, from the first paint (no touch emulation: a phone's emulated touch marks
# every shift as following input, which hides it — round-6 verifier)
CLS_STUB = """window.__ls = 0; window.__lsAt = [];
new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__ls += e.value;
  window.__lsAt.push([Math.round(e.startTime), +e.value.toFixed(4), (e.sources || []).map((x) => [x.node && (x.node.className || x.node.nodeName),
    Math.round(x.previousRect.y), Math.round(x.previousRect.height), Math.round(x.currentRect.y), Math.round(x.currentRect.height)]), Math.round(scrollY)]); } })
  .observe({ type: 'layout-shift', buffered: true });"""
# analytics that outlive a reload (what the page sent while it was going)
GA_KEPT = """window.siteTrack = function (name, params) { try { const a = JSON.parse(localStorage.getItem('__ga') || '[]');
  a.push([name, params]); localStorage.setItem('__ga', JSON.stringify(a)); } catch (e) {} };"""


@pytest.mark.parametrize("width", [390, 1440])
def test_in_a_browser_a_plan_drawn_on_load_moves_nothing_and_a_reload_while_refining_is_a_cut(site, tmp_path, width):
    """Round-6 verifier. A plan the page draws as it loads — a share link opened (its view a second late), a link pasted
    into a tab already on /plan/, a reload of the tab's plan (twice) — has its room from the first paint, so nothing
    under it (the crumbs, the footer) is pushed out: no layout shift without input (it was 0.74–0.91). A reload puts
    the reader back where they were once the plan is drawn. The bar's words describe the course's heading (a screen
    reader hears '공유받은 코스예요 …' with it). A reload while the AI refines is a cut — '다듬는 중에 끊겨 …', nothing
    counted as an error — and a connection that drops is one too; '멈추기' leaves the focus on the bar's words."""
    sync_api = pytest.importorskip("playwright.sync_api")
    helper = NodeView(site, tmp_path)
    paths = plan_paths(site)
    plan = ready_plan(paths)
    signed = helper.call({"op": "sign", "plan": plan})
    early, final = early_and_final(paths)
    base = server(site, final, [], {"next": []})

    def serve(route):
        req = route.request
        if req.url.endswith("/api/plan/") and req.method == "POST" and "view" in (req.post_data_json or {}):
            import time
            time.sleep(0.9)   # the server a second late: the room is held all that while
            out = helper.call({"op": "view", "body": req.post_data, "now": helper.now})
            return route.fulfill(status=out["status"], body=out["body"], content_type="application/json")
        return base(route)

    dev = {"viewport": {"width": width, "height": 844}, "is_mobile": False, "has_touch": False}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            helper.close()
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            # 1. a share link opened on a companion's phone
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.add_init_script(CLS_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            first = {"date": "2026-10-24", "days": 2}
            compact = helper.call({"op": "canonical", "compact": {"v": 1, "c": first, "t": "", "s": "", "n": [], "d": []}}) and None
            link = None
            # the link the page itself makes, from a plan drawn in another tab
            other = phone(browser, **dev, locale="ko-KR")
            other.add_init_script(CLIP_STUB)
            other.route("**/*", base)
            o = other.new_page()
            o.goto("http://site.test/plan/", wait_until="load")
            o.evaluate("([p, sig]) => sessionStorage.setItem('gs-plan', JSON.stringify({ conditions: p.conditions, plan: p, sig }))", [plan, signed["sig"]])
            o.reload(wait_until="load")
            o.wait_for_selector("#h-result")
            o.click(".trp-x-link")
            o.wait_for_function("document.querySelector('.trp-x-msg').textContent.includes('링크를 복사했어요')")
            link = o.evaluate("window.__clip")
            other.close()
            assert link and link.endswith("." + signed["sig"]), (link, compact, first)
            page.goto(link, wait_until="load")
            page.wait_for_selector(".trp-shared")
            page.wait_for_timeout(1200)
            assert page.evaluate("window.__ls") < 0.001, page.evaluate("window.__lsAt")
            said = page.evaluate("(() => { const h = document.getElementById('h-result'); const d = h.getAttribute('aria-describedby'); return d && document.getElementById(d).textContent; })()")
            assert said and "공유받은 코스예요 · 오늘 자료로 다시 검사했어요" in said, said
            assert page.evaluate("document.documentElement.classList.contains('trp-holding')") is False
            assert page.evaluate("document.querySelector('[data-plan-result]').classList.contains('trp-hold')") is False

            # 2. two reloads of the plan this tab keeps: nothing moves, the reader is put back where they were
            for _ in range(2):
                page.evaluate("document.querySelector('.trp-edit').scrollIntoView({block: 'start'})")
                page.wait_for_timeout(200)
                y = page.evaluate("scrollY")
                page.reload(wait_until="load")
                page.wait_for_selector(".trp-shared")
                page.wait_for_timeout(1200)
                assert page.evaluate("window.__ls") < 0.001, page.evaluate("window.__lsAt")
                assert abs(page.evaluate("scrollY") - y) <= 2, (page.evaluate("scrollY"), y)
            ctx.close()

            # 3. the link pasted into a tab already on /plan/ (only the fragment changes)
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.add_init_script(CLS_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.wait_for_timeout(600)
            page.evaluate("window.__ls = 0; window.__lsAt = []")
            page.evaluate("h => { location.hash = h; }", link.split("/plan/", 1)[1])
            page.wait_for_selector(".trp-shared")
            page.wait_for_timeout(1200)
            assert page.evaluate("window.__ls") < 0.001, page.evaluate("window.__lsAt")
            assert "#p=" not in page.url
            ctx.close()

            # 4. a reload while the AI refines: a cut, not the AI failing — and nothing counted as an error
            ctx = phone(browser, **dev, locale="ko-KR")
            ctx.add_init_script(GA_KEPT)
            ctx.add_init_script(STREAM_STUB)
            ctx.route("**/*", base)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            push = lambda i, ev: page.evaluate("([i, ev]) => window.__streams[i].push(ev)", [i, ev])  # noqa: E731
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 1")
            push(0, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.reload(wait_until="load")
            page.wait_for_selector(".trp-early")
            assert page.text_content(".trp-early p.trp-early-t") == "다듬는 중에 끊겨 먼저 짠 코스를 그대로 둬요"
            assert page.text_content("#h-result") == early["title"]
            sent = [x[0] for x in page.evaluate("JSON.parse(localStorage.getItem('__ga') || '[]')")]
            assert "plan_early" in sent and "plan_error" not in sent, sent
            # a connection that drops while the reader stays: a cut as well (counted as one)
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 1")
            push(0, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.evaluate("window.__streams[0].fail()")
            page.wait_for_selector(".trp-early[data-phase=cut]")
            assert page.text_content(".trp-early p.trp-early-t") == "다듬는 중에 끊겨 먼저 짠 코스를 그대로 둬요"
            assert ["plan_error", {"code": "cut"}] in page.evaluate("JSON.parse(localStorage.getItem('__ga') || '[]')")
            # 5. '멈추기' by the keyboard: the focus stays on the bar's words, never the page's top
            page.click(".trp-submit")
            page.wait_for_function("window.__streams.length === 2")
            push(1, {"type": "early", "plan": early})
            page.wait_for_selector(".trp-early[data-phase=wait]")
            page.focus(".trp-early button")
            page.keyboard.press("Enter")
            page.wait_for_selector(".trp-early[data-phase=stopped]")
            assert page.evaluate("document.activeElement.id") == "trp-line"
            assert page.evaluate("document.activeElement.textContent") == "다듬기를 멈췄어요 · 먼저 짠 코스를 그대로 둬요"
            assert page.evaluate("document.getElementById('h-result').getAttribute('aria-describedby')") == "trp-line"
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()
            helper.close()


@pytest.mark.parametrize("width", [360, 390])
def test_in_a_browser_the_line_over_the_course_never_moves_when_its_words_change_on_a_phone(site, width):
    """Round-6 final verifier: on a phone the line's words of two lines ('사이트 자료로 먼저 짠 코스예요 · AI가 …')
    became one ('AI가 다듬은 코스로 바꿨어요', 'AI가 다듬지 못해 …') at the swap in place and at the 'kept' redraw, and,
    centred in the room the longest words keep, moved half a line (CLS 0.00046, source #trp-line). The words now sit
    at the top of that room: no layout shift without input (no touch emulation, which would hide it)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    early, final = early_and_final(paths)
    kept = {**early, "fixed": ["일정 전체: AI 응답을 받지 못해 사이트 자료로 일정을 짰습니다"]}
    serve = server(site, final, [], {"next": []})
    push = lambda page, i, ev: page.evaluate("([i, ev]) => window.__streams[i].push(ev)", [i, ev])  # noqa: E731
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 800}, is_mobile=False, has_touch=False, locale="ko-KR")
            ctx.add_init_script(CLS_STUB)
            ctx.add_init_script(STREAM_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/plan/", wait_until="load")
            line_h = "document.querySelector('#trp-line').getBoundingClientRect().height"
            line_y = "document.querySelector('#trp-line').getBoundingClientRect().top - document.querySelector('.trp-early').getBoundingClientRect().top"
            for i, (last, phase) in enumerate([(final, "swapped"), (kept, "kept")]):
                page.click(".trp-submit")
                page.wait_for_function(f"window.__streams.length === {i + 1}")
                push(page, i, {"type": "early", "plan": early, "sig": "a" * 43})
                page.wait_for_selector(".trp-early[data-phase=wait]")
                page.wait_for_timeout(900)   # the page's own scroll to the result, and past the click's input window
                h0, y0 = page.evaluate(line_h), page.evaluate(line_y)
                assert h0 > 30, "the words of the wait take two lines at this width"
                page.evaluate("window.__ls = 0; window.__lsAt = []")
                push(page, i, {"type": "plan", "plan": last, "sig": "b" * 43})
                page.evaluate(f"window.__streams[{i}].end()")
                page.wait_for_selector(f".trp-early[data-phase={phase}]")
                page.wait_for_timeout(400)   # the words change a moment after the line is back (read out)
                assert page.evaluate(line_h) < h0, "one line now"
                assert page.evaluate(line_y) == y0, "the words' first line stays where it was"
                assert page.evaluate("window.__lsAt") == [] and page.evaluate("window.__ls") == 0, (phase, page.evaluate("window.__lsAt"))
                assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ half-hour start and end (outside tester 2026-10-23)
HALF_STARTS = [f"{m // 60:02d}:{m % 60:02d}" for m in range(7 * 60, 14 * 60 + 1, 30)]
HALF_ENDS = [f"{m // 60:02d}:{m % 60:02d}" for m in range(15 * 60, 22 * 60 + 1, 30)]


def test_the_day_s_start_and_end_come_every_half_hour(site):
    """Outside tester 2026-10-23: a 10:30 train could not be entered — the form offered the day's start and end on the
    hour only. Every half hour now: a start 07:00–14:00, an end 15:00–22:00, the defaults 10:00 and 18:00 as before."""
    html = (site / "plan" / "index.html").read_text("utf-8")
    for name, want, default in (("start", HALF_STARTS, "10:00"), ("end", HALF_ENDS, "18:00")):
        select = re.search(rf'<select name="{name}">(.*?)</select>', html).group(1)
        opts = re.findall(r'<option value="([^"]+)"( selected)?>([^<]+)</option>', select)
        assert [v for v, _, _ in opts] == want, name
        assert [v for v, sel, _ in opts if sel] == [default], name
        assert [t for _, _, t in opts] == [f"{int(v[:2])}:{v[3:]}" for v in want], name   # '7:30', '10:30'
    assert len(HALF_STARTS) == len(HALF_ENDS) == 15 and "10:30" in HALF_STARTS and "17:30" in HALF_ENDS


def test_in_a_browser_half_hour_times_go_through_the_form_a_reload_and_a_share_link(site, tmp_path):
    """A 10:30 train and a 17:30 one: the assistant's hand-over (/plan/?start=10:30&end=17:30) fills the selects — a time
    off the half hour (10:20) is not one of the form's and leaves the default —, the summary says '군산역 10:30 출발 →
    군산역 17:30 도착', the three hours are counted by the minute (12:30–15:00 is refused at the button, nothing sent),
    the request carries '10:30' and '17:30', a reload puts them back, the share link carries them, and a companion's
    phone that opens it puts them in its form with '이 조건으로 내 코스 만들기' (the real view handler)."""
    import datetime
    sync_api = pytest.importorskip("playwright.sync_api")
    helper = NodeView(site, tmp_path)
    paths = plan_paths(site)
    plan = ready_plan(paths)
    plan["conditions"] = dict(SHARE_COND, start="10:30", end="17:30")
    plan["days"][0]["stops"][0]["start"] = "10:30"
    signed = helper.call({"op": "sign", "plan": plan})
    calls: list = []
    base = server(site, plan, calls, {"next": [sse({"type": "plan", "plan": plan, "sig": signed["sig"]})]})

    def serve(route):
        req = route.request
        if req.url.endswith("/api/plan/") and req.method == "POST" and "view" in (req.post_data_json or {}):
            helper.views.append(req.post_data_json)
            out = helper.call({"op": "view", "body": req.post_data, "now": helper.now})
            return route.fulfill(status=out["status"], body=out["body"], content_type="application/json")
        return base(route)

    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    dev = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            helper.close()
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(**dev, locale="ko-KR")
            ctx.add_init_script(CLIP_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # a time off the half hour is none of the form's: the defaults stay
            page.goto("http://site.test/plan/?start=10:20&end=17:50", wait_until="load")
            assert (page.input_value("select[name=start]"), page.input_value("select[name=end]")) == ("10:00", "18:00")
            # the hand-over of a 10:30 arrival and a 17:30 departure at 군산역
            page.goto(f"http://site.test/plan/?date={day}&start=10:30&end=17:30&from=station&to=station", wait_until="load")
            assert (page.input_value("select[name=start]"), page.input_value("select[name=end]")) == ("10:30", "17:30")
            assert "군산역 10:30 출발 → 군산역 17:30 도착" in page.text_content("[data-plan-sum]")
            # three hours by the minute: 12:30–15:00 is two and a half (on the hour it read as three)
            page.select_option("select[name=start]", "12:30")
            page.select_option("select[name=end]", "15:00")
            page.click(".trp-submit")
            assert page.is_visible("[data-plan-formerr]")
            assert page.text_content("[data-plan-formerr]") == "하루 일정은 3시간 이상으로 골라 주세요."
            page.wait_for_timeout(200)
            assert calls == []
            page.select_option("select[name=start]", "10:30")
            page.select_option("select[name=end]", "17:30")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[0]["conditions"]
            assert (c["date"], c["start"], c["end"], c["from"], c["to"]) == (day, "10:30", "17:30", "station", "station")
            # a reload: the plan and the form's half hours come back
            page.reload(wait_until="load")
            page.wait_for_selector("#h-result")
            assert (page.input_value("select[name=start]"), page.input_value("select[name=end]")) == ("10:30", "17:30")
            # the share link carries them, as the server signed them
            page.click(".trp-x-link")
            page.wait_for_function("document.querySelector('.trp-x-msg').textContent.includes('링크를 복사했어요')")
            link = page.evaluate("window.__clip")
            assert link.endswith("." + signed["sig"])
            compact = link_compact(link)
            assert (compact["c"]["start"], compact["c"]["end"]) == ("10:30", "17:30") and compact["d"][0][0][1] == "10:30"
            assert helper.call({"op": "canonical", "compact": compact})["canonical"] == signed["canonical"]
            ctx.close()

            # a companion's phone: the link opens, its conditions go into the form on a tap — the half hours too
            other = browser.new_context(**dev, locale="ko-KR")
            other.route("**/*", serve)
            page = other.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(link, wait_until="load")
            page.wait_for_selector(".trp-shared")
            assert helper.views[-1]["view"]["sig"] == signed["sig"]
            assert "10:30" in page.text_content(".trp-stop")
            page.click(".trp-shared .trp-early-b")
            assert (page.input_value("select[name=start]"), page.input_value("select[name=end]")) == ("10:30", "17:30")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            assert errors == [], errors
            other.close()
        finally:
            browser.close()
            helper.close()


@pytest.mark.parametrize("width", [360, 390, 1280])
def test_in_a_browser_each_stop_has_its_own_buttons_that_change_the_plan_in_place(site, width):
    """Operator 2026-10-23 (mockup A, '니 추천대로 진행하고 배포해'): under each stop's facts a dashed hairline and three
    outlined pills, 44px tall — 빼기 · 다른 곳으로 · 고정 — on one line across the card on a phone, together at the left on a
    wide screen; a night's stay has no 다른 곳으로, a day's only stop no 빼기. 고정 toggles (aria-pressed, '고정됨') and holds
    다른 곳으로 while pinned (its reason in its title); the pins stay in the tab and ride with every later edit. 빼기 sends
    the plan on screen with its base and an act — no request, no working view — and the timeline is drawn again in place:
    the server's lines first in '바꾼 뒤 달라진 것', the focus on the stop after the one taken out. A shared plan has no
    buttons."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    plan = a_plan(paths, days=1)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    plan.update({"status": "ready", "flags": [], "todo": [], "conditions": dict(SHARE_COND, days=1), "aware": []})
    a, b, c, d = paths
    name = lambda p: p.split("/")[2]  # noqa: E731
    # the server's answer to 빼기 on the third stop: the stops after it sooner, its lines first
    dropped = json.loads(json.dumps(plan))
    dropped["days"][0]["stops"] = [s for s in dropped["days"][0]["stops"] if s["path"] != c]
    dropped["days"][0]["legs"] = dropped["days"][0]["legs"][:1]
    dropped["edited"] = [{"k": "act", "t": f"{name(c)}를 뺐어요"}]
    calls: list = []
    script = {"next": [sse({"type": "plan", "plan": plan, "sig": "s" * 43}),
                       sse({"type": "status", "step": "fees", "text": "입장료와 조건을 확인하고 있어요"},
                           {"type": "plan", "plan": dropped, "sig": "t" * 43, "act": {"op": "drop", "day": 0, "from": c, "to": None}})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 844}, locale="ko-KR")
            ctx.add_init_script(GA_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            stops = page.locator(".trp-tl .trp-stop")
            assert stops.count() == 4 and page.locator(".trp-tl .trp-stop .trp-acts").count() == 4
            labels = [stops.nth(i).locator(".trp-act .trp-act-t").all_text_contents() for i in range(4)]
            assert labels == [["빼기", "다른 곳으로", "고정"]] * 3 + [["빼기", "고정"]], labels   # the stay: no 다른 곳으로
            # a place with no point on the site: 다른 곳으로 waits, saying why (nothing to search near)
            for i, path in enumerate(paths[:3]):
                held = stops.nth(i).locator("[data-act=swap]").get_attribute("aria-disabled")
                assert (held == "true") == (not places[path].get("g")), (path, held)
            row = stops.nth(0).locator(".trp-acts")
            assert row.get_attribute("role") == "group" and row.get_attribute("aria-label") == f"{name(a)} 바꾸기"
            assert "dashed" in page.evaluate("(el) => getComputedStyle(el).borderTopStyle", row.element_handle())
            # (read in one go: the page is still scrolling smoothly to the result)
            box, buttons = page.evaluate("""() => {
              const r = document.querySelector('.trp-tl .trp-stop .trp-acts'), at = (x) => { const b = x.getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height }; };
              return [at(r), [...r.querySelectorAll('.trp-act')].map(at)];
            }""")
            assert all(x["height"] >= 44 for x in buttons), buttons
            assert len({round(x["y"]) for x in buttons}) == 1, "one line"
            if width < 600:   # across the card
                assert buttons[0]["x"] - box["x"] < 2 and box["x"] + box["width"] - (buttons[2]["x"] + buttons[2]["width"]) < 2, (box, buttons)
            else:             # together at the left, each as wide as its words
                gaps = [buttons[i + 1]["x"] - (buttons[i]["x"] + buttons[i]["width"]) for i in range(2)]
                assert buttons[0]["x"] - box["x"] < 2 and all(g <= 8 for g in gaps), (box, buttons)
                assert box["x"] + box["width"] - (buttons[2]["x"] + buttons[2]["width"]) > 20, (box, buttons)
            # the focus is seen
            drop0 = stops.nth(0).locator("[data-act=drop]")
            drop0.focus()
            page.keyboard.press("Tab")
            ring = page.evaluate("() => [document.activeElement.getAttribute('data-act'), getComputedStyle(document.activeElement).outlineStyle, getComputedStyle(document.activeElement).outlineWidth]")
            assert ring == ["swap", "solid", "3px"], ring
            # 고정: a toggle; while pinned, 다른 곳으로 waits and says why
            pin = stops.nth(0).locator("[data-act=pin]")
            swap = stops.nth(0).locator("[data-act=swap]")
            assert pin.get_attribute("aria-pressed") == "false" and pin.text_content() == "고정"
            pin.click()
            assert pin.get_attribute("aria-pressed") == "true" and pin.text_content() == "고정됨"
            assert swap.text_content() == "다른 곳으로 — 고정한 곳이라 다른 곳으로 바꾸지 않아요 — 고정을 풀면 바꿀 수 있어요"   # (its name for a screen reader)
            assert swap.get_attribute("aria-disabled") == "true" and "고정한 곳이라" in swap.get_attribute("title")
            assert json.loads(page.evaluate("() => sessionStorage.getItem('gs-plan')"))["pins"] == [f"0|{a}"]
            # with '고정됨' (wider than '고정') every label still sits inside its pill, the three on one line (review:
            # at 360px 다른 곳으로 ran past its pill)
            pills = page.evaluate("""() => [...document.querySelector('.trp-tl .trp-stop .trp-acts').querySelectorAll('.trp-act')].map((b) => {
              const r = b.getBoundingClientRect(), t = b.querySelector('.trp-act-t').getBoundingClientRect();
              return [Math.round(r.top), t.left - r.left, r.right - t.right]; })""")
            assert len({x[0] for x in pills}) == 1 and all(x[1] >= 8 and x[2] >= 8 for x in pills), pills
            swap.dispatch_event("click")   # does nothing while pinned
            assert len(calls) == 1
            # 빼기 on the third stop: the plan on screen with its base and the act, the pins with it — no request
            y0 = page.evaluate("() => scrollY")
            stops.nth(2).locator("[data-act=drop]").click()
            page.wait_for_function("() => document.querySelectorAll('.trp-tl .trp-stop').length === 3")
            page.wait_for_selector(".trp-diff")
            sent = calls[-1]
            assert sent["act"] == {"op": "drop", "day": 0, "page": c} and "request" not in sent
            assert sent["pins"] == [{"day": 0, "page": a}]
            assert sent["base"]["sig"] == "s" * 43 and sent["base"]["t"] == plan["title"]
            assert [s["page"] for s in sent["plan"]["days"][0]["stops"]] == [a, b, c, d]
            assert page.is_hidden("[data-plan-work]")
            assert page.locator(".trp-tl .trp-stop h3").all_text_contents() == [name(a), name(b), name(d)]
            assert page.locator(".trp-diff li").all_text_contents()[0] == f"{name(c)}를 뺐어요"
            assert not any(t.endswith(" 뺌") for t in page.locator(".trp-diff li").all_text_contents())
            # the focus on the stop after the one taken out; the course stays where the reader was
            assert page.evaluate("() => document.activeElement.closest('.trp-stop').getAttribute('data-path')") == d
            assert page.evaluate("() => document.activeElement.tagName") == "A"
            assert page.evaluate("() => scrollY") > 0 and abs(page.evaluate("() => scrollY") - y0) < 1600
            page.wait_for_function("(t) => [...document.querySelectorAll('[role=status]')].some((x) => x.textContent === t)", arg=f"{name(c)}를 뺐어요")
            ga = [e for e in page.evaluate("window.__ga") if e[0] == "plan_edit"]
            assert ga and ga[-1][1]["kind"] == "drop", ga
            # the pin is still there (and pressed) on the plan drawn again, and a typed edit carries it
            assert page.locator(".trp-tl .trp-stop").nth(0).locator("[data-act=pin]").get_attribute("aria-pressed") == "true"
            page.fill("#trp-ask", "카페 하나 넣어 주세요")
            page.click(".trp-edit-f button[type=submit]")
            for _ in range(50):
                if len(calls) > 2:
                    break
                page.wait_for_timeout(100)
            assert calls[-1]["request"] == "카페 하나 넣어 주세요" and calls[-1]["pins"] == [{"day": 0, "page": a}] and "act" not in calls[-1]
            page.wait_for_selector("#h-result")
            # a reload keeps the pins with the plan
            page.reload(wait_until="load")
            page.wait_for_selector(".trp-tl .trp-stop .trp-acts")
            assert page.locator(".trp-tl .trp-stop").nth(0).locator("[data-act=pin]").get_attribute("aria-pressed") == "true"
            # 빼기 on a pinned stop unpins it (the reader takes it out)
            script["next"].append(sse({"type": "plan", "plan": dropped, "sig": "u" * 43, "act": {"op": "drop", "day": 0, "from": a, "to": None}}))
            page.locator(".trp-tl .trp-stop").nth(0).locator("[data-act=drop]").click()
            for _ in range(50):
                if calls[-1].get("act", {}).get("page") == a:
                    break
                page.wait_for_timeout(100)
            assert calls[-1]["act"]["page"] == a and "pins" not in calls[-1]
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            assert errors == [], errors
            ctx.close()

            # a shared plan: no buttons
            other = browser.new_context(viewport={"width": width, "height": 844}, locale="ko-KR")
            script["next"].append((200, {"type": "view", "plan": plan, "sig": None, "signed": True, "words": True, "past": False, "during": False, "dropped": 0}))
            other.route("**/*", serve)
            page = other.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(pack_link({"v": 1, "c": {"date": "2026-10-24", "days": 1}, "t": "x", "s": "", "n": [], "d": [[[name(a), "10:00", "11:30", "v"]]]}, "v" * 43), wait_until="load")
            page.wait_for_selector(".trp-shared")
            assert page.locator(".trp-tl .trp-stop").count() == 4 and page.locator(".trp-acts, .trp-act").count() == 0
            assert errors == [], errors
            other.close()
        finally:
            browser.close()


def test_in_a_browser_a_stop_button_that_fails_keeps_the_pin_and_tries_again_in_place(site):
    """Review of the stop buttons: 빼기 on a pinned stop goes unpinned, but the pin is the page's until the stop is out —
    a 빼기 that fails leaves it pinned (it was dropped on screen before the answer came); '다시 시도' sends the same act
    the way the button did: no working view, the timeline drawn in place."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths, days=1)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    plan.update({"status": "ready", "flags": [], "todo": [], "conditions": dict(SHARE_COND, days=1), "aware": []})
    a, b, c, d = paths
    name = lambda p: p.split("/")[2]  # noqa: E731
    dropped = json.loads(json.dumps(plan))
    dropped["days"][0]["stops"] = [s for s in dropped["days"][0]["stops"] if s["path"] != a]
    dropped["days"][0]["legs"] = []
    dropped["edited"] = [{"k": "act", "t": f"{name(a)}를 뺐어요"}]
    calls: list = []
    script = {"next": [sse({"type": "plan", "plan": plan, "sig": "s" * 43}),
                       (503, {"code": "busy", "message": "지금은 코스를 만들 수 없습니다. 잠시 뒤 다시 시도해 주세요."}),
                       sse({"type": "plan", "plan": dropped, "sig": "t" * 43, "act": {"op": "drop", "day": 0, "from": a, "to": None}})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.add_init_script(GA_STUB)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            first = page.locator(".trp-tl .trp-stop").nth(0)
            first.locator("[data-act=pin]").click()
            first.locator("[data-act=drop]").click()
            page.wait_for_selector(".trp-fail-edit")
            assert calls[-1]["act"] == {"op": "drop", "day": 0, "page": a} and "pins" not in calls[-1]
            assert "지금은 코스를 만들 수 없습니다" in page.text_content(".trp-fail-edit")
            # the plan as it was, the stop still pinned — on screen and in the tab
            assert page.locator(".trp-tl .trp-stop").count() == 4
            assert page.locator(".trp-tl .trp-stop").nth(0).locator("[data-act=pin]").get_attribute("aria-pressed") == "true"
            assert json.loads(page.evaluate("() => sessionStorage.getItem('gs-plan')"))["pins"] == [f"0|{a}"]
            # tried again: the same act, quiet, drawn in place with the focus on the stop after it
            page.evaluate("() => { window.__work = 0; new MutationObserver(() => { if (!document.querySelector('[data-plan-work]').hidden) window.__work += 1; })"
                          ".observe(document.querySelector('[data-plan-work]'), { attributes: true }); }")
            page.click(".trp-fail-edit button")
            page.wait_for_function("() => document.querySelectorAll('.trp-tl .trp-stop').length === 3")
            assert calls[-1]["act"] == {"op": "drop", "day": 0, "page": a}
            assert page.evaluate("window.__work") == 0, "no working view"
            assert page.locator(".trp-diff li").all_text_contents()[0] == f"{name(a)}를 뺐어요"
            page.wait_for_function("(p) => document.activeElement.closest('.trp-stop') && document.activeElement.closest('.trp-stop').getAttribute('data-path') === p", arg=b)
            # the pin went with the stop
            assert "pins" not in json.loads(page.evaluate("() => sessionStorage.getItem('gs-plan')"))
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ 영주·세종 집중 분석 2026-10-24 (the same engine)
def test_the_need_counts_are_the_planner_s_own_reading_of_the_data(site, tmp_path):
    """UI-A01: the form says, the moment a need is picked, how many places to visit the site's data says fit it — the
    count chat_index.need_counts makes at build time with the words plan_state.js needAt reads (영주: 0 for the
    wheelchair, every such trip refused with nothing said before). The built page carries each count; over 군산's own
    planner facts (tests/fixtures/plan_places.json) and 세종 고운뜰공원's steep route, Python and Node count alike."""
    import subprocess
    from pipeline import chat_index
    html = (site / "plan" / "index.html").read_text("utf-8")
    counts = chat_index.need_counts(json.loads((site / "chat" / "docs.json").read_text("utf-8"))["docs"])
    for need, words in (("wheelchair", "휠체어: 출입구 자료로 접근할 수 있다고 나온 관광지"), ("stroller", "유모차: 출입구 자료로 접근할 수 있다고 나온 관광지"),
                        ("parking", "주차 편한 곳: 주차할 수 있다(또는 근처 공영주차장)고 사이트 자료에 있는 관광지"),
                        ("free", "입장료 없는 곳 위주: 무료라고 사이트 자료에 있는 관광지"), ("rain", "비 와도 실내 위주: 실내라고 사이트 자료에 있는 관광지")):
        assert f'value="{need}" data-need-note="{words} {counts[need]}곳" data-need-n="{counts[need]}"' in html, need
    assert 'value="lesswalk" data-need-note="걷기 적게: 걷는 거리는 사이트 자료로 잴 수 없어 구간 직선거리만 적어요">' in html
    assert 'data-need-notes data-tail="사이트에 자료가 있는 곳의 수예요. 자료가 없는 곳은 이용할 수 없다는 뜻이 아니라 사이트에 정보가 없다는 뜻이에요' in html
    docs = json.loads((ROOT / "tests" / "fixtures" / "plan_places.json").read_text("utf-8"))["docs"]
    docs["/places/gountteulgongwon/"] = {"t": "고운뜰공원", "k": "place", "f": {"kd": "attraction", "g": [36.5, 127.25], "ac": [{"k": "accessible_route",
        "p": "한국관광공사 무장애 여행 정보(TourAPI)", "t": "경사로가 가파른 편으로 휠체어와 유모차 접근은 다소 어려울 수 있으나 고운뜰전망대 방향쪽으로는 차량으로 접근 할 수 있어 휠체어도 함께 올라 전망 관람 가능"}]}}
    assert not chat_index.need_fits("wheelchair", docs["/places/gountteulgongwon/"]["f"])
    py = chat_index.need_counts(docs)
    assert py["wheelchair"] > 0 and py["parking"] > 0
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    (tmp_path / "docs.json").write_text(json.dumps({"docs": docs}, ensure_ascii=False), "utf-8")
    script = ("import { readFileSync } from 'node:fs'; import { needAt } from '" + (ROOT / "chatbot" / "plan_state.js").as_uri() + "';"
              "const docs = JSON.parse(readFileSync(process.argv[1], 'utf8')).docs;"
              "const fs = Object.values(docs).filter((d) => d.k === 'place' && d.f && d.f.kd === 'attraction' && d.f.g).map((d) => d.f);"
              "const fee = (f) => ({ how: 'own', states: f.fee && f.fee.free ? { free: 1 } : f.fee && f.fee.tab ? { paid: 1 } : { unknown: 1 } });"
              "const out = {}; for (const n of ['rain', 'stroller', 'wheelchair', 'parking', 'free'])"
              " out[n] = fs.filter((f) => ['ok', 'near'].includes(needAt(n, f, 'visit', n === 'free' ? fee(f) : null).state)).length;"
              "console.log(JSON.stringify(out));")
    r = subprocess.run([node, "--input-type=module", "-e", script, str(tmp_path / "docs.json")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == py


def test_in_a_browser_a_need_picked_says_how_many_places_the_data_has_for_it(site):
    """UI-A01: checked — its count and once what the count means; unchecked — nothing."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from pipeline import chat_index
    n = chat_index.need_counts(json.loads((site / "chat" / "docs.json").read_text("utf-8"))["docs"])
    serve = server(site, a_plan(plan_paths(site)), [], {"next": []})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/plan/", wait_until="load")
            box = page.locator("[data-need-notes]")
            assert box.is_hidden()
            page.click('label.trp-card:has(input[name="needs"][value="wheelchair"])')
            assert box.is_visible()
            lines = box.locator("p").all_text_contents()
            assert lines[0] == f"휠체어: 출입구 자료로 접근할 수 있다고 나온 관광지 {n['wheelchair']}곳"
            assert lines[-1].startswith("사이트에 자료가 있는 곳의 수예요. 자료가 없는 곳은 이용할 수 없다는 뜻이 아니라")
            # (a live region: another condition changed — the days — leaves its lines as they are, never read out again)
            page.evaluate("() => { window.__needP = document.querySelector('[data-need-notes] p'); }")
            page.click('label.trp-card:has(input[name="days"][value="2"])')
            assert page.evaluate("() => window.__needP.isConnected && document.querySelector('[data-need-notes] p') === window.__needP")
            page.click('label.trp-card:has(input[name="needs"][value="lesswalk"])')
            assert box.locator("p").count() == 3
            page.click('label.trp-card:has(input[name="needs"][value="wheelchair"])')
            assert box.locator("p").all_text_contents() == ["걷기 적게: 걷는 거리는 사이트 자료로 잴 수 없어 구간 직선거리만 적어요"]
            page.click('label.trp-card:has(input[name="needs"][value="lesswalk"])')
            assert box.is_hidden()
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_cancel_by_keyboard_leaves_the_focus_on_the_button_and_the_wait_says_only_the_seconds(site):
    """UX04: the working view goes on 취소 — the focus goes to the button that asks again, never to the page (it was
    BODY); the line under it counts the seconds and names only a step the server said ('거의 다 됐어요' came from 40
    seconds on whatever the server had said)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    serve = server(site, a_plan(plan_paths(site)), [], {"next": []})
    held = []

    def route(r):
        if r.request.url.endswith("/api/plan/"):
            held.append(r)   # no answer: the request waits
            return None
        return serve(r)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", route)
            page = ctx.new_page()
            page.clock.install()
            page.goto("http://site.test/plan/", wait_until="load")
            page.focus(".trp-submit")
            page.keyboard.press("Enter")
            page.clock.run_for(500)
            assert page.evaluate("() => !document.querySelector('[data-plan-work]').hidden && document.activeElement.id === 'h-work'")
            page.clock.run_for(40500)
            line = page.text_content("[data-plan-live]")
            assert line.startswith("41초째 만들고 있어요") and "거의" not in line, line
            page.focus("[data-plan-cancel]")
            page.keyboard.press("Enter")
            page.clock.run_for(100)
            assert page.evaluate("() => document.activeElement.classList.contains('trp-submit')"), page.evaluate("() => document.activeElement.outerHTML.slice(0, 80)")
            assert page.evaluate("() => document.activeElement !== document.body")
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_course_the_tab_could_not_keep_is_said_on_the_spot_and_after_a_reload(site):
    """UX05: a tab whose storage refuses the course (full, a private window) says so as soon as the course comes, with
    the ways that keep it; a reload with the conditions alone (the course lost) says why there is no course, the
    conditions on the form, and makes it again with one button — never a bare form as if nothing had been made."""
    from datetime import date, timedelta
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    calls: list = []
    serve = server(site, plan, calls, {"next": []})
    day = (date.today() + timedelta(days=7)).isoformat()
    kept = {"conditions": {"date": day, "days": 2, "start": "10:00", "end": "18:00", "from": "", "to": "", "move": "transit", "with": "couple",
                           "adults": 2, "seniors": 0, "kids": [], "prefs": [], "needs": [], "budget": None}, "plan": None, "lost": 1}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.add_init_script("Storage.prototype.setItem = function (k) { if (k === 'gs-plan') throw new DOMException('full', 'QuotaExceededError'); };")
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            note = page.locator(".trp-save-note")
            assert note.is_visible() and note.get_attribute("role") == "status"
            assert note.text_content().startswith("이 탭에 코스를 보관하지 못했어요(브라우저 저장 공간이 모자라거나 사생활 보호 모드)")
            assert "'링크 복사'나 '파일로 저장'" in note.text_content()
            ctx.close()
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.add_init_script("sessionStorage.setItem('gs-plan', " + json.dumps(json.dumps(kept)) + ");")
            page.goto("http://site.test/plan/", wait_until="load")
            page.wait_for_selector(".trp-lost")
            assert page.text_content(".trp-lost h2") == "이전 코스를 다시 불러오지 못했어요"
            assert "이 탭에 코스를 보관하지 못했어요" in page.text_content(".trp-lost")
            assert page.is_checked('input[name="days"][value="2"]') and page.input_value("input[name=date]") == day
            n = len(calls)
            page.click(".trp-lost button")
            page.wait_for_function("() => { const h = document.querySelector('#h-result'); return !!h && !h.textContent.includes('불러오지'); }")
            assert len(calls) == n + 1 and calls[-1]["conditions"]["days"] == 2 and calls[-1]["conditions"]["date"] == day
            ctx.close()
        finally:
            browser.close()
