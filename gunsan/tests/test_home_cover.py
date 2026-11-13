"""The home's opening photo: a cover the page would drop (no AVIF derivative) fails validation
(pipeline/media.cover_problems; 2026-10-28 세종각·목포각)."""
from types import SimpleNamespace as NS

from pipeline import media


def state(photos):
    e = {"name": "표지 장소", "_path": "/places/p1/", "kind": "attraction", "_photos": photos}
    return NS(ent_by_slug={"p1": e}, warnings=[])


def k1(url, avif=True):
    return {"url": url, "type": 1, **({"avif": f"/assets/media/{url}-480.avif 480w"} if avif else {})}


def test_cover_with_derivative_passes(monkeypatch):
    monkeypatch.setattr(media, "HOME_COVER", ("p1", 0))
    assert media.cover_problems(state([k1("a")])) == []


def test_cover_without_derivative_names_the_ready_photos(monkeypatch):
    monkeypatch.setattr(media, "HOME_COVER", ("p1", 1))
    got = media.cover_problems(state([k1("a"), k1("b", avif=False), k1("c")]))
    assert len(got) == 1 and "변환본(AVIF)이 없어" in got[0] and "p1 #1" in got[0] and "#0, #2" in got[0]


def test_kogl3_cover_is_refused(monkeypatch):
    monkeypatch.setattr(media, "HOME_COVER", ("p1", 0))
    got = media.cover_problems(state([{"url": "a", "type": 3, "avif": "x 480w"}]))
    assert len(got) == 1 and "제3유형" in got[0]


def test_place_without_photos(monkeypatch):
    monkeypatch.setattr(media, "HOME_COVER", ("p1", 0))
    got = media.cover_problems(state([]))
    assert len(got) == 1 and "p1" in got[0]


def test_build_without_the_cover_place(monkeypatch):
    monkeypatch.setattr(media, "HOME_COVER", ("zz", 0))      # data/sample: no such place, nothing to show
    assert media.cover_problems(state([k1("a")])) == []
