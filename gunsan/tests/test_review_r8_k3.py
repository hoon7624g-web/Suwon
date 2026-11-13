"""Review 2026-10-22, cluster K3 (fees and data):
- tools/round3_official.py, run by tools/refresh.py after every TourAPI merge, deleted a TourAPI value that now says
  something else and kept '한국관광공사 TourAPI로 재확인' on the homepage's value, and put the 2026-10-08 value back over a
  later recheck. Now a differing TourAPI value stays beside the homepage's (both shown, 방문 전 전화 확인 — CLAUDE.md 3.2),
  TourAPI is named as confirming only when it agrees, and a later non-TourAPI recheck is left as it is;
- tools/tourapi_details.merge_facts: a provider that now says something else is no longer named as confirming the
  value, and one that agrees again leaves no earlier differing value of its own;
- pipeline/tickets.py: a combined ticket's rules name a shared source once per run of rules;
- 선유 스카이썬라인: its 요금 from the 군산시 table already collected (table values, 3.3) beside TourAPI's value for the
  same zipline (선유도's 체험 안내), both shown."""
import json
import shutil
from pathlib import Path

import pytest

from pipeline import build as B
from pipeline import present, tickets
from pipeline.build import State
from tools import round3_official
from tools.tourapi_details import merge_facts


@pytest.fixture(scope="module", autouse=True)
def _engine_both_values(engine_both_values):
    """This module checks the engine's both-values display on 군산각's data (tests/conftest.py)."""

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"
TOUR = "한국관광공사 TourAPI"
HOME = "군산근대역사박물관 홈페이지"
OFFICIAL_RESTDATE = "매주 월요일, 1월 1일, 시장이 휴관일로 정한 날"


def _copy(tmp_path: Path) -> Path:
    for f in ("places.json", "events.json"):
        shutil.copy(GUNSAN / f, tmp_path / f)
    return tmp_path


def _museum(data: Path) -> dict:
    return next(p for p in json.loads((data / "places.json").read_text("utf-8")) if p["slug"] == "근대역사박물관")


def _tourapi(data: Path, usetime: str, restdate: str, today: str) -> None:
    """Refresh step 1: the TourAPI detail merge, with this response for the museum."""
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = next(x for x in places if x["slug"] == "근대역사박물관")
    merge_facts(p, {"usetime": usetime, "restdate": restdate}, today, "1684836")
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _rows(p: dict) -> dict:
    return {r["key"]: r for r in present.fact_rows(p, ["usetime", "restdate"], present.Notes())}


def _tour_confirms(src: dict) -> bool:
    return TOUR in str(src.get("confirmed_by") or "")


def test_round3_official_is_idempotent_on_the_data(tmp_path):
    data = _copy(tmp_path)
    round3_official.run(data)
    round3_official.run(data)
    for f in ("places.json", "events.json"):
        assert (data / f).read_bytes() == (GUNSAN / f).read_bytes(), f


def test_a_differing_tourapi_value_stays_beside_the_homepage_s(tmp_path):
    data = _copy(tmp_path)
    for _ in range(2):   # two refreshes: the same result
        _tourapi(data, "09:00~19:00(입장마감 18:30)", "매주 화요일", "2026-10-20")
        round3_official.run(data)
        p = _museum(data)
        rows = _rows(p)
        for key in ("usetime", "restdate"):
            assert rows[key]["conflict"], key
            assert "방문 전 전화 확인" in rows[key]["flag_text"]
            assert TOUR in [b.get("provider_full") for b in rows[key]["blocks"]], key
            assert not _tour_confirms(p["fact_sources"][key]), key   # never '한국관광공사 TourAPI로 재확인'
            assert p["fact_sources"][key]["provider"] == HOME
        assert p["facts"]["restdate"] == OFFICIAL_RESTDATE
        assert [a["value"] for a in p["fact_alternatives"]["restdate"]] == ["매주 화요일"]
        assert p["fact_sources"]["usetime"]["confirmed_by"] == "군산시 문화관광 본문"
        # the 군산시 info table's value stays too, once
        assert sum(a["provider"] == "군산시 문화관광 상세 정보표" for a in p["fact_alternatives"]["usetime"]) == 1
    # TourAPI agrees again: its earlier value goes, the confirmation comes back — the data as it was
    _tourapi(data, round3_official.HOURS, OFFICIAL_RESTDATE, "2026-10-27")
    round3_official.run(data)
    assert (data / "places.json").read_bytes() == (GUNSAN / "places.json").read_bytes()


def test_a_later_recheck_is_never_reverted(tmp_path):
    data = _copy(tmp_path)
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = next(x for x in places if x["slug"] == "근대역사박물관")
    p["facts"]["restdate"] = "매주 화요일, 1월 1일"
    p["fact_sources"]["restdate"] = {**p["fact_sources"]["restdate"], "checked_at": "2026-10-20"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    log = round3_official.run(data)
    p = _museum(data)
    assert p["facts"]["restdate"] == "매주 화요일, 1월 1일"
    assert p["fact_sources"]["restdate"]["checked_at"] == "2026-10-20"
    assert any("restdate" in x and "그대로 둠" in x for x in log)
    # the other key of the same place is still the 2026-10-08 value
    assert p["facts"]["usetime"] == round3_official.HOURS


def test_merge_facts_names_a_provider_as_confirming_only_while_it_agrees():
    place = {"facts": {"restdate": "매주 월요일"}, "fact_sources": {"restdate": {
        "provider": "어느 시설 홈페이지", "checked_at": "2026-10-08", "confirmed_by": f"{TOUR} 2026-10-08 · 군산시 문화관광 본문"}}}
    out = merge_facts(place, {"restdate": "매주 화요일"}, "2026-10-20", "1")
    assert out["conflicts"] == ["restdate"]
    assert place["fact_sources"]["restdate"]["confirmed_by"] == "군산시 문화관광 본문"
    assert [a["value"] for a in place["fact_alternatives"]["restdate"]] == ["매주 화요일"]
    out = merge_facts(place, {"restdate": "매주 월요일"}, "2026-10-27", "1")
    assert out["confirmed"] == ["restdate"]
    assert "fact_alternatives" not in place   # its own earlier '매주 화요일' is gone, nothing contradicts the note
    assert place["fact_sources"]["restdate"]["confirmed_by"] == f"군산시 문화관광 본문 · {TOUR} 2026-10-27"
    # another provider's differing value is never touched
    place["fact_alternatives"] = {"restdate": [{"value": "매주 수요일", "provider": "다른 곳", "checked_at": "2026-10-01"}]}
    merge_facts(place, {"restdate": "매주 월요일"}, "2026-10-28", "1")
    assert [a["value"] for a in place["fact_alternatives"]["restdate"]] == ["매주 수요일"]


def test_ticket_rules_name_a_shared_source_once_per_run():
    sources = {k: {"provider": f"출처{k}", "what": "표", "url": f"https://x.example/{k}", "checked_at": "2026-10-08"}
               for k in ("a", "b")}
    rules = [{"kind": "free", "who": "6세 이하 유아", "source": "a"}, {"kind": "note", "text": "당일만", "source": "a"},
             {"kind": "age", "text": "어린이(7~12세)", "source": "b"}, {"kind": "free", "who": "장애인", "source": "a"}]
    src = {k: tickets.source_text(s) for k, s in sources.items()}
    assert tickets.rules_by_source(rules, sources) == [
        f"무료입장 6세 이하 유아; 당일만 — {src['a']}", f"어린이(7~12세) — {src['b']}", f"무료입장 장애인 — {src['a']}"]
    # each rule alone reads as before
    assert tickets.rule_text(rules[2], sources) == f"어린이(7~12세) — {src['b']}"


def test_skyline_fee_from_the_gunsan_table_beside_tourapi_s():
    S = State(GUNSAN, "production")
    e = next(x for x in S.entities if x["id"] == "gunsan-313200")
    flat = " ".join(e["original"]["text"].split())
    value = e["facts"]["usefee"]
    for n in ("20,000원", "16,000원", "2,000원", "1,000원", "만 13세 이상", "만 7세 이상 ~ 만 12세 이하"):
        assert n in value and n in flat, n   # table values of the collected 군산시 page (CLAUDE.md 3.3)
    src = e["fact_sources"]["usefee"]
    assert (src["provider"], src["url"], src["checked_at"]) == (
        "군산시 문화관광", e["original"]["source_url"], e["original"]["collected_at"])
    row = B.fact_row(e, "usefee")
    [alt] = row["alternatives"]
    assert alt["provider"] == TOUR and not alt["also"]
    isle = next(x for x in S.entities if x["name"] == "선유도")
    assert "만 14세 이상 20,000원 / 만 13세 이하 16,000원" in isle["facts"]["expguide"]
    assert e["fact_alternatives"]["usefee"][0]["contentid"] == isle["tourapi"]["contentid"] == "226923"
    # the first screen shows both, with the call line, and 요금 is no longer '확인 필요'
    kf = present.key_facts(e, "hero")
    fee = next(s for s in kf["slots"] if s["key"] == "fee")
    assert fee["conflict"] and [v["provider"] for v in fee["vals"]] == ["군산시", "한국관광공사"]
    assert "요금" not in kf["missing"]
