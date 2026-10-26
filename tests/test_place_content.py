"""tools/place_content.py: 작성자용 사실표(prepare), 기계 검사(check), 반영(merge).

The data folder is a tmp copy: a 구·군 city's site.json (tests/fixtures/metro, read, never written) and three fake '[샘플]' places. City words in
the sentences below come from that site.json (CITY.admin_line, CITY.districts), never from this file.
"""
import ast
import json
import shutil
from pathlib import Path

import pytest

from pipeline import city as citymod
from pipeline.schema import INDEX_REASONS
from tests import test_no_city_literals as literals
from tools import place_content as pc

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "tests" / "fixtures" / "metro" / "site.json"   # a 구·군 city config
CITY = citymod.of(json.loads(SITE.read_text("utf-8")))
ADMIN, GU = CITY.admin_line, CITY.districts[0]
PARK, FOOD, STAY = "[샘플] 한빛공원", "[샘플] 누리식당", "[샘플] 다온스테이"
TOUR = "한국관광공사 TourAPI"
HOME = "https://example.org/park"
OVERVIEW = (f"{PARK}은 2003년에 문을 연 도심 공원이다.\n\n공원 한가운데에   둥근 분수대 세 곳과 산책로가 있고 "
            "오래된 느티나무 그늘 아래 의자가 놓여 있다.")
SHARED_Q = f"{STAY}에서 {PARK}까지 걸어갈 수 있나요?"   # already on the stay page (places.json)


def src(provider: str = TOUR, **extra) -> dict:
    return {"provider": provider, "checked_at": "2026-10-10", **extra}


def places() -> list[dict]:
    park = {
        "id": "sample-park", "slug": "sample-park", "name": PARK, "kind": "attraction", "category": "관광지",
        "status": "draft", "summary": "",
        "facts": {"address": f"{ADMIN} {GU} 동성로2길 80 (공평동)", "usetime": "10:00~17:00", "restdate": "매주 월요일",
                  "usefee": "무료", "parking": "가능", "infocenter": "053-111-2222"},
        "facts_source": src(),
        "fact_sources": {"usetime": src("[샘플] 공원 홈페이지", url=HOME)},
        "fact_alternatives": {"usetime": [{"value": "09:00~18:00", **src()}]},
        "tourapi": {"contentid": "900001", "title": PARK, "overview": OVERVIEW},
        "nearby": [{"name": FOOD, "kind": "food", "distance_m": 120}],
    }
    food = {
        "id": "sample-food", "slug": "sample-food", "name": FOOD, "kind": "food", "category": "한식",
        "status": "published", "reviewed_at": "2026-10-01", "approved_at": "2026-10-02",
        "summary": f"{FOOD}은 음식점입니다.", "summary_auto": True,
        "facts": {"address": f"{ADMIN} {GU} 동성로2길 90 (공평동)", "menu": "비빔밥", "usetime": "11:00~21:00"},
        "facts_source": src(), "tourapi": {"contentid": "900002", "title": FOOD, "overview": f"{FOOD}은 비빔밥을 낸다."},
    }
    stay = {
        "id": "sample-stay", "slug": "sample-stay", "name": STAY, "kind": "stay", "category": "게스트하우스",
        "status": "draft", "summary": f"{STAY}는 공평동 골목 안쪽의 숙소입니다.",
        "facts": {"address": f"{ADMIN} {GU} 동성로2길 99 (공평동)", "homepage": "https://example.org/stay"},
        "facts_source": src(), "tourapi": {"contentid": "900003", "title": STAY, "overview": f"{STAY}는 골목 안의 숙소다."},
        "faq": [{"q": SHARED_Q, "a": "두 곳 모두 공평동에 있습니다.", "source": TOUR}],
    }
    return [park, food, stay]


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


@pytest.fixture
def data(tmp_path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy(SITE, d / "site.json")
    write(d / "places.json", places())
    write(d / "events.json", [{"id": "ev1", "name": "[샘플] 분수 음악회", "place_name": f"{PARK} 야외무대",
                               "address": "", "start_date": "2026-11-01", "end_date": "2026-11-02"}])
    return d


def prepared(data: Path, *ids: str) -> Path:
    """Fact sheets for the given ids (all three by default) in data/../work; returns that folder."""
    work = data.parent / "work"
    only = data.parent / "only.txt"
    only.write_text("\n".join(ids or ("sample-park", "sample-food", "sample-stay")), "utf-8")
    pc.prepare(data, work, 12, pc.read_only_list(only))
    return work


def output(work: Path, *items: dict, name: str = "batch.output.json") -> Path:
    path = work / name
    write(path, {"items": list(items)})
    return path


def issues_of(data: Path, *items: dict) -> dict:
    rep = pc.review([output(prepared(data), *items)], data=data)
    return {r["id"]: r["issues"] for r in rep["rows"]}


def faq(q: str, a: str = "주차할 수 있습니다.", source: str = HOME) -> dict:
    return {"q": q, "a": a, "source": source}


CLEAN_PARK = {"id": "sample-park", "summary": f"{PARK}은 매주 월요일에 쉬고 입장료는 무료입니다. 분수대 세 곳과 산책로가 있습니다.",
              "faq": [faq(f"{PARK}은 주차할 수 있나요?")]}
CLEAN_FOOD = {"id": "sample-food", "summary": f"{FOOD}은 비빔밥을 내는 음식점으로 11:00~21:00에 엽니다.",
              "faq": [faq(f"{FOOD}의 대표 메뉴는 무엇인가요?", "비빔밥입니다.", TOUR)]}
THIN_STAY = {"id": "sample-stay", "summary": f"{STAY}는 공평동 골목의 숙소입니다.", "thin": True}


# ------------------------------------------------------------------ prepare
def test_prepare_picks_places_without_a_usable_summary_and_writes_fact_sheets(data, tmp_path):
    work = tmp_path / "work"
    res = pc.prepare(data, work, batch=1)
    assert res == {"places": 2, "batches": 2, "out": str(work), "unknown": [], "skipped": []}
    assert sorted(p.name for p in work.iterdir()) == ["places-01.input.json", "places-02.input.json"]
    docs = [json.loads((work / f"places-0{n}.input.json").read_text("utf-8")) for n in (1, 2)]
    assert [d["items"][0]["id"] for d in docs] == ["sample-park", "sample-food"]   # the stay's summary is fine
    doc = docs[0]
    assert set(doc) == {"rules", "output_example", "items"}
    rules = " ".join(doc["rules"])
    assert "source_text" in rules and "옮기지 않는다" in rules and "15자" in rules and "~나요?/~인가요?" in rules
    assert f"'○○은 {ADMIN} ○○에 있는 ○○입니다'" in rules
    sheet = doc["items"][0]
    assert set(sheet) == {"id", "slug", "name", "kind", "category", "district", "area", "road", "alternate_names",
                          "tourapi_title", "facts", "source_text", "nearby", "events", "current_summary",
                          "current_faq", "faq_sources"}
    assert (sheet["district"], sheet["area"], sheet["road"]) == (GU, "공평동", "동성로2길")
    rows = {r["key"]: r for r in sheet["facts"]}
    assert rows["usetime"] == {"key": "usetime", "label": "이용시간", "value": "10:00~17:00",
                               "provider": "[샘플] 공원 홈페이지", "checked_at": "2026-10-10", "url": HOME,
                               "differs_from": [{"value": "09:00~18:00", "provider": TOUR}]}
    assert rows["usefee"]["label"] == "이용요금" and rows["usefee"]["provider"] == TOUR
    assert "  " not in sheet["source_text"] and "\n" not in sheet["source_text"]
    assert sheet["faq_sources"] == [TOUR, HOME]
    assert sheet["nearby"] == [FOOD]
    assert [e["name"] for e in sheet["events"]] == ["[샘플] 분수 음악회"]
    assert docs[1]["items"][0]["current_summary"] == f"{FOOD}은 음식점입니다."


def test_prepare_only_list_truncates_source_text_and_replaces_old_inputs(data, tmp_path):
    work = tmp_path / "work"
    pc.prepare(data, work, batch=1)
    only = tmp_path / "only.json"
    only.write_text(json.dumps(["sample-stay", "no-such-place"]), "utf-8")
    assert pc.main(["prepare", "--data", str(data), "--out", str(work), "--only", str(only)]) == 0
    assert sorted(p.name for p in work.iterdir()) == ["places-01.input.json"]     # old batches removed
    items = json.loads((work / "places-01.input.json").read_text("utf-8"))["items"]
    assert [i["id"] for i in items] == ["sample-stay"] and items[0]["current_faq"][0]["q"] == SHARED_Q
    long = {**places()[0], "tourapi": {"overview": "가 나\n" * 4000}}
    assert len(pc.fact_sheet(long, city=CITY)["source_text"]) == pc.SOURCE_TEXT_MAX
    assert pc.read_only_list(tmp_path / "only.json") == ["sample-stay", "no-such-place"]
    text = tmp_path / "ids.txt"
    text.write_text("# 다시 쓸 곳\nsample-park, sample-food\n", "utf-8")
    assert pc.read_only_list(text) == ["sample-park", "sample-food"]


# ------------------------------------------------------------------ check
def test_clean_items_pass(data):
    assert issues_of(data, CLEAN_PARK, CLEAN_FOOD, THIN_STAY) == {"sample-park": [], "sample-food": [], "sample-stay": []}


def test_copy_of_15_or_more_characters_is_blocked_but_names_are_excepted(data):
    copied = {"id": "sample-park", "summary": f"{PARK}은 한가운데에 둥근 분수대 세 곳과 산책로가 있고 오래된 느티나무가 섰습니다."}
    found = issues_of(data, copied)["sample-park"]
    assert len(found) == 1 and "source_text 복사" in found[0] and "둥근 분수대 세 곳과 산책로가 있고" in found[0]
    named = {"id": "sample-park", "summary": f"{PARK}은 2003년에 문을 열었습니다."}   # shares '{PARK}은 2003년에 ' only
    assert issues_of(data, named)["sample-park"] == []
    # a long excepted span (a name) does not hide a shorter real copy elsewhere in the text
    name = "한빛누리다온공원관리사무소앞마당"
    source = f"{name}에서 출발하면 둘레길 입구가 보이고 표지판이 이어진다"
    text = f"{name}에서 출발합니다. 둘레길 입구가 보이고 표지판이 있습니다."
    assert "둘레길 입구가 보이고 표지판이" in pc._longest_copy(text, source, [name])
    assert pc._longest_copy(f"{name}에서 출발합니다.", source, [name]) == ""


def test_banned_wording_is_blocked_after_the_name_is_removed(data):
    found = issues_of(data, {"id": "sample-park", "summary": f"{PARK}은 인기 산책 공원으로 매주 월요일에 쉽니다."})
    assert [x for x in found["sample-park"] if "근거 없는 수식어" in x]
    found = issues_of(data, {"id": "sample-park", "summary": f"{PARK}의 요금은 확인이 필요합니다."})
    assert [x for x in found["sample-park"] if "'확인 필요' 문구" in x]
    assert pc._wording("[샘플] 낭만공원은 무료입니다.", ("[샘플] 낭만공원",)) == []
    assert pc._wording("[샘플] 낭만공원은 무료입니다.") != []


def test_stock_first_sentence_is_blocked(data):
    taut = f"summary 색인 규칙 위반: {INDEX_REASONS['taut']}"
    for summary in (f"{PARK}은 {ADMIN} {GU} 공평동에 있는 공원입니다.",
                    f"{PARK}은 {CITY.region} {CITY.districts[5]}에 위치한 도심 공원입니다.",
                    f"{PARK}은 {GU} 동성로2길에 있는 공원입니다. 매주 월요일에 쉽니다."):
        assert taut in issues_of(data, {"id": "sample-park", "summary": summary})["sample-park"], summary
    # the same sentence under the name without its bracket is caught too
    alias = issues_of(data, {"id": "sample-park", "summary": f"한빛공원은 {ADMIN} {GU}에 있는 공원입니다."})["sample-park"]
    assert any("첫 문장이 상투구('한빛공원'" in x for x in alias)
    # a first sentence that answers with a fact passes, even with the city in a later sentence
    ok = {"id": "sample-park", "summary": f"{PARK}은 분수대 세 곳이 있는 공원입니다. {ADMIN} {GU} 공평동에 있습니다."}
    assert issues_of(data, ok)["sample-park"] == []


def test_numbers_must_come_from_the_sheet(data):
    found = issues_of(data, {"id": "sample-park", "summary": f"{PARK}은 분수대 7곳이 있는 공원입니다.",
                             "faq": [faq(f"{PARK}은 주차할 수 있나요?", "주차면 45대가 있습니다.")]})["sample-park"]
    assert "summary 사실표에 없는 숫자 ['7']" in found
    assert "faq[0].a 사실표에 없는 숫자 ['45']" in found
    # values of the other source, the overview, the road and the phone are in the sheet
    ok = {"id": "sample-park", "summary": f"{PARK}은 2003년에 문을 연 공원으로 동성로2길 80에 있습니다.",
          "faq": [faq(f"{PARK}의 이용시간은 어떻게 되나요?",
                      "10:00~17:00과 09:00~18:00으로 출처마다 달라 방문 전 전화 확인(053-111-2222)이 좋습니다.")]}
    assert issues_of(data, ok)["sample-park"] == []


def test_summary_shape(data):
    found = issues_of(data, {"id": "sample-park", "summary": ""}, {"id": "sample-food", "summary": f"{FOOD}은 비빔밥집이에요"},
                      {"id": "sample-stay", "summary": " ".join(f"{STAY}는 숙소입니다." for _ in range(4))})
    assert found["sample-park"] == [f"summary 색인 규칙 위반: {INDEX_REASONS['no_summary']}"]
    assert any("'다.'로 끝나지 않음" in x for x in found["sample-food"])
    assert "summary는 1~3문장(지금 4문장)" in found["sample-stay"]


def test_faq_rules(data):
    found = issues_of(data, {**CLEAN_PARK, "faq": [faq(f"{PARK} 주차돼?"), faq("주차할 수 있나요?"),
                                                    faq(f"{PARK}은 무료인가요?", "무료입니다.", "https://blog.example.com/x"),
                                                    faq(f"{PARK}은 월요일에 쉬나요?", "쉽니다.")]})["sample-park"]
    assert any(x.startswith("faq[0].q 존댓말 의문형") for x in found)
    assert any(x.startswith("faq[1].q에 장소 이름이 없음") for x in found)
    assert any(x.startswith("faq[2].source는") for x in found)
    assert "관광지 FAQ는 3개 이하(지금 4개)" in found
    three = [faq(f"{FOOD}은 {w}인가요?", "비빔밥입니다.", TOUR) for w in ("한식집", "비빔밥집", "밥집")]
    assert "음식점 FAQ는 2개 이하(지금 3개)" in issues_of(data, {**CLEAN_FOOD, "faq": three})["sample-food"]
    assert issues_of(data, {**CLEAN_PARK, "faq": [faq(f"{PARK}은 {w} 있나요?") for w in ("주차장이", "의자가", "분수대가")]}) \
        == {"sample-park": []}


def test_a_question_is_not_repeated_across_places(data):
    shared = f"{PARK}과 {FOOD}은 같은 동네에 있나요?"
    found = issues_of(data, {**CLEAN_PARK, "faq": [faq(SHARED_Q, "두 곳 모두 공평동입니다.", TOUR)]},
                      {**CLEAN_FOOD, "faq": [faq(shared, "두 곳 모두 공평동입니다.", TOUR)]})
    assert found["sample-park"] == [f"같은 질문이 places.json의 sample-stay에 있음: {SHARED_Q}"]
    assert found["sample-food"] == []
    found = issues_of(data, {**CLEAN_PARK, "faq": [faq(shared, "두 곳 모두 공평동입니다.", TOUR)]},
                      {**CLEAN_FOOD, "faq": [faq(shared, "두 곳 모두 공평동입니다.", TOUR)]})
    assert found == {"sample-park": [], "sample-food": [f"같은 질문이 sample-park에도 있음: {shared}"]}
    # the stay may keep (or restate) its own question
    assert issues_of(data, {**THIN_STAY, "faq": [faq(SHARED_Q, "두 곳 모두 공평동입니다.", TOUR)]}) == {"sample-stay": []}


def test_ids_thin_and_cli(data, capsys):
    work = prepared(data, "sample-park")
    out = output(work, {**THIN_STAY}, {"id": "sample-park", "summary": f"{PARK}은 공원입니다.", "thin": True})
    found = {r["id"]: r["issues"] for r in pc.review([out], data=data)["rows"]}
    assert found["sample-stay"] == ["입력 사실표에 없는 id"]          # only the park was prepared
    assert any(x.startswith("thin 표시는") for x in found["sample-park"])  # the park has facts to write
    assert pc.main(["check", "--data", str(data), str(out)]) == 1
    assert "sample-stay 입력 사실표에 없는 id" in capsys.readouterr().out
    clean = output(work, CLEAN_PARK, name="places-01.output.json")
    assert pc.main(["check", "--data", str(data), str(clean), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    with pytest.raises(SystemExit):
        pc.main(["check", str(clean)])                                     # --data is required


# ------------------------------------------------------------------ merge
def test_merge_applies_only_clean_items_and_never_touches_status(data, capsys):
    before = (data / "places.json").read_bytes()
    bad_food = {**CLEAN_FOOD, "summary": f"{FOOD}은 인기 비빔밥집입니다."}
    out = output(prepared(data), CLEAN_PARK, bad_food, THIN_STAY)
    assert pc.main(["merge", "--data", str(data), str(out), "--dry-run"]) == 1
    res = json.loads(capsys.readouterr().out)
    assert (res["dry_run"], res["merged"], res["refused"], res["written"]) == (True, 2, 1, None)
    assert (data / "places.json").read_bytes() == before

    res = pc.merge([out], data=data)
    assert (res["merged"], res["refused"], res["faq"], res["thin"]) == (2, 1, 1, 1)
    assert res["refused_items"][0]["id"] == "sample-food" and res["merged_ids"] == ["sample-park", "sample-stay"]
    old = {p["id"]: p for p in places()}
    new = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    assert new["sample-park"]["summary"] == CLEAN_PARK["summary"] and new["sample-park"]["faq"] == CLEAN_PARK["faq"]
    assert new["sample-food"] == old["sample-food"]                          # refused: untouched
    assert new["sample-stay"]["summary_thin"] is True and new["sample-stay"]["faq"] == old["sample-stay"]["faq"]
    for pid in old:   # nothing but summary / faq / summary_* changes, and status never
        changed = {k for k in {*old[pid], *new[pid]} if old[pid].get(k) != new[pid].get(k)}
        assert changed <= {"summary", "faq", "summary_auto", "summary_thin"}, (pid, changed)
    assert not list(data.glob(".*.tmp"))                                     # written via a temp file + replace

    res = pc.merge([output(data.parent / "work", CLEAN_FOOD)], data=data)
    food = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}["sample-food"]
    assert res["merged_ids"] == ["sample-food"] and res["after_review"] == ["sample-food"]
    assert "summary_auto" not in food and food["summary"] == CLEAN_FOOD["summary"]
    assert (food["status"], food["reviewed_at"], food["approved_at"], food["slug"]) == \
        ("published", "2026-10-01", "2026-10-02", "sample-food")


def test_merge_writes_nothing_when_places_json_changed_meanwhile(data, monkeypatch):
    out = output(prepared(data), CLEAN_PARK)
    real = pc.review

    def review_then_someone_writes(*args, **kwargs):
        rep = real(*args, **kwargs)
        write(data / "places.json", places() + [{"id": "new", "name": "새 장소", "kind": "food", "status": "draft"}])
        return rep

    monkeypatch.setattr(pc, "review", review_then_someone_writes)
    with pytest.raises(SystemExit, match="바뀌었습니다"):
        pc.merge([out], data=data)
    assert [p["id"] for p in json.loads((data / "places.json").read_text("utf-8"))][-1] == "new"


def test_the_tool_names_no_city():
    path = ROOT / "tools" / "place_content.py"
    consts = [(f"{path.name}:{n.lineno}", n.value) for n in ast.walk(ast.parse(path.read_text("utf-8")))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    patterns = [getattr(literals, n) for n in dir(literals) if n.endswith("_RX")]   # the first city's, Daegu's and this one's
    assert len(consts) > 50 and len(patterns) == 3
    assert [h for rx in patterns for h in literals.hits(rx, consts)] == []
