"""The language versions besides Korean, as one table (English is one locale of it).

A version exists in a build only when data/<region>/<code> exists (pipeline/en_site.py). Everything that differs
by language and is not a translation of our data lives here: the route and data folder, <html lang> / hreflang,
og:locale, the version's site name and the city's name, the language menu label, dates, distances and decimals,
how money is written (the translation rules and checks of tools/en_content.py), sentence splitting, plural forms,
and the word lists and script checks the translation check (tools/en_content.py) and the page check
(pipeline/validate.py) share: promotional words, disclaimers, weekday and month names, Chinese script both ways
(OpenCC character tables), kana in Japanese prose, Cyrillic in Russian prose, the language of German, French and
Spanish prose (a small stopword test). Russian names: kontsevich() (Kontsevich system, Cyrillic).

The words the pages print (the UI text) are not here: English's are pipeline/intl_text.py, the other versions'
are translations of those in data/<region>/<code>/strings.json ('chrome.<key>', tools/en_content.py).
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import re
from dataclasses import dataclass, field

ORDER = ("en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")   # the language menu and hreflang order after ko
KO = {"code": "ko", "html": "ko", "label": "한국어", "home": "/"}
HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")
KANA = re.compile(r"[ぁ-ゖァ-ヺー]")
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
CYR = re.compile(r"[А-Яа-яЁё]")
LAT = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]")
NNBSP = "\u202f"   # narrow no-break space: French and Russian thousands


@dataclass(frozen=True)
class Locale:
    code: str            # route (/ja/), data folder (data/<region>/ja), --lang
    tag: str             # record field suffix (name_ja, strings.json {"ja": …})
    html: str            # <html lang>, hreflang, JSON-LD inLanguage
    og: str              # og:locale
    label: str           # the language menu label, in the language itself
    english: str         # the language's English name (translator rules)
    site_name: str
    city: str            # Gunsan in this language
    service: str         # TourAPI multilingual service (official names)
    cjk: bool = False
    dec: str = "."       # decimal mark
    grp: str = ","       # thousands separator
    title_max: int = 70  # <title> length (characters)
    desc_max: int = 160  # meta description length (characters)
    sent_max: int = 40   # a prose sentence: words (characters for CJK)
    plural: tuple = ("one", "other")
    weekdays: tuple = ()          # Monday … Sunday, the names a translation uses
    weekdays_short: tuple = ()    # in a date: (Mo.) (月) (周一)
    months: tuple = ()            # month names in a date (genitive for Russian)
    months_short: tuple = ()
    conflict: str = ""            # where two sources differ (places)
    event_conflict: str = ""      # the same for an event's values
    untranslated: str = ""        # the language menu's note on a link to a list (no translation of this page there)
    money_word: str = ""          # '3,000 <word>'
    promo: tuple = ()             # promotional words (CLAUDE.md 3.5: answer-first plain sentences)
    disclaimers: tuple = ()
    free: str = ""                # regex: the word for 무료
    colon: str = ": "
    list_sep: str = ", "
    sjoin: str = " "              # between sentences
    abbr: tuple = ()              # abbreviations a sentence never ends with
    # AI art (owner decisions 2026-10-13, CLAUDE.md 4; pipeline/art.py): the words an illustration's alt text starts
    # with, in the language ('일러스트: ' for Korean). No label on the picture since 2026-10-13 night.
    art_alt: str = ""
    units: tuple = ("m", "km")             # Locale.dist: metres, kilometres
    same_xy: str = "same coordinates"      # Locale.dist under 10 m (two places on the same stored coordinates)
    home_h1: str = ""                      # the home opening's H1: what the site is, in this language
                                           # (operator 2026-10-16: '군산 여행의 모든 것'); site_name stays Gunsangak
    extra: dict = field(default_factory=dict)

    @property
    def home(self) -> str:
        return f"/{self.code}/"

    @property
    def name_key(self) -> str:
        return f"name_{self.tag}"

    # ---- numbers, dates, distances
    def num(self, n: float, decimals: int = 0) -> str:
        s = f"{n:,.{decimals}f}"
        return s.translate(str.maketrans({",": "\x00", ".": "\x01"})).replace("\x00", self.grp).replace("\x01", self.dec)

    def money(self, won: int) -> str:
        """'3,000 won' as this language writes it (the spec's formats)."""
        n = self.num(won)
        if self.cjk:
            return f"{n}{self.money_word}"
        return f"{n} {self.money_word}"

    def dist(self, m) -> str:
        """'430 m' (rounded to 10 m), '2.4 km' / '2,4 km' / '2,4 км' (units: the language's), under 10 m the words for
        'same coordinates' (present.dist: '같은 좌표'); '' for unknown."""
        if m is None:
            return ""
        m = float(m)
        if m < 10:
            return self.same_xy
        mu, ku = self.units
        return f"{int(round(m / 10) * 10)} {mu}" if m < 1000 else f"{m / 1000:.1f}".replace(".", self.dec) + f" {ku}"

    def date(self, iso: str | None) -> str:
        """A full date with its weekday ('2026年10月13日（月）', '13. Oktober 2026 (Di.)'); English: 'October 9, 2026'."""
        try:
            d = dt.date.fromisoformat(str(iso or "")[:10])
        except ValueError:
            return re.sub(r"\s+", " ", str(iso or "")).strip()
        if self.code == "en":
            return f"{d.strftime('%B')} {d.day}, {d.year}"
        wd = self.weekdays_short[d.weekday()]
        mo = self.months[d.month - 1]
        return self.extra["date"].format(y=d.year, m=d.month, d=d.day, mo=mo, wd=wd)

    def date_bare(self, iso: str | None) -> str:
        """A date without its weekday (a founding date): date() without the bracketed weekday it ends with."""
        return re.sub(r"\s*[（(][^（()）]*[)）]$", "", self.date(iso))

    def md(self, iso: str | None) -> str:
        """A short month-day ('Oct 9', '10月9日', '9. Okt.')."""
        try:
            d = dt.date.fromisoformat(str(iso or "")[:10])
        except ValueError:
            return re.sub(r"\s+", " ", str(iso or "")).strip()
        if self.code == "en":
            return f"{d.strftime('%b')} {d.day}"
        return self.extra["md"].format(m=d.month, d=d.day, mo=self.months_short[d.month - 1])

    def mon(self, ym: str | None) -> str:
        """A month standing alone ('Oct', '10月', 'Okt.', 'окт.'): an end the source gives only as a month
        ('2026-10'), never turned into that month's last day (QA 2026-10-15 SRC-06)."""
        m = int(str(ym or "")[5:7])
        if self.code == "en":
            return dt.date(2000, m, 1).strftime("%b")
        return self.extra.get("mon_alone", self.months_short)[m - 1]

    # ---- plural forms (CLDR cardinal categories)
    def plural_form(self, n: int) -> str:
        if self.plural == ("other",):
            return "other"
        if self.plural == ("one", "few", "many"):
            if n % 10 == 1 and n % 100 != 11:
                return "one"
            if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
                return "few"
            return "many"
        if self.code == "fr":
            return "one" if n in (0, 1) else "other"
        return "one" if n == 1 else "other"

    # ---- sentences
    def sentences(self, text: str | None) -> list[str]:
        """Sentences of a prose text, each whole; joined with self.sjoin they are the text again."""
        t = re.sub(r"\s+", " ", str(text or "")).strip()
        if not t:
            return []
        if self.cjk:
            parts = re.split(r"(?<=[。！？])(?![」』）】〕”’。！？])\s*", t)
            return [p for p in parts if p]
        rx = re.compile(r"(?<=[.?!…])\s+(?=[\"'«„“¿¡(\[0-9A-ZÀ-ÖØ-ÞА-ЯЁ])")
        abbr = re.compile(rf"\b(?:{'|'.join(map(re.escape, self.abbr))})\.$") if self.abbr else None
        out: list[str] = []
        for part in rx.split(t):
            if out and ((abbr and abbr.search(out[-1]))   # 'Nr. 5', 'ул. Ленина'
                        or (self.code == "de" and re.search(r"(?:^|\s)\d{1,2}\.$", out[-1]))):   # '13. Oktober'
                out[-1] = f"{out[-1]} {part}"
            elif part:
                out.append(part)
        return out


_DE_WD = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
LOCALES: dict[str, Locale] = {
    "en": Locale("en", "en", "en", "en_US", "English", "English", "Gunsangak", "Gunsan", "EngService2",
                 weekdays=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
                 conflict="Sources differ — call before visiting",
                 event_conflict="Sources differ — check with the organizer before visiting", money_word="won",
                 untranslated="not translated",
                 abbr=("No", "Dr", "Mt", "St", "Mr", "Ms", "Jr", "vs", "approx", "Ave"),
                 home_h1="All About Gunsan Travel", art_alt="Illustration: "),
    "ja": Locale("ja", "ja", "ja", "ja_JP", "日本語", "Japanese", "Gunsangak", "群山", "JpnService2", cjk=True,
                 title_max=40, desc_max=110, sent_max=80, plural=("other",),
                 weekdays=("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
                 weekdays_short=("月", "火", "水", "木", "金", "土", "日"),
                 months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                 conflict="情報源によって値が異なります。訪問前に電話でご確認ください",
                 event_conflict="情報源によって値が異なります。訪問前に電話でご確認ください", money_word="ウォン",
                 untranslated="未翻訳",
                 promo=("必見", "絶対", "最高", "人気", "有名", "おすすめ", "オススメ", "お勧め", "お薦め", "話題"),
                 disclaimers=("参考程度", "変更される場合があります", "変更になる場合があります", "責任を負いかねます", "免責"),
                 free="無料", colon="：", list_sep="、", sjoin="",
                 home_h1="群山旅行のすべて", art_alt="イラスト：", same_xy="同じ座標",
                 extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "言語"}),
    "zh-hans": Locale("zh-hans", "zh_hans", "zh-Hans", "zh_CN", "中文(简体)", "Simplified Chinese", "Gunsangak",
                      "群山", "ChsService2", cjk=True, title_max=40, desc_max=110, sent_max=70, plural=("other",),
                      weekdays=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                      weekdays_short=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                      months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                      conflict="不同来源的信息不一致，请出发前致电确认",
                      event_conflict="不同来源的信息不一致，请出发前致电确认", money_word="韩元",
                      untranslated="未翻译",
                      promo=("必去", "必游", "最好", "最佳", "著名", "热门", "网红", "推荐", "人气"),
                      disclaimers=("仅供参考", "如有变动", "以实际为准", "概不负责", "免责声明"),
                      free="免费", colon="：", list_sep="、", sjoin="",
                      home_h1="群山旅游全攻略", art_alt="插图：", same_xy="相同坐标",
                      extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "语言"}),
    "zh-hant": Locale("zh-hant", "zh_hant", "zh-Hant", "zh_TW", "中文(繁體)", "Traditional Chinese", "Gunsangak",
                      "群山", "ChtService2", cjk=True, title_max=40, desc_max=110, sent_max=70, plural=("other",),
                      weekdays=("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                      weekdays_short=("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                      months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                      conflict="不同來源的資訊不一致，請出發前致電確認",
                      event_conflict="不同來源的資訊不一致，請出發前致電確認", money_word="韓元",
                      untranslated="未翻譯",
                      promo=("必去", "必遊", "最好", "最佳", "著名", "熱門", "網紅", "推薦", "人氣"),
                      disclaimers=("僅供參考", "如有變動", "以實際為準", "概不負責", "免責聲明"),
                      free="免費", colon="：", list_sep="、", sjoin="",
                      home_h1="群山旅遊全攻略", art_alt="插圖：", same_xy="相同座標",
                      extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "語言"}),
    "de": Locale("de", "de", "de", "de_DE", "Deutsch", "German", "Gunsangak", "Gunsan", "GerService2",
                 dec=",", grp=".", weekdays=_DE_WD, weekdays_short=("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."),
                 months=("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
                         "November", "Dezember"),
                 months_short=("Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.",
                               "Dez."),
                 conflict="Die Quellen nennen unterschiedliche Angaben – bitte vor dem Besuch anrufen.",
                 event_conflict="Die Quellen nennen unterschiedliche Angaben – bitte vor dem Besuch anrufen.",
                 untranslated="nicht übersetzt",
                 money_word="Won", promo=("unbedingt", "Geheimtipp", "berühmt", "beliebt", "beste", "Muss"),
                 disclaimers=("ohne Gewähr", "Änderungen vorbehalten", "keine Haftung", "Haftungsausschluss",
                              "unverbindlich"),
                 free=r"kostenlos|gratis|Eintritt frei|eintrittsfrei|frei(?:er)? Eintritt|gebührenfrei",
                 abbr=("Nr", "z", "B", "ca", "bzw", "Str", "St", "Dr", "usw", "inkl", "evtl", "u", "a", "Tel"),
                 home_h1="Alles über Gunsan", art_alt="Illustration: ", same_xy="gleiche Koordinaten",
                 extra={"date": "{d}. {mo} {y} ({wd})", "md": "{d}. {mo}", "lang_word": "Sprache"}),
    "fr": Locale("fr", "fr", "fr", "fr_FR", "Français", "French", "Gunsangak", "Gunsan", "FreService2",
                 dec=",", grp=NNBSP,
                 weekdays=("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
                 weekdays_short=("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
                 months=("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                         "octobre", "novembre", "décembre"),
                 months_short=("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
                               "nov.", "déc."),
                 conflict="Les sources indiquent des valeurs différentes : appelez avant votre visite.",
                 event_conflict="Les sources indiquent des valeurs différentes : appelez avant votre visite.",
                 untranslated="non traduit",
                 money_word="wons", promo=("incontournable", "célèbre", "populaire", "meilleur", "à ne pas manquer"),
                 disclaimers=("sous réserve", "à titre indicatif", "susceptible de changer",
                              "décline toute responsabilité", "avertissement"),
                 free=r"gratuit(?:e|s|es)?|entrée libre", colon=" : ",
                 abbr=("M", "Mme", "St", "Ste", "av", "bd", "env", "n°", "tél", "p. ex"),
                 home_h1="Tout sur Gunsan", art_alt="Illustration : ", same_xy="mêmes coordonnées",
                 extra={"date": "{d} {mo} {y} ({wd})", "md": "{d} {mo}", "lang_word": "Langue"}),
    "es": Locale("es", "es", "es", "es_ES", "Español", "Spanish", "Gunsangak", "Gunsan", "SpnService2",
                 dec=",", grp=".",
                 weekdays=("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
                 weekdays_short=("lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."),
                 months=("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                         "octubre", "noviembre", "diciembre"),
                 months_short=("ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.",
                               "nov.", "dic."),
                 conflict="Las fuentes indican datos distintos: llame antes de su visita.",
                 event_conflict="Las fuentes indican datos distintos: llame antes de su visita.",
                 untranslated="sin traducir",
                 money_word="wones", promo=("imprescindible", "famoso", "popular", "mejor", "no te puedes perder"),
                 disclaimers=("sujeto a cambios", "a título informativo", "no nos hacemos responsables",
                              "descargo de responsabilidad"),
                 free=r"gratis|gratuit[oa]s?|entrada libre",
                 abbr=("Sr", "Sra", "Dr", "Dra", "av", "Avda", "núm", "aprox", "tel", "p. ej"),
                 home_h1="Todo sobre Gunsan", art_alt="Ilustración: ", same_xy="mismas coordenadas",
                 extra={"date": "{d} de {mo} de {y} ({wd})", "md": "{d} {mo}", "lang_word": "Idioma"}),
    "ru": Locale("ru", "ru", "ru", "ru_RU", "Русский", "Russian", "Gunsangak", "Кунсан", "RusService2",
                 dec=",", grp=NNBSP, plural=("one", "few", "many"),
                 weekdays=("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
                 weekdays_short=("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
                 months=("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
                         "октября", "ноября", "декабря"),
                 months_short=("янв.", "февр.", "марта", "апр.", "мая", "июня", "июля", "авг.", "сент.", "окт.",
                               "нояб.", "дек."),
                 conflict="Источники расходятся — позвоните перед визитом.",
                 event_conflict="Источники расходятся — позвоните перед визитом.",
                 untranslated="нет перевода",
                 money_word="вон", promo=("обязательно", "знаменитый", "популярный", "лучший"),
                 disclaimers=("может измениться", "носит справочный характер", "не несём ответственности",
                              "не несем ответственности", "отказ от ответственности"),
                 free=r"бесплатн\w*",
                 abbr=("г", "ул", "д", "т", "е", "др", "им", "ок", "мин", "пр", "просп", "тел", "руб"),
                 home_h1="Всё о Кунсане", art_alt="Иллюстрация: ", units=("м", "км"),
                 same_xy="те же координаты",
                 extra={"date": "{d} {mo} {y} г. ({wd})", "md": "{d} {mo}", "lang_word": "Язык",
                        # a month standing alone is nominative (months_short holds the genitive марта, мая, июня, июля)
                        "mon_alone": ("янв.", "февр.", "март", "апр.", "май", "июнь", "июль", "авг.", "сент.", "окт.",
                                      "нояб.", "дек.")}),
}
CODES = tuple(LOCALES)


def get(code: str) -> Locale:
    return LOCALES[code.lower()]


def by_html(html: str) -> Locale | None:
    return next((loc for loc in LOCALES.values() if loc.html == html), None)


def code_of_path(path: str) -> str:
    """'/ja/places/x/' -> 'ja'; a Korean path -> 'ko'."""
    first = path.replace("\\", "/").strip("/").split("/", 1)[0].lower()
    return first if first in LOCALES else "ko"


# ------------------------------------------------------------------ promotional words and disclaimers
def _word_rx(words: tuple, cjk: bool, code: str) -> re.Pattern | None:
    if not words:
        return None
    if cjk:
        return re.compile("|".join(map(re.escape, words)))
    stems = {   # inflected forms of the spec's words
        "de": {"beste": r"beste[nmrs]?", "beliebt": r"beliebte?[nmrs]?", "berühmt": r"berühmte?[nmrs]?",
               "Geheimtipp": r"Geheimtipps?", "Muss": r"(?-i:Muss)"},
        "fr": {"incontournable": r"incontournables?", "célèbre": r"célèbres?", "populaire": r"populaires?",
               "meilleur": r"meilleure?s?"},
        "es": {"famoso": r"famos[oa]s?", "popular": r"populares|popular", "mejor": r"mejores|mejor",
               "imprescindible": r"imprescindibles?"},
        "ru": {"обязательно": r"обязательн\w*", "знаменитый": r"знаменит\w*", "популярный": r"популярн\w*",
               "лучший": r"лучш\w*"},
    }.get(code, {})
    alts = [stems.get(w, re.escape(w)) for w in words]
    return re.compile(rf"(?<![\w-])(?:{'|'.join(alts)})(?![\w-])", re.I)


@functools.lru_cache(maxsize=None)
def promo_rx(code: str):
    loc = get(code)
    return _word_rx(loc.promo, loc.cjk, code)


@functools.lru_cache(maxsize=None)
def disclaimer_rx(code: str):
    loc = get(code)
    return _word_rx(loc.disclaimers, loc.cjk, code)


# ------------------------------------------------------------------ Chinese script (OpenCC character tables)
@functools.lru_cache(maxsize=None)
def _opencc_tables() -> tuple[dict, dict, set]:
    """(simplified -> [traditional …], traditional -> [simplified …], characters Taiwan/Hong Kong standards use)."""
    import opencc   # opencc-python-reimplemented (requirements.txt)
    base = os.path.join(os.path.dirname(opencc.__file__), "dictionary")

    def load(name: str) -> dict:
        out = {}
        with open(os.path.join(base, name), encoding="utf-8") as f:
            for line in f:
                k, _, v = line.rstrip("\n").partition("\t")
                if k:
                    out[k] = v.split(" ")
        return out
    st, ts = load("STCharacters.txt"), load("TSCharacters.txt")
    variants = {c for name in ("TWVariants.txt", "HKVariants.txt") for vals in load(name).values() for c in vals}
    return st, ts, variants


def traditional_only(text: str) -> list[str]:
    """Characters of `text` that Simplified Chinese does not use (OpenCC: a traditional form whose simplified form
    differs and that is not itself a simplified character)."""
    _, ts, _ = _opencc_tables()
    return list(dict.fromkeys(c for c in text if c in ts and c not in ts[c]))


def simplified_only(text: str) -> list[str]:
    """Characters of `text` that Traditional Chinese (Taiwan / Hong Kong standards) does not use."""
    st, _, variants = _opencc_tables()
    return list(dict.fromkeys(c for c in text if c in st and c not in st[c] and c not in variants))


# ------------------------------------------------------------------ the language of a text
STOPWORDS = {
    "en": {"the", "and", "of", "to", "is", "are", "was", "with", "for", "on", "at", "from", "this", "that", "it", "its",
           "by", "or", "you", "your", "there", "which", "be", "has", "have", "can", "an"},
    "de": {"der", "die", "das", "und", "ist", "sind", "mit", "für", "von", "zu", "im", "den", "dem", "des", "ein",
           "eine", "einen", "auf", "nicht", "sie", "wird", "werden", "bei", "auch", "als", "nach", "aus", "am", "vom",
           "zum", "zur", "über", "oder", "kann", "gibt"},
    "fr": {"le", "les", "et", "est", "sont", "des", "du", "une", "pour", "dans", "sur", "avec", "au", "aux", "par",
           "qui", "il", "elle", "ne", "pas", "ce", "cette", "ou", "vous", "peut", "être"},
    "es": {"el", "los", "las", "y", "son", "del", "una", "para", "con", "por", "al", "lo", "su", "sus", "está",
           "están", "pero", "hay", "puede", "también", "muy", "como",
           # 2026-10-14: words only Spanish writes among these four languages — without them a plain Spanish sentence
           # ('Huirak es un restaurante de sopas cuya especialidad es la sopa de pescado') had no stopword at all, since
           # de/la/en/un are French too; English or German left in Spanish is caught exactly as before
           "es", "qué", "sí", "cuya", "cuyo", "tiene", "tienen", "hasta", "desde"},
}
_SHARED = {w for a in STOPWORDS for b in STOPWORDS if a < b for w in STOPWORDS[a] & STOPWORDS[b]}
_STOP = {k: v - _SHARED for k, v in STOPWORDS.items()}


def _stop_counts(text: str) -> dict[str, int]:
    words = re.findall(r"[^\W\d_]+", text.lower())
    return {k: sum(1 for w in words if w in s) for k, s in _STOP.items()}


def script_problems(text: str, code: str, prose: bool = True) -> list[str]:
    """What is wrong with the script or language of a translated text (English: nothing here — tools/en_content.py
    style() has its own checks). prose: a sentence or more (the kana, Cyrillic and stopword tests need words)."""
    loc = get(code)
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t or code == "en":
        return []
    out: list[str] = []
    if code in ("zh-hans", "zh-hant", "ja"):
        if CYR.search(t):
            out.append(f"Cyrillic in {loc.english}")
    else:
        hits = "".join(dict.fromkeys(CJK.findall(t) + KANA.findall(t)))
        if hits:
            out.append(f"Chinese or Japanese characters in {loc.english}: {hits[:10]}")
    if code == "zh-hans":
        bad = traditional_only(t)
        if bad:
            out.append(f"Traditional characters in Simplified Chinese: {''.join(bad[:10])}")
    if code == "zh-hant":
        bad = simplified_only(t)
        if bad:
            out.append(f"Simplified characters in Traditional Chinese: {''.join(bad[:10])}")
    if code in ("zh-hans", "zh-hant") and KANA.search(t):
        out.append(f"Japanese kana in {loc.english}: {''.join(dict.fromkeys(KANA.findall(t)))[:10]}")
    if not prose:   # a label or a value (romanized addresses and names are Latin in every language)
        return out
    if code == "ja":
        for s in loc.sentences(t):
            if len(CJK.findall(s)) >= 8 and not KANA.search(s):
                out.append(f"Chinese text in Japanese (no kana): '{s[:30]}'")
                break
        for s in loc.sentences(t):
            words = re.findall(r"[A-Za-z]{2,}", s)
            if len(words) >= 4 and not KANA.search(s) and not CJK.search(s):
                out.append(f"English left in Japanese: '{s[:40]}'")
                break
    elif code in ("zh-hans", "zh-hant"):
        for s in loc.sentences(t):
            words = re.findall(r"[A-Za-z]{2,}", s)
            if len(words) >= 4 and not CJK.search(s):
                out.append(f"English left in {loc.english}: '{s[:40]}'")
                break
    elif code == "ru":
        lat, cyr = len(re.findall(r"[A-Za-z]", t)), len(CYR.findall(t))
        en = _stop_counts(t)["en"]
        if (lat + cyr >= 20 and lat > 0.3 * (lat + cyr)) or en >= 2:
            out.append(f"Latin text in Russian: '{t[:40]}'")
    else:   # de, fr, es: the prose is in the language (a small stopword test)
        words = re.findall(r"[^\W\d_]+", t)
        counts = _stop_counts(t)
        own = counts[code]
        other = max((k for k in counts if k != code), key=lambda k: counts[k])
        if (counts[other] >= 2 and counts[other] > own) or (len(words) >= 12 and own == 0):
            name = {"en": "English", "de": "German", "fr": "French", "es": "Spanish"}[other]
            out.append(f"{name} left in {loc.english} (stopwords {other} {counts[other]} vs {code} {own}): '{t[:40]}'")
    return out


# ------------------------------------------------------------------ Russian: Kontsevich transcription of Korean
# choseong 0..18: ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ — word-initial / after an obstruent (voiceless) and
# after a vowel or a sonorant (voiced)
_K_INIT = ("к", "кк", "н", "т", "тт", "р", "м", "п", "пп", "с", "сс", "", "ч", "чч", "чх", "кх", "тх", "пх", "х")
_K_MED = ("г", "кк", "н", "д", "тт", "р", "м", "б", "пп", "с", "сс", "", "дж", "чч", "чх", "кх", "тх", "пх", "х")
# jungseong 0..20: ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ
_K_VOW = ("а", "э", "я", "йе", "о", "е", "ё", "йе", "о", "ва", "вэ", "ве", "ё", "у", "во", "ве", "ви", "ю", "ы",
          "ый", "и")
# jongseong 1..27 by how they sound before a consonant or at the end
_K_K, _K_T, _K_P = {1, 2, 3, 9, 24}, {7, 19, 20, 22, 23, 25, 27}, {14, 17, 18, 26}
_K_L = {8, 11, 12, 13, 15}
_K_FIN = {**{f: "к" for f in _K_K}, **{f: "т" for f in _K_T}, **{f: "п" for f in _K_P}, **{f: "ль" for f in _K_L},
          4: "н", 5: "н", 6: "н", 10: "м", 16: "м", 21: "н", 0: ""}
_K_SONORANT = {0, 4, 5, 6, 8, 10, 11, 12, 13, 15, 16, 21}
# a final before a vowel (liaison): (kept in this syllable, carried to the next)
_K_LIAISON = {1: ("", "г"), 2: ("", "кк"), 3: ("к", "с"), 4: ("", "н"), 5: ("н", "дж"), 6: ("", "н"), 7: ("", "д"),
              8: ("", "р"), 9: ("ль", "г"), 10: ("ль", "м"), 11: ("ль", "б"), 12: ("ль", "с"), 13: ("ль", "тх"),
              14: ("ль", "пх"), 15: ("", "р"), 16: ("", "м"), 17: ("", "б"), 18: ("п", "с"), 19: ("", "с"),
              20: ("", "сс"), 21: ("нъ", ""), 22: ("", "дж"), 23: ("", "чх"), 24: ("", "кх"), 25: ("", "тх"),
              26: ("", "пх"), 27: ("", "")}
_K_ADMIN = {"동": "дон", "읍": "ып", "면": "мён", "리": "ри"}


def _k_boundary(f: int, i: int, v: int) -> tuple[str, str]:
    """(this syllable's final, the next syllable's initial) for final f, next initial i and next vowel v —
    liaison, nasalization, ㄹ assimilation and ㅎ aspiration, as Kontsevich writes the pronunciation."""
    if f == 0:
        return "", _K_MED[i]
    if i == 11:   # a vowel next
        if v == 20 and f in (7, 25):   # 해돋이 Хэдоджи, 같이 качхи
            return "", "дж" if f == 7 else "чх"
        return _K_LIAISON[f]
    if i == 18:   # ㅎ next: aspiration
        if f in _K_K:
            return "", "кх"
        if f in _K_T:
            return "", "тх" if f != 22 else "чх"
        if f in _K_P:
            return "", "пх"
        return _K_FIN[f], "х"
    if f in (27, 6, 15) and i in (0, 3, 12):   # 좋고 чокхо
        return {27: "", 6: "н", 15: "ль"}[f], {0: "кх", 3: "тх", 12: "чх"}[i]
    if i in (2, 6):   # ㄴ ㅁ next: 백마 Пэнма, 십만 симман
        if f in _K_K:
            return "н", _K_INIT[i]
        if f in _K_T:
            return "н", _K_INIT[i]
        if f in _K_P:
            return "м", _K_INIT[i]
        if i == 2 and f in _K_L:   # 칼날 каллаль
            return "л", "л"
    if i == 5:   # ㄹ next: 신라 Силла, 종로 Чонно, 백리 пэнни
        if f in (4, 5) or f in _K_L:
            return "л", "л"
        if f in (10, 16, 21):
            return _K_FIN[f], "н"
        if f in _K_K or f in _K_T:
            return "н", "н"
        if f in _K_P:
            return "м", "н"
    return _K_FIN[f], (_K_MED[i] if f in _K_SONORANT else _K_INIT[i])


def _k_run(text: str) -> str:
    """One run of Hangul syllables in Cyrillic (lowercase), sound changes inside the run."""
    parts = [((ord(c) - 0xAC00) // 588, (ord(c) - 0xAC00) // 28 % 21, (ord(c) - 0xAC00) % 28) for c in text]
    out, carry = [], None
    for n, (cho, jung, jong) in enumerate(parts):
        init = _K_INIT[cho] if carry is None else carry
        if n == 0 and cho == 11:
            vow = {5: "э", 3: "йе", 7: "йе"}.get(jung, _K_VOW[jung])
        elif cho != 11 and jung in (3, 7):   # ㅒ ㅖ after a consonant
            vow = "е"
        else:
            vow = _K_VOW[jung]
        nxt = parts[n + 1] if n + 1 < len(parts) else None
        if nxt:
            fin, carry = _k_boundary(jong, nxt[0], nxt[1])
        else:
            fin, carry = _K_FIN[jong], None
        out.append(init + vow + fin)
    return "".join(out)


def kontsevich(text: str | None) -> str:
    """Cyrillic for a Korean name by the Kontsevich system ('군산' -> 'Кунсан', '경암동' -> 'Кёнам-дон'): each
    word capitalized, Latin letters and digits kept, administrative units hyphenated."""
    words = []
    for word in re.sub(r"\s+", " ", str(text or "")).strip().split(" "):
        if not word:
            continue
        if len(word) >= 3 and all(0xAC00 <= ord(c) <= 0xD7A3 for c in word) and word[-1] in "동읍면":
            base = _k_run(word[:-1])
            words.append(base[:1].upper() + base[1:] + "-" + _K_ADMIN[word[-1]])
            continue
        out, prev = [], ""
        for run in re.findall(r"[가-힣]+|[^가-힣]+", word):
            if all(0xAC00 <= ord(c) <= 0xD7A3 for c in run):
                r = _k_run(run)
                if not prev or not prev[-1].isalnum():
                    r = r[:1].upper() + r[1:]
                out.append(r)
            else:
                out.append(run)
            prev = out[-1]
        words.append("".join(out))
    return " ".join(words)


def area_name(area: str | None, code: str) -> str:
    """An administrative area ('장미동') in a language without a written form of its own in our data: Revised
    Romanization for every language but Russian ('Jangmi-dong'), Kontsevich Cyrillic for Russian ('Чанми-дон')."""
    from .en_source import _admin, romanize
    a = re.sub(r"\s+", " ", str(area or "")).strip()
    if not a:
        return ""
    if code == "ru":
        if re.fullmatch(r"[가-힣]{2,}", a) and a[-1] in "동읍면리":
            base = _k_run(a[:-1])
            return f"{base[:1].upper()}{base[1:]}-{_K_ADMIN[a[-1]]}"
        return kontsevich(a)
    if re.fullmatch(r"[가-힣]{2,}", a) and a[-1] in "동읍면리":
        return _admin(a)
    return romanize(a)


# the map's keyboard line (map.js: the map box's accessible name '… · <keys>' — the map takes the focus, the arrow keys
# move it, + and − zoom): English and Korean are in map.js itself; the other versions pass theirs in data-words.keys
# (post-launch review 2026-10-14: the Japanese maps had none)
MAP_KEYS = {
    "ja": "矢印キーで移動、+ と − キーで拡大・縮小",
    "zh-hans": "方向键移动，+ − 键放大缩小",
    "zh-hant": "方向鍵移動，+ − 鍵放大縮小",
    "de": "Pfeiltasten verschieben, + und − zoomen",
    "fr": "flèches pour déplacer, + et − pour zoomer",
    "es": "flechas para moverse, + y − para acercar o alejar",
    "ru": "стрелки — сдвиг, + и − — масштаб",
}



# the site search of the other language versions (owner 2026-10-14: '이 언어들도 다 검색이 되는 거지?'): the bar's field,
# the search page (<home>search/) and the words assets/search.js prints there (data-words). {r} the city, {q} the query.
# Nothing found (QA 2026-10-15 F08): none (one line), sug before the names it may have meant, diet for a food-rule
# word (the site has no such data: it says so and names no place), ask / all ({n} places) / browse in the help below.
# Evaluation 2026-10-18: scope — the line under the box (what the search finds; travel questions go to the AI chat,
# named as on the chat's launcher, templates/_chat.html.j2); related — the heading of the guides that match a part of
# a query nothing matches whole; syn — before the words a query word was also searched as (present.SEARCH_CONCEPTS).
SEARCH_WORDS = {
    "en": {"bar": "Search places, dishes, areas", "go": "Search", "close": "Close search", "open": "Search",
           "label": "Place name, dish, area, course, guide or event", "ph": "Name, dish or area",
           "h1": "Search {r}", "title": "Search {r}: places, dishes, areas and courses",
           "desc": "Find {r}'s places by name, signature dish or area, and its courses, guides and events by name.",
           "none": "Nothing matches ‘{q}’.", "dir": "Every place", "jump": "Jump to",
           "menu": "Dish: ", "other": "Also: ", "via": "Stops: ", "des": "Listed: ", "of": "{n} of {m}",
           "sug": "Did you mean: ", "ask": "Ask the AI chat",
           "all": "Show every place ({n})", "browse": "Browse the lists",
           "scope": "Finds places by name, dish or area, and guides; ask the AI chat your travel questions.",
           "related": "Related guides", "syn": "Also searched: ",
           "diet": "This site has no halal, vegetarian, vegan or allergy information on its restaurants. Ask the"
                   " restaurant before you go; when the site has its phone number, it is on the restaurant's page."},
    "ja": {"bar": "場所・料理・地域を検索", "go": "検索", "close": "検索を閉じる", "open": "検索",
           "label": "場所の名前、料理、地域、コース・ガイド・イベントの名前", "ph": "名前・料理・地域",
           "h1": "{r}を検索", "title": "{r}を検索：場所・料理・地域・コース",
           "desc": "{r}の場所を名前・看板料理・地域で、コース・ガイド・イベントを名前で探せます。",
           "none": "「{q}」に合う結果はありません。", "dir": "すべての場所", "jump": "移動",
           "menu": "料理：", "other": "別名：", "via": "経由：", "des": "指定：", "of": "{m}件中{n}件",
           "sug": "もしかして：", "ask": "AIチャットに聞く",
           "all": "すべての場所を表示（{n}か所）", "browse": "一覧から探す",
           "scope": "場所の名前・料理・地域・ガイドを探せます。旅行の質問はAIチャットへどうぞ。",
           "related": "関連ガイド", "syn": "あわせて検索：",
           "diet": "このサイトには飲食店のハラール・ベジタリアン・ヴィーガン・アレルギーの情報がありません。"
                   "訪れる前にお店に直接確認してください。電話番号がわかる場合は、そのお店のページに載っています。"},
    "zh-hans": {"bar": "搜索地点、菜品、地区", "go": "搜索", "close": "关闭搜索", "open": "搜索",
                "label": "地点名称、菜品、地区，或路线、指南、活动名称", "ph": "名称、菜品或地区",
                "h1": "在{r}搜索", "title": "在{r}搜索：地点、菜品、地区与路线",
                "desc": "按名称、招牌菜或地区查找{r}的地点，按名称查找路线、指南和活动。",
                "none": "没有与“{q}”相符的结果。", "dir": "全部地点", "jump": "跳转",
                "menu": "菜品：", "other": "别名：", "via": "途经：", "des": "认定：", "of": "{m}条中的{n}条",
                "sug": "您是不是要找：", "ask": "询问AI助手",
                "all": "显示全部地点（{n}个）", "browse": "按列表查找",
                "scope": "按名称、菜品、地区查找地点和指南；旅行问题请问AI助手。",
                "related": "相关指南", "syn": "同时搜索：",
                "diet": "本网站没有餐厅的清真、素食或过敏原信息。前往前请直接向餐厅确认；本网站有餐厅电话时，可在该餐厅的页面上找到。"},
    "zh-hant": {"bar": "搜尋地點、菜色、地區", "go": "搜尋", "close": "關閉搜尋", "open": "搜尋",
                "label": "地點名稱、菜色、地區，或路線、指南、活動名稱", "ph": "名稱、菜色或地區",
                "h1": "在{r}搜尋", "title": "在{r}搜尋：地點、菜色、地區與路線",
                "desc": "依名稱、招牌菜或地區查找{r}的地點，依名稱查找路線、指南和活動。",
                "none": "沒有與「{q}」相符的結果。", "dir": "全部地點", "jump": "跳至",
                "menu": "菜色：", "other": "別名：", "via": "途經：", "des": "認定：", "of": "{m}筆中的{n}筆",
                "sug": "您是不是要找：", "ask": "詢問AI助手",
                "all": "顯示全部地點（{n}處）", "browse": "依列表查找",
                "scope": "依名稱、菜色、地區查找地點和指南；旅行問題請問AI助手。",
                "related": "相關指南", "syn": "同時搜尋：",
                "diet": "本網站沒有餐廳的清真、素食或過敏原資訊。前往前請直接向餐廳確認；本網站有餐廳電話時，可在該餐廳的頁面上找到。"},
    "de": {"bar": "Orte, Gerichte, Viertel suchen", "go": "Suchen", "close": "Suche schließen", "open": "Suche",
           "label": "Ortsname, Gericht, Viertel, Route, Ratgeber oder Veranstaltung", "ph": "Name, Gericht oder Viertel",
           "h1": "{r} durchsuchen", "title": "{r} durchsuchen: Orte, Gerichte, Viertel und Routen",
           "desc": "Orte in {r} nach Name, Hauptgericht oder Viertel finden, Routen, Ratgeber und Veranstaltungen nach Namen.",
           "none": "Nichts passt zu „{q}“.", "dir": "Alle Orte", "jump": "Springen zu",
           "menu": "Gericht: ", "other": "Auch: ", "via": "Stationen: ", "des": "Ausgezeichnet: ", "of": "{n} von {m}",
           "sug": "Meinten Sie: ", "ask": "Den KI-Chat fragen",
           "all": "Alle Orte zeigen ({n})", "browse": "In den Listen suchen",
           "scope": "Findet Orte nach Name, Gericht oder Viertel und Ratgeber; Reisefragen beantwortet der KI-Chat.",
           "related": "Passende Ratgeber", "syn": "Auch gesucht: ",
           "diet": "Diese Website hat zu ihren Restaurants keine Angaben zu halal, vegetarisch, vegan oder Allergenen."
                   " Fragen Sie vor dem Besuch im Restaurant nach; hat die Website seine Telefonnummer, steht sie"
                   " auf der Seite des Restaurants."},
    "fr": {"bar": "Rechercher lieux, plats, quartiers", "go": "Rechercher", "close": "Fermer la recherche",
           "open": "Recherche", "label": "Nom de lieu, plat, quartier, itinéraire, guide ou événement",
           "ph": "Nom, plat ou quartier", "h1": "Rechercher à {r}",
           "title": "Rechercher à {r} : lieux, plats, quartiers et itinéraires",
           "desc": "Trouvez les lieux de {r} par nom, plat phare ou quartier, et les itinéraires, guides et événements par nom.",
           "none": "Aucun résultat pour « {q} ».", "dir": "Tous les lieux",
           "jump": "Aller à", "menu": "Plat : ", "other": "Aussi : ", "via": "Étapes : ",
           "des": "Labellisé : ", "of": "{n} sur {m}",
           "sug": "Vouliez-vous dire : ", "ask": "Demander au chat IA",
           "all": "Afficher tous les lieux ({n})", "browse": "Parcourir les listes",
           "scope": "Trouve les lieux par nom, plat ou quartier, et les guides ; posez vos questions de voyage"
                    " au chat IA.",
           "related": "Guides liés", "syn": "Recherché aussi : ",
           "diet": "Ce site n’a aucune information halal, végétarienne, végane ou sur les allergènes pour ses restaurants."
                   " Renseignez-vous auprès du restaurant avant d’y aller ; quand le site a son numéro de téléphone,"
                   " il figure sur la page du restaurant."},
    "es": {"bar": "Buscar lugares, platos, barrios", "go": "Buscar", "close": "Cerrar la búsqueda", "open": "Buscar",
           "label": "Nombre del lugar, plato, barrio, ruta, guía o evento", "ph": "Nombre, plato o barrio",
           "h1": "Buscar en {r}", "title": "Buscar en {r}: lugares, platos, barrios y rutas",
           "desc": "Encuentre los lugares de {r} por nombre, plato estrella o barrio, y las rutas, guías y eventos por nombre.",
           "none": "No hay resultados para «{q}».", "dir": "Todos los lugares",
           "jump": "Ir a", "menu": "Plato: ", "other": "También: ", "via": "Paradas: ", "des": "Distinción: ",
           "of": "{n} de {m}",
           "sug": "Quizá quiso decir: ", "ask": "Preguntar al chat IA",
           "all": "Ver todos los lugares ({n})", "browse": "Buscar en las listas",
           "scope": "Busca lugares por nombre, plato o barrio, y guías; haga sus preguntas de viaje al chat IA.",
           "related": "Guías relacionadas", "syn": "También se buscó: ",
           "diet": "Este sitio no tiene información halal, vegetariana, vegana ni sobre alérgenos de sus restaurantes."
                   " Consulte al restaurante antes de ir; cuando el sitio tiene su teléfono, figura en la página"
                   " del restaurante."},
    "ru": {"bar": "Поиск мест, блюд, районов", "go": "Найти", "close": "Закрыть поиск", "open": "Поиск",
           "label": "Название места, блюдо, район, маршрут, путеводитель или событие", "ph": "Название, блюдо или район",
           "h1": "Поиск: {r}", "title": "Поиск: {r} — места, блюда, районы и маршруты",
           "desc": "Ищите места в городе {r} по названию, фирменному блюду или району, а маршруты, путеводители и события — по названию.",
           "none": "По запросу «{q}» ничего не найдено.", "dir": "Все места",
           "jump": "Перейти к", "menu": "Блюдо: ", "other": "Также: ", "via": "Остановки: ", "des": "Статус: ",
           "of": "{n} из {m}",
           "sug": "Возможно, вы искали: ", "ask": "Спросить ИИ-чат",
           "all": "Показать все места ({n})", "browse": "Искать по спискам",
           "scope": "Ищет места по названию, блюду или району, а также путеводители; вопросы о поездке"
                    " задайте ИИ-чату.",
           "related": "Связанные путеводители", "syn": "Также искали: ",
           "diet": "На этом сайте нет сведений о халяльной, вегетарианской или веганской еде и об аллергенах в"
                   " ресторанах. Уточните в ресторане перед визитом; если на сайте есть его телефон, он указан"
                   " на странице ресторана."},
}


# the place page's '주변·함께 가기' chapter (owner 2026-10-14: 시각화·모션; templates/_near.html.j2): the words of the course
# segments, the nearby rows, the guide and event cards, for Korean and every version. The headings keep their words
# (Korean literals; the versions' chrome strings courses_here, near_sights, near_biz, guides_here, events_here), so a
# version never drops out of the build for a missing string. Counts sit in parentheses: no plural forms. Distances are
# straight lines between coordinates and say so in every language ({d}: present.dist / Locale.dist).
# part_of / same_building: the line under a place's name that names the place it is inside / the other page for the
# same building ({name}: that place's name in this version, a link where it has a page here); parts: the heading of
# the list of places inside this one (pipeline/relations.py, operator decision 2026-10-16).
NEAR_WORDS = {
    "ko": {"prev": "이전 경유지", "next": "다음 경유지", "here": "이곳", "first": "코스 시작", "last": "코스 끝",
           "to_next": "다음 경유지까지", "to_here": "이곳까지", "varies": "{label} 출처마다 다름", "leg": "직선 {d}", "pos": "경유지 {N}곳 중 {n}번째", "order": "경유지 순서",
           "key": "점 사이 간격은 순서만 · 거리는 좌표 사이 직선", "more_segs": "다른 구간 보기 ({n})",
           "more_guides": "가이드 더 보기 ({n})", "more_events": "행사 더 보기 ({n})", "scale": "막대 끝 = 직선 {d}",
           "see_map": "지도에서 보기", "ev_on": "진행·예정", "ev_past": "지난 회차", "ev_varies": "기간 출처마다 다름",
           "credit": "사진 출처: 한국관광공사 · {lic}", "ext": "지도 검색", "branch": "다른 안",
           "part_of": "속한 곳: {name}", "same_building": "같은 건물: {name}", "parts": "{name} 안에 있는 곳"},
    "en": {"prev": "Previous stop", "next": "Next stop", "here": "Here", "first": "Start of the course",
           "last": "End of the course", "to_next": "To the next stop:", "to_here": "To here:",
           "varies": "{label}: sources differ", "leg": "straight-line {d}",
           "pos": "stop {n} of {N}", "order": "Order of stops",
           "key": "Dots are spaced by order only · distances are straight lines between coordinates",
           "more_segs": "Other sections ({n})", "more_guides": "More guides ({n})", "more_events": "More events ({n})",
           "scale": "Full bar = straight-line {d}", "see_map": "See on the map", "ev_on": "On now or coming up",
           "ev_past": "Past edition", "ev_varies": "Dates differ by source",
           "credit": "Photos: Korea Tourism Organization · {lic}", "ext": "map search", "branch": "Other option",
           "part_of": "Part of {name}", "same_building": "Same building as {name}", "parts": "Places within {name}"},
    "ja": {"prev": "前の経由地", "next": "次の経由地", "here": "ここ", "first": "コースの始まり", "last": "コースの終わり",
           "to_next": "次の経由地まで", "to_here": "ここまで", "varies": "{label}：出典により異なる", "leg": "直線{d}", "pos": "{N}か所中{n}番目の経由地", "order": "経由地の順序",
           "key": "点の間隔は順序だけを表します・距離は座標間の直線距離です", "more_segs": "ほかの区間（{n}）",
           "more_guides": "ほかのガイド（{n}）", "more_events": "ほかのイベント（{n}）", "scale": "バーの端＝直線{d}",
           "see_map": "地図で見る", "ev_on": "開催中・開催予定", "ev_past": "過去の開催", "ev_varies": "日程は出典により異なる",
           "credit": "写真：韓国観光公社・{lic}", "ext": "地図で検索", "branch": "別の案",
           "part_of": "{name}内にあります", "same_building": "{name}と同じ建物です", "parts": "{name}内の場所"},
    "zh-hans": {"prev": "上一站", "next": "下一站", "here": "此处", "first": "路线开始", "last": "路线结束",
                "to_next": "到下一站", "to_here": "到此处", "varies": "{label}：来源不一致", "leg": "直线{d}", "pos": "共{N}站中的第{n}站", "order": "途经顺序",
                "key": "圆点间距只表示顺序 · 距离为坐标之间的直线距离", "more_segs": "其他路段（{n}）",
                "more_guides": "更多指南（{n}）", "more_events": "更多活动（{n}）", "scale": "条形末端 = 直线{d}",
                "see_map": "在地图上查看", "ev_on": "进行中·即将举行", "ev_past": "往届", "ev_varies": "日期因来源而异",
                "credit": "照片：韩国观光公社 · {lic}", "ext": "地图搜索", "branch": "另一方案",
                "part_of": "位于{name}内", "same_building": "与{name}是同一栋建筑", "parts": "{name}内的地点"},
    "zh-hant": {"prev": "上一站", "next": "下一站", "here": "此處", "first": "路線開始", "last": "路線結束",
                "to_next": "到下一站", "to_here": "到此處", "varies": "{label}：來源不一致", "leg": "直線{d}", "pos": "共{N}站中的第{n}站", "order": "途經順序",
                "key": "圓點間距只表示順序 · 距離為座標之間的直線距離", "more_segs": "其他路段（{n}）",
                "more_guides": "更多指南（{n}）", "more_events": "更多活動（{n}）", "scale": "長條末端 = 直線{d}",
                "see_map": "在地圖上查看", "ev_on": "進行中·即將舉行", "ev_past": "往屆", "ev_varies": "日期因來源而異",
                "credit": "照片：韓國觀光公社 · {lic}", "ext": "地圖搜尋", "branch": "另一方案",
                "part_of": "位於{name}內", "same_building": "與{name}是同一棟建築", "parts": "{name}內的地點"},
    "de": {"prev": "Vorherige Station", "next": "Nächste Station", "here": "Hier", "first": "Beginn der Route",
           "last": "Ende der Route", "to_next": "Bis zur nächsten Station:", "to_here": "Bis hierher:",
           "varies": "{label}: je nach Quelle verschieden", "leg": "Luftlinie {d}",
           "pos": "Station {n} von {N}", "order": "Reihenfolge der Stationen",
           "key": "Punktabstände zeigen nur die Reihenfolge · Entfernungen sind Luftlinien zwischen Koordinaten",
           "more_segs": "Weitere Abschnitte ({n})", "more_guides": "Weitere Reiseführer ({n})",
           "more_events": "Weitere Veranstaltungen ({n})", "scale": "Ganzer Balken = Luftlinie {d}",
           "see_map": "Auf der Karte ansehen", "ev_on": "Läuft oder geplant", "ev_past": "Vergangene Ausgabe",
           "ev_varies": "Termine je nach Quelle verschieden", "credit": "Fotos: Koreanische Tourismusorganisation · {lic}", "ext": "Kartensuche", "branch": "Andere Variante",
           "part_of": "Teil von {name}", "same_building": "Im selben Gebäude wie {name}", "parts": "Orte innerhalb von {name}"},
    "fr": {"prev": "Étape précédente", "next": "Étape suivante", "here": "Ici", "first": "Début du circuit",
           "last": "Fin du circuit", "to_next": "Jusqu'à l'étape suivante :", "to_here": "Jusqu'ici :",
           "varies": "{label} : les sources divergent", "leg": "{d} en ligne droite",
           "pos": "étape {n} sur {N}", "order": "Ordre des étapes",
           "key": "L'écart entre les points indique seulement l'ordre · distances en ligne droite entre les coordonnées",
           "more_segs": "Autres tronçons ({n})", "more_guides": "Autres guides ({n})", "more_events": "Autres événements ({n})",
           "scale": "Barre entière = {d} en ligne droite", "see_map": "Voir sur la carte", "ev_on": "En cours ou à venir",
           "ev_past": "Édition passée", "ev_varies": "Dates différentes selon les sources",
           "credit": "Photos : Office national du tourisme coréen · {lic}", "ext": "recherche sur la carte", "branch": "Autre option",
           "part_of": "Fait partie de {name}", "same_building": "Même bâtiment que {name}", "parts": "Lieux situés dans {name}"},
    "es": {"prev": "Parada anterior", "next": "Parada siguiente", "here": "Aquí", "first": "Inicio de la ruta",
           "last": "Fin de la ruta", "to_next": "Hasta la parada siguiente:", "to_here": "Hasta aquí:",
           "varies": "{label}: las fuentes difieren", "leg": "{d} en línea recta",
           "pos": "parada {n} de {N}", "order": "Orden de las paradas",
           "key": "La separación entre puntos solo indica el orden · las distancias son líneas rectas entre coordenadas",
           "more_segs": "Otros tramos ({n})", "more_guides": "Más guías ({n})", "more_events": "Más eventos ({n})",
           "scale": "Barra completa = {d} en línea recta", "see_map": "Ver en el mapa", "ev_on": "En curso o próximo",
           "ev_past": "Edición pasada", "ev_varies": "Las fechas varían según la fuente",
           "credit": "Fotos: Organización de Turismo de Corea · {lic}", "ext": "búsqueda en el mapa", "branch": "Otra opción",
           "part_of": "Forma parte de {name}", "same_building": "Mismo edificio que {name}", "parts": "Lugares dentro de {name}"},
    "ru": {"prev": "Предыдущая остановка", "next": "Следующая остановка", "here": "Здесь", "first": "Начало маршрута",
           "last": "Конец маршрута", "to_next": "До следующей остановки:", "to_here": "До этого места:",
           "varies": "{label}: источники расходятся", "leg": "по прямой {d}",
           "pos": "остановка {n} из {N}", "order": "Порядок остановок",
           "key": "Интервалы между точками показывают только порядок · расстояния — по прямой между координатами",
           "more_segs": "Другие участки ({n})", "more_guides": "Ещё путеводители ({n})", "more_events": "Ещё события ({n})",
           "scale": "Вся полоса = {d} по прямой", "see_map": "Посмотреть на карте", "ev_on": "Идёт или скоро",
           "ev_past": "Прошедший выпуск", "ev_varies": "Даты в источниках расходятся",
           "credit": "Фото: Корейская организация по туризму · {lic}", "ext": "поиск на карте", "branch": "Другой вариант",
           "part_of": "Входит в состав: {name}", "same_building": "То же здание: {name}", "parts": "Объекты на территории: {name}"},
}


# the list pages' filter bar (QA 2026-10-15 SRC-01: the other versions had no filters and no list | map switch on phones):
# the words of templates/_filters.html.j2 for Korean and every version (hand-written like NEAR_WORDS, so a version never
# drops out of the build for a missing string). The chips' own labels are the data's (type, 권역, theme and check
# labels from strings.json); the filter VALUES are the Korean ones in every version (one URL vocabulary: ?type=한식 …).
# of: after the count while a filter is set ({m} = every place of the list). clear_one / clear_all: the buttons of the
# zero-result panel (outside evaluation 2026-10-18: '박물관·전시 + 섬과 바다' left only a sentence) — one per filter that
# brings rows back on its own ({v} = that chip's label in this version) and the reset of every filter. off_map: after
# the map caption, the shown places without coordinates ({n}; worded without a plural form, so one string serves 1 and
# 23 alike).
LIST_WORDS = {
    "ko": {"type": "유형", "all": "전체", "filters": "필터", "view": "보기", "list": "목록", "map": "지도", "area": "권역",
           "all_areas": "모든 권역", "theme": "테마", "all_themes": "모든 테마",
           "empty": "조건에 맞는 곳이 없습니다. 필터를 바꿔 보세요.", "of": " (전체 {m}곳 중)",
           "clear_one": "{v} 조건 해제", "clear_all": "전체 조건 초기화", "off_map": "지도에 없는 {n}곳은 목록에서"},
    "en": {"type": "Type", "all": "All", "filters": "Filters", "view": "View", "list": "List", "map": "Map", "area": "Area",
           "all_areas": "All areas", "theme": "Theme", "all_themes": "All themes",
           "empty": "No places match these filters. Try changing them.", "of": " (of {m})",
           "clear_one": "Remove filter: {v}", "clear_all": "Clear all filters", "off_map": "Not on the map: {n} (see the list)"},
    "ja": {"type": "種類", "all": "すべて", "filters": "絞り込み", "view": "表示", "list": "一覧", "map": "地図", "area": "エリア",
           "all_areas": "すべてのエリア", "theme": "テーマ", "all_themes": "すべてのテーマ",
           "empty": "条件に合う場所がありません。絞り込みを変えてください。", "of": "（全{m}か所中）",
           "clear_one": "「{v}」を解除", "clear_all": "条件をすべて解除", "off_map": "地図にない{n}か所は一覧で"},
    "zh-hans": {"type": "类型", "all": "全部", "filters": "筛选", "view": "查看方式", "list": "列表", "map": "地图", "area": "区域",
                "all_areas": "全部区域", "theme": "主题", "all_themes": "全部主题",
                "empty": "没有符合条件的地点，请更改筛选条件。", "of": "（共{m}个）",
                "clear_one": "取消“{v}”", "clear_all": "清除全部筛选条件", "off_map": "不在地图上的{n}个地点请见列表"},
    "zh-hant": {"type": "類型", "all": "全部", "filters": "篩選", "view": "檢視方式", "list": "列表", "map": "地圖", "area": "區域",
                "all_areas": "全部區域", "theme": "主題", "all_themes": "全部主題",
                "empty": "沒有符合條件的地點，請變更篩選條件。", "of": "（共{m}處）",
                "clear_one": "取消「{v}」", "clear_all": "清除全部篩選條件", "off_map": "不在地圖上的{n}處地點請見列表"},
    "de": {"type": "Art", "all": "Alle", "filters": "Filter", "view": "Ansicht", "list": "Liste", "map": "Karte", "area": "Gebiet",
           "all_areas": "Alle Gebiete", "theme": "Thema", "all_themes": "Alle Themen",
           "empty": "Keine Orte passen zu diesen Filtern. Ändern Sie die Auswahl.", "of": " (von {m})",
           "clear_one": "Filter entfernen: {v}", "clear_all": "Alle Filter zurücksetzen",
           "off_map": "Nicht auf der Karte: {n} (siehe Liste)"},
    "fr": {"type": "Type", "all": "Tous", "filters": "Filtres", "view": "Affichage", "list": "Liste", "map": "Carte",
           "area": "Secteur", "all_areas": "Tous les secteurs", "theme": "Thème", "all_themes": "Tous les thèmes",
           "empty": "Aucun lieu ne correspond à ces filtres. Modifiez-les.", "of": " (sur {m})",
           "clear_one": "Retirer le filtre : {v}", "clear_all": "Effacer tous les filtres",
           "off_map": "Hors de la carte : {n} (voir la liste)"},
    "es": {"type": "Tipo", "all": "Todos", "filters": "Filtros", "view": "Vista", "list": "Lista", "map": "Mapa", "area": "Zona",
           "all_areas": "Todas las zonas", "theme": "Tema", "all_themes": "Todos los temas",
           "empty": "Ningún lugar coincide con estos filtros. Pruebe a cambiarlos.", "of": " (de {m})",
           "clear_one": "Quitar el filtro: {v}", "clear_all": "Quitar todos los filtros",
           "off_map": "Fuera del mapa: {n} (ver la lista)"},
    "ru": {"type": "Тип", "all": "Все", "filters": "Фильтры", "view": "Вид", "list": "Список", "map": "Карта", "area": "Район",
           "all_areas": "Все районы", "theme": "Тема", "all_themes": "Все темы",
           "empty": "Нет мест, подходящих под эти фильтры. Измените их.", "of": " (из {m})",
           "clear_one": "Убрать фильтр: {v}", "clear_all": "Сбросить все фильтры", "off_map": "Нет на карте: {n} (см. список)"},
}

# 조건으로 찾기 (pipeline/conditions.py, _filters.html.j2 conds): the condition chips of the lists, hand-written like
# LIST_WORDS so a version never drops out of the build for a missing string. labels: the chip of each condition
# (mon_<kind> where the kind words it its own way); late_at / late_next / allday: the late tag's words ({t} = 22:00);
# count / of: the visual count above the ratio bar ({n} shown, {m} all; the count line [data-result] stays the words
# a screen reader hears); clear: the button that takes every condition off.
COND_WORDS = {
    "ko": {"group": "조건", "clear": "조건 지우기", "count": "{n}곳", "of": "/ {m}곳",
           "late_at": "{t}까지 영업", "late_next": "익일 {t}까지 영업", "allday": "24시간 영업",
           "labels": {"mon": "월요일 영업", "mon_attraction": "월요일 개방", "late": "21시 이후까지", "park": "주차 가능",
                      "pack": "포장 가능", "pet": "반려동물 동반", "free": "무료", "stroller": "유모차 대여", "wheel": "휠체어",
                      "cook": "취사 가능"}},
    "en": {"group": "Conditions", "clear": "Clear conditions", "count": "{n}", "of": "/ {m}",
           "late_at": "Open until {t}", "late_next": "Open until {t} (next day)", "allday": "Open 24 hours",
           "labels": {"mon": "Open Mondays", "late": "Open till 21:00+", "park": "Parking", "pack": "Takeout",
                      "pet": "Pets allowed", "free": "Free entry", "stroller": "Stroller rental", "wheel": "Wheelchair",
                      "cook": "Cooking allowed"}},
    "ja": {"group": "条件", "clear": "条件をクリア", "count": "{n}", "of": "/ {m}",
           "late_at": "{t}まで営業", "late_next": "翌{t}まで営業", "allday": "24時間営業",
           "labels": {"mon": "月曜営業", "mon_attraction": "月曜も開館", "late": "21時以降まで営業", "park": "駐車可",
                      "pack": "テイクアウト可", "pet": "ペット同伴可", "free": "無料", "stroller": "ベビーカー貸出", "wheel": "車いす",
                      "cook": "自炊可"}},
    "zh-hans": {"group": "条件", "clear": "清除条件", "count": "{n}", "of": "/ {m}",
                "late_at": "营业至{t}", "late_next": "营业至次日{t}", "allday": "24小时营业",
                "labels": {"mon": "周一营业", "mon_attraction": "周一开放", "late": "营业到21点以后", "park": "可停车",
                           "pack": "可外带", "pet": "可带宠物", "free": "免费", "stroller": "婴儿车租借", "wheel": "轮椅",
                           "cook": "可做饭"}},
    "zh-hant": {"group": "條件", "clear": "清除條件", "count": "{n}", "of": "/ {m}",
                "late_at": "營業至{t}", "late_next": "營業至隔日{t}", "allday": "24小時營業",
                "labels": {"mon": "週一營業", "mon_attraction": "週一開放", "late": "營業到21點以後", "park": "可停車",
                           "pack": "可外帶", "pet": "可帶寵物", "free": "免費", "stroller": "嬰兒車租借", "wheel": "輪椅",
                           "cook": "可開伙"}},
    "de": {"group": "Bedingungen", "clear": "Bedingungen löschen", "count": "{n}", "of": "/ {m}",
           "late_at": "Geöffnet bis {t}", "late_next": "Geöffnet bis {t} (Folgetag)", "allday": "24 Stunden geöffnet",
           "labels": {"mon": "Montags geöffnet", "late": "Bis 21 Uhr und länger", "park": "Parkplatz",
                      "pack": "Zum Mitnehmen", "pet": "Haustiere erlaubt", "free": "Eintritt frei",
                      "stroller": "Kinderwagenverleih", "wheel": "Rollstuhl", "cook": "Kochen möglich"}},
    "fr": {"group": "Critères", "clear": "Effacer les critères", "count": "{n}", "of": "/ {m}",
           "late_at": "Ouvert jusqu’à {t}", "late_next": "Ouvert jusqu’à {t} (lendemain)", "allday": "Ouvert 24 h/24",
           "labels": {"mon": "Ouvert le lundi", "late": "Jusqu’à 21 h ou plus", "park": "Parking", "pack": "À emporter",
                      "pet": "Animaux acceptés", "free": "Entrée gratuite", "stroller": "Prêt de poussettes",
                      "wheel": "Fauteuil roulant", "cook": "Cuisine possible"}},
    "es": {"group": "Condiciones", "clear": "Quitar condiciones", "count": "{n}", "of": "/ {m}",
           "late_at": "Abierto hasta las {t}", "late_next": "Abierto hasta las {t} (día siguiente)",
           "allday": "Abierto 24 horas",
           "labels": {"mon": "Abre los lunes", "late": "Hasta las 21:00 o más", "park": "Aparcamiento",
                      "pack": "Para llevar", "pet": "Se admiten mascotas", "free": "Entrada gratuita",
                      "stroller": "Alquiler de carritos", "wheel": "Silla de ruedas", "cook": "Se puede cocinar"}},
    "ru": {"group": "Условия", "clear": "Сбросить условия", "count": "{n}", "of": "/ {m}",
           "late_at": "Открыто до {t}", "late_next": "Открыто до {t} (следующего дня)", "allday": "Круглосуточно",
           "labels": {"mon": "Открыто по понедельникам", "late": "До 21:00 и позже", "park": "Парковка",
                      "pack": "Навынос", "pet": "Можно с питомцами", "free": "Вход бесплатный",
                      "stroller": "Прокат колясок", "wheel": "Инвалидная коляска", "cook": "Можно готовить"}},
}


# the course pages (QA 2026-10-15 F09, F09-a/b/c; templates/en/course.html.j2 and _en.html.j2 week()): the closed-day
# grid by weekday, the source's day / option headings and duration, the optional stop, the unlinked stops' map search,
# and the '차 없이 다니기' block (bus stops near the stops, transit directions per leg, the city bus timetable's first
# and last buses), for Korean and every version — hand-written like NEAR_WORDS, so a version never drops out of the
# build for a missing string. A dict value has one form per plural category of the language (course_word picks it);
# a tuple has one entry per weekday (Monday first) or per item. Bus-stop and timetable stop names stay Korean on the
# pages (lang="ko", with their romanization): the words here never carry them.
COURSE_WORDS = {
    "ko": {"closed": "쉬는 날", "closed_day": ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"),
           "closed_n": "{day} 휴무 {n}곳", "wd_short": ("월", "화", "수", "목", "금", "토", "일"),
           "week_title": "{name} 경유지의 요일별 쉬는 날", "place": "장소", "src_col": "쉬는 날(출처 표기)",
           "closed_on": "{day} 휴무", "partial": "일부 주 휴무", "key_closed": "매주 쉬는 요일",
           "key_partial": "격주·특정 주만 쉬는 요일", "key_blank": "빈칸: 쉬는 날로 적히지 않은 요일",
           "key_na": "쉬는 날 자료가 없거나 출처마다 다른 칸", "day": "{n}일차", "day_opt": "{n}일차({k}안)",
           "day_head": "코스 원문 일정", "taketime": "소요시간", "hours_n": "{n}시간", "optional": "선택 경유지",
           "gmaps_search": "구글 지도에서 찾기(검색)", "guide": "가이드: {name}", "map_opt": " · 선택 경유지는 그리지 않음",
           "move_h": "차 없이 다니기", "bus_h": "경유지 근처 버스 정류장", "bus_r": "직선거리 {m}m 안", "stop_word": "정류장",
           "city_bus": "시내버스 {routes}번", "more_bus": "다른 경유지 근처 정류장 ({n})",
           "legs_h": "경유지 사이 대중교통 길찾기", "legs_r": "경로와 시간은 지도 앱이 계산", "transit_link": "대중교통 길찾기",
           "tt_h": "시내버스 첫차·막차", "tt_r": "시간표의 기준 정류장 시각", "bus_no": "시내버스 {no}번", "weekdays": "평일",
           "same_all": "평일·토·일·공휴일 같음", "weekend": "토·일·공휴일", "out": "가는 편", "back": "돌아오는 편",
           "runs": "{n}회", "past_hour": "매시 {m}분", "differ": "{dir} {stop} 시각 출처마다 다름",
           "tt_two": "시간표 {a} · {provider} {b}", "guides_h": "가이드", "routes_more": "다른 노선 {nos}번", "routes_all": "노선 {nos}번", "missing_items": ("구간별 이동 시간", "총 소요 시간"),
           "src_bus": "정류장·거리: {stops} · 노선 번호: {tt}", "src_times": "시각: {name} — {provider}",
           "src_dir": "길찾기: 지도 앱", "src_stops": "공공데이터포털 군산시 버스정류장현황",
           "src_tt": "군산시 시내버스 시간표(2024.10.21 시행)"},
    "en": {"closed": "Closed days",
           "closed_day": ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"),
           "closed_n": {"one": "{n} stop closed on {day}", "other": "{n} stops closed on {day}"},
           "wd_short": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
           "week_title": "{name}: closed days of the stops by weekday", "place": "Place", "src_col": "Closed days as listed",
           "closed_on": "closed on {day}", "partial": "closed in some weeks only", "key_closed": "Closed every week",
           "key_partial": "Closed in some weeks only (every other week or given weeks)",
           "key_blank": "Blank: not listed as a closed day", "key_na": "No closed-day data, or the sources differ",
           "day": "Day {n}", "day_opt": "Day {n}, option {k}", "day_head": "Itinerary", "taketime": "Time needed",
           "hours_n": {"one": "{n} hour", "other": "{n} hours"}, "optional": "Optional stop",
           "gmaps_search": "Search on Google Maps", "guide": "Guide: {name}", "map_opt": " · the optional stop is not drawn",
           "move_h": "Getting around without a car", "bus_h": "Bus stops near the stops", "bus_r": "straight line, within {m} m",
           "stop_word": "stop", "city_bus": "city bus {routes}", "more_bus": "Bus stops near the other stops ({n})",
           "legs_h": "Public transport between stops", "legs_r": "Google Maps works out the route and the time",
           "transit_link": "Public transport directions (Google Maps)", "tt_h": "First and last city buses",
           "tt_r": "times at the reference stops of the timetable", "bus_no": "City bus {no}", "weekdays": "Weekdays",
           "same_all": "Weekdays, Saturdays, Sundays and holidays alike", "weekend": "Saturdays, Sundays and holidays",
           "out": "outbound", "back": "return", "runs": {"one": "{n} run", "other": "{n} runs"},
           "past_hour": "at :{m} every hour", "differ": "{dir} {stop}: sources differ",
           "tt_two": "timetable {a} · {provider} {b}", "guides_h": "Guides", "routes_more": "Other routes: {nos}", "routes_all": "Routes: {nos}",
           "missing_items": ("travel time per leg", "total time"),
           "src_bus": "Bus stops and distances: {stops} · route numbers: {tt}",
           "src_times": "Times: {name} — {provider}", "src_dir": "Directions: Google Maps",
           "src_stops": "Gunsan bus stop list, Public Data Portal",
           "src_tt": "Gunsan city bus timetable (in effect from October 21, 2024)"},
    "ja": {"closed": "休業日", "closed_day": ("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
           "closed_n": "{day}休み {n}か所", "wd_short": ("月", "火", "水", "木", "金", "土", "日"),
           "week_title": "{name}：立ち寄り先の曜日別の休業日", "place": "場所", "src_col": "休業日（出典の表記）",
           "closed_on": "{day}休み", "partial": "一部の週のみ休み", "key_closed": "毎週休み",
           "key_partial": "隔週・特定の週のみ休み", "key_blank": "空欄：休業日として記載のない曜日",
           "key_na": "休業日の情報がない、または出典により異なる", "day": "{n}日目", "day_opt": "{n}日目（{k}案）",
           "day_head": "日程", "taketime": "所要時間", "hours_n": "{n}時間", "optional": "任意の立ち寄り先",
           "gmaps_search": "Googleマップで検索", "guide": "ガイド：{name}", "map_opt": "・任意の立ち寄り先は地図に描いていません",
           "move_h": "車なしで回る", "bus_h": "立ち寄り先近くのバス停", "bus_r": "直線距離{m} m以内", "stop_word": "バス停",
           "city_bus": "市内バス{routes}番", "more_bus": "ほかの立ち寄り先近くのバス停（{n}）",
           "legs_h": "立ち寄り先間の公共交通ルート", "legs_r": "経路と所要時間はGoogleマップが計算",
           "transit_link": "公共交通ルート（Googleマップ）", "tt_h": "市内バスの始発・終発", "tt_r": "時刻表の基準停留所の時刻",
           "bus_no": "市内バス{no}番", "weekdays": "平日", "same_all": "平日・土日祝日とも同じ", "weekend": "土日祝日",
           "out": "往路", "back": "復路", "runs": "{n}本", "past_hour": "毎時{m}分", "differ": "{dir}{stop}：出典により異なる",
           "tt_two": "時刻表 {a}・{provider} {b}", "guides_h": "ガイド", "routes_more": "ほかの路線：{nos}番", "routes_all": "路線：{nos}番", "missing_items": ("区間ごとの所要時間", "全体の所要時間"),
           "src_bus": "バス停と距離：{stops}、路線番号：{tt}", "src_times": "時刻：{name}（{provider}）",
           "src_dir": "ルート：Googleマップ", "src_stops": "群山市バス停現況（公共データポータル）",
           "src_tt": "群山市内バス時刻表（2024年10月21日施行）"},
    "zh-hans": {"closed": "休息日", "closed_day": ("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                "closed_n": "{day}休息 {n}处", "wd_short": ("一", "二", "三", "四", "五", "六", "日"),
                "week_title": "{name}：各途经地按星期的休息日", "place": "地点", "src_col": "休息日（来源原文）",
                "closed_on": "{day}休息", "partial": "仅部分周休息", "key_closed": "每周休息", "key_partial": "隔周或特定周休息",
                "key_blank": "空白：未列为休息日", "key_na": "无休息日资料或来源不一致", "day": "第{n}天",
                "day_opt": "第{n}天（方案{k}）", "day_head": "行程", "taketime": "所需时间", "hours_n": "{n}小时",
                "optional": "可选途经地", "gmaps_search": "在 Google 地图中搜索", "guide": "指南：{name}",
                "map_opt": " · 可选途经地未画出", "move_h": "无车出行", "bus_h": "途经地附近的公交站", "bus_r": "直线{m} m以内",
                "stop_word": "站", "city_bus": "市内公交{routes}路", "more_bus": "其他途经地附近的公交站（{n}）",
                "legs_h": "途经地之间的公共交通路线", "legs_r": "路线和时间由 Google 地图计算",
                "transit_link": "公共交通路线（Google 地图）", "tt_h": "市内公交首末班车", "tt_r": "时刻表基准站的时刻",
                "bus_no": "市内公交{no}路", "weekdays": "工作日", "same_all": "工作日与周六、周日、节假日相同",
                "weekend": "周六、周日、节假日", "out": "去程", "back": "返程", "runs": "{n}班", "past_hour": "每小时{m}分",
                "differ": "{dir}{stop}：来源不一致", "tt_two": "时刻表{a} · {provider}{b}", "guides_h": "指南", "routes_more": "其他线路：{nos}路", "routes_all": "线路：{nos}路",
                "missing_items": ("各路段所需时间", "总所需时间"), "src_bus": "公交站与距离：{stops}；线路号：{tt}",
                "src_times": "时刻：{name}（{provider}）", "src_dir": "路线：Google 地图",
                "src_stops": "群山市公交站现状（公共数据门户）", "src_tt": "群山市内公交时刻表（2024年10月21日起施行）"},
    "zh-hant": {"closed": "休息日", "closed_day": ("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                "closed_n": "{day}休息 {n}處", "wd_short": ("一", "二", "三", "四", "五", "六", "日"),
                "week_title": "{name}：各途經地依星期的休息日", "place": "地點", "src_col": "休息日（來源原文）",
                "closed_on": "{day}休息", "partial": "僅部分週休息", "key_closed": "每週休息", "key_partial": "隔週或特定週休息",
                "key_blank": "空白：未列為休息日", "key_na": "無休息日資料或來源不一致", "day": "第{n}天",
                "day_opt": "第{n}天（方案{k}）", "day_head": "行程", "taketime": "所需時間", "hours_n": "{n}小時",
                "optional": "可選途經地", "gmaps_search": "在 Google 地圖搜尋", "guide": "指南：{name}",
                "map_opt": " · 可選途經地未畫出", "move_h": "無車出行", "bus_h": "途經地附近的公車站", "bus_r": "直線{m} m以內",
                "stop_word": "站", "city_bus": "市區公車{routes}路", "more_bus": "其他途經地附近的公車站（{n}）",
                "legs_h": "途經地之間的大眾運輸路線", "legs_r": "路線與時間由 Google 地圖計算",
                "transit_link": "大眾運輸路線（Google 地圖）", "tt_h": "市區公車首末班車", "tt_r": "時刻表基準站的時刻",
                "bus_no": "市區公車{no}路", "weekdays": "平日", "same_all": "平日與週六、週日、假日相同",
                "weekend": "週六、週日、假日", "out": "去程", "back": "回程", "runs": "{n}班", "past_hour": "每小時{m}分",
                "differ": "{dir}{stop}：來源不一致", "tt_two": "時刻表{a} · {provider}{b}", "guides_h": "指南", "routes_more": "其他路線：{nos}路", "routes_all": "路線：{nos}路",
                "missing_items": ("各路段所需時間", "總所需時間"), "src_bus": "公車站與距離：{stops}；路線號：{tt}",
                "src_times": "時刻：{name}（{provider}）", "src_dir": "路線：Google 地圖",
                "src_stops": "群山市公車站現況（公共資料入口網）", "src_tt": "群山市區公車時刻表（2024年10月21日起施行）"},
    "de": {"closed": "Ruhetage",
           "closed_day": ("montags", "dienstags", "mittwochs", "donnerstags", "freitags", "samstags", "sonntags"),
           "closed_n": {"one": "{n} Station {day} geschlossen", "other": "{n} Stationen {day} geschlossen"},
           "wd_short": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
           "week_title": "{name}: Ruhetage der Stationen nach Wochentag", "place": "Ort", "src_col": "Ruhetage laut Quelle",
           "closed_on": "{day} geschlossen", "partial": "nur in manchen Wochen geschlossen",
           "key_closed": "Jede Woche geschlossen",
           "key_partial": "Nur in manchen Wochen geschlossen (jede zweite oder bestimmte Wochen)",
           "key_blank": "Leer: nicht als Ruhetag angegeben",
           "key_na": "Keine Angaben zu Ruhetagen oder die Quellen widersprechen sich", "day": "Tag {n}",
           "day_opt": "Tag {n}, Variante {k}", "day_head": "Tagesplan", "taketime": "Zeitbedarf",
           "hours_n": {"one": "{n} Stunde", "other": "{n} Stunden"}, "optional": "Optionale Station",
           "gmaps_search": "In Google Maps suchen", "guide": "Ratgeber: {name}",
           "map_opt": " · die optionale Station ist nicht eingezeichnet", "move_h": "Unterwegs ohne Auto",
           "bus_h": "Bushaltestellen bei den Stationen", "bus_r": "Luftlinie, bis {m} m", "stop_word": "Haltestelle",
           "city_bus": "Stadtbus {routes}", "more_bus": "Haltestellen bei den anderen Stationen ({n})",
           "legs_h": "Mit öffentlichen Verkehrsmitteln zwischen den Stationen",
           "legs_r": "Route und Fahrzeit berechnet Google Maps", "transit_link": "Route mit Bus und Bahn (Google Maps)",
           "tt_h": "Erste und letzte Stadtbusse", "tt_r": "Zeiten an den Bezugshaltestellen des Fahrplans",
           "bus_no": "Stadtbus {no}", "weekdays": "Montag bis Freitag",
           "same_all": "Montag bis Freitag, Samstag, Sonntag und Feiertage gleich",
           "weekend": "Samstag, Sonntag und Feiertage", "out": "Hinfahrt", "back": "Rückfahrt",
           "runs": {"one": "{n} Fahrt", "other": "{n} Fahrten"}, "past_hour": "stündlich um :{m}",
           "differ": "{dir} {stop}: die Quellen widersprechen sich", "tt_two": "Fahrplan {a} · {provider} {b}",
           "guides_h": "Ratgeber", "routes_more": "Weitere Linien: {nos}", "routes_all": "Linien: {nos}", "missing_items": ("Fahrzeit je Abschnitt", "Gesamtdauer"),
           "src_bus": "Haltestellen und Entfernungen: {stops} · Liniennummern: {tt}",
           "src_times": "Zeiten: {name} — {provider}", "src_dir": "Routen: Google Maps",
           "src_stops": "Bushaltestellen der Stadt Gunsan, Portal für öffentliche Daten",
           "src_tt": "Stadtbusfahrplan Gunsan (gültig ab 21. Oktober 2024)"},
    "fr": {"closed": "Jours de fermeture",
           "closed_day": ("le lundi", "le mardi", "le mercredi", "le jeudi", "le vendredi", "le samedi", "le dimanche"),
           "closed_n": {"one": "{n} étape fermée {day}", "other": "{n} étapes fermées {day}"},
           "wd_short": ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
           "week_title": "{name} : jours de fermeture des étapes par jour de la semaine", "place": "Lieu",
           "src_col": "Jours de fermeture selon la source", "closed_on": "fermé le {day}",
           "partial": "fermé certaines semaines seulement", "key_closed": "Fermé chaque semaine",
           "key_partial": "Fermé certaines semaines seulement (une semaine sur deux ou des semaines précises)",
           "key_blank": "Case vide : pas indiqué comme jour de fermeture",
           "key_na": "Pas de données de fermeture, ou les sources divergent", "day": "Jour {n}",
           "day_opt": "Jour {n}, option {k}", "day_head": "Programme", "taketime": "Durée",
           "hours_n": {"one": "{n} heure", "other": "{n} heures"}, "optional": "Étape facultative",
           "gmaps_search": "Rechercher sur Google Maps", "guide": "Guide : {name}",
           "map_opt": " · l'étape facultative n'est pas tracée", "move_h": "Se déplacer sans voiture",
           "bus_h": "Arrêts de bus près des étapes", "bus_r": "à vol d'oiseau, moins de {m} m", "stop_word": "arrêt",
           "city_bus": "bus urbain {routes}", "more_bus": "Arrêts près des autres étapes ({n})",
           "legs_h": "Transports en commun entre les étapes", "legs_r": "Google Maps calcule l'itinéraire et la durée",
           "transit_link": "Itinéraire en transports en commun (Google Maps)", "tt_h": "Premiers et derniers bus urbains",
           "tt_r": "horaires aux arrêts de référence de la grille", "bus_no": "Bus urbain {no}",
           "weekdays": "Du lundi au vendredi",
           "same_all": "Identique du lundi au vendredi, le samedi, le dimanche et les jours fériés",
           "weekend": "Samedi, dimanche et jours fériés", "out": "aller", "back": "retour",
           "runs": {"one": "{n} départ", "other": "{n} départs"}, "past_hour": "toutes les heures à :{m}",
           "differ": "{dir} {stop} : les sources divergent", "tt_two": "grille {a} · {provider} {b}", "guides_h": "Guides", "routes_more": "Autres lignes : {nos}",
           "routes_all": "Lignes : {nos}",
           "missing_items": ("durée de chaque trajet", "durée totale"),
           "src_bus": "Arrêts et distances : {stops} · numéros de ligne : {tt}",
           "src_times": "Horaires : {name} — {provider}", "src_dir": "Itinéraires : Google Maps",
           "src_stops": "Liste des arrêts de bus de Gunsan, portail des données publiques",
           "src_tt": "Horaires des bus urbains de Gunsan (en vigueur depuis le 21 octobre 2024)"},
    "es": {"closed": "Días de cierre",
           "closed_day": ("los lunes", "los martes", "los miércoles", "los jueves", "los viernes", "los sábados",
                          "los domingos"),
           "closed_n": {"one": "{n} parada cierra {day}", "other": "{n} paradas cierran {day}"},
           "wd_short": ("lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."),
           "week_title": "{name}: días de cierre de las paradas por día de la semana", "place": "Lugar",
           "src_col": "Días de cierre según la fuente", "closed_on": "cierra el {day}", "partial": "cierra solo algunas semanas",
           "key_closed": "Cierra todas las semanas", "key_partial": "Cierra solo algunas semanas (semanas alternas o concretas)",
           "key_blank": "En blanco: no figura como día de cierre", "key_na": "Sin datos de cierre, o las fuentes difieren",
           "day": "Día {n}", "day_opt": "Día {n}, opción {k}", "day_head": "Programa", "taketime": "Duración",
           "hours_n": {"one": "{n} hora", "other": "{n} horas"}, "optional": "Parada opcional",
           "gmaps_search": "Buscar en Google Maps", "guide": "Guía: {name}", "map_opt": " · la parada opcional no se dibuja",
           "move_h": "Moverse sin coche", "bus_h": "Paradas de autobús cerca de las paradas de la ruta",
           "bus_r": "en línea recta, a menos de {m} m", "stop_word": "parada", "city_bus": "autobús urbano {routes}",
           "more_bus": "Paradas cerca de las demás paradas de la ruta ({n})", "legs_h": "Transporte público entre las paradas",
           "legs_r": "Google Maps calcula el recorrido y el tiempo",
           "transit_link": "Cómo llegar en transporte público (Google Maps)", "tt_h": "Primeros y últimos autobuses urbanos",
           "tt_r": "horas en las paradas de referencia del horario", "bus_no": "Autobús urbano {no}",
           "weekdays": "De lunes a viernes", "same_all": "Igual de lunes a viernes, sábados, domingos y festivos",
           "weekend": "Sábados, domingos y festivos", "out": "ida", "back": "vuelta",
           "runs": {"one": "{n} salida", "other": "{n} salidas"}, "past_hour": "cada hora a las :{m}",
           "differ": "{dir} {stop}: las fuentes difieren", "tt_two": "horario {a} · {provider} {b}", "guides_h": "Guías", "routes_more": "Otras líneas: {nos}", "routes_all": "Líneas: {nos}",
           "missing_items": ("tiempo de cada tramo", "tiempo total"),
           "src_bus": "Paradas y distancias: {stops} · números de línea: {tt}",
           "src_times": "Horas: {name} — {provider}", "src_dir": "Rutas: Google Maps",
           "src_stops": "Lista de paradas de autobús de Gunsan, portal de datos públicos",
           "src_tt": "Horario de autobuses urbanos de Gunsan (vigente desde el 21 de octubre de 2024)"},
    "ru": {"closed": "Выходные дни",
           "closed_day": ("по понедельникам", "по вторникам", "по средам", "по четвергам", "по пятницам", "по субботам",
                          "по воскресеньям"),
           "closed_n": {"one": "{n} остановка закрыта {day}", "few": "{n} остановки закрыты {day}",
                        "many": "{n} остановок закрыты {day}"},
           "wd_short": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
           "week_title": "{name}: выходные дни остановок по дням недели", "place": "Место",
           "src_col": "Выходные дни по источнику", "closed_on": "закрыто: {day}",
           "partial": "закрыто только в некоторые недели", "key_closed": "Закрыто каждую неделю",
           "key_partial": "Закрыто только в некоторые недели (через неделю или в определённые недели)",
           "key_blank": "Пусто: не указан как выходной", "key_na": "Нет данных о выходных или источники расходятся",
           "day": "День {n}", "day_opt": "День {n}, вариант {k}", "day_head": "Программа", "taketime": "Продолжительность",
           "hours_n": {"one": "{n} час", "few": "{n} часа", "many": "{n} часов"}, "optional": "Необязательная остановка",
           "gmaps_search": "Найти в Google Картах", "guide": "Путеводитель: {name}",
           "map_opt": " · необязательная остановка на карте не показана", "move_h": "Без машины",
           "bus_h": "Автобусные остановки рядом с местами маршрута", "bus_r": "по прямой, до {m} м",
           "stop_word": "остановка", "city_bus": "городской автобус {routes}",
           "more_bus": "Остановки рядом с другими местами маршрута ({n})",
           "legs_h": "Общественный транспорт между остановками маршрута",
           "legs_r": "маршрут и время рассчитывают Google Карты",
           "transit_link": "Маршрут на общественном транспорте (Google Карты)",
           "tt_h": "Первые и последние городские автобусы", "tt_r": "время на опорных остановках расписания",
           "bus_no": "Городской автобус {no}", "weekdays": "Будни",
           "same_all": "Одинаково в будни, субботу, воскресенье и праздники", "weekend": "Суббота, воскресенье и праздники",
           "out": "туда", "back": "обратно", "runs": {"one": "{n} рейс", "few": "{n} рейса", "many": "{n} рейсов"},
           "past_hour": "каждый час в :{m}", "differ": "{dir} {stop}: источники расходятся",
           "tt_two": "расписание {a} · {provider} {b}", "guides_h": "Путеводители", "routes_more": "Другие маршруты: {nos}",
           "routes_all": "Маршруты: {nos}",
           "missing_items": ("время в пути на каждом участке", "общее время"),
           "src_bus": "Остановки и расстояния: {stops} · номера маршрутов: {tt}",
           "src_times": "Время: {name} — {provider}", "src_dir": "Маршруты: Google Карты",
           "src_stops": "Список автобусных остановок Кунсана, портал открытых данных",
           "src_tt": "Расписание городских автобусов Кунсана (действует с 21 октября 2024 г.)"},
}


def course_word(code: str, key: str, n: int | None = None, **kw) -> str:
    """COURSE_WORDS[code][key] filled in: a plural dict takes the form of n in the language (Korean has none)."""
    v = COURSE_WORDS[code][key]
    if isinstance(v, dict):
        v = v[LOCALES[code].plural_form(int(n or 0))]
    return v.format(n=n, **kw) if isinstance(v, str) else v


# 코스 목록 카드 (operator 2026-10-31 '이런 곳들 UI도 좀 더 고도화할 방안 없나?'; present.course_index_vm, en_site
# Site.course_cards, templates/_courses.html.j2): the /courses/ page's group nav and eyebrows, the stop range under a
# group heading ({a}–{b}, plural by {n} = b), a card's key figures (dt labels; n = the stop count as the dd), the route
# band ('외 n곳', its start and last tags, its aria-label), the photo caption, the source line and the notes under the
# groups — hand-written like LIST_WORDS so a version never drops out of the build for a missing string. No internal
# term ('좌표 있는 구간 n/m') — a course page keeps its measured legs in its own sources block.
COURSES_WORDS = {
    "ko": {"nav": "일정·주제별 코스", "by_dur": "일정별", "by_theme": "주제별", "range": "경유지 {a}~{n}곳",
           "range_one": "경유지 {n}곳", "stops": "경유지", "n": "{n}곳", "line": "직선 합", "time": "소요시간",
           "closed": "쉬는 날", "areas": "지나는 권역", "more": "외 {n}곳", "start": "출발", "end": "마지막",
           "route_all": "{name} 경유지 순서", "route_part": "{name} 경유지 순서: 처음 {k}곳과 마지막",
           "photo": "사진: {name}", "official": "{src} 공식 코스", "photos_src": "사진 출처: {name}",
           "note_line": "직선 합은 경유지 좌표 사이 직선거리를 더한 값이며(좌표 출처는 코스마다 표시), 모든 구간에 좌표가 "
                        "있는 코스에만 적었습니다.",
           "note_areas": "권역은 지도 페이지의 여행 권역이고, 장소 페이지가 없는 경유지는 넣지 않았습니다.",
           "note_photo": "카드 사진은 그 코스 경유지 한 곳의 사진으로, 앞 카드와 겹치지 않는 첫 경유지를 골랐습니다."},
    "en": {"nav": "Courses by length and theme", "by_dur": "By length", "by_theme": "By theme",
           "range": "{a}–{n} stops", "range_one": {"one": "{n} stop", "other": "{n} stops"}, "stops": "Stops", "n": "{n}",
           "line": "Straight line", "time": "Time needed", "closed": "Closed days", "areas": "Areas",
           "more": "+ {n} more", "start": "Start", "end": "Last", "route_all": "Stops of {name} in order",
           "route_part": "Stops of {name}: the first {k} and the last", "photo": "Photo: {name}",
           "official": "Official course of {src}", "photos_src": "Photos: {name}",
           "note_line": "The straight line is the sum of the straight-line distances between the stops' coordinates, "
                        "given only for a course with coordinates for every leg.",
           "note_areas": "Areas are this site's travel areas, taken from the stops that have a place page.",
           "note_photo": "Each card's photo shows one stop of its course: the first one not already shown on an "
                         "earlier card."},
    "ja": {"nav": "日程・テーマ別のコース", "by_dur": "日程別", "by_theme": "テーマ別", "range": "立ち寄り先{a}～{n}か所",
           "range_one": "立ち寄り先{n}か所", "stops": "立ち寄り先", "n": "{n}か所", "line": "直線距離の合計",
           "time": "所要時間", "closed": "休業日", "areas": "エリア", "more": "ほか{n}か所", "start": "出発", "end": "最後",
           "route_all": "{name}の立ち寄り先（順番）", "route_part": "{name}の立ち寄り先：最初の{k}か所と最後",
           "photo": "写真：{name}", "official": "{src}の公式コース", "photos_src": "写真の出典：{name}",
           "note_line": "直線距離の合計は立ち寄り先の座標間の直線距離を足したもので、すべての区間に座標があるコースにのみ記しています。",
           "note_areas": "エリアはこのサイトの旅行エリアで、場所のページがない立ち寄り先は含めていません。",
           "note_photo": "カードの写真はそのコースの立ち寄り先1か所の写真で、前のカードと重ならない最初の立ち寄り先を選んでいます。"},
    "zh-hans": {"nav": "按行程和主题分类的路线", "by_dur": "按行程", "by_theme": "按主题", "range": "途经地{a}～{n}处",
                "range_one": "途经地{n}处", "stops": "途经地", "n": "{n}处", "line": "直线距离合计", "time": "所需时间",
                "closed": "休息日", "areas": "区域", "more": "另有{n}处", "start": "出发", "end": "最后",
                "route_all": "{name}的途经地（按顺序）", "route_part": "{name}的途经地：前{k}处和最后一处",
                "photo": "照片：{name}", "official": "{src}官方路线", "photos_src": "照片来源：{name}",
                "note_line": "直线距离合计是各途经地坐标之间直线距离之和，仅标注在所有路段都有坐标的路线上。",
                "note_areas": "区域是本网站的旅游区域，没有地点页面的途经地不计入。",
                "note_photo": "卡片照片是该路线一处途经地的照片，选取与前面卡片不重复的第一处途经地。"},
    "zh-hant": {"nav": "依行程與主題分類的路線", "by_dur": "依行程", "by_theme": "依主題", "range": "途經地{a}～{n}處",
                "range_one": "途經地{n}處", "stops": "途經地", "n": "{n}處", "line": "直線距離合計", "time": "所需時間",
                "closed": "休息日", "areas": "區域", "more": "另有{n}處", "start": "出發", "end": "最後",
                "route_all": "{name}的途經地（依序）", "route_part": "{name}的途經地：前{k}處與最後一處",
                "photo": "照片：{name}", "official": "{src}官方路線", "photos_src": "照片來源：{name}",
                "note_line": "直線距離合計是各途經地座標之間直線距離的總和，只標示在所有路段都有座標的路線上。",
                "note_areas": "區域是本網站的旅遊區域，沒有地點頁面的途經地不計入。",
                "note_photo": "卡片照片是該路線一處途經地的照片，選取與前面卡片不重複的第一處途經地。"},
    "de": {"nav": "Routen nach Dauer und Thema", "by_dur": "Nach Dauer", "by_theme": "Nach Thema",
           "range": "{a}–{n} Stationen", "range_one": {"one": "{n} Station", "other": "{n} Stationen"},
           "stops": "Stationen", "n": "{n}", "line": "Luftlinie", "time": "Zeitbedarf", "closed": "Ruhetage",
           "areas": "Gebiete", "more": "+ {n} weitere", "start": "Start", "end": "Ziel",
           "route_all": "Stationen von {name} der Reihe nach", "route_part": "Stationen von {name}: die ersten {k} und die letzte",
           "photo": "Foto: {name}", "official": "Offizielle Route von {src}", "photos_src": "Fotos: {name}",
           "note_line": "Die Luftlinie ist die Summe der direkten Entfernungen zwischen den Koordinaten der Stationen und "
                        "steht nur bei einer Route, für deren Abschnitte alle Koordinaten vorliegen.",
           "note_areas": "Die Gebiete sind die Reisegebiete dieser Website, ermittelt aus den Stationen mit eigener Ortsseite.",
           "note_photo": "Das Foto einer Karte zeigt eine Station der Route, und zwar die erste, die noch auf keiner "
                         "früheren Karte zu sehen ist."},
    "fr": {"nav": "Circuits par durée et par thème", "by_dur": "Par durée", "by_theme": "Par thème",
           "range": "{a} à {n} étapes", "range_one": {"one": "{n} étape", "other": "{n} étapes"}, "stops": "Étapes",
           "n": "{n}", "line": "En ligne droite", "time": "Durée", "closed": "Jours de fermeture", "areas": "Secteurs",
           "more": "+ {n} autres", "start": "Départ", "end": "Arrivée", "route_all": "{name} : étapes dans l'ordre",
           "route_part": "{name} : les {k} premières étapes et la dernière", "photo": "Photo : {name}",
           "official": "Circuit officiel de {src}", "photos_src": "Photos : {name}",
           "note_line": "La distance en ligne droite est la somme des distances directes entre les coordonnées des "
                        "étapes ; elle n'est donnée que pour un circuit dont tous les tronçons ont des coordonnées.",
           "note_areas": "Les secteurs sont les zones de visite de ce site, d'après les étapes qui ont une page de lieu.",
           "note_photo": "La photo de chaque carte montre une étape du circuit : la première qui n'est pas déjà sur une "
                         "carte précédente."},
    "es": {"nav": "Rutas por duración y tema", "by_dur": "Por duración", "by_theme": "Por tema",
           "range": "De {a} a {n} paradas", "range_one": {"one": "{n} parada", "other": "{n} paradas"},
           "stops": "Paradas", "n": "{n}", "line": "En línea recta", "time": "Duración", "closed": "Días de cierre",
           "areas": "Zonas", "more": "+ {n} más", "start": "Salida", "end": "Última",
           "route_all": "Paradas de {name} en orden", "route_part": "Paradas de {name}: las {k} primeras y la última",
           "photo": "Foto: {name}", "official": "Ruta oficial de {src}", "photos_src": "Fotos: {name}",
           "note_line": "La distancia en línea recta es la suma de las distancias directas entre las coordenadas de las "
                        "paradas y solo se da para una ruta con coordenadas en todos sus tramos.",
           "note_areas": "Las zonas son las áreas de viaje de este sitio, tomadas de las paradas que tienen página propia.",
           "note_photo": "La foto de cada tarjeta muestra una parada de la ruta: la primera que no aparece ya en una "
                         "tarjeta anterior."},
    "ru": {"nav": "Маршруты по длительности и темам", "by_dur": "По длительности", "by_theme": "По темам",
           "range": {"one": "{a}–{n} пункт маршрута", "few": "{a}–{n} пункта маршрута", "many": "{a}–{n} пунктов маршрута"},
           "range_one": {"one": "{n} пункт маршрута", "few": "{n} пункта маршрута", "many": "{n} пунктов маршрута"},
           "stops": "Пункты маршрута", "n": "{n}", "line": "По прямой", "time": "Продолжительность",
           "closed": "Выходные дни", "areas": "Районы", "more": "+ ещё {n}", "start": "Начало", "end": "Конец",
           "route_all": "Пункты маршрута по порядку: {name}", "route_part": "Пункты маршрута {name}: первые {k} и последний",
           "photo": "Фото: {name}", "official": "Официальный маршрут: {src}", "photos_src": "Фото: {name}",
           "note_line": "Расстояние по прямой — это сумма прямых расстояний между координатами пунктов маршрута; оно "
                        "указано только для маршрута, у всех отрезков которого есть координаты.",
           "note_areas": "Районы — это туристические районы этого сайта, определённые по пунктам, у которых есть своя страница.",
           "note_photo": "Фото на карточке показывает один пункт маршрута — первый, которого ещё нет на предыдущих карточках."},
}


def courses_word(code: str, key: str, n: int | None = None, **kw) -> str:
    """COURSES_WORDS[code][key] filled in: a plural dict takes the form of n in the language (Korean has none)."""
    v = COURSES_WORDS[code][key]
    if isinstance(v, dict):
        v = v[LOCALES[code].plural_form(int(n or 0))]
    return v.format(n=n, **kw)


# 예약하기 (step 1, 2026-10-16; pipeline/booking.py, templates/_ui.html.j2 book()): the button word, the guide and course
# box's heading, the one note under the buttons, the page-nav link, the about pages' sentence and the names of the
# booking services of data/<region>/booking.json, for Korean and every version — hand-written like NEAR_WORDS, so a
# version never drops out of the build for a missing string. The chat's link cards name a booking link with 'book'
# (templates/assets/chat.js STR kinds.book: the same words — tests/test_booking.py).
BOOK_WORDS = {
    "ko": {"book": "예약하기", "box": "예약·예매", "nav": "예약",
           "note": "공식 예약 페이지로 이동합니다. 이 사이트는 예약을 받지 않습니다.",
           "about": "이 사이트는 예약·결제를 받지 않습니다. 장소·가이드·코스 페이지의 '예약하기' 버튼은 데이터에 있는 공식 예약 "
                    "페이지(시설이나 공공기관이 운영하는 곳)로만 이어지고, 여행사·숙박 예약 앱의 링크는 버튼으로 만들지 않습니다.",
           "svc": {"bus": "버스타고 시외버스", "rail": "코레일", "ferry": "한국해운조합 여객선",
                   "citytour": "군산시 시티투어", "forest": "산림청 숲나들e", "camp": "무녀도오토캠핑장",
                   "heli": "수에어항공"}},
    "en": {"book": "Book", "box": "Booking and tickets", "nav": "Booking",
           "note": "Opens the official site. This site takes no bookings.",
           "about": "This site takes no bookings or payments. The ‘Book’ buttons on place, guide and course pages open only "
                    "the official booking pages in our data (run by the facility or a public body); links of travel "
                    "agencies and booking apps never become buttons.",
           "svc": {"bus": "Bustago intercity buses", "rail": "Korail", "ferry": "Korea Shipping Association ferries",
                   "citytour": "Gunsan City Tour", "forest": "Sumnadeul-e, Korea Forest Service",
                   "camp": "Munyeodo Auto Campground", "heli": "Su Air Aviation"}},
    "ja": {"book": "予約する", "box": "予約・チケット", "nav": "予約",
           "note": "公式サイトが開きます（このサイトでは予約不可）。",
           "about": "このサイトは予約や支払いを受け付けません。スポット・ガイド・コースのページの「予約する」ボタンは、データにある"
                    "公式の予約ページ（施設や公的機関が運営するもの）だけにつながり、旅行会社や宿泊予約アプリのリンクはボタンにしません。",
           "svc": {"bus": "バスタゴ 市外バス", "rail": "KORAIL 韓国鉄道公社", "ferry": "韓国海運組合 旅客船",
                   "citytour": "群山シティツアー", "forest": "山林庁 スプナドゥルe", "camp": "ムニョ島オートキャンプ場",
                   "heli": "スエア航空"}},
    "zh-hans": {"book": "预订", "box": "预订与购票", "nav": "预订",
                "note": "将打开官方预订网站。本网站不接受预订。",
                "about": "本网站不接受预订或付款。景点、指南和路线页面上的“预订”按钮只链接到资料中的官方预订页面（由设施或公共机构运营），"
                         "旅行社和住宿预订应用的链接不会做成按钮。",
                "svc": {"bus": "Bustago 市外巴士", "rail": "KORAIL 韩国铁道公社", "ferry": "韩国海运组合 客轮",
                        "citytour": "群山城市观光巴士", "forest": "山林厅 Sumnadeul-e", "camp": "巫女岛汽车露营场",
                        "heli": "Su Air航空"}},
    "zh-hant": {"book": "預訂", "box": "預訂與購票", "nav": "預訂",
                "note": "將開啟官方預訂網站。本網站不接受預訂。",
                "about": "本網站不接受預訂或付款。景點、指南和路線頁面上的「預訂」按鈕只連結到資料中的官方預訂頁面（由設施或公共機構營運），"
                         "旅行社和住宿預訂應用程式的連結不會做成按鈕。",
                "svc": {"bus": "BusTago 市外巴士", "rail": "KORAIL 韓國鐵道公社", "ferry": "韓國海運組合 客輪",
                        "citytour": "群山城市觀光巴士", "forest": "山林廳 Sumnadeul-e", "camp": "巫女島汽車露營場",
                        "heli": "Su Air航空"}},
    "de": {"book": "Buchen", "box": "Buchung und Tickets", "nav": "Buchung",
           "note": "Zur offiziellen Seite. Diese Website bucht nicht.",
           "about": "Diese Website nimmt keine Buchungen oder Zahlungen an. Die Schaltflächen „Buchen“ auf den Seiten zu Orten, "
                    "Reiseführern und Routen öffnen nur die offiziellen Buchungsseiten aus unseren Daten (betrieben von der "
                    "Einrichtung oder einer öffentlichen Stelle); Links von Reisebüros und Buchungs-Apps werden nie zu Schaltflächen.",
           "svc": {"bus": "Bustago Überlandbusse", "rail": "Korail",
                   "ferry": "Fähren des Koreanischen Schifffahrtsverbands", "citytour": "Stadtrundfahrt Gunsan",
                   "forest": "Sumnadeul-e der Koreanischen Forstverwaltung", "camp": "Auto-Campingplatz Munyeodo",
                   "heli": "Su Air"}},
    "fr": {"book": "Réserver", "box": "Réservations et billets", "nav": "Réservation",
           "note": "Ouvre le site officiel. Ce site ne réserve pas.",
           "about": "Ce site ne prend ni réservation ni paiement. Les boutons « Réserver » des pages de lieux, de guides et de "
                    "circuits ouvrent uniquement les pages de réservation officielles de nos données (gérées par "
                    "l’établissement ou un organisme public) ; les liens des agences de voyage et des applications de "
                    "réservation ne deviennent jamais des boutons.",
           "svc": {"bus": "Bustago, bus interurbains", "rail": "Korail",
                   "ferry": "Ferries de l’Association coréenne des transports maritimes",
                   "citytour": "Bus touristique de Gunsan", "forest": "Sumnadeul-e, Service forestier coréen",
                   "camp": "Camping automobile de Munyeodo", "heli": "Su Air"}},
    "es": {"book": "Reservar", "box": "Reservas y billetes", "nav": "Reservas",
           "note": "Abre la web oficial. Aquí no se reserva.",
           "about": "Este sitio no acepta reservas ni pagos. Los botones «Reservar» de las páginas de lugares, guías y rutas "
                    "solo abren las páginas oficiales de reserva de nuestros datos (gestionadas por el establecimiento o un "
                    "organismo público); los enlaces de agencias de viajes y aplicaciones de reserva nunca se convierten en botones.",
           "svc": {"bus": "Bustago, autobuses interurbanos", "rail": "Korail",
                   "ferry": "Ferris de la Asociación Naviera de Corea", "citytour": "Circuito turístico de Gunsan",
                   "forest": "Sumnadeul-e, Servicio Forestal de Corea", "camp": "Autocamping de Munyeodo",
                   "heli": "Su Air"}},
    "ru": {"book": "Забронировать", "box": "Бронирование и билеты", "nav": "Бронирование",
           "note": "Откроется официальный сайт. Здесь не бронируют.",
           "about": "Этот сайт не принимает бронирования и оплату. Кнопки «Забронировать» на страницах мест, путеводителей и "
                    "маршрутов открывают только официальные страницы бронирования из наших данных (их ведёт само заведение "
                    "или государственная организация); ссылки турагентств и приложений бронирования никогда не становятся кнопками.",
           "svc": {"bus": "Bustago — междугородние автобусы", "rail": "Korail",
                   "ferry": "Паромы Корейской ассоциации судоходства", "citytour": "Сити-тур по Кунсану",
                   "forest": "«Сумнадыль-е» Лесной службы Кореи", "camp": "Автокемпинг Мунёдо",
                   "heli": "Su Air"}},
}

# 공유 (operator 2026-10-17, ui.lnav's share button on place, guide, course and event pages): the button's word, and the
# short note after the link was copied (a screen without the phone's share sheet) or could not be
SHARE_WORDS = {
    "ko": {"label": "공유", "copied": "링크를 복사했습니다", "failed": "링크를 복사하지 못했습니다"},
    "en": {"label": "Share", "copied": "Link copied", "failed": "Couldn't copy the link"},
    "ja": {"label": "共有", "copied": "リンクをコピーしました", "failed": "リンクをコピーできませんでした"},
    "zh-hans": {"label": "分享", "copied": "链接已复制", "failed": "无法复制链接"},
    "zh-hant": {"label": "分享", "copied": "已複製連結", "failed": "無法複製連結"},
    "de": {"label": "Teilen", "copied": "Link kopiert", "failed": "Link konnte nicht kopiert werden"},
    "fr": {"label": "Partager", "copied": "Lien copié", "failed": "Impossible de copier le lien"},
    "es": {"label": "Compartir", "copied": "Enlace copiado", "failed": "No se pudo copiar el enlace"},
    "ru": {"label": "Поделиться", "copied": "Ссылка скопирована", "failed": "Не удалось скопировать ссылку"},
}

# 오늘의 상태 · 오늘의 바다 (the place page's day card, operator 2026-10-31; present.today_vm, templates/_today.html.j2,
# assets/today.js): the card's words in every version. open/closed/hours by kind (attraction, food); {t} a time or time
# range, {d} a duration or distance, {km} the tide station limit, {name} a station's name. 'js' goes into the page's
# JSON for today.js ('지금' line). 'cond' and 'closed_note' are Korean only (the other versions never print the
# source's Korean words). The agencies' names: the sources line of a version (the Korean page prints the data's own).
TODAY_WORDS = {
    "ko": {"title": "오늘의 상태", "title_sea": "오늘의 바다", "pick": "날짜 선택", "chip": "날짜별 계산",
           "open": {"attraction": "문 엽니다", "food": "영업합니다"}, "open_s": {"attraction": "개관", "food": "영업"},
           "closed": {"attraction": "휴관합니다", "food": "쉬는 날입니다"}, "closed_s": {"attraction": "휴관", "food": "휴무"},
           "maybe": "쉬는 날일 수 있습니다", "maybe_s": "확인 필요",
           "maybe_why": "몇째 주·격주 휴무라 이날은 확인이 필요합니다", "if_open": "여는 날이면 {t}",
           "no_hours": "이날 시간은 자료에 없습니다", "no_hours_s": "시간 정보 없음",
           "hours": {"attraction": "이용시간", "food": "영업시간"}, "see_hours": "시간은 아래 '방문 전 확인'에 있습니다",
           "always": "상시 개방", "h24": "24시간", "next_day": "익일 {t}", "cond": "{c} 시간",
           "sec": {"break": "준비시간", "order": "마지막 주문", "entry": "입장 마감"},
           "sunset": "해 지는 시각", "sunrise": "해 뜨는 시각 {t}",
           "crowd": "붐빔 예측", "grades": ("여유", "보통", "붐빔"),
           "crowd_rule": "여유 0~39 · 보통 40~69 · 붐빔 70 이상 — 이 사이트가 나눈 구간",
           "crowd_scale": "이 장소의 가장 붐비는 때 = 100", "crowd_what": "이 장소가 가장 붐비는 때를 100으로 본 상대 예측치입니다. 장소끼리 비교하는 값이 아닙니다.", "crowd_got": "{who} 예측 · {date} 받음", "tide": "물때", "tide_at": "{name} 관측소 · 직선 {d}", "tide_near": "가장 가까운 관측소 · 직선 {d}",
           "high": "만조", "low": "간조", "tide_th": ("물때", "시각", "높이"), "cm": "{n}cm",
           "tide_rule": "바닷가 관광지에만, 가장 가까운 조석 관측소가 직선 {km}km 안일 때 싣습니다. 곡선은 만조·간조의 시각과 "
                        "높이를 이은 것입니다.",
           "beach_open": "해수욕장 개장", "water": "수질", "water_ok": "적합", "water_bad": "부적합",
           "water_year": "{y}년 조사", "beach": "해변", "beach_len": "길이 {n}m", "beach_wid": "폭 {n}m", "sand": "모래", "sun_point": "{name} 지점 값, 섬에서는 1~2분 다를 수 있음", "ferry": "이곳에 들르는 여객선", "ferry_route": "{name} 항로({ports})", "src_ferry": "여객선", "closed_note": "쉬는 날: {text}",
           "note_undated": "명절·공휴일처럼 날짜가 적히지 않은 휴무는 날짜에 넣지 않았습니다.",
           "src": "출처", "src_hours": "이용시간·쉬는 날", "src_sun": "해 뜨고 지는 시각", "src_tide": "물때",
           "src_crowd": "붐빔 예측", "src_beach": "해수욕장", "none": "자료 없음",
           "agency": {"kasi": "한국천문연구원", "khoa": "국립해양조사원", "kto": "한국관광공사", "mof": "해양수산부"},
           "js": {"today": "오늘", "now": "지금 {t}", "left": "{t}까지 {d} 남음", "before": "{t}에 엽니다",
                  "after": "오늘 운영이 끝났습니다", "brk": "지금은 쉬는 시간입니다", "h": "{h}시간", "m": "{m}분",
                  "hm": "{h}시간 {m}분"}},
    "en": {"title": "Today", "title_sea": "The sea today", "pick": "Pick a date", "chip": "Worked out per date",
           "open": {"attraction": "Open", "food": "Open"}, "open_s": {"attraction": "Open", "food": "Open"},
           "closed": {"attraction": "Closed", "food": "Closed"}, "closed_s": {"attraction": "Closed", "food": "Closed"},
           "maybe": "May be closed", "maybe_s": "Check",
           "maybe_why": "Closed on certain weeks of the month or every other week: check before you go",
           "if_open": "If open: {t}", "no_hours": "No hours listed for this day", "no_hours_s": "No hours listed",
           "hours": {"attraction": "Hours", "food": "Hours"}, "see_hours": "See the hours below",
           "always": "Open at all times", "h24": "Open 24 hours", "next_day": "{t} (next day)", "cond": "",
           "sec": {"break": "Break", "order": "Last order", "entry": "Last entry"},
           "sunset": "Sunset", "sunrise": "Sunrise {t}",
           "crowd": "Crowd forecast", "grades": ("Quiet", "Moderate", "Busy"),
           "crowd_rule": "Quiet 0–39 · Moderate 40–69 · Busy 70 and over — bands set by this site",
           "crowd_scale": "100 = this place at its busiest", "crowd_what": "A relative forecast where 100 is this place at its busiest; not for comparing places.", "crowd_got": "Forecast by {who} · received {date}", "tide": "Tides", "tide_at": "{name} station · {d} away", "tide_near": "Nearest station · {d} away",
           "high": "High tide", "low": "Low tide", "tide_th": ("Tide", "Time", "Height"), "cm": "{n} cm",
           "tide_rule": "Shown for seaside places only, when the nearest tide station is within {km} km in a straight "
                        "line. The curve joins the times and heights of high and low tide.",
           "beach_open": "Beach season", "water": "Water quality", "water_ok": "Suitable", "water_bad": "Unsuitable",
           "water_year": "{y} survey", "beach": "Beach", "beach_len": "{n} m long", "beach_wid": "{n} m wide", "sand": "Sand", "sun_point": "values for {name}; on the islands they may differ by a minute or two", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "",
           "note_undated": "Closures without a date (public and lunar holidays) are not marked on the dates.",
           "src": "Sources", "src_hours": "Hours and closed days", "src_sun": "Sunrise and sunset", "src_tide": "Tides",
           "src_crowd": "Crowd forecast", "src_beach": "Beach", "none": "No data",
           "agency": {"kasi": "Korea Astronomy and Space Science Institute",
                      "khoa": "Korea Hydrographic and Oceanographic Agency", "kto": "Korea Tourism Organization",
                      "mof": "Ministry of Oceans and Fisheries"},
           "js": {"today": "Today", "now": "Now {t}", "left": "{d} left until {t}", "before": "Opens at {t}",
                  "after": "Closed for the day", "brk": "On a break now", "h": "{h} h", "m": "{m} min",
                  "hm": "{h} h {m} min"}},
    "ja": {"title": "今日の状況", "title_sea": "今日の海", "pick": "日付を選ぶ", "chip": "日付ごとに計算",
           "open": {"attraction": "開いています", "food": "営業しています"}, "open_s": {"attraction": "開館", "food": "営業"},
           "closed": {"attraction": "休館日です", "food": "定休日です"}, "closed_s": {"attraction": "休館", "food": "休業"},
           "maybe": "休みの可能性があります", "maybe_s": "要確認",
           "maybe_why": "第○週・隔週の休みのため、この日は確認が必要です", "if_open": "開いていれば{t}",
           "no_hours": "この日の時間は資料にありません", "no_hours_s": "時間の記載なし",
           "hours": {"attraction": "利用時間", "food": "営業時間"}, "see_hours": "時間は下の情報をご覧ください",
           "always": "常時開放", "h24": "24時間", "next_day": "翌{t}", "cond": "",
           "sec": {"break": "準備時間", "order": "ラストオーダー", "entry": "入場締切"},
           "sunset": "日の入り", "sunrise": "日の出 {t}",
           "crowd": "混雑予測", "grades": ("空いている", "普通", "混雑"),
           "crowd_rule": "空いている 0〜39・普通 40〜69・混雑 70以上（このサイトが区切った目安）",
           "crowd_scale": "このスポットの最混雑時 = 100", "crowd_what": "このスポットが最も混む時期を100とした相対的な予測値です。スポット同士を比べる値ではありません。", "crowd_got": "{who}の予測・{date}取得", "tide": "潮汐", "tide_at": "{name}観測所・直線{d}", "tide_near": "最寄りの観測所・直線{d}",
           "high": "満潮", "low": "干潮", "tide_th": ("潮", "時刻", "潮位"), "cm": "{n}cm",
           "tide_rule": "海辺のスポットのみ、最寄りの潮汐観測所が直線{km}km以内のときに載せています。曲線は満潮・干潮の時刻と潮位を"
                        "結んだものです。",
           "beach_open": "海水浴場の開場", "water": "水質", "water_ok": "適合", "water_bad": "不適合",
           "water_year": "{y}年の調査", "beach": "浜", "beach_len": "長さ{n}m", "beach_wid": "幅{n}m", "sand": "砂浜", "sun_point": "{name}地点の値。島では1〜2分ずれることがあります", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "", "note_undated": "祝日・旧正月・秋夕など日付のない休みは、日付には反映していません。",
           "src": "出典", "src_hours": "利用時間・休み", "src_sun": "日の出・日の入り", "src_tide": "潮汐",
           "src_crowd": "混雑予測", "src_beach": "海水浴場", "none": "資料なし",
           "agency": {"kasi": "韓国天文研究院", "khoa": "国立海洋調査院", "kto": "韓国観光公社", "mof": "海洋水産部"},
           "js": {"today": "今日", "now": "現在 {t}", "left": "{t}まで あと{d}", "before": "{t}に開きます",
                  "after": "本日の営業は終了しました", "brk": "現在は休憩時間です", "h": "{h}時間", "m": "{m}分",
                  "hm": "{h}時間{m}分"}},
    "zh-hans": {"title": "今日状态", "title_sea": "今日海况", "pick": "选择日期", "chip": "按日期计算",
                "open": {"attraction": "开放", "food": "营业"}, "open_s": {"attraction": "开放", "food": "营业"},
                "closed": {"attraction": "闭馆", "food": "休息"}, "closed_s": {"attraction": "闭馆", "food": "休息"},
                "maybe": "可能休息", "maybe_s": "需确认", "maybe_why": "每月第几周或隔周休息，这一天需要确认",
                "if_open": "如开放：{t}", "no_hours": "资料中没有这一天的时间", "no_hours_s": "无时间资料",
                "hours": {"attraction": "开放时间", "food": "营业时间"}, "see_hours": "时间请见下方信息",
                "always": "全天开放", "h24": "24小时", "next_day": "次日{t}", "cond": "",
                "sec": {"break": "休息时间", "order": "最后点餐", "entry": "停止入场"},
                "sunset": "日落", "sunrise": "日出 {t}",
                "crowd": "拥挤预测", "grades": ("宽松", "一般", "拥挤"),
                "crowd_rule": "宽松 0–39 · 一般 40–69 · 拥挤 70以上（本网站划分的区间）",
                "crowd_scale": "该地最拥挤时 = 100", "crowd_what": "以该地最拥挤的时候为100的相对预测值，不能用来比较不同地点。", "crowd_got": "{who}预测 · {date}获取", "tide": "潮汐", "tide_at": "{name}观测站 · 直线{d}", "tide_near": "最近的观测站 · 直线{d}",
                "high": "满潮", "low": "干潮", "tide_th": ("潮", "时间", "潮高"), "cm": "{n} cm",
                "tide_rule": "仅限海边景点，且最近的潮汐观测站在直线{km}公里以内时显示。曲线连接满潮、干潮的时间和潮高。",
                "beach_open": "海水浴场开放", "water": "水质", "water_ok": "合格", "water_bad": "不合格",
                "water_year": "{y}年调查", "beach": "海滩", "beach_len": "长{n}米", "beach_wid": "宽{n}米", "sand": "沙滩", "sun_point": "{name}地点的数值，岛上可能相差一两分钟", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "", "note_undated": "节假日、春节、中秋等没有具体日期的休息日未标在日期上。",
                "src": "来源", "src_hours": "开放时间·休息日", "src_sun": "日出日落", "src_tide": "潮汐",
                "src_crowd": "拥挤预测", "src_beach": "海水浴场", "none": "无资料",
                "agency": {"kasi": "韩国天文研究院", "khoa": "国立海洋调查院", "kto": "韩国观光公社", "mof": "海洋水产部"},
                "js": {"today": "今天", "now": "现在 {t}", "left": "距{t}还有{d}", "before": "{t}开门",
                       "after": "今天的营业已结束", "brk": "现在是休息时间", "h": "{h}小时", "m": "{m}分钟",
                       "hm": "{h}小时{m}分钟"}},
    "zh-hant": {"title": "今日狀態", "title_sea": "今日海況", "pick": "選擇日期", "chip": "按日期計算",
                "open": {"attraction": "開放", "food": "營業"}, "open_s": {"attraction": "開放", "food": "營業"},
                "closed": {"attraction": "閉館", "food": "休息"}, "closed_s": {"attraction": "閉館", "food": "休息"},
                "maybe": "可能休息", "maybe_s": "需確認", "maybe_why": "每月第幾週或隔週休息，這一天需要確認",
                "if_open": "如開放：{t}", "no_hours": "資料中沒有這一天的時間", "no_hours_s": "無時間資料",
                "hours": {"attraction": "開放時間", "food": "營業時間"}, "see_hours": "時間請見下方資訊",
                "always": "全天開放", "h24": "24小時", "next_day": "次日{t}", "cond": "",
                "sec": {"break": "休息時間", "order": "最後點餐", "entry": "停止入場"},
                "sunset": "日落", "sunrise": "日出 {t}",
                "crowd": "擁擠預測", "grades": ("寬鬆", "一般", "擁擠"),
                "crowd_rule": "寬鬆 0–39 · 一般 40–69 · 擁擠 70以上（本網站劃分的區間）",
                "crowd_scale": "該地最擁擠時 = 100", "crowd_what": "以該地最擁擠的時候為100的相對預測值，不能用來比較不同地點。", "crowd_got": "{who}預測 · {date}取得", "tide": "潮汐", "tide_at": "{name}觀測站 · 直線{d}", "tide_near": "最近的觀測站 · 直線{d}",
                "high": "滿潮", "low": "乾潮", "tide_th": ("潮", "時間", "潮高"), "cm": "{n} cm",
                "tide_rule": "僅限海邊景點，且最近的潮汐觀測站在直線{km}公里以內時顯示。曲線連接滿潮、乾潮的時間和潮高。",
                "beach_open": "海水浴場開放", "water": "水質", "water_ok": "合格", "water_bad": "不合格",
                "water_year": "{y}年調查", "beach": "海灘", "beach_len": "長{n}公尺", "beach_wid": "寬{n}公尺", "sand": "沙灘", "sun_point": "{name}地點的數值，島上可能相差一兩分鐘", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "", "note_undated": "節假日、春節、中秋等沒有具體日期的休息日未標在日期上。",
                "src": "來源", "src_hours": "開放時間·休息日", "src_sun": "日出日落", "src_tide": "潮汐",
                "src_crowd": "擁擠預測", "src_beach": "海水浴場", "none": "無資料",
                "agency": {"kasi": "韓國天文研究院", "khoa": "國立海洋調查院", "kto": "韓國觀光公社", "mof": "海洋水產部"},
                "js": {"today": "今天", "now": "現在 {t}", "left": "距{t}還有{d}", "before": "{t}開門",
                       "after": "今天的營業已結束", "brk": "現在是休息時間", "h": "{h}小時", "m": "{m}分鐘",
                       "hm": "{h}小時{m}分鐘"}},
    "de": {"title": "Heute", "title_sea": "Das Meer heute", "pick": "Datum wählen", "chip": "Je Datum berechnet",
           "open": {"attraction": "Geöffnet", "food": "Geöffnet"}, "open_s": {"attraction": "Geöffnet", "food": "Geöffnet"},
           "closed": {"attraction": "Geschlossen", "food": "Ruhetag"},
           "closed_s": {"attraction": "Geschlossen", "food": "Ruhetag"},
           "maybe": "Möglicherweise geschlossen", "maybe_s": "Prüfen",
           "maybe_why": "Ruhetag nur in bestimmten Wochen des Monats oder alle zwei Wochen – bitte vorher prüfen",
           "if_open": "Falls geöffnet: {t}", "no_hours": "Für diesen Tag sind keine Zeiten angegeben",
           "no_hours_s": "Keine Zeiten", "hours": {"attraction": "Öffnungszeiten", "food": "Öffnungszeiten"},
           "see_hours": "Zeiten siehe unten", "always": "Jederzeit zugänglich", "h24": "24 Stunden geöffnet",
           "next_day": "{t} (Folgetag)", "cond": "",
           "sec": {"break": "Pause", "order": "Letzte Bestellung", "entry": "Letzter Einlass"},
           "sunset": "Sonnenuntergang", "sunrise": "Sonnenaufgang {t}",
           "crowd": "Andrang (Prognose)", "grades": ("Ruhig", "Mittel", "Voll"),
           "crowd_rule": "Ruhig 0–39 · Mittel 40–69 · Voll ab 70 – Stufen dieser Website",
           "crowd_scale": "100 = dieser Ort zur vollsten Zeit", "crowd_what": "Relative Prognose: 100 ist dieser Ort zu seiner vollsten Zeit; kein Vergleichswert zwischen Orten.", "crowd_got": "Prognose: {who} · abgerufen am {date}", "tide": "Gezeiten", "tide_at": "Pegel {name} · {d} Luftlinie", "tide_near": "Nächster Pegel · {d} Luftlinie",
           "high": "Hochwasser", "low": "Niedrigwasser", "tide_th": ("Gezeit", "Zeit", "Höhe"), "cm": "{n} cm",
           "tide_rule": "Nur für Orte am Meer, wenn der nächste Gezeitenpegel höchstens {km} km Luftlinie entfernt ist. "
                        "Die Kurve verbindet die Zeiten und Höhen von Hoch- und Niedrigwasser.",
           "beach_open": "Badesaison", "water": "Wasserqualität", "water_ok": "Geeignet", "water_bad": "Ungeeignet",
           "water_year": "Untersuchung {y}", "beach": "Strand", "beach_len": "{n} m lang", "beach_wid": "{n} m breit", "sand": "Sand", "sun_point": "Werte für {name}; auf den Inseln können sie um ein bis zwei Minuten abweichen", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "",
           "note_undated": "Schließtage ohne Datum (Feiertage, Mondneujahr, Chuseok) sind nicht bei den Daten eingetragen.",
           "src": "Quellen", "src_hours": "Öffnungszeiten und Ruhetage", "src_sun": "Sonnenauf- und -untergang",
           "src_tide": "Gezeiten", "src_crowd": "Andrang", "src_beach": "Strand", "none": "Keine Daten",
           "agency": {"kasi": "Koreanisches Institut für Astronomie und Weltraumforschung (KASI)",
                      "khoa": "Koreanische Behörde für Hydrografie und Ozeanografie (KHOA)",
                      "kto": "Koreanische Tourismusorganisation", "mof": "Ministerium für Ozeane und Fischerei"},
           "js": {"today": "Heute", "now": "Jetzt {t}", "left": "Noch {d} bis {t}", "before": "Öffnet um {t}",
                  "after": "Für heute geschlossen", "brk": "Gerade Pause", "h": "{h} Std.", "m": "{m} Min.",
                  "hm": "{h} Std. {m} Min."}},
    "fr": {"title": "Aujourd’hui", "title_sea": "La mer aujourd’hui", "pick": "Choisir une date",
           "chip": "Calculé pour chaque date",
           "open": {"attraction": "Ouvert", "food": "Ouvert"}, "open_s": {"attraction": "Ouvert", "food": "Ouvert"},
           "closed": {"attraction": "Fermé", "food": "Fermé"}, "closed_s": {"attraction": "Fermé", "food": "Fermé"},
           "maybe": "Peut-être fermé", "maybe_s": "À vérifier",
           "maybe_why": "Fermé certaines semaines du mois ou une semaine sur deux : à vérifier avant de venir",
           "if_open": "S’il est ouvert : {t}", "no_hours": "Aucun horaire indiqué pour ce jour",
           "no_hours_s": "Pas d’horaire", "hours": {"attraction": "Horaires", "food": "Horaires"},
           "see_hours": "Voir les horaires ci-dessous", "always": "Accès libre à toute heure", "h24": "Ouvert 24 h/24",
           "next_day": "{t} (lendemain)", "cond": "",
           "sec": {"break": "Pause", "order": "Dernière commande", "entry": "Dernière entrée"},
           "sunset": "Coucher du soleil", "sunrise": "Lever du soleil {t}",
           "crowd": "Affluence prévue", "grades": ("Calme", "Moyenne", "Forte"),
           "crowd_rule": "Calme 0–39 · Moyenne 40–69 · Forte à partir de 70 — seuils fixés par ce site",
           "crowd_scale": "100 = ce lieu à son affluence maximale", "crowd_what": "Prévision relative : 100 correspond à ce lieu au plus fort de sa fréquentation ; ne sert pas à comparer des lieux.", "crowd_got": "Prévision : {who} · reçue le {date}", "tide": "Marées", "tide_at": "Station de {name} · {d} à vol d’oiseau",
           "tide_near": "Station la plus proche · {d} à vol d’oiseau",
           "high": "Pleine mer", "low": "Basse mer", "tide_th": ("Marée", "Heure", "Hauteur"), "cm": "{n} cm",
           "tide_rule": "Seulement pour les lieux en bord de mer, quand la station marégraphique la plus proche est à "
                        "{km} km au plus à vol d’oiseau. La courbe relie les heures et hauteurs des pleines et basses mers.",
           "beach_open": "Saison de baignade", "water": "Qualité de l’eau", "water_ok": "Conforme",
           "water_bad": "Non conforme", "water_year": "analyses {y}", "beach": "Plage", "beach_len": "{n} m de long", "beach_wid": "{n} m de large", "sand": "Sable", "sun_point": "valeurs pour {name} ; sur les îles, elles peuvent varier d’une ou deux minutes", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "",
           "note_undated": "Les fermetures sans date (jours fériés, Nouvel An lunaire, Chuseok) ne sont pas reportées "
                           "sur les dates.",
           "src": "Sources", "src_hours": "Horaires et jours de fermeture", "src_sun": "Lever et coucher du soleil",
           "src_tide": "Marées", "src_crowd": "Affluence", "src_beach": "Plage", "none": "Pas de données",
           "agency": {"kasi": "Institut coréen d’astronomie et des sciences spatiales (KASI)",
                      "khoa": "Agence coréenne d’hydrographie et d’océanographie (KHOA)",
                      "kto": "Office national du tourisme coréen", "mof": "ministère des Océans et de la Pêche"},
           "js": {"today": "Aujourd’hui", "now": "Il est {t}", "left": "Encore {d} jusqu’à {t}",
                  "before": "Ouvre à {t}", "after": "Fermé pour aujourd’hui", "brk": "Pause en cours", "h": "{h} h",
                  "m": "{m} min", "hm": "{h} h {m} min"}},
    "es": {"title": "Hoy", "title_sea": "El mar hoy", "pick": "Elegir fecha", "chip": "Calculado por fecha",
           "open": {"attraction": "Abierto", "food": "Abierto"}, "open_s": {"attraction": "Abierto", "food": "Abierto"},
           "closed": {"attraction": "Cerrado", "food": "Cerrado"}, "closed_s": {"attraction": "Cerrado", "food": "Cerrado"},
           "maybe": "Puede estar cerrado", "maybe_s": "Comprobar",
           "maybe_why": "Cierra ciertas semanas del mes o cada dos semanas: compruébelo antes de ir",
           "if_open": "Si abre: {t}", "no_hours": "No hay horario indicado para este día", "no_hours_s": "Sin horario",
           "hours": {"attraction": "Horario", "food": "Horario"}, "see_hours": "Vea el horario más abajo",
           "always": "Acceso libre a cualquier hora", "h24": "Abierto 24 horas", "next_day": "{t} (día siguiente)",
           "cond": "", "sec": {"break": "Descanso", "order": "Último pedido", "entry": "Última entrada"},
           "sunset": "Puesta de sol", "sunrise": "Salida del sol {t}",
           "crowd": "Afluencia prevista", "grades": ("Tranquila", "Media", "Alta"),
           "crowd_rule": "Tranquila 0–39 · Media 40–69 · Alta desde 70 — tramos fijados por este sitio",
           "crowd_scale": "100 = este lugar en su momento de más afluencia", "crowd_what": "Previsión relativa: 100 es este lugar en su momento de más afluencia; no sirve para comparar lugares.", "crowd_got": "Previsión: {who} · recibida el {date}", "tide": "Mareas", "tide_at": "Estación de {name} · {d} en línea recta",
           "tide_near": "Estación más cercana · {d} en línea recta",
           "high": "Pleamar", "low": "Bajamar", "tide_th": ("Marea", "Hora", "Altura"), "cm": "{n} cm",
           "tide_rule": "Solo para lugares junto al mar, cuando la estación mareográfica más cercana está a {km} km o "
                        "menos en línea recta. La curva une las horas y alturas de pleamar y bajamar.",
           "beach_open": "Temporada de baño", "water": "Calidad del agua", "water_ok": "Apta", "water_bad": "No apta",
           "water_year": "análisis de {y}", "beach": "Playa", "beach_len": "{n} m de largo", "beach_wid": "{n} m de ancho", "sand": "Arena", "sun_point": "valores de {name}; en las islas pueden variar uno o dos minutos", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "",
           "note_undated": "Los cierres sin fecha (festivos, Año Nuevo lunar, Chuseok) no se marcan en las fechas.",
           "src": "Fuentes", "src_hours": "Horario y días de cierre", "src_sun": "Salida y puesta del sol",
           "src_tide": "Mareas", "src_crowd": "Afluencia", "src_beach": "Playa", "none": "Sin datos",
           "agency": {"kasi": "Instituto Coreano de Astronomía y Ciencias Espaciales (KASI)",
                      "khoa": "Agencia Coreana de Hidrografía y Oceanografía (KHOA)",
                      "kto": "Organización de Turismo de Corea", "mof": "Ministerio de Océanos y Pesca"},
           "js": {"today": "Hoy", "now": "Ahora {t}", "left": "Quedan {d} hasta las {t}", "before": "Abre a las {t}",
                  "after": "Cerrado por hoy", "brk": "Ahora en descanso", "h": "{h} h", "m": "{m} min",
                  "hm": "{h} h {m} min"}},
    "ru": {"title": "Сегодня", "title_sea": "Море сегодня", "pick": "Выбрать дату", "chip": "Рассчитано по датам",
           "open": {"attraction": "Открыто", "food": "Открыто"}, "open_s": {"attraction": "Открыто", "food": "Открыто"},
           "closed": {"attraction": "Закрыто", "food": "Выходной"}, "closed_s": {"attraction": "Закрыто", "food": "Выходной"},
           "maybe": "Возможно, закрыто", "maybe_s": "Уточнить",
           "maybe_why": "Выходной в отдельные недели месяца или раз в две недели — уточните заранее",
           "if_open": "Если открыто: {t}", "no_hours": "Для этого дня часы не указаны", "no_hours_s": "Часы не указаны",
           "hours": {"attraction": "Часы работы", "food": "Часы работы"}, "see_hours": "Часы работы — ниже",
           "always": "Доступ в любое время", "h24": "Круглосуточно", "next_day": "{t} (следующего дня)", "cond": "",
           "sec": {"break": "Перерыв", "order": "Последний заказ", "entry": "Последний вход"},
           "sunset": "Закат", "sunrise": "Восход {t}",
           "crowd": "Прогноз загруженности", "grades": ("Свободно", "Средне", "Многолюдно"),
           "crowd_rule": "Свободно 0–39 · Средне 40–69 · Многолюдно от 70 — границы задал этот сайт",
           "crowd_scale": "100 = это место в самое загруженное время", "crowd_what": "Относительный прогноз: 100 — это место в самое загруженное время; места между собой не сравниваются.", "crowd_got": "Прогноз: {who} · получен {date}", "tide": "Приливы", "tide_at": "Станция {name} · {d} по прямой", "tide_near": "Ближайшая станция · {d} по прямой",
           "high": "Полная вода", "low": "Малая вода", "tide_th": ("Прилив", "Время", "Высота"), "cm": "{n} см",
           "tide_rule": "Только для мест у моря, если ближайшая станция наблюдения за приливами не дальше {km} км по "
                        "прямой. Кривая соединяет время и высоту полной и малой воды.",
           "beach_open": "Купальный сезон", "water": "Качество воды", "water_ok": "Соответствует",
           "water_bad": "Не соответствует", "water_year": "проверка {y} г.", "beach": "Пляж", "beach_len": "длина {n} м", "beach_wid": "ширина {n} м", "sand": "Песок", "sun_point": "данные пункта «{name}»; на островах время может отличаться на минуту-две", "ferry": "", "ferry_route": "", "src_ferry": "", "closed_note": "",
           "note_undated": "Выходные без даты (праздники, Новый год по лунному календарю, Чхусок) на датах не отмечены.",
           "src": "Источники", "src_hours": "Часы работы и выходные", "src_sun": "Восход и закат", "src_tide": "Приливы",
           "src_crowd": "Загруженность", "src_beach": "Пляж", "none": "Нет данных",
           "agency": {"kasi": "Корейский институт астрономии и космических исследований (KASI)",
                      "khoa": "Корейское агентство гидрографии и океанографии (KHOA)",
                      "kto": "Корейская организация по туризму", "mof": "Министерство океанов и рыболовства"},
           "js": {"today": "Сегодня", "now": "Сейчас {t}", "left": "До {t} осталось {d}", "before": "Откроется в {t}",
                  "after": "На сегодня закрыто", "brk": "Сейчас перерыв", "h": "{h} ч", "m": "{m} мин",
                  "hm": "{h} ч {m} мин"}},
}

# 영업 확인 (licenses.json, operator 2026-10-31; present.license_vm): the line in 방문 전 확인 of a place the 행정안전부
# licence records show as operating, and a 식품안심업소 designation still valid — never a grade or stars. {who} the
# agency, {kind} the licence's kind, {a}/{b} the designation's period. The Korean page prints the data's own words.
LICENSE_KINDS = ("일반음식점", "휴게음식점", "제과점영업", "관광식당", "숙박업", "관광숙박업", "관광펜션업", "농어촌민박업",
                 "외국인관광도시민박업", "한옥체험업", "일반야영장업", "자동차야영장업")
LICENSE_WORDS = {
    "ko": {"open": "영업 중", "by": "{who} 인허가({kind})", "by_bare": "{who} 인허가",
           "safe": "식품안심업소 지정({who}, {a}~{b})", "src": "출처",
           "agency": {"행정안전부": "행정안전부", "식품의약품안전처": "식약처", "한국식품안전관리인증원": "한국식품안전관리인증원"},
           "kinds": {k: k for k in LICENSE_KINDS}},
    "en": {"open": "Open for business", "by": "{who} business licence ({kind})", "by_bare": "{who} business licence",
           "safe": "Designated food-safe establishment ({who}, {a} to {b})", "src": "Sources",
           "agency": {"행정안전부": "Ministry of the Interior and Safety", "식품의약품안전처": "Ministry of Food and Drug Safety",
                      "한국식품안전관리인증원": "Korea Agency of HACCP Accreditation and Services"},
           "kinds": dict(zip(LICENSE_KINDS, ("restaurant", "café or snack bar", "bakery", "tourist restaurant", "lodging",
                                             "tourist accommodation", "tourist pension", "rural homestay",
                                             "urban homestay for foreign tourists", "hanok stay", "campground",
                                             "auto campground")))},
    "ja": {"open": "営業中", "by": "{who}の営業許可（{kind}）", "by_bare": "{who}の営業許可",
           "safe": "食品安心店に指定（{who}、{a}〜{b}）", "src": "出典",
           "agency": {"행정안전부": "行政安全部", "식품의약품안전처": "食品医薬品安全処", "한국식품안전관리인증원": "韓国食品安全管理認証院"},
           "kinds": dict(zip(LICENSE_KINDS, ("一般飲食店", "休憩飲食店（カフェ・軽食）", "製菓店", "観光食堂", "宿泊業", "観光宿泊業",
                                             "観光ペンション業", "農漁村民泊業", "外国人観光都市民泊業", "韓屋体験業", "一般キャンプ場",
                                             "オートキャンプ場")))},
    "zh-hans": {"open": "营业中", "by": "{who}营业许可（{kind}）", "by_bare": "{who}营业许可",
                "safe": "被指定为食品安心店（{who}，{a}至{b}）", "src": "来源",
                "agency": {"행정안전부": "行政安全部", "식품의약품안전처": "食品药品安全处", "한국식품안전관리인증원": "韩国食品安全管理认证院"},
                "kinds": dict(zip(LICENSE_KINDS, ("一般餐饮店", "休闲餐饮店（咖啡、小吃）", "面包糕点店", "旅游餐厅", "住宿业", "旅游住宿业",
                                                  "旅游民宿业", "农渔村民宿业", "外国游客城市民宿业", "韩屋体验业", "普通露营地", "汽车露营地")))},
    "zh-hant": {"open": "營業中", "by": "{who}營業許可（{kind}）", "by_bare": "{who}營業許可",
                "safe": "被指定為食品安心店（{who}，{a}至{b}）", "src": "來源",
                "agency": {"행정안전부": "行政安全部", "식품의약품안전처": "食品醫藥品安全處", "한국식품안전관리인증원": "韓國食品安全管理認證院"},
                "kinds": dict(zip(LICENSE_KINDS, ("一般餐飲店", "休閒餐飲店（咖啡、小吃）", "麵包糕點店", "觀光餐廳", "住宿業", "觀光住宿業",
                                                  "觀光民宿業", "農漁村民宿業", "外國遊客城市民宿業", "韓屋體驗業", "一般露營地", "汽車露營地")))},
    "de": {"open": "In Betrieb", "by": "Gewerbeerlaubnis: {who} ({kind})", "by_bare": "Gewerbeerlaubnis: {who}",
           "safe": "Als lebensmittelsicherer Betrieb ausgewiesen ({who}, {a} bis {b})", "src": "Quellen",
           "agency": {"행정안전부": "Ministerium für Inneres und Sicherheit", "식품의약품안전처": "Ministerium für Lebensmittel- und Arzneimittelsicherheit",
                      "한국식품안전관리인증원": "Korea Agency of HACCP Accreditation and Services"},
           "kinds": dict(zip(LICENSE_KINDS, ("Gaststätte", "Café oder Imbiss", "Bäckerei und Konditorei", "Touristenrestaurant",
                                             "Beherbergungsbetrieb", "touristischer Beherbergungsbetrieb", "Touristenpension",
                                             "ländliche Privatunterkunft", "städtische Privatunterkunft für ausländische Gäste",
                                             "Hanok-Unterkunft", "Campingplatz", "Auto-Campingplatz")))},
    "fr": {"open": "En activité", "by": "autorisation d’exploitation : {who} ({kind})", "by_bare": "autorisation d’exploitation : {who}",
           "safe": "Désigné établissement alimentaire sûr ({who}, du {a} au {b})", "src": "Sources",
           "agency": {"행정안전부": "ministère de l’Intérieur et de la Sécurité", "식품의약품안전처": "ministère de la Sécurité des aliments et des médicaments",
                      "한국식품안전관리인증원": "Korea Agency of HACCP Accreditation and Services"},
           "kinds": dict(zip(LICENSE_KINDS, ("restaurant", "café ou snack", "boulangerie-pâtisserie", "restaurant touristique",
                                             "hébergement", "hébergement touristique", "pension touristique", "chambre d’hôtes rurale",
                                             "chambre d’hôtes urbaine pour touristes étrangers", "séjour en hanok", "terrain de camping",
                                             "camping pour véhicules")))},
    "es": {"open": "En actividad", "by": "licencia de actividad: {who} ({kind})", "by_bare": "licencia de actividad: {who}",
           "safe": "Designado establecimiento de alimentos seguros ({who}, del {a} al {b})", "src": "Fuentes",
           "agency": {"행정안전부": "Ministerio del Interior y Seguridad", "식품의약품안전처": "Ministerio de Seguridad de Alimentos y Medicamentos",
                      "한국식품안전관리인증원": "Korea Agency of HACCP Accreditation and Services"},
           "kinds": dict(zip(LICENSE_KINDS, ("restaurante", "cafetería o bar de aperitivos", "panadería y pastelería",
                                             "restaurante turístico", "alojamiento", "alojamiento turístico", "pensión turística",
                                             "alojamiento rural en casa particular",
                                             "alojamiento urbano en casa particular para turistas extranjeros", "alojamiento en hanok",
                                             "camping", "autocamping")))},
    "ru": {"open": "Работает", "by": "лицензия: {who} ({kind})", "by_bare": "лицензия: {who}",
           "safe": "Признано безопасным заведением питания ({who}, с {a} по {b})", "src": "Источники",
           "agency": {"행정안전부": "Министерство внутренних дел и безопасности", "식품의약품안전처": "Министерство безопасности пищевых продуктов и лекарств",
                      "한국식품안전관리인증원": "Korea Agency of HACCP Accreditation and Services"},
           "kinds": dict(zip(LICENSE_KINDS, ("ресторан", "кафе или закусочная", "пекарня-кондитерская", "туристический ресторан",
                                             "средство размещения", "туристическое размещение", "туристический пансион",
                                             "сельский гостевой дом", "городской гостевой дом для иностранных туристов",
                                             "проживание в ханоке", "кемпинг", "автокемпинг")))},
}

# 이어서 많이 간 곳 (related.json, 한국관광공사 관광지별 연관 관광지 정보, operator 2026-10-31; present.related_vm): the
# places cars went to next after this one (TMAP navigation), never a recommendation. {ym} the month of the data, {src}
# the provider (a link).
RELATED_WORDS = {
    "ko": {"title": "이어서 많이 간 곳", "note": "티맵 차량 이동 기준, {ym} · {src}", "ym": "{y}년 {m}월"},
    "en": {"title": "Where visitors drove next", "note": "Car trips in TMAP navigation, {ym} · {src}", "ym": "{mo} {y}",
           "months": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                      "November", "December")},
    "ja": {"title": "このあと多く向かった場所", "note": "TMAPの車での移動による、{ym} · {src}", "ym": "{y}年{m}月"},
    "zh-hans": {"title": "之后最常前往的地方", "note": "根据TMAP车辆行程，{ym} · {src}", "ym": "{y}年{m}月"},
    "zh-hant": {"title": "之後最常前往的地方", "note": "根據TMAP車輛行程，{ym} · {src}", "ym": "{y}年{m}月"},
    "de": {"title": "Wohin Besucher danach am häufigsten fuhren", "note": "Autofahrten laut TMAP-Navigation, {ym} · {src}",
           "ym": "{mo} {y}", "months": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
                                        "Oktober", "November", "Dezember")},
    "fr": {"title": "Où les visiteurs sont le plus allés ensuite",
           "note": "Trajets en voiture selon la navigation TMAP, {ym} · {src}", "ym": "{mo} {y}",
           "months": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                      "novembre", "décembre")},
    "es": {"title": "Adónde fueron después más visitantes",
           "note": "Trayectos en coche según la navegación TMAP, {ym} · {src}", "ym": "{mo} de {y}",
           "months": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                      "noviembre", "diciembre")},
    "ru": {"title": "Куда чаще всего ехали дальше", "note": "По поездкам на машине в навигаторе TMAP, {ym} · {src}",
           "ym": "{mo} {y} г.", "months": ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
                                          "октябрь", "ноябрь", "декабрь")},
}

# The tab panel (operator 2026-10-31 '적용하자' — the approved layout after travel.webforai.kr: from 1200px a panel at
# the left, below it the bar whose menu opens the same groups; templates/_side.html.j2, present.side_vm, en_site
# Pages.side): the groups' names, the wordmark's line, the day card's '다음 행사' and the weather card's words — every
# version, hand-written like COURSES_WORDS so a version never drops out of the build for a missing string.
# The weather card (날씨각's own first-screen card — weather.o2o.kr is the operator's service, operator 2026-10-31 '날씨각
# 실제 디자인으로 … 출처 표기 필요없어 우리 회사 거야'; templates/assets/weather.js): no '출처'/'Source' words. wx_title the
# card's name, wx_go the link a reader without JavaScript (or after a failed answer) gets, wx_more the drawn card's link,
# wx_score the label in the sun / moon, wx_slots the four cells (아침 · 낮 · 저녁 · 밤, the one 날씨각 says it is now
# '지금'), wx_feels · wx_hum the other versions' line of figures (날씨각's own Korean sentences — its bubble, summary and
# status words — show on the Korean pages only), sky the icons' alt words (날씨각's sky keys). {r} the region in the
# version, {t} a temperature ('9°'), {p} a percentage. Korean-only keys (the actions, 가는 법·시간표, 해 뜨고 지는 시각,
# 일출·일몰) live in "ko".
SIDE_WORDS = {
    "ko": {"find": "찾기", "plan": "여행 계획", "events": "행사 달력", "read": "읽을거리", "about": "소개·출처",
           "tagline": "{r} 여행 정보", "next": "다음 행사", "plan_btn": "내 일정 만들기", "courses_btn": "추천 코스",
           "transport": "가는 법·시간표", "sun": "해 뜨고 지는 시각", "sunrise": "일출", "sunset": "일몰",
           "wx_title": "{r} 날씨", "wx_go": "{r} 날씨 보기", "wx_more": "자세히 보기", "wx_score": "지금 날씨 점수",
           "wx_slots": {"morning": "아침", "day": "낮", "sunset": "저녁", "night": "밤", "now": "지금"},
           "wx_feels": "체감 {t}", "wx_hum": "습도 {p}%",
           "sky": {"sun": "맑음", "sun_cloud": "구름 조금", "cloud": "흐림", "rain": "비", "snow": "눈", "moon": "맑음"}},
    "en": {"find": "Find", "plan": "Plan your trip", "events": "Events calendar", "read": "Read",
           "tagline": "{r} travel information", "next": "Next event",
           "wx_title": "{r} weather", "wx_go": "See the weather in {r}", "wx_more": "Details", "wx_score": "Weather score",
           "wx_slots": {"morning": "Morning", "day": "Day", "sunset": "Evening", "night": "Night", "now": "Now"},
           "wx_feels": "Feels like {t}", "wx_hum": "Humidity {p}%",
           "sky": {"sun": "Sunny", "sun_cloud": "Partly cloudy", "cloud": "Cloudy", "rain": "Rain", "snow": "Snow",
                   "moon": "Clear"}},
    "ja": {"find": "探す", "plan": "旅の計画", "events": "イベントカレンダー", "read": "読みもの",
           "tagline": "{r}の旅行情報", "next": "次のイベント",
           "wx_title": "{r}の天気", "wx_go": "{r}の天気を見る", "wx_more": "詳しく見る", "wx_score": "天気スコア",
           "wx_slots": {"morning": "朝", "day": "昼", "sunset": "夕方", "night": "夜", "now": "いま"},
           "wx_feels": "体感 {t}", "wx_hum": "湿度 {p}%",
           "sky": {"sun": "晴れ", "sun_cloud": "晴れ時々くもり", "cloud": "くもり", "rain": "雨", "snow": "雪", "moon": "晴れ"}},
    "zh-hans": {"find": "查找", "plan": "旅行规划", "events": "活动日历", "read": "阅读",
                "tagline": "{r}旅游信息", "next": "下一场活动",
                "wx_title": "{r}天气", "wx_go": "查看{r}天气", "wx_more": "查看详情", "wx_score": "天气评分",
                "wx_slots": {"morning": "早上", "day": "白天", "sunset": "傍晚", "night": "夜间", "now": "现在"},
                "wx_feels": "体感 {t}", "wx_hum": "湿度 {p}%",
                "sky": {"sun": "晴", "sun_cloud": "多云", "cloud": "阴", "rain": "雨", "snow": "雪", "moon": "晴"}},
    "zh-hant": {"find": "查找", "plan": "旅行規劃", "events": "活動日曆", "read": "閱讀",
                "tagline": "{r}旅遊資訊", "next": "下一場活動",
                "wx_title": "{r}天氣", "wx_go": "查看{r}天氣", "wx_more": "查看詳情", "wx_score": "天氣評分",
                "wx_slots": {"morning": "早上", "day": "白天", "sunset": "傍晚", "night": "夜間", "now": "現在"},
                "wx_feels": "體感 {t}", "wx_hum": "濕度 {p}%",
                "sky": {"sun": "晴", "sun_cloud": "多雲", "cloud": "陰", "rain": "雨", "snow": "雪", "moon": "晴"}},
    "de": {"find": "Finden", "plan": "Reise planen", "events": "Veranstaltungskalender", "read": "Lesen",
           "tagline": "Reiseinfos zu {r}", "next": "Nächste Veranstaltung",
           "wx_title": "Wetter in {r}", "wx_go": "Wetter in {r} ansehen", "wx_more": "Details", "wx_score": "Wetter-Score",
           "wx_slots": {"morning": "Morgen", "day": "Mittag", "sunset": "Abend", "night": "Nacht", "now": "Jetzt"},
           "wx_feels": "Gefühlt {t}", "wx_hum": "Luftfeuchte {p} %",
           "sky": {"sun": "Sonnig", "sun_cloud": "Heiter bis wolkig", "cloud": "Bewölkt", "rain": "Regen", "snow": "Schnee",
                   "moon": "Klar"}},
    "fr": {"find": "Trouver", "plan": "Préparer le voyage", "events": "Agenda des événements", "read": "À lire",
           "tagline": "Infos voyage à {r}", "next": "Prochain événement",
           "wx_title": "Météo à {r}", "wx_go": "Voir la météo à {r}", "wx_more": "Détails", "wx_score": "Score météo",
           "wx_slots": {"morning": "Matin", "day": "Midi", "sunset": "Soir", "night": "Nuit", "now": "Actuel"},
           "wx_feels": "Ressenti {t}", "wx_hum": "Humidité {p} %",
           "sky": {"sun": "Ensoleillé", "sun_cloud": "Éclaircies", "cloud": "Nuageux", "rain": "Pluie", "snow": "Neige",
                   "moon": "Dégagé"}},
    "es": {"find": "Buscar", "plan": "Planear el viaje", "events": "Calendario de eventos", "read": "Para leer",
           "tagline": "Información de viaje de {r}", "next": "Próximo evento",
           "wx_title": "El tiempo en {r}", "wx_go": "Ver el tiempo en {r}", "wx_more": "Detalles",
           "wx_score": "Nota del tiempo",
           "wx_slots": {"morning": "Mañana", "day": "Día", "sunset": "Tarde", "night": "Noche", "now": "Ahora"},
           "wx_feels": "Sensación {t}", "wx_hum": "Humedad {p} %",
           "sky": {"sun": "Soleado", "sun_cloud": "Parcialmente nublado", "cloud": "Nublado", "rain": "Lluvia",
                   "snow": "Nieve", "moon": "Despejado"}},
    "ru": {"find": "Найти", "plan": "План поездки", "events": "Календарь событий", "read": "Почитать",
           "tagline": "{r}: информация для поездки", "next": "Ближайшее событие",
           "wx_title": "Погода: {r}", "wx_go": "Смотреть погоду: {r}", "wx_more": "Подробнее", "wx_score": "Оценка погоды",
           "wx_slots": {"morning": "Утро", "day": "День", "sunset": "Вечер", "night": "Ночь", "now": "Сейчас"},
           "wx_feels": "Ощущается как {t}", "wx_hum": "Влажность {p} %",
           "sky": {"sun": "Солнечно", "sun_cloud": "Переменная облачность", "cloud": "Облачно", "rain": "Дождь",
                   "snow": "Снег", "moon": "Ясно"}},
}
SIDE_KEYS = ("find", "plan", "events", "read", "tagline", "next", "wx_title", "wx_go", "wx_more", "wx_score", "wx_slots",
             "wx_feels", "wx_hum", "sky")   # every version has these (tests/test_sidebar_layout.py)
