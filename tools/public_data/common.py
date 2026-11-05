"""공통 — 키·가리기·설정·파일·호출 상한(인천각 tools/almanac_incheon.py·tourapi_related.py·tago_incheon.py와
pipeline/tourapi.py에서 가져온 것을 한곳에 모음, 2026-11-05).

설정: config/<slug>.json 하나가 한 사이트의 값이다. 나중에 그 사이트 site.json의 'public_data' 묶음으로 옮길 수 있게
사이트 저장소 경로(data_dir)와 '나중에 site.json에 들어갈 값'(public_data)을 나눠 둔다.

    {"slug": "busan", "data_dir": "/home/user/busan/data/busan",
     "public_data": {"region": {...}, "mois_groups": {...}, "tourapi_area": {...}, "datalab": {...},
                     "sun_location": "부산", "tide_stations": {...}, "beaches": {...}, "ferry": {...}, "tago": {...}}}

키는 환경 변수 DATA_GO_KR_KEY(없으면 TOURAPI_KEY)로만 받는다. '%'가 있으면 한 번 풀어 쓴다. 모든 메시지에서
«KEY»로 가리고, 캐시·원자료·결과 파일에는 쓰지 않는다(요청 주소를 저장하지 않는다).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
REPO = Path(__file__).resolve().parents[2]
# 수원각 저장소로 옮김(2026-11-05): 작업 폴더는 PUBDATA_WORK(기본 data/cache/public_data — 커밋하지 않음). 설정 파일
# config/<slug>.json이 없으면 data/<slug>/site.json의 'public_data' 묶음을 읽는다(data_dir = data/<slug>).
ROOT = Path(os.environ.get("PUBDATA_WORK") or REPO / "data" / "cache" / "public_data")
CONFIG_DIR = ROOT / "config"
OUT_DIR = ROOT / "out"
CACHE_DIR = ROOT / "cache"
QUOTA_MARKERS = ("LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS", "LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS",
                 "QUOTA_EXCEEDED", "TOO_MANY_REQUESTS")
RETRY_GW = ("APPLICATION_ERROR", "SERVICETIMEOUT_ERROR", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND", "HTTP_ERROR")


# ---------------------------------------------------------------- errors

class ApiError(RuntimeError):
    """A provider or network failure; the message is the provider's own, the key masked."""


class CallCapError(ApiError):
    """This run's call cap is used up — the next run continues from the cache."""


class QuotaError(ApiError):
    """The provider's daily quota (트래픽 초과) — stop this service, the cache lets tomorrow's run continue."""


# ---------------------------------------------------------------- key

def normalize_key(raw: str) -> str:
    key = (raw or "").strip().strip('"').strip("'")
    return urllib.parse.unquote(key) if "%" in key else key


def load_key(key_file: Path | None = None) -> str:
    raw = key_file.read_text("utf-8") if key_file else (os.environ.get("DATA_GO_KR_KEY") or os.environ.get("TOURAPI_KEY") or "")
    key = normalize_key(raw)
    if not key:
        raise SystemExit("키가 없습니다 — 환경 변수 DATA_GO_KR_KEY(또는 TOURAPI_KEY)나 --key-file")
    return key


def mask(text, key: str) -> str:
    """Every form of the key (decoded, encoded once, form-encoded) replaced by «KEY»."""
    out = str(text or "")
    if not key or len(key) < 6:
        return out
    for form in sorted({key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}, key=len, reverse=True):
        out = out.replace(form, "«KEY»")
    return out


def is_quota(text: str) -> bool:
    t = str(text or "").upper()
    return any(m in t for m in QUOTA_MARKERS) or "RETURNREASONCODE>22<" in t.replace(" ", "") or "(22)" in t


# ---------------------------------------------------------------- budget + plain GET

class Budget:
    def __init__(self, max_calls: int):
        self.max, self.used = max_calls, 0
        self.remaining: str | None = None   # X-RateLimit-Remaining of the last answer (the service's daily quota)

    def spend(self) -> None:
        if self.used >= self.max:
            raise CallCapError(f"호출 상한 {self.max}회 — 캐시로 이어서 다시 실행")
        self.used += 1


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


def api_get(url: str, params: dict, key: str, budget: Budget, tries: int = 5, timeout: int = 60) -> str:
    """GET url?serviceKey=…&params. Retries a dropped connection, a 5xx and a gateway timeout; a gateway refusal or 4xx
    is raised at once (QuotaError for the daily quota). Every attempt counts against the budget."""
    q = urllib.parse.urlencode({"serviceKey": key, **params})
    err = ""
    for i in range(tries):
        budget.spend()
        retry = True
        try:
            with urllib.request.urlopen(f"{url}?{q}", timeout=timeout) as r:
                budget.remaining = r.headers.get("X-RateLimit-Remaining") or budget.remaining
                text = r.read().decode("utf-8", "replace")
            gw = gateway_error(text)
            if not gw:
                return text
            err, retry = f"포털 게이트웨이: {gw}", any(m in gw for m in RETRY_GW)
            if is_quota(gw) and "PER_SECOND" not in gw:
                raise QuotaError(mask(err, key))
        except QuotaError:
            raise
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            err, retry = f"HTTP {e.code} {gateway_error(body) or body[:300]}", e.code >= 500 or e.code == 429
            if is_quota(body) and "PER_SECOND" not in body.upper():
                raise QuotaError(mask(err, key)) from None
        except Exception as e:   # noqa: BLE001 — connection reset through the proxy, timeouts
            err = f"{type(e).__name__}: {e}"
        if not retry:
            break
        if i < tries - 1:
            time.sleep(2 + 2 * i)
    raise ApiError(mask(err, key))


# ---------------------------------------------------------------- config + site paths

class Site:
    """One site of the run: slug, its repo data dir (read only), its config and the staging output dir."""

    def __init__(self, slug: str, config: Path | None = None, out: Path | None = None):
        self.slug = slug
        self.config_path = config or CONFIG_DIR / f"{slug}.json"
        if not self.config_path.is_file() and (REPO / "data" / slug / "site.json").is_file():
            site = json.loads((REPO / "data" / slug / "site.json").read_text("utf-8"))
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps({"slug": slug, "data_dir": str(REPO / "data" / slug),
                                                    "public_data": site["public_data"]}, ensure_ascii=False, indent=1)
                                        + "\n", "utf-8")
        self.cfg = json.loads(self.config_path.read_text("utf-8"))
        self.pd = self.cfg["public_data"]
        self.data = Path(self.cfg["data_dir"])
        self.out = out or OUT_DIR / slug
        self.raw = self.out / "raw"

    @property
    def region(self) -> dict:
        return self.pd["region"]

    def places(self) -> list[dict]:
        p = json.loads((self.data / "places.json").read_text("utf-8"))
        return p if isinstance(p, list) else p.get("places", [])

    def save_config(self) -> None:
        self.config_path.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=1) + "\n", "utf-8")


def all_slugs() -> list[str]:
    return sorted(p.stem for p in CONFIG_DIR.glob("*.json") if not p.stem.startswith("_"))


# ---------------------------------------------------------------- text, geometry

def squash(s) -> str:
    return " ".join(str(s or "").split())


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    k = math.pi / 180
    x = (b[1] - a[1]) * k * math.cos((a[0] + b[0]) / 2 * k)
    return 6371000 * math.hypot(x, (b[0] - a[0]) * k)


def josa(word: str, pair: str) -> str:
    """word + the right particle of pair ('을를', '이가', '은는', '과와'): '부산을', '대구를'."""
    ch = (word or " ")[-1]
    has = 0xAC00 <= ord(ch) <= 0xD7A3 and (ord(ch) - 0xAC00) % 28 != 0
    return word + (pair[0] if has else pair[1])


def iso(ymd) -> str:
    s = re.sub(r"\D", "", str(ymd or ""))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else ""


# ---------------------------------------------------------------- files

def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], cols: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, data, indent: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", "utf-8")


def height(o) -> int:
    if isinstance(o, dict):
        return 1 + max((height(v) for v in o.values()), default=0)
    if isinstance(o, list):
        return 1 + max((height(v) for v in o), default=0)
    return 0


def dumps(data) -> str:
    """JSON indented by 1, with on one line: an object of plain values, a list up to objects of plain values, and an
    object in a list up to two levels deep (a day, a survey per line) — tools/almanac_incheon.py's layout."""
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


def today_kst() -> dt.date:
    return dt.datetime.now(KST).date()


def log_calls(service: str, slug: str, calls: int, note: str = "") -> None:
    """Append one line to cache/calls.log (service, site, live calls) — the report counts calls from it."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_DIR / "calls.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": dt.datetime.now(KST).isoformat(timespec="seconds"), "service": service, "site": slug,
                            "calls": calls, "note": note}, ensure_ascii=False) + "\n")
