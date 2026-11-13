"""Course source integrity, preservation, exact matching and duplicate counts."""
from copy import deepcopy
import csv
import hashlib
import json

import pytest

from tools import import_gunsan_courses as courses
from tools.gunsan_parse import parse_courses


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def html(name="사진 코스", stops=None):
    stops = stops if stops is not None else ["초원사진관", "경암동<br>철길마을", "", " 다른 장소 "]
    items = "".join(f'<li>{stop}</li>' for stop in stops)
    return ('<div class="subTit"><h3>코스 안내</h3></div><div class="subCnt">'
            '<div class="recoCouse"><div class="course">\r\n  '
            f'<div class="title"><p>{name}</p></div>\r\n'
            f'<div class="detail"><ol>{items}</ol></div>\r\n'
            '</div></div></div>')


def setup(tmp_path, *, pages=None, existing=None, places=None):
    data, raw, reports = tmp_path / "data", tmp_path / "raw", tmp_path / "reports"
    data.mkdir()
    (raw / "html").mkdir(parents=True)
    (data / "courses.json").write_text(json.dumps(existing or [], ensure_ascii=False), "utf-8")
    (data / "places.json").write_text(json.dumps(places if places is not None else [
        {"name": "초원사진관", "slug": "초원사진관"},
        {"name": "경암동 철길마을", "slug": "경암동-철길마을"},
    ], ensure_ascii=False), "utf-8")
    page_records, rows = [], []
    for menu, body in (pages or [("m2552", html())]):
        url, path = f"https://www.gunsan.go.kr/tour/{menu}", f"html/{menu}.html"
        (raw / path).write_bytes(body.encode())
        parsed = parse_courses(body, url)
        page_records.append({"url": url, "raw_path": path, "classification": "course",
                             "course_count": len(parsed), "courses": parsed})
        rows.append({"url": url, "raw_path": path, "http_status": "200", "body_sha256": digest(body),
                     "collected_at": "2026-10-07T22:18:21+00:00", "error": ""})
    (raw / "scope_crawl.json").write_text(json.dumps({"status": "complete", "pages": page_records}, ensure_ascii=False), "utf-8")
    with (raw / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return data, raw, reports


def old_course(body=None):
    body = body or html("기존 코스", ["기존 장소"])
    source = parse_courses(body, "https://www.gunsan.go.kr/tour/m2107")[0]
    original = deepcopy(source["original"])
    original["sha256"] = digest(original["text"])
    return {"id": "gunsan-course-m2107-1", "slug": "preserve-this-url", "name": "검수한 이름",
            "status": "published", "reviewed_at": "2026-10-01", "summary": "검수한 요약",
            "original": original, "stops": [{"name": "검수한 경유지", "note": "기존 메모"}],
            "custom_field": {"keep": True}}


def snapshot(data, raw):
    return {str(p): p.read_bytes() for root in (data, raw) for p in root.rglob("*") if p.is_file()}


def test_dry_run_does_not_change_data_or_raw_and_reports_placeholder(tmp_path):
    data, raw, reports = setup(tmp_path)
    before = snapshot(data, raw)
    report = courses.run(data, raw, report_dir=reports)
    assert report["status"] == "ready" and not report["applied"]
    assert report["new_course_count"] == report["unique_source_originals"] == 1
    assert report["empty_stop_placeholders"] == [{"id": "gunsan-course-m2552-1", "position": 3}]
    assert snapshot(data, raw) == before


def test_apply_preserves_existing_fields_and_exact_source_with_exact_name_links(tmp_path):
    old = old_course()
    data, raw, reports = setup(tmp_path, existing=[old], pages=[
        ("m2107", html("기존 코스", ["기존 장소"])), ("m2552", html())])
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["status"] == "applied"
    merged = json.loads((data / "courses.json").read_text("utf-8"))
    assert merged[0] == old
    new = merged[1]
    assert new["status"] == "draft" and "reviewed_at" not in new
    assert new["original"]["text"] == parse_courses(html(), "https://www.gunsan.go.kr/tour/m2552")[0]["original"]["text"]
    assert "\r\n" in new["original"]["text"]
    assert new["original"]["collected_at"] == "2026-10-08"
    assert new["stops"] == [{"place_slug": "초원사진관", "note": ""},
                             {"name": "경암동\n철길마을", "note": ""},
                             {"name": " 다른 장소 ", "note": ""}]
    assert new["original"]["license"] == "NONE"


def test_identical_original_on_second_menu_is_alias_not_new_course(tmp_path):
    body = html("기존 코스", ["기존 장소"])
    data, raw, reports = setup(tmp_path, existing=[old_course(body)], pages=[
        ("m2107", body), ("m2743", body), ("m2552", html())])
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["source_block_count"] == 3
    assert report["unique_source_originals"] == 2
    assert report["new_course_count"] == report["alias_count"] == 1
    assert report["aliases"][0]["canonical_ids"] == ["gunsan-course-m2107-1"]
    assert len(json.loads((data / "courses.json").read_text("utf-8"))) == 2


@pytest.mark.parametrize("problem", ["raw_sha", "stored_extraction", "existing_sha", "same_id_changed_original", "escaping_path"])
def test_integrity_failure_leaves_all_data_unchanged(tmp_path, problem):
    old = old_course()
    if problem == "existing_sha":
        old["original"]["sha256"] = "wrong"
    pages = [("m2552", html())]
    if problem == "same_id_changed_original":
        pages.append(("m2107", html("바뀐 원문", ["기존 장소"])))
    data, raw, reports = setup(tmp_path, pages=pages, existing=[old])
    if problem == "raw_sha":
        (raw / "html/m2552.html").write_text("changed bytes")
    elif problem in {"stored_extraction", "escaping_path"}:
        scope = json.loads((raw / "scope_crawl.json").read_text("utf-8"))
        if problem == "stored_extraction":
            scope["pages"][0]["courses"][0]["original"]["text"] += "changed text"
        else:
            scope["pages"][0]["raw_path"] = "../outside.html"
        (raw / "scope_crawl.json").write_text(json.dumps(scope))
    before = snapshot(data, raw)
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["status"] == "blocked"
    assert snapshot(data, raw) == before


def test_duplicate_place_names_remain_unlinked(tmp_path):
    data, raw, reports = setup(tmp_path, places=[{"name": "초원사진관", "slug": "one"},
                                                {"name": "초원사진관", "slug": "two"}])
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["status"] == "applied"
    new = json.loads((data / "courses.json").read_text("utf-8"))[0]
    assert new["stops"][0] == {"name": "초원사진관", "note": ""}
    assert report["ambiguous_stop_names"][0]["slugs"] == ["one", "two"]


def test_unknown_and_alternative_route_layouts_never_become_flattened_new_courses(tmp_path):
    data, raw, reports = setup(tmp_path, pages=[("m9999", html()), ("m2136", html())])
    before = (data / "courses.json").read_bytes()
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["new_course_count"] == 0 and report["status"] == "applied"
    assert report["excluded_pages"][0]["reason"] == "route_layout_not_inspected"
    assert report["excluded_courses"][0]["reason"] == "multi_day_or_alternative_routes_require_model_review"
    assert (data / "courses.json").read_bytes() == before


def test_repeat_apply_is_byte_stable(tmp_path):
    data, raw, reports = setup(tmp_path)
    courses.run(data, raw, apply=True, report_dir=reports)
    before = snapshot(data, raw)
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["status"] == "applied" and report["new_course_count"] == 0
    assert snapshot(data, raw) == before


def test_concurrent_place_edit_prevents_course_overwrite(tmp_path, monkeypatch):
    data, raw, reports = setup(tmp_path)
    before = (data / "courses.json").read_bytes()
    verify = courses._verify_page

    def concurrent(page, root, manifest):
        result = verify(page, root, manifest)
        (data / "places.json").write_text("user change")
        return result

    monkeypatch.setattr(courses, "_verify_page", concurrent)
    report = courses.run(data, raw, apply=True, report_dir=reports)
    assert report["status"] == "blocked" and "changed during staging" in report["error"]
    assert (data / "courses.json").read_bytes() == before
    assert (data / "places.json").read_text("utf-8") == "user change"
