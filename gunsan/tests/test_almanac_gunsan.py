"""tools/almanac_gunsan.py — 군산 해(한국천문연구원 출몰시각)·물때(국립해양조사원 조석예보 고·저조): 응답 값을 그대로
옮기는 규칙, 덜 받은 묶음은 이전 값을 두는 규칙, 키 가림. 네트워크 없이 작은 고정 응답으로만 본다."""
import datetime as dt
import io
import json
import urllib.error
import urllib.parse

import pytest

from tools import almanac_gunsan as A

# 2026-10-31 getAreaRiseSetInfo(location=군산) 응답 그대로(시각 뒤 공백 포함)
SUN_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><response><header><resultCode>00</resultCode>'
           '<resultMsg>NORMAL SERVICE.</resultMsg></header><body><items><item><aste>1905  </aste><astm>0528  </astm>'
           '<civile>1805  </civile><civilm>0628  </civilm><latitude>3558</latitude><latitudeNum>35.9666660</latitudeNum>'
           '<location>군산</location><locdate>20261031</locdate><longitude>12644</longitude>'
           '<longitudeNum>126.7333330</longitudeNum><moonrise>2210  </moonrise><moonset>1225  </moonset>'
           '<moontransit>0444  </moontransit><naute>1835  </naute><nautm>0557  </nautm><sunrise>0654  </sunrise>'
           '<sunset>1739  </sunset><suntransit>121641</suntransit></item></items><numOfRows>10</numOfRows>'
           '<pageNo>1</pageNo><totalCount>1</totalCount></body></response>')
# 포털 활용가이드(오픈API 활용가이드_조석예보(고, 저조).hwp)의 응답 형식, 한 날짜에 네 극치
TIDE_XML = ('<response><header><resultCode>00</resultCode><resultMsg>NORMAL_SERVICE</resultMsg></header><body><items>'
            + "".join(f'<item><obsvtrNm>군산</obsvtrNm><lot>126.56305</lot><lat>35.97555</lat><predcDt>2025-11-26 {t}'
                      f'</predcDt><predcTdlvVl>{v}</predcTdlvVl><extrSe>{e}</extrSe></item>'
                      for t, v, e in (("13:20", "88.5", "4"), ("00:47", "190.0", "2"), ("06:58", "612.0", "1"),
                                      ("19:31", "598.0", "3")))
            + '</items><pageNo>1</pageNo><numOfRows>10</numOfRows><totalCount>4</totalCount><type>xml</type></body>'
              '</response>')
GW_XML = ('<?xml version="1.0" encoding="UTF-8"?><OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>HTTP_ERROR</errMsg>'
          '<returnAuthMsg>HTTP 에러</returnAuthMsg><returnReasonCode>04</returnReasonCode></cmmMsgHeader>'
          '</OpenAPI_ServiceResponse>')
GW_JSON = json.dumps({"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "HTTP_ERROR", "returnAuthMsg": "HTTP 에러",
                                                                    "returnReasonCode": "04"}}}, ensure_ascii=False)
KEY = "abc+def/ghi=="


def test_sun_times_only_change_format_and_keep_the_location_point():
    assert A.hhmm("0654  ") == "06:54" and A.hhmm("----") is None and A.hhmm("") is None
    code, _, items = A.xml_items(SUN_XML)
    days, point = A.sun_block(items)
    assert code == "00"
    assert days == {"2026-10-31": {"sunrise": "06:54", "sunset": "17:39", "civil_dawn": "06:28", "civil_dusk": "18:05"}}
    assert point == {"lat": 35.966666, "lng": 126.733333}


def test_tide_extremes_map_high_and_low_and_keep_the_level_as_given():
    _, _, items = A.xml_items(TIDE_XML)
    st = A.tide_station("DT_0018", items)
    assert (st["name"], st["lat"], st["lng"]) == ("군산", 35.97555, 126.56305)
    assert st["days"] == {"2025-11-26": [
        {"time": "00:47", "type": "간조", "level_cm": 190}, {"time": "06:58", "type": "만조", "level_cm": 612},
        {"time": "13:20", "type": "간조", "level_cm": 88.5}, {"time": "19:31", "type": "만조", "level_cm": 598}]}
    # a row without a known extrSe or a level is left out, never guessed
    assert A.tide_rows([{"predcDt": "2025-11-26 01:00", "extrSe": "9", "predcTdlvVl": "1"},
                        {"predcDt": "2025-11-26 02:00", "extrSe": "1", "predcTdlvVl": ""}]) == {}


def test_gateway_refusals_are_read_from_xml_and_json_and_the_key_is_masked():
    assert A.gateway_error(GW_XML) == "HTTP_ERROR HTTP 에러 (04)"
    assert A.gateway_error(GW_JSON) == "HTTP_ERROR HTTP 에러 (04)"
    assert A.gateway_error(SUN_XML) is None
    msg = A.mask(f"bad {KEY} and {urllib.parse.quote(KEY, safe='')}", KEY)
    assert KEY not in msg and urllib.parse.quote(KEY, safe="") not in msg and msg.count("«KEY»") == 2


def test_a_gateway_refusal_is_not_retried_and_every_attempt_counts(monkeypatch):
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(url, timeout=0):
        calls.append(url)
        return Resp(GW_XML.encode())
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    b = A.Budget(5)
    with pytest.raises(A.ApiError) as e:
        A.api_get(A.TIDE["api"], {"obsCode": "DT_0018"}, KEY, b)
    assert "HTTP_ERROR" in str(e.value) and KEY not in str(e.value) and len(calls) == 1 and b.used == 1

    def reset(url, timeout=0):
        calls.append(url)
        raise urllib.error.URLError(ConnectionResetError(104, f"reset {KEY}"))
    monkeypatch.setattr(A.urllib.request, "urlopen", reset)
    monkeypatch.setattr(A.time, "sleep", lambda s: None)
    with pytest.raises(A.CallCapError):
        A.api_get(A.SUN["api"], {}, KEY, A.Budget(2))   # a dropped connection is retried until the cap


def test_only_a_complete_block_replaces_the_old_one():
    start, today = dt.date(2026, 10, 31), dt.date(2026, 10, 31)
    _, _, sun_items = A.xml_items(SUN_XML)
    old = {"sun": {"2026-10-30": {"sunrise": "06:53"}}, "sources": {"sun": {"base_date": "2026-10-30"}},
           "tide": {"DT_0018": {"name": "군산", "days": {"2026-10-30": []}}}, "_about": ""}
    # one day asked, one day got: the sun block is replaced; the tide station that failed keeps its old days
    data, notes = A.build(old, start, 1, today, (sun_items, None), {"DT_0018": ([], "조석예보 DT_0018: HTTP_ERROR")})
    assert data["sun"] == {"2026-10-31": {"sunrise": "06:54", "sunset": "17:39", "civil_dawn": "06:28",
                                          "civil_dusk": "18:05"}}
    assert data["sources"]["sun"]["checked_at"] == "2026-10-31" and data["sources"]["sun"]["lat"] == 35.966666
    assert data["tide"] == old["tide"] and any("DT_0018" in n for n in notes)
    # two days asked, one got: the old sun block stays
    data, notes = A.build(old, start, 2, today, (sun_items, None), {})
    assert data["sun"] == old["sun"] and notes
    # no station ever answered: no tide block, and _about says so
    data, _ = A.build({}, start, 1, today, (sun_items, None), {"DT_0018": ([], "HTTP_ERROR")})
    assert "tide" not in data and "tide" not in data["sources"] and "아직 없다" in data["_about"]


def test_the_file_keeps_a_day_per_line():
    text = A.dumps({"sun": {"2026-10-31": {"sunrise": "06:54"}, "2026-11-01": {"sunrise": "06:55"}},
                    "tide": {"DT_0018": {"name": "군산", "days": {"2026-10-31": [{"time": "00:47", "level_cm": 190}]}}}})
    assert json.loads(text)["tide"]["DT_0018"]["days"]["2026-10-31"][0]["level_cm"] == 190
    lines = text.splitlines()
    assert '  "2026-10-31": {"sunrise": "06:54"},' in lines
    assert '   "days": {' in lines and '    "2026-10-31": [{"time": "00:47", "level_cm": 190}]' in lines
