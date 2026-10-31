"""군산 해·물때 — 한국천문연구원 출몰시각(군산)과 국립해양조사원 조석예보(고·저조)를 data/gunsan/almanac.json으로
(운영자 결정 2026-10-31 '데이터 다 추출해서 사이트에 반영' — 군산각 추가 출처).

    DATA_GO_KR_KEY=… python tools/almanac_gunsan.py --data data/gunsan             # 받기(캐시) + 미리보기
    DATA_GO_KR_KEY=… python tools/almanac_gunsan.py --data data/gunsan --apply     # almanac.json·원자료 쓰기
        --days 120 (오늘부터 며칠)  --start YYYY-MM-DD  --only sun|tide  --max-calls 800  --key-file <파일>

규칙
- 키는 환경 변수 DATA_GO_KR_KEY(또는 --key-file; '%'가 있으면 한 번 풀어 쓴다)로만 받고, 모든 메시지에서 가린다.
  공급자 오류 메시지(errMsg·returnAuthMsg·resultMsg)는 그대로 보인다.
- 응답은 하루·지점마다 data/cache/almanac/에 캐시한다(같은 날짜의 값은 바뀌지 않는다 — 다시 실행하면 부르지 않는다).
  실행당 호출 상한은 --max-calls(재시도도 센다).
- 값은 응답 그대로 옮긴다: 해 시각은 HHMM의 앞뒤 공백만 빼고 HH:MM으로, 조석은 predcDt의 날짜·시각, extrSe 1·3(오전·
  오후 고조) → '만조', 2·4(오전·오후 저조) → '간조', predcTdlvVl(cm)은 숫자 그대로.
- 출몰시각은 천문연 '군산' 지점(응답의 위·경도) 한 곳 값이다. 고군산군도는 서쪽이라 1~2분쯤 다를 수 있다(_about).
- 조석은 지점마다 이름·좌표(응답의 lat·lot)만 남긴다. 장소마다 가까운 지점을 고르는 일은 화면이 한다.
- 한 묶음(해, 또는 조석 지점 하나)은 기간 전체를 받았을 때만 바꾼다. 오류·상한으로 덜 받은 묶음은 이전 값을 그대로 두고
  알린다(캐시가 있어 다시 실행하면 이어 받는다). 2026-10-31 조석예보는 기관 서버(khoa.go.kr/oceandata)가 503으로
  돌려보내 포털이 HTTP_ERROR(04)를 준다 — 요청 형식(obsCode·reqDate·type)은 포털 활용가이드와 같다.
- 원자료: data/raw/gunsan/almanac/sun_gunsan.csv, tide_<지점코드>.csv(응답 필드 그대로, 이번 기간).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SUN = {"provider": "한국천문연구원", "dataset": "한국천문연구원_출몰시각 정보",
       "url": "https://www.data.go.kr/data/15012688/openapi.do",
       "api": "https://apis.data.go.kr/B090041/openapi/service/RiseSetInfoService/getAreaRiseSetInfo",
       "location": "군산"}
TIDE = {"provider": "해양수산부 국립해양조사원", "dataset": "해양수산부 국립해양조사원_조석예보(고, 저조)",
        "url": "https://www.data.go.kr/data/15156018/openapi.do",
        "api": "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"}
# 조석 예보지점(포털 활용가이드 '예보지점 목록'에서 군산 바다에 있는 곳): 군산(군산 외항), 말도(고군산군도 서쪽 끝),
# 연도항(연도), 어청도, 위도(부안 — 고군산군도 남쪽 바다). 장소마다 가까운 곳은 화면이 좌표로 고른다.
TIDE_STATIONS = {"DT_0018": "군산", "SO_0547": "말도", "SO_1269": "연도항", "DT_0037": "어청도", "DT_0068": "위도"}
# 응답의 해 시각 필드 → 우리 키(시민박명: 해 뜨기 전·진 뒤 밝은 때)
SUN_FIELDS = {"sunrise": "sunrise", "sunset": "sunset", "civilm": "civil_dawn", "civile": "civil_dusk"}
TIDE_TYPE = {"1": "만조", "2": "간조", "3": "만조", "4": "간조"}   # extrSe: 1 오전 고조, 2 오전 저조, 3 오후 고조, 4 오후 저조
RETRY_GW = ("APPLICATION_ERROR", "SERVICETIMEOUT_ERROR", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND")
DEFAULT_DAYS = 120
DEFAULT_MAX_CALLS = 800


class ApiError(RuntimeError):
    """A provider or network failure; the message is the provider's own, the key masked."""


class CallCapError(ApiError):
    """This run's call cap is used up — the next run continues from the cache."""


class Budget:
    def __init__(self, max_calls: int):
        self.max, self.used = max_calls, 0

    def spend(self) -> None:
        if self.used >= self.max:
            raise CallCapError(f"호출 상한 {self.max}회 — 캐시로 이어서 다시 실행")
        self.used += 1


def load_key(key_file: Path | None = None) -> str:
    """The data.go.kr key from --key-file or DATA_GO_KR_KEY ('%…' encoded form unquoted once); never printed."""
    raw = key_file.read_text("utf-8").strip() if key_file else os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not raw:
        raise SystemExit("키가 없습니다 — 환경 변수 DATA_GO_KR_KEY 또는 --key-file")
    return urllib.parse.unquote(raw) if "%" in raw else raw


def mask(text: str, key: str) -> str:
    for form in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}:
        if form:
            text = text.replace(form, "«KEY»")
    return text


def gateway_error(text: str) -> str | None:
    """'errMsg returnAuthMsg (code)' of a data.go.kr gateway refusal (XML or JSON), else None."""
    if "OpenAPI_ServiceResponse" not in text and "cmmMsgHeader" not in text:
        return None
    try:
        j = json.loads(text)
        h = (j.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader") or {}
    except ValueError:
        try:
            el = ET.fromstring(text).find(".//cmmMsgHeader")
            h = {c.tag: (c.text or "").strip() for c in el} if el is not None else {}
        except ET.ParseError:
            return text[:300]
    return f"{h.get('errMsg', '')} {h.get('returnAuthMsg', '')} ({h.get('returnReasonCode', '')})".strip()


def api_get(url: str, params: dict, key: str, budget: Budget, tries: int = 3, timeout: int = 60) -> str:
    """GET url?serviceKey=…&params (urlencode encodes the key once). Retries a dropped connection, a 5xx and a gateway
    timeout; a gateway refusal or 4xx is raised at once. Every attempt counts against the budget."""
    q = urllib.parse.urlencode({"serviceKey": key, **params})
    err = ""
    for i in range(tries):
        budget.spend()
        retry = True
        try:
            with urllib.request.urlopen(f"{url}?{q}", timeout=timeout) as r:
                text = r.read().decode("utf-8", "replace")
            gw = gateway_error(text)
            if not gw:
                return text
            err, retry = f"포털 게이트웨이: {gw}", any(m in gw for m in RETRY_GW)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            err, retry = f"HTTP {e.code} {gateway_error(body) or body[:300]}", e.code >= 500
        except Exception as e:   # noqa: BLE001 — connection reset through the proxy, timeouts
            err = f"{type(e).__name__}: {e}"
        if not retry:
            break
        if i < tries - 1:
            time.sleep(2 + 2 * i)
    raise ApiError(mask(err, key))


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
    """The getAreaRiseSetInfo item of each day (location 군산), from the cache or one call a day. Stops at the first
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
    """({date: sun fields}, point {lat, lng} of the 군산 location as the response gives it)."""
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


def height(o) -> int:
    if isinstance(o, dict):
        return 1 + max((height(v) for v in o.values()), default=0)
    if isinstance(o, list):
        return 1 + max((height(v) for v in o), default=0)
    return 0


def dumps(data) -> str:
    """JSON indented by 1, with on one line: an object of plain values, a list up to objects of plain values, and an
    object in a list up to two levels deep (a day, a survey per line)."""
    marks: dict[str, str] = {}

    def walk(o, in_list=False):
        h = height(o)
        if (isinstance(o, dict) and h <= (2 if in_list else 1)) or (isinstance(o, list) and h <= 2):
            k = f"\x00{len(marks)}\x00"
            marks[json.dumps(k)] = json.dumps(o, ensure_ascii=False)
            return k
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v, True) for v in o]
        return o
    text = json.dumps(walk(data), ensure_ascii=False, indent=1)
    for k, v in marks.items():
        text = text.replace(k, v)
    return text + "\n"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def about(start: dt.date, days: int, has_tide: bool = True) -> str:
    end = start + dt.timedelta(days=days - 1)
    return (f"군산 해·물때 {start.isoformat()}~{end.isoformat()}({days}일). sun: 한국천문연구원 출몰시각 '군산' 지점의 "
            "일출·일몰·시민박명(아침 civil_dawn, 저녁 civil_dusk) — 응답의 HHMM을 HH:MM으로만 바꿨다. 고군산군도는 "
            "지점보다 서쪽이라 1~2분쯤 다를 수 있다. "
            + ("tide: 국립해양조사원 조석예보(고·저조) 지점별 만조·간조 시각과 예측 조위(cm) — 지점 좌표만 두고 장소마다 "
               "가까운 지점은 화면이 고른다. 조석은 예보값이다. " if has_tide else
               "tide: 아직 없다 — 국립해양조사원 조석예보(고·저조) API가 기관 서버 오류(포털 HTTP_ERROR)로 답하지 않아 "
               "받지 못했다. 다시 실행하면 채운다. ")
            + "tools/almanac_gunsan.py가 만든다.")


def build(old: dict, start: dt.date, days: int, today: dt.date, sun: tuple[list[dict], str | None] | None,
          tides: dict[str, tuple[list[dict], str | None]]) -> tuple[dict, list[str]]:
    """The new almanac.json from the fetched blocks: a complete block replaces the old one, an incomplete one keeps the
    old (with a note). Returns (data, notes)."""
    notes = []
    data = {"_about": about(start, days), "sources": dict(old.get("sources") or {}),
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
        data["_about"] = about(start, days, has_tide=False)
    return data, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--start", help="첫날 YYYY-MM-DD(기본: 오늘, 한국 시각)")
    ap.add_argument("--only", choices=("sun", "tide"))
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--key-file", type=Path)
    ap.add_argument("--cache", type=Path, default=Path("data/cache/almanac"))
    a = ap.parse_args(argv)
    key = load_key(a.key_file)
    today = dt.datetime.now(KST).date()
    start = dt.date.fromisoformat(a.start) if a.start else today
    span = dates(start, a.days)
    budget = Budget(a.max_calls)
    sun = fetch_sun(span, key, budget, a.cache) if a.only in (None, "sun") else None
    tides = {}
    if a.only in (None, "tide"):
        for obs in TIDE_STATIONS:
            tides[obs] = fetch_tide(obs, span, key, budget, a.cache)
            if budget.used >= budget.max:
                break
    out = a.data / "almanac.json"
    old = json.loads(out.read_text("utf-8")) if out.is_file() else {}
    data, notes = build(old, start, a.days, today, sun, tides)
    print(f"호출 {budget.used}회(상한 {budget.max})")
    if data.get("sun"):
        first = next(iter(data["sun"]))
        print(f"해 {len(data['sun'])}일 {first}~{list(data['sun'])[-1]} 예: {first} {data['sun'][first]}")
    for obs, st in (data.get("tide") or {}).items():
        n = sum(len(v) for v in st["days"].values())
        print(f"조석 {obs} {st['name']} ({st.get('lat')}, {st.get('lng')}) {len(st['days'])}일 {n}건")
    for n in notes:
        print("주의:", n)
    if not a.apply:
        print("미리보기 — 쓰려면 --apply")
        return 0
    raw = a.data.parent / "raw" / a.data.name / "almanac"
    if sun is not None and not any(n.startswith("해:") for n in notes):
        write_csv(raw / "sun_gunsan.csv", sun[0])
    for obs, (items, err) in tides.items():
        if obs in (data.get("tide") or {}) and not err and items:
            write_csv(raw / f"tide_{obs}.csv", items)
    out.write_text(dumps(data), "utf-8")
    print(f"썼음: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
