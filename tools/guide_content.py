"""가이드 작성 도구 — 작성자용 장소 목록(catalog), 개수 계산(count), 기계 검사(check-guide), 반영(merge).
네트워크를 쓰지 않는다. 도시 값(시·도, 구·군, 상투구)은 site.json → pipeline.city.of(site)에서 오고, 이 파일에는
도시 이름이 없다. 문구 검사(BANNED·출처 복사)는 tools/place_content.py의 것을 그대로 쓴다.

    python tools/guide_content.py catalog --data data/<도시> --out work/guides/catalog.json [--with-text] [--kind food]
    python tools/guide_content.py count --data data/<도시> '{"kind": "food", "monday_open": true}' [--list]
    python tools/guide_content.py check-guide --data data/<도시> work/guides/guide-x.json [...] [--json]
    python tools/guide_content.py merge --data data/<도시> work/guides/guide-x.json [...] [--dry-run]

catalog — 작성자용 장소 목록(중복·제외 레코드는 뺀다): id·slug·name·kind·category·lcls(TourAPI 분류),
  district·area·road(City.parse_address), facts {키: 값}, 값마다 출처가 facts_source와 다를 때만 providers, 다른 출처
  값 differs, closed(쉬는 날 원문·매주 쉬는 요일·월요일 영업·연중무휴, pipeline.present의 같은 규칙), hours(첫 여는 시각·
  마지막 닫는 시각 — 준비시간·마지막 주문은 빼고, 자정 넘김은 next_day), geo [위도, 경도], photo(게재 가능한 사진 유무),
  summary, status, 있으면 nearby(근처 공영주차장·정류장·역 — 화면의 줄 값), designations(화면에 나가는 지정과 목록 키),
  courses(그 장소를 경유지로 잇는 공개 코스). --with-text는 TourAPI 소개문(source_text, 사실 확인용 — 옮겨 쓰기 금지)을
  더한다. 행사(events), 이미 있는 가이드(id·slug·title·label·items·FAQ 질문), 공개 코스(id·slug·name·group·duration·facts·
  stops), nearby 반경, 지정 목록(designation_lists: key·use·type·label·source_name·url·base_date와 다시 센 rows·kinds·
  file_rows)도 함께 쓴다.
count — 조건(where) 하나를 데이터에 적용해 개수와(--list) 해당 장소를 보인다. check-guide가 같은 함수로 다시 센다.
check-guide — 가이드 JSON(가이드 하나, 가이드 목록, 또는 {"guides": [...]})을 검사한다. 하나라도 걸리면 종료 코드 1.
  - 참조: items[].place_slug·route_slugs·mentions(본문에서 이름을 부른 장소)·counts의 slugs/near가 places.json에 있는
    장소(중복·제외 아님)여야 한다. event_ids는 events.json의 id. mentions의 이름은 글에 실제로 나와야 한다.
    courses는 courses.json의 공개 코스 slug(또는 id) — 공개 전 코스는 막고, 코스 이름(앞의 group 말을 뺀 이름도 됨)이 글에
    나와야 한다.
  - 개수(counts): [{n, what, where | names, items?}]. where는 COUNT_KEYS 조건이고 검사기가 다시 센다(n과 다르면 막음).
    names는 이름 목록(n = 서로 다른 이름 수, 이름마다 글에 나와야 함). items: true면 가이드 items의 장소 집합이 where
    결과와 정확히 같아야 한다(목록 개수를 주장하면 그만큼 싣는다). 공개 뒤에는 공개 장소·공개 코스만 센다(Data).
    근처(nearby.json)·지정 키는 묶음마다 같은 행 하나가 모두 맞아야 한다: lot_within·lot_paid(같은 주차장),
    stop_within·bus_route(같은 정류장), rail_within·rail_line·rail_station(같은 역), designation·designation_source(같은
    지정). nearby.json은 가까운 순 몇 곳만 담으므로(_meta의 max·radius_m) *_within은 반경 이하만 되고, 노선·역 조건은
    '담긴 가까운 정류장·역'에 대한 것이다. course는 공개 코스의 경유지(place_slug로 이은 곳). 데이터에 없는 노선·역·
    지정 유형·지정 목록·코스는 조건 오류다(오타가 0곳으로 세어지지 않게).
  - 숫자: 제목·라벨·요약·본문·items 사유·FAQ·answer의 숫자 묶음은 모두 (a) 참조 장소의 이름·사실 값·다른 출처 값·
    분류·주소·TourAPI 소개문, 참조 행사의 값, (b) 검사를 통과한 counts의 n과 기준값(closes_after·opens_before·near.m·
    *_within의 m·bus_route·rail_line·rail_station의 숫자), (c) items 개수, (d) 구·군 수, (e) 참조 장소의 근처 줄
    (present.lot_row·rail_row가 화면에 내는 값: 주차장 이름·유형·주소·면수·무료/유료·운영시간·요금 판마다의 분·원·
    문의 전화, 다른 출처 값; 정류장 이름·노선 번호; 화면의 역 이름·호선·출구 번호; 줄마다 직선 m — 단, 가는 길을 말하는
    글(주차·정류장·버스·노선·도시철도·지하철·호선·출구 같은 말(ACCESS_CUE)이나 그 줄의 주차장·정류장·역 이름이 있는
    제목·요약·본문 절·사유·FAQ 답 하나)에서만)과 화면에 나가는 지정(이름·연도·목록 이름), (f) courses로 참조한 공개
    코스의 이름·group·duration·facts(label·value·short)·경유지 이름·경유지 수, (g) sources에 적은 지정 목록(url이
    sources.json의 url과 같거나 이름이 source_name과 같음 — 화면 이름(label)만 같은 출처는 인용이 아님)의 다시 센 행 수
    (rows·kinds·file_rows)와 기준일, (h) sources에 적은 교통 자료(transit.json — 도시의 교통 수집 도구가 만든다: 블록의
    source url이 sources에 있을 때만)의 시간표 날짜·대수(전체·등급·등급 계열)·출발/도착 시각·요금·열차 번호·소요 시간과
    시내버스 노선 번호·기점/종점·방면, 탈 정류장에서 참조 장소 근처 정류장까지(돌아올 때는 그 정류장에서 탈 정류장까지)의
    정류장 수에 있어야 한다. m·km가 붙은 숫자는 참조 장소끼리의 직선거리와 근처 줄의 m(반올림
    표기, (e)와 같은 글에서만)도 된다. 'N곳'(두 곳 같은 한글 수 포함)은 개수 주장이라 (b)·(c)이거나 참조 사실·코스
    facts에 'N곳'으로 있거나 코스 경유지 수·인용한 목록의 행 수여야 한다. 시각(HH:MM)과 전화번호는 숫자 낱낱이 아니라
    통째로 참조 장소·행사·근처 줄((e)와 같은 글에서만)·코스의 값(또는 counts의 기준 시각)에 있어야 한다.
  - 문구: place_content.BANNED(출처 해설체·전언체·'확인 필요'·근거 없는 수식어)와 STOCK(상투어·추천·감탄),
    schema.SOURCE_COMMENTARY. 장소 이름과 (e)~(g)의 고유 이름(주차장·정류장·역·지정·코스·경유지)은 지우고 본다.
    items 사유의 첫 문장이 상투구(City.taut_rx)면 막는다.
  - 복사: 참조 장소의 TourAPI 소개문과 15자 이상 연속 일치(이름·사실 값 제외, place_content._longest_copy).
  - 모양: id·title(질문형 '?')·label·slug(ASCII, pipeline.slugs.is_slug, 다른 가이드와 겹치지 않음)·summary(문장마다
    '다.', 4문장 이하, (b)·(c)의 숫자 하나 이상)·body 2절 이상(heading·text)·items 사유·sources {name, url}·FAQ(존댓말
    의문형 JONDAE, source는 sources의 url·name 중 하나, 다른 가이드·장소 FAQ와 같은 질문 금지). 공개 필드(status·
    reviewed_at·approved_at·approved_by)는 guides.json에 있는 값 그대로여야 하고, 새 가이드는 status "draft"·빈 검수일이다.
merge — check-guide를 다시 돌려 깨끗한 가이드만 guides.json에 넣는다(같은 id는 교체, 새 id는 뒤에). 임시 파일 +
  os.replace로 쓰고, 읽은 뒤 guides.json이 바뀌었으면 아무것도 쓰지 않는다. --dry-run은 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import present
from pipeline.schema import SOURCE_COMMENTARY, summary_sentences
from pipeline.schema import designations as shown_designations
from pipeline.slugs import is_slug, slugify
from pipeline.textutil import squash_ws
from tools import place_content as pc

SUMMARY_MAX_SENTENCES = 4
BODY_MIN = 2
STATUS_FIELDS = ("status", "reviewed_at", "approved_at", "approved_by")
TEXT_MAX = 1500
STOCK = [
    (r"다양한|즐길\s*수\s*있|즐기(기|세요)|만끽|풍성|풍부한", "상투어('다양한·즐길 수 있는')"),
    (r"추천(합니다|드립니다|해요|할\s*만|하는)|가\s*볼\s*만|들러\s*보세요|가\s*보세요|방문해\s*보세요", "추천·권유"),
    (r"놓치지|빼놓을\s*수\s*없|제격|안성맞춤|매력|색다른|이색적|운치|정취|맛있|좋은\s*곳|좋습니다|좋아요|분위기\s*좋",
     "근거 없는 평가"),
]
KNUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
NUM_RX = re.compile(r"\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:\.\d+)?")
GO_RX = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s*곳")
KGO_RX = re.compile(r"(?<![가-힣])(" + "|".join(KNUM) + r")\s*곳")
DIST_UNIT = re.compile(r"\s*(?:km|㎞|킬로미터|미터|m(?![A-Za-z²㎡]))")
HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")
CLOCK_RX = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
COUNT_KEYS = {
    "kind": "유형(attraction·food·stay) 하나 또는 목록",
    "category": "분류 값(정확히 같음) 하나 또는 목록",
    "lcls": "TourAPI 분류 코드 앞부분 하나 또는 목록 ('VE07', 'FD0101')",
    "district": "구·군 하나 또는 목록", "area": "동·읍·면 하나 또는 목록",
    "name": "이름 정규식(search)", "not_name": "이름이 맞지 않을 정규식",
    "fact": "{키 또는 '키1|키2': 정규식} — 그 키들 가운데 하나의 값이 맞음(모든 조건 AND)",
    "not_fact": "{키 또는 '키1|키2': 정규식} — 어느 키의 값도 맞지 않음(값 없음 포함)",
    "has": "값이 있어야 할 키 목록", "lacks": "값이 없어야 할 키 목록",
    "monday_open": "true: 쉬는 날 값이 요일을 말하고 월요일이 없음(일부 월요일도 없음), 출처끼리 다르지 않음",
    "closed_on": "매주 쉬는 요일 글자('월', '월화' = 둘 다)",
    "closed_partly_on": "일부 주에만 쉬는 요일 글자('첫째·셋째 월요일', '격주 월요일' → '월')",
    "weekly_closed": "true: 요일로 쉬는 날이 있음(매주 또는 일부 주) / false: 없음",
    "open_all_year": "true: 쉬는 날 값이 연중무휴·상시 개방",
    "closes_after": "'HH:MM' — 마지막 닫는 시각이 이 시각과 같거나 늦음(자정 넘김은 24:00 이후, '25:30' 표기 가능)",
    "opens_before": "'HH:MM' — 첫 여는 시각이 이 시각과 같거나 이름",
    "near": "{slug, m} — 그 장소에서 직선 m미터 안(좌표 있는 곳만, 그 장소 자신 제외)",
    "slugs": "slug 목록 — 그중 데이터에 있는 장소", "summary": "true: 요약이 있음 / false: 없음",
    "photo": "true: 게재 가능한 사진(공공누리 제1·3유형)이 있음", "geo": "true: 좌표가 있음(near·지도에 들어감) / false: 없음",
    "any": "조건 목록 — 하나라도 맞음(OR)",
    "not": "조건 — 맞지 않음",
    # nearby.json (장소 좌표에서 직선거리로 잰 근처 공영주차장·시내버스 정류장·도시철도역 — 장소 자체의 주차·교통이 아님).
    # 같은 묶음의 키는 같은 행 하나가 모두 맞아야 한다(lot_within+lot_paid = 그 거리 안의 그 요금 주차장).
    "lot_within": "m — 근처 공영주차장(nearby.json, 가까운 순 최대 _meta.parking.max곳, 근처 목록에서 뺀 주차장 제외) 하나가 "
                  "직선 m미터 안. m은 _meta.parking.radius_m 이하",
    "lot_paid": "true: 그 근처 공영주차장이 '유료' / false: '무료'('혼합'이거나 두 출처 값이 다르면 어느 쪽도 아님)",
    "stop_within": "m — 근처 시내버스 정류장(nearby.json, 가까운 순 최대 _meta.bus.max곳) 하나가 직선 m미터 안. "
                   "m은 _meta.bus.radius_m 이하",
    "bus_route": "노선 번호 하나 또는 목록(nearby.json의 routes 값 그대로) — 근처 정류장의 경유노선에 정확히 같은 값이 있음",
    "rail_within": "m — 근처 도시철도역(nearby.json, 가장 가까운 출구까지, 최대 _meta.rail.max곳)이 직선 m미터 안. "
                   "m은 _meta.rail.radius_m 이하",
    "rail_line": "'3호선' 하나 또는 목록 — 근처 역의 노선",
    "rail_station": "역 이름 하나 또는 목록('○○역'·'○○' 모두 됨) — 근처 역",
    "designation": "지정 유형(places.json designations의 type: 'ansim'·'mobeom'·'goodprice'·'baeknyeon' 등) 하나 또는 "
                   "목록, 또는 true(하나라도) — 화면에 나가는 지정만(schema.designations)",
    "designation_source": "지정 목록 키(data/raw/<도시>/designations/sources.json의 key, 지정의 match.row_ref 앞부분) "
                          "하나 또는 목록 — designation과 함께 쓰면 같은 지정",
    "course": "공개 코스(courses.json)의 id·slug·group 하나 또는 목록, 또는 true — 그 코스의 경유지(stops의 place_slug)",
}
LOT_KEYS = ("lot_within", "lot_paid")
STOP_KEYS = ("stop_within", "bus_route")
RAIL_KEYS = ("rail_within", "rail_line", "rail_station")
DESIGNATION_KEYS = ("designation", "designation_source")
WITHIN = {"lot_within": "parking", "stop_within": "bus", "rail_within": "rail"}   # key -> nearby.json _meta section
NEARBY_RADIUS = {"parking": 500, "bus": 500, "rail": 800}   # pipeline.present.access_vm's defaults when _meta has none
TEXT_KEYS = ("bus_route", "rail_line", "rail_station", "designation_source")
# a text that is about getting there: only such a text (or one naming a nearby row) may use the nearby rows' values
ACCESS_CUE = re.compile(r"주차|정류장|정류소|정거장|버스|노선|도시철도|지하철|전철|호선|출구|환승")


# ------------------------------------------------------------------ io
def load_json(path: Path, default=None):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _text(value) -> str:
    return squash_ws("" if value is None else str(value))


def _list(value) -> list:
    return [] if value is None else list(value) if isinstance(value, (list, tuple, set)) else [value]


class Data:
    """One data folder: the City, the shown places (no duplicate_of / exclude), events, guides, the shown courses,
    nearby.json + parking_lots.json (근처 공영주차장·정류장·역) and the designation lists (data/raw/<도시>/designations).
    Once the site is public (some place is published) a guide's '이 사이트에 실린 n곳' means the published places —
    production pages show nothing else — so a draft record (a new TourAPI place before its summary and approval) is
    neither counted nor referable and the counts stay true when drafts arrive. Before launch (no published place)
    every record counts. Courses follow the same rule (and once any course is published, only published courses
    count): a draft course neither makes its stops count for `course` nor grounds a guide's numbers."""

    def __init__(self, data: Path):
        self.path = Path(data)
        self.city = pc.load_city(self.path)
        raw = load_json(self.path / "places.json", []) or []
        live = any(p.get("status") == "published" for p in raw)
        shown = lambda p: (not p.get("duplicate_of") and not p.get("exclude")  # noqa: E731
                           and (not live or p.get("status") == "published"))
        self.places = [p for p in raw if shown(p)]
        self.hidden = {p.get("slug") for p in raw if not shown(p)} - {None, ""}
        self.by_slug = {p.get("slug"): p for p in self.places if p.get("slug")}
        self.events = load_json(self.path / "events.json", []) or []
        self.event_by_id = {e.get("id"): e for e in self.events if e.get("id")}
        self.guides = load_json(self.path / "guides.json", []) or []
        courses = [c for c in load_json(self.path / "courses.json", []) or [] if isinstance(c, dict)]
        course_live = live or any(c.get("status") == "published" for c in courses)
        shown_course = lambda c: (not c.get("duplicate_of") and not c.get("exclude")  # noqa: E731
                                  and (not course_live or c.get("status") == "published"))
        self.courses = [c for c in courses if shown_course(c)]
        self.hidden_courses = {_text(c.get(k)) for c in courses if not shown_course(c) for k in ("id", "slug")} - {""}
        self.course_by_ref = {_text(c.get(k)): c for c in self.courses for k in ("id", "slug") if _text(c.get(k))}
        self.course_groups = {_text(c.get("group")) for c in self.courses} - {""}
        self.stop_courses: dict[str, list[dict]] = {}   # place slug -> the shown courses that link it as a stop
        for c in self.courses:
            for s in c.get("stops") or []:
                slug = _text((s if isinstance(s, dict) else {}).get("place_slug"))
                if slug and c not in self.stop_courses.setdefault(slug, []):
                    self.stop_courses[slug].append(c)
        nearby = load_json(self.path / "nearby.json", {}) or {}
        self.nearby_meta = nearby.get("_meta") or {}
        self.nearby = {k: v for k, v in nearby.items() if not k.startswith("_") and isinstance(v, dict)}
        parking = load_json(self.path / "parking_lots.json", {}) or {}
        self.parking_lots = {l["id"]: l for l in parking.get("lots") or [] if isinstance(l, dict) and l.get("id")}
        # what pipeline.present.lot_row reads from the build state (the same rows the place page prints)
        self._access_state = SimpleNamespace(city=self.city, site=load_json(self.path / "site.json", {}) or {},
                                             parking_source=parking.get("source") or {}, nearby_meta=self.nearby_meta,
                                             parking_contacts=parking.get("contacts") or [], warnings=[])
        self._access_state.access_names = present.access_names(self._access_state)
        self._lists: list[dict] | None = None
        self._memo: dict = {}

    def radius(self, section: str) -> int:
        """The radius nearby.json was made with (_meta.<parking|bus|rail>.radius_m)."""
        return int((self.nearby_meta.get(section) or {}).get("radius_m") or NEARBY_RADIUS[section])

    def access(self, p: dict) -> dict:
        """The place page's '근처 주차·버스·도시철도' rows of a place (cached): {lots: [{row (present.lot_row), m, paid}],
        stops: [{name, m, routes}], rails: [{name, official, lines, exit, m}]}. Empty when the place has no
        coordinates or no entry, or the entry was measured from other coordinates (measured_from more than 1 m away —
        pipeline.validate warns that nearby.json must be made again). A lot missing from parking_lots.json or taken
        off the nearby lists (nearby: false) is skipped like the page does. paid: True '유료' / False '무료' / None
        ('혼합', blank, or the other source's value differs)."""
        key = ("access", p.get("id") or id(p))
        if key in self._memo:
            return self._memo[key]
        out: dict = {"lots": [], "stops": [], "rails": []}
        entry = self.nearby.get(p.get("id"))
        src = (entry or {}).get("measured_from") or {}
        moved = (src.get("lat") is not None and src.get("lng") is not None and _geo(p)
                 and round(present.hav(src, p.get("geo"))) > 1)   # whole metres, as pipeline.validate rounds
        if entry and _geo(p) and not moved:
            for x in entry.get("parking") or []:
                lot = self.parking_lots.get(x.get("lot_id"))
                if lot is None or lot.get("nearby") is False or not isinstance(x.get("meters"), int):
                    continue
                paid, alt = _text(lot.get("paid")), _text(((lot.get("alt") or {}).get("paid") or {}).get("value"))
                state = None if alt and alt != paid else {"유료": True, "무료": False}.get(paid)
                out["lots"].append({"lot": lot, "m": x["meters"], "paid": state,
                                    "row": present.lot_row(self._access_state, lot, x["meters"], p.get("id") or "")})
            for s in entry.get("bus") or []:
                if isinstance(s.get("meters"), int) and _text(s.get("stop_name")):
                    out["stops"].append({"name": _text(s["stop_name"]), "m": s["meters"],
                                         "routes": [_text(r) for r in s.get("routes") or [] if _text(r)]})
            for r in entry.get("rail") or []:
                if isinstance(r.get("meters"), int) and _text(r.get("station")):
                    row = present.rail_row(r)
                    out["rails"].append({"name": row["name"], "official": _text(r.get("official_name")),
                                         "lines": row["lines"], "exit": row["exit"], "m": row["m"]})
        self._memo[key] = out
        return out

    def designations(self, p: dict) -> list[dict]:
        """The designations the place page shows (schema.designations), each with `list`: its list key (row_ref)."""
        key = ("designations", p.get("id") or id(p))
        if key not in self._memo:
            self._memo[key] = [{**d, "list": _text((d.get("match") or {}).get("row_ref")).split("#")[0]}
                               for d in shown_designations(p, city=self.city)]
        return self._memo[key]

    def courses_of(self, p: dict) -> list[dict]:
        """The shown courses that link the place as a stop."""
        return self.stop_courses.get(p.get("slug") or "", [])

    def designation_lists(self) -> list[dict]:
        """The official designation lists (data/raw/<도시>/designations/sources.json next to this data folder), each
        with its rows recounted from its CSV: rows (after the list's `rows` filter), kinds (rows per kind when the list
        sorts rows by a column), file_rows (every row of the file, when a filter applies), and the list's key, use,
        type, label, source_name, url and base_date (기준일). A missing CSV leaves rows None (nothing grounded)."""
        if self._lists is None:
            root = self.path.parent / "raw" / self.path.name / "designations"
            manifest = load_json(root / "sources.json", {}) or {}
            self._lists = [{**{k: src.get(k) for k in ("key", "use", "type", "label", "source_name", "url", "base_date")},
                            **list_rows(root / _text(src.get("file")), src)}
                           for src in manifest.get("lists") or [] if isinstance(src, dict) and src.get("file")]
        return self._lists

    def cited_lists(self, sources: list[dict]) -> list[dict]:
        """The designation lists a guide's sources cite: a source whose url is the list's url, or whose name is the
        list's source_name (institution, dataset and 기준일 — two lists of one file share its url, both are cited).
        The screen label ('안심식당') is not a citation: a source of that name with another url is another list."""
        urls = {_text(s.get("url")) for s in sources} - {""}
        names = {_text(s.get("name")) for s in sources} - {""}
        return [x for x in self.designation_lists()
                if _text(x.get("url")) in urls or (_text(x.get("source_name")) and _text(x.get("source_name")) in names)]

    def derived(self, p: dict) -> dict:
        """Computed values of a place (cached): address parts, closed days, first opening / last closing time."""
        key = p.get("id") or id(p)
        if key not in self._memo:
            f = p.get("facts") or {}
            a = self.city.parse_address(f.get("address"))
            text, contested = present.closed_text(p)
            wc = present.week_closure(text)
            opens, closes = hours_span(f.get("usetime") or f.get("usetime_restdate"))
            self._memo[key] = {
                "district": a.district, "area": a.area, "road": a.road, "closed_text": text, "contested": contested,
                "days": "".join(d for d in present.WEEK if d in wc["days"]),
                "partial": "".join(d for d in present.WEEK if d in wc["partial"]),
                "open_all_year": bool(wc["open"]) and not contested,
                "monday_open": bool(text) and not contested and present.monday_open(text),
                "opens": opens, "closes": closes,
                "photo": any(i.get("license") in present.LIC and i.get("source") == "TourAPI" for i in p.get("images") or []),
            }
        return self._memo[key]


def list_rows(path: Path, src: dict) -> dict:
    """{rows, kinds, file_rows} of one designation list's CSV, read like tools/import_designations_*: a row is kept
    when every `rows` filter column holds one of its values; `kinds` {col, food: [...], stay: [...], shop: [...]}
    sorts kept rows (other values -> 'other'). Blank rows are not rows."""
    if not path.is_file():
        return {"rows": None, "kinds": {}, "file_rows": None}
    flt = {c: {_text(v) for v in _list(vals)} for c, vals in (src.get("rows") or {}).items()}
    sort = src.get("kinds") if isinstance(src.get("kinds"), dict) else {}
    total = kept = 0
    kinds: dict[str, int] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not any(_text(v) for v in r.values() if isinstance(v, str)):
                continue
            total += 1
            if any(_text(r.get(c)) not in vals for c, vals in flt.items()):
                continue
            kept += 1
            if sort:
                v = _text(r.get(sort.get("col")))
                k = next((k for k in ("food", "stay", "shop") if v in {_text(x) for x in sort.get(k) or []}), "other")
                kinds[k] = kinds.get(k, 0) + 1
    return {"rows": kept, "kinds": kinds, "file_rows": total if flt else None}


# ------------------------------------------------------------------ hours
def _minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def hours_span(raw) -> tuple[int | None, int | None]:
    """(first opening, last closing) in minutes of the day from the primary time ranges of an hours value. A range
    after a 준비시간 / 브레이크 / 마지막 주문 word, or inside a bracket holding one, is not primary. A closing time not
    after its opening ('17:00~01:00', '10:00~익일 01:30', '~24:00') is the next day (+24h). (None, None) when no
    primary range is read — '상시 영업' or '점포별 상이' are left to a `fact` condition."""
    opens: list[int] = []
    closes: list[int] = []
    for line in present.clean_lines(raw):
        line = re.sub(r"익일\s*", "", line)
        prev = 0
        for m in present.RANGE_FIND.finditer(line):
            before = line[:m.start()]
            depth = before.count("(") - before.count(")")
            if depth > 0:
                start = before.rfind("(")
                end = line.find(")", m.end())
                secondary = present.SECONDARY.search(line[start:end if end >= 0 else len(line)])
            else:
                secondary = present.SECONDARY.search(line[prev:m.start()])
            prev = m.end()
            if secondary:
                continue
            a, b = _minutes(m.group(1)), _minutes(m.group(2))
            if b <= a:
                b += 24 * 60
            opens.append(a)
            closes.append(b)
    return (min(opens) if opens else None), (max(closes) if closes else None)


def hhmm(minutes: int | None) -> str:
    if minutes is None:
        return ""
    m = minutes % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


# ------------------------------------------------------------------ count conditions
def _strings(v) -> list[str] | None:
    """A non-empty string or list of non-empty strings as a list; None otherwise."""
    vals = v if isinstance(v, list) else [v]
    return [_text(x) for x in vals] if vals and all(isinstance(x, str) and _text(x) for x in vals) else None


def _station(name: str) -> str:
    return re.sub(r"역$", "", _text(name))


def value_problems(D: Data, k: str, v, path: str) -> list[str]:
    """Values of the new keys the data does not hold (a typo would silently count 0, a radius beyond what
    nearby.json was made with would undercount, a draft course is not counted): course refs, designation types and
    lists, route / line / station names, *_within radii."""
    out = []
    if k in WITHIN and v > D.radius(WITHIN[k]):
        out.append(f"{path}.{k}: {v}m는 nearby.json 반경 {D.radius(WITHIN[k])}m 밖 — 그 밖의 행은 데이터에 없다")
    if k == "course" and v is not True:
        for x in _strings(v) or []:
            if x not in D.course_by_ref and x not in D.course_groups:
                out.append(f"{path}.course: {'공개되지 않은 코스' if x in D.hidden_courses else 'courses.json에 없는 코스·group'}: {x}")
    if k == "designation" and v is not True:
        known = {_text(x.get("type")) for x in D.designation_lists()} | {
            _text(d.get("type")) for p in D.places for d in p.get("designations") or [] if isinstance(d, dict)}
        out += [f"{path}.designation: 모르는 지정 유형 {x!r}" for x in _strings(v) or [] if x not in known]
    if k == "designation_source":
        known = {_text(x.get("key")) for x in D.designation_lists()} | {
            _text((d.get("match") or {}).get("row_ref")).split("#")[0]
            for p in D.places for d in p.get("designations") or [] if isinstance(d, dict)}
        out += [f"{path}.designation_source: 모르는 지정 목록 {x!r}" for x in _strings(v) or [] if x not in known]
    if k in ("bus_route", "rail_line", "rail_station"):
        rows = [r for e in D.nearby.values() for r in e.get("bus" if k == "bus_route" else "rail") or []]
        known = ({_text(x) for r in rows for x in r.get("routes") or []} if k == "bus_route" else
                 {_text(x) for r in rows for x in r.get("lines") or []} if k == "rail_line" else
                 {_station(r.get(f)) for r in rows for f in ("station", "official_name") if _text(r.get(f))})
        word = {"bus_route": "버스 노선", "rail_line": "도시철도 노선", "rail_station": "역"}[k]
        out += [f"{path}.{k}: nearby.json에 없는 {word} {x!r}" for x in _strings(v) or []
                if (_station(x) if k == "rail_station" else x) not in known]
    return out


def condition_problems(where, path: str = "where", D: Data | None = None) -> list[str]:
    """Unknown keys or malformed values of a condition (so a typo never matches everything); with D, also values
    the data does not hold (value_problems)."""
    if not isinstance(where, dict) or not where:
        return [f"{path}: 조건은 비어 있지 않은 객체"]
    out = []
    for k, v in where.items():
        if k not in COUNT_KEYS:
            out.append(f"{path}: 모르는 조건 '{k}' (쓸 수 있는 것: {', '.join(COUNT_KEYS)})")
        elif k in WITHIN and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            out.append(f"{path}.{k}: 미터(양수)")
        elif k == "lot_paid" and not isinstance(v, bool):
            out.append(f"{path}.lot_paid: true 또는 false")
        elif k in TEXT_KEYS and _strings(v) is None:
            out.append(f"{path}.{k}: 문자열 하나 또는 문자열 목록")
        elif k in ("designation", "course") and v is not True and _strings(v) is None:
            out.append(f"{path}.{k}: 문자열 하나·문자열 목록 또는 true")
        elif k in WITHIN or k in TEXT_KEYS or k in ("designation", "course"):
            out += value_problems(D, k, v, path) if D is not None else []
        elif k in ("fact", "not_fact"):
            if not isinstance(v, dict) or not v:
                out.append(f"{path}.{k}: {{키: 정규식}}")
            else:
                for rx in v.values():
                    try:
                        re.compile(str(rx))
                    except re.error as exc:
                        out.append(f"{path}.{k}: 정규식 오류 {rx!r} — {exc}")
        elif k in ("name", "not_name"):
            try:
                re.compile(str(v))
            except re.error as exc:
                out.append(f"{path}.{k}: 정규식 오류 {v!r} — {exc}")
        elif k in ("closes_after", "opens_before") and not HHMM.match(str(v)):
            out.append(f"{path}.{k}: 'HH:MM' 형식")
        elif k == "near" and not (isinstance(v, dict) and v.get("slug") and isinstance(v.get("m"), (int, float))):
            out.append(f"{path}.near: {{slug, m}}")
        elif k == "any":
            if not isinstance(v, list) or not v:
                out.append(f"{path}.any: 조건 목록")
            else:
                for i, sub in enumerate(v):
                    out += condition_problems(sub, f"{path}.any[{i}]", D)
        elif k == "not":
            out += condition_problems(v, f"{path}.not", D)
    return out


def _values(p: dict, keys: str) -> list[str]:
    f = p.get("facts") or {}
    return [_text(f.get(k)) for k in keys.split("|")]


def matches(D: Data, p: dict, where: dict) -> bool:
    """One place against a condition (all keys AND). Callers check condition_problems first."""
    d = D.derived(p)
    for k, v in where.items():
        if k == "kind" and p.get("kind") not in _list(v):
            return False
        if k == "category" and p.get("category") not in _list(v):
            return False
        if k == "lcls" and not str((p.get("tourapi") or {}).get("lcls") or "").startswith(tuple(_list(v))):
            return False
        if k in ("district", "area") and d[k] not in _list(v):
            return False
        if k == "name" and not re.search(str(v), p.get("name") or ""):
            return False
        if k == "not_name" and re.search(str(v), p.get("name") or ""):
            return False
        if k == "fact" and not all(any(re.search(str(rx), x) for x in _values(p, keys) if x) for keys, rx in v.items()):
            return False
        if k == "not_fact" and any(re.search(str(rx), x) for keys, rx in v.items() for x in _values(p, keys) if x):
            return False
        if k == "has" and not all(_text((p.get("facts") or {}).get(x)) for x in _list(v)):
            return False
        if k == "lacks" and any(_text((p.get("facts") or {}).get(x)) for x in _list(v)):
            return False
        if k == "monday_open" and d["monday_open"] != bool(v):
            return False
        if k == "closed_on" and (d["contested"] or not set(str(v)) <= set(d["days"])):
            return False
        if k == "closed_partly_on" and (d["contested"] or not set(str(v)) <= set(d["partial"])):
            return False
        if k == "weekly_closed" and (bool(d["days"] or d["partial"]) != bool(v) or d["contested"]):
            return False
        if k == "open_all_year" and d["open_all_year"] != bool(v):
            return False
        if k == "closes_after" and (d["closes"] is None or d["closes"] < _minutes(str(v))):
            return False
        if k == "opens_before" and (d["opens"] is None or d["opens"] > _minutes(str(v))):
            return False
        if k == "near":
            anchor = D.by_slug.get(v["slug"])
            meters = present.hav((anchor or {}).get("geo"), p.get("geo")) if anchor and _geo(p) and _geo(anchor) else None
            if p is anchor or meters is None or meters > float(v["m"]):
                return False
        if k == "slugs" and p.get("slug") not in _list(v):
            return False
        if k == "summary" and bool(_text(p.get("summary"))) != bool(v):
            return False
        if k == "photo" and d["photo"] != bool(v):
            return False
        if k == "geo" and bool(_geo(p)) != bool(v):
            return False
        if k == "course" and not any(v is True or {_text(c.get("id")), _text(c.get("slug")), _text(c.get("group"))}
                                     & set(_list(v)) for c in D.courses_of(p)):
            return False
        if k == "any" and not any(matches(D, p, sub) for sub in v):
            return False
        if k == "not" and matches(D, p, v):
            return False
    return _family_match(D, p, where)


def _family_match(D: Data, p: dict, where: dict) -> bool:
    """The nearby and designation keys: the keys of one family must all hold for the same row (lot, stop, station or
    designation) of the place — lot_within 300 + lot_paid false is a free lot within 300 m, not some lot within 300 m
    and some free lot elsewhere."""
    fam = {k: where[k] for k in LOT_KEYS if k in where}
    if fam and not any(("lot_within" not in fam or x["m"] <= fam["lot_within"])
                       and ("lot_paid" not in fam or x["paid"] is fam["lot_paid"]) for x in D.access(p)["lots"]):
        return False
    fam = {k: where[k] for k in STOP_KEYS if k in where}
    if fam and not any(("stop_within" not in fam or s["m"] <= fam["stop_within"])
                       and ("bus_route" not in fam or set(s["routes"]) & set(_strings(fam["bus_route"])))
                       for s in D.access(p)["stops"]):
        return False
    fam = {k: where[k] for k in RAIL_KEYS if k in where}
    if fam and not any(("rail_within" not in fam or r["m"] <= fam["rail_within"])
                       and ("rail_line" not in fam or set(r["lines"]) & set(_strings(fam["rail_line"])))
                       and ("rail_station" not in fam
                            or {_station(r["name"]), _station(r["official"])} & {_station(x) for x in _strings(fam["rail_station"])})
                       for r in D.access(p)["rails"]):
        return False
    fam = {k: where[k] for k in DESIGNATION_KEYS if k in where}
    if fam and not any(("designation" not in fam or fam["designation"] is True
                        or _text(d.get("type")) in _strings(fam["designation"]))
                       and ("designation_source" not in fam or d["list"] in _strings(fam["designation_source"]))
                       for d in D.designations(p)):
        return False
    return True


def _geo(p: dict) -> bool:
    g = p.get("geo") or {}
    return g.get("lat") is not None and g.get("lng") is not None


def select(D: Data, where: dict) -> list[dict]:
    """The shown places a condition matches, in data order. Raises ValueError on a malformed condition."""
    problems = condition_problems(where, D=D)
    if problems:
        raise ValueError("; ".join(problems))
    return [p for p in D.places if matches(D, p, where)]


def threshold_times(where: dict) -> set[str]:
    """The clock times a count's definition states ('24:00' also reads '00:00')."""
    out: set[str] = set()
    for k, v in (where or {}).items():
        if k in ("closes_after", "opens_before") and HHMM.match(str(v)):
            h, m = str(v).split(":")
            out |= {f"{int(h):02d}:{m}", f"{int(h) % 24:02d}:{m}"}
        elif k == "any" and isinstance(v, list):
            for sub in v:
                out |= threshold_times(sub if isinstance(sub, dict) else {})
        elif k == "not" and isinstance(v, dict):
            out |= threshold_times(v)
    return out


def threshold_numbers(where: dict) -> set[str]:
    """Numbers a count's definition states (a time or a radius), allowed in the text that names the count."""
    out: set[str] = set()
    for k, v in (where or {}).items():
        if k in ("closes_after", "opens_before"):
            h, m = str(v).split(":")
            out |= {str(int(h)), str(int(m)), str(int(h) % 24)}
        elif k == "near" and isinstance(v, dict) and isinstance(v.get("m"), (int, float)):
            out |= _distance_forms(float(v["m"]))
        elif k in WITHIN and isinstance(v, (int, float)) and not isinstance(v, bool):
            out |= _distance_forms(float(v))
        elif k in ("bus_route", "rail_line", "rail_station"):
            out |= set().union(*(_nums(x) for x in _strings(v) or []))
        elif k == "any" and isinstance(v, list):
            for sub in v:
                out |= threshold_numbers(sub if isinstance(sub, dict) else {})
        elif k == "not" and isinstance(v, dict):
            out |= threshold_numbers(v)
    return out


# ------------------------------------------------------------------ catalog
def place_row(D: Data, p: dict, with_text: bool = False) -> dict:
    f = p.get("facts") or {}
    d = D.derived(p)
    base = _text((p.get("facts_source") or {}).get("provider"))
    providers = {k: _text(s.get("provider")) for k, s in (p.get("fact_sources") or {}).items()
                 if isinstance(s, dict) and _text(s.get("provider")) and _text(s.get("provider")) != base}
    differs = {k: [{"value": _text(a.get("value")), "provider": _text(a.get("provider"))} for a in alts]
               for k, alts in (p.get("fact_alternatives") or {}).items() if alts}
    tour = p.get("tourapi") or {}
    geo = p.get("geo") or {}
    row = {
        "id": p.get("id"), "slug": p.get("slug"), "name": p.get("name"), "kind": p.get("kind"),
        "category": p.get("category", ""), "lcls": _text(tour.get("lcls")),
        "district": d["district"], "area": d["area"], "road": d["road"],
        "facts": {k: _text(v) for k, v in f.items() if _text(v)}, "provider": base,
        "closed": {"text": d["closed_text"], "contested": d["contested"], "days": d["days"], "partial": d["partial"],
                   "open_all_year": d["open_all_year"], "monday_open": d["monday_open"]},
        "hours": {"opens": hhmm(d["opens"]), "closes": hhmm(d["closes"]),
                  "next_day": d["closes"] is not None and d["closes"] > 24 * 60},
        "geo": [geo["lat"], geo["lng"]] if _geo(p) else None, "photo": d["photo"],
        "summary": _text(p.get("summary")), "status": p.get("status", ""),
    }
    if p.get("alternate_names"):
        row["alternate_names"] = list(p["alternate_names"])
    if _text(tour.get("title")) and _text(tour.get("title")) != p.get("name"):
        row["tourapi_title"] = _text(tour.get("title"))
    if providers:
        row["providers"] = providers
    if differs:
        row["differs"] = differs
    a = D.access(p)
    if a["lots"] or a["stops"] or a["rails"]:
        row["nearby"] = {
            "lots": [{"name": x["row"]["name"], "m": x["m"], "type": x["row"]["type"], "spaces": x["row"]["spaces"],
                      "paid": x["row"]["paid"], "paid_state": x["paid"], "hours": x["row"]["hours"],
                      "fees": [f["text"] for f in x["row"]["fees"] if f["text"]], "contact": x["row"]["contact"],
                      "differs": x["row"]["differ"]} for x in a["lots"]],
            "stops": [{"name": s["name"], "m": s["m"], "routes": s["routes"]} for s in a["stops"]],
            "rails": [{"name": r["name"], "lines": r["lines"], "exit": r["exit"], "m": r["m"]} for r in a["rails"]]}
    ds = D.designations(p)
    if ds:
        row["designations"] = [{"type": d.get("type"), "label": d.get("label"), "year": d.get("year"), "list": d["list"]}
                               for d in ds]
    if D.courses_of(p):
        row["courses"] = [c.get("slug") for c in D.courses_of(p)]
    if with_text:
        row["source_text"] = squash_ws(tour.get("overview"))[:TEXT_MAX]
    return row


def catalog(data: Path, out: Path, with_text: bool = False, kinds: list[str] | None = None) -> dict:
    D = Data(data)
    rows = [place_row(D, p, with_text) for p in D.places if not kinds or p.get("kind") in kinds]
    doc = {
        "rules": rules(D.city),
        "count_keys": COUNT_KEYS,
        "places": rows,
        "events": [{k: e.get(k) for k in ("id", "name", "start_date", "end_date", "period_text", "place_name",
                                          "address", "fee", "place_slug") if e.get(k)} for e in D.events],
        "guides": [{"id": g.get("id"), "slug": g.get("slug"), "title": g.get("title"), "label": g.get("label"),
                    "items": [i.get("place_slug") for i in g.get("items") or []],
                    "faq": [f.get("q") for f in g.get("faq") or []]} for g in D.guides],
        "courses": [{"id": c.get("id"), "slug": c.get("slug"), "name": c.get("name"), "group": c.get("group"),
                     "duration": c.get("duration"),
                     "facts": [{"label": f.get("label"), "value": f.get("value")} for f in c.get("facts") or []
                               if isinstance(f, dict)],
                     "stops": [{"name": s.get("name"), "place_slug": s.get("place_slug") or ""}
                               for s in c.get("stops") or [] if isinstance(s, dict)]} for c in D.courses],
        "nearby_radius": {k: D.radius(k) for k in NEARBY_RADIUS},
        "designation_lists": D.designation_lists(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"places": len(rows), "events": len(D.events), "guides": len(D.guides), "courses": len(D.courses),
            "out": str(out)}


def rules(city) -> list[str]:
    """What a guide writer reads first (CLAUDE.md 3절 1·2·5·6·10, 4절)."""
    return [
        "가이드는 실제 여행자 질문 하나에 답한다. title은 그 질문('…?'), summary 첫 문장이 답이다. 답은 데이터에서 센 숫자로 쓴다.",
        "사실은 places.json·events.json의 값(이 목록의 facts·closed·hours, TourAPI 소개문)에서만 가져온다. 추정·일반 지식·"
        "제3자 리뷰·평점·블로그 내용을 쓰지 않고, 근거 없이 업체를 추천하지 않는다.",
        "숫자는 모두 참조한 장소의 값이거나 counts로 선언해 검사기가 다시 센 개수다. 'N곳'은 counts의 n이나 items 개수여야 "
        "한다. 목록 개수를 주장하면 counts에 items: true를 붙이고 그 조건의 장소를 모두 싣는다.",
        f"TourAPI 소개문은 사실 확인용이다. {pc.COPY_LIMIT}자 이상 옮기면 막힌다. 장소 이름과 사실 값 말고는 우리 문장으로 쓴다.",
        "출처 해설체('원문은…', '~라고 합니다'), '확인 필요'·'자료에 없음' 문구, 수식어(인기·유명한·아름다운·최고·다양한·"
        "즐길 수 있는·추천·가볼 만한·맛있는 등)를 쓰지 않는다. 평서문 '~입니다/~습니다'로 쓴다.",
        "출처마다 값이 다르면(differs) 둘 다 적고 '방문 전 전화 확인'을 붙인다. 한쪽을 고르지 않는다.",
        f"items 사유를 '○○은 {city.admin_line} ○○에 있는 ○○입니다'로만 쓰지 않는다. 그 장소의 값(메뉴·시간·쉬는 날·요금·주차)을 쓴다.",
        "FAQ는 데이터로 답할 수 있는 질문만, 존댓말 '~나요?/~인가요?'로. 다른 가이드·장소 FAQ와 같은 질문은 쓰지 않는다.",
        "slug는 pipeline.slugs.slugify로 만든 ASCII 값을 저장한다. status는 'draft', reviewed_at·approved_at은 비운다(사람이 정한다).",
        "근처 주차장·정류장·역(nearby)은 장소 좌표에서 잰 직선거리의 공공데이터 값이다. '근처 공영주차장'·'직선 n m'로 쓰고 "
        "장소 자체의 주차·걷는 시간으로 쓰지 않는다. 지정(designations)은 목록 이름과 함께, 코스 값은 courses에 그 코스를 적고 쓴다. "
        "지정 목록의 행 수는 그 목록을 sources에 적었을 때만 쓴다.",
    ]


# ------------------------------------------------------------------ check
def _nums(text: str | None) -> set[str]:
    out = set()
    for m in NUM_RX.finditer(text or ""):
        v = m.group(0).replace(",", "")
        if "." in v:
            a, b = v.split(".", 1)
            out.add(f"{int(a)}.{b}")
        else:
            out.add(str(int(v)))
    return out


def _times(text: str | None) -> set[str]:
    return {f"{int(h):02d}:{m}" for h, m in CLOCK_RX.findall(text or "")}


def _phones(text: str | None) -> set[str]:
    return set(present.PHONE.findall(text or ""))


def _distance_forms(meters: float) -> set[str]:
    km = meters / 1000
    forms = {str(int(round(meters))), str(int(round(meters / 10) * 10)), str(int(round(meters / 100) * 100)),
             f"{km:.1f}", f"{km:.2f}".rstrip("0").rstrip(".")}
    if meters >= 1000:
        forms.add(str(int(round(km))))
    if f"{km:.1f}".endswith(".0"):
        forms.add(f"{km:.1f}"[:-2])
    return set().union(*(_nums(x) for x in forms))


def _go_numbers(text: str) -> set[str]:
    """The numbers of 'N곳' claims (digits or 한·두·세… 곳)."""
    out = {m.group(1).replace(",", "").lstrip("0") or "0" for m in GO_RX.finditer(text or "")}
    out |= {str(KNUM[m.group(1)]) for m in KGO_RX.finditer(text or "")}
    return out


def course_names(c: dict) -> list[str]:
    """Names a guide may call a course by: its name, without a bracket, and without its group word in front."""
    name, group = _text(c.get("name")), _text(c.get("group"))
    out = [name, squash_ws(re.sub(r"\(.*?\)", " ", name))]
    if group and name.startswith(group) and len(name) > len(group):
        out.append(name[len(group):].strip(" -·:"))
    return [n for n in dict.fromkeys(out) if len(n) >= 2]


def course_texts(c: dict) -> list[str]:
    """What a course page states: name, group, duration, every facts row (label, value, short) and the stop names."""
    out = [_text(c.get(k)) for k in ("name", "group", "duration")]
    for f in c.get("facts") or []:
        if isinstance(f, dict):
            out += [_text(f.get(k)) for k in ("label", "value", "short")]
    out += [_text((s if isinstance(s, dict) else {}).get("name")) for s in c.get("stops") or []]
    return [t for t in out if t]


def _fee_numbers(lot: dict) -> set[str]:
    """The minutes and amounts of a lot's fee versions as stored (basic / extra / day, or an ordinance tier) — the
    page prints them through present.fee_text ('기본 1시간 1,000원'), a guide may also write 60분. month is not shown."""
    out: set[str] = set()
    for v in (lot.get("fee") or {}).get("versions") or []:
        for part in ("basic", "extra", "day"):
            out |= {str(x) for x in ((v.get(part) or {}).get(k) for k in ("minutes", "won")) if isinstance(x, int)}
        out |= {str(x) for size in ("small", "large") for x in (v.get(size) or {}).values() if isinstance(x, int)}
        if isinstance(v.get("free_minutes"), int):
            out.add(str(v["free_minutes"]))
    return out


def _bucket(texts: list[str], numbers: set[str] = frozenset(), go: set[str] = frozenset(),
            go_texts: list[str] = (), metres: list[int] = ()) -> dict:
    """The numbers, 'N곳' numbers, whole clock times, phones and distance forms that a set of source texts grounds."""
    texts = [t for t in texts if t]
    return {"numbers": set(numbers) | {str(m) for m in metres} | set().union(*(_nums(t) for t in texts)),
            "go": set(go) | set().union(*(_go_numbers(t) for t in go_texts)),
            "times": set().union(*(_times(t) for t in texts)),
            "phones": set().union(*(_phones(t) for t in texts)),
            "dists": set().union(*(_distance_forms(float(m)) for m in metres))}


def _hhmm(v: str) -> str:
    v = _text(v)
    return f"{v[:2]}:{v[2:4]}" if len(v) == 4 and v.isdigit() else ""


def _span(a: str, b: str) -> int | None:
    """Minutes from HHMM a to HHMM b (past midnight when b is earlier)."""
    try:
        m = (int(b[:2]) * 60 + int(b[2:])) - (int(a[:2]) * 60 + int(a[2:]))
    except (ValueError, TypeError):
        return None
    return m + 1440 if m < 0 else m


def transit_grounding(D: Data, sources: list[dict], places: list[dict]) -> dict:
    """What a guide may cite from data/<city>/transit.json (the city's transit import tool), only for the blocks whose
    source url the guide's sources name: a timetable's date, the number of trains or buses and of distinct departure
    times (all, per grade, per grade family — 'KTX' and its variants), every departure and arrival time, fare, train
    number and journey time (minutes, hours and minutes); a city bus route's number, ends, notes and direction notes and,
    from each boarding stop of the block, the number of stops to every later stop that is a boarding stop or a stop near
    a referenced place (D.access), and from each of those stops back to a later boarding stop. {numbers, times, names}."""
    T = load_json(D.path / "transit.json", {}) or {}
    urls = {_text(s.get("url")) for s in sources} - {""}
    numbers: set[str] = set()
    times: set[str] = set()
    names: list[str] = []
    for kind, rows_key in (("rail", "trains"), ("expbus", "buses")):
        blk = T.get(kind) or {}
        if _text((blk.get("source") or {}).get("url")) not in urls:
            continue
        for run in blk.get("runs") or []:
            rows = run.get(rows_key) or []
            date = _text(run.get("date"))
            if len(date) == 8:
                numbers |= {str(int(date[:4])), str(int(date[4:6])), str(int(date[6:]))}
            names += [_text(run.get("from")), _text(run.get("to"))]
            groups: dict[str, list] = {"": rows}
            for r in rows:
                g = _text(r.get("grade"))
                groups.setdefault(g, []).append(r)
                groups.setdefault(g.split("-")[0].split("(")[0], []).append(r)
            for grp in groups.values():
                numbers |= {str(len(grp)), str(len({r.get("dep") for r in grp}))}
            for r in rows:
                for t in (r.get("dep"), r.get("arr")):
                    if _hhmm(t):   # the whole time, and its digits as the number check reads them
                        times.add(_hhmm(t))
                        numbers |= _nums(_hhmm(t))
                if r.get("fare"):
                    numbers.add(str(int(r["fare"])))
                if _text(r.get("no")).isdigit():
                    numbers.add(str(int(r["no"])))
                m = _span(_text(r.get("dep")), _text(r.get("arr")))
                if m is not None:
                    numbers |= {str(m), str(m // 60), str(m % 60)}
                names += [_text(r.get("grade")), _text(r.get("dep_terminal")), _text(r.get("arr_terminal"))]
    blk = T.get("bus") or {}
    if _text((blk.get("source") or {}).get("url")) in urls:
        board = set(blk.get("stops") or [])
        targets = {s["name"] for p in places for s in D.access(p)["stops"]} | board
        names += sorted(board)
        for r in (blk.get("routes") or {}).values():
            numbers |= _nums(r.get("routeNo"))
            names += [_text(r.get("routeNo")), _text(r.get("start")), _text(r.get("end")), _text(r.get("note")),
                      *(_text(v) for v in (r.get("dir_note") or {}).values())]
            for seq in (r.get("stops") or {}).values():
                for i, a in enumerate(seq):
                    if a[2] not in targets:
                        continue
                    ends = targets if a[2] in board else board   # going out from a boarding stop, or coming back
                    for j in range(i + 1, len(seq)):
                        if seq[j][2] in ends:
                            numbers.add(str(j - i))
                            names += [a[2], seq[j][2]]
    return {"numbers": numbers, "times": times, "names": [n for n in dict.fromkeys(names) if n]}


def grounding(D: Data, places: list[dict], courses: list[dict], lists: list[dict]) -> dict:
    """Numbers, 'N곳' numbers, clock times, phones, distance forms and proper names a guide may use beyond the places'
    facts: for each referenced place its shown designations (label, year, list name); for each referenced course its
    name, group, duration, facts and stops (and the number of stops, also as 'N곳'); for each cited designation list
    its label, list name, 기준일 and its recounted rows (also as 'N곳'). `access` holds, apart, what the referenced
    places' nearby rows print (present.lot_row: lot name, type, address, spaces, 무료/유료, hours, every fee version,
    the desk and phones, the other source's values; stop names, route numbers; station names as shown, lines, exit;
    the straight-line metres of each row, rounded forms with a unit) and the rows' names: check_guide lets them ground
    only a text that is about getting there (ACCESS_CUE or a row's name) — a referenced place has up to six rows, so
    used everywhere they would ground most small numbers of any guide. names: every proper name for the wording check."""
    near, near_names, near_numbers, metres = [], [], set(), []
    for p in places:
        a = D.access(p)
        for x in a["lots"]:
            r = x["row"]
            near += [r["name"], r["alt_name"], r["type"], r["alt_type"], r["addr"], r["jibun"], r["paid"], r["alt_paid"],
                     r["hours"], r["alt_hours"], r["contact"], _text(r["spaces"]), _text(r["alt_spaces"])]
            near += [f["text"] for f in r["fees"]]
            near_numbers |= _fee_numbers(x["lot"])
            near_names += [r["name"], r["alt_name"]]
            metres.append(x["m"])
        for s in a["stops"]:
            near += [s["name"], *s["routes"]]
            near_names.append(s["name"])
            metres.append(s["m"])
        for r in a["rails"]:   # the station as the page prints it ('…역'), not the list's official name
            near += [r["name"], *r["lines"], r["exit"]]
            near_names.append(r["name"])
            metres.append(r["m"])
    texts, names, go_texts = [], [], []
    numbers: set[str] = set()
    go: set[str] = set()
    for p in places:
        for d in D.designations(p):
            texts += [_text(d.get("label")), _text(d.get("short")), _text(d.get("year")), _text(d.get("source_name"))]
            names += [_text(d.get("label")), _text(d.get("short"))]
    for c in courses:
        t = course_texts(c)
        texts += t
        go_texts += t
        names += course_names(c) + [_text(c.get("group"))]
        names += [_text((s if isinstance(s, dict) else {}).get("name")) for s in c.get("stops") or []]
        numbers.add(str(len(c.get("stops") or [])))
        go.add(str(len(c.get("stops") or [])))
    for x in lists:
        texts += [_text(x.get("label")), _text(x.get("source_name")), _text(x.get("base_date"))]
        names += [_text(x.get("label"))]
        sizes = {str(n) for n in [x.get("rows"), x.get("file_rows"), *(x.get("kinds") or {}).values()] if isinstance(n, int)}
        numbers |= sizes
        go |= sizes
    near_names = [n for n in dict.fromkeys(_text(x) for x in near_names) if len(n) >= 2]
    return {**_bucket(texts, numbers, go, go_texts),
            "access": {**_bucket(near, near_numbers, metres=metres), "names": near_names},
            "names": [n for n in dict.fromkeys(names + near_names) if len(n) >= 2]}


def guide_texts(g: dict) -> list[tuple[str, str]]:
    """(where, text) of everything a guide prints."""
    out = [("title", _text(g.get("title"))), ("label", _text(g.get("label"))), ("summary", _text(g.get("summary")))]
    for i, b in enumerate(g.get("body") or []):
        b = b if isinstance(b, dict) else {}
        out += [(f"body[{i}].heading", _text(b.get("heading"))), (f"body[{i}].text", _text(b.get("text")))]
    for i, it in enumerate(g.get("items") or []):
        out.append((f"items[{i}].reason", _text((it if isinstance(it, dict) else {}).get("reason"))))
    for i, f in enumerate(g.get("faq") or []):
        f = f if isinstance(f, dict) else {}
        out += [(f"faq[{i}].q", _text(f.get("q"))), (f"faq[{i}].a", _text(f.get("a")))]
    for field in ("answer", "answer_short", "hub_short"):
        a = g.get(field)
        if isinstance(a, dict):
            out += [(f"{field}.{k}", _text(v)) for k, v in a.items() if isinstance(v, str) and _text(v)]
    return [(w, t) for w, t in out if t]


def _qkey(q: str) -> str:
    return re.sub(r"[\s?？.!]", "", _text(q))


def check_guide(g: dict, D: Data, *, others: list[dict] | None = None) -> list[str]:
    """Problems of one guide against the data; [] when clean. others: the other guides whose slugs and FAQ
    questions this one must not repeat (default: guides.json without this id)."""
    issues: list[str] = []
    if not isinstance(g, dict):
        return ["가이드가 객체가 아님"]
    gid = _text(g.get("id"))
    others = [x for x in (D.guides if others is None else others) if isinstance(x, dict) and _text(x.get("id")) != gid]
    stored = next((x for x in D.guides if isinstance(x, dict) and _text(x.get("id")) == gid), None)

    # shape and the fields only a person sets
    for k in ("id", "title", "label", "summary"):
        if not _text(g.get(k)):
            issues.append(f"{k} 비어 있음")
    if _text(g.get("title")) and "?" not in _text(g.get("title")):
        issues.append("title은 질문형('…?')")
    slug = _text(g.get("slug"))
    if not slug:
        hint = slugify(_text(g.get("label")))
        issues.append(f"slug 없음 — pipeline.slugs.slugify로 만든 ASCII 값을 저장(예: label로 '{hint}')")
    elif not is_slug(slug):
        issues.append(f"slug 형식 오류: {slug!r} (a-z·0-9·하이픈, 60자 이하)")
    elif any(_text(x.get("slug")) == slug for x in others):
        issues.append(f"slug가 다른 가이드와 겹침: {slug}")
    for k in STATUS_FIELDS:
        now, before = _text(g.get(k)), _text((stored or {}).get(k))
        if stored is None and k == "status" and now != "draft":
            issues.append(f"새 가이드의 status는 'draft'(지금 {now!r}) — 공개는 사람이 정한다")
        elif stored is None and k != "status" and now:
            issues.append(f"새 가이드의 {k}는 비워 둔다 — 사람이 정한다")
        elif stored is not None and now != before:
            issues.append(f"{k}를 바꿈({before!r} → {now!r}) — 사람이 정한다")
    checked = _text(g.get("checked_at"))
    if checked:
        try:
            if dt.date.fromisoformat(checked) > dt.date.today():
                issues.append(f"checked_at이 미래: {checked}")
        except ValueError:
            issues.append(f"checked_at 날짜 형식 오류: {checked}")
    body = [b for b in g.get("body") or [] if isinstance(b, dict)]
    if len(body) < BODY_MIN:
        issues.append(f"body는 {BODY_MIN}절 이상(지금 {len(body)}절)")
    for i, b in enumerate(body):
        if not _text(b.get("heading")) or not _text(b.get("text")):
            issues.append(f"body[{i}] heading·text가 비어 있음")
    sources = [s for s in g.get("sources") or [] if isinstance(s, dict)]
    if not sources:
        issues.append("sources 없음({name, url})")
    for i, s in enumerate(sources):
        if not _text(s.get("name")) or not _text(s.get("url")).startswith(("http://", "https://")):
            issues.append(f"sources[{i}]는 name과 http(s) url")
    summary = _text(g.get("summary"))
    sentences = summary_sentences(summary)
    if len(sentences) > SUMMARY_MAX_SENTENCES:
        issues.append(f"summary는 1~{SUMMARY_MAX_SENTENCES}문장(지금 {len(sentences)}문장)")
    issues += [f"summary 문장이 '다.'로 끝나지 않음: '{s}'" for s in sentences if not s.endswith("다.")]

    # references
    items = [it if isinstance(it, dict) else {} for it in g.get("items") or []]
    refs: dict[str, dict] = {}

    def ref(slug_: str, where: str) -> None:
        if slug_ in D.by_slug:
            refs.setdefault(slug_, D.by_slug[slug_])
        elif slug_ in D.hidden:
            issues.append(f"{where} 중복·제외된 장소: {slug_}")
        else:
            issues.append(f"{where} places.json에 없는 장소: {slug_}")

    seen_items: set[str] = set()
    for i, it in enumerate(items):
        s = _text(it.get("place_slug"))
        if not s:
            issues.append(f"items[{i}] place_slug 없음")
            continue
        ref(s, f"items[{i}]")
        if s in seen_items:
            issues.append(f"items[{i}] 같은 장소가 두 번: {s}")
        seen_items.add(s)
        if not _text(it.get("reason")):
            issues.append(f"items[{i}] reason 비어 있음")
    for s in g.get("route_slugs") or []:
        ref(_text(s), "route_slugs")
    texts = guide_texts(g)
    joined = " ".join(t for _, t in texts)
    for s in g.get("mentions") or []:
        s = _text(s)
        ref(s, "mentions")
        p = D.by_slug.get(s)
        if p and not any(n in joined for n in pc.name_variants(p["name"], p.get("alternate_names")) or [p["name"]]):
            issues.append(f"mentions의 장소 이름이 글에 없음: {p['name']} ({s})")
    events = []
    for eid in g.get("event_ids") or []:
        e = D.event_by_id.get(_text(eid))
        if e is None:
            issues.append(f"event_ids events.json에 없는 행사: {eid}")
        else:
            events.append(e)
    courses: list[dict] = []
    for s in g.get("courses") or []:
        s = _text(s)
        c = D.course_by_ref.get(s)
        if c is None:
            issues.append(f"courses {'공개되지 않은 코스' if s in D.hidden_courses else 'courses.json에 없는 코스'}: {s}")
            continue
        if c not in courses:
            courses.append(c)
        if not any(n in joined for n in course_names(c)):
            issues.append(f"courses의 코스 이름이 글에 없음: {c.get('name')} ({c.get('slug')})")

    # counts
    item_slugs = [_text(it.get("place_slug")) for it in items if _text(it.get("place_slug"))]
    counted: set[str] = {str(len(items))} if items else set()
    thresholds: set[str] = set()
    clock: set[str] = set()
    for i, c in enumerate(g.get("counts") or []):
        c = c if isinstance(c, dict) else {}
        n = c.get("n")
        if not isinstance(n, int) or isinstance(n, bool):
            issues.append(f"counts[{i}].n은 정수")
            continue
        if not _text(c.get("what")):
            issues.append(f"counts[{i}].what(무엇을 센 것인지) 비어 있음")
        if "names" in c:
            names = [_text(x) for x in c.get("names") or [] if _text(x)]
            if len(set(names)) != n:
                issues.append(f"counts[{i}] names {len(set(names))}개인데 n={n}")
                continue
            missing = [x for x in names if x not in joined]
            if missing:
                issues.append(f"counts[{i}] names가 글에 없음: {', '.join(missing)}")
                continue
            counted.add(str(n))
            continue
        where = c.get("where")
        bad = condition_problems(where, f"counts[{i}].where", D)
        if bad:
            issues += bad
            continue
        for s in _list(where.get("slugs")) + ([where["near"]["slug"]] if isinstance(where.get("near"), dict) else []):
            if s not in D.by_slug:
                issues.append(f"counts[{i}].where places.json에 없는 장소: {s}")
        got = select(D, where)
        if len(got) != n:
            issues.append(f"counts[{i}] '{_text(c.get('what'))}': 다시 센 값 {len(got)}, 적은 값 {n}")
            continue
        if c.get("items"):
            want = {p["slug"] for p in got}
            extra, lack = sorted(set(item_slugs) - want), sorted(want - set(item_slugs))
            if extra or lack:
                issues.append(f"counts[{i}] items: true인데 items가 조건 결과와 다름 — 조건 밖 {extra}, 빠진 곳 {lack}")
                continue
        counted.add(str(n))
        thresholds |= threshold_numbers(where)
        clock |= threshold_times(where)

    # numbers
    names = [n for p in refs.values()
             for n in pc.name_variants(p["name"], p.get("alternate_names"), (p.get("tourapi") or {}).get("title", ""))]
    values = [_text(v) for p in refs.values() for v in (p.get("facts") or {}).values()]
    values += [_text(a.get("value")) for p in refs.values() for alts in (p.get("fact_alternatives") or {}).values()
               for a in alts or []]
    hay = names + values + [_text(p.get("category")) for p in refs.values()]
    hay += [" ".join((D.derived(p)["district"], D.derived(p)["area"], D.derived(p)["road"])) for p in refs.values()]
    overviews = [squash_ws((p.get("tourapi") or {}).get("overview")) for p in refs.values()]
    event_text = [_text(v) for e in events for v in e.values() if isinstance(v, (str, int, float))]
    known = set().union(*(_nums(x) for x in hay + overviews + event_text)) if hay or overviews or event_text else set()
    known |= counted | thresholds | {str(len(D.city.districts))}
    gos = set().union(*(_go_numbers(x) for x in values + overviews + event_text)) if values or overviews or event_text else set()
    sources_text = hay + overviews + event_text
    clock |= set().union(*(_times(x) for x in sources_text)) if sources_text else set()
    phones = set().union(*(_phones(x) for x in sources_text)) if sources_text else set()
    pts = [p.get("geo") for p in refs.values() if _geo(p)]
    dists: set[str] = set()
    for a_i, a in enumerate(pts):
        for b in pts[a_i + 1:]:
            dists |= _distance_forms(present.hav(a, b))
    # official data outside the places' facts: the referenced places' designations, the referenced courses, the
    # designation lists the sources cite (grounding(), the same three checks: digits, whole times, phones); the
    # referenced places' nearby rows only in a text about getting there (an access word or a row's name)
    extra = grounding(D, list(refs.values()), courses, D.cited_lists(sources))
    tg = transit_grounding(D, sources, list(refs.values()))   # transit.json, when the sources cite its providers
    known |= extra["numbers"] | tg["numbers"]
    clock |= tg["times"]
    extra["names"] = list(extra["names"]) + tg["names"]
    gos |= extra["go"]
    clock |= extra["times"]
    phones |= extra["phones"]
    dists |= extra["dists"]
    near = extra["access"]
    for where_, text in texts:
        about = bool(ACCESS_CUE.search(text) or any(n in text for n in near["names"]))
        t_known, t_dists, t_clock, t_phones = ((known | near["numbers"], dists | near["dists"], clock | near["times"],
                                                phones | near["phones"]) if about else (known, dists, clock, phones))
        plain, with_unit = set(), set()
        for m in NUM_RX.finditer(text):
            (with_unit if DIST_UNIT.match(text, m.end()) else plain).update(_nums(m.group(0)))
        unknown = sorted((plain - t_known) | (with_unit - t_known - t_dists), key=lambda x: float(x))
        if unknown:
            issues.append(f"{where_} 근거 없는 숫자 {unknown}")
        bad_times = sorted(_times(text) - t_clock)
        if bad_times:
            issues.append(f"{where_} 참조 장소의 값에 없는 시각 {bad_times}")
        bad_phones = sorted(_phones(text) - t_phones)
        if bad_phones:
            issues.append(f"{where_} 참조 장소의 값에 없는 전화번호 {bad_phones}")
        claims = sorted(_go_numbers(text) - counted - gos, key=int)
        if claims:
            issues.append(f"{where_} 'N곳' 개수 주장 {claims}이 counts·items 개수에 없음")
    if summary and not (_nums(summary) & counted):
        issues.append("summary에 데이터에서 센 숫자(counts의 n 또는 items 개수)가 없음")

    # wording, stock sentences, copies
    allowed = names + values + [n.split("(")[0] for n in names]
    strip = tuple(dict.fromkeys(names + extra["names"]))   # proper names ('팔공산 힐링' course) are not wording
    for where_, text in texts:
        found = pc._wording(text, strip)
        cleaned = text
        for n in sorted(strip, key=len, reverse=True):
            cleaned = cleaned.replace(n, " ")
        found += [f"{lbl}: …{m.group(0)}…" for pat, lbl in STOCK for m in [re.search(pat, cleaned)] if m]
        if SOURCE_COMMENTARY.search(cleaned) and not any(x.startswith("출처 해설체") or x.startswith("전언체") for x in found):
            found.append("출처 해설체")
        issues += [f"{where_} {w}" for w in found]
        for p, ov in zip(refs.values(), overviews):
            span = pc._longest_copy(text, ov, allowed)
            if span:
                issues.append(f"{where_} TourAPI 소개문 복사 {len(span)}자({p['name']}): '{span}'")
                break
    for i, it in enumerate(items):
        p = D.by_slug.get(_text(it.get("place_slug")))
        first = (summary_sentences(_text(it.get("reason"))) or [""])[0]
        if p and first and any(D.city.taut_rx(n).match(first) for n in pc.name_variants(p["name"], p.get("alternate_names"))):
            issues.append(f"items[{i}].reason 첫 문장이 상투구: '{first}'")

    # FAQ
    srcs = {_text(s.get("url")) for s in sources} | {_text(s.get("name")) for s in sources}
    taken = {}
    for x in others:
        for f in x.get("faq") or []:
            taken.setdefault(_qkey(f.get("q")), f"가이드 {x.get('id')}")
    for p in D.places:
        for f in p.get("faq") or []:
            taken.setdefault(_qkey(f.get("q")), f"장소 {p.get('id')}")
    mine: set[str] = set()
    for i, f in enumerate(g.get("faq") or []):
        f = f if isinstance(f, dict) else {}
        q, a = _text(f.get("q")), _text(f.get("a"))
        if not q or not a:
            issues.append(f"faq[{i}] q·a가 비어 있음")
            continue
        if not pc.JONDAE.search(q):
            issues.append(f"faq[{i}].q 존댓말 의문형('~나요?/~인가요?')이 아님: {q}")
        if _text(f.get("source")) not in srcs:
            issues.append(f"faq[{i}].source는 sources의 url·name 중 하나: {f.get('source')}")
        k = _qkey(q)
        if k in mine:
            issues.append(f"faq[{i}] 같은 질문이 두 번: {q}")
        elif k in taken:
            issues.append(f"faq[{i}] 같은 질문이 {taken[k]}에 있음: {q}")
        mine.add(k)
    return issues


def load_guides(path: Path) -> list[dict]:
    doc = json.loads(path.read_text("utf-8"))
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("guides"), list):
        return doc["guides"]
    if isinstance(doc, dict):
        return [doc]
    raise ValueError("가이드 객체, 가이드 목록, 또는 {\"guides\": [...]}이어야 함")


def review(paths: list[Path], *, data: Path) -> dict:
    """{"rows": [{file, id, guide, issues}], "problems": [file-level]}. Guides checked together must not repeat each
    other's slug or FAQ question either (the later one is reported)."""
    D = Data(data)
    rows, problems, batch = [], [], []
    for path in paths:
        try:
            guides = load_guides(path)
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: 읽을 수 없음 — {exc}")
            continue
        for g in guides:
            gid = _text((g if isinstance(g, dict) else {}).get("id"))
            stored_others = [x for x in D.guides if _text(x.get("id")) != gid]
            earlier = [x for x in batch if _text(x.get("id")) != gid]
            seen = {_text(x.get("id")) for x in earlier}
            issues = check_guide(g, D, others=earlier + [x for x in stored_others if _text(x.get("id")) not in seen])
            if gid in {_text(x.get("id")) for x in batch}:
                issues.append("같은 id가 이번 검사에 두 번")
            rows.append({"file": path.name, "id": gid, "guide": g, "issues": issues})
            if isinstance(g, dict):
                batch.append(g)
    return {"rows": rows, "problems": problems}


def finding_lines(rep: dict) -> list[str]:
    return rep["problems"] + [f"{r['file']} {r['id']} {x}" for r in rep["rows"] for x in r["issues"]]


def merge(paths: list[Path], *, data: Path, dry_run: bool = False) -> dict:
    gp = Path(data) / "guides.json"
    raw = gp.read_bytes() if gp.exists() else b"[]\n"
    guides = json.loads(raw.decode("utf-8"))
    rep = review(paths, data=data)
    out = {"dry_run": dry_run, "merged": 0, "replaced": 0, "refused": 0, "merged_ids": [], "refused_items": [],
           "problems": rep["problems"], "written": None}
    index = {_text(g.get("id")): i for i, g in enumerate(guides)}
    for row in rep["rows"]:
        if row["issues"]:
            out["refused"] += 1
            out["refused_items"].append({"file": row["file"], "id": row["id"], "issues": row["issues"]})
            continue
        if row["id"] in index:
            guides[index[row["id"]]] = row["guide"]
            out["replaced"] += 1
        else:
            index[row["id"]] = len(guides)
            guides.append(row["guide"])
        out["merged"] += 1
        out["merged_ids"].append(row["id"])
    if out["merged"] and not dry_run:
        if (gp.read_bytes() if gp.exists() else b"[]\n") != raw:
            raise SystemExit(f"{gp}이 검사 중에 바뀌었습니다(다른 작업이 쓰는 중) — 아무것도 쓰지 않았습니다. 다시 실행하세요.")
        pc.write_atomic(gp, dump(guides))
        out["written"] = str(gp)
    return out


# ------------------------------------------------------------------ cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("catalog", help="작성자용 장소 목록을 쓴다")
    a1.add_argument("--data", type=Path, required=True)
    a1.add_argument("--out", type=Path, required=True)
    a1.add_argument("--with-text", action="store_true", help="TourAPI 소개문(사실 확인용)을 더한다")
    a1.add_argument("--kind", action="append", help="이 유형만(여러 번 쓸 수 있음)")
    a2 = sub.add_parser("count", help="조건 하나의 개수와 장소")
    a2.add_argument("--data", type=Path, required=True)
    a2.add_argument("where", help="조건 JSON(COUNT_KEYS) 또는 @파일")
    a2.add_argument("--list", action="store_true", help="해당 장소를 함께 보인다")
    for name, help_ in (("check-guide", "가이드를 검사한다(문제가 있으면 종료 코드 1)"),
                        ("merge", "검사를 통과한 가이드만 guides.json에 넣는다")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--data", type=Path, required=True)
        s.add_argument("paths", nargs="+", type=Path)
        if name == "check-guide":
            s.add_argument("--json", action="store_true", help="결과를 JSON으로")
        else:
            s.add_argument("--dry-run", action="store_true", help="쓰지 않고 결과만 보인다")
    a = ap.parse_args(argv)
    if a.cmd == "catalog":
        print(json.dumps(catalog(a.data, a.out, a.with_text, a.kind), ensure_ascii=False))
        return 0
    if a.cmd == "count":
        text = Path(a.where[1:]).read_text("utf-8") if a.where.startswith("@") else a.where
        D = Data(a.data)
        try:
            got = select(D, json.loads(text))
        except ValueError as exc:
            print(f"조건 오류: {exc}")
            return 1
        res = {"n": len(got)}
        if a.list:
            res["places"] = [{"slug": p.get("slug"), "name": p.get("name"), "district": D.derived(p)["district"],
                              "area": D.derived(p)["area"]} for p in got]
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "check-guide":
        rep = review(a.paths, data=a.data)
        lines = finding_lines(rep)
        if a.json:
            print(json.dumps({"ok": not lines, "guides": len(rep["rows"]), "problems": rep["problems"],
                              "issues": [{"file": r["file"], "id": r["id"], "issues": r["issues"]}
                                         for r in rep["rows"] if r["issues"]]}, ensure_ascii=False, indent=1))
        else:
            for line in lines:
                print(line)
            if not lines:
                print(f"OK — 가이드 {len(rep['rows'])}편 통과")
        return 1 if lines else 0
    res = merge(a.paths, data=a.data, dry_run=a.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 1 if res["refused"] or res["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
