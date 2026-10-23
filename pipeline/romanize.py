"""Revised Romanization of Korean (문화관광부 고시 2000-8, MCST rules) — a leaf module (standard library only).

Two callers, two modes:
- the English pages (pipeline.en_site, pipeline.en_source): romanize(text) capitalises each word and hyphenates a
  word that looks like an administrative unit ('한빛동 철길마을' -> 'Hanbit-dong Cheolgilmaeul');
- slugs (pipeline.slugs): romanize(text, admin=frozenset(words)) hyphenates only the administrative names the
  caller passes (the place's 구·군 and 동·읍·면 from its address), never a guess from the last syllable — '다니면'
  stays 'Danimyeon' and '평양냉면' 'Pyeongyangnaengmyeon'.

The default mode is the one pipeline.en_source has always used (byte-identical output). It must not import
pipeline.textutil (textutil -> slugs -> romanize), so it keeps its own whitespace squash.
"""
from __future__ import annotations

import re

HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")

# ------------------------------------------------------------------ Revised Romanization (문화관광부 2000)
_CHO = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_JUNG = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
         "yu", "eu", "ui", "i")
# final consonant before another consonant or at the end of a word (index = jongseong 0..27)
_JONG = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
         "ng", "t", "t", "k", "t", "p", "t")
# final consonant before a vowel (initial ㅇ): (kept in this syllable, carried to the next) — liaison
_LIAISON = {1: ("", "g"), 2: ("", "kk"), 3: ("k", "s"), 4: ("", "n"), 5: ("n", "j"), 6: ("n", ""), 7: ("", "d"),
            8: ("", "r"), 9: ("l", "g"), 10: ("l", "m"), 11: ("l", "b"), 12: ("l", "s"), 13: ("l", "t"),
            14: ("l", "p"), 15: ("", "r"), 16: ("", "m"), 17: ("", "b"), 18: ("p", "s"), 19: ("", "s"),
            20: ("", "ss"), 21: ("ng", ""), 22: ("", "j"), 23: ("", "ch"), 24: ("", "k"), 25: ("", "t"),
            26: ("", "p"), 27: ("", "")}
_K, _T, _P = {1, 2, 3, 9, 24}, {7, 19, 20, 22, 23, 25, 27}, {14, 17, 18, 26}
_L = {8, 11, 12, 13, 15}
_ADMIN = {"동": "dong", "읍": "eup", "면": "myeon", "리": "ri"}
# Slug mode: every administrative unit a caller may name (시·도, 구·군, 읍·면·동·리, 법정동 'N가'). The unit is
# written after a hyphen, without sound change across it ('한빛구' Hanbit-gu, '누리군' Nuri-gun).
_UNIT = {**_ADMIN, "도": "do", "시": "si", "군": "gun", "구": "gu", "가": "ga"}
_UNIT_WORD = re.compile(r"^(?P<base>[가-힣]+?)(?P<unit>[도시군구읍면동리가])$")
# '삼덕동1가', '동성로2가': the 동 (or road) name, then 'N-ga' ('Samdeok-dong 1-ga', 'Dongseong-ro 2-ga')
_GA_WORD = re.compile(r"^(?P<base>[가-힣]+?)(?P<unit>동|로)(?P<num>[0-9]+)가$")


def _boundary(f: int, i: int, v: int) -> tuple[str, str]:
    """Sound change between a final consonant f and the next initial i (next vowel v), as RR writes it.
    Nasalization, liquidization, liaison, palatalization and ㅎ-aspiration are written; tensing is not, and in
    nouns ㄱ·ㄷ·ㅂ + ㅎ stays k/t/p + h (묵호 Mukho)."""
    if f == 0:
        return "", _CHO[i]
    if i == 11:  # vowel next
        if v == 20 and f in (7, 25):  # 해돋이 haedoji, 같이 gachi
            return "", "j" if f == 7 else "ch"
        return _LIAISON[f]
    if f in (27, 6, 15) and i in (0, 3, 12):  # 좋고 joko
        return {27: "", 6: "n", 15: "l"}[f], {0: "k", 3: "t", 12: "ch"}[i]
    if f == 27 and i == 2:  # 놓는 nonneun
        return "n", "n"
    if f == 27 and i == 9:
        return "", "s"
    if i in (2, 6):  # ㄴ·ㅁ next: 백마 Baengma, 박물관 bangmulgwan, 십만 simman
        if f in _K:
            return "ng", _CHO[i]
        if f in _T:
            return "n", _CHO[i]
        if f in _P:
            return "m", _CHO[i]
        if i == 2 and f in _L:  # 칼날 kallal
            return "l", "l"
    if i == 5:  # ㄹ next: 신라 Silla, 종로 Jongno, 백리 baengni, 십리 simni
        if f == 4 or f in _L:
            return "l", "l"
        if f in (10, 16, 21):
            return _JONG[f], "n"
        if f in _K:
            return "ng", "n"
        if f in _P:
            return "m", "n"
        return "n", "n"
    return _JONG[f], _CHO[i]


def _rr_run(text: str) -> str:
    """One run of Hangul syllables (sound changes inside the run)."""
    syl = [divmod(ord(c) - 0xAC00, 28) for c in text]
    parts = [(cv // 21, cv % 21, jong) for cv, jong in syl]
    out = []
    carry = _CHO[parts[0][0]]
    for n, (cho, jung, jong) in enumerate(parts):
        nxt = parts[n + 1] if n + 1 < len(parts) else None
        if nxt:
            fin, carry_next = _boundary(jong, nxt[0], nxt[1])
        else:
            fin, carry_next = _JONG[jong], ""
        out.append(carry + _JUNG[jung] + fin)
        carry = carry_next
    return "".join(out)


def _syllables(word: str) -> bool:
    return bool(word) and all(0xAC00 <= ord(c) <= 0xD7A3 for c in word)


def _squash_ws(text: str | None) -> str:
    """pipeline.textutil.squash_ws, kept here so this module stays a leaf."""
    return re.sub(r"\s+", " ", text or "").strip()


def _runs(word: str) -> str:
    """A word without an administrative unit: each Hangul run romanized (capitalised after a non-alphanumeric),
    Latin letters, digits and symbols kept."""
    out, prev = [], ""
    for run in re.findall(r"[가-힣]+|[^가-힣]+", word):
        if _syllables(run):
            r = _rr_run(run)
            if not prev or not prev[-1].isalnum():
                r = r[:1].upper() + r[1:]
            out.append(r)
        else:
            out.append(run)
        prev = out[-1]
    return "".join(out)


def _unit_word(word: str) -> str:
    """An administrative name the caller named: 'Jung-gu', 'Gyeongam-dong', 'Samdeok-dong 1-ga'; a word that is
    not of that shape is romanized as any other word."""
    m = _GA_WORD.match(word)
    if m:
        unit = "dong" if m.group("unit") == "동" else "ro"
        return f"{_rr_cap(m.group('base'))}-{unit} {m.group('num')}-ga"
    m = _UNIT_WORD.match(word)
    if m:
        return f"{_rr_cap(m.group('base'))}-{_UNIT[m.group('unit')]}"
    return _runs(word)


def romanize(text: str | None, *, admin: str | frozenset = "heuristic") -> str:
    """Revised Romanization of a Korean name: each word capitalized, Latin letters and digits kept,
    administrative units hyphenated ('한빛동 철길마을' -> 'Hanbit-dong Cheolgilmaeul', '종로' -> 'Jongno').

    admin="heuristic" (the English pages): a Hangul word of three or more syllables ending in 동·읍·면 is taken as an
    administrative unit. A frozenset (slugs): only the whole words in it are, the guess is off ('다니면' Danimyeon)."""
    words = []
    for word in _squash_ws(re.sub(r"(?<=[^\s(\[])([(\[])(?=[^)\]]*[가-힣])", r" \1", text or "")).split(" "):
        if not word:
            continue
        if not isinstance(admin, str):
            words.append(_unit_word(word) if word in admin else _runs(word))
            continue
        if _syllables(word) and len(word) >= 3 and word[-1] in ("동", "읍", "면"):
            base = _rr_run(word[:-1])
            words.append(base[:1].upper() + base[1:] + "-" + _ADMIN[word[-1]])
            continue
        words.append(_runs(word))
    return " ".join(words)


def _rr_cap(text: str) -> str:
    r = _rr_run(text)
    return r[:1].upper() + r[1:]


def _admin(word: str) -> str:
    return f"{_rr_cap(word[:-1])}-{_ADMIN[word[-1]]}"
