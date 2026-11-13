"""Operator 2026-10-31 '홈에 불꽃축제 고정': events.json pin_home puts that edition first on the home's event rows and
news cards (present.pinned_first); the others keep ranked_events' order, and an edition that is over is not there."""
import json
from pathlib import Path

from pipeline import present

ROOT = Path(__file__).resolve().parents[1]


def row(i, pin=False, days=0):
    return {"ev": {"id": i, **({"pin_home": True} if pin else {})}, "days": days}


def test_pinned_rows_come_first_and_the_rest_keep_their_order():
    rows = [row("a"), row("b", days=3), row("fw", pin=True, days=14), row("c", days=20)]
    assert [r["ev"]["id"] for r in present.pinned_first(rows)] == ["fw", "a", "b", "c"]
    assert [r["ev"]["id"] for r in present.pinned_first(rows[:2])] == ["a", "b"]


def test_the_fireworks_edition_is_the_one_pinned_and_it_is_published():
    ev = json.loads((ROOT / "data" / "gunsan" / "events.json").read_text("utf-8"))
    pinned = [e for e in ev if e.get("pin_home")]
    assert [e["id"] for e in pinned] == ["fest-군산불꽃축제-2026"]
    assert pinned[0]["status"] == "published" and pinned[0]["end_date"] == "2026-11-14"


# ------------------------------------------------------------------ 홈의 불꽃축제 띠 (operator 2026-11-04 meeting)
def test_event_start_time_only_for_one_day_editions_with_one_start():
    from pipeline.textutil import event_start_dt
    one = {"start_date": "2026-11-14", "end_date": "2026-11-14"}
    assert event_start_dt({**one, "playtime": "20:00 (약 30분)"}) == "2026-11-14T20:00+09:00"
    assert event_start_dt({**one, "playtime": "9:30~21:00"}) == "2026-11-14T09:30+09:00"
    assert event_start_dt({**one, "playtime": "화~일요일 10:00~17:00"}) == ""
    assert event_start_dt({**one, "playtime": "20:00", "alternatives": {"playtime": [{"value": "19:00"}]}}) == ""
    assert event_start_dt({"start_date": "2026-10-02", "end_date": "2026-10-05", "playtime": "10:00~21:00"}) == ""
    assert event_start_dt({**one}) == ""


def test_the_home_band_shows_the_pinned_edition_with_its_reel_until_it_is_over():
    ev = {"id": "fw", "pin_home": True, "highlights": ["해상 불꽃쇼 — 축사 없음", "약 1만 석", "부스 없음 — 안내 예정"],
          "home_reel": {"url": "https://www.instagram.com/reel/x/", "points": [0, 2, 9]},
          "start_date": "2026-11-14", "end_date": "2026-11-14", "playtime": "20:00 (약 30분)"}
    r = {"ev": ev, "title": "2026 군산불꽃축제 '군산의 밤을 물들이다'", "start": "2026-11-14", "last": "2026-11-14",
         "time": "20:00 (약 30분)", "days": 10, "place": "내항", "path": "/events/x/",
         "source": "군산시 보도자료 '해상 불꽃쇼… 개최' (관광진흥과, 2026-10-27)"}
    f = present.home_fest([{"ev": {"id": "a"}}, r])
    assert f["h"] == "2026 군산불꽃축제" and f["sub"] == "'군산의 밤을 물들이다'"
    assert f["points"] == [{"t": "해상 불꽃쇼", "d": "축사 없음"}, {"t": "부스 없음", "d": "안내 예정"}]
    assert f["when"] == "11월 14일(토)" and f["start_dt"] == "2026-11-14T20:00+09:00"
    assert f["src"] == "군산시 보도자료 (관광진흥과, 2026-10-27)"
    # not pinned, no reel, or over (ranked_events leaves it out): no band
    assert present.home_fest([{"ev": {**ev, "pin_home": False}}]) is None
    assert present.home_fest([{"ev": {**ev, "home_reel": {}}}]) is None
    assert present.home_fest([]) is None


def test_the_fireworks_reel_is_the_operator_s_own_post_without_tracking_values():
    ev = json.loads((ROOT / "data" / "gunsan" / "events.json").read_text("utf-8"))
    reel = next(e for e in ev if e["id"] == "fest-군산불꽃축제-2026")["home_reel"]
    assert reel["url"] == "https://www.instagram.com/reel/DfPLO1hN5gA/" and reel["account"] == "gunsangak_official"


# ------------------------------------------------------------------ 관련 사진 (operator 2026-11-04)
def test_a_post_without_a_place_photo_gets_a_related_one_marked_so():
    ph = lambda u, t=1: {"url": u, "type": t}
    by = {"해망굴": {"slug": "해망굴", "name": "해망굴", "_photos": [ph("h1")]},
          "군산신흥동일본식가옥": {"slug": "군산신흥동일본식가옥", "name": "군산신흥동일본식가옥(히로쓰가옥)",
                              "_photos": [ph("j1"), ph("j2", 3)]},
          "구-조선식량영단-군산출장소": {"slug": "x", "name": "구 조선식량영단 군산출장소", "_photos": [ph("s1")]},
          **{s: {"slug": s, "name": s, "_photos": [ph(s)]} for s in present.RELATED_ANY}}
    own = {"id": "a", "_places": [{"name": "대장봉", "_photos": [ph("d1")]}], "note": "대장봉"}
    rows = present.home_posts([own, {"id": "b", "note": "해망로의 식당에서 아침"},
                               {"id": "c", "note": "일본식 연립 가옥(나가야)"}, {"id": "d", "note": "일본 가옥 안"},
                               {"id": "e", "note": "아무 말"}], by)
    assert [r["related"] for r in rows] == [False, True, True, True, True]
    assert [r["photo"]["url"] for r in rows][:4] == ["d1", "h1", "j1", "s1"]   # each related place once
    assert rows[2]["place_short"] == "군산신흥동일본식가옥"
    assert rows[4]["place"]["slug"] == present.RELATED_ANY[0]
    assert present.home_posts([{"id": "z", "note": "x"}])[0]["photo"] is None   # without places: words, as before
