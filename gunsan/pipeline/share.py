"""공유하기 — 보내기 (operator 2026-10-17: the local bar's 공유; 2026-11-11, after 안성민's note '공유하기 버튼을 크게 …
웹브라우저에서 공유하기를 쉽게 하지만 못 하는 사람들이 많으니까': the recommended placement, approved with '카카오 공유
가능하고 … 사진 내용 모두 진행하자').

- ui.lnav's 공유 (place, guide, course, column, event) is a pill with its word on phones too, and the list pages carry
  the same pill beside their title (ui.sharebtn): the phone's share sheet, else the link copied.
- The 보내기 box (templates/_share.html.j2 box(), view()): tiles with a picture and a word each — phones: 카카오톡 ·
  링크 복사 · 문자 · 더보기 (the phone's share sheet, when the browser has one); from 1024px: 카카오톡 · 링크 복사 ·
  페이스북 · X · 밴드 and a QR code that opens the page on a phone. A place page has it under its route row (and
  its booking rows), a guide, course or column before 이어서 보기, an event under its 일정·장소; the home ('군산각
  알리기') before 제휴·관련 사이트, and the panel's / phone menu's '군산각 공유하기' opens it for the site in a dialog.
- 카카오톡: the Kakao JavaScript SDK (SDK, SDK_SRI — fetched only when a pointer reaches the tile, the tile takes the
  focus or the site's dialog opens: never on a page view) with site.json kakao_js_key (the maps' key: Kakao accepts it only from the domain registered
  for it), Kakao.Share.sendScrap of the page's address — the preview is the page's own og:title / og:image.
- Every shared address is the page's canonical one + utm_source=share&utm_medium=<method> (tagged), so the visits it
  brings count apart in GA4; site.js sends GA4 'share' {method, content_type, item_id} (track.js).
Nothing is sent anywhere before a reader presses a tile: 페이스북 · X · 밴드 · 문자 are plain links (no SDK, no
counter), the QR code is drawn at build time (segno).
"""
from __future__ import annotations

import functools
import io
from pathlib import Path
from urllib.parse import quote, urlsplit

import segno

# Kakao SDK for JavaScript (https://t1.kakaocdn.net/kakao_js_sdk/<v>/kakao.min.js, released 2026-10-19), checked
# against its integrity hash; the CDN answers with Access-Control-Allow-Origin: * (crossorigin="anonymous")
SDK = "https://t1.kakaocdn.net/kakao_js_sdk/2.8.4/kakao.min.js"
SDK_SRI = "sha384-BGX7Wb16GmRFagri4bLJV2DgipVZaU2AI812GZtHtHzzDQJnfHasDXN5houxv45w"

# the logo card (operator 2026-11-11, '2번은 니 권장안대로'): the link preview of a place page without a Type1 photo —
# previews crop (a Type3 photo may not be), and an illustration may not stand for a place (CLAUDE.md 4). The logo
# and the address on the site's pale blue, 1200×630, drawn from templates/assets/brand/gunsangak-logo.svg.
CARD = "/assets/brand/og-card.png"
CARD_FILE = Path(__file__).resolve().parent.parent / "templates" / "assets" / "brand" / "og-card.png"


def card(site_name: str | None, lang: str = "ko") -> dict | None:
    """The logo card as a page image ({src, alt, w, h}), or None when the file is not there."""
    if not CARD_FILE.is_file():
        return None
    name = (site_name or "").strip()
    return {"src": CARD, "alt": f"{name} 로고" if lang == "ko" else name, "w": 1200, "h": 630}


# the methods a share is counted by (utm_medium and GA4 share.method): the ones site.js sends itself and the links'
METHODS = ("kakao", "copy_link", "web_share", "sms", "facebook", "x", "band", "qr")


def tagged(url: str, method: str) -> str:
    """The address to share: the page's own + utm_source=share&utm_medium=<method> (site.js does the same)."""
    return url + ("&" if "?" in url else "?") + "utm_source=share&utm_medium=" + method


@functools.lru_cache(maxsize=None)
def qr_svg(url: str) -> str:
    """The QR code of an address as one inline <svg> (a single path, dark on the page's white); the caption beside it
    says what it does, so the picture itself is hidden from screen readers."""
    buf = io.BytesIO()
    segno.make(url, error="m", micro=False).save(
        buf, kind="svg", xmldecl=False, svgns=False, nl=False, omitsize=True, border=2, dark="#111",
        svgclass="shr-qr-i", lineclass=None)
    return buf.getvalue().decode("ascii").replace("<svg ", '<svg aria-hidden="true" focusable="false" ', 1)


def view(url: str, title: str, item_id: str = "") -> dict:
    """What a 보내기 box needs for one address: the links of the plain tiles (each already tagged), the QR code and
    the words the JavaScript tiles send (data-shr-*)."""
    host = urlsplit(url).netloc
    text = title.strip()
    return {
        "url": url, "title": text, "id": item_id,
        "sms": "sms:?&body=" + quote(f"{text}\n{tagged(url, 'sms')}", safe=""),
        "facebook": "https://www.facebook.com/sharer/sharer.php?u=" + quote(tagged(url, "facebook"), safe=""),
        "x": "https://x.com/intent/tweet?text=" + quote(text, safe="") + "&url=" + quote(tagged(url, "x"), safe=""),
        "band": ("https://band.us/plugin/share?body=" + quote(f"{text}\n{tagged(url, 'band')}", safe="")
                 + "&route=" + quote(host, safe="")),
        "qr": qr_svg(tagged(url, "qr")),
    }
