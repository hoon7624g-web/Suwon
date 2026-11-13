"""tools/datalab_gunsan.py — 기간 나누기, 군산시 행 고르기, 날짜별 값 그대로. 네트워크 없음."""
import datetime as dt
import json

import pytest

from tools.datalab_gunsan import build, gunsan_rows, latest_day, windows
from tools.tourapi_related import Client


def _row(day, div_cd, div_nm, n, code="52130", name="군산시"):
    return {"signguCode": code, "signguNm": name, "daywkDivCd": "4", "daywkDivNm": "목요일", "touDivCd": div_cd,
            "touDivNm": div_nm, "touNum": n, "baseYmd": day}


def test_windows_cover_the_year_without_overlap():
    w = windows(dt.date(2026, 10, 1), 365)
    assert w[0] == (dt.date(2026, 9, 20), dt.date(2026, 10, 1))
    assert w[-1][0] == dt.date(2025, 10, 2) and len(w) == 31
    days = [lo + dt.timedelta(days=i) for lo, hi in w for i in range((hi - lo).days + 1)]
    assert len(days) == len(set(days)) == 365 and all((hi - lo).days < 12 for lo, hi in w)


def test_gunsan_rows_only():
    rows = [_row("20261001", "1", "현지인(a)", "1"), _row("20261001", "1", "현지인(a)", "2", "11110", "종로구"),
            _row("20231001", "1", "현지인(a)", "3", "45130")]
    assert [r["touNum"] for r in gunsan_rows(rows)] == ["1", "3"]


def test_build_keeps_names_and_numbers():
    rows = [_row("20261001", "2", "외지인(b)", "67676.0"), _row("20261001", "1", "현지인(a)", "216580"),
            _row("20261001", "3", "외국인(c)", "2877.489999999999"), _row("20260929", "1", "현지인(a)", "5"),
            _row("20260801", "1", "현지인(a)", "9")]          # outside the period
    data = build(rows, "2026-09-29", "2026-10-01", "2026-10-31")
    assert data["days"] == {"2026-09-29": {"현지인(a)": 5},
                            "2026-10-01": {"현지인(a)": 216580, "외지인(b)": 67676.0, "외국인(c)": 2877.489999999999}}
    assert data["divisions"] == ["현지인(a)", "외지인(b)", "외국인(c)"]
    assert data["period"] == {"start": "2026-09-29", "end": "2026-10-01", "days": 2, "missing": ["2026-09-30"]}
    assert data["source"]["url"] == "https://www.data.go.kr/data/15101972/openapi.do"
    assert data["source"]["base_date"] == "2026-10-01" and data["region"]["signguCode"] == "52130"
    with pytest.raises(ValueError):
        build(rows + [_row("20261001", "1", "현지인(a)", "1")], "2026-09-29", "2026-10-01", "2026-10-31")


def test_latest_day_is_the_last_row_of_a_recent_listing(tmp_path):
    def fetch(url):
        last = "pageNo=3" in url
        body = {"items": {"item": [_row("20261001" if last else "20260830", "3", "외국인(c)", "1")]},
                "numOfRows": 1, "pageNo": 3 if last else 1, "totalCount": 3}
        return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"}, "body": body}})
    c = Client("k" * 20, "DataLabService", tmp_path, fetch=fetch, min_interval=0)
    assert latest_day(c, dt.date(2026, 10, 31)) == dt.date(2026, 10, 1) and c.calls == 2
