"""군산각 파트너 (operator decision at the 2026-11-04 meeting): a partner stay — 스테이,머뭄 first — stands at the top of
the 숙박 예약하기 page with a premium frame, a diagonal '파트너' ribbon and a '?' that says why (a Web4AI stay that takes
its own bookings), and its own homepage's direct booking comes before the booking sites; the /partners/ page offers the
stay and content partnerships, and every page's side panel, phone menu and footer link it ('문의/제휴').

data/<region>/partners.json (build.State.partners):
- contact: the address partner inquiries are mailed to (empty: site.json operator.email);
- badge, explain: the ribbon's word and the '?' text (the stay is a client of the site's operator: said there);
- stays: {place id: {direct {url, label, note, checked_at}, since}} — only these get the frame, the top and the direct
  link (a stay of the data that is built);
- offers: {stay | content: {title, lead, benefits [{t, d}], terms?}} for /partners/.
Templates: _staybook.html.j2 (the card), _ui.html.j2 aff() (the stay page's booking box), partners.html.j2,
_side.html.j2 / base.html.j2 (the '문의/제휴' link). data_problems checks the file.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlsplit

from .textutil import link_url, squash_ws

PATH = "/partners/"
CONTACT_PATH = "/partners/contact/"   # the inquiry form (operator 2026-11-04: a page of its own, mail to sales)
TRACK_DIRECT = "direct_booking_click"   # a partner stay's own homepage (GA4, track.js)
TRACK_CONTACT = "partner_contact"       # the inquiry mail link


def registry(S) -> dict:
    return getattr(S, "partners", None) or {}


def contact(S) -> str:
    """The inquiry address: partners.json contact, else the operator's public email."""
    reg = registry(S)
    return squash_ws(reg.get("contact")) or squash_ws(((getattr(S, "site", None) or {}).get("operator") or {}).get("email"))


def mailto(S, subject: str = "[군산각 파트너 문의]") -> str:
    """mailto: the inquiry address with a subject and a short body to fill in ('' without an address)."""
    to = contact(S)
    if not to:
        return ""
    body = "숙소·채널 이름:\n연락처:\n문의 내용:\n"
    return f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"


def partner_for(S, e: dict | None) -> dict | None:
    """A built stay's partner record for the page: {badge, explain, direct {url, label, note}, more (PATH)}, else None."""
    reg = registry(S)
    rec = (reg.get("stays") or {}).get((e or {}).get("id") or "")
    if not rec or not e or e.get("kind") != "stay":
        return None
    d = rec.get("direct") or {}
    url = link_url(d.get("url"))
    return {"badge": squash_ws(reg.get("badge")) or "파트너", "explain": squash_ws(reg.get("explain")),
            "direct": {"url": url, "label": squash_ws(d.get("label")) or "공식 홈페이지",
                       "note": squash_ws(d.get("note")), "host": (urlsplit(url).hostname or "")} if url else None,
            "more": PATH, "id": e.get("id"), "name": e.get("name"), "path": e.get("_path", ""),
            # the stay's own photos (its homepage, operator 2026-11-04) and the Web4AI homepage screens
            "photos": [ph for ph in rec.get("photos") or [] if ph.get("src") and ph.get("alt")],
            "photo_credit": squash_ws(rec.get("photo_credit")), "screens": rec.get("screens") or {},
            "headline": squash_ws(rec.get("headline")) or e.get("name")}


def offers(S) -> list[dict]:
    """The /partners/ offers in their order: [{key, title, lead, benefits [{t, d}], terms}]."""
    out = []
    for key, o in (registry(S).get("offers") or {}).items():
        out.append({"key": key, "title": squash_ws(o.get("title")), "lead": squash_ws(o.get("lead")),
                    "benefits": [{"t": squash_ws(b.get("t")), "d": squash_ws(b.get("d"))} for b in o.get("benefits") or []],
                    "terms": squash_ws(o.get("terms"))})
    return out


def data_problems(S) -> list[str]:
    """partners.json itself (pipeline.validate): a badge and its explanation saying who runs the stay's homepage; every
    partner stay is a built stay with a direct address and the day it was checked; every offer has a title and
    benefits; an inquiry address exists (contact or operator.email)."""
    reg = registry(S)
    if not reg:
        return []
    out = []
    if not squash_ws(reg.get("badge")):
        out.append("badge 없음")
    if "에이아이오투오" not in (reg.get("explain") or "") and "Web4AI" not in (reg.get("explain") or ""):
        out.append("explain에 파트너 관계(Web4AI·운영사)가 없음 — 표시·광고 기준")
    built = {e.get("id"): e for e in getattr(S, "entities", None) or []}
    for pid, rec in (reg.get("stays") or {}).items():
        e = built.get(pid)
        if not e:
            out.append(f"stays.{pid}: 빌드되는 장소가 아님")
        elif e.get("kind") != "stay":
            out.append(f"stays.{pid}: 숙소가 아님")
        d = rec.get("direct") or {}
        if not link_url(d.get("url")):
            out.append(f"stays.{pid}: direct.url 없음")
        if not squash_ws(d.get("checked_at")):
            out.append(f"stays.{pid}: direct.checked_at 없음")
        if rec.get("photos") and not squash_ws(rec.get("photo_credit")):
            out.append(f"stays.{pid}: photos가 있는데 photo_credit 없음")
        root = Path(__file__).resolve().parent.parent / "templates"
        for ph in rec.get("photos") or []:
            for k in ("src", "thumb"):
                if ph.get(k) and not (root / ph[k].lstrip("/")).is_file():
                    out.append(f"stays.{pid}: 사진 파일이 templates{ph[k]}에 없음")
            if not squash_ws(ph.get("alt")):
                out.append(f"stays.{pid}: 사진 alt 없음 {ph.get('src')}")
    for key, o in (reg.get("offers") or {}).items():
        if not squash_ws(o.get("title")) or not o.get("benefits"):
            out.append(f"offers.{key}: title·benefits 없음")
    if not contact(S):
        out.append("문의 주소 없음(contact, site.json operator.email)")
    return out
