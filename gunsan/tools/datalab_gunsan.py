"""군산시 일별 방문자 수 — 한국관광공사 '빅데이터_지역별 방문자수'(DataLabService locgoRegnVisitrDDList, 기초지자체 일별)에서
군산시(signguCode 52130) 최근 1년치를 받아 날짜별로 둔다(운영자 결정 2026-10-31 '데이터 다 추출해서 사이트에 반영').

    DATA_GO_KR_KEY=… python tools/datalab_gunsan.py --data data/gunsan            # 미리보기
    DATA_GO_KR_KEY=… python tools/datalab_gunsan.py --data data/gunsan --apply    # 파일 쓰기
        --apply: data/raw/gunsan/datalab/locgo_visitors_daily_52130_<시작>_<끝>.csv(군산시 행, 응답 값 그대로)
                 → data/gunsan/visitors_daily.json
        --end 20261001: 마지막 날(없으면 서비스에 값이 있는 가장 최근 날) · --days 365
        --fresh: 캐시를 쓰지 않고 새로 받는다 · --max-calls: 실행당 호출 상한(기본 60)

규칙
- 서비스는 지역을 고르는 값이 없어(signguCode를 주면 INVALID_REQUEST_PARAMETER_ERROR) 전국 기초지자체 행을 12일씩
  (하루 약 807행, numOfRows 10000) 받아 군산시(52130, 2024-01-18 전 전라북도 시절 코드 45130) 행만 남긴다.
  가장 최근 날은 최근 두 달을 한 번 조회해 마지막 행의 날짜로 찾는다(값은 날짜순). 응답은 data/cache/DataLabService/에.
- 값(touNum)은 서비스가 준 숫자 그대로(소수점이 있는 추정값), 구분 이름(touDivNm '현지인(a)'·'외지인(b)'·'외국인(c)')도
  그대로다. 더하거나 반올림하지 않는다.
- 키는 환경 변수 DATA_GO_KR_KEY(없으면 TOURAPI_KEY)로만 받고 출력에서 가린다(tools/tourapi_related.Client).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tourapi import TourAPIError, normalize_key, redact  # noqa: E402
from tools.tourapi_related import (GW, PROVIDER, ApiError, Client, iso, key_from_env, number,  # noqa: E402
                                   squash, write_csv, write_json)

SERVICE, OP = "DataLabService", "locgoRegnVisitrDDList"
DATASET = "한국관광공사_빅데이터_지역별 방문자수_GW"
URL = "https://www.data.go.kr/data/15101972/openapi.do"
BASIS = "㈜케이티(내국인)·SK텔레콤(주)(외국인) 이동통신 데이터"
CODES = ("52130", "45130")      # 전북특별자치도 군산시 (45130: 2024-01-18 전 전라북도 군산시)
NAME = "군산시"
CHUNK_DAYS = 12                  # 12 days x ~807 rows a day < ROWS
ROWS = 10000


def ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def windows(end: dt.date, days: int, chunk: int = CHUNK_DAYS) -> list[tuple[dt.date, dt.date]]:
    """[(start, end), …] covering the `days` days up to `end`, newest first, each at most `chunk` days."""
    out, first = [], end - dt.timedelta(days=days - 1)
    hi = end
    while hi >= first:
        lo = max(first, hi - dt.timedelta(days=chunk - 1))
        out.append((lo, hi))
        hi = lo - dt.timedelta(days=1)
    return out


def latest_day(client: Client, today: dt.date, back: int = 62) -> dt.date:
    """The last day the service has: the last row of a two-month listing (rows come in date order)."""
    span = {"startYmd": ymd(today - dt.timedelta(days=back)), "endYmd": ymd(today)}
    _, total = client.page(OP, fresh=True, numOfRows=1, pageNo=1, **span)
    if not total:
        raise ApiError(f"{OP}: 최근 {back}일에 값이 없습니다")
    items, _ = client.page(OP, fresh=True, numOfRows=1, pageNo=total, **span)
    day = iso(items[-1].get("baseYmd")) if items else ""
    if not day:
        raise ApiError(f"{OP}: 마지막 행에 날짜가 없습니다")
    return dt.date.fromisoformat(day)


def gunsan_rows(items: list[dict]) -> list[dict]:
    return [r for r in items if str(r.get("signguCode")) in CODES and squash(r.get("signguNm")) == NAME]


def build(rows: list[dict], start: str, end: str, checked: str) -> dict:
    """visitors_daily.json from 군산시 rows: {날짜: {구분 이름: 값}} with the service's names and numbers."""
    days: dict[str, dict] = collections.defaultdict(dict)
    divisions: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: (str(r.get("baseYmd")), str(r.get("touDivCd")))):
        d, name, v = iso(r.get("baseYmd")), squash(r.get("touDivNm")), number(r.get("touNum"))
        if not d or not name or v is None or not (start <= d <= end):
            continue
        if name in days[d] and days[d][name] != v:
            raise ValueError(f"{d} {name}: 값이 둘({days[d][name]}, {v})")
        days[d][name] = v
        divisions.setdefault(str(r.get("touDivCd")), name)
    got = sorted(days)
    missing = []
    if got:
        d = dt.date.fromisoformat(start)
        while d <= dt.date.fromisoformat(end):
            if d.isoformat() not in days:
                missing.append(d.isoformat())
            d += dt.timedelta(days=1)
    return {
        "_about": (f"군산시 일별 방문자 수 — 한국관광공사 '빅데이터_지역별 방문자수'(DataLabService {OP}, 기초지자체 일별)에서 "
                   f"군산시(signguCode 52130) {start}~{end}를 {checked}에 받았다(tools/datalab_gunsan.py). ㈜케이티(내국인)·"
                   "SK텔레콤(주)(외국인) 이동통신 데이터로 센 '방문자'(거주·통근·통학 같은 일상생활권을 벗어나 한 곳에 일정 시간 "
                   "머문 사람 — 방문 목적을 알 수 없어 관광객과 같지 않다)의 일자별 순방문자 수다. 2박 3일 머문 사람은 사흘에 한 "
                   "명씩 세므로 날짜를 더한 값은 사람 수가 아니고, 기초·광역 지자체는 집계 기준이 달라 서로 더할 수 없다. 값은 "
                   "서비스가 준 숫자 그대로(소수점이 있는 추정값)이고 구분 이름(현지인(a)·외지인(b)·외국인(c))도 응답 그대로다. "
                   "자세한 해석 유의사항: 한국관광 데이터랩 https://datalab.visitkorea.or.kr"),
        "source": {"provider": PROVIDER, "dataset": DATASET, "url": URL, "api": f"{GW}/{SERVICE}/{OP}", "basis": BASIS,
                   "base_date": end, "checked_at": checked},
        "region": {"signguCode": "52130", "signguNm": NAME},
        "period": {"start": start, "end": end, "days": len(got), "missing": missing},
        "divisions": [divisions[k] for k in sorted(divisions)],
        "days": {d: days[d] for d in got},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--end", help="마지막 날 YYYYMMDD (없으면 서비스의 가장 최근 날)")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--max-calls", type=int, default=60)
    ap.add_argument("--fresh", action="store_true", help="캐시를 쓰지 않고 새로 받는다")
    ap.add_argument("--cache", type=Path, default=Path("data/cache"))
    a = ap.parse_args(argv)
    key = key_from_env()
    client = Client(key, SERVICE, a.cache / SERVICE, max_calls=a.max_calls, refresh=a.fresh)
    try:
        end = dt.date.fromisoformat(iso(a.end)) if a.end else latest_day(client, dt.date.today())
        rows, total = [], 0
        for lo, hi in windows(end, a.days):
            items = client.all(OP, rows=ROWS, startYmd=ymd(lo), endYmd=ymd(hi))
            total += len(items)
            rows += gunsan_rows(items)
    except TourAPIError as err:
        print(redact(str(err), normalize_key(key)), file=sys.stderr)
        return 1
    start = (end - dt.timedelta(days=a.days - 1)).isoformat()
    data = build(rows, start, end.isoformat(), client.checked_at())
    per = collections.defaultdict(list)
    for v in data["days"].values():
        for k, n in v.items():
            per[k].append(n)
    print(f"[방문자 수] {start}~{end}: 전국 행 {total} 중 군산시 {len(rows)} · {data['period']['days']}일"
          f"(빠진 날 {len(data['period']['missing'])}) · 호출 {client.calls}(캐시 {client.cache_hits})")
    for k in data["divisions"]:
        print(f"  {k}: 하루 {min(per[k]):,.1f} ~ {max(per[k]):,.1f}")
    if data["period"]["missing"]:
        print(f"  빠진 날: {', '.join(data['period']['missing'][:20])}")
    if a.apply:
        raw = (a.data.parent / "raw" / a.data.name / "datalab" /
               f"locgo_visitors_daily_52130_{ymd(dt.date.fromisoformat(start))}_{ymd(end)}.csv")
        write_csv(raw, sorted(rows, key=lambda r: (str(r.get("baseYmd")), str(r.get("touDivCd")))))
        write_json(a.data / "visitors_daily.json", data)
        print(f"  씀: {raw} · {a.data / 'visitors_daily.json'}")
    else:
        print("(미리보기 — 파일을 쓰려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
