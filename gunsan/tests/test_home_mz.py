"""The home's five sections in the operator's MZ look (2026-11-02 '일단 반영하자'; present.home_tiles · feed_extra ·
home_post(s), templates/_mz.html.j2, css/81-home-mz.css): words go on a KOGL-1 photo only, a KOGL-3 photo stays whole
with nothing on it, the SNS cards never repeat a photo, and the short photo words come from the place's own data."""
import re
import shutil
from pathlib import Path

from pipeline import present
from pipeline.build import build

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


def ent(name, restdate="", photos=(), area="", fee=""):
    facts = {"restdate": restdate} if restdate else {}
    if fee:
        facts["usefee"] = fee
    return {"name": name, "kind": "attraction", "facts": facts, "_photos": list(photos), "_area": area, "_street": ""}


def test_post_language_comes_from_our_note():
    assert present.post_lang("일본어 계정이 군산 짬뽕 축제를 보러 온 길에 …") == "일본어"
    assert present.post_lang("베트남어로 글을 쓴 계정이 … 영어 자막") == "베트남어"      # the first one named
    assert present.post_lang("철길마을 사진을 올린 게시물입니다.") == ""


def test_off_word_and_feed_words():
    assert present.off_word(ent("가", "매주 월요일")) == "MON OFF"
    assert present.off_word(ent("나", "연중무휴")) == "EVERYDAY"
    assert present.off_word(ent("다", "매주 월요일, 화요일")) == "MON·TUE OFF"
    assert present.off_word(ent("라", "비정기적 휴무")) == ""
    kf = {"slots": [{"key": "fee", "main": "무료", "missing": False, "conflict": False}]}
    w = present.feed_extra(ent("동국사", "연중무휴", area="금광동"), kf, "군산")
    assert w == {"title": "군산 '동국사'", "line": "금광동 / EVERYDAY / 무료", "closed_days": ""}
    w = present.feed_extra(ent("군산근대건축관", "1월 1일, 매주 월요일"), kf, "군산")
    assert w["title"] == "군산근대건축관" and w["closed_days"] == "월" and w["line"] == "MON OFF / 무료"


def test_sns_cards_never_repeat_a_photo():
    p1 = {"url": "u1", "type": 1}
    p3 = {"url": "u3", "type": 3}
    a = ent("대장봉", photos=[p1])
    b = ent("고군산군도", photos=[p3])
    posts = [{"note": "일본어 계정", "_places": [a, b]}, {"note": "", "_places": [a, b]}, {"note": "", "_places": [a]}]
    cards = present.home_posts(posts)
    assert [c["photo"] and c["photo"]["url"] for c in cards] == ["u1", "u3", None]
    assert [c["place"]["name"] for c in cards] == ["대장봉", "고군산군도", "대장봉"]   # the third names its place in words
    assert cards[0]["lang"] == "일본어"


def test_home_sections_keep_words_off_kogl3_photos(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    out = tmp_path / "out"
    build(data, out, "sample")
    home = (out / "index.html").read_text("utf-8")
    for m in re.finditer(r'<figure class="fp-ph t3">(.*?)</figure>', home, re.S):
        assert "fp-cap" not in m.group(1) and "fp-badge" not in m.group(1)
    for m in re.finditer(r'<div class="fp-ph t(\d)">', home):
        assert m.group(1) == "1"                                  # words on the photo: KOGL-1 only
    assert 'class="blz-ph t3"' not in home                         # the lead post's photo is KOGL-1
    for tile in re.findall(r'<a class="mzt mzt-photo".*?</a>', home, re.S):
        assert 'data-kogl="1"' in tile
    if 'class="gtab-bar"' in home:
        assert home.count('role="tabpanel"') == home.count('role="tab" ')
