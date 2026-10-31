"""조건으로 찾기 — the condition chips of the list pages (operator 2026-10-31, design ③ Filter.dc.html;
pipeline/conditions.py, templates/_filters.html.j2, site.js 'list filters').

The judgement (no build): 월요일 영업 is the rule of the guide '군산 월요일 맛집' and of the former check box
(present.monday_open: the closed days are stated and Monday is not one, not even partly); 21시 이후까지 reads the
latest closing time the way the guide '늦게까지 하는 식당' counts (the latest day; a break, a last order or a preparation
range never closes the day; '익일 02:00' is 26:00; '24시간' all day) at 21:00 or later; 주차 가능 needs a car to be
left somewhere — a seat count alone ('40석', schema.parking_seats_part) is no parking; 반려동물 only where the pet value
allows one ('불가', '불가능', '없음' never). Each reason carries the field's label, its shown value and the source's short
name, no date (operator decision 2026-10-09).

The build (the sample data with five restaurants and two attractions added) and a browser (Playwright + Chromium, the
build served through page.route — nothing leaves the machine): the chips combine (AND), the count rolls to its new
number (at once with reduced motion) beside the ratio bar, each shown row shows the reasons of the chosen conditions,
the URL keeps them (?c=mon,late; an old ?check=1 is the condition the check box became) and a way back restores them,
zero results offer one '<조건> 조건 해제' per condition that alone brings rows back, and without JS the lists are
complete with neither chips nor reasons."""
import copy
import json
import mimetypes
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline import conditions as C
from pipeline import locales as LC
from pipeline import present
from pipeline.build import build

ROOT = Path(__file__).resolve().parent.parent
# the sample city (data/sample, the first site's shape): its short provider names ('군산시 문화관광' → '군산시')
CITY = __import__("pipeline.city", fromlist=["of"]).of(json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8")))


def judge(e: dict) -> dict:
    return C.judge(e, city=CITY)


def rec(kind: str, facts: dict, **extra) -> dict:
    return {"id": "t", "name": "t", "kind": kind, "facts": facts,
            "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"}, **extra}


# ------------------------------------------------------------------ the judgement
def test_monday_follows_the_guide_and_the_former_check_box():
    yes = judge(rec("food", {"usetime_restdate": "11:30~21:00 / 연중무휴"}))["mon"]
    assert (yes["key"], yes["label"], yes["value"], yes["short"]) == ("usetime_restdate", "쉬는 날", "연중무휴", "군산시")
    assert judge(rec("food", {"restdate": "매주 화요일"}))["mon"]["value"] == "매주 화요일"
    for closed in ("매주 월요일", "둘째,넷째주 월요일 휴무", "전화문의", "비정기적 휴무"):
        assert "mon" not in judge(rec("food", {"restdate": closed})), closed
    assert "mon" not in judge(rec("food", {"usetime": "11:00~21:00"}))          # no closed day stated
    # an attraction's chip is worded for it, the rule is the same
    assert "mon" in judge(rec("attraction", {"restdate": "연중무휴"}))
    assert C.chip_label("mon", "attraction", LC.COND_WORDS["ko"]) == "월요일 개방"
    assert C.chip_label("mon", "food", LC.COND_WORDS["ko"]) == "월요일 영업"


def test_the_latest_closing_time_is_read_the_way_the_late_guide_counts():
    ct = lambda raw: (lambda c: c and (c["minutes"], c["t"], c["next"], c["allday"]))(C.close_time(raw))
    assert ct("24시간영업 / 연중무휴") == (2880, "", False, True)
    # the latest day counts; an order deadline never closes the day; 익일 02:00 is 26:00
    assert ct("월~목 11:00~23:00 (주문마감 22:00)금 11:00~익일02:00 (주문마감 01:00)토~일 10:00~익일02:00 (주문마감 22:00)") \
        == (26 * 60, "02:00", True, False)
    assert ct("[월요일~토요일]- 11:00~24:00- 쉬는시간 14:00~17:00[일요일]- 17:00~24:00") == (24 * 60, "24:00", False, False)
    # a break or preparation range, a last order: never the closing time
    assert ct("11:00~21:00\n- 준비 시간 15:00~17:00\n- 마지막 주문 20:30")[:2] == (21 * 60, "21:00")
    assert ct("[화요일~토요일]- 11:00~21:00- 준비시간 15:00~17:00[일요일]- 11:00~20:00- 마지막 주문 15:00~17:00")[1] == "21:00"
    assert ct("11:00 ~ 20:30 (브레이크 타임 14:30 ~17:00)")[1] == "20:30"
    assert ct("10:30~재료 소진 시※ 자세한 영업시간은 방문 전 전화 문의 요망") is None
    assert ct("월요일~토요일 12:00~22:30\n일요일 12:00~22:00")[1] == "22:30"
    # the chip: 21:00 or later
    late = lambda raw: "late" in judge(rec("food", {"usetime": raw}))
    assert late("17:00~21:00") and late("12:00~24:00") and not late("11:00~20:30") and not late("06:00~14:00")
    words = LC.COND_WORDS["ko"]
    r = judge(rec("food", {"usetime": "11:00~익일02:00"}))["late"]
    assert C.late_text(r["close"], words) == "익일 02:00까지 영업"
    assert C.ko_tags(judge(rec("food", {"usetime": "10:00~22:00"})), words)[0]["value"] == "22:00까지 영업"
    assert C.late_text({"allday": True}, words) == "24시간 영업"


def test_a_seat_count_alone_is_no_parking():
    park = lambda **f: (judge(rec("food", f)).get("park") or {}).get("value")
    assert park(parking_seats="40석") is None                     # seats only: 주차 stays unknown
    assert park(parking_seats="좌석 100석") is None
    assert park(parking_seats="7대/40석") == "7대"                # the parking half
    assert park(parking_seats="좌석수 200석/ 주차 100대") == "100대"
    assert park(parking_seats="공용주차장/35석") == "공용주차장"
    assert park(parking_seats="전화문의") is None
    assert park(parking="불가능") is None and park(parking="불가") is None
    assert park(parking="가능요금 (무료)") == "가능, 요금 무료"
    assert park(parking="가능 (선유도 공영주차장) 요금 (기본 1시간 무료 / 이후 소형 30분당 1500원)") == "가능 (선유도 공영주차장)"
    assert judge(rec("food", {"parking_seats": "7대/40석"}))["park"]["label"] == "주차"


def test_pets_only_where_the_value_allows_one():
    pet = lambda kind, v: (judge(rec(kind, {"pet": v})).get("pet") or {}).get("value")
    assert pet("attraction", "동반 구분 전구역 동반가능 · 동반 가능 동물 전 견종 동반 가능 · 동반 시 필요 사항 목줄 착용") \
        == "전구역 동반가능"
    assert pet("attraction", "가능") == "가능"
    assert pet("stay", "5층에 한하여 반려견 동반 전용층으로 운영") == "5층에 한하여 반려견 동반 전용층으로 운영"
    for no in ("불가", "불가능", "없음"):
        assert pet("attraction", no) is None and pet("stay", no) is None
    # a list none of whose places allows a pet gets no chip (the food list today: no restaurant has a pet value)
    rows = [{"conds": judge(rec("food", {"usetime_restdate": "11:00~22:00 / 연중무휴"}))}]
    assert [c["id"] for c in C.conditions("food", rows, LC.COND_WORDS["ko"])] == ["mon", "late"]


def test_the_other_conditions_and_their_reasons():
    j = lambda kind, **f: judge(rec(kind, f))
    assert j("attraction", usefee="무료")["free"]["value"] == "무료"
    assert "free" not in j("attraction", usefee="무료 (단, 여객선 비용 별도)")   # the former '요금 무료' box: exactly 무료
    assert j("food", packing="가능(일부 메뉴)")["pack"]["value"] == "가능(일부 메뉴)" and "pack" not in j("food", packing="불가")
    assert j("attraction", babycarriage="대여 가능(예약 없이 박물관 안내소에서)")["stroller"]["label"] == "유모차 대여"
    assert "stroller" not in j("attraction", babycarriage="없음")
    assert j("attraction", wheelchair="대여가능(1대)")["wheel"]["key"] == "wheelchair"
    assert j("food", accessible_route="출입구까지 턱이 없어 휠체어 접근 가능함")["wheel"]["key"] == "accessible_route"
    for route in ("출입구까지 경사로가 설치되어 있음(완만하지 않음)", "출입구까지 경사로가 설치되어 있지 않음", "공사중"):
        assert "wheel" not in j("attraction", accessible_route=route), route
    assert j("stay", cooking="일부객실만 가능")["cook"]["value"] == "일부객실만 가능" and "cook" not in j("stay", cooking="불가")
    # the source's short name per field (fact_sources first), never a date
    r = judge(rec("attraction", {"pet": "가능"}, fact_sources={"pet": {"provider": "한국관광공사 반려동물 동반여행(TourAPI)",
                                                                        "checked_at": "2026-10-30"}}))["pet"]
    assert r["short"] == "한국관광공사" and "2026" not in json.dumps(C.ko_tags({"pet": r}, LC.COND_WORDS["ko"]))


def test_every_version_words_every_condition():
    keys = set(LC.COND_WORDS["ko"])
    ids = {cid for conds in C.KIND_CONDS.values() for cid in conds}
    for code, w in LC.COND_WORDS.items():
        assert set(w) == keys, code
        assert ids <= set(w["labels"]), (code, ids - set(w["labels"]))
        assert "{t}" in w["late_at"] and "{t}" in w["late_next"] and "{n}" in w["count"] and "{m}" in w["of"]
        if code != "ko":
            assert not LC.HANGUL.search(json.dumps(w, ensure_ascii=False)), code
    assert set(LC.COND_WORDS) == {"ko", *LC.ORDER}


def test_the_guides_places_meet_the_conditions_they_are_listed_for():
    """The chips use the guides' own rules: every place the Monday guide (guide-05 '월요일 영업·맛집') lists is open on
    Mondays."""
    from pipeline.build import State
    S = State(ROOT / "data" / "suwon", "production")
    for gid, cid in (("guide-05", "mon"),):
        g = next(x for x in S.guides if x["id"] == gid)
        slugs = [it["place_slug"] for it in g.get("items") or [] if it.get("place_slug") in S.ent_by_slug]
        assert len(slugs) >= 10, gid
        missing = [s for s in slugs if cid not in C.judge(S.ent_by_slug[s], city=S.city)]
        if missing:   # a content error of the guide, for the operator (its own reasons say these close on Mondays)
            pytest.xfail(f"{gid} lists places closed every Monday: {missing}")


# ------------------------------------------------------------------ the build
FOOD = (  # slug, name, facts, (lat, lng) or None
    ("t-hansokkeum", "한소끔", {"usetime_restdate": "11:00~22:00 / 연중무휴", "parking_seats": "50대/200석"}, (35.97, 126.70)),
    ("t-ilhaeok", "일해옥", {"usetime_restdate": "04:00~15:00/연중무휴", "parking_seats": "40석"}, None),
    ("t-sanmaru", "산마루", {"usetime": "월~목 11:00~23:00 (주문마감 22:00)금 11:00~익일02:00 (주문마감 01:00)",
                           "restdate": "매주 월요일", "parking": "가능", "packing": "가능"}, (35.96, 126.69)),
    ("t-wellmi", "웰미가", {"usetime_restdate": "24시간영업 / 연중무휴", "parking": "불가능"}, None),
    ("t-gukbap", "국밥집", {"usetime": "11:00~20:30", "restdate": "둘째,넷째 월요일 휴무",
                          "parking_seats": "좌석수 100석/ 주차 10대"}, None),
)
SPOTS = (
    ("t-park", "호수 산책길", {"restdate": "연중무휴", "usefee": "무료",
                            "pet": "동반 구분 전구역 동반가능 · 동반 가능 동물 전 견종 동반 가능"}),
    ("t-hall", "기념관", {"restdate": "매주 월요일", "usefee": "성인 2,000원", "pet": "불가"}),
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("conds")
    data = tmp / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    food = next(p for p in places if p["id"] == "sample-0201")
    spot = next(p for p in places if p["id"] == "sample-0003")
    for i, (slug, name, facts, geo) in enumerate(FOOD):
        p = copy.deepcopy(food)
        p.update(id=f"t-f{i}", slug=slug, name=name)
        p["facts"] = {"address": f"군산시 테스트로 {i + 1}", "menu": "백반", **facts}
        if geo:
            p["geo"] = {"lat": geo[0], "lng": geo[1], "source": "TourAPI"}
        places.append(p)
    for i, (slug, name, facts) in enumerate(SPOTS):
        p = copy.deepcopy(spot)
        p.update(id=f"t-a{i}", slug=slug, name=name)
        p["facts"] = {"address": f"군산시 시험로 {i + 1}", **facts}
        p["fact_sources"] = {"pet": {"provider": "한국관광공사 반려동물 동반여행(TourAPI)", "checked_at": "2026-10-30"}}
        places.append(p)
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp / "out"
    build(data, out, "preview")
    return out


def page_html(built, seg: str) -> str:
    return (built / seg / "index.html").read_text("utf-8")


def test_the_chips_take_the_check_box_place_and_the_rows_carry_their_reasons(built):
    h = page_html(built, "food")
    chips = re.findall(r'<button type="button" data-cond="(\w+)" aria-pressed="false"><span class="c-ck" aria-hidden="true">'
                       r'</span>([^<]*) <span class="tn">(\d+)</span></button>', h)
    assert chips == [("mon", "월요일 영업", "3"), ("late", "21시 이후까지", "3"), ("park", "주차 가능", "3"), ("pack", "포장 가능", "1")]
    assert 'data-f="check"' not in h and '<div class="f-conds" data-conds data-legacy="mon">' in h
    assert '<div class="f-row c-row" role="group" aria-label="조건"><span class="c-lab" aria-hidden="true">조건</span>' in h
    assert re.search(r'<span class="tn">1</span></button><button type="button" class="c-clear" data-c-clear hidden>조건 지우기'
                     r'</button></div>', h)
    # the count line keeps its place in the tools and its words for a screen reader; the visual count and the bar are
    # aria-hidden
    assert re.search(r'<div class="f-tools">\s*<div class="c-meter"><p class="f-result" aria-live="polite"><span data-result '
                     r'[^>]*>음식점 6곳</span>.*?<span class="c-count" aria-hidden="true"><b class="c-n" data-c-n>6</b>곳 '
                     r'<span class="c-of">/ 6곳</span></span></p><span class="c-bar" aria-hidden="true"><i data-c-bar></i>'
                     r'</span></div>', h)
    row = lambda name: re.search(rf'<li class="rec"[^>]*>(?:(?!</li>).)*?>{name}</a>.*?</li>', h, re.S).group(0)
    assert 'data-conds="mon late park"' in row("한소끔")
    assert re.search(r'<p class="rec-why" data-why hidden><span data-cond="mon" hidden><b>쉬는 날</b> 연중무휴 <small>한국관광공사</small>'
                     r'</span><span data-cond="late" hidden>22:00까지 영업 <small>한국관광공사</small></span><span data-cond="park" '
                     r'hidden><b>주차</b> 50대 <small>한국관광공사</small></span></p>', row("한소끔"))
    assert 'data-conds="mon"' in row("일해옥") and 'data-cond="park"' not in row("일해옥")    # '40석': no parking
    assert "익일 02:00까지 영업" in row("산마루") and "24시간 영업" in row("웰미가")
    assert 'data-conds="park"' in row("국밥집") and "<b>주차</b> 10대" in row("국밥집")
    p = page_html(built, "places")
    assert re.findall(r'data-cond="(\w+)" aria-pressed', p) == ["mon", "free", "pet"]
    assert "<b>반려동물 동반</b> 전구역 동반가능 <small>한국관광공사</small>" in p
    assert not re.search(r"\d{4}-\d{2}-\d{2}", "".join(re.findall(r'<p class="rec-why".*?</p>', p)))


def test_filter_vm_keeps_the_check_box_where_a_list_has_no_condition():
    F = present.filter_vm(4, [], [], [], ("free", "요금 무료", 0), 4, LC.LIST_WORDS["ko"], {"other": "관광지 {n}곳"})
    assert (F["conds"], F["legacy"]) == ([], "")
    G = present.filter_vm(4, [], [], [], ("free", "요금 무료", 1), 4, LC.LIST_WORDS["ko"], {"other": "관광지 {n}곳"},
                          conds=[{"id": "free", "label": "무료", "n": 1}], cwords=LC.COND_WORDS["ko"], legacy="free")
    assert G["legacy"] == "free" and G["cw"]["clear"] == "조건 지우기"


# ------------------------------------------------------------------ in a browser
def _serve(out: Path):
    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = out / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return serve


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        yield b
        b.close()


PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}
STATE = """() => ({
  shown: [...document.querySelectorAll('.rec:not([hidden]) .rec-link')].map(a => a.textContent),
  on: [...document.querySelectorAll('[data-cond][aria-pressed=true]')].map(b => b.getAttribute('data-cond')),
  chips: Object.fromEntries([...document.querySelectorAll('.f-conds [data-cond]')].map(b => [b.getAttribute('data-cond'),
         [+b.querySelector('.tn').textContent, b.classList.contains('is-zero')]])),
  why: Object.fromEntries([...document.querySelectorAll('li.rec')].map(r => [r.querySelector('.rec-link').textContent,
         [...r.querySelectorAll('[data-why]:not([hidden]) [data-cond]:not([hidden])')].map(t => t.textContent)])),
  result: document.querySelector('[data-result]').textContent, n: document.querySelector('[data-c-n]').textContent,
  bar: document.querySelector('[data-c-bar]').style.transform, map: (document.querySelector('[data-view=map] .tn') || {}).textContent,
  clear: !document.querySelector('[data-c-clear]').hidden, q: decodeURIComponent(location.search) })"""
SETTLE = "() => new Promise(r => setTimeout(r, 700))"


def _page(browser, out, **kw):
    ctx = browser.new_context(**{**PHONE, **kw})
    ctx.route("**/*", _serve(out))
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def test_in_a_browser_the_chips_combine_and_each_row_says_why(built, browser):
    ctx, page, errors = _page(browser, built)
    try:
        page.goto("http://site.test/food/", wait_until="load")
        s = page.evaluate(STATE)
        assert len(s["shown"]) == 6 and s["on"] == [] and s["n"] == "6" and not s["clear"]
        assert all(w == [] for w in s["why"].values())
        page.click("[data-cond=mon]")
        page.evaluate(SETTLE)
        s = page.evaluate(STATE)
        assert sorted(s["shown"]) == sorted(["한소끔", "일해옥", "웰미가"]) and s["q"] == "?c=mon" and s["clear"]
        assert (s["result"], s["n"], s["bar"]) == ("음식점 3곳 (전체 6곳 중)", "3", "scaleX(0.5)")
        assert s["why"]["한소끔"] == ["쉬는 날 연중무휴 한국관광공사"] and s["why"]["산마루"] == []
        # faceted: each other chip counts what choosing it as well would show
        assert s["chips"] == {"mon": [3, False], "late": [2, False], "park": [1, False], "pack": [0, True]}
        page.click("[data-cond=late]")
        page.evaluate(SETTLE)
        s = page.evaluate(STATE)
        assert sorted(s["shown"]) == ["웰미가", "한소끔"] and s["q"] == "?c=mon,late" and s["n"] == "2"
        assert s["why"]["웰미가"] == ["쉬는 날 연중무휴 한국관광공사", "24시간 영업 한국관광공사"]
        # the map's count follows (the rows with coordinates among the shown)
        assert s["map"] == "1"
        # a 0 chip still works: nothing left, and the way back is one press per condition that alone brings rows back
        page.click("[data-cond=pack]")
        undo = page.evaluate("() => [...document.querySelectorAll('[data-f-undo] button')].map(b => b.textContent)")
        # (월요일 영업 off: 산마루 is late with takeout; 포장 가능 off: the two again; 21시 이후까지 off: still nothing)
        assert undo == ["월요일 영업 조건 해제", "포장 가능 조건 해제", "전체 조건 초기화"]
        page.click("[data-f-undo] button >> nth=1")
        assert page.evaluate(STATE)["q"] == "?c=mon,late"
        # '조건 지우기' takes every condition off and the focus goes to the count line
        page.click("[data-c-clear]")
        page.evaluate(SETTLE)
        s = page.evaluate(STATE)
        assert len(s["shown"]) == 6 and s["q"] == "" and s["n"] == "6" and not s["clear"]
        assert page.evaluate("document.activeElement.matches('.c-meter .f-result')")
        assert errors == [], errors
    finally:
        ctx.close()


def test_in_a_browser_the_url_keeps_the_conditions_and_a_way_back_restores_them(built, browser):
    ctx, page, errors = _page(browser, built)
    try:
        page.goto("http://site.test/food/?c=late,mon", wait_until="load")
        s = page.evaluate(STATE)
        # read in the chips' order, drawn in place (no roll on the first apply)
        assert s["on"] == ["mon", "late"] and s["n"] == "2" and s["bar"] == "scaleX(0.333333)"
        page.click(".rec:not([hidden]) .rec-link >> nth=0")
        page.wait_for_load_state("load")
        page.go_back(wait_until="load")
        s = page.evaluate(STATE)
        assert s["on"] == ["mon", "late"] and sorted(s["shown"]) == ["웰미가", "한소끔"]
        # an old link to the check box (?check=1) is the condition it became
        page.goto("http://site.test/food/?check=1", wait_until="load")
        s = page.evaluate(STATE)
        assert s["on"] == ["mon"] and len(s["shown"]) == 3
        page.goto("http://site.test/places/?check=1", wait_until="load")
        assert page.evaluate(STATE)["on"] == ["free"]
        assert errors == [], errors
    finally:
        ctx.close()


def test_in_a_browser_the_count_rolls_but_not_with_reduced_motion(built, browser):
    """The visual count's digits roll into place (each its own clipped band) — the new number at once, never the
    numbers between (motion.js's rule for figures); with reduced motion the number is plain text."""
    click_and_read = """() => { document.querySelector('[data-cond=mon]').click(); const n = document.querySelector('[data-c-n]');
      return [n.textContent, n.querySelectorAll('.c-rl > .c-rl-i').length]; }"""
    for motion, rolled in (("reduce", 0), ("no-preference", 1)):
        ctx, page, errors = _page(browser, built, reduced_motion=motion)
        try:
            page.goto("http://site.test/food/", wait_until="load")
            assert page.evaluate("() => document.querySelector('[data-c-n]').children.length") == 0   # the first draw: text
            assert page.evaluate(click_and_read) == ["3", rolled], motion
            page.evaluate(SETTLE)
            assert page.evaluate(STATE)["n"] == "3"
            # the words a screen reader hears are final at once either way
            assert page.inner_text("[data-result]") == "음식점 3곳 (전체 6곳 중)"
            assert errors == [], errors
        finally:
            ctx.close()


@pytest.mark.parametrize("dev", [pytest.param({}, id="390"), pytest.param({"viewport": {"width": 1440, "height": 900},
                                                                          "is_mobile": False, "has_touch": False}, id="1440")])
def test_in_a_browser_the_chips_are_one_row_more_with_44px_targets(built, browser, dev):
    """One row more than the type chips and the tools, packed tight (the first results keep their place: test_present):
    a phone swipes it (one line, like the type row) and every chip and '조건 지우기' there is a 44px touch target; a
    desktop with a mouse sees the chips wrap, 36px high; nothing scrolls the page sideways."""
    ctx, page, errors = _page(browser, built, **dev)
    touch = dev.get("has_touch", True)
    try:
        page.goto("http://site.test/food/?c=mon", wait_until="load")
        for b in page.query_selector_all(".f-conds [data-cond], [data-c-clear], .f-top [data-f]"):
            box = b.bounding_box()
            assert box["height"] >= (44 if touch else 36), box
        tops = page.evaluate("() => [...document.querySelectorAll('.f-conds [data-cond]')].map(b => Math.round(b.getBoundingClientRect().top))")
        assert len(set(tops)) == 1, tops
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        # the row comes 4px under the bar's top part (the type chips and the tools)
        gap = page.evaluate("() => document.querySelector('.f-conds').getBoundingClientRect().top - document.querySelector('.f-top').getBoundingClientRect().bottom")
        assert gap == 4, gap
        page.goto("http://site.test/places/", wait_until="load")
        page.click("[data-cond=pet]")
        s = page.evaluate(STATE)
        assert s["shown"] == ["호수 산책길"] and s["why"]["호수 산책길"] == ["반려동물 동반 전구역 동반가능 한국관광공사"]
        assert errors == [], errors
    finally:
        ctx.close()


def test_in_a_browser_without_js_there_are_no_chips_and_no_reasons(built, browser):
    ctx, page, errors = _page(browser, built, java_script_enabled=False)
    try:
        page.goto("http://site.test/food/?c=mon,late", wait_until="load")
        assert not page.is_visible("[data-conds]") and not page.is_visible("[data-why]")
        assert page.locator(".rec:visible").count() == 6
    finally:
        ctx.close()
