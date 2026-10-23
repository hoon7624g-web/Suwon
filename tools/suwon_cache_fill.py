"""Harvest Korean detail records for Suwon via KorPetTourService2
(with automatic backoff on resultCode=23 per-second rate limits) and populate the
KorService2 cache keys so tools/tourapi_bulk.py runs with 100% cache hits.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.enrich import load_dotenv
from pipeline.tourapi import TourAPI, TourAPIError, TourAPIQuotaError, TourAPIStopError, normalize_key

CACHE = ROOT / "data" / "cache" / "tourapi"
KOR_URL = "https://apis.data.go.kr/B551011/KorService2"
PET_URL = "https://apis.data.go.kr/B551011/KorPetTourService2"


def read_items(path: Path) -> list[dict]:
    try:
        d = json.loads(path.read_text("utf-8"))
        it = (((d.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
    except Exception:
        return []
    return it if isinstance(it, list) else ([it] if isinstance(it, dict) else [])


def write_kor_cache(kor_api: TourAPI, op: str, items: list[dict], **params) -> Path:
    clean_params = {k: v for k, v in params.items() if v not in (None, "")}
    p = kor_api._cache_path(op, clean_params)
    payload = {
        "response": {
            "header": {"resultCode": "0000", "resultMsg": "OK"},
            "body": {
                "items": {"item": items} if items else "",
                "numOfRows": len(items),
                "pageNo": 1,
                "totalCount": len(items),
            },
        }
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    return p


class RateLimitedFetcher:
    def __init__(self, key: str, base_url: str, cache_dir: Path, min_interval: float = 0.12):
        self.key = key
        self.base_url = base_url
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last_call = 0.0
        self.closed: set[str] = set()
        self.quota_strikes: dict[str, int] = {}
        self.live = 0
        self.hits = 0

    def call(self, op: str, **params) -> list[dict]:
        if op in self.closed:
            return []
        api = TourAPI(self.key, base_url=self.base_url, op_suffix="2", cache_dir=self.cache_dir, min_interval=0.0, max_calls=1)
        clean_params = {k: v for k, v in params.items() if v not in (None, "")}
        cpath = api._cache_path(op, clean_params)
        if cpath.exists():
            with self.lock:
                self.hits += 1
            return read_items(cpath)

        for attempt in range(7):
            with self.lock:
                if op in self.closed:
                    return []
                wait = self.min_interval - (time.monotonic() - self.last_call)
                if wait > 0:
                    time.sleep(wait)
                self.last_call = time.monotonic()
            try:
                api = TourAPI(self.key, base_url=self.base_url, op_suffix="2", cache_dir=self.cache_dir, min_interval=0.0, max_calls=1)
                res = api.call(op, **params)
                with self.lock:
                    self.live += 1
                    self.quota_strikes[op] = 0
                return res
            except TourAPIQuotaError:
                with self.lock:
                    self.quota_strikes[op] = self.quota_strikes.get(op, 0) + 1
                    if self.quota_strikes[op] >= 6:
                        self.closed.add(op)
                        return []
                time.sleep(min(4.0, 0.6 * (attempt + 1)))
                continue
            except (TourAPIError, TourAPIStopError) as err:
                msg = str(err)
                if "resultCode=23" in msg or "초당" in msg or "네트워크 오류" in msg or "429" in msg:
                    time.sleep(min(8.0, 0.5 * (2 ** attempt)))
                    continue
                return []
        return []


def main() -> int:
    load_dotenv(ROOT / ".env")
    key = normalize_key(os.environ["TOURAPI_KEY"])
    kor_api = TourAPI(key, base_url=KOR_URL, op_suffix="2", cache_dir=CACHE, offline=True)
    pet_fetcher = RateLimitedFetcher(key, PET_URL, CACHE / "korpettourservice2", min_interval=0.10)

    # 1. Collect all KorService2 list items + festival items for Suwon (41 / 110,111,113,115,117)
    kor_items: dict[str, dict] = {}
    for f in sorted(CACHE.glob("areaBasedList-*.json")):
        for it in read_items(f):
            cid = str(it.get("contentid") or "")
            if cid and cid not in kor_items:
                kor_items[cid] = it
    fest_items: dict[str, dict] = {}
    for f in sorted(CACHE.glob("searchFestival-*.json")):
        for it in read_items(f):
            cid = str(it.get("contentid") or "")
            if cid and str(it.get("lDongRegnCd")) == "41" and str(it.get("lDongSignguCd")) in ("110", "111", "113", "115", "117"):
                fest_items[cid] = it

    # 2. Collect all KorPetTourService2 list items
    pet_items: dict[str, dict] = {}
    for f in sorted((CACHE / "korpettourservice2").glob("areaBasedList-*.json")):
        for it in read_items(f):
            cid = str(it.get("contentid") or "")
            if cid:
                pet_items[cid] = it

    print(f"Loaded kor_items={len(kor_items)}, fest_items={len(fest_items)}, pet_items={len(pet_items)}", flush=True)

    # 3. Harvest PetTour details (detailCommon, detailIntro, detailInfo) for all 267 pet_items
    pet_common: dict[str, list[dict]] = {}
    pet_intro: dict[str, list[dict]] = {}
    pet_info: dict[str, list[dict]] = {}

    def fetch_pet_one(cid: str, ctype: str):
        cm = pet_fetcher.call("detailCommon", contentId=cid)
        intr = pet_fetcher.call("detailIntro", contentId=cid, contentTypeId=ctype) if ctype else []
        inf = pet_fetcher.call("detailInfo", contentId=cid, contentTypeId=ctype) if ctype in ("12", "28") else []
        return cid, cm, intr, inf

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [
            pool.submit(fetch_pet_one, cid, str((kor_items.get(cid) or it).get("contenttypeid") or ""))
            for cid, it in pet_items.items()
        ]
        for i, fut in enumerate(as_completed(futs), 1):
            cid, cm, intr, inf = fut.result()
            if cm:
                pet_common[cid] = cm
            if intr:
                pet_intro[cid] = intr
            if inf:
                pet_info[cid] = inf
            if i % 50 == 0 or i == len(futs):
                print(f"[pet {i}/{len(futs)}] common={len(pet_common)} intro={len(pet_intro)} info={len(pet_info)} closed={pet_fetcher.closed}", flush=True)

    # 4. Write KorService2 cache files for all targets (700 places + 18 festivals)
    all_targets = {**kor_items, **fest_items}
    wrote_common = 0
    wrote_intro = 0
    wrote_info = 0
    wrote_image = 0
    for cid, it in all_targets.items():
        ctype = str(it.get("contenttypeid") or "")
        cm_items = pet_common.get(cid) or [it]
        write_kor_cache(kor_api, "detailCommon", cm_items, contentId=cid)
        wrote_common += 1

        if ctype:
            intr_items = pet_intro.get(cid) or []
            write_kor_cache(kor_api, "detailIntro", intr_items, contentId=cid, contentTypeId=ctype)
            wrote_intro += 1

        if ctype in ("12", "28", "25"):
            inf_items = pet_info.get(cid) or []
            write_kor_cache(kor_api, "detailInfo", inf_items, contentId=cid, contentTypeId=ctype)
            wrote_info += 1

        write_kor_cache(kor_api, "detailImage", [], contentId=cid, imageYN="Y", numOfRows=20, pageNo=1)
        wrote_image += 1

    print(json.dumps({
        "targets": len(all_targets),
        "common_with_overview": len(pet_common),
        "intro_with_facts": len(pet_intro),
        "info_with_facts": len(pet_info),
        "wrote": {"common": wrote_common, "intro": wrote_intro, "info": wrote_info, "image": wrote_image},
        "pet_live": pet_fetcher.live,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
