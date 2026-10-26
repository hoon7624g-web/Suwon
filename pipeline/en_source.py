"""The Korean side of the English pages: what each English record was translated from, and its hash.

tools/en_content.py prepare writes these items as translation batches; pipeline/en_site.py recomputes them at build
time from the current Korean data. A record whose stored `ko_hash` differs from the hash of the current Korean item
was translated from older Korean text: it is stale and its English page is not built (the Korean page is the only
version until the record is translated again).

Also here: English road-name / lot addresses from the Korean address and the city's configuration (address_en).
Names are romanized by pipeline.romanize (Revised Romanization, MCST rules), imported from there by every caller.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .city import NATIONAL_PROVIDER_SHORT
from .romanize import _ADMIN, _admin, _rr_cap, _syllables, romanize
from .schema import FACT_LABELS, FIT_ORDER, FACT_ORDER
from .slugs import YEAR_PREFIX, series_slug
from .textutil import display_address, display_value, series_key, squash_ws

CONFLICT_NOTE = "Sources differ — call before visiting"
EVENT_CONFLICT_NOTE = "Sources differ — check with the organizer before visiting"
URL_KEYS = ("homepage", "reservationurl")  # shown as links from the Korean data, nothing to translate

# ------------------------------------------------------------------ English address (road-name / lot address)
_ROAD = re.compile(r"^(?P<base>[가-힣]+?)(?P<num>[0-9][0-9.]*)?(?P<sfx>대로|로|길)$")
# what follows the 시·도, the 시 and the 구·군 (City.parse_address reads those): the road-name form
# '[읍·면] [리] <road>[ N번길] <no>[ (<동>)]' — the bracket a 동 (법정동 'N가' kept whole) or 'OO로N가' — …
_ADDR = re.compile(
    r"^(?:(?P<em>[가-힣]+[읍면])\s+)?(?:(?P<ri>[가-힣0-9]+리)\s+)?"
    r"(?P<road>[가-힣]+[0-9.]*(?:대로|로|길))(?:\s?(?P<rn>\d+)번길)?\s?(?P<no>\d+(?:-\d+)?)"
    r"(?:\s?\((?P<dong>[가-힣0-9]+동(?:[0-9]+가)?|[가-힣]+로[0-9]+가)\))?$")
# … or the lot form '[읍·면] <리·동>[ [산]<no>]'
_LOT = re.compile(r"^(?:(?P<em>[가-힣]+[읍면])\s*)?(?:(?P<ri>[가-힣0-9]+[리동])"
                  r"(?:\s+(?P<san>산)?(?P<no>\d+(?:-\d+)?))?)?$")


def _road(word: str) -> str:
    """'한빛공원1길' -> 'Hanbitgongwon 1-gil'; a numbered branch of a road keeps that road's name whole:
    '동성로2길' -> 'Dongseong-ro 2-gil'."""
    m = _ROAD.match(word)
    sfx = {"대로": "daero", "로": "ro", "길": "gil"}[m.group("sfx")]
    if m.group("num") and _ROAD.match(m.group("base")) and m.group("base").endswith("로"):
        return f"{_road(m.group('base'))} {m.group('num')}-{sfx}"
    base = _rr_cap(m.group("base"))
    return f"{base} {m.group('num')}-{sfx}" if m.group("num") else f"{base}-{sfx}"


def _unit(word: str) -> str:
    """An administrative name with its unit hyphenated: '한빛동' -> 'Hanbit-dong', '한빛동1가' -> 'Hanbit-dong 1-ga',
    '한빛구' -> 'Hanbit-gu', '한빛시' -> 'Hanbit-si'."""
    if len(word) >= 2 and _syllables(word) and word[-1] in _ADMIN:
        return _admin(word)
    return romanize(word, admin=frozenset({word}))


def official_address(addr_en: str | None, address, city) -> str:
    """The TourAPI English address of the matched item, only when it states our Korean address: the same numbers
    (road and building numbers, lot numbers, '2가') and the city's English tail at the end. Review 2026-10-16: the
    English service gave a road address for our lot address ('180, Universiad-ro' for '노변동 650'), dropped the
    '계산동2가' bracket, or still named the 도 a 군 left ('…, Gunwi-gun, Gyeongsangbuk-do'); then the address is
    romanized from ours (address_en) or written by the translator."""
    en = squash_ws(addr_en)
    if not en:
        return ""
    tail = address_tail(city) if city is not None else ()
    if tail and not en.rstrip(". ").endswith(tail[-1]):
        return ""
    ko = display_address(address.get("value") if isinstance(address, dict) else address)
    nums = lambda t: sorted(re.findall(r"\d+", t))
    return en if nums(en) == nums(ko) else ""


def address_tail(city) -> tuple[str, ...]:
    """The English names an address ends with after its 구·군: the 시 when it is not the 시·도 itself (romanized with
    its unit, 'Hanbit-si'), then the 시·도: site.json region_admin_en, or — for a metropolitan city, whose 시·도 is the
    city — region_en (else the romanized region). A 시·도 without an English name is left out, never guessed."""
    out = []
    if city.locality and city.locality != city.region_admin:
        out.append(_unit(city.locality))
    admin_en = squash_ws(city.raw.get("region_admin_en"))
    if not admin_en and city.locality == city.region_admin:
        admin_en = city.region_en or romanize(city.region)
    if admin_en:
        out.append(admin_en)
    return tuple(out)


def address_en(address: str | None, city) -> str:
    """'<도> 한빛시 한빛공원1길 26' -> '26 Hanbitgongwon 1-gil, Hanbit-si, <region_admin_en>';
    '<광역시> 한빛구 동성로2길 80 (한빛동1가)' -> '80 Dongseong-ro 2-gil (Hanbit-dong 1-ga), Hanbit-gu, <region_en>'.
    The start is read by City.parse_address (the 시·도 or an alias; the 시, which must be written when it is not the
    시·도; a 구·군 of `districts`); the English tail is address_tail. '' when the address is not this city's or has
    parts this does not read (floors, business names, '일원' …): the translator writes it."""
    a = display_address(address)
    if not a:
        return ""
    pa = city.parse_address(a)
    if not pa.admin:
        return ""
    head = a[:len(a) - len(pa.rest)]
    if city.locality != city.region_admin and city.locality not in head:
        return ""
    tail = ([_unit(pa.district)] if pa.district else []) + list(address_tail(city))
    m = _ADDR.match(pa.rest)
    if m:
        road = _road(m.group("road"))
        if m.group("rn"):
            road += f" {m.group('rn')}beon-gil"
        parts = [f"{m.group('no')} {road}" + (f" ({_unit(m.group('dong'))})" if m.group("dong") else "")]
        parts += [_unit(m.group(k)) for k in ("ri", "em") if m.group(k)]
        return ", ".join(parts + tail)
    m = _LOT.match(pa.rest)
    if m and (m.group("em") or m.group("ri")):
        parts = []
        if m.group("ri"):
            lot = (("San " if m.group("san") else "") + m.group("no") + " ") if m.group("no") else ""
            parts.append(lot + _unit(m.group("ri")))
        if m.group("em"):
            parts.append(_unit(m.group("em")))
        return ", ".join(parts + tail)
    return ""


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _load(data: Path, name: str, default=None):
    path = data / name
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def _name_table(data: Path, places: list[dict]) -> dict:
    """place id -> names.json row (official English name or romanized), romanized when names.json lacks it."""
    table = _load(data, "en/names.json", {}) or {}
    out = {}
    for p in places:
        row = table.get(p["id"]) or {}
        if row.get("name_ko") != p["name"]:  # renamed since names.json was written: romanize again
            row = {}
        rr = romanize(p["name"])
        out[p["id"]] = {"name_en": row.get("name_en") or rr, "name_en_source": row.get("name_en_source") or "romanized",
                        "addr_en": row.get("addr_en") or ""}
    return out


class Glossary:
    """Names that appear inside Korean text, with the English form translators must use (mentions)."""

    def __init__(self, places: list[dict], names_en: dict, courses: list[dict]):
        terms: dict[str, str] = {}
        for p in places:
            for n in [p["name"], *(p.get("alternate_names") or [])]:
                n = squash_ws(n)
                if len(n) >= 3 and n not in terms:
                    terms[n] = names_en[p["id"]]["name_en"]
        areas = set()
        for p in places:
            for tok in re.findall(r"[가-힣0-9]+(?:동|읍|면|리)(?=[\s,)]|$)", display_address((p.get("facts") or {}).get("address"))):
                if _syllables(tok) and len(tok) >= 3:  # 2-letter areas ('금동') also occur inside other words
                    areas.add(tok)
        for a in sorted(areas):
            terms.setdefault(a, _admin(a))
        self.terms = dict(sorted(terms.items(), key=lambda kv: -len(kv[0])))

    def mentions(self, texts: list[str], skip: tuple = ()) -> list[dict]:
        # '한국관' (a place) inside '한국관광공사' (the national provider) names no place
        hay = " ".join(t for t in texts if t).replace(NATIONAL_PROVIDER_SHORT, " ")
        found, taken = [], []
        for ko, en in self.terms.items():
            if ko in skip or ko not in hay:
                continue
            if any(ko in t for t in taken):  # '한빛섬' inside an already listed '한빛섬해수욕장'
                if hay.count(ko) <= sum(hay.count(t) for t in taken if ko in t):
                    continue
            taken.append(ko)
            found.append({"ko": ko, "en": en})
        return found


def conflict_alternatives(p: dict, key: str) -> list[dict]:
    """The other sources' values of one fact that differ from it, in the order the translation batches carry them
    (a translated record's facts[key].alternatives[i] is the translation of item i)."""
    value = display_value(key, (p.get("facts") or {}).get(key))
    return [a for a in ((p.get("fact_alternatives") or {}).get(key) or [])
            if a.get("relation") != "also" and squash_ws(str(a.get("value") or ""))
            and squash_ws(display_value(key, a["value"])) != squash_ws(value)]


def _fact_rows(p: dict, names_row: dict, city) -> list[dict]:
    facts = p.get("facts") or {}
    rows = []
    for key in [k for k in (*FACT_ORDER, *FIT_ORDER) if k in facts] + [k for k in facts if k not in FACT_ORDER + FIT_ORDER]:
        if key in URL_KEYS:
            continue
        value = display_value(key, facts.get(key))
        alts = (p.get("fact_alternatives") or {}).get(key) or []
        conflict = conflict_alternatives(p, key)
        also = [a for a in alts if a.get("relation") == "also" and squash_ws(str(a.get("value") or ""))]
        if not value and not conflict:
            continue
        row = {"key": key, "label": FACT_LABELS.get(key, key), "value": value}
        if conflict:
            row["alternatives"] = [{"value": display_value(key, a["value"]), "provider": a.get("provider", "")}
                                   for a in conflict]
        if also:
            row["also"] = [{"value": display_value(key, a["value"]), "provider": a.get("provider", "")} for a in also]
        if key == "address":
            row["address_en_candidate"] = (official_address(names_row.get("addr_en"), facts.get(key), city)
                                           or address_en(facts.get(key), city))
        rows.append(row)
    return rows


def place_item(p: dict, names_row: dict, gloss: Glossary, indexable: bool, *, city) -> dict:
    """city: the data's City (pipeline.city), for the English address candidate (address_en)."""
    item = {"id": p["id"], "slug": p.get("slug", ""), "kind": p["kind"], "category": p.get("category", ""),
            "indexable": indexable, "name": p["name"], "name_en": names_row["name_en"],
            "name_en_source": names_row["name_en_source"], "alternate_names": p.get("alternate_names") or [],
            "facts": _fact_rows(p, names_row, city), "summary": squash_ws(p.get("summary")),
            "details": [{"heading": squash_ws(d.get("heading")), "text": squash_ws(d.get("text"))}
                        for d in p.get("details") or []],
            "faq": [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a"))} for f in p.get("faq") or []]}
    texts = [item["summary"], *[d["heading"] + " " + d["text"] for d in item["details"]],
             *[f["q"] + " " + f["a"] for f in item["faq"]]]
    item["mentions"] = gloss.mentions(texts, skip=(p["name"], *(p.get("alternate_names") or []))) if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("name", "facts", "summary", "details", "faq")})
    return item


def guide_item(g: dict, by_slug: dict, names_en: dict, gloss: Glossary) -> dict:
    items = []
    for it in g.get("items") or []:
        p = by_slug.get(it.get("place_slug"))
        items.append({"place_slug": it.get("place_slug", ""), "place_name": p["name"] if p else "",
                      "place_name_en": names_en[p["id"]]["name_en"] if p else "", "reason": squash_ws(it.get("reason"))})
    item = {"id": g["id"], "slug": g.get("slug", ""), "label": squash_ws(g.get("label")), "title": squash_ws(g.get("title")),
            "summary": squash_ws(g.get("summary")),
            "body": [{"heading": squash_ws(b.get("heading")), "text": squash_ws(b.get("text"))} for b in g.get("body") or []],
            "items": items, "faq": [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a"))} for f in g.get("faq") or []],
            "sources": [{"name": squash_ws(s.get("name")), "url": s.get("url", "")} for s in g.get("sources") or []]}
    texts = [item["title"], item["summary"], *[b["heading"] + " " + b["text"] for b in item["body"]],
             *[i["reason"] for i in items], *[f["q"] + " " + f["a"] for f in item["faq"]]]
    item["mentions"] = gloss.mentions(texts) if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("label", "title", "summary", "body", "items", "faq", "sources")})
    return item


def course_item(c: dict, by_slug: dict, names_en: dict, gloss: Glossary) -> dict:
    stops = []
    for s in c.get("stops") or []:
        p = by_slug.get(s.get("place_slug"))
        stops.append({"name": squash_ws(s.get("name")), "note": squash_ws(s.get("note")),
                      "place_slug": s.get("place_slug") or "", "place_name_en": names_en[p["id"]]["name_en"] if p else "",
                      "name_rr": romanize(s.get("name"))})
    item = {"id": c["id"], "slug": c.get("slug", ""), "name": display_value("course_name", c.get("name")),
            "group": squash_ws(c.get("group")), "duration": squash_ws(c.get("duration")),
            "summary": squash_ws(c.get("summary")), "stops": stops}
    item["mentions"] = gloss.mentions([item["name"], item["summary"], *[s["name"] + " " + s["note"] for s in stops]]) \
        if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("name", "group", "duration", "summary", "stops")})
    return item


EVENT_FIELDS = ("name", "period_text", "place_name", "address", "fee", "playtime", "sponsor", "tel")


def event_series(events: list[dict], all_events: list[dict] | None = None) -> list[dict]:
    """Series as pipeline.build.event_series groups them, dated series only, from the published records (not a
    duplicate, not excluded) in the build's order (start date, then name). The URL slug is the same rule
    (slugs.series_slug): every series slug stored in events.json (all_events, default `events`) is reserved first,
    so the Korean page /events/<slug>/ and the English record share it."""
    taken = {squash_ws(x.get("slug")) for x in (events if all_events is None else all_events) if squash_ws(x.get("slug"))}
    published = sorted((ev for ev in events if ev.get("status") == "published" and not ev.get("duplicate_of")
                        and not ev.get("exclude")), key=lambda e: (e.get("start_date") or "9999", e.get("name", "")))
    groups: dict[str, list] = {}
    for ev in published:
        groups.setdefault(series_key(ev), []).append(ev)
    out = []
    for key, evs in groups.items():
        dated = sorted((x for x in evs if x.get("start_date")), key=lambda x: (x["start_date"], x.get("end_date") or ""),
                       reverse=True)
        if not dated:
            continue
        newest = dated[0]
        undated = [x for x in evs if not x.get("start_date")]
        name = next((squash_ws(x["series"]) for x in [newest, *evs] if squash_ws(x.get("series"))), "") \
            or YEAR_PREFIX.sub("", squash_ws(newest["name"]))
        slug = series_slug(evs, name, taken)
        out.append({"key": key, "name": name, "slug": slug, "newest": newest, "editions": dated + undated})
    return out


def event_item(sr: dict, gloss: Glossary, *, city) -> dict:
    """city: the data's City (pipeline.city), for the English address candidate (address_en)."""
    ev = sr["newest"]
    newest = {"id": ev["id"]}
    for f in EVENT_FIELDS:
        v = squash_ws(ev.get(f))
        if f == "address":
            v = display_address(v)
        if f == "playtime":
            v = display_value("playtime", v)
        if v:
            newest[f] = v
    if newest.get("address"):
        newest["address_en_candidate"] = address_en(ev.get("address"), city)
    if ev.get("summary"):
        newest["summary"] = squash_ws(ev["summary"])
    newest["notes"] = [squash_ws(n) for n in ev.get("notes") or [] if squash_ws(n)]
    alts = {f: [{"value": squash_ws(a.get("value")), "provider": squash_ws(a.get("source_name"))} for a in vals]
            for f, vals in (ev.get("alternatives") or {}).items() if vals}
    program = next((x for x in sr["editions"] if x.get("highlights")), None)
    usual = []
    for x in sr["editions"]:
        if not x.get("start_date") and "매년" in str(x.get("period_text", "")):
            usual.append({"text": squash_ws(x["period_text"]), "place": squash_ws(x.get("place_name"))})
    usual += [{"text": squash_ws(u.get("text")), "place": squash_ws(u.get("place"))}
              for x in sr["editions"] for u in x.get("usual") or [] if squash_ws(u.get("text"))]
    editions = [{"id": x["id"], "name": squash_ws(x.get("name")), "period_text": squash_ws(x.get("period_text")),
                 "place_name": squash_ws(x.get("place_name"))} for x in sr["editions"] if x is not ev]
    sources: list[str] = []
    for x in sr["editions"]:
        names_ = [x.get("source_name"), *[a.get("name") for a in x.get("also_sources") or []],
                  *[u.get("source_name") for u in x.get("usual") or []],
                  *[a.get("source_name") for vals in (x.get("alternatives") or {}).values() for a in vals]]
        for s in names_:
            s = squash_ws(s)
            if s and s not in sources:
                sources.append(s)
    item = {"id": sr["slug"], "series_name": sr["name"], "newest": newest, "alternatives": alts,
            "highlights": [squash_ws(h) for h in (program or {}).get("highlights") or [] if squash_ws(h)],
            "program_notes": [squash_ws(n) for n in (program or {}).get("notes") or [] if squash_ws(n)]
            if program is not ev else [],
            "usual": usual, "editions": editions, "sources": sources}
    texts = [sr["name"], *[v for v in newest.values() if isinstance(v, str)], *item["highlights"],
             *[u["text"] + " " + u["place"] for u in usual], *[e["name"] + " " + e["place_name"] for e in editions]]
    item["mentions"] = gloss.mentions(texts) if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("series_name", "newest", "alternatives", "highlights",
                                                  "program_notes", "usual", "editions", "sources")})
    return item


def current_hashes(data: Path, *, city) -> dict:
    """The ko_hash of every item `prepare` would write from the current Korean data in `data`:
    {"places": {id: hash}, "guides": {id: hash}, "courses": {id: hash}, "events": {series slug: hash}}.
    Same filters as prepare: published places that are not duplicates, published guides and courses, and the
    dated event series of published records. Mentions (the glossary) are not part of a hash, so none is built.
    city: the City of data/site.json (pipeline.city.of)."""
    places_all = _load(data, "places.json", []) or []
    places = [p for p in places_all if p.get("status") == "published" and not p.get("duplicate_of")]
    names_en = _name_table(data, places)
    by_slug = {p["slug"]: p for p in places if p.get("slug")}
    guides = [g for g in _load(data, "guides.json", []) or [] if g.get("status") == "published"]
    courses = [c for c in _load(data, "courses.json", []) or [] if c.get("status") == "published"]
    events = _load(data, "events.json", []) or []
    return {"places": {p["id"]: place_item(p, names_en[p["id"]], None, True, city=city)["ko_hash"] for p in places},
            "guides": {g["id"]: guide_item(g, by_slug, names_en, None)["ko_hash"] for g in guides},
            "courses": {c["id"]: course_item(c, by_slug, names_en, None)["ko_hash"] for c in courses},
            "events": {sr["slug"]: event_item(sr, None, city=city)["ko_hash"] for sr in event_series(events)}}
