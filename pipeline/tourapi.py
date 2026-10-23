"""TourAPI client (한국관광공사 국문 관광정보 서비스, KorService2) with an on-disk response cache.

Notes
- The key may be the portal's "Encoding" or "Decoding" form. A key containing '%' is unquoted once,
  then urlencode() encodes it exactly once, so neither form is double-encoded.
- Every successful response is cached under data/cache/tourapi/, so re-runs cost nothing.
- `fetched_dates` records, per answered call, the date its data was fetched: today for a live call, the cache
  file's date for a cached one. Merges use it as checked_at, so a cache-first re-run never bumps a 확인일.
- Each client stops itself after `max_calls` live requests (default 900, inside the development
  account's daily limit). The next run continues from the cache.
- Provider error messages (resultMsg, returnAuthMsg, errMsg) are shown as-is with only the key masked.
- base_url / op_suffix / mobile_app / min_interval / detail_common_params come from site.json -> "tourapi".
  The MobileApp parameter and the User-Agent name no city or brand (DEFAULT_MOBILE_APP unless site.json sets one).
- 한국관광공사 무장애 여행 정보 (KorWithService2, detailWithTour2) is a separate service with its own data.go.kr
  활용신청: barrier_free_client() builds its own client (base_url from site.json tourapi.barrier_free_base_url, else
  BARRIER_FREE_BASE_URL) with its own cache folder, so its calls and cache never mix with KorService2's.

Region codes (resolve_ldong): lDongRegnCd / lDongSignguCd are never written in code or config — they are read from
the provider's ldongCode2 answer at run time, by exact name: the 시·도 whose name is site.json
tourapi.ldong_regn_name (else region_admin), then every 구·군 of `districts` under it (or, without districts, the
locality). A name that matches no code, or more than one, is a RegionCodeError that names it.
tourapi.list_scope: "districts" (default; one list per resolved 구·군, or the 시) or "region" (one list for the
whole 시·도; only for a city that is the whole 시·도: districts configured and locality == region_admin).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_CALLS = 900
DEFAULT_MOBILE_APP = "TravelSite"  # TourAPI's required MobileApp value: neutral unless site.json tourapi.mobile_app
LIST_SCOPES = ("districts", "region")
BARRIER_FREE_BASE_URL = "https://apis.data.go.kr/B551011/KorWithService2"
BARRIER_FREE_CACHE = "barrier_free"   # sub-folder of the TourAPI cache for KorWithService2 responses

CONTENT_TYPES = {
    "12": "관광지", "14": "문화시설", "15": "축제·공연·행사", "25": "여행코스",
    "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점",
}
# contentTypeId -> our entity kind
KIND_BY_TYPE = {"12": "attraction", "14": "attraction", "28": "attraction", "38": "attraction",
                "32": "stay", "39": "food"}

# detailIntro field names per contentTypeId -> our fact keys (TourAPI 4.x manual)
INTRO_FIELDS = {
    "usetime": {"12": "usetime", "14": "usetimeculture", "28": "usetimeleports",
                "38": "opentime", "39": "opentimefood", "15": "playtime"},
    "restdate": {"12": "restdate", "14": "restdateculture", "28": "restdateleports",
                 "38": "restdateshopping", "39": "restdatefood"},
    "usefee": {"14": "usefee", "28": "usefeeleports", "15": "usetimefestival"},
    "parking": {"12": "parking", "14": "parkingculture", "28": "parkingleports",
                "38": "parkingshopping", "39": "parkingfood", "32": "parkinglodging"},
    "parkingfee": {"14": "parkingfee", "28": "parkingfeeleports"},
    "spendtime": {"14": "spendtime", "15": "spendtimefestival", "25": "taketime"},
    "infocenter": {"12": "infocenter", "14": "infocenterculture", "28": "infocenterleports",
                   "38": "infocentershopping", "39": "infocenterfood", "32": "infocenterlodging",
                   "25": "infocentertourcourse", "15": "sponsor1tel"},
    "checkin": {"32": "checkintime"},
    "checkout": {"32": "checkouttime"},
    "menu": {"39": "firstmenu"},
    "babycarriage": {"12": "chkbabycarriage", "14": "chkbabycarriageculture",
                     "28": "chkbabycarriageleports", "38": "chkbabycarriageshopping"},
    "pet": {"12": "chkpet", "14": "chkpetculture", "28": "chkpetleports", "38": "chkpetshopping"},
    "expagerange": {"12": "expagerange", "28": "expagerangeleports"},
    "useseason": {"12": "useseason"},
}

QUOTA_MARKERS = ("LIMITED_NUMBER_OF_SERVICE_REQUESTS", "TOO_MANY_REQUESTS", "QUOTA_EXCEEDED")


class TourAPIError(RuntimeError):
    pass


class TourAPIStopError(TourAPIError):
    """Stop the current run (per-run call cap or provider quota); the next run resumes from cache."""


class TourAPIQuotaError(TourAPIStopError):
    pass


class RegionCodeError(TourAPIError):
    """site.json's 시·도 / 구·군 names do not each match exactly one ldongCode2 code."""


class TourAPIConfigError(ValueError):
    """site.json -> tourapi holds a value this module does not accept."""


def normalize_key(raw: str) -> str:
    """Return the decoded key. A key containing '%' (the portal's Encoding form) is unquoted once."""
    key = (raw or "").strip().strip('"').strip("'")
    return urllib.parse.unquote(key) if "%" in key else key


def redact(text: str, key: str) -> str:
    """Mask every form of the key (decoded, encoded once, form-encoded) in a message."""
    out = str(text or "")
    if not key or len(key) < 6:
        return out
    forms = {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}
    for form in sorted(forms, key=len, reverse=True):
        out = out.replace(form, "«KEY»")
    return out


def _provider_error(label: str, code: str, message: str) -> TourAPIError:
    text = f"{label}: resultCode={code or '?'} {message}".strip()
    if code == "22" or any(marker in str(message).upper() for marker in QUOTA_MARKERS):
        return TourAPIQuotaError(text)
    return TourAPIError(text)


def _xml_error(body: str) -> tuple[str, str] | None:
    def tag(*names: str) -> str:
        for name in names:
            m = re.search(rf"<{name}>\s*([^<]*)<", body or "")
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""
    code = tag("returnReasonCode", "resultCode")
    message = tag("returnAuthMsg", "resultMsg", "errMsg")
    return (code, message) if code or message else None


def parse_items(payload: dict, op: str = "") -> list[dict]:
    """Return the item list from a TourAPI JSON payload (handles dict/list/empty)."""
    label = op or "TourAPI"
    gateway = payload.get("OpenAPI_ServiceResponse") if isinstance(payload, dict) else None
    if isinstance(gateway, dict):
        header = gateway.get("cmmMsgHeader") or {}
        raise _provider_error(label, str(header.get("returnReasonCode", "")),
                              header.get("returnAuthMsg") or header.get("errMsg") or "")
    resp = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(resp, dict):
        raise TourAPIError(f"{label}: 예상과 다른 응답 구조: {json.dumps(payload, ensure_ascii=False)[:300]}")
    header = resp.get("header") or {}
    code = str(header.get("resultCode", ""))
    if code not in ("0000", "00", "0"):
        raise _provider_error(label, code, str(header.get("resultMsg", "")))
    body = resp.get("body") or {}
    items = body.get("items") if isinstance(body, dict) else None
    if not items or not isinstance(items, dict):
        return []
    item = items.get("item")
    if item is None:
        return []
    values = item if isinstance(item, list) else [item]
    if not all(isinstance(value, dict) for value in values):
        raise TourAPIError(f"{label}: 예상과 다른 항목 구조")
    return values


class TourAPI:
    def __init__(self, service_key: str, base_url: str = "https://apis.data.go.kr/B551011/KorService2",
                 op_suffix: str = "2", mobile_app: str = DEFAULT_MOBILE_APP,
                 cache_dir: str | Path = "data/cache/tourapi", min_interval: float = 0.3,
                 detail_common_params: dict | None = None, timeout: int = 20, offline: bool = False,
                 refresh: bool = False, max_calls: int = DEFAULT_MAX_CALLS):
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.service_key = normalize_key(service_key)
        self.base_url = base_url.rstrip("/")
        self.op_suffix = op_suffix
        self.mobile_app = mobile_app
        self.cache_dir = Path(cache_dir)
        self.min_interval = min_interval
        self.detail_common_params = detail_common_params or {}
        self.timeout = timeout
        self.offline = offline  # True: cache only, never call the network
        self.refresh = refresh  # True: ignore cached responses (weekly re-check), still write cache
        self.max_calls = max_calls
        self._last = 0.0
        self.live_calls = 0
        self.cache_hits = 0
        self.fetched_dates: list[str] = []  # ISO date each answered call's data was fetched (see module notes)

    def _cache_path(self, op: str, params: dict) -> Path:
        key = json.dumps([self.base_url, op, sorted(params.items())], ensure_ascii=False)
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{op}-{h}.json"

    def _fail(self, label: str, status, body: str) -> TourAPIError:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            payload = None
        prefix = f"HTTP {status}; " if status not in (None, 200) else ""
        if isinstance(payload, dict):
            try:
                parse_items(payload, label)
            except TourAPIError as err:
                return type(err)(redact(prefix + str(err), self.service_key))
        found = _xml_error(body)
        if found:
            err = _provider_error(label, *found)
            return type(err)(redact(prefix + str(err), self.service_key))
        return TourAPIError(redact(f"{label}: {prefix}JSON이 아닌 응답: {(body or '')[:300]}", self.service_key))

    def call(self, op: str, **params) -> list[dict]:
        label = f"{op}{self.op_suffix}"
        params = {k: v for k, v in params.items() if v not in (None, "")}
        path = self._cache_path(op, params)
        if path.exists() and not self.refresh:
            self.cache_hits += 1
            items = parse_items(json.loads(path.read_text("utf-8")), label)
            self.fetched_dates.append(dt.date.fromtimestamp(path.stat().st_mtime).isoformat())
            return items
        if self.offline:
            raise TourAPIError(f"{label}: 오프라인 모드인데 캐시가 없습니다")
        if not self.service_key:
            raise TourAPIError("TOURAPI_KEY가 없습니다 (.env 또는 환경 변수)")
        if self.live_calls >= self.max_calls:
            raise TourAPIStopError(f"이번 실행의 호출 상한 {self.max_calls}회에 도달 — 다음 실행에서 캐시로 이어 갑니다")
        query = {"serviceKey": self.service_key, "MobileOS": "ETC", "MobileApp": self.mobile_app,
                 "_type": "json", **params}
        url = f"{self.base_url}/{op}{self.op_suffix}?{urllib.parse.urlencode(query)}"
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.live_calls += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"{self.mobile_app} tourapi-client"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            try:
                body = error.read().decode("utf-8", "replace")
            except (OSError, AttributeError):
                body = ""
            if error.code == 429 and not body:
                raise TourAPIQuotaError(f"{label}: HTTP 429 호출 한도") from None
            raise self._fail(label, error.code, body) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise TourAPIError(redact(f"{label}: 네트워크 오류 {type(error).__name__}: {error}",
                                      self.service_key)) from None
        finally:
            self._last = time.monotonic()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise self._fail(label, 200, raw) from None
        try:
            items = parse_items(payload, label)
        except TourAPIError as err:
            raise type(err)(redact(str(err), self.service_key)) from None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
        self.fetched_dates.append(dt.date.today().isoformat())
        return items

    # ---- operations -------------------------------------------------------
    def search_keyword(self, keyword: str, content_type_id: str | None = None, rows: int = 20) -> list[dict]:
        return self.call("searchKeyword", keyword=keyword, contentTypeId=content_type_id,
                         numOfRows=rows, pageNo=1, arrange="A")

    def detail_common(self, content_id: str) -> dict:
        items = self.call("detailCommon", contentId=content_id, **self.detail_common_params)
        return items[0] if items else {}

    def detail_intro(self, content_id: str, content_type_id: str) -> dict:
        items = self.call("detailIntro", contentId=content_id, contentTypeId=content_type_id)
        return items[0] if items else {}

    def detail_info(self, content_id: str, content_type_id: str) -> list[dict]:
        return self.call("detailInfo", contentId=content_id, contentTypeId=content_type_id)

    def detail_image(self, content_id: str) -> list[dict]:
        return self.call("detailImage", contentId=content_id, imageYN="Y", numOfRows=20, pageNo=1)

    def detail_with_tour(self, content_id: str) -> dict:
        """KorWithService2 detailWithTour2 (무장애여행 조회): one item of barrier-free fields (parking, route,
        wheelchair, restroom, stroller, … — 개방데이터 활용매뉴얼(무장애여행) v4.3), {} when the service has none.
        Call it on a barrier_free_client(); the KorService2 base_url has no such operation."""
        return (self.call("detailWithTour", contentId=content_id) or [{}])[0]

    def location_based(self, lat: float, lng: float, radius: int = 2000,
                       content_type_id: str | None = None, rows: int = 40) -> list[dict]:
        # arrange=E : distance order. Items carry 'dist' (metres).
        return self.call("locationBasedList", mapX=lng, mapY=lat, radius=radius,
                         contentTypeId=content_type_id, numOfRows=rows, pageNo=1, arrange="E")

    def ldong_code(self, l_dong_regn_cd: str | None = None, rows: int = 100) -> list[dict]:
        """Statutory region codes (lDongRegnCd, then lDongSignguCd under it) from the provider."""
        return self.call("ldongCode", lDongRegnCd=l_dong_regn_cd, numOfRows=rows, pageNo=1)

    def search_festival(self, event_start_date: str, l_dong_regn_cd: str | None = None,
                        l_dong_signgu_cd: str | None = None, rows: int = 100, page: int = 1) -> list[dict]:
        if not re.fullmatch(r"\d{8}", event_start_date or ""):
            raise ValueError("eventStartDate must be YYYYMMDD")
        return self.call("searchFestival", eventStartDate=event_start_date, lDongRegnCd=l_dong_regn_cd,
                         lDongSignguCd=l_dong_signgu_cd, numOfRows=rows, pageNo=page, arrange="A")

    def area_based(self, l_dong_regn_cd: str | None = None, l_dong_signgu_cd: str | None = None,
                   content_type_id: str | None = None, rows: int = 40, page: int = 1,
                   arrange: str = "A") -> list[dict]:
        """areaBasedList2 with statutory region codes (lDongRegnCd/lDongSignguCd from ldongCode2)."""
        for label, value in (("rows", rows), ("page", page)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if arrange not in {"A", "C", "D", "O", "Q", "R"}:
            raise ValueError("areaBasedList arrange must be A, C, D, O, Q or R")
        region = str(l_dong_regn_cd) if l_dong_regn_cd is not None else None
        district = str(l_dong_signgu_cd) if l_dong_signgu_cd is not None else None
        for label, value in (("lDongRegnCd", region), ("lDongSignguCd", district)):
            if value is not None and not re.fullmatch(r"[0-9]+", value):
                raise ValueError(f"{label} must be a numeric code from the provider")
        if district is not None and region is None:
            raise ValueError("lDongSignguCd requires lDongRegnCd")
        ctype = str(content_type_id) if content_type_id is not None else None
        if ctype is not None and ctype not in CONTENT_TYPES:
            raise ValueError("contentTypeId must be a documented tourism content type")
        return self.call("areaBasedList", lDongRegnCd=region, lDongSignguCd=district,
                         contentTypeId=ctype, numOfRows=rows, pageNo=page, arrange=arrange)


def from_site_config(site: dict, service_key: str, cache_dir: str | Path, offline: bool = False,
                     refresh: bool = False, max_calls: int = DEFAULT_MAX_CALLS) -> TourAPI:
    t = site.get("tourapi") or {}
    return TourAPI(
        service_key=service_key,
        base_url=t.get("base_url", "https://apis.data.go.kr/B551011/KorService2"),
        op_suffix=t.get("op_suffix", "2"),
        mobile_app=t.get("mobile_app") or DEFAULT_MOBILE_APP,
        cache_dir=cache_dir,
        min_interval=float(t.get("min_interval", 0.3)),
        detail_common_params=t.get("detail_common_params") or {},
        offline=offline,
        refresh=refresh,
        max_calls=max_calls,
    )


def barrier_free_client(site: dict, service_key: str, cache_dir: str | Path, offline: bool = False,
                        refresh: bool = False, max_calls: int = DEFAULT_MAX_CALLS) -> TourAPI:
    """A client for 한국관광공사 무장애 여행 정보 (KorWithService2): the same key and settings as KorService2, its own
    base_url (site.json tourapi.barrier_free_base_url, else BARRIER_FREE_BASE_URL) and cache folder (cache_dir /
    BARRIER_FREE_CACHE). The KorService2 default stays as it is."""
    t = site.get("tourapi") or {}
    return TourAPI(
        service_key=service_key,
        base_url=t.get("barrier_free_base_url") or BARRIER_FREE_BASE_URL,
        op_suffix=t.get("op_suffix", "2"),
        mobile_app=t.get("mobile_app") or DEFAULT_MOBILE_APP,
        cache_dir=Path(cache_dir) / BARRIER_FREE_CACHE,
        min_interval=float(t.get("min_interval", 0.3)),
        offline=offline,
        refresh=refresh,
        max_calls=max_calls,
    )


# ----------------------------------------------------------------------------- region codes (ldongCode2)
def _squash(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _subject(word: str) -> str:
    """The word with its subject particle: '누리군이', '한빛구가'."""
    code = ord(word[-1]) - 0xAC00 if word else -1
    return word + ("이" if 0 <= code < 11172 and code % 28 else "가")


def _direct(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@dataclass(frozen=True)
class LDong:
    """The provider's codes for the configured city, as ldongCode2 answered (never written in code or config)."""
    regn_cd: str
    regn_name: str
    signgu: tuple[tuple[str, str], ...]  # (lDongSignguCd, name) in site.json order: every 구·군, or the 시
    whole_region: bool                   # the city is the whole 시·도: districts configured, locality == region_admin
    locality_cd: str = ""                # optional parent 시 code when a province city also has 구 codes (e.g. 용인시 460)

    def name_of(self, code) -> str:
        return next((n for c, n in self.signgu if c == str(code or "")), "")


def tourapi_conf(city) -> dict:
    """site.json -> tourapi of a pipeline.city.City."""
    t = (city.raw or {}).get("tourapi")
    return t if isinstance(t, dict) else {}


def ldong_regn_name(city) -> str:
    """The 시·도 name looked up in ldongCode2: site.json tourapi.ldong_regn_name, else region_admin."""
    return _squash(tourapi_conf(city).get("ldong_regn_name")) or city.region_admin


def list_scope(city) -> str:
    """site.json tourapi.list_scope: 'districts' (default) or 'region'. TourAPIConfigError for any other value, and
    for 'region' when the city is not the whole 시·도 (an area-wide list would also hold other cities)."""
    scope = _squash(tourapi_conf(city).get("list_scope")) or "districts"
    if scope not in LIST_SCOPES:
        raise TourAPIConfigError(f"site.json tourapi.list_scope 값 오류: {scope!r} (허용: {', '.join(LIST_SCOPES)})")
    if scope == "region" and not (city.districts and city.locality == city.region_admin):
        raise TourAPIConfigError("site.json tourapi.list_scope 'region'은 시·도 전체가 이 도시일 때만 쓴다"
                                 "(districts가 있고 locality == region_admin)")
    return scope


def resolve_ldong(api, city, call=None) -> LDong:
    """The provider's codes for the city, by exact name (codes always come from this answer):
    1. ldongCode2 (no code): the one 시·도 whose name equals ldong_regn_name(city); none or several -> RegionCodeError.
    2. ldongCode2 (that code): with districts, every 구·군 must match exactly one name — a missing one is an error
       that names it ('누리군이 OO광역시 코드 아래에 없음 — docs/rights.md 4절'); without districts, the locality.
    `call(fn, *args, **kwargs)` makes each request (tools/tourapi_bulk.py passes its network retry)."""
    call = call or _direct
    want = ldong_regn_name(city)
    regions = call(api.ldong_code)
    hits = [r for r in regions if _squash(r.get("name")) == want]
    if len(hits) != 1:
        names = ", ".join(_squash(r.get("name")) for r in regions) or "없음"
        raise RegionCodeError(f"ldongCode2 시·도 가운데 이름이 '{want}'인 항목이 {len(hits)}개 — site.json "
                              f"tourapi.ldong_regn_name(없으면 region_admin)을 응답의 이름과 정확히 맞추세요 (응답: {names})")
    regn_cd = str(hits[0].get("code") or "")
    under = [(str(r.get("code") or ""), _squash(r.get("name"))) for r in call(api.ldong_code, regn_cd)]
    found, missing = [], []
    for name in list(city.districts) or [city.locality]:
        alt = f"{city.locality} {name}" if city.districts and city.locality and city.locality != city.region_admin else name
        codes = [c for c, n in under if n == name] or ([c for c, n in under if n == alt] if alt != name else [])
        if len(codes) == 1:
            found.append((codes[0], name))
        else:
            missing.append(name if not codes else f"{name}({len(codes)}개)")
    if missing:
        what = "구·군" if city.districts else "시"
        listed = ", ".join(n for _, n in under) or "없음"
        raise RegionCodeError(f"{_subject('·'.join(missing))} {want} 코드 아래에 없음 — docs/rights.md 4절 "
                              f"(ldongCode2 {want}({regn_cd}) 아래 {what}: {listed})")
    loc_cd = ""
    if city.districts and city.locality and city.locality != city.region_admin:
        loc_codes = [c for c, n in under if n == city.locality]
        if len(loc_codes) == 1:
            loc_cd = loc_codes[0]
    return LDong(regn_cd, want, tuple(found),
                 whole_region=bool(city.districts) and city.locality == city.region_admin,
                 locality_cd=loc_cd)


def fetch_festivals(api, event_start_date: str, ldong: LDong, rows: int = 100, call=None) -> list[dict]:
    """searchFestival2 from event_start_date for the city: one search for the whole 시·도 when the city is the whole
    시·도 (lDongRegnCd only), else one per resolved 시군구. Every page is read, until a short page (or one that adds
    nothing new); items are deduplicated by contentid, the first one kept."""
    call = call or _direct
    out, seen = [], set()
    for signgu in [None] if ldong.whole_region else [c for c, _ in ldong.signgu]:
        page = 1
        while True:
            got = call(api.search_festival, event_start_date, ldong.regn_cd, signgu, rows=rows, page=page)
            new = [it for it in got if str(it.get("contentid")) not in seen]
            seen.update(str(it.get("contentid")) for it in new)
            out += new
            if len(got) < rows or not new:
                break
            page += 1
    return out
