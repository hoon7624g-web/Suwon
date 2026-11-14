"""A city's online photo portal of the 'uprbank' kind (군산시 온라인홍보포털 uprbank.gunsan.go.kr and others built on the same
system) → photos for the places of the site (운영자 결정 2026-11-13·14, the city's permission). Settings per region:
data/<region>/city_portal.json (base, fields, aliases, cap, source); pass --data data/<region>.

    python tools/city_portal.py lists            # the posts of the travel-related fields (title, date, fields)
    python tools/city_portal.py match            # which posts show which place → report
    python tools/city_portal.py search           # the portal's own search for each place still without a photo
    python tools/city_portal.py views            # the photo lists of the newest matched posts of each place
    python tools/city_portal.py photos           # up to CAP photos per place (1280px) → data/cache/city-portal
    python tools/city_portal.py write            # data/<region>/portal.json
then  python tools/city_photos.py portal-attach --apply  and  python tools/kogl1_media.py

The portal holds 15,477 posts (2026-11-13), each with 10–40 photos; 8,892 are 행정/운영 (the mayor's day, meetings,
agreements). The operator asked to place every photo where it fits ('적절한 장소들에 모두 배치'): a post goes to a
place when its title names the place (the longest name wins, spaces ignored, '군산' prefix ignored, a checked old
name — 은파유원지 → 은파호수공원 …) and it is not an event with people as its subject (EXCLUDE words: 개막식, 방문,
협약, 시장 …: ceremonies, visits, meetings, campaigns — the city's own news photos, with identifiable people). Fields
read: 문화/관광, 여행/음식, 생태/환경, 도시/시설, 항공사진, 기타/일반, 행사/축제, 인물/역사.

Curated, not everything (운영자 2026-11-13 '홍보포털에 사진이 15만장 있으면 어차피 다 못 가져오는 거 아니야? 거기서만
추려와도 엄청나겠는데' and '홈페이지 내 사진이 빈 곳들은 모두 채워주고'): per place at most CAP (12) photos, from its newest
posts first, taken in turn across posts (the first photo of each post, then the second …), a near-duplicate of a photo
already kept for the place (dHash ≤ 6 bits) skipped. A published place without any photo is also looked up with the
portal's own search by its name (a shop: '모범음식점-한일옥' style titles).

The portal resets bursts of requests: one request at a time, a pause between (PAUSE, default 6 s), retries with a
growing wait. Pages and photos are cached in data/cache (git-ignored); a rerun asks only for what is missing.
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
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ""   # set by configure(): the portal's address (data/<region>/city_portal.json base)
DATA = ROOT / "data" / "gunsan"
SOURCE = ""
PAGES = ROOT / "data" / "cache" / "city-portal-pages"
PHOTOS = ROOT / "data" / "cache" / "city-portal"
WORK = ROOT / "data" / "cache" / "city-portal-work"   # contents.json, views.json (intermediate)
UA = "Mozilla/5.0 (compatible; webforai-photo-sync/1.0)"
PAUSE = float(os.environ.get("PAUSE", "6"))
FIELDS: dict[int, str] = {}   # set by configure() from data/<region>/city_portal.json
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
           "입학", "결혼", "웨딩", "자원", "봉축", "연등", "추석", "설날", "명절", "성탄", "송년", "신년", "해맞이")
# old or other names the portal uses for a place on the site (checked 2026-11-13)
ALIASES: dict[str, str] = {}   # set by configure()
MIN_KEY = 3   # a name shorter than this matches only a title that is exactly the name
CAP = 12      # photos per place at most (city_portal.json cap)


def configure(data: Path) -> None:
    """The region's portal settings (data/<region>/city_portal.json: base, fields, aliases, cap, source)."""
    global BASE, DATA, SOURCE, CAP
    cfg = json.loads((Path(data) / "city_portal.json").read_text("utf-8"))
    DATA, BASE, SOURCE = Path(data), cfg["base"].rstrip("/"), cfg.get("source") or ""
    FIELDS.clear()
    FIELDS.update({int(k): v for k, v in (cfg.get("fields") or {}).items()})
    ALIASES.clear()
    ALIASES.update(cfg.get("aliases") or {})
    CAP = int(cfg.get("cap") or CAP)


def fetch(path: str, binary: bool = False, tries: int = 7, cache: Path = PAGES) -> bytes | str:
    url = path if path.startswith("http") else BASE + path
    cache.mkdir(parents=True, exist_ok=True)
    fn = cache / (hashlib.sha1(url.encode()).hexdigest()[:20] + (".bin" if binary else ".html"))
    if fn.exists() and fn.stat().st_size:
        return fn.read_bytes() if binary else fn.read_text("utf-8", "ignore")
    wait = 15
    for _ in range(tries):
        time.sleep(PAUSE + random.uniform(0, 2))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
            fn.write_bytes(body)
            return body if binary else body.decode("utf-8", "ignore")
        except OSError as exc:
            print(f"  다시 시도 {url[:90]}: {exc} ({wait}초 뒤)", file=sys.stderr, flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 240)
    raise RuntimeError(f"받지 못함: {url}")


ITEM = re.compile(r'<div class="item">\s*<a href="/main/m\d+/view\.do\?cntsId=(\d+)[^"]*">.*?<img src="([^"]+)" '
                  r'alt="([^"]*)".*?<dt>(.*?)</dt>.*?ic_gallery_date\.png[^>]*>\s*([\d-]+)</span>.*?'
                  r'ic_gallery_view\.png[^>]*>\s*([\d,]+)</span>', re.S)


def lists() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "contents.json"
    db = json.loads(out.read_text("utf-8")) if out.exists() else {}
    for c, name in FIELDS.items():
        first = fetch(f"/main/m21/list.do?s_cat1={c}&s_rowNum=60&s_idx=1")
        tot = re.search(r'class="total">\s*Total\s*<span>([\d,]+)</span>', first)
        pages = math.ceil(int(tot.group(1).replace(",", "")) / 60) if tot else 1
        for p in range(1, pages + 1):
            s = first if p == 1 else fetch(f"/main/m21/list.do?s_cat1={c}&s_rowNum=60&s_idx={p}")
            for cid, img, _alt, title, date, views in ITEM.findall(s):
                d = db.setdefault(cid, {"id": cid, "title": html.unescape(re.sub(r"<[^>]+>", "", title)).strip(),
                                        "date": date, "views": int(views.replace(",", "")), "cover": img, "cats": []})
                if name not in d["cats"]:
                    d["cats"].append(name)
        out.write_text(json.dumps(db, ensure_ascii=False), "utf-8")
        print(f"{name}: {pages}쪽, 지금까지 {len(db)}건", flush=True)
    return db


def norm(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s or "")
    return re.sub(r"[\s·.,_\-]+|^군산(시)?", "", s)


def place_keys(places: list[dict]) -> dict[str, dict]:
    keys: dict[str, dict] = {}
    by_name = {p["name"]: p for p in places}
    for p in places:
        names = [p["name"], *(p.get("aliases") or []), (p.get("tourapi") or {}).get("title") or ""]
        inner = [x for x in re.findall(r"\(([^)]+)\)", p["name"]) if len(norm(x)) >= 4]   # (히로쓰가옥), not (창오리)
        for n in names + inner:
            k = norm(n)
            if len(k) >= 2:
                keys.setdefault(k, (p, p.get("kind")))
    for old, name in ALIASES.items():
        if name and name in by_name:
            keys[norm(old)] = (by_name[name], by_name[name].get("kind"))
    return keys


def match_title(title: str, keys: dict) -> dict | None:
    """The place a post's title names, or None. A shop or stay (food/stay) only by its exact name (after a
    '모범음식점-' style prefix): a short shop name inside a longer title is too often a common word ('아리랑')."""
    if any(w in title for w in EXCLUDE):
        return None
    t = norm(re.sub(r"\d+$|_\d+$|드론\s*사진|드론사진|항공사진|전경|야경|풍경|사진|^모범음식점|^맛집", "", title.strip()))
    if t in keys:
        return keys[t][0]
    hits = [(len(k), k) for k, (p, kind) in keys.items() if len(k) >= MIN_KEY and k in t and kind == "attraction"]
    return keys[max(hits)[1]][0] if hits else None


def match() -> dict:
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    places = [p for p in json.loads((DATA / "places.json").read_text("utf-8")) if p.get("status") == "published"]
    keys = place_keys(places)
    res: dict[str, list] = {}
    for c in db.values():
        p = match_title(c["title"], keys)
        if p:
            res.setdefault(p["id"], []).append(c["id"])
    (WORK / "match.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    by_id = {p["id"]: p for p in places}
    n = sum(len(v) for v in res.values())
    print(json.dumps({"posts": n, "places": len(res)}, ensure_ascii=False))
    for pid, v in sorted(res.items(), key=lambda x: -len(x[1]))[:40]:
        print(f"  {by_id[pid]['name']}: {len(v)} — " + " | ".join(db[i]["title"] for i in v[:4]))
    return res


VIEW_IMG = re.compile(r'<div class="swiper-slide"><img src="(/photo/[^"]+)" alt="([^"]*)"')


def shown_photos(p: dict) -> int:
    return sum(1 for im in p.get("images") or [] if im.get("license") in ("KOGL-1", "KOGL-3", "CITY-PERMIT"))


def search() -> dict:
    """The portal's search (상세검색, by keyword) for every published place without a photo; a post whose title
    is the place's name (or names it, for a place name of 3+ characters; a shop by its exact name after a
    '모범음식점' style prefix) and is not an occasion joins match.json."""
    db = json.loads((WORK / "contents.json").read_text("utf-8"))
    res = json.loads((WORK / "match.json").read_text("utf-8")) if (WORK / "match.json").exists() else {}
    places = [p for p in json.loads((DATA / "places.json").read_text("utf-8"))
              if p.get("status") == "published" and not shown_photos(p) and p["id"] not in res]
    found = {}
    for p in places:
        word = re.sub(r"\s*\(.*?\)", "", p["name"]).strip()
        s = fetch(f"/main/m43/index.do?s_key=keyword&s_word={urllib.request.quote(word)}&s_rowNum=60")
        key = norm(word)
        for cid, img, _alt, title, date, views in ITEM.findall(s):
            title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
            if any(w in title for w in EXCLUDE):
                continue
            t = norm(re.sub(r"\d+$|_\d+$|^모범음식점|^맛집|드론\s*사진", "", title))
            if not (t == key or (len(key) >= MIN_KEY and p.get("kind") == "attraction" and key in t)):
                continue
            db.setdefault(cid, {"id": cid, "title": title, "date": date, "views": int(views.replace(",", "")),
                                "cover": img, "cats": ["검색"]})
            res.setdefault(p["id"], []).append(cid)
            found.setdefault(p["name"], []).append(title)
    (WORK / "contents.json").write_text(json.dumps(db, ensure_ascii=False), "utf-8")
    (WORK / "match.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({"searched": len(places), "found_places": len(found)}, ensure_ascii=False))
    for n, ts in found.items():
        print(f"  {n}: " + " | ".join(ts[:5]))
    return found


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
                s = fetch(f"/main/m21/view.do?cntsId={cid}")
                photos = list(dict.fromkeys(u for u, _ in VIEW_IMG.findall(s)))
                shot = re.search(r"<th[^>]*>촬영일자</th>\s*<td[^>]*>(.*?)</td>", s, re.S)
                got[cid] = {"photos": photos,
                            "shot": html.unescape(re.sub(r"<[^>]+>|\s+", " ", shot.group(1))).strip() if shot else ""}
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


def photos() -> dict:
    """Up to CAP photos per place: download in pick order, skip a near-duplicate of one already kept."""
    PHOTOS.mkdir(parents=True, exist_ok=True)
    kept_all: dict[str, list] = {}
    fetched = 0
    for pid, order in picks().items():
        kept, hashes = [], []
        for cid, u in order:
            if len(kept) >= CAP:
                break
            dest = PHOTOS / u.rsplit("/", 1)[-1]
            if not (dest.exists() and dest.stat().st_size):
                try:
                    dest.write_bytes(fetch(BASE + u, binary=True, cache=PHOTOS / "_raw"))
                    fetched += 1
                except RuntimeError as exc:
                    print(exc, file=sys.stderr)
                    continue
            h = dhash(dest)
            if h is None or any(bin(h ^ x).count("1") <= 6 for x in hashes):
                continue
            hashes.append(h)
            kept.append([cid, u])
        kept_all[pid] = kept
    (WORK / "kept.json").write_text(json.dumps(kept_all, ensure_ascii=False), "utf-8")
    report = {"places": len(kept_all), "photos": sum(len(v) for v in kept_all.values()), "fetched_now": fetched}
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
              "page": f"{BASE}/main/m21/view.do?cntsId={cid}", "fields": db[cid].get("cats") or [], "opens_page": True,
              "alt": re.sub(r"\s*\d+$|_\d+$", "", db[cid]["title"]).strip(), "photos": phs}
             for (cid, pid), phs in sorted(by_post.items(), key=lambda x: (x[0][1], db[x[0][0]]["date"]), reverse=True)]
    doc = {"_about": f"{SOURCE or BASE} 게시물 가운데 제목이 이 사이트의 장소를 가리키는 것(행사·인물이 "
                     "주인인 게시물 제외)에서 장소마다 최신 게시물부터 돌아가며 고른 사진(장소당 12장까지, 거의 같은 연속 사진 "
                     "제외). 운영자 결정 2026-11-13 '군산시 허락은 받았으니까 …' · '거기서만 추려와도' · '사진이 빈 곳들은 모두 "
                     "채워주고'. tools/city_portal.py가 만들고 tools/city_photos.py portal-attach가 장소에 붙인다. 싣지 않을 "
                     "게시물·사진은 hold: true.",
           "source": SOURCE, "checked_at": time.strftime("%Y-%m-%d"), "posts": posts}
    (DATA / "portal.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    report = {"posts": len(posts), "photos": sum(len(p["photos"]) for p in posts),
              "places": len({p["places"][0] for p in posts})}
    print(json.dumps(report, ensure_ascii=False))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("lists", "match", "search", "views", "photos", "write"))
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "gunsan")
    a = ap.parse_args(argv)
    configure(a.data)
    {"lists": lists, "match": match, "search": search, "views": views, "photos": photos, "write": write}[a.step]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
