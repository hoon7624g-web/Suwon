"""A city's photo portal → photos for the places of the site (운영자 결정 2026-11-14 '모두 허락 받았어. 전수조사하고,
최대한 사진들 많이 끌어와서 … 모든 사이트가 아주 풍성해지도록': the photos of the city government's own sites, used with
its permission). Settings per region: data/<region>/city_portal.json (type, base, fields, aliases, cap, source).

    python tools/city_portal.py lists  --data data/<region>   # the posts of the travel-related fields
    python tools/city_portal.py match  --data data/<region>   # which posts show which place → report
    python tools/city_portal.py search --data data/<region>   # the portal's own search for places still short of photos
    python tools/city_portal.py views  --data data/<region>   # the photo lists of the newest matched posts of each place
    python tools/city_portal.py photos --data data/<region>   # up to CAP photos per place → data/cache/city-portal
    python tools/city_portal.py write  --data data/<region>   # data/<region>/portal.json
then  python tools/city_photos.py attach --apply  and  python tools/kogl1_media.py

Portal kinds (city_portal.json type):
- 'photobank': a '포토뱅크' of the gm kind — list /gmMenuSearchList.do?cate_numb_1=&cate_numb_2=&req_pg= (12 posts a
  page), search the same address with search_txt, a post /gmMenuView.do?group_numb=<id> (its photos are the hidden
  image_N inputs: /data/simg/<yyyymm>/<file>, 800px; the post's own page is what a photo opens to).
  fields: {"<cate_numb_1>-<cate_numb_2>": name}.

Curated, not everything: a post goes to a place when its title names the place (the longest name wins, spaces
ignored, the city's own short name in front ignored, a checked other name — aliases) and it is not an occasion with
people as its subject (EXCLUDE words: 개막식, 방문, 협약, 시장 …: ceremonies, visits, meetings — the city's news photos,
with identifiable people). Per place at most CAP photos, from its newest posts first, taken in turn across posts (the
first photo of each post, then the second …), a near-duplicate of a photo already kept for the place (dHash ≤ 6 bits)
skipped. A published attraction without a matched post (a shop or stay short of photos) is also looked up with the
portal's own search by its name.

City servers reset bursts of requests: one request at a time, a pause between (PAUSE, default 5 s), retries with a
growing wait from 15 s. Pages and photos are cached in data/cache (git-ignored); a rerun asks only for what is missing.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ""   # set by configure(): the portal's address (data/<region>/city_portal.json base)
DATA = ROOT / "data"
SOURCE = ""
KIND = ""
PAGES = ROOT / "data" / "cache" / "city-portal-pages"
PHOTOS = ROOT / "data" / "cache" / "city-portal"
WORK = ROOT / "data" / "cache" / "city-portal-work"   # contents.json, match.json, views.json, kept.json
UA = "Mozilla/5.0 (compatible; webforai-photo-sync/1.0)"
PAUSE = float(os.environ.get("PAUSE", "5"))
FIELDS: dict[str, str] = {}   # set by configure() from data/<region>/city_portal.json
PREFIXES: tuple[str, ...] = ()   # the city's own short names, dropped in front of a title or name (site.json)
# a post about people or an occasion, not a place: the city's news photos (with identifiable people)
EXCLUDE = ("개장식", "개막식", "폐막식", "개회식", "폐회식", "위촉", "방문", "점검", "협약", "MOU", "시상", "회의", "보고회",
           "세미나", "대화", "격려", "브리핑", "현판", "개관식", "개소식", "수여", "기념식", "준공", "기공", "착공", "간담회",
           "설명회", "발대식", "선포식", "출범", "결의", "캠페인", "교육", "훈련", "봉사", "위문", "만찬", "면담", "접견", "시찰",
           "시장", "의장", "도지사", "장관", "국회", "의원", "예방", "환영", "환송", "총회", "토론", "포럼", "워크숍", "공청회",
           "정화", "일손", "김장", "헌혈", "투표", "선거", "심사", "평가", "품평", "취임", "이임", "퇴임", "직원", "공무원",
           "현장", "회견", "인터뷰", "촬영회", "시연", "체결", "약정", "서명", "기념촬영", "단체", "행진", "집회", "추모",
           "참배", "헌화", "제례", "고유제", "영결", "합동", "연찬", "연수", "실습", "워크샵", "강연", "강의", "특강", "시험",
           "모집", "접수", "상담", "진료", "검진", "접종", "방역", "소독", "단속", "계도", "홍보활동", "가두", "릴레이",
           "전달식", "기탁", "후원", "나눔", "성금", "물품", "증정", "축사", "인사", "의회", "위원회", "협의회", "연합회",
           "대책", "피해", "복구", "사고", "화재", "침몰", "불법", "공사", "철거", "정비사업", "조성사업", "추진", "용역",
           # occasions at a place (people are the subject): festivals, rites, openings, shows (→ not a place photo)
           "축제", "돌파", "잔치", "석전", "대제", "법회", "점안", "전시회", "제막", "개관", "개장", "오신 날", "기획전",
           "감사패", "탐방", "공연", "행사", "대회", "기념", "공모", "사진전", "음악회", "콘서트", "페스티벌", "축전",
           "문화제", "야적장", "설명", "답사", "견학", "투어", "체험", "참가", "참여", "시민", "학생", "어린이날", "졸업",
           "입학", "결혼", "웨딩", "자원", "봉축", "연등", "추석", "설날", "명절", "성탄", "송년", "신년", "해맞이",
           # the photobank kind's own words for occasions and people (부시장, 생방송, 다례 …)
           "부시장", "생방송", "방송", "다례", "능행차", "시승식", "기림일", "대표단", "야화", "프레스", "개최", "시청",
           "공무", "업무", "협력", "주민", "청소년", "아동", "노인", "어르신", "장애인", "가족", "선수", "리그전",
           "시즌", "응원", "개통", "착수", "발표", "수상", "의정", "정책", "선정", "협의", "출연", "녹화", "상량식",
           "대향연", "한마당", "기증", "점등", "리허설", "연주회", "합창", "미술대전", "박람회", "버스킹", "관람")
ALIASES: dict[str, str] = {}   # set by configure(): other names the portal uses → the site's place name
MIN_KEY = 3   # a name shorter than this matches only a title that is exactly the name
CAP = 20      # photos per place at most (city_portal.json cap)
SHORT = 4     # a published place with fewer shown photos than this is looked up with the portal's search


def configure(data: Path) -> None:
    """The region's portal settings (data/<region>/city_portal.json) and the city's short names (site.json)."""
    global BASE, DATA, SOURCE, CAP, KIND, PREFIXES
    cfg = json.loads((Path(data) / "city_portal.json").read_text("utf-8"))
    DATA, BASE, SOURCE, KIND = Path(data), cfg["base"].rstrip("/"), cfg.get("source") or "", cfg.get("type") or ""
    if KIND != "photobank":
        raise SystemExit(f"city_portal.json type '{KIND}'는 이 도구가 읽지 못합니다(photobank)")
    FIELDS.clear()
    FIELDS.update({str(k): v for k, v in (cfg.get("fields") or {}).items()})
    ALIASES.clear()
    ALIASES.update(cfg.get("aliases") or {})
    CAP = int(cfg.get("cap") or CAP)
    site = json.loads((Path(data) / "site.json").read_text("utf-8"))
    names = {site.get("region") or "", site.get("locality") or ""}
    names |= {n.removesuffix("시").removesuffix("특례") for n in names if n}
    PREFIXES = tuple(sorted({n for n in names if len(n) >= 2}, key=len, reverse=True))


def fetch(path: str, binary: bool = False, tries: int = 7, cache: Path = PAGES) -> bytes | str:
    url = path if path.startswith("http") else BASE + path
    cache.mkdir(parents=True, exist_ok=True)
    fn = cache / (hashlib.sha1(url.encode()).hexdigest()[:20] + (".bin" if binary else ".html"))
    if fn.exists() and fn.stat().st_size:
        return fn.read_bytes() if binary else fn.read_text("utf-8", "ignore")
    wait = 15
    for _ in range(tries):
        time.sleep(PAUSE + random.uniform(0, 1.5))
        try:   # curl: the city server resets far fewer of its connections than of urllib's
            r = subprocess.run(["curl", "-sS", "-f", "-m", "90", "-A", UA, "-H", "Accept-Language: ko", "-D", "-", url],
                               capture_output=True, timeout=120)
            if r.returncode:
                raise OSError(r.stderr.decode("utf-8", "ignore").strip()[:120])
            head, _, body = r.stdout.partition(b"\r\n\r\n")
            ctype = "html" if b"content-type: text/html" in head.lower() else ""
            if binary and ("html" in ctype or body[:15].lstrip().lower().startswith((b"<!doctype", b"<html"))):
                raise RuntimeError(f"사진이 아님(HTML 응답): {url}")
            fn.write_bytes(body)
            return body if binary else body.decode("utf-8", "ignore")
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"  다시 시도 {url[:100]}: {exc} ({wait}초 뒤)", file=sys.stderr, flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 240)
    raise RuntimeError(f"받지 못함: {url}")


# ----------------------------------------------------------------------------- photobank (gm) pages
ITEM = re.compile(r"fn_Detail\('(\d+)', '\d+'\);\">\s*<div class=\"imgbox\">\s*<img src=\"([^\"]+)\" alt=\"([^\"]*)\""
                  r".*?<p class=\"st txtL\">(.*?)</p>.*?<span class=\"ft_gray fl\">\s*([\d-]+)\s*</span>", re.S)
TOTAL = re.compile(r"총검색수\s*:\s*([\d,]+)")


def list_path(field: str, page: int) -> str:
    c1, _, c2 = field.partition("-")
    return f"/gmMenuSearchList.do?cate_numb_1={c1}&cate_numb_2={c2}&menu_id=0&req_pg={page}&orig_type=1&selectGubun=d"


def search_path(word: str, page: int = 1) -> str:
    return (f"/gmMenuSearchList.do?search_txt={urllib.parse.quote(word)}&menu_id=0&req_pg={page}&orig_type=1"
            "&selectGubun=s")


def post_page(cid: str) -> str:
    return f"{BASE}/gmMenuView.do?group_numb={cid}&list_numb=1&menu_id=0"


def items(s: str) -> list[dict]:
    out = []
    for cid, img, alt, title, date in ITEM.findall(s):
        title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        title = re.sub(r"\s*\[\d+\]$", "", title).strip()   # '… [21]': the post's photo count
        out.append({"id": cid, "title": title, "date": date, "cover": img})
    return out


def lists() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "contents.json"
    db = json.loads(out.read_text("utf-8")) if out.exists() else {}
    for field, name in FIELDS.items():
        first = fetch(list_path(field, 1))
        tot = TOTAL.search(first)
        pages = math.ceil(int(tot.group(1).replace(",", "")) / 12) if tot else 1
        for p in range(1, pages + 1):
            s = first if p == 1 else fetch(list_path(field, p))
            for it in items(s):
                d = db.setdefault(it["id"], {**it, "cats": []})
                if name not in d["cats"]:
                    d["cats"].append(name)
            if p % 20 == 0:
                out.write_text(json.dumps(db, ensure_ascii=False), "utf-8")
                print(f"  {name}: {p}/{pages}쪽, 지금까지 {len(db)}건", flush=True)
        out.write_text(json.dumps(db, ensure_ascii=False), "utf-8")
        print(f"{name}: {pages}쪽, 지금까지 {len(db)}건", flush=True)
    return db


# ----------------------------------------------------------------------------- matching
def norm(s: str) -> str:
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s or "")
    s = re.sub(r"[\s·.,_\-'\"‘’“”「」<>《》]+", "", s)
    for pre in PREFIXES:
        if s.startswith(pre) and len(s) > len(pre) + 1:
            s = s[len(pre):]
            break
    return s


def place_keys(places: list[dict]) -> dict[str, tuple]:
    keys: dict[str, tuple] = {}
    by_name = {p["name"]: p for p in places}
    for p in places:
        names = [p["name"], *(p.get("aliases") or []), (p.get("tourapi") or {}).get("title") or ""]
        inner = [x for x in re.findall(r"\(([^)]+)\)", p["name"]) if len(norm(x)) >= 4]
        for n in names + inner:
            k = norm(n)
            if len(k) >= 2:
                keys.setdefault(k, (p, p.get("kind")))
    for old, name in ALIASES.items():
        if name and name in by_name:
            keys[norm(old)] = (by_name[name], by_name[name].get("kind"))
        elif not name:
            keys.pop(norm(old), None)
    return keys


STRIP = re.compile(r"\d+$|_\d+$|드론\s*사진|드론사진|항공사진|항공|전경|야경|풍경|사진|설경|가을|겨울|봄|여름|"
                   r"^모범음식점|^맛집")


def match_title(title: str, keys: dict) -> dict | None:
    """The place a post's title names, or None. A shop or stay (food/stay) only by its exact name: a short shop name
    inside a longer title is too often a common word."""
    if any(w in title for w in EXCLUDE):
        return None
    t = norm(STRIP.sub("", re.sub(r"\[.*?\]", "", title).strip()))
    if t in keys:
        return keys[t][0]
    hits = [(len(k), k) for k, (p, kind) in keys.items() if len(k) >= MIN_KEY and k in t and kind == "attraction"]
    # a post about two subjects or more ('광교호수공원, 수원컨벤션센터 봄 스케치', '수원메쎄, 롯데몰'): its photos mix them —
    # no place's, unless every part names the same place (a name inside a longer hit — 장안문 in 장안문거북시장 — is that hit)
    ids = {keys[k][0]["id"] for _, k in hits if not any(k != o and k in o for _, o in hits)}
    parts = [norm(x) for x in re.split(r"[,，/]", re.sub(r"\[.*?\]", "", title)) if norm(x)]
    if len(ids) > 1 or (len(parts) > 1 and not all(any(k in x for _, k in hits) for x in parts)):
        return None
    return keys[max(hits)[1]][0] if hits else None


def published() -> list[dict]:
    return [p for p in json.loads((DATA / "places.json").read_text("utf-8")) if p.get("status") == "published"]


def match() -> dict:
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    places = published()
    keys = place_keys(places)
    res: dict[str, list] = {}
    for c in db.values():
        p = match_title(c["title"], keys)
        if p:
            res.setdefault(p["id"], []).append(c["id"])
    old = json.loads((WORK / "match.json").read_text("utf-8")) if (WORK / "match.json").exists() else {}
    for pid, ids in old.items():   # keep what search() found
        for cid in ids:
            if (db.get(cid) or {}).get("cats") == ["검색"] and cid not in res.get(pid, []):
                res.setdefault(pid, []).append(cid)
    (WORK / "match.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    by_id = {p["id"]: p for p in places}
    n = sum(len(v) for v in res.values())
    print(json.dumps({"posts": n, "places": len(res)}, ensure_ascii=False))
    for pid, v in sorted(res.items(), key=lambda x: -len(x[1]))[:60]:
        print(f"  {by_id[pid]['name']}: {len(v)} — " + " | ".join(db[i]["title"] for i in v[:4]))
    return res


def shown_photos(p: dict) -> int:
    return sum(1 for im in p.get("images") or [] if im.get("license") in ("KOGL-1", "KOGL-3", "CITY-PERMIT"))


def search() -> dict:
    """The portal's search for every published attraction without a matched post (and a shop or stay with fewer than
    SHORT photos — operator 2026-11-14 '최대한 사진들 많이'): a post whose
    title is the place's name (or names it, for an attraction name of 3+ characters) and is not an occasion joins
    match.json."""
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    res = json.loads((WORK / "match.json").read_text("utf-8")) if (WORK / "match.json").exists() else {}
    places = [p for p in published() if p["id"] not in res
              and (p.get("kind") == "attraction" or shown_photos(p) < SHORT)]
    found = {}
    for p in places:
        word = re.sub(r"\s*\(.*?\)", "", p["name"]).strip()
        key = norm(word)
        if len(key) < 2:
            continue
        try:
            s = fetch(search_path(word))
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            continue
        for it in items(s):
            title = it["title"]
            if any(w in title for w in EXCLUDE):
                continue
            t = norm(STRIP.sub("", re.sub(r"\[.*?\]", "", title)))
            if not (t == key or (len(key) >= MIN_KEY and p.get("kind") == "attraction" and key in t)):
                continue
            db.setdefault(it["id"], {**it, "cats": ["검색"]})
            if it["id"] not in res.setdefault(p["id"], []):
                res[p["id"]].append(it["id"])
            found.setdefault(p["name"], []).append(title)
    (WORK / "contents.json").write_text(json.dumps(db, ensure_ascii=False), "utf-8")
    (WORK / "match.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({"searched": len(places), "found_places": len(found)}, ensure_ascii=False))
    for n, ts in found.items():
        print(f"  {n}: " + " | ".join(ts[:5]))
    return found


VIEW_IMG = re.compile(r'id="image_(\d+)" value="(/data/simg/[^"]+)"')


def views() -> dict:
    """The photo lists of each place's newest matched posts, until 2×CAP candidates (or no more posts)."""
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    res = json.loads((WORK / "match.json").read_text("utf-8"))
    out = WORK / "views.json"
    got = json.loads(out.read_text("utf-8")) if out.exists() else {}
    n = 0
    for pid, ids in res.items():
        have = 0
        for cid in sorted(ids, key=lambda c: db[c]["date"], reverse=True):
            if have >= 2 * CAP:
                break
            if cid not in got:
                try:
                    s = fetch(post_page(cid))
                except RuntimeError as exc:
                    print(exc, file=sys.stderr)
                    continue
                photos = list(dict.fromkeys(u for _, u in sorted(VIEW_IMG.findall(s), key=lambda x: int(x[0]))))
                got[cid] = {"photos": [u for u in photos if "*" not in u]}
                n += 1
                if n % 10 == 0:
                    out.write_text(json.dumps(got, ensure_ascii=False), "utf-8")
                    print(f"  상세 {n}", flush=True)
            have += len(got[cid]["photos"])
    out.write_text(json.dumps(got, ensure_ascii=False), "utf-8")
    print(json.dumps({"views": len(got), "photos_listed": sum(len(v["photos"]) for v in got.values())}, ensure_ascii=False))
    return got


def dhash(path: Path) -> int | None:
    from PIL import Image, ImageOps
    try:
        im = ImageOps.exif_transpose(Image.open(path)).convert("L").resize((9, 8), Image.LANCZOS)
    except OSError:
        return None
    px = list(im.getdata())
    return sum(1 << i for i in range(64) if px[(i // 8) * 9 + i % 8] > px[(i // 8) * 9 + i % 8 + 1])


def picks() -> dict[str, list[tuple[str, str]]]:
    """{place id: [(post id, photo path), …]} in the order photos are tried: newest post first, in turn."""
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    res = json.loads((WORK / "match.json").read_text("utf-8"))
    got = json.loads((WORK / "views.json").read_text("utf-8"))
    out = {}
    for pid, ids in res.items():
        posts = [(c, got[c]["photos"]) for c in sorted(ids, key=lambda c: db[c]["date"], reverse=True) if c in got]
        order, i = [], 0
        while any(i < len(ph) for _, ph in posts):
            order += [(c, ph[i]) for c, ph in posts if i < len(ph)]
            i += 1
        out[pid] = order
    return out


def cache_name(u: str) -> str:
    """The cache file of a portal photo: <host>__<path with __> (tools/city_photos.cache_candidates)."""
    parts = urllib.parse.urlsplit(BASE + u)
    return f"{parts.netloc}__{parts.path.lstrip('/').replace('/', '__')}"


def photos(workers: int = 3) -> dict:
    """Up to CAP photos per place: download in pick order, skip a near-duplicate of one already kept. Places are
    taken WORKERS at a time (each request still paced: PAUSE, retries from 15 s) — the city server's own limit."""
    from concurrent.futures import ThreadPoolExecutor
    PHOTOS.mkdir(parents=True, exist_ok=True)
    out = WORK / "kept.json"
    kept_all: dict[str, list] = json.loads(out.read_text("utf-8")) if out.exists() else {}
    stats = {"fetched": 0, "bad": []}

    def one(item):
        pid, order = item
        kept, hashes = [], []
        for cid, u in order:
            if len(kept) >= CAP:
                break
            dest = PHOTOS / cache_name(u)
            if not (dest.exists() and dest.stat().st_size):
                try:
                    body = fetch(BASE + u, binary=True, cache=PHOTOS / "_raw")
                except RuntimeError as exc:
                    stats["bad"].append(u)
                    print(exc, file=sys.stderr, flush=True)
                    continue
                dest.write_bytes(body)
                (PHOTOS / "_raw" / (hashlib.sha1((BASE + u).encode()).hexdigest()[:20] + ".bin")).unlink(missing_ok=True)
                stats["fetched"] += 1
            h = dhash(dest)
            if h is None:
                stats["bad"].append(u)
                continue
            if any(bin(h ^ x).count("1") <= 6 for x in hashes):
                continue
            hashes.append(h)
            kept.append([cid, u])
        return pid, kept

    todo = [(pid, order) for pid, order in picks().items()]
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for i, (pid, kept) in enumerate(ex.map(one, todo), 1):
            kept_all[pid] = kept
            if i % 10 == 0:
                out.write_text(json.dumps(kept_all, ensure_ascii=False), "utf-8")
                print(f"  장소 {i}/{len(todo)}, 받은 사진 {stats['fetched']}", flush=True)
    out.write_text(json.dumps(kept_all, ensure_ascii=False), "utf-8")
    report = {"places": len(kept_all), "photos": sum(len(v) for v in kept_all.values()), "fetched_now": stats["fetched"],
              "broken": len(stats["bad"])}
    print(json.dumps(report, ensure_ascii=False))
    return report


def write() -> dict:
    """data/<region>/portal.json: per post its place and the photos kept for it."""
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    kept = json.loads((WORK / "kept.json").read_text("utf-8"))
    by_post: dict[tuple, list] = {}
    for pid, rows in kept.items():
        for cid, u in rows:
            by_post.setdefault((cid, pid), []).append({"url": BASE + u})
    posts = [{"id": cid, "title": db[cid]["title"], "date": db[cid]["date"], "places": [pid],
              "page": post_page(cid), "fields": db[cid].get("cats") or [], "opens_page": True,
              "alt": re.sub(r"\s*\d+$|_\d+$", "", re.sub(r"^\[.*?\]\s*", "", db[cid]["title"])).strip(), "photos": phs}
             for (cid, pid), phs in sorted(by_post.items(), key=lambda x: (x[0][1], db[x[0][0]]["date"]), reverse=True)]
    doc = {"_about": f"{SOURCE or BASE} 게시물 가운데 제목이 이 사이트의 장소를 가리키는 것(행사·인물이 주인공인 게시물 "
                     f"제외)에서 장소마다 최신 게시물부터 돌아가며 고른 사진(장소당 {CAP}장까지, 거의 같은 연속 사진 제외). "
                     "운영자 결정 2026-11-14 '모두 허락 받았어. 전수조사하고, 최대한 사진들 많이 끌어와서 … 모든 사이트가 "
                     "아주 풍성해지도록'. tools/city_portal.py가 만들고 tools/city_photos.py attach가 장소에 붙인다. "
                     "싣지 않을 게시물·사진은 hold: true.",
           "source": SOURCE, "checked_at": time.strftime("%Y-%m-%d"), "posts": posts}
    (DATA / "portal.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    report = {"posts": len(posts), "photos": sum(len(p["photos"]) for p in posts),
              "places": len({p["places"][0] for p in posts})}
    print(json.dumps(report, ensure_ascii=False))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("lists", "match", "search", "views", "photos", "write"))
    ap.add_argument("--data", type=Path, required=True)
    a = ap.parse_args(argv)
    configure(a.data)
    {"lists": lists, "match": match, "search": search, "views": views, "photos": photos, "write": write}[a.step]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
