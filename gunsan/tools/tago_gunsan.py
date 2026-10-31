"""군산을 오가는 열차·고속버스·시외버스·항공편 — 국토교통부 TAGO 4종(열차정보·고속버스정보·시외버스정보·국내항공운항정보)
에서 평일 하루와 주말 하루의 배차를 받아 data/gunsan/transport_tago.json으로 만든다(운영자 결정 2026-10-31 '데이터 다
추출해서 사이트에 반영').

    DATA_GO_KR_KEY=… python tools/tago_gunsan.py --data data/gunsan fetch     # API 호출 → data/raw/gunsan/tago/
    python tools/tago_gunsan.py --data data/gunsan                            # 미리보기(노선·날짜별 횟수·첫차~막차·요금)
    python tools/tago_gunsan.py --data data/gunsan --apply                    # data/gunsan/transport_tago.json 쓰기

    fetch 옵션: --weekday YYYY-MM-DD --weekend YYYY-MM-DD (기본: 내일부터 가장 가까운 평일·토/일), --max-calls 350,
                --key-file <파일>(없으면 환경 변수 DATA_GO_KR_KEY), --cache data/cache/tago

규칙
- 값은 응답 그대로 둔다: 역·터미널·공항 이름, 열차 등급(traingradename)·열차 번호, 버스 등급(gradeNm)·노선 ID, 항공사·편명,
  출발·도착 시각(dep·arr, YYYYMMDDHHMM[SS]), 요금(원 — 숫자 문자열은 정수로만 바꾼다). 화면용 값은 별도 필드(dep_hm·arr_hm
  '05:34', dep_plus_days·arr_plus_days)로만 더한다.
- 노선은 ROUTES에 적은 짝(군산 쪽 ID, 상대 ID)을 두 방향 모두, 기준일마다 한 번씩 묻는다. 0건인 짝도 routes에 count 0으로
  남긴다 — TAGO에 0건이라는 뜻이지 운행이 없다는 뜻이 아니다(시외버스정보에는 군산 출발과 전북 안 노선이 없다, 2026-10-31).
- ID와 이름은 TAGO 목록(역·터미널·공항)에서 확인한 값이고, fetch가 목록을 다시 받아 ID·이름이 달라졌으면 알린다.
- 원자료(data/raw/gunsan/tago/)는 응답의 item을 값 그대로, 서비스·오퍼레이션·조회 인자(키 제외)와 함께 둔다.
- 키는 환경 변수 DATA_GO_KR_KEY(또는 --key-file)로만 받고, 로그·오류·캐시·원자료 어디에도 남기지 않는다(«KEY»로 가림).
  공급자 오류 메시지(resultMsg·returnAuthMsg)는 그대로 보인다. 실행당 호출 상한(--max-calls)과 캐시(data/cache/tago/)를 둔다.
- 항공 요금(economyCharge·prestigeCharge)은 응답이 0을 준다 — 요금이 없다는 뜻이라 화면에 '0원'으로 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tourapi import normalize_key, redact  # noqa: E402

BASE = "https://apis.data.go.kr/1613000"
PROVIDER = "국토교통부"
MODES = ("train", "express_bus", "intercity_bus", "flight")
SOURCES = {
    "train": {"service": "TrainInfo", "operation": "GetStrtpntAlocFndTrainInfo",
              "dataset": "국토교통부_(TAGO)_열차정보", "url": "https://www.data.go.kr/data/15098552/openapi.do",
              "params": ("depPlaceId", "arrPlaceId")},
    "express_bus": {"service": "ExpBusInfo", "operation": "GetStrtpntAlocFndExpbusInfo",
                    "dataset": "국토교통부_(TAGO)_고속버스정보", "url": "https://www.data.go.kr/data/15098522/openapi.do",
                    "params": ("depTerminalId", "arrTerminalId")},
    "intercity_bus": {"service": "SuburbsBusInfo", "operation": "GetStrtpntAlocFndSuberbsBusInfo",
                      "dataset": "국토교통부_(TAGO)_시외버스정보", "url": "https://www.data.go.kr/data/15098541/openapi.do",
                      "params": ("depTerminalId", "arrTerminalId")},
    "flight": {"service": "DmstcFlightNvgInfo", "operation": "GetFlightOpratInfoList",
               "dataset": "국토교통부_(TAGO)_국내항공운항정보", "url": "https://www.data.go.kr/data/15098526/openapi.do",
               "params": ("depAirportId", "arrAirportId")},
}
# TAGO 목록에서 확인한 ID → 이름(2026-10-31). 목록 오퍼레이션: (서비스, 오퍼레이션, 인자, ID 필드, 이름 필드)
LISTS = {
    "train": ("TrainInfo", "GetCtyAcctoTrainSttnList", tuple({"cityCode": c} for c in ("11", "25", "34", "35")),
              "nodeid", "nodename"),
    "express_bus": ("ExpBusInfo", "GetExpBusTrminlList", ({},), "terminalId", "terminalNm"),
    "intercity_bus": ("SuburbsBusInfo", "GetSuberbsBusTrminlList", ({},), "terminalId", "terminalNm"),
    "flight": ("DmstcFlightNvgInfo", "GetArprtList", ({},), "airportId", "airportNm"),
}
EXTRA_LISTS = (("TrainInfo", "GetVhcleKndList", {}), ("ExpBusInfo", "GetExpBusGradList", {}),
               ("DmstcFlightNvgInfo", "GetAirmanList", {}))
NAMES = {
    # 열차: 군산역과 장항선 주요 역(용산·영등포는 서울, 천안은 경부선, 익산은 호남선·전라선 갈아타는 역), 대전·서대전
    # (가이드 guide-12가 '대전→군산 무궁화호'를 적어 확인용으로 묻는다)
    "NAT081388": "군산", "NAT010032": "용산", "NAT010091": "영등포", "NAT010971": "천안", "NAT030879": "익산",
    "NAT011668": "대전", "NAT030057": "서대전",
    # 고속버스
    # (센트럴시티는 목록에 NAEK020·NAEK021 두 ID가 있고 군산 노선은 NAEK021(호남선)에만 나온다 — NAEK020은 묻지 않는다)
    "NAEK610": "군산", "NAEK611": "군산대야", "NAEK021": "센트럴시티(서울)",
    "NAEK010": "서울경부", "NAEK030": "동서울", "NAEK050": "서울남부", "NAEK105": "인천공항T1", "NAEK117": "인천공항T2",
    "NAEK300": "대전복합", "NAEK500": "광주(유·스퀘어)", "NAEK600": "전주", "NAEK615": "익산", "NAEK700": "부산",
    "NAEK800": "동대구",
    # 시외버스(가이드 guide-33이 적은 도착지와 전주·익산·인천공항·서울 쪽)
    "NAI5403701": "군산", "NAI5493301": "전주시외터미널", "NAI5467401": "익산", "NAI5437901": "김제", "NAI5615801": "정읍",
    "NAI5630801": "부안", "NAI6193701": "광주(유·스퀘어)", "NAI5864201": "목포", "NAI5796001": "순천", "NAI3345801": "보령",
    "NAI3364501": "서천", "NAI3455101": "대전복합", "NAI3417501": "유성복합", "NAI3015401": "세종시", "NAI3112001": "천안",
    "NAI2839701": "청주", "NAI2224201": "인천", "NAI2238202": "인천공항2터미널", "NAI0511601": "동서울",
    "NAI0671801": "서울남부", "NAI1349701": "성남", "NAI1658501": "수원터미널", "NAI1045001": "고양종합",
    "NAI4248201": "대구서부", "NAI4620401": "부산동부", "NAI5135601": "마산", "NAI3815701": "경주시외", "NAI4472001": "울산",
    # 항공(목록의 공항 전부)
    "NAARKJK": "군산공항", "NAARKPC": "제주국제공항", "NAARKSS": "김포국제공항", "NAARKSI": "인천국제공항",
    "NAARKPK": "김해국제공항", "NAARKTN": "대구국제공항", "NAARKJJ": "광주공항", "NAARKJB": "무안국제공항",
    "NAARKPS": "사천공항", "NAARKNY": "양양국제공항", "NAARKJY": "여수공항", "NAARKPU": "울산공항", "NAARKNW": "원주공항",
    "NAARKTU": "청주국제공항", "NAARKTH": "포항경주공항",
}
GUNSAN = {"train": ("NAT081388",), "express_bus": ("NAEK610", "NAEK611"), "intercity_bus": ("NAI5403701",),
          "flight": ("NAARKJK",)}
_OTHERS = {
    "train": ("NAT010032", "NAT010091", "NAT010971", "NAT030879", "NAT011668", "NAT030057"),
    "express_bus": ("NAEK021", "NAEK010", "NAEK030", "NAEK050", "NAEK105", "NAEK117", "NAEK300", "NAEK500",
                    "NAEK600", "NAEK615", "NAEK700", "NAEK800"),
    "intercity_bus": tuple(k for k in NAMES if k.startswith("NAI") and k != "NAI5403701"),
    "flight": tuple(k for k in NAMES if k.startswith("NAAR") and k != "NAARKJK"),
}
# (군산 쪽 ID, 상대 ID) — 두 방향 모두 묻는다. 군산대야(NAEK611)는 센트럴시티(서울)만(2026-10-31 확인한 유일한 노선).
ROUTES = {
    "train": [("NAT081388", o) for o in _OTHERS["train"]],
    "express_bus": [("NAEK610", o) for o in _OTHERS["express_bus"]] + [("NAEK611", "NAEK021")],
    "intercity_bus": [("NAI5403701", o) for o in _OTHERS["intercity_bus"]],
    "flight": [("NAARKJK", o) for o in _OTHERS["flight"]],
}
DOW = "월화수목금토일"
ROWS_PER_PAGE = 100
RAW_DIR = "tago"
OUT_FILE = "transport_tago.json"


class TagoError(RuntimeError):
    """A TAGO call that failed; the message has the provider's words with the key masked."""


# ---------------------------------------------------------------- dates


def base_dates(today: dt.date) -> dict[str, dt.date]:
    """The nearest weekday (Mon–Fri) and weekend day (Sat/Sun) from tomorrow on — today's schedule is never used."""
    out: dict[str, dt.date] = {}
    d = today + dt.timedelta(days=1)
    while len(out) < 2:
        out.setdefault("weekend" if d.weekday() >= 5 else "weekday", d)
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------- response helpers


def items_of(body: dict) -> list[dict]:
    """The item list of a response body: '' (no rows), {'item': {...}} (one row) and {'item': [...]} all become a list."""
    items = (body or {}).get("items")
    if not isinstance(items, dict):
        return []
    it = items.get("item")
    if isinstance(it, dict):
        return [it]
    return list(it) if isinstance(it, list) else []


def provider_message(text: str) -> str:
    """The provider's own error words of a non-JSON (XML gateway) answer: returnAuthMsg, errMsg, resultMsg — else the
    first 300 characters as they came."""
    found = [m.group(1).strip() for tag in ("returnAuthMsg", "errMsg", "resultMsg", "returnReasonCode")
             for m in [re.search(rf"<{tag}>(.*?)</{tag}>", text or "", re.S)] if m]
    return " ".join(found) if found else (text or "").strip()[:300]


def parse_answer(text: str) -> dict:
    """The response body of a TAGO answer; TagoError with the provider's message when it is not a normal answer."""
    try:
        payload = json.loads(text)
    except ValueError:
        raise TagoError(provider_message(text)) from None
    resp = payload.get("response") or {}
    head = resp.get("header") or {}
    code = str(head.get("resultCode", ""))
    if code not in ("00", "0", "0000"):
        raise TagoError(f"resultCode={code or '?'} {head.get('resultMsg', '')}".strip())
    return resp.get("body") or {}


# ---------------------------------------------------------------- client


class Client:
    """A TAGO client: on-disk cache (per service), a per-run cap on live calls, 3 tries on a dropped connection, the key
    masked in every message. `opener(url) -> text` is replaceable (tests)."""

    def __init__(self, key: str, cache: Path | None, max_calls: int = 350, opener=None, sleep=time.sleep):
        self.key = normalize_key(key)
        self.cache = cache
        self.max_calls = max_calls
        self.calls = 0
        self.opener = opener or self._open
        self.sleep = sleep

    @staticmethod
    def _open(url: str) -> str:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code} {provider_message(e.read().decode('utf-8', 'replace'))}"
            if e.code >= 500:   # a gateway hiccup: tried again like a dropped connection
                raise OSError(msg) from None
            raise TagoError(msg) from None

    def _cache_file(self, service: str, op: str, params: dict) -> Path | None:
        if not self.cache:
            return None
        h = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        return self.cache / service / f"{op}-{h}.json"

    def page(self, service: str, op: str, params: dict) -> dict:
        """One page (body) of service/op with params (no key); cached on success."""
        f = self._cache_file(service, op, params)
        if f and f.is_file():
            return json.loads(f.read_text("utf-8"))
        q = urllib.parse.urlencode({"serviceKey": self.key, "_type": "json", **params})
        url = f"{BASE}/{service}/{op}?{q}"
        err = ""
        for i in range(3):
            if self.calls >= self.max_calls:
                raise TagoError(f"호출 상한 {self.max_calls}회 — 캐시로 이어서 다시 실행")
            self.calls += 1
            try:
                body = parse_answer(self.opener(url))
                break
            except TagoError as e:   # the provider answered: show its words, do not retry
                raise TagoError(redact(f"{service}/{op} {params}: {e}", self.key)) from None
            except Exception as e:   # noqa: BLE001 — a dropped connection (proxy 'Connection reset'): try again
                err = redact(f"{service}/{op} {params}: {e}", self.key)
                if i < 2:
                    self.sleep(2 + 2 * i)
        else:
            raise TagoError(err)
        if f:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(body, ensure_ascii=False), "utf-8")
        return body

    def all_items(self, service: str, op: str, params: dict) -> tuple[int, list[dict]]:
        """(totalCount, every item) of a query, page by page."""
        items: list[dict] = []
        page, total = 1, None
        while total is None or len(items) < total:
            body = self.page(service, op, {**params, "numOfRows": ROWS_PER_PAGE, "pageNo": page})
            total = int(body.get("totalCount") or 0)
            got = items_of(body)
            items += got
            if not got:
                break
            page += 1
        return total or 0, items


# ---------------------------------------------------------------- fetch


def fetch(client: Client, raw: Path, dates: dict[str, dt.date], today: dt.date) -> dict:
    """The code lists (codes.json) and, for every ROUTES pair both ways on every base date, the items as returned
    (<mode>_<YYYYMMDD>.json) into raw; manifest fetch.json. Raw files of other dates are removed (superseded)."""
    raw.mkdir(parents=True, exist_ok=True)
    codes, warnings = {}, []
    for mode, (service, op, arg_sets, idf, namef) in LISTS.items():
        seen = {}
        for args in arg_sets:
            _, items = client.all_items(service, op, dict(args))
            codes[f"{service}/{op}" + (f"?{urllib.parse.urlencode(args)}" if args else "")] = items
            seen.update({str(i.get(idf)): i.get(namef) for i in items})
        for pid in {x for pair in ROUTES[mode] for x in pair}:
            if seen.get(pid) != NAMES[pid]:
                warnings.append(f"{mode} {pid}: 목록 이름 {seen.get(pid)!r} ≠ 적어 둔 이름 {NAMES[pid]!r}")
    for service, op, args in EXTRA_LISTS:
        codes[f"{service}/{op}"] = client.all_items(service, op, args)[1]
    write_json(raw / "codes.json", {"fetched_at": today.isoformat(), "provider": PROVIDER, "lists": codes})
    keep = {"codes.json", "fetch.json"}
    for mode in MODES:
        src = SOURCES[mode]
        dep_k, arr_k = src["params"]
        for day, d in dates.items():
            pairs = []
            for a, b in ROUTES[mode]:
                for dep, arr in ((a, b), (b, a)):
                    params = {dep_k: dep, arr_k: arr, "depPlandTime": d.strftime("%Y%m%d")}
                    total, items = client.all_items(src["service"], src["operation"], params)
                    pairs.append({"params": params, "totalCount": total, "items": items})
            name = f"{mode}_{d.strftime('%Y%m%d')}.json"
            keep.add(name)
            write_json(raw / name, {"service": src["service"], "operation": src["operation"], "provider": PROVIDER,
                                    "dataset": src["dataset"], "url": src["url"], "date": d.isoformat(), "day": day,
                                    "fetched_at": today.isoformat(), "pairs": pairs})
    for f in raw.glob("*.json"):
        if f.name not in keep:
            f.unlink()
    manifest = {"fetched_at": today.isoformat(), "calls": client.calls,
                "base_dates": {k: v.isoformat() for k, v in dates.items()}, "warnings": warnings}
    write_json(raw / "fetch.json", manifest)
    return manifest


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", "utf-8")


# ---------------------------------------------------------------- rows


def hm(v) -> str:
    """'05:34' of a TAGO time (YYYYMMDDHHMM[SS], string or number); '' when it has no time."""
    s = re.sub(r"\D", "", str(v if v is not None else ""))
    return f"{s[8:10]}:{s[10:12]}" if len(s) >= 12 else ""


def plus_days(dep, arr) -> int:
    """How many days after the first value's date (a TAGO time or a 'YYYY-MM-DD' base date) the second falls: an
    overnight ride's arrival, or the 00:12 train that belongs to the base date's timetable but leaves the next day."""
    a, b = (re.sub(r"\D", "", str(x if x is not None else ""))[:8] for x in (dep, arr))
    try:
        return (dt.datetime.strptime(b, "%Y%m%d").date() - dt.datetime.strptime(a, "%Y%m%d").date()).days
    except ValueError:
        return 0


def won(v):
    """A fare as an int when the answer gives digits (원), else the value as given (None stays None)."""
    s = str(v).strip() if v is not None else ""
    return int(s) if s.isdigit() else v


def to_row(mode: str, item: dict, date: str, day: str, params: dict) -> dict:
    """One schedule row of a response item: names, times, grade/number and fare as given + dep_hm/arr_hm/arr_plus_days."""
    dep_k, arr_k = SOURCES[mode]["params"]
    base = {"date": date, "day": day, "from_id": params[dep_k], "to_id": params[arr_k]}
    if mode == "train":
        dep, arr = item.get("depplandtime"), item.get("arrplandtime")
        row = {"from": item.get("depplacename"), "to": item.get("arrplacename"), "dep": dep, "arr": arr,
               "type": item.get("traingradename"), "no": item.get("trainno"), "fare": won(item.get("adultcharge"))}
    elif mode == "flight":
        dep, arr = item.get("depPlandTime"), item.get("arrPlandTime")
        row = {"from": item.get("depAirportNm"), "to": item.get("arrAirportNm"), "dep": dep, "arr": arr,
               "airline": item.get("airlineNm"), "no": item.get("vihicleId"),
               "fare_economy": won(item.get("economyCharge")), "fare_prestige": won(item.get("prestigeCharge"))}
    else:
        dep, arr = item.get("depPlandTime"), item.get("arrPlandTime")
        row = {"from": item.get("depPlaceNm"), "to": item.get("arrPlaceNm"), "dep": dep, "arr": arr,
               "type": item.get("gradeNm"), "route_id": item.get("routeId"), "fare": won(item.get("charge"))}
    return {**base, **row, "dep_hm": hm(dep), "arr_hm": hm(arr), "dep_plus_days": plus_days(date, dep),
            "arr_plus_days": plus_days(dep, arr)}


def route_summary(mode: str, rows: list[dict], params: dict, date: str, day: str) -> dict:
    """count, first/last departure (dep_hm), minutes of the shortest/longest ride and the fares by grade of one pair on
    one date (rows of that pair only); a pair TAGO gave no rows for has count 0."""
    dep_k, arr_k = SOURCES[mode]["params"]
    ordered = sorted(rows, key=lambda r: str(r["dep"]))
    fares: dict[str, list] = {}
    for r in ordered:
        if mode == "flight":
            continue
        fares.setdefault(str(r.get("type") or ""), [])
        if r.get("fare") not in fares[str(r.get("type") or "")]:
            fares[str(r.get("type") or "")].append(r.get("fare"))
    mins = [m for m in (ride_minutes(r["dep"], r["arr"]) for r in ordered) if m is not None]
    return {"mode": mode, "date": date, "day": day,
            "from_id": params[dep_k], "from": ordered[0]["from"] if ordered else NAMES.get(params[dep_k], ""),
            "to_id": params[arr_k], "to": ordered[0]["to"] if ordered else NAMES.get(params[arr_k], ""),
            "count": len(ordered), "first": ordered[0]["dep_hm"] if ordered else "",
            "last": ordered[-1]["dep_hm"] if ordered else "",
            "minutes": [min(mins), max(mins)] if mins else [],
            **({"fares": {k: sorted(v, key=str) for k, v in fares.items()}} if mode != "flight" else {})}


def ride_minutes(dep, arr) -> int | None:
    a, b = (re.sub(r"\D", "", str(x if x is not None else ""))[:12] for x in (dep, arr))
    try:
        t = dt.datetime.strptime(b, "%Y%m%d%H%M") - dt.datetime.strptime(a, "%Y%m%d%H%M")
    except ValueError:
        return None
    return int(t.total_seconds() // 60)


def build(raw: Path) -> dict:
    """transport_tago.json of the raw files of the last fetch (fetch.json)."""
    manifest = json.loads((raw / "fetch.json").read_text("utf-8"))
    checked = manifest["fetched_at"]
    dates = manifest["base_dates"]
    out: dict = {
        "_about": ("군산을 오가는 열차(군산역↔용산·영등포·천안·익산·대전·서대전)·고속버스(군산·군산대야↔서울 등)·시외버스(군산↔전주·익산·"
                   "대전·광주 등)·항공편(군산공항↔전국 공항)의 하루 배차. 국토교통부 TAGO에서 평일 하루와 주말 하루"
                   f"(base_dates)를 {checked}에 조회한 값 그대로다(tools/tago_gunsan.py). dep·arr는 응답 시각"
                   "(YYYYMMDDHHMM[SS]), dep_hm·arr_hm은 화면용 시:분, dep_plus_days는 기준일 다음 날 출발(1 — 자정 "
                   "넘어 떠나는 그날 시간표의 막차), arr_plus_days는 다음 날 도착(1). 요금은 원. "
                   "routes는 조회한 모든 짝(0건 포함)의 횟수·첫차·막차·걸린 분(최소·최대)·등급별 요금이다."),
        "notes": [
            "routes의 count 0은 TAGO에 배차가 없다는 뜻이지 운행이 없다는 뜻이 아니다. 시외버스정보는 군산 출발 배차와 "
            "전주·익산 등 전북 안 노선을 주지 않는다(도착편만 일부 터미널에서 나온다).",
            "열차 요금(adultcharge)은 같은 구간이면 무궁화호·새마을호가 같은 값으로 나온다 — 등급별 운임이 아닐 수 있어 "
            "화면에는 '국토교통부 TAGO 기준'으로 표시하거나 코레일 조회를 안내한다.",
            "항공 요금(fare_economy·fare_prestige)은 응답이 0을 준다 — 요금 없음이라는 뜻이라 '0원'으로 쓰지 않는다.",
            "시각은 조회한 기준일 하루의 배차다. 다른 날은 코레일·코버스·버스타고·티머니·항공사에서 조회한다.",
        ],
        "sources": {},
        "base_dates": {k: {"date": v, "dow": DOW[dt.date.fromisoformat(v).weekday()]} for k, v in dates.items()},
        "routes": [],
    }
    for mode in MODES:
        src = SOURCES[mode]
        out["sources"][mode] = {"provider": PROVIDER, "dataset": src["dataset"], "url": src["url"],
                                "operation": f"{src['service']}/{src['operation']}",
                                "base_date": sorted(dates.values()), "checked_at": checked}
        rows: list[dict] = []
        for day, d in sorted(dates.items(), key=lambda kv: kv[1]):
            f = raw / f"{mode}_{d.replace('-', '')}.json"
            doc = json.loads(f.read_text("utf-8"))
            for pair in doc["pairs"]:
                got = [to_row(mode, it, d, day, pair["params"]) for it in pair["items"]]
                out["routes"].append(route_summary(mode, got, pair["params"], d, day))
                rows += got
        out[mode] = sorted(rows, key=lambda r: (r["date"], r["from_id"], r["to_id"], str(r["dep"])))
    return out


def preview(doc: dict) -> list[str]:
    lines = ["기준일: " + ", ".join(f"{k} {v['date']}({v['dow']})" for k, v in doc["base_dates"].items())]
    for r in doc["routes"]:
        if not r["count"]:
            continue
        fares = " ".join(f"{k} {'/'.join(map(str, v))}" for k, v in (r.get("fares") or {}).items())
        mins = f" {r['minutes'][0]}~{r['minutes'][1]}분" if r["minutes"] else ""
        lines.append(f"{r['mode']:13} {r['date']} {r['from']}→{r['to']}: {r['count']}회 {r['first']}~{r['last']}{mins} {fares}")
    for mode in MODES:
        zero = sorted({f"{r['from']}→{r['to']}" for r in doc["routes"] if r["mode"] == mode and not r["count"]})
        lines.append(f"{mode} 0건 짝 {len(zero)}개: " + ", ".join(zero))
    lines.append("행: " + ", ".join(f"{m} {len(doc[m])}" for m in MODES))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data/gunsan"))
    ap.add_argument("--apply", action="store_true", help=f"data/<지역>/{OUT_FILE} 쓰기")
    sub = ap.add_subparsers(dest="cmd")
    fe = sub.add_parser("fetch", help="TAGO 4종을 불러 원자료(data/raw/<지역>/tago/)를 만든다")
    fe.add_argument("--key-file", type=Path, help="키가 든 파일(없으면 환경 변수 DATA_GO_KR_KEY)")
    fe.add_argument("--max-calls", type=int, default=350)
    fe.add_argument("--cache", type=Path, default=Path("data/cache/tago"))
    fe.add_argument("--weekday", type=dt.date.fromisoformat)
    fe.add_argument("--weekend", type=dt.date.fromisoformat)
    a = ap.parse_args(argv)
    raw = a.data.parent / "raw" / a.data.name / RAW_DIR
    if a.cmd == "fetch":
        key = (a.key_file.read_text("utf-8") if a.key_file else os.environ.get("DATA_GO_KR_KEY", "")).strip()
        if not key:
            raise SystemExit("키가 없습니다 — DATA_GO_KR_KEY 환경 변수나 --key-file")
        today = dt.date.today()
        dates = base_dates(today)
        dates.update({k: v for k, v in (("weekday", a.weekday), ("weekend", a.weekend)) if v})
        client = Client(key, a.cache, a.max_calls)
        try:
            manifest = fetch(client, raw, dates, today)
        except TagoError as e:
            raise SystemExit(f"TAGO 오류: {e} (실호출 {client.calls}회)") from None
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    doc = build(raw)
    print("\n".join(preview(doc)))
    if a.apply:
        write_json(a.data / OUT_FILE, doc)
        print(f"썼음: {a.data / OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
