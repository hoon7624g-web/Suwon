"""Enrichment logic with a fake TourAPI (no network). City rules come from the metro fixture's config (names, roads and
region codes here are made up; only the 구·군 names are real) and, for a city inside a province, the sample config."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline import city as city_mod
from pipeline.enrich import collect_events, fill_entity, in_city, match_entity, score_candidate
from pipeline import enrich
from pipeline.slugs import is_slug
from pipeline.tourapi import TourAPIQuotaError

ROOT = Path(__file__).resolve().parent.parent
METRO_SITE = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))
METRO = city_mod.from_site(METRO_SITE)
SAMPLE = city_mod.from_site(json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8")))
REGN = "990"  # synthetic region code: the provider's real codes are only ever read from ldongCode2


class FakeAPI:
    live_calls = 0
    cache_hits = 0
    festivals: list = []

    def __init__(self):
        self.festival_queries = []

    def search_keyword(self, keyword, content_type_id=None, rows=20):
        return [
            {"contentid": "111", "contenttypeid": "12", "title": "샘플 철길마을", "addr1": "대구광역시 중구 샘플4길 14",
             "mapx": "128.6", "mapy": "35.87"},
            {"contentid": "999", "contenttypeid": "12", "title": "철길마을", "addr1": "서울특별시 어딘가"},
        ]

    def detail_common(self, cid):
        return {"contentid": cid, "contenttypeid": "12", "title": "샘플 철길마을", "addr1": "대구광역시 중구 샘플4길 14",
                "mapx": "128.6", "mapy": "35.87", "tel": "053-000-0000", "homepage": '<a href="https://example.org">x</a>',
                "overview": "개요<br>두 줄", "firstimage": "https://img/1.jpg", "cpyrhtDivCd": "Type1"}

    def detail_intro(self, cid, ctype):
        return {"usetime": "상시 개방", "parking": "인근 공영주차장<br>(유료)", "chkbabycarriage": "없음"}

    def detail_info(self, cid, ctype):
        return [{"infoname": "입 장 료", "infotext": "무료"}]

    def location_based(self, lat, lng, radius=2000, content_type_id=None, rows=40):
        return [
            {"contentid": "111", "contenttypeid": "12", "title": "샘플 철길마을", "dist": "0"},
            {"contentid": "222", "contenttypeid": "12", "title": "샘플사진관", "dist": "850.5"},
            {"contentid": "333", "contenttypeid": "32", "title": "숙소 A", "dist": "400"},
            {"contentid": "444", "contenttypeid": "39", "title": "식당 A", "dist": "120"},
            {"contentid": "555", "contenttypeid": "25", "title": "코스(제외 대상)", "dist": "10"},
        ]

    def ldong_code(self, regn=None, rows=100):
        if regn is None:
            return [{"code": "980", "name": "다른광역시"}, {"code": REGN, "name": "대구광역시"}]
        return [{"code": str(99101 + i), "name": d} for i, d in enumerate(METRO.districts)] if regn == REGN else []

    def search_festival(self, start, regn=None, signgu=None, rows=100, page=1):
        self.festival_queries.append((start, regn, signgu, page))
        return self.festivals[(page - 1) * rows:page * rows]


def test_score_prefers_region_and_exact_name():
    a = score_candidate("샘플 철길마을", {"title": "대구 샘플 철길마을", "addr1": "대구 중구"}, METRO)
    b = score_candidate("샘플 철길마을", {"title": "샘플 철길마을", "addr1": "서울"}, METRO)
    assert a >= 0.85 > b


def test_inside_the_city_is_the_configured_admin_and_its_city():
    assert in_city("대구광역시 수성구 시험로 42", METRO) and in_city("대구 동구 샘플길 5", METRO)
    assert not in_city("서울특별시 중구 샘플로 1", METRO) and not in_city("", METRO)
    # a city inside a province: the province alone is not enough, its 시 must follow
    inside = score_candidate("샘플관", {"title": "샘플관", "addr1": f"{SAMPLE.region_admin} {SAMPLE.locality} 샘플로 1"}, SAMPLE)
    elsewhere = score_candidate("샘플관", {"title": "샘플관", "addr1": f"{SAMPLE.region_admin} 다른시 샘플로 1"}, SAMPLE)
    assert inside == 1.0 and elsewhere == 0.5


def test_match_and_fill():
    api = FakeAPI()
    e = {"id": "g-1", "name": "샘플 철길마을", "slug": "saempeul-cheolgilmaeul", "kind": "attraction"}
    best, score, _ = match_entity(api, e, METRO)
    assert best["contentid"] == "111" and score >= 0.75
    e["tourapi"] = {"contentid": "111", "contenttypeid": "12"}
    other = {"id": "g-2", "name": "샘플사진관", "slug": "saempeul-sajingwan", "tourapi": {"contentid": "222"}}
    site = {"tourapi": {"nearby_radius_m": 2000, "nearby_per_kind": 3}, "publish_rules": {}}
    fill_entity(api, e, site, {"222": other, "111": e}, "2026-10-12")
    f = e["facts"]
    assert f["usetime"] == "상시 개방" and f["usefee"] == "무료" and f["parking"] == "인근 공영주차장\n(유료)"
    assert f["babycarriage"] == "없음" and f["homepage"] == "https://example.org" and f["infocenter"] == "053-000-0000"
    assert e["geo"] == {"lat": 35.87, "lng": 128.6, "source": "TourAPI"}
    assert e["images"][0]["license"] == "KOGL-1"
    kinds = [(n["name"], n["kind"]) for n in e["nearby"]]
    assert kinds == [("샘플사진관", "attraction"), ("숙소 A", "stay"), ("식당 A", "food")]
    assert e["nearby"][0]["internal_slug"] == "saempeul-sajingwan" and e["nearby"][0]["distance_m"] == 850
    assert e["facts_source"]["checked_at"] == "2026-10-12"


def test_locks_are_respected():
    api = FakeAPI()
    e = {"id": "g-1", "name": "샘플 철길마을", "kind": "attraction", "locks": ["facts", "geo"],
         "facts": {"usetime": "수동 확인값"}, "geo": {"lat": 1.0, "lng": 2.0, "source": "manual"},
         "tourapi": {"contentid": "111", "contenttypeid": "12"}}
    fill_entity(api, e, {"tourapi": {}, "publish_rules": {}}, {}, "2026-10-12")
    assert e["facts"] == {"usetime": "수동 확인값"} and e["geo"]["source"] == "manual"


def test_disallowed_image_licence_is_dropped():
    class Type4(FakeAPI):
        def detail_common(self, cid):
            d = super().detail_common(cid)
            d["cpyrhtDivCd"] = "Type4"
            return d
    e = {"id": "g-1", "name": "샘플 철길마을", "kind": "attraction", "tourapi": {"contentid": "111", "contenttypeid": "12"}}
    fill_entity(Type4(), e, {"tourapi": {}, "publish_rules": {}}, {}, "2026-10-12")
    assert e["images"] == []


def test_events_come_from_the_region_codes_and_keep_a_series_slug():
    fest = lambda cid, title: {"contentid": cid, "title": title, "eventstartdate": "20261009",
                               "eventenddate": "20261011", "addr1": "대구광역시 중구 샘플로 1"}

    class Fests(FakeAPI):
        festivals = [fest("1", "2026 샘플 축제"), fest("2", "2026 다른 축제"), fest("3", "이미 받은 행사")]
    existing = [{"id": "e-old", "name": "2025 샘플 축제", "start_date": "2025-10-10", "slug": "sample-festival"},
                {"id": "e-x", "name": "[샘플] 기존 행사", "start_date": "2026-05-01", "slug": "dareun-chukje"},
                {"id": "e-3", "contentid": "3", "name": "이미 받은 행사", "start_date": "2026-01-01"}]
    api = Fests()
    out = collect_events(api, METRO_SITE, deepcopy(existing), "2026-10-12")
    # a metropolitan city: one search for the whole 시·도 (region code only), from 1 January
    assert api.festival_queries == [("20260101", REGN, None, 1)]
    added = {ev["contentid"]: ev for ev in out[len(existing):]}
    assert sorted(added) == ["1", "2"]                                      # contentid 3 already listed
    assert added["1"]["slug"] == "sample-festival"                          # the series' stored slug
    assert added["2"]["slug"] == "dareun-chukje-2"                          # another series holds the plain one
    assert all(is_slug(ev["slug"]) for ev in added.values())


@pytest.mark.parametrize("phase", ["match", "detail", "events"])
def test_quota_stop_prevents_later_entities_and_events_and_restores_partial_fill(tmp_path, monkeypatch, phase):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOURAPI_KEY", "synthetic-test-key")
    data = tmp_path / "data"
    data.mkdir()
    entities = [{"id": f"g-{i}", "name": "샘플 철길마을", "kind": "attraction",
                 "facts": {"address": "기존 주소"}, "original": {"text": "보존 원문"}}
                for i in range(2)]
    if phase != "match":
        for entity in entities:
            entity["tourapi"] = {"contentid": "111", "contenttypeid": "12"}
    before = deepcopy(entities)
    (data / "places.json").write_text(json.dumps(entities), "utf-8")
    (data / "site.json").write_text(json.dumps(METRO_SITE, ensure_ascii=False), "utf-8")
    (data / "events.json").write_bytes(b"[]")

    class StoppingAPI(FakeAPI):
        def __init__(self):
            super().__init__()
            self.calls = []

        def search_keyword(self, *args, **kwargs):
            self.calls.append("match")
            raise TourAPIQuotaError("resultCode=22; quota stop")

        def detail_common(self, cid):
            self.calls.append("common")
            return super().detail_common(cid)

        def detail_intro(self, cid, ctype):
            self.calls.append("intro")
            if phase == "detail":
                raise TourAPIQuotaError("resultCode=22; quota stop")
            return super().detail_intro(cid, ctype)

        def search_festival(self, *args, **kwargs):
            self.calls.append("events")
            raise TourAPIQuotaError("resultCode=22; quota stop")

    api = StoppingAPI()
    monkeypatch.setattr(enrich, "from_site_config", lambda *args, **kwargs: api)
    result = enrich.run(data, events=True)
    assert result["stopped"] and result["failed"] == 1
    saved = json.loads((data / "places.json").read_text("utf-8"))
    assert (data / "events.json").read_bytes() == b"[]"
    if phase == "match":
        assert api.calls == ["match"]
        assert saved[1] == before[1]
    elif phase == "detail":
        assert api.calls == ["common", "intro"]
        assert saved == before  # No half-filled geo/facts or later entity mutations.
    else:
        assert api.calls[-1] == "events"
    report = (tmp_path / "reports" / "enrich_report.md").read_text("utf-8")
    assert "호출 중단" in report and "synthetic-test-key" not in report
