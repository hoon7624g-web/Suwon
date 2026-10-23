import csv
import hashlib
import json
from pathlib import Path

import pytest

from tools import question_coverage as qc
from tools.question_coverage import course_candidates, guide_candidates, rules_problems, source_documents

# The question rules are data written with a city's question set (tools/question_coverage.py docstring). These are the
# rules of the sample (Gunsan) N30/P3 question set this tool was first written for, kept as a fixture: the engine reads
# them exactly as it reads a city's rules file. Place names match data/sample-style records built below.
SAMPLE_SITE = Path(__file__).resolve().parents[1] / "data" / "sample" / "site.json"
SOURCE = json.loads(SAMPLE_SITE.read_text("utf-8"))["source"]["name"]   # the site's own source (sample config)
TRAVEL = {"from": "documents", "name_any": ["교통", "버스", "철도", "군산역", "시티투어"]}
TOUR_LEFT = "의 현재 적용 여부·정확한 경로/위치 확인"
DESC = {"do": "text", "pattern": "마을은|촬영 장소", "facet": "장소 설명", "id": "desc"}
NO_DESC = {"do": "missing", "text": "장소 소개 원문", "unless": "desc"}


def text(pattern, facet, scope="selected", **extra):
    return {"do": "text", "pattern": pattern, "facet": facet, "in": scope, **extra}


def missing(value, **extra):
    return {"do": "missing", "text": value, **extra}


def rule(names=(), *steps):
    return {"names": list(names), "steps": list(steps)}


MUSEUM = ("군산근대역사박물관", "근대역사박물관")
RAIL = ("경암동 철길마을",)
RULES = {"groups": {"N": 30, "P": 3}, "questions": {
    "N01": rule(RAIL, DESC, text("(?:입장|관람|이용)[^\n]{0,20}(?:료|무료)", "원문 이용요금 언급"),
                missing("입장료의 현재 적용 여부 확인값"), NO_DESC),
    "N02": rule(("초원사진관",), DESC,
                {"do": "any", "if_none": "주소·위치 직접 근거",
                 "steps": [{"do": "fact", "field": "address", "facet": "출처가 기록된 주소 필드"},
                           text("주소\\s*[:：]", "원문 주소")]}, NO_DESC),
    "N03": rule(MUSEUM, text("\\d{1,2}:\\d{2}|휴관", "원문 관람시간·휴관일 언급"), text("휴관", "원문 휴관일"),
                missing("박물관 운영시간의 출처 간 상충 여부 및 현재 적용값 확인 필요; 원문 언급만으로 확정하지 않음"),
                {"do": "conflict", "label": "이용시간", "facet": "본문과 상충하는 원문 정보표 이용시간",
                 "missing": "수집 본문과 상세 정보표의 이용시간 상충을 확인함; 검증 전 확정 불가"}),
    "N04": rule(("신흥동 일본식 가옥", "군산신흥동일본식가옥", "군산신흥동일본식가옥(히로쓰가옥)"),
                text("실내.{0,40}(?:개방|관람)|내부.{0,40}(?:개방|관람)", "실내 관람 허용·제한을 명시한 원문"),
                missing("기재된 실내 개방·제한 조건의 현재 적용 여부 확인")),
    "N05": rule(("동국사",), text("대웅전|사찰|절이다|금강선사", "해당 장소 자체 소개 원문",
                                  if_none="동국사 자체 소개·볼거리 원문")),
    "N06": rule(("은파호수공원",), text("(?:한 바퀴|산책|보행)[^\n]{0,80}(?:시간|분)", "보행 소요시간 언급"),
                missing("한 바퀴의 경로·출발점·보행 조건과 소요시간 직접 근거 대조")),
    "N07": rule(("월명공원",), text("월명공원은|정상|공원", "산책 후보의 공원 소개"),
                missing("공원 내부 산책 동선·경유지 순서의 직접 근거")),
    "N08": rule(("말랭이마을",), text("말랭이.{0,5}마을|산비탈|레지던스", "해당 장소 자체 소개 원문",
                                    if_none="말랭이마을 자체 소개 원문")),
    "N09": rule((), {"do": "courses", "pages": ["m2135"], "if_none": "당일 코스 분류에 속한 공식 원문과 경유지 순서"}),
    "N10": rule((), {"do": "courses", "pages": ["m2136"], "if_none": "1박 2일 코스 원문",
                     "need_text": ["1일차", "2일차"], "if_lacking": "1·2일차로 나뉜 경유지의 직접 근거"}),
    "N11": rule((), {"do": "courses", "pages": ["m2107"], "facet": "근대문화유산 코스 순서"},
                missing("경유지 사이 도보 이동·보행 가능 여부(코스가 존재해도 도보임을 의미하지 않음)")),
    "N12": rule((), {"do": "course_stops", "pages": ["m2135", "m2136"], "tokens": ["선유", "장자도", "대장도"],
                     "facet": "관련 명칭을 포함한 코스 순서"},
                text("다리|연결|섬", "섬 자체 소개·연결 근거", {"from": "sources", "names": ["선유도", "장자도", "대장도"]}),
                missing("코스 내 명칭 대응과 현재 이동·접근 조건 확인")),
    "N13": rule((), {"do": "courses", "pages": ["m2137"], "if_none": "2박 3일 코스 원문", "need_text": ["3일차"],
                     "if_lacking": "제목은 2박 3일이나 저장 원문에서 3일차 경유지를 확인하지 못함"}),
    "N14": rule((), text("서울|기차|철도|시내버스|시외버스|고속버스|대중교통", "교통 안내 보조 근거", TRAVEL),
                missing("철도·버스·도보 환승과 각 경유지 접근 방법" + TOUR_LEFT)),
    "N15": rule(("선유도",), text("차량|자동차|주차", "선유도 자체 교통·주차 언급"),
                text("자동차로 진입|선유.{0,20}주차장|주차장", "선유도 관련 교통 안내", {**TRAVEL, "text_all": ["선유"]}),
                text("선유.{0,20}주차장", "선유도 관련 주차장 명칭 근거", {**TRAVEL, "text_all": ["선유"]}),
                missing("선유도 차량 진입·주차장 위치의 직접 근거" + TOUR_LEFT)),
    "N16": rule((), text("서울|기차|철도|시내버스|시외버스|고속버스|대중교통", "교통 안내 보조 근거", TRAVEL),
                missing("서울 출발 기차·버스 노선과 군산 도착 정보" + TOUR_LEFT)),
    "N17": rule(MUSEUM, text("군산역", "군산역과 박물관을 함께 언급한 교통 안내(노선 답변 검토 필요)",
                             {**TRAVEL, "text_all": ["군산역", "박물관"]}),
                missing("군산역→근대역사박물관 교통 경로" + TOUR_LEFT)),
    "N18": rule(RAIL, text("주차", "해당 장소의 원문 주차 언급"), missing("경암동 철길마을 일반 방문객 주차 정보" + TOUR_LEFT)),
    "N19": rule((), text("시티투어|사전예약|운행", "수집된 시티투어 안내(현재 운행 확정 아님)",
                         {"from": "sources", "name_any": ["시티투어"]}, id="regular"),
                {"do": "samples", "pattern": "시티투어", "facet": "기간 한정 공지에 시티투어 존재 언급"},
                missing("현재 운행 여부·해당 날짜 예약 가능 여부·운영조건 재확인 필요", **{"if": "regular"}),
                missing("특정 추석 연휴 증차 공지의 근거와 현재 운행 여부는 구분해야 함; 정기 운영 안내 원문 미확인",
                        unless="regular")),
    "N20": rule((), text("어린이.{0,20}체험|아동.{0,20}체험|어린이박물관", "어린이 시설·체험의 직접 근거", "sources"),
                missing("체험연령·유모차·보호자 동반 등 방문 적합성 확인값")),
    "N21": rule((), text("실내|우천", "실내·우천 언급(이용 제한 문구 포함 가능)", "sources"),
                missing("실내 언급의 허용/제한 맥락·현재 개방·우천 접근 조건 확인; 명칭만으로 적합성 확정 금지")),
    "N22": rule((), text("근대 추억|사진도 찍을", "레트로 또는 사진 촬영의 일부 근거", "sources"),
                missing("각 후보마다 레트로와 사진 촬영 가능 범위를 함께 확인할 근거")),
    "N23": rule((), text("영화[^\n]{0,200}촬영|촬영 영화", "영화 촬영 사실", "sources",
                         if_none="영화·드라마 촬영을 명시한 장소 자체 원문")),
    "N24": rule((), text("야경|야간경관", "야경 직접 근거", "sources", if_none="야경을 명시한 장소 자체 원문")),
    "N25": rule((), text("(?:입장|관람|이용)[^\n]{0,20}무료|무료[^\n]{0,20}(?:입장|관람)", "무료 입장·관람의 원문 언급",
                         "sources"), missing("무료 적용 대상·기간·현재 이용요금 확인")),
    "N26": rule((), text("가을.{0,40}단풍|가을.{0,40}풍경", "가을 직접 근거", "sources",
                         if_none="가을을 명시한 장소 자체 원문")),
    "N27": rule((), text("20\\d{2}|기간|일시|개최", "수집된 행사 일정 언급",
                         {"from": "sources", "name_any": ["축제", "행사"], "name_all": ["시간여행"]}),
                missing("측정 날짜의 연도·월과 행사 적용 기간 및 취소/변경 공지 확인")),
    "N28": rule((), text("20\\d{2}|기간|일시|개최", "수집된 행사 일정 언급", {"from": "sources", "name_any": ["축제", "행사"]}),
                missing("측정 날짜의 연도·월과 행사 적용 기간 및 취소/변경 공지 확인")),
    "N29": rule((), text("독채", "숙소 자체 원문의 독채 언급", {"from": "sources", "kind": "stay"}),
                missing("독채 적용 객실·현재 영업·예약 경로·업주 확인")),
    "N30": rule((), text("메뉴|음식|요리|식당|전문", "음식점 자체 원문", {"from": "sources", "kind": "food"}),
                missing("현재 메뉴·영업 여부 확인; 원문 존재가 맛 평가·순위의 근거는 아님")),
    "P01": rule((), text("독채", "숙소 자체 원문의 독채 언급", {"from": "sources", "kind": "stay"}),
                missing("독채 적용 객실·현재 영업·예약 경로·업주 확인")),
    "P02": rule((), {"do": "courses", "pages": ["m2135"], "if_none": "당일 코스 분류에 속한 공식 원문과 경유지 순서"}),
    "P03": rule(RAIL, text("주차", "해당 장소의 원문 주차 언급"), missing("경암동 철길마을 주차 정보의 직접 출처" + TOUR_LEFT)),
}}


def assess_question(question, places, courses, samples=None, documents=None):
    return qc.assess_question(question, places, courses, samples, documents, rules=RULES, source_name=SOURCE)


def run(*args, **kwargs):
    return qc.run(*args, rules=RULES, **kwargs)


def question(ident):
    return {"id": ident, "group": ident[0], "question": ident + " 검토 질문"}


def place(name, text, slug="place-1"):
    return {"name": name, "slug": slug, "original": {"text": text,
            "source_url": "https://www.city.example/tour/m2080/view/1", "license": "NONE"}}


def course(page="m2135", text="공식 코스\n첫 장소\n둘째 장소", name="A코스"):
    return {"name": name, "source_url": f"https://www.city.example/tour/{page}",
            "original": {"text": text, "source_url": f"https://www.city.example/tour/{page}", "license": "NONE"},
            "stops": [{"name": "첫 장소"}, {"name": "둘째 장소"}]}


def test_name_or_course_stop_match_does_not_supply_operational_answers():
    places = [place("경암동 철길마을", "경암동 철길마을은 마을이다.", "rail")]
    courses = course_candidates([course(text="근대역사박물관\n경암동 철길마을\n숙소\n이성당")])
    for ident in ("N03", "N17", "N18", "N25", "N29", "N30", "P01", "P03"):
        result = assess_question(question(ident), places, courses)
        assert result["answer_status"] == "미확인"
        assert result["missing"]
    assert assess_question(question("N18"), places, courses)["candidate_slugs"] == ["rail"]


def test_compound_description_and_fee_question_stays_partial():
    source = "\n경암동 철길마을은 철로 주변의 마을이다.\n"
    result = assess_question(question("N01"), [place("경암동 철길마을", source)], [])
    assert result["answer_status"] == "일부"
    assert "입장료" in result["missing"][0]
    assert result["evidence"][0]["quote"] in source


def test_official_day_course_satisfies_day_course_but_not_car_free_trip():
    courses = course_candidates([course()])
    assert assess_question(question("N09"), [], courses)["answer_status"] == "답충분"
    assert assess_question(question("P02"), [], courses)["answer_status"] == "답충분"
    assert assess_question(question("N14"), [], courses)["answer_status"] == "미확인"
    assert guide_candidates([], courses)[0]["candidates"] == []


def test_source_period_and_missing_third_day_are_checked_separately():
    courses = course_candidates([course("m2136", "1일차\n첫 장소\n2일차\n둘째 장소"),
                                 course("m2137", "1일차\n첫 장소\n2일차\n둘째 장소", "2박 3일 코스")])
    assert assess_question(question("N10"), [], courses)["answer_status"] == "답충분"
    result = assess_question(question("N13"), [], courses)
    assert result["answer_status"] == "일부"
    assert "3일차" in result["missing"][0]


def test_film_night_autumn_require_explicit_source_text():
    records = [place("초원사진관", "영화의 촬영 장소이다.", "studio"),
               place("은파호수공원", "음악분수와 함께 야경을 연출한다.", "lake"),
               place("월명공원", "가을에는 아름다운 단풍이 보인다.", "park")]
    for ident in ("N23", "N24", "N26"):
        result = assess_question(question(ident), records, [])
        assert result["answer_status"] == "답충분"
        assert result["evidence"]
    for ident in ("N23", "N24", "N26"):
        assert assess_question(question(ident), [place("명소", "관광지 소개")], [])["answer_status"] == "미확인"


def test_guide_candidates_do_not_infer_indoor_from_museum_or_private_house_from_hotel():
    source = "어린이들의 체험학습의 \n장으로 활용한다. 영상관이 있다. 관광호텔이 있다."
    candidates = guide_candidates([place("진포해양공원", source, "jinpo")], course_candidates([course()]))
    by_name = {g["name"]: g for g in candidates}
    assert by_name["아이와 함께"]["candidates"][0]["slug"] == "jinpo"
    assert by_name["아이와 함께"]["candidates"][0]["quote"] in source
    assert by_name["비 오는 날"]["candidates"] == []
    assert by_name["독채 숙소 고르기"]["candidates"] == []
    assert by_name["차 없는 당일여행"]["candidates"] == []


def test_existing_course_slug_reused_by_source_and_name():
    raw = course()
    imported = [{"name": "A코스", "slug": "stable-course", "original": raw["original"]}]
    mapped = course_candidates([raw], imported)[0]
    assert mapped["slug"] == "stable-course"
    assert mapped["slug_registered"] is True


def test_period_limited_citytour_notice_is_partial_without_registered_page():
    samples = [{"name": "2026년 추석 연휴 맞이 시티투어버스 특별 증차 운행!",
                "source_url": "https://www.city.example/tour/m2172/view/9834787",
                "original_text": "2026년 추석 연휴를 맞아 시티투어버스를 특별 증차 운행합니다.\n",
                "original_license": "NONE"}]
    result = assess_question(question("N19"), [], [], samples)
    assert result["answer_status"] == "일부"
    assert result["candidate_slugs"] == []
    assert result["evidence"][0]["quote"] in samples[0]["original_text"]
    assert "현재 운행 여부" in result["missing"][0]
    assert "2026년 추석" in result["evidence"][0]["name"]


def test_reports_keep_n_p_separate_preserve_inputs_and_omit_u(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    original = [place("경암동 철길마을", "경암동 철길마을은 마을이다.")]
    places_path = data / "places.json"
    places_path.write_text(json.dumps(original, ensure_ascii=False), "utf-8")
    raw = tmp_path / "courses.json"
    raw.write_text(json.dumps([course()], ensure_ascii=False), "utf-8")
    questions = tmp_path / "questions.csv"
    with questions.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "group", "question"])
        writer.writeheader()
        writer.writerows(question(f"N{i:02d}") for i in range(1, 31))
        writer.writerows(question(f"P{i:02d}") for i in range(1, 4))
        writer.writerow(question("U01"))
    before = {p: hashlib.sha256(p.read_bytes()).digest() for p in (places_path, raw, questions)}
    reports = tmp_path / "reports"
    results = run(questions, data, raw, reports)
    assert len(results) == 33
    assert sum(r["group"] == "N" for r in results) == 30
    assert sum(r["group"] == "P" for r in results) == 3
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in before.items())
    md = (reports / "question_coverage.md").read_text("utf-8")
    assert "N 核心" not in md
    assert "N 핵심 30문항" in md and "P 플랫폼 제외 3문항" in md
    assert "U01" not in md
    assert (reports / "guide_candidates.md").exists()


def test_changed_question_ids_require_review_instead_of_silent_remapping(tmp_path):
    questions = tmp_path / "questions.csv"
    questions.write_text("id,group,question\nN01,N,원문 질문\n", "utf-8")
    with pytest.raises(ValueError, match="fixed N30/P3"):
        run(questions, tmp_path, tmp_path / "missing.json", tmp_path / "reports")


def test_collected_dongguksa_and_mallaengi_originals_replace_stale_no_source_claims():
    # Exact excerpts observed in the saved 2026-10-08 source records.
    temple = "대웅전은 건축 자재를 일본에서 가져와 지었으며, 우리나라의 전통 사찰과 달리 승려들의 거처인 요사와 복도로 연결된 것이 특징이다."
    village = "산비탈에 위치한 말랭이 마을에는 예술인 레지던스 9동과 전시관 8동이 조성되어 있으며 골목길 곳곳에 그려진 벽화가 볼거리를 제공해주고 있다."
    originals = [place("동국사", temple, "동국사"), place("말랭이 마을", village, "말랭이-마을")]
    for ident, text, slug in (("N05", temple, "동국사"), ("N08", village, "말랭이-마을")):
        result = assess_question(question(ident), originals, [])
        assert result["answer_status"] == "답충분" and not result["missing"]
        assert result["candidate_slugs"] == [slug]
        assert result["evidence"][0]["quote"] in text


def test_verified_address_fact_resolves_location_but_unsourced_address_does_not():
    studio = place("초원사진관", '영화 "8월의 크리스마스"의 촬영 장소이다.', "studio")
    studio["facts"] = {"address": "전북특별자치도  군산시 구영2길 12-1 (신창동)"}
    assert assess_question(question("N02"), [studio], [])["answer_status"] == "일부"
    studio["facts_source"] = {"provider": SOURCE, "checked_at": "2026-10-08"}
    result = assess_question(question("N02"), [studio], [])
    assert result["answer_status"] == "답충분"
    assert any(e.get("source_field") == "facts.address" for e in result["evidence"])


def test_actual_museum_conflicting_source_hours_remain_insufficient():
    original = "(3월~10월) 09:00 ~ 18:00\n(11월~2월) 09:00 ~ 17:00\n매주 월요일 휴관"
    documents = source_documents([{"name": "근대역사박물관", "original_text": original,
        "source_url": "https://www.city.example/tour/m2080/view/305395",
        "source_fields": [{"label": "이용시간", "value": "09:00~21:00(입장마감 20:30)"}]}], "raw_detail_source")
    result = assess_question(question("N03"), [], [], documents=documents)
    assert result["answer_status"] == "일부"
    assert any("상충을 확인함" in missing for missing in result["missing"])
    assert any(e["source_type"] == "raw_source_field" for e in result["evidence"])


def test_collected_citytour_static_page_is_evidence_without_claiming_live_operations():
    documents = source_documents([{"name": "시티투어 소개",
        "source_url": "https://www.city.example/tour/m2102",
        "original_text": "군산 시티투어는 사전예약을 통해 운영하고\r\n                있습니다.",
        "original_license": "NONE"}], "static_source")
    result = assess_question(question("N19"), [], [], documents=documents)
    assert result["answer_status"] == "일부" and result["candidate_slugs"] == []
    assert result["evidence"][0]["source_type"] == "static_source"
    assert result["evidence"][0]["slug_registered"] is False
    assert "현재 운행 여부" in result["missing"][0]
    assert not any("안내 원문 미확인" in m for m in result["missing"])


def test_collected_seonyu_traffic_is_partial_not_unsupported_or_current_confirmation():
    text = "신시도 새만금광장 – 무녀도 – 선유도 – 장자도 까지 자동차로 진입 가능하나\n주차장이 협소하오니 참고하시어 불편함이 없으시기 바랍니다."
    documents = source_documents([{"name": "교통안내", "original_text": text,
        "source_url": "https://www.city.example/tour/m2197"}], "static_source")
    result = assess_question(question("N15"), [], [], documents=documents)
    assert result["answer_status"] == "일부"
    assert result["evidence"][0]["quote"] in text
    assert result["missing"]


def test_editorial_summary_faq_never_supply_missing_raw_evidence():
    item = place("동국사", "자료")
    item.update(summary="대웅전과 사찰이 있다.", faq=[{"q": "어떤 절?", "a": "대웅전이 있다."}])
    assert assess_question(question("N05"), [item], [])["answer_status"] == "미확인"


def test_explicit_indoor_closure_is_evidence_but_never_rain_guide_candidate():
    text = "문화재 보호를 위하여 실내 개방은 하지 않습니다."
    originals = [place("군산신흥동일본식가옥(히로쓰가옥)", text)]
    result = assess_question(question("N04"), originals, [])
    assert result["answer_status"] == "일부"
    assert result["evidence"][0]["quote"] == text
    assert guide_candidates(originals, [])[2]["candidates"] == []


def test_run_reads_raw_auxiliary_documents_without_modifying_them(tmp_path):
    data, raw, reports = tmp_path / "data", tmp_path / "raw", tmp_path / "reports"
    data.mkdir()
    raw.mkdir()
    (data / "places.json").write_text("[]")
    raw_courses = tmp_path / "courses.json"
    raw_courses.write_text("[]")
    auxiliary = raw / "static_documents.json"
    auxiliary.write_text(json.dumps({"documents": [{"name": "시티투어 소개", "original_text": "군산 시티투어는 사전예약으로 운영합니다.",
                                                   "source_url": "https://www.city.example/tour/m2102"}]}))
    questions = tmp_path / "questions.csv"
    with questions.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "group", "question"])
        writer.writeheader()
        writer.writerows(question(f"N{i:02d}") for i in range(1, 31))
        writer.writerows(question(f"P{i:02d}") for i in range(1, 4))
        writer.writerow(question("U01"))
    before = {p: p.read_bytes() for p in (auxiliary, questions, raw_courses, data / "places.json")}
    results = run(questions, data, raw_courses, reports, raw_dir=raw)
    assert len(results) == 33 and all(r["group"] in ("N", "P") for r in results)
    assert next(r for r in results if r["id"] == "N19")["evidence"]
    assert all(p.read_bytes() == content for p, content in before.items())
    assert "공개 페이지 slug 미등록" in (reports / "question_coverage.md").read_text("utf-8")


def test_only_tourapi_and_the_sites_own_source_count_as_recorded_facts():
    studio = place("초원사진관", '영화 "8월의 크리스마스"의 촬영 장소이다.', "studio")
    studio.update(facts={"address": "샘플시 샘플로 1"}, facts_source={"provider": SOURCE, "checked_at": "2026-10-08"})
    other_site = qc.assess_question(question("N02"), [studio], [], rules=RULES, source_name="다른 시 문화관광")
    assert other_site["answer_status"] == "일부" and "주소·위치 직접 근거" in other_site["missing"]
    studio["facts_source"] = {"provider": qc.TOURAPI_PROVIDER, "checked_at": "2026-10-08"}
    assert qc.assess_question(question("N02"), [studio], [], rules=RULES)["answer_status"] == "답충분"


def test_rules_are_checked_and_a_question_without_rules_stays_unconfirmed(tmp_path):
    assert rules_problems(RULES) == []
    bad = {"groups": {"N": 1}, "questions": {"N01": {"steps": [{"do": "guess"}, {"do": "text", "pattern": "("},
                                                                {"do": "text", "pattern": "x", "facet": "f", "in": "web"}]}}}
    problems = rules_problems(bad)
    assert len(problems) == 4 and any("guess" in p for p in problems) and any("정규식" in p for p in problems)
    assert rules_problems({"questions": {}}) == ['groups: {"군": 문항 수} 객체여야 합니다']
    with pytest.raises(ValueError, match="규칙 오류"):
        qc.run(tmp_path / "q.csv", tmp_path, None, tmp_path / "reports", rules=bad)
    result = qc.assess_question(question("N99"), [place("경암동 철길마을", "마을은 있다.")], [], rules=RULES)
    assert result["answer_status"] == "미확인" and result["missing"] == [qc.NO_RULE]


def test_unregistered_course_locator_uses_the_site_id_prefix(tmp_path):
    assert course_candidates([course()], [], "city")[0]["slug"] == "city-course-m2135-1"
    assert course_candidates([course(), course(name="B코스")])[1]["slug"] == "course-m2135-2"
    data = tmp_path / "data"
    data.mkdir()
    (data / "places.json").write_text("[]", "utf-8")
    (data / "site.json").write_text(json.dumps({"id_prefix": "city", "source": {"name": SOURCE}}), "utf-8")
    raw = tmp_path / "raw" / "city_courses.json"
    raw.parent.mkdir()
    raw.write_text(json.dumps([course()], ensure_ascii=False), "utf-8")
    questions = write_questions(tmp_path / "questions.csv")
    results = run(questions, data, raw, tmp_path / "reports")
    assert next(r for r in results if r["id"] == "N09")["candidate_slugs"] == ["city-course-m2135-1"]


def test_cli_reads_the_rules_file_and_requires_data(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "places.json").write_text(json.dumps([place("경암동 철길마을", "경암동 철길마을은 마을이다.")],
                                                 ensure_ascii=False), "utf-8")
    (data / "site.json").write_text(json.dumps({"id_prefix": "city"}), "utf-8")
    questions = write_questions(tmp_path / "questions.csv")
    rules = tmp_path / "question_rules.json"
    rules.write_text(json.dumps(RULES, ensure_ascii=False), "utf-8")
    reports = tmp_path / "reports"
    assert qc.main(["--data", str(data), "--questions", str(questions), "--raw", str(tmp_path / "raw"),
                    "--reports", str(reports)]) == 0                    # rules beside the questions by default
    counts = json.loads(capsys.readouterr().out)
    assert set(counts) == {"N", "P"} and sum(counts["N"].values()) == 30 and counts["N"]["일부"] >= 1
    assert "N 핵심 30문항" in (reports / "question_coverage.md").read_text("utf-8")
    rules.write_text(json.dumps({"groups": {"N": 30}, "questions": {"N01": {"steps": [{"do": "x"}]}}}), "utf-8")
    assert qc.main(["--data", str(data), "--questions", str(questions), "--rules", str(rules)]) == 1
    assert "규칙 오류" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        qc.main(["--data", str(data), "--questions", str(questions), "--rules", str(tmp_path / "none.json")])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        qc.main(["--questions", str(questions)])
    assert exc.value.code == 2 and "--data" in capsys.readouterr().err


def write_questions(path):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "group", "question"])
        writer.writeheader()
        writer.writerows(question(f"N{i:02d}") for i in range(1, 31))
        writer.writerows(question(f"P{i:02d}") for i in range(1, 4))
    return path
