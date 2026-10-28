"""The home's opening photo: a configured cover the page would drop (no AVIF derivative) fails validation
(pipeline/media.cover_problems; 2026-10-28 세종각·목포각)."""
from types import SimpleNamespace as NS

from pipeline import media


def state(cover, photos):
    e = {"id": "p1", "name": "호수공원", "_path": "/places/p1/", "_photos": photos}
    return NS(city=NS(home={"media": {"cover": cover}} if cover is not None else {}), entities=[e], warnings=[])


def k1(url, avif=True):
    return {"url": url, "type": 1, **({"avif": f"/assets/media/{url}-480.avif 480w"} if avif else {})}


def test_cover_with_derivative_passes():
    assert media.cover_problems(state(["p1", 0], [k1("a")])) == []


def test_no_cover_configured_passes():
    assert media.cover_problems(state(None, [k1("a")])) == []


def test_cover_without_derivative_names_the_ready_photos():
    got = media.cover_problems(state(["p1", 1], [k1("a"), k1("b", avif=False), k1("c")]))
    assert len(got) == 1 and "변환본(AVIF)이 없어" in got[0] and "p1 #1" in got[0] and "#0, #2" in got[0]


def test_kogl3_cover_is_refused():
    got = media.cover_problems(state(["p1", 0], [{"url": "a", "type": 3, "avif": "x 480w"}]))
    assert len(got) == 1 and "제3유형" in got[0]


def test_unknown_place():
    assert media.cover_problems(state(["zz", 0], [k1("a")])) == ["홈 표지 사진: 장소 없음 zz"]


def test_empty_build_has_no_cover_to_check():
    s = state(["p1", 0], [])
    s.entities = []          # a new city before its places (tests/test_empty_city)
    assert media.cover_problems(s) == []
