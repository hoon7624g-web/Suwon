"""The place page's '주변·함께 가기' chapter (owner 2026-10-14: 시각화·모션; templates/_near.html.j2, css/71-nearby.css,
present.route_segs / near_row / near_scale / small_thumb, locales.NEAR_WORDS): the official courses through a place as
segments (courses that share the same neighbours at the same straight-line distances grouped, each course a chip that
links to its stop), the nearby rows on one stepped straight-line scale with the place's own small photo or its kind
icon, guide and event cards. Distances are straight lines and say so; no walking times; no AI art; KOGL-3 thumbnails
are never cropped; every language gets the same markup."""
import datetime as dt
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import locales as LC
from pipeline import present
from pipeline.build import State, build, entity_ctx, event_last_day, make_env, site_css

ROOT = Path(__file__).resolve().parent.parent
SAMPLE, CITY = ROOT / "data" / "sample", ROOT / "data" / "suwon"
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module")
def city_state():
    """The city's production State (real data) and the view of every published place on an official course."""
    S = State(CITY, "production")
    vms = {e["slug"]: present.place_vm(S, e, entity_ctx(e, S)) for e in S.entities
           if any(e["slug"] in {st.get("place_slug") for st in c.get("stops") or []} for c in S.courses)}
    return S, vms


def stop(name, t=None, prev_m=None, next_m=None, path=""):
    return {"name": name, "short": name, "t": t, "path": path, "prev_m": prev_m, "next_m": next_m}


def course(display, stops, here):
    return {"display": display, "path": f"/courses/{display}/", "stops": stops,
            "i": next(i for i, s in enumerate(stops) if s["t"] is here)}


# ---------------------------------------------------------------- present.route_segs
def test_route_segs_groups_shared_neighbours():
    a, h, b, x, y = ({"name": n} for n in ("A", "H", "B", "X", "Y"))
    boards = [
        course("other", [stop("X", x), stop("H", h, 300, 120), stop("Y", y)], h),           # its own neighbours
        course("one", [stop("Q"), stop("A", a), stop("H", h, 906.3, 398.7), stop("B", b)], h),
        course("two", [stop("A", a), stop("H", h, 906.3, 398.7), stop("B", b), stop("Z")], h),
        course("three", [stop("A", a, path="/places/a/"), stop("H", h, 906.3, 398.7), stop("B", b)], h),
        course("alone", [stop("H", h)], h),
    ]
    segs = present.route_segs(boards, present.dist, lambda s: s["t"]["name"] if s.get("t") else s["short"])
    # three courses with the same neighbours and legs are one segment, first (most courses), then first appearance
    assert [[c["display"] for c in g["courses"]] for g in segs] == [["one", "two", "three"], ["other"], ["alone"]]
    assert sorted(c["display"] for g in segs for c in g["courses"]) == sorted(b["display"] for b in boards)
    shared = segs[0]
    assert shared["prev"] == {"name": "A", "path": "", "d": "910m", "same": False}
    assert shared["next"] == {"name": "B", "path": "", "d": "400m", "same": False}
    assert [(c["n"], c["N"], c["p"]) for c in shared["courses"]] == [(3, 4, 0.667), (2, 4, 0.333), (2, 3, 0.5)]
    assert all(c["path"] == f"/courses/{c['display']}/" for g in segs for c in g["courses"])
    alone = segs[2]
    assert alone["prev"] is None and alone["next"] is None and alone["courses"][0]["p"] == 0


def test_route_segs_ends_and_unmeasured_legs():
    h, b = {"name": "H"}, {"name": "B"}
    seg = present.route_segs([course("c", [stop("H", h, None, None), stop("B", b, None, None, "/places/b/"),
                                           stop("섬")], h)], present.dist, lambda s: s["short"])[0]
    assert seg["prev"] is None                                     # the course starts here
    assert seg["next"] == {"name": "B", "path": "/places/b/", "d": "", "same": False}   # no coordinates: no distance, never a guess
    mid = present.route_segs([course("c", [stop("H0", {"name": "x"}), stop("B", b, None, None), stop("섬")], b)],
                             present.dist, lambda s: s["short"])[0]
    assert mid["next"] == {"name": "섬", "path": "", "d": "", "same": False}     # a stop without its own page: no link


def test_route_segs_repeated_stops(city_state):
    """A course that passes the place on consecutive stops (C코스 은파호수공원야경 → 은파호수공원) is one visit whose
    neighbours are the stops around the run — never the place itself; a later visit (B코스 장자도 6 · 8 · 13) is
    another segment of the same course."""
    h, a, b, c = ({"name": n} for n in ("H", "A", "B", "C"))
    stops = [stop("A", a, None, 500), stop("H1", h, 500, 0.0), stop("H2", h, 0.0, 300), stop("B", b, 300, 2200),
             stop("H3", h, 2200, 1200), stop("C", c, 1200, None)]
    segs = present.route_segs([{"display": "c", "path": "/c/", "stops": stops, "at": [1, 2, 4]}], present.dist,
                              lambda s: s["t"]["name"])
    assert [(g["prev"]["name"], g["prev"]["d"], g["next"]["name"], g["next"]["d"], g["courses"][0]["n"]) for g in segs] == [
        ("A", "500m", "B", "300m", 2), ("B", "2.2km", "C", "1.2km", 5)]
    assert all(g["prev"]["name"] != "H" and g["next"]["name"] != "H" for g in segs)
    # real data: no segment of a place on a course points at the place itself, and every visit is kept
    S, vms = city_state
    assert vms
    for slug, vm in vms.items():
        e = S.ent_by_slug[slug]
        ends = [x for g in vm["route_segs"] for x in (g["prev"], g["next"]) if x]
        assert all(x["name"] != e["name"] and x["path"] != e["_path"] for x in ends), slug
        assert sum(len(g["courses"]) for g in vm["route_segs"]) >= len(vm["boards"]), slug


def test_route_segs_never_cross_two_options_of_a_day(city_state):
    """The first site's QA 2026-10-15 F09-b: the first stop of a '(2안)' block after a '(1안)' block is a break
    (s['brk']) — no neighbour across it, never one run, and that side reads NEAR_WORDS 'branch', not the course's
    start or end. Real data: no segment of a place on a course names a stop across such a break."""
    h, a, b = ({"name": n} for n in ("H", "A", "B"))
    stops = [stop("A", a, None, 500), stop("H1", h, 500, None), {**stop("H2", h, None, 300), "brk": True},
             stop("B", b, 300, None)]
    segs = present.route_segs([{"display": "c", "path": "/c/", "stops": stops, "at": [1, 2]}], present.dist,
                              lambda s: s["t"]["name"])
    assert [(g["prev"] and g["prev"]["name"], g["next"] and g["next"]["name"], g["prev_branch"], g["next_branch"])
            for g in segs] == [("A", None, False, True), (None, "B", True, False)]
    env = make_env()
    nb = env.get_template("_near.html.j2").module
    out = str(nb.segs(segs, "x", LC.NEAR_WORDS["ko"], "코스", "H"))
    assert out.count("다른 안") == 2 and "코스 시작" not in out and "코스 끝" not in out
    assert all(bool(HANGUL.search(w["branch"])) == (c == "ko") for c, w in LC.NEAR_WORDS.items())
    S, vms = city_state
    for slug, vm in vms.items():
        for g in vm["route_segs"]:
            for c in g["courses"]:
                cv = next(v for v in S.course_vms.values() if v["display"] == c["display"])
                here = cv["stops"][c["n"] - 1]
                if here["brk"]:
                    assert g["prev"] is None and g["prev_branch"], (slug, c)
                nxt = cv["stops"][c["n"]] if c["n"] < len(cv["stops"]) else None
                if nxt is not None and nxt["brk"]:
                    assert g["next"] is None and g["next_branch"], (slug, c)


# ---------------------------------------------------------------- one stepped straight-line scale per page
def test_near_scale_steps():
    assert present.near_scale([70]) == 100
    assert present.near_scale([12, 243]) == 250
    assert present.near_scale([1177, 60]) == 2000
    assert present.near_scale([2600], 2000) == 2000 and present.near_scale([]) == 100
    for ms in ([70, 12], [243, 100, 5], [1177, 2600]):
        scale = present.near_scale(ms, 2000)
        assert all(0 <= present.near_fill(m, scale) <= 1 for m in ms)
    assert present.dist(0) == "같은 좌표" and present.near_fill(0, 100) == 0 and present.near_fill(6, 100) == 0
    assert present.near_fill(70, 100) == 0.7


def test_small_thumb_never_original():
    k3 = {"url": "https://x/a_image2_1.jpg", "w": 1024, "h": 768, "type": 3, "lic": "공공누리 제3유형(변경금지)", "alt": "a",
          "th": None, "webp": ""}
    assert present.small_thumb(k3) is None                         # no small copy: no picture, never the original
    assert present.small_thumb({**k3, "th": {"url": "https://x/a_image3_1.jpg", "w": None, "h": None}}) is None
    th = present.small_thumb({**k3, "th": {"url": "https://x/a_image3_1.jpg", "w": 160, "h": 120}})
    assert (th["url"], th["w"], th["h"], th["type"], th["lic"]) == ("https://x/a_image3_1.jpg", 160, 120, 3, k3["lic"])
    k1 = {**k3, "type": 1, "webp": "/m/a-320.webp 320w, /m/a-640.webp 640w"}
    assert present.small_thumb(k1)["url"] == "/m/a-320.webp" and present.small_thumb(k1)["h"] == 240
    # a small copy squeezed to another shape (the provider's 300×200 of a 940×705 original): never shown — a KOGL-3
    # photo falls back to the kind icon, a KOGL-1 one to its own proportional derivative
    squeezed = {"url": "https://x/a_image3_1.jpg", "w": 300, "h": 200}
    assert present.small_thumb({**k3, "w": 940, "h": 705, "th": squeezed}) is None
    assert present.small_thumb({**k1, "w": 940, "h": 705, "th": squeezed})["url"] == "/m/a-320.webp"
    assert present.small_thumb({**k3, "w": 940, "h": 627, "th": squeezed})["url"] == squeezed["url"]   # 1.4992 vs 1.5
    assert present.small_thumb({**k3, "w": None, "h": None, "th": squeezed}) is None   # the original unmeasured
    # a nearby row whose place has only an original falls back to its kind icon
    S = State(SAMPLE, "sample")
    t = S.ent_by_slug["sample-food-a"]
    row = present.near_row(S, {**t, "_photos": [k3]}, {"name": t["name"], "kind": "food", "distance_m": 320})
    assert row["photo"] is None and row["icon"] == (t.get("_visual") or ("", "pin"))[1]
    assert present.near_row(S, None, {"name": "밖", "kind": "food", "href": "https://map", "distance_m": 9})["icon"] == "bowl"


# ---------------------------------------------------------------- the built chapter (sample data + photos)
def data_with(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    geo = {"sample-0001": (35.9870443, 126.7111681), "sample-0002": (35.9886113, 126.7125570),
           "sample-0101": (35.9901, 126.7151), "sample-0201": (35.9851, 126.7091)}
    sizes = {}
    for p in places:
        if p["id"] in geo:
            p["geo"] = {"lat": geo[p["id"]][0], "lng": geo[p["id"]][1], "source": "TourAPI"}
    for p in places:
        if p["id"] == "sample-0002":   # a KOGL-1 photo with the provider's measured small copy
            url = "https://tong.visitkorea.or.kr/cms/resource/11/1_image2_1.jpg"
            p["images"] = [{"url": url, "license": "KOGL-1", "source": "TourAPI", "credit": "한국관광공사", "alt": "초원사진관"}]
            sizes[url] = [1024, 683, 412000]
            sizes[url.replace("_image2_1", "_image3_1")] = [160, 107, 9000]
        if p["id"] == "sample-0101":   # a KOGL-3 photo without a small copy: the row shows the kind icon
            url = "https://tong.visitkorea.or.kr/cms/resource/22/2_image2_1.jpg"
            p["images"] = [{"url": url, "license": "KOGL-3", "source": "TourAPI", "credit": "한국관광공사", "alt": "숙소"}]
            sizes[url] = [1000, 750, 517000]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    (data / "image_sizes.json").write_text(json.dumps(sizes), "utf-8")
    events = json.loads((data / "events.json").read_text("utf-8"))
    events[0]["place_slug"] = "chowon-photo-studio"
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    return data


def block(html):
    i = html.index('data-block="nearby"')
    return html[i:html.index("</section>", i)]


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


@pytest.fixture(scope="module")
def sample_site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("near")
    data = data_with(tmp)
    out = tmp / "site"
    build(data, out, "sample")
    return {"data": data, "out": out, "S": State(data, "sample")}


def page(site, slug):
    return (site["out"] / "places" / slug / "index.html").read_text("utf-8")


def test_place_nearby_chapter(sample_site):
    S = sample_site["S"]
    for slug in ("gyeongam-railroad-village", "chowon-photo-studio"):
        e = S.ent_by_slug[slug]
        b = block(page(sample_site, slug))
        # every course through the place is a chip linking to its stop (#s<n>, course_click), one per board
        boards = [(c, next(s for s in S.course_vms[c["slug"]]["stops"] if s["t"] is e)) for c in e["_courses"]]
        hrefs = re.findall(r'<a class="crs" href="([^"]+)" data-track="course_click" data-place="([^"]+)"', b)
        assert sorted(h for h, _ in hrefs) == sorted(f"{c['_path']}#s{s['n']}" for c, s in boards) and boards
        assert {p for _, p in hrefs} == {e["id"]}
        assert b.count('aria-current="location"') == b.count('class="nb-seg"') >= 1
        assert re.search(r'<ol class="seg-line" aria-label="경유지 순서" data-draw>(?:<li[^>]*>.*?</li>)+</ol>', b, re.S)
        for d in re.findall(r'<span class="seg-d tn">(.*?)<i class="seg-wire"', b, re.S):
            assert "직선" in text(d)
        t = text(b)
        assert "직선" in t and "도보" not in t and "걸어서" not in t and not re.search(r"\d\s*분", t)
        assert "data-art" not in b
        # the nearby rows: hrefs, data-track and data-place as the nearby list gives them (sights, then stays and
        # food, each by straight-line distance); a place without a page keeps its map-search link
        want = []
        for n in sorted(e.get("nearby") or [], key=lambda n: (n["kind"] != "attraction", n.get("distance_m") or 0)):
            tt = S.ent_by_slug.get(n.get("internal_slug") or "")
            want.append((tt["_path"] if tt else None, {"stay": "stay_click", "food": "food_click"}.get(n["kind"], "nearby_click")))
        got = re.findall(r'<a class="nr-nm" href="([^"]+)"( rel="noopener")? data-track="([^"]+)" data-place="([^"]+)"', b)
        assert [(None if ext else h, tr) for h, ext, tr, _ in got] == want
        assert all(h.startswith("https://map.naver.com/") for h, ext, _, _ in got if ext)
        assert {p for _, _, _, p in got} == {e["id"]}
    # the course's first stop: '코스 시작' in place of a previous stop, on a dashed stub; the next stop is a link
    b = block(page(sample_site, "gyeongam-railroad-village"))
    assert ('<li class="seg-n prev end"><i class="seg-dot" aria-hidden="true"></i><span class="seg-nm seg-end">코스 시작</span>'
            '<i class="seg-wire is-open" aria-hidden="true"></i></li>') in b
    assert '<span class="vh">이곳 </span><span class="seg-nm">' in b
    assert '<a class="seg-nm" href="/places/chowon-photo-studio/">초원사진관</a>' in b
    # a middle stop: the next stop has no page (span) and no coordinates (the line draws, unlabelled)
    c = block(page(sample_site, "chowon-photo-studio"))
    assert '<span class="vh">다음 경유지 </span><span class="seg-nm">선유도</span>' in c
    here = re.search(r'<li class="seg-n here".*?</li>', c, re.S).group(0)
    assert "seg-wire" in here and "class=\"seg-d " not in here
    # the leg into this place reads 이곳까지 (screen readers), the leg out of it 다음 경유지까지
    assert re.search(r'<span class="seg-d tn"><span class="vh">이곳까지 </span>직선 \d+m</span>', c)
    assert re.search(r'<span class="seg-d tn"><span class="vh">다음 경유지까지 </span>직선 \d+m</span>', b)
    # a chip: the name, the position for screen readers, n/N and its track as one no-wrap piece
    assert re.search(r'<span class="crs-at" aria-hidden="true"><span class="crs-n tn">\d+/\d+</span><i class="crs-pos" style="--p:[\d.]+"></i></span></a>', c)
    # thumbnails: the small copy only, lazy, sized, licence on the element; the KOGL-3 original falls back to the icon
    th = present.small_thumb(S.ent_by_slug["chowon-photo-studio"]["_photos"][0])
    b = block(page(sample_site, "gyeongam-railroad-village"))
    imgs = re.findall(r'<span class="nr-th t(\d)"><img ([^>]+)></span>', b)
    assert imgs == [("1", f'src="{th["url"]}" width="160" height="107" alt="" loading="lazy" decoding="async" data-kogl="1"')]
    assert "2_image2_1.jpg" not in b and "1_image2_1.jpg" not in b
    assert b.count('class="nr-th nr-ico"') == 3
    assert "막대 끝 = 직선 1.0km · 반경 2.0km 안 · 직선거리 순" in text(b) and "사진 출처: 한국관광공사 · 공공누리 제1유형" in text(b)
    # under 10 m: '같은 좌표' with no bar and no '직선' (not a distance)
    assert re.findall(r'<i style="--f:([\d.]+)">', b) == ["0.32", "0.48", "0.65"]
    assert '<span class="nr-d tn is-same">같은 좌표</span></li>' in b
    assert '<span class="nr-d tn"><span class="vh">직선 </span>320m</span>' in b
    # the guide card and the event card (its dates, 진행·예정 or 지난 회차 on the build date)
    assert 'data-track="guide_click" data-place="sample-0002"' in c and "이곳이 포함된 가이드" in c
    sr = S.ent_by_slug["chowon-photo-studio"]["_events"][0]
    tag = "지난 회차" if event_last_day(sr["newest"]) < dt.date.today().isoformat() else "진행·예정"
    assert "이곳에서 열리는 행사" in c and f'href="{sr["_path"]}"' in c
    assert f'<span class="tn">{present.event_row(sr["newest"], city=S.city)["range"]}</span> <span class="xc-tag' in c and tag in text(c)


def test_related_rows_skip_the_nearby_ones(city_state):
    """Real data (the places on a course): no visit lost between the course boards and the segments, a nearby row is
    never again a 'name runs on' row, one stepped scale per page, and a row's picture is its place's small copy.
    (The first site's per-place counts stay there.)"""
    S, vms = city_state
    by_path = {x["_path"]: x for x in S.entities}
    rows = []
    for slug, vm in vms.items():
        assert sum(len(g["courses"]) for g in vm["route_segs"]) >= len(vm["boards"]), slug
        near = vm["near_sights"] + vm["near_biz"]
        assert not {r["name"] for r in near} & {r["name"] for r in vm["rel_rows"]}, slug
        assert not near or (vm["near_scale"] in present.NEAR_STEPS and all(0 <= r["f"] <= 1 for r in near)), slug
        rows += near
    assert rows
    for r in rows:   # a row's picture is its own place's first photo, in its small copy, never the original
        t = by_path[r["href"]]
        if r["photo"]:
            assert r["photo"]["url"] != t["_photos"][0]["url"] and r["photo"] == present.small_thumb(t["_photos"][0])
        else:
            assert not t["_photos"] or present.small_thumb(t["_photos"][0]) is None


# ---------------------------------------------------------------- stylesheet: KOGL-3 thumbnails stay whole
def test_kogl3_thumb_not_cropped():
    css = site_css()
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    t3 = [body for sel, body in rules if ".nr-th.t3 img" in sel]
    assert t3 and all("cover" not in body and "transform" not in body and "scale" not in body for body in t3)
    # only KOGL-1 thumbnails scale on hover; the global guard keeps every KOGL-3 image whole
    assert any(".nr:hover .nr-th.t1 img" in sel for sel, _ in rules)
    assert not any(".nr-th.t3" in sel and ("hover" in sel) for sel, _ in rules)
    guard = next(body for sel, body in rules if sel.strip().startswith("img.t3")).replace(" ", "")
    assert "object-fit:contain!important" in guard and "transform:none!important" in guard
    assert ".onroute" not in css and ".near-cols2" not in css


# ---------------------------------------------------------------- words in every language
def test_near_words_complete():
    codes = ("ko",) + LC.ORDER
    assert set(LC.NEAR_WORDS) == set(codes)
    keys = set(LC.NEAR_WORDS["ko"])
    for code in codes:
        w = LC.NEAR_WORDS[code]
        assert set(w) == keys, code
        for k, v in w.items():
            assert v.strip() and v.format(d="910 m", n=3, N=11, lic="KOGL", label="X", name="X"), (code, k)
            assert bool(HANGUL.search(v)) == (code == "ko"), (code, k, v)
        assert "{d}" in w["leg"] and "{d}" in w["scale"] and "{n}" in w["pos"] and "{N}" in w["pos"]
        assert "{lic}" in w["credit"] and all("{n}" in w[k] for k in ("more_segs", "more_guides", "more_events"))
        assert "{label}" in w["varies"]
        # the relation line and the parts heading name one place each (pipeline/relations.py)
        assert all(w[k].count("{name}") == 1 for k in ("part_of", "same_building", "parts")), code
    assert LC.NEAR_WORDS["ko"]["credit"].startswith("사진 출처: 한국관광공사")   # as the list and guide footers


def test_intl_place_nearby_markup():
    """The same macros in every language: the same classes and structure as Korean, the words of the version,
    no Hangul (names here are the version's)."""
    env = make_env()
    nb = env.get_template("_near.html.j2").module

    def render(code):
        w = LC.NEAR_WORDS[code]
        loc = LC.get(code) if code != "ko" else None
        d = (lambda m: present.dist(m)) if code == "ko" else loc.dist
        segs = [{"prev": {"name": "Alpha", "path": "/a/", "d": d(910)}, "next": {"name": "Beta", "path": "", "d": ""},
                 "courses": [{"display": "Course 1", "path": "/c1/", "n": 6, "N": 11, "p": 0.5},
                             {"display": "Course 2", "path": "/c2/", "n": 1, "N": 2, "p": 0}]},
                {"prev": None, "next": None, "courses": [{"display": "Course 3", "path": "/c3/", "n": 1, "N": 1, "p": 0}]}] * 2
        rows = [{"name": "Gamma", "href": "/g/", "internal": True, "kind": "attraction", "type": "Museum", "m": 70,
                 "d": d(70), "f": 0.7, "track": "nearby_click", "closed": {"main": "Every Mon", "closed": True}, "fact": None,
                 "photo": {"url": "/t.jpg", "w": 160, "h": 107, "type": 3}, "icon": "pin"},
                {"name": "Delta", "href": "/s/", "internal": True, "kind": "stay", "type": "Hotel", "m": 243,
                 "d": d(243), "f": 1, "track": "stay_click", "closed": None, "fact": {"label": "Check-in", "main": "15:00"},
                 "photo": None, "icon": "bed"},
                {"name": "Eps", "href": "/e/", "internal": True, "kind": "food", "type": "Food", "m": 4, "d": d(4), "f": 0,
                 "track": "food_click", "closed": {"label": "Closed", "varies": True}, "fact": None, "photo": None,
                 "icon": "bowl"}]
        cards = [{"label": "Night", "title": "Night views", "path": "/n/"}] * 5
        events = [{"name": "Festival", "path": "/e/", "range": "Oct 10", "past": False},
                  {"name": "Fair", "path": "/f/", "range": "", "past": True}]
        return "".join(str(x) for x in (
            nb.segs(segs, "id-1", w, "Courses", "Here place"),
            nb.groups([("Sights", rows, "icon-sights"), ("Stay", rows, "icon-stay")], "id-1", w, True),
            nb.cards(cards, "id-1", w, "guide_click", w["more_guides"]),
            nb.cards(events, "id-1", w, "", w["more_events"])))

    shape = lambda h: (re.findall(r'class="([^"]+)"', h), re.findall(r"<(/?[a-z0-9]+)", h),
                       re.findall(r'(?:href|data-track|data-place|aria-current|data-kogl|loading)="([^"]*)"', h))
    ko = render("ko")
    assert ko.count('class="nb-seg"') == 4 and ko.count('aria-current="location"') == 4
    assert ko.count("<details") == 2 and "다른 구간 보기 (1)" in ko and "가이드 더 보기 (1)" in ko
    for code in LC.ORDER:
        h = render(code)
        assert shape(h) == shape(ko), code
        assert not HANGUL.search(h), (code, HANGUL.findall(h)[:5])
        assert LC.NEAR_WORDS[code]["leg"].format(d=LC.get(code).dist(910)) in h
        assert LC.NEAR_WORDS[code]["varies"].format(label="Closed") in h and LC.get(code).same_xy in h
        assert h.count('class="nr-bar"') == 4    # no bar for the row on the same coordinates


def test_row_values_and_dates():
    """A closed day two sources give differently reads '<label> 출처마다 다름' (never one picked); a closed day's red
    square stays with its first word; an event card from another year carries its year; units and 'same coordinates'
    in every language."""
    S = State(CITY, "production")
    varies = [e for e in S.entities if e.get("kind") != "stay" and (present.slot_value(e, "closed") or {}).get("conflict")]
    if not varies:   # none in the city's data today: one place given a second source's different closed day
        e = dict(next(x for x in S.entities if x.get("kind") != "stay"))
        e["facts"] = {**(e.get("facts") or {}), "restdate": "매주 월요일"}
        e["fact_alternatives"] = {"restdate": [{"value": "매주 화요일", "provider": "다른 출처", "checked_at": "2026-10-16"}]}
        varies = [e]
    assert (present.slot_value(varies[0], "closed") or {}).get("conflict")
    row = present.near_row(S, varies[0], {"name": varies[0]["name"], "kind": varies[0]["kind"], "distance_m": 120})
    assert row["closed"] == {"label": present.slot_value(varies[0], "closed")["label"], "varies": True}
    env = make_env()
    nb = env.get_template("_near.html.j2").module
    h = str(nb.rows([{**row, "f": 0.5, "href": "/x/", "track": "nearby_click"}], "id", LC.NEAR_WORDS["ko"]))
    assert f'{row["closed"]["label"]} 출처마다 다름' in text(h)
    assert str(present.closed_head("매주 토요일~일요일 / 법정공휴일")) == '<span class="nw">매주</span> 토요일~일요일\u00a0/ 법정공휴일'
    assert str(present.closed_head("毎週月–水曜日／公休日")) == '<span class="nw">毎週</span>月–水曜日／公休日'
    assert str(present.glue_dots("해설·군산 A&B")) == '해<span class="nw">설·</span>군산 A&amp;B'
    r = {"range": "10. 30.(목)–11. 2.(일)", "start": "2025-10-30", "contested": []}
    assert present.card_range(r, "2026-10-14") == "2025. 10. 30.(목)–11. 2.(일)"
    assert present.card_range({**r, "start": "2026-10-30"}, "2026-10-14") == r["range"]
    assert present.card_range({**r, "range": "기간 출처마다 다름", "contested": ["period"]}, "2026-10-14") == "기간 출처마다 다름"
    assert LC.get("ru").dist(430) == "430 м" and LC.get("ru").dist(1234) == "1,2 км" and LC.get("en").dist(4) == "same coordinates"
    assert all(LC.get(c).dist(0) and "0 m" not in LC.get(c).dist(0) for c in LC.ORDER)
