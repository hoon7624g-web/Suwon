"""tools/perf_check.py: the default pages come from the build output (no fixed slug). No browser is started here."""
from pathlib import Path

import pytest

from tools import perf_check


def page(out: Path, path: str) -> None:
    folder = out / path.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text("<!doctype html><title>x</title>", "utf-8")


def test_default_pages_are_the_home_the_list_and_the_first_place_of_the_build(tmp_path):
    out = tmp_path / "out"
    for path in ("/", "/places/", "/places/b-place/", "/places/a-place/", "/courses/day-trip/"):
        page(out, path)
    (out / "places" / "no-page").mkdir()                       # a folder without index.html is not a page
    assert perf_check.default_pages(out) == ["/", "/places/", "/places/a-place/"]


def test_default_pages_skip_what_the_build_lacks(tmp_path):
    out = tmp_path / "out"
    page(out, "/")
    assert perf_check.default_pages(out) == ["/"]
    assert perf_check.default_pages(tmp_path / "missing") == []


def test_nothing_to_measure_is_an_argument_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(perf_check, "measure", lambda *a: pytest.fail("no page, no browser"))
    with pytest.raises(SystemExit) as exc:
        perf_check.main(["--out", str(tmp_path)])
    assert exc.value.code == 2 and "--pages" in capsys.readouterr().err


def test_explicit_pages_win_and_the_lcp_budget_decides_the_exit_code(tmp_path, monkeypatch, capsys):
    page(tmp_path, "/")
    seen = []

    def fake(out, pages, block):
        seen.append(pages)
        return [{"page": p, "motion": "on", "lcp_ms": 2400, "lcp_element": "H1", "fcp_ms": 900, "cls": 0.0,
                 "font_kb": 100, "script_kb": 10, "requests": 5} for p in pages]
    monkeypatch.setattr(perf_check, "measure", fake)
    assert perf_check.main(["--out", str(tmp_path), "--pages", "/about/"]) == 0
    assert perf_check.main(["--out", str(tmp_path)]) == 0
    assert seen == [["/about/"], ["/"]]
    assert "| /about/ | on | 2400 |" in capsys.readouterr().out
