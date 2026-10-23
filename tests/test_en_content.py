"""tools/en_content.py for English: Revised Romanization, English addresses (with the city's configuration:
tests/fixtures/gunsan_subset/site.json), EngService2 matching, the rules a batch carries and the parity check."""
import json
from pathlib import Path

from pipeline.city import of as city_of
from tools import en_content as C
from tools.en_content import CONFLICT_NOTE, address_en, address_rule, check, match_en, parity, romanize, style

ROOT = Path(__file__).resolve().parent.parent
SUBSET_CITY = city_of(json.loads((ROOT / "tests" / "fixtures" / "gunsan_subset" / "site.json").read_text("utf-8")))
DAEGU_CITY = city_of(json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8")))

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
    city = SUBSET_CITY   # the fixture city's site.json: its 시, 시·도 and their English names
    assert address_en("전라북도 군산시 월명공원1길 26", city) == "26 Wolmyeonggongwon 1-gil, Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 백토로 284-22 (나운동)", city) == \
        "284-22 Baekto-ro (Naun-dong), Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 옥도면 선유도리 474-1", city) == \
        "474-1 Seonyudo-ri, Okdo-myeon, Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 수송안7길 36 청담횟집", city) == ""   # a business name: the translator writes it


def test_the_address_rule_ends_with_the_city_s_own_english_names():
    """The batches' address rule (every language) names this city's English tail from site.json, never a fixed one."""
    assert address_rule(SUBSET_CITY).endswith("'<number> <Road>, <eup/myeon/dong>, Gunsan-si, Jeonbuk State' with "
                                              "Revised Romanization and every digit kept.")
    assert "'<number> <Road>, <eup/myeon/dong>, <gu/gun>, Daegu'" in address_rule(DAEGU_CITY)
    assert C.rules(DAEGU_CITY)["address"] == address_rule(DAEGU_CITY)
    assert "Daegu" in C.rules_for("ja", DAEGU_CITY)["address"]


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


def test_promotional_word_inside_a_place_name_is_a_name(tmp_path, monkeypatch):
    """An English place name of the run's data folder (--data: en/names.json) is a name, not promotion."""
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "names.json").write_text(json.dumps({"p": {"name_en": "Best Western Hanbit Hotel"}}), "utf-8")
    monkeypatch.setattr(C, "DATA", tmp_path)
    monkeypatch.setattr(C, "_NAMED", None)
    assert style("Best Western Hanbit Hotel has 80 rooms.") == []
    assert any("promotional" in x for x in style("It is the best hotel in Hanbit."))


def test_hours_followed_by_copula_or_particle_are_times():
    assert parity("체크인은 15시이고 체크아웃은 11시입니다", "Check-in is 15:00 and check-out is 11:00.") == []
    assert parity("체크아웃은 12시가 많습니다", "Check-out is usually 12:00.") == []
    assert parity("3시간 걸립니다", "It takes 3 hours.") == []          # 시간 (hours) is not a clock time


def test_programme_title_hour_is_not_a_clock_time():
    assert parity("방송사 채널 영상: 6시 내고향 — 만남스넥", "Broadcaster channel video: 6si Nae Gohyang — Mannam Snack") == []
    assert "number 6 missing" in parity("6시 내고향", "Nae Gohyang")


def test_a_lone_candidate_must_also_name_the_place_and_nested_korean_brackets_go():
    """Review 2026-10-16 (a dense city centre): the one item of the type within 150m is often the place next door; a
    Latin title stands alone only when its Korean part is one of the place's names or it holds the romanized name."""
    from tools.en_content import name_evidence, strip_ko_brackets
    place = {"name": "산호찜갈비", "kind": "food", "geo": {"lat": 35.87, "lng": 128.60}, "tourapi": {"contenttypeid": "39"}}
    door = {"contentid": "1", "contenttypeid": "82", "title": "Bongsan Jjimgalbi", "mapy": "35.8701", "mapx": "128.60"}
    assert match_en(place, [door])[0] is None and match_en(place, [door])[2] == "weak"
    temple = {"name": "부인사", "kind": "attraction", "geo": {"lat": 35.9, "lng": 128.7}, "tourapi": {"contenttypeid": "12"}}
    assert name_evidence(temple, {"title": "Buinsa Temple (Daegu) (부인사)"})
    assert name_evidence({"name": "MRNW"}, {"title": "MRNW Miraenongwon (MRNW)"})
    assert not name_evidence({"name": "강정고령보"}, {"title": "The ARC Communication Space"})
    assert strip_ko_brackets("Kim Kwangseok-gil Street (김광석 길 (김광석다시그리기길))") == "Kim Kwangseok-gil Street"
    assert strip_ko_brackets("Dodongseowon Confucian Academy [UNESCO World Heritage]") == "Dodongseowon Confucian Academy"
    assert strip_ko_brackets("Daegu Concert House (Formerly Daegu Citizens' Hall)") == \
        "Daegu Concert House (Formerly Daegu Citizens' Hall)"


def test_guideline_names_take_the_city_words_from_site_json():
    from tools import en_names
    en_names.use_city_words({"한빛": "Hanbit"})
    assert en_names.business_name("한빛콘서트하우스") == "Hanbit Concert House"
    assert en_names.public_name("한빛시장", "") == "Hanbit Market"
    en_names.use_city_words({})
    assert "한빛" not in en_names.WORDS


def test_the_official_english_address_is_used_only_when_it_states_our_address():
    """Review 2026-10-16: the English service's address of a matched item can be another address of the place (a road
    address for our lot address), lose the '2가' bracket, or name the 도 the place's 군 left; then ours is romanized."""
    from pipeline.en_source import official_address
    assert official_address("80, Dongseong-ro 2-gil, Jung-gu, Daegu", "대구광역시 중구 동성로2길 80 (공평동)", DAEGU_CITY) \
        == "80, Dongseong-ro 2-gil, Jung-gu, Daegu"
    assert official_address("180, Universiad-ro, Suseong-gu, Daegu", "대구 수성구 노변동 650", DAEGU_CITY) == ""
    assert official_address("10 Seoseong-ro, Jung-gu, Daegu", "대구광역시 중구 서성로 10 (계산동2가)", DAEGU_CITY) == ""
    assert official_address("24, Namsan 4-gil, Gunwi-gun, Gyeongsangbuk-do", "대구광역시 군위군 부계면 남산4길 24",
                            DAEGU_CITY) == ""


def test_won_starting_a_word_is_not_money():
    """'56-1 원조현풍할매집곰탕' (a shop's name in an address) is not '1 won'; '1,000원이며' is."""
    assert parity("현풍중앙로 56-1 원조현풍할매집곰탕", "56-1 Hyeonpungjungang-ro (Wonjo Hyeonpung Halmaejip Gomtang)") == []
    assert parity("입장료 1,000원이며", "Admission is 1,000 won.") == []
    assert parity("입장료 1,000원이며", "Admission is 1,000.")


def test_a_course_name_in_latin_letters_is_not_promotion(tmp_path, monkeypatch):
    """'대구 Best of Best' (a course of the city's tourism site) is named so; 'best' elsewhere is still promotion."""
    import tools.en_content as C
    data = tmp_path / "data"
    data.mkdir()
    (data / "courses.json").write_text(json.dumps([{"name": "한빛 Best of Best"}], ensure_ascii=False), "utf-8")
    monkeypatch.setattr(C, "DATA", data)
    monkeypatch.setattr(C, "_NAMED", None)
    assert not any("promotional" in x for x in C.style("Hanbit Best of Best links six stops."))
    assert any("promotional" in x for x in C.style("It is the best view."))
    monkeypatch.setattr(C, "_NAMED", None)


def test_the_il_that_ends_a_word_is_not_sunday():
    """'평일·토요일·공휴일' names Saturday only (평일 and 공휴일 are not weekdays); '토·일요일' names both."""
    from tools.en_content import _ko_days
    assert _ko_days("평일·토요일·공휴일 09:00~18:00")[0] == {"saturday"}
    assert _ko_days("토·일요일")[0] == {"saturday", "sunday"}
