"""URL slugs and fragment ids: ASCII only, Revised Romanization of the Korean name (CLAUDE.md 2, design 2.2).

A public URL uses only the `slug` stored in the data. The places that first decide a slug (pipeline.importer, the
TourAPI new-place step, the event step of the bulk tool) write it into the data; the build never writes one back.
After publication a slug never changes, so the rules here only ever run for records that have none yet:

- slugify(name, admin_words=...): NFC, brackets dropped, a space between Latin/digits and Hangul, RR with only the
  named administrative units hyphenated ('한빛동 철길마을' with admin_words={'한빛동'} -> 'hanbit-dong-cheolgilmaeul'),
  then ascii_core: [a-z0-9-] only, at most SLUG_MAX_LEN characters cut at a '-' (a single longer word is cut).
  '' when nothing ASCII is left ('大邱'): the caller then uses fallback_slug.
- assign_slugs: stored slugs are reserved first and never renamed (a malformed or duplicate stored slug is a
  problem the caller reports); records without one get a slug in id order, a collision taking the 구·군 suffix
  ('-jung-gu', policy "district") and then a number ('-2', '-3').
- series_slug, topic_slug, anchor_id: one rule for event series, video topics and ASCII fragment ids.

A leaf module: the standard library and pipeline.romanize only (textutil, city and build import it).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping

from .romanize import romanize

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX_LEN = 60
SLUG_POLICIES = ("district", "number")
YEAR_PREFIX = re.compile(r"^20\d\d\s+")
EDITION = re.compile(r"(?:^|\s)제\s*\d+\s*회(?=\s|$)")
_BRACKETS = re.compile(r"\(.*?\)|\[.*?\]|（.*?）")
_LATIN_HANGUL = re.compile(r"(?<=[A-Za-z0-9])(?=[가-힣])|(?<=[가-힣])(?=[A-Za-z0-9])")
_DONG_GA = re.compile(r"^([가-힣]+동)[0-9]+가$")
OTHER_TOPIC = ("기타", "other")
# Fixed fragment keys (design 2.2): course groups, and the 가나다 index initials (anything else: 'other').
COURSE_GROUP_IDS = {"당일": "day-trip", "1박 2일": "one-night", "2박 3일": "two-nights"}
INITIAL_IDS = {"ㄱ": "g", "ㄴ": "n", "ㄷ": "d", "ㄹ": "r", "ㅁ": "m", "ㅂ": "b", "ㅅ": "s", "ㅇ": "ng", "ㅈ": "j",
               "ㅊ": "ch", "ㅋ": "k", "ㅌ": "t", "ㅍ": "p", "ㅎ": "h"}


def _squash(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def is_slug(value: str | None) -> bool:
    """A well-formed slug: SLUG_RE and at most SLUG_MAX_LEN characters."""
    return bool(value) and len(value) <= SLUG_MAX_LEN and bool(SLUG_RE.match(value))


def ascii_core(text: str | None, max_len: int = SLUG_MAX_LEN) -> str:
    """The ASCII part of a text as one slug: NFKD (accents dropped), every other non-ASCII character a word break,
    '&' read 'and', lowercase words of [a-z0-9] joined by '-', cut at a word boundary within max_len (a first word
    longer than max_len is cut). pipeline.en_site.en_slug is this plus its English tail rule. '' when no word."""
    t = unicodedata.normalize("NFKD", _squash(text))
    t = "".join(c if c.isascii() else ("" if unicodedata.category(c).startswith("M") else " ") for c in t).lower()
    t = t.replace("&", " and ").replace("'", "")
    out: list[str] = []
    for w in (w for w in re.split(r"[^a-z0-9]+", t) if w):
        if out and len("-".join(out + [w])) > max_len:
            break
        out.append(w[:max_len])
    return "-".join(out)


def _admin_set(admin_words: Iterable[str]) -> frozenset:
    """The named administrative words, plus the 동 of a 법정동 'N가' ('삼덕동1가' also names '삼덕동')."""
    words = {_squash(w) for w in admin_words or () if _squash(w)}
    return frozenset(words | {m.group(1) for w in words if (m := _DONG_GA.match(w))})


def slugify(name: str | None, *, admin_words: Iterable[str] = ()) -> str:
    """'서문 시장' -> 'seomun-sijang', '83타워' -> '83-tawo', 'E-World(이월드)' -> 'e-world'; '' when nothing ASCII is
    left. Only `admin_words` (whole words: the place's 구·군, 동·읍·면) are hyphenated as units: '한빛동 철길마을' ->
    'hanbit-dong-cheolgilmaeul' with admin_words={'한빛동'}, 'hanbitdong-cheolgilmaeul' without. No English stop
    words are dropped."""
    admin = _admin_set(admin_words)
    s = _BRACKETS.sub("", unicodedata.normalize("NFC", name or ""))
    words = [w if w in admin else _LATIN_HANGUL.sub(" ", w) for w in s.split()]
    return ascii_core(romanize(" ".join(words), admin=admin), SLUG_MAX_LEN)


def _fit(slug: str, max_len: int) -> str:
    """An ASCII slug cut at a '-' within max_len (ascii_core's rule)."""
    return ascii_core(slug, max(max_len, 1))


def fallback_slug(kind: str, rec_id) -> str:
    """When a name gives no slug: '<kind>-<the id's trailing number>' ('tourapi-126508' -> 'place-126508'), else
    '<kind>-<slugify(id)>', else '<kind>-<sha1(id)[:6]>'."""
    rid = _squash(rec_id)
    m = re.search(r"([0-9]+)$", rid)
    if m:
        return _fit(f"{kind}-{m.group(1)}", SLUG_MAX_LEN)
    core = slugify(rid)
    if core:
        return _fit(f"{kind}-{core}", SLUG_MAX_LEN)
    return f"{kind}-{hashlib.sha1(rid.encode('utf-8')).hexdigest()[:6]}"


def _natural(text: str) -> list:
    """Sort key: digit runs compared as numbers ('p-2' before 'p-10')."""
    return [int(t) if t.isdigit() else t for t in re.split(r"([0-9]+)", text)]


def _label(it: dict, name_key: str) -> str:
    return f"[{it.get('id') or '?'} {_squash(it.get(name_key))}]"


def assign_slugs(items: list[dict], *, name_key: str, kind: str, policy: str = "number", reserved: Iterable[str] = (),
                 district_of: Callable[[dict], str] | None = None,
                 admin_of: Callable[[dict], Iterable[str]] | None = None) -> list[str]:
    """Give every item without a stored `slug` one, in place; returns the problems (Korean, one line each).

    1. Stored slugs (and `reserved`, e.g. records already in the file) are reserved first. A stored slug that breaks
       SLUG_RE / SLUG_MAX_LEN, or one already taken, is a problem — it is never renamed (a published URL stays).
    2. The others, in id order (natural), get slugify(name, admin_words=admin_of(item)), or fallback_slug(kind, id)
       when that is empty. On a collision, policy "district" first adds the 구·군 suffix (district_of(item): a 구·군
       name or its slug, '' when unknown), then '-2', '-3' …; policy "number" adds the number only. The name part
       is cut so the whole slug stays within SLUG_MAX_LEN. A generated record is marked `_slug_generated=True`
       (memory only: callers that write the file drop the flag)."""
    if policy not in SLUG_POLICIES:
        raise ValueError(f"slug policy {policy!r} (허용: {', '.join(SLUG_POLICIES)})")
    problems: list[str] = []
    taken: dict[str, str] = {s: "기존 기록" for s in reserved or () if s}
    for it in items:
        s = it.get("slug")
        if not s:
            continue
        s = str(s)
        if not is_slug(s):
            problems.append(f"{_label(it, name_key)} 저장된 slug 형식 오류: {s!r} "
                            f"(a-z·0-9·하이픈, {SLUG_MAX_LEN}자 이하)")
        if s in taken:
            problems.append(f"{_label(it, name_key)} 저장된 slug 중복: {s} (이미 {taken[s]})")
        else:
            taken[s] = _label(it, name_key)
    for it in sorted((x for x in items if not x.get("slug")), key=lambda x: _natural(_squash(x.get("id")))):
        base = (slugify(it.get(name_key), admin_words=admin_of(it) if admin_of else ())
                or fallback_slug(kind, it.get("id")))
        slug = base
        if slug in taken:
            dist = ""
            if policy == "district" and district_of:
                d = _squash(district_of(it))
                dist = d if SLUG_RE.match(d) else slugify(d, admin_words=(d,))
            slug, n = "", 1 if dist else 2
            while not slug or slug in taken:
                suffix = (f"-{dist}" if dist else "") + (f"-{n}" if n > 1 else "")
                slug, n = _fit(base, SLUG_MAX_LEN - len(suffix)) + suffix, n + 1
        it["slug"], it["_slug_generated"] = slug, True
        taken[slug] = _label(it, name_key)
    return problems


def series_slug(editions: list[dict], name: str | None, taken: set) -> str:
    """The URL slug of an event series: the newest edition's stored `slug` (editions by start/end date, newest
    first; the first stored one wins), else slugify(name without a leading year and '제N회'), '-2' … when taken,
    fallback_slug('event', newest id) when the name gives nothing. The chosen slug is added to `taken`. Callers
    reserve every series' stored slug in `taken` first, so a generated one never takes it. pipeline.build and
    pipeline.en_source share this rule (the Korean and English pages of a series have the same slug)."""
    newest = sorted(editions, key=lambda x: (x.get("start_date") or "", x.get("end_date") or ""), reverse=True)
    for ev in newest:
        stored = _squash(ev.get("slug"))
        if stored:
            taken.add(stored)
            return stored
    core = EDITION.sub(" ", YEAR_PREFIX.sub("", _squash(name)))
    base = slugify(core) or fallback_slug("event", (newest[0] if newest else {}).get("id") or core)
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{_fit(base, SLUG_MAX_LEN - len(str(n)) - 1)}-{n}", n + 1
    taken.add(slug)
    return slug


def topic_slug(title: str | None, configured: Mapping[str, str] | Iterable[tuple[str, str]] = (),
               taken: set | None = None) -> str:
    """A video topic's slug: the configured one (site.json video_topics, as given), '기타' -> 'other', else
    slugify(title with '·' as a space), '-2' … when `taken` already holds it. The chosen slug is added to `taken`."""
    conf = dict(configured.items() if isinstance(configured, Mapping) else configured or ())
    t = _squash(title)
    if t in conf:
        slug = conf[t]
    elif t == OTHER_TOPIC[0]:
        slug = OTHER_TOPIC[1]
    else:
        base = slugify(t.replace("·", " ")) or fallback_slug("topic", t)
        slug, n = base, 2
        while taken is not None and slug in taken:
            slug, n = f"{_fit(base, SLUG_MAX_LEN - len(str(n)) - 1)}-{n}", n + 1
    if taken is not None:
        taken.add(slug)
    return slug


def initial_id(initial: str | None) -> str:
    """The ASCII key of a 가나다 index initial ('ㅇ' -> 'ng'); any other bucket (Latin letters, digits) -> 'other'."""
    return INITIAL_IDS.get(_squash(initial), "other")


def _key_id(key) -> str:
    k = _squash(key)
    if k in COURSE_GROUP_IDS:
        return COURSE_GROUP_IDS[k]
    if k in INITIAL_IDS:
        return INITIAL_IDS[k]
    if SLUG_RE.match(k):
        return k
    return slugify(k) or hashlib.sha1(k.encode("utf-8")).hexdigest()[:6]


def anchor_id(prefix: str, *keys) -> str:
    """An ASCII fragment id: anchor_id('g', '당일') -> 'g-day-trip', anchor_id('i', 'ㅇ') -> 'i-ng',
    anchor_id('d', 'jung-gu', '한빛동') -> 'd-jung-gu-hanbitdong'. A key that is already a slug (a region key from
    City.region_key) is kept; other text is slugified (a short hash when nothing ASCII is left)."""
    return "-".join([prefix, *(_key_id(k) for k in keys)])
