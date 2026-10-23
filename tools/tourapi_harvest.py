"""TourAPI raw harvest: fill the response cache for every TourAPI service this key may use, in parallel, and keep it.

    python tools/tourapi_harvest.py --data data/daegu                       # every service below, inside the caps
    python tools/tourapi_harvest.py --data data/daegu --service kor --service eng
    python tools/tourapi_harvest.py --data data/daegu --pack                # cache -> data/raw/<city>/tourapi/*.tar.gz
    python tools/tourapi_harvest.py --data data/daegu --unpack              # data/raw/<city>/tourapi/*.tar.gz -> cache

Why: the development key allows about 1,000 calls per operation per day and the container's cache (data/cache/,
not committed) is lost with the container. This tool only fetches and stores answers; it changes no site data.
The tools that merge (tools/tourapi_bulk.py, later the language and barrier-free tools) then read the same cache,
so their calls are cache hits. Every call goes through pipeline.tourapi.TourAPI with the same operation names and
parameters those tools use, so the cache keys match.

Services (--service, repeatable; default all)
  kor      KorService2 — what tools/tourapi_bulk.py asks for: ldongCode2, areaBasedList2 per 구·군 and content type
           (12·14·28·38·32·39, and 25), searchFestival2 from 1 January, then for every listed item not yet in
           places.json and every place (published first): detailCommon2 · detailIntro2 · detailInfo2 (all types) ·
           detailImage2. Also areaBasedSyncList2 for the 시·도 (showflag 0 = the provider no longer shows the item)
           and lclsSystmCode2 (the classification names).
  eng jpn chs cht ger fre spn rus
           EngService2 … RusService2 (the eight language services, pipeline: the language versions): areaBasedList2 for
           the 시·도 (every page), searchFestival2 from 1 January, then per item detailCommon2 · detailIntro2 ·
           detailInfo2 · detailImage2.
  bf       KorWithService2 (무장애 여행): areaBasedList2 for the 시·도, then detailWithTour2 for every listed item and
           every place of places.json (published first), and detailCommon2 where it answered — cache folder
           barrier_free, as tools/tourapi_bulk.py --barrier-free in the 군산 engine.
  photo    PhotoGalleryService1 (관광사진): gallerySearchList1 for the city's name and each 군 name, every page.
           Metadata only (title, place, photographer, month, image URL); no image is downloaded.
  pet      KorPetTourService2 (반려동물 동반여행): areaBasedList2 for the 시·도, then detailPetTour2 per item.
  durunubi Durunubi (두루누비 걷기·자전거길): courseList and routeList, every page (nationwide; the merge keeps the
           city's courses by their 시·군 field).
  camping  GoCamping (고캠핑): basedList, every page (nationwide, about 3,100), then imageList for the camps whose
           도 is the city's 시·도.

Caps: --max-calls is per operation of a service (default 950, under the daily 1,000). A quota answer from the provider
stops that operation only; the others go on. Network resets through the proxy are retried with back-off.
--workers: requests in flight at once over all services (default 6).

--pack writes one tar.gz per cache folder to data/raw/<city>/tourapi/ (committed) and a manifest; --unpack restores
them, so a new container continues from the stored answers instead of spending the day's quota again.
The key is read from TOURAPI_KEY (environment or .env) and never printed; errors show the provider message with the
key masked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tarfile
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.city import of as city_of
from pipeline.enrich import load_dotenv
from pipeline.tourapi import (TourAPI, TourAPIError, TourAPIQuotaError, TourAPIStopError, fetch_festivals,
                              from_site_config, list_scope, normalize_key, redact, resolve_ldong)

ROOT = Path(__file__).resolve().parents[1]
B = "https://apis.data.go.kr/B551011/"
LANG = {"eng": "EngService2", "jpn": "JpnService2", "chs": "ChsService2", "cht": "ChtService2",
        "ger": "GerService2", "fre": "FreService2", "spn": "SpnService2", "rus": "RusService2"}
KOR_TYPES = ("12", "14", "28", "38", "32", "39", "25")
OTHER = {"bf": ("KorWithService2", "2"), "photo": ("PhotoGalleryService1", "1"), "pet": ("KorPetTourService2", "2"),
         "durunubi": ("Durunubi", ""), "camping": ("GoCamping", "")}
ALL = ("kor", *LANG, *OTHER)
FOLDER = {"kor": "", "bf": "barrier_free", "photo": "photo_gallery", "pet": "korpettourservice2",
          "durunubi": "durunubi", "camping": "gocamping", **{k: v.lower() for k, v in LANG.items()}}


class Harvest:
    """Calls for one run: a fresh client per call (the client keeps per-instance counters), a shared cap per
    (service, operation), and a set of operations the provider has closed for today."""

    def __init__(self, site: dict, key: str, cache: Path, max_calls: int, workers: int):
        self.site, self.key, self.cache, self.max_calls = site, key, cache, max_calls
        self.lock = threading.Lock()
        self.live = Counter()
        self.hits = Counter()
        self.errors = defaultdict(list)
        self.closed: dict[tuple, str] = {}
        self.pool = ThreadPoolExecutor(max_workers=workers)

    def client(self, svc: str) -> TourAPI:
        if svc == "kor":
            api = from_site_config(self.site, self.key, self.cache, max_calls=1)
        else:
            name, suffix = OTHER.get(svc) or (LANG[svc], "2")
            api = TourAPI(self.key, base_url=B + name, op_suffix=suffix,
                          mobile_app=(self.site.get("tourapi") or {}).get("mobile_app") or "TravelSite",
                          cache_dir=self.cache / FOLDER[svc] if FOLDER[svc] else self.cache, max_calls=1)
        api.timeout = 30
        return api

    def call(self, svc: str, op: str, **params) -> list[dict] | None:
        """One answer (cache first). None when the operation is closed or capped, or the call failed."""
        k = (svc, op)
        if k in self.closed:
            return None
        api = self.client(svc)
        if api._cache_path(op, {p: v for p, v in params.items() if v not in (None, "")}).exists():
            with self.lock:
                self.hits[k] += 1
            return api.call(op, **params)
        with self.lock:
            if self.live[k] >= self.max_calls:
                self.closed.setdefault(k, f"이번 실행 상한 {self.max_calls}회")
                return None
            self.live[k] += 1
        for attempt in range(7):
            try:
                return api.call(op, **params)
            except TourAPIQuotaError as err:
                self.closed.setdefault(k, str(err))
                return None
            except TourAPIStopError:
                api = self.client(svc)  # per-client cap of 1: a retry needs a new client
                continue
            except TourAPIError as err:
                if ("네트워크 오류" in str(err) or "resultCode=23" in str(err) or "초당" in str(err)) and attempt < 6:
                    time.sleep(min(20, 0.8 * 2 ** attempt))
                    api = self.client(svc)
                    continue
                with self.lock:
                    self.errors[k].append(f"{params}: {err}"[:300])
                return None
        return None

    def run(self, jobs: list[tuple]) -> list:
        """jobs: (svc, op, params) — run in parallel, results in order."""
        futs = [self.pool.submit(self.call, s, o, **p) for s, o, p in jobs]
        return [f.result() for f in futs]


def pages(h: Harvest, svc: str, op: str, rows: int, **params) -> list[dict]:
    """Every page of a list (a short page or one adding no new contentid ends it)."""
    out, seen, page = [], set(), 1
    while True:
        got = h.call(svc, op, numOfRows=rows, pageNo=page, **params)
        if got is None:
            break
        ids = [str(it.get("contentid") or it.get("galContentId") or it.get("contentId")
                   or json.dumps(it, sort_keys=True, ensure_ascii=False)) for it in got]
        new = [it for it, i in zip(got, ids) if i not in seen]
        seen.update(ids)
        out += new
        if len(got) < rows or not new:
            break
        page += 1
    return out


def details(h: Harvest, svc: str, items: list[tuple[str, str]]) -> None:
    """detailCommon2 · detailIntro2 · detailInfo2 · detailImage2 for (contentid, contenttypeid) pairs, in parallel,
    with the parameters pipeline.tourapi.TourAPI's methods use (cache keys shared with the merging tools)."""
    jobs = []
    for cid, ctype in items:
        jobs.append((svc, "detailCommon", {"contentId": cid}))
        if ctype:
            jobs.append((svc, "detailIntro", {"contentId": cid, "contentTypeId": ctype}))
            jobs.append((svc, "detailInfo", {"contentId": cid, "contentTypeId": ctype}))
        jobs.append((svc, "detailImage", {"contentId": cid, "imageYN": "Y", "numOfRows": 20, "pageNo": 1}))
    h.run(jobs)


def harvest_kor(h: Harvest, city, places: list[dict], year: str) -> dict:
    api = h.client("kor")
    api.max_calls = 10
    ldong = resolve_ldong(api, city, call=lambda fn, *a, **k: _retry(fn, *a, **k))
    scope = list_scope(city)
    areas = [(None, "")] if scope == "region" else list(ldong.signgu)
    if scope != "region" and getattr(ldong, "locality_cd", ""):
        areas.append((ldong.locality_cd, city.locality))
    items: dict[str, dict] = {}
    for code, _name in areas:
        for ctype in KOR_TYPES:
            for it in pages(h, "kor", "areaBasedList", 200, lDongRegnCd=ldong.regn_cd, lDongSignguCd=code,
                            contentTypeId=ctype, arrange="A"):
                items.setdefault(str(it["contentid"]), it)
    # sync list: every item with its showflag (0 = no longer shown by the provider — a place to re-check), and the
    # provider's classification table (lcls codes -> names)
    sync = []
    for code, _name in areas:
        sync += pages(h, "kor", "areaBasedSyncList", 200, lDongRegnCd=ldong.regn_cd, lDongSignguCd=code, arrange="A")
    lcls = pages(h, "kor", "lclsSystmCode", 1000, lclsSystmListYn="Y")
    fest_api = h.client("kor")
    fest_api.max_calls = 40
    try:
        fest = fetch_festivals(fest_api, f"{year}0101", ldong, call=lambda fn, *a, **k: _retry(fn, *a, **k))
    except TourAPIError as err:
        h.errors[("kor", "searchFestival")].append(str(err)[:300])
        fest = []
    with h.lock:
        h.live[("kor", "searchFestival")] += fest_api.live_calls
    for it in fest:
        items.setdefault(str(it["contentid"]), it)
    # new items and events first (nothing of them is stored yet), then our places, published first
    have = {str((p.get("tourapi") or {}).get("contentid")): p for p in places if (p.get("tourapi") or {}).get("contentid")}
    pairs = {cid: str(it.get("contenttypeid") or "") for cid, it in items.items() if cid not in have}
    order = sorted(have.values(), key=lambda p: (p.get("status") != "published", p.get("tier") != "full", p.get("name", "")))
    for p in order:
        pairs.setdefault(str(p["tourapi"]["contentid"]), str(p["tourapi"].get("contenttypeid") or ""))
    details(h, "kor", list(pairs.items()))
    return {"listed": len(items), "festivals": len(fest), "detailed": len(pairs), "sync_items": len(sync),
            "sync_hidden": sum(1 for it in sync if str(it.get("showflag")) == "0"), "lcls_codes": len(lcls)}


def _retry(fn, *args, **kwargs):
    for attempt in range(7):
        try:
            return fn(*args, **kwargs)
        except TourAPIStopError:
            raise
        except TourAPIError as err:
            if "네트워크 오류" not in str(err) or attempt == 6:
                raise
            time.sleep(min(40, 3 * 2 ** attempt))


def resolve_city_ldong(h: Harvest, city):
    api = h.client("kor")
    api.max_calls = 10
    return resolve_ldong(api, city, call=_retry)


def _signgu_codes(ldong) -> list[str | None]:
    if ldong.whole_region:
        return [None]
    codes = [c for c, _ in ldong.signgu]
    if getattr(ldong, "locality_cd", "") and ldong.locality_cd not in codes:
        codes.append(ldong.locality_cd)
    return codes


def harvest_lang(h: Harvest, svc: str, ldong, year: str) -> dict:
    regn = ldong.regn_cd
    items: dict[str, dict] = {}
    fest: list[dict] = []
    for signgu in _signgu_codes(ldong):
        for it in pages(h, svc, "areaBasedList", 200, lDongRegnCd=regn, lDongSignguCd=signgu, arrange="A"):
            items.setdefault(str(it["contentid"]), it)
        for it in pages(h, svc, "searchFestival", 100, eventStartDate=f"{year}0101", lDongRegnCd=regn,
                        lDongSignguCd=signgu, arrange="A"):
            fest.append(it)
            items.setdefault(str(it["contentid"]), it)
    details(h, svc, [(cid, str(it.get("contenttypeid") or "")) for cid, it in items.items()])
    return {"listed": len(items), "festivals": len(fest)}


def harvest_bf(h: Harvest, ldong, places: list[dict]) -> dict:
    regn = ldong.regn_cd
    items = []
    for signgu in _signgu_codes(ldong):
        items += pages(h, "bf", "areaBasedList", 200, lDongRegnCd=regn, lDongSignguCd=signgu, arrange="A")
    cids = list(dict.fromkeys([str(it["contentid"]) for it in items] + [
        str(p["tourapi"]["contentid"]) for p in sorted(places, key=lambda p: p.get("status") != "published")
        if (p.get("tourapi") or {}).get("contentid") and not p.get("duplicate_of")]))
    res = h.run([("bf", "detailWithTour", {"contentId": c}) for c in cids])
    # the merge checks the title on the same service (detailCommon2) for every answer with data
    h.run([("bf", "detailCommon", {"contentId": c}) for c, r in zip(cids, res) if r])
    return {"listed": len(items), "asked": len(cids), "with_data": sum(1 for r in res if r)}


def harvest_photo(h: Harvest, city) -> dict:
    extra = (h.site.get("tourapi") or {}).get("photo_keywords") or []
    words = [city.region, *[d for d in (h.site.get("districts") or []) if d.endswith("군")], *extra]
    words += [d[:-1] for d in (h.site.get("districts") or []) if d.endswith("군")]  # 군 names bare, as photos are titled
    seen, n = set(), 0
    for w in dict.fromkeys(words):
        for it in pages(h, "photo", "gallerySearchList", 100, keyword=w, arrange="A"):
            gid = str(it.get("galContentId"))
            if gid not in seen:
                seen.add(gid)
                n += 1
    return {"keywords": list(dict.fromkeys(words)), "photos": n}


def harvest_pet(h: Harvest, ldong) -> dict:
    regn = ldong.regn_cd
    items = []
    for signgu in _signgu_codes(ldong):
        items += pages(h, "pet", "areaBasedList", 200, lDongRegnCd=regn, lDongSignguCd=signgu, arrange="A")
    seen_cids = list(dict.fromkeys(str(it["contentid"]) for it in items if it.get("contentid")))
    res = h.run([("pet", "detailPetTour", {"contentId": cid}) for cid in seen_cids])
    return {"listed": len(seen_cids), "with_data": sum(1 for r in res if r)}


def harvest_durunubi(h: Harvest) -> dict:
    courses = pages(h, "durunubi", "courseList", 100)
    routes = pages(h, "durunubi", "routeList", 100)
    region = h.site.get("region") or ""
    mine = [c for c in courses if region and region in str(c.get("sigun") or "")]
    return {"courses": len(courses), "routes": len(routes), "in_city": len(mine)}


def harvest_camping(h: Harvest) -> dict:
    camps = pages(h, "camping", "basedList", 100)
    admin = h.site.get("region_admin") or ""
    region = h.site.get("region") or ""
    locality = h.site.get("locality") or ""
    mine = [c for c in camps if str(c.get("doNm") or "") in {admin, f"{region}시"} and admin
            and (not locality or locality == admin or region in str(c.get("sigunguNm") or ""))]
    h.run([("camping", "imageList", {"contentId": str(c.get("contentId")), "numOfRows": 50, "pageNo": 1})
           for c in mine if c.get("contentId")])
    return {"nationwide": len(camps), "in_city": len(mine)}


def pack(data: Path, cache: Path) -> dict:
    city_dir = data.name
    out = ROOT / "data" / "raw" / city_dir / "tourapi"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"about": "TourAPI 원응답 캐시 묶음 — tools/tourapi_harvest.py --unpack으로 data/cache/tourapi/에 되돌린다. "
                         "사실 확인·병합 도구의 입력이며 화면에 그대로 싣지 않는다(overview 포함).",
                "packed_on": dt.date.today().isoformat(), "archives": {}}
    for svc, folder in FOLDER.items():
        src = cache / folder if folder else cache
        files = sorted(p for p in src.glob("*.json")) if src.exists() else []
        if not files:
            continue
        name = f"{folder or 'korservice2'}.tar.gz"
        with tarfile.open(out / name, "w:gz", compresslevel=9) as tar:
            for f in files:
                tar.add(f, arcname=(f"{folder}/" if folder else "") + f.name)
        ops = Counter(f.name.split("-")[0] for f in files)
        manifest["archives"][name] = {"service": svc, "files": len(files), "by_operation": dict(sorted(ops.items())),
                                      "newest": dt.date.fromtimestamp(max(f.stat().st_mtime for f in files)).isoformat()}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return manifest


def unpack(data: Path, cache: Path) -> int:
    src = ROOT / "data" / "raw" / data.name / "tourapi"
    cache.mkdir(parents=True, exist_ok=True)
    n = 0
    for arc in sorted(src.glob("*.tar.gz")):
        with tarfile.open(arc, "r:gz") as tar:
            members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".json") and ".." not in m.name]
            for m in members:
                target = cache / m.name
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as fh:
                    target.write_bytes(fh.read())
                os.utime(target, (m.mtime, m.mtime))  # the fetch date is the file date (checked_at)
                n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--service", action="append", choices=ALL)
    ap.add_argument("--max-calls", type=int, default=950)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--pack", action="store_true")
    ap.add_argument("--unpack", action="store_true")
    a = ap.parse_args(argv)
    cache = ROOT / "data" / "cache" / "tourapi"
    if a.pack:
        print(json.dumps(pack(a.data, cache), ensure_ascii=False, indent=1))
        return 0
    if a.unpack:
        print(f"restored {unpack(a.data, cache)} files")
        return 0
    load_dotenv(ROOT / ".env")
    key = normalize_key(os.environ.get("TOURAPI_KEY", ""))
    if not key:
        print("TOURAPI_KEY가 없습니다 (.env 또는 환경 변수)")
        return 2
    site = json.loads((a.data / "site.json").read_text("utf-8"))
    city = city_of(site)
    places = json.loads((a.data / "places.json").read_text("utf-8"))
    year = str(dt.date.today().year)
    h = Harvest(site, key, cache, a.max_calls, a.workers)
    services = a.service or list(ALL)
    summary: dict = {}
    t0 = time.monotonic()
    ldong = resolve_city_ldong(h, city)

    def one(svc):
        if svc == "kor":
            return harvest_kor(h, city, places, year)
        if svc in LANG:
            return harvest_lang(h, svc, ldong, year)
        if svc == "bf":
            return harvest_bf(h, ldong, places)
        if svc == "pet":
            return harvest_pet(h, ldong)
        if svc == "durunubi":
            return harvest_durunubi(h)
        if svc == "camping":
            return harvest_camping(h)
        return harvest_photo(h, city)

    with ThreadPoolExecutor(max_workers=len(services)) as outer:
        futs = {outer.submit(one, s): s for s in services}
        for f in as_completed(futs):
            s = futs[f]
            try:
                summary[s] = f.result()
            except Exception as err:  # one service failing must not stop the others
                summary[s] = {"error": redact(f"{type(err).__name__}: {err}", key)[:300]}
            print(f"[{time.strftime('%H:%M:%S')}] {s} done: {summary[s]}", flush=True)
    h.pool.shutdown()
    report = {"date": dt.date.today().isoformat(), "minutes": round((time.monotonic() - t0) / 60, 1),
              "services": summary,
              "live_calls": {f"{s}.{o}": n for (s, o), n in sorted(h.live.items())},
              "cache_hits": {f"{s}.{o}": n for (s, o), n in sorted(h.hits.items())},
              "closed": {f"{s}.{o}": redact(m, key) for (s, o), m in h.closed.items()},
              "errors": {f"{s}.{o}": [redact(e, key) for e in v[:5]] + ([f"… {len(v) - 5} more"] if len(v) > 5 else [])
                         for (s, o), v in h.errors.items()}}
    Path("reports").mkdir(exist_ok=True)
    name = "tourapi_harvest" + ("" if not a.service else "_" + "_".join(a.service))
    Path(f"reports/{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({k: report[k] for k in ("minutes", "services", "closed")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
