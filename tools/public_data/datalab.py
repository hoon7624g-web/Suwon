"""일별 방문자 수 — 한국관광공사 '빅데이터_지역별 방문자수'(DataLabService)에서 사이트 지역의 최근 1년치를 받아 날짜별로
둔다(군산각 tools/datalab_gunsan.py(기초지자체)·인천각 tools/datalab_incheon.py(광역지자체)를 설정으로 일반화, 2026-11-05).

    DATA_GO_KR_KEY=… python tools/datalab.py --site busan            # 미리보기
    DATA_GO_KR_KEY=… python tools/datalab.py --site busan --apply    # 파일 쓰기
        --apply: out/<slug>/raw/datalab/<metco|locgo>_visitors_daily_<코드>_<시작>_<끝>.csv(그 지역 행, 응답 값 그대로)
                 → out/<slug>/visitors_daily.json
        --end 20261001: 마지막 날(없으면 서비스에 값이 있는 가장 최근 날) · --days 365
        --fresh: 캐시를 쓰지 않고 새로 받는다 · --max-calls: 실행당 호출 상한(기본 80)

규칙
- config public_data.datalab.level:
  · 'locgo'(기초지자체 일별 locgoRegnVisitrDDList) — 사이트 범위가 시·군·구 하나(군산과 같다). codes는 지금 코드와 기간 안의
    옛 코드(전남 46xxx → 전남광주통합특별시 12xxx 같은), names는 응답의 signguNm.
  · 'metco'(광역지자체 일별 metcoRegnVisitrDDList) — 사이트 범위가 시도 전체(부산·대구·제주, 인천과 같다). 기초·광역 값은
    집계 기준이 달라 기초 값을 더해 광역 값을 만들지 않는다.
- 서비스는 지역을 고르는 값이 없어(signguCode를 주면 INVALID_REQUEST_PARAMETER_ERROR) 전국 행을 받아 사이트 행만 남긴다:
  기초는 12일씩(하루 약 807행), 광역은 190일씩(하루 약 48행) numOfRows 10000. 응답은 cache/DataLabService/에 두고 모든
  사이트가 같은 캐시를 쓴다(같은 --end면 같은 요청). 가장 최근 날은 기초는 최근 두 달의 마지막 행, 광역은 최근 두 달 목록의
  가장 늦은 baseYmd로 찾는다.
- 값(touNum)은 서비스가 준 숫자 그대로(소수점이 있는 추정값), 구분 이름(touDivNm '현지인(a)'·'외지인(b)'·'외국인(c)')도
  그대로다. 더하거나 반올림하지 않는다.
- 키는 환경 변수 DATA_GO_KR_KEY(없으면 TOURAPI_KEY)로만 받고 출력에서 가린다(tools/tourapi_related.Client).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, Site, log_calls  # noqa: E402
from tourapi_related import (GW, PROVIDER, ApiError, Client, TourAPIError, iso, key_from_env,  # noqa: E402
                             normalize_key, number, redact, squash, write_csv, write_json)

SERVICE = "DataLabService"
OPS = {"locgo": "locgoRegnVisitrDDList", "metco": "metcoRegnVisitrDDList"}
DATASET = "한국관광공사_빅데이터_지역별 방문자수_GW"
URL = "https://www.data.go.kr/data/15101972/openapi.do"
BASIS = "㈜케이티(내국인)·SK텔레콤(주)(외국인) 이동통신 데이터"
CHUNK = {"locgo": 12, "metco": 190}   # 12 days x ~807 rows / 190 days x ~51 rows < ROWS
ROWS = 10000


def ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def windows(end: dt.date, days: int, chunk: int) -> list[tuple[dt.date, dt.date]]:
    """[(start, end), …] covering the `days` days up to `end`, newest first, each at most `chunk` days."""
    out, first = [], end - dt.timedelta(days=days - 1)
    hi = end
    while hi >= first:
        lo = max(first, hi - dt.timedelta(days=chunk - 1))
        out.append((lo, hi))
        hi = lo - dt.timedelta(days=1)
    return out


def latest_day(client: Client, op: str, level: str, today: dt.date, back: int = 62) -> dt.date:
    span = {"startYmd": ymd(today - dt.timedelta(days=back)), "endYmd": ymd(today)}
    if level == "metco":
        # the 광역 listing is not in date order (인천각 2026-10-31): the latest baseYmd of one page of every row
        items = client.all(op, rows=ROWS, **span)
        days = [iso(r.get("baseYmd")) for r in items if iso(r.get("baseYmd"))]
        if not days:
            raise ApiError(f"{op}: 최근 {back}일에 값이 없습니다")
        return dt.date.fromisoformat(max(days))
    _, total = client.page(op, numOfRows=1, pageNo=1, **span)
    if not total:
        raise ApiError(f"{op}: 최근 {back}일에 값이 없습니다")
    items, _ = client.page(op, numOfRows=1, pageNo=total, **span)
    day = iso(items[-1].get("baseYmd")) if items else ""
    if not day:
        raise ApiError(f"{op}: 마지막 행에 날짜가 없습니다")
    return dt.date.fromisoformat(day)


def region_rows(items: list[dict], cfg: dict) -> list[dict]:
    codes, names = set(cfg["codes"]), set(cfg["names"])
    if cfg["level"] == "metco":
        return [r for r in items if str(r.get("areaCode")) in codes and squash(r.get("areaNm")) in names]
    return [r for r in items if str(r.get("signguCode")) in codes and squash(r.get("signguNm")) in names]


def build(rows: list[dict], start: str, end: str, checked: str, cfg: dict) -> dict:
    """visitors_daily.json from the region's rows: {날짜: {구분 이름: 값}} with the service's names and numbers."""
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
    level, code, name = cfg["level"], cfg["codes"][0], cfg["name"]
    op = OPS[level]
    old = [c for c in cfg["codes"][1:]]
    if level == "metco":
        head = (f"{name} 일별 방문자 수 — 한국관광공사 '빅데이터_지역별 방문자수'(DataLabService {op}, 광역지자체 일별)에서 "
                f"{name}(areaCode {code}) {start}~{end}를 {checked}에 받았다(tools/datalab.py). region의 "
                "signguCode·signguNm 칸에는 광역지자체 코드·이름(areaCode·areaNm)을 넣었다(기초지자체 파일과 같은 구조). ")
    else:
        head = (f"{name} 일별 방문자 수 — 한국관광공사 '빅데이터_지역별 방문자수'(DataLabService {op}, 기초지자체 일별)에서 "
                f"{name}(signguCode {code}" + (f", 기간 안의 옛 코드 {'·'.join(old)}" if old else "") +
                f") {start}~{end}를 {checked}에 받았다(tools/datalab.py). ")
    return {
        "_about": (head + "㈜케이티(내국인)·"
                   "SK텔레콤(주)(외국인) 이동통신 데이터로 센 '방문자'(거주·통근·통학 같은 일상생활권을 벗어나 한 곳에 일정 시간 "
                   "머문 사람 — 방문 목적을 알 수 없어 관광객과 같지 않다)의 일자별 순방문자 수다. 2박 3일 머문 사람은 사흘에 한 "
                   "명씩 세므로 날짜를 더한 값은 사람 수가 아니고, 기초·광역 지자체는 집계 기준이 달라 서로 더할 수 없다. 값은 "
                   "서비스가 준 숫자 그대로(소수점이 있는 추정값)이고 구분 이름(현지인(a)·외지인(b)·외국인(c))도 응답 그대로다. "
                   "자세한 해석 유의사항: 한국관광 데이터랩 https://datalab.visitkorea.or.kr"),
        "source": {"provider": PROVIDER, "dataset": DATASET, "url": URL, "api": f"{GW}/{SERVICE}/{op}", "basis": BASIS,
                   "base_date": end, "checked_at": checked},
        "region": {"signguCode": code, "signguNm": name},
        "period": {"start": start, "end": end, "days": len(got), "missing": missing},
        "divisions": [divisions[k] for k in sorted(divisions)],
        "days": {d: days[d] for d in got},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--end", help="마지막 날 YYYYMMDD (없으면 서비스의 가장 최근 날)")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--max-calls", type=int, default=80)
    ap.add_argument("--fresh", action="store_true", help="캐시를 쓰지 않고 새로 받는다")
    ap.add_argument("--cache", type=Path, default=CACHE_DIR)
    a = ap.parse_args(argv)
    site = Site(a.site)
    cfg = site.pd["datalab"]
    op = OPS[cfg["level"]]
    key = key_from_env()
    client = Client(key, SERVICE, a.cache / SERVICE, max_calls=a.max_calls, refresh=a.fresh)
    try:
        end = dt.date.fromisoformat(iso(a.end)) if a.end else latest_day(client, op, cfg["level"], dt.date.today())
        rows, total = [], 0
        for lo, hi in windows(end, a.days, CHUNK[cfg["level"]]):
            items = client.all(op, rows=ROWS, startYmd=ymd(lo), endYmd=ymd(hi))
            total += len(items)
            rows += region_rows(items, cfg)
    except TourAPIError as err:
        print(redact(str(err), normalize_key(key)), file=sys.stderr)
        print("RESULT " + json.dumps({"error": redact(str(err), normalize_key(key)), "calls": client.calls}, ensure_ascii=False))
        return 1
    finally:
        log_calls(SERVICE, site.slug, client.calls)
    start = (end - dt.timedelta(days=a.days - 1)).isoformat()
    data = build(rows, start, end.isoformat(), client.checked_at(), cfg)
    per = collections.defaultdict(list)
    for v in data["days"].values():
        for k, n in v.items():
            per[k].append(n)
    print(f"[방문자 수] {start}~{end}: 전국 행 {total} 중 {cfg['name']} {len(rows)} · {data['period']['days']}일"
          f"(빠진 날 {len(data['period']['missing'])}) · 호출 {client.calls}(캐시 {client.cache_hits})")
    for k in data["divisions"]:
        print(f"  {k}: 하루 {min(per[k]):,.1f} ~ {max(per[k]):,.1f}")
    if data["period"]["missing"]:
        print(f"  빠진 날: {', '.join(data['period']['missing'][:20])}")
    if a.apply and rows:
        raw = (site.raw / "datalab" /
               f"{cfg['level']}_visitors_daily_{cfg['codes'][0]}_{ymd(dt.date.fromisoformat(start))}_{ymd(end)}.csv")
        for old in (site.raw / "datalab").glob(f"{cfg['level']}_visitors_daily_*.csv") if (site.raw / "datalab").is_dir() else ():
            if old != raw:
                old.unlink()
        write_csv(raw, sorted(rows, key=lambda r: (str(r.get("baseYmd")), str(r.get("touDivCd")))))
        write_json(site.out / "visitors_daily.json", data)
        print(f"  씀: {raw} · {site.out / 'visitors_daily.json'}")
    elif not a.apply:
        print("(미리보기 — 파일을 쓰려면 --apply)")
    print("RESULT " + json.dumps({"rows": len(rows), "days": data["period"]["days"], "missing": len(data["period"]["missing"]),
                                  "calls": client.calls, "end": end.isoformat()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
