"""예약하기, step 1 (pipeline/booking.py, data/gunsan/booking.json, templates/_ui.html.j2 book()): the official booking
pages a page links as buttons. Only addresses the data already holds (the registry's are checked against places.json,
the guides' sources and text, present.OFFICIAL_WEB and booking.OFFICIAL_ENTRY), never an OTA, Naver, a blog or a social
network; each version opens the service's page in its language, else the Simplified Chinese / English one (labelled),
else the Korean one '(in Korean)'; a facility's own booking address by its domain with no language claimed. The words
exist for Korean and every version (locales.BOOK_WORDS) and the chat's cards use the same word (chat.js kinds.book).
The pages themselves: tests/test_en_site.py (one production build of every version)."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import booking
from pipeline import locales as LC
from pipeline import present
from pipeline.build import State
from pipeline.textutil import drop_dead_links, link_url, url_key
from pipeline.validate import PageScan, booking_problems

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gunsan"
REG = json.loads((DATA / "booking.json").read_text("utf-8"))
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module")
def S():
    return State(DATA, "production")


def _ids(targets):
    return [t["key"] for t in targets]


# ------------------------------------------------------------------ the registry and the words
def test_registry_services_have_address_basis_date_and_a_name_in_every_language(S):
    assert booking.data_problems(S) == []
    services = REG["services"]
    assert list(services) == ["bus", "rail", "ferry", "citytour", "forest", "camp", "heli"]   # the button order
    for key, s in services.items():
        assert link_url(s["url"]) == s["url"] and s["basis"].strip(), key
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s["checked_at"]), key
        for u in [s["url"], *(s.get("pages") or {}).values(), *(s.get("match") or [])]:
            assert u.startswith("https://") and not booking.excluded(u, REG), (key, u)
        assert set(s.get("pages") or {}) <= set(LC.ORDER), key
    published = {e["id"] for e in S.entities}
    for pid, keys in REG["places"].items():
        assert pid in published, pid
        assert keys and set(keys) <= set(services), pid


def test_book_words_cover_every_version_hand_written():
    assert set(LC.BOOK_WORDS) == {"ko", *LC.ORDER}
    ko = LC.BOOK_WORDS["ko"]
    for code, w in LC.BOOK_WORDS.items():
        assert set(w) == set(ko) and set(w["svc"]) == set(REG["services"]), code
        assert all(str(v).strip() for k, v in w.items() if k != "svc") and all(v.strip() for v in w["svc"].values()), code
        if code != "ko":
            text = " ".join([*(v for k, v in w.items() if k != "svc"), *w["svc"].values()])
            assert not HANGUL.search(text), code
            assert w["book"] != ko["book"] and w["note"] != ko["note"], code   # no Korean stand-in


def test_the_chat_cards_use_the_same_word():
    js = (ROOT / "templates" / "assets" / "chat.js").read_text("utf-8")
    blocks = dict(re.findall(r'\n    "?([a-zA-Z-]+)"?: \{\n(.*?)\n    \},', js, re.S))
    for code in ("ko", *LC.ORDER):
        html = "ko" if code == "ko" else LC.get(code).html
        kinds = re.search(r"kinds: \{([^}]*)\}", blocks[html]).group(1)
        assert f'book: "{LC.BOOK_WORDS[code]["book"]}"' in kinds, code


def _web_urls(text: str) -> set[str]:
    """The links present.tel_markup makes of the official hosts a text writes (OFFICIAL_WEB)."""
    return {present.web_href(m.group(1), m.group(2)) for m in present.WEB.finditer(text or "")}


def test_every_registry_address_is_already_in_the_data():
    """No invented URL: each address of booking.json (url, pages, match) is a value of places.json, a guide's source,
    a link the guides' or places' text makes (present.WEB), present.OFFICIAL_WEB or booking.OFFICIAL_ENTRY."""
    known: set[str] = set()
    for p in json.loads((DATA / "places.json").read_text("utf-8")):
        facts, official = p.get("facts") or {}, p.get("official") or {}
        for k in ("homepage", "reservationurl"):
            known.add(link_url(facts.get(k)))
            known |= {link_url(a.get("value")) for a in (p.get("fact_alternatives") or {}).get(k) or []}
        known.add(link_url(official.get("homepage")))
        texts = [p.get("summary")] + [d.get("text") for d in p.get("details") or []] + [f.get("a") for f in p.get("faq") or []]
        for t in texts:
            known |= _web_urls(t)
    for g in json.loads((DATA / "guides.json").read_text("utf-8")):
        known |= {s.get("url") for s in g.get("sources") or [] if s.get("url")}
        for t in [g.get("summary")] + [b.get("text") for b in g.get("body") or []] + [f.get("a") for f in g.get("faq") or []]:
            known |= _web_urls(t)
    for ko_url, intl_url, _ in present.OFFICIAL_WEB.values():
        known |= {ko_url, intl_url}
    for pages in booking.OFFICIAL_ENTRY.values():
        known |= set(pages.values())
    known = {url_key(u) for u in known if u}
    for key, s in REG["services"].items():
        for u in [s["url"], *(s.get("pages") or {}).values(), *(s.get("match") or [])]:
            assert url_key(u) in known, (key, u)


def test_official_entry_and_the_registry_pages_agree():
    """booking.OFFICIAL_ENTRY (the guides' sources) and booking.json pages name the same language pages."""
    for host, pages in booking.OFFICIAL_ENTRY.items():
        s = next(s for s in REG["services"].values() if host in (s.get("hosts") or []))
        assert s["pages"] == pages, host


# ------------------------------------------------------------------ targets
def test_place_targets(S):
    by = {e["id"]: e for e in S.entities}
    assert _ids(booking.place_targets(S, by["tourapi-2737403"])) == ["forest"]          # 국립신시도자연휴양림
    assert _ids(booking.place_targets(S, by["tourapi-2734787"])) == ["camp"]            # 무녀도오토캠핑장
    assert _ids(booking.place_targets(S, by["gunsan-1447076"])) == ["heli"]             # 헬기체험비행 (www.suair.kr)
    for pid in ("tourapi-2748799", "tourapi-2748760", "tourapi-126297", "tourapi-126298", "tourapi-126296",
                "tourapi-3590209", "tourapi-3592202"):                                   # 장자도·섬 여객선 (guide-32)
        assert _ids(booking.place_targets(S, by[pid])) == ["ferry"], pid
    ramada = booking.place_targets(S, by["gunsan-307082"])
    assert [(t["key"], t["url"]) for t in ramada] == [("reservationurl", "http://www.ramadagunsan.com/view/index.do")]
    assert _ids(booking.place_targets(S, by["gunsan-306691"])) == ["reservationurl"]    # 예스모텔 (own site)
    # an OTA, Naver Map, a Naver booking alternative, the client stay: no button (step 2 / operator decision)
    for pid in ("tourapi-3532632", "tourapi-3103191", "tourapi-3101991", "gunsan-307032", "official-stay-meomum"):
        assert booking.place_targets(S, by[pid]) == [], pid
    with_buttons = [e for e in S.entities if booking.place_targets(S, e)]
    assert len(with_buttons) == 13


def test_a_dead_contested_or_excluded_reservationurl_is_no_button():
    reg = {"services": {}, "places": {}, "exclude_hosts": ["airbnb.com"]}
    dead = {"hosts": {"modoo.at": {"reason": "종료", "checked_at": "2026-10-15"}}, "urls": {}}
    fake = SimpleNamespace(booking=reg, dead_links=dead)
    e = {"id": "x", "facts": {"reservationurl": "http://hotel.modoo.at/"}}
    assert _ids(booking.place_targets(SimpleNamespace(booking=reg, dead_links=None), e)) == ["reservationurl"]
    assert booking.place_targets(fake, e) == []          # listed in dead_links.json
    drop_dead_links([e], dead)                           # as build.State does first
    assert "reservationurl" not in e["facts"] and booking.place_targets(fake, e) == []
    assert booking.place_targets(fake, {"id": "y", "facts": {"reservationurl": "https://www.airbnb.com/rooms/1"}}) == []
    assert booking.place_targets(fake, {"id": "y", "facts": {"reservationurl": "https://m.airbnb.com/rooms/1"}}) == []
    two = {"id": "z", "facts": {"reservationurl": "http://a-hotel.kr/"},
           "fact_alternatives": {"reservationurl": [{"value": "http://b-hotel.kr/", "provider": "공식 홈페이지"}]}}
    assert booking.place_targets(fake, two) == []        # sources differ: the facts card shows both, no button picks one
    assert [t["url"] for t in booking.place_targets(fake, {"id": "w", "facts": {"reservationurl": "a-hotel.kr"}})] \
        == ["https://a-hotel.kr"]


def test_guide_and_course_targets(S):
    want = {"guide-01": ["citytour"], "guide-12": ["bus", "rail", "ferry"], "guide-14": ["forest", "camp"],
            "guide-30": ["citytour"], "guide-32": ["ferry"], "guide-33": ["bus"]}
    got = {g["id"]: _ids(booking.guide_targets(S, g)) for g in S.guides if booking.guide_targets(S, g)}
    assert got == want
    courses = {c["id"]: _ids(booking.course_targets(S, c)) for c in S.courses if booking.course_targets(S, c)}
    assert courses == {"gunsan-course-m2136-2": ["ferry"], "gunsan-course-m2137-1": ["ferry"],
                       "gunsan-course-m2552-5": ["ferry"]}


# ------------------------------------------------------------------ what each version shows
def test_view_picks_the_reader_s_language_page(S):
    g12 = booking.guide_targets(S, S.guide_by_id["guide-12"])
    ink = lambda n: f"{n} (KO)"
    ko = booking.view(g12, "ko")
    assert [b["url"] for b in ko] == ["https://www.bustago.or.kr/newweb/kr/index.do", "https://www.korail.com/",
                                      "https://island.theksa.co.kr/page/booking?lang="]
    assert all(not b["hreflang"] and not b["note"] for b in ko) and ko[0]["name"] == "버스타고 시외버스"
    ja = {b["key"]: b for b in booking.view(g12, "ja", ink)}
    assert ja["bus"]["url"].endswith("/newweb/jp/index.do") and ja["bus"]["hreflang"] == "ja" and not ja["bus"]["note"]
    assert ja["ferry"]["url"].endswith("?lang=en") and (ja["ferry"]["note"], ja["ferry"]["note_lang"]) == ("English", "en")
    zt = {b["key"]: b for b in booking.view(g12, "zh-hant", ink)}
    assert zt["bus"]["url"].endswith("/newweb/cn/index.do") and zt["bus"]["hreflang"] == "zh-Hans"
    de = {b["key"]: b for b in booking.view(g12, "de", ink)}
    assert de["bus"]["url"].endswith("/newweb/en/index.do") and de["bus"]["note"] == "English"
    assert de["rail"]["url"] == "https://www.korail.com/" and de["rail"]["hreflang"] == "ko"
    assert de["rail"]["name"] == "Korail (KO)"
    ru = {b["key"]: b for b in booking.view(g12, "ru", ink)}
    assert ru["ferry"]["url"] == "https://island.theksa.co.kr/page/booking?lang=en"
    own = booking.view([{"key": "reservationurl", "url": "http://www.ramadagunsan.com/view/index.do", "pages": {}}], "de", ink)
    assert own == [{"key": "reservationurl", "url": "http://www.ramadagunsan.com/view/index.do", "hreflang": "",
                    "name": "ramadagunsan.com", "note": "", "note_lang": ""}]


# ------------------------------------------------------------------ the validator
def _page(links: str) -> PageScan:
    p = PageScan()
    p.feed(f'<html lang="ko"><body><div data-block="booking">{links}</div>'
           '<a href="https://www.korail.com/" data-track="official_click">코레일</a></body></html>')
    return p


def _a(url: str, hreflang: str = "") -> str:
    hl = f' hreflang="{hreflang}"' if hreflang else ""
    return f'<a class="btn" href="{url}" data-track="booking_click" data-provider="x"{hl}>예약하기</a>'


def test_booking_problems_catch_each_wrong_button(S):
    allowed = booking.allowed_urls(S)
    forest = booking.view(booking.place_targets(S, next(e for e in S.entities if e["id"] == "tourapi-2737403")), "ko")
    url = forest[0]["url"]
    assert booking_problems(S, _page(_a(url)), forest, "ko", allowed) == []
    # missing, extra (and not an address of the registry), an OTA host, a stray button on a page that has none
    assert len(booking_problems(S, _page(""), forest, "ko", allowed)) == 1
    extra = booking_problems(S, _page(_a(url) + _a("https://example.kr/resv")), forest, "ko", allowed)
    assert len(extra) == 2 and any("booking.json" in x for x in extra) and any("다른 예약 버튼" in x for x in extra)
    ota = booking_problems(S, _page(_a(url) + _a("https://www.airbnb.co.kr/rooms/1232259768400727594")), forest, "ko", allowed)
    assert any("OTA" in x for x in ota)
    assert len(booking_problems(S, _page(_a(url)), None, "ko", allowed)) == 1
    outside = PageScan()
    outside.feed(f'<html lang="ko"><body>{_a(url)}</body></html>')
    assert any("data-block" in x for x in booking_problems(S, outside, forest, "ko", allowed))
    # a version that opens the Korean ferry page although the registry has the English one
    ferry = booking.view(booking.place_targets(S, next(e for e in S.entities if e["id"] == "tourapi-126297")), "de",
                         lambda n: n)
    ko_url = REG["services"]["ferry"]["url"]
    wrong = booking_problems(S, _page(_a(ko_url, "ko")), ferry, "de", allowed)
    assert any("한국어 예약 페이지" in x for x in wrong) and any("없음" in x for x in wrong)
    assert booking_problems(S, _page(_a(ferry[0]["url"], "en")), ferry, "de", allowed) == []


def test_the_prompt_and_tracking_name_the_booking_links():
    rules = (ROOT / "chatbot" / "prompt.js").read_text("utf-8")
    assert rules.count("'예약하기'") == 2 and "never link a booking or travel-agency site the data does not list" in rules
    track = (ROOT / "templates" / "assets" / "track.js").read_text("utf-8")
    assert "params.link_lang = a.getAttribute('hreflang')" in track
