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

    def fake(out, pages, block, **kw):
        seen.append(pages)
        return [{"page": p, "motion": "on", "lcp_ms": 2400, "lcp_element": "H1", "fcp_ms": 900, "cls": 0.0,
                 "font_kb": 100, "script_kb": 10, "requests": 5} for p in pages]
    monkeypatch.setattr(perf_check, "measure", fake)
    assert perf_check.main(["--out", str(tmp_path), "--pages", "/about/"]) == 0
    assert perf_check.main(["--out", str(tmp_path)]) == 0
    assert seen == [["/about/"], ["/"]]
    assert "| /about/ | on | 2400 |" in capsys.readouterr().out


def test_budgets_cover_cls_and_fonts_and_motion_off_rows_do_not_count(tmp_path, monkeypatch):
    page(tmp_path, "/")
    row = {"page": "/", "motion": "on", "lcp_ms": 2000, "lcp_element": "H1", "fcp_ms": 900, "cls": 0.0,
           "font_kb": 100, "script_kb": 10, "requests": 5}
    for over in ({"cls": 0.11}, {"font_kb": 301}, {"lcp_ms": 2501}, {"lcp_ms": 0}):
        monkeypatch.setattr(perf_check, "measure", lambda *a, _o=over, **k: [{**row, **_o}])
        assert perf_check.main(["--out", str(tmp_path)]) == 1, over
    monkeypatch.setattr(perf_check, "measure", lambda *a, **k: [{**row, "motion": "off(reduced)", "cls": 0.5}])
    assert perf_check.main(["--out", str(tmp_path)]) == 0


def test_compress_serves_text_gzipped_and_fonts_as_they_are(tmp_path):
    import gzip as gz
    import socket
    import urllib.request
    (tmp_path / "index.html").write_text("<h1>안녕</h1>" * 50, encoding="utf-8")
    (tmp_path / "f.woff2").write_bytes(b"wOF2" + b"x" * 100)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = perf_check.serve(tmp_path, port, compress=True)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req) as r:
            assert r.headers["Content-Encoding"] == "gzip"
            assert gz.decompress(r.read()).decode() == "<h1>안녕</h1>" * 50
        req = urllib.request.Request(f"http://127.0.0.1:{port}/f.woff2", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req) as r:
            assert r.headers.get("Content-Encoding") is None and r.read().startswith(b"wOF2")
    finally:
        srv.terminate()


def test_the_home_slide_counts_only_on_the_first_screen(tmp_path, monkeypatch):
    page(tmp_path, "/")
    row = {"page": "/", "motion": "on", "lcp_ms": 2000, "lcp_element": "IMG", "fcp_ms": 900, "cls": 0.0, "font_kb": 100,
           "script_kb": 10, "requests": 5, "slide": "local a.avif", "slide_ms": 0, "slide_ok": False}
    for first, code in ((True, 1), (False, 0)):
        monkeypatch.setattr(perf_check, "measure", lambda *a, _f=first, **k: [{**row, "slide_first": _f}])
        assert perf_check.main(["--out", str(tmp_path)]) == code
    monkeypatch.setattr(perf_check, "measure", lambda *a, **k: [{**row, "slide_first": True, "slide_ok": True, "slide_ms": 2600}])
    assert perf_check.main(["--out", str(tmp_path)]) == 1
