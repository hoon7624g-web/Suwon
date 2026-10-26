"""pipeline/intl_check.py: a Korean word written by its sound in place of a translation is found; a real word of
the language or a proper noun is not."""
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
    assert not translit("남원천 일원", "Namwoncheon Stream area", "en", proper={"남원천"})
