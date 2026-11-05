"""사이트를 오가는 열차·고속버스·시외버스·항공편 — 국토교통부 TAGO 4종(열차정보·고속버스정보·시외버스정보·국내항공운항정보)
에서 평일 하루와 주말 하루의 배차를 받아 out/<slug>/transport_tago.json으로 만든다(인천각 tools/tago_incheon.py·군산각
tago_gunsan.py를 설정으로 일반화, 2026-11-05).

    DATA_GO_KR_KEY=… python tools/tago.py lists                       # TAGO 목록(역·터미널·공항)을 cache/tago_lists.json에
    DATA_GO_KR_KEY=… python tools/tago.py --site busan discover       # 짝 찾기: config tago.home의 역·터미널·공항마다
        # tago.candidates(주요 상대)와 두 방향으로 평일 기준일 하루를 물어 한 방향이라도 배차가 나온 짝을 config tago.routes에
    DATA_GO_KR_KEY=… python tools/tago.py --site busan fetch          # API 호출 → out/<slug>/raw/tago/
    python tools/tago.py --site busan                                 # 미리보기(노선·날짜별 횟수·첫차~막차·요금)
    python tools/tago.py --site busan --apply                         # out/<slug>/transport_tago.json 쓰기

    fetch·discover 옵션: --weekday YYYY-MM-DD --weekend YYYY-MM-DD (기본: 내일부터 가장 가까운 평일·토/일), --max-calls,
                         --key-file <파일>(없으면 환경 변수 DATA_GO_KR_KEY), --cache cache/tago

규칙(인천각 도구와 같다)
- 값은 응답 그대로 둔다: 역·터미널·공항 이름, 열차 등급(traingradename)·열차 번호, 버스 등급(gradeNm)·노선 ID, 항공사·편명,
  출발·도착 시각(dep·arr, YYYYMMDDHHMM[SS]), 요금(원 — 숫자 문자열은 정수로만 바꾼다). 화면용 값은 별도 필드(dep_hm·arr_hm
  '05:34', dep_plus_days·arr_plus_days)로만 더한다.
- 노선은 config tago.routes에 적은 짝(사이트 쪽 ID, 상대 ID)을 두 방향 모두, 기준일마다 한 번씩 묻는다. 0건인 짝도 routes에
  count 0으로 남긴다 — TAGO에 0건이라는 뜻이지 운행이 없다는 뜻이 아니다. 짝은 discover가 평일 기준일 하루를 사이트 쪽
  역·터미널·공항마다 주요 상대(tago.candidates — 전국 주요 역·터미널·공항과, 시외버스는 같은 시도의 터미널)와 두 방향으로 물어
  한 방향이라도 배차가 나온 것이다. 한 수단에 그런 짝이 없으면 확인용 짝(상대 셋)만 남긴다.
- ID와 이름은 TAGO 목록(역·터미널·공항)에서 확인한 값이고, fetch가 목록을 다시 받아 ID·이름이 달라졌으면 알린다.
  국내항공 공항 목록(GetArprtList)이 요청 형식 오류로 답하지 않으면 군산각 원자료(2026-10-31 받은 공항 15곳)를 쓴다.
- 원자료(raw/tago/)는 응답의 item을 값 그대로, 서비스·오퍼레이션·조회 인자(키 제외)와 함께 둔다.
- 키는 환경 변수 DATA_GO_KR_KEY(또는 --key-file)로만 받고, 로그·오류·캐시·원자료 어디에도 남기지 않는다(«KEY»로 가림).
  공급자 오류 메시지(resultMsg·returnAuthMsg)는 그대로 보인다. 실행당 호출 상한(--max-calls)과 캐시(cache/tago/)를 둔다.
- 항공 요금(economyCharge·prestigeCharge)은 응답이 0을 준다 — 요금이 없다는 뜻이라 화면에 '0원'으로 쓰지 않는다.
- 결과의 사이트 쪽 이름: 엔진마다 읽는 열쇠가 달라 config tago.home_keys에 적은 열쇠로 쓴다('home'·'home_stops' — 이름 목록,
  'homes' — 엔진에 따라 수단별 이름 하나 {수단: 이름} 또는 이름 목록).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, Site, is_quota, josa, log_calls, normalize_key  # noqa: E402
from common import mask as _mask  # noqa: E402

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
TRAIN_CITY_CODES = ("11", "12", "21", "22", "23", "24", "25", "26", "31", "32", "33", "34", "35", "36", "37", "38")
LISTS = {
    "train": ("TrainInfo", "GetCtyAcctoTrainSttnList", tuple({"cityCode": c} for c in TRAIN_CITY_CODES), "nodeid", "nodename"),
    "express_bus": ("ExpBusInfo", "GetExpBusTrminlList", ({},), "terminalId", "terminalNm"),
    "intercity_bus": ("SuburbsBusInfo", "GetSuberbsBusTrminlList", ({},), "terminalId", "terminalNm"),
    "flight": ("DmstcFlightNvgInfo", "GetArprtList", ({},), "airportId", "airportNm"),
}
EXTRA_LISTS = (("TrainInfo", "GetVhcleKndList", {}), ("ExpBusInfo", "GetExpBusGradList", {}),
               ("DmstcFlightNvgInfo", "GetAirmanList", {}))
# 국내항공 공항 목록이 답하지 않을 때: 군산각 data/raw/gunsan/tago/codes.json(2026-10-31 GetArprtList 응답)의 15곳
AIRPORTS_FALLBACK = Path("/home/user/gunsan/data/raw/gunsan/tago/codes.json")
LISTS_CACHE = CACHE_DIR / "tago_lists.json"
# 확인용 짝(한 수단에 배차가 나온 짝이 없을 때)으로 먼저 고르는 상대: 서울·부산 쪽 역·터미널, 제주·김포·인천 공항
CHECK_PREF = {"train": ("NAT010000", "NAT010032", "NAT014445"), "express_bus": ("NAEK010", "NAEK020", "NAEK021", "NAEK030"),
              "intercity_bus": ("NAI0511601", "NAI0671801", "NAI4620401"), "flight": ("NAARKPC", "NAARKSS", "NAARKSI")}
DOW = "월화수목금토일"
ROWS_PER_PAGE = 100
RAW_DIR = "tago"
OUT_FILE = "transport_tago.json"

# set by configure(site)
NAMES: dict[str, str] = {}
HOME: dict[str, list[str]] = {}
ROUTES: dict[str, list[tuple[str, str]]] = {}
LABEL = ""
NOTES_EXTRA: list[str] = []
HOME_KEYS: list[str] = ["home"]


def configure(site: Site) -> None:
    global NAMES, HOME, ROUTES, LABEL, NOTES_EXTRA, HOME_KEYS
    t = site.pd["tago"]
    NAMES = dict(t.get("names") or {})
    HOME = {m: list(t.get("home", {}).get(m) or []) for m in MODES}
    ROUTES = {m: [tuple(p) for p in (t.get("routes") or {}).get(m) or []] for m in MODES}
    LABEL = site.region["short"]
    NOTES_EXTRA = list(t.get("notes") or [])
    HOME_KEYS = list(t.get("home_keys") or ["home"])


def squash(s) -> str:
    return " ".join(str(s or "").split())


def redact(text, key):
    return _mask(text, key)


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

    def __init__(self, key: str, cache: Path | None, max_calls: int = 900, opener=None, sleep=time.sleep):
        self.key = normalize_key(key)
        self.cache = cache
        self.max_calls = max_calls
        self.calls = 0
        self.opener = opener or self._open
        self.sleep = sleep
        import threading
        self._lock = threading.Lock()

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
        for i in range(5):
            with self._lock:
                if self.calls >= self.max_calls:
                    raise TagoError(f"호출 상한 {self.max_calls}회 — 캐시로 이어서 다시 실행")
                self.calls += 1
            try:
                body = parse_answer(self.opener(url))
                break
            except TagoError as e:   # the provider answered: show its words, do not retry
                msg = str(e)
                # the gateway's per-second limit or a timeout is not an answer: wait and try again
                if any(m in msg.upper() for m in ("PER_SECOND", "SERVICETIMEOUT", "APPLICATION_ERROR")) and i < 4:
                    err = redact(f"{service}/{op} {params}: {e}", self.key)
                    self.sleep(2 + 2 * i)
                    continue
                raise TagoError(redact(f"{service}/{op} {params}: {e}", self.key)) from None
            except Exception as e:   # noqa: BLE001 — a dropped connection (proxy 'Connection reset'): try again
                err = redact(f"{service}/{op} {params}: {e}", self.key)
                if i < 4:
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


# ---------------------------------------------------------------- dates


def base_dates(today: dt.date) -> dict[str, dt.date]:
    """The nearest weekday (Mon–Fri) and weekend day (Sat/Sun) from tomorrow on — today's schedule is never used."""
    out: dict[str, dt.date] = {}
    d = today + dt.timedelta(days=1)
    while len(out) < 2:
        out.setdefault("weekend" if d.weekday() >= 5 else "weekday", d)
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------- lists


def fetch_lists(client: Client, today: dt.date) -> dict:
    """Every TAGO code list (stations of every 도시코드, express and intercity terminals, airports, grades) into
    cache/tago_lists.json — shared by every site. The airport list falls back to the 군산각 raw file when TAGO refuses it."""
    lists, notes = {}, []
    for mode, (service, op, arg_sets, idf, namef) in LISTS.items():
        for args in arg_sets:
            name = f"{service}/{op}" + (f"?{urllib.parse.urlencode(args)}" if args else "")
            try:
                lists[name] = client.all_items(service, op, dict(args))[1]
            except TagoError as e:
                if mode != "flight" or not AIRPORTS_FALLBACK.is_file():
                    raise
                old = json.loads(AIRPORTS_FALLBACK.read_text("utf-8"))
                lists[name] = old["lists"].get(name) or []
                notes.append(f"{name}: TAGO 오류({e}) — 군산각 원자료 {old.get('fetched_at')}의 공항 {len(lists[name])}곳을 씀")
    for service, op, args in EXTRA_LISTS:
        try:
            lists[f"{service}/{op}"] = client.all_items(service, op, args)[1]
        except TagoError as e:
            notes.append(f"{service}/{op}: {e}")
    doc = {"fetched_at": today.isoformat(), "provider": PROVIDER, "notes": notes, "lists": lists}
    write_json(LISTS_CACHE, doc)
    return doc


def id_names(doc: dict) -> dict[str, dict[str, str]]:
    """{mode: {id: name}} of the lists (cityName kept for intercity terminals as 'id' → name)."""
    out: dict[str, dict[str, str]] = {m: {} for m in MODES}
    for mode, (service, op, _, idf, namef) in LISTS.items():
        for name, items in doc["lists"].items():
            if name.startswith(f"{service}/{op}"):
                out[mode].update({str(i.get(idf)): i.get(namef) for i in items})
    return out


# ---------------------------------------------------------------- discover


def discover(site: Site, client: Client, probe: dt.date, check_pairs: int = 3, workers: int = 8,
             modes: tuple[str, ...] = MODES) -> dict:
    """For every home ID and every candidate of its mode, both directions on the probe day: the pairs with a departure
    either way go to config tago.routes (and their names to tago.names). A mode with no such pair keeps `check_pairs`
    confirmation pairs per home (count 0 on the page). Every answer is cached, so fetch's weekday reuses them. The
    queries run in `workers` threads (one TAGO answer takes 1~3 s, 2026-11-05)."""
    import concurrent.futures as cf
    t = site.pd["tago"]
    known = id_names(json.loads(LISTS_CACHE.read_text("utf-8")))
    found: dict[str, list] = {m: list((t.get("routes") or {}).get(m) or []) for m in MODES}
    zero: dict[str, list] = {m: [] for m in MODES}
    old = dict(t.get("discovered") or {})
    for mode in modes:
        src = SOURCES[mode]
        dep_k, arr_k = src["params"]
        homes = list(t.get("home", {}).get(mode) or [])
        cands = [c for c in (t.get("candidates", {}).get(mode) or []) if c not in homes]
        found[mode], zero[mode] = [], []
        pairs = [(h, o) for h in homes for o in cands]

        def ask(pair):
            n = 0
            for dep, arr in (pair, pair[::-1]):
                params = {dep_k: dep, arr_k: arr, "depPlandTime": probe.strftime("%Y%m%d")}
                n += len(client.all_items(src["service"], src["operation"], params)[1])
            return n
        with cf.ThreadPoolExecutor(workers) as ex:
            counts = list(ex.map(ask, pairs))
        for pair, n in zip(pairs, counts):
            (found if n else zero)[mode].append(list(pair))
        if homes and not found[mode]:
            pref = CHECK_PREF.get(mode, ())
            rank = lambda z: (pref.index(z[1]) if z[1] in pref else len(pref), cands.index(z[1]))   # noqa: E731
            found[mode] = [p for h in homes for p in sorted([z for z in zero[mode] if z[0] == h], key=rank)[:check_pairs]]
            t.setdefault("check_only", {})[mode] = True
        else:
            t.setdefault("check_only", {}).pop(mode, None)
    t["routes"] = found
    ids = {x for m in MODES for p in found[m] for x in p} | {x for m in MODES for x in t.get("home", {}).get(m) or []}
    t["names"] = {i: known[m][i] for m in MODES for i in sorted(ids) if i in known[m]}
    t["discovered"] = {"date": probe.isoformat(), "calls": client.calls + (old.get("calls", 0) if modes != MODES else 0),
                       "pairs": {m: len(found[m]) for m in MODES},
                       "zero_pairs": {m: (len(zero[m]) if m in modes else (old.get("zero_pairs") or {}).get(m, 0))
                                      for m in MODES}}
    site.save_config()
    return t["discovered"]


# ---------------------------------------------------------------- fetch


def fetch(client: Client, raw: Path, dates: dict[str, dt.date], today: dt.date) -> dict:
    """The code lists (codes.json — the lists of the modes this site asks) and, for every ROUTES pair both ways on every
    base date, the items as returned (<mode>_<YYYYMMDD>.json) into raw; manifest fetch.json. Raw files of other dates are
    removed (superseded)."""
    raw.mkdir(parents=True, exist_ok=True)
    doc = json.loads(LISTS_CACHE.read_text("utf-8")) if LISTS_CACHE.is_file() else fetch_lists(client, today)
    codes, warnings = {}, list(doc.get("notes") or [])
    known = id_names(doc)
    for mode, (service, op, _, idf, namef) in LISTS.items():
        ids = {x for pair in ROUTES[mode] for x in pair}
        for name, items in doc["lists"].items():
            if name.startswith(f"{service}/{op}") and any(str(i.get(idf)) in ids for i in items):
                codes[name] = items
        for pid in ids:
            if known[mode].get(pid) != NAMES.get(pid):
                warnings.append(f"{mode} {pid}: 목록 이름 {known[mode].get(pid)!r} ≠ 적어 둔 이름 {NAMES.get(pid)!r}")
    for service, op, _ in EXTRA_LISTS:
        if f"{service}/{op}" in doc["lists"]:
            codes[f"{service}/{op}"] = doc["lists"][f"{service}/{op}"]
    write_json(raw / "codes.json", {"fetched_at": doc.get("fetched_at"), "provider": PROVIDER, "lists": codes})
    keep = {"codes.json", "fetch.json"}
    for mode in MODES:
        src = SOURCES[mode]
        dep_k, arr_k = src["params"]
        if not ROUTES[mode]:
            continue
        for day, d in dates.items():
            import concurrent.futures as cf
            qs = [{dep_k: dep, arr_k: arr, "depPlandTime": d.strftime("%Y%m%d")}
                  for a, b in ROUTES[mode] for dep, arr in ((a, b), (b, a))]
            with cf.ThreadPoolExecutor(8) as ex:
                got = list(ex.map(lambda p: client.all_items(src["service"], src["operation"], p), qs))
            pairs = [{"params": p, "totalCount": total, "items": items} for p, (total, items) in zip(qs, got)]
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
    path.parent.mkdir(parents=True, exist_ok=True)
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


def build(raw: Path, site: Site) -> dict:
    """transport_tago.json of the raw files of the last fetch (fetch.json)."""
    manifest = json.loads((raw / "fetch.json").read_text("utf-8"))
    checked = manifest["fetched_at"]
    dates = manifest["base_dates"]
    t = site.pd["tago"]
    check_only = t.get("check_only") or {}
    modes = [m for m in MODES if ROUTES[m]]
    homes = {m: [NAMES.get(h, h) for h in HOME[m] if any(h in p for p in ROUTES[m])] for m in modes}
    mode_words = {"train": "열차", "express_bus": "고속버스", "intercity_bus": "시외버스", "flight": "항공편"}
    parts = []
    for m in modes:
        h = "·".join(dict.fromkeys(homes[m]))
        others = list(dict.fromkeys(NAMES.get(o, o) for _, o in ROUTES[m]))
        part = f"{mode_words[m]}({h}↔{'·'.join(others[:4])}{' 등' if len(others) > 4 else ''}"
        part += " — 조회한 날 TAGO에 배차 없음)" if check_only.get(m) else ")"
        parts.append(part)
    out: dict = {
        "_about": (f"{josa(LABEL, '을를')} 오가는 " + "·".join(parts) + "의 하루 배차. 국토교통부 TAGO에서 평일 하루와 주말 하루"
                   f"(base_dates)를 {checked}에 조회한 값 그대로다(tools/tago.py). dep·arr는 응답 시각"
                   "(YYYYMMDDHHMM[SS]), dep_hm·arr_hm은 화면용 시:분, dep_plus_days는 기준일 다음 날 출발(1 — 자정 "
                   "넘어 떠나는 그날 시간표의 막차), arr_plus_days는 다음 날 도착(1). 요금은 원. "
                   "routes는 조회한 모든 짝(0건 포함)의 횟수·첫차·막차·걸린 분(최소·최대)·등급별 요금이다."),
        "notes": [
            "routes의 count 0은 TAGO에 배차가 없다는 뜻이지 운행이 없다는 뜻이 아니다."
            + "".join(f" {LABEL} 쪽 {mode_words[m]}({'·'.join(homes[m])})은 조회한 짝 모두 0건이었다." for m in modes if check_only.get(m)),
            "열차 요금(adultcharge)은 같은 구간이면 무궁화호·새마을호가 같은 값으로 나온다 — 등급별 운임이 아닐 수 있어 "
            "화면에는 '국토교통부 TAGO 기준'으로 표시하거나 코레일 조회를 안내한다.",
            "항공 요금(fare_economy·fare_prestige)은 응답이 0을 준다 — 요금 없음이라는 뜻이라 '0원'으로 쓰지 않는다.",
            "시각은 조회한 기준일 하루의 배차다. 다른 날은 코레일·코버스·버스타고·티머니·항공사에서 조회한다.",
            *NOTES_EXTRA,
        ],
        "sources": {},
        "base_dates": {k: {"date": v, "dow": DOW[dt.date.fromisoformat(v).weekday()]} for k, v in dates.items()},
        "routes": [],
    }
    if t.get("notes_format") == "by_mode":
        # the 경주각 engine reads 'notes' as {mode: the note under that mode} (it replaces its own note for the mode):
        # the list goes to 'notes_all', the per-mode notes are config tago.mode_notes plus the zero-run note
        out["notes_all"] = out.pop("notes")
        by_mode = {m: squash(" ".join(x for x in [
            (t.get("mode_notes") or {}).get(m, ""),
            f"조회한 짝 모두 TAGO에 배차가 없었다(0건 — 운행이 없다는 뜻은 아니다)." if check_only.get(m) else ""] if x))
            for m in modes}
        out["notes"] = {m: v for m, v in by_mode.items() if v}
    names = list(dict.fromkeys(n for m in modes for n in homes[m]))
    for k in HOME_KEYS:
        if k == "homes_by_mode":
            # the 대구각 engine reads {mode: one home name} and else takes names starting with the region: a mode whose
            # home names all start with the region is left to that rule (all kept), else its first (main) home is named
            out["homes"] = {m: homes[m][0] for m in modes
                            if homes[m] and not all(n.startswith(LABEL) for n in homes[m])}
        elif k == "homes_list":      # the 목포각 engine reads 'homes' as a list of names
            out["homes"] = names
        else:
            out[k] = names
    for mode in MODES:
        if not ROUTES[mode]:
            continue
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
        lines.append(f"{mode} 0건 짝 {len(zero)}개: " + ", ".join(zero[:12]) + (" …" if len(zero) > 12 else ""))
    lines.append("행: " + ", ".join(f"{m} {len(doc.get(m) or [])}" for m in MODES))
    return lines


def load_key_arg(a) -> str:
    key = (a.key_file.read_text("utf-8") if a.key_file else (os.environ.get("DATA_GO_KR_KEY") or "")).strip()
    if not key:
        raise SystemExit("키가 없습니다 — DATA_GO_KR_KEY 환경 변수나 --key-file")
    return key


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", nargs="?", choices=("build", "lists", "discover", "fetch"), default="build")
    ap.add_argument("--site")
    ap.add_argument("--apply", action="store_true", help=f"out/<slug>/{OUT_FILE} 쓰기")
    ap.add_argument("--key-file", type=Path, help="키가 든 파일(없으면 환경 변수 DATA_GO_KR_KEY)")
    ap.add_argument("--max-calls", type=int, default=3000)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR / "tago")
    ap.add_argument("--weekday", type=dt.date.fromisoformat)
    ap.add_argument("--weekend", type=dt.date.fromisoformat)
    ap.add_argument("--only", nargs="*", choices=MODES, help="discover: 이 수단만")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    today = dt.date.today()
    dates = base_dates(today)
    dates.update({k: v for k, v in (("weekday", a.weekday), ("weekend", a.weekend)) if v})
    if a.cmd == "lists":
        client = Client(load_key_arg(a), a.cache, a.max_calls)
        try:
            doc = fetch_lists(client, today)
        finally:
            log_calls("1613000(TAGO lists)", "_all", client.calls)
        print(json.dumps({"calls": client.calls, "lists": {k: len(v) for k, v in doc["lists"].items()},
                          "notes": doc["notes"]}, ensure_ascii=False))
        return 0
    site = Site(a.site)
    configure(site)
    raw = site.raw / RAW_DIR
    if a.cmd in ("discover", "fetch"):
        client = Client(load_key_arg(a), a.cache, a.max_calls)
        try:
            if a.cmd == "discover":
                res = discover(site, client, dates["weekday"], workers=a.workers, modes=tuple(a.only or MODES))
                print("RESULT " + json.dumps(res, ensure_ascii=False))
                return 0
            manifest = fetch(client, raw, dates, today)
        except TagoError as e:
            print("RESULT " + json.dumps({"error": str(e), "calls": client.calls}, ensure_ascii=False))
            raise SystemExit(f"TAGO 오류: {e} (실호출 {client.calls}회)") from None
        finally:
            log_calls(f"1613000(TAGO {a.cmd})", site.slug, client.calls)
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    doc = build(raw, site)
    print("\n".join(preview(doc)))
    res = {"routes": len(doc["routes"]), "with_runs": sum(1 for r in doc["routes"] if r["count"]),
           **{m: len(doc.get(m) or []) for m in MODES}}
    if a.apply:
        write_json(site.out / OUT_FILE, doc)
        print(f"썼음: {site.out / OUT_FILE}")
    print("RESULT " + json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
