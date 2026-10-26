"""장소 요약·FAQ 생성기 — places.json의 사실 값만으로 한 줄 요약(summary)과 FAQ를 만든다. 네트워크를 쓰지 않는다.

    python tools/place_text.py --data data/<도시> [--all] [--only ids.txt] [--dry-run] [--today YYYY-MM-DD] [--json]

누구를 다시 쓰나: 기본은 기계가 쓴 요약(summary_auto)과 요약이 없는 레코드. --all은 locks에 summary가 없는 모든
레코드(사람이 tools/place_content.py merge로 쓴 요약도 덮으므로 생성기를 고친 뒤 한 번만). 중복·제외 레코드는 건너뛴다.
쓰는 필드는 summary·faq·summary_auto(true)·summary_thin·summary_notices뿐이다. status·reviewed_at·approved_at·slug·
facts는 건드리지 않는다(CLAUDE.md 3절 7항).

규칙(CLAUDE.md 3절 1·2·5·6항)
- 값은 화면이 읽는 그대로 꺼낸다(pipeline.present의 시간표·요금표·주차·메뉴 읽기). 원문의 머리글('[개인]')·'※' 주석·
  목록 기호·이름표('주차 :')는 문장에 넣지 않고, 조사는 textutil.josa로 붙인다. 같은 메뉴를 두 번 쓰지 않는다.
- 출처마다 값이 다르면(present.contested — 화면이 '출처마다 다름'을 붙이는 값) 한쪽을 고르지 않는다. 요약·FAQ 모두
  두 값을 출처와 함께 쓰고 '방문 전에 전화로 확인해야 합니다'를 붙인다. 값이 길면 '출처마다 달라'만 쓴다.
- 종료일 없는 휴관 공지(notices.json open_end)가 있는 장소는 요약 첫 문장과 첫 FAQ가 그 공지이고 평소 값은 그 뒤에
  둔다. 그 공지 id를 summary_notices에 남긴다(공지가 끝나면 pipeline.validate가 '다시 생성' 경고를 낸다). 기간이 정해진
  휴관(7일 이상)과 바뀐 운영 시간(야간 개장 등, kind hours)도 공지가 보이는 동안 요약 첫 문장과 첫 FAQ에 쓰고 같은 자리에
  남긴다. 하루짜리 공지(하루 무료 개방 등)는 요약·FAQ에 쓰지 않는다 — 화면의 공지 줄이 보인다.
- 요약: 답부터 쓰는 존댓말 평서문 1~3문장. 그 장소만의 값(체험·판매 품목·장날·대표 메뉴·좌석·객실·지정·운영 시간·
  요금 중 하나 이상)을 넣는다. 위치만 말하는 상투구를 쓰지 않는다. 쓸 값이 주소·홈페이지뿐이면 짧은 한 문장에
  summary_thin=true(색인에서 빠진다).
- FAQ: 그 장소 값으로만 답하는 질문(질문에 장소 이름, 존댓말 '~나요?/~인가요?'). 음식점·숙소 2개, 그 밖 3개 이하.
  값이 있는 것 가운데 방문 판단에 쓰는 것(공지·요일·입장 마감·요금표·예약·체험·메뉴 가격·체크인·취사)을 먼저 고르고,
  다른 장소의 FAQ와 같은 질문은 만들지 않는다.
- 쓰기 전에 tools/place_content.check_item(원문 복사·금지 문구·사실표에 없는 숫자·존댓말·출처 검사)을 통과해야 한다.
  걸린 FAQ는 빼고, 요약이 걸리면 그 장소는 쓰지 않고 보고한다(종료 코드 1).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import city as citymod
from pipeline import notices as noticesmod
from pipeline import present
from pipeline.schema import designations as shown_designations, index_groups
from pipeline.textutil import clock_text, display_address, josa, parking_text, squash_ws
from tools import place_content as pc

CALL = "방문 전에 전화로 확인해야 합니다"
CONFLICT_MAX = 56        # a summary writes a conflict's values out only while both fit in this many characters
FAQ_CONFLICT_MAX = 170   # an FAQ answer lists every source's value (up to four) within this many characters
SUMMARY_MAX = 3          # sentences (tools/place_content.SUMMARY_MAX_SENTENCES)
SUMMARY_SOFT = 210       # characters: a further sentence is added only while the summary stays this short
LIST_MAX = 3             # items named from a list (menu, programmes, goods)
TEMPLATE_CAP = 10        # a question worded the same apart from the place name is asked on at most this many pages
VARIES = re.compile(r"([가-힣]+(?:\s*(?:및|과|와|,)\s*[가-힣]+?)?)\s*(?:별로|별|마다)\s*(?:[가-힣]+\s*){0,2}?(?:상이|다름|다릅|달라)")
ADULT_WORDS = re.compile(r"어른|성인|대인|청소년|어린이|소인|경로|유아|군인|일반")
WELL_FORMED = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d{1,3})원(?:\s*\([\d,]+원\))?$|^무료$")
OPEN_PLAIN = re.compile(r"^(?:휴무일?\s*[:：]?\s*)?(?:없음|휴무\s*없음|무휴|연중\s*무휴|년중\s*무휴|연중무휴)$")
END_WORDS = re.compile(r"(?:(?<=\s)|(?<=요일)|(?<=당일)|(?<=연휴)|(?<=명절))(?:정기\s*)?(?:휴무일?|휴관일?|휴일|휴장)\s*$")


# ------------------------------------------------------------------ small text helpers
def tidy(text) -> str:
    """A stored value as a sentence may carry it: '–' and spaced '~' as '~', '( x )' as '(x)', a label's colon
    ('라스트오더: 오후', '주차 : 10대') as a space (clock times keep theirs), '3월~5월' as '3~5월', month spans
    joined by '·', a dot between words ('목. 금. 토') as '·', no doubled spaces."""
    t = squash_ws(text)
    t = re.sub(r"[–—∼～〜]", "~", t)
    t = re.sub(r"\s*~\s*", "~", t)
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = re.sub(r"(?<=[가-힣0-9])\s+\((?=[^)]*\))", "(", t)
    t = re.sub(r"(?<=[가-힣A-Za-z)\]])\s*[:：]\s*(?=\S)", " ", t)
    t = re.sub(r"\s*[▶►]\s*", " ", t)
    t = re.sub(r"(\d{1,2})\s*월\s*~\s*(\d{1,2})\s*월", r"\1~\2월", t)
    t = re.sub(r"(?<=월)\s*/\s*(?=\d)", "·", t)
    t = re.sub(r"(?<=[가-힣])\.\s+(?=[가-힣])", "·", t)
    t = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "·", t)
    t = re.sub(r"\s*,(?!\d{3}(?!\d))\s*", ", ", t)
    t = re.sub(r"\s*·\s*", "·", t)
    return squash_ws(t).strip(" ,/-")


def top_split(text: str, seps: str = r"\s*/\s*|\s*,(?!(?<=\d,)\d{3}(?!\d))\s*|\s*·\s*|\s+및\s+") -> list[str]:
    """Parts of a list value split at its separators outside brackets only ('복합쇼핑몰(백화점, 마트)' stays whole)."""
    guard = re.sub(r"\([^()]*\)", lambda m: m.group(0).replace(",", "\x01").replace("/", "\x02").replace("·", "\x03"), text)
    return [x.replace("\x01", ",").replace("\x02", "/").replace("\x03", "·") for x in re.split(seps, guard)]


def clean_word(text: str) -> bool:
    """No word the content checks refuse (tools/place_content.BANNED: evaluative words even inside a programme name)."""
    return not pc._wording(text)


def varies_word(text: str) -> str:
    """'프로그램 및 시설' -> '프로그램과 시설' (the subject of '…마다 다릅니다')."""
    parts = [x for x in re.split(r"\s*(?:및|과|와|,)\s*", squash_ws(text)) if x]
    return f"{josa(parts[0], '과/와')} {parts[1]}" if len(parts) == 2 else squash_ws(text)


def has_word(text: str) -> bool:
    return bool(re.search(r"[0-9A-Za-z가-힣]", text or ""))


def connective(sentence: str) -> str:
    """'…입니다' -> '…이고', '…있습니다' -> '…있고' (the first of two clauses joined into one sentence); '' when the
    ending is not one of these."""
    s = sentence.rstrip(".")
    for end, conn in (("입니다", "이고"), ("있습니다", "있고"), ("없습니다", "없고"), ("엽니다", "열고"),
                      ("쉽니다", "쉬고"), ("합니다", "하고"), ("됩니다", "되고"), ("팝니다", "팔고")):
        if s.endswith(end):
            return s[: -len(end)] + conn
    return ""


def join2(a: str, b: str) -> str:
    c = connective(a)
    return f"{c} {b}" if c else ""


def listing(items: list[str], more: bool = False) -> str:
    """'a·b·c 등' — at most LIST_MAX items; '등' when more were left out (or the source said so)."""
    shown = items[:LIST_MAX]
    return "·".join(shown) + (" 등" if more or len(items) > LIST_MAX else "")


def split_items(raw) -> tuple[list[str], bool]:
    """Items of a list value ('다도체험 / 한지뜨기 체험 / 쿠킹클래스 등', 'a, b, c 외'): (items, the source said 등/외)."""
    t = " ".join(present.clean_lines(raw))
    more = bool(re.search(r"(?:\s|^)(?:등|외|기타)\s*$", t))
    t = re.sub(r"\s*(?:등|외|기타)\s*$", "", t)
    parts = [tidy(x) for x in top_split(t)]
    seen, out = set(), []
    for x in parts:
        key = re.sub(r"[\s()]", "", x)
        if x and has_word(x) and key not in seen and clean_word(re.sub(r"\([^()]*\)", "", x)) and x.count("(") == x.count(")"):
            seen.add(key)
            out.append(x)
    return out, more


# ------------------------------------------------------------------ value readers (the page's own reading)
def hours_text(raw, base: str = "") -> dict | None:
    """{'text': '11~2월 09:00~17:00, 3~5월·9~10월 09:00~18:00', 'single': one plain range, 'always': 상시 개방,
    'varies': '점포'} — None when nothing readable."""
    lines = present.clean_lines(raw)
    joined = squash_ws(" ".join(lines))
    if not has_word(joined):
        return None
    if re.fullmatch(r"(?:연중\s*)?상시\s*개방|24\s*시간(?:\s*개방)?|상시", joined):
        return {"text": "상시 개방", "single": False, "always": True, "varies": ""}
    if not re.search(r"\d", joined):
        m = VARIES.search(joined)
        return {"text": "", "single": False, "always": False, "varies": varies_word(m.group(1))} if m else None
    tt = present.timetable(raw)
    rows = [r for r in (tt or {}).get("rows", []) if r["kind"] == "time"]
    if rows:
        groups: list[tuple[str, list[str]]] = []
        for r in rows:
            g, lab = tidy(r["group"]), tidy(r["label"])
            if lab in present.BASE_WORDS or lab == base:
                lab = ""
            item = " ".join(x for x in (lab, tidy(r["value"])) if x)
            if tidy(r["note"]):
                item += f"({tidy(r['note'])})"
            if groups and g and groups[-1][0] == g:
                groups[-1][1].append(item)
            else:
                groups.append((g, [item]))
        parts = [" ".join(x for x in (g, "·".join(items)) if x) for g, items in groups]
        text = ", ".join(parts[:3]) + (" 등" if len(parts) > 3 else "")
        single = len(rows) == 1 and not tidy(rows[0]["group"]) and not (tidy(rows[0]["label"]) not in ("", base)
                                                                          and tidy(rows[0]["label"]) not in present.BASE_WORDS) \
            and not rows[0]["note"]
        return {"text": text, "single": single, "always": False, "varies": ""}
    b, _closed = present.brief_hours(raw, base)
    if not b or not has_word(b["main"]):
        return None
    text = tidy(b["main"]) + (f", {tidy(b['sub'])}" if b["sub"] else "") + (" 등" if b["more"] else "")
    return {"text": text, "single": False, "always": False, "varies": ""}


def entry_close(raw) -> str:
    """'관람 종료 1시간 전' / '17:00' — when entry closes, as the hours value says it (any line, the ※ notes too)."""
    t = squash_ws(" ".join(str(raw or "").splitlines()))
    m = re.search(r"(?:입장\s*(?:마감|시간은)?|마감\s*시간)[^.※\d]{0,14}?(\d+)\s*(시간|분)\s*전", t) or \
        re.search(r"(?:관람|운영)\s*종료\s*(\d+)\s*(시간|분)\s*전까지\s*입장", t)
    if m:
        return f"관람 종료 {m.group(1)}{m.group(2)} 전"
    times = set(re.findall(r"입장\s*마감\s*[:：]?\s*(\d{1,2}:\d{2})", t))
    return times.pop() if len(times) == 1 else ""   # one closing time per season stays in the hours text


def closed_text(raw) -> dict | None:
    """{'open': True, 'text': '연중무휴'} or {'open': False, 'text': '매주 월요일과 설날, 추석 당일'} — the closed-day
    clauses joined, their trailing '휴무' words dropped (the sentence says 쉽니다); a clause that names no day ('사전
    예약제') is left out; None when open and closed clauses mix or nothing is readable."""
    t = " ".join(present.clean_lines(raw))
    t = re.sub(r"^\s*(?:휴무일?|휴관일|정기\s*휴일|쉬는\s*날)\s*[:：]\s*", "", t).strip()
    if not has_word(t):
        return None
    clauses = [c.strip(" ,") for c in re.split(r"\s*/\s*", t) if c.strip(" ,")]
    opened, closed = [], []
    for c in clauses:
        c = re.sub(r"^\s*(?:-\s*)?(?:휴무일?|휴관일)\s*[:：]\s*", "", c).lstrip("- ")
        # an hours remark inside a closed-day value ('21:30 라스트 오더, 매주 월요일') belongs to the hours, not here
        c = ", ".join(x for x in c.split(", ") if not re.search(r"\d{1,2}:\d{2}", x)).strip(" ,")
        if not c:
            continue
        if OPEN_PLAIN.match(c) or present.is_open_value(c) or present.OPENISH.search(c):
            opened.append(c)
        elif present.CLOSED_HINT.search(c) or present.WEEKLY.search(c) or present.PARTIAL_RX.search(c):
            closed.append(tidy(END_WORDS.sub("", c)))
    if opened and closed:
        return None
    if opened:
        word = tidy(opened[0])
        return {"open": True, "text": "연중무휴" if OPEN_PLAIN.match(opened[0]) or len(opened) > 1 else word}
    if not closed:
        return None
    if len(closed) == 1:
        text = closed[0]
    else:
        text = ", ".join(closed[:-2] + [f"{josa(closed[-2], '과/와')} {closed[-1]}"])
    return {"open": False, "text": text}


def who(text: str) -> str:
    return tidy(re.sub(r"\s*(?:및|,)\s*", "·", squash_ws(text)))


def fee_text(raw) -> dict | None:
    """{'free': True} / {'varies': '체험'} / {'text': '어른 5,000원, 청소년·군인 4,000원', 'group': '개인',
    'admission': True (the rows are people), 'free_for': '7세 미만'} — None when nothing readable (a call note)."""
    lines = present.clean_lines(raw)
    text = squash_ws(" ".join(lines))
    if not has_word(text):
        return None
    if re.fullmatch(r"(?:입장료|관람료|이용료|입장)?\s*(?:무료|없음)(?:\s*입장)?", text):
        return {"free": True}
    if not re.search(r"\d", text):
        m = VARIES.search(text)
        return {"varies": varies_word(m.group(1))} if m else None
    free_for = ""
    for line in present.restore_lines(raw):
        m = re.match(r"^※?\s*무료\s*[:：]\s*(.+?)(?:\s*\(.*\))?$", line)
        if m:
            free_for = tidy(m.group(1))
    gr = present.fee_grid(text)
    if gr:
        r = gr["rows"][0]
        return {"text": f"{who(r['who'])} {r['a']}원" + (" 등" if len(gr["rows"]) > 1 else ""), "group": tidy(gr["cols"][0]),
                "admission": bool(ADULT_WORDS.search(r["who"])), "free_for": free_for}
    ft = present.fee_table("\n".join(lines))
    if ft:
        g = ft["groups"][0]
        good = [x for x in g["rows"] if WELL_FORMED.match(squash_ws(x["price"]))]   # '13,2000원' is a typo in the source
        if not good:
            return None
        items = [f"{who(x['who'])} {tidy(x['price'])}" for x in good[:4]]
        return {"text": ", ".join(items) + (" 등" if len(g["rows"]) > len(items) else ""),
                "group": tidy(re.sub(r"\s*/\s*", "·", g["label"])),
                "admission": any(ADULT_WORDS.search(x["who"]) for x in g["rows"]), "free_for": free_for}
    b = present.brief_fee(raw)
    if not b or not has_word(b["main"]) or b["main"] == "전화 문의":
        return None
    main = tidy(b["main"])
    if re.fullmatch(r"(?:입장료?\s*)?무료", main) and not b["sub"]:
        return {"free": True} if not b["more"] else {"text": "무료 등", "group": "", "admission": False, "free_for": ""}
    if len(main) > 40 or not re.search(r"\d|무료", main):
        return None
    return {"text": " ".join(x for x in (tidy(b["sub"]), main) if x) + (" 등" if b["more"] else ""), "group": "",
            "admission": bool(ADULT_WORDS.search(main)), "free_for": free_for}


PARK_LABEL = re.compile(r"^(?:주차\s*(?:시설|대수|가능\s*대수|가능\s*여부|여부)?|주차장)\s*[:：]\s*")


def parking_info(e: dict) -> dict | None:
    """{'yes': True|False|None, 'count': '150', 'fee': '무료'|'유료'|'승용차 4,000원 등'|'', 'near': True (a nearby
    lot), 'text': the tidied value when it says more than these}."""
    f = e.get("facts") or {}
    raw, fee_raw = f.get("parking"), f.get("parkingfee")
    if not raw and not fee_raw:
        return None
    t = squash_ws(parking_text(" ".join(present.clean_lines(raw)))) if raw else ""
    t = tidy(PARK_LABEL.sub("", t))
    t = re.sub(r"(\d)\s+대(?!형)", r"\1대", t)
    if re.search(r"온돌|화장실|거실|객실|\*|\.\s", t):   # another field's text in the parking value: nothing to say
        t = ""
        if not fee_raw:
            return None
    out = {"yes": None, "count": "", "fee": "", "near": False, "text": "", "more": ""}
    said = re.match(r"^주차\s*가능\s*,?\s*", t)   # '주차가능 유료 추가 요금 …': the label is no part of the sentence
    if said:
        t = t[said.end():]
        out["yes"] = True
        if not t:
            return out
    if t:
        no = re.search(r"불가|없음", t) and not re.search(r"(?<!불)가능|이용\s*가능|있음", t.replace("불가능", ""))
        out["yes"] = True if said else (False if no else True)
        m = re.search(r"(\d+)\s*대(?!형)", t) or re.search(r"주차장\s*(?:보유)?\s*\(\s*(\d+)\s*\)", t)
        out["count"] = m.group(1) if m else ""
        if re.search(r"\d+\s*대\s*이상", t):
            out["more"] = "이상"
        if re.search(r"(?:요금\s*)?\(?\s*무료\s*\)?", t) and "유료" not in t:
            out["fee"] = "무료"
        elif re.search(r"\(\s*유료\s*\)|^유료$|가능\s*,?\s*유료", t):
            out["fee"] = "유료"
        out["near"] = bool(re.search(r"인근|근처|주변|건너편|공영|공용|노면|갓길|오성", t))
        simple = re.fullmatch(r"(?:자체\s*)?(?:주차\s*)?(?:가능|있음|주차장\s*보유|주차장)?\s*(?:,?\s*요금\s*)?"
                              r"(?:\(\s*(?:\d+\s*대?|무료|유료)\s*\))?\s*(?:,?\s*요금\s*무료)?|\d+\s*대|불가능?|없음|"
                              r"(?:자체\s*)?주차장\s*(?:보유)?\s*\(\s*\d+\s*대?\s*\)|(?:승용차\s*)?\d+\s*대\s*(?:이상)?\s*(?:정도|가량)?",
                              t)
        if not simple:
            out["text"] = t
    if fee_raw and not out["fee"]:
        fee = squash_ws(" ".join(present.clean_lines(fee_raw)))
        if fee == "무료":
            out["fee"] = "무료"
        else:
            # the table's first price as written ('최초 30분 1,000원', '30분 무료', '6시간 이내 무료') — never a cap or
            # an extra charge on its own ('최대 18,000원', '이후 10분당 500원'), nor a unit as a label ('분 1,000원')
            m = re.search(r"(?:승용차|소형|일반)?\s*(?:1회\s*)?\(?최초\s*\d+\s*(?:분|시간)\)?\s*[\d,]+원", fee)
            first = m.group(0).strip() if m else next(
                (x for x in re.split(r"\s*(?:/|·|\s-\s?|^-\s?|(?<=[원료])\s*-)\s*", fee)
                 if re.search(r"원|무료", x) and len(x) <= 30 and not re.search(r"\[|\]|상이|참조|발생|추가|이후|초과", x)
                 and not re.match(r"(?:1일|일일|최대)", x)), "")
            out["fee"] = f"{tidy(first)} 등" if first else ("유료" if re.search(r"\d원", fee) else "")
        if out["yes"] is None and out["fee"]:
            out["yes"] = True
    return out


def parking_sentence(p: dict, own: bool = False) -> str:
    """One sentence on parking; '' when the value says nothing a sentence can carry."""
    if not p:
        return ""
    if p["text"]:
        t = re.sub(r"\s*/\s*", ", ", p["text"])
        return f"주차는 {t}입니다." if re.search(r"[가-힣0-9)]$", t) and len(t) <= 40 else ""
    if p["yes"] is False:
        return "자체 주차장은 없어 근처 주차장을 이용해야 합니다." if p["near"] else "주차할 수 없습니다."
    if p["yes"] is None:
        return ""
    fee = {"무료": "주차비는 무료입니다", "유료": "주차비는 유료입니다"}.get(p["fee"], f"주차비는 {p['fee']}입니다" if p["fee"] else "")
    if p["count"]:
        head = f"주차장은 {p['count']}대{' 이상' if p.get('more') else ''} 규모입니다"
    else:
        head = "주차할 수 있습니다"
    return (join2(head + ".", fee) if fee else head) + "."


def menu_items(e: dict) -> tuple[list[str], list[tuple[str, str]], bool]:
    """(dish names to name — the representative menu first, the rest of the menu list after it, each once; (dish,
    price) pairs the data states; the list said 등/외)."""
    f = e.get("facts") or {}
    names, prices, more = [], [], False
    seen = set()

    def add(item: str, priced: bool = True):
        item = tidy(item)
        if not clean_word(item) and clean_word(re.sub(r"\s*\([^()]*\)", "", item)):
            item = tidy(re.sub(r"\s*\([^()]*\)", "", item))   # '오리능이한방백숙(4인기준)': '인기' is not a word there
        m = re.match(r"^(?P<n>.+?)\s*\(?(?P<p>\d{1,3}(?:,\d{3})+|\d{4,})\s*원?\)?\s*(?P<tail>~)?$", item)
        if m and not re.search(r"\d{1,3}(?:,\d{3})+.*\d{1,3}(?:,\d{3})+", item):
            name, price = tidy(m.group("n")), m.group("p") + "원" + ("~" if m.group("tail") else "")
            if priced and not re.search(r"\d", re.sub(r"\([^()]*\)", "", name)) and has_word(name):
                key = re.sub(r"[\s()]", "", name)
                if key not in {re.sub(r"[\s()]", "", n) for n, _ in prices}:
                    prices.append((name, price))
        else:
            name = re.sub(r"\s*\(?\d[\d,]*(?:\s*~\s*\d[\d,]*)?\s*원.*$", "", item)
        name = tidy(name)
        if re.fullmatch(r"(?:주문\s*)?(?:예약|문의)|주문\s*예약", name):   # a booking note in the menu list, not a dish
            return
        key = re.sub(r"\s|\([^()]*\)", "", name)
        if name and has_word(name) and key not in seen and len(name) <= 24 and not re.search(r"[小中大]|택\s*1", name) \
                and name.count("(") == name.count(")") and not re.fullmatch(r"(?:대|중|소|특|보통|일반|\d+인분?)", key) \
                and clean_word(name):
            seen.add(key)
            names.append(name)

    for k in ("menu", "treatmenu"):
        if f.get(k):
            items, m = split_items(f[k])
            more = more or m
            for it in items:
                add(it, priced=not present.contested(e, k))   # a price another source gives otherwise is not said
    for k in ("menu", "treatmenu"):
        for a in (e.get("fact_alternatives") or {}).get(k) or []:
            if a.get("relation") == "also":
                for it in split_items(a.get("value"))[0]:
                    m = re.match(r"^(?P<n>.+?)\s*\(?(?P<p>\d{1,3}(?:,\d{3})+)\s*원\)?$", tidy(it))
                    if m and not re.search(r"\d", re.sub(r"\([^()]*\)", "", m.group("n"))):
                        n = tidy(m.group("n"))
                        if re.sub(r"[\s()]", "", n) not in {re.sub(r"[\s()]", "", x) for x, _ in prices}:
                            prices.append((n, m.group("p") + "원"))
    return names, prices, more


def seat_text(raw) -> str:
    """'총 96석·개별룸 4개' from '총 96석 - 입식 96석 | 개별룸 4개' — the total seats (only a stated total or a single
    count) and private rooms."""
    t = squash_ws(raw)
    if not t:
        return ""
    total = re.search(r"총\s*(\d+)\s*석", t)
    counts = re.findall(r"(\d+)\s*석", t)
    seats = total.group(1) if total else (counts[0] if len(set(counts)) == 1 else "")
    rooms = re.search(r"(?:개별룸|룸|방)\s*(\d+)\s*개", t)
    parts = ([f"{seats}석"] if seats else []) + ([f"개별룸 {rooms.group(1)}개"] if rooms else [])
    return "·".join(parts)


def room_count(raw) -> str:
    t = tidy(re.sub(r"^\s*(?:객실\s*수|객실|방)\s*[:：]\s*", "", squash_ws(raw)))
    if re.fullmatch(r"\d+", t):
        return f"{t}실"
    m = re.fullmatch(r"(\d+)\s*실(?:\s*\(([^()]+)\))?", t)
    if m:
        return f"{m.group(1)}실" + (f"({m.group(2)})" if m.group(2) else "")
    return ""


def access_items(raw) -> list[str]:
    """The items of '열린관광지(점자 겸용 팸플릿·촉지/음성 종합관광안내판·…)' (top-level '·' only)."""
    m = re.match(r"^\s*열린관광지\s*\((.+)\)\s*$", squash_ws(raw))
    if not m:
        return []
    out, depth, cur = [], 0, ""
    for ch in m.group(1):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "·" and not depth:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    out.append(cur.strip())
    return [tidy(x) for x in out if x.strip()]


# ------------------------------------------------------------------ sources and conflicts
class Place:
    """One record with the readings the sentences need."""

    def __init__(self, e: dict, city, notices: list[dict]):
        self.e, self.city = e, city
        self.f = e.get("facts") or {}
        self.name = squash_ws(e.get("name"))
        self.kind = e.get("kind") or "attraction"
        self.closures = [n for n in notices if noticesmod.open_ended(n)]
        # a dated closure of a week or more, or changed hours (a night opening): the summary's first sentence and the
        # first FAQ while it is shown (summary_notices; pipeline.validate asks to regenerate once it is gone)
        self.dated = [] if self.closures else [n for n in notices if dated_notice(n)]
        self.facts_used: set[str] = set()

    def N(self, pair: str) -> str:
        return f"{self.name}의" if pair == "의" else josa(self.name, pair)

    def provider(self, p: str) -> str:
        return self.city.short_provider(squash_ws(p)) or squash_ws(p)

    def where(self, p: str) -> str:
        """'한국관광공사 자료에' / '소수서원 홈페이지에'."""
        short = self.provider(p)
        return f"{short}에" if re.search(r"(홈페이지|공지|누리집)$", short) else f"{short} 자료에"

    def contested(self, k: str) -> list[dict]:
        return present.contested(self.e, k) if self.f.get(k) else []

    def source(self, k: str) -> str:
        """The FAQ source of facts[k]: TourAPI, else the page the value was read on, else the record's original."""
        s = (self.e.get("fact_sources") or {}).get(k) or self.e.get("facts_source") or {}
        prov = squash_ws(s.get("provider"))
        if any(w in prov for w in citymod.NATIONAL_PROVIDER) or s.get("contentid"):
            return pc.TOURAPI_SOURCE
        url = squash_ws(s.get("url"))
        if url.startswith(("http://", "https://")):
            return url
        orig = squash_ws((self.e.get("original") or {}).get("source_url"))
        return orig or pc.TOURAPI_SOURCE

    def values(self, k: str, read) -> list[tuple[str, str]]:
        """[(provider, text)] of facts[k] and every contradicting source's value, as `read` words them; one entry
        when they read the same."""
        main = read(self.f.get(k))
        prov = squash_ws(present.src_of(self.e, k)["provider"])
        out = [(prov, main)] if main else []
        for a in self.contested(k):
            v = read(a.get("value"))
            if v and all(v != x for _, x in out):
                out.append((squash_ws(a.get("provider")), v))
        return out

    def conflict(self, label: str, vals: list[tuple[str, str]], limit: int = CONFLICT_MAX) -> str:
        """'<label>은 A 자료에 X, B 자료에 Y로 출처마다 달라 방문 전에 전화로 확인해야 합니다.'; without the values when
        they are longer than `limit` (or more than two in a summary); two pages of one provider: '출처마다 X와 Y로'."""
        vals = [(p, re.sub(r"\s+등$", "", v)) for p, v in vals]
        if sum(len(v) for _, v in vals) > limit or len(vals) > (2 if limit <= CONFLICT_MAX else 4):
            return f"{josa(label, '은/는')} 출처마다 달라 {CALL}."
        shorts = [self.where(p) for p, _ in vals]
        if len(set(shorts)) < len(shorts):
            values = ", ".join(v for _, v in vals[:-1])
            return (f"{josa(label, '은/는')} 출처마다 {josa(values, '과/와')} {josa(vals[-1][1], '으로/로')} 달라 {CALL}.")
        parts = [f"{w} {v}" for w, (_, v) in zip(shorts, vals)]
        last = josa(parts[-1], "으로/로")
        return f"{josa(label, '은/는')} {', '.join(parts[:-1] + [last])} 출처마다 달라 {CALL}."


# ------------------------------------------------------------------ the readings as sentences
def hours_reading(pl: Place) -> dict:
    """{'h': hours dict | None, 'c': closed dict | None, 'h_conf': [(p, text)], 'c_conf': [...], 'entry': '…'}."""
    hkey = "usetime_restdate" if pl.kind == "food" and pl.f.get("usetime_restdate") else "usetime"
    base = present.BASE_LABEL.get(hkey, "")
    read_h = lambda v: (hours_text(v, base) or {}).get("text") or ("" if not v else (
        f"{(hours_text(v, base) or {}).get('varies')}마다 다름" if (hours_text(v, base) or {}).get("varies") else ""))
    h = hours_text(pl.f.get(hkey), base) if pl.f.get(hkey) else None
    h_conf = pl.values(hkey, read_h) if pl.contested(hkey) else []
    if len(h_conf) < 2:
        h_conf = []
    ckey = "restdate" if pl.f.get("restdate") else ""
    c = closed_text(pl.f.get("restdate")) if ckey else None
    if not ckey and pl.f.get(hkey):
        _b, inside = present.brief_hours(pl.f.get(hkey), base)
        c = closed_text(inside) if inside else None
    read_c = lambda v: (closed_text(v) or {}).get("text") or ""
    c_conf = pl.values("restdate", read_c) if ckey and pl.contested("restdate") else []
    if len(c_conf) < 2:
        c_conf = []
    entry = entry_close(pl.f.get(hkey)) if pl.f.get(hkey) and not h_conf else ""
    if entry and h and h.get("text"):   # said once, in its own sentence
        h = {**h, "text": squash_ws(re.sub(r"\s*\([^()]*입장[^()]*\)", "", h["text"]))}
    return {"h": h, "c": c, "h_conf": h_conf, "c_conf": c_conf, "entry": entry, "key": hkey}


def hours_sentence(pl: Place, r: dict, subject: bool, verb: str) -> list[str]:
    """Sentences on when the place opens: hours and closed days together when both are settled ('연중무휴로
    09:00~18:00에 문을 엽니다'), a conflict sentence for each side that differs. subject: start with the place name."""
    S = f"{pl.N('은/는')} " if subject else ""
    out = []
    h, c = r["h"], r["c"]
    label = "영업시간" if pl.kind == "food" else "이용시간"
    if r["h_conf"]:
        out.append(pl.conflict(label, r["h_conf"]))
        h = None
        S = ""
    if r["c_conf"]:
        out.append(pl.conflict("쉬는 날", r["c_conf"]))
        c = None
    hs = ""
    if h:
        if h["always"]:
            hs = "always"
        elif h["varies"]:
            hs = "varies"
    if h and hs == "always":
        if c and c["open"]:
            out.insert(0, f"{S}쉬는 날 없이 상시 개방합니다.")
        elif c:
            out.insert(0, f"{S}상시 개방하지만 {c['text']}에는 쉽니다.")
        else:
            out.insert(0, f"{S}상시 개방합니다.")
        return out
    if h and hs == "varies":
        first = f"{(pl.N('의') + ' ') if subject else ''}{label}{'은' if label.endswith('간') else '는'} {h['varies']}마다 다릅니다."
        if c:
            first = join2(first, f"{c['text']}에 쉽니다." if not c["open"] else "쉬는 날은 없습니다.") or first
        out.insert(0, first)
        return out
    if h and h["text"]:
        ht = h["text"]
        if h["single"]:
            if c and c["open"]:
                s = f"{S}{'연중무휴로' if c['text'] == '연중무휴' else josa(c['text'], '으로/로')} {ht}에 {verb}."
            elif c:
                s = f"{S}{c['text']}에 쉬고, {ht}에 {verb}."
            else:
                s = f"{S}{ht}에 {verb}."
        else:
            lead = f"{pl.N('의')} " if subject else ""
            if c and c["open"]:
                s = f"{lead}{label}{'은' if label.endswith('간') else '는'} {ht}이고 {c['text']}입니다."
            elif c:
                s = f"{lead}{label}{'은' if label.endswith('간') else '는'} {ht}이고, {c['text']}에 쉽니다."
            else:
                s = f"{lead}{label}{'은' if label.endswith('간') else '는'} {ht}입니다."
        out.insert(0, s)
    elif c:
        out.insert(0, f"{S}{'쉬는 날 없이 운영합니다' if c['open'] and c['text'] == '연중무휴' else (c['text'] + '입니다' if c['open'] else c['text'] + '에 쉽니다')}.")
    if r["entry"] and out and not r["h_conf"]:
        e = r["entry"]
        tail = f"입장은 {e}까지입니다." if not re.fullmatch(r"\d{1,2}:\d{2}", e) else f"입장은 {e}에 마감합니다."
        if "입장 마감" not in out[0] and e not in out[0]:
            out.insert(1, tail)
    return out


def fee_word(pl: Place, x: dict) -> str:
    """What the price is for: '개인 입장료' (people's rows of an attraction), '<group> 요금' (a named table: rides,
    rooms), '이용료' (people's rows at a stay: its bath or facility), '숙박료', '요금'."""
    group, stay = x.get("group") or "", pl.kind == "stay"
    if x.get("admission"):
        if stay:
            return "이용료"
        return f"{group} 입장료" if group in ("개인", "일반") else ("입장료" if not group else f"{group} 요금")
    return f"{group} 요금" if group else ("숙박료" if stay else "요금")


def fee_sentence(pl: Place, subject: bool, limit: int = CONFLICT_MAX) -> str:
    key = "usefee"
    if not pl.f.get(key):
        return ""
    if pl.contested(key):
        def read(v):
            x = fee_text(v) or {}
            if x.get("free"):
                return "무료"
            if x.get("varies"):
                return f"{x['varies']}마다 다름"
            return (x.get("text") or "").split(", ")[0]
        vals = pl.values(key, read)
        if len(vals) >= 2:
            word = "입장료" if pl.kind == "attraction" else "요금"
            return pl.conflict(word, vals, limit)
    x = fee_text(pl.f.get(key))
    if not x:
        return ""
    S = f"{pl.N('은/는')} " if subject else ""
    stay = pl.kind == "stay"
    if x.get("free"):
        return f"{S}{'요금은 무료입니다' if stay else '입장료 없이 둘러볼 수 있습니다'}."
    if x.get("varies"):
        return f"{S}{'숙박료는' if stay else '요금은'} {x['varies']}마다 다릅니다."
    lead = f"{pl.N('의')} " if subject else ""
    s = f"{lead}{josa(fee_word(pl, x), '은/는')} {x['text']}입니다."
    if x.get("free_for"):
        s = join2(s, f"{josa(x['free_for'], '은/는')} 무료입니다.") or s
    return s


DATED_CLOSURE_DAYS = 7


def dated_notice(n: dict) -> bool:
    """A notice the summary leads with: a closure from one date to another of DATED_CLOSURE_DAYS or more, or changed
    hours ('hours'). A one-day free entry or closure stays on the page's notice line only."""
    if noticesmod.open_ended(n):
        return False
    start, end = noticesmod.span(n)
    if n.get("kind") == "hours":
        return True
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1 if start and end else 0
    return n.get("kind") == "closed" and days >= DATED_CLOSURE_DAYS


def dated_sentence(pl: Place, n: dict) -> str:
    """'<이름>은 2026년 11월 1일(일)–2027년 1월 31일(일)에 쉰다고 공지했습니다.' / '<이름>은 2026년 10월 30일(금)–11월 1일(일)에
    09:00–21:30에 운영합니다(입장 마감 21:00).' — the notice's own dates and times (pipeline/notices.py ko_dates)."""
    when = noticesmod.ko_dates(n)
    if n.get("kind") == "closed":
        return f"{pl.N('은/는')} {when}에 쉰다고 공지했습니다."
    last = f", 입장은 {n['last_entry']}에 마감합니다" if n.get("last_entry") else ""
    return f"{pl.N('은/는')} {when}에 {n['from']}–{n['to']} {'운영하고' if last else '운영합니다'}{last}."


def closure_sentence(pl: Place) -> tuple[str, str]:
    """(sentence, notice id) for an open-ended closure; ('', '')."""
    for n in pl.closures:
        start = noticesmod.ko_date(noticesmod.span(n)[0]).split("(")[0]
        why = noticesmod.REASONS.get(n.get("reason") or "", "")
        return (f"{pl.N('은/는')} {start}부터 {why}운영을 멈췄고, 다시 여는 날은 아직 공지되지 않았습니다.", n["id"])
    return "", ""


def designation_line(pl: Place) -> str:
    """'영주시가 영주맛집·모범음식점으로 지정한 곳' from the designations the page shows."""
    ds = shown_designations(pl.e, city=pl.city)
    if not ds:
        return ""
    labels, issuers = [], []
    for d in ds:
        m = re.match(r"^(.+?)\s*\(\s*(.+?)\s*지정\s*\)$", squash_ws(d.get("label")))
        labels.append(tidy(m.group(1)) if m else tidy(re.sub(r"\(.*?\)", "", d.get("label") or "")))
        if m:
            issuers.append(m.group(2))
    labels = list(dict.fromkeys(x for x in labels if x))
    if not labels:
        return ""
    issuer = issuers[0] if issuers and len(set(issuers)) == 1 and len(issuers) == len(ds) else ""
    what = josa("·".join(labels), "으로/로")
    return f"{josa(issuer, '이/가')} {what} 지정한 곳" if issuer else f"{what} 지정된 곳"


# ------------------------------------------------------------------ summaries
def fit(sentences: list[str]) -> list[str]:
    out = []
    for s in sentences:
        if not s:
            continue
        if len(out) >= SUMMARY_MAX:
            break
        if out and len(" ".join(out + [s])) > SUMMARY_SOFT:
            continue
        out.append(s)
    return out


def merge_pair(a: str, b: str) -> list[str]:
    """Two short clauses as one sentence when both fit ('입장료 없이 … 있고 주차할 수 있습니다.')."""
    if a and b and len(a) + len(b) <= 70 and not re.search(r"고 |며 ", a + b):
        j = join2(a, b)
        if j:
            return [j]
    return [x for x in (a, b) if x]


def session_times(raw) -> tuple[str, list[str]]:
    """('탐방프로그램', ['10:30', '14:00', '16:00']) when the hours value only lists start times ('[탐방프로그램
    운영시간]10:30 / 14:00 / 16:00'): a visit by programme; ('', []) otherwise."""
    label, rest = "", []
    for line in present.restore_lines(raw):
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            label = tidy(re.sub(r"\s*운영\s*시간$", "", m.group(1)))
        elif not line.startswith("※"):
            rest.append(line)
    body = squash_ws(" ".join(rest))
    if re.fullmatch(r"\d{1,2}:\d{2}(?:\s*[/,·]\s*\d{1,2}:\d{2})+", body):
        return label, re.findall(r"\d{1,2}:\d{2}", body)
    return "", []


def attraction_summary(pl: Place) -> tuple[list[str], bool]:
    f = pl.f
    lead_bits = []
    if f.get("expguide") and not pl.contested("expguide"):
        items, more = split_items(f["expguide"])
        if items:
            lead_bits.append(f"{pl.name}에서는 {josa(listing(items, more), '을/를')} 체험할 수 있습니다.")
    if f.get("saleitem") and not pl.contested("saleitem"):
        items, more = split_items(f["saleitem"])
        if items and not re.search(r"쇼핑몰|백화점|아울렛", items[0]):   # a store type, not goods it sells
            lead_bits.append(f"{pl.name}에서는 {josa(listing(items, more), '을/를')} 팝니다.")
    if f.get("fairday") and not pl.contested("fairday") and re.search(r"\d\s*일|\d\s*[·,/]\s*\d", f["fairday"]):
        lead_bits.append(f"장날은 {tidy(' '.join(present.clean_lines(f['fairday'])))}입니다.")
    acc = access_items(f.get("accessibility")) if f.get("accessibility") else []
    if acc:
        lead_bits.append(f"{pl.N('은/는')} 열린관광지 사업으로 {josa(listing(acc, True), '을/를')} 갖추거나 고쳤습니다.")
    if f.get("spendtime") and not pl.contested("spendtime"):
        lead_bits.append(f"둘러보는 데 {tidy(f['spendtime'])} 정도 걸립니다.")
    r = hours_reading(pl)
    out: list[str] = []
    closure, _ = closure_sentence(pl)
    if closure:
        # closed until further notice: the notice first, then only the usual hours (marked 평소) — what the place
        # offers when open (체험, 요금) would read as available now
        out.append(closure)
        hours = hours_sentence(pl, r, subject=False, verb="문을 엽니다")
        if hours:
            first = hours[0]
            hours[0] = "평소 " + (first if re.match(r"^(이용시간|쉬는 날)", first) else first)
        return fit(out + hours[:2]), False
    label, times = session_times(f.get("usetime")) if f.get("usetime") and not r["h_conf"] else ("", [])
    if times:
        what = label or "프로그램"
        out.append(f"{pl.N('은/는')} {josa(what, '으로/로')} 관람하며, 프로그램은 {'·'.join(times)}에 시작합니다.")
        if r["c_conf"]:
            out.append(pl.conflict("쉬는 날", r["c_conf"]))
        elif r["c"]:
            out.append(f"{r['c']['text']}에 쉽니다." if not r["c"]["open"] else "쉬는 날 없이 운영합니다.")
        if f.get("reservation") and not pl.contested("reservation"):
            first = tidy(re.split(r"\s*·\s*|,\s*", squash_ws(f["reservation"]))[0])
            if re.search(r"[가-힣)]$", first):
                out.append(f"예약은 {josa(first, '으로/로')} 합니다.")
        return fit(out), False
    hours = hours_sentence(pl, r, subject=True, verb="문을 엽니다")
    fee = fee_sentence(pl, subject=not hours)
    park = parking_sentence(parking_info(pl.e))
    out += hours
    if lead_bits:
        out += [fee] + lead_bits[:1] + [park] + lead_bits[1:]   # 체험·판매 품목·장날: what the place itself offers
    else:
        out += merge_pair(fee, park) if fee and park and "출처마다" not in fee + park else [fee, park]
    got = fit(out)
    thin = False
    if not got:
        got, thin = fallback(pl)
    elif len(" ".join(got)) < 40 and len(got) == 1 and not closure:
        where = where_text(pl)
        body = got[0][len(pl.name):].lstrip() if got[0].startswith(pl.name) else ""
        if where and re.match(r"^(은|는) ", body):   # '<이름>은 입장료 없이 …' -> '<이름>은 <주소>에 있고, 입장료 없이 …'
            got[0] = f"{pl.N('은/는')} {where}에 있고, {body[2:]}"
    got[0] = subjectify(pl, got[0])
    return got, thin


def subjectify(pl: Place, s: str) -> str:
    """A first sentence that does not name the place gets it: '입장료 없이 …' -> '<이름>은 입장료 없이 …', '이용시간은
    …' -> '<이름>의 이용시간은 …'."""
    if s.startswith(pl.name):
        return s
    if re.match(r"^(이용시간|영업시간|쉬는 날은|입장료는|요금은|숙박료는|이용료는|주차는|주차장은|주차비는|대표 메뉴|객실|좌석은|장날|개인 입장료|일반 입장료|체크인|문의 전화|[가-힣·]+ 요금은)", s):
        return f"{pl.N('의')} {s}"
    return f"{pl.N('은/는')} {s}"


def where_text(pl: Place) -> str:
    """The address without the city prefix, and without a trailing '(<읍·면·동>)' the address already names
    ('풍기읍 삼가로 661-29(풍기읍)' -> '풍기읍 삼가로 661-29')."""
    addr = display_address(pl.f.get("address"))
    where = tidy(pl.city.strip_city_prefix(addr) or addr)
    m = re.search(r"\s*\(([^()]+)\)$", where)
    if m and m.group(1) in where[:m.start()]:
        where = where[:m.start()]
    return where


def thin_sentence(pl: Place) -> str:
    """Only an address to say: where it is, in one short sentence (summary_thin — the page is not indexed)."""
    where = where_text(pl)
    kind = {"attraction": "여행지", "food": "음식점", "stay": "숙소"}.get(pl.kind, "장소")
    return f"{pl.N('은/는')} {where}에 있습니다." if where else f"{pl.N('은/는')} {kind}입니다."


def food_summary(pl: Place) -> tuple[list[str], bool]:
    f = pl.f
    names, _prices, more = menu_items(pl.e)
    desig = designation_line(pl)
    out: list[str] = []
    if names:
        menu = names[0]
        rest = names[1:]
        if rest:
            lead = f"{pl.N('의')} 대표 메뉴는 {menu}이고, {listing(rest, more)}도 있습니다."
        else:
            lead = f"{pl.N('의')} 대표 메뉴는 {menu}입니다."
        if desig:
            lead = f"{pl.N('은/는')} {desig}으로, 대표 메뉴는 {menu}입니다." if not rest else \
                f"{pl.N('은/는')} {desig}으로, 대표 메뉴는 {menu}이고 {listing(rest, more)}도 있습니다."
        out.append(lead)
    elif desig:
        out.append(f"{pl.N('은/는')} {desig}입니다.")
    r = hours_reading(pl)
    out += hours_sentence(pl, r, subject=not out, verb="영업합니다")
    seat = seat_text(f.get("seat")) if f.get("seat") and not pl.contested("seat") else ""
    park = parking_sentence(parking_info(pl.e))
    seat_s = f"좌석은 {seat.replace('·', '이고 ', 1).replace('개별룸', '개별룸이') if '·' in seat else seat}{'입니다' if '·' not in seat else ' 있습니다'}." if seat else ""
    if seat and "·" in seat:
        a, b = seat.split("·", 1)
        seat_s = f"좌석은 {a}이고 {josa(b.split(' ')[0], '이/가')} {b.split(' ', 1)[1]} 있습니다."
    out += merge_pair(seat_s, park) if seat_s and park and "출처마다" not in park else [seat_s, park]
    got = fit(out)
    thin = False
    if not got:
        got, thin = fallback(pl)
    got[0] = subjectify(pl, got[0])
    return got, thin


def stay_type(pl: Place) -> str:
    t = present.kind_type(pl.e, {}, city=pl.city)
    if t in ("", "숙박업소", "모텔·호텔·리조트", "그 밖의 숙소", "기타", "숙박"):
        return "숙소"
    return t


def cooking(raw) -> str:
    """'객실에서 취사할 수 있습니다.' / '일부 객실에서만 취사할 수 있습니다.' / '객실에서는 취사할 수 없습니다.' / ''."""
    c = squash_ws(raw)
    if re.match(r"^가능", c):
        return "일부 객실에서만 취사할 수 있습니다." if "일부" in c else "객실에서 취사할 수 있습니다."
    if re.match(r"^(불가|불가능|없음|안\s*됨)", c):
        return "객실에서는 취사할 수 없습니다."
    return ""


def stay_summary(pl: Place) -> tuple[list[str], bool]:
    f = pl.f
    out: list[str] = []
    closure, _ = closure_sentence(pl)
    if closure:
        out.append(closure)
    rooms = room_count(f.get("roomcount")) if f.get("roomcount") and not pl.contested("roomcount") else ""
    rtype = tidy(f.get("roomtype")) if f.get("roomtype") and len(squash_ws(f.get("roomtype"))) <= 12 \
        and not pl.contested("roomtype") else ""
    typ = stay_type(pl)
    ci = clock_text(squash_ws(f.get("checkin"))) if f.get("checkin") and not pl.contested("checkin") else ""
    co = clock_text(squash_ws(f.get("checkout"))) if f.get("checkout") and not pl.contested("checkout") else ""
    if rooms:
        what = f"{rtype} 객실 {rooms}" if rtype else f"객실 {rooms}"
        out.append(f"{pl.N('은/는')} {josa(what, '을/를')} 갖춘 {typ}입니다." if not closure
                   else f"평소 {josa(what, '을/를')} 운영합니다.")
    if ci and co:
        out.append(f"체크인은 {ci}, 체크아웃은 {co}입니다.")
    elif ci or co:
        out.append(f"체크인은 {ci}입니다." if ci else f"체크아웃은 {co}입니다.")
    cook_s = cooking(f.get("cooking")) if f.get("cooking") and not pl.contested("cooking") else ""
    park = parking_sentence(parking_info(pl.e))
    fee = fee_sentence(pl, subject=False) if f.get("usefee") else ""
    if fee:
        out.append(fee)
    out += merge_pair(cook_s, park) if cook_s and park and "출처마다" not in park else [cook_s, park]
    got = fit(out)
    if not got:
        got, thin = fallback(pl)
    else:
        thin = False
    got[0] = subjectify(pl, got[0])
    return got, thin


def fallback(pl: Place) -> tuple[list[str], bool]:
    """No value a sentence can carry: where it is and the phone (not thin — it is a value), else where it is
    (thin — only an address or a homepage)."""
    tel, _digits = present.settled_phone(pl.e)
    where = where_text(pl)
    if tel:
        word = "예약·문의 전화" if pl.kind == "stay" else "문의 전화"
        return ([f"{pl.N('은/는')} {where}에 있고, {word}는 {tel}입니다." if where else f"{pl.N('의')} {word}는 {tel}입니다."],
                False)
    others = set(k for k, v in pl.f.items() if squash_ws(v)) - {"address", "homepage"}
    return [thin_sentence(pl)], not others


# ------------------------------------------------------------------ FAQ
def faq_candidates(pl: Place) -> list[tuple[str, str, str]]:
    """(q, a, source) in the order they are worth: what decides a visit first."""
    f, N, out = pl.f, pl.name, []
    add = lambda q, a, src: out.append((squash_ws(q), squash_ws(a), src))
    for n in pl.closures:
        start = noticesmod.ko_date(noticesmod.span(n)[0]).split("(")[0]
        why = noticesmod.REASONS.get(n.get("reason") or "", "")
        verb = "숙박할" if pl.kind == "stay" else ("이용할" if pl.kind == "food" else "관람할")
        add(f"{N}{'에서' if pl.kind == 'stay' else josa('', '')} 지금 {verb} 수 있나요?" if pl.kind == "stay"
            else f"{pl.N('은/는')} 지금 {verb} 수 있나요?",
            f"아니요. {start}부터 {why}운영을 멈췄고 다시 여는 날은 아직 공지되지 않았습니다. 가기 전에 공지를 확인하세요.",
            n["url"])
    if pl.closures:   # closed until further notice: every other answer would read as if it were open now
        return out
    for n in pl.dated:
        when = noticesmod.ko_dates(n)
        if n.get("kind") == "closed":
            add(f"{pl.N('은/는')} {when}에도 문을 여나요?",
                f"아니요. 그 기간에 쉰다는 공지가 있습니다. 가기 전에 공지를 확인하세요.", n["url"])
        else:
            last = f" 입장은 {n['last_entry']}에 마감합니다." if n.get("last_entry") else ""
            add(f"{pl.N('은/는')} {when}에 몇 시까지 운영하나요?",
                f"{n['from']}–{n['to']} 운영합니다.{last} 가기 전에 공지를 확인하세요.", n["url"])
    r = hours_reading(pl) if pl.kind != "stay" else None
    if r and pl.kind == "attraction":
        wk = present.week_closure(f.get("restdate")) if f.get("restdate") else None
        if wk and not r["c_conf"] and r["c"]:
            if wk["days"]:
                day = next(d for d in present.WEEK if d in wk["days"])
                add(f"{pl.N('은/는')} {day}요일에 쉬나요?", f"네, {r['c']['text']}에 쉽니다.", pl.source("restdate"))
            elif wk["open"] and r["c"]["open"]:
                add(f"{pl.N('은/는')} 월요일에도 문을 여나요?", f"네, {r['c']['text']}입니다." if r["c"]["text"] != "연중무휴"
                    else "네, 쉬는 날 없이 운영합니다.", pl.source("restdate"))
            elif wk["days"] and "월" not in wk["days"] | wk["partial"]:
                add(f"{pl.N('은/는')} 월요일에도 문을 여나요?", f"네, 월요일에도 엽니다. 쉬는 날은 {r['c']['text']}입니다.",
                    pl.source("restdate"))
        if r["c_conf"]:
            add(f"{pl.N('은/는')} 언제 쉬나요?", pl.conflict("쉬는 날", r["c_conf"], FAQ_CONFLICT_MAX), pl.source("restdate"))
    if r and r["h_conf"]:
        label = "영업시간" if pl.kind == "food" else "이용시간"
        vals = r["h_conf"]
        shorts = [pl.provider(p) for p, _ in vals]
        if len(set(shorts)) < len(shorts):
            ans = pl.conflict(label, vals, FAQ_CONFLICT_MAX)
        else:
            said = " ".join(f"{sh}{'는' if re.search(r'(홈페이지|공지|누리집)$', sh) else ' 자료는'} {v}입니다."
                            for sh, (_, v) in zip(shorts, vals))
            ans = f"{label}{'은' if label.endswith('간') else '는'} 출처마다 다릅니다. {said} {CALL}."
        add(f"{pl.N('은/는')} 몇 시에 문을 여나요?" if pl.kind != "food" else f"{pl.N('은/는')} 몇 시까지 영업하나요?",
            ans, pl.source(r["key"]))
    elif r and r["h"] and r["h"]["text"] and not r["h"]["single"] and "," in r["h"]["text"] and pl.kind == "attraction":
        # the question names what the times differ by, and only when the value says it (a lunch break is neither)
        by = "철마다" if re.search(r"\d\s*월|절기", r["h"]["text"]) else (
            "요일마다" if re.search(r"[월화수목금토일]요일|[월화수목금토일]\s*~|평일|주말|공휴일", r["h"]["text"]) else "")
        if by:
            add(f"{N} 이용시간은 {by} 다르나요?", f"네, {r['h']['text']}입니다.", pl.source(r["key"]))
    if r and r["entry"]:
        e = r["entry"]
        add(f"{pl.N('은/는')} 몇 시까지 입장할 수 있나요?",
            f"입장은 {e}까지입니다." if not re.fullmatch(r"\d{1,2}:\d{2}", e) else f"입장은 {e}에 마감합니다.",
            pl.source(r["key"]))
    if pl.kind == "attraction" and f.get("reservation") and not pl.contested("reservation"):
        text = tidy(squash_ws(f["reservation"]).replace(" · ", ", "))
        if re.search(r"[가-힣)]$", text):
            add(f"{pl.N('은/는')} 예약해야 하나요?", f"{text}입니다.", pl.source("reservation"))
    if f.get("usefee"):
        if pl.contested("usefee"):
            s = fee_sentence(pl, subject=False, limit=FAQ_CONFLICT_MAX)
            if s:
                add(f"{N} {'입장료는' if pl.kind == 'attraction' else '요금은'} 얼마인가요?", s, pl.source("usefee"))
        else:
            x = fee_text(f["usefee"]) or {}
            if x.get("free") and pl.kind == "attraction":
                add(f"{pl.N('은/는')} 입장료가 있나요?", "아니요, 입장료 없이 둘러볼 수 있습니다.", pl.source("usefee"))
            elif x.get("text"):
                s = fee_sentence(pl, subject=False)
                add(f"{N} {josa(fee_word(pl, x).split(' ')[-1] if ' 요금' not in fee_word(pl, x) else '요금', '은/는')} 얼마인가요?",
                    s, pl.source("usefee"))
    if f.get("expguide") and not pl.contested("expguide"):
        items, more = split_items(f["expguide"])
        if items:
            add(f"{N}에서는 어떤 체험을 할 수 있나요?", f"{josa(listing(items, more), '을/를')} 체험할 수 있습니다.", pl.source("expguide"))
    if f.get("saleitem") and not pl.contested("saleitem"):
        items, more = split_items(f["saleitem"])
        if items and not re.search(r"쇼핑몰|백화점|아울렛", items[0]):
            add(f"{N}에서는 무엇을 파나요?", f"{josa(listing(items, more), '을/를')} 팝니다.", pl.source("saleitem"))
    if f.get("fairday") and not pl.contested("fairday") and re.search(r"\d\s*일|\d\s*[·,/]\s*\d", f["fairday"]):
        add(f"{N} 장날은 언제인가요?", f"장날은 {tidy(' '.join(present.clean_lines(f['fairday'])))}입니다.", pl.source("fairday"))
    if f.get("spendtime") and not pl.contested("spendtime"):
        add(f"{josa(N, '을/를')} 둘러보는 데 얼마나 걸리나요?", f"{tidy(f['spendtime'])} 정도 걸립니다.", pl.source("spendtime"))
    acc = access_items(f.get("accessibility")) if f.get("accessibility") else []
    if acc:
        add(f"{N}에는 어떤 무장애 시설이 있나요?",
            f"열린관광지 사업으로 {josa(listing(acc, len(acc) > LIST_MAX), '을/를')} 갖추거나 고쳤습니다.", pl.source("accessibility"))
    if pl.kind == "food":
        names, prices, more = menu_items(pl.e)
        if prices:
            dish, price = prices[0]
            add(f"{N} {dish} 가격은 얼마인가요?", f"{josa(dish, '은/는')} {price}입니다.",
                pl.source("menu") if any(dish in str(f.get(k) or "") for k in ("menu", "treatmenu"))
                else alt_source(pl, ("menu", "treatmenu"), dish))
        last = re.search(r"(?:마지막\s*주문|라스트\s*오더|라스트오더|주문\s*마감)\s*[:：]?\s*((?:오후\s*)?\d{1,2}(?::\d{2}|시(?:\s*\d{1,2}분)?))",
                         squash_ws(f.get("usetime") or f.get("usetime_restdate") or ""))
        if last and r and not r["h_conf"]:
            add(f"{pl.N('은/는')} 몇 시까지 주문할 수 있나요?", f"마지막 주문은 {tidy(last.group(1))}입니다.", pl.source(r["key"]))
        brk = re.search(r"(?:브레이크\s*타임|휴식\s*시간|준비\s*시간|쉬는\s*시간)\s*[:：▶]?\s*(\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2})"
                        r"|(\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2})\s*브레이크\s*타임", squash_ws(f.get("usetime") or ""))
        if brk and r and not r["h_conf"]:
            add(f"{pl.N('은/는')} 브레이크타임이 있나요?", f"네, {tidy(brk.group(1) or brk.group(2))}에는 쉬는 시간입니다.",
                pl.source(r["key"]))
        if r and r["c"] and not r["c_conf"]:
            c = r["c"]
            add(f"{pl.N('은/는')} 쉬는 날이 있나요?" if c["open"] else f"{pl.N('은/는')} 언제 쉬나요?",
                ("쉬는 날 없이 영업합니다." if c["text"] == "연중무휴" else f"{c['text']}입니다.") if c["open"]
                else f"{c['text']}에 쉽니다.", pl.source("restdate" if f.get("restdate") else r["key"]))
        elif r and r["c_conf"]:
            add(f"{pl.N('은/는')} 언제 쉬나요?", pl.conflict("쉬는 날", r["c_conf"], FAQ_CONFLICT_MAX), pl.source("restdate"))
        if names and not prices:
            add(f"{N} 대표 메뉴는 무엇인가요?", f"대표 메뉴는 {names[0]}입니다." + (f" {listing(names[1:], more)}도 있습니다." if names[1:] else ""),
                pl.source("menu" if f.get("menu") else "treatmenu"))
        pack = squash_ws(f.get("packing"))
        if pack and not pl.contested("packing"):
            if re.match(r"^가능", pack):
                extra = re.search(r"\(([^()]+)\)", pack)
                add(f"{pl.N('은/는')} 포장이 되나요?", f"네, {tidy(extra.group(1)) + ' ' if extra else ''}포장할 수 있습니다.", pl.source("packing"))
            elif re.search(r"불가", pack):
                add(f"{pl.N('은/는')} 포장이 되나요?", "아니요, 포장은 안 됩니다.", pl.source("packing"))
        seat = seat_text(f.get("seat")) if f.get("seat") and not pl.contested("seat") else ""
        if seat and "개별룸" in seat:
            add(f"{N}에 개별룸이 있나요?", f"네, 좌석은 {seat.replace('·', '이고 ', 1).replace('개별룸 ', '개별룸이 ')} 있습니다.",
                pl.source("seat"))
        elif seat:
            add(f"{N} 좌석은 몇 석인가요?", f"좌석은 {seat}입니다.", pl.source("seat"))
    if pl.kind == "stay":
        ci = clock_text(squash_ws(f.get("checkin"))) if f.get("checkin") and not pl.contested("checkin") else ""
        co = clock_text(squash_ws(f.get("checkout"))) if f.get("checkout") and not pl.contested("checkout") else ""
        if ci:
            add(f"{N} 체크인은 몇 시부터인가요?", f"체크인은 {ci}" + (f", 체크아웃은 {co}입니다." if co else "입니다."), pl.source("checkin"))
        cook = cooking(f.get("cooking")) if f.get("cooking") and not pl.contested("cooking") else ""
        if cook:
            add(f"{N} 객실에서 취사할 수 있나요?", ("아니요, " if "없습니다" in cook else "네, ") + cook, pl.source("cooking"))
        rooms = room_count(f.get("roomcount")) if f.get("roomcount") and not pl.contested("roomcount") else ""
        if rooms:
            add(f"{N} 객실은 몇 실인가요?", f"객실은 {rooms}입니다.", pl.source("roomcount"))
        tel, _d = present.settled_phone(pl.e)
        if tel:
            key = "infocenter" if f.get("infocenter") else "reservation"
            add(f"{N} 예약 전화번호는 무엇인가요?", f"예약·문의 전화는 {tel}입니다.", pl.source(key))
        sub = f.get("subfacility")
        if sub and not pl.contested("subfacility"):
            items, more = split_items(sub)
            if items:
                add(f"{N}에는 어떤 부대시설이 있나요?", f"{josa(listing(items, more), '이/가')} 있습니다.", pl.source("subfacility"))
        rt = tidy(f.get("roomtype")) if f.get("roomtype") and not pl.contested("roomtype") else ""
        if rt and len(rt) <= 40:
            add(f"{N} 객실은 어떤 형태인가요?", f"객실 유형은 {rt}입니다.", pl.source("roomtype"))
        res = squash_ws(f.get("reservation"))
        if res and not pl.contested("reservation"):
            t = tidy(res)
            add(f"{pl.N('은/는')} 어떻게 예약하나요?", f"예약은 {josa(t, '으로/로')} 합니다." if re.search(r"[가-힣)]$", t)
                else f"예약 문의는 {t}입니다.", pl.source("reservation"))
    p = parking_info(pl.e)
    if p:
        key = "parking" if f.get("parking") else "parkingfee"
        if p["text"] and parking_sentence(p):
            add(f"{N}에 주차할 수 있나요?", parking_sentence(p), pl.source(key))
        elif p["count"] and p["yes"]:
            add(f"{N}에는 차를 몇 대 댈 수 있나요?", parking_sentence(p), pl.source(key))
        elif p["fee"] and p["yes"]:
            add(f"{N} 주차비는 얼마인가요?", parking_sentence(p), pl.source("parkingfee" if f.get("parkingfee") else key))
        elif p["yes"] is not None and parking_sentence(p):
            add(f"{N}에 주차할 수 있나요?", ("네, " if p["yes"] else "아니요, ") + parking_sentence(p), pl.source(key))
    if pl.kind == "food":
        d = designation_line(pl)
        if d:
            add(f"{pl.N('은/는')} 지정 업소인가요?", f"네, {d}입니다.", designation_source(pl))
    if r and pl.kind == "attraction" and r["h"] and r["h"].get("text") and not r["h_conf"]:
        add(f"{N} 이용시간은 어떻게 되나요?", f"이용시간은 {r['h']['text']}입니다.", pl.source(r["key"]))
    tel, _d = present.settled_phone(pl.e)
    if tel and pl.kind != "stay":
        key = "infocenter" if f.get("infocenter") else "reservation"
        add(f"{N} 문의 전화번호는 무엇인가요?", f"문의 전화는 {tel}입니다.", pl.source(key))
    return out


def alt_source(pl: Place, keys, dish: str) -> str:
    for k in keys:
        for a in (pl.e.get("fact_alternatives") or {}).get(k) or []:
            if dish in str(a.get("value") or "") and squash_ws(a.get("url")).startswith("http"):
                return squash_ws(a["url"])
    return pl.source(keys[0])


def designation_source(pl: Place) -> str:
    ds = shown_designations(pl.e, city=pl.city)
    url = squash_ws((ds[0] if ds else {}).get("url"))
    return url or pl.source("address")


# ------------------------------------------------------------------ one place
def template(q: str, name: str) -> str:
    """The question without the place name (its particle in one form), to count how often one wording is used."""
    for pair in ("으로/로", "은/는", "이/가", "을/를", "과/와"):
        q = q.replace(josa(name, pair), "{N}" + pair)
    return pc._qkey(q.replace(name, "{N}"))


def write_place(e: dict, *, city, notices: list[dict], used_q: set, used_t: dict | None = None) -> dict:
    """{'summary', 'faq', 'thin', 'notices', 'issues'} for one record; issues are place_content.check_item's on the
    summary (the FAQs that fail are dropped one by one)."""
    pl = Place(e, city, notices)
    if pl.kind == "food":
        sents, thin = food_summary(pl)
    elif pl.kind == "stay":
        sents, thin = stay_summary(pl)
    else:
        sents, thin = attraction_summary(pl)
    if pl.dated:
        lead = [dated_sentence(pl, n) for n in pl.dated]
        rest = [x for x in sents if x]
        if rest and rest[0].startswith(pl.name):   # the usual values follow under their own subject: '평소에는 …'
            rest[0] = "평소에는 " + rest[0][len(pl.N("은/는")):].lstrip() if rest[0].startswith(pl.N("은/는")) else rest[0]
        sents = (lead + rest)[:SUMMARY_MAX]
    sents = [squash_ws(s) for s in sents if s and squash_ws(s).endswith("다.") and not re.search(r"[\[\]]", s)]
    flagged = [i for i, s in enumerate(sents) if s.endswith(f"출처마다 달라 {CALL}.")]
    for i in flagged[:-1]:   # the call line once, after the last value that differs
        sents[i] = sents[i][: -len(f"달라 {CALL}.")] + "다릅니다."
    summary = " ".join(dict.fromkeys(sents))
    sheet = pc.fact_sheet(e, city=city)
    for n in notices:   # a notice is a source of this place's text: its dates and its post
        sheet["facts"].append({"key": "notice", "label": "공지", "value": noticesmod.ko_text(n), "provider": n["provider"]})
        if n.get("url") and n["url"] not in sheet["faq_sources"]:
            sheet["faq_sources"].append(n["url"])
    for d in shown_designations(e, city=city):
        if d.get("url") and d["url"] not in sheet["faq_sources"]:
            sheet["faq_sources"].append(d["url"])
    for k, alts in (e.get("fact_alternatives") or {}).items():
        for a in alts or []:
            u = squash_ws(a.get("url"))
            if u.startswith("http") and u not in sheet["faq_sources"]:
                sheet["faq_sources"].append(u)
    limit = pc.FAQ_MAX.get(pl.kind, pc.FAQ_MAX_DEFAULT)
    faqs, keys = [], set()
    used_t = {} if used_t is None else used_t
    cands = faq_candidates(pl)
    # a 'full' page shows an FAQ block (schema.TIER_BLOCKS): its first answer may use a wording already at the cap
    need_one = e.get("tier") == "full"
    for q, a, src in cands:
        k = pc._qkey(q)
        t = template(q, pl.name)
        capped = used_t.get(t, 0) >= TEMPLATE_CAP and not (need_one and not faqs and (q, a, src) == next(
            (c for c in cands if pc._qkey(c[0]) not in used_q and c[1]), None))
        if k in keys or k in used_q or len(faqs) >= limit or not a or capped or re.search(r"[\[\]]", a):
            continue
        item = {"id": e["id"], "summary": summary, "faq": [{"q": q, "a": a, "source": src}]}
        if pc.check_item(item, sheet, city=city, place=e) and not pc.check_item({**item, "faq": []}, sheet, city=city, place=e):
            continue   # the summary is clean and this FAQ is not: leave the FAQ out
        faqs.append({"q": q, "a": a, "source": src})
        keys.add(k)
        used_t[t] = used_t.get(t, 0) + 1
    issues = pc.check_item({"id": e["id"], "summary": summary, "faq": faqs, "thin": thin}, sheet, city=city, place=e)
    return {"summary": summary, "faq": faqs, "thin": thin, "notices": [n["id"] for n in pl.closures + pl.dated],
            "issues": issues, "keys": keys}


def needs(p: dict, every: bool) -> bool:
    if p.get("duplicate_of") or p.get("exclude") or "summary" in (p.get("locks") or []):
        return False
    return every or bool(p.get("summary_auto")) or not squash_ws(p.get("summary"))


def run(data: Path, *, every: bool = False, only: list[str] | None = None, dry_run: bool = False,
        today: str | None = None) -> dict:
    city = pc.load_city(data)
    path = data / "places.json"
    before = path.read_text("utf-8")
    places = json.loads(before)
    today = today or dt.date.today().isoformat()
    active = noticesmod.active(noticesmod.load(data), today)
    want = set(only or [])
    todo = [p for p in places if needs(p, every or bool(want)) and (not want or p.get("id") in want or p.get("slug") in want)]
    todo_ids = {p["id"] for p in todo}
    # questions other records keep are taken; the records rewritten here claim theirs in order (published first)
    used_q = {pc._qkey(f.get("q")) for p in places if p["id"] not in todo_ids for f in p.get("faq") or []}
    used_t: dict[str, int] = {}
    for p in places:
        if p["id"] not in todo_ids:
            for f in p.get("faq") or []:
                t = template(f.get("q") or "", squash_ws(p.get("name")))
                used_t[t] = used_t.get(t, 0) + 1
    # the pages with the most to say claim a shared wording first (TEMPLATE_CAP): published, then by the index groups held
    todo.sort(key=lambda p: (p.get("status") != "published", -len(index_groups(p)),
                             {"attraction": 0, "food": 1, "stay": 2}.get(p.get("kind"), 3), p.get("id")))
    written, refused, faq_n, thin_n = [], [], 0, 0
    for p in todo:
        res = write_place(p, city=city, notices=noticesmod.for_place(active, p["id"]), used_q=used_q, used_t=used_t)
        if res["issues"]:
            refused.append({"id": p["id"], "slug": p.get("slug"), "summary": res["summary"], "issues": res["issues"]})
            continue
        used_q |= res["keys"]
        p["summary"], p["faq"], p["summary_auto"] = res["summary"], res["faq"], True
        if res["thin"]:
            p["summary_thin"] = True
        else:
            p.pop("summary_thin", None)
        if res["notices"]:
            p["summary_notices"] = res["notices"]
        else:
            p.pop("summary_notices", None)
        written.append(p["id"])
        faq_n += len(res["faq"])
        thin_n += res["thin"]
    out = {"dry_run": dry_run, "written": len(written), "refused": len(refused), "faq": faq_n, "thin": thin_n,
           "refused_items": refused}
    if not dry_run and written:
        if path.read_text("utf-8") != before:
            raise SystemExit("places.json이 읽은 뒤 바뀌었습니다(다른 작업이 쓰는 중) — 다시 실행하세요")
        pc.write_atomic(path, pc.dump(places))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--all", action="store_true", help="locks에 summary가 없는 모든 레코드를 다시 만든다")
    ap.add_argument("--only", type=Path, help="장소 id·slug 목록 파일(place_content.read_only_list 형식)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today", help="공지를 읽는 날(YYYY-MM-DD, 기본 오늘)")
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로")
    a = ap.parse_args(argv)
    only = pc.read_only_list(a.only) if a.only else None
    res = run(a.data, every=a.all, only=only, dry_run=a.dry_run, today=a.today)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(json.dumps({k: v for k, v in res.items() if k != "refused_items"}, ensure_ascii=False))
        for r in res["refused_items"]:
            print(f"거부 {r['id']} {r['slug']}: {'; '.join(r['issues'])}")
    return 1 if res["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
