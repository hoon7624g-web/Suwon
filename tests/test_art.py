"""AI art (the first site's owner decisions 2026-10-13; pipeline/art.py): data/<city>/art.json, the renditions
tools/art_media.py writes,
the one macro that shows a picture (templates/_art.html.j2), the build publishing only what a page uses, and the
validate rules — alt '일러스트: …' with width and height, never on a place page, inside a place card or in a place's
structured data, and no 'AI 생성 이미지' label on any page (owner 2026-10-13 night: '다 빼'; /about/ says once that the
illustrations are drawn with generative AI). The home's news cards use the pictures; the season hero is no longer a
slot (the Korean home opens on an official photo). A slot whose files are missing renders exactly as the site does
without art.

This city has no art yet (the operator draws it later): the repository checks run on data/daegu's art.json when it
comes (none now: no slot, no rendition), and every engine rule is checked on a small synthetic picture set
(fake_art(): tiny files under tmp, art.ART_DIR pointed there) instead of the first site's pictures."""
import io
import json
import shutil
from pathlib import Path

import pytest

from pipeline import art
from pipeline.build import build, make_env
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
CITY = ROOT / "data" / "suwon"
SAMPLE = ROOT / "data" / "sample"


def page(body: str = "", head: str = "", jsonld: dict | None = None, lang: str = "ko") -> str:
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"<!doctype html><html lang=\"{lang}\"><head>{head}{ld}</head><body>{body}</body></html>"


def fig(alt="일러스트: 바다", size=' width="640" height="427"', name="hero-autumn-640", caption=""):
    """A picture as templates/_art.html.j2 draws it: no caption (caption: a label as the pages carried it before)."""
    cap = f'<figcaption class="art-label">{caption}</figcaption>' if caption else ""
    return (f'<figure class="art" data-art="hero-autumn"><picture><source type="image/avif" '
            f'srcset="/assets/art/{name}.avif 640w"><img src="/assets/art/{name}.webp" alt="{alt}"{size}></picture>'
            f'{cap}</figure>')


def fake_art(data_dir: Path, art_dir: Path, entries: dict) -> dict:
    """A synthetic picture set: art.json in data_dir and, in art_dir, a manifest with tiny files for every entry
    {art_id: {"slot", "status" (default '연결'), "size" (w, h), "langs", "text", "files": False (none on disk)}}.
    Link previews (og-*) get one 1200 JPEG; the others AVIF and WebP at 400 and 800 (never wider than w)."""
    art_dir.mkdir(parents=True, exist_ok=True)
    blob = tiny_picture()
    images, manifest = {}, {}
    for art_id, e in entries.items():
        w, h = e.get("size", (1024, 1024))
        text = e.get("text")
        alt = f"일러스트: 시험 그림 {art_id}" + (f" {text}" if text else "")
        meta = {"file": f"{art_id}.png", "alt": alt, "alt_en": f"Illustration: test picture {art_id}",
                "slot": e["slot"], "status": e.get("status", "연결")}
        if e.get("langs"):
            meta["langs"] = e["langs"]
            if "en" not in e["langs"]:
                meta.pop("alt_en")
        if text:
            meta["text"] = [text]
        images[art_id] = meta
        if e.get("files") is False:
            continue
        if art_id.startswith("og-"):
            names = {"jpg": [[f"{art_id}-1200.jpg", 1200, len(blob)]]}
            w, h = 1200, 630
        else:
            names = {fmt: [[f"{art_id}-{x}.{fmt}", x, len(blob)] for x in (400, 800) if x <= w]
                     for fmt in ("avif", "webp")}
        for files in names.values():
            for name, _, _ in files:
                (art_dir / name).write_bytes(blob)
        manifest[art_id] = {"w": w, "h": h, **names}
    (data_dir / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    (art_dir / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return images


# ------------------------------------------------------------------ the repository's art: data, renditions, budget
# the renditions the owner's pictures need, written out here (not read from tools/art_media.py, so a wrong change to
# its tables fails a test even after the renditions are made again): the 2.4:1 bands are cut 1536:640 from the
# centre; a picture a phone shows at its width (the bands, the campaign cards, the about head) gets a small file first
BANDS = ("head-", "theme-", "vtopic-", "course-", "area-")
PHONE_WIDTH = (*BANDS, "camp-", "en-camp-", "about-")


def test_city_art_json_matches_the_renditions_on_disk():
    """data/daegu/art.json (none yet: no picture, no rendition) against templates/assets/art."""
    assert art.data_problems(CITY) == []
    data, manifest = art.load(CITY), art.load_manifest()
    assert set(manifest) == set(data["images"])              # no rendition without an entry, none missing
    assert not set(data["held"]) & set(manifest)              # a held picture is not prepared
    listed = {name for m in manifest.values() for fmt in ("avif", "webp", "jpg") for name, _, _ in m.get(fmt) or []}
    on_disk = {f.name for f in art.ART_DIR.iterdir() if f.name != "manifest.json"} if art.ART_DIR.is_dir() else set()
    assert on_disk == listed                                  # nothing stray in templates/assets/art
    for art_id, m in manifest.items():
        if art_id.startswith("og-"):                          # a link preview: one 1200×630 JPEG
            assert (m["w"], m["h"]) == (1200, 630) and [w for _, w, _ in m["jpg"]] == [1200], art_id
            assert not m.get("avif") and not m.get("webp"), art_id
            continue
        if art_id.startswith(BANDS):                          # a band (head-, theme-, …), cut 1536:640 from the centre
            assert m["w"] * 640 == m["h"] * 1536, art_id
        landscape = m["w"] != m["h"]
        if art_id.startswith(PHONE_WIDTH):                    # a phone shows it at its width: a small file first
            wanted = (400, 800, 1280, 1920)
        else:
            wanted = (640, 1280, 1920) if landscape else (400, 800)
        widths = [x for x in wanted if x <= m["w"]] + ([m["w"]] if max(wanted) > m["w"] else [])
        for fmt in ("avif", "webp"):
            assert [w for _, w, _ in m[fmt]] == widths, (art_id, fmt)   # never wider than the original
        if art_id.startswith("hero-"):
            assert next(b for _, w, b in m["avif"] if w == 1280) <= 150_000, art_id   # first-screen budget


def test_every_picture_has_a_slot_and_illustration_alt_texts():
    found = art.slots(CITY)
    data = art.load(CITY)
    assert set(found) == {meta["slot"] for meta in data["images"].values() if meta["status"] == "연결"}
    for slot, pic in found.items():
        langs = data["images"][pic["id"]].get("langs") or ["ko", "en"]
        assert "ko" not in langs or pic["alt"].startswith("일러스트: "), slot
        assert "en" not in langs or pic["alt_en"].startswith("Illustration: "), slot
        assert all(pic["alts"][lang].startswith(art.ALT_PREFIX[lang]) for lang in langs), slot
        assert not {"label", "label_en", "labels"} & set(pic)               # no label travels with a picture
        if slot.startswith("og."):                                   # a link preview: one JPEG, no srcset
            assert pic["src"].endswith("-1200.jpg") and not pic["avif"], slot
        else:
            assert pic["avif"].startswith("/assets/art/") and pic["src"].endswith(".webp"), slot
    for art_id in data["held"]:
        assert not any(p["id"] == art_id for p in found.values())
    assert not any(slot.startswith("home.hero.") for slot in found)       # the home opens on a photo now
    printed = {k: v for k, v in data["images"].items() if v.get("text")}   # campaign cards and link previews
    kinds = {next((p for p in ("en-camp", "camp", "og") if k.startswith(p + "-")), k) for k in printed}
    assert kinds <= {"camp", "en-camp", "og"}, sorted(printed)   # only campaign cards and link previews carry words
    for art_id, meta in printed.items():
        assert not ({"ko", "en"} <= set(meta.get("langs") or ["ko", "en"])), art_id   # words in one language


def test_the_season_hero_is_not_a_slot_any_more(tmp_path):
    """Owner 2026-10-13 night: the Korean home opens on the official photo, so home.hero.<season> is no slot of the
    site — the repository's four season pictures stay listed as '개편 뒤 연결' (a slot the site does not have) with a
    note, and one put back to '연결' is an error, not a picture shown nowhere."""
    for season in ("spring", "summer", "autumn", "winter"):
        assert not art.known_slot(f"home.hero.{season}"), season
    assert art.known_slot("home.card.event") and art.known_slot("list.head.places")
    fake_art(tmp_path, tmp_path / "art", {"hero-autumn": {"slot": "home.hero.autumn", "status": "개편 뒤 연결",
                                                          "size": (1536, 1024)}})
    assert art.data_problems(tmp_path, tmp_path / "art") == []          # kept for a slot the site does not have
    assert art.slots(tmp_path, tmp_path / "art") == {}
    fake_art(tmp_path, tmp_path / "art", {"hero-autumn": {"slot": "home.hero.autumn", "size": (1536, 1024)}})
    assert any("'연결'인데 사이트에 없는 자리: home.hero.autumn" in p for p in art.data_problems(tmp_path, tmp_path / "art"))


def test_a_picture_without_its_renditions_is_an_empty_slot(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    fake_art(data, tmp_path / "art", {"card-guide": {"slot": "home.card.guide"}, "art-404": {"slot": "page.404"}})
    assert set(art.slots(data, tmp_path / "art")) == {"home.card.guide", "page.404"}
    assert art.slots(data, tmp_path / "no-art") == {}          # files missing: the slot renders as without art
    assert art.slots(SAMPLE) == {}                             # a region without art.json has no art
    assert any("파생본 없음" in p for p in art.data_problems(data, tmp_path / "no-art"))


def test_data_problems_catch_bad_alt_slot_status_and_held(tmp_path):
    bad = {"images": {"hero-autumn": {"alt": "가을 풍경", "alt_en": "autumn", "slot": "Home Hero", "status": "보류"}},
           "held": {"hero-autumn": "다시 만들기"}}
    (tmp_path / "art.json").write_text(json.dumps(bad, ensure_ascii=False), "utf-8")
    problems = "\n".join(art.data_problems(tmp_path))
    for needle in ("alt는 '일러스트: '", "alt_en는 'Illustration: '", "slot 형식", "status는", "held(보류)에도"):
        assert needle in problems, needle


# ------------------------------------------------------------------ the macro: alt, size, loading — and no label
def test_figure_macro_draws_the_picture_without_a_label_and_passes_the_page_rules(tmp_path):
    fake_art(tmp_path, tmp_path / "art", {"card-event": {"slot": "home.card.event", "size": (1536, 1024)}})
    pic = art.slots(tmp_path, tmp_path / "art")["home.card.event"]
    macro = make_env().get_template("_art.html.j2").module.figure
    ko = str(macro(pic, sizes="(min-width: 1024px) 50vw, 100vw"))
    assert f'data-art="{pic["id"]}"' in ko and f'alt="{pic["alt"]}"' in ko and pic["alt"].startswith("일러스트: ")
    assert "<figcaption" not in ko and not art.dropped_labels(ko)    # owner 2026-10-13 night: no label
    assert f'width="{pic["w"]}" height="{pic["h"]}"' in ko and 'loading="lazy"' in ko and "fetchpriority" not in ko
    assert 'type="image/avif"' in ko and 'type="image/webp"' in ko
    en = str(macro(pic, lang="en", eager=True))
    assert f'alt="{pic["alt_en"]}"' in en and pic["alt_en"].startswith("Illustration: ")
    assert "<figcaption" not in en and not art.dropped_labels(en)
    assert "fetchpriority" not in en and "loading=" not in en      # first screen: not lazy, not ahead of fonts
    assert 'fetchpriority="high"' in str(macro(pic, high=True))
    assert art.page_problems(page(ko), [], place=False) == []
    assert art.page_problems(page(en, lang="en"), [], place=False) == []


# ------------------------------------------------------------------ page rules (validate.py uses page_problems)
def test_page_rules_accept_a_figure_without_label_and_og_image_off_place_pages():
    head = '<meta property="og:image" content="https://x.test/assets/art/og-ko-1200.jpg">' \
           '<link rel="preload" as="image" imagesrcset="/assets/art/hero-autumn-640.avif 640w">'
    assert art.page_problems(page(fig(), head), [{"@type": "WebPage", "image": "/assets/art/og.jpg"}], False) == []
    assert art.page_problems(page("<p>no art</p>"), [], True) == []


@pytest.mark.parametrize("body, needle", [
    ('<img src="/assets/art/hero-autumn-640.webp" alt="일러스트: 바다" width="1" height="1">', "figure[data-art]"),
    ('<div style="background:url(/assets/art/hero-autumn-640.webp)"></div>', "figure[data-art]"),
    (fig(caption="AI 생성 이미지"), "'AI 생성 이미지'가 페이지에 있음"),
    (fig(alt="바다 사진"), "alt가 '일러스트: '"),
    (fig(alt="일러스트: "), "alt가 '일러스트: '"),
    (fig(size=""), "width·height"),
    (f'<a href="/places/seonyudo/">{fig()}</a>', "장소 카드"),
    (f'<a href="/en/places/seonyudo/">{fig()}</a>', "장소 카드"),
    ('<figure data-art="x"></figure>', "<img>가 없음"),
])
def test_page_rules_reject_misplaced_or_badly_described_art(body, needle):
    problems = art.page_problems(page(body), [], place=False)
    assert any(needle in p for p in problems), problems


@pytest.mark.parametrize("body, lang", [
    (fig(caption="AI 생성 이미지"), "ko"),                               # the caption the pictures carried
    ("<p>사진 아래 AI 생성 이미지라고 적음</p>", "ko"),                      # any text, art or not
    ("<p>AI생성  이미지</p>", "ko"),                                      # any spacing
    ('<img src="/x.webp" alt="AI 생성 이미지" width="1" height="1">', "ko"),   # an attribute too
    ("<p>AI <b>생성</b> 이미지</p>", "ko"),                                # split by tags
    ("<p>An AI-Generated Image</p>", "en"), ("<p>AI生成画像</p>", "ja"), ("<p>KI-generiertes Bild</p>", "de"),
    ("<p>Image générée par IA</p>", "fr"), ("<p>Изображение создано ИИ</p>", "ru"),
])
def test_no_page_may_carry_the_dropped_label(body, lang):
    """Owner 2026-10-13 night ('AI 생성 이미지 표시는 다 빼'): the label may not come back on any page — with or
    without a picture on it — in any page language."""
    problems = art.page_problems(page(body, lang=lang), [], place=False)
    assert any("가 페이지에 있음" in p for p in problems), problems


def test_the_label_check_leaves_plain_words_alone():
    for text in ("이 사이트의 일러스트는 생성형 AI로 그렸습니다", "AI가 이 사이트 정보로 답합니다",
                 "The illustrations on this site were drawn with generative AI", "생성 이미지 파일"):
        assert art.page_problems(page(f"<p>{text}</p>"), [], place=False) == [], text


def test_page_rules_keep_art_off_place_pages_and_out_of_place_data():
    assert any("장소 페이지에 AI 그림" in p for p in art.page_problems(page(fig()), [], place=True))
    head = '<meta property="og:image" content="https://x.test/assets/art/og-ko-1200.jpg">'
    assert any("og:image" in p for p in art.page_problems(page("", head), [], place=True))
    place = {"@type": "TouristAttraction", "@id": "https://x.test/places/a/#place", "image": "/assets/art/a.webp"}
    assert any("장소 페이지 구조화 데이터" in p for p in art.page_problems(page(), [place], place=True))
    photo = {"@type": "WebPage", "primaryImageOfPage": {"@type": "ImageObject", "contentUrl": "/assets/art/a.webp"}}
    assert any("ImageObject" in p for p in art.page_problems(page(), [photo], place=False))


def test_page_rules_report_a_rendition_the_build_did_not_publish(tmp_path):
    assert any("빌드에 없음" in p for p in art.page_problems(page(fig()), [], False, tmp_path))
    (tmp_path / "assets" / "art").mkdir(parents=True)
    for ext in ("avif", "webp"):
        (tmp_path / "assets" / "art" / f"hero-autumn-640.{ext}").write_bytes(b"x")
    assert art.page_problems(page(fig()), [], False, tmp_path) == []


# ------------------------------------------------------------------ build: only used renditions; same site without art
def test_build_publishes_only_the_renditions_pages_use(tmp_path, monkeypatch):
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    for name in ("hero-autumn-640.avif", "hero-autumn-640.webp", "hero-autumn-1280.avif", "card-guide-400.webp"):
        (art_dir / name).write_bytes(tiny_picture())
    monkeypatch.setattr(art, "ART_DIR", art_dir)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.html").write_text(page(fig()), "utf-8")
    assert art.copy_used(out) == ["hero-autumn-640.avif", "hero-autumn-640.webp"]
    assert sorted(f.name for f in (out / "assets" / "art").iterdir()) == ["hero-autumn-640.avif",
                                                                           "hero-autumn-640.webp"]


def test_without_art_files_the_site_is_the_same(tmp_path, monkeypatch):
    """A slot whose files are missing renders exactly as the site did before AI art: the same bytes as a build
    without art.json — no band, no banner, no og:image fallback, nothing under /assets/art/."""
    def tree(out):
        return {str(f.relative_to(out)): f.read_bytes() for f in sorted(out.rglob("*")) if f.is_file()}
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    fake_art(data, tmp_path / "no-art", {                       # every kind of picture listed …
        "card-guide": {"slot": "home.card.guide", "files": False},
        "head-places": {"slot": "list.head.places", "size": (1536, 640), "files": False},
        "art-404": {"slot": "page.404", "files": False}, "art-empty": {"slot": "search.empty", "files": False},
        "og-ko": {"slot": "og.default", "langs": ["ko"], "files": False}})
    monkeypatch.setattr(art, "ART_DIR", tmp_path / "no-art")   # … but no rendition on disk
    build(data, tmp_path / "missing", "sample")
    (data / "art.json").unlink()
    build(data, tmp_path / "none", "sample")
    assert tree(tmp_path / "missing") == tree(tmp_path / "none")
    assert not (tmp_path / "missing" / "assets" / "art").exists()


def test_validate_rejects_art_misused_in_a_built_site(tmp_path):
    out = tmp_path / "out"
    build(SAMPLE, out, "sample")
    home = out / "index.html"
    home.write_text(home.read_text("utf-8").replace("</main>", f'<img src="/assets/art/x-640.webp" alt="x"></main>', 1),
                    "utf-8")
    place = next((out / "places").glob("*/index.html"))
    place.write_text(place.read_text("utf-8").replace("</main>", fig() + "</main>", 1), "utf-8")
    (out / "assets" / "style.css").write_text(".h{background:url(/assets/art/x.webp)}", "utf-8")
    errors = "\n".join(validate(SAMPLE, out, "sample")[0])
    assert "figure[data-art]" in errors and "장소 페이지에 AI 그림" in errors and "CSS 배경" in errors


# ------------------------------------------------------------------ tools/art_media.py (needs Pillow with AVIF)
def test_art_media_widths_never_upscale():
    from tools import art_media
    assert art_media.widths_for(1536, 1024) == [640, 1280, 1536]
    assert art_media.widths_for(2400, 1600) == [640, 1280, 1920]
    assert art_media.widths_for(1024, 1024) == [400, 800]
    assert art_media.widths_for(96, 64) == [96]
    assert art_media.widths_for(1536, 640, "head-places") == [400, 800, 1280, 1536]   # phones get a small file
    assert art_media.widths_for(1536, 1024, "camp-night") == [400, 800, 1280, 1536]
    for prefix in PHONE_WIDTH:                                       # every picture a phone shows at its width
        assert art_media.widths_for(1536, 1024, prefix + "x") == [400, 800, 1280, 1536], prefix
    for art_id in ("hero-autumn", "card-guide", "evkind-race", "month-01", "abroad-press", "art-404"):
        assert art_media.widths_for(1536, 1024, art_id) == [640, 1280, 1536], art_id
        assert art_media.widths_for(1024, 1024, art_id) == [400, 800], art_id


def test_art_media_tables_are_the_owners():
    """tools/art_media.py's crop and width tables, as the second picture list needs them (BANDS, PHONE_WIDTH above;
    the widths art.json _notes names)."""
    from tools import art_media
    assert art_media.CROPS == {p: (1536, 640) for p in BANDS}
    assert art_media.SMALL_FIRST == (PHONE_WIDTH, (400, 800, 1280, 1920))
    assert art_media.WIDTHS == {"landscape": (640, 1280, 1920), "square": (400, 800)}


def test_art_media_is_deterministic_keeps_committed_files_and_drops_stale(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image, features
    if not features.check("avif"):
        pytest.skip("Pillow without AVIF")
    from tools import art_media
    data, src = tmp_path / "data", tmp_path / "src"
    data.mkdir()
    src.mkdir()
    entry = {"file": "hero-test.png", "alt": "일러스트: 시험", "alt_en": "Illustration: test",
             "slot": "home.hero.autumn", "status": "개편 뒤 연결"}
    (data / "art.json").write_text(json.dumps({"images": {"hero-test": entry}}, ensure_ascii=False), "utf-8")
    im = Image.new("RGBA", (96, 64), (240, 200, 160, 255))
    im.putpixel((0, 0), (0, 0, 0, 230))                         # a semi-transparent edge pixel, as ChatGPT leaves
    im.save(src / "hero-test.png")
    one, two = tmp_path / "one", tmp_path / "two"
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(one)]) == 0
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(two), "--force"]) == 0
    names = sorted(f.name for f in one.iterdir())
    assert names == ["hero-test-96.avif", "hero-test-96.webp", "manifest.json"]
    assert all((one / n).read_bytes() == (two / n).read_bytes() for n in names)   # same original, same bytes
    assert art.data_problems(data, one) == []
    with Image.open(one / "hero-test-96.webp") as w:
        assert w.mode == "RGB"                                  # flattened, no alpha
    (src / "hero-test.png").unlink()                            # another computer: originals are not in git
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(one)]) == 0
    assert sorted(f.name for f in one.iterdir()) == names
    (data / "art.json").write_text(json.dumps({"images": {}, "held": {"hero-test": "다시"}}), "utf-8")
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(one)]) == 0
    assert sorted(f.name for f in one.iterdir()) == ["manifest.json"]
    assert json.loads((one / "manifest.json").read_text("utf-8")) == {}


# ------------------------------------------------------------------ the slots that are connected (C·D·E·F)
def test_og_fallback_never_reaches_a_place_page():
    found = {"og.default": {"id": "og-ko"}, "og.default-en": {"id": "og-en"}, "og.abroad": {"id": "og-abroad"}}
    assert art.og_fallback(found, "/places/seonyudo/") is None
    assert art.og_fallback(found, "/en/places/seonyudo/", "en") is None
    assert art.og_fallback(found, "/404.html") is None
    assert art.og_fallback(found, "/abroad/")["id"] == "og-abroad"
    assert art.og_fallback(found, "/about/")["id"] == "og-ko"
    assert art.og_fallback(found, "/places/")["id"] == "og-ko"           # the list, not a place
    assert art.og_fallback(found, "/en/guides/", "en")["id"] == "og-en"
    assert art.og_fallback({}, "/about/") is None                        # no picture: no og:image, as before


def test_connected_art_is_published_without_a_label_and_valid(tmp_path, monkeypatch):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    # one picture per connected family (C·D·E·F·I), the guide's and course's on the sample's own first id
    ids = art.data_ids(data)
    first = {fam: f"{fam.split('.')[0]}-test" for fam in ("guide.banner", "course.banner") if ids[fam]}
    # the 404 and empty-search pictures wait ('개편 뒤 연결', as on the first site: the mascot holds those places now)
    entries = {"head-places": {"slot": "list.head.places", "size": (1536, 640)},
               "art-404": {"slot": "page.404", "size": (1536, 1024), "status": "개편 뒤 연결"},
               "art-empty": {"slot": "search.empty", "status": "개편 뒤 연결"},
               "og-ko": {"slot": "og.default", "langs": ["ko"]}}
    if "guide.banner" in first:
        entries["camp-test"] = {"slot": f"guide.banner.{sorted(ids['guide.banner'])[0]}", "size": (1536, 1024),
                                "langs": ["ko"], "text": "비 오는 날 갈 곳"}
        first["guide.banner"] = "camp-test"
    if "course.banner" in first:
        entries["course-test"] = {"slot": f"course.banner.{sorted(ids['course.banner'])[0]}", "size": (1536, 640)}
        first["course.banner"] = "course-test"
    cfg = {"images": fake_art(data, tmp_path / "art", entries)}
    monkeypatch.setattr(art, "ART_DIR", tmp_path / "art")
    assert art.data_problems(data) == []
    camp = first.get("guide.banner")
    out = tmp_path / "out"
    build(data, out, "sample")
    found = art.slots(data)

    def html(path):
        return (out / path).read_text("utf-8")
    if "list.head.places" in found:                                      # D: the band above the list's H1
        page = html("places/index.html")
        band = page.split('data-art="head-places"', 1)[1].split("</figure>", 1)[0]
        assert band.startswith(' aria-hidden="true">')              # decorative: not read on every list
        assert "fetchpriority" not in band and "loading=" not in band   # first screen, not ahead of css and fonts
        assert 'alt="일러스트: ' in band and "<figcaption" not in band and "head-places-400.avif 400w" in band
        assert page.index('data-art="head-places"') < page.index('id="h-list"')
    if camp:                                                             # C: the guide's campaign card
        guide = html(next((out / "guides").glob("*/index.html")).relative_to(out))
        printed = cfg["images"][camp]["text"]
        printed = printed if isinstance(printed, str) else " ".join(printed)
        assert 'class="art art-camp"' in guide and printed in guide and "has-camp" in guide
    if first.get("course.banner"):                                       # I: the band above the course's H1
        course = html(next((out / "courses").glob("*/index.html")).relative_to(out))
        assert f'data-art="{first["course.banner"]}"' in course and 'class="wrap art-band-wrap"' in course
    if "page.404" in found:                                              # F: 404 and the empty search result
        assert 'data-art="art-404"' in html("404.html")
    if "search.empty" in found and (out / "search" / "index.html").exists():
        search = html("search/index.html")
        assert "<div data-empty-art hidden>" in search and 'data-art="art-empty"' in search
    if "og.default" in found:                                            # E: link preview of photo-less pages
        about = html("about/index.html")
        assert 'property="og:image" content="https://example.com/assets/art/og-ko-1200.jpg"' in about
        assert 'property="og:image:alt" content="일러스트: ' in about and 'og:image:width" content="1200"' in about
    for f in (out / "places").glob("*/index.html"):                       # a place keeps its photo, or none
        assert "/assets/art/" not in f.read_text("utf-8"), f
    published = {f.name for f in (out / "assets" / "art").iterdir()} if (out / "assets" / "art").exists() else set()
    assert published == art.used_files(out)                              # exactly what the pages use
    errors = validate(data, out, "sample")[0]
    assert errors == [], errors[:10]


# ------------------------------------------------------------------ A·B: the home's season picture and news-card pictures
def tiny_picture() -> bytes:
    """A tiny generated test image (WebP from Pillow; a fixed 1×1 WebP when Pillow is not installed)."""
    try:
        from PIL import Image
    except ImportError:
        return bytes.fromhex("524946461e000000574542505650384c110000002f000000000750f3fa77b9ff8188e87f0000")
    buf = io.BytesIO()
    Image.new("RGB", (6, 4), (254, 230, 203)).save(buf, "WEBP")
    return buf.getvalue()


def test_home_opening_and_news_cards_with_and_without_art(tmp_path, monkeypatch):
    """Spec 7, owner 2026-10-13 night: with a picture in art.json (home.card.<kind>) a news card without a photo shows
    it through figure() — alt '일러스트: ', width·height, lazy, no label; without one, the card shows its type icon.
    The opening is the photo opening either way: a season picture ('개편 뒤 연결' — home.hero is no slot any more) never
    shows, and no page carries the dropped label. Both builds pass validate."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    blob = tiny_picture()
    images, manifest = {}, {}
    for art_id, slot, size, status in (("hero-test", "home.hero.autumn", (1536, 1024), "개편 뒤 연결"),
                                       ("card-test-guide", "home.card.guide", (1024, 1024), "연결"),
                                       ("card-test-event", "home.card.event", (1024, 1024), "연결")):
        files = {fmt: f"{art_id}-400.{fmt}" for fmt in ("avif", "webp")}
        for name in files.values():
            (art_dir / name).write_bytes(blob)
        manifest[art_id] = {"w": size[0], "h": size[1], **{fmt: [[name, 400, len(blob)]] for fmt, name in files.items()}}
        images[art_id] = {"file": f"{art_id}.png", "alt": f"일러스트: 시험 그림 {art_id}",
                          "alt_en": f"Illustration: test picture {art_id}", "slot": slot, "status": status}
    (art_dir / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    (data / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    monkeypatch.setattr(art, "ART_DIR", art_dir)

    def home_parts(out):
        html = (out / "index.html").read_text("utf-8")
        news = html[html.index('<div class="ho-news">'):html.index('<section class="hq"')]
        guide = next(c for c in news.split('<article class="nc nc-')[1:] if c.startswith("guide"))
        return html, guide

    build(data, tmp_path / "with", "sample")
    html, guide = home_parts(tmp_path / "with")
    assert '<section class="ho"' in html and 'data-art="hero-test"' not in html   # the season picture: gone
    assert 'data-art="card-test-guide"' in guide and 'data-pic=' not in guide
    assert 'alt="일러스트: 시험 그림 card-test-guide"' in guide and "<figcaption" not in guide
    assert 'loading="lazy"' in guide and 'width="1024" height="1024"' in guide
    for f in (tmp_path / "with").rglob("*.html"):
        assert not art.dropped_labels(f.read_text("utf-8")), f
    assert sorted(f.name for f in (tmp_path / "with" / "assets" / "art").iterdir()) == \
        sorted(art.used_files(tmp_path / "with"))
    assert not any(n.startswith("hero-test") for n in art.used_files(tmp_path / "with"))
    assert validate(data, tmp_path / "with", "sample")[0] == []

    (data / "art.json").unlink()                                         # no picture: the type icon
    build(data, tmp_path / "without", "sample")
    html, guide = home_parts(tmp_path / "without")
    assert '<section class="ho"' in html and "data-art=" not in html
    # no picture: the kind's 3D picture by registry ID (the interim look until its file exists), never a photo
    assert 'data-pic="guide"' in guide and 'class="nc-frame nc-icof"' in guide
    assert not (tmp_path / "without" / "assets" / "art").exists()
    assert validate(data, tmp_path / "without", "sample")[0] == []
