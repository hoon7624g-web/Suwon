"""events.json pin_home (the first site's operator decision 2026-10-31, '홈에 … 고정') puts that edition first on the
home's event rows and news cards (present.pinned_first); the others keep ranked_events' order, and an edition that is
over is not there. Pinning is the operator's call: this site pins only what its operator names."""
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


def test_only_published_editions_are_pinned():
    """No edition is pinned without the operator (rule 7): a pinned one must be published and still dated."""
    ev = json.loads((ROOT / "data" / "suwon" / "events.json").read_text("utf-8"))
    for e in (e for e in ev if e.get("pin_home")):
        assert e.get("status") == "published" and e.get("end_date"), e.get("id")


# ------------------------------------------------------------------ 홈의 행사 띠 (군산 cf4ebcd8a·a0dc577a3, 2026-11-05 이식)
def test_event_start_time_only_for_one_day_editions_with_one_start():
    from pipeline.textutil import event_start_dt
    one = {"start_date": "2026-11-14", "end_date": "2026-11-14"}
    assert event_start_dt({**one, "playtime": "20:00 (약 30분)"}) == "2026-11-14T20:00+09:00"
    assert event_start_dt({**one, "playtime": "9:30~21:00"}) == "2026-11-14T09:30+09:00"
    assert event_start_dt({**one, "playtime": "화~일요일 10:00~17:00"}) == ""
    assert event_start_dt({**one, "playtime": "20:00", "alternatives": {"playtime": [{"value": "19:00"}]}}) == ""
    assert event_start_dt({"start_date": "2026-10-02", "end_date": "2026-10-05", "playtime": "10:00~21:00"}) == ""
    assert event_start_dt({**one}) == ""


def test_the_home_band_shows_only_a_pinned_edition_that_is_not_over():
    ev = {"id": "x", "pin_home": True, "highlights": ["야간 공연 — 무료", "약 1만 석", "부스 없음 — 안내 예정"],
          "pin_points": [0, 2, 9], "start_date": "2026-11-14", "end_date": "2026-11-14", "playtime": "20:00 (약 30분)",
          "page_media": {"guide": "g1", "series": ["g1", "g2", "no-such-guide"]}}
    r = {"ev": ev, "title": "2026 강변 축제 '밤을 물들이다'", "start": "2026-11-14", "last": "2026-11-14",
         "time": "20:00 (약 30분)", "days": 10, "place": "강변", "path": "/events/x/",
         "source": "시 보도자료 '축제 개최' (관광과, 2026-10-27)"}
    guides = [{"slug": "g1", "_path": "/guides/g1/", "title": "야경, 어디서 보나요"},
              {"slug": "g2", "_path": "/guides/g2/", "title": "주차", "label": "주차 안내"}]
    f = present.home_fest([{"ev": {"id": "a"}}, r], guides)
    assert f["h"] == "2026 강변 축제" and f["sub"] == "'밤을 물들이다'"
    # the record's own programme lines, split at ' — '; an index past the list is skipped, never filled
    assert f["points"] == [{"t": "야간 공연", "d": "무료"}, {"t": "부스 없음", "d": "안내 예정"}]
    assert f["when"] == "11월 14일(토)" and f["start_dt"] == "2026-11-14T20:00+09:00"
    assert f["src"] == "시 보도자료 (관광과, 2026-10-27)"
    assert [(s["path"], s["label"]) for s in f["series"]] == [("/guides/g1/", "야경"), ("/guides/g2/", "주차 안내")]
    # not pinned, or over (ranked_events leaves it out): no band
    assert present.home_fest([{"ev": {**ev, "pin_home": False}}]) is None
    assert present.home_fest([]) is None
