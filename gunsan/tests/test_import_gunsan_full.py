"""Staging/import rollback and source integrity contracts; no network required."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import import_gunsan_full as full


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def record(ident="2", name="새 장소", text=" 원문\r\n둘째 줄  ", kinds=None, eligible=True):
    return {"id": "gunsan-" + ident, "source_id": ident, "name": name, "original_text": text,
            "original_sha256": digest(text), "html_sha256": "recorded-html-hash", "original_license": "NONE",
            "source_url": "https://www.gunsan.go.kr/tour/m2080/view/" + ident,
            "collected_at": "2026-10-07T18:30:00+00:00", "candidate_kinds": kinds or ["attraction"],
            "import_eligible": eligible, "body_status": "text", "review_flags": [],
            "list_evidence": {"category": "실제 분류"}, "facts": {"address": "원문 주소", "usetime": "원문 시간"},
            "images": [{"url": "https://www.gunsan.go.kr/photo1.jpg", "alt": "사진1", "license": "UNKNOWN", "evidence": "표기 미확인"},
                       {"url": "https://www.gunsan.go.kr/photo2.jpg", "alt": "사진2", "license": "KOGL-1", "evidence": "직접 표기"}]}


def existing():
    return {"id": "gunsan-1", "name": "기존 장소", "slug": "보존할-슬러그", "kind": "attraction", "tier": "full",
            "status": "published", "reviewed_at": "2026-10-01", "themes": ["기존-테마"],
            "summary": "기존 요약", "faq": [{"q": "기존 질문", "a": "기존 답변"}],
            "facts": {"address": "검수된 주소"}, "facts_source": {"provider": "검수 출처", "checked_at": "2026-10-01"},
            "images": [{"url": "https://www.gunsan.go.kr/old.jpg", "alt": "기존 사진", "license": "KOGL-1", "source": "원문"}],
            "original": {"text": "기존\r\n원문", "sha256": digest("기존\r\n원문"), "license": "KOGL-3"},
            "locks": ["geo"], "custom_existing_field": {"preserve": True}}


def setup(tmp_path, records, entities=None):
    data, raw, reports = tmp_path / "data", tmp_path / "raw" / "gunsan", tmp_path / "reports"
    data.mkdir()
    raw.mkdir(parents=True)
    (data / "site.json").write_text(json.dumps({"source": {"name": full.PROVIDER}, "brand": "보존할 브랜드"}))
    (data / "places.json").write_text(json.dumps(entities if entities is not None else [existing()], ensure_ascii=False), "utf-8")
    (data / "courses.json").write_bytes(b"existing courses untouched")
    (raw.parent / "gunsan_places.csv").write_bytes(b"legacy csv untouched")
    (raw / "details_crawl.json").write_text(json.dumps({"status": "complete", "records": records}, ensure_ascii=False), "utf-8")
    return data, raw, reports


def snapshot(data, raw):
    return {str(path): path.read_bytes() for root in (data, raw.parent) for path in root.rglob("*") if path.is_file()}


def test_default_dry_run_validates_without_changing_data_or_raw_csv(tmp_path):
    data, raw, reports = setup(tmp_path, [record()])
    before = snapshot(data, raw)
    report = full.run(data, raw, report_dir=reports)
    assert report["status"] == "ready" and not report["applied"]
    assert report["new_place_count"] == 1
    assert snapshot(data, raw) == before
    assert (reports / "import_gunsan_full.json").exists()


def test_apply_preserves_existing_entity_whole_and_imports_exact_text_facts_all_images(tmp_path):
    old = existing()
    raw_old = record("1", text=old["original"]["text"])
    raw_old["facts"] = {"address": "다른 원문 주소"}
    data, raw, reports = setup(tmp_path, [raw_old, record()])
    original_site = (data / "site.json").read_bytes()
    report = full.run(data, raw, apply=True, report_dir=reports)
    assert report["status"] == "applied"
    entities = json.loads((data / "places.json").read_text("utf-8"))
    assert entities[0] == old
    new = entities[1]
    assert new["status"] == "draft" and new["tier"] == "basic"
    assert new["original"]["text"] == record()["original_text"]
    assert new["original"]["sha256"] == record()["original_sha256"]
    assert new["facts"] == record()["facts"]
    assert new["facts_source"] == {"provider": full.PROVIDER, "checked_at": "2026-10-08"}
    assert len(new["images"]) == 2
    assert new["images"][0]["license"] == "UNKNOWN"
    assert new["images"][1]["alt"] == "사진2"
    assert "summary" not in new and "faq" not in new and "reviewed_at" not in new
    assert (data / "site.json").read_bytes() == original_site
    assert (data / "courses.json").read_bytes() == b"existing courses untouched"
    assert (raw.parent / "gunsan_places.csv").read_bytes() == b"legacy csv untouched"
    assert (raw.parent / "gunsan_places_full.csv").exists()


@pytest.mark.parametrize("corruption", ["existing_hash", "incoming_hash", "changed_original"])
def test_original_conflicts_block_entire_apply_without_partial_output(tmp_path, corruption):
    old = existing()
    incoming = record("1", text=old["original"]["text"])
    if corruption == "existing_hash":
        old["original"]["sha256"] = "wrong"
    elif corruption == "incoming_hash":
        incoming["original_sha256"] = "wrong"
    else:
        incoming = record("1", text="changed text")
    data, raw, reports = setup(tmp_path, [incoming, record()], [old])
    before = snapshot(data, raw)
    result = full.run(data, raw, apply=True, report_dir=reports)
    assert result["status"] == "blocked"
    assert result["conflicts"]
    assert snapshot(data, raw) == before


def test_ambiguous_nonplace_and_review_records_are_private_source_documents(tmp_path):
    records = [record("2", kinds=["attraction", "guide"]), record("3", kinds=["notice"]),
               record("4", kinds=["food"], eligible=False)]
    data, raw, reports = setup(tmp_path, records)
    places_before = (data / "places.json").read_bytes()
    result = full.run(data, raw, apply=True, report_dir=reports)
    assert result["status"] == "applied" and result["new_place_count"] == 0
    assert (data / "places.json").read_bytes() == places_before
    archive = json.loads((data / "source_documents.json").read_text("utf-8"))
    assert archive["status"] == "draft" and archive["public"] is False
    assert [entry["record"] for entry in archive["documents"]] == records
    assert not (raw.parent / "gunsan_places_full.csv").exists()


def test_duplicate_names_get_stable_slugs_and_repeat_apply_preserves_entity_bytes(tmp_path):
    data, raw, reports = setup(tmp_path, [record("2", name="새 장소"), record("3", name="새 장소")])
    first = full.run(data, raw, apply=True, report_dir=reports)
    assert first["new_place_count"] == 2
    entities = json.loads((data / "places.json").read_text("utf-8"))
    assert entities[1]["slug"] != entities[2]["slug"]
    before = (data / "places.json").read_bytes()
    csv_before = (raw.parent / "gunsan_places_full.csv").read_bytes()
    second = full.run(data, raw, apply=True, report_dir=reports)
    assert second["new_place_count"] == 0
    assert (data / "places.json").read_bytes() == before
    assert (raw.parent / "gunsan_places_full.csv").read_bytes() == csv_before


def test_schema_failure_after_staging_never_reaches_real_data(tmp_path):
    bad = record()
    bad["images"][1]["license"] = "made-up-license"
    data, raw, reports = setup(tmp_path, [bad])
    before = snapshot(data, raw)
    result = full.run(data, raw, apply=True, report_dir=reports)
    assert result["status"] == "blocked"
    assert "schema" in result["error"]
    assert snapshot(data, raw) == before


def test_concurrent_data_edit_is_not_overwritten(tmp_path, monkeypatch):
    data, raw, reports = setup(tmp_path, [record()])
    original_run = full.importer.run

    def concurrent_edit(csv_path, staging):
        result = original_run(csv_path, staging)
        (data / "site.json").write_bytes(b"concurrent user change")
        return result

    monkeypatch.setattr(full.importer, "run", concurrent_edit)
    result = full.run(data, raw, apply=True, report_dir=reports)
    assert result["status"] == "blocked"
    assert (data / "site.json").read_bytes() == b"concurrent user change"
    assert json.loads((data / "places.json").read_text("utf-8")) == [existing()]


def test_atomic_batch_rolls_back_already_replaced_files_if_later_replace_fails(tmp_path, monkeypatch):
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    one.write_bytes(b"original-one")
    two.write_bytes(b"original-two")
    replace = full.os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated replace failure")
        return replace(source, target)

    monkeypatch.setattr(full.os, "replace", fail_second)
    with pytest.raises(OSError):
        full._atomic_batch({one: b"changed-one", two: b"changed-two"})
    assert one.read_bytes() == b"original-one" and two.read_bytes() == b"original-two"
    assert not list(tmp_path.glob(".gunsan-*"))
