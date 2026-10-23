"""No city's own words in the engine (WP7, design 6.2): every city value comes from data/<city>/site.json through
pipeline/city.py (CLAUDE.md 4). Checked:
- pipeline/*.py: every string constant (ast, docstrings included; comments are not checked) — none of the first
  city's words (Gunsan) and none of this city's (Daegu: the city, its 9 구·군) either;
- templates/**/*.j2 (the body, {# #} comments stripped) and templates/assets/*.js: none of the first city's words;
- tools/*.py: no path or name of the first city's site.
The one exception is the national table of dated administrative renames (textutil.ADDRESS_RENAMES): a fact about the
country's addresses, not a city setting. Its entries are pinned below so it cannot become a place to hide city words.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# the first city's words (the engine came from the Gunsan site), and its province's old and new names
GUNSAN_WORDS = ("군산", "고군산", "선유도", "은파", "새만금", "비응", "짬뽕", "경암동", "초원사진관", "근대역사박물관", "빈해원",
                "이성당", "장미동", "월명", "gunsan", "Gunsan", "Jeonbuk", "전북특별자치도", "전라북도")
# this city's words: its name and the 9 구·군 (site.json districts) — they belong in data/daegu/site.json only
DAEGU_WORDS = ("대구", "daegu", "Daegu", "중구", "동구", "서구", "남구", "북구", "수성구", "달서구", "달성군", "군위군", "군위",
               "달성")
GUNSAN_RX = re.compile("|".join(re.escape(w) for w in GUNSAN_WORDS), re.I)
DAEGU_RX = re.compile("|".join(re.escape(w) for w in DAEGU_WORDS), re.I)

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
