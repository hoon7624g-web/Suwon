"""Offline evidence, source integrity and dry-run boundary checks."""
import csv
import hashlib
import json

import pytest

from tools.archive_gunsan_static import build_archive, main


ORIGIN = "https://www.gunsan.go.kr"
BODY = ('<div class="trafficTop"><p>원문 민박 안내\r\n두 번째 줄 </p></div><h4>현황</h4>'
        '<div class="basic scrollBox"><table><caption>군산시 농어촌 민박</caption>'
        '<thead><tr><th>업소명</th></tr></thead><tbody><tr><td>원문 상호\r\n그대로 </td></tr></tbody></table></div>')


def html(body=BODY):
    return '<section id="content"><div class="subTit"><h3>농어촌민박</h3></div><div class="subCnt">' + body + '</div></section>'


def sources(tmp_path, entries=None, *, samples=None):
    (tmp_path / "html").mkdir()
    entries = entries or [{"url": ORIGIN + "/tour/m2158", "raw_path": "html/stay.html", "html": html()}]
    scope, manifest = [], []
    for entry in entries:
        raw_path = entry["raw_path"]
        content = entry["html"].encode("utf-8")
        (tmp_path / raw_path).write_bytes(content)
        row = {"url": entry["url"], "raw_path": raw_path, "classification": "static-awaiting-review"}
        scope.append(row)
        manifest.append({"url": entry["url"], "raw_path": raw_path, "http_status": "200",
                         "body_sha256": hashlib.sha256(content).hexdigest(), "collected_at": "2026-10-07T22:06:12Z", "error": ""})
    (tmp_path / "scope_crawl.json").write_text(json.dumps({"pages": scope}))
    (tmp_path / "scope_probe_samples.json").write_text(json.dumps(samples or []))
    with (tmp_path / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    return scope


def test_manifest_sha_and_source_crlf_are_preserved_without_writes(tmp_path):
    sources(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    result = build_archive(tmp_path)
    document = result["documents"][0]
    assert "원문 민박 안내\r\n두 번째 줄 " in document["original_text"]
    assert document["tables"][0]["rows"][1]["cells"][0]["text"] == "원문 상호\r\n그대로 "
    assert document["raw_html_sha256"] == hashlib.sha256((tmp_path / "html/stay.html").read_bytes()).hexdigest()
    assert document["collected_at"] == ["2026-10-07T22:06:12Z"]
    assert document["original_license"] == "NONE"
    assert result["summary"]["supported_source_url_count"] == 1
    assert result["summary"]["observed_business_rows_by_document_version"] == 1
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


@pytest.mark.parametrize("field,value", [("body_sha256", "0" * 64), ("url", ORIGIN + "/tour/m2153"), ("http_status", "403"), ("raw_path", "html/other.html")])
def test_manifest_mismatch_is_not_parsed_and_is_recorded(tmp_path, field, value):
    sources(tmp_path)
    with (tmp_path / "manifest.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0][field] = value
    with (tmp_path / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = build_archive(tmp_path)
    assert not result["documents"]
    assert result["extraction_failures"][0]["stage"] == "integrity"


def test_raw_path_escape_is_rejected_even_when_matching_manifest_exists(tmp_path):
    scope = sources(tmp_path)
    scope[0]["raw_path"] = "../secret.html"
    (tmp_path / "scope_crawl.json").write_text(json.dumps({"pages": scope}))
    result = build_archive(tmp_path)
    assert not result["documents"] and "relative path" in result["extraction_failures"][0]["reason"]


def test_unsupported_and_changed_structures_remain_in_output(tmp_path):
    sources(tmp_path, [
        {"url": ORIGIN + "/tour/m29999", "raw_path": "html/uninspected.html", "html": html()},
        {"url": ORIGIN + "/tour/m2158", "raw_path": "html/changed.html", "html": html('<form>관측되지 않은 폼</form>')},
    ])
    result = build_archive(tmp_path)
    assert len(result["unsupported"]) == 1 and result["unsupported"][0]["manifest_evidence"]
    assert len(result["extraction_failures"]) == 1 and result["extraction_failures"][0]["stage"] == "extraction"


def test_sha_groups_page_counts_table_rows_and_sample_provenance_are_separate(tmp_path):
    entries = [{"url": ORIGIN + "/tour/" + path, "raw_path": "html/" + path + ".html", "html": html()}
               for path in ("m2153", "m2158")]
    samples = [{"url": entries[0]["url"], "raw_path": entries[0]["raw_path"]}]
    sources(tmp_path, entries, samples=samples)
    result = build_archive(tmp_path)
    assert result["summary"]["supported_source_url_count"] == 2
    assert result["summary"]["distinct_original_sha_count"] == 1
    assert result["summary"]["observed_tbody_rows_by_document_version"] == 2
    assert result["summary"]["observed_tbody_rows_by_distinct_original_sha"] == 1
    assert result["summary"]["observed_business_rows_by_distinct_original_sha"] == 1
    assert result["documents"][0]["observed_in"] == ["scope_crawl", "scope_probe_samples"]


def test_observed_navigation_candidates_and_exclusions_are_not_invented(tmp_path):
    menu = ('<div class="tab4"><a href="/tour/m2177">관광지도</a><a href="/tour/m2870">예약하기</a>'
            '<a href="/tour/m2700">여행 후기</a><a href="/tour/m2701">UCC</a><a href="/tour/m2702">TPO</a>'
            '<a href="/tour/m2703">신청하기</a></div>')
    body = BODY.replace('</p></div>', '</p><a href="https://example.com/">외부 안내</a></div>')
    sources(tmp_path, [{"url": ORIGIN + "/tour/m2158", "raw_path": "html/stay.html", "html": html(menu + body)}])
    result = build_archive(tmp_path)
    assert [x["url"] for x in result["supplemental_navigation_candidates"]] == [ORIGIN + "/tour/m2177"]
    candidate = result["supplemental_navigation_candidates"][0]
    assert candidate["observations"][0]["source_url"] == ORIGIN + "/tour/m2158"
    assert candidate["observations"][0]["field"] == "navigation_links"
    assert len(result["excluded_navigation_observations"]) == 6


def test_default_dry_run_and_explicit_apply_leave_input_files_unchanged(tmp_path, capsys):
    sources(tmp_path)
    scope_before = (tmp_path / "scope_crawl.json").read_bytes()
    assert main(["--raw-dir", str(tmp_path)]) == 0
    assert '"mode": "dry-run"' in capsys.readouterr().out
    assert not (tmp_path / "static_documents.json").exists()
    assert main(["--raw-dir", str(tmp_path), "--apply"]) == 0
    assert json.loads((tmp_path / "static_documents.json").read_text("utf-8"))["documents"]
    assert (tmp_path / "scope_crawl.json").read_bytes() == scope_before


def test_apply_cannot_target_a_site_dataset_or_arbitrary_filename(tmp_path):
    sources(tmp_path)
    with pytest.raises(SystemExit):
        main(["--raw-dir", str(tmp_path), "--apply", "--output", str(tmp_path / "places.json")])
    assert not (tmp_path / "places.json").exists()


def test_missing_optional_probe_uses_only_manifest_verified_actual_scope_pages(tmp_path):
    sources(tmp_path)
    (tmp_path / "scope_probe_samples.json").unlink()
    result = build_archive(tmp_path)
    assert result["summary"]["supported_source_url_count"] == 1
    assert result["documents"][0]["observed_in"] == ["scope_crawl"]
    assert result["documents"][0]["manifest_evidence"]
    assert result["extraction_failures"] == []
    assert not (tmp_path / "scope_probe_samples.json").exists()


@pytest.mark.parametrize("required", ["scope_crawl.json", "manifest.csv"])
def test_scope_and_manifest_remain_required_without_probe(tmp_path, required):
    sources(tmp_path)
    (tmp_path / "scope_probe_samples.json").unlink()
    (tmp_path / required).unlink()
    with pytest.raises(FileNotFoundError):
        build_archive(tmp_path)


def test_missing_probe_does_not_relax_manifest_sha_validation(tmp_path):
    sources(tmp_path)
    (tmp_path / "scope_probe_samples.json").unlink()
    (tmp_path / "html/stay.html").write_bytes(b"changed source HTML")
    result = build_archive(tmp_path)
    assert result["documents"] == []
    assert result["extraction_failures"][0]["stage"] == "integrity"


def test_present_probe_still_needs_actual_matching_raw_and_manifest(tmp_path):
    sources(tmp_path, samples=[{"url": ORIGIN + "/tour/m2153", "raw_path": "html/fake.html"}])
    result = build_archive(tmp_path)
    assert len(result["documents"]) == 1
    assert result["extraction_failures"][0]["url"] == ORIGIN + "/tour/m2153"
    assert result["extraction_failures"][0]["stage"] == "integrity"


def test_malformed_present_probe_is_not_silently_ignored(tmp_path):
    sources(tmp_path)
    (tmp_path / "scope_probe_samples.json").write_text('{"fake":"observation"}')
    with pytest.raises(ValueError, match="list of actual response"):
        build_archive(tmp_path)
