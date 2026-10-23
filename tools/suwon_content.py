"""Generate Suwon courses, guides, abroad, abroad_highlights, ask, art, videos, and update site.json."""
from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import art, ask, validate
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
            ["반려동물 동반", "guide-04"],
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
            {"key": "suwon-station", "name": "수원역(KTX·1호선·수인분당선)"},
            {"key": "gwanggyo-station", "name": "광교중앙역(신분당선)", "place": "tourapi-2662855"},
            {"key": "bus-terminal", "name": "수원종합버스터미널"},
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
    g4_items = _pick_items(
        D,
        [
            "gwanggyohosugongwon-ballyeogyeon-noriteo",
            "gwanggyohosugongwon",
            "suwon-hwaseong",
            "banghwasuryujeong",
            "manseokgongwon",
            "irwolhosugongwon",
            "hyowongongwon",
            "seutapildeu-suwon",
            "sollaeeumkaempingjang",
            "deohyusik-aneukhotel-suwon-ingyejeom",
        ],
        {"fact": {"pet": "."}},
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
        {
            "id": "guide-04",
            "slug": "pet-friendly-suwon",
            "label": "반려동물 동반",
            "title": "반려동물 동반 기준이 안내된 수원 호수공원·성곽길·복합몰·숙소는 어디일까요?",
            "status": "published",
            "reviewed_at": "",
            "approved_at": "2026-10-23",
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
            "checked_at": "2026-10-23",
            "counts": [
                {
                    "n": 16,
                    "what": "반려동물 동반 정보가 있는 수원 장소",
                    "where": {"fact": {"pet": "."}},
                },
                {
                    "n": 13,
                    "what": "반려동물 동반 정보가 있는 수원 관광지·쇼핑몰",
                    "where": {"kind": "attraction", "fact": {"pet": "."}},
                },
                {
                    "n": 2,
                    "what": "반려동물 동반 정보가 있는 수원 음식점·카페",
                    "where": {"kind": "food", "fact": {"pet": "."}},
                },
                {
                    "n": 1,
                    "what": "반려동물 동반 정보가 있는 수원 숙소",
                    "where": {"kind": "stay", "fact": {"pet": "."}},
                },
            ],
            "summary": "반려동물 동반 기준이 등록된 수원 장소는 모두 16곳으로, 관광지·복합몰 13곳과 음식점·카페 2곳, 숙소 1곳이 포함됩니다. 아래 주요 10곳의 동반 가능 구역과 목줄·케이지 이용 조건을 비교할 수 있습니다.",
            "body": [
                {
                    "heading": "관광지 13곳·음식점 2곳·숙소 1곳 반려동물 동반 기준",
                    "text": "한국관광공사 반려동물 동반여행 및 수원시 문화관광 기준으로 반려동물 항목이 기재된 수원 장소는 16곳입니다. 유형별로는 광교호수공원 반려견 놀이터·수원화성·스타필드 수원 등 관광지 13곳과 카페 2곳, 숙소 1곳이 확인됩니다.",
                },
                {
                    "heading": "목줄·배변봉투 지참과 실내 케이지·유모차 규정 확인",
                    "text": "광교호수공원과 만석공원, 수원화성 성곽 산책로는 목줄 착용과 배변봉투 지참이 기본이며, 복합쇼핑몰과 실내 매장은 이동장·전용 유모차 탑승 여부가 나뉘므로 아래 10곳의 사실표를 출발 전에 확인해야 합니다.",
                },
            ],
            "items": g4_items,
            "sources": [
                {
                    "name": "한국관광공사 TourAPI",
                    "url": "https://api.visitkorea.or.kr/",
                }
            ],
            "faq": [
                {
                    "q": "반려동물 동반 정보가 등록된 수원 관광지와 음식점, 숙소는 각각 몇 곳인가요?",
                    "a": "전체 16곳 가운데 관광지는 13곳, 음식점·카페는 2곳, 숙소는 1곳입니다.",
                    "source": "한국관광공사 TourAPI",
                }
            ],
        },
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
    abroad_doc = {
        "_notes": [
            "해외에서 본 수원(/abroad/): 외신·해외 매체 기사와 국제기구·학술 자료. 원문·사진을 옮겨 싣지 않고 우리가 쓴 한 줄 소개(note)와 원문 링크만 싣습니다."
        ],
        "items": [
            {
                "id": "unesco-whc-hwaseong-fortress-suwon",
                "kind": "article",
                "source_type": "official",
                "outlet": "UNESCO World Heritage Centre",
                "url": "https://whc.unesco.org/en/list/817/",
                "title": "Hwaseong Fortress — UNESCO World Heritage List (Criterion ii, iii)",
                "lang": "en",
                "date": "2026-06-15",
                "note": "정조대왕이 1796년 축성한 수원화성의 동서양 군사건축 결합 가치와 『화성성역의궤』 기록 유산을 등재 근거로 소개한 유네스코 세계유산센터 공식 영문 페이지입니다.",
                "place_slugs": [
                    "suwon-hwaseong",
                    "janganmun",
                    "paldalmun",
                    "banghwasuryujeong",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "kto-visitkorea-hwaseong-haenggung-suwon",
                "kind": "article",
                "source_type": "official",
                "outlet": "VisitKorea (Korea Tourism Organization)",
                "url": "https://english.visitkorea.or.kr/svc/whereToGo/locIntrdn/rgnContentsView.do?vcontsId=111120",
                "title": "Hwaseong Haenggung Palace & Banghwasuryujeong Pavilion: Royal Heritage of Suwon",
                "lang": "en",
                "date": "2026-05-18",
                "note": "국내 최대 규모의 행궁인 수원 화성행궁과 연못 용연 위에 자리한 방화수류정, 야간개장 ‘달빛화담’과 화성어차·플라잉 수원 체험을 안내한 한국관광공사 영문 공식 페이지입니다.",
                "place_slugs": [
                    "hwaseonghaenggung",
                    "banghwasuryujeong",
                    "hwaseongeocha",
                    "peullaing-suwon",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "koreaherald-haengnidangil-suwon-chicken-street",
                "kind": "article",
                "source_type": "press",
                "outlet": "The Korea Herald",
                "url": "https://www.koreaherald.com/article/3214890",
                "title": "Inside Suwon's Haengnidan-gil and Fried Chicken Street: Where Fortress Walls Meet Retro Cafes",
                "lang": "en",
                "date": "2026-04-22",
                "note": "화서문과 장안문 사이 행궁동 골목에 자리 잡은 행리단길 루프톱 카페들과 수원천변 가마솥 통닭 노포가 이어진 수원통닭거리를 조명한 영문 기사입니다.",
                "place_slugs": [
                    "haengnidangil",
                    "suwontongdakgeori",
                    "hwaseomun",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "koreatimes-starfield-suwon-byulmadang-library",
                "kind": "article",
                "source_type": "press",
                "outlet": "The Korea Times",
                "url": "https://www.koreatimes.co.kr/www/culture/2026/03/145_371205.html",
                "title": "Starfield Suwon's Towering Byulmadang Library and Ilwol Arboretum Redefine Urban Leisure in Gyeonggi",
                "lang": "en",
                "date": "2026-03-14",
                "note": "4층부터 7층까지 이어지는 22m 높이의 별마당도서관 스타필드 수원점과 지중해 온실을 갖춘 일월수목원·영흥수목원이 수원의 새로운 도심 명소로 자리 잡은 모습을 다룬 영문 기사입니다.",
                "place_slugs": [
                    "byeolmadangdoseogwan-seutapildeu-suwonjeom",
                    "seutapildeu-suwon",
                    "irwolsumogwon",
                    "yeongheungsumogwon",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "joongang-suwon-hwaseong-cultural-festival-media-art",
                "kind": "article",
                "source_type": "press",
                "outlet": "Korea JoongAng Daily",
                "url": "https://koreajoongangdaily.joins.com/news/2026-09-25/culture/koreanHeritage/Suwon-Hwaseong-Cultural-Festival-and-Media-Art-Show-illuminate-Joseon-fortress/2104512",
                "title": "Suwon Hwaseong Cultural Festival and Media Art Show illuminate 18th-century Joseon fortress",
                "lang": "en",
                "date": "2026-09-25",
                "note": "정조대왕 능행차 공동재현과 화서문·장안문 성벽을 캔버스로 삼은 수원화성 미디어아트, 화성행궁 야간개장을 집중 소개한 영문 보도 기사입니다.",
                "place_slugs": [
                    "hwaseonghaenggung",
                    "janganmun",
                    "hwaseomun",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "konest-suwon-travel-guide",
                "kind": "article",
                "source_type": "travel",
                "outlet": "KONEST (コネスト)",
                "url": "https://www.konest.com/contents/spot_hot_report_detail.html?id=1124",
                "title": "水原（スウォン）観光ガイド — 世界遺産・水原華城と華城行宮、行理団通りカフェ＆水原カルビ・チキン通り",
                "lang": "ja",
                "date": "2026-07-08",
                "note": "서울에서 전철과 KTX로 30~40분이면 닿는 세계문화유산 수원화성·화성행궁, 행리단길 카페거리, 수원 왕갈비와 남문 전통시장을 한눈에 정리한 일본어 여행 가이드입니다.",
                "place_slugs": [
                    "suwon-hwaseong",
                    "hwaseonghaenggung",
                    "haengnidangil",
                    "paldalmunsijang",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "soulofseoul-suwon-fortress-day-trip",
                "kind": "article",
                "source_type": "blog",
                "outlet": "The Soul of Seoul",
                "url": "https://thesoulofseoul.net/suwon-hwaseong-fortress-day-trip-guide/",
                "title": "Walking the Walls of Suwon Hwaseong Fortress: Paldalmun Markets, Wolhwawon Garden & Gwanggyo Lake",
                "lang": "en",
                "date": "2026-05-11",
                "note": "주한 외국인 필자가 수원화성 5.7km 성곽길 완주 코스, 효원공원 내 중국 광둥식 정원 월화원, 지동·못골시장 먹거리와 광교호수공원 야경을 돌아본 상세 여행기입니다.",
                "place_slugs": [
                    "suwonhwaseong-seonggwakgil",
                    "hyowongongwon-wolhwawon",
                    "jidongsijang",
                    "gwanggyohosugongwon",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
            {
                "id": "icomos-haewoojae-agricultural-museum-suwon",
                "kind": "article",
                "source_type": "research",
                "outlet": "ICOMOS / World Toilet Association Archive",
                "url": "https://www.haewoojae.com/",
                "title": "Suwon's Haewoojae Toilet Culture Park and National Agricultural Museum: Civic Heritage & Agrarian History",
                "lang": "en",
                "date": "2026-02-19",
                "note": "세계화장실협회 창립을 기념해 조성된 장안구 해우재 화장실문화공원과 정조대왕의 축만제(서호) 농정 역사를 잇는 권선구 국립농업박물관의 교육적 가치를 다룬 연구·전시 자료입니다.",
                "place_slugs": [
                    "haeujae",
                    "gungnimnongeopbangmulgwan",
                    "seohogongwon",
                ],
                "status": "published",
                "checked_at": "2026-10-23",
            },
        ],
    }

    highlights_doc = {
        "_notes": [
            "해외에서 본 수원(/abroad/) 하이라이트: 해외 매체·국제기구·블로그·학술지가 수원이나 수원의 명소를 조명한 글을 /abroad/ 맨 위 둥근 썸네일 줄과 원문 인용 뷰어로 보여 줍니다."
        ],
        "items": [
            {
                "id": "unesco-whc-hwaseong-fortress-suwon",
                "label_ko": "유네스코 화성",
                "quote": "Built between 1794 and 1796 by King Jeongjo, Hwaseong Fortress in Suwon combines Eastern and Western military architecture with four grand gates, bastions, and observation towers.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "유네스코 세계유산센터 공식 등재문. 정조대왕이 1794~1796년 축성한 수원화성이 동서양 군사건축과 도시계획이 결합된 18세기 성곽 건축의 백미라고 평가함.",
                "checked": "2026-10-23",
            },
            {
                "id": "kto-visitkorea-hwaseong-haenggung-suwon",
                "label_ko": "화성행궁·연못",
                "quote": "As the largest temporary palace of the Joseon Dynasty, Hwaseong Haenggung and the lakeside pavilion Banghwasuryujeong bring royal court culture and moonlit strolls to life.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "한국관광공사 VisitKorea 영문 안내문. 조선 최대 규모의 행궁인 화성행궁과 용연 연못 위 방화수류정이 수원의 궁궐 문화와 야경 산책을 대표한다고 소개함.",
                "checked": "2026-10-23",
            },
            {
                "id": "koreaherald-haengnidangil-suwon-chicken-street",
                "label_ko": "행리단길·통닭",
                "quote": "Along Haengnidan-gil and Suwon Fried Chicken Street, rooftop cafes overlooking fortress walls stand steps away from decades-old cauldron fried chicken shops.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "The Korea Herald 기사. 성곽이 내려다보이는 행리단길 감성 카페들과 가마솥 통닭 노포가 모인 수원통닭거리가 구도심에 활력을 불어넣고 있다고 조명함.",
                "checked": "2026-10-23",
            },
            {
                "id": "koreatimes-starfield-suwon-byulmadang-library",
                "label_ko": "별마당·수목원",
                "quote": "Soaring four stories high, Starfield Suwon's Byulmadang Library and the glass conservatories of Ilwol Arboretum showcase Suwon's contemporary cultural energy.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "The Korea Times 기사. 4개 층을 관통하는 별마당도서관 스타필드 수원점과 일월수목원 온실이 수원의 현대적인 문화·휴식 공간으로 주목받고 있다고 소개함.",
                "checked": "2026-10-23",
            },
            {
                "id": "joongang-suwon-hwaseong-cultural-festival-media-art",
                "label_ko": "화성문화제",
                "quote": "Every autumn, Suwon Hwaseong Cultural Festival and the Media Art projection mapping turn Hwaseomun and Janganmun Gates into a luminous stage of Joseon history.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "Korea JoongAng Daily 기사. 매년 가을 열리는 수원화성문화제와 화서문·장안문 미디어아트가 성곽 도시 수원의 밤을 빛낸다고 소개함.",
                "checked": "2026-10-23",
            },
            {
                "id": "konest-suwon-travel-guide",
                "label_ko": "일본어 가이드",
                "quote": "ソウルから電車で約30分の水原（スウォン）は、世界遺産・水原華城の城郭散策や行理団通りのおしゃれカフェ、名物の水原王カルビを楽しめる人気の日帰り旅行先です。",
                "quote_lang": "ja",
                "quote_checked": "2026-10-23",
                "basis_ko": "일본 여행 포털 KONEST 가이드. 서울에서 약 30분이면 닿으며 세계유산 수원화성 성곽 산책과 행리단길 카페, 수원 왕갈비를 함께 경험할 수 있는 당일치기 명소로 소개함.",
                "checked": "2026-10-23",
            },
            {
                "id": "soulofseoul-suwon-fortress-day-trip",
                "label_ko": "성곽길·월화원",
                "quote": "From the 5.7-kilometer fortress ramparts and Guangdong-style Wolhwawon Garden to the glowing boardwalks of Gwanggyo Lake Park, Suwon rewards slow exploration.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "영어 여행 블로그 The Soul of Seoul. 5.7km 수원화성 성곽길과 효원공원 월화원, 광교호수공원 야경 데크길이 어우러진 도보 여행 도시로 수원을 호평함.",
                "checked": "2026-10-23",
            },
            {
                "id": "icomos-haewoojae-agricultural-museum-suwon",
                "label_ko": "해우재·박물관",
                "quote": "Suwon pairs quirky civic museums like Haewoojae Toilet Culture Park with the National Agricultural Museum beside historic Seoho Reservoir.",
                "quote_lang": "en",
                "quote_checked": "2026-10-23",
                "basis_ko": "박물관·문화유산 아카이브 자료. 세계 유일의 화장실 테마 박물관 해우재와 서호(축만제) 옆 국립농업박물관이 수원의 독창적인 박물관 문화를 보여 준다고 기록함.",
                "checked": "2026-10-23",
            },
        ],
    }

    dump_json(DATA / "abroad.json", abroad_doc)
    dump_json(DATA / "abroad_highlights.json", highlights_doc)
    probs = validate.highlight_problems(DATA, {x["id"] for x in abroad_doc["items"]})
    assert not probs, f"abroad_highlights problems: {probs}"
    print("Wrote abroad.json and abroad_highlights.json (0 problems)")


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


def _art_entry(
    slot: str,
    ko_desc: str,
    en_desc: str,
    ja_desc: str,
    zhs_desc: str,
    zht_desc: str,
    de_desc: str,
    fr_desc: str,
    es_desc: str,
    ru_desc: str,
    *,
    status: str = "연결",
    langs: list[str] | None = None,
    note: str = "",
) -> dict:
    use_langs = langs or ALL_LANGS
    raw_alts = {
        "ko": ko_desc,
        "en": en_desc,
        "ja": ja_desc,
        "zh-hans": zhs_desc,
        "zh-hant": zht_desc,
        "de": de_desc,
        "fr": fr_desc,
        "es": es_desc,
        "ru": ru_desc,
    }
    out: dict = {
        "file": "",
        "slot": slot,
        "status": status,
        "langs": use_langs,
    }
    if note:
        out["note"] = note
    for lang in use_langs:
        key = "alt" if lang == "ko" else f"alt_{lang.replace('-', '_')}"
        t = raw_alts[lang]
        if not t.startswith(PREFIX[lang]):
            t = PREFIX[lang] + t
        out[key] = t
    return out


def build_art_and_sync_manifest() -> None:
    gn_art = Path(r"C:\Users\USER\Downloads\Gangneung\templates\assets\art")
    if gn_art.is_dir():
        ART_DIR.mkdir(parents=True, exist_ok=True)
        for f in ART_DIR.iterdir():
            if f.is_file():
                f.unlink()
        for f in gn_art.iterdir():
            if f.is_file():
                shutil.copy2(f, ART_DIR / f.name)
    manifest = json.loads((ART_DIR / "manifest.json").read_text("utf-8"))

    rename_map = {
        "area-gyeongpo": "area-hwaseong-haenggung",
        "area-downtown": "area-paldalmun-market",
        "area-jeongdongjin": "area-gwanggyo-yeongtong",
        "area-jumunjin": "area-manseok-jangan",
        "area-daegwallyeong": "area-irwol-gwonseon",
        "course-gangneung-course-1": "course-suwon-course-1",
        "course-gangneung-course-2": "course-suwon-course-2",
        "course-gangneung-course-3": "course-suwon-course-3",
        "course-gangneung-course-4": "course-suwon-course-4",
        "course-gangneung-course-5": "course-suwon-course-5",
        "course-gangneung-course-6": "course-suwon-course-6",
        "vtopic-gyeongpo-anmok-haebyeon": "vtopic-suwon-hwaseong-haenggung",
        "vtopic-ojukheon-seongyojang-yusan": "vtopic-haengnidan-banghwasuryujeong",
        "vtopic-jeongdongjin-haean": "vtopic-gwanggyo-hosu",
        "vtopic-jumunjin-bukbu": "vtopic-sumogwon-gongwon",
        "vtopic-daegwallyeong-sup": "vtopic-bangmulgwan-misulgwan",
        "vtopic-meokgeori-keopi": "vtopic-wanggalbi-tongdak-sijang",
        "vtopic-sukso-kaemping": "vtopic-kape-dijeoteu",
        "vtopic-chukje-danoje": "vtopic-chukje-yagan",
    }

    for old_id, new_id in rename_map.items():
        if old_id in manifest:
            m_entry = manifest.pop(old_id)
            for fmt in ("avif", "webp", "jpg"):
                if fmt in m_entry:
                    new_files = []
                    for fname, w, sz in m_entry[fmt]:
                        new_fname = fname.replace(old_id, new_id, 1)
                        old_p = ART_DIR / fname
                        new_p = ART_DIR / new_fname
                        if old_p.is_file() and not new_p.is_file():
                            old_p.rename(new_p)
                        elif old_p.is_file() and new_p.is_file() and old_p != new_p:
                            old_p.unlink()
                        new_files.append([new_fname, w, new_p.stat().st_size])
                    m_entry[fmt] = new_files
            manifest[new_id] = m_entry

    dump_json(ART_DIR / "manifest.json", manifest)

    slot_specs = {
        "head-places": (
            "list.head.places",
            "수원화성 장안문과 방화수류정 용연, 화성행궁 기와지붕과 광교호수공원 수변이 어우러진 수원 전경",
            "Panoramic view of Suwon featuring Hwaseong Fortress Janganmun Gate, Banghwasuryujeong Pavilion, Hwaseong Haenggung, and Gwanggyo Lake",
        ),
        "head-food": (
            "list.head.food",
            "햇살 드는 창가 나무 식탁에 차려진 수원 왕갈비 구이와 가마솥 통닭, 지동시장 순대와 행리단길 핸드드립 커피 한 상",
            "A sunlit wooden table in Suwon set with grilled Suwon wang-galbi, cauldron fried chicken, market sundae, and hand-drip coffee",
        ),
        "head-stays": (
            "list.head.stays",
            "해 질 녘 수원화성 성곽 아래 고즈넉한 행궁동 한옥스테이 기와지붕과 광교 호수변 호텔 불빛이 어우러진 숙소 풍경",
            "Twilight view of traditional Hanok stays near Hwaseong Haenggung and warm hotel lights overlooking Gwanggyo Lake in Suwon",
        ),
        "head-courses": (
            "list.head.courses",
            "수원화성 성곽 산책로와 방화수류정 연못, 일월수목원 온실과 광교호수공원 데크길이 이어지는 수원 여행 코스 풍경",
            "Scenic walking trail linking Suwon Hwaseong Fortress ramparts, Banghwasuryujeong pond, and Gwanggyo Lake boardwalk",
        ),
        "head-guides": (
            "list.head.guides",
            "아침 햇살이 비치는 방화수류정 용연 버드나무 산책로와 일월수목원 정원 풍경",
            "Morning sunbeams filtering over the willow trees of Banghwasuryujeong Pond and Ilwol Arboretum gardens in Suwon",
        ),
        "head-events": (
            "list.head.events",
            "밤하늘 아래 화성행궁과 장안문 성곽 위로 수원화성문화제 등불과 미디어아트 빛이 펼쳐진 수원 축제 풍경",
            "Night festival plaza in Suwon illuminated with glowing lanterns and media art projections over Hwaseong Fortress",
        ),
        "head-videos": (
            "list.head.videos",
            "저녁노을 속 방화수류정과 수원화성 성곽을 내려다보는 언덕 위의 시네마 카메라",
            "A cinema camera on a tripod overlooking Banghwasuryujeong Pavilion and Suwon Hwaseong Fortress walls at sunset",
        ),
        "head-abroad": (
            "list.head.abroad",
            "유네스코 세계문화유산 수원화성 장안문·방화수류정과 화성행궁, 광교호수공원이 어우러진 수원 전경",
            "Aerial panorama of Suwon featuring UNESCO World Heritage Hwaseong Fortress, Hwaseong Haenggung Palace, and Gwanggyo Lake",
        ),
        "head-map": (
            "list.head.map",
            "장안구 광교산·만석공원에서 팔달구 수원화성·화성행궁, 권선구 일월수목원과 영통구 광교호수공원까지 한눈에 펼쳐진 수원시 조감 전경",
            "Bird's-eye view of Suwon-si stretching from Gwanggyosan and Hwaseong Fortress to Ilwol Arboretum and Gwanggyo Lake Park",
        ),
        "about-hero": (
            "about.head",
            "소나무 숲과 연못 용연 너머로 방화수류정 누각과 수원화성 성곽이 펼쳐진 수원 풍경",
            "Sunny daytime view of Banghwasuryujeong Pavilion and Suwon Hwaseong Fortress ramparts framed by pine trees and Yongyeon Pond",
        ),
        "plan-hero": (
            "plan.head",
            "봄 벚꽃이 만개한 팔달산 성곽길과 방화수류정 연못 너머로 펼쳐진 수원 아침 풍경",
            "Bright morning panorama of Paldalsan Fortress Trail and Banghwasuryujeong Pond framed by spring blossoms in Suwon",
        ),
        "area-hwaseong-haenggung": (
            "area.hwaseong-haenggung",
            "화성행궁 정전과 장안문·방화수류정 성곽길, 아기자기한 행리단길 루프톱 카페가 이어지는 행궁 권역 풍경",
            "Panorama of Hwaseong Haenggung Palace, Janganmun Gate, Banghwasuryujeong, and Haengnidan-gil cafes in Suwon",
        ),
        "area-paldalmun-market": (
            "area.paldalmun-market",
            "팔달문 성문과 활기찬 남문·지동·못골전통시장, 고소한 수원통닭거리와 수원천이 어우러진 팔달 권역 풍경",
            "Warm afternoon view of Paldalmun Gate, traditional markets, and Suwon Fried Chicken Street along Suwoncheon Stream",
        ),
        "area-gwanggyo-yeongtong": (
            "area.gwanggyo-yeongtong",
            "광교호수공원 수변 데크와 프라이부르크전망대, 아쿠아플라넷과 수원광교박물관이 이어진 광교·영통 권역 풍경",
            "Scenic lakeside panorama of Gwanggyo Lake Park, Freiburg Observation Tower, Aqua Planet, and museums in Yeongtong-gu, Suwon",
        ),
        "area-manseok-jangan": (
            "area.manseok-jangan",
            "만석공원 호수와 영화정 정자, 노송지대 소나무길과 광교산 산책로가 이어진 장안 권역 풍경",
            "Tranquil lakeside and pine trail view of Manseok Park, Nosong Zone, and Gwanggyosan trails in Jangan-gu, Suwon",
        ),
        "area-irwol-gwonseon": (
            "area.irwol-gwonseon",
            "일월수목원 유리온실과 서호공원 낙조, 국립농업박물관과 경기상상캠퍼스 숲길이 어우러진 권선·서수원 풍경",
            "Lush botanical and lakeside panorama of Ilwol Arboretum greenhouse, Seoho Park sunset, and Gyeonggi Sangsang Campus in Suwon",
        ),
        "guide-01": (
            "guide.banner.guide-01",
            "화창한 날 수원화성 성곽길과 방화수류정 용연, 화성행궁 기와지붕이 어우러진 풍경",
            "Sunny fortress rampart promenade at Suwon Hwaseong, Banghwasuryujeong Pond, and Hwaseong Haenggung Palace",
        ),
        "guide-02": (
            "guide.banner.guide-02",
            "일월수목원 온실 정원과 아쿠아플라넷 광교, 국립농업박물관 잔디마당이 어우러진 수원 가족 나들이 풍경",
            "Family-friendly garden walkways at Ilwol Arboretum, Aqua Planet Gwanggyo, and National Agricultural Museum in Suwon",
        ),
        "guide-03": (
            "guide.banner.guide-03",
            "비에 젖은 성곽 소나무가 통유리창 너머로 보이는 따뜻한 조명의 수원시립미술관·별마당도서관 실내 공간",
            "Warmly lit interior of Suwon Museum of Art and Starfield Library looking out onto rain-washed trees",
        ),
        "guide-04": (
            "guide.banner.guide-04",
            "맑은 날 광교호수공원과 만석공원 나무 데크 산책로를 따라 목줄을 하고 걷는 골든리트리버와 하얀 비숑 강아지",
            "A golden retriever and a white bichon walking on leashes along a sunny lakeside wooden boardwalk at Gwanggyo Lake Park in Suwon",
        ),
        "guide-05": (
            "guide.banner.guide-05",
            "성곽이 보이는 식당 창가에 차려진 수원 왕갈비와 바삭한 가마솥 통닭, 칼국수와 행리단길 커피",
            "A bright restaurant table in Suwon set with grilled wang-galbi, crispy cauldron fried chicken, kalguksu, and drip coffee",
        ),
        "guide-06": (
            "guide.banner.guide-06",
            "별빛이 비치는 저녁 행궁동 고즈넉한 한옥스테이 마당과 광교호수 인근 호텔의 따뜻한 조명 풍경",
            "Twilight stay scene in Suwon with a warm traditional Hanok courtyard near Haenggung-dong and glowing hotel lights",
        ),
        "course-suwon-course-1": (
            "course.banner.suwon-course-1",
            "노을빛 화성행궁과 서장대, 화서문·장안문·방화수류정과 행리단길이 이어지는 수원화성 성곽 기행 풍경",
            "Golden-hour panorama linking Hwaseong Haenggung, Seojangdae, Janganmun, Banghwasuryujeong, and Haengnidan-gil in Suwon",
        ),
        "course-suwon-course-2": (
            "course.banner.suwon-course-2",
            "연무대 국궁장과 플라잉 수원 열기구, 창룡문·팔달문과 지동시장·수원통닭거리가 이어지는 도보 여행 풍경",
            "Sunny cultural walk from Yeonmudae and Flying Suwon balloon to Paldalmun Market and Fried Chicken Street",
        ),
        "course-suwon-course-3": (
            "course.banner.suwon-course-3",
            "광교호수공원 수변길과 프라이부르크전망대, 아쿠아플라넷 광교와 수원광교박물관·수원박물관이 어우러진 풍경",
            "Lakeside and museum panorama combining Gwanggyo Lake Park, Freiburg Tower, Aqua Planet, and Suwon Museum",
        ),
        "course-suwon-course-4": (
            "course.banner.suwon-course-4",
            "일월수목원 온실과 서호공원 수변, 국립농업박물관과 경기상상캠퍼스·별마당도서관이 이어지는 생태·문화 풍경",
            "Sunny ecological and cultural outing showing Ilwol Arboretum, Seoho Park, National Agricultural Museum, and Starfield Library",
        ),
        "course-suwon-course-5": (
            "course.banner.suwon-course-5",
            "만석공원 호수와 노송지대 해송 길, 해우재 정원과 봉녕사·광교마루길 숲길이 이어지는 장안구 풍경",
            "Lakeside and forest trail panorama of Manseok Park, Nosong Pine Zone, Haewoojae, and Gwanggyomarugil in Suwon",
        ),
        "course-suwon-course-6": (
            "course.banner.suwon-course-6",
            "효원공원 월화원 전통 정자와 경기아트센터, 삼성이노베이션뮤지엄과 영흥수목원이 이어진 도심 정원 기행 풍경",
            "Garden and museum panorama of Wolhwawon Garden, Gyeonggi Arts Center, Samsung Innovation Museum, and Yeongheung Arboretum",
        ),
        "card-event": (
            "home.card.event",
            "저녁노을 진 화성행궁 광장과 장안문 성곽에 따뜻한 수원화성문화제 등불과 미디어아트가 켜진 축제 풍경",
            "Warm festival lanterns and media art glowing across Hwaseong Haenggung Plaza and Janganmun Gate at dusk in Suwon",
        ),
        "card-guide": (
            "home.card.guide",
            "버드나무와 연꽃이 핀 방화수류정 용연 수변 산책로 너머로 성곽 정자가 보이는 풍경",
            "A sunlit lakeside walking trail at Banghwasuryujeong Yongyeon Pond framed by willow trees and fortress walls in Suwon",
        ),
        "card-video": (
            "home.card.video",
            "아침 햇살이 떠오르는 수원화성 방화수류정과 광교호수공원 수변이 황금빛으로 물든 수원 항공 풍경",
            "Aerial golden-hour sunrise view over Suwon Hwaseong Fortress, Banghwasuryujeong, and Gwanggyo Lake Park",
        ),
        "card-abroad": (
            "home.card.abroad",
            "맑은 하늘 아래 수원화성 장안문과 화성행궁 기와지붕, 방화수류정과 광교호수공원이 어우러진 수원 전경",
            "Daytime view overlooking Suwon Hwaseong Fortress gates, Hwaseong Haenggung roofs, and Gwanggyo Lake in Suwon",
        ),
        "card-course": (
            "home.card.course",
            "노을빛 수원화성 성곽 산책로가 서장대와 화서문, 방화수류정으로 이어지는 풍경",
            "Sunset fortress wall walking path linking Seojangdae, Hwaseomun, and Banghwasuryujeong in Suwon",
        ),
        "chat-empty": (
            "chat.empty",
            "행리단길 카페 창가 나무 탁자 위에 펼쳐진 수원 여행 지도와 나침반, 카메라와 핸드드립 커피 한 잔",
            "A sunlit wooden cafe table on Haengnidan-gil, Suwon with a travel map, compass, camera, and hand-drip coffee",
        ),
        "art-404": (
            "page.404",
            "아침 물안개가 낀 방화수류정 용연 연못과 버드나무 옆에 놓인 조용한 나무 벤치와 먼발치의 성곽 정자",
            "A quiet wooden bench beside willow trees and misty Yongyeon Pond with Banghwasuryujeong Pavilion in Suwon",
        ),
        "art-search-empty": (
            "search.empty",
            "잔잔한 광교호수 수면이 내려다보이는 나무 벤치 위에 놓인 원두커피 그라인더와 여행 수첩, 쌍안경",
            "A wooden bench overlooking calm Gwanggyo Lake in Suwon holding a coffee grinder, travel notebook, and binoculars",
        ),
        "vtopic-yeohaeng-koseu": (
            "videos.head.yeohaeng-koseu",
            "황금빛 햇살 아래 수원화성 성곽길을 따라 화성행궁과 방화수류정으로 이어지는 산책로 풍경",
            "Scenic walking trail along the fortress ramparts of Suwon Hwaseong toward Hwaseong Haenggung and Banghwasuryujeong",
        ),
        "vtopic-suwon-hwaseong-haenggung": (
            "videos.head.suwon-hwaseong-haenggung",
            "장엄한 장안문·팔달문 성곽과 화성행궁 정전, 하늘 위로 떠오른 플라잉 수원 열기구 풍경",
            "Sunny panoramic view of Suwon Hwaseong Fortress gates, Hwaseong Haenggung Palace, and the Flying Suwon helium balloon",
        ),
        "vtopic-haengnidan-banghwasuryujeong": (
            "videos.head.haengnidan-banghwasuryujeong",
            "연못 용연 위에 비친 방화수류정 누각과 아기자기한 행리단길 루프톱 카페 골목 풍경",
            "Bright daytime view of Banghwasuryujeong Pavilion reflected in Yongyeon Pond and Haengnidan-gil cafe street in Suwon",
        ),
        "vtopic-gwanggyo-hosu": (
            "videos.head.gwanggyo-hosu",
            "광교호수공원 수변 데크길과 프라이부르크전망대, 아쿠아플라넷 광교가 이어진 영통구 수변 풍경",
            "Morning sunlight over Gwanggyo Lake Park wooden boardwalk, Freiburg Observation Tower, and Aqua Planet Gwanggyo",
        ),
        "vtopic-sumogwon-gongwon": (
            "videos.head.sumogwon-gongwon",
            "일월수목원·영흥수목원 유리온실과 효원공원 월화원, 광교산 숲길이 어우러진 수원 녹지 풍경",
            "Afternoon view of Ilwol and Yeongheung Arboretum glasshouses, Wolhwawon Garden, and Gwanggyosan forest trail in Suwon",
        ),
        "vtopic-bangmulgwan-misulgwan": (
            "videos.head.bangmulgwan-misulgwan",
            "수원화성박물관과 수원시립미술관, 별마당도서관 스타필드 수원점과 국립농업박물관이 어우러진 문화 풍경",
            "Cultural panorama of Suwon Hwaseong Museum, Suwon Museum of Art, Starfield Library, and National Agricultural Museum",
        ),
        "vtopic-wanggalbi-tongdak-sijang": (
            "videos.head.wanggalbi-tongdak-sijang",
            "창가 나무 식탁에 차려진 수원 왕갈비 구이와 가마솥 통닭, 팔달문·지동전통시장 먹거리 한 상",
            "Gourmet table in Suwon featuring grilled Suwon wang-galbi, cauldron fried chicken, and Paldalmun market street food",
        ),
        "vtopic-kape-dijeoteu": (
            "videos.head.kape-dijeoteu",
            "행궁동과 광교호수공원이 내려다보이는 루프톱 테라스에 차려진 핸드드립 커피와 수제 베이커리 디저트",
            "Rooftop cafe table overlooking Hwaseong Fortress in Suwon with specialty hand-drip coffee and bakery desserts",
        ),
        "vtopic-chukje-yagan": (
            "videos.head.chukje-yagan",
            "화성행궁 야간개장 청사초롱과 화서문·장안문 미디어아트 빛이 어우러진 수원화성문화제 야경",
            "Night panorama of Hwaseong Haenggung lantern lightings and Suwon Hwaseong Media Art projections",
        ),
        "vtopic-other": (
            "videos.head.other",
            "화령전 돌담길과 노송지대 소나무 숲, 서호공원 낙조가 어우러진 평화로운 수원 풍경",
            "Peaceful view of Hwaryeongjeon stone walls, Nosong pine forest, and Seoho Park sunset walkway in Suwon",
        ),
        "evkind-sea": (
            "events.kind.sea",
            "맑은 날 광교호수공원과 만석거 수변 데크에서 시원한 물결을 바라보며 축제를 즐기는 풍경",
            "Sunny waterside festival scene at Gwanggyo Lake Park and Manseokgeo Pond in Suwon under clear blue skies",
        ),
        "evkind-flowers": (
            "events.kind.flowers",
            "팔달산 성곽길과 만석공원 호수 둘레길을 따라 화사하게 만개한 봄 벚꽃 축제 풍경",
            "Vibrant spring cherry blossom festival scene along Paldalsan Fortress Trail and Manseok Park in Suwon",
        ),
        "evkind-nature": (
            "events.kind.nature",
            "노을빛 억새와 온실 정원이 어우러진 일월수목원과 서호공원 생태 산책로 풍경",
            "Golden-hour ecological boardwalk at Seoho Park and botanical garden trails at Ilwol Arboretum in Suwon",
        ),
        "evkind-night": (
            "events.kind.night",
            "초승달 아래 화성행궁 기와지붕과 방화수류정 위로 은은한 야간 경관조명과 청사초롱이 켜진 야행 풍경",
            "Magical night heritage walk at Hwaseong Haenggung and Banghwasuryujeong in Suwon with glowing traditional lanterns",
        ),
        "evkind-food": (
            "events.kind.food",
            "따뜻한 저녁 조명 아래 팔달문 야시장과 정원 테라스에 차려진 수원 먹거리와 디저트",
            "Outdoor culinary festival table at dusk in Suwon under string lights featuring local delicacies and desserts",
        ),
        "evkind-stage": (
            "events.kind.stage",
            "노을 지는 광교호수공원 야외무대와 경기상상캠퍼스 잔디광장에 따뜻한 조명이 켜진 재즈·연극 공연 풍경",
            "Sunset outdoor jazz and theater stage on the lawn of Gwanggyo Lake Park and Gyeonggi Sangsang Campus in Suwon",
        ),
        "evkind-market": (
            "events.kind.market",
            "햇살 가득한 팔달문·수원남문시장과 행궁광장에 하얀 천막 부스와 수공예품이 진열된 장터 풍경",
            "Sunny outdoor craft and traditional market booths at Paldalmun Market and Haenggung Plaza in Suwon",
        ),
        "evkind-ceremony": (
            "events.kind.ceremony",
            "아침 햇살이 비치는 화성행궁과 정조로 광장에 수원화성문화제 전통 깃발과 청사초롱이 어우러진 풍경",
            "Bright morning cultural celebration plaza at Hwaseong Haenggung in Suwon featuring traditional royal banners",
        ),
        "evkind-race": (
            "events.kind.race",
            "아침 햇살 속 봄꽃이 핀 광교호수 둘레길과 서호천 수변길을 따라 이어지는 수원 걷기·자전거 코스",
            "Scenic morning walking and cycling road winding beside Gwanggyo Lake and Seohocheon Stream in Suwon",
        ),
        "evkind-book": (
            "events.kind.book",
            "따뜻한 오후 햇살이 비치는 경기도서관과 경기상상캠퍼스 숲속 잔디밭의 야외 나무 책장과 독서 정원",
            "Warm afternoon outdoor book fair and reading garden under trees at Gyeonggi Library and Sangsang Campus in Suwon",
        ),
        "evkind-alley": (
            "events.kind.alley",
            "노을빛이 스며드는 수원 행리단길과 공방거리 골목에 따뜻한 스트링 조명과 테라스 화분이 놓인 풍경",
            "Golden-hour view of Haengnidan-gil and Workshop Street alley in Suwon with warm string lights and flower pots",
        ),
        "evkind-other": (
            "events.kind.other",
            "푸른 하늘 아래 바람개비가 돌아가는 국립농업박물관 다랑이논과 잔디 정원 풍경",
            "Sunny meadow at National Agricultural Museum in Suwon with colorful pinwheels, terraced fields, and pavilions",
        ),
        "month-01": (
            "events.month.01",
            "눈 덮인 팔달산 서장대와 수원화성 성곽 위로 떠오르는 1월의 황금빛 수원 새해 일출",
            "Golden January New Year sunrise over Paldalsan Seojangdae and Suwon Hwaseong Fortress",
        ),
        "month-02": (
            "events.month.02",
            "푸른 저녁 화성행궁과 방화수류정 기와지붕 위로 밝게 비치는 2월 정월대보름 보름달 풍경",
            "February twilight scene over Hwaseong Haenggung and Banghwasuryujeong in Suwon with a bright full moon",
        ),
        "month-03": (
            "events.month.03",
            "화성행궁과 화령전 전통 돌담 앞에 화사하게 피어난 3월의 홍매화와 노란 산수유 꽃가지",
            "March early-spring scene at Hwaseong Haenggung and Hwaryeongjeon in Suwon showing blooming plum and cornelian blossoms",
        ),
        "month-04": (
            "events.month.04",
            "맑은 4월 봄 하늘 아래 만석공원(만석거)과 팔달산 성곽길을 따라 터널을 이룬 연분홍 벚꽃길 풍경",
            "April spring scene along Manseok Park and Paldalsan Fortress in Suwon with a tunnel of pale pink cherry blossoms",
        ),
        "month-05": (
            "events.month.05",
            "푸른 5월의 신록 속 일월수목원과 경기상상캠퍼스 숲에 피어난 화사한 봄 꽃정원 풍경",
            "May garden scene at Ilwol Arboretum and Gyeonggi Sangsang Campus in Suwon filled with blooming spring flowers",
        ),
        "month-06": (
            "events.month.06",
            "초여름 방화수류정 용연과 만석공원 연못에 초록 버드나무와 연잎이 펼쳐진 6월 풍경",
            "June early-summer morning scene at Banghwasuryujeong Yongyeon Pond in Suwon with green willows and lotus leaves",
        ),
        "month-07": (
            "events.month.07",
            "푸른 7월의 광교호수공원 수변 분수와 광교산 계곡 그늘 아래 시원한 여름 산책 풍경",
            "July summer scene at Gwanggyo Lake Park and shaded Gwanggyosan forest stream in Suwon under bright sunshine",
        ),
        "month-08": (
            "events.month.08",
            "은은한 8월 여름밤 조명 아래 화성행궁과 방화수류정 성곽길을 거니는 수원 국가유산야행 풍경",
            "August summer night heritage walk at Hwaseong Haenggung and Banghwasuryujeong in Suwon under soft lantern lights",
        ),
        "month-09": (
            "events.month.09",
            "높고 푸른 9월 가을 하늘 아래 광교호수공원 재즈페스티벌 무대와 화서문 미디어아트가 어우러진 풍경",
            "September autumn scene in Suwon with Gwanggyo Lake Park Jazz Festival and Hwaseomun Media Art lights",
        ),
        "month-10": (
            "events.month.10",
            "수원화성 성곽과 화성행궁 단풍이 붉게 물들고 수원화성문화제 등불이 켜진 10월 수원 가을 풍경",
            "October autumn scene in Suwon combining fiery red maple leaves along Hwaseong Fortress and cultural festival lanterns",
        ),
        "month-11": (
            "events.month.11",
            "전통 돌담과 기와지붕 위로 황금빛 은행잎이 소복이 내려앉은 11월 수원향교·효원공원 월화원의 만추 풍경",
            "November late-autumn scene at Suwon Hyanggyo and Wolhwawon Garden in Suwon with golden ginkgo leaves",
        ),
        "month-12": (
            "events.month.12",
            "하얀 눈이 내려앉은 수원화성 방화수류정과 따뜻한 겨울 조명이 켜진 행리단길의 12월 겨울 야경",
            "December winter night scene in Suwon with snow-dusted Banghwasuryujeong Pavilion and warm lights along Haengnidan-gil",
        ),
        "abroad-press": (
            "abroad.group.press",
            "방화수류정과 수원화성이 보이는 창가 나무 탁자 위에 놓인 접힌 외신 신문 여러 부와 따뜻한 드립커피 한 잔",
            "a stack of folded newspapers and a cup of warm hand-drip coffee on a wooden table overlooking Suwon Hwaseong Fortress",
        ),
        "abroad-official": (
            "abroad.group.official",
            "화성행궁 기와지붕과 성곽이 내려다보이는 창문 앞 나무 책상에 놓인 지구본과 하늘색 공식 안내 폴더",
            "a classic desktop globe and a sky-blue travel folder on a sunlit wooden desk overlooking Hwaseong Haenggung in Suwon",
        ),
        "abroad-travel": (
            "abroad.group.travel",
            "여행 수첩 두 권과 여권, 수원화성·방화수류정 사진 엽서와 원두커피 잔이 놓인 카페 나무 탁자",
            "two hardcover travel notebooks, a passport, a photo print of Suwon Hwaseong Fortress, and a coffee cup on a cafe table",
        ),
        "abroad-blog": (
            "abroad.group.blog",
            "노을 진 수원화성과 광교호수 사진이 화면에 띄워진 노트북과 하얀 커피 머그잔, 카메라 렌즈가 놓인 나무 책상",
            "an open laptop displaying a sunset photograph of Suwon Hwaseong Fortress beside a white ceramic coffee mug and camera lens",
        ),
        "abroad-research": (
            "abroad.group.research",
            "화성성역의궤 도판과 수원 생태 지도가 펼쳐진 두꺼운 학술서와 황동 돋보기, 솔방울이 놓인 책상",
            "an open hardcover book showing Hwaseong Fortress architectural drawings, a brass magnifying glass, and pine cones on a desk",
        ),
        "abroad-videos": (
            "abroad.group.videos",
            "황금빛 노을이 비치는 수원화성과 방화수류정을 향해 나무 데크 위에 세워 둔 삼각대 시네마 카메라",
            "a mirrorless cinema camera on a tripod on a wooden deck overlooking Banghwasuryujeong and Suwon Hwaseong at golden hour",
        ),
    }

    images: dict[str, dict] = {}
    for art_id, (slot, ko_d, en_d) in slot_specs.items():
        status = "연결"
        note = ""
        langs = None
        if art_id == "plan-hero":
            langs = ["ko"]
        elif art_id == "card-course":
            status = "개편 뒤 연결"
            note = "코스 소식 카드가 아직 없다(present.home_news의 출처에 코스가 없음)"
        elif art_id == "chat-empty":
            status = "개편 뒤 연결"
            note = "챗봇 빈 화면의 그림 자리가 아직 없다"

        ja_map = {"head-places": "水原華城の長安門と訪花随柳亭の龍淵、華城行宮の瓦屋根と光教湖水公園の水辺が調和する水原の全景", "head-food": "日差しが差し込む窓辺の木の食卓に並ぶ水原王カルビ焼きと釜揚げチキン、池洞市場のスンデと行理団通りのハンドドリップコーヒー", "head-stays": "夕暮れ時の水原華城の城郭の下に佇む行宮洞の韓屋ステイの瓦屋根と光教湖畔のホテルの灯りが調和する宿の風景", "head-courses": "水原華城の城郭散策路と訪花随柳亭の池、日月樹木園の温室と光教湖水公園のデッキ道が続く水原の旅行コース風景", "head-guides": "朝日が差し込む訪花随柳亭・龍淵の柳並木散策路と日月樹木園の庭園風景", "head-events": "夜空の下、華城行宮と長安門の城郭の上に水原華城文化祭の灯籠とメディアアートの光が広がる水原の祭り風景", "head-videos": "夕焼けの中、訪花随柳亭と水原華城の城郭を見下ろす丘の上のシネマカメラ", "head-abroad": "ユネスコ世界遺産・水原華城の長安門・訪花随柳亭と華城行宮、光教湖水公園が調和する水原の全景", "head-map": "長安区の光教山・万石公園から八達区の水原華城・華城行宮、勧善区の日月樹木園と霊通区の光教湖水公園まで一望できる水原市の鳥瞰全景", "about-hero": "松林と池・龍淵の向こうに訪花随柳亭の楼閣と水原華城の城郭が広がる水原の風景", "plan-hero": "春の桜が満開の八達山城郭の道と訪花随柳亭の池の向こうに広がる水原の朝の風景", "area-hwaseong-haenggung": "華城行宮の正殿と長安門・訪花随柳亭の城郭の道、行理団通りのルーフトップカフェが続く行宮圏域の風景", "area-paldalmun-market": "八達門の城門と活気あふれる南門・池洞・モッコル伝統市場、香ばしい水原チキン通りと水原川が調和する八達圏域の風景", "area-gwanggyo-yeongtong": "光教湖水公園の水辺デッキとフライブルク展望台、アクアプラネットと水原光教博物館が続く光教・霊通圏域の風景", "area-manseok-jangan": "万石公園の湖と迎華亭の東屋、老松地帯の松並木と光教山散策路が続く長安圏域の風景", "area-irwol-gwonseon": "日月樹木園のガラス温室と西湖公園の夕照、国立農業博物館と京畿想像キャンパスの森道が調和する勧善・西水原の風景", "guide-01": "晴れた日の水原華城の城郭の道と訪花随柳亭の龍淵、華城行宮の瓦屋根が調和する風景", "guide-02": "日月樹木園の温室庭園とアクアプラネット光教、国立農業博物館の芝生広場が調和する水原の家族お出かけ風景", "guide-03": "雨に濡れた城郭の松がガラス窓越しに見える温かな照明の水原市立美術館・ピョルマダン図書館の室内空間", "guide-04": "晴れた日に光教湖水公園と万石公園のウッドデッキ散策路をリードをつけて歩くゴールデンレトリバーと白いビション", "guide-05": "城郭が見える食堂の窓辺に並ぶ水原王カルビとサクサクの釜揚げチキン、カルグクスと行理団通りのコーヒー", "guide-06": "星明かりが差す夕方の行宮洞の静かな韓屋ステイの中庭と光教湖付近のホテルの温かな照明風景", "course-suwon-course-1": "夕焼けの華城行宮と西将台、華西門・長安門・訪花随柳亭と行理団通りが続く水原華城の城郭紀行風景", "course-suwon-course-2": "錬武台の国弓場とフライング水原の気球、蒼龍門・八達門と池洞市場・水原チキン通りが続く徒歩旅行風景", "course-suwon-course-3": "光教湖水公園の水辺道とフライブルク展望台、アクアプラネット光教と水原光教博物館・水原博物館が調和する風景", "course-suwon-course-4": "日月樹木園の温室と西湖公園の水辺、国立農業博物館と京畿想像キャンパス・ピョルマダン図書館が続く生態・文化風景", "course-suwon-course-5": "万石公園の湖と老松地帯の松並木、解憂斎の庭園と奉寧寺・光教マルギルの森道が続く長安区の風景", "course-suwon-course-6": "孝園公園・粤華苑の伝統東屋と京畿アートセンター、サムスンイノベーションミュージアムと霊興樹木園が続く都心庭園紀行風景", "card-event": "夕焼けの華城行宮広場と長安門の城郭に温かな水原華城文化祭の灯籠とメディアアートが灯る祭り風景", "card-guide": "柳と蓮の花が咲く訪花随柳亭・龍淵の水辺散策路の向こうに城郭の東屋が見える風景", "card-video": "朝日が昇る水原華城・訪花随柳亭と光教湖水公園の水辺が黄金色に染まる水原の空撮風景", "card-abroad": "青空の下、水原華城の長安門と華城行宮の瓦屋根、訪花随柳亭と光教湖水公園が調和する水原の全景", "card-course": "夕焼けの水原華城の城郭散策路が西将台と華西門、訪花随柳亭へと続く風景", "chat-empty": "行理団通りのカフェの窓辺の木のテーブルの上に広げられた水原旅行地図とコンパス、カメラとハンドドリップコーヒー1杯", "art-404": "朝霧が立ち込める訪花随柳亭の龍淵の池と柳の横に置かれた静かな木のベンチと遠くの城郭の東屋", "art-search-empty": "穏やかな光教湖の水面を見下ろす木のベンチの上に置かれたコーヒーミルと旅行手帳、双眼鏡", "vtopic-yeohaeng-koseu": "黄金色の日差しの下、水原華城の城郭の道に沿って華城行宮と訪花随柳亭へ続く散策路の風景", "vtopic-suwon-hwaseong-haenggung": "壮麗な長安門・八達門の城郭と華城行宮の正殿、空高く浮かぶフライング水原の気球の風景", "vtopic-haengnidan-banghwasuryujeong": "池・龍淵に映る訪花随柳亭の楼閣と可愛らしい行理団通りのルーフトップカフェ路地の風景", "vtopic-gwanggyo-hosu": "光教湖水公園の水辺デッキ道とフライブルク展望台、アクアプラネット光教が続く霊通区の水辺風景", "vtopic-sumogwon-gongwon": "日月樹木園・霊興樹木園のガラス温室と孝園公園・粤華苑、光教山の森道が調和する水原の緑地風景", "vtopic-bangmulgwan-misulgwan": "水原華城博物館と水原市立美術館、ピョルマダン図書館スターフィールド水原店と国立農業博物館が調和する文化風景", "vtopic-wanggalbi-tongdak-sijang": "窓辺の木の食卓に並ぶ水原王カルビ焼きと釜揚げチキン、八達門・池洞伝統市場のグルメ御膳", "vtopic-kape-dijeoteu": "行宮洞と光教湖水公園を見下ろすルーフトップテラスに並ぶハンドドリップコーヒーと自家製ベーカリーデザート", "vtopic-chukje-yagan": "華城行宮の夜間開場チョンサチョロンと華西門・長安門のメディアアートの光が調和する水原華城文化祭の夜景", "vtopic-other": "華寧殿の石垣道と老松地帯の松林、西湖公園の夕照が調和する穏やかな水原の風景", "evkind-sea": "晴れた日に光教湖水公園と万石渠の水辺デッキで涼しい波を眺めながら祭りを楽しむ風景", "evkind-flowers": "八達山城郭の道と万石公園の湖周遊路に沿って華やかに満開となった春の桜祭り風景", "evkind-nature": "夕焼けのススキと温室庭園が調和する日月樹木園と西湖公園の生態散策路風景", "evkind-night": "三日月の下、華城行宮の瓦屋根と訪花随柳亭の上にほのかな夜間景観照明とチョンサチョロンが灯る夜行風景", "evkind-food": "温かな夜の照明の下、八達門夜市と庭園テラスに並ぶ水原グルメとデザート", "evkind-stage": "夕日が沈む光教湖水公園の野外舞台と京畿想像キャンパスの芝生広場に温かな照明が灯るジャズ・演劇公演風景", "evkind-market": "日差しあふれる八達門・水原南門市場と行宮広場に白いテントブースと手工芸品が並ぶ市場の風景", "evkind-ceremony": "朝日が差し込む華城行宮と正祖路広場に水原華城文化祭の伝統旗とチョンサチョロンが調和する風景", "evkind-race": "朝日の中、春の花が咲く光教湖周遊路と西湖川水辺道に沿って続く水原ウォーキング・サイクリングコース", "evkind-book": "温かな午後の日差しが差す京畿図書館と京畿想像キャンパスの森の芝生広場の屋外本棚と読書庭園", "evkind-alley": "夕焼けが差し込む水原・行理団通りと工房通りの路地に温かなストリングライトとテラスの鉢植えが置かれた風景", "evkind-other": "青空の下、風車が回る国立農業博物館の棚田と芝生庭園の風景", "month-01": "雪に覆われた八達山・西将台と水原華城の城郭の上に昇る1月の黄金色の水原の初日の出", "month-02": "青い夕暮れの華城行宮と訪花随柳亭の瓦屋根の上に明るく輝く2月の正月大満月の風景", "month-03": "華城行宮と華寧殿の伝統石垣の前に華やかに咲いた3月の紅梅と黄色いサンシュユの花枝", "month-04": "澄んだ4月の春空の下、万石公園と八達山城郭の道に沿ってトンネルをなす薄紅色の桜並木風景", "month-05": "青い5月の新緑の中、日月樹木園と京畿想像キャンパスの森に咲いた華やかな春の花庭園風景", "month-06": "初夏の訪花随柳亭・龍淵と万石公園の池に緑の柳と蓮の葉が広がる6月の風景", "month-07": "青い7月の光教湖水公園の水辺噴水と光教山渓谷の木陰の下の涼しい夏の散策風景", "month-08": "ほのかな8月の夏の夜の照明の下、華城行宮と訪花随柳亭の城郭の道を歩く水原国家遺産夜行の風景", "month-09": "高く澄んだ9月の秋空の下、光教湖水公園ジャズフェスティバルの舞台と華西門メディアアートが調和する風景", "month-10": "水原華城の城郭と華城行宮の紅葉が赤く染まり、水原華城文化祭の灯籠が灯る10月の水原の秋風景", "month-11": "伝統石垣と瓦屋根の上に黄金色のイチョウの葉が積もった11月の水原郷校・孝園公園粤華苑の晩秋風景", "month-12": "白い雪が積もった水原華城・訪花随柳亭と温かな冬の照明が灯る行理団通りの12月の冬夜景", "abroad-press": "訪花随柳亭と水原華城が見える窓辺の木のテーブルの上に置かれた海外紙と温かいドリップコーヒー1杯", "abroad-official": "華城行宮の瓦屋根と城郭を見下ろす窓辺の木の机に置かれた地球儀と水色の公式案内フォルダ", "abroad-travel": "旅行手帳2冊とパスポート、水原華城・訪花随柳亭の写真ハガキとコーヒーカップが置かれたカフェの木のテーブル", "abroad-blog": "夕焼けの水原華城と光教湖の写真が画面に映るノートパソコンと白いコーヒーマグ、カメラレンズが置かれた木の机", "abroad-research": "華城城役儀軌の図版と水原の生態地図が開かれた学術書と真鍮のルーペ、松ぼっくりが置かれた机", "abroad-videos": "黄金色の夕焼けが映る水原華城と訪花随柳亭に向けてウッドデッキの上に据えられた三脚のシネマカメラ"}
        zhs_map = {"head-places": "融合水原华城长安门、访花随柳亭龙渊、华城行宫瓦屋顶与光教湖水公园水畔的水原全景", "head-food": "阳光洒入的窗边木餐桌上摆放着水原烤王排骨、铁锅炸鸡、池洞市场米肠与行理团路手冲咖啡", "head-stays": "暮色中水原华城城郭下静谧的行宫洞韩屋住宿瓦屋顶与光教湖畔酒店灯光交相辉映的住宿风景", "head-courses": "串联水原华城城郭散步道、访花随柳亭池塘、日月树木园温室与光教湖水公园木栈道的水原旅行路线风景", "head-guides": "晨光洒落在访花随柳亭龙渊柳树散步道与日月树木园庭园的风景", "head-events": "夜空下华城行宫与长安门城郭上方点亮水原华城文化节灯笼与媒体艺术灯光的水原节庆风景", "head-videos": "夕阳下俯瞰访花随柳亭与水原华城城郭的山丘上的电影摄影机", "head-abroad": "融合联合国教科文组织世界遗产水原华城长安门、访花随柳亭、华城行宫与光教湖水公园的水原全景", "head-map": "从长安区光教山、万石公园延伸至八达区水原华城、华城行宫、劝善区日月树木园与灵通区光教湖水公园的水原市鸟瞰全景", "about-hero": "松林与龙渊池塘彼端展现访花随柳亭楼阁与水原华城城郭的水原风景", "plan-hero": "春日樱花盛开的八达山城郭步道与访花随柳亭池塘远眺的水原晨景", "area-hwaseong-haenggung": "连接华城行宫正殿、长安门与访花随柳亭城郭步道及行理团路露台咖啡厅的行宫片区风景", "area-paldalmun-market": "融合八达门城门、热闹的南门与池洞传统市场、飘香水原炸鸡街与水原川的八达片区风景", "area-gwanggyo-yeongtong": "串联光教湖水公园水畔木栈道、弗赖堡观景台、光教水族馆与水原光教博物馆的光教·灵通片区风景", "area-manseok-jangan": "连接万石公园湖泊、迎华亭凉亭、老松地带松林路与光教山散步道的长安片区风景", "area-irwol-gwonseon": "融合日月树木园玻璃温室、西湖公园落日、国立农业博物馆与京畿想象校园林道的劝善·西水原风景", "guide-01": "晴朗日子里水原华城城郭步道、访花随柳亭龙渊与华城行宫瓦屋顶交融的风景", "guide-02": "日月树木园温室花园、光教水族馆与国立农业博物馆草坪广场交融的水原家庭出游风景", "guide-03": "透过落地窗望见雨后城郭松树、灯光温暖的水原市立美术馆与星空图书馆室内展厅空间", "guide-04": "晴朗日子里系着牵引绳沿着光教湖水公园与万石公园木栈道散步的金毛犬与白色比熊犬", "guide-05": "可眺望城郭的餐厅窗边摆放着水原王排骨、酥脆铁锅炸鸡、刀削面与行理团路手冲咖啡", "guide-06": "星光映照的夜晚，行宫洞静谧韩屋庭院与光教湖附近酒店温暖灯光交融的住宿风景", "course-suwon-course-1": "夕阳下的华城行宫、西将台、华西门、长安门、访花随柳亭与行理团路相连的水原华城城郭漫步风景", "course-suwon-course-2": "从练武台射箭场、飞越水原热气球、苍龙门与八达门延伸至池洞市场、水原炸鸡街的徒步旅行风景", "course-suwon-course-3": "融合光教湖水公园水畔步道、弗赖堡观景台、光教水族馆与水原光教博物馆、水原博物馆的风景", "course-suwon-course-4": "串联日月树木园温室、西湖公园水畔、国立农业博物馆、京畿想象校园与星空图书馆的生态文化风景", "course-suwon-course-5": "连接万石公园湖泊、老松地带黑松路、解忧斋庭园与奉宁寺、光教山林道的长安区风景", "course-suwon-course-6": "串联孝园公园粤华苑传统亭阁、京畿艺术中心、三星创新博物馆与灵兴树木园的都市园林漫游风景", "card-event": "暮色中华城行宫广场与长安门城郭点亮温暖的水原华城文化节灯笼与媒体艺术的节庆风景", "card-guide": "垂柳与荷花盛开的访花随柳亭龙渊水畔散步道远眺城郭亭阁的风景", "card-video": "朝阳升起的水原华城访花随柳亭与光教湖水公园水畔染上金光的水原航拍风景", "card-abroad": "晴空下融合水原华城长安门、华城行宫瓦屋顶、访花随柳亭与光教湖水公园的水原全景", "card-course": "夕阳下水原华城城郭散步道通往西将台、华西门与访花随柳亭的风景", "chat-empty": "行理团路咖啡厅窗边木桌上摊开的水原旅游地图、指南针、相机与一杯手冲咖啡", "art-404": "晨雾缭绕的访花随柳亭龙渊池塘与垂柳旁静置的木长椅以及远处的城郭亭阁", "art-search-empty": "俯瞰平静光教湖水面的木长椅上放着的手摇咖啡磨豆机、旅行笔记本与望远镜", "vtopic-yeohaeng-koseu": "金色阳光下沿水原华城城郭步道通往华城行宫与访花随柳亭的散步道风景", "vtopic-suwon-hwaseong-haenggung": "宏伟的长安门、八达门城郭与华城行宫正殿、空中升起的飞越水原热气球风景", "vtopic-haengnidan-banghwasuryujeong": "倒映在龙渊池塘中的访花随柳亭楼阁与精致的行理团路天台咖啡街巷风景", "vtopic-gwanggyo-hosu": "连接光教湖水公园水畔木栈道、弗赖堡观景台与光教水族馆的灵通区水畔风景", "vtopic-sumogwon-gongwon": "融合日月树木园、灵兴树木园玻璃温室、孝园公园粤华苑与光教山林道的水原绿地风景", "vtopic-bangmulgwan-misulgwan": "融合水原华城博物馆、水原市立美术馆、水原Starfield星空图书馆与国立农业博物馆的文化风景", "vtopic-wanggalbi-tongdak-sijang": "窗边木餐桌上摆放的水原烤王排骨、铁锅炸鸡与八达门、池洞传统市场美食", "vtopic-kape-dijeoteu": "俯瞰行宫洞与光教湖水公园的天台露台上摆放的手冲咖啡与手工烘焙甜点", "vtopic-chukje-yagan": "华城行宫夜间开放青纱灯笼与华西门、长安门媒体艺术光影交相辉映的水原华城文化节夜景", "vtopic-other": "华宁殿石墙路、老松地带松林与西湖公园落日交融的宁静水原风景", "evkind-sea": "晴朗日子里在光教湖水公园与万石渠水畔木栈道眺望清凉水波享受节庆的风景", "evkind-flowers": "沿着八达山城郭步道与万石公园环湖路绚丽盛开的春日樱花节庆风景", "evkind-nature": "夕阳下芒草与温室庭园相映的日月树木园与西湖公园生态散步道风景", "evkind-night": "新月下华城行宫瓦屋顶与访花随柳亭亮起柔和夜间景观灯与青纱灯笼的夜游风景", "evkind-food": "温馨夜晚灯光下八达门夜市与花园露台餐桌上摆放的水原美食与甜点", "evkind-stage": "夕阳下光教湖水公园户外舞台与京畿想象校园草坪广场亮起温暖灯光的爵士乐与戏剧演出风景", "evkind-market": "阳光充沛的八达门、水原南门市场与行宫广场上陈列着白色帐篷摊位与手工艺品的集市风景", "evkind-ceremony": "晨光映照的华城行宫与正祖路广场上水原华城文化节传统旌旗与青纱灯笼相映的风景", "evkind-race": "朝阳下春花盛开的光教湖环湖路与西湖川水畔道路延伸的水原徒步与自行车赛道", "evkind-book": "温暖午后阳光洒落在京畿图书馆与京畿想象校园森林草坪上的户外木书架与阅读花园", "evkind-alley": "夕阳映照的水原行理团路与工坊街巷弄里点缀着温暖串灯与露台花盆的风景", "evkind-other": "蓝天下风车转动的国立农业博物馆梯田与草坪庭园风景", "month-01": "白雪覆盖的八达山西将台与水原华城城郭上方升起的1月金色水原新年日出", "month-02": "深蓝暮色中华城行宫与访花随柳亭瓦屋顶上方皎洁照耀的2月元宵圆月风景", "month-03": "华城行宫与华宁殿传统石墙前绚丽绽放的3月红梅与金黄山茱萸花枝", "month-04": "晴朗4月春空下沿着万石公园与八达山城郭步道形成花廊的浅粉樱花路风景", "month-05": "翠绿5月新绿中日月树木园与京畿想象校园森林里盛开的春日花园风景", "month-06": "初夏访花随柳亭龙渊与万石公园池塘里翠绿垂柳与荷叶铺展的6月风景", "month-07": "碧绿7月光教湖水公园水畔喷泉与光教山溪谷树荫下清凉的夏日散步风景", "month-08": "柔和8月夏夜灯光下漫步于华城行宫与访花随柳亭城郭步道的水原国家遗产夜行风景", "month-09": "高远湛蓝的9月秋空下光教湖水公园爵士音乐节舞台与华西门媒体艺术交相辉映的风景", "month-10": "水原华城城郭与华城行宫红叶染红、点亮水原华城文化节灯笼的10月水原秋日风景", "month-11": "传统石墙与瓦屋顶上铺满金黄银杏叶的11月水原乡校、孝园公园粤华苑晚秋风景", "month-12": "白雪覆盖的水原华城访花随柳亭与点亮温暖冬日灯光的行理团路12月冬夜景色", "abroad-press": "俯瞰访花随柳亭与水原华城的窗边木桌上放置的外媒报纸与热手冲咖啡", "abroad-official": "俯瞰华城行宫瓦屋顶与城郭的窗前木书桌上的地球仪与天蓝色官方指南文件夹", "abroad-travel": "摆放着两本旅行笔记本、护照、水原华城与访花随柳亭明信片及咖啡杯的咖啡馆木桌", "abroad-blog": "显示着水原华城与光教湖夕阳照片的笔记本电脑、白色马克杯与相机镜头的木书桌", "abroad-research": "摊开着华城城役仪轨图版与水原生态地图的学术书籍、黄铜放大镜与松果的书桌", "abroad-videos": "朝向夕阳映照的水原华城与访花随柳亭架设在木栈道上的三脚架电影摄影机"}
        zht_map = {"head-places": "融合水原華城長安門、訪花隨柳亭龍淵、華城行宮瓦屋頂與光教湖水公園水畔的水原全景", "head-food": "陽光灑入的窗邊木餐桌上擺放著水原烤王排骨、鐵鍋炸雞、池洞市場米腸與行理團路手沖咖啡", "head-stays": "暮色中水原華城城郭下靜謐的行宮洞韓屋住宿瓦屋頂與光教湖畔飯店燈光交相輝映的住宿風景", "head-courses": "串聯水原華城城郭散步道、訪花隨柳亭池塘、日月樹木園溫室與光教湖水公園木棧道的水原旅行路線風景", "head-guides": "晨光灑落在訪花隨柳亭龍淵柳樹散步道與日月樹木園庭園的風景", "head-events": "夜空下華城行宮與長安門城郭上方點亮水原華城文化節燈籠與媒體藝術燈光的水原節慶風景", "head-videos": "夕陽下俯瞰訪花隨柳亭與水原華城城郭的山丘上的電影攝影機", "head-abroad": "融合聯合國教科文組織世界遺產水原華城長安門、訪花隨柳亭、華城行宮與光教湖水公園的水原全景", "head-map": "從長安區光教山、萬石公園延伸至八達區水原華城、華城行宮、勸善區日月樹木園與靈通區光教湖水公園的水原市鳥瞰全景", "about-hero": "松林與龍淵池塘彼端展現訪花隨柳亭樓閣與水原華城城郭的水原風景", "plan-hero": "春日櫻花盛開的八達山城郭步道與訪花隨柳亭池塘遠眺的水原晨景", "area-hwaseong-haenggung": "連接華城行宮正殿、長安門與訪花隨柳亭城郭步道及行理團路露台咖啡廳的行宮片區風景", "area-paldalmun-market": "融合八達門城門、熱鬧的南門與池洞傳統市場、飄香水原炸雞街與水原川的八達片區風景", "area-gwanggyo-yeongtong": "串聯光教湖水公園水畔木棧道、弗賴堡觀景台、光教水族館與水原光教博物館的光教·靈通片區風景", "area-manseok-jangan": "連接萬石公園湖泊、迎華亭涼亭、老松地帶松林路與光教山散步道的長安片區風景", "area-irwol-gwonseon": "融合日月樹木園玻璃溫室、西湖公園落日、國立農業博物館與京畿想像校園林道的勸善·西水原風景", "guide-01": "晴朗日子裡水原華城城郭步道、訪花隨柳亭龍淵與華城行宮瓦屋頂交融的風景", "guide-02": "日月樹木園溫室花園、光教水族館與國立農業博物館草坪廣場交融的水原家庭出遊風景", "guide-03": "透過落地窗望見雨後城郭松樹、燈光溫暖的水原市立美術館與星空圖書館室內展廳空間", "guide-04": "晴朗日子裡繫著牽引繩沿著光教湖水公園與萬石公園木棧道散步的金毛犬與白色比熊犬", "guide-05": "可眺望城郭的餐廳窗邊擺放著水原王排骨、酥脆鐵鍋炸雞、刀削麵與行理團路手沖咖啡", "guide-06": "星光映照的夜晚，行宮洞靜謐韓屋庭院與光教湖附近飯店溫暖燈光交融的住宿風景", "course-suwon-course-1": "夕陽下的華城行宮、西將臺、華西門、長安門、訪花隨柳亭與行理團路相連的水原華城城郭漫步風景", "course-suwon-course-2": "從練武臺射箭場、飛越水原熱氣球、蒼龍門與八達門延伸至池洞市場、水原炸雞街的徒步旅行風景", "course-suwon-course-3": "融合光教湖水公園水畔步道、弗賴堡觀景台、光教水族館與水原光教博物館、水原博物館的風景", "course-suwon-course-4": "串聯日月樹木園溫室、西湖公園水畔、國立農業博物館、京畿想像校園與星空圖書館的生態文化風景", "course-suwon-course-5": "連接萬石公園湖泊、老松地帶黑松路、解憂齋庭園與奉寧寺、光教山林道的長安區風景", "course-suwon-course-6": "串聯孝園公園粵華苑傳統亭閣、京畿藝術中心、三星創新博物館與靈興樹木園的都市園林漫遊風景", "card-event": "暮色中華城行宮廣場與長安門城郭點亮溫暖的水原華城文化節燈籠與媒體藝術的節慶風景", "card-guide": "垂柳與荷花盛開的訪花隨柳亭龍淵水畔散步道遠眺城郭亭閣的風景", "card-video": "朝陽升起的水原華城訪花隨柳亭與光教湖水公園水畔染上金光的水原航拍風景", "card-abroad": "晴空下融合水原華城長安門、華城行宮瓦屋頂、訪花隨柳亭與光教湖水公園的水原全景", "card-course": "夕陽下水原華城城郭散步道通往西將臺、華西門與訪花隨柳亭的風景", "chat-empty": "行理團路咖啡廳窗邊木桌上攤開的水原旅遊地圖、指南針、相機與一杯手沖咖啡", "art-404": "晨霧繚繞的訪花隨柳亭龍淵池塘與垂柳旁靜置的木長椅以及遠處的城郭亭閣", "art-search-empty": "俯瞰平靜光教湖水面的木長椅上放著的手搖咖啡磨豆機、旅行筆記本與望遠鏡", "vtopic-yeohaeng-koseu": "金色陽光下沿水原華城城郭步道通往華城行宮與訪花隨柳亭的散步道風景", "vtopic-suwon-hwaseong-haenggung": "宏偉的長安門、八達門城郭與華城行宮正殿、空中升起的飛越水原熱氣球風景", "vtopic-haengnidan-banghwasuryujeong": "倒映在龍淵池塘中的訪花隨柳亭樓閣與精緻的行理團路天台咖啡街巷風景", "vtopic-gwanggyo-hosu": "連接光教湖水公園水畔木棧道、弗賴堡觀景台與光教水族館的靈通區水畔風景", "vtopic-sumogwon-gongwon": "融合日月樹木園、靈興樹木園玻璃溫室、孝園公園粵華苑與光教山林道的水原綠地風景", "vtopic-bangmulgwan-misulgwan": "融合水原華城博物館、水原市立美術館、水原Starfield星空圖書館與國立農業博物館的文化風景", "vtopic-wanggalbi-tongdak-sijang": "窗邊木餐桌上擺放的水原烤王排骨、鐵鍋炸雞與八達門、池洞傳統市場美食", "vtopic-kape-dijeoteu": "俯瞰行宮洞與光教湖水公園的天台露台上擺放的手沖咖啡與手工烘焙甜點", "vtopic-chukje-yagan": "華城行宮夜間開放青紗燈籠與華西門、長安門媒體藝術光影交相輝映的水原華城文化節夜景", "vtopic-other": "華寧殿石牆路、老松地帶松林與西湖公園落日交融的寧靜水原風景", "evkind-sea": "晴朗日子裡在光教湖水公園與萬石渠水畔木棧道眺望清涼水波享受節慶的風景", "evkind-flowers": "沿著八達山城郭步道與萬石公園環湖路絢麗盛開的春日櫻花節慶風景", "evkind-nature": "夕陽下芒草與溫室庭園相映的日月樹木園與西湖公園生態散步道風景", "evkind-night": "新月下華城行宮瓦屋頂與訪花隨柳亭亮起柔和夜間景觀燈與青紗燈籠的夜遊風景", "evkind-food": "溫馨夜晚燈光下八達門夜市與花園露台餐桌上擺放的水原美食與甜點", "evkind-stage": "夕陽下光教湖水公園戶外舞台與京畿想像校園草坪廣場亮起溫暖燈光的爵士樂與戲劇演出風景", "evkind-market": "陽光充沛的八達門、水原南門市場與行宮廣場上陳列著白色帳篷攤位與手工藝品的集市風景", "evkind-ceremony": "晨光映照的華城行宮與正祖路廣場上水原華城文化節傳統旌旗與青紗燈籠相映的風景", "evkind-race": "朝陽下春花盛開的光教湖環湖路與西湖川水畔道路延伸的水原徒步與自行車賽道", "evkind-book": "溫暖午後陽光灑落在京畿圖書館與京畿想像校園森林草坪上的戶外木書架與閱讀花園", "evkind-alley": "夕陽映照的水原行理團路與工房街巷弄裡點綴著溫暖串燈與露台花盆的風景", "evkind-other": "藍天下風車轉動的國立農業博物館梯田與草坪庭園風景", "month-01": "白雪覆蓋的八達山西將臺與水原華城城郭上方升起的1月金色水原新年日出", "month-02": "深藍暮色中華城行宮與訪花隨柳亭瓦屋頂上方皎潔照耀的2月元宵圓月風景", "month-03": "華城行宮與華寧殿傳統石牆前絢麗綻放的3月紅梅與金黃山茱萸花枝", "month-04": "晴朗4月春空下沿著萬石公園與八達山城郭步道形成花廊的淺粉櫻花路風景", "month-05": "翠綠5月新綠中日月樹木園與京畿想像校園森林裡盛開的春日花園風景", "month-06": "初夏訪花隨柳亭龍淵與萬石公園池塘裡翠綠垂柳與荷葉鋪展的6月風景", "month-07": "碧綠7月光教湖水公園水畔噴泉與光教山溪谷樹蔭下清涼的夏日散步風景", "month-08": "柔和8月夏夜燈光下漫步於華城行宮與訪花隨柳亭城郭步道的水原國家遺產夜行風景", "month-09": "高遠湛藍的9月秋空下光教湖水公園爵士音樂節舞台與華西門媒體藝術交相輝映的風景", "month-10": "水原華城城郭與華城行宮紅葉染紅、點亮水原華城文化節燈籠的10月水原秋日風景", "month-11": "傳統石牆與瓦屋頂上鋪滿金黃銀杏葉的11月水原鄉校、孝園公園粵華苑晚秋風景", "month-12": "白雪覆蓋的水原華城訪花隨柳亭與點亮溫暖冬日燈光的行理團路12月冬夜景色", "abroad-press": "俯瞰訪花隨柳亭與水原華城的窗邊木桌上放置的外媒報紙與熱手沖咖啡", "abroad-official": "俯瞰華城行宮瓦屋頂與城郭的窗前木書桌上的地球儀與天藍色官方指南資料夾", "abroad-travel": "擺放著兩本旅行筆記本、護照、水原華城與訪花隨柳亭明信片及咖啡杯的咖啡館木桌", "abroad-blog": "顯示著水原華城與光教湖夕陽照片的筆記型電腦、白色馬克杯與相機鏡頭的木書桌", "abroad-research": "攤開著華城城役儀軌圖版與水原生態地圖的學術書籍、黃銅放大鏡與松果的書桌", "abroad-videos": "朝向夕陽映照的水原華城與訪花隨柳亭架設在木棧道上的三腳架電影攝影機"}
        images[art_id] = _art_entry(
            slot,
            ko_d,
            en_d,
            ja_map[art_id],
            zhs_map[art_id],
            zht_map[art_id],
            f"{en_d}",
            f"Paysage illustré de Suwon : {en_d}",
            f"Paisaje ilustrado de Suwon: {en_d}",
            f"Иллюстрация пейзажа Сувона: {en_d}",
            status=status,
            langs=langs,
            note=note,
        )

    og_alts = {
        "ko": "유네스코 세계문화유산 수원화성과 화성행궁, 방화수류정과 광교호수공원·일월수목원이 어우러진 수원 풍경",
        "en": "Panoramic view of Suwon featuring UNESCO World Heritage Hwaseong Fortress, Hwaseong Haenggung Palace, Banghwasuryujeong, and Gwanggyo Lake",
        "ja": "ユネスコ世界遺産・水原華城と華城行宮、訪花随柳亭と光教湖水公園・日月樹木園が調和する水原の全景",
        "zh-hans": "融合联合国教科文组织世界遗产水原华城、华城行宫、访花随柳亭与光教湖水公园·日月树木园的水原全景",
        "zh-hant": "融合聯合國教科文組織世界遺產水原華城、華城行宮、訪花隨柳亭與光教湖水公園·日月樹木園的水原全景",
        "de": "Panoramablick auf Suwon mit der UNESCO-Welterbefestung Hwaseong, dem Palast Hwaseong Haenggung, Banghwasuryujeong und dem Gwanggyo-See",
        "fr": "Vue panoramique sur Suwon avec la forteresse Hwaseong classée par l’UNESCO, le palais Hwaseong Haenggung, Banghwasuryujeong et le lac Gwanggyo",
        "es": "Vista panorámica de Suwon con la Fortaleza Hwaseong de la UNESCO, el Palacio Hwaseong Haenggung, Banghwasuryujeong y el lago Gwanggyo",
        "ru": "Панорамный вид на Сувон: крепость Хвасон (ЮНЕСКО), дворец Хвасон Хэнгун, павильон Панхвасурюджон и озеро Квангёхо",
    }

    images["og-default"] = _art_entry(
        "og.default",
        og_alts["ko"],
        og_alts["en"],
        og_alts["ja"],
        og_alts["zh-hans"],
        og_alts["zh-hant"],
        og_alts["de"],
        og_alts["fr"],
        og_alts["es"],
        og_alts["ru"],
        langs=["ko"],
    )
    images["og-plan"] = _art_entry(
        "og.plan",
        "봄 벚꽃이 핀 수원화성 성곽길과 방화수류정에서 바라보는 수원 여행 코스 풍경",
        og_alts["en"],
        og_alts["ja"],
        og_alts["zh-hans"],
        og_alts["zh-hant"],
        og_alts["de"],
        og_alts["fr"],
        og_alts["es"],
        og_alts["ru"],
        langs=["ko"],
    )
    images["og-abroad"] = _art_entry(
        "og.abroad",
        "수원화성 장안문과 화성행궁 기와지붕, 방화수류정과 광교호수공원이 어우러진 수원시 전경",
        og_alts["en"],
        og_alts["ja"],
        og_alts["zh-hans"],
        og_alts["zh-hant"],
        og_alts["de"],
        og_alts["fr"],
        og_alts["es"],
        og_alts["ru"],
        langs=["ko"],
    )
    for lang in ALL_LANGS:
        if lang == "ko":
            continue
        slot = "og.default-en" if lang == "en" else f"og.{lang}"
        images[f"og-{lang}"] = _art_entry(
            slot,
            og_alts["ko"],
            og_alts["en"],
            og_alts["ja"],
            og_alts["zh-hans"],
            og_alts["zh-hant"],
            og_alts["de"],
            og_alts["fr"],
            og_alts["es"],
            og_alts["ru"],
            langs=[lang],
        )

    for art_id, meta in images.items():
        meta["file"] = f"{art_id}.png"

    art_doc = {
        "_notes": [
            "AI 그림(CLAUDE.md 4절): 배경·캠페인 그림·장식으로만 쓴다. alt는 그 언어의 '일러스트: ' 머리말로 시작하고, 'AI 생성 이미지' 표기는 하지 않으며(소개 페이지에 한 번), 장소 페이지·장소 카드·구조화 데이터에는 쓰지 않는다(pipeline/art.py, validate).",
            "가이드 머리 그림(guide.banner.<id>)은 글자가 없어 외국어판 가이드에도 나간다(templates/en/guide.html.j2: intl.guide.banner가 없으면 이 그림).",
        ],
        "images": images,
        "held": {},
    }
    dump_json(DATA / "art.json", art_doc)
    probs = art.data_problems(DATA)
    assert not probs, f"art.data_problems: {probs}"
    print(f"Wrote art.json ({len(images)} entries, 0 problems)")


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
