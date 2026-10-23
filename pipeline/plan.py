"""The AI course planner (/plan/, AI 코스 만들기) — the first city's operator request 2026-10-17: 'AI 여행 코스 생성기'
on its own page, very visible, many cute 3D pictures. The page asks /api/plan/ (chatbot/planner.js) and draws the plan
from the site's own place data: the model's words are only the title, the summary, a reason per stop and the notes;
every fact on a card is a value of the place's first screen, every photo a TourAPI KOGL-1/3 photo with its credit
(CLAUDE.md 3.4), and a place with no photo gets its kind's 3D picture (never an illustration in a photo's place,
CLAUDE.md 4). See docs/handover/planner.md.

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
                    "fact-closed", "fact-fee", "cond-wheelchair")
PLAN_QUICK_EDITS = [("비가 오면 실내 위주로 바꿔 주세요", "비 오면 실내로", "sit-rainy"),
                    ("걷는 거리를 줄여 주세요", "덜 걷게", "sit-walk"),
                    ("점심 맛집을 다른 곳으로 바꿔 주세요", "점심 바꾸기", "icon-food"),
                    ("입장료 없는 곳 위주로 바꿔 주세요", "입장료 줄이기", "sit-free"),
                    ("카페나 빵집을 한 곳 넣어 주세요", "카페 넣기", "kind-cafe")]


def plan_config(site: dict) -> dict:
    """site.json `plan`, checked loosely (problems() says what is wrong): {hubs [{key, name, place}], prefs [{key,
    label, prompt, pic, glyph}], resident_label, note_example}. Entries that cannot be used are left out."""
    raw = site.get("plan") if isinstance(site.get("plan"), dict) else {}
    hubs = []
    for h in raw.get("hubs") or []:
        if isinstance(h, dict) and KEY_RX.match(str(h.get("key") or "")) and squash_ws(h.get("name")):
            hubs.append({"key": h["key"], "name": squash_ws(h["name"]), "place": squash_ws(h.get("place"))})
    prefs = []
    for p in raw.get("prefs") or []:
        if isinstance(p, dict) and KEY_RX.match(str(p.get("key") or "")) and squash_ws(p.get("label")):
            prefs.append({"key": p["key"], "label": squash_ws(p["label"]),
                          "prompt": squash_ws(p.get("prompt")) or squash_ws(p["label"]),
                          "pic": squash_ws(p.get("pic")), "glyph": squash_ws(p.get("glyph")) or "pin"})
    if not prefs:
        prefs = [{"key": k, "label": lab, "prompt": pr, "pic": pic, "glyph": g} for k, lab, pr, pic, g in DEFAULT_PREFS]
    return {"hubs": hubs, "prefs": prefs[:PREFS_MAX], "resident_label": squash_ws(raw.get("resident_label")),
            "note_example": squash_ws(raw.get("note_example")) or NOTE_EXAMPLE}


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
    return out


def plan_meta(S) -> dict:
    """docs.json meta.plan (chatbot/plan_prompt.js, planner.js): {hubs {key: {name, path?, g?}}, prefs {key: the
    words the model reads}, resident} — a hub that is a place of the site carries its page and point."""
    cfg = plan_config(S.site)
    by_id = {e["id"]: e for e in S.entities}
    hubs = {}
    for h in cfg["hubs"]:
        row: dict = {"name": h["name"]}
        e = by_id.get(h["place"]) if h["place"] else None
        if e:
            row["path"] = e["_path"]
            geo = e.get("_geo") or {}
            if isinstance(geo.get("lat"), (int, float)) and isinstance(geo.get("lng"), (int, float)):
                row["g"] = [round(geo["lat"], 6), round(geo["lng"], 6)]
        hubs[h["key"]] = row
    return {"hubs": hubs, "prefs": {p["key"]: p["prompt"] for p in cfg["prefs"]}, "resident": cfg["resident_label"]}


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
            "n_places": len(S.entities), "n_courses": len(S.courses), "n_guides": len(S.guides),
            "region": S.site.get("region") or "", "note_example": cfg["note_example"],
            "has_tickets": bool((getattr(S, "tickets", None) or {}).get("tickets")),
            "mascots": {"work": pose("mascot-plan", "mascot-think"), "done": pose("mascot-plan-done", "mascot-hello"),
                        "rain": pose("mascot-plan-rain", "mascot-point"), "sorry": pose("mascot-sorry", "mascot-sorry")}}
