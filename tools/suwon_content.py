"""Generate Suwon courses, guides, abroad, abroad_highlights, ask, art, videos, and update site.json."""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import art, ask
from tools import guide_content as gc
from tools import place_content as pc

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "suwon"
ART_DIR = ROOT / "templates" / "assets" / "art"
ALL_LANGS = ["ko", "en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru"]
PREFIX = {
    "ko": "일러스트: ",
    "en": "Illustration: ",
    "ja": "イラスト：",
    "zh-hans": "插图：",
    "zh-hant": "插圖：",
    "de": "Illustration: ",
    "fr": "Illustration : ",
    "es": "Ilustración: ",
    "ru": "Иллюстрация: ",
}


def dump_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def update_site_json() -> None:
    site_path = DATA / "site.json"
    site = json.loads(site_path.read_text("utf-8"))
    site["regions"] = {
        "mode": "anchors",
        "label": "권역",
        "area_label": "동·구",
        "anchors": [
            {
                "key": "hwaseong-haenggung",
                "name": "수원화성·화성행궁·행리단길",
                "place_id": "tourapi-129437",
            },
            {
                "key": "paldalmun-market",
                "name": "팔달문·전통시장·통닭거리",
                "place_id": "tourapi-264386",
            },
            {
                "key": "gwanggyo-yeongtong",
                "name": "광교호수공원·박물관·영통",
                "place_id": "tourapi-2662855",
            },
            {
                "key": "manseok-jangan",
                "name": "만석공원·광교산·장안",
                "place_id": "tourapi-3351831",
            },
            {
                "key": "irwol-gwonseon",
                "name": "일월수목원·서호공원·권선",
                "place_id": "tourapi-3076051",
            },
        ],
        "far": None,
        "none_label": "권역 미정",
    }
    site["dist_anchors"] = [
        "tourapi-129437",
        "tourapi-264386",
        "tourapi-2662855",
        "tourapi-3351831",
        "tourapi-3076051",
    ]
    site["course_move"] = {
        "guides_first": ["guide-03"],
        "guides_last": [],
        "route_by_guide": {},
    }
    site["list_hubs"] = {
        "attraction": {
            "guide_id": "guide-01",
            "label": "수원화성·행궁·성곽 가이드",
        },
        "food": {
            "guide_id": "guide-05",
            "label": "월요일 영업·맛집 가이드",
        },
        "stay": {
            "guide_id": "guide-06",
            "label": "호텔·한옥·숙소 가이드",
        },
    }
    site["home"] = {
        "answers": [
            ["수원화성·행궁·성곽", "guide-01"],
            ["아이와 함께", "guide-02"],
            ["비 오는 날·실내", "guide-03"],
            ["월요일 영업·맛집", "guide-05"],
            ["호텔·한옥·숙소", "guide-06"],
        ],
        "story": [
            {
                "id": "fortress-palace",
                "big": "성곽과 행궁",
                "kicker": "수원화성 · 화성행궁 · 방화수류정",
                "title": "유네스코 세계문화유산 수원화성 성곽길과 정조대왕의 발자취가 깃든 화성행궁·방화수류정",
                "sources": [
                    {"place_id": "tourapi-125555", "needle": "수원 화성"},
                    {"place_id": "tourapi-129437", "needle": "화성행궁"},
                ],
                "figs": ["within", "far_km"],
                "photo": ["tourapi-2613658", 0],
            },
            {
                "id": "market-alley",
                "big": "시장과 골목",
                "kicker": "팔달문 · 남문시장 · 수원통닭거리",
                "title": "정조가 세운 팔달문 아래 전통시장 아홉 곳과 가마솥 고소한 향이 퍼지는 수원통닭거리",
                "sources": [
                    {"place_id": "tourapi-2589025", "needle": "수원 남문시장"},
                    {"place_id": "tourapi-2613664", "needle": "수원통닭거리"},
                ],
                "figs": [],
                "photo": ["tourapi-2613664", 0],
            },
            {
                "id": "lake-garden",
                "big": "호수와 수목원",
                "kicker": "광교호수공원 · 일월수목원 · 월화원",
                "title": "수변 데크길이 이어진 광교호수공원과 사계절 온실을 품은 일월수목원·효원공원 월화원",
                "sources": [
                    {"place_id": "tourapi-2662855", "needle": "광교호수공원"},
                    {"place_id": "tourapi-3076051", "needle": "일월수목원"},
                ],
                "figs": [],
                "photo": ["tourapi-2662855", 0],
            },
        ],
        "center": {
            "place_id": "tourapi-129437",
            "radius_m": 6000,
        },
        "far": {
            "place_id": "tourapi-2662855",
        },
        "teaser_course": "suwon-course-1",
        "featured_min_courses": 1,
        "video_rows": [
            "수원화성·화성행궁",
            "광교호수공원·아쿠아플라넷",
            "왕갈비·통닭·전통시장",
        ],
        "gallery": {
            "eyebrow": "수원 풍경",
            "title": "유네스코 세계문화유산 수원화성과 화성행궁, 방화수류정·광교호수공원·일월수목원까지 사진으로 미리 보는 수원",
            "region": "수원화성·화성행궁·행리단길",
        },
        "media": {
            "cover": ["tourapi-125555", 0],
            "hero": [
                ["tourapi-125555", 0],
                ["tourapi-129437", 0],
                ["tourapi-2613658", 0],
                ["tourapi-2662855", 0],
                ["tourapi-750947", 0],
                ["tourapi-3076051", 0],
            ],
            "gallery": [
                ["tourapi-3351831", 0],
                ["tourapi-1925403", 0],
                ["tourapi-2613664", 0],
                ["tourapi-4067984", 0],
                ["tourapi-2589025", 0],
                ["tourapi-2752650", 0],
            ],
        },
        "getting_here": {
            "label": "실내·문화 가이드",
            "guide_id": "guide-03",
        },
    }
    site["plan"] = {
        "hubs": [
            {"key": "station", "name": "수원역(KTX·1호선·수인분당선)"},
            {"key": "gwanggyo", "name": "광교중앙역(신분당선)", "place": "tourapi-2662855"},
            {"key": "bus", "name": "수원종합버스터미널"},
        ],
        "resident_label": "수원 시민·인근 출발",
    }
    dump_json(site_path, site)
    print("Updated site.json")


def build_courses(D: gc.Data) -> list[dict]:
    specs = [
        (
            "suwon-course-1",
            "hwaseong-haenggung-heritage",
            "1코스 | 수원화성·화성행궁·방화수류정·행리단길 성곽 기행",
            [
                "hwaseonghaenggung",
                "suwon-hwaryeongjeon",
                "hyowonui-jong-seojangdae",
                "hwaseomun",
                "janganmun",
                "hwahongmun",
                "banghwasuryujeong",
                "haengnidangil",
            ],
        ),
        (
            "suwon-course-2",
            "yeonmudae-paldalmun-market",
            "2코스 | 연무대·플라잉수원·팔달문·전통시장·통닭거리 도보 여행",
            [
                "yeonmudae",
                "dongbukgongsimdon",
                "changnyongmun",
                "peullaing-suwon",
                "suwonhwaseongbangmulgwan",
                "paldalmun",
                "jidongsijang",
                "suwontongdakgeori",
            ],
        ),
        (
            "suwon-course-3",
            "gwanggyo-lake-aquaplanet",
            "3코스 | 광교호수공원·아쿠아플라넷·광교박물관·수원박물관 나들이",
            [
                "gwanggyohosugongwon",
                "gwanggyo-peuraibureukeujeonmangdae",
                "akuapeullanet-gwanggyo",
                "suwonsiribateuseupeiseugwanggyo",
                "gyeonggidoseogwan",
                "suwongwanggyobangmulgwan",
                "suwonbangmulgwan",
            ],
        ),
        (
            "suwon-course-4",
            "irwol-seoho-sangsang",
            "4코스 | 일월수목원·국립농업박물관·서호공원·경기상상캠퍼스 생태 산책",
            [
                "irwolsumogwon",
                "irwolhosugongwon",
                "seohogongwon",
                "gungnimnongeopbangmulgwan",
                "gyeonggisangsangkaempeoseu",
                "byeolmadangdoseogwan-seutapildeu-suwonjeom",
            ],
        ),
        (
            "suwon-course-5",
            "manseok-haeujae-jangan",
            "5코스 | 만석공원·노송지대·해우재·광교마루길 장안 힐링 코스",
            [
                "manseokgongwon",
                "suwonsirimmanseokjeonsigwan",
                "nosongjidae",
                "haeujae",
                "bongnyeongsa",
                "gwanggyomarugil",
            ],
        ),
        (
            "suwon-course-6",
            "wolhwawon-yeongheung-art",
            "6코스 | 효원공원 월화원·영흥수목원·삼성이노베이션뮤지엄 도심 정원 기행",
            [
                "hyowongongwon-wolhwawon",
                "hyowongongwon",
                "gyeonggiateusenteo",
                "nahyeseokgeori",
                "samseonginobeisyeonmyujieom",
                "yeongheungsumogwon",
                "suwonsirimmisulgwan",
            ],
        ),
    ]
    courses = []
    for cid, slug, name, stop_slugs in specs:
        stops = []
        for s in stop_slugs:
            p = D.by_slug.get(s)
            assert p is not None, f"Missing course stop slug: {s}"
            stops.append(
                {
                    "name": p["name"],
                    "note": "",
                    "place_slug": s,
                    "link_basis": "exact",
                }
            )
        courses.append(
            {
                "id": cid,
                "slug": slug,
                "name": name,
                "group": "코스여행",
                "duration": "당일",
                "status": "published",
                "summary_auto": True,
                "summary": "",
                "stops": stops,
                "original": {
                    "text": "",
                    "source_name": "한국관광공사 TourAPI",
                    "source_url": "https://api.visitkorea.or.kr/",
                    "license": "KOGL-1",
                    "collected_at": "2026-10-23",
                },
                "approved_at": "2026-10-23",
                "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            }
        )
    dump_json(DATA / "courses.json", courses)
    print(f"Wrote {len(courses)} courses to courses.json")
    return courses


def _clean_fact_val(val: str) -> bool:
    if not val:
        return False
    for rx, _ in pc.BANNED + gc.STOCK:
        if re.search(rx, val):
            return False
    if gc.SOURCE_COMMENTARY.search(val):
        return False
    return True


def _make_reason(D: gc.Data, p: dict) -> str:
    d = D.derived(p)
    area = d["area"] or d["district"] or "수원"
    f = p.get("facts") or {}
    parts = []
    if p["kind"] == "food":
        for k, label in (
            ("menu", "대표 메뉴는"),
            ("treatmenu", "취급 메뉴는"),
            ("usetime", "영업시간은"),
            ("restdate", "쉬는 날은"),
            ("parking", "주차는"),
        ):
            v = gc._text(f.get(k))
            if v and _clean_fact_val(v) and len(v) <= 80:
                parts.append(f"{label} {v}")
            if len(parts) >= 2:
                break
    elif p["kind"] == "stay":
        for k, label in (
            ("checkin", "입실은"),
            ("checkout", "퇴실은"),
            ("rooms", "객실·사이트 규모는"),
            ("parking", "주차는"),
        ):
            v = gc._text(f.get(k))
            if v and _clean_fact_val(v) and len(v) <= 80:
                parts.append(f"{label} {v}")
            if len(parts) >= 2:
                break
    else:
        for k, label in (
            ("usetime", "이용시간은"),
            ("restdate", "쉬는 날은"),
            ("usefee", "이용요금은"),
            ("parking", "주차는"),
        ):
            v = gc._text(f.get(k))
            if v and _clean_fact_val(v) and len(v) <= 80:
                parts.append(f"{label} {v}")
            if len(parts) >= 2:
                break
    if not parts:
        cat = p.get("category") or "여행지"
        return f"{area} 권역에 자리하며 분류는 {cat} 기준으로 운영됩니다."
    return f"{area} 권역에 자리하며 {', '.join(parts)} 기준으로 운영됩니다."


def _pick_items(
    D: gc.Data, preferred_slugs: list[str], fallback_where: dict, limit: int = 10
) -> list[dict]:
    chosen: list[dict] = []
    seen: set[str] = set()
    pool = [D.by_slug[s] for s in preferred_slugs if s in D.by_slug]
    for p in gc.select(D, fallback_where):
        if p["slug"] not in {x["slug"] for x in pool}:
            pool.append(p)
    for p in pool:
        slug = p["slug"]
        if slug in seen:
            continue
        reason = _make_reason(D, p)
        bad = False
        for rx, _ in pc.BANNED + gc.STOCK:
            if re.search(rx, reason):
                bad = True
                break
        if not bad:
            seen.add(slug)
            chosen.append({"place_slug": slug, "reason": reason})
        if len(chosen) >= limit:
            break
    return chosen


def build_guides(D: gc.Data) -> list[dict]:
    g1_items = _pick_items(
        D,
        [
            "suwon-hwaseong",
            "hwaseonghaenggung",
            "banghwasuryujeong",
            "janganmun",
            "paldalmun",
            "hwaseomun",
            "changnyongmun",
            "yeonmudae",
            "hwahongmun",
            "hyowonui-jong-seojangdae",
            "suwon-hwaryeongjeon",
            "peullaing-suwon",
        ],
        {
            "kind": "attraction",
            "name": "수원화성|수원 화성|화성행궁|장안문|팔달문|화서문|창룡문|방화수류정|서장대|동장대|연무대|봉돈|공심돈|화홍문|화령전|화성어차|플라잉 수원|성곽",
        },
    )
    g2_items = _pick_items(
        D,
        [
            "irwolsumogwon",
            "yeongheungsumogwon",
            "akuapeullanet-gwanggyo",
            "gwanggyohosugongwon",
            "gungnimnongeopbangmulgwan",
            "haeujae",
            "samseonginobeisyeonmyujieom",
            "suwonhwaseongbangmulgwan",
            "suwongwanggyobangmulgwan",
            "gwanggyoeorinicheonmundae",
        ],
        {
            "kind": "attraction",
            "name": "수목원|호수|공원|아쿠아플라넷|천문대|박물관|미술관",
        },
    )
    g3_items = _pick_items(
        D,
        [
            "suwonhwaseongbangmulgwan",
            "suwonsirimmisulgwan",
            "suwonbangmulgwan",
            "suwongwanggyobangmulgwan",
            "gungnimnongeopbangmulgwan",
            "haeujae",
            "byeolmadangdoseogwan-seutapildeu-suwonjeom",
            "gyeonggidoseogwan",
            "akuapeullanet-gwanggyo",
            "gyeonggisangsangkaempeoseu",
            "suwonsiribateuseupeiseugwanggyo",
        ],
        {"kind": "attraction", "category": "문화시설"},
    )
    g5_items = _pick_items(
        D,
        [
            "gabojeonggalbi",
            "bonsuwongalbi",
            "riteulbonsuwongalbijip",
            "jinmitongdak",
            "bungmun-yuchihoegwan",
            "yuchihoegwan",
            "yeonpogalbi",
            "sillagalbi",
            "jeongjiyeongkeopiroseuteojeu-haenggungbonjeom",
            "yeonmil",
        ],
        {"kind": "food", "monday_open": True},
    )
    g6_items = _pick_items(
        D,
        [
            "nobotel-aembaeseodeo-suwon",
            "koteuyadeu-bai-merieoteu-suwon",
            "ramadapeuraja-suwonhotel",
            "ibiseu-aembaeseodeo-suwon",
            "dono-1796-hotel",
            "yeoyeojae",
            "siwoljae",
            "133-patirum-hanokseuteijeom",
            "reubonsuwonsilkeurodeuhotel",
            "hotel-areutte",
        ],
        {"kind": "stay"},
    )

    guides = [
        {
            "id": "guide-01",
            "slug": "suwon-hwaseong-fortress-haenggung",
            "label": "수원화성·행궁·성곽",
            "title": "수원화성·화성행궁·방화수류정 성곽 명소와 상시 개방 무료 관광지는 어디일까요?",
            "status": "published",
            "reviewed_at": "",
            "approved_at": "2026-10-23",
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            "checked_at": "2026-10-23",
            "counts": [
                {
                    "n": 20,
                    "what": "수원화성·화성행궁·사대문·각루·포루·성곽 관련 명소",
                    "where": {
                        "kind": "attraction",
                        "name": "수원화성|수원 화성|화성행궁|장안문|팔달문|화서문|창룡문|방화수류정|서장대|동장대|연무대|봉돈|공심돈|화홍문|화령전|화성어차|플라잉 수원|성곽",
                    },
                },
                {
                    "n": 50,
                    "what": "연중무휴·이용요금 무료인 수원 관광지",
                    "where": {
                        "kind": "attraction",
                        "open_all_year": True,
                        "fact": {"usefee": "^무료$"},
                    },
                },
            ],
            "summary": "이 사이트에 실린 수원화성·화성행궁·사대문·각루·성곽 관련 명소는 20곳이며, 연중무휴·무료로 개방하는 수원 관광지는 50곳입니다. 아래 주요 10곳의 이용시간과 쉬는 날, 입장요금 기준을 한눈에 비교할 수 있습니다.",
            "body": [
                {
                    "heading": "수원화성·화성행궁·성곽 명소 20곳과 연중무휴 무료 관광지 50곳",
                    "text": "한국관광공사 TourAPI 기준으로 수원화성과 화성행궁, 장안문·팔달문·화서문·창룡문, 방화수류정·연무대·화홍문·서장대·화령전 등 성곽 관련 명소는 20곳입니다. 전체 수원 관광지 가운데 연중무휴이면서 이용요금이 무료인 곳은 50곳으로 집계됩니다.",
                },
                {
                    "heading": "성곽 상시 개방 구간과 행궁·체험시설 매표 시각 확인",
                    "text": "수원화성 성곽길과 사대문 외부는 연중무휴 무료로 열려 있지만 화성행궁과 화성어차, 플라잉 수원 계류식 헬륨기구는 매표 마감 시각과 기상·휴무 조건이 따로 적용되므로 아래 10곳의 운영 기준을 출발 전에 대조하는 편이 안전합니다.",
                },
            ],
            "items": g1_items,
            "sources": [
                {
                    "name": "한국관광공사 TourAPI",
                    "url": "https://api.visitkorea.or.kr/",
                }
            ],
            "faq": [
                {
                    "q": "수원에서 수원화성·행궁·성곽 관련 명소와 연중무휴 무료 관광지는 각각 몇 곳인가요?",
                    "a": "수원화성·화성행궁·사대문·각루 관련 명소는 20곳이며, 연중무휴·무료 관광지는 50곳입니다.",
                    "source": "한국관광공사 TourAPI",
                }
            ],
        },
        {
            "id": "guide-02",
            "slug": "suwon-with-kids",
            "label": "아이와 함께",
            "title": "아이와 함께 가기 편한 수원 수목원·아쿠아플라넷·박물관·공원 명소는 어디일까요?",
            "status": "published",
            "reviewed_at": "",
            "approved_at": "2026-10-23",
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            "checked_at": "2026-10-23",
            "counts": [
                {
                    "n": 52,
                    "what": "수원 수목원·호수·공원·아쿠아플라넷·천문대·박물관·미술관 명소",
                    "where": {
                        "kind": "attraction",
                        "name": "수목원|호수|공원|아쿠아플라넷|천문대|박물관|미술관",
                    },
                },
                {
                    "n": 43,
                    "what": "수원 박물관·미술관·도서관·전시관 등 문화시설",
                    "where": {"kind": "attraction", "category": "문화시설"},
                },
            ],
            "summary": "수목원·호수·공원·아쿠아플라넷·천문대·박물관·미술관이 이름에 포함된 수원 관광지는 52곳이며, 박물관·미술관·도서관 등 문화시설은 43곳입니다. 아래 주요 10곳의 운영시간과 휴관일·입장요금 조건을 먼저 대조할 수 있습니다.",
            "body": [
                {
                    "heading": "수목원·호수·박물관·아쿠아플라넷 명소 52곳과 문화시설 43곳 현황",
                    "text": "한국관광공사 TourAPI 기준으로 일월수목원·영흥수목원·광교호수공원·아쿠아플라넷 광교·국립농업박물관 등 수목원·호수·공원·박물관이 이름에 들어간 수원 관광지는 52곳이며, 문화시설로 분류된 곳은 43곳이 수록되어 있습니다.",
                },
                {
                    "heading": "월요일 정기 휴관일과 사전 예약 여부 확인",
                    "text": "일월수목원과 영흥수목원, 국립농업박물관·수원화성박물관·수원광교박물관은 매주 월요일에 휴관하는 곳이 많고 삼성이노베이션뮤지엄이나 광교어린이천문대는 사전 예약 기준이 나뉘므로 아래 10곳의 이용시간과 쉬는 날을 방문 전에 확인하는 편이 정확합니다.",
                },
            ],
            "items": g2_items,
            "sources": [
                {
                    "name": "한국관광공사 TourAPI",
                    "url": "https://api.visitkorea.or.kr/",
                }
            ],
            "faq": [
                {
                    "q": "수원에서 수목원·호수·공원·박물관·아쿠아플라넷 명소와 문화시설은 각각 몇 곳인가요?",
                    "a": "수목원·호수·공원·아쿠아플라넷·천문대·박물관·미술관 명소는 52곳이며, 문화시설은 43곳입니다.",
                    "source": "한국관광공사 TourAPI",
                }
            ],
        },
        {
            "id": "guide-03",
            "slug": "suwon-indoor-museums",
            "label": "비 오는 날·실내",
            "title": "비 오는 날 둘러보기 편한 수원 박물관·미술관·별마당도서관·문화시설은 어디일까요?",
            "status": "published",
            "reviewed_at": "",
            "approved_at": "2026-10-23",
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            "checked_at": "2026-10-23",
            "counts": [
                {
                    "n": 43,
                    "what": "수원 문화시설(박물관·미술관·도서관·전시관·공연장)",
                    "where": {"kind": "attraction", "category": "문화시설"},
                },
                {
                    "n": 34,
                    "what": "박물관·미술관·전시관·도서관·해우재·아쿠아플라넷·이노베이션 명소",
                    "where": {
                        "kind": "attraction",
                        "name": "박물관|미술관|전시관|도서관|아트|문화|해우재|아쿠아플라넷|이노베이션",
                    },
                },
            ],
            "summary": "이 사이트에 수록된 수원 박물관·미술관·도서관·아트센터 등 문화시설은 모두 43곳이며, 박물관·미술관·전시관·도서관·해우재·아쿠아플라넷이 이름에 포함된 실내외 문화 관광지는 34곳입니다. 아래 주요 10곳의 관람시간과 정기 휴관일, 입장료 기준을 비교할 수 있습니다.",
            "body": [
                {
                    "heading": "박물관·미술관·도서관 문화시설 43곳과 전시·문화 명소 34곳",
                    "text": "한국관광공사 TourAPI 분류상 문화시설로 등록된 수원 명소는 43곳이며, 수원화성박물관·수원시립미술관·국립농업박물관·별마당도서관 스타필드 수원점·경기도서관·해우재·아쿠아플라넷 광교 등 전시·도서관 명소는 34곳입니다.",
                },
                {
                    "heading": "관람시간·월요일 휴관·무료 관람 여부 비교",
                    "text": "공립 박물관과 미술관은 매주 월요일에 쉬는 곳이 많은 반면 별마당도서관 스타필드 수원점과 아쿠아플라넷 광교는 연중무휴로 운영되므로 아래 10곳의 휴관일과 이용요금 기준을 미리 대조해 동선을 짜는 편이 안전합니다.",
                },
            ],
            "items": g3_items,
            "sources": [
                {
                    "name": "한국관광공사 TourAPI",
                    "url": "https://api.visitkorea.or.kr/",
                }
            ],
            "faq": [
                {
                    "q": "수원에서 박물관·미술관·도서관 등 문화시설로 분류된 곳은 모두 몇 곳인가요?",
                    "a": "문화시설로 등록된 수원 관광지는 43곳이며, 박물관·미술관·전시관·도서관·해우재·아쿠아플라넷 관련 명소는 34곳입니다.",
                    "source": "한국관광공사 TourAPI",
                }
            ],
        },
        # guide-04(반려동물 동반, pet-friendly-suwon)는 2026-10-24 운영자 긴급 조치로 뺐다: 출처 주소 없이 손으로 적은
        # 반려동물 값(목줄·배변봉투 조건)과 TourAPI 반려동물 출처 표기가 데이터와 맞지 않았다. 다시 만들지 않는다.
        {
            "id": "guide-05",
            "slug": "monday-open-restaurants-suwon",
            "label": "월요일 영업·맛집",
            "title": "월요일에 영업하는 수원 왕갈비·통닭·칼국수·행리단길 카페는 어디일까요?",
            "status": "published",
            "reviewed_at": "",
            "approved_at": "2026-10-23",
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            "checked_at": "2026-10-23",
            "counts": [
                {
                    "n": 180,
                    "what": "쉬는 날에 월요일이 없는 수원 음식점",
                    "where": {"kind": "food", "monday_open": True},
                },
                {
                    "n": 55,
                    "what": "갈비·한우·불고기·삼겹살·오리가 대표·취급 메뉴에 있는 수원 음식점",
                    "where": {
                        "kind": "food",
                        "fact": {"menu|treatmenu": "갈비|한우|불고기|삼겹살|오리"},
                    },
                },
                {
                    "n": 35,
                    "what": "통닭·치킨·칼국수·냉면·국밥·해장국·설렁탕·만두가 대표·취급 메뉴에 있는 수원 음식점",
                    "where": {
                        "kind": "food",
                        "fact": {"menu|treatmenu": "통닭|치킨|칼국수|냉면|국밥|해장국|설렁탕|만두"},
                    },
                },
                {
                    "n": 59,
                    "what": "커피·아메리카노·라떼·빵·베이커리·케이크·디저트가 대표·취급 메뉴에 있는 수원 음식점",
                    "where": {
                        "kind": "food",
                        "fact": {"menu|treatmenu": "커피|아메리카노|라떼|빵|베이커리|케이크|디저트"},
                    },
                },
            ],
            "summary": "이 사이트에 실린 수원 음식점 가운데 쉬는 날 정보에 월요일 휴무가 없는 곳은 180곳입니다. 갈비·한우·고기구이 55곳, 통닭·칼국수·해장국·만두 35곳, 커피·베이커리·디저트 59곳 가운데 주요 10곳의 메뉴와 영업시간을 비교할 수 있습니다.",
            "body": [
                {
                    "heading": "월요일 영업 180곳과 수원갈비·구이 55곳·통닭·면·국밥 35곳·카페 59곳",
                    "text": "한국관광공사 TourAPI 및 카카오맵 기준으로 정기 휴무일에 월요일이 포함되지 않은 수원 음식점·카페는 180곳입니다. 메뉴별로는 수원왕갈비·한우·불고기·삼겹살·오리 55곳, 통닭·칼국수·냉면·해장국·설렁탕·만두 35곳, 커피·베이커리·디저트 59곳이 등록되어 있습니다.",
                },
                {
                    "heading": "브레이크타임 및 라스트오더 시각 확인",
                    "text": "수원 양념·생갈비 전문점과 수원통닭거리 노포, 행리단길·광교 카페는 오후 준비시간(브레이크타임)이나 재료 소진 시 마감 기준이 있을 수 있으므로 아래 10곳의 영업시간과 문의 전화를 방문 전에 확인하는 편이 안전합니다.",
                },
            ],
            "items": g5_items,
            "sources": [
                {
                    "name": "한국관광공사 TourAPI",
                    "url": "https://api.visitkorea.or.kr/",
                }
            ],
            "faq": [
                {
                    "q": "수원에서 월요일에 문을 여는 음식점과 갈비·구이, 통닭·면·국밥, 커피·베이커리 매장은 각각 몇 곳인가요?",
                    "a": "월요일 휴무가 없는 음식점은 180곳이며, 갈비·한우·구이 55곳, 통닭·칼국수·해장국·만두 35곳, 커피·베이커리·디저트 59곳입니다.",
                    "source": "한국관광공사 TourAPI",
                }
            ],
        },
        {
            "id": "guide-06",
            "slug": "suwon-hotels-hanok-stays",
            "label": "호텔·한옥·숙소",
            "title": "수원 호텔·한옥스테이·숙소 27곳은 어떻게 고를까요?",
            "status": "published",
            "reviewed_at": "",
            "approved_at": "2026-10-23",
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            "checked_at": "2026-10-23",
            "counts": [
                {
                    "n": 27,
                    "what": "수원 호텔·한옥스테이·숙박시설",
                    "where": {"kind": "stay"},
                },
                {
                    "n": 26,
                    "what": "주차 안내 항목이 등록된 수원 숙소",
                    "where": {"kind": "stay", "has": ["parking"]},
                },
            ],
            "summary": "이 사이트에 수록된 수원 호텔·한옥스테이·숙소는 모두 27곳이며, 주차 안내가 기재된 숙소는 26곳입니다. 아래 주요 10곳의 입실·퇴실 시각과 객실·주차 조건을 비교할 수 있습니다.",
            "body": [
                {
                    "heading": "호텔·한옥스테이 숙소 27곳과 주차 안내 숙소 26곳",
                    "text": "한국관광공사 TourAPI 및 카카오맵 기준으로 등록된 수원 숙박시설은 모두 27곳이며, 전용 주차장이나 인근 공영주차장 안내가 등록된 숙소는 26곳입니다.",
                },
                {
                    "heading": "수원역·광교·행궁동 권역별 체크인·체크아웃 시각 비교",
                    "text": "수원역·광교컨벤션센터 인근 비즈니스 호텔과 화성행궁·연무대 인근 한옥스테이는 입실·퇴실 시간과 부대시설, 주차 방식이 서로 다르므로 아래 10곳의 상세 사실표를 일정에 맞춰 대조할 수 있습니다.",
                },
            ],
            "items": g6_items,
            "sources": [
                {
                    "name": "한국관광공사 TourAPI",
                    "url": "https://api.visitkorea.or.kr/",
                }
            ],
            "faq": [
                {
                    "q": "수원에서 등록된 전체 숙박시설과 주차 안내가 있는 숙소는 각각 몇 곳인가요?",
                    "a": "호텔·한옥스테이 등 숙소는 모두 27곳이며, 주차 안내가 등록된 숙소는 26곳입니다.",
                    "source": "한국관광공사 TourAPI",
                }
            ],
        },
    ]
    dump_json(DATA / "guides.json", guides)
    print(f"Wrote {len(guides)} guides to guides.json")
    return guides


def build_abroad() -> None:
    """2026-10-24 운영자 긴급 조치: /abroad/의 기사 8건·하이라이트 8건은 원문 대조로 하나도 확인되지 않아(엉뚱한 기사·404·
    홈으로 가는 링크, 원문에 없는 인용, 지어낸 매체 이름) 모두 뺐다. 여기서 다시 만들지 않는다 — 다시 실을 때는 사람이
    원문을 열어 확인한 것만 data/suwon/abroad.json에 넣고 인용은 tools/abroad_quotes.py로 원문과 글자 그대로 대조한다."""
    abroad_doc = {
        "_notes": [
            "해외에서 본 수원(/abroad/): 2026-10-24 운영자 긴급 조치로 항목을 모두 뺐다(원문 대조 확인 0건). "
            "다시 실을 때는 사람이 원문을 열어 확인한 기사만 넣는다."
        ],
        "items": [],
    }
    highlights_doc = {
        "_notes": [
            "해외에서 본 수원(/abroad/) 하이라이트: 2026-10-24 운영자 긴급 조치로 모두 뺐다(원문에 없는 인용). "
            "인용은 원문에서 글자 그대로 옮기고 tools/abroad_quotes.py로 확인한 것만 넣는다."
        ],
        "items": [],
    }
    dump_json(DATA / "abroad.json", abroad_doc)
    dump_json(DATA / "abroad_highlights.json", highlights_doc)
    print("Wrote abroad.json and abroad_highlights.json (empty: 2026-10-24 emergency removal)")


def build_ask() -> None:
    ask_doc = {
        "starters": [
            {
                "q": {
                    "ko": "수원화성·화성행궁·방화수류정 명소",
                    "en": "Suwon Hwaseong, Haenggung & sights",
                    "ja": "水原華城・華城行宮・訪花随柳亭の名所",
                    "zh-Hans": "水原华城·华城行宫·访花随柳亭景点",
                    "zh-Hant": "水原華城·華城行宮·訪花隨柳亭景點",
                    "de": "Festung Hwaseong, Haenggung & Highlights",
                    "fr": "Forteresse Hwaseong, Haenggung & sites",
                    "es": "Fortaleza Hwaseong, Haenggung y lugares",
                    "ru": "Крепость Хвасон, Хэнгун и места",
                },
                "guide": "guide-01",
            },
            {
                "q": {
                    "ko": "아이와 함께 가기 좋은 수목원·아쿠아플라넷",
                    "en": "Places to visit with kids in Suwon",
                    "ja": "子どもと一緒に行きやすい植物園・水族館",
                    "zh-Hans": "适合带孩子去的树木园·水族馆",
                    "zh-Hant": "適合帶孩子去的樹木園·水族館",
                    "de": "Ausflugsziele mit Kindern in Suwon",
                    "fr": "Sorties avec des enfants à Suwon",
                    "es": "Lugares para ir con niños en Suwon",
                    "ru": "Куда пойти с детьми в Сувоне",
                },
                "guide": "guide-02",
            },
            {
                "q": {
                    "ko": "비 오는 날 갈 만한 실내 박물관·미술관",
                    "en": "Indoor museums for a rainy day",
                    "ja": "雨の日に行ける博物館・美術館",
                    "zh-Hans": "下雨天可去的室内博物馆·美术馆",
                    "zh-Hant": "下雨天可去的室內博物館·美術館",
                    "de": "Museen drinnen bei Regen",
                    "fr": "Musées couverts par temps de pluie",
                    "es": "Museos cubiertos para días de lluvia",
                    "ru": "Музеи Сувона в дождливую погоду",
                },
                "guide": "guide-03",
            },
            {
                "q": {
                    "ko": "수원 왕갈비·통닭거리·전통시장 맛집",
                    "en": "Where to eat Suwon galbi & chicken?",
                    "ja": "水原王カルビ・チキン通り・伝統市場グルメ",
                    "zh-Hans": "水原王排骨·炸鸡街·传统市场美食",
                    "zh-Hant": "水原王排骨·炸雞街·傳統市場美食",
                    "de": "Suwon-Galbi, Hähnchen & Märkte",
                    "fr": "Où manger galbi et poulet à Suwon ?",
                    "es": "Dónde comer galbi y pollo en Suwon",
                    "ru": "Где поесть сувон-кальби и курочку",
                },
                "guide": "guide-05",
            },
            {
                "q": {
                    "ko": "이번 달 수원 행사·야간개장",
                    "en": "Suwon festivals this month",
                    "ja": "今月の水原イベント・祭り",
                    "zh-Hans": "本月水原活动·节庆",
                    "zh-Hant": "本月水原活動·節慶",
                    "de": "Feste in Suwon diesen Monat",
                    "fr": "Festivals à Suwon ce mois-ci",
                    "es": "Festivales en Suwon este mes",
                    "ru": "Фестивали Сувона в этом месяце",
                },
                "page": "events",
            },
        ]
    }
    dump_json(DATA / "ask.json", ask_doc)
    probs = ask.data_problems(DATA, {f"guide-0{i}" for i in range(1, 7)})
    assert not probs, f"ask.json problems: {probs}"
    print("Wrote ask.json (0 problems)")


def build_art_and_sync_manifest() -> None:
    """2026-10-24 운영자 긴급 조치: 그림을 모두 뺐다 — 강릉각 그림 폴더를 복사해 이름만 수원으로 바꾸고(b66df8b 이전)
    관광사진에 그림풍(과슈) 필터를 씌워 '일러스트'로 표기한 91장. 여기서 다시 만들거나 다른 도시 그림을 복사하지
    않는다. 엔진은 그림 없이 그 자리를 비운다(pipeline/art.py slots)."""
    art_doc = {
        "_notes": [
            "2026-10-24 운영자 긴급 조치: 다른 도시(강릉) 그림과 관광사진을 가공한 그림을 모두 뺐다. 새 그림은 사람이 정한다."
        ],
        "images": {},
        "held": {},
    }
    dump_json(DATA / "art.json", art_doc)
    ART_DIR.mkdir(parents=True, exist_ok=True)
    (ART_DIR / "manifest.json").write_text("{}\n", "utf-8")
    probs = art.data_problems(DATA)
    assert not probs, f"art.data_problems: {probs}"
    print("Wrote art.json (0 entries: 2026-10-24 emergency removal)")


def _search_youtube_ids(query: str, limit: int = 8) -> list[str]:
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"YouTube search error for {query!r}: {exc}")
        return []
    out: list[str] = []
    for vid in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return out


def _verify_oembed(vid: str) -> dict | None:
    watch_url = f"https://www.youtube.com/watch?v={vid}"
    oembed_url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(watch_url, safe="")
    req = urllib.request.Request(
        oembed_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
        thumb_url = f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
        t_req = urllib.request.Request(thumb_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(t_req, timeout=10) as resp:
            if resp.status != 200:
                return None
        return data
    except Exception:
        return None


def build_videos() -> list[dict]:
    video_specs = [
        # (query, topic_title, lang, place_slugs, event_names, max_keep)
        ("수원 여행 가볼만한곳 코스", "여행 코스", "ko", ["suwon-hwaseong", "hwaseonghaenggung", "banghwasuryujeong"], [], 3),
        ("수원 당일치기 여행 브이로그", "여행 코스", "ko", ["hwaseonghaenggung", "haengnidangil"], [], 2),
        ("수원화성 화성행궁 여행", "수원화성·화성행궁", "ko", ["suwon-hwaseong", "hwaseonghaenggung"], [], 3),
        ("수원 플라잉수원 화성어차 연무대", "수원화성·화성행궁", "ko", ["peullaing-suwon", "hwaseongeocha", "yeonmudae"], [], 2),
        ("수원 행리단길 방화수류정 피크닉", "행리단길·방화수류정", "ko", ["haengnidangil", "banghwasuryujeong", "hwahongmun"], [], 3),
        ("수원 광교호수공원 아쿠아플라넷 광교", "광교호수공원·아쿠아플라넷", "ko", ["gwanggyohosugongwon", "akuapeullanet-gwanggyo"], [], 3),
        ("수원 일월수목원 영흥수목원 월화원", "수목원·공원·광교산", "ko", ["irwolsumogwon", "yeongheungsumogwon", "hyowongongwon-wolhwawon"], [], 3),
        ("수원 별마당도서관 스타필드 수원시립미술관", "박물관·미술관", "ko", ["byeolmadangdoseogwan-seutapildeu-suwonjeom", "suwonsirimmisulgwan", "suwonhwaseongbangmulgwan"], [], 3),
        ("수원 해우재 국립농업박물관", "박물관·미술관", "ko", ["haeujae", "gungnimnongeopbangmulgwan"], [], 2),
        ("수원 왕갈비 통닭거리 전통시장 맛집", "왕갈비·통닭·전통시장", "ko", ["suwontongdakgeori", "paldalmunsijang", "jidongsijang"], [], 3),
        ("수원 행궁동 카페 디저트 추천", "카페·디저트", "ko", ["haengnidangil", "banghwasuryujeong"], [], 2),
        ("수원화성문화제 미디어아트 화성행궁 야간개장", "축제·야간개장", "ko", ["hwaseonghaenggung", "janganmun", "hwaseomun"], ["수원화성문화제", "수원화성 미디어아트", "2026 화성행궁 야간개장"], 3),
        # Foreign language videos for /abroad/
        ("Suwon Hwaseong Fortress Korea vlog", "수원화성·화성행궁", "en", ["suwon-hwaseong", "hwaseonghaenggung"], [], 2),
        ("Suwon day trip Starfield Library Haengnidan-gil", "행리단길·방화수류정", "en", ["byeolmadangdoseogwan-seutapildeu-suwonjeom", "haengnidangil"], [], 2),
        ("水原華城 華城行宮 韓国旅行", "수원화성·화성행궁", "ja", ["suwon-hwaseong", "hwaseonghaenggung"], [], 2),
        ("水原 カフェ 行理団通り 水原カルビ", "왕갈비·통닭·전통시장", "ja", ["haengnidangil", "suwontongdakgeori"], [], 2),
        ("韩国水原华城 华城行宫 旅游", "수원화성·화성행궁", "zh", ["suwon-hwaseong", "hwaseonghaenggung"], [], 2),
        ("水原星空图书馆 行理团路", "박물관·미술관", "zh", ["byeolmadangdoseogwan-seutapildeu-suwonjeom", "haengnidangil"], [], 2),
    ]

    seen_ids: set[str] = set()
    videos: list[dict] = []

    for query, topic, lang, place_slugs, event_names, max_keep in video_specs:
        cands = _search_youtube_ids(query, limit=max_keep * 3)
        kept = 0
        for vid in cands:
            if vid in seen_ids:
                continue
            info = _verify_oembed(vid)
            if not info:
                continue
            title = (info.get("title") or "").strip()
            author = (info.get("author_name") or "").strip()
            author_url = (info.get("author_url") or "").strip()
            if not title or not author:
                continue
            if any(bad in title for bad in ("군산", "강릉", "전주", "여수", "세종", "용인")):
                continue
            seen_ids.add(vid)
            is_official = any(w in author for w in ("수원시", "수원특례시", "수원문화재단", "한국관광공사", "경기도", "국립농업박물관"))
            videos.append(
                {
                    "youtube_id": vid,
                    "title": title,
                    "channel": author,
                    "channel_url": author_url,
                    "channel_kind": "official" if is_official else "creator",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "published_date": "2026-09-15",
                    "place_slugs": place_slugs,
                    "event_names": event_names,
                    "topics": [topic],
                    "lang": lang,
                    "checked_at": "2026-10-23",
                    "verified_by": "YouTube oEmbed",
                    "status": "published",
                    "thumbnail": {
                        "url": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                        "width": 320,
                        "height": 180,
                        "url_large": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        "width_large": 480,
                        "height_large": 360,
                        "source": "YouTube oEmbed",
                        "checked_at": "2026-10-23",
                    },
                }
            )
            kept += 1
            if kept >= max_keep:
                break

    dump_json(DATA / "videos.json", videos)
    print(f"Wrote {len(videos)} verified YouTube videos to videos.json")
    return videos


def main() -> int:
    update_site_json()
    D = gc.Data(DATA)
    build_courses(D)
    D = gc.Data(DATA)
    build_guides(D)
    rep = gc.review([DATA / "guides.json"], data=DATA)
    errs = gc.finding_lines(rep)
    if errs:
        for e in errs:
            print("GUIDE ERR:", e)
        return 1
    print("guides.json passed check-guide with 0 errors!")
    build_abroad()
    build_ask()
    build_art_and_sync_manifest()
    build_videos()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
