"""The AI course planner (/plan/, AI 코스 만들기) — the first city's operator request 2026-10-17: 'AI 여행 코스 생성기'
on its own page, very visible, many cute 3D pictures. The page asks /api/plan/ (chatbot/planner.js) and draws the plan
from the site's own place data: the model's words are only the title, the summary, a reason per stop and the notes;
every fact on a card is a value of the place's first screen, every photo a TourAPI KOGL-1/3 photo with its credit
(CLAUDE.md 3.4), and a place with no photo gets its kind's 3D picture (never an illustration in a photo's place,
CLAUDE.md 4). The server side: chatbot/planner.js (its header).

The city's values are site.json `plan` (plan_config), nothing of a city is written here:

    hubs            [{key, name, place?}] where a trip may start and end (a station, a terminal, an airport): the form's
                    출발·도착. A hub that is a place record of the site names it (place: its id) and its leg gets the
                    straight-line distance; any other hub is a name only (no point on the site, a directions link by
                    names). None: the form has no such choice.
    resident_label  the word a combined ticket's table uses for the residents whose price is the second of a pair
                    (pipeline/tickets.py); needed only when data/<region>/tickets.json has tickets.
    prefs           [{key, label, prompt, pic, glyph}] the 좋아하는 것 cards (label), the words the model reads (prompt),
                    the card's 3D picture ID and line glyph; default DEFAULT_PREFS.
    note_example    the placeholder of the form's 하고 싶은 말 box (an example wish, no facts); default NOTE_EXAMPLE.
    hubs[].region   the travel area (권역, as the place pages name it) a hub is in — the margin after it before a stop
                    in another area is longer (chatbot/plan_state.hubMargin); with its basis in hubs[].basis.
    far             {area: {car, transit}} minutes: a leg into or out of that travel area keeps at least this margin
                    (an island reached by one bus an hour); none: 30 / 45 minutes between any two areas.
    pref_regions    {pref key: [areas]} a liking read by the travel area a page names (islands); pref_types {pref key:
                    [the city's type labels]} a liking read by the city's own list labels besides the engine's classes.
    hub_guides      [{hub?, region?, path, label}] the site's bus guidance for a hub's leg without a car, first match.
    transit_strict  true: without a car the data names no bus stop or route for the city's places, so a leg longer
                    than a walk is sent back and the way to the first stop and back is a check (chatbot/planner.js).
    rules           the city's own lines for the planner's rules (English, facts only from the site's guides).

plan_meta() hands the server the same values with each hub's page and point (docs.json meta.plan); plan_places() and
plan_vm() make the page's data and context; problems() is what validate reports about the block.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .schema import KIND_LABELS
from .textutil import squash_ws

KEY_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
# the 좋아하는 것 cards: (key, card label, the words the model reads, 3D picture ID, glyph for the interim look) — the
# keys are what /api/plan/ accepts (chatbot/plan_prompt.js reads the prompts from docs.json meta.plan.prefs)
DEFAULT_PREFS = (
    ("history", "역사·문화", "역사·문화(박물관·문화유산·근대 건물)", "theme-modern-history", "building"),
    ("food", "맛집", "맛집", "icon-food", "bowl"),
    ("nature", "자연·힐링", "자연·힐링(공원·산·호수)", "theme-parks-nature", "tree"),
    ("alleys", "골목 산책", "골목 산책", "theme-alleys-culture", "lamp"),
    ("cafe", "카페·빵집", "카페·빵집", "kind-cafe", "cup"),
    ("experience", "체험", "체험", "kind-experience", "spark"),
    ("night", "야경", "야경", "sit-night", "moon"),
    ("photo", "사진 명소", "사진 명소", "pref-photo", "camera"),
)
PREFS_MAX = 12
NOTE_EXAMPLE = "예: 점심은 전통시장에서 먹고 싶어요. 오후엔 공원을 걷고 싶어요."

# a place's 3D picture by its visual's glyph (build.VISUALS, a theme's own visual) — _ui.html.j2 KIND_PIC
KIND_PIC = {"bed": "kind-stay", "bowl": "kind-food", "museum": "kind-museum", "spark": "kind-experience",
            "building": "theme-modern-history", "wave": "theme-islands-sea", "tree": "theme-parks-nature",
            "lamp": "theme-alleys-culture", "pin": "kind-attraction", "cup": "kind-cafe"}

# the planner's fixed choices: (value, label, picture ID, glyph for the interim look) — the values are
# chatbot/plan_prompt.js MOVE / WITH / NEEDS keys and the trip's length in days
PLAN_CHOICES = {
    "days": [(1, "당일치기", "plan-dur-day", "sun"), (2, "1박 2일", "plan-dur-1n2d", "moon"), (3, "2박 3일", "plan-dur-2n3d", "bag")],
    "move": [("car", "자가용", "fact-parking", "car"), ("transit", "대중교통·걷기", "sit-carfree", "bus")],
    "with": [("solo", "혼자", "plan-with-solo", "user"), ("couple", "연인·친구", "plan-with-couple", "heart"),
             ("kids", "아이와 가족", "sit-kids", "family"), ("parents", "부모님과", "plan-with-parents", "cup")],
    "needs": [("rain", "비 와도 실내 위주", "sit-rainy", "umbrella"), ("stroller", "유모차", "cond-stroller", "family"),
              ("wheelchair", "휠체어", "cond-wheelchair", "access"), ("parking", "주차 편한 곳", "cond-parking", "car"),
              ("free", "입장료 없는 곳 위주", "sit-free", "ticket"), ("lesswalk", "걷기 적게", "sit-walk", "walk")],
}
# the pictures the result draws by ID (plan.js clones them from the page's <template>)
PLAN_RESULT_PICS = ("kind-attraction", "kind-food", "kind-stay", "kind-cafe", "kind-museum", "kind-experience",
                    "theme-modern-history", "theme-islands-sea", "theme-parks-nature", "theme-alleys-culture",
                    "transit-bus", "sit-walk", "fact-parking", "plan-budget", "plan-swap", "icon-map", "fact-hours",
                    "fact-closed", "fact-fee", "cond-wheelchair", "icon-course")
# what the form says when a need is picked: the count of places to visit the site's data says fit it ({n}:
# pipeline/chat_index.need_counts) — a place it says nothing of is not one the need does not fit
PLAN_NEED_NOTES = {
    "rain": "비 와도 실내 위주: 실내라고 사이트 자료에 있는 관광지 {n}곳",
    "stroller": "유모차: 출입구 자료로 접근할 수 있다고 나온 관광지 {n}곳",
    "wheelchair": "휠체어: 출입구 자료로 접근할 수 있다고 나온 관광지 {n}곳",
    "parking": "주차 편한 곳: 주차할 수 있다(또는 근처 공영주차장)고 사이트 자료에 있는 관광지 {n}곳",
    "free": "입장료 없는 곳 위주: 무료라고 사이트 자료에 있는 관광지 {n}곳",
    "lesswalk": "걷기 적게: 걷는 거리는 사이트 자료로 잴 수 없어 구간 직선거리만 적어요",
}
PLAN_NEED_TAIL = "사이트에 자료가 있는 곳의 수예요. 자료가 없는 곳은 이용할 수 없다는 뜻이 아니라 사이트에 정보가 없다는 뜻이에요 — 방문 전 전화로 확인하세요."
PLAN_QUICK_EDITS = [("비가 오면 실내 위주로 바꿔 주세요", "비 오면 실내로", "sit-rainy"),
                    ("걷는 거리를 줄여 주세요", "덜 걷게", "sit-walk"),
                    ("점심 맛집을 다른 곳으로 바꿔 주세요", "점심 바꾸기", "icon-food"),
                    ("입장료 없는 곳 위주로 바꿔 주세요", "입장료 줄이기", "sit-free"),
                    ("카페나 빵집을 한 곳 넣어 주세요", "카페 넣기", "kind-cafe")]


def plan_config(site: dict) -> dict:
    """site.json `plan`, checked loosely (problems() says what is wrong): {hubs [{key, name, place, region}], prefs
    [{key, label, prompt, pic, glyph}], resident_label, note_example, far, pref_regions, pref_types, hub_guides,
    transit_strict, rules}. Entries that cannot be used are left out."""
    raw = site.get("plan") if isinstance(site.get("plan"), dict) else {}
    hubs = []
    for h in raw.get("hubs") or []:
        if isinstance(h, dict) and KEY_RX.match(str(h.get("key") or "")) and squash_ws(h.get("name")):
            hubs.append({"key": h["key"], "name": squash_ws(h["name"]), "place": squash_ws(h.get("place")),
                         "region": squash_ws(h.get("region"))})
    prefs = []
    for p in raw.get("prefs") or []:
        if isinstance(p, dict) and KEY_RX.match(str(p.get("key") or "")) and squash_ws(p.get("label")):
            prefs.append({"key": p["key"], "label": squash_ws(p["label"]),
                          "prompt": squash_ws(p.get("prompt")) or squash_ws(p["label"]),
                          "pic": squash_ws(p.get("pic")), "glyph": squash_ws(p.get("glyph")) or "pin"})
    if not prefs:
        prefs = [{"key": k, "label": lab, "prompt": pr, "pic": pic, "glyph": g} for k, lab, pr, pic, g in DEFAULT_PREFS]
    far = {}
    for area, v in (raw.get("far") or {}).items() if isinstance(raw.get("far"), dict) else ():
        if squash_ws(area) and isinstance(v, dict) and all(isinstance(v.get(k), int) and 0 <= v[k] <= 600 for k in ("car", "transit")):
            far[squash_ws(area)] = {"car": v["car"], "transit": v["transit"]}

    def by_key(name):
        raw_map = raw.get(name) if isinstance(raw.get(name), dict) else {}
        return {k: [squash_ws(x) for x in v if squash_ws(x)] for k, v in raw_map.items()
                if KEY_RX.match(str(k)) and isinstance(v, list) and any(squash_ws(x) for x in v)}
    guides = [{k: squash_ws(g.get(k)) for k in ("hub", "region", "path", "label") if squash_ws(g.get(k))}
              for g in raw.get("hub_guides") or [] if isinstance(g, dict)
              and str(g.get("path") or "").startswith("/") and squash_ws(g.get("label"))]
    rules = [squash_ws(r) for r in raw.get("rules") or [] if isinstance(r, str) and squash_ws(r)]
    return {"hubs": hubs, "prefs": prefs[:PREFS_MAX], "resident_label": squash_ws(raw.get("resident_label")),
            "note_example": squash_ws(raw.get("note_example")) or NOTE_EXAMPLE, "far": far,
            "pref_regions": by_key("pref_regions"), "pref_types": by_key("pref_types"), "hub_guides": guides,
            "transit_strict": raw.get("transit_strict") is True, "rules": rules}


def problems(site: dict, published: dict[str, dict]) -> list[str]:
    """What is wrong with site.json `plan` (Korean, one line each): a hub needs a key (a-z·0-9·-) and a name, keys and
    names once each, and a hub's place a published place; a pref needs a key and a label, keys once each."""
    raw = site.get("plan")
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["plan: 객체여야 함"]
    out = []
    keys, names = [], []
    for h in raw.get("hubs") or []:
        if not (isinstance(h, dict) and KEY_RX.match(str(h.get("key") or "")) and squash_ws(h.get("name"))):
            out.append(f"plan.hubs 항목은 {{key(a-z·0-9·-), name, place?}}: {h!r}")
            continue
        keys.append(h["key"])
        names.append(squash_ws(h["name"]))
        if squash_ws(h.get("place")) and squash_ws(h["place"]) not in published:
            out.append(f"plan.hubs {h['key']}: place {h['place']}가 공개 장소가 아님")
    pkeys = []
    for p in raw.get("prefs") or []:
        if not (isinstance(p, dict) and KEY_RX.match(str(p.get("key") or "")) and squash_ws(p.get("label"))):
            out.append(f"plan.prefs 항목은 {{key(a-z·0-9·-), label, prompt?, pic?, glyph?}}: {p!r}")
            continue
        pkeys.append(p["key"])
    for what, xs in (("plan.hubs key", keys), ("plan.hubs name", names), ("plan.prefs key", pkeys)):
        twice = sorted({x for x in xs if xs.count(x) > 1})
        if twice:
            out.append(f"{what} 중복: {', '.join(twice)}")
    if len(pkeys) > PREFS_MAX:
        out.append(f"plan.prefs는 {PREFS_MAX}개까지")
    for area, v in (raw.get("far") or {}).items() if isinstance(raw.get("far"), dict) else ():
        if not (isinstance(v, dict) and all(isinstance(v.get(k), int) and 0 <= v[k] <= 600 for k in ("car", "transit"))):
            out.append(f"plan.far {area}: {{car, transit}} 분(0~600 정수)이어야 함")
    for g in raw.get("hub_guides") or []:
        if not (isinstance(g, dict) and str(g.get("path") or "").startswith("/") and squash_ws(g.get("label"))):
            out.append(f"plan.hub_guides 항목은 {{hub?, region?, path(/…), label}}: {g!r}")
        elif squash_ws(g.get("hub")) and squash_ws(g["hub"]) not in keys:
            out.append(f"plan.hub_guides: hub {g['hub']}가 plan.hubs에 없음")
    if "transit_strict" in raw and not isinstance(raw["transit_strict"], bool):
        out.append("plan.transit_strict는 true/false")
    return out


def plan_meta(S) -> dict:
    """docs.json meta.plan (chatbot/city.js readPlan): {hubs {key: {name, path?, g?, region?}}, prefs {key: the words
    the model reads}, resident, far, pref_regions, pref_types, hub_guides, transit_strict, rules} — a hub that is a
    place of the site carries its page and point."""
    cfg = plan_config(S.site)
    by_id = {e["id"]: e for e in S.entities}
    hubs = {}
    for h in cfg["hubs"]:
        row: dict = {"name": h["name"], **({"region": h["region"]} if h["region"] else {})}
        e = by_id.get(h["place"]) if h["place"] else None
        if e:
            row["path"] = e["_path"]
            geo = e.get("_geo") or {}
            if isinstance(geo.get("lat"), (int, float)) and isinstance(geo.get("lng"), (int, float)):
                row["g"] = [round(geo["lat"], 6), round(geo["lng"], 6)]
        hubs[h["key"]] = row
    return {"hubs": hubs, "prefs": {p["key"]: p["prompt"] for p in cfg["prefs"]}, "resident": cfg["resident_label"],
            **{k: cfg[k] for k in ("far", "pref_regions", "pref_types", "hub_guides", "rules") if cfg[k]},
            **({"transit_strict": True} if cfg["transit_strict"] else {})}


# the engine's classes of a place to visit (chatbot/plan_geo.js FLOORS, plan_state.js INDOOR/OUTDOOR and PREF_TYPES
# read them): a city whose list labels are other words (site.json list_filters.attraction_groups) has each place
# classed by its source category and name with the engine's own groups (pipeline/build.ATTRACTION_GROUPS) — a TourAPI
# 문화시설 that names a museum or an exhibition hall is 박물관·전시, any other 문화시설, 레포츠 and 쇼핑 as they are, else
# the engine group the words find, else none (the planner then knows nothing of indoors or outdoors)
PLAN_CLASSES = ("박물관·전시", "체험", "레포츠", "문화유산", "문화시설", "골목과 문화", "시장·쇼핑", "자연·야외", "산업·회의 시설")
MUSEUM_RX = re.compile(r"박물관|전시관|기념관|미술관|과학관|홍보관")


# TourAPI's own classification (lclsSystm3, the record's tourapi.lcls; names from lclsSystmCode2) of a place outdoors:
# 자연관광 but caves, 도시공원, 거리·마을·둘레길, landmarks one stands outside of (다리, 분수, 동상, 댐, 등대, 조형물), camping,
# 역사유적지 but modern buildings, 역사유물, water and air sports but swimming. A place the planner's type words do not
# call indoors or outdoors reads as outdoors for the rain by it (QA 2026-10-26 F01: 희방폭포·죽계구곡 went in an indoor
# day as '실내인지 자료 없음', past the one-outdoor-stop rule). Nothing here names a city: the codes are the nation's.
OUTDOOR_LCLS = {
    **{f"NA01{n:02d}00": w for n, w in enumerate(("산, 고개, 오름, 봉우리", "숲", "폭포", "계곡", "약수터"), 1)},
    **{f"NA02{n:02d}00": w for n, w in enumerate(("강", "호수", "저수지", "연못·늪", "섬", "염전", "항구/포구", "해안절경",
                                                   "해변. 해수욕장"), 1)},
    **{f"NA03{n:02d}00": w for n, w in ((2, "희귀동.식물"), (3, "기암괴석"), (4, "생태습지"), (5, "기타자연생태"))},
    **{f"NA04{n:02d}00": w for n, w in enumerate(("국립공원", "도립공원", "군립공원", "지질공원", "생태관광지", "자연휴양림",
                                                   "수목원ㆍ정원"), 1)},
    "NA050100": "기타자연관광",
    **{f"VE01{n:02d}00": w for n, w in ((3, "다리 / 대교"), (4, "분수"), (5, "동상"), (7, "댐"), (8, "등대"),
                                         (9, "기타 건축/조형물"))},
    **{f"VE03{n:02d}00": w for n, w in enumerate(("시민공원", "소공원", "어린이공원", "근린공원", "주제공원"), 1)},
    **{f"VE04{n:02d}00": w for n, w in enumerate(("골목길, 문화거리", "마을관광지", "둘레길"), 1)},
    **{f"AC05{n:02d}00": w for n, w in enumerate(("일반야영장", "오토캠핑장", "카라반", "글램핑장"), 1)},
    **{f"HS01{n:02d}00": w for n, w in enumerate(("고궁", "성ㆍ산성ㆍ성곽", "문", "고택", "생가", "민속마을", "사적지", "고분, 능",
                                                   "사당", "선사유적지"), 1)},
    "HS011200": "기타역사유적지",
    **{f"HS02{n:02d}00": w for n, w in enumerate(("탑ㆍ비석ㆍ기념탑", "선사유물", "불상", "기타역사유물"), 1)},
    **{f"LS02{n:02d}00": w for n, w in enumerate(("윈드서핑/제트스키", "카약/카누", "요트", "스노쿨링/스킨스쿠버다이빙", "민물낚시",
                                                   "바다낚시", None, "래프팅", "수상오토바이", "수상자전거", "조정", "워터슬레드",
                                                   "패러세일", "기타수상레저스포츠"), 1) if w},
    **{f"LS03{n:02d}00": w for n, w in enumerate(("스카이다이빙", "초경량비행", "헹글라이딩/패러글라이딩", "열기구",
                                                   "무인비행장치(드론)", "기타항공레저스포츠"), 1)},
}
# the planner's type words for indoors and for outdoors (chatbot/plan_state.js INDOOR, OUTDOOR — the same words)
INDOOR_CLASS = re.compile(r"박물관|전시|문화시설|미술관")
OUTDOOR_CLASS = re.compile(r"자연·야외|레포츠")


def outdoor_lcls(e: dict, ty: str = "") -> str:
    """The TourAPI class name (OUTDOOR_LCLS) of a place to visit that its type `ty` (plan_class) calls neither indoors
    nor outdoors, or ''."""
    if e.get("kind") != "attraction" or INDOOR_CLASS.search(ty or "") or OUTDOOR_CLASS.search(ty or ""):
        return ""
    code = (e.get("tourapi") or {}).get("lcls") or ""
    if isinstance(code, list):   # tourapi_bulk keeps the three levels: the last is the place's own
        code = code[-1] if code else ""
    return OUTDOOR_LCLS.get(str(code).strip(), "")


def plan_class(e: dict, S) -> str:
    """The engine class (PLAN_CLASSES) of a place to visit, '' when none fits; its own type when that is one."""
    t = e.get("_type") or ""
    if e.get("kind") != "attraction" or t in PLAN_CLASSES:
        return t
    from . import build as B
    cat = squash_ws(e.get("category"))
    if cat == "문화시설":
        return "박물관·전시" if MUSEUM_RX.search(f"{cat} {e.get('name', '')}") else "문화시설"
    if cat == "레포츠":
        return "레포츠"
    if cat in ("쇼핑", "시장") or cat.startswith("쇼핑"):
        return "시장·쇼핑"
    g = B.category_group(e, B.ATTRACTION_GROUPS, getattr(S, "mountain", None) or B.mountain_rx(list(B.MOUNTAIN_NOT)))
    return g if g in PLAN_CLASSES else ""


def plan_places(S) -> dict:
    """{path: {n name, k kind, t type, a area, r its 구·군 or 권역, ic its kind's picture ID, img? {u, w, h, alt, t KOGL
    type, s/sw the provider's small copy}, h hours, c closed days, f fee, m menu, p parking, ci check-in, g [lat, lng]}}
    for every published place — each value as the place's first screen shows it (key_facts 'hero'; both sources where
    they differ)."""
    from .present import key_facts, thumb

    C = S.city
    out = {}
    for e in S.entities:
        slots = {s["key"]: s for s in key_facts(e, "hero")["slots"]}

        def val(k):
            s = slots.get(k)
            if not s or s.get("missing"):
                return ""
            if s.get("vals"):
                return " / ".join(squash_ws(f"{v.get('provider') or ''} {v.get('main') or ''}") for v in s["vals"])
            return " · ".join(x for x in (s.get("main"), s.get("sub")) if x)

        ph = e["_photos"][0] if e.get("_photos") else None
        th = thumb(ph) if ph else None
        geo = e.get("_geo") or {}
        region = e.get("_region") if e.get("_region") not in (None, "", C.none_label) else ""
        if region and C.region_mode != "district":
            region = f"{region} {C.region_label}"
        row = {"n": e["name"], "k": e["kind"], "t": e.get("_type") or KIND_LABELS.get(e["kind"], ""),
               "a": e.get("_area") or "", "r": region,
               "ic": KIND_PIC.get((e.get("_visual") or ("", "pin"))[1], "kind-attraction")}
        if ph:   # the provider's own file (KOGL-3 is never cropped: the card frames it whole), its small copy in srcset
            row["img"] = {"u": ph["url"], "w": ph["w"], "h": ph["h"], "alt": ph["alt"], "t": ph["type"],
                          **({"s": th["url"], "sw": th["w"]} if th and th["url"] != ph["url"] and th.get("w") else {})}
        for key, slot in (("h", "hours"), ("c", "closed"), ("f", "fee"), ("m", "menu"), ("p", "parking"), ("ci", "checkin")):
            v = val(slot)
            if v:
                row[key] = v
        if isinstance(geo.get("lat"), (int, float)) and isinstance(geo.get("lng"), (int, float)):
            row["g"] = [round(geo["lat"], 6), round(geo["lng"], 6)]
        out[e["_path"]] = row
    return out


def plan_vm(S) -> dict:
    """The /plan/ page's context: the choices (the city's hubs and prefs with the fixed ones), the result pictures and
    quick edits, the counts the page's words name, the courses to fall back on, the mascot poses."""
    cfg = plan_config(S.site)
    choices = {**PLAN_CHOICES, "prefs": [(p["key"], p["label"], p["pic"], p["glyph"]) for p in cfg["prefs"]],
               "hubs": [(h["key"], h["name"]) for h in cfg["hubs"]]}
    # the planner's own mascot poses once tools/mascot_media.py has made them, else the nearest existing pose
    have = json.loads((Path(__file__).resolve().parent.parent / "templates" / "assets" / "mascot" / "manifest.json")
                      .read_text("utf-8"))

    def pose(own, other):   # {name, kind}: 'medium' (200·400) when its files exist, else 'small' (96·192)
        name = own if own in have else other
        files = [f for f, *_ in (have.get(name) or {}).get("webp", [])]
        return {"name": name, "kind": "medium" if f"{name}-200.webp" in files else "small"}
    return {"choices": choices, "result_pics": PLAN_RESULT_PICS, "quick_edits": PLAN_QUICK_EDITS,
            "need_notes": PLAN_NEED_NOTES, "need_tail": PLAN_NEED_TAIL, "transit_strict": cfg["transit_strict"],
            "n_places": len(S.entities), "n_courses": len(S.courses), "n_guides": len(S.guides),
            "region": S.site.get("region") or "", "note_example": cfg["note_example"],
            "has_tickets": bool((getattr(S, "tickets", None) or {}).get("tickets")),
            "mascots": {"work": pose("mascot-plan", "mascot-think"), "done": pose("mascot-plan-done", "mascot-hello"),
                        "rain": pose("mascot-plan-rain", "mascot-point"), "sorry": pose("mascot-sorry", "mascot-sorry")}}
