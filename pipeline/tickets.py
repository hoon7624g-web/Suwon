"""Combined admission tickets (통합권) as data — the first city's review 2026-10-17 G02 · D04 (operator's request).

The site assistant gave three totals for one family for the same combined ticket: the fee tables were text in each
place's facts, the age of '어린이' and who enters free were not in the knowledge, and the model added the sums itself,
more than once. data/<region>/tickets.json holds such tables as values (a city without any keeps
{"sources": {}, "tickets": []} — nothing is ever filled in from general knowledge):

    {"sources": {key: {provider, place, url, what, checked_at,        the page each value was read from:
                       text?}},                                       a place's original page (places.json), or
                                                                      its own homepage's page with the excerpt
                                                                      we read in 'text' (never published)
     "tickets": [{"id", "name", "covers",                             the ticket as the table names it
                  "places": [place ids],                              the places it opens
                  "source": key,                                      the prices' table
                  "prices": {"개인"|"단체": {category: [price, resident's price]}},
                  "rules": [{"kind": "age", "category", "from", "to", "text", "source"},
                            {"kind": "born", "category", "from", "to", "text", "source"},   birth years, the
                                                                      table of the source's checked_at year
                            {"kind": "free", "who", "age_max"?, "age_min"?, "source"},
                            {"kind": "note", "text", "source"}]}]}

The resident's price is the second number of a pair; the word the table uses for those residents is the city's
(site.json plan.resident_label, chat_index.plan_config) — a table with prices needs it. A rule belongs to the table
its source page prints it under; a ticket without an age or free rule has none in its table, and the assistant says
so (never borrows another table's rule as this one's). The chat knowledge carries the tables in the place docs
(place_lines) and in docs.json 'tickets' (export), where chatbot/knowledge.js feeTotal adds a group's total once,
with its sum, for every answer to repeat; chatbot/plan_fees.js prices a course plan by them.

A table that sorts people by birth year ('성인 1962년~ 2007년생') is that year's table: export gives each born rule its
source's checked_at year, and the planner applies it to a visit in that year only — someone N years old was born in
one of two years, and both must fall in one category.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

CATEGORIES = ("성인", "청소년·군인", "어린이")
MODES = ("개인", "단체")
RULE_KINDS = ("age", "born", "free", "note")
RESIDENT_FALLBACK = "거주자"   # the words of a problem message when site.json names no resident label


def load(data_dir: Path) -> dict:
    path = Path(data_dir) / "tickets.json"
    if not path.exists():
        return {"sources": {}, "tickets": []}
    data = json.loads(path.read_text("utf-8"))
    return data if isinstance(data, dict) else {"sources": {}, "tickets": []}


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def won(n: int) -> str:
    return f"{n:,}원"


def _host(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def problems(data: dict, places: dict[str, dict], published: set[str], resident: str = "") -> list[str]:
    """What is wrong with tickets.json: every source names a place whose original page is the source address — or,
    for a source with its own excerpt (text), a page on the place's homepage; every ticket names published places, a
    known source and an integer price pair for each category; every price pair and every age, birth-year or free rule
    is written in its source's text (the place's original text or the stored excerpt, whitespace aside); a table with
    prices needs the resident label (`resident`, site.json plan.resident_label)."""
    out = []
    sources = data.get("sources") or {}
    tickets = data.get("tickets") or []
    if tickets and not _flat(resident):
        out.append("tickets: 통합권 요금표가 있는데 site.json plan.resident_label(요금 쌍의 두 번째 값을 내는 거주자 이름)이 없음")
    label = _flat(resident) or RESIDENT_FALLBACK
    for key, s in sources.items():
        for f in ("provider", "place", "url", "what", "checked_at"):
            if not s.get(f):
                out.append(f"tickets 출처 {key}: {f} 없음")
        p = places.get(s.get("place") or "")
        if s.get("text"):
            home = ((p or {}).get("facts") or {}).get("homepage") or ""
            if p is None or not _host(home) or _host(home) != _host(s.get("url")):
                out.append(f"tickets 출처 {key}: {s.get('url')}가 장소 {s.get('place')}의 홈페이지({home or '없음'})가 아님")
        elif p is None or ((p.get("original") or {}).get("source_url") or "") != s.get("url"):
            out.append(f"tickets 출처 {key}: 장소 {s.get('place')}의 원문 주소가 {s.get('url')}가 아님")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(s.get("checked_at") or "")):
            out.append(f"tickets 출처 {key}: checked_at 날짜 형식(YYYY-MM-DD) 아님")

    def text_of(key: str) -> str:
        s = sources.get(key) or {}
        if s.get("text"):
            return _flat(s["text"])
        p = places.get(s.get("place") or "") or {}
        return _flat((p.get("original") or {}).get("text"))

    seen = set()
    for t in tickets:
        tid = t.get("id") or "?"
        if tid in seen:
            out.append(f"tickets {tid}: id 중복")
        seen.add(tid)
        if not t.get("name") or not t.get("covers"):
            out.append(f"tickets {tid}: name·covers 없음")
        for pid in t.get("places") or []:
            if pid not in published:
                out.append(f"tickets {tid}: 공개 장소가 아님 {pid}")
        if not t.get("places"):
            out.append(f"tickets {tid}: places 없음")
        if t.get("source") not in sources:
            out.append(f"tickets {tid}: 알 수 없는 출처 {t.get('source')}")
            continue
        src = text_of(t["source"])
        prices = t.get("prices") or {}
        if "개인" not in prices:
            out.append(f"tickets {tid}: 개인 요금 없음")
        for mode, table in prices.items():
            if mode not in MODES:
                out.append(f"tickets {tid}: 알 수 없는 구분 {mode}")
                continue
            for cat in CATEGORIES:
                pair = table.get(cat)
                if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, int) and x >= 0 for x in pair)):
                    out.append(f"tickets {tid}: {mode} {cat} 요금이 [금액, {label} 금액]이 아님")
                    continue
                if f"{pair[0]:,} ({pair[1]:,})" not in src:
                    out.append(f"tickets {tid}: {mode} {cat} {pair[0]:,} ({pair[1]:,})이 출처 표에 없음")
        for r in t.get("rules") or []:
            if r.get("kind") not in RULE_KINDS or r.get("source") not in sources:
                out.append(f"tickets {tid}: 규칙의 kind·source가 맞지 않음 {r}")
                continue
            words = {"age": r.get("text"), "born": r.get("text"), "free": r.get("who")}.get(r["kind"])
            if r["kind"] != "note" and (not words or _flat(words) not in text_of(r["source"])):
                out.append(f"tickets {tid}: 규칙 '{words}'이 출처 {r['source']}의 원문에 없음")
            if r["kind"] in ("age", "born") and (r.get("category") not in CATEGORIES or not isinstance(r.get("from"), int)
                                                 or not isinstance(r.get("to"), int) or r["from"] > r["to"]):
                out.append(f"tickets {tid}: 연령 규칙이 맞지 않음 {r}")
            # a birth-year rule's words are its two years as the table prints them ('1962년~ 2007년생')
            if r["kind"] == "born" and not re.fullmatch(rf"{r.get('from')}년\s*~\s*{r.get('to')}년생", _flat(words)):
                out.append(f"tickets {tid}: 출생 연도 규칙의 text가 from·to와 다름 {r}")
            if r["kind"] == "note" and not r.get("text"):
                out.append(f"tickets {tid}: 비어 있는 안내")
    return out


def source_text(s: dict) -> str:
    """'<provider> <what> https://… (출처 확인 2026-10-08)'."""
    return f"{s['provider']} {s['what']} {s['url']} (출처 확인 {s['checked_at']})"


def _prices(t: dict, resident: str) -> str:
    parts = []
    label = _flat(resident) or RESIDENT_FALLBACK
    for mode in MODES:
        table = (t.get("prices") or {}).get(mode)
        if not table:
            continue
        cats = [f"{cat} {won(table[cat][0])}({label} {won(table[cat][1])})" for cat in CATEGORIES if cat in table]
        parts.append(f"{mode}{'(20인 이상)' if mode == '단체' and _group_note(t) else ''} — " + ", ".join(cats))
    return "; ".join(parts)


def _group_note(t: dict) -> bool:
    return any(r.get("kind") == "note" and "20인" in str(r.get("text")) for r in t.get("rules") or [])


def table_year(s: dict) -> int:
    """The year a source's birth years are for: the year we read the table."""
    return int(str(s["checked_at"])[:4])


def rule_text(r: dict, sources: dict) -> str:
    what = {"age": lambda: f"{r['text']}",
            "born": lambda: f"{r['category']} {r['text']}({table_year(sources[r['source']])}년 요금표)",
            "free": lambda: f"무료입장 {r['who']}", "note": lambda: r["text"]}[r["kind"]]()
    return f"{what} — {source_text(sources[r['source']])}"


def place_lines(data: dict, e: dict, path_of, resident: str = "") -> list[str]:
    """The combined tickets that open place `e`, for its chat doc: the table's prices with their source, the places,
    then the table's age, free and other rules with theirs — or that the table gives none (확인 필요)."""
    sources = data.get("sources") or {}
    out = []
    for t in data.get("tickets") or []:
        if e["id"] not in (t.get("places") or []):
            continue
        names = "; ".join(path_of(pid) for pid in t["places"])
        out.append(f"- 통합권 요금표 '{t['name']}'({t['covers']}): {_prices(t, resident)} — {source_text(sources[t['source']])}")
        out.append(f"  '{t['name']}' 시설 {len(t['places'])}곳: {names}")
        rules = t.get("rules") or []
        kinds = {r["kind"] for r in rules}
        lines = [rule_text(r, sources) for r in rules]
        if not kinds & {"age", "born"}:
            lines.append("어린이·청소년의 연령 기준: 이 요금표에 없음(확인 필요)")
        if "free" not in kinds:
            lines.append("무료 대상(유아·경로 등): 이 요금표에 없음(확인 필요)")
        out.append(f"  '{t['name']}' 연령·무료·이용 조건: " + "; ".join(lines))
        out.append(f"  여러 사람의 '{t['name']}' 합계는 fee_total 도구로 한 번 계산한다")
    return out


def export(data: dict, path_of_place) -> list[dict]:
    """docs.json 'tickets' (chatbot/knowledge.js feeTotal): each ticket with its places' paths and names, its prices,
    its rules and every source written out (a birth-year rule with its table's year; never a source's stored text)."""
    sources = data.get("sources") or {}
    out = []
    for t in data.get("tickets") or []:
        out.append({
            "id": t["id"], "name": t["name"], "covers": t["covers"],
            "places": [path_of_place(pid) for pid in t["places"]],
            "prices": t["prices"], "src": source_text(sources[t["source"]]),
            "rules": [{**{k: v for k, v in r.items() if k != "source"}, "src": source_text(sources[r["source"]]),
                       **({"year": table_year(sources[r["source"]])} if r["kind"] == "born" else {})}
                      for r in t.get("rules") or []],
        })
    return out
