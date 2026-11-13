"""Network-free regressions using observed structural fragments, not raw probes.

The title/fieldBasic/conText/viewImg, boardSearch/board/paging, travel_map
and recoCouse shapes below were observed at www.gunsan.go.kr/tour on
2026-10-08. Small bodies are synthetic; they are not attributed source prose.
"""
import pytest

from tools.gunsan_parse import classify_license, parse_courses, parse_detail, parse_inventory


BASE = "https://www.gunsan.go.kr"


def detail(name="초원사진관", body="<p> 첫 줄&nbsp;<br>둘째 줄 </p>", extras=""):
    return f'''<html><head><title>{name} 게시글 보기 &lt; 감성여행 &lt; 문화관광</title></head>
    <body><div class="subCnt"><div class="board">
    <div class="viewImg"><ul><li><img src="/upload_data/board_data/THEME/photo.jpg" alt="{name}"></li></ul>
    <div class="rollCtrl"><img src="/www/images/btn_prev.png" alt="이전이미지로 이동"></div></div>
    <div class="viewField"><h4>감성여행</h4><div class="fieldBasic"><ul>
    <li class="i-1"><p>{name}</p></li><li class="i-1"><span>휠체어대여 :</span><p>없음</p></li>
    </ul></div><div class="conText">{body}</div>{extras}</div></div></div>
    <footer><img src="/img_opentype01.png" alt="공공누리 제1유형"></footer></body></html>'''


def test_detail_uses_name_row_instead_of_category_and_preserves_text():
    parsed = parse_detail(detail(body="\n  <h4> 소개 </h4><p> 첫 줄&nbsp;<br>둘째 줄 </p>\n"), BASE + "/tour/m2339/view/433869")
    assert parsed["name"] == "초원사진관"
    assert parsed["original_text"] == "\n  \n 소개 \n 첫 줄\xa0\n둘째 줄 \n\n"
    assert parsed["original_license"] == "NONE"  # Footer must not grant content rights.
    assert len(parsed["images"]) == 1  # Excludes slideshow control icons.
    assert parsed["images"][0]["license"] == "UNKNOWN"
    assert parsed["checks"]["name_matches"] is True


def test_notice_titlefield_and_inline_body_photo():
    # Actual source structure: /tour/m2172/view/9834787 (titleField, conText).
    html = '''<title>시티투어 안내 게시글 보기 &lt; 공지사항</title><div class="subCnt">
    <div class="board"><div class="basicView"><div class="titleField"><h4>시티투어 안내</h4></div>
    <div class="conText"><blockquote><p>일정 안내<br><br>문의 안내</p></blockquote>
    <div><img src="/upload_data/board_data/BBS_0000056/poster.jpg" alt="안내문"></div></div></div></div></div>'''
    parsed = parse_detail(html, BASE + "/tour/m2172/view/9834787")
    assert parsed["name"] == "시티투어 안내"
    assert "일정 안내\n\n문의 안내" in parsed["original_text"]
    assert parsed["images"][0]["url"] == BASE + "/upload_data/board_data/BBS_0000056/poster.jpg"
    assert parsed["structure"]["name_selector"] == ".titleField h4"


def test_metadata_only_record_does_not_pass_the_original_text_gate():
    html = detail(body="")
    with pytest.raises(ValueError, match="empty .conText"):
        parse_detail(html, BASE + "/tour/m2145/view/8596003")
    parsed = parse_detail(html, BASE + "/tour/m2145/view/8596003", allow_metadata_only=True)
    assert parsed["original_text"] == ""
    assert parsed["body_status"] == "metadata_only"
    assert parsed["checks"]["nonempty"] is False
    assert not all(parsed["checks"].values())


def test_source_facts_map_only_observed_exact_labels_and_keep_combined_fields():
    fields = '''<li class="i-3"><span>주소 :</span><p> 군산시  경촌4길 14 </p></li>
    <li class="i-4"><span>이용시간 :</span><p> 10:00~17:00 </p></li>
    <li class="i-5"><span>영업시간 및 정기휴일 :</span><p>별도 안내</p></li>
    <li><span>주메뉴 :</span><p></p></li>'''
    html = detail().replace('</ul></div><div class="conText">', fields + '</ul></div><div class="conText">')
    parsed = parse_detail(html, BASE + "/tour/m2167/view/1377622")
    assert parsed["facts"] == {"address": "군산시  경촌4길 14", "usetime": "10:00~17:00"}
    assert any(f["label"] == "영업시간 및 정기휴일" and f["value"] == "별도 안내"
               for f in parsed["source_fields"])
    assert parsed["original_text"] == parse_detail(detail(), BASE + "/tour/m2167/view/1377622")["original_text"]


def test_ambiguous_duplicate_address_is_not_silently_selected():
    fields = '<li><span>주소 :</span><p>주소 A</p></li><li><span>주소 :</span><p>주소 B</p></li>'
    html = detail().replace('</ul></div><div class="conText">', fields + '</ul></div><div class="conText">')
    parsed = parse_detail(html, BASE + "/tour/m2167/view/1377622")
    assert "address" not in parsed["facts"]
    assert len([f for f in parsed["source_fields"] if f["label"] == "주소"]) == 2


def test_observed_food_menu_does_not_turn_seat_count_into_parking_or_body_text():
    fields = '<li><span>주메뉴 :</span><p>꽃게장, 해물간장모듬장</p></li><li><span>주차 및 좌석수 :</span><p>40석</p></li>'
    html = detail(body="").replace('</ul></div><div class="conText">', fields + '</ul></div><div class="conText">')
    parsed = parse_detail(html, BASE + '/tour/m2145/view/1', allow_metadata_only=True)
    assert parsed['facts'] == {'menu': '꽃게장, 해물간장모듬장'}
    assert parsed['source_fields'][-1]['value'] == '40석'
    assert parsed['body_status'] == 'metadata_only'
    assert parsed['checks']['nonempty'] is False


def test_page_specific_license_outside_body_is_matched_to_work_name():
    marker = '''<div class="license2"><img src="/img_opentype04.jpg" alt="공공누리 제4유형">
    <p class="license_txt"><font color="blue">초원사진관</font> 저작물은 공공누리 제4유형입니다.</p></div>'''
    html = detail().replace('<body>', '<body><main id="content">').replace('<footer>', marker + '</main><footer>')
    parsed = parse_detail(html, BASE + "/tour/m2339/view/433869")
    assert parsed["original_license"] == "KOGL-4"
    assert parsed["images"][0]["license"] == "UNKNOWN"
    assert parsed["structure"]["license_matched_scopes"]
    assert parsed["original_text"] == parse_detail(detail(), BASE + "/tour/m2339/view/433869")["original_text"]
    mismatched = html.replace('<font color="blue">초원사진관</font>', '<font color="blue">다른 장소</font>')
    assert parse_detail(mismatched, BASE + "/tour/m2339/view/433869")["original_license"] == "UNKNOWN"


@pytest.mark.parametrize("number", range(1, 5))
def test_kogl_image_alt_filename_and_text(number):
    extras = f'<p><a href="https://www.kogl.or.kr">공공누리 <span>제{number}유형</span></a></p><img src="/img_opentype0{number}.jpg" alt="공공누리 제{number}유형">'
    parsed = parse_detail(detail(extras=extras), BASE + "/tour/m2339/view/433869")
    assert parsed["original_license"] == f"KOGL-{number}"
    assert "img_opentype" in parsed["license_evidence"]
    assert parsed["images"][0]["license"] == "UNKNOWN"  # Never inherit page licence.


def test_ambiguous_and_conflicting_rights_are_unknown():
    assert classify_license(["공공누리"])[0] == "UNKNOWN"
    assert classify_license(["공공누리 제1유형", "img_opentype02.jpg"])[0] == "UNKNOWN"
    assert classify_license([])[0] == "NONE"


def test_photo_specific_figure_license_does_not_grant_article_rights():
    body = '<p>소개 문장</p><figure><img src="/photo-2.jpg" alt="사진"><figcaption>사진: 공공누리 제1유형</figcaption></figure>'
    parsed = parse_detail(detail(body=body), BASE + "/tour/m2339/view/433869")
    assert parsed["original_license"] == "NONE"
    assert parsed["images"][1]["license"] == "KOGL-1"
    assert all(isinstance(v, bool) for v in parsed["checks"].values())
    assert parsed["structure"]["photo_count"] == 2


def test_photo_license_alt_does_not_grant_article_rights():
    body = '<p>소개 문장</p><img src="/regular-photo.jpg" alt="사진: 공공누리 제2유형">'
    parsed = parse_detail(detail(body=body), BASE + "/tour/m2339/view/433869")
    assert parsed["original_license"] == "NONE"
    assert parsed["images"][1]["license"] == "KOGL-2"


def test_missing_photo_does_not_fail_text_extraction_gate():
    html = detail().replace('<li><img src="/upload_data/board_data/THEME/photo.jpg" alt="초원사진관"></li>', "")
    parsed = parse_detail(html, BASE + "/tour/m2339/view/433869")
    assert parsed["images"] == []
    assert parsed["structure"]["photo_count"] == 0
    assert all(parsed["checks"].values())


def test_hidden_template_and_script_markers_do_not_grant_rights():
    html = detail(extras='<script>공공누리 제1유형</script><template><p>공공누리 제2유형</p></template>')
    parsed = parse_detail(html, BASE + "/tour/m2339/view/433869")
    assert parsed["original_license"] == "NONE"


@pytest.mark.parametrize("html,reason", [
    ("<title>없는 구조</title>", "subCnt"),
    (detail().replace('class="conText"', 'class="unknownBody"'), "conText"),
    (detail().replace("초원사진관 게시글 보기", "다른 장소 게시글 보기"), "name/title mismatch"),
    (detail(body=""), "empty .conText"),
])
def test_unknown_detail_structure_stops(html, reason):
    with pytest.raises(ValueError, match=reason):
        parse_detail(html, BASE + "/tour/m2339/view/433869")


def test_at_once_deduplicates_alias_content_ids_and_retains_categories():
    html = '''<div class="subTit"><h3>관광지 한번에 보기</h3></div><div class="subCnt"><div class="travel_map">
    <dl><dt>관광명소 </dt><dd><ul><strong>공원 </strong>
    <li><a href="/tour/m2094/view/305373">월명공원</a></li></ul></dd></dl>
    <dl><dt>테마여행</dt><dd><ul><strong>감성여행</strong>
    <li><a href="/tour/m2339/view/305373">월명공원</a></li>
    <li><a href="https://other.example/tour/m2339/view/1">외부</a></li></ul></dd></dl></div></div>'''
    parsed = parse_inventory(html, BASE + "/tour/m2237", "at_once")
    assert len(parsed["items"]) == 1
    item = parsed["items"][0]
    assert item["source_id"] == "305373"
    assert item["category"] == "관광명소 > 공원"
    assert item["aliases"][0]["category"] == "테마여행 > 감성여행"
    assert parsed["reported_total"] is None


def test_board_count_alias_board_paging_and_image_anchor_duplicates():
    # /tour/m2076 is a navigation alias; actual observed board is /tour/m2172.
    html = '''<div class="subCnt"><div class="boardSearch"><p class="page">총 <span>312</span>건</p></div>
    <div class="board"><article><span class="cate-a-1">공지사항</span>
    <a href="/tour/m2172/view/9834787?"><img src="/photo.jpg" alt="안내"></a>
    <p><a href="/tour/m2172/view/9834787?">안내</a></p></article></div>
    <div class="paging"><a href="/tour/m2172/list?s_idx=1">1</a><a href="/tour/m2172/list?s_idx=2">2</a>
    <a href="/tour/m9999/list?s_idx=2">다른 목록</a><a href="https://elsewhere.example/tour/m2172/list">외부</a></div></div>'''
    parsed = parse_inventory(html, BASE + "/tour/m2076", "board")
    assert parsed["reported_total"] == 312
    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["name"] == "안내"
    assert parsed["items"][0]["category"] == "공지사항"
    assert parsed["pagination"] == [BASE + "/tour/m2172/list?s_idx=1", BASE + "/tour/m2172/list?s_idx=2"]


def test_nonzero_board_with_no_details_is_structure_failure():
    html = '<div class="subCnt"><div class="boardSearch"><p class="page">총 20건</p></div><div class="board"></div></div>'
    with pytest.raises(ValueError, match="nonzero total"):
        parse_inventory(html, BASE + "/tour/m2080", "board")


def test_observed_board_without_total_never_invents_a_total():
    html = '''<div class="subCnt"><div class="boardSearch"><input name="search"></div>
    <div class="board"><article><a href="/tour/m2167/view/1377622">시간여행 관광안내소</a></article></div>
    <div class="paging"><a href="/tour/m2167/list?s_idx=1">1</a></div></div>'''
    with pytest.raises(ValueError, match="missing .boardSearch .page"):
        parse_inventory(html, BASE + "/tour/m2167", "board")
    parsed = parse_inventory(html, BASE + "/tour/m2167", "board_unreported_total")
    assert parsed["reported_total"] is None
    assert len(parsed["items"]) == 1
    assert parsed["pagination"] == [BASE + "/tour/m2167/list?s_idx=1"]
    assert "source total not reported" in parsed["structure"]["count_basis"]
    with pytest.raises(ValueError, match="unexpected total marker"):
        parse_inventory(html.replace('<input name="search">', '<p class="page">총 8건</p>'),
                        BASE + "/tour/m2167", "board_unreported_total")


def test_navigation_is_leaf_menu_count_skips_forms_actions_and_external():
    html = '''<ul id="gnb"><li class="gnb-4"><a href="/tour/m2076">관광 가이드</a><ul>
    <li><a href="/tour/m2164">커뮤니티</a><ul><li><a href="/tour/m2172">공지사항</a></li>
    <li><a href="/tour/m2173">군산여행후기</a></li></ul></li>
    <li><a href="/tour/m2165">관광홍보물 신청</a><ul></ul></li>
    <li><a href="/tour/m2189">단체해설 예약</a></li>
    <li><a href="/tour/m2167">관광안내소</a></li>
    <li><a href="https://gunsan.dadora.kr/">전자지도</a></li></ul></li></ul>'''
    parsed = parse_inventory(html, BASE + "/tour", "navigation")
    assert [i["name"] for i in parsed["items"]] == ["공지사항", "관광안내소"]
    assert "not content entity count" in parsed["structure"]["count_basis"]
    assert parsed["reported_total"] is None


def test_courses_preserve_stops_order_and_ignore_commented_duration():
    html = '''<div class="subTit"><h3>당일 코스</h3></div><div class="subCnt"><div class="recoCouse">
    <div class="course mt0"><div class="title"><p>A코스 | 근대~고군산</p><!--<span>소요시간:7시간</span>--></div>
    <div class="detail"><ol><li><a href="/tour/m2222">근대역사<br />박물관</a></li><li>중식</li></ol></div></div>
    <div class="course"><div class="title"><p>B코스</p></div><div class="detail"><ol><li>다음 장소 </li></ol></div></div>
    </div></div>'''
    courses = parse_courses(html, BASE + "/tour/m2135")
    assert len(courses) == 2
    assert courses[0]["name"] == "A코스 | 근대~고군산"
    assert [s["name"] for s in courses[0]["stops"]] == ["근대역사\n박물관", "중식"]
    assert courses[0]["duration"] == ""
    assert courses[0]["status"] == "draft"
    assert "소요시간" not in courses[0]["original"]["text"]
    assert "reviewed_at" not in courses[0]


def test_single_multiday_course_title_is_page_name_not_day_heading():
    # Actual /tour/m2137 has one .course with day headings h5.title, no div.title.
    html = '''<div class="subTit"><h3>2박 3일 코스</h3></div><div class="subCnt"><div class="recoCouse">
    <div class="course mt0"><div class="detail"><h5 class="title">1일차</h5><ol><li>첫 장소</li></ol>
    <h5 class="title">2일차(1안)</h5><ol><li>둘째 장소</li></ol></div></div></div></div>'''
    courses = parse_courses(html, BASE + "/tour/m2137")
    assert courses[0]["name"] == "2박 3일 코스"
    assert [s["name"] for s in courses[0]["stops"]] == ["첫 장소", "둘째 장소"]
    assert len(parse_inventory(html, BASE + "/tour/m2137", "courses")["items"]) == 1


def test_multiple_unnamed_course_blocks_stop():
    html = '<div class="subCnt"><div class="recoCouse"><div class="course"></div><div class="course"></div></div></div>'
    with pytest.raises(ValueError, match="unambiguous course-level name"):
        parse_courses(html, BASE + "/tour/m2136")


@pytest.mark.parametrize("body", ["\r\n\t 등대로   \n", "\n 등 대 로 \t"])
def test_name_only_description_is_metadata_without_changing_original_whitespace(body):
    html = detail(name="등대로", body=body)
    url = BASE + "/tour/m2145/view/306596"
    with pytest.raises(ValueError, match="only the source name"):
        parse_detail(html, url)
    parsed = parse_detail(html, url, allow_metadata_only=True)
    assert parsed["original_text"] == body
    assert parsed["name"] == "등대로"
    assert parsed["body_status"] == "metadata_only"
    assert not parsed["checks"]["nonempty"]
    assert parsed["checks"]["name_matches"]


def test_name_only_body_keeps_actual_facts_and_photo_evidence_but_is_not_text():
    html = detail(name="어시장활어회직거래판매장", body="<p> 어시장활어회직거래판매장 </p>")
    html = html.replace('<li class="i-1"><span>휠체어대여 :</span><p>없음</p></li>',
                        '<li><span>주소 :</span><p>원문 주소</p></li><li><span>주메뉴 :</span><p>원문 메뉴</p></li>')
    parsed = parse_detail(html, BASE + "/tour/m2145/view/306620", allow_metadata_only=True)
    assert parsed["original_text"] == " 어시장활어회직거래판매장 \n"
    assert parsed["body_status"] == "metadata_only" and not parsed["checks"]["nonempty"]
    assert parsed["facts"] == {"address": "원문 주소", "menu": "원문 메뉴"}
    assert parsed["original_license"] == "NONE"
    assert len(parsed["images"]) == 1 and parsed["images"][0]["license"] == "UNKNOWN"


def test_source_name_inside_actual_description_remains_a_text_body():
    parsed = parse_detail(detail(name="등대로", body="<p>등대로의 원문 설명입니다.</p>"),
                          BASE + "/tour/m2145/view/306596")
    assert parsed["body_status"] == "text"
    assert parsed["checks"]["nonempty"]
    assert parsed["original_text"] == "등대로의 원문 설명입니다.\n"
