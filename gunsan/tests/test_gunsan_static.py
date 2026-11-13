"""Small inline fragments of observed layouts; no ignored raw files are needed."""
from __future__ import annotations

import hashlib

import pytest

from tools.gunsan_static import parse_information_list, parse_static


ORIGIN = "https://www.gunsan.go.kr"


def page(name, body, *, licence="", footer=""):
    return ('<!doctype html><html><head><title>' + name + '</title></head><body>'
            '<section id="content"><div class="subTit"><h3>' + name + '</h3></div>'
            '<div class="subCnt">' + body + '</div>' + licence + '</section>' + footer + '</body></html>')


def dedicated(work="선유도 해수욕장", type_number=4):
    return ('<div class="license2"><div class="mark_box"><ul class="mark"><li>'
            f'<img src="/www/images/main/img_opentype0{type_number}.jpg" '
            f'alt="OPEN 공공누리 공공저작물 자유이용허락- 제 {type_number} 유형">'
            '</li></ul></div><p class="license_txt"><a href="http://www.kogl.or.kr/info/'
            f'licenseType{type_number}.do">군산시청 문화관광에서 제작한 '
            f'<font color="blue">{work}</font> 저작물은 "공공누리" '
            '<font color="red">출처표시-상업적 이용금지-변경금지</font> 조건에 따라 이용 할 수 있습니다.'
            '</a></p></div>')


MUSEUM = ('<div class="topBoxA"><div class="conTxt"><h4>근대역사박물관</h4>'
          '<p>근대역사교육의 도시 군산에 자리한\r\n특화 박물관이다.&nbsp; </p></div></div>'
          '<h4 class="h4">소개</h4><div class="h4Box">'
          '<div class="imgBox v2"><img src="/www/images/ntour/images/content/img_timeDe1_1.jpg" '
          'alt="근대역사발관 전체 전경"></div><table class="conTable">'
          '<caption>군산관광지 개인 관람료</caption><thead><tr><th colspan="2">구분</th></tr></thead>'
          '<tbody><tr><th>성인\n(군산시민)</th><td>3,000 \n(2,000)</td></tr></tbody></table></div>')
ISLAND = ('<div class="gogunsanBox"><div class="trip bg1"><h4>선유도 해수욕장</h4>'
          '<p>고군산군도의 중심섬으로 선유도에 위치한 천연해안사구 해수욕장으로  \n'
          '유리알처럼 고운 천연 모래가 펼쳐 있다.</p></div><div class="imgBox v3">'
          '<img src="/upload_data/board_data/BBS_0000231/154096129936154.jpg" '
          'alt="해수욕장에서 물놀이하는 사람들의 모습"></div></div>')
GUBUL = ('<div class="gubulBox"><div class="titleBox bg1"><strong>구불 1길 비단강길</strong></div>'
         '<div class="tabMenu"><ul><li class="intro on"><a href="/tour/m2290">코스소개</a></li>'
         '<li class="trip"><a href="/tour/m2291">여행포인트</a></li>'
         '<li class="food"><a href="/tour/m2292">먹거리정보</a></li></ul></div>'
         '<div class="tabInfo1"><div class="blind mList"><ol>'
         '<li><strong>군산역 </strong> 출발</li><li>1.5Km 25분</li><li>진포시비공원</li>'
         '</ol></div><div class="btnBox tc"><a href="/upload_data/board_data/BBS_0000391/177373924164475.jpg">'
         '구불1길 비단강길 지도</a></div><div class="curseInfo"><p>금강을 주인공으로 이야기를 펼쳐가는 이 길은\n'
         '채만식 문학관을 만날 수 있다. </p></div></div></div>')
BUS = ('<div class="trafficBox"><div class="trafficInfo"><h4>군산시시내버스 안내</h4>'
       '<p>시내버스 전화번호 063-443-3077 </p></div></div><h4 class="h4">버스종점지변경안내</h4>'
       '<div class="imgBox"><img src="/upload_data/board_data/BBS_0000391/172281971375298.jpg" '
       'alt="버스종점지변경안내"></div><div class="btnBox tc">'
       '<a href="/upload_data/board_data/BBS_0000391/172949409447936.xlsx">군산시내버스시간표</a></div>')
FOOD = ('<div class="tab4"><ul><li><a href="/tour/m2141">전체</a></li>'
        '<li><a href="/tour/m2555">군산 맛집</a></li></ul></div>'
        '<div class="basic"><h4>군산 맛집 선정 절차</h4><table class="conTable">'
        '<caption>군산맛집 지정 현황 - 34개소</caption><thead><tr><th>업소명</th><th>소재지(도로명)</th></tr></thead>'
        '<tbody><tr><td>계곡가든</td><td>개정면 금강로 470</td></tr></tbody></table></div>')
TIME_MAP = ('<div class="timeMap courseMap"><p>지도에서 지역을 클릭하면 상세내용을 확인할 수 있습니다.</p>'
            '<div class="map"><img src="/www/images/ntour/images/content/img_time_map.jpg" alt="시간여행마을지도"></div>'
            '<ul class="point"><li><a href="#">근대역사박물관</a></li></ul>'
            '<div class="mapPopup"><div class="popup pop1"><p class="title">근대역사박물관</p>'
            '<a class="more" href="/tour/m2222">자세히보기</a><a class="close" href="#">닫기</a>'
            '</div></div></div>')


@pytest.mark.parametrize("path,name,body,profile", [
    ("m2222", "근대역사박물관", MUSEUM, "museum"),
    ("m2195", "선유도 해수욕장", ISLAND, "island"),
    ("m2113", "구불1길 코스소개", GUBUL, "gubul"),
    ("m2180", "시내버스", BUS, "bus"),
    ("m2555", "군산 맛집", FOOD, "food_table"),
    ("m2219", "시간여행 코스 소개", TIME_MAP, "time_map"),
])
def test_only_registered_observed_static_shapes(path, name, body, profile):
    result = parse_static(page(name, body), ORIGIN + "/tour/" + path)
    assert result["profile"] == profile and result["name"] == name
    assert result["checks"]["nonempty"] and result["checks"]["inspected_profile"]
    assert result["original_sha256"] == hashlib.sha256(result["original_text"].encode()).hexdigest()


def test_original_body_and_table_whitespace_are_not_normalised():
    result = parse_static(page("근대역사박물관", MUSEUM), ORIGIN + "/tour/m2222")
    assert "군산에 자리한\r\n특화 박물관이다.\xa0 " in result["original_text"]
    table = result["tables"][0]
    assert table["rows"][1]["cells"][1]["text"] == "3,000 \n(2,000)"
    assert table["rows"][0]["cells"][0]["colspan"] == "2"
    assert table["observed_tbody_rows"] == 1
    assert table["sha256"] == hashlib.sha256(table["original_text"].encode()).hexdigest()


def test_page_specific_licence_outside_body_matches_work_but_not_photos():
    result = parse_static(page("선유도 해수욕장", ISLAND, licence=dedicated()), ORIGIN + "/tour/m2195")
    assert result["original_license"] == "KOGL-4"
    assert "img_opentype04.jpg" in result["license_evidence"]
    assert "licenseType4.do" in result["license_evidence"]
    assert "선유도 해수욕장" in result["license_evidence"]
    assert "제 4 유형" in result["license_evidence"]
    assert result["structure"]["license_scopes"][1].startswith("#content .license2")
    assert len(result["images"]) == 1 and result["images"][0]["license"] == "UNKNOWN"
    assert "공공누리" not in result["original_text"]


def test_licence_of_a_different_work_is_unknown_not_inherited():
    result = parse_static(page("선유도 해수욕장", ISLAND, licence=dedicated("무녀도")), ORIGIN + "/tour/m2195")
    assert result["original_license"] == "UNKNOWN"
    assert result["structure"]["unmatched_license_markers"][0]["work_names"] == ["무녀도"]


def test_global_footer_licence_is_not_an_article_licence():
    result = parse_static(page("선유도 해수욕장", ISLAND, footer=dedicated()), ORIGIN + "/tour/m2195")
    assert result["original_license"] == "NONE"


def test_conflicting_page_specific_types_are_unknown():
    conflict = dedicated().replace('alt="OPEN 공공누리 공공저작물 자유이용허락- 제 4 유형"', 'alt="공공누리 제1유형"')
    result = parse_static(page("선유도 해수욕장", ISLAND, licence=conflict), ORIGIN + "/tour/m2195")
    assert result["original_license"] == "UNKNOWN"


def test_tabs_are_preserved_separately_without_becoming_body_text():
    result = parse_static(page("구불1길 코스소개", GUBUL), ORIGIN + "/tour/m2113")
    assert "먹거리정보" not in result["original_text"]
    assert "먹거리정보" in result["tabs"][0]["original_text"]
    assert [t["url"] for t in result["tabs"][0]["links"]] == [ORIGIN + "/tour/m2290", ORIGIN + "/tour/m2291", ORIGIN + "/tour/m2292"]
    assert result["ordered_course"] is True
    assert result["stops"][0] == {"name": "군산역", "source_text": "군산역  출발"}
    assert result["stops"][1]["name"] == "진포시비공원"
    assert result["legs"] == [{"source_text": "1.5Km 25분"}]
    assert result["attachment_links"][0]["url"].endswith("177373924164475.jpg")


def test_bus_notice_images_and_attachment_are_only_urls():
    result = parse_static(page("시내버스", BUS), ORIGIN + "/tour/m2180")
    assert result["images"][0]["role"] == "notice_image"
    assert result["images"][0]["license"] == "UNKNOWN"
    assert result["attachment_links"][0]["url"].endswith(".xlsx")
    assert "image_bytes" not in result and "attachment_bytes" not in result


def test_map_points_are_not_an_ordered_course():
    result = parse_static(page("시간여행 코스 소개", TIME_MAP), ORIGIN + "/tour/m2219")
    assert result["ordered_course"] is False and "stops" not in result
    assert result["map_points"][0]["name"] == "근대역사박물관"
    assert result["map_points"][0]["url"] == ORIGIN + "/tour/m2222"
    assert result["images"][0]["role"] == "map"


@pytest.mark.parametrize("url", [ORIGIN + "/tour/m29999", ORIGIN + "/tour/m29998", "https://example.com/tour/m2222", "http://www.gunsan.go.kr/tour/m2222"])
def test_uninspected_page_or_origin_is_rejected(url):
    with pytest.raises(ValueError):
        parse_static(page("근대역사박물관", MUSEUM), url)


@pytest.mark.parametrize("body", [BUS, '<div class="topBoxA">소개</div>', MUSEUM + '<div class="board">게시글</div>', MUSEUM + '<form>검색</form>'])
def test_wrong_section_or_uninspected_shape_is_rejected(body):
    with pytest.raises(ValueError):
        parse_static(page("근대역사박물관", body), ORIGIN + "/tour/m2222")


def information(rows=8):
    articles = ''.join('<article><div class="thumnail"><a href="/tour/m2167/view/'
                       + str(1377622 - i) + '?"><img src="/sample.jpg" alt="시간여행 관광안내소"></a></div>'
                       '<div class="info-v5"><p><a href="/tour/m2167/view/' + str(1377622 - i)
                       + '?">시간여행 관광안내소</a></p><p>주소 :\n전북특별자치도 군산시 중앙로 1가 11-1</p></div></article>'
                       for i in range(rows))
    return '<div class="boardSearch"><form>명칭 입력</form></div><div class="board">' + articles + '</div><div class="paging"><a href="/tour/m2167/list?s_idx=1">1</a></div>'


def test_information_rows_have_no_invented_overall_total():
    result = parse_information_list(page("관광안내소", information()), ORIGIN + "/tour/m2167")
    assert result["reported_total"] is None and result["observed_count"] == 8
    assert result["items"][0]["source_id"] == "1377622"
    assert "주소 :\n전북특별자치도 군산시 중앙로 1가 11-1" in result["items"][0]["original_text"]
    assert result["pagination"] == [ORIGIN + "/tour/m2167/list?s_idx=1"]


def test_information_changed_total_or_missing_rows_requires_inspection():
    with pytest.raises(ValueError):
        parse_information_list(page("관광안내소", information().replace('<form>', '<p class="page">총8건</p><form>')), ORIGIN + "/tour/m2167")
    with pytest.raises(ValueError):
        parse_information_list(page("관광안내소", information(0)), ORIGIN + "/tour/m2167")


def test_nested_basic_tables_do_not_create_a_second_food_body():
    body = FOOD.replace('<h4>', '<div class="basic">표 안내</div><h4>')
    result = parse_static(page("군산 맛집", body), ORIGIN + "/tour/m2555")
    assert len(result["tables"]) == 1 and "표 안내" in result["original_text"]


def test_gubul_changed_stop_and_leg_structure_requires_inspection():
    with pytest.raises(ValueError):
        parse_static(page("구불1길 코스소개", GUBUL.replace('1.5Km 25분', '이동 안내')), ORIGIN + "/tour/m2113")


def gubul_variant(route, *, info="curseInfo2"):
    return ('<div class="gubulBox"><div class="titleBox bg6"><strong>구불길</strong></div>'
            '<div class="tabInfo1"><div class="blind mList"><ol>' + route + '</ol></div>'
            '<div class="' + info + '"><p>원문 설명\n그대로 </p></div></div></div>')


@pytest.mark.parametrize("path,route,shape", [
    ("m2118", '<li>은파호수공원</li><li>4Km 60분</li><li><ol><li>월명공원</li><li>대안 경로</li></ol></li>', "branched"),
    ("m2121", '<li>1.5Km 25분</li><li>옥산저수지</li><li>1Km 20분</li>', "open_ends"),
    ("m2123", '<li>내초공원</li><li><ol><li>가지 경로</li></ol></li>', "branched"),
])
def test_branch_and_open_boundary_routes_are_preserved_without_inventing_order(path, route, shape):
    result = parse_static(page("구불길 코스소개", gubul_variant(route)), ORIGIN + "/tour/" + path)
    assert result["route_shape"] == shape and result["ordered_course"] is False
    assert "stops" not in result and "legs" not in result
    assert result["route_lists"][0]["original_text"]
    assert "원문 설명\n그대로 " in result["original_text"]


def test_gubul_info_variant_keeps_actual_linear_names():
    result = parse_static(page("구불길 코스소개", gubul_variant('<li>월명공원</li><li>1Km 20분</li><li>도착지</li>')), ORIGIN + "/tour/m2119")
    assert [x["name"] for x in result["stops"]] == ["월명공원", "도착지"]
    assert result["ordered_course"] is True


def test_gubul_article_excludes_nested_feedback_form_only():
    body = ('<h4>구불길 소개</h4><div class="gubulBox"><div class="thousand"><p>원문\n내용 </p></div>'
            '<div class="customerBox"><form>담당자 만족도</form></div></div>')
    result = parse_static(page("구불길 안내", body), ORIGIN + "/tour/m2124")
    assert "원문\n내용 " in result["original_text"] and "만족도" not in result["original_text"]
    with pytest.raises(ValueError):
        parse_static(page("구불길 안내", body.replace('class="customerBox"', 'class="actualContent"')), ORIGIN + "/tour/m2124")


def test_city_intro_booking_controls_and_tabs_are_separate_from_source_description():
    body = ('<div class="tab4"><a href="/tour/m2288">코스소개</a></div><div class="subMain1"><p>시티투어 안내\n</p></div>'
            '<div class="cList"><p>테마코스 소개 </p></div><div class="btnBox"><a href="/tour/m2870">예약하기</a></div>')
    result = parse_static(page("시티투어", body), ORIGIN + "/tour/m2074")
    assert "테마코스 소개 " in result["original_text"] and "예약하기" not in result["original_text"]
    assert result["navigation_links"] == [{"name": "코스소개", "url": ORIGIN + "/tour/m2288"}]


def test_stay_intro_and_listing_are_kept_with_row_counts_separate_from_documents():
    body = ('<div class="tab4"><a href="/tour/m2158">농어촌민박</a></div><div class="trafficTop"><p>민박 안내\n</p></div>'
            '<h4>현황</h4><div class="basic scrollBox"><table><caption>군산시 농어촌민박</caption>'
            '<thead><tr><th>업소명</th></tr></thead><tbody><tr><td>원문 업소\n상호 </td></tr></tbody></table></div>')
    result = parse_static(page("농어촌민박", body), ORIGIN + "/tour/m2158")
    assert result["tables"][0]["observed_tbody_rows"] == 1 and len(result["tables"]) == 1
    assert result["tables"][0]["rows"][1]["cells"][0]["text"] == "원문 업소\n상호 "
    assert "민박 안내" in result["original_text"] and result["navigation_links"]


def test_extensionless_map_download_is_a_link_only():
    body = '<div class="mapGuide"><p>관광안내지도\n</p><a href="/_cms/board/eFileDownload/58/1117347/2064138/">관광지도 다운로드</a></div>'
    result = parse_static(page("관광지도", body), ORIGIN + "/tour/m2168")
    assert result["attachment_links"][0]["url"] == ORIGIN + "/_cms/board/eFileDownload/58/1117347/2064138/"
    assert "attachment_bytes" not in result


def test_gogunsan_navigation_is_separate_and_external_references_are_not_followed():
    body = ('<div class="gogunsanBox"><div class="topBoxA"><p>고군산 소개\n</p></div>'
            '<div class="tripList"><a href="/tour/m2352">유람선관광</a></div><h4>여객선 관광</h4>'
            '<p>장자도 원문 안내 </p><a href="https://island.theksa.co.kr/">여객선예매</a></div>')
    result = parse_static(page("여객선 관광", body), ORIGIN + "/tour/m2351")
    assert "유람선관광" not in result["original_text"] and "장자도 원문 안내 " in result["original_text"]
    assert result["navigation_links"][0]["url"] == ORIGIN + "/tour/m2352"
    assert result["outbound_links"] == [{"name": "여객선예매", "url": "https://island.theksa.co.kr/", "source_text": "여객선예매", "followed": False}]


def test_stamps_include_source_image_and_free_choice_block_without_ordered_course():
    body = ('<h4>군산관광 스탬프 투어 코스 안내</h4><p class="mt20 mb30"><img src="/source.jpg" alt="코스 지도"></p>'
            '<div class="recoCouse stampCouse"><div class="course"><div class="title"><p>아리랑 코스</p><em>체험 안내</em></div><p>경유지 원문\n</p></div>'
            '<div class="course"><div class="title"><p>내맘대로 스탬프 투어</p><em>완주코스는 내가 정한다~~</em></div></div></div>'
            '<div class="mapGuide"><a href="/source.pdf">다운로드</a></div>')
    result = parse_static(page("스탬프투어 코스안내", body), ORIGIN + "/tour/m2126")
    assert [x["name"] for x in result["course_blocks"]] == ["아리랑 코스", "내맘대로 스탬프 투어"]
    assert result["ordered_course"] is False and "stops" not in result
    assert result["images"][0]["url"] == ORIGIN + "/source.jpg"
    assert result["course_blocks"][0]["sha256"] == hashlib.sha256(result["course_blocks"][0]["original_text"].encode()).hexdigest()


def test_time_food_multiple_tables_do_not_omit_non_table_chinese_food_descriptions():
    body = ('<h4>한식</h4><div class="basic mb50"><table><caption>주변맛집</caption><tbody><tr><td>식당</td></tr></tbody></table></div>'
            '<h4>중식</h4><div class="basic mb50"><div class="gogunsanBox"><p>빈해원\n공식 원문 설명 </p></div></div>')
    result = parse_static(page("음식점", body), ORIGIN + "/tour/m2220")
    assert "빈해원\n공식 원문 설명 " in result["original_text"] and "중식" in result["original_text"]
    assert result["tables"][0]["observed_tbody_rows"] == 1


def culture_gallery():
    gallery = ''.join('<article><div><img src="/image' + str(i) + '.jpg" alt="img' + str(i) + '"></div></article>' for i in range(1, 5))
    return ('<div class="trafficBox"><h4>JB문화공간</h4><div class="h4Box"><div class="board"><div class="A-2">'
            + gallery + '</div></div><h5>전북은행미술관</h5><p>원문 미술관 소개\n그대로 </p></div></div>')


@pytest.mark.parametrize("path", ["m2106", "m3005"])
def test_culture_page_image_only_board_wrapper_is_not_a_board_inventory(path):
    result = parse_static(page("문화공간 체험", culture_gallery()), ORIGIN + "/tour/" + path)
    assert result["profile"] == "culture_gallery_article" and len(result["images"]) == 4
    assert "원문 미술관 소개\n그대로 " in result["original_text"]


@pytest.mark.parametrize("replacement", ["게시글", '<a href="/tour/m2106/view/1">제목</a>', '<form>검색</form>'])
def test_image_gallery_board_with_article_text_links_or_form_is_rejected(replacement):
    body = culture_gallery().replace('<div class="A-2">', '<div class="A-2">' + replacement)
    with pytest.raises(ValueError):
        parse_static(page("문화공간 체험", body), ORIGIN + "/tour/m2106")


@pytest.mark.parametrize("path", ["m2290", "m2293", "m2298", "m2301"])
def test_inspected_gubul_intro_tab_urls_keep_explicit_route_source(path):
    result = parse_static(page("구불길 코스소개", GUBUL), ORIGIN + "/tour/" + path)
    assert result["ordered_course"] is True and len(result["stops"]) == 2
    assert "먹거리정보" not in result["original_text"]


@pytest.mark.parametrize("path,panel,contents", [
    ("m2291", "tabInfo2", '<ul><li class="img1"><strong>채만식 문학관</strong><p>근거 원문\r\n문장 </p></li></ul>'),
    ("m2292", "tabInfo3", '<div class="basic"><table><caption>비단강길 주변음식점 소개</caption><tbody><tr><td>원문 상호 </td></tr></tbody></table></div>'),
])
def test_gubul_point_and_food_tabs_keep_sources_separate_from_navigation(path, panel, contents):
    body = ('<div class="gubulBox"><div class="titleBox"><strong>구불길</strong></div><div class="txt">도입 원문 </div>'
            '<div class="tabMenu"><a href="/tour/m2290">코스소개</a><a href="/tour/m2292">먹거리정보</a></div>'
            '<div class="' + panel + '">' + contents + '</div></div>')
    result = parse_static(page("구불길 정보", body), ORIGIN + "/tour/" + path)
    assert "도입 원문 " in result["original_text"] and "코스소개" not in result["original_text"]
    assert result["tabs"][0]["links"] and result["original_license"] == "NONE"
    assert result["original_sha256"] == hashlib.sha256(result["original_text"].encode()).hexdigest()
    with pytest.raises(ValueError):
        parse_static(page("구불길 정보", body.replace(panel, 'tabInfo1')), ORIGIN + "/tour/" + path)


@pytest.mark.parametrize("path,separate", [("m2285", False), ("m2761", True), ("m2284", False)])
def test_city_route_body_keeps_sibling_or_nested_course_as_observed(path, separate):
    route = '<div class="cursebox"><div class="day1 type2"><p>출발지\r\n(09:15)</p></div><div class="infoList">원문 코스 안내 </div></div>'
    body = ('<div class="tab4"><a href="/tour/m2288">시티투어 소개</a></div><div class="tourTit">운행 원문 </div>'
            '<div class="tourCont"><ul class="bu01"><li>이용 안내</li></ul>' + ('' if separate else route) + '</div>' + (route if separate else ''))
    result = parse_static(page("출발 코스", body), ORIGIN + "/tour/" + path)
    assert "출발지\r\n(09:15)" in result["original_text"] and "시티투어 소개" not in result["original_text"]
    assert result["ordered_course"] is False and result["route_blocks"][0]["original_text"]
    assert "stops" not in result


def test_observed_cycling_point_body_and_tabs_are_preserved_without_image_inference():
    body = ('<div class="tab4"><a href="/tour/m2305">철새와 금강제방</a></div>'
            '<div class="gubulBox cycleBox"><div class="titleBox"><p>금강하구둑</p></div><div class="txt">원문 도입\r\n</div>'
            '<div class="tabInfo2"><ul><li class="img1"><p>관찰한 지점 설명 </p></li></ul></div></div>')
    result = parse_static(page("금강하구둑", body), ORIGIN + "/tour/m2304")
    assert "관찰한 지점 설명 " in result["original_text"] and result["images"] == []
    assert result["navigation_links"][0]["url"] == ORIGIN + "/tour/m2305"


def test_time_village_place_intro_detail_whitespace_and_photo_urls_are_preserved():
    body = ('<div class="topBoxA"><div class="conTxt"><h4>장미갤러리</h4><p>1945년 광복 이후에는 위락시설로 사용하였다. \r\n</p></div></div>'
            '<h4 class="h4">소개</h4><div class="h4Box"><div class="imgBox"><img src="/source-gallery.jpg" alt="장미갤러리"></div>'
            '<p>군산시의 근대산업 유산 예술창작벨트사업의 일환으로 개관했다. </p></div>')
    result = parse_static(page("장미갤러리", body), ORIGIN + "/tour/m2225")
    assert "위락시설로 사용하였다. \r\n" in result["original_text"]
    assert result["images"][0]["url"] == ORIGIN + "/source-gallery.jpg"
    assert result["images"][0]["license"] == "UNKNOWN"
    with pytest.raises(ValueError):
        parse_static(page("장미갤러리", body.replace('class="h4Box"', 'class="changedBox"')), ORIGIN + "/tour/m2225")


def test_specialty_food_source_is_not_normalised_or_promoted_to_a_business_record():
    body = ('<div class="tab4"><a href="/tour/m2343">꽃게장(간장게장)</a></div>'
            '<div class="gusanFood"><h4>군산특산품01</h4><h5>울외장아찌</h5>'
            '<p>전북특별자치도 군산시에서 재배되는 울외를\r\n청주 부산물인 술지게미로 </p></div>')
    result = parse_static(page("울외장아찌", body), ORIGIN + "/tour/m2342")
    assert "울외를\r\n청주" in result["original_text"] and result["tables"] == []
    assert "꽃게장(간장게장)" not in result["original_text"]


def test_inspected_island_licence_inside_subcnt_keeps_body_and_feedback_separate():
    body = ('<div class="gogunsanBox"><div class="trip bg1"><h4>관리도</h4><p>관리도 원문\r\n그대로 </p></div>'
            '<div class="imgBox"><img src="/island.jpg" alt="관리도"></div></div>' + dedicated("관리도")
            + '<div class="customerBox"><form>매우만족/불만족</form></div>')
    result = parse_static(page("관리도", body), ORIGIN + "/tour/m2210")
    assert result["original_license"] == "KOGL-4"
    assert "관리도 원문\r\n그대로 " in result["original_text"]
    assert "매우만족" not in result["original_text"] and "공공누리" not in result["original_text"]
    assert result["images"][0]["license"] == "UNKNOWN"
    mismatch = parse_static(page("관리도", body.replace('<font color="blue">관리도</font>', '<font color="blue">말도</font>')), ORIGIN + "/tour/m2210")
    assert mismatch["original_license"] == "UNKNOWN"


def test_new_time_map_alias_is_supported_only_after_actual_response_inspection():
    result = parse_static(page("시간여행 코스 소개", TIME_MAP), ORIGIN + "/tour/m2355")
    assert result["ordered_course"] is False and len(result["map_points"]) == 1
    assert result["map_points"][0]["url"] == ORIGIN + "/tour/m2222"
