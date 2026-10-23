"""The guide reading layer (owner 2026-10-09: "guide pages are walls of prose — fine for AI, tiring for people").
Every sentence of a guide stays on its page, verbatim and in order (Korean and English); the layer only wraps spans
of the guide's own text: figures emphasised (present.rich), the guide's places linked once per section, the summary's
first sentence as the answer line with the summary still one run in the DOM, mini cards, the table of contents, the
FAQ as an accordion with every answer in the DOM. Also: a menu price is never cut at its thousands comma.
Built from gunsan_subset (its five guides: guide-02 has 'again' rows, guide-13 more places than PICKS_MAX) with
tests/fixtures/en_min laid over it (the English guide-13); guides are looked up by id."""
import html as htmlmod
import re
import shutil
from pathlib import Path

import pytest

from pipeline import en_site, present
from pipeline.build import State, build
from pipeline.textutil import squash_ws
from pipeline.validate import PageScan
from tests.fixtures.build_en_min import overlay

ROOT = Path(__file__).resolve().parent.parent
SUBSET = ROOT / "tests" / "fixtures" / "gunsan_subset"
KIDS = "guide-02"     # 아이와 함께: sections with 'again' rows
HUB = "guide-13"      # the food hub: 13 places on its list (more than PICKS_MAX)
BLOCK_END = re.compile(r"</(?:li|p|h[1-6]|dt|dd|div|section|summary|details|ol|ul|nav|header|figure|figcaption|td|th)>|<br\s*/?>")


def text_of(markup: str) -> str:
    """What a reader sees: inline tags join their text without a space (unlike PageScan), block ends separate it."""
    t = BLOCK_END.sub(" ", str(markup))
    t = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", t, flags=re.S)
    return squash_ws(htmlmod.unescape(re.sub(r"<[^>]+>", "", t)))


@pytest.fixture(scope="module")
def DATA(tmp_path_factory):
    data = tmp_path_factory.mktemp("guides_data") / "data"
    shutil.copytree(SUBSET, data)
    overlay(data)
    return data


@pytest.fixture(scope="module")
def S(DATA):
    return State(DATA, "preview")


@pytest.fixture(scope="module")
def built(DATA, tmp_path_factory):
    out = tmp_path_factory.mktemp("guides") / "preview"
    build(DATA, out, "preview")
    return out


def test_rich_keeps_every_character_and_marks_only_figures():
    names = [{"name": "근대역사박물관", "path": "/places/a/", "id": "p1"}, {"name": "채만식 문학관", "path": "/places/b/", "id": "p2"}]
    t = ("근대역사박물관 1층에는 126㎡ 넓이의 어린이박물관이 있고, 어린이 500원·통합권 1,000원이며 10:00~19:00에 열고 "
         "매주 월요일과 월·화요일에 쉬며 01·18·19번과 11~19·61번 버스가 서고 2시간30분 걸립니다(문의 063-443-3077).")
    seen: set = set()
    h = present.rich(t, "ko", names, seen)
    assert text_of(h) == t
    assert h.count('class="gl"') == 1 and 'href="/places/a/"' in h and seen == {"p1"}
    figs = re.findall(r'class="gk"[^>]*>([^<]+)</b>', h)
    assert figs == ["126㎡", "500원", "1,000원", "10:00~19:00", "월요일", "월·화요일", "01·18·19번", "11~19·61번", "2시간30분"]
    assert 'href="tel:0634433077"' in h
    # a long run of route numbers may break after each dot (it has no break opportunity of its own)
    long = present.rich("309·403·609·649·990·991번이 섭니다.", "ko")
    assert '<b class="gk">309·<wbr>403·<wbr>609·<wbr>649·<wbr>990·<wbr>991번</b>' in long
    assert text_of(long) == "309·403·609·649·990·991번이 섭니다."
    # a place already linked in this section is not linked again (and never emphasised inside)
    again = present.rich("근대역사박물관·채만식 문학관", "ko", names, seen)
    assert again.count('class="gl"') == 1 and 'href="/places/b/"' in again
    # dates, years, floors, titles and phone digits are not figures
    for plain in ("2026-10-08 조회", "「8월의 크리스마스」(1998)", "3층 전시관", "2024.10.21 시행", "4200t급", "LJ463"):
        assert 'class="gk"' not in present.rich(plain), plain
    # skip: no markup starts inside the first characters (the validator compares them as one run)
    h = present.rich("이 사이트에 실린 군산 숙소 89곳의 정보에는 객실 25실", skip=present.PLAIN_HEAD)
    assert re.findall(r'class="gk"[^>]*>([^<]+)', h) == ["25실"]


def test_rich_links_the_official_hosts_the_guide_writes():
    """QA 2026-10-15 SRC-05b: a host of present.OFFICIAL_WEB written in the guide's text is a link — the Korean page to
    the checked page, the other versions to the site's English page where it has one, a written path kept — and the
    text stays character for character. Unlisted or unchecked hosts stay text."""
    t = "여객선 예매는 한국해운조합(island.theksa.co.kr)에서, 열차는 한국철도공사(www.korail.com, 1544-7788)에서 봅니다."
    ko, en = present.rich(t, "ko"), present.rich(t, "en")
    assert text_of(ko) == t and text_of(en) == t
    assert '<a class="xl" href="https://island.theksa.co.kr/" rel="noopener" data-track="official_click">island.theksa.co.kr</a>' in ko
    assert 'href="https://island.theksa.co.kr/page/booking?lang=en"' in en and 'href="https://www.korail.com/"' in en
    assert 'href="tel:15447788"' in en                              # a nationwide number keeps its digits
    h = present.rich("시간표는 www.korail.com/ticket/search에서 봅니다.", "ko")   # a written path is kept
    assert '<a class="xl" href="https://www.korail.com/ticket/search" rel="noopener" data-track="official_click">' in h
    h = present.rich("군산 날씨는 kma.go.kr에서 봅니다.", "ko")
    assert re.findall(r'<a class="xl"[^>]*>([^<]+)</a>', h) == ["kma.go.kr"]
    # a facility's own site is no engine host (the first city's camp site, airline and race were its own data)
    for plain in ("군산시 축제정보에 적힌 gsmg-marathon.com은 열리지 않았습니다.", "홈페이지 주소는 funvillage.kr입니다.",
                  "예약은 홈페이지 실시간 예약(mndcamp.com/resv)이나 전화로 합니다.",
                  "xwww.korail.com", "전체 시각은 코버스(www.kobus.co.kr)에서 조회합니다."):
        assert "<a " not in present.rich(plain, "ko"), plain
    # never inside the answer line's plain head (the validator compares it with the JSON-LD as one run)
    h = present.rich("예매는 island.theksa.co.kr에서 합니다.", "ko", skip=present.PLAIN_HEAD)
    assert 'class="xl"' not in h
    # English figures
    t = "About 500 m away; 1,000 won; 10:00–19:00 on Mondays; ages 6 and under; from 18 months; 16 pieces; 2 hours 30 minutes."
    h = present.rich(t, "en")
    assert text_of(h) == t
    assert re.findall(r'class="gk"[^>]*>([^<]+)</b>', h) == ["500 m", "1,000 won", "10:00–19:00", "Mondays", "ages 6 and under",
                                                              "18 months", "16 pieces", "2 hours 30 minutes"]
    # the roll-in hook: every figure with digits (its own digits roll; a weekday has none), only when asked, never
    # [data-roll] (the home story's year)
    h = present.rich("16대 · 1.5km · 20,900원 · 10:00~19:00 · 7~12세 · 월요일", roll=True)
    assert re.findall(r'<b class="gk" data-numroll>([^<]+)', h) == ["16대", "1.5km", "20,900원", "10:00~19:00", "7~12세"]
    assert 'data-numroll' in present.rich("16 pieces", "en", roll=True) and 'data-numroll' not in present.rich("Mondays", "en", roll=True)
    assert 'data-numroll' not in present.rich("16대") and "data-roll" not in h.replace("data-numroll", "")


def test_menu_price_is_never_cut_at_its_thousands_comma():
    b = present.brief_menu("한우떡갈비(200g)24,000원, 돼지떡갈비(200g)11,000원")
    assert b["main"] == "한우떡갈비(200g)24,000원" and b["more"]
    assert en_site.brief_en("menu", "Hanwoo tteokgalbi (200 g) 24,000 won, pork tteokgalbi 11,000 won")["main"].endswith("24,000 won")


def _guide_pages(S, built, DATA):
    """(page html, summary as shown, [(heading, [paragraph as shown])], faqs, lang) for every Korean and English guide."""
    out = []
    for g in S.guides:
        page = (built / "guides" / g["slug"] / "index.html").read_text("utf-8")
        body = [(squash_ws(b.get("heading")), [present.decaution(squash_ws(p)) for p in str(b.get("text") or "").split("\n")
                                               if p.strip()]) for b in g.get("body") or []]
        faqs = [present.decaution(squash_ws(f["a"])) for f in g.get("faq") or [] if f.get("q") and f.get("a")]
        out.append((page, present.decaution(g.get("summary")), body, faqs, "ko"))
    en = en_site.load(S, DATA)
    for x in en.guides.values():
        rec = x["rec"]
        page = (built / x["path"].strip("/") / "index.html").read_text("utf-8")
        body = [(squash_ws(b.get("heading")), [squash_ws(p) for p in str(b.get("text") or "").split("\n") if p.strip()])
                for b in rec.get("body") or []]
        out.append((page, squash_ws(rec.get("summary")), body, [squash_ws(f["a"]) for f in rec.get("faq") or []], "en"))
    return out


def test_every_guide_sentence_is_on_its_page_verbatim_and_in_order(S, built, DATA):
    pages = _guide_pages(S, built, DATA)
    assert [lang for *_, lang in pages] == ["ko"] * 5 + ["en"]      # gunsan_subset's 5 guides, en_min's 1
    for page, summary, body, faqs, lang in pages:
        main = page[page.index("<main"):]
        text = text_of(main)
        # the answer card keeps the summary as one run (answer line, then the rest; the cards come after in the DOM)
        assert summary in text, summary[:40]
        scan = PageScan()
        scan.feed(page)
        assert squash_ws(summary)[:present.PLAIN_HEAD] in scan.visible
        pos = text.index(summary) + len(summary)
        split = en_site.sentences_en if lang == "en" else present.ko_sentences
        for head, paras in body:
            pos = text.index(head, pos) + len(head)
            for p in paras:
                for s in split(p):
                    pos = text.index(s, pos) + len(s)     # every sentence, in order
        for a in faqs:
            assert a in text and a[:present.PLAIN_HEAD] in scan.visible


def test_answer_card_toc_sections_and_faq_markup(S, built):
    g = S.guide_by_id[KIDS]
    G = present.guide_vm(S, g)
    page = (built / "guides" / g["slug"] / "index.html").read_text("utf-8")
    start = page.index('<div class="gd-ans">')
    head = page[start:page.index("</header>", start)]
    # answer line first, then the rest of the summary, then the mini cards (CSS order shows the cards second)
    assert head.index('class="lede gd-ans-l') < head.index('class="dek gd-ans-r"') < head.index('class="gd-picks"')
    assert head.count('<li class="mc') == len(G["picks"]) == len({it["t"]["slug"] for it in G["places"] if it["t"]})
    assert "사진 출처: 한국관광공사" in head
    # mini card chips: settled values only, at most two, never a value two sources give differently
    for c in G["picks"]:
        assert len(c["chips"]) <= 2 and not any(s.get("conflict") or s.get("missing") for s in c["chips"])
    # one table of contents entry per section, linked to its heading
    assert page.count("data-toc-link=") == len(G["sections"]) == len(g["body"])
    for s in G["sections"]:
        assert f'href="#{s["id"]}"' in page and f'<h2 id="{s["id"]}"' in page
    # sentence bullets carry the section's place links and figure marks
    assert '<ul class="gd-pts">' in page and 'class="gl"' in page and 'class="gk"' in page
    # the FAQ: an accordion, the first answer open, every answer in the DOM
    faq = page[page.index('<div class="faq faq-acc">') + len('<div class="faq faq-acc">'):]
    assert faq.count('<details class="qa"') == len(G["faqs"]) and faq.startswith('<details class="qa" open>')
    assert faq.count(" open>") == 1
    for f in G["faqs"]:
        assert present.decaution(squash_ws(f["a"])) in text_of(faq)
    # the map knows each place by id, so it can follow the section being read
    assert all(p.get("id") for p in G["points"])
    assert all(set(s["pts"]) <= {p["id"] for p in G["points"]} for s in G["sections"])


def test_hub_answer_card_shows_a_dozen_places_and_points_to_the_rest(S, built):
    """A hub guide (13 places here) shows the places its summary names first, at most PICKS_MAX, then a tile to the
    full list; every icon a mini card on the page uses is in the page's sprite."""
    g = S.guide_by_id[HUB]
    G = present.guide_vm(S, g)
    total = len({it["t"]["slug"] for it in G["places"] if it["t"]})
    assert total == 13 > present.PICKS_MAX and len(G["picks"]) == present.PICKS_MAX
    assert G["picks_total"] == total and G["picks_more"] == total - present.PICKS_MAX
    named = [n["id"] for n in present.mentions(present.decaution(g["summary"]),
                                                [{"name": c["name"], "id": c["id"]} for c in G["picks"]])]
    assert [c["id"] for c in G["picks"][:len(named)]] == named      # the summary's places lead
    page = (built / "guides" / g["slug"] / "index.html").read_text("utf-8")
    start = page.index('<div class="gd-ans">')
    head = page[start:page.index("</header>", start)]
    assert len(re.findall(r'<li class="mc(?: mc-ic)?">', head)) == present.PICKS_MAX
    assert head.count('<li class="mcs-more">') == 1 and f"외 {G['picks_more']}곳" in head
    assert f'이 가이드의 장소 <b class="tn">{total}</b>곳' in head
    for page in [page] + [(built / "guides" / x["slug"] / "index.html").read_text("utf-8") for x in S.guides]:
        used = set(re.findall(r'<use href="#gi-([\w-]+)"', page))
        drawn = set(re.findall(r'<symbol id="gi-([\w-]+)"', page))
        assert used <= drawn, used - drawn


def test_one_place_count_and_one_card_per_place(DATA):
    """Review 2026-10-09: the answer card counts the rows of the place list (a place without a published page is a row
    there but has no card; the '외 n곳' tile names the rest), and a place gets its whole mini card once per page — the
    answer card or the first section that names it; a later section shows it as a one-line row (again)."""
    S = State(DATA, "production")
    for g in S.guides:
        G = present.guide_vm(S, g)
        assert G["picks_total"] == len(G["places"])
        assert G["picks_more"] == len(G["places"]) - len(G["picks"])
        full = [c["id"] for c in G["picks"]] + [c["id"] for s in G["sections"] for c in s["places"]]
        assert len(full) == len(set(full)), g["slug"]
        for s in G["sections"]:
            assert not {c["id"] for c in s["places"]} & {c["id"] for c in s["again"]}
            assert set(s["pts"]) == {c["slug"] for c in s["places"] + s["again"] if c["geo"]}


def test_again_rows_and_english_bullets(S, built):
    g = S.guide_by_id[KIDS]
    G = present.guide_vm(S, g)
    assert any(s["again"] for s in G["sections"])
    page = (built / "guides" / g["slug"] / "index.html").read_text("utf-8")
    body = page[page.index('<div class="gd-body">'):page.index('<aside class="gd-map"')]
    for s in G["sections"]:
        for c in s["again"]:
            assert f'data-place="{c["id"]}">{c["name"]}</a>' in body
        assert set(s["pts"]) == {c["slug"] for c in s["places"] + s["again"] if c["geo"]}
    assert body.count('<ul class="mcr"') == sum(1 for s in G["sections"] if s["again"])
    # English: a sentence that leans on the one before it stays in that bullet; the text is unchanged
    t = "The museum has a children's floor. It opens at 09:00. There is an elevator. Bring a stroller."
    pts = present.points_list(t, en_site.sentences_en, "en")
    assert pts == ["The museum has a children's floor. It opens at 09:00. There is an elevator.", "Bring a stroller."]
    assert " ".join(pts) == t and present.points_list(t, en_site.sentences_en, "ko") == en_site.sentences_en(t)


def test_english_figures_match_the_korean_units():
    """The English figures of the Korean units 곳 / 번 / 세 이하; tonnage and '1박 2일' stay plain in both languages."""
    t = ("The site lists 89 lodgings (56 inns and motels); take city bus 11, 12 or 19, then bus 99; children 6 and under "
         "are free; a 4,200-ton ship; 1-night, 2-day courses.")
    h = present.rich(t, "en")
    assert text_of(h) == t
    assert re.findall(r'class="gk"[^>]*>([^<]+)</b>', h) == ["89 lodgings", "56 inns", "bus 11, 12 or 19", "bus 99",
                                                              "6 and under"]
    # an age in months is the months figure, not 'ages 18' cut off from its unit
    h = present.rich("Activities are open to ages 18 months through adults; ages 7–12 pay 1,000 won.", "en")
    assert re.findall(r'class="gk"[^>]*>([^<]+)</b>', h) == ["18 months", "ages 7–12", "1,000 won"]
