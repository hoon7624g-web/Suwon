"""Merge harvested TourAPI answers (tools/tourapi_harvest.py cache) into the place data — no network calls.

    python tools/harvest_merge.py --data data/daegu --photos            # dry run: what would change (report only)
    python tools/harvest_merge.py --data data/daegu --photos --apply    # write places.json
    python tools/harvest_merge.py --data data/daegu --pet --apply

--photos  관광사진 정보(PhotoGalleryService1, 공공누리 제1유형): a photo joins a place when its title names the place —
          the title (or the part inside or outside its brackets) equals the place's name, its TourAPI title or the part
          inside the brackets of either (tools.tourapi_bulk.name_key: no spaces or punctuation, the city's short name
          in front dropped) — and it was taken in the city (galPhotographyLocation is the 시·도 or one of its 구·군).
          When the location names a 구·군 the place must be in that 구·군. A title that names two places, a photo
          already on the place and a place outside the city are skipped (the report lists them). At most --per-place
          new photos per place, newest month first, one per photographer and month before a second.
          The photos go after the place's own TourAPI photos; a place whose first photo is narrower than 900px (by
          image_sizes.json) gets the widest landscape 관광사진 first instead — run tools/image_sizes.py after --apply
          and this again to settle that order. Each photo: source 'TourAPI 관광사진', licence KOGL-1, credit
          한국관광공사, photographer, month taken, gallery id, checked_at = the answer's date.
--pet     반려동물 동반여행(KorPetTourService2 detailPetTour2) by contentid: facts.pet = the 동반 type, the animals and
          what to bring, in the provider's words joined by ' · ', with the provider '한국관광공사 반려동물 동반여행(TourAPI)'.
          A value we already hold from another source stays; a different one is kept beside it (fact_alternatives:
          both shown + 방문 전 전화 확인).

--camping 고캠핑(GoCamping basedList) for the city's 시·도: a camp joins a place when one name holds the other
          (name_key) and their coordinates are within 300m. Facts in the provider's words (lists joined by '·'):
          부대시설 (sbrsCl, sbrsEtc), 반려동물 동반 (animalCmgCl), 예약 안내 (resveCl), 예약 페이지 (resveUrl), 운영 기간
          (operPdCl · operDeCl), 문의 (tel), 홈페이지 (homepage), provider '한국관광공사 고캠핑(TourAPI)', merged as --pet.
          A camp with no place stays out (the report counts them); its intro texts are not used (as overview).
--add-camps (with --camping) a camp with no place becomes a new stay record (status draft, id gocamping-<contentId>):
          name, address (addr1 addr2), coordinates, the camp kind (induty), the site counts (gnrlSiteCo …) and the facts
          above, all with the provider as their source; a reservation page only when it is a web address. A camp
          that gives fewer than two of 문의·부대시설·사이트 수·운영 기간 is left out (the report lists it). The summary
          is one sentence from those values. No photos (GoCamping images carry no 공공누리 type).

Report: reports/harvest_merge.md (what joined where, what was skipped and why). Without --apply nothing is written
but the report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import city as citymod
from pipeline.textutil import url_key
from tools.tourapi_bulk import name_key

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "tourapi"
PHOTO_SOURCE = "TourAPI 관광사진"
PET_PROVIDER = "한국관광공사 반려동물 동반여행(TourAPI)"
NARROW = 900


def items_of(path: Path) -> list[dict]:
    """The item list of one cached answer ([] for an error or empty answer)."""
    try:
        d = json.loads(path.read_text("utf-8"))
        it = d["response"]["body"]["items"]
    except (ValueError, KeyError, TypeError):
        return []
    it = it.get("item", []) if isinstance(it, dict) else []
    return it if isinstance(it, list) else [it]


def answer_date(path: Path) -> str:
    return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()


def bracket_parts(name: str) -> list[str]:
    """'앞산전망대(앞산케이블카)' -> ['앞산전망대(앞산케이블카)', '앞산전망대', '앞산케이블카']; 'A & B' -> [.., 'A', 'B']."""
    out = [name]
    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", name or "")
    if m:
        out += [m.group(1), m.group(2)]
    if " & " in (name or ""):
        out += (name or "").split(" & ")
    return [x for x in out if x.strip()]


# ----------------------------------------------------------------------------------------------- photos
def gallery_items(cache: Path) -> list[dict]:
    seen: dict[str, dict] = {}
    for f in sorted((cache / "photo_gallery").glob("gallerySearchList-*.json")):
        day = answer_date(f)
        for it in items_of(f):
            if it.get("galContentId") and it.get("galWebImageUrl"):
                seen.setdefault(it["galContentId"], {**it, "_day": day})
    return list(seen.values())


def place_keys(p: dict, C) -> set[str]:
    names = [p.get("name") or "", (p.get("tourapi") or {}).get("title") or ""]
    return {k for n in names for part in bracket_parts(n) if (k := name_key(part, C))}


def merge_photos(places: list[dict], items: list[dict], C, sizes: dict, per_place: int,
                 aliases: dict | None = None) -> dict:
    """aliases: {gallery title: place id} for a title that names the place another way ('대구 진골목길' for the place
    '대구 진골목'), data/<city>/photo_aliases.json — a person's call, written down with its basis."""
    by_key: dict[str, set[str]] = defaultdict(set)
    full: dict[str, set[str]] = defaultdict(set)   # the whole name: it wins over a part ('구암서원' over '…(구암서원)')
    by_id = {p["id"]: p for p in places if p.get("id")}
    for p in places:
        if p.get("id"):
            for k in place_keys(p, C):
                by_key[k].add(p["id"])
            for n in (p.get("name"), (p.get("tourapi") or {}).get("title")):
                if k := name_key(n, C):
                    full[k].add(p["id"])
    aliases = {t: i for t, i in (aliases or {}).items() if i in by_id}
    skipped: Counter = Counter()
    ambiguous: Counter = Counter()
    unmatched: Counter = Counter()
    picks: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        loc = C.parse_address(it.get("galPhotographyLocation"))
        if not (loc.admin == C.region_admin or loc.district):
            skipped["시·도 밖에서 찍은 사진"] += 1
            continue
        if C.locality and C.locality != C.region_admin and C.region not in (it.get("galPhotographyLocation") or ""):
            skipped["시·도 밖에서 찍은 사진"] += 1
            continue
        title = it.get("galTitle") or ""
        keys = {name_key(part, C) for part in bracket_parts(title)} - {""}
        if title in aliases:
            ids = {aliases[title]}
        elif full.get(name_key(title, C)):
            ids = set(full[name_key(title, C)])
        else:
            ids = set().union(*(by_key.get(k, set()) for k in keys)) if keys else set()
        if loc.district:
            ids = {i for i in ids if C.address_parts(by_id[i])[0] in ("", loc.district)}
        if not ids:
            unmatched[it.get("galTitle") or ""] += 1
            continue
        if len(ids) > 1:
            ambiguous[f"{it.get('galTitle')} → " + " / ".join(sorted(by_id[i]["name"] for i in ids))] += 1
            continue
        picks[ids.pop()].append(it)
    added: dict[str, int] = {}
    hero: list[str] = []
    for pid, its in picks.items():
        p = by_id[pid]
        have = {i.get("url") for i in p.get("images") or []}
        its = [i for i in its if i["galWebImageUrl"] not in have]
        # newest month first; one per (photographer, month) before a second from the same shoot
        its.sort(key=lambda i: (i.get("galPhotographyMonth") or "", i.get("galModifiedtime") or ""), reverse=True)
        seen_shoot: Counter = Counter()
        order = []
        for i in its:
            order.append((seen_shoot[(i.get("galPhotographer"), i.get("galPhotographyMonth"))], len(order), i))
            seen_shoot[(i.get("galPhotographer"), i.get("galPhotographyMonth"))] += 1
        chosen = [i for _, _, i in sorted(order, key=lambda t: (t[0], t[1]))][:max(0, per_place - sum(
            1 for x in p.get("images") or [] if x.get("source") == PHOTO_SOURCE))]
        new = [photo_record(i, p["name"]) for i in chosen]
        if not new and not any(x.get("source") == PHOTO_SOURCE for x in p.get("images") or []):
            continue
        imgs = (p.get("images") or []) + new
        imgs = hero_first(imgs, sizes)
        if imgs and imgs[0].get("source") == PHOTO_SOURCE and (p.get("images") or [{}])[0].get("source") != PHOTO_SOURCE:
            hero.append(p["name"])
        p["images"] = imgs
        if new:
            added[p["name"]] = len(new)
    return {"added": added, "hero": hero, "skipped": skipped, "ambiguous": ambiguous, "unmatched": unmatched,
            "places": len(added), "photos": sum(added.values())}


def photo_record(it: dict, name: str) -> dict:
    month = it.get("galPhotographyMonth") or ""
    return {"url": it["galWebImageUrl"], "alt": name, "credit": "한국관광공사", "license": "KOGL-1",
            "source": PHOTO_SOURCE, "photographer": (it.get("galPhotographer") or "").strip(),
            "taken": f"{month[:4]}-{month[4:6]}" if re.fullmatch(r"\d{6}", month) else "",
            "gallery_id": it["galContentId"], "checked_at": it["_day"]}


def hero_first(imgs: list[dict], sizes: dict) -> list[dict]:
    """A first photo narrower than NARROW gives its place to the widest landscape 관광사진 (KOGL-1, measured)."""
    if not imgs:
        return imgs
    w0 = (sizes.get(imgs[0].get("url")) or [0])[0] or 0
    if imgs[0].get("source") == PHOTO_SOURCE or (w0 and w0 >= NARROW):
        return imgs
    best = None
    for i, im in enumerate(imgs):
        s = sizes.get(im.get("url")) or []
        if im.get("source") == PHOTO_SOURCE and len(s) >= 2 and s[0] and s[1] and s[0] > s[1] and s[0] > w0:
            if best is None or s[0] > (sizes[imgs[best]["url"]][0]):
                best = i
    if best is None:
        return imgs
    return [imgs[best]] + imgs[:best] + imgs[best + 1:]


# ----------------------------------------------------------------------------------------------- pet
def pet_items(cache: Path) -> dict[str, dict]:
    out = {}
    for f in sorted((cache / "korpettourservice2").glob("detailPetTour-*.json")):
        day = answer_date(f)
        for it in items_of(f):
            if it.get("contentid"):
                out[str(it["contentid"])] = {**it, "_day": day}
    return out


def pet_value(it: dict) -> str:
    parts = [(it.get(k) or "").strip() for k in ("acmpyTypeCd", "acmpyPsblCpam", "acmpyNeedMtr")]
    return " · ".join(dict.fromkeys(x for x in parts if x))


def merge_pet(places: list[dict], items: dict[str, dict]) -> dict:
    added, same, differ = [], [], []
    for p in places:
        cid = str((p.get("tourapi") or {}).get("contentid") or "")
        it = items.get(cid)
        if not it:
            continue
        v = pet_value(it)
        if not v:
            continue
        facts = p.setdefault("facts", {})
        src = {"provider": PET_PROVIDER, "checked_at": it["_day"], "contentid": cid}
        old = (facts.get("pet") or "").strip()
        if not old:
            facts["pet"] = v
            p.setdefault("fact_sources", {})["pet"] = src
            added.append(p["name"])
        elif old == v:
            same.append(p["name"])
        else:
            alts = p.setdefault("fact_alternatives", {}).setdefault("pet", [])
            if not any(a.get("value") == v for a in alts):
                alts.append({"value": v, **src})
            differ.append(p["name"])
    return {"added": added, "same": same, "differ": differ}


# ----------------------------------------------------------------------------------------------- camping
CAMP_PROVIDER = "한국관광공사 고캠핑(TourAPI)"
CAMP_NEAR_M = 300
# the camp's own page on 고캠핑 (the coordinates' source page for pipeline.validate.geo_problems)
CAMP_PAGE = "https://www.gocamping.or.kr/bsite/camp/info/read.do?c_no={cid}"


def camp_items(cache: Path, C) -> list[dict]:
    out: dict[str, dict] = {}
    for f in sorted((cache / "gocamping").glob("basedList-*.json")):
        day = answer_date(f)
        for it in items_of(f):
            if (it.get("contentId")
                    and C.parse_address(f"{it.get('doNm') or ''} {it.get('sigunguNm') or ''}").admin == C.region_admin
                    and (not C.locality or C.locality == C.region_admin
                         or (it.get("sigunguNm") or "").strip() in (C.locality, C.region))):
                out[str(it["contentId"])] = {**it, "_day": day}
    return list(out.values())


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math
    return 6371000 * math.hypot(math.radians(a[0] - b[0]), math.radians(a[1] - b[1]) * math.cos(math.radians(a[0])))


def dots(v: str | None) -> str:
    return "·".join(x.strip() for x in str(v or "").split(",") if x.strip())


def camp_facts(it: dict) -> dict:
    sub = " · ".join(x for x in (dots(it.get("sbrsCl")), (it.get("sbrsEtc") or "").strip()) if x)
    period = " · ".join(x for x in (dots(it.get("operPdCl")), (it.get("operDeCl") or "").strip()) if x)
    f = {"subfacility": sub, "pet": (it.get("animalCmgCl") or "").strip(), "reservation": dots(it.get("resveCl")),
         "reservationurl": (it.get("resveUrl") or "").strip(), "openperiod": period,
         "infocenter": (it.get("tel") or "").strip(), "homepage": (it.get("homepage") or "").strip()}
    if not f["reservationurl"].startswith("http"):   # '네이버,캠핏', '이지파크펜션': a booking note, not an address
        f["reservationurl"] = ""
    return {k: v for k, v in f.items() if v}


def same_value(key: str, old: str, new: str) -> bool:
    """One value written two ways: a web address by url_key (scheme, www, trailing slash), a phone number or a list
    by its characters without spaces and separators — the same, or one holding the other ('053-667-3191~2' and
    '053-667-3191'; '봄, 여름, 가을' and '봄·여름·가을 · 평일+주말')."""
    if key in ("homepage", "reservationurl"):
        a, b = (re.sub(r"^www\.", "", url_key(x)) for x in (old, new))
        # one site: the same address, or the site's front page and a page under it
        return a == b or (a.split("/")[0] == b.split("/")[0] and "/" not in (a if len(a) < len(b) else b))
    a, b = (re.sub(r"[\s,·/]", "", x) for x in (old, new))
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def merge_facts_into(p: dict, values: dict, src: dict, out: dict) -> None:
    facts = p.setdefault("facts", {})
    for k, v in values.items():
        old = (facts.get(k) or "").strip() if isinstance(facts.get(k), str) else facts.get(k)
        if not old:
            facts[k] = v
            p.setdefault("fact_sources", {})[k] = src
            out["added"].append(f"{p['name']} {k}")
        elif old == v or (isinstance(old, str) and same_value(k, old, v)):
            out["same"].append(f"{p['name']} {k}")
        else:
            alts = p.setdefault("fact_alternatives", {}).setdefault(k, [])
            if not any(a.get("value") == v for a in alts):
                alts.append({"value": v, **src})
            out["differ"].append(f"{p['name']} {k}: {old} / {v}")


def merge_camping(places: list[dict], camps: list[dict], C, aliases: dict | None = None) -> dict:
    """aliases: {고캠핑 contentId: place id} for a camp that is a place under another name or address part
    (data/<city>/camp_aliases.json — a person's call, written down with its basis). An aliased camp merges into that
    place, and a stay made from it earlier (gocamping-<id>, --add-camps) becomes its duplicate (duplicate_of): one page."""
    out = {"added": [], "same": [], "differ": [], "matched": [], "unmatched": [], "duplicates": []}
    by_id = {p.get("id"): p for p in places}
    aliases = {str(c): i for c, i in (aliases or {}).items() if i in by_id}
    located = [p for p in places if (p.get("geo") or {}).get("lat") and p.get("id") and not p.get("duplicate_of")]
    for it in camps:
        cid = str(it.get("contentId") or "")
        if cid in aliases:
            p = by_id[aliases[cid]]
            out["matched"].append(f"{it.get('facltNm')} → {p['name']} (camp_aliases)")
            src = {"provider": CAMP_PROVIDER, "checked_at": it["_day"], "contentid": cid}
            merge_facts_into(p, camp_facts(it), src, out)
            stay = by_id.get(f"gocamping-{cid}")
            if stay is not None and stay.get("duplicate_of") != p["id"]:
                stay["duplicate_of"] = p["id"]
                out["duplicates"].append(f"{stay['name']} ({stay['id']}) → {p['name']} ({p['id']})")
            continue
        try:
            g = (float(it["mapY"]), float(it["mapX"]))
        except (KeyError, TypeError, ValueError):
            out["unmatched"].append(it.get("facltNm") or "")
            continue
        ck = name_key(it.get("facltNm"), C)
        near = []
        for p in located:
            pk = name_key(p["name"], C)
            if ck and pk and (ck in pk or pk in ck):
                d = metres(g, (p["geo"]["lat"], p["geo"]["lng"]))
                if d <= CAMP_NEAR_M:
                    near.append((d, p))
        if len(near) != 1:
            out["unmatched"].append(it.get("facltNm") or "")
            out.setdefault("unmatched_items", []).append(it)
            continue
        d, p = near[0]
        out["matched"].append(f"{it.get('facltNm')} → {p['name']} ({round(d)}m)")
        src = {"provider": CAMP_PROVIDER, "checked_at": it["_day"], "contentid": str(it["contentId"])}
        merge_facts_into(p, camp_facts(it), src, out)
    return out


SITE_KINDS = (("gnrlSiteCo", "일반"), ("autoSiteCo", "자동차"), ("glampSiteCo", "글램핑"), ("caravSiteCo", "카라반"))


def _count(v) -> int:
    try:
        return int(str(v or "0").strip())
    except ValueError:
        return 0


def camp_sites(it: dict) -> str:
    """'사이트 27개(일반 22·자동차 5)', '' when the provider gives no count."""
    parts = [(label, _count(it.get(k))) for k, label in SITE_KINDS]
    total = sum(n for _, n in parts)
    if not total:
        return ""
    named = [f"{label} {n}" for label, n in parts if n]
    return f"사이트 {total}개" + (f"({'·'.join(named)})" if len(named) > 1 else f"({named[0].split()[0]})")


def camp_summary(name: str, it: dict) -> str:
    """One sentence from the provider's values: kind, sites, open season, facilities ('' when none of the three)."""
    from pipeline.textutil import josa
    kind = dots(it.get("induty")) or "야영장"
    parts = []   # (joining form, closing form)
    sites = camp_sites(it)
    if sites:
        parts.append((f"{josa(sites, '을/를')} 두고", f"{josa(sites, '을/를')} 두고 있습니다."))
    period = dots(it.get("operPdCl"))
    if period:
        days = (it.get("operDeCl") or "").strip()
        when = f"{period}({days})" if days else period
        parts.append((f"{when}에 문을 열며", f"{when}에 문을 엽니다."))
    subs = dots(it.get("sbrsCl"))
    if subs:
        parts.append((f"부대시설로 {josa(subs, '이/가')} 있고", f"부대시설로 {josa(subs, '이/가')} 있습니다."))
    if not parts:
        return ""
    return f"{josa(name, '은/는')} {josa(kind, '으로/로')}, " + ", ".join([j for j, _ in parts[:-1]] + [parts[-1][1]])


def add_camps(places: list[dict], items: list[dict], C) -> dict:
    """New draft stays from the camps no place matched (--add-camps)."""
    from pipeline import slugs
    out = {"new": [], "thin": [], "have": []}
    have = {p["id"] for p in places}
    taken = {p["slug"] for p in places if p.get("slug")}
    for it in items:
        rid = f"gocamping-{it['contentId']}"
        name = (it.get("facltNm") or "").strip()
        if rid in have:
            out["have"].append(name)
            continue
        facts = camp_facts(it)
        useful = [k for k in ("infocenter", "subfacility", "openperiod") if facts.get(k)] + (["sites"] if camp_sites(it) else [])
        if len(useful) < 2:
            out["thin"].append(name)
            continue
        address = " ".join(x for x in ((it.get("addr1") or "").strip(), (it.get("addr2") or "").strip()) if x)
        facts = {"address": address, **facts}
        if camp_sites(it):
            facts["roomcount"] = camp_sites(it)
        src = {"provider": CAMP_PROVIDER, "checked_at": it["_day"], "contentid": str(it["contentId"])}
        rec = {"id": rid, "name": name, "kind": "stay", "category": dots(it.get("induty")) or "야영장", "themes": [],
               "tier": "basic", "status": "draft", "official": {}, "original": {},
               "map_ids": {"naver_place_id": "", "google_place_id": ""}, "images": [], "facts": facts,
               "facts_source": dict(src), "fact_sources": {k: dict(src) for k in facts},
               "summary": camp_summary(name, it),
               "geo": {"lat": float(it["mapY"]), "lng": float(it["mapX"]), "source": CAMP_PROVIDER,
                       "url": CAMP_PAGE.format(cid=it["contentId"]), "checked_at": it["_day"]}}
        district = C.parse_address(address).district or (it.get("sigunguNm") or "")
        slugs.assign_slugs([rec], name_key="name", kind="place", policy=C.slug_collision, reserved=taken,
                           district_of=lambda _: district, admin_of=lambda _: C.admin_words(address))
        rec.pop("_slug_generated", None)
        taken.add(rec["slug"])
        places.append(rec)
        out["new"].append(name)
    return out


# ----------------------------------------------------------------------------------------------- main
def report(path: Path, ph: dict | None, pet: dict | None, applied: bool, camp: dict | None = None) -> None:
    L = [f"# 수집 원응답 병합 ({dt.date.today().isoformat()}, {'반영' if applied else '미리보기 — 쓰지 않음'})", ""]
    if ph is not None:
        L += ["## 관광사진", f"- 사진을 더한 장소 {ph['places']}곳, 사진 {ph['photos']}장(장소당 상한 안)",
              f"- 첫 사진이 관광사진으로 바뀐 곳(기존 첫 사진 너비 {NARROW}px 미만): {len(ph['hero'])}곳"]
        for k, n in ph["skipped"].most_common():
            L.append(f"- 건너뜀: {k} {n}장")
        L += ["", "### 장소별", ""] + [f"- {n}: {c}장" for n, c in sorted(ph["added"].items())]
        if ph["hero"]:
            L += ["", "### 첫 사진이 바뀐 곳", ""] + [f"- {n}" for n in sorted(ph["hero"])]
        L += ["", "### 두 장소에 맞는 제목(건너뜀)", ""] + [f"- {k} ({n}장)" for k, n in ph["ambiguous"].most_common()]
        L += ["", "### 맞는 장소가 없는 제목", ""] + [f"- {k} ({n}장)" for k, n in ph["unmatched"].most_common()]
        L.append("")
    if pet is not None:
        L += ["## 반려동물 동반", f"- 새 값 {len(pet['added'])}곳, 같은 값 {len(pet['same'])}곳, 다른 값(둘 다 보임) {len(pet['differ'])}곳", ""]
        L += [f"- 다른 값: {n}" for n in pet["differ"]]
        L.append("")
    if camp is not None:
        L += ["## 고캠핑", f"- 장소에 맞춘 캠핑장 {len(camp['matched'])}곳, 맞는 장소 없음 {len(camp['unmatched'])}곳",
              f"- 새 값 {len(camp['added'])}칸, 같은 값 {len(camp['same'])}칸, 다른 값(둘 다 보임) {len(camp['differ'])}칸", ""]
        L += [f"- {m}" for m in camp["matched"]] + [""] + [f"- 다른 값: {m}" for m in camp["differ"]]
        L += ["", "### 맞는 장소가 없는 캠핑장", ""] + [f"- {m}" for m in camp["unmatched"]] + [""]
        ns = camp.get("new_stays")
        if ns:
            L += ["### 새 숙소로 넣은 캠핑장(draft)", ""] + [f"- {m}" for m in ns["new"]] + [""]
            L += ["### 정보가 적어 넣지 않은 캠핑장(문의·부대시설·사이트 수·운영 기간 가운데 둘 미만)", ""] + [f"- {m}" for m in ns["thin"]] + [""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), "utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--photos", action="store_true")
    ap.add_argument("--pet", action="store_true")
    ap.add_argument("--camping", action="store_true")
    ap.add_argument("--add-camps", action="store_true", help="--camping과 함께: 맞는 장소 없는 캠핑장을 새 숙소(draft)로")
    ap.add_argument("--per-place", type=int, default=6)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", type=Path, default=ROOT / "reports" / "harvest_merge.md")
    a = ap.parse_args(argv)
    if not (a.photos or a.pet or a.camping):
        ap.error("--photos·--pet·--camping 가운데 하나 이상")
    site = json.loads((a.data / "site.json").read_text("utf-8"))
    C = citymod.of(site)
    pf = a.data / "places.json"
    places = json.loads(pf.read_text("utf-8"))
    sf = a.data / "image_sizes.json"
    sizes = json.loads(sf.read_text("utf-8")) if sf.exists() else {}
    af = a.data / "photo_aliases.json"
    aliases = json.loads(af.read_text("utf-8")).get("titles", {}) if af.exists() else {}
    ph = merge_photos(places, gallery_items(a.cache), C, sizes, a.per_place, aliases) if a.photos else None
    pet = merge_pet(places, pet_items(a.cache)) if a.pet else None
    cf = a.data / "camp_aliases.json"
    camp_alias = {c: v["place"] for c, v in json.loads(cf.read_text("utf-8")).get("camps", {}).items()} if cf.exists() else {}
    camp = merge_camping(places, camp_items(a.cache, C), C, camp_alias) if a.camping else None
    if camp is not None and a.add_camps:
        camp["new_stays"] = add_camps(places, camp.pop("unmatched_items", []), C)
    elif camp is not None:
        camp.pop("unmatched_items", None)
    if a.apply:
        pf.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    report(a.report, ph, pet, a.apply, camp)
    print(json.dumps({"photos": ph and {k: ph[k] for k in ("places", "photos")} | {"hero": len(ph["hero"])},
                      "pet": pet and {k: len(v) for k, v in pet.items()},
                      "camping": camp and {k: (len(v) if k != "new_stays" else {x: len(y) for x, y in v.items()})
                                           for k, v in camp.items()}, "applied": a.apply,
                      "report": str(a.report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
