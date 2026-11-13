"""Detail source preservation and safety; all HTTP calls are mocked."""
import hashlib
import io
import json
from urllib.error import HTTPError

import pytest

from tools.collect_gunsan import CollectionError
from tools.collect_gunsan_full import InventoryFetcher
from tools.collect_gunsan_details import build_plan, crawl_details, load_exclusions
from tools.gunsan_parse import parse_detail


BASE = "https://www.gunsan.go.kr"
ROBOTS = b"User-agent: *\nAllow: /tour\n"


class Response(io.BytesIO):
    status = 200


class Opener:
    def __init__(self, events):
        self.events, self.calls = list(events), []

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        assert self.events, "unexpected request"
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return Response(event)


def detail(name="장소", body="<p>첫 줄<br>둘째 줄  </p>"):
    return f'''<title>{name} 게시글 보기 &lt; 문화관광</title><div class="subCnt"><div class="fieldBasic"><ul>
    <li class="i-1"><p>{name}</p></li><li><span>주소 :</span><p>원문 주소</p></li></ul></div>
    <div class="conText">{body}</div></div>'''.encode()


def fetcher(root, events, **kwargs):
    opener = Opener(events)
    return InventoryFetcher(root, opener=opener, sleep=lambda delay: None, **kwargs), opener


def setup_sources(root, candidates):
    initial, _ = fetcher(root, [])
    samples = []
    for n in range(901, 904):
        url = BASE + f"/tour/m2080/view/{n}"
        raw = detail("샘플")
        path = initial._record(url, 200, raw)
        parsed = parse_detail(raw.decode(), url)
        samples.append({**parsed, "raw_path": path})
    (root / "sample_review.json").write_text(json.dumps({"passed": True, "samples": samples}), encoding="utf-8")
    scope = {"status": "complete", "detail_candidates": candidates, "pages": [
        {"url": BASE + "/tour/m2080", "classification": "board", "items": candidates}], "scope": {"excluded": []}}
    (root / "scope_crawl.json").write_text(json.dumps(scope), encoding="utf-8")
    return scope


def candidate(ident="1", name="장소", kind="attraction"):
    return {"source_id": ident, "name": name, "url": BASE + "/tour/m2080/view/" + ident,
            "category": "관광명소", "candidate_kinds": [kind], "aliases": [], "discovery_contexts": []}


def test_text_preserves_exact_body_hash_facts_and_draft_without_importing(tmp_path):
    setup_sources(tmp_path, [candidate()])
    f, opener = fetcher(tmp_path, [ROBOTS, detail()])
    result = crawl_details(f)
    assert result["status"] == "complete"
    assert result["counts"]["text_bodies"] == 1
    record = result["records"][0]
    assert record["original_text"] == "첫 줄\n둘째 줄  \n"
    assert record["original_sha256"] == hashlib.sha256(record["original_text"].encode()).hexdigest()
    assert record["facts"] == {"address": "원문 주소"}
    assert record["status"] == "draft" and record["import_eligible"]
    assert record["original_license"] == "NONE"
    assert opener.calls == [BASE + "/robots.txt", candidate()["url"]]
    assert not (tmp_path / "gunsan_places.csv").exists()


@pytest.mark.parametrize("body,status", [("", "metadata_only"), ('<img src="/photo.jpg" alt="사진">', "image_only")])
def test_metadata_and_image_only_records_are_separate_from_successful_text(tmp_path, body, status):
    setup_sources(tmp_path, [candidate(kind="food")])
    f, opener = fetcher(tmp_path, [ROBOTS, detail(body=body)])
    result = crawl_details(f)
    record = result["records"][0]
    assert record["body_status"] == status
    assert result["counts"]["text_bodies"] == 0
    assert result["counts"][status] == 1
    assert record["facts"]["address"] == "원문 주소"
    assert not record["import_eligible"]
    assert len(opener.calls) == 2  # Image is recorded but never fetched.


def test_name_mismatch_preserves_evidence_but_blocks_import(tmp_path):
    setup_sources(tmp_path, [candidate(name="목록 이름")])
    f, _ = fetcher(tmp_path, [ROBOTS, detail(name="본문 이름")])
    result = crawl_details(f)
    record = result["records"][0]
    assert record["name"] == "본문 이름"
    assert record["list_evidence"]["expected_name"] == "목록 이름"
    assert record["review_flags"] == ["list_detail_name_mismatch"]
    assert not record["import_eligible"]


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_pause_keeps_pending_and_restart_continues_after_robots(tmp_path, status):
    setup_sources(tmp_path, [candidate()])
    error = HTTPError(candidate()["url"], status, "test", {}, None)
    f, _ = fetcher(tmp_path, [ROBOTS, error])
    paused = crawl_details(f)
    assert paused["status"] == "paused"
    assert len(paused["pending"]) == 1
    assert paused["consecutive_errors"] == 1
    if status in (403, 429):
        assert paused["fetcher_stopped"]
    resumed, opener = fetcher(tmp_path, [ROBOTS, detail()])
    result = crawl_details(resumed)
    assert result["status"] == "complete"
    assert result["counts"]["records_preserved"] == 1
    assert opener.calls == [BASE + "/robots.txt", candidate()["url"]]


def test_bad_structure_is_preserved_then_pauses_without_losing_pending(tmp_path):
    setup_sources(tmp_path, [candidate()])
    f, opener = fetcher(tmp_path, [ROBOTS, b'<div class="unknown">uninspected</div>'])
    result = crawl_details(f)
    assert result["status"] == "paused"
    assert len(result["pending"]) == 1
    assert "subCnt" in result["last_error"]["reason"]
    assert len(opener.calls) == 2


def test_max_items_and_request_budget_keep_resumable_pending_queue(tmp_path):
    setup_sources(tmp_path, [candidate("1"), candidate("2")])
    f, _ = fetcher(tmp_path, [ROBOTS, detail()])
    first = crawl_details(f, max_items=1)
    assert first["status"] == "limited" and len(first["pending"]) == 1
    resumed, opener = fetcher(tmp_path, [], limit=5)  # 3 samples + robots + first detail.
    blocked = crawl_details(resumed)
    assert blocked["status"] == "paused"
    assert blocked["counts"]["records_preserved"] == 1
    assert len(blocked["pending"]) == 1 and opener.calls == []


def test_exclusion_requires_specific_evidence_and_remains_in_denominator(tmp_path):
    setup_sources(tmp_path, [candidate("1"), candidate("2")])
    evidence = tmp_path / "redirect-evidence.json"
    evidence.write_text('{"status":302,"location":"/tour/m2080/view/tour"}')
    exclusions = tmp_path / "reviewed.json"
    exclusions.write_text(json.dumps([{"id": "1", "url": candidate()["url"], "reason": "Observed invalid target",
                                      "evidence": str(evidence), "observed_at": "2026-10-07T22:00:00+00:00"}]))
    f, opener = fetcher(tmp_path, [ROBOTS, detail()])
    result = crawl_details(f, exclude_reviewed=exclusions)
    assert result["status"] == "complete"
    assert result["counts"]["inventory_candidates_total"] == 2
    assert result["counts"]["explicit_reviewed_exclusions"] == 1
    assert result["counts"]["records_preserved"] == 1
    assert candidate()["url"] not in opener.calls
    exclusions.write_text(json.dumps([{"id": "*", "url": candidate()["url"], "reason": "skip"}]))
    with pytest.raises(CollectionError, match="needs"):
        load_exclusions(exclusions)


def test_actual_board_alias_is_preferred_to_legacy_without_synthesizing_urls():
    legacy = candidate()
    legacy["url"] = BASE + "/tour/m2094/view/1"
    board = candidate()
    scope = {"detail_candidates": [legacy], "pages": [{"url": BASE + "/tour/m2080", "classification": "board", "items": [board]}]}
    plan = build_plan(scope)
    assert plan[0]["url"] == board["url"]
    assert plan[0]["selection_basis"] == "observed board item"
    forbidden = candidate()
    forbidden["discovery_contexts"] = [{"menu_path": ["관광 가이드", "군산여행후기"]}]
    with pytest.raises(CollectionError, match="Prohibited"):
        build_plan({"detail_candidates": [forbidden]})


def test_tampered_sample_gate_stops_before_network(tmp_path):
    setup_sources(tmp_path, [candidate()])
    gate = json.loads((tmp_path / "sample_review.json").read_text())
    gate["samples"][0]["original_text"] = "changed"
    (tmp_path / "sample_review.json").write_text(json.dumps(gate))
    f, opener = fetcher(tmp_path, [])
    result = crawl_details(f)
    assert result["status"] == "paused"
    assert "Sample extraction changed" in result["last_error"]["reason"]
    assert opener.calls == []


def test_notice_aliases_never_move_a_notice_ahead_of_travel_or_place_records():
    notice = candidate("1", kind="notice")
    notice["candidate_kinds"] = ["guide", "notice", "unclassified"]
    entries = [notice, candidate("2", kind="guide"), candidate("3", kind="stay"),
               candidate("4", kind="food"), candidate("5", kind="attraction"), candidate("6", kind="media")]
    plan = build_plan({"detail_candidates": entries, "pages": []})
    assert plan[-1]["source_id"] == "1"
    assert [item["source_id"] for item in plan] == ["5", "3", "4", "2", "6", "1"]
