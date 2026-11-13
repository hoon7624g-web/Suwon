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


# 날씨각 (weather.o2o.kr, the operator's own service — the weather card of the tab panel and the homes:
# templates/_side.html.j2, assets/weather.js; operator 2026-10-31): the browser tests answer its two APIs here, as they
# answer every other request, so nothing leaves the machine and a refused request does not log 'Failed to load
# resource' into the console their checks read. `day` is today in Korea (weather.js draws only today's answers).
# weather_answer: the day's slots (/v1/weather/today), three hours apart as the API's; feed_answer: the feed's hero
# (/v1/feed) — the sky (sky_mode), the score, 날씨각's words, the moon.
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


def feed_answer(day: str | None = None, sky_mode: str = "night") -> dict:
    import datetime as dt
    from zoneinfo import ZoneInfo
    day = day or dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    return {"result": {"success": True, "code": 0, "desc": "SUCCESS"}, "region_code": "5213000000",
            "region_name": "전북 군산시", "slot": sky_mode,
            "hero": {"now_at": f"{day}T19:48:00.000000+09:00", "sky_mode": sky_mode, "temp_c": 10.0, "feels_c": 9.7,
                     "humidity": 60, "discomfort": 52, "discomfort_label": "쾌적", "weather_score": 60,
                     "weather_slots": {"morning": 74, "day": 79, "evening": 69, "night": 60},
                     "top1": {"index_id": 9, "code": "running", "name": "러닝각", "icon": "running", "score": 82,
                              "summary": "오후 7시 10°, 바람 살랑"},
                     "bubble": "지금은 러닝각!", "moon_name": "기우는 달", "moon_pct": 64,
                     "status": [{"icon": "muggy", "label": "습도", "value": "보통", "tone": "normal", "detail": "60%"},
                                {"icon": "muggy", "label": "불쾌지수", "value": "쾌적", "tone": "normal", "detail": "52"},
                                {"icon": "mask", "label": "미세먼지", "value": "나쁨", "tone": "warn", "detail": "초미세먼지"}]}}


def weather_body(url: str, day: str | None = None, sky_mode: str = "night") -> dict:
    """The answer 날씨각 gives at this address: the feed's or the day's slots."""
    return feed_answer(day, sky_mode) if "/v1/feed" in url else weather_answer(day)


def route_weather(target, answer: dict | None = None, status: int = 200, feed: dict | None = None) -> None:
    """Answer weather.o2o.kr on a Playwright context or page (register it after a catch-all route: the last one wins):
    the feed and the day's slots (answer / feed replace them). The card's round fonts (Google Fonts, asked only once
    the card is drawn) get an empty stylesheet: the card is drawn in the site's font, nothing leaves the machine."""
    import json

    def fulfill(route):
        url = route.request.url
        body = (feed or feed_answer()) if "/v1/feed" in url else (answer or weather_answer())
        route.fulfill(status=status, body=json.dumps(body, ensure_ascii=False),
                      headers={"content-type": "application/json", "access-control-allow-origin": "*"})
    target.route("https://weather.o2o.kr/**", fulfill)
    target.route("https://fonts.googleapis.com/**", lambda route: route.fulfill(
        status=200, body="", headers={"content-type": "text/css; charset=utf-8", "access-control-allow-origin": "*"}))
