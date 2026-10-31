"""영업 확인 (licenses.json) and 이어서 많이 간 곳 (related.json) on the place page, every language (present.license_vm,
related_vm / related_places; operator 2026-10-31). A '영업' licence prints one line in 방문 전 확인 with its source; a
식품안심업소 designation prints while it is valid, never as a grade; '폐업 확인' prints nothing. The related places are the
built ones in rank order, at most 8, described as movement data (TMAP), never as a recommendation. The chatbot's document
and llms-full carry the same. The data files are written in a temporary folder (never into data/gunsan)."""
import json
import re
import types

from pipeline import build as B
from pipeline import locales as LC
from pipeline import present as P
from pipeline.validate import visible_check_dates

HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")
LICENSES = {
    "sources": {"general_restaurants": {"provider": "행정안전부", "dataset": "행정안전부_식품_일반음식점 조회서비스",
                                        "url": "https://www.data.go.kr/data/15154916/openapi.do"},
                "hygiene": {"provider": "식품의약품안전처",
                            "dataset": "식품의약품안전처_식품접객업소 식품안심업소(위생등급) 지정 현황",
                            "url": "https://www.data.go.kr/data/15060883/openapi.do"}},
    "places": {
        "f1": {"status": "영업", "kind": "일반음식점", "kind_detail": "한식", "name": "가게 군산점", "licensed_at": "2022-05-24",
               "tel": "070-0000-0000", "source": "general_restaurants",
               "hygiene": {"level": "적합", "valid_from": "2025-06-19", "valid_to": "2028-06-18",
                           "designated_by": "식품의약품안전처"}},
        "f2": {"status": "영업", "kind": "일반음식점", "kind_detail": "", "source": "general_restaurants",
               "hygiene": {"level": "적합", "valid_from": "2020-01-01", "valid_to": "2023-01-01",
                           "designated_by": "식품의약품안전처"}},
        "f3": {"status": "폐업 확인", "kind": "일반음식점", "source": "general_restaurants"}}}


def state(tmp_path, places=()):
    (tmp_path / "licenses.json").write_text(json.dumps(LICENSES, ensure_ascii=False), "utf-8")
    related = {"source": {"provider": "한국관광공사", "base_date": "2026-09", "url": "https://www.data.go.kr/data/15128560/openapi.do"},
               "base_ym": "202609",
               "places": {"a1": [{"rank": 3, "name": "C", "place_id": "c"}, {"rank": 1, "name": "B", "place_id": "b"},
                                 {"rank": 2, "name": "없는 곳", "place_id": None}, {"rank": 4, "name": "A", "place_id": "a1"},
                                 *({"rank": 10 + k, "name": f"x{k}", "place_id": f"x{k}"} for k in range(10))]}}
    (tmp_path / "related.json").write_text(json.dumps(related, ensure_ascii=False), "utf-8")
    ents = list(places)
    return types.SimpleNamespace(today="2026-10-31", licenses=B._load(tmp_path / "licenses.json", {}),
                                 related_trips=B._load(tmp_path / "related.json", {}),
                                 entities=ents, ent_by_id={x["id"]: x for x in ents})


def test_license_line_and_valid_designation(tmp_path):
    S = state(tmp_path)
    b = P.license_vm(S, {"id": "f1"})
    assert (b["open"], b["by"]) == ("영업 중", "행정안전부 인허가(일반음식점·한식)")
    assert b["safe"] == "식품안심업소 지정(식약처, 2025-06-19~2028-06-18)"
    assert [x["name"] for x in b["sources"]] == ["행정안전부 식품 일반음식점 조회서비스",
                                                 "식품의약품안전처 식품접객업소 식품안심업소(위생등급) 지정 현황"]
    text = " ".join([b["open"], b["by"], b["safe"]])
    assert "적합" not in text and "등급" not in text and "070" not in text and "2022-05-24" not in text
    assert not visible_check_dates(text)
    f2 = P.license_vm(S, {"id": "f2"})
    assert f2["by"] == "행정안전부 인허가(일반음식점)" and f2["safe"] == ""   # the designation ended in 2023
    assert P.license_vm(S, {"id": "f3"}) is None and P.license_vm(S, {"id": "nope"}) is None


def test_license_line_in_every_version(tmp_path):
    S = state(tmp_path)
    for code in LC.LICENSE_WORDS:
        if code == "ko":
            continue
        b = P.license_vm(S, {"id": "f1"}, code)
        assert b and b["safe"] and not HANGUL.search(json.dumps(b, ensure_ascii=False, default=str)), code
    assert P.license_vm(S, {"id": "f1"}, "en")["by"] == "Ministry of the Interior and Safety business licence (restaurant)"


def _place(pid):
    return {"id": pid, "name": pid.upper(), "kind": "attraction", "_path": f"/places/{pid}/", "_type": "", "_geo": None,
            "_photos": [], "facts": {}}


def test_related_places_rank_order_built_only_at_most_eight(tmp_path):
    ents = [_place(x) for x in ("a1", "b", "c", *(f"x{k}" for k in range(10)))]
    S = state(tmp_path, ents)
    got = [t["id"] for t in P.related_places(S, ents[0])]
    assert got == ["b", "c", "x0", "x1", "x2", "x3", "x4", "x5"]       # rank order, no unlinked row, never itself, 8
    assert P.related_ym(S.related_trips) == "2026년 9월" and P.related_ym(S.related_trips, "en") == "September 2026"
    vm = P.related_vm(S, ents[0])
    assert vm["title"] == "이어서 많이 간 곳" and [r["name"] for r in vm["rows"]][:2] == ["B", "C"]
    note = str(vm["note"])
    assert note.startswith("티맵 차량 이동 기준, 2026년 9월 · <a href=\"https://www.data.go.kr/data/15128560/openapi.do\"")
    assert "추천" not in note and P.related_vm(S, ents[1]) is None


def test_the_card_sits_before_the_facts_on_phones():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for tpl, v in (("place.html.j2", "p"), ("en/place.html.j2", "v")):
        s = (root / "templates" / tpl).read_text("utf-8")
        assert s.index(f"tdy.card({v}.today, nm)") < s.index('<section class="pl-side"') < s.index('<div class="pl-main">')
        assert f"{v}.biz.open" in s and f"{v}.went_next.rows" in s
    css = (root / "templates" / "assets" / "css" / "74-today.css").read_text("utf-8")
    assert ".pl-grid > .td { order: -2;" in css and ".pl-grid > .td ~ .pl-main { grid-row: 2; }" in css


def test_chat_and_llms_lines_on_the_real_data():
    """The chatbot's place document and llms-full carry both blocks (the real files, when present)."""
    from pathlib import Path
    data = Path(__file__).resolve().parent.parent / "data" / "suwon"
    if not (data / "licenses.json").exists() or not (data / "related.json").exists():
        return
    S = B.State(data, "preview")
    biz = next((e for e in S.entities if P.license_vm(S, e) and not e["_noindex"]), None)
    went = next((e for e in S.entities if P.related_places(S, e) and not e["_noindex"]), None)
    _, full = B.llms_txt(S)
    if biz:
        assert f"- 영업 확인: 영업 중 — " in full.split(f"## {biz['name']} (")[1].split("\n## ")[0]
    if went:
        part = full.split(f"## {went['name']} (")[1].split("\n## ")[0]
        assert "- 이어서 많이 간 곳(티맵 차량 이동 기준" in part and "추천 아님" in part
    from pipeline import chat_index
    K = chat_index.Knowledge(S)
    for e, needle in ((biz, "영업 확인: 영업 중 — "), (went, "이어서 많이 간 곳(티맵 차량 이동 기준")):
        if e:
            K.place_doc(e, "", "")
            assert needle in K.docs[e["_path"]]["x"]


def test_a_renamed_lodging_names_its_licensed_name_on_the_korean_page_only():
    """운영자 결정 2026-10-31 '이어': a lodging joined to its licence by address and phone (tools/mois_licenses_gunsan
    'address+tel') says the licensed name; a version that cannot write that name leaves the licence block out."""
    import types
    from pipeline import present
    S = types.SimpleNamespace(today="2026-10-31", licenses={
        "sources": {"lodgings": {"provider": "행정안전부", "dataset": "행정안전부_문화_숙박업 조회서비스",
                                 "url": "https://www.data.go.kr/data/15155124/openapi.do"}},
        "places": {"s1": {"status": "영업", "kind": "숙박업", "kind_detail": "", "name": "BB호텔", "source": "lodgings",
                          "match": "address+tel"}}})
    ko = present.license_vm(S, {"id": "s1", "name": "까사밀라모텔"}, "ko")
    assert ko and ko["licensed_name"] == "BB호텔"
    assert present.license_vm(S, {"id": "s1", "name": "까사밀라모텔"}, "en") is None
