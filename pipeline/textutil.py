"""Text helpers shared by the pipeline.

Imports: the standard library and pipeline.slugs (a leaf) only, so every other pipeline module may import this one.
"""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata

from .slugs import YEAR_PREFIX

_TAG_BR = re.compile(r"<\s*br\s*/?\s*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t 　]+")
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_URL = re.compile(r"https?://[^\s<>\"']+")
# A character reference only when it ends in ';' ('&amp;', '&#38;'): html.unescape also decodes legacy names without
# one, so a query '&region=1' became '®ion=1' (a dead link). Hangul glued straight onto a URL's last ASCII letter or
# digit is the label the source ran into it ('…example.kr한빛시장', '…/blogid공식'), not part of the address; a
# Hangul domain ('http://한글.com') or path segment ('/index.php/한글') starts after '/' or '.', so it stays.
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_GLUED_LABEL = re.compile(r"(?<=[A-Za-z0-9])[가-힣].*$")
# Map services' place pages: a link the page already makes (길찾기), never the place's own homepage.
MAP_HOSTS = ("map.naver.com", "m.map.naver.com", "map.kakao.com", "place.map.kakao.com", "m.map.kakao.com",
             "maps.google.com", "google.com/maps", "maps.app.goo.gl")
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


def _unescape_refs(text: str) -> str:
    """html.unescape for complete character references only ('&amp;' -> '&'; '&region=1' stays)."""
    return _ENTITY.sub(lambda m: html.unescape(m.group(0)), text)


def _url_part(text: str) -> str:
    return _GLUED_LABEL.sub("", text.strip())


def extract_url(value: str | None) -> str:
    """TourAPI 'homepage' fields are often '<a href=...>...</a>'. Return the first URL: an href that is a web address
    (a malformed '<a href="<a href="…' captures '<a href=', which is skipped), else the first http(s) address in the
    text. Only complete character references are decoded, and a label glued onto the address is not part of it."""
    if not value:
        return ""
    for m in _HREF.finditer(value):
        url = _url_part(_unescape_refs(m.group(1)))
        if web_url(url):
            return url
    m = _URL.search(_unescape_refs(value))
    return _url_part(m.group(0)) if m else ""


def homepage_url(value: str | None) -> str:
    """extract_url for a place's or an event's homepage: a map service's place page ('map.naver.com/…/place/…') is
    not a homepage (the page links the maps itself), so it gives ''."""
    url = extract_url(value)
    low = re.sub(r"^https?://(?:www\.)?", "", url.lower())
    return "" if any(low.startswith(h) for h in MAP_HOSTS) else url


# A phone number written with a space or an en/em dash between its parts ('054 637-9121', '054–631-3332',
# '054-638–7008' — TourAPI and city pages, QA 2026-10-24 YJ-10): read as the hyphenated number. Only the separators
# between the area code, the exchange and the line number change; a value with no such number stays as it is.
_SPACED_PHONE = re.compile(r"(?<![\d-])(0\d{1,2})[\s\u2013\u2014-]+(\d{3,4})[\s\u2013\u2014-]+(\d{4})(?![\d-])")


def hyphenate_phones(value: str | None) -> str:
    """'054 637-9121' -> '054-637-9121'; '054–631-3332' -> '054-631-3332'; anything else unchanged."""
    text = str(value or "")
    return _SPACED_PHONE.sub(r"\1-\2-\3", text) if re.search(r"[\s\u2013\u2014]", text) else text


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


# An 문의 value that names another organisation than the place: a 시·도·구·군청 or one of its departments, a 읍·면·동
# 행정복지센터, a tourist information desk, a national park office. National administrative words only (no city names).
_ORG_CONTACT = re.compile(r"[가-힣]+(?:시|도|구|군)\s*청|(?:시|도|구|군)\s+[가-힣]*과(?![가-힣])|행정복지센터|주민센터"
                          r"|관광\s*(?:정보\s*)?(?:센터|안내소)|안내\s*센터|국립공원[가-힣]*사무소")


def contact_org(value: str | None, name: str | None = "") -> str:
    """The organisation an 문의 value names when it is not the place itself: 'OO관광정보센터 053-000-0000' ->
    'OO관광정보센터', '한빛구청 문화관광과 053-000-0000' -> '한빛구청 문화관광과'; '' for a bare number, the place's own
    office ('OO국립공원동부사무소' on the page of OO국립공원) or any other wording. Its number is that organisation's,
    so pages print the name beside it and the structured data does not give it as the place's telephone."""
    label = _PHONE.sub(" ", str(value or ""))
    label = squash_ws(re.sub(r"~\s*\d+|[,/()·:]", " ", label)).strip(" -")
    if not label or not _ORG_CONTACT.search(label):
        return ""
    own, org = normalize_name(name), normalize_name(label)
    if own and (own in org or org in own):
        return ""
    return label


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


# The national table of administrative renames (facts with a date, not a city setting): sources still write the
# old or short form. City-specific short forms ('OO시 …' for 'OO광역시 …') are not rewritten here: they are read
# as the city only when parsing (pipeline.city.City.parse_address, site.json address_aliases).
ADDRESS_RENAMES = (
    (re.compile(r"^(?:전라북도|전북\s*특별자치도|전북)\s+"), "전북특별자치도 "),   # 전북특별자치도 출범 2024-01-18
    (re.compile(r"^(?:경상북도|경북)\s*군위군"), "대구광역시 군위군"),             # 군위군 편입 2023-07-01
    # 읍 승격 (달성군 연혁, dalseong.daegu.kr 'menu_id=00000257', 확인 2026-10-11): 유가 2018-03-01, 옥포·현풍
    # 2018-11-01, 구지 2026-09-30 — TourAPI still writes some of them as 면
    (re.compile(r"^(대구광역시\s*달성군\s*)(유가|옥포|현풍|구지)면(?![가-힣])"), r"\1\2읍"),
)


def display_address(raw: str | None) -> str:
    """Address as shown: only a renamed province/county prefix is rewritten (ADDRESS_RENAMES, the national table of
    dated renames). Nothing else is derived (no 지번, no postcode). The stored value stays the source string."""
    text = squash_ws(raw)
    for rx, new in ADDRESS_RENAMES:
        text = rx.sub(new, text, count=1)
    return text


def normalize_name(name: str | None) -> str:
    """Normalise a place name for matching: NFC, drop bracketed parts, spaces, punctuation."""
    s = unicodedata.normalize("NFC", name or "")
    s = re.sub(r"\(.*?\)|\[.*?\]|（.*?）", "", s)
    s = re.sub(r"[\s\-_·.,'\"!?~/]", "", s)
    return s.lower()


def event_name_key(name: str | None) -> str:
    """An event name as a series key: without a leading year ('2026 한빛축제' -> '한빛축제'), normalize_name'd."""
    return normalize_name(YEAR_PREFIX.sub("", squash_ws(name)))


def series_key(ev: dict) -> str:
    """The series an events.json record belongs to: its `series`, else its name, as event_name_key. The one grouping
    rule of pipeline.build.event_series, pipeline.en_source.event_series, pipeline.validate's slug check and
    pipeline.enrich (a new record's stored series slug)."""
    return event_name_key(squash_ws(ev.get("series")) or squash_ws(ev.get("name")))


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


# a bracket's first item: '(한빛동)', '(한빛동1가, …)', '(누리로2가)' — a 법정동 'N가' is kept whole
_AREA_PAREN = re.compile(r"\(([가-힣0-9]+(?:동|면|읍)(?:[0-9]+가)?|[가-힣]+로[0-9]+가)(?:[,\s][^()]*)?\)")
_AREA_TOKEN = re.compile(r"(?:^|[\s(])([가-힣]+[0-9]*(?:읍|면|동))(?=[\s,)\d]|$)")


def area_from_address(address: str | None) -> str:
    """읍·면·동 named in an address, e.g. 'OO시 경촌4길 14(한빛동)' -> '한빛동', '… (삼덕동1가)' -> '삼덕동1가'. Empty
    when not stated. City-blind; pipeline.city.City.parse_address reads the 구·군 and the 동 by position."""
    text = address or ""
    m = _AREA_PAREN.search(text)
    if m:
        return m.group(1)
    m = _AREA_TOKEN.search(text)
    return m.group(1) if m else ""


_ROAD = re.compile(r"(?:^|\s)([가-힣]+[0-9]*(?:로|길)(?:\s?[0-9]+번?길)?)\s+[0-9]")


def road_from_address(address: str | None) -> str:
    """Road name of a road-name address, e.g. '한빛시 내항2길 32' -> '내항2길'. Empty when not found."""
    m = _ROAD.search(address or "")
    return m.group(1).replace(" ", "") if m else ""


_ROAD_NO = re.compile(r"([가-힣0-9]+(?:로|길))\s*([0-9]+(?:-[0-9]+)?)")


def address_norm(address: str | None) -> str:
    """An address without brackets, spaces and the leading 시·도 and 시 ('한빛도 한빛시 누리면 해솔리 (일원)' ->
    '누리면해솔리'; a 광역시's 구·군 stays: 'OO광역시 누리구 해솔로 3' -> '누리구해솔로3'), for comparing two spellings of
    one address. The national renames (ADDRESS_RENAMES) are applied first, so an old 시·도 name compares equal."""
    a = re.sub(r"\([^)]*\)", "", display_address(address)).strip()
    a = re.sub(r"^[가-힣]+(?:특별자치도|특별자치시|광역시|특별시|도)\s+", "", a)
    a = re.sub(r"^[가-힣]{1,4}시\s+", "", a)   # the city as its own word ('한빛시 '), never an island's '…시도'
    return re.sub(r"\s+", "", a)


def address_key(address: str | None) -> str:
    """One building's key: road + number ('한빛시 해솔4길 14(누리동)' -> '해솔4길14', as tools/tourapi_bulk.road_key),
    else the normalized address (address_norm)."""
    m = _ROAD_NO.search(re.sub(r"\s+", " ", address or ""))
    return f"{m.group(1)}{m.group(2)}" if m else address_norm(address)


# the final consonant of a number read aloud: 1 일·3 삼·6 육·7 칠·8 팔 have one, 2 이·4 사·5 오·9 구 do not; a number
# ending in 0 ends in 십·백·천·만 (all with one). 8 = ㄹ (as 'ㄹ' for '으로/로').
_DIGIT_FINAL = {"0": 1, "1": 8, "2": 0, "3": 16, "4": 0, "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}
_TAIL_BRACKET = re.compile(r"\s*[(（][^()（）]*[)）]\s*$")


def josa(word: str, pair: str) -> str:
    """Attach the right Korean particle: josa('코스', '으로/로') -> '코스로', josa('공원', '은/는') -> '공원은'.
    A trailing bracket is read past ('트리풀(treefull)' -> '트리풀(treefull)은') and a final number is read aloud
    ('스테이700' -> '스테이700은', '라운드힐 905' -> '라운드힐 905는')."""
    with_final, without_final = pair.split("/")
    base = (word or "").rstrip()
    while _TAIL_BRACKET.search(base) and _TAIL_BRACKET.sub("", base):
        base = _TAIL_BRACKET.sub("", base)
    last = base[-1:] or " "
    if last in _DIGIT_FINAL:
        final = _DIGIT_FINAL[last]
    else:
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
    """'https://www.example.kr/x' -> 'example.kr'."""
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


_SECONDS = re.compile(r"(?<![\d:])(\d{1,2}:\d{2}):00(?![\d:])")


def clock_text(text: str | None) -> str:
    """A check-in/check-out time as a reader reads it: '15:00:00' -> '15:00' (zero seconds only; other text kept)."""
    return _SECONDS.sub(r"\1", str(text or ""))


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


def dash_times(text: str | None) -> str:
    """'10:00~21:00', '10:00 - 21:00' -> '10:00–21:00' (the times themselves are kept as written)."""
    return _TIME_RANGE.sub(lambda m: f"{m.group(1)}–{m.group(2)}", text or "")


# a day or season label run straight onto the previous time range: '평일 10:30~19:00주말 10:30~19:30'
_GLUED_TIME_LABEL = re.compile(r"(?<=\d:\d\d)(?=(?:[월화수목금토일]요일|주말|주중|평일|하절기|동절기|체험\s*운영))")


def restore_lines(raw: str | None) -> list[str]:
    """Line breaks that TourAPI text lost: before '[group]' (also after a space: '… 19:00 [주말/공휴일] …') and
    after it, before a glued '- item', before '※ note', before a day or season label glued to a time ('19:00주말 …').
    Presentation only — no character is dropped except the joining whitespace."""
    s = str(raw or "").replace("\r", "")
    s = re.sub(r"(?<=[^\s\[])[ \t]*\[", "\n[", s)
    s = re.sub(r"\]\s*(?=\S)", "]\n", s)
    s = _GLUED_TIME_LABEL.sub("\n", s)
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


def parking_compatible(a: str | None, b: str | None) -> bool:
    """Two sources' parking values that hold together (QA 2026-10-24 YJ-09): one says parking is possible ('가능',
    '가능(150대)', '주차가능'), the other only what it costs ('무료', '유료') — no contradiction, so neither is flagged as
    '출처마다 다름'. '불가능' against '자체 주차장', '무료' against '유료' still are."""
    def kind(t):
        t = squash_ws(parking_text(t))
        if re.fullmatch(r"(?:주차\s*)?(?:요금\s*)?(?:무료|유료)", t):
            return "fee"
        if re.match(r"^(?:주차\s*)?가능", t) and not re.search(r"불가|유료|무료", t):
            return "yes"
        return ""
    return {kind(a), kind(b)} == {"fee", "yes"}


def course_display_name(name: str | None) -> str:
    """'A코스 | 근대~섬' -> 'A코스 근대~섬' (the source's separator pipe is not shown)."""
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
    if key in ("checkin", "checkout"):
        text = clock_text(text)
    if key in ("infocenter", "reservation"):   # a number written with a space or a dash between its groups is shown
        text = hyphenate_phones(text)           # (and linked) as one: '054 637-9121' -> '054-637-9121'
    return "\n".join(tidy_punct(dash_times(x)) for x in restore_lines(text))


def tidy_punct(text: str) -> str:
    """Source spacing around punctuation as a reader expects it: no space before a comma ('생등심 , 갈비탕' ->
    '생등심, 갈비탕'; '떡갈비 ,곰탕' stays: a comma between two words is one word to the validator) or inside brackets ('25(일 )' -> '25(일)'). Words and symbols stay (value_tokens ignore both)."""
    text = re.sub(r"\s+,(?=\s)", ",", text)
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", text))


# ---------------------------------------------------------------- value-shown check (pipeline.validate)
# A word token is a maximal run of letters/digits that may hold joiners between them ('10:00–21:00',
# '3,000원', '063-445-2429', '토·일', 'example.kr'). Every other character is a token of its own ('~' in
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


# ---------------------------------------------------------------------------------------------- clock words
# an hours value written in words for the clock ('AM 10시 ~ PM 10시', '오전 8시~ 오후 23시', '오전10-오후10시', '9시~18시',
# '오후 8시 30분'): the same times as HH:MM, for the course planner's reading of the hours (chat_index plan_facts — the
# page shows the value as the source writes it). 오후·PM adds 12 to an hour under 12; 오전·AM 12 is 00. '1시간' (an
# hour's length), '24시간' and a number with no 시 are left alone.
_CLOCK_WORD = re.compile(
    r"(?:(?P<ap>오전|오후|AM|PM|am|pm|a\.m\.|p\.m\.)\s*)?(?<![\d:.])(?P<h>\d{1,2})"
    r"(?:\s*:\s*(?P<m1>\d{2})|\s*시(?!간|즌|대|경)(?:\s*(?P<m2>\d{1,2})\s*분|\s*반)?|(?=\s*[~∼～〜\-–]\s*(?:오전|오후|AM|PM|am|pm)))")


def clock_hours(text: str | None) -> str:
    """'AM 10시 ~ PM 10시' → '10:00 ~ 22:00', '오전10-오후10시' → '10:00-22:00', '9시~18시' → '09:00~18:00'; a value with no
    clock words as it is."""
    s = str(text or "")

    def one(m: re.Match) -> str:
        ap = (m.group("ap") or "").lower().replace(".", "")
        word = m.group(0)
        if not ap and ":" in word:   # already a clock time
            return word
        h = int(m.group("h"))
        mi = int(m.group("m1") or m.group("m2") or (30 if word.rstrip().endswith("반") else 0))
        if h > 24 or mi > 59 or (ap and h > 23 and ap in ("오후", "pm")):
            return word
        if ap in ("오후", "pm") and h < 12:
            h += 12
        elif ap in ("오전", "am") and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}"
    return _CLOCK_WORD.sub(one, s)


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
_HEADING = re.compile(r'(?<!<div class="qa">)(?<!<summary>)(<h[1-3]\b[^>]*>)(.*?)(</h[1-3]>)', re.S)
_TITLE_LINK = re.compile(r'(<a class="line-name"[^>]*>)(.*?)(</a>)', re.S)   # a course row's title (courses, home)
_DOT = re.compile(r"([^\s<>·;])·")


_UNIT_END = re.compile(r'(<span class="dj">[^<]*·</span>)(?=[^\s<])')   # a unit with a letter after it


def _dot_unit(m: re.Match) -> str:
    """'장·' kept whole, then a <wbr> when a letter follows: under word-break: keep-all the dot is a title's only break
    ('가가가가·나나나나·다다다다다·라라라라 성곽 기행'), and the unit's nowrap would take it away (a phone's row overflowed)."""
    tail = m.string[m.end():m.end() + 1]
    return f'<span class="dj">{m.group(1)}·</span>' + ("<wbr>" if tail and not tail.isspace() else "")


def keep_dots(html_text: str) -> str:
    """A title never starts a line with '·': in every h1–h3 and course-row title the dot is kept with the letter
    before it (<span class="dj">장·</span>); the line may still break after the dot. Only text between tags changes,
    so the title's text stays as written. An FAQ question (div.qa h3, a summary's h3 — details.qa, open or not) is left alone:
    pipeline.validate finds each FAQPage question name word for word in the page's text runs, and a span would split
    it (as in the 부평시장각 engine)."""
    def heading(m: re.Match) -> str:
        parts = re.split(r"(<[^>]+>)", m.group(2))
        out, inside = [], 0
        for x in parts:   # text already in a unit (the ku filter's <span class="dj">) is left as it is
            if x.startswith("<"):
                inside += 1 if x.startswith('<span class="dj"') else -1 if (x == "</span>" and inside) else 0
                out.append(x)
            else:
                out.append(x if inside else _DOT.sub(_dot_unit, x))
        body = _UNIT_END.sub(r"\1<wbr>", "".join(out))
        return m.group(1) + body + m.group(3)
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
PART_MAX = 10   # a spaced-list part up to this many characters is one unit ('매주 월요일', 'A코스 화성~행궁')


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
    """Where the bracket that ends `text` opens ('가능 (○○박물관, …)' → 3), or -1: none, unbalanced, the whole
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
