"""해·물때 — 한국천문연구원 출몰시각(config public_data.sun_location 지점)과 국립해양조사원 조석예보(고·저조, config
public_data.tide_stations)를 out/<slug>/almanac.json으로(인천각 tools/almanac_incheon.py·군산각 almanac_gunsan.py를 설정으로
일반화, 2026-11-05).

    DATA_GO_KR_KEY=… python tools/almanac.py --site busan             # 받기(캐시) + 미리보기
    DATA_GO_KR_KEY=… python tools/almanac.py --site busan --apply     # almanac.json·원자료 쓰기
        --days 120 (오늘부터 며칠)  --start YYYY-MM-DD  --only sun|tide  --max-calls 2500  --key-file <파일>
    DATA_GO_KR_KEY=… python tools/almanac.py stations --date 20261105  # 예보지점 목록(tide_guide_stations.json)의
        지점마다 하루를 불러 이름·좌표를 cache/tide_stations.json에 둔다(사이트마다 가까운 지점을 고르는 데 쓴다)

규칙(인천각 도구와 같다)
- 키는 환경 변수 DATA_GO_KR_KEY(또는 --key-file; '%'가 있으면 한 번 풀어 쓴다)로만 받고, 모든 메시지에서 가린다.
  공급자 오류 메시지(errMsg·returnAuthMsg·resultMsg)는 그대로 보인다.
- 응답은 하루·지점마다 cache/almanac/에 캐시한다(같은 날짜의 값은 바뀌지 않는다 — 다시 실행하면 부르지 않는다).
  실행당 호출 상한은 --max-calls(재시도도 센다). 하루 한도(서비스마다 10000회, 2026-11-05 응답 머리말)를 넘으면 멈춘다.
- 값은 응답 그대로 옮긴다: 해 시각은 HHMM의 앞뒤 공백만 빼고 HH:MM으로, 조석은 predcDt의 날짜·시각, extrSe 1·3(오전·
  오후 고조) → '만조', 2·4(오전·오후 저조) → '간조', predcTdlvVl(cm)은 숫자 그대로.
- 출몰시각은 천문연 지점(응답의 위·경도) 한 곳 값이다. 이 지점에서 멀리 떨어진 곳(섬·시 경계)의 해 시각은 이 값과
  1~2분 다를 수 있다(_about).
- 조석 지점은 포털 활용가이드의 예보지점 목록(조위관측소 DT_·조석예보지점 SO_·IE_)을 하루씩 불러 얻은 좌표 가운데 사이트의
  바닷가 장소(config tide_basis)에서 약 30km 안의 곳이다(tools/make_configs.py). 지점마다 이름·좌표(응답의 lat·lot)만
  남긴다. 장소마다 가까운 지점을 고르는 일은 화면이 한다.
- 한 묶음(해, 또는 조석 지점 하나)은 기간 전체를 받았을 때만 바꾼다. 오류·상한으로 덜 받은 묶음은 이전 값을 그대로 두고
  알린다(캐시가 있어 다시 실행하면 이어 받는다). 프록시가 연결을 자주 끊어(Connection reset) 한 요청을 5번까지 다시 부른다.
- 원자료: raw/almanac/sun_<slug>.csv, tide_<지점코드>.csv(응답 필드 그대로, 이번 기간).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CACHE_DIR, KST, ApiError, Budget, CallCapError, QuotaError, Site, api_get, dumps,  # noqa: E402
                    load_key, log_calls, write_csv)

SUN = {"provider": "한국천문연구원", "dataset": "한국천문연구원_출몰시각 정보",
       "url": "https://www.data.go.kr/data/15012688/openapi.do",
       "api": "https://apis.data.go.kr/B090041/openapi/service/RiseSetInfoService/getAreaRiseSetInfo",
       "location": ""}
TIDE = {"provider": "해양수산부 국립해양조사원", "dataset": "해양수산부 국립해양조사원_조석예보(고, 저조)",
        "url": "https://www.data.go.kr/data/15156018/openapi.do",
        "api": "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"}
TIDE_STATIONS: dict[str, str] = {}
GUIDE = Path(__file__).resolve().parent / "tide_guide_stations.json"
STATIONS_CACHE = CACHE_DIR / "tide_stations.json"
SUN_FIELDS = {"sunrise": "sunrise", "sunset": "sunset", "civilm": "civil_dawn", "civile": "civil_dusk"}
TIDE_TYPE = {"1": "만조", "2": "간조", "3": "만조", "4": "간조"}   # extrSe: 1 오전 고조, 2 오전 저조, 3 오후 고조, 4 오후 저조
DEFAULT_DAYS = 120
DEFAULT_MAX_CALLS = 2500
NAME = ""        # '부산'
SLUG = ""
FAR_NOTE = ""
DAYS_NOTE = ""


def configure(site: Site) -> None:
    global NAME, SLUG, FAR_NOTE, TIDE_STATIONS, DAYS_NOTE
    DAYS_NOTE = site.pd.get("sun_days_note") or ""
    SUN["location"] = site.pd["sun_location"]
    NAME, SLUG = site.region["short"], site.slug
    FAR_NOTE = site.pd.get("sun_far_note") or "시 경계나 섬처럼 이 지점에서 멀리 떨어진 곳"
    TIDE_STATIONS = dict(site.pd.get("tide_stations") or {})


def xml_items(text: str) -> tuple[str, str, list[dict]]:
    """(resultCode, resultMsg, [item as {tag: text stripped}]) of a data.go.kr XML response."""
    root = ET.fromstring(text)
    code = (root.findtext(".//header/resultCode") or "").strip()
    msg = (root.findtext(".//header/resultMsg") or "").strip()
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    return code, msg, items


def hhmm(v: str) -> str | None:
    """'0654  ' → '06:54' (only the format changes); blank, '----' or other text → None."""
    v = (v or "").strip()
    return f"{v[:2]}:{v[2:4]}" if len(v) >= 4 and v[:4].isdigit() and int(v[:2]) < 24 and int(v[2:4]) < 60 else None


def sun_day(item: dict) -> dict:
    """Our sun fields of one getAreaRiseSetInfo item ({'sunrise': '06:54', 'sunset': '17:39', ...})."""
    return {ours: t for theirs, ours in SUN_FIELDS.items() if (t := hhmm(item.get(theirs, "")))}


def level(v: str):
    """predcTdlvVl as a number, as given ('190.0' → 190, '183.5' → 183.5)."""
    f = float(v)
    return int(f) if f == int(f) else f


def tide_rows(items: list[dict]) -> dict[str, list[dict]]:
    """{date: [{time, type, level_cm}]} of getTideFcstHghLwApi items (predcDt 'YYYY-MM-DD HH:MM'), by time."""
    out: dict[str, list[dict]] = {}
    for it in items:
        when = (it.get("predcDt") or "").strip()
        kind = TIDE_TYPE.get((it.get("extrSe") or "").strip())
        if len(when) < 16 or not kind or not (it.get("predcTdlvVl") or "").strip():
            continue
        out.setdefault(when[:10], []).append({"time": when[11:16], "type": kind, "level_cm": level(it["predcTdlvVl"])})
    return {d: sorted(v, key=lambda x: x["time"]) for d, v in out.items()}


def dates(start: dt.date, days: int) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(days)]


def cached(cache: Path, name: str, fetch) -> str:
    f = cache / name
    if f.is_file():
        return f.read_text("utf-8")
    text = fetch()
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(text, "utf-8")
    return text


def fetch_sun(days: list[dt.date], key: str, budget: Budget, cache: Path) -> tuple[list[dict], str | None]:
    """The getAreaRiseSetInfo item of each day (location SUN["location"]), from the cache or one call a day. Stops at the first
    error: (items so far, error message or None)."""
    got = []
    for d in days:
        ymd = d.strftime("%Y%m%d")
        try:
            def call():
                text = api_get(SUN["api"], {"location": SUN["location"], "locdate": ymd}, key, budget)
                code, msg, items = xml_items(text)
                if code != "00" or not items:
                    raise ApiError(f"{ymd}: {code} {msg} (항목 {len(items)})")
                return text
            text = cached(cache, f"sun-{SUN['location']}-{ymd}.xml", call)
        except ApiError as e:
            return got, f"출몰시각 {ymd}: {e}"
        got.append(xml_items(text)[2][0])
    return got, None


def fetch_tide(obs: str, days: list[dt.date], key: str, budget: Budget, cache: Path) -> tuple[list[dict], str | None]:
    """The getTideFcstHghLwApi items of one station for each day (type xml, the format of the portal's guide)."""
    got = []
    for d in days:
        ymd = d.strftime("%Y%m%d")
        try:
            def call():
                text = api_get(TIDE["api"], {"obsCode": obs, "reqDate": ymd, "type": "xml", "numOfRows": 10,
                                             "pageNo": 1}, key, budget)
                code, msg, _ = xml_items(text)
                if code not in ("00", "0"):
                    raise ApiError(f"{ymd}: {code} {msg}")
                return text
            text = cached(cache, f"tide-{obs}-{ymd}.xml", call)
        except ApiError as e:
            return got, f"조석예보 {obs}({TIDE_STATIONS.get(obs, '')}) {ymd}: {e}"
        got += xml_items(text)[2]
    return got, None


def sun_block(items: list[dict]) -> tuple[dict, dict]:
    """({date: sun fields}, point {lat, lng} of the location as the response gives it)."""
    out, point = {}, {}
    for it in items:
        d = it.get("locdate", "")
        if len(d) == 8:
            out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = sun_day(it)
        if not point and it.get("latitudeNum") and it.get("longitudeNum"):
            point = {"lat": float(it["latitudeNum"]), "lng": float(it["longitudeNum"])}
    return out, point


def tide_station(obs: str, items: list[dict]) -> dict:
    """{name, lat, lng, days} of one station (name and point from the response; the list's name if it has none)."""
    first = next((it for it in items if it.get("lat") and it.get("lot")), {})
    st = {"name": next((it["obsvtrNm"] for it in items if it.get("obsvtrNm")), TIDE_STATIONS.get(obs, obs))}
    if first:
        st.update({"lat": float(first["lat"]), "lng": float(first["lot"])})
    st["days"] = tide_rows(items)
    return st


def about(start: dt.date, days: int, has_tide: bool = True, wants_tide: bool = True) -> str:
    end = start + dt.timedelta(days=days - 1)
    return (f"{NAME} 해·물때 {start.isoformat()}~{end.isoformat()}({days}일). sun: 한국천문연구원 출몰시각 '{SUN['location']}' 지점의 "
            "일출·일몰·시민박명(아침 civil_dawn, 저녁 civil_dusk) — 응답의 HHMM을 HH:MM으로만 바꿨다. "
            f"{FAR_NOTE}의 해 시각은 이 값과 1~2분 다를 수 있다. " + (f"{DAYS_NOTE} " if DAYS_NOTE else "")
            + (("tide: 국립해양조사원 조석예보(고·저조) 지점별 만조·간조 시각과 예측 조위(cm) — 지점 좌표만 두고 장소마다 "
                "가까운 지점은 화면이 고른다. 조석은 예보값이다. ") if has_tide else
               ("tide: 아직 없다 — 국립해양조사원 조석예보(고·저조)를 다 받지 못했다. 다시 실행하면 채운다. " if wants_tide else ""))
            + "tools/almanac.py(공공데이터 모음 도구)가 만든다.")


def build(old: dict, start: dt.date, days: int, today: dt.date, sun: tuple[list[dict], str | None] | None,
          tides: dict[str, tuple[list[dict], str | None]]) -> tuple[dict, list[str]]:
    """The new almanac.json from the fetched blocks: a complete block replaces the old one, an incomplete one keeps the
    old (with a note). Returns (data, notes)."""
    notes = []
    data = {"_about": about(start, days, wants_tide=bool(TIDE_STATIONS)), "sources": dict(old.get("sources") or {}),
            "sun": old.get("sun") or {}, "tide": dict(old.get("tide") or {})}
    want = {d.isoformat() for d in dates(start, days)}
    if sun is not None:
        items, err = sun
        block, point = sun_block(items)
        if err or set(block) != want:
            notes.append(f"해: {len(block)}/{days}일만 받음 — 이전 값 유지" + (f" ({err})" if err else ""))
        else:
            data["sun"] = dict(sorted(block.items()))
            data["sources"]["sun"] = {**{k: SUN[k] for k in ("provider", "dataset", "url", "api", "location")},
                                      **point, "base_date": start.isoformat(), "days": days,
                                      "checked_at": today.isoformat()}
    for obs, (items, err) in tides.items():
        st = tide_station(obs, items)
        if err or set(st["days"]) != want:
            notes.append(f"조석 {obs}: {len(st['days'])}/{days}일만 받음 — 이전 값 유지" + (f" ({err})" if err else ""))
            continue
        data["tide"][obs] = {**st, "checked_at": today.isoformat()}
        data["sources"]["tide"] = {**{k: TIDE[k] for k in ("provider", "dataset", "url", "api")},
                                   "base_date": start.isoformat(), "days": days, "checked_at": today.isoformat()}
    if not data["tide"]:
        data.pop("tide")
        data["sources"].pop("tide", None)
        data["_about"] = about(start, days, has_tide=False, wants_tide=bool(TIDE_STATIONS))
    return data, notes


def probe_stations(key: str, day: str, max_calls: int) -> dict:
    """Name and point of every station of the guide's list, from one day's answer (cached like the daily calls)."""
    guide = json.loads(GUIDE.read_text("utf-8"))["stations"]
    old = json.loads(STATIONS_CACHE.read_text("utf-8")) if STATIONS_CACHE.is_file() else {"stations": {}}
    budget = Budget(max_calls)
    cache = CACHE_DIR / "almanac"
    out = dict(old.get("stations") or {})
    errors = {}
    d = dt.date(int(day[:4]), int(day[4:6]), int(day[6:]))
    try:
        for obs, name in guide.items():
            if obs in out and out[obs].get("lat"):
                continue
            items, err = fetch_tide(obs, [d], key, budget, cache)
            if err:
                errors[obs] = err
                continue
            st = tide_station(obs, items)
            out[obs] = {"guide_name": name, "name": st["name"], "lat": st.get("lat"), "lng": st.get("lng")}
    finally:
        log_calls("1192136/tideFcstHghLw(stations)", "_all", budget.used)
    doc = {"_about": "예보지점 목록(tools/tide_guide_stations.json)의 지점마다 하루 조석예보를 불러 얻은 이름·좌표(응답 값).",
           "date": day, "stations": dict(sorted(out.items())), "errors": errors}
    STATIONS_CACHE.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"stations": len(out), "with_point": sum(1 for v in out.values() if v.get("lat")), "errors": len(errors),
            "calls": budget.used, "remaining": budget.remaining}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", nargs="?", choices=("run", "stations"), default="run")
    ap.add_argument("--site")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=None, help="며칠(기본 config sun_days, 없으면 120)")
    ap.add_argument("--start", help="첫날 YYYY-MM-DD(기본: 오늘, 한국 시각)")
    ap.add_argument("--date", help="stations: 부를 날 YYYYMMDD")
    ap.add_argument("--only", choices=("sun", "tide"))
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--key-file", type=Path)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR / "almanac")
    a = ap.parse_args(argv)
    key = load_key(a.key_file)
    if a.cmd == "stations":
        print(json.dumps(probe_stations(key, a.date or dt.datetime.now(KST).strftime("%Y%m%d"), a.max_calls),
                         ensure_ascii=False))
        return 0
    site = Site(a.site)
    configure(site)
    today = dt.datetime.now(KST).date()
    start = dt.date.fromisoformat(a.start) if a.start else today
    a.days = a.days or int(site.pd.get("sun_days") or DEFAULT_DAYS)
    span = dates(start, a.days)
    budget = Budget(a.max_calls)
    stopped = ""
    try:
        sun = fetch_sun(span, key, budget, a.cache) if a.only in (None, "sun") else None
        tides = {}
        if a.only in (None, "tide"):
            for obs in TIDE_STATIONS:
                tides[obs] = fetch_tide(obs, span, key, budget, a.cache)
                if budget.used >= budget.max:
                    break
    finally:
        log_calls("B090041+1192136(almanac)", site.slug, budget.used)
    for blk in ([sun] if sun else []) + list(tides.values()):
        if blk[1] and ("하루 한도" in blk[1] or "LIMITED" in blk[1].upper()):
            stopped = blk[1]
    out = site.out / "almanac.json"
    old = json.loads(out.read_text("utf-8")) if out.is_file() else {}
    data, notes = build(old, start, a.days, today, sun, tides)
    print(f"호출 {budget.used}회(상한 {budget.max}, 남은 하루 한도 {budget.remaining})")
    if data.get("sun"):
        first = next(iter(data["sun"]))
        print(f"해 {len(data['sun'])}일 {first}~{list(data['sun'])[-1]} 예: {first} {data['sun'][first]}")
    for obs, st in (data.get("tide") or {}).items():
        n = sum(len(v) for v in st["days"].values())
        print(f"조석 {obs} {st['name']} ({st.get('lat')}, {st.get('lng')}) {len(st['days'])}일 {n}건")
    for n in notes:
        print("주의:", n)
    result = {"calls": budget.used, "sun_days": len(data.get("sun") or {}), "tide_stations": len(data.get("tide") or {}),
              "tide_wanted": len(TIDE_STATIONS), "notes": notes}
    if not a.apply:
        print("미리보기 — 쓰려면 --apply")
        print("RESULT " + json.dumps(result, ensure_ascii=False))
        return 0
    raw = site.raw / "almanac"
    if sun is not None and not any(n.startswith("해:") for n in notes):
        write_csv(raw / f"sun_{SLUG}.csv", sun[0])
    for obs, (items, err) in tides.items():
        if obs in (data.get("tide") or {}) and not err and items:
            write_csv(raw / f"tide_{obs}.csv", items)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(data), "utf-8")
    print(f"썼음: {out}")
    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
