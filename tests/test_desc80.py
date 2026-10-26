"""Korean meta descriptions within 80 characters (owner 2026-10-14, Naver Search Advisor '80자 이내로 설명문을
작성해주세요'): whole sentences or one fact line from the page's own data, answer first, never cut, never '…'."""
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.build import (DESC_MAX, answer_description, build, event_description, fit_sentences, guide_description,
                            place_head, place_summary)
from pipeline.validate import scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DATA = ROOT / "data" / "suwon"
INTL = ("en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")


def row(key, label, value, *alts):
    """A key row as build.fact_row returns it; alts: (value, also) pairs from other sources."""
    return {"key": key, "label": label, "value": value, "source": {},
            "alternatives": [{"value": v, "also": also, "provider": "다른 출처", "checked_at": ""} for v, also in alts]}


def korean_pages(out: Path):
    for f in sorted(out.rglob("*.html")):
        rel = f.relative_to(out).parts
        if rel[0] in INTL or rel[0] == "assets":
            continue
        yield f


# ---------------------------------------------------------------- sentences are never cut
def test_fit_sentences_takes_whole_sentences_only():
    first = "은파호수공원은 물빛다리와 음악분수가 있는 호수공원입니다."
    second = "벚꽃산책로는 호수 둘레를 따라 이어지고 봄에는 야시장이 열리며 주차장은 무료로 쓸 수 있습니다."
    assert fit_sentences(f"{first} {second}", 80) == first             # the second would pass 80: left out whole
    assert fit_sentences(f"{first} 주차는 무료입니다.", 80) == f"{first} 주차는 무료입니다."
    assert fit_sentences(f"{first} {second}", 20) == ""                 # the first alone is longer: nothing, not a cut


def test_place_first_sentence_kept_and_facts_added_only_within_80():
    first = "근대건축관은 1922년에 지은 옛 조선은행 군산지점 건물로, 2층 전시실에 근대 건축 자료를 둡니다."   # 56
    rows = [row("usetime", "이용시간", "09:00~18:00"),
            row("restdate", "쉬는 날", "매주 월요일", ("연중무휴", False)),          # contradicted: never in it
            row("usefee", "이용요금", "성인 500원"),
            row("parkingfee", "주차요금", "무료")]
    out = answer_description(f"{first} 두 번째 문장은 들어가지 않습니다.", "", rows, head="근대건축관: 장미동 관광지")
    # 56 ≥ 40: no second sentence; the first fact fits (75), the next two would pass 80 (90, 85): left out whole
    assert out == f"{first} 이용시간: 09:00–18:00."                       # the value as the page shows it
    assert len(f"{first} 이용시간: 09:00–18:00. 주차요금: 무료.") > DESC_MAX
    assert "매주 월요일" not in out and "연중무휴" not in out and "…" not in out
    # with room, up to three facts (the first site's Search Console 2026-10-22: a short snippet takes the page's facts
    # while it stays within 80)
    out = answer_description("근대건축관은 옛 조선은행 군산지점 건물입니다. 두 번째 문장은 아주 길어서 이 설명에 들어갈 자리가 없으므로 "
                             "사실 값이 뒤에 붙고 이 문장은 통째로 빠집니다.", "", rows)
    assert out == "근대건축관은 옛 조선은행 군산지점 건물입니다. 이용시간: 09:00–18:00. 이용요금: 성인 500원. 주차요금: 무료."
    assert len(out) <= DESC_MAX


def test_a_fact_the_summary_already_says_is_not_repeated():
    rows = [row("parking_seats", "주차·좌석", "100대/160석"), row("usefee", "이용요금", "무료"),
            row("restdate", "쉬는 날", "연중 무휴"), row("usetime", "이용시간", "10:00~18:00"),
            row("parking", "주차", "불가"), row("menu", "대표 메뉴", "아나고탕")]
    # every figure ('좌석 160석, 주차 100대'), every word, or the summary's own wording ('요금 없이', '쉬는 날도 없')
    said = "계명수산은 좌석 160석, 주차 100대 규모로 아나고탕을 내며, 요금 없이 10:00~18:00에 열고 쉬는 날도 없습니다."
    assert answer_description(said, "", rows[:4] + rows[5:]) == said
    # 주차 불가 said in words: left out; a value the summary does not say is still added
    out = answer_description("이성당은 단팥빵을 팔며, 주차는 할 수 없습니다.", "", rows[4:] + [row("restdate", "쉬는 날", "매주 월요일")])
    assert out == "이성당은 단팥빵을 팔며, 주차는 할 수 없습니다. 대표 메뉴: 아나고탕. 쉬는 날: 매주 월요일."


def test_short_place_sentence_takes_the_phone_while_under_40():
    rows = [row("infocenter", "문의", "063-454-3852")]
    out = answer_description("군산요는 임피면에 있는 도자기 체험 시설입니다. " + "가" * 70 + "입니다.", "", [],
                             head="군산요: 임피면 체험 관광지", extra_rows=rows)
    assert out == "군산요는 임피면에 있는 도자기 체험 시설입니다. 전화: 063-454-3852."


def test_long_first_sentence_becomes_the_place_fact_line():
    e = {"name": "어시장활어회직거래판매장", "kind": "food", "_type": "일식", "_area": "수송동"}
    summary = ("어시장활어회직거래판매장은 킹크랩·생선회·생선탕을 대표 메뉴로 내는 수송동의 일식 음식점으로, "
               "좌석 200석과 30대 규모의 주차 공간을 갖췄습니다. 영업시간은 10:00~23:00이며 명절 당일에는 쉽니다.")
    rows = [row("usetime_restdate", "영업시간·정기휴일", "10:00 ~ 23:00 / 명절당일 휴무"),
            row("parking_seats", "주차·좌석", "30대/200석"),
            row("menu", "대표 메뉴", "킹크랩, 생선회,생선탕")]
    out = answer_description(summary, "", rows, head=place_head(e), extra_rows=[row("infocenter", "문의", "063-471-8844")])
    assert out == "어시장활어회직거래판매장: 수송동 일식 음식점, 영업시간·정기휴일 10:00–23:00 / 명절당일 휴무, 주차·좌석 30대/200석."
    assert len(out) <= DESC_MAX and "…" not in out
    stay = {"name": "탑클라우드호텔 군산점", "kind": "stay", "_type": "호텔", "_area": "경장동"}
    assert place_head(stay) == "탑클라우드호텔 군산점: 경장동 호텔"         # a stay's type is the kind of lodging
    assert place_head({"name": "음미당", "kind": "food", "_type": "", "_area": ""}) == "음미당: 음식점"
    # a conflicting value is not on the line; a value over 30 characters stays on the page only
    out = answer_description("가" * 90 + "입니다.", "", [row("usetime", "이용시간", "09:00~18:00", ("10:00~17:00", False)),
                                                    row("restdate", "쉬는 날", "매주 월요일, 1월 1일, 설날·추석 당일, 시장이 정한 날")],
                             head="근대역사박물관: 박물관·전시 관광지")
    assert out == "근대역사박물관: 박물관·전시 관광지."
    # a line still under 40 takes the summary's next whole sentence while it fits
    out = answer_description("가" * 90 + "입니다. 군산시청까지는 차로 2분 걸립니다.", "", [], head=place_head(stay),
                             extra_rows=[row("infocenter", "문의", "063-452-4404")])
    assert out == "탑클라우드호텔 군산점: 경장동 호텔, 전화 063-452-4404. 군산시청까지는 차로 2분 걸립니다."


# ---------------------------------------------------------------- events: the dates stay exact
EVENT = {"_title": "2026 군산 국가유산 야행(제11회)", "start_date": "2026-08-14", "end_date": "2026-08-22",
         "place_name": "원도심 국가유산 5곳: 구 조선식량영단, 구 남조선전기주식회사, 군산 신흥동 일본식 가옥, 해망굴, 구 군산세관 본관 일원"}


def test_event_answer_line_kept_when_it_fits():
    ev = {"_title": "2026 군산시간여행축제", "start_date": "2026-10-02", "end_date": "2026-10-05",
          "place_name": "구·시청광장 및 시간여행마을 일원", "fee": "무료 (일부 유료)"}
    assert event_description(ev) == ("2026 군산시간여행축제 기간: 2026년 10월 2일(금)~10월 5일(월) · 장소: "
                                     "구·시청광장 및 시간여행마을 일원.")   # with the fee it would be 85: left out whole
    ev["fee"] = "무료"
    assert event_description(ev).endswith(" 요금: 무료.")


def test_event_long_place_becomes_first_place_and_dates_stay_exact():
    out = event_description(EVENT, "군산 국가유산 야행")
    assert out == "2026 군산 국가유산 야행(제11회) 2026년 8월 14일(금)~8월 22일(토), 원도심 국가유산 5곳 일원."
    assert len(out) <= DESC_MAX and "…" not in out
    assert place_summary("군산3·1운동100주년기념관 일원(구암교회 출발, 시내 중심가 행진)") == \
        ("군산3·1운동100주년기념관 일원", "군산3·1운동100주년기념관 일원")   # '·' is not a list separator
    assert place_summary("군산회관, 군산항1981") == ("군산회관, 군산항1981", "군산회관 일원")
    # a title that leaves no room for a place: the whole period alone, never a cut date
    ev = {**EVENT, "_title": "2026 국가유산 미디어아트 구 군산세관 본관 등 '빛을 품은 군산번화구경(群山繁花九景)'",
          "start_date": "2026-08-28", "end_date": "2026-09-20"}
    out = event_description(ev, "국가유산 미디어아트")
    assert out == "2026 국가유산 미디어아트 구 군산세관 본관 등 '빛을 품은 군산번화구경(群山繁花九景)' 2026년 8월 28일(금)~9월 20일(일)."
    # still too long: the series name the breadcrumb shows, with the same whole period
    ev["_title"] = "가" * 70
    assert event_description(ev, "국가유산 미디어아트") == "국가유산 미디어아트 2026년 8월 28일(금)~9월 20일(일)."
    month = {**EVENT, "end_date": "", "end_month": "2026-10", "place_name": ""}
    assert event_description(month) == "2026 군산 국가유산 야행(제11회) 기간: 2026년 8월 14일(금)~10월."


# ---------------------------------------------------------------- guides: the title-level answer, never a cut sentence
LONG = "군산 고기집은 " + "한우·삼겹살·갈비·곱창·오리숯불구이·떡갈비를 대표 메뉴로 내는 곳이 23곳이고, " * 2 + "15곳입니다."


def guide(**kw):
    g = {"id": "guide-test", "label": "고기집", "title": "군산 고기집 — 한우·삼겹살·갈비·곱창 15곳의 대표 메뉴, 닫는 시간, 주차",
         "summary": f"{LONG} 둘째 문장입니다.", "body": [], "items": []}
    g.update(kw)
    return g


S = SimpleNamespace(ent_by_slug={}, warnings=[], lists={"attraction": [], "food": [], "stay": []})


def test_guide_keeps_its_first_sentence_when_it_fits():
    assert guide_description(guide(summary="군산 고기집은 15곳입니다. 둘째 문장입니다."), S) == "군산 고기집은 15곳입니다."


def test_guide_long_summary_takes_its_first_heading_with_a_figure():
    g = guide(body=[{"heading": "군산 고기집 15곳 가운데 6곳은 23:00이나 그보다 늦게 닫습니다", "text": "6곳입니다."},
                    {"heading": LONG, "text": ""}])                      # the next heading would pass 80: not added
    assert guide_description(g, S) == "군산 고기집 15곳 가운데 6곳은 23:00이나 그보다 늦게 닫습니다."
    # a first heading without a figure is a topic: the guide's own short answer comes first, when its figures are
    # written on the page
    topic = guide(body=[{"heading": "작품별 촬영지: 어느 작품을 어디서 찍었나",
                         "text": "「8월의 크리스마스」는 초원사진관에서 찍었고, 영화 속 군산 코스는 9곳입니다."}],
                  answer={"answer": "「8월의 크리스마스」는 초원사진관 · 영화 속 군산 코스는 9곳"})
    assert guide_description(topic, S) == "「8월의 크리스마스」는 초원사진관 · 영화 속 군산 코스는 9곳."
    topic["answer"]["answer"] = "영화 속 군산 코스는 12곳"                   # 12 is not on the page: not used
    assert guide_description(topic, S) == "군산 고기집: 한우·삼겹살·갈비·곱창 15곳의 대표 메뉴, 닫는 시간, 주차."
    short = guide(body=[{"heading": "월요일에는 전시관 여덟 곳이 쉽니다", "text": ""},
                        {"heading": "월요일에 여는 실내: 테디베어박물관·군산항1981", "text": ""}])
    assert guide_description(short, S) == "월요일에는 전시관 여덟 곳이 쉽니다. 월요일에 여는 실내: 테디베어박물관·군산항1981."


def test_guide_title_line_then_count_line():
    long_head = [{"heading": LONG, "text": ""}]
    assert guide_description(guide(body=long_head), S) == \
        "군산 고기집: 한우·삼겹살·갈비·곱창 15곳의 대표 메뉴, 닫는 시간, 주차."
    names = ["우민회관", "마루벌돌구이군산점", "군산한우촌", "한우진대가", "선현대솥뚜껑갈비", "안동집", "신자네연탄구이",
             "토실배기", "삼풍식당", "명월갈비", "원풍갈비", "산마루", "명인", "또또생곱창", "순돌이곱창"]
    g = guide(title="군산 고기집, 어디가 늦게까지 열까?", body=long_head, items=[{"name": n} for n in names])
    out = guide_description(g, S)
    assert out.startswith("고기집: 우민회관·마루벌돌구이군산점·") and out.endswith(" 등 15곳.") and len(out) <= DESC_MAX
    for g in (guide(body=long_head), g):
        assert "…" not in guide_description(g, S)


# ---------------------------------------------------------------- build level
def long_sample(tmp_path: Path) -> Path:
    """The bundled sample with a place, an event and a guide whose first sentences are over 80 characters."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["summary"] = ("경암동 철길마을은 1944년 신문 용지 공장으로 원료를 실어 나르던 철로를 따라 생긴 마을로, 지금은 교복 대여점과 "
                            "추억의 과자 가게가 철길 양쪽에 늘어서 있어 사진을 찍으러 오는 사람이 많습니다. 철길은 상시 개방합니다.")
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    events = json.loads((data / "events.json").read_text("utf-8"))
    events[0]["place_name"] = "군산 내항 일원(개막식: 군산항1981 여객터미널 옥상), 구 군산세관 본관~내항 역사문화공간(내항철로)"
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    guides = json.loads((data / "guides.json").read_text("utf-8"))
    guides[0]["summary"] = f"{LONG} 둘째 문장입니다."
    (data / "guides.json").write_text(json.dumps(guides, ensure_ascii=False), "utf-8")
    return data


def test_no_korean_page_description_over_80_and_the_validator_warns(tmp_path):
    data, out = long_sample(tmp_path), tmp_path / "s"
    build(data, out, "sample")
    for f in korean_pages(out):
        p = scan_file(f)
        desc = p.meta.get("description", "")
        assert len(desc) <= DESC_MAX and not desc.endswith("…"), (f, desc)
        assert p.meta.get("og:description", "") == desc and len(p.meta.get("twitter:description", "")) <= DESC_MAX
    gy = scan_file(out / "places/gyeongam-railroad-village/index.html").meta["description"]
    assert gy.startswith("경암동 철길마을: ") and gy.endswith(".")      # the fact line, not a cut sentence
    errors, warns, _ = validate(data, out, "sample")
    assert errors == [] and not [w for w in warns if "80자 이내" in w], warns
    # a description over 80 on a Korean page is caught (og:description too); the English pages keep their own rule
    page = out / "places/gyeongam-railroad-village/index.html"
    html = re.sub(r'(<meta (?:name="description"|property="og:description") content=")[^"]*"', r'\g<1>' + "가" * 81 + '"',
                  page.read_text("utf-8"))
    page.write_text(html, "utf-8")
    _, warns, _ = validate(data, out, "sample")
    hits = [w for w in warns if "80자 이내" in w and "gyeongam-railroad-village" in w]
    assert len(hits) == 2 and any("og:description 81자" in w for w in hits), warns


@pytest.fixture(scope="module")
def public(tmp_path_factory):
    out = tmp_path_factory.mktemp("desc80") / "prod"
    build(DATA, out, "production")
    return out


def test_every_korean_page_of_the_public_build_fits_in_80(public):
    n = 0
    for f in korean_pages(public):
        p = scan_file(f)      # attribute values unescaped: len() counts the text a reader sees
        if not p.html_lang.startswith("ko"):
            continue
        n += 1
        for key in ("description", "og:description", "twitter:description"):
            text = p.meta.get(key, "")
            assert len(text) <= DESC_MAX, (f, key, len(text), text)
            assert "…" not in text, (f, text)
        assert p.meta.get("og:description", "") == p.meta.get("description", "")
    published = sum(1 for x in json.loads((DATA / "places.json").read_text("utf-8")) if x.get("status") == "published")
    assert published > 100 and n > published     # every published place's page, and the lists, guides, courses


def test_food_title_says_hours_and_dish_first():
    """The first site's Search Console 2026-10-22: a restaurant's title names 영업시간, then its dish, then the closed
    day; the other kinds keep the key-row order and 이용시간."""
    from pipeline.build import title_keys, title_label
    keys = ["usetime", "restdate", "parking", "menu"]
    assert [title_label("food", k) for k in title_keys("food", keys)][:3] == ["영업시간", "메뉴", "쉬는 날"]
    assert [title_label("attraction", k) for k in title_keys("attraction", keys)][:3] == ["이용시간", "쉬는 날", "주차"]


def test_short_description_takes_the_phone_then_the_next_sentence():
    first = "월명공원은 시내 한가운데 있는 산책 공원으로 수시탑까지 숲길이 이어집니다."
    nxt = "봄에는 벚꽃이 핍니다."
    assert 40 <= len(first) and len(f"{first} 전화: 063-454-3337.") < 60     # ≥ DESC_SHORT, still under DESC_FILL
    phone = [row("infocenter", "문의", "063-454-3337")]
    out = answer_description(f"{first} {nxt}", "", [], extra_rows=phone)
    assert out == f"{first} 전화: 063-454-3337. {nxt}" and len(out) <= DESC_MAX
    # without a phone the next sentence alone fills it
    assert answer_description(f"{first} {nxt}", "", []) == f"{first} {nxt}"


def test_intl_description_joins_a_short_listed_value():
    from pipeline.en_site import answer_description as en_desc
    rows = [{"key": "usetime", "label": "Hours", "text": "- 11:10–22:00\n- Break 15:00–17:00", "conflict": False}]
    out = en_desc("Ojuk is a restaurant on Hanbat-ro in Naun-dong.", rows, 160)
    assert out == "Ojuk is a restaurant on Hanbat-ro in Naun-dong. Hours: 11:10–22:00; Break 15:00–17:00."


def test_intl_long_first_sentence_keeps_its_longest_fitting_clauses():
    """'Urimil, in Seosu-myeon, has …' became 'Urimil.' (first clause only): the longest run of whole clauses within
    the limit is kept instead."""
    from pipeline.en_site import answer_description as en_desc
    long = ("Urimil, in Seosu-myeon, has a dining hall for groups of up to 120 people, a garden with a pond and "
            "a farm shop that sells the rice and soybean paste it makes, and it opens for lunch on weekdays only.")
    out = en_desc(long, [], 160)
    assert out == ("Urimil, in Seosu-myeon, has a dining hall for groups of up to 120 people, a garden with a pond and "
                   "a farm shop that sells the rice and soybean paste it makes.")
    assert len(out) <= 160


def test_guide_article_is_part_of_the_site():
    """A guide's Article names the site it belongs to (the first site's 7d022f47f): isPartOf the WebSite node the home
    page states, by its @id and name."""
    from pipeline.jsonld import guide_graph
    site = {"site_name": "한빛각", "brand": {}, "operator": {}}
    g = guide_graph({"title": "가이드", "summary": "요약입니다."}, "https://x.test", "https://x.test/guides/a/",
                    [("홈", "https://x.test/")], [], [], site=site)
    art = next(n for n in g["@graph"] if n.get("@type") == "Article")
    assert art["isPartOf"] == {"@type": "WebSite", "@id": "https://x.test/#website", "name": "한빛각"}
def test_search_script_on_the_public_build_finds_every_row_it_found_before_the_query_words(public):
    """tests/js/search.test.js on this build's search pages and indexes (every version; ported from the first site's
    review round 3, 2026-10-18): the rows found for every name, menu item, area, guide-title word and the review's
    queries include every row the script before the query words found (tests/fixtures/search_before_concepts.js); a
    word next to a concept stays a condition; concept words only where they stand as words or word starts; the
    evaluation query and the related guides; a menu's price shown whole. Nothing skipped: this build's forms carry
    the query words. (Here because this module already builds the city's real data.)"""
    import os
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    r = subprocess.run([node, "--test", str(ROOT / "tests" / "js" / "search.test.js")], cwd=ROOT,
                       env={**os.environ, "SEARCH_SITE_DIR": str(public)}, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0, r.stdout[-6000:] + "\n" + r.stderr[-3000:]
    assert re.search(r"(?:#|ℹ) fail 0", r.stdout) and re.search(r"(?:#|ℹ) skipped 0", r.stdout), r.stdout[-2000:]


def test_a_conflict_kept_without_its_call_line_gets_the_call():
    """A description that keeps '…은 출처마다 다릅니다.' but cuts the summary's later sentence that carried the call line
    ends that conflict with '방문 전에 전화로 확인해야 합니다' (CLAUDE.md 3.2), while it fits."""
    from pipeline.build import with_call
    s = "[샘플]관은 쉬는 날 없이 운영합니다. 이용시간은 출처마다 다릅니다. 주차: 가능."
    assert with_call(s, DESC_MAX) == "[샘플]관은 쉬는 날 없이 운영합니다. 이용시간은 출처마다 달라 방문 전에 전화로 확인해야 합니다. 주차: 가능."
    assert with_call(s, len(s)) == s   # no room: unchanged
    called = "요금은 출처마다 달라 방문 전에 전화로 확인해야 합니다. 이용시간은 출처마다 다릅니다."
    assert with_call(called, DESC_MAX) == called
