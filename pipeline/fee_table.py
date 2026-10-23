"""A place's admission fee value read as a table — the first city's review 2026-10-17 (AI 코스 만들기 집중 평가
CE01·CE03).

The course planner priced a plan from what the model wrote: a combined ticket counted twice, a paid museum left out,
any unit price taken as 'the page's value'. The planner now prices every visit itself (chatbot/plan_fees.js) from
the place's own fee value, read here into numbers once at build time and carried in docs.json (f.fee):

    {"free": True, "note"?: "단, 일부 기획전시는 유료"}                     the value says entry is free
    {"tab": {"성인": 2000, "청소년·군인": 1000, "어린이": 500},            the table a visitor (not a resident, not a
     "tl": "개별권",                                                    group) pays one by one, and its heading —
                                                                        or the ticket word every row names
                                                                        ('성인 자유이용권 49,000원')
     "fr": [{"w": "6세 이하 유아", "max": 6}, {"w": "65세 이상 경로", "min": 65}, {"w": "장애인"},
            {"w": "매주 수요일 문화가 있는 날", "wd": 3}],              who enters free as the value says it
     "ag": {"어린이": [7, 12]}}                                         a category's ages, when the value gives them
    {} — a value that names no table this reader can be priced from (rooms, months, ferries, a round trip or a one
         way, weekday and weekend tables, another facility's prices): the planner says 확인 필요

Only what the value writes: a category the table has no ages for stays a name (the planner never maps an age to it);
a resident's price (시민·군민·구민·거주자) and a group's (단체) are not the visitor's; a combined ticket's table is the
ticket's (data/<region>/tickets.json), not the place's. A category is read only where a row starts with it — after a
bullet, a bracket, a separator, a price or a table's own header word ('단체') — never after another facility's name
('아이스링크 대인 10,000원' is the rink's price, not the entry's); a row listing several categories before one price
('청소년, 어린이 1,000원', '청소년/고령자/장애인 1,000원') gives that price to each of them.
"""
from __future__ import annotations

import re

WEEK = "일월화수목금토"
# the categories a table may name, as the value writes them → one name per category
CATS = (("성인", "성인"), ("어른", "성인"), ("일반", "성인"), ("대인", "성인"),
        ("청소년·군인", "청소년·군인"), ("청소년,군인", "청소년·군인"), ("청소년, 군인", "청소년·군인"),
        ("청소년/군인", "청소년·군인"), ("청소년 / 군인", "청소년·군인"), ("청소년", "청소년"),
        ("어린이", "어린이"), ("소인", "소인"))
CAT_OF = dict(CATS)
NOT_VISITOR = re.compile(r"통합권|단체|시민|군민|구민|도민|주민|거주자|관내")
PREFERRED = ("개별권", "타지역", "개인")
PRICE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*원")
# a table's own header words: a category right after one of them still starts its row ('개인 20인이상 단체 성인 …')
HEAD_WORDS = ("개인", "단체", "일반", "구분", "요금", "입장료", "관람료")
BRACKET = r"(?:\([^)]{0,12}\))?"
# a ticket word between a category and its price: '성인 자유이용권 49,000원' (a word ending in 권 — never '왕복', '평일')
TICKET_WORD = r"([가-힣]{1,8}권)"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sections(text: str) -> list[tuple[str, str]]:
    """[(heading, body)] split at '[heading]'; text before the first heading has heading ''."""
    parts = re.split(r"\[([^\]]{1,40})\]", text)
    out = [("", parts[0])]
    for i in range(1, len(parts) - 1, 2):
        out.append((_flat(parts[i]), parts[i + 1]))
    return [(h, b) for h, b in out if _flat(b)]


def _starts_row(flat: str, i: int) -> bool:
    """Whether a category at flat[i] starts a row: after the start, a bullet, a bracket, a separator, a range, a price
    or a header word — not after another word ('아이스링크 대인')."""
    before = flat[:i].rstrip()
    if not before:
        return True
    if before[-1] in "-[]()/,·:~※":
        return True
    if re.search(r"\d\s*원$", before):
        return True
    word = re.search(r"[가-힣A-Za-z]+$", before)
    return bool(word) and word.group(0) in HEAD_WORDS


def _rows(flat: str) -> list[str]:
    """The rows of a flattened table: split at bullets ('- 성인 …', '…원- 소인 …')."""
    return [r.strip(" -") for r in re.split(r"(?:^|\s|(?<=원))-\s", flat) if r.strip(" -")]


def _prices(body: str) -> tuple[dict[str, int], str]:
    """({category: price}, ticket word) for '- 성인 2,000원' rows (the first price after the category name; a price in
    brackets right after it — the resident's — is not read), then the rows that list several categories before one
    price; when no row gives an adult's price that way, the rows that name the same ticket word ('자유이용권')."""
    out: dict[str, int] = {}
    flat = _flat(body.split("※")[0])
    for raw, cat in CATS:
        if cat in out:
            continue
        # '성인 2,000원', '성인 : 500원', '성인(시 거주자) 1,000원(500원)' — the bracket after the name says whose
        # price the bracket after the amount is; the first amount is the visitor's
        for m in re.finditer(re.escape(raw) + r"\s*" + BRACKET + r"\s*[:：]?\s*" + PRICE.pattern, flat):
            if _starts_row(flat, m.start()):
                out[cat] = int(m.group(1).replace(",", ""))
                break
    # '청소년, 어린이 1,000원', '청소년 / 대학생 / 하사 이하의 군인 700원': each category the row lists pays that price
    for row in _rows(flat):
        m = PRICE.search(row)
        if not m:
            continue
        label = row[:m.start()].strip(" :：")
        items = [re.sub(r"\([^)]*\)", "", x).strip() for x in re.split(r"\s*[,/·]\s*", label)]
        if len(items) < 2:
            continue
        for item in items:
            cat = CAT_OF.get(item)
            if cat and cat not in out:
                out[cat] = int(m.group(1).replace(",", ""))
    # '청소년' alone when '청소년·군인' was read is the same price written again
    if "청소년" in out and "청소년·군인" in out and out["청소년"] == out["청소년·군인"]:
        del out["청소년"]
    word = ""
    if "성인" not in out:
        found: dict[str, tuple[str, int]] = {}
        for raw, cat in CATS:
            if cat in found:
                continue
            for m in re.finditer(re.escape(raw) + r"\s*" + BRACKET + r"\s+" + TICKET_WORD + r"\s*" + BRACKET + r"\s*[:：]?\s*"
                                 + PRICE.pattern, flat):
                if _starts_row(flat, m.start()):
                    found[cat] = (m.group(1), int(m.group(2).replace(",", "")))
                    break
        words = {w for w, _ in found.values()}
        if "성인" in found and len(words) == 1:   # every row names the same ticket: its table
            out = {cat: n for cat, (_, n) in found.items()}
            word = words.pop()
    return out, word


def _age_max(part: str) -> int | None:
    """The oldest age (in full years) a free rule's words cover: 'N세 이하' N, 'N세 미만' N − 1, 'N개월 미만' and
    'N개월 이하' the years every child of that age is still under the months; None when they name no age."""
    if (a := re.search(r"(\d+)\s*개월\s*(미만|이하)", part)):
        n = int(a.group(1))
        return (n - 12) // 12 if a.group(2) == "미만" else (n - 11) // 12
    if (a := re.search(r"(\d+)\s*세\s*이하", part)):
        return int(a.group(1))
    if (a := re.search(r"(\d+)\s*세\s*미만", part)):
        return int(a.group(1)) - 1
    return None


def _rule(part: str) -> dict | None:
    part = _flat(part).strip(" -[]:：")
    if not part:
        return None
    rule: dict = {"w": part}
    top = _age_max(part)
    if top is not None:
        if top < 0:
            return None
        rule["max"] = top
    elif (a := re.search(r"(\d+)\s*세\s*이상", part)):
        rule["min"] = int(a.group(1))
    elif (a := re.search(r"매주\s*([월화수목금토일])요일", part)):
        rule["wd"] = WEEK.index(a.group(1))
    elif not re.search(r"장애인|유공자", part):
        return None   # words the planner cannot apply ('문화가 있는 날' alone, a list's leftovers, '후원회원')
    return rule


def _free_rules(text: str) -> list[dict]:
    """Who enters free, as the value lists it after '무료' or '면제' ('※ 무료 : 6세 이하 유아 / 65세 이상 경로대상자 /
    매주 수요일 문화가 있는 날 무료 관람', '무료입장 6세이하 유아, 65세이상 어른, 장애인, 유공자', '※ 무료 : 만 36개월
    미만', '[면제] - 유아(유치원생 포함) : 7세 이하'), and the rows that end in 무료 ('- 12개월 이하 무료')."""
    out = []
    flat = _flat(text)
    m = re.search(r"(?:무료|면제)\s*(?:입장|관람|대상)?\s*[:：]?\s*(.+?)(?:※|$)", flat)
    if m:
        for part in re.split(r"\s*(?:/|,|(?<!\d)·(?!\d)|\s-\s)\s*", m.group(1)):
            rule = _rule(part)
            if rule:
                out.append(rule)
    for row in _rows(flat.split("※")[0]):
        if (r := re.fullmatch(r"(.+?)\s*무료", row)) and _age_max(r.group(1)) is not None:
            rule = _rule(r.group(1))
            if rule and rule not in out:
                out.append(rule)
    return out


def _ages(flat: str) -> dict[str, list[int]]:
    """A category's ages as the value writes them after its name: '어린이(7~12세)', '청소년(만13세~만18세)',
    '어린이(36개월~만12세)' (months in full years)."""
    ages = {}
    for raw, cat in CATS:
        m = re.search(re.escape(raw) + r"\s*\(\s*(?:만\s*)?(\d+)\s*(개월|세)?\s*[~～-]\s*(?:만\s*)?(\d+)\s*세\s*\)", flat)
        if m and cat not in ages:
            lo = int(m.group(1)) // 12 if m.group(2) == "개월" else int(m.group(1))
            ages[cat] = [lo, int(m.group(3))]
    return ages


def parse(text: str) -> dict:
    """The visitor's fee table of one fee value (see the module doc)."""
    flat = _flat(text)
    if not flat:
        return {}
    if re.match(r"^무료(?:\s|$|\(|※)", flat) and not PRICE.search(flat):
        note = re.match(r"^무료\s*\(\s*※?\s*([^)]+)\)", flat) or re.search(r"※\s*(단[,.]?\s*.+?)\s*(?=※|$)", flat)
        return {"free": True, **({"note": _flat(note.group(1))} if note else {})}
    out: dict = {}
    sections = _sections(text)
    chosen = None
    for want in PREFERRED:
        chosen = next(((h, b) for h, b in sections if want in h and not NOT_VISITOR.search(h)), None)
        if chosen:
            break
    if chosen is None:
        plain = [(h, b) for h, b in sections if not h]
        if len(sections) == 1 and plain:
            chosen = plain[0]
    if chosen is not None:
        tab, word = _prices(chosen[1])
        if "성인" in tab:   # a table without an adult price is not one this reader can be priced from
            out["tab"] = tab
            if chosen[0] or word:
                out["tl"] = chosen[0] or word
    ages = _ages(flat)
    if ages and out.get("tab"):
        out["ag"] = ages
    fr = _free_rules(text)
    if fr and out.get("tab"):
        out["fr"] = fr
    return out
