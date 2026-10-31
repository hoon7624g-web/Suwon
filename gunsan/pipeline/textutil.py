"""Text helpers shared by the pipeline."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata

_TAG_BR = re.compile(r"<\s*br\s*/?\s*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t 　]+")
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_URL = re.compile(r"https?://[^\s<>\"']+")
# A whole domestic number (063-…, 0507-…, 010-…) or a nationwide one (1577-…), never one glued to other digits.
_PHONE = re.compile(r"(?<![\d-])(0\d{1,3}-\d{3,4}-\d{4}|1\d{3}-\d{4})(?![\d-])")
_SENT_END = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s*")


def strip_html(value: str | None) -> str:
    """Convert TourAPI-style HTML fragments to plain text, keeping line breaks."""
    if not value:
        return ""
    text = _TAG_BR.sub("\n", str(value))
    text = _TAG.sub("", text)
    text = html.unescape(text)
    lines = [_WS.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_url(value: str | None) -> str:
    """TourAPI 'homepage' fields are often '<a href=...>...</a>'. Return the first URL."""
    if not value:
        return ""
    m = _HREF.search(value)
    if m:
        return html.unescape(m.group(1)).strip()
    m = _URL.search(html.unescape(value))
    return m.group(0).strip() if m else ""


def extract_phone(value: str | None) -> str:
    """The first cleanly delimited phone number in `value`, else "" (a truncated number is worse than none)."""
    m = _PHONE.search(value or "")
    return m.group(1) if m else ""


def extract_phones(value: str | None) -> list[str]:
    """Every cleanly delimited phone number in `value`, in order, without repeats."""
    out: list[str] = []
    for m in _PHONE.finditer(value or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def phone_intl(phone: str) -> str:
    """The number as structured data writes it: domestic '063-454-7870' -> '+82-63-454-7870' (phone_e164); a number
    that has no international form — nationwide '1577-4050', free 080, premium 060 — stays as written."""
    return phone_e164(phone) or phone


def phone_domestic(phone: str) -> str:
    """Inverse of phone_intl, so a marked-up '+82-…' number can be matched against the visible text."""
    if not phone.startswith("+82-"):
        return phone
    rest = phone[4:]
    return rest if re.match(r"1\d{3}-\d{4}$", rest) else "0" + rest


def phone_e164(phone: str) -> str:
    """'063-454-7870' -> '+82-63-454-7870' (also 010 mobiles, 070 and 0507): the form a caller abroad dials. '' for a
    number that cannot be dialled from abroad: nationwide 15xx/16xx/18xx (and 1330, 114, 119 …), free 080, premium
    060 (QA 2026-10-15: never +82 on a domestic-only number)."""
    if not phone.startswith("0") or phone.startswith(("080", "060")):
        return ""
    return "+82-" + phone[1:]


# Area codes (02, 031–033, 041–044, 051–055, 061–064), mobiles (010, 011, 016–019) and 070: numbers that are known to
# answer a call from abroad. 0507 (a personal relay number) gets a +82 link but no visible +82 form: its reach from
# abroad is not verified.
_INTL_SHOWN = re.compile(r"0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|1[016789]|70)-")


def phone_intl_shown(phone: str) -> str:
    """The visible international form under a number on a foreign-language place page: '02-530-6311' ->
    '+82 2-530-6311'; '' for 0507, 15xx/16xx, 080 and 060 numbers."""
    return "+82 " + phone[1:] if _INTL_SHOWN.match(phone) else ""


# The province has been 전북특별자치도 since 2024-01-18; sources still write the old or short form.
_PROVINCE_PREFIX = re.compile(r"^(?:전라북도|전북\s*특별자치도|전북)\s+")
PROVINCE = "전북특별자치도"


def display_address(raw: str | None) -> str:
    """Address as shown: only the province prefix is rewritten ('전라북도 군산시 …' -> '전북특별자치도 군산시 …').
    Nothing else is derived (no 지번, no postcode). The stored value stays the source string."""
    text = squash_ws(raw)
    return _PROVINCE_PREFIX.sub(PROVINCE + " ", text, count=1) if text else ""


def normalize_name(name: str | None) -> str:
    """Normalise a place name for matching: NFC, drop bracketed parts, spaces, punctuation."""
    s = unicodedata.normalize("NFC", name or "")
    s = re.sub(r"\(.*?\)|\[.*?\]|（.*?）", "", s)
    s = re.sub(r"[\s\-_·.,'\"!?~/]", "", s)
    return s.lower()


def slugify(name: str | None) -> str:
    """Readable slug that keeps Hangul: '경암동 철길마을' -> '경암동-철길마을'."""
    s = unicodedata.normalize("NFC", name or "").strip()
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^\w\s-]", "", s)  # \w keeps Hangul in Python 3
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s.lower() or "item"


def sha256_text(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def squash_ws(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def first_sentence(text: str | None, limit: int = 120) -> str:
    """First sentence (Korean-aware), trimmed to `limit` characters."""
    t = squash_ws(text)
    if not t:
        return ""
    parts = _SENT_END.split(t, maxsplit=1)
    s = parts[0].strip() if parts else t
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


_AREA_PAREN = re.compile(r"\(([가-힣0-9]+(?:동|면|읍))(?:[,\s][^()]*)?\)")
_AREA_TOKEN = re.compile(r"(?:^|[\s(])([가-힣]+[0-9]*(?:읍|면|동))(?=[\s,)\d]|$)")


def area_from_address(address: str | None) -> str:
    """읍·면·동 named in an address, e.g. '군산시 경촌4길 14(경암동)' -> '경암동'. Empty when not stated."""
    text = address or ""
    m = _AREA_PAREN.search(text)
    if m:
        return m.group(1)
    for m in _AREA_TOKEN.finditer(text):
        if m.group(1) not in ("전북특별자치도", "전라북도"):
            return m.group(1)
    return ""


_ROAD = re.compile(r"(?:^|\s)([가-힣]+[0-9]*(?:로|길)(?:\s?[0-9]+번?길)?)\s+[0-9]")


def road_from_address(address: str | None) -> str:
    """Road name of a road-name address, e.g. '군산시 내항2길 32' -> '내항2길'. Empty when not found."""
    m = _ROAD.search(address or "")
    return m.group(1).replace(" ", "") if m else ""


_ROAD_NO = re.compile(r"([가-힣0-9]+(?:로|길))\s*([0-9]+(?:-[0-9]+)?)")


def address_norm(address: str | None) -> str:
    """An address without brackets, spaces and the leading province and city ('전북특별자치도 군산시 옥도면
    선유도리 (일원)' -> '옥도면선유도리'), for comparing two spellings of one address."""
    a = re.sub(r"\([^)]*\)", "", address or "").strip()
    a = re.sub(r"^(?:전북특별자치도|전라북도)\s*", "", a)
    a = re.sub(r"^[가-힣]{1,4}시\s+", "", a)   # the city as its own word ('군산시 '), never '신시도'
    return re.sub(r"\s+", "", a)


def address_key(address: str | None) -> str:
    """One building's key: road + number ('군산시 경촌4길 14(경암동)' -> '경촌4길14', as tools/tourapi_bulk.road_key),
    else the normalized address (address_norm)."""
    m = _ROAD_NO.search(re.sub(r"\s+", " ", address or ""))
    return f"{m.group(1)}{m.group(2)}" if m else address_norm(address)


def josa(word: str, pair: str) -> str:
    """Attach the right Korean particle: josa('코스', '으로/로') -> '코스로', josa('공원', '은/는') -> '공원은'."""
    with_final, without_final = pair.split("/")
    last = (word or "").rstrip()[-1:] or " "
    code = ord(last) - 0xAC00
    if not 0 <= code < 11172:
        return f"{word}{without_final}"
    final = code % 28
    if with_final == "으로":
        return f"{word}{'로' if final in (0, 8) else '으로'}"
    return f"{word}{with_final if final else without_final}"


# ---------------------------------------------------------------- display normalisation (round 3 redesign)
# One normaliser for every value a page shows. Templates print display_value(), jsonld.py emits it, and
# pipeline.validate compares the page against it, so markup, visible text and the check never drift apart.
# It changes presentation only: no word is dropped (the course-name pipe and joining whitespace are not words).
TIME = r"\d{1,2}:\d{2}"
TILDE = "[~～∼〜]"
_TIME_RANGE = re.compile(rf"({TIME})\s*(?:{TILDE}|[–—]|-(?=\s*\d))\s*({TIME})")
_PARKING_YES = {"가능", "주차가능", "주차 가능", "주차장이 구비", "주차장을 구비", "별도의 주차장"}
_PARKING_NO = {"불가능", "불가"}
_FREE_PARKING = (re.compile(r"^가능\s*,?\s*요금\s*\(\s*무료\s*\)$"), re.compile(r"^가능\s*\(\s*무료\s*\)$"))
_URL_KEYS = ("homepage", "reservationurl")
# Hosts many places share: the first path segment is shown too (instagram.com/xxx), else the text is ambiguous.
SHARED_HOSTS = ("instagram.com", "blog.naver.com", "m.blog.naver.com", "facebook.com", "youtube.com",
                "smartstore.naver.com", "booking.naver.com", "m.booking.naver.com")


def web_url(value: str | None) -> str:
    """Link target for a stored homepage value; 'www.example.kr' gets https://, non-URLs give ''."""
    v = squash_ws(value)
    if v.startswith(("http://", "https://")):
        return v
    return f"https://{v}" if re.fullmatch(r"[\w.-]+\.[a-z]{2,}(/\S*)?", v, re.I) else ""


def url_domain(url: str | None) -> str:
    """'https://www.gunsandal.kr/x' -> 'gunsandal.kr'."""
    m = re.match(r"^(?:[a-z][a-z0-9+.-]*://)?([^/?#:]+)", squash_ws(url), re.I)
    host = (m.group(1) if m else "").lower()
    return host[4:] if host.startswith("www.") else host


def web_text(url: str | None) -> str:
    """A homepage as shown in text: its domain; for hosts many places share, the first path segment too."""
    host = url_domain(url)
    if host in SHARED_HOSTS:
        path = re.sub(r"^(?:[a-z][a-z0-9+.-]*://)?[^/?#]+", "", squash_ws(url), flags=re.I)
        seg = [s for s in re.split(r"[/?#]", path) if s][:1]
        return f"{host}/{seg[0]}" if seg else host
    return host


def url_key(url: str | None) -> str:
    """Comparison key for a URL: no scheme, no trailing '/' or '?', lower case."""
    return re.sub(r"^https?://", "", (url or "").strip().lower()).rstrip("/?")


# ---------------------------------------------------------------- dead homepage links (QA 2026-10-15 SRC-02)
# data/<region>/dead_links.json lists, with a reason and the date it was checked, homepage/booking addresses that no
# longer lead to the place: whole hosts ('modoo.at': the service ended, every address shows the same notice) and
# single URLs (a domain that is gone or now belongs to someone else). build.State drops them before anything is
# rendered (pages in every language, cards, JSON-LD sameAs, llms-full, chat docs) and validate fails a page that
# still links or prints one. tools/link_check.py proposes entries; a person reviews them in git diff.
DEAD_LINK_KEYS = ("homepage", "reservationurl")


def _dead_key(url: str | None) -> str:
    return re.sub(r"^www\.", "", url_key(url))


def dead_reason(url: str | None, dead: dict | None) -> str:
    """The reason `url` is listed as dead in a dead_links.json mapping, '' when it is not listed (or not a URL)."""
    link = link_url(url)
    if not link or not dead:
        return ""
    host = url_domain(link)
    for h, info in (dead.get("hosts") or {}).items():
        h = h.lower().removeprefix("www.")
        if host == h or host.endswith("." + h):
            return squash_ws((info or {}).get("reason")) or "종료된 주소"
    key = _dead_key(link)
    for u, info in (dead.get("urls") or {}).items():
        if key == _dead_key(link_url(u) or u):
            return squash_ws((info or {}).get("reason")) or "종료된 주소"
    return ""


def dead_tokens(dead: dict | None) -> list[str]:
    """How a listed address would appear in visible text: each host, and each URL's web_text (its domain, or
    domain/first-segment for shared hosts such as blog.naver.com/<id>)."""
    out = [h.lower().removeprefix("www.") for h in (dead or {}).get("hosts") or {}]
    out += [web_text(link_url(u) or u) for u in (dead or {}).get("urls") or {}]
    return [t for t in dict.fromkeys(out) if t]


def drop_dead_links(records: list[dict], dead: dict | None) -> list[dict]:
    """Remove listed dead addresses from places and events in place: facts.homepage/reservationurl (with their
    fact_sources entry), the same keys' fact_alternatives, official.homepage and an event's homepage. When a main
    value goes and another source's live value remains, that one becomes the main value with its own source.
    Returns one row per removed address: {id, key, url, reason}."""
    dropped: list[dict] = []
    if not (dead and ((dead.get("hosts") or {}) or (dead.get("urls") or {}))):
        return dropped

    def gone(rec: dict, key: str, url) -> bool:
        reason = dead_reason(url, dead)
        if reason:
            dropped.append({"id": rec.get("id", ""), "key": key, "url": squash_ws(url), "reason": reason})
        return bool(reason)

    for rec in records:
        facts = rec.get("facts") if isinstance(rec.get("facts"), dict) else {}
        sources = rec.get("fact_sources") if isinstance(rec.get("fact_sources"), dict) else {}
        alts = rec.get("fact_alternatives") if isinstance(rec.get("fact_alternatives"), dict) else {}
        for key in DEAD_LINK_KEYS:
            if alts.get(key):
                alts[key] = [a for a in alts[key] if not gone(rec, f"fact_alternatives.{key}", a.get("value"))]
            if facts.get(key) and gone(rec, f"facts.{key}", facts[key]):
                facts.pop(key)
                sources.pop(key, None)
                if alts.get(key):   # another source's live address takes its place, with that source
                    first = alts[key].pop(0)
                    facts[key] = first["value"]
                    sources = rec.setdefault("fact_sources", sources)
                    sources[key] = {k: first[k] for k in ("provider", "checked_at", "contentid", "url") if first.get(k)}
            if key in alts and not alts[key]:
                alts.pop(key)
        if "fact_alternatives" in rec and not alts:
            rec.pop("fact_alternatives")
        official = rec.get("official") if isinstance(rec.get("official"), dict) else {}
        if official.get("homepage") and gone(rec, "official.homepage", official["homepage"]):
            official.pop("homepage")
        if isinstance(rec.get("homepage"), str) and rec["homepage"] and gone(rec, "homepage", rec["homepage"]):
            rec.pop("homepage")
    return dropped


def _note_only(value) -> bool:
    """A value that is only a note that the shops differ ('※ 점포별 상이함'), not a time, day or fee."""
    v = squash_ws(value.get("value") if isinstance(value, dict) else value)
    return bool(v) and not re.search(r"\d", v) and "상이" in v


def keep_primary_facts(records: list[dict]) -> list[dict]:
    """Operator decisions 2026-10-30 (부평시장각, '출처마다 다름도 보기 좀 안 좋은데 하나로 통일') and 2026-10-31
    (군산각, '출처마다 다름 표시는 좀 안 보이면 좋겠는데'): site.json fact_conflicts 'primary': where another source's value differs from a record's main value (a fact_alternatives entry that is not
    'also'), the main value — the one the data already leads with — stays alone, with its own source; the other values
    leave the record in memory before anything reads it (pages, cards, JSON-LD, the chat documents, the hub's text). A
    main value that is only a note ('※ 점포별 상이함') gives way to the first other value that is not, with that value's
    source; with no main value the first other value leads. An 'also' value (a second dish, another phone line) stays.
    The data file keeps every value. Returns one row per value set aside: {id, key, value, provider}."""
    aside: list[dict] = []
    for rec in records:
        alts = rec.get("fact_alternatives") if isinstance(rec.get("fact_alternatives"), dict) else {}
        for key in list(alts):
            other = [a for a in alts[key] or [] if a.get("relation") != "also"]
            if not other:
                continue
            facts, sources = rec.setdefault("facts", {}), rec.setdefault("fact_sources", {})
            main = facts.get(key)
            mv = squash_ws(main.get("value") if isinstance(main, dict) else main)
            lead = None
            if not mv or _note_only(mv):
                lead = next((a for a in other if not _note_only(a.get("value"))), None) or (None if mv else other[0])
            if lead is not None:
                if mv:
                    aside.append({"id": rec.get("id", ""), "key": key, "value": mv,
                                  "provider": (sources.get(key) or {}).get("provider", "")})
                facts[key] = lead.get("value")
                sources[key] = {k: lead[k] for k in ("provider", "checked_at", "contentid", "url") if lead.get(k)}
            aside += [{"id": rec.get("id", ""), "key": key, "value": squash_ws(a.get("value")),
                       "provider": a.get("provider", "")} for a in other if a is not lead]
            alts[key] = [a for a in alts[key] if a.get("relation") == "also"]
            if not alts[key]:
                alts.pop(key)
        if "fact_alternatives" in rec and not alts:
            rec.pop("fact_alternatives")
    return aside


def dash_times(text: str | None) -> str:
    """'10:00~21:00', '10:00 - 21:00' -> '10:00–21:00' (the times themselves are kept as written)."""
    return _TIME_RANGE.sub(lambda m: f"{m.group(1)}–{m.group(2)}", text or "")


def restore_lines(raw: str | None) -> list[str]:
    """Line breaks that TourAPI text lost: before '[group]' and after it, before a glued '- item', before
    '※ note'. Presentation only — no character is dropped except the joining whitespace."""
    s = str(raw or "").replace("\r", "")
    s = re.sub(r"(?<=\S)\[", "\n[", s)
    s = re.sub(r"\]\s*(?=\S)", "]\n", s)
    s = re.sub(r"(?<=[^\s\-~])-\s(?=\S)", "\n- ", s)
    s = re.sub(r"(?<=\S)\s*※", "\n※", s)
    s = re.sub(r"\s-\s(?=[가-힣])", "\n- ", s)  # ' - 일요일 …' inside one line
    return [squash_ws(x) for x in s.split("\n") if squash_ws(x)]


def parking_text(raw: str | None) -> str:
    """'가능요금 (무료)' -> '가능, 요금 무료'; '주차장이 구비' / '주차가능' -> '가능'; '불가능' -> '불가'.
    Other values verbatim (lines joined with ', ')."""
    text = ", ".join(squash_ws(x) for x in str(raw or "").replace("\r", "").split("\n") if squash_ws(x))
    if any(rx.match(text) for rx in _FREE_PARKING):
        return "가능, 요금 무료"
    if text in _PARKING_YES:
        return "가능"
    if text in _PARKING_NO:
        return "불가"
    return text


def course_display_name(name: str | None) -> str:
    """'A코스 | 근대~고군산' -> 'A코스 근대~고군산' (the source's separator pipe is not shown)."""
    return squash_ws(re.sub(r"\s*\|\s*", " ", str(name or "")))


def display_value(key: str, raw) -> str:
    """The text a reader sees for one stored value, line breaks as '\\n' (templates print it with nl2br;
    JSON-LD and the validator use it squashed). Never shortens a value."""
    text = "" if raw is None else str(raw)
    if not text.strip():
        return ""
    if key == "address":
        return display_address(text)
    if key in _URL_KEYS:
        url = link_url(text)
        return web_text(url) if url else squash_ws(text)
    if key in ("course_name", "course"):
        return course_display_name(text)
    if key == "parking":
        return tidy_punct(dash_times(parking_text(text)))
    return "\n".join(tidy_punct(dash_times(x)) for x in restore_lines(text))


def tidy_punct(text: str) -> str:
    """Source spacing around punctuation as a reader expects it: no space before a comma ('생등심 , 갈비탕' ->
    '생등심, 갈비탕'; '떡갈비 ,곰탕' stays: a comma between two words is one word to the validator) or inside brackets ('25(일 )' -> '25(일)'). Words and symbols stay (value_tokens ignore both)."""
    text = re.sub(r"\s+,(?=\s)", ",", text)
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", text))


# ---------------------------------------------------------------- value-shown check (pipeline.validate)
# A word token is a maximal run of letters/digits that may hold joiners between them ('10:00–21:00',
# '3,000원', '063-445-2429', '토·일', 'gunsandal.kr'). Every other character is a token of its own ('~' in
# '~21:00', '%' in '50%', '+', '₩', '.', '·', '→' …), except whitespace and the layout punctuation that a
# restored line break or a table layout replaces: / , : ( ) [ ] ※ and the '-' list marker (LAYOUT). So a
# value matches only when every word and every symbol is there in order; nothing may be added in between,
# dropped, reordered or changed.
LAYOUT = "/,:：()（）[]※-"
_TOKEN = re.compile(r"[^\W_]+(?:[:.,~～∼〜–—\-·・'’%&+][^\W_]+)*|[^\w\s" + re.escape(LAYOUT) + r"]|_")


def value_tokens(text: str | None) -> list[str]:
    return _TOKEN.findall(str(text or ""))


def value_shown(value: str | None, text: str | None) -> bool:
    """True when every token of `value` appears in `text` in the same order with nothing but whitespace or
    layout punctuation between them (a contiguous run of `text`'s tokens). An empty value is trivially shown."""
    want = value_tokens(value)
    if not want:
        return True
    have = value_tokens(text)
    n = len(want)
    return any(have[i:i + n] == want for i in range(len(have) - n + 1))


def link_url(raw: str | None) -> str:
    """The link target the page uses for a stored homepage/booking value ('' when the value is not a URL);
    a dangling '?' is dropped. Templates, present.value_view, display_value and the validator share it."""
    return web_url(squash_ws(raw).rstrip("?"))


# ---------------------------------------------------------------- line breaks around '·' '~' '/' (UI 2026-10-31)
# Operator 2026-10-31 ('이런 것들도 줄바꿈도 그렇고, UI 좀 더 세련되게'): Korean text is set word-break: keep-all, so a line
# breaks at a space or beside a mark — and it broke before '·' ('…테디베어박물관' | '·킹콩놀이터'), after '~' inside a short
# unit ('B코스 근대~' | '금강권') and inside a short part of a ' · ' / ' / ' list ('1월' | '1일'). Three pieces, each only
# wraps text in spans, so the text (textContent) stays exactly as written:
# - keep_dots(html): every h1–h3 and course-row title of a written page (pipeline.build._write), from the
#   부평시장각 engine (bpss pipeline/textutil.py, 2026-10-30): the dot kept with the letter before it.
# - keep_units(text): a plain value or sentence (the home's answer tiles, list cells): a mark never begins a line,
#   a run joined by marks ('근대~금강권', '토·일') and a short part of a spaced list ('매주 월요일 / 1월 1일') stay whole
#   unless wider than the line.
# - cell_html(text): a list cell's value in parts the table styles apart (head or time bold, label and notes quiet).
# A span splits the page's text runs for pipeline.validate (PageScan joins runs with a space): never put one inside a
# string the structured data repeats only there (an FAQ question; a title is also in <title>).
# Classes (css/10-base.css): .dj = white-space: nowrap + display: contents — no box of its own, so it is safe even in
# a flex title (bpss: a nowrap span with a box split a flex course title into flex items and overflowed at 390px);
# .ku = an inline-block unit — a line breaks before it, never inside it, unless it is wider than the line (then it
# breaks inside, at a space or after a mark, never overflowing). keep_units is used only in block text (never as the
# direct content of a flex box), where an inline-block is one run of text.
_HEADING = re.compile(r'(?<!<div class="qa">)(?<!<details class="qa"><summary>)(<h[1-3]\b[^>]*>)(.*?)(</h[1-3]>)', re.S)
_TITLE_LINK = re.compile(r'(<a class="line-name"[^>]*>)(.*?)(</a>)', re.S)   # a course row's title (courses, home)
_DOT = re.compile(r"([^\s<>·;])·")


def keep_dots(html_text: str) -> str:
    """A title never starts a line with '·': in every h1–h3 and course-row title the dot is kept with the letter
    before it (<span class="dj">장·</span>); the line may still break after the dot. Only text between tags changes,
    so the title's text stays as written. An FAQ question (div.qa h3, details.qa summary h3) is left alone:
    pipeline.validate finds each FAQPage question name word for word in the page's text runs, and a span would split
    it (as in the 부평시장각 engine)."""
    def heading(m: re.Match) -> str:
        parts = re.split(r"(<[^>]+>)", m.group(2))
        return m.group(1) + "".join(x if x.startswith("<") else _DOT.sub(r'<span class="dj">\1·</span>', x)
                                    for x in parts) + m.group(3)
    return _TITLE_LINK.sub(heading, _HEADING.sub(heading, html_text)) if "·" in html_text else html_text


MARKS = "·~～/–→"
_MARK = f"[{MARKS}]"
_NOMARK = rf"[^\s{MARKS}]"
_GLUE = re.compile(rf"{_NOMARK}{_MARK}+")                       # a mark with the letter before it: '관·', '석/'
_JOINED = re.compile(rf"{_NOMARK}+(?:{_MARK}+{_NOMARK}+)+")     # a run joined by marks: '근대~금강권', '토·일'
_SPACED = re.compile(rf"(\s+)({_MARK}|\|)(\s+)")                 # a spaced list mark: ' · ', ' / '
_LAST = re.compile(rf"(?:{_NOMARK}{_MARK}*|{_MARK}+)$")          # the end a tail is glued to
UNIT_MAX = 12   # a joined run up to this many characters is one unit; a longer one ('근대역사박물관·진포해양공원·…')
                # only keeps each mark with the letter before it (a wrapped inline-block would leave a ragged gap)
PART_MAX = 10   # a spaced-list part up to this many characters is one unit ('매주 월요일', 'A코스 근대~고군산')


def _esc(text: str) -> str:
    from markupsafe import escape
    return str(escape(text))


def _glued(tok: str) -> str:
    out, last = [], 0
    for m in _GLUE.finditer(tok):
        out += [_esc(tok[last:m.start()]), f'<span class="dj">{_esc(m.group(0))}</span>']
        last = m.end()
    return "".join(out) + _esc(tok[last:])


def _token(tok: str, tail: str = "") -> str:
    """One word: its marks glued to the letter before them, a short joined run one unit; tail (HTML) glued to its
    end."""
    if tail:
        m = _LAST.search(tok)
        a = m.start() if m else len(tok)
        body = _glued(tok[:a]) + f'<span class="dj">{_esc(tok[a:])}{tail}</span>'
    else:
        body = _glued(tok)
    return f'<span class="ku">{body}</span>' if len(tok) <= UNIT_MAX and _JOINED.fullmatch(tok) else body


def _words(text: str, tail: str = "") -> str:
    bits = [b for b in re.split(r"(\s+)", text) if b]
    last = max((i for i, b in enumerate(bits) if not b.isspace()), default=-1)
    out = [_esc(b) if b.isspace() else _token(b, tail if i == last else "") for i, b in enumerate(bits)]
    return "".join(out) + (tail if tail and last < 0 else "")


def keep_units(text: str | None, tail: str = "") -> str:
    """HTML for a plain text that breaks only where it reads well (see above): a mark ('·', '~', '/', '–', '→') never
    begins a line, a joined run of UNIT_MAX characters or fewer stays one unit, and so does a part of a spaced list
    ('A · B', 'A / B') of PART_MAX characters or fewer, its list mark kept at its end. tail: HTML glued to the last
    word (a list cell's '외'). Tags only: the text is the escaped input."""
    pieces = _SPACED.split(str(text or ""))      # [part, ws, mark, ws, part, …]
    out = []
    for k in range(0, len(pieces), 4):
        part, more = pieces[k], k + 3 < len(pieces)
        html_part = _words(part, _esc(pieces[k + 1] + pieces[k + 2]) if more else tail)
        if " " in part.strip() and len(part.strip()) <= PART_MAX:
            html_part = f'<span class="ku">{html_part}</span>'
        out.append(html_part + (_esc(pieces[k + 3]) if more else ""))
    return "".join(out)


_CELL_RANGE = re.compile(r"\d{1,2}:\d{2}\s*[–~-]\s*\d{1,2}:\d{2}")
_CELL_TIME = re.compile(r"\d{1,2}:\d{2}")
NOTE_MIN = 3   # a closing bracket of at least this many characters inside is the value's note


def _trailing_note(text: str) -> int:
    """Where the bracket that ends `text` opens ('가능 (근대역사박물관, …)' → 3), or -1: none, unbalanced, the whole
    value, or too short to stand apart ('생선탕(찜)')."""
    if not text.endswith((")", "）")):
        return -1
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        depth += ch in ")）"
        depth -= ch in "(（"
        if depth == 0:
            inner = text[i + 1:-1].strip()
            return i if i > 0 and text[:i].strip() and len(inner) >= NOTE_MIN else -1
    return -1


def _top_level(text: str) -> list[re.Match]:
    """The spaced list marks of `text` outside brackets."""
    out = []
    for m in _SPACED.finditer(text):
        before = text[:m.start()]
        if before.count("(") + before.count("（") == before.count(")") + before.count("）"):
            out.append(m)
    return out


def cell_html(text: str | None, tail: str = "") -> str:
    """A list cell's value (present.slot_value main or sub) as parts the table styles apart (css/30-info.css .cv):
    a value of several parts ('매주 월요일 / 1월 1일', '하절기 09:00–18:00 · 하절기(입장마감 17:30), …') is one unit per
    part (.ku), its mark kept at its end, so a line breaks between parts. In a part, a closing bracket of its own is
    the note (.cv-n; .kfl when it holds a time — the last entry '(입장마감 17:30)' — kept beside its range, else a small
    line under the value), a time range is .cv-t (never broken) and the words before it its label (.cv-l:
    '하절기(3~10월)', '평일'); any other value is the head (.cv-h). Every run of words goes through keep_units. tail: HTML
    glued to the value's last word ('외'). The text is unchanged."""
    text = str(text or "")
    marks = _top_level(text)
    if not marks:
        return _cell_part(text, tail)
    out, last = [], 0
    for m in marks:
        out.append(f'<span class="ku">{_cell_part(text[last:m.start()], _esc(m.group(1) + m.group(2)))}</span>'
                   + _esc(m.group(3)))
        last = m.end()
    return "".join(out) + f'<span class="ku">{_cell_part(text[last:], tail)}</span>'


def _cell_part(text: str, tail: str = "") -> str:
    a = _trailing_note(text)
    head, note = (text[:a], text[a:]) if a >= 0 else (text, "")
    gap = head[len(head.rstrip()):]
    head = head.rstrip()
    if note:
        cls = "cv-n kfl" if _CELL_TIME.search(note) else "cv-n"
        end = f'{_esc(gap)}<span class="{cls}">{keep_units(note, tail)}</span>'
        tail = ""
    else:
        end = _esc(gap)
    m = _CELL_RANGE.search(head)
    if m:
        label, rng, rest = head[:m.start()], m.group(0), head[m.end():]
        out = (f'<span class="cv-l">{keep_units(label.rstrip())}</span>{_esc(label[len(label.rstrip()):])}'
               if label.strip() else _esc(label))
        out += f'<span class="cv-t">{_esc(rng)}{tail if not rest else ""}</span>'
        if rest:
            out += keep_units(rest, tail)
        return out + end
    return (f'<span class="cv-h">{keep_units(head, tail)}</span>' if head else "") + end
