"""KOGL-1 derivatives (pipeline/media.py, tools/kogl1_media.py, templates/_media.html.j2) and the behaviour layer's
first-screen rule (templates/assets/motion.js, site.js, css/65-states.css): static checks, no browser.

Merge r3-wpb (deliberate changes): B2's motion.css is the stylesheet partial css/65-states.css (one built
style.css); the story dimming is B1's navy layer (css/40-cinema.css) with a licence guard instead of a filter;
count-ups are gone from motion.js; the shared macros (_ui.html.j2) print photos through _media.picture.

Apple skin (r3-apple, deliberate changes): css/40-cinema.css is replaced by css/40-showcase.css; the pinned island
gallery is gone (native scroll-snap row + buttons; its KOGL-1 drift moves only with the reader's own scroll, from
rest), and the story no longer pins or dims (a CSS sticky stage where only KOGL-1 photos scale)."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

from pipeline import city as citymod
from pipeline import media
from pipeline.schema import PHOTO_SOURCES
from pipeline.build import make_env

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates" / "assets"
METRO_SITE = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))


def photo(url, kind):
    return {"url": url, "type": kind, "w": None, "h": None, "alt": "사진", "credit": "한국관광공사", "lic": "", "th": None}


# ------------------------------------------------------------------ derivatives: KOGL-1 only, on disk, within budget
def tiny_media(tmp_path):
    """A media folder with one KOGL-1 photo's derivatives and its manifest entry; (folder, manifest, licences)."""
    d = tmp_path / "media"
    d.mkdir()
    for name, size in (("11-480.avif", 7), ("11-940.avif", 9), ("11-480.webp", 8)):
        (d / name).write_bytes(b"x" * size)
    man = {"https://x/11_image2_1.jpg": {"w": 940, "h": 627, "avif": [["/assets/media/11-480.avif", 480, 7],
                                                                      ["/assets/media/11-940.avif", 940, 9]],
                                        "webp": [["/assets/media/11-480.webp", 480, 8]]}}
    return d, man, {"https://x/11_image2_1.jpg": "KOGL-1", "https://x/33_image2_1.jpg": "KOGL-3"}


def test_manifest_check_holds_kogl1_files_within_budget(tmp_path):
    d, man, lic = tiny_media(tmp_path)
    assert media.manifest_problems(man, lic, d) == []
    assert media.manifest_problems({}, lic, tmp_path / "none") == []        # Q15: no photos yet — nothing to check
    # a KOGL-3 photo (변경금지) is never re-encoded, even with its files in place
    (d / "33-480.avif").write_bytes(b"y")
    (d / "33-480.webp").write_bytes(b"y")
    k3 = {**man, "https://x/33_image2_1.jpg": {"w": 940, "h": 705, "avif": [["/assets/media/33-480.avif", 480, 1]],
                                               "webp": [["/assets/media/33-480.webp", 480, 1]]}}
    problems = media.manifest_problems(k3, lic, d)
    assert len(problems) == 1 and "33_image2_1.jpg" in problems[0] and "제1유형이 아닌" in problems[0]
    # files the manifest does not list would ship: a stray derivative is caught (here the KOGL-3 ones)
    stray = media.manifest_problems(man, lic, d)
    assert sorted(stray) == ["manifest에 없는 파생 이미지 파일(남은 파일): 33-480.avif",
                             "manifest에 없는 파생 이미지 파일(남은 파일): 33-480.webp"]
    (d / "33-480.avif").unlink()
    (d / "33-480.webp").unlink()
    # never upscaled, the listed size on disk, a format present, within the budget
    up = {u: {**e, "avif": e["avif"] + [["/assets/media/11-1200.avif", 1200, 3]]} for u, e in man.items()}
    (d / "11-1200.avif").write_bytes(b"x" * 3)
    assert any("원본 너비" in p for p in media.manifest_problems(up, lic, d))
    (d / "11-1200.avif").unlink()
    (d / "11-940.avif").write_bytes(b"x" * 10)
    assert any("크기가 manifest와 다름" in p for p in media.manifest_problems(man, lic, d))
    (d / "11-940.avif").write_bytes(b"x" * 9)
    no_webp = media.manifest_problems({u: {**e, "webp": []} for u, e in man.items()}, lic, d)
    assert any("webp 파일 없음" in p for p in no_webp) and any("남은 파일): 11-480.webp" in p for p in no_webp)
    assert any("상한" in p for p in media.manifest_problems(man, lic, d, budget=10))
    assert media.MEDIA_BUDGET == 15 * 1024 * 1024


def test_repository_media_holds_only_listed_kogl1_derivatives():
    """The repository as it is: a missing or empty manifest is allowed (Q15: no city photo yet), and then no .avif /
    .webp may be left in templates/assets/media; with a manifest, every rule of manifest_problems holds against the
    licences stored in the data."""
    licences = {i["url"]: i.get("license") for f in sorted((ROOT / "data").glob("*/places.json"))
                for e in json.loads(f.read_text("utf-8")) for i in e.get("images") or [] if i.get("source") in PHOTO_SOURCES}
    assert media.manifest_problems(media.load_manifest(), licences, media.MEDIA_DIR) == []


def test_attach_adds_srcsets_to_kogl1_only():
    k1, k3 = "https://x/1_image2_1.jpg", "https://x/3_image2_1.jpg"
    man = {u: {"w": 940, "h": 627, "avif": [["/assets/media/1-480.avif", 480, 1], ["/assets/media/1-940.avif", 940, 2]],
               "webp": [["/assets/media/1-480.webp", 480, 1]]} for u in (k1, k3)}
    S = SimpleNamespace(entities=[{"_photos": [photo(k1, 1), photo(k3, 3)]}])
    media.attach(S, man)
    a, b = S.entities[0]["_photos"]
    assert a["avif"] == "/assets/media/1-480.avif 480w, /assets/media/1-940.avif 940w" and a["w"] == 940 and a["h"] == 627
    assert b["avif"] == "" and b["webp"] == "" and b["w"] is None  # a mistaken KOGL-3 entry never reaches a page


def test_crop_and_zoom_slots_refuse_kogl3():
    e = {"id": "place-1", "slug": "isle", "name": "섬", "_path": "/places/isle/", "kind": "attraction",
         "_photos": [photo("https://x/a.jpg", 3), photo("https://x/b.jpg", 1)]}
    S = SimpleNamespace(city=citymod.of(METRO_SITE), entities=[e], warnings=[])
    assert media.pick_photo(S, ["place-1", 0], need_k1=True) is None and "place-1 #0" in S.warnings[-1]
    assert media.pick_photo(S, ["place-1", 0], need_k1=False)["url"] == "https://x/a.jpg"
    assert media.pick_photo(S, ["place-1", 5], need_k1=True)["url"] == "https://x/b.jpg"  # the last photo when fewer
    assert media.pick_photo(S, {"place_id": "place-1", "n": 1})["slug"] == "isle"
    # a slot names a place by its id only — a slug may still change before publication (design: place id keys)
    assert media.pick_photo(S, ["isle", 5]) is None and "장소 없음 isle" in S.warnings[-1]
    assert media.pick_photo(S, ["없음", 0]) is None
    assert media.pick_photo(S, ["place-1", "0"]) is None and "형식 오류" in S.warnings[-1]   # n must be a number
    assert list(media.wanted(S)) == []  # no home slot configured; the lead photo is KOGL-3: nothing to derive
    assert media.slot_photos(S) == {"hero": [], "cover": None, "story": {}, "gallery": []}


def test_home_slots_come_from_site_json_by_place_id():
    site = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))
    k1 = {"id": "place-1", "slug": "a", "name": "가", "_path": "/places/a/", "kind": "attraction",
          "_photos": [photo("https://x/1.jpg", 1), photo("https://x/3.jpg", 3)]}
    k3 = {"id": "place-3", "slug": "b", "name": "나", "_path": "/places/b/", "kind": "attraction",
          "_photos": [photo("https://x/9.jpg", 3)]}
    site = {**site, "home": {**site["home"], "media": {"cover": ["place-1", 0], "hero": [["place-1", 0], ["place-3", 0]],
                                                       "gallery": [["place-3", 0], ["place-gone", 0]]},
                             "story": [{"id": "ch-1", "photo": ["place-3", 0]}, {"id": "ch-2"}]}}
    S = SimpleNamespace(city=citymod.of(site), entities=[k1, k3], warnings=[])
    slots = media.slot_photos(S)
    assert slots["cover"]["url"] == "https://x/1.jpg" and slots["cover"]["slug"] == "a"
    assert [p["url"] for p in slots["hero"]] == ["https://x/1.jpg"]          # a cropped slide refuses KOGL-3
    assert [p["url"] for p in slots["gallery"]] == ["https://x/9.jpg"]       # KOGL-3 shown whole; a gone place left out
    assert slots["story"] == {"ch-1": {**k3["_photos"][0], "place": "나", "path": "/places/b/", "slug": "b",
                                       "id": "place-3", "kind": "attraction"}}
    assert any("place-gone" in w for w in S.warnings) and any("place-3 #0" in w for w in S.warnings)
    assert media.wanted(S) == {"https://x/1.jpg": "cover"}     # the cover slot wins (kogl1_media: up to 1280w)
    # null cover and empty lists (a new city before its home is configured): no slot, no warning
    bare = {**site, "home": {**site["home"], "media": {"cover": None, "hero": [], "gallery": []}, "story": []}}
    empty = SimpleNamespace(city=citymod.of(bare), entities=[], warnings=[])
    assert media.slot_photos(empty) == {"hero": [], "cover": None, "story": {}, "gallery": []} and empty.warnings == []


def test_the_home_and_the_derivatives_read_one_slot_decision():
    """pipeline/media.py alone decides the home's photo slots: the home shows media.slot_photos (present has no copy)
    and tools/kogl1_media.py derives media.wanted from the same references — so every KOGL-1 photo a slot shows has
    its derivative listed, and a KOGL-3 one never does (tests/fixtures/gunsan_subset configures gallery and story)."""
    from pipeline import present
    from pipeline.build import State

    S = State(ROOT / "tests" / "fixtures" / "gunsan_subset", "preview")
    slots = present.home_vm(S)["slots"]
    assert slots == media.slot_photos(S) and not hasattr(present, "home_photo_slots")
    shown = [p for p in [slots["cover"], *slots["hero"], *slots["gallery"], *slots["story"].values()] if p]
    want = media.wanted(S)
    assert {p["type"] for p in shown} == {1, 3}
    assert all(p["url"] in want for p in shown if p["type"] == 1)
    assert not [p for p in shown if p["type"] == 3 and p["url"] in want]
    assert S.warnings == []


def test_picture_macro_emits_size_and_licence_hooks():
    env = make_env()
    md = env.get_template("_media.html.j2").module
    k1 = {**photo("https://x/1.jpg", 1), "w": 940, "h": 627, "avif": "/a-480.avif 480w", "webp": "/a-480.webp 480w"}
    k3 = {**photo("https://x/3.jpg", 3), "w": 940, "h": 705, "avif": "", "webp": ""}
    html = str(md.picture(k1, "100vw", True, "", False, True, True))
    assert html.startswith("<picture>") and 'type="image/avif" srcset="/a-480.avif 480w"' in html
    assert 'src="https://x/1.jpg" width="940" height="627"' in html and 'fetchpriority="high"' in html
    assert 'data-kogl="1" data-kb' in html
    lazy = str(md.picture(k1, "100vw", False, "", True))
    assert 'data-srcset="/a-480.avif 480w"' in lazy and 'data-src="https://x/1.jpg"' in lazy and ' src=' not in lazy
    html3 = str(md.picture(k3, "100vw", False, "", False, False, True))
    assert html3.startswith("<img") and "<picture>" not in html3 and 'data-kogl="3"' in html3 and "data-kb" not in html3
    assert "imagesrcset" in str(md.preload(k1)) and str(md.preload(k3)) == ""


# ------------------------------------------------------------------ behaviour layer: nothing on the first screen
def test_motion_only_touches_elements_below_the_first_screen():
    js = (ASSETS / "motion.js").read_text("utf-8")
    body = js[js.index("(function () {"):]
    # reduced motion returns before anything is defined or loaded
    assert body.index('matchMedia("(prefers-reduced-motion: reduce)").matches) return;') < body.index("function all(")
    targets = re.search(r"var T = \{(.*?)\n    \};", js, re.S).group(1)
    for line in [l for l in targets.splitlines() if l.strip()]:
        assert "below" in line, line  # every scroll target list is filtered to below-the-first-screen elements
    go = js[js.index("var go = function ()"):]
    for call in re.findall(r"\n\s+(splitHeads|reveals|photos|counts|parallax|routes)\(g, (?:ST, )?(\w+)\(", go):
        assert call[1] == "keep", call  # re-checked when the libraries arrive
    assert "below(box)" in js[js.index("function story("):js.index("function story(") + 800]
    drift = js[js.index("function drift("):js.index("function smooth(")]
    assert ".filter(k1)" in drift and "rest[k]" in drift  # KOGL-1 only, identity at rest (moves with the reader)
    hero = js[js.index("function hero("):js.index("function splitHeads(")]
    assert not re.search(r"\bg\.(set|from|fromTo|to)\(", hero) and "gsap" not in hero  # cross-fade over a visible photo
    assert "motion-pending" not in js


def test_site_js_and_state_css_never_hide_content_by_default():
    site = re.sub(r"/\*.*?\*/|//[^\n]*", "", (ASSETS / "site.js").read_text("utf-8"), flags=re.S)
    for word in ("opacity", "clipPath", "clip-path", "visibility"):
        assert word not in site, word
    css = (ASSETS / "css" / "65-states.css").read_text("utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    allowed = ("[data-slide]", "html:not(.js)", "[data-mq-dup]", "html.js [data-marquee]:has",
               "[data-hero-pause], [data-mq-pause]")
    for sel, decl in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if re.search(r"opacity:\s*0[;\s]|visibility:\s*hidden|display:\s*none", decl):
            sel = " ".join(sel.split())
            if re.fullmatch(r"(from|to|[\d.]+%)", sel):  # keyframe steps (the page transition's old snapshot)
                continue
            assert any(sel.startswith(a) or a in sel for a in allowed), sel
    assert "[data-slide].is-on { opacity: 1; visibility: visible;" in " ".join(css.split())
    # a KOGL-3 photo is never scaled or dimmed: the story stage scales a chapter photo only when it is KOGL-1, and
    # nothing dims a photo (no --dim layer, no brightness filter)
    showcase = " ".join((ASSETS / "css" / "40-showcase.css").read_text("utf-8").split())
    motion = (ASSETS / "motion.js").read_text("utf-8")
    assert 'return i && k1(i) ? i : null;' in motion and "--dim" not in motion
    assert "brightness" not in css and "brightness" not in showcase
    # pause buttons work from the first paint (the marquee moves before motion.js arrives)
    assert '"[data-mq-pause]"' in site and '"[data-hero-pause]"' in site


def test_map_module_keeps_the_markup_contract():
    js = (ASSETS / "map.js").read_text("utf-8")
    assert '.map[data-points]' in js and 'data-leaflet-js' in js and 'data-lenis-prevent' in js   # Leaflet + OSM (operator 2026-10-16)
    site = (ASSETS / "site.js").read_text("utf-8")
    assert 'attach("map.js")' in site and 'attach("course.js")' in site and 'attach("search.js")' in site


def test_shared_macros_print_photos_through_the_media_helpers():
    env = make_env()
    ui = env.get_template("_ui.html.j2").module
    k1 = {**photo("https://x/1.jpg", 1), "w": 940, "h": 627, "avif": "/a-480.avif 480w", "webp": "/a-480.webp 480w",
          "lic": "공공누리 제1유형", "name": "섬"}
    k3 = {**photo("https://x/3.jpg", 3), "w": 940, "h": 705, "avif": "", "webp": "", "lic": "공공누리 제3유형", "name": "섬"}
    one = str(ui.img(k1, "100vw", True, "kb", False, True))
    assert one.startswith("<picture>") and 'class="t1 kb"' in one and 'data-kogl="1"' in one
    assert "data-kb" not in one  # ui.img never asks for the CSS slow zoom (ui.showcase zooms with the scroll)
    three = str(ui.figure(k3))
    assert "<picture>" not in three and 'class="t3"' in three and 'data-kogl="3"' in three
    assert "출처: 한국관광공사 · 공공누리 제3유형" in three and "data-reveal-ph" in three


def test_opening_credit_lines_follow_their_slides_and_no_phone_dock_remains():
    js = (ASSETS / "motion.js").read_text("utf-8")
    hero = js[js.index("function hero("):js.index("function splitHeads(")]
    assert 'all("[data-cap]", box)' in hero and 'caps.forEach(function (c, k) { c.classList.toggle("is-on", k === idx); })' in hero
    assert '"[data-hero-bars] > *, .hero-bars > i"' in hero
    site = (ASSETS / "site.js").read_text("utf-8")
    # the phones' dock is gone (Apple direction, 2026-10-08): the local bar's pill (ui.lnav) carries the route, so
    # no fixed bottom bar, no dock script and no dock rules remain
    assert "data-dock" not in site and "setDock" not in site
    css = "".join(f.read_text("utf-8") for f in (ASSETS / "css").glob("*.css"))
    assert ".dock" not in css and "[data-dock]" not in css
