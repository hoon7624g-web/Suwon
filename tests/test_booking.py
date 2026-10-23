"""예약하기, step 1 (pipeline/booking.py, data/<city>/booking.json, templates/_ui.html.j2 book()): the official booking
pages a page links as buttons. Only addresses the data already holds, never an OTA, Naver, a blog or a social network;
each version opens the service's page in its language, else the Simplified Chinese / English one (labelled), else the
Korean one '(in Korean)'; a facility's own booking address by its domain with no language claimed. The words exist for
Korean and every version (locales.BOOK_WORDS) and the chat's cards use the same word (chat.js kinds.book).

This city has no booking.json yet (the registry is the operator's: each service needs the basis in our data that it is
where the booking is made): the city's checks say so — no registry button, only a place's own booking address — and
the engine is checked on a small registry over the sample data (REG below; its services and their pages are the
first site's, which the engine's words name). The first site's registry contents, place ids and guide ids stay in
that repository."""
import json
import re
import shutil
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
CITY = ROOT / "data" / "suwon"
SAMPLE = ROOT / "data" / "sample"
HANGUL = re.compile(r"[가-힣]")
# a small registry over the sample: the button order, a page per language where the service has one, a place's
# services, a guide named by a host it writes, an excluded host (OTA)
REG = {
    "services": {
        "bus": {"url": "https://www.bustago.or.kr/newweb/kr/index.do",
                "pages": {"en": "https://www.bustago.or.kr/newweb/en/index.do",
                          "ja": "https://www.bustago.or.kr/newweb/jp/index.do",
                          "zh-hans": "https://www.bustago.or.kr/newweb/cn/index.do"},
                "hosts": ["www.bustago.or.kr"], "basis": "시험: 가이드 본문의 버스타고", "checked_at": "2026-10-15"},
        "rail": {"url": "https://www.korail.com/", "hosts": ["www.korail.com"], "basis": "시험: 가이드 본문의 코레일",
                 "checked_at": "2026-10-15"},
        "ferry": {"url": "https://island.theksa.co.kr/page/booking?lang=",
                  "pages": {"en": "https://island.theksa.co.kr/page/booking?lang=en"},
                  "match": ["https://island.theksa.co.kr/"], "hosts": ["island.theksa.co.kr"],
                  "basis": "시험: 여객선 예매", "checked_at": "2026-10-15"},
    },
    "places": {"sample-0001": ["ferry"], "sample-0002": ["rail"]},
    "exclude_hosts": ["airbnb.com", "airbnb.co.kr", "yanolja.com", "goodchoice.kr", "yeogi.com", "agoda.com", "booking.com",
                      "map.naver.com", "booking.naver.com", "place.naver.com", "naver.me", "blog.naver.com",
                      "instagram.com", "facebook.com", "youtube.com"],
}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """The sample with REG as its booking.json, a guide that writes the bus and rail hosts, a course that stops at the
    ferry place and a place with its own booking address."""
    data = tmp_path_factory.mktemp("booking") / "data"
    shutil.copytree(SAMPLE, data)
    (data / "booking.json").write_text(json.dumps(REG, ensure_ascii=False), "utf-8")
    guides = json.loads((data / "guides.json").read_text("utf-8"))
    # the bus service as a cited source (url), the rail one as a host its text writes (present.OFFICIAL_WEB)
    guides[0]["summary"] = (guides[0].get("summary") or "") + " 기차표는 www.korail.com에서 예매합니다."
    guides[0].setdefault("sources", []).append({"title": "승차권 조회 — 버스타고",
                                                "url": "https://www.bustago.or.kr/newweb/kr/index.do"})
    (data / "guides.json").write_text(json.dumps(guides, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    by = {p["id"]: p for p in places}
    by["sample-0003"].setdefault("facts", {})["reservationurl"] = "https://www.samplehotel.kr/resv"
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    return data


@pytest.fixture(scope="module")
def S(world):
    return State(world, "sample")


def _ids(targets):
    return [t["key"] for t in targets]


# ------------------------------------------------------------------ the city's data
def test_the_city_has_no_registry_yet_and_only_own_booking_addresses():
    S = State(CITY, "preview")
    assert booking.data_problems(S) == []
    if (CITY / "booking.json").exists():      # once the operator writes one, the registry tests above apply to it
        return
    assert booking.registry(S) == {}
    for e in S.entities:
        assert all(t["key"] == booking.OWN for t in booking.place_targets(S, e)), e["id"]
    assert not any(booking.guide_targets(S, g) for g in S.guides)
    assert not any(booking.course_targets(S, c) for c in S.courses)


# ------------------------------------------------------------------ the registry and the words
def test_registry_services_have_address_basis_date_and_a_name_in_every_language(S):
    assert booking.data_problems(S) == []
    services = REG["services"]
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


def test_data_problems_name_a_wrong_registry(tmp_path):
    reg = {"services": {"rail": {"url": "https://www.airbnb.com/x", "basis": "", "checked_at": "2026-10-15",
                                 "pages": {"xx": "https://www.korail.com/xx"}},
                        "nameless": {"url": "https://example.kr/", "basis": "b", "checked_at": "2026-10-15"}},
           "places": {"no-such-place": ["rail", "spaceship"]}, "exclude_hosts": ["airbnb.com"]}
    text = "\n".join(booking.data_problems(SimpleNamespace(booking=reg, entities_all=[{"id": "sample-0001"}])))
    for needle in ("services.rail: basis 없음", "services.rail: pages에 이 사이트에 없는 언어 xx",
                   "services.rail: 버튼에서 빼는 호스트의 주소", "services.nameless: ko 이름(locales.BOOK_WORDS svc) 없음",
                   "places.no-such-place: places.json에 없는 장소", "places.no-such-place: 없는 서비스 spaceship"):
        assert needle in text, needle


def test_book_words_cover_every_version_hand_written():
    assert set(LC.BOOK_WORDS) == {"ko", *LC.ORDER}
    ko = LC.BOOK_WORDS["ko"]
    for code, w in LC.BOOK_WORDS.items():
        assert set(w) == set(ko) and set(w["svc"]) == set(ko["svc"]) >= set(REG["services"]), code
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


def test_official_entry_and_the_registry_pages_agree():
    """booking.OFFICIAL_ENTRY (cited booking sites' pages per language) and a registry's pages name the same pages."""
    for host, pages in booking.OFFICIAL_ENTRY.items():
        s = next(s for s in REG["services"].values() if host in (s.get("hosts") or []))
        assert s["pages"] == pages, host


# ------------------------------------------------------------------ targets
def test_place_targets(S):
    by = {e["id"]: e for e in S.entities}
    assert _ids(booking.place_targets(S, by["sample-0001"])) == ["ferry"]
    assert _ids(booking.place_targets(S, by["sample-0002"])) == ["rail"]
    own = booking.place_targets(S, by["sample-0003"])
    assert [(t["key"], t["url"]) for t in own] == [("reservationurl", "https://www.samplehotel.kr/resv")]
    with_buttons = [e for e in S.entities if booking.place_targets(S, e)]
    assert {e["id"] for e in with_buttons} == {"sample-0001", "sample-0002", "sample-0003"}


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
    got = {g["id"]: _ids(booking.guide_targets(S, g)) for g in S.guides if booking.guide_targets(S, g)}
    assert got == {"guide-sample-1": ["bus", "rail"]}                     # the hosts its text writes, registry order
    courses = {c["id"]: _ids(booking.course_targets(S, c)) for c in S.courses if booking.course_targets(S, c)}
    stops = {st.get("place_slug") for c in S.courses for st in c.get("stops") or []}
    ferry_slug = next(e["slug"] for e in S.entities if e["id"] == "sample-0001")
    if ferry_slug in stops:
        assert all("ferry" in keys for keys in courses.values())
    for c in S.courses:                                                   # a course box lists no hotel
        assert "reservationurl" not in _ids(booking.course_targets(S, c))


# ------------------------------------------------------------------ what each version shows
def test_view_picks_the_reader_s_language_page(S):
    g = booking.guide_targets(S, S.guide_by_id["guide-sample-1"]) + booking.place_targets(
        S, next(e for e in S.entities if e["id"] == "sample-0001"))
    ink = lambda n: f"{n} (KO)"  # noqa: E731
    ko = booking.view(g, "ko")
    assert [b["url"] for b in ko] == ["https://www.bustago.or.kr/newweb/kr/index.do", "https://www.korail.com/",
                                      "https://island.theksa.co.kr/page/booking?lang="]
    assert all(not b["hreflang"] and not b["note"] for b in ko) and ko[0]["name"] == LC.BOOK_WORDS["ko"]["svc"]["bus"]
    ja = {b["key"]: b for b in booking.view(g, "ja", ink)}
    assert ja["bus"]["url"].endswith("/newweb/jp/index.do") and ja["bus"]["hreflang"] == "ja" and not ja["bus"]["note"]
    assert ja["ferry"]["url"].endswith("?lang=en") and (ja["ferry"]["note"], ja["ferry"]["note_lang"]) == ("English", "en")
    zt = {b["key"]: b for b in booking.view(g, "zh-hant", ink)}
    assert zt["bus"]["url"].endswith("/newweb/cn/index.do") and zt["bus"]["hreflang"] == "zh-Hans"
    de = {b["key"]: b for b in booking.view(g, "de", ink)}
    assert de["bus"]["url"].endswith("/newweb/en/index.do") and de["bus"]["note"] == "English"
    assert de["rail"]["url"] == "https://www.korail.com/" and de["rail"]["hreflang"] == "ko"
    assert de["rail"]["name"] == f'{LC.BOOK_WORDS["de"]["svc"]["rail"]} (KO)'
    ru = {b["key"]: b for b in booking.view(g, "ru", ink)}
    assert ru["ferry"]["url"] == "https://island.theksa.co.kr/page/booking?lang=en"
    own = booking.view([{"key": "reservationurl", "url": "http://www.samplehotel.kr/view/index.do", "pages": {}}], "de", ink)
    assert own == [{"key": "reservationurl", "url": "http://www.samplehotel.kr/view/index.do", "hreflang": "",
                    "name": "samplehotel.kr", "note": "", "note_lang": ""}]


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
    rail = booking.view(booking.place_targets(S, next(e for e in S.entities if e["id"] == "sample-0002")), "ko")
    url = rail[0]["url"]
    assert booking_problems(S, _page(_a(url)), rail, "ko", allowed) == []
    # missing, extra (and not an address of the registry), an OTA host, a stray button on a page that has none
    assert len(booking_problems(S, _page(""), rail, "ko", allowed)) == 1
    extra = booking_problems(S, _page(_a(url) + _a("https://example.kr/resv")), rail, "ko", allowed)
    assert len(extra) == 2 and any("booking.json" in x for x in extra) and any("다른 예약 버튼" in x for x in extra)
    ota = booking_problems(S, _page(_a(url) + _a("https://www.airbnb.co.kr/rooms/1232259768400727594")), rail, "ko", allowed)
    assert any("OTA" in x for x in ota)
    assert len(booking_problems(S, _page(_a(url)), None, "ko", allowed)) == 1
    outside = PageScan()
    outside.feed(f'<html lang="ko"><body>{_a(url)}</body></html>')
    assert any("data-block" in x for x in booking_problems(S, outside, rail, "ko", allowed))
    # a version that opens the Korean ferry page although the registry has the English one
    ferry = booking.view(booking.place_targets(S, next(e for e in S.entities if e["id"] == "sample-0001")), "de",
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
