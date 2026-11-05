"""시안 A 홈·휴대폰 아래 탭·장소 전화/길찾기 줄·파트너 되기 (군산 8f2370215·c4020e9bd·c2552acc7·7f2afaad7·3ee5bff35, ported
2026-11-05 under the operator's decisions of that day): the home opens with the cover card (cover photo, the H1, the
search, four answer tiles and the course buttons) and never shows the blog ('블로그는 없어') or the booking pages and their
buttons ('제휴링크는 일단 제외하자'); the phone tab bar has no 숙박 tab; a place opens with a call / route bar; the
recruiting page /partners/ and its inquiry page are the only partner pages ('파트너는 군산 말고는 없어') — no partner
stay, nothing of the first site's own case — and the side panel, phone menu and footer link them ('문의/제휴')."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import partners
from pipeline.build import State, build, make_env

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
CITY = ROOT / "data" / "suwon"   # this city


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("home-design")
    data = tmp / "data"
    shutil.copytree(SAMPLE, data)
    shutil.copy(CITY / "partners.json", data / "partners.json")
    out = tmp / "out"
    build(data, out, "sample")
    return out


def page(out, path):
    return (out / path.strip("/") / "index.html").read_text("utf-8") if path != "/" else (out / "index.html").read_text("utf-8")


def test_home_opens_with_the_cover_card_and_no_blog_or_booking(built):
    home = page(built, "/")
    assert re.search(r'<section class="ha"', home) and "<h1" in home
    assert home.index('class="ha"') < home.index("<h1")
    for gone in ("/blog/", "숙박 예약하기", "/stays/booking/", "sb-c", "rel=\"sponsored"):
        assert gone not in home, gone


def test_the_phone_tab_bar_has_no_stay_tab(built):
    home = page(built, "/")
    bar = re.search(r'<nav class="tabbar".*?</nav>', home, re.S).group(0)
    assert "숙박" not in bar and "data-tab-chat" in bar and 'href="/"' in bar


def test_a_place_page_opens_with_its_call_and_route_bar(built):
    places = sorted((built / "places").glob("*/index.html"))
    bars = [p for p in places if 'class="pl-bar"' in p.read_text("utf-8")]
    assert bars, "no place page has the call / route bar"
    html = bars[0].read_text("utf-8")
    bar = re.search(r'<div class="pl-bar">.*?</div>', html, re.S).group(0)
    assert 'data-track="tel_click"' in bar or 'data-track="route_click"' in bar or 'data-track="map_click"' in bar
    assert html.index('class="pl-bar"') < html.index('id="h-facts"')


def test_the_partners_pages_and_their_links(built):
    pn = page(built, partners.PATH)
    pc = page(built, partners.CONTACT_PATH)
    assert 'action="mailto:sales@o2o.kr"' in pc and "data-pc-form" in pc and 'data-to="sales@o2o.kr"' in pc
    assert partners.CONTACT_PATH in pn
    home = page(built, "/")
    links = re.findall(r'href="/partners/"[^>]*data-track="partner_cta"', home)
    assert len(links) >= 3                                           # panel, phone menu, footer
    for html in (pn, pc):
        for word in ("머뭄", "스테이,", "sb-pt", "pt-strip", "direct_booking_click"):   # (the sample's own name is 군산)
            assert word not in html, word


def test_this_city_lists_no_partner_stay():
    S = State(CITY, "preview")
    assert partners.data_problems(S) == []
    assert partners.contact(S) == "sales@o2o.kr"
    assert partners.mailto(S).startswith("mailto:sales@o2o.kr?subject=")
    assert [o["key"] for o in partners.offers(S)] == ["stay", "content"]
    reg = json.loads((CITY / "partners.json").read_text("utf-8"))
    shown = json.dumps({k: v for k, v in reg.items() if not k.startswith("_")}, ensure_ascii=False)
    assert "stays" not in reg and "머뭄" not in shown and "군산" not in shown
    assert not (ROOT / "pipeline" / "affiliate.py").exists()
    env = make_env()
    side = env.from_string('{% import "_side.html.j2" as sdm %}{{ sdm.partner(path, "/") }}').render(path=partners.PATH)
    assert f'href="{partners.PATH}"' in side and "문의/제휴" in side and 'data-track="partner_cta"' in side
    assert env.from_string('{% import "_side.html.j2" as sdm %}{{ sdm.partner("", "/") }}').render().strip() == ""
