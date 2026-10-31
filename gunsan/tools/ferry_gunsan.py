"""군산 여객선 — 한국해양교통안전공단 '여객선 운항상태 정보'에서 군산 항로의 구조(항로·기항지·여객선·필드·상태 값)를
data/gunsan/ferry.json으로(운영자 결정 2026-10-31 '데이터 다 추출해서 사이트에 반영' — 군산각 추가 출처).

    DATA_GO_KR_KEY=… python tools/ferry_gunsan.py --data data/gunsan fetch --date 20261030 --date 20260801
        # 그날 전국 운항상태(1000행씩 모든 쪽)를 받아 군산운항관리센터 항로 행만 data/raw/gunsan/ferry/에 값 그대로
    python tools/ferry_gunsan.py --data data/gunsan            # 미리보기(원자료로 만든 ferry.json)
    python tools/ferry_gunsan.py --data data/gunsan --apply    # ferry.json 쓰기

규칙
- 운항상태는 실시간 값이다: 배가 출항·운항·입항·기항지 도착·완료할 때마다 한 행이 쌓인다(오늘 값은 계속 바뀐다).
  정적 사이트에 그대로 넣지 않는다. ferry.json에는 항로·기항지·여객선·응답 필드·상태 값과 표본일의 운항 기록만 둔다.
  표본 기록은 시간표가 아니다(그날 다닌 배·출항 시각일 뿐, 배와 시각은 날마다·철마다 바뀐다).
- API에는 항로 거름 조건이 없다(출항일자 필수, 여객선명·출항시각만 거를 수 있음). 그래서 하루치 전국(약 5천 행, 1000행씩
  5회)을 받아 거른다. 개발계정 트래픽은 하루 100회 — --max-calls(기본 30)로 실행당 상한을 둔다. 지난 날짜의 응답만
  data/cache/ferry/에 캐시한다(오늘 응답은 바뀌므로 캐시하지 않는다). 키는 DATA_GO_KR_KEY(또는 --key-file)로만 받고
  가린다(tools/almanac_gunsan.py의 api_get).
- 군산 항로: 그날 기항지(portcl_nm) 가운데 하나라도 GUNSAN_PORTS(군산시의 항·섬)인 면허항로. 원자료에는 군산 항로와
  면허항로코드 첫 글자가 같은 항로(군산운항관리센터 관할, 예: 격포-위도)의 행까지 둔다. ferry.json에서 군산이 아닌
  항로는 other_routes에 이름과 기항지만 남긴다.
- 섬 장소: 기항지와 장소는 ISLAND_PLACES 대응표(사람이 이름·주소를 보고 확인)로만 잇는다. 이름만 비슷하다고 잇지 않는다.
- 승선·하선 인원(emkt_nope·lvsp_nope)은 공단이 '참고용'이라 한 값이라 원자료에만 둔다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.almanac_gunsan import KST, ApiError, Budget, api_get, dumps, load_key, write_csv  # noqa: E402

SOURCE = {"provider": "한국해양교통안전공단", "dataset": "한국해양교통안전공단_여객선 운항상태 정보",
          "url": "https://www.data.go.kr/data/15142304/openapi.do",
          "api": "https://apis.data.go.kr/B554035/ferry-route-info-v4/get-ferry-route-info-v4"}
# 요청 변수(포털 명세): serviceKey·pageNo·numOfRows·rlvtYmd 필수, dataType(JSON|XML)·psnshpNm(여객선명)·sailTm(출항시각)·filters
PARAMS = {"rlvtYmd": "출항일자 YYYYMMDD(필수)", "pageNo": "페이지번호(필수)", "numOfRows": "한 페이지 결과 수(필수)",
          "dataType": "JSON 또는 XML", "psnshpNm": "여객선명(그 배의 행만)", "sailTm": "출항시각(예: 830)",
          "filters": "응답에 넣을 칼럼"}
# 응답 필드(포털 명세의 설명 그대로)
FIELDS = {"rlvt_ymd": "출항일자", "psnshp_cd": "여객선코드", "sail_tm": "출항시각", "psnshp_nm": "여객선명",
          "lcns_seawy_nm": "면허항로명", "nvg_seawy_nm": "운항항로명", "nvg_drc_nm": "운항방향명",
          "lcns_seawy_cd": "면허항로코드", "nvg_seawy_cd": "운항항로코드", "nvg_drc_cd": "운항방향코드",
          "nvg_stts_cd": "운항상태코드", "portcl_cd": "기항지코드", "portcl_nm": "기항지명",
          "nvg_stts_chg_dt": "운항상태변경시간", "nvg_stts_nm": "운항상태명", "emkt_nope": "승선인원수",
          "lvsp_nope": "하선인원수", "vsl_no": "선박번호"}
# 군산시의 항·섬(기항지명이 이 가운데 하나면 군산 항로)
GUNSAN_PORTS = ("군산", "개야", "개야도", "어청", "어청도", "연도", "장자도", "관리도", "방축도", "명도", "말도", "선유도",
                "무녀도", "신시도", "야미도", "비안도", "두리도", "횡경도")
# 기항지명 → 그 섬(또는 그 섬의 여객터미널) 장소 id — 2026-10-31 places.json의 이름·주소로 확인. 관리도·개야도는 섬
# 장소가 없어(관리도캠핑장은 섬이 아니라 캠핑장) 넣지 않는다.
ISLAND_PLACES = {
    "어청": ["tourapi-126297"],                                  # 어청도(옥도면 어청도길)
    "연도": ["tourapi-126298"],                                  # 연도(옥도면 연도1길)
    "장자도": ["gunsan-static-m2203", "tourapi-2748799", "tourapi-2748760"],   # 장자도·장자도여객터미널·장자도선착장
    "방축도": ["tourapi-126296"],                                # 방축도(옥도면 방축도길)
    "명도": ["tourapi-3590209"],                                 # 명도(옥도면 명도길)
    "말도": ["tourapi-3592202"],                                 # 말도(옥도면 말도리)
}
ROWS = 1000
DEFAULT_MAX_CALLS = 30


def items_of(body: dict) -> tuple[list[dict], int]:
    """(rows, totalCount) of a JSON answer; a header other than 200/00 is an error (the provider's words)."""
    r = body.get("response") or {}
    head = r.get("header") or {}
    if str(head.get("resultCode")) not in ("200", "00", "0"):
        raise ApiError(f"{head.get('resultCode')} {head.get('resultMsg')}")
    b = r.get("body") or {}
    box = b.get("items")
    items = (box.get("item") or []) if isinstance(box, dict) else []
    return ([items] if isinstance(items, dict) else items), int(b.get("totalCount") or 0)


def fetch_day(ymd: str, key: str, budget: Budget, cache: Path, today: dt.date) -> list[dict]:
    """Every row of one day, nationwide (ROWS a page). Pages of a past day are cached; today's are not."""
    rows, page, total = [], 1, None
    past = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])) < today
    while total is None or (page - 1) * ROWS < total:
        f = cache / f"{ymd}-p{page}.json"
        if past and f.is_file():
            body = json.loads(f.read_text("utf-8"))
        else:
            body = json.loads(api_get(SOURCE["api"], {"pageNo": page, "numOfRows": ROWS, "dataType": "JSON",
                                                      "rlvtYmd": ymd}, key, budget, timeout=90))
            items_of(body)
            if past:
                cache.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(body, ensure_ascii=False), "utf-8")
        got, total = items_of(body)
        rows += got
        if not got:
            break
        page += 1
    return rows


def route_ports(rows: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = collections.defaultdict(set)
    for r in rows:
        if r.get("portcl_nm"):
            out[r.get("lcns_seawy_cd") or ""].add(r["portcl_nm"])
    return out


def gunsan_routes(rows: list[dict]) -> set[str]:
    """면허항로코드 of the routes that call at a GUNSAN_PORTS port that day."""
    return {c for c, ports in route_ports(rows).items() if ports & set(GUNSAN_PORTS)}


def keep_rows(rows: list[dict]) -> list[dict]:
    """The rows of the Gunsan routes and of the routes whose code shares their first letter (the same 운항관리센터)."""
    letters = {c[:1] for c in gunsan_routes(rows) if c}
    return [r for r in rows if (r.get("lcns_seawy_cd") or "")[:1] in letters]


def hm(sail_tm: str) -> str:
    """'830' → '08:30' (sail_tm as the API writes it, hours without a leading zero)."""
    s = str(sail_tm or "").strip()
    return f"{int(s[:-2]):02d}:{s[-2:]}" if s.isdigit() and 3 <= len(s) <= 4 else s


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build(days: dict[str, list[dict]], checked: str) -> dict:
    """ferry.json from {YYYY-MM-DD: rows} (the raw files)."""
    every = [r for rows in days.values() for r in rows]
    ours = gunsan_routes(every)
    ports_by = route_ports(every)
    routes: dict[str, dict] = {}
    other: dict[str, dict] = {}
    status = {}
    for r in sorted(every, key=lambda r: (r.get("rlvt_ymd") or "", r.get("nvg_stts_chg_dt") or "")):
        code = r.get("lcns_seawy_cd") or ""
        if r.get("nvg_stts_cd"):
            status[str(r["nvg_stts_cd"])] = r.get("nvg_stts_nm") or ""
        if code not in ours:
            other.setdefault(code, {"name": r.get("lcns_seawy_nm"), "ports": sorted(ports_by.get(code, ())),
                                    "why": "기항지가 군산시가 아니다"})
            continue
        rt = routes.setdefault(code, {"name": r.get("lcns_seawy_nm"), "sea_routes": {}, "ports": [], "ships": [],
                                      "places": [], "samples": {}})
        rt["sea_routes"].setdefault(r.get("nvg_seawy_cd") or "", r.get("nvg_seawy_nm"))
        port = {"code": r.get("portcl_cd"), "name": r.get("portcl_nm")}
        if port["name"] and port not in rt["ports"]:
            rt["ports"].append(port)   # first seen first (rows in time order)
        ship = {"code": r.get("psnshp_cd"), "name": r.get("psnshp_nm"), "vsl_no": r.get("vsl_no")}
        if ship not in rt["ships"]:
            rt["ships"].append(ship)
    for code, rt in routes.items():
        rt["places"] = sorted({pid for p in rt["ports"] for pid in ISLAND_PLACES.get(p["name"], ())})
        for day, rows in sorted(days.items()):
            runs: dict[tuple, list[dict]] = collections.defaultdict(list)
            for r in rows:
                if r.get("lcns_seawy_cd") == code:
                    runs[(r.get("psnshp_nm"), r.get("nvg_drc_nm"), r.get("sail_tm"), r.get("nvg_seawy_nm"))].append(r)
            got = []
            for (ship, drc, sail, sea), rs in runs.items():
                rs = sorted(rs, key=lambda x: x.get("nvg_stts_chg_dt") or "")
                got.append({"ship": ship, "direction": drc, "sail": hm(sail), "sea_route": sea,
                            "calls": list(dict.fromkeys(x["portcl_nm"] for x in rs if x.get("portcl_nm"))),
                            "last_status": rs[-1].get("nvg_stts_nm")})
            if got:
                rt["samples"][day] = sorted(got, key=lambda x: x["sail"].zfill(5))
    places: dict[str, list[str]] = collections.defaultdict(list)
    for code, rt in sorted(routes.items()):
        for pid in rt["places"]:
            places[pid].append(code)
    return {
        "_about": ("군산 여객선 항로 — 한국해양교통안전공단 여객선 운항상태 정보의 군산 항로(기항지가 군산시인 면허항로)와 "
                   "기항지·여객선, 응답 필드와 운항상태 값, 표본일의 운항 기록. 운항상태는 실시간 값이라 이 파일에는 "
                   "넣지 않았다(화면에 보이려면 서버 함수나 잦은 빌드가 받아야 한다). samples는 그날 다닌 배·출항 시각일 "
                   "뿐 시간표가 아니다. places는 섬 장소 id → 그 섬에 들르는 항로. tools/ferry_gunsan.py가 만든다."),
        "source": {**SOURCE, "sample_dates": sorted(days), "checked_at": checked,
                   "traffic": "개발계정 하루 100회(운영계정은 활용사례 등록 후 늘릴 수 있음)",
                   "note": "항로로 거를 수 없어 하루치 전국(약 5천 행)을 1000행씩 받거나, 여객선명(psnshpNm)으로 배마다 받는다"},
        "params": PARAMS,
        "fields": FIELDS,
        "status": dict(sorted(status.items())),
        "routes": dict(sorted(routes.items())),
        "other_routes": dict(sorted(other.items())),
        "places": dict(sorted(places.items())),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    fe = sub.add_parser("fetch", help="그날 전국 운항상태를 받아 군산운항관리센터 항로 행만 원자료로 옮긴다")
    fe.add_argument("--date", action="append", required=True, help="YYYYMMDD(여러 번 줄 수 있다)")
    fe.add_argument("--key-file", type=Path)
    fe.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    fe.add_argument("--cache", type=Path, default=Path("data/cache/ferry"))
    a = ap.parse_args(argv)
    raw = a.data.parent / "raw" / a.data.name / "ferry"
    today = dt.datetime.now(KST).date()
    if a.cmd == "fetch":
        key = load_key(a.key_file)
        budget = Budget(a.max_calls)
        for ymd in a.date:
            try:
                rows = fetch_day(ymd, key, budget, a.cache, today)
            except ApiError as e:
                raise SystemExit(f"{ymd}: {e} (호출 {budget.used}회)")
            keep = keep_rows(rows)
            print(f"{ymd}: 전국 {len(rows)}행 → 군산운항관리센터 항로 {len(keep)}행 "
                  f"({', '.join(sorted({r['lcns_seawy_cd'] + ' ' + r['lcns_seawy_nm'] for r in keep}))})")
            if keep:
                write_csv(raw / f"ferry_status_{ymd}.csv", keep)
        print(f"호출 {budget.used}회(상한 {budget.max})")
        return 0
    days = {f"{f.stem[-8:-4]}-{f.stem[-4:-2]}-{f.stem[-2:]}": read_csv(f) for f in sorted(raw.glob("ferry_status_*.csv"))}
    if not days:
        raise SystemExit(f"원자료가 없습니다 — 먼저 fetch ({raw})")
    data = build(days, today.isoformat())
    for code, rt in data["routes"].items():
        print(f"{code} {rt['name']}: 기항지 {'·'.join(p['name'] for p in rt['ports'])} / 배 "
              f"{', '.join(s['name'] for s in rt['ships'])} / 장소 {rt['places']} / 표본 {list(rt['samples'])}")
    for code, rt in data["other_routes"].items():
        print(f"(군산 아님) {code} {rt['name']} {rt['ports']}")
    print("상태 값:", data["status"])
    if not a.apply:
        print("미리보기 — 쓰려면 --apply")
        return 0
    out = a.data / "ferry.json"
    out.write_text(dumps(data), "utf-8")
    print(f"썼음: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
