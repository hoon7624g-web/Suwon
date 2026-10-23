"""TourAPI bulk enrichment: the city's list per content type, matched locally (few calls).

    python tools/tourapi_bulk.py --data data/daegu --max-calls 900                       # list, coordinates, photos
    python tools/tourapi_bulk.py --data data/daegu --details --add-new --events --max-calls 900
    python tools/tourapi_bulk.py --data data/daegu --add-new --district 중구 --district 수성구  # some 구·군 first
    python tools/tourapi_bulk.py --data data/daegu --gallery --max-calls 900              # detailImage2 photos
    python tools/tourapi_bulk.py --data data/daegu --offline                             # cache only
    python tools/tourapi_bulk.py --data data/daegu --courses --max-calls 300             # 여행코스(25) → tourapi_courses.json
    python tools/tourapi_bulk.py --data data/daegu --barrier-free --max-calls 600        # 무장애 여행 정보, alone
    python tools/tourapi_bulk.py --data data/daegu --nearby-only     # nearby again from stored coordinates, no calls

Options
  --data DIR        the city's data folder (required; site.json there says which city)
  --max-calls N     live requests of this run (default 120); the next run continues from the cache
  --offline         cache only, no network        --refresh   ignore the cache (tools/refresh.py --fresh)
  --gallery         detailImage2 photos for every matched place (one call per place)
  --details         detailCommon2 · detailIntro2 (· detailInfo2) for every matched place, merged per field
  --add-new         TourAPI-only places (types 12·14·28·32·38·39) as draft/basic records with a stored slug
  --events          searchFestival2 from 1 January this year (runs before --details/--add-new: time-sensitive)
  --district NAME   repeatable: --details and --add-new only for these 구·군 (names of site.json districts)
  --courses         TourAPI 여행코스 only (contentTypeId 25), alone: areaBasedList2 per 구·군 (every page), then per course
                    detailCommon2 · detailIntro2 (distance, taketime, schedule, theme) · detailInfo2 (the sub-stops in
                    order: subnum, subname, subcontentid). Writes <data>/tourapi_courses.json for a later, person-checked
                    import (the city's tools/import_courses_<city>.py); places.json, courses.json and events.json are
                    not touched.
                    A sub-stop is matched to a place by its contentid only (any status, recorded as such); a name is
                    never a match. With --district only those 구·군 are listed and the file keeps the others' courses.
  --barrier-free    alone: 한국관광공사 무장애 여행 정보 merged into the published places (see below)
  --nearby-only     alone: every place's nearby list again from the coordinates in places.json; no client, no calls

1. ldongCode2 -> the provider's codes (pipeline.tourapi.resolve_ldong): the 시·도 whose name is exactly
   tourapi.ldong_regn_name (else region_admin), then every 구·군 of site.json districts under it — a 구·군 the
   provider does not list there is an error naming it — or, without districts, the locality. No code is written in
   code or config.
2. areaBasedList2 for content types 12·14·28·38·32·39, every page: one list per resolved 구·군 (tourapi.list_scope
   "districts", the default) or one for the whole 시·도 ("region"). Items are deduplicated by contentid and keep the
   구·군 of their list as tourapi.ldong_signgu_cd / ldong_signgu_name (the provider's classification).
3. Local matching against places.json (missing: starts as []; duplicates skipped): the same name (the city's short
   name in front ignored, City.strip_region_prefix), or a near-identical name at the same road address in the same
   구·군 (road_key '<구·군>|<road><no>'; a 법정동 'N가' is not a road number). Anything less certain stays
   unmatched (listed in the report).
4. Fills tourapi.contentid, geo (TourAPI; a point from another source — the city's official tourism site, a
   facility's homepage — stays, the report lists how far TourAPI's is), images
   (cpyrhtDivCd Type1/Type3 only, https, credit 한국관광공사; the alt is the title without its bracketed city tail,
   City.title_suffix_rx), with --gallery also detailImage2 photos named after the place, then straight-line nearby
   places (attraction/stay/food, within 2 km) computed from those coordinates; nearby_source names every provider of
   the points used (pipeline.schema.nearby_provider: '한국관광공사 TourAPI 좌표' when all are TourAPI's).
5. --events: searchFestival2 for the whole 시·도 of a metropolitan city (else per resolved 시), every page,
   deduplicated; a new event stores its series slug (pipeline.slugs.series_slug). --add-new order: site.json
   districts, then content type (the list order above), then title; `have` grows as places are added, and a new
   place's slug is ASCII (slugs.assign_slugs, the city's collision policy), place-<contentid> when the name gives none.
Fields named in an entity's "locks" are not touched. Values are copied as given; nothing is guessed.
checked_at is the date the TourAPI response was fetched (a cached response keeps its own date), so a
cache-first re-run does not bump 확인일 or sitemap lastmod (aeo_geo_spec P0-4). --refresh ignores the cache
(used by tools/refresh.py --fresh) and the values it re-fetches get today's date.

Stops and errors. The call cap or the provider's quota (TourAPIStopError) ends the run where it is; what was
finished is saved and reports/tourapi_bulk.md says where it stopped. If the region codes or the list cannot be read
(cap, quota, --offline without cache, network, a 구·군 missing from ldongCode2), nothing is changed — places.json and
events.json stay as they were — the report says why, and the tool exits 1 with that message (no traceback).
Exit codes: 0 done (see "stopped" in the summary line), 1 list not collected, 2 configuration error.

--barrier-free runs alone: 한국관광공사 무장애 여행 정보 (KorWithService2, its own data.go.kr 활용신청) for every
published place with a TourAPI contentid — detailWithTour2, and for an answer with values detailCommon2 of the same
service to check the title is our place's TourAPI title. Wheelchair, accessible parking/toilet/route and stroller
rental merge with provider '한국관광공사 무장애 여행 정보(TourAPI)' (tools/tourapi_details.merge_facts): a new value is
added with its source, the same value confirms, a different one is kept beside ours (both shown + 방문 전 전화 확인).
Its own client (pipeline.tourapi.barrier_free_client), cache folder (data/cache/tourapi/barrier_free — the folder
tools/tourapi_harvest.py --service bf fills, so a harvested day is all cache hits) and --max-calls; report in
reports/tourapi_barrier_free.md for a person to read before the guides that cite these values are rewritten.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.city import CityConfigError
from pipeline.city import of as city_of
from pipeline.enrich import event_series_slug, haversine_m, load_dotenv
from pipeline.relations import raw_family
from pipeline.schema import TOURAPI_LICENSE_MAP, geo_providers, license_allowed, nearby_provider
from pipeline.textutil import normalize_name, squash_ws
from pipeline.tourapi import (KIND_BY_TYPE, TourAPIConfigError, TourAPIError, TourAPIStopError, fetch_festivals,
                              from_site_config, list_scope, resolve_ldong)
from tools.tourapi_details import display_name

LIST_TYPES = ("12", "14", "28", "38", "32", "39")
COURSE_TYPE = "25"                     # 여행코스: listed only with --courses (run_courses)
COURSES_FILE = "tourapi_courses.json"
# road + building number; a 법정동 'N가' after the number ('샘플로2가 88-1') is not one
ROAD = re.compile(r"([가-힣0-9]+(?:로|길))\s*([0-9]+(?:-[0-9]+)?)(?![0-9]*가)")
GENERIC = re.compile(r"게스트하우스|게하|모텔|호텔|펜션|민박|하우스")
BRANCH = re.compile(r"(\d+)\s*호점")
NEARBY_RADIUS_M = 2000
NEARBY_PER_KIND = 3
NO_DISTRICT = "구·군 미상"


class ConfigError(ValueError):
    """The command line or the data folder does not fit this tool (exit 2)."""


def road_no(address: str | None) -> str:
    """'OO시 샘플4길 14(OO동)' -> '샘플4길14'; '' when the address has no road + building number ('샘플로2가 88-1'
    is a 법정동 lot address, not road '샘플로' number 2)."""
    m = ROAD.search(re.sub(r"\s+", " ", address or ""))
    return f"{m.group(1)}{m.group(2)}" if m else ""


def road_key(address: str | None, city) -> str:
    """'<구·군>|<road><no>': 'OO광역시 중구 샘플로2길 80' -> '중구|샘플로2길80' (the 구·군 part is '' when the address
    names none, always for a city without districts); '' when there is no road + number."""
    rn = road_no(address)
    return f"{city.parse_address(address).district}|{rn}" if rn else ""


def name_key(name: str | None, city) -> str:
    """A name for matching: normalised (no brackets, spaces or punctuation), the city's short name in front dropped
    unless the name starts with a homograph (City.strip_region_prefix)."""
    return city.strip_region_prefix(normalize_name(name))


def photo_title(title: str | None, city) -> str:
    """What the provider photo shows: the title without '[…]' and the bracketed city tail at the end
    (tools.tourapi_details.display_name, one rule)."""
    return display_name(title, city)


def retry(fn, *args, **kwargs):
    """Connection resets through the proxy are transient; provider errors are not retried."""
    for attempt in range(6):
        try:
            return fn(*args, **kwargs)
        except TourAPIError as err:
            if "네트워크 오류" not in str(err) or attempt == 5:
                raise
            time.sleep(min(30, 2 ** (attempt + 1)))


def fetch_region(api, regn: str, signgu: str | None, rows: int = 200, types=LIST_TYPES) -> list[dict]:
    """areaBasedList2, every page of every type (LIST_TYPES; --courses: 25 only), for one 시군구 (signgu None: the
    whole 시·도). A page ends a type when it is short or adds no new contentid."""
    items: list[dict] = []
    for ctype in types:
        page, seen = 1, set()
        while True:
            got = retry(api.area_based, regn, signgu, ctype, rows=rows, page=page)
            new = [it for it in got if str(it.get("contentid")) not in seen]
            seen.update(str(it.get("contentid")) for it in new)
            items += new
            if len(got) < rows or not new:
                break
            page += 1
    return items


def fetch_list(api, ldong, scope: str, rows: int = 200, types=LIST_TYPES, only=frozenset()) -> tuple[list[dict], dict]:
    """The city's whole list: one fetch_region per resolved 구·군 (scope 'districts') or one for the 시·도 ('region'),
    deduplicated by contentid (the first kept). Each item is tagged with the provider's 구·군 of its list
    (ldong_signgu_cd / ldong_signgu_name; in a 'region' list, from the item's own lDongSignguCd when it is one of the
    resolved codes; `only`: these 구·군 names, else all). Returns (items, {"scope", "regn", "by_district": {name: count},
    "duplicates"})."""
    info = {"scope": scope, "regn": f"{ldong.regn_name}({ldong.regn_cd})", "by_district": {}, "duplicates": 0}
    out, seen = [], set()
    for code, name in [(None, "")] if scope == "region" else [x for x in ldong.signgu if not only or x[1] in only]:
        if name:
            info["by_district"].setdefault(name, 0)
        for it in fetch_region(api, ldong.regn_cd, code, rows, types):
            cid = str(it.get("contentid"))
            if cid in seen:
                info["duplicates"] += 1
                continue
            seen.add(cid)
            code_i = code or str(it.get("lDongSignguCd") or "")
            name_i = name or ldong.name_of(code_i)
            if name_i:
                it["ldong_signgu_cd"], it["ldong_signgu_name"] = code_i, name_i
            info["by_district"][name_i or NO_DISTRICT] = info["by_district"].get(name_i or NO_DISTRICT, 0) + 1
            out.append(it)
    return out, info


def match(place: dict, by_name: dict, by_road: dict, city) -> tuple[dict | None, str]:
    kind = place.get("kind")
    nk = name_key(place.get("name"), city)
    rk = road_key((place.get("facts") or {}).get("address"), city)
    same_name = [c for c in by_name.get(nk, []) if KIND_BY_TYPE.get(str(c.get("contenttypeid"))) == kind]
    if len(same_name) == 1:
        return same_name[0], "same_name"
    if len(same_name) > 1 and rk:
        hit = [c for c in same_name if road_key(c.get("addr1"), city) == rk]
        if len(hit) == 1:
            return hit[0], "same_name_address"
    if rk:
        near = [c for c in by_road.get(rk, []) if KIND_BY_TYPE.get(str(c.get("contenttypeid"))) == kind
                and SequenceMatcher(None, nk, name_key(c.get("title"), city)).ratio() >= 0.6]
        if len(near) == 1:
            return near[0], "same_address_similar_name"
    if rk and kind in ("stay", "food"):  # a business at one address: '게스트하우스 OO여행' = 'OO여행'
        core = lambda s: GENERIC.sub("", s)
        branches = lambda s: set(BRANCH.findall(s or ""))
        hit = [c for c in by_road.get(rk, []) if KIND_BY_TYPE.get(str(c.get("contenttypeid"))) == kind
               and branches(c.get("title")) == branches(place.get("name"))
               and min(len(core(nk)), len(core(name_key(c.get("title"), city)))) >= 2
               and (core(nk) in core(name_key(c.get("title"), city))
                    or core(name_key(c.get("title"), city)) in core(nk))]
        if len(hit) == 1:
            return hit[0], "same_address_name_contains"
    return None, ""


def https(url: str) -> str:
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def fill(place: dict, cand: dict, basis: str, allowed: list | None, city) -> dict:
    locks = set(place.get("locks") or [])
    changed = {"geo": False, "image": ""}
    place["tourapi"] = {**(place.get("tourapi") or {}), "contentid": str(cand["contentid"]),
                        "contenttypeid": str(cand.get("contenttypeid", "")), "title": cand.get("title", ""),
                        "match_basis": basis, "modifiedtime": cand.get("modifiedtime", ""),
                        **{k: cand[k] for k in ("ldong_signgu_cd", "ldong_signgu_name") if cand.get(k)}}
    try:
        lat, lng = float(cand.get("mapy")), float(cand.get("mapx"))
    except (TypeError, ValueError):
        lat = lng = None
    have = place.get("geo") or {}
    if "geo" not in locks and lat and lng:
        if have.get("lat") is None or have.get("source") in (None, "", "TourAPI"):
            place["geo"] = {"lat": lat, "lng": lng, "source": "TourAPI"}
            changed["geo"] = True
        else:  # a point from another source (the city's tourism site, a homepage) stays; how far TourAPI's is goes in the stats
            changed["geo_kept"] = int(round(haversine_m(float(have["lat"]), float(have["lng"]), lat, lng)))
    code = TOURAPI_LICENSE_MAP.get(str(cand.get("cpyrhtDivCd") or ""), "UNKNOWN")
    if "images" not in locks and cand.get("firstimage"):
        others = [i for i in (place.get("images") or []) if i.get("source") != "TourAPI"]
        first = https(cand["firstimage"])
        # keep gallery photos added earlier (detailImage2); the list photo stays first
        gallery = [i for i in (place.get("images") or []) if i.get("source") == "TourAPI" and i.get("url") != first]
        tour = []
        if license_allowed(code, allowed):
            tour = [{"url": first, "alt": photo_title(cand.get("title"), city) or place["name"],
                     "credit": "한국관광공사", "license": code, "source": "TourAPI"}]
            changed["image"] = code
        place["images"] = others + tour + gallery
    return changed


def add_gallery(api, place: dict, allowed: list | None, city, limit: int = 6) -> int:
    """detailImage2 photos whose name mentions the place (provider lists sometimes carry other places'
    photos), allowed licence types only, after the list photo."""
    if "images" in set(place.get("locks") or []):
        return 0
    title = photo_title((place.get("tourapi") or {}).get("title"), city)
    key = normalize_name(title)[:6]
    have = {i["url"] for i in place.get("images") or []}
    added = 0
    for im in retry(api.detail_image, place["tourapi"]["contentid"]):
        code = TOURAPI_LICENSE_MAP.get(str(im.get("cpyrhtDivCd") or ""), "UNKNOWN")
        url = https(im.get("originimgurl") or "")
        if (not url or url in have or not license_allowed(code, allowed)
                or len(key) < 2 or key not in normalize_name(im.get("imgname"))):
            continue
        place.setdefault("images", []).append({"url": url, "alt": title or place["name"], "credit": "한국관광공사",
                                               "license": code, "source": "TourAPI"})
        have.add(url)
        added += 1
        if len([i for i in place["images"] if i.get("source") == "TourAPI"]) >= limit:
            break
    return added


# Shops listed as "nearby": markets, local-produce halls and bookstores only (TourAPI lclsSystm3), not marts or malls
NEARBY_SHOP_LCLS = ("SH05", "SH06", "SH07")


# A neighbour is listed only when its own page is on the public site (published) or has passed review: a draft (a
# brand shop, a group's office, a record still to check) would take a slot as a bare map search and push a real
# neighbour within the radius out of the three per kind. A record without a status is an old-format one: shown.
NEARBY_STATUSES = ("published", "reviewed")


def compute_nearby(places: list[dict], today: str) -> int:
    """Up to NEARBY_PER_KIND places of each kind within NEARBY_RADIUS_M (straight line between the two places' coordinates).
    A place's own family (pipeline/relations.py: its parent, parts and same-building partners — they have their own
    lines on the page) is never its nearby place, and a same-building alias is skipped while its parent is listable
    (one building, one row); the next places fill the slots. Network-free: also run alone with --nearby-only."""
    live = [p for p in places if not p.get("duplicate_of") and (p.get("geo") or {}).get("lat") is not None]
    listable = lambda q: (not q.get("exclude") and q.get("status", "published") in NEARBY_STATUSES
                          and (q.get("category") != "쇼핑"
                               or (q.get("tourapi") or {}).get("lcls", "").startswith(NEARBY_SHOP_LCLS)))
    family, alias = raw_family(places)
    shown = {q["id"] for q in live if listable(q) and q.get("id")}   # records without an id (tests) have no family
    n = 0
    for p in live:
        if "nearby" in set(p.get("locks") or []):
            continue
        fam = family.get(p.get("id")) or set()
        dists = sorted(((haversine_m(p["geo"]["lat"], p["geo"]["lng"], q["geo"]["lat"], q["geo"]["lng"]), q)
                        for q in live if q is not p and listable(q) and q.get("id") not in fam
                        and alias.get(q.get("id")) not in shown), key=lambda x: x[0])
        groups = {"attraction": [], "stay": [], "food": []}
        geos = [p["geo"]]
        for d, q in dists:
            if d > NEARBY_RADIUS_M:
                break
            g = groups.get(q.get("kind"))
            if g is not None and len(g) < NEARBY_PER_KIND:
                g.append({"name": q["name"], "kind": q["kind"], "type_label": q.get("category") or "",
                          "distance_m": int(round(d)), "internal_slug": q["slug"],
                          "contentid": (q.get("tourapi") or {}).get("contentid", "")})
                geos.append(q["geo"])
        nearby = groups["attraction"] + groups["stay"] + groups["food"]
        kept = (p.get("nearby_source") or {}).get("checked_at") if nearby == p.get("nearby") else ""
        p["nearby"] = nearby
        # whose coordinates the distances come from: this place's point and every listed place's, TourAPI first
        # ('한국관광공사 TourAPI 좌표' when all are TourAPI's, '한국관광공사 TourAPI·<other provider> 좌표' when mixed)
        providers = geo_providers(geos)
        p["nearby_source"] = {"provider": nearby_provider(providers), "providers": providers,
                              "radius_m": NEARBY_RADIUS_M, "distance_basis": "직선거리", "checked_at": kept or today}
        n += bool(p["nearby"])
    return n


def run_nearby_only(data_dir: Path, today: str | None = None) -> dict:
    """--nearby-only: recompute every place's nearby list from the coordinates already in places.json (compute_nearby)
    and write it back. No TourAPI client is created and nothing is fetched; locks are kept."""
    import datetime as dt
    path = data_dir / "places.json"
    places = json.loads(path.read_text("utf-8"))
    before = {p["id"]: p.get("nearby") for p in places}
    n = compute_nearby(places, today or dt.date.today().isoformat())
    path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    changed = sum(1 for p in places if p.get("nearby") != before.get(p["id"]))
    return {"nearby_pages": n, "changed": changed}


def _priority(p: dict) -> tuple:
    """Detail calls go to the pages people read first: full tier, question places, attractions, the rest."""
    return (p.get("tier") != "full", not p.get("question_ids"), p.get("kind") != "attraction", p.get("name", ""))


def fetched_on(api, start: int, today: str) -> str:
    """Oldest fetch date of the responses the client answered since `start` (len(api.fetched_dates) before the
    calls): a cached response keeps the date it was fetched, so re-running from cache changes no 확인일."""
    dates = (getattr(api, "fetched_dates", None) or [])[start:]
    return min(dates) if dates else today


def _details(api, cid: str, ctype: str) -> tuple[dict, dict, list]:
    common = retry(api.detail_common, cid)
    intro = retry(api.detail_intro, cid, ctype) if ctype else {}
    info = retry(api.detail_info, cid, ctype) if ctype in ("12", "28") else []
    return common, intro, info


def place_district(p: dict, city) -> str:
    """The 구·군 of one of our places: the provider's (tourapi.ldong_signgu_name), else the one its address names."""
    return ((p.get("tourapi") or {}).get("ldong_signgu_name")
            or city.parse_address((p.get("facts") or {}).get("address")).district)


def item_district(it: dict, city) -> str:
    """The 구·군 of a list item: the one of the list it came from, else the one its address names."""
    return it.get("ldong_signgu_name") or city.parse_address(it.get("addr1")).district


def district_filter(names, city) -> frozenset:
    """--district values, each a name of site.json districts (ConfigError otherwise); empty: no filter."""
    picked = [squash_ws(n) for n in names or () if squash_ws(n)]
    unknown = [n for n in picked if n not in city.districts]
    if unknown:
        raise ConfigError(f"--district {', '.join(unknown)}: site.json districts에 없는 이름 "
                          f"(있는 값: {', '.join(city.districts) or '없음 — districts가 비어 있음'})")
    return frozenset(picked)


def run(data_dir: Path, max_calls: int, offline: bool, gallery: bool = False, details: bool = False,
        add_new: bool = False, events: bool = False, refresh: bool = False, districts=()) -> dict:
    import datetime as dt
    from tools.tourapi_details import (NEW_PLACE_TYPES, alternate_name, clean, duplicate_candidates, event_key,
                                       festival_event, merge_facts, new_place, tourapi_facts)
    load_dotenv(Path(".env"))
    site_path = data_dir / "site.json"
    if not site_path.exists():
        raise ConfigError(f"{site_path} 없음 — --data에 도시 데이터 폴더(site.json이 있는 곳)를 주세요")
    site = json.loads(site_path.read_text("utf-8"))
    city = city_of(site)
    scope = list_scope(city)
    only = district_filter(districts, city)
    places_path = data_dir / "places.json"
    places = json.loads(places_path.read_text("utf-8")) if places_path.exists() else []
    overrides_path = data_dir / "tourapi_overrides.json"
    overrides = json.loads(overrides_path.read_text("utf-8")) if overrides_path.exists() else {}
    same = {str(k): ([v] if isinstance(v, str) else list(v))                 # contentid -> our slug(s)
            for k, v in (overrides.get("same") or {}).items()}
    different = {str(x) for x in overrides.get("different") or []}           # contentid: add as its own place
    skip = {str(x) for x in overrides.get("skip") or []}                     # contentid: not a place for this site
    hold = {str(x) for x in overrides.get("hold") or {}}                     # contentid: a person decides first
    api = from_site_config(site, os.environ.get("TOURAPI_KEY", ""), data_dir.parent / "cache" / "tourapi",
                           offline=offline, refresh=refresh, max_calls=max_calls)
    today = dt.date.today().isoformat()
    stats = {"list_items": 0, "list_complete": False, "live_calls": 0, "targets": 0, "matched": {}, "geo": 0,
             "images": {"KOGL-1": 0, "KOGL-3": 0}, "image_other_type": 0, "unmatched": []}
    if only:
        stats["districts"] = sorted(only, key=city.districts.index)
    flags = {"gallery": gallery, "details": details, "add_new": add_new, "events": events}
    ldong = None
    try:  # region codes and the whole list first: without them nothing below is safe to write
        ldong = resolve_ldong(api, city, call=retry)
        items, stats["list"] = fetch_list(api, ldong, scope)
    except TourAPIError as err:  # the call cap, the quota, a missing cache, the network, a 구·군 not in ldongCode2
        stats["stopped"], stats["stopped_at"] = str(err), "ldong" if ldong is None else "list"
        stats["live_calls"], stats["cache_hits"] = api.live_calls, api.cache_hits
        _write_report(stats, today, flags)
        print(json.dumps(_summary(stats, flags), ensure_ascii=False))
        return stats
    stats["list_complete"] = True
    stats["list_items"] = len(items)
    by_cid = {str(it["contentid"]): it for it in items}
    by_name: dict[str, list] = {}
    by_road: dict[str, list] = {}
    for it in items:
        by_name.setdefault(name_key(it.get("title"), city), []).append(it)
        rk = road_key(it.get("addr1"), city)
        if rk:
            by_road.setdefault(rk, []).append(it)
    allowed = (site.get("publish_rules") or {}).get("allowed_image_licenses")
    forced = {slug: by_cid[cid] for cid, slugs in same.items() if cid in by_cid for slug in slugs}
    for p in places:
        if p.get("duplicate_of") or str(p.get("id", "")).startswith("tourapi-"):
            continue
        stats["targets"] += 1
        if p.get("slug") in forced:
            cand, basis = forced[p["slug"]], "reviewed_same_place"
        else:
            cand, basis = match(p, by_name, by_road, city)
        if not cand:
            stats["unmatched"].append(f"{p['kind']}:{p['name']}")
            continue
        stats["matched"][p["kind"]] = stats["matched"].get(p["kind"], 0) + 1
        ch = fill(p, cand, basis, allowed, city)
        stats["geo"] += ch["geo"]
        if "geo_kept" in ch:
            stats.setdefault("geo_kept", []).append(f"{p['name']}: {p['geo'].get('source')} 좌표 유지 "
                                                    f"(TourAPI 좌표와 {ch['geo_kept']}m)")
        if ch["image"]:
            stats["images"][ch["image"]] += 1
        elif cand.get("firstimage"):
            stats["image_other_type"] += 1
    in_scope = lambda district: not only or district in only
    detail_log: list[str] = []
    stage = "gallery"
    try:
        if gallery:
            stats["gallery_added"], stats["gallery_errors"] = 0, []
            for p in places:
                if p.get("duplicate_of") or not (p.get("tourapi") or {}).get("match_basis"):
                    continue
                try:
                    stats["gallery_added"] += add_gallery(api, p, allowed, city)
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    stats["gallery_errors"].append(f"{p['name']}: {err}")
        stage = "events"
        if events:
            ev_path = data_dir / "events.json"
            existing = json.loads(ev_path.read_text("utf-8")) if ev_path.exists() else []
            e = stats["events"] = {"festival_items": 0, "added": [], "updated": [], "errors": []}
            mark = len(getattr(api, "fetched_dates", []))
            try:
                fest = fetch_festivals(api, f"{today[:4]}0101", ldong, call=retry)
            except TourAPIStopError:
                raise
            except TourAPIError as err:
                e["errors"].append(f"searchFestival2: {err}")
                fest = None
            list_date = fetched_on(api, mark, today)
            e["festival_items"] = len(fest or [])
            have_cid = {str(x.get("contentid")): x for x in existing if x.get("contentid")}
            for it in fest or []:
                cid = str(it["contentid"])
                start = len(getattr(api, "fetched_dates", []))
                try:
                    intro = retry(api.detail_intro, cid, "15")
                    common = retry(api.detail_common, cid)
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    e["errors"].append(f"{it.get('title')}: {err}")
                    continue
                checked = min(list_date, fetched_on(api, start, today))
                ev = festival_event(it, intro, common, checked)
                if cid in have_cid:  # refresh our earlier TourAPI copy
                    have_cid[cid].update({k: v for k, v in ev.items() if k not in ("id", "status", "summary")})
                    e["updated"].append(ev["name"])
                    continue
                key, year = event_key(ev["name"]), ev["start_date"][:4]
                twin = next((x for x in existing if event_key(x.get("name")) == key
                             and (x.get("start_date") or "")[:4] == year and year), None)
                if twin:  # same edition already listed from another source: keep its dates, note TourAPI's next to them
                    twin["tourapi_contentid"] = cid
                    if (twin.get("start_date"), twin.get("end_date")) != (ev["start_date"], ev["end_date"]):
                        twin["date_alternatives"] = [{"start_date": ev["start_date"], "end_date": ev["end_date"],
                                                      "provider": "한국관광공사 TourAPI", "checked_at": checked}]
                    for k in ("address", "geo", "tel", "homepage", "playtime", "fee"):
                        if ev.get(k) and not twin.get(k):
                            twin[k] = ev[k]
                    e["updated"].append(twin["name"])
                    continue
                for x in existing:  # undated '매년 …' record of the same festival: mark it recurring
                    if event_key(x.get("name")) == key and not x.get("start_date"):
                        x["recurring"] = True
                ev["slug"] = event_series_slug(ev, existing)  # stored once: the series' URL (CLAUDE.md 2절)
                existing.append(ev)
                have_cid[cid] = ev
                e["added"].append(f"{ev['name']} ({ev['start_date']}~{ev['end_date']})")
            if fest is not None:
                ev_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", "utf-8")
        stage = "details"
        if details:
            d = stats["details"] = {"done": 0, "added": {}, "confirmed": {}, "conflicts": [], "alternate_names": 0,
                                    "errors": []}
            matched = sorted((p for p in places if not p.get("duplicate_of") and (p.get("tourapi") or {}).get("contentid")
                              and in_scope(place_district(p, city))), key=_priority)
            for p in matched:
                t = p["tourapi"]
                cid, ctype = str(t["contentid"]), str(t.get("contenttypeid") or "")
                start = len(getattr(api, "fetched_dates", []))
                try:
                    common, intro, info = _details(api, cid, ctype)
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    d["errors"].append(f"{p['name']}: {err}")
                    continue
                res = merge_facts(p, tourapi_facts(common, intro, info, ctype), fetched_on(api, start, today), cid,
                                  city=city)
                t["modifiedtime"] = common.get("modifiedtime") or t.get("modifiedtime", "")
                t["overview"] = clean(common.get("overview"))  # fact-checking reference only — never rendered
                alt = alternate_name(p, common.get("title") or t.get("title"), city)
                if alt and alt not in (p.get("alternate_names") or []):
                    p.setdefault("alternate_names", []).append(alt)
                    d["alternate_names"] += 1
                d["done"] += 1
                for k in res["added"]:
                    d["added"][k] = d["added"].get(k, 0) + 1
                for k in res["confirmed"]:
                    d["confirmed"][k] = d["confirmed"].get(k, 0) + 1
                d.setdefault("also", 0)
                d["also"] += len(res["also"])
                for k in res["conflicts"]:
                    d["conflicts"].append(f"{p['name']}·{k}")
                    detail_log.append(f"- {p['name']} · {k}: 기존 '{squash(p['facts'].get(k, ''))}' / TourAPI "
                                      f"'{squash(p['fact_alternatives'][k][-1]['value'])}'")
        stage = "add_new"
        if add_new:
            n = stats["new_places"] = {"added": [], "held_duplicate_candidates": [], "skipped": 0, "errors": []}
            have = {str((p.get("tourapi") or {}).get("contentid")) for p in places if (p.get("tourapi") or {}).get("contentid")}
            taken = {p["slug"] for p in places if p.get("slug")}
            order = {name: i for i, name in enumerate(city.districts)}
            rank = lambda it: (order.get(item_district(it, city), len(order)),
                               LIST_TYPES.index(str(it.get("contenttypeid"))), it.get("title", ""))
            todo = sorted((it for it in items if str(it.get("contenttypeid")) in NEW_PLACE_TYPES
                           and str(it["contentid"]) not in have and str(it["contentid"]) not in same
                           and in_scope(item_district(it, city))), key=rank)
            for it in todo:
                cid = str(it["contentid"])
                if cid in have:  # added earlier in this run
                    continue
                if cid in skip:
                    n["skipped"] += 1
                    continue
                if cid in hold:
                    n["held_duplicate_candidates"].append({"contentid": cid, "title": it.get("title", ""),
                                                           "addr": it.get("addr1", ""), "candidates": [],
                                                           "note": overrides["hold"][cid]})
                    continue
                cands = duplicate_candidates(it, places, city)
                if cands and cid not in different:
                    n["held_duplicate_candidates"].append({"contentid": cid, "title": it.get("title", ""),
                                                           "addr": it.get("addr1", ""), "candidates": cands})
                    continue
                start = len(getattr(api, "fetched_dates", []))
                try:
                    common, intro, info = _details(api, cid, str(it.get("contenttypeid")))
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    n["errors"].append(f"{it.get('title')}: {err}")
                    continue
                place = new_place(it, common, intro, info, fetched_on(api, start, today), allowed, taken, city)
                places.append(place)
                have.add(cid)
                n["added"].append(f"{place['kind']}:{place['name']}")
    except TourAPIStopError as err:
        stats["stopped"], stats["stopped_at"] = str(err), stage
    stats["nearby_pages"] = compute_nearby(places, today)
    stats["live_calls"] = api.live_calls
    stats["cache_hits"] = api.cache_hits
    places_path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    _write_report(stats, today, flags, detail_log)
    print(json.dumps(_summary(stats, flags), ensure_ascii=False))
    return stats


def course_record(it: dict, common: dict, intro: dict, info: list, checked: str, by_cid: dict, allowed, city) -> dict:
    """One TourAPI 여행코스 as tourapi_courses.json keeps it: the provider's values only (title, 구·군, category codes,
    intro distance · taketime · schedule · theme · infocenter, the sub-stops in subnum order) and the list photo when
    its licence type is allowed. A sub-stop is tied to one of our places by its contentid alone (place_slug and that
    place's status); without one it stays unmatched. overview / sub-stop overview: fact-checking reference only, never
    rendered (CLAUDE.md 3.4)."""
    from tools.tourapi_details import clean
    code = TOURAPI_LICENSE_MAP.get(str(it.get("cpyrhtDivCd") or ""), "UNKNOWN")
    stops = []
    for sub in sorted(info or [], key=lambda x: int(re.sub(r"\D", "", str(x.get("subnum") or "")) or 0)):
        sid = str(sub.get("subcontentid") or "").strip()
        place = by_cid.get(sid) if sid else None
        stops.append({"subnum": int(re.sub(r"\D", "", str(sub.get("subnum") or "")) or 0),
                      "subname": clean(sub.get("subname")), "subcontentid": sid,
                      "place_slug": place["slug"] if place else "", "place_status": place.get("status", "") if place else "",
                      "match": "contentid" if place else "", "overview": clean(sub.get("subdetailoverview"))})
    rec = {"contentid": str(it["contentid"]), "title": display_name(it.get("title"), city),
           "tourapi_title": it.get("title", ""),
           **{k: it[k] for k in ("ldong_signgu_cd", "ldong_signgu_name") if it.get(k)},
           "addr1": clean(it.get("addr1")), "cat": [it.get(k, "") for k in ("cat1", "cat2", "cat3")],
           "lcls": [it.get(k, "") for k in ("lclsSystm1", "lclsSystm2", "lclsSystm3") if it.get(k)],
           "modifiedtime": common.get("modifiedtime") or it.get("modifiedtime", ""),
           "intro": {"distance": clean(intro.get("distance")), "taketime": clean(intro.get("taketime")),
                     "schedule": clean(intro.get("schedule")), "theme": clean(intro.get("theme")),
                     "infocenter": clean(intro.get("infocentertourcourse"))},
           "stops": stops, "overview": clean(common.get("overview")), "checked_at": checked}
    if it.get("firstimage") and license_allowed(code, allowed):
        rec["image"] = {"url": https(it["firstimage"]), "license": code, "credit": "한국관광공사", "source": "TourAPI"}
    return rec


def run_courses(data_dir: Path, max_calls: int, offline: bool, refresh: bool = False, districts=()) -> dict:
    """--courses: TourAPI 여행코스 (contentTypeId 25) into <data>/tourapi_courses.json (see the module notes). Region
    codes and the course list come first; without them nothing is written. A call cap or the quota during the
    details ends the run: the courses finished so far are written (the cache lets the next run go on) and the file's
    _meta says where it stopped."""
    import datetime as dt
    load_dotenv(Path(".env"))
    site_path = data_dir / "site.json"
    if not site_path.exists():
        raise ConfigError(f"{site_path} 없음 — --data에 도시 데이터 폴더(site.json이 있는 곳)를 주세요")
    site = json.loads(site_path.read_text("utf-8"))
    city = city_of(site)
    scope = list_scope(city)
    only = district_filter(districts, city)
    places_path = data_dir / "places.json"
    places = json.loads(places_path.read_text("utf-8")) if places_path.exists() else []
    by_cid = {str((p.get("tourapi") or {}).get("contentid")): p for p in places
              if (p.get("tourapi") or {}).get("contentid") and not p.get("duplicate_of")}
    out_path = data_dir / COURSES_FILE
    kept = json.loads(out_path.read_text("utf-8")) if out_path.exists() else {}
    api = from_site_config(site, os.environ.get("TOURAPI_KEY", ""), data_dir.parent / "cache" / "tourapi",
                           offline=offline, refresh=refresh, max_calls=max_calls)
    allowed = (site.get("publish_rules") or {}).get("allowed_image_licenses")
    today = dt.date.today().isoformat()
    stats = {"list_complete": False, "courses": 0, "done": 0, "stops": 0, "stops_matched": 0, "errors": []}
    if only:
        stats["districts"] = sorted(only, key=city.districts.index)
    ldong = None
    try:
        ldong = resolve_ldong(api, city, call=retry)
        mark = len(getattr(api, "fetched_dates", []))
        items, stats["list"] = fetch_list(api, ldong, scope, types=(COURSE_TYPE,), only=only)
        list_date = fetched_on(api, mark, today)
    except TourAPIError as err:
        stats["stopped"], stats["stopped_at"] = str(err), "ldong" if ldong is None else "list"
        stats["live_calls"], stats["cache_hits"] = api.live_calls, api.cache_hits
        _write_courses_report(stats, today)
        print(json.dumps({k: v for k, v in stats.items() if k != "errors"}, ensure_ascii=False))
        return stats
    if only:
        items = [it for it in items if item_district(it, city) in only]
    stats["list_complete"] = True
    stats["courses"] = len(items)
    done: list[dict] = []
    try:
        for it in items:
            cid = str(it["contentid"])
            start = len(getattr(api, "fetched_dates", []))
            try:
                common = retry(api.detail_common, cid)
                intro = retry(api.detail_intro, cid, COURSE_TYPE)
                info = retry(api.detail_info, cid, COURSE_TYPE)
            except TourAPIStopError:
                raise
            except TourAPIError as err:
                stats["errors"].append(f"{it.get('title')}: {err}")
                continue
            rec = course_record(it, common, intro, info, min(list_date, fetched_on(api, start, today)), by_cid,
                                allowed, city)
            done.append(rec)
            stats["done"] += 1
            stats["stops"] += len(rec["stops"])
            stats["stops_matched"] += sum(1 for x in rec["stops"] if x["place_slug"])
    except TourAPIStopError as err:
        stats["stopped"], stats["stopped_at"] = str(err), "course_details"
    stats["live_calls"], stats["cache_hits"] = api.live_calls, api.cache_hits
    mine = {c["contentid"] for c in done}
    # --district: the other 구·군's courses stay as the file had them
    others = [c for c in kept.get("courses") or [] if only and c.get("ldong_signgu_name") not in only
              and c["contentid"] not in mine]
    order = {n: i for i, n in enumerate(city.districts)}
    courses = sorted(others + done, key=lambda c: (order.get(c.get("ldong_signgu_name"), len(order)), c["title"]))
    meta = {"about": ("한국관광공사 TourAPI 여행코스(contentTypeId 25) 수집 결과 — 사람이 확인하고 도시의 코스 가져오기 도구"
                      "(tools/import_courses_<도시>.py)로 코스에 넣기 전의 원자료. overview는 사실 확인용이며 싣지 않는다."),
            "provider": "한국관광공사 TourAPI(KorService2: areaBasedList2·detailCommon2·detailIntro2·detailInfo2)",
            "content_type": COURSE_TYPE, "list": stats["list"], "collected_on": today,
            "stopped": stats.get("stopped", ""), "list_complete": True,
            "courses_in_list": len(items), "courses_detailed": len(done)}
    out_path.write_text(json.dumps({"_meta": meta, "courses": courses}, ensure_ascii=False, indent=1) + "\n", "utf-8")
    _write_courses_report(stats, today, courses)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in stats.items() if k != "list"},
                     ensure_ascii=False))
    return stats


def _write_courses_report(stats: dict, today: str, courses: list | None = None) -> None:
    """reports/tourapi_courses.md: counts, where it stopped, and each course with its sub-stops' matches."""
    report = Path("reports")
    report.mkdir(exist_ok=True)
    lines = [f"# TourAPI 여행코스 ({today})", ""]
    if not stats.get("list_complete"):
        lines += [f"- 중단({STAGES.get(stats.get('stopped_at'), stats.get('stopped_at', ''))}): {stats.get('stopped', '')}",
                  f"- 실호출 {stats.get('live_calls', 0)} · 캐시 {stats.get('cache_hits', 0)}",
                  "- 지역 코드나 코스 목록을 다 받지 못해 tourapi_courses.json을 쓰지 않았다."]
    else:
        per = " · ".join(f"{k} {v}" for k, v in (stats.get("list") or {}).get("by_district", {}).items())
        lines += [f"- 목록: {per or '-'} · 코스 {stats['courses']} · 상세 {stats['done']} · 오류 {len(stats['errors'])}",
                  f"- 경유지 {stats['stops']} · contentid로 장소와 맞은 경유지 {stats['stops_matched']}",
                  f"- 실호출 {stats.get('live_calls', 0)} · 캐시 {stats.get('cache_hits', 0)}"]
        if stats.get("stopped"):
            lines.append(f"- 중단(코스 상세): {stats['stopped']} — 받은 코스까지 썼다. 같은 명령을 다시 돌리면 캐시로 이어 간다")
        lines += [f"- 오류: {x}" for x in stats["errors"]]
        for c in courses or []:
            i = c["intro"]
            lines += ["", f"## {c['title']} ({c['contentid']}, {c.get('ldong_signgu_name', '')})",
                      f"- 거리 {i['distance'] or '-'} · 소요 {i['taketime'] or '-'} · 일정 {i['schedule'] or '-'}"]
            lines += [f"- {x['subnum']}. {x['subname']}" + (f" → {x['place_slug']}({x['place_status']})" if x["place_slug"]
                                                           else " (장소 없음)") for x in c["stops"]]
    (report / "tourapi_courses.md").write_text("\n".join(lines) + "\n", "utf-8")


STAGES = {"ldong": "지역 코드(ldongCode2)", "list": "목록(areaBasedList2)", "gallery": "사진(detailImage2)",
          "events": "행사(searchFestival2)", "details": "상세", "add_new": "새 장소", "course_details": "코스 상세"}


def _write_report(stats: dict, today: str, flags: dict, detail_log: list[str] | None = None) -> None:
    """reports/tourapi_bulk.md (for people) and reports/tourapi_bulk.json (every count and list)."""
    report = Path("reports")
    report.mkdir(exist_ok=True)
    lines = [f"# TourAPI 일괄 보강 ({today})", ""]
    lst = stats.get("list") or {}
    if lst:
        per = " · ".join(f"{k} {v}" for k, v in lst.get("by_district", {}).items())
        lines.append(f"- 목록 {lst.get('regn', '')} ({'시·도 전체' if lst.get('scope') == 'region' else '구·군별'}): "
                     f"{per or '-'} · 중복 제거 {lst.get('duplicates', 0)}")
    if stats.get("districts"):
        lines.append(f"- 상세·새 장소 범위(--district): {', '.join(stats['districts'])}")
    if not stats.get("list_complete"):
        lines += [f"- 중단({STAGES.get(stats.get('stopped_at'), '')}): {stats.get('stopped', '')}",
                  f"- 실호출 {stats.get('live_calls', 0)} · 캐시 {stats.get('cache_hits', 0)}",
                  "- 지역 코드나 목록을 다 받지 못해 아무것도 바꾸지 않았다(places.json·events.json 그대로). "
                  "받은 응답은 캐시에 남아 다음 실행이 이어 간다."]
    else:
        lines += [f"- 목록 항목 {stats['list_items']} · 실호출 {stats['live_calls']} · 캐시 {stats['cache_hits']}",
                  f"- 대상 {stats['targets']} · 매칭 {stats['matched']} · 좌표 {stats['geo']}",
                  f"- 허용 사진 Type1 {stats['images']['KOGL-1']} · Type3 {stats['images']['KOGL-3']}"
                  f" · 사진은 있으나 허용 외 유형 {stats['image_other_type']}",
                  f"- 직선거리 주변이 생긴 장소 {stats['nearby_pages']}"]
        lines += [f"- 다른 출처 좌표 유지: {x}" for x in stats.get("geo_kept") or []]
        if stats.get("stopped"):
            lines.append(f"- 중단({STAGES.get(stats.get('stopped_at'), '')}): {stats['stopped']} — 그 전까지 한 것은 저장했다")
        if flags.get("gallery") and "gallery_added" in stats:
            lines += ["", "## 사진(detailImage2)", "",
                      f"- 추가 {stats['gallery_added']} · 오류 {len(stats['gallery_errors'])}"]
            lines += [f"- 오류: {x}" for x in stats["gallery_errors"]]
        if flags.get("details") and "details" in stats:
            d = stats["details"]
            lines += ["", "## 상세(detailCommon2·detailIntro2·detailInfo2)", "",
                      f"- 처리 {d['done']}곳 · 새로 채운 항목 {d['added']} · 기존 값과 일치 {d['confirmed']}",
                      f"- 값이 달라 둘 다 표시 {len(d['conflicts'])}건 · 함께 표시(같은 시각의 다른 표기·보완 값) "
                      f"{d.get('also', 0)}건 · 다른 이름 {d['alternate_names']}곳 · 오류 {len(d['errors'])}"]
            lines += (detail_log or []) + [f"- 오류: {x}" for x in d["errors"]]
        if flags.get("add_new") and "new_places" in stats:
            n = stats["new_places"]
            lines += ["", "## TourAPI에만 있는 장소", "", f"- 추가 {len(n['added'])} · 중복 의심 보류 "
                      f"{len(n['held_duplicate_candidates'])} · 제외 {n['skipped']} · 오류 {len(n['errors'])}"]
            lines += [f"- 추가: {x}" for x in n["added"]]
            for h in n["held_duplicate_candidates"]:
                lines.append(f"- 보류 {h['contentid']} {h['title']} ({h['addr']}) ↔ "
                             + ", ".join(f"{c['name']}[{c['slug']}] {c['address']}" for c in h["candidates"]))
            lines += [f"- 오류: {x}" for x in n["errors"]]
        if flags.get("events") and "events" in stats:
            e = stats["events"]
            lines += ["", "## 행사(searchFestival2)", "", f"- 응답 {e['festival_items']} · 추가 {len(e['added'])} · "
                      f"갱신 {len(e['updated'])} · 오류 {len(e['errors'])}"]
            lines += [f"- 추가: {x}" for x in e["added"]] + [f"- 갱신: {x}" for x in e["updated"]]
            lines += [f"- 오류: {x}" for x in e["errors"]]
        lines += ["", "## 미매칭"] + [f"- {x}" for x in stats["unmatched"]]
    (report / "tourapi_bulk.md").write_text("\n".join(lines) + "\n", "utf-8")
    (report / "tourapi_bulk.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", "utf-8")


def _summary(stats: dict, flags: dict) -> dict:
    """The one-line JSON summary on stdout (tools/refresh.py reads it): lists as counts."""
    out = {k: v for k, v in stats.items()
           if k not in ("unmatched", "details", "new_places", "events", "gallery_errors", "list", "geo_kept")}
    out["unmatched"] = len(stats["unmatched"])
    out["geo_kept"] = len(stats.get("geo_kept") or [])
    if "gallery_errors" in stats:
        out["gallery_errors"] = len(stats["gallery_errors"])
    if stats.get("list"):
        out["list"] = {k: v for k, v in stats["list"].items() if k != "by_district"}
    for key, flag in (("details", "details"), ("new_places", "add_new"), ("events", "events")):
        if flags.get(flag) and key in stats:
            out[key] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats[key].items()}
    return out


def squash(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:80]


def run_barrier_free(data_dir: Path, max_calls: int, offline: bool = False, refresh: bool = False,
                     report_dir: Path = Path("reports")) -> dict:
    """--barrier-free: KorWithService2 detailWithTour2 for the published places with a contentid (see the module
    docstring). Writes places.json and reports/tourapi_barrier_free.{md,json}."""
    import datetime as dt
    from pipeline.tourapi import barrier_free_client
    from tools.tourapi_details import BARRIER_FREE, merge_facts, with_facts
    load_dotenv(Path(".env"))
    site_path = data_dir / "site.json"
    if not site_path.exists():
        raise ConfigError(f"{site_path} 없음 — --data에 도시 데이터 폴더(site.json이 있는 곳)를 주세요")
    site = json.loads(site_path.read_text("utf-8"))
    city = city_of(site)
    places_path = data_dir / "places.json"
    places = json.loads(places_path.read_text("utf-8")) if places_path.exists() else []
    api = barrier_free_client(site, os.environ.get("TOURAPI_KEY", ""), data_dir.parent / "cache" / "tourapi",
                              offline=offline, refresh=refresh, max_calls=max_calls)
    today = dt.date.today().isoformat()
    targets = sorted((p for p in places if p.get("status") == "published" and not p.get("duplicate_of")
                      and (p.get("tourapi") or {}).get("contentid")), key=_priority)
    s = {"service": api.base_url, "targets": len(targets), "done": 0, "with_data": 0, "no_data": [],
         "title_mismatch": [], "added": {}, "confirmed": {}, "also": {}, "conflicts": [], "errors": []}
    log: list[str] = []
    try:
        for p in targets:
            cid = str(p["tourapi"]["contentid"])
            start = len(api.fetched_dates)
            try:
                facts = with_facts(retry(api.detail_with_tour, cid))
                if not facts:
                    s["done"] += 1
                    s["no_data"].append(p["name"])
                    continue
                title = (retry(api.detail_common, cid) or {}).get("title")
            except TourAPIStopError:
                raise
            except TourAPIError as err:
                s["errors"].append(f"{p['name']}: {err}")
                continue
            s["done"] += 1
            ours = (p.get("tourapi") or {}).get("title") or p["name"]
            if normalize_name(display_name(title, city)) != normalize_name(display_name(ours, city)):
                s["title_mismatch"].append(f"{p['name']} ({cid}): 무장애 '{title or '없음'}' ≠ TourAPI '{ours}'")
                continue
            s["with_data"] += 1
            before = {k: (p.get("facts") or {}).get(k, "") for k in facts}
            res = merge_facts(p, facts, fetched_on(api, start, today), cid, provider=BARRIER_FREE, city=city)
            for part in ("added", "confirmed", "also"):
                for k in res[part]:
                    s[part][k] = s[part].get(k, 0) + 1
            for part, word in (("added", "추가"), ("confirmed", "일치"), ("also", "함께 표시"), ("conflicts", "값이 다름")):
                for k in res[part]:
                    old = f"기존 '{squash(before[k])}' / " if before[k] else ""
                    log.append(f"- {p['name']} · {k} · {word}: {old}무장애 '{squash(facts[k])}'")
            s["conflicts"] += [f"{p['name']}·{k}" for k in res["conflicts"]]
    except TourAPIStopError as err:
        s["stopped"] = str(err)
    s["live_calls"], s["cache_hits"] = api.live_calls, api.cache_hits
    places_path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    report_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# TourAPI 무장애 여행 정보 ({today})", "",
             f"- 서비스 {s['service']} · 실호출 {s['live_calls']} · 캐시 {s['cache_hits']}",
             f"- 대상(공개·contentid) {s['targets']} · 처리 {s['done']} · 값 있음 {s['with_data']} · 값 없음 {len(s['no_data'])}"
             f" · 제목 불일치 {len(s['title_mismatch'])} · 오류 {len(s['errors'])}",
             f"- 추가 {s['added']} · 일치 {s['confirmed']} · 함께 표시 {s['also']} · 값이 달라 둘 다 표시 {len(s['conflicts'])}"]
    if s.get("stopped"):
        lines.append(f"- 중단: {s['stopped']} (다시 실행하면 캐시로 이어 갑니다)")
    lines += ["", "## 장소별", ""] + (log or ["- 없음"])
    lines += ["", "## 제목 불일치(병합하지 않음)", ""] + [f"- {x}" for x in s["title_mismatch"]]
    lines += ["", "## 오류", ""] + [f"- {x}" for x in s["errors"]]
    lines += ["", "다음: 값이 달라진 장소의 요약·FAQ와 그 값을 인용한 가이드 문장(휠체어 대수 등)을 두 출처로 고쳐 쓰고,"
              " 언어판(data/<도시>/<언어>)이 있으면 바뀐 장소·가이드를 다시 번역한다."]
    (report_dir / "tourapi_barrier_free.md").write_text("\n".join(lines) + "\n", "utf-8")
    (report_dir / "tourapi_barrier_free.json").write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in s.items()}, ensure_ascii=False))
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="도시 데이터 폴더(site.json이 있는 곳, 예: data/daegu)")
    ap.add_argument("--max-calls", type=int, default=120, help="이번 실행의 실호출 상한(캐시는 세지 않음)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="캐시만 쓴다(네트워크 호출 없음)")
    mode.add_argument("--refresh", action="store_true",
                      help="캐시를 무시하고 새로 받는다(응답은 다시 캐시에 저장, 실행당 상한 --max-calls 적용)")
    ap.add_argument("--gallery", action="store_true", help="매칭된 장소마다 detailImage2로 허용 사진 추가(장소당 1회)")
    ap.add_argument("--details", action="store_true",
                    help="매칭된 장소마다 detailCommon2·detailIntro2(관광지·레포츠는 detailInfo2도) — 필드별 출처로 병합")
    ap.add_argument("--add-new", action="store_true",
                    help="TourAPI에만 있는 장소(유형 12·14·28·32·38·39)를 draft/basic으로 추가(중복 의심은 보류, slug 저장)")
    ap.add_argument("--events", action="store_true", help="searchFestival2(올해 1월 1일부터, 모든 쪽)로 행사 갱신")
    ap.add_argument("--district", action="append", default=[], metavar="NAME",
                    help="--details·--add-new 대상을 이 구·군으로 거른다(여러 번 줄 수 있음, site.json districts의 이름)")
    ap.add_argument("--courses", action="store_true",
                    help="여행코스(25)만: 목록·detailCommon2·detailIntro2·detailInfo2 → <data>/tourapi_courses.json "
                         "(places·courses·events는 바꾸지 않음, 다른 수집 옵션과 함께 쓰지 않음)")
    ap.add_argument("--barrier-free", action="store_true",
                    help="무장애 여행 정보(KorWithService2 detailWithTour2)를 공개 장소에 병합 — 이 옵션만 따로 실행")
    ap.add_argument("--nearby-only", action="store_true",
                    help="places.json의 좌표로 주변 장소(nearby)만 다시 계산 — TourAPI 호출 없음, 이 옵션만 따로 실행")
    a = ap.parse_args(argv)
    gather = a.gallery or a.details or a.add_new or a.events or a.courses or a.district
    try:
        if a.nearby_only:
            if gather or a.barrier_free or a.refresh or a.offline:
                raise ConfigError("--nearby-only는 다른 옵션 없이 따로 실행합니다")
            if not (a.data / "places.json").exists():
                raise ConfigError(f"{a.data / 'places.json'} 없음 — 주변을 다시 계산할 장소가 없습니다")
            print(json.dumps(run_nearby_only(a.data), ensure_ascii=False))
            return 0
        if a.barrier_free:
            if gather:
                raise ConfigError("--barrier-free는 다른 보강 옵션(--gallery·--details·--add-new·--events·--courses·"
                                  "--district) 없이 따로 실행합니다")
            run_barrier_free(a.data, a.max_calls, a.offline, a.refresh)
            return 0
        if a.courses:
            if a.gallery or a.details or a.add_new or a.events:
                raise ConfigError("--courses는 --gallery·--details·--add-new·--events와 함께 쓰지 않습니다(따로 실행)")
            stats = run_courses(a.data, a.max_calls, a.offline, a.refresh, a.district)
        else:
            stats = run(a.data, a.max_calls, a.offline, a.gallery, a.details, a.add_new, a.events, a.refresh,
                        a.district)
    except (ConfigError, CityConfigError, TourAPIConfigError) as err:
        print(f"[설정 오류] {err}", file=sys.stderr)
        return 2
    if not stats.get("list_complete"):
        hint = " 캐시가 없으면 TOURAPI_KEY를 두고 --offline 없이 먼저 실행하세요." if a.offline else ""
        what, rep_ = (("tourapi_courses.json을 쓰지 않았습니다", "reports/tourapi_courses.md") if a.courses else
                      ("places.json·events.json은 바꾸지 않았습니다", "reports/tourapi_bulk.md"))
        print(f"[TourAPI 목록 수집 중단] {stats.get('stopped', '')} — {what} ({rep_}).{hint}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
