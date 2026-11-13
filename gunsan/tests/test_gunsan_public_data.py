"""2026-10-31 (운영자 '1번부터 모두 반영'): 군산각의 공공데이터 보강 — 시장 품목별 가게(tools/market_data_gunsan.py:
온누리 명부·상가정보·행정안전부 인허가), 반려동물 동반(tools/tourapi_pet.py), 관광지점 월별 관광객수
(tools/visitors_gunsan.py) — and how a place page shows them."""
import json
import shutil
from pathlib import Path

from pipeline import present
from pipeline.build import build
from tools import market_data_gunsan as M
from tools import tourapi_pet as PET
from tools import visitors_gunsan as V

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "gunsan"


def test_the_four_markets_get_their_shop_groups_and_only_shops_in_business():
    places = json.loads((ROOT / "data" / "gunsan" / "places.json").read_text("utf-8"))
    by = {p["id"]: p for p in places}
    assert set(M.MARKETS) <= set(by)
    rows = M.market_rows(RAW / "markets", "2026-10-31", M.market_points(ROOT / "data" / "gunsan"), by)
    for pid in M.MARKETS:
        shops = rows[pid]["shops"][0]
        assert shops["groups"] and int(shops["value"].split("곳")[0]) > 0
    # a 행안부 row that is not '영업/정상' never becomes a card
    closed = {M.norm_name(r["BPLC_NM"]) for f in (RAW / "licenses").glob("mois_*.csv") for r in M.read(f)
              if r["SALS_STTS_CD"] != "01"}
    open_ = {M.norm_name(r["BPLC_NM"]) for f in (RAW / "licenses").glob("mois_*.csv") for r in M.read(f)
             if r["SALS_STTS_CD"] == "01"}
    shown = {M.norm_name(x["name"]) for got in rows.values() for lc in (got.get("shops") or [{}])[0].get("licensed") or []
             if lc["source"]["provider"] == "행정안전부" for x in lc["rows"]}
    assert shown and not (shown & (closed - open_))
    # the city part of an address is dropped on cards; 상가정보 '구암31로' and 인허가 '구암3.1로' are one road
    assert M.road_key("전북특별자치도 군산시 구암3.1로 13-1 (대명동)") == M.road_key("전북특별자치도 군산시 구암31로 13-1")


def test_pet_values_keep_the_service_words_and_never_replace_another_source():
    detail = {"acmpyTypeCd": "일부구역 동반가능", "acmpyPsblCpam": "", "acmpyNeedMtr": "목줄 착용"}
    assert PET.pet_value(detail) == "동반 구분 일부구역 동반가능 · 동반 시 필요 사항 목줄 착용"
    place = {"facts": {}}
    assert PET.apply_pet(place, "동반 구분 전구역 동반가능", "1", "2026-10-31") == "set"
    assert place["fact_sources"]["pet"]["provider"] == PET.PROVIDER
    other = {"facts": {"pet": "불가"}, "fact_sources": {"pet": {"provider": "한국관광공사 TourAPI"}}}
    assert PET.apply_pet(other, "동반 구분 전구역 동반가능", "1", "2026-10-31") == "alt"
    assert other["facts"]["pet"] == "불가" and other["fact_alternatives"]["pet"][0]["value"] == "동반 구분 전구역 동반가능"
    assert PET.apply_pet(other, "동반 구분 전구역 동반가능", "1", "2026-10-31") == "same"


def test_monthly_visitors_take_the_latest_full_year_and_the_months_after_it():
    import csv
    rows = list(csv.DictReader(open(RAW / "visitors" / V.FILE, encoding="utf-8-sig")))
    v = V.visitors(rows, "선유도(고군산군도)")
    assert v["year"] == 2024 and len(v["months"]) == 12 and v["total"] == sum(v["months"])
    assert v["recent"]["year"] == 2025 and v["recent"]["through"] == 11
    assert V.visitors(rows, "없는 관광지") is None


def test_a_place_page_shows_shop_cards_and_monthly_visitors(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = places[0]
    p["market"] = {"shops": [{"value": "2곳", "provider": M.PROVIDER, "dataset": M.ONNURI["dataset"], "url": M.ONNURI["url"],
                              "checked_at": "2026-10-31", "base_date": "2026-07-31", "stalls": 0, "rows": 2,
                              "licensed": [{"group": "oil", "mode": "add", "rows": [{"name": "미면떡집", "kind": "즉석판매제조가공업",
                                                                                     "addr": "대명3길 38-8", "geo": [35.98, 126.72],
                                                                                     "tel": "063-446-9086"}],
                                            "source": {"provider": "행정안전부", "dataset": M.MOIS[0]["dataset"],
                                                       "url": M.MOIS[0]["url"], "base_date": "2026-10-30"}}],
                              "groups": [{"key": "oil", "label": "기름·방앗간·떡", "shops": [{"name": "골목떡집", "items": "떡"}]}]}]}
    months = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
    p["visitors"] = {"year": 2024, "months": months, "total": sum(months), "recent": {"year": 2025, "through": 11, "total": 999},
                     "source": V.SOURCE}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    html = (out / "places" / p["slug"] / "index.html").read_text("utf-8")
    assert 'data-block="shops"' in html and '<p class="sc-name">골목떡집</p>' in html and '<p class="sc-name">미면떡집</p>' in html
    assert 'href="tel:0634469086"' in html and "행정안전부 인허가 정보(즉석판매제조가공업)에서 영업 중으로 적히고" in html
    assert 'href="#h-shops"' in html   # the place's local nav
    assert 'data-block="visitors"' in html and "2024년 <b class=\"tn\">780명</b>" in html and "가장 많은 달 <b>12월</b>" in html
    assert "2025년 1~11월 <span class=\"tn\">999명</span>" in html and V.SOURCE["url"] in html
    vm = present.visitors_vm(p)
    assert vm["peak"] == {"m": 12, "n": 120} and vm["low"] == {"m": 1, "n": 10} and vm["bars"][11]["pct"] == 100
    docs = json.loads((out / "chat" / "docs.json").read_text("utf-8"))["docs"]
    doc = docs[f"/places/{p['slug']}/"]["x"]
    assert "미면떡집(대명3길 38-8 · 063-446-9086)" in doc and "월별 관광객(2024년" in doc


def test_a_gocamping_campsite_the_site_lacks_becomes_a_draft_with_the_services_values():
    c = {"contentId": "100545", "facltNm": "버드글램핑", "addr1": "전북 군산시 강변로 29 (금암동)", "addr2": "",
         "tel": "063-446-3355", "homepage": "https://birdglamping.modoo.at/", "operPdCl": "봄,여름,가을,겨울",
         "operDeCl": "평일+주말", "sbrsCl": "전기,무선인터넷", "sbrsEtc": "", "resveCl": "온라인실시간예약",
         "animalCmgCl": "가능", "induty": "글램핑", "glampSiteCo": "13", "gnrlSiteCo": "0",
         "glampInnerFclty": "침대,TV", "manageSttus": "운영", "modifiedtime": "2024-04-19",
         "mapX": "126.7268994", "mapY": "35.9857213", "firstImageUrl": "https://gocamping.or.kr/x.jpg"}
    p = PET.new_camp(c, "2026-10-31", {"버드글램핑"})
    assert p["id"] == "gocamping-100545" and p["status"] == "draft" and p["slug"] == "버드글램핑-2"
    assert p["images"] == []   # 고캠핑 사진은 공공누리 유형이 없어 쓰지 않는다(CLAUDE.md 3절 4항)
    assert p["facts"]["openperiod"] == "봄·여름·가을·겨울 · 평일+주말" and p["facts"]["pet"] == "가능"
    assert p["facts"]["subfacility"] == "전기, 무선인터넷" and "usetime" not in p["facts"]
    assert {s["provider"] for s in p["fact_sources"].values()} == {PET.CAMP_PROVIDER}
    assert p["geo"]["source"] == PET.CAMP_PROVIDER and p["geo"]["url"].endswith("c_no=100545")
    assert p["gocamping"]["sites"] == {"glamping": 13}
    places = json.loads((ROOT / "data" / "gunsan" / "places.json").read_text("utf-8"))
    camps = [x for x in places if x["id"].startswith("gocamping-")]
    assert len(camps) == 3 and all(x["status"] == "draft" and not x.get("approved_at") for x in camps)
