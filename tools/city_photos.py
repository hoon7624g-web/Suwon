"""시청 사진 — the city government's own photos on a ○○각 site, used with its permission: mark, fetch and place them.

    python tools/city_photos.py permit [--apply]   # photos already in places.json that sit on the city's servers
    python tools/city_photos.py fetch              # their originals → data/cache/city-photos (paced, retried)
    python tools/city_photos.py attach [--apply]   # photos an adapter found (data/<region>/portal.json) → places

운영자 결정: 군산각 2026-11-13 '군산시 허락은 받았으니까 아래 2개 출처의 모든 사진들 추가해서 적절한 장소들에 모두 배치해
(사이즈 조절 등 편집 가능)'; 지역 ○○각 20곳 2026-11-14 '모두 허락 받았어. 전수조사하고, 최대한 사진들 많이 끌어와서 …
모든 사이트가 아주 풍성해지도록'.

Settings: data/<region>/site.json city_photos — credit (the city's name as the photo credit, e.g. '군산시'), credit_intl
(that name in the other versions' languages), permit_at, hosts (the servers the city's photos are on), sources
({name, url}: the city's sites the photos come from, linked under the place page's 사진 더 보기 and on /about/).

permit: every photo of places.json on one of those hosts gets license CITY-PERMIT, credit <city>, source (the site it
came from), page (the place's page there) and permit_at. A duplicate draft's photos (duplicate_of) are copied to its
published twin. Pages never load the city's files: the build shows a city photo only from its same-origin WebP/AVIF
copies (tools/kogl1_media.py, pipeline/media.attach drops one without them).

fetch: the originals of the published places' city photos (camera files up to several MB; city servers are slow and
reset bursts — a few requests at once, a pause after each, retries with a growing wait) → data/cache/city-photos.

attach: data/<region>/portal.json — {"source": <name of the site the photos come from>, "posts": [{id, title, date,
places: [place id], page (the photo's page there), alt, opens_page (true: pressing a photo opens that page, as a photo
portal post; false: our larger copy), photos: [{url}]}]} — made by an adapter for the city's site (tools/city_portal.py
for the 'uprbank' photo portals; a region writes its own for another system). Each photo goes after the place's other
photos (한국관광공사 first on the page, then the city's in stored order).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "city-photos"
PORTAL_CACHE = ROOT / "data" / "cache" / "city-portal"
UA = "Mozilla/5.0 (compatible; webforai-photo-sync/1.0)"
LICENSE = "CITY-PERMIT"


def settings(data: Path) -> dict:
    site = json.loads((data / "site.json").read_text("utf-8"))
    cfg = site.get("city_photos") or {}
    if not cfg.get("credit") or not cfg.get("hosts"):
        raise SystemExit(f"{data}/site.json에 city_photos(credit·hosts)가 없습니다 — 시청 이름과 사진 서버를 먼저 적는다")
    return cfg


def load(data: Path) -> list[dict]:
    return json.loads((data / "places.json").read_text("utf-8"))


def save(data: Path, places: list[dict]) -> None:
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")


def host_of(url: str) -> str:
    return urlsplit(url or "").netloc.lower()


def is_city(url: str, hosts) -> bool:
    return host_of(url) in {h.lower() for h in hosts}


def cache_candidates(url: str) -> list[Path]:
    """Where a city original may be cached: <host>__<path with __> (any region), and the names the first Gunsan run
    used (the path after /upload_data/ or after the host, the file name alone)."""
    parts = urlsplit(url)
    path = parts.path.lstrip("/")
    names = [f"{parts.netloc}__{path.replace('/', '__')}"]
    if "upload_data/" in path:
        names.append(path.split("upload_data/", 1)[1].replace("/", "__"))
    names += [path.replace("/", "__"), path.rsplit("/", 1)[-1]]
    return [d / n for d in (CACHE, PORTAL_CACHE) for n in dict.fromkeys(names) if n]


def cached(url: str) -> Path | None:
    return next((p for p in cache_candidates(url) if p.exists() and p.stat().st_size), None)


def permit(data: Path, apply: bool) -> dict:
    cfg = settings(data)
    places = load(data)
    by_id = {p["id"]: p for p in places}
    first_source = ((cfg.get("sources") or [{}])[0]).get("name") or cfg["credit"]
    marked = copied = 0
    for p in places:
        page = (p.get("official") or {}).get("source_url") or (p.get("original") or {}).get("source_url") or ""
        for im in p.get("images") or []:
            if not is_city(im.get("url"), cfg["hosts"]):
                continue
            if im.get("license") != LICENSE:
                marked += 1
            src = im.get("source") if im.get("source") not in (None, "", "원문") else (im.get("credit") or first_source)
            if src == cfg["credit"]:
                src = first_source
            im.update({"credit": cfg["credit"], "license": LICENSE, "source": src, "page": im.get("page") or page,
                       "permit_at": cfg.get("permit_at") or im.get("permit_at") or ""})
    for p in places:   # a duplicate draft's photos to its published twin (after the twin's own)
        twin = by_id.get(p.get("duplicate_of") or "")
        if not twin or p.get("status") == "published" or twin.get("status") != "published":
            continue
        have = {im["url"] for im in twin.get("images") or []}
        for im in p.get("images") or []:
            if is_city(im.get("url"), cfg["hosts"]) and im["url"] not in have:
                twin.setdefault("images", []).append({**im, "alt": twin["name"]})
                have.add(im["url"])
                copied += 1
    pub = [p for p in places if p.get("status") == "published"]
    report = {"marked": marked, "copied_to_twin": copied,
              "published_photos": sum(1 for p in pub for im in p.get("images") or [] if im.get("license") == LICENSE),
              "published_places": sum(1 for p in pub if any(im.get("license") == LICENSE for im in p.get("images") or [])),
              "draft_photos": sum(1 for p in places if p.get("status") != "published"
                                  for im in p.get("images") or [] if im.get("license") == LICENSE)}
    if apply:
        save(data, places)
    print(json.dumps(report, ensure_ascii=False))
    return report


def get(url: str, dest: Path, pause: float = 1.5, tries: int = 6) -> bool:
    if cached(url):
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    wait = 15
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type") or ""
            if "html" in ctype.lower() or body[:15].lstrip().lower().startswith((b"<!doctype", b"<html")):
                print(f"  사진이 아님(HTML 응답) {url}", file=sys.stderr, flush=True)   # a broken link: an error page
                return False
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(body)
            tmp.replace(dest)
            time.sleep(pause + random.random())
            return True
        except OSError as exc:   # the server's own error, as is
            print(f"  다시 시도 {url}: {exc} ({wait}초 뒤)", file=sys.stderr, flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 240)
    return False


def fetch(data: Path, include_drafts: bool = False, workers: int = 3) -> dict:
    places = load(data)
    urls = list(dict.fromkeys(im["url"] for p in places if include_drafts or p.get("status") == "published"
                              for im in p.get("images") or [] if im.get("license") == LICENSE))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, workers)) as ex:   # city servers are slow per connection: a few at once
        done = list(ex.map(lambda u: (u, get(u, cache_candidates(u)[0])), urls))
    for u, good in done:
        if not good:
            print(f"못 받음: {u}", file=sys.stderr)
    ok = sum(1 for _, good in done if good)
    report = {"photos": len(urls), "ok": ok, "failed": len(urls) - ok}
    print(json.dumps(report, ensure_ascii=False))
    return report


def attach(data: Path, apply: bool) -> dict:
    """Add the photos of data/<region>/portal.json to their places (after the place's other photos)."""
    cfg = settings(data)
    doc = json.loads((data / "portal.json").read_text("utf-8"))
    places = load(data)
    by_id = {p["id"]: p for p in places}
    have = {im["url"] for p in places for im in p.get("images") or []}
    added, touched = 0, set()
    for post in doc.get("posts") or []:
        if post.get("hold"):
            continue
        for pid in post.get("places") or []:
            p = by_id.get(pid)
            if not p:
                continue
            for ph in post.get("photos") or []:
                url = ph["url"]
                if url in have or ph.get("hold"):
                    continue
                p.setdefault("images", []).append({
                    "url": url, "alt": post.get("alt") or post["title"], "credit": cfg["credit"], "license": LICENSE,
                    "source": post.get("source") or doc.get("source") or cfg["credit"], "page": post.get("page") or "",
                    "taken": post.get("date") or "", "portal_id": str(post.get("id") or ""),
                    "opens_page": bool(post.get("opens_page", True)), "permit_at": cfg.get("permit_at") or ""})
                have.add(url)
                added += 1
                touched.add(pid)
    report = {"added": added, "places": len(touched),
              "published_places": sum(1 for pid in touched if by_id[pid].get("status") == "published")}
    if apply:
        save(data, places)
    print(json.dumps(report, ensure_ascii=False))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("permit", "fetch", "attach", "portal-attach"))
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "gunsan")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--drafts", action="store_true", help="fetch: also the photos of draft places")
    ap.add_argument("--workers", type=int, default=3, help="fetch: requests at once (default 3)")
    a = ap.parse_args(argv)
    if a.step == "permit":
        permit(a.data, a.apply)
    elif a.step == "fetch":
        fetch(a.data, a.drafts, a.workers)
    else:
        attach(a.data, a.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
