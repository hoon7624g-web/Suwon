"""The site assistant in a real browser (Playwright + Chromium) on a sample build served locally, /api/chat/ mocked
with scripted SSE: the 1440px card (non-modal) opens from the launcher with focus in the question box, an input method's
Enter does not send (a conversion) while the Enter that ends a Korean syllable does, a streamed answer is drawn with its checked links and link cards and announced once, Esc closes
and returns focus to the launcher, the conversation comes back on the next page (sessionStorage); the 390px sheet is
modal (page inert, full height), its opener is there from the first paint (owner 2026-10-13 night; on a Korean phone
the tab bar's 'AI 챗봇' button since 시안 A, operator 2026-11-05), the
not-configured and error states (with retry), a text of its own for each 429 (the client's minute, its day, the whole
instance, the Vercel Firewall), a cut answer that goes on in place ('이어서 보기': continue: true with the cut answer as
the last message), earlier answers sent back with their checked links as page paths and a stopped question left out,
the course planner's door under an answer whose question states trip conditions (Korean pages with /plan/) — and no
console errors. Skipped where Playwright or its Chromium is missing."""
import functools
import http.server
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.build import build
from conftest import route_weather

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
SITE = "https://gunsan.webforai.kr"
ANSWER = ("은파호수공원은 쉬는 날 없이 열려 있습니다. [은파호수공원](/places/eunpa-lake-park/)\n\n"
          "- 시간: 상시 개방\n- 주차: 가능 — **무료**\n\n[없는 페이지](/places/nowhere/)")


def sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


def answer_stream() -> str:
    deltas = [{"type": "text", "delta": ANSWER[i:i + 7]} for i in range(0, len(ANSWER), 7)]
    done = {"type": "done", "links": [{"title": "은파호수공원", "url": f"{SITE}/places/eunpa-lake-park/", "ext": False}],
            "fix": {"/places/eunpa-lake-park/": f"{SITE}/places/eunpa-lake-park/", "/places/nowhere/": None}}
    return sse({"type": "status", "text": "찾는 중: 은파호수공원"}, *deltas, done)


OK = (200, answer_stream(), "text/event-stream; charset=utf-8")
# an answer cut at the length limit, and the rest the server writes when the reader asks to go on
CUT_TEXT = "후보 일정입니다.\n- 10:00 | [은파호수공원](/places/eunpa-lake-park/) | 그날 운영: 엶 | 요금: 무"
REST = "료 | 이동: 미확인\n\n이동 확인이 필요한 후보 일정입니다."
PARK = {"title": "은파호수공원", "url": f"{SITE}/places/eunpa-lake-park/", "ext": False}


def stream_of(text: str, **done) -> tuple:
    deltas = [{"type": "text", "delta": text[i:i + 7]} for i in range(0, len(text), 7)]
    end = {"type": "done", "links": [PARK], "fix": {"/places/eunpa-lake-park/": PARK["url"]}, **done}
    return 200, sse(*deltas, end), "text/event-stream; charset=utf-8"
NOT_CONFIGURED = (503, json.dumps({"code": "not_configured"}), "application/json")
BUSY = (200, sse({"type": "error", "code": "busy", "message": "x"}), "text/event-stream; charset=utf-8")
# the function's 429s (chatbot/server.js: a code per limit) and the Vercel Firewall's own 429 (no code)
LIMITED = [(429, json.dumps({"code": code, "message": "x"}), "application/json")
           for code in ("rate_limited", "daily_limit", "busy")] + [(429, "<html>Too Many Requests</html>", "text/html")]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):   # the test output stays readable; failures show up as assertions
        return None


def korean_enter(page, syllable):
    """Enter pressed while a Korean input method still composes the last syllable, as Chrome delivers it (CDP): a
    keydown 229 that the input method keeps (it commits the syllable: compositionend), then the reader's own Enter a
    few milliseconds later."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": syllable, "selectionStart": 1, "selectionEnd": 1})
    cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "code": "Enter",
                                        "windowsVirtualKeyCode": 229, "nativeVirtualKeyCode": 229})
    cdp.send("Input.insertText", {"text": syllable})
    page.keyboard.press("Enter")
    cdp.detach()


def converting_enter(page, text):
    """Enter pressed to confirm an input method's conversion (Japanese, Chinese): the key comes while composing, then
    the text is committed."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": text, "selectionStart": len(text), "selectionEnd": len(text)})
    page.keyboard.press("Enter")
    cdp.send("Input.insertText", {"text": text})
    cdp.detach()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("chatweb") / "out"
    build(SAMPLE, out, "sample")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error as err:
            pytest.skip(f"Chromium is not installed for Playwright: {err}")
        yield b
        b.close()


def open_page(browser, width, height, responses):
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="ko-KR")
    page = ctx.new_page()
    errors, calls = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    def handle(route):
        calls.append(route.request.post_data_json)
        status, body, ctype = responses[min(len(calls), len(responses)) - 1]
        route.fulfill(status=status, body=body, headers={"content-type": ctype})
    page.route("**/api/chat/", handle)
    route_weather(page)   # the tab panel's weather module (tests/conftest.py)
    return ctx, page, errors, calls


def test_desktop_card(browser, site):
    ctx, page, errors, calls = open_page(browser, 1440, 900, [OK])
    page.goto(site + "/places/")
    fab = page.locator(".chat-fab")
    assert fab.is_visible()                                   # a list page: the launcher is there from the start
    fab.click()
    panel = page.locator("#chat")
    panel.wait_for(state="visible")
    assert panel.get_attribute("role") == "dialog" and panel.get_attribute("aria-modal") == "false"
    assert page.evaluate("document.activeElement.id") == "chat-q"
    assert page.locator(".chat-chip").count() == 5
    assert not page.evaluate("document.querySelector('main').inert")
    page.wait_for_timeout(350)                                # after the opening slide
    box = {k: round(v) for k, v in panel.bounding_box().items()}
    assert box["width"] == 400 and box["height"] == 640 and box["x"] + box["width"] == 1440 - 24
    # an Enter the input method keeps for itself (a Japanese or Chinese conversion): nothing is sent
    page.fill("#chat-q", "은파 주")
    converting_enter(page, "차")
    page.wait_for_timeout(120)
    assert calls == []
    # Korean: the Enter that ends the last syllable sends at once (the 2026-10-14 bug: a guard after compositionend
    # swallowed it, so the reader had to press Enter twice)
    page.fill("#chat-q", "은파 주")
    korean_enter(page, "차")
    page.wait_for_selector(".chat-a .chat-card")
    assert calls[0]["messages"] == [{"role": "user", "content": "은파 주차"}]
    assert calls[0]["lang"] == "ko" and calls[0]["page"] == "/places/"
    md = page.locator(".chat-a .chat-md")
    assert "주차: 가능 — 무료" in md.inner_text() and md.locator("strong").inner_text() == "무료"
    assert md.locator("ul li").count() == 2
    links = md.locator("a")
    assert links.count() == 1 and links.first.get_attribute("href") == "/places/eunpa-lake-park/"   # checked; the fake one is text
    assert "없는 페이지" in md.inner_text() and md.locator(".chat-lk").count() == 0
    card = page.locator(".chat-card")
    assert card.get_attribute("href") == "/places/eunpa-lake-park/" and card.get_attribute("data-track") == "chat_link_click"
    page.wait_for_timeout(150)
    assert "은파호수공원은 쉬는 날 없이" in page.locator("[data-chat-live]").inner_text()
    # Esc closes; focus returns to the launcher
    page.keyboard.press("Escape")
    assert panel.is_hidden()
    assert page.evaluate("document.activeElement.classList.contains('chat-fab')")
    # the next page restores the open chat and the conversation from sessionStorage
    fab.click()
    panel.wait_for(state="visible")
    page.click(".chat-card")
    page.wait_for_url("**/places/eunpa-lake-park/")
    page.locator("#chat").wait_for(state="visible")
    assert "은파 주차" in page.inner_text("#chat") and page.locator(".chat-card").count() == 1
    assert errors == []
    ctx.close()


def test_phone_sheet_and_error_states(browser, site):
    ctx, page, errors, calls = open_page(browser, 390, 844, [NOT_CONFIGURED, BUSY, OK])
    page.goto(site + "/")
    # a Korean phone page (시안 A, operator 2026-11-05): the tab bar's 'AI 챗봇' button stands for the floating launcher
    # (not drawn there) — at the bottom of the screen from the first paint, on the home too, and while the page scrolls
    fab = page.locator(".tabbar [data-tab-chat]")
    assert fab.is_visible() and fab.inner_text().strip() == "AI 챗봇"
    assert page.evaluate("getComputedStyle(document.querySelector('.chat-fab')).display") == "none"
    box = fab.bounding_box()
    assert box["height"] >= 44 and box["width"] >= 44 and 844 - 110 <= box["y"] and box["y"] + box["height"] <= 844
    page.mouse.wheel(0, 700)
    page.wait_for_timeout(400)
    assert page.evaluate("scrollY") > 0 and fab.is_visible() and fab.bounding_box() == box
    fab.click()
    panel = page.locator("#chat")
    panel.wait_for(state="visible")
    assert panel.get_attribute("aria-modal") == "true"
    assert page.evaluate("document.querySelector('main').inert && document.querySelector('footer').inert")
    page.wait_for_timeout(350)
    sheet = {k: round(v) for k, v in panel.bounding_box().items()}
    assert sheet["x"] == 0 and sheet["y"] == 0 and sheet["width"] == 390 and sheet["height"] == 844
    assert page.evaluate("document.activeElement.id") == "chat-title"
    page.locator(".chat-chip").first.click()                   # 503 not_configured: a plain message and the search link
    page.wait_for_selector(".chat-err")
    assert "아직 연결되지 않았습니다" in page.inner_text(".chat-err")
    assert page.locator(".chat-err a[href='/search/']").count() == 1 and page.locator(".chat-retry").count() == 0
    page.fill("#chat-q", "다시 물어볼게요")
    page.click(".chat-send")
    page.wait_for_selector(".chat-retry")                      # an error event: retry
    page.click(".chat-retry")
    page.wait_for_selector(".chat-a .chat-card")
    assert len(calls) == 3 and calls[2]["messages"][-1]["content"] == "다시 물어볼게요"
    page.keyboard.press("Tab")
    assert page.evaluate("document.getElementById('chat').contains(document.activeElement)")
    page.click('.chat-ib[aria-label="닫기"]')
    assert panel.is_hidden() and not page.evaluate("document.querySelector('main').inert")
    # Chromium logs the scripted 503 as a failed resource; nothing else may reach the console
    assert [e for e in errors if "status of 503" not in e] == []
    ctx.close()


def test_on_a_phone_the_bar_s_button_opens_the_chat_and_gets_the_focus_back(browser, site):
    """On a phone the launcher is not on screen: the tab bar's 'AI 챗봇' (시안 A, 2026-11-05) and, on a place page, the
    bottom bar's (the calm pass 2026-11-10) press it for the reader (site.js [data-tab-chat]). While the sheet is open
    the bar is not drawn (it lay over half of the question box and the send button — found on the live site); closing
    the chat brings it back and gives the focus to the button that was pressed — it went to the hidden launcher, that
    is to <body>."""
    ctx, page, errors, calls = open_page(browser, 390, 844, [OK])
    for path, bar in (("/places/eunpa-lake-park/", ".pl-bar"), ("/places/", ".tabbar")):
        page.goto(site + path)
        button = page.locator(f"{bar} [data-tab-chat]")
        assert button.is_visible() and not page.locator(".chat-fab").is_visible()
        assert "AI 챗봇" in button.inner_text()
        box = button.bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44
        for close in ("Escape", "button"):
            button.focus()
            page.keyboard.press("Enter")
            panel = page.locator("#chat")
            panel.wait_for(state="visible")
            assert panel.get_attribute("aria-modal") == "true"
            # the bar steps out while the sheet is open: it was drawn over the question box and the send button
            assert not page.locator(bar).is_visible(), (path, close)
            send = page.locator(".chat-send").bounding_box()
            assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('#chat')",
                                 [send["x"] + send["width"] / 2, send["y"] + send["height"] - 3]), (path, close)
            if close == "Escape":
                page.keyboard.press("Escape")
            else:
                page.click('.chat-ib[aria-label="닫기"]')
            assert panel.is_hidden()
            assert page.evaluate("b => document.activeElement === document.querySelector(b + ' [data-tab-chat]')", bar), (path, close)
    assert errors == []
    ctx.close()


def test_each_limit_tells_the_reader_what_it_is(browser, site):
    """The client's minute (and the Firewall's 429): 'ask again in a minute', with retry. The client's day: the day's
    limit, no retry, the site search instead. The whole instance full: 'cannot answer right now', not the reader's
    doing."""
    ctx, page, errors, calls = open_page(browser, 1440, 900, LIMITED)
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    for i, q in enumerate(["하나", "둘", "셋", "넷"]):
        page.fill("#chat-q", q)
        page.keyboard.press("Enter")
        page.locator(".chat-err").nth(i).wait_for()
    errs = page.locator(".chat-err")
    minute, day, busy, firewall = (errs.nth(i).inner_text() for i in range(4))
    assert "1분 뒤" in minute and firewall == minute and errs.nth(0).locator(".chat-retry").count() == 1
    assert "1분" not in day and "내일" in day and "질문이 너무 잦습니다" not in day
    assert errs.nth(1).locator(".chat-retry").count() == 0 and errs.nth(1).locator("a[href='/search/']").count() == 1
    assert "지금은 답을 만들 수 없습니다" in busy and "1분" not in busy and errs.nth(2).locator(".chat-retry").count() == 1
    assert len(calls) == 4
    assert [e for e in errors if "status of 429" not in e] == []
    ctx.close()


def test_a_cut_answer_goes_on_in_place(browser, site):
    """done.cut: the last answer says it was cut and offers '이어서 보기'. That request carries continue: true and the cut
    answer, raw, as the last message; the rest streams into the same answer, the links of both parts stay links, the
    link cards are not doubled, and the next question sends the whole answer back with its links as page paths."""
    ctx, page, errors, calls = open_page(browser, 1440, 900, [stream_of(CUT_TEXT, cut=True), stream_of(REST), OK])
    page.add_init_script("window.__ga = []; window.gtag = function (k, name, p) { if (k === 'event') window.__ga.push([name, p]); };")
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", "일정 짜줘")
    page.keyboard.press("Enter")
    more = page.locator(".chat-a .chat-retry")
    more.wait_for()
    assert more.inner_text() == "이어서 보기" and "답이 길어 여기서 끊겼습니다" in page.inner_text(".chat-a")
    more.click()
    page.wait_for_function("document.querySelector('.chat-a .chat-md').innerText.includes('이동 확인이 필요한')")
    page.wait_for_timeout(100)
    assert calls[1]["continue"] is True
    assert calls[1]["messages"] == [{"role": "user", "content": "일정 짜줘"}, {"role": "assistant", "content": CUT_TEXT}]
    answer = page.locator(".chat-a")
    assert answer.count() == 1 and "요금: 무료 | 이동: 미확인" in answer.inner_text()   # one answer, joined at the cut
    assert "끊겼습니다" not in answer.inner_text() and answer.locator(".chat-retry").count() == 0
    assert answer.locator(".chat-md a[href='/places/eunpa-lake-park/']").count() == 1
    assert answer.locator(".chat-card").count() == 1
    # GA4: one answer in two parts — the rest is part 'more', so answers are counted on part 'first' only
    ends = [(p["outcome"], p["part"]) for name, p in page.evaluate("window.__ga") if name == "chat_answer"]
    assert ends == [("cut", "first"), ("answered", "more")], ends
    page.fill("#chat-q", "다음 질문")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('.chat-a').length === 2"
                           " && document.querySelectorAll('.chat-a')[1].querySelector('.chat-card')")
    prior = calls[2]["messages"]
    assert [m["role"] for m in prior] == ["user", "assistant", "user"] and "continue" not in calls[2]
    assert "요금: 무료 | 이동: 미확인" in prior[1]["content"]
    assert "[은파호수공원](/places/eunpa-lake-park/)" in prior[1]["content"]
    assert errors == []
    ctx.close()


def test_earlier_answers_go_back_with_page_paths_and_without_a_stopped_question(browser, site):
    """In this tab: a question the reader stopped (no answer) and a question with a long answer whose checked link is at
    the end (a Korean page path). The next request leaves the stopped question out, cuts the long answer to 2,000
    characters and keeps its link, as a readable page path."""
    long = "가" * 2300 + "\n[가옥](/places/한글/)"
    state = {"v": 1, "open": True, "msgs": [
        {"r": "u", "t": "3박 4일 일정 길게"}, {"r": "a", "t": "", "s": True},
        {"r": "u", "t": "첫 질문"},
        {"r": "a", "t": long, "f": {"/places/한글/": SITE + "/places/%ED%95%9C%EA%B8%80/"}, "l": []}]}
    ctx, page, errors, calls = open_page(browser, 1440, 900, [OK])
    page.goto(site + "/places/")
    page.evaluate("s => sessionStorage.setItem('gs-chat', JSON.stringify(s))", state)
    page.reload()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", "새 질문")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat-a .chat-card")
    msgs = calls[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "첫 질문" and msgs[2]["content"] == "새 질문"
    assert len(msgs[1]["content"]) <= 2000 and msgs[1]["content"].endswith(" …\n[가옥](/places/한글/)")
    assert errors == []
    ctx.close()


def test_an_official_booking_page_is_a_booking_card(browser, site):
    """예약하기 (pipeline/booking.py, chatbot/knowledge.js: link.book = the service, link.hl = the page's language): the
    card of an official booking page is a booking_click with the service as data-provider, the page's hreflang and
    chat_where, named '예약하기 · host'; a site page's card stays chat_link_click."""
    ferry = "https://island.theksa.co.kr/page/booking?lang="
    text = f"여객 표는 [한국해운조합 여객선예매]({ferry})에서 예매합니다. [은파호수공원](/places/eunpa-lake-park/)"
    book = {"title": "한국해운조합 여객선예매", "url": ferry, "ext": True, "book": "ferry", "hl": "ko"}
    deltas = [{"type": "text", "delta": text[i:i + 7]} for i in range(0, len(text), 7)]
    end = {"type": "done", "links": [PARK, book], "fix": {"/places/eunpa-lake-park/": PARK["url"], ferry: ferry}}
    resp = (200, sse(*deltas, end), "text/event-stream; charset=utf-8")
    ctx, page, errors, calls = open_page(browser, 1440, 900, [resp])
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.fill("#chat-q", "여객선 예매")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat-a .chat-card >> nth=1")
    cards = page.locator(".chat-card")
    assert cards.nth(0).get_attribute("data-track") == "chat_link_click"
    b = cards.nth(1)
    assert b.get_attribute("href") == ferry and b.get_attribute("data-track") == "booking_click"
    assert b.get_attribute("data-provider") == "ferry" and b.get_attribute("hreflang") == "ko"
    assert b.get_attribute("data-chat-where") == "panel" and b.get_attribute("target") == "_blank"
    assert b.locator(".chat-card-k").inner_text() == "예약하기 · island.theksa.co.kr"
    inline = page.locator(".chat-a .chat-md a[href^='https://island']")
    assert inline.count() == 1 and inline.get_attribute("data-track") == "chat_link_click"
    assert errors == []
    ctx.close()


# a day ahead in Korea: planQuery leaves out a day gone by
TRIP = (datetime.now(timezone(timedelta(hours=9))) + timedelta(days=30)).date()
PLAN_Q = f"{TRIP.year}년 {TRIP.month}월 {TRIP.day}일에 초등학생 아이와 차 없이 군산 당일치기, 점심 포함 코스를 짜 주세요"
PLAN_URL = f"/plan/?date={TRIP.isoformat()}&days=1&move=transit&with=kids"


def test_a_question_with_trip_conditions_gets_the_planner_with_them(browser, site):
    """The chatbot → planner handoff (2026-10-18): on a Korean page of a site with /plan/ (its header links it), the
    finished answer to a question that states trip conditions ends with one link, '이 조건으로 AI 코스 만들기', to
    /plan/ with exactly those conditions as URL parameters (chat.js planQuery; GA4 plan_cta with chat_where); a
    question that states none gets no link, nor does a failed answer; the link comes back with the conversation on the
    next page and opens the planner. A page without the planner's link, and a page in another language, never show it."""
    ctx, page, errors, calls = open_page(browser, 1440, 900, [OK, OK, BUSY])
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", PLAN_Q)
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat-a .chat-plan")
    link = page.locator(".chat-a .chat-plan")
    assert link.count() == 1 and link.inner_text().strip() == "이 조건으로 AI 코스 만들기"
    assert link.get_attribute("href") == PLAN_URL
    assert link.get_attribute("data-track") == "plan_cta" and link.get_attribute("data-chat-where") == "panel"
    # under the answer and its page cards, after the text
    assert page.evaluate("""(() => { const a = document.querySelector('.chat-a'); const kids = [...a.children];
      return kids.indexOf(a.querySelector('.chat-plan-w')) > kids.indexOf(a.querySelector('.chat-links')); })()""")
    for q in ("은파호수공원 주차", "비 오는 날 갈 곳"):   # no condition; a condition but the answer failed
        page.fill("#chat-q", q)
        page.keyboard.press("Enter")
        page.wait_for_function(f"document.querySelectorAll('.chat-a').length === {2 if q.startswith('은파') else 3} "
                               "&& !document.querySelector('.chat-send[data-mode=stop]')")
    page.wait_for_selector(".chat-a >> nth=2 >> .chat-err")
    assert page.locator(".chat-a .chat-plan").count() == 1
    # the next page: the conversation comes back with its link, which opens the planner with the conditions
    page.goto(site + "/places/")
    page.locator("#chat .chat-plan").wait_for()
    page.click("#chat .chat-plan")
    page.wait_for_url(f"**{PLAN_URL}")
    assert [e for e in errors if "status of" not in e] == []
    ctx.close()
    # no planner link on the page, or another language: no door
    for setup in ("document.querySelectorAll('a[data-track=\"plan_cta\"]').forEach((a) => a.remove())",
                  "document.documentElement.lang = 'en'"):
        ctx, page, errors, calls = open_page(browser, 1440, 900, [OK])
        page.goto(site + "/places/")
        page.evaluate(setup)   # before chat.js loads: it reads both once
        page.locator(".chat-fab").click()
        page.locator("#chat").wait_for(state="visible")
        page.fill("#chat-q", PLAN_Q)
        page.keyboard.press("Enter")
        page.wait_for_selector(".chat-a .chat-card")
        assert page.locator(".chat-plan").count() == 0, setup
        assert errors == []
        ctx.close()


def test_no_planner_link_under_a_stopped_or_cut_answer_and_the_link_keeps_the_conversation(browser, site):
    """The planner's door only under a finished answer (review 2026-10-18): an answer the reader stopped after its first
    words gets none, nor does an answer cut at the length limit while '이어서 보기' may still finish it — the finished
    answer does. Its link carries the conditions of the conversation's earlier questions with this question's own over
    them (chat.js planQuery): '자가용으로 가면요?' after the day-trip question keeps the date, the day trip and the
    child, by car."""
    ctx, page, errors, calls = open_page(browser, 1440, 900, [stream_of(CUT_TEXT, cut=True), stream_of(REST)])
    page.goto(site + "/places/")
    # the first answer streams its first words and then nothing until the reader stops it (the abort ends the stream)
    page.evaluate("""() => { const real = window.fetch; let held = true;
      window.fetch = (url, opt) => {   // the chat's first request (the tab panel's weather module asks too)
        if (!held || String(url).indexOf('/api/chat') < 0) return real(url, opt);
        held = false;
        const body = new ReadableStream({ start(c) {
          c.enqueue(new TextEncoder().encode('data: ' + JSON.stringify({ type: 'text', delta: '10월 19일 당일 후보 일정은 ' }) + '\\n\\n'));
          opt.signal.addEventListener('abort', () => c.error(new DOMException('stopped', 'AbortError')));
        } });
        return Promise.resolve(new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } }));
      }; }""")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", PLAN_Q)
    page.keyboard.press("Enter")
    page.wait_for_function("(document.querySelector('.chat-a .chat-md') || {}).innerText === '10월 19일 당일 후보 일정은'")
    page.locator(".chat-send[data-mode=stop]").click()
    page.wait_for_function("(document.querySelector('.chat-a .chat-note2') || {}).innerText === '답을 멈췄습니다.'")
    page.wait_for_timeout(100)
    assert page.locator(".chat-plan").count() == 0
    # cut: '이어서 보기', no door yet
    page.fill("#chat-q", "자가용으로 가면요?")
    page.keyboard.press("Enter")
    more = page.locator(".chat-a >> nth=1 >> .chat-retry")
    more.wait_for()
    assert more.inner_text() == "이어서 보기"
    assert page.locator(".chat-plan").count() == 0
    # finished: the door, with the conversation's conditions (by car now)
    more.click()
    page.wait_for_selector(".chat-a >> nth=1 >> .chat-plan")
    assert page.locator(".chat-plan").count() == 1
    href = f"/plan/?date={TRIP.isoformat()}&days=1&move=car&with=kids"
    assert page.locator(".chat-a >> nth=1 >> .chat-plan").get_attribute("href") == href
    # the next page: the stopped answer, its words kept, still has none; the finished one keeps its door
    page.goto(site + "/places/")
    page.locator("#chat .chat-a >> nth=1 >> .chat-plan").wait_for()
    first = page.locator("#chat .chat-a").first
    assert "10월 19일 당일 후보 일정은" in first.inner_text() and first.locator(".chat-plan").count() == 0
    assert page.locator("#chat .chat-plan").count() == 1
    assert len(calls) == 2 and calls[1]["continue"] is True
    assert errors == []
    ctx.close()


def test_a_long_conversation_keeps_its_first_question_and_answer(browser, site):
    """Review 2026-10-17 E05: only the last 12 messages went along, so the first question's conditions (people, ages,
    no car, budget) were gone in a long conversation. Past 12 messages, the first question and answer go along in place
    of the oldest two of the rest: 13 messages, alternating, the new question last."""
    msgs = []
    for i in range(10):
        msgs += [{"r": "u", "t": f"질문 {i}" + (" — 성인 2명, 7살 1명, 차 없음, 예산 1만원" if i == 0 else "")},
                 {"r": "a", "t": f"답 {i}", "l": []}]
    ctx, page, errors, calls = open_page(browser, 1440, 900, [OK])
    page.goto(site + "/places/")
    page.evaluate("s => sessionStorage.setItem('gs-chat', JSON.stringify(s))", {"v": 1, "open": True, "msgs": msgs})
    page.reload()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", "새 질문")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat-a .chat-card")
    sent = calls[0]["messages"]
    assert len(sent) == 13 and [m["role"] for m in sent] == ["user", "assistant"] * 6 + ["user"]
    assert "차 없음" in sent[0]["content"] and sent[1]["content"] == "답 0"
    assert sent[2]["content"] == "질문 5" and sent[-1]["content"] == "새 질문"
    assert errors == []
    ctx.close()


def test_the_note_links_the_help_page_in_the_page_s_own_language_when_the_site_has_it(browser, site):
    """UX01 (2026-10-24): the note under the question box linked /en/about/#chatbot from every page but the Korean and
    English ones, though each version has its own /<lang>/about/ with #chatbot. A page under /ja/ that links /ja/about/
    links the Japanese help; one that does not, the English."""
    from urllib.request import urlopen
    base = urlopen(site + "/places/").read().decode("utf-8").replace('<html lang="ko"', '<html lang="ja"', 1)
    for own, want in ((True, "/ja/about/#chatbot"), (False, "/en/about/#chatbot")):
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
        page = ctx.new_page()
        html = base.replace("</body>", '<a href="/ja/about/">サイト紹介と出典</a></body>', 1) if own else base
        serve = (lambda body: lambda r: r.fulfill(status=200, body=body, headers={"content-type": "text/html; charset=utf-8"}))(html)
        page.route("**/ja/places/", serve)
        page.goto(site + "/ja/places/")
        page.locator(".chat-fab").click()
        page.locator("#chat").wait_for(state="visible")
        assert page.get_attribute("#chat-note a", "href") == want, own
        ctx.close()


def test_an_answer_that_never_comes_stops_by_itself_and_the_question_asks_again(browser, site):
    """UX04 (2026-10-24): with no answer the button said '멈추기' after 65 seconds and nothing else happened. Nothing from
    the server for 100 seconds (past its own 90 for a whole answer, chatbot/server.js requestMs): the request stops as
    timed out, the question stays, '다시 시도' sends it again."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR")
    page = ctx.new_page()
    calls, held = [], []

    def handle(route):
        calls.append(route.request.post_data_json)
        if len(calls) == 1:
            held.append(route)   # the first request: no byte comes back
            return
        status, body, ctype = OK
        route.fulfill(status=status, body=body, headers={"content-type": ctype})
    page.route("**/api/chat/", handle)
    route_weather(page)   # the tab panel's weather module (tests/conftest.py)
    page.clock.install()
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.clock.run_for(500)
    page.fill("#chat-q", "은파호수공원 주차")
    page.click(".chat-send")
    page.clock.run_for(95000)
    assert page.locator(".chat-err").count() == 0                 # past the server's 90 s: still waiting
    page.clock.run_for(6000)
    assert page.text_content(".chat-err p") == "답이 너무 오래 걸려 멈췄습니다."
    assert page.locator(".chat-retry").count() == 1 and page.locator(".chat-send").is_visible()
    page.click(".chat-retry")
    page.clock.run_for(1500)
    page.wait_for_function("() => !!document.querySelector('.chat-a .chat-card')")
    assert len(calls) == 2 and calls[1]["messages"][-1] == {"role": "user", "content": "은파호수공원 주차"}


def test_each_answer_end_goes_to_ga4_without_its_words(browser, site):
    """Outside review 2026-10-17 (bundle D, which questions go unanswered): every answer's end is a GA4 chat_answer
    with its outcome — answered (site pages linked), no_links (none: often no data), cut, stopped or error with its
    code — the number of site pages it links, the answer's language and, for a Korean answer saying 사이트에 없음
    (rule 1), not_on_site; never the question's or the answer's words."""
    none = "그 식당의 할랄 메뉴 여부는 사이트에 없음입니다. 음식점에 직접 전화로 확인하세요."
    meta = {"type": "meta", "dir": "", "site": "ko", "lang": "ko"}
    answers = [
        (200, sse(meta, {"type": "text", "delta": "은파호수공원은 무료입니다. [은파호수공원](/places/eunpa-lake-park/)"},
                  {"type": "done", "links": [PARK], "fix": {"/places/eunpa-lake-park/": PARK["url"]}}),
         "text/event-stream; charset=utf-8"),
        (200, sse(meta, {"type": "text", "delta": none}, {"type": "done", "links": [], "fix": {}}),
         "text/event-stream; charset=utf-8"),
        (429, json.dumps({"code": "rate_limited"}), "application/json"),
    ]
    ctx, page, errors, calls = open_page(browser, 1440, 900, answers)
    page.add_init_script("window.__ga = []; window.gtag = function (k, name, p) { if (k === 'event') window.__ga.push([name, p]); };")
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    for i, q in enumerate(("은파호수공원 요금", "할랄 메뉴 있나요", "하나 더")):
        page.fill("#chat-q", q)
        page.keyboard.press("Enter")
        page.wait_for_function(f"window.__ga.filter(e => e[0] === 'chat_answer').length === {i + 1}")
    ends = [p for name, p in page.evaluate("window.__ga") if name == "chat_answer"]
    assert [e["outcome"] for e in ends] == ["answered", "no_links", "error"], ends
    assert [e["links"] for e in ends] == [1, 0, 0] and ends[2]["error_code"] == "rate_limited"
    assert ends[1].get("not_on_site") == "yes" and "not_on_site" not in ends[0]
    assert all(e["chat_where"] == "panel" and e["part"] == "first" for e in ends)
    # the answer's language is the one the server was sure of (meta.lang), 'und' when it sent none (the 429)
    assert [e["answer_lang"] for e in ends] == ["ko", "ko", "und"], ends
    words = json.dumps(page.evaluate("window.__ga"), ensure_ascii=False)
    assert "할랄" not in words and "은파호수공원 요금" not in words and "무료입니다" not in words
    assert [e for e in errors if "status of 429" not in e] == []   # the browser logs the 429 this test asked for
    ctx.close()
