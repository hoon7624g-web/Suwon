"""tools/watch_updates.py — 군산시 보도자료·TourAPI 행사·인허가 폐업·조석예보·집중률 기간 점검. 네트워크 없이 작은 고정
응답(실제 응답 모양 그대로)으로만 본다: 목록·상세 읽기, 지난 번호까지만 내려가기, 이미 쓴 보도자료 알아보기, 행사의 새것·
바뀐 일정, 공개 장소의 새 폐업, 재시도·호출 상한·키 가림, 보고서·상태 파일, 데이터 파일을 고치지 않는 것."""
import datetime as dt
import json
import urllib.error
import urllib.parse

import pytest

from tools import mois_licenses_gunsan as L
from tools import watch_updates as W

KEY = "abc+def/ghi=="


def press_row(no, seq, title, dept, date, views="3"):
    """One list row as eminwon writes it (2026-10-31)."""
    cell = f'style="cursor:hand;" onclick="javaScript:searchDetail(\'{no}\')"'
    return (f'<tr bgColor="#FFFFFF" onmouseover=\'this.style.backgroundColor="#FEF5EC";\'>\n'
            f'<td width="40" height="22" align="center" {cell}>{seq}</td>\n'
            f'<td align="left" {cell}><p align=left>{title}</p></td>\n'
            f'<td align="center" {cell}>{dept}</td>\n<td align="center" {cell} >{date}</td>\n'
            f'<td align="center" {cell} >{views}</td>\n</tr>\n<tr><Td colspan=5 height=1></td></tr>\n')


def press_page(rows, total=34334):
    return ('﻿<html><head><title>보도 및 대응자료</title></head><body><table>'
            f'<tr><TD colspan=8><font color="046D83">전체게시물:{total}개 \n 페이지:1/10</font></td></tr>'
            '<tr height=23><th>번호</th><th>제목</th><th>작성부서</th><th>등록일</th><th>조회수</th></tr>'
            + "".join(press_row(*r) for r in rows) + "</table></body></html>")


DETAIL = ('﻿<html><body><table><tr>\n<td width="100" height="22" align="center" bgcolor=BAE6E7>작성부서</td>\n'
          '<td width="285" bgcolor="#F5FAF5">관광진흥과</td>\n<td width="100" align="center" bgcolor=BAE6E7>등록일자</td>\n'
          '<td width="285" bgcolor="#F5FAF5">2026-10-27</td>\n</tr><tr>\n<td width="100" align="center" bgcolor=BAE6E7>제목'
          '</td>\n<td bgcolor="#F5FAF5" colspan="3">군산 내항 밤하늘 물들이는 해상 불꽃쇼… ‘2026 군산불꽃축제’ 11월 14일 '
          '개최</td>\n</tr><tr> \n<TD style=\'word-break:break-all;\' colspan=4>늦가을&nbsp;군산&nbsp;내항의&nbsp;밤하늘.'
          '<br><br>재단은&nbsp;11월&nbsp;14일(토)&nbsp;오후&nbsp;8시&nbsp;개최한다.</TD>\n</tr><tr><TD>'
          '<a href="javascript:goDownLoad(\'1.[관광진흥과] 군산불꽃축제 개최.hwpx\',\'x.hwpx\',\'/ntishome\')">1</a>'
          '</TD></tr></table></body></html>')

FEST = {"response": {"header": {"resultCode": "0000", "resultMsg": "OK"}, "body": {"items": {"item": [
    {"contentid": "1846797", "title": "군산시간여행축제", "eventstartdate": "20261002", "eventenddate": "20261005",
     "modifiedtime": "20261019140011", "addr1": "전북특별자치도 군산시 중앙로1가", "tel": "063-454-3305"},
    {"contentid": "3999999", "title": "군산 겨울빛 축제", "eventstartdate": "20261205", "eventenddate": "20261231",
     "modifiedtime": "20261030100000", "addr1": "전북특별자치도 군산시 장미동", "tel": ""}]},
    "numOfRows": 100, "pageNo": 1, "totalCount": 2}}}

TIDE_OK = ('<response><header><resultCode>00</resultCode><resultMsg>NORMAL_SERVICE</resultMsg></header><body><items>'
           '<item><obsvtrNm>군산</obsvtrNm><lot>126.56305</lot><lat>35.97555</lat><predcDt>2026-10-31 06:58</predcDt>'
           '<predcTdlvVl>612.0</predcTdlvVl><extrSe>1</extrSe></item></items><totalCount>1</totalCount></body></response>')
GW_XML = ('<?xml version="1.0" encoding="UTF-8"?><OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>HTTP_ERROR</errMsg>'
          '<returnAuthMsg>HTTP 에러</returnAuthMsg><returnReasonCode>04</returnReasonCode></cmmMsgHeader>'
          '</OpenAPI_ServiceResponse>')


def mois_page(items, total=None):
    return json.dumps({"response": {"header": {"resultCode": "0", "resultMsg": "정상"}, "body": {
        "items": {"item": items}, "numOfRows": 100, "pageNo": 1,
        "totalCount": len(items) if total is None else total}}}, ensure_ascii=False)


def lic_raw(name, road, code="01", mng="1", closed="", lcpmt="2020-01-01"):
    return {"MNG_NO": mng, "BPLC_NM": name, "ROAD_NM_ADDR": road, "LOTNO_ADDR": "", "SALS_STTS_CD": code,
            "SALS_STTS_NM": {"01": "영업/정상", "02": "휴업", "03": "폐업"}[code], "LCPMT_YMD": lcpmt,
            "CLSBIZ_YMD": closed, "TELNO": "063-445-0000", "CRD_INFO_X": "", "CRD_INFO_Y": "",
            "DAT_UPDT_PNT": "2026-11-05 22:39:00"}


class Fake:
    """opener(url, data, timeout) -> bytes: answers by a part of the URL (and the POST form's method)."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, data, timeout):
        form = urllib.parse.parse_qs(data.decode()) if data else {}
        self.calls.append((url, form))
        for match, answer in self.routes:
            if match(url, form):
                out = answer(url, form) if callable(answer) else answer
                if isinstance(out, Exception):
                    raise out
                return out.encode("utf-8")
        raise AssertionError(f"unexpected call {url} {form}")


def is_list(page):
    return lambda url, f: f.get("method") == ["selectListOfrNews"] and f.get("pageIndex") == [str(page)]


def net(fake, max_calls=50):
    return W.Net(W.Budget(max_calls), (KEY,), opener=fake, sleep=lambda s: None)


# ---------------------------------------------------------------- press

def test_list_and_detail_pages_are_read_as_written():
    total, rows = W.parse_press_list(press_page([("35276", "34334", "(재)군산먹거리통합지원센터, 센터장 임명",
                                                  "행정지원과", "2026-10-29"),
                                                 ("35242", "34300", ("군산 내항 밤하늘 물들이는 해상 불꽃쇼… ‘2026 "
                                                                     "군산불꽃축제’ 11월..."), "관광진흥과", "2026-10-27",
                                                  "10")]))
    assert total == 34334
    assert rows[1] == {"no": "35242", "seq": "34300", "title": "군산 내항 밤하늘 물들이는 해상 불꽃쇼… ‘2026 군산불꽃축제’ "
                       "11월...", "dept": "관광진흥과", "date": "2026-10-27", "views": "10"}
    d = W.parse_press_detail(DETAIL, "35242")
    assert d["title"] == "군산 내항 밤하늘 물들이는 해상 불꽃쇼… ‘2026 군산불꽃축제’ 11월 14일 개최"
    assert (d["dept"], d["date"]) == ("관광진흥과", "2026-10-27")
    assert d["body"] == "늦가을 군산 내항의 밤하늘.\n\n재단은 11월 14일(토) 오후 8시 개최한다."
    assert d["attachments"] == ["1.[관광진흥과] 군산불꽃축제 개최.hwpx"]
    assert W.body_dates(d["body"]) == ["11월 14일(토)"]


def test_new_press_goes_down_to_the_last_number_seen_and_says_when_it_could_not():
    p1 = press_page([("35276", "3", "a 축제", "관광진흥과", "2026-10-29"), ("35275", "2", "b", "옥산면", "2026-10-29")])
    p2 = press_page([("35274", "1", "c 개장", "항만해양과", "2026-10-28"), ("35270", "0", "d", "x", "2026-10-27")])
    fake = Fake([(is_list(1), p1), (is_list(2), p2)])
    rows, complete, err = W.new_press(net(fake), 35270, "2026-10-01", max_pages=5)
    assert [r["no"] for r in rows] == ["35276", "35275", "35274"] and complete and not err
    rows, complete, err = W.new_press(net(fake), 35000, "2026-10-01", max_pages=1)
    assert not complete and "max-press-pages" in err
    # no number yet: the date decides
    rows, complete, _ = W.new_press(net(fake), None, "2026-10-29", max_pages=5)
    assert [r["no"] for r in rows] == ["35276", "35275"] and complete


def test_check_press_keeps_travel_titles_and_knows_the_numbers_events_json_cites():
    p1 = press_page([("35276", "3", "‘2026 군산불꽃축제’ 안전 개최 회의", "관광진흥과", "2026-10-29"),
                     ("35275", "2", "착한가게 현판 전달", "옥산면", "2026-10-29"),
                     ("35242", "1", "해상 불꽃쇼… ‘2026 군산불꽃축제’ 11월...", "관광진흥과", "2026-10-27"),
                     ("35100", "0", "old", "x", "2026-09-28")])
    fake = Fake([(is_list(1), p1), (lambda u, f: f.get("method") == ["selectOfrNews"], DETAIL)])
    events = [{"id": "fest-a", "source_news_epct_no": "35242", "also_sources": []},
              {"id": "fest-b", "source_name": "군산시 보도자료 '…' (관광진흥과, 2026-10-29, 보도자료 번호 35276)"}]
    res = W.check_press(net(fake), {"last_no": 35100}, events, "2026-10-01", 5, 10)
    assert res["complete"] and res["last_no"] == 35276 and res["rows"] == 3
    assert [(h["no"], h["in_events"]) for h in res["hits"]] == [("35276", "fest-b"), ("35242", "fest-a")]
    assert res["hits"][0]["dates"] == ["11월 14일(토)"]


def test_travel_titles_strong_words_win_weak_words_yield_to_skip_words():
    assert W.travel_words("군산시, 고군산섬잇길 공식 개통 기념 SNS 이벤트 진행")[:2] == ["개통", "섬잇길"]
    assert W.travel_words("군산시, 올해 마지막 ‘GO! 군산 섬해진미’ 참가자 모집")
    assert W.travel_words("전 세계 클라이밍 최고 선수들 모인다… 군산시, ‘2026 월드클라이밍’...") == ["클라이밍"]
    assert W.travel_words("군산시간여행축제, ‘2026 세계축제협회 피너클 어워드’ 은상 수상")   # strong beats '수상'
    assert W.travel_words("(재)군산먹거리통합지원센터, 제3대 최철원 센터장 임명") == []
    assert W.travel_words("군산시, 대한민국 평생학습도시 ‘좋은 정책상’ 수상") == []
    assert W.travel_words("군산시립도서관, 2026년 도서관 운영 유공 ‘문화체육관광부 장관표창’ 수상") == []
    assert W.travel_words("HD현대중공업 군산조선소, 혹서기 맞아 3,000만 원 상당 보양식 식품 기탁") == []


def test_a_failed_detail_is_skipped_and_the_rest_are_still_read():
    p1 = press_page([("35276", "3", "축제 개최", "x", "2026-10-29"), ("35275", "2", "공연 개최", "x", "2026-10-29"),
                     ("35100", "0", "old", "x", "2026-09-28")])

    def detail(url, form):
        return ConnectionResetError(104, "reset") if form["news_epct_no"] == ["35276"] else DETAIL
    fake = Fake([(is_list(1), p1), (lambda u, f: f.get("method") == ["selectOfrNews"], detail)])
    res = W.check_press(net(fake), {"last_no": 35100}, [], "2026-10-01", 5, 10)
    assert "body" not in res["hits"][0] and res["hits"][1]["body"].startswith("늦가을")
    assert res["details_error"].startswith("상세 35276: ConnectionResetError")
    assert res["complete"] and res["last_no"] == 35276   # the list itself was read to the end


def test_an_unfinished_press_scan_does_not_move_the_last_number():
    fake = Fake([(is_list(1), press_page([("35276", "3", "축제", "x", "2026-10-29")])),
                 (is_list(2), ConnectionResetError(104, "Connection reset by peer"))])
    res = W.check_press(net(fake), {"last_no": 35000}, [], "2026-10-01", 5, 0)
    assert not res["complete"] and res["last_no"] == 35000 and "ConnectionResetError" in res["error"]


# ---------------------------------------------------------------- network

def test_dropped_connections_are_retried_counted_and_the_key_masked():
    seen = []

    def flaky(url, data, timeout):
        seen.append(url)
        if len(seen) < 3:
            raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))
        return b"ok"
    n = W.Net(W.Budget(10), (KEY,), opener=flaky, sleep=lambda s: None)
    assert n.fetch("https://x/api", {"serviceKey": KEY}) == "ok" and n.budget.used == 3

    def refused(url, data, timeout):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    n = W.Net(W.Budget(10), (KEY,), opener=refused, sleep=lambda s: None)
    with pytest.raises(W.FetchError) as e:
        n.fetch("https://x/api", {"serviceKey": KEY})
    assert n.budget.used == 1 and "HTTP 401" in str(e.value)   # a 4xx is not retried

    def leaky(url, data, timeout):
        raise urllib.error.URLError(f"bad url {url}")
    n = W.Net(W.Budget(10), (KEY,), opener=leaky, sleep=lambda s: None)
    with pytest.raises(W.FetchError) as e:
        n.fetch("https://x/api", {"serviceKey": KEY})
    assert KEY not in str(e.value) and urllib.parse.quote(KEY, safe="") not in str(e.value) and "«KEY»" in str(e.value)
    with pytest.raises(W.CallCapError):
        W.Net(W.Budget(0), (KEY,), opener=lambda *a: b"", sleep=lambda s: None).fetch("https://x")


def test_tide_check_reports_the_portal_refusal_as_given():
    ok, msg = W.tide_alive(net(Fake([(lambda u, f: "tideFcst" in u, GW_XML)])), KEY, dt.date(2026, 10, 31))
    assert not ok and "HTTP_ERROR" in msg and "(04)" in msg
    ok, msg = W.tide_alive(net(Fake([(lambda u, f: "tideFcst" in u, TIDE_OK)])), KEY, dt.date(2026, 10, 31))
    assert ok and "2026-10-31 06:58" in msg


# ---------------------------------------------------------------- festival

def test_festivals_new_changed_gone_and_missing_from_the_site():
    items = FEST["response"]["body"]["items"]["item"]
    old = {"1846797": {"title": "군산시간여행축제", "start": "20261001", "end": "20261005", "modified": "1"},
           "3364857": {"title": "군산짬뽕페스티벌", "start": "20261109", "end": "20261111", "modified": "1"}}
    events = [{"id": "event-tourapi-1846797", "contentid": "1846797", "name": "군산시간여행축제", "start_date": "2026-10-02"},
              {"id": "event-5235377", "tourapi_contentid": "3364857", "name": "2026 군산짬뽕페스티벌"}]
    res = W.compare_festivals(items, old, events, "2026-10-31")
    assert [x["contentid"] for x in res["new"]] == ["3999999"]
    assert res["changed"][0]["diff"] == {"start": ("20261001", "20261002")}
    assert res["changed"][0]["site"] == "event-tourapi-1846797"
    assert [(x["contentid"], x["site"]) for x in res["gone"]] == [("3364857", "event-5235377")]
    assert [x["title"] for x in res["missing"]] == ["군산 겨울빛 축제"]
    assert set(res["items"]) == {"1846797", "3999999"}


def test_festival_call_uses_the_gunsan_codes_and_pages():
    fake = Fake([(lambda u, f: "searchFestival2" in u, json.dumps(FEST))])
    items = W.festivals(net(fake), KEY, "20261031")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.calls[0][0]).query)
    assert (q["lDongRegnCd"], q["lDongSignguCd"], q["eventStartDate"]) == (["52"], ["130"], ["20261031"])
    assert len(items) == 2 and len(fake.calls) == 1   # fewer than numOfRows: no second page


# ---------------------------------------------------------------- licences

def test_a_new_closure_of_a_published_place_is_found_and_others_are_not():
    base = [L.prep(lic_raw("째보식당", "전북특별자치도 군산시 구영1길 10", mng="A"), "general_restaurants"),
            L.prep(lic_raw("다른집", "전북특별자치도 군산시 월명로 5", mng="B"), "general_restaurants"),
            L.prep(lic_raw("숨은집", "전북특별자치도 군산시 해망로 7", mng="C"), "general_restaurants")]
    places = [{"id": "p1", "name": "째보식당", "kind": "food", "status": "published",
               "facts": {"address": "전북특별자치도 군산시 구영1길 10"}},
              {"id": "p2", "name": "다른집", "kind": "food", "status": "published",
               "facts": {"address": "전북특별자치도 군산시 월명로 5"}},
              {"id": "p3", "name": "숨은집", "kind": "food", "status": "draft",
               "facts": {"address": "전북특별자치도 군산시 해망로 7"}}]
    licenses = {"places": {"p1": {"status": "영업", "mng_no": "A"}, "p2": {"status": "영업", "mng_no": "B"},
                           "p3": {"status": "영업", "mng_no": "C"}}}
    updated = [L.prep(lic_raw("째보식당", "전북특별자치도 군산시 구영1길 10", code="03", mng="A", closed="2026-11-03"),
                      "general_restaurants"),
               L.prep(lic_raw("숨은집", "전북특별자치도 군산시 해망로 7", code="03", mng="C", closed="2026-11-03"),
                      "general_restaurants")]
    out = W.license_changes(places, base, updated, licenses, "2026-11-07")
    assert [(x["id"], x["was"], x["now"], x["closed_at"]) for x in out] == [("p1", "영업", "폐업 확인", "2026-11-03")]
    assert W.license_changes(places, base, [], licenses, "2026-11-07") == []


def test_licence_updates_ask_only_for_rows_changed_since_the_last_check():
    fake = Fake([(lambda u, f: "/1741000/" in u, mois_page([lic_raw("째보식당", "전북특별자치도 군산시 구영1길 10",
                                                                     code="03", mng="A")]))])
    rows = W.license_updates(net(fake), KEY, "2026-10-31", services=["general_restaurants"])
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.calls[0][0]).query)
    assert q["cond[DAT_UPDT_PNT::GTE]"] == ["20261031"] and q["cond[OPN_ATMY_GRP_CD::EQ]"] == ["4671000"]
    assert rows[0]["MNG_NO"] == "A" and rows[0]["_group"] == "food"


# ---------------------------------------------------------------- the whole run

def site(tmp_path):
    data = tmp_path / "data" / "gunsan"
    lic_dir = tmp_path / "data" / "raw" / "gunsan" / "licenses"
    lic_dir.mkdir(parents=True)
    data.mkdir(parents=True, exist_ok=True)
    places = [{"id": "p1", "name": "째보식당", "kind": "food", "status": "published",
               "facts": {"address": "전북특별자치도 군산시 구영1길 10"}}]
    events = [{"id": "fest-군산불꽃축제-2026", "status": "draft", "source_news_epct_no": "35242", "also_sources": []}]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    (data / "licenses.json").write_text(json.dumps({"places": {"p1": {"status": "영업", "mng_no": "A"}}}), "utf-8")
    (data / "crowd.json").write_text(json.dumps({"generated": "2026-10-31", "period": {"start": "2026-10-31",
                                                                                     "end": "2026-11-29"},
                                                 "places": {"x": {}}}), "utf-8")
    sun = {(dt.date(2026, 10, 31) + dt.timedelta(days=i)).isoformat(): {} for i in range(120)}
    (data / "almanac.json").write_text(json.dumps({"sources": {}, "sun": sun}), "utf-8")
    L.write_csv(lic_dir / "mois_general_restaurants.csv", [lic_raw("째보식당", "전북특별자치도 군산시 구영1길 10", mng="A")])
    (lic_dir / L.FETCH_LOG).write_text(json.dumps({"general_restaurants": {"fetched_at": "2026-10-31"}}), "utf-8")
    return data


def routes():
    page = press_page([("35280", "5", "군산 겨울 해넘이 축제 개최", "관광진흥과", "2026-11-02"),
                       ("35279", "4", "착한가게 현판", "옥산면", "2026-11-02"),
                       ("35242", "1", "해상 불꽃쇼… ‘2026 군산불꽃축제’ 11월...", "관광진흥과", "2026-10-27")])
    closed = mois_page([lic_raw("째보식당", "전북특별자치도 군산시 구영1길 10", code="03", mng="A", closed="2026-11-03")])
    return [(is_list(1), page), (is_list(2), press_page([])),
            (lambda u, f: f.get("method") == ["selectOfrNews"], DETAIL.replace("2026-10-27", "2026-11-02")),
            (lambda u, f: "searchFestival2" in u, json.dumps(FEST)),
            (lambda u, f: "tideFcst" in u, GW_XML),
            (lambda u, f: "/1741000/general_restaurants/" in u, closed),
            (lambda u, f: "/1741000/" in u, mois_page([]))]


def test_run_reports_and_remembers_but_never_changes_the_site_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", KEY)
    monkeypatch.setenv("TOURAPI_KEY", KEY)
    data = site(tmp_path)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    state = tmp_path / "data" / "watch" / "state.json"
    fake = Fake(routes())
    W.run(data, state, tmp_path / "reports" / "watch", dt.date(2026, 11, 7), set(W.SECTIONS), "2026-10-24",
          150, 10, 30, False, True, opener=fake, sleep=lambda s: None)
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before
    text = (tmp_path / "reports" / "watch" / "2026-11-07.md").read_text("utf-8")
    assert "보도자료 35280" in text and "보도자료 35242" not in text.split("## (a)")[0]   # cited one is not a to-do
    assert "TourAPI 행사 3999999 군산 겨울빛 축제" in text
    assert "인허가 폐업 확인: 째보식당" in text and "응답 없음" in text and "HTTP_ERROR" in text
    assert "crowd.json: 2026-10-31에 받은 예측, 마지막 날 2026-11-29(남은 22일)" in text
    assert KEY not in text and urllib.parse.quote(KEY, safe="") not in text
    st = json.loads(state.read_text("utf-8"))
    assert st["press"]["last_no"] == 35280 and set(st["festival"]["items"]) == {"1846797", "3999999"}
    assert st["license"]["since"] == "2026-11-07" and "p1" in st["license"]["alerted"]
    assert st["tide"]["ok"] is False
    # the licence query started at the raw data's fetch date (no state yet)
    lic_q = [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query) for u, _ in fake.calls if "/1741000/" in u]
    assert lic_q[0]["cond[DAT_UPDT_PNT::GTE]"] == ["20261031"]

    # next run: nothing new, the closure still not in licenses.json → shown again as an earlier alert
    fake2 = Fake([(is_list(1), press_page([("35280", "5", "군산 겨울 해넘이 축제 개최", "관광진흥과", "2026-11-02")]))]
                 + routes()[3:5] + [(lambda u, f: "/1741000/" in u, mois_page([]))])
    W.run(data, state, tmp_path / "reports" / "watch", dt.date(2026, 11, 14), set(W.SECTIONS), "2026-10-31",
          150, 10, 30, False, True, opener=fake2, sleep=lambda s: None)
    text2 = (tmp_path / "reports" / "watch" / "2026-11-14.md").read_text("utf-8")
    assert "새 글 0건" in text2 and "| 이전 알림 | p1 |" in text2
    assert not [c for c in fake2.calls if c[1].get("method") == ["selectOfrNews"]]


def test_call_cap_stops_a_section_and_keeps_its_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", KEY)
    monkeypatch.setenv("TOURAPI_KEY", KEY)
    data = site(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"license": {"since": "2026-11-01"}}), "utf-8")
    res = W.run(data, state, tmp_path / "r", dt.date(2026, 11, 7), {"license"}, "2026-10-31", 3, 10, 30, False, True,
                opener=Fake(routes()), sleep=lambda s: None)
    assert "호출 상한 3회" in res["license"]["error"]
    assert json.loads(state.read_text("utf-8"))["license"]["since"] == "2026-11-01"


def test_apply_safe_only_refreshes_automatic_data(tmp_path, monkeypatch):
    from tools import almanac_gunsan, tourapi_related
    ran = []
    monkeypatch.setattr(tourapi_related, "main", lambda argv: ran.append(("crowd", argv)) or 0)
    monkeypatch.setattr(almanac_gunsan, "main", lambda argv: ran.append(("almanac", argv)) or 0)
    n = net(Fake([]))
    today = dt.date(2026, 11, 7)
    fresh = {"exists": True, "generated": "2026-11-07"}
    long_sun = {"exists": True, "has_tide": False, "sun_days_left": 100}
    assert W.apply_safe(tmp_path, fresh, long_sun, False, today, n) == [] and ran == []
    done = W.apply_safe(tmp_path, {"exists": True, "generated": "2026-10-31"}, long_sun, True, today, n)
    assert [r[0] for r in ran] == ["crowd", "almanac"] and ran[1][1][-1] == "--apply"   # tide back: sun + tide
    assert all(d["code"] == 0 for d in done)
    ran.clear()
    W.apply_safe(tmp_path, fresh, {"exists": True, "has_tide": False, "sun_days_left": 30}, False, today, n)
    assert ran == [("almanac", ["--data", str(tmp_path), "--apply", "--only", "sun"])]
