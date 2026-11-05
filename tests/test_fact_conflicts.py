"""Operator decision 2026-11-05 ('출처 마다 다른 값은 대표 값 하나만 보이도록 해'; the first site's 2026-10-31 decision, as
부평시장각 2026-10-30, ported from its tests): with site.json fact_conflicts 'primary' a place keeps its main value alone — the other sources' differing values leave the record
before the build reads it (pipeline.textutil.keep_primary_facts), so no page, card or chat document says '출처마다 다름'.
Without the key the engine keeps both values side by side."""
import json
import shutil
from pathlib import Path

from pipeline.build import build
from pipeline.textutil import keep_primary_facts

ROOT = Path(__file__).resolve().parent.parent


def test_the_main_value_stays_alone():
    recs = [{"id": "a", "facts": {"usetime": "08:00~21:00", "tel": "1"}, "fact_sources": {"usetime": {"provider": "인천투어"}},
             "fact_alternatives": {"usetime": [{"value": "※ 점포별 상이함", "provider": "TourAPI"},
                                               {"value": "05:00~21:00", "provider": "부평구"}],
                                   "tel": [{"value": "2", "provider": "TourAPI", "relation": "also"}]}},
            # a main value that is only a note gives way to the other source's value, with that source
            {"id": "b", "facts": {"restdate": "※ 점포별 상이함"}, "fact_sources": {"restdate": {"provider": "TourAPI"}},
             "fact_alternatives": {"restdate": [{"value": "연중무휴", "provider": "인천투어", "url": "https://x/"}]}},
            # no main value: the first other value leads
            {"id": "c", "facts": {}, "fact_alternatives": {"parking": [{"value": "있음", "provider": "X"},
                                                                       {"value": "없음", "provider": "Y"}]}}]
    aside = keep_primary_facts(recs)
    assert [(r["id"], r["value"]) for r in aside] == [("a", "※ 점포별 상이함"), ("a", "05:00~21:00"), ("b", "※ 점포별 상이함"),
                                                       ("c", "없음")]
    a, b, c = recs
    assert a["facts"]["usetime"] == "08:00~21:00" and a["fact_alternatives"] == {"tel": [{"value": "2", "provider": "TourAPI",
                                                                                          "relation": "also"}]}
    assert b["facts"]["restdate"] == "연중무휴" and b["fact_sources"]["restdate"] == {"provider": "인천투어", "url": "https://x/"}
    assert "fact_alternatives" not in b and c["facts"]["parking"] == "있음" and c["fact_sources"]["parking"] == {"provider": "X"}


def _build(tmp_path, primary: bool):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    if primary:
        site["fact_conflicts"] = "primary"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = next(x for x in places if x["slug"] == "chowon-photo-studio")
    p["fact_alternatives"] = {"usetime": [{"value": "11:00~19:00", "provider": "한국관광공사 TourAPI", "checked_at": "2026-10-29"}]}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    page = (out / "places" / p["slug"] / "index.html").read_text("utf-8")
    doc = json.loads((out / "chat" / "docs.json").read_text("utf-8"))["docs"][f"/places/{p['slug']}/"]["x"]
    return page, doc, p["facts"]["usetime"]


def test_a_primary_site_shows_one_value_and_the_engine_default_shows_both(tmp_path):
    other = "11:00–19:00"   # the page writes a time range with an en dash
    page, doc, main = _build(tmp_path / "one", True)
    assert main in page and other not in page and "출처마다 다름" not in page
    assert "11:00" not in doc and "다른 출처 값" not in doc
    page, doc, main = _build(tmp_path / "both", False)
    assert main in page and other in page and "출처마다 다름" in page and "11:00" in doc


def test_a_value_with_a_shop_note_is_not_only_a_note():
    """'[칠성시장] 연중무휴 (단, 점포 별로 상이할 수 있음) [칠성야시장] 매주 화요일~수요일' names days: it stays the main value
    (textutil._note_only); a bare '점포마다 상이' gives way."""
    recs = [{"id": "m", "facts": {"restdate": "[칠성시장]\n- 연중무휴 (단, 점포 별로 상이할 수 있음)\n[칠성야시장]\n- 매주 화요일~수요일"},
             "fact_alternatives": {"restdate": [{"value": "[칠성종합시장] 매달 1, 3주차 일요일 휴무", "provider": "X"}]}},
            {"id": "n", "facts": {"usetime": "점포마다 상이"},
             "fact_alternatives": {"usetime": [{"value": "09:00~18:00", "provider": "Y"}]}}]
    keep_primary_facts(recs)
    assert recs[0]["facts"]["restdate"].startswith("[칠성시장]") and "fact_alternatives" not in recs[0]
    assert recs[1]["facts"]["usetime"] == "09:00~18:00"


def test_this_site_shows_one_value_and_its_prose_says_no_source_differs():
    """data/suwon/site.json fact_conflicts is 'primary' (operator 2026-11-05), and the Korean prose of places, guides and
    courses no longer says the sources differ ('출처마다 달라 … 방문 전 전화 확인'): it states the representative value."""
    import re
    site = json.loads((ROOT / "data" / "suwon" / "site.json").read_text("utf-8"))
    assert site.get("fact_conflicts") == "primary"
    pat = re.compile(r"출처마다 (?:달라|다름|다릅니다)|출처에 따라 .{0,60}달라|두 안내가 달라|(?:목록|자료)의? [^.]{0,30}값이 달라 방문 전")
    found = []
    for name in ("places", "guides", "courses"):
        for rec in json.loads((ROOT / "data" / "suwon" / f"{name}.json").read_text("utf-8")):
            def walk(o, path):
                if isinstance(o, str):
                    if pat.search(o) and "corrections" not in path:
                        found.append((name, rec.get("id"), path))
                elif isinstance(o, dict):
                    for k, v in o.items():
                        walk(v, f"{path}.{k}")
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        walk(v, f"{path}[{i}]")
            walk(rec, "")
    assert found == []
