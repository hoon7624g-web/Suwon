"""Render the static site from data/<region>/*.json.

    python -m pipeline.build --data data/gunsan --out dist                      # 공개용 (published만)
    python -m pipeline.build --data data/gunsan --out dist-preview --mode preview  # 검수용 (reviewed 포함, noindex)
    python -m pipeline.build --data data/sample --out dist-sample --mode sample     # 샘플 미리보기

Modes
- production : status=published only; robots.txt allows search crawlers. An entity page is indexed only when it
               meets the index criteria (schema.index_status, CLAUDE.md 3.8); other pages get
               "noindex, follow" and are left out of sitemap.xml / llms.txt / llms-full.txt, but stay in
               lists, maps and nearby links.
- preview    : draft + reviewed + published, for human review; noindex + robots Disallow. No visible review
               banner or status badge (owner's request); the index verdict is kept in data-index on each place.
- sample     : published + reviewed of the bundled sample data (placeholders allowed), noindex.

Status flow: draft (작성됨·검수 전) -> reviewed (사람 검수 완료·공개 대기) -> published (공개).

Other language versions (/en/, /ja/, /zh-hans/, /zh-hant/, /de/, /fr/, /es/, /ru/): when data/<region>/<code> exists,
pipeline/en_site.py (one engine, locale table pipeline/locales.py) builds them next to the Korean ones from the
translations whose ko_hash matches the current Korean data (stale ones are skipped with a warning); Korean pages
with a twin carry hreflang links, and every page the language menu (each version's counterpart, else its home).

Everything a reader or crawler needs is in the HTML. JavaScript only adds the map (when coordinates
exist) and list filters; without it every page is complete.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from . import art, ask, chat_index, en_site, icons, jsonld, notices, relations, tickets, timetables
from .enrich import haversine_m
from .maplinks import DEFAULT_TMAP_SCHEME, build_links, precision_summary, search_link
from .schema import (DEFAULT_ALLOWED_LICENSES, FACT_ALIASES, FACT_LABELS, FACT_ORDER, FIT_ORDER, INDEX_GROUP_LABELS,
                     INDEX_REASONS, KEY_FACTS, KEY_FACTS_BY_CATEGORY, KIND_LABELS, LICENSE_LABELS, alias_holds,
                     designations, fact_label, index_groups, index_status, license_allowed, parking_seats_half,
                     summary_sentences)
from . import present
from . import locales as LC
from .textutil import (area_from_address, cell_html, display_address, display_value, drop_dead_links, first_sentence,
                       josa, keep_dots, keep_primary_facts, keep_units, link_url, normalize_name, road_from_address,
                       slugify, squash_ws, url_key, web_url)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
MARKER = ".webforai-build"

MODES = {
    "production": {"statuses": {"published"}, "noindex": False, "banner": ""},
    "preview": {"statuses": {"draft", "reviewed", "published"}, "noindex": True,
                "banner": ""},
    "sample": {"statuses": {"published", "reviewed"}, "noindex": True,
               "banner": "샘플 빌드 — 화면 구조 확인용이며 표시된 값은 실제 정보가 아닙니다"},
}
# Short labels for the title, from the key fact rows a page actually shows (P1-1). checkout/spendtime: no label.
TITLE_LABELS = {"usetime": "이용시간", "usetime_restdate": "영업시간", "restdate": "쉬는 날", "usefee": "요금",
                "parking": "주차", "parking_seats": "주차", "parkingfee": "주차", "checkin": "체크인", "menu": "메뉴"}
# A restaurant's title says what people search for a restaurant (Search Console 2026-10-22: '라라코스트 영업시간',
# '군산 오죽'): its hours as 영업시간 and its dish before the closed day — '군산 오죽 영업시간·메뉴·쉬는 날'. The other
# kinds keep the key-row order.
FOOD_TITLE_ORDER = ("usetime", "usetime_restdate", "menu", "restdate", "parking", "parking_seats", "parkingfee", "usefee")


def title_keys(kind: str, keys: list[str]) -> list[str]:
    """The key-row keys in the order the title names them (FOOD_TITLE_ORDER for a restaurant)."""
    if kind != "food":
        return list(keys)
    rank = {k: i for i, k in enumerate(FOOD_TITLE_ORDER)}
    return sorted(keys, key=lambda k: rank.get(k, len(rank)))


def title_label(kind: str, key: str) -> str:
    """The title's word for a key row: a restaurant's 이용시간 is its 영업시간."""
    return "영업시간" if kind == "food" and key == "usetime" else TITLE_LABELS[key]
KO_WEEKDAYS = "월화수목금토일"
SEARCH_BOTS = ["OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User", "PerplexityBot",
               "Perplexity-User", "Googlebot", "Bingbot", "Yeti", "Daumoa"]
TRAINING_BOTS = ["GPTBot", "ClaudeBot", "CCBot"]
# named when the owner allows AI training / generative use (crawler_policy.allow_training_bots): the training
# crawlers plus the robots tokens that govern generative use (Gemini: Google-Extended, Apple Intelligence …)
AI_USE_BOTS = TRAINING_BOTS + ["Google-Extended", "Applebot-Extended", "meta-externalagent", "Amazonbot"]

# List pages per kind. Every entity page stays at /places/{slug}/ (URLs never change).
LISTS = {
    "attraction": {"path": "/places/", "title": "관광지", "h1": "가볼만한 곳·관광지",
                   "seo": "{region} 가볼만한 곳 {n}곳 — 관광지 이용시간·쉬는 날·요금·주차·길찾기",
                   "lead": "어떤 곳인지, 지금 가도 되는지 확인하고 길찾기로 이어 가세요.",
                   "hub": ("guide-15", "권역별로 고른 가볼만한 곳")},
    "stay": {"path": "/stays/", "title": "숙소", "h1": "숙소",
             "seo": "{region} 숙소 {n}곳 — 호텔·모텔·게스트하우스의 체크인·주차·문의",
             "lead": "숙소마다 체크인·체크아웃·주차·문의처를 정리했습니다.",
             "hub": ("guide-14", "호텔·모텔·게스트하우스·섬 민박·펜션 고르는 법")},
    "food": {"path": "/food/", "title": "음식점", "h1": "맛집·음식점",
             "seo": "{region} 맛집·음식점 {n}곳 — 대표 메뉴·영업시간·쉬는 날·주차",
             "lead": "음식점마다 대표 메뉴와 영업시간·정기휴일을 정리했습니다.",
             "hub": ("guide-13", "짬뽕·꽃게장·박대·아귀찜, 메뉴별 맛집")},
}
# Official Gunsan categories grouped for the list filter (presentation only).
ATTRACTION_GROUPS = (
    ("박물관·전시", ("박물관", "전시관", "근대건축관")),
    ("체험", ("체험", "농장", "농원")),
    ("문화유산", ("문화유산", "보물", "사적", "명승", "향토", "기념물")),
    ("자연·야외", ("공원", "금강", "섬", "천연기념물", "마파지길", "캠핑", "골프")),
)
MOUNTAIN = re.compile(r"(?<![군유])산(?=\s|$)")  # 오성산, category '산' — not 군산·산업·유산
VISUALS = {  # tone, icon
    "stay": ("stay", "bed"), "food": ("food", "bowl"),
    "islands-sea": ("sea", "wave"), "parks-nature": ("park", "tree"),
    "modern-history": ("history", "building"), "alleys-culture": ("alley", "lamp"),
    "박물관·전시": ("history", "museum"), "체험": ("craft", "spark"), "문화유산": ("history", "pin"),   # 향교·석탑 too: not the brick building (theme-modern-history)
    "자연·야외": ("park", "tree"),
}
# Home hero slides: (place slug, n-th Type1 photo). Only KOGL-1 (cropping allowed); Type3 is never cropped.
HERO_PICKS = (("대장도", 1), ("장자도", 0), ("오성산", 0), ("월명공원", 1), ("무녀도", 1))
PURPOSES = (  # home entry points: guide id (when written) or fallback path
    ("맛집", "guide-13", "/food/", "짬뽕·꽃게장·박대·아귀찜, 메뉴별로"),
    ("숙소·펜션", "guide-14", "/stays/", "호텔·모텔·게스트하우스·섬 민박"),
    ("가볼만한 곳", "guide-15", "/places/", "원도심·고군산·은파·새만금·금강 권역별"),
    ("당일 여행", "guide-01", "/courses/#g-당일-코스", "공식 당일 코스와 차 없이 다니는 법"),
    ("아이와 함께", "guide-02", "/places/", "체험·박물관처럼 아이와 둘러볼 곳"),
    ("비 오는 날", "guide-03", "/places/", "실내 전시·박물관"),
    ("차 없이", "guide-01", "/courses/", "버스·시티투어·관광안내소"),
)


# ---------------------------------------------------------------- helpers
def _load(path: Path, default=None):
    if not path.exists():
        if default is None:
            raise FileNotFoundError(f"필수 파일 없음: {path}")
        return default
    return json.loads(path.read_text("utf-8"))


def fmt_dist(m) -> str:
    try:
        m = int(m)
    except (TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    return f"{m}m" if m < 1000 else f"{m / 1000:.1f}km"


# the map provider (owner decision 2026-10-14): Kakao Maps JavaScript SDK. site.json kakao_js_key is a public key that
# Kakao accepts only from the web domains registered for it; every map box names the SDK URL (data-kakao-sdk) and
# assets/map.js fetches it near the screen, after load. A page without a map box never names it.
KAKAO_SDK = "https://dapi.kakao.com/v2/maps/sdk.js?appkey={key}&autoload=false"


def kakao_sdk_url(site: dict) -> str:
    """The SDK URL for the map boxes, or '' when site.json has no kakao_js_key (the boxes then show the failure line)."""
    key = str((site or {}).get("kakao_js_key") or "").strip()
    return KAKAO_SDK.format(key=quote(key, safe="")) if key else ""


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(enabled_extensions=("html", "j2", "xml")),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["nl2br"] = lambda s: Markup("<br>".join(str(escape(x)) for x in str(s or "").split("\n")))
    env.filters["dist"] = fmt_dist
    env.filters["first_sentence"] = first_sentence
    env.filters["license_label"] = lambda c: LICENSE_LABELS.get(c or "UNKNOWN", c)
    env.filters["kind_label"] = lambda k: KIND_LABELS.get(k, k)
    env.filters["squash"] = squash_ws
    env.filters["josa"] = josa
    env.filters["web_url"] = web_url
    env.filters["ko_date"] = ko_date
    env.filters["address"] = display_address
    env.filters["addr_nw"] = present.nowrap_address   # an address's house numbers on one line; long unspaced ones wrap
    env.filters["wordmark"] = present.wordmark        # the site name with its emphasised end (군산각 → 각, Gunsangak → gak)
    # {{ raw|dv(key) }}: a stored value as the page shows it (textutil.display_value; JSON-LD and validate use it too)
    env.filters["dv"] = lambda raw, key: display_value(key, raw)
    env.filters["link_url"] = link_url  # a homepage/booking value's link target (validate checks the same URL)
    # shared markup (templates/_ui.html.j2): footnote superscripts — the visible number plus a hidden " — 출처 n", so
    # a fact <dd> reads "value — 출처 1" as text (validate's dt/dd pair parser splits on " — "); chapter notes (FAQ,
    # 자세히) read " 출처 n"; JSON for data-* attributes (escaped by autoescape); distances as present.dist shows them
    env.filters["sup"] = lambda n: Markup(f'<sup class="fn"><span class="vh"> — 출처 </span>{n}</sup>') if n else ""
    env.filters["csup"] = lambda n: Markup(f'<sup class="fn"><span class="vh"> 출처 </span>{n}</sup>') if n else ""
    env.filters["tojson_attr"] = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    env.filters["pdist"] = present.dist
    env.filters["short_date"] = present.short_date
    # Apple skin: time ranges and prices never break inside ('09:00–18:00', '3,000원(1,500원)'); a short date
    # ('10. 9.(금)') never breaks inside itself (a range breaks only after its dash); '2026. 10. 8.'; fragment ids
    # without spaces; tap-to-call numbers; closed-day phrases marked; owner item 7's caution filter (opt-in)
    # a time in brackets — the last entry a key-fact tile folds in ('09:00–18:00(입장마감 17:30)', present.brief_hours)
    # — is .kfl (kept whole, its own weight; a size down on the hero's tiles: css/30-info.css), its time unbroken. A
    # range with the word right before it — its season or days ('11~2월', '동절기(11~2월)', '토,일') — and its bracket,
    # or a word with its bracket ('하절기(입장마감 17:30)'), is one unit (.nwu), so a line breaks between ranges, never
    # inside one (review 2026-10-18, fourth round: '11~2월 | 09:00–17:00'); the words do not change. A unit never
    # begins with a list mark ('、，,;·'): left outside it, the mark stays at the end of the line before, so a Japanese or
    # Chinese line never starts with '、' ('夏季（入場締切17:30）、冬季（…）', en_site.last_entry_tr; UI review 2026-10-19)
    last = r"[(（][^()（）]*?\d{1,2}:\d{2}[^()（）]*[)）]"
    lead = "、，,;；·・"

    def nwt(t):
        def kfl(s):
            return '<span class="kfl">' + re.sub(r"(\d{1,2}:\d{2}(?:–\d{1,2}:\d{2})?)", r'<span class="nw">\1</span>', s) + "</span>"

        def one(m):
            if m.group("last"):
                return f'<span class="nwu">{m.group("word")}{kfl(m.group("last"))}</span>' if m.group("word") else kfl(m.group("last"))
            if m.group("range"):
                unit = (m.group("label") or "") + f'<span class="nw">{m.group("range")}</span>' + (kfl(m.group("tail")) if m.group("tail") else "")
                return f'<span class="nwu">{unit}</span>' if m.group("label") or m.group("tail") else unit
            return f'<span class="nw">{m.group("price")}</span>'
        return Markup(re.sub(rf"(?P<word>(?:[^\s<>:()（）{lead}][^\s<>:()（）]*)?)(?P<last>{last})"
                             rf"|(?P<label>[^\s<>:{lead}][^\s<>:]*\s)?(?P<range>\d{{1,2}}:\d{{2}}–\d{{1,2}}:\d{{2}})(?P<tail>{last})?"
                             r"|(?P<price>[\d,]+원(?:\([\d,]+원\))?)", one, str(escape(t or ""))))
    env.filters["nwt"] = nwt
    # line breaks that read well (textutil.keep_units / cell_html, UI 2026-10-31): `ku` for a sentence or a label,
    # `cellv` for a list cell's value (more=True glues its '외' to the last word, never a line of its own)
    env.filters["ku"] = lambda t: Markup(keep_units(t))
    env.filters["cellv"] = lambda t, more=False: Markup(cell_html(t, ' <span class="kf-more">외</span>' if more else ""))
    env.filters["dbr"] = lambda t: Markup(re.sub(r"(\d{1,2}\. \d{1,2}\.(?:\([월화수목금토일]\))?)",
                                                 lambda m: f'<span class="nw">{m.group(1)}</span>', str(escape(t or ""))))
    env.filters["short_iso"] = lambda iso: f"{iso[:4]}. {int(iso[5:7])}. {int(iso[8:10])}." if iso and len(iso) >= 10 else (iso or "")
    env.filters["frag"] = present.frag
    env.filters["tel"] = present.tel_markup
    env.filters["closedmark"] = present.mark_closed
    env.filters["clhead"] = present.closed_head     # a row's closed day: the square kept with its first word
    env.filters["glue_dots"] = present.glue_dots   # '해설·군산': a middle dot never starts a line
    env.filters["decaution"] = present.decaution
    env.filters["side_state"] = present.side_state   # the tab panel's groups of one page (templates/_side.html.j2)
    env.globals["card_vm"] = present.card_vm
    env.globals["SHARE_WORDS"] = LC.SHARE_WORDS   # ui.lnav's share button, in the page's language
    env.globals["key_facts"] = present.key_facts
    # the 3D picture registry (pipeline/icons.py; templates/_pic.html.j2 asks it, never naming files)
    env.globals["icon_pic"] = icons.lookup
    env.globals["icon_glyph"] = icons.glyph
    env.globals["book_words"] = LC.BOOK_WORDS   # 예약하기 words of every version (the about pages' sentence)
    en_site.add_filters(env)  # the English templates (templates/en/)
    return env


# ---------------------------------------------------------------- stylesheet
CSS_DIR = TEMPLATES / "assets" / "css"
# css/49-art.css from '/* art-slots' to '/* art-slots end */': the rules of AI art slots that may have no picture yet (the
# map 권역 strip, the small picture beside a heading, the about head's picture). site_css keeps them only for a build
# whose pages show such a picture (art.slot_css_needed), so a slot without a picture adds nothing to the site.
ART_SLOT_CSS = re.compile(r"/\* art-slots\b.*?/\* art-slots end \*/", re.S)


def css_source() -> str:
    """The style partials (templates/assets/css/*.css) joined in file-name order, as written (comments kept)."""
    return "\n".join(f.read_text("utf-8") for f in sorted(CSS_DIR.glob("*.css")))


def site_css(art_slots: bool = False) -> str:
    """/assets/style.css: the partials in one request, comments stripped and whitespace collapsed (spaces after
    commas and inside values are kept, so font stacks and calc() stay as written). The stylesheet blocks the first
    paint and shares the line with the HTML, so every byte shows in the first paint on a slow line (2026-10-09:
    5 KB less = the stylesheet in ~80 ms earlier on the guide hub, tools/perf_check conditions): the space after a
    declaration's colon and the line break after a selector list's comma go too. art_slots: keep the AI art slot
    rules (ART_SLOT_CSS) — True when a built page shows one of those pictures."""
    css = css_source() if art_slots else ART_SLOT_CSS.sub("", css_source())
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s*\n\s*", "\n", css)
    css = re.sub(r"[ \t]{2,}", " ", css)
    css = re.sub(r"\s*([{};>])\s*", r"\1", css).replace(";}", "}")
    css = re.sub(r"([{;])(-*[A-Za-z][\w-]*):\s+", r"\1\2:", css)   # 'color: x' -> 'color:x' (a declaration's name)
    css = css.replace(",\n", ",")
    return css.strip() + "\n"


def _unique_slugs(items: list[dict], name_key: str) -> None:
    seen = set()
    for it in items:
        base = it.get("slug") or slugify(it.get(name_key, ""))
        s, n = base, 2
        while s in seen:
            s, n = f"{base}-{n}", n + 1
        it["slug"] = s
        seen.add(s)


def guide_has_content(guide: dict) -> bool:
    """A planning title alone is not a visitor guide. Keep its draft in data."""
    return (
        any(str(block.get("text") or "").strip() for block in guide.get("body") or [])
        or any(str(item.get("reason") or "").strip()
               and (item.get("place_slug") or item.get("name")) for item in guide.get("items") or [])
        or any(str(faq.get("q") or "").strip() and str(faq.get("a") or "").strip()
               for faq in guide.get("faq") or [])
    )


def category_group(e: dict) -> str:
    if e.get("kind") != "attraction":
        cat = squash_ws(e.get("category"))
        if "(" in cat and "특화거리" in cat:
            name, _, inner = cat.partition("(")
            return f"{inner.rstrip(')').strip()}({name.strip()})"
        return cat or "기타"
    text = f"{e.get('category', '')} {e.get('name', '')}"
    for label, words in ATTRACTION_GROUPS:
        if any(w in text for w in words) or (label == "자연·야외" and MOUNTAIN.search(text)):
            return label
    return "테마 여행지"


def has_fact(e: dict, key: str) -> bool:
    """facts[key], or an alias field that answers it (schema.alias_holds: a seat count alone is no parking value)."""
    return bool((e.get("facts") or {}).get(key)) or any(alias_holds(e, key, a) for a in FACT_ALIASES.get(key, ()))


# ---------------------------------------------------------------- field-level provenance
KEY_ROW_KEYS = ("usetime", "usetime_restdate", "restdate", "usefee", "parking", "parking_seats",
                "parkingfee", "checkin", "checkout", "menu", "spendtime")


def _source(src: dict | None, fallback_provider: str = "") -> dict:
    src = src or {}
    return {"provider": squash_ws(src.get("provider")) or fallback_provider,
            "checked_at": squash_ws(src.get("checked_at")), "url": web_url(src.get("url"))}


def fact_source(e: dict, key: str) -> dict:
    """Where facts[key] came from: fact_sources[key], else the record-level facts_source.
    With neither, the original's source name (the importer took the value from it)."""
    src = (e.get("fact_sources") or {}).get(key) or e.get("facts_source") or {}
    return _source(src, squash_ws((e.get("original") or {}).get("source_name")))


def fact_alternatives(e: dict, key: str, primary) -> list[dict]:
    """Values for `key` from other sources that differ from the shown value (CLAUDE.md 3.2: show both)."""
    seen = {squash_ws(str(primary or ""))}
    out = []
    for alt in (e.get("fact_alternatives") or {}).get(key) or []:
        value = str(alt.get("value") or "")
        if key == "address":
            value = display_address(value)
        if not squash_ws(value) or squash_ws(value) in seen:
            continue
        seen.add(squash_ws(value))
        # relation 'also': a second, non-contradicting value (another dish, phone line, web page)
        out.append({"value": value, **_source(alt), "note": squash_ws(alt.get("note")),
                    "also": alt.get("relation") == "also"})
    return out


def fact_row(e: dict, key: str) -> dict | None:
    value = (e.get("facts") or {}).get(key) or ""
    if key == "address":  # only the province prefix is rewritten; data keeps the source string
        value = display_address(value)
    alternatives = fact_alternatives(e, key, value)
    if not value and not alternatives:
        return None
    return {"key": key, "label": fact_label(e, key), "value": value,
            "source": fact_source(e, key) if value else {}, "alternatives": alternatives}


def fact_source_groups(rows: list[dict]) -> list[dict]:
    """Distinct (provider, 확인일) pairs with the labels they back, for one block's source line."""
    groups: dict[tuple, dict] = {}
    for r in rows:
        for src in ([r["source"]] if r["source"] else []) + r["alternatives"]:
            g = groups.setdefault((src["provider"], src["checked_at"]),
                                  {"provider": src["provider"], "checked_at": src["checked_at"], "url": "", "labels": []})
            g["url"] = g["url"] or src.get("url", "")
            if r["label"] not in g["labels"]:
                g["labels"].append(r["label"])
    return list(groups.values())


def facts_checked_date(e: dict, rows: list[dict] | None = None) -> str:
    """The newest 확인일 among the facts shown on the place page (shown there as 정보 확인일)."""
    if rows is None:
        rows = [r for r in (fact_row(e, k) for k in FACT_ORDER + FIT_ORDER) if r]
    return max((g["checked_at"] for g in fact_source_groups(rows) if g["checked_at"]), default="") \
        or squash_ws((e.get("facts_source") or {}).get("checked_at"))


def _url_key(url: str) -> str:
    """Comparison key for a URL: no scheme, no trailing '/' or '?', lower case (textutil.url_key)."""
    return url_key(url)


def latest(*dates) -> str | None:
    """Newest of the given ISO dates (each one visible on its page); None when none is known."""
    found = [squash_ws(str(d)) for d in dates if d and squash_ws(str(d))]
    return max(found) if found else None


def og_image(images: list[dict]) -> str:
    """og:image: a Type1 photo first (platforms crop previews; Type3 must not be cropped — owner decision
    pending), else the first licensed photo as before."""
    for im in images or []:
        if im.get("license") == "KOGL-1":
            return im["url"]
    return images[0]["url"] if images else ""


def ko_date(iso: str | None, with_year: bool = True) -> str:
    """'2026-10-02' -> '2026년 10월 2일(금)' (the weekday is the calendar's, nothing else is added)."""
    try:
        d = dt.date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return squash_ws(iso)
    text = f"{d.month}월 {d.day}일({KO_WEEKDAYS[d.weekday()]})"
    return f"{d.year}년 {text}" if with_year else text


def source_labels(e: dict) -> dict:
    """URL -> who published it, so a FAQ/'자세히' source link is named after the page it opens."""
    out = {}
    orig = e.get("original") or {}
    if orig.get("source_url"):
        out[orig["source_url"]] = orig.get("source_name") or "군산시 문화관광"
    for src in (e.get("fact_sources") or {}).values():
        if src.get("url") and src.get("provider"):
            out.setdefault(src["url"], src["provider"])
    return out


def index_note(e: dict) -> str:
    """One line for reviewers (preview/sample) saying what production will do with this page."""
    if e["_index_ok"]:
        return "색인 기준 충족"
    parts = []
    for reason in e["_index_reasons"]:
        if reason == INDEX_REASONS["groups"]:
            have = [INDEX_GROUP_LABELS[g] for g in index_groups(e)]
            reason += f"(있음: {'·'.join(have)})" if have else "(하나도 없음)"
        parts.append(reason)
    return "색인 제외 예정: " + " · ".join(parts)


class State:
    def __init__(self, data_dir: Path, mode: str):
        self.mode = mode
        self.cfg = MODES[mode]
        self.site = _load(data_dir / "site.json")
        self.site_url = self.site["site_url"].rstrip("/")
        self.today = dt.date.today().isoformat()
        statuses = self.cfg["statuses"]
        keep = lambda xs: [x for x in xs if x.get("status") in statuses and not x.get("duplicate_of")
                           and not x.get("exclude")]  # exclude: e.g. 'not_a_place' (a reading guide, a walking course)
        self.entities_all = _load(data_dir / "places.json", [])
        _unique_slugs(self.entities_all, "name")
        self.themes = _load(data_dir / "themes.json", [])
        self.courses_all = _load(data_dir / "courses.json", [])
        self.guides_all = _load(data_dir / "guides.json", [])
        self.columns_all = _load(data_dir / "columns.json", []) if self.entities_all else []
        self.events_all = _load(data_dir / "events.json", [])
        # dead homepage/booking addresses (data/<region>/dead_links.json, QA 2026-10-15 SRC-02) leave every record
        # before anything reads it: index_status, pages in every language, cards, JSON-LD, llms-full, chat docs
        self.dead_links = _load(data_dir / "dead_links.json", {})
        self.dead_dropped = drop_dead_links(self.entities_all + self.events_all, self.dead_links)
        # 출처마다 다른 값 (site.json fact_conflicts 'primary', operator 2026-10-31 '출처마다 다름 표시는 안 보이면'):
        # every record keeps its main value alone before anything reads it (textutil.keep_primary_facts); the language
        # versions drop their translated alternatives the same way (en_site.Site); without the key both values show
        self.facts_set_aside = (keep_primary_facts(self.entities_all + self.events_all)
                                if self.site.get("fact_conflicts") == "primary" else [])
        if self.site.get("fact_conflicts") == "primary":   # an event edition's other sources' values, the same way
            for ev in self.events_all:
                if ev.get("alternatives"):
                    ev["alternatives"] = {}
        # 예약하기 (step 1): the official booking pages pages link as buttons (pipeline/booking.py); none without the file
        self.booking = _load(data_dir / "booking.json", {})
        _unique_slugs(self.courses_all, "name")
        _unique_slugs(self.guides_all, "title")
        _unique_slugs(self.columns_all, "title")
        self.entities = keep(self.entities_all)
        self.courses = keep(self.courses_all)
        self.guides = [g for g in keep(self.guides_all)
                       if g.get("status") != "draft" or guide_has_content(g)]
        self.columns = [c for c in keep(self.columns_all)
                        if c.get("status") != "draft" or guide_has_content(c)]
        self.events = sorted(keep(self.events_all), key=lambda e: (e.get("start_date") or "9999", e.get("name", "")))
        rules = self.site.get("publish_rules") or {}
        self.allowed_original = tuple(rules.get("allowed_original_licenses") or DEFAULT_ALLOWED_LICENSES)
        self.allowed_images = tuple(rules.get("allowed_image_licenses") or DEFAULT_ALLOWED_LICENSES)
        self.theme_by_slug = {t["slug"]: t for t in self.themes}
        for e in self.entities:
            facts = e.get("facts") or {}
            e["_path"] = f"/places/{e['slug']}/"
            e["_url"] = self.abs(e["_path"])
            e["_courses"], e["_guides"], e["_columns"] = [], [], []
            e["_area"] = area_from_address(facts.get("address"))
            e["_road"] = road_from_address(facts.get("address"))
            e["_group"] = category_group(e)
            e["_images"] = [i for i in e.get("images") or [] if license_allowed(i.get("license"), self.allowed_images)]
            # Several photos under the same TourAPI title get a number, so their alt texts differ.
            alts = Counter(squash_ws(i.get("alt")) or e["name"] for i in e["_images"])
            nth: Counter = Counter()
            for i in e["_images"]:
                a = squash_ws(i.get("alt")) or e["name"]
                nth[a] += 1
                i["_alt"] = f"{a} 사진 {nth[a]}" if alts[a] > 1 else a
            e["_themes"] = [self.theme_by_slug[t] for t in e.get("themes") or [] if t in self.theme_by_slug]
            first = (e.get("themes") or [None])[0] if e.get("kind") == "attraction" else e.get("kind")
            e["_visual"] = VISUALS.get(first) or VISUALS.get(e["_group"]) or ("sight", "pin")
            e["_chips"] = self.chips(e)
            geo = e.get("geo") or {}
            e["_geo"] = geo if geo.get("lat") is not None and geo.get("lng") is not None else None
            e["_index_ok"], e["_index_reasons"] = index_status(e)
            e["_facts_checked"] = facts_checked_date(e)
            # a point read from another source than TourAPI (tools/official_coords.py: 군산시 문화관광) carries the day
            # it was read; the page shows that source, so its date counts as the page's (sitemap lastmod, IndexNow)
            geo_day = geo.get("checked_at") if e["_geo"] and geo.get("source") not in (None, "", "TourAPI") else None
            e["_page_date"] = latest(e.get("reviewed_at"), e["_facts_checked"], geo_day)
            # production only: a page below the index criteria is noindex and left out of sitemap/llms
            e["_noindex"] = mode == "production" and not e["_index_ok"]
        # Footer/about/llms.txt "원문 수집일": the configured date, else the latest one among built pages.
        source = self.site.get("source") or {}
        self.collected_at = squash_ws(source.get("collected_at")) or max(
            (squash_ws((e.get("original") or {}).get("collected_at")) for e in self.entities), default="")
        self.site_view = {**self.site, "source": {**source, "collected_at": self.collected_at}}
        for c in self.courses:
            c["_path"] = f"/courses/{c['slug']}/"
            c["_url"] = self.abs(c["_path"])
            c["_page_date"] = latest(c.get("reviewed_at"), (c.get("original") or {}).get("collected_at"))
        for g in self.guides:
            g["_path"] = f"/guides/{g['slug']}/"
            g["_url"] = self.abs(g["_path"])
            g["_page_date"] = latest(g.get("reviewed_at"), g.get("checked_at"))
        for col in self.columns:
            col["_path"] = f"/columns/{col['slug']}/"
            col["_url"] = self.abs(col["_path"])
            col["_page_date"] = latest(col.get("published_at"), col.get("reviewed_at"), col.get("checked_at"))
        self.ent_by_slug = {e["slug"]: e for e in self.entities}
        self.ent_by_id = {e["id"]: e for e in self.entities}   # related.json's place_id (present.related_places)
        # places that belong together (data part_of, pipeline/relations.py, operator decision 2026-10-16): _parent,
        # _rel, _parts, _same, _alias_of, _family on every built place; a parent outside the build drops the relation
        self.relation_warnings = relations.resolve(self.entities_all, self.entities)
        # every record by slug, built or not: a nearby list names places by slug, and the providers of their points
        # are named under it (schema.nearby_geo_providers)
        self.ent_all_by_slug = {e["slug"]: e for e in self.entities_all if e.get("slug")}
        # dated facility notices (data/<region>/notices.json, pipeline/notices.py, operator decision 2026-10-15): shown
        # near the key facts in every language until their `until` date; never part of a place record or its hash
        # combined tickets' fee tables (data/<region>/tickets.json, pipeline/tickets.py, review 2026-10-17): the chat
        # knowledge's prices, ages and free rules per ticket, and its fee_total tool
        self.tickets = tickets.load(data_dir)
        by_id = {e["id"]: e for e in self.entities}
        for e in self.entities:   # its own fee beside the narrowest one on the first screen (present.slot_value 'fee')
            e["_tickets"] = tickets.for_place(self.tickets, e["id"], by_id)
        self.notices_all = notices.load(data_dir)
        self.notices = notices.active(self.notices_all, self.today)
        for e in self.entities:
            e["_notices"] = [{"id": n["id"], "kind": n["kind"], "text": notices.ko_text(n), "provider": n["provider"],
                              "url": n["url"], "n": n} for n in notices.for_place(self.notices, e["id"])]
        homepages = Counter(_url_key(web_url((x.get("facts") or {}).get("homepage")))
                            for x in self.entities_all if not x.get("duplicate_of"))
        self.shared_homepages = {k for k, n in homepages.items() if k and n > 1}
        self.ent_by_cid = {str((e.get("tourapi") or {}).get("contentid")): e for e in self.entities
                           if (e.get("tourapi") or {}).get("contentid")}
        for c in self.courses:
            for s in c.get("stops") or []:
                target = self.ent_by_slug.get(s.get("place_slug"))
                if target and c not in target["_courses"]:
                    target["_courses"].append(c)
        for g in self.guides:
            for it in g.get("items") or []:
                if it.get("place_slug") in self.ent_by_slug:
                    self.ent_by_slug[it["place_slug"]]["_guides"].append(g)
        for c in self.courses:  # cover: the first linked stop that has a licensed photo
            c["_cover"] = next((self.ent_by_slug[s["place_slug"]]["_images"][0] for s in c.get("stops") or []
                                if self.ent_by_slug.get(s.get("place_slug"))
                                and self.ent_by_slug[s["place_slug"]]["_images"]), None)
        self.guide_by_id = {g["id"]: g for g in self.guides}
        self.col_by_id = {c["id"]: c for c in self.columns}
        self.col_by_slug = {c["slug"]: c for c in self.columns}
        for col in self.columns:
            for it in col.get("items") or []:
                if it.get("place_slug") in self.ent_by_slug:
                    self.ent_by_slug[it["place_slug"]]["_columns"].append(col)
        self.series = event_series(self.events, self)
        for e in self.entities:
            e["_events"] = [sr for sr in self.series if e["slug"] in sr["place_slugs"]]
        # YouTube videos (data/gunsan/videos.json, each checked through YouTube oEmbed): linked from places and
        # event pages, all of them on /videos/. Only the title, channel and link are ours to show.
        self.videos = load_videos(data_dir)
        for e in self.entities:
            e["_videos"] = sorted((v for v in self.videos if e["slug"] in (v.get("place_slugs") or [])),
                                  key=video_rank)[:VIDEOS_PER_PAGE]
        for sr in self.series:
            sr["videos"] = sorted((v for v in self.videos
                                   if sr["keys"] & {normalize_name(YEAR_PREFIX.sub("", squash_ws(n)))
                                                    for n in v.get("event_names") or []}),
                                  key=video_rank)[:VIDEOS_PER_PAGE]
        # 해외에서 본 군산 (data/<region>/abroad.json, owner 2026-10-13): foreign press and social posts, shown as our
        # own one-line note + the link (+ the outlet's og:image, from its address; posts load the service's official
        # embed near the screen). Published only.
        self.abroad = load_abroad(data_dir)
        self.abroad_highlights = load_abroad_highlights(data_dir, self.abroad)   # the /abroad/ highlights row
        self.abroad_videos = [v for v in self.videos if (v.get("lang") or "ko") != "ko"]
        self.art = art.slots(data_dir)   # AI art by slot (pipeline/art.py); an empty slot renders as before
        # the homes' centre question card (pipeline/ask.py, owner 2026-10-13): its starter questions, or None when the
        # region has no ask.json or no places (the assistant answers from them; the Korean box falls back to /search/,
        # which only a build with places has) — then the homes render as before
        self.ask = ask.load(data_dir) if (data_dir / "ask.json").exists() and self.entities else None
        series_by_slug = {sr["slug"]: sr for sr in self.series}
        for e in self.entities:
            e["_abroad"] = [a for a in self.abroad if e["slug"] in a["place_slugs"]]
        for a in self.abroad:
            a["_places"] = [self.ent_by_slug[s] for s in a["place_slugs"] if s in self.ent_by_slug]
            a["_series"] = [series_by_slug[s] for s in a.get("event_slugs") or [] if s in series_by_slug]
        for h in self.abroad_highlights:   # an article card on /abroad/ shows its highlight's quotation too (2026-10-14)
            if h["quote"]:
                h["item"]["_quote"] = {"text": h["quote"], "lang": h["quote_lang"]}
        # 군산각 블로그 (data/<region>/blog.json from tools/blog_sync.py, operator 2026-10-30): the operator's Naver blog
        # as its posts' titles and links only — no text, no photos (their sources are not known), never a fact. A place
        # gets the posts that link to its page or name it; a guide, column or course page the posts that link to it.
        self.blog = load_blog(data_dir)
        self.blog_by_path: dict[str, list[dict]] = {}
        for p in (self.blog or {}).get("posts") or []:
            for link in p["links"]:
                self.blog_by_path.setdefault(link, []).append(p)
        for e in self.entities:
            e["_blog"] = blog_for_place(self, e)
        self.lists = {k: [e for e in self.entities if e.get("kind") == k] for k in LISTS}
        self.tourapi_used = any(
            any("TourAPI" in str((src or {}).get("provider", ""))
                for src in [e.get("facts_source"), *(e.get("fact_sources") or {}).values(),
                            *(a for alts in (e.get("fact_alternatives") or {}).values() for a in alts or [])])
            or any(i.get("source") == "TourAPI" for i in e["_images"]) for e in self.entities)
        self.pages: list[tuple[str, str]] = []  # (path, lastmod) — the sitemap
        self.stats = {"entities": len(self.entities),
                      "excluded_entities": sum(1 for x in self.entities_all if x not in self.entities
                                               and not x.get("duplicate_of")),
                      "index": index_counts(self.entities), "dead_links": len(self.dead_dropped)}
        # Public parking lots and bus stops near each place (parking_lots.json, nearby.json; both optional). Shown on
        # the place page after the map (present.access_vm); not facts of the place, so the index criteria never see them.
        parking = _load(data_dir / "parking_lots.json", {})
        self.parking_lots = {l["id"]: l for l in parking.get("lots") or []}
        self.parking_contacts = parking.get("contacts") or []
        nearby = _load(data_dir / "nearby.json", {})
        self.nearby_meta = nearby.get("_meta") or {}
        self.nearby = {k: v for k, v in nearby.items() if not k.startswith("_")}
        # the city bus timetable's reference-stop first and last times (transit.json, optional; QA 2026-10-15 F09 and
        # operator decision 4): the course pages' '차 없이 다니기' block; checked against guide-31 by pipeline.validate
        self.transit = _load(data_dir / "transit.json", {}) or {}
        # the place page's day card (present.today_vm, operator 2026-10-31): sunrise·sunset and tides (almanac.json),
        # the crowd forecast (crowd.json) and beaches (beaches.json) — each optional, a file not made yet is empty
        self.almanac = _load(data_dir / "almanac.json", {}) or {}
        # /transport/ 군산 교통 시간표 (transport_tago.json: 국토교통부 TAGO, pipeline/timetables.py) — optional
        self.transport = _load(data_dir / "transport_tago.json", {}) or {}
        self.crowd = _load(data_dir / "crowd.json", {}) or {}
        self.beaches = _load(data_dir / "beaches.json", {}) or {}
        self.ferry = _load(data_dir / "ferry.json", {}) or {}   # the routes that call at an island place (Korean card)
        # 영업 확인 (licenses.json: 행정안전부 인허가, 식품안심업소) and 이어서 많이 간 곳 (related.json: 한국관광공사 연관
        # 관광지) on the place page (present.license_vm, related_vm; operator 2026-10-31) — optional files
        self.licenses = _load(data_dir / "licenses.json", {}) or {}
        self.related_trips = _load(data_dir / "related.json", {}) or {}
        # View-model fields for the redesigned templates (pipeline/present.py, computed once): e["_type"],
        # e["_photos"] (with image_sizes.json), e["_line"], e["_region"], S.anchors, S.course_vms, S.warnings …
        self.warnings: list[str] = list(self.relation_warnings)
        present.prepare(self, data_dir)
        self.common_vm = present.common_vm(self)
        # /sun/ 군산 일출·일몰 시간 and /transport/ 군산 교통 시간표 (pipeline/timetables.py, operator 2026-10-31): their
        # view models, None without data — the pages, the footer's links and the place / guide links follow them
        self.tt_sun = timetables.sun_vm(self)
        self.tt_transport = timetables.transport_vm(self)
        # the tab panel (operator 2026-10-31 '적용하자'; present.side_vm, templates/_side.html.j2): its groups, the day card's
        # next event and sunrise · sunset, the weather module's hook — once per build
        self.side = present.side_vm(self)
        self.en = None  # the English site, set by build()/validate() (pipeline/en_site.load_all)
        self.intl = None  # every version besides Korean (en_site.Intl): hreflang sets and the language menu

    def abs(self, path: str) -> str:
        return self.site_url + quote(path)

    @staticmethod
    def chips(e: dict) -> list[dict]:
        """Up to three short facts for cards. A chip shows the whole value or is not shown (a value cut
        mid-way is a wrong answer when lifted); when no value fits, one label-only chip points to the page."""
        facts = e.get("facts") or {}
        order = {"attraction": ("usetime", "usetime_restdate", "usefee", "restdate", "parking", "expagerange"),
                 "stay": ("checkin", "parking", "infocenter"),
                 "food": ("menu", "usetime_restdate", "usetime", "parking_seats")}.get(e.get("kind"), ())
        out, long_key = [], ""
        for key in order:
            if facts.get(key):
                value = squash_ws(facts[key])
                if len(value) <= 26:
                    out.append({"label": fact_label(e, key), "value": value})
                else:
                    long_key = long_key or key
        if not out and long_key:
            out = [{"label": fact_label(e, long_key), "value": "장소 페이지에서 확인", "more": True}]
        return out[:3]

    def common(self, page: dict, page_kind: str) -> dict:
        return {"site": self.site_view, "page": page, "page_kind": page_kind, "noindex": self.cfg["noindex"],
                "banner": self.cfg["banner"], "mode": self.mode, "has_events": bool(self.events),
                "has_guides": bool(self.guides), "has_columns": bool(self.columns), "has_courses": bool(self.courses), "build_date": self.today,
                "list_nav": [(k, v["path"], v["title"]) for k, v in LISTS.items() if self.lists[k] or k == "attraction"],
                "tourapi_used": self.tourapi_used, "has_map": bool(self.entities), "has_videos": bool(self.videos),
                "has_search": bool(self.entities), "has_abroad": bool(self.abroad or self.abroad_videos),
                "blog": self.blog,
                "has_plan": bool(self.entities),   # /plan/, the AI course planner (Korean pages)
                "has_sun": bool(self.tt_sun), "has_transport": bool(self.tt_transport),   # /sun/ · /transport/
                "tt_guides": timetables.TRANSPORT_GUIDES if self.tt_transport else (),   # guides that link /transport/
                "art_slots": art.for_lang(self.art, "ko"), "side": self.side, **self.common_vm,
                **present.page_chrome(page_kind, bool(self.courses))}

    def name_related(self, e: dict) -> list[dict]:
        """Places whose name contains this place's full name or is contained in it ('이름이 비슷한 곳'), never the
        page's own family (its parent, parts and same-building partners have their own lines, pipeline/relations.py)
        and never an alias beside its parent."""
        key = lambda x: "".join(squash_ws(x["name"]).split())
        mine = key(e)
        if len(mine) < 3:
            return []
        out = [x for x in self.entities if x is not e and len(key(x)) >= 3 and (
            (key(x).startswith(mine) and e.get("kind") == "attraction")
            or (mine.startswith(key(x)) and x.get("kind") == "attraction"))]
        out = relations.keep_rows(e, sorted(out, key=lambda x: (x.get("kind") != "attraction", x["name"])), lambda x: x)
        return out[:4]

    def area_neighbours(self, e: dict) -> dict:
        """Places in the same 읍·면·동 by address, or on the same road when the address names no 읍·면·동
        (no coordinates, so no distance)."""
        field = "_area" if e["_area"] else "_road"
        if not e[field]:
            return {}
        # never the page's own family nor an alias beside its parent (pipeline/relations.py), as the nearby rows
        same = relations.keep_rows(e, [x for x in self.entities if x is not e and x[field] == e[field]], lambda x: x)
        rank = lambda x: (x.get("tier") != "full", not x.get("summary"), x["name"])
        out = {k: sorted((x for x in same if x.get("kind") == k), key=rank)[:n]
               for k, n in (("attraction", 4), ("stay", 3), ("food", 3))}
        out["label"] = e["_area"] or f"도로명 주소({e['_road']})"
        return out


def index_counts(entities: list[dict]) -> dict:
    """Index criteria tally for build/validate stats (judged in every mode; enforced in production)."""
    reasons = Counter(r for e in entities for r in e["_index_reasons"])
    unreviewed_only = [INDEX_REASONS["unreviewed"]]
    return {"entity_pages": len(entities), "indexable": sum(1 for e in entities if e["_index_ok"]),
            "content_ok_awaiting_review": sum(1 for e in entities if e["_index_reasons"] == unreviewed_only),
            "top_reasons": reasons.most_common(5)}


def map_points(items: list[dict]) -> list[dict]:
    return [{"lat": e["_geo"]["lat"], "lng": e["_geo"]["lng"], "name": e["name"], "url": e["_path"],
             "kind": e.get("kind", "")} for e in items if e.get("_geo")]


# ---------------------------------------------------------------- contexts
def qualified_name(e: dict, region: str) -> str:
    """Name with the city in it for the title: the name itself, a visible other name that holds both the city
    and the name (군산근대역사박물관), else '군산 {name}'. Presentation only; the h1 stays e.name."""
    name = e["name"]
    if not region or region in name:
        return name
    key = "".join(name.split())
    for alt in jsonld.alternate_names(e):
        if region in alt and key in "".join(alt.split()):
            return alt
    return f"{region} {name}"


# ---------------------------------------------------------------- meta description (Korean pages)
# <meta name="description"> and og:description of every Korean page: at most DESC_MAX characters (owner 2026-10-14 —
# Naver Search Advisor: '80자 이내로 설명문을 작성해주세요'), answer first, made only of what the page itself shows.
# Whole sentences or one fact line: a sentence is never cut and never ends in '…'. JSON-LD descriptions are separate
# (they repeat the on-screen summary, pipeline.validate) and are not shortened. The other language versions keep their
# own rule (pipeline/en_site.py answer_description, locale desc_max).
DESC_MAX = 80
FACT_VALUE_MAX = 30   # a fact value longer than this stays on the page, not in the description


def fit_sentences(text: str | None, limit: int = DESC_MAX) -> str:
    """The text's whole sentences from the start while the total stays within `limit`; '' when the first one alone
    is longer (a sentence is never cut)."""
    out = ""
    for s in summary_sentences(squash_ws(text)):
        nxt = f"{out} {s}" if out else s
        if len(nxt) > limit:
            break
        out = nxt
    return out


def first_fit(*candidates: str | None, limit: int = DESC_MAX) -> str:
    """The first non-empty candidate within `limit` (each one a whole sentence or fact line); '' when none fits."""
    return next((c for c in candidates if c and len(c) <= limit), "")


def full_stop(text: str | None) -> str:
    """A heading or fact line as a sentence: one final '.', unless it already ends in . ! or ?."""
    t = squash_ws(text)
    return t if not t or t.endswith((".", "!", "?")) else f"{t}."


def settled_facts(rows: list[dict]):
    """(row, value as the page shows it) for each row whose value no other source contradicts ('also' values — a second
    dish — do not contradict) and is at most FACT_VALUE_MAX characters."""
    for r in rows:
        if not r["value"] or any(not a["also"] for a in r["alternatives"]):
            continue
        value = squash_ws(display_value(r["key"], r["value"])).rstrip(".")
        if value and len(value) <= FACT_VALUE_MAX:
            yield r, value


def place_head(e: dict) -> str:
    """'<이름>: <동> <유형>' as the place page's first screen shows them (동 from the address; a stay's type is a kind of
    lodging, an attraction's or restaurant's type is followed by its kind: '일식 음식점', '박물관·전시 관광지')."""
    kind = e.get("kind", "attraction")
    typ = e.get("_type") or ""
    label = typ if typ and kind == "stay" else " ".join(x for x in (typ, KIND_LABELS.get(kind, "")) if x)
    return f"{e['name']}: " + " ".join(x for x in (e.get("_area") or "", label) if x)


def place_line(head: str, rows: list[dict], limit: int = DESC_MAX) -> str:
    """One fact line, '<이름>: <동> <유형>, <라벨> <값>, ….': the settled short values in the page's key-row order
    (운영시간·쉬는 날·요금·주차·체크인·대표 메뉴 …, then 전화) while the line stays within `limit`."""
    out = squash_ws(head)
    for r, value in settled_facts(rows):
        label = "전화" if r["key"] == "infocenter" else r["label"]  # the first screen's key line calls it 전화
        nxt = f"{out}, {label} {value}"
        if len(nxt) + 1 <= limit:
            out = nxt
    return full_stop(out)


DESC_SHORT = 40      # under this a description takes one more whole sentence or fact while it fits
# a place description still under this after its facts takes the phone, then the summary's next sentence, while they
# fit (Search Console 2026-10-22: 112 place descriptions used under 60 of the 80 characters — a short snippet)
DESC_FILL = 60
FIGURE = re.compile(r"\d+(?:[:.,]\d+)*")
WORD = re.compile(r"[0-9A-Za-z가-힣]+(?:[:.,]\d+)*")
# how a summary says a value in its own words (compared without spaces): '쉬는 날 없이 상시 개방합니다' says 연중무휴
SAID_AS = {"연중무휴": ("쉬는날없이", "쉬는날이없", "쉬는날도없", "상시개방", "상시열려"),
           "상시개방": ("언제든", "상시열려"),
           "무료": ("요금없이", "요금이없", "요금은없", "입장료없이", "요금을받지않")}
PARKING_SAID_AS = {"가능": ("주차할수있", "주차도할수있", "차를세울수", "주차공간"), "불가": ("주차는할수없", "주차할수없")}


def said_already(key: str, value: str, said: str) -> bool:
    """The description's sentences already say this fact value, compared without spaces ('~' and '–' alike): every
    word of the value ('매주 토요일~일요일과 법정공휴일에는 쉽니다' says '매주 토요일~일요일 / 법정공휴일'), every
    figure in it ('좌석 160석, 주차 100대' says '100대/160석'; '입실 시간은 14:00, 퇴실 시간은 12:00' says '- 입실 14:00
    - 퇴실 12:00'), or the summary's usual wording of it (SAID_AS; a parking row's 가능·불가, PARKING_SAID_AS). A short
    value said in another sense ('체험이 가능' for 주차 가능) only leaves that fact out of the description."""
    v, s = (re.sub(r"\s+", "", t.replace("–", "~")) for t in (value, said))
    words = WORD.findall(v)
    if words and all(w in s for w in words):
        return True
    wordings = SAID_AS.get(v, ()) + (PARKING_SAID_AS.get(v, ()) if key.startswith("parking") else ())
    if any(w in s for w in wordings):
        return True
    figures = FIGURE.findall(v)
    return bool(figures) and set(figures) <= set(FIGURE.findall(s))


def answer_description(summary: str, fallback: str, key_rows: list[dict], limit: int = DESC_MAX,
                       head: str = "", extra_rows: list[dict] | tuple = ()) -> str:
    """A place page's description, within `limit`; a sentence is never cut, no boilerplate tail.
    - The summary's first sentence when it fits (the next one too while under DESC_SHORT), plus up to three short (≤30
      chars) key-row values that no other source contradicts and the summary does not already say, each only while the
      total fits; still under DESC_FILL, an extra row (the phone the first screen shows) the same way, then the
      summary's next whole sentences while they fit.
    - A first sentence longer than `limit`: the place's fact line instead (place_line: head + key rows + extra rows);
      still under DESC_SHORT, the summary's next whole sentences while they fit. Without a head, the fallback sentence."""
    sentences = summary_sentences(squash_ws(summary)) or [fallback]
    out = sentences[0]
    if len(out) > limit:
        if not head:
            return fallback
        out = place_line(head, list(key_rows) + list(extra_rows), limit)
        for nxt in sentences[1:]:
            if len(out) >= DESC_FILL or len(out) + 1 + len(nxt) > limit:
                break
            out = f"{out} {nxt}"
        return out
    used = 1
    for nxt in sentences[1:]:
        if len(out) >= DESC_SHORT or len(out) + 1 + len(nxt) > limit:
            break
        out, used = f"{out} {nxt}", used + 1
    added, said = 0, out
    for r, value in settled_facts(key_rows):
        if added == 3:
            break
        sentence = f"{r['label']}: {value}."
        if len(out) + 1 + len(sentence) > limit:
            continue
        if said_already(r["key"], value, said):  # the summary already says it (the same menu, the same hours)
            continue
        out, added = f"{out} {sentence}", added + 1
    for r, value in settled_facts(extra_rows):
        sentence = f"{'전화' if r['key'] == 'infocenter' else r['label']}: {value}."
        if len(out) < DESC_FILL and len(out) + 1 + len(sentence) <= limit and not said_already(r["key"], value, said):
            out = f"{out} {sentence}"
    for nxt in sentences[used:]:   # still short: the summary's next whole sentence
        if len(out) >= DESC_FILL or len(out) + 1 + len(nxt) > limit:
            break
        out = f"{out} {nxt}"
    return out


def guide_description(g: dict, S, limit: int = DESC_MAX) -> str:
    """A guide's description, the first of these within `limit` (each whole; from the guide's own page):
    1. the summary's first sentence (the answer line the page shows big);
    2. the first body heading — the content's answer sentence, shown verbatim on the page — when it holds a figure
       (a heading without one, '작품별 촬영지: 어느 작품을 어디서 찍었나', is a topic, not the answer); under
       DESC_SHORT the next heading follows while it fits;
    3. the guide's short answer (present.guide_answer, the line /guides/ shows) when every figure in it is written on
       the guide page;
    4. the title as one line, '<question>: <its list>.' (a title with ' — ');
    5. '<label>: <place>·<place> 등 <n>곳.' — the label, the first names of its place list and the list's count."""
    lead = (present.ko_sentences(present.decaution(g.get("summary"))) or [""])[0]
    heads = [full_stop(b.get("heading")) for b in g.get("body") or [] if squash_ws(b.get("heading"))]
    heading = heads[0] if heads and present.figures(heads[0]) else ""
    for nxt in heads[1:] if heading else []:  # under DESC_SHORT: the next heading too, while it fits
        if len(heading) >= DESC_SHORT or len(heading) + 1 + len(nxt) > limit:
            break
        heading = f"{heading} {nxt}"
    answer = present.guide_answer(g, S)["answer"]
    if not present.figures(answer) <= present.figures(present.guide_text(g)):
        answer = ""
    title = squash_ws(g.get("title"))
    title_line = ": ".join(title.split(" — ", 1)) if " — " in title else ""
    found = first_fit(lead, full_stop(heading), full_stop(answer), full_stop(title_line), limit=limit)
    if found:
        return found
    label = squash_ws(g.get("label")) or title
    names = [squash_ws((S.ent_by_slug.get(it.get("place_slug") or "") or {}).get("name") or it.get("name"))
             for it in g.get("items") or []]
    names = [n for n in names if n]
    out = ""
    for k in range(1, len(names) + 1):
        line = f"{label}: {'·'.join(names[:k])}{' 등' if k < len(names) else ''} {len(names)}곳."
        if len(line) > limit:
            break
        out = line
    return out or first_fit(full_stop(title), full_stop(label), limit=limit) or full_stop(label)


def near_target(S, n: dict) -> dict | None:
    """The built place a nearby entry points at (by slug, else by TourAPI contentid), or None."""
    return S.ent_by_slug.get(n.get("internal_slug") or "") or S.ent_by_cid.get(str(n.get("contentid")))


def entity_ctx(e: dict, S: State) -> dict:
    kind = e.get("kind", "attraction")
    site, region = S.site, S.site.get("region", "")
    facts = e.get("facts") or {}
    rows = lambda keys: [r for r in (fact_row(e, k) for k in keys) if r]
    key_rows = rows(KEY_ROW_KEYS)
    shown = {r["key"] for r in key_rows}
    info_rows = rows([k for k in FACT_ORDER if k not in shown])
    fit_rows = rows(FIT_ORDER)
    all_rows = key_rows + info_rows + fit_rows
    alt_keys = {r["key"] for r in all_rows if r["alternatives"]}
    missing = [FACT_LABELS[k] for k in KEY_FACTS_BY_CATEGORY.get(e.get("category"), KEY_FACTS.get(kind, ()))
               if not has_fact(e, k) and k not in alt_keys]
    fact_srcs = fact_source_groups(all_rows)
    facts_checked = facts_checked_date(e, all_rows)
    geo = e["_geo"] or {}
    mid = e.get("map_ids") or {}
    links = build_links(e["name"], geo.get("lat"), geo.get("lng"), region=region,
                        address=facts.get("address", ""), naver_place_id=mid.get("naver_place_id", ""),
                        google_place_id=mid.get("google_place_id", ""),
                        tmap_scheme=site.get("tmap_scheme", DEFAULT_TMAP_SCHEME),
                        kakao_place_id=mid.get("kakao_place_id", ""))
    links = sorted(links, key=lambda l: (not l["precise"], l["role"] != "map"))
    nearby = []
    # the page's own family (parent, parts, same-building partners) has its own lines, and an alias never shows beside
    # its parent (pipeline/relations.py): both left out of the nearby rows
    for n in relations.keep_rows(e, e.get("nearby") or [], lambda n: near_target(S, n)):
        target = near_target(S, n)
        track = {"stay": "stay_click", "food": "food_click"}.get(n.get("kind"), "nearby_click")
        nearby.append({**n, "href": target["_path"] if target else search_link(n["name"], region),
                       "internal": bool(target), "track": track})
    orig = e.get("original") or {}
    show_original = bool(orig.get("text")) and license_allowed(orig.get("license"), S.allowed_original)
    images = e["_images"]
    official = e.get("official") or {}
    sources = []
    if orig.get("source_url") or official.get("source_url"):
        sources.append({"label": f"{orig.get('source_name') or site['source']['name']} 원문",
                        "url": orig.get("source_url") or official.get("source_url")})
    if official.get("visitkorea_url"):
        sources.append({"label": "대한민국 구석구석(한국관광공사)", "url": official["visitkorea_url"]})
    if official.get("homepage"):
        sources.append({"label": "공식 홈페이지", "url": web_url(official["homepage"])})
    themes = e["_themes"]
    list_cfg = LISTS.get(kind, LISTS["attraction"])
    crumbs = [("홈", S.site_url + "/"), (list_cfg["title"], S.abs(list_cfg["path"])), (e["name"], e["_url"])]
    # a seat count alone ('30석') answers no parking question: no '주차' in the title
    title_rows = [r["key"] for r in key_rows if r["key"] in TITLE_LABELS
                  and not (r["key"] == "parking_seats" and parking_seats_half(e) == "seats")]
    labels = list(dict.fromkeys(title_label(kind, k) for k in title_keys(kind, title_rows)))[:3]
    title = f"{qualified_name(e, region)} {'·'.join(labels) or '방문 정보·지도'}"  # <title> adds ' | site_name' (base)
    summary = e.get("summary") or ""
    fallback = f"{josa(e['name'], '은/는')} {site.get('locality', '')}{' ' + e['_area'] if e['_area'] else ''}에 있는 {KIND_LABELS.get(kind, '')}입니다."
    # a first sentence over DESC_MAX: the fact line (head + key rows, then the phone the first screen shows)
    description = answer_description(summary, fallback, key_rows, head=place_head(e), extra_rows=rows(["infocenter"]))
    faqs = [f for f in e.get("faq") or [] if f.get("q") and f.get("a")]
    # facts.homepage joins sameAs only when it is this place's own site: a homepage several places share
    # (the city's tourism portal, a museum group's site) is not the same entity.
    own_homepage = web_url(facts.get("homepage"))
    if _url_key(own_homepage) in S.shared_homepages:
        own_homepage = ""
    same_as = [orig.get("source_url"), official.get("visitkorea_url"), web_url(official.get("homepage")) or own_homepage]
    shown_images = images[:7]  # hero + gallery images[1:7], exactly what the page renders
    kakao = next((l["url"] for l in links if l["key"] == "kakao" and l["precise"]), "")
    graph = jsonld.place_graph(e, site, S.site_url, e["_url"], title, crumbs, shown_images, same_as,
                               [orig.get("source_url")], faqs, e.get("reviewed_at") or "", facts_checked, kakao,
                               parent=e.get("_parent") if e.get("_rel") == "inside" else None, parts=e.get("_parts") or ())
    page = {"title": title, "description": description, "canonical": e["_url"],
            "og_type": "article", "image": og_image(images),
            "geo": e["_geo"], "geo_placename": f"{site.get('locality', '')} {e['name']}".strip(),
            "jsonld": [jsonld.dumps(graph)], "crumbs": crumbs, "map": bool(e["_geo"]),
            "videos": bool(place_media(e)["videos"])}
    if e["_noindex"]:
        page["robots"] = "noindex, follow"
    area = S.area_neighbours(e)
    ctx = {"e": e, "kind": kind, "facts": facts, "key_rows": key_rows, "info_rows": info_rows,
            "fit_rows": fit_rows, "alt_rows": [r for r in all_rows if any(not a["also"] for a in r["alternatives"])],
            "fact_srcs": fact_srcs, "facts_checked": facts_checked,
            "alt_names": jsonld.alternate_names(e), "index_note": index_note(e),
            "missing": missing, "links": links, "precision": precision_summary(links),
            "nearby_sights": [n for n in nearby if n.get("kind") == "attraction"],
            "nearby_biz": [n for n in nearby if n.get("kind") in ("stay", "food")],
            "nearby_source": e.get("nearby_source") or {},
            "area_sights": area.get("attraction", []), "area_stays": area.get("stay", []),
            "area_food": area.get("food", []), "area_label": area.get("label", ""), "related": S.name_related(e),
            "courses": e["_courses"], "guides": e["_guides"], "themes": themes, "events": e["_events"],
            "orig": orig, "show_original": show_original, "images": images,
            "media": place_media(e), "faqs": faqs, "sources": sources,
            "src_labels": source_labels(e),
            "facts_source": e.get("facts_source") or {},
            "points": map_points([e]), "page": page}
    # Redesign view model (pipeline/present.py): all of it as `p`, and each key at the top level unless an
    # existing key already has that name (existing keys keep their meaning; `points` stays the map_box list,
    # the redesign's {self, near, anchors} is `place_points`).
    vm = present.place_vm(S, e, ctx)
    if S.tt_sun and (vm.get("today") or {}).get("sun"):   # the day card's sunset leads to /sun/ (pipeline/timetables.py)
        vm["today"]["sun_page"] = timetables.SUN_PATH
    ctx.update({k: v for k, v in vm.items() if k not in ctx})
    # inside `p` the names the prototype templates use are free: p.faqs, p.points, p.segs (the course segments of
    # the 주변·함께 가기 chapter, present.route_segs)
    ctx["p"] = {**vm, "faqs": vm["faq_vm"], "points": vm["place_points"], "segs": vm["route_segs"]}
    return ctx


def place_media(e: dict) -> dict:
    media = dict(e.get("media") or {})
    videos = list(media.get("videos") or [])
    seen = {v.get("youtube_id") for v in videos}
    media["videos"] = videos + [v for v in e.get("_videos") or [] if v["youtube_id"] not in seen]
    return media


# ---------------------------------------------------------------- writers
def _write(out: Path, path: str, html: str) -> None:
    target = out / path.strip("/") / "index.html" if path.endswith("/") else out / path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    # a title never starts a line with '·' (textutil.keep_dots)
    target.write_text(keep_dots(html) if target.suffix == ".html" else html, "utf-8")


def _render(env, S: State, out: Path, template: str, path: str, page: dict, page_kind: str,
            lastmod: str | None = None, in_sitemap: bool = True, **ctx) -> None:
    """lastmod is a date from data (확인일·검수일 — kept in the sitemap and JSON-LD, not shown on the page since the
    operator decision of 2026-10-09); None (unknown) means no <lastmod>, never the build date.
    With other language versions (S.intl, pipeline/en_site.py): hreflang links when the page has a twin, and the
    language menu (each version's counterpart, else its list of the same kind or its home, with a 'not translated'
    note: Intl.menu)."""
    intl = getattr(S, "intl", None)
    if intl:
        page.setdefault("alternates", intl.alternates(path))
        ctx.setdefault("langs", intl.menu(path))
    og = None if page.get("image") else art.og_fallback(art.for_lang(S.art, "ko"), path, "ko")
    if og:  # a page without a photo of its own: the link-preview illustration (never a place page)
        page.update(image=S.abs(og["src"]), image_alt=og["alt"], image_w=og["w"], image_h=og["h"])
    html = env.get_template(template).render({**S.common(page, page_kind), **ctx})  # a page's own keys win
    _write(out, path, html)
    if path != "/404.html" and in_sitemap:
        S.pages.append((path, lastmod or None))


def _simple_page(S: State, path: str, title: str, description: str, crumbs: list, item_urls: list[str] | None = None,
                 **extra) -> dict:
    return {"title": title, "description": description, "canonical": S.abs(path), "crumbs": crumbs,
            "jsonld": [jsonld.dumps(jsonld.simple_page_graph(S.site_url, S.abs(path), title, crumbs, item_urls))],
            **extra}


def _prepare_out(out: Path, data_dir: Path) -> None:
    out = out.resolve()
    if out in (ROOT, Path.cwd().resolve()) or out in data_dir.resolve().parents or out == data_dir.resolve():
        raise SystemExit(f"출력 폴더가 위험한 위치입니다: {out}")
    if out.exists():
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise SystemExit(f"{out} 에 이 빌드가 만들지 않은 파일이 있어 지우지 않습니다. 빈 폴더를 지정하세요.")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("generated by pipeline.build\n", "utf-8")


def robots_txt(S: State) -> str:
    if S.cfg["noindex"]:
        return "# 미리보기/샘플 빌드: 모든 수집 차단\nUser-agent: *\nDisallow: /\n"
    pol = S.site.get("crawler_policy") or {}
    search = pol.get("allow_search_bots", SEARCH_BOTS)
    training = [] if pol.get("allow_training_bots") else pol.get("training_bots", TRAINING_BOTS)
    lines = [f"# {S.site['site_name']} robots.txt (생성 {S.today})",
             "# 검색·답변 엔진과 사용자 요청 크롤러: 허용"]
    lines += [f"User-agent: {b}" for b in search] + ["Allow: /", ""]
    if training:
        lines += ["# 학습 전용 크롤러: 원문 권리가 원 출처에 있어 기본 차단 (site.json crawler_policy로 변경)"]
        lines += [f"User-agent: {b}" for b in training] + ["Disallow: /", ""]
    else:
        lines += ["# AI 학습·생성형 답변 크롤러: 허용 (운영자 결정, site.json crawler_policy)"]
        lines += [f"User-agent: {b}" for b in pol.get("ai_use_bots", AI_USE_BOTS)] + ["Allow: /", ""]
    lines += ["User-agent: *", "Allow: /", "", f"Sitemap: {S.site_url}/sitemap.xml", f"Sitemap: {S.site_url}/sitemap-ko.xml", ""]
    return "\n".join(lines)


def sitemap_xml(S: State, ko_only: bool = False) -> str:
    intl_prefixes = tuple(f"/{c}/" for c in getattr(getattr(S, "intl", None), "sites", {}) or ())
    pages = [(p, lm) for p, lm in S.pages if not (ko_only and intl_prefixes and p.startswith(intl_prefixes))]
    rows = [f"  <url><loc>{S.abs(p)}</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "") + "</url>"
            for p, lm in pages]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n")


def _rss_date(iso: str | None) -> str:
    """RFC 2822 date ('Sat, 24 Oct 2026 09:00:00 +0900') from a data YYYY-MM-DD date; '' when none."""
    if not iso or not re.match(r"^\d{4}-\d{2}-\d{2}", str(iso)):
        return ""
    d = dt.date.fromisoformat(str(iso)[:10])
    wk = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[d.weekday()]
    mo = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[d.month - 1]
    return f"{wk}, {d.day:02d} {mo} {d.year} 09:00:00 +0900"


def rss_xml(S: State) -> str:
    """RSS 2.0 feed (/rss.xml) of published columns, guides, courses and event series, newest data date first."""
    region = S.site.get("region", "")
    title = f"{S.site['site_name']} — {region} 칼럼·가이드·코스·행사" if region else S.site["site_name"]
    desc = squash_ws(S.site.get("description")) or f"{region} 여행 정보와 에디토리얼 칼럼·가이드·코스를 전합니다."
    entries: list[tuple[str, str, str, str, str]] = []
    for col in S.columns:
        body0 = squash_ws((col.get("body") or [{}])[0].get("text"))
        summary = squash_ws(present.decaution(col.get("summary")))
        text = f"{summary} {body0}".strip() if body0 else summary
        entries.append((col.get("_page_date") or col.get("published_at") or "", col["_url"], col["title"],
                        text, col.get("theme") or "칼럼"))
    for g in S.guides:
        entries.append((g.get("_page_date") or "", g["_url"], g["title"],
                        squash_ws(present.decaution(g.get("summary"))), g.get("category") or "가이드"))
    for c in S.courses:
        cv = S.course_vms.get(c["slug"]) or {}
        summary = cv.get("lede") if c.get("summary_auto") else squash_ws(c.get("summary"))
        entries.append((c.get("_page_date") or "", c["_url"], display_value("course_name", c["name"]),
                        summary or "", "여행 코스"))
    for sr in S.series:
        ev = sr["newest"]
        entries.append((sr.get("checked") or "", sr["_url"], f"{ev['_title']} 기간·장소",
                        event_description(ev, sr["name"]), "행사·축제"))
    entries.sort(key=lambda x: (x[0], x[1]), reverse=True)
    last_iso = max((x[0] for x in entries if x[0]), default="")
    head = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0">',
            "  <channel>",
            f"    <title>{escape(title)}</title>",
            f"    <link>{escape(S.site_url + '/')}</link>",
            f"    <description>{escape(desc)}</description>",
            "    <language>ko</language>"]
    if _rss_date(last_iso):
        head.append(f"    <lastBuildDate>{_rss_date(last_iso)}</lastBuildDate>")
    items = []
    for iso, url, it_title, it_desc, cat in entries:
        pub = f"\n      <pubDate>{_rss_date(iso)}</pubDate>" if _rss_date(iso) else ""
        items.append("    <item>\n"
                     f"      <title>{escape(it_title)}</title>\n"
                     f"      <link>{escape(url)}</link>\n"
                     f'      <guid isPermaLink="true">{escape(url)}</guid>\n'
                     f"      <category>{escape(cat)}</category>\n"
                     f"      <description>{escape(it_desc)}</description>{pub}\n"
                     "    </item>")
    return "\n".join(head + items + ["  </channel>", "</rss>", ""])


def _src_note(src: dict) -> str:
    """'출처: 한국관광공사 TourAPI' — the provider only; 확인일 stays in the data and JSON-LD, never in the text
    (operator decision 2026-10-09: no visible check dates)."""
    return f"출처: {src.get('provider') or '출처 미기재'}"


def llms_txt(S: State) -> tuple[str, str]:
    """llms.txt (links) and llms-full.txt (facts). In production, pages below the index criteria are left out."""
    site, src = S.site, S.site["source"]
    credits = f"원문 출처: {src['name']} ({src['url']})."
    if S.tourapi_used:
        credits += " 관광 정보·사진: 한국관광공사 TourAPI."
    head = [f"# {site['site_name']}", "", f"> {site.get('description', '')} {site.get('disclaimer', '')}".strip(), "",
            f"{credits} 방문 정보마다 출처를 적었습니다. 운영: {(site.get('operator') or {}).get('name', '')}.", ""]
    short = list(head)
    if S.guides:
        hubs = sorted(c["hub"][0] for c in LISTS.values() if c.get("hub"))  # 맛집·숙소·가볼만한 곳 허브 가이드 먼저
        ordered = sorted(S.guides, key=lambda g: hubs.index(g["id"]) if g["id"] in hubs else len(hubs))
        short += ["## 목적별 가이드"] + [f"- [{g['title']}]({g['_url']}): {first_sentence(g.get('summary'), 100)}".rstrip() for g in ordered] + [""]

    def dz_note(e: dict) -> str:  # ' 지정: 군산맛집 2026·모범음식점.' (the labels and their sources are on the page)
        ds = designations(e)
        return f" 지정: {'·'.join(d['short'] for d in ds)}." if ds else ""

    for kind, cfg in LISTS.items():
        items = [e for e in S.lists[kind] if not e["_noindex"]]
        if items:
            short += [f"## {cfg['title']}"] + [f"- [{e['name']}]({e['_url']}): {first_sentence(e.get('summary'), 100)}".rstrip()
                                                + dz_note(e) for e in items] + [""]
    if S.courses:
        short += ["## 여행 코스"] + [f"- [{c['name']}]({c['_url']}): {first_sentence(c.get('summary'), 100)}".rstrip() for c in S.courses] + [""]
    if S.columns:
        short += ["## 칼럼"] + [f"- [{c['title']}]({c['_url']}): {first_sentence(c.get('summary'), 100)}".rstrip() for c in S.columns] + [""]
    if S.abroad or S.abroad_videos:
        short += ["## 해외에서 본 " + S.site.get("region", ""),
                  f"- [해외에서 본 {S.site.get('region', '')}]({S.abs('/abroad/')}): 외신·해외 매체 기사 "
                  f"{sum(a.get('kind') == 'article' for a in S.abroad)}건(우리가 쓴 한 줄 소개와 원문 링크, 일부는 원문 한두 문장 인용)과 외국어 영상 "
                  f"{len(S.abroad_videos)}편", ""]
    if S.blog:
        short += [f"## {S.blog['name']}",
                  f"- [{S.blog['name']} 글 모음]({S.abs('/blog/')}): {josa(S.site.get('site_name', ''), '이/가')} 쓰는 네이버 블로그 글 "
                  f"{len(S.blog['posts'])}편의 제목과 원문 링크(주제별), 글에 나온 장소 페이지. 블로그 글은 이 사이트 방문 정보의 "
                  "출처가 아닙니다.", ""]
    short += timetables.llms_short(S, S.tt_sun, S.tt_transport)   # /sun/ · /transport/ (operator 2026-10-31)
    short += ["## 이용 안내", f"- [출처·이용 안내]({S.abs('/about/')}): 원문 이용조건, 사진, 운영 주체, 정정 요청", ""]
    for site in (getattr(S, "intl", None) or en_site.Intl({})).sites.values():   # one section per version
        short += en_site.llms_lines(site)
    full = list(head)
    for e in S.entities:
        if e["_noindex"]:
            continue
        full += [f"## {e['name']} ({KIND_LABELS.get(e.get('kind'), '')})", f"URL: {e['_url']}"]
        alt = jsonld.alternate_names(e)
        if alt:
            full.append(f"다른 이름: {', '.join(alt)}")
        full.append(f"요약: {e.get('summary', '')}")
        for d in e.get("details") or []:  # '자세히' paragraphs written from the sources (each stands alone)
            full.append(f"### {squash_ws(d.get('heading'))}")
            full.append(f"{squash_ws(d.get('text'))}" + (f" (출처: {d['source']})" if d.get("source") else ""))
        for k in FACT_ORDER + FIT_ORDER:
            row = fact_row(e, k)
            if not row:
                continue
            if row["value"]:
                full.append(f"- {row['label']}: {squash_ws(row['value'])} ({_src_note(row['source'])})")
            for a in row["alternatives"]:
                if a["also"]:  # a second, non-contradicting value (another dish, phone line)
                    full.append(f"- {row['label']}(추가): {squash_ws(a['value'])} ({_src_note(a)})")
                else:
                    full.append(f"- {row['label']}(다른 출처 값): {squash_ws(a['value'])} ({_src_note(a)}) "
                                "— 출처마다 값이 달라 방문 전 전화 확인")
        for d in designations(e):
            full.append(f"- 지정: {d['label']} (출처: {d['source_name']} {d['url']})")
        # 영업 확인 and 이어서 많이 간 곳 (present.license_vm, related_places; operator 2026-10-31), as the page shows them
        biz = present.license_vm(S, e)
        if biz:
            srcs = ", ".join(f"{x['name']} {x['url']}" for x in biz["sources"])
            full.append(f"- 영업 확인: {biz['open']} — {biz['by']}" + (f" · 인허가상 상호 {biz['licensed_name']}" if biz.get("licensed_name") else "") + (f" (출처: {srcs})" if srcs else ""))
            if biz["safe"]:
                full.append(f"- {biz['safe']}")
        went = present.related_places(S, e)
        if went:
            ym = present.related_ym(getattr(S, "related_trips", None) or {})
            full.append(f"- 이어서 많이 간 곳(티맵 차량 이동 기준{', ' + ym if ym else ''}, 한국관광공사 · 추천 아님): "
                        + ", ".join(t["name"] for t in went))
        full.append("")
    full += timetables.llms_full(S, S.tt_sun, S.tt_transport)   # the two timetables' summary lines
    return "\n".join(short), "\n".join(full)


def course_legs(stops: list[dict]) -> dict:
    """Straight-line distance between consecutive stops whose linked places have coordinates.
    Sets stop["next_m"] (to the next stop) and returns the measured legs and their sum. Not a travel route."""
    measured = total = 0
    for s, nxt in zip(stops, stops[1:]):
        a, b = (s.get("target") or {}).get("_geo"), (nxt.get("target") or {}).get("_geo")
        if not (a and b):
            continue
        m = 0 if s["target"] is nxt["target"] else round(haversine_m(float(a["lat"]), float(a["lng"]),
                                                                     float(b["lat"]), float(b["lng"])))
        s["next_m"] = m
        measured += 1
        total += m
    return {"measured": measured, "possible": max(len(stops) - 1, 0), "total_m": total}


def course_groups(courses: list[dict]) -> list[dict]:
    groups: dict[str, list] = {}
    for c in courses:
        groups.setdefault(c.get("group") or "여행 코스", []).append(c)
    return [{"title": t, "id": "g-" + slugify(t), "items": items} for t, items in groups.items()]


YEAR_PREFIX = re.compile(r"^20\d\d\s+")


ALT_LABELS = {"period": "기간", "place_name": "장소", "address": "주소", "fee": "요금", "playtime": "시간", "tel": "문의"}


def event_series(events: list[dict], S: State) -> list[dict]:
    """Event records grouped into series: the `series` field, else the name without a leading year after
    normalize_name (exact match only). A series with at least one dated record gets a leaf page; its newest
    dated edition is the one marked up (P1-4). The page title is the `series` name when there is one, so the
    URL stays the same from one edition to the next."""
    groups: dict[str, list] = {}
    for ev in events:
        name = squash_ws(ev.get("name"))
        # the same key form either way, so a record with `series` and one without can share a series
        key = normalize_name(YEAR_PREFIX.sub("", squash_ws(ev.get("series")) or name))
        groups.setdefault(key, []).append(ev)
    out, slugs = [], set()
    for key, evs in groups.items():
        dated = sorted((x for x in evs if x.get("start_date")),
                       key=lambda x: (x["start_date"], x.get("end_date") or ""), reverse=True)
        if not dated:
            continue
        newest = dated[0]
        undated = [x for x in evs if not x.get("start_date")]
        name = next((squash_ws(x["series"]) for x in [newest, *evs] if squash_ws(x.get("series"))), "") \
            or YEAR_PREFIX.sub("", squash_ws(newest["name"]))
        slug = base = slugify(name)
        n = 2
        while slug in slugs:
            slug, n = f"{base}-{n}", n + 1
        slugs.add(slug)
        title = squash_ws(newest["name"])
        newest["_title"] = title if YEAR_PREFIX.match(title) or newest["start_date"][:4] in title \
            else f"{newest['start_date'][:4]} {YEAR_PREFIX.sub('', title)}"
        newest["_homepage"] = web_url(newest.get("homepage"))
        # '보통 언제 열리나': what a source says about the usual timing ('매년 …' records, with the place the same
        # source gives, and `usual` notes)
        yearly = [x for x in undated if "매년" in str(x.get("period_text", ""))]
        usual = [{"text": squash_ws(x["period_text"]), "place": squash_ws(x.get("place_name")),
                  "source_name": x.get("source_name", ""), "source_url": x.get("source_url", ""),
                  "checked_at": x.get("checked_at", "")} for x in yearly]
        usual += [u for x in dated + undated for u in x.get("usual") or [] if squash_ws(u.get("text"))]
        program = next((x for x in dated + undated if x.get("highlights")), None)
        place_slugs: list[str] = []
        for x in dated + undated:
            for s in [*(x.get("place_slugs") or []), x.get("place_slug")]:
                if s and s not in place_slugs:
                    place_slugs.append(s)
        alternatives = [{"ev": x, "field": f, "label": ALT_LABELS.get(f, f), "values": vals}
                        for x in dated + undated for f, vals in (x.get("alternatives") or {}).items() if vals]
        sr = {"key": key, "name": name, "slug": slug, "_path": f"/events/{slug}/", "_url": S.abs(f"/events/{slug}/"),
              "newest": newest, "past": dated[1:], "undated": [x for x in undated if x not in yearly],
              "editions": evs, "checked": latest(*(x.get("checked_at") for x in evs)),
              "question_ids": sorted({q for x in evs for q in x.get("question_ids") or []}),
              "place_slugs": place_slugs, "program": program, "usual": usual, "alternatives": alternatives,
              "newest_alt_labels": [ALT_LABELS.get(f, f) for f, v in (newest.get("alternatives") or {}).items() if v],
              # every name the series went by, for matching videos' event_names
              "keys": {key} | {normalize_name(YEAR_PREFIX.sub("", squash_ws(x.get("name")))) for x in evs}}
        for x in evs:
            x["_series"] = sr
        out.append(sr)
    return out


VIDEOS_PER_PAGE = 3
VIDEO_TOPICS = ("여행 코스", "근대역사", "섬·바다", "호수·공원", "자연·생태", "먹거리", "축제", "숙소", "기타")
# each topic page's AI art band, videos.head.<key> (pipeline/art.py): the topic in English, as the owner's picture list
# (docs/handover/image_prompts_round2_2026-10-13.md M) names it — the one table of these names
VIDEO_TOPIC_ART = dict(zip(VIDEO_TOPICS, ("travel-courses", "modern-history", "islands-sea", "lakes-parks", "nature",
                                          "food", "festivals", "stays", "other")))


ABROAD_PLATFORMS = {"instagram": "Instagram", "threads": "Threads", "x": "X", "facebook": "Facebook"}
# /abroad/ groups its articles by who published them, in this order
ABROAD_SOURCES = (("press", "언론 기사"), ("official", "공공 매체"), ("travel", "여행 매체·가이드북"), ("blog", "해외 여행 블로그"),
                  ("research", "연구"))


def load_abroad(data_dir: Path) -> list[dict]:
    """Published foreign press articles and social posts, newest first (undated last). Every item needs a link and our
    own note; a post needs a known platform (its embed loads near the screen or when pressed — assets/site.js
    [data-embed]). An article's image is the outlet's own link-preview picture (og:image), shown from its https
    address only — never copied here, never in JSON-LD."""
    raw = _load(data_dir / "abroad.json", {}) or {}
    items = []
    for a in raw.get("items") or []:
        if a.get("status") != "published" or not a.get("url") or not squash_ws(a.get("note")):
            continue
        if a.get("kind") == "post" and a.get("platform") not in ABROAD_PLATFORMS:
            continue
        items.append({**a, "place_slugs": list(a.get("place_slugs") or []),
                      "image": a["image"] if str(a.get("image") or "").startswith("https://") else "",
                      "platform_label": ABROAD_PLATFORMS.get(a.get("platform"), "")})
    return sorted(items, key=lambda a: a.get("date") or "", reverse=True)   # '' (undated) sorts last


HL_SMALL_MAX = 60_000   # bytes: the provider's small rendition is used in a highlight circle only up to this size
HL_VIEWER = "/abroad/highlights.json"   # the viewer's markup, fetched on the first press (not in the page's first load)


def load_abroad_highlights(data_dir: Path, abroad: list[dict]) -> list[dict]:
    """data/<region>/abroad_highlights.json (owner 2026-10-13; quotations 2026-10-14): the /abroad/ highlights row, in
    file order. Each is a published abroad item (by id) with a short verbatim passage of the original in its own
    language (quote, quote_lang — shown in a <blockquote lang cite>, never translated; checked against the original by
    tools/abroad_quotes.py) and a short name for its circle (label_ko, else the outlet / service). An article needs its
    quote; a social post may go without one (its service's oEmbed gives no text — the official embed shows the post).
    An id that is not a published item, or an article without a quote, is left out here and reported by
    validate.highlight_problems."""
    raw = _load(data_dir / "abroad_highlights.json", {}) or {}
    by_id = {a["id"]: a for a in abroad if a.get("id")}
    out = []
    for h in raw.get("items") or []:
        a, quote = by_id.get(h.get("id")), squash_ws(h.get("quote"))
        lang = str(h.get("quote_lang") or "").strip()
        if not a or (quote and not lang) or not (quote or a.get("kind") == "post"):
            continue
        out.append({"item": a, "quote": quote, "quote_lang": lang if quote else "",
                    "label": squash_ws(h.get("label_ko")) or a.get("outlet") or a.get("platform_label") or "",
                    "checked": h.get("checked") or ""})
    return out


def highlight_photo(S, a: dict) -> dict | None:
    """A licensed photo of a place the item names (in its order) for an item without the outlet's own picture. The
    circle crops it, so KOGL-1 only (CLAUDE.md 3.4), and it stays light: the same-origin AVIF/WebP derivatives
    (pipeline/media.py; no third-party connection) when it has them, else the provider's small rendition when it is
    under HL_SMALL_MAX."""
    for slug in a.get("place_slugs") or []:
        e = S.ent_by_slug.get(slug)
        for ph in (e or {}).get("_photos") or []:
            th = ph.get("th") or {}
            small = th.get("url") if th.get("url") and (th.get("bytes") or HL_SMALL_MAX + 1) <= HL_SMALL_MAX else ""
            if ph.get("type") == 1 and (small or ph.get("avif")):
                return {**ph, "small": small, "place": e["name"]}
    return None


def abroad_highlights_vm(S) -> dict:
    """The row and the viewer of /abroad/: each highlight with its picture (the outlet's og:image, else highlight_photo,
    else none — the circle then shows the globe picture), the photo credit line under the row and the address of the
    viewer's markup (HL_VIEWER)."""
    items = [{**h, "photo": None if h["item"].get("image") else highlight_photo(S, h["item"])}
             for h in S.abroad_highlights]
    credits: dict[str, list[str]] = {}
    for h in items:
        if h["photo"]:
            ph = h["photo"]
            credits.setdefault(f"출처: {ph['credit']} · {ph['lic']}", []).append(ph["place"])
    return {"items": items, "og": any(h["item"].get("image") for h in items), "src": HL_VIEWER,
            "credits": [("·".join(dict.fromkeys(places)), c) for c, places in credits.items()]}


BLOG_PER_PAGE = 3       # posts in a place, guide, column or course page's 군산각 블로그 block
BLOG_GROUP_OPEN = 10    # posts each /blog/ category shows before its '더 보기'
BLOG_ROW_PLACES = 3     # places a /blog/ row links


def load_blog(data_dir: Path) -> dict | None:
    """data/<region>/blog.json (tools/blog_sync.py): the blog's name and address, its category names and its posts,
    newest first. A post needs a title, a date and an address on the blog itself; the ids under exclude stay hidden.
    None when there is no file or no post."""
    raw = _load(data_dir / "blog.json", {}) or {}
    blog = raw.get("blog") or {}
    if not blog.get("id"):
        return None
    prefix = f"https://blog.naver.com/{blog['id']}/"
    cats, hidden = raw.get("categories") or {}, set(raw.get("exclude") or {})
    posts = [{**p, "cat": squash_ws(cats.get(p.get("category"), "")), "links": list(p.get("links") or []),
              "places": [h for h in p.get("places") or [] if h.get("id")], "mentions": list(p.get("mentions") or [])}
             for p in raw.get("posts") or []
             if p.get("id") not in hidden and squash_ws(p.get("title")) and p.get("date")
             and str(p.get("url") or "") == prefix + str(p.get("id"))]
    if not posts:
        return None
    posts.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    return {"id": blog["id"], "name": squash_ws(blog.get("name")) or "블로그", "url": f"https://blog.naver.com/{blog['id']}",
            "checked_at": raw.get("checked_at"), "categories": cats, "posts": posts, "prefix": prefix}


def blog_for_place(S, e: dict) -> list[dict]:
    """The posts a place page lists: those that link to its page first, then those that name it in their title, then
    the ones naming it most often in their text; newest first among equals. At most BLOG_PER_PAGE."""
    linked = {p["id"] for p in S.blog_by_path.get(e["_path"], [])}
    rows = []
    for p in (S.blog or {}).get("posts") or []:
        hit = next((h for h in p["places"] if h["id"] == e["id"]), None)
        if hit or p["id"] in linked:
            rows.append((p["id"] in linked, bool((hit or {}).get("title")), (hit or {}).get("n", 0), p["date"], p))
    rows.sort(key=lambda r: r[:4], reverse=True)
    return [r[-1] for r in rows[:BLOG_PER_PAGE]]


def blog_for_page(S, path: str) -> list[dict]:
    """The posts that link to a guide, column or course page, newest first. At most BLOG_PER_PAGE."""
    return S.blog_by_path.get(path, [])[:BLOG_PER_PAGE]


def blog_photo(tiers: list[list[dict]], used: set[str]) -> dict | None:
    """A /blog/ card's photo: a licensed photo (TourAPI KOGL 1/3, e['_photos']) — never the blog's own pictures, whose
    sources are not known. From the first tier of places that has any photo (the most related places first); inside
    it a photo not yet on the page first, so posts about the same place do not all show the same picture."""
    for places in tiers:
        shots = [(e, ph) for e in places for ph in e.get("_photos") or []]
        if shots:
            e, ph = next(((e, ph) for e, ph in shots if ph["url"] not in used), shots[0])
            used.add(ph["url"])
            return {**ph, "place": e["name"], "path": e["_path"], "alt": e["name"]}
    return None


def blog_page_places(S) -> dict[str, list[dict]]:
    """The built places each page of this site is about, by path: a place page, a guide's or column's items, a
    course's stops (a post's links give its card a photo when the places it names have none)."""
    out = {e["_path"]: [e] for e in S.entities}
    for x in [*S.guides, *S.columns]:
        out[x["_path"]] = [S.ent_by_slug[it["place_slug"]] for it in x.get("items") or []
                           if isinstance(it, dict) and it.get("place_slug") in S.ent_by_slug]
    for c in S.courses:
        out[c["_path"]] = [S.ent_by_slug[st["place_slug"]] for st in c.get("stops") or [] if st.get("place_slug") in S.ent_by_slug]
    return out


def nearest_with_photo(S, places: list[dict]) -> list[dict]:
    """Built places with a photo, nearest first to the first of `places` that has coordinates (a place without a
    licensed photo, such as a stay, lends its card the photo of what stands nearest)."""
    g = next((e["_geo"] for e in places if e.get("_geo")), None)
    if not g:
        return []
    far = lambda x: haversine_m(float(g["lat"]), float(g["lng"]), float(x["_geo"]["lat"]), float(x["_geo"]["lng"]))
    return sorted((x for x in S.entities if x.get("_photos") and x.get("_geo")), key=far)[:3]


def blog_cards(S) -> list[dict]:
    """Every post's card, newest first: the built places it is about (its places in the order blog_sync ranked them:
    named in the title, then most often) and its photo (operator 2026-10-30: every card a photo) — from the places it
    is about, else the places it names once, else the place nearest to them, else the places of the pages it links,
    else the places of its category's posts. Computed once per State: /blog/ and the home show the same cards."""
    if getattr(S, "_blog_cards", None) is not None:
        return S._blog_cards
    by_id = {e["id"]: e for e in S.entities}
    pages = blog_page_places(S)
    rows, by_cat = [], {}
    for p in S.blog["posts"]:
        places = list({x["_path"]: x for x in (by_id[h["id"]] for h in p["places"] if h["id"] in by_id)}.values())
        mentioned = [by_id[i] for i in p["mentions"] if i in by_id]
        linked = [x for link in p["links"] for x in pages.get(link, [])]
        r = {"p": p, "places": places[:BLOG_ROW_PLACES],
             "_tiers": [places, mentioned, nearest_with_photo(S, places + mentioned), linked]}
        rows.append(r)
        by_cat.setdefault(p["category"], []).append(r)
    for cat_rows in by_cat.values():   # the last tier: the places of the category's posts
        pool = [x for r in cat_rows for tier in r["_tiers"] for x in tier if x.get("_photos")]
        for r in cat_rows:
            r["_tiers"].append(pool)
    used: set[str] = set()
    for r in rows:   # newest first: the newest posts, those the home shows, get the photos not used yet
        r["photo"] = blog_photo(r["_tiers"], used)
    S._blog_cards = rows
    return rows


def blog_groups(S) -> list[dict]:
    """/blog/ by the blog's own categories, the largest first, newest first inside (blog_cards)."""
    groups: dict[str, list[dict]] = {}
    for r in blog_cards(S):
        groups.setdefault(r["p"]["category"], []).append(r)
    out = [{"id": f"bl-{k}", "title": rows[0]["p"]["cat"] or "그 밖의 글", "rows": rows} for k, rows in groups.items()]
    return sorted(out, key=lambda g: -len(g["rows"]))


BLOG_HOME = 6   # cards in the home's 군산각 블로그 section


def blog_home(S) -> list[dict]:
    """The home's 군산각 블로그 cards: the newest post of each category (the largest category first), then the next
    newest of each, until BLOG_HOME — so the row is not all one subject — and no photo twice among them."""
    if not S.blog:
        return []
    queues = [list(g["rows"]) for g in blog_groups(S)]
    out: list[dict] = []
    while len(out) < BLOG_HOME and any(queues):
        out += [q.pop(0) for q in queues if q][:BLOG_HOME - len(out)]
    shown: set[str] = set()
    for i, r in enumerate(out):   # no photo twice in the row: a repeat takes the post's next candidate
        if r["photo"] and r["photo"]["url"] in shown:
            out[i] = r = {**r, "photo": blog_photo(r["_tiers"], shown) or r["photo"]}
        if r["photo"]:
            shown.add(r["photo"]["url"])
    return out


def load_videos(data_dir: Path) -> list[dict]:
    """Checked videos, official channels first (file order otherwise)."""
    vids = [v for v in _load(data_dir / "videos.json", []) or []
            if v.get("youtube_id") and v.get("url") and v.get("verified_by") and not v.get("exclude")]
    return sorted(vids, key=lambda v: v.get("channel_kind") != "official")


VIDEO_KIND_RANK = {"official": 0, "broadcaster": 1, "creator": 2}
VIDEOS_PER_TOPIC_PREVIEW = 8


def video_rank(v: dict) -> tuple:
    """Newest first (owner, 2026-10-09: old videos must not lead); on the same date official channels, then
    broadcasters, then creators, and videos about fewer places (more specific) first. Undated videos last."""
    return (-int((v.get("published_date") or "0").replace("-", "") or 0),
            VIDEO_KIND_RANK.get(v.get("channel_kind"), 3), len(v.get("place_slugs") or []) or 9)


def video_groups(videos: list[dict]) -> list[dict]:
    """Videos under their first topic, in VIDEO_TOPICS order (unknown topics last, by name). Each topic has its
    own page (/videos/<slug>/); the index shows the first VIDEOS_PER_TOPIC_PREVIEW of each. art: the key of the
    topic page's AI art band (VIDEO_TOPIC_ART; '' for a topic outside VIDEO_TOPICS)."""
    groups: dict[str, list] = {}
    for v in videos:
        groups.setdefault((v.get("topics") or ["기타"])[0], []).append(v)
    order = lambda t: (VIDEO_TOPICS.index(t) if t in VIDEO_TOPICS else len(VIDEO_TOPICS), t)
    out = []
    for n, t in enumerate(sorted(groups, key=order)):
        items = sorted(groups[t], key=video_rank)
        slug = "그-밖의-영상" if t == "기타" else slugify(t.replace("·", " "))
        out.append({"id": f"v-{n + 1}", "title": t, "slug": slug, "_path": f"/videos/{slug}/", "items": items,
                    "preview": items[:VIDEOS_PER_TOPIC_PREVIEW], "art": VIDEO_TOPIC_ART.get(t, "")})
    return out


def event_months(events: list[dict]) -> list[dict]:
    """Dated records grouped under absolute month headings ('2026년 10월'), newest month first."""
    months: dict[str, list] = {}
    for ev in events:
        if ev.get("start_date"):
            months.setdefault(ev["start_date"][:7], []).append(ev)
    return [{"id": f"m-{ym}", "title": f"{int(ym[:4])}년 {int(ym[5:7])}월",
             "items": sorted(items, key=lambda x: (x["start_date"], x.get("name", "")))}
            for ym, items in sorted(months.items(), reverse=True)]


def event_last_day(ev: dict) -> str:
    """The last day an edition can run: its end date, else the last day of `end_month` (a source that says
    only '~10월'), else its start date. For sorting and upcoming/past only — never printed: a month-only end is
    shown as its month (event_end_month), never as that month's last day (QA 2026-10-15 SRC-06)."""
    if ev.get("end_date"):
        return ev["end_date"]
    if re.fullmatch(r"\d{4}-\d{2}", ev.get("end_month") or ""):
        y, m = int(ev["end_month"][:4]), int(ev["end_month"][5:])
        return (dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
    return ev.get("start_date") or ""


def event_end_month(ev: dict) -> str:
    """'2026-10' when the source gives the edition's end only as a month (no end_date), else ''."""
    em = ev.get("end_month") or ""
    return em if not ev.get("end_date") and re.fullmatch(r"\d{4}-\d{2}", em) else ""


def upcoming_events(S: State) -> list[dict]:
    """Dated editions still running or yet to start on the build date, then the undated '매년 …' records."""
    dated = [e for e in S.events if e.get("start_date") and event_last_day(e) >= S.today]
    yearly = [e for e in S.events if not e.get("start_date") and str(e.get("period_text", "")).startswith("매년")]
    return dated + yearly


# ---------------------------------------------------------------- build
def course_title(name: str, n_stops: int, region: str) -> str:
    """'A코스 | 근대~고군산 당일 코스' -> '군산 근대~고군산 당일 코스(A코스) — 경유지 11곳' (<title> adds ' | site_name')."""
    m = re.match(r"^\s*(\S*코스)\s*\|\s*(.+)$", name)
    core = f"{m.group(2).strip()}({m.group(1)})" if m else squash_ws(name)
    if region and not re.search(rf"(?<![가-힣]){re.escape(region)}", core):  # '고군산' does not name the city
        core = f"{region} {core}"
    return f"{core} — 경유지 {n_stops}곳"


def event_period(ev: dict) -> str:
    """'2026년 10월 2일(금)~10월 5일(월)' — the exact dates of the edition (an end month without a day stays '~10월')."""
    start, end = ev["start_date"], ev.get("end_date") or ""
    period = ko_date(start)
    if end and end != start:
        period += "~" + ko_date(end, with_year=end[:4] != start[:4])
    elif not end and re.fullmatch(r"\d{4}-\d{2}", ev.get("end_month") or ""):  # '~10월': no end day in the source
        y, m = ev["end_month"][:4], int(ev["end_month"][5:])
        period += f"~{y + '년 ' if y != start[:4] else ''}{m}월"
    return period


def event_answer(ev: dict, with_place: bool = True) -> str:
    """Tense-free answer line: '2026 군산시간여행축제 기간: 2026년 10월 2일(금)~10월 5일(월) · 장소: …'."""
    place = squash_ws(ev.get("place_name"))
    return f"{ev['_title']} 기간: {event_period(ev)}" + (f" · 장소: {place}" if place and with_place else "")


def place_summary(place: str | None) -> tuple[str, str]:
    """An event place, shorter: (the place without its notes in brackets, the first place of the list + '일원').
    '구 군산세관 본관~내항 역사문화공간(내항철로)~구 조선은행 군산지점 일원' -> ('구 군산세관 본관~내항 역사문화공간~구 조선은행
    군산지점 일원', '구 군산세관 본관 일원'). A '·' is not a list separator here ('3·1운동', '구·시청광장')."""
    bare = squash_ws(re.sub(r"\s*\([^()]*\)", "", squash_ws(place)))
    first = re.split(r"\s*(?:,|~|/|:|\s및\s)\s*", bare, maxsplit=1)[0].strip()
    first = re.sub(r"\s*일원$", "", first)
    return bare, (f"{first} 일원" if first else "")


def event_description(ev: dict, series_name: str = "", limit: int = DESC_MAX) -> str:
    """An event page's description, the first of these within `limit`; the dates are always the whole, exact period:
    1. the answer line the page shows, '<행사명> 기간: <기간> · 장소: <장소>.', with ' 요금: <요금>.' when it fits;
    2. '<행사명> <기간>, <장소 요약>.' — the place without its bracketed notes, else its first place + '일원';
    3. '<행사명> <기간>.', then '<행사 이름(이 페이지의 목록 이름)> <기간>.'."""
    answer = event_answer(ev)
    fee = squash_ws(ev.get("fee"))
    title, period = squash_ws(ev["_title"]), event_period(ev)
    bare, first = place_summary(ev.get("place_name"))
    return first_fit(f"{answer}. 요금: {fee}." if fee else "", f"{answer}.",
                     f"{title} {period}, {bare}." if bare else "", f"{title} {period}, {first}." if first else "",
                     f"{title} {period}.", f"{squash_ws(series_name)} {period}." if series_name else "",
                     limit=limit) or f"{title} {period}."


def build(data_dir: Path, out: Path, mode: str = "production") -> dict:
    S = State(data_dir, mode)
    # the other language versions (/en/ …) whose data/<region>/<code> exists: which records are current, their slugs
    # and the ko ↔ version pairs are known before any page is written, so every Korean page can carry its hreflang
    # links and the language menu
    S.intl = en_site.load_all(S, data_dir)
    S.en = S.intl.sites.get("en")
    S.side["latin"] = S.en.loc.site_name if S.en else ""   # the panel's wordmark line: 'Gunsangak · 군산 여행 정보'
    env = make_env()
    env.globals["kakao_sdk"] = kakao_sdk_url(S.site)  # the map boxes' data-kakao-sdk (templates/_ui mapfig …)
    _prepare_out(out, data_dir)
    region = S.site.get("region", "")
    # Dates (P0-4): every lastmod is a data date shown on that page; aggregate pages use the newest date
    # of the leaf pages they link to and show it. Nothing comes from the build clock.
    date_of = lambda items: latest(*(x.get("_page_date") for x in items))

    for e in S.entities:
        ctx = entity_ctx(e, S)
        _render(env, S, out, "place.html.j2", e["_path"], ctx.pop("page"), f"place-{ctx['kind']}", e["_page_date"],
                in_sitemap=not e["_noindex"], **ctx)

    for t in S.themes:
        members = [e for e in S.entities if t["slug"] in (e.get("themes") or [])]
        if not members:
            continue
        path = f"/themes/{t['slug']}/"
        crumbs = [("홈", S.site_url + "/"), ("관광지", S.abs("/places/")), (t["name"], S.abs(path))]
        desc = t.get("description") or f"{region}의 {t['name']} 여행지 목록입니다."
        if len(desc) < 40:
            desc = f"{desc} — {region} 여행지 {len(members)}곳의 이용시간·요금·주차를 장소별 출처와 함께 정리했습니다."
        desc = first_fit(desc, fit_sentences(desc), f"{t['name']} — {region} 여행지 {len(members)}곳.")
        lastmod = date_of(members)
        L = present.list_vm(S, "attraction", t)
        # the ItemList follows the page: the records in the order the list shows them (권역 groups, list_vm)
        page = _simple_page(S, path, f"{t['name']} — {region} 여행지 {len(members)}곳", desc, crumbs,
                            [it["e"]["_url"] for g in L["groups"] for it in g["recs"]],
                            image=next((og_image(e["_images"]) for e in members if e["_images"]), ""))
        _render(env, S, out, "theme.html.j2", path, page, "theme", lastmod, theme=t, members=members, L=L)

    for kind, cfg in LISTS.items():
        # places with a licensed photo first, then full-tier pages; otherwise the data order is kept
        items = sorted(S.lists[kind], key=lambda e: (not e["_images"], e.get("tier") != "full"))
        if not items and kind != "attraction":
            continue
        crumbs = [("홈", S.site_url + "/"), (cfg["title"], S.abs(cfg["path"]))]
        title = cfg["seo"].format(region=region, n=len(items))
        groups = sorted({e["_group"] for e in items})
        areas = sorted({e["_area"] for e in items if e["_area"]})
        themes = [t for t in S.themes if any(t["slug"] in (e.get("themes") or []) for e in items)]
        points = map_points(items)
        lastmod = date_of(items)
        L = present.list_vm(S, kind)
        page = _simple_page(S, cfg["path"], title,
                            f"{region} {josa(cfg['title'], '을/를')} 유형·테마·지역으로 골라 보고, 방문 정보와 길찾기로 이어 갑니다.",
                            crumbs, [it["e"]["_url"] for g in L["groups"] for it in g["recs"]], map=bool(points),
                            filters=True, image=next((og_image(e["_images"]) for e in items if e["_images"]), ""))
        page_kind = "places" if kind == "attraction" else f"list-{kind}"
        hub_id, hub_label = cfg.get("hub") or ("", "")
        hub = S.guide_by_id.get(hub_id)
        _render(env, S, out, "list.html.j2", cfg["path"], page, page_kind, lastmod, kind=kind, cfg=cfg, items=items,
                hub={"path": hub["_path"], "label": hub_label} if hub else None, groups=groups, areas=areas, themes=themes,
                points=points, L=L)

    if S.entities:
        path = "/map/"
        crumbs = [("홈", S.site_url + "/"), ("지도·지역", S.abs(path))]
        by_area: dict[str, list] = {}
        for e in S.entities:
            by_area.setdefault(e["_area"] or "읍·면·동 미기재", []).append(e)
        areas = sorted(by_area.items(), key=lambda kv: (kv[0] == "읍·면·동 미기재", -len(kv[1]), kv[0]))
        # each point also carries its 권역 (r) and an id for the redesign's region tabs and row highlighting
        points = [{**pt, "r": e["_region"], "id": e["slug"]} for e in S.entities for pt in map_points([e])]
        lastmod = date_of(S.entities)
        page = _simple_page(S, path, f"{region} 지도·지역별 여행지", f"{region} 관광지·숙소·음식점을 읍·면·동별로 모았습니다.",
                            crumbs, map=bool(points))
        _render(env, S, out, "map.html.j2", path, page, "map", lastmod, areas=areas, points=points,
                **present.map_vm(S))

    for g in S.guides:
        items = []
        for it in g.get("items") or []:
            target = S.ent_by_slug.get(it.get("place_slug") or "")
            items.append({**it, "target": target, "name": target["name"] if target else it.get("name", "")})
        crumbs = [("홈", S.site_url + "/"), ("목적별 가이드", S.abs("/guides/")), (g["title"], g["_url"])]
        targets = [i["target"] for i in items if i["target"]]
        points = map_points(targets)
        unique = list({t["slug"]: t for t in targets}.values())
        about = [jsonld.place_ref(t["_url"], t) for t in unique]
        page = {"title": g['title'], "description": guide_description(g, S),
                "canonical": g["_url"], "og_type": "article", "crumbs": crumbs, "map": bool(points),
                "image": next((og_image(t["_images"]) for t in targets if t["_images"]), ""),
                # the summary and FAQ answers as guide.html.j2 shows them (present.decaution), so the structured
                # data never says more than the page
                "jsonld": [jsonld.dumps(jsonld.guide_graph(
                    {**g, "summary": present.decaution(g.get("summary")),
                     "faq": [{**f, "a": present.decaution(squash_ws(f.get("a")))} for f in g.get("faq") or []]},
                    S.site_url, g["_url"], crumbs, about, [t["_url"] for t in unique], g["_page_date"] or "",
                    site=S.site))]}
        _render(env, S, out, "guide.html.j2", g["_path"], page, "guide", g["_page_date"], g=g, items=items,
                points=points, G=present.guide_vm(S, g), blog_posts=blog_for_page(S, g["_path"]))
    if S.guides:
        path = "/guides/"
        crumbs = [("홈", S.site_url + "/"), ("목적별 가이드", S.abs(path))]
        lastmod = date_of(S.guides)
        page = _simple_page(S, path, f"{region} 여행 목적별 가이드",
                            f"당일여행·가족여행·비 오는 날·숙소 찾기 등 목적별로 {region} 여행 정보를 묶었습니다.", crumbs)
        _render(env, S, out, "guides_index.html.j2", path, page, "guides", lastmod, guides=S.guides,
                guide_rows=present.guide_rows(S))
    for col in S.columns:
        items = []
        for it in col.get("items") or []:
            target = S.ent_by_slug.get(it.get("place_slug") or "")
            items.append({**it, "target": target, "name": target["name"] if target else it.get("name", "")})
        crumbs = [("홈", S.site_url + "/"), ("칼럼", S.abs("/columns/")), (col["title"], col["_url"])]
        targets = [i["target"] for i in items if i["target"]]
        points = map_points(targets)
        unique = list({t["slug"]: t for t in targets}.values())
        about = [jsonld.place_ref(t["_url"], t) for t in unique]
        desc = first_fit(squash_ws(col.get("dek")), fit_sentences(present.decaution(col.get("summary"))),
                         f"{col['title']} — {region} 칼럼.")
        page = {"title": col["title"], "description": desc,
                "canonical": col["_url"], "og_type": "article", "crumbs": crumbs, "map": bool(points),
                "image": next((og_image(t["_images"]) for t in targets if t["_images"]), ""),
                "jsonld": [jsonld.dumps(jsonld.guide_graph(
                    {**col, "summary": present.decaution(col.get("summary")), "faq": []},
                    S.site_url, col["_url"], crumbs, about, [t["_url"] for t in unique], col["_page_date"] or "",
                    site=S.site))]}
        _render(env, S, out, "column.html.j2", col["_path"], page, "column", col["_page_date"], col=col, items=items,
                points=points, C=present.column_vm(S, col), blog_posts=blog_for_page(S, col["_path"]))
    if S.columns:
        path = "/columns/"
        crumbs = [("홈", S.site_url + "/"), ("칼럼", S.abs(path))]
        lastmod = date_of(S.columns)
        CV = present.columns_index_vm(S)
        desc = first_fit(f"{region}의 근대건축·골목 역사·섬 동선·미식·해외 시선을 깊이 있게 풀어쓴 칼럼 {len(S.columns)}편을 모았습니다.",
                         f"{region} 여행과 역사·건축·미식을 깊이 있게 다룬 칼럼 {len(S.columns)}편입니다.")
        page = _simple_page(S, path, f"{region} 칼럼 — 역사·건축·동선·미식 에세이 {len(S.columns)}편", desc, crumbs,
                            [col["_url"] for col in S.columns],
                            image=next((c["photo"]["url"] for c in CV["cards"] if c.get("photo")), ""))
        _render(env, S, out, "columns_index.html.j2", path, page, "columns", lastmod, columns=S.columns, CV=CV)

    for c in S.courses:
        stops = []
        for i, s in enumerate(c.get("stops") or [], 1):
            target = S.ent_by_slug.get(s.get("place_slug") or "")
            name = squash_ws(s.get("name") or (target or {}).get("name", ""))
            stops.append({**s, "n": i, "target": target, "name": name,
                          "part_of": bool(target) and str(s.get("link_basis", "")).startswith("part_of"),
                          "search": search_link(name, region)})
        legs = course_legs(stops)
        co = present.course_stop_details(S.course_vms[c["slug"]])
        # The page shows the course name without the source's separator pipe; JSON-LD and the crumbs use the
        # same text. A summary_auto course (a template sentence) is described by its computed lede, shown on
        # the page; a course with a written summary keeps it (course_lede is then that summary).
        name = display_value("course_name", c["name"])
        course_lede = co["lede"]
        crumbs = [("홈", S.site_url + "/"), ("여행 코스", S.abs("/courses/")), (name, c["_url"])]
        orig = c.get("original") or {}
        show_original = bool(orig.get("text")) and license_allowed(orig.get("license"), S.allowed_original)
        # the itinerary lists places only: a meal, the night's lodging or an activity is not a stop (present.stop_kind)
        refs = [jsonld.place_ref(s["target"]["_url"], s["target"]) if s["target"]
                else {"@type": "Place", "name": s["name"]} for s in stops
                if present.stop_kind(squash_ws(s.get("name")), s["target"]) == "place"]
        description = course_lede if c.get("summary_auto") else c.get("summary")
        # its first sentence, whole; one over DESC_MAX gives way to the stops line (count, first and last stop)
        page = {"title": course_title(c["name"], co["n_places"], region),
                "description": first_fit(first_sentence(description, len(squash_ws(description)) + 1),
                                         f"{name}: 경유지 {co['n_places']}곳, {co['first']}에서 {co['last']}까지.",
                                         f"{name}: 경유지 {co['n_places']}곳.") or f"{name}.",
                "canonical": c["_url"], "crumbs": crumbs, "map": bool(co["map"]),
                "image": c["_cover"]["url"] if c.get("_cover") else "",
                "jsonld": [jsonld.dumps(jsonld.course_graph(c, c["_url"], crumbs, refs, orig.get("source_url") or "",
                                                            description=course_lede))]}
        linked = sum(1 for s in stops if s["target"])
        _render(env, S, out, "course.html.j2", c["_path"], page, "course", c["_page_date"], blog_posts=blog_for_page(S, c["_path"]),
                c=c, stops=stops, orig=orig, show_original=show_original, linked=linked, legs=legs,
                co=co, course_lede=course_lede, lede=course_lede, course_name=name, orig_url=orig.get("source_url") or "",
                orig_name=orig.get("source_name") or S.site["source"]["name"], collected=orig.get("collected_at") or "",
                week=present.week_grid([s["t"] for s in co["stops"] if s["t"]]), move=present.course_move(S, co))
    if S.courses:
        path = "/courses/"
        crumbs = [("홈", S.site_url + "/"), ("여행 코스", S.abs(path))]
        lastmod = date_of(S.courses)
        page = _simple_page(S, path, f"{region} 여행 코스 — 당일·1박 2일·2박 3일",
                            f"군산시 문화관광이 안내하는 {region} 여행 코스와 경유지를 정리했습니다.", crumbs,
                            image=next((c["_cover"]["url"] for c in S.courses if c.get("_cover")), ""))
        _render(env, S, out, "courses_index.html.j2", path, page, "courses", lastmod, groups=course_groups(S.courses),
                CV=present.course_index_vm(S))

    if S.events:
        index_path = "/events/"
        for sr in S.series:
            ev = sr["newest"]
            crumbs = [("홈", S.site_url + "/"), ("행사·축제", S.abs(index_path)), (sr["name"], sr["_url"])]
            answer = event_answer(ev)
            description = event_description(ev, sr["name"])  # never cut a value mid-way: the whole period stays
            places = [S.ent_by_slug[x] for x in sr["place_slugs"] if x in S.ent_by_slug]
            page = {"title": f"{ev['_title']} 기간·장소", "description": description,
                    "canonical": sr["_url"], "og_type": "article", "crumbs": crumbs,
                    "jsonld": [jsonld.dumps(jsonld.event_graph(ev, sr["_url"], crumbs, S.site))],
                    "videos": bool(sr.get("videos"))}
            _render(env, S, out, "event.html.j2", sr["_path"], page, "events", sr["checked"], sr=sr, ev=ev,
                    answer=answer, address=display_address(ev.get("address")), places=places,
                    V=present.event_vm(S, sr))
        crumbs = [("홈", S.site_url + "/"), ("행사·축제", S.abs(index_path))]
        checked = latest(*(e.get("checked_at") for e in S.events))
        page = _simple_page(S, index_path, f"{region} 행사·축제 일정 — 월별 기간·장소",
                            f"{region} 행사와 축제의 기간·장소를 시작 월별로 정리했습니다. 회차마다 출처를 함께 적었습니다.",
                            crumbs, [sr["_url"] for sr in S.series])
        # editions still running or yet to start on the build date first; finished ones by month below
        current = [e for e in S.events if e.get("start_date") and event_last_day(e) >= S.today]
        finished = [e for e in S.events if e.get("start_date") and event_last_day(e) < S.today]
        _render(env, S, out, "events.html.j2", index_path, page, "events", checked, current=current,
                months=event_months(finished),
                undated=[e for e in S.events if not e.get("start_date")], checked=checked, series=S.series,
                EV=present.events_vm(S))

    if S.videos:
        path = "/videos/"
        crumbs = [("홈", S.site_url + "/"), ("영상", S.abs(path))]
        groups = video_groups(S.videos)
        checked = latest(*(v.get("checked_at") for v in S.videos))
        official = sum(v.get("channel_kind") == "official" for v in S.videos)
        page = _simple_page(S, path, f"영상으로 보는 {region} — 주제별 YouTube 영상 {len(S.videos)}편",
                            fit_sentences(f"{region} 여행 코스·근대역사·섬·먹거리·축제를 다룬 YouTube 영상 {len(S.videos)}편을 "
                                          f"주제별로 모았습니다. 공식 채널 영상은 {official}편입니다."), crumbs,
                            None, videos=True)  # no ItemList: the items are YouTube pages, not this site's URLs
        _render(env, S, out, "videos.html.j2", path, page, "videos", checked, groups=groups, checked=checked,
                official=official, total=len(S.videos), places=S.ent_by_slug, topic=None,
                video_groups=present.video_groups_vm(groups))
        for g in groups:
            label = "그 밖의" if g["title"] == "기타" else g["title"]
            tcrumbs = crumbs + [(f"{label} 영상", S.abs(g["_path"]))]
            tchecked = latest(*(v.get("checked_at") for v in g["items"]))
            kinds = Counter(v.get("channel_kind") for v in g["items"])
            page = _simple_page(S, g["_path"], f"{region} {label} 영상 {len(g['items'])}편 — YouTube 모아 보기",
                                fit_sentences(f"{region} {label} 주제를 다룬 YouTube 영상 {len(g['items'])}편입니다. 공식 채널 "
                                              f"{kinds['official']}편, 방송사 {kinds['broadcaster']}편, 크리에이터 "
                                              f"{kinds['creator']}편을 이 순서로 실었습니다."),
                                tcrumbs, None, videos=True)
            _render(env, S, out, "videos.html.j2", g["_path"], page, "videos", tchecked, groups=[g], checked=tchecked,
                    official=kinds["official"], total=len(g["items"]), places=S.ent_by_slug, topic=g,
                    video_groups=present.video_groups_vm([g]))

    if S.abroad or S.abroad_videos:
        # /abroad/ 해외에서 본 군산 (owner 2026-10-13): foreign press (our note + the link), YouTube videos in other
        # languages (the same facade cards as /videos/) and social posts (a card; the service's official embed loads
        # near the screen). Korean only, like every page added after 2026-10-09.
        path = "/abroad/"
        crumbs = [("홈", S.site_url + "/"), ("해외에서 본 " + region, S.abs(path))]
        articles = [a for a in S.abroad if a.get("kind") == "article"]
        posts = [a for a in S.abroad if a.get("kind") == "post"]
        # the counts the page shows, in one sentence within DESC_MAX (the outlet names are on the page, not in here)
        desc = (f"{region} 관련 외신·해외 매체 기사 {len(articles)}건과 외국어 영상 {len(S.abroad_videos)}편"
                + (f", SNS 게시물 {len(posts)}건" if posts else "") + "을 원문 링크와 함께 모았습니다.")
        page = _simple_page(S, path, f"해외에서 본 {region} — 외신 기사·외국어 영상" + ("·SNS" if posts else ""),
                            desc, crumbs, None, videos=bool(S.abroad_videos))
        checked = latest(*(a.get("checked_at") for a in S.abroad), *(v.get("checked_at") for v in S.abroad_videos),
                         *(h["checked"] for h in S.abroad_highlights))
        groups = [{"id": f"ab-{k}", "key": k, "title": label,
                   "items": [a for a in articles if (a.get("source_type") or "press") == k]} for k, label in ABROAD_SOURCES]
        hl = abroad_highlights_vm(S) if S.abroad_highlights else None
        _render(env, S, out, "abroad.html.j2", path, page, "abroad", checked, articles=articles, posts=posts,
                article_groups=[g for g in groups if g["items"]],
                abroad_videos=S.abroad_videos, places=S.ent_by_slug, highlights=hl)
        if hl:   # the viewer (templates/_abroad_hl.html.j2 dialog) arrives with highlights.js on the first press
            viewer = env.get_template("_abroad_hl.html.j2").module.dialog(hl)
            (out / HL_VIEWER.strip("/")).write_text(json.dumps({"html": str(viewer)}, ensure_ascii=False), "utf-8")

    if S.blog:
        # /blog/ 군산각 블로그 (operator 2026-10-30): every post by the blog's categories as a card — its title as a link
        # to the blog, the date, the places it is about (this site's pages) and a licensed photo of one of them (the
        # blog's own pictures are never shown). Korean only; no ItemList (blog pages).
        path, B = "/blog/", S.blog
        crumbs = [("홈", S.site_url + "/"), (B["name"], S.abs(path))]
        groups = blog_groups(S)
        desc = first_fit(f"{B['name']} 여행 기록 {len(B['posts'])}편을 주제별로 모으고, 글에 나온 장소의 방문 정보 페이지를 이었습니다.",
                         f"{B['name']} 여행 기록 {len(B['posts'])}편을 주제별로 모았습니다.")
        page = _simple_page(S, path, f"{B['name']} — {region} 여행 기록 {len(B['posts'])}편 모아 보기", desc, crumbs, None)
        _render(env, S, out, "blog.html.j2", path, page, "blog", latest(*(p["date"] for p in B["posts"])),
                B=B, groups=groups, open_n=BLOG_GROUP_OPEN)

    # /sun/ 군산 일출·일몰 시간 and /transport/ 군산 교통 시간표 (pipeline/timetables.py, operator 2026-10-31: the new public
    # data on the site, for search and AI answers): Korean pages, WebPage + BreadcrumbList + Dataset, lastmod the data's
    # checked date (never shown)
    for V, make, path, template, kind in ((S.tt_sun, timetables.sun_page, timetables.SUN_PATH, "sun.html.j2", "sun"),
                                          (S.tt_transport, timetables.transport_page, timetables.TRANSPORT_PATH,
                                           "transport.html.j2", "transport")):
        if not V:
            continue
        P = make(S, V)
        page = {k: P[k] for k in ("title", "description", "canonical", "crumbs", "ds_name", "ds_desc")}
        page["jsonld"] = [jsonld.dumps(P["graph"])]
        checked = V["src"]["checked"] if kind == "sun" else V["checked"]
        _render(env, S, out, template, path, page, kind, checked or None, V=V)

    if S.entities:
        # /search/: a static index (name · other names · 대표 메뉴 · 동 · 권역) fetched by assets/search.js on first
        # focus; without JS the page itself is the answer: every place in 가나다 groups. A utility page: noindex,
        # not in the sitemap.
        path = "/search/"
        index = present.search_index(S)
        (out / "search").mkdir(parents=True, exist_ok=True)
        (out / "search" / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), "utf-8")
        crumbs = [("홈", S.site_url + "/"), ("검색", S.abs(path))]
        page = _simple_page(S, path, f"{region} 여행 검색 — 장소·대표 메뉴·동·코스",
                            f"{region}의 장소 이름, 대표 메뉴, 동 이름, 코스·가이드·행사 이름으로 찾습니다.", crumbs,
                            robots="noindex, follow")
        # the query words, the city and the planner (built just below, under the same condition) for search.js
        _render(env, S, out, "search.html.j2", path, page, "search", None, in_sitemap=False,
                directory=present.search_directory(S), n_index=len(index),
                search_data=present.search_form_data(region, "/plan/"))

    if S.entities:
        # /plan/: the AI course planner (operator 2026-10-17; chatbot/planner.js answers /api/plan/). The page draws a
        # plan from /plan/places.json — each place's first-screen values, photo and point (present.plan_places). A
        # utility page: noindex, not in the sitemap, Korean only.
        path = "/plan/"
        (out / "plan").mkdir(parents=True, exist_ok=True)
        (out / "plan" / "places.json").write_text(
            json.dumps(present.plan_places(S), ensure_ascii=False, separators=(",", ":")), "utf-8")
        crumbs = [("홈", S.site_url + "/"), ("AI 코스 만들기", S.abs(path))]
        page = _simple_page(S, path, f"AI 코스 만들기 — 조건대로 짜는 {region} 여행 일정",
                            f"날짜·이동 수단·동행·취향을 고르면 {region}의 장소 정보로 일정을 짜고, 휴무·운영시간·입장료 합계를 "
                            "사이트 자료로 확인합니다.", crumbs, robots="noindex, follow")
        # (each need's count of places to visit the data says fit it: the form shows it when the need is picked — UI-A01)
        _render(env, S, out, "plan.html.j2", path, page, "plan", None, in_sitemap=False, **present.plan_vm(S),
                need_n=chat_index.plan_need_counts(S))

    path = "/about/"
    crumbs = [("홈", S.site_url + "/"), ("소개·출처", S.abs(path))]
    lastmod = latest(*(x.get("_page_date") for x in S.entities + S.guides + S.courses),
                     *(e.get("checked_at") for e in S.events))
    page = _simple_page(S, path, f"소개·출처 안내 | {S.site['site_name']}",
                        "이 사이트가 무엇인지, 원문 출처와 이용조건, 사진, 운영 주체, 정정 요청 방법을 안내합니다.", crumbs)
    license_counts = {}
    for e in S.entities:
        code = (e.get("original") or {}).get("license") or "UNKNOWN"
        license_counts[code] = license_counts.get(code, 0) + 1
    _render(env, S, out, "about.html.j2", path, page, "about", lastmod, license_counts=license_counts,
            allowed_original=S.allowed_original, **present.about_vm(S))

    attractions = S.lists["attraction"]
    featured = sorted(attractions, key=lambda e: (not e["_images"], e.get("tier") != "full", not e.get("summary")))[:7]
    hero = []
    for slug, n in HERO_PICKS:
        e = S.ent_by_slug.get(slug)
        type1 = [i for i in (e or {}).get("_images", []) if i.get("license") == "KOGL-1"]
        if type1:
            hero.append({"e": e, "img": type1[min(n, len(type1) - 1)]})
    purposes = []
    for label, gid, fallback, note in PURPOSES:
        g = S.guide_by_id.get(gid)
        href = g["_path"] if g else fallback
        if "#" in href and href.split("#", 1)[1] not in {grp["id"] for grp in course_groups(S.courses)}:
            href = href.split("#", 1)[0]
        if href.startswith("/courses/") and not S.courses:
            href = "/places/"
        if href == "/stays/" and not S.lists["stay"]:
            continue
        purposes.append({"label": label, "href": href, "note": note, "guide": bool(g)})
    site_faq = [f for f in S.site.get("site_faq") or [] if f.get("q") and f.get("a")]
    groups = course_groups(S.courses)
    shown_courses = [c for grp in groups for c in grp["items"][:2]]
    linked_guides = [g for g in S.guides if any(p["href"] == g["_path"] for p in purposes)]
    lastmod = date_of(featured + [h["e"] for h in hero] + linked_guides + shown_courses)
    h = present.home_vm(S)
    # includesAttraction names exactly the places the home shows as 대표 장소 (home.html.j2: h.featured, else the
    # first four of `featured`), so the structured data never names a place the page does not show
    shown = [c["e"] for c in h["featured"]] or featured[:4]
    page = {"title": f"{S.site['site_name']} — {region} 관광지·맛집·숙소·코스·축제·영상",
            # the counts the home shows, in one sentence: the longest wording within DESC_MAX
            "description": first_fit(*(f"{region} 관광지 {len(S.lists['attraction'])}곳, 음식점 {len(S.lists['food'])}곳, "
                                       f"숙소 {len(S.lists['stay'])}곳의 {tail}" for tail in (
                                           f"이용시간·쉬는 날·요금·주차와 공식 코스, 축제 일정, 영상 {len(S.videos)}편을 모았습니다.",
                                           f"이용시간·쉬는 날·요금·주차와 코스·축제 일정, 영상 {len(S.videos)}편을 모았습니다.",
                                           "이용시간·쉬는 날·요금·주차를 모았습니다."))),
            "canonical": S.site_url + "/", "crumbs": [],
            "image": hero[0]["img"]["url"] if hero else "",
            # FAQPage only where the FAQ is visible: home.html.j2 does not render site_faq (yet), so no FAQPage.
            "jsonld": [jsonld.dumps(jsonld.home_graph(S.site, S.site_url,
                                                      [jsonld.place_ref(e["_url"], e) for e in shown], []))]}
    counts = {k: len(v) for k, v in S.lists.items()}
    area_counts: dict[str, int] = {}
    for e in S.entities:
        if e["_area"]:
            area_counts[e["_area"]] = area_counts.get(e["_area"], 0) + 1
    top_areas = sorted(area_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    video_topics = video_groups(S.videos) if S.videos else []
    home_videos = [g["items"][0] for g in video_topics if g["title"] != "기타"][:6]  # the top video of each topic
    page["videos"] = bool(home_videos)
    # the centre question card (templates/_ask.html.j2): each starter links to the page that answers it — a guide this
    # build publishes, or /events/ when it is built; None: no card
    ask_starters = None if S.ask is None else ask.starters(
        S.ask, "ko", {g["id"]: g["_path"] for g in S.guides}, {"events": "/events/"} if S.events else {})
    _render(env, S, out, "home.html.j2", "/", page, "home", lastmod, featured=featured, site_faq=site_faq, hero=hero,
            home_videos=home_videos, video_topics=video_topics, video_total=len(S.videos),
            counts=counts, guides=S.guides, courses=S.courses, purposes=purposes,
            course_groups=groups, events=upcoming_events(S)[:3], top_areas=top_areas,
            themes=[t for t in S.themes if any(t["slug"] in (e.get("themes") or []) for e in S.entities)], h=h,
            ask_starters=ask_starters,
            # the SNS row (owner 2026-10-14: 'SNS 게시물이 좀 더 잘 보이면'): the newest published posts, our notes only
            home_posts=sorted([a for a in getattr(S, "abroad", None) or [] if a.get("kind") == "post"],
                              key=lambda a: (a.get("date") or "", a["id"]), reverse=True)[:8],
            n_posts=sum(a.get("kind") == "post" for a in getattr(S, "abroad", None) or []),
            home_blog=blog_home(S))   # 군산각 블로그 (operator 2026-10-30): the /blog/ cards, one per category first

    page = {"title": f"페이지를 찾을 수 없습니다 | {S.site['site_name']}", "description": "", "canonical": S.site_url + "/",
            "crumbs": [], "jsonld": []}
    _render(env, S, out, "404.html.j2", "/404.html", page, "404", h=h)

    for code, site in S.intl.sites.items():  # /en/ … (pipeline/en_site.py): indexable pages join sitemap.xml via S.pages
        st = en_site.render(site, env, out, S.intl)
        if code == "en":
            S.stats["en"] = st
        else:
            S.stats.setdefault("intl", {})[code] = st
        stale = sum(st["stale_skipped"].values())
        if stale:  # the Korean changed after the translation: only the Korean page is built until it is redone
            print(f"경고: {code} 번역이 현재 한국어와 달라(ko_hash 불일치) 페이지를 만들지 않은 항목 {stale}건 "
                  f"{st['stale_skipped']} — tools/en_content.py prepare --lang {code}로 다시 번역", file=sys.stderr)
        untranslated = {k: n for k, n in st["untranslated"].items() if n}
        if untranslated:  # a published Korean record this version never got: only the Korean page (the menu says so)
            print(f"경고: {code} 번역이 없는 공개 항목 {sum(untranslated.values())}건 {untranslated} "
                  f"— tools/en_content.py prepare --lang {code}", file=sys.stderr)
        if st.get("missing_strings"):
            print(f"경고: {code} strings.json에 없는 이름표 {len(st['missing_strings'])}개(대신 키를 표시) "
                  f"{st['missing_strings'][:5]}", file=sys.stderr)
    for code, missing in S.intl.skipped.items():  # data/<region>/<code> exists but its UI words are incomplete
        S.stats.setdefault("intl_skipped", {})[code] = len(missing)
        print(f"경고: {code} strings.json에 화면 문구(chrome.*) {len(missing)}개가 없어 이 언어 페이지를 만들지 않음 "
              f"(예: {missing[:3]}) — tools/en_content.py prepare --lang {code}의 strings 묶음", file=sys.stderr)

    # assets: the partials in templates/assets/css become one /assets/style.css (see site_css); the folder itself
    # is not published. AI art renditions (templates/assets/art, pipeline/art.py) go out only when a page uses them.
    shutil.copytree(TEMPLATES / "assets", out / "assets", ignore=shutil.ignore_patterns("css", "art"))
    art.copy_used(out)
    # site icon at the root addresses browsers, search engines and AI answer chips look up (operator's AIO2O mark)
    brand = TEMPLATES / "assets" / "brand"
    for src, dst in (("favicon.ico", "favicon.ico"), ("icon-180.png", "apple-touch-icon.png")):
        if (brand / src).exists():
            shutil.copyfile(brand / src, out / dst)
    (out / "assets" / "style.css").write_text(site_css(art.slot_css_needed(out)), "utf-8")
    (out / "robots.txt").write_text(robots_txt(S), "utf-8")
    (out / "sitemap.xml").write_text(sitemap_xml(S), "utf-8")
    (out / "sitemap-ko.xml").write_text(sitemap_xml(S, ko_only=True), "utf-8")
    (out / "rss.xml").write_text(rss_xml(S), "utf-8")
    short, full = llms_txt(S)
    (out / "llms.txt").write_text(short, "utf-8")
    (out / "llms-full.txt").write_text(full, "utf-8")
    # the site assistant's knowledge (pipeline/chat_index.py): /chat/catalog.txt, docs.json, index.json — api/chat.js
    # reads them from public/chat/ (vercel.json includeFiles)
    S.stats["chat"] = chat_index.export(S, out)

    if S.dead_dropped:
        print(f"홈페이지 링크 숨김 {len(S.dead_dropped)}건(data/{data_dir.name}/dead_links.json)", file=sys.stderr)
    S.stats.update({"mode": mode, "pages": len(S.pages), "guides": len(S.guides), "columns": len(S.columns), "courses": len(S.courses),
                    "events": len(S.events), "event_pages": len(S.series), "out": str(out)})
    if S.warnings:  # view-model notes (pipeline/present.py): a hard-wired place or anchor missing from the data
        notes = list(dict.fromkeys(S.warnings))
        S.stats["view_warnings"] = {"count": len(notes), "first": notes[:5]}
    print(json.dumps(S.stats, ensure_ascii=False))
    return S.stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--mode", choices=list(MODES), default="production")
    a = ap.parse_args(argv)
    build(a.data, a.out, a.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
