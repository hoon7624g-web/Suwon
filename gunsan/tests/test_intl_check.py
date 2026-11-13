"""pipeline/intl_check.py and tools/intl_table.py (the translation-table method, ported 2026-11-01 from the other
engines): a Korean word written by its sound in place of a translation is found, a real word of the language or a
proper noun is not; the table's units are cut and masked as the checker reads them; every kind this engine's prepare
writes (columns too) is built from the table in the shape en_content check reads and merge stores."""
from pathlib import Path

from pipeline import locales as LC
from pipeline.intl_check import translit
from pipeline.locales import kontsevich


def test_sound_copies_are_found_in_each_script():
    assert translit("무료 공영주차장 이용 가능", "Free Gongyeong Juchajang Iyong Available", "en")
    assert translit("탐방로 입산 시간", "タムバンロ イプサン時間", "ja")
    assert translit("연중무휴", f"Режим: {kontsevich('연중무휴')}", "ru")
    assert not translit("무료 공영주차장 이용 가능", "Free public parking available", "en")


def test_words_of_the_language_and_proper_nouns_are_not_sound_copies():
    # 라고 (a quoting ending) inside the French 'ragoût', and a place name kept by its sound on purpose
    assert not translit("“맛이 난다”라고 말하고 있다", "le gamjatang (ragoût d'os de porc)", "fr")
    assert not translit("은파천 일원", "Eunpacheon Stream area", "en", proper={"은파천"})


def test_a_loanword_of_the_same_origin_is_no_sound_copy():
    """Gunsan 2026-11-01 (Japanese lint): 크리스마스, 온라인, 테라스 are words Korean took from English; Japanese writes
    its own loanword (クリスマス, オンライン, テラス), which sounds alike — while a Korean word written in katakana is
    still a sound copy."""
    assert not translit("크리스마스 시즌 온라인 예약, 테라스 좌석", "クリスマスシーズンのオンライン予約、テラス席", "ja")
    assert translit("박대 정식", "パクテ定食", "ja")


def test_an_administrative_ending_is_not_joined_to_the_next_word():
    """2026-10-31 (the other engine): '… in Ganghwa-gun in the …' — '-gun' + 'in' is no 'gunin' (군인), while a
    soldier written by sound still is."""
    ko = "어린이·청소년·군인 900원, 강화군 역사 유적 54곳"
    assert not translit(ko, "children, youth and military 900 won; 54 historic sites in Ganghwa-gun in the list", "en")
    assert translit(ko, "children, youth and gunin 900 won", "en")


def test_a_road_with_its_number_inside_is_romanized_by_rule():
    """2026-11-01 (Gunsan's '구영6길 125-1', '나운5길에'): a road name with its number inside is an address word written
    by the romanization rule, not a sound copy — the same word outside a road still is."""
    assert not translit("구영6길 125-1로 들어서면 카페가 나타납니다", "Turn into 125-1 Guyeong 6-gil and you find the cafe", "en")
    assert not translit("나운5길에 산마루가 있습니다", "Sanmaru is on Naun 5-gil", "en", proper={"산마루"})
    assert translit("구영 마을 앞에 있습니다", "It is in front of Guyeong village", "en")


def test_a_number_without_hangul_takes_the_languages_marks():
    """2026-10-31 (the other engine, '1,260.8㎡'): a value with no Korean word is copied, but its number is written as
    the language writes numbers — a German '1,260.8' would read as 1.26 — and a date or a range is left as it is."""
    from tools.intl_table import norm_plain
    assert norm_plain("1,260.8㎡", LC.get("de")) == "1.260,8㎡"
    assert norm_plain("1,260.8㎡", LC.get("fr")) == f"1{LC.get('fr').grp}260,8㎡"   # this engine: a narrow no-break space
    assert norm_plain("1,260.8㎡", LC.get("ja")) == norm_plain("1,260.8㎡") == "1,260.8㎡"
    assert norm_plain("2026.10.31 / 10:00~18:00", LC.get("de")) == "2026.10.31 / 10:00–18:00"


def test_a_russian_word_that_only_starts_with_the_sound_is_not_a_copy():
    """2026-10-31 (the other engine): 번에 (in '한 번에') sounds 'поне', the start of 'понедельник' (Monday) — not a
    sound copy; a word that is the sound with a case ending still is."""
    assert not translit("한 번에 즐길 수 있습니다", "Работает в понедельник", "ru")
    assert translit("연중무휴", f"Режим: {kontsevich('연중무휴')}а", "ru")


def test_a_clock_time_after_its_word_of_the_day_is_masked_as_24_hours():
    """'체크인은 오후 4:00 이후': the checker reads '오후 4:00' as 16:00 (en_content._times_ko), so the table's unit is
    '{t1} 이후' with t1 = 16:00 — a unit '오후 {t1}' with 04:00 would put 04:00 back into every translation."""
    from tools.en_content import parity
    from tools.intl_table import Masker
    unit, slots = Masker([], []).mask("체크인은 오후 4:00 이후, 체크아웃은 오후 12:00 전까지, 10:00~22:00 영업")
    assert unit == "체크인은 {t1} 이후, 체크아웃은 {t2} 전까지, {t3}~{t4} 영업"
    assert [v for _, v in slots.values()] == ["16:00", "12:00", "10:00", "22:00"]
    assert parity("체크인은 오후 4:00 이후입니다.", "Check-in is after 16:00.") == []
    assert parity("체크인은 오후 4:00 이후입니다.", "Check-in is after 04:00.") != []


def test_lint_sample_names_carry_no_digits():
    """A placeholder's sample name ends in letters: 'Zq1만' would read as 10,000 and '{m2}2길' as the number 22
    (Gunsan 2026-11-01: 1 in 4 of English lint's parity findings were that)."""
    from tools.intl_table import _sample
    ko, tr = _sample("{m1}만 {t1}에 닫고 {m2}2길에 있습니다.", "Only {m1} closes at {t1}; it is on {m2} 2-gil.", "en")
    assert "Zqa만" in ko and "Zqb2길" in ko and "Zqa" in tr
    from tools.en_content import parity
    assert parity(ko, tr) == []


def _bare_version(code: str, units: dict, names: dict | None = None):
    """A tools/intl_table.Version without its data folder (no prepare): the table and the name lookups only."""
    from tools import intl_table as IT
    v = object.__new__(IT.Version)
    v.data, v.code, v.work = Path("."), code, Path(".")
    v.loc = LC.get(code) if code != "en" else None
    v.table = {"units": dict(units), "names": dict(names or {}), "proper": []}
    v.en_table = v.table
    v.missing, v.findings, v.used, v.proper, v.place_names = {}, [], set(), set(), {}
    return v


COLUMN = {"id": "column-test", "slug": "test-column", "category": "역사·건축 해설", "label": "근대건축",
          "title": "붉은 벽돌의 항구", "dek": "항구를 걸으며 건물을 봅니다.",
          "summary": "세관 본관은 1908년에 지었습니다. 관람료는 무료입니다.", "pull_quote": "항구는 지금도 걷는 속도를 정합니다.",
          "body": [{"heading": "세관에서 시작합니다", "paras": ["세관 본관은 1908년에 지었습니다.", "월요일에 쉽니다."]}],
          "items": [{"place_slug": "old-customs", "place_name": "구 군산세관", "place_name_en": "", "reason": "월요일에 쉽니다."}],
          "sources": [{"name": "군산시 문화관광", "url": "https://example.invalid/tour"}], "mentions": [],
          "ko_hash": "0123456789abcdef"}
EN_UNITS = {"역사·건축 해설": "History and architecture", "근대건축": "Modern architecture",
            "붉은 벽돌의 항구": "A port of red brick", "항구를 걸으며 건물을 봅니다.": "A walk past the port's buildings.",
            "세관 본관은 1908년에 지었습니다.": "The customs house main building was built in 1908.",
            "관람료는 무료입니다.": "Admission is free.", "항구는 지금도 걷는 속도를 정합니다.": "The port still sets the pace of a walk.",
            "세관에서 시작합니다": "Starting at the customs house", "월요일에 쉽니다.": "It is closed on Mondays.",
            "군산시 문화관광": "Gunsan Culture and Tourism"}


def test_a_column_is_built_from_the_table_paragraph_for_paragraph():
    """Gunsan's prepare writes columns (en_source.column_item): apply builds them from the table — every section's
    paragraphs one for one, each cut into sentences — in the shape en_content check_column reads and merge stores
    (_column_record keeps the Korean slug, place slugs, source addresses and ko_hash); a unit the table lacks is
    listed, never left out or romanized."""
    from tools import en_content as ec
    v = _bare_version("en", EN_UNITS)
    out = v.column(COLUMN)
    assert v.missing == {} and v.findings == []
    assert out["body"][0]["paras"] == ["The customs house main building was built in 1908.", "It is closed on Mondays."]
    assert out["summary"] == "The customs house main building was built in 1908. Admission is free."
    assert ec.check_column(out, COLUMN) == []
    rec = ec._column_record(out, COLUMN, "2026-11-01", ec.squash_ws)
    assert rec["slug"] == "test-column" and rec["items"] == [{"place_slug": "old-customs", "reason": "It is closed on Mondays."}]
    assert rec["sources"] == [{"name": "Gunsan Culture and Tourism", "url": "https://example.invalid/tour"}]
    assert rec["ko_hash"] == COLUMN["ko_hash"]
    v = _bare_version("en", {k: x for k, x in EN_UNITS.items() if k != "관람료는 무료입니다."})
    v.column(COLUMN)
    assert [m["ko"] for m in v.missing.values()] == ["관람료는 무료입니다."]


def test_a_place_keeps_its_other_sources_values_as_merge_stores_them():
    """Gunsan shows one value a fact (site.json fact_conflicts 'primary'), but its versions' files keep the other
    sources' values (en_site.Site drops them on the page): a place built from the table carries its alternatives and
    'also' values and the conflict note, and merge stores each with its provider."""
    from tools import en_content as ec
    item = {"id": "p1", "slug": "p-one", "kind": "attraction", "name": "은파호수공원", "name_en": "Eunpa Lake Park",
            "name_en_source": "TourAPI EngService2", "alternate_names": [], "mentions": [], "ko_hash": "f" * 16,
            "summary": "", "details": [], "faq": [],
            "facts": [{"key": "usetime", "label": "이용시간", "value": "09:00~18:00",
                       "alternatives": [{"value": "10:00~17:00", "provider": "한국관광공사"}]},
                      {"key": "parking", "label": "주차", "value": "가능",
                       "also": [{"value": "공영주차장 이용", "provider": "군산시"}]}]}
    v = _bare_version("en", {"가능": "Available", "공영주차장 이용": "Use the public parking lot"})
    out = v.place(item)
    assert v.missing == {}
    usetime, parking = out["facts"]
    assert usetime == {"key": "usetime", "value": "09:00–18:00", "alternatives": [{"value": "10:00–17:00"}],
                       "note": ec.CONFLICT_NOTE}
    assert parking["also"] == [{"value": "Use the public parking lot"}]
    rec = ec._merge_place(out, item, "2026-11-01", {})
    assert rec["facts"]["usetime"]["alternatives"] == [{"value": "10:00–17:00", "provider": "한국관광공사"}]
    assert rec["facts"]["parking"]["also"] == [{"value": "Use the public parking lot", "provider": "군산시"}]


def test_an_area_name_of_the_table_is_no_sound_copy(tmp_path):
    """2026-11-01 (Gangneung ja): 'サチョン面のカンヌン…' — サチョン面 is the table's name of the area 사천면, which sounds
    like 사정 in the record's Korean ('펜션 사정 및 날씨로'); the report masks the table's names like the place names, while
    the same sound outside a name is still found."""
    import json
    from pipeline.intl_check import mask_names, names_of_version
    (tmp_path / "ja").mkdir()
    (tmp_path / "ja" / "places.json").write_text(json.dumps({"p1": {"name_ja": "カンヌン バダ"}}), "utf-8")
    names = names_of_version(tmp_path, "ja", {"units": {}, "names": {"사천면": "サチョン面"}, "proper": []})
    assert names == ["カンヌン バダ", "サチョン面"]
    ko = "사천면 펜션은 사정 및 날씨로 쉴 수 있습니다"
    text = "サチョン面のカンヌン バダは、天候により休むことがあります。"
    assert translit(ko, text, "ja") and not translit(ko, mask_names(text, names), "ja")
    assert translit(ko, mask_names("サチョンにより休みます。", names), "ja")


def test_a_word_only_in_an_untranslated_field_is_no_sound_copy():
    """2026-11-01 (Gangneung ru): 'подают' (they serve) starts with the sound of 보다, which the record has only in its
    TourAPI overview (never published), and 'нарезки' with that of 날에, only in a guide's count query — the report reads
    the Korean the version translates; a word of the summary is still read."""
    from pipeline.intl_check import source_text
    place = {"summary": "회와 매운탕을 냅니다.", "tourapi": {"overview": "보다 좋은 가격에"}}
    guide = {"title": "막국수", "counts": [{"what": "쉬는 날에 월요일이 없는 음식점"}]}
    assert "보다" not in source_text(place) and "날에" not in source_text(guide)
    # (a word written by the sound of 보다 itself; 'подают' is a Russian verb, never counted — Daegu 2026-11-02)
    assert translit(" ".join([place["summary"], place["tourapi"]["overview"]]), "Здесь пода и сырая рыба.", "ru")
    assert not translit(source_text(place), "Здесь пода и сырая рыба.", "ru")
    assert not translit(" ".join([place["summary"], place["tourapi"]["overview"]]), "Здесь подают сырую рыбу.", "ru")
    assert not translit(source_text(guide), "Лапша ручной нарезки.", "ru")
    assert "매운탕" in source_text(place)


def test_a_name_at_the_start_of_an_addresss_road_stays_the_roads_own_name():
    """2026-11-01 (Jeju '제주시 우도면 우도로 153'): 우도 (the record's name) at the start of the road 우도로 is the road's
    own name — masked, '{name}로 153' would read 'Udo Island-ro 153'; the name before a particle ('우도로 가는 배') is
    still masked."""
    from tools.intl_table import Masker
    m = Masker(["우도"], ["우도면"])
    assert m.mask("제주특별자치도 제주시 우도면 우도로 153")[0] == "제주특별자치도 제주시 {m1} 우도로 153"
    assert m.mask("우도로 가는 배는 우도면에서 내립니다.")[0] == "{name}로 가는 배는 {m1}에서 내립니다."
    assert Masker(["파계사"], ["달성군"]).mask("달성군 파계사길 127, 파계사에 딸린 암자입니다.")[0] == \
        "{m1} 파계사길 127, {name}에 딸린 암자입니다."
    # a place name inside a longer word: 멸고국수 (a dish) holds the restaurant name 고국수, 강릉통일공원 the name 통일공원
    assert Masker(["통일공원"], ["고국수"]).mask("메뉴는 멸고국수이고, 문의는 강릉통일공원 안보전시관입니다. 고국수 옆입니다.")[0] == \
        "메뉴는 멸고국수이고, 문의는 강릉통일공원 안보전시관입니다. {m1} 옆입니다."


def test_the_word_of_a_lot_number_is_part_of_the_address():
    """2026-11-01 (Jeju event address '서귀포시 하효동 999번지선'): the word after a lot number is romanized by rule like
    the rest of the address ('999beonji-seon'); a sound copy elsewhere in the text is still found."""
    ko = "축제는 하효동 999번지선 일대에서 열립니다. 주차장이 있습니다."
    assert not translit(ko, "999beonji-seon, Hahyo-dong", "en")
    assert translit(ko, "999beonji-seon, Hahyo-dong; juchajang available", "en")


def test_a_latin_word_joined_to_chinese_characters_is_still_found():
    """2026-11-01 (Jeju zh-hans 'Ttaksaeu虾'): a Korean word written by its sound right before or after Chinese
    characters is a sound copy as much as one between spaces; a real Latin name joined to them is not."""
    assert translit("딱새우 회를 냅니다.", "供应Ttaksaeu虾生鱼片。", "zh-hans")
    assert not translit("딱새우 회를 냅니다.", "供应硬壳虾生鱼片。", "zh-hans")
    assert not translit("에펠탑 모형이 있습니다.", "有Eiffel塔的模型。", "zh-hans")




def test_foreign_words_that_sound_like_themselves_are_no_sound_copies():
    """2026-11-01 (translators of five sites): 'yoga', 'robot', 'tiramisu', 'salsa' are the languages' own words for
    요가, 로봇, 티라미수, 살사 — no Korean word written by its sound; a Korean word so written still is."""
    assert not translit("요가 수업과 로봇 체험이 있습니다.", "Hay clases de yoga y una experiencia con robots.", "es")
    assert not translit("티라미수와 살사 소스", "Tiramisu und Salsa", "de")
    assert translit("요가 수업과 주차장이 있습니다.", "Yoga class and juchajang", "en")


def test_model_is_the_english_word_korean_took():
    """Gunsan 2026-11-02 (en strings row of the about page): '모델 학습' is 'model training' — 모델 is English 'model',
    not a Korean word written by its sound; a Korean word beside it so written still is."""
    assert not translit("모델 학습 전용 수집기는 robots.txt로 제한합니다.",
                        "Crawlers used only for model training are limited through robots.txt.", "en")
    assert not translit("모델 학습", "モデルの学習", "ja")
    assert translit("모델 학습 전용 수집기", "Model hakseup crawlers", "en")




def test_a_name_that_opens_a_sentence_starts_with_a_capital():
    """2026-11-01 (Jeju es/ru: 'playa de Sehwa, en …', 'водопад Соджонбан — …'): the names table writes a generic word
    in lowercase for the middle of a sentence; at the start of a sentence or a line the name is capitalized."""
    from tools.intl_table import sentence_start
    assert sentence_start("", "playa de Sehwa") == "Playa de Sehwa"
    assert sentence_start("Es gratis. ", "водопад Соджонбан") == "Водопад Соджонбан"
    assert sentence_start("Se llega desde la ", "playa de Sehwa") == "playa de Sehwa"
    assert sentence_start("a\n", "parc Tongil") == "Parc Tongil"




def test_a_web_address_is_no_sound_copy():
    """2026-11-01 (Daegu zh-hant): 'https://yeyak.dssiseol.or.kr' holds the sound of 예약 but is an address to copy."""
    ko = "예약은 누리집에서 합니다."
    assert not translit(ko, "请在网站预订：https://yeyak.dssiseol.or.kr", "zh-hans")
    assert translit(ko, "Yeyak online", "en")




def test_a_bare_domain_is_no_sound_copy():
    """2026-11-01 (Daegu zh-hans 'yeyak.daegu.go.kr'): a domain written without https:// is an address too."""
    assert not translit("예약은 누리집에서 합니다.", "请在yeyak.daegu.go.kr预订。", "zh-hans")
    assert translit("예약은 누리집에서 합니다.", "Yeyak online", "en")


def test_a_number_inside_a_name_is_no_fact_of_the_text():
    """Gunsan zh-hant, zh-hans, ja 2026-11-01: a version writes a place by its official name in the language, which may
    lack the number of the Korean name ('구 일본 제18은행 군산지점' is zh '群山近代美術館') or carry one the Korean alternate
    name lacks ('군산근대미술관' is ja '旧日本第18銀行群山支店'); a number inside such a name is no fact the translation
    drops or adds. Any other number is still checked."""
    from tools.en_content import LangCheck
    pairs = (("구 일본 제18은행 군산지점", "群山近代美術館"),)
    ko, zh = "구 일본 제18은행 군산지점은 어떤 은행이었나요?", "群山近代美術館是什麼樣的銀行？"
    assert any("18" in x for x in LangCheck("zh-hant").pair("q", ko, zh))
    assert LangCheck("zh-hant", (), pairs).pair("q", ko, zh) == []
    # the text spells the Korean name out beside the official one: its 18 is the name's
    assert LangCheck("zh-hant", (), pairs).pair(
        "h", "군산근대미술관(구 일본 제18은행 군산지점) 관람료", "群山近代美術館（舊日本第18銀行群山分行）門票") == []
    # two Korean names, one Japanese name: '{name}({name})' -> '群山近代美術館（{name}）'
    ja = (("구 일본 제18은행 군산지점", "旧日本第18銀行群山支店"), ("군산근대미술관", "旧日本第18銀行群山支店"))
    assert LangCheck("ja", (), ja).pair("h", "군산근대미술관(구 일본 제18은행 군산지점) 관람료",
                                        "群山近代美術館（旧日本第18銀行群山支店）の観覧料") == []
    assert LangCheck("ja", (), ja).pair("t", "군산근대미술관 통합권", "旧日本第18銀行群山支店の統合券") == []
    # a number outside the names is still a fact
    assert any("2008" in x for x in LangCheck("zh-hant", (), pairs).pair(
        "t", "구 일본 제18은행 군산지점은 2008년에 지정됐습니다.", "群山近代美術館已列入文化遺產。"))


def test_a_value_without_hangul_takes_full_width_brackets_around_a_cjk_name():
    """Gunsan zh-hant 2026-11-01: '063-451-2138(군산문화원)' masks to '{p1}({m1})', a unit with no Hangul that apply
    writes as the value itself; around the Chinese name its brackets are the full-width ones."""
    from tools.intl_table import Masker
    v = _bare_version("zh-hant", {}, {"군산문화원": "群山文化院"})
    assert v.translate("063-451-2138(군산문화원)", "text", Masker([], ["군산문화원"]), "events/x.tel") == \
        "063-451-2138（群山文化院）"
    v = _bare_version("de", {}, {"군산문화원": "Kulturzentrum Gunsan"})
    assert v.translate("063-451-2138(군산문화원)", "text", Masker([], ["군산문화원"]), "events/x.tel") == \
        "063-451-2138(Kulturzentrum Gunsan)"


def test_a_japanese_road_with_its_number_and_a_shared_loanword_are_no_sound_copies():
    """Gunsan ja report 2026-11-01: 'キョンチョン4ギル14' is the road 경촌4길 written by rule, not the sound of 견종 (the
    record's pet notes, same katakana); タオル is Japanese for 수건 and of the same origin as 타올. A word written by its
    sound outside a road is still found."""
    assert translit("견종은 소형견만 됩니다. 주소는 경촌4길 14입니다.", "小型犬のみ可。住所はキョンチョン4ギル14です。", "ja") == []
    assert translit("침구·타올 제공", "寝具・タオルあり", "ja") == []
    assert translit("견종은 소형견만 됩니다.", "キョンチョンは小型犬のみです。", "ja") == [("견종", "キョンチョン")]


def test_two_korean_names_the_version_writes_alike_are_written_once():
    """Gunsan zh-hant 2026-11-01: '군산근대미술관(구 일본 제18은행 군산지점)' names one place twice; in Chinese both are
    '群山近代美術館', so the version writes it once (not '群山近代美術館（群山近代美術館）'). Two different names stay."""
    import re
    from tools.intl_table import Masker
    ko = "군산근대미술관(구 일본 제18은행 군산지점) 관람료"
    m = Masker([], ["군산근대미술관", "구 일본 제18은행 군산지점"])
    unit, _ = m.mask(ko)
    assert len(set(re.findall(r"\{m\d+\}", unit))) == 2
    tr = unit.replace(" 관람료", "門票").replace("(", "（").replace(")", "）")
    v = _bare_version("zh-hant", {unit: tr}, {"군산근대미술관": "群山近代美術館", "구 일본 제18은행 군산지점": "群山近代美術館"})
    assert v.translate(ko, "text", m, "x") == "群山近代美術館門票"
    v = _bare_version("zh-hant", {unit: tr}, {"군산근대미술관": "群山近代美術館", "구 일본 제18은행 군산지점": "舊日本第18銀行群山分行"})
    assert v.translate(ko, "text", m, "x") == "群山近代美術館（舊日本第18銀行群山分行）門票"


def test_a_latin_word_the_korean_writes_is_no_sound_copy():
    """Gunsan zh-hans report 2026-11-01: '국토교통부 TAGO 국내항공운항정보' keeps the system name TAGO in Latin letters; it is
    not the sound of the verb 타고 ('출입구에서 타고') of the same record. A 타고 written by its sound is still found."""
    ko = "국토교통부 TAGO 국내항공운항정보를 봅니다. 출입구에서 타고 내립니다."
    assert translit(ko, "查看国土交通部TAGO国内航班运行信息。在出入口上下车。", "zh-hans") == []
    assert translit("출입구에서 타고 내립니다.", "在出入口tago下车。", "zh-hans") == [("타고", "tago")]
    # the copied word breaks the run: 'No place in' (place in the Korean) is no 'noin' of 놓인 (Gunsan en 2026-11-01)
    assert translit("place 목록에 놓인 곳은 없습니다.", "No place in the list.", "en") == []


def test_a_word_of_the_language_that_sounds_korean_is_no_sound_copy():
    """Gunsan es 2026-11-01: Spanish 'olla' (pot) in 'olla caliente de marisco' is not 올라 of '올라 있으며'. In English,
    'olla' would still be the sound of 올라."""
    ko = "해물전골이 메뉴에 올라 있으며 2인분부터 주문합니다."
    assert translit(ko, "En la carta figura la olla caliente de marisco, desde dos raciones.", "es") == []
    assert translit(ko, "The seafood hot pot is olla on the menu.", "en") == [("올라", "olla")]



def test_a_russian_word_is_a_sound_copy_only_with_a_case_ending():
    """Daegu ru report 2026-11-02: 'подают' (they serve) starts with 'пода' (보다) but its 'ют' is a verb's ending, as
    'погоды' (보고 'пого'), 'через' (제례 'чере'), 'катков' (같고 'катко') are Russian words; a sound copy with a noun's
    case ending is still found."""
    assert not translit("안심식당 현황보다 새로 낸 곳", "Здесь подают обеды.", "ru")
    assert not translit("날씨를 보고 정합니다. 제례를 엽니다.", "В зависимости от погоды. Проходит через парк.", "ru")
    assert translit("연중무휴", f"Режим: {kontsevich('연중무휴')}ом", "ru")


def test_french_seul_and_juin_are_french_words():
    """Gunsan fr 2026-11-02: 'seul' (alone) is not the sound of 세울, 'juin' (June) not that of 주인."""
    assert translit("주인이 세울 계획입니다.", "Le seul bâtiment, construit en juin 1908.", "fr") == []
    assert translit("주인이 세울 계획입니다.", "Le seul bâtiment, construit en juin 1908.", "en") != []



def test_an_administrative_ending_left_alone_by_a_masked_name_is_dropped():
    """Daegu de report 2026-11-02: masking the name Dalseong leaves '13 in  -gun, 10 in Dong-gu' — the bare '-gun' and
    the next 'in' are no 'gunin' (군인). A 군인 written by its sound is still found."""
    assert translit("군인 13명", "13 in  -gun, 10 in Dong-gu", "de") == []
    assert translit("군인 13명", "13 gunin", "de") == [("군인", "gunin")]
