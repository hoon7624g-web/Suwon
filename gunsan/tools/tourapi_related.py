"""연관 관광지·관광지 집중률 — 한국관광공사 '관광지별 연관 관광지 정보'(TarRlteTarService1)와 '관광지 집중률 방문자 추이
예측 정보'(TatsCnctrRateService)에서 군산(areaCd 52, signguCd 52130) 값을 받아 이 사이트 장소 id로 묶는다(운영자 결정
2026-10-31 '데이터 다 추출해서 사이트에 반영').

    DATA_GO_KR_KEY=… python tools/tourapi_related.py --data data/gunsan                # 미리보기(둘 다)
    DATA_GO_KR_KEY=… python tools/tourapi_related.py --data data/gunsan related        # 연관 관광지만
    DATA_GO_KR_KEY=… python tools/tourapi_related.py --data data/gunsan crowd --apply  # 집중률만, 파일 쓰기
        --apply: data/raw/gunsan/tourapi_related/related_<기준연월>.csv · tourapi_crowd/crowd_<조회일>.csv(응답 값 그대로)
                 → data/gunsan/related.json · crowd.json
        --base-ym 202609: 연관 관광지 기준연월(없으면 이번 달부터 거꾸로 값이 있는 가장 최근 달)
        --fresh: 캐시를 쓰지 않고 새로 받는다 · --max-calls: 실행당 호출 상한(기본 40)

규칙
- 키는 환경 변수 DATA_GO_KR_KEY(없으면 TOURAPI_KEY)로만 받고, 오류·로그에서 키 문자열만 가린다(공급자 메시지는 그대로).
  응답은 data/cache/<서비스>/에 둔다(.gitignore). 연결이 끊기면 세 번까지 다시 부른다.
- 값은 서비스가 준 그대로 둔다(순위·집중률 숫자, 관광지 이름, 분류). 등급(여유·붐빔 같은 말)은 만들지 않는다.
- 장소 잇기(이름만 주는 서비스라 주소·좌표가 없다): 서비스 이름과 장소 이름·다른 이름(alternate_names)·TourAPI 제목·
  카카오맵 장소 이름(map_id_sources의 matched_name 가운데 도로명 건물번호가 맞은 것 — '이성당 본점')을
  정규화(공백·문장부호 제거, 괄호는 뺀 것과 둔 것 둘 다, 앞의 '군산 '·'군산시 ' 뺀 것)해서 같을 때만 잇는다.
  · 연관 관광지는 군산시(rlteSignguNm)에 있는 곳만 잇고, 분류가 장소 종류와 맞아야 한다(관광지 → attraction, 음식 → food,
    숙박 → stay; 숙박 > 캠핑은 attraction도).
  · 티맵 이름의 '/' 뒤(지점 표시)는 '군산·군산시·군산점'이면 무시하고, 그 밖('나운점', '몽돌해변')은 그 말이 장소 이름이나
    도로명 주소(동·길 이름)에 있을 때만 앞부분으로 잇는다 — '이성당/본점'처럼 확인할 수 없으면 잇지 않는다. '[중식]' 같은
    업종 꼬리표는 뺀다.
  · 중복 장소(duplicate_of)는 원래 장소로, 한 건물 안의 장소(part_of)와 그 건물이 함께 맞으면 건물로 모은다. 그래도 두 곳
    이상이면 애매하므로 잇지 않는다. CONFIRMED는 사람이 확인한 이름 → 장소 id(같은 곳의 다른 이름만).
- 연관 관광지(티맵 모빌리티 내비게이션 데이터, 중심관광지마다 상위 50위까지): 중심관광지가 장소와 이어지면
  places[장소 id]에 순위 순으로, 연관관광지가 장소와 이어지면 place_id를 단다. 못 이은 중심관광지는 unmatched_centers.
- 집중률(㈜케이티 이동통신 데이터, 조회일부터 30일 예측): 가장 붐비는 시기를 100으로 본 상대 수치(단위 없음, % 아님).
  장소마다 날짜 → 값. 매일 바뀌므로 조회일이 다르면 새로 받는다(캐시 폴더가 날짜별).
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
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
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tourapi import (TourAPIError, TourAPIStopError, normalize_key, parse_items,  # noqa: E402
                              redact)

GW = "https://apis.data.go.kr/B551011"
PROVIDER = "한국관광공사"
AREA = {"areaCd": "52", "signguCd": "52130"}     # 전북특별자치도 군산시 (서비스의 지역 코드)
CITY = "군산시"
RELATED = {"service": "TarRlteTarService1", "op": "areaBasedList1",
           "dataset": "한국관광공사_관광지별 연관 관광지 정보", "url": "https://www.data.go.kr/data/15128560/openapi.do",
           "basis": "티맵 모빌리티(주) 내비게이션 데이터(차량 이동 기준)"}
CROWD = {"service": "TatsCnctrRateService", "op": "tatsCnctrRatedList",
         "dataset": "한국관광공사_관광지 집중률 방문자 추이 예측 정보", "url": "https://www.data.go.kr/data/15128555/openapi.do",
         "basis": "㈜케이티 이동통신 데이터 기반 머신러닝 예측"}
ROWS = 1000
# 사람이 확인한 서비스 이름 → 장소 id (이름 규칙으로 잇지 못한 곳을 사람이 확인했을 때만 적는다)
CONFIRMED: dict[str, str] = {   # 2026-10-31 확인: 같은 곳의 다른 이름(위치·시설 종류가 같음)
    "임피역/폐역": "gunsan-305951",              # 군산 임피역사 (폐역된 임피역)
    "군산CC": "gunsan-305411",                   # 군산컨트리클럽
    "군산시 신흥동 말랭이마을": "gunsan-1171773",  # 말랭이마을 (신흥동)
    "선유도유람선": "tourapi-2743288",            # 군산선유도유람선
    "옥돌해수욕장": "tourapi-2748431",            # 옥돌해변
}

TAG_RX = re.compile(r"\[[^\]]*\]")          # 티맵 업종 꼬리표 '[중식]'
LEAD_RX = re.compile(r"^\s*군산시?\s+")      # '군산시 경암동 철길마을' → '경암동 철길마을'
REGION_SUFFIX = {"군산", "군산시", "군산점"}
BRANCH_END_RX = re.compile(r"(?:직영점|dt점|점)$")
ADDRESS_AGREED = "도로명 건물번호 일치"   # map_id_sources basis: the map name was checked against the road address
KINDS = {"관광지": {"attraction"}, "음식": {"food"}, "숙박": {"stay"}}


# ---- client ------------------------------------------------------------------------------------------------------
class ApiError(TourAPIError):
    pass


def _urlopen(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "WebforAI data"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


class Client:
    """One 한국관광공사 data.go.kr service (apis.data.go.kr/B551011/<service>): MobileOS=ETC, MobileApp=WebforAI,
    _type=json; gzip cache per call under cache_dir; at most max_calls live requests per run (retries count); a reset
    connection is tried again up to `tries` times; the key is masked in every message."""

    def __init__(self, key: str, service: str, cache_dir: str | Path, max_calls: int = 40, refresh: bool = False,
                 fetch: Callable[[str], str] | None = None, min_interval: float = 0.3, tries: int = 3,
                 wait: float = 2.0):
        self.key = normalize_key(key)
        self.service = service
        self.base = f"{GW}/{service}"
        self.cache_dir = Path(cache_dir)
        self.max_calls, self.refresh, self.tries, self.wait = max_calls, refresh, tries, wait
        self.fetch = fetch or _urlopen
        self.min_interval = min_interval
        self.calls = 0
        self.cache_hits = 0
        self.fetched: list[str] = []      # ISO date each answered call's data was fetched (cache file date if cached)
        self._last = 0.0

    def mask(self, text) -> str:
        return redact(str(text), self.key)

    def _cache_path(self, op: str, params: dict) -> Path:
        h = hashlib.sha1(json.dumps([self.base, op, sorted(params.items())], ensure_ascii=False).encode()).hexdigest()
        return self.cache_dir / f"{op}-{h[:16]}.json.gz"

    def _get(self, op: str, params: dict) -> str:
        query = urllib.parse.urlencode({"serviceKey": self.key, "MobileOS": "ETC", "MobileApp": "WebforAI",
                                        "_type": "json", **params})
        for attempt in range(1, self.tries + 1):
            if self.calls >= self.max_calls:
                raise TourAPIStopError(f"이번 실행의 호출 상한 {self.max_calls}회에 도달 — 다음 실행에서 캐시로 이어 갑니다")
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self.calls += 1
            try:
                return self.fetch(f"{self.base}/{op}?{query}")
            except urllib.error.HTTPError as err:
                try:
                    body = err.read().decode("utf-8", "replace")
                except (OSError, AttributeError):
                    body = ""
                raise ApiError(self.mask(f"{op}: HTTP {err.code} {body[:300]}")) from None
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                if attempt == self.tries:
                    raise ApiError(self.mask(f"{op}: 네트워크 오류 {type(err).__name__}: {err}")) from None
                print(self.mask(f"  {op}: {type(err).__name__} — 다시 부름({attempt}/{self.tries - 1})"), file=sys.stderr)
                time.sleep(self.wait * attempt)
            finally:
                self._last = time.monotonic()
        raise ApiError(f"{op}: 응답 없음")   # unreachable

    @staticmethod
    def read(payload, op: str) -> tuple[list[dict], int]:
        """(items, totalCount) of a payload; the provider's own error (also the gateway's short form
        {"resultCode", "resultMsg"}) raised as it is."""
        if isinstance(payload, dict) and "response" not in payload and "resultCode" in payload:
            raise ApiError(f"{op}: resultCode={payload.get('resultCode')} {payload.get('resultMsg') or ''}".strip())
        items = parse_items(payload, op)
        body = (payload.get("response") or {}).get("body") or {}
        try:
            total = int(body.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = len(items)
        return items, total

    def page(self, op: str, fresh: bool = False, **params) -> tuple[list[dict], int]:
        params = {k: str(v) for k, v in params.items() if v not in (None, "")}
        path = self._cache_path(op, params)
        if path.exists() and not (self.refresh or fresh):
            self.cache_hits += 1
            self.fetched.append(dt.date.fromtimestamp(path.stat().st_mtime).isoformat())
            return self.read(json.loads(gzip.decompress(path.read_bytes()).decode("utf-8")), op)
        if not self.key:
            raise ApiError("키가 없습니다 — 환경 변수 DATA_GO_KR_KEY(또는 TOURAPI_KEY)")
        body = self._get(op, params)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise ApiError(self.mask(f"{op}: JSON이 아닌 응답: {body[:300]}")) from None
        try:
            out = self.read(payload, op)
        except TourAPIError as err:
            raise type(err)(self.mask(err)) from None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
        self.fetched.append(dt.date.today().isoformat())
        return out

    def all(self, op: str, rows: int = ROWS, fresh: bool = False, **params) -> list[dict]:
        """Every item of a listing, page by page (totalCount)."""
        out, page = [], 1
        while True:
            items, total = self.page(op, fresh=fresh, numOfRows=rows, pageNo=page, **params)
            out += items
            if not items or len(out) >= total:
                return out
            page += 1

    def checked_at(self) -> str:
        return max(self.fetched) if self.fetched else dt.date.today().isoformat()


def key_from_env() -> str:
    return os.environ.get("DATA_GO_KR_KEY") or os.environ.get("TOURAPI_KEY") or ""


# ---- matching ----------------------------------------------------------------------------------------------------
def squash(s) -> str:
    return " ".join(str(s or "").split())


def norm(s: str, keep_brackets: bool = False) -> str:
    """A name for matching: spaces and punctuation removed, lower case; brackets and what is in them dropped, or
    (keep_brackets) only the bracket marks dropped."""
    s = s or ""
    s = re.sub(r"[()\[\]]", " ", s) if keep_brackets else re.sub(r"\(.*?\)|\[.*?\]", "", s)
    return re.sub(r"[\s\W_]+", "", s).lower()


def keys(name: str) -> set[str]:
    """Every normalized form of one name: brackets dropped / kept, with and without a leading '군산 '/'군산시 '."""
    out = set()
    for s in (name or "", LEAD_RX.sub("", name or "")):
        out |= {norm(s), norm(s, keep_brackets=True)}
    out.discard("")
    return out


def split_name(name: str) -> tuple[str, str]:
    """('고래면옥', '나운점') of a 티맵 name '고래면옥/나운점' (the '[중식]' tag dropped); (name, '') without '/'."""
    s = TAG_RX.sub(" ", name or "")
    base, _, rest = s.partition("/")
    return squash(base), squash(rest.replace("/", " "))


def branch_word(branch: str) -> str:
    """'군산미장점' → '미장', '나운점' → '나운', '몽돌해변' → '몽돌해변' ('' when shorter than two letters: '본점')."""
    w = norm(branch)
    w = BRANCH_END_RX.sub("", re.sub(r"^군산시?", "", w))
    return w if len(w) >= 2 else ""


class Places:
    """The site's places for matching service names: name, alternate_names, the TourAPI title and the 카카오맵 name
    whose road address and building number agreed (map_id_sources), under the id of the place itself (duplicate_of →
    the original; places marked exclude are left out)."""

    def __init__(self, places: list[dict]):
        self.index: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
        self.kind, self.category, self.parent = {}, {}, {}
        self.names: dict[str, set[str]] = collections.defaultdict(set)
        self.roads: dict[str, set[str]] = collections.defaultdict(set)
        for p in places:
            if p.get("exclude"):
                continue
            pid = p.get("duplicate_of") or p["id"]
            if not p.get("duplicate_of"):
                self.kind[pid], self.category[pid] = p.get("kind"), p.get("category") or ""
                if isinstance(p.get("part_of"), dict) and p["part_of"].get("id"):
                    self.parent[pid] = p["part_of"]["id"]
                addr = (p.get("facts") or {}).get("address") or ""
                self.roads[pid] |= {norm(t) for t in re.split(r"[\s(),]+", addr) if norm(t)}
            fields = [("name", p.get("name")), *(("alternate_name", a) for a in p.get("alternate_names") or []),
                      ("tourapi_title", (p.get("tourapi") or {}).get("title"))]
            fields += [("kakao_name", s["matched_name"]) for s in (p.get("map_id_sources") or {}).values()
                       if isinstance(s, dict) and s.get("matched_name") and ADDRESS_AGREED in str(s.get("basis"))]
            for field, n in fields:
                for k in keys(n or ""):
                    self.index[k].add((pid, field))
                    self.names[pid].add(k)

    def _find(self, ks: set[str]) -> dict[str, set[str]]:
        found: dict[str, set[str]] = collections.defaultdict(set)
        for k in ks:
            for pid, field in self.index.get(k, ()):
                found[pid].add(field)
        return found

    def _pick(self, found: dict[str, set[str]], kinds: set[str] | None) -> dict[str, set[str]]:
        """Candidates of the wanted kinds; a part (part_of) is dropped when its building is a candidate too."""
        if kinds:
            found = {pid: f for pid, f in found.items() if self.kind.get(pid) in kinds}
        return {pid: f for pid, f in found.items() if self.parent.get(pid) not in found}

    def _has(self, pid: str, word: str) -> bool:
        return bool(word) and (any(word in n for n in self.names[pid])
                               or any(r.startswith(word) for r in self.roads[pid]))

    def match(self, name: str, kinds: set[str] | None = None) -> tuple[str | None, str, list[str]]:
        """(place id or None, basis, candidates) of one service name. basis: the matched fields of the place
        ('name', 'alternate_name', 'tourapi_title', 'kakao_name'; '+branch' when the part after '/' was checked),
        'confirmed', or why there is no match ('none', 'ambiguous')."""
        if CONFIRMED.get(name) in self.names:   # a confirmed name, when that place is in the data at hand
            return CONFIRMED[name], "confirmed", [CONFIRMED[name]]
        base, branch = split_name(name)
        found = self._pick(self._find(keys(f"{base} {branch}".strip())), kinds)
        extra = ""
        if not found and branch:
            if norm(branch) in {norm(w) for w in REGION_SUFFIX}:
                found = self._pick(self._find(keys(base)), kinds)
            else:
                word = branch_word(branch)
                found = self._pick({pid: f for pid, f in self._find(keys(base)).items() if self._has(pid, word)},
                                   kinds)
                extra = "+branch"
        if len(found) == 1:
            pid, fields = next(iter(found.items()))
            return pid, "+".join(sorted(fields)) + extra, [pid]
        return None, ("ambiguous" if found else "none"), sorted(found)


def kinds_of(large: str, small: str = "") -> set[str] | None:
    """Our place kinds that a 티맵 category may be: 관광지 → attraction, 음식 → food, 숙박 → stay (숙박 > 캠핑 also
    attraction — the site files campsites under 레포츠)."""
    k = set(KINDS.get(large or "", set()))
    if large == "숙박" and "캠핑" in (small or ""):
        k.add("attraction")
    return k or None


# ---- related -----------------------------------------------------------------------------------------------------
def latest_base_ym(client: Client, today: dt.date, months: int = 12) -> str:
    """The most recent baseYm (YYYYMM) the service has for 군산, from this month back."""
    y, m = today.year, today.month
    for _ in range(months):
        ym = f"{y}{m:02d}"
        _, total = client.page(RELATED["op"], fresh=True, baseYm=ym, numOfRows=1, pageNo=1, **AREA)
        if total:
            return ym
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    raise ApiError(f"{RELATED['op']}: 최근 {months}개월에 군산 값이 없습니다")


def build_related(items: list[dict], places: Places, base_ym: str, checked: str) -> tuple[dict, dict]:
    """(related.json, report) from the service's rows for 군산."""
    centers: dict[str, list[dict]] = collections.defaultdict(list)
    for it in items:
        centers[squash(it.get("tAtsNm"))].append(it)
    out_places, center_of, unmatched = {}, {}, []
    rel_cache: dict[tuple, str | None] = {}
    report = {"rows": len(items), "centers": len(centers), "related_names": set(), "related_matched": set(),
              "related_unmatched": set(), "related_ambiguous": {}}
    claimed: dict[str, list[str]] = collections.defaultdict(list)
    for cname, rows in centers.items():
        city = {squash(r.get("signguNm")) for r in rows}
        pid, basis, cands = places.match(cname) if city == {CITY} else (None, "none", [])
        if pid:
            claimed[pid].append(cname)
            center_of[cname] = (pid, basis)
        else:
            unmatched.append({"name": cname, "reason": f"애매함: {', '.join(cands)}" if cands else "이름이 같은 장소 없음",
                              "rows": len(rows)})
    for pid, names in claimed.items():
        if len(names) > 1:   # two centres on one place: neither is used
            for n in names:
                center_of.pop(n)
                unmatched.append({"name": n, "reason": f"다른 중심관광지와 같은 장소({pid})", "rows": len(centers[n])})
    for cname, (pid, basis) in sorted(center_of.items(), key=lambda kv: kv[1][0]):
        entries = []
        for r in sorted(centers[cname], key=lambda r: int(r.get("rlteRank") or 0)):
            rname = squash(r.get("rlteTatsNm"))
            large, mid, small = (squash(r.get(f"rlteCtgry{x}clsNm")) for x in ("L", "M", "S"))
            in_city = squash(r.get("rlteSignguNm")) == CITY
            ck = (rname, large, small, in_city)
            if ck not in rel_cache:
                rid, rbasis, rc = places.match(rname, kinds_of(large, small)) if in_city else (None, "none", [])
                rel_cache[ck] = rid
                if in_city:
                    report["related_names"].add(rname)
                    if rid:
                        report["related_matched"].add(rname)
                    elif rbasis == "ambiguous":
                        report["related_ambiguous"][rname] = rc
                    else:
                        report["related_unmatched"].add(rname)
            entries.append({"rank": int(r.get("rlteRank") or 0), "name": rname, "place_id": rel_cache[ck],
                            "category": large, "subcategory": " > ".join(x for x in (mid, small) if x),
                            "region": squash(f"{r.get('rlteRegnNm') or ''} {r.get('rlteSignguNm') or ''}")})
        out_places[pid] = entries
    ym = f"{base_ym[:4]}-{base_ym[4:]}"
    data = {
        "_about": (f"관광지별 연관 관광지 — 한국관광공사 '관광지별 연관 관광지 정보'(TarRlteTarService1 areaBasedList1, 군산시 "
                   f"areaCd 52·signguCd 52130, 기준연월 {ym})를 이 사이트 장소 id로 묶었다(tools/tourapi_related.py, "
                   f"{checked} 받음). 티맵 모빌리티 내비게이션 데이터로, 중심관광지를 목적지로 조회한 뒤 이어서 간 곳의 순위다"
                   "(차량 이동 기준·100m·1분 이상 이동, 실제 방문자 수와 다를 수 있음). places는 중심관광지가 이 사이트 장소와 "
                   "이어진 것(centers에 서비스 이름)이고, 값은 순위(rank 1이 가장 많이 이어 간 곳, 최대 50위)·서비스상 이름·분류·"
                   "지역 그대로다. place_id는 연관관광지가 이 사이트 장소와 이어질 때만(군산시·분류가 장소 종류와 맞고 이름이 "
                   "같을 때 — 서비스에 주소·좌표가 없어 이름으로만 잇고, 애매하면 잇지 않는다). 추천이 아니라 이동 데이터다."),
        "source": {"provider": PROVIDER, "dataset": RELATED["dataset"], "url": RELATED["url"],
                   "api": f"{GW}/{RELATED['service']}/{RELATED['op']}", "basis": RELATED["basis"],
                   "base_date": ym, "checked_at": checked},
        "base_ym": base_ym,
        "centers": {pid: {"name": c, "match": b} for c, (pid, b) in sorted(center_of.items(), key=lambda kv: kv[1][0])},
        "places": dict(sorted(out_places.items())),
        "unmatched_centers": sorted(unmatched, key=lambda u: u["name"]),
    }
    return data, report


def related_csv_rows(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda r: (squash(r.get("tAtsNm")), int(r.get("rlteRank") or 0)))


# ---- crowd -------------------------------------------------------------------------------------------------------
def number(v):
    """The service's number as it is: '85.78' → 85.78, '100' → 100 (None when it is not a number)."""
    s = str(v if v is not None else "").strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    try:
        return float(s)
    except ValueError:
        return None


def iso(ymd: str) -> str:
    s = re.sub(r"\D", "", str(ymd or ""))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else ""


def build_crowd(items: list[dict], places: Places, checked: str) -> tuple[dict, dict]:
    """(crowd.json, report) from the service's rows for 군산."""
    by_name: dict[str, list[dict]] = collections.defaultdict(list)
    for it in items:
        if squash(it.get("signguNm")) == CITY:
            by_name[squash(it.get("tAtsNm"))].append(it)
    out, unmatched, claimed, basis_of = {}, [], collections.defaultdict(list), {}
    for name in by_name:
        pid, basis, cands = places.match(name, {"attraction"})
        if pid:
            claimed[pid].append(name)
            basis_of[name] = basis
        else:
            unmatched.append({"name": name, "reason": f"애매함: {', '.join(cands)}" if cands else "이름이 같은 장소 없음"})
    for pid, names in claimed.items():
        if len(names) > 1:
            unmatched += [{"name": n, "reason": f"다른 관광지와 같은 장소({pid})"} for n in names]
            continue
        name = names[0]
        days = {}
        for r in sorted(by_name[name], key=lambda r: str(r.get("baseYmd"))):
            d, v = iso(r.get("baseYmd")), number(r.get("cnctrRate"))
            if d and v is not None:
                days[d] = v
        out[pid] = {"name": name, "match": basis_of[name], "days": days}
    all_days = sorted({iso(r.get("baseYmd")) for rows in by_name.values() for r in rows if iso(r.get("baseYmd"))})
    vals = [number(r.get("cnctrRate")) for rows in by_name.values() for r in rows]
    vals = [v for v in vals if v is not None]
    start, end = (all_days[0], all_days[-1]) if all_days else ("", "")
    data = {
        "_about": (f"관광지 집중률 예측 — 한국관광공사 '관광지 집중률 방문자 추이 예측 정보'(TatsCnctrRateService "
                   f"tatsCnctrRatedList, 군산시 areaCd 52·signguCd 52130)를 {checked}에 받아 이 사이트 장소 id로 묶었다"
                   "(tools/tourapi_related.py). ㈜케이티 이동통신 데이터(2018년부터)의 패턴으로 조회일부터 30일 동안 그 관광지에 "
                   "방문자가 얼마나 몰릴지 머신러닝으로 예측한 값이다. 값(cnctrRate)은 그 관광지가 가장 붐비는 시기를 100으로 본 "
                   "상대 수치(단위 없음, 퍼센트·인원 아님)이고 서비스가 준 숫자 그대로다 — 관광지끼리 비교하는 값이 아니고 "
                   f"실제와 다를 수 있다. 이번 값의 범위 {min(vals) if vals else '-'}~{max(vals) if vals else '-'}. 등급(여유·붐빔)은 "
                   "만들지 않았다(화면이 정한다). name은 서비스상 관광지 이름, 장소는 이름이 같을 때만 이었다(애매하면 unmatched). "
                   "매일 바뀌는 예측이라 다시 받아야 한다."),
        "source": {"provider": PROVIDER, "dataset": CROWD["dataset"], "url": CROWD["url"],
                   "api": f"{GW}/{CROWD['service']}/{CROWD['op']}", "basis": CROWD["basis"],
                   "base_date": checked, "checked_at": checked},
        "generated": checked,
        "period": {"start": start, "end": end},
        "range_seen": [min(vals), max(vals)] if vals else [],
        "places": dict(sorted(out.items())),
        "unmatched": sorted(unmatched, key=lambda u: u["name"]),
    }
    return data, {"rows": len(items), "names": len(by_name), "matched": len(out)}


# ---- files -------------------------------------------------------------------------------------------------------
def write_csv(path: Path, rows: list[dict]) -> None:
    cols: list[str] = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")


def run_related(a, places: Places, key: str, cache: Path) -> int:
    client = Client(key, RELATED["service"], cache / RELATED["service"], max_calls=a.max_calls, refresh=a.fresh)
    base_ym = a.base_ym or latest_base_ym(client, dt.date.today())
    items = client.all(RELATED["op"], baseYm=base_ym, **AREA)
    data, rep = build_related(items, places, base_ym, client.checked_at())
    n_rel = len(rep["related_names"])
    print(f"[연관 관광지] 기준연월 {base_ym}: 행 {rep['rows']} · 중심관광지 {rep['centers']} 중 장소와 이음 {len(data['places'])}"
          f" · 군산 연관관광지 이름 {n_rel} 중 장소와 이음 {len(rep['related_matched'])}"
          f" (애매 {len(rep['related_ambiguous'])}) · 호출 {client.calls}(캐시 {client.cache_hits})")
    for pid, c in data["centers"].items():
        linked = sum(1 for e in data["places"][pid] if e["place_id"])
        print(f"  {pid} ← {c['name']} ({c['match']}): {len(data['places'][pid])}곳, 장소 연결 {linked}")
    for u in data["unmatched_centers"]:
        print(f"  못 이음(중심): {u['name']} — {u['reason']}")
    for n, c in sorted(rep["related_ambiguous"].items()):
        print(f"  애매(연관): {n} — {', '.join(c)}")
    if a.apply:
        raw = a.data.parent / "raw" / a.data.name / "tourapi_related" / f"related_{base_ym}.csv"
        write_csv(raw, related_csv_rows(items))
        write_json(a.data / "related.json", data)
        print(f"  씀: {raw} · {a.data / 'related.json'}")
    return 0


def run_crowd(a, places: Places, key: str, cache: Path) -> int:
    today = dt.date.today()
    client = Client(key, CROWD["service"], cache / CROWD["service"] / today.strftime("%Y%m%d"),
                    max_calls=a.max_calls, refresh=a.fresh)
    items = client.all(CROWD["op"], **AREA)
    data, rep = build_crowd(items, places, client.checked_at())
    print(f"[집중률] {data['period']['start']}~{data['period']['end']}: 행 {rep['rows']} · 관광지 {rep['names']} 중 장소와 이음 "
          f"{rep['matched']} · 값 범위 {data['range_seen']} · 호출 {client.calls}(캐시 {client.cache_hits})")
    for pid, v in data["places"].items():
        print(f"  {pid} ← {v['name']} ({v['match']}): {len(v['days'])}일")
    for u in data["unmatched"]:
        print(f"  못 이음: {u['name']} — {u['reason']}")
    if a.apply:
        raw = a.data.parent / "raw" / a.data.name / "tourapi_crowd" / f"crowd_{today.strftime('%Y%m%d')}.csv"
        write_csv(raw, sorted(items, key=lambda r: (squash(r.get("tAtsNm")), str(r.get("baseYmd")))))
        write_json(a.data / "crowd.json", data)
        print(f"  씀: {raw} · {a.data / 'crowd.json'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", nargs="?", choices=("both", "related", "crowd"), default="both")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--base-ym", help="연관 관광지 기준연월 YYYYMM (없으면 가장 최근 달)")
    ap.add_argument("--max-calls", type=int, default=40)
    ap.add_argument("--fresh", action="store_true", help="캐시를 쓰지 않고 새로 받는다")
    ap.add_argument("--cache", type=Path, default=Path("data/cache"))
    a = ap.parse_args(argv)
    key = key_from_env()
    places = Places(json.loads((a.data / "places.json").read_text("utf-8")))
    try:
        if a.what in ("both", "related"):
            run_related(a, places, key, a.cache)
        if a.what in ("both", "crowd"):
            run_crowd(a, places, key, a.cache)
    except TourAPIError as err:
        print(redact(str(err), normalize_key(key)), file=sys.stderr)
        return 1
    if not a.apply:
        print("(미리보기 — 파일을 쓰려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
