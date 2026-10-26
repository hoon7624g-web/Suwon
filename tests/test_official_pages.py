"""Official values of this city (tools/suwon_official.py) and its dated notices (data/suwon/notices.json) are what the
facility's own page says: every page read is stored (data/raw/suwon/official_pages.json: provider, checked_at, the
lines read), every number of a value stands on that page, and places.json carries each value with its page."""
import json
import re
from pathlib import Path

from tools import suwon_official as so

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "suwon"
PAGES = json.loads((ROOT / "data" / "raw" / "suwon" / "official_pages.json").read_text("utf-8"))
PLACES = {p["id"]: p for p in json.loads((DATA / "places.json").read_text("utf-8"))}
NUM = re.compile(r"\d[\d,:]*\d|\d")


def page_text(url: str) -> str:
    return re.sub(r"\s+", "", "".join(PAGES[url]["lines"]))


def test_every_page_is_stored_with_its_provider_and_date():
    for page in so.OFFICIAL_PAGES:
        assert page["url"] in PAGES, page["url"]
        assert PAGES[page["url"]]["checked_at"] == page["checked_at"]
        assert PAGES[page["url"]]["lines"]


def test_every_number_of_a_value_stands_on_its_page():
    for page in so.OFFICIAL_PAGES:
        text = page_text(page["url"])
        for item in page["places"]:
            for key, value in (item.get("facts") or {}).items():
                for n in NUM.findall(value):
                    assert n.replace(" ", "") in text, (page["provider"], item["name"], key, n)


def test_places_carry_each_value_with_its_page():
    for page in so.OFFICIAL_PAGES:
        for item in page["places"]:
            p = PLACES[item["id"]]
            assert p["name"] == item["name"]
            for key, value in (item.get("facts") or {}).items():
                src = (p.get("fact_sources") or {}).get(key) or {}
                held = (p["facts"].get(key) == value and src.get("provider") == page["provider"] and src.get("url") == page["url"]) \
                    or any(a["value"] == value and a.get("url") == page["url"] for a in (p.get("fact_alternatives") or {}).get(key, []))
                assert held, (item["name"], key, page["provider"])
            for key in item.get("confirms") or ():
                if p["facts"].get(key):
                    src = p["fact_sources"][key]
                    assert src.get("provider") == page["provider"] or src.get("confirmed_urls", {}).get(page["provider"]) == page["url"], \
                        (item["name"], key, page["provider"])


def test_no_value_without_a_page_and_no_portal_front_page():
    """No fact keeps a city-tourism source with no address of its own page (the hand-written values of 2026-10-23,
    '수원시 문화관광' with the portal's front page), and no fact or alternative comes from 카카오맵."""
    for p in PLACES.values():
        srcs = list((p.get("fact_sources") or {}).values()) + [a for v in (p.get("fact_alternatives") or {}).values() for a in v]
        for s in srcs:
            assert s.get("provider") not in ("카카오맵", "수원시 문화관광"), (p["name"], s)
            if s.get("provider") in so.OURS:
                assert s.get("url") in PAGES and not s["url"].endswith("/index.do"), (p["name"], s)


def test_notices_come_from_stored_pages():
    from pipeline import notices
    items = notices.load(DATA)
    assert notices.problems(items, PLACES) == []
    for n in items:
        assert n["url"] in PAGES, n["id"]
        text = page_text(n["url"])
        for t in (n.get("to"), n.get("last_entry")):
            if t:
                assert t in text, (n["id"], t)
