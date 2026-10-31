"""조건으로 찾기 — the condition chips of the list pages (/food/, /places/, /stays/, the theme lists and every
version's lists; operator 2026-10-31, design ③ Filter.dc.html).

Each condition is decided at build time from the value the place page shows (the record's facts after
textutil.keep_primary_facts: one value per field, site.json fact_conflicts 'primary'; with that key off a field two
sources state differently decides nothing). A condition the data cannot decide is never made: there is no 아이와
chip (no field says so), no 반려동물 chip on the food list (no restaurant has a pet value), and a chip whose list has
no place that meets it is left out (conditions()).

    mon       월요일 영업 / 월요일 개방   present.monday_open on the closed-day text — the rule of the food list's former
                                         '월요일 영업 표기' box and of the first site's Monday restaurants guide
    late      21시 이후까지 (food)        the latest closing time of the hours value, the guide '늦게 까지 하는 식당'
                                         (guide-25) way — the latest day counts, a break, a last order or a
                                         preparation range never closes the day, '익일 02:00' is 26:00, '24시간'
                                         is all day — at 21:00 or later
    park      주차 가능                   parking (or the parking half of a city's '주차 및 좌석수': a seat count alone is no
                                         parking, schema.parking_seats_part) that says a car can be left: '가능…',
                                         'n대', '…주차장…'; never '불가', '없음', '전화문의'
    pack      포장 가능 (food)            packing '가능…'
    pet       반려동물 동반               pet that allows one ('가능', '동반가능', '반려견 동반 …'), never '불가'/'없음'
    free      무료 (attraction)           usefee exactly '무료' (the former '요금 무료' box)
    stroller  유모차 대여 (attraction)    babycarriage '대여 가능…'/'가능'/'있음'
    wheel     휠체어                      wheelchair '대여가능…', or an entrance route a wheelchair takes ('휠체어 접근
                                         가능', '턱이/단차가 없어', '경사로가 설치되어 있음' unless '완만하지 않음',
                                         '엘리베이터 설치')
    cook      취사 가능 (stay)            cooking '가능…' (also '일부객실만 가능')

A reason (the card's '이 조건에 맞는 이유' tag) is {id, key (the field), label, value, provider, short}: the field's
label and value as the list shows them, the source's short name. No date: check dates stay in the data and JSON-LD,
never on a page (operator decision 2026-10-09, pipeline.validate visible_check_dates)."""
from __future__ import annotations

import re

from . import present as P
from .schema import FACT_LABELS, PARKING_WORDS, SEAT_COUNT
from .textutil import TILDE, parking_text, squash_ws

# the chips of each kind, in their order on the page
KIND_CONDS = {
    "food": ("mon", "late", "park", "pack", "pet", "wheel"),
    "attraction": ("mon", "free", "park", "pet", "stroller", "wheel"),
    "stay": ("park", "pet", "cook", "wheel"),
}
LATE_AT = 21 * 60   # the late chip: open until 21:00 or later
# the list's former check box (?check=1) is the condition it became: a shared old link keeps its rows
LEGACY_CHECK = {"attraction": "free", "food": "mon"}

_NOT_CLOSE = re.compile(r"(?:준비|브레이크|break|쉬는|휴게|주문|라스트|오더|L\.?O|입장|마감)[^\d]{0,6}$", re.I)
_RANGE = re.compile(rf"(\d{{1,2}}):(\d{{2}})\s*(?:{TILDE}|[-–—])\s*(익일|다음\s*날|새벽)?\s*(\d{{1,2}}):(\d{{2}})")
_ALLDAY = re.compile(r"24\s*시간(?!\s*전)")


def close_time(raw: str | None) -> dict | None:
    """The latest closing time an hours value states: {minutes, t ('22:00'), next (past midnight: '익일 02:00'),
    allday ('24시간 영업')} or None. Every range counts but those a break, a last order, a preparation time or a last
    entry names (the words just before it on its line); a range ending at or before its start, or after '익일', ends
    the next day."""
    text = str(raw or "")
    if not text.strip():
        return None
    if _ALLDAY.search(text):
        return {"minutes": 48 * 60, "t": "", "next": False, "allday": True}
    best = None
    for line in re.split(r"[\n/]|(?<=\))|-\s+(?=\D)", text):
        for m in _RANGE.finditer(line):
            if _NOT_CLOSE.search(line[max(0, m.start() - 14):m.start()]):
                continue
            a = int(m.group(1)) * 60 + int(m.group(2))
            b = int(m.group(4)) * 60 + int(m.group(5))
            nxt = bool(m.group(3)) or (b <= a and b < 12 * 60)
            mins = b + (24 * 60 if nxt else 0)
            if best is None or mins > best["minutes"]:
                best = {"minutes": mins, "t": f"{int(m.group(4)):02d}:{m.group(5)}", "next": nxt, "allday": False}
    return best


def hours_text(e: dict) -> tuple[str, str]:
    """(field, value) of the place's hours: a restaurant's combined '영업시간·정기휴일' first, else usetime."""
    f = e.get("facts") or {}
    for k in ("usetime_restdate", "usetime"):
        if squash_ws(f.get(k)):
            return k, f[k]
    return "", ""


_PARK_NO = re.compile(r"불가|없음|안\s*됨|전화\s*문의|문의")
_PARK_YES = re.compile(r"^가능|주차|\d\s*대|무료")


def parking_value(e: dict) -> tuple[str, str] | None:
    """(field, shown text) when the place's parking value says a car can be left there (or at the lot it names);
    the parking half of a '주차 및 좌석수' value ('7대/40석' -> '7대'); None otherwise."""
    f = e.get("facts") or {}
    raw = squash_ws(f.get("parking"))
    if raw:
        t = parking_text(f["parking"])
        return ("parking", t) if not _PARK_NO.search(t) and _PARK_YES.search(t) else None
    raw = squash_ws(f.get("parking_seats"))
    if not raw:
        return None
    parts = [p.strip() for p in re.split(r"[/／]", raw) if p.strip()]
    car = [p for p in parts if not SEAT_COUNT.match(p) and PARKING_WORDS.search(p)]
    if not car:
        return None
    t = car[0]
    if _PARK_NO.search(t) or re.fullmatch(r"0\s*대", t):
        return None
    return ("parking_seats", t) if _PARK_YES.search(t) else None


def _yes(raw, yes: str, no: str = r"^(?:불가|불가능|없음|안\s*됨)") -> bool:
    t = squash_ws(raw)
    return bool(t) and not re.search(no, t) and bool(re.search(yes, t))


def pet_value(raw) -> str:
    """A pet value the tag can show: the pet service's first part without its label ('동반 구분 전구역 동반가능 · …'
    -> '전구역 동반가능'), else the value whole."""
    t = squash_ws(raw).split(" · ")[0]
    return re.sub(r"^동반\s*구분\s*", "", t)


_ROUTE_YES = re.compile(r"휠체어\s*접근\s*가능|경사로\s*완만함|턱이\s*없|단차가\s*없|경사로가?\s*설치되어\s*있음|엘리베이터\s*설치")
_ROUTE_NO = re.compile(r"완만하지\s*않|설치되어\s*있지\s*않|없음|공사")


def judge(e: dict, city=None) -> dict[str, dict]:
    """{condition id: reason} for one place (the conditions of its kind that its shown values meet)."""
    kind = e.get("kind") if e.get("kind") in KIND_CONDS else "attraction"
    f = e.get("facts") or {}
    out: dict[str, dict] = {}

    def add(cid: str, key: str, label: str, value: str, **extra):
        src = P.src_of(e, key)
        out[cid] = {"id": cid, "key": key, "label": label, "value": squash_ws(value), "provider": src["provider"],
                    "short": P.slot_provider(src["provider"], city=city) if city else src["provider"], **extra}

    for cid in KIND_CONDS[kind]:
        if cid == "mon":
            # the rule of the former '월요일 영업 표기' box and of guide-24: the closed-day texts state the closed days
            # (or 연중무휴) and Monday is not among them, not even partly; with both values shown (fact_conflicts off)
            # every source has to say so
            rest = f"{squash_ws(f.get('restdate'))} {squash_ws(f.get('usetime_restdate'))}".strip()
            texts = [rest] + [a["value"] for k in ("restdate", "usetime_restdate") for a in P.contested(e, k)]
            if not rest or not all(P.monday_open(t) for t in texts):
                continue
            v = P.slot_value(e, "closed")
            if v and v.get("main") and not v.get("conflict"):
                add(cid, v["src_key"], v["label"], v["main"])
            else:   # the weekday words sit in an hours text the closed-day slot does not split out
                k = "restdate" if squash_ws(f.get("restdate")) else "usetime_restdate"
                add(cid, k, FACT_LABELS.get(k, ""), P.split_closed(f[k])[1] or squash_ws(f[k]))
        elif cid == "late":
            k, raw = hours_text(e)
            if not k or P.contested(e, k):
                continue
            c = close_time(raw)
            if c and c["minutes"] >= LATE_AT:
                add(cid, k, "", "", close=c)
        elif cid == "park":
            pv = parking_value(e)
            if pv and not P.contested(e, pv[0]):
                # the value as the list's parking cell shows it (present.brief_parking: a fee note goes to its own
                # line there, so it stays off the tag); the parking half of '7대/40석' alone
                b = P.brief_parking(pv[1]) if pv[0] == "parking" else None
                add(cid, pv[0], FACT_LABELS["parking"], b["main"] if b else re.sub(r"^주차\s*", "", pv[1]))
        elif cid == "free":
            if squash_ws(f.get("usefee")) == "무료" and not P.contested(e, "usefee"):
                add(cid, "usefee", FACT_LABELS["usefee"], "무료")
        elif cid in ("pack", "pet", "stroller", "cook"):
            key = {"pack": "packing", "pet": "pet", "stroller": "babycarriage", "cook": "cooking"}[cid]
            yes = {"pack": r"^가능", "pet": r"가능|반려견\s*동반|동반\s*전용", "stroller": r"대여\s*가능|^가능|^있음",
                   "cook": r"가능"}[cid]
            if _yes(f.get(key), yes) and not P.contested(e, key):
                add(cid, key, FACT_LABELS[key], pet_value(f[key]) if cid == "pet" else f[key])
        elif cid == "wheel":
            if _yes(f.get("wheelchair"), r"대여\s*가능|^가능|^있음") and not P.contested(e, "wheelchair"):
                add(cid, "wheelchair", FACT_LABELS["wheelchair"], f["wheelchair"])
            elif (_ROUTE_YES.search(squash_ws(f.get("accessible_route"))) and
                  not _ROUTE_NO.search(squash_ws(f.get("accessible_route"))) and not P.contested(e, "accessible_route")):
                add(cid, "accessible_route", FACT_LABELS["accessible_route"], f["accessible_route"])
    return out


def late_text(c: dict, words: dict) -> str:
    """The late tag's words: '22:00까지 영업', '익일 02:00까지 영업', '24시간 영업' (words = locales.COND_WORDS[code])."""
    if c.get("allday"):
        return words["allday"]
    return words["late_next" if c.get("next") else "late_at"].replace("{t}", c["t"])


def chip_label(cid: str, kind: str, words: dict) -> str:
    return words["labels"].get(f"{cid}_{kind}") or words["labels"][cid]


def conditions(kind: str, rows: list[dict], words: dict) -> list[dict]:
    """The chips of a list: {id, label, n} for each condition of the kind that at least one row meets (rows carry
    conds: {id: reason}), in KIND_CONDS order."""
    out = []
    for cid in KIND_CONDS.get(kind, ()):
        n = sum(1 for r in rows if cid in (r.get("conds") or {}))
        if n:
            out.append({"id": cid, "label": chip_label(cid, kind, words), "n": n})
    return out


def ko_tags(conds: dict[str, dict], words: dict) -> list[dict]:
    """A Korean row's reason tags, in KIND_CONDS order: {id, label, value, src}."""
    out = []
    for r in conds.values():
        if r["id"] == "late":
            out.append({"id": "late", "label": "", "value": late_text(r["close"], words), "src": r["short"]})
        else:
            out.append({"id": r["id"], "label": r["label"], "value": r["value"], "src": r["short"]})
    return out
