"""List filters of /places/, /food/, /stays/ and /map/ — ported from the first site (its outside evaluation 2026-10-18,
fc51ca0ec · 857d1beec: after one type chip cut a list the other chips kept their whole-list counts, and two filters
gave 0 places with only a sentence telling to change them). Now (site.js 'list filters', templates/_filters.html.j2):
faceted counts (each chip reads the places the list would show if it were chosen with the other groups' filters; one
that would show none reads 0, drawn faint, still a working button); at zero results one '<값> 조건 해제' button per
filter whose removal alone brings places back, then '전체 조건 초기화'; the map caption names the shown places that
are not on the map; /map/ counts its kind toggles for the chosen group, says its count in a status line and offers
the hidden kinds back when nothing is left. Without JS the bar and the panel are absent and the lists complete.
The build: the sample data (three attractions, three themes, none free); the browser tests (Playwright + Chromium, a
local server — nothing leaves the machine) run as a phone (390px) and a desktop (1440px)."""
import functools
import http.server
import re
import shutil
import threading
from pathlib import Path

import pytest

from pipeline import locales as LC
from pipeline.build import build, make_env
from pipeline.present import filter_vm

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("filters")
    data = tmp / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    out = tmp / "out"
    build(data, out, "sample")
    return out


def test_the_zero_panel_is_built_hidden_between_the_bar_and_the_ledger_in_the_page_s_words(built):
    h = (built / "places" / "index.html").read_text("utf-8")
    w = LC.LIST_WORDS["ko"]
    panel = re.search(r'<p class="empty" data-empty hidden>([^<]*)</p>\s*<div class="f-undo" data-f-undo data-one="([^"]*)" '
                      r'hidden><button type="button" data-f-reset>([^<]*)</button></div>', h)
    assert panel and h.index("data-filters hidden") < panel.start() < h.index('<div class="ledger" data-ledger>')
    assert panel.groups() == (w["empty"], "{v} 조건 해제", "전체 조건 초기화")
    assert h.count("data-empty") == 1   # no second sentence inside the ledger
    # /map/: the kind toggles carry their counts, a status count line, the zero panel with the kinds' undo words
    m = (built / "map" / "index.html").read_text("utf-8")
    assert re.search(r'data-kind="attraction" aria-pressed="true">.*?관광지 <span class="tn">\d+</span></button>', m)
    assert re.search(r'<p class="f-result" role="status"><span data-map-result data-tpl="장소 \{n\}곳" '
                     r'data-of=" \(전체 \{m\}곳 중\)">장소 \d+곳</span></p>', m)
    assert 'data-map-undo data-one="{v} 조건 해제" data-kind-one="{v} 숨김 해제" hidden><button type="button" data-map-reset>' in m


def test_the_caption_names_the_places_off_the_map_in_every_version():
    F = filter_vm(4, [], [], [], ("free", "요금 무료", 0), 4, LC.LIST_WORDS["ko"], {"other": "관광지 {n}곳"})
    assert F["n_off"] == 0 and filter_vm(9, [], [], [], (), 4, LC.LIST_WORDS["ko"], {})["n_off"] == 5
    fb = make_env().get_template("_filters.html.j2").module
    assert str(fb.off_map(0, LC.LIST_WORDS["ko"])).strip() == ""
    assert str(fb.off_map(23, LC.LIST_WORDS["en"])) == \
        '<span data-geo-off data-tpl=" · Not on the map: {n} (see the list)"> · Not on the map: 23 (see the list)</span>'
    for code, words in LC.LIST_WORDS.items():
        assert "{v}" in words["clear_one"] and words["clear_all"] and "{n}" in words["off_map"], code


sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def site(built):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            return None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(built)))
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


SHOWN = "document.querySelectorAll('.rec:not([hidden])').length"


@pytest.mark.parametrize("width", [390, 1440])
def test_each_chip_shows_its_number_and_zero_results_offer_one_press_ways_back(browser, site, width):
    ctx = browser.new_context(viewport={"width": width, "height": 860}, locale="ko-KR", has_touch=width < 600)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # a theme and '요금 무료' together leave nothing (no sample place is free)
    page.goto(site + "/places/?theme=parks-nature&check=1")
    page.wait_for_load_state("load")
    assert page.evaluate(SHOWN) == 0
    assert page.is_visible("[data-empty]") and page.is_visible("[data-f-undo]")
    undo = page.eval_on_selector_all("[data-f-undo] button", "bs => bs.map(b => b.textContent)")
    # taking the theme off alone still leaves nothing (no free place): only '요금 무료' gets a button, then the reset
    assert undo == ["요금 무료 조건 해제", "전체 조건 초기화"], undo
    page.click("[data-f-undo] button[data-f-undo-k]")
    assert page.evaluate(SHOWN) == 1 and not page.is_visible("[data-empty]") and not page.is_visible("[data-f-undo]")
    assert page.evaluate("document.activeElement.closest('.f-result') !== null")
    # the reset from a zero result brings every place back
    page.goto(site + "/places/?theme=parks-nature&check=1")
    page.wait_for_load_state("load")
    page.click("[data-f-reset]")
    total = page.evaluate("document.querySelectorAll('.rec').length")
    assert page.evaluate(SHOWN) == total
    # faceted counts: pressing a chip shows exactly the number it read; a chip that reads 0 is faint, still a button
    if width < 1024:
        more = page.query_selector("[data-f-more]")
        if more and more.is_visible():
            more.click()
    chips = page.eval_on_selector_all("[data-filters] button[data-f]", "bs => bs.map(b => [b.dataset.f, b.dataset.v])")
    assert len(chips) >= 3
    for f, v in chips:
        sel = f'[data-filters] button[data-f="{f}"][data-v="{v}"]'
        n = int(page.eval_on_selector(sel, "b => b.querySelector('.tn') ? b.querySelector('.tn').textContent : '-1'"))
        if n < 0:
            continue
        page.eval_on_selector(sel, "b => b.click()")
        assert page.evaluate(SHOWN) == n, (f, v, n)
    zero = page.eval_on_selector_all(".f-row button.is-zero", "bs => bs.map(b => [b.tagName, b.getAttribute('aria-disabled')])")
    assert all(t == "BUTTON" and d is None for t, d in zero)
    assert errors == []
    ctx.close()


def test_map_hiding_every_kind_offers_the_kinds_back(browser, site):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR")
    page = ctx.new_page()
    page.goto(site + "/map/")
    page.wait_for_load_state("load")
    total = page.evaluate("document.querySelectorAll('[data-kind-row]').length")
    assert page.inner_text("[data-map-result]") == f"장소 {total}곳"
    for k in ("attraction", "stay", "food"):
        page.click(f'[data-kinds] button[data-kind="{k}"]')
    assert page.is_visible("[data-map-empty]") and page.is_visible("[data-map-undo]")
    labels = page.eval_on_selector_all("[data-map-undo] button", "bs => bs.map(b => b.textContent)")
    assert labels[-1] == "전체 조건 초기화" and all(x.endswith("숨김 해제") for x in labels[:-1]) and labels[:-1], labels
    page.click("[data-map-undo] button:first-child")
    assert not page.is_visible("[data-map-empty]")
    assert re.match(r"장소 \d+곳", page.inner_text("[data-map-result]"))
    ctx.close()
