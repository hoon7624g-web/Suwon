"""UI 2026-10-31 (operator: '이런 것들도 줄바꿈도 그렇고, UI 좀 더 세련되게'): line breaks around '·' '~' '/' in titles,
the home's answer tiles and the list cells (pipeline/textutil.py keep_dots — from the 부평시장각 engine — keep_units,
cell_html), the list cell macro (_p1 cellv), the answer tile (_p2 answer) and the home's guide groups
(present.guide_groups). Only tags are added: the text a reader, a search engine or the validator reads is unchanged."""
import re
from types import SimpleNamespace

from markupsafe import escape

from pipeline import present
from pipeline.build import css_source, make_env
from pipeline.textutil import cell_html, keep_dots, keep_units

TAGS = re.compile(r"<[^>]+>")
MORE = ' <span class="kf-more">외</span>'


def text(html: str) -> str:
    return TAGS.sub("", html)


def test_a_title_keeps_its_dot_with_the_letter_before_it():
    html = ('<h1 class="x" title="a·b">1박 2일·2박 3일 <a href="/a·b/">가·나</a></h1><p>다·라</p>'
            '<a class="line-name" href="/c/">공원·박물관</a><div class="qa"><h3>체크인·체크아웃</h3></div>'
            '<details class="qa"><summary><h3>운임은 토·일에 더 비싼가요?</h3></summary></details>')
    out = keep_dots(html)
    assert ('<h1 class="x" title="a·b">1박 2<span class="dj">일·</span><wbr>2박 3일 '
            '<a href="/a·b/"><span class="dj">가·</span><wbr>나</a></h1>') in out
    assert '<p>다·라</p>' in out and '<a class="line-name" href="/c/">공<span class="dj">원·</span><wbr>박물관</a>' in out
    assert '<h3>체크인·체크아웃</h3>' in out          # an FAQ question is read word for word: left as written
    assert '<summary><h3>운임은 토·일에 더 비싼가요?</h3>' in out
    assert keep_dots("<h2>점 없음</h2>") == "<h2>점 없음</h2>"
    assert text(out) == text(html)


CASES = [
    "군산시 공식 당일 코스: A코스 근대~고군산 · B코스 근대~금강권 · C코스 고군산",
    "근대역사박물관·진포해양공원·테디베어박물관은 서로 직선 1km 안 · 월요일에도 여는 곳은 테디베어박물관·킹콩놀이터",
    "매주 월요일 / 1월 1일",
    "좌석수 400석/ 주차 100대",
    "선유도는 배 없이 차로 · 다리로 이어진 네 섬은 무녀도→선유도→장자도→대장도, 직선 약 3.6km",
    'A&B <i> "q"', "", "·", " / ",
]


def test_keep_units_only_adds_tags():
    for t in CASES:
        assert text(keep_units(t)) == str(escape(t)), t
        assert text(keep_units(t, MORE)) == str(escape(t)) + " 외", t


def test_keep_units_never_lets_a_mark_begin_a_line():
    # a spaced list mark sits with the word before it (no break between them: one no-wrap piece), so the line
    # breaks after it; a mark inside a word too ('관·')
    out = keep_units(CASES[1])
    assert '<span class="dj">안 ·</span> 월요일에도' in out
    assert '테디베어박물<span class="dj">관·</span>킹콩놀이터' in out
    assert not re.search(r"(?:^|>|\s)[·~/→]", re.sub(r'<span class="dj">[^<]*</span>', "", out))
    # a short run joined by marks is one unit; a long one only keeps each mark with its letter
    first = keep_units(CASES[0])
    assert '<span class="ku">근<span class="dj">대~</span>금강<span class="dj">권 ·</span></span>' in first
    assert '<span class="ku">C코스 고군산</span>' in first        # a short spaced-list part: one unit
    assert '<span class="ku">근대역사' not in out                   # longer than UNIT_MAX: no inline-block
    # each part of a short spaced list stays whole ('1월' | '1일' never), the mark at the end of the first
    assert keep_units(CASES[2]) == ('<span class="ku">매주 월요<span class="dj">일 /</span></span> '
                                    '<span class="ku">1월 1일</span>')
    assert keep_units('A&B <i> "q"') == 'A&amp;B &lt;i&gt; &#34;q&#34;'


VALUES = [
    ("하절기(3~10월) 09:00–18:00(입장마감 17:30)", False),
    ("동절기(11월~2월) 09:00–17:00(입장마감 16:30)", True),
    ("가능 (근대역사박물관, 진포해양공원 주차장)", False),
    ("매주 월요일 / 1월 1일", True),
    ("하절기 09:00–18:00 · 하절기(입장마감 17:30), 동절기(입장마감 16:30)", False),
    ("11:00–21:00", True), ("준비시간 14:00–17:00", True), ("초원사진관(매주 첫째, 셋째 월요일)", False),
    ("생선탕(찜)", False), ("한우떡갈비(200g)24,000원", True), ("가능 (a / b)", False), ("(전체)", False),
]


def test_a_cell_value_is_split_into_parts_without_changing_its_words():
    for v, more in VALUES:
        out = cell_html(v, MORE if more else "")
        assert text(out) == str(escape(v)) + (" 외" if more else ""), v
    # the season before a time is its label, the time is never broken, the last entry is .kfl beside it
    assert cell_html(VALUES[0][0]) == ('<span class="cv-l"><span class="ku">하절기(<span class="dj">3~</span>10월)</span>'
                                       '</span> <span class="cv-t">09:00–18:00</span>'
                                       '<span class="cv-n kfl">(입장마감 17:30)</span>')
    # a bracket of words is the value's note (a small line under it); a short one stays in the value
    assert cell_html(VALUES[2][0]) == ('<span class="cv-h">가능</span> '
                                       '<span class="cv-n">(근대역사박물관, 진포해양공원 주차장)</span>')
    assert cell_html("생선탕(찜)") == '<span class="cv-h">생선탕(찜)</span>'
    # '외' never stands alone: glued inside the time, the note or the last word
    assert cell_html("11:00–21:00", MORE) == f'<span class="cv-t">11:00–21:00{MORE}</span>'
    assert cell_html(VALUES[1][0], MORE).endswith(f'<span class="dj">){MORE}</span></span>')
    assert '<span class="dj">원' + MORE + "</span>" in cell_html("한우떡갈비(200g)24,000원", MORE)
    # parts of a list are units, a list mark inside a bracket is not a part's end
    parts = cell_html(VALUES[4][0])
    assert parts.startswith('<span class="ku"><span class="cv-l">하절기</span> <span class="cv-t">09:00–18:00 ·</span></span> ')
    assert '<span class="cv-n">(<span class="dj">a /</span> b)</span>' in cell_html("가능 (a / b)")


def test_the_list_cell_macro():
    cellv = make_env().get_template("_p1.html.j2").module.cellv
    slot = {"key": "hours", "label": "이용시간", "main": "10:00–17:00", "sub": "점심시간 12:00–13:00", "more": True,
            "closed": False, "conflict": False, "missing": False, "vals": []}
    out = str(cellv(slot, "p1"))
    assert out == ('<span class="kf-main tn cv"><span class="cv-t">10:00–17:00</span></span>'
                   '<span class="kf-sub tn cv"><span class="cv-l">점심시간</span> '
                   f'<span class="cv-t">12:00–13:00{MORE}</span></span>')
    closed = str(cellv({**slot, "key": "closed", "main": "매주 월요일 / 1월 1일", "sub": "", "more": False, "closed": True}))
    assert closed.startswith('<span class="kf-main tn cv closed">') and text(closed) == "매주 월요일 / 1월 1일"
    # a missing value, a phone number and a conflict keep the shared tile markup (ui.kfv)
    na = str(cellv({**slot, "main": "", "sub": "", "missing": True}))
    assert na == '<span class="kf-na">확인 필요</span>'


def test_the_answer_tile_puts_its_note_and_arrow_on_the_foot():
    answer = make_env().get_template("_p2.html.j2").module.answer
    a = {"key": "비 오는 날", "href": "/guides/x/", "answer": "해망로 실내 전시관 4곳 · 그중 3곳은 통합권",
         "closed": "월요일엔 전시관 8곳 휴관 · 여는 곳은 테디베어박물관·군산항1981", "fig": "4", "unit": "곳", "fig_label": ""}
    out = str(answer(a))
    assert '<span class="ans-n"><b class="num tn">4</b><small class="ans-u">곳</small></span>' in out
    foot = out[out.index('<span class="ans-f">'):]
    assert foot.index('class="ans-closed"') < foot.index('class="arr"')       # note, then the arrow, one foot
    assert '<span class="dj">관·</span>군산항1981' in foot and 'class="closed"' not in out
    labelled = str(answer({**a, "closed": "", "fig": "09:30", "unit": "", "fig_label": "토·일 첫 출발"}))
    assert '<small class="ans-fl">토·일 첫 출발</small>' in labelled and 'class="ans-closed"' not in labelled
    css = " ".join(css_source().split())
    assert ".ans-f { order: 3; display: flex; align-items: flex-end; gap: 14px; margin-top: auto; }" in css
    assert ".dj { white-space: nowrap; display: contents; }" in css and ".ku { display: inline-block; }" in css


def test_guides_fall_into_groups_read_off_the_guides():
    kinds = {"a": "attraction", "f": "food", "s": "stay"}
    S = SimpleNamespace(ent_by_slug={k: {"kind": v} for k, v in kinds.items()}, guides=[
        {"id": "g1", "label": "차 없는 여행", "items": [{"place_slug": "a"}]},
        {"id": "g2", "label": "먹거리·짬뽕", "items": [{"place_slug": "f"}, {"place_slug": "f"}, {"place_slug": "a"}]},
        {"id": "g3", "label": "숙소·펜션", "items": [{"place_slug": "s"}, {"place_slug": "s"}, {"place_slug": "a"}]},
        {"id": "g4", "label": "시내버스로 관광지 가기", "items": [{"place_slug": "a"}]},
        {"id": "g5", "label": "관광지 근처 공영주차장", "items": [{"place_slug": "f"}]},
        {"id": "g6", "label": "시장", "items": [{"place_slug": "a"}, {"place_slug": "f"}]},   # half food: not 먹거리
        {"id": "g7", "label": "시외·고속버스·공항", "items": []},
    ])
    groups = present.guide_groups(S)
    assert [(g["name"], [x["id"] for x in g["guides"]]) for g in groups] == [
        ("여행·볼거리", ["g1", "g6"]), ("먹거리", ["g2"]), ("숙소", ["g3"]), ("교통·주차", ["g4", "g5", "g7"])]
    S.guides = S.guides[:1]
    assert [g["name"] for g in present.guide_groups(S)] == ["여행·볼거리"]   # an empty group is left out
