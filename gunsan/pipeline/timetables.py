"""군산 일출·일몰 시간표(/sun/)와 군산 교통 시간표(/transport/) — the two data pages of the operator's decision of
2026-10-31 ('새 공공데이터를 사이트에 싹 반영하고 검색엔진 노출·AI 인용을 각별히'). Korean pages; the view models here,
the templates templates/sun.html.j2 · transport.html.j2 (+ _timetables.html.j2), css/78-timetables.css, assets/sun.js.

/sun/ — data/<region>/almanac.json 'sun' (tools/almanac_gunsan.py: 한국천문연구원 출몰시각 정보, the '군산' point): every
date from the build day on, by month, as a real <table> (date · weekday · 시민박명 시작 · 일출 · 일몰 · 시민박명 끝). The
answer comes first: the build day written out ('10월 31일(토) 해 뜨는 시각 06:54 · 해 지는 시각 17:39', never '오늘'),
then figures computed from the table's own values only (the earliest sunset, the latest sunrise, the shortest day as
일출→일몰, 1월 1일's sunrise when the table holds it). assets/sun.js moves the answer to the visitor's own date
(Asia/Seoul) and marks its row. The places whose own page text (summary · 자세히 · FAQ answer — our sentences) names a
sunset (SUNSET) are listed with that sentence as the reason. almanac.json 'tide' (국립해양조사원 조석예보, none yet: the
agency's server answered 503 on 2026-10-31) adds a tide block to the same page when it exists (tide_vm) and nothing
at all while it does not.

/transport/ — data/<region>/transport_tago.json (tools/tago_gunsan.py: 국토교통부 TAGO 열차·고속버스·시외버스·국내항공,
the departures of one weekend day and one weekday, base_dates): per mode one card per pair (the Gunsan end ↔ the other
end), each direction a summary table (첫차 · 막차 · 하루 횟수 · 걸린 시간 · 요금 by grade; one column when both days are
the same) and every departure in a <details>. A direction TAGO returned nothing for reads '이 자료(TAGO)에 없음 — 운수사
확인' (never '운행 없음': the services leave out whole kinds of departures, the file's notes say which); a pair with
nothing either way is one line under its mode. The train fare is TAGO's one value for both classes (a note says so);
the flight fare TAGO returns as 0 is never printed ('확인 필요: 요금').

Both pages: WebPage + BreadcrumbList + Dataset (creator and publisher: the providing agency; isBasedOn: the portal page;
license: the portal's 이용허락범위 as its dataset page states it, PORTAL_LICENSE; dateModified: the data's checked date —
machine-readable only, operator decision 2026-10-09), sitemap, llms.txt and a few summary lines in llms-full.txt. No
check date is printed; the schedule days and the table's period are (validate.visible_check_dates allows them)."""
from __future__ import annotations

import datetime as dt
import re

from .jsonld import breadcrumb, webpage
from .textutil import squash_ws

SUN_PATH = "/sun/"
TRANSPORT_PATH = "/transport/"
WEEK = "월화수목금토일"
# the words that say a place is a sunset spot, in our own sentences on its page
# ('일몰' only with a viewing word: '일출부터 일몰까지' is an opening time, not a view)
SUNSET = re.compile(r"노을|해넘이|낙조|석양|일몰\s*(?:명소|풍경|경관|감상|(?:을|이)\s*(?:보|볼|아름))")
PORTAL = re.compile(r"data\.go\.kr/data/(\d+)")
PORTAL_HOME = "https://www.data.go.kr/"
KOGL1 = "https://www.kogl.or.kr/info/licenseType1.do"
# 공공데이터포털 '이용허락범위' as each dataset page states it (read 2026-10-31): (the words shown, a licence page or '')
PORTAL_LICENSE = {
    "15012688": ("이용허락범위 제한 없음", ""),                 # 한국천문연구원_출몰시각 정보
    "15098552": ("이용허락범위 제한 없음", ""),                 # 국토교통부_(TAGO)_열차정보
    "15098522": ("이용허락범위 제한 없음", ""),                 # 국토교통부_(TAGO)_고속버스정보
    "15098541": ("이용허락범위 제한 없음", ""),                 # 국토교통부_(TAGO)_시외버스정보
    "15098526": ("이용허락범위 제한 없음", ""),                 # 국토교통부_(TAGO)_국내항공운항정보
    "15156018": ("공공누리 제1유형(출처표시)", KOGL1),          # 해양수산부 국립해양조사원_조석예보(고, 저조)
}
# the guides a timetable page leads to (and that link back to it, templates/guide.html.j2): guides.json ids
TRANSPORT_GUIDES = ("guide-12", "guide-33", "guide-31", "guide-01")
SUN_MONTH_OPEN = 7   # the first month opens with the next one when it has fewer rows than this


# ----------------------------------------------------------------------------- small helpers
def clock(v) -> str:
    """'0654', '06:54' → '06:54'; '' for anything else."""
    s = re.sub(r"\s+", "", str(v or ""))
    m = re.fullmatch(r"(\d{1,2}):?(\d{2})", s)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def mins(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def dur(m: int) -> str:
    """Minutes as '10시간 45분', '2시간', '49분'."""
    h, r = divmod(int(m), 60)
    return f"{h}시간 {r}분" if h and r else f"{h}시간" if h else f"{r}분"


def md(d: dt.date) -> str:
    return f"{d.month}월 {d.day}일"


def mdw(d: dt.date) -> str:
    """'11월 1일(일)': an absolute date, never '오늘'."""
    return f"{d.month}월 {d.day}일({WEEK[d.weekday()]})"


def when(rows: list[dict]) -> str:
    """The days of rows (date order) in words: one day, a run ('11월 29일(일)~12월 12일(토)') or the span and how many
    days in it ('12월 16일(수)~12월 26일(토) 중 8일')."""
    ds = [r["d"] for r in rows]
    if len(ds) == 1:
        return mdw(ds[0])
    run = all((b - a).days == 1 for a, b in zip(ds, ds[1:]))
    return f"{mdw(ds[0])}~{mdw(ds[-1])}" + ("" if run else f" 중 {len(ds)}일")


def won(n) -> str:
    return f"{int(n):,}원"


def portal_license(url: str | None) -> dict | None:
    """{'name', 'url', 'portal'} of a 공공데이터포털 dataset page this module knows the 이용허락범위 of; None otherwise."""
    m = PORTAL.search(url or "")
    lic = PORTAL_LICENSE.get(m.group(1)) if m else None
    if not lic:
        return None
    return {"name": lic[0], "url": lic[1], "portal": url}


def _sentences(text) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", squash_ws(text)) if s]


def region_of(S) -> str:
    return squash_ws((getattr(S, "site", None) or {}).get("region")) or "군산"


def org(name: str) -> dict:
    return {"@type": "Organization", "name": name}


def dataset_node(page_url: str, frag: str, name: str, description: str, provider: str, based_on, coverage: str,
                 modified: str, variables: list[str], lic: dict | None, place: dict | None = None) -> dict:
    """A schema.org Dataset for a table the page shows: every string is on the page (validate.jsonld_visibility), the
    portal page as isBasedOn, the providing agency as creator and publisher, dateModified the data's checked date."""
    node = {"@type": "Dataset", "@id": f"{page_url}#{frag}", "name": name, "description": description,
            "url": page_url, "inLanguage": "ko-KR", "creator": org(provider), "publisher": org(provider),
            # an outside page is named with sameAs: every JSON-LD url/@id/item is on the site's own domain (validate)
            "isBasedOn": based_on, "includedInDataCatalog": {"@type": "DataCatalog", "name": "공공데이터포털",
                                                            "sameAs": PORTAL_HOME},
            "temporalCoverage": coverage, "variableMeasured": variables}
    if place:
        node["spatialCoverage"] = place
    if lic:
        node["license"] = lic["url"] or {"@type": "CreativeWork", "name": lic["name"], "sameAs": lic["portal"]}
    if modified:
        node["dateModified"] = modified
    return node


# ----------------------------------------------------------------------------- /sun/
def sun_rows(S) -> list[dict]:
    """almanac.json 'sun' from the build day on, in date order: {iso, d, md, dow, we, dawn, rise, set, dusk, day, day_t};
    a day without both its sunrise and its sunset is left out."""
    raw = (getattr(S, "almanac", None) or {}).get("sun") or {}
    today = str(S.today)[:10]
    out = []
    for iso in sorted(raw):
        v = raw[iso] if isinstance(raw[iso], dict) else {}
        try:
            d = dt.date.fromisoformat(iso)
        except ValueError:
            continue
        rise, sset = clock(v.get("sunrise")), clock(v.get("sunset"))
        if iso < today or not (rise and sset) or mins(sset) <= mins(rise):
            continue
        day = mins(sset) - mins(rise)
        out.append({"iso": iso, "d": d, "md": md(d), "dow": WEEK[d.weekday()], "we": d.weekday() >= 5,
                    "dawn": clock(v.get("civil_dawn")), "rise": rise, "set": sset, "dusk": clock(v.get("civil_dusk")),
                    "day": day, "day_t": dur(day)})
    return out


def sunset_spots(S) -> list[dict]:
    """Attractions this build publishes whose own sentences (summary, then 자세히, then FAQ answers — the text we wrote
    for the page) name a sunset: {e, name, path, type, area, line}, line being the first such sentence; by name."""
    out = []
    for e in S.entities:
        if e.get("kind") != "attraction":
            continue
        texts = ([e.get("summary")] + [d.get("text") for d in e.get("details") or [] if isinstance(d, dict)]
                 + [f.get("a") for f in e.get("faq") or [] if isinstance(f, dict)])
        line = next((s for t in texts for s in _sentences(t) if SUNSET.search(s)), "")
        if line:
            out.append({"e": e, "name": e["name"], "path": e["_path"], "type": squash_ws(e.get("_type")),
                        "area": squash_ws(e.get("_area")), "line": line})
    return sorted(out, key=lambda x: x["name"])


def _src(alm: dict, part: str) -> dict:
    return ((alm.get("sources") or {}).get(part) or {}) if isinstance(alm.get("sources"), dict) else {}


def tide_vm(S) -> dict | None:
    """almanac.json 'tide' from the build day on (none until the agency answers): {stations: [{code, name, months:
    [{label, rows: [{iso, md, dow, we, high: [{t, cm}], low}]}]}], src}; None without any station day."""
    alm = getattr(S, "almanac", None) or {}
    today = str(S.today)[:10]
    stations = []
    for code, st in sorted(((alm.get("tide") or {}) if isinstance(alm.get("tide"), dict) else {}).items(),
                           key=lambda kv: squash_ws((kv[1] or {}).get("name")) if isinstance(kv[1], dict) else ""):
        if not isinstance(st, dict):
            continue
        months: list[dict] = []
        for iso in sorted(st.get("days") or {}):
            if iso < today:
                continue
            try:
                d = dt.date.fromisoformat(iso)
            except ValueError:
                continue
            pts = []
            for x in st["days"][iso] or []:
                if not isinstance(x, dict):
                    continue
                t, typ = clock(x.get("time")), squash_ws(x.get("type"))
                k = "high" if re.search(r"만조|고조", typ) else "low" if re.search(r"간조|저조", typ) else ""
                try:
                    cm = int(round(float(x.get("level_cm"))))
                except (TypeError, ValueError):
                    cm = None
                if t and k:
                    pts.append({"t": t, "k": k, "cm": cm})
            if not pts:
                continue
            pts.sort(key=lambda p: p["t"])
            row = {"iso": iso, "d": d, "md": md(d), "dow": WEEK[d.weekday()], "we": d.weekday() >= 5,
                   "high": [p for p in pts if p["k"] == "high"], "low": [p for p in pts if p["k"] == "low"]}
            key = iso[:7]
            if not months or months[-1]["key"] != key:
                months.append({"key": key, "label": f"{d.year}년 {d.month}월", "rows": []})
            months[-1]["rows"].append(row)
        if months:
            name = squash_ws(st.get("name")) or code
            stations.append({"code": code, "id": f"tide-{re.sub(r'[^0-9A-Za-z_-]', '', code)}", "name": name,
                             "months": months, "first": months[0]["rows"][0]["iso"], "last": months[-1]["rows"][-1]["iso"]})
    if not stations:
        return None
    src = _src(alm, "tide")
    return {"stations": stations, "provider": squash_ws(src.get("provider")) or "국립해양조사원",
            "dataset": squash_ws(src.get("dataset")), "url": src.get("url") or "", "lic": portal_license(src.get("url")),
            "checked": str(src.get("checked_at") or "")[:10],
            "first": min(s["first"] for s in stations), "last": max(s["last"] for s in stations)}


def sun_vm(S) -> dict | None:
    """The /sun/ page (see the module note); None when almanac.json has no day from the build day on."""
    rows = sun_rows(S)
    if not rows:
        return None
    alm = getattr(S, "almanac", None) or {}
    src = _src(alm, "sun")
    lead = rows[0]
    months: list[dict] = []
    for r in rows:
        key = r["iso"][:7]
        if not months or months[-1]["key"] != key:
            months.append({"key": key, "id": f"m-{key}", "label": f"{r['d'].year}년 {r['d'].month}월",
                           "short": f"{r['d'].month}월", "rows": []})
        months[-1]["rows"].append(r)
    for i, m in enumerate(months):
        rs = m["rows"]
        rises, sets = sorted(r["rise"] for r in rs), sorted(r["set"] for r in rs)
        m["rise"] = rises[0] if rises[0] == rises[-1] else f"{rises[0]}–{rises[-1]}"
        m["set"] = sets[0] if sets[0] == sets[-1] else f"{sets[0]}–{sets[-1]}"
        m["open"] = i == 0 or (i == 1 and len(months[0]["rows"]) < SUN_MONTH_OPEN)
        m["days"] = f"{rs[0]['md']}~{rs[-1]['md']}" if len(rs) > 1 else rs[0]["md"]
    facts = []
    if len(rows) > 1:
        es = min(r["set"] for r in rows)
        lr = max(r["rise"] for r in rows)
        sd = min(r["day"] for r in rows)
        facts = [{"k": "해가 가장 일찍 지는 때", "v": es, "when": when([r for r in rows if r["set"] == es])},
                 {"k": "해가 가장 늦게 뜨는 때", "v": lr, "when": when([r for r in rows if r["rise"] == lr])},
                 {"k": "낮이 가장 짧은 때(일출~일몰)", "v": dur(sd), "when": when([r for r in rows if r["day"] == sd])}]
        jan1 = next((r for r in rows if r["iso"][5:] == "01-01"), None)
        if jan1 and jan1 is not lead:
            facts.append({"k": f"{jan1['d'].year}년 1월 1일 해 뜨는 시각", "v": jan1["rise"],
                          "when": f"{mdw(jan1['d'])} · 해 지는 시각 {jan1['set']}"})
    lic = portal_license(src.get("url"))
    first, last = rows[0]["d"], rows[-1]["d"]
    period = f"{first.year}년 {md(first)}~{last.year}년 {md(last)}" if first.year != last.year else \
        f"{first.year}년 {md(first)}~{md(last)}"
    tide = tide_vm(S)
    point = squash_ws(src.get("location")) or "군산"
    return {"rows": rows, "lead": {**lead, "lab": mdw(lead["d"])}, "months": months, "facts": facts,
            "n": len(rows), "period": period, "coverage": f"{rows[0]['iso']}/{rows[-1]['iso']}",
            "spots": sunset_spots(S), "tide": tide,
            "src": {"provider": squash_ws(src.get("provider")) or "한국천문연구원", "dataset": squash_ws(src.get("dataset")),
                    "url": src.get("url") or "", "point": point, "lat": src.get("lat"), "lng": src.get("lng"),
                    "lic": lic, "checked": str(src.get("checked_at") or "")[:10]}}


SUN_DESC = "{p} '{pt}' 지점의 날짜별 일출·일몰·시민박명 시각을 옮긴 표입니다. 기간은 {period}({n}일)이고, 섬에서는 1~2분 다를 수 있습니다."


def sun_page(S, V: dict) -> dict:
    """title, description, h1 and JSON-LD of /sun/ (every JSON-LD string is on the page)."""
    tide = bool(V["tide"])
    r = region_of(S)
    title = (f"{r} 일출·일몰·물때 시간표 — 날짜별 해 뜨는 시각·해 지는 시각·만조·간조" if tide
             else f"{r} 일출·일몰 시간표 — 날짜별 해 뜨는 시각·해 지는 시각")
    lead, s = V["lead"], V["src"]
    head = f"{r} {lead['lab']} 일출 {lead['rise']}·일몰 {lead['set']}."
    desc = next((x for x in (f"{head} {V['period']} 날짜별 해 뜨는·지는 시각과 시민박명을 {s['provider']} 값으로 정리했습니다.",
                             f"{head} 날짜별 해 뜨는·지는 시각과 시민박명을 {s['provider']} 값으로 정리했습니다.",
                             f"{head} 날짜별 해 뜨는·지는 시각을 정리했습니다.") if len(x) <= 80), head)
    url = S.abs(SUN_PATH)
    crumbs = [("홈", S.site_url + "/"), (f"{r} 일출·일몰 시간", url)]
    ds_name = f"{r} 일출·일몰·시민박명 시각표"
    ds_desc = SUN_DESC.format(p=s["provider"], pt=s["point"], period=V["period"], n=V["n"])
    place = {"@type": "Place", "name": s["point"]}
    if s["lat"] is not None and s["lng"] is not None:
        place["geo"] = {"@type": "GeoCoordinates", "latitude": s["lat"], "longitude": s["lng"]}
    graph = [webpage(url, title, S.site_url, about_id=f"{url}#sun", date_modified=s["checked"] or None,
                     based_on=[s["url"]] + ([V["tide"]["url"]] if tide else [])),
             breadcrumb(crumbs),
             dataset_node(url, "sun", ds_name, ds_desc, s["provider"], s["url"], V["coverage"], s["checked"],
                          ["시민박명 시작", "일출", "일몰", "시민박명 끝"], s["lic"], place)]
    if tide:
        T = V["tide"]
        T["ds_name"] = f"{r} 바다 물때(만조·간조) 시각표"
        T["ds_desc"] = (f"{T['provider']} 조석예보의 관측소별 만조·간조 시각과 예측 높이를 날짜별로 옮긴 표입니다. "
                        f"관측소 {len(T['stations'])}곳.")
        T["coverage"] = f"{T['first']}/{T['last']}"
        graph.append(dataset_node(url, "tide", T["ds_name"], T["ds_desc"], T["provider"], T["url"], T["coverage"],
                                  T["checked"], ["만조", "간조"], T["lic"], {"@type": "Place", "name": r}))
    return {"title": title, "description": desc, "canonical": url, "crumbs": crumbs, "ds_name": ds_name,
            "ds_desc": ds_desc, "graph": {"@context": "https://schema.org", "@graph": graph}}


# ----------------------------------------------------------------------------- /transport/
MODES = (("train", "열차"), ("express_bus", "고속버스"), ("intercity_bus", "시외버스"), ("flight", "항공"))
MODE_WORDS = {   # the summary table's first / last row words, the count's unit, the list's class and number columns
    "train": {"first": "첫차", "last": "막차", "unit": "회", "kind": "열차", "no": "열차 번호"},
    "express_bus": {"first": "첫차", "last": "막차", "unit": "회", "kind": "등급", "no": ""},
    "intercity_bus": {"first": "첫차", "last": "막차", "unit": "회", "kind": "등급", "no": ""},
    "flight": {"first": "첫 편", "last": "마지막 편", "unit": "편", "kind": "항공사", "no": "편명"},
}
# what the source leaves out, per mode (transport_tago.json notes, in the page's words)
MODE_NOTES = {
    "train": "열차 요금은 TAGO가 등급 구분 없이 준 값입니다 — 같은 구간이면 무궁화호·새마을호가 같은 값으로 나옵니다. "
             "등급별 운임은 코레일에서 확인하세요.",
    "intercity_bus": "TAGO 시외버스정보는 군산에서 떠나는 배차를 주지 않고, 전주·익산 노선도 나오지 않습니다(도착편만 일부 "
                     "터미널에서 나옵니다). 군산에서 떠나는 시외버스는 버스타고·티머니에서 조회하세요.",
    "flight": "확인 필요: 요금 — TAGO 항공 운항정보에는 요금 값이 없습니다(항공사에서 확인).",
}
NONE_TEXT = "이 자료(TAGO)에 없음"
NONE_CHECK = "운수사 확인"
NEXT_DAY = "다음 날"


def _row(mode: str, x: dict) -> dict:
    fare = x.get("fare")
    try:
        fare = int(fare) if fare is not None and int(fare) > 0 else None
    except (TypeError, ValueError):
        fare = None
    return {"dep": clock(x.get("dep_hm")), "dep_next": bool(x.get("dep_plus_days")), "arr": clock(x.get("arr_hm")),
            "arr_next": bool(x.get("arr_plus_days")),
            "kind": squash_ws(x.get("airline") if mode == "flight" else x.get("type")),
            "no": squash_ws(x.get("no")) if mode in ("train", "flight") else "",
            "fare": won(fare) if fare and mode != "flight" else ""}


def _fares(mode: str, fares) -> str:
    """'21,600원(무궁화호·새마을호)' when every class has the one same fare, else '고속 16,400원 · 우등 23,900원 …'
    (cheapest first); '' for a flight (TAGO returns 0: no fare) or none."""
    if mode == "flight" or not isinstance(fares, dict):
        return ""
    items = []
    for g, vs in fares.items():
        vals = sorted({int(v) for v in (vs or []) if isinstance(v, (int, float)) and v > 0})
        if vals:
            items.append((squash_ws(g), vals))
    if not items:
        return ""
    if len(items) > 1 and len({tuple(v) for _, v in items}) == 1:
        return f"{'·'.join(won(v) for v in items[0][1])}({'·'.join(g for g, _ in items)})"
    items.sort(key=lambda gv: (gv[1][0], gv[0]))
    return " · ".join(f"{g} {'·'.join(won(v) for v in vals)}" for g, vals in items)


def _summary(mode: str, route: dict, rows: list[dict]) -> dict | None:
    """One direction on one day: {first, last, count, time, fare} as the page prints them; None for no departures."""
    n = int(route.get("count") or 0)
    if n <= 0:
        return None
    W = MODE_WORDS[mode]
    first, last = clock(route.get("first")), clock(route.get("last"))
    nxt = lambda t: any(r["dep"] == t and r["dep_next"] for r in rows)   # noqa: E731 — a departure past midnight
    m = sorted(int(x) for x in route.get("minutes") or [] if isinstance(x, (int, float)))
    first = first + (f"({NEXT_DAY})" if first and nxt(first) else "")
    last = last + (f"({NEXT_DAY})" if last and nxt(last) else "")
    return {"first": first, "last": last, "span": f"{first}–{last}" if first and last else first or last,
            "count": f"{n}{W['unit']}", "n": n,
            "time": "" if not m else dur(m[0]) if m[0] == m[-1] else f"{dur(m[0])}~{dur(m[-1])}",
            "fare": _fares(mode, route.get("fares"))}


def transport_vm(S) -> dict | None:
    """The /transport/ page (see the module note); None without transport_tago.json routes."""
    doc = getattr(S, "transport", None) or {}
    region = region_of(S)   # the region's end of a pair: 군산, 군산대야, 군산공항
    routes = [r for r in doc.get("routes") or [] if isinstance(r, dict)]
    if not routes:
        return None
    days = []
    for key, v in (doc.get("base_dates") or {}).items():
        try:
            d = dt.date.fromisoformat(str((v or {}).get("date")))
        except ValueError:
            continue
        days.append({"key": key, "iso": d.isoformat(), "d": d, "lab": mdw(d)})
    days.sort(key=lambda x: x["iso"])
    if not days:
        return None
    lab = {x["key"]: x["lab"] for x in days}
    keys = [x["key"] for x in days]
    both = days[0]["lab"] + "·" + (f"{days[1]['d'].day}일({WEEK[days[1]['d'].weekday()]})"
                                  if len(days) == 2 and days[1]["d"].month == days[0]["d"].month else
                                  "·".join(x["lab"] for x in days[1:]))
    srcs = doc.get("sources") or {}
    modes = []
    for mode, label in MODES:
        W = MODE_WORDS[mode]
        rows_by: dict[tuple, list[dict]] = {}
        for x in doc.get(mode) or []:
            if isinstance(x, dict):
                rows_by.setdefault((x.get("from"), x.get("to"), x.get("day")), []).append(_row(mode, x))
        for rs in rows_by.values():
            rs.sort(key=lambda r: (r["dep_next"], r["dep"]))
        pairs: dict[tuple, dict] = {}
        for r in routes:
            if r.get("mode") != mode or r.get("day") not in lab:
                continue
            frm, to = squash_ws(r.get("from")), squash_ws(r.get("to"))
            home = frm if frm.startswith(region) else to if to.startswith(region) else ""
            if not home:
                continue
            other = to if home == frm else frm
            p = pairs.setdefault((home, other), {"home": home, "other": other, "out": {}, "in": {}})
            p["out" if frm == home else "in"][r["day"]] = r
        cards, missing = [], []
        for (home, other), p in pairs.items():
            dirs = []
            for way, frm, to in (("out", home, other), ("in", other, home)):
                sums = {k: _summary(mode, p[way][k], rows_by.get((frm, to, k), [])) for k in keys if k in p[way]}
                lists = {k: rows_by.get((frm, to, k), []) for k in keys if sums.get(k)}
                d = {"way": way, "from": frm, "to": to, "id": "", "none": not any(sums.values())}
                if not d["none"]:
                    same = len(sums) == len(keys) and all(sums[k] for k in keys) and \
                        len({tuple(sorted((a, b) for a, b in sums[k].items())) for k in keys}) == 1
                    d["cols"] = [{"lab": both, "s": sums[keys[0]]}] if same else \
                        [{"lab": lab[k], "s": sums.get(k)} for k in keys]
                    d["rows"] = [(fld, w) for fld, w in (("span", f"{W['first']}–{W['last']}"), ("count", "하루 횟수"),
                                                         ("time", "걸린 시간"), ("fare", "요금"))
                                 if any(c["s"] and c["s"][fld] for c in d["cols"])]
                    tup = lambda rs: [tuple(sorted(r.items())) for r in rs]   # noqa: E731
                    lsame = len(lists) == len(keys) and len({str(tup(lists[k])) for k in keys}) == 1
                    d["lists"] = [{"lab": both, "rows": lists[keys[0]], "same": True}] if lsame else \
                        [{"lab": lab[k], "rows": lists[k], "same": False} for k in keys if k in lists]
                    d["counts"] = d["cols"][0]["s"]["count"] if len(d["cols"]) == 1 else \
                        " · ".join(f"{c['lab']} {c['s']['count']}" for c in d["cols"] if c["s"])
                    d["no_fare"] = mode == "flight"
                dirs.append(d)
            if all(d["none"] for d in dirs):
                missing.append(f"{home}↔{other}")
                continue
            cid = f"{mode}-{len(cards) + 1}"
            for d in dirs:
                d["id"] = f"{cid}-{d['way']}"
            cards.append({"id": cid, "home": home, "other": other, "dirs": dirs,
                          "n": max((c["s"]["n"] for d in dirs if not d["none"] for c in d["cols"] if c["s"]), default=0)})
        if not cards and not missing:
            continue
        # a direction TAGO leaves out on every pair of the mode (시외버스: no departure from Gunsan) is said once under
        # the mode, not on each card; a card left with one direction is titled by it
        none_ways = []
        if len(cards) > 1:
            for way in ("out", "in"):
                if all(any(d["way"] == way and d["none"] for d in c["dirs"]) for c in cards):
                    homes = "·".join(dict.fromkeys(c["home"] for c in cards))
                    none_ways.append(f"{homes} → 각 도착지" if way == "out" else f"각 출발지 → {homes}")
                    for c in cards:
                        c["dirs"] = [d for d in c["dirs"] if d["way"] != way]
        for c in cards:
            one = c["dirs"][0]
            c["title"] = f"{one['from']} → {one['to']}" if len(c["dirs"]) == 1 else f"{c['home']} ↔ {c['other']}"
        src = srcs.get(mode) or {}
        modes.append({"mode": mode, "id": f"tp-{mode.replace('_', '-')}", "label": label, "w": W, "cards": cards,
                      "single": all(len(c["dirs"]) == 1 for c in cards), "none_ways": none_ways,
                      "missing": missing, "note": MODE_NOTES.get(mode, ""),
                      "src": {"provider": squash_ws(src.get("provider")), "dataset": squash_ws(src.get("dataset")),
                              "url": src.get("url") or "", "lic": portal_license(src.get("url")),
                              "checked": str(src.get("checked_at") or "")[:10]}})
    if not any(m["cards"] for m in modes):
        return None
    # the answer first: per mode its busiest direction out of Gunsan (else into it) on the later day (a weekday)
    tiles = []
    for m in modes:
        best = None
        for c in m["cards"]:
            for d in c["dirs"]:
                if d["none"]:
                    continue
                s = d["cols"][-1]["s"] or next((x["s"] for x in d["cols"] if x["s"]), None)
                rank = (d["way"] == "out", s["n"] if s else 0)
                if s and (best is None or rank > best[0]):
                    best = (rank, d, s, c)
        if best:
            _, d, s, c = best
            counts = sorted({x["s"]["n"] for x in d["cols"] if x["s"]})
            n_text = f"{counts[0]}{m['w']['unit']}" if len(counts) == 1 else f"{counts[0]}~{counts[-1]}{m['w']['unit']}"
            tiles.append({"label": m["label"], "href": f"#{c['id']}", "route": f"{d['from']} → {d['to']}",
                          "count": n_text, "span": f"{s['first']}–{s['last']}"})
    checked = max((m["src"]["checked"] for m in modes if m["src"]["checked"]), default="")
    providers = list(dict.fromkeys(m["src"]["provider"] for m in modes if m["src"]["provider"]))
    lic_names = list(dict.fromkeys(m["src"]["lic"]["name"] for m in modes if m["src"]["lic"]))
    return {"days": days, "both": both, "both_y": f"{days[0]['d'].year}년 {both}", "modes": modes, "tiles": tiles,
            "checked": checked,
            "provider": "·".join(providers) or "국토교통부", "lic": lic_names[0] if len(lic_names) == 1 else "",
            "coverage": f"{days[0]['iso']}/{days[-1]['iso']}",
            "guides": [S.guide_by_id[g] for g in TRANSPORT_GUIDES if g in (getattr(S, "guide_by_id", None) or {})]}


def transport_page(S, V: dict) -> dict:
    """title, description, h1 and JSON-LD of /transport/."""
    url = S.abs(TRANSPORT_PATH)
    r = region_of(S)
    title = f"{r} 교통 시간표 — {r}역 기차·고속버스·시외버스·{r}공항 첫차·막차·요금"
    labels = [t["label"] for t in V["tiles"]]
    desc = next((x for x in (
        f"국토교통부 TAGO {V['both']} 배차로 {r}역 기차, 고속·시외버스, {r}공항 항공편의 첫차·막차·하루 횟수·요금을 정리했습니다.",
        f"TAGO {V['both']} 배차로 {r} 기차·고속버스·시외버스·항공편의 첫차·막차·하루 횟수·요금을 정리했습니다.",
        f"{r} 기차·고속버스·시외버스·항공편의 첫차·막차·하루 횟수·요금(TAGO {V['both']} 배차).") if len(x) <= 80), "")
    crumbs = [("홈", S.site_url + "/"), (f"{r} 교통 시간표", url)]
    ds_name = f"{r} 오가는 열차·고속버스·시외버스·항공 배차표"
    ds_desc = (f"{V['provider']} TAGO의 {V['both']} 하루 배차에서 {r}을 오가는 {'·'.join(labels)}의 출발·도착 시각과 "
               "요금을 노선별로 옮긴 표입니다.")
    portal = [m["src"]["url"] for m in V["modes"] if m["src"]["url"]]
    lic = next((m["src"]["lic"] for m in V["modes"] if m["src"]["lic"]), None) if V["lic"] else None
    graph = [webpage(url, title, S.site_url, about_id=f"{url}#transport", date_modified=V["checked"] or None,
                     based_on=portal),
             breadcrumb(crumbs),
             dataset_node(url, "transport", ds_name, ds_desc, V["provider"], portal if len(portal) > 1 else portal[0],
                          V["coverage"], V["checked"], ["출발", "도착", "요금"], lic, {"@type": "Place", "name": r})]
    return {"title": title, "description": desc, "canonical": url, "crumbs": crumbs, "ds_name": ds_name,
            "ds_desc": ds_desc, "graph": {"@context": "https://schema.org", "@graph": graph}}


# ----------------------------------------------------------------------------- llms.txt / llms-full.txt
def llms_short(S, sun: dict | None, tr: dict | None) -> list[str]:
    if not (sun or tr):
        return []
    out = ["## 해·교통 시각표"]
    if sun:
        out.append(f"- [{region_of(S)} 일출·일몰 시간표]({S.abs(SUN_PATH)}): {sun['src']['provider']} '{sun['src']['point']}' 지점의 "
                   f"날짜별 일출·일몰·시민박명 시각({sun['period']}, {sun['n']}일)"
                   + (" — 물때(만조·간조) 포함" if sun["tide"] else "") + ".")
    if tr:
        out.append(f"- [{region_of(S)} 교통 시간표]({S.abs(TRANSPORT_PATH)}): 국토교통부 TAGO {tr['both_y']} 배차 — "
                   f"{'·'.join(m['label'] for m in tr['modes'] if m['cards'])}의 노선별 첫차·막차·하루 횟수·걸린 시간·요금.")
    return out + [""]


def _dir_line(mode: dict, d: dict) -> str:
    parts = []
    for c in d["cols"]:
        s = c["s"]
        if not s:
            parts.append(f"{c['lab']} {NONE_TEXT}")
            continue
        bits = [s["count"], f"{mode['w']['first']} {s['first']}", f"{mode['w']['last']} {s['last']}"]
        if s["time"]:
            bits.append(f"걸린 시간 {s['time']}")
        if s["fare"]:
            bits.append(f"요금 {s['fare']}")
        parts.append((f"{c['lab']}: " if len(d["cols"]) > 1 else "") + ", ".join(bits))
    return f"- {d['from']} → {d['to']} {mode['label']}: " + " / ".join(parts)


def llms_full(S, sun: dict | None, tr: dict | None) -> list[str]:
    out = []
    if sun:
        s = sun["src"]
        out += [f"## {region_of(S)} 일출·일몰 시간 ({s['provider']} 출몰시각, '{s['point']}' 지점)", f"URL: {S.abs(SUN_PATH)}",
                f"기간: {sun['period']}({sun['n']}일). 고군산군도 등 섬에서는 1~2분 다를 수 있음."]
        lead = sun["lead"]
        out.append(f"- {lead['lab']}: 시민박명 시작 {lead['dawn']}, 일출 {lead['rise']}, 일몰 {lead['set']}, "
                   f"시민박명 끝 {lead['dusk']}, 낮 길이 {lead['day_t']}")
        for m in sun["months"]:
            r0, r1 = m["rows"][0], m["rows"][-1]
            out.append(f"- {m['label']}({m['days']}): 일출 {m['rise']}, 일몰 {m['set']} "
                       f"— {r0['md']} {r0['rise']}/{r0['set']}, {r1['md']} {r1['rise']}/{r1['set']}")
        for f in sun["facts"]:
            out.append(f"- {f['k']}: {f['v']} ({f['when']})")
        if sun["spots"]:
            out.append("- 해넘이·노을이 장소 페이지에 적힌 곳: " + ", ".join(f"{x['name']}({S.abs(x['path'])})" for x in sun["spots"]))
        if sun["tide"]:
            T = sun["tide"]
            out.append(f"- 물때(만조·간조): {T['provider']} 조석예보, 관측소 " + ", ".join(st["name"] for st in T["stations"]))
        out.append("")
    if tr:
        out += [f"## {region_of(S)} 교통 시간표 (국토교통부 TAGO, {tr['both_y']} 배차)", f"URL: {S.abs(TRANSPORT_PATH)}",
                "TAGO에 0건인 구간은 운행이 없다는 뜻이 아니다(운수사 확인). 열차 요금은 등급 구분 없는 TAGO 값, 항공 요금은 자료에 없음."]
        for m in tr["modes"]:
            for c in m["cards"]:
                for d in c["dirs"]:
                    out.append(_dir_line(m, d) if not d["none"] else
                               f"- {d['from']} → {d['to']} {m['label']}: {NONE_TEXT} — {NONE_CHECK}")
            for x in m["none_ways"]:
                out.append(f"- {x} {m['label']}: {NONE_TEXT} — {NONE_CHECK}")
            if m["missing"]:
                out.append(f"- {m['label']} {NONE_TEXT}(양방향): " + ", ".join(m["missing"]))
        out.append("")
    return out
