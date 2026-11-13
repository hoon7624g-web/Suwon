"""A sentence that TourAPI glued to the next one by its period ('이용 쉬움.내부 턱 없음') starts a new line on the page
(present.lines_html: an empty <span class="lb">) while the stored value, its display text and its translation key stay
as they are; items joined by a period ('마트.편의점', '유아.초.중.고', '토.일') stay whole."""
from markupsafe import escape

from pipeline.present import lines_html
from pipeline.textutil import display_value, restore_lines

LB = '<span class="lb"></span>'


def test_a_sentence_glued_by_its_period_starts_a_new_line_on_the_page():
    assert str(lines_html("휠체어 사용자 이용 쉬움.내부 턱 없음.")) == f"휠체어 사용자 이용 쉬움.{LB}내부 턱 없음."
    h = str(lines_html("장애인 전용 주차구역 주차대수 : 2대.주변 휠체어 이용자 등이 이용할 수 있는 여유공간 있음."
                       "관광지 주출입구까지의 거리 : 약 100m"))
    assert h.count(LB) == 2 and h.replace(LB, "").startswith("장애인 전용 주차구역 주차대수 : 2대.주변")
    assert str(lines_html("주차 가능.주변 여유공간 있음\n내부 턱 없음.")) == f"주차 가능.{LB}주변 여유공간 있음<br>내부 턱 없음."


def test_items_joined_by_a_period_and_open_brackets_stay_whole():
    for text in ("놀이터·산책로·마트.편의점", "의류 / 농.축산물 / 채소류", "소인 (유아.초.중.고/청소년)", "토.일 휴무",
                 "주.야간 운영", "약 3.5km", "허균.허난설헌 기념공원", "출입구 (경사로 있음.휠체어 가능)"):
        assert str(lines_html(text)) == str(escape(text)), text


def test_the_stored_value_and_its_display_text_do_not_change():
    raw = "장애인 전용 주차구역 있음.식당 건물 내 주차장 있음."
    assert display_value("accessible_parking", raw) == raw
    assert restore_lines(raw) == [raw]
    assert str(lines_html(display_value("accessible_parking", raw))).replace(LB, "") == raw
