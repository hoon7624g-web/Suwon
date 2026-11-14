"""The city government's own photos (CITY-PERMIT, site.json city_photos — 운영자 결정 2026-11-14 '모두 허락 받았어 …'):
their place in a place's photo list, the same-origin copies pages use instead of the city's files, the one credit line
(the city's name only — 운영자 2026-11-14 ''이용 허락'이라는 글자 표기하지 말고 모두 빼 출처만 표기해'), never a link
preview, and the validator's page checks. No browser, no network."""
from pathlib import Path
from types import SimpleNamespace

from pipeline import media, present, validate
from pipeline.schema import EDITABLE_LICENSES, LICENSE_LABELS

ROOT = Path(__file__).resolve().parent.parent
CITY = "https://photo.example.go.kr/data/simg/202611/I1.JPG"
CITY2 = "https://photo.example.go.kr/data/simg/202611/I2.JPG"
KTO = "https://tong.visitkorea.or.kr/cms/resource/1_image2_1.jpg"
KTO3 = "https://tong.visitkorea.or.kr/cms/resource/3_image2_1.jpg"


def place(images):
    return {"id": "p1", "name": "누리관", "_images": images}


def img(url, lic, source="TourAPI", **kw):
    return {"url": url, "license": lic, "source": source, "credit": "한국관광공사", **kw}


def test_licence_code_is_editable_and_known():
    assert "CITY-PERMIT" in LICENSE_LABELS and EDITABLE_LICENSES == ("KOGL-1", "CITY-PERMIT")


def test_kto_photos_first_then_the_city_photos_in_stored_order():
    e = place([img(CITY, "CITY-PERMIT", "포토뱅크", page="https://photo.example.go.kr/v?1", opens_page=True),
               img(KTO, "KOGL-1"), img(CITY2, "CITY-PERMIT", "포토뱅크"), img(KTO3, "KOGL-3")])
    phs = present.photos(e, {}, "누리시")
    assert [p["url"] for p in phs] == [KTO, KTO3, CITY, CITY2]
    city = phs[2]
    assert city["src"] == "city" and city["type"] == 1 and city["lic"] == "" and city["credit"] == "누리시"
    assert city["opens_page"] and city["page"].endswith("?1") and city["th"] is None
    assert phs[0]["src"] == "kto" and phs[0]["page"] == "" and phs[0]["credit"] == "한국관광공사"


def test_pages_never_load_the_city_files():
    man = {CITY: {"w": 800, "h": 600, "slot": "thumb", "avif": [],
                  "webp": [["/assets/media/g-i1-480.webp", 480, 30000]]},
           CITY2: None}
    e = {"_photos": [present.photo(img(KTO, "KOGL-1"), "누리관", {}),
                     present.photo(img(CITY, "CITY-PERMIT", page="https://photo.example.go.kr/v?1", opens_page=True),
                                   "누리관", {}, "누리시"),
                     present.photo(img(CITY2, "CITY-PERMIT"), "누리관", {}, "누리시")]}
    S = SimpleNamespace(entities=[e])
    media.attach(S, {k: v for k, v in man.items() if v})
    phs = e["_photos"]
    assert len(phs) == 2 and len(e["_photos_all"]) == 3      # a city photo without our copy is dropped
    c = phs[1]
    assert c["url"] == "/assets/media/g-i1-480.webp" and c["orig"] == CITY and c["full"].endswith("?1")
    assert c["w"] == 800 and c["h"] == 600
    assert phs[0]["full"] == KTO and phs[0]["url"] == KTO
    # what tools/kogl1_media.py is asked for: the city photos after the lead (portal → thumb, website → view)
    e["_photos_all"][2]["opens_page"] = False
    S2 = SimpleNamespace(entities=[e], city=SimpleNamespace(home={}))
    want = media.wanted(S2)
    assert want[CITY] == "thumb" and want[CITY2] == "view" and want[KTO] == "k1"


def test_credit_line_names_the_city_only():
    present.CITY_CREDIT["name"] = "누리시"
    kto1, kto3 = {"type": 1, "src": "kto"}, {"type": 3, "src": "kto"}
    city = {"type": 1, "src": "city", "credit": "누리시"}
    assert present.credit_line([kto1, kto3]) == "한국관광공사 · 공공누리 제1유형·제3유형(변경금지)"
    assert present.credit_line([kto1, city]) == "한국관광공사 · 공공누리 제1유형 / 누리시"
    assert present.credit_line([city]) == "누리시"
    for w in validate.PERMISSION_WORDS:
        assert w not in present.credit_line([kto1, kto3, city])


def test_link_previews_are_kto_type1_only():
    assert present.og_photo({"type": 1, "src": "kto"})
    assert not present.og_photo({"type": 3, "src": "kto"})
    assert not present.og_photo({"type": 1, "src": "city"})


def test_manifest_rules_for_the_city_copies(tmp_path):
    d = tmp_path / "media"
    d.mkdir()
    (d / "g-i1-480.webp").write_bytes(b"x" * 5)
    man = {CITY: {"w": 800, "h": 600, "slot": "thumb", "avif": [], "webp": [["/assets/media/g-i1-480.webp", 480, 5]]}}
    assert media.manifest_problems(man, {CITY: "CITY-PERMIT"}, d) == []
    # a WebP-only slot for a KTO photo, or a city copy without a city licence, is reported
    assert media.manifest_problems(man, {CITY: "KOGL-3"}, d)
    assert any("시청 사진 사본 합계" in p for p in media.manifest_problems(man, {CITY: "CITY-PERMIT"}, d, city_budget=1))


def test_validator_catches_city_files_previews_and_permission_words():
    hosts = ["photo.example.go.kr"]
    ok = '<img src="/assets/media/g-i1-480.webp" alt="">'
    assert validate.city_photo_problems(ok, {"og:image": KTO}, "출처: 누리시", hosts) == []
    raw = f'<img src="{CITY}" alt=""><source srcset="{CITY2} 800w">'
    assert len(validate.city_photo_problems(raw, {}, "", hosts)) == 2
    assert validate.city_photo_problems("", {"og:image": "https://x.kr/assets/media/g-i1-480.webp"}, "", hosts)
    assert validate.city_photo_problems("", {}, "출처: 누리시 · 이용 허락", hosts)
    assert validate.city_photo_problems("", {}, "Photos: Nuri City (used with permission)", hosts)
