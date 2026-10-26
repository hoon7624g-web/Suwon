"""An empty city (WP7, design 4 '빈 설정에서도 지켜야 할 것'): this city's site.json (data/suwon) with no data yet — no data file at
all, or every list file empty — builds and validates without an exception, an error or a warning; no page claims a
count of nothing ('0곳', '0편'); every path is ASCII; there is no English site; and production validation fails only
on the two values the operator still has to give (ga4_id, operator.contact). An inconsistent setting in site.json
(City.problems) is a validation error, never silently ignored."""
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from pipeline.build import State, build
from pipeline.validate import scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
CITY = ROOT / "data" / "suwon"   # this city: its site.json alone is copied, none of the files beside it
LISTS = ("places", "courses", "guides", "events", "themes")
PRODUCTION_ERRORS = ["[site.json] ga4_id 없음 — 신규 사이트 GA4 설치는 확정 사항",
                     "[site.json] operator.contact(정정 요청 연락처) 없음"]
ZERO_CLAIM = re.compile(r"(?<![0-9.,])0\s?(?:곳|편|개|건|회|장|명)")


def empty_city(tmp_path: Path, files: str) -> Path:
    """This city's site.json alone ('none') or with every list file holding [] ('empty'). A city before its first
    collection has no place to measure from yet: the two settings that name collected places (dist_anchors, the 권역
    anchors' place_id) are emptied — with them, the build rightly warns that each named place is missing."""
    data = tmp_path / f"data-{files}"
    data.mkdir()
    site = json.loads((CITY / "site.json").read_text("utf-8"))
    site["dist_anchors"] = []
    site["regions"] = {**site.get("regions", {}), "anchors": []}
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), "utf-8")
    if files == "empty":
        for name in LISTS:
            (data / f"{name}.json").write_text("[]\n", "utf-8")
    return data


def html_pages(out: Path) -> list[Path]:
    return sorted(out.rglob("*.html"))


@pytest.mark.parametrize("files", ["none", "empty"])
def test_empty_city_preview_has_no_error_warning_or_empty_claim(tmp_path, files):
    data = empty_city(tmp_path, files)
    assert sorted(p.name for p in data.iterdir()) == (["site.json"] if files == "none" else
                                                      sorted(["site.json", *(f"{n}.json" for n in LISTS)]))
    S = State(data, "preview")
    assert S.warnings == [] and S.entities == [] and S.slug_problems == []
    out = tmp_path / f"preview-{files}"
    build(data, out, "preview")
    errors, warns, _ = validate(data, out, "preview")
    assert errors == [] and warns == []
    pages = html_pages(out)
    assert {p.relative_to(out).as_posix() for p in pages} >= {"index.html", "about/index.html", "404.html"}
    for page in pages:
        text = page.read_text("utf-8")
        assert not ZERO_CLAIM.findall(text), (page, ZERO_CLAIM.findall(text))
        scan = scan_file(page)
        assert not ZERO_CLAIM.search(scan.title + " " + scan.meta.get("description", ""))
    # every path is ASCII: files, canonical / og:url, sitemap, internal links
    assert [p for p in out.rglob("*") if not p.relative_to(out).as_posix().isascii()] == []
    for page in pages:
        scan = scan_file(page)
        for url in [scan.canonical, scan.meta.get("og:url", ""), *(h for h in scan.hrefs if h.startswith("/"))]:
            assert urlsplit(url).path.isascii() and "%" not in urlsplit(url).path, (page, url)
    site_url = json.loads((CITY / "site.json").read_text("utf-8"))["site_url"].rstrip("/")
    assert scan_file(out / "index.html").canonical == f"{site_url}/"
    for loc in re.findall(r"<loc>(.*?)</loc>", (out / "sitemap.xml").read_text("utf-8")):
        assert loc.isascii() and "%" not in loc, loc
    # no English site: no folder, no hreflang alternate, no language menu, no link to /en/ (an outside link to an
    # English page — the emergency notice's VisitKorea pages in site.json — may say hreflang="en" on its <a>)
    assert not (out / "en").exists()
    assert not [p for p in pages if re.search(r'<link[^>]*hreflang=', p.read_text("utf-8"))
                or "data-langmenu" in p.read_text("utf-8") or 'href="/en/' in p.read_text("utf-8")]


@pytest.mark.parametrize("files", ["none", "empty"])
def test_empty_city_production_fails_only_on_the_operator_values(tmp_path, files):
    data = empty_city(tmp_path, files)
    # without the operator's two values (the 2026-10-11 operator set operator.contact and a GA4 launch exception in
    # this city's site.json; take them out again) production fails on exactly those two
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["operator"]["contact"] = ""
    site["ga4_id"] = ""
    site.pop("launch_exceptions", None)
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    out = tmp_path / f"production-{files}"
    build(data, out, "production")
    errors, warns, _ = validate(data, out, "production")
    assert errors == PRODUCTION_ERRORS
    assert warns == []
    assert not (out / "en").exists()
    assert [p for p in out.rglob("*") if not p.relative_to(out).as_posix().isascii()] == []
    for page in html_pages(out):
        assert not ZERO_CLAIM.findall(page.read_text("utf-8")), page
    # with the operator's values (this city's live site.json), nothing else stands in the way of a production build
    (tmp_path / "filled").mkdir()
    filled = empty_city(tmp_path / "filled", files)
    out2 = tmp_path / f"production-filled-{files}"
    build(filled, out2, "production")
    assert validate(filled, out2, "production")[0] == []


def test_an_inconsistent_city_setting_is_a_validation_error(tmp_path):
    data = empty_city(tmp_path, "none")
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["address_aliases"] = [*site["address_aliases"], site["address_aliases"][-1]]   # one alias twice
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    out = tmp_path / "preview"
    build(data, out, "preview")
    errors, _, _ = validate(data, out, "preview")
    assert errors == [f"[site.json] 도시 설정 오류: address_aliases 중복: {site['address_aliases'][-1]}"]
