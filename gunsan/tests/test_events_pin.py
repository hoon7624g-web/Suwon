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
