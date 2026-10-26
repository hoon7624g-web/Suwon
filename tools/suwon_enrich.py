"""Enrich data/suwon/places.json and data/suwon/events.json from what the data already holds (no network):
1. Duplicate TourAPI records (`duplicate_of`) and the vercel.json path redirects of their old addresses (the host
   rules in front are kept).
2. Themes (data/suwon/themes.json slugs) from the place's name, TourAPI category and class words.
3. An event's places (`place_slugs`): the published attractions whose name the event's TourAPI place (eventplace) or
   title names.
4. Summaries and FAQs through tools/place_text.py (machine-written or empty ones only; the rules are there).

Facts come only from tools/tourapi_bulk.py (TourAPI answers), tools/harvest_merge.py (TourAPI photos, pets) and
tools/suwon_official.py (official pages, each value with its page). Nothing here writes a fact, a default value
('연중무휴', '무료', '상시 개방', '인근 공영주차장' …) or publication (status / reviewed_at / approved_at — a person
decides it, CLAUDE.md 3절 7항).

    python tools/suwon_enrich.py              # write places.json, events.json, vercel.json
    python tools/suwon_enrich.py --dry-run    # print the counts only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import place_text

DATA_DIR = ROOT / "data" / "suwon"

DUPLICATE_OF = {
    "tourapi-4011413": "tourapi-3057776",   # 수원KT위즈파크 (쇼핑 -> 레포츠)
    "gocamping-100057": "tourapi-2909927",  # 수원 솔내음 캠핑장 -> 솔내음캠핑장
}

# theme slug -> words of the place's name, TourAPI category or class; a place gets at most two, none when no word
# matches (no default theme). The slugs are the published theme addresses (themes.json); their names say what they hold.
THEME_WORDS = {
    "modern-history": ("수원화성", "수원 화성", "화성행궁", "행궁", "장안문", "팔달문", "화서문", "창룡문", "방화수류정",
                       "동북각루", "서장대", "동장대", "연무대", "화홍문", "공심돈", "봉돈", "화령전", "효원의 종", "성곽",
                       "향교", "노송지대", "현충탑", "박물관", "미술관", "전시관", "해우재", "아트센터", "아트홀",
                       "도서관", "별마당", "전통문화관", "공연장", "사찰", "봉녕사", "팔달사", "청련암", "반야사",
                       "용화사", "문화시설"),
    "islands-sea": ("호수", "저수지", "만석거", "서호", "용연", "수변", "천길"),
    "parks-nature": ("수목원", "공원", "광교산", "팔달산", "칠보산", "여기산", "마루길", "숲", "생태", "무궁화", "월화원"),
    "alleys-culture": ("행리단길", "공방거리", "통닭거리", "시장", "벽화마을", "나혜석거리", "아쿠아플라넷", "스타필드",
                       "갤러리아", "롯데몰", "AK플라자", "스몹", "위즈파크", "월드컵", "캠핑", "국궁", "플라잉 수원",
                       "어차", "XR버스", "골목", "스모어"),
}


def assign_themes(p: dict) -> list[str]:
    if p.get("kind") != "attraction":
        return []
    text = f"{p.get('name', '')} {p.get('category', '')}"
    return [slug for slug, words in THEME_WORDS.items() if any(w in text for w in words)][:2]


def mark_duplicates(places: list[dict]) -> int:
    n = 0
    for p in places:
        if p["id"] in DUPLICATE_OF:
            p["duplicate_of"] = DUPLICATE_OF[p["id"]]
            n += 1
    return n


def sync_vercel_redirects(places: list[dict]) -> int:
    """The path rules of merged duplicates (tests/test_domain_move.py); the host rules in front stay as they are."""
    vercel_path = ROOT / "vercel.json"
    vercel = json.loads(vercel_path.read_text("utf-8"))
    by_id = {p["id"]: p for p in places}
    paths = []
    for p in places:
        dup_id = p.get("duplicate_of")
        if dup_id and p.get("slug") and dup_id in by_id:
            to_slug = by_id[dup_id]["slug"]
            paths.append({"source": f"/places/{p['slug']}/", "destination": f"/places/{to_slug}/", "permanent": True})
            paths.append({"source": f"/:lang(en|ja|zh-hans|zh-hant|de|fr|es|ru)/places/{p['slug']}/",
                          "destination": f"/:lang/places/{to_slug}/", "permanent": True})
    hosts = [r for r in vercel.get("redirects") or [] if r.get("has")]
    vercel["redirects"] = hosts + paths
    if not vercel["redirects"]:
        vercel.pop("redirects")
    vercel_path.write_text(json.dumps(vercel, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return len(paths)


def link_events(events: list[dict], places: list[dict]) -> int:
    """place_slugs of an event: published attractions (not duplicates) whose name — three letters or more — stands in the
    event's TourAPI place or title (spaces and bracketed parts left out). Longer names first, so '수원 화성' inside
    '수원화성행궁 일원' gives way to 화성행궁."""
    bare = lambda s: re.sub(r"\s|\([^()]*\)", "", s or "")   # '화서문(華西門)' -> '화서문', '수원 화성' -> '수원화성'
    cands = sorted(((bare(p["name"]), p) for p in places if p.get("status") == "published" and not p.get("duplicate_of")
                    and p.get("kind") == "attraction" and len(bare(p.get("name"))) >= 3), key=lambda x: -len(x[0]))
    n = 0
    for ev in events:
        found, taken = [], bare(f"{ev.get('place_name', '')} {ev.get('name', '')}")
        for name, p in cands:
            if name in taken:
                found.append(p["slug"])
                taken = taken.replace(name, "|")
        if found:
            ev["place_slugs"] = found
            n += 1
        else:
            ev.pop("place_slugs", None)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    places = json.loads((DATA_DIR / "places.json").read_text("utf-8"))
    events = json.loads((DATA_DIR / "events.json").read_text("utf-8"))
    stats = {"duplicates": mark_duplicates(places)}
    for p in places:
        themes = assign_themes(p)
        if themes:
            p["themes"] = themes
        else:
            p.pop("themes", None)
    stats["themed"] = sum(1 for p in places if p.get("themes"))
    stats["events_linked"] = link_events(events, places)
    if a.dry_run:
        print(json.dumps(stats, ensure_ascii=False))
        return 0
    (DATA_DIR / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (DATA_DIR / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", "utf-8")
    stats["redirects"] = sync_vercel_redirects(places)
    stats["text"] = {k: (len(v) if isinstance(v, list) else v) for k, v in place_text.run(DATA_DIR).items()}
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
