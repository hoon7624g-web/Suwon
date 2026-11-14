"""Attach every 한국관광공사 photo (공공누리 제1·3유형) the stored TourAPI answers hold for a place but the site did not use.

    python tools/kto_more_photos.py                 # report what would be added (no change)
    python tools/kto_more_photos.py --apply         # write data/gunsan/places.json

운영자 결정 2026-11-13: first '관광공사 1, 3유형 사진 중 … 사용 안 하고 있는 사진들은 모두 가져와', then the same day
'미사용 사진을 모두 붙일 필요는 없겠다 … 거기서만(홍보포털) 추려와도 엄청나겠는데' — so a place gets them only while it
shows fewer than --fill-to photos (default 7: the opening photo and the six of the photo strip, counting the 군산시
photos it already has), plus the three same-address places' photos. The rest stays out (the TourAPI answers keep them).

Sources, offline (no TourAPI call; the stored answers in data/raw):
  - detailImage answers (tourapi_recollect/korservice2.tar.gz, collect_2026-11-05/tourapi_delta.tar.gz): a place's
    photos by its tourapi.contentid, under the same rule as tourapi_bulk.add_gallery — the photo's name must name the
    place (a provider list sometimes carries another place's photos) — and Type1/Type3 only.
  - 관광사진 갤러리 (PhotoGalleryService1, gallerySearchList in both bundles; 공공누리 제1유형): a photo whose title (without
    a leading '군산 ', spaces ignored) is the place's name, another name, its TourAPI title, or one of the checked
    other names below (GALLERY_ALIASES: same building or shop, different wording).
  - SAME_ADDRESS: three published places whose TourAPI record was never linked although the address is the same; their
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

from tourapi_bulk import normalize_name, photo_title  # noqa: E402

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
    return re.sub(r"\s+", "", re.sub(r"^군산\s*", "", s or ""))


def insert_kto(place: dict, new: list[dict]) -> None:
    """Put new 한국관광공사 photos right after the place's last one (군산시 photos keep their place after them)."""
    imgs = place.setdefault("images", [])
    last = max((i for i, im in enumerate(imgs) if "visitkorea.or.kr" in (im.get("url") or "")), default=-1)
    imgs[last + 1:last + 1] = new


def shown_count(p: dict) -> int:
    """Photos the place page shows now: TourAPI KOGL-1/3 and 군산시 (이용 허락)."""
    return sum(1 for im in p.get("images") or [] if im.get("license") in ("KOGL-1", "KOGL-3", "CITY-PERMIT"))


def run(data: Path, apply: bool, fill_to: int = 7) -> dict:
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
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "gunsan")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fill-to", type=int, default=7, help="add only while the place shows fewer photos than this")
    a = ap.parse_args(argv)
    run(a.data, a.apply, a.fill_to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
