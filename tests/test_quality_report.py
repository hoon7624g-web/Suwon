"""tools/quality_report.py — counts only what is shown, flags thin pages and hygiene issues."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from pipeline import city as citymod
from pipeline import schema

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("quality_report", ROOT / "tools" / "quality_report.py")
qr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr)


def shown(data: Path, out: Path, places: list[dict], site: Path) -> None:
    """Write places.json, copy a site.json and make each place's page exist in the build output."""
    data.mkdir()
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    shutil.copyfile(site, data / "site.json")
    for p in places:
        if p["slug"] != "hidden":
            (out / "places" / p["slug"]).mkdir(parents=True)
            (out / "places" / p["slug"] / "index.html").write_text("<html></html>", "utf-8")


def test_report_counts_shown_pages_and_flags(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    places = [
        {"slug": "a", "name": "가게", "kind": "food", "status": "draft", "summary": "가게는 군산시 신창동에 있는 한식 음식점입니다.",
         "facts": {"address": "전북특별자치도  군산시 구영3길 70  70", "menu": "꽃게장"}, "images": []},
        {"slug": "b", "name": "박물관", "kind": "attraction", "status": "draft", "summary": "박물관은 근대 전시관입니다. 월요일에 쉽니다.",
         "facts": {"address": "군산시 해망로 240", "usetime": "09:00~18:00", "restdate": "월요일", "infocenter": "063-000-0000"},
         "images": [{"license": "KOGL-1"}], "geo": {"lat": 1, "lng": 2},
         "faq": [{"q": "무료로 들어갈 수 있나요?", "a": "-"}, {"q": "주차 돼?", "a": "-"}]},
        {"slug": "hidden", "name": "아리랑 코스", "kind": "attraction", "status": "draft", "facts": {}},
    ]
    shown(data, out, places, ROOT / "data" / "sample" / "site.json")    # the sample city: 전북특별자치도 군산시
    rep = qr.analyse(data, out, "2026-10-08")
    assert rep["shown_places"] == 2 and rep["data_places"] == 3
    food, attr = rep["kinds"]["food"], rep["kinds"]["attraction"]
    assert food["summary_tautology_first"] == 1 and food["thin"] == 1        # 상투구 한 문장 + 실용 정보 부족
    assert attr["phone"] == 1 and attr["photo"] == 1 and attr["thin"] == 0
    assert rep["hygiene"]["address_multiple_spaces"] == 1 and rep["hygiene"]["address_repeated_number"] == 1
    assert not {k for k in rep["hygiene"] if k in qr.ADDRESS_CHECKS}        # both addresses name the city ('군산시 …' too)
    assert rep["faq"]["style"] == {"존댓말": 1, "반말": 1}
    assert "suspected_non_place" not in rep["hygiene"]                      # 화면에 없는 장소는 세지 않는다
    md = qr.to_md(rep)
    assert "| food |" in md and schema.INDEX_REASONS["taut"] in md


def test_stock_sentence_is_the_index_rule_of_the_configured_city(tmp_path):
    """The report judges the first sentence with schema.summary_problems(…, city=…) — the same City.taut_rx as the
    production index — so a 구·군-level stock sentence counts in a metropolitan city, and a sentence that only names
    the short city name does not."""
    data, out = tmp_path / "data", tmp_path / "out"
    stock = "식당은 대구광역시 중구 삼덕동1가에 있는 한식 음식점입니다."
    places = [
        {"slug": "a", "name": "식당", "kind": "food", "summary": stock, "facts": {"address": "대구광역시 중구 샘플로 1"}},
        {"slug": "b", "name": "가게", "kind": "food", "summary": "가게는 중구 샘플로에 있는 분식집입니다.",
         "facts": {"address": "대구광역시 중구 샘플로 2"}},
        {"slug": "c", "name": "밥집", "kind": "food", "summary": "밥집은 대구에서 아침 7시에 문을 여는 국밥집입니다.",
         "facts": {"address": "대구광역시 중구 샘플로 3"}},
    ]
    site = ROOT / "tests" / "fixtures" / "metro" / "site.json"
    shown(data, out, places, site)
    rep = qr.analyse(data, out, "2026-10-20")
    assert rep["kinds"]["food"]["summary_tautology_first"] == 2
    metro = citymod.from_site(json.loads(site.read_text("utf-8")))
    assert [("taut" in schema.summary_problems(p, city=metro)) for p in places] == [True, True, False]


def test_address_hygiene_items_for_a_metropolitan_city(tmp_path):
    """Report items, not build failures: no 구·군 (districts configured), an address outside the city, a legacy 시·도
    name the page shows renamed. A short alias ('OO 동구 …') is the city."""
    data, out = tmp_path / "data", tmp_path / "out"
    place = lambda slug, address: {"slug": slug, "name": f"[샘플] {slug}", "kind": "attraction", "summary": "",
                                   "facts": {"address": address}}
    places = [place("full", "대구광역시 중구 샘플로2길 80 (삼덕동1가)"), place("alias", "대구 동구 샘플길 5"),
              place("no-district", "대구광역시 샘플대로 9"), place("legacy", "경상북도 군위군 효령면 예시길 3"),
              place("outside", "서울특별시 종로구 샘플로 1"), place("no-prefix", "중구 샘플로 7"), place("empty", "")]
    shown(data, out, places, ROOT / "tests" / "fixtures" / "metro" / "site.json")
    rep = qr.analyse(data, out, "2026-10-20")
    h, samples = rep["hygiene"], rep["samples"]
    assert (h["address_no_district"], h["address_legacy_prefix"], h["address_outside_city"]) == (1, 1, 2)
    assert samples["address_no_district"] == ["[샘플] no-district: 대구광역시 샘플대로 9"]
    assert samples["address_legacy_prefix"] == ["[샘플] legacy: 경상북도 군위군 효령면 예시길 3"]
    assert samples["address_outside_city"] == ["[샘플] outside: 서울특별시 종로구 샘플로 1", "[샘플] no-prefix: 중구 샘플로 7"]
    md = qr.to_md(rep)
    assert "주소 점검(보고 항목, 빌드를 막지 않음)" in md and "address_no_district: 구·군이 없는 주소" in md
    assert qr.main(["--data", str(data), "--out", str(out), "--json"]) == 0     # report items never fail the run


def test_sample_city_has_no_districts_to_check(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    places = [{"slug": "a", "name": "가", "kind": "food", "facts": {"address": "전북특별자치도 군산시 샘플로 1"}},
              {"slug": "b", "name": "나", "kind": "food", "facts": {"address": "전라북도 군산시 샘플로 2"}}]
    shown(data, out, places, ROOT / "data" / "sample" / "site.json")
    h = qr.analyse(data, out, "2026-10-20")["hygiene"]
    assert "address_no_district" not in h and "address_outside_city" not in h
    assert h["address_legacy_prefix"] == 1                                  # '전라북도' is shown as 전북특별자치도


def test_data_and_a_city_config_are_required(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        qr.main(["--out", str(tmp_path)])
    assert exc.value.code == 2 and "--data" in capsys.readouterr().err
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "site.json").write_text("{}", "utf-8")
    with pytest.raises(SystemExit) as exc:
        qr.main(["--data", str(tmp_path / "data"), "--out", str(tmp_path)])
    assert exc.value.code == 2 and "site.json" in capsys.readouterr().err
