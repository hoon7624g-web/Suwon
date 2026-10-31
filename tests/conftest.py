"""Shared test helpers (pytest loads this first; tests import from it with `from conftest import …`)."""


# 날씨각 (weather.o2o.kr, the tab panel's weather module — templates/_side.html.j2, assets/weather.js; operator
# 2026-10-31): the browser tests answer its API here, as they answer every other request, so nothing leaves the
# machine and a refused request does not log 'Failed to load resource' into the console their checks read. `day` is
# today in Korea (weather.js shows only today's answer); the slots are three hours apart, as the API's.
def weather_answer(day: str | None = None) -> dict:
    import datetime as dt
    from zoneinfo import ZoneInfo
    day = day or dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    icons = ("cloud", "cloud", "sun", "sun", "sun", "sunset", "moon", "cloud")
    return {"result": {"success": True, "code": 0, "desc": "SUCCESS"}, "region_code": "4111500000",
            "region_name": "경기 수원시", "day": day, "issued_at": f"{day}T14:00:00+09:00", "headline": "낮 최고 17°, 저녁 9°",
            "slots": [{"at": f"{day}T{h:02d}:00:00+09:00", "label": f"{h}시", "temp_c": float(10 + i), "feels_c": float(10 + i),
                       "sky": 1, "rain_type": 1, "rain_prob": 10 * (i % 3), "humidity": 50, "wind_ms": 2.0,
                       "icon": icons[i], "tone": 1, "note": "구름 많음"} for i, h in enumerate(range(0, 24, 3))]}


def weather_feed(day: str | None = None, sky_mode: str = "night", moon_pct: int = 64) -> dict:
    """/v1/feed's hero as 날씨각 gives it (the card: sky, score, moon, the Korean lines)."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    day = day or dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    return {"result": {"success": True, "code": 0, "desc": "SUCCESS"}, "region_code": "4111500000",
            "region_name": "경기 수원시 팔달구", "slot": sky_mode,
            "hero": {"now_at": f"{day}T20:00:00+09:00", "sky_mode": sky_mode, "temp_c": 7.0, "feels_c": 7.0,
                     "humidity": 60, "weather_score": 60, "bubble": "지금은 러닝각!", "moon_name": "기우는 달",
                     "moon_pct": moon_pct, "top1": {"name": "러닝각", "summary": "오후 8시 7°, 바람 살랑"},
                     "status": [{"label": "습도", "value": "보통"}, {"label": "불쾌지수", "value": "쾌적"},
                                {"label": "미세먼지", "value": "보통"}]}}


def route_weather(target, answer: dict | None = None, status: int = 200, feed: dict | None = None) -> None:
    """Answer weather.o2o.kr on a Playwright context or page (register it after a catch-all route: the last one wins):
    /v1/feed with `feed` (weather_feed), /v1/weather/today with `answer` (weather_answer)."""
    import json

    def fulfill(route):
        url = route.request.url
        body = (feed or weather_feed()) if "/v1/feed" in url else (answer or weather_answer())
        route.fulfill(status=status, body=json.dumps(body, ensure_ascii=False),
                      headers={"content-type": "application/json", "access-control-allow-origin": "*"})
    target.route("https://weather.o2o.kr/**", fulfill)
