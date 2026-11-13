"""Operator decision 2026-10-31 (군산각, '출처마다 다름 표시는 좀 안 보이면 좋겠는데' — as 부평시장각 2026-10-30): with site.json
fact_conflicts 'primary' a place keeps its main value alone — the other sources' differing values leave the record
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
