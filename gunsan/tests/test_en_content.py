"""English pages: Revised Romanization, English addresses, EngService2 matching and the parity check."""
import json

from tools.en_content import CONFLICT_NOTE, address_en, check, match_en, parity, romanize, style

ITEM = {"id": "p1", "slug": "근대건축관", "kind": "attraction", "category": "관광지", "indexable": True,
        "name": "군산근대건축관", "name_en": "Gunsangeundaegeonchukgwan", "name_en_source": "romanized",
        "alternate_names": [],
        "facts": [{"key": "address", "label": "주소", "value": "전북특별자치도 군산시 해망로 214",
                   "address_en_candidate": "214 Haemang-ro, Gunsan-si, Jeonbuk State"},
                  {"key": "usetime", "label": "이용시간", "value": "09:00–18:00",
                   "alternatives": [{"value": "상시 개방", "provider": "한국관광공사 TourAPI"}]},
                  {"key": "restdate", "label": "쉬는 날", "value": "매주 월요일"},
                  {"key": "usefee", "label": "이용요금", "value": "성인 500원, 단체 1만원"},
                  {"key": "infocenter", "label": "문의", "value": "063-454-7870"}],
        "summary": "군산근대건축관은 옛 조선은행 군산지점 건물로, 2008년에 복원을 마쳤습니다.",
        "details": [], "faq": [{"q": "군산근대건축관은 언제 쉬나요?", "a": "매주 월요일에 쉽니다."}],
        "mentions": [], "ko_hash": "x"}

GOOD = {"id": "p1", "name_en": "Gunsangeundaegeonchukgwan",
        "summary": "Gunsangeundaegeonchukgwan is the former Gunsan branch of the Bank of Chosun. Its restoration "
                   "was finished in 2008.",
        "facts": [{"key": "address", "value": "214 Haemang-ro, Gunsan-si, Jeonbuk State"},
                  {"key": "usetime", "value": "09:00–18:00", "alternatives": [{"value": "Always open"}],
                   "note": CONFLICT_NOTE},
                  {"key": "restdate", "value": "Every Monday"},
                  {"key": "usefee", "value": "Adults 500 won, groups 10,000 won"},
                  {"key": "infocenter", "value": "063-454-7870"}],
        "details": [], "faq": [{"q": "When is Gunsangeundaegeonchukgwan closed?", "a": "It is closed every Monday."}]}


def write_pair(tmp_path, out):
    (tmp_path / "en-01.input.json").write_text(json.dumps({"type": "places", "items": [ITEM]}, ensure_ascii=False), "utf-8")
    path = tmp_path / "en-01.output.json"
    path.write_text(json.dumps({"items": [out]}, ensure_ascii=False), "utf-8")
    return path


def test_romanize_follows_revised_romanization():
    assert romanize("월명공원") == "Wolmyeonggongwon"
    assert romanize("신라") == "Silla"            # ㄴ+ㄹ -> ll
    assert romanize("종로") == "Jongno"           # ㅇ+ㄹ -> ng n
    assert romanize("백마") == "Baengma"          # nasalization
    assert romanize("해돋이") == "Haedoji"        # palatalization
    assert romanize("묵호") == "Mukho"            # noun: ㄱ+ㅎ stays k h
    assert romanize("선유도") == "Seonyudo"
    assert romanize("경암동 철길마을") == "Gyeongam-dong Cheolgilmaeul"
    assert romanize("구 일본 제18은행") == "Gu Ilbon Je18eunhaeng"


def test_address_en_reads_road_and_lot_addresses():
    assert address_en("전라북도 군산시 월명공원1길 26") == "26 Wolmyeonggongwon 1-gil, Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 백토로 284-22 (나운동)") == \
        "284-22 Baekto-ro (Naun-dong), Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 옥도면 선유도리 474-1") == \
        "474-1 Seonyudo-ri, Okdo-myeon, Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 수송안7길 36 청담횟집") == ""   # a business name: the translator writes it


def test_match_en_needs_distance_and_type():
    place = {"name": "선유도", "kind": "attraction", "geo": {"lat": 35.81, "lng": 126.41},
             "tourapi": {"contenttypeid": "12"}}
    near = {"contentid": "1", "contenttypeid": "76", "title": "Seonyudo Island (선유도)", "mapy": "35.8105", "mapx": "126.41"}
    food = {**near, "contentid": "2", "contenttypeid": "82"}
    far = {**near, "contentid": "3", "mapy": "35.83"}
    it, dist, basis = match_en(place, [food, far, near])
    assert it["contentid"] == "1" and dist < 150 and basis == "coordinates_type_korean_title"
    assert match_en(place, [food, far])[0] is None


def test_check_passes_a_faithful_translation(tmp_path):
    assert check([write_pair(tmp_path, GOOD)]) == []


def test_check_finds_changed_values_style_and_missing_conflict(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["facts"][1] = {"key": "usetime", "value": "9:00 AM–6:00 PM"}            # 12-hour, conflict dropped
    bad["facts"][2]["value"] = "Every Tuesday"                                   # wrong weekday
    bad["facts"][3]["value"] = "Adults ₩500, groups 1 man won"                   # money convention, 1만원
    bad["facts"][4]["value"] = "+82-63-454-7870"                                 # phone changed
    bad["summary"] = "A famous former bank, restored in 2009. 군산"               # banned word, number, Korean left
    issues = "\n".join(check([write_pair(tmp_path, bad)]))
    for want in ("12-hour time", "facts.usetime.alternatives: missing", f"note must be '{CONFLICT_NOTE}'",
                 "weekday Monday missing", "weekday Tuesday not in Korean", "amount 10,000 won missing",
                 "no ₩/KRW", "phone 063-454-7870 missing", "promotional word: 'famous'", "number 2008 missing",
                 "number 2009 not in Korean", "Korean script left"):
        assert want in issues, want


def test_check_requires_every_item(tmp_path):
    path = write_pair(tmp_path, GOOD)
    path.write_text(json.dumps({"items": []}), "utf-8")
    assert any("p1: not translated" in x for x in check([path]))


def test_parity_reads_approximate_korean_myriads():
    assert parity("부지 70여만 평", "a site of about 700,000 pyeong") == []      # 70여만 = 700,000-plus
    assert parity("5만여 평", "about 50,000 pyeong") == []
    assert "number 70000 not in Korean" in parity("70여만 평", "about 70,000 pyeong")


def test_parity_reads_weekday_abbreviations_with_particles():
    # '월~금은', '토~일에는' (a particle after the range) and '금 11:00' (one day right before a time)
    assert parity("월~금은 11:00-17:00, 토~일은 11:00-18:00에 영업합니다.",
                  "Monday–Friday 11:00–17:00, Saturday–Sunday 11:00–18:00.") == []
    assert parity("월~목 11:00–23:00 금 11:00~익일02:00", "Monday–Thursday 11:00–23:00, Friday 11:00–02:00 the next day") == []
    assert "weekday Friday missing" in parity("금은 11:00~익일 02:00", "11:00–02:00 the next day")
    assert parity("매월 10:00 개장", "Opens at 10:00 every month") == []   # '매월' is not Monday


def test_promotional_word_inside_a_place_name_is_a_name():
    assert style("Best Western Gunsan Hotel has 80 rooms.") == []
    assert any("promotional" in x for x in style("It is the best hotel in Gunsan."))


def test_hours_followed_by_copula_or_particle_are_times():
    assert parity("체크인은 15시이고 체크아웃은 11시입니다", "Check-in is 15:00 and check-out is 11:00.") == []
    assert parity("체크아웃은 12시가 많습니다", "Check-out is usually 12:00.") == []
    assert parity("3시간 걸립니다", "It takes 3 hours.") == []          # 시간 (hours) is not a clock time


def test_programme_title_hour_is_not_a_clock_time():
    assert parity("방송사 채널 영상: 6시 내고향 — 만남스넥", "Broadcaster channel video: 6si Nae Gohyang — Mannam Snack") == []
    assert "number 6 missing" in parity("6시 내고향", "Nae Gohyang")


# ---- columns (data/<region>/columns.json): paragraph for paragraph, the guide's parity and style checks
COLUMN = {"id": "c1", "slug": "해망로-근대건축", "category": "역사·건축 해설", "label": "해망로 근대건축",
          "title": "해망로 근대건축 산책", "dek": "1908년 세관 본관부터 근대건축 5곳을 걷는다.",
          "summary": "해망로에는 1908년에 완공된 구 군산세관 본관이 있습니다.", "pull_quote": "붉은 벽돌이 남았다.",
          "body": [{"heading": "1908년의 세관", "paras": ["구 군산세관 본관은 1908년 6월에 완공됐다.", "입장료는 무료다."]}],
          "items": [{"place_slug": "호남관세박물관", "place_name": "호남관세박물관", "place_name_en": "Honam Customs Museum",
                     "reason": "1908년 6월 완공된 세관 건물이다."}],
          "sources": [{"name": "군산근대역사박물관", "url": "https://www.gunsan.go.kr/museum/"}], "mentions": [], "ko_hash": "h"}
COLUMN_GOOD = {"id": "c1", "category": "History and architecture", "label": "Modern buildings on Haemang-ro",
               "title": "A walk past the modern buildings of Haemang-ro",
               "dek": "5 modern buildings, from the 1908 customs house on.",
               "summary": "Haemang-ro has the former Gunsan Customs House, finished in 1908.",
               "pull_quote": "The red brick remains.",
               "body": [{"heading": "The customs house of 1908",
                         "paras": ["The former Gunsan Customs House was finished in June 1908.", "Entry is free."]}],
               "items": [{"place_slug": "호남관세박물관", "reason": "A customs building finished in June 1908."}],
               "sources": [{"name": "Gunsan Modern History Museum"}]}


def _column_pair(tmp_path, out):
    (tmp_path / "en-01.input.json").write_text(json.dumps({"type": "columns", "items": [COLUMN]}, ensure_ascii=False),
                                               "utf-8")
    path = tmp_path / "en-01.output.json"
    path.write_text(json.dumps({"items": [out]}, ensure_ascii=False), "utf-8")
    return path


def test_a_column_is_checked_paragraph_for_paragraph(tmp_path):
    assert check([_column_pair(tmp_path, COLUMN_GOOD)]) == []
    bad = json.loads(json.dumps(COLUMN_GOOD))
    bad["body"][0]["paras"] = ["The former Gunsan Customs House was finished in June 1908. Entry is free."]
    bad["dek"] = "Five modern buildings."
    bad["items"][0]["place_slug"] = "x"
    issues = "\n".join(check([_column_pair(tmp_path, bad)]))
    for want in ("body[0].paras: 1 given, Korean has 2", "dek: number 1908 missing",
                 "items[0].place_slug must be '호남관세박물관'"):
        assert want in issues, want


def test_a_merged_column_keeps_the_korean_slug_places_sources_and_hash(tmp_path):
    from tools.en_content import merge
    data = tmp_path / "data"
    data.mkdir()
    (data / "places.json").write_text("[]", "utf-8")
    out = _column_pair(tmp_path, COLUMN_GOOD)
    assert merge([out], data)["columns"] == 1
    rec = json.loads((data / "en" / "columns.json").read_text("utf-8"))["c1"]
    assert rec["slug"] == "해망로-근대건축" and rec["ko_hash"] == "h"
    assert rec["body"] == COLUMN_GOOD["body"] and rec["items"] == [{"place_slug": "호남관세박물관",
                                                                   "reason": "A customs building finished in June 1908."}]
    assert rec["sources"] == [{"name": "Gunsan Modern History Museum", "url": "https://www.gunsan.go.kr/museum/"}]


def test_column_batches_carry_the_page_paragraphs_and_the_build_hash(tmp_path):
    from pathlib import Path
    from pipeline.en_source import current_hashes
    from tools.en_content import COLUMN_BATCH, prepare
    data = Path(__file__).resolve().parents[1] / "data" / "gunsan"
    cols = [c for c in json.loads((data / "columns.json").read_text("utf-8")) if c.get("status") == "published"]
    res = prepare(tmp_path / "ja", data=data, lang="ja", only=("columns",))
    assert {b["type"] for b in res["batches"]} == {"columns"} and len(res["batches"]) == -(-len(cols) // COLUMN_BATCH)
    items = [i for f in sorted((tmp_path / "ja").glob("ja-*.input.json"))
             for i in json.loads(f.read_text("utf-8"))["items"]]
    hashes = current_hashes(data)["columns"]
    assert [i["id"] for i in items] == [c["id"] for c in cols] and all(i["ko_hash"] == hashes[i["id"]] for i in items)
    for i, c in zip(items, cols):
        assert [len(b["paras"]) for b in i["body"]] == \
            [len([x for x in b["text"].split("\n") if x.strip()]) for b in c["body"]]
        assert all("quote" not in b for b in i["body"])   # an original-language quote is never translated


def test_a_month_or_weekday_is_a_whole_word_in_every_language():
    from tools.en_content import _l_days, parity_l
    # maison, main, mayor, Mainz, маяк are not May; среди and средний are not Wednesday (columns review 2026-10-25)
    assert parity_l("집과 손", "la maison et la main, maintenant", "fr") == []
    assert parity_l("가장 큰 박물관", "el mayor museo", "es") == []
    assert parity_l("마인츠의 집", "ein Haus in Mainz", "de") == []
    assert parity_l("섬 사이의 등대", "маяк среди островов", "ru") == []
    assert parity_l("5월에 연다.", "Открыт в мае.", "ru") == [] and parity_l("5월에 연다.", "Ouvert en mai.", "fr") == []
    assert _l_days("по средам", "ru")[0] == {"wednesday"}


def test_banzai_is_not_ten_thousand():
    from tools.en_content import parity_l
    assert parity_l("군산 3.5 만세운동", "群山3.5万岁运动", "zh-hans") == []
    assert parity_l("입장료 1만원", "门票1万韩元", "zh-hans") == []


def test_german_am_after_a_time_is_a_preposition():
    from tools.en_content import parity_l, style_l
    assert style_l("Um 18:00 am Hafen und ab 4 am Ufer.", "de") == []
    assert any("24-hour" in x for x in style_l("Um 6 PM geöffnet.", "de"))


def test_the_sea_at_the_end_of_a_sentence_is_not_a_weekday():
    from tools.en_content import _l_days
    assert _l_days("Le phare regarde la mer.", "fr")[0] == set() and _l_days("Mira al mar.", "es")[0] == set()
    assert _l_days("lun.–ven. 09:00–18:00", "fr")[1] >= {"monday", "friday"}


def test_korean_times_months_and_names_read_as_a_translation_writes_them():
    # columns review 2026-10-25: a time before 나/의/여서, an hour range under one 오후, a month word, and numbers
    # that are part of a name — a faithful translation writes 09:00, 16:00–17:00, April, per person, World War II
    from tools.en_content import parity, parity_l
    assert parity("오전 9시나 10시 개관 직후에", "right after opening at 09:00 or 10:00") == []
    assert parity("오후 4~5시경에는 버스에 오르고", "board a bus around 16:00–17:00") == []
    assert parity("1~2시간 남짓 산책", "a walk of about 1–2 hours") == []
    assert parity("체크아웃이 낮 12시여서", "check-out is at 12:00, so") == []
    assert parity("6시의 소고기무국", "beef soup at 06:00") == []
    assert parity("사월의 바람과 시월의 밤공기", "the April wind and the October night air") == []
    assert parity("1인당 1,000~2,000원 할인", "a discount of 1,000–2,000 won per person") == []
    assert parity("2차 세계대전 당시 건조된 상륙함", "a landing ship built during World War II") == []
    assert parity("6·25 전쟁에 참전한 상륙함", "a landing ship that served in the Korean War") == []
    assert parity_l("오후 5~6시 무렵", "vers 17:00–18:00", "fr") == []
    assert parity("오후 4~5시경", "around 4 o'clock and 17:00")   # the half-number form no longer passes


# ---- checker rules brought from the other engines (2026-11-01, the translation-table port) beside this engine's own
def test_weekdays_listed_with_slashes_or_standing_alone_are_read():
    """2026-10-31 (the other engine's TourAPI values): '주중(화/수/목)', '주말(금/토/일/공휴일)', a value cut to '매일 화'
    and '{t2}토 {t3}' name weekdays, so the translation must name them — while '1월 1일', '월 1회' and '일 3회' name none."""
    from tools.en_content import _ko_days
    assert _ko_days("주중(화/수/목)")[0] == {"tuesday", "wednesday", "thursday"}
    assert _ko_days("주말(금/토/일/공휴일)")[0] == {"friday", "saturday", "sunday"}
    assert _ko_days("매일 화")[0] == {"tuesday"}
    assert _ko_days("평일/토")[0] == {"saturday"}
    # the noun 수 (count) is not Wednesday: '객실 수·취사', '구·군별 수'
    for ko in ("1월 1일 휴무", "월 1회 휴무", "일 3회 운영", "매일 10:00~18:00", "구·군별 수",
               "체크인 시각·객실 수·취사·사이트 수는 어떻게 되나요?"):
        assert _ko_days(ko)[0] == set(), ko
    assert parity("주중(화/수/목)", "Weekdays (Tuesday/Wednesday/Thursday)") == []
    assert parity("10:10토 15:15", "10:10, Saturday 15:15") == []
    assert parity("월~금 01:05–02:10토 03:15–04:20", "Mon–Fri 01:05–02:10, Sat 03:15–04:20") == []
    assert parity("주중(화/수/목)", "Tuesday/Wednesday") == ["weekday Thursday missing"]


def test_a_syllable_of_a_list_of_goods_is_not_a_weekday():
    """'농·수·축산물': 수 there is 수산물 (fishery goods), not Wednesday — a lone weekday syllable after '·' counts only
    after a day word ('평일·토'); '평일·토요일' names Saturday alone (the 일 of 평일 is no Sunday)."""
    from tools.en_content import _ko_days
    assert _ko_days("농·수·축산물 및 공산품 일체")[0] == set()
    assert parity("농·수·축산물 판매", "Farm, marine and livestock products on sale") == []
    assert _ko_days("평일·토")[0] == {"saturday"} and _ko_days("토")[0] == {"saturday"}
    assert _ko_days("평일·토요일·공휴일 09:00~18:00")[0] == {"saturday"}


def test_a_weekday_service_names_its_day():
    """'수요기도회 19:30': the Wednesday prayer meeting names Wednesday; German writes the day in a compound."""
    from tools.en_content import _ko_days, parity_l
    assert _ko_days("- 수요기도회 19:30")[0] == {"wednesday"}
    assert parity("- 수요기도회 19:30", "- Wednesday prayer meeting 19:30") == []
    assert parity_l("- 수요기도회 11:00", "- Mittwochsgebet 11:00", "de") == []
    assert parity_l("- 수요기도회 11:00", "- Gebet 11:00", "de") == ["weekday Mittwoch missing"]


def test_a_latin_name_in_the_korean_is_not_read_as_a_month():
    """'호텔 준 (Hotel June …)': the Korean already writes the name in Latin letters and the English repeats it, so its
    'June' is no 6; a month the English adds is still caught."""
    ko = "호텔 준 (Hotel June Incheon Airport)은 객실 48실을 갖춘 숙소입니다."
    assert parity(ko, "Hotel June Incheon Airport is a place to stay with 48 rooms.") == []
    assert parity("호텔 준은 객실 48실을 갖춘 숙소입니다.", "Hotel June has 48 rooms.") == ["number 6 not in Korean"]
    assert parity("더스카이184(THE SKY184)의 요금은 15,000원입니다.", "THE SKY184 charges 15,000 won.") == []


def test_room_numbers_listed_with_a_comma_are_two_numbers():
    """'… 2층 203,204호': rooms 203 and 204, as parity_l reads them (Gunsan's stored English writes 'Units 203,204',
    which the check now asks to write 'Units 203, 204')."""
    ko = "전북특별자치도 군산시 궁포1로 24-5, 2층 203,204호 (조촌동)"
    assert parity(ko, "Units 203, 204, 2nd floor, 24-5 Gungpo 1-ro (Jochon-dong), Gunsan-si, Jeonbuk State") == []
    assert "number 203204 not in Korean" in parity(ko, "Units 203,204, 2nd floor, 24-5 Gungpo 1-ro (Jochon-dong), "
                                                       "Gunsan-si, Jeonbuk State")


def test_the_other_engines_hour_rules_sit_beside_this_engines():
    """A weekday right after a time ('20:00토 10:00'), the chain '목. 금. 토. 일 요일', the range '목요일~월요일', an hour
    range whose first hour has its own word and no 시 ('오전10-오후10시'), '오후 4:00' as 16:00 — and this engine's own
    '오후 4~5시경' (one word for both hours) still 16:00–17:00."""
    from tools.en_content import _ko_days
    assert parity("평일 11:00~20:00토 10:00~21:00", "Weekdays 11:00–20:00, Saturday 10:00–21:00") == []
    assert _ko_days("목. 금. 토. 일 요일")[0] == {"thursday", "friday", "saturday", "sunday"}
    assert _ko_days("목요일~월요일")[1] == {"thursday", "friday", "saturday", "sunday", "monday"}
    assert parity("오전10-오후10시", "10:00–22:00") == []
    assert parity("10~18시", "10:00–18:00") == []
    assert parity("오후 4~5시경", "around 16:00–17:00") == []
    assert parity("입실은 오후 3:00부터입니다.", "Check-in is from 15:00.") == []


def test_won_written_with_dots_and_words_that_begin_with_won():
    """'2.000원' is 2,000 won (a source writing thousands with dots); 원 after a number that begins a word (원도심, 원조)
    is not money; '3백 명' is 300."""
    assert parity("입장료 2.000원", "Admission 2,000 won") == []
    assert parity("해망로 56 원도심 일대", "the old downtown area around 56 Haemang-ro") == []
    assert parity("최대 3백 명", "up to 300 people") == []


def test_a_french_or_spanish_weekday_abbreviation_in_brackets_is_its_day():
    """Gunsan's event dates ('2024. 6. 9.(일)') are written '9 juin 2024 (dim.)' and '9 de junio de 2024 (dom.)': the
    abbreviation in brackets names the day; 'mer.' and 'mar.' ending a sentence stay the sea."""
    from tools.en_content import _l_days, parity_l
    assert parity_l("2024. 6. 9.(일) 10:00~18:00", "9 juin 2024 (dim.), 10:00–18:00", "fr") == []
    assert parity_l("2024.9.25 (수) 10:00~", "25 septembre 2024 (mer.), à partir de 10:00", "fr") == []
    assert parity_l("2024. 6. 9.(일) 10:00~18:00", "9 de junio de 2024 (dom.), 10:00–18:00", "es") == []
    assert parity_l("2024. 6. 9.(화) 10:00", "9 de junio de 2024 (mar.), 10:00", "es") == []
    assert _l_days("Le phare regarde la mer. Le port est proche.", "fr")[0] == set()
    assert _l_days("Junto al mar.", "es")[0] == set()


def test_a_japanese_day_name_ending_is_not_sunday():
    """The 日 that ends '月曜日・火曜日' is not Sunday."""
    from tools.en_content import _l_days
    assert _l_days("月曜日・火曜日は休みです。", "ja")[0] == {"monday", "tuesday"}


def test_june_in_a_name_is_no_month():
    """2026-11-01 (Jeju en): 'Nam June Paik' (백남준) — 'June' between two capitalized words is a person's name, no 6;
    elsewhere it is still the month (and an added one is caught, as for 'Hotel June has 48 rooms')."""
    from tools.en_content import parity
    assert parity("백남준의 작품을 전시합니다.", "It shows works by Nam June Paik.") == []
    assert parity("백남준아트센터는 6월에 엽니다.", "The Nam June Paik Art Center opens in June.") == []
    assert parity("6월~8월에 엽니다.", "It opens June–August.") == []
    assert parity("6월에 엽니다.", "It opens in June.") == []
    assert parity("엽니다.", "It opens in June.") == ["number 6 not in Korean"]


def test_earl_grey_is_a_name_not_british_spelling():
    """2026-11-01 (Jeju en menu '얼그레이'): Earl Grey is the tea's name; 'grey' alone is still British spelling."""
    from tools.en_content import BRITISH
    assert not BRITISH.search("Earl Grey latte") and BRITISH.search("a grey stone wall")


def test_hour_lists_a_time_before_myeon_and_names_that_look_like_dates():
    """2026-11-01 (Daegu en): '오전 11시면' is 11:00; '19·20·21시' is three hours; 'Gwak Jun' (곽준) and 'Gang Sun-hang'
    (강순항) are names, not June and Sunday — while a month abbreviation next to a number and a weekday word alone still
    count."""
    from tools.en_content import parity
    assert parity("오전 11시면 장이 파했습니다.", "The market closed at 11:00.") == []
    assert parity("야간 19·20·21시에 엽니다.", "It opens at night at 19:00, 20:00, and 21:00.") == []
    assert parity("13·14·17·18시 출발합니다.", "It departs at 13:00, 14:00, 17:00 and 18:00.") == []
    assert parity("곽준의 사당입니다.", "It is the shrine of Gwak Jun.") == []
    assert parity("강순항이 지었습니다.", "It was built by Gang Sun-hang.") == []
    assert parity("6월 5일에 엽니다.", "It opens on Jun 5.") == []
    assert parity("월~금요일 엽니다.", "Open Mon–Fri.") == []
    assert parity("엽니다.", "Open Sun.") == ["weekday Sunday not in Korean"]




def test_a_bare_weekday_range_before_a_particle_is_read():
    """2026-11-01 (Gunsan en '월~목이 쉬는 날'): a bare range followed by 이/가/도/만 is the days, as before 은/는/에."""
    from tools.en_content import parity
    assert parity("월~목이 쉬는 날입니다.", "It is closed Monday to Thursday.") == []
    assert parity("월~목은 쉽니다.", "It is closed Monday to Thursday.") == []
    assert parity("월~목이 쉬는 날입니다.", "It is closed Monday to Friday.") != []
