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
