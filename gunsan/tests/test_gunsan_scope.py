"""Offline regressions for the six groups observed in the saved /tour menu."""
from copy import deepcopy
import json

import pytest

from tools.gunsan_scope import main, merge_candidates, pagination_queue, parse_scope_navigation


BASE = "https://www.gunsan.go.kr"


def navigation(groups):
    return '<ul id="gnb">' + ''.join(
        f'<li class="gnb-{number}"><a href="/tour/m{2000 + number}">{label}</a><ul>{body}</ul></li>'
        for number, label, body in groups) + '</ul>'


def menu(name, href, children=""):
    return f'<li><a href="{href}">{name}</a><ul>{children}</ul></li>'


def test_scope_includes_every_observed_group_with_nested_discovery_context():
    html = navigation([
        (1, "군산 자랑", menu("관광명소", "/tour/m2080")),
        (2, "추천여행", menu("구불길", "/tour/m2103", menu("구불1길 비단강길", "/tour/m2113"))),
        (3, "음식/숙박/쇼핑", menu("숙박", "/tour/m2142", menu("관광호텔", "/tour/m2151"))),
        (4, "관광 가이드", menu("관광안내소", "/tour/m2167")),
        (5, "Go! 군산군도", menu("기본정보", "/tour/m2194")),
        (6, "시간여행마을", menu("여행코스", "/tour/m2219")),
    ])
    result = parse_scope_navigation(html, BASE + "/tour")
    assert {x["group"] for x in result["items"]} == {f"gnb-{i}" for i in range(1, 7)}
    by_id = {x["source_id"]: x for x in result["items"]}
    assert by_id["m2113"]["menu_path"] == ["추천여행", "구불길", "구불1길 비단강길"]
    assert by_id["m2113"]["leaf"]
    assert not by_id["m2103"]["leaf"]
    assert by_id["m2151"]["discoveries"][0]["source_url"] == BASE + "/tour"
    assert by_id["m2194"]["name"] == "기본정보"
    assert by_id["m2219"]["name"] == "여행코스"
    assert result["counts"]["observed_menu_links"] == 14
    assert "not article" in result["count_basis"]


def test_prohibited_menus_and_their_descendants_have_explicit_exclusion_reasons():
    html = navigation([
        (1, "군산 자랑", menu("TPO 교류도시 관광 소개", "/tour/m2794", menu("중국 칭타오", "/tour/m2795"))),
        (2, "추천여행", menu("예약하기", "/tour/m2110") + menu("예약확인", "/tour/m2111")),
        (4, "관광 가이드", menu("군산여행후기", "/tour/m2173")
         + menu("관광홍보물 신청", "/tour/m2165")
         + menu("관광사진 공모전", "/tour/m2849")
         + menu("UCC", "/tour/m2519")
         + '<li><form><a href="/tour/m2192">실행</a></form></li>'),
    ])
    result = parse_scope_navigation(html, BASE + "/tour")
    excluded = {x["menu_label"]: x["reason"] for x in result["excluded"]}
    assert excluded == {"TPO 교류도시 관광 소개": "outside_gunsan_tpo", "중국 칭타오": "outside_gunsan_tpo",
                        "예약하기": "application_or_reservation", "예약확인": "application_or_reservation",
                        "군산여행후기": "user_reviews", "관광홍보물 신청": "application_or_reservation",
                        "관광사진 공모전": "user_contest_content", "UCC": "user_contest_content", "실행": "form_action"}
    assert len(result["items"]) == 3  # Only the group menus remain.


def test_repeated_urls_preserve_each_context_and_external_or_action_links_are_excluded():
    html = navigation([
        (2, "추천여행", menu("도보 여행", "/tour/m2113")),
        (4, "관광 가이드", menu("도보 코스", "/tour/m2113#section")
         + menu("전자지도", "https://gunsan.dadora.kr/")
         + menu("다른 사이트", "https://www.gunsan.go.kr.evil.example/tour/m999")
         + menu("다른 경로", "/main/m99")
         + menu("접두사만 일치", "/tour/m1234/anything")
         + menu("상세는 메뉴가 아님", "/tour/m2080/view/433883")
         + menu("동작", "javascript:openMenu()")
         + menu("HTTP", "http://www.gunsan.go.kr/tour/m2113")),
    ])
    result = parse_scope_navigation(html, BASE + "/tour")
    item = next(x for x in result["items"] if x["source_id"] == "m2113")
    assert item["url"] == BASE + "/tour/m2113"
    assert [d["menu_label"] for d in item["discoveries"]] == ["도보 여행", "도보 코스"]
    assert result["counts"]["duplicate_discoveries"] == 1
    assert len(result["excluded"]) == 7
    assert all(x["reason"] for x in result["excluded"])


@pytest.mark.parametrize("html", ['<nav></nav>', '<ul id="gnb"><li class="gnb-7">other</li></ul>',
                                  '<div id="gnb"></div><div id="gnb"></div>'])
def test_unknown_navigation_shape_stops_instead_of_guessing(html):
    with pytest.raises(ValueError, match="scope:"):
        parse_scope_navigation(html, BASE + "/tour")


def test_pagination_queues_only_observed_links_without_inventing_missing_page_numbers():
    page1 = BASE + "/tour/m2080/list?s_idx=1"
    page3 = BASE + "/tour/m2080/list?s_idx=3"
    page9 = BASE + "/tour/m2080/list?s_idx=9"
    inventories = [{"url": BASE + "/tour/m2080", "reported_total": 78,
                    "pagination": [page1, page3, page9]}, {"pagination": [page3]}]
    assert pagination_queue(inventories, seen=[page1]) == [page3, page9]
    assert all("s_idx=2" not in url for url in pagination_queue(inventories))
    with pytest.raises(ValueError, match="unsupported"):
        pagination_queue([{"pagination": ["https://elsewhere.example/tour/m2080/list?s_idx=2"]}])


def test_candidate_union_keeps_first_identity_and_alias_evidence_without_mutating_inputs():
    first = {"source_id": "305373", "name": "월명공원", "url": BASE + "/tour/m2094/view/305373",
             "category": "공원", "aliases": [{"name": "월명공원", "url": BASE + "/tour/m2339/view/305373", "category": "감성여행"}]}
    second = {"source_id": "305373", "name": "월명공원", "url": BASE + "/tour/m2080/view/305373", "category": "관광명소", "aliases": []}
    third = {"source_id": "433869", "name": "초원사진관", "url": BASE + "/tour/m2339/view/433869", "category": "감성여행"}
    original = deepcopy([first, second, first, third])
    merged = merge_candidates([first, second, first, third])
    assert len(merged) == 2
    assert merged[0]["url"] == first["url"]
    assert [a["category"] for a in merged[0]["aliases"]] == ["감성여행", "관광명소"]
    assert [first, second, first, third] == original


def test_local_html_cli_emits_discovery_inventory_without_network(tmp_path, capsys, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network prohibited"))
    source = tmp_path / "saved.html"
    source.write_text(navigation([(5, "Go! 군산군도", menu("기본정보", "/tour/m2194"))]), encoding="utf-8")
    out = tmp_path / "scope.json"
    assert main(["--html", str(source), "--out", str(out)]) == 0
    result = json.loads(out.read_text("utf-8"))
    assert result["input_html"] == str(source)
    assert len(result["items"]) == 2
    assert json.loads(capsys.readouterr().out)["unique_candidate_urls"] == 2


def test_observed_board_page_can_supply_new_nested_navigation_evidence():
    source = BASE + "/tour/m2080/list?s_idx=2"
    result = parse_scope_navigation(navigation([(5, "Go! 군산군도", menu("섬여행", "/tour/m2195"))]), source)
    assert result["items"][1]["discoveries"][0]["source_url"] == source


def test_side_navigation_discovers_hidden_islands_and_merges_existing_menu_urls():
    html = navigation([(5, "Go! 군산군도", menu("섬여행", "/tour/m2195"))])
    html += '<nav id="side"><ul>' + menu("섬여행", "/tour/m2195",
        menu("선유도 해수욕장", "/tour/m2199") + menu("선유도", "/tour/m2201")) + '</ul></nav>'
    result = parse_scope_navigation(html, BASE + "/tour/m2195")
    by_id = {item["source_id"]: item for item in result["items"]}
    assert by_id["m2199"]["group"] == "side"
    assert by_id["m2199"]["menu_path"] == ["섬여행", "선유도 해수욕장"]
    assert by_id["m2199"]["discoveries"][0]["selector"] == "nav#side > ul > li > ul > li a[href]"
    assert by_id["m2201"]["source_url"] == BASE + "/tour/m2195"
    assert [d["group"] for d in by_id["m2195"]["discoveries"]] == ["gnb-5", "side"]
    assert len([item for item in result["items"] if item["source_id"] == "m2195"]) == 1


def test_side_menus_inherit_exclusions_and_only_inspected_side_structure_is_read():
    html = navigation([(4, "관광 가이드", "")])
    html += '<nav id="side"><ul>' + menu("관광사진 공모전", "/tour/m2849", menu("사진 목록", "/tour/m2850"))
    html += menu("여행 안내", "/tour/m2167", menu("외부 사이트", "https://outside.example/tour/m1"))
    html += '</ul><div><a href="/tour/m9999">메뉴 밖 링크</a></div></nav>'
    result = parse_scope_navigation(html, BASE + "/tour/m2167")
    excluded = {item["menu_label"]: item["reason"] for item in result["excluded"]}
    assert excluded["관광사진 공모전"] == "user_contest_content"
    assert excluded["사진 목록"] == "user_contest_content"
    assert excluded["외부 사이트"] == "external_or_credentialed_url"
    assert not any(item["source_id"] == "m9999" for item in result["items"])


def test_missing_side_is_normal_but_multiple_sides_fail_explicitly():
    html = navigation([(5, "Go! 군산군도", "")])
    assert parse_scope_navigation(html, BASE + "/tour")["items"]
    with pytest.raises(ValueError, match="multiple #side"):
        parse_scope_navigation(html + '<nav id="side"></nav><nav id="side"></nav>', BASE + "/tour")
