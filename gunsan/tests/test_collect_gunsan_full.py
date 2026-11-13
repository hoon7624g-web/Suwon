"""Network-free end-to-end inventory, preservation and restart contracts."""
import csv
import hashlib
import io
import json
from urllib.error import HTTPError

import pytest

from tools.collect_gunsan import CollectionError, Fetcher, ORIGIN
from tools.collect_gunsan_full import InventoryFetcher, candidate_kind, classify_page, crawl_inventory


ROBOTS = b"User-agent: *\nAllow: /tour\n"


class Response(io.BytesIO):
    status = 200


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class Opener:
    def __init__(self, events):
        self.events, self.calls = list(events), []

    def open(self, request, timeout):
        self.calls.append(request)
        assert self.events, "unexpected network request"
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return Response(event)


def fetcher(root, events, **kwargs):
    clock, opener = Clock(), Opener(events)
    return InventoryFetcher(root, opener=opener, clock=clock, sleep=clock.sleep, **kwargs), opener


def nav(*urls):
    body = ''.join(f'<li><a href="{url}">관광명소 {i}</a></li>' for i, url in enumerate(urls))
    return f'<ul id="gnb"><li class="gnb-1"><a href="/tour/m2001">군산 자랑</a><ul>{body}</ul></li></ul>'.encode()


def board(ident, page=""):
    return f'''<div class="subTit"><h3>관광명소</h3></div><div class="subCnt">
    <div class="boardSearch"><p class="page">총 2건</p></div><div class="board">
    <a href="/tour/m2080/view/{ident}">장소 {ident}</a></div><div class="paging">{page}</div></div>'''.encode()


def test_inventory_bfs_unions_observed_ids_and_preserves_csv_and_originals(tmp_path):
    existing_csv = tmp_path.parent / (tmp_path.name + ".csv")
    existing_csv.write_bytes(b"existing source untouched\r\n")
    p2 = ORIGIN + "/tour/m2080/list?s_idx=2"
    rootpage = board(1, f'<a href="{p2}">2</a>')
    f, opener = fetcher(tmp_path, [ROBOTS, nav("/tour/m2080"), b'<div class="subCnt">static <img src="/photo.jpg"></div>', rootpage, board(2)])
    result = crawl_inventory(f)
    assert result["status"] == "complete"
    assert result["counts"]["unique_detail_ids"] == 2
    assert result["counts"]["board_pages"] == 2
    assert result["counts"]["static_awaiting_review"] == 1
    assert len(opener.calls) == 5
    assert opener.calls[-1].full_url == p2
    assert all("photo.jpg" not in r.full_url for r in opener.calls)
    assert existing_csv.read_bytes() == b"existing source untouched\r\n"
    assert {i["source_id"] for i in result["detail_candidates"]} == {"1", "2"}
    with f.manifest.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        raw = (tmp_path / row["raw_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["body_sha256"]
    stored = json.loads((tmp_path / "scope_crawl.json").read_text("utf-8"))
    assert stored["pending"] == []
    assert all(i["candidate_kinds"] == ["attraction"] for i in stored["detail_candidates"])


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_error_pauses_and_restart_reuses_cached_pages_refreshing_robots(tmp_path, status):
    error = HTTPError(ORIGIN + "/tour/m2080", status, "test", {}, None)
    f, opener = fetcher(tmp_path, [ROBOTS, nav("/tour/m2080"), b'<div class="subCnt">saved</div>', error])
    first = crawl_inventory(f)
    assert first["status"] == "paused"
    assert first["pending"][0]["url"] == ORIGIN + "/tour/m2080"
    assert len(first["pages"]) == 1
    old_bytes = (tmp_path / first["pages"][0]["raw_path"]).read_bytes()
    resumed, retry_opener = fetcher(tmp_path, [ROBOTS, board(1)])
    second = crawl_inventory(resumed)
    assert second["status"] == "complete"
    assert [r.full_url for r in retry_opener.calls] == [ORIGIN + "/robots.txt", ORIGIN + "/tour/m2080"]
    assert (tmp_path / first["pages"][0]["raw_path"]).read_bytes() == old_bytes
    assert second["requests_total_in_manifest"] == 6


def test_redirect_location_is_preserved_without_following_even_same_origin(tmp_path):
    error = HTTPError(ORIGIN + "/tour/m2001", 302, "redirect", {"Location": "/tour/m2001/view/tour"}, None)
    f, opener = fetcher(tmp_path, [ROBOTS, nav(), error])
    result = crawl_inventory(f)
    assert result["status"] == "paused"
    assert result["last_error"]["redirect"] == {"url": ORIGIN + "/tour/m2001", "status": 302,
                                                   "location": "/tour/m2001/view/tour"}
    assert len(opener.calls) == 3
    assert f.stopped
    assert "view/tour" in f.manifest.read_text("utf-8")


def test_disk_cache_is_hash_verified_and_does_not_cache_robots(tmp_path):
    f, opener = fetcher(tmp_path, [ROBOTS, b"original\r\nbytes"])
    f.load_robots()
    _, saved = f.get(ORIGIN + "/tour/m2080")
    resumed, new_opener = fetcher(tmp_path, [ROBOTS])
    resumed.load_robots()
    raw, _ = resumed.get(ORIGIN + "/tour/m2080")
    assert raw == b"original\r\nbytes"
    assert len(new_opener.calls) == 1
    (tmp_path / saved).write_bytes(b"tampered")
    with pytest.raises(CollectionError, match="hash mismatch"):
        fetcher(tmp_path, [])


def test_request_budget_is_cumulative_and_stops_before_over_limit(tmp_path):
    f, opener = fetcher(tmp_path, [ROBOTS, nav()], limit=2)
    first = crawl_inventory(f)
    assert first["status"] == "paused"
    assert len(opener.calls) == 2
    resumed, next_opener = fetcher(tmp_path, [], limit=2)
    result = crawl_inventory(resumed)
    assert result["status"] == "paused"
    assert result["requests_total_in_manifest"] == 2
    assert next_opener.calls == []
    with pytest.raises(ValueError, match="980"):
        fetcher(tmp_path, [], limit=981)


def test_unknown_board_shape_is_retained_without_extracting_article_or_guessing_totals():
    raw = b'<div class="subCnt"><div class="board"><a href="/tour/m2080/view/1">body</a></div></div>'
    result = classify_page(raw, ORIGIN + "/tour/m2080")
    assert result["classification"] == "static-awaiting-review"
    assert "items" not in result
    assert "original_text" not in result
    assert "reported_total" not in result


def test_menu_context_classification_does_not_turn_notice_or_food_into_attractions():
    contexts = [({"group": "gnb-3", "menu_path": ["음식/숙박/쇼핑", "음식", "한식"]}, "food"),
                ({"group": "gnb-3", "menu_path": ["음식/숙박/쇼핑", "숙박", "관광호텔"]}, "stay"),
                ({"group": "gnb-4", "menu_path": ["관광 가이드", "커뮤니티", "공지사항"]}, "notice"),
                ({"group": "gnb-6", "menu_path": ["시간여행마을"]}, "unclassified")]
    for context, expected in contexts:
        assert candidate_kind(context) == expected


def test_selected_section_discovers_hidden_children_and_records_canonical_without_following_it(tmp_path):
    initial = '<ul id="gnb"><li class="gnb-5"><a href="/tour/m2195">Go! 군산군도</a></li></ul>'.encode()
    selected = b'''<link rel="canonical" href="https://www.gunsan.go.kr/tour/m2199">
    <ul id="gnb"><li class="gnb-5"><a href="/tour/m2195">Go! Gunsan</a><ul>
    <li><a href="/tour/m2199">Island A</a></li></ul></li></ul><div class="subCnt">intro</div>'''
    f, opener = fetcher(tmp_path, [ROBOTS, initial, selected, b'<div class="subCnt">island page</div>'])
    result = crawl_inventory(f)
    assert result["status"] == "complete"
    assert len(result["scope"]["items"]) == 2
    assert [r.full_url for r in opener.calls][-2:] == [ORIGIN + "/tour/m2195", ORIGIN + "/tour/m2199"]
    page = result["pages"][0]
    assert page["canonical_links"][0]["url"] == ORIGIN + "/tour/m2199"
    assert result["pages"][1]["contexts"][0]["source_url"] == ORIGIN + "/tour/m2195"
    assert len(result["pages"]) == 2  # Canonical alias did not merge distinct observed source URLs.


def test_existing_at_once_candidates_remain_union_members_with_board_aliases(tmp_path):
    original = {"source_id": "1", "name": "장소 1", "url": ORIGIN + "/tour/m2094/view/1",
                "category": "공원", "aliases": []}
    (tmp_path / "inventory.json").write_text(json.dumps({"place_candidates": [original]}))
    f, opener = fetcher(tmp_path, [ROBOTS, nav(), board(1)])
    result = crawl_inventory(f)
    assert result["status"] == "complete"
    item = result["detail_candidates"][0]
    assert item["url"] == original["url"]
    assert item["aliases"][0]["url"] == ORIGIN + "/tour/m2080/view/1"
    assert {c["group"] for c in item["discovery_contexts"]} == {"gnb-1", "at_once"}


def test_inspected_information_center_list_keeps_unreported_total_unknown():
    raw = b'<div class="subCnt"><div class="boardSearch"><input></div><div class="board"><a href="/tour/m2167/view/12">Center</a></div></div>'
    parsed = classify_page(raw, ORIGIN + "/tour/m2167")
    assert parsed["classification"] == "board"
    assert parsed["reported_total"] is None
    assert len(parsed["items"]) == 1
    assert classify_page(raw, ORIGIN + "/tour/m3005")["classification"] == "static-awaiting-review"


def test_notice_pagination_uses_observed_title_even_from_generic_guide_parent():
    from tools.collect_gunsan_full import _refresh_candidates
    state = {"scope": {"items": []}, "pending": [], "pages": [{
        "url": ORIGIN + "/tour/m2172/list?s_idx=2", "title": "공지사항", "classification": "board",
        "contexts": [{"group": "gnb-4", "menu_path": ["관광 가이드"]}],
        "items": [{"source_id": "123", "name": "휴관 안내", "url": ORIGIN + "/tour/m2172/view/123", "category": "공지사항"}]}]}
    _refresh_candidates(state)
    assert state["detail_candidates"][0]["candidate_kinds"] == ["notice"]


def test_excluded_contest_cannot_reenter_via_parent_alias_or_pagination(tmp_path):
    home = '''<ul id="gnb"><li class="gnb-4"><a href="/tour/m2166">생생포토/영상</a><ul>
    <li><a href="/tour/m2849">관광사진 공모전</a></li></ul></li></ul>'''.encode()
    parent_board = '''<div class="subTit"><h3>관광사진 공모전</h3></div><div class="subCnt">
    <div class="boardSearch"><p class="page">총 12건</p></div><div class="board">
    <a href="/tour/m2849/view/1450649">참가 사진</a></div><div class="paging">
    <a href="/tour/m2849/list?s_idx=2">2</a></div></div>'''.encode()
    f, opener = fetcher(tmp_path, [ROBOTS, home, parent_board])
    state = crawl_inventory(f)
    assert state["status"] == "complete"
    assert state["detail_candidates"] == []
    assert state["counts"]["observed_unique_detail_ids"] == 1
    assert state["counts"]["eligible_detail_ids"] == 0
    assert state["counts"]["excluded_unique_detail_ids"] == 1
    observation = state["excluded_candidate_observations"][0]
    assert observation["source_id"] == "1450649"
    assert observation["original_list_url"] == ORIGIN + "/tour/m2166"
    assert observation["excluded_policies"][0]["reason"] == "user_contest_content"
    assert state["pages"][0]["items"][0]["source_id"] == "1450649"  # Evidence remains intact.
    assert len(opener.calls) == 3  # Forbidden pagination/detail not requested.
    assert state["excluded_pagination_observations"][0]["url"] == ORIGIN + "/tour/m2849/list?s_idx=2"


def test_recomputed_candidates_hold_out_forbidden_alias_ids_without_mutating_pages():
    from copy import deepcopy
    from tools.collect_gunsan_full import _refresh_candidates
    allowed = {"source_id": "2", "name": "안내", "url": ORIGIN + "/tour/m28490/view/2", "category": "안내"}
    held = {"source_id": "1", "name": "같은 ID", "url": ORIGIN + "/tour/m2175/view/1", "category": "풍경",
            "aliases": [{"name": "공모전 별칭", "url": ORIGIN + "/tour/m2849/view/1", "category": "공모전"}]}
    state = {"scope": {"items": [], "excluded": [{"url": ORIGIN + "/tour/m2849", "reason": "user_contest_content"}]},
             "pending": [], "pages": [{"url": ORIGIN + "/tour/m2166", "classification": "board",
                                         "contexts": [{"group": "gnb-4", "menu_path": ["관광 가이드", "생생포토/영상"]}],
                                         "items": [held, allowed]}]}
    before = deepcopy(state["pages"])
    _refresh_candidates(state)
    assert state["pages"] == before
    assert [item["source_id"] for item in state["detail_candidates"]] == ["2"]
    assert state["counts"]["observed_unique_detail_ids"] == 2
    assert state["counts"]["excluded_unique_detail_ids"] == 1
    assert state["counts"]["eligible_detail_ids"] == 1  # m28490 is not the excluded m2849.


def test_resume_removes_previous_forbidden_pagination_before_request(tmp_path):
    state = {"version": 1, "status": "paused", "pages": [], "failures": [], "at_once_candidates": [],
             "scope": {"items": [], "excluded": [{"url": ORIGIN + "/tour/m2849", "reason": "user_contest_content"}]},
             "pending": [{"url": ORIGIN + "/tour/m2849/list?s_idx=2", "contexts": [], "discovered_on": ORIGIN + "/tour/m2166"}]}
    (tmp_path / "scope_crawl.json").write_text(json.dumps(state))
    f, opener = fetcher(tmp_path, [ROBOTS])
    result = crawl_inventory(f)
    assert result["status"] == "complete" and result["pending"] == []
    assert [request.full_url for request in opener.calls] == [ORIGIN + "/robots.txt"]
    assert result["excluded_pagination_observations"][0]["original_list_url"] == ORIGIN + "/tour/m2166"


@pytest.mark.parametrize("contexts,expected", [
    ([{"group": "gnb-3", "menu_path": ["음식/숙박/쇼핑", "음식", "한식"]},
      {"group": "side", "menu_path": ["음식", "한식"]}], ["food"]),
    ([{"group": "side", "menu_path": ["음식", "한식"]},
      {"group": "observed_content_link", "menu_path": ["음식점"]}], ["unclassified"]),
    ([{"group": "gnb-3", "menu_path": ["음식/숙박/쇼핑", "음식"]},
      {"group": "gnb-1", "menu_path": ["군산 자랑", "관광명소"]},
      {"group": "side", "menu_path": ["음식"]}], ["attraction", "food"]),
])
def test_missing_kind_evidence_does_not_override_specific_or_hide_conflicting_classifications(contexts, expected):
    from tools.collect_gunsan_full import _refresh_candidates
    state = {"scope": {"items": []}, "pending": [], "pages": [{
        "url": ORIGIN + "/tour/m2145", "classification": "board", "contexts": contexts,
        "items": [{"source_id": "123", "name": "항목", "url": ORIGIN + "/tour/m2145/view/123", "category": "분류"}]}]}
    _refresh_candidates(state)
    item = state["detail_candidates"][0]
    assert item["candidate_kinds"] == expected
    assert len(item["discovery_contexts"]) == len(contexts)
    assert any(context["kind"] == "unclassified" for context in item["discovery_contexts"])


def static_island_page(links, body_links=""):
    return ('<div class="subTit"><h3>여객선 관광</h3></div><div class="subCnt"><div class="gogunsanBox">'
            '<p>원문 설명\n그대로</p><div class="tripList">' + links + '</div>' + body_links + '</div></div>').encode()


def test_registered_static_tabs_are_discovered_without_being_in_navigation_menu(tmp_path):
    # Inspected /tour/m2351 gogunsanBox/tripList layout; no #gnb on this body fixture.
    source = static_island_page('<a href="/tour/m2352">유람선 관광</a>')
    destination = static_island_page('')
    f, opener = fetcher(tmp_path, [ROBOTS, nav('/tour/m2351'), b'<div class="subCnt">hub</div>', source, destination])
    state = crawl_inventory(f)
    assert state["status"] == "complete"
    assert opener.calls[-1].full_url == ORIGIN + '/tour/m2352'
    item = next(item for item in state['scope']['items'] if item['url'] == ORIGIN + '/tour/m2352')
    evidence = item['discoveries'][0]
    assert evidence['group'] == 'observed_content_link'
    assert evidence['field'] == 'navigation_links' and evidence['selector'] == '.subCnt .tripList a[href]'
    assert evidence['original_sha256'] and evidence['html_sha256']
    assert 'original_text' not in evidence
    assert next(p for p in state['pages'] if p['url'] == ORIGIN + '/tour/m2351')['classification'] == 'static-awaiting-review'


def test_static_links_keep_policy_unavailable_and_form_exclusions_without_network():
    from tools.collect_gunsan_full import expand_static_links
    state = {'scope': {'items': [], 'excluded': [{'url': ORIGIN + '/tour/m2849', 'reason': 'user_contest_content'}]},
             'pages': [], 'pending': [], 'failures': [{'url': ORIGIN + '/tour/m2352'}],
             'reviewed_unavailable_pages': [{'url': ORIGIN + '/tour/m2352', 'review_reason': 'Observed unavailable response'}]}
    links = ('<a href="/tour/m2352">유람선 관광</a><a href="/tour/m2849">사진 목록</a>'
             '<a href="/tour/m9991">예약</a><a href="https://external.example/tour/m9992">외부</a>'
             '<form><a href="/tour/m9993">확인</a></form>')
    body_links = '<a href="/tour/m2353">명품고군산군도</a><a href="/tour/m9994/view/1">본문 상세 링크</a>'
    expand_static_links(state, static_island_page(links, body_links), ORIGIN + '/tour/m2351')
    assert [item['url'] for item in state['pending']] == [ORIGIN + '/tour/m2353']
    reasons = {item['reason'] for item in state['excluded_static_link_observations']}
    assert {'reviewed_unavailable_exact_url', 'excluded_menu_policy', 'prohibited_link_or_source_label', 'form_action',
            'outside_same_origin_static_menu_path'} <= reasons
    assert state['pending'][0]['contexts'][0]['field'] == 'internal_links'
    assert not any('external.example' in item['url'] for item in state['pending'])


def test_unregistered_or_changed_static_layout_never_expands_links(monkeypatch):
    from tools import collect_gunsan_full as full
    state = {'scope': {'items': [], 'excluded': []}, 'pages': [], 'pending': [], 'failures': []}
    parser = full.parse_static
    calls = []

    def checked_parser(html, url):
        calls.append(url)
        return parser(html, url)

    monkeypatch.setattr(full, 'parse_static', checked_parser)
    full.expand_static_links(state, static_island_page('<a href="/tour/m2352">다음</a>'), ORIGIN + '/tour/m9999')
    assert calls == []
    full.expand_static_links(state, b'<div class="subCnt"><a href="/tour/m2352">changed</a></div>', ORIGIN + '/tour/m2351')
    assert calls == [ORIGIN + '/tour/m2351']
    assert state['pending'] == []
    assert [review['status'] for review in state['static_link_reviews']] == ['unsupported', 'awaiting-review']


def test_reviewed_unavailable_page_requires_failure_evidence_and_is_not_requeued():
    from tools.collect_gunsan_full import _expand_navigation, _filter_pending_pages
    target = ORIGIN + '/tour/m2954'
    state = {'scope': {'items': [], 'excluded': [], 'counts': {}}, 'pages': [],
             'pending': [{'url': target, 'contexts': []}],
             'reviewed_unavailable_pages': [{'url': target, 'review_reason': 'Observed redirect outside numeric tourism route'}],
             'failures': []}
    with pytest.raises(CollectionError, match='observed failure'):
        _filter_pending_pages(state)
    state['failures'] = [{'url': target, 'reason': 'Unexpected redirect'}]
    _filter_pending_pages(state)
    assert state['pending'] == []
    _expand_navigation(state, nav('/tour/m2954'), ORIGIN + '/tour')
    assert target not in [item['url'] for item in state['pending']]
    assert any(item['url'] == target for item in state['scope']['items'])
    assert state['reviewed_unavailable_pages']
