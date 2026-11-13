"""The /plan/ result says no more than the plan's data (review 2026-10-22, the result's words): the '필요한 조건' row
counts each need on its own and never says '고른 조건 없음' under 걷기 적게; '정기 규칙상 방문 가능' and its ring count only
the stops whose regular rule keeps them open; a stop open by its rule whose day still asks whether it opens reads
'운영 확인 필요' on its card and in the text passed on; a stop the site swapped in says '쉬는 곳 대신' only when the
plan says it was for a closed day; 맛집 reads '식사 장소 포함', never '반영'; a start or an end at a station is a leg
with no distance, so no distance total; a hub leg's bus guide is one link beside Kakao Map's; a shared plan with data
gaps opens under an information line, not '✓ … 맞는 코스예요', and never under a '확인할 것'; a year the holiday table lacks is never all-clear; the
/courses/ banner promises a plan matched against the site's data, not one confirmed. Drawn in a browser from this
tab's storage (Playwright, nothing leaves the machine, no /api/ call), at 390px."""
import copy
import datetime
import json

import pytest

from test_plan_page import a_plan, plan_build, plan_paths, server

HOLIDAY = "그날은 공휴일(성탄절) — 공휴일 운영은 사이트 자료에 없음, 그날 여는지 확인 필요"
GUIDE = "/guides/군산-시내버스-관광지/#h-b6"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return plan_build(tmp_path_factory.mktemp("plan_r8"))


def conditions(**kw):
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    c = {"date": day, "days": 1, "start": "09:00", "end": "21:00", "move": "transit", "with": "couple", "adults": 2,
         "seniors": 0, "kids": [], "from": "station", "to": "bus", "prefs": ["history", "food"], "needs": [],
         "budget": None, "note": ""}
    c.update(kw)
    return c


def ready(paths):
    """A finished one-day plan (planner finish v 2, status ready) with the shapes this review is about."""
    plan = a_plan(paths, days=1)
    d = plan["days"][0]
    d["legs"][1].update({"gap": 10, "flag": ""})
    s = d["stops"]
    s[0].update({"swapped": "closed"})                                       # for a closed day (the server's new shape)
    s[1].update({"checks": [HOLIDAY], "swapped": "other"})                   # open by its rule, a holiday that day
    s[3].update({"checks": ["같은 날 다시 들어갈 수 있는지(재입장) 확인 필요"], "swapped": True})   # a plan from before
    d["hubs"] = [{"dir": "from", "name": "군산역", "stop": s[0]["name"], "at": "09:00", "gap": 60, "url": "https://map.kakao.com/?sName=a&eName=b",
                  "guide": {"path": GUIDE, "label": "99번 버스"}},
                 {"dir": "to", "name": "군산시외버스터미널", "stop": s[2]["name"], "at": "21:00", "gap": 30, "url": "https://map.kakao.com/?sName=c&eName=d"}]
    plan["needs"].append({"key": "rain", "label": "실내", "rows": [
        {"day": 0, "i": 0, "name": "a", "state": "ok", "text": "박물관·전시"},
        {"day": 0, "i": 1, "name": "b", "state": "ok", "text": "음식점"},
        {"day": 0, "i": 2, "name": "c", "state": "unknown", "text": "실내인지 자료 없음"},
        {"day": 0, "i": 3, "name": "d", "state": "na", "text": ""}]})
    plan.update({"status": "ready", "flags": [], "todo": [], "fixed": [],
                 "checks": [{"k": "day", "t": f"{s[1]['name']}: {HOLIDAY}"}, {"k": "need", "t": "유모차: b — 출입구 접근 정보 없음"}],
                 "aware": [{"k": "walk", "t": "걷기: 걷는 거리는 사이트 자료로 잴 수 없어요 — 구간마다 직선거리를 적었어요"}],
                 "complete": {"meals": [{"day": 0, "kind": "lunch", "state": "ok"}], "gaps": [],
                              "prefs": [{"key": "history", "label": "역사·문화", "met": True}, {"key": "food", "label": "맛집", "met": True}]}})
    return plan


def draw(page, plan, c, shared=None):
    """The plan as this tab keeps it (sessionStorage 'gs-plan'), drawn on a fresh load: no request to /api/."""
    state = {"conditions": c, "plan": plan, "sig": None}
    if shared:
        state["shared"] = shared
    page.goto("http://site.test/plan/", wait_until="load")
    page.evaluate("s => sessionStorage.setItem('gs-plan', s)", json.dumps(state, ensure_ascii=False))
    page.goto("http://site.test/plan/", wait_until="load")
    page.wait_for_selector(".trp-status")
    return page.locator(".trp-st4 li")


def test_in_a_browser_the_result_says_no_more_than_its_data(site):
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = ready(paths)
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
            rows = draw(page, plan, conditions(needs=["rain", "stroller", "lesswalk"]))
            # the header stays the operator's (2026-10-18): a finished plan reads as finished — with the number of its
            # status rows to check before going (operator 2026-10-23: the rows marked i or !; 입장료 and 일정 완성도 are ✓)
            assert page.locator(".trp-st4 li.is-info .trp-st4-l, .trp-st4 li.is-bad .trp-st4-l").all_text_contents() == [
                "정기 휴무·운영시간", "공휴일·특별 운영", "필요한 조건", "이동"]
            assert page.text_content(".trp-status h3") == "✓코스 완성 · 가기 전 확인 4가지" and "is-ok" in page.get_attribute(".trp-status", "class")
            # S1: the stop whose closed days the site does not have is not '방문 가능' — the row and the ring alike
            assert "is-info" in rows.nth(0).get_attribute("class")
            assert rows.nth(0).locator(".trp-st4-v").text_content().endswith("정기 규칙상 방문 가능 3/4곳 · 규칙만으로 알 수 없음 1곳")
            ring = page.locator(".trp-kpi >> nth=3")
            assert ring.locator(".trp-kpi-v").text_content() == "3/4" and ring.locator(".trp-kpi-n").text_content() == "그날 운영 확인 필요 3곳"
            # the holiday stays in the row made for it
            assert "그날 운영 자료가 없는 곳 3곳" in rows.nth(1).text_content() and "is-info" in rows.nth(1).get_attribute("class")
            # C1 + S4: each need its own counts (맞지 않음 only when there is one), 걷기 적게 said as what the data cannot measure
            assert rows.nth(2).locator(".trp-st4-v").text_content().endswith(
                "유모차: 자료 있음 1 · 정보 없음 1 / 실내: 자료 있음 2 · 정보 없음 1 / 걷기 적게: 사이트 자료로 잴 수 없음 · 구간 직선거리만 있음")
            assert "is-info" in rows.nth(2).get_attribute("class")
            # S6: 맛집 is a meal stop, never '반영'
            done = rows.nth(5).locator(".trp-st4-v").text_content()
            assert done.endswith("점심 포함 · 역사·문화 반영 / 맛집: 식사 장소 포함 · 2시간 넘게 빈 시간 없음") and "맛집 반영" not in done
            assert "is-ok" in rows.nth(5).get_attribute("class")
            # S2: open by its rule, a holiday that day → '운영 확인 필요'; a second visit to check says nothing of the day
            cards = page.locator(".trp-stop")
            assert [cards.nth(i).locator(".trp-day span:last-child").text_content() for i in range(4)] == ["운영", "운영 확인 필요", "운영 확인 필요", "운영"]
            assert "trp-day-unknown" in cards.nth(1).locator(".trp-day").get_attribute("class")
            assert cards.nth(1).get_attribute("data-day") == "open"   # the server's own state stays on the stop
            # S5: '쉬는 곳 대신' only for a swap made for a closed day; any other, and true from before, is neutral
            assert cards.nth(0).locator(".trp-by").text_content().endswith("그날 쉬는 곳 대신 사이트가 고른 가까운 곳이에요")
            assert cards.nth(1).locator(".trp-by").text_content().endswith("사이트가 바꿔 넣은 가까운 곳이에요")
            assert cards.nth(3).locator(".trp-by").text_content().endswith("사이트가 바꿔 넣은 가까운 곳이에요")
            assert page.locator(".trp-stop .trp-by:has-text('쉬는 곳')").count() == 1
            # movement S1: two legs with a distance and two hub legs without → no total
            tile = page.locator(".trp-kpi >> nth=1")
            assert tile.locator(".trp-kpi-v").text_content() == "전체 이동거리 계산 안 됨"
            assert tile.locator(".trp-kpi-n").text_content() == "4개 구간 중 2개만 거리 있음"
            # movement S2: the hub leg's bus guide, one link beside Kakao Map's, a 44px target; none without a guide
            hubs = page.locator(".trp-hub")
            assert hubs.nth(0).locator("a").all_text_contents() == ["카카오맵 길찾기", "버스 안내(가이드)"]
            guide = hubs.nth(0).locator("a >> nth=1")
            assert guide.get_attribute("href") == GUIDE and guide.get_attribute("target") is None
            assert guide.get_attribute("aria-label") == "버스 안내(가이드): 99번 버스"
            assert guide.bounding_box()["height"] >= 44
            assert hubs.nth(1).locator("a").all_text_contents() == ["카카오맵 길찾기"]
            # the text passed on says the same
            text = page.text_content(".trp-print")
            assert f"1. {plan['days'][0]['stops'][0]['name']} [둘러보기 · 그날 운영 · 쉬는 곳 대신 사이트가 고름]" in text
            assert f"2. {plan['days'][0]['stops'][1]['name']} [식사 · 그날 운영 확인 필요 · 사이트가 바꿔 넣음]" in text
            assert f"4. {plan['days'][0]['stops'][3]['name']} [숙소 · 그날 운영 · 사이트가 바꿔 넣음]" in text
            assert "구간 직선거리: 전체 이동거리 계산 안 됨(4개 구간 중 2개만 거리 있음)" in text
            assert "09:00 군산역 출발 (길찾기 https://map.kakao.com/?sName=a&eName=b · 버스 안내 https://gunsan.webforai.kr/guides/%EA%B5%B0" in text
            assert "21:00까지 군산시외버스터미널 (길찾기 https://map.kakao.com/?sName=c&eName=d)" in text
            assert "일정 완성도: 점심 포함 · 역사·문화 반영 / 맛집: 식사 장소 포함" in text
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390

            # by car the bus guide is not offered
            draw(page, plan, conditions(move="car", needs=["rain", "stroller", "lesswalk"]))
            assert page.locator(".trp-hub >> nth=0").locator("a").all_text_contents() == ["카카오맵 길찾기"]
            assert " · 버스 안내 " not in page.text_content(".trp-print")

            # S4: 걷기 적게 alone — never '고른 조건 없음'; read from the plan's own conditions as well as the tab's
            walk = copy.deepcopy(plan)
            walk["needs"], walk["checks"] = [], []
            rows = draw(page, walk, conditions(needs=["lesswalk"]))
            assert rows.nth(2).locator(".trp-st4-v").text_content().endswith("걷기 적게: 사이트 자료로 잴 수 없음 · 구간 직선거리만 있음")
            assert "is-info" in rows.nth(2).get_attribute("class")
            walk["aware"], walk["conditions"] = [], {"needs": ["lesswalk"]}
            rows = draw(page, walk, conditions(needs=[]))
            assert rows.nth(2).locator(".trp-st4-v").text_content().endswith("걷기 적게: 사이트 자료로 잴 수 없음 · 구간 직선거리만 있음")
            # nothing picked: as before
            walk["conditions"] = {"needs": []}
            rows = draw(page, walk, conditions(needs=[]))
            assert rows.nth(2).locator(".trp-st4-v").text_content().endswith("고른 조건 없음") and "is-na" in rows.nth(2).get_attribute("class")

            # every stop open by its rule, nothing to check: the rows read all-clear as before
            clear = copy.deepcopy(walk)
            for s in clear["days"][0]["stops"]:
                s.update({"day": "open", "checks": [], "flags": []})
            rows = draw(page, clear, conditions())
            assert rows.nth(0).locator(".trp-st4-v").text_content().endswith("정기 규칙상 4/4곳 방문 가능") and "is-ok" in rows.nth(0).get_attribute("class")
            assert rows.nth(1).locator(".trp-st4-v").text_content().endswith("공휴일·날짜별 공지에 걸리는 곳 없음")
            assert page.text_content(".trp-kpi:nth-child(4) .trp-kpi-v") == "4/4"
            # …but not for a year whose holiday table the site does not have (the server's new field, when it is there)
            clear["holidayTableMissing"] = True
            rows = draw(page, clear, conditions())
            assert "is-info" in rows.nth(1).get_attribute("class")
            assert rows.nth(1).locator(".trp-st4-v").text_content().endswith("그해 공휴일 표 없음 — 설·추석·대체공휴일이면 그날 운영 확인")
            assert page.text_content(".trp-kpi:nth-child(4) .trp-kpi-n") == "그해 공휴일 표 없음"
            # …by knowledge.checkPlan's own name for it too, on a day
            del clear["holidayTableMissing"]
            clear["days"][0]["noHolidayTable"] = True
            rows = draw(page, clear, conditions())
            assert rows.nth(1).locator(".trp-st4-v").text_content().endswith("그해 공휴일 표 없음 — 설·추석·대체공휴일이면 그날 운영 확인")

            # S3: a shared plan with data gaps opens under an information line; one without, as before
            shared = {"signed": True, "words": True, "past": False, "during": False, "dropped": 0}
            # (counted as the plan's own heading counts: the status rows marked i or ! — operator 2026-10-23)
            rows = draw(page, plan, conditions(), shared)
            n = page.locator(".trp-st4 li.is-info, .trp-st4 li.is-bad").count()
            assert n == 4   # 정기 휴무·운영시간, 공휴일·특별 운영, 입장료, 이동 (no need picked: '–')
            assert page.text_content(".trp-status h3") == f"i오늘 자료와 어긋난 곳 없음 · 가기 전 확인 {n}가지"
            assert "is-info" in page.get_attribute(".trp-status", "class") and page.text_content(".trp-status h3 .trp-mark") == "i"
            assert f"상태: 오늘 자료와 어긋난 곳 없음 · 가기 전 확인 {n}가지" in page.text_content(".trp-print")
            # what the data does not say never sits on top as '확인할 것' (operator 2026-10-18), shared or not
            assert "확인할 것" not in page.text_content(".trp-status h3") and "확인할 것" not in page.text_content(".trp-print")
            draw(page, clear, conditions(), shared)   # nothing to check but a year the holiday table lacks — and 이동: no ✓ either
            assert [x.text_content() for x in page.locator(".trp-st4 li.is-info .trp-st4-l").all()] == ["공휴일·특별 운영", "이동"]
            assert page.text_content(".trp-status h3") == "i오늘 자료와 어긋난 곳 없음 · 가기 전 확인 2가지"
            assert "is-info" in page.get_attribute(".trp-status", "class")
            del clear["days"][0]["noHolidayTable"]
            draw(page, clear, conditions(), shared)   # 이동 alone (its row is always i: the map app's times)
            assert page.text_content(".trp-status h3") == "i오늘 자료와 어긋난 곳 없음 · 가기 전 확인 1가지" and "is-info" in page.get_attribute(".trp-status", "class")
            assert calls == [] and errors == [], (calls, errors)
            ctx.close()
        finally:
            browser.close()


def test_the_courses_banner_promises_a_plan_matched_against_the_data_not_one_confirmed(site):
    html = (site / "courses" / "index.html").read_text("utf-8")
    assert "사이트 자료로 맞춰 본 일정이 나와요(자료에 없는 값은 ‘확인 필요’로 표시)." in html
    assert "확인한 일정" not in html
