"""Review 2026-10-22 (k4b-handoff), in Chromium on a sample build; /api/plan/ is never answered and /api/chat/ is a
scripted stream (nothing leaves the machine).

- C2 · S10: the assistant hands a reader over with only what it read; a date it did not read ('월요일' — it never
  guesses a day) is left empty, not the coming Saturday. The line over the form has two sets of words, picked before
  the first paint (no layout shift): a date carried, or none (asks for one); both say what the conversation did not
  say is the form's default. The button asks for the date ('날짜를 골라 주세요.') and puts the cursor on it; a reload
  keeps the empty date with the conditions.
- U4: on phones only the button's bar stays at the screen's foot — header + bar within 15% of the screen (CLAUDE.md
  7) — with the summary and the short notice in the page above it; the assistant's round button steps aside while the
  button is on screen; from 900px the box is as before. Step 4 says '선택'.
- daybounds: the hint by the two times says what they mean on a trip of several days.
- memory: the tab keeps the conversation's first exchange and its questions, so after a page change the planner door
  still carries the conditions of the earliest questions and the model still gets the first exchange; '새 대화'
  forgets them.
- U3: the log follows a growing answer only until its question reaches the top, so the conclusion stays in view; a
  conversation opened again shows its last question."""
import datetime
import json
import mimetypes
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline.build import build

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
# 'not read', not 'not said' (k4b review): the assistant never reads how many people come, and a child's age only in
# digits — '대화에 없던 조건' implied that '어른 3명', said and not carried, had been
DATED = "대화에서 읽은 조건만 채웠어요. 읽지 못한 조건(인원·아이 나이·예산 등)은 기본값이니 확인하고 코스 만들기를 누르세요."
UNDATED = ("대화에서 읽은 조건만 채웠어요. 날짜는 읽지 못해 비워 뒀으니 골라 주세요. "
           "그 밖에 읽지 못한 조건(인원·아이 나이·예산 등)은 기본값이에요.")
SHIFTS = """() => new Promise(r => { let s = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) s += e.value; })
  .observe({ type: 'layout-shift', buffered: true }); setTimeout(() => r(s), 400); })"""
PHONE = {"is_mobile": True, "has_touch": True}
# a day ahead in Korea (the planner's door reads only a written date from today on)
TRIP = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))) + datetime.timedelta(days=30)).date()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("k4b") / "out"
    build(SAMPLE, out, "sample")
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error as err:
            pytest.skip(f"Chromium is not installed for Playwright: {err}")
        yield b
        b.close()


def sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


def answer(text, links=()):
    return sse({"type": "meta", "dir": "", "site": "ko", "lang": "ko"},
               *[{"type": "text", "delta": text[i:i + 40]} for i in range(0, len(text), 40)],
               {"type": "done", "links": list(links), "fix": {}})


class Net:
    """The browser's whole network: the built site from disk; /api/chat/ answers `self.text`; /api/plan/ is refused
    (and recorded); plan.js can come late (`slow`), as on a slow phone."""

    def __init__(self, site, slow=0.0):
        self.site, self.slow, self.text, self.links = site, slow, "답입니다.", []
        self.chat: list = []
        self.plan: list = []

    def __call__(self, route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        if path == "/api/chat/":
            self.chat.append(route.request.post_data_json)
            return route.fulfill(status=200, body=answer(self.text, self.links), headers={"content-type": "text/event-stream; charset=utf-8"})
        if path.startswith("/api/"):
            self.plan.append(route.request.post_data_json)
            return route.abort()
        if self.slow and path.endswith("/assets/plan.js"):
            time.sleep(self.slow)
        f = self.site / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")


def new_page(browser, net, **kw):
    ctx = browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul", **kw)
    ctx.route("**/*", net)
    page = ctx.new_page()
    errors: list = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def html_has(page, cls):
    return page.evaluate("c => document.documentElement.classList.contains(c)", cls)


# ------------------------------------------------------------------ C2 · S10: the hand-over
@pytest.mark.parametrize("dev", [pytest.param({"viewport": {"width": 360, "height": 740}, **PHONE}, id="360"),
                                 pytest.param({"viewport": {"width": 390, "height": 844}, **PHONE}, id="390")])
def test_a_hand_over_with_no_date_leaves_it_empty_and_says_what_is_a_default(browser, site, dev):
    net = Net(site, slow=0.4)
    ctx, page, errors = new_page(browser, net, **dev)
    # the door of '월요일에 아이랑 군산 당일치기 가요. 대중교통으로 … 비 오는 날 … 유모차': no date key
    page.goto("http://site.test/plan/?days=1&move=transit&with=kids&needs=rain,stroller", wait_until="commit")
    page.wait_for_selector("[data-plan-form]", state="attached")
    # before plan.js: the room and the words that ask for a date are chosen from the address
    assert html_has(page, "trp-handing") and html_has(page, "trp-undated")
    page.wait_for_function("document.querySelector('.trp-handed').textContent !== ''")
    assert page.text_content(".trp-handed") == UNDATED
    page.wait_for_timeout(200)
    assert page.evaluate(SHIFTS) == 0
    assert page.input_value("input[name=date]") == ""
    assert page.text_content("[data-plan-sum]").startswith("날짜 미정 · 당일치기 · 대중교통·걷기 · 아이와 가족(어른 2, 아이 7살)")
    # the button asks for the date and puts the cursor on it; nothing is sent
    page.click(".trp-submit")
    assert page.text_content("[data-plan-formerr]") == "날짜를 골라 주세요."
    assert page.evaluate("document.activeElement.name") == "date" and net.plan == []
    # a date picked: the line under the button goes, and with it the bar's extra height (k4b review: it stayed, and
    # held header + bar at 17.8% of a 390×844 screen — CLAUDE.md 7 allows 15%)
    page.fill("input[name=date]", page.get_attribute("input[name=date]", "min"))
    assert page.is_hidden("[data-plan-formerr]")
    page.evaluate("document.querySelectorAll('.trp-step')[2].scrollIntoView({block: 'start'})")
    page.wait_for_timeout(300)
    assert page.evaluate("""() => document.querySelector('.mast').getBoundingClientRect().height
      + document.querySelector('.trp-go-bar').getBoundingClientRect().height <= 0.15 * innerHeight""")
    page.fill("input[name=date]", "")
    # a reload keeps the conditions and the empty date (no line: the address is spent)
    page.reload(wait_until="load")
    page.wait_for_timeout(300)
    assert page.input_value("input[name=date]") == "" and not html_has(page, "trp-handing")
    assert page.is_checked('input[name="move"][value="transit"]') and page.is_checked('input[name="needs"][value="stroller"]')
    # a date picked: it goes
    day = page.get_attribute("input[name=date]", "min")
    page.fill("input[name=date]", day)
    page.click(".trp-submit")
    page.wait_for_function("document.querySelector('[data-plan-work]').hidden === false || document.querySelector('.trp-fail')")
    assert net.plan and net.plan[0]["conditions"]["date"] == day and net.plan[0]["conditions"]["move"] == "transit"
    assert errors == [], errors
    ctx.close()


def test_a_hand_over_with_a_date_keeps_it_and_one_gone_by_is_none(browser, site):
    net = Net(site, slow=0.4)
    ctx, page, errors = new_page(browser, net, viewport={"width": 390, "height": 844}, **PHONE)
    page.goto(f"http://site.test/plan/?date={TRIP.isoformat()}&days=2&move=car", wait_until="commit")
    page.wait_for_selector("[data-plan-form]", state="attached")
    assert html_has(page, "trp-handing") and not html_has(page, "trp-undated")
    page.wait_for_function("document.querySelector('.trp-handed').textContent !== ''")
    assert page.text_content(".trp-handed") == DATED
    page.wait_for_timeout(200)
    assert page.evaluate(SHIFTS) == 0 and page.input_value("input[name=date]") == TRIP.isoformat()
    # a date gone by (a door opened days later) is no date: the same as none, from the first paint
    page.goto("http://site.test/plan/?date=2020-01-04&days=2", wait_until="commit")
    page.wait_for_selector("[data-plan-form]", state="attached")
    assert html_has(page, "trp-undated")
    page.wait_for_function("document.querySelector('.trp-handed').textContent !== ''")
    assert page.text_content(".trp-handed") == UNDATED and page.input_value("input[name=date]") == ""
    page.wait_for_timeout(200)
    assert page.evaluate(SHIFTS) == 0
    # the page again in this tab: the conditions it kept, the date still empty, no line
    page.goto("http://site.test/plan/", wait_until="load")
    page.wait_for_timeout(200)
    assert page.input_value("input[name=date]") == "" and page.is_checked('input[name="days"][value="2"]')
    assert not html_has(page, "trp-handing")
    assert errors == [] and net.plan == [], errors
    ctx.close()
    # a plain visit in a new tab: the coming Saturday as before, no line
    ctx, page, errors = new_page(browser, net, viewport={"width": 390, "height": 844}, **PHONE)
    page.goto("http://site.test/plan/", wait_until="load")
    sat = page.input_value("input[name=date]")
    assert sat and datetime.date.fromisoformat(sat).weekday() == 5 and not html_has(page, "trp-handing")
    assert errors == [], errors
    ctx.close()


# ------------------------------------------------------------------ U4 · daybounds: the form
FIXED = """() => { const mast = document.querySelector('.mast').getBoundingClientRect();
  const bar = document.querySelector('.trp-go-bar'), b = bar.getBoundingClientRect(), cs = getComputedStyle(bar);
  return {mast: mast.height, bar: b.height, barBottom: b.bottom, pos: cs.position, vh: innerHeight,
          submit: document.querySelector('.trp-submit').getBoundingClientRect().height,
          inBar: [...bar.querySelectorAll('.trp-sum, .trp-fine-s, .trp-fine')].length,
          fab: getComputedStyle(document.querySelector('.chat-fab')).visibility,
          formFits: [...document.querySelectorAll('.trp-form *')].every((e) => { const r = e.getBoundingClientRect(); return !r.width || r.right <= innerWidth + 0.5; })}; }"""


@pytest.mark.parametrize("w,h", [(390, 844), (360, 740), (375, 667)])
def test_on_phones_only_the_buttons_bar_stays_at_the_foot_within_the_fixed_area_rule(browser, site, w, h):
    net = Net(site)
    ctx, page, errors = new_page(browser, net, viewport={"width": w, "height": h}, **PHONE)
    page.goto("http://site.test/plan/", wait_until="load")
    page.wait_for_timeout(300)
    assert page.evaluate("getComputedStyle(document.querySelector('.chat-fab')).visibility") == "visible"   # the hero: there
    page.evaluate("document.querySelectorAll('.trp-step')[2].scrollIntoView({block: 'start'})")
    page.wait_for_timeout(500)
    m = page.evaluate(FIXED)
    # (measured in the layout viewport: the sample build's header menu is 12px wider than a 360px screen, which zooms
    # the page out a little — the share of the screen is the same)
    assert m["pos"] == "sticky" and abs(m["barBottom"] - m["vh"]) < 1, m
    assert m["mast"] + m["bar"] <= 0.15 * m["vh"], m               # CLAUDE.md 7: the fixed areas ≤ 15% of the screen
    assert m["submit"] >= 44 and m["inBar"] == 0, m                # a 44px target; only the button (and its error)
    assert m["fab"] == "hidden" and m["formFits"], m                # the round button steps aside while the button shows
    # the summary and the short notice: in the page right above the bar, not under it
    page.evaluate("window.scrollTo(0, document.querySelector('.trp-sum').getBoundingClientRect().top + scrollY - 300)")
    page.wait_for_timeout(300)
    r = page.evaluate("""() => ({fine: document.querySelector('.trp-fine-s').getBoundingClientRect().bottom,
      finePos: getComputedStyle(document.querySelector('.trp-fine-s')).position,
      sum: document.querySelector('.trp-sum').getBoundingClientRect().bottom,
      bar: document.querySelector('.trp-go-bar').getBoundingClientRect().top})""")
    assert r["finePos"] == "static" and page.is_visible(".trp-fine-s") and r["sum"] <= r["fine"] <= r["bar"], r
    # back at the top (the bar out of sight): the round button is there again
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_function("getComputedStyle(document.querySelector('.chat-fab')).visibility === 'visible'")
    assert errors == [], errors
    ctx.close()


def test_from_900px_the_box_is_as_before_and_the_form_says_what_is_optional(browser, site):
    net = Net(site)
    ctx, page, errors = new_page(browser, net, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/plan/", wait_until="load")
    page.evaluate("document.querySelector('.trp-sum').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)
    box = page.evaluate("""() => { const g = document.querySelector('.trp-go'), r = g.getBoundingClientRect(), cs = getComputedStyle(g);
      const inside = (s) => { const e = document.querySelector(s).getBoundingClientRect(); return e.top >= r.top && e.bottom <= r.bottom && e.height > 0; };
      return {pos: cs.position, display: cs.display, sum: inside('.trp-sum'), submit: inside('.trp-submit'), fine: inside('.trp-fine'),
              order: document.querySelector('.trp-sum').getBoundingClientRect().top < document.querySelector('.trp-submit').getBoundingClientRect().top
                && document.querySelector('.trp-submit').getBoundingClientRect().top < document.querySelector('.trp-fine').getBoundingClientRect().top}; }""")
    assert box == {"pos": "static", "display": "grid", "sum": True, "submit": True, "fine": True, "order": True}, box
    assert page.is_hidden(".trp-fine-s")
    # step 4 is optional and says so; the two times on a trip of several days
    assert "선택" in page.text_content(".trp-step:nth-of-type(4) legend")
    hint = page.text_content(".trp-step:first-of-type .trp-hint")
    # (operator 2026-10-24: the check holds every day to both times for the places to visit and the cafés; a day before
    # a night has its dinner and the night's stay after the end — the hint says so)
    assert "여러 날이면 둘러볼 곳과 카페는 날마다 하루 시작부터 하루 끝 안에 넣습니다." in hint
    assert "밤을 묵는 날은 저녁 식사와 숙소를 하루 끝 뒤에도 둡니다(하루 끝이 17:30 이후면 저녁 시간에 그날 여는 음식점을 넣어요)." in hint
    assert "마지막 날은 모든 일정을 하루 끝까지 마칩니다." in hint
    # an error comes last in the box, as before
    page.fill("input[name=date]", "")
    page.click(".trp-submit")
    assert page.text_content("[data-plan-formerr]") == "날짜를 골라 주세요."
    assert page.evaluate("""() => document.querySelector('.trp-err').getBoundingClientRect().top
      > document.querySelector('.trp-fine').getBoundingClientRect().top""")
    assert errors == [] and net.plan == [], errors
    ctx.close()


# ------------------------------------------------------------------ memory and U3: the assistant
def open_chat(page, path):
    """The page, with the panel: restored when the tab left it open (site.js, after load), else from the launcher — on
    a Korean phone from the tab bar's 'AI 챗봇' button, which stands for it there (시안 A, operator 2026-11-05)."""
    page.goto("http://site.test" + path, wait_until="load")
    restores = page.evaluate("(() => { try { return !!(JSON.parse(sessionStorage.getItem('gs-chat')) || {}).open; } catch (e) { return false; } })()")
    if not restores:
        bar = page.locator(".tabbar [data-tab-chat]")
        (bar if bar.count() and bar.is_visible() else page.locator(".chat-fab")).click()
    page.locator("#chat").wait_for(state="visible")
    page.wait_for_function("!!window.gsChat")


def ask(page, q):
    page.evaluate("q => window.gsChat.ask(q)", q)
    page.wait_for_function("!window.gsChat.busy()")
    hrefs = page.evaluate("[...document.querySelectorAll('#chat a.chat-plan')].map(a => decodeURIComponent(a.getAttribute('href')))")
    return hrefs[-1] if hrefs else None


def test_a_long_conversation_keeps_its_first_exchange_and_its_questions_across_pages(browser, site):
    net = Net(site)
    ctx, page, errors = new_page(browser, net, viewport={"width": 1440, "height": 900})
    open_chat(page, "/places/")
    q1 = f"{TRIP.month}월 {TRIP.day}일에 2살 아이랑 대중교통으로 당일치기 가요"
    full = f"/plan/?date={TRIP.isoformat()}&days=1&move=transit&with=kids&kids=2"
    assert ask(page, q1) == full
    for i in range(11):
        ask(page, f"선유도 가는 법 알려 주세요 {i}")
    assert ask(page, "비 오는 날 갈 곳 있나요?") == full + "&needs=rain"
    kept = page.evaluate("JSON.parse(sessionStorage.getItem('gs-chat'))")
    assert len(kept["msgs"]) == 24 and kept["msgs"][0] == {"r": "u", "t": q1} and kept["msgs"][1]["r"] == "a"
    assert kept["msgs"][2]["t"] == "선유도 가는 법 알려 주세요 1"          # then the last 22
    assert len(kept["q"]) == 13 and kept["q"][0] == q1 and kept["q"][-1] == "비 오는 날 갈 곳 있나요?"
    # another page: the door still carries the first question's conditions, the model still gets the first exchange
    open_chat(page, "/courses/")
    assert ask(page, "유모차로 다닐 만한 비 오는 날 코스?") == full + "&needs=rain,stroller"
    assert net.chat[-1]["messages"][0]["content"] == q1 and len(net.chat[-1]["messages"]) == 13
    # conditions spread over the early questions, past the stored messages: all of them still count
    page.click("#chat .chat-ib[aria-label='새 대화']")
    assert ask(page, "유모차로 다닐 만한 비 오는 날 코스?") == "/plan/?needs=rain,stroller"   # '새 대화' forgot the old ones
    page.click("#chat .chat-ib[aria-label='새 대화']")
    for q in [f"{TRIP.month}월 {TRIP.day}일에 가요", "대중교통으로 가요", "2살 아이랑 가요"] + [f"선유도 가는 법 {i}" for i in range(12)]:
        ask(page, q)
    open_chat(page, "/places/")
    assert ask(page, "유모차로 다닐 만한 비 오는 날 코스?") == (
        f"/plan/?date={TRIP.isoformat()}&move=transit&with=kids&kids=2&needs=rain,stroller")
    assert errors == [], errors
    ctx.close()


LONG = ("결론: 선유도는 시내버스로 갈 수 있고, 비 오는 날에는 실내 장소를 먼저 보세요.\n\n"
        + "\n".join(f"- 항목 {i}: 답의 뒷부분입니다. 길게 이어지는 설명이 여기에 들어갑니다." for i in range(14)))
CARDS = [{"title": f"관련 페이지 {i}", "url": "https://gunsan.webforai.kr/places/", "ext": False} for i in range(6)]
GEO = """() => { const log = document.querySelector('#chat .chat-log'), L = log.getBoundingClientRect();
  const first = [...document.querySelectorAll('#chat .chat-a')].at(-1).querySelector('p').getBoundingClientRect();
  return {inView: first.top >= L.top && first.bottom <= L.bottom, top: log.scrollTop, end: log.scrollHeight - log.clientHeight}; }"""


@pytest.mark.parametrize("w,h", [(390, 844), (1440, 900)])
def test_the_log_keeps_an_answers_first_lines_in_view(browser, site, w, h):
    net = Net(site)
    ctx, page, errors = new_page(browser, net, viewport={"width": w, "height": h}, **(PHONE if w < 900 else {}))
    open_chat(page, "/places/")
    ask(page, "선유도 가는 법")                                   # a short answer: the log at its end
    page.wait_for_timeout(100)
    g = page.evaluate(GEO)
    assert g["inView"] and abs(g["top"] - g["end"]) <= 1, g
    net.text, net.links = LONG, CARDS                              # longer than the log, with its cards
    ask(page, "선유도 가는 법과 비 오는 날 갈 곳 알려 주세요")
    page.wait_for_timeout(100)
    g = page.evaluate(GEO)
    assert g["inView"] and g["top"] < g["end"] - 100, g             # its conclusion, not its last cards
    assert page.locator("#chat .chat-a").last.locator(".chat-card").count() == 6   # the cards stay
    # the conversation opened again on the next page: at its last question
    open_chat(page, "/courses/")
    page.wait_for_timeout(100)
    g = page.evaluate(GEO)
    assert g["inView"] and g["top"] < g["end"] - 100, g
    assert errors == [], errors
    ctx.close()
