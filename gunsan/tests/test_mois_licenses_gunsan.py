"""tools/mois_licenses_gunsan.py — 행정안전부 인허가 12종 + 식품안심업소(위생등급) → 장소의 영업 상태·전화·지정.
네트워크 없이 작은 고정 응답으로 매칭·상태·키 가림을 본다."""
import csv
import gzip
import io
import json
import urllib.error

import pytest

from tools import mois_licenses_gunsan as L

TODAY = "2026-10-31"


def lic(name, road="", lot="", code="01", svc="general_restaurants", mng="1", lcpmt="2020-01-01", closed="", tel="",
        x="", y=""):
    r = {"MNG_NO": mng, "BPLC_NM": name, "ROAD_NM_ADDR": road, "LOTNO_ADDR": lot, "SALS_STTS_CD": code,
         "SALS_STTS_NM": {"01": "영업/정상", "02": "휴업", "03": "폐업"}.get(code, ""), "LCPMT_YMD": lcpmt,
         "CLSBIZ_YMD": closed, "TELNO": tel, "CRD_INFO_X": x, "CRD_INFO_Y": y, "BZSTAT_SE_NM": "한식"}
    return L.prep(r, svc)


def place(pid, name, address, kind="food", status="published", tel=None, geo=None, **kw):
    facts = {"address": address}
    if tel:
        facts["infocenter"] = tel
    return {"id": pid, "name": name, "kind": kind, "status": status, "facts": facts, "geo": geo, **kw}


def index(rows):
    by = {}
    for r in rows:
        for n in r["_names"]:
            by.setdefault(n, []).append(r)
    return by


def test_address_keys_read_road_and_lot_addresses_alike_across_sources():
    k = L.addr_keys
    assert k("전북특별자치도 군산시 성산면 철새로 56") == {("road", "철새로", "56")}
    assert k("전북특별자치도 군산시 백릉안 1길 17 (경장동)") == k("전북특별자치도 군산시 백릉안1길 17")
    assert k("전북특별자치도 군산시 구암3.1로 137(스타필드마켓 2층 경암동)") == {("road", "구암31로", "137")}
    assert k("전북특별자치도 군산시 대학로 316(나운동, 외4필지 시민프라자 112.113호)") == {("road", "대학로", "316")}
    assert k("전라북도 군산시 중앙로 1가 14-7") == k("전북특별자치도 군산시 중앙로1가 14-7") == {("lot", "중앙로1가", "14-7")}
    assert k("전북특별자치도 군산시 부흥로 316번길 38-3") == {("road", "부흥로316번길", "38-3")}
    assert k("전북특별자치도 군산시 현충로84(호텔나운)") == {("road", "현충로", "84")}
    assert k("전라북도 군산시 구영6길 (월명동)") == set()   # no number: no key, never a guess


def test_names_read_spelling_brackets_and_lodging_words_alike_but_not_branches_or_former_names():
    assert L.norm_name("청담횟집") == L.norm_name("청담회집")
    assert "베스트웨스턴군산호텔" in L.name_variants("오에이치엠씨(주)(베스트웨스턴 군산호텔)")
    assert L.name_variants("Hotel RG(알지)") == {"hotelrg", "알지"}
    assert L.name_variants("라라코스트(수송점)") == {"라라코스트"}
    assert L.name_variants("여미랑 (구.고우당)") == {"여미랑"}
    assert L.related("비타민호텔", "호텔비타민") and L.related("프리마호텔", "프리마모텔")
    assert not L.related("스타무인텔", "아트무인텔")


def test_same_name_and_address_matches_and_open_beats_closed():
    rows = [lic("째보식당", road="전북특별자치도 군산시 구영3길 70 (신창동)", code="03", mng="a", closed="2015-03-01"),
            lic("째보식당", road="전북특별자치도 군산시 구영3길 70 (신창동)", mng="b", lcpmt="2015-04-01", tel="063-445-1234")]
    p = place("p1", "째보식당", "전북특별자치도 군산시 구영3길 70(신창동)", tel="063-445-1234")
    got, basis, _ = L.match_place(p, rows, index(rows))
    assert basis == "name+address" and len(got) == 2
    assert L.status_of(got) == "영업" and L.representative(got)["MNG_NO"] == "b"
    out = L.build([p], rows, [], {}, None, TODAY)
    v = out["places"]["p1"]
    assert v["status"] == "영업" and v["closed_at"] is None and v["tel_compare"] == "same" and v["kind"] == "일반음식점"
    assert out["closed"] == [] and out["unmatched_places"] == []


def test_all_rows_closed_is_a_closed_report_and_status_is_never_touched():
    rows = [lic("옛집", road="전북특별자치도 군산시 해망로 10", code="03", mng="a", closed="2019-01-02"),
            lic("옛집", road="전북특별자치도 군산시 해망로 10", code="03", mng="b", closed="2024-05-06")]
    p = place("p1", "옛집", "전북특별자치도 군산시 해망로 10")
    out = L.build([p], rows, [], {}, None, TODAY)
    assert out["places"]["p1"]["status"] == "폐업 확인" and out["places"]["p1"]["closed_at"] == "2024-05-06"
    assert out["closed"][0]["id"] == "p1" and out["closed"][0]["closed_at"] == "2024-05-06"
    assert p["status"] == "published"


def test_same_name_elsewhere_is_left_unmatched_with_candidates():
    rows = [lic("바다횟집", road="전북특별자치도 군산시 해망로 99")]
    p = place("p1", "바다횟집", "전북특별자치도 군산시 해망로 10")
    out = L.build([p], rows, [], {}, None, TODAY)
    assert out["places"] == {}
    u = out["unmatched_places"][0]
    assert u["reason"] == "same name, other address" and u["candidates"][0]["name"] == "바다횟집"


def test_similar_name_needs_the_same_address_and_one_name_only():
    one = [lic("째보식당", road="전북특별자치도 군산시 구영3길 70")]
    p = place("p1", "째보식당 본점", "전북특별자치도 군산시 구영3길 70")
    assert L.match_place(p, one, index(one))[1] == "similar-name+address"
    two = [lic("바다횟집", road="전북특별자치도 군산시 해망로 1"), lic("푸른바다", road="전북특별자치도 군산시 해망로 1", mng="2")]
    p2 = place("p2", "바다", "전북특별자치도 군산시 해망로 1")
    got, basis, cands = L.match_place(p2, two, index(two))
    assert got == [] and basis == "similar names at the address" and len(cands) == 2
    elsewhere = [lic("째보식당", road="전북특별자치도 군산시 구영3길 71")]
    assert L.match_place(p, elsewhere, index(elsewhere))[0] == []


def test_a_brand_relicensed_at_the_same_address_keeps_the_place_in_business():
    # '째보식당' closed and '째보식당 군산점' licensed the same day at the same address (구영3길 70)
    rows = [lic("째보식당", road="전북특별자치도 군산시 구영3길 70 (신창동)", code="03", mng="a", closed="2022-05-24"),
            lic("째보식당 군산점", road="전북특별자치도 군산시 구영3길 70, 1층 (신창동)", mng="b", lcpmt="2022-05-24"),
            lic("황제반찬식당", road="전북특별자치도 군산시 구영3길 70 (신창동)", code="03", mng="c", closed="2018-02-08")]
    for name in ("째보식당 본점", "째보식당"):
        got, basis, _ = L.match_place(place("p1", name, "전북특별자치도 군산시 구영3길 70(신창동)"), rows, index(rows))
        assert {r["MNG_NO"] for r in got} == {"a", "b"} and L.status_of(got) == "영업"


def test_closed_report_lists_what_is_open_at_the_same_unit_and_a_renamed_stay_joins_by_address_and_phone():
    rows = [lic("삼풍식당", road="전북특별자치도 군산시 성산면 철새로 31, 107호 (금강회센타)", code="03", closed="2025-03-04"),
            lic("이레식당", road="전북특별자치도 군산시 성산면 철새로 31, 1층 107호", mng="2", lcpmt="2025-08-13"),
            lic("신가네칼국수", road="전북특별자치도 군산시 성산면 철새로 31, 101호", mng="3")]
    out = L.build([place("p1", "삼풍식당", "전북특별자치도 군산시 성산면 철새로 31")], rows, [], {}, None, TODAY)
    c = out["closed"][0]
    assert c["name"] == "삼풍식당" and [o["name"] for o in c["open_at_same_address"]] == ["이레식당"]
    stay = [lic("BB호텔", road="전북특별자치도 군산시 현충로 88 (나운동)", svc="lodgings", tel="063-464-7755")]
    out = L.build([place("s1", "까사밀라모텔", "전북특별자치도 군산시 현충로 88 (나운동)", kind="stay", tel="063-464-7755")],
                  stay, [], {}, None, TODAY)
    # 운영자 결정 2026-10-31 '이어': the same address and our phone — the same house under its licensed name
    assert out["places"]["s1"]["match"] == "address+tel" and out["places"]["s1"]["name"] == "BB호텔"
    # another phone at the address stays a candidate for a person
    out = L.build([place("s1", "까사밀라모텔", "전북특별자치도 군산시 현충로 88 (나운동)", kind="stay", tel="063-000-0000")],
                  stay, [], {}, None, TODAY)
    u = out["unmatched_places"][0]
    assert out["places"] == {} and u["reason"] == "other names at the address" and not u["candidates"][0]["same_tel"]


def test_same_name_without_an_address_key_matches_only_by_a_near_point():
    # 군산 중앙로1가 11-1 in EPSG:5174 (a 인허가 CRD_INFO pair)
    x, y = "173927.17921379", "276419.278498382"
    lat, lng = L.tm5174_to_wgs84(float(x), float(y))
    assert abs(lat - 35.98776) < 1e-4 and abs(lng - 126.71168) < 1e-4
    rows = [lic("여미랑", road="", lot="", x=x, y=y, svc="lodgings")]
    near = place("p1", "여미랑 (구.고우당)", "전라북도 군산시 구영6길 (월명동)", kind="stay",
                 geo={"lat": lat + 0.0003, "lng": lng})
    far = dict(near, id="p2", geo={"lat": lat + 0.01, "lng": lng})
    assert L.match_place(near, rows, index(rows))[1] == "name+coords"
    assert L.match_place(far, rows, index(rows))[0] == []


def test_groups_keep_food_stay_and_camping_apart():
    assert L.place_group({"id": "gocamping-1", "name": "버드글램핑", "kind": "attraction"}) == "camp"
    assert L.place_group({"id": "x", "name": "관리도캠핑장", "kind": "attraction"}) == "camp"
    assert L.place_group({"id": "x", "name": "선유도 리조트", "kind": "stay"}) == "stay"
    assert L.place_group({"id": "x", "name": "공원", "kind": "attraction"}) is None
    rows = [lic("선유도", road="전북특별자치도 군산시 옥도면 선유북길 1", svc="lodgings")]
    p = place("p1", "선유도", "전북특별자치도 군산시 옥도면 선유북길 1")   # a food place never takes a 숙박업 row
    out = L.build([p], rows, [], {}, None, TODAY)
    assert out["places"] == {} and out["unmatched_places"][0]["reason"] == "no licence row"


def hyg(name, addr, **kw):
    r = {"HG_ASGN_NM": "식품의약품안전처", "HG_ASGN_LV": "적합", "HG_ASGN_NO": "제HG1호", "INDUTY_NM": "일반음식점",
         "LCNS_NO": "20200000001", "BSSH_NM": name, "ADDR": addr, "ASGN_FROM": "20250101", "ASGN_TO": "20271231",
         "ASGN_CANCEL_YMD": "", "CLSBIZ_DVS_CD_NM": "정상", "INSTT_CD_NM": "전북 군산시"}
    r.update(kw)
    return r


def test_hygiene_needs_name_and_address_and_a_valid_designation():
    rows = [lic("째보식당", road="전북특별자치도 군산시 구영3길 70 (신창동)")]
    p = place("p1", "째보식당 본점", "전북특별자치도 군산시 구영3길 70(신창동)")
    good = hyg("째보식당", "전북특별자치도 군산시 구영3길 70(1층 신창동)")
    out = L.build([p], rows, [good], {}, None, TODAY)
    h = out["places"]["p1"]["hygiene"]
    assert h == {"level": "적합", "valid_from": "2025-01-01", "valid_to": "2027-12-31", "no": "제HG1호",
                 "designated_by": "식품의약품안전처", "kind": "일반음식점", "name": "째보식당"}
    for bad in (hyg("째보식당", "전북특별자치도 군산시 구영3길 71"), hyg("째보식당", good["ADDR"], CLSBIZ_DVS_CD_NM="폐업(자진)"),
                hyg("째보식당", good["ADDR"], ASGN_TO="20261030"), hyg("째보식당", good["ADDR"], ASGN_CANCEL_YMD="20260101"),
                hyg("다른식당", good["ADDR"])):
        assert "hygiene" not in L.build([p], rows, [bad], {}, None, TODAY)["places"]["p1"]


def test_phone_comparison_uses_digits_only():
    assert L.tel_compare("063-445-1234", "063 4451234") == "same"
    assert L.tel_compare("063-445-1234 / 010-1111-2222", "01011112222") == "same"
    assert L.tel_compare("063-445-1234", "063-445-9999") == "different"
    assert L.tel_compare(None, "063-445-9999") == "ours_missing"
    assert L.tel_compare("063-445-1234", "") == "license_missing"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_pages_writes_raw_values_and_never_the_key(tmp_path):
    key = "SECRET+KEY/=="
    data = tmp_path / "data" / "gunsan"
    data.mkdir(parents=True)
    calls = []
    items = [{"MNG_NO": f"m{i}", "BPLC_NM": f"가게{i}", "SALS_STTS_CD": "01", "TELNO": None, "ROAD_NM_ADDR": "a",
              "DAT_UPDT_PNT": "2026-10-30 22:47:46", "EXTRA": "x"} for i in range(150)]

    def opener(url):
        calls.append(url)
        page = int(url.split("pageNo=")[1].split("&")[0])
        body = {"totalCount": 150, "items": {"item": items[(page - 1) * 100:page * 100]}}
        return FakeResp(json.dumps({"response": {"header": {"resultCode": "0"}, "body": body}}).encode())

    got = L.fetch(data, key, tmp_path / "cache", services=["bakeries"], opener=opener, today=TODAY)
    assert got == {"calls": 2, "bakeries": 150} and all("OPN_ATMY_GRP_CD%3A%3AEQ%5D=4671000" in u for u in calls)
    rows = L.read_csv(tmp_path / "data" / "raw" / "gunsan" / "licenses" / "mois_bakeries.csv")
    assert len(rows) == 150 and rows[0]["TELNO"] == "" and "EXTRA" not in rows[0]
    log = json.loads((tmp_path / "data" / "raw" / "gunsan" / "licenses" / L.FETCH_LOG).read_text("utf-8"))
    assert log["bakeries"] == {"fetched_at": TODAY, "total": 150, "rows": 150, "data_updated": "2026-10-30",
                               "file": "mois_bakeries.csv"}
    # a second run reads the day's cache: no call
    assert L.fetch(data, key, tmp_path / "cache", services=["bakeries"], opener=opener, today=TODAY)["calls"] == 0
    for f in list((tmp_path / "cache").rglob("*")) + list((tmp_path / "data").rglob("*")):
        if f.is_file():
            assert "SECRET" not in f.read_text("utf-8")


def test_fetch_error_shows_the_provider_message_with_the_key_masked(tmp_path, monkeypatch):
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    key = "SECRET+KEY/=="

    def opener(url):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {},
                                     io.BytesIO(f"SERVICE_KEY_IS_NOT_REGISTERED_ERROR {url}".encode()))

    with pytest.raises(SystemExit) as e:
        L.fetch(tmp_path / "data" / "gunsan", key, tmp_path / "cache", services=["bakeries"], opener=opener, today=TODAY)
    msg = str(e.value)
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in msg and "SECRET" not in msg and "***" in msg


def test_hygiene_extract_keeps_gunsan_rows_with_every_column(tmp_path):
    cols = ["HG_ASGN_NM", "HG_ASGN_LV", "HG_ASGN_NO", "HG_ASGN_YMD", "INDUTY_NM", "LCNS_NO", "BSSH_NM", "ADDR",
            "ASGN_FROM", "ASGN_TO", "CLSBIZ_DVS_CD_NM", "CHNG_DT", "INSTT_CD_NM"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    w.writerow({**{c: "" for c in cols}, "BSSH_NM": "군산집", "ADDR": "전북특별자치도 군산시 해망로 1",
                "CHNG_DT": "20261001", "HG_ASGN_YMD": "20261002", "INSTT_CD_NM": "전북 군산시"})
    w.writerow({**{c: "" for c in cols}, "BSSH_NM": "여수집", "ADDR": "전남 여수시 장군산길 70",
                "CHNG_DT": "20261029", "HG_ASGN_YMD": "20261003", "INSTT_CD_NM": "전남광주통합특별시 여수시"})
    src = tmp_path / "in" / "C004.csv.gz"
    src.parent.mkdir()
    src.write_bytes(gzip.compress(buf.getvalue().encode("utf-8-sig")))
    data = tmp_path / "data" / "gunsan"
    log = L.extract_hygiene(data, src, today=TODAY)
    assert log["rows_total"] == 2 and log["rows_gunsan"] == 1 and log["base_date"] == "2026-10-29"
    rows = L.read_csv(tmp_path / "data" / "raw" / "gunsan" / "hygiene" / L.HYGIENE_FILE)
    assert [r["BSSH_NM"] for r in rows] == ["군산집"] and list(rows[0]) == cols
