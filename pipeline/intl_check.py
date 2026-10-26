"""The checks every language version's stored text must pass, shared by the build, validate and tools/intl_table.py
(CLAUDE.md 3절 1·5항, 사용자 지시 2026-10-24: a value is translated, never filled by its sound).

- sound check (translit): a Korean word written by its sound in a translation — Revised Romanization ('Juchajang'
  for 주차장) in the Latin-script versions and Chinese, katakana in Japanese, Kontsevich Cyrillic in Russian — unless
  the word is a proper noun: a place's, course's or event's name, an address, or a word in the version's table
  "proper" list (data/<city>/<code>/table.json). Names of the version are masked before the check.
- report: per version, the records missing or stale against the current Korean (pipeline/en_source.current_hashes,
  the ko_hash every record stores), the stored values and strings rows that write a Korean word by its sound.

Imports: the standard library and pipeline modules (locales, city, en_source, romanize, textutil); tools/ imports this
module, never the other way round.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import locales as LC
from .city import of as city_of
from .en_source import _load, current_hashes
from .romanize import romanize
from .textutil import squash_ws

KINDS = ("places", "guides", "courses", "events")
SLOT = re.compile(r"\{(name|m\d+|w\d+|t\d+|p\d+)\}")
TRAIL_LABEL = re.compile(r"\s*[［【\[][^］】\]]*[］】\]]\s*$")   # an official name's label: ［ユネスコ世界遺産…］


def load_table(data: Path, code: str) -> dict:
    t = _load(data, f"{code}/table.json", {}) or {}
    return {"units": dict(t.get("units") or {}), "names": dict(t.get("names") or {}),
            "proper": list(t.get("proper") or [])}



# ------------------------------------------------------------------ sound check
_PARTICLES = ("입니다", "이며", "이고", "에서", "으로", "부터", "까지", "에게", "이나", "에는", "에도", "은", "는", "이",
              "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "나", "랑")
# words Korean took from English: the version writes its own loanword, which may sound alike (メニュー, ホテル)
KO_LOANWORDS = {"메뉴", "타입", "호텔", "모텔", "펜션", "리조트", "카페", "코스", "캠핑", "텐트", "버스", "택시", "프로그램",
                "체크인", "체크아웃", "커피", "투어", "센터", "파크", "테마파크", "키링", "쿠키", "보트", "카트", "데크",
                "토마토", "파스타", "피자", "샐러드", "스테이크", "치즈", "소스", "라떼", "케이크", "아이스크림", "바베큐",
                "레스토랑", "와인", "맥주", "주스", "스파", "사우나", "캠프", "오토캠핑", "카라반", "글램핑", "바이킹",
                "오일", "크림", "오일파스타", "크림파스타", "스테이크", "필라프", "리코타", "쉬림프", "갈릭"}
_REAL_WORDS = {"hotel", "motel", "pension", "golf", "tennis", "piano", "bus", "taxi", "radio", "video", "camera",
               "drama", "opera", "pasta", "pizza", "salad", "steak", "menu", "data", "mini", "sofa", "piano", "pocha"}

_JA_V = ("ア", "エ", "ヤ", "イェ", "オ", "エ", "ヨ", "イェ", "オ", "ワ", "ウェ", "ウェ", "ヨ", "ウ", "ウォ", "ウェ", "ウィ",
         "ユ", "ウ", "ウィ", "イ")
_JA_JONG = ("", "ク", "ック", "ク", "ン", "ン", "ン", "ッ", "ル", "ルク", "ルム", "ルプ", "ルス", "ルト", "ルプ", "ル", "ム",
            "プ", "プ", "ッ", "ッ", "ン", "ッ", "ッ", "ク", "ッ", "プ", "ッ")
_JA_SYL = {  # consonant row -> the 21 vowels (the table the sound-copy translations used)
    "k": ("カ", "ケ", "キャ", "イェ", "コ", "ケ", "キョ", "イェ", "コ", "クァ", "クェ", "クェ", "キョ", "ク", "クォ", "クェ", "クィ", "キュ", "ク", "クィ", "キ"),
    "n": ("ナ", "ネ", "ニャ", "ニェ", "ノ", "ネ", "ニョ", "ニェ", "ノ", "ヌァ", "ヌェ", "ヌェ", "ニョ", "ヌ", "ヌォ", "ヌェ", "ヌィ", "ニュ", "ヌ", "ヌィ", "ニ"),
    "t": ("タ", "テ", "ティャ", "ティェ", "ト", "テ", "ティョ", "ティェ", "ト", "トァ", "トェ", "トェ", "ティョ", "トゥ", "トォ", "トェ", "トゥィ", "テュ", "トゥ", "トゥィ", "ティ"),
    "r": ("ラ", "レ", "リャ", "リェ", "ロ", "レ", "リョ", "リェ", "ロ", "ルァ", "ルェ", "ルェ", "リョ", "ル", "ルォ", "ルェ", "ルィ", "リュ", "ル", "ルィ", "リ"),
    "m": ("マ", "メ", "ミャ", "ミェ", "モ", "メ", "ミョ", "ミェ", "モ", "ムァ", "ムェ", "ムェ", "ミョ", "ム", "ムォ", "ムェ", "ムィ", "ミュ", "ム", "ムィ", "ミ"),
    "p": ("パ", "ペ", "ピャ", "ピェ", "ポ", "ペ", "ピョ", "ピェ", "ポ", "プァ", "プェ", "プェ", "ピョ", "プ", "プォ", "プェ", "プィ", "ピュ", "プ", "プィ", "ピ"),
    "s": ("サ", "セ", "シャ", "シェ", "ソ", "セ", "ショ", "シェ", "ソ", "スァ", "スェ", "スェ", "ショ", "ス", "スォ", "スェ", "スィ", "シュ", "ス", "スィ", "シ"),
    "": _JA_V,
    "ch": ("チャ", "チェ", "チャ", "チェ", "チョ", "チェ", "チョ", "チェ", "チョ", "チュア", "チュエ", "チュエ", "チョ", "チュ", "チュオ", "チュエ", "チュイ", "チュ", "チュ", "チュイ", "チ"),
    "h": ("ハ", "ヘ", "ヒャ", "ヒェ", "ホ", "ヘ", "ヒョ", "ヒェ", "ホ", "ファ", "フェ", "フェ", "ヒョ", "フ", "フォ", "フェ", "フィ", "ヒュ", "フ", "フィ", "ヒ"),
}
_JA_CHO = ("k", "k", "n", "t", "t", "r", "m", "p", "p", "s", "s", "", "ch", "ch", "ch", "k", "t", "p", "h")


def katakana(word: str) -> str:
    """A Korean word in katakana by its sound (how the sound-copy translations wrote it)."""
    out = []
    for ch in word:
        c = ord(ch) - 0xAC00
        if 0 <= c <= 11171:
            cho, jung, jong = c // 588, c // 28 % 21, c % 28
            pre = "ッ" if cho in (1, 4, 8, 10, 13) else ""
            out.append(pre + _JA_SYL[_JA_CHO[cho]][jung] + _JA_JONG[jong])
    return "".join(out)


def _stems(word: str) -> set[str]:
    out = {word}
    for p in _PARTICLES:
        if word.endswith(p) and len(word) - len(p) >= 2:
            out.add(word[: -len(p)])
    return out


def sound_forms(word: str, code: str) -> set[str]:
    if code == "ja":
        k = katakana(word)
        return {k} if len(k) >= 3 else set()
    if code == "ru":
        k = LC.kontsevich(word).lower()
        return {k} if len(k) >= 4 else set()
    r = re.sub(r"[^a-z]", "", romanize(word).lower())
    return {r} if len(r) >= 4 and r not in _REAL_WORDS else set()


ADDRESS_WORD = re.compile(r"(?:특별시|광역시|[도시군구읍면동리로길])$")
ADDRESS_UNIT = re.compile(r"^[가-힣]+(?:도|특별시|광역시|특별자치시)\s")   # an address: its words are romanized by rule
ROAD = re.compile(r"[가-힣]+(?:대로|로|길)(?=\s?\d)")   # a road name before its number (영부로890번길 30): romanized by rule


def forms_of(ko: str, code: str, proper=()) -> list[tuple[str, str]]:
    """[(Korean word, its sound form)] for the Hangul words of `ko` (placeholders out), longest first; words in
    `proper` (or inside one of them) and the words of an address (a 시·도, 시·군·구, 읍·면·동·리, a road) are left out."""
    proper = set(proper)
    words = {w for run in re.findall(r"[가-힣]{2,}", ROAD.sub(" ", SLOT.sub(" ", ko))) for w in _stems(run)}
    words = {w for w in words if w not in proper and not any(w in p for p in proper) and not ADDRESS_WORD.search(w)
             and w not in KO_LOANWORDS}
    return [(w, f) for w in sorted(words, key=len, reverse=True) for f in sound_forms(w, code)]


def translit(ko: str, text: str, code: str, proper=(), forms=None) -> list[tuple[str, str]]:
    """[(Korean word, its sound form found in text)] for the Hangul words of `ko` written by their sound in `text`."""
    if not text or ADDRESS_UNIT.match(ko):
        return []
    forms = forms_of(ko, code, proper) if forms is None else forms
    if code == "ja":   # a katakana run that is the whole sound copy (not a part of a longer loanword)
        runs = set(re.findall(r"[ァ-ヺー]+", text))
        return [(w, f) for w, f in forms if f in runs]
    if code == "ru":
        hay = text.lower()
        return [(w, f) for w, f in forms if f in hay]
    toks = re.findall(r"[^\W\d_]+", text.lower())   # whole words: 'ragoût' is not 'rago' (라고)
    grams = set(toks) | {a + b for a, b in zip(toks, toks[1:])} | {a + b + c for a, b, c in zip(toks, toks[1:], toks[2:])}
    return [(w, f) for w, f in forms if f in grams]


# ------------------------------------------------------------------ report (stored records)
def mask_names(text: str, names: list[str]) -> str:
    """text with every name of `names` (longest first) taken out, in its prose form too (TRAIL_LABEL)."""
    for n in names:
        for form in {n, TRAIL_LABEL.sub("", n)}:
            if form:
                text = text.replace(form, " ")
    return text


def _texts(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [t for k, v in obj.items() if k not in ("slug", "kind", "ko_hash", "translated_at", "provider",
                                                        "place_slug", "id", "url", "source", "providers", "name_ko",
                                                        "name_en_source") and not k.endswith("_source")
                for t in _texts(v)]
    if isinstance(obj, list):
        return [t for v in obj for t in _texts(v)]
    return []


def _proper_names(data: Path) -> set[str]:
    """The Hangul words of every name the versions write by their sound on purpose: places (and their other names,
    TourAPI titles, addresses), courses, events."""
    out: set[str] = set()
    for p in _load(data, "places.json", []) or []:
        for n in [p.get("name"), *(p.get("alternate_names") or []), (p.get("tourapi") or {}).get("title")]:
            out |= set(re.findall(r"[가-힣]{2,}", str(n or "")))
        addr = (p.get("facts") or {}).get("address")
        addr = addr.get("value") if isinstance(addr, dict) else addr
        out |= set(re.findall(r"[가-힣]{2,}", str(addr or "")))
    for c in _load(data, "courses.json", []) or []:
        out |= set(re.findall(r"[가-힣]{2,}", str(c.get("name") or "")))
    for e in _load(data, "events.json", []) or []:
        out |= set(re.findall(r"[가-힣]{2,}", " ".join(str(e.get(k) or "") for k in ("name", "series", "place_name"))))
    return out


def report(data: Path, codes: list[str]) -> dict:
    """Per version: the records missing or stale against the current Korean (their keys in missing_ids / stale_ids),
    and the stored values and strings rows that write a Korean word of their Korean source by its sound (examples).
    Names (every place, course and event name, the areas of the addresses, the version's place names) and each
    table's "proper" words are not counted."""
    data = Path(data)
    site = _load(data, "site.json", {})
    city = city_of(site)
    hashes = current_hashes(data, city=city)
    sources = {"places": {p["id"]: p for p in _load(data, "places.json", []) or []},
               "guides": {g["id"]: g for g in _load(data, "guides.json", []) or []},
               "courses": {c["id"]: c for c in _load(data, "courses.json", []) or []}}
    proper_names = _proper_names(data)
    events_ko = " ".join(_texts(_load(data, "events.json", []) or []))
    out = {}
    for code in codes:
        tbl = load_table(data, code)
        proper = set(tbl["proper"]) | proper_names
        row = {"stale": 0, "missing": 0, "stale_ids": [], "missing_ids": [], "records": 0, "records_with_sound": 0,
               "values": 0, "values_with_sound": 0, "strings": 0, "strings_with_sound": 0, "examples": []}
        # the place names of this version, masked in the stored texts ('Надыри' holds the sound of 아들이)
        name_key = "name_en" if code == "en" else LC.get(code).name_key
        version_names = sorted({squash_ws(r.get(name_key)) for r in (_load(data, f"{code}/places.json", {}) or {}).values()
                                if squash_ws(r.get(name_key))}, key=len, reverse=True)
        for kind in KINDS:
            recs = _load(data, f"{code}/{kind}.json", {}) or {}
            for key, h in hashes[kind].items():
                rec = recs.get(key)
                if not rec:
                    row["missing"] += 1
                    row["missing_ids"].append(f"{kind}/{key}")
                    continue
                if rec.get("ko_hash") != h:
                    row["stale"] += 1
                    row["stale_ids"].append(f"{kind}/{key}")
                src = sources.get(kind, {}).get(key)
                ko = events_ko if kind == "events" else " ".join(_texts(src)) if src else json.dumps(rec, ensure_ascii=False)
                vals = [mask_names(t, version_names) for t in
                        _texts({k: v for k, v in rec.items() if not k.startswith("name_")})]
                row["records"] += 1
                row["values"] += len(vals)
                hits = 0
                forms = forms_of(ko, code, proper)
                for v in vals:
                    found = translit(ko, v, code, forms=forms)
                    if found:
                        hits += 1
                        if len(row["examples"]) < 12:
                            row["examples"].append(f"{kind}/{key}: {found[0][1]} ({found[0][0]})")
                row["values_with_sound"] += hits
                row["records_with_sound"] += 1 if hits else 0
        # the strings rows (labels, theme and region names, site texts): each against its own Korean source
        tag = "en" if code == "en" else LC.get(code).tag
        for rid, r in (_load(data, f"{code}/strings.json", {}) or {}).items():
            ko, tr = r.get("ko"), r.get(tag)
            if not isinstance(ko, str) or not isinstance(tr, str):
                continue
            row["strings"] += 1
            found = translit(ko, mask_names(tr, version_names), code, proper)
            if found:
                row["strings_with_sound"] += 1
                if len(row["examples"]) < 12:
                    row["examples"].append(f"strings/{rid}: {found[0][1]} ({found[0][0]})")
        out[code] = row
    return out
