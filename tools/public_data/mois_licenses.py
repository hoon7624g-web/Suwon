"""음식점·숙소·캠핑장의 영업 상태·인허가 전화·식품안심업소(위생등급) — 행정안전부 인허가 조회서비스 12종(사이트 설정의
개방자치단체코드 mois_groups)과 식품의약품안전처 '식품접객업소 식품안심업소(위생등급) 지정 현황'을 사이트 장소에 잇는다
(인천각 tools/mois_licenses_incheon.py를 설정으로 일반화, 2026-11-05). 결과는 out/<slug>/licenses.json 하나다 — 사이트의
places.json은 읽기만 한다.

    DATA_GO_KR_KEY=… python tools/mois_licenses.py --site busan fetch     # 인허가 12종을 out/busan/raw/licenses/에
    python -I tools/mois_licenses.py --site busan hygiene --file <C004.csv(.gz)>  # (파일 자료 — 이번 실행 범위 밖)
    python tools/mois_licenses.py --site busan          # 미리보기(매칭·폐업 확인·전화 차이 건수)
    python tools/mois_licenses.py --site busan --apply  # out/busan/licenses.json 쓰기

출처
- 행정안전부 인허가 조회서비스(https://apis.data.go.kr/1741000/<서비스>/info, 개방자치단체코드 = config public_data.mois_groups).
  100행씩 모든 쪽(numOfRows는 1000을 줘도 100행 — 2026-11-05 다시 확인). 응답은 cache/mois_licenses/<받은 날>/에 쪽마다
  두고(키 없음), 원자료는 raw/licenses/mois_<서비스>.csv(RAW_COLS 가운데 그 서비스에 있는 열, 값 그대로)와 받은 날·건수를 적은
  mois_licenses_fetch.json이다. 키는 환경 변수 DATA_GO_KR_KEY(또는 --key-file)로만 받고 모든 메시지에서 ***로 가린다.
  공급자 오류 메시지는 그대로 보인다. 실행당 호출 상한 --max-calls, 연결 끊김은 5번까지 다시 시도. 서비스별 하루 한도
  (2026-11-05 응답 머리말 X-RateLimit-Limit 10000)를 넘으면 그 서비스만 멈추고 다른 서비스를 계속 받는다.
- 식품의약품안전처 식품안심업소(위생등급) 지정 현황(운영자가 올린 전국 파일). 사이트 행(INSTT_CD_NM이 config
  region.hygiene_prefix로 시작)만 원본 열 그대로(사업자등록번호·대표자명 제외) raw/hygiene/mfds_hygiene_<slug>.csv에 옮긴다.

매칭 규칙(추정하지 않는다 — 인천각 도구와 같다)
- 장소 묶음: 캠핑장(id gocamping-* 또는 이름에 '캠핑')은 야영장업 2종, kind food는 일반·휴게음식점·제과점·관광식당,
  kind stay는 숙박업·관광숙박업·관광펜션업·농어촌민박업·외국인관광도시민박업·한옥체험업 행과만 잇는다.
- 이름은 norm_name(괄호·공백·문장부호·'주식회사' 제거, '횟집'='회집')으로 비교하고, 장소 이름·alternate_names·TourAPI
  제목과 괄호 안 이름(지점·'구.' 옛 이름 제외)을 모두 쓴다.
  1) 이름이 같고 주소 열쇠(도로명+건물번호 또는 동·리+번지)가 같다 → name+address
  2) 이름이 같고 인허가 좌표(CRD_INFO, EPSG:5174 → WGS84)와 장소 좌표가 COORD_M 안 → name+coords
  3) 주소 열쇠가 같고 한 이름이 다른 이름을 품으며(짧은 쪽 2자 이상, 숙박의 '호텔·모텔·여관·무인텔'은 빼고 비교),
     그 주소의 그런 업소가 한 상호 계열뿐 → similar-name+address
  1)·3)에는 같은 주소에서 그 상호로 시작하는 다른 인허가도 함께 넣는다. 같은 이름만 있고 주소·좌표가 다르면, 3)에서
  계열이 둘 이상이면, 같은 주소에 다른 이름만 있으면 매칭하지 않고 unmatched_places에 후보와 함께 남긴다.
  숙소는 같은 주소에서 영업 중이고 전화가 우리 전화와 같은 인허가가 있으면 address+tel로 잇는다(인천 운영자 결정 2026-10-31).
- 상태: 매칭된 행 가운데 영업(SALS_STTS_CD 01)이 하나라도 있으면 '영업', 없고 휴업(02)이 있으면 '휴업', 모두
  폐업·취소·말소이면 '폐업 확인'(closed 목록 — 운영자 보고용, status는 건드리지 않는다).
- 식품안심업소: 지정 현황 행의 이름이 그 장소 이름이나 매칭된 인허가 상호와 같고 주소 열쇠가 같을 때만 붙인다.
- 전화 비교(tel_compare): 장소 facts.infocenter의 번호(숫자만)와 인허가 TELNO — same·different·ours_missing·license_missing.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import io
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, Site, is_quota, log_calls  # noqa: E402

PROVIDER = "행정안전부"
# set by configure(site) from config public_data
REGION = ""          # '부산광역시'
SHORT = ""           # '부산'
GROUPS: dict[str, str] = {}
GROUPS_LABEL = ""    # '부산광역시 16개 구·군'
CITY_RX = r"^$"
HYGIENE_CITY = ""
HYGIENE_FILE = HYGIENE_LOG = ""
BASE = "https://apis.data.go.kr/1741000/{svc}/info"
PORTAL = "https://www.data.go.kr/data/{no}/openapi.do"
LICENSE = "이용허락범위 제한 없음"
# (서비스 경로, 포털 번호, 데이터 이름(포털 제목), 업종 이름, 장소 묶음)
SERVICES = (
    ("general_restaurants", "15154916", "행정안전부_식품_일반음식점 조회서비스", "일반음식점", "food"),
    ("rest_cafes", "15154921", "행정안전부_식품_휴게음식점 조회서비스", "휴게음식점", "food"),
    ("bakeries", "15155252", "행정안전부_식품_제과점영업 조회서비스", "제과점영업", "food"),
    ("tourist_restaurants", "15154897", "행정안전부_식품_관광식당 조회서비스", "관광식당", "food"),
    ("lodgings", "15155124", "행정안전부_문화_숙박업 조회서비스", "숙박업", "stay"),
    ("tourist_accommodations", "15155090", "행정안전부_문화_관광숙박업 조회서비스", "관광숙박업", "stay"),
    ("tourist_pensions", "15155103", "행정안전부_문화_관광펜션업 조회서비스", "관광펜션업", "stay"),
    ("rural_homestays", "15155113", "행정안전부_문화_농어촌민박업 조회서비스", "농어촌민박업", "stay"),
    ("foreigner_city_homestays", "15155139", "행정안전부_문화_외국인관광도시민박업 조회서비스", "외국인관광도시민박업", "stay"),
    ("hanok_experience", "15154808", "행정안전부_문화_한옥체험업 조회서비스", "한옥체험업", "stay"),
    ("general_campgrounds", "15155149", "행정안전부_문화_일반야영장업 조회서비스", "일반야영장업", "camp"),
    ("auto_campgrounds", "15154788", "행정안전부_문화_자동차야영장업 조회서비스", "자동차야영장업", "camp"),
)
SVC = {s[0]: {"svc": s[0], "no": s[1], "dataset": s[2], "kind": s[3], "group": s[4]} for s in SERVICES}
RAW_COLS = ("MNG_NO", "OPN_ATMY_GRP_CD", "BPLC_NM", "BZSTAT_SE_NM", "SNTTN_BZSTAT_NM", "TOUR_LDGBIZ_DTL_NM",
            "SALS_STTS_CD", "SALS_STTS_NM", "DTL_SALS_STTS_CD", "DTL_SALS_STTS_NM", "LCPMT_YMD", "CLSBIZ_YMD",
            "TCBIZ_BGNG_YMD", "TCBIZ_END_YMD", "ROAD_NM_ADDR", "ROAD_NM_ZIP", "LOTNO_ADDR", "TELNO", "HPG",
            "CRD_INFO_X", "CRD_INFO_Y", "GSRM_CNT", "KSRM_CNT", "WSRM_CNT", "DAT_UPDT_SE", "DAT_UPDT_PNT", "LAST_MDFCN_PNT")
FETCH_LOG = "mois_licenses_fetch.json"
OPEN, PAUSED = "01", "02"   # SALS_STTS_CD: 01 영업/정상, 02 휴업, 03 폐업, 04 취소/말소/만료/정지/중지

HYGIENE = {"key": "hygiene", "provider": "식품의약품안전처",
           "dataset": "식품의약품안전처_식품접객업소 식품안심업소(위생등급) 지정 현황",
           "url": "https://www.data.go.kr/data/15060883/openapi.do", "license": LICENSE,
           "note": "2026-03-16부터 '매우 우수·우수·좋음' 3단계가 식품안심업소 '적합'으로 통일됨(포털 설명)"}

COORD_M = 100   # name equal and the licence point this close to the place point → the same place


def configure(site: Site) -> None:
    """The module's region constants from the site's config (public_data.region, mois_groups)."""
    global REGION, SHORT, GROUPS, GROUPS_LABEL, CITY_RX, HYGIENE_CITY, HYGIENE_FILE, HYGIENE_LOG
    reg = site.region
    REGION, SHORT = reg["name"], reg["short"]
    GROUPS = dict(site.pd["mois_groups"])
    GROUPS_LABEL = reg.get("groups_label") or REGION
    sido = "|".join(sorted(map(re.escape, reg["address_prefixes"]), key=len, reverse=True))
    city = "|".join(sorted(map(re.escape, reg.get("city_names") or []), key=len, reverse=True))
    CITY_RX = rf"^(?:(?:{sido})\s*)?" + (rf"(?:(?:{city})\s*)?" if city else "") + r"(?:\S+?(?:구|군)\s+)?"
    HYGIENE_CITY = reg.get("hygiene_prefix") or (SHORT + " ")
    HYGIENE_FILE, HYGIENE_LOG = f"mfds_hygiene_{site.slug}.csv", f"mfds_hygiene_{site.slug}.json"


# ---------------------------------------------------------------- names, addresses, phones, points

def norm_name(s: str | None) -> str:
    """A name for matching: brackets and their contents, '주식회사'·'(주)'·'(유)', spaces and punctuation removed, lower case;
    '횟집' and its common spelling '회집' read alike ('청담횟집' = '청담회집')."""
    s = re.sub(r"\(.*?\)|\[.*?\]|（.*?）", "", s or "").replace("주식회사", "").replace("유한회사", "")
    return re.sub(r"[\s\W_]+", "", s).lower().replace("횟집", "회집")


def name_variants(s: str | None) -> set[str]:
    """norm_name and each bracketed name of 2+ characters ('오에이치엠씨(주)(베스트웨스턴 군산호텔)' → also
    '베스트웨스턴군산호텔', 'Hotel RG(알지)' → also '알지') — never a branch ('(수송점)') or a former name ('(구.고우당)')."""
    out = {norm_name(s)}
    for inner in re.findall(r"[(\[（]([^()\[\]（）]*)[)\]）]", s or ""):
        if re.match(r"\s*(?:구\s*[.:]|구\s|舊|前)", inner):
            continue
        n = norm_name(inner)
        if len(n) >= 2 and n not in ("주", "유", "사") and not n.endswith("점"):
            out.add(n)
    return {n for n in out if n}


def squash(s) -> str:
    return " ".join(str(s or "").split())


def addr_keys(addr: str | None) -> set[tuple[str, str, str]]:
    """The keys of an address in the site's region: ('road', '구암31로', '137') for a road address (읍·면 before the road ignored,
    '백릉안 1길' = '백릉안1길', '구암3.1로' = '구암31로'), ('lot', '중앙로1가', '11-1') for a lot address. Anything in
    brackets or after a comma is dropped; an address without a number gives no key."""
    a = re.sub(CITY_RX, "", squash(addr))
    a = re.split(r"[,(]", a)[0].replace(".", "").replace("번지", "")
    a = re.sub(r"(\S)\s+(\d+(?:번)?길)(?=\s|$)", r"\1\2", a)   # '백릉안 1길' / '부흥로 316번길'
    a = re.sub(r"(\S)\s+(\d+가)(?=\s|$)", r"\1\2", a)          # '중앙로 1가'
    a = re.sub(r"(\S(?:로|길))(\d+(?:-\d+)?)(?=\s|$)", r"\1 \2", a)   # '현충로84' → '현충로 84'
    t = a.split()
    out = set()
    for i, w in enumerate(t[:-1]):
        n = t[i + 1]
        if not re.fullmatch(r"산?\d+(?:-\d+)?", n):
            continue
        if re.search(r"(?:로|길)$", w):
            out.add(("road", w, n))
        elif re.search(r"(?:동|가|리)$", w) and not w.endswith(("읍", "면")):
            out.add(("lot", w, n))
    return out


def row_keys(r: dict) -> set[tuple[str, str, str]]:
    return addr_keys(r.get("ROAD_NM_ADDR")) | addr_keys(r.get("LOTNO_ADDR"))


def phones(s: str | None) -> set[str]:
    """The phone numbers in a text, digits only ('063-451-0055 / 010…' → {'0634510055', '010…'})."""
    out = set()
    for m in re.finditer(r"\d[\d\s\-)(.]{6,}\d", s or ""):
        d = re.sub(r"\D", "", m.group())
        if len(d) >= 8:
            out.add(d)
    return out


def tel_compare(ours: str | None, theirs: str | None) -> str:
    a, b = phones(ours), phones(theirs)
    if not a and not b:
        return "both_missing"
    if not a:
        return "ours_missing"
    if not b:
        return "license_missing"
    return "same" if a & b else "different"


def tm5174_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """(lat, lng) of a point in EPSG:5174 (Korean 1985 / Modified Central Belt, Bessel 1841, the 인허가 CRD_INFO_X·Y):
    inverse transverse Mercator on Bessel, then the 7-parameter shift to WGS84 (towgs84 -115.80,474.99,674.11,
    1.16,-2.31,-1.63,6.43, position vector)."""
    a, f = 6377397.155, 1 / 299.1528128
    e2 = f * (2 - f)
    lat0, lon0, k0, fe, fn = math.radians(38), math.radians(127.0028902777778), 1.0, 200000.0, 500000.0

    def merid(phi):
        e4, e6 = e2 * e2, e2 ** 3
        return a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                    + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi) - (35 * e6 / 3072) * math.sin(6 * phi))
    m = merid(lat0) + (y - fn) / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    ep2 = e2 / (1 - e2)
    c1, t1 = ep2 * math.cos(phi1) ** 2, math.tan(phi1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = (x - fe) / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                              + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(phi1)
    # Bessel geodetic → ECEF → WGS84 ECEF → WGS84 geodetic
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    X, Y, Z = n * math.cos(lat) * math.cos(lon), n * math.cos(lat) * math.sin(lon), n * (1 - e2) * math.sin(lat)
    tx, ty, tz, s = -115.80, 474.99, 674.11, 6.43e-6
    rx, ry, rz = (math.radians(v / 3600) for v in (1.16, -2.31, -1.63))
    X2 = tx + (1 + s) * (X - rz * Y + ry * Z)
    Y2 = ty + (1 + s) * (rz * X + Y - rx * Z)
    Z2 = tz + (1 + s) * (-ry * X + rx * Y + Z)
    a2, f2 = 6378137.0, 1 / 298.257223563
    e22 = f2 * (2 - f2)
    p = math.hypot(X2, Y2)
    lat2 = math.atan2(Z2, p * (1 - e22))
    for _ in range(6):
        n2 = a2 / math.sqrt(1 - e22 * math.sin(lat2) ** 2)
        lat2 = math.atan2(Z2 + e22 * n2 * math.sin(lat2), p)
    return math.degrees(lat2), math.degrees(math.atan2(Y2, X2))


def row_point(r: dict) -> tuple[float, float] | None:
    try:
        x, y = float(r.get("CRD_INFO_X") or ""), float(r.get("CRD_INFO_Y") or "")
    except ValueError:
        return None
    return tm5174_to_wgs84(x, y) if x and y else None


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    k = math.pi / 180
    x = (b[1] - a[1]) * k * math.cos((a[0] + b[0]) / 2 * k)
    return 6371000 * math.hypot(x, (b[0] - a[0]) * k)


# ---------------------------------------------------------------- files

def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], cols: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def raw_dirs(site: Site) -> tuple[Path, Path]:
    return site.raw / "licenses", site.raw / "hygiene"


def mask(text: str, key: str) -> str:
    import urllib.parse
    for k in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}:
        if k:
            text = text.replace(k, "***")
    return text


# ---------------------------------------------------------------- fetch

class CallCap(SystemExit):
    """This run's call cap is used up — the next run continues from the day's cache."""


class Quota(RuntimeError):
    """The service's daily quota is used up — stop this service, continue the others."""


def fetch_pages(svc: str, group: str, key: str, day_cache: Path, budget: dict, max_calls: int, opener) -> tuple[list, int]:
    """(items, totalCount) of every page of one service for one 개방자치단체코드; pages cached per day. RuntimeError with
    the provider's own message (key masked) when a page fails after the retries; Quota on the daily quota."""
    import urllib.error
    import urllib.parse
    out, page, total = [], 1, None
    while total is None or (page - 1) * 100 < total:
        f = day_cache / f"{svc}-{group}-{page}.json"
        if f.is_file():
            body = json.loads(f.read_text("utf-8"))
        else:
            q = urllib.parse.urlencode({"serviceKey": key, "pageNo": page, "numOfRows": 100, "returnType": "json",
                                        "cond[OPN_ATMY_GRP_CD::EQ]": group})
            err = ""
            for i in range(6):
                if budget["calls"] >= max_calls:
                    raise CallCap(f"호출 상한 {max_calls}회 — 캐시({day_cache})로 이어서 다시 실행")
                raw = ""
                retry = True
                try:
                    budget["calls"] += 1
                    with opener(BASE.format(svc=svc) + "?" + q) as r:
                        budget["remaining"] = r.headers.get("X-RateLimit-Remaining") or budget.get("remaining")
                        raw = r.read().decode("utf-8")
                    resp = json.loads(raw)["response"]
                    head = resp.get("header") or {}
                    if str(head.get("resultCode", "0")) not in ("0", "00"):
                        retry = False
                        raise ValueError(f"resultCode {head.get('resultCode')} {head.get('resultMsg')}")
                    body = resp["body"]
                    break
                except Exception as e:   # noqa: BLE001 — the provider's own message, the key masked
                    if isinstance(e, urllib.error.HTTPError):
                        raw = e.read().decode("utf-8", "replace")
                        retry = e.code >= 500
                    err = mask(f"{e} {raw[:400]}", key)
                    if is_quota(err) and "PER_SECOND" not in err.upper():
                        raise Quota(f"{svc}: 하루 한도 — {err}") from None
                    if not retry:
                        break
                    if i < 5:
                        time.sleep(2 + 2 * i)
            else:
                raise RuntimeError(f"{svc} {group}({GROUPS.get(group, '')}) {page}쪽: {err}")
            if err and not retry:
                raise RuntimeError(f"{svc} {group}({GROUPS.get(group, '')}) {page}쪽: {err}")
            f.write_text(json.dumps(body, ensure_ascii=False), "utf-8")
        total = int(body.get("totalCount") or 0)
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        out += items
        page += 1
        if not items:
            break
    return out, total or 0


def fetch(site: Site, key: str, cache: Path, max_calls: int = 3000, services=None, opener=None,
          today: str | None = None, groups=None, day: str | None = None) -> dict:
    """Every page of each service for every config GROUPS code into raw/licenses/mois_<svc>.csv (RAW_COLS the service
    has, values as returned, sorted by MNG_NO) and mois_licenses_fetch.json (받은 날·건수·군·구별 건수·자료 갱신 시점).
    Pages are cached per day (day: the cache day to use — a run that goes past midnight keeps the first day's pages).
    A service the provider refuses (미승인·하루 한도 등) is skipped with its message in the log — the other services go
    on; the call cap stops the run (the cache lets the next run continue)."""
    import urllib.request
    opener = opener or (lambda url: urllib.request.urlopen(url, timeout=60))
    today = today or dt.date.today().isoformat()
    lic_dir, _ = raw_dirs(site)
    day_cache = cache / (day or today)
    day_cache.mkdir(parents=True, exist_ok=True)
    log_path = lic_dir / FETCH_LOG
    log = json.loads(log_path.read_text("utf-8")) if log_path.is_file() else {}
    budget = {"calls": 0}
    errors = {}
    try:
        for svc in services or SVC:
            rows, totals = {}, {}
            try:
                for group in groups or GROUPS:
                    items, totals[group] = fetch_pages(svc, group, key, day_cache, budget, max_calls, opener)
                    for it in items:
                        rows[str(it.get("MNG_NO"))] = it
            except (RuntimeError, Quota) as e:
                errors[svc] = str(e)
                if not (log.get(svc) or {}).get("rows"):
                    log[svc] = {"fetched_at": today, "total": 0, "rows": 0, "data_updated": "", "file": "", "error": str(e)}
                continue
            have = {c for it in rows.values() for c in it}
            cols = [c for c in RAW_COLS if c in have]
            out = [{c: "" if it.get(c) is None else str(it.get(c)) for c in cols} for it in rows.values()]
            out.sort(key=lambda r: r["MNG_NO"])
            path = lic_dir / f"mois_{svc}.csv"
            if out:
                write_csv(path, out, cols)
            elif path.is_file():
                path.unlink()
            updated = max((r.get("DAT_UPDT_PNT") or "")[:10] for r in out) if out else ""
            log[svc] = {"fetched_at": day or today, "total": sum(totals.values()), "rows": len(out), "data_updated": updated,
                        "file": path.name if out else "", "groups": totals}
    finally:
        lic_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", "utf-8")
        log_calls("1741000(" + ",".join(services or SVC) + ")", site.slug, budget["calls"])
    got = {"calls": budget["calls"], "quota_remaining_last": budget.get("remaining"),
           **{s: v["rows"] for s, v in log.items() if s in (services or SVC)}}
    if errors:
        got["errors"] = errors
    return got


# ---------------------------------------------------------------- hygiene

def extract_hygiene(site: Site, src: Path, today: str | None = None) -> dict:
    """The site's rows (INSTT_CD_NM starting HYGIENE_CITY) of the national 식품안심업소 file, every column as published,
    into raw/hygiene/; the file's latest CHNG_DT is its base date. Read as data only (csv), never run."""
    raw = src.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949")
    rows = list(csv.DictReader(io.StringIO(text)))
    need = {"BSSH_NM", "ADDR", "LCNS_NO", "HG_ASGN_LV", "INSTT_CD_NM"}
    if not rows or not need <= set(rows[0]):
        raise SystemExit(f"열이 다릅니다 — 필요한 열: {sorted(need)}")
    keep = [r for r in rows if squash(r.get("INSTT_CD_NM")).startswith(HYGIENE_CITY)]
    if not keep:
        raise SystemExit(f"{SHORT} 행이 없습니다")
    _, hyg_dir = raw_dirs(site)
    cols = [c for c in rows[0] if c not in ("WRKR_REG_NO", "PRSDNT_NM")]
    write_csv(hyg_dir / HYGIENE_FILE, [{c: r.get(c, "") for c in cols} for r in
                                       sorted(keep, key=lambda r: (r.get("LCNS_NO") or "", r.get("HG_ASGN_NO") or ""))],
              cols)
    ymd_ = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"\d{8}", s or "") else ""   # noqa: E731
    log = {"source_file": src.name, "rows_total": len(rows), "rows_site": len(keep),
           "base_date": ymd_(max((r.get("CHNG_DT") or "") for r in rows)),
           "latest_designation": ymd_(max((r.get("HG_ASGN_YMD") or "") for r in rows)),
           "extracted_at": today or dt.date.today().isoformat()}
    (hyg_dir / HYGIENE_LOG).write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return log


def ymd(s: str | None) -> str:
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"\d{8}", s) else s


def hygiene_valid(r: dict, today: str) -> bool:
    return (squash(r.get("CLSBIZ_DVS_CD_NM")) == "정상" and not squash(r.get("ASGN_CANCEL_YMD"))
            and ymd(r.get("ASGN_TO")) >= today)


# ---------------------------------------------------------------- matching

def place_group(p: dict) -> str | None:
    if p["id"].startswith("gocamping-") or "캠핑" in (p.get("name") or ""):
        return "camp"
    return p.get("kind") if p.get("kind") in ("food", "stay") else None


def place_names(p: dict) -> set[str]:
    names = [p.get("name")] + list(p.get("alternate_names") or []) + [(p.get("tourapi") or {}).get("title")]
    return {n for x in names if x for n in name_variants(x)}


def place_point(p: dict) -> tuple[float, float] | None:
    g = p.get("geo") or {}
    try:
        return (float(g["lat"]), float(g["lng"])) if g.get("lat") and g.get("lng") else None
    except (TypeError, ValueError):
        return None


LODGING_WORDS = r"호텔|모텔|여관|무인텔"


def core(n: str) -> str:
    """A normalized name without the lodging words ('프리마호텔' · '프리마모텔' → '프리마'), when 2+ characters are left."""
    c = re.sub(LODGING_WORDS, "", n)
    return c if len(c) >= 2 else n


def related(a: str, b: str) -> bool:
    """One name holds the other (the shorter of 2+ characters), lodging words aside: '째보식당' · '째보식당본점',
    '비타민호텔' · '호텔비타민'."""
    s, t = sorted((core(a), core(b)), key=len)
    return len(s) >= 2 and s in t


def match_place(p: dict, rows: list[dict], by_name: dict[str, list[dict]], our_tel: str = "",
                group: str = "") -> tuple[list[dict], str, list[dict]]:
    """(matched licence rows, basis, candidates when not matched) for one place — see the module rules."""
    names, keys, pt = place_names(p), addr_keys((p.get("facts") or {}).get("address")), place_point(p)
    same = list({id(r): r for n in names for r in by_name.get(n, ())}.values())
    here = [r for r in rows if keys & r["_keys"]]

    def family(got: list[dict]) -> list[dict]:
        # the brand's other licences at the address (the old name closed, '<name> ○○점' licensed the same day)
        brands = {r["_name"] for r in got if len(r["_name"]) >= 3}
        return got + [r for r in here if r not in got and any(r["_name"].startswith(b) for b in brands)]
    if same:
        got = [r for r in same if keys & r["_keys"]]
        if got:
            return family(got), "name+address", []
        if pt:
            got = [r for r in same if r["_pt"] and metres(pt, r["_pt"]) <= COORD_M]
            if got:
                return got, "name+coords", []
    near = [r for r in here if not (r["_names"] & names) and any(related(a, n) for a in r["_names"] for n in names)]
    if near:
        near = family(near)   # one family only
        base = min((core(r["_name"]) for r in near), key=len)
        if all(base in core(r["_name"]) for r in near):
            return near, "similar-name+address", []
        return [], "similar names at the address", near
    # a renamed lodging (운영자 결정 2026-10-31 '이어'): a licence in business at the same address under another name
    # whose phone is our phone — the same house under its new name (the page then names the licensed name)
    if group == "stay" and our_tel:
        renamed = [r for r in here if r.get("SALS_STTS_CD") == OPEN and tel_compare(our_tel, r.get("TELNO")) == "same"]
        if renamed:
            return renamed, "address+tel", []
    if same:
        return [], "same name, other address", same
    return [], ("other names at the address" if here else "no licence row"), here


def representative(rows: list[dict]) -> dict:
    open_ = [r for r in rows if r.get("SALS_STTS_CD") == OPEN]
    if open_:
        return max(open_, key=lambda r: (r.get("LCPMT_YMD") or "", r.get("MNG_NO") or ""))
    paused = [r for r in rows if r.get("SALS_STTS_CD") == PAUSED]
    if paused:
        return max(paused, key=lambda r: (r.get("LCPMT_YMD") or "", r.get("MNG_NO") or ""))
    return max(rows, key=lambda r: (r.get("CLSBIZ_YMD") or "", r.get("LCPMT_YMD") or ""))


def status_of(rows: list[dict]) -> str:
    codes = {r.get("SALS_STTS_CD") for r in rows}
    return "영업" if OPEN in codes else "휴업" if PAUSED in codes else "폐업 확인"


def prep(r: dict, svc: str) -> dict:
    r = dict(r, _svc=svc, _group=SVC[svc]["group"], _name=norm_name(r.get("BPLC_NM")),
             _names=name_variants(r.get("BPLC_NM")))
    r["_keys"], r["_pt"] = row_keys(r), row_point(r)
    return r


def load_rows(lic_dir: Path) -> list[dict]:
    out = []
    for svc in SVC:
        f = lic_dir / f"mois_{svc}.csv"
        if f.is_file():
            out += [prep(r, svc) for r in read_csv(f)]
    return out


def unit(addr: str | None) -> str:
    """The 호 of an address ('철새로 31, 1층 107호' → '107호'), or ''."""
    m = re.search(r"(\d+)\s*호", addr or "")
    return m.group(1) + "호" if m else ""


def brief(r: dict, our_tel: str | None = None) -> dict:
    """A licence row as a candidate for the operator (values as published)."""
    out = {"name": r["BPLC_NM"], "kind": SVC[r["_svc"]]["kind"], "status": r.get("SALS_STTS_NM", ""),
           "licensed_at": r.get("LCPMT_YMD", ""), "closed_at": r.get("CLSBIZ_YMD", ""), "tel": squash(r.get("TELNO")),
           "road_addr": squash(r.get("ROAD_NM_ADDR") or r.get("LOTNO_ADDR")), "mng_no": r["MNG_NO"]}
    if our_tel is not None:
        out["same_tel"] = tel_compare(our_tel, r.get("TELNO")) == "same"
    return out


def match_hygiene(p: dict, rows: list[dict], hyg: list[dict], today: str) -> dict | None:
    names = place_names(p) | {n for r in rows for n in r["_names"]}
    keys = addr_keys((p.get("facts") or {}).get("address")) | {k for r in rows for k in r["_keys"]}
    got = [h for h in hyg if name_variants(h.get("BSSH_NM")) & names and addr_keys(h.get("ADDR")) & keys
           and hygiene_valid(h, today)]
    if not got:
        return None
    h = max(got, key=lambda h: (h.get("ASGN_FROM") or "", h.get("HG_ASGN_NO") or ""))
    return {"level": squash(h.get("HG_ASGN_LV")), "valid_from": ymd(h.get("ASGN_FROM")), "valid_to": ymd(h.get("ASGN_TO")),
            "no": squash(h.get("HG_ASGN_NO")), "designated_by": squash(h.get("HG_ASGN_NM")),
            "kind": squash(h.get("INDUTY_NM")), "name": squash(h.get("BSSH_NM"))}


def build(places: list[dict], rows: list[dict], hyg: list[dict], fetch_log: dict, hyg_log: dict | None,
          today: str) -> dict:
    by_group: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_group[r["_group"]].append(r)
    names = {g: collections.defaultdict(list) for g in by_group}
    for g, rs in by_group.items():
        for r in rs:
            for n in r["_names"]:
                names[g][n].append(r)
    out, unmatched, closed = {}, [], []
    for p in places:
        g = place_group(p)
        if not g:
            continue
        our_tel = (p.get("facts") or {}).get("infocenter") or ""
        got, basis, cands = match_place(p, by_group.get(g, []), names.get(g, {}), our_tel, g)
        pub = p.get("status") == "published"
        if not got:
            cands = sorted(cands, key=lambda r: (r.get("SALS_STTS_CD") != OPEN, r.get("LCPMT_YMD") or ""))
            unmatched.append({"id": p["id"], "name": p["name"], "group": g, "published": pub, "reason": basis,
                              "address": (p.get("facts") or {}).get("address") or "",
                              "candidates": [brief(r, our_tel) for r in cands[:6]]})
            continue
        rep, st = representative(got), status_of(got)
        s = SVC[rep["_svc"]]
        detail = squash(rep.get("TOUR_LDGBIZ_DTL_NM") or rep.get("BZSTAT_SE_NM"))
        item = {"status": st, "kind": s["kind"], "kind_detail": detail if detail and detail != s["kind"] else "",
                "name": rep["BPLC_NM"], "licensed_at": rep.get("LCPMT_YMD") or "",
                "closed_at": (rep.get("CLSBIZ_YMD") or None) if st == "폐업 확인" else None,
                "tel": squash(rep.get("TELNO")), "road_addr": squash(rep.get("ROAD_NM_ADDR")),
                "lot_addr": squash(rep.get("LOTNO_ADDR")), "source": rep["_svc"], "mng_no": rep["MNG_NO"],
                "match": basis, "rows": len(got), "tel_compare": tel_compare(our_tel, rep.get("TELNO"))}
        if g == "food":
            h = match_hygiene(p, got, hyg, today)
            if h:
                item["hygiene"] = h
        out[p["id"]] = item
        if st == "폐업 확인":
            keys, u = {k for r in got for k in r["_keys"]}, unit(rep.get("ROAD_NM_ADDR"))
            now = [r for r in by_group.get(g, []) if r.get("SALS_STTS_CD") == OPEN and keys & r["_keys"]
                   and (not u or unit(r.get("ROAD_NM_ADDR")) == u)]
            closed.append({"id": p["id"], "name": p["name"], "published": pub, "license_name": rep["BPLC_NM"],
                           "kind": s["kind"], "closed_at": rep.get("CLSBIZ_YMD") or "", "mng_no": rep["MNG_NO"],
                           "open_at_same_address": [brief(r, our_tel) for r in now[:5]]})
    sources = {}
    for svc, s in SVC.items():
        lg = fetch_log.get(svc) or {}
        sources[svc] = {"provider": PROVIDER, "dataset": s["dataset"], "kind": s["kind"],
                        "url": PORTAL.format(no=s["no"]), "api": BASE.format(svc=svc), "region_code": ",".join(GROUPS),
                        "base_date": lg.get("data_updated") or "", "checked_at": lg.get("fetched_at") or "",
                        "rows": lg.get("rows", 0), "license": LICENSE}
        if lg.get("error"):
            sources[svc]["error"] = lg["error"]
    if hyg_log:
        sources["hygiene"] = {**{k: v for k, v in HYGIENE.items() if k != "key"}, "base_date": hyg_log.get("base_date", ""),
                              "checked_at": hyg_log.get("extracted_at", ""), "rows": hyg_log.get("rows_site", 0)}
    checked = max((v["checked_at"] for v in sources.values() if v.get("checked_at")), default=today)
    return {
        "_about": (f"{SHORT} 음식점·숙소·캠핑장의 인허가상 영업 상태·상호·인허가일·폐업일·전화와 식품안심업소(위생등급) 지정. "
                   f"행정안전부 인허가 조회서비스({GROUPS_LABEL} {', '.join(GROUPS)}) 12종과 식품의약품안전처 "
                   "식품안심업소(위생등급) 지정 현황(운영자가 올린 전국 파일이 있을 때만)에서 "
                   "값 그대로 가져와 이름+주소(또는 좌표)가 맞는 장소에만 붙였다. places의 키는 places.json의 id. "
                   "status '폐업 확인'은 매칭된 인허가 행이 모두 폐업·말소인 곳(운영자 보고용 — 공개 여부는 바꾸지 않음). "
                   "tools/mois_licenses.py(공공데이터 모음 도구)로 만든다."),
        "source": {"provider": "행정안전부 · 식품의약품안전처",
                   "dataset": f"행정안전부 인허가 조회서비스 12종({GROUPS_LABEL}) · 식품접객업소 식품안심업소(위생등급) 지정 현황",
                   "url": "https://www.data.go.kr/data/15154916/openapi.do",
                   "base_date": max((v["base_date"] for v in sources.values() if v.get("base_date")), default=""),
                   "checked_at": checked},
        "sources": sources,
        "places": dict(sorted(out.items())),
        "unmatched_places": sorted(unmatched, key=lambda u: (not u["published"], u["group"], u["name"])),
        "closed": sorted(closed, key=lambda c: (not c["published"], c["closed_at"], c["name"])),
    }


def summary(places: list[dict], result: dict) -> dict:
    pub = {p["id"]: place_group(p) for p in places if p.get("status") == "published" and place_group(p)}
    s = {}
    for g in ("food", "stay", "camp"):
        ids = [i for i, gg in pub.items() if gg == g]
        m = [i for i in ids if i in result["places"]]
        s[g] = f"{len(m)}/{len(ids)}"
    allg = {p["id"]: place_group(p) for p in places if place_group(p)}
    s["all_matched"] = f"{len(result['places'])}/{len(allg)}"
    got = [v for k, v in result["places"].items() if k in pub]
    s["status"] = dict(collections.Counter(v["status"] for v in got))
    s["tel_compare"] = dict(collections.Counter(v["tel_compare"] for v in got))
    s["hygiene"] = sum(1 for v in got if v.get("hygiene"))
    s["match"] = dict(collections.Counter(v["match"] for v in got))
    s["closed_published"] = [(c["name"], c["closed_at"]) for c in result["closed"] if c["published"]]
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True, help="config/<slug>.json의 slug")
    ap.add_argument("--apply", action="store_true", help="out/<slug>/licenses.json 쓰기(없으면 미리보기)")
    sub = ap.add_subparsers(dest="cmd")
    fe = sub.add_parser("fetch", help="인허가 조회서비스 12종(config mois_groups)을 받아 raw/licenses/에 옮긴다")
    fe.add_argument("--key-file", type=Path, help="키가 든 파일(없으면 환경 변수 DATA_GO_KR_KEY)")
    fe.add_argument("--max-calls", type=int, default=3000)
    fe.add_argument("--cache", type=Path, default=CACHE_DIR / "mois_licenses")
    fe.add_argument("--only", nargs="*", choices=list(SVC), help="이 서비스만")
    fe.add_argument("--groups", nargs="*", help="이 개방자치단체코드만(나눠 받기 — 마지막에 전부로 한 번 더)")
    fe.add_argument("--day", help="캐시 날짜 폴더(YYYY-MM-DD, 기본 오늘) — 자정을 넘긴 이어받기에 같은 날 캐시를 쓴다")
    hy = sub.add_parser("hygiene", help="식품안심업소(위생등급) 전국 파일에서 사이트 행만 옮긴다")
    hy.add_argument("--file", type=Path, required=True)
    a = ap.parse_args(argv)
    site = Site(a.site)
    configure(site)
    if a.cmd == "fetch":
        import os
        import urllib.parse
        key = a.key_file.read_text("utf-8").strip() if a.key_file else (os.environ.get("DATA_GO_KR_KEY") or "").strip()
        if "%" in key:
            key = urllib.parse.unquote(key)
        if not key:
            raise SystemExit("키가 없습니다 — DATA_GO_KR_KEY 환경 변수나 --key-file")
        print(json.dumps(fetch(site, key, a.cache, a.max_calls, a.only, groups=a.groups, day=a.day), ensure_ascii=False))
        return 0
    if a.cmd == "hygiene":
        print(json.dumps(extract_hygiene(site, a.file), ensure_ascii=False))
        return 0
    lic_dir, hyg_dir = raw_dirs(site)
    places = site.places()
    log_path, hlog_path = lic_dir / FETCH_LOG, hyg_dir / HYGIENE_LOG
    if not log_path.is_file():
        raise SystemExit("인허가 원자료가 없습니다 — 먼저 fetch")
    fetch_log = json.loads(log_path.read_text("utf-8"))
    hyg = read_csv(hyg_dir / HYGIENE_FILE) if (hyg_dir / HYGIENE_FILE).is_file() else []
    hyg_log = json.loads(hlog_path.read_text("utf-8")) if hlog_path.is_file() else None
    today = max((v.get("fetched_at", "") for v in fetch_log.values()), default="") or dt.date.today().isoformat()
    result = build(places, load_rows(lic_dir), hyg, fetch_log, hyg_log, today)
    print(json.dumps(summary(places, result), ensure_ascii=False, indent=1))
    if a.apply:
        site.out.mkdir(parents=True, exist_ok=True)
        (site.out / "licenses.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"썼습니다: {site.out / 'licenses.json'} (장소 {len(result['places'])}곳)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
