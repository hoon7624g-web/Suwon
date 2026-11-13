"""공유하기 — 보내기 (pipeline/share.py; the first site's operator decision 2026-11-11, carried here 2026-11-13): the
군산각 tests/test_present.py share tests, on this engine's fixture (tests/fixtures/gunsan_subset) with a Kakao key and
the company's four related sites laid over it.

- share.view tags every plain tile and draws the QR code;
- the box stands where the operator placed it (a place page under its route row, a guide and a course before 이어서
  보기, an event under its route, the home's '<지역>각 알리기' before 제휴·관련 사이트) and every Korean page with the
  panel holds the site's dialog and its two openers;
- link previews: a Type1 photo, else the logo card on a place page, else the site's picture — never a Type3 photo;
- in a browser: 링크 복사, 카카오톡 (a stand-in SDK 2.x: no Kakao.Share before Kakao.init), 문자 and the panel's dialog;
- a site without a Kakao key (an OSM site) has no 카카오톡 tile."""
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

from pipeline import present, share
from pipeline.build import State, build

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "fixtures" / "gunsan_subset"
KEY = "0123456789abcdef0123456789abcdef"
SHR_BOX = re.compile(r'<div class="shr[^"]*" role="group" aria-labelledby="([^"]+)" data-shr data-shr-url="([^"]+)" '
                     r'data-shr-title="([^"]*)" data-shr-id="([^"]*)"')


def _data(tmp: Path, key: str = KEY) -> Path:
    data = tmp / "data"
    shutil.copytree(DATA, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    if key:
        site["kakao_js_key"] = key
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    shutil.copy(ROOT / "data" / "suwon" / "related_sites.json", data / "related_sites.json")
    return data


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("share")
    data = _data(tmp)
    out = tmp / "preview"
    build(data, out, "preview")
    return State(data, "preview"), out


def _place_with_route(S, out):
    for e in S.entities:
        f = out / unquote(e["_path"]).strip("/") / "index.html"
        if f.is_file() and "data-route" in f.read_text("utf-8") and e.get("kind") == "food":
            return e
    raise AssertionError("no food place with a route row in the fixture")


def test_share_view_tags_every_link_and_draws_the_qr_code():
    url = "https://example.com/places/%EB%AA%A8%ED%8A%B8/"
    v = share.view(url, "모트 | 예시각", "place-1")
    assert v["url"] == url and v["id"] == "place-1"
    for key, prefix in (("sms", "sms:?&body="), ("facebook", "https://www.facebook.com/sharer/sharer.php?u="),
                        ("x", "https://x.com/intent/tweet?text="), ("band", "https://band.us/plugin/share?body=")):
        assert v[key].startswith(prefix), key
        assert f"{url}?utm_source=share&utm_medium={key}" in unquote(v[key]), key
    assert "모트 | 예시각" in unquote(v["sms"]) and "&route=example.com" in v["band"]
    assert v["qr"].startswith('<svg aria-hidden="true" focusable="false" viewBox=') and 'class="shr-qr-i"' in v["qr"]
    assert share.tagged(url + "?a=1", "qr") == url + "?a=1&utm_source=share&utm_medium=qr"


def test_the_send_box_stands_where_the_operator_placed_it(world):
    S, built = world
    e = _place_with_route(S, built)
    g = next((x for x in S.guides if present.see_also(S, "guide", x)), S.guides[0])
    pages = {e["_path"]: ("같이 갈 사람에게 보내기", e["id"]), g["_path"]: ("이 가이드 보내기", g["id"]),
             S.courses[0]["_path"]: ("이 코스 보내기", S.courses[0]["id"]),
             S.series[0]["_path"]: ("같이 갈 사람에게 보내기", S.series[0]["key"])}
    for path, (title, rid) in pages.items():
        html = (built / unquote(path).strip("/") / "index.html").read_text("utf-8")
        canon = re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)
        boxes = SHR_BOX.findall(html)
        assert [b for b in boxes if b[0] == "h-shr"] == [("h-shr", canon, boxes[0][2], rid)], path
        assert '<p class="shr-h" id="h-shr">' in html and f"<span>{title}</span>" in html, path
        assert f'data-shr-key="{KEY}" data-shr-sdk="{share.SDK}" data-shr-sri="{share.SDK_SRI}"' in html, path
        for do in ("kakao", "copy_link", "sms", "web_share", "facebook", "x", "band"):
            assert f'data-shr-do="{do}"' in html, (path, do)
        assert "utm_medium%3Dfacebook" in html and 'class="shr-qr-i"' in html, path
        box_at = html.index('id="h-shr"')
        if path == e["_path"]:
            assert html.index("data-route") < box_at, path
        elif "/events/" not in path and 'id="h-see"' in html:
            assert box_at < html.index('id="h-see"'), path
    home = (built / "index.html").read_text("utf-8")
    name = S.site["site_name"]
    assert re.search(r'<section class="home-shr[^"]*" id="share" aria-labelledby="h-home-shr">', home)
    assert home.index('id="share"') < home.index('제휴·관련 사이트', home.index('id="share"'))
    site_url = S.site["site_url"].rstrip("/") + "/"
    assert ("h-home-shr", site_url, name, "site") in SHR_BOX.findall(home)
    for path in ("index.html", "places/index.html", unquote(e["_path"]).strip("/") + "/index.html"):
        html = (built / path).read_text("utf-8")
        assert html.count('<dialog class="shr-dlg" id="shr-site"') == 1, path
        assert ("shr-site-h", site_url, name, "site") in SHR_BOX.findall(html), path
        assert html.count('<a class="sd-shr-a" href="/#share" data-shr-open="shr-site">') == 2, path
        side = html[html.index('<div class="side">'):]
        assert 'class="sd-shr"' in side, path
        if 'class="sd-pt"' in side:   # '문의/제휴' (a site with partners.json): the share card right above it
            assert side.index('class="sd-shr"') < side.index('class="sd-pt"'), path


def test_link_previews_show_a_type1_photo_or_the_sites_picture(world):
    S, built = world
    type3 = {im["url"] for e in S.entities for im in e["_images"] if im.get("license") != "KOGL-1"}
    card = S.site["site_url"].rstrip("/") + "/assets/brand/og-card.png"
    seen = {"card": 0, "photo": 0}
    for e in S.entities:
        f = built / unquote(e["_path"]).strip("/") / "index.html"
        if not f.is_file():
            continue
        html = f.read_text("utf-8")
        og = re.search(r'<meta property="og:image" content="([^"]+)"', html).group(1)
        own1 = [im["url"] for im in e["_images"] if im.get("license") == "KOGL-1"]
        assert og == (own1[0] if own1 else card), e["id"]
        seen["card" if og == card else "photo"] += 1
    assert seen["card"] or seen["photo"]
    assert (built / "assets" / "brand" / "og-card.png").is_file()
    for f in [built / "index.html", *built.glob("guides/*/index.html"), *built.glob("courses/*/index.html"),
              built / "places" / "index.html", built / "food" / "index.html"]:
        m = re.search(r'<meta property="og:image" content="([^"]+)"', f.read_text("utf-8"))
        assert not m or m.group(1) not in type3, f


def test_without_a_kakao_key_the_box_has_no_kakaotalk_tile(tmp_path):
    S0 = State(_data(tmp_path / "a", key=""), "preview")
    assert not S0.site.get("kakao_js_key")
    out = tmp_path / "out"
    build(_data(tmp_path / "b", key=""), out, "preview")
    home = (out / "index.html").read_text("utf-8")
    assert 'id="share"' in home and 'data-shr-do="copy_link"' in home
    assert 'data-shr-do="kakao"' not in home and "data-shr-key" not in home


SHARE_STUBS = """
window.__events = []; window.__copied = []; window.__shared = [];
window.siteTrack = function (name, params) { window.__events.push([name, params]); };
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function (t) {
  window.__copied.push(t); return Promise.resolve(); }}});
var mode = (location.search.match(/share=(\\w+)/) || [])[1];
Object.defineProperty(navigator, 'share', {configurable: true, value: mode === 'none' ? undefined : function (data) {
  window.__shared.push(data); return Promise.resolve(); }});
"""
# as the real SDK 2.x: no Kakao.Share before Kakao.init (the first site's live check, 2026-11-12)
KAKAO_STUB = """window.__kakao = [];
window.Kakao = {_on: false, isInitialized: function () { return this._on; },
  init: function (k) { this._on = true; window.__kakao.push(['init', k]);
    this.Share = {sendScrap: function (o) { window.__kakao.push(['scrap', o.requestUrl]); }}; }};"""


def _serve(built):
    import mimetypes
    from urllib.parse import urlsplit

    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return serve


def test_the_send_box_copies_hands_kakaotalk_the_address_and_counts_in_ga4(world):
    """On a 360px phone: the box fits with tiles of 44px or more; 카카오톡 hands Kakao.Share.sendScrap the address
    tagged kakao after Kakao.init with the site's key; without the SDK the link is copied with its note; 링크 복사 and
    문자 count in GA4. On a 1440px screen the panel's '<지역>각 공유하기' opens the site's box in a dialog; Escape closes it."""
    sync_api = pytest.importorskip("playwright.sync_api")
    S, built = world
    e = _place_with_route(S, built)
    path = f"http://site.test{quote(e['_path'])}"
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            want = {"content_type": "place-food", "item_id": e["id"]}
            for stub in (True, False):
                ctx = browser.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True)
                ctx.add_init_script(SHARE_STUBS + (KAKAO_STUB if stub else ""))
                ctx.route("**/*", _serve(built))
                page = ctx.new_page()
                page.goto(f"{path}?share=none", wait_until="load")
                canon = page.get_attribute('link[rel="canonical"]', "href")
                box = page.locator("main [data-shr]").first
                box.scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth") <= 360
                tiles = box.locator(".shr-b:visible")
                assert tiles.all_inner_texts() == ["카카오톡", "링크 복사", "문자"]   # 더보기: no share sheet here
                for t in tiles.all():
                    bb = t.bounding_box()
                    assert bb["width"] >= 44 and bb["height"] >= 44 and bb["x"] + bb["width"] <= 360
                box.locator('[data-shr-do="kakao"]').click()
                page.wait_for_timeout(400)
                ev, cop = page.evaluate("window.__events"), page.evaluate("window.__copied")
                note = page.locator("body > .share-note")
                if stub:
                    assert page.evaluate("window.__kakao") == [["init", KEY],
                                                               ["scrap", f"{canon}?utm_source=share&utm_medium=kakao"]]
                    assert ev == [["share", {"method": "kakao", **want}]] and cop == []
                    box.locator('[data-shr-do="copy_link"]').click()
                    page.wait_for_timeout(300)
                    assert page.evaluate("window.__copied") == [f"{canon}?utm_source=share&utm_medium=copy_link"]
                    assert note.inner_text() == "링크를 복사했습니다"
                    box.locator('[data-shr-do="sms"]').evaluate("a => a.addEventListener('click', ev => ev.preventDefault())")
                    box.locator('[data-shr-do="sms"]').click()
                    assert page.evaluate("window.__events")[-2:] == [["share", {"method": "copy_link", **want}],
                                                                    ["share", {"method": "sms", **want}]]
                else:   # the SDK is blocked (only site.test answers): the link is copied and the note says why
                    assert cop == [f"{canon}?utm_source=share&utm_medium=copy_link"]
                    assert note.inner_text() == "카카오톡을 열지 못해 링크를 복사했습니다"
                    assert ev == [["share", {"method": "copy_link", **want}]]
                ctx.close()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(SHARE_STUBS)
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            page.goto(path, wait_until="load")
            pc = page.locator("main [data-shr]").first.locator(".shr-b:visible")
            assert [t.split("(")[0].strip() for t in pc.all_inner_texts()] == ["카카오톡", "링크 복사", "페이스북", "X", "밴드"]
            page.locator(".side [data-shr-open]").click()
            dlg = page.locator("dialog[data-shr-dlg]")
            assert dlg.evaluate("d => d.open")
            dlg.locator('[data-shr-do="copy_link"]').click()
            page.wait_for_timeout(300)
            home = S.site["site_url"].rstrip("/") + "/"
            assert page.evaluate("window.__copied") == [f"{home}?utm_source=share&utm_medium=copy_link"]
            assert dlg.locator(".share-note").inner_text() == "링크를 복사했습니다"
            page.keyboard.press("Escape")
            assert not dlg.evaluate("d => d.open")
            ctx.close()
        finally:
            browser.close()
