"""/sun/ 군산 일출·일몰 시간 and /transport/ 군산 교통 시간표 (pipeline/timetables.py, templates/sun.html.j2 ·
transport.html.j2; operator 2026-10-31). The view models read almanac.json / transport_tago.json and never guess:
figures are computed from the table's own values, a pair TAGO returned nothing for reads '이 자료(TAGO)에 없음 — 운수사
확인' (never '운행 없음'), a flight's 0 fare is never printed, the tide block exists only with tide data. The pages are
real tables (caption, th scope), answer first in absolute dates (never '오늘' in the HTML), with WebPage + BreadcrumbList
+ Dataset whose every string is on the page, and no check date anywhere (operator decision 2026-10-09). Synthetic files
are written to a temporary folder; the page tests render with the real data/gunsan State (never writing into it)."""
import datetime as dt
import json
import re
import types
from pathlib import Path

import pytest

from pipeline import build as B
from pipeline import timetables as T
from pipeline.validate import PageScan, _graph_nodes, jsonld_visibility, visible_check_dates

DATA = Path(__file__).resolve().parent.parent / "data" / "gunsan"


def ns(today="2026-10-31", almanac=None, transport=None, entities=(), guides=None, region="군산"):
    return types.SimpleNamespace(today=today, almanac=almanac or {}, transport=transport or {}, entities=list(entities),
                                 guide_by_id=guides or {}, site={"region": region}, site_url="https://example.test",
                                 abs=lambda p: "https://example.test" + p)


def sun_days(start="2026-10-30", n=70, rise0=414, set0=1059):
    """Synthetic sun days: sunrise one minute later a day, sunset one minute earlier until day 30, then back."""
    d0 = dt.date.fromisoformat(start)
    out = {}
    for k in range(n):
        r = rise0 + min(k, 40)
        s = set0 - min(k, 30) + max(0, k - 50)
        hm = lambda m: f"{m // 60:02d}:{m % 60:02d}"   # noqa: E731
        out[(d0 + dt.timedelta(days=k)).isoformat()] = {"sunrise": hm(r), "sunset": hm(s), "civil_dawn": hm(r - 26),
                                                         "civil_dusk": hm(s + 26)}
    return out


ALM = {"sources": {"sun": {"provider": "한국천문연구원", "dataset": "한국천문연구원_출몰시각 정보", "location": "군산",
                           "url": "https://www.data.go.kr/data/15012688/openapi.do", "lat": 35.966666, "lng": 126.733333,
                           "checked_at": "2026-10-31"}}}


# ----------------------------------------------------------------------------- /sun/ view model
def test_sun_rows_start_at_the_build_day_with_absolute_dates():
    V = T.sun_vm(ns(almanac={**ALM, "sun": sun_days()}))
    assert V["rows"][0]["iso"] == "2026-10-31"                       # the day before the build day is left out
    assert V["lead"]["lab"] == "10월 31일(토)" and V["lead"]["rise"] == "06:55"
    assert V["coverage"] == f"2026-10-31/{V['rows'][-1]['iso']}" and V["n"] == len(V["rows"])
    assert [m["label"] for m in V["months"]][:3] == ["2026년 10월", "2026년 11월", "2026년 12월"]
    # the first month has one row: the next one opens with it; the rest are folded
    assert [m["open"] for m in V["months"]] == [True, True, False, False][:len(V["months"])]


def test_sun_facts_come_from_the_table_values_only():
    V = T.sun_vm(ns(almanac={**ALM, "sun": sun_days()}))
    rows = V["rows"]
    facts = {f["k"]: f for f in V["facts"]}
    early = facts["해가 가장 일찍 지는 때"]
    assert early["v"] == min(r["set"] for r in rows)
    late = facts["해가 가장 늦게 뜨는 때"]
    assert late["v"] == max(r["rise"] for r in rows)
    short = facts["낮이 가장 짧은 때(일출~일몰)"]
    assert short["v"] == T.dur(min(r["day"] for r in rows))
    assert re.fullmatch(r"\d{1,2}월 \d{1,2}일\(.\)~\d{1,2}월 \d{1,2}일\(.\)( 중 \d+일)?", early["when"])
    jan = facts["2027년 1월 1일 해 뜨는 시각"]
    assert jan["v"] == next(r["rise"] for r in rows if r["iso"] == "2027-01-01")


def test_when_reads_a_run_a_day_or_days_in_a_span():
    r = lambda iso: {"d": dt.date.fromisoformat(iso)}   # noqa: E731
    assert T.when([r("2026-12-22")]) == "12월 22일(화)"
    assert T.when([r("2026-11-29"), r("2026-11-30"), r("2026-12-01")]) == "11월 29일(일)~12월 1일(화)"
    assert T.when([r("2026-12-16"), r("2026-12-18"), r("2026-12-20")]) == "12월 16일(수)~12월 20일(일) 중 3일"


def test_no_sun_page_without_days_ahead():
    assert T.sun_vm(ns(almanac={})) is None
    assert T.sun_vm(ns(today="2027-03-01", almanac={**ALM, "sun": sun_days()})) is None   # every day is past


def place(name, kind="attraction", **kw):
    return {"id": name, "name": name, "kind": kind, "_path": f"/places/{name}/", "_type": "섬", "_area": "옥도면", **kw}


def test_sunset_spots_from_our_own_sentences_only():
    es = [place("장자도", summary="장자도는 섬입니다. 다리 위에서는 해넘이가 보입니다."),
          place("말랭이마을", faq=[{"q": "노을을 볼 수 있나요?", "a": "볼 수 있습니다. 해 질 녘 노을과 밤 경관을 볼 수 있습니다."}]),
          place("불주사 대웅전", faq=[{"q": "언제 볼 수 있나요?", "a": "일출부터 일몰까지 둘러볼 수 있습니다."}],
                facts={"usetime": "일출~일몰"}),
          place("라비치호텔", kind="stay", details=[{"text": "해넘이가 보이는 방이 있습니다."}]),
          place("선유도", details=[{"text": "고군산 8경은 선유낙조 등이며 5경이 선유도에 있습니다."}],
                tourapi={"overview": "노을"})]
    spots = T.sunset_spots(ns(entities=es))
    assert [x["name"] for x in spots] == ["말랭이마을", "선유도", "장자도"]   # opening hours and a stay are not spots
    assert spots[0]["line"] == "해 질 녘 노을과 밤 경관을 볼 수 있습니다."
    assert spots[2]["line"] == "다리 위에서는 해넘이가 보입니다."


TIDE = {"DT_0018": {"name": "군산", "lat": 35.975, "lng": 126.563, "days": {
    "2026-10-30": [{"time": "21:40", "type": "간조", "level_cm": 120}],
    "2026-10-31": [{"time": "03:12", "type": "만조", "level_cm": 612}, {"time": "09:30", "type": "간조", "level_cm": 98},
                   {"time": "15:40", "type": "만조", "level_cm": 640}, {"time": "21:58", "type": "간조", "level_cm": 110}],
    "2026-11-01": [{"time": "03:50", "type": "고조", "level_cm": 600}]}}}
TIDE_SRC = {"provider": "해양수산부 국립해양조사원", "dataset": "해양수산부 국립해양조사원_조석예보(고, 저조)",
            "url": "https://www.data.go.kr/data/15156018/openapi.do", "checked_at": "2026-10-31"}


def test_tide_block_only_with_tide_data():
    assert T.tide_vm(ns(almanac={**ALM, "sun": sun_days()})) is None
    alm = {"sources": {**ALM["sources"], "tide": TIDE_SRC}, "sun": sun_days(), "tide": TIDE}
    V = T.tide_vm(ns(almanac=alm))
    st = V["stations"][0]
    assert st["name"] == "군산" and st["first"] == "2026-10-31"            # the day before the build day is left out
    d = st["months"][0]["rows"][0]
    assert [(p["t"], p["cm"]) for p in d["high"]] == [("03:12", 612), ("15:40", 640)]
    assert [p["t"] for p in d["low"]] == ["09:30", "21:58"]
    assert V["lic"]["name"] == "공공누리 제1유형(출처표시)" and V["lic"]["url"].startswith("https://www.kogl.or.kr/")


# ----------------------------------------------------------------------------- /transport/ view model
@pytest.fixture(scope="module")
def tago():
    f = DATA / "transport_tago.json"
    if not f.exists():
        pytest.skip("transport_tago.json not built yet")
    return json.loads(f.read_text("utf-8"))


@pytest.fixture(scope="module")
def tv(tago):
    return T.transport_vm(ns(transport=tago))


def test_transport_days_and_modes(tv):
    assert [d["iso"] for d in tv["days"]] == ["2026-11-01", "2026-11-02"] and tv["both"] == "11월 1일(일)·2일(월)"
    assert [m["label"] for m in tv["modes"]] == ["열차", "고속버스", "시외버스", "항공"]
    assert tv["coverage"] == "2026-11-01/2026-11-02"


def test_transport_summaries_match_the_routes(tv, tago):
    routes = {(r["mode"], r["from"], r["to"], r["day"]): r for r in tago["routes"]}
    for m in tv["modes"]:
        for c in m["cards"]:
            for d in c["dirs"]:
                if d["none"]:
                    continue
                keys = [k["key"] for k in tv["days"]]
                for col, key in zip(d["cols"], keys if len(d["cols"]) > 1 else keys[:1]):
                    r = routes[(m["mode"], d["from"], d["to"], key)]
                    assert col["s"]["n"] == r["count"]
                    assert col["s"]["first"].startswith(r["first"]) and col["s"]["last"].startswith(r["last"])
                    assert sum(len(L["rows"]) for L in d["lists"] if L["lab"] == col["lab"] or L["same"]) == r["count"]


def test_transport_train_fare_and_next_day(tv):
    train = tv["modes"][0]
    out = {(d["from"], d["to"]): d for c in train["cards"] for d in c["dirs"]}
    s = out[("군산", "용산")]["cols"][0]["s"]
    assert s["fare"] == "21,600원(무궁화호·새마을호)" and s["span"] == "05:34–20:26" and s["count"] == "15회"
    assert out[("군산", "익산")]["cols"][0]["s"]["last"] == "00:12(다음 날)"   # departs past midnight
    assert "등급 구분 없이" in train["note"] and "코레일" in train["note"]
    assert train["missing"] == ["군산↔대전", "군산↔서대전"]


def test_transport_flight_has_no_fare(tv):
    fl = tv["modes"][-1]
    d = fl["cards"][0]["dirs"][0]
    assert d["no_fare"] and not any(c["s"]["fare"] for c in d["cols"])
    assert all(r["fare"] == "" for L in d["lists"] for r in L["rows"])
    assert fl["note"].startswith("확인 필요: 요금")


def test_transport_missing_direction_said_once(tv):
    ic = next(m for m in tv["modes"] if m["mode"] == "intercity_bus")
    assert ic["none_ways"] == ["군산 → 각 도착지"] and ic["single"]
    assert all(len(c["dirs"]) == 1 and c["dirs"][0]["to"] == "군산" for c in ic["cards"])
    assert ic["cards"][0]["title"] == "김제 → 군산"
    ex = next(m for m in tv["modes"] if m["mode"] == "express_bus")
    seoul = ex["cards"][0]["dirs"][0]
    assert [c["lab"] for c in seoul["cols"]] == ["11월 1일(일)", "11월 2일(월)"]   # the two days differ
    assert [c["s"]["count"] for c in seoul["cols"]] == ["55회", "51회"]


def test_transport_tiles_answer_first(tv):
    tiles = {t["label"]: t for t in tv["tiles"]}
    assert tiles["열차"]["route"] == "군산 → 용산" and tiles["열차"]["count"] == "15회"
    assert tiles["고속버스"]["count"] == "51~55회"
    assert tiles["시외버스"]["route"].endswith("→ 군산")     # no departure from Gunsan in the source
    assert tiles["항공"]["count"] == "2편"


def test_portal_license():
    assert T.portal_license("https://www.data.go.kr/data/15098552/openapi.do")["name"] == "이용허락범위 제한 없음"
    assert T.portal_license("https://example.test/") is None


# ----------------------------------------------------------------------------- the pages, rendered with the real data
@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not (DATA / "almanac.json").exists() or not (DATA / "transport_tago.json").exists():
        pytest.skip("almanac.json / transport_tago.json not built yet")
    S = B.State(DATA, "preview")
    S.today = "2026-10-31"     # the data's first day (the tests do not age with the clock)
    S.tt_sun, S.tt_transport = T.sun_vm(S), T.transport_vm(S)
    env = B.make_env()
    env.globals["kakao_sdk"] = B.kakao_sdk_url(S.site)
    out = tmp_path_factory.mktemp("tt")

    def render(V, make, path, tpl, kind):
        P = make(S, V)
        page = {k: P[k] for k in ("title", "description", "canonical", "crumbs", "ds_name", "ds_desc")}
        page["jsonld"] = [B.jsonld.dumps(P["graph"])]
        B._render(env, S, out, tpl, path, page, kind, None, V=V)
        return (out / path.strip("/") / "index.html").read_text("utf-8")
    return types.SimpleNamespace(S=S, env=env, out=out, render=render)


def scan(html):
    p = PageScan()
    p.feed(html)
    return p


def check_page(html):
    p = scan(html)
    nodes, errs = _graph_nodes(p.jsonld_raw)
    assert not errs and jsonld_visibility(nodes, p) == []
    seen = " ".join([p.visible, p.meta.get("description", ""), p.meta.get("og:description", "")])
    assert visible_check_dates(seen) == []
    assert len(p.meta.get("description", "")) <= B.DESC_MAX
    types_ = [n.get("@type") for n in nodes]
    assert {"WebPage", "BreadcrumbList", "Dataset"} <= set(types_)
    ds = next(n for n in nodes if n.get("@type") == "Dataset")
    assert ds["creator"]["name"] == ds["publisher"]["name"] and ds["isBasedOn"] and ds["dateModified"] == "2026-10-31"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}", ds["temporalCoverage"])
    # real tables: every one has a caption and its header cells a scope
    for t in re.findall(r"<table.*?</table>", html, re.S):
        assert "<caption" in t
        assert not re.search(r"<th(?=[\s>])(?![^>]*scope=)", t)
    return p, nodes


def test_sun_page(built):
    html = built.render(built.S.tt_sun, T.sun_page, T.SUN_PATH, "sun.html.j2", "sun")
    p, nodes = check_page(html)
    assert "10월 31일(토)" in p.body and "해 뜨는 시각 06:54" in p.body and "해 지는 시각 17:39" in p.body
    assert "오늘" not in p.body                         # sun.js adds it on the visitor's own date
    assert "data-sun" in html and 'data-d="2026-11-01"' in html
    assert "1~2분 다를 수 있습니다" in p.body and "한국천문연구원" in p.body
    # the tides (국립해양조사원 조석예보, filled 2026-10-31 once the agency's server answered again): one table per
    # station and month, each with its caption, and the data box names the provider
    assert "바다 물때" in p.body and "관측소 5곳" in p.body and "국립해양조사원" in p.body
    caps = re.findall(r"<caption>([^<]*만조·간조)</caption>", html)
    assert {c.split()[0] for c in caps} == {"군산", "말도", "연도항", "어청도", "위도"}, caps[:3]
    assert 'id="h-tide-data"' in html
    assert re.search(r'<a href="/places/[^"]+/"[^>]*>장자도</a>', html)   # a sunset spot links its page
    assert p.title.startswith("군산 일출·일몰·물때 시간표")   # with the tides, the title names them too


def test_sun_page_with_tides(built, monkeypatch):
    S = built.S
    monkeypatch.setattr(S, "almanac", {**S.almanac, "sources": {**S.almanac["sources"], "tide": TIDE_SRC}, "tide": TIDE})
    V = T.sun_vm(S)
    html = built.render(V, T.sun_page, T.SUN_PATH, "sun.html.j2", "sun")
    p, nodes = check_page(html)
    assert "군산 관측소" in p.body and "03:12" in p.body and "612cm" in p.body
    assert sum(n.get("@type") == "Dataset" for n in nodes) == 2
    assert "공공누리 제1유형(출처표시)" in p.body


def test_transport_page(built):
    html = built.render(built.S.tt_transport, T.transport_page, T.TRANSPORT_PATH, "transport.html.j2", "transport")
    p, nodes = check_page(html)
    assert "2026년 11월 1일(일)·2일(월) 하루 배차입니다" in p.body
    assert "이 자료(TAGO)에 없음 — 운수사 확인" in p.body and "운행 없음" not in p.body
    assert " 0원" not in p.body and "확인 필요: 요금" in p.body
    assert "<details class=\"tp-all\">" in html and "00:12(다음 날)" in p.body
    for gid in ("guide-12", "guide-33", "guide-31"):   # the guides on getting here are linked
        g = built.S.guide_by_id.get(gid)
        if g:
            assert f'href="{g["_path"]}"' in html
    assert p.title.startswith("군산 교통 시간표")


def test_footer_and_llms(built):
    S = built.S
    html = built.render(S.tt_transport, T.transport_page, T.TRANSPORT_PATH, "transport.html.j2", "transport")
    assert 'href="/sun/"' in html and 'href="/transport/"' in html          # the footer's links, on every Korean page
    short = "\n".join(T.llms_short(S, S.tt_sun, S.tt_transport))
    full = "\n".join(T.llms_full(S, S.tt_sun, S.tt_transport))
    assert S.abs("/sun/") in short and S.abs("/transport/") in short
    assert "- 10월 31일(토): 시민박명 시작 06:28, 일출 06:54, 일몰 17:39" in full
    assert "- 군산 → 용산 열차: 15회, 첫차 05:34, 막차 20:26" in full
    assert visible_check_dates(short) == [] and visible_check_dates(full) == []


def test_place_day_card_links_the_sun_page(built):
    S = built.S
    e = next(e for e in S.entities if e["name"] == "장자도")
    ctx = B.entity_ctx(e, S)
    T_ = ctx["p"]["today"]
    assert T_ and T_["sun"] and T_["sun_page"] == "/sun/"
    html = built.env.get_template("_today.html.j2").module.card(T_, e["name"])
    assert 'href="/sun/"' in str(html)


def test_dataset_nodes_name_outside_pages_only_with_sameas():
    """production validate: every JSON-LD url/@id/item starts with site_url — the portal and the licence page are
    outside pages, so a Dataset names them with sameAs / isBasedOn (2026-10-31 production build)."""
    from pipeline import timetables as T

    def walk(o, key=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from walk(v, k)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v, key)
        elif key in ("url", "@id", "item"):
            yield o
    lic = {"name": "이용허락범위 제한 없음", "url": "", "portal": "https://www.data.go.kr/data/15012688/openapi.do"}
    node = T.dataset_node("https://gunsan.webforai.kr/sun/", "sun", "n", "d", "한국천문연구원",
                          ["https://www.data.go.kr/data/15012688/openapi.do"], "2026-10-31/2027-02-27", "2026-10-31",
                          ["일출"], lic)
    assert all(str(u).startswith("https://gunsan.webforai.kr/") for u in walk(node))
