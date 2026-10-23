"""'근처 주차·버스' with the standard's own per-lot values and nearby stations: a lot's fee as the 전국주차장정보표준데이터
fields (basic / extra / day ticket), its operating hours, its own desk, the other file's differing values for the
same lot (alt type · 면수 · 무료/유료 · hours · phone, labelled by the data), and nearby.json 'rail' rows (station,
lines, straight-line metres to the nearest exit, its number). Every shown value comes from the files; the validator
catches a changed one. City-neutral: nothing here is a city's name in the engine — labels come from the data."""
import json
import re
import shutil
from pathlib import Path

from pipeline import present
from pipeline.build import State, build
from pipeline.validate import nearby_data_problems, nearby_stale_problems, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
SRC = {"source": "standard", "label": "시청 자료", "source_name": "공공데이터포털 전국주차장정보표준데이터 · 시 파일"}

PAID = {"id": "lot-std", "management_no": "150-2-000013", "name": "샘플길공영주차장", "operation": "공영", "type": "노외",
        "address": "전북특별자치도 군산시 구영7길 69 (신창동 )", "address_jibun": None, "lat": 35.98676791,
        "lng": 126.7104599, "spaces": 81, "paid": "유료", "phone": "063-661-3173", "manager": "군산시 교통과",
        "hours": {"days": "평일+토요일+공휴일", "weekday": ["09:00", "18:00"], "saturday": ["09:00", "19:30"],
                  "holiday": ["09:00", "19:30"]},
        "alt": {"name": {"value": "샘플길주차장", **SRC}, "type": {"value": "노상", **SRC},
                "spaces": {"value": 76, "unit": "면", **SRC}, "phone": {"value": "063-603-4064", "manager": "시설공단", **SRC}},
        "fee": {"differs": True, "versions": [
            {"source": "standard", "label": "구청 자료", "basic": {"minutes": 30, "won": 500},
             "extra": {"minutes": 10, "won": 250}, "day": {"won": 10000, "applies_raw": "3.5"}, "month": {"won": 80000}},
            {"source": "standard", "label": "시청 자료", "basic": {"minutes": 120, "won": 1000}}]}}
FREE = {"id": "lot-free24", "management_no": "150-1-000001", "name": "샘플 노상", "operation": "공영", "type": "노상",
        "address": None, "address_jibun": "전북특별자치도 군산시 신창동 1-2", "lat": 35.987, "lng": 126.711,
        "spaces": 12, "paid": "무료", "hours": {"days": "평일+토요일+공휴일", "weekday": ["00:00", "23:59"],
                                                "saturday": ["00:00", "23:59"], "holiday": ["00:00", "23:59"]},
        "alt": {"name": {"value": "샘플 노상 주차장", **SRC}, "paid": {"value": "유료", **SRC}}}
LOTS = {"source": {"standard": {"name": "공공데이터포털 전국주차장정보표준데이터"}}, "contacts": [], "lots": [PAID, FREE]}
NEARBY = {"_meta": {"parking": {"radius_m": 500, "max": 3},
                    "bus": {"radius_m": 500, "max": 2, "source_name": "공공데이터포털 시내버스 정류소 위치정보"},
                    "rail": {"radius_m": 800, "max": 1, "label": "도시철도역", "heading": "도시철도",
                             "source_name": "공공데이터포털 교통공사 역별 출구별 위치정보"}},
          "sample-0001": {"parking": [{"lot_id": "lot-std", "meters": 71}, {"lot_id": "lot-free24", "meters": 90}],
                          "bus": [{"stop_name": "샘플시장앞", "meters": 40, "routes": ["304", "급행2"]}],
                          "rail": [{"station": "샘플시장역", "official_name": "샘플시장(병원)", "lines": ["1호선", "2호선"],
                                    "exit": "14", "meters": 230}]},
          "sample-0002": {"parking": [], "bus": [], "rail": [{"station": "한빛역", "lines": ["3호선"], "exit": "",
                                                             "meters": 610}]}}


def data_with(tmp_path, nearby=NEARBY, lots=LOTS):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    for p in places:
        if p["id"] in ("sample-0001", "sample-0002"):
            p["geo"] = {"lat": 35.9870443303, "lng": 126.7111681428, "source": "TourAPI"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    (data / "parking_lots.json").write_text(json.dumps(lots, ensure_ascii=False), "utf-8")
    (data / "nearby.json").write_text(json.dumps(nearby, ensure_ascii=False), "utf-8")
    return data


def access_errors(data, out):
    errors, _, _ = validate(data, out, "sample")
    return [x for x in errors if "근처" in x or "정류장" in x or "역" in x or "nearby.json" in x]


def block_text(html):
    b = html[html.index('data-block="access"'):html.index("</section>", html.index('data-block="access"'))]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", b))


def test_standard_fee_hours_and_alt_values_in_the_view_model(tmp_path):
    assert present.fee_text(PAID["fee"]["versions"][0]) == "기본 30분 500원 · 이후 10분마다 250원 · 1일 주차권 10,000원"
    assert present.fee_text(PAID["fee"]["versions"][1]) == "기본 2시간 1,000원"
    assert present.fee_text({"source": "standard", "basic": {"minutes": 20, "won": 0},
                             "extra": {"minutes": 10, "won": 1000}}) == "처음 20분 무료 · 이후 10분마다 1,000원"
    assert present.fee_amounts(PAID["fee"]["versions"][0]) == [500, 250, 10000]      # the month pass is not shown
    assert present.hours_text(PAID["hours"]) == "평일 09:00~18:00 · 토요일·공휴일 09:00~19:30"
    assert present.hours_text(FREE["hours"]) == "평일·토요일·공휴일 24시간"
    assert present.hours_text({"days": "평일", "weekday": ["09:00", "18:00"], "saturday": ["09:00", "13:00"]}) == \
        "평일 09:00~18:00"                                                               # a day not operated: not shown
    S = State(data_with(tmp_path), "sample")
    A = present.access_vm(S, S.ent_by_slug["gyeongam-railroad-village"])
    paid, free = A["lots"]
    assert [f["src"] for f in paid["fees"]] == ["구청 자료", "시청 자료"]
    assert (paid["alt_src"], paid["alt_name"], paid["alt_type"], paid["alt_spaces"], paid["alt_unit"]) == \
        ("시청 자료", "샘플길주차장", "노상주차장", 76, "면")
    assert paid["confirm"] and paid["differ"] == "유형·면수·요금"
    assert paid["contact"] == "군산시 교통과 063-661-3173 · 시설공단 063-603-4064"
    assert free["fees"] == [] and free["confirm"] and free["differ"] == "요금" and free["alt_paid"] == "유료"
    # the source line names the dataset once (the alt's 'standard' source), never the row labels
    assert A["sources"] == ["공공데이터포털 전국주차장정보표준데이터", "공공데이터포털 시내버스 정류소 위치정보",
                            "공공데이터포털 교통공사 역별 출구별 위치정보"]
    assert A["rails"] == [{"name": "샘플시장역", "lines": ["1호선", "2호선"], "lines_text": "1호선·2호선", "m": 230,
                           "exit": "14"}]
    assert A["heading"] == "주차·버스·도시철도" and A["rail_radius"] == 800 and A["rail_label"] == "도시철도역"
    # a place with a station only still gets the block; without rail the heading stays '주차·버스'
    only = present.access_vm(S, S.ent_by_slug["chowon-photo-studio"])
    assert only["lots"] == [] and only["stops"] == [] and only["rails"][0]["exit"] == ""
    S.nearby["sample-0001"] = {**NEARBY["sample-0001"], "rail": []}
    assert present.access_vm(S, S.ent_by_slug["gyeongam-railroad-village"])["heading"] == "주차·버스"


def test_place_page_rows_and_validator(tmp_path):
    data, out = data_with(tmp_path), tmp_path / "site"
    build(data, out, "sample")
    page = out / "places" / "gyeongam-railroad-village" / "index.html"
    good = page.read_text("utf-8")
    text = block_text(good)
    assert "경암동 철길마을 근처 주차·버스·도시철도" in text
    assert "운영 평일 09:00~18:00 · 토요일·공휴일 09:00~19:30" in text
    assert "시청 자료 표기 샘플길주차장 · 노상주차장 · 76면" in text
    assert "구청 자료 기본 30분 500원 · 이후 10분마다 250원 · 1일 주차권 10,000원" in text
    assert "유형·면수·요금 출처마다 다름 · 방문 전 전화 확인 · 문의 군산시 교통과 063-661-3173 · 시설공단 063-603-4064" in text
    assert "80,000" not in text and "3.5" not in text                     # month pass and raw 적용시간 never shown
    assert "운영 평일·토요일·공휴일 24시간" in text and "시청 자료 표기 샘플 노상 주차장 · 유료" in text
    assert "가까운 도시철도역 직선거리 800m 안" in text and "샘플시장역 1호선·2호선 직선거리 230m 가장 가까운 출구 14번" in text
    assert 'data-rail="샘플시장역"' in good and 'href="tel:0636613173"' in good
    other = block_text((out / "places" / "chowon-photo-studio" / "index.html").read_text("utf-8"))
    assert "한빛역 3호선 직선거리 610m" in other and "가장 가까운 출구" not in other and "근처 공영주차장" not in other
    assert access_errors(data, out) == []

    def errors_after(html):
        page.write_text(html, "utf-8")
        found = access_errors(data, out)
        page.write_text(good, "utf-8")
        return found

    assert any("가까운 역" in x for x in errors_after(good.replace(">14</span>번", ">15</span>번")))
    assert any("가까운 역" in x for x in errors_after(good.replace(">230m<", ">250m<")))
    assert any("2호선" in x for x in errors_after(good.replace("1호선·2호선", "1호선")))
    assert any("가까운 역 줄이 nearby.json과 다름" in x for x in
               errors_after(re.sub(r'<li data-rail="샘플시장역">.*?</li>', "", good, flags=re.S)))
    assert any("파일에 없는 숫자" in x or "파일 값이 줄에 없음" in x for x in
               errors_after(good.replace("09:00~18:00", "09:00~17:00", 1)))
    assert any("10,000원" in x or "파일에 없는 숫자" in x for x in errors_after(good.replace("10,000원", "9,000원", 1)))
    assert any("063-661-3173" in x for x in errors_after(good.replace("063-661-3173", "063-661-3174")))
    assert any("방문 전 전화 확인" in x for x in errors_after(good.replace(" · 방문 전 전화 확인", "", 2)))
    # '24' is allowed only for a lot whose stored hours read 24시간 — not on the paid lot (09:00~18:00)
    assert any("파일에 없는 숫자 ['24']" in x for x in errors_after(good.replace("81면", "81면 · 24", 1)))


def test_rail_rows_in_nearby_json_keep_radius_count_and_order(tmp_path):
    rail = [{"station": "가역", "lines": ["1호선"], "exit": "1", "meters": 900},
            {"station": "", "lines": [], "exit": "", "meters": 100}]
    bad = {**NEARBY, "sample-0001": {"parking": [], "bus": [], "rail": rail}}
    S = State(data_with(tmp_path, nearby=bad), "sample")
    problems = nearby_data_problems(S)
    assert any("역 거리 900m" in x for x in problems)
    assert any("역 이름이나 노선이 비어 있음" in x for x in problems)
    assert any("max를 넘음" in x for x in problems)
    assert any("역이 가까운 순이 아님" in x for x in problems)


def test_a_moved_place_warns_even_when_it_has_only_stops(tmp_path):
    """measured_from (the place coordinates an entry was measured from): a place that has moved since warns — stop and
    station rows carry no coordinates of their own, so this is the only check that sees them go stale — and an entry
    that matches the place, or a file without measured_from (Gunsan's), gives no warning."""
    here = {"lat": 35.9870443303, "lng": 126.7111681428}
    moved = {"lat": 35.9970443303, "lng": 126.7111681428}          # about 1.1 km north
    only_stops = {"parking": [], "bus": [{"stop_name": "샘플시장앞", "meters": 40, "routes": ["304"]}], "rail": []}
    for name, at, warned in (("same", here, False), ("moved", moved, True), ("none", None, False)):
        entry = {**({"measured_from": at} if at else {}), **only_stops}
        nearby = {**NEARBY, "sample-0001": entry}
        S = State(data_with(tmp_path / name, nearby=nearby), "sample")
        found = [x for x in nearby_stale_problems(S) if "sample-0001" in x]
        assert bool(found) is warned, (name, found)
        if warned:
            assert "옮겨짐" in found[0] and "다시 만들어야" in found[0]
