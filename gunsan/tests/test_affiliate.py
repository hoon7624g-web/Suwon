"""제휴 예약 링크 (operator decision at the 2026-11-03 meeting: '군산각에 있는 숙소는 제휴 링크 연결, 링크가 있는 예약사는
모두 노출'; pipeline/affiliate.py, data/gunsan/affiliate.json, templates/_ui.html.j2 aff()).

A published stay's Korean page shows every booking site the data has a link for, in the providers' order, through the
affiliate network only, marked as affiliate links (heading tag + one line) with rel="sponsored nofollow"; a held stay
(the client's stay) and every other page show none; the file's links are the network's, each once, for stays of the
data, and record the provider's page they opened. The built pages: pipeline.validate affiliate_problems (every
production build)."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import affiliate, present
from pipeline.build import State, make_env
from pipeline.validate import PageScan, affiliate_problems

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gunsan"
REG = json.loads((DATA / "affiliate.json").read_text("utf-8"))
# the booking sites whose buttons show: a provider with a hold keeps its links in the file and shows none
# (operator 2026-11-11: 야놀자 — its links end on 야놀자's home, not on the stay)
SHOWN = [k for k, v in REG["providers"].items() if not v.get("hold")]
CHECKED = re.compile(r"\d{4}-\d{2}-\d{2}")


@pytest.fixture(scope="module")
def S():
    return State(DATA, "production")


def _scan(html: str) -> PageScan:
    p = PageScan()
    p.feed(html)
    return p


def _render(items, place="p1", more="") -> str:
    return make_env().from_string('{% import "_ui.html.j2" as ui %}{{ ui.aff(items, place, more) }}').render(
        items=items, place=place, more=more)


def _cards(rows) -> str:
    return make_env().from_string('{% import "_staybook.html.j2" as sb %}<p>제휴 링크</p><ul>{% for c in rows %}'
                                  '{{ sb.card(c, loop.index0) }}{% endfor %}</ul>').render(rows=rows)


# ------------------------------------------------------------------ the file
def test_the_file_is_clean_and_every_link_is_the_network_s(S):
    assert affiliate.data_problems(S) == []
    net = REG["network"]
    assert net["host"] == "3ha.in" and CHECKED.fullmatch(net["checked_at"])
    assert list(REG["providers"]) == ["agoda", "yeogi", "trip", "myrealtrip", "yanolja", "hotelscombined", "booking",
                                     "hotels", "expedia"]
    urls = [ln["url"] for rec in REG["places"].values() for ln in rec["links"].values()]
    assert len(urls) == len(set(urls)) and all(u.startswith("https://3ha.in/r/") for u in urls)
    stays = {e["id"]: e for e in S.entities_all if e["kind"] == "stay"}
    for pid, rec in REG["places"].items():
        assert pid in stays and rec["name"] == stays[pid]["name"], pid
        for key, ln in rec["links"].items():
            assert affiliate.on_host(ln["to"], REG["providers"][key]["host"]), (pid, key, ln["to"])
            # the page it opened, without the network's tracking values (Agoda: its property number only)
            assert "?" not in ln["to"] or (key == "agoda" and re.fullmatch(r".*\?hid=\d+", ln["to"])), (pid, key)


def test_data_problems_catch_each_wrong_entry(S):
    reg = json.loads(json.dumps(REG))
    a, b = list(reg["places"])[:2]
    first = next(iter(reg["places"][a]["links"]))
    reg["places"][a]["links"][first]["url"] = "https://www.yeogi.com/x"           # not the network
    reg["places"][b]["links"]["nope"] = {"url": "https://3ha.in/r/1", "to": "https://x.example/"}
    reg["places"]["no-such-place"] = {"name": "x", "links": {}}
    reg["hold"]["gunsan-307026"] = " "
    reg["providers"]["agoda"]["hold"] = ""
    got = affiliate.data_problems(SimpleNamespace(affiliate=reg, entities_all=S.entities_all))
    assert any("providers.agoda.hold: 이유 없음" in g for g in got)
    assert any(f"places.{a}.{first}: 제휴 네트워크" in g for g in got)
    assert any(f"places.{b}: 없는 예약사 nope" in g for g in got)
    assert any("no-such-place: places.json에 없는 장소" in g for g in got)
    assert any("hold.gunsan-307026: 이유 없음" in g for g in got)


# ------------------------------------------------------------------ which page shows which links
def test_every_listed_published_stay_shows_all_its_links_in_the_providers_order(S):
    by_id = {e["id"]: e for e in S.entities}
    shown = 0
    for pid, rec in REG["places"].items():
        got = affiliate.links_for(S, by_id.get(pid))
        if pid in REG["hold"]:
            assert got == [], pid
            continue
        want = [k for k in SHOWN if k in rec["links"]]
        assert [x["key"] for x in got] == want, pid
        assert [x["url"] for x in got] == [rec["links"][k]["url"] for k in want], pid
        assert [x["name"] for x in got] == [REG["providers"][k]["name"] for k in want], pid
        shown += 1
    assert shown >= 30
    # the big hotels carry every site the network has (라마다·베스트웨스턴: all nine in the file; those shown)
    assert len(REG["places"]["gunsan-307082"]["links"]) == 9
    assert len(affiliate.links_for(S, by_id["gunsan-307082"])) == len(SHOWN)


def test_a_held_booking_site_shows_no_button_and_keeps_its_links(S):
    """Operator 2026-11-11 ('야놀자 버튼은 일단 숨겨줘'): the network's 야놀자 links end on 야놀자's home — through
    링크프라이스 the stay is passed only as an app address (yanolja.onelink.me, yanoljamotel://…), so a computer and a
    phone without the app land on nol.yanolja.com. The site's buttons are held (providers.yanolja.hold, with the
    reason); the links stay in the file, and without the hold they show again."""
    assert REG["providers"]["yanolja"]["hold"].strip() and "yanolja" not in SHOWN
    held_links = {rec["links"]["yanolja"]["url"] for rec in REG["places"].values() if "yanolja" in rec["links"]}
    assert len(held_links) == 20 and held_links <= affiliate.all_urls(S)          # kept in the data
    for e in S.entities:
        assert not any(x["key"] == "yanolja" or x["url"] in held_links for x in affiliate.links_for(S, e)), e["id"]
    # a stay whose only link is the held site's shows no block and is not on 숙박 예약하기
    only = [pid for pid, rec in REG["places"].items() if set(rec["links"]) == {"yanolja"}]
    by_id = {e["id"]: e for e in S.entities}
    assert only and all(affiliate.links_for(S, by_id[pid]) == [] for pid in only if pid in by_id)
    assert not {e["id"] for e in affiliate.stays(S)} & set(only)
    # the hold taken away: the links are back, in the providers' order
    free = json.loads(json.dumps(REG))
    del free["providers"]["yanolja"]["hold"]
    got = affiliate.links_for(SimpleNamespace(affiliate=free), by_id["gunsan-307082"])
    assert [x["key"] for x in got] == list(REG["providers"]) and len(got) == 9


def test_the_client_stay_shows_its_links_and_other_places_none(S):
    by_id = {e["id"]: e for e in S.entities_all}
    # the client's stay: shown since the operator's decision of 2026-11-04 (official booking buttons still excluded)
    meomum = [k for k in SHOWN if k in REG["places"]["official-stay-meomum"]["links"]]
    assert "official-stay-meomum" not in REG["hold"] and len(REG["places"]["official-stay-meomum"]["links"]) == 3
    assert [x["key"] for x in affiliate.links_for(S, by_id["official-stay-meomum"])] == meomum and meomum
    held = {**REG, "hold": {"official-stay-meomum": "test"}}
    assert affiliate.links_for(SimpleNamespace(affiliate=held), by_id["official-stay-meomum"]) == []
    # the duplicate '파라다이스' (operator 2026-11-04) has no page and no links; '파라다이스 호텔' keeps its own
    assert "gunsan-306798" not in REG["places"] and by_id["gunsan-306798"].get("duplicate_of") == "gunsan-307070"
    others = [e for e in S.entities if e["id"] not in REG["places"]]
    assert others and all(affiliate.links_for(S, e) == [] for e in others)
    stay = dict(by_id["gunsan-307082"], status="draft")
    assert affiliate.links_for(S, stay) == []          # only a published stay


# ------------------------------------------------------------------ the markup
def test_the_block_marks_the_links_as_affiliate_and_sponsored(S):
    items = affiliate.links_for(S, next(e for e in S.entities if e["id"] == "gunsan-307009"))
    html = _render(items, "gunsan-307009")
    assert 'data-block="affiliate"' in html and "제휴 링크" in html and "수수료" in html and f"{len(SHOWN)}곳" in html
    links = re.findall(r"<a [^>]*>", html)
    assert len(links) == len(items) == len(SHOWN)
    for a, it in zip(links, items):
        assert f'href="{it["url"]}"' in a and 'rel="sponsored nofollow noopener"' in a
        assert 'data-track="affiliate_click"' in a and f'data-provider="{it["key"]}"' in a
        assert 'data-place="gunsan-307009"' in a
    assert not CHECKED.search(html)                     # no date on the page (operator 2026-10-09)
    assert _render([]).strip() == ""


def test_affiliate_problems_catch_each_wrong_page(S):
    e = next(x for x in S.entities if x["id"] == "gunsan-307082")
    items = affiliate.links_for(S, e)
    good = _render(items, e["id"])
    assert affiliate_problems(S, _scan(good), items) == []
    # another page (a list, the home, a language version) shows none
    assert affiliate_problems(S, _scan(good), None)
    assert affiliate_problems(S, _scan('<a href="https://3ha.in/r/855469">x</a>'), None)
    # missing a site, a link outside the block, without rel sponsored
    assert affiliate_problems(S, _scan(_render(items[:-1], e["id"])), items)
    loose = good + f'<a href="{items[0]["url"]}" data-track="affiliate_click" data-provider="yeogi" rel="sponsored nofollow">x</a>'
    assert any("밖에 있음" in p for p in affiliate_problems(S, _scan(loose), items))
    bare = good.replace('rel="sponsored nofollow noopener"', 'rel="noopener"')
    assert any("sponsored" in p for p in affiliate_problems(S, _scan(bare), items))
    untracked = good + f'<p><a href="{items[1]["url"]}x">x</a></p>'
    assert any("affiliate_click 없이" in p for p in affiliate_problems(S, _scan(untracked), items))


def test_the_stay_page_links_the_booking_page_once():
    html = _render([{"key": "yeogi", "name": "여기어때", "url": "https://3ha.in/r/1"}], "p1", affiliate.STAYS_PATH)
    assert html.count(f'href="{affiliate.STAYS_PATH}"') == 1 and 'data-track="stay_booking_cta"' in html


# ------------------------------------------------------------------ 숙박 예약하기 (/stays/booking/)
def test_the_booking_page_holds_every_shown_stay_photos_first(S):
    V = present.stay_booking_vm(S)
    rows = V["rows"]
    assert {c["id"] for c in rows} == {pid for pid, rec in REG["places"].items()
                                       if pid not in REG["hold"] and set(rec["links"]) & set(SHOWN)}
    assert all(c["aff"] == affiliate.links_for(S, c["e"]) for c in rows)
    lead = [c["partner"] is not None for c in rows]
    assert lead == sorted(lead, reverse=True)              # partner stays lead (operator 2026-11-04, tests/test_partners.py)
    photo = [c["photo"] is not None for c in rows if not c["partner"]]
    assert photo == sorted(photo, reverse=True)            # then the stays with a photo
    assert all(c["photo"]["type"] in (1, 3) for c in rows if c["photo"])
    assert V["n_links"] == sum(len(c["aff"]) for c in rows) and V["n_sites"] == len(SHOWN)
    assert sum(g["n"] for g in V["groups"]) == len(rows)
    for c in rows:   # a fact the card shows is this site's own value; a slot it lacks is said once
        assert not set(f["key"] for f in c["facts"]) & set(c["need"])


def test_the_booking_cards_keep_the_photo_rules_and_mark_the_links(S):
    V = present.stay_booking_vm(S)
    html = _cards(V["rows"])
    assert html.count('data-block="affiliate"') == len(V["rows"])
    assert html.count('data-track="affiliate_click"') == V["n_links"]
    assert html.count('rel="sponsored nofollow noopener"') == V["n_links"]
    assert html.count('class="sb-ph t3"') == sum(1 for c in V["rows"] if c["photo"] and c["photo"]["type"] == 3)
    # no empty cover: a stay without a photo shows the kind icon (a partner stay its own homepage photo, 2026-11-04)
    assert html.count('class="type-ico"') == sum(1 for c in V["rows"] if not c["photo"] and not (c["partner"] and c["partner"]["photos"]))
    assert not CHECKED.search(re.sub(r"<[^>]+>", " ", html))
    scan = _scan(html)
    want = [a for c in V["rows"] for a in c["aff"]]
    assert affiliate_problems(S, scan, want) == []
    assert affiliate_problems(S, _scan(html.replace("제휴 링크", "")), want)   # the disclosure must be on screen


def test_the_booking_page_head_is_the_title_and_the_disclosure_stands_over_the_cards():
    """Operator 2026-11-11 ('위 사진 내용도 빼' — the head's two big numbers and its labelled notice): the head is the
    kicker, the title and one sentence. That the buttons are affiliate links and the site may be paid is still said —
    a reader must be told, and affiliate_problems requires '제휴 링크' on a page with such links — in one line right
    over the cards, before any booking-site link; the partner relation is said with the order under the grid."""
    src = (ROOT / "templates" / "stay_booking.html.j2").read_text("utf-8")
    body = src[src.index("{% block content %}"):]
    head = body[:body.index("</section>")]
    assert "sb-stats" not in src and "sb-disc" not in src and "제휴 링크" not in head and "수수료" not in head
    line = body.index('<p class="sb-aff">')
    assert "제휴 링크" in body[line:line + 200] and "수수료" in body[line:line + 200]
    assert line < body.index('<ul class="sb-grid">')                        # before the cards' links
    assert "Web4AI 고객 숙소" in body[body.index('class="note sb-note"'):]   # the partner relation, with the order
    css = (ROOT / "templates" / "assets" / "css" / "82-stay-booking.css").read_text("utf-8")
    assert ".sb-stats" not in css and ".sb-disc" not in css and ".sb-aff {" in css
