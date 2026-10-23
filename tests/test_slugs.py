"""ASCII URL slugs (pipeline.slugs) and Revised Romanization (pipeline.romanize): the rules of design 2.1–2.2."""
import ast
import json
import sys
from pathlib import Path

import pytest

from pipeline import city as citymod
from pipeline.en_site import en_slug
from pipeline.romanize import romanize
from pipeline.slugs import (SLUG_MAX_LEN, SLUG_RE, anchor_id, ascii_core, assign_slugs, fallback_slug, initial_id,
                            is_slug, series_slug, slugify, topic_slug)

ROOT = Path(__file__).resolve().parent.parent
METRO = ROOT / "tests" / "fixtures" / "metro"


# ---------------------------------------------------------------- slugify (design 2.2 table)
@pytest.mark.parametrize("name, admin, want", [
    ("서문시장", (), "seomunsijang"),
    ("서문 시장", (), "seomun-sijang"),
    ("경암동 철길마을", {"경암동"}, "gyeongam-dong-cheolgilmaeul"),
    ("83타워", (), "83-tawo"),
    ("카페 온", (), "kape-on"),
    ("E-World(이월드)", (), "e-world"),
    ("[샘플] 군산 행사 A", (), "gunsan-haengsa-a"),
    ("바다 게스트하우스", (), "bada-geseuteuhauseu"),
    ("大邱", (), ""),
])
def test_slugify_design_table(name, admin, want):
    assert slugify(name, admin_words=admin) == want


def test_slug_mode_hyphenates_only_the_named_administrative_words():
    # without admin words the guess of the English pages is off: '-myeon' is not read into a word ending in 면
    assert slugify("경암동 철길마을") == "gyeongamdong-cheolgilmaeul"
    assert slugify("다니면") == "danimyeon" and slugify("평양냉면") == "pyeongyangnaengmyeon"
    assert romanize("다니면") == "Dani-myeon"                        # the English pages keep their heuristic
    # 구·군, 읍·면, a 법정동 'N가' (whose 동 is named too) and '로N가'
    assert slugify("중구", admin_words={"중구"}) == "jung-gu"
    assert slugify("삼덕동1가 카페", admin_words={"삼덕동1가"}) == "samdeok-dong-1-ga-kape"
    assert slugify("삼덕동 카페", admin_words={"삼덕동1가"}) == "samdeok-dong-kape"
    assert slugify("동성로2가", admin_words={"동성로2가"}) == "dongseong-ro-2-ga"
    assert slugify("화원읍 장터", admin_words={"화원읍", "달성군"}) == "hwawon-eup-jangteo"
    assert slugify("") == "" and slugify(None) == ""


def test_slugs_are_ascii_and_at_most_60_characters_cut_at_a_word():
    long_words = " ".join(["가나다라"] * 12)
    s = slugify(long_words)
    assert len(s) <= SLUG_MAX_LEN and SLUG_RE.match(s) and not s.endswith("-")
    assert s == "-".join(["ganadara"] * 6)                               # 53 characters, the 7th word does not fit
    one_word = slugify("가" * 80)
    assert len(one_word) == SLUG_MAX_LEN and SLUG_RE.match(one_word)     # a single longer word is cut
    for name in ("커피&빵", "근대·역사 골목", "Café 온", "1박 2일", "（주）한빛 상회"):
        assert SLUG_RE.match(slugify(name)), name
    assert slugify("근대·역사 골목") == "geundae-yeoksa-golmok"
    assert is_slug("abc-1") and not is_slug("Abc") and not is_slug("a--b") and not is_slug("a" * 61) and not is_slug("")


def test_ascii_core_is_the_shared_part_of_the_english_slug():
    for text in ("Eunpa Lake Park", "Course A Modern–Gogunsan", "동국사 Dongguksa Temple", "Café & Bakery",
                 "Where and when to eat jjamppong, marinated blue crab and bakdae in Gunsan"):
        core = ascii_core(text)
        words = core.split("-")
        while len(words) > 1 and words[-1] in {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or",
                                                "the", "to", "with"}:
            words.pop()
        assert "-".join(words) == en_slug(text), text


def test_fallback_slug():
    assert fallback_slug("place", "tourapi-126508") == "place-126508"
    assert fallback_slug("event", "festival") == "event-festival"
    assert fallback_slug("guide", "가이드") == "guide-gaideu"
    weird = fallback_slug("place", "大邱")
    assert weird.startswith("place-") and len(weird) == len("place-") + 6 and SLUG_RE.match(weird)


# ---------------------------------------------------------------- assign_slugs
def test_assign_slugs_reserves_stored_slugs_and_reports_bad_ones_without_renaming():
    items = [{"id": "p-1", "name": "같은 집", "slug": "gateun-jip"},
             {"id": "p-2", "name": "다른 집", "slug": "Bad_Slug"},
             {"id": "p-3", "name": "또 다른 집", "slug": "gateun-jip"},
             {"id": "p-4", "name": "같은 집"}]
    problems = assign_slugs(items, name_key="name", kind="place", policy="number")
    assert [it["slug"] for it in items] == ["gateun-jip", "Bad_Slug", "gateun-jip", "gateun-jip-2"]
    assert len(problems) == 2
    assert "p-2" in problems[0] and "형식 오류" in problems[0]
    assert "p-3" in problems[1] and "중복" in problems[1] and "p-1" in problems[1]
    assert [it.get("_slug_generated") for it in items] == [None, None, None, True]


def test_assign_slugs_in_id_order_with_the_district_then_a_number():
    district = {"p-2": "중구", "p-10": "중구", "p-5": "수성구", "p-7": ""}
    items = [{"id": i, "name": "같은 집"} for i in ("p-10", "p-2", "p-5", "p-7")] + [{"id": "p-9", "name": "大邱"}]
    assert assign_slugs(items, name_key="name", kind="place", policy="district",
                        district_of=lambda it: district.get(it["id"], "")) == []
    got = {it["id"]: it["slug"] for it in items}
    # natural id order: p-2 first takes the plain slug; p-5 its 구; p-7 has no 구 → a number; p-10 the 구 then -2
    assert got == {"p-2": "gateun-jip", "p-5": "gateun-jip-suseong-gu", "p-7": "gateun-jip-2",
                   "p-10": "gateun-jip-jung-gu", "p-9": "place-9"}
    # a district already given as a slug is used as it is; policy "number" never adds it
    items = [{"id": "a", "name": "집"}, {"id": "b", "name": "집"}]
    assign_slugs(items, name_key="name", kind="place", policy="district", district_of=lambda it: "jung-gu")
    assert [it["slug"] for it in items] == ["jip", "jip-jung-gu"]
    items = [{"id": "a", "name": "집"}, {"id": "b", "name": "집"}]
    assign_slugs(items, name_key="name", kind="place", policy="number", district_of=lambda it: "중구")
    assert [it["slug"] for it in items] == ["jip", "jip-2"]


def test_assign_slugs_keeps_the_limit_with_a_suffix_and_respects_reserved():
    long_name = " ".join(["가나다라"] * 7)                       # 62 characters romanized
    items = [{"id": "a", "name": long_name}, {"id": "b", "name": long_name}, {"id": "c", "name": long_name}]
    assign_slugs(items, name_key="name", kind="place", policy="district", district_of=lambda it: "달성군")
    for it in items:
        assert len(it["slug"]) <= SLUG_MAX_LEN and SLUG_RE.match(it["slug"]), it["slug"]
    assert items[1]["slug"].endswith("-dalseong-gun") and items[2]["slug"].endswith("-dalseong-gun-2")
    items = [{"id": "x", "name": "서문 시장"}]
    assign_slugs(items, name_key="name", kind="place", reserved=["seomun-sijang"])
    assert items[0]["slug"] == "seomun-sijang-2"
    with pytest.raises(ValueError):
        assign_slugs([], name_key="name", kind="place", policy="random")


def test_metro_fixture_slugs_follow_the_rules():
    """The fixture's stored slugs are what assign_slugs gives with the city's 구·군 and 동 as admin words."""
    site = json.loads((METRO / "site.json").read_text("utf-8"))
    c = citymod.from_site(site)
    stored = json.loads((METRO / "places.json").read_text("utf-8"))
    fresh = [{k: v for k, v in p.items() if k != "slug"} for p in stored]
    addr = lambda e: e["facts"]["address"]
    assert assign_slugs(fresh, name_key="name", kind="place", policy=c.slug_collision,
                        district_of=lambda e: c.parse_address(addr(e)).district,
                        admin_of=lambda e: c.admin_words(addr(e))) == []
    assert [p["slug"] for p in fresh] == [p["slug"] for p in stored]
    by_id = {p["id"]: p["slug"] for p in stored}
    assert by_id["metro-0009"] == "gateun-ireum-sikdang" and by_id["metro-0010"] == "gateun-ireum-sikdang-nam-gu"
    assert by_id["metro-0001"] == "jung-gu-jeonsigwan-a"


# ---------------------------------------------------------------- series, topics, fragment ids
def test_series_slug_prefers_the_newest_stored_slug_and_strips_year_and_edition():
    taken = {"seomun-chukje"}
    eds = [{"id": "e1", "start_date": "2025-10-01", "slug": "old-slug"}, {"id": "e2", "start_date": "2026-10-01", "slug": "new-slug"}]
    assert series_slug(eds, "2026 서문 축제", taken) == "new-slug"
    assert series_slug([{"id": "e3", "start_date": "2026-05-01"}], "2026 제5회 서문 축제", taken) == "seomun-chukje-2"
    assert series_slug([{"id": "e4"}], "제12회 한빛 축제", taken) == "hanbit-chukje"
    assert series_slug([{"id": "e5"}], "大邱", taken) == "event-5"
    assert {"new-slug", "seomun-chukje-2", "hanbit-chukje", "event-5"} <= taken


def test_topic_slug():
    taken: set = set()
    assert topic_slug("먹거리", {"먹거리": "food"}, taken) == "food"
    assert topic_slug("먹거리", [("먹거리", "food")]) == "food"
    assert topic_slug("기타", (), taken) == "other"
    assert topic_slug("근대·역사", (), taken) == "geundae-yeoksa"
    assert topic_slug("근대 역사", (), taken) == "geundae-yeoksa-2"          # no silent overwrite
    assert taken == {"food", "other", "geundae-yeoksa", "geundae-yeoksa-2"}


def test_anchor_ids_are_ascii():
    assert anchor_id("g", "당일") == "g-day-trip" and anchor_id("g", "1박 2일") == "g-one-night"
    assert anchor_id("g", "2박 3일") == "g-two-nights" and anchor_id("g", "여행 코스") == "g-yeohaeng-koseu"
    assert anchor_id("i", "ㅇ") == "i-ng" and anchor_id("i", initial_id("ㅊ")) == "i-ch"
    assert anchor_id("i", initial_id("A–Z·숫자")) == "i-other"
    assert anchor_id("d", "jung-gu", "삼덕동1가") == "d-jung-gu-samdeokdong-1-ga"
    for frag in (anchor_id("r", "大邱"), anchor_id("v", "근대·역사"), anchor_id("d", "none", "")):
        assert SLUG_RE.match(frag), frag


# ---------------------------------------------------------------- romanize: the English pages' default is unchanged
def test_romanize_default_mode_is_unchanged():
    """Values of the implementation that lived in pipeline.en_source before the move (commit 25c2d83)."""
    assert romanize("경암동 철길마을") == "Gyeongam-dong Cheolgilmaeul"
    assert romanize("평양냉면") == "Pyeongyangnaeng-myeon"
    assert [romanize(x) for x in ("종로", "신라", "백마", "박물관", "칼날", "백리", "해돋이", "같이", "좋고", "놓는", "묵호")] == \
        ["Jongno", "Silla", "Baengma", "Bangmulgwan", "Kallal", "Baengni", "Haedoji", "Gachi", "Joko", "Nonneun", "Mukho"]
    assert romanize("E-World(이월드)") == "E-World (Iwoldeu)" and romanize("83타워") == "83tawo"
    assert romanize("동국사 Dongguksa") == "Dongguksa Dongguksa" and romanize(None) == ""
    # one implementation: every module romanizes through pipeline.romanize (en_source no longer re-exports it)
    from pipeline import en_site, en_source
    assert en_source.romanize is romanize and en_site.romanize is romanize
    assert not ({"HANGUL", "_rr_run"} & set(vars(en_source)))


def test_leaf_modules_import_only_the_standard_library():
    """romanize and slugs are leaves (design 2.1): textutil, city and build import them, never the reverse."""
    allowed = {"romanize.py": set(), "slugs.py": {"romanize"}}
    for name, local in allowed.items():
        tree = ast.parse((ROOT / "pipeline" / name).read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.module in local, (name, node.module)
                    continue
                mods = [(node.module or "").split(".")[0]]
            else:
                continue
            for m in mods:
                assert m in sys.stdlib_module_names or m == "__future__", (name, m)
