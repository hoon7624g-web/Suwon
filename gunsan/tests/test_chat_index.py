"""Site assistant knowledge (pipeline/chat_index.py), exported from the real data the way the public build does:
every published place, guide, course, event series, /abroad/ article and video is there; the core catalog lists the
places with facts as a directory, the full place lines (lines.json) carry the first-screen key facts with both values
where sources differ; every fact names its source, the exact address the value came from and the date this site checked
it, and the link check allows that address; dates are named for what they are (출처 확인, 페이지 검수, 운영자 공개 승인,
원문 수집, 시행); a timetable chain is spelled out stop by stop with its direction and kind of time; the about page says
what the chat sends where; no TourAPI overview or 군산시 original text; the bytes do not depend on the build date; the
core stays under CORE_BUDGET and all lines under LINES_BUDGET."""
import datetime as dt
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import build as B
from pipeline import chat_index, en_site, present
from pipeline.build import State, build
from pipeline.schema import FACT_ORDER, FIT_ORDER, INDEX_MIN_GROUPS, index_groups


@pytest.fixture(scope="module", autouse=True)
def _engine_both_values(engine_both_values):
    """This module checks the engine's both-values display on 군산각's data (tests/conftest.py)."""

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"
SAMPLE = ROOT / "data" / "sample"
LETTERS = ("P ", "G ", "C ", "E ", "A ", "V ", "T ", "S ")


def _state(data: Path, mode: str = "production") -> State:
    S = State(data, mode)
    S.intl = en_site.load_all(S, data)   # as pipeline.build does: every version, English first
    S.en = S.intl.sites.get("en")
    return S


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    S = _state(GUNSAN)
    out = tmp_path_factory.mktemp("chat")
    stats = chat_index.export(S, out)
    d = out / "chat"
    return {"S": S, "stats": stats, "dir": d, "catalog": (d / "catalog.txt").read_text("utf-8"),
            "lines": json.loads((d / "lines.json").read_text("utf-8")),
            "docs": json.loads((d / "docs.json").read_text("utf-8")), "index": json.loads((d / "index.json").read_text("utf-8"))}


def _lines(catalog: str) -> dict[str, str]:
    """catalog line by its path / id (the second field)."""
    return {line.split(" | ")[0][2:]: line for line in catalog.splitlines() if line[:2] in LETTERS}


def _full(real) -> dict[str, str]:
    """The full P and A lines (lines.json) by their key: a place's path, 'abroad:<id>'."""
    return real["lines"]["lines"]


def _thin(e: dict) -> bool:
    return len(index_groups(e)) < INDEX_MIN_GROUPS


def test_every_published_record_is_in_the_catalog_and_the_docs(real):
    S, docs = real["S"], real["docs"]["docs"]
    lines, full = _lines(real["catalog"]), _full(real)
    for e in S.entities:
        assert e["_path"] in full and e["_path"] in docs, e["id"]
    for x in S.guides + S.courses + S.series:
        assert x["_path"] in lines and x["_path"] in docs, x["_path"]
    for a in S.abroad:
        assert f"abroad:{a['id']}" in full and f"abroad:{a['id']}" in docs
    for v in S.videos:
        assert f"video:{v['youtube_id']}" in docs
    for path in ("/", "/about/", "/map/", "/search/", "/places/", "/food/", "/stays/", "/events/", "/videos/", "/abroad/"):
        assert path in lines and path in docs, path
    assert real["stats"]["places"] == len(S.entities) == sum(1 for x in full.values() if x.startswith("P "))
    assert real["stats"]["places_listed"] == len(real["lines"]["core"]) == sum(
        1 for x in real["catalog"].splitlines() if x.startswith("P "))
    # guide sections: one doc per body section, keyed by the section's anchor on the guide page (h-b1 …)
    g = next(g for g in S.guides if g.get("body"))
    assert f"{g['_path']}#h-b{len(g['body'])}" in docs


def test_place_lines_carry_the_first_screen_facts_and_both_values_where_sources_differ(real):
    S = real["S"]
    lines = _full(real)
    seen_conflict = 0
    for e in S.entities:
        line = lines[e["_path"]]
        kf = present.key_facts(e, "hero")
        for s in kf["slots"]:
            label = chat_index.SHORT_LABEL.get(s["label"], s["label"])
            assert f"{label} " in line, (e["id"], s["label"])
            if s.get("conflict"):
                seen_conflict += 1
                assert f"{label} 두 출처 다름: " in line
                for v in s["vals"]:
                    assert v["provider"] in line, (e["id"], v["provider"])
        # the place's own doc names both values of every differing fact and the call line
        doc = real["docs"]["docs"][e["_path"]]["x"]
        for k, alts in (e.get("fact_alternatives") or {}).items():
            row = B.fact_row(e, k)
            if row and any(not a["also"] for a in row["alternatives"]):
                assert "다른 출처 값" in doc and "방문 전 전화 확인" in doc, e["id"]
    assert seen_conflict > 0


def test_a_seat_count_alone_is_not_parking_in_the_knowledge(real):
    """모트 '30석' (군산시 '주차 및 좌석수', seats only): no parking slot in the full line, the doc gives the value
    under 좌석 and names 주차 among the values the site does not have; 명동소바's two parking values both."""
    S = real["S"]
    lines, docs = _full(real), real["docs"]["docs"]
    e = S.ent_by_slug["모트"]
    assert "주차·좌석" not in lines[e["_path"]] and "주차 " not in lines[e["_path"]]
    doc = docs[e["_path"]]["x"]
    assert "- 좌석: 30석 — " in doc and "사이트에 없는 값(확인 필요): 주차" in doc and "주차·좌석" not in doc
    m = S.ent_by_slug["명동소바"]
    assert "주차·좌석 두 출처 다름: " in lines[m["_path"]]
    assert "인근 공영주차장/70석" in lines[m["_path"]] and "불가능 / 70석" in lines[m["_path"]]


def test_every_fact_names_its_source_address_and_check_date(real):
    """The external evaluation (2026-10-13) asked for the two official pages behind the museum's two opening hours and
    got 'not in the site's data' although the place page links them: each value now carries its source, the address it
    came from and the date this site checked that source, and the link check (docs.json ext) allows that address."""
    S, docs, ext = real["S"], real["docs"]["docs"], set(real["docs"]["ext"])
    with_url = 0
    for e in S.entities:
        doc = docs[e["_path"]]["x"]
        for k in FACT_ORDER + FIT_ORDER:
            row = B.fact_row(e, k)
            if not row:
                continue
            for src in ([row["source"]] if row["value"] else []) + row["alternatives"]:
                url = chat_index._fact_url(e, src)
                said = f" — {chat_index._src(src, url)}"
                assert said in doc, (e["id"], k, said)
                if url:
                    with_url += 1
                    assert url in ext, (e["id"], url)
                if src.get("checked_at"):
                    assert said.endswith(f"(출처 확인 {src['checked_at']})"), said
        # the page's own dates, each named for what it is
        dates = chat_index._dates(B.facts_checked_date(e), e.get("reviewed_at") or "", e.get("approved_at") or "")
        assert dates in doc.split("\n"), e["id"]
        assert "페이지 검수" in dates and (not e.get("approved_at") or f"운영자 공개 승인 {e['approved_at']}" in dates)
    assert with_url > 100
    # the museum the evaluation asked about: both hours with their own pages
    museum = next(e for e in S.entities if e["_path"] == "/places/근대역사박물관/")
    doc = docs[museum["_path"]]["x"]
    usetime = B.fact_row(museum, "usetime")
    for src in [usetime["source"], *usetime["alternatives"]]:
        url = chat_index._fact_url(museum, src)
        assert url.startswith("http") and url in doc and url in ext, src


def test_dates_by_kind_and_timetables_with_their_effective_date(real):
    S, docs = real["S"], real["docs"]["docs"]
    chains = 0
    for g in S.guides:
        doc = docs[g["_path"]]["x"]
        assert chat_index._dates(g.get("checked_at") or "", g.get("reviewed_at") or "", g.get("approved_at") or "") in doc
        timetables = chat_index._effective(g.get("sources") or [])
        if timetables:
            assert "시간표 시행일: " + "; ".join(timetables) in doc
        for i, b in enumerate(g.get("body") or [], 1):
            sec = docs[f"{g['_path']}#h-b{i}"]["x"]
            assert sec.split("\n")[-1].startswith("가이드 날짜: "), (g["id"], i)
            lines = chat_index._chain_lines(chat_index._clean(b.get("text")))
            chains += bool(lines)
            for line in lines:
                assert line in sec
            if timetables and "시간표" in b.get("text", ""):
                assert "이 절의 시간표: " in sec and "시행 " in sec, (g["id"], i)
    assert chains >= 1   # the 99번 sentence the evaluation misread ('선유도 21:15' taken for the last bus)
    for c in S.courses:
        doc = docs[c["_path"]]["x"]
        assert "날짜: " in doc and "페이지 검수" in doc
        if (c.get("original") or {}).get("collected_at"):
            assert f"원문 수집 {c['original']['collected_at']}" in doc
    # the nearby bus block names the timetable its route numbers come from, with its 시행일
    meta = (S.nearby_meta.get("bus") or {}).get("timetable") or {}
    if meta.get("effective_date"):
        assert any(f"시행 {meta['effective_date']}" in d["x"] and "노선 번호는 이 시간표 기준" in d["x"]
                   for d in docs.values() if d["k"] == "place")


def test_chain_lines_spell_out_stop_direction_and_kind_of_time():
    text = ("99번은 A역을 떠나 섬을 돌아옵니다. 시간표의 기준 시각은 A역 06:10, 09:10~20:10 매시 10분(13회) → B(환) 06:35~20:35 "
            "→ C섬 07:15~21:15 → D섬 07:20~21:20 → B(환) 07:45~21:45입니다. 평일과 같습니다.")
    lines = chat_index._chain_lines(text)
    assert lines[1] == "- A역 — 출발 시각(첫 정류장), 가는 길(D섬 쪽): 06:10, 09:10~20:10 매시 10분(13회) (첫 06:10, 마지막 20:10)"
    assert lines[3] == ("- C섬 — 버스가 그 정류장에 오는 시각(거기서 타고 내림), 가는 길(D섬 쪽): 07:15~21:15 "
                        "(첫 07:15, 마지막 21:15)")
    assert lines[4] == ("- D섬 — 버스가 그 정류장에 오는 시각(거기서 타고 내림), 가는 길의 끝(D섬, 여기서 돌아 나옴): 07:20~21:20 "
                        "(첫 07:20, 마지막 21:20)")
    assert lines[5] == ("- B(환) — 버스가 그 정류장에 오는 시각(거기서 타고 내림), 돌아오는 길(A역 쪽): 07:45~21:45 "
                        "(첫 07:45, 마지막 21:45)")
    # a stop time is the time to get on there — not a departure toward it
    assert ("정류장에 붙은 시각은 버스가 그 정류장에 오는 시각이라 그 정류장에서 타는 시각이고, A역에서 그 시각에 출발하는 차라는 "
            "뜻이 아니다.") in lines[6]
    assert "C섬 21:15" not in lines[6]   # live check 2026-10-14: a named example made the model deny the way back
    assert lines[6].endswith("D섬 쪽으로 가는 마지막 차는 A역 20:10 출발이다.")
    # the way back (the review: '선유도에서 군산대 쪽으로 가는 막차' answered 'not on the site'): a stop the way back passes
    # again has its own times; a stop it does not list is served by the same bus, which goes on to the end and returns
    assert lines[7] == "돌아오는 길: D섬까지 간 차가 돌아 나와 B(환) 07:45~21:45 순으로 지난다. 이 표에는 A역에 닿는 시각이 없다."
    assert lines[8] == "B(환)에서 A역 쪽으로 가는 차: 돌아오는 길의 B(환) 07:45~21:45 (마지막 21:45)."
    assert lines[9] == ("C섬에서 A역 쪽으로 가는 막차: C섬에 21:15에 오는 차를 타고 그대로 있으면 된다(D섬 21:20 → B(환) 21:45 → "
                        "A역 쪽, A역 도착 시각은 이 표에 없음). C섬에 오는 차(07:15~21:15)는 모두 D섬까지 갔다가 돌아 나와 B(환) 순으로 "
                        "지난다. 돌아오는 차가 C섬 정류장을 다시 지나는 시각은 이 표에 없다.")
    assert lines[10] == "D섬에서 A역 쪽으로 가는 차: D섬에 오는 차(07:20~21:20)가 그대로 돌아 나간다(마지막 21:20)."
    assert len(lines) == 11
    # a route that does not come back: no way-back lines
    one_way = chat_index._chain_lines("기준 시각은 A역 06:10 → B역 06:35 → C역 07:00입니다.")
    assert one_way[1].endswith("가는 길: 06:10 (첫 06:10, 마지막 06:10)") and not any("돌아" in x for x in one_way)
    # no chain, a chain without times, or two stops only: nothing is added
    assert chat_index._chain_lines("기준 시각은 없습니다.") == []
    assert chat_index._chain_lines("기준 시각은 A역 → B역입니다.") == []
    assert chat_index._chain_lines("기준 시각은 A역 06:10 → B역 06:35입니다.") == []


def test_the_guide_gives_each_stop_its_way_back(real):
    """A reader of the whole bus guide (not only its timetable section) gets the way back from each stop too."""
    S, docs = real["S"], real["docs"]["docs"]
    seen = 0
    for g in S.guides:
        body = g.get("body") or []
        at = next((i for i, b in enumerate(body, 1) if chat_index._chain_lines(chat_index._clean(b.get("text")))), 0)
        if not at:
            continue
        seen += 1
        doc = docs[g["_path"]]["x"]
        back = [x for x in chat_index._chain_lines(chat_index._clean(body[at - 1].get("text")))
                if x.startswith("돌아오는 길:") or " 쪽으로 가는 차: " in x]
        assert back and all(f"- {x}" in doc.split("\n") for x in back), g["id"]
        assert doc.index("시간표에서 돌아가는 차") < 6000   # inside what get_pages reads of a page
    assert seen >= 1


def test_other_names_and_the_combined_ticket_s_places(real):
    """The external evaluation's assistant 'corrected' a right answer (구 일본 제18은행 군산지점 is in the museum's
    combined ticket) because the museum page gave the ticket's places only by kind ('박물관·미술관·건축관·위봉함') and
    nothing tied 군산근대미술관 to the bank's page. Now the place's lines (the core's directory line and the full
    line) carry its other names, a combined ticket in a fee table comes with the guides' sentences about it and the
    pages of the places they name, and an other name counts as a title for search."""
    S, docs, idx = real["S"], real["docs"]["docs"], real["index"]["docs"]
    lines, core = _full(real), _lines(real["catalog"])
    for e in S.entities:
        alt = chat_index.jsonld.alternate_names(e)
        if alt:
            assert f" · 다른 이름 {', '.join(alt)} | " in lines[e["_path"]], e["id"]
            if e["_path"] in core:
                assert f" · 다른 이름 {', '.join(alt)} | " in core[e["_path"]], e["id"]
            head = set(idx[e["_path"]][0].split())
            assert set(chat_index.tokens(" ".join(alt))) <= head, e["id"]
    bank = "/places/구-일본-제18은행-군산지점/"
    assert "다른 이름 군산근대미술관" in lines[bank] and "다른 이름 군산근대미술관" in core[bank]
    museum = docs["/places/근대역사박물관/"]["x"].split("\n")
    fee = next(i for i, x in enumerate(museum) if x.startswith("- 이용요금: [박물관 통합권]"))
    said, named = museum[fee + 1], museum[fee + 2]
    assert said.startswith("- 이용요금의 '박물관 통합권'(가이드의 설명): 박물관 통합권은 근대역사박물관·군산근대미술관·군산근대건축관·위봉함")
    assert "(/guides/비-오는-날-군산/)" in said
    # the review's fix, word for word: the ticket's 4 places with their official names and paths, under the fee line
    assert named == ("  '박물관 통합권' 시설 4곳(가이드가 쓴 이름 — 장소 페이지): 근대역사박물관 /places/근대역사박물관/ (이 페이지); "
                     "군산근대미술관 = 구 일본 제18은행 군산지점 /places/구-일본-제18은행-군산지점/; 군산근대건축관 /places/군산근대건축관/; "
                     "진포해양공원 위봉함 /places/진포해양공원/")
    # only sentences about the ticket: '근대역사박물관·근대미술관·근대건축관은 박물관 통합권 … 호남관세박물관·초원사진관 …은
    # 입장료가 없습니다' is about the places, and 호남관세박물관 is not one of the ticket's
    assert "호남관세박물관" not in said + named and "초원사진관" not in said + named
    assert fee + 2 < len(museum) and "\n".join(museum).index(named) < 6000   # read by get_pages (6,000 characters)
    bank_doc = docs[bank]["x"]
    assert "- 이용요금의 '통합권'(가이드의 설명): 박물관 통합권은 근대역사박물관·군산근대미술관" in bank_doc
    assert ("  '통합권' 시설 4곳(가이드가 쓴 이름 — 장소 페이지): 근대역사박물관 /places/근대역사박물관/; 군산근대미술관 = 구 일본 "
            "제18은행 군산지점 /places/구-일본-제18은행-군산지점/ (이 페이지); 군산근대건축관 /places/군산근대건축관/; 진포해양공원 위봉함 "
            "/places/진포해양공원/") in bank_doc.split("\n")
    # the full line carries the ticket's places too, the bank by the name the guides use and its page name
    four ="근대역사박물관·군산근대미술관(=구 일본 제18은행 군산지점 /places/구-일본-제18은행-군산지점/)·군산근대건축관·진포해양공원 위봉함"
    assert f" | 박물관 통합권 4곳: {four}" in lines["/places/근대역사박물관/"]
    assert f" | 통합권 4곳: {four}" in lines[bank]
    # the other names as docs.json gives them (search_site and get_pages show them by the title)
    assert docs[bank]["a"] == ["군산근대미술관"]
    for e in S.entities:
        assert docs[e["_path"]].get("a", []) == chat_index.jsonld.alternate_names(e), e["id"]
    # a fee table without a combined ticket gets nothing
    assert not any("(가이드의 설명)" in d["x"] for k, d in docs.items() if k not in ("/places/근대역사박물관/", bank))
    assert sum(" 통합권 4곳: " in line for line in lines.values()) == 2


def test_get_pages_reads_every_place_s_facts_and_dates(real):
    """Review 2026-10-22 (docs6000 CLAIM-5): get_pages reads a page up to knowledge.js DOC_CHARS, and the combined
    tickets' rules — one source written after each of 11 rules — pushed 근대역사박물관's 문의, 유모차, 장애인 주차·화장실,
    접근로 and 날짜 lines past it (구 일본 제18은행·진포해양공원 too). Now a source is written once for a run of rules that
    share it, and every place doc's lines from '정보(' through '날짜:' and '사이트에 없는 값' start before the cut."""
    cap = int(re.search(r"export const DOC_CHARS = (\d+)", (ROOT / "chatbot" / "knowledge.js").read_text("utf-8")).group(1))
    docs = real["docs"]["docs"]
    places = [k for k, d in docs.items() if d["k"] == "place"]
    assert len(places) == len(real["S"].entities)
    for key in places:
        lines, at = docs[key]["x"].split("\n"), 0
        starts = []
        for line in lines:
            starts.append(at)
            at += len(line) + 1
        first = next(i for i, x in enumerate(lines) if x.startswith("정보("))
        last = max(i for i, x in enumerate(lines) if x.startswith(("날짜:", "사이트에 없는 값")))
        late = [lines[i][:40] for i in range(first, last + 1) if starts[i] >= cap]
        assert not late, (key, late)
    # the rules keep their sources: each rule's words and its source in the line, the shared source written once
    museum = docs["/places/근대역사박물관/"]["x"].split("\n")
    rules = next(x for x in museum if x.startswith("  '박물관 통합권' 연령·무료·이용 조건: "))
    src = "군산근대역사박물관 홈페이지 관람안내 페이지의 통합권 요금표(나이 구분)·이용안내·관람료 면제대상"
    assert rules.count(src) == 1 and "(출처 확인 2026-10-17)" in rules
    for words in ("무료입장 6세 이하 유아", "무료입장 65세 이상 경로대상자", "어린이 2014년~ 2019년생(2026년 요금표)"):
        assert words in rules
    both = next(x for x in museum if x.startswith("  '금강권 통합권' 연령·무료·이용 조건: "))
    assert " / 어린이(7~12세) — 군산시 문화관광 금강미래체험관 페이지의 관람료 표" in both


def test_an_added_fee_value_reaches_the_planner_marked(real):
    """Review 2026-10-22 (fees C3): 금강미래체험관's notice '2026년 4~12월 매주 수요일 무료 관람' is an added value beside
    TourAPI's '매주 수요일 … 무료' (relation 'also'), and the planner's f.fee left it out — so a 2027 Wednesday was
    priced 0원 as certain. Every other source's fee value is in f.fee.alt now, an added one marked a:1 (the planner
    names only the others as a differing value)."""
    fee = real["docs"]["docs"]["/places/금강미래체험관/"]["f"]["fee"]
    assert {"p": "금강미래체험관 홈페이지 공지", "t": "2026년 4~12월 매주 수요일 무료 관람(문화가 있는 날)", "a": 1} in fee["alt"]
    assert {"w": "매주 수요일 문화가 있는 날 무료 관람", "wd": 3} in fee["fr"] and fee["p"] == "한국관광공사 TourAPI"
    for e in real["S"].entities:   # each alternative as the data has it: 'also' ones marked, the others not
        row = B.fact_row(e, "usefee")
        alt = (real["docs"]["docs"][e["_path"]].get("f") or {}).get("fee", {}).get("alt", [])
        assert [bool(a.get("a")) for a in alt] == [a["also"] for a in (row or {}).get("alternatives", [])], e["id"]


def _ticket_kb(monkeypatch, entities, guides, fees):
    from pipeline import build as B
    monkeypatch.setattr(B, "fact_row", lambda e, k: {"value": fees[e["id"]], "alternatives": []}
                        if k == "usefee" and e["id"] in fees else None)
    k = chat_index.Knowledge.__new__(chat_index.Knowledge)
    k.S = SimpleNamespace(site_url="https://x.example", entities=entities, guides=guides)
    k._names, k._sentences, k._tickets = None, None, {}
    return k


def test_tickets_align_the_lists_the_guides_give(monkeypatch):
    """A ticket's places come from the guides' sentences about it, one per place however each sentence names it
    ('근대미술관' = '군산근대미술관', '위봉함' = '진포해양공원 위봉함'); a sentence whose list adds a place that is not
    the ticket's ('금강권 통합권은 … 채만식문학관을 더한') is never used; a place with no page says so."""
    ents = [{"id": "m", "name": "근대역사박물관", "_path": "/places/m/"},
            {"id": "b", "name": "구 일본 제18은행 군산지점", "alternate_names": ["군산근대미술관"], "_path": "/places/b/"},
            {"id": "c", "name": "군산근대건축관", "_path": "/places/c/"},
            {"id": "j", "name": "진포해양공원", "_path": "/places/j/"},
            {"id": "x", "name": "채만식문학관", "_path": "/places/x/"}]
    guides = [
        {"id": "g1", "_path": "/guides/g1/", "body": [{"text": "박물관 통합권은 근대역사박물관·군산근대미술관·군산근대건축관·위봉함 "
         "네 곳을 묶은 표로 성인 3,000원입니다. 금강권 통합권은 박물관 통합권 네 곳에 채만식문학관·금강미래체험관을 더한 표로 "
         "성인 5,000원입니다."}]},
        {"id": "g2", "_path": "/guides/g2/", "body": [{"text": "박물관 통합권은 근대역사박물관, 근대미술관, 근대건축관, 진포해양공원 "
         "위봉함을 묶은 표로 성인 3,000원입니다. 박물관 통합권은 박물관·미술관·건축관·위봉함·채만식문학관을 묶은 표입니다."}]}]
    fees = {"m": "[박물관 통합권] - 성인 3,000원 [개별권] - 성인 2,000원",
            "b": "[통합권]인근 전시장(박물관+미술관+건축관+위봉함) - 성인 3,000원", "c": "성인 500원"}
    k = _ticket_kb(monkeypatch, ents, guides, fees)
    want = [("근대역사박물관", "m", "name"), ("군산근대미술관", "b", "other"), ("군산근대건축관", "c", "name"),
            ("진포해양공원 위봉함", "j", "name")]
    for pid, label, n_said in (("m", "박물관 통합권", 2), ("b", "통합권", 1)):
        [t] = k.tickets(next(e for e in ents if e["id"] == pid))
        assert t["label"] == label and len(t["said"]) == n_said, pid
        assert [(p["written"], p["e"]["id"], p["by"]) for p in t["places"]] == want, pid
        assert not any("채만식" in s for _, s in t["said"]), pid
    assert k.tickets(ents[2]) == []   # no combined ticket in the fee table
    assert k.ticket_lines(ents[0])[1] == ("  '박물관 통합권' 시설 4곳(가이드가 쓴 이름 — 장소 페이지): 근대역사박물관 /places/m/ "
                                          "(이 페이지); 군산근대미술관 = 구 일본 제18은행 군산지점 /places/b/; 군산근대건축관 "
                                          "/places/c/; 진포해양공원 위봉함 /places/j/")
    # without a page for 진포해양공원 the 위봉함 is still one of the four, said to have no page
    k2 = _ticket_kb(monkeypatch, [e for e in ents if e["id"] != "j"], guides, fees)
    assert k2.ticket_lines(ents[0])[1].endswith("; 군산근대건축관 /places/c/; 위봉함 (장소 페이지 없음)")


def test_places_in_reads_longer_names_first():
    S = SimpleNamespace(site_url="https://x.example", entities=[
        {"id": "a", "name": "근대역사박물관", "alternate_names": ["군산근대역사박물관"], "_path": "/places/a/"},
        {"id": "b", "name": "구 일본 제18은행 군산지점", "alternate_names": ["군산근대미술관"], "_path": "/places/b/"},
        {"id": "c", "name": "연도", "_path": "/places/c/"}], guides=[])
    k = chat_index.Knowledge.__new__(chat_index.Knowledge)
    k.S, k._names, k._sentences, k._tickets = S, None, None, {}
    found = k.places_in("군산 근대미술관과 군산근대역사박물관, 연도별 요금")
    assert [(w, e["id"]) for w, e in found] == [("군산근대미술관", "b"), ("군산근대역사박물관", "a")]
    assert k.places_in("군산근대미술관", skip={"b"}) == []


def test_effective_dates_come_from_the_source_title():
    srcs = [{"name": "군산시내버스시간표(2024.10.21 시행) — 군산시", "url": "https://x.example/t.xlsx"},
            {"name": "시내버스 — 군산시 문화관광", "url": "https://x.example/bus"}]
    assert chat_index._effective(srcs) == ["군산시내버스시간표 — 군산시, 시행 2024-10-21, https://x.example/t.xlsx"]
    assert chat_index._effective([]) == []


def test_the_about_doc_says_what_the_chat_sends_where(real):
    about = real["docs"]["docs"]["/about/"]["x"]
    for words in ("sessionStorage", "서버 함수(/api/chat/)", "최근 12개 메시지", "Anthropic API", "Anthropic의 정책",
                  "이미 보낸 내용을 지울 수 없다", "자동으로 가리는 기능은 없다", "'새 대화'"):
        assert words in about, words
    # the page says the same (templates/about.html.j2)
    page = (ROOT / "templates" / "about.html.j2").read_text("utf-8")
    for words in ("최근 12개 메시지", "Anthropic API", "지울 수 없습니다", "자동으로 가려 주는 기능은 없습니다", "‘새 대화’"):
        assert words in page, words


def test_the_emergency_numbers_are_one_short_catalog_line_and_a_sourced_doc(real):
    """Operator 2026-10-15 (QA C16/C21): the numbers of site.json emergency (KTO VisitKorea) — one catalog line without
    addresses, which prompt rule 14 answers from without a tool, and the doc /about/#emergency with each number's
    provider, the address it came from and the date this site checked it."""
    em = real["S"].site["emergency"]
    lines = [x for x in real["catalog"].splitlines() if x.startswith("S /about/#emergency")]
    assert len(lines) == 1, lines
    assert all(n in lines[0] for n in ("119", "112", "1330", "+82-2-1330", "English please")), lines[0]
    assert "http" not in lines[0] and chat_index.estimate_tokens(lines[0]) <= 100
    doc = real["docs"]["docs"]["/about/#emergency"]
    assert doc["k"] == "page" and doc["h"] == "긴급 연락처" and doc["e"] == "/en/about/"
    for s in em["sources"].values():
        assert s["url"] in doc["x"] and s["url"] in real["docs"]["ext"]
    assert doc["x"].count(f"출처 확인 {em['checked_at']}") == len(em["lines"]) + len(em["steps"])
    assert "응급" in doc["x"] and "구급차" in doc["x"]
    # the build without the block (the sample data) has neither
    sample = _state(SAMPLE, "sample")
    assert not sample.site.get("emergency")
    k = chat_index.Knowledge(sample).build()
    assert not any("#emergency" in x for x in k.lines) and "/about/#emergency" not in k.docs


def test_event_series_carry_their_name_in_every_version_that_lists_them(real):
    """A card to an event series opens <home>events/#anchor in the reader's version: it carries the series' name there."""
    docs = real["docs"]["docs"]
    series = [docs[sr["_path"]] for sr in real["S"].series if docs[sr["_path"]].get("l")]
    assert len(series) > 10
    for d in series:
        assert set(d["n"]) == set(d["l"]), d["t"]
        assert all(v and not re.search("[가-힣]", v) for h, v in d["n"].items()), d["n"]


def test_search_tokens_leave_out_web_addresses(real):
    """Source addresses are not words a reader searches for: the parts of 'https://www.gunsan.go.kr/tour/m2080/view/…'
    or '…/userInfo101.jsp' never make a page match."""
    for key, (head, body) in real["index"]["docs"].items():
        assert not ({"m2080", "userinfo101", "m2339"} & set(body.split())), key


def test_english_pages_are_known_for_link_mapping(real):
    S, data = real["S"], real["docs"]
    en = S.en
    assert en is not None
    for p in en.places.values():
        doc = data["docs"][p["e"]["_path"]]
        assert doc["e"] == p["path"]
        assert data["alias"][p["path"]] == p["e"]["_path"]
        assert f"({p['name']})" in _full(real)[p["e"]["_path"]]   # the English name on the line
        assert f"({p['name']})" in _lines(real["catalog"]).get(p["e"]["_path"], f"({p['name']})")   # and the directory's
    for x in en.guides.values():
        assert data["docs"][x["g"]["_path"]]["e"] == x["path"]
    # every version: a reader of that language opens that version's page and sees its name on the link card
    for site in S.intl.sites.values():
        h = site.loc.html
        for p in site.places.values():
            doc = data["docs"][p["e"]["_path"]]
            assert doc["l"][h] == p["path"] and doc["n"][h] == p["name"], (h, p["path"])
            assert data["alias"][p["path"]] == p["e"]["_path"]
        for x in site.guides.values():
            assert data["docs"][x["g"]["_path"]]["l"][h] == x["path"]
            assert data["alias"][x["path"]] == x["g"]["_path"]
    assert len(S.intl.sites) == 8


def test_the_site_search_opens_in_the_reader_s_version(real):
    """QA 2026-10-15: the chat's '사이트 검색' link (it often sends a reader there) opens <home>search/ of the answer's
    language, as /food/ does — every version builds its search page (en_site Pages.search)."""
    doc = real["docs"]["docs"]["/search/"]
    assert doc["e"] == "/en/search/"
    sites = real["S"].intl.sites.values()
    assert doc["l"] == {s.loc.html: f"/{s.loc.code}/search/" for s in sites if s.places}
    assert doc["l"]["zh-Hans"] == "/zh-hans/search/" and len(doc["l"]) == 8
    assert real["docs"]["alias"]["/ja/search/"] == "/search/"


def test_no_tourapi_overview_and_no_gunsan_original_text(real):
    blob = real["catalog"] + json.dumps(real["lines"], ensure_ascii=False) + json.dumps(real["docs"], ensure_ascii=False)
    checked = 0
    for e in real["S"].entities_all:
        for text in ((e.get("tourapi") or {}).get("overview"), (e.get("original") or {}).get("text")):
            for sentence in re.split(r"(?<=[.!?다])\s+", str(text or "")):
                if len(sentence) >= 40:
                    checked += 1
                    assert sentence not in blob, (e["id"], sentence[:60])
    assert checked > 100


def test_a_ticket_is_named_by_its_places_never_by_the_table_s_own_words(real):
    """Review 2026-10-18: tickets.json 'covers' (a 60+ character run of 군산시 문화관광's page, CLAUDE.md 3.3) reached the
    public through docs.json and the chat's fee_total. What a ticket opens is its places' page names ('7곳: 근대역사박물관
    · …') in the place docs, and docs.json 'tickets' has no 'covers'; tickets.json keeps it as source data only."""
    from pipeline import tickets
    S, docs = real["S"], real["docs"]
    data = tickets.load(GUNSAN)
    by_id = {e["id"]: e for e in S.entities}
    assert docs["tickets"] and all("covers" not in t for t in docs["tickets"])
    # anywhere but a place's own 요금 value (a table value: '[통합권]인근 전시장(박물관+미술관+건축관+위봉함)')
    lines = [*real["catalog"].split("\n"), *_full(real).values(),
             *(x for d in docs["docs"].values() for x in d["x"].split("\n"))]
    for t in data["tickets"]:
        assert t["covers"] not in json.dumps(docs["tickets"], ensure_ascii=False), t["id"]
        assert not [x for x in lines if t["covers"] in x and not x.startswith("- 이용요금")], t["id"]
        names = [by_id[p]["name"] for p in t["places"]]
        head = f"- 통합권 요금표 '{t['name']}'({len(names)}곳: {' · '.join(names)}): "
        for pid in t["places"]:
            assert any(x.startswith(head) for x in docs["docs"][by_id[pid]["_path"]]["x"].split("\n")), (t["id"], pid)


def test_outside_links_are_the_data_s_own_addresses(real):
    ext = set(real["docs"]["ext"])
    assert "https://www.gunsan.go.kr/tour" in ext
    assert all(u.startswith(("http://", "https://")) and not u.startswith(real["S"].site_url) for u in ext)
    for a in real["S"].abroad:
        assert a["url"] in ext


def test_bytes_do_not_depend_on_the_build_date(real, tmp_path, monkeypatch):
    class Later(dt.date):
        @classmethod
        def today(cls):
            return cls(2031, 7, 1)

    class LaterTime(dt.datetime):   # the build date is Seoul's day (State: datetime.now(Asia/Seoul), 2026-11-01)
        @classmethod
        def now(cls, tz=None):
            return cls(2031, 7, 1, 12, 0, tzinfo=tz)
    monkeypatch.setattr(B, "dt", SimpleNamespace(date=Later, timedelta=dt.timedelta, datetime=LaterTime))
    S = _state(GUNSAN)
    assert S.today == "2031-07-01"
    chat_index.export(S, tmp_path)
    for name in ("catalog.txt", "lines.json", "docs.json", "index.json"):
        data = (tmp_path / "chat" / name).read_bytes()
        assert data == (real["dir"] / name).read_bytes(), name
        assert b"\r\n" not in data
    assert "2031" not in real["catalog"] and "2031" not in json.dumps(real["lines"], ensure_ascii=False)
    assert (real["dir"] / "lines.json").read_text("utf-8") == chat_index.dumps(real["lines"]) + "\n"


def test_the_core_lists_the_places_with_facts_as_a_directory_under_its_budget(real):
    """The cached core (catalog.txt): every place as a four-field directory line — path, title, type, where — and no
    facts, the thin ones (fewer than INDEX_MIN_GROUPS required groups) too while the budget allows (review 2026-10-23:
    the only 찜질방 are thin, and a core without them never named the type); core = those paths in catalog order; each
    kind's heading counts them; no A lines; the whole file under CORE_BUDGET."""
    S, cat, lj = real["S"], real["catalog"], real["lines"]
    est = real["stats"]["catalog_tokens_est"]
    assert est == chat_index.estimate_tokens(cat)
    assert est <= chat_index.CORE_BUDGET, f"core {est} estimated tokens > {chat_index.CORE_BUDGET}"
    rows = cat.splitlines()
    directory = [x for x in rows if x.startswith("P ")]
    assert [x.split(" | ")[0][2:] for x in directory] == lj["core"]   # core = the directory, in catalog order
    core = set(lj["core"])
    thin = [e for e in S.entities if _thin(e)]
    assert thin and real["stats"]["places_thin"] == 0 and real["stats"]["places_cut"] == 0
    for e in S.entities:
        path = e["_path"]
        assert path in lj["lines"], e["id"]
        assert path in core, e["id"]   # every place of this region fits, the thin ones too
    assert real["stats"]["places_listed"] == len(S.entities)
    # every type of place is named in the cached core, those only thin places have too (the old core named no 찜질방)
    types = {x.split(" | ")[2] for x in directory}
    assert types == {e.get("_type") or chat_index.KIND_LABELS[e["kind"]] for e in S.entities}
    full = _full(real)
    for line in directory:
        fields = line.split(" | ")
        assert len(fields) == 4 and all(fields), line
        whole = full[fields[0][2:]].split(" | ")
        assert fields[:3] == whole[:3], line   # path, title (name, English name, 다른 이름), type as the full line has them
    assert sum(x.endswith(" | -") for x in directory) == sum(1 for e in S.entities if not (
        e.get("_area") or e.get("_road") or e.get("_region") not in (None, "", present.NONE_LABEL)))
    # each kind's heading: the total and how many are listed — all of them, so nothing is left to search_site
    for kind in chat_index.KIND_ORDER:
        items = S.lists.get(kind) or []
        head = f"## {chat_index.KIND_HEAD[kind]} {len(items)}곳 — 목록 "
        [h] = [x for x in rows if x.startswith(head)]
        assert h.endswith(f" — 이 목록에 {len(items)}곳"), h
    # /abroad/: the heading only, its A lines in lines.json
    assert not any(x.startswith("A ") for x in rows)
    [h] = [x for x in rows if x.startswith("## 해외에서 본 ")]
    assert f"기사 {len(S.abroad)}건 — 페이지 /abroad/" in h and "lines 블록" in h and "search_site" in h
    # the header explains the directory and the lines block, and the other sections are as they were
    # (never a '<': chatbot/prompt.js neutralise() would rewrite the cached bytes — the tag is named, not written)
    assert 'site_data block whose source is "lines"' in cat and "P path | name | type | where" in cat
    assert "<" not in cat and not any("<" in x for x in full.values())
    assert "read its page with get_pages (or find it with search_site) before you state its hours" in cat
    for x in S.guides + S.courses + S.series:
        assert x["_path"] in _lines(cat), x["_path"]


def test_over_the_budget_the_lowest_priority_places_leave_the_core(real):
    """A region bigger than CORE_BUDGET (Jeju, Busan, Seoul): directory lines leave lowest priority first — a page that
    is not indexable before one that is, then fewer required groups (the thin places first of all), then name order —
    the heading says how many and why, the file fits and the result is the same every time; the full lines stay in
    lines.json."""
    k = chat_index.Knowledge(real["S"]).build()
    assert k.core == real["lines"]["core"] and k.catalog() == real["catalog"]
    budget = chat_index.estimate_tokens(k.catalog()) - 3_000
    lines, core = k.fit_core(budget)
    assert chat_index.estimate_tokens(k._render(lines)) <= budget
    dropped = [p for p in real["lines"]["core"] if p not in set(core)]
    assert len(dropped) > 50 and [p for p in real["lines"]["core"] if p in set(core)] == core
    by_path = {e["_path"]: e for e in real["S"].entities}
    rank = lambda p: (not by_path[p].get("_index_ok"), -len(index_groups(by_path[p])),   # noqa: E731
                      present.name_key(by_path[p]["name"]), p)
    assert max(rank(p) for p in core) < min(rank(p) for p in dropped)
    thin = {p for p in real["lines"]["core"] if _thin(by_path[p])}
    assert thin and thin <= set(dropped)   # the thin places leave first
    assert sum(c["thin"] for c in k.counts.values()) == len(thin)
    assert sum(c["cut"] + c["thin"] for c in k.counts.values()) == len(dropped)
    for kind, c in k.counts.items():
        [h] = [x for x in lines if x.startswith(f"## {chat_index.KIND_HEAD[kind]} ")]
        if c["cut"] and c["thin"]:
            assert f"(핵심 정보가 {INDEX_MIN_GROUPS}개 미만 {c['thin']}곳, 목록 크기 한도로 뺀 {c['cut']}곳)" in h, h
        elif c["cut"]:
            assert f", 나머지 {c['cut']}곳(목록 크기 한도로 뺀 곳)은 search_site로 찾는다" in h, h
        elif c["thin"]:
            assert f", 나머지 {c['thin']}곳(핵심 정보가 {INDEX_MIN_GROUPS}개 미만)은 search_site로 찾는다" in h, h
    assert k.fit_core(budget) == (lines, core)
    assert k.fit_core(10) == k.fit_core(0) and not k.fit_core(0)[1]   # nothing fits: no directory line, the rest stays
    assert set(k.full) == set(real["lines"]["lines"])


def test_lines_hold_every_place_and_article_under_the_raised_ceiling(real):
    """lines.json: every place's full line by its path and every /abroad/ article's A line by 'abroad:<id>' — each key
    a docs.json key —, the core's keys, and all lines together under LINES_BUDGET (the region's size limit now that the
    whole catalog is never sent)."""
    S, lj, docs = real["S"], real["lines"], real["docs"]["docs"]
    assert set(lj) == {"v", "lines", "core"} and lj["v"] == chat_index.VERSION
    places = {e["_path"] for e in S.entities}
    articles = {f"abroad:{a['id']}" for a in S.abroad}
    assert set(lj["lines"]) == places | articles and len(lj["lines"]) == len(S.entities) + len(S.abroad)
    assert all(key in docs for key in lj["lines"])
    for key, line in lj["lines"].items():
        assert line.startswith(("P " if key in places else "A ") + key + " | "), key
        assert "\n" not in line and line == chat_index.month_ranges(line)
        # short enough to read: a long value is cut after an item, never mid-value
        assert not line.startswith("P ") or len(line) <= 600, line[:80]
    assert len(set(lj["core"])) == len(lj["core"]) and set(lj["core"]) <= places
    est = real["stats"]["lines_tokens_est"]
    assert est == chat_index.lines_tokens(lj["lines"]) and real["stats"]["lines"] == len(lj["lines"])
    assert est <= chat_index.LINES_BUDGET, f"lines {est} estimated tokens > {chat_index.LINES_BUDGET}"
    # the full line is the one Knowledge.place builds, as the whole catalog carried it: summary sentence, key facts
    museum = lj["lines"]["/places/근대역사박물관/"]
    assert museum.startswith("P /places/근대역사박물관/ | 근대역사박물관 (") and " | 시간 " in museum and "전화 " in museum


def test_estimate_and_tokens():
    assert chat_index.estimate_tokens("가나다") == 3
    assert chat_index.estimate_tokens("abcde") == 2
    assert chat_index.estimate_tokens("월명공원 09:00") == 4 + 3   # 4 Hangul + ceil(6 ASCII / 2.5)
    # the same vector as tests/js/chat.test.js (chatbot/knowledge.js tokens)
    assert chat_index.tokens("선유도 가는 법 Seonyudo 063-454-3337 a 群山 カフェ Кунсан café") == [
        "선유", "유도", "가는", "법", "seonyudo", "063", "454", "3337", "群山", "カフ", "フェ", "кунсан", "café"]


def test_search_tokens_cover_names_and_menus(real):
    idx, S = real["index"]["docs"], real["S"]
    for e in S.entities:
        head, body = (set(x.split()) for x in idx[e["_path"]])
        assert set(chat_index.tokens(e["name"])) <= head, e["id"]
        menu = (e.get("facts") or {}).get("menu")
        if menu:
            assert set(chat_index.tokens(menu)) <= head | body, e["id"]


def test_the_build_writes_the_knowledge_in_every_mode(tmp_path):
    stats = build(SAMPLE, tmp_path / "out", "sample")
    chat = tmp_path / "out" / "chat"
    assert stats["chat"]["places"] == stats["entities"]
    assert all((chat / n).exists() for n in ("catalog.txt", "lines.json", "docs.json", "index.json"))
    assert json.loads((chat / "docs.json").read_text("utf-8"))["site"]
    lj = json.loads((chat / "lines.json").read_text("utf-8"))
    assert len(lj["lines"]) == stats["entities"] and stats["chat"]["places_listed"] == len(lj["core"])
    S = State(SAMPLE, "sample")
    assert set(lj["core"]) == {e["_path"] for e in S.entities} and any(_thin(e) for e in S.entities)


def test_course_docs_say_how_to_get_around_without_a_time_of_ours(real):
    """QA 2026-10-15 F09 / F09-b: a course doc names where the course starts and ends with the nearest stops and
    routes, the timetable's first and last buses (both 비응 values with the call line), the guides, the source's day
    headings and duration — and keeps saying that per-leg and total travel times are not in the data."""
    S, docs = real["S"], real["docs"]["docs"]
    a = next(c for c in S.courses if c["id"] == "gunsan-course-m2135-1")
    doc = docs[a["_path"]]["x"]
    assert "'근대역사박물관' 100m 시내버스 01·08·09·18·19·71번" in doc
    assert "시내버스 99번 첫차~막차" in doc and "장자도 07:20~21:20(15회)" in doc and "매시 40분" in doc
    assert "구간별 소요시간·총 소요시간은 자료에 없다" in doc and "/guides/군산-시내버스-관광지/#h-b6" in doc
    b = next(c for c in S.courses if c["id"] == "gunsan-course-m2136-2")
    doc = docs[b["_path"]]["x"]
    assert "[2일차(1안)]" in doc and "[2일차(2안)]" in doc and "소요시간(코스 원문): 12시간" in doc
    assert "구간별 소요시간은 자료에 없다" in doc


def test_booking_pages_are_in_the_docs_with_each_version_s_page(real):
    """예약하기 (pipeline/booking.py): a place, guide or course doc lists the official booking pages its page shows as
    buttons, with the basis in the data; docs.json 'book' gives, per address, the service and the page each version's
    button opens (chatbot/knowledge.js links that page for a reader of that language); never an OTA or Naver; the
    about doc says the chat only links official booking pages."""
    S, docs, book = real["S"], real["docs"]["docs"], real["docs"]["book"]
    forest = next(e for e in S.entities if e["id"] == "tourapi-2737403")
    x = docs[forest["_path"]]["x"]
    assert "예약하기(페이지의 공식 예약 페이지 버튼 — 이 사이트와 챗봇은 예약을 받지 않는다):" in x
    assert "- 산림청 숲나들e: https://www.foresttrip.go.kr/indvz/main.do?hmpgId=0301 — 근거: " in x
    g32 = S.guide_by_id["guide-32"]
    assert "- 한국해운조합 여객선: https://island.theksa.co.kr/page/booking?lang= (English 페이지 " \
           "https://island.theksa.co.kr/page/booking?lang=en) — 근거: " in docs[g32["_path"]]["x"]
    c = next(c for c in S.courses if c["id"] == "gunsan-course-m2137-1")
    assert "- 한국해운조합 여객선: https://island.theksa.co.kr/page/booking?lang=" in docs[c["_path"]]["x"]
    ferry = book["https://island.theksa.co.kr/page/booking?lang="]
    assert ferry["k"] == "ferry" and ferry["p"]["en"] == ferry["p"]["ja"] == "https://island.theksa.co.kr/page/booking?lang=en"
    assert ferry["l"]["https://island.theksa.co.kr/page/booking?lang="] == "ko"
    bus = book["https://www.bustago.or.kr/newweb/kr/index.do"]
    assert bus["p"]["zh-Hant"] == bus["p"]["zh-Hans"] == "https://www.bustago.or.kr/newweb/cn/index.do"
    assert book["https://www.foresttrip.go.kr/indvz/main.do?hmpgId=0301"] == {
        "k": "forest", "p": {}, "l": {"https://www.foresttrip.go.kr/indvz/main.do?hmpgId=0301": "ko"}}
    assert book["http://www.ramadagunsan.com/view/index.do"] == {"k": "reservationurl", "p": {}}
    assert not any(h in u for u in book for h in ("airbnb", "naver", "vercel.app"))
    assert set(book) <= set(real["docs"]["ext"]) and len(book) == 10
    assert "공식 예약 페이지 링크만 단다" in docs["/about/"]["x"]


def test_month_ranges_name_both_months(real):
    """Review 2026-10-17 L08: '3~10월 09:00~18:00' was answered in Spanish as '3–10 de octubre'. The knowledge names
    both months ('3월~10월'); dates, days and ranges already written in full stay as they are."""
    assert chat_index.month_ranges("3~10월 09:00~18:00 / 11~2월 09:00~17:00") == "3월~10월 09:00~18:00 / 11월~2월 09:00~17:00"
    for same in ("6월~10월", "매월 1~3일", "2026.3~10월", "10.3~10.10"):
        assert chat_index.month_ranges(same) == same
    x = real["docs"]["docs"]["/places/근대역사박물관/"]["x"]
    assert "3월~10월 09:00~18:00(입장마감 17:30) / 11월~2월 09:00~17:00(입장마감 16:30)" in x
    for text in (real["catalog"], *_full(real).values()):
        assert not re.search(r"(?<![\d.\-/월])\d{1,2}~\d{1,2}월", text)


def test_names_on_the_other_versions_find_the_page(real):
    """Review 2026-10-17 E03: the eight versions' names of a place are title words of its doc, so '群山近代歴史博物館',
    '仙遊島' or the Russian name rank the page first (they used to fall below the top 8)."""
    import subprocess
    docs = real["docs"]["docs"]
    queries = []
    for path in ("/places/근대역사박물관/", "/places/선유도/"):
        for lang, name in sorted((docs[path].get("n") or {}).items()):
            queries.append([path, lang, name])
    assert len(queries) >= 14
    script = (
        "import { loadKnowledge } from './chatbot/knowledge.js';"
        f"const k = await loadKnowledge({json.dumps(str(real['dir']))});"
        f"const qs = {json.dumps(queries, ensure_ascii=False)};"
        "console.log(JSON.stringify(qs.map(([p, l, q]) => [p, l, q, k.search(q, { limit: 3 }).map((h) => h.key)])));"
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True)
    for path, lang, name, top in json.loads(out.stdout):
        assert path in top, (lang, name, top)


def test_the_access_route_carries_every_source_s_words(real):
    """Round-6 verifier: a second source's access route (marked 'also' — not contradicting) was left out of the planner's
    data, so a disagreement between sources was never shown. Every route value of a place is in its f.ac."""
    S, docs = real["S"], real["docs"]["docs"]
    seen = 0
    for e in S.entities:
        row = B.fact_row(e, "accessible_route")
        if not row:
            continue
        want = ([row["value"]] if row["value"] else []) + [a["value"] for a in row["alternatives"]]
        got = [a["t"] for a in (docs[e["_path"]].get("f") or {}).get("ac", []) if a["k"] == "accessible_route"]
        assert len(got) == len(want), e["id"]
        seen += len(want) > 1
    assert seen >= 1   # 3.1운동 100주년 기념관: 군산시 and TourAPI


def test_a_place_whose_inside_is_not_open_is_flagged_from_its_own_data_only(real):
    """Outside tester 2026-10-23: 구 제일사료주식회사 공장 went in a course as a 30-minute stop whose card said '내부 관람
    불가' while the planner only said its hours could not be read. The planner's data (f.ex) says so now, read with a
    conservative pattern from the place's own fact values (every source's) and FAQ answers — never the TourAPI overview
    (제일사료's '내부는 둘러볼 수 없다') or the 군산시 original. On the real data: the factory and 히로쓰가옥 (외부·정원만),
    no museum, nothing else."""
    docs = real["docs"]["docs"]
    flagged = {k: d["f"]["ex"] for k, d in docs.items() if (d.get("f") or {}).get("ex")}
    assert flagged == {
        "/places/구-제일사료주식회사-공장/": [{"p": "한국관광공사 TourAPI", "w": "내부 관람 불가"}],
        "/places/군산신흥동일본식가옥/": [{"p": "군산시 문화관광", "w": "외부,정원만 관람"},
                                   {"p": "한국관광공사 TourAPI", "w": "실내 개방은 하지 않"},
                                   {"p": "군산시 문화관광", "w": "실내는 공개하지 않"}]}
    assert "ex" not in docs["/places/근대역사박물관/"]["f"] and "ex" not in docs["/places/이당미술관/"]["f"]
    # the words are the place's own data, found again where the planner reads its hours
    assert any("내부 관람 불가" in h["t"] for h in docs["/places/구-제일사료주식회사-공장/"]["f"]["h"])
    # never from the overview or the 군산시 original: with only those saying so, nothing is flagged
    e = next(x for x in real["S"].entities if x["_path"] == "/places/구-제일사료주식회사-공장/")
    assert "내부는 둘러볼 수 없다" in e["tourapi"]["overview"]
    bare = {**e, "facts": {k: v for k, v in e["facts"].items() if k != "usetime"}, "fact_sources": {}, "faq": []}
    assert chat_index.outside_only(bare) == []


@pytest.mark.parametrize("text,hit", [
    ("내부 관람 불가 ※ 자세한 사항은 전화 문의 요망", "내부 관람 불가"),
    ("구 제일사료주식회사 공장은 내부 관람이 되지 않습니다.", "내부 관람이 되지 않"),
    ("10:00~17:00  외부,정원만 관람 가능", "외부,정원만 관람"),
    ("※ 문화유산 보호를 위하여 실내 개방은 하지 않음", "실내 개방은 하지 않"),
    ("실내는 공개하지 않고 바깥과 정원만 관람할 수 있으며", "실내는 공개하지 않"),
    ("바깥과 정원만 관람할 수 있습니다", "바깥과 정원만 관람"),
    ("건물은 외관만 볼 수 있습니다", "외관만 볼 수"),
    ("외부에서만 관람 가능", "외부에서만 관람"),
    ("내부는 관람할 수 없습니다", "내부는 관람할 수 없"),
    # near misses on the real data and the like: a building's inside described, an exhibition in the building, works
    # inside, a ship's inside with models in it, an outer wall, a pet kept out, what is left after a fire — none says
    # visitors see only the outside
    ("구조는 철근콘크리트와 시멘트벽돌을 섞어 썼고, 내부는 저장·가공·출하 공간으로 나뉘어 있습니다.", None),
    ("4층 건물인 영화빌딩을 고쳐 만든 미술관이어서 건물 안에서 관람합니다.", None),
    ("2000년부터 전시실 내부와 조경 공사를 거쳐 문을 열었습니다.", None),
    ("위봉함 내부 3,288㎡(지하 2층, 지상 4층)에 병영생활 모습을 재현한 모형", None),
    ("용마루는 일직선이며 바깥벽에 창이 많습니다.", None),
    ("건물 안의 전시·체험 공간입니다.", None),
    ("건물 안은 리모델링으로 새로 꾸몄지만, 겉모습은 오래된 거리와 어울리도록", None),
    ("반려동물 실내 입장 불가", None),
    ("화재로 외관만 남아 있다", None),
])
def test_the_inside_not_open_pattern_is_conservative(text, hit):
    m = chat_index.OUTSIDE_ONLY.search(text)
    assert (m.group(0) if m else None) == hit
