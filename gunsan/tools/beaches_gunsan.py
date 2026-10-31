"""군산 해수욕장 — 해양수산부 해수욕장정보·해수욕장 수질적합 여부를 장소에 이어 data/gunsan/beaches.json으로
(운영자 결정 2026-10-31 '데이터 다 추출해서 사이트에 반영' — 군산각 추가 출처).

    DATA_GO_KR_KEY=… python tools/beaches_gunsan.py --data data/gunsan            # 받기(캐시) + 미리보기
    DATA_GO_KR_KEY=… python tools/beaches_gunsan.py --data data/gunsan --apply    # beaches.json·원자료 쓰기
        --years 4 (올해부터 거슬러 몇 해의 수질 조사를 볼지)  --max-calls 40  --key-file <파일>

규칙
- 키는 DATA_GO_KR_KEY(또는 --key-file)로만 받고 메시지에서 가린다(tools/almanac_gunsan.py의 api_get).
- 두 API 모두 SIDO_NM=전북으로 부르고 gugun_nm이 '군산시'인 행만 쓴다. 응답은 확인한 날짜별로 data/cache/beaches/에
  캐시한다(같은 날 다시 실행하면 부르지 않는다).
- 장소 잇기: 해수욕장정보 행의 관련사이트(link_addr) cid가 장소의 TourAPI contentid와 같거나, 장소 이름이
  '<정점명>해수욕장'이고, 장소 좌표가 행 좌표에서 MATCH_M 안일 때만 잇는다. 후보가 없거나 둘 이상이면 잇지 않고
  unmatched에 남긴다(이름만 비슷하다고 같은 곳으로 보지 않는다). 수질 행은 같은 정점명의 해수욕장정보 행을 따라간다.
- 값은 응답 그대로 둔다(info는 응답 필드 이름 그대로; num·sido_nm만 뺀다). 수질은 결과가 있는 가장 최근 해 하나만
  water에 두고(조사차수별 날짜·조사종류·지점 수·적합 여부 원문 개수, 마지막 조사의 지점별 값), 조사일 res_date(밀리초,
  한국 시각 자정)는 날짜로만 바꾼다. 장구균·대장균의 '&lt;1'은 '<1'로 읽는다(HTML 문자 참조).
- 개장 기간은 두 API에 없다(수질의 res_knd '개장전'·'개장중'은 조사 종류다). 넣지 않는다.
- 원자료: data/raw/gunsan/beaches/beach_info_gunsan.csv, beach_water_gunsan_<해>.csv(군산시 행, 응답 필드 그대로).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import json
import math
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.almanac_gunsan import KST, ApiError, Budget, api_get, dumps, load_key, write_csv  # noqa: E402

PROVIDER = "해양수산부"
INFO = {"provider": PROVIDER, "dataset": "해양수산부_해수욕장정보 서비스", "url": "https://www.data.go.kr/data/15058519/openapi.do",
        "api": "https://apis.data.go.kr/1192000/service/OceansBeachInfoService1/getOceansBeachInfo1", "key": "getOceansBeachInfo"}
WATER = {"provider": PROVIDER, "dataset": "해양수산부_해수욕장 수질적합 여부 서비스",
         "url": "https://www.data.go.kr/data/15056705/openapi.do",
         "api": "https://apis.data.go.kr/1192000/service/OceansBeachSeawaterService1/getOceansBeachSeawaterInfo1",
         "key": "getOceansBeachSeawaterInfo"}
SIDO, GUGUN = "전북", "군산시"
MATCH_M = 1500     # a place this close to the beach's point (the 해수욕장정보 point is the beach's middle, ours a gate)
ROWS = 300
DROP = ("num", "sido_nm")
WATER_KEEP = ("res_loc", "res_loc_detail", "res1", "res2", "res_yn")   # a point of the last survey, names as given


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    k = math.pi / 180
    x = (b[1] - a[1]) * k * math.cos((a[0] + b[0]) / 2 * k)
    return 6371000 * math.hypot(x, (b[0] - a[0]) * k)


def unescape(v):
    return html.unescape(v) if isinstance(v, str) else v


def items_of(body: dict, key: str) -> tuple[list[dict], int]:
    """(rows, totalCount) of a 1192000 JSON answer ({key: {header, item, totalCount}}); a non-00 header is an error."""
    root = body.get(key) or {}
    head = root.get("header") or {}
    if str(head.get("code", "00")) != "00":
        raise ApiError(f"{head.get('code')} {head.get('message')}")
    rows = root.get("item") or []
    return ([rows] if isinstance(rows, dict) else rows), int(root.get("totalCount") or 0)


def fetch_all(src: dict, params: dict, key: str, budget: Budget, cache: Path, tag: str) -> list[dict]:
    """Every page of one query (ROWS a page), each page cached as data/cache/beaches/<today>-<tag>-p<n>.json."""
    rows, page, total = [], 1, None
    today = dt.datetime.now(KST).date().isoformat()
    while total is None or (page - 1) * ROWS < total:
        f = cache / f"{today}-{tag}-p{page}.json"
        if f.is_file():
            body = json.loads(f.read_text("utf-8"))
        else:
            body = json.loads(api_get(src["api"], {"SIDO_NM": SIDO, "resultType": "json", "numOfRows": ROWS,
                                                   "pageNo": page, **params}, key, budget))
            items_of(body, src["key"])
            cache.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(body, ensure_ascii=False), "utf-8")
        got, total = items_of(body, src["key"])
        rows += got
        if not got:
            break
        page += 1
    return rows


def cid(link: str) -> str:
    m = re.search(r"[?&]cid=(\d+)", link or "")
    return m.group(1) if m else ""


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", re.sub(r"\(.*?\)", "", s or ""))


def point(r: dict) -> tuple[float, float] | None:
    try:
        return float(r["lat"]), float(r["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def match(row: dict, places: list[dict]) -> tuple[str | None, dict]:
    """(place id or None, how) for one 해수욕장정보 row: cid = TourAPI contentid or name '<정점명>해수욕장', and the place
    point within MATCH_M of the row's point; exactly one candidate or none."""
    want = norm(row.get("sta_nm", "")) + "해수욕장"
    c = cid(row.get("link_addr", ""))
    here = point(row)
    cands = []
    for p in places:
        by = [w for w, ok in (("TourAPI contentid", c and str((p.get("tourapi") or {}).get("contentid") or "") == c),
                              ("이름", norm(p.get("name", "")) == want)) if ok]
        g = p.get("geo") or {}
        if not by or not here or not g.get("lat"):
            continue
        d = metres(here, (float(g["lat"]), float(g["lng"])))
        if d <= MATCH_M:
            cands.append((p["id"], {"by": " + ".join(by), "distance_m": round(d)}))
    if len(cands) == 1:
        return cands[0]
    return None, {"reason": "후보 없음" if not cands else f"후보 {len(cands)}곳: " + ", ".join(i for i, _ in cands)}


def kst_date(ms) -> str:
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, KST).date().isoformat()
    except (TypeError, ValueError):
        return str(ms or "")


def water_block(rows: list[dict]) -> dict | None:
    """{year, result, checked, surveys, last} of one beach's rows of its latest year: result is the 적합 여부 as written
    when every point of the last survey reads the same, else None (the counts are in surveys)."""
    if not rows:
        return None
    year = max(str(r.get("res_year")) for r in rows)
    rows = [r for r in rows if str(r.get("res_year")) == year]
    by = collections.defaultdict(list)
    for r in rows:
        by[str(r.get("res_num"))].append(r)
    surveys = []
    for n in sorted(by, key=lambda x: (len(x), x)):
        rs = by[n]
        surveys.append({"round": n, "date": max(kst_date(r.get("res_date")) for r in rs),
                        "kinds": sorted({r.get("res_knd") for r in rs if r.get("res_knd")}), "points": len(rs),
                        "results": dict(collections.Counter(unescape(r.get("res_yn")) for r in rs))})
    last = max(surveys, key=lambda s: (s["date"], len(s["round"]), s["round"]))
    res = list(last["results"])
    return {"year": year, "result": res[0] if len(res) == 1 else None, "checked": last["date"], "surveys": surveys,
            "last": [{k: unescape(r.get(k)) for k in WATER_KEEP} for r in by[last["round"]]]}


def build(info: list[dict], water: list[dict], places: list[dict], checked: str, years: list[int]) -> dict:
    gun_info = [r for r in info if r.get("gugun_nm") == GUGUN]
    gun_water = [r for r in water if r.get("gugun_nm") == GUGUN]
    by_name = {p["id"]: p for p in places}
    out, unmatched = {}, []
    sta_place = {}
    for r in gun_info:
        pid, how = match(r, places)
        if not pid:
            unmatched.append({"source": "info", "sta_nm": r.get("sta_nm"), **how})
            continue
        sta_place[r.get("sta_nm")] = pid
        out[pid] = {"name": by_name[pid].get("name"), "sta_nm": r.get("sta_nm"),
                    "info": {k: unescape(v) for k, v in r.items() if k not in DROP}, "match": how}
    wby = collections.defaultdict(list)
    for r in gun_water:
        wby[r.get("sta_nm")].append(r)
    for sta, rows in wby.items():
        pid = sta_place.get(sta)
        if not pid:
            unmatched.append({"source": "water", "sta_nm": sta, "reason": "해수욕장정보에 같은 정점명 없음"})
            continue
        out[pid]["water"] = water_block(rows)
    return {
        "_about": ("군산 해수욕장 — 해양수산부 해수욕장정보(해변 폭·길이·특징·비상연락처·좌표)와 해수욕장 수질적합 여부"
                   "(조사차수별 대장균·장구균·적합 여부)를 장소 id에 이었다. 값은 응답 그대로다. 개장 기간은 두 API에 "
                   "없다. 수질은 결과가 있는 가장 최근 해(water.year)의 조사다 — 올해 값이 아니면 화면에 해를 함께 적는다. "
                   "tools/beaches_gunsan.py가 만든다."),
        "sources": {
            "info": {**{k: INFO[k] for k in ("provider", "dataset", "url", "api")}, "query": {"SIDO_NM": SIDO},
                     "rows": len(info), "rows_gunsan": len(gun_info), "checked_at": checked},
            "water": {**{k: WATER[k] for k in ("provider", "dataset", "url", "api")}, "query": {"SIDO_NM": SIDO},
                      "years_asked": years, "rows_gunsan": len(gun_water), "checked_at": checked},
        },
        "places": out,
        "unmatched": unmatched,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--years", type=int, default=4, help="올해부터 거슬러 볼 수질 조사 해 수")
    ap.add_argument("--max-calls", type=int, default=40)
    ap.add_argument("--key-file", type=Path)
    ap.add_argument("--cache", type=Path, default=Path("data/cache/beaches"))
    a = ap.parse_args(argv)
    key = load_key(a.key_file)
    budget = Budget(a.max_calls)
    today = dt.datetime.now(KST).date()
    years = [today.year - i for i in range(a.years)]
    water: list[dict] = []
    water_by_year: dict[int, list[dict]] = {}
    try:
        info = fetch_all(INFO, {}, key, budget, a.cache, f"info-{SIDO}")
        for y in years:   # this year first, back to the first year that has 군산 rows (only that year is used)
            water_by_year[y] = fetch_all(WATER, {"RES_YEAR": y}, key, budget, a.cache, f"water-{SIDO}-{y}")
            water = [r for r in water_by_year[y] if r.get("gugun_nm") == GUGUN]
            if water:
                break
    except ApiError as e:
        raise SystemExit(f"해양수산부 API: {e}")
    places = json.loads((a.data / "places.json").read_text("utf-8"))
    data = build(info, water, places, today.isoformat(), years)
    print(f"호출 {budget.used}회 · 해수욕장정보 {SIDO} {len(info)}행(군산 {data['sources']['info']['rows_gunsan']}) · "
          f"수질 " + ", ".join(f"{y} {len(water_by_year[y])}행(군산 "
                                f"{sum(r.get('gugun_nm') == GUGUN for r in water_by_year[y])})" for y in water_by_year))
    for pid, b in data["places"].items():
        w = b.get("water") or {}
        print(f"  {pid} {b['name']} ← {b['sta_nm']} ({b['match']}) 수질 {w.get('year')} {w.get('result')} "
              f"{w.get('checked')} 조사 {len(w.get('surveys') or [])}회")
    for u in data["unmatched"]:
        print("  잇지 않음:", u)
    if not a.apply:
        print("미리보기 — 쓰려면 --apply")
        return 0
    raw = a.data.parent / "raw" / a.data.name / "beaches"
    gun_info = [r for r in info if r.get("gugun_nm") == GUGUN]
    if gun_info:
        write_csv(raw / "beach_info_gunsan.csv", gun_info)
    if water:
        write_csv(raw / f"beach_water_gunsan_{water[0].get('res_year')}.csv", water)
    out = a.data / "beaches.json"
    out.write_text(dumps(data), "utf-8")
    print(f"썼음: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
