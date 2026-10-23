"""Build tests/fixtures/gunsan_subset/ and tests/fixtures/fact_values.json from the Gunsan site's data (read only).

    python tests/fixtures/build_gunsan_subset.py [--src /home/user/gunsan/data/gunsan]

Not a test (pytest collects test_*.py only). The output is committed; run this again only to rebuild it from the
Gunsan repository at SOURCE_COMMIT (hoon7624g-web/gunsan), which this script never writes to.

gunsan_subset/ is a small real-data site for the engine tests (tests/test_present.py, the English and guide-reading
tests build on it too): the sample site.json (data/sample/site.json: Gunsan-style designations, categories,
official_domains, list_filters, search examples) with anchors-mode regions on the five Gunsan anchor places (by place
id, far 12000 m '먼 섬'), the Gunsan list hubs and a Gunsan-style home configuration; the places the tests name, the
stops of five courses and the places of guide-02 and guide-03 and the first 13 of guide-13 (so its answer card has
more than PICKS_MAX); a guide keeps the items whose places are in the subset (guide-13: those 13, every row of its
list a page); the guides' answer-bar copy as guides.json fields (answer, answer_short, hub_short, hub_lead — the copy
the engine held in code until 2026-10-10; every figure in it is still written in the guide's summary or headings).
What is left out: original.text (licence NONE), tourapi.overview, nearby lists, videos, parking and bus files. Place
FAQs stay: a 'full' tier page must have its FAQ block (pipeline.validate). Every record gets an ASCII slug
(pipeline.slugs.assign_slugs) and every reference is rewritten; a guide source that links to a guide or place outside
the subset goes. events.json
is synthetic ('[샘플]' records: upcoming, past, 매년, text only, an earlier year, values two sources give differently).
fact_values.json: every distinct (key, value) of the Gunsan places' facts and other sources' values (fact_alternatives)
of a preview build — values only, for the value-presentation tests.
Never copied: Gunsan's GA4 / GTM / search verification / IndexNow values (the sample site.json has none).
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import city as citymod  # noqa: E402
from pipeline.slugs import SLUG_RE, assign_slugs  # noqa: E402

SOURCE_REPO = "hoon7624g-web/gunsan"
SOURCE_COMMIT = "4ae7409"
DEFAULT_SRC = Path("/home/user/gunsan/data/gunsan")
OUT = ROOT / "tests" / "fixtures" / "gunsan_subset"
FACT_VALUES = ROOT / "tests" / "fixtures" / "fact_values.json"

# A·B 당일 (B: every stop has coordinates), 2박 3일 (meals and activities between the stops), 아리랑 (a written
# summary) and one course with too few coordinates for a map
COURSES = ("gunsan-course-m2135-1", "gunsan-course-m2135-2", "gunsan-course-m2137-1", "gunsan-course-arirang",
           "gunsan-course-m2552-2")
GUIDES = ("guide-02", "guide-03", "guide-13", "guide-14", "guide-15")
ALL_ITEMS = ("guide-02", "guide-03")       # every place of these guides is in the subset
FIRST_ITEMS = {"guide-13": 13}             # the first n places of a hub guide (more than PICKS_MAX = 12)
# places the tests name (Gunsan slugs), the anchors, the home story's places and three more stays (a guesthouse)
NAMED = ("빈해원", "근대역사박물관", "링스모텔", "베스트웨스턴-군산호텔", "라마다-군산호텔", "에이본-호텔", "게스트하우스-이웃",
         "홍영장", "군산-임피역사", "복성루", "일제강점기-군산역사관", "선유-스카이썬라인", "동국사", "진포해양공원", "쌍용반점",
         "궁전갈치찜", "완주옥", "장국명가", "어청도", "은파호수공원", "선유도", "새만금비응공원", "금강미래체험관", "군산내항",
         "구-군산세관-본관", "호남관세박물관", "장자도", "대장도", "무녀도")
ANCHORS = (("wondosim", "원도심", "근대역사박물관"), ("eunpa", "은파", "은파호수공원"), ("gogunsan", "고군산", "선유도"),
           ("saemangeum-bieung", "새만금·비응", "새만금비응공원"), ("geumgang", "금강", "금강미래체험관"))
DIST_ANCHORS = ("근대역사박물관", "은파호수공원", "새만금비응공원", "선유도")
LIST_HUBS = {"food": ("guide-13", "짬뽕·꽃게장·박대·아귀찜, 메뉴별 맛집"),
             "stay": ("guide-14", "호텔·모텔·게스트하우스·섬 민박·펜션 고르는 법"),
             "attraction": ("guide-15", "권역별로 고른 가볼만한 곳")}
# the per-guide copy the engine kept in present.py (ANSWER_COPY, ANSWER_SHORT, HUB_SHORT, HUB_LEAD) until 2026-10-10,
# now the guides' own fields
ANSWER = {
    "guide-02": {"answer": "근대역사박물관·진포해양공원·테디베어박물관은 서로 직선 1km 안 · 월요일에도 여는 곳은 테디베어박물관·킹콩놀이터",
                 "fig": "1km", "unit": "직선"},
    "guide-03": {"answer": "해망로 실내 전시관 4곳은 서로 직선 350m 안 · 그중 3곳은 통합권 한 장(성인 3,000원)",
                 "closed": "월요일엔 전시관 8곳 휴관 · 여는 곳은 테디베어박물관·군산항1981·국립군산대학교 박물관",
                 "fig": "4", "unit": "곳"},
    "guide-13": {"answer": "짬뽕 20곳(장미동 동령길 특화거리 9곳) · 게장 12곳 · 아귀(아구) 9곳 · 떡갈비·칼국수 6곳씩 · 콩나물국밥 4곳",
                 "fig": "20", "unit": "곳"},
    "guide-14": {"answer": "여관·모텔 56곳 · 호텔 15곳 · 게스트하우스 9곳 · 펜션형 객실은 유로빌리지(25실)·링스모텔",
                 "fig": "89", "unit": "곳"},
    "guide-15": {"answer": "원도심 41곳 · 금강 43곳 · 고군산 36곳 · 은파 27곳 · 새만금·비응 8곳 · 이용요금 무료 59곳",
                 "fig": "161", "unit": "곳"},
}
ANSWER_SHORT = {
    "guide-02": {"key": "아이와 함께", "short": "어린이박물관·군함·테디베어가 서로 직선 1km 안", "tiny": "어린이박물관·군함·테디베어",
                 "fig": "1", "unit": "km 안"},
    "guide-03": {"key": "비 오는 날", "short": "해망로 실내 전시관 · 3곳 통합권 성인 3,000원", "tiny": "해망로 실내 전시관",
                 "fig": "4", "unit": "곳"},
}
HUB_SHORT = {
    "guide-13": {"key": "맛집", "short": "짬뽕 요리 20곳 · 게장 12곳 · 아귀 9곳 · 떡갈비 6곳", "tiny": "게장 12곳 · 아귀 9곳",
                 "fig": "20", "unit": "곳"},
    "guide-14": {"key": "숙소·펜션", "short": "여관·모텔 56곳 · 호텔 15곳 · 게스트하우스 9곳", "tiny": "모텔 56곳 · 호텔 15곳",
                 "fig": "89", "unit": "곳"},
    "guide-15": {"key": "가볼만한 곳", "short": "원도심·고군산·은파·새만금·금강 · 무료 관광지 59곳", "tiny": "무료 관광지 59곳",
                 "fig": "5", "unit": "권역"},
}
HUB_LEAD = {"guide-13": "짬뽕 요리"}
PLACE_DROP = ("nearby", "nearby_source", "question_ids")
GUIDE_DROP = ("question_ids", "allowed_numbers_from")


def load(src: Path, name: str):
    return json.loads((src / name).read_text("utf-8"))


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")


def source_commit(src: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(src), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True,
                             check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out


def kept(rows: list[dict]) -> list[dict]:
    """What a preview build keeps (build.State: draft, reviewed, published; no duplicate_of, no exclude)."""
    return [x for x in rows if x.get("status") in ("draft", "reviewed", "published") and not x.get("duplicate_of")
            and not x.get("exclude")]


def fact_values(places: list[dict]) -> list[list]:
    pairs = set()
    for e in kept(places):
        for k, v in (e.get("facts") or {}).items():
            pairs.add((k, json.dumps(v, ensure_ascii=False)))
        for k, alts in (e.get("fact_alternatives") or {}).items():
            for a in alts or []:
                if a.get("value"):
                    pairs.add((k, json.dumps(a["value"], ensure_ascii=False)))
    return [[k, json.loads(v)] for k, v in sorted(pairs)]


def clean_place(p: dict) -> dict:
    p = copy.deepcopy(p)
    for k in PLACE_DROP:
        p.pop(k, None)
    orig = p.get("original") or {}
    if orig:
        orig.pop("text", None)
        orig.pop("sha256", None)
        orig["body"] = "metadata_only"
    if isinstance(p.get("tourapi"), dict):
        p["tourapi"].pop("overview", None)
    return p


def site_json(src_commit: str, by_slug: dict, slug_map: dict) -> dict:
    site = json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8"))
    pid = lambda slug: by_slug[slug]["id"]  # noqa: E731
    site["_notes"] = [
        f"tests/fixtures/build_gunsan_subset.py가 {SOURCE_REPO} 커밋 {SOURCE_COMMIT}의 data/gunsan에서 만든 시험용 부분집합이다"
        f"(실행 시 원본 커밋 {src_commit or '확인 못 함'}). 손으로 고치지 않는다.",
        "site.json은 data/sample/site.json에 anchors 모드 권역(군산 기준점 5곳, place id), 먼 섬 12000m, 군산 list_hubs, "
        "군산식 home 설정을 더한 것이다. home.featured_min_courses는 코스 5개짜리 부분집합이라 3이다(군산 실제 값 7).",
        "events.json은 지어낸 [샘플] 기록이다. GA4·GTM·검색엔진 인증·IndexNow 값은 넣지 않는다.",
    ]
    site["_source"] = {"repo": SOURCE_REPO, "commit": SOURCE_COMMIT, "data": "data/gunsan",
                       "slug_map": dict(sorted(slug_map.items()))}
    site["regions"] = {"mode": "anchors", "label": "권역", "area_label": "읍·면·동",
                       "anchors": [{"key": k, "name": n, "place_id": pid(s)} for k, n, s in ANCHORS],
                       "far": {"m": 12000, "label": "먼 섬"}, "none_label": "권역 미정"}
    site["dist_anchors"] = [pid(s) for s in DIST_ANCHORS]
    site["list_hubs"] = {k: {"guide_id": g, "label": label} for k, (g, label) in LIST_HUBS.items()}
    gallery = [[pid(s), n] for s, n in (("선유도", 4), ("장자도", 3), ("대장도", 0), ("무녀도", 3))
               if by_slug[s].get("images")]
    site["home"] = {
        "answers": [["아이와 함께", "guide-02"], ["비 오는 날", "guide-03"]],
        "story": [
            {"id": "ch-1899", "big": "1899", "kicker": "개항", "title": "1899년, 군산항이 열리다",
             "sources": [{"place_id": pid("군산내항"), "needle": "1899년에 개항", "also": ["1979년"]}]},
            {"id": "ch-1908", "big": "1908", "kicker": "세관", "title": "1908년, 붉은 벽돌 세관",
             "sources": [{"place_id": pid("구-군산세관-본관"), "needle": "1908년", "also": ["붉은 벽돌"]},
                         {"place_id": pid("호남관세박물관"), "needle": "3대 건축물"}],
             "photo": [pid("구-군산세관-본관"), 0]},
            {"id": "ch-1909", "kicker": "근대", "title": "{first}–{last}, 근대 도시의 흔적", "title_one": "{first}년",
             "steps": True,
             "sources": [{"place_id": pid("동국사"), "needle": "1909년", "y": "1909"},
                         {"place_id": pid("군산-임피역사"), "needle": "1936년", "y": "1936"}],
             "photo": [pid("동국사"), 0]},
            {"id": "ch-today", "big": "오늘", "kicker": "오늘", "title": "다리로 이어진 섬까지",
             "sources": [{"place_id": pid("선유도"), "needle": "다리로 이어져"}], "figs": ["within", "far_km"],
             "photo": [pid("대장도"), 2]},
        ],
        "center": {"place_id": pid("구-군산세관-본관"), "radius_m": 1000},
        "far": {"place_id": pid("선유도")},
        "teaser_course": "gunsan-course-m2135-2",
        "featured_min_courses": 3,
        "video_rows": [],
        "gallery": {"eyebrow": "고군산군도", "title": "다리로 잇는 섬들.", "region": "고군산"},
        "media": {"cover": None, "hero": [], "gallery": gallery},
    }
    return site


def events(new_slug: dict) -> list[dict]:
    """Synthetic '[샘플]' event records: what the event tests need, no real event."""
    tour = "한국관광공사 TourAPI"
    site = "[샘플] 행사 누리집"
    url = "https://example.com/events/"
    eunpa = new_slug["은파호수공원"]
    return [
        {"id": "event-fixture-1", "slug": "sample-spring-night-market", "status": "published",
         "series": "[샘플] 봄꽃 야시장", "name": "[샘플] 2030 봄꽃 야시장", "period_text": "2030. 4. 5.(금) ~ 4. 7.(일)",
         "start_date": "2030-04-05", "end_date": "2030-04-07", "place_name": "전북특별자치도 군산시 [샘플] 호수공원 일원",
         "address": "전북특별자치도 군산시 은파순환길 9(나운동)", "geo": {"lat": 35.9567, "lng": 126.6970},
         "playtime": "18:00~22:00", "fee": "무료", "tel": "063-000-0001", "sponsor": "[샘플] 축제위원회",
         "source_name": tour, "source_url": "", "checked_at": "2026-10-08", "place_slugs": [eunpa],
         "highlights": ["[샘플] 야시장 먹거리 장터"],
         "alternatives": {"tel": [{"value": "070-0000-0002(운영사무국)", "source_name": site, "source_url": url,
                                   "checked_at": "2026-10-08"}]}},
        {"id": "event-fixture-2", "slug": "sample-spring-night-market", "status": "published",
         "series": "[샘플] 봄꽃 야시장", "name": "[샘플] 2025 봄꽃 야시장", "period_text": "2025. 4. 4.(금) ~ 4. 6.(일)",
         "start_date": "2025-04-04", "end_date": "2025-04-06", "place_name": "[샘플] 호수공원 일원",
         "source_name": tour, "source_url": "", "checked_at": "2026-10-08"},
        {"id": "event-fixture-3", "slug": "sample-craft-beer-festival", "status": "published",
         "series": "[샘플] 수제맥주 축제", "name": "[샘플] 2025 수제맥주 축제", "period_text": "2025. 6. 20.(금) ~ 6. 22.(일)",
         "start_date": "2025-06-20", "end_date": "2025-06-22", "place_name": "[샘플] 축제 광장", "fee": "10,000원",
         "source_name": tour, "source_url": "", "checked_at": "2026-10-08",
         "alternatives": {"fee": [{"value": "12,000원(사전 예매 10,000원)", "source_name": site, "source_url": url,
                                   "checked_at": "2026-10-08"}],
                          "place_name": [{"value": "[샘플] 강변 광장", "source_name": site, "source_url": url,
                                          "checked_at": "2026-10-08"}]}},
        {"id": "event-fixture-4", "status": "published", "series": "[샘플] 수제맥주 축제", "name": "[샘플] 수제맥주 축제",
         "period_text": "매년 6월 20일 전후 / 금, 토, 일(3일간)", "start_date": "", "place_name": "[샘플] 축제 광장",
         "source_name": site, "source_url": url, "checked_at": "2026-10-08"},
        {"id": "event-fixture-5", "status": "published", "name": "[샘플] 골목 음악회",
         "period_text": "날짜는 출처에 없음", "start_date": "", "place_name": "[샘플] 골목",
         "source_name": site, "source_url": url, "checked_at": "2026-10-08"},
        {"id": "event-fixture-6", "status": "published", "name": "[샘플] 2025 가을 등산축제",
         "period_text": "2025년 가을(날짜는 출처에 없음)", "start_date": "", "place_name": "[샘플] 산 입구",
         "source_name": site, "source_url": url, "checked_at": "2026-10-08"},
        {"id": "event-fixture-7", "status": "published", "name": "[샘플] 강변 음악회",
         "period_text": "2025.5.28(수) 18:30~", "start_date": "", "place_name": "전북특별자치도 군산시 [샘플] 강변 무대",
         "source_name": site, "source_url": url, "checked_at": "2026-10-08"},
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="data/gunsan of the Gunsan repository (read only)")
    a = ap.parse_args(argv)
    src = a.src
    commit = source_commit(src)
    if commit and commit != SOURCE_COMMIT:
        print(f"경고: 원본 커밋 {commit} ≠ 기록할 커밋 {SOURCE_COMMIT}", file=sys.stderr)
    places_all = load(src, "places.json")
    by_slug = {p["slug"]: p for p in places_all}
    courses = [copy.deepcopy(c) for c in load(src, "courses.json") if c["id"] in COURSES]
    guides = {g["id"]: copy.deepcopy(g) for g in load(src, "guides.json") if g["id"] in GUIDES}
    sizes = load(src, "image_sizes.json")

    want: list[str] = []

    def add(slug):
        if slug and slug in by_slug and slug not in want:
            want.append(slug)
    for c in courses:
        for s in c.get("stops") or []:
            add(s.get("place_slug"))
    for gid in ALL_ITEMS:
        for it in guides[gid].get("items") or []:
            add(it.get("place_slug"))
    for gid, n in FIRST_ITEMS.items():
        for it in [it for it in guides[gid].get("items") or [] if it.get("place_slug") in by_slug][:n]:
            add(it["place_slug"])
    for s in NAMED:
        add(s)
    missing = [s for s in NAMED if s not in by_slug]
    if missing:
        raise SystemExit(f"원본에 없는 장소: {missing}")
    places = [clean_place(by_slug[s]) for s in sorted(want, key=lambda s: by_slug[s]["id"])]
    old = {p["id"]: p.pop("slug") for p in places}
    site = site_json(commit, by_slug, {})
    C = citymod.from_site(site)
    problems = assign_slugs(places, name_key="name", kind="place", policy=C.slug_collision,
                            admin_of=lambda e: C.admin_words((e.get("facts") or {}).get("address")))
    for p in places:
        p.pop("_slug_generated", None)
    slug_map = {old[p["id"]]: p["slug"] for p in places}
    new = lambda s: slug_map.get(s or "")  # noqa: E731

    for c in courses:
        for s in c.get("stops") or []:
            if s.get("place_slug"):
                s["place_slug"] = new(s["place_slug"])
                if not s["place_slug"]:
                    raise SystemExit(f"코스 경유지 장소가 부분집합에 없음: {c['id']}")
        c.pop("question_ids", None)
        if not SLUG_RE.match(c.get("slug") or ""):
            c.pop("slug", None)
    problems += assign_slugs(courses, name_key="name", kind="course", policy="number")
    for g in guides.values():
        for k in [k for k in g if k.startswith("_")] + list(GUIDE_DROP):
            g.pop(k, None)
        items = []
        for it in g.get("items") or []:
            ps = it.get("place_slug")
            if ps and not new(ps):
                continue   # a place outside the subset: the item goes (the guide's own text stays as it is)
            if ps:
                it["place_slug"] = new(ps)
            items.append(it)
        g["items"] = items
        g["route_slugs"] = [new(s) for s in g.get("route_slugs") or [] if new(s)]
        if not g["route_slugs"]:
            g.pop("route_slugs")
        g.pop("slug", None)
        g["answer"] = ANSWER[g["id"]]
        if g["id"] in ANSWER_SHORT:
            g["answer_short"] = ANSWER_SHORT[g["id"]]
        if g["id"] in HUB_SHORT:
            g["hub_short"] = HUB_SHORT[g["id"]]
        if g["id"] in HUB_LEAD:
            g["hub_lead"] = HUB_LEAD[g["id"]]
    guide_list = [guides[g] for g in GUIDES]
    old_guide = {g["id"]: g["slug"] for g in load(src, "guides.json")}
    problems += assign_slugs(guide_list, name_key="title", kind="guide", policy="number")
    for x in courses + guide_list:
        x.pop("_slug_generated", None)
    # a source that links inside the site: rewritten to the subset's path, or left out when its page is not built
    paths = {f"/guides/{old_guide[g['id']]}/": f"/guides/{g['slug']}/" for g in guide_list}
    paths.update({f"/places/{o}/": f"/places/{n}/" for o, n in slug_map.items()})
    for g in guide_list:
        srcs = []
        for s in g.get("sources") or []:
            u = s.get("url") or ""
            if u.startswith("/"):
                if u not in paths:
                    continue
                s = {**s, "url": paths[u]}
            srcs.append(s)
        g["sources"] = srcs
    if problems:
        raise SystemExit("slug 문제: " + "; ".join(problems))
    urls = set()
    for p in places:
        for im in p.get("images") or []:
            urls.add(im["url"])
            urls.add(im["url"].replace("_image2_1", "_image3_1"))
    site = site_json(commit, {**by_slug, **{old[p["id"]]: p for p in places}}, slug_map)

    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / "site.json", site)
    dump(OUT / "places.json", places)
    dump(OUT / "courses.json", courses)
    dump(OUT / "guides.json", guide_list)
    dump(OUT / "events.json", events(slug_map))
    dump(OUT / "themes.json", json.loads((ROOT / "data" / "sample" / "themes.json").read_text("utf-8")))
    dump(OUT / "image_sizes.json", {u: sizes[u] for u in sorted(urls) if u in sizes})
    dump(FACT_VALUES, {"_notes": [f"{SOURCE_REPO} 커밋 {SOURCE_COMMIT} data/gunsan/places.json에서 미리보기 빌드가 싣는 장소의 "
                                  "facts와 fact_alternatives 값(서로 다른 key·value 쌍, 값만). "
                                  "tests/fixtures/build_gunsan_subset.py가 만든다."],
                       "pairs": fact_values(places_all)})
    print(json.dumps({"places": len(places), "courses": len(courses), "guides": len(guide_list),
                      "image_sizes": len(urls & set(sizes)), "fact_values": len(fact_values(places_all)),
                      "source_commit": commit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
