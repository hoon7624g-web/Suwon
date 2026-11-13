"""tools/tago_gunsan.py — 국토교통부 TAGO 열차·고속버스·시외버스·국내항공 배차를 data/gunsan/transport_tago.json으로
(운영자 결정 2026-10-31). 네트워크 없이 작은 고정 응답으로 기준일·변환·키 가림·캐시·호출 상한·원자료 규칙을 본다."""
import datetime as dt
import json
import urllib.parse
from pathlib import Path

import pytest

from tools import tago_gunsan as T

ROOT = Path(__file__).resolve().parent.parent
KEY = "abc+def/ghi=="   # not a real key; its encoded forms must be masked too

# items as the services return them (2026-10-31 answers, trimmed)
TRAIN = {"trainno": "01287", "traingradename": "무궁화호", "depplacename": "군산", "arrplacename": "익산",
         "depplandtime": "20261103001200", "arrplandtime": "20261103003000", "adultcharge": "4800"}
EXPRESS = {"routeId": "NAEK610021", "depPlaceNm": "군산", "arrPlaceNm": "센트럴시티(서울)",
           "depPlandTime": 202611022200, "arrPlandTime": 202611030025, "charge": 37200, "gradeNm": "심야프리미엄"}
INTERCITY = {"routeId": "NAIRT201607018069649", "depPlaceNm": "대전복합", "arrPlaceNm": "군산",
             "depPlandTime": 20261102083000, "arrPlandTime": 20261102100000, "charge": 12900, "gradeNm": "일반"}
FLIGHT = {"airlineNm": "진에어", "arrAirportNm": "제주국제공항", "arrPlandTime": 202611021040, "depAirportNm": "군산공항",
          "depPlandTime": 202611020940, "economyCharge": 0, "prestigeCharge": 0, "vihicleId": "LJ7825"}


def answer(items, total=None) -> str:
    body = {"items": {"item": items} if items else "", "numOfRows": 100, "pageNo": 1,
            "totalCount": len(items) if total is None else total}
    return json.dumps({"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."}, "body": body}})


def test_base_dates_skip_today_and_take_the_nearest_weekday_and_weekend_day():
    assert T.base_dates(dt.date(2026, 10, 31)) == {"weekend": dt.date(2026, 11, 1), "weekday": dt.date(2026, 11, 2)}
    assert T.base_dates(dt.date(2026, 11, 4)) == {"weekday": dt.date(2026, 11, 5), "weekend": dt.date(2026, 11, 7)}
    assert T.base_dates(dt.date(2026, 11, 6)) == {"weekend": dt.date(2026, 11, 7), "weekday": dt.date(2026, 11, 9)}


def test_items_of_reads_empty_single_and_list_answers():
    assert T.items_of({"items": "", "totalCount": 0}) == []
    assert T.items_of({"items": {"item": []}}) == []
    assert T.items_of({"items": {"item": FLIGHT}}) == [FLIGHT]
    assert T.items_of({"items": {"item": [TRAIN, TRAIN]}}) == [TRAIN, TRAIN]


def test_rows_keep_the_answer_values_and_only_add_screen_fields():
    p = {"depPlaceId": "NAT081388", "arrPlaceId": "NAT030879", "depPlandTime": "20261102"}
    r = T.to_row("train", TRAIN, "2026-11-02", "weekday", p)
    assert (r["from"], r["to"], r["type"], r["no"], r["dep"], r["arr"]) == (
        "군산", "익산", "무궁화호", "01287", "20261103001200", "20261103003000")
    assert r["fare"] == 4800 and (r["dep_hm"], r["arr_hm"]) == ("00:12", "00:30")
    assert (r["dep_plus_days"], r["arr_plus_days"]) == (1, 0)   # the base date's last train leaves after midnight
    p = {"depTerminalId": "NAEK610", "arrTerminalId": "NAEK021", "depPlandTime": "20261102"}
    e = T.to_row("express_bus", EXPRESS, "2026-11-02", "weekday", p)
    assert e["dep"] == 202611022200 and e["type"] == "심야프리미엄" and e["route_id"] == "NAEK610021"
    assert (e["fare"], e["dep_hm"], e["arr_hm"], e["dep_plus_days"], e["arr_plus_days"]) == (37200, "22:00", "00:25", 0, 1)
    p = {"depTerminalId": "NAI3455101", "arrTerminalId": "NAI5403701", "depPlandTime": "20261102"}
    i = T.to_row("intercity_bus", INTERCITY, "2026-11-02", "weekday", p)
    assert (i["from"], i["to"], i["type"], i["fare"], i["dep_hm"]) == ("대전복합", "군산", "일반", 12900, "08:30")
    p = {"depAirportId": "NAARKJK", "arrAirportId": "NAARKPC", "depPlandTime": "20261102"}
    f = T.to_row("flight", FLIGHT, "2026-11-02", "weekday", p)
    assert (f["airline"], f["no"], f["dep_hm"], f["arr_hm"]) == ("진에어", "LJ7825", "09:40", "10:40")
    assert f["fare_economy"] == 0 and f["fare_prestige"] == 0   # kept as given; the notes say 0 is 'no fare'
    assert T.won("") == "" and T.won(None) is None and T.won("21,600") == "21,600"   # never guessed


def test_route_summary_counts_first_last_minutes_fares_and_keeps_zero_pairs():
    p = {"depTerminalId": "NAI3455101", "arrTerminalId": "NAI5403701", "depPlandTime": "20261102"}
    late = {**INTERCITY, "depPlandTime": 20261102173000, "arrPlandTime": 20261102190000, "charge": 16700, "gradeNm": "우등"}
    rows = [T.to_row("intercity_bus", it, "2026-11-02", "weekday", p) for it in (late, INTERCITY)]
    s = T.route_summary("intercity_bus", rows, p, "2026-11-02", "weekday")
    assert (s["count"], s["first"], s["last"], s["minutes"]) == (2, "08:30", "17:30", [90, 90])
    assert s["fares"] == {"일반": [12900], "우등": [16700]}
    z = T.route_summary("intercity_bus", [], {**p, "depTerminalId": "NAI5403701", "arrTerminalId": "NAI5493301"},
                        "2026-11-02", "weekday")
    assert (z["count"], z["from"], z["to"], z["first"]) == (0, "군산", "전주시외터미널", "")


def test_client_masks_the_key_shows_the_provider_words_caches_and_caps_calls(tmp_path):
    def dropped(url):
        raise ConnectionResetError(f"Connection reset by peer: {url}")

    c = T.Client(KEY, None, opener=dropped, sleep=lambda s: None)
    with pytest.raises(T.TagoError) as e:
        c.page("TrainInfo", "GetVhcleKndList", {})
    assert c.calls == 3   # a dropped connection is tried three times
    msg = str(e.value)
    assert "«KEY»" in msg and KEY not in msg and urllib.parse.quote(KEY, safe="") not in msg
    xml = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
           "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>")
    c = T.Client(KEY, None, opener=lambda url: xml)
    with pytest.raises(T.TagoError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        c.page("TrainInfo", "GetVhcleKndList", {})
    assert c.calls == 1   # the provider answered: shown as it is, not retried
    bad = json.dumps({"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED ERROR."}}})
    with pytest.raises(T.TagoError, match="resultCode=30 SERVICE KEY IS NOT REGISTERED ERROR"):
        T.Client(KEY, None, opener=lambda url: bad).page("TrainInfo", "GetVhcleKndList", {})
    seen = []
    c = T.Client(KEY, tmp_path / "cache", max_calls=1, opener=lambda url: seen.append(url) or answer([FLIGHT]))
    assert c.all_items("DmstcFlightNvgInfo", "GetFlightOpratInfoList", {"depAirportId": "NAARKJK"}) == (1, [FLIGHT])
    assert c.all_items("DmstcFlightNvgInfo", "GetFlightOpratInfoList", {"depAirportId": "NAARKJK"}) == (1, [FLIGHT])
    assert len(seen) == 1   # the second answer came from the cache
    assert "serviceKey=" in seen[0] and "_type=json" in seen[0]
    assert not any(KEY in f.read_text("utf-8") for f in (tmp_path / "cache").rglob("*.json"))
    with pytest.raises(T.TagoError, match="호출 상한 1회"):
        c.page("DmstcFlightNvgInfo", "GetFlightOpratInfoList", {"depAirportId": "NAARKPC"})


def test_fetch_writes_raw_items_as_returned_without_the_key_and_build_reads_them(tmp_path):
    def opener(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        op = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        if op == "GetFlightOpratInfoList" and (q["depAirportId"], q["arrAirportId"]) == ("NAARKJK", "NAARKPC"):
            return answer([{**FLIGHT, "depPlandTime": int(q["depPlandTime"] + "0940"),
                            "arrPlandTime": int(q["depPlandTime"] + "1040")}])
        if op == "GetStrtpntAlocFndSuberbsBusInfo" and q["depTerminalId"] == "NAI3455101":
            return answer([{**INTERCITY, "depPlandTime": int(q["depPlandTime"] + "083000"),
                            "arrPlandTime": int(q["depPlandTime"] + "100000")}])
        if op == "GetArprtList":
            return answer([{"airportId": k, "airportNm": v} for k, v in T.NAMES.items() if k.startswith("NAAR")])
        return answer([])

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "train_20200101.json").write_text("{}", "utf-8")   # an older fetch's date: superseded
    c = T.Client(KEY, tmp_path / "cache", max_calls=2000, opener=opener)
    dates = {"weekend": dt.date(2026, 11, 1), "weekday": dt.date(2026, 11, 2)}
    m = T.fetch(c, raw, dates, dt.date(2026, 10, 31))
    assert m["base_dates"] == {"weekend": "2026-11-01", "weekday": "2026-11-02"}
    assert not any("flight" in w for w in m["warnings"])            # the airport list had every name
    assert any(w.startswith("train ") for w in m["warnings"])        # an empty station list is reported, not hidden
    assert not (raw / "train_20200101.json").exists()
    assert {f.name for f in raw.glob("*.json")} == {"codes.json", "fetch.json"} | {
        f"{mode}_{d}.json" for mode in T.MODES for d in ("20261101", "20261102")}
    for f in raw.glob("*.json"):
        assert KEY not in f.read_text("utf-8") and "serviceKey" not in f.read_text("utf-8")
    fl = json.loads((raw / "flight_20261102.json").read_text("utf-8"))
    got = [p for p in fl["pairs"] if p["items"]]
    assert len(got) == 1 and got[0]["items"][0]["vihicleId"] == "LJ7825" and got[0]["items"][0]["economyCharge"] == 0
    assert len(fl["pairs"]) == 2 * len(T.ROUTES["flight"])   # both ways, zero pairs kept
    doc = T.build(raw)
    assert doc["_about"] and doc["sources"]["flight"]["url"] == "https://www.data.go.kr/data/15098526/openapi.do"
    assert doc["sources"]["train"]["provider"] == "국토교통부" and doc["sources"]["train"]["checked_at"] == "2026-10-31"
    assert doc["base_dates"]["weekday"] == {"date": "2026-11-02", "dow": "월"}
    assert [r["date"] for r in doc["flight"]] == ["2026-11-01", "2026-11-02"]
    assert [(r["from"], r["dep_hm"]) for r in doc["intercity_bus"]] == [("대전복합", "08:30")] * 2
    assert doc["train"] == [] and doc["express_bus"] == []
    zero = [r for r in doc["routes"] if r["mode"] == "intercity_bus" and not r["count"]]
    assert zero and all(r["from"] and r["to"] for r in zero)


def test_routes_pair_a_gunsan_end_with_a_listed_id():
    for mode, pairs in T.ROUTES.items():
        assert pairs and len(set(pairs)) == len(pairs)
        for a, b in pairs:
            assert a in T.GUNSAN[mode] and b in T.NAMES and b not in T.GUNSAN[mode]


def test_the_site_data_file_matches_its_base_dates_and_names():
    f = ROOT / "data" / "gunsan" / T.OUT_FILE
    if not f.is_file():
        pytest.skip("transport_tago.json not built yet")
    doc = json.loads(f.read_text("utf-8"))
    dates = {v["date"] for v in doc["base_dates"].values()}
    assert set(doc["sources"]) == set(T.MODES)
    for mode in T.MODES:
        for r in doc[mode]:
            assert r["date"] in dates and r["from_id"] in T.NAMES and r["to_id"] in T.NAMES
        for rt in (x for x in doc["routes"] if x["mode"] == mode):
            n = sum(1 for r in doc[mode] if (r["date"], r["from_id"], r["to_id"]) == (rt["date"], rt["from_id"], rt["to_id"]))
            assert n == rt["count"]
