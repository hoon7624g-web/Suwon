"""No city's own words in the engine (WP7, design 6.2): every city value comes from data/<city>/site.json through
pipeline/city.py (CLAUDE.md 4). Checked:
- pipeline/*.py: every string constant (ast, docstrings included; comments are not checked) — none of the first
  city's words (Gunsan), none of the city the engine was generalized on (Daegu: the city, its 9 구·군) and none of
  this city's (read from data/<city>/site.json: its names, 구·군 and search examples);
- templates/**/*.j2 (the body, {# #} comments stripped), templates/assets/*.js, chatbot/*.js and api/*.js: none of
  the first city's words, none of this city's;
- tools/*.py: no path or name of the first city's site.
The one exception is the national table of dated administrative renames (textutil.ADDRESS_RENAMES): a fact about the
country's addresses, not a city setting. Its entries are pinned below so it cannot become a place to hide city words.
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# the first city's words (the engine came from the Gunsan site), and its province's old and new names
GUNSAN_WORDS = ("군산", "고군산", "선유도", "은파", "새만금", "비응", "짬뽕", "경암동", "초원사진관", "근대역사박물관", "빈해원",
                "이성당", "장미동", "월명", "gunsan", "Gunsan", "Jeonbuk", "전북특별자치도", "전라북도")
# the city the engine was generalized on (pipeline/city.py): its name and its 9 구·군 — they belong in its site.json
DAEGU_WORDS = ("대구", "daegu", "Daegu", "중구", "동구", "서구", "남구", "북구", "수성구", "달서구", "달성군", "군위군", "군위",
               "달성")
GUNSAN_RX = re.compile("|".join(re.escape(w) for w in GUNSAN_WORDS), re.I)
DAEGU_RX = re.compile("|".join(re.escape(w) for w in DAEGU_WORDS), re.I)

# this city: every data/<city>/site.json but the sample's (the first city's values, checked above)
CITY_SITES = sorted(d / "site.json" for d in (ROOT / "data").iterdir()
                    if d.name != "sample" and (d / "site.json").is_file())


def city_words(site: dict) -> set[str]:
    """A city's own words from its site.json: its names (Korean, English, the site's), its 구·군, its search examples
    and the region names the assistant uses in every language."""
    words = {site.get(k) for k in ("region", "region_en", "locality", "site_name", "site_name_en")}
    words |= set(site.get("districts") or ()) | set(site.get("search_examples") or ())
    words |= set(((site.get("chatbot") or {}).get("region_names") or {}).values())
    return {w.strip() for w in words if isinstance(w, str) and len(w.strip()) >= 2}


def words_rx(words) -> re.Pattern:
    """A Korean word not inside another Korean word ('영주' is the city, '공영주차장' is not), a Latin word on a word
    boundary, any other script as written."""
    def one(w):
        if re.match(r"[가-힣]", w):
            return r"(?<![가-힣])" + re.escape(w)
        return (r"\b" + re.escape(w) + r"\b") if re.match(r"[A-Za-z]", w) else re.escape(w)
    return re.compile("|".join(one(w) for w in sorted(words, key=len, reverse=True)), re.I)


CITY_RX = words_rx(set().union(*(city_words(json.loads(p.read_text("utf-8"))) for p in CITY_SITES)) or {"\0"})

# (file, top-level name) whose string constants are exempt, with the reason. Exactly one entry.
ALLOWED = {("pipeline/textutil.py", "ADDRESS_RENAMES"):
           "national administrative renames with their dates (전북특별자치도 2024-01-18, 군위군 편입 2023-07-01)"}
TOOL_PATHS = re.compile(r"data/gunsan|all-about-gunsan|gunsan-seven|round3_")


def _exempt_lines(tree: ast.Module, rel: str) -> set[int]:
    """Line numbers of the top-level assignments ALLOWED names in this file."""
    lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and (rel, t.id) in ALLOWED:
                    lines |= set(range(node.lineno, node.end_lineno + 1))
    return lines


def string_constants(path: Path) -> list[tuple[int, str]]:
    """(line, text) of every str constant of a module (docstrings and f-string parts included), minus ALLOWED."""
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text("utf-8"))
    skip = _exempt_lines(tree, rel)
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.lineno not in skip]


def template_body(path: Path) -> str:
    """A Jinja template without its {# … #} comments (whitespace-control forms included)."""
    return re.sub(r"\{#.*?#\}", "", path.read_text("utf-8"), flags=re.S)


def hits(rx: re.Pattern, items) -> list[str]:
    return [f"{where}: {m.group(0)!r} in {text[:80]!r}" for where, text in items for m in [rx.search(text)] if m]


PIPELINE = sorted((ROOT / "pipeline").glob("*.py"))


def test_engine_names_no_gunsan_word():
    found = hits(GUNSAN_RX, [(f"{p.name}:{line}", s) for p in PIPELINE for line, s in string_constants(p)])
    templates = sorted((ROOT / "templates").rglob("*.j2"))
    found += hits(GUNSAN_RX, [(p.relative_to(ROOT).as_posix(), template_body(p)) for p in templates])
    scripts = sorted((ROOT / "templates" / "assets").glob("*.js"))
    found += hits(GUNSAN_RX, [(p.relative_to(ROOT).as_posix(), p.read_text("utf-8")) for p in scripts])
    assert len(PIPELINE) > 10 and len(templates) > 20 and len(scripts) >= 5   # the scan sees the engine
    assert found == []


def test_engine_names_no_daegu_word():
    found = hits(DAEGU_RX, [(f"{p.name}:{line}", s) for p in PIPELINE for line, s in string_constants(p)])
    assert found == []


def test_engine_names_no_word_of_this_city():
    """This city's words (data/<city>/site.json) are in none of the engine's modules, templates and scripts: a city
    value is read from site.json (pipeline/city.py), never written into the engine (CLAUDE.md 4)."""
    assert CITY_SITES, "no data/<city>/site.json"
    templates = sorted((ROOT / "templates").rglob("*.j2"))
    scripts = sorted((ROOT / "templates" / "assets").glob("*.js")) + sorted((ROOT / "chatbot").glob("*.js")) \
        + sorted((ROOT / "api").glob("*.js"))
    for site_json in CITY_SITES:
        words = city_words(json.loads(site_json.read_text("utf-8")))
        assert words, site_json
        rx = words_rx(words)
        found = hits(rx, [(f"{p.name}:{line}", s) for p in PIPELINE for line, s in string_constants(p)])
        found += hits(rx, [(p.relative_to(ROOT).as_posix(), template_body(p)) for p in templates])
        found += hits(rx, [(p.relative_to(ROOT).as_posix(), p.read_text("utf-8")) for p in scripts])
        assert found == [], (site_json.parent.name, found)


def test_the_city_word_pattern():
    rx = words_rx({"영주", "Yeongju", "栄州"})
    assert rx.search("영주 여행") and rx.search("경상북도 영주시") and rx.search("Yeongju-si") and rx.search("栄州旅行")
    assert not rx.search("공영주차장") and not rx.search("운영주체") and not rx.search("Yeongjugak2")


def test_the_one_exception_is_the_national_rename_table():
    """ALLOWED holds one table, and that table holds dated national renames only: (old prefix pattern, new prefix)."""
    from pipeline import textutil

    assert list(ALLOWED) == [("pipeline/textutil.py", "ADDRESS_RENAMES")]
    assert [new for _, new in textutil.ADDRESS_RENAMES] == ["전북특별자치도 ", "대구광역시 군위군", r"\1\2읍"]
    assert textutil.display_address("전라북도 군산시 구영7길 69") == "전북특별자치도 군산시 구영7길 69"
    assert textutil.display_address("경상북도 군위군 군위읍 군청로 10") == "대구광역시 군위군 군위읍 군청로 10"
    # 면 -> 읍 승격 with its date (달성군 연혁): the old name a source still writes reads as the current one; a road
    # name that only starts with the old name ('현풍면사무소길') and another 면 stay as written
    assert textutil.display_address("대구광역시 달성군 현풍면 상리") == "대구광역시 달성군 현풍읍 상리"
    assert textutil.display_address("대구광역시 달성군 현풍면사무소길 3") == "대구광역시 달성군 현풍면사무소길 3"
    assert textutil.display_address("대구광역시 달성군 하빈면 하산리") == "대구광역시 달성군 하빈면 하산리"
    # outside the table the textutil module names no city at all
    rest = [s for _, s in string_constants(ROOT / "pipeline" / "textutil.py")]
    assert not [s for s in rest if GUNSAN_RX.search(s) or DAEGU_RX.search(s)]


def test_the_scan_would_catch_a_city_word():
    """The checks are live: a docstring, an f-string part and a template body with a city word are all found, and
    a {# comment #} is not."""
    src = 'def f(x):\n    """한빛 대구 안내."""\n    return f"{x} 군산시"\n'
    tree = ast.parse(src)
    consts = [(n.lineno, n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert len(hits(DAEGU_RX, consts)) == 1 and len(hits(GUNSAN_RX, consts)) == 1
    body = re.sub(r"\{#.*?#\}", "", "{#- 군산 예시 -#}<p>{{ cityv.region }}</p>{# Gunsan #}")
    assert not GUNSAN_RX.search(body)
    assert GUNSAN_RX.search("<p>Gunsan</p>") and GUNSAN_RX.search("all-about-gunsan")


def test_tools_name_no_path_of_the_first_city():
    tools = sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "tools").glob("*.sh"))
    found = [f"{p.name}:{i}: {line.strip()[:80]}" for p in tools
             for i, line in enumerate(p.read_text("utf-8").splitlines(), 1) if TOOL_PATHS.search(line)]
    assert len(tools) > 10 and found == []
