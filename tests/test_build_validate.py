"""End-to-end: build the bundled sample and validate it."""
import json
import shutil
from pathlib import Path

from pipeline.build import State, build
from pipeline.validate import PageScan, seat_only_parking_problems, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


def test_sample_builds_and_passes_sample_rules(tmp_path):
    out = tmp_path / "dist-sample"
    stats = build(SAMPLE, out, "sample")
    assert stats["entities"] == 5 and stats["excluded_entities"] == 1     # draft is never built
    assert (out / "places" / "gyeongam-railroad-village" / "index.html").exists()
    assert not (out / "places" / "sample-draft").exists()
    assert "Disallow: /" in (out / "robots.txt").read_text("utf-8")        # sample is never indexable
    errors, warns, s = validate(SAMPLE, out, "sample")
    assert errors == [], errors
    assert s["original_shown"] == 2 and s["original_linked"] == 1


def test_unknown_licence_text_never_appears(tmp_path):
    out = tmp_path / "d"
    build(SAMPLE, out, "sample")
    page = (out / "places" / "chowon-photo-studio" / "index.html").read_text("utf-8")
    assert "이용조건 확인 전 원문입니다" not in page
    assert "원문 보기" in page


def test_jsonld_matches_visible_text(tmp_path):
    out = tmp_path / "d"
    build(SAMPLE, out, "sample")
    html = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
    graph = json.loads(raw)["@graph"]
    node = next(n for n in graph if n.get("@type") == "TouristAttraction")
    assert node["name"] == "경암동 철길마을"
    assert node["description"] in html

    # P0-3: an old-province address and a 0507 number build clean; every page passes the visibility rule
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["facts"].update(address="전라북도 군산시 경촌4길 14", infocenter="0507-1302-6070")
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "fixture"
    build(data, out, "sample")
    page = out / "places" / "gyeongam-railroad-village" / "index.html"
    html = page.read_text("utf-8")
    node = next(n for n in json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])["@graph"]
                if n.get("@id", "").endswith("#place"))
    assert node["address"] == {"@type": "PostalAddress", "addressRegion": "전북특별자치도", "addressLocality": "군산시",
                               "streetAddress": "경촌4길 14", "addressCountry": "KR"}
    assert "전북특별자치도 군산시 경촌4길 14" in html and "전라북도" not in html
    assert node["telephone"] == "+82-507-1302-6070" and "0507-1302-6070" in html
    errors, _, _ = validate(data, out, "sample")
    assert errors == [], errors
    # a description that the page does not show is caught
    raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
    doc = json.loads(raw)
    next(n for n in doc["@graph"] if n.get("@id", "").endswith("#place"))["description"] = "화면에 없는 설명입니다"
    page.write_text(html.replace(raw, json.dumps(doc, ensure_ascii=False)), "utf-8")
    errors, _, _ = validate(data, out, "sample")
    assert any("구조화 데이터가 화면과 다름" in x and "화면에 없는 설명입니다" in x for x in errors), errors


def test_production_rules_catch_sample_leftovers(tmp_path):
    out = tmp_path / "prod"
    build(SAMPLE, out, "production")
    errors, _, _ = validate(SAMPLE, out, "production")
    text = "\n".join(errors)
    assert "site_url" in text and "ga4_id" in text and "자리표시" in text


def test_refuses_to_wipe_foreign_folder(tmp_path):
    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("x")
    try:
        build(SAMPLE, foreign, "sample")
        raised = False
    except SystemExit:
        raised = True
    assert raised and (foreign / "keep.txt").exists()
    shutil.rmtree(foreign)


def test_empty_draft_guides_stay_in_review_data_but_not_visitor_routes(tmp_path):
    from tools.make_review_list import make_report

    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    guides_path = data / "guides.json"
    guides = json.loads(guides_path.read_text("utf-8"))
    guides += [
        {"id": "empty-plan", "slug": "empty-plan", "title": "작성할 가이드", "status": "draft",
         "summary": "제목과 계획만 있는 초안", "body": [{"heading": "예정", "text": "  "}],
         "items": [], "faq": [], "sources": []},
        {**guides[0], "id": "readable-draft", "slug": "readable-draft", "status": "draft"},
    ]
    guides_path.write_text(json.dumps(guides, ensure_ascii=False), "utf-8")
    before = {p: p.read_bytes() for p in data.glob("*.json")}
    out = tmp_path / "preview"
    result = build(data, out, "preview")
    assert result["guides"] == 2
    assert not (out / "guides" / "empty-plan").exists()
    assert (out / "guides" / "readable-draft" / "index.html").exists()
    for p in list(out.rglob("*.html")) + [out / "sitemap.xml", out / "llms.txt"]:
        assert "/guides/empty-plan/" not in p.read_text("utf-8"), p
    review, errors, counts = make_report(data)
    assert counts["가이드"] == 2 and not errors
    assert "empty-plan" in review and "미리보기 미생성" in review
    assert "[/guides/empty-plan/]" not in review
    assert "[/guides/readable-draft/]" in review
    assert all(p.read_bytes() == contents for p, contents in before.items())


# ---------------------------------------------------------------- URL paths and slugs (design 2.5)
def non_ascii(out: Path) -> list[str]:
    return [p.relative_to(out).as_posix() for p in out.rglob("*") if not p.relative_to(out).as_posix().isascii()]


def copy_sample(tmp_path, places=None, events=None):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    for name, value in (("places.json", places), ("events.json", events)):
        if value is not None:
            (data / name).write_text(json.dumps(value, ensure_ascii=False), "utf-8")
    return data


def test_every_sample_path_is_ascii_and_the_event_follows_its_stored_slug(tmp_path):
    from urllib.parse import urlsplit
    from pipeline.validate import URL_PATH, _sitemap_locs
    out = tmp_path / "s"
    build(SAMPLE, out, "sample")
    assert (out / "events" / "sample-event" / "index.html").exists()      # events.json `slug`, not the name
    assert non_ascii(out) == []
    locs = _sitemap_locs(out)
    assert "https://example.com/events/sample-event/" in locs
    assert all(URL_PATH.match(urlsplit(u).path) for u in locs), locs


def test_a_stored_slug_is_never_renamed_and_a_bad_one_is_an_error(tmp_path):
    places = json.loads((SAMPLE / "places.json").read_text("utf-8"))
    places[1]["slug"] = "초원사진관"                       # a Hangul slug in the data: kept as it is, and an error
    places[5]["slug"] = places[0]["slug"]                 # the draft's stored slug duplicates a published one
    data = copy_sample(tmp_path, places)
    out = tmp_path / "s"
    stats = build(data, out, "sample")
    assert stats["slug_problems"]["count"] == 2
    assert (out / "places" / "초원사진관" / "index.html").exists()
    errors, _, _ = validate(data, out, "sample")
    text = "\n".join(errors)
    assert "저장된 slug 형식 오류: '초원사진관'" in text and "저장된 slug 중복: gyeongam-railroad-village" in text
    assert "주소 경로 규칙 위반" in text and "canonical https://example.com/places/%EC%B4%88" in text
    assert "비ASCII 파일·폴더 이름(주소 경로가 됨): places/초원사진관" in text
    assert "[sitemap.xml] 주소 경로 규칙 위반" in text and "[llms.txt] 주소 경로 규칙 위반" in text


def test_a_published_record_needs_its_stored_slug_in_production(tmp_path):
    places = json.loads((SAMPLE / "places.json").read_text("utf-8"))
    events = json.loads((SAMPLE / "events.json").read_text("utf-8"))
    del places[2]["slug"]                                  # 은파호수공원: the build makes one from the name
    del events[0]["slug"]
    data = copy_sample(tmp_path, places, events)
    out = tmp_path / "s"
    build(data, out, "sample")
    assert (out / "places" / "eunpahosugongwon" / "index.html").exists() and non_ascii(out) == []
    assert (out / "events" / "gunsan-haengsa-a" / "index.html").exists()
    errors, warns, _ = validate(data, out, "sample")
    assert errors == [], errors                            # preview / sample: a warning
    assert sum("저장된 slug가 없어" in w for w in warns) == 2
    out = tmp_path / "prod"
    build(data, out, "production")
    errors, _, _ = validate(data, out, "production")
    why = "공개(published) 기록에 저장된 slug가 없어 빌드가 만든 주소 — 공개 주소는 데이터의 slug로 고정해야 함"
    assert [x for x in errors if "저장된 slug가 없어" in x] == [
        f"[/places/eunpahosugongwon/] {why}", f"[/events/gunsan-haengsa-a/] {why}"]


def test_an_empty_list_page_is_noindex_and_left_out_in_production(tmp_path):
    places = [p for p in json.loads((SAMPLE / "places.json").read_text("utf-8")) if p["kind"] != "attraction"]
    data = copy_sample(tmp_path, places, [])
    out = tmp_path / "prod"
    build(data, out, "production")
    page = (out / "places" / "index.html").read_text("utf-8")
    assert '<meta name="robots" content="noindex, follow">' in page and "0곳" not in page.split("</title>")[0]
    sitemap = (out / "sitemap.xml").read_text("utf-8")
    assert "https://example.com/places/<" not in sitemap and "https://example.com/stays/<" in sitemap
    q10 = lambda errs: [x for x in errs if "0곳인 목록" in x or "noindex 페이지" in x]
    assert q10(validate(data, out, "production")[0]) == []
    (out / "places" / "index.html").write_text(page.replace('<meta name="robots" content="noindex, follow">', ""),
                                               "utf-8")
    assert q10(validate(data, out, "production")[0]) == [
        "[/places/] 기록이 0곳인 목록 페이지에 noindex 없음 — 답이 없는 페이지는 색인하지 않음"]
    # a noindex page in sitemap.xml is caught too
    (out / "places" / "index.html").write_text(page, "utf-8")
    (out / "sitemap.xml").write_text(sitemap.replace(
        "</urlset>", "  <url><loc>https://example.com/places/</loc></url>\n</urlset>"), "utf-8")
    assert q10(validate(data, out, "production")[0]) == [
        "[sitemap.xml] noindex 페이지가 들어 있음: https://example.com/places/"]


def test_list_filters_hubs_and_icons_come_from_site_json(tmp_path):
    from pipeline import city as city_mod
    from pipeline.build import ATTRACTION_GROUPS, category_group, list_filters
    sample = city_mod.of(json.loads((SAMPLE / "site.json").read_text("utf-8")))
    metro = city_mod.of(json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8")))
    groups, mountain = list_filters(sample)
    assert groups[0] == ("박물관·전시", ("박물관", "전시관", "근대건축관"))       # the sample's own list
    assert mountain.search("오성산") and not mountain.search("군산") and not mountain.search("문화유산")
    groups, mountain = list_filters(metro)                                       # nothing configured
    assert groups == ATTRACTION_GROUPS and mountain.pattern == r"(?<!유)산(?=\s|$)"
    assert mountain.search("한빛산") and not mountain.search("문화유산")
    a = lambda name, category="관광지": {"kind": "attraction", "name": name, "category": category}
    assert category_group(a("한빛산"), groups, mountain) == "자연·야외"
    assert category_group(a("한빛 근대건축관"), groups, mountain) == "테마 여행지"   # a city's own word, not the engine's
    # the list's hub guide (site.json list_hubs) and a theme's icon (themes.json visual)
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["list_hubs"] = {"attraction": {"guide_id": "guide-sample-1", "label": "차 없이 다니는 하루"}}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    out = tmp_path / "s"
    build(data, out, "sample")
    places = (out / "places" / "index.html").read_text("utf-8")
    assert '<a href="/guides/no-car-day-trip/" data-track="guide_click">차 없이 다니는 하루' in places
    assert 'class="list-hub"' not in (out / "food" / "index.html").read_text("utf-8")      # no hub configured
    S = State(data, "sample")
    assert {e["slug"]: e["_visual"] for e in S.entities}["gyeongam-railroad-village"] == ("alley", "lamp")
    assert validate(data, out, "sample")[0] == []


def test_a_site_without_an_original_source_builds_and_says_nothing_about_one(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["source"] = {"name": "", "name_en": "", "url": "", "collected_at": "", "kogl": ""}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    out = tmp_path / "s"
    build(data, out, "sample")
    llms = (out / "llms.txt").read_text("utf-8")
    assert "원문 출처" not in llms and "방문 정보마다 출처를 적었습니다. 운영: 에이아이오투오." in llms
    assert validate(data, out, "sample")[0] == []
    # a page's own original keeps its source's name; without one (and no site source) the link names its domain
    from pipeline.build import entity_ctx, source_labels
    S = State(data, "sample")
    e = S.ent_by_slug["chowon-photo-studio"]
    assert entity_ctx(e, S)["sources"][0]["label"] == "군산시 문화관광 원문"
    e["original"] = {**e["original"], "source_name": ""}
    assert entity_ctx(e, S)["sources"][0]["label"] == "gunsan.go.kr 원문"
    assert source_labels(e, S.site) == {"https://www.gunsan.go.kr/tour": "gunsan.go.kr"}


def test_metro_postal_address_names_the_district_as_locality():
    from pipeline import jsonld
    metro = json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8"))
    pa = lambda raw: {k: v for k, v in jsonld.postal_address(raw, metro).items() if k not in ("@type", "addressCountry")}
    assert pa("대구광역시 중구 동성로2길 80 (삼덕동1가)") == {"addressRegion": "대구광역시", "addressLocality": "중구",
                                                     "streetAddress": "동성로2길 80 (삼덕동1가)"}
    assert pa("대구광역시 달성군 화원읍 사문진로 1") == {"addressRegion": "대구광역시", "addressLocality": "달성군",
                                                 "streetAddress": "화원읍 사문진로 1"}
    # the national rename (군위군, 2023-07-01) is what the page shows, so it is what the markup splits
    assert pa("경상북도 군위군 군위읍 군청로 10") == {"addressRegion": "대구광역시", "addressLocality": "군위군",
                                               "streetAddress": "군위읍 군청로 10"}
    assert pa("대구광역시 샘플대로 9") == {"addressRegion": "대구광역시", "streetAddress": "샘플대로 9"}   # no 구·군
    assert pa("대구 수성구 무학로 42") == {"streetAddress": "대구 수성구 무학로 42"}       # an alias: kept whole
    assert pa("대구광역시 중구청로 5") == {"addressRegion": "대구광역시", "streetAddress": "중구청로 5"}  # not a word
    # the sample (a 시 under a 도) keeps today's markup
    sample = json.loads((SAMPLE / "site.json").read_text("utf-8"))
    assert jsonld.postal_address("전북특별자치도 군산시 경촌4길 14", sample) == {
        "@type": "PostalAddress", "addressRegion": "전북특별자치도", "addressLocality": "군산시",
        "streetAddress": "경촌4길 14", "addressCountry": "KR"}


def test_seat_count_alone_is_never_shown_as_parking():
    """validate.seat_only_parking_problems: a '30석' value under 주차 / 주차·좌석 is an error, under 좌석 it is not;
    a seats-only place must name 주차 in both '확인 필요' lines."""
    e = {"facts": {"parking_seats": "30석"}}

    def page(dt, need="주차", value="30석"):
        p = PageScan()
        p.feed(f'<p class="kf-need">확인 필요: {need}</p><section data-block="facts"><dl><div><dt>{dt}</dt>'
               f'<dd data-key="parking_seats">{value}</dd></div></dl><p class="need"><b>확인 필요</b> {need}</p></section>')
        return p

    assert seat_only_parking_problems(e, page("좌석")) == []
    assert len(seat_only_parking_problems(e, page("주차·좌석"))) == 1
    assert len(seat_only_parking_problems(e, page("주차"))) == 1
    assert len(seat_only_parking_problems(e, page("좌석", need="쉬는 날"))) == 2
    # both halves, or a parking value of its own: nothing to report
    assert seat_only_parking_problems({"facts": {"parking_seats": "20대/30석"}}, page("주차·좌석", "", "20대/30석")) == []
    assert seat_only_parking_problems({"facts": {"parking_seats": "30석", "parking": "가능"}}, page("좌석", need="")) == []


# the sample city's box and its tourism portal map's default point, as site.json gives them (geo_bounds,
# geo_default_point: city values, never in code)
SAMPLE_GEO = {"geo_bounds": [35.70, 36.16, 125.93, 127.00], "geo_default_point": [35.96761, 126.73684]}


def _state(tmp_path, edit, site_edit=None):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    edit({p["id"]: p for p in places})
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    if site_edit:
        site = json.loads((data / "site.json").read_text("utf-8"))
        (data / "site.json").write_text(json.dumps({**site, **site_edit}, ensure_ascii=False), "utf-8")
    return State(data, "sample")


CITY = {"source": "군산시 문화관광", "url": "https://www.gunsan.go.kr/tour/m2096/view/305391", "checked_at": "2026-10-16"}


def test_validate_checks_every_published_point(tmp_path):
    """geo_problems: numbers inside the region's box (site.json geo_bounds), never the city portal map's default point
    (site.json geo_default_point), a source, and for a source other than TourAPI the page and the day it was read
    (errors); three places at one point with different addresses (warning). A TourAPI point and a complete city
    portal point pass. Without geo_bounds / geo_default_point those two checks are skipped, the others stay."""
    from pipeline.validate import geo_problems

    def edit(by):
        by["sample-0001"]["geo"] = {"lat": 36.5, "lng": 126.72, "source": "TourAPI"}             # out of the box
        by["sample-0002"]["geo"] = {"lat": 35.96761, "lng": 126.73684, "source": "TourAPI"}      # the default point
        by["sample-0003"]["geo"] = {"lat": 35.95, "lng": 126.69}                                 # no source
        by["sample-0101"]["geo"] = {"lat": 35.97, "lng": 126.70, "source": "군산시 문화관광"}     # no url, no day
        by["sample-0201"]["geo"] = {"lat": 35.98, "lng": "x", "source": "TourAPI"}               # not a number
        by["sample-0999"]["geo"] = {"lat": 99.0, "lng": 126.7}                                   # a draft: not checked
    errors, warns = geo_problems(_state(tmp_path, edit, SAMPLE_GEO))
    assert len(errors) == 6 and warns == [], errors
    for pid, words in (("sample-0001", "범위"), ("sample-0002", "기본점"), ("sample-0003", "geo.source"),
                       ("sample-0101", "geo.url"), ("sample-0101", "geo.checked_at"), ("sample-0201", "숫자가 아님")):
        assert any(x.startswith(pid) and words in x for x in errors), (pid, words)

    def fine(by):
        for i, pid in enumerate(("sample-0001", "sample-0002", "sample-0003")):
            by[pid]["geo"] = {"lat": 35.98, "lng": 126.72, "source": "TourAPI"}       # one point …
            by[pid]["facts"]["address"] = f"전북특별자치도 군산시 경촌4길 {10 + i}"   # … three addresses
        by["sample-0101"]["geo"] = {"lat": 35.97, "lng": 126.70, **CITY}
    errors, warns = geo_problems(_state(tmp_path / "b", fine, SAMPLE_GEO))
    assert errors == [] and len(warns) == 1 and "주소가 다른 장소 3곳" in warns[0], warns
    # no box and no default point configured: the out-of-box and default-point records are not reported, the rest is
    errors, _ = geo_problems(_state(tmp_path / "c", edit))
    assert len(errors) == 4 and not any(x.startswith(("sample-0001", "sample-0002")) for x in errors), errors


def test_validate_checks_whose_points_a_nearby_list_names(tmp_path):
    """nearby_provenance_problems: a list with providers must name exactly the providers of the place's point and
    every listed place's, in its list and its line (errors); a list stored before providers were recorded whose line
    misses one is one warning naming the place."""
    from pipeline.validate import nearby_provenance_problems
    tour = {"source": "TourAPI"}
    listed = lambda slug: {"name": slug, "kind": "attraction", "distance_m": 10, "internal_slug": slug}  # noqa: E731
    one, both = ["한국관광공사 TourAPI"], ["한국관광공사 TourAPI", "군산시 문화관광"]

    def edit(by):
        by["sample-0001"].update(geo={"lat": 35.98, "lng": 126.72, **tour}, nearby=[listed("chowon-photo-studio")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표", "providers": one})
        by["sample-0002"].update(geo={"lat": 35.981, "lng": 126.72, **CITY}, nearby=[listed("gyeongam-railroad-village")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표", "providers": both})
        by["sample-0003"].update(geo={"lat": 35.982, "lng": 126.72, **tour}, nearby=[listed("chowon-photo-studio")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표"})      # stored before providers
        by["sample-0101"].update(geo={"lat": 35.983, "lng": 126.72, **tour}, nearby=[listed("eunpa-lake-park")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표", "providers": one})
    errors, warns = nearby_provenance_problems(_state(tmp_path, edit))
    assert len(errors) == 2, errors
    assert errors[0].startswith("sample-0001") and "providers" in errors[0]          # it lists the 군산시 point
    assert errors[1].startswith("sample-0002") and "provider '한국관광공사 TourAPI 좌표'" in errors[1]
    assert len(warns) == 1 and "1곳" in warns[0] and "sample-0101" not in warns[0], warns
