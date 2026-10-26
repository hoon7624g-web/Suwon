"""pipeline/fee_table.py — a place's fee value read as the table a visitor pays (the first city's review 2026-10-17,
AI 코스 만들기 집중 평가 CE01·CE03: the planner prices every visit from these tables itself). The engine cases first,
then this city's own fee values as data/suwon/places.json holds them: what reads as a table, what
stays 확인 필요, and the rows that must never become an adult's entry price."""
import json
from pathlib import Path

from pipeline.fee_table import parse

ROOT = Path(__file__).resolve().parent.parent


def test_free_and_free_with_a_proviso():
    assert parse("무료") == {"free": True}
    assert parse("무료 (단, 여객선 비용 별도)") == {"free": True, "note": "단, 여객선 비용 별도"}
    assert parse("무료 (※ 단, 체육시설은 유료)") == {"free": True, "note": "단, 체육시설은 유료"}
    # the city's values: a proviso in brackets, after a line break, glued to 무료 with ※
    assert parse("무료 (시설이용료, 체험료 별도)") == {"free": True, "note": "시설이용료, 체험료 별도"}
    assert parse("무료\n※ 단, 일부 기획전시는 유료일 수 있으므로 홈페이지 참고") == \
        {"free": True, "note": "단, 일부 기획전시는 유료일 수 있으므로 홈페이지 참고"}
    assert parse("무료 ※단, 유료 특별·기획전시 제외") == {"free": True, "note": "단, 유료 특별·기획전시 제외"}
    assert parse("무료※ 단, 기획전 또는 특별전의 경우 관람료가 책정될 수 있으므로 자세한 사항은 홈페이지 참조")["free"] is True
    assert parse("무료\n※ 자세한 사항은 전화문의 요망") == {"free": True}


def test_the_place_s_own_ticket_not_the_combined_one():
    museum = "[박물관 통합권]\n- 성인 3,000원\n- 청소년·군인 2,000원\n- 어린이 1,000원\n[개별권]\n- 성인 2,000원\n- 청소년·군인 1,000원\n- 어린이 500원\n※ 자세한 사항은 홈페이지 참조"
    assert parse(museum) == {"tab": {"성인": 2000, "청소년·군인": 1000, "어린이": 500}, "tl": "개별권"}
    gallery = "[미술관 개별권]\n- 성인 500원\n- 청소년, 군인 300원\n- 어린이 200원\n[통합권]인근 전시장(박물관+미술관+건축관)\n- 성인 3,000원"
    assert parse(gallery)["tab"] == {"성인": 500, "청소년·군인": 300, "어린이": 200}


def test_the_visitor_s_price_not_the_resident_s_or_the_group_s():
    t = ("[시민]\n- 성인 1,000원\n- 청소년/군인 500원\n- 어린이 300원\n[타지역]\n- 성인 2,000원\n- 청소년/군인 1,000원\n"
         "- 어린이 500원\n※ 무료 : 6세 이하 유아 / 65세 이상 경로대상자 / 매주 수요일 문화가 있는 날 무료 관람\n※ 자세한 사항은 홈페이지 참조")
    assert parse(t) == {"tab": {"성인": 2000, "청소년·군인": 1000, "어린이": 500}, "tl": "타지역",
                        "fr": [{"w": "6세 이하 유아", "max": 6}, {"w": "65세 이상 경로대상자", "min": 65},
                               {"w": "매주 수요일 문화가 있는 날 무료 관람", "wd": 3}]}
    columns = ("개인 20인이상 단체 성인(시거주자) 1,000원(500원) 700원(300원) 청소년·군인(시거주자) 700원(300원) "
               "400원(200원) 어린이(시거주자) 500원(200원) 300원(100원) 무료입장 6세이하 유아, 65세이상 어른, 장애인, 유공자")
    r = parse(columns)
    assert r["tab"] == {"성인": 1000, "청소년·군인": 700, "어린이": 500}
    assert r["fr"] == [{"w": "6세이하 유아", "max": 6}, {"w": "65세이상 어른", "min": 65}, {"w": "장애인"}, {"w": "유공자"}]
    assert parse("[개인]\n- 성인 12,000원\n- 청소년 11,000원\n- 어린이 10,000원\n[단체(20인 이상)]\n- 성인 10,000원\n※ 무료 : 만 36개월 미만") \
        == {"tab": {"성인": 12000, "청소년": 11000, "어린이": 10000}, "tl": "개인", "fr": [{"w": "만 36개월 미만", "max": 2}]}


def test_no_table_this_reader_can_be_priced_from():
    # numbers without 원, rooms, months, ferries, ages only in words: the planner says 확인 필요
    assert parse("개인 단체(20인 이상) 성인 (시민) 1,000 (500) 700 (300)") == {}
    assert parse("월마다 요금이 다르므로 전화 문의 또는 홈페이지 참조 요망") == {}
    assert parse("[배편요금]- 입도 13,050원 / 출도 12,000원 (성인기준)") == {}
    assert parse("초등학생이상(1만원), 유치원생이하(5,000원)") == {}
    assert parse("1박 198,000원~350,000원(날짜·시즌에 따라 다름)") == {}
    assert parse("") == {}


# ------------------------------------------------------------------ the city's TourAPI fee values (2026-10-18)
def test_city_tables_read_as_the_visitor_pays():
    # 대구미술관: the [개인] table; a row naming several groups before one price gives it to 청소년; who enters free
    art = parse("[개인]\n- 성인 1,000원\n- 청소년 / 대학생 / 하사 이하의 군인 / 예술인 패스카드 소지자 700원\n[단체]\n- 성인 700원\n"
                "- 청소년 / 대학생 / 하사 이하의 군인 / 예술인 패스카드 소지자 500원\n※ 무료 : 독립유공자 / 독립유공자 배우자 / "
                "독립유공자 선순위 유족 / 국가유공자 / 5·18민주유공자 등\n※ 자세한 사항은 홈페이지 참조")
    assert art["tab"] == {"성인": 1000, "청소년": 700} and art["tl"] == "개인"
    assert {"w": "5·18민주유공자 등"} in art["fr"] and all("max" not in r for r in art["fr"])   # no age rule: kids stay 확인 필요
    # 이월드: every row names the same ticket ('자유이용권') — its table, with the ticket as the heading
    assert parse("- 성인 자유이용권 49,000원\n- 청소년 자유이용권 44,000원\n- 어린이 자유이용권 39,000원\n※ 자세한 사항은 홈페이지 참조") == \
        {"tab": {"성인": 49000, "청소년": 44000, "어린이": 39000}, "tl": "자유이용권"}
    # 대구 아쿠아리움: the categories' ages in brackets (만 나이, months as full years)
    assert parse("- 성인(만19세 이상) 29,000원\n- 청소년(만13세~만18세) 27,000원\n- 어린이(36개월~만12세) 25,000원") == \
        {"tab": {"성인": 29000, "청소년": 27000, "어린이": 25000}, "ag": {"청소년": [13, 18], "어린이": [3, 12]}}
    # 국립대구기상과학관: [개인]; '청소년, 어린이 1,000원' prices both; the [면제] section's 7세 이하
    sci = parse("[개인]\n- 성인 2,000원\n- 청소년, 어린이 1,000원\n[단체(20인 이상)]\n- 성인 1,000원\n- 청소년, 어린이 500원\n[면제]\n"
                "- 유아(유치원생 포함) : 7세 이하\n- 우대고객 : 경로우대자, 장애인 및 장애 정도가 심한 장애인동반 보호자 1인, 국가유공자 유족 및 가족\n"
                "※ 우대고객은 증빙서류 지참 필수")
    assert sci["tab"] == {"성인": 2000, "어린이": 1000, "청소년": 1000} and sci["tl"] == "개인"
    assert sci["fr"][0] == {"w": "유아(유치원생 포함) : 7세 이하", "max": 7}
    # 희움: '만 12세 미만' is up to 11; 글로우사파리·네이처파크: '24개월 미만' up to 1; 엘리몽: '12개월 이하 무료' only under 1
    assert parse("- 성인 2,000원\n- 청소년/고령자/장애인 1,000원\n※ 무료\n- 어린이(만 12세 미만) / 국가유공자 / 후원회원") == \
        {"tab": {"성인": 2000, "청소년": 1000}, "fr": [{"w": "어린이(만 12세 미만)", "max": 11}, {"w": "국가유공자"}]}
    assert parse("- 대인 20,000원- 소인 18,000원※ 무료 : 24개월 미만 유아※ 자세한 사항은 홈페이지 참조") == \
        {"tab": {"성인": 20000, "소인": 18000}, "fr": [{"w": "24개월 미만 유아", "max": 1}]}
    assert parse("- 어린이(24개월~초등학생) 20,000원\n- 성인 9,000원\n- 12개월 이하 무료\n※ 이용요금은 변동될 수 있으므로 홈페이지 참조")["fr"] == \
        [{"w": "12개월 이하", "max": 0}]
    # 신전뮤지엄: '대인 (중학생~성인)' is the adult's row; 엄마아빠어렸을적에: '중학생~성인 3,000원' too
    assert parse("- 대인 (중학생~성인) 10,000원- 소인(36개월~초등학생) 8,000원") == {"tab": {"성인": 10000, "소인": 8000}}
    assert parse("- 중학생~성인 3,000원\n- 어린이(만 3세)~초등학생 2,500원\n- 단체(25명 이상) 1,500원") == {"tab": {"성인": 3000}}


def test_city_values_that_stay_check_needed():
    # 팔공산 케이블카: round trip or one way, by heading — no single price for a visit
    assert parse("[대인]\n- 왕복 14,000원\n- 편도 11,000원\n[소인]\n- 왕복 8,000원\n- 편도 5,500원\n[경로우대(만65세 이상), 국가유공자, 장애인]\n"
                 "- 왕복 12,000원\n- 편도 8,000원\n※ 이용요금은 변동될 수 있으므로 홈페이지 참고") == {}
    # 앞산 케이블카: the [개인] table names a round trip and a one way for each category — never the first of them
    assert parse("[개인]\n- 대인 왕복 14,000원\n- 대인 편도 10,000원\n- 소인 왕복 10,000원\n- 소인 편도 6,000원\n[단체]\n- 대인 왕복 12,000원\n"
                 "※ 자세한 사항은 홈페이지 참조") == {}
    # 아르떼수성랜드: '아이스링크 대인 10,000원' is the rink's price, not the entry's (입장 3,000원 names no category)
    assert parse("입장 3,000원\n입장+놀이1종 6,500원\n입장+놀이3종 12,000원\n입장+놀이5종 17,000원\n아이스링크 대인 10,000원\n"
                 "아이스링크 소인 8,000원\n※ 이용요금은 변동될 수 있으므로 홈페이지 참조 또는 전화 문의 요망") == {}
    # 사유원: weekday and weekend tables; 사문진나루터: the boat's weekday and weekend prices; 달성화석박물관: no 원
    assert parse("[주중]- 일반 50,000원- 청소년 45,000원[주말 및 공휴일] - 일반 69,000원 - 청소년 62,000원 ※ 자세한 사항은 홈페이지 참조") == {}
    assert parse("[유람선]\n- 평일 대인 10,000원\n- 평일 소인 7,000원\n- 주말 대인 12,000원\n- 주말 소인 9,000원") == {}
    assert parse("일반 성인 3000/일반 어린이, 청소년 2000/달성군민 성인 1500/달성군민 어린이, 청소년 1000") == {}
    # a lone amount says nothing of children; a range is not a price; programmes are not an entry fee
    assert parse("8,000원") == {}
    assert parse("120,000원~190,000원\n※ 이용요금은 변동될 수 있으므로 홈페이지 참조 또는 전화 문의 요망") == {}
    assert parse("※ 공연별 상이하므로 홈페이지 참고") == {}


def test_every_published_fee_value_of_the_city_reads_without_an_adult_less_table():
    """All of this city's data/suwon/places.json: a table always has an adult's price, a free value no table, ages only beside a
    table; an adult's price is one the value itself writes."""
    places = json.loads((ROOT / "data" / "suwon" / "places.json").read_text("utf-8"))
    seen = 0
    for p in places:
        v = (p.get("facts") or {}).get("usefee")
        if p.get("status") != "published" or not v:
            continue
        seen += 1
        r = parse(v)
        assert not (r.get("free") and r.get("tab")), p["name"]
        if "tab" in r:
            assert "성인" in r["tab"] and f"{r['tab']['성인']:,}원" in v.replace("\n", " "), (p["name"], r)
        assert set(r) <= {"free", "note", "tab", "tl", "fr", "ag"}, p["name"]
        assert ("fr" not in r and "ag" not in r) or "tab" in r, p["name"]
    assert seen >= 30          # the scan sees the city's fee values (41 published places on 2026-10-24)
