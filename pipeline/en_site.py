"""Every language version besides Korean, built by one engine next to the Korean pages.

English (/en/), Japanese (/ja/), Simplified and Traditional Chinese (/zh-hans/, /zh-hant/), German (/de/), French
(/fr/), Spanish (/es/) and Russian (/ru/). What differs by language is the locale table (pipeline/locales.py, English
being one locale) and the words the pages print (UIText: English's in pipeline/intl_text.py, every other version's
translated from those into data/<city>/<code>/strings.json 'chrome.<key>'). The module keeps its first name and
its English helpers (en_slug, sentences_en, brief_en, load …) for the code and tests that import them.

Switch: a version exists only when site.json `languages` lists its code and data/<city>/<code>/places.json exists
(the sample data and a city without translations have neither: no /<code>/, no hreflang, no language menu), and its
UI words are complete. City words come from site.json through pipeline.city and locales.names: the site's and the
city's names in the language (site_name_en, region_en, `locales`), the province (region_admin_en / locales admin), the
city's providers (English: locality_en, source.name_en; another version: its strings 'provider:<Korean name>'), the
list hubs (list_hubs), the regions (anchors, far, none — strings REGIONS.<region key>, else a 구·군 transcribed) and
official_domains (a course or source is called official only on one of those sites).

A version's records are translations of OUR Korean data (tools/en_content.py prepare → check → merge --lang <code>).
Each stores the hash of the Korean item it was translated from (`ko_hash`, pipeline/en_source.py — the same hash for
every language); this module recomputes that hash from the current Korean data. A stale record (the Korean changed
since the translation) is not rendered at all: the Korean page is then the only version, and the build prints the
count. Nothing here adds a fact: every value on a page is the language's record value, a number from the Korean data
(dates, distances, counts, phone numbers, coordinates), or a label from data/<city>/<code>/strings.json.

Routes (per version, <home> = /en/, /ja/ …):
    <home> · <home>places/ · <home>food/ · <home>stays/ · <home>places/<slug>/ · <home>guides/ (+ /<slug>/) ·
    <home>courses/ (+ /<slug>/) · <home>events/ (#<series slug>) · <home>about/ · <home>search/
Slugs: every version uses the slug the Korean record stores (ASCII, CLAUDE.md 2): /places/<slug>/ and
<home>places/<slug>/ are the same place, a guide or course likewise, and an event series' anchor is its Korean page's
series slug — so a slug never changes while its record stays and no version makes one up.
Index rule: a place page is indexable only when its Korean page is (schema.index_status, production) and its record
is current; otherwise noindex and out of sitemap.xml / llms.txt (still listed). hreflang: ko, every version the page
has (en, ja, zh-Hans, zh-Hant, de, fr, es, ru) and x-default (= Korean), the same list on every page of the set
(Intl.alternates). The language menu (templates/_lang.html.j2, Intl.menu) links each version's counterpart page
(the search pages pair too, without hreflang: Site.menu_twins), else that version's list of the same kind (guides,
courses, events, the place's list; else its home) with a visible 'not translated' note in that version's words
(Site.menu_link, Locale.untranslated); it lists only the versions this build has. A published Korean record a version
has no translation of is counted (render stats 'untranslated', a build warning, build_public's intl_untranslated).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from markupsafe import Markup, escape

from . import art, ask, booking, intl_text, jsonld, media, notices, present, relations
from . import locales as LC
# a cited booking site's own page in a reader's language (QA 2026-10-15 SRC-05b): moved to booking.py with the booking
# buttons (2026-10-16), so present and en_site share it
from .booking import OFFICIAL_ENTRY, official_entry  # noqa: F401
from .en_source import CONFLICT_NOTE, EVENT_CONFLICT_NOTE, conflict_alternatives, current_hashes, event_series
from .maplinks import DEFAULT_TMAP_SCHEME, build_links, google_transit_url
from .romanize import HANGUL, romanize
from .schema import (FACT_ALIASES, GEO_PROVIDER, KEY_FACTS, KEY_FACTS_BY_CATEGORY, alias_holds, designations,
                     geo_provider, node_types, parking_seats_half, schema_type)
from .slugs import COURSE_GROUP_IDS, SLUG_MAX_LEN, ascii_core
from .textutil import (display_address, extract_phones, link_url, phone_intl, phone_intl_shown, url_domain, web_text,
                       web_url)

EN = LC.get("en")
EN_HOME = "/en/"
KINDS = ("attraction", "food", "stay")
# list pages: the path under the version's home and the Korean counterpart; the hub guide of a list is site.json
# list_hubs[kind] (Site.hub_ids)
LIST_PAGES = {"attraction": {"seg": "places/", "ko": "/places/"},
              "food": {"seg": "food/", "ko": "/food/"},
              "stay": {"seg": "stays/", "ko": "/stays/"}}
NAV_KEYS = (("nav_attraction", "places/"), ("nav_food", "food/"), ("nav_stay", "stays/"), ("guides", "guides/"),
            ("courses", "courses/"), ("events", "events/"))
CURRENT = {"place-attraction": "places/", "places": "places/", "place-food": "food/", "list-food": "food/",
           "place-stay": "stays/", "list-stay": "stays/", "guide": "guides/", "guides": "guides/",
           "course": "courses/", "courses": "courses/", "events": "events/", "search": "search/"}
# short provider names (present.slot_provider) as UIText keys: the national ones here; the city's own come from
# site.json (English: locality -> locality_en, source.name -> source.name_en) or the version's strings
# 'provider:<Korean name>' (Site.short_name)
SHORT_PROVIDER = {"한국관광공사": "provider_kto", "공식 홈페이지": "provider_official"}
# key-fact slots: the label key in strings.json (the Korean slot names: present.SLOT_LABEL)
SLOT_STRING = {"hours": "TITLE_LABELS.usetime", "closed": "FACT_LABELS.restdate", "fee": "STATUS_PREFIX.usefee",
               "parking": "FACT_LABELS.parking", "tel": "INDEX_GROUP_LABELS.phone", "menu": "FACT_LABELS.menu",
               "checkin": "FACT_LABELS.checkin", "checkout": "FACT_LABELS.checkout", "rooms": "STATUS_PREFIX.roomcount"}
ABBR = EN.abbr
SENT_SPLIT = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(\[])")
TIME_RANGE = re.compile(r"\d{1,2}:\d{2}\s*[–-]\s*\d{1,2}:\d{2}")
WEEKDAY = re.compile(r"\b(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)days?\b")
HOURS_KEYS = ("usetime", "usetime_restdate")
TIME_TOKEN = re.compile(r"\d{1,2}:\d{2}")
KO_TIME_TOKEN = re.compile(r"\d{1,2}:\d{2}|\d{1,2}\s*시(?!간)(?:\s*\d{1,2}\s*분)?")
SPAN_EDGE = " \t/／,，、;；:：-–.。"
# the '휴무일:' label in front of a closed part as the translations write it (present._closed_part drops the Korean one)
CLOSED_LABEL = {
    "en": r"(?:closing|closed)\s+days?", "ja": r"(?:休業日|定休日|公休日|休館日)", "zh-hans": r"(?:公休日|休息日|休业日)",
    "zh-hant": r"(?:公休日|休息日|休業日)", "de": r"Ruhetage?", "fr": r"jours?\s+de\s+fermeture",
    "es": r"d[ií]as?\s+de\s+cierre", "ru": r"выходн(?:ой|ые)(?:\s+дни|\s+день)?"}
DURATION_ORDER = {"당일": 0, "1박 2일": 1, "2박 3일": 2}   # course groups: day trip, one night, two nights, the rest
BRIEF_MAX = 40
CELL_MAX = 48


# ---------------------------------------------------------------------------------------------- small helpers
def squash_ws(text: str | None) -> str:
    """textutil.squash_ws, but a narrow no-break space stays: French and Russian write thousands with it
    ('3\u202f000 wons'), and a line never breaks there (the data has none elsewhere)."""
    return re.sub(r"[^\S\u202f]+", " ", text or "").strip()


SLUG_TAIL = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}


def en_slug(text: str | None, max_len: int = SLUG_MAX_LEN) -> str:
    """'Eunpa Lake Park' -> 'eunpa-lake-park': slugs.ascii_core (lowercase ASCII words joined by '-', 'Modern–Old Town'
    -> 'modern-old-town', cut at a word boundary) without a dangling 'and' / 'the' …"""
    out = [w for w in ascii_core(text, max_len).split("-") if w]
    while len(out) > 1 and out[-1] in SLUG_TAIL:
        out.pop()
    return "-".join(out) or "item"


def sentences_en(text: str | None) -> list[str]:
    """English sentences; 'No. 183', 'Dr. Lee' and the like do not end one."""
    out: list[str] = []
    for part in SENT_SPLIT.split(squash_ws(text)):
        if out and re.search(rf"\b(?:{'|'.join(ABBR)})\.$", out[-1]):
            out[-1] = f"{out[-1]} {part}"
        elif part:
            out.append(part)
    return out


def sentences(text: str | None, loc: LC.Locale) -> list[str]:
    return sentences_en(text) if loc.code == "en" else loc.sentences(text)


def dist_en(m) -> str:
    """'430 m' (rounded to 10 m), '2.4 km'; '' for unknown."""
    return EN.dist(m)


def en_date(iso: str | None) -> str:
    """'2026-10-09' -> 'October 9, 2026'."""
    return EN.date(iso)


def en_md(iso: str | None) -> str:
    """'2026-10-09' -> 'Oct 9'."""
    return EN.md(iso)


def area_en(area: str | None) -> str:
    """'한빛동' -> 'Hanbit-dong', '한빛동1가' -> 'Hanbit-dong 1-ga' (Revised Romanization, the administrative unit
    hyphenated: locales.area_name)."""
    return LC.area_name(area, "en")


def district_en(district: str | None) -> str:
    """A 구·군 of site.json districts in Revised Romanization: '한빛구' -> 'Hanbit-gu', '누리군' -> 'Nuri-gun'
    (locales.district_name)."""
    return LC.district_name(district, "en")


def no_hangul(text: str) -> str:
    return "" if HANGUL.search(text or "") else (text or "")


def lines_html(text: str | None) -> Markup:
    return Markup("<br>").join(escape(x) for x in str(text or "").split("\n"))


def _segments(value: str, timeish: bool) -> list[tuple[str, str]]:
    """A stored value cut into (header, text) parts at line breaks and ' / '. A '[Header]' line labels the part
    after it: hours read 'Summer (March–October) 09:00–18:00'; other values keep the header apart (fees: 'Adults
    500 won' under 'Individuals')."""
    parts = [p.strip() for p in re.split(r"\s*\n\s*|\s+/\s+", value or "") if p.strip()]
    out, head = [], ""
    for p in parts:
        m = re.fullmatch(r"\[(.+)\]", p)
        if m:
            head = m.group(1).strip()
            continue
        p = re.sub(r"^[-•※]\s*", "", p)
        out.append((("", f"{head} {p}") if timeish and head else (head, p)))
        if timeish:
            head = ""
    return out


def _clauses(t: str, loc: LC.Locale) -> list[str]:
    if loc.code == "en":
        cs = [re.sub(r"^(?:and|or)\s+", "", c.strip()).rstrip(".,;") for c in re.split(r"[,;]\s+|\.\s+|\s+and\s+", t)]
    elif loc.cjk:
        cs = [c.strip().rstrip("。、，；") for c in re.split(r"[、，；。]\s*", t)]
    else:
        conj = {"de": "und|oder", "fr": "et|ou", "es": "y|o", "ru": "и|или"}.get(loc.code, "and")
        cs = [re.sub(rf"^(?:{conj})\s+", "", c.strip()).rstrip(".,;") for c in
              re.split(rf"[,;]\s+|\.\s+|\s+(?:{conj})\s+", t)]
    return [c for c in cs if c]


def _weekday(text: str, loc: LC.Locale) -> bool:
    if loc.code == "en":
        return bool(WEEKDAY.search(text))
    return any(w[:3].lower() in text.lower() for w in loc.weekdays) if not loc.cjk else \
        any(w in text for w in loc.weekdays) or bool(re.search(r"[月火水木金土日]曜", text))


def _reduce(text: str, prefer_day: bool = False, loc: LC.Locale = EN) -> str:
    """A short main part of one segment: the whole when short; else without a trailing '(…)', else the first
    clause (the one naming a weekday for closed days), else the time range it states; else the whole segment
    (never cut inside a word or number)."""
    t = squash_ws(text)
    limit = BRIEF_MAX // 2 if loc.cjk else BRIEF_MAX
    if len(t) <= limit:
        return t
    s = t
    while re.search(r"\s*[(（][^()（）]*[)）]$", s) and len(s) > limit:
        s = re.sub(r"\s*[(（][^()（）]*[)）]$", "", s).strip()
    if len(s) <= limit and len(s) >= (3 if loc.cjk else 5):
        return s
    clauses = _clauses(t, loc)
    if prefer_day:
        day = next((c for c in clauses if _weekday(c, loc) and len(c) <= limit), "")
        if day:
            return day[0].upper() + day[1:]
    if clauses and (3 if loc.cjk else 5) <= len(clauses[0]) <= limit:
        return clauses[0]
    m = TIME_RANGE.search(t)
    if m:
        return m.group(0)
    return t


def brief_en(key: str, value: str | None, loc: LC.Locale = EN) -> dict:
    """{main, sub, more} for a key-fact tile or a list cell (the facts card prints the whole value)."""
    v = squash_ws(value) if "\n" not in str(value or "") else str(value).strip()
    if not v:
        return {"main": "", "sub": "", "more": False}
    timeish = key in ("usetime", "usetime_restdate", "openperiod", "checkin", "checkout")
    if key == "menu":
        if loc.cjk:
            items = [x.strip() for x in re.split(r"[、，,]\s*(?!\d{3}(?!\d))|\n", v) if x.strip()]
            sep, room = loc.list_sep, 16
        else:
            items = [x.strip() for x in re.split(r",(?!(?<=\d,)\d{3}(?!\d))\s*|\n", v) if x.strip()]   # never at a thousands comma
            sep, room = ", ", 32
        main, k = items[0], 1
        while k < len(items) and len(main) + len(sep) + len(items[k]) <= room:
            main += sep + items[k]
            k += 1
        return {"main": cap(main), "sub": "", "more": k < len(items)}
    segs = _segments(v, timeish)
    if not segs:
        return {"main": squash_ws(v), "sub": "", "more": False}
    limit = BRIEF_MAX // 2 if loc.cjk else BRIEF_MAX
    if len(segs) == 1 and len(segs[0][1]) <= limit and not segs[0][0]:
        return {"main": segs[0][1], "sub": "", "more": False}
    head, first = segs[0]
    main = _reduce(first, key == "restdate", loc)
    sub = head
    used = 1
    if not sub and len(segs) > 1 and timeish:
        nxt = _reduce(segs[1][1], False, loc)
        if len(nxt) <= limit:
            sub, used = nxt, 2
    whole = squash_ws(" ".join(f"{h} {t}".strip() for h, t in segs))
    shown = squash_ws(f"{sub} {main}") if head else squash_ws(f"{main} {sub}")
    return {"main": cap(main), "sub": cap(sub),
            "more": used < len(segs) or main != squash_ws(first) or len(shown) < len(whole) - 2}


def cap(text: str) -> str:
    """A tile's main part starts with a capital ('closed on the second Monday' -> 'Closed on …')."""
    return text[:1].upper() + text[1:] if text[:1].islower() else text


def _unwrap(text: str) -> str:
    """present._closed_part for a translated part: separators at both ends off, a bracket pair around the whole
    goes, a bracket left unpaired by the cut goes."""
    t = text.strip(SPAN_EDGE)
    for o, c in (("(", ")"), ("（", "）")):
        if t.startswith(o) and t.endswith(c) and t.count(o) == t.count(c) == 1:
            t = t[1:-1].strip(SPAN_EDGE)
        while t.endswith(c) and t.count(c) > t.count(o):
            t = t[:-1].rstrip(SPAN_EDGE)
        while t.startswith(o) and t.count(o) > t.count(c):
            t = t[1:].lstrip(SPAN_EDGE)
    return t


def closed_span(ko_value, value, loc: LC.Locale = EN) -> dict | None:
    """The closed-day part of a translated hours value, found from the Korean parse instead of from words of the
    language (the hours value is translated whole, closed day included): present.brief_hours finds the Korean
    closed part, which follows the value's last time; the translation keeps the times (tools/en_content.py parity
    compares their sets; the count is checked here), so its closed part is what follows its own last time (after the
    bracket that time sits in) — in a value without times, its last '/'-part, as in the Korean. The '휴무일:' label of
    the language goes, as the Korean one does. None when the Korean value has no closed part; {start, text}; {start: -1, why} when the two cannot be aligned
    (pipeline.validate reports it as an error)."""
    ko, tr = str(ko_value or ""), str(value or "")
    _, ko_closed = present.brief_hours(ko)
    if not ko_closed:
        return None
    ko_t, tr_t = list(KO_TIME_TOKEN.finditer(ko)), list(TIME_TOKEN.finditer(tr))
    if ko_t and ko.rfind(re.split(r"[\s,(]", ko_closed.strip())[0]) < ko_t[-1].end():
        return {"start": -1, "text": "", "why": "the Korean closed day is not after the last time"}
    if ko_t:
        if len(tr_t) != len(ko_t):
            return {"start": -1, "text": "", "why": f"{len(ko_t)} times in the Korean, {len(tr_t)} in the translation"}
        start, ko_start = _after_time(tr, tr_t[-1].end()), _after_time(ko, ko_t[-1].end())
    else:
        cut = r"\s*[/／]\s*|\n"
        ko_s, tr_s = [x for x in re.split(cut, ko) if x.strip()], [x for x in re.split(cut, tr) if x.strip()]
        if len(ko_s) == len(tr_s) == 1 and _key(ko_closed) == _key(ko):
            return {"start": tr.find(tr_s[0]), "text": tr_s[0].strip()}   # the whole value is the closed-day text
        if len(ko_s) < 2 or len(ko_s) != len(tr_s):
            return {"start": -1, "text": "", "why": "the '/' parts of the Korean and the translation differ"}
        start, ko_start = tr.rfind(tr_s[-1]), ko.rfind(ko_s[-1])
    # the Korean side decides what the translated tail is: the closed part brief_hours found must be the whole Korean
    # tail, or the bracket that ends it ('외부·정원만 관람 가능 (매주 월요일 휴관)') — anything else is not aligned
    ko_tail = _tail(ko[ko_start:], r"(?:휴무일|휴관일|휴일|정기\s*휴무|쉬는\s*날)")
    tr_tail = re.split(r"\s*※", tr[start:])[0]
    if _key(ko_tail) != _key(ko_closed):
        kb, tb = BRACKET_END.search(ko_tail), BRACKET_END.search(tr_tail)
        if not (kb and _key(kb.group(1)) == _key(ko_closed)):
            return {"start": -1, "text": "", "why": "the Korean closed day is not the whole tail"}
        if not tb:
            return {"start": -1, "text": "", "why": "the Korean closed day is in brackets, the translation's is not"}
        start, tr_tail = start + tb.start(), tb.group(1)
    text = _tail(tr_tail, CLOSED_LABEL[loc.code])
    if not text:
        return {"start": -1, "text": "", "why": "nothing after the last time"}
    return {"start": start, "text": text}


BRACKET_END = re.compile(r"[(（]([^()（）]*)[)）]\s*$")


def _after_time(text: str, end: int) -> int:
    """Where a value's tail starts after its last time: past the bracket that time sits in."""
    head = text[:end]
    if head.count("(") + head.count("（") > head.count(")") + head.count("）"):
        m = re.compile(r"[)）]").search(text, end)
        return m.end() if m else end
    return end


def _tail(text: str, label: str) -> str:
    """A value's tail as a closed-day tile shows it: '※' notes off, separators and a whole bracket off, a leading
    'closed:' label of the language off."""
    t = _unwrap(re.split(r"\s*※", text)[0])
    return _unwrap(re.sub(rf"^{label}\s*[:：]\s*", "", t, flags=re.I))


def _key(text: str) -> str:
    """Two Korean closed-day texts compared without spaces, separators and brackets."""
    return re.sub(r"[\s,/·()（）:：~\-]|및", "", str(text or ""))


def hours_part(ko_value, value, loc: LC.Locale = EN) -> str:
    """A translated hours value without its closed-day part (the Korean hours tile never shows it either)."""
    sp = closed_span(ko_value, value, loc)
    return str(value or "")[:sp["start"]].rstrip(SPAN_EDGE) if sp and sp["start"] > 0 else str(value or "")


def ko_closed_whole(ko_text) -> bool:
    """present.brief_closed shows this Korean closed-day text ('restdate') whole: no sub, nothing left for 'more'."""
    t = " ".join(present.clean_lines(ko_text))
    kb = present.brief_closed(t)
    # brief_closed writes '첫째/셋째' as '첫째, 셋째' and '및' as a comma: compare with the separators made alike
    norm = lambda x: re.sub(r"\s*[,/]\s*|\s+및\s+", ", ", squash_ws(x).strip(" ,/"))
    return bool(kb) and not kb["sub"] and not kb["more"] and norm(kb["main"]) == norm(t)


def closed_whole(value, ko_raw=None) -> str:
    """A translated closed-day value whole, as present.clean_lines reads the Korean: '※' notes off, and the closing
    bracket of the '(전화 문의)' aside the Korean leaves out ('… (call for details)')."""
    t = squash_ws(re.split(r"\s*※", str(value or ""))[0]).strip(" ,/").rstrip(".。")
    if ko_raw and present.ASK_PAREN.search(str(ko_raw)):
        t = re.sub(r"\s*[(（][^()（）]*[)）]$", "", t).strip(" ,/").rstrip(".。")
    return t


def closed_brief(ko_raw, value, loc: LC.Locale = EN) -> dict:
    """The closed-day tile of a 'restdate' value: whole where the Korean tile is whole (never cut inside a list of
    days: 'first and third Sundays'), else brief_en, as the Korean is shortened too."""
    if ko_closed_whole(ko_raw):
        return {"main": cap(closed_whole(value, ko_raw)), "sub": "", "more": False}
    return brief_en("restdate", value, loc)


def _load(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


# a city bus route's own words in Hangul ('급행1', '순환2', '팔공1', '수성6') on the other versions: the kind words
# any Korean city uses in English (the route type), the rest romanized as one word, the number kept ('Palgong 1')
ROUTE_KIND = {"급행": "Express", "순환": "Circular", "간선": "Trunk", "지선": "Branch", "마을": "Village", "심야": "Night"}


def route_name(no) -> str:
    """'급행9-1' -> 'Express 9-1', '팔공1' -> 'Palgong 1', '401' -> '401' (digits and Latin letters as they are)."""
    no = squash_ws(str(no or ""))
    m = re.fullmatch(r"([가-힣]+)\s*(.*)", no)
    if not m:
        return no
    word, rest = m.groups()
    word = ROUTE_KIND.get(word) or romanize(word).replace(" ", "")
    return f"{word} {rest}".strip()


def route_names(text) -> str:
    """'306·403·누리6' -> '306·403·Nuri 6'."""
    return "·".join(route_name(x) for x in str(text or "").split("·"))


def add_filters(env) -> None:
    """Jinja filters of the English helpers (registered by build.make_env; the templates of every version use the
    locale's own methods: loc.md, loc.dist, E.sup …)."""
    env.filters["en_date"] = en_date
    env.filters["route"] = route_name
    env.filters["routes"] = route_names
    env.filters["en_md"] = en_md
    env.filters["edist"] = dist_en
    env.filters["first_sentence_en"] = lambda t: (sentences_en(t) or [""])[0]
    # footnote superscripts: the visible number plus a hidden ' — source n' (fact rows) / ' source n' (chapters)
    env.filters["esup"] = lambda n: Markup(f'<sup class="fn"><span class="vh"> — source </span>{n}</sup>') if n else ""
    env.filters["ecsup"] = lambda n: Markup(f'<sup class="fn"><span class="vh"> source </span>{n}</sup>') if n else ""
    # the Korean `tel` filter for the other versions: call links in the +82 form a caller abroad dials (present.tel_href;
    # nationwide 15xx/16xx numbers keep their digits), official hosts linked to their foreign entry page where there is one
    env.filters["telx"] = lambda t, place="": present.tel_markup(t, place, intl=True)
    # an FAQ answer: the same, but no link starts in its first characters (FAQPage repeats the answer and
    # pipeline.validate compares that head with the page as one run — present.PLAIN_HEAD, as in the guide's answer)
    env.filters["telx_faq"] = lambda t, place="": present.tel_markup(t, place, intl=True, skip=present.PLAIN_HEAD)
    # the visible '+82 …' forms of a line's numbers that answer from abroad (textutil.phone_intl_shown: area codes,
    # mobiles, 070 — not 0507, 15xx/16xx, 080, 060), printed after the whole line on a place page's contact rows
    env.filters["intl_forms"] = lambda line: [x for x in (phone_intl_shown(n) for n in extract_phones(line)) if x]


def title_list(tail: str, loc: LC.Locale = EN) -> list[str]:
    """'jjamppong, kkotgejang (marinated blue crab), bakdae … and bakeries' → ['Jjamppong', 'Kkotgejang', 'Bakdae', …]:
    the items of a guide title's list, glosses in brackets dropped, each capitalised (the home bento's pills)."""
    if loc.code == "en":
        return en_title_list(tail)
    t = re.sub(r"\s*[(（][^)）]*[)）]", "", squash_ws(tail))
    conj = {"de": "und", "fr": "et", "es": "y", "ru": "и"}.get(loc.code)
    rx = r"[、，,]\s*" + (rf"|\s+{conj}\s+" if conj else "")
    return [w[:1].upper() + w[1:] for w in (w.strip() for w in re.split(rx, t)) if w]


def en_title_list(tail: str) -> list[str]:
    words = re.split(r",\s*(?:and\s+)?|\s+and\s+", re.sub(r"\s*\([^)]*\)", "", squash_ws(tail)))
    return [w[:1].upper() + w[1:] for w in (w.strip() for w in words) if w]


# ---------------------------------------------------------------------------------------------- UI words
class UIText:
    """The words one version's pages print. English: pipeline/intl_text.EN; every other version: its
    data/<region>/<code>/strings.json 'chrome.<key>' rows (translations of the English, tools/en_content.py).
    In templates: {{ t.key }} and {{ t.f('key', name=…) }} / {{ t.n('key', count) }} give markup (English is
    written in this repository, so it is printed as it is; a translation is escaped); in Python t.s() / t.sn() give
    plain text (escaped where the page prints it). Plural keys have one form per CLDR category (loc.plural).
    official: whether the site's courses are all from one official site (Site.course_src); when not, a key of
    intl_text.PLAIN prints its '<key>_plain' twin (the same words without 'official')."""

    def __init__(self, loc: LC.Locale, strings: dict[str, str]):
        self.loc = loc
        self.official = True
        if loc.code == "en":
            self._w = intl_text.flat(intl_text.EN)
        else:
            self._w = {k[len("chrome."):]: v for k, v in strings.items() if k.startswith("chrome.") and v}
        self.missing = [k for k in intl_text.keys_for(loc) if not self._w.get(k)]

    def _key(self, key: str) -> str:
        return f"{key}_plain" if not self.official and key in intl_text.PLAIN else key

    def _raw(self, key: str, count: int | None = None) -> str:
        key = self._key(key)
        if count is not None:
            return self._w.get(f"{key}.{self.loc.plural_form(count)}", "")
        return self._w.get(key, "")

    def _m(self, v: str) -> Markup:
        return Markup(v) if self.loc.code == "en" else Markup(escape(v))

    def __getattr__(self, key: str) -> Markup:
        if key.startswith("_"):
            raise AttributeError(key)
        return self._m(self._raw(key))

    def s(self, key: str, **kw) -> str:
        v = self._raw(key)
        return v.format(**kw) if kw else v

    def sn(self, key: str, count: int, **kw) -> str:
        kw.setdefault("n", count)
        return self._raw(key, count).format(**kw)

    def f(self, key: str, **kw) -> Markup:
        return self._m(self._raw(key)).format(**kw)

    def n(self, key: str, count: int, **kw) -> Markup:
        kw.setdefault("n", count)
        return self._m(self._raw(key, count)).format(**kw)

    def forms(self, key: str) -> dict[str, str]:
        """A plural key's forms by CLDR category, for a script that picks one (Intl.PluralRules): {'one': …, 'other': …}."""
        key = self._key(key)
        return {f: self._w[f"{key}.{f}"] for f in self.loc.plural if self._w.get(f"{key}.{f}")}

    def printf(self, key: str) -> str:
        """A '{n}' text as a printf pattern for the shared macros ('+ {n} more' -> '+ %d more')."""
        return self._raw(key).replace("%", "%%").replace("{n}", "%d")

    def search_words(self) -> dict:
        """The site search's words in this version (locales.SEARCH_WORDS; English for a version without its own)."""
        return LC.SEARCH_WORDS.get(self.loc.code) or LC.SEARCH_WORDS["en"]

    def map_words(self) -> str:
        """The words map.js writes, for a version other than English and Korean (data-words on the map box)."""
        return json.dumps({"in": self.s("map_zoom_in"), "out": self.s("map_zoom_out"), "all": self.s("map_whole_course"),
                           "load": self.s("map_loading"), "fail": self.s("map_fail"), "off": self.s("map_off"),
                           "keys": LC.MAP_KEYS.get(self.loc.code, "")}, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------- the site
class Site:
    """One language version: its records that are current, their slugs and paths, the ko ↔ version pairs, and the
    page view models."""

    def __init__(self, S, data_dir: Path, loc: LC.Locale = EN):
        self.S, self.loc = S, loc
        self.city = C = S.city
        site = S.site
        ldir = Path(data_dir) / loc.code
        strings = _load(ldir / "strings.json", {}) or {}
        self.strings = {k: no_hangul(squash_ws((v or {}).get(loc.tag))) for k, v in strings.items()}
        self.t = UIText(loc, self.strings)
        recs = {k: _load(ldir / f"{k}.json", {}) or {} for k in ("places", "guides", "courses", "events")}
        hashes = current_hashes(Path(data_dir), city=C)
        # names (site.json through locales.names): the site, the city and its province in this language; never
        # Korean script
        nm = LC.names(site, loc.code)
        self.site_name, self.region, self.admin = nm["site_name"], nm["city"], nm["admin"]
        self.home_h1 = nm["home_h1"]
        # the city's own providers in English (site.json): full names (the source of the original texts, the city
        # body) and the short names present.slot_provider gives; another version names them in its strings
        source = site.get("source") or {}
        self.full_names: dict[str, str] = {}
        if loc.code == "en":
            for ko, en in ((C.locality, site.get("locality_en")), (source.get("name"), source.get("name_en"))):
                if squash_ws(ko) and no_hangul(squash_ws(en)):
                    self.full_names[squash_ws(ko)] = no_hangul(squash_ws(en))
        # the list hubs (site.json list_hubs: kind -> guide id), food · stay · attraction
        self.hub_ids = {k: squash_ws((C.list_hubs.get(k) or {}).get("guide_id")) for k in present.HUB_KINDS
                        if isinstance(C.list_hubs.get(k), dict) and squash_ws(C.list_hubs[k].get("guide_id"))}
        self.stale: dict[str, list[str]] = {k: [] for k in recs}
        # published Korean records with no translation at all in this version (the build warns: prepare --lang <code>)
        self.untranslated: dict[str, list[str]] = {k: [] for k in recs}
        self.hashes, self.recs = hashes, recs
        self.home = loc.home
        self.misses: set[str] = set()
        self._cv: dict[str, dict] = {}     # course view models, each computed once (Site.cv)

        def current(kind: str, key: str) -> dict | None:
            rec, h = recs[kind].get(key), hashes[kind].get(key)
            if not rec or h is None:   # untranslated, or not published (no hash): no page in this language
                if h is not None:
                    self.untranslated[kind].append(key)
                return None
            if rec.get("ko_hash") != h:
                self.stale[kind].append(key)
                return None
            return rec

        # places, guides, courses: the slug the Korean record stores (every version, CLAUDE.md 2 — never made here)
        self.places: dict[str, dict] = {}
        for e in S.entities:
            rec = current("places", e["id"])
            if rec:
                self.places[e["id"]] = {"e": e, "rec": rec, "slug": e["slug"]}
        for p in self.places.values():
            e = p["e"]
            p["path"] = f"{self.home}places/{p['slug']}/"
            p["url"] = S.abs(p["path"])
            p["name"] = squash_ws(p["rec"].get(loc.name_key)) or self.fallback_name(e["name"])
            p["noindex"] = S.mode == "production" and not e["_index_ok"]
            e.setdefault("_intl", {})[loc.code] = p
            if loc.code == "en":
                e["_en"] = p
        self.guides: dict[str, dict] = {}
        for g in S.guides:
            rec = current("guides", g["id"])
            if rec:
                self.guides[g["id"]] = {"g": g, "rec": rec, "slug": g["slug"]}
        for x in self.guides.values():
            x["path"] = f"{self.home}guides/{x['slug']}/"
            x["url"] = S.abs(x["path"])
        self.courses: dict[str, dict] = {}
        for c in S.courses:
            rec = current("courses", c["id"])
            if rec:
                self.courses[c["id"]] = {"c": c, "rec": rec, "slug": c["slug"]}
        for x in self.courses.values():
            x["path"] = f"{self.home}courses/{x['slug']}/"
            x["url"] = S.abs(x["path"])
        # event series exactly as tools/en_content.py prepared them (published records), keyed by the series slug —
        # the same slug as the Korean page /events/<slug>/ (slugs.series_slug, every stored slug reserved first); the
        # series' anchor on <home>events/ is that slug too
        self.series: list[dict] = []
        events_all = getattr(S, "events_all", []) or []
        for sr in event_series(events_all):
            rec = current("events", sr["slug"])
            if rec:
                self.series.append({"sr": sr, "rec": rec, "slug": sr["slug"], "anchor": sr["slug"]})
        self.ko_series = {sr["slug"]: sr for sr in getattr(S, "series", []) or []}
        self.by_kind = {k: [p for p in self.places.values() if p["e"].get("kind") == k] for k in KINDS}
        self.guide_by_id = {gid: x for gid, x in self.guides.items()}
        self.place_by_ko_slug = {p["e"]["slug"]: p for p in self.places.values()}
        # ko ↔ version pairs (both pages are built)
        pairs: dict[str, str] = {}
        if self.places:
            pairs["/"] = self.home
            pairs["/about/"] = f"{self.home}about/"
            for kind, cfg in LIST_PAGES.items():
                if self.by_kind[kind] and S.lists.get(kind):
                    pairs[cfg["ko"]] = self.home + cfg["seg"]
            for p in self.places.values():
                pairs[p["e"]["_path"]] = p["path"]
            if self.guides:
                pairs["/guides/"] = f"{self.home}guides/"
            for x in self.guides.values():
                pairs[x["g"]["_path"]] = x["path"]
            if self.courses:
                pairs["/courses/"] = f"{self.home}courses/"
            for x in self.courses.values():
                pairs[x["c"]["_path"]] = x["path"]
            if self.series and S.events:
                pairs["/events/"] = f"{self.home}events/"
        self.ko2en = pairs
        self.en2ko = {v: k for k, v in pairs.items()}
        # pages the language menu pairs although they are no hreflang twins (noindex, kept out of ko2en): the site
        # search (Korean /search/ is built with S.entities, <home>search/ with this version's places: Pages.search)
        self.menu_twins = {"/search/": f"{self.home}search/"} if self.places and S.entities else {}
        self._ko_kind = {e["_path"]: e.get("kind") for e in S.entities}
        # a Korean event page has no twin: its link opens that series on <home>events/
        self.event_links = {}
        by_slug = {x["slug"]: x for x in self.series}
        for sr in getattr(S, "series", []) or []:
            x = by_slug.get(sr["slug"])
            if x:
                self.event_links[sr["_path"]] = f"{self.home}events/#{x['anchor']}"
        # the city body's name here (about: 'run independently of …'; '' when this version has none)
        self.city_body = self.config_name(C.locality, site.get("locality_en"))
        # where the courses come from (present.course_source): their one shared source in this language, and whether
        # it is an official site (site.json official_domains) — only then do the pages call them official (UIText
        # prints the '<key>_plain' words of intl_text otherwise)
        ks = present.courses_source(S, [present.course_source(S, x["c"]) for x in self.courses.values()])
        self.course_src = {"name": self.en_name(ks["name"]) if ks["name"] else "", "official": bool(ks["official"])}
        self.t.official = self.course_src["official"]
        self._type_map()

    # ---- strings and labels
    def T(self, key: str, default: str = "", track: bool = False) -> str:
        """A label from strings.json. track: a label whose fallback is its key (Latin on a page of another script),
        so a missing one is listed (build stats, a validate warning)."""
        v = self.strings.get(key)
        if not v and track and self.loc.code != "en":
            self.misses.add(key)
        return v or default

    def offer(self) -> str:
        """The suffix of the sentences that say what the site has beyond places (intl_text home_desc, about_lede,
        llms_home): '' — official courses and festival dates; '_courses' — courses (not all from one official site)
        and festival dates; '_none' — neither (a site without courses or events says nothing about them)."""
        if self.courses and self.series and self.S.events:
            return "" if self.course_src["official"] else "_courses"
        return "_none"

    def fallback_name(self, ko: str) -> str:
        """A name with no translated form: Revised Romanization (Kontsevich Cyrillic in Russian)."""
        return LC.kontsevich(ko) if self.loc.code == "ru" else romanize(ko)

    def first_sentence(self, text: str | None) -> str:
        return (sentences(text, self.loc) or [""])[0]

    def lists(self) -> dict[str, dict]:
        """The three list pages of this version: path, Korean counterpart, nav label, H1, <title>, hub guide."""
        t, r = self.t, self.region
        return {kind: {"path": self.home + c["seg"], "ko": c["ko"], "hub": self.hub_ids.get(kind, ""), "kind": kind,
                       "nav": t.s(f"nav_{kind}"), "h1": t.s(f"h1_{kind}", r=r)} for kind, c in LIST_PAGES.items()}

    def nav(self) -> list[tuple[str, str]]:
        return [(self.t.s(k), self.home + seg) for k, seg in NAV_KEYS]

    def current_nav(self, page_kind: str) -> str:
        seg = CURRENT.get(page_kind)
        return self.home + seg if seg else ""

    def _type_map(self) -> None:
        """Type labels in English (strings.json): source categories, the type words (the national tables of present
        with this city's site.json categories over them: STAY_TYPE.<category> …), the list's attraction groups by
        position (ATTRACTION_GROUPS.<i>, build.list_filters) and theme names."""
        S, T, C = self.S, self.T, self.city
        m: dict[str, str] = {}
        for cat in {squash_ws(e.get("category")) for e in S.entities_all}:
            if cat and T(f"category:{cat}"):
                m[cat] = T(f"category:{cat}")
        for kind_map, key, base in (("stay_type", "STAY_TYPE", present.STAY_TYPE),
                                    ("food_type", "FOOD_TYPE", present.FOOD_TYPE),
                                    ("attr_type", "ATTR_TYPE", present.ATTR_TYPE)):
            own = C.categories.get(kind_map)
            for k, v in {**base, **(own if isinstance(own, dict) else {})}.items():
                if v and T(f"{key}.{k}"):
                    m[v] = T(f"{key}.{k}")
        for i, (name, _) in enumerate(getattr(S, "attraction_groups", ()) or ()):
            if T(f"ATTRACTION_GROUPS.{i}"):
                m[name] = T(f"ATTRACTION_GROUPS.{i}")
        for t in S.themes:
            if T(f"theme.{t['slug']}.name"):
                m[t["name"]] = T(f"theme.{t['slug']}.name")
        self.type_en = m

    def region_name(self, name: str | None) -> str:
        """A region group's name here: strings REGIONS.<region key> (City.region_key: an anchor's key, a 구·군's
        slug, 'far', 'none'), else a 구·군 transcribed ('Jung-gu', Russian 'Чун-гу'), this version's word for the
        'none' group of the mode, or the name transcribed (fallback_name)."""
        C, n = self.city, squash_ws(name)
        key = C.region_key(n)
        if self.T(f"REGIONS.{key}"):
            return self.T(f"REGIONS.{key}")
        if n in C.districts:
            return LC.district_name(n, self.loc.code)
        if n == C.none_label:
            return self.t.s("none_anchors" if C.region_mode == "anchors" else "none_district")
        return self.fallback_name(n)

    def area(self, e: dict | None) -> str:
        """A place's area here, larger unit first like the Korean label: 'Jung-gu, Samdeok-dong 1-ga', 'Jangmi-dong'
        (the build's `_district` and `_area`; Kontsevich Cyrillic in Russian)."""
        e, code = e or {}, self.loc.code
        return ", ".join(x for x in (LC.district_name(e.get("_district"), code), LC.area_name(e.get("_area"), code)) if x)

    def tag_label(self, tag: str) -> str:
        """A list tag (present.list_vm: the type, or the 특화거리 of a food place) in this language; '' when it has none
        (the chip is left out — never Korean script on these pages). A street takes its category's translation
        without the bracketed cuisine ('한빛국수 특화거리 ( 한식)' -> 'Hanbit Noodle Specialty Street')."""
        v = self.type_en.get(tag)
        if v:
            return v
        for cat, lab in self.type_en.items():
            if present.street_of({"kind": "food", "category": cat}) == tag:
                return re.sub(r"\s*[(（][^()（）]*[)）]\s*$", "", lab)
        self.misses.add(f"tag:{tag}")
        return ""

    def kind_label(self, kind: str) -> str:
        return self.T(f"KIND_LABELS.{kind}", kind, track=True)

    def type_label(self, e: dict) -> str:
        return self.type_en.get(e.get("_type") or "") or self.kind_label(e.get("kind", "attraction"))

    def fact_label(self, key: str) -> str:
        return self.T(f"FACT_LABELS.{key}", track=True) or key

    def row_label(self, e: dict, key: str) -> str:
        """A facts row's label as the Korean row's (schema.fact_label): a parking_seats value with one half only is
        labelled by that half (seating / parking)."""
        half = parking_seats_half(e) if key == "parking_seats" else ""
        if half:
            return self.fact_label("seat" if half == "seats" else "parking")
        return self.fact_label(key)

    def seats_note(self, p: dict) -> str:
        """The Korean list cell's '좌석 30석' (present.seats_note) in this language: 'Seating: 30 seats' — the label is
        left off when the value already starts with it ('座席100席')."""
        if not present.seats_note(p["e"]):
            return ""
        value = squash_ws(((p["rec"].get("facts") or {}).get("parking_seats") or {}).get("value"))
        if not value:
            return ""
        lab = self.fact_label("seat")
        return value if value.startswith(lab) else f"{lab}{self.loc.colon}{value}"

    def en_name(self, ko: str | None) -> str:
        """A source's name in this language: strings provider:<name>, else its English full name (site.json), else its
        short name (present.slot_provider with this city: the national ones in UIText words, the city's own from
        site.json or the strings), else the name when it has no Korean script; '' when there is none."""
        k = squash_ws(ko)
        if not k:
            return ""
        return (self.T(f"provider:{k}") or self.full_names.get(k, "")
                or self.short_name(present.slot_provider(k, city=self.city)) or no_hangul(k))

    def config_name(self, ko: str | None, en: str | None) -> str:
        """A name the site configures for the city (the source of the original texts, the city body): English the
        site.json value (source.name_en, locality_en) only, another version its strings 'provider:<Korean name>';
        '' when there is none — the words that need it are then left out, never guessed."""
        k = squash_ws(ko)
        if not k:
            return ""
        return no_hangul(squash_ws(en)) if self.loc.code == "en" else self.T(f"provider:{k}")

    def short_name(self, short: str | None) -> str:
        """A short provider name (present.slot_provider) here: UIText words for the national ones, the city's own
        from site.json (English) or the strings ('provider:<short name>'); '' when there is none."""
        s = squash_ws(short)
        if not s:
            return ""
        key = SHORT_PROVIDER.get(s)
        return self.t.s(key) if key else (self.full_names.get(s, "") or self.T(f"provider:{s}"))

    def provider(self, ko: str | None) -> str:
        """A source's name in this language (en_name), the word 'Source' when it has none; never Korean script."""
        k = squash_ws(ko)
        return (self.en_name(k) or self.t.s("source")) if k else ""

    def short_provider(self, ko: str | None) -> str:
        k = squash_ws(ko)
        return self.short_name(present.slot_provider(k, city=self.city)) or self.provider(k)

    def event_source(self, rec: dict, ko: str | None) -> str:
        k = squash_ws(ko)
        return no_hangul(squash_ws((rec.get("sources") or {}).get(k))) or self.provider(k)

    def lic(self, code: str) -> str:
        return self.T(f"LIC.{code}") or code

    def designations(self, e: dict) -> list[dict]:
        """The official designations the Korean page shows (schema.designations), in this language: {type, label,
        source_name, url, checked_at}. The label and the list's name come from strings.json (designation:<label>,
        designation_source:<list name>); one without both is left out (never Korean script on these pages) and
        pipeline.validate reports it."""
        out = []
        for d in designations(e, city=self.city):
            label = self.T(f"designation:{d['label']}")
            src = self.T(f"designation_source:{squash_ws(d['source_name'])}")
            if label and src:
                out.append({"type": d["type"], "label": label, "source_name": src, "url": d["url"],
                            "checked_at": d["checked_at"]})
        return out

    # ---- pairs (this version's own; Intl.alternates / Intl.menu combine every version's)
    def menu_link(self, ko_path: str) -> tuple[str, str]:
        """(href, note) of this version's item in the language menu of a Korean page: its twin (a series on
        <home>events/, the search page) with no note; else this version's list of the same kind (guides, courses,
        events, the place's own list), or <home> when there is none, with the note '<that page's name> · not
        translated' in this version's words."""
        twin = self.ko2en.get(ko_path) or self.event_links.get(ko_path) or self.menu_twins.get(ko_path)
        if twin:
            return twin, ""
        seg = ko_path.strip("/").split("/", 1)[0]
        key, section = "home", ""
        if seg in ("guides", "courses", "events"):
            key, section = seg, f"/{seg}/"
        elif self._ko_kind.get(ko_path) in LIST_PAGES:
            kind = self._ko_kind[ko_path]
            key, section = f"nav_{kind}", LIST_PAGES[kind]["ko"]
        href = self.ko2en.get(section) if section else ""
        return href or self.home, f"{self.t.s(key if href else 'home')} · {self.loc.untranslated}"

    def ko_link(self, en_path: str) -> str:
        return self.en2ko.get(en_path) or "/"

    def place_href(self, slug: str | None) -> str:
        p = self.place_by_ko_slug.get(slug or "")
        return p["path"] if p else ""

    def own(self, e: dict | None) -> dict | None:
        """This version's page record of a Korean place (None when it has no current page here)."""
        return ((e or {}).get("_intl") or {}).get(self.loc.code)

    # ---- photos
    def photos(self, p: dict) -> list[dict]:
        """The place's licensed photos with alt text in this language, credit and licence label."""
        out = []
        phs = p["e"].get("_photos") or []
        kto = self.t.s("kto")
        for i, ph in enumerate(phs, 1):
            alt = self.t.s("photo_alt", name=p["name"], i=i) if len(phs) > 1 else p["name"]
            out.append({**ph, "alt": alt, "name": p["name"], "credit": kto,
                        "lic": self.lic("KOGL-1" if ph["type"] == 1 else "KOGL-3")})
        return out

    # ---- key facts (the first-screen tiles and card rows)
    def slot_label(self, e: dict, name: str, v: dict | None = None) -> str:
        if name == "parking" and v and v.get("src_key") == "parking_seats":
            if parking_seats_half(e) == "parking":
                return self.fact_label("parking")
            return self.T("CONTEST_LABEL.parking_seats", self.t.s("parking_seats"))
        if name == "parking" and v and v.get("src_key") == "parkingfee":
            return self.fact_label("parkingfee")
        return self.T(SLOT_STRING[name], name, track=True)

    def slot(self, p: dict, name: str) -> dict | None:
        """One key-fact slot from the record, following the Korean slot (present.slot_value): which field it reads,
        whether two sources differ. None when the Korean slot is empty; {'skip': True} when the translated value
        cannot be split the way the Korean was (a closed day inside an hours value)."""
        e, facts, loc = p["e"], p["rec"].get("facts") or {}, self.loc
        v = present.slot_value(e, name)
        if not v:
            return None
        label = self.slot_label(e, name, v)
        base = {"key": name, "src_key": v["src_key"], "label": label, "sub": "", "more": False, "closed": False,
                "conflict": False, "vals": [], "tel": "", "date": v.get("date") or "",
                "provider": self.short_provider(present.src_of(e, v["src_key"])["provider"]), "missing": False}
        f = facts.get(v["src_key"]) or {}
        if name == "tel":
            if v.get("tel"):
                main = extract_phones(v["main"])[0] if extract_phones(v["main"]) else ""
                return {**base, "main": main, "tel": present.tel_href(main, True)} if main else None
            own = (extract_phones(f.get("value")) or [""])[0]
            vals = [{"provider": base["provider"], "main": own, "sub": "", "closed": False}] if own else []
            for a in f.get("alternatives") or []:
                ph = (extract_phones(a.get("value")) or [""])[0]
                if ph and ph != own:
                    vals.append({"provider": self.short_provider(a.get("provider")), "main": ph, "sub": "", "closed": False})
            if len(vals) > 1:
                return {**base, "main": own, "conflict": True, "vals": vals}
            return {**base, "main": own, "tel": present.tel_href(own, True)} if own else None
        if not f.get("value") and not f.get("alternatives"):
            return None
        tr_raw = [f.get("value")] + [a.get("value") for a in f.get("alternatives") or []]
        ko_raw = ([(e.get("facts") or {}).get(v["src_key"])] + [a["value"] for a in conflict_alternatives(e, v["src_key"])]
                  if v["src_key"] in HOURS_KEYS else [])
        if name == "closed" and v["src_key"] != "restdate":
            # the closed day inside an hours value: the part the Korean parse finds, at the same place in each value;
            # another source's closed day is shown where the Korean slot shows it (present.slot_value)
            if len(ko_raw) != len(tr_raw):
                return {"skip": True, "why": f"{len(ko_raw) - 1} other source values in the Korean, "
                                             f"{len(tr_raw) - 1} in the translation"}
            spans = [closed_span(k, t, loc) for k, t in zip(ko_raw, tr_raw)]
            if not spans[0] or spans[0]["start"] < 0:
                return {"skip": True, "why": (spans[0] or {}).get("why") or "no closed day in the Korean"}
            cb = present.brief_closed(present.brief_hours(ko_raw[0])[1])
            b = {"main": cap(spans[0]["text"]), "sub": "", "more": bool(v.get("more"))}
            alt_b = []
            for k, sp in zip(ko_raw[1:], spans[1:]):
                ac = present.brief_hours(k)[1]
                acb = present.brief_closed(ac) if ac else None
                shown = bool(acb and cb and acb["main"] != cb["main"] and (acb["closed"] or cb["closed"]))
                alt_b.append({"main": cap(sp["text"]) if shown and sp and sp["start"] >= 0 else "", "sub": "", "more": True,
                              "lost": shown and not (sp and sp["start"] >= 0)})
            if any([x.pop("lost") for x in alt_b]):
                return {"skip": True, "why": "another source's closed day cannot be aligned"}
        elif name == "hours" and len(ko_raw) == len(tr_raw):
            b = brief_en(v["src_key"], hours_part(ko_raw[0], tr_raw[0], loc), loc)
            alt_b = [brief_en(v["src_key"], hours_part(k, t, loc), loc) for k, t in zip(ko_raw[1:], tr_raw[1:])]
        elif name == "closed":
            # its own field ('restdate'): whole where the Korean tile is whole (QA 2026-10-15: never 'the first' of
            # 'the first and third Sundays'), each other source against the Korean value it translates
            ko_alts = [a["value"] for a in conflict_alternatives(e, "restdate")]
            tr_alts = f.get("alternatives") or []
            b = closed_brief((e.get("facts") or {}).get("restdate"), f.get("value"), loc)
            alt_b = ([closed_brief(k, a.get("value"), loc) for k, a in zip(ko_alts, tr_alts)] if len(ko_alts) == len(tr_alts)
                     else [brief_en("restdate", a.get("value"), loc) for a in tr_alts])
        elif name == "rooms":
            r = squash_ws(f.get("value"))
            b = {"main": self.t.sn("rooms_n", int(r), n=r) if r.isdigit() else r, "sub": "", "more": False}
            alt_b = []
        else:
            b = brief_en(v["src_key"], f.get("value"), loc)
            alt_b = [brief_en(v["src_key"], a.get("value"), loc) for a in f.get("alternatives") or []]
        out = {**base, **b, "closed": v.get("closed", False)}
        if v.get("conflict") and f.get("alternatives"):
            ko_vals = v.get("vals") or []
            vals = [{"provider": base["provider"], **b, "closed": v.get("closed", False)}] if b.get("main") else []
            j = 1   # the Korean slot's values are the ones it shows: its j-th is this version's j-th shown one
            for a, ab in zip(f.get("alternatives") or [], alt_b):
                if ab.get("main"):
                    closed = ko_vals[j].get("closed", False) if j < len(ko_vals) else False
                    j += 1
                    vals.append({"provider": self.short_provider(a.get("provider")), **ab, "closed": closed})
            if len(vals) > 1:
                out.update(conflict=True, vals=vals)
        if not out.get("main") and not out["vals"]:
            return None
        return out

    def key_facts(self, p: dict, mode: str = "hero") -> dict:
        """present.key_facts in this language: the kind's slots in fixed order; hero mode lists a missing slot
        once ('Not listed: …'), card mode keeps it in its place."""
        e = p["e"]
        kind = e.get("kind") if e.get("kind") in present.HERO_SLOTS else "attraction"
        names = (present.HERO_SLOTS if mode == "hero" else present.KF_CARD_SLOTS)[kind]
        slots, missing = [], []
        for n in names:
            s = self.slot(p, n)
            if s and s.get("skip"):
                continue
            if s:
                slots.append(s)
            else:
                missing.append(self.slot_label(e, n))
                if mode != "hero":
                    slots.append({"key": n, "label": self.slot_label(e, n), "main": "",
                                  "sub": self.seats_note(p) if n == "parking" else "", "more": False,
                                  "closed": False, "conflict": False, "vals": [], "missing": True, "tel": ""})
        dates = [s["date"] for s in slots if s.get("date")]
        provs: list[str] = []
        for s in slots:
            for pr in [s.get("provider")] + [v["provider"] for v in s.get("vals") or []]:
                if pr and pr not in provs:
                    provs.append(pr)
        tel = next((s for s in slots if s["key"] == "tel" and s.get("tel")), None)
        if tel and mode == "hero" and not tel.get("conflict"):
            # the place page's call tile: the number as the source writes it, the +82 form a caller abroad dials under
            # it (area codes, mobiles, 070 only — textutil.phone_intl_shown). Never on list cells or mini cards.
            tel["sub"] = phone_intl_shown(tel["main"])
        return {"slots": slots, "missing": missing, "date": min(dates) if dates else "", "providers": provs,
                "conflict": any(s.get("conflict") for s in slots), "tel": (tel["main"], tel["tel"]) if tel else ("", "")}

    # ---- facts card
    def fact_rows(self, p: dict, keys, notes: "present.Notes", tel: tuple = ("", "")) -> list[dict]:
        """Every fact in `keys` order, whole, with its source as a footnote; both values (each with its source) and
        the record's note when two sources differ; 'also' values as 'or …'."""
        e, facts = p["e"], p["rec"].get("facts") or {}
        ko = e.get("facts") or {}
        out, called = [], False
        for k in keys:
            label = self.row_label(e, k)
            if k in ("homepage", "reservationurl"):
                url = link_url(ko.get(k))
                if not url:
                    continue
                text = web_text(url)
                text = text if not HANGUL.search(text) else url_domain(url)
                if HANGUL.search(text):   # a Korean domain name ('화본마을.com'): its ASCII form, which every browser opens
                    try:
                        text = ".".join(part.encode("idna").decode("ascii") for part in text.split("."))
                    except UnicodeError:
                        text = url_domain(url)
                src = present.src_of(e, k)
                n = notes.ref({**src, "provider": self.provider(src["provider"]), "confirmed_by": ""}, label)
                out.append({"key": k, "label": label, "text": text, "url": url, "n": n, "conflict": False,
                            "blocks": [], "alts": [], "note": "", "tel": None, "wide": False})
                continue
            f = facts.get(k)
            if not f:
                continue
            value = f.get("value") or ""
            src = present.src_of(e, k)
            conf = squash_ws(src.get("confirmed_by"))
            conf = self.provider(re.sub(r"\s+\d{4}-\d{2}-\d{2}$", "", conf)) if conf else ""
            row = {"key": k, "label": label, "text": value, "url": "", "n": None, "conflict": False, "blocks": [],
                   "alts": [], "note": "", "tel": None, "wide": "\n" in value or len(value) > (11 if self.loc.cjk else 22),
                   "provider": self.provider(src["provider"]), "checked_at": src["checked_at"]}
            if value:
                row["n"] = notes.ref({**src, "provider": row["provider"], "confirmed_by": conf}, label)
            ko_alts = present.contested(e, k)
            for i, a in enumerate(f.get("alternatives") or []):
                ka = ko_alts[i] if i < len(ko_alts) else {}
                a_src = {"provider": self.provider(a.get("provider")), "checked_at": squash_ws(ka.get("checked_at")),
                         "url": ka.get("url") or "", "confirmed_by": ""}
                row["blocks"].append({"provider": a_src["provider"], "checked_at": a_src["checked_at"],
                                      "text": a.get("value") or "", "n": notes.ref(a_src, label + " (other value)")})
            ko_also = [a for a in present.alternatives(e, k) if a.get("relation") == "also"]
            for i, a in enumerate(f.get("also") or []):
                ka = ko_also[i] if i < len(ko_also) else {}
                a_src = {"provider": self.provider(a.get("provider")), "checked_at": squash_ws(ka.get("checked_at")),
                         "url": ka.get("url") or "", "confirmed_by": ""}
                row["alts"].append({"provider": a_src["provider"], "text": a.get("value") or "",
                                    "n": notes.ref(a_src, label + " (also)")})
            if row["blocks"]:
                row["conflict"], row["wide"] = True, True
                if value:
                    row["blocks"].insert(0, {"provider": row["provider"], "checked_at": row["checked_at"],
                                             "text": value, "n": row["n"]})
                row["note"] = squash_ws(f.get("note")) or (CONFLICT_NOTE if self.loc.code == "en" else self.loc.conflict)
                if not called and tel[0]:
                    row["tel"], called = tel, True
            out.append(row)
        return out

    def missing_facts(self, p: dict) -> list[str]:
        """Labels of the kind's key facts no source gives (one 'Not listed: …' line under the facts)."""
        e, facts = p["e"], p["rec"].get("facts") or {}
        kind = e.get("kind", "attraction")
        keys = KEY_FACTS_BY_CATEGORY.get(e.get("category"), KEY_FACTS.get(kind, ()))
        out = []
        for k in keys:
            if facts.get(k) or any(facts.get(x) and alias_holds(e, k, x) for x in FACT_ALIASES.get(k, ())):
                continue
            if k == "parking" and facts.get("parkingfee"):
                continue
            out.append(self.fact_label(k))
        return out

    # ---- chapters with their own sources (details, FAQ)
    def chapter_notes(self, e: dict):
        from .build import source_labels
        labels = {u: self.provider(n) for u, n in source_labels(e).items()}
        site = self

        class Notes:
            def __init__(self):
                self.items: list[dict] = []

            def ref(self, source: str | None):
                s = squash_ws(source)
                if not s:
                    return None
                if s.startswith("http"):
                    # a page on an official site (site.json official_domains) is named by that site's name here
                    official = site.city.official_label(s)
                    name = labels.get(s) or (site.t.s("kto_visitkorea") if "visitkorea" in s
                                             else (site.en_name(official) if official else "") or url_domain(s))
                    item = {"url": s, "name": name}
                else:
                    item = {"url": "", "name": site.provider(s)}
                if item not in self.items:
                    self.items.append(item)
                return self.items.index(item) + 1
        return Notes()

    # ---- routes
    def route(self, p: dict) -> dict:
        """Front row: Google Maps (by coordinates, else the Korean name + the region and 구·군, City.map_query_prefix),
        Naver Map, Kakao Map (the Korean page's exact links); the rest under 'Other maps'. Same data-track /
        data-provider values as the Korean."""
        e, S, t, C = p["e"], self.S, self.t, self.city
        geo = e["_geo"] or {}
        mid = e.get("map_ids") or {}
        region = C.map_query_prefix(e)
        links = build_links(e["name"], geo.get("lat"), geo.get("lng"), region=region,
                            address=(e.get("facts") or {}).get("address", ""), naver_place_id=mid.get("naver_place_id", ""),
                            google_place_id=mid.get("google_place_id", ""),
                            tmap_scheme=S.site.get("tmap_scheme", DEFAULT_TMAP_SCHEME), homographs=C.homographs,
                            kakao_place_id=mid.get("kakao_place_id", ""))
        by = {l["key"]: l for l in links}
        if geo:
            google = {"key": "google", "url": f"https://www.google.com/maps/search/?api=1&query={geo['lat']},{geo['lng']}",
                      "precise": True}
        else:
            said = e["name"]
            for h in sorted(C.homographs, key=len, reverse=True):   # a dish named like the city does not name it
                said = said.replace(h, " ")
            q = e["name"] if region and region in said else f"{e['name']} {region}".strip()
            google = {"key": "google", "url": "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": q}),
                      "precise": False}
        front = [{**google, "label": t.s("map_google"), "role": "map"},
                 {**by["naver"], "label": t.s("map_naver")}, {**by["kakao"], "label": t.s("map_kakao")}]
        names = {"kakao_route": t.s("route_kakao"), "google_route": t.s("route_google"), "tmap": t.s("route_tmap")}
        rest = [{**by[k], "label": lab} for k, lab in names.items() if k in by]
        for l in front + rest:
            l["track"] = "route_click" if l["role"] == "route" else "map_click"
        cta = by.get("google_route") or google
        return {"front": front, "rest": rest,
                "cta": {"url": cta["url"], "label": t.s("directions") if cta.get("role") == "route" else t.s("sec_map"),
                        "ext": True, "track": "route_click" if cta.get("role") == "route" else "map_click",
                        "provider": cta["key"], "place": e["id"]}}

    # ---- place page
    def place_vm(self, p: dict) -> dict:
        S, e, rec, loc = self.S, p["e"], p["rec"], self.loc
        kind = e.get("kind", "attraction")
        tel_text, tel = present.settled_phone(e)
        tel = (tel_text, present.tel_href(tel_text, True)) if tel_text and not HANGUL.search(tel_text) else ("", "")
        notes = present.Notes()
        facts = rec.get("facts") or {}
        practical_keys = list(present.PRACTICAL[kind])
        shown = set(practical_keys)
        known = set(present.MORE) | set(present.FIT) | shown
        more_keys = [k for k in present.MORE if k not in shown] + [k for k in facts if k not in known]
        practical = self.fact_rows(p, practical_keys, notes, tel)
        more = self.fact_rows(p, more_keys, notes, tel)
        fit = self.fact_rows(p, present.FIT, notes, tel)
        summary = squash_ws(rec.get("summary"))
        ss = sentences(summary, loc)
        photos = self.photos(p)
        lead = photos[0] if photos else None
        details_n, faq_n = self.chapter_notes(e), self.chapter_notes(e)
        details = [{"heading": squash_ws(d.get("heading")), "text": squash_ws(d.get("text")), "n": details_n.ref(d.get("source"))}
                   for d in rec.get("details") or [] if squash_ws(d.get("text"))]
        faqs = [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a")), "n": faq_n.ref(f.get("source"))}
                for f in rec.get("faq") or [] if squash_ws(f.get("q")) and squash_ws(f.get("a"))]
        # nearby places that have pages in this version (TourAPI nearby list, straight-line distance), as the Korean
        # rows (present.near_row): the place's own small photo or its kind icon, closed day / check-in, one bar scale;
        # never the page's own family, never an alias beside its parent (pipeline/relations.py, as the Korean page)
        near = []
        target = lambda n: S.ent_by_slug.get(n.get("internal_slug") or "") or S.ent_by_cid.get(str(n.get("contentid")))  # noqa: E731
        for n in relations.keep_rows(e, e.get("nearby") or [], target):
            t = target(n)
            tp = self.own(t)
            if not tp:
                continue
            near.append(self.near_row(t, tp, n.get("distance_m")))
        near.sort(key=lambda x: x["m"])
        near_sights = [n for n in near if n["kind"] == "attraction"][:8]
        near_biz = [n for n in near if n["kind"] in ("stay", "food")][:8]
        scale = present.near_scale([n["m"] for n in near_sights + near_biz], (e.get("nearby_source") or {}).get("radius_m"))
        for n in near_sights + near_biz:
            n["f"] = present.near_fill(n["m"], scale)
        points = None
        if e["_geo"]:
            points = {"self": {"lat": e["_geo"]["lat"], "lng": e["_geo"]["lng"], "name": p["name"]},
                      "near": [{"lat": n["geo"]["lat"], "lng": n["geo"]["lng"], "name": n["name"], "d": n["d"],
                                "url": n["href"], "kind": n["kind"]} for n in near if n["geo"]][:12],
                      "anchors": []}
        courses = [self.courses[c["id"]] for c in e["_courses"] if c["id"] in self.courses]
        boards = []
        for x in courses:
            cv = self.cv(x)
            at = [k for k, s in enumerate(cv["stops"]) if s["t"] is e]   # every visit (present.route_segs)
            if at:
                boards.append({"display": cv["name"], "path": x["path"], "stops": cv["stops"], "at": at})
        segs = present.route_segs(boards, loc.dist, lambda s: (s.get("p") or {}).get("name") or s["name"])
        guides = [self.guides[g["id"]] for g in e["_guides"] if g["id"] in self.guides]
        guide_cards = []
        for x in guides:
            label, title = squash_ws(x["rec"].get("label")), squash_ws(x["rec"].get("title"))
            guide_cards.append({"label": label if label != title else "", "title": title, "path": x["path"]})
        events = [x for x in self.series if e["slug"] in self._series_places(x)]
        from . import build as B
        nw = LC.NEAR_WORDS[loc.code]
        ko_ev = {ev["id"]: ev for ev in getattr(S, "events_all", []) or []}
        event_cards = []
        for x in events:   # ev_rec: the series' record — `rec` stays the place's own (its JSON-LD address, phone, hours)
            ev_rec, ko = x["rec"], x["sr"]["newest"]
            ev = ko_ev.get((ev_rec.get("newest") or {}).get("id")) or ko
            varies = ((ev_rec.get("alternatives") or {}).get("period") or {}).get("values")
            event_cards.append({"name": squash_ws(ev_rec.get("series_name")), "path": f"{loc.home}events/#{x['anchor']}",
                                "range": nw["ev_varies"] if varies else squash_ws((ev_rec.get("newest") or {}).get("period_text")),
                                "past": (B.event_last_day(ev) if ev.get("start_date") else "") < S.today})
        relation, parts = self.relation_vm(e)
        photo_lics = present.photo_credits(near_sights + near_biz + parts)
        official = e.get("official") or {}
        orig = e.get("original") or {}
        list_cfg = self.lists()[kind]
        kicker = [(list_cfg["nav"], list_cfg["path"])]
        tl = self.type_label(e)
        if tl and tl != self.kind_label(kind):
            kicker.append((tl, ""))
        facts_checked = e.get("_facts_checked") or ""
        k = self.key_facts(p, "hero")
        own_home = web_url(official.get("homepage")) or web_url((e.get("facts") or {}).get("homepage"))
        return {
            "p": p, "e": e, "rec": rec, "kind": kind, "name": p["name"], "name_ko": e["name"], "kicker": kicker,
            "area": self.area(e), "lede": ss[0] if ss else "", "story": ss[1:], "summary": summary,
            "kf": k, "route": self.route(p), "photos": photos, "notices": self.notices(e),
            # official designations (Site.designations): chips under the answer, the 'Designations' row of the facts card
            "designations": self.designations(e),
            "hero_k1": lead if lead and lead["type"] == 1 else None,
            "hero_k3": lead if lead and lead["type"] != 1 else None,
            "thumbs": [{"url": ph["th"]["url"], "w": ph["th"]["w"], "h": ph["th"]["h"], "alt": ph["alt"], "type": ph["type"]}
                       for ph in photos[:6] if ph.get("th") and ph["th"].get("w")],
            "practical": practical, "more": more, "fit": fit, "notes": notes.items, "missing": self.missing_facts(p),
            "address_ko": display_address((e.get("facts") or {}).get("address")),
            "details": details, "detail_notes": details_n.items, "faqs": faqs, "faq_notes": faq_n.items,
            "near_sights": near_sights, "near_biz": near_biz, "near_scale": scale, "photo_lics": photo_lics,
            "nearby_source": e.get("nearby_source") or {}, "points": points,
            # whose coordinates: the map caption's 'Location: …' (present.place_vm geo_src) and the nearby note's
            # providers (nearby_source.providers, each name in this language; a list stored before providers were
            # recorded keeps its one provider line)
            "loc_src": self.provider(geo_provider(e["_geo"])) if e["_geo"] else "",
            "near_src": loc.list_sep.join(self.provider(x) for x in (e.get("nearby_source") or {}).get("providers") or [])
                        or self.provider((e.get("nearby_source") or {}).get("provider")),
            "courses": courses, "guides": guides, "events": events, "segs": segs,
            "guide_cards": guide_cards, "event_cards": event_cards, "nw": nw, "relation": relation, "parts": parts,
            "orig_url": orig.get("source_url") or official.get("source_url") or "",
            "orig_name": self.provider(orig.get("source_name") or (S.site.get("source") or {}).get("name")),
            "visitkorea": official.get("visitkorea_url", ""), "homepage": own_home if own_home and not HANGUL.search(own_home) else "",
            "facts_checked": facts_checked, "reviewed_at": e.get("reviewed_at") or "",
            "translated_at": rec.get("translated_at") or "", "ko_path": e["_path"],
            "lics": list(dict.fromkeys(ph["lic"] for ph in photos)),
            **self.book_vm(booking.place_targets(S, e)),
        }

    def book_vm(self, targets: list[dict]) -> dict:
        """예약하기 (pipeline/booking.py) in this version: the buttons (booking.view: the service's page in this
        language, else the Simplified Chinese / English one labelled, else the Korean one '(in Korean)') and the words."""
        code = self.loc.code
        return {"booking": booking.view(targets, code, lambda n: self.t.s("in_korean_paren", name=n)),
                "bw": LC.BOOK_WORDS[code]}

    def near_row(self, t: dict, tp: dict, m) -> dict:
        """One row of the nearby chapter for the Korean place t and its page tp here (present.near_row's fields): its
        name and path here, its kind and type, the straight line m (None: unmeasured), its closed day or check-in,
        its own small photo or its kind icon."""
        nk = t.get("kind")
        cl = self.slot(tp, "closed") if nk != "stay" else None
        fact = self.slot(tp, "checkin") if nk == "stay" else None
        phs = self.photos(tp)
        return {"name": tp["name"], "href": tp["path"], "internal": True, "kind": nk,
                "type": self.type_label(t), "m": m or 0, "d": self.loc.dist(m) if m is not None else "",
                "geo": t["_geo"], "track": present.NEAR_TRACK.get(nk, "nearby_click"),
                "closed": present.one_value(cl), "fact": present.one_value(fact),
                "photo": present.small_thumb(phs[0]) if phs else None,
                "icon": (t.get("_visual") or ("", "pin"))[1]}

    def relation_vm(self, e: dict) -> tuple[list[dict], list[dict]]:
        """present.relation_vm in this version: the line under the name (NEAR_WORDS part_of / same_building) naming
        the parent or the same building's other page — its name here with a link, or its Korean name without one
        when it has no page here — and the parts (the places inside this one that have a page here) as rows."""
        w = LC.NEAR_WORDS[self.loc.code]

        def ref(x: dict) -> dict:
            xp = self.own(x)
            return {"name": xp["name"], "path": xp["path"]} if xp else {"name": x["name"], "path": "", "ko": True}
        lines = []
        parent = e.get("_parent")
        if parent is not None and e.get("_rel") == "inside":
            lines.append({"rel": "inside", "word": w["part_of"], "places": [ref(parent)]})
        if e.get("_same"):
            lines.append({"rel": "same_building", "word": w["same_building"], "places": [ref(x) for x in e["_same"]]})
        parts = []
        for c in e.get("_parts") or []:
            cp = self.own(c)
            if cp:
                parts.append(self.near_row(c, cp, present.hav(e.get("_geo"), c.get("_geo"))))
        return lines, parts

    def notices(self, e: dict) -> list[dict]:
        """The place's dated notices (build.State e['_notices'], pipeline/notices.py) in this version's fixed words:
        the dates as this language writes them, times as they are, the provider's name and the post's link."""
        loc, out = self.loc, []
        for row in e.get("_notices") or []:
            n = row["n"]
            start, end = notices.span(n)
            dates = loc.date(start) if start == end else f"{loc.date(start)}{'–' if loc.cjk else ' – '}{loc.date(end)}"
            if n["kind"] == "hours":
                text = self.t.s("notice_hours", dates=dates, start=n["from"], end=n["to"])
                if n.get("last_entry"):
                    last = self.t.s("notice_last_entry", time=n["last_entry"])
                    text += f"（{last}）" if loc.cjk else f" ({last})"
            else:
                text = self.t.s(f"notice_{n['kind']}", dates=dates)
            out.append({"id": n["id"], "text": text, "provider": self.provider(n["provider"]), "url": n["url"]})
        return out

    def _series_places(self, x: dict) -> list[str]:
        out: list[str] = []
        for ev in x["sr"]["editions"]:
            for s in [*(ev.get("place_slugs") or []), ev.get("place_slug")]:
                if s and s not in out:
                    out.append(s)
        return out

    def card(self, p: dict, photo: dict | None = None) -> dict:
        e = p["e"]
        phs = self.photos(p)
        if photo is not None:
            photo = next((x for x in phs if x["url"] == photo.get("url")), phs[0] if phs else None)
        else:
            photo = phs[0] if phs else None
        return {"p": p, "e": e, "id": e["id"], "kind": e.get("kind", "attraction"), "name": p["name"], "path": p["path"],
                "type": self.type_label(e), "area": self.area(e), "photo": photo,
                "kf": self.key_facts(p, "card")}

    # ---- lists
    def list_vm(self, kind: str) -> dict:
        """The Korean list's records (present.list_vm: grouped by 권역 / 구·군, same order and group ids) that have pages
        here. far_label / none_label: the Korean names of those groups (the map's points carry the Korean group name;
        map.js leaves those groups out of the first view)."""
        S, C = self.S, self.city
        L = present.list_vm(S, kind)
        groups, n_photo, lics = [], 0, set()
        points = []
        for g in L["groups"]:
            recs = []
            for it in g["recs"]:
                p = self.own(it["e"])
                if not p:
                    continue
                cells = []
                for key, _ in present.KF_LIST_COLS[kind]:
                    s = self.slot(p, key)
                    label = self.slot_label(p["e"], key, s if s and not s.get("skip") else None)
                    if s and s.get("skip"):
                        s = None
                    cells.append(s or {"key": key, "label": label, "main": "", "missing": True, "conflict": False,
                                       "vals": [], "sub": self.seats_note(p) if key == "parking" else "", "more": False,
                                       "closed": False, "tel": ""})
                    if s:
                        cells[-1]["label"] = label
                th = present.thumb(p["e"]["_photos"][0]) if p["e"].get("_photos") else None
                if th:
                    n_photo += 1
                    lics.add(th["type"])
                rid = f"r{it['i']}"
                recs.append({"p": p, "e": p["e"], "id": rid, "name": p["name"], "path": p["path"],
                             "type": self.type_label(p["e"]), "area": self.area(p["e"]), "photo": th,
                             "cells": cells,
                             # the Korean list's filter keys (Korean values: one URL vocabulary in every version)
                             "tags": it["tags"], "region": it["region"], "themes": it["themes"], "flags": it["flags"],
                             "dishes": it.get("dishes") or [], "geo": p["e"]["_geo"]})
                if p["e"]["_geo"]:
                    points.append({"lat": p["e"]["_geo"]["lat"], "lng": p["e"]["_geo"]["lng"], "name": p["name"],
                                   "url": p["path"], "id": rid, "kind": kind, "r": it["region"]})
            if recs:
                groups.append({"name": self.region_name(g["name"]), "id": g["id"], "recs": recs})
        count = sum(len(g["recs"]) for g in groups)
        cols = [(key, self.slot_label({"kind": kind}, key)) for key, _ in present.KF_LIST_COLS[kind]]
        flat = [r for g in groups for r in g["recs"]]
        tagc = Counter(t for r in flat for t in r["tags"])
        regc = Counter(r["region"] for r in flat)
        themec = Counter(t for r in flat for t in r["themes"])
        ck = present.LIST_CFG[kind]["check"][0]
        forms = self.t.forms(f"count_{kind}")
        filters = present.filter_vm(
            count, [(t, lab, n) for t, n in tagc.most_common() if n >= 2 and (lab := self.tag_label(t))],
            [(r, self.region_name(r), regc[r]) for r in S.region_names if regc[r]],
            [(s, self.T(f"theme.{s}.name", track=True), n) for s, n in themec.most_common()
             if kind == "attraction" and self.T(f"theme.{s}.name")],
            (ck, self.T(f"LIST_CFG.{kind}.check", track=True), sum(1 for r in flat if r["flags"].get(ck))),
            len(points), LC.LIST_WORDS[self.loc.code], forms,
            dishes=present.dish_chips(flat, present.dish_groups(S.site),
                                      lambda g: squash_ws((g.get("names") or {}).get(self.loc.code))))
        filters["result"] = self.t.sn(f"count_{kind}", count)
        return {"kind": kind, "groups": groups, "count": count, "cols": cols, "points": points, "n_geo": len(points),
                "far_label": squash_ws((C.far or {}).get("label")), "none_label": C.none_label, "filters": filters,
                "map_open": len(points) >= 0.3 * max(1, count), "n_photo": n_photo,
                "lics": [self.lic("KOGL-1") if t == 1 else self.lic("KOGL-3") for t in sorted(lics)]}

    # ---- guides
    def guide_vm(self, x: dict) -> dict:
        S, g, rec, loc = self.S, x["g"], x["rec"], self.loc
        ss = sentences(rec.get("summary"), loc)
        items = []
        for i, it in enumerate(rec.get("items") or [], 1):
            p = self.place_by_ko_slug.get(it.get("place_slug") or "")
            t = S.ent_by_slug.get(it.get("place_slug") or "")
            name = p["name"] if p else (self.fallback_name(t["name"]) if t else "")
            ko_name = (t or {}).get("name", "")
            if not name:
                rows = (self.recs["places"] or {})
                name = next((squash_ws(r.get(loc.name_key)) for r in rows.values() if r.get("slug") == it.get("place_slug")), "")
            items.append({"n": i, "p": p, "name": name, "name_ko": ko_name if not p else "", "reason": squash_ws(it.get("reason")),
                          "path": p["path"] if p else "", "kf": self.key_facts(p, "card") if p else None,
                          "type": self.type_label(p["e"]) if p else "", "area": self.area(p["e"]) if p else "",
                          "photo": self.photos(p)[0] if p and p["e"].get("_photos") else None})
        pts = [{"lat": it["p"]["e"]["_geo"]["lat"], "lng": it["p"]["e"]["_geo"]["lng"], "name": it["name"],
                "url": it["path"], "n": it["n"], "kind": it["p"]["e"].get("kind"), "id": it["p"]["e"]["slug"]} for it in items
               if it["p"] and it["p"]["e"]["_geo"]]
        # the reading layer (present.rich / guide_sections, the Korean guide's components): the answer line, sentence
        # bullets with figures emphasised and the guide's places linked, mini cards
        uniq = list({it["p"]["e"]["id"]: it["p"] for it in items if it["p"]}.values())
        names = [{"name": p["name"], "path": p["path"], "id": p["e"]["id"]} for p in uniq]
        cards = {}
        for p in uniq:
            ph = self.photos(p)
            cards[p["e"]["id"]] = present.mini_card(p["e"], self.key_facts(p, "card"), p["name"], p["path"],
                                                    self.type_label(p["e"]), self.area(p["e"]),
                                                    {**present.thumb(ph[0]), "lic": ph[0]["lic"]} if ph else None)
        heads = [(squash_ws(b.get("heading")), [squash_ws(t) for t in str(b.get("text") or "").split("\n") if t.strip()])
                 for b in rec.get("body") or []]
        split = sentences_en if loc.code == "en" else loc.sentences
        reading = present.guide_reading(ss, heads, names, cards, loc.code, split, len(items))
        cn = self.chapter_notes({})
        faqs = [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a")), "n": cn.ref(f.get("source"))}
                for f in rec.get("faq") or [] if squash_ws(f.get("q")) and squash_ws(f.get("a"))]
        sources, entry_hosts = [], set()
        for s in rec.get("sources") or []:
            if not s.get("url"):
                continue
            src = {"name": no_hangul(squash_ws(s.get("name"))) or url_domain(s.get("url")), "url": s["url"]}
            ent = official_entry(s["url"], loc.code)
            host = urlsplit(s["url"]).hostname
            if ent and host not in entry_hosts:   # once per site: at its first cited page
                entry_hosts.add(host)
                src.update(entry=ent[1], entry_lang=LC.get(ent[0]).html, entry_label=LC.get(ent[0]).label)
            sources.append(src)
        return {**reading, "x": x, "g": g, "rec": rec, "label": squash_ws(rec.get("label")), "title": squash_ws(rec.get("title")),
                "summary": squash_ws(rec.get("summary")), "lede": ss[0] if ss else "", "dek": loc.sjoin.join(ss[1:]),
                "body": [{"heading": squash_ws(b.get("heading")), "text": str(b.get("text") or "")} for b in rec.get("body") or []],
                "places": items, "points": pts, "faqs": faqs, "faq_notes": cn.items, "sources": sources,
                "checked": g.get("_page_date") or "", "reviewed_at": g.get("reviewed_at") or "",
                "translated_at": rec.get("translated_at") or "", **self.book_vm(booking.guide_targets(S, g))}

    # ---- courses
    def cv(self, x: dict) -> dict:
        """course_vm(x), computed once per course (every place page on the course reads it)."""
        cid = x["c"]["id"]
        if cid not in self._cv:
            self._cv[cid] = self.course_vm(x)
        return self._cv[cid]

    def cw(self, key: str, n: int | None = None, **kw) -> str:
        """The course pages' words in this language (locales.COURSE_WORDS)."""
        return LC.course_word(self.loc.code, key, n, **kw)

    def day_label(self, day: str) -> str:
        """The source's '2일차(1안)' in this language ('Day 2, option 1'); '' when it is not that form."""
        m = re.fullmatch(r"(\d+)일차(?:\((\d+)안\))?", squash_ws(day))
        if not m:
            return ""
        return self.cw("day_opt", n=int(m.group(1)), k=m.group(2)) if m.group(2) else self.cw("day", n=int(m.group(1)))

    def stop_guide(self, g: dict | None) -> dict | None:
        """A Korean stop / course guide reference (present._stop_guide) as this version's guide page, or None."""
        x = self.guides.get((g or {}).get("id") or "")
        if not x:
            return None
        title = squash_ws(x["rec"].get("label")) or squash_ws(x["rec"].get("title"))
        return {"name": title, "path": x["path"] + (f"#{g['frag']}" if g.get("frag") else "")}

    def course_vm(self, x: dict) -> dict:
        S, c, rec = self.S, x["c"], x["rec"]
        cv = S.course_vms.get(c["slug"]) or {}
        stops_en = rec.get("stops") or []
        rows, stops = [], []
        day_now = ""
        for i, s in enumerate(c.get("stops") or []):
            se = stops_en[i] if i < len(stops_en) else {}
            t = S.ent_by_slug.get(s.get("place_slug") or "")
            kind = present.stop_kind(squash_ws(s.get("name")), t, s.get("kind") or "")
            name = squash_ws(se.get("name")) or (self.fallback_name(s.get("name")) if s.get("name") else "")
            note = squash_ws(se.get("note"))
            day = squash_ws(str(s.get("day") or ""))
            # the source's day / option heading (F09-b), or its plain schedule number (a stop's `day` 1, 2: the Korean
            # page's '일정 2', here the word for the itinerary and the number — nothing is said about nights)
            label = self.day_label(day) or (f"{self.cw('day_head')} {day}" if day.isdigit() else "")
            if day and day != day_now and label:
                rows.append({"sep": True, "kind": "day", "kind_label": label, "name": "", "note": ""})
                day_now = day
            if kind != "place":
                rows.append({"sep": True, "kind": kind, "kind_label": self.T(f"STOP_KIND_LABELS.{kind}", kind.title()),
                             "name": name, "note": note})
                continue
            p = self.own(t)
            st = {"sep": False, "n": len(stops) + 1, "name": name, "note": note, "p": p, "t": t,
                  "path": p["path"] if p else "", "geo": t["_geo"] if t else None,
                  "kf": self.key_facts(p, "card") if p else None, "photo": self.photos(p)[0] if p and t.get("_photos") else None,
                  "type": self.type_label(t) if t else "", "area": self.area(t) if t else "",
                  "place_name": p["name"] if p else "",
                  # an unlinked stop: a map search for its Korean name and the city, as the Korean page's search (F09-c)
                  "search": "" if t else "https://www.google.com/maps/search/?" + urlencode(
                      {"api": "1", "query": f"{squash_ws(s.get('name'))} {self.city.region}".strip()}),
                  "see": [{"name": o["name"], "path": o["path"], "id": o["e"]["id"]}
                          for o in (self.own(S.ent_by_slug.get(k)) for k in s.get("see") or []) if o]}
            stops.append(st)
            rows.append(st)
        ko_stops = cv.get("stops") or []
        for st, ks in zip(stops, ko_stops):   # straight-line legs from the Korean course model (same stops, same order)
            st["next_m"], st["prev_m"] = ks.get("next_m"), ks.get("prev_m")
            # the breaks between two options of a day and the optional stop (present.course_vm): no leg across them
            st["brk"], st["optional"], st["day"] = ks.get("brk", False), ks.get("optional", False), ks.get("day", "")
            st["guide"] = self.stop_guide(ks.get("guide"))
        s0 = next((s for s in stops if s["geo"]), None)
        first_route = {"n": s0["n"], "name": s0["name"],
                       "url": "https://www.google.com/maps/dir/?" + urlencode({"api": "1", "destination": f"{s0['geo']['lat']},{s0['geo']['lng']}"}),
                       "place": (s0["t"] or {}).get("id", "")} if s0 else None
        # the course map as on the Korean page (present.course_map): numbered as the stop list, only when at least
        # half of the stops have coordinates
        cmap = present.course_map(stops)
        src = present.course_source(S, c)
        # a summary_auto course (the Korean summary is a template sentence) is described the way the Korean page
        # describes it (present.course_lede): computed from the stops' coordinates; a written summary is kept
        summary = squash_ws(rec.get("summary"))
        if c.get("summary_auto") or not summary:
            summary = self.course_lede(stops, cv) or summary
        tk = cv.get("taketime")
        return {"x": x, "c": c, "rec": rec, "name": squash_ws(rec.get("name")), "group": squash_ws(rec.get("group")),
                "duration": squash_ws(rec.get("duration")), "summary": summary, "rows": rows,
                "stops": stops, "n_places": len(stops), "total": cv.get("total") or 0, "measured": cv.get("measured") or 0,
                "legs_possible": cv.get("legs_possible") or 0, "complete": bool(cv.get("complete")),
                # whose coordinates the measured legs join: the TourAPI-only wording stays legs_measured, any other
                # provider names them all (legs_measured_src)
                "geo_src": self.loc.list_sep.join(self.provider(x) for x in cv.get("geo_providers") or []),
                "geo_mixed": (cv.get("geo_providers") or []) not in ([], [GEO_PROVIDER["TourAPI"]]),
                "first": stops[0]["name"] if stops else "", "last": stops[-1]["name"] if stops else "",
                "first_route": first_route, "map": cmap,
                "orig_url": src["orig_url"], "orig_name": self.en_name(src["orig_name"]), "official": src["official"],
                "collected": (c.get("original") or {}).get("collected_at") or "", "reviewed_at": c.get("reviewed_at") or "",
                "translated_at": rec.get("translated_at") or "",
                # F09-b: the one duration the source gives ('소요시간 : 12시간')
                "taketime": {"text": self.cw("hours_n", tk["hours"]), "url": tk.get("source_url") or "",
                             "name": self.provider(tk.get("source_name")), "date": tk.get("checked_at") or ""}
                if tk and tk.get("hours") else None,
                **self.course_week(stops, cv), "move": self.course_move(stops, cv), "cw": LC.COURSE_WORDS[self.loc.code],
                **self.book_vm(booking.course_targets(S, c))}

    def course_week(self, stops: list[dict], cv: dict) -> dict:
        """F09-a (QA 2026-10-15): the Korean course page's closed days by weekday in this language — present.week_grid
        over the same linked stops (the cells come from the Korean parse), each row named and linked as this version's
        page with this version's closed-day value (or the sources-differ note); the busiest day as the datarow note
        (present.course_vm's rule: most stops, the earlier weekday on a tie)."""
        linked = [s for s in stops if s["t"]]
        W = present.week_grid([s["t"] for s in linked])
        week = None
        if W:
            rows = []
            for r, s in zip(W["rows"], linked):
                p = s["p"]
                v = present.one_value(self.slot(p, "closed")) if p and r["stated"] and not r["contested"] else None
                rows.append({"name": p["name"] if p else s["name"], "path": p["path"] if p else "", "cells": r["cells"],
                             "contested": r["contested"], "stated": r["stated"],
                             "text": v["main"] if v and not v.get("varies") else ""})
            week = {**W, "rows": rows,
                    "per_day": [(i, n) for i, n in enumerate(W["per_day"].values())]}
        by_day = cv.get("closed_by_day") or {}
        note = ""
        if by_day:
            day, cnt = max(by_day.items(), key=lambda kv: (kv[1], -present.WEEK.index(kv[0])))
            note = self.cw("closed_n", cnt, day=LC.COURSE_WORDS[self.loc.code]["closed_day"][present.WEEK.index(day)])
        return {"week": week, "closed_note": note}

    def course_move(self, stops: list[dict], cv: dict) -> dict | None:
        """F09 (QA 2026-10-15): the Korean page's '차 없이 다니기' (present.course_move) in this language — the nearest bus
        stops of the stops (names stay Korean: lang="ko" with their romanization), every measured leg with a Google Maps
        public-transport link between the two stored coordinates (the map computes route and time), the city bus
        timetable's first and last buses, this version's guides, the one 'Not listed' line, the sources — each named
        in this language from the Korean source name the block carries (Site.provider: strings 'provider:<name>')."""
        S = self.S
        mv = present.course_move(S, cv)
        if mv is None:
            return None
        by_n = {s["n"]: s for s in stops}
        romanized = lambda ko: {"ko": ko, "rr": self.fallback_name(re.sub(r"[()]", " ", ko)).strip()}  # noqa: E731
        bus = lambda rows: [{"n": r["n"], "name": by_n[r["n"]]["place_name"] or by_n[r["n"]]["name"],  # noqa: E731
                             "path": by_n[r["n"]]["path"], "id": r["id"],
                             "bus": [{**b, "stop": romanized(b["name"])} for b in r["bus"]]} for r in rows]
        legs = [{"a": by_n[l["a"]["n"]], "b": by_n[l["b"]["n"]], "d": l["d"], "long": l["long"],
                 "guide": self.stop_guide(l["guide"]),
                 "url": google_transit_url(l["a"]["geo"]["lat"], l["a"]["geo"]["lng"], l["b"]["geo"]["lat"], l["b"]["geo"]["lng"])}
                for l in mv["legs"]]
        row = lambda t: {**t, "stop": romanized(t["stop"]), "wd": t["weekday"].replace("~", "–"),  # noqa: E731
                         "we": t["weekend"].replace("~", "–"), "wd_n": self.cw("runs", t["weekday_n"]),
                         "we_n": self.cw("runs", t["weekend_n"])}
        routes = [{**R, "out": [row(t) for t in R["out"]], "back": [row(t) for t in R["back"]],
                   "alts": [{**t, "stop": romanized(t["stop"]), "every_l": self.past_hour(t.get("every")),
                             "alt_l": self.past_hour((t.get("alt") or {}).get("value")),
                             "provider": self.provider((t.get("alt") or {}).get("provider"))} for t in R["alts"]]}
                  for R in mv["routes"]]
        guides = [g for g in (self.stop_guide(g) for g in mv["guides"]) if g]
        missing = list(LC.COURSE_WORDS[self.loc.code]["missing_items"])[:len(mv["missing"])]
        tt = mv["tt"] or {}
        # the Korean names of the block's sources (present.course_move sources, by source key) in this language
        srcs = dict(zip(mv.get("source_keys") or [], mv.get("sources") or []))
        return {"lead": bus(mv["lead"]), "rest": bus(mv["rest"]), "legs": legs, "routes": routes, "guides": guides,
                "missing": missing, "bus_radius": mv["bus_radius"], "tel": mv["tel"],
                "leg_word": LC.NEAR_WORDS[self.loc.code]["leg"],
                "src_stops": self.provider(srcs.get("stops")) if srcs.get("stops") else "",
                "src_tt": self.provider(srcs.get("timetable") or tt.get("name")), "tt_url": tt.get("url") or "",
                "tt_provider": self.provider(tt.get("provider"))}

    def past_hour(self, ko: str | None) -> str:
        """'매시 35분' in this language (COURSE_WORDS past_hour); '' for another form."""
        m = re.fullmatch(r"매시\s*(\d{1,2})분", squash_ws(ko))
        return self.cw("past_hour", m=m.group(1)) if m else ""

    def course_lede(self, stops: list[dict], cv: dict) -> str:
        """present.course_lede in this language: how many first stops lie within 1 km of the start, and the longest
        leg when every leg is measured (straight lines between stored coordinates); else where the stops start and end."""
        if not stops:
            return ""
        t, loc = self.t, self.loc
        cluster = 1
        if stops[0]["geo"]:
            while cluster < len(stops) and stops[cluster]["geo"] and \
                    present.hav(stops[0]["geo"], stops[cluster]["geo"]) <= 1000:
                cluster += 1
        legs, pairs = cv.get("legs") or [], cv.get("pairs") or []
        longest = ""
        if cv.get("complete") and cv.get("measured") and len(pairs) == len(legs) and stops:
            i = max(range(len(legs)), key=lambda j: legs[j] or 0)
            if legs[i]:   # the Korean pair's stops, by number (no leg across a break or into an optional stop)
                a, b = (stops[k["n"] - 1] for k in pairs[i])
                longest = t.s("lede_longest", a=a["name"], b=b["name"], d=loc.dist(legs[i]))
        near = t.sn("lede_near", cluster) if cluster > 2 else ""
        if near and longest:
            return t.s("lede_both", near=near, longest=longest)
        if near:
            return t.s("lede_one", text=near)
        if longest:
            return t.s("lede_one", text=f"{longest[0].upper()}{longest[1:]}")
        return t.sn("lede_ends", len(stops), a=stops[0]["name"], b=stops[-1]["name"])

    # ---- events
    def events_vm(self) -> dict:
        """Every current series: the newest dated edition's facts (from the record; dates from the Korean), both
        values and the organizer note where sources differ, highlights, the usual timing, earlier editions."""
        from . import build as B
        S, t = self.S, self.t
        out_up, out_past = [], []
        ko_ev = {ev["id"]: ev for ev in getattr(S, "events_all", []) or []}
        note_default = EVENT_CONFLICT_NOTE if self.loc.code == "en" else self.loc.event_conflict
        for x in self.series:
            sr, rec = x["sr"], x["rec"]
            ko = sr["newest"]
            new = rec.get("newest") or {}
            ev = ko_ev.get(new.get("id")) or ko
            alts = rec.get("alternatives") or {}
            src_name = squash_ws(ev.get("source_name"))
            primary = self.event_source(rec, src_name)
            rows = []
            for field, label in (("period_text", "ev_dates"), ("playtime", "ev_time"), ("fee", "ev_fee"),
                                 ("place_name", "ev_venue"), ("address", "ev_address"), ("sponsor", "ev_organizer"),
                                 ("tel", "ev_contact")):
                value = squash_ws(new.get(field))
                a = alts.get("period" if field == "period_text" else field) or {}
                if not value and not a:
                    continue
                row = {"field": field, "label": t.s(label), "value": value, "blocks": [], "note": ""}
                if a.get("values"):
                    row["blocks"] = [{"provider": primary, "value": value}] if value else []
                    for v, pr in zip(a.get("values") or [], a.get("providers") or []):
                        row["blocks"].append({"provider": self.event_source(rec, pr), "value": squash_ws(v)})
                    row["note"] = squash_ws(a.get("note")) or note_default
                rows.append(row)
            last = B.event_last_day(ev) if ev.get("start_date") else ""
            # sources: the names in this language, linked when a Korean record of the series gives the URL
            urls: dict[str, str] = {}
            for r in sr["editions"]:
                if r.get("source_name") and r.get("source_url"):
                    urls.setdefault(squash_ws(r["source_name"]), r["source_url"])
                for a in r.get("also_sources") or []:
                    if a.get("name") and a.get("url"):
                        urls.setdefault(squash_ws(a["name"]), a["url"])
                for u in r.get("usual") or []:
                    if u.get("source_name") and u.get("source_url"):
                        urls.setdefault(squash_ws(u["source_name"]), u["source_url"])
            sources = [{"name": no_hangul(squash_ws(en)) or self.provider(ko_name), "url": urls.get(squash_ws(ko_name), "")}
                       for ko_name, en in (rec.get("sources") or {}).items()]
            places = [self.place_by_ko_slug[s] for s in self._series_places(x) if s in self.place_by_ko_slug]
            item = {"x": x, "anchor": x["anchor"], "series_name": squash_ws(rec.get("series_name")),
                    "name": squash_ws(new.get("name")) or squash_ws(rec.get("series_name")), "rows": rows,
                    "start": ev.get("start_date") or "", "end": ev.get("end_date") or "", "last": last,
                    # the end the source gives only as a month ('2026-10'): shown as the month; last (its final day)
                    # only sorts and splits upcoming / past (build.event_last_day)
                    "end_month": B.event_end_month(ev),
                    "highlights": [squash_ws(h) for h in rec.get("highlights") or [] if squash_ws(h)],
                    "program_notes": [squash_ws(h) for h in rec.get("program_notes") or [] if squash_ws(h)],
                    "notes": [squash_ws(n) for n in new.get("notes") or [] if squash_ws(n)],
                    "usual": [u for u in rec.get("usual") or [] if squash_ws(u.get("text"))],
                    "editions": [ed for ed in rec.get("editions") or [] if squash_ws(ed.get("name"))],
                    "sources": sources, "places": places, "checked": sr.get("checked") or latest_date(sr["editions"]),
                    "flag": any(r["blocks"] for r in rows),
                    "ko_path": (self.ko_series.get(x["slug"]) or {}).get("_path", ""),
                    "homepage": web_url(ev.get("homepage")) if not HANGUL.search(web_url(ev.get("homepage")) or "") else ""}
            (out_up if last and last >= S.today else out_past).append(item)
        out_up.sort(key=lambda r: (r["start"], r["name"]))
        out_past.sort(key=lambda r: (r["start"], r["name"]), reverse=True)
        # held around this time one or two years ago, nothing newer dated (present.season_rows): links to their cards
        season = sorted((a, r["name"], r) for r in out_past if r["start"] and (a := present.season_ahead(r["start"], S.today)) is not None)
        return {"upcoming": out_up, "past": out_past, "season": [r for _, _, r in season], "n": len(out_up) + len(out_past),
                "checked": max((r["checked"] or "" for r in out_up + out_past), default="")}


En = Site   # the English site's first name (tests and tools import it)


def latest_date(records: list[dict]) -> str:
    return max((squash_ws(r.get("checked_at")) for r in records if r.get("checked_at")), default="")


def course_kinds(rows: list[dict]) -> tuple[bool, bool]:
    """(day trips, overnight trips): whether the courses include any of each, by their Korean duration (당일 ·
    1박 2일 · 2박 3일) — the course pages' and the home's words say only what the data has."""
    durs = {squash_ws(r["c"].get("duration")) for r in rows}
    return "당일" in durs, bool(durs & {"1박 2일", "2박 3일"})


# ---------------------------------------------------------------------------------------------- every version
class Intl:
    """The versions this build has (in menu order) and what their pages share: hreflang sets and the language menu.
    skipped: versions not built for missing UI words ({code: keys}); off: versions whose data/<city>/<code>/ exists
    but site.json `languages` leaves out (the operator switches a version on there)."""

    def __init__(self, sites: dict[str, Site], skipped: dict[str, list[str]] | None = None,
                 off: list[str] | None = None):
        self.sites = sites
        self.skipped = skipped or {}
        self.off = list(off or [])

    def __bool__(self) -> bool:
        return bool(self.sites)

    def site_of(self, path: str) -> Site | None:
        return self.sites.get(LC.code_of_path(path))

    def ko_path(self, path: str) -> str | None:
        site = self.site_of(path)
        if site is None:
            return path
        return site.en2ko.get(path) or next((k for k, v in site.menu_twins.items() if v == path), None)

    def alternates(self, path: str) -> list[dict]:
        """hreflang links for a page that has at least one twin: ko, every version with a twin, x-default (= ko)."""
        ko = self.ko_path(path)
        if not ko:
            return []
        twins = [(s.loc.html, s.ko2en[ko]) for s in self.sites.values() if ko in s.ko2en]
        if not twins:
            return []
        S = next(iter(self.sites.values())).S
        return ([{"hreflang": "ko", "href": S.abs(ko)}] + [{"hreflang": h, "href": S.abs(p)} for h, p in twins]
                + [{"hreflang": "x-default", "href": S.abs(ko)}])

    def menu(self, path: str) -> list[dict]:
        """The language menu of a page: Korean and every version, each its counterpart of this page; a version
        without one links its list of the same kind (else its home) with a note 'Guides · not translated' in its own
        words (Site.menu_link; none on the 404 page). The page's own version is marked current. Empty when the build
        has no other version."""
        if not self.sites:
            return []
        own = self.site_of(path)
        ko = self.ko_path(path) if own else path
        items = [{"code": "ko", "hreflang": "ko", "label": LC.KO["label"], "current": own is None,
                  "href": path if own is None else (ko or "/"), "note": ""}]
        for code, s in self.sites.items():
            href, note = (path, "") if s is own else (s.menu_link(ko) if ko else (s.home, ""))
            if path == "/404.html":
                note = ""
            items.append({"code": code, "hreflang": s.loc.html, "label": s.loc.label, "current": s is own,
                          "href": href, "note": note})
        return items


def _switched_on(S, data_dir: Path, code: str) -> bool:
    """A version's switch: site.json `languages` lists the code and data/<city>/<code>/places.json exists."""
    return code in S.city.languages and (Path(data_dir) / code / "places.json").is_file()


def load_all(S, data_dir: Path) -> Intl:
    """Every version this build has, in menu order (locales.ORDER): switched on (_switched_on) and with complete UI
    words (a version whose strings.json lacks some 'chrome.<key>' rows is not built; build stats list the missing
    keys). Every version reads the Korean records' own slugs, so none depends on another."""
    data_dir = Path(data_dir)
    sites: dict[str, Site] = {}
    skipped: dict[str, list[str]] = {}
    off: list[str] = []
    for code in LC.ORDER:
        if not (data_dir / code / "places.json").is_file():
            continue
        if not _switched_on(S, data_dir, code):
            off.append(code)
            continue
        site = Site(S, data_dir, LC.get(code))
        if site.t.missing:
            skipped[code] = site.t.missing
            for e in S.entities:
                (e.get("_intl") or {}).pop(code, None)
                if code == "en":
                    e.pop("_en", None)
            continue
        sites[code] = site
    return Intl(sites, skipped, off)


def load(S, data_dir: Path) -> Site | None:
    """The English site for this build, or None — no /en/ and no hreflang — unless site.json `languages` lists "en"
    and data/<city>/en/places.json exists (the sample data and an English-less city have neither)."""
    if not _switched_on(S, data_dir, "en"):
        return None
    return Site(S, data_dir, EN)


# ---------------------------------------------------------------------------------------------- JSON-LD
def _webpage(site: Site, url: str, title: str, about: str | None = None, modified: str = "", based_on=None,
             reviewed: str = "") -> dict:
    S = site.S
    node = {"@type": "WebPage", "@id": url, "url": url, "name": title, "inLanguage": site.loc.html,
            "isPartOf": {"@id": f"{S.site_url}{site.home}#website"}, "publisher": jsonld.org_ref(S.site_url)}
    if about:
        node["about"] = {"@id": about}
    if modified:
        node["dateModified"] = modified
    if reviewed:
        node["lastReviewed"] = reviewed
    based_on = [u for u in (based_on or []) if u]
    if based_on:
        node["isBasedOn"] = based_on if len(based_on) > 1 else based_on[0]
    return node


def _city(site: Site) -> dict:
    """The one City node of the site (jsonld.CITY_NODE_ID, defined on the Korean home), named in this language."""
    return {"@id": f"{site.S.site_url}/{jsonld.CITY_NODE_ID}", "@type": "City", "name": site.region}


def _author(site: Site) -> dict:
    """The editor in charge (site.json editor) as on the footer, else the publisher."""
    S = site.S
    if site.loc.code == "en":
        return jsonld.author_node(S.site, S.site_url, "en")
    ed = S.site.get("editor") or {}
    if not ed.get("name"):
        return jsonld.org_ref(S.site_url)
    return {"@type": "Person", "name": ed["name"], "worksFor": jsonld.org_ref(S.site_url),
            "jobTitle": site.t.s("editor_role")}


def place_ref(p: dict, *, city) -> dict:
    return {"@id": f"{p['url']}#place", "@type": schema_type(p["e"], city=city), "name": p["name"]}


def place_graph(site: Site, vm: dict, title: str, crumbs: list, images: list[dict]) -> dict:
    S, p, e, rec = site.S, vm["p"], vm["e"], vm["rec"]
    facts = rec.get("facts") or {}
    url = p["url"]
    node = {"@type": schema_type(e, city=site.city), "@id": f"{url}#place", "name": p["name"], "alternateName": e["name"], "url": url}
    if vm["summary"]:
        node["description"] = vm["summary"]
    addr = squash_ws((facts.get("address") or {}).get("value"))
    if addr:
        node["address"] = {"@type": "PostalAddress", "streetAddress": addr, "addressCountry": "KR"}
    if e["_geo"]:
        node["geo"] = {"@type": "GeoCoordinates", "latitude": e["_geo"]["lat"], "longitude": e["_geo"]["lng"]}
        node["hasMap"] = f"https://www.google.com/maps/search/?api=1&query={e['_geo']['lat']},{e['_geo']['lng']}"
    phones = [phone_intl(x) for x in extract_phones((facts.get("infocenter") or {}).get("value"))]
    if phones and not (facts.get("infocenter") or {}).get("alternatives"):
        node["telephone"] = phones if len(phones) > 1 else phones[0]
    if e.get("kind") == "stay":
        for key, prop in (("checkin", "checkinTime"), ("checkout", "checkoutTime")):
            v = squash_ws((facts.get(key) or {}).get("value"))
            if re.fullmatch(r"\d{2}:\d{2}", v) and not (facts.get(key) or {}).get("alternatives"):
                node[prop] = v
    ko = e.get("facts") or {}
    hours = []
    ut = squash_ws((facts.get("usetime") or {}).get("value"))
    if not (jsonld.conflicted(e, "usetime") or jsonld.conflicted(e, "restdate")):
        hours = [h for h in jsonld.opening_hours(ko.get("usetime"), ko.get("restdate"))]
        if not all(h["opens"] in ut and h["closes"] in ut for h in hours):
            hours = []
    if hours:
        node["openingHoursSpecification"] = hours
    typed = {"usetime", "restdate"} if hours else set()
    props = [{"@type": "PropertyValue", "name": site.fact_label(k), "value": squash_ws(facts[k]["value"])}
             for k in jsonld.PROP_KEYS if k in facts and squash_ws(facts[k].get("value")) and k not in typed]
    if props:
        node["additionalProperty"] = props
    if images:
        kto = site.t.s("kto")
        node["image"] = [{"@type": "ImageObject", "contentUrl": im["url"], "creditText": kto, "copyrightNotice": kto,
                          "creator": {"@type": "Organization", "name": kto},
                          "license": (lic := jsonld.LICENSE_URLS["KOGL-1" if im["type"] == 1 else "KOGL-3"]),
                          "acquireLicensePage": lic}
                         for im in images]
    awards = [d["label"] for d in vm["designations"]]   # the labels the page shows (as the Korean `award`)
    if awards and jsonld.AWARD_TYPES & set(node_types(node)):
        node["award"] = awards if len(awards) > 1 else awards[0]
    official = e.get("official") or {}
    same = [u for u in ((e.get("original") or {}).get("source_url"), official.get("visitkorea_url")) if u]
    if same:
        node["sameAs"] = same
    node["containedInPlace"] = _city(site)
    parent = site.own(e.get("_parent")) if e.get("_rel") == "inside" else None
    if parent:   # pipeline/relations.py 'inside': the parent's page here, then the city (same_building: neither)
        node["containedInPlace"] = [place_ref(parent, city=site.city), _city(site)]
    parts = [cp for cp in (site.own(c) for c in e.get("_parts") or []) if cp]
    if parts:
        node["containsPlace"] = [place_ref(cp, city=site.city) for cp in parts]
    graph = [_webpage(site, url, title, f"{url}#place", vm["facts_checked"], [(e.get("original") or {}).get("source_url")],
                      vm["reviewed_at"]), node, jsonld.breadcrumb(crumbs)]
    if vm["faqs"]:
        graph.append(jsonld.faq_page(vm["faqs"], url))
    return {"@context": "https://schema.org", "@graph": graph}


def simple_graph(site: Site, url: str, title: str, crumbs: list, item_urls: list[str] | None = None) -> dict:
    graph = [_webpage(site, url, title), jsonld.breadcrumb(crumbs)]
    if item_urls:
        graph.append(jsonld.item_list(item_urls, url))
    return {"@context": "https://schema.org", "@graph": graph}


# ---------------------------------------------------------------------------------------------- pages
def _title(base: str, labels: list[str], limit: int = 70, loc: LC.Locale = EN) -> str:
    """'<name>: Hours, Fees, Parking' with as many labels as fit in `limit` characters."""
    for n in range(len(labels), 0, -1):
        t = f"{base}{loc.colon}{loc.list_sep.join(labels[:n])}"
        if len(t) <= limit:
            return t
    return base


def answer_description(summary: str, rows: list[dict], limit: int = 160, loc: LC.Locale = EN) -> str:
    """The summary's first sentence (the next one too while short), then up to two short fact values no other
    source contradicts ('Hours: 09:00–18:00.'). Whole sentences and whole values only; a first sentence longer
    than the limit is cut back to its first clause (or its last whole word)."""
    ss = sentences(summary, loc)
    stop, join = ("。", "") if loc.cjk else (".", " ")
    out = ss[0] if ss else ""
    if len(out) > limit:
        if loc.cjk:
            cut = re.split(r"[、，；]", out)[0]
            out = cut if len(cut) <= limit - 1 else out[: limit - 1]
            return out.rstrip("、，；。") + stop
        cut = re.split(r",\s|;\s|\s—\s", out)[0]
        out = cut if len(cut) <= limit - 1 else out[: limit - 1].rsplit(" ", 1)[0]
        return out.rstrip(".,;") + "."
    short = 30 if loc.cjk else 60
    for nxt in ss[1:]:
        if len(out) >= short or len(out) + len(join) + len(nxt) > limit:
            break
        out = f"{out}{join}{nxt}"
    added = 0
    for r in rows:
        if added == 2:
            break
        if r["conflict"] or r["key"] in ("address", "infocenter", "homepage", "reservationurl") or not r["text"]:
            continue
        v = squash_ws(r["text"]).rstrip(".。")
        s = f"{r['label']}{loc.colon}{v}{stop}"
        if "\n" in r["text"] or len(v) > 30 or len(out) + len(join) + len(s) > limit or v in out:
            continue
        out, added = f"{out}{join}{s}", added + 1
    return out


def latest_of(dates) -> str | None:
    found = [squash_ws(str(d)) for d in dates if d and squash_ws(str(d))]
    return max(found) if found else None


class Pages:
    """Renders every page of one version into the build's output folder and records the sitemap rows."""

    def __init__(self, site: Site, env, out: Path, intl: Intl | None = None):
        self.site, self.en, self.S, self.env, self.out = site, site, site.S, env, out
        self.intl = intl or Intl({site.loc.code: site})
        self.t, self.loc = site.t, site.loc
        self.count = 0
        self.indexable = 0

    def abs(self, path: str) -> str:
        return self.S.abs(path)

    def common(self, page: dict, page_kind: str, path: str) -> dict:
        S, site, loc = self.S, self.site, self.loc
        page.setdefault("alternates", self.intl.alternates(path))
        nav = [(lab, href) for lab, href in site.nav() if self._built(href)]
        # site.json source in this language (the footer and about macros see `site` only): name_l ('' when the Korean
        # source has no name or this version has no name for it), official (its URL is on an official_domains site)
        source = dict(S.site_view.get("source") or {})
        source["name_l"] = site.config_name(source.get("name"), source.get("name_en"))
        source["official"] = bool(site.city.official_label(source.get("url")))
        return {"site": {**S.site_view, "site_name": site.site_name, "brand": site.site_name, "source": source},
                "page": page, "page_kind": page_kind, "noindex": S.cfg["noindex"], "banner": "", "mode": S.mode,
                "lang": loc.html, "og_locale": loc.og, "nav": nav, "nav_current": site.current_nav(page_kind),
                "ctxbtn": None, "has_search": False, "has_videos": False, "tourapi_used": S.tourapi_used,
                "wordmark": site.site_name, "build_date": S.today, "langs": self.intl.menu(path), "en": site,
                "t": site.t, "loc": loc, "region": site.region, "ko_site_name": S.site.get("site_name", ""),
                "home_h1": site.home_h1,
                # the province in this language ('' for a city that is its own 시·도 or without a configured name: the
                # words that need it are left out, never guessed), the city body ('run independently of …'), the
                # courses' shared source and whether it is official (Site.course_src)
                "admin_l": site.admin, "city_l": site.city_body, "course_src": site.course_src,
                # AI art (pipeline/art.py): only the pictures whose langs name this version, with its alt and label
                "art_slots": art.for_lang(S.art, loc.code)}

    def _built(self, href: str) -> bool:
        site = self.site
        for kind, c in LIST_PAGES.items():
            if site.home + c["seg"] == href:
                return bool(site.by_kind[kind])
        return {f"{site.home}guides/": bool(site.guides), f"{site.home}courses/": bool(site.courses),
                f"{site.home}events/": bool(site.series and self.S.events)}.get(href, True)

    def render(self, template: str, path: str, page: dict, page_kind: str, lastmod: str | None = None,
               in_sitemap: bool = True, **ctx) -> None:
        from .build import _write
        code = self.loc.code
        og = None if page.get("image") else art.og_fallback(art.for_lang(self.S.art, code), path, code)
        if og:  # a page without a photo of its own: the version's link-preview illustration (og.default-en, og.ja …;
            # never a place page) with its alt in the version's language
            page.update(image=self.S.abs(og["src"]), image_alt=og["alts"].get(code, ""), image_w=og["w"], image_h=og["h"])
        elif (page.get("image") or "").startswith("/"):
            page["image"] = self.S.abs(page["image"])
        html = self.env.get_template(template).render({**self.common(page, page_kind, path), **ctx})
        _write(self.out, path, html)
        self.count += 1
        if in_sitemap:
            self.S.pages.append((path, lastmod or None))
            self.indexable += 1

    def crumbs(self, *items) -> list:
        return [(self.t.s("home"), self.abs(self.site.home)), *items]

    def _simple(self, path: str, title: str, desc: str, crumbs: list, item_urls: list[str] | None = None) -> dict:
        url = self.abs(path)
        return {"title": title, "description": desc, "canonical": url, "crumbs": crumbs,
                "jsonld": [jsonld.dumps(simple_graph(self.site, url, title, crumbs, item_urls))]}

    # ---- pages
    def place(self, p: dict) -> None:
        site, t, loc = self.site, self.t, self.loc
        vm = site.place_vm(p)
        e = p["e"]
        cfg = site.lists()[vm["kind"]]
        crumbs = self.crumbs((cfg["nav"], self.abs(cfg["path"])), (p["name"], p["url"]))
        labels: list[str] = []
        for r in vm["practical"]:
            if r["key"] == "parking_seats" and parking_seats_half(e) == "seats":
                continue   # a seat count alone answers no parking question (the Korean title: build.entity_ctx)
            lab = site.T(f"TITLE_LABELS.{r['key']}")
            if lab and lab not in labels:
                labels.append(lab)
        qualified = p["name"] if site.region in p["name"] else t.s("name_in_region", name=p["name"], r=site.region)
        title = _title(qualified, labels[:3], loc.title_max, loc)
        if title == qualified and len(qualified) <= loc.title_max - 20:
            title = t.s("visit_information", name=qualified)
        desc = answer_description(vm["summary"], vm["practical"], loc.desc_max, loc) or \
            t.s("place_desc_fallback", name=p["name"], r=site.region)
        images = vm["photos"][:7]
        page = {"title": title, "description": desc, "canonical": p["url"], "og_type": "article",
                "image": next((ph["url"] for ph in vm["photos"] if ph["type"] == 1), vm["photos"][0]["url"] if vm["photos"] else ""),
                "geo": e["_geo"], "geo_placename": f"{site.region} {p['name']}", "crumbs": crumbs, "map": bool(e["_geo"]),
                "jsonld": [jsonld.dumps(place_graph(site, vm, title, crumbs, images))]}
        if p["noindex"]:
            page["robots"] = "noindex, follow"
        self.render("en/place.html.j2", p["path"], page, f"place-{vm['kind']}", e.get("_page_date"),
                    in_sitemap=not p["noindex"], v=vm)

    def lists(self) -> None:
        site, t, loc = self.site, self.t, self.loc
        for kind, cfg in site.lists().items():
            if not site.by_kind[kind]:
                continue
            L = site.list_vm(kind)
            r = site.region
            title = t.s(f"title_{kind}", r=r, n=L["count"])
            crumbs = self.crumbs((cfg["nav"], self.abs(cfg["path"])))
            hub = site.guides.get(site.hub_ids.get(kind, ""))
            urls = [it["p"]["url"] for g in L["groups"] for it in g["recs"]]
            desc = t.sn(f"desc_{kind}", L["count"], r=r)
            page = {**self._simple(cfg["path"], title, desc, crumbs, urls),
                    "image": next((it["photo"]["url"] for g in L["groups"] for it in g["recs"]
                                   if it["photo"] and it["photo"]["type"] == 1), "")}
            lastmod = latest_of([it["e"].get("_page_date") for g in L["groups"] for it in g["recs"]])
            self.render("en/list.html.j2", cfg["path"], page, "places" if kind == "attraction" else f"list-{kind}",
                        lastmod, L=L, cfg=cfg, h1=cfg["h1"], lead=site.T(f"LISTS.{kind}.lead"),
                        hub={"path": hub["path"], "label": squash_ws(hub["rec"].get("label"))} if hub else None)

    def guide_order(self) -> list[dict]:
        """The list hubs' guides first (food · stay · attraction), then the others in file order."""
        hub_ids = list(self.site.hub_ids.values())
        hubs = [self.site.guides[g] for g in hub_ids if g in self.site.guides]
        return hubs + [x for gid, x in self.site.guides.items() if gid not in hub_ids]

    def guides(self) -> None:
        site, t, loc = self.site, self.t, self.loc
        if not site.guides:
            return
        order = self.guide_order()
        rows = []
        home = site.home
        for x in order:
            G = site.guide_vm(x)
            rows.append(G)
            crumbs = self.crumbs((t.s("guides"), self.abs(f"{home}guides/")), (G["title"], x["url"]))
            title = G["title"] if len(G["title"]) <= loc.title_max else t.s("label_in_region", label=G["label"], r=site.region)
            unique = list({it["p"]["url"]: it["p"] for it in G["places"] if it["p"]}.values())
            art_ = {"@type": "Article", "@id": f"{x['url']}#article", "headline": G["title"][:110],
                    "mainEntityOfPage": x["url"], "inLanguage": loc.html, "author": _author(site),
                    "publisher": jsonld.org_ref(self.S.site_url)}
            if G["summary"]:
                art_["description"] = G["summary"]
            if G["checked"]:
                art_["dateModified"] = G["checked"]
            if unique:
                art_["about"] = [place_ref(p, city=site.city) for p in unique]
            srcs = [s["url"] for s in G["sources"] if s.get("url")]
            if srcs:
                art_["isBasedOn"] = srcs
            graph = [art_, jsonld.breadcrumb(crumbs)]
            if unique:
                graph.append(jsonld.item_list([p["url"] for p in unique], x["url"]))
            if G["faqs"]:
                graph.append(jsonld.faq_page(G["faqs"], x["url"]))
            page = {"title": title, "description": answer_description(G["summary"], [], loc.desc_max, loc),
                    "canonical": x["url"], "og_type": "article", "crumbs": crumbs, "map": bool(G["points"]),
                    "image": next((it["photo"]["url"] for it in G["places"] if it["photo"] and it["photo"]["type"] == 1), ""),
                    "jsonld": [jsonld.dumps({"@context": "https://schema.org", "@graph": graph})]}
            self.render("en/guide.html.j2", x["path"], page, "guide", x["g"].get("_page_date"), G=G)
        crumbs = self.crumbs((t.s("guides"), self.abs(f"{home}guides/")))
        page = self._simple(f"{home}guides/", t.s("guides_title", r=site.region),
                            t.sn("guides_desc", len(rows), r=site.region), crumbs, [x["url"] for x in order])
        self.render("en/guides.html.j2", f"{home}guides/", page, "guides",
                    latest_of([x["g"].get("_page_date") for x in order]), rows=rows)

    def courses(self) -> None:
        site, t, loc = self.site, self.t, self.loc
        if not site.courses:
            return
        home = site.home
        vms = []
        for x in site.courses.values():
            C = site.course_vm(x)
            vms.append(C)
            crumbs = self.crumbs((t.s("courses"), self.abs(f"{home}courses/")), (C["name"], x["url"]))
            refs = [place_ref(s["p"], city=site.city) if s["p"] else {"@type": "Place", "name": s["name"]}
                    for s in C["stops"]]
            trip = {"@type": "TouristTrip", "@id": f"{x['url']}#trip", "name": C["name"], "url": x["url"]}
            if C["summary"]:
                trip["description"] = C["summary"]
            if C["orig_url"]:
                trip["isBasedOn"] = C["orig_url"]
            if refs:
                trip["itinerary"] = {"@type": "ItemList", "itemListElement": [
                    {"@type": "ListItem", "position": i, "item": it} for i, it in enumerate(refs, 1)]}
            base = C["name"] if site.region in C["name"] else t.s("region_name", r=site.region, name=C["name"])
            title = _title(base, [t.sn("n_stops_title", C["n_places"])], loc.title_max, loc) \
                if len(base) <= loc.title_max - 10 else base
            page = {"title": title, "description": answer_description(C["summary"], [], loc.desc_max, loc)
                    or t.sn("course_desc_fallback", C["n_places"], name=C["name"]),
                    "canonical": x["url"], "crumbs": crumbs, "map": bool(C["map"]),
                    "image": next((s["photo"]["url"] for s in C["stops"] if s["photo"] and s["photo"]["type"] == 1), ""),
                    "jsonld": [jsonld.dumps({"@context": "https://schema.org", "@graph": [trip, jsonld.breadcrumb(crumbs)]})]}
            self.render("en/course.html.j2", x["path"], page, "course", x["c"].get("_page_date"), C=C)
        groups: dict[str, list] = {}
        for C in vms:
            groups.setdefault(C["duration"] or C["group"] or t.s("courses"), []).append(C)
        grouped = sorted(groups.items(), key=lambda kv: (DURATION_ORDER.get(kv[1][0]["c"].get("duration") or "", 9)
                                                         if kv[1][0]["duration"] else 9, kv[0]))
        crumbs = self.crumbs((t.s("courses"), self.abs(f"{home}courses/")))
        # what the courses are (course_kinds) and whose (Site.course_src: named only when they share one source,
        # official only on an official_domains site) — each a sentence of its own in intl_text
        day, night = course_kinds(vms)
        tkey = "courses_title" if day and night else "courses_title_day" if day else \
            "courses_title_night" if night else "courses_title_plain"
        src = site.course_src
        tail = "" if src["name"] and src["official"] else "_of" if src["name"] else "_plain"
        page = self._simple(f"{home}courses/", t.s(tkey, r=site.region),
                            t.sn("courses_desc" + tail, len(vms), provider=src["name"]),
                            crumbs, [C["x"]["url"] for C in vms])
        used: set = set()
        self.render("en/courses.html.j2", f"{home}courses/", page, "courses",
                    latest_of([C["c"].get("_page_date") for C in vms]),
                    lede=t.s("courses_lede" + tail, name=src["name"]),
                    # one fragment id per group in every version: the Korean page's (slugs.COURSE_GROUP_IDS for a
                    # duration), else the romanized Korean group
                    groups=[{"title": tt, "id": present.unique_id("g-" + (
                        COURSE_GROUP_IDS.get(squash_ws(cs[0]["c"].get("duration")))
                        or en_slug(romanize(cs[0]["c"].get("duration") or cs[0]["c"].get("group") or "") or tt)), used),
                             "courses": cs} for tt, cs in grouped])

    def events(self) -> None:
        site, S, t = self.site, self.S, self.t
        if not site.series or not S.events:
            return
        EV = site.events_vm()
        path = f"{site.home}events/"
        crumbs = self.crumbs((t.s("events"), self.abs(path)))
        url = self.abs(path)
        title = t.s("events_title", r=site.region)
        nodes = []
        for r in EV["upcoming"] + EV["past"]:
            if not r["start"]:
                continue
            node = {"@type": "Event", "@id": f"{url}#{r['anchor']}", "name": r["name"], "url": f"{url}#{r['anchor']}",
                    "startDate": r["start"]}
            if r["end"]:
                node["endDate"] = r["end"]
            by = {row["field"]: row for row in r["rows"]}
            venue = by.get("place_name")
            if venue and venue["value"] and not venue["blocks"]:
                loc_ = {"@type": "Place", "name": venue["value"]}
                ad = by.get("address")
                if ad and ad["value"] and not ad["blocks"]:
                    loc_["address"] = {"@type": "PostalAddress", "streetAddress": ad["value"], "addressCountry": "KR"}
                node["location"] = loc_
            sp = by.get("sponsor")
            if sp and sp["value"] and not sp["blocks"]:
                node["organizer"] = {"@type": "Organization", "name": sp["value"]}
            nodes.append(node)
        graph = [_webpage(site, url, title, None, EV["checked"]), jsonld.breadcrumb(crumbs), *nodes]
        page = {"title": title,
                "description": t.s("events_desc", a=len(EV["upcoming"]), b=len(EV["past"]), r=site.region),
                "canonical": url, "crumbs": crumbs,
                "jsonld": [jsonld.dumps({"@context": "https://schema.org", "@graph": graph})]}
        self.render("en/events.html.j2", path, page, "events", EV["checked"], EV=EV)

    def about(self) -> None:
        site, t = self.site, self.t
        path = f"{site.home}about/"
        crumbs = self.crumbs((t.s("about"), self.abs(path)))
        page = self._simple(path, t.s("about_title"), t.s("about_desc", site=site.site_name), crumbs)
        lics = Counter(ph["type"] for p in site.places.values() for ph in p["e"].get("_photos") or [])
        # English: a name made by the government guideline (romanized proper part + English generic) as the example
        example = next((p["name"] for p in sorted(site.places.values(), key=lambda p: p["e"]["id"])
                        if "generic" in squash_ws(p["rec"].get("name_en_source")) and p["name"] != romanize(p["e"]["name"])),
                       "") if site.loc.code == "en" else ""
        self.render("en/about.html.j2", path, page, "about",
                    latest_of([p["e"].get("_page_date") for p in site.places.values()]),
                    n_places=len(site.places), n_index=sum(1 for p in site.places.values() if not p["noindex"]),
                    n_guides=len(site.guides), n_courses=len(site.courses), n_series=len(site.series), lics=lics,
                    name_example=example, offer=site.offer())

    def search(self) -> None:
        """<home>search/ (owner 2026-10-14: '이 언어들도 다 검색이 되는 거지?'): the Korean site search in this version —
        a static index (<home>search/index.json) that assets/search.js reads on the first focus (or at once with ?q=):
        every place of this version (its name here, its Korean name too, its type, area and 권역 group in this
        language, the signature dishes of a restaurant), the courses (their stops), the guides and the event
        series, each with its path here. o: the names in the other versions — the Korean ones (QA 2026-10-15 U10:
        a Korean name on /en/search/ finds what its romanized name finds) and, in a version other than English, the
        English one (the romanised name on signs and maps); v: a course's stops in those versions
        (present.other_names). Without JS the page lists every place by kind, alphabetically. A utility page:
        noindex, not in the sitemap."""
        site, t, loc = self.site, self.t, self.loc
        if not site.places:
            return
        home = site.home
        en = getattr(self.S, "en", None) if loc.code != "en" else None
        en_series = {x["slug"]: x for x in (en.series if en else [])}
        rows, kinds = [], []
        for kind in KINDS:
            if not site.by_kind[kind]:
                continue
            L = site.list_vm(kind)
            recs = []
            for g in L["groups"]:
                for it in g["recs"]:
                    row = {"n": it["name"], "a": it["e"]["name"], "k": kind, "t": it["type"] or "", "d": it["area"] or "",
                           "r": g["name"], "p": it["path"]}
                    present.other_names(row, *jsonld.alternate_names(it["e"]),
                                        en and (it["e"].get("_en") or {}).get("name"))
                    menu = next((c.get("main") for c in it["cells"] if c.get("key") == "menu" and not c.get("missing")), "")
                    if menu:
                        row["m"] = re.sub(r"<[^>]+>", "", str(menu))
                    alias = site.own(it["e"].get("_alias_of"))   # pipeline/relations.py same_building, as /search/
                    if alias:
                        row["s"] = LC.NEAR_WORDS[loc.code]["same_building"].format(name=alias["name"])
                    rows.append(row)
                    recs.append(it)
            kinds.append({"kind": kind, "label": t.s(f"cat_{kind}"), "id": f"k-{kind}",
                          "recs": sorted(recs, key=lambda it: it["name"].casefold())})
        for x in site.courses.values():
            C = site.course_vm(x)
            row = {"n": C["name"], "a": " · ".join(s["name"] for s in C["stops"] if s.get("name")), "k": "course",
                   "t": t.s("courses"), "d": "", "r": "", "p": x["path"]}
            cv = self.S.course_vms.get(x["c"]["slug"]) or {}
            xe = en.courses.get(x["c"]["id"]) if en else None
            present.other_names(row, cv.get("display"), xe and xe["rec"].get("name"))
            present.other_names(row, *(s.get("name") for s in cv.get("stops") or []),
                                *(s.get("name") for s in (en.cv(xe)["stops"] if xe else [])), key="v")
            rows.append(row)
        for x in site.guides.values():
            row = {"n": squash_ws(x["rec"].get("title")), "a": squash_ws(x["rec"].get("label")), "k": "guide",
                   "t": t.s("guides"), "d": "", "r": "", "p": x["path"]}
            xe = en.guides.get(x["g"]["id"]) if en else None
            present.other_names(row, x["g"].get("title"), x["g"].get("label"), xe and xe["rec"].get("title"))
            rows.append(row)
        if site.series and self.S.events:
            EV = site.events_vm()
            for r in EV["upcoming"] + EV["past"]:
                row = {"n": r["name"], "a": r["series_name"], "k": "event", "t": t.s("events"), "d": "", "r": "",
                       "p": f"{home}events/#{r['anchor']}"}
                sr, xe = r["x"]["sr"], en_series.get(r["x"]["slug"])
                present.other_names(row, sr.get("name"), (sr.get("newest") or {}).get("name"),
                                    xe and xe["rec"].get("series_name"))
                rows.append(row)
        path = f"{home}search/"
        (self.out / path.strip("/")).mkdir(parents=True, exist_ok=True)
        (self.out / path.strip("/") / "index.json").write_text(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")), "utf-8")
        w = t.search_words()
        crumbs = self.crumbs((w["open"], self.abs(path)))
        page = {**self._simple(path, w["title"].format(r=site.region), w["desc"].format(r=site.region), crumbs),
                "robots": "noindex, follow"}
        words = {"kinds": {"attraction": t.s("cat_attraction"), "food": t.s("cat_food"), "stay": t.s("cat_stay"),
                           "course": t.s("courses"), "guide": t.s("guides"), "event": t.s("events")},
                 **{k: w[k] for k in ("none", "menu", "other", "via", "des", "of", "sug", "diet")}}
        self.render("en/search.html.j2", path, page, "search", None, in_sitemap=False, kinds=kinds, n_index=len(rows),
                    words=json.dumps(words, ensure_ascii=False), sw=w)

    def home_news(self, EV: dict) -> list[dict]:
        """The opening's news cards in this version (owner 2026-10-14: the other versions take the Korean home's
        design): the Korean home's cards (present.home_news — the same order, the same photos) that have a page here.
        An event: this version's name, dates and venue, linked to its row on this version's events list; a guide: this
        version's title (the part before ': '), linked to its page here. Outside items (articles, videos) have no
        page in this version and stay out; when fewer than present.NEWS_MIN remain, the list hubs' guides follow. A
        photo shows only with its place's page here (its name and link in this language); without one, the card's art
        in this language (art.for_lang: alt and langs) or the 3D icon. The first slide is the LCP: a KOGL-1 photo with
        a local AVIF derivative or the art, as on the Korean home. Card: {kind, chip_key, title, href, start, end,
        end_month (an end the source gives only as a month: shown as the month, never as its last day), sub, photo,
        art, track}."""
        site, S, loc = self.site, self.S, self.loc
        home = site.home
        ent_by_path = {e["_path"]: e for e in S.entities}
        ev_by_ko = {r["ko_path"]: r for r in EV["upcoming"]}
        slots = art.for_lang(S.art, loc.code)

        def guide_card(gid: str) -> dict | None:
            x = site.guides.get(gid)
            if not x:
                return None
            title = squash_ws(x["rec"].get("title"))
            parts = re.split(r"\s*(?:: |：| — )\s*", title, maxsplit=1)
            slugs = [*(x["g"].get("route_slugs") or []),
                     *(it.get("place_slug") for it in x["g"].get("items") or [] if isinstance(it, dict))]
            return {"kind": "guide", "chip_key": "guide", "title": parts[0], "sub": parts[1] if len(parts) > 1 else "",
                    "href": x["path"], "track": "guide_click", "key": "g:" + gid,
                    "places": [S.ent_by_slug[s] for s in slugs if s and s in S.ent_by_slug]}

        cards: list[dict] = []
        for c in present.home_news(S):
            if c["kind"] in ("festival", "event"):
                r = ev_by_ko.get(c["href"])
                if not r:
                    continue
                venue = next((row["value"] for row in r["rows"] if row["field"] == "place_name" and row["value"]
                              and not row["blocks"]), "")
                ko_ph = c.get("photo")
                cards.append({"kind": c["kind"], "chip_key": c["kind"], "title": r["name"], "sub": venue,
                              "href": f"{home}events/#{r['anchor']}", "start": r["start"], "end": r["end"],
                              "end_month": r["end_month"], "track": "", "key": c["key"], "ev_kind": c.get("ev_kind") or "",
                              "places": [ent_by_path[ko_ph["path"]]] if ko_ph and ko_ph.get("path") in ent_by_path else []})
            elif c["kind"] == "guide":
                g = guide_card(c["key"][2:])
                if g:
                    cards.append(g)
        for gid in (*site.hub_ids.values(), *site.guides):
            if len(cards) >= present.NEWS_MIN:
                break
            if not any(x["key"] == "g:" + gid for x in cards):
                g = guide_card(gid)
                if g:
                    cards.append(g)
        used: set[str] = set()
        for i, c in enumerate(cards[:present.NEWS_MAX]):
            own = [e for e in c.pop("places") if site.own(e)]
            ph = present.news_photo(own, used)
            if ph and i == 0 and not (ph["type"] == 1 and ph.get("avif")):
                ph = None    # the first slide is the LCP: never a heavy original there
            if ph:
                used.add(ph["url"])
                tp = site.own(ent_by_path.get(ph["path"]))
                ph = {**ph, "place": tp["name"], "path": tp["path"], "alt": tp["name"], "credit": self.t.s("kto"),
                      "lic": site.lic(f"KOGL-{ph['type']}")} if tp else None
            c["photo"] = ph
            c["art"] = None if ph else ((slots.get("events.kind." + c["ev_kind"]) if c.get("ev_kind") else None)
                                        or slots.get("home.card." + ("event" if c["kind"] == "festival" else c["kind"])))
        return cards[:present.NEWS_MAX]

    def home_services(self, counts: dict, lists: dict, n_events: int) -> list[dict]:
        """The 3D icon menu of the white card (as present.home_services on the Korean home), with the pages this version
        has. The core four first (operator 2026-10-15; core=True: one row of four larger tiles on phones): its
        attractions, restaurants and stays lists and the 'getting there' guide (the Korean menu's — its bus row —
        when it has a page here); then the courses, the events list and the guides."""
        site, t = self.site, self.t
        home = site.home
        go = next((r for r in present.home_services(self.S, n_events) if r.get("icon") == "bus"), None)
        x = next((x for x in site.guides.values() if go and x["g"].get("_path") == go.get("href")), None)
        # (label, href, picture, glyph, count, track, core, short): short is the HC key (templates/en/home.html.j2) of
        # a phone's shorter label — a guide's own label does not fit a quarter of a phone's width
        rows = [*((t.s(f"cat_{k}"), lists[k]["path"], pic, glyph, counts[k], "", True, "")
                  for k, pic, glyph in (("attraction", "icon-sights", "pin"), ("food", "icon-food", "bowl"),
                                        ("stay", "icon-stay", "bed")) if counts[k]),
                (squash_ws(x["rec"].get("label")) or squash_ws(x["rec"].get("title")), x["path"],
                 "icon-getting-here", "bus", 0, "guide_click", True, "go") if x else None,
                (t.s("courses"), f"{home}courses/", "icon-course", "route", len(site.courses), "course_click", False, "")
                if site.courses else None,
                (t.s("events"), f"{home}events/", "icon-events", "calendar", n_events, "", False, "")
                if site.series and self.S.events else None,
                (t.s("guides"), f"{home}guides/", "guide", "book", len(site.guides), "guide_click", False, "")
                if site.guides else None]
        return [{"label": lab, "href": href, "pic": pic, "icon": glyph, "n": n, "track": track, "core": core,
                 "short": short}
                for lab, href, pic, glyph, n, track, core, short in filter(None, rows)]

    def home(self) -> None:
        site, S, t, loc = self.site, self.S, self.t, self.loc
        counts = {k: len(site.by_kind[k]) for k in KINDS}
        home = site.home
        lists = site.lists()
        tiles = []
        for kind, g in site.hub_ids.items():   # the accent bento (present.ACCENT_TONES): the list hubs' guides
            if g not in site.guides:
                continue
            x = site.guides[g]
            n = len([it for it in x["rec"].get("items") or [] if it.get("place_slug")])
            tone, icon = present.ACCENT_TONES.get(kind) or present.ACCENT_TONES.get(g) or ("", "")
            title = squash_ws(x["rec"].get("title"))
            if loc.code == "en":
                head, _, tail = title.partition(": ")
            else:   # 'title：list' (CJK) or 'title : list' (French spacing)
                parts = re.split(r"\s*[:：]\s*", title, maxsplit=1)
                head, tail = parts[0], (parts[1] if len(parts) > 1 else "")
            # a hub with a lead (the Korean guide's hub_lead) shows its first items as pills, from the guide title's
            # own list; the others a short phone line (strings LIST_HUB_TINY.<kind>, else the title's head)
            pills = (title_list(tail, loc)[:4] if squash_ws(x["g"].get("hub_lead")) else [])
            tiles.append({"href": x["path"], "fig": str(n), "unit": t.sn("places_unit", n), "key": squash_ws(x["rec"].get("label")),
                          "short": head, "tiny": " · ".join(pills[:3]) if pills else site.T(f"LIST_HUB_TINY.{kind}", head),
                          "track": "guide_click", "tone": tone, "icon": icon, "pills": pills})
        if site.courses:   # the one dark card, right after the hub guides: what the courses are, 'official' only when so
            day, night = course_kinds(list(site.courses.values()))
            both = day and night
            tiles.append({"href": f"{home}courses/", "fig": str(len(site.courses)), "unit": "", "key": t.s("courses"),
                          "short": t.s("tile_courses_short" if both else "tile_courses_any"),
                          "tiny": t.s("tile_courses_tiny" if both else "tile_courses_tiny_day" if day else "tile_courses_tiny_any"),
                          "track": "course_click", **present.ACCENT_DARK,
                          "pill": t.s("tile_courses_pill") if site.course_src["official"] else ""})
        # (desktop line, phone line): the phone line stays one short line in a 160px tile; the title is the list's
        # noun ('161 Attractions'), short enough for one line there too
        for kind in KINDS:
            if counts[kind]:
                tiles.append({"href": lists[kind]["path"], "fig": str(counts[kind]), "unit": "", "key": t.s(f"tile_{kind}"),
                              "short": t.s(f"tile_short_{kind}"), "tiny": t.s(f"tile_tiny_{kind}"), "track": ""})
        EV = site.events_vm() if site.series and S.events else {"upcoming": [], "past": []}
        if site.series and S.events:
            tiles.append({"href": f"{home}events/", "fig": str(len(EV["upcoming"])), "unit": "", "key": t.s("events"),
                          "short": t.s("tile_events_short"), "tiny": t.s("tile_events_tiny"), "track": ""})
        h = present.home_vm(S)
        slots = h.get("slots") or media.slot_photos(S)   # site.json home.media (media.slot_photos), licence-checked
        hero = None
        kto = t.s("kto")
        for ph in slots.get("hero") or []:
            tg = S.ent_by_slug.get(ph.get("slug"))
            tp = site.own(tg)
            if tg and tp and ph.get("type") == 1:
                hero = {**ph, "alt": tp["name"], "name": tp["name"], "place": tp["name"],
                        "path": tp["path"], "credit": kto, "lic": site.lic("KOGL-1")}
                break
        cover = None   # the full-bleed opening photo (home.media.cover, KOGL-1), with the place's name in this language
        ph = slots.get("cover")
        tg = S.ent_by_slug.get(ph.get("slug")) if ph else None
        tp = site.own(tg)
        if ph and tg and tp and ph.get("type") == 1:
            cover = {**ph, "alt": tp["name"], "name": tp["name"], "place": tp["name"],
                     "path": tp["path"], "credit": kto, "lic": site.lic("KOGL-1")}
        # the opening's bottom bar: the same event the Korean home shows (present.pick_next_event), else the first
        ko_next = present.pick_next_event(present.ranked_events(S)) if EV["upcoming"] else None
        hero_ev = next((r for r in EV["upcoming"] if ko_next and r["ko_path"] == ko_next.get("path")),
                       EV["upcoming"][0] if EV["upcoming"] else None)
        featured = [site.card(site.own(c["e"]), c.get("photo")) for c in h.get("featured") or [] if site.own(c["e"])][:8]
        day = [x for x in site.courses.values() if x["c"].get("duration") == "당일"]
        lines = [site.course_vm(x) for x in (day or list(site.courses.values()))[:4]]
        page = {"title": t.s("home_title", site=site.site_name, r=site.region),
                "description": t.s("home_desc" + site.offer(), a=counts["attraction"], f=counts["food"], s=counts["stay"],
                                   r=site.region),
                "canonical": self.abs(home), "crumbs": [], "image": (cover or hero or {}).get("url", "")}
        dest = {"@type": ["City", "TouristDestination"], "@id": f"{S.site_url}/{jsonld.CITY_NODE_ID}", "name": site.region}
        if featured:
            dest["includesAttraction"] = [place_ref(c["p"], city=site.city) for c in featured]
        website = {"@type": "WebSite", "@id": f"{S.site_url}{home}#website", "url": self.abs(home), "name": site.site_name,
                   "inLanguage": loc.html, "publisher": jsonld.org_ref(S.site_url)}
        page["jsonld"] = [jsonld.dumps({"@context": "https://schema.org",
                                        "@graph": [website, jsonld.organization(S.site, S.site_url, lang=loc.code), dest]})]
        # the opening photo fills the first screen: the template preloads it (md.preload) with high priority
        lastmod = latest_of([c["e"].get("_page_date") for c in featured]
                            + [x["g"].get("_page_date") for x in site.guides.values()])
        # the centre question card (templates/_ask.html.j2) under the photo: a starter shows only where its page in this
        # version is built — one of its guides, or its events list (State.ask None: no card). ask.json keys the
        # questions by the html language tag (ko, en, ja, zh-Hans …), like the card's own strings.
        items = getattr(S, "ask", None)
        ask_starters = None if items is None else ask.starters(
            items, loc.html, {gid: x["path"] for gid, x in site.guides.items()},
            {"events": f"{home}events/"} if site.series and S.events else {})
        self.render("en/home.html.j2", home, page, "home", lastmod, counts=counts, tiles=tiles, hero=hero, cover=cover,
                    hero_ev=hero_ev, today=S.today, featured=featured, events=EV["upcoming"][:4], lines=lines,
                    hubs=[site.guides[g] for g in site.hub_ids.values() if g in site.guides], lists=lists,
                    n_courses=len(site.courses), n_guides=len(site.guides), ask_starters=ask_starters,
                    news=self.home_news(EV), services=self.home_services(counts, lists, len(EV["upcoming"])))


def render(site: Site, env, out: Path, intl: Intl | None = None) -> dict:
    """Every page of one version; returns the build line's stats (pages, indexable, stale records skipped)."""
    pg = Pages(site, env, out, intl)
    for p in site.places.values():
        pg.place(p)
    pg.lists()
    pg.guides()
    pg.courses()
    pg.events()
    pg.about()
    pg.search()
    pg.home()
    out_ = {"pages": pg.count, "indexable": pg.indexable, "places": len(site.places),
            "places_indexable": sum(1 for p in site.places.values() if not p["noindex"]),
            "guides": len(site.guides), "courses": len(site.courses), "event_series": len(site.series),
            "stale_skipped": {k: len(v) for k, v in site.stale.items()},
            "untranslated": {k: len(v) for k, v in site.untranslated.items()}}
    if site.loc.code != "en":
        out_["missing_strings"] = sorted(site.misses)
    return out_


def llms_lines(site: Site) -> list[str]:
    """The llms.txt section of a version. English: home, the list hubs' guides, lists, courses, events, about, top
    place pages (indexable only; places on the most courses first). The other versions: home, the hub guides and the
    lists."""
    S, t = site.S, site.t
    home_line = t.s("llms_home" + site.offer(), r=site.region)
    if site.loc.code != "en":
        out = [f"## {site.loc.label}", f"- [{site.site_name}]({S.abs(site.home)}): {home_line}"]
        for gid in site.hub_ids.values():
            x = site.guides.get(gid)
            if x:
                first = (sentences(x["rec"].get("summary"), site.loc) or [""])[0]
                out.append(f"- [{squash_ws(x['rec'].get('title'))}]({x['url']}): {first}".rstrip(": "))
        for kind, cfg in site.lists().items():
            if site.by_kind[kind]:
                out.append(f"- [{cfg['h1']}]({S.abs(cfg['path'])}): {t.sn('count_' + kind, len(site.by_kind[kind]))}")
        return out + [""]
    out = ["## English", f"- [{site.site_name}]({S.abs(EN_HOME)}): {home_line}"]
    for gid in site.hub_ids.values():
        x = site.guides.get(gid)
        if x:
            first = (sentences_en(x["rec"].get("summary")) or [""])[0]
            out.append(f"- [{squash_ws(x['rec'].get('title'))}]({x['url']}): {first}".rstrip(": "))
    for kind, cfg in site.lists().items():
        if site.by_kind[kind]:
            out.append(f"- [{cfg['h1']}]({S.abs(cfg['path'])}): {t.sn('count_' + kind, len(site.by_kind[kind]))}")
    if site.courses:
        n = len(site.courses)
        out.append(f"- [{site.region} travel courses]({S.abs('/en/courses/')}): {n} "
                   f"{'official ' if site.course_src['official'] else ''}course{'s' if n != 1 else ''}")
    if site.series and S.events:
        out.append(f"- [{site.region} festivals and events]({S.abs('/en/events/')}): dates, venues and fees")
    out.append(f"- [About and sources]({S.abs('/en/about/')}): sources, photo licenses, corrections")
    top = [p for p in site.places.values() if not p["noindex"]]
    top.sort(key=lambda p: (-len(p["e"].get("_courses") or []), p["e"].get("tier") != "full",
                            not p["e"].get("_photos"), p["name"]))
    for p in top[:60]:
        first = (sentences_en(p["rec"].get("summary")) or [""])[0]
        out.append(f"- [{p['name']}]({p['url']}): {first}".rstrip(": "))
    return out + [""]
