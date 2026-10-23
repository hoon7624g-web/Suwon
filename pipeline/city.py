"""site.json -> City: the one place where city-specific behaviour is derived (CLAUDE.md 1·4, design 1.4).

Every value comes from data/<city>/site.json; the defaults here are neutral or empty, and no city's name is written in
this module. Code reaches the City of a build through city.of(site) (one City per site object, no "current city"
global), templates through City.view() (present.common_vm puts it in every page as `cityv`).

What it derives:
- addresses: parse_address (시·도 or an alias, the 시 when it differs, the 구·군 from `districts`, the 동·읍·면 from
  the bracket or the token right after, the road), strip_city_prefix, place_line ('OO시 OO구 한빛동'), area_label
  ('OO구 한빛동'), map_query_prefix, admin_words (for slugs);
- names: names_city / strip_region_prefix (a homograph such as a dish named after the city is not the city),
  title_suffix_rx (a TourAPI title's '(OO)' tail);
- the stock summary sentence (taut_rx, the index rule of schema.summary_problems) and the locator sentence
  (locator_rx, the display rule of present.distinct_line);
- regions: district_slug ('한빛구' -> 'hanbit-gu'), region_key (fragment ids), the configured anchors / far / none;
- sources: short_provider, official_label; designations and category overrides layered over the national tables
  in pipeline.schema; view() for templates; problems() for a config check.

Imports: the standard library, pipeline.romanize, pipeline.slugs and pipeline.textutil (none of them imports this
module). pipeline.schema is read inside the designation methods only (schema never imports city).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .slugs import SLUG_POLICIES, SLUG_RE, slugify
from .textutil import display_address, road_from_address, squash_ws, url_domain


class CityConfigError(ValueError):
    """site.json lacks a key every city needs (REQUIRED)."""


REQUIRED = ("site_url", "region", "region_admin", "locality")   # site_url may be '' (the production gate reports it)
REGION_MODES = ("district", "anchors")
# site.json languages: Korean and the other versions the engine knows (pipeline/locales.py CODES, the same order)
LANGUAGES = ("ko", "en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
KINDS = ("attraction", "stay", "food")
# site.json categories: per-key overrides of the national source-category tables (dicts), heritage_buildings a list
CATEGORY_MAPS = ("stay_type", "food_type", "attr_type", "stay_schema", "cuisine")
CATEGORY_LISTS = ("heritage_buildings",)
# engine words per region mode, used when site.json regions leaves them out
REGION_WORDS = {"district": {"label": "구·군", "area_label": "동·읍·면", "none_label": "구·군 미기재"},
                "anchors": {"label": "권역", "area_label": "읍·면·동", "none_label": "권역 미정"}}
NATIONAL_PROVIDER = ("TourAPI", "한국관광공사")
NATIONAL_PROVIDER_SHORT = "한국관광공사"

# 동·읍·면 forms (design 3.1): a bracket's first item, or the token right after the 구·군 (or the 시)
_AREA_ITEM = re.compile(r"^(?:[가-힣0-9]+(?:동|읍|면|리)(?:[0-9]+가)?|[가-힣]+로(?:[0-9]+가)?)$")
_AREA_POS = re.compile(r"^(?:[가-힣0-9]+(?:동|읍|면)(?:[0-9]+가)?|[가-힣]+로[0-9]+가)$")
_LAST_BRACKET = re.compile(r"\(([^()]*)\)[^()]*$")
# what may follow a 시·도 / 시 / 구·군 written without a space ('…도OO시OO면 …'): an address unit, not a name
_GLUED_UNIT = re.compile(r"[가-힣0-9]+(?:읍|면|동|리|가|로|길)(?=[\s(,0-9]|$)")


@dataclass(frozen=True)
class Address:
    """A parsed address. admin is region_admin when the address starts with it or an alias, else ''."""
    admin: str = ""
    district: str = ""
    area: str = ""
    road: str = ""
    rest: str = ""


def _alt(words) -> str:
    """A regex alternation of literal words, longest first."""
    return "|".join(re.escape(w) for w in sorted({w for w in words if w}, key=lambda w: (-len(w), w)))


def _strs(value) -> tuple[str, ...]:
    return tuple(squash_ws(v) for v in value or () if isinstance(v, str) and squash_ws(v))


def _pairs(value, a: str, b: str) -> tuple[tuple[str, str], ...]:
    return tuple((squash_ws(x.get(a)), squash_ws(x.get(b))) for x in value or ()
                 if isinstance(x, dict) and squash_ws(x.get(a)))


@dataclass(frozen=True, eq=False)
class City:
    region: str
    region_en: str
    region_admin: str
    locality: str
    site_url: str = ""
    districts: tuple[str, ...] = ()
    address_aliases: tuple[str, ...] = ()
    homographs: tuple[str, ...] = ()
    region_mode: str = "district"
    region_label: str = ""
    area_label_word: str = ""
    none_label: str = ""
    anchors: tuple[dict, ...] = ()
    far: dict | None = None
    dist_anchor_ids: tuple[str, ...] = ()
    official_domains: tuple[tuple[str, str], ...] = ()
    provider_short: tuple[tuple[str, str], ...] = ()
    designations: dict = field(default_factory=dict)
    categories: dict = field(default_factory=dict)
    list_hubs: dict = field(default_factory=dict)
    list_filters: dict = field(default_factory=dict)
    video_topics: tuple[tuple[str, str], ...] = ()
    search_examples: tuple[str, ...] = ()
    slug_collision: str = "number"
    home: dict = field(default_factory=dict)
    title_suffixes: tuple[str, ...] = ()
    id_prefix: str = ""
    languages: tuple[str, ...] = ("ko",)
    raw: dict = field(default_factory=dict, repr=False)
    _memo: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ names
    @property
    def admin_line(self) -> str:
        """시·도 and 시 without repeating one: 'OO광역시' (locality == region_admin) or 'OO도 OO시'."""
        return " ".join(dict.fromkeys(x for x in (self.region_admin, self.locality) if x))

    @property
    def _admin_names(self) -> tuple[str, ...]:
        """What an address may start with for the 시·도: region_admin and the aliases, longest first."""
        return tuple(sorted({self.region_admin, *self.address_aliases} - {""}, key=lambda w: (-len(w), w)))

    @property
    def _formal_heads(self) -> tuple[str, ...]:
        """Names that state the city in a sentence: region_admin, locality and aliases ending in 시·도 ('OO시'),
        never the bare short name (it is also part of other words)."""
        return tuple({self.region_admin, self.locality, *(a for a in self.address_aliases if a.endswith(("시", "도")))}
                     - {""})

    def _homograph_at(self, text: str) -> bool:
        return any(text.startswith(h) for h in self.homographs)

    def names_city(self, name: str | None) -> bool:
        """Does the name contain the city's name ('OO 근대골목', 'OO광역시립…')? A homograph ('OO탕' when the city's
        name is also a fish) is taken out first, so a dish name does not count."""
        n = str(name or "")
        for h in sorted(self.homographs, key=len, reverse=True):
            n = n.replace(h, " ")
        return any(w in n for w in {self.region, self.region_admin, self.locality, *self.address_aliases} if w)

    def strip_region_prefix(self, name: str | None) -> str:
        """A name without a leading short region name, for name-matching keys ('OO 동국사' -> '동국사'); a name that
        starts with a homograph is returned as it is."""
        n = str(name or "")
        if not self.region or self._homograph_at(n):
            return n
        return re.sub(rf"^{re.escape(self.region)}\s*", "", n)

    @property
    def title_suffix_rx(self) -> re.Pattern:
        """A TourAPI title's bracketed city tail, matched whole at the end only: '(OO)', '(OO광역시)', '(OO 한빛구)',
        '(한빛구)', plus tourapi.title_suffixes. Use rx.sub('', title)."""
        if "title_suffix_rx" not in self._memo:
            heads = _alt({self.region, self.region_admin, self.locality, *self.address_aliases, *self.title_suffixes})
            body = f"(?:{heads})"
            if self.districts:
                body = f"(?:(?:{heads})\\s*)?(?:{_alt(self.districts)})|{body}"
            self._memo["title_suffix_rx"] = re.compile(rf"\s*\((?:{body})\)\s*$")
        return self._memo["title_suffix_rx"]

    # ------------------------------------------------------------------ addresses
    def _glued_ok(self, after: str) -> bool:
        """After a prefix written without a space: the 시, a 구·군 or an address unit — not the rest of a name."""
        heads = [w for w in (self.locality, *self.districts) if w]
        return any(after.startswith(w) for w in heads) or bool(_GLUED_UNIT.match(after))

    def _eat(self, text: str, words) -> tuple[str, str]:
        """(word, rest) when text starts with one of words (longest first) followed by a space, the end, or a glued
        address unit; ('', text) otherwise."""
        for w in sorted((w for w in words if w), key=lambda w: (-len(w), w)):
            if not text.startswith(w):
                continue
            after = text[len(w):]
            if not after or after[0].isspace():
                return w, after.lstrip()
            if self._glued_ok(after):
                return w, after
        return "", text

    def _prefix(self, text: str) -> tuple[str, str, str]:
        """(admin, district, rest) after the leading 시·도 (or alias), 시 and 구·군, in that order."""
        if self._homograph_at(text):
            return "", "", text
        w, t = self._eat(text, self._admin_names)
        admin = self.region_admin if w else ""
        if self.locality and self.locality != self.region_admin:
            _, t = self._eat(t, (self.locality,))
        district = ""
        if self.districts:
            district, t = self._eat(t, self.districts)
        return admin, district, t

    def parse_address(self, raw: str | None) -> Address:
        """Design 3.1. After the national renames (textutil.display_address), the start is read in order — the
        시·도 or an alias (longest first), the 시 when it differs from the 시·도, a 구·군 of `districts` — spaces
        optional. The 동·읍·면 (area) is the first item of the last bracket when it is a 동·읍·면·리 (법정동 'N가' kept
        whole) or 'OO로N가'; otherwise the token right after that prefix when it is 'OO동[N가]', 'OO읍', 'OO면' or
        'OO로N가' (by position, so a building's 'O동 2층' further on is not read). road: textutil.road_from_address."""
        a = display_address(raw)
        admin, district, rest = self._prefix(a)
        area = ""
        m = _LAST_BRACKET.search(a)
        if m:
            first = squash_ws(m.group(1).split(",")[0])
            if _AREA_ITEM.match(first):
                area = first
        if not area:
            token = rest.split(" ", 1)[0] if rest else ""
            if _AREA_POS.match(token):
                area = token
        return Address(admin=admin, district=district, area=area, road=road_from_address(rest), rest=rest)

    def strip_city_prefix(self, text: str | None) -> str:
        """Text without the leading 시·도 (or alias) and, when it differs, the 시: 'OO광역시 한빛구 …' -> '한빛구 …',
        'OO도 OO시 구영7길 69' -> '구영7길 69'. The 구·군 stays. Whitespace squashed, national renames applied."""
        t = display_address(text)
        if self._homograph_at(t):
            return t
        _, t = self._eat(t, self._admin_names)
        if self.locality and self.locality != self.region_admin:
            _, t = self._eat(t, (self.locality,))
        return t

    def admin_words(self, raw: str | None) -> frozenset:
        """The administrative words of an address for slugs.slugify(admin_words=…): its 구·군 and 동·읍·면."""
        a = self.parse_address(raw)
        return frozenset(x for x in (a.district, a.area) if x)

    def address_parts(self, e: dict) -> tuple[str, str]:
        """(구·군, 동·읍·면) of a place or an event: the build's `_district`/`_area` when set, else parsed from its
        address (facts.address, or an event's address)."""
        if "_district" in e:
            return e.get("_district") or "", e.get("_area") or ""
        a = self.parse_address((e.get("facts") or {}).get("address") or e.get("address"))
        return a.district, a.area

    def place_line(self, e: dict) -> str:
        """The page's place line: 'OO광역시 한빛구 한빛동1가', 'OO시 한빛동', 'OO광역시 누리구'."""
        return " ".join(x for x in (self.locality, *self.address_parts(e)) if x)

    def area_label(self, e: dict) -> str:
        """Short place label for cards and lists: '한빛구 한빛동1가', '누리구' (no 동), '한빛동' (no 구·군); '' when the
        address names neither."""
        return " ".join(x for x in self.address_parts(e) if x)

    def map_query_prefix(self, e: dict) -> str:
        """What a map search puts before the name: 'OO 한빛구', or the short region name alone."""
        return " ".join(x for x in (self.region, self.address_parts(e)[0]) if x)

    # ------------------------------------------------------------------ sentences
    @property
    def _w(self) -> str:
        """W of design 3.6: the 시·도, the 시, aliases ending in 시·도, and a 구·군 (optionally after the short name)."""
        w = _alt(self._formal_heads)
        if self.districts:
            d = f"(?:{re.escape(self.region)}\\s+)?(?:{_alt(self.districts)})"
            w = f"{w}|{d}" if w else d
        return w

    def taut_rx(self, name: str | None) -> re.Pattern:
        """The stock first sentence 'XX은 <W> … 있는/위치한 … 입니다.' (CLAUDE.md 3.5) for one place name. A sentence
        that only mentions the short region name ('XX은 OO에서 …') is not one."""
        key = ("taut", name or "")
        if key not in self._memo:
            self._memo[key] = re.compile(rf"^{re.escape(name or '')}\s*(은|는)\s*(?:{self._w})[^.]*?(있는|위치한)[^.]*?입니다\.$")
        return self._memo[key]

    @property
    def locator_rx(self) -> re.Pattern:
        """'X는 [W ]…동/면/읍/가/리/로/길/도[의 …]에 있는' or 'X는 [W ]W에 있는': a sentence that only restates where
        the place is (present.distinct_line skips it)."""
        if "locator_rx" not in self._memo:
            w = self._w
            self._memo["locator_rx"] = re.compile(
                rf"^.{{1,40}}?[은는이가] (?:(?:{w})\s+)*(?:\S+(?:동|면|읍|가|리|로|길|도)(?:의 \S+)?|(?:{w}))에 있는")
        return self._memo["locator_rx"]

    # ------------------------------------------------------------------ regions and keys
    def district_slug(self, district: str | None) -> str:
        """'한빛구' -> 'hanbit-gu', '누리군' -> 'nuri-gun' (RR, the unit hyphenated)."""
        d = squash_ws(district)
        return slugify(d, admin_words=(d,))

    def region_key(self, region_name: str | None) -> str:
        """The ASCII key of a region group: an anchor's key, a 구·군's district_slug, 'far', 'none'; any other name
        slugified ('other' when nothing is left)."""
        n = squash_ws(region_name)
        for a in self.anchors:
            if a.get("name") == n and a.get("key"):
                return a["key"]
        if self.far and n == self.far.get("label"):
            return "far"
        if n == self.none_label:
            return "none"
        if n in self.districts:
            return self.district_slug(n)
        return slugify(n) or "other"

    # ------------------------------------------------------------------ sources
    def short_provider(self, provider: str | None) -> str:
        """A provider's short name: '한국관광공사' for TourAPI; a provider_short match; the whole name when it names a
        구·군 ('OO광역시 한빛구 …'); the locality when it names the city ('OO시 문화관광' -> 'OO시'); else as given."""
        p = squash_ws(provider)
        if any(x in p for x in NATIONAL_PROVIDER):
            return NATIONAL_PROVIDER_SHORT
        for match, short in self.provider_short:
            if match in p:
                return short
        heads = [self.locality] + ([a for a in self.address_aliases if a.endswith(("시", "도"))]
                                   if self.locality == self.region_admin else [])
        for h in (h for h in heads if h and h in p):
            if self.districts and re.search(rf"{re.escape(h)}\s*(?:{_alt(self.districts)})", p):
                return p
            return self.locality
        return p

    def official_label(self, url: str | None) -> str:
        """The configured name of an official site the URL is on (official_domains: the domain or a subdomain of it,
        the longest matching domain winning), else ''."""
        host = url_domain(url)
        hits = [(len(dom), name) for dom, name in self.official_domains
                if host and (host == dom or host.endswith("." + dom))]
        return max(hits)[1] if hits else ""

    # ------------------------------------------------------------------ designations and categories
    def _designation_tables(self) -> tuple[dict, dict, frozenset]:
        if "designations" not in self._memo:
            from . import schema  # national tables live in schema; schema never imports this module
            own = [t for t in self.designations.get("order") or () if isinstance(t, str)]
            order = own + [t for t in schema.DESIGNATION_ORDER_NATIONAL if t not in own]
            short = {**schema.DESIGNATION_SHORT_NATIONAL, **(self.designations.get("short") or {})}
            year = frozenset(t for t in self.designations.get("show_year") or () if isinstance(t, str))
            self._memo["designations"] = ({t: i for i, t in enumerate(order)}, short, year)
        return self._memo["designations"]

    def designation_rank(self, dtype: str | None) -> int:
        """Display priority: designations.order (it may list national types too), then the national order; an unknown
        type after all of them."""
        order = self._designation_tables()[0]
        return order.get(dtype or "", len(order))

    def designation_short_label(self, dtype: str | None) -> str:
        """The chip word of a type ('백년가게', a city list's configured short name), '' for an unknown type."""
        return self._designation_tables()[1].get(dtype or "", "")

    def designation_show_year(self, dtype: str | None) -> bool:
        """Is the year part of what the designation says (designations.show_year)?"""
        return (dtype or "") in self._designation_tables()[2]

    def category(self, kind_map: str, cat: str | None, base: dict | None = None, default=None):
        """A source category looked up in categories[kind_map] (this city's override), then in `base` (the engine's
        national table); `default` when neither has it. kind_map: one of CATEGORY_MAPS."""
        c = squash_ws(cat)
        own = self.categories.get(kind_map)
        if isinstance(own, dict) and c in own:
            return own[c]
        if base and c in base:
            return base[c]
        return default

    def category_names(self, key: str) -> tuple[str, ...]:
        """The configured names under a list key (heritage_buildings) or the keys of a map."""
        own = self.categories.get(key)
        return tuple(own) if isinstance(own, (dict, list, tuple)) else ()

    # ------------------------------------------------------------------ templates and checks
    def view(self) -> dict:
        """What templates read (`cityv`)."""
        return {"admin_line": self.admin_line, "region": self.region, "region_label": self.region_label,
                "area_label": self.area_label_word, "region_mode": self.region_mode,
                "search_examples": list(self.search_examples), "districts": list(self.districts),
                "none_label": self.none_label, "far_label": (self.far or {}).get("label", "")}

    def problems(self) -> list[str]:
        """Config problems (Korean, one line each); [] when site.json is consistent."""
        raw, out = self.raw, []
        dup = lambda xs: sorted({x for x in xs if list(xs).count(x) > 1})
        for key in ("districts", "address_aliases", "region_homographs", "search_examples", "dist_anchors"):
            v = raw.get(key)
            if v is not None and (not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v)):
                out.append(f"{key}: 빈 값이 아닌 문자열 목록이어야 함")
        if dup(self.districts):
            out.append(f"districts 중복: {', '.join(dup(self.districts))}")
        if dup(self.address_aliases):
            out.append(f"address_aliases 중복: {', '.join(dup(self.address_aliases))}")
        for a in self.address_aliases:
            if a in self.homographs or a in self.districts:
                out.append(f"address_aliases에 동형이의어·구·군 이름은 쓸 수 없음: {a}")
        if self.region_mode not in REGION_MODES:
            out.append(f"regions.mode 값 오류: {self.region_mode!r} (허용: {', '.join(REGION_MODES)})")
        if self.region_mode == "district" and not self.districts:
            out.append("regions.mode가 district인데 districts가 비어 있음")
        anchors = (raw.get("regions") or {}).get("anchors") or []
        if not isinstance(anchors, list):
            out.append("regions.anchors: 목록이어야 함")
            anchors = []
        keys, names = [], []
        for a in anchors:
            if not isinstance(a, dict):
                out.append(f"regions.anchors 항목 형식 오류: {a!r}")
                continue
            if not (isinstance(a.get("key"), str) and SLUG_RE.match(a["key"])):
                out.append(f"regions.anchors key 형식 오류(a-z·0-9·하이픈): {a.get('key')!r}")
            for k in ("name", "place_id"):
                if not squash_ws(a.get(k)):
                    out.append(f"regions.anchors {k} 없음: {a.get('key') or a!r}")
            keys.append(a.get("key"))
            names.append(a.get("name"))
        twice = dup([k for k in keys if k]) + dup([n for n in names if n])
        if twice:
            out.append(f"regions.anchors key·name 중복: {', '.join(twice)}")
        if set(keys) & {"far", "none"}:
            out.append("regions.anchors key에 far·none은 쓸 수 없음")
        far = (raw.get("regions") or {}).get("far")
        if far is not None and not (isinstance(far, dict) and isinstance(far.get("m"), (int, float)) and far["m"] > 0
                                    and squash_ws(far.get("label"))):
            out.append("regions.far는 null 또는 {m: 양수, label: 이름}")
        if self.slug_collision not in SLUG_POLICIES:
            out.append(f"slug_policy.collision 값 오류: {self.slug_collision!r} (허용: {', '.join(SLUG_POLICIES)})")
        slugs = [s for _, s in self.video_topics]
        for t, s in self.video_topics:
            if not SLUG_RE.match(s):
                out.append(f"video_topics slug 형식 오류: {t} {s!r}")
            if s == "other" and t != "기타":
                out.append(f"video_topics slug 'other'는 '기타' 전용: {t}")
        if dup(slugs):
            out.append(f"video_topics slug 중복: {', '.join(dup(slugs))}")
        if len(self.video_topics) != len(raw.get("video_topics") or []):
            out.append("video_topics 항목은 {title, slug}")
        if self.id_prefix and not SLUG_RE.match(self.id_prefix):
            out.append(f"id_prefix 형식 오류(a-z·0-9·하이픈): {self.id_prefix!r}")
        if not self.languages or "ko" not in self.languages or set(self.languages) - set(LANGUAGES):
            out.append(f"languages 값 오류: {list(self.languages)} (ko 필수, 허용: {', '.join(LANGUAGES)})")
        for dom, name in self.official_domains:
            if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", dom) or not name:
                out.append(f"official_domains 항목은 {{domain(소문자, scheme 없이), name}}: {dom} {name!r}")
        if len(self.official_domains) != len(raw.get("official_domains") or []):
            out.append("official_domains 항목은 {domain, name}")
        if any(not short for _, short in self.provider_short) or \
                len(self.provider_short) != len(raw.get("provider_short") or []):
            out.append("provider_short 항목은 {match, short}")
        for k, v in self.categories.items():
            if k in CATEGORY_MAPS and not isinstance(v, dict):
                out.append(f"categories.{k}: 객체여야 함")
            elif k in CATEGORY_LISTS and not isinstance(v, list):
                out.append(f"categories.{k}: 목록이어야 함")
            elif k not in CATEGORY_MAPS + CATEGORY_LISTS:
                out.append(f"categories 키 오류: {k} (허용: {', '.join(CATEGORY_MAPS + CATEGORY_LISTS)})")
        order = self.designations.get("order") or []
        if not isinstance(order, list) or dup(order):
            out.append("designations.order: 중복 없는 목록이어야 함")
        if not isinstance(self.designations.get("short") or {}, dict):
            out.append("designations.short: 객체여야 함")
        for k, v in self.list_hubs.items():
            if k not in KINDS or not (isinstance(v, dict) and squash_ws(v.get("guide_id"))):
                out.append(f"list_hubs 항목 오류: {k} (kind: {', '.join(KINDS)}, 값: {{guide_id, label}})")
        return out


def from_site(site: dict) -> City:
    """A City from a site.json dict. CityConfigError when a REQUIRED key is missing (site_url may be empty, the
    others may not); everything else has a neutral default and problems() reports what is inconsistent."""
    if not isinstance(site, dict):
        raise CityConfigError("site.json은 객체여야 합니다")
    missing = [k for k in REQUIRED if not isinstance(site.get(k), str) or (k != "site_url" and not site[k].strip())]
    if missing:
        raise CityConfigError(f"site.json 필수 키 없음: {', '.join(missing)}")
    districts = _strs(site.get("districts"))
    regions = site.get("regions") if isinstance(site.get("regions"), dict) else {}
    mode = squash_ws(regions.get("mode")) or ("district" if districts else "anchors")
    words = REGION_WORDS.get(mode, REGION_WORDS["district"])
    far = regions.get("far")
    tour = site.get("tourapi") if isinstance(site.get("tourapi"), dict) else {}
    dict_of = lambda key: site.get(key) if isinstance(site.get(key), dict) else {}
    return City(
        region=squash_ws(site["region"]),
        region_en=squash_ws(site.get("region_en")),
        region_admin=squash_ws(site["region_admin"]),
        locality=squash_ws(site["locality"]),
        site_url=squash_ws(site["site_url"]).rstrip("/"),
        districts=districts,
        address_aliases=_strs(site.get("address_aliases")),
        homographs=_strs(site.get("region_homographs")),
        region_mode=mode,
        region_label=squash_ws(regions.get("label")) or words["label"],
        area_label_word=squash_ws(regions.get("area_label")) or words["area_label"],
        none_label=squash_ws(regions.get("none_label")) or words["none_label"],
        anchors=tuple(a for a in regions.get("anchors") or () if isinstance(a, dict)),
        far=far if isinstance(far, dict) else None,
        dist_anchor_ids=_strs(site.get("dist_anchors")),
        official_domains=_pairs(site.get("official_domains"), "domain", "name"),
        provider_short=_pairs(site.get("provider_short"), "match", "short"),
        designations=dict_of("designations"),
        categories=dict_of("categories"),
        list_hubs=dict_of("list_hubs"),
        list_filters=dict_of("list_filters"),
        video_topics=tuple((t, s) for t, s in _pairs(site.get("video_topics"), "title", "slug") if s),
        search_examples=_strs(site.get("search_examples")),
        slug_collision=squash_ws((site.get("slug_policy") or {}).get("collision")) or "number",
        home=dict_of("home"),
        title_suffixes=_strs(tour.get("title_suffixes")),
        id_prefix=squash_ws(site.get("id_prefix")),
        languages=_strs(site.get("languages")) or ("ko",),
        raw=site,
    )


_CACHE: dict[int, tuple[dict, City]] = {}
_CACHE_MAX = 64


def of(site: dict) -> City:
    """The City of this site object, computed once per object (kept by id and checked with `is`, so a new dict —
    another data folder in the same process — always gets its own City)."""
    hit = _CACHE.get(id(site))
    if hit and hit[0] is site:
        return hit[1]
    c = from_site(site)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[id(site)] = (site, c)
    return c
