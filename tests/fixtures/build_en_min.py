"""Build tests/fixtures/en_min/ — the English-site fixture — from the Gunsan site's English records (read only) and
tests/fixtures/gunsan_subset/ (its ids and ASCII slugs are authoritative).

    python tests/fixtures/build_en_min.py [--src /home/user/gunsan/data/gunsan]

Not a test (pytest collects test_*.py only). The output is committed; run this again only to rebuild it (after
gunsan_subset changes, or when the Korean side of a record changes: the ko_hash of every record is recomputed here
with pipeline.en_source.current_hashes over gunsan_subset + this overlay).

The tests (tests/test_en_site.py, tests/test_guide_reading.py) copy gunsan_subset to a temporary folder and lay
en_min over it (overlay()):
- en/places.json, en/names.json: the English records of PLACES (8 places: every kind, a value two sources give
  differently, an official designation of two kinds, a page below the index rule, the place whose Korean summary the
  stale-record test edits), their `slug` the subset's;
- en/guides.json: GUIDE (the food hub, its items cut to the subset's as gunsan_subset cut the Korean guide, internal
  source links kept only when their page is in the subset); en/courses.json: COURSE;
- events.json + en/events.json: one real Gunsan event series (EVENT_SERIES: two dated editions and a '매년' record,
  three values two sources give differently) with its English record, in place of gunsan_subset's synthetic
  '[샘플]' events — a production build may not show a placeholder (pipeline.validate), and an English record must
  be a translation, so no event is made up here. Every edition stores the series slug (slugs.series_slug);
- en/strings.json: the Gunsan English labels the pages read (not the 'ui.' / 'site.' sets), the region names
  re-keyed by region key (REGIONS.<anchor key>, REGIONS.far, REGIONS.none — pipeline.en_site.En.region_name) and the
  hub tiles' phone lines (LIST_HUB_TINY.<kind>: the copy pipeline.en_site held in code until 2026-10-10);
- site_overrides.json: merged into site.json — languages ko+en (the English switch), https://fixture.test, a fake
  GA4 id and correction address, no '[샘플]' description or FAQ. Gunsan's real GA4 / GTM / search verification /
  IndexNow values are never copied (they are not read at all).
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import city as citymod  # noqa: E402
from pipeline.en_source import current_hashes  # noqa: E402
from pipeline.slugs import series_slug  # noqa: E402
from pipeline.textutil import squash_ws  # noqa: E402

SOURCE_REPO = "hoon7624g-web/gunsan"
SOURCE_COMMIT = "4ae7409"
DEFAULT_SRC = Path("/home/user/gunsan/data/gunsan")
SUBSET = ROOT / "tests" / "fixtures" / "gunsan_subset"
OUT = ROOT / "tests" / "fixtures" / "en_min"

PLACES = ("gunsan-305395",    # 근대역사박물관: its Korean summary is edited in the stale-record test
          "gunsan-305372",    # 은파호수공원: no designation, coordinates, photos
          "gunsan-1379526",   # 군산근대건축관: hours two sources give differently
          "gunsan-305401",    # 청암산: below the index rule (noindex in production)
          "gunsan-306591",    # 복성루: a city designation (군산맛집 2026)
          "gunsan-1305918",   # 빈해원: another designation (짬뽕 특화거리)
          "gunsan-307082",    # 라마다 군산호텔: a stay
          "gunsan-433871")    # 동국사: on the course
GUIDE = "guide-13"                    # the food hub (site.json list_hubs.food, a hub_lead)
COURSE = "gunsan-course-m2135-2"      # B 당일 course: every stop has coordinates
EVENT_SERIES = "군산 수제맥주&블루스 페스티벌"
EN_EVENT_KEY = "군산-수제맥주블루스-페스티벌"   # its key in the Gunsan en/events.json (the old Korean series slug)
STRING_KEEP = ("KIND_LABELS.", "FACT_LABELS.", "INDEX_GROUP_LABELS.", "TITLE_LABELS.", "STATUS_PREFIX.",
               "CONTEST_LABEL.", "LIC.", "category:", "STAY_TYPE.", "FOOD_TYPE.", "ATTR_TYPE.", "ATTRACTION_GROUPS.",
               "provider:", "designation:", "designation_source:", "STOP_KIND_LABELS.", "LIST_CFG.")
HUB_TINY = {"guide-14": "Including pensions", "guide-15": "Area by area"}
SITE_OVERRIDES = {"languages": ["ko", "en"], "site_url": "https://fixture.test", "ga4_id": "G-FIXTURE000",
                  "operator": {"contact": "corrections@fixture.test"}, "description": "", "site_faq": []}


def load(path: Path):
    return json.loads(path.read_text("utf-8"))


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")


def merge_site(site: dict, overrides: dict) -> dict:
    """site.json with the overrides (a dict value is merged one level deep, e.g. operator.contact)."""
    out = copy.deepcopy(site)
    for k, v in overrides.items():
        out[k] = {**(out.get(k) or {}), **v} if isinstance(v, dict) else copy.deepcopy(v)
    return out


def overlay(data: Path, en_min: Path = OUT) -> None:
    """Lay en_min over a copy of gunsan_subset in `data`: en/ and events.json copied, site_overrides.json merged."""
    shutil.copytree(en_min / "en", data / "en", dirs_exist_ok=True)
    shutil.copy(en_min / "events.json", data / "events.json")
    site = load(data / "site.json")
    (data / "site.json").write_text(json.dumps(merge_site(site, load(en_min / "site_overrides.json")),
                                               ensure_ascii=False, indent=1) + "\n", "utf-8")


def source_commit(src: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(src), "rev-parse", "--short=7", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def strings_of(src_strings: dict, site: dict) -> dict:
    out = {k: v for k, v in src_strings.items() if k.startswith(STRING_KEEP)
           or (k.startswith("LISTS.") and k.endswith(".lead")) or (k.startswith("theme.") and k.endswith(".name"))}
    regions = site["regions"]
    for i, a in enumerate(regions["anchors"]):   # Gunsan REGIONS.<i> follow the anchors' order
        row = src_strings.get(f"REGIONS.{i}")
        if not row or row.get("ko") != a["name"]:
            raise SystemExit(f"REGIONS.{i} != anchor {a['name']}")
        out[f"REGIONS.{a['key']}"] = row
    if (regions.get("far") or {}).get("label") == src_strings["FAR_LABEL"]["ko"]:
        out["REGIONS.far"] = src_strings["FAR_LABEL"]
    if regions.get("none_label") == src_strings["NONE_LABEL"]["ko"]:
        out["REGIONS.none"] = src_strings["NONE_LABEL"]
    hubs = {v["guide_id"]: k for k, v in (site.get("list_hubs") or {}).items()}
    for gid, en in HUB_TINY.items():
        if gid in hubs:
            out[f"LIST_HUB_TINY.{hubs[gid]}"] = {"ko": "", "en": en}
    return dict(sorted(out.items()))


def events_of(src_events: list[dict], slug_map: dict) -> list[dict]:
    """The real Gunsan records of EVENT_SERIES, the series slug stored on each, place slugs rewritten (or dropped)."""
    evs = [copy.deepcopy(e) for e in src_events if squash_ws(e.get("series")) == EVENT_SERIES]
    if len([e for e in evs if e.get("start_date")]) < 2:
        raise SystemExit(f"행사 시리즈 회차 부족: {EVENT_SERIES}")
    slug = series_slug(evs, EVENT_SERIES, set())
    for e in evs:
        e["slug"] = slug
        for k in ("place_slugs", "place_slug"):
            if k in e:
                v = e.pop(k)
                kept = [slug_map[s] for s in (v if isinstance(v, list) else [v]) if s in slug_map]
                if kept:
                    e[k] = kept if isinstance(v, list) else kept[0]
        e.pop("question_ids", None)
    return evs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="data/gunsan of the Gunsan repository (read only)")
    a = ap.parse_args(argv)
    src, en_src = a.src, a.src / "en"
    commit = source_commit(src)
    if commit and commit != SOURCE_COMMIT:
        print(f"경고: 원본 커밋 {commit} ≠ 기록할 커밋 {SOURCE_COMMIT}", file=sys.stderr)
    site = load(SUBSET / "site.json")
    slug_map = site["_source"]["slug_map"]                 # Gunsan (Korean) slug -> subset ASCII slug
    sub_places = {p["id"]: p for p in load(SUBSET / "places.json")}
    sub_guides = {g["id"]: g for g in load(SUBSET / "guides.json")}
    sub_courses = {c["id"]: c for c in load(SUBSET / "courses.json")}
    en = {k: load(en_src / f"{k}.json") for k in ("places", "guides", "courses", "events", "names", "strings")}

    places, names = {}, {}
    for pid in PLACES:
        p, rec = sub_places[pid], copy.deepcopy(en["places"][pid])
        if rec.get("name_ko") != p["name"]:
            raise SystemExit(f"영어 기록의 한국어 이름이 다름: {pid}")
        rec["slug"] = p["slug"]
        places[pid] = rec
        names[pid] = en["names"][pid]

    g = copy.deepcopy(en["guides"][GUIDE])
    kept = {it["place_slug"] for it in sub_guides[GUIDE]["items"] if it.get("place_slug")}
    g["slug"] = sub_guides[GUIDE]["slug"]
    g["items"] = [{**it, "place_slug": slug_map[it["place_slug"]]} for it in g.get("items") or []
                  if slug_map.get(it.get("place_slug")) in kept]
    if [it["place_slug"] for it in g["items"]] != [it["place_slug"] for it in sub_guides[GUIDE]["items"]]:
        raise SystemExit(f"{GUIDE}: 영어 항목이 부분집합의 한국어 항목과 다름")
    paths = {f"/places/{o}/": f"/places/{n}/" for o, n in slug_map.items()}
    srcs = []
    for s in g.get("sources") or []:
        u = s.get("url") or ""
        if u.startswith("/"):
            if u not in paths:
                continue   # a page outside the subset (the Korean guide's source went the same way)
            s = {**s, "url": paths[u]}
        srcs.append(s)
    g["sources"] = srcs

    c = copy.deepcopy(en["courses"][COURSE])
    c["slug"] = sub_courses[COURSE]["slug"]
    for st in c.get("stops") or []:
        if st.get("place_slug"):
            st["place_slug"] = slug_map.get(st["place_slug"], "")
    if [s.get("place_slug") or "" for s in c["stops"]] != \
            [s.get("place_slug") or "" for s in sub_courses[COURSE]["stops"]]:
        raise SystemExit(f"{COURSE}: 영어 경유지가 부분집합의 한국어 경유지와 다름")

    events = events_of(load(src / "events.json"), slug_map)
    ev_rec = copy.deepcopy(en["events"][EN_EVENT_KEY])

    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / "site_overrides.json", SITE_OVERRIDES)
    dump(OUT / "events.json", events)
    # the hashes of the Korean side as the tests will build it: gunsan_subset + this overlay
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        shutil.copytree(SUBSET, data)
        dump(OUT / "en" / "names.json", names)
        dump(OUT / "en" / "strings.json", strings_of(en["strings"], site))
        for k in ("places", "guides", "courses", "events"):
            dump(OUT / "en" / f"{k}.json", {})
        overlay(data)
        hashes = current_hashes(data, city=citymod.of(load(data / "site.json")))
    for pid, rec in places.items():
        rec["ko_hash"] = hashes["places"][pid]
    g["ko_hash"] = hashes["guides"][GUIDE]
    c["ko_hash"] = hashes["courses"][COURSE]
    ev_slug = events[0]["slug"]
    ev_rec["ko_hash"] = hashes["events"][ev_slug]
    dump(OUT / "en" / "places.json", places)
    dump(OUT / "en" / "guides.json", {GUIDE: g})
    dump(OUT / "en" / "courses.json", {COURSE: c})
    dump(OUT / "en" / "events.json", {ev_slug: ev_rec})
    print(json.dumps({"places": len(places), "guides": 1, "courses": 1, "event_series": ev_slug,
                      "events": len(events), "strings": len(load(OUT / "en" / "strings.json")),
                      "source_commit": commit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
