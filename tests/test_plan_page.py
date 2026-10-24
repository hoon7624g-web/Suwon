"""The AI course planner's page /plan/ (the first city's operator 2026-10-17: its own page, very visible, many cute 3D
pictures; chatbot/planner.js answers /api/plan/). The build writes the page — noindex, not in the sitemap — and
/plan/places.json, each place's first-screen values, TourAPI photo and point; the page's choices are real inputs, the
hubs and likes the city's (site.json plan, pipeline/plan.py); in a browser (Playwright, /api/plan/ mocked with
scripted SSE, nothing leaves the machine) the form asks with the conditions, the steps light up, the plan is drawn from
the site's own data with day tabs, legs with directions links, a numbered day map (map.js loaded when the plan comes,
Leaflet + OpenStreetMap), the fee card and what to check, an edit sends the plan and the change, an error offers a
retry, a reload shows the plan again, and no phone width scrolls sideways."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline.build import build

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def plan_build(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["plan"] = {"hubs": [{"key": "station", "name": "샘플역"}, {"key": "terminal", "name": "샘플버스터미널"}]}
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
    assert "data-kakao-sdk" not in html and "map.js" not in html and "leaflet" not in html   # nothing of the map before a plan
    assert "data-tickets" not in html   # no combined ticket (tickets.json): the fee card names the places' tables only
    # the city's hubs (site.json plan.hubs) in both selects, and no hub select for a city without them
    assert html.count('<option value="station">샘플역</option>') == 2 and html.count('<option value="terminal">샘플버스터미널</option>') == 2
    # every choice is a real radio or check box inside its card's label
    for name, kind, n in (("days", "radio", 3), ("move", "radio", 2), ("with", "radio", 4), ("prefs", "checkbox", 8),
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
    assert 'value="islands"' not in html   # the engine's likes have no sea: a city adds its own in site.json plan.prefs
    # the doors: the masthead's pill, the phone menu's first row, the courses' banner, the about page's note
    for page in ("index.html", "courses/index.html", "about/index.html"):
        doc = (site / page).read_text("utf-8")
        assert '<a class="mast-plan" href="/plan/"' in doc and '<a class="menu-plan" href="/plan/"' in doc, page
    assert '<a class="pcta pcta-courses" href="/plan/" data-track="plan_cta">' in (site / "courses" / "index.html").read_text("utf-8")
    about = (site / "about" / "index.html").read_text("utf-8")
    assert '<p id="plan"><a href="/plan/">AI 코스 만들기</a>' in about and "장소 요금표로 사람마다 계산" in about
    assert "통합권 요금표로" not in about   # the sample city has no combined ticket (tickets.json)


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
          "hubs": [{"dir": "from", "name": "샘플역", "stop": "a", "at": "09:00", "gap": 60, "url": "https://map.kakao.com/?sName=a&eName=b"}]}
    d2 = {"date": "2026-10-25", "label": "2일차 · 10월 25일 (일)", "stops": [stop(paths[2], "10:00", "12:00")], "legs": [], "hubs": []}
    return {"v": 2, "made": "2026-10-17T01:00:00Z", "title": "아이와 박물관 1박 2일", "summary": "실내 위주로 돕니다.",
            "notes": ["구간 시간은 여유입니다"], "conditions": {}, "days": [d1, d2][:days],
            "fees": {"state": "known", "total": 3000, "known": 3000, "limit": 10000, "verdict": "within", "open": [], "conds": [],
                     "days": [{"date": "2026-10-24", "lines": [{"what": "샘플박물관", "who": "어른", "count": 1, "status": "paid",
                                                                "won": 3000, "sub": 3000, "basis": "요금표 '성인'"}]}]},
            "needs": [{"key": "stroller", "label": "유모차", "rows": [
                {"day": 0, "i": 0, "name": "a", "state": "ok", "text": "출입구: 경사로"},
                {"day": 0, "i": 1, "name": "b", "state": "unknown", "text": "출입구 접근 정보 없음"}]}],
            "checks": [{"k": "need", "t": "유모차: b — 출입구 접근 정보 없음"}, {"k": "move", "t": "장소 사이 시간은 계획상 여유"}],
            "flags": ["1일차 2→3번 b → c: 직선 400m인데 이동 시간을 두지 않음"], "status": "unmet"}


def test_in_a_browser_the_planner_asks_draws_edits_recovers_and_comes_back(site):
    sync_api = pytest.importorskip("playwright.sync_api")
    import mimetypes
    from urllib.parse import unquote, urlsplit
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    shot = next(p for p in places if places[p].get("img"))   # the place with a TourAPI photo comes first
    paths = [shot, next(p for p in places if places[p]["k"] == "food" and p != shot),
             next(p for p in places if places[p]["k"] == "attraction" and p != shot),
             next(p for p in places if places[p]["k"] == "stay" and p != shot)]
    plan = a_plan(paths)
    calls = []
    script = {"next": [sse({"type": "status", "step": "search", "text": "장소를 찾고 있어요"},
                           {"type": "status", "step": "check", "text": "휴무·운영시간을 확인하고 있어요"},
                           {"type": "plan", "plan": plan})]}

    def serve(route):
        url = route.request.url
        if url.endswith("/api/plan/"):
            calls.append(route.request.post_data_json)
            body = script["next"].pop(0) if script["next"] else sse({"type": "plan", "plan": plan})
            return route.fulfill(status=200, body=body, headers={"content-type": "text/event-stream; charset=utf-8"})
        if "tong.visitkorea.or.kr" in url or "tile.openstreetmap.org" in url:   # photos and map tiles: a 1×1 stand-in
            return route.fulfill(status=200, body=PNG, content_type="image/png")
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = site / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

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
            for v in ("history", "food", "nature", "night", "photo"):
                page.click(f'label.trp-card:has(input[name="prefs"][value="{v}"])')
            assert page.evaluate("() => document.querySelectorAll('input[name=prefs]:checked').length") == 4
            page.click('label.trp-card:has(input[name="needs"][value="rain"])')
            page.click('[data-budget="10000"]')
            page.select_option("select[name=from]", "station")
            page.fill("textarea[name=note]", "국수 먹고 싶어요")
            assert "1박 2일" in page.text_content("[data-plan-sum]") and "아이 4살" in page.text_content("[data-plan-sum]")
            assert "샘플역 10:00 출발" in page.text_content("[data-plan-sum]")   # the hub's name from the form's own option
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[0]["conditions"]
            assert c["days"] == 2 and c["with"] == "kids" and c["kids"] == [4] and c["adults"] == 2
            assert c["prefs"] == ["history", "food", "nature", "night"] and c["needs"] == ["rain"] and c["budget"] == 10000
            assert c["note"] == "국수 먹고 싶어요" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["date"]) and c["from"] == "station"
            # what the code says first (review 2026-10-17: a '6/6 확인' badge above unconfirmed places): the status, each
            # check in its own state, the first things to check
            assert "is-bad" in page.get_attribute(".trp-status", "class") and "조건을 다 맞추지 못한" in page.text_content(".trp-status h3")
            assert page.locator(".trp-flags li").all_text_contents() == ["1일차 2→3번 b → c: 직선 400m인데 이동 시간을 두지 않음"]
            rows = page.locator(".trp-st4 li")
            assert rows.count() == 5
            assert "그날 운영 확인 필요 1곳" in rows.nth(1).text_content() and "is-check" in rows.nth(1).get_attribute("class")
            assert "자료 있음 1 · 정보 없음 1 · 맞지 않음 0" in rows.nth(2).text_content()
            assert "3,000원 · 예산 안" in rows.nth(3).text_content()
            assert "구간 이동 시간은 확인되지 않음" in rows.nth(4).text_content()
            # the plan: title, day tabs, stops from the site's data, legs, the start, fees, checks
            assert page.text_content("#h-result") == "아이와 박물관 1박 2일"
            assert page.locator(".trp-days [role=tab]").count() == 2
            assert page.locator(".trp-stop").count() == 4
            assert page.locator(".trp-stop .trp-ai").first.text_content() == "AI"
            assert page.locator(".trp-ph figcaption").first.text_content() == "출처: 한국관광공사"
            assert page.locator(".trp-ph.t3 img").count() == 1   # KOGL-3: framed whole
            assert page.locator(".trp-stop[data-day=unknown] .trp-day").text_content().endswith("운영 확인 필요")
            assert "확인: 쉬는 날이 사이트에 없음" in page.text_content(".trp-stop[data-day=unknown] .trp-warn")
            assert page.locator(".trp-leg").count() == 3 and page.locator(".trp-leg-bad").count() == 1 and page.locator(".trp-hub").count() == 1
            assert "샘플역 09:00 출발" in page.text_content(".trp-hub") and "계획상 여유 60분" in page.text_content(".trp-hub")
            assert page.get_attribute(".trp-leg:not(.trp-hub) .trp-leg-go >> nth=0", "href").startswith("https://map.kakao.com/link/by/traffic/")
            assert "같은 번호 노선 07·99번" in page.text_content(".trp-leg:not(.trp-hub) >> nth=0")
            assert "계획상 여유 30분" in page.text_content(".trp-leg:not(.trp-hub) >> nth=0")
            assert page.text_content(".trp-total") == "3,000원" and "예산 안" in page.text_content(".trp-verdict")
            assert "장소마다의 요금표로 사람마다 계산" in page.text_content(".trp-budget-c") and "통합권" not in page.text_content(".trp-budget-c")
            assert "샘플박물관 · 어른 1명:" in page.text_content(".trp-budget-c .trp-lines")
            assert "유모차: b — 출입구 접근 정보 없음" in page.text_content(".trp-check-c")
            assert page.locator(".trp-map .map[data-map]").count() == 1
            # the day map: map.js (window.GSMapStart) and Leaflet come with the plan, the stops numbered on the map
            page.wait_for_selector(".trp-map .map .leaflet-container, .trp-map .map.leaflet-container", timeout=15000)
            assert page.evaluate("() => !!window.GSMapStart && !!window.L")
            assert "OpenStreetMap" in page.text_content(".trp-map figcaption")
            # on a phone the charts are folded; the reader opens them
            assert page.locator(".trp-fold[open]").count() == 0 and page.is_visible(".trp-fine-s")
            for summary in page.locator(".trp-fold > summary").all():
                summary.click()
            # the diagrams, every number from the checked plan: tiles, the day clock, the needs, the stations, the bars
            kpis = page.locator(".trp-kpi")
            assert kpis.count() == 4
            assert kpis.nth(0).locator(".trp-kpi-v").text_content() == "5곳" and "관람 3 · 식사 1 · 숙소 1" in kpis.nth(0).text_content()
            assert kpis.nth(1).locator(".trp-kpi-v").text_content() == "1.8km"   # 1,430m + 400m, straight lines
            assert kpis.nth(2).locator(".trp-kpi-v").text_content() == "3,000원"
            assert page.get_attribute(".trp-meter", "aria-label") == "확인된 입장료 3,000원 / 예산 10,000원"
            assert page.evaluate("() => document.querySelector('.trp-meter span').style.width") == "30%"
            assert kpis.nth(3).locator(".trp-kpi-v").text_content() == "5/5" and "그날 운영 확인 필요 1곳" in kpis.nth(3).text_content()
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
            assert text.startswith("아이와 박물관 1박 2일") and "■ 2일차 · 10월 25일 (일)" in text and "유모차: b — 출입구 접근 정보 없음" in text
            assert "09:00 샘플역 출발" in text and "입장료: 3,000원" in text
            assert "https://example.com/plan/) 자료로 검사했어요" in text and dl.value.suggested_filename.endswith("-코스-" + c["date"] + ".txt")
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
            assert page.input_value("textarea[name=note]") == "국수 먹고 싶어요" and page.input_value("input[name=budget]") == "10000"
            assert page.input_value("select[name=from]") == "station"
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
