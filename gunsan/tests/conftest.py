"""Shared test helpers."""
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def engine_both_values():
    """군산각 shows one value per fact since 2026-10-31 (site.json fact_conflicts 'primary', CLAUDE.md 3절 2항). The
    engine still shows both values with '출처마다 다름' on a site without that key, and the modules that check that
    behaviour on 군산각's own data (its real conflicting hours, fees, parking) read site.json without the key — the
    whole module, so module-scoped builds see it too. tests/test_fact_conflicts.py checks the one-value mode."""
    import pipeline.build as B
    orig = B._load

    def load(path, default=None):
        v = orig(path, default)
        if Path(path).name == "site.json" and isinstance(v, dict) and "fact_conflicts" in v:
            v = {k: x for k, x in v.items() if k != "fact_conflicts"}
        return v
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(B, "_load", load)
        yield


# 군산각's guide-31 is written for one value per fact: it names the timetable's 99 비응(환) time only. Read without
# fact_conflicts (engine_both_values), validate rightly asks the guide for the other source's time too
# (validate.transit_problems; tests/test_present.py checks both modes) — the one finding a whole-site validate in that
# mode is expected to give on 군산각's own data.
ONE_VALUE_PROSE = "transit.json 99번 비응(환): '매시 40분'가 guide-31 본문에 없음"


def without_one_value_prose(errors: list[str]) -> list[str]:
    return [e for e in errors if ONE_VALUE_PROSE not in e]


# 날씨각 (weather.o2o.kr, the tab panel's weather module — templates/_side.html.j2, assets/weather.js; operator
# 2026-10-31): the browser tests answer its API here, as they answer every other request, so nothing leaves the
# machine and a refused request does not log 'Failed to load resource' into the console their checks read. `day` is
# today in Korea (weather.js shows only today's answer); the slots are three hours apart, as the API's.
def weather_answer(day: str | None = None) -> dict:
    import datetime as dt
    from zoneinfo import ZoneInfo
    day = day or dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    icons = ("cloud", "cloud", "sun", "sun", "sun", "sunset", "moon", "cloud")
    return {"result": {"success": True, "code": 0, "desc": "SUCCESS"}, "region_code": "5213000000",
            "region_name": "전북 군산시", "day": day, "issued_at": f"{day}T14:00:00+09:00", "headline": "낮 최고 17°, 저녁 9°",
            "slots": [{"at": f"{day}T{h:02d}:00:00+09:00", "label": f"{h}시", "temp_c": float(10 + i), "feels_c": float(10 + i),
                       "sky": 1, "rain_type": 1, "rain_prob": 10 * (i % 3), "humidity": 50, "wind_ms": 2.0,
                       "icon": icons[i], "tone": 1, "note": "구름 많음"} for i, h in enumerate(range(0, 24, 3))]}


def route_weather(target, answer: dict | None = None, status: int = 200) -> None:
    """Answer weather.o2o.kr on a Playwright context or page (register it after a catch-all route: the last one wins)."""
    import json

    def fulfill(route):
        route.fulfill(status=status, body=json.dumps(answer or weather_answer(), ensure_ascii=False),
                      headers={"content-type": "application/json", "access-control-allow-origin": "*"})
    target.route("https://weather.o2o.kr/**", fulfill)
