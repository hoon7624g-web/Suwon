"""해수욕장 — 해양수산부 해수욕장정보·해수욕장 수질적합 여부를 장소에 이어 out/<slug>/beaches.json으로(인천각
tools/beaches_incheon.py·군산각 beaches_gunsan.py를 설정으로 일반화, 2026-11-05).

    DATA_GO_KR_KEY=… python tools/beaches.py --site busan            # 받기(캐시) + 미리보기
    DATA_GO_KR_KEY=… python tools/beaches.py --site busan --apply    # beaches.json·원자료 쓰기
        --years 4 (올해부터 거슬러 몇 해의 수질 조사를 볼지)  --max-calls 40  --key-file <파일>

규칙(인천각 도구와 같다)
- 키는 DATA_GO_KR_KEY(또는 --key-file)로만 받고 메시지에서 가린다(tools/common.api_get).
- 두 API 모두 SIDO_NM=<config beaches.sido>로 부르고 sido_nm이 그 값이고 gugun_nm이 config beaches.gugun 가운데 하나인 행
  (gugun이 비면 시도 전체 — 부산·제주)을 쓴다. 응답은 확인한 날짜별로 cache/beaches/에 캐시한다(같은 시도를 쓰는 사이트끼리
  같은 캐시).
- 장소 잇기: 해수욕장정보 행의 관련사이트(link_addr) cid가 장소의 TourAPI contentid와 같거나, 장소 이름(다른 이름·괄호 안
  이름, 앞의 지역 이름을 뺀 이름 포함)이 '<정점명>해수욕장' 또는 '<정점명>해변'(TourAPI 표기)이고, 장소 좌표가 행 좌표에서 MATCH_M 안일 때만 잇는다. 후보가 없거나 둘 이상이면 잇지 않고
  unmatched에 남긴다(이름만 비슷하다고 같은 곳으로 보지 않는다). 수질 행은 같은 정점명의 해수욕장정보 행을 따라간다.
- 값은 응답 그대로 둔다(info는 응답 필드 이름 그대로; num·sido_nm만 뺀다). 수질은 결과가 있는 가장 최근 해 하나만
  water에 두고(조사차수별 날짜·조사종류·지점 수·적합 여부 원문 개수, 마지막 조사의 지점별 값), 조사일 res_date(밀리초,
  한국 시각 자정)는 날짜로만 바꾼다. 장구균·대장균의 '&lt;1'은 '<1'로 읽는다(HTML 문자 참조).
- 개장 기간은 두 API에 없다(수질의 res_knd '개장전'·'개장중'은 조사 종류다). 넣지 않는다.
- 원자료: raw/beaches/beach_info_<slug>.csv, beach_water_<slug>_<해>.csv(사이트 행, 응답 필드 그대로).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, KST, ApiError, Budget, Site, api_get, dumps, load_key, log_calls, write_csv  # noqa: E402

PROVIDER = "해양수산부"
INFO = {"provider": PROVIDER, "dataset": "해양수산부_해수욕장정보 서비스", "url": "https://www.data.go.kr/data/15058519/openapi.do",
        "api": "https://apis.data.go.kr/1192000/service/OceansBeachInfoService1/getOceansBeachInfo1", "key": "getOceansBeachInfo"}
WATER = {"provider": PROVIDER, "dataset": "해양수산부_해수욕장 수질적합 여부 서비스",
         "url": "https://www.data.go.kr/data/15056705/openapi.do",
         "api": "https://apis.data.go.kr/1192000/service/OceansBeachSeawaterService1/getOceansBeachSeawaterInfo1",
         "key": "getOceansBeachSeawaterInfo"}
SIDO = ""          # SIDO_NM of the query and sido_nm of the rows kept
GUGUN: list[str] = []
NAME = ""
SLUG = ""
MATCH_M = 1500     # a place this close to the beach's point (the 해수욕장정보 point is the beach's middle, ours a gate)
ROWS = 300
DROP = ("num", "sido_nm")
WATER_KEEP = ("res_loc", "res_loc_detail", "res1", "res2", "res_yn")   # a point of the last survey, names as given


LEAD = ""


def configure(site: Site) -> None:
    global SIDO, GUGUN, NAME, SLUG, LEAD
    b = site.pd["beaches"]
    SIDO, GUGUN = b["sido"], list(b.get("gugun") or [])
    NAME, SLUG = site.region["short"], site.slug
    sfx = "|".join(re.escape(x) for x in sorted(site.region.get("name_suffixes") or ["시", "광역시"], key=len, reverse=True))
    LEAD = rf"^\s*{re.escape(NAME)}(?:{sfx})?\s+"


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
    """Every page of one query (ROWS a page), each page cached as cache/beaches/<today>-<tag>-p<n>.json."""
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


def place_names(p: dict) -> set[str]:
    """norm of the place's name, alternate names and each bracketed name ('사근진해변(사근진해수욕장)' → '사근진해변',
    '사근진해수욕장')."""
    out = set()
    for n in [p.get("name")] + list(p.get("alternate_names") or []):
        out.add(norm(n or ""))
        if LEAD and re.match(LEAD, n or ""):     # '부산 송도해수욕장' → '송도해수욕장' (tools/tourapi_related.py와 같은 규칙)
            out.add(norm(re.sub(LEAD, "", n or "")))
        out |= {norm(x) for x in re.findall(r"\(([^()]*)\)", n or "")}
    return {x for x in out if x}


def match(row: dict, places: list[dict]) -> tuple[str | None, dict]:
    """(place id or None, how) for one 해수욕장정보 row: cid = TourAPI contentid or a name '<정점명>해수욕장' (인천각·군산각
    도구) or '<정점명>해변'(TourAPI가 해수욕장을 '○○해변'으로 싣는다 — 2026-11-05 일반화 때 더함), and the place point within
    MATCH_M of the row's point; exactly one candidate or none."""
    want = {norm(row.get("sta_nm", "")) + "해수욕장", norm(row.get("sta_nm", "")) + "해변"}
    c = cid(row.get("link_addr", ""))
    here = point(row)
    cands = []
    for p in places:
        if p.get("duplicate_of") or p.get("exclude"):
            continue
        by = [w for w, ok in (("TourAPI contentid", c and str((p.get("tourapi") or {}).get("contentid") or "") == c),
                              ("이름", bool(place_names(p) & want))) if ok]
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


def ours(rows: list[dict]) -> list[dict]:
    """The rows of the site (sido_nm SIDO and, when GUGUN is set, gugun_nm in it)."""
    return [r for r in rows if r.get("sido_nm") == SIDO and (not GUGUN or r.get("gugun_nm") in GUGUN)]


def build(info: list[dict], water: list[dict], places: list[dict], checked: str, years: list[int]) -> dict:
    gun_info = ours(info)
    gun_water = ours(water)
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
    query = {"SIDO_NM": SIDO, **({"gugun_nm": GUGUN} if GUGUN else {})}
    return {
        "_about": (f"{NAME} 해수욕장 — 해양수산부 해수욕장정보(해변 폭·길이·특징·비상연락처·좌표)와 해수욕장 수질적합 여부"
                   "(조사차수별 대장균·장구균·적합 여부)를 장소 id에 이었다. 값은 응답 그대로다. 개장 기간은 두 API에 "
                   "없다. 수질은 결과가 있는 가장 최근 해(water.year)의 조사다 — 올해 값이 아니면 화면에 해를 함께 적는다. "
                   "tools/beaches.py(공공데이터 모음 도구)가 만든다."),
        "sources": {
            "info": {**{k: INFO[k] for k in ("provider", "dataset", "url", "api")}, "query": query,
                     "rows": len(info), f"rows_{SLUG}": len(gun_info), "checked_at": checked},
            "water": {**{k: WATER[k] for k in ("provider", "dataset", "url", "api")}, "query": query,
                      "years_asked": years, f"rows_{SLUG}": len(gun_water), "checked_at": checked},
        },
        "places": out,
        "unmatched": unmatched,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--years", type=int, default=4, help="올해부터 거슬러 볼 수질 조사 해 수")
    ap.add_argument("--max-calls", type=int, default=40)
    ap.add_argument("--key-file", type=Path)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR / "beaches")
    a = ap.parse_args(argv)
    site = Site(a.site)
    configure(site)
    key = load_key(a.key_file)
    budget = Budget(a.max_calls)
    today = dt.datetime.now(KST).date()
    years = [today.year - i for i in range(a.years)]
    water: list[dict] = []
    water_by_year: dict[int, list[dict]] = {}
    try:
        info = fetch_all(INFO, {}, key, budget, a.cache, f"info-{SIDO}")
        for y in years:   # this year first, back to the first year that has the site's rows (only that year is used)
            water_by_year[y] = fetch_all(WATER, {"RES_YEAR": y}, key, budget, a.cache, f"water-{SIDO}-{y}")
            water = ours(water_by_year[y])
            if water:
                break
    except ApiError as e:
        print("RESULT " + json.dumps({"error": str(e), "calls": budget.used}, ensure_ascii=False))
        raise SystemExit(f"해양수산부 API: {e}")
    finally:
        log_calls("1192000(beaches)", site.slug, budget.used)
    places = site.places()
    data = build(info, water, places, today.isoformat(), years)
    print(f"호출 {budget.used}회 · 해수욕장정보 {SIDO} {len(info)}행({NAME} {data['sources']['info'][f'rows_{SLUG}']}) · "
          f"수질 " + ", ".join(f"{y} {len(water_by_year[y])}행({NAME} {len(ours(water_by_year[y]))})" for y in water_by_year))
    for pid, b in data["places"].items():
        w = b.get("water") or {}
        print(f"  {pid} {b['name']} ← {b['sta_nm']} ({b['match']}) 수질 {w.get('year')} {w.get('result')} "
              f"{w.get('checked')} 조사 {len(w.get('surveys') or [])}회")
    for u in data["unmatched"]:
        print("  잇지 않음:", u)
    result = {"calls": budget.used, "rows": data["sources"]["info"][f"rows_{SLUG}"], "matched": len(data["places"]),
              "unmatched": len(data["unmatched"]), "water_rows": len(water)}
    if not a.apply:
        print("미리보기 — 쓰려면 --apply")
        print("RESULT " + json.dumps(result, ensure_ascii=False))
        return 0
    raw = site.raw / "beaches"
    gun_info = ours(info)
    if gun_info:
        write_csv(raw / f"beach_info_{SLUG}.csv", gun_info)
    if water:
        write_csv(raw / f"beach_water_{SLUG}_{water[0].get('res_year')}.csv", water)
    out = site.out / "beaches.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(data), "utf-8")
    print(f"썼음: {out}")
    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
