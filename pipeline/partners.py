"""파트너 되기 (the first site's 7f2afaad7 · 3ee5bff35 · cf8e7c077, operator decision at the 2026-11-04 meeting; this
city: operator 2026-11-05 — the first site alone has partner stays, so here the recruiting page, its inquiry page and
the '문의/제휴' links only).
/partners/ offers the stay and content partnerships; /partners/contact/ writes the inquiry mail in the visitor's mail
app (site.js [data-pc-form]); every Korean page's side panel, phone menu and footer link /partners/ ('문의/제휴').
No partner stay is listed or framed on this site (the first site's partner card, badge and direct booking link are
not part of this engine).

data/<region>/partners.json (build.State.partners; no file, no page and no link):
- contact: the address partner inquiries are mailed to (empty: site.json operator.email);
- lede: the page's lead sentence (this city's words; the template never names a city);
- offers: {stay | content: {title, lead, benefits [{t, d, pic?, icon?}]}} for /partners/ — what is offered, in the
  operator's words (pic: a 3D picture id of data/<region>/icons.json, icon: its glyph until the file is there);
- note: the page's last line (who runs the site; visit facts stay from the sources whatever the partnership).
Templates: partners.html.j2, partners_contact.html.j2, _side.html.j2 partner(), base.html.j2 (footer).
data_problems checks the file (pipeline.validate).
"""
from __future__ import annotations

from urllib.parse import quote

from .textutil import squash_ws

PATH = "/partners/"
CONTACT_PATH = "/partners/contact/"   # the inquiry form (the first site's operator 2026-11-04: a page of its own)
TRACK_CTA = "partner_cta"             # a press toward /partners/ (the panel's '문의/제휴', the footer, the page's buttons)
TRACK_CONTACT = "partner_contact"     # the inquiry mail link and the form's send button


def registry(S) -> dict:
    return getattr(S, "partners", None) or {}


def contact(S) -> str:
    """The inquiry address: partners.json contact, else the operator's public email."""
    reg = registry(S)
    return squash_ws(reg.get("contact")) or squash_ws(((getattr(S, "site", None) or {}).get("operator") or {}).get("email"))


def mailto(S) -> str:
    """mailto: the inquiry address with a subject ('[<site> 파트너 문의]') and a short body to fill in ('' without an
    address)."""
    to = contact(S)
    if not to:
        return ""
    name = squash_ws((getattr(S, "site", None) or {}).get("site_name"))
    body = "숙소·채널 이름:\n연락처:\n문의 내용:\n"
    return f"mailto:{to}?subject={quote(f'[{name} 파트너 문의]')}&body={quote(body)}"


def offers(S) -> list[dict]:
    """The /partners/ offers in their order: [{key, title, lead, benefits [{t, d, pic, icon}]}]."""
    out = []
    for key, o in (registry(S).get("offers") or {}).items():
        out.append({"key": key, "title": squash_ws(o.get("title")), "lead": squash_ws(o.get("lead")),
                    "benefits": [{"t": squash_ws(b.get("t")), "d": squash_ws(b.get("d")), "pic": squash_ws(b.get("pic")),
                                  "icon": squash_ws(b.get("icon")) or "spark"} for b in o.get("benefits") or []]})
    return out


def page_vm(S) -> dict:
    """What partners.html.j2 and partners_contact.html.j2 print."""
    reg = registry(S)
    to = contact(S)
    return {"offers": offers(S), "mailto": mailto(S), "contact": to, "contact_path": CONTACT_PATH if to else "",
            "lede": squash_ws(reg.get("lede")), "note": squash_ws(reg.get("note"))}


def data_problems(S) -> list[str]:
    """partners.json itself (pipeline.validate): a lead sentence, every offer with a title and benefits (each with its
    words), an inquiry address (contact or operator.email); no partner stay (this engine lists none)."""
    reg = registry(S)
    if not reg:
        return []
    out = []
    if not squash_ws(reg.get("lede")):
        out.append("lede 없음")
    for key, o in (reg.get("offers") or {}).items():
        if not squash_ws(o.get("title")) or not o.get("benefits"):
            out.append(f"offers.{key}: title·benefits 없음")
        for i, b in enumerate(o.get("benefits") or []):
            if not squash_ws(b.get("t")) or not squash_ws(b.get("d")):
                out.append(f"offers.{key}.benefits[{i}]: t·d 없음")
    if not reg.get("offers"):
        out.append("offers 없음")
    if reg.get("stays"):
        out.append("stays: 이 엔진은 파트너 숙소를 싣지 않음(운영자 2026-11-05 — 파트너 숙소는 첫 사이트에만 있음)")
    if not contact(S):
        out.append("문의 주소 없음(contact, site.json operator.email)")
    return out
