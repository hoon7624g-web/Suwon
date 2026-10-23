"""Site assistant knowledge (owner decision 2026-10-16, CLAUDE.md 3.10): the files api/chat.js answers from, written
by pipeline.build under <out>/chat/ in every mode (public/chat/ in the public build; vercel.json bundles public/chat/**
with the function through functions.includeFiles). The layout is the first city's chatbot's; every city value — the
site, its name, the region's name in each language, the assistant's name, the extra origins the function accepts —
comes from site.json (`site_url`, `site_name`, `region`, and the `chatbot` object: chat_config).

    catalog.txt  one compact line per page the site publishes: places, guides, courses, event series, video topic
                 pages, theme and site pages. A place line carries its name (English name, other names), type, 구·군
                 and only the most asked first-screen facts (CATALOG_SLOTS, as present.key_facts gives them, both
                 values with their providers where two sources differ) — the rest is in docs.json. It is the cached
                 part of the system prompt: deterministic (sorted, no build date) and under CATALOG_BUDGET estimated
                 tokens (estimate_tokens) so the cached prefix stays well inside the cheaper price tier.
    docs.json    {v, site, meta, docs: {key: {t title, k kind, e English path, l {hreflang: that version's path}, n
                 {hreflang: that version's name}, u page, h heading, a other names, x text}}, alias, ext}: what
                 get_pages returns. key = the page path (a guide section: the guide path + '#h-b<n>', the section's
                 anchor on the page; a video: 'video:<id>' with u = the topic page that lists it). x = every fact with
                 its source, the address it came from and 출처 확인일, both values where sources differ, FAQ, nearby
                 public parking, bus stops and stations, guide sections, course stops and values, event editions.
                 meta = the city values the function needs (chat_meta): the site, its names, the region and the
                 assistant in each language, the extra origins. alias maps every version's path to its key; ext lists
                 the outside addresses the data links to (the only outside links an answer may carry).
    index.json   {v, docs: {key: [title tokens, body tokens]}} for search_site (tokens(): Hangul and CJK bigrams,
                 Latin / Cyrillic / digit words; chatbot/knowledge.js tokenizes queries the same way).

Facts come only from the records and helpers the pages use (CLAUDE.md 3.1, 3.2). Never included: TourAPI overview text
(3.4), a city office's original text, photos. Single videos are not catalog lines: the catalog lists the video topic
pages, docs/index hold every video.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

from . import fee_table, jsonld, notices, plan, present, tickets
from .schema import FACT_ORDER, FIT_ORDER, KIND_LABELS, designations, food_class
from .romanize import romanize
from .textutil import display_address, squash_ws, web_url

CHAT_DIR = "chat"
VERSION = 1
# estimated tokens (estimate_tokens) of catalog.txt. estimate_tokens counts about a third fewer tokens than Haiku 5.5's
# tokenizer (measured on the first city's catalog: 68.7K estimated = ~93K real with the rules and tools). The operator
# set 100K estimated (2026-10-17 '상한을 10만으로 해', after 153 stays were published; 50K before): a catalog near it
# makes the cached prefix (tools + rules + catalog) cost more per question — the warning says when it is crossed
CATALOG_BUDGET = 100_000
DOC_LIMIT = 9_000            # characters of one doc's text (get_pages caps what it returns again, chatbot/knowledge.js)
GUIDE_DOC_FIT = 5_800        # a guide doc longer than this (get_pages reads 6,000) gives its places and FAQ docs of their own
KIND_ORDER = ("attraction", "food", "stay")
KIND_HEAD = {"attraction": "관광지", "food": "음식점", "stay": "숙소"}
# the first-screen facts a place line carries, per kind (present.key_facts slot keys): what travellers ask most and
# lists filter by — closed days, admission fee, signature dishes. Hours, parking, phone, check-in and the rest are in
# the place's doc (get_pages); with all of them the catalog would pass its budget (852 places)
CATALOG_SLOTS = {"attraction": ("closed", "fee"), "food": ("menu", "closed"), "stay": ()}
GUIDE_LINE_MAX = 100         # a guide's short answer, an event's usual timing
SEP = " | "
# the languages the assistant speaks to (chatbot/prompt.js LANGS; the site's versions when they exist)
LANGS = ("ko", "en", "ja", "zh-Hans", "zh-Hant", "de", "fr", "es", "ru")
ORIGIN_RX = re.compile(r"^https://[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
CHIPS_MAX = 6


# ---------------------------------------------------------------- the city's chatbot settings (site.json chatbot)
def _per_lang(value) -> dict[str, str]:
    """{lang: text} of a site.json chatbot entry, the languages of LANGS only, blanks dropped."""
    value = value if isinstance(value, dict) else {}
    return {k: squash_ws(value.get(k)) for k in LANGS if isinstance(value.get(k), str) and squash_ws(value.get(k))}


def chat_config(site: dict) -> dict:
    """The assistant's city values from site.json, with neutral fallbacks so a city without a `chatbot` object (the
    sample data) still builds: {region {lang: name}, assistant {lang: name}, chips {lang: [questions]}, origins [https
    origins]}. region: chatbot.region_names, else site.json region / region_en; assistant: chatbot.assistant_name,
    else '<region> 여행 도우미' / '<region> travel helper'; chips: the example questions each language's chat shows
    (none when not configured); origins: chatbot.production_aliases + previous_sites (an origin is https://host,
    nothing else is kept)."""
    c = site.get("chatbot") if isinstance(site.get("chatbot"), dict) else {}
    region = {"ko": squash_ws(site.get("region")), "en": squash_ws(site.get("region_en")) or squash_ws(site.get("region"))}
    region.update(_per_lang(c.get("region_names")))
    assistant = {"ko": f"{region['ko']} 여행 도우미".strip(), "en": f"{region['en']} travel helper".strip()}
    assistant.update(_per_lang(c.get("assistant_name")))
    chips = {}
    for lang, qs in (c.get("chips") if isinstance(c.get("chips"), dict) else {}).items():
        if lang in LANGS and isinstance(qs, list):
            keep = [squash_ws(q) for q in qs if isinstance(q, str) and squash_ws(q)][:CHIPS_MAX]
            if keep:
                chips[lang] = keep
    origins = []
    for key in ("production_aliases", "previous_sites"):
        for o in c.get(key) or []:
            o = squash_ws(o).rstrip("/").lower() if isinstance(o, str) else ""
            if ORIGIN_RX.match(o) and o not in origins:
                origins.append(o)
    return {"region": region, "assistant": assistant, "chips": chips, "origins": origins}


def chat_meta(site: dict) -> dict:
    """docs.json meta: what chatbot/server.js and prompt.js need of the city — the public address (the origin
    allow-list starts with it, links are checked against it), the site's names, the region and the assistant in each
    language, the extra origins (production alias, previous public address), and the short emergency numbers of
    site.json emergency when there is one (tel: the only short tel: links an answer keeps)."""
    cfg = chat_config(site)
    em = site.get("emergency") if isinstance(site.get("emergency"), dict) else {}
    tel = [re.sub(r"[^\d+]", "", str(x.get("tel") or "")) for x in em.get("lines") or [] if isinstance(x, dict)]
    return {"site": squash_ws(site.get("site_url")).rstrip("/"), "site_name": squash_ws(site.get("site_name")),
            "site_name_en": squash_ws(site.get("site_name_en")), "region": cfg["region"],
            "assistant": cfg["assistant"], "origins": cfg["origins"],
            # the short numbers of site.json emergency (when there is one): the only short tel: links an answer keeps
            "tel": [t for t in dict.fromkeys(tel) if re.fullmatch(r"\+?\d{3,15}", t)]}


def ui_config(site: dict, lang: str = "ko") -> dict:
    """The browser's part (templates/_chat.html.j2 puts it on the launcher as data-chat, chat.js reads it): the site
    address (a link to it opens on the deployment the reader is on), the assistant's name and the region's name in the
    page's language (else English), and that language's example questions (none when not configured)."""
    cfg = chat_config(site)
    lang = next((x for x in LANGS if x.lower() == str(lang or "").lower()), "en")
    pick = lambda d: d.get(lang) or d.get("en") or d.get("ko", "")
    return {"site": squash_ws(site.get("site_url")).rstrip("/"), "name": pick(cfg["assistant"]),
            "region": pick(cfg["region"]), "chips": cfg["chips"].get(lang, [])}


# ---------------------------------------------------------------- tokens (search) and the token estimate (budget)
TOKEN_RX = re.compile(r"[가-힣]+|[぀-ヿ㐀-鿿]+|[a-z0-9À-ɏЀ-ӿ]+")


def tokens(text: str | None) -> list[str]:
    """Search tokens in first-seen order, each once: Hangul / kana / CJK runs as bigrams (a one-syllable run as
    itself), Latin, Cyrillic and digit runs as words (one-letter Latin words dropped). NFKC + lower case.
    chatbot/knowledge.js tokens() is the same function for queries — keep the two in step."""
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    out: list[str] = []
    seen: set[str] = set()
    for run in TOKEN_RX.findall(t):
        if run[0] >= "぀":
            grams = [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
        else:
            grams = [run] if len(run) > 1 or run.isdigit() else []
        for g in grams:
            if g not in seen:
                seen.add(g)
                out.append(g)
    return out


def estimate_tokens(text: str) -> int:
    """A tokenizer-free estimate of Claude's token count: a Hangul syllable, kana, CJK or any other non-ASCII character
    counts 1.0, ASCII 1 per 2.5 characters. It runs about a third under Haiku 5.5's real count (the first city's
    catalog: 68.7K estimated, ~93K real with rules and tools); CATALOG_BUDGET allows for that. The real count is in the
    function log (cache_creation_input_tokens / cache_read_input_tokens)."""
    wide = sum(1 for ch in text if ord(ch) > 127)
    ascii_ = len(text) - wide
    return int(math.ceil(wide + ascii_ / 2.5))


# ---------------------------------------------------------------- small helpers
# a month range written with the first 월 left out ('3~10월 09:00~18:00'): the first city's model read it as days of
# one month in a Spanish answer ('3–10 de octubre', review 2026-10-17 L08). The docs, the catalog and the facts
# check_plan reads (plan_facts) name both months ('3월~10월', the form chatbot/knowledge.js checkPlan reads a season by)
MONTH_RANGE = re.compile(r"(?<![\d.\-/월])(1[0-2]|[1-9])\s*~\s*(1[0-2]|[1-9])월")


def month_ranges(text: str) -> str:
    return MONTH_RANGE.sub(r"\1월~\2월", text)


def _clean(text) -> str:
    return squash_ws(str(text or "").replace("\n", " "))


def _short_line(text: str, limit: int = GUIDE_LINE_MAX) -> str:
    """A catalog summary: the text whole when it is short, else cut after an item or a clause (' …') — never inside
    a value."""
    s = _clean(text)
    if len(s) <= limit:
        return s
    cut = max(s.rfind(m, 0, limit) for m in (" · ", ", ", "고 ", "며 "))
    return (s[:cut].rstrip(" ,·") if cut > limit // 2 else s[:limit].rsplit(" ", 1)[0]) + " …"


def _when(iso: str | None) -> str:
    return squash_ws(iso)[:10]


def _period(ev: dict) -> str:
    start, end = _when(ev.get("start_date")), _when(ev.get("end_date"))
    if not start:
        return _clean(ev.get("period_text"))
    if end and end != start:
        return f"{start}~{end[5:] if end[:4] == start[:4] else end}"
    if not end and re.fullmatch(r"\d{4}-\d{2}", ev.get("end_month") or ""):
        return f"{start}~{ev['end_month']}"
    return start


def _src(src: dict | None, url: str = "") -> str:
    """'한국관광공사 TourAPI (출처 확인 2026-10-10)', '<facility> 누리집 https://… (출처 확인 …)': the provider, the exact
    address the value came from when the data has one, and the date this site last checked that source (출처 확인 —
    not a page review date)."""
    src = src or {}
    p = _clean(src.get("provider")) or "출처 미기재"
    d = _clean(src.get("checked_at"))
    return p + (f" {url}" if url else "") + (f" (출처 확인 {d})" if d else "")


def _fact_url(e: dict, src: dict | None, site: dict | None = None) -> str:
    """The address one fact's value came from: the source's own URL, else — for a value from the city's tourism site
    (site.json source.name) — the place's 원문 page (the page the importer read), else ''. TourAPI values come from an
    API and have no page of their own."""
    src = src or {}
    url = web_url(src.get("url")) if src.get("url") else ""
    if url:
        return url
    own = _clean(((site or {}).get("source") or {}).get("name"))
    orig, official = e.get("original") or {}, e.get("official") or {}
    if own and _clean(src.get("provider")).startswith(own):
        return web_url(orig.get("source_url") or official.get("source_url") or "")
    return ""


def _dates(checked: str = "", reviewed: str = "", approved: str = "", checked_label: str = "출처 확인") -> str:
    """The page's dates, each named for what it is: when this site last checked the sources (출처 확인), when a person
    reviewed the page (페이지 검수 — none yet means '검수 전'), when the operator approved publishing it."""
    parts = [f"{checked_label} {checked}" if checked else "", f"페이지 검수 {reviewed}" if reviewed else "페이지 검수 전(검수일 없음)",
             f"운영자 공개 승인 {approved}" if approved else ""]
    return "날짜: " + " · ".join(p for p in parts if p)


URL_RX = re.compile(r"https?://\S+")
SHORT_LABEL = {"이용시간": "시간", "영업시간": "시간", "쉬는 날": "휴무", "대표 메뉴": "메뉴", "주차 요금": "주차요금"}
SLOT_MAX = 40                # a slot value longer than this is cut after an item (' 외'); get_pages has it whole


def _cap(text: str, limit: int) -> str:
    """Cut a long value after a whole item (', ' · ' / ' · '; ') and mark it ' 외' — never inside an item."""
    if len(text) <= limit:
        return text
    cut = max(text.rfind(m, 0, limit) for m in (", ", " / ", "; ", " - ", " · "))
    return (text[:cut] if cut > 8 else text[:limit].rsplit(" ", 1)[0]).rstrip(" ,/;-·") + " 외"


def _letters(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _slot_text(s: dict) -> str:
    """A key-fact slot as the first screen gives it, with a short label ('휴무 매주 월요일'); a conflict names both
    providers ('요금 두 출처 다름: 한국관광공사 무료 / 공식 홈페이지 성인 1,000원')."""
    def one(v):
        t = _clean(v.get("main"))
        if v.get("sub"):
            t += f", {_clean(v['sub'])}"
        t = _cap(t, SLOT_MAX)
        if v.get("more") and not t.endswith(" 외"):
            t += " 외"
        return t
    label = SHORT_LABEL.get(s["label"], s["label"])
    if s.get("conflict"):
        return f"{label} 두 출처 다름: " + " / ".join(f"{v.get('provider') or '출처'} {one(v)}" for v in s["vals"])
    text = one(s)
    if text == "연중무휴":   # the value names itself (open all year): no label (CATALOG_BUDGET, the header says so)
        return text
    return f"{label} {text}"


def _versions(S) -> list[tuple[str, object]]:
    """[(hreflang, site)] of the site's other language versions: every version when the build knows several
    (S.intl.sites), else the English one (S.en), else none."""
    intl = getattr(S, "intl", None)
    if intl is not None and getattr(intl, "sites", None):
        return [(site.loc.html, site) for site in intl.sites.values()]
    en = getattr(S, "en", None)
    return [("en", en)] if en is not None else []


class Knowledge:
    """Everything the three files hold, computed from a build State (pipeline.build.State, S.en loaded)."""

    def __init__(self, S):
        self.S = S
        self.site = S.site_url
        self.meta = chat_meta(S.site)
        en = getattr(S, "en", None)
        self.ko2en = dict(getattr(en, "ko2en", {}) or {})
        self.event_en = dict(getattr(en, "event_links", {}) or {})
        self.en_names = {p["e"]["id"]: p["name"] for p in (getattr(en, "places", {}) or {}).values()}
        # the catalog line names the English form only where it is more than the Korean read aloud: an attraction (its
        # generic part in English: 'Seomun Market') or the provider's own English title; a restaurant's or a stay's
        # guideline name is the Korean romanized, which the model reads from the Korean (CATALOG_BUDGET). Every
        # place's doc keeps its English name.
        self.en_line_names = {p["e"]["id"]: p["name"] for p in (getattr(en, "places", {}) or {}).values()
                              if (p["e"].get("kind") == "attraction"
                                  or str((p.get("rec") or {}).get("name_en_source", "")).startswith("TourAPI"))
                              and _letters(p["name"]) != _letters(romanize(p["e"]["name"]))}
        # every version's twin of a Korean page, its path and name: a reader of that language opens that page and
        # sees its name on the link card (chatbot/knowledge.js pathFor, fixLinks); ko path → {hreflang: [path, name]}
        self.twins: dict[str, dict[str, list[str]]] = {}
        for hl, site in _versions(S):
            names = {p["e"]["_path"]: p["name"] for p in (site.places or {}).values()}
            names.update({x["g"]["_path"]: squash_ws(x["rec"].get("title")) for x in (site.guides or {}).values()})
            names.update({x["c"]["_path"]: squash_ws(x["rec"].get("name")) for x in (site.courses or {}).values()})
            # an event series opens <home>events/#anchor there: its card carries the series' name in that language
            by_slug = {x["slug"]: x for x in getattr(site, "series", None) or []}
            names.update({sr["_path"]: squash_ws(by_slug[sr["slug"]]["rec"].get("series_name"))
                          for sr in getattr(S, "series", None) or [] if sr["slug"] in by_slug})
            for ko, path in {**(getattr(site, "event_links", {}) or {}), **(site.ko2en or {})}.items():
                self.twins.setdefault(ko, {})[hl] = [path, names.get(ko, "")]
        self.lines: list[str] = []
        self.docs: dict[str, dict] = {}
        self.ext: set[str] = set()
        self.video_topic: dict[str, dict] = {}

    # -- paths
    def en_path(self, ko_path: str) -> str:
        return self.ko2en.get(ko_path) or ""

    def keep_url(self, *urls) -> None:
        for u in urls:
            u = web_url(u) if u else ""
            if u.startswith(("http://", "https://")) and not u.startswith(self.site):
                self.ext.add(u)

    def add_doc(self, key: str, title: str, kind: str, text: str, en: str = "", page: str = "", head: str = "",
                alt: list[str] | None = None) -> None:
        text = month_ranges(text.strip())
        if len(text) > DOC_LIMIT:
            text = text[:DOC_LIMIT].rsplit("\n", 1)[0] + "\n… (이하 생략: 전체는 페이지에서)"
        doc = {"t": title, "k": kind, "x": text}
        if en:
            doc["e"] = en
        twins = self.twins.get(key) if "#" not in key else None   # a guide section opens its guide's twin + anchor
        if twins:
            doc["l"] = {h: v[0] for h, v in twins.items()}
            if any(v[1] for v in twins.values()):
                doc["n"] = {h: v[1] for h, v in twins.items() if v[1]}
        if page:
            doc["u"] = page
        if head:   # a guide section's own heading: the title of its link card
            doc["h"] = head
        if alt:    # a place's other names (the page lists them under its name): search and get_pages show them by the title
            doc["a"] = list(alt)
        self.docs[key] = doc

    # -- build
    def build(self) -> "Knowledge":
        S = self.S
        self.video_topic = {v["youtube_id"]: g for g in S.video_groups for v in g["items"]}
        slots = "; ".join(f"{KIND_HEAD[k]}: " + (", ".join(SHORT_LABEL.get(present.SLOT_LABEL[n], present.SLOT_LABEL[n])
                                                            for n in CATALOG_SLOTS[k]) or "없음") for k in KIND_ORDER)
        out = [
            f"# Site catalog of {self.meta['site_name']} ({self.site}). One line = one page of this site.",
            "# Line letter: P place, G guide, C course, E event series, V video topic page, T theme list, S site page. "
            f"The second field is the page path: pass it to get_pages as is, and link the page as {self.site} + path. "
            "A name in brackets is the place's English name (attractions and official English names; any other "
            "place's English name is its Korean name romanized, and its page has it); '다른 이름' = other names of the "
            "same place; '연중무휴' alone = open all year.",
            "# A place line is short: name, type, 구·군 (the district of its address) and only these first-screen facts "
            f"— {slots} (휴무 = closed days, 요금 = admission fee, 메뉴 = signature dishes). A fact missing from a line is "
            "not evidence that the site lacks it: hours, parking, phone, check-in, the full fee table and the sources "
            "are in the place's page (get_pages). '외' = the page has more. '두 출처 다름' = two sources give different "
            "values and the page shows both (방문 전 전화 확인). 지정 = official designations the page lists.",
            "",
        ]
        for kind in KIND_ORDER:
            items = sorted(S.lists.get(kind) or [], key=lambda e: present.name_key(e["name"]))
            if not items:
                continue
            out.append(f"## {KIND_HEAD[kind]} {len(items)}곳 — 목록 {present.LIST_PATH[kind]}")
            out += [self.place(e) for e in items]
            out.append("")
        if S.guides:
            out.append(f"## 가이드 {len(S.guides)}편 — 목록 /guides/ (제목이 답하는 질문, 그다음 짧은 답)")
            out += [self.guide(g) for g in sorted(S.guides, key=lambda g: g["id"])]
            out.append("")
        if S.courses:
            out.append(f"## 여행 코스 {len(S.courses)}개 — 목록 /courses/")
            out += [self.course(c) for c in sorted(S.courses, key=lambda c: c["id"])]
            out.append("")
        if S.series:
            out.append(f"## 행사·축제 {len(S.series)}개 (회차 날짜는 정확한 값, 오늘 기준 진행·예정·종료는 직접 판단) — 목록 /events/")
            out += [self.series(sr) for sr in sorted(S.series, key=lambda sr: sr["slug"])]
            out.append("")
        for v in S.videos:
            self.video(v)
        if S.video_groups:
            out.append(f"## 영상 {len(S.videos)}편 — 주제별 페이지 (영상 하나하나는 search_site로 찾는다)")
            out += [self.video_page(g) for g in S.video_groups]
            out.append("")
        if S.abroad:
            out.append(self.abroad_section())
            out.append("")
        notes = getattr(S, "service_notices", None) or []
        if notes:
            # official notices that belong to no place page (pipeline/notices.py service notices): the post is the
            # source to cite
            out.append(f"## 공식 공지 {len(notes)}건 (장소 페이지가 없는 서비스·운영 변경 — 답에는 공지 글 주소를 출처로)")
            for n in notes:
                a, b = notices.span(n)
                when = a if a == b else f"{a}~{b}"
                out.append(SEP.join(["N " + _clean(n.get("subject")), f"{when} {_clean(n.get('note'))}",
                                     f"{_clean(n.get('provider'))} {n.get('url')} (확인 {_clean(n.get('checked_at'))})"]))
                self.keep_url(n.get("url"))
            out.append("")
        out.append("## 테마와 사이트 페이지")
        out += self.theme_lines() + self.site_pages()
        self.lines = out
        self.keep_url((S.site.get("source") or {}).get("url"), *(l.get("url") for l in S.site.get("official_links") or []))
        return self

    # -- places
    def place(self, e: dict) -> str:
        name = e["name"]
        en_name = self.en_names.get(e["id"], "")
        line_name = self.en_line_names.get(e["id"], "")
        title = f"{name} ({line_name})" if line_name else name
        alt = jsonld.alternate_names(e)
        if alt:   # the other names the page lists under its name: an old and a new name, a building and what is in it
            title += " · 다른 이름 " + ", ".join(alt)
        kf = {s["key"]: s for s in present.key_facts(e, "hero")["slots"]}
        facts = "; ".join(_slot_text(kf[n]) for n in CATALOG_SLOTS.get(e["kind"], ()) if n in kf)
        ds = designations(e, city=self.S.city)
        district = e.get("_district") or ""
        parts = [f"P {e['_path']}", title, e.get("_type") or food_class(e), district, facts,
                 "지정 " + "·".join(d["short"] for d in ds) if ds else ""]
        self.place_doc(e, self.en_path(e["_path"]), en_name)
        return SEP.join(p for p in parts if p)

    def place_doc(self, e: dict, en: str, en_name: str) -> None:
        from . import build as B
        S = self.S
        L = [f"{e['name']} — {KIND_LABELS.get(e['kind'], '')}{' · ' + e['_type'] if e.get('_type') else ''}"
             + (f" (English: {en_name})" if en_name else "")]
        alt = jsonld.alternate_names(e)
        if alt:
            L.append("다른 이름: " + ", ".join(alt))
        where = [x for x in (e.get("_place_label"),
                             f"{e['_region']} 권역" if S.city.region_mode != "district"
                             and e.get("_region") not in (None, "", S.city.none_label) else "") if x]
        if where:
            L.append("위치: " + " · ".join(where))
        if e.get("summary"):
            L.append("요약: " + _clean(e["summary"]))
        for d in e.get("details") or []:
            L.append(f"{_clean(d.get('heading'))}: {present.decaution(_clean(d.get('text')))}")
        L.append("정보(값 — 출처, 그 값을 가져온 주소, 출처 확인일 = 이 사이트가 그 출처를 확인한 날):")
        for k in FACT_ORDER + FIT_ORDER:
            row = B.fact_row(e, k)
            if not row:
                continue
            if row["value"]:
                url = _fact_url(e, row["source"], S.site)
                L.append(f"- {row['label']}: {_clean(row['value'])} — {_src(row['source'], url)}")
                self.keep_url(url)
                if k in ("homepage", "reservationurl"):
                    self.keep_url(row["value"])
            for a in row["alternatives"]:
                tag = "추가 값" if a["also"] else "다른 출처 값"
                url = _fact_url(e, a, S.site)
                line = f"- {row['label']}({tag}): {_clean(a['value'])} — {_src(a, url)}"
                if a.get("note"):
                    line += f" [{_clean(a['note'])}]"
                self.keep_url(url)
                if not a["also"]:
                    line += " → 출처마다 값이 달라 방문 전 전화 확인"
                L.append(line)
            if k == "usefee":
                # the combined tickets that open this place (data/<region>/tickets.json, pipeline/tickets.py)
                L += tickets.place_lines(getattr(S, "tickets", None) or {}, e, self.place_ref,
                                         plan.plan_config(S.site)["resident_label"])
        L.append(_dates(B.facts_checked_date(e), _clean(e.get("reviewed_at")), _clean(e.get("approved_at"))))
        kf = present.key_facts(e, "hero")
        if kf["missing"]:
            L.append("사이트에 없는 값(확인 필요): " + "·".join(kf["missing"]))
        # dated notices of the facility (pipeline/notices.py; only those still shown, i.e. until ≥ the build date): a
        # question about one of these dates is answered from them, with the provider's post as the link
        for row in e.get("_notices") or []:
            n = row["n"]
            L.append(f"- 날짜별 공지: {row['text']} — {_src({'provider': n['provider'], 'checked_at': n['checked_at']}, n['url'])}"
                     f" (이 공지는 {n['until']}까지 표시; 그 밖의 날은 위 이용시간·쉬는 날)")
            self.keep_url(n["url"])
        for d in designations(e, city=S.city):
            L.append(f"- 지정: {d['label']} (출처: {_clean(d.get('source_name'))} {d.get('url') or ''})".rstrip())
            self.keep_url(d.get("url"))
        faqs = [x for x in e.get("faq") or [] if x.get("q") and x.get("a")]
        if faqs:
            L.append("자주 묻는 질문:")
            L += [f"- Q {_clean(x['q'])} A {present.decaution(_clean(x['a']))}" for x in faqs]
        acc = present.access_vm(S, e)
        if acc:
            if acc["lots"]:
                L.append(f"근처 공영주차장(직선 {acc['radius']}m 안): " + "; ".join(self._lot(l) for l in acc["lots"]))
            if acc["stops"]:
                L.append(f"가까운 버스 정류장(직선 {acc['bus_radius']}m 안): " + "; ".join(
                    f"{s['name']} {s['m']}m" + (f" (노선 {s['routes_text']})" if s["routes_text"] else "") for s in acc["stops"]))
            if acc["rails"]:
                L.append(f"가까운 {acc['rail_label']}(가장 가까운 출구까지 직선 {acc['rail_radius']}m 안): " + "; ".join(
                    f"{r['name']}" + (f"({r['lines_text']})" if r["lines_text"] else "")
                    + (f" {r['exit']}번 출구" if r["exit"] else "") + f" {r['m']}m" for r in acc["rails"]))
            L.append("출처: " + "; ".join(self._access_source(name) for name in acc["sources"]))
        near = []
        for n in e.get("nearby") or []:
            t = S.ent_by_slug.get(n.get("internal_slug") or "") or S.ent_by_cid.get(str(n.get("contentid")))
            if t and n.get("distance_m") is not None:
                near.append(f"{t['name']} {t['_path']} 직선 {present.dist(n['distance_m'])}")
        if near:
            L.append("가까운 장소: " + "; ".join(near))
        if e.get("_courses"):
            L.append("이 장소가 나오는 코스: " + "; ".join(f"{present.course_display(c['name'])} {c['_path']}" for c in e["_courses"]))
        if e.get("_guides"):
            L.append("이 장소가 나오는 가이드: " + "; ".join(f"{_clean(g['title'])} {g['_path']}"
                                                   for g in self._unique(e["_guides"])))
        if e.get("_events"):
            L.append("이 장소의 행사: " + "; ".join(f"{sr['name']} {sr['_path']}" for sr in e["_events"]))
        vids = [v for v in S.videos if e["slug"] in (v.get("place_slugs") or [])]
        if vids:
            L.append(f"영상 {len(vids)}편: " + "; ".join(f"{_clean(v.get('title'))} — {_clean(v.get('channel'))}" for v in vids[:5]))
        orig, official = e.get("original") or {}, e.get("official") or {}
        links = [("원문", orig.get("source_url") or official.get("source_url")), ("대한민국 구석구석", official.get("visitkorea_url")),
                 ("공식 홈페이지", official.get("homepage"))]
        links = [(lab, web_url(u)) for lab, u in links if u]
        if links:
            L.append("공식 링크: " + "; ".join(f"{lab} {u}" for lab, u in links))
            self.keep_url(*(u for _, u in links))
        self.add_doc(e["_path"], e["name"], "place", "\n".join(L), en, alt=alt)
        facts = self.plan_facts(e)
        if facts:
            self.docs[e["_path"]]["f"] = facts

    def place_ref(self, pid: str) -> str:
        """'<name> /places/<slug>/' for a place id (its id alone when it has no page here)."""
        e = next((x for x in self.S.entities if x["id"] == pid), None)
        return f"{e['name']} {e['_path']}" if e else pid

    def plan_facts(self, e: dict) -> dict:
        """What chatbot/knowledge.js checkPlan and the course planner (chatbot/planner.js, plan_fees.js, plan_state.js)
        read of a place (the first city's review 2026-10-17 G01: a plan put 0 minutes between two places 5.7 km apart):
        its point (g), its hours (h) and closed days (c) as each source writes them — the whole value, so a last entry
        time and the months of a season stay —, the bus routes of the stops near it (b), its dated notices still shown
        (n); then what the planner checks a plan's conditions with (AI 코스 만들기 집중 평가: fees the model left out or
        counted twice, access the page has said to be missing): its kind (kd) and type (ty), the fee value read as a
        table (fee: pipeline/fee_table.parse, the other sources' values beside it), the access rows as each source
        writes them (ac), the own parking value (pk) and the nearest public lot (pkn), the check-in time (ci)."""
        from . import build as B
        out: dict = {}
        geo = e.get("_geo") or {}
        if isinstance(geo.get("lat"), (int, float)) and isinstance(geo.get("lng"), (int, float)):
            out["g"] = [round(geo["lat"], 6), round(geo["lng"], 6)]
        for slot in present.key_facts(e, "hero")["slots"]:
            if slot["key"] not in ("hours", "closed"):
                continue
            row = B.fact_row(e, slot["src_key"]) if slot["src_key"] in FACT_ORDER + FIT_ORDER else None
            if row and row["value"] and slot["key"] == "hours":
                texts = [{"p": row["source"].get("provider", ""), "t": month_ranges(_clean(row["value"]))}]
                texts += [{"p": a.get("provider", ""), "t": month_ranges(_clean(a["value"]))}
                          for a in row["alternatives"] if not a["also"]]
            else:   # closed days as the first screen splits them, and hours a combined field gives
                texts = [{"p": v.get("provider") or slot.get("provider") or "",
                          "t": month_ranges(", ".join(x for x in (v.get("main"), v.get("sub")) if x))}
                         for v in (slot["vals"] or [slot])]
            texts = [x for x in texts if x["t"]]
            if texts:
                out["h" if slot["key"] == "hours" else "c"] = texts
        acc = present.access_vm(self.S, e) or {}
        routes = sorted({r for st in acc.get("stops") or [] for r in st.get("routes") or []})
        if routes:
            out["b"] = routes
        notes = []
        for row in e.get("_notices") or []:
            n = row["n"]
            start = str(n.get("start") or n.get("date") or "")
            notes.append({k: v for k, v in {"k": n["kind"], "s": start, "e": str(n.get("end") or start),
                                             "f": n.get("from"), "t": n.get("to"), "l": n.get("last_entry")}.items() if v})
        if notes:
            out["n"] = notes
        out["kd"] = e["kind"]
        if e.get("_type") or food_class(e):   # a restaurant's TourAPI class when its category is generic: 카페, 제과, 한식 …
            out["ty"] = e.get("_type") or food_class(e)
        row = B.fact_row(e, "usefee")
        if row and (row["value"] or row["alternatives"]):
            fee = fee_table.parse(row["value"]) if row["value"] else {}
            fee["t"] = _clean(row["value"]) if row["value"] else ""
            fee["p"] = row["source"].get("provider", "") if row["value"] else ""
            alt = [{"p": a.get("provider", ""), "t": _clean(a["value"])} for a in row["alternatives"] if not a["also"]]
            if alt:
                fee["alt"] = alt
            out["fee"] = fee
        access = []
        for key in ("accessible_route", "wheelchair", "accessible_toilet", "accessible_parking", "babycarriage"):
            row = B.fact_row(e, key)
            if not row:
                continue
            if row["value"]:
                access.append({"k": key, "t": _clean(row["value"]), "p": row["source"].get("provider", "")})
            access += [{"k": key, "t": _clean(a["value"]), "p": a.get("provider", "")} for a in row["alternatives"]
                       if not a["also"]]
        if access:
            out["ac"] = access
        row = B.fact_row(e, "parking")
        if row and row["value"]:
            out["pk"] = _clean(row["value"])
        lots = acc.get("lots") or []
        if lots:
            out["pkn"] = {"n": lots[0].get("name") or "", "m": lots[0].get("m")}
        row = B.fact_row(e, "checkin")
        if row and row["value"]:
            out["ci"] = _clean(row["value"])
        return out

    @staticmethod
    def _unique(items: list[dict]) -> list[dict]:
        """Records in first-seen order, each once (a guide that lists a place twice names it once)."""
        seen, out = set(), []
        for x in items:
            if id(x) not in seen:
                seen.add(id(x))
                out.append(x)
        return out

    def _access_source(self, name: str) -> str:
        """One source of the nearby parking / bus / station block with its address and 출처 확인 from nearby.json _meta
        (parking, bus, rail) or parking_lots.json source; any other name as given."""
        meta = getattr(self.S, "nearby_meta", None) or {}
        names = getattr(self.S, "access_names", None) or {}
        key = next((k for k, v in names.items() if v == name), "")
        src = {"standard": meta.get("parking"), "stops": meta.get("bus"), "rail": meta.get("rail")}.get(key) or {}
        urls = [src["url"]] if src.get("url") else [f["url"] for f in src.get("files") or [] if f.get("url")]
        if (src.get("names") or {}).get("url"):
            urls.append(src["names"]["url"])
        self.keep_url(*urls)
        bits = " ".join(urls)
        return name + (f" {bits}" if bits else "") + (f" (출처 확인 {src['checked_at']})" if src.get("checked_at") else "")

    @staticmethod
    def _lot(l: dict) -> str:
        bits = [l["type"], f"직선 {l['m']}m"]
        if l.get("spaces") is not None:
            bits.append(f"{l['spaces']}면" + (f"(다른 출처 {l['alt_spaces']}{l.get('alt_unit') or '대'})"
                                              if l.get("alt_spaces") is not None and l["alt_spaces"] != l["spaces"] else ""))
        if l.get("paid"):
            bits.append(l["paid"])
        if l.get("hours"):
            bits.append(f"운영 {l['hours']}")
        for fee in l.get("fees") or []:
            if fee.get("text"):
                bits.append(f"{fee['text']}({fee['src']})")
        if l.get("confirm"):
            bits.append(f"{l['differ']} 출처마다 다름 — 방문 전 전화 확인")
        if l.get("contact"):
            bits.append(f"문의 {l['contact']}")
        return f"{l['name']} (" + ", ".join(b for b in bits if b) + f") {l['addr']}"

    # -- guides
    def guide(self, g: dict) -> str:
        summary = present.decaution(_clean(g.get("summary")))
        answer = _clean((g.get("answer") or {}).get("answer")) or (present.sentences(summary) or [""])[0]
        en = self.en_path(g["_path"])
        parts = [f"G {g['_path']}", _clean(g["title"]), _short_line(answer, GUIDE_LINE_MAX)]
        L = [f"{_clean(g['title'])} — 가이드" + (f" ({_clean(g.get('label'))})" if g.get("label") else ""), "요약: " + summary]
        if _clean((g.get("answer") or {}).get("answer")):
            L.append("짧은 답: " + _clean(g["answer"]["answer"]))
        body = g.get("body") or []
        srcs = g.get("sources") or []
        # the dates first: a long guide is cut at DOC_LIMIT (and get_pages reads 6,000 characters)
        dates = _dates(_clean(g.get("checked_at")), _clean(g.get("reviewed_at")), _clean(g.get("approved_at")))
        L.append(dates)
        if body:
            L.append("본문 절(get_pages에 '경로#h-bN'으로 한 절만 읽을 수 있다):")
            L += [f"- #h-b{i} {_clean(b.get('heading'))}" for i, b in enumerate(body, 1)]
        items = []   # (name, place path, reason, page anchor of the item: templates/guide.html.j2 li#gi-<slug>)
        for i, it in enumerate(g.get("items") or [], 1):
            t = self.S.ent_by_slug.get(it.get("place_slug") or "")
            name = t["name"] if t else _clean(it.get("name"))
            if name:
                items.append((name, t["_path"] if t else "", present.decaution(_clean(it.get("reason"))),
                              f"gi-{t['slug']}" if t else f"gi-{i}"))
        faqs = [f"- Q {_clean(x['q'])} A {present.decaution(_clean(x['a']))}"
                for x in g.get("faq") or [] if x.get("q") and x.get("a")]
        src = ("출처: " + "; ".join(f"{_clean(s.get('name') or s.get('title'))} {s.get('url') or ''}".strip()
                                   for s in srcs)) if srcs else ""
        self.keep_url(*(s.get("url") for s in srcs))
        full = [f"- {n}{' ' + p if p else ''}" + (f": {r}" if r else "") for n, p, r, _ in items]
        whole = L + (["자주 묻는 질문:", *faqs] if faqs else []) + ([f"이 가이드의 장소 {len(items)}곳:", *full] if items else [])
        if len("\n".join(whole + [src])) <= GUIDE_DOC_FIT:
            L = whole
        else:
            # a long guide (dozens of places): get_pages reads DOC_CHARS of a page, so the places' reasons and the
            # FAQ past that point were never read (QA 2026-10-17: the bus guide's way back to the cable car). The page
            # doc names each place with the anchor of its own doc; every place's reason and the FAQ are docs of their
            # own, found by search_site and read whole
            L += (["자주 묻는 질문(전체는 '" + g["_path"] + "#h-faq'):", *faqs] if faqs else [])
            L.append(f"이 가이드의 장소 {len(items)}곳(장소마다 이유·가는 법은 '{g['_path']}#gi-' 뒤에 장소 주소의 슬러그를 붙인 문서를 "
                     "한 곳씩 읽거나 장소 이름으로 search_site): " + ", ".join(n for n, _, _, _ in items))
            for n, p, r, a in items:
                if r:
                    self.add_doc(f"{g['_path']}#{a}", f"{_clean(g['title'])} — {n}", "section",
                                 "\n".join([f"{n}{' ' + p if p else ''}", r, f"가이드 {dates}"]), en, head=n)
            if faqs:
                self.add_doc(f"{g['_path']}#h-faq", f"{_clean(g['title'])} — 자주 묻는 질문", "section",
                             "\n".join(["자주 묻는 질문", *faqs, f"가이드 {dates}"]), en, head="자주 묻는 질문")
        if src:
            L.append(src)
        self.add_doc(g["_path"], _clean(g["title"]), "guide", "\n".join(L), en)
        for i, b in enumerate(body, 1):
            text = "\n".join(present.decaution(_clean(p)) for p in str(b.get("text") or "").split("\n") if p.strip())
            self.add_doc(f"{g['_path']}#h-b{i}", f"{_clean(g['title'])} — {_clean(b.get('heading'))}", "section",
                         "\n".join([_clean(b.get("heading")), text, f"가이드 {dates}"]), en, head=_clean(b.get("heading")))
        return SEP.join(p for p in parts if p)

    # -- courses
    def course(self, c: dict) -> str:
        cv = self.S.course_vms[c["slug"]]
        stops = [s["name"] for s in cv["stops"]]
        en = self.en_path(c["_path"])
        head = cv["display"] + (f" ({cv['group']})" if cv.get("group") else "") + (f", {cv['duration']}" if cv.get("duration") else "")
        hero = "; ".join(f"{_clean(f.get('label'))} {_clean(f.get('short') or f.get('value'))}"
                         for f in c.get("facts") or [] if f.get("hero"))
        parts = [f"C {c['_path']}", head, f"경유지 {len(stops)}곳: " + " > ".join(stops), hero, cv.get("closed_note") or ""]
        L = [f"{head} — 여행 코스", "요약: " + _clean(cv.get("lede"))]
        if c.get("facts"):
            L.append("이용 안내(코스의 값):")
            L += [f"- {_clean(f.get('label'))}: {_clean(f.get('value'))}" for f in c["facts"] if f.get("label")]
            fs = [x for x in c.get("facts_sources") or [] if x.get("url")]
            if fs:
                L.append("이용 안내 출처: " + "; ".join(f"{_clean(x.get('label'))} {x['url']}" for x in fs))
                self.keep_url(*(x["url"] for x in fs))
        for r in cv["rows"]:
            if r["sep"] and r["kind"] == "day":   # the source's own schedule numbers ('일정 1', '일정 2')
                L.append(f"[{r['kind_label']} {r['name']}]")
                continue
            if r["sep"]:
                L.append(f"  ({r['kind_label']}: {r['name']}{' — ' + r['note'] if r.get('note') else ''})")
                continue
            nxt = f" → 다음 경유지까지 직선 {present.dist(r['next_m'])}" if r.get("next_m") else ""
            L.append(f"{r['n']}. {r['name']}{' ' + r['path'] if r['path'] else ''}"
                     f"{' (원문 표기: ' + r['label'] + ')' if r.get('label') else ''}"
                     f"{' — ' + r['note'] if r.get('note') else ''}{nxt}")
        if cv.get("show_total"):
            L.append(f"경유지 사이 직선거리 합: {present.dist(cv['total'])} ({cv['measure_note']}, 실제 이동 거리 아님)")
        L.append("이동: 경유지 사이 값은 직선거리다. 구간별 소요시간·총 소요시간은 자료에 없다(이동 미확인)"
                 + (", 이용 안내에 적힌 시각만 있다." if c.get("facts") else "."))
        if cv.get("closed_note"):
            L.append(f"쉬는 날 주의: {cv['closed_note']}")
        if cv.get("orig_url"):
            L.append(f"출처: {cv['orig_name']} {cv['orig_url']}")
            self.keep_url(cv["orig_url"])
        orig = c.get("original") or {}
        L.append(_dates(_clean(orig.get("collected_at")), _clean(c.get("reviewed_at")), _clean(c.get("approved_at")),
                        checked_label="원문 수집"))
        self.add_doc(c["_path"], cv["display"], "course", "\n".join(L), en)
        return SEP.join(p for p in parts if p)

    # -- events
    def series(self, sr: dict) -> str:
        ev = sr["newest"]
        place = _clean(ev.get("place_name"))
        fee = _clean(ev.get("fee"))
        latest = f"최근 회차 {_period(ev)}" + (f" · 장소 {place}" if place else "") + (f" · 요금 {_cap(fee, SLOT_MAX)}" if fee else "")
        if sr.get("newest_alt_labels"):
            latest += f" · {'·'.join(sr['newest_alt_labels'])} 두 출처 다름"
        past = ", ".join(_when(x.get("start_date"))[:7] for x in sr.get("past") or [])
        usual = _clean((sr.get("usual") or [{}])[0].get("text"))
        en = self.event_en.get(sr["_path"], "")
        parts = [f"E {sr['_path']}", _clean(sr["name"]), latest, f"이전 회차 {past}" if past else "",
                 f"보통: {_short_line(usual, GUIDE_LINE_MAX)}" if usual else ""]
        L = [f"{_clean(sr['name'])} — 행사·축제 (회차 {len(sr['editions'])}개)"]
        for x in sorted(sr["editions"], key=lambda x: (x.get("start_date") or "", x.get("name", "")), reverse=True):
            L.append(f"[{_clean(x.get('name'))}] 기간: {_period(x)}"
                     + (f" (원문 표기: {_clean(x.get('period_text'))})" if x.get("period_text") else ""))
            for k, lab in (("place_name", "장소"), ("address", "주소"), ("playtime", "시간"), ("fee", "요금"), ("agelimit", "관람 연령"),
                           ("tel", "문의"), ("homepage", "누리집"), ("sponsor", "주최·주관")):
                v = _clean(x.get(k))
                if v:
                    L.append(f"- {lab}: {display_address(v) if k == 'address' else v}")
            for k, vals in (x.get("alternatives") or {}).items():
                for a in vals or []:
                    L.append(f"- {k} 다른 출처 값: {_clean(a.get('value'))} — {_clean(a.get('source_name'))} → 출처마다 값이 달라 방문 전 확인")
                    self.keep_url(a.get("source_url"))
            for h in x.get("highlights") or []:
                L.append(f"- 프로그램: {_clean(h)}")
            for n in x.get("notes") or []:
                L.append(f"- 참고: {_clean(n)}")
            src = _clean(x.get("source_name"))
            if src or x.get("source_url"):
                L.append(f"- 출처: {src} {x.get('source_url') or ''}".rstrip() + (f" (출처 확인 {x['checked_at']})" if x.get("checked_at") else ""))
            for a in x.get("also_sources") or []:
                L.append(f"- 함께 본 출처: {_clean(a.get('name'))} {a.get('url') or ''}".rstrip())
                self.keep_url(a.get("url"))
            self.keep_url(x.get("source_url"), x.get("homepage"))
        for u in sr.get("usual") or []:
            L.append(f"보통 언제 열리나: {_clean(u.get('text'))} ({_clean(u.get('source_name'))})")
        places = [self.S.ent_by_slug[s] for s in sr.get("place_slugs") or [] if s in self.S.ent_by_slug]
        if places:
            L.append("관련 장소: " + "; ".join(f"{p['name']} {p['_path']}" for p in places))
        self.add_doc(sr["_path"], _clean(sr["name"]), "event", "\n".join(L), en)
        return SEP.join(p for p in parts if p)

    # -- videos
    def video(self, v: dict) -> None:
        g = self.video_topic.get(v["youtube_id"])
        places = [self.S.ent_by_slug[s] for s in v.get("place_slugs") or [] if s in self.S.ent_by_slug]
        kind = {"official": "공식 채널", "broadcaster": "방송사", "creator": "크리에이터"}.get(v.get("channel_kind"), "")
        title = _clean(v.get("title")) or v["youtube_id"]
        L = [f"{title} — YouTube 영상", f"채널: {_clean(v.get('channel'))}" + (f" ({kind})" if kind else ""),
             f"올린 날: {v.get('published_date') or '모름'}", f"주소: {v['url']}"]
        if g:
            L.append(f"실린 곳: {g['_path']} ({g['title']} 영상)")
        if places:
            L.append("관련 장소: " + "; ".join(f"{p['name']} {p['_path']}" for p in places))
        if v.get("event_names"):
            L.append("관련 행사: " + ", ".join(_clean(n) for n in v["event_names"]))
        if (v.get("lang") or "ko") != "ko":
            L.append(f"언어: {v['lang']}")
        self.keep_url(v["url"])
        self.add_doc(f"video:{v['youtube_id']}", title, "video", "\n".join(L), page=g["_path"] if g else "/videos/")

    def video_page(self, g: dict) -> str:
        items = g["items"]
        official = sum(1 for v in items if v.get("channel_kind") == "official")
        label = "그 밖의" if g["title"] == "기타" else g["title"]
        L = [f"{label} 영상 {len(items)}편 — 공식 채널 {official}편 (최신순)"]
        L += [f"- {_clean(v.get('title')) or v['youtube_id']} — {_clean(v.get('channel'))}, {v.get('published_date') or '날짜 없음'}, video:{v['youtube_id']}"
              for v in items[:60]]
        if len(items) > 60:
            L.append(f"… 나머지 {len(items) - 60}편은 페이지에서")
        self.add_doc(g["_path"], f"{label} 영상", "page", "\n".join(L))
        return SEP.join([f"V {g['_path']}", f"{label} 영상 {len(items)}편(공식 채널 {official}편)"])

    # -- abroad (해외에서 본 …): foreign articles and social posts, our note and the original's address (report
    # 2026-10-17 D27: the chatbot said the site had no Japanese travel piece while /abroad/ listed nine)
    def abroad_item(self, a: dict) -> None:
        post = a.get("kind") == "post"
        title = _clean(a.get("title")) or _short_line(_clean(a.get("note")), 60)
        L = [f"{title} — {'SNS 게시물 (' + (a.get('platform_label') or a.get('platform') or '') + ')' if post else '해외 기사'}"]
        L.append(f"{'계정' if post else '매체'}: {_clean(a.get('author') if post else a.get('outlet'))}")
        if not post and a.get("title"):
            L.append(f"원문 제목(원문 그대로): {_clean(a['title'])}")
        L.append(f"언어: {a.get('lang') or '모름'}")
        L.append(f"게시일: {a.get('date') or '모름'}")
        L.append(f"원문 주소: {a['url']}")
        L.append(f"우리 소개: {_clean(a.get('note'))}")
        q = a.get("_quote")
        if q and q.get("text"):
            L.append(f"원문 인용({q.get('lang') or ''}, 원문 그대로): {_clean(q['text'])}")
        places = a.get("_places") or []
        if places:
            L.append("관련 장소: " + "; ".join(f"{p['name']} {p['_path']}" for p in places))
        self.keep_url(a["url"])
        self.add_doc(f"abroad:{a['id']}", title, "abroad", "\n".join(L), page="/abroad/")

    def abroad_section(self) -> str:
        """The catalog line of /abroad/ (counts by kind and language) and its page doc: every article and post, newest
        first, one short line each with its abroad:<id> (get_pages reads the item)."""
        S = self.S
        for a in S.abroad:
            self.abroad_item(a)
        arts = [a for a in S.abroad if a.get("kind") != "post"]
        posts = [a for a in S.abroad if a.get("kind") == "post"]

        def by(items, key):
            c: dict[str, int] = {}
            for a in items:
                c[a.get(key) or "?"] = c.get(a.get(key) or "?", 0) + 1
            return "·".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))
        head = (f"해외에서 본 {S.city.region}: 해외 기사 {len(arts)}건(언어 {by(arts, 'lang')}), SNS 게시물 {len(posts)}건"
                f"({by(posts, 'platform_label')}; 언어 {by(posts, 'lang')})")
        if S.abroad_videos:
            head += f", 외국어 영상 {len(S.abroad_videos)}편"
        L = [head + " — 최신순. 항목마다 원문 제목·매체·언어·게시일·원문 주소·우리 소개는 abroad:<id>를 get_pages로"]
        for a in arts + posts:
            who = _clean(a.get("author") if a.get("kind") == "post" else a.get("outlet"))
            what = _clean(a.get("title")) or _short_line(_clean(a.get("note")), 40)
            L.append(f"- {a.get('date') or '날짜 없음'} · {a.get('lang') or '?'} · "
                     f"{a.get('platform_label') or '기사'} · {who}: {what} — abroad:{a['id']}")
        self.add_doc("/abroad/", f"해외에서 본 {S.city.region}", "page", "\n".join(L), self.en_path("/abroad/"))
        return SEP.join(["S /abroad/", head + " (하나하나는 search_site kind abroad)"])

    # -- themes and site pages
    def theme_lines(self) -> list[str]:
        S, out = self.S, []
        for t in sorted(S.themes, key=lambda t: t["slug"]):
            members = [e for e in S.entities if t["slug"] in (e.get("themes") or [])]
            if not members:
                continue
            path = f"/themes/{t['slug']}/"
            out.append(SEP.join(p for p in (f"T {path}", f"{t['name']} 여행지 {len(members)}곳", _clean(t.get("description"))) if p))
            self.add_doc(path, f"{t['name']} 여행지", "page", f"{t['name']} 여행지 {len(members)}곳:\n"
                         + "\n".join(f"- {e['name']} {e['_path']}" for e in sorted(members, key=lambda e: present.name_key(e["name"]))))
        return out

    def site_pages(self) -> list[str]:
        S = self.S
        site = S.site
        n = {k: len(v) for k, v in S.lists.items()}
        op = site.get("operator") or {}
        contact = op.get("contact") or ""
        region_word = S.city.region_label or "지역"
        source = (site.get("source") or {}).get("name", "")
        pages = [
            ("/", f"홈 — {site.get('site_name', '')}: 관광지 {n.get('attraction', 0)}곳·음식점 {n.get('food', 0)}곳·숙소 "
                  f"{n.get('stay', 0)}곳, 가이드 {len(S.guides)}편·코스 {len(S.courses)}개·행사 {len(S.series)}개·영상 {len(S.videos)}편",
             _clean(site.get("description"))),
            ("/places/", f"관광지 목록 {n.get('attraction', 0)}곳 (유형·{region_word}으로 거르기, 지도)", ""),
            ("/food/", f"음식점 목록 {n.get('food', 0)}곳 (대표 메뉴·영업시간·쉬는 날)", ""),
            ("/stays/", f"숙소 목록 {n.get('stay', 0)}곳 (체크인·체크아웃·주차·문의)", ""),
            ("/guides/", f"목적별 가이드 {len(S.guides)}편", ""),
            ("/courses/", f"여행 코스 {len(S.courses)}개", ""),
            ("/events/", f"행사·축제 일정 {len(S.series)}개 (월별 기간·장소)", ""),
            ("/map/", f"지도·{region_word}: " + "·".join(x for x in S.region_names if x and x != S.city.none_label), ""),
            ("/search/", "검색: 장소 이름·다른 이름·대표 메뉴·동 이름·코스·가이드·행사 이름으로 찾는다", ""),
            ("/videos/", f"영상 {len(S.videos)}편, 주제별 (공식 채널 표시, 누를 때만 YouTube 불러옴)", ""),
            ("/about/", f"소개·출처: 운영 {op.get('name', '')}, 공식 사이트 아님(독립 운영), 출처 "
                        + "·".join(x for x in (source, "한국관광공사 TourAPI") if x)
                        + (f", 정정 요청 {contact}" if contact else "") + ", 사이트 안내 챗봇 설명 /about/#chatbot", ""),
        ]
        out = []
        for path, line, extra in pages:
            if (path == "/videos/" and not S.videos) or (path == "/guides/" and not S.guides) \
                    or (path == "/courses/" and not S.courses) or (path == "/events/" and not S.series) \
                    or (path in ("/food/", "/stays/") and not n.get("food" if path == "/food/" else "stay")) \
                    or (path in ("/map/", "/search/") and not S.entities):
                continue
            out.append(SEP.join(p for p in (f"S {path}", line) if p))
            self.add_doc(path, line.split(":")[0].split(" — ")[0], "page", line + (f"\n{extra}" if extra else ""), self.en_path(path))
        self.about_doc()
        if site.get("emergency"):
            out.append(self.emergency(site["emergency"]))
        return out

    def emergency(self, em: dict) -> str:
        """The emergency numbers an about page lists (site.json emergency, when the operator adds it — the first city's
        has one): one short catalog line without addresses (prompt rule 14 answers from it at once, without a tool) and
        a doc with each number's source, the address it came from and 출처 확인일."""
        src = em.get("sources") or {}
        checked = em.get("checked_at") or ""
        nums = ", ".join(f"{x['tel']} {x['ko']}" + (f" 해외 {x['abroad']}" if x.get("abroad") else "")
                         for x in em.get("lines") or [])
        phrases = "·".join(f"'{p}'" for p in em.get("phrases") or [])
        line = SEP.join(["S /about/#emergency", f"긴급 연락처(출처 확인 {checked}): {nums}"
                         + (f"; 통역: 연결 뒤 {phrases}" if phrases else "")])
        L = ["긴급 연락처 — 여행 중 위급할 때(사람이 쓰러짐·다침·화재·범죄·물에 빠짐·아이를 잃어버림) 바로 전화",
             "페이지: /about/#emergency"]
        for x in em.get("lines") or []:
            s = src.get(x.get("src")) or {}
            L.append(f"- {x['tel']}: {x['ko']}" + (f" — 해외에서 걸 때 {x['abroad']}" if x.get("abroad") else "")
                     + f" — {s.get('provider', '')} {s.get('url', '')} (출처 확인 {checked})")
        for x in em.get("steps") or []:
            s = src.get(x.get("src")) or {}
            L.append(f"- {x['ko']} — {s.get('provider', '')} {s.get('url', '')} (출처 확인 {checked})")
        L.append("이 사이트는 응급처치·의료 안내를 하지 않는다. 찾는 말: 응급, 구급차, 긴급, 경찰, 소방, 통역, 신고")
        self.keep_url(*(s.get("url") for s in src.values()))
        self.add_doc("/about/#emergency", "긴급 연락처", "page", "\n".join(L), self.en_path("/about/"), head="긴급 연락처")
        return line

    def about_doc(self) -> None:
        S = self.S
        site = S.site
        op = site.get("operator") or {}
        src = site.get("source") or {}
        L = [f"{site.get('site_name', '')} — 소개·출처",
             _clean(site.get("description")), _clean(site.get("disclaimer")),
             f"운영: {op.get('name', '')}{'(' + op['name_en'] + ')' if op.get('name_en') else ''}"
             + (f", 편집 책임 {site['editor']['name']}" if (site.get("editor") or {}).get("name") else "")
             + (f", 정정 요청 {op['contact']}" if op.get("contact") else ""),
             f"공식 제휴: {site.get('affiliation') or '없음 — 지자체·기관의 공식 사이트가 아니다'}",
             (f"원문 출처: {src.get('name', '')} {src.get('url', '')}. " if src.get("name") else "")
             + "장소의 실용 정보(이용시간·요금 등)는 값마다 출처를 적고, 출처끼리 값이 다르면 둘 다 싣는다. 출처에 없는 항목은 "
             "'확인 필요'로 표시한다.",
             "사진: 한국관광공사 TourAPI의 공공누리 제1·3유형만, 출처와 함께. 제3유형은 자르거나 보정하지 않는다.",
             "거리: 코스·가이드·주변 목록의 거리는 모두 좌표 사이의 직선거리다.",
             "사이트 안내 챗봇(/about/#chatbot): 이 사이트에 실린 정보로만 답하고 답마다 페이지 링크를 단다. 모델은 Anthropic의 "
             "Claude Haiku 5.5. AI 답은 틀릴 수 있어 방문 전 확인이 필요하다. 예약·결제·회원가입은 하지 않는다.",
             "챗봇이 보내고 남기는 것: ① 브라우저 — 대화는 이 탭(sessionStorage)에만 남고, '새 대화'를 누르거나 탭을 닫으면 "
             "지워진다. ② 이 사이트의 서버 함수(/api/chat/) — 질문할 때마다 새 질문과 그 앞의 대화(최근 12개 메시지, 이전 답은 "
             "2,000자까지), 보고 있는 페이지 주소, 화면 언어를 받는다. 대화를 저장하지 않고, 서버 기록에는 처리 상태와 사용량 "
             "숫자만 남는다(질문·답의 글은 남기지 않음). ③ 외부 AI(Anthropic API) — 답을 만들려고 서버 함수가 위 내용을 "
             "Anthropic API로 보낸다. 그쪽의 처리·보관은 Anthropic의 정책을 따르고, 이 사이트는 이미 보낸 내용을 지울 수 없다.",
             "개인정보: 이름·전화번호·이메일을 자동으로 가리는 기능은 없다. 잘못 입력했다면 '새 대화'를 누른다. 그러면 이 탭의 "
             "대화가 지워지고 다음 질문부터는 보내지 않는다(그대로 두면 다음 질문 때 앞의 대화와 함께 다시 보낸다). 이미 보낸 "
             "질문은 되돌릴 수 없다."]
        self.add_doc("/about/", "소개·출처", "page", "\n".join(x for x in L if x), self.en_path("/about/"))

    # -- output
    def catalog(self) -> str:
        return month_ranges("\n".join(self.lines).rstrip("\n")) + "\n"

    def docs_json(self) -> dict:
        alias = {}
        for key, d in self.docs.items():
            if "#" in key:
                continue
            for path in [d.get("e"), *(d.get("l") or {}).values()]:
                if path and path not in alias:
                    alias[path] = key
        out = {"v": VERSION, "site": self.site, "meta": {**self.meta, "plan": plan.plan_meta(self.S)},
               "docs": dict(sorted(self.docs.items())), "alias": dict(sorted(alias.items())), "ext": sorted(self.ext)}
        # the combined tickets' tables for the fee_total tool and the course planner (pipeline/tickets.py;
        # chatbot/knowledge.js feeTotal, chatbot/plan_fees.js)
        data = getattr(self.S, "tickets", None) or {}
        if data.get("tickets"):
            by_id = {e["id"]: e for e in self.S.entities}
            out["tickets"] = tickets.export(data, lambda pid: {"path": by_id[pid]["_path"], "name": by_id[pid]["name"]}
                                            if pid in by_id else {"path": "", "name": pid})
        return out

    def index_json(self) -> dict:
        out = {}
        for key, d in sorted(self.docs.items()):
            head = tokens(f"{d['t']} {key if key.startswith('/') else ''}")
            lines = d["x"].split("\n", 3)
            head += [t for t in tokens(lines[0]) if t not in head]
            # a place's other names count as its title: searching an old name finds the place first
            alt = next((x[len("다른 이름: "):] for x in lines[1:3] if x.startswith("다른 이름: ")), "")
            head += [t for t in tokens(alt) if t not in head]
            # its names on the other versions of the site ('大邱美術館', 'Kunstmuseum Daegu') find the page as its Korean
            # name does (the first site's review 2026-10-17 E03)
            head += [t for t in tokens(" ".join((d.get("n") or {}).values())) if t not in head]
            # web addresses (sources, official links) are not words a reader searches for
            body = [t for t in tokens(URL_RX.sub(" ", d["x"])) if t not in set(head)]
            out[key] = [" ".join(head), " ".join(body)]
        return {"v": VERSION, "docs": out}


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def export(S, out: Path) -> dict:
    """Write <out>/chat/catalog.txt, docs.json and index.json (UTF-8, LF line ends on every system) and return the
    sizes for the build stats."""
    k = Knowledge(S).build()
    target = Path(out) / CHAT_DIR
    target.mkdir(parents=True, exist_ok=True)
    catalog = k.catalog()
    files = {"catalog.txt": catalog, "docs.json": dumps(k.docs_json()) + "\n", "index.json": dumps(k.index_json()) + "\n"}
    for name, text in files.items():
        (target / name).write_bytes(text.encode("utf-8"))
    places = sum(1 for line in k.lines if line.startswith("P "))
    return {"catalog_lines": sum(1 for line in k.lines if line[:2] in ("P ", "G ", "C ", "E ", "V ", "T ", "S ")),
            "places": places, "catalog_chars": len(catalog), "catalog_bytes": len(catalog.encode("utf-8")),
            "catalog_tokens_est": estimate_tokens(catalog), "docs": len(k.docs),
            "docs_bytes": len(files["docs.json"].encode("utf-8")), "index_bytes": len(files["index.json"].encode("utf-8"))}
