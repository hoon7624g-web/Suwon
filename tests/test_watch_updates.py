"""tools/watch_updates.py — TourAPI 행사(searchFestival2)·집중률·해 자료 기간 점검. 네트워크 없이 작은 고정 응답(실제
응답 모양 그대로)으로만 본다: 지역 코드를 site.json 이름으로 찾기, 구마다 묻고 합치기, 행사의 새것·바뀐 일정·빠진 것,
재시도·호출 상한·키 가림, 보고서·상태 파일, 데이터 파일을 고치지 않는 것."""
import datetime as dt
import json
import shutil
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from tools import watch_updates as W

KEY = "abc+def/ghi=="
SITE = Path(__file__).resolve().parents[1] / "data" / "suwon" / "site.json"


def ok(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"}, "body": {
        "items": {"item": items} if items else "", "numOfRows": 100, "pageNo": 1, "totalCount": len(items)}}},
        ensure_ascii=False)


REGIONS = ok([{"code": "11", "name": "서울특별시"}, {"code": "41", "name": "경기도"}])
UNDER_41 = ok([{"code": "110", "name": "수원시"}, {"code": "111", "name": "수원시 장안구"},
               {"code": "113", "name": "수원시 권선구"}, {"code": "115", "name": "수원시 팔달구"},
               {"code": "117", "name": "수원시 영통구"}, {"code": "130", "name": "성남시"}])

F1 = {"contentid": "2700001", "title": "수원화성문화제", "eventstartdate": "20261009", "eventenddate": "20261011",
      "modifiedtime": "20261019140011", "addr1": "경기도 수원시 팔달구 정조로 825", "tel": "031-000-0000"}
F2 = {"contentid": "3999999", "title": "광교호수 겨울빛 축제", "eventstartdate": "20261205", "eventenddate": "20261231",
      "modifiedtime": "20261030100000", "addr1": "경기도 수원시 영통구 광교호수로 57", "tel": ""}
GW_XML = ('<?xml version="1.0" encoding="UTF-8"?><OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>'
          '<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode>'
          '</cmmMsgHeader></OpenAPI_ServiceResponse>')


class Fake:
    """opener(url, data, timeout) -> bytes: answers by the operation and its query."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, data, timeout):
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
        self.calls.append((url, q))
        for match, answer in self.routes:
            if match(url, q):
                out = answer(url, q) if callable(answer) else answer
                if isinstance(out, Exception):
                    raise out
                return out.encode("utf-8")
        raise AssertionError(f"unexpected call {url}")


def op(name, **want):
    return lambda url, q: f"/{name}?" in url and all(q.get(k) == v for k, v in want.items())


def routes(by_signgu=None):
    by_signgu = by_signgu if by_signgu is not None else {"115": [F1], "117": [F2, F1]}
    return [(lambda u, q: "/ldongCode2?" in u and "lDongRegnCd" not in q, REGIONS),
            (op("ldongCode2", lDongRegnCd="41"), UNDER_41),
            (op("searchFestival2"), lambda u, q: ok(by_signgu.get(q.get("lDongSignguCd"), [])))]


def net(fake, max_calls=50):
    return W.Net(W.Budget(max_calls), (KEY,), opener=fake, sleep=lambda s: None)


def site_dir(tmp_path, events=(), crowd=None, almanac=None):
    data = tmp_path / "data" / "suwon"
    data.mkdir(parents=True)
    shutil.copy(SITE, data / "site.json")
    (data / "events.json").write_text(json.dumps(list(events), ensure_ascii=False), "utf-8")
    if crowd is not None:
        (data / "crowd.json").write_text(json.dumps(crowd), "utf-8")
    if almanac is not None:
        (data / "almanac.json").write_text(json.dumps(almanac), "utf-8")
    return data


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


def test_a_gateway_refusal_is_reported_as_given():
    assert W.gateway_error(GW_XML) == "SERVICE ERROR SERVICE_KEY_IS_NOT_REGISTERED_ERROR (30)"
    assert W.gateway_error('{"response": {}}') is None
    api = W.WatchAPI(net(Fake([(op("ldongCode2"), GW_XML)])), KEY, json.loads(SITE.read_text("utf-8")))
    with pytest.raises(W.FetchError) as e:
        api.ldong_code()
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(e.value)


# ---------------------------------------------------------------- festival

def test_festivals_new_changed_gone_and_missing_from_the_site():
    old = {"2700001": {"title": "수원화성문화제", "start": "20261008", "end": "20261011", "modified": "1"},
           "2700002": {"title": "수원 연극축제", "start": "20261120", "end": "20261122", "modified": "1"}}
    events = [{"id": "event-tourapi-2700001", "contentid": "2700001", "name": "수원화성문화제", "start_date": "2026-10-09"},
              {"id": "event-2700002", "tourapi_contentid": "2700002", "name": "2026 수원 연극축제"}]
    res = W.compare_festivals([F1, F2], old, events, "2026-10-31")
    assert [x["contentid"] for x in res["new"]] == ["3999999"]
    assert res["changed"][0]["diff"] == {"start": ("20261008", "20261009")}
    assert res["changed"][0]["site"] == "event-tourapi-2700001"
    assert [(x["contentid"], x["site"]) for x in res["gone"]] == [("2700002", "event-2700002")]
    assert [x["title"] for x in res["missing"]] == ["광교호수 겨울빛 축제"]
    assert set(res["items"]) == {"2700001", "3999999"}


def test_an_event_of_the_same_series_and_year_counts_as_on_the_site():
    events = [{"id": "event-x", "name": "2026 광교호수 겨울빛 축제", "start_date": "2026-12-05"}]
    res = W.compare_festivals([F2], {}, events, "2026-10-31")
    assert res["missing"] == [] and res["new"][0]["site"] == "event-x"


def test_region_codes_come_from_ldongcode_names_and_every_gu_is_asked():
    site = json.loads(SITE.read_text("utf-8"))
    fake = Fake(routes())
    res = W.check_festival(net(fake), KEY, site, {}, [], dt.date(2026, 10, 31))
    fest = [q for u, q in fake.calls if "/searchFestival2?" in u]
    assert {q["lDongRegnCd"] for q in fest} == {"41"}
    assert [q["lDongSignguCd"] for q in fest] == ["111", "113", "115", "117", "110"]   # 4개 구 + 시 코드
    assert all(q["eventStartDate"] == "20261031" for q in fest)
    assert set(res["items"]) == {"2700001", "3999999"}   # 117 repeats 2700001: merged by contentid
    assert "장안구·권선구·팔달구·영통구" in res["region"] and "경기도" in res["region"]


def test_a_district_missing_from_ldongcode_is_an_error_not_a_guess():
    site = json.loads(SITE.read_text("utf-8"))
    short = ok([{"code": "111", "name": "수원시 장안구"}])
    fake = Fake([routes()[0], (op("ldongCode2", lDongRegnCd="41"), short)])
    res = W.check_festival(net(fake), KEY, site, {}, [], dt.date(2026, 10, 31))
    assert "지역 코드" in res["error"] and "권선구" in res["error"]
    assert not [u for u, _ in fake.calls if "/searchFestival2?" in u]


def test_festival_pages_until_a_short_page():
    site = json.loads(SITE.read_text("utf-8"))
    api = W.WatchAPI(net(Fake([])), KEY, site)
    pages = {1: [dict(F1, contentid=str(i)) for i in range(2)], 2: [dict(F1, contentid="9")]}
    asked = []

    def search(start, regn, code, rows, page):
        asked.append((code, page))
        return pages.get(page, []) if code == "111" else []
    api.search_festival = search
    ldong = W.LDong("41", "경기도", (("111", "장안구"),), whole_region=False)
    items = W.festivals(api, ldong, "20261031", rows=2)
    assert [it["contentid"] for it in items] == ["0", "1", "9"] and asked == [("111", 1), ("111", 2)]


# ---------------------------------------------------------------- crowd · almanac

def test_crowd_and_almanac_status_and_their_absence(tmp_path):
    today = dt.date(2026, 11, 7)
    assert W.crowd_status(tmp_path, today) == {"exists": False}
    assert W.almanac_status(tmp_path, today) == {"exists": False, "sun_days_left": None}
    (tmp_path / "crowd.json").write_text(json.dumps({"generated": "2026-10-31", "period": {"end": "2026-11-10"},
                                                     "places": {"a": 1}}), "utf-8")
    (tmp_path / "almanac.json").write_text(json.dumps({"sun": {"2026-11-08": {}, "2026-12-01": {}}}), "utf-8")
    c, a = W.crowd_status(tmp_path, today), W.almanac_status(tmp_path, today)
    assert c["days_left"] == 3 and c["places"] == 1 and a["sun_last"] == "2026-12-01" and a["sun_days_left"] == 24
    text = W.report("2026-11-07", {"crowd": c, "almanac": a}, (0, 150), "수원각")
    assert "남은 3일) — 곧 끝남" in text and "남은 24일) — 다시 받기 권장" in text
    text = W.report("2026-11-07", {"crowd": {"exists": False}, "almanac": {"exists": False}}, (0, 150), "수원각")
    assert "- crowd.json: 없음" in text and "- almanac.json: 없음" in text


# ---------------------------------------------------------------- run

def test_run_reports_and_remembers_but_never_changes_the_site_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TOURAPI_KEY", KEY)
    events = [{"id": "event-tourapi-2700001", "contentid": "2700001", "name": "수원화성문화제", "start_date": "2026-10-09"}]
    data = site_dir(tmp_path, events)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    state = tmp_path / "data" / "watch" / "state.json"
    res = W.run(data, state, tmp_path / "reports" / "watch", dt.date(2026, 11, 7), set(W.SECTIONS), 150, True,
                opener=Fake(routes()), sleep=lambda s: None)
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before
    text = (tmp_path / "reports" / "watch" / "2026-11-07.md").read_text("utf-8")
    assert text.startswith("# 수원각 변화 감시 2026-11-07")
    assert "TourAPI 행사 3999999 광교호수 겨울빛 축제" in text and "TourAPI 행사 2700001" not in text
    assert "- crowd.json: 없음" in text and "- almanac.json: 없음" in text
    assert KEY not in text and urllib.parse.quote(KEY, safe="") not in text
    assert res["calls"] == 7   # ldongCode2 ×2 + searchFestival2 ×5
    st = json.loads(state.read_text("utf-8"))
    assert set(st["festival"]["items"]) == {"2700001", "3999999"} and st["festival"]["checked_at"] == "2026-11-07"
    assert "festival.items" in st["_about"]

    # next run: one schedule moved — only that is a to-do; nothing new
    moved = dict(F2, eventstartdate="20261212")
    W.run(data, state, tmp_path / "reports" / "watch", dt.date(2026, 11, 14), set(W.SECTIONS), 150, True,
          opener=Fake(routes({"115": [F1], "117": [moved]})), sleep=lambda s: None)
    text2 = (tmp_path / "reports" / "watch" / "2026-11-14.md").read_text("utf-8")
    assert "새로 보임 0 · 일정 바뀜 1" in text2 and "start: 20261205 → 20261212" in text2


def test_no_key_is_reported_and_nothing_is_called(tmp_path, monkeypatch):
    monkeypatch.delenv("TOURAPI_KEY", raising=False)
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
    monkeypatch.setattr("pipeline.enrich.load_dotenv", lambda path: None)
    data = site_dir(tmp_path)
    fake = Fake([])
    state = tmp_path / "state.json"
    res = W.run(data, state, tmp_path / "r", dt.date(2026, 11, 7), set(W.SECTIONS), 150, False, opener=fake)
    assert "키 없음" in res["festival"]["error"] and fake.calls == [] and not state.exists()
    assert "받지 못함 — 키 없음" in (tmp_path / "r" / "2026-11-07.md").read_text("utf-8")


def test_call_cap_stops_the_festival_check_and_keeps_its_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TOURAPI_KEY", KEY)
    data = site_dir(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"festival": {"items": {"1": {"title": "x"}}, "checked_at": "2026-11-01"}}), "utf-8")
    res = W.run(data, state, tmp_path / "r", dt.date(2026, 11, 7), {"festival"}, 3, True,
                opener=Fake(routes()), sleep=lambda s: None)
    assert "호출 상한 3회" in res["festival"]["error"]
    assert json.loads(state.read_text("utf-8"))["festival"]["checked_at"] == "2026-11-01"


def test_the_tool_names_no_other_city():
    src = Path(W.__file__).read_text("utf-8")
    assert "군산" not in src and "gunsan" not in src.lower()
