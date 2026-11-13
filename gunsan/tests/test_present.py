"""pipeline/present.py (redesign view models), textutil.display_value and the validator's row check, on the real
Gunsan data: 빈해원's TourAPI hours, 근대역사박물관's fee table, '가능요금 (무료)', 0507 phone numbers, the meal
stops of the 2박 3일 course and menu search."""
import copy
import json
import os
import re
import shutil
import struct
import subprocess
from html import unescape
from pathlib import Path
from urllib.parse import quote

import pytest

from pipeline import jsonld, present
from pipeline.build import State, build, entity_ctx
from pipeline.schema import fact_label, parking_seats_half, parking_seats_part
from pipeline.textutil import dash_times, display_value, value_shown, value_tokens
from pipeline.validate import PageScan, fact_shown, seat_only_parking_problems, validate
from conftest import weather_answer, without_one_value_prose
from tools.image_sizes import image_size


@pytest.fixture(scope="module", autouse=True)
def _engine_both_values(engine_both_values):
    """This module checks the engine's both-values display on 군산각's data (tests/conftest.py)."""

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gunsan"


@pytest.fixture(scope="module")
def S():
    return State(DATA, "preview")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("present") / "preview"
    build(DATA, out, "preview")
    return out


def place(S, slug):
    return S.ent_by_slug[slug]


def all_values(S):
    """(entity, key, value) for every stored fact and every other source's value."""
    for e in S.entities:
        for k, v in (e.get("facts") or {}).items():
            yield e, k, v
        for k, alts in (e.get("fact_alternatives") or {}).items():
            for a in alts or []:
                if a.get("value"):
                    yield e, k, a["value"]


# ------------------------------------------------------------------ display_value
def test_display_value_normalises_presentation_only():
    assert display_value("parking", "가능요금 (무료)") == "가능, 요금 무료"
    assert display_value("parking", "가능\n요금 (무료)") == "가능, 요금 무료"
    assert display_value("parking", "주차장이 구비") == "가능"
    assert display_value("parking", "주차가능") == "가능"
    assert display_value("parking", "불가능") == "불가"
    assert display_value("usetime", "10:00 ~ 21:00,  휴무일 : 매주 월요일") == "10:00–21:00, 휴무일 : 매주 월요일"
    assert display_value("usetime", "[하절기]09:00~18:00[동절기] 09:00~17:00 ※ 매표마감 17:00") == \
        "[하절기]\n09:00–18:00\n[동절기]\n09:00–17:00\n※ 매표마감 17:00"
    assert display_value("homepage", "http://www.gunsandal.kr/") == "gunsandal.kr"
    assert display_value("homepage", "https://www.instagram.com/some.place/") == "instagram.com/some.place"
    assert display_value("course_name", "A코스 | 근대~고군산") == "A코스 근대~고군산"
    assert display_value("address", "전라북도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"


def test_display_value_never_drops_or_changes_a_word(S):
    """Except the time-range dash, every word of every stored value survives display_value unchanged."""
    checked = 0
    for e, k, v in all_values(S):
        if k in ("parking", "homepage", "reservationurl", "address"):
            continue
        assert value_tokens(display_value(k, v)) == value_tokens(dash_times(str(v))), (e["name"], k, v)
        checked += 1
    assert checked > 1500


def test_every_parsed_form_prints_the_display_words_in_order(S):
    """A timetable, price table or fee grid keeps every source word in source order, so a template printing the
    view model passes the validator's row check (value_shown) against display_value."""
    parsed = {"tt": 0, "fees": 0, "grid": 0}
    for e, k, v in all_values(S):
        view = present.value_view(k, v)
        for form in ("tt", "fees", "grid"):
            if view[form]:
                parsed[form] += 1
                assert value_shown(display_value(k, v), present.linear_text(view)), (e["name"], k, v)
    # the flattened two-column grid was 진포해양공원's 군산시 table, shown until TourAPI gave the same fee as rows
    # (2026-11-05; the 군산시 text stays its source note): the grid form is checked on that text
    grid = ("개인 단체(20인 이상) 성인 (군산시민) 1,000 (500) 700 (300) 청소년,군인 (군산시민) 700 (300) 400 (200) "
            "어린이 (군산시민) 300 (200) 200 (100)")
    view = present.value_view("usefee", grid)
    assert view["grid"] and value_shown(display_value("usefee", grid), present.linear_text(view))
    assert parsed["tt"] >= 40 and parsed["fees"] >= 5, parsed


# ------------------------------------------------------------------ 빈해원: TourAPI hours vs 군산시
def test_binhaewon_hours_conflict_shows_both_sources_flag_first(S):
    e = place(S, "빈해원")
    notes = present.Notes()
    tel = present.first_phone(e["facts"].get("infocenter"))
    row = present.fact_rows(e, ["usetime_restdate"], notes, tel)[0]
    assert row["conflict"] and row["flag"] == "영업시간만 다름"        # both sources: 매주 월요일
    assert row["flag_text"] == "영업시간만 다름 · 방문 전 전화 확인"
    assert [b["provider"] for b in row["blocks"]] == ["군산시", "한국관광공사"]
    assert row["tel"] == ("063-445-2429", "0634452429")
    tour = row["blocks"][1]["tt"]
    assert [r["group"] for r in tour["rows"] if r["kind"] == "time"][:3] == ["평일", "평일", "평일"]
    assert any(r["group"] == "평일" and r["label"] == "준비시간" and r["value"] == "15:00–16:30" for r in tour["rows"])
    assert any(r["group"] == "주말" and r["label"] == "준비시간" and r["value"] == "17:00–18:00" for r in tour["rows"])
    assert tour["rows"][-1] == {"group": "", "label": "", "kind": "closed", "closed": True, "value": "매주 월요일", "note": ""}
    status = present.status_items(e, full=True)
    texts = [x["text"] for x in status]
    assert "매주 월요일 휴무" in texts and "영업시간 출처마다 다름" in texts
    flag = next(x for x in status if x["text"] == "영업시간 출처마다 다름")
    assert flag["href"] == "#h-facts" and flag["cls"] == "st-flag"
    # no 확인일 item at the end of the line any more (operator decision 2026-10-09: check dates stay in the data)
    assert all(x["key"] != "date" for x in status) and not any("2026-10-08" in x["text"] for x in status)


# ------------------------------------------------------------------ 근대역사박물관: fees and seasons
def test_stroller_rental_from_the_homepage_and_tourapi_none_show_two_blocks():
    """QA 2026-10-15 F02: a facility homepage says strollers can be borrowed, TourAPI says 없음 — both shown, the
    homepage's block first, with the flag and the call line; neither value is picked."""
    e = {"id": "x", "name": "박물관", "kind": "attraction",
         "facts": {"babycarriage": "대여 가능(예약 없이 박물관 안내소에서)", "infocenter": "063-454-7870"},
         "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"},
         "fact_sources": {"babycarriage": {"provider": "군산근대역사박물관 홈페이지", "checked_at": "2026-10-15",
                                           "url": "https://museum.example/qna/2166"}},
         "fact_alternatives": {"babycarriage": [{"value": "없음", "provider": "한국관광공사 TourAPI",
                                                 "checked_at": "2026-10-08", "contentid": "1684836"}]}}
    rows = present.fact_rows(e, present.FIT, present.Notes(), ("063-454-7870", "0634547870"))
    row = next(r for r in rows if r["key"] == "babycarriage")
    assert row["conflict"] and row["flag_text"] == "출처마다 다름 · 방문 전 전화 확인"
    assert [b["provider_full"] for b in row["blocks"]] == ["군산근대역사박물관 홈페이지", "한국관광공사 TourAPI"]
    assert [b["text"] for b in row["blocks"]] == ["대여 가능(예약 없이 박물관 안내소에서)", "없음"]
    assert row["tel"] == ("063-454-7870", "0634547870")
    assert not any(f["name"] == "유모차 대여" for f in
                   jsonld.entity_node(e, {"locality": "군산시"}, "https://x", "https://x/p/", [], []).get("amenityFeature", []))


def test_modern_history_museum_fee_table_and_season_hours(S):
    e = place(S, "근대역사박물관")
    fees = present.value_view("usefee", e["facts"]["usefee"])["fees"]
    assert [g["label"] for g in fees["groups"]] == ["박물관 통합권", "개별권"]
    assert fees["groups"][0]["rows"] == [{"who": "성인", "price": "3,000원"}, {"who": "청소년·군인", "price": "2,000원"},
                                         {"who": "어린이", "price": "1,000원"}]
    assert fees["groups"][1]["rows"][-1] == {"who": "어린이", "price": "500원"}
    assert fees["foot"] == ["자세한 사항은 홈페이지 참조"]
    tt = present.value_view("usetime", e["facts"]["usetime"])["tt"]
    assert [(r["label"], r["value"], r["note"]) for r in tt["rows"]] == [
        ("3~10월", "09:00–18:00", "입장마감 17:30"), ("11~2월", "09:00–17:00", "입장마감 16:30")]
    texts = [x["text"] for x in present.status_items(e, full=True)]
    # the 27-character closed day now fits (≤48); the contested hours are flagged, not picked
    assert "매주 월요일, 1월 1일, 시장이 휴관일로 정한 날" in texts and "이용시간 출처마다 다름" in texts


# ------------------------------------------------------------------ the fee tile beside a combined ticket
TICKET_PLACES = ("근대역사박물관", "구-일본-제18은행-군산지점", "군산근대건축관", "진포해양공원", "채만식-문학관",
                 "31운동-100주년-기념관", "금강미래체험관")


def test_combined_ticket_is_set_beside_the_places_own_fee(S):
    """Operator-forwarded evaluation 2026-10-18: 근대역사박물관's body gave the single-site 성인 2,000원 while its first
    screen showed the 박물관 통합권's 3,000원 alone. A place a combined ticket (tickets.json) also opens shows both on
    its fee tile — the visitor's own first price (the table's combined groups and its residents' group taken out: review
    2026-10-18), then the same visitor's price of the narrowest ticket under the ticket's name, never the table's own
    words for what it opens (CLAUDE.md 3.3) — and the ticket's provider joins those under the tiles; sources that differ
    on the fee stay two values."""
    tk = {t["id"]: t for t in json.loads((DATA / "tickets.json").read_text("utf-8"))["tickets"]}
    museum = place(S, "근대역사박물관")
    kf = present.key_facts(museum, "hero")
    fee = next(s for s in kf["slots"] if s["key"] == "fee")
    assert (fee["main"], fee["sub"], fee["more"], fee["conflict"]) == ("개별 성인 2,000원", "박물관 통합권 성인 3,000원", True, False)
    assert "[개별권]\n- 성인 2,000원" in museum["facts"]["usefee"]
    assert tk["museum-combined"]["prices"]["개인"]["성인"][0] == 3000
    assert fee["provider"] == "한국관광공사" and fee["ticket"]["provider"] == "군산시" and "군산시" in kf["providers"]
    assert fee["ticket"]["url"] == "https://www.gunsan.go.kr/tour/m2080/view/305395"
    # never the combined price as the main value, on any card or list cell either
    assert present.slot_cell(museum, "fee", "요금")["main"] == "개별 성인 2,000원"
    assert next(s for s in present.key_facts(museum, "card")["slots"] if s["key"] == "fee")["sub"] == "박물관 통합권 성인 3,000원"
    rows = {slug: next(s for s in present.key_facts(place(S, slug), "hero")["slots"] if s["key"] == "fee")
            for slug in TICKET_PLACES}
    assert {slug: (r["main"], r["sub"]) for slug, r in rows.items() if r.get("ticket")} == {
        "근대역사박물관": ("개별 성인 2,000원", "박물관 통합권 성인 3,000원"),
        # the art museum's own table names its ticket after its single ticket: its own price leads all the same
        "구-일본-제18은행-군산지점": ("개별 성인 500원", "박물관 통합권 성인 3,000원"),
        "군산근대건축관": ("개별 성인 500원", "박물관 통합권 성인 3,000원"),
        "채만식-문학관": ("개별 성인 500원", "금강권 통합권 성인 5,000원"),
        "31운동-100주년-기념관": ("개별 성인 500원", "금강권 통합권 성인 5,000원"),
        # '[군산시민] 성인 1,000원' first in the table: the visitor's price is the '[타지역]' group's, beside the
        # ticket's price for a visitor — never the residents' prices alone
        "금강미래체험관": ("개별 성인 2,000원", "금강권 통합권 성인 5,000원"),
        # 진포해양공원: TourAPI 2026-11-05 gives the same table as 군산시 (성인 1,000원, 군산시민 500원) — one value now,
        # so its own price stands beside the museum ticket like the others
        "진포해양공원": ("개별 성인 1,000원", "박물관 통합권 성인 3,000원")}
    assert present.clean_lines(place(S, "금강미래체험관")["facts"]["usefee"])[:2] == ["[군산시민]", "- 성인 1,000원"]
    assert present.own_fee_row(place(S, "금강미래체험관")["facts"]["usefee"]) == \
        {"who": "성인", "price": "2,000원", "group": "타지역", "index": 1}
    assert present.own_fee_row("[군산시민]\n- 성인 1,000원") is None   # residents only: no visitor's price to set
    assert tk["geumgang-combined"]["prices"]["개인"]["성인"] == [5000, 3000]
    # what a ticket opens is never the table's own words on a tile (tickets.json 'covers', 군산시 문화관광's note)
    for r in rows.values():
        assert not any(t["covers"] in f"{r['main']} {r['sub']}" for t in tk.values()) and "+" not in r["sub"]
    # two sources that give a fee differently both stay the tile, no ticket is added to settle them (진포해양공원 until
    # TourAPI agreed on 2026-11-05: its earlier TourAPI value, as a second source on a copy of the record)
    jin = copy.deepcopy(place(S, "진포해양공원"))
    jin.setdefault("fact_alternatives", {})["usefee"] = [{
        "value": "[개인]- 성인 3,000원(500원)- 청소년,군인 2,000원(300원)- 어린이 1,000원(200원)※ 군산시 거주자 요금",
        "provider": "한국관광공사 TourAPI", "checked_at": "2026-10-26", "contentid": "923263"}]
    split = next(s for s in present.key_facts(jin, "hero")["slots"] if s["key"] == "fee")
    assert split["conflict"] and not split.get("ticket")
    # a place no ticket opens keeps the brief of its own table
    bear = next(s for s in present.key_facts(place(S, "테디베어박물관"), "hero")["slots"] if s["key"] == "fee")
    assert not bear.get("ticket") and not bear["main"].startswith("개별")
    # the ticket's price names its visitor as the place's own does (review 2026-10-18, fourth round: '개별 성인 2,000원 ·
    # 박물관 통합권 3,000원' left the ticket's visitor unsaid, where every other version names it) — the visitor word of
    # the place's own table, the ticket's price for that visitor from tickets.json
    for r in rows.values():
        if r.get("ticket"):
            who = present.own_fee_row(place(S, next(k for k, v in rows.items() if v is r))["facts"]["usefee"])["who"]
            assert r["sub"] == f"{r['ticket']['name']} {who} {r['ticket']['price']:,}원", r
    teen = present.fee_with_ticket(museum, "[개별권]\n- 청소년 1,000원\n- 성인 2,000원")
    assert (teen["main"], teen["sub"]) == ("개별 청소년 1,000원", "박물관 통합권 청소년 2,000원")
    assert tk["museum-combined"]["prices"]["개인"]["청소년·군인"][0] == 2000
    # no own price row (free, a sentence): nothing to set beside the ticket
    assert present.fee_with_ticket(museum, "무료") is None and present.fee_with_ticket(museum, "전화 문의") is None
    assert present.fee_with_ticket({**museum, "_tickets": []}, museum["facts"]["usefee"]) is None


def test_the_visitors_price_is_what_the_chat_the_planner_and_the_description_read(S, built):
    """Review 2026-10-18: the fee tile feeds the chat catalog, /plan/places.json and the meta description — where a
    place's table lists 군산시민 first, each of them gives the visitor's price beside the ticket's, never the residents'
    prices alone."""
    from urllib.parse import unquote
    e = place(S, "금강미래체험관")
    plan = json.loads((built / "plan" / "places.json").read_text("utf-8"))
    row = next(v for k, v in plan.items() if unquote(k) == e["_path"])
    assert row["f"] == "개별 성인 2,000원 · 금강권 통합권 성인 5,000원"
    line = json.loads((built / "chat" / "lines.json").read_text("utf-8"))["lines"][e["_path"]]   # the full catalog line
    assert "개별 성인 2,000원, 금강권 통합권 성인 5,000원" in line and "군산시민 1,000원" not in line, line
    page = (built / unquote(e["_path"]).strip("/") / "index.html").read_text("utf-8")
    desc = re.search(r'<meta name="description" content="([^"]*)"', page).group(1)
    assert "1,000원" not in desc and ("요금 개별 성인 2,000원" in desc or "요금" not in desc), desc


def test_every_ticket_that_opens_a_place_is_a_facts_row_with_its_source(S, built):
    """The facts card shows each combined ticket that opens the place right after its own 요금 — the ticket's name, what
    it opens in our words (its places by their page names, each linked but this one; review 2026-10-18: never the
    table's own note for them, tickets.json 'covers', a 60-character run of 군산시 문화관광's page, CLAUDE.md 3.3) and
    its table — with the table's page as its note. Where the place's own 요금 already holds that ticket as a group with
    the same prices, the row points to it (#f-usefee) instead of printing the table twice."""
    from pipeline import tickets
    from urllib.parse import unquote
    data = tickets.load(DATA)
    by_id = {e["id"]: e for e in S.entities}
    same = {"근대역사박물관": {"박물관 통합권": "박물관 통합권"}, "구-일본-제18은행-군산지점": {"박물관 통합권": "통합권"}}
    for slug, names in (("근대역사박물관", ["박물관 통합권", "금강권 통합권"]), ("채만식-문학관", ["금강권 통합권"]),
                        ("군산근대건축관", ["박물관 통합권", "금강권 통합권"]),
                        ("구-일본-제18은행-군산지점", ["박물관 통합권", "금강권 통합권"])):
        e = place(S, slug)
        vm = present.place_vm(S, e, entity_ctx(e, S))
        keys = [r["key"] for r in vm["practical"]]
        at = keys.index("usefee")
        rows = vm["practical"][at + 1:at + 1 + len(names)]
        assert [r["label"] for r in rows] == names and keys.count("tickets") == len(names), slug
        page = (built / unquote(e["_path"]).strip("/") / "index.html").read_text("utf-8")
        for r in rows:
            t = next(t for t in data["tickets"] if t["name"] == r["label"])
            head = f"{len(t['places'])}곳: " + " · ".join(by_id[p]["name"] for p in t["places"])
            group = same.get(slug, {}).get(t["name"])
            assert r["text"].split("\n") == [head, f"요금: 위 이용요금의 [{group}]"] if group else \
                [head, *tickets.price_lines(t)], slug
            assert t["covers"] not in r["text"] and t["covers"] not in str(r["html"]), slug
            for p in t["places"]:   # each other place a link to its page, this one plain
                link = f'<a href="{by_id[p]["_path"]}">{by_id[p]["name"]}</a>'
                assert (link in str(r["html"])) == (p != e["id"]), (slug, p)
            note = vm["notes"][r["n"] - 1]
            assert (note["provider"], note["url"]) == ("군산시 문화관광", data["sources"][t["source"]]["url"]), slug
            # the same table never twice: a pointer to the 요금 row, which carries the anchor
            assert ('<a href="#f-usefee">' in str(r["html"])) == bool(group) and \
                ("개인 — 성인" in r["text"]) == (not group), slug
        fee_row = vm["practical"][at]
        assert (fee_row.get("anchor") == "f-usefee") == (slug in same), slug
        assert ('id="f-usefee"' in page) == (slug in same) and page.count('id="f-usefee"') <= 1, slug
        # the notes stay numbered in the order the card shows them: each new number is the next one
        top = 0
        for r in vm["practical"]:
            for n in [r["n"], *(x["n"] for x in r["blocks"]), *(x["n"] for x in r["alts"])]:
                assert not n or n <= top + 1, (slug, r["label"], n, top)
                top = max(top, n or 0)
    assert "개인 — 성인 3,000원(군산시민 2,000원), 청소년·군인 2,000원(군산시민 1,000원), 어린이 1,000원(군산시민 500원)" in \
        tickets.price_lines(next(t for t in data["tickets"] if t["id"] == "museum-combined"))
    assert not [r for r in present.place_vm(S, place(S, "테디베어박물관"),
                                            entity_ctx(place(S, "테디베어박물관"), S))["practical"] if r["key"] == "tickets"]
    # no built page in any version prints a ticket's 'covers' words, but where the place's own stored fee holds them
    covers = [t["covers"] for t in data["tickets"]]
    for path in built.rglob("index.html"):
        html = path.read_text("utf-8")
        for c in covers:
            if c in html:
                e = next(x for x in S.entities if unquote(x["_path"]).strip("/") == path.parent.relative_to(built).as_posix())
                assert c in e["facts"].get("usefee", ""), (path, c)


def test_the_last_entry_is_in_the_first_summary(S):
    """Operator-forwarded evaluation 2026-10-18: the last entry belongs in the first summary whenever the data gives it.
    A time that follows a range joins that range when the tile would leave it behind '외' (a second season takes the
    sub line); a lone one takes the sub line; a rule without a time goes on the sub line in its own words. A tile that
    already shows it is unchanged."""
    b = lambda raw: present.brief_hours(raw)[0]   # noqa: E731
    assert b("3~10월 09:00~18:00(입장마감 17:30) / 11~2월 09:00~17:00(입장마감 16:30)") == \
        {"main": "3~10월 09:00–18:00(입장마감 17:30)", "sub": "11~2월 09:00–17:00(입장마감 16:30)", "more": False,
         "closed": False}
    assert b("[하절기(3~10월)]\n09:00~18:00 (입장마감 17:30)\n[동절기(11월~2월)]\n09:00~17:00 (입장마감 16:30)")["sub"] == \
        "동절기(11월~2월) 09:00–17:00(입장마감 16:30)"
    assert (b("09:00~21:00 (입장마감 20:30)")["main"], b("09:00~21:00 (입장마감 20:30)")["sub"]) == ("09:00–21:00", "입장마감 20:30")
    assert b("11:00~21:00 (브레이크 15:00~17:00)(입장마감 20:00)")["main"] == "11:00–21:00(입장마감 20:00)"
    assert b("평일 09:00~18:00 / 주말 10:00~19:00 / 입장마감 17:30")["sub"] == "입장마감 17:30"
    assert b("10:00~17:00\n※ 20분 전 입장마감\n※ 문화유산 보호를 위하여 실내 개방은 하지 않음")["sub"] == "20분 전 입장마감"
    assert b("하절기 10:00~18:00 / 동절기 10:00~17:00, 폐관 30분 전까지 입장")["sub"] == "동절기 10:00–17:00 · 폐관 30분 전까지 입장"
    assert b("09:00~18:00") == {"main": "09:00–18:00", "sub": "", "more": False, "closed": False}
    # every hours value of the data that gives a last entry time shows one on its tile
    seen = 0
    for e in S.entities:
        hours = present.slot_value(e, "hours")
        raw = (e.get("facts") or {}).get(hours["src_key"]) if hours else None
        if not raw or not re.search(r"(?:입장\s*(?:마감|종료)|마지막\s*입장)\s*\d{1,2}:\d{2}", str(raw)):
            continue
        shown = hours["vals"][0] if hours["conflict"] else hours
        assert present.LAST_ENTRY.search(f"{shown['main']} {shown['sub']}"), (e["name"], raw)
        seen += 1
    assert seen >= 6
    museum = present.slot_value(place(S, "근대역사박물관"), "hours")
    assert museum["conflict"] and [(v["provider"], v["main"]) for v in museum["vals"]] == \
        [("공식 홈페이지", "3~10월 09:00–18:00(입장마감 17:30)"), ("군산시", "09:00–21:00")]


def test_a_last_entry_another_source_adds_is_on_the_sub_line(S):
    """Review 2026-10-18: a source that adds to the stored hours (fact_alternatives relation 'also', the facts card's
    '또는 …') and gives the last entry the stored value lacks puts it on the tile's sub line, as brief_hours does for a
    rule of the value's own — each season's time after the season's word, the months left out, or the rule in its own
    words — and its provider joins those under the tiles. Every such place of the data, read from its 'also' values."""
    p = present.last_entry_part
    assert p("[하절기(3~10월)]\n09:00~18:00 (입장마감 17:30)\n[동절기(11월~2월)]\n09:00~17:00 (입장마감 16:30)") == \
        "하절기(입장마감 17:30), 동절기(입장마감 16:30)"
    assert p("09:00~21:00 (입장마감 20:30)") == "입장마감 20:30"
    assert p("10:00~17:00\n※ 20분 전 입장마감\n※ 문화유산 보호를 위하여 실내 개방은 하지 않음") == "20분 전 입장마감"
    assert p("10:00~17:00") == "" and p("") == ""
    seen = {}
    for e in S.entities:
        hours = present.slot_value(e, "hours")
        if not hours:
            continue
        also = [a for a in present.alternatives(e, hours["src_key"]) if a.get("relation") == "also"]
        extra = next((p(a["value"]) for a in also if p(a["value"])), "")
        if not extra:
            continue
        shown = hours["vals"][0] if hours["conflict"] else hours
        assert present.shows_last_entry(shown), (e["name"], shown)
        if not present.shows_last_entry(present.brief_hours((e.get("facts") or {}).get(hours["src_key"]))[0]):
            assert shown["sub"].endswith(extra) and hours["also"]["provider"] in present.key_facts(e)["providers"], e["name"]
            seen[e["slug"]] = shown["sub"]
    assert seen["군산근대건축관"] == "하절기 09:00–18:00 · 하절기(입장마감 17:30), 동절기(입장마감 16:30)"
    assert seen["군산신흥동일본식가옥"] == "20분 전 입장마감"
    assert present.key_facts(place(S, "군산근대건축관"))["providers"] == ["군산시", "한국관광공사"]


def test_a_range_keeps_its_season_in_one_unit_and_the_last_entry_its_own_weight():
    """Review 2026-10-18, fourth round: on the Korean museum page at 390px the hours tile broke after a season's word
    ('… 11~2월 | 09:00–17:00(입장마감 16:30)'). The nwt filter keeps the word right before a range — its season or days
    — with the range and the bracket after it in one unit (.nwu: a line breaks before it, not inside it); a time is
    never a season. The last entry's bracket is .kfl; the words do not change."""
    from markupsafe import escape

    from pipeline.build import css_source, make_env
    nwt = make_env().filters["nwt"]
    nw, kfl = '<span class="nw">{}</span>', '<span class="kfl">({} <span class="nw">{}</span>)</span>'
    cases = {
        "3~10월 09:00–18:00(입장마감 17:30)":
            '<span class="nwu">3~10월 ' + nw.format("09:00–18:00") + kfl.format("입장마감", "17:30") + "</span>",
        "동절기(11월~2월) 09:00–17:00(입장 마감 16:30)":
            '<span class="nwu">동절기(11월~2월) ' + nw.format("09:00–17:00") + kfl.format("입장 마감", "16:30") + "</span>",
        "평일 09:00–18:00, 토,일 10:00–19:00":
            '<span class="nwu">평일 ' + nw.format("09:00–18:00") + '</span>, <span class="nwu">토,일 ' + nw.format("10:00–19:00") + "</span>",
        "11:00–21:00(입장마감 20:00)": '<span class="nwu">' + nw.format("11:00–21:00") + kfl.format("입장마감", "20:00") + "</span>",
        "09:00–12:00 13:00–18:00": nw.format("09:00–12:00") + " " + nw.format("13:00–18:00"),
        "09:00–21:00 입장마감 20:30": nw.format("09:00–21:00") + " 입장마감 20:30",
        "하절기(입장마감 17:30), 동절기(입장마감 16:30)":
            '<span class="nwu">하절기' + kfl.format("입장마감", "17:30") + '</span>, <span class="nwu">동절기' + kfl.format("입장마감", "16:30") + "</span>",
        "11:00–21:00 (브레이크 15:00–17:00)": nw.format("11:00–21:00") + ' <span class="kfl">(브레이크 ' + nw.format("15:00–17:00") + ")</span>",
        "성인 3,000원(1,500원)": "성인 " + nw.format("3,000원(1,500원)"),
        "A&B 09:00–18:00": '<span class="nwu">A&amp;B ' + nw.format("09:00–18:00") + "</span>",
        # UI review 2026-10-19: a list mark stays out of the unit after it, at the end of the line before — a Japanese or
        # Chinese line never starts with '、' (the last entries en_site.last_entry_tr joins with the locale's list mark)
        "夏季（入場締切17:30）、冬季（入場締切16:30）":
            '<span class="nwu">夏季<span class="kfl">（入場締切' + nw.format("17:30") + '）</span></span>、<span class="nwu">冬季'
            '<span class="kfl">（入場締切' + nw.format("16:30") + "）</span></span>",
        "平日 09:00–18:00、土日 10:00–17:00":
            '<span class="nwu">平日 ' + nw.format("09:00–18:00") + '</span>、<span class="nwu">土日 ' + nw.format("10:00–17:00") + "</span>",
        "夏季（17:30停止入场），冬季（16:30停止入场）":
            '<span class="nwu">夏季<span class="kfl">（' + nw.format("17:30") + '停止入场）</span></span>，<span class="nwu">冬季'
            '<span class="kfl">（' + nw.format("16:30") + "停止入场）</span></span>",
        "월,화(입장마감 17:00)": '<span class="nwu">월,화' + kfl.format("입장마감", "17:00") + "</span>",
    }
    for text, want in cases.items():
        assert str(nwt(text)) == want, text
        assert re.sub(r"<[^>]+>", "", want) == str(escape(text))   # the words do not change
        assert not re.search(r'class="(?:nwu|kfl|nw)">[、，,;；·・]', want), text   # no unit begins with a list mark
    css = " ".join(css_source().split())
    assert ".nwu, .kfl { display: inline-block; }" in css
    # the size down is the first screen's big tiles' only, never under 13px; elsewhere the bracket keeps the value's size
    assert ".kf-main .kfl { font-weight: 400; letter-spacing: -.01em; }" in css
    assert not re.search(r"(?:^|[}/]\s)\.kf-main \.kfl \{[^}]*font-size", css)
    assert ".kf-hero .kf-main .kfl { font-size: max(13px, .68em); }" in css


@pytest.mark.parametrize("dev", [pytest.param({"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}, id="390"),
                                 pytest.param({"viewport": {"width": 1440, "height": 900}}, id="1440")])
def test_in_a_browser_the_last_entry_is_readable_and_a_season_keeps_its_time(S, built, dev):
    """Review 2026-10-18, fourth round, in a browser (Playwright + Chromium) at 390 (a phone) and 1440: the last entry's
    bracket ('(입장마감 17:30)') was .68em of every value it sat in — about 10px in list rows, the home's place cards and
    the phone's tiles. Now it keeps its value's size in rows and cards and is 13px or more on the first screen's tiles;
    on 근대역사박물관's hours tile each season stays on one line with its time, the line breaking between seasons, and
    nothing scrolls sideways."""
    sync_api = pytest.importorskip("playwright.sync_api")
    sizes = """() => [...document.querySelectorAll('.kfl')].filter(e => e.getClientRects().length).map(e => {
      const v = e.closest('.kf-main, .kf-sub, dd, p') || e.parentElement;
      return { hero: !!e.closest('.kf-hero'), px: parseFloat(getComputedStyle(e).fontSize),
               of: parseFloat(getComputedStyle(v).fontSize), t: e.textContent }; })"""
    units = """() => [...document.querySelectorAll('.kf-hero .kf-hours .nwu')].map(u => ({ t: u.textContent,
      h: u.getBoundingClientRect().height, lh: parseFloat(getComputedStyle(u.querySelector('.nw')).lineHeight) || 0 }))"""
    museum = f"http://site.test{quote(place(S, '근대역사박물관')['_path'])}"
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(**dev)
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            seen = {}
            for url in ("http://site.test/", "http://site.test/places/", museum):
                page.goto(url, wait_until="load")
                got = page.evaluate(sizes)
                for k in got:
                    assert k["px"] >= (13 if k["hero"] else 12), (url, k)
                    if not k["hero"]:
                        assert k["px"] == k["of"], (url, k)   # rows and cards: the value's own size
                seen[url] = len(got)
                assert page.evaluate("document.documentElement.scrollWidth") <= dev["viewport"]["width"], url
            assert seen["http://site.test/places/"] and seen["http://site.test/"] and seen[museum], seen
            us = page.evaluate(units)
            assert [u["t"] for u in us] == ["3~10월 09:00–18:00(입장마감 17:30)", "11~2월 09:00–17:00(입장마감 16:30)"], us
            for u in us:   # one line each: the season on the line of its time
                assert u["h"] < 1.6 * u["lh"], u
            ctx.close()
        finally:
            browser.close()


@pytest.mark.parametrize("width", [360, 390])
def test_in_a_browser_the_pressed_chip_stays_in_view_once_the_fonts_are_in(built, width):
    """UI review 2026-10-19: a phone list opened with a type filter scrolls its row to the pressed chip (site.js
    showPressed), but measured in the fallback font: on /en/places/ — the longest row, nine chips of English words —
    the last chip ended about 18px from the row's end, under its 36px fade, once Pretendard came. It runs again when
    the fonts are in. Here the font files come late (as on a slow phone) and every chip of the real row is checked."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import time
    serve = _serve(built)

    def late_fonts(route):
        if route.request.url.endswith(".woff2"):
            time.sleep(0.15)
        serve(route)
    seen = """() => { const r = document.querySelector('.f-top .f-row'), c = r.querySelector('[aria-pressed="true"]');
      const a = r.getBoundingClientRect(), b = c.getBoundingClientRect();
      return { v: c.getAttribute('data-v'), inside: b.left >= a.left && b.right <= a.right - 35, y: scrollY,
               wide: r.scrollWidth > 4 * r.clientWidth, fonts: document.fonts.status }; }"""
    dev = {"viewport": {"width": width, "height": 800}, "is_mobile": True, "has_touch": True}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(**dev)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/en/places/", wait_until="load")
            types = page.evaluate("[...document.querySelectorAll('.f-top [data-f=type]')].map(c => c.getAttribute('data-v'))")
            ctx.close()
            assert len(types) >= 8, types
            for t in types[1:]:
                ctx = browser.new_context(**dev)   # a first visit each: the fonts come after the row is first measured
                ctx.route("**/*", late_fonts)
                page = ctx.new_page()
                page.goto(f"http://site.test/en/places/?type={quote(t)}", wait_until="load")
                page.evaluate("document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => r())))")
                got = page.evaluate(seen)
                assert got == {"v": t, "inside": True, "y": 0, "wide": True, "fonts": "loaded"}, (t, got)
                ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ '가능요금 (무료)'
def test_free_parking_value_reads_the_same_in_page_status_and_markup(S):
    e = place(S, "새만금비응공원")
    assert e["facts"]["parking"] == "가능요금 (무료)"
    assert display_value("parking", e["facts"]["parking"]) == "가능, 요금 무료"
    assert "주차 가능(무료)" in [x["text"] for x in present.status_items(e)]
    node = jsonld.entity_node(e, S.site, "https://x", "https://x/p/", [], [])
    assert {"@type": "PropertyValue", "name": "주차", "value": "가능, 요금 무료"} in node["additionalProperty"]
    assert jsonld.amenity_value("parking", "가능요금 (무료)") is None          # not a plain Y/N value
    assert jsonld.amenity_value("parking", "주차장이 구비") is True             # shown as '가능'


# ------------------------------------------------------------------ phones
def test_0507_numbers_stay_whole_and_tel_dials_the_visible_number(S):
    e = place(S, "링스모텔")
    assert present.first_phone(e["facts"]["infocenter"]) == ("0507-1302-6070", "050713026070")
    html = str(present.tel_markup("예약 0507-1302-6070"))
    assert html == '예약 <a class="tel" data-track="tel_click" href="tel:050713026070">0507-1302-6070</a>'  # tracked like every call link
    links = 0
    for x, k, v in all_values(S):
        for m in re.finditer(r'href="tel:(\d+)">([^<]+)</a>', str(present.tel_markup(v))):
            assert m.group(1) == re.sub(r"\D", "", m.group(2)), (x["name"], v)
            links += 1
    for x in S.entities:
        for it in present.status_items(x, full=True):
            if it["key"] == "tel":
                assert it["href"] == "tel:" + re.sub(r"\D", "", it["text"])
    assert links > 250
    assert "07-1364-9263" not in str(present.tel_markup("0507-1364-9263")).replace("0507-1364-9263", "")


def test_other_versions_dial_the_international_form(S):
    """QA 2026-10-15 SRC-05a: on the other versions (intl) a call link dials +82 and the number without its trunk 0;
    a nationwide 15xx/16xx number keeps its digits (no international form); the visible text never changes; Korean
    pages keep the domestic digits."""
    links = 0
    for x, k, v in all_values(S):
        ko, intl = str(present.tel_markup(v)), str(present.tel_markup(v, intl=True))
        assert re.sub(r"<[^>]+>", "", intl) == re.sub(r"<[^>]+>", "", ko)
        for m in re.finditer(r'href="tel:([+\d]+)">([^<]+)</a>', intl):
            digits = re.sub(r"\D", "", m.group(2))
            want = digits if digits.startswith("1") else "+82" + digits[1:]
            assert m.group(1) == want, (x["name"], v)
            links += 1
    assert links > 250
    assert 'href="tel:+82634433077"' in present.rich("문의 063-443-3077로 합니다", "en")
    assert 'href="tel:0634433077"' in present.rich("문의 063-443-3077로 합니다", "ko")
    assert 'href="tel:15447788"' in present.rich("Korail (www.korail.com, 1544-7788)", "en")


def test_official_hosts_in_the_text_are_links_and_the_text_stays():
    """QA 2026-10-15 SRC-05b: an official site the text writes as a bare host is a link (only OFFICIAL_WEB's hosts);
    the text of the result is the input, character for character."""
    t = "예매는 한국해운조합(island.theksa.co.kr), 문의는 1644-8774"
    h = str(present.tel_markup(t))
    assert h.count('class="xl"') == 1 and h.count('class="tel"') == 1
    assert re.sub(r"<[^>]+>", "", h) == t
    assert 'href="https://island.theksa.co.kr/"' in h and 'data-track="official_click"' in h
    # the other versions: the English booking page of the same site
    assert 'href="https://island.theksa.co.kr/page/booking?lang=en"' in str(present.tel_markup(t, intl=True))
    for plain in ("gsmg-marathon.com은 열리지 않았습니다", "홈페이지 주소는 funvillage.kr입니다", "xwww.korail.com",
                  "https://www.korail.com/", "abc.mndcamp.com", "www.kobus.co.kr"):
        assert 'class="xl"' not in str(present.tel_markup(plain)), plain
    # an FAQ answer (skip): no link starts in its head, which FAQPage repeats and the validator compares as one run
    a = "It is 063-454-7870. Booking is at island.theksa.co.kr or 063-454-7871."
    h = str(present.tel_markup(a, intl=True, skip=present.PLAIN_HEAD))
    assert h.startswith("It is 063-454-7870. ") and h.count('class="tel"') == 1 and 'href="tel:+82634547871"' in h
    assert h.count('class="xl"') == 1 and re.sub(r"<[^>]+>", "", h) == a


# ------------------------------------------------------------------ courses
def test_two_night_course_meals_and_activities_are_not_stations(S):
    cv = next(v for v in S.course_vms.values() if v["c"]["name"] == "2박 3일 코스")
    seps = [(r["kind"], r["name"]) for r in cv["seps"]]
    assert ("meal", "중식") in seps and ("meal", "석식") in seps and ("activity", "유람선관광") in seps
    names = [s["name"] for s in cv["stops"]]
    assert "중식" not in names and "석식" not in names
    assert cv["n_places"] == len(cv["stops"]) == len(cv["c"]["stops"]) - len(seps)
    assert [s["code"] for s in cv["stops"]] == [f"{i:02d}" for i in range(1, cv["n_places"] + 1)]
    assert all("next_m" not in r and "cum" not in r for r in cv["seps"])
    # under 80% of legs measured: no distance sum, the measured share instead
    assert cv["measured"] < 0.8 * cv["legs_possible"] and not cv["show_total"]
    assert cv["measure_note"] == f"좌표 있는 구간 {cv['measured']}/{cv['legs_possible']}"
    assert re.fullmatch(r"월요일 휴관 \d+곳", cv["closed_note"])
    # equal spacing when a leg is unmeasured; a stop's distance from the start only while every leg before it is
    assert [round(s["x"], 6) for s in cv["stops"]] == [round(i / (cv["n_places"] - 1), 6) for i in range(cv["n_places"])]
    first_gap = next(i for i, s in enumerate(cv["stops"]) if s["next_m"] is None)
    assert all(s["cum"] is None for s in cv["stops"][first_gap + 1:])


def test_measured_course_shows_its_sum_and_a_computed_lede(S):
    cv = next(v for v in S.course_vms.values() if v["display"] == "B코스 근대~금강권")
    assert cv["complete"] and cv["show_total"]
    assert cv["lede"].startswith("처음 5곳은 출발지에서 직선 1km 안에 모여 있고, 가장 긴 구간은")
    arirang = next(v for v in S.course_vms.values() if v["display"] == "아리랑 코스")
    assert arirang["lede"] == " ".join(arirang["c"]["summary"].split())     # a written summary is kept


def test_course_page_shows_the_lede_that_jsonld_describes(built):
    page = built / "courses"
    found = 0
    for f in page.glob("*/index.html"):
        p = PageScan()
        p.feed(f.read_text("utf-8"))
        trip = next(n for raw in p.jsonld_raw for n in json.loads(raw)["@graph"] if n.get("@type") == "TouristTrip")
        assert "|" not in trip["name"] and trip["name"] in p.h1
        assert trip["description"] in p.plain
        assert "군산시 문화관광이 안내하는" not in p.blocks.get("summary", "")
        assert all(i["item"].get("name") not in ("중식", "석식", "숙소") for i in trip["itinerary"]["itemListElement"])
        found += 1
    assert found == 15


def test_course_map_needs_half_the_stops_and_numbers_them_as_the_list(S, built):
    """present.course_map: drawn only when at least half of the stops (and two or more) have coordinates; each
    marker carries its number in the stop list (meals and lodging are not stops). The course page shows the map
    with the factual caption, or none; the index cards name their first stops (route band), no ring diagram."""
    drawn = 0
    for cv in S.course_vms.values():
        stops, m = cv["stops"], present.course_map(cv["stops"])
        # QA 2026-10-15 F09-c: an optional stop (어청도 (선택사항)) is neither drawn nor counted for the share
        n_geo = sum(1 for s in stops if s["geo"] and not s["optional"])
        assert (m is not None) == (n_geo >= 2 and 2 * n_geo >= sum(1 for s in stops if not s["optional"]))
        html = (built / "courses" / cv["slug"] / "index.html").read_text("utf-8")
        assert "rt-dot" not in html and "route-fig" not in html and 'class="ng"' not in html   # no dashed rings
        if m:
            drawn += 1
            assert all(present.map_name(stops[p["n"] - 1]) == p["name"] and stops[p["n"] - 1]["geo"] for p in m["points"])
            assert f"경유지 {len(stops)}곳 중 좌표가 있는 {n_geo}곳 · 순서대로 직선 연결" in html and "data-map=" in html
        else:
            assert "data-map=" not in html and "co-grid no-map" in html
    assert 0 < drawn < len(S.course_vms)
    two = next(v for v in S.course_vms.values() if v["c"]["name"] == "2박 3일 코스")   # meals sit between its stops
    assert len(two["c"]["stops"]) > len(two["stops"]) and present.course_map(two["stops"])["points"][-1]["n"] <= len(two["stops"])
    index = (built / "courses" / "index.html").read_text("utf-8")
    # the index: one card per course, each with its route band (tests/test_courses_index.py checks the cards)
    assert index.count('class="cc-route"') == len(S.course_vms) and 'class="mini' not in index


def _course(S, cid):
    return next(v for v in S.course_vms.values() if v["c"]["id"] == cid)


def _move_block(built, cv) -> str:
    html = (built / "courses" / cv["slug"] / "index.html").read_text("utf-8")
    m = re.search(r'<section class="wrap chapter chapter-mid co-move"[^>]*data-block="move">(.*?)</section>', html, re.S)
    assert m, cv["slug"]
    return m.group(1)


def test_course_move_block_from_sourced_data(S, built):
    """QA 2026-10-15 F09: '차 없이 다니기' on course A from data the site holds — the nearest bus stops of the start
    (nearby.json, routes as the timetable names them; an empty list prints no route), a 카카오맵 대중교통 길찾기 link per
    measured leg between the two stored coordinates (never a place ID; the long 6 → 7 leg first), the island bus 99
    from transit.json, the guides, and once '확인 필요: 구간별 이동 시간·총 소요 시간' — never a time or 'walkable' of ours."""
    cv = _course(S, "gunsan-course-m2135-1")
    mv = present.course_move(S, cv)
    first = mv["lead"][0]
    assert first["s"]["name"] == "근대역사박물관"
    assert first["bus"][0] == {"name": "근대역사박물관", "m": 100, "routes": ["01", "08", "09", "18", "19", "71"],
                               "routes_text": "01·08·09·18·19·71"}
    assert [r["n"] for r in mv["lead"]] == [1, 7] and all(not b["routes"] for b in mv["lead"][1]["bus"])
    assert (mv["legs"][0]["a"]["n"], mv["legs"][0]["b"]["n"], present.dist(mv["legs"][0]["d"])) == (6, 7, "16.4km")
    assert len(mv["legs"]) == cv["measured"]
    for leg in mv["legs"]:
        a, b = leg["a"]["geo"], leg["b"]["geo"]
        assert leg["url"].startswith("https://map.kakao.com/link/by/traffic/")
        assert leg["url"].endswith(f",{a['lat']},{a['lng']}/{quote(leg['b']['name'], safe='')},{b['lat']},{b['lng']}")
    assert mv["routes"][0]["no"] == "99" and {"01", "08", "09", "18", "19", "71"} <= {r["no"] for r in mv["routes"]}
    assert [g["path"] for g in mv["guides"]][:2] == [S.guide_by_id["guide-01"]["_path"],
                                                      S.guide_by_id["guide-31"]["_path"] + "#h-b6"]
    block = _move_block(built, cv)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block))
    assert "확인 필요: 구간별 이동 시간·총 소요 시간" in text and text.count("확인 필요") == 1
    assert "실제 이동" not in text and not re.search(r"\d+\s*분\s*(?:걸|소요)|도보|걸어서", text)
    assert block.count('data-provider="kakao_transit"') == len(mv["legs"])
    assert re.search(r"data-bus=\"신시도입구삼거리\"[^>]*>[^<]*정류장 <span class=\"tn\">490m</span></p>", block)   # no routes
    assert "장자도 07:20~21:20" in text and "비응(환) 07:45~21:45" in text and "매시 40분" in text
    assert "방문 전 전화 확인" in text and 'href="tel:0634433077"' in block


def test_course_days_options_and_the_source_duration(S, built):
    """QA 2026-10-15 F09-b: the source's day / option headings in source order; no leg between the last stop of
    '2일차(1안)' and the first of '2일차(2안)' (not counted, not measured, no neighbour on the boards); a day change
    keeps its leg (B코스 장자도 → 무녀도); the one source duration '12시간' with its m2136 source."""
    b = _course(S, "gunsan-course-m2136-2")
    assert b["days"] == ["1일차", "2일차(1안)", "2일차(2안)"]
    st = {s["n"]: s for s in b["stops"]}
    assert st[13]["brk"] and st[12]["next"] is None and st[13]["prev"] is None
    assert st[12]["next_m"] is None and st[13]["prev_m"] is None and (st[12], st[13]) not in b["pairs"]
    assert b["legs_possible"] == len(b["stops"]) - 2                     # one break, no optional stop
    assert st[8]["day"] == "1일차" and st[9]["day"] == "2일차(1안)" and st[8]["next_m"] is not None   # 장자도 → 무녀도
    assert b["taketime"]["value"] == "12시간" and b["taketime"]["source_url"] == "https://www.gunsan.go.kr/tour/m2136"
    html = (built / "courses" / b["slug"] / "index.html").read_text("utf-8")
    assert "<dt>소요시간</dt><dd class=\"tn\">12시간</dd>" in html and 'href="https://www.gunsan.go.kr/tour/m2136"' in html
    seps = re.findall(r'<li class="stop-sep sep-day"><span class="sep-k">[^<]*</span><span class="sep-v">([^<]*)</span>', html)
    assert seps == b["days"]
    assert "2일차(1안) 끝" in html and "2일차(2안) 시작" in html
    pts = present.course_map(b["stops"])["points"]
    assert [p.get("seg", 0) for p in pts if p["n"] >= 13] == [1, 1] and all(not p.get("seg") for p in pts if p["n"] < 13)
    two = _course(S, "gunsan-course-m2137-1")
    dj = next(s for s in two["stops"] if s["t"] and s["t"]["slug"] == "대장도")
    assert dj["name"] == "대장도대장봉등반" and dj["part_of"]          # a stop inside a place keeps the course's name
    assert dj["day"] == "2일차(1안)" and dj["next"] is None and dj["next_m"] is None
    # the 2026-10-15 one-visit merge stays: C코스 은파호수공원야경 (1일차) → 은파호수공원 (2일차) is one place, 0 m
    c = _course(S, "gunsan-course-m2136-3")
    assert c["days"] == ["1일차", "2일차"] and not any(s["brk"] for s in c["stops"])


def test_course_relinked_optional_and_see_stops(S, built):
    """QA 2026-10-15 F09-c: stops linked again by tools/round2_data.link_course_stops (옥돌해변, 방축도 출렁 다리 …);
    '어청도 (선택사항)' is optional — no leg into it, not on the map, the island ferry guide on its card; the
    장자도차도선선착장 → 방축도 leg carries the ferry guide; '선유도,대장도일원' links both islands, with no leg."""
    c3 = _course(S, "gunsan-course-m2135-3")
    assert [s["t"]["slug"] if s["t"] else None for s in c3["stops"][:2]] == ["옥돌해변", "옥돌해변"]
    # review 2026-10-17 ('코스 미리보기에 옥돌해변이 두 번 연달아'): the deck path inside the beach is named as the course
    # names it, its row says whose it is, and the place's own page is still its link
    assert [(s["name"], s["short"], s["part_of"], s["label"]) for s in c3["stops"][:2]] == [
        ("옥돌해변 명품 데크길", "옥돌해변 명품 데크길", True, ""), ("옥돌해변", "옥돌해변", False, "")]
    listing = (built / "courses" / "index.html").read_text("utf-8")
    assert "옥돌해변</a><span class=\"ls-arr\" aria-hidden=\"true\">&nbsp;→</span></li> <li><a href=\"/places/옥돌해변/\">옥돌해변<" not in listing
    assert "옥돌해변 명품 데크길" in listing   # the course card's route band names the first stop (2026-10-31 cards)
    five = _course(S, "gunsan-course-m2552-5")
    ech = five["stops"][-1]
    assert ech["optional"] and ech["t"]["slug"] == "어청도" and ech["prev_m"] is None
    assert all(ech not in pair for pair in five["pairs"])
    m = present.course_map(five["stops"])
    assert m is None or ech["n"] not in [p["n"] for p in m["points"]]
    assert ech["guide"]["path"] == S.guide_by_id["guide-32"]["_path"] + "#h-b2"
    html = (built / "courses" / five["slug"] / "index.html").read_text("utf-8")
    assert "선택 경유지" in html and f'href="{ech["guide"]["path"]}"' in html
    b = _course(S, "gunsan-course-m2136-2")
    mv = present.course_move(S, b)
    leg = next(l for l in mv["legs"] if l["b"]["name"] == "방축도 출렁 다리")
    assert leg["a"]["name"] == "장자도차도선선착장" and leg["a"]["t"]["slug"] == "장자도"   # the pier, inside 장자도
    assert leg["guide"]["path"].startswith(S.guide_by_id["guide-32"]["_path"])
    a = _course(S, "gunsan-course-m2135-1")
    see = next(s for s in a["stops"] if s["see"])
    assert [x["name"] for x in see["see"]] == ["선유도", "대장도"] and see["t"] is None and see["geo"] is None
    page = (built / "courses" / a["slug"] / "index.html").read_text("utf-8")
    assert all(f'href="{x["path"]}"' in page for x in see["see"])


def test_validate_checks_the_move_block_and_the_timetable_copy(S, built):
    """pipeline.validate: course_move_problems reads the block's bus rows against nearby.json (a changed route number
    is a finding) and its transit links against the stops' coordinates; transit_problems checks transit.json against
    the reviewed guide-31 timetable record (a changed '21:45' is a finding)."""
    import copy
    from pipeline.validate import course_move_problems, scan_file, transit_problems
    c = next(x for x in S.courses if x["id"] == "gunsan-course-m2135-1")
    page = scan_file(built / "courses" / c["slug"] / "index.html")
    assert course_move_problems(S, c, page) == []
    pid = S.ent_by_slug["근대역사박물관"]["id"]
    saved = S.nearby[pid]
    try:
        S.nearby[pid] = {**saved, "bus": [{**saved["bus"][0], "routes": ["01", "08", "09", "18", "19", "72"]}, *saved["bus"][1:]]}
        assert any("근대역사박물관" in p and "72" in p for p in course_move_problems(S, c, page))
    finally:
        S.nearby[pid] = saved
    leg = next(r for r in page.access_rows if r["kind"] == "leg")
    leg_hrefs = list(leg["hrefs"])
    leg["hrefs"][:] = [h.replace("/link/by/traffic/", "/link/to/") for h in leg_hrefs]
    try:
        assert any("대중교통 길찾기 링크" in p for p in course_move_problems(S, c, page))
    finally:
        leg["hrefs"][:] = leg_hrefs
    # on a site that shows both values guide-31 must also name the other source's 99 비응(환) time; 군산각 shows one
    # value per fact (site.json fact_conflicts 'primary'), and its guide names the timetable's time only
    assert any("'매시 40분'가 guide-31 본문에 없음" in p for p in transit_problems(S))
    saved_tr = S.transit
    S.site["fact_conflicts"] = "primary"
    try:
        assert transit_problems(S) == []
        tr = copy.deepcopy(saved_tr)
        t = tr["routes"][-1]["times"][-1]
        assert (tr["routes"][-1]["no"], t["weekday"]) == ("99", "07:45~21:45")
        t["weekday"] = t["weekend"] = "07:45~21:46"
        S.transit = tr
        assert any("99번" in p for p in transit_problems(S))
    finally:
        S.transit = saved_tr
        S.site.pop("fact_conflicts")


# ------------------------------------------------------------------ search
def test_menu_search_finds_binhaewon_and_alternate_names(S, built):
    index = json.loads((built / "search" / "index.json").read_text("utf-8"))
    row = next(r for r in index if r["n"] == "빈해원")
    assert "짜장면" in row["m"] and row["s"]
    norm = lambda s: re.sub(r"\s+", "", (s or "").lower())
    hits = [r["n"] for r in index if norm("짜장면") in norm(r.get("m"))]
    assert "빈해원" in hits
    assert any("군산근대역사박물관" in r["a"] for r in index if r["n"] == "근대역사박물관")
    js = (ROOT / "templates" / "assets" / "search.js").read_text("utf-8")
    assert "row.m" in js and "?q=" in js and "focus" in js
    html = (built / "search" / "index.html").read_text("utf-8")
    assert 'action="/search/"' in html and "빈해원" in html                    # no-JS: the 가나다 directory
    assert sum(1 for r in index if r["k"] in ("attraction", "stay", "food")) == len(S.entities)


def test_search_concepts_point_at_real_entries(S):
    """present.SEARCH_CONCEPTS (evaluation 2026-10-18: '비 오는 날 아이랑' found nothing): every word a concept stands
    for finds a row of the Gunsan index, compared as search.js does (lower case, without spaces and ·-()[]|,; names,
    other names, dishes, designations, 동·권역·type) — the table never stands in for a page the site lacks; no word a
    reader says belongs to two concepts. The rainy-day guide (guide-03) has the rain concept, the guide for
    travelling with children (guide-02) the children's one, and no row has both: search.js lists those two guides as
    '관련 가이드' for '비 오는 날 아이랑' (tests/test_ask_browser.py)."""
    def flat(s):
        return present.SEARCH_STRIP.sub("", str(s or "")).lower()
    rows = present.search_index(S)
    hay = [(r, "\n".join([*(flat(r.get(f)) for f in ("n", "a", "o", "v", "m", "g")),
                          flat(" ".join([r.get("d") or "", r.get("r") or "", r.get("t") or ""]))])) for r in rows]
    said = {}
    for c in present.SEARCH_CONCEPTS:
        assert c["say"] and c["find"], c
        for w in c["find"]:
            assert any(flat(w) in h for _, h in hay), w
        for w in c["say"]:
            assert flat(w) and flat(w) not in said, w
            said[flat(w)] = c

    def has(c, r):
        return any(flat(w) in h for x, h in hay if x is r for w in c["find"])
    rain, kids = said[flat("비 오는")], said[flat("아이랑")]
    assert said[flat("비오는")] is rain and said[flat("아이와")] is kids
    row = {r["p"]: r for r in rows}
    assert has(rain, row[S.guide_by_id["guide-03"]["_path"]]) and has(kids, row[S.guide_by_id["guide-02"]["_path"]])
    assert not [r["n"] for r in rows if has(rain, r) and has(kids, r)]
    # the words the evaluation named: 차 없이·뚜벅이·대중교통 → the car-free guide, 맛집·밥집 → 음식점, 주차, 야경
    assert has(said[flat("뚜벅이")], row[S.guide_by_id["guide-01"]["_path"]])
    assert said[flat("대중교통")] is said[flat("차 없이")] and said[flat("밥집")] is said[flat("맛집")]
    assert "음식점" in said[flat("밥집")]["find"] and "주차" in said[flat("주차")]["find"]
    assert has(said[flat("밤")], row[S.guide_by_id["guide-11"]["_path"]])


def test_search_page_says_what_it_covers_and_carries_the_query_words(built):
    """The Korean /search/ (evaluation 2026-10-18): one line under the box says what the search finds and that travel
    questions go to the AI chat (the input's description); the form carries the query words for search.js
    (data-concepts = present.SEARCH_CONCEPTS), the city (data-region) and the AI course planner's path, a page this
    build writes (data-planner). The 404 page's form (no search.js) carries none of it."""
    page = (built / "search" / "index.html").read_text("utf-8")
    form = re.search(r'<form class="search"[^>]*>', page).group(0)
    attrs = {k: unescape(v) for k, v in re.findall(r' data-([a-z-]+)="([^"]*)"', form)}
    assert json.loads(attrs["concepts"]) == present.SEARCH_CONCEPTS
    assert attrs["region"] == "군산" and attrs["planner"] == "/plan/" and (built / "plan" / "index.html").exists()
    assert '<p class="search-note" id="q-note">장소 이름·메뉴·동네·가이드를 찾고, 여행 질문은 AI 챗봇에게 물어보세요.</p>' in page
    assert 'aria-describedby="q-note"' in page and not re.search(r"data-plan[\s>=]", page)   # site.js: no plan.js here
    not_found = (built / "404.html").read_text("utf-8")
    assert "data-concepts" not in not_found and "search-note" not in not_found


def test_other_versions_search_lists_related_guides_in_their_language(S, built):
    """Review 2026-10-18, in a browser (Playwright + Chromium; the build served through page.route): on the English
    search, 'things to do in the rain' asks for 'rain' (things, the and the words of one or two letters are no
    condition; before, every guide with to·in·do·the in it came first and the rainy-day guide was not among the five):
    no row has every word of it, so 'Related guides' lists the rainy-day guide ('Rainy day': a word that starts with
    'rain'; there a Latin word is found at a word start, not inside 'Training'). The French stop words the same ('que
    faire sous la pluie' lists the guide with 'pluie' in its title); the German search lists the rainy-day and
    children guides under 'Passende Ratgeber' for 'Regen mit Kindern', the Japanese one under '関連ガイド' for a Korean
    query and names the words also searched in Japanese. The rows found keep the matching before the query words
    (review round 3): each word inside the row's text, so 'pilot rain' finds Pilot Training; '아이스크림' brings no
    concept there either."""
    sync_api = pytest.importorskip("playwright.sync_api")
    korean = {S.guide_by_id[g]["title"]: g for g in ("guide-02", "guide-03")}

    def guides(code):
        rows = json.loads((built / code / "search" / "index.json").read_text("utf-8"))
        return {korean[t]: r["p"] for r in rows if r["k"] == "guide" for t in korean if t in (r.get("o") or "")}

    hrefs = "els => els.map(a => a.getAttribute('href'))"
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def search(code, q):
                page.goto(f"http://site.test/{code}/search/?q={quote(q)}", wait_until="load")
                page.wait_for_selector(".f-result, .res-none")
                return page.locator(".res-rel a").evaluate_all(hrefs)

            en, de, ja = guides("en"), guides("de"), guides("ja")
            assert search("en", "things to do in the rain") == [en["guide-03"]]
            assert page.inner_text(".res-rel h2").startswith("Related guides") and page.locator(".f-result").count() == 0
            assert search("fr", "que faire sous la pluie") == [guides("fr")["guide-03"]]
            assert page.locator(".f-result").count() == 0
            assert sorted(search("de", "Regen mit Kindern")) == sorted([de["guide-02"], de["guide-03"]])
            assert page.inner_text(".res-rel h2").startswith("Passende Ratgeber")
            assert search("ja", "비 오는 날 아이랑") == [ja["guide-03"], ja["guide-02"]]
            assert page.inner_text(".res-rel h2").startswith("関連ガイド")
            assert page.inner_text(".res-syn").startswith("あわせて検索：")
            assert not search("en", "pilot rain") and page.locator(".f-result").count() == 1
            assert [n for n in page.locator(".res-nm").all_inner_texts() if "Pilot Training" in n]
            assert not search("en", "아이스크림") and page.locator(".res-syn").count() == 0
            assert errors == []
            ctx.close()
        finally:
            browser.close()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_search_finds_every_row_it_found_before_the_query_words_in_every_version(built):
    """Review round 3 (2026-10-18; two rounds of query words dropped words: '빵 맛집' listed every restaurant, '마을',
    '섬여행' vanished through their endings, '주차할 곳' found nothing, 'cafe' missed 'Cafes'): tests/js/search.test.js on
    this build's search pages and indexes, in Korean, English, German, French, Spanish, Japanese and Simplified Chinese
    — the rows found for every name, menu word, 동·권역, guide-title word and the review's queries include every row
    the script before the query words found (tests/fixtures/search_99a303949.js); a word next to a concept stays a
    condition; concept words only where they stand as words or word starts ('아이스크림' is none); the related guides
    (the evaluation query '비 오는 날 아이랑', clause words such as quand·cuándo·когда no part). None of it is
    skipped: this build's forms carry the query words."""
    r = subprocess.run([shutil.which("node"), "--test", str(ROOT / "tests" / "js" / "search.test.js")], cwd=ROOT,
                       env={**os.environ, "SEARCH_SITE_DIR": str(built)}, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout[-6000:] + "\n" + r.stderr[-3000:]
    assert re.search(r"(?:#|ℹ) fail 0", r.stdout) and re.search(r"(?:#|ℹ) skipped 0", r.stdout), r.stdout[-2000:]


def test_other_names_keep_only_what_the_search_would_not_find_anyway():
    """present.other_names (QA 2026-10-15 U10): the names in the other versions, ' · '-joined in their order, each
    once — without one search.js finds anyway (inside n, a or a longer name kept, compared as search.js does)."""
    row = {"n": "선유도", "a": "선유도 해수욕장"}
    present.other_names(row, "Seonyudo Island", "", None, "seonyudo island", "선유 도", "2026 Seonyudo Island Festival")
    assert row["o"] == "2026 Seonyudo Island Festival"
    row = {"n": "군산시간여행축제", "a": ""}
    present.other_names(row, "2026 군산시간여행축제", "Gunsan Time Travel Festival")
    assert row["o"] == "2026 군산시간여행축제 · Gunsan Time Travel Festival"
    row = {"n": "A", "a": ""}
    present.other_names(row, "", None, "A")
    assert "o" not in row
    present.other_names(row, "선유도", "Seonyudo Island", key="v")
    assert row["v"] == "선유도 · Seonyudo Island"


def test_the_index_has_no_other_language_names_without_the_english_version():
    """A build without an English version (the sample data): no row carries o or v, and nothing breaks."""
    S = State(ROOT / "data" / "sample", "sample")
    assert getattr(S, "en", None) is None
    rows = present.search_index(S)
    assert rows and not any("o" in r or "v" in r for r in rows)


# ------------------------------------------------------------------ status line, stays, regions, home
def test_status_line_is_never_empty_and_shows_no_check_date(S):
    # rule change (operator decision 2026-10-09): the line used to end with the earliest 확인일 of its items; now
    # no item is a date and no item text carries a check date (validate.visible_check_dates)
    from pipeline.validate import visible_check_dates
    for e in S.entities:
        items = present.status_items(e, full=True)
        assert items, e["name"]
        assert all(x["key"] != "date" for x in items), e["name"]
        assert not visible_check_dates(" ".join(x["text"] for x in items)), e["name"]
    harbour = present.status_items(place(S, "군산내항"))
    assert harbour[0]["text"].startswith("확인 필요: ") and harbour[0]["href"].endswith("#h-facts")


def test_stay_ask_line_only_where_it_can_differ(S):
    asked = []
    for e in S.lists["stay"]:
        vm = present.place_vm(S, e, entity_ctx(e, S))
        rooms = (e.get("facts") or {}).get("roomcount", "")
        if vm["ask"]:
            asked.append(e)
            assert any(w in e["_type"] for w in present.SMALL_STAY) or (str(rooms).isdigit() and int(rooms) <= 3)
    big = place(S, "베스트웨스턴-군산호텔") if "베스트웨스턴-군산호텔" in S.ent_by_slug else None
    assert asked and len(asked) < len(S.lists["stay"]) / 2
    if big:
        assert not present.place_vm(S, big, entity_ctx(big, S))["ask"]


def test_regions_follow_the_five_anchors(S):
    assert [a["name"] for a in S.anchors] == ["원도심", "은파", "고군산", "새만금·비응", "금강"]
    assert place(S, "근대역사박물관")["_region"] == "원도심" and place(S, "선유도")["_region"] == "고군산"
    assert place(S, "어청도")["_region"] == present.FAR_LABEL
    for e in S.entities:
        assert e["_region"] in S.region_names
        if not e["_geo"]:
            assert e["_region_basis"] in ("읍·면·동", "") and (e["_region_basis"] or e["_region"] == present.NONE_LABEL)
    vm = present.map_vm(S)
    ids = [r["id"] for r in vm["regions"]] + [d["id"] for r in vm["regions"] for d in r["dongs"]]
    assert all(" " not in i for i in ids) and len(ids) == len(set(ids))
    assert sum(len(r["members"]) for r in vm["regions"]) == len(S.entities)
    # the kind toggles' counts (site.js keeps them to the chosen 권역)
    assert sum(vm["k_all"].values()) == len(S.entities) and set(vm["k_all"]) <= {"attraction", "stay", "food"}


def test_list_filters_count_the_places_off_the_map(S):
    """Outside evaluation 2026-10-18: the list map's caption says how many places are not on it — the list's rows
    without coordinates (n_off), so the caption's two numbers add up to the list."""
    for kind in ("attraction", "food", "stay"):
        L = present.list_vm(S, kind)
        F = L["filters"]
        off = sum(1 for g in L["groups"] for it in g["recs"] if not it["geo"])
        assert F["n_off"] == off == F["count"] - F["n_geo"] > 0, kind


def test_home_answer_figures_have_a_referent(S):
    h = present.home_vm(S)
    assert h["h1"] == "군산, 1899년에 개항한 항구 도시"
    assert re.search(r"직선 1km 안에 관광지 \d+곳", h["lede"])
    assert h["answers"]
    for a in h["answers"]:
        assert not a["fig"] or a["fig"].replace(",", "") in present.figures(a["answer"]) or a["fig_label"], a
    assert present.answer_row("x", "/", "숫자가 없는 문장", "12", "곳")["fig"] == ""


def test_home_focus_follows_dish_festivals(S):
    """Owner 2026-10-13 ('왜 아직도 짬뽕 요리가 메인이지?'): a dish leads the home — the 맛집 tile, the last answer row,
    the search example — only while its festival runs or starts within FOCUS_DAYS; otherwise the tile leads with the
    restaurant count and the dishes are equal pills, largest count first."""
    saved = S.today
    try:
        S.today = "2026-10-13"                                   # two days after the 2026 짬뽕 festival (10-09–10-11)
        assert present.home_focus(S) is None
        food = present.purposes_vm(S)[0]
        assert (food["key"], food["lead"], food["fig"]) == ("맛집", "음식점", "169")   # 2026-10-31: 3 closed places down
        assert food["pills"] == ["짬뽕 20곳", "게장 12곳", "아귀 9곳", "떡갈비 6곳"]
        assert "짬뽕" not in present.search_example(S)
        keys = [a["key"] for a in present.home_vm(S)["answers"]]
        assert "짬뽕" not in keys and "가는 법" in keys
        S.today = "2026-09-25"                                   # 14 days before it
        assert present.home_focus(S)["dish"] == "짬뽕"
        food = present.purposes_vm(S)[0]
        assert (food["lead"], food["fig"]) == ("짬뽕 요리", "20") and present.search_example(S).startswith("예: 짬뽕")
        assert "짬뽕" in [a["key"] for a in present.home_vm(S)["answers"]]
        S.today = "2026-09-10"                                   # 29 days before: out of the window
        assert present.home_focus(S) is None
    finally:
        S.today = saved


def test_home_accent_points(S, built):
    """Accent points (owner 2026-10-09, after masstige.io): the hub guides lead the answer bar's bento on lime · lavender ·
    sky, the official 당일 courses are the one black tile, the rest stay grey; each home has one lime-marked H1 phrase
    and (review 2026-10-14) no black band on either home any more."""
    rows = present.purposes_vm(S)
    tones = [(p["key"], p.get("tone", "")) for p in rows]
    assert tones[:4] == [("맛집", "lead"), ("숙소·펜션", "tint"), ("가볼만한 곳", "mist"), ("당일", "sea")]
    assert tones[4:] and not any(t for _, t in tones[4:])
    # review 2026-10-09: the lime figure names what it counts ('음식점 172곳', or '짬뽕 요리 20곳' around the festival —
    # test_home_focus_follows_dish_festivals); the other parts become pills
    food = rows[0]
    lead = food["lead"]
    assert lead in ("음식점", "짬뽕 요리") and food["short"].startswith(f"{lead} {food['fig']}{food['unit']} · ")
    assert food["pills"] and not any(p.startswith(lead) for p in food["pills"])
    # the phone line and the pills are the desktop line's other parts (nothing the lead already says, nothing new)
    assert food["pills"] == food["short"].split(" · ")[1:]
    assert all(part in food["pills"] for part in food["tiny"].split(" · "))
    # UI4 (owner 2026-10-14): the homes have no colour bento and no black band any more — their purposes are the
    # question card's icon menu and the guides
    for page in ("index.html", "en/index.html"):
        html = (built / page).read_text("utf-8")
        assert re.search(r'<h1 id="h-home" class="op-h1[^"]*">.+?</h1>', html) and 'class="mkr"' not in html, page
        # the big-numerals band is retired (owner 2026-10-14: 'AI 같고 촌스럽다'), no heading ends in a full stop
        assert 'id="h-nums"' not in html and not re.search(r'class="h2"[^>]*>[^<]*[가-힣a-z]\.</h2>', html), page
    en = (built / "en" / "index.html").read_text("utf-8")
    # owner 2026-10-14 ('외국어 사이트들은 UI UX가 아직 업데이트가 안 됐네'): the English home takes the Korean home's
    # design — no bento tiles, no black band, no oversized word; the counts under the icon menu's pictures
    assert "band-dk" not in en and "on-dark" not in en and 'class="dk-word"' not in en
    assert 'class="bt ' not in en and '<section class="abar"' not in en and 'class="hq-n tn"' in en
    assert '<section class="sec sec-co tone-2" aria-labelledby="h-co">' in en
    ko = (built / "index.html").read_text("utf-8")
    assert 'class="hq-n tn"' in ko   # the counts sit under the menu's pictures instead
    assert 'class="bt ' not in ko and "band-dk" not in ko and '<section class="abar"' not in ko
    assert '<section class="story" data-story' in ko and ko.count('class="dk-word"') <= 1
    css = (built / "assets" / "style.css").read_text("utf-8")
    assert "--lime:var(--tint2)" in css.replace(" ", "")   # the lime / lavender / sky roles are retired to sea tints


def test_home_survives_missing_places(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for f in DATA.glob("*.json"):
        rows = json.loads(f.read_text("utf-8"))
        if f.name == "places.json":
            rows = [p for p in rows if p["slug"] not in ("구-군산세관-본관", "군산내항", "근대역사박물관")]
        (data / f.name).write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
    S2 = State(data, "preview")
    h = present.home_vm(S2)
    assert not h["h1"] and not h["lede"] and h["answers"]
    assert any("구-군산세관-본관" in w for w in S2.warnings) and "원도심" not in [a["name"] for a in S2.anchors]


# ------------------------------------------------------------------ home opening (owner 2026-10-13, specs/home_redesign.md)
NEWS_ORDER = ("reel", "festival", "event", "abroad", "guide", "video")   # reel: the pinned edition's reel (2026-11-04)


def _check_news(S, day: str) -> list[dict]:
    """The ranking rule (the comment above present.NEWS_MAX) checked against the data itself on one build date."""
    S.today = day
    news = present.home_news(S)
    kinds = [c["kind"] for c in news]
    assert present.NEWS_MIN <= len(news) <= present.NEWS_MAX, (day, kinds)
    assert len({c["key"] for c in news}) == len(news) and all(c["href"] and c["title"] for c in news)
    assert kinds == sorted(kinds, key=NEWS_ORDER.index), (day, kinds)    # focus → events → abroad → guides → video
    # events: the dish festival's card first when it runs (focus), then the running / coming editions within 30 days
    # in ranked_events order, an edition the operator pinned (pin_home, 2026-10-31) first whatever its distance;
    # nothing past
    rows = [r for r in present.pinned_first(present.ranked_events(S))
            if r["days"] <= present.NEWS_EVENT_DAYS or r["ev"].get("pin_home")]
    want = ["ev:" + str(r["ev"].get("id")) for r in rows]
    got = [c["key"] for c in news if c["kind"] == "event"]
    # the reel card (operator 2026-11-04) stands in for its edition's event card
    reel = ["ev:" + c["key"].split(":", 1)[1] for c in news if c["kind"] == "reel"]
    assert got == [k for k in want if k in got] and all(r["last"] >= day for r in rows) and not set(reel) & set(got)
    assert all(c["key"] in want for c in news if c["kind"] == "festival") and all(k in want for k in reel)
    if "festival" not in kinds:
        assert reel + got == want[:3]
    # foreign press: the newest articles dated on or before the build date (date, then id)
    dated = sorted((a for a in S.abroad if a.get("kind") == "article" and a.get("date")
                    and present.iso_floor(a["date"]) <= day), key=lambda a: a["id"])
    dated.sort(key=lambda a: present.iso_floor(a["date"]), reverse=True)
    ab = [c["key"] for c in news if c["kind"] == "abroad"]
    assert ab and ab == ["ab:" + a["id"] for a in dated[:len(ab)]]
    # guides: approved_at, then the guide number, both newest first
    guides = [c["href"] for c in news if c["kind"] == "guide"]
    top = sorted(S.guides, key=present._guide_rank, reverse=True)
    assert guides and guides == [g["_path"] for g in top[:len(guides)]]
    return news


def test_home_news_ranking_on_fixed_dates(S):
    """Spec 1·5·8a: one rule over the data and the build date. 2026-10-10: the 짬뽕 festival runs, so its card leads;
    2026-10-13: no dish festival, PROJECT YOURSIDE 군산 (10.2–10.31) is among the running events; 2026-11-01: the
    October editions are over and none of them is a card."""
    saved = S.today
    try:
        n10 = _check_news(S, "2026-10-10")
        # the pinned fireworks edition's reel leads while that edition is ahead (operator 2026-11-04); then the rule
        assert n10[0]["kind"] == "reel" and n10[0]["href"].startswith("/events/")
        n10 = n10[1:]
        assert n10[0]["kind"] == "festival" and "짬뽕" in n10[0]["title"] and n10[0]["status"].startswith("진행 중")
        assert n10[0]["chip"] == "축제" and n10[0]["href"].startswith("/events/")
        n13 = _check_news(S, "2026-10-13")
        assert "festival" not in [c["kind"] for c in n13]
        # PROJECT YOURSIDE (10.2–10.31) is a running edition that day; whether it makes the top 3 depends on the
        # editions around it (2026-10-31: pinned fireworks, new exhibitions), so its card is checked on its own
        yr = next(r for r in present.ranked_events(S) if "YOURSIDE" in r["title"])
        yourside = present._event_card(S, yr)
        assert yourside["kind"] == "event" and yourside["status"] == "진행 중 · 10.31.까지"
        assert yourside["when"] == "10. 2.–10. 31."
        on_home = next((c for c in n13 if c["key"] == yourside["key"]), None)   # home_news gives the cards their photos
        assert on_home is None or on_home["photo"]["place"] == "군산항1981"
        assert [c["chip"] for c in n13 if c["kind"] == "abroad"][0] == "해외에서 본 군산"
        n11 = _check_news(S, "2026-11-01")
        assert not any(c["key"] == yourside["key"] for c in n11)
        assert not any(c["kind"] == "event" and c["status"].endswith("10.31.까지") for c in n11)
    finally:
        S.today = saved


MUSEUM_EV = "fest-군산근대역사박물관-주말상설행사-2026"


def test_an_end_given_only_as_a_month_is_never_shown_as_its_last_day(S):
    """QA 2026-10-15 SRC-06: the museum's weekend programme runs '2026. 6. 6. ~ 10월' — the source gives no end day.
    The month's last day (build.event_last_day) only sorts and splits upcoming / past: the chip, the big date, the home
    card and the event page say '10월', never '10.31.'; the page asks for the end day; JSON-LD has no endDate.
    PROJECT YOURSIDE (end_date 2026-10-31 in its source) keeps its day."""
    from pipeline.build import event_end_month, event_last_day
    saved = S.today
    try:
        S.today = "2026-10-13"
        ev = next(x for x in S.events if x.get("id") == MUSEUM_EV)
        assert event_end_month(ev) == "2026-10" and event_last_day(ev) == "2026-10-31"
        r = next(x for x in present.ranked_events(S) if x["ev"] is ev)
        assert r["chip"] == "진행 중 · 10월 중 끝남"
        assert r["dp"]["b"] is None and r["dp"]["end_month"] == "10"
        card = present._event_card(S, r)   # the home's event card for this edition (whether or not it makes the top 3)
        assert card["status"] == "진행 중 · 10월 중 끝남" and card["when"] == "6. 6.–10월"
        shown = " ".join(str(card.get(k) or "") for k in ("title", "when", "when_iso", "sub", "status", "chip"))
        assert "10.31" not in shown and "10. 31." not in shown
        sr = next(x for x in S.series if x["newest"] is ev)
        vm = present.event_vm(S, sr)
        assert vm["need"][0] == "끝나는 날" and vm["chip"] == "진행 중 · 10월 중 끝남" and vm["dp"]["b"] is None
        assert "endDate" not in json.dumps(jsonld.event_graph(ev, "https://x/events/a/", [], S.site), default=str)
        # an end day the source gives stays a day
        y = next(x for x in present.ranked_events(S) if "YOURSIDE" in x["title"])
        assert y["chip"] == "진행 중 · 10.31.까지" and y["dp"]["b"]["md"] == "10. 31."
        assert "끝나는 날" not in present.event_vm(S, next(x for x in S.series if x["newest"] is y["ev"]))["need"]
    finally:
        S.today = saved


def test_event_places_split_the_place_name_and_match_contentid(S):
    """Spec 8a: '군산회관, 군산항1981' (a string, no contentid) finds 군산항1981 by name; a TourAPI contentid finds its
    place; brackets and a trailing 일원 are dropped."""
    place = S.ent_by_slug["군산항1981"]
    assert present.event_places(S, {"place_name": "군산회관, 군산항1981"}) == [place]
    assert present.event_places(S, {"place_name": f"전북특별자치도 군산시 {place['name']}(장미동) 일원"}) == [place]
    cid, by_cid = next(iter(S.ent_by_cid.items()))
    assert present.event_places(S, {"place_name": "", "contentid": cid}) == [by_cid]
    assert present.event_places(S, {"place_name": "어딘가 없는 곳"}) == []


def test_home_news_pictures_are_allowed_ones(S):
    """Spec 1·5: a card's picture is a licensed TourAPI photo of an attraction it is about (KOGL-1/3, never a
    business's), an /abroad/ article's own preview image on that article's card, or the kind's AI picture; a video
    card never shows a YouTube thumbnail; no photo is shown twice."""
    from pipeline.validate import TOURAPI_IMAGE_HOSTS
    saved = S.today
    by_name = {e["name"]: e for e in S.entities}
    images = {a["id"]: a.get("image") for a in S.abroad}
    try:
        for day in ("2026-10-10", "2026-10-13", "2026-11-01"):
            S.today = day
            shown = []
            for c in present.home_news(S):
                ph = c["photo"]
                if ph:
                    e = by_name[ph["place"]]
                    assert e["kind"] == "attraction" and ph["type"] in (1, 3)
                    assert ph["url"].startswith(TOURAPI_IMAGE_HOSTS) and ph["url"] in [p["url"] for p in e["_photos"]]
                    shown.append(ph["url"])
                if c["og"]:
                    assert c["kind"] == "abroad" and not ph and c["og"] == images[c["key"][3:]]
                    assert c["og"].startswith("https://") and c["outlet"]
                if c["art"]:
                    assert not (ph or c["og"])
                    kind = (f"events.kind.{c['ev_kind']}",) if c["kind"] in ("event", "festival") else ()   # K
                    assert c["art"]["slot"] in (f"home.card.{c['kind']}", "home.card.event", "home.card.festival-jjamppong",
                                                *kind)
                if c["kind"] == "video":
                    assert not (ph or c["og"])
            assert len(shown) == len(set(shown)), day
    finally:
        S.today = saved


def test_home_opening_markup_carousel_and_links(S, built):
    """UI4 (owner 2026-10-14, '참고 사이트처럼 밝게'): the Korean home opens LIGHT — no full-bleed photo, no scrim. The
    opening holds the eyebrow pill, the H1, one lede, the sea pill button and the slide controls (the pause button
    first, previous / next, the counter 'n / N' not live while it turns, the progress line, '소식 전체'), and at the
    right one big card per news item (present.home_news): a labelled carousel of groups 'i / N', each with exactly one
    working link and an allowed picture with its credit (an illustration: alt only, no label). The first slide's photo
    is eager, high priority and preloaded; the others lazy. Then the white card, the AI assistant only (owner
    2026-10-14: '페이지 상단에는 검색, 중앙 부분에는 AI챗봇'): its heading, one GET form to /search/ (without JS it
    searches) with ONE button '물어보기' and no '검색', the starter questions as '#' tags linking to pages of this
    build, and the 3D icon menu of the service links (no 물어보기 item: the card above it is the assistant; pictures by
    registry ID); the conversation panel right after the card, empty and hidden. The site search is the header's: a
    GET form to /search/ in the bar, and no '물어보기' button in the bar."""
    from urllib.parse import unquote
    html = (built / "index.html").read_text("utf-8")
    # 시안 A (operator 2026-11-05): the H1 describes the site, '모든 것' in the sea blue; the name 군산각 stays in the bar,
    # the footer, the title and JSON-LD
    assert '<h1 id="h-home" class="op-h1 ha-h1">군산 여행의 <span class="ha-em">모든 것</span></h1>' in html
    assert 'class="wm-a">군산<span class="wm-em">각</span></span>' in html   # 각 in the site blue (operator 2026-10-17)
    start = html.index('<div class="hk" data-chat-dock>')
    top = html[start:html.index('<section class="sec ', start)]
    opening = top[:top.index('<section class="hq"')]
    assert re.match(r'<div class="hk" data-chat-dock>\s*<section class="ha" aria-labelledby="h-home">', opening)
    # the card over the 고군산군도 photo (operator 2026-11-05 '흰색 배경 말고, 고군산군도 고화질 사진을 배경으로'): the
    # official KOGL-1 cover (cropping allowed), credited, its local AVIF derivative the one image preloaded
    head = html[:html.index("</head>")]
    assert '<div class="ha-card ha-ph">' in opening and "ho-dot" not in html
    bg = opening[opening.index('<div class="ha-bg" aria-hidden="true">'):]
    assert 'data-kogl="1"' in bg.split("</div>", 1)[0] and 'class="ha-cap"' in opening and "공공누리 제1유형" in opening
    pre = re.findall(r'<link rel="preload" as="image"[^>]*>', head)
    assert len(pre) == 1 and 'type="image/avif"' in pre[0] and 'imagesrcset="/assets/media/' in pre[0], pre
    # the site search, big: a GET form to /search/ with one button '검색'
    form = opening[opening.index('<form class="ha-search"'):opening.index("</form>")]
    assert 'action="/search/" method="get" role="search"' in form and 'name="q" type="search"' in form
    assert re.findall(r"<button [^>]*>([^<]*)</button>", form) == ["검색"]
    # the four core lists, each with its picture — no counts (operator 2026-11-05: '숫자는 다 빼는 게 좋을 것 같아')
    assert re.findall(r'<a class="ha-tile ha-[a-z]" href="([^"]+)"', opening) == ["/places/", "/food/", "/stays/", "/courses/"]
    assert re.findall(r'<span class="ha-tl">([^<]+)</span>', opening) == ["관광지", "음식점", "숙소", "코스"]
    assert "ha-tn" not in opening and opening.count('data-pic="icon-') >= 4
    assert re.search(r'<a class="ha-btn ha-stay"[^>]*>.*?<span>숙박 예약하기</span></a>', opening, re.S)
    # 숙박 예약하기 and the planner (the city's courses: the 코스 tile and the bar's '추천 코스')
    assert '<a class="ha-btn ha-stay" href="/stays/booking/" data-track="stay_booking_cta">' in opening
    assert '<a class="ha-btn ha-plan" href="/plan/" data-track="plan_cta">AI 코스 만들기</a>' in opening
    # the pinned fireworks edition while it is ahead: the banner (D-day, the event page, the reel — the dialog plays the
    # post, nothing from Instagram before) and the series' guides, each a page of this build
    if '<section class="ha-fest"' in opening:
        fest = opening[opening.index('<section class="ha-fest"'):]
        assert 'data-dday="' in fest and 'data-track="fest_click"' in fest and "data-reel-open" in fest
        assert "instagram.com/embed" not in fest and "불꽃 장면은 자료화면" in fest
        guides = re.findall(r'<li><a href="([^"]+)" data-track="guide_click">', fest)
        assert 1 <= len(guides) <= 3
        for href in guides:
            assert (built / unquote(href).strip("/") / "index.html").exists(), href
    # the news row, after the assistant: a labelled carousel of groups 'i / N', the controls under the cards
    news_sec = top[top.index('<section class="hn"'):]
    assert re.search(r'<div class="hn-in" data-hcar aria-roledescription="carousel" aria-label="지금 군산 소식">', news_sec)
    n = news_sec.count('aria-roledescription="slide"')
    assert present.NEWS_MIN <= n <= present.NEWS_MAX
    assert re.findall(r'role="group" aria-roledescription="slide" aria-label="(\d+) / (\d+)"', news_sec) == \
        [(str(i), str(n)) for i in range(1, n + 1)]
    ctl = news_sec[news_sec.index('<div class="ho-ctl">'):news_sec.index('</section>')]
    buttons = re.findall(r"<button [^>]*>", ctl)
    assert len(buttons) == 3 and "data-hcar-pause" in buttons[0] and 'aria-label="소식 자동 넘김 멈추기"' in buttons[0]
    assert 'data-hcar-dir="-1" aria-controls="hv-track" aria-label="이전 소식"' in buttons[1]
    assert 'data-hcar-dir="1" aria-controls="hv-track" aria-label="다음 소식"' in buttons[2]
    assert f'data-hcar-count aria-live="off"><span class="vh">소식 </span><span data-hcar-cur>1</span> / {n}</p>' in ctl
    assert '<i data-hcar-prog></i>' in ctl and '<a class="ho-all" href="/events/">' in ctl
    news = news_sec[news_sec.index('<div class="ho-news">'):news_sec.index('<div class="ho-ctl">')]
    assert 'aria-live="polite"' not in news and 'id="hv-track"' in news
    for i, card in enumerate(news.split('<article class="nc nc-')[1:]):
        links = re.findall(r'<a href="([^"]+)"([^>]*)>', card)
        assert len(links) == 1, card[:120]
        href, attrs = links[0]
        if href.startswith("/"):
            assert (built / unquote(href).strip("/") / "index.html").exists(), href
        else:
            assert href.startswith("https://") and 'rel="noopener"' in attrs, href
        for img in re.findall(r"<img [^>]*>", card):
            src = re.search(r' src="([^"]+)"', img).group(1)
            if src.startswith("/assets/art/"):    # the card kind's picture; an event's may be its event kind's (K)
                kind_art = card.startswith(("event", "festival")) and 'data-art="evkind-' in card
                assert ('data-art="card-' in card or kind_art) and 'alt="일러스트: ' in img
                assert "AI 생성 이미지" not in card and "<figcaption" not in card   # owner 2026-10-13: no label
            elif 'class="nc-og"' in img:
                assert card.startswith("abroad") and "미리보기 이미지</p>" in card
                assert 'referrerpolicy="no-referrer"' in img and 'alt=""' in img
            elif src.startswith("/assets/icons/"):
                assert 'alt=""' in img
            elif src.startswith("/assets/reel/"):    # operator 2026-11-04: the pinned edition's reel as slide 1 — a
                # still of the operator's own post, the post itself only after a tap (no Instagram request before)
                assert i == 0 and card.startswith("reel") and "data-reel-open" in card and 'alt=""' not in img
                assert "instagram.com/embed" not in card
            else:
                assert src.startswith("https://tong.visitkorea.or.kr/") and "출처: 한국관광공사" in card
            assert 'loading="lazy"' in img and "width=" in img and "height=" in img   # below the first screen now
    card = top[top.index('<section class="hq"'):]
    assert card.startswith('<section class="hq" aria-labelledby="h-ask">')
    assert '<h2 id="h-ask" class="hk-h"><span class="hk-hn">군산 여행 도우미에게</span> 물어보세요</h2>' in card
    form = card[card.index('<form class="hk-box"'):card.index("</form>")]
    assert form.startswith('<form class="hk-box" action="/search/" method="get" data-ask-form="search" data-empty="')
    assert 'id="ask-q" name="q"' in form and 'maxlength="800"' in form and 'data-ask-q' in form
    buttons = re.findall(r"<button [^>]*>", form)
    assert buttons == ['<button type="submit" class="ask-go hk-go" data-ask-go>']   # one button, no '검색'
    assert '<span class="ask-go-l">물어보기</span><span class="ask-go-l ask-go-s">멈추기</span>' in form
    assert "data-ask-search" not in html and "formaction" not in card
    # the header: the site search (a GET form to /search/), no '물어보기' button in the bar
    mast = html[html.index('<header class="mast"'):html.index("</header>")]
    assert '<form class="hs" id="hs" action="/search/" method="get" role="search" data-hs>' in mast
    assert 'placeholder="장소·음식·지역 검색"' in mast and 'name="q" type="search"' in mast
    assert '<a class="mast-search" href="/search/" data-hs-open>' in mast
    assert "data-chat-open" not in mast and "mast-ask" not in mast and "물어보기" not in mast
    chips = re.findall(r'<a class="hk-pill" href="([^"]+)" data-ask="([^"]+)">', card)
    assert 3 <= len(chips) <= 5
    for href, q in chips:
        assert (built / unquote(href).strip("/") / "index.html").exists(), href
    assert 'class="hk-mascot"' in card and 'alt=""' in card.split('class="hk-mascot"', 1)[1][:400]
    # the 3D icon menu: every service link, each with its picture ID — no '물어보기' item (the card above is the
    # assistant, and the launcher is on screen too)
    menu = card[card.index('<nav class="hq-menu"'):card.index("</nav>")]
    assert "data-chat-open" not in menu and "icon-ask" not in menu and "<button" not in menu
    for href, pid in (("/food/", "icon-food"), ("/stays/", "icon-stay"), ("/places/", "icon-sights"),
                      ("/courses/", "icon-course"), ("/events/", "icon-events"), ("/map/", "icon-map"),
                      ("/videos/", "icon-video"), ("/abroad/", "icon-abroad"), ("/blog/", "mascot-camera")):
        assert re.search(rf'<a class="hq-i" href="{href}"[^>]*><span class="pic [^"]*" data-pic="{pid}"', menu), href
    services = present.home_services(S)
    assert menu.count("<li ") == len(services)
    assert '<a class="hq-i" href="/guides/' in menu and 'data-pic="icon-getting-here"' in menu
    # operator 2026-10-15: the core four lead (one row of four tiles on phones, css/46-home-open.css), then the rest
    labels = re.findall(r'<span class="hq-l">([^<]+)</span>', menu)
    assert labels == [s["label"] for s in services]
    assert labels[:4] == ["가볼만한 곳", "맛집", "숙소", "가는 법"]
    assert labels[4:] == ["코스", "칼럼", "지도", "행사 달력", "영상", "해외에서 본 군산", "블로그"]   # 블로그: operator 2026-10-30
    assert re.findall(r'<li class="(hq-core|hq-more)">', menu) == ["hq-core"] * 4 + ["hq-more"] * 7
    assert '<ul class="hq-row hq-m1" style="--core:4">' in menu   # 7 tiles on phones: 3 · 2 · 2 (css/46-home-open.css)
    # the conversation: right after the card, hidden and empty until the reader asks (chat.js draws into it)
    rest = card[card.index("</section>") + len("</section>"):]
    assert rest.startswith('\n<div class="wrap hk-conv"><div class="ask-log ask-panel" data-ask-log hidden '
                           'data-ask-more="이어서 물어보기" data-note="AI가 이 사이트의 정보로 쓴 답입니다. 틀릴 수 있으니 '
                           '방문 전에 확인하세요."')
    assert "AI 생성 이미지" not in html and 'class="hv ' not in html and "hv-top" not in html and 'class="svc' not in html


def test_home_first_screen_tells_the_planner_from_the_citys_courses(S, built):
    """Operator-forwarded evaluation 2026-10-18: '공식 코스 보기' and the header's course entry led to the city's
    courses while the AI planner came further down, so a first visitor could not tell 공식 코스 from 맞춤 코스. The
    opening now names both actions side by side — '내 일정 만들기' (/plan/) and '군산시 추천 코스' (/courses/) — then
    three situational entries in words (the first-visit guide, the planner, the map), every link to a page of this
    build with its GA4 event; no picture is added to the first screen. The header's course button reads '추천 코스'
    (the planner keeps 'AI 코스'), and so does a guide's local-bar pill."""
    from urllib.parse import unquote
    html = (built / "index.html").read_text("utf-8")
    opening = html[html.index('<section class="ha"'):html.index('<section class="hq"')]
    text = opening[:opening.index('<section class="ha-fest"')] if '<section class="ha-fest"' in opening else opening
    # 시안 A (operator 2026-11-05): the card names the planner ('내 일정 만들기', /plan/) and the city's courses as the
    # 코스 tile (/courses/); the bar keeps '추천 코스'
    assert '<a class="ha-btn ha-plan" href="/plan/" data-track="plan_cta">AI 코스 만들기</a>' in text
    assert re.search(r'<a class="ha-tile ha-c" href="/courses/"[^>]*>', text) and '<span class="ha-tl">코스</span>' in text
    assert "공식 코스 보기" not in html
    starts = present.home_starts(S)
    guide = next(g for g in S.guides if g["title"].startswith(present.FIRST_VISIT_TITLE.format(region="군산")))
    assert [(s["label"], s["href"], s["track"]) for s in starts] == [
        ("처음 가는 군산", guide["_path"], "guide_click"), ("내 조건으로 코스 만들기", "/plan/", "plan_cta"),
        ("지도에서 찾기", "/map/", "")]
    # review 2026-10-18: the map entry says what /map/ is — every place on one map; the page knows no reader's place,
    # so nothing claims 'near you'
    assert "가까운 곳" not in text and "내 주변" not in text
    map_page = (built / "map" / "index.html").read_text("utf-8")
    assert "geolocation" not in map_page and re.search(r'<h1[^>]*>군산 지도', map_page)
    for href in ["/plan/", "/courses/"] + [s["href"] for s in starts]:
        assert (built / unquote(href).strip("/") / "index.html").exists(), href
    # the header: the course button says whose courses they are; the planner's own door keeps its name
    mast = html[html.index('<header class="mast"'):html.index("</header>")]
    assert '<a class="mast-ctx" href="/courses/" data-track="course_click">추천 코스</a>' in mast
    assert '<span>AI 코스</span>' in mast and "코스 보기" not in mast
    assert present.page_chrome("home", True)["ctxbtn"] == ("추천 코스", "/courses/")
    assert present.page_chrome("home", False)["ctxbtn"] is None
    g = (built / unquote(S.guides[0]["_path"]).strip("/") / "index.html").read_text("utf-8")
    assert "코스 보기" not in g and ('>추천 코스<' in g or 'href="#h-route"' in g)
    # without the first-visit guide, the entry is the guide index; without guides or places, entries drop out
    from types import SimpleNamespace
    other = SimpleNamespace(site=S.site, guides=[x for x in S.guides if x is not guide], entities=S.entities)
    assert present.home_starts(other)[0] == {"label": "처음 가는 군산", "href": "/guides/", "track": "guide_click"}
    assert present.home_starts(SimpleNamespace(site=S.site, guides=[], entities=[])) == []


def test_english_home_takes_the_korean_opening(S, built):
    """Owner 2026-10-14 ('외국어 사이트들은 UI UX가 아직 업데이트가 안 됐네'): the English home opens as the Korean one —
    media.HOME_COVER full-bleed under its scrim with its credit, the H1, the course button, the news cards (this
    version's events and guides, Pages.home_news) and the white card with the assistant and the icon menu, all in
    English; the old light opening (.hx) and its see-through masthead rules are gone."""
    en = (built / "en" / "index.html").read_text("utf-8")
    cover = present.media.slot_photos(S)["cover"]
    assert present.media.HOME_COVER == ("고군산군도", 0) and cover and cover["type"] == 1 and cover["avif"]
    assert '<body data-page-kind="home" class="pg-home pg-intl-home pg-h4 has-ask">' in en
    assert '<section class="ho ho-ph" aria-labelledby="h-home">' in en and f'src="{cover["url"]}"' in en
    assert 'rel="preload" as="image" type="image/avif"' in en and "Start with an official course" in en
    assert '<p class="ho-cap">Photo: ' in en and 'class="hx' not in en
    top = en[en.index('<div class="hk" data-chat-dock>'):en.index('<section class="sec ')]
    cards = re.findall(r'<article class="nc nc-(\w+)"', top)
    assert len(cards) >= 2 and set(cards) <= {"festival", "event", "guide"}
    for href in re.findall(r'<h3 class="nc-t"><a href="([^"]+)"', top):
        assert href.startswith("/en/"), href
    assert "data-hcar" in top and '<nav class="hq-menu"' in top and not re.search(r"[가-힣]", top)
    # operator 2026-10-15: the core four lead the menu as on the Korean home — attractions, restaurants, stays and
    # the 'getting there' guide (its long label has a short one for phones) — then courses, events, guides
    menu = top[top.index('<nav class="hq-menu"'):]
    menu = menu[:menu.index("</nav>")]
    items = re.findall(r'<li class="(hq-core|hq-more)"><a class="hq-i" href="([^"]+)"', menu)
    assert [c for c, _ in items] == ["hq-core"] * 4 + ["hq-more"] * (len(items) - 4)
    assert [h for _, h in items][:3] == ["/en/places/", "/en/food/", "/en/stays/"]
    assert items[3][1].startswith("/en/guides/") and [h for _, h in items][4:] == ["/en/courses/", "/en/events/",
                                                                                      "/en/guides/", "/en/columns/"]
    assert ('<span class="hq-l"><span class="hq-lw">Getting to Gunsan and around</span>'
            '<span class="hq-ls">Getting here</span></span>') in menu
    css = (built / "assets" / "style.css").read_text("utf-8")
    assert ".pg-en-home" not in css and "html:not(.is-scrolled) .pg-home .mast{" not in css


def test_homes_ask_in_place(built):
    """Owner 2026-10-13: ask the site assistant from the home itself. The Korean home asks from its question card (UI4,
    owner 2026-10-14: the white card under the light opening) — one dock (data-chat-dock on the home's top), the box in
    the card, the conversation panel right under it, no centre card; the English home the same (owner 2026-10-14).
    Every starter links to a page of this build, in the page's language."""
    from urllib.parse import unquote
    ko = (built / "index.html").read_text("utf-8")
    assert ko.count("data-chat-dock") == 1 and '<div class="hk" data-chat-dock>' in ko
    assert '<section class="ask' not in ko and 'class="ask-card"' not in ko
    start = ko.index('<div class="hk" data-chat-dock>')
    top = ko[start:ko.index('<section class="sec ', start)]
    # 시안 A (operator 2026-11-05): the white card, the fireworks banner and guides, then the assistant, then the news row
    assert top.index('<section class="ha"') < top.index('<section class="hq"') < top.index('<form class="hk-box"') \
        < top.index('<nav class="hq-menu"') < top.index("data-ask-log") < top.index('data-hcar-item')
    en = (built / "en" / "index.html").read_text("utf-8")
    # owner 2026-10-14: the English home asks from the same white card (_ask.html.j2 box_intl): no search page in
    # English, so its form shows with JS only (data-js-only); no centre card any more
    assert en.count("data-chat-dock") == 1 and '<div class="hk" data-chat-dock>' in en and 'class="ask-card"' not in en
    start = en.index('<div class="hk" data-chat-dock>')
    en_top = en[start:en.index('<section class="sec ', start)]
    assert en_top.index('<section class="ho') < en_top.index('<section class="hq"') \
        < en_top.index('<form class="hk-box" method="get" data-ask-form data-js-only data-empty="') \
        < en_top.index('<nav class="hq-menu"') < en_top.index("data-ask-log")
    assert "Ask the Gunsan travel helper" in en_top and not re.search(r"[가-힣]", en_top)
    for html, prefix in ((top, "/"), (en_top, "/en/")):
        chips = re.findall(r'<a class="hk-pill" href="([^"]+)" data-ask="([^"]+)">', html)
        assert len(chips) >= 3, prefix
        for href, q in chips:
            assert href.startswith(prefix) and (built / unquote(href).strip("/") / "index.html").exists(), href


def test_home_news_row_turns_by_itself_and_stops_for_the_reader(built):
    """The home's news row in a browser (Playwright + Chromium; the build is served through page.route, nothing leaves
    the machine). 시안 A (operator 2026-11-05): the first screen at 390 and 1440 is the opening card — the H1, the
    search, the four lists and the two buttons — and the news row is a section of its own ('지금 군산 소식') under the
    question card. Exactly one news card is in view at a time (a compact card on phones, the picture at the left of
    the words at both sizes); from 768px the row advances by itself while it is on screen, a control press stops it
    (the play button restarts it, the counter is live only while stopped), focus inside stops it; on phones it waits
    on its first card; with reduced motion there is no autoplay and no pause button; without JS the controls are
    hidden, one card is still in view, the cards still scroll and the question box searches."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if url.startswith("https://weather.o2o.kr/"):   # the tab panel's weather module (tests/conftest.py)
            return route.fulfill(status=200, body=json.dumps(weather_answer()), content_type="application/json",
                                 headers={"access-control-allow-origin": "*"})
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            def open_home(width=1440, height=900, **kw):
                ctx = browser.new_context(viewport={"width": width, "height": height}, **kw)
                ctx.route("**/*", serve)
                page = ctx.new_page()
                page.goto("http://site.test/", wait_until="load")
                return ctx, page
            in_view = """(() => { const v = document.querySelector('[data-hcar-view]').getBoundingClientRect();
              return [...document.querySelectorAll('[data-hcar-item]')].filter(c => { const r = c.getBoundingClientRect();
                return r.right > v.left + 1 && r.left < v.right - 1 && r.width > 0; }).length; })()"""
            in_screen = """(sel => { const r = document.querySelector(sel).getBoundingClientRect();
              return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; })"""
            opening = (".ha-h1", ".ha-search", ".ha-tiles", ".ha-cta")
            order = """(() => { const t = s => document.querySelector(s).getBoundingClientRect();
              return t('.ha-card').bottom <= t('.hq-card').top && t('.hq-card').bottom <= t('.hn-h').top
                && t('.hn-h').bottom <= t('[data-hcar-view]').top; })()"""
            side_by_side = """(() => { const f = document.querySelector('[data-hcar-item] .nc-frame')
              .getBoundingClientRect(), t = document.querySelector('[data-hcar-item] .nc-t').getBoundingClientRect();
              return [f.width, f.right <= t.left]; })()"""
            ctx, page = open_home(390, 844)                          # phones
            assert page.evaluate(in_view) == 1
            # the first screen: the opening card whole — the H1, the search, the four lists, the two buttons on one
            # row (44px targets)
            for sel in opening:
                assert page.evaluate(in_screen + f"('{sel}')"), sel
            pair = page.evaluate("[...document.querySelectorAll('.ha-cta .ha-btn')].map(a => { const r = a.getBoundingClientRect();"
                                 " return [r.top, r.height, r.right]; })")
            assert len(pair) == 2 and pair[0][0] == pair[1][0] and min(h for _, h, _ in pair) >= 44
            # the news row: a section of its own, named by its heading, under the question card; the compact card
            # waits on its first card (no autoplay below 768px)
            assert page.evaluate(order) and page.inner_text(".hn-h") == "지금 군산 소식"
            assert page.evaluate("document.documentElement.scrollWidth") == 390
            assert page.evaluate("document.querySelector('[data-hcar-view]').getBoundingClientRect().height") < 200
            frame_w, beside = page.evaluate(side_by_side)
            assert frame_w <= 96 and beside
            assert "is-stopped" in page.get_attribute("[data-hcar]", "class")
            assert page.get_attribute("[data-hcar-pause]", "aria-label") == "소식 자동 넘김 시작"
            assert page.text_content("[data-hcar-cur]") == "1"
            ctx.close()
            ctx, page = open_home()
            box, cur = "[data-hcar]", "[data-hcar-cur]"
            # 1440: the opening card whole in the first screen; the news row under the question card — one feature
            # card (the picture at the left of the words) that fits a screen with its controls
            for sel in opening:
                assert page.evaluate(in_screen + f"('{sel}')"), sel
            assert page.evaluate(order) and page.inner_text(".hn-h") == "지금 군산 소식"
            page.wait_for_timeout(1500)
            assert page.text_content(cur) == "1"                     # it has not turned while off screen
            page.evaluate("document.querySelector('.hn').scrollIntoView({block: 'center'})")   # the reader comes to it
            page.wait_for_timeout(700)
            assert page.evaluate(in_screen + "('.hn-h')") and page.evaluate(in_screen + "('[data-hcar]')")
            frame_w, beside = page.evaluate(side_by_side)
            assert frame_w >= 300 and beside
            assert page.evaluate(in_view) == 1
            assert page.text_content(cur) == "1"
            assert page.get_attribute("[data-hcar-pause]", "aria-label") == "소식 자동 넘김 멈추기"
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "off"
            page.wait_for_function("document.querySelector('[data-hcar-cur]').textContent === '2'", timeout=10000)
            page.wait_for_timeout(900)                               # let the smooth scroll settle
            assert page.evaluate(in_view) == 1                       # one card again, the next one
            page.click('[data-hcar-dir="1"]')                       # a control press: one on, autoplay stops
            page.wait_for_function("document.querySelector('[data-hcar-cur]').textContent === '3'", timeout=4000)
            assert "is-stopped" in page.get_attribute(box, "class")
            assert page.get_attribute("[data-hcar-pause]", "aria-label") == "소식 자동 넘김 시작"
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "polite"
            page.click("[data-hcar-pause]")                          # play again
            assert "is-stopped" not in page.get_attribute(box, "class")
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "off"
            page.focus(".nc-t a")                                     # focus inside: stops for good
            assert "is-stopped" in page.get_attribute(box, "class")
            ctx.close()
            ctx, page = open_home(reduced_motion="reduce")
            assert page.locator("[data-hcar-pause]").count() == 0 and "is-stopped" in page.get_attribute(box, "class")
            assert page.get_attribute("[data-hcar-count]", "aria-live") == "polite"
            ctx.close()
            ctx, page = open_home(java_script_enabled=False)
            assert not page.is_visible(".hv-ctl") and page.evaluate(in_view) == 1
            assert page.evaluate("(() => { const v = document.querySelector('[data-hcar-view]');"
                                 " return v.scrollWidth > v.clientWidth; })()")
            # without JS the question box searches
            page.fill("#ask-q", "선유도")
            page.press("#ask-q", "Enter")
            page.wait_for_url("**/search/?q=*")
            ctx.close()
        finally:
            browser.close()


def test_launcher_and_quick_menu_are_there_at_load(built):
    """Owner 2026-10-14 ('첫 화면부터 우측 하단에 챗봇 잘 보이게 해주고. 지금은 스크롤 해야만 보이거든'): at load, without
    scrolling, the mascot launcher is visible at the bottom right — fully on screen, opaque, on top (the point at its
    centre is the launcher) — on the home, a place page and /en/, at 390×844 and 1440×900. On the Korean pages from
    1024px the floating quick menu sits above it (44px targets with their names; on a place page its third item is
    길찾기, the page's own block); phones show only the launcher; /en/ has no quick menu. No layout shift while the home
    loads (fonts cached, as on any second page), no console errors, and no 'AI 생성 이미지' anywhere on screen.
    Operator 2026-10-15: on the homes below 1024px the launcher steps aside while their own question box is on screen
    (hidden, out of the tab order) and is there as above once the box has left the screen.
    Operator 2026-11-05 (시안 A): on a Korean phone page the bottom bar stands for the launcher — the tab bar's 'AI 챗봇'
    button, and on a place page the call/route bar's (the calm pass 2026-11-10: the launcher above that bar covered
    the phone tile and the photo credit). The calm pass 2026-11-10 (css/90-refine): from 1200px — the pages with the
    tab panel, which holds the search and every list — the launcher is 68px inside the page's right margin and the
    quick menu is its last link only, '맨 위로'; at 1024–1199px the pill and the 100px launcher stay."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if url.startswith("https://weather.o2o.kr/"):   # the tab panel's weather module (tests/conftest.py)
            return route.fulfill(status=200, body=json.dumps(weather_answer()), content_type="application/json",
                                 headers={"access-control-allow-origin": "*"})
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    shifts = """window.__ls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput)
      window.__ls.push(e.value); }).observe({type: 'layout-shift', buffered: true});"""
    fab_ok = """(() => { const b = document.querySelector('.chat-fab'), r = b.getBoundingClientRect(), cs = getComputedStyle(b);
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return r.width >= 54 && r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth
        && r.right > innerWidth - 60 && r.bottom > innerHeight - 60 && cs.visibility === 'visible' && cs.opacity === '1'
        && b.contains(hit); })()"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            for w, h in ((390, 844), (1440, 900)):
                for path in ("/", "/places/이성당/", "/en/"):
                    ctx = browser.new_context(viewport={"width": w, "height": h})
                    ctx.route("**/*", serve)
                    page = ctx.new_page()
                    errors = []
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script(shifts)
                    page.goto("http://site.test/about/", wait_until="load")
                    page.evaluate("document.fonts.ready.then(() => 1)")
                    page.goto("http://site.test" + path, wait_until="load")
                    page.wait_for_timeout(300)
                    assert page.evaluate("window.scrollY") == 0
                    shifted = page.evaluate("window.__ls.slice()")      # while the page loaded, before any scrolling
                    box_at_load = True
                    qm = page.locator(".qm")
                    if path != "/en/" and w < 768:
                        # a Korean phone page: the bottom bar's 'AI 챗봇' button, not the floating launcher
                        assert page.evaluate("getComputedStyle(document.querySelector('.chat-fab')).display") == "none", (w, path)
                        bar = ".pl-bar" if path.startswith("/places/") else ".tabbar"
                        chat = page.locator(f"{bar} [data-tab-chat]")
                        assert chat.is_visible() and "AI 챗봇" in chat.inner_text(), (w, path)
                        cb = chat.bounding_box()
                        assert cb["width"] >= 44 and cb["height"] >= 44, (w, path, cb)
                        assert cb["y"] >= h - 110 and cb["y"] + cb["height"] <= h and cb["x"] + cb["width"] <= w, (w, path, cb)
                    elif path in ("/", "/en/"):
                        # on the homes the launcher (and quick menu from 1024px) steps aside while the page's own
                        # question box is on screen — out of the tab order and the pointer's way — and comes back
                        # once the box has left the screen
                        fab_style = "getComputedStyle(document.querySelector('.chat-fab'))"
                        box_at_load = page.evaluate("document.querySelector('[data-ask-zone]').getBoundingClientRect().top") < h
                        if not box_at_load:
                            # the Korean home since 시안 A (operator 2026-11-05): the question box is below the first
                            # screen — the launcher is there at load (once the page has seen that the box is not on
                            # screen: its fade) and steps aside when the box comes on screen
                            page.wait_for_function("document.documentElement.classList.contains('ask-out')", timeout=3000)
                            page.wait_for_timeout(400)
                            assert page.evaluate("window.scrollY") == 0 and page.evaluate(fab_ok), (w, path)
                            page.evaluate("document.querySelector('[data-ask-zone]').scrollIntoView({block: 'center'})")
                            page.wait_for_function("!document.documentElement.classList.contains('ask-out')", timeout=3000)
                            page.wait_for_timeout(400)                     # the fade
                        assert page.evaluate(fab_style + ".visibility") == "hidden", (w, path)
                        assert page.evaluate(fab_style + ".pointerEvents") == "none", (w, path)
                        assert qm.count() == 0 or not qm.is_visible(), (w, path)
                        page.evaluate("window.scrollTo(0, document.querySelector('[data-ask-zone]')"
                                      ".getBoundingClientRect().bottom + scrollY + 40)")
                        page.wait_for_function("document.documentElement.classList.contains('ask-out')", timeout=3000)
                        page.wait_for_timeout(400)                         # the fade
                        assert page.evaluate(fab_ok), (w, path)
                    else:
                        assert page.evaluate(fab_ok), (w, path)
                    if path == "/en/" or w < 1024:
                        assert qm.count() == 0 or not qm.is_visible(), (w, path)
                    else:
                        assert qm.is_visible(), (w, path)
                        items = page.locator(".qm-i")
                        names = [items.nth(i).get_attribute("aria-label") for i in range(items.count())]
                        assert names[0] == "검색" and names[1] == "지도" and names[-1] == "맨 위로"
                        assert names[2] == ("길찾기" if path.startswith("/places/") else "행사 달력")
                        shown = [i for i in range(items.count()) if items.nth(i).is_visible()]
                        # from 1200px the menu is its last link: the panel holds the search, the map and the calendar
                        assert [names[i] for i in shown] == ["맨 위로"], (w, path)
                        for i in shown:
                            bb = items.nth(i).bounding_box()
                            assert bb["width"] >= 44 and bb["height"] >= 44
                        q, f = qm.bounding_box(), page.locator(".chat-fab").bounding_box()
                        assert q["y"] + q["height"] <= f["y"]                     # above the launcher
                        assert f["width"] == 68 and f["height"] == 68, (w, path, f)
                        # both inside the page's right margin: over no part of the content column
                        edge = page.evaluate("document.querySelector('main .wrap').getBoundingClientRect().right"
                                             " - parseFloat(getComputedStyle(document.querySelector('main .wrap')).paddingRight)")
                        assert f["x"] >= edge and q["x"] >= edge, (w, path, edge, f, q)
                        if path.startswith("/places/"):
                            assert page.locator("#h-dir").count() == 1
                    if path in ("/", "/en/") and not (path == "/" and w < 768) and box_at_load:
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_function("!document.documentElement.classList.contains('ask-out')", timeout=3000)
                    if path == "/":
                        assert shifted == [], w                                # nothing shifts while the home loads
                    assert "AI 생성 이미지" not in page.inner_text("body")
                    assert [e for e in errors if "ERR_FAILED" not in e] == [], (w, path, errors)
                    ctx.close()
            # 1024–1199px (no tab panel): the pill with its four links above the 100px launcher, in the page's gutter
            ctx = browser.new_context(viewport={"width": 1100, "height": 800})
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/places/이성당/", wait_until="load")
            page.wait_for_timeout(300)
            items = page.locator(".qm-i")
            assert [items.nth(i).get_attribute("aria-label") for i in range(items.count()) if items.nth(i).is_visible()] \
                == ["검색", "지도", "길찾기", "맨 위로"]
            f = page.locator(".chat-fab").bounding_box()
            assert f["width"] == 100 and f["height"] == 100, f
            ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ events, photos
def test_events_split_upcoming_past_and_undated(S):
    ev = present.events_vm(S)
    assert ev["n_records"] == len(S.events) and ev["n_series"] == len(S.series)
    assert all(r["last"] >= S.today for r in ev["upcoming"]) and all(r["last"] < S.today for r in ev["past"])
    assert all("매년" in r["period_text"] for r in ev["annual"])
    assert len(ev["upcoming"]) + len(ev["past"]) + len(ev["annual"]) + len(ev["textonly"]) + len(ev["past_undated"]) \
        == len(S.events)
    sr = next(s for s in S.series if any(x.get("alternatives") for x in s["editions"] if x is s["newest"]))
    vm = present.event_vm(S, sr)
    assert vm["confirm_line"] == "방문 전 주최 측 확인" and any(r["flag"] for r in vm["rows"])
    flagged = next(r for r in vm["rows"] if r["flag"])
    assert len(flagged["blocks"]) >= 2 and all(b["provider"] for b in flagged["blocks"])


def test_every_licensed_photo_has_its_measured_size(S):
    sizes = json.loads((DATA / "image_sizes.json").read_text("utf-8"))
    photos = [p for e in S.entities for p in e["_photos"]]
    assert photos and all(p["w"] and p["h"] and p["bytes"] for p in photos)
    assert all(sizes[p["url"]][:2] == [p["w"], p["h"]] for p in photos)
    assert all(p["type"] in (1, 3) and "_image3_1" not in p["url"] for p in photos)
    assert sum(1 for p in photos if p["th"]) > len(photos) * 0.9


def test_image_header_parser():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 940, 627) + b"\x08\x02\x00\x00\x00"
    assert image_size(png) == (940, 627)
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 626, 940) + b"\x03" + b"\x00" * 9
    assert image_size(b"\xff\xd8" + app0 + sof) == (940, 626)
    assert image_size(b"\xff\xd8" + app0) is None


# ------------------------------------------------------------------ validator row check
FACTS_PAGE = ('<section data-block="facts"><dl>'
              '<div><dt>쉬는 날</dt><dd data-key="restdate">{a}</dd></div>'
              '<div><dt>주차</dt><dd data-key="parking">{b}</dd></div></dl></section>')
CLOSED = "매주 월요일, 1월 1일, 시장이 휴관일로 정한 날"


def scan(a, b="가능"):
    p = PageScan()
    p.feed(FACTS_PAGE.format(a=a, b=b))
    return p


def old_probe(p, raw):
    return raw[:20] in " ".join(p.blocks["facts"].split())


def test_validator_row_check_is_stricter_than_the_old_prefix_probe():
    assert fact_shown(scan(CLOSED), "restdate", CLOSED)
    # line breaks, a table layout or a closed-day mark do not matter, the words and their order do
    assert fact_shown(scan("매주 월요일,<br>1월 1일, <b>시장이 휴관일로 정한 날</b>"), "restdate", CLOSED)
    cases = {"tail cut after 20 characters": scan(CLOSED[:21]),
             "shown in another row": scan("", CLOSED),
             "a word slipped in": scan(CLOSED.replace("휴관일로 정한", "휴관일로 임시로 정한")),
             "words reordered": scan("1월 1일, 매주 월요일, 시장이 휴관일로 정한 날")}
    for why, p in cases.items():
        assert not fact_shown(p, "restdate", CLOSED), why
    # the old probe (first 20 characters anywhere in the block) let the first three through
    assert all(old_probe(cases[k], CLOSED) for k in ("tail cut after 20 characters", "shown in another row",
                                                     "a word slipped in"))
    # parking compares against the displayed form, never the raw '가능요금 (무료)'
    assert fact_shown(scan("", "가능, 요금 무료"), "parking", "가능요금 (무료)")
    assert not fact_shown(scan("", "가능"), "parking", "가능요금 (무료)")


def test_preview_build_validates_with_the_row_check(built):
    errors, warns, _ = validate(DATA, built, "preview")
    assert without_one_value_prose(errors) == []   # tests/conftest.py
    assert not [w for w in warns if "facts." in w]
    html = (built / "places" / "빈해원" / "index.html").read_text("utf-8")
    assert 'data-key="usetime_restdate"' in html and "10:00–21:00" in html


# ------------------------------------------------------------------ review fixes (r3-wpa review)
def row_page(key, inner):
    p = PageScan()
    p.feed(f'<section data-block="facts"><dl><div><dt>x</dt><dd data-key="{key}">{inner}</dd></div></dl></section>')
    return p


def test_row_check_keeps_symbols_and_the_whole_text():
    """Counter-examples to the first token check, which ignored every symbol: each one passed it while the old
    20-character probe failed. A symbol is a token now, and a value that prints as text must be there verbatim."""
    cases = [("usetime", "~21:00", "21:00"), ("usetime", "10:00~", "10:00"), ("discount", "단체 50%", "단체 50"),
             ("usefee", "₩3,000", "3,000"), ("expagerange", "만 3세+", "만 3세"),
             ("usefee", "성인 3,000원(청소년 2,000원)", "성인 3,000원 청소년 2,000원"),
             ("expguide", "A/B 체험", "A B 체험")]
    for key, value, page in cases:
        p = row_page(key, page)
        assert not fact_shown(p, key, value), (key, value, page)
        assert not old_probe(p, value)                   # the old probe failed these too: nothing is looser
        assert fact_shown(row_page(key, value), key, value)
    # a value inside a longer word is not shown (the old substring probe let '가능' pass in '불가능')
    assert not fact_shown(row_page("parking", "불가능"), "parking", "가능") and old_probe(row_page("parking", "불가능"), "가능")
    assert not fact_shown(row_page("parking", "불<b>가능</b>"), "parking", "가능")
    # a footnote mark right after the value does not hide it
    assert fact_shown(row_page("usetime", "09:00–18:00<sup>1</sup> — 한국관광공사"), "usetime", "09:00~18:00")
    # a value that parses into a price table may lose the layout punctuation its cells replace — nothing else
    fee = "[개별권]\n- 성인 2,000원\n- 어린이 500원"
    assert present.value_view("usefee", fee)["fees"]
    table = '<table data-form="fees"><tr><th>개별권</th></tr><tr><td>성인</td><td>2,000원</td></tr><tr><td>어린이</td><td>500원</td></tr></table>'
    assert fact_shown(row_page("usefee", table), "usefee", fee)
    assert not fact_shown(row_page("usefee", table.replace("<td>500원</td>", "")), "usefee", fee)
    # the same cells without the table mark are plain text and must match verbatim
    assert not fact_shown(row_page("usefee", table.replace(' data-form="fees"', "")), "usefee", fee)
    # a value that does not parse gets no table allowance, mark or not
    assert not fact_shown(row_page("usefee", '<table data-form="fees"><tr><td>성인 3,000원 청소년 2,000원</td></tr></table>'),
                          "usefee", "성인 3,000원(청소년 2,000원)")


def test_row_check_requires_the_full_homepage_link():
    url = "https://booking.naver.com/booking/3/bizes/60723"
    shown = display_value("homepage", url)
    assert shown == "booking.naver.com/booking"
    assert fact_shown(row_page("homepage", f'<a href="{url}">{shown}</a>'), "homepage", url)
    assert not fact_shown(row_page("homepage", shown), "homepage", url)                       # text only
    assert not fact_shown(row_page("homepage", f'<a href="https://booking.naver.com/">{shown}</a>'), "homepage", url)


def test_no_value_passes_the_row_check_that_the_old_probe_failed(built):
    """On every place page of the preview build, every stored value and every other source's value: a pass of
    fact_shown implies a pass of the round-2 probe (first 20 characters of the displayed value in the block)."""
    S = State(DATA, "preview")
    checked = 0
    for e in S.entities:
        p = PageScan()
        p.feed((built / e["_path"].strip("/") / "index.html").read_text("utf-8"))
        block = " ".join(p.blocks.get("facts", "").split())
        values = list((e.get("facts") or {}).items()) + [(k, a["value"]) for k, al in (e.get("fact_alternatives") or {}).items()
                                                         for a in al or [] if a.get("value")]
        for k, v in values:
            shown = fact_shown(p, k, v)
            assert shown, (e["name"], k, v)
            assert " ".join(display_value(k, v).split())[:20] in block, (e["name"], k, v)
            checked += 1
    assert checked > 2500


def test_every_dropped_character_is_caught(S):
    """Delete any one non-space character of a displayed value: the row check fails, except a layout mark
    (/ , : ( ) [ ] ※ -) inside a value that prints as a table."""
    from pipeline.textutil import LAYOUT, link_url
    import html as _html
    seen, mutations = set(), 0
    for e, k, v in all_values(S):
        if (k, v) in seen:
            continue
        seen.add((k, v))
        d = display_value(k, v)
        url = link_url(v) if k in ("homepage", "reservationurl") else ""
        view = present.value_view(k, v)
        table = bool(view["tt"] or view["fees"] or view["grid"])

        def page(text):
            inner = _html.escape(text).replace("\n", "<br>")
            inner = f'<a href="{_html.escape(url)}">{inner}</a>' if url else inner
            return row_page(k, f'<div data-form="t">{inner}</div>' if table else inner)
        assert fact_shown(page(d), k, v), (k, v)
        for i, ch in enumerate(d):
            cut = d[:i] + d[i + 1:]
            if ch.isspace() or " ".join(cut.split()) == " ".join(d.split()) or (table and ch in LAYOUT):
                continue
            mutations += 1
            assert not fact_shown(page(cut), k, v), (k, d, i, ch)
    assert mutations > 20000


def test_alternative_homepages_are_linked(built):
    html = (built / "places" / "산들" / "index.html").read_text("utf-8")
    assert 'href="https://booking.naver.com/booking/3/bizes/60723"' in html
    html = (built / "places" / "라마다-군산호텔" / "index.html").read_text("utf-8")
    assert 'href="http://www.ramadagunsan.com/view/index.do"' in html


def test_contested_phone_is_never_the_call_number(S):
    sr = next(s for s in S.series if (s["newest"].get("alternatives") or {}).get("tel"))
    vm = present.event_vm(S, sr)
    row = next(r for r in vm["rows"] if r["field"] == "tel")
    assert row["flag"] and len(row["blocks"]) == 2
    assert all('href="tel:' in str(b["html"]) for b in row["blocks"])        # both numbers, neither picked
    assert not vm["tel"] and not any(r["tel"] for r in vm["rows"])
    # a place whose phone is contested: no call number in the status line, the list cell or a flag line
    e = place(S, "빈해원")
    e2 = {**e, "fact_alternatives": {**(e.get("fact_alternatives") or {}),
                                     "infocenter": [{"value": "063-000-0000", "provider": "x"}]}}
    assert present.settled_phone(e2) == ("", "")
    assert not [x for x in present.status_items(e2, full=True) if x["key"] == "tel"]
    assert present.cell(e2, "tel")["text"] == "출처마다 다름"


def test_events_held_around_this_time_in_an_earlier_year(S, built):
    """Review 2026-10-17 ('행사 달력에 2건뿐'): beside the editions to come, the series whose newest dated edition —
    one or two years ago, nothing newer — began in the next three months of the year, as that edition (its year in
    the title); the page says this year's dates are not in the data, never that it will be held."""
    assert present.season_ahead("2025-10-30", "2026-10-17") == 13
    assert present.season_ahead("2024-11-21", "2026-10-17") == 35
    assert present.season_ahead("2026-03-01", "2026-10-17") is None      # this year's: finished, not 'around this time'
    assert present.season_ahead("2023-11-01", "2026-10-17") is None      # three years back
    assert present.season_ahead("2025-04-01", "2026-10-17") is None      # outside the next three months
    assert present.season_ahead("2024-02-29", "2025-12-30") == 60        # 2월 29일 → 28일
    rows = present.season_rows(S)
    for r in rows:
        assert r["last"] < S.today and present.season_ahead(r["start"], S.today) is not None
        assert r["title"][:4] == r["start"][:4]                          # the edition's year in its title
        assert not any(u["start"] and u["name"] in r["name"] for u in present.events_vm(S)["upcoming"])
    html = (built / "events" / "index.html").read_text("utf-8")
    assert ('id="season"' in html) == bool(rows)
    if rows:
        assert "올해 일정은 아직 이 사이트 자료에 없습니다" in html and "열릴 것" not in html


def test_event_rows_do_not_settle_contested_values(S):
    rows = {r["title"]: r for r in present.events_vm(S)["past"] + present.events_vm(S)["upcoming"]}
    beer = next(r for t, r in rows.items() if "수제맥주" in t and r["ev"].get("alternatives"))
    assert beer["fee"] == "요금 출처마다 다름" and beer["place"] == "장소 출처마다 다름"
    assert set(beer["contested"]) >= {"fee", "place_name"}


def test_status_keeps_the_label_of_a_bare_open_value(S):
    texts = [x["text"] for x in present.status_items(place(S, "홍영장"))]
    assert "없음" not in texts and "휴무일 없음" in texts


def test_open_every_day_inside_the_hours_value_is_read():
    """'11:00~20:00(연중무휴)' and '10:00~21:30 / 연중무휴' are open every day, not 'no data' in the week grid."""
    for raw in ("11:00~20:00(연중무휴)", "10:00~21:30 / 연중무휴", "10:00~20:00 연중무휴"):
        text, _ = present.closed_text({"facts": {"usetime_restdate": raw}})
        assert text == "연중무휴" and present.week_closure(text)["open"]


def test_week_closure_reads_exceptions_feast_clauses_and_nth_words():
    """2026-10-24 SJ-D03 (세종 /chat/docs.json, 한국관광공사 values): '일요일을 제외한' takes Sunday out, '(단, 설·추석 연휴
    기간 중 일요일은 휴관)' is no weekly closure, '첫 번째, 세 번째' is a partial day — the same rules as knowledge.js closedOn.
    군산's own lists split by a comma or a slash keep their n-th (data/gunsan: 압강옥, 군산 공설시장, 아리랑)."""
    lib = "매월 둘째, 넷째 월요일, 일요일을 제외한 관공서의 공휴일 (단, 설·추석 연휴 기간 중 일요일은 휴관), 기타 관장이 필요하다고 인정하는 날"
    assert present.week_closure(lib) == {"days": set(), "partial": {"월"}, "open": False}   # before: days {'일'}
    assert present.week_closure("매월 첫 번째, 세 번째 수요일") == {"days": set(), "partial": {"수"}, "open": False}   # before: days {'수'}
    for t, day in (("매달 2, 4번째 화요일", "화"), ("매월 첫째 / 셋째 일요일", "일"), ("매달 첫째, 셋째 주 월요일", "월"), ("둘째,넷째주 일요일 휴무", "일")):
        assert present.week_closure(t) == {"days": set(), "partial": {day}, "open": False}, t
    # an n-th belongs to its own weekday: the Monday of '5째주 일요일, 4째주 월요일 휴무' is partial, never weekly
    assert present.week_closure("5째주 일요일, 4째주 월요일 휴무") == {"days": set(), "partial": {"일", "월"}, "open": False}
    assert present.week_closure("매주 월요일, 1월 1일")["days"] == {"월"}


def test_glued_weekday_closures_are_read(S):
    """'매주월요일' (no space) is a Monday closure; '공휴일 휴무' is not a Sunday ('일') closure."""
    assert present.closed_days(place(S, "군산-임피역사")) == {"월"}
    assert present.week_closure("휴무일: 매주목요일")["days"] == {"목"}
    assert present.closed_text(place(S, "복성루"))[0] == "일요일,공휴일 휴무"
    assert present.closed_days(place(S, "복성루")) == {"일"}
    g = next(x for x in S.guides if x["id"] == "guide-03")
    week = present.guide_vm(S, g)["week"]
    row = next(r for r in week["rows"] if r["name"] == "일제강점기 군산역사관")
    assert row["cells"][0] == "closed"                      # the guide says all 8 halls close on Mondays
    # a text with no weekday information is unknown in the grid, never 'open every day'
    sky = present.week_grid([place(S, "선유-스카이썬라인"), place(S, "동국사"), place(S, "근대역사박물관"),
                             place(S, "진포해양공원")])
    assert sky["rows"][0]["cells"] == ["na"] * 7


def test_monday_open_filter_needs_every_source_to_say_so(S):
    L = present.list_vm(S, "food")
    flags = {it["name"]: it["flags"]["open_mon"] for g in L["groups"] for it in g["recs"]}
    assert flags["쌍용반점"] is False          # 연중무휴 vs 둘째·넷째주 월요일 (TourAPI)
    assert flags["궁전갈치찜"] is False        # '전화문의' states no closed day
    assert flags["완주옥"] is True             # 연중무휴 vs 매주 수요일: Monday open in both
    assert flags["장국명가"] is True           # '매주일요일 휴무'


def test_guide_figure_is_never_part_of_a_compound_amount():
    g = {"body": [{"heading": "서울 센트럴시티→군산 고속버스는 2시간30분, 금호고속 운행분은 하루 23회"}], "title": "t"}
    a = present.guide_answer(g)
    assert (a["fig"], a["unit"]) == ("23", "회")


def test_thumb_uses_the_smallest_kogl1_derivative_when_the_provider_has_no_small_copy():
    # a TourAPI photo-gallery picture (KOGL-1, 1280 px) has no provider small copy: a list row gets our 480w WebP
    base = {"url": "https://tong.visitkorea.or.kr/cms2/website/28/3587128.jpg", "w": 1280, "h": 850, "alt": "고군산군도",
            "type": 1, "webp": "/assets/media/3587128-940.webp 940w, /assets/media/3587128-480.webp 480w", "th": None}
    assert present.thumb(base) == {"url": "/assets/media/3587128-480.webp", "w": 480, "h": 319, "alt": "고군산군도",
                                   "type": 1}
    # the provider's own small copy still wins; KOGL-3 (never re-encoded) and photos without derivatives keep the original
    own = {**base, "th": {"url": "https://tong.visitkorea.or.kr/x_image3_1.jpg", "w": 160, "h": 106}}
    assert present.thumb(own)["url"] == "https://tong.visitkorea.or.kr/x_image3_1.jpg"
    assert present.thumb({**base, "type": 3})["url"] == base["url"]
    assert present.thumb({**base, "webp": ""})["url"] == base["url"]
    assert present.thumb(None) is None


# ------------------------------------------------------------------ 군산시 '주차 및 좌석수' with one half only
def test_parking_seats_part_reads_each_half():
    for raw in ("40석", "좌석 100석", "1,200석"):
        assert parking_seats_part(raw) == "seats", raw
    for raw in ("20대", "공영주차장", "불가"):
        assert parking_seats_part(raw) == "parking", raw
    for raw in ("20대/80석", "좌석 40석/ 주차 15대", "30 ~ 40대/100석", "불가능 / 70석", "전화문의", ""):
        assert parking_seats_part(raw) == "", raw


def _seat_only(S) -> list[dict]:
    out = [e for e in S.entities if parking_seats_half(e) == "seats"]
    assert "모트" in {e["slug"] for e in out}
    return out


def test_seat_only_parking_is_listed_missing_once_per_block(S):
    """A seat count alone ('30석') answers no parking question: no 주차 tile, 주차 once in each block's '확인 필요'
    line, the facts row reads 좌석, the list's 주차 cell reads '확인 필요' with '좌석 30석' under it, and neither the
    status line, the title nor the description calls the seats 주차."""
    for e in _seat_only(S):
        kf = present.key_facts(e, "hero")
        assert not [s for s in kf["slots"] if s["key"] == "parking"], e["name"]
        assert kf["missing"].count("주차") == 1, e["name"]
        assert "주차" in present.missing_keys(e)
        ctx = entity_ctx(e, S)
        assert ctx["missing"].count("주차") == 1, e["name"]
        assert [r["label"] for r in present.fact_rows(e, ["parking_seats"], present.Notes())] == ["좌석"]
        cell = present.slot_cell(e, "parking", "주차")
        assert cell["missing"] and cell["label"] == "주차" and cell["sub"].startswith("좌석 "), e["name"]
        assert not [x for x in present.status_items(e) if x["text"].startswith("주차")], e["name"]
        assert "주차" not in ctx["page"]["title"] and "주차·좌석" not in ctx["page"]["description"], e["name"]
    e = place(S, "모트")
    assert present.slot_cell(e, "parking", "주차")["sub"] == "좌석 30석"
    assert "좌석 30석" in [x["text"] for x in present.status_items(e)]
    assert present.seats_note(place(S, "삼미정")) == "좌석 100석"          # '좌석 100석', never '좌석 좌석 100석'


def test_combined_parking_seats_keeps_its_label(S):
    e = place(S, "쌍용반점")
    s = present.slot_value(e, "parking")
    assert (s["label"], s["main"], s["conflict"]) == ("주차·좌석", "7대/40석", False)
    assert "주차" not in present.key_facts(e, "hero")["missing"] and "주차" not in present.missing_keys(e)
    assert [r["label"] for r in present.fact_rows(e, ["parking_seats"], present.Notes())] == ["주차·좌석"]
    assert present.seats_note(e) == "" and "주차" in entity_ctx(e, S)["page"]["title"]
    # a note for the whole field stays the combined field
    assert present.slot_value(place(S, "궁전갈치찜"), "parking")["label"] == "주차·좌석"
    # a parking-only value (none in the data so far) is labelled 주차 and answers it
    one = {**e, "facts": {**e["facts"], "parking_seats": "20대"}}
    assert present.slot_value(one, "parking")["label"] == "주차" and fact_label(one, "parking_seats") == "주차"
    assert "주차" not in present.missing_keys(one)


def test_parking_seats_conflict_on_first_screen(S):
    """명동소바: 군산시 '인근 공영주차장/70석', 한국관광공사 '불가능 / 70석' — the tile and the list cell show both with
    their providers (CLAUDE.md 3.2), never the city's value alone."""
    e = place(S, "명동소바")
    s = present.slot_value(e, "parking")
    assert s["conflict"] and [(v["provider"], v["main"]) for v in s["vals"]] == \
        [("군산시", "인근 공영주차장/70석"), ("한국관광공사", "불가능 / 70석")]
    kf = present.key_facts(e, "hero")
    assert kf["conflict"] and [x["label"] for x in kf["slots"] if x["conflict"]] == ["주차·좌석"]
    cell = present.slot_cell(e, "parking", "주차")
    assert cell["conflict"] and len(cell["vals"]) == 2


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def test_seat_only_markup(S, built):
    html = (built / "places" / "모트" / "index.html").read_text("utf-8")
    assert 'class="kf-i kf-parking' not in html
    i = html.index('<div class="kf-notes">')
    notes = _text(html[i:html.index("</div>", i)])
    assert notes.count("확인 필요") == 1 and "주차" in notes.split("확인 필요", 1)[1], notes
    page = PageScan()
    page.feed(html)
    rows = [r for r in page.fact_rows if "parking_seats" in r["keys"]]
    assert [r["dt"] for r in rows] == ["좌석"] and rows[0]["text"].startswith("30석")
    assert squash(page.blocks["facts"]).count("확인 필요") == 1
    for e in _seat_only(S):
        p = PageScan()
        p.feed((built / "places" / e["slug"] / "index.html").read_text("utf-8"))
        assert seat_only_parking_problems(e, p) == [], e["name"]
    # the validator catches the old tile and a page that drops 주차 from its '확인 필요' lines
    old = PageScan()
    old.feed(html.replace("<dt>좌석</dt>", "<dt>주차·좌석</dt>").replace("확인 필요: 주차", "확인 필요: ")
             .replace("<b>확인 필요</b> 주차", "<b>확인 필요</b> "))
    problems = seat_only_parking_problems(place(S, "모트"), old)
    assert len(problems) == 3, problems
    food = (built / "food" / "index.html").read_text("utf-8")
    rec = next(r for r in food.split('<li class="rec"')[1:] if 'data-place="gunsan-4372587"' in r)
    j = rec.index('<div class="c-parking')
    cell = rec[j:rec.index("</div>", j)]
    assert 'class="kf-na"' in cell and "좌석 30석" in _text(cell), cell


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()



def test_an_unspaced_address_keeps_only_its_house_number_together():
    """present.nowrap_address: a word holding a hyphen ('244-7(장미동)') stays one no-wrap piece; a word longer than
    ADDRESS_WORD_MAX — an address the source gives without spaces — stays one plain text run (no no-wrap piece, so
    the body's overflow-wrap can break it on a phone, and the validator reads it whole as JSON-LD has it)."""
    assert str(present.nowrap_address("전북특별자치도 군산시 해망로 244-7(장미동)")) == \
        '전북특별자치도 군산시 해망로 <span class="nw">244-7(장미동)</span>'
    long = "전북특별자치도군산시임피면구신기길104-3수에어항공"
    assert str(present.nowrap_address(long)) == long


def test_phone_tiles_and_unspaced_addresses_fit_a_360px_phone(built):
    """At 360px (the narrowest width the design is checked at; served through page.route, nothing leaves the
    machine): a 0507 number in a half-width key-fact tile fits its tile, whole (모트: the tile is sized by itself, no
    ellipsis), and an address the source gives without spaces wraps (헬기체험비행 및 조종교육) — no page scrolls
    sideways."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True)
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            for slug in ("모트", "헬기체험비행-및-조종교육"):
                page.goto(f"http://site.test/places/{quote(slug)}/", wait_until="load")
                assert page.evaluate("document.documentElement.scrollWidth") <= 360, slug
                tel = page.locator(".kf-hero .kf-tel")
                if tel.count():
                    fits = tel.evaluate("t => t.scrollWidth <= t.clientWidth && "
                                        "t.querySelector('a.tel').getBoundingClientRect().right <= t.getBoundingClientRect().right")
                    assert fits, slug
                    assert "0507" in tel.inner_text() or slug != "모트"
            ctx.close()
        finally:
            browser.close()


SHARE_BTN = re.compile(r'<button type="button" class="lnav-share" data-share data-share-id="([^"]*)" '
                       r'data-copied="([^"]*)" data-failed="([^"]*)" data-js-only>.*?<span class="lnav-share-t">([^<]*)</span>'
                       r'</button>', re.S)


def test_place_guide_course_and_event_pages_have_one_share_button(S, built):
    """Operator 2026-10-17 (공유하기 + GA4): the local bar of every place, guide, course and event page holds one 공유
    button naming the page's id (the place, guide, course or event series id) with the Korean words. Since
    2026-11-11 ('공유하기 버튼을 크게', the recommended placement approved: 숙박 예약하기 · 코스 목록 · 영상 · 블로그)
    those four pages carry the same pill beside their title (one each, naming the page); the home and the other lists
    have none (the home's 군산각 알리기 box is the share there; a phone's list keeps its first result within 500px)."""
    from urllib.parse import unquote
    pages = {S.ent_by_slug["모트"]["_path"]: S.ent_by_slug["모트"]["id"]}
    for xs, key in ((S.guides, "id"), (S.courses, "id"), (S.series, "key")):
        pages[xs[0]["_path"]] = xs[0][key]
    for path, want in pages.items():
        html = (built / unquote(path).strip("/") / "index.html").read_text("utf-8")
        found = SHARE_BTN.findall(html)
        assert found == [(want, "링크를 복사했습니다", "링크를 복사하지 못했습니다", "공유")], path
        assert html.index('class="lnav-share"') < html.index('class="lnav-cta"'), path
    assert "data-share " not in (built / "index.html").read_text("utf-8")
    title_pill = re.compile(r'<div class="ttl-row"><h1 [^>]*>.*?</h1><button type="button" class="lnav-share ttl-share" '
                            r'data-share data-share-id="([^"]*)"', re.S)
    for path, want in (("courses/index.html", "courses"), ("videos/index.html", "videos"),
                       ("stays/booking/index.html", "stays-booking"), ("blog/index.html", "blog")):
        html = (built / path).read_text("utf-8")
        assert title_pill.findall(html) == [want], path
        assert html.count("data-share ") == 1, path
    for path in ("places/index.html", "food/index.html", "stays/index.html", "guides/index.html", "columns/index.html",
                 "events/index.html", "abroad/index.html"):
        assert "data-share " not in (built / path).read_text("utf-8"), path


def _serve(built):
    """A page.route handler serving the built site at http://site.test/ (nothing leaves the machine)."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if url.startswith("https://weather.o2o.kr/"):   # the tab panel's weather module (tests/conftest.py)
            return route.fulfill(status=200, body=json.dumps(weather_answer()), content_type="application/json",
                                 headers={"access-control-allow-origin": "*"})
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


# the browser's share sheet, clipboard and GA4 sender stood in for: what the page hands them is recorded
SHARE_STUBS = """
window.__events = []; window.__copied = []; window.__shared = [];
window.gunsanTrack = function (name, params) { window.__events.push([name, params]); };
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function (t) {
  window.__copied.push(t); return Promise.resolve(); }}});
var mode = (location.search.match(/share=(\\w+)/) || [])[1];
Object.defineProperty(navigator, 'share', {configurable: true, value: mode === 'none' ? undefined : function (data) {
  window.__shared.push(data);
  if (mode === 'abort') return Promise.reject(new DOMException('closed', 'AbortError'));
  if (mode === 'deny') return Promise.reject(new DOMException('no', 'NotAllowedError'));
  return Promise.resolve(); }});
"""


def test_share_opens_the_sheet_or_copies_and_counts_in_ga4(S, built):
    """In a browser (Playwright + Chromium): the 공유 button hands the phone's share sheet the page title and its
    canonical address with utm_source=share&utm_medium=web_share, and GA4 gets 'share' {method, content_type,
    item_id} only once it went through; a closed sheet sends nothing; a refused sheet, or a browser without one,
    copies the link (utm_medium=copy_link) and says so in the note. Its word shows on phones too (operator
    2026-11-11: the icon alone was not read as 공유), at least 44px to touch, inside the 390px screen."""
    sync_api = pytest.importorskip("playwright.sync_api")
    e = S.ent_by_slug["모트"]
    path = f"http://site.test{quote(e['_path'])}"
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            ctx.add_init_script(SHARE_STUBS)
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            want_ev = {"content_type": "place-food", "item_id": e["id"]}
            for mode, method, copied in (("ok", "web_share", False), ("abort", None, False), ("deny", "copy_link", True),
                                         ("none", "copy_link", True)):
                page.goto(f"{path}?share={mode}", wait_until="load")   # a new document each time (a hash alone would not reload)
                canon = page.get_attribute('link[rel="canonical"]', "href")
                btn = page.locator(".lnav [data-share]")
                box = btn.bounding_box()
                assert box["width"] >= 44 and box["height"] >= 44 and box["x"] + box["width"] <= 390, mode
                assert page.locator(".lnav [data-share] .lnav-share-t").is_visible(), mode
                assert btn.inner_text().strip() == "공유", mode
                btn.click()
                page.wait_for_timeout(300)
                ev = page.evaluate("window.__events")
                shared, cop = page.evaluate("window.__shared"), page.evaluate("window.__copied")
                if mode != "none":
                    assert shared == [{"title": page.title(), "url": f"{canon}?utm_source=share&utm_medium=web_share"}], mode
                assert ev == ([["share", {"method": method, **want_ev}]] if method else []), mode
                assert cop == ([f"{canon}?utm_source=share&utm_medium=copy_link"] if copied else []), mode
                note = page.locator("body > .share-note")
                if copied:
                    assert note.inner_text() == "링크를 복사했습니다" and "is-on" in note.get_attribute("class"), mode
                    assert note.get_attribute("role") == "status"
            ctx.close()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            page.goto(path, wait_until="load")
            assert page.locator(".lnav [data-share] .lnav-share-t").is_visible()
            assert page.locator(".lnav [data-share]").inner_text().strip() == "공유"
            ctx.close()
        finally:
            browser.close()


# ------------------------------------------------------------------ 보내기 (operator 2026-11-11, pipeline/share.py)
def test_share_view_tags_every_link_and_draws_the_qr_code():
    """Each plain tile carries the page's address with utm_source=share&utm_medium=<its method>; the QR code opens the
    address tagged qr and is hidden from screen readers (its caption says what it does)."""
    from urllib.parse import unquote

    from pipeline import share
    url = "https://gunsan.webforai.kr/places/%EB%AA%A8%ED%8A%B8/"
    v = share.view(url, "모트 | 군산각", "gunsan-1")
    assert v["url"] == url and v["id"] == "gunsan-1"
    for key, prefix in (("sms", "sms:?&body="), ("facebook", "https://www.facebook.com/sharer/sharer.php?u="),
                        ("x", "https://x.com/intent/tweet?text="), ("band", "https://band.us/plugin/share?body=")):
        assert v[key].startswith(prefix), key
        assert f"{url}?utm_source=share&utm_medium={key}" in unquote(v[key]), key
    assert "모트 | 군산각" in unquote(v["sms"]) and "&route=gunsan.webforai.kr" in v["band"]
    assert v["qr"].startswith('<svg aria-hidden="true" focusable="false" viewBox=') and 'class="shr-qr-i"' in v["qr"]
    assert share.tagged(url + "?a=1", "qr") == url + "?a=1&utm_source=share&utm_medium=qr"


SHR_BOX = re.compile(r'<div class="shr[^"]*" role="group" aria-labelledby="([^"]+)" data-shr data-shr-url="([^"]+)" '
                     r'data-shr-title="([^"]*)" data-shr-id="([^"]*)"')


def test_the_send_box_stands_where_the_operator_placed_it(S, built):
    """Operator 2026-11-11 (the recommended placement): a place page has the box under its route row (and booking
    rows), before the photo; a guide, course and column before 이어서 보기; an event under its route; the home its
    '군산각 알리기' (#share) before 제휴·관련 사이트. Every box names the page's canonical address and record id, carries
    the Kakao key and the SDK with its integrity hash, the 카카오톡 / 링크 복사 / 문자 / 더보기 tiles and the 페이스북 / X /
    밴드 links and the QR code. Every Korean page with the panel holds the site's dialog and two openers (the panel,
    the phone menu), each a link to /#share without JavaScript."""
    from urllib.parse import unquote

    from pipeline import share
    key = S.site["kakao_js_key"]
    motte = S.ent_by_slug["모트"]
    g = next(x for x in S.guides if present.see_also(S, "guide", x))
    pages = {motte["_path"]: ("같이 갈 사람에게 보내기", motte["id"]), g["_path"]: ("이 가이드 보내기", g["id"]),
             S.courses[0]["_path"]: ("이 코스 보내기", S.courses[0]["id"]),
             S.columns[0]["_path"]: ("이 칼럼 보내기", S.columns[0]["id"]),
             S.series[0]["_path"]: ("같이 갈 사람에게 보내기", S.series[0]["key"])}
    for path, (title, rid) in pages.items():
        html = (built / unquote(path).strip("/") / "index.html").read_text("utf-8")
        canon = re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)
        boxes = SHR_BOX.findall(html)
        assert [b for b in boxes if b[0] == "h-shr"] == [("h-shr", canon, boxes[0][2], rid)], path
        assert f'<p class="shr-h" id="h-shr">' in html and f"<span>{title}</span>" in html, path
        assert f'data-shr-key="{key}" data-shr-sdk="{share.SDK}" data-shr-sri="{share.SDK_SRI}"' in html, path
        for do in ("kakao", "copy_link", "sms", "web_share", "facebook", "x", "band"):
            assert f'data-shr-do="{do}"' in html, (path, do)
        assert f"utm_medium%3Dfacebook" in html and 'class="shr-qr-i"' in html, path
        box_at = html.index('id="h-shr"')
        if path == motte["_path"]:
            assert html.index("data-route") < box_at < html.index('class="pv '), path
        elif "/events/" not in path and 'id="h-see"' in html:
            assert box_at < html.index('id="h-see"'), path
    home = (built / "index.html").read_text("utf-8")
    assert re.search(r'<section class="home-shr[^"]*" id="share" aria-labelledby="h-home-shr">', home)
    assert home.index('id="share"') < home.index('제휴·관련 사이트', home.index('id="share"'))
    site_url = S.site["site_url"].rstrip("/") + "/"
    assert ("h-home-shr", site_url, "군산각", "site") in SHR_BOX.findall(home)
    for path in ("index.html", "places/index.html", unquote(motte["_path"]).strip("/") + "/index.html"):
        html = (built / path).read_text("utf-8")
        assert html.count('<dialog class="shr-dlg" id="shr-site"') == 1, path
        assert ("shr-site-h", site_url, "군산각", "site") in SHR_BOX.findall(html), path
        assert html.count('<a class="sd-shr-a" href="/#share" data-shr-open="shr-site">') == 2, path
        side = html[html.index('<div class="side">'):]
        assert side.index('class="sd-shr"') < side.index('class="sd-pt"'), path


def test_link_previews_show_a_type1_photo_or_the_sites_picture(S, built):
    """Operator 2026-11-11 ('2번은 니 권장안대로'): previews crop and a Type3 photo may not be cropped, so og:image is a
    Type1 photo only — a place page without one shows the logo card (no illustration: CLAUDE.md 4), the other pages
    the site's link-preview picture."""
    from urllib.parse import unquote
    type3 = {im["url"] for e in S.entities for im in e["_images"] if im.get("license") != "KOGL-1"}
    type1 = {im["url"] for e in S.entities for im in e["_images"] if im.get("license") == "KOGL-1"}
    card = S.site["site_url"].rstrip("/") + "/assets/brand/og-card.png"
    seen = {"card": 0, "photo": 0}
    for e in S.entities:
        if not (built / unquote(e["_path"]).strip("/") / "index.html").is_file():
            continue
        html = (built / unquote(e["_path"]).strip("/") / "index.html").read_text("utf-8")
        og = re.search(r'<meta property="og:image" content="([^"]+)"', html).group(1)
        own1 = [im["url"] for im in e["_images"] if im.get("license") == "KOGL-1"]
        assert og == (own1[0] if own1 else card), e["id"]
        seen["card" if og == card else "photo"] += 1
        if og == card:
            assert '<meta property="og:image:alt" content="군산각 로고">' in html, e["id"]
    assert seen["card"] and seen["photo"]
    assert (built / "assets" / "brand" / "og-card.png").is_file()
    for f in [built / "index.html", *built.glob("guides/*/index.html"), *built.glob("courses/*/index.html"),
              *built.glob("themes/*/index.html"), built / "places" / "index.html", built / "columns" / "index.html"]:
        og = re.search(r'<meta property="og:image" content="([^"]+)"', f.read_text("utf-8"))
        assert og and og.group(1) not in type3, f
        assert og.group(1) in type1 or "/assets/art/og-" in og.group(1), f


def test_the_send_box_copies_hands_kakaotalk_the_address_and_counts_in_ga4(S, built):
    """In a browser (Playwright + Chromium) on a 360px phone: the box fits the screen with tiles of 44px or more; 링크
    복사 copies the canonical address tagged copy_link and says so; 카카오톡 hands Kakao.Share.sendScrap the address
    tagged kakao after Kakao.init with the site's key (a stand-in SDK); without the SDK (blocked) the link is copied
    with the note '카카오톡을 열지 못해 …'; 문자 is a link tagged sms; every one sends GA4 'share' with its method.
    On a 1440px screen the panel's '군산각 공유하기' opens the site's box in a dialog (페이스북 · X · 밴드 and the QR code
    shown, the phone tiles hidden), its 링크 복사 copies the home's address with the note inside the dialog, and
    Escape closes it."""
    sync_api = pytest.importorskip("playwright.sync_api")
    e = S.ent_by_slug["모트"]
    path = f"http://site.test{quote(e['_path'])}"
    # as the real SDK 2.x: no Kakao.Share before Kakao.init (the live site, 2026-11-12)
    kakao_stub = """window.__kakao = [];
window.Kakao = {_on: false, isInitialized: function () { return this._on; },
  init: function (k) { this._on = true; window.__kakao.push(['init', k]);
    this.Share = {sendScrap: function (o) { window.__kakao.push(['scrap', o.requestUrl]); }}; }};"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            want = {"content_type": "place-food", "item_id": e["id"]}
            for stub in (True, False):
                ctx = browser.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True)
                ctx.add_init_script(SHARE_STUBS + (kakao_stub if stub else ""))
                ctx.route("**/*", _serve(built))
                page = ctx.new_page()
                page.goto(f"{path}?share=none", wait_until="load")
                canon = page.get_attribute('link[rel="canonical"]', "href")
                box = page.locator(".pl-head [data-shr]")
                box.scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth") <= 360
                tiles = box.locator(".shr-b:visible")
                assert tiles.all_inner_texts() == ["카카오톡", "링크 복사", "문자"]   # 더보기: no share sheet here
                for t in tiles.all():
                    bb = t.bounding_box()
                    assert bb["width"] >= 44 and bb["height"] >= 44 and bb["x"] + bb["width"] <= 360
                assert box.locator('[data-shr-do="sms"]').get_attribute("href").endswith(
                    quote(f"{canon}?utm_source=share&utm_medium=sms", safe=""))
                box.locator('[data-shr-do="kakao"]').click()
                page.wait_for_timeout(400)
                ev, cop = page.evaluate("window.__events"), page.evaluate("window.__copied")
                note = page.locator("body > .share-note")
                if stub:
                    assert page.evaluate("window.__kakao") == [["init", S.site["kakao_js_key"]],
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
                else:
                    assert cop == [f"{canon}?utm_source=share&utm_medium=copy_link"]
                    assert note.inner_text() == "카카오톡을 열지 못해 링크를 복사했습니다"
                    assert ev == [["share", {"method": "copy_link", **want}]]
                ctx.close()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(SHARE_STUBS)
            ctx.route("**/*", _serve(built))
            page = ctx.new_page()
            page.goto(path, wait_until="load")
            pc = page.locator(".pl-head [data-shr] .shr-b:visible")
            assert [t.split("(")[0].strip() for t in pc.all_inner_texts()] == ["카카오톡", "링크 복사", "페이스북", "X", "밴드"]
            assert page.locator(".pl-head [data-shr] .shr-qr-i").is_visible()
            page.locator(".side [data-shr-open]").click()
            dlg = page.locator("dialog[data-shr-dlg]")
            assert dlg.evaluate("d => d.open")
            dlg.locator('[data-shr-do="copy_link"]').click()
            page.wait_for_timeout(300)
            home = S.site["site_url"].rstrip("/") + "/"
            assert page.evaluate("window.__copied") == [f"{home}?utm_source=share&utm_medium=copy_link"]
            assert dlg.locator(".share-note").inner_text() == "링크를 복사했습니다"
            assert page.evaluate("window.__events")[-1] == ["share", {"method": "copy_link", "content_type": "place-food",
                                                                       "item_id": "site"}]
            page.keyboard.press("Escape")
            assert not dlg.evaluate("d => d.open")
            ctx.close()
        finally:
            browser.close()


def test_the_site_name_and_the_logos_colour_its_end():
    """Operator 2026-10-17 (ChatGPT colour study A, 'gak' too): the bar's and the footer's name keeps its text and puts
    its end in .wm-em (군산<각>, Gunsan<gak>); the light logos draw 각 and gak in the site blue #2F6FC9, the reverse in
    the lantern yellow #FFD54A, the mono one in one black path per line as before."""
    assert str(present.wordmark("군산각")) == '군산<span class="wm-em">각</span>'
    assert str(present.wordmark("Gunsangak")) == 'Gunsan<span class="wm-em">gak</span>'
    assert str(present.wordmark("군산 여행")) == "군산 여행" and str(present.wordmark("<b>")) == "&lt;b&gt;"
    brand = ROOT / "templates" / "assets" / "brand"
    fills = lambda name: re.findall(r'<path fill="(#[0-9A-F]{6})"', (brand / name).read_text("utf-8"))  # noqa: E731
    for name in ("gunsangak-logo.svg", "gunsangak-logo-vertical.svg"):
        assert fills(name)[-4:] == ["#172033", "#2F6FC9", "#172033", "#2F6FC9"], name
    assert fills("gunsangak-logo-reverse.svg")[-4:] == ["#FFFFFF", "#FFD54A", "#FFFFFF", "#FFD54A"]
    assert set(fills("gunsangak-logo-mono.svg")) == {"#000000"} and len(fills("gunsangak-logo-mono.svg")) == 3
    css = (ROOT / "templates" / "assets" / "css" / "20-chrome.css").read_text("utf-8")
    assert ".wm-em { color: var(--sea); }" in css


def test_the_story_stage_keeps_its_text_years_and_photo_together_on_tall_windows(built):
    """Operator 2026-10-17: on a 1840px-tall desktop window the home's 군산 이야기 had its text at the top, its photo in
    the middle and its years at the bottom, 1276px below the text. Now the window's spare height goes to the margins:
    the heading, the text and the years are one block, the photo on its centre line, on short and tall windows.
    The tall window is compared with a short one of the same width (2026-11-10: the home's right board starts at 1680px,
    so a 1440px window's column is no longer the narrower one — a chapter's text wraps differently at 1440 and 1900px,
    and a short chapter's gap under the row that holds the longest differs by that, not by the window's height)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    measure = """() => {
      const box = document.querySelector('[data-story]'), r = el => el.getBoundingClientRect();
      const on = box.querySelector('.st-ch.is-on') || box.querySelector('.st-ch');
      const kids = [...on.querySelector('.st-text').children];
      const ph = [...box.querySelectorAll('.st-ph')].reduce((a, p) => +getComputedStyle(p).opacity >= .5 ? p : a);
      return {head: r(box.querySelector('.st-head')).top, text: r(kids[kids.length - 1]).bottom,
              rail: [r(box.querySelector('.st-rail')).top, r(box.querySelector('.st-rail')).bottom],
              photo: [r(ph).top, r(ph).bottom]}; }"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            gaps = {}
            for w, h in ((1440, 900), (1900, 900), (1900, 1840)):
                ctx = browser.new_context(viewport={"width": w, "height": h}, reduced_motion="no-preference")
                ctx.route("**/*", _serve(built))
                page = ctx.new_page()
                page.goto("http://site.test/", wait_until="load")
                page.wait_for_function("!!document.querySelector('[data-story].is-staged')", timeout=15000)
                top, height = page.evaluate("(() => { const s = document.querySelector('[data-stage]').getBoundingClientRect();"
                                            " return [s.top + scrollY, s.height]; })()")
                for k in range(3):   # each chapter: 1908 세관, 1909 근대, 오늘
                    page.evaluate("y => window.scrollTo(0, y)", top + (height - h) * (k / 3 + .12))
                    page.wait_for_timeout(700)
                    m = page.evaluate(measure)
                    gaps[(w, h, k)] = m["rail"][0] - m["text"]
                    assert 0 < gaps[(w, h, k)] <= 160, (w, h, k, m)  # the years right under the text (its row holds the longest)
                    block, photo = (m["head"] + m["rail"][1]) / 2, sum(m["photo"]) / 2
                    assert abs(block - photo) <= 60 and m["rail"][1] <= h, (w, h, k, m)
                ctx.close()
        finally:
            browser.close()
    for k in range(3):   # a taller window adds no gap between the text and the years (it was 364px → 1276px)
        assert gaps[(1900, 1840, k)] - gaps[(1900, 900, k)] <= 24, gaps


def test_home_ranks_the_curated_videos_by_views_and_the_instagram_posts_by_likes(S, built):
    """Operator 2026-11-10 ('유튜브, 인스타도 순위별로 큐레이션해서 굉장히 잘 보이는 곳에'): right under the opening — after the
    hero and the festival card, before the food row, the question box and the news — the home ranks the five curated
    videos with the most views and the five curated Instagram posts with the most likes. Each row carries its rank,
    who, the count the rank comes from and one link (the video on YouTube; the post's card in the cafe guide, where
    the official embed is); the block says what the order is — an order within the lists this site picked, not among
    every video about the region —, that it is not a recommendation and that the counts are those of the day the lists
    were made, without the day itself (operator 2026-10-09: a check date is data, not screen text). An Instagram row's
    picture is a licensed photo of a place the post lists, never the post's. The curated videos are in
    the order of their views wherever they are listed (/videos/ numbers them), and the list holds every video of
    this site with more views than its last one (operator 2026-11-10 '넣어': a video outside the list never has more
    views than one in it). The home has no other YouTube or Instagram section: a list is on the screen once (from
    1680px the board beside the column shows one of the two and the block the other — the browser test below)."""
    from markupsafe import escape
    from pipeline.build import view_count
    html = (built / "index.html").read_text("utf-8")
    a = html.index('<section class="hrk"')
    blk = html[a:html.index("</section>", a)]
    assert html.index('aria-labelledby="h-home"') < a < html.index('aria-labelledby="h-hfood"') < html.index('aria-labelledby="h-news"')
    if 'aria-labelledby="h-fw"' in html:
        assert html.index('aria-labelledby="h-fw"') < a
    assert 'aria-labelledby="h-vid"' not in html and "h-insta-home" not in html
    yt, ig = blk.split('hrk-svc svc-instagram', 1)   # the two columns
    row = r'<a class="hrk-a" href="([^"]+)"'
    rank = r'<span class="hrk-n tn">(\d)<span class="vh">위</span></span>'
    # the videos: the curated list is in the order of its view counts, and the home shows its first five
    pop = S.popular_videos
    counts = [view_count(v) for v in pop]
    assert len(pop) >= 5 and all(counts) and counts == sorted(counts, reverse=True)
    assert not [v["youtube_id"] for v in S.videos if v not in pop and view_count(v) > counts[-1]]   # none outranks the list
    # a count is a whole number of views; a short form is not read as its digits (it would rank below everything)
    assert view_count({"view_text": "조회수 3,486,762회"}) == 3486762
    assert view_count({"view_text": "조회수 349만회"}) == 0 and view_count({"view_text": "조회수 1.2만회"}) == 0 and view_count({}) == 0
    assert re.findall(row, yt) == [str(escape(v["url"])) for v in pop[:5]]
    assert re.findall(rank, yt) == list("12345")
    for v in pop[:5]:
        assert (v.get("short_view_text") or v["view_text"]) in yt and str(escape(v["channel"])) in yt
    # the posts: by likes, each to its card in the guide that holds the Instagram chapter
    posts = sorted(S.insta, key=lambda p: (int(p.get("likes") or 0), p["id"]), reverse=True)[:5]
    guide = next(g["_path"] for g in S.guides if g.get("_insta"))
    assert [int(p["likes"]) for p in posts] == sorted((int(p["likes"]) for p in posts), reverse=True) and posts[-1]["likes"]
    assert re.findall(row, ig) == [f"{guide}#{p['id']}" for p in posts]
    assert re.findall(r'<span class="hrk-cnt tn">좋아요 ([\d,]+)</span>', ig) == [f"{int(p['likes']):,}" for p in posts]
    assert re.findall(rank, ig) == list("12345")
    assert len(re.findall(r"<img ", ig)) == len(re.findall(r'<img [^>]*data-kogl="[13]"', ig))   # place photos only
    rows = ig.split('<li class="hrk-i')[1:]
    for p, r in zip(posts, rows):     # … each of a place the post itself lists (never a 'related' one)
        src = re.search(r'<img src="([^"]+)"', r)
        if src:
            own = {ph["url"] for s in p["place_slugs"] if s in S.ent_by_slug for ph in S.ent_by_slug[s]["_photos"]}
            assert unescape(src.group(1)) in own, (p["id"], src.group(1))
    # ranks four and five are the rows a phone leaves out (css .hrk-x)
    assert blk.count('<li class="hrk-i hrk-x">') == 4 and blk.count('<li class="hrk-i">') == 6
    note = unescape(re.sub(r"<[^>]+>", "", re.search(r'<p class="hrk-note">(.*?)</p>', blk, re.S).group(1)))
    assert "고른 목록 안에서 유튜브는 조회수" in note and "인스타그램은 좋아요 수가 많은 순서" in note and "실은 때의 값" in note
    sub = unescape(re.sub(r"<[^>]+>", "", re.search(r'<p class="hrk-sub">(.*?)</p>', blk, re.S).group(1)))
    assert f"고른 영상 {len(pop)}편·카페 게시물 {len(S.insta)}편 가운데" in sub      # the scope of the ranks, said first
    assert "추천 순서가 아닙니다" in note and "한국관광공사" in note and not re.search(r"\d{4}년|\d+월 \d+일|확인\)", note)
    # the board (from 1680px) shows the same five with the rank on each picture, and says what its orders are
    board = html[html.index('<aside class="h-rside"'):html.index("</aside>")]
    assert re.findall(r'<span class="hrs-rk tn">(\d)<span class="vh">위 </span></span>', board) == list("12345")
    assert board.count('class="hrs-by">조회수 순<') == 1 and board.count('class="hrs-by">좋아요 순<') == 1
    caveats = re.findall(r'<p class="hrs-note">(.*?)</p>', board)
    assert len(caveats) == 2 and all("추천 순서가 아님" in c and "실은 때의 값" in c and "안의" in c for c in caveats)
    assert re.findall(r'<a class="hrs-va" href="([^"]+)"', board) == [str(escape(v["url"])) for v in pop[:5]]
    # /videos/: the whole curated list in the same order (css/47-rank.css draws each one's number), with the rule
    v = (built / "videos" / "index.html").read_text("utf-8")
    sec = v[v.index('id="yt-popular"'):]
    sec = sec[:sec.index("</section>")]
    assert re.findall(r'data-yt="([^"]+)"', sec) == [x["youtube_id"] for x in pop[:8]]
    listed = list(dict.fromkeys(re.findall(r'(?:data-yt="|watch\?v=)([\w-]{11})', sec)))    # the cards, then the folded rows
    assert listed == [x["youtube_id"] for x in pop]
    rule = unescape(re.sub(r"<[^>]+>", "", re.search(r'<p class="note yt-rank-note">(.*?)</p>', sec, re.S).group(1)))
    assert f"고른 {len(pop)}편을 조회수가 많은 순으로" in rule and "추천 순서가 아닙니다" in rule and not re.search(r"\d+월 \d+일", rule)


def test_the_rank_block_is_under_the_opening_and_shares_the_two_lists_with_the_board_on_wide_windows(built):
    """The same (operator 2026-11-10), in a browser: below 1680px the rank block is on the page above the food row —
    three ranks of each list while they are one column, five in two columns from 720px — with every link a 44px
    target where fingers are, and no board. From 1680px the board beside the column shows one list behind its tabs
    and the block shows the other as five cards (operator: on a wide window 'the way you find reasonable'): the
    Instagram ranks while the board is on YouTube, the videos once its Instagram tab is pressed — both lists on the
    screen, no row on it twice. Nothing is wider than the window. An Instagram row's place photo is whole inside its
    box (a KOGL-3 photo may not be cut: it was, by its lower edge, while the box was a grid)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    measure = """() => { const b = document.querySelector('.hrk'), r = b.getBoundingClientRect(), shown = e => e.getClientRects().length > 0;
      const board = document.querySelector('.h-rside');
      return {block: shown(b), top: r.top + scrollY, height: r.height, rows: [...b.querySelectorAll('.hrk-i')].filter(shown).length,
              cols: shown(b) ? getComputedStyle(b.querySelector('.hrk-cols')).gridTemplateColumns.split(' ').length : 0,
              board: !!board && getComputedStyle(board).display !== 'none',
              ranks: board ? [...board.querySelectorAll('.hrs-rk')].filter(shown).map(e => e.textContent.trim()) : [],
              title: b.querySelector('.hrk-h').innerText.trim(),
              mine: [...b.querySelectorAll('.hrk-a')].filter(shown).map(a => a.getAttribute('href')),
              theirs: board ? [...board.querySelectorAll('.hrs-va, .hrs-ctop')].filter(shown).map(a => a.getAttribute('href')) : [],
              small: [...b.querySelectorAll('a')].filter(shown).filter(a => a.getBoundingClientRect().height < 44).length,
              cut: [...b.querySelectorAll('.hrk-ig img')].filter(shown).filter(i => { const a = i.getBoundingClientRect(),
                c = i.closest('.hrk-th').getBoundingClientRect(); return a.top < c.top - .5 || a.bottom > c.bottom + .5
                  || a.left < c.left - .5 || a.right > c.right + .5
                  || (i.dataset.kogl === '3' && getComputedStyle(i).objectFit !== 'contain'); }).length,
              photos: [...b.querySelectorAll('.hrk-ig img')].filter(shown).length,
              sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
              food: document.querySelector('.ha-food').getBoundingClientRect().top + scrollY}; }"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            for w, h in ((360, 740), (390, 844), (640, 900), (768, 1024), (1280, 800), (1440, 900), (1679, 1000), (1680, 1000), (1920, 1080)):
                ctx = browser.new_context(viewport={"width": w, "height": h})
                ctx.route("**/*", _serve(built))
                page = ctx.new_page()
                page.goto("http://site.test/", wait_until="load")
                page.wait_for_timeout(300)
                m = page.evaluate(measure)
                assert m["sw"] <= m["cw"] + 1, (w, m)
                if w < 1680:
                    assert m["block"] and not m["board"] and m["top"] < m["food"], (w, m)
                    assert m["rows"] == (6 if w < 720 else 10) and m["cols"] == (1 if w < 720 else 2), (w, m)
                    assert m["photos"] >= 1 and m["cut"] == 0, (w, m)
                    assert m["height"] <= (1000 if w < 720 else 860), (w, m)      # a compact chart, not a long section
                    if w < 1024:
                        assert m["small"] == 0, (w, m)
                else:
                    # the board is on YouTube: the block is the Instagram list, five cards in one row
                    assert m["block"] and m["board"] and m["ranks"] == ["1위", "2위", "3위", "4위", "5위"], (w, m)
                    assert m["title"] == "인스타그램 인기 순위" and m["rows"] == 5 and m["cols"] == 1 and m["top"] < m["food"], (w, m)
                    assert m["photos"] >= 1 and m["cut"] == 0 and m["height"] <= 640, (w, m)
                    assert len(m["mine"]) == 5 and not set(m["mine"]) & set(m["theirs"]), (w, m)
                    page.click("#hrs-tab-ig")                      # … and the reverse
                    page.wait_for_timeout(200)
                    m = page.evaluate(measure)
                    assert m["title"] == "유튜브 인기 순위" and m["rows"] == 5 and m["ranks"] == [], (w, m)
                    assert len(m["mine"]) == 5 and not set(m["mine"]) & set(m["theirs"]) and m["sw"] <= m["cw"] + 1, (w, m)
                ctx.close()
        finally:
            browser.close()


def test_a_photo_that_does_not_load_leaves_no_broken_image(S, built):
    """Report 2026-10-17 (외부 사진 실패 화면): with every photo request failing (TourAPI's server unreachable), no page
    shows a broken-image box — a row, card or guide item keeps its text without the thumbnail, a gallery drops the
    item, a photo frame goes with its credit, the home's opening and story keep their dark frame without the
    picture."""
    sync_api = pytest.importorskip("playwright.sync_api")
    broken = """() => [...document.querySelectorAll('img')].filter(i => i.isConnected && i.complete && !i.naturalWidth
        && getComputedStyle(i).visibility !== 'hidden' && i.getClientRects().length).map(i => i.outerHTML.slice(0, 90))"""
    guide = next(g["_path"] for g in S.guides if 'class="gi-th' in (built / g["_path"].strip("/") / "index.html").read_text())
    paths = ["/", S.ent_by_slug["모트"]["_path"], "/food/", guide, S.courses[0]["_path"]]
    # what must stay when its photo fails: a guide's place items, each with its name and reason (review 2026-10-17:
    # a failed thumbnail took the whole item), and no photo link left without its photo
    kept = """() => ({items: document.querySelectorAll('li.gitem').length,
        empty: [...document.querySelectorAll('a')].filter(a => !a.textContent.trim() && !a.querySelector('img, svg')).length})"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            for w, h in ((390, 844), (1440, 900)):
                ctx = browser.new_context(viewport={"width": w, "height": h})
                ctx.route("**/*", _serve(built))          # the photos' hosts are aborted: every photo fails
                page = ctx.new_page()
                for path in paths:
                    page.goto(f"http://site.test{quote(path)}", wait_until="load")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")   # lazy photos start (and fail)
                    page.wait_for_timeout(700)
                    assert page.evaluate(broken) == [], (w, path)
                    # no photo frame (with its credit line) stays around a photo that failed
                    assert page.evaluate("[...document.querySelectorAll('figure.pv img, figure.ph img, figure.pc-ph img')]"
                                         ".filter(i => i.complete && !i.naturalWidth).length") == 0, (w, path)
                    html = (built / path.strip("/") / "index.html").read_text()
                    assert page.evaluate(kept) == {"items": html.count('class="gitem"'), "empty": 0}, (w, path)
                ctx.close()
        finally:
            browser.close()


def test_list_and_map_pages_show_their_filters_map_and_first_results_early(built):
    """Outside review 2026-10-17: on the map and list pages the head picture took ~400px of a 900px desktop screen
    (the map began at 606px, the first place at 791px). The band is a thin strip there now: on a 1440×900 screen the
    map and the filters start above 500px, the first result above 650px; on a phone (390 and 360 wide) the first result
    above 500px — on the stays list too, under its '숙박 예약하기' row (operator 2026-11-04; css/90-refine 6.)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    m = """() => { const q = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().top : null; };
      return {map: q('.map'), filters: q('[data-filters]'), first: q('.rec, [data-filter-item]')}; }"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            for w, h, mob in ((1440, 900, False), (390, 844, True), (360, 740, True)):
                ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=mob, has_touch=mob)
                ctx.route("**/*", _serve(built))
                page = ctx.new_page()
                for path in ("/map/", "/food/", "/places/", "/stays/"):
                    page.goto(f"http://site.test{path}", wait_until="load")
                    r = page.evaluate(m)
                    if not mob:
                        assert r["map"] is not None and r["map"] <= 500, (path, r)
                    if path != "/map/":
                        assert r["first"] <= (650 if not mob else 500), (w, path, r)
                ctx.close()
        finally:
            browser.close()
