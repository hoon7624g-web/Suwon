"""군산각 파트너 (operator decision at the 2026-11-04 meeting; pipeline/partners.py, data/gunsan/partners.json): the
partner stay (스테이,머뭄) leads the 숙박 예약하기 page framed, with the diagonal ribbon, the badge and a '?' that names
the relationship (the operator's Web4AI), and its own homepage comes before the booking sites there and on its page;
/partners/ offers the stay and content partnerships with one inquiry mail; the panel, the phone menu and the footer link
it. The built pages: pipeline.validate (partners.data_problems, the relationship beside a direct link)."""
import re
from pathlib import Path

import pytest

from pipeline import affiliate, partners, present
from pipeline.build import State, make_env

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gunsan"
PID = "official-stay-meomum"


@pytest.fixture(scope="module")
def S():
    return State(DATA, "production")


def test_the_file_is_clean_and_says_the_relationship(S):
    assert partners.data_problems(S) == []
    reg = partners.registry(S)
    assert "Web4AI" in reg["explain"] and "에이아이오투오" in reg["explain"]
    assert partners.contact(S) and partners.mailto(S).startswith("mailto:" + partners.contact(S) + "?subject=")
    assert [o["key"] for o in partners.offers(S)] == ["stay", "content"]


def test_only_the_partner_stay_gets_a_partner_record(S):
    by = {e["id"]: e for e in S.entities}
    p = partners.partner_for(S, by[PID])
    assert p["direct"]["url"] == "https://co.webforai.kr/s/stay" and p["more"] == partners.PATH
    assert all(partners.partner_for(S, e) is None for e in S.entities if e["id"] != PID)


def test_the_partner_card_leads_with_its_own_homepage_first(S):
    V = present.stay_booking_vm(S)
    c = V["rows"][0]
    assert c["id"] == PID and c["partner"] and V["n_partners"] == 1
    html = make_env().from_string('{% import "_staybook.html.j2" as sb %}{{ sb.card(c, 0) }}').render(c=c)
    assert 'class="sb-c sb-pt"' in html and 'class="sb-rib"' in html and 'class="pt-why"' in html
    assert 'class="sb-ph sb-ph-pt"' in html                       # the stay's own photo (its homepage, 2026-11-04)
    banner = make_env().from_string('{% import "_staybook.html.j2" as sb %}{{ sb.banner(c) }}').render(c=c)
    # a low, wide strip that is one link to the stay's homepage (operator 2026-11-04: no buttons)
    assert 'class="pt-strip"' in banner and "Web4AI" in banner and banner.count("<a ") == 1
    assert f'href="{c["partner"]["direct"]["url"]}"' in banner and c["partner"]["photo_credit"] in banner
    direct, first_ota = html.index('data-track="direct_booking_click"'), html.index('data-track="affiliate_click"')
    assert direct < first_ota                       # Web4AI before the booking sites (탈플랫폼)
    assert 'rel="sponsored noopener"' in html and "Web4AI" in html
    other = make_env().from_string('{% import "_staybook.html.j2" as sb %}{{ sb.card(c, 1) }}').render(c=V["rows"][1])
    assert "sb-pt" not in other and "direct_booking_click" not in other


def test_the_stay_page_box_puts_the_direct_link_first(S):
    e = next(x for x in S.entities if x["id"] == PID)
    tpl = '{% import "_ui.html.j2" as ui %}{{ ui.aff(items, place, "", partner) }}'
    html = make_env().from_string(tpl).render(items=affiliate.links_for(S, e), place=PID, partner=partners.partner_for(S, e))
    assert html.index("direct_booking_click") < html.index("affiliate_click") and "aff-pt" in html
    plain = make_env().from_string(tpl).render(items=affiliate.links_for(S, e), place=PID, partner=None)
    assert "direct_booking_click" not in plain and "pt-why" not in plain


def test_the_partners_page_and_the_side_link(S, tmp_path):
    env = make_env()
    side = env.from_string('{% import "_side.html.j2" as sdm %}{{ sdm.partner(path, "/") }}').render(path=partners.PATH)
    assert f'href="{partners.PATH}"' in side and "문의/제휴" in side and 'data-track="partner_cta"' in side
    assert env.from_string('{% import "_side.html.j2" as sdm %}{{ sdm.partner("", "/") }}').render().strip() == ""


def test_the_badge_note_never_takes_the_card_s_clicks():
    """2026-11-04 fix: the '?' touch target (summary::after) is sized by the summary itself, never by the card."""
    css = (ROOT / "templates" / "assets" / "css" / "83-partners.css").read_text("utf-8")
    assert re.search(r"\.pt-why > summary \{ position: relative;", css)


# ------------------------------------------------------------------ 파트너 문의 페이지 (operator 2026-11-04)
def test_the_inquiry_buttons_lead_to_the_contact_page_that_writes_the_mail(tmp_path_factory):
    import re
    from pipeline import build as B, partners as PT
    S = B.State(ROOT / "data" / "gunsan", "production")
    env = B.make_env()
    html = env.get_template("partners_contact.html.j2").render(
        site=S.site, P={"contact": "sales@o2o.kr"}, page={"title": "t", "description": "d", "canonical": "c", "crumbs": [],
                                                       "jsonld": []}, common={})
    assert 'action="mailto:sales@o2o.kr"' in html and 'data-pc-form' in html and 'data-to="sales@o2o.kr"' in html
    assert 'name="name" required' in html and "저장되지 않습니다" in html
    assert PT.CONTACT_PATH == "/partners/contact/"
    page = (ROOT / "templates" / "partners.html.j2").read_text("utf-8")
    assert page.count("P.contact_path") >= 2 and "P.mailto }}\" data-track=\"partner_contact\">파트너 문의" not in page
