"""Attach every 한국관광공사 photo (공공누리 제1·3유형) the stored TourAPI answers hold for a place but the site did not use.

    python tools/kto_more_photos.py --data data/<region>                 # report what would be added (no change)
    python tools/kto_more_photos.py --data data/<region> --fill-to 12 --apply   # write places.json

운영자 결정 (the first site, 2026-11-13; every region 2026-11-14 '최대한 사진들 많이 끌어와서 … 아주 풍성해지도록'):
a place gets the unused 한국관광공사 photos only while it shows fewer than --fill-to photos (counting the city's own
photos it already has), plus the same-address places' photos. The rest stays out (the TourAPI answers keep them).

Sources, offline (no TourAPI call; the stored answers in data/raw):
  - detailImage answers (tourapi_recollect/korservice2.tar.gz, collect_2026-11-05/tourapi_delta.tar.gz): a place's
    photos by its tourapi.contentid, under the same rule as tourapi_bulk.add_gallery — the photo's name must name the
    place (a provider list sometimes carries another place's photos) — and Type1/Type3 only.
  - 관광사진 갤러리 (PhotoGalleryService1, gallerySearchList in both bundles; 공공누리 제1유형): a photo whose title (without
    the region's name in front, spaces ignored) is the place's name, another name, its TourAPI title, or one of the checked
    other names below (GALLERY_ALIASES: same building or shop, different wording).
  - SAME_ADDRESS (data/<region>/kto_more.json): published places whose TourAPI record was never linked although the address is the same; their
    list photo (and their detailImage photos under that record's title).
New photos go after the place's last 한국관광공사 photo (the lead and the home's photo slots keep their place).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from pipeline.city import of as city_of  # noqa: E402
from tourapi_bulk import normalize_name  # noqa: E402
from tourapi_bulk import photo_title as _photo_title  # noqa: E402

CITY = None     # set by run(): the region's City (its name prefix, photo titles)
PREFIX = ""     # the region's short name, dropped in front of a gallery title


def photo_title(title):
    return _photo_title(title, CITY)

def bundles(data: Path) -> list[Path]:
    """The stored TourAPI answers of the region: every .tar.gz under data/raw/<region>/ (the recollect and delta
    bundles; any layout), oldest name first."""
    return sorted((ROOT / "data" / "raw" / Path(data).name).rglob("*.tar.gz"))


LIC = {"Type1": "KOGL-1", "Type3": "KOGL-3"}
# region settings: data/<region>/kto_more.json — gallery_aliases {gallery title (normalized): place name} (the same place
# under another wording, checked against the photo's shooting place and the place's address) and same_address
# {published place name: TourAPI contentid} (a record at the same address that was never linked)
def region_settings(data: Path) -> tuple[dict, dict]:
    f = Path(data) / "kto_more.json"
    cfg = json.loads(f.read_text("utf-8")) if f.exists() else {}
    return cfg.get("gallery_aliases") or {}, cfg.get("same_address") or {}


def https(url: str) -> str:
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def items(doc) -> list[dict]:
    try:
        it = doc["response"]["body"]["items"]
    except (KeyError, TypeError):
        return []
    if not it:
        return []
    it = it.get("item") if isinstance(it, dict) else it
    return it if isinstance(it, list) else [it]


def load_answers(data: Path) -> tuple[dict, dict, dict]:
    """(detail images {contentid: {url: (code, imgname)}}, list rows {contentid: row}, gallery {id: row})."""
    det: dict[str, dict] = {}
    rows: dict[str, dict] = {}
    gal: dict[str, dict] = {}
    for b in bundles(data):
        if not b.exists():
            continue
        with tarfile.open(b) as tf:
            for m in tf.getmembers():
                name = m.name.rsplit("/", 1)[-1]
                if not (m.isfile() and name.endswith(".json")):
                    continue
                op = name.split("-", 1)[0]
                if op not in ("detailImage", "gallerySearchList", "areaBasedList", "areaBasedSyncList"):
                    continue
                try:
                    doc = json.load(tf.extractfile(m))
                except ValueError:
                    continue
                for it in items(doc):
                    if op == "detailImage" and it.get("contentid") and it.get("originimgurl"):
                        det.setdefault(str(it["contentid"]), {})[https(it["originimgurl"])] = \
                            (it.get("cpyrhtDivCd") or "", it.get("imgname") or "")
                    elif op == "gallerySearchList" and it.get("galWebImageUrl"):
                        gal[str(it.get("galContentId"))] = it
                    elif op.startswith("areaBased") and it.get("contentid"):
                        old = rows.get(str(it["contentid"]))
                        if not old or (it.get("modifiedtime") or "") > (old.get("modifiedtime") or ""):
                            rows[str(it["contentid"])] = it
    return det, rows, gal


def norm(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    return s[len(PREFIX):] if PREFIX and s.startswith(PREFIX) and len(s) > len(PREFIX) + 1 else s


def insert_kto(place: dict, new: list[dict]) -> None:
    """Put new 한국관광공사 photos right after the place's last one (the city's photos keep their place after them)."""
    imgs = place.setdefault("images", [])
    last = max((i for i, im in enumerate(imgs) if "visitkorea.or.kr" in (im.get("url") or "")), default=-1)
    imgs[last + 1:last + 1] = new


def shown_count(p: dict) -> int:
    """Photos the place page shows now: TourAPI KOGL-1/3 and the city's own (CITY-PERMIT)."""
    return sum(1 for im in p.get("images") or [] if im.get("license") in ("KOGL-1", "KOGL-3", "CITY-PERMIT"))


def run(data: Path, apply: bool, fill_to: int = 7) -> dict:
    global CITY, PREFIX
    site = json.loads((data / "site.json").read_text("utf-8"))
    CITY, PREFIX = city_of(site), (site.get("region") or "").strip()
    path = data / "places.json"
    places = json.loads(path.read_text("utf-8"))
    det, rows, gal = load_answers(data)
    GALLERY_ALIASES, SAME_ADDRESS = region_settings(data)
    have = {im["url"] for p in places for im in p.get("images") or [] if im.get("url")}
    by_norm: dict[str, dict] = {}
    for p in sorted(places, key=lambda p: p.get("status") != "published"):   # a published place first
        for n in [p["name"], *(p.get("aliases") or []), (p.get("tourapi") or {}).get("title") or ""]:
            if n:
                by_norm.setdefault(norm(n), p)
    by_name = {p["name"]: p for p in places if p.get("status") == "published"}
    report = {"detail": 0, "detail_places": 0, "gallery": 0, "gallery_places": 0, "same_address": 0,
              "detail_name_miss": 0, "gallery_unmatched": 0}
    adds: dict[str, list[dict]] = {}

    def add(p: dict, im: dict, always: bool = False) -> bool:
        if im["url"] in have:
            return False
        if not always and shown_count(p) + len(adds.get(p["id"], [])) >= fill_to:
            return False
        have.add(im["url"])
        adds.setdefault(p["id"], []).append(im)
        return True

    # 1. detailImage photos of linked places (and of the three same-address records)
    for p in places:
        cids = []
        t = p.get("tourapi") or {}
        if t.get("contentid"):
            cids.append((str(t["contentid"]), t.get("title") or p["name"]))
        if p.get("status") == "published" and p["name"] in SAME_ADDRESS:
            cid = SAME_ADDRESS[p["name"]]
            row = rows.get(cid) or {}
            cids.append((cid, row.get("title") or p["name"]))
            first = https(row.get("firstimage") or "")
            if first and row.get("cpyrhtDivCd") in LIC and add(p, always=True, im={
                    "url": first, "alt": photo_title(row.get("title")) or p["name"], "credit": "한국관광공사",
                    "license": LIC[row["cpyrhtDivCd"]], "source": "TourAPI", "tourapi_contentid": cid,
                    "match_basis": "same_address"}):
                report["same_address"] += 1
        n0 = report["detail"]
        for cid, title in cids:
            key = normalize_name(photo_title(title))[:6]
            for url, (code, imgname) in (det.get(cid) or {}).items():
                if code not in LIC:
                    continue
                if len(key) < 2 or key not in normalize_name(imgname):
                    report["detail_name_miss"] += 1
                    continue
                if add(p, {"url": url, "alt": photo_title(title) or p["name"], "credit": "한국관광공사",
                           "license": LIC[code], "source": "TourAPI"}):
                    report["detail"] += 1
        report["detail_places"] += report["detail"] > n0

    # 2. the TourAPI photo gallery (KOGL-1)
    gplaces = set()
    for g in sorted(gal.values(), key=lambda g: (g.get("galCreatedtime") or ""), reverse=True):
        title = norm(g.get("galTitle"))
        p = by_norm.get(title) or by_name.get(GALLERY_ALIASES.get(title, ""))
        if p and p.get("status") != "published" and p.get("duplicate_of"):   # a duplicate draft: its published twin
            p = next((x for x in places if x["id"] == p["duplicate_of"]), p)
        if not p:
            report["gallery_unmatched"] += 1
            continue
        taken = g.get("galPhotographyMonth") or ""
        if add(p, {"url": https(g["galWebImageUrl"]), "alt": p["name"], "credit": "한국관광공사", "license": "KOGL-1",
                   "source": "TourAPI", "service": "PhotoGalleryService1", "gallery_id": str(g.get("galContentId")),
                   "photographer": g.get("galPhotographer") or "",
                   "taken": f"{taken[:4]}-{taken[4:6]}" if len(taken) >= 6 else ""}):
            report["gallery"] += 1
            gplaces.add(p["id"])
    report["gallery_places"] = len(gplaces)

    by_id = {p["id"]: p for p in places}
    shown = {pid: sum(1 for im in ims) for pid, ims in adds.items() if by_id[pid].get("status") == "published"}
    report["published_places"] = len(shown)
    report["published_photos"] = sum(shown.values())
    if apply:
        for pid, ims in adds.items():
            insert_kto(by_id[pid], ims)
        path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fill-to", type=int, default=7, help="add only while the place shows fewer photos than this")
    a = ap.parse_args(argv)
    run(a.data, a.apply, a.fill_to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
