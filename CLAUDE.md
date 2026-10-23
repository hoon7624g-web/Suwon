# CLAUDE.md — 수원각 (수원 여행 실증 사이트)

> 이 파일이 최우선 지시다. 기준 엔진: 군산각 `6a26206c4`(`hoon7624g-web/gunsan`, `https://gunsan.webforai.kr`) · 마스터 프롬프트 v1.0(`docs/master/region_master_prompt.md`) · 다도시 확장 구조(`pipeline/city.py`)
> 작업 기록: `docs/handover/suwon_log.md` · 보고서: `docs/handover/suwon_report.md` · 데이터 표준: `docs/02_page_standard.md` · 이용조건: `docs/rights.md`

## 1. 무엇을 만드는가
여행자가 실제로 쓰는 수원 여행 사이트이자, 공개 후 AI 답변엔진 인용·유입을 측정할 실험 사이트다. 군산각에서 검증한 엔진(빌드·검증·구조화 데이터·화면·챗봇·AI 코스 만들기·9개 언어)을 그대로 쓰고, 도시마다 다른 값은 `data/suwon/site.json`과 `pipeline/city.py`에 둔다.

**성공 기준 5가지**
1. 공개 대상 장소 페이지가 **방문 판단 정보**(이용시간·쉬는 날·요금·주차·전화·체크인)로 채워져 있다.
2. **얇은 페이지는 색인되지 않는다.** 색인 기준은 3절 8번이다.
3. 사람이 **검수와 공개 설정만** 하면 공개할 수 있다.
4. 한국어와 외국어 8개 판이 같은 공개 범위로 나간다.
5. 새 사이트 어디에도 **군산 데이터·문장·그림·키·주소가 섞이지 않는다.**

## 2. 기본 설정
| 항목 | 설정 |
|---|---|
| 주소 | `https://suwon.webforai.kr` (`data/suwon/site.json` `site_url`) |
| 이름 | **'수원각'** / 외국어 8개 판 **'Suwongak'**(한자권: 水原閣·水原阁, 러시아어: Сувонгак). 홈 첫 화면 큰 제목은 '수원 여행의 모든 것' |
| 페이지 주소 | **영문 슬러그**(국어의 로마자 표기법, `[a-z0-9-]`만). 한 번 공개한 슬러그는 바꾸지 않는다(`slug`에 저장) |
| 범위 | 경기도(`lDongRegnCd` 41) 산하 `수원시 장안구`(111)·`권선구`(113)·`팔달구`(115)·`영통구`(117) 및 `수원시`(110) 전역 — 5개 여행 권역(`anchors`: 수원화성·화성행궁·행리단길, 팔달문·전통시장·통닭거리, 광교호수공원·박물관·영통, 만석공원·광교산·장안, 일월수목원·서호공원·권선) |
| 언어 | 한국어 + 8개 외국어(`ko`·`en`·`ja`·`zh-hans`·`zh-hant`·`de`·`fr`·`es`·`ru`) = 9개 언어. 언어판은 `data/suwon/<언어>/places.json`이 있을 때만 생성된다 |
| 지도 | 오픈소스 지도(Leaflet + OpenStreetMap) 기본. 도메인 연결 및 카카오 개발자 콘솔 등록 후 카카오맵 전환 가능 |

## 3. 지켜야 할 규칙
1. **사실은 출처 데이터에서만** 가져온다(TourAPI·수원시 문화관광 공식 자료·해당 시설 공식 홈페이지). 없는 값은 블록마다 "확인 필요: 요금·주차"처럼 한 번만 쓴다. 추정이나 일반 지식으로 채우지 않는다.
2. **필드별 출처**: 필드마다 출처와 확인일을 남긴다(`fact_sources`). 두 출처 값이 다르면 둘 다 보여 주고(`fact_alternatives`) "방문 전 전화 확인"을 붙인다. 한쪽을 임의로 고르지 않는다.
3. **시 원문과 사진**: 수원문화관광(`suwon.go.kr/web/visitsuwon/`) 및 수원문화재단(`swcf.or.kr`)은 페이지별 공공누리 표시가 없거나 제한적이므로 군산과 같은 규칙을 적용한다 — 원문은 링크로만, 설명은 우리 문장으로(원문과 15자 이상 연속 일치 금지), 표의 값(시간·요금·메뉴·지정 업소)은 값 그대로 써도 된다. 확인 결과는 `docs/rights.md`에 적는다.
4. **TourAPI 이미지**: `cpyrhtDivCd`가 Type1·Type3인 것만, "출처: 한국관광공사". Type3은 자르기·확대·보정 금지. 홈 첫 화면처럼 자르기가 필요한 곳은 제1유형만. overview 문장은 게재하지 않고 사실 확인용으로만 쓴다.
5. **요약 문장**: 답부터 쓰는 평서문(존댓말). "○○은 경기도 수원시에 있는 ○○입니다"로만 끝내지 않고 그 장소만의 사실을 하나 이상 넣는다. 쓸 사실이 없으면 짧게 두고 색인에서 뺀다.
6. **FAQ**: "~나요?/~인가요?"로 통일, 같은 질문을 여러 장소에 반복하지 않는다, 데이터로 답할 수 없는 질문은 만들지 않는다.
7. **공개는 사람이 정한다**: `status=published`·`reviewed_at`·`approved_at`, `site.json`의 `site_url`·`ga4_id`·`gtm_id`·`brand`·`operator`·`publish_rules`·`crawler_policy`·`search_verification`, noindex·robots 해제는 운영자 지시를 따른다.
8. **색인 기준(production)**: 유형별 필수 정보 2개 이상(`pipeline/schema.py` `INDEX_KIND_GROUPS`) + 요약 규칙 + 검수일 또는 운영자 공개 승인. 미달 페이지는 noindex, sitemap·llms.txt에서 뺀다.
9. **비밀값**: `TOURAPI_KEY`는 환경 변수나 `.env`(커밋 금지). `.env`를 열어 보거나 출력하지 않는다. 로그에서는 키 문자열만 가린다.
10. **제3자 콘텐츠 금지**: 네이버 플레이스·블로그·리뷰·평점 복제 금지. 회원가입·예약·결제 없음. 근거 없는 업체 추천 금지.
    - 사이트 안내 챗봇(`api/chat.js`, `chatbot/`): Claude Haiku 5.5(`claude-haiku-5-5`), 키는 Vercel 환경 변수 `ANTHROPIC_API_KEY`(커밋·출력 금지). 이 사이트 데이터로만 답하고 답마다 해당 페이지 링크를 단다.
    - 해외에서 본 수원(`/abroad/`): 외신·해외 매체 기사와 SNS 게시물은 원문·사진을 옮기지 않고 우리가 쓴 한 줄 소개(`note`) + 원문 링크 + 짧은 원문 인용(`<blockquote lang cite>`)으로만 싣는다.
11. **AI 그림(일러스트)**: 배경·캠페인 그림·장식으로만 쓰고 alt는 '일러스트: '로 시작한다. 소개 페이지에 생성형 AI 고지를 적는다. 장소 사진 자리와 장소 구조화 데이터에는 쓰지 않는다.
12. **화면에 확인일을 표시하지 않는다**. 구조화 데이터의 날짜는 남긴다.

## 4. 하지 말 것
- 검증 규칙을 완화해서 통과시키지 않는다. 테스트·문서 분량을 목표로 삼지 않는다.
- 빈 데이터를 장식으로 덮지 않는다(가짜 사진, 가짜 지도, 큰 빈 표지). 데이터가 없으면 그 장을 뺀다.
- 첫 화면 내용을 스크립트로 숨겼다가 보여 주지 않는다. 모바일 LCP ≤ 2.5초, CLS ≤ 0.1, 첫 방문 글꼴 ≤ 300KB.
- 도시 이름·권역·출처 같은 도시 값을 코드에 새로 박지 않는다. `data/suwon/site.json`이나 `pipeline/city.py`에 둔다.

## 5. 명령어
```bash
python -m pip install -r requirements.txt
python -m pytest

# TourAPI 진단 및 수집 (TOURAPI_KEY가 .env 또는 환경 변수에 있을 때)
python tools/tourapi_doctor.py --data data/suwon --keyword 화성행궁       # 1. 키·연결 진단
python tools/tourapi_doctor.py --data data/suwon --check-region          # 2. 경기도 수원시 4개 구 법정동 코드 확인
python tools/tourapi_harvest.py --data data/suwon                        # 3. TourAPI 전 서비스 캐시 수확
python tools/tourapi_bulk.py --data data/suwon --details --add-new --events --gallery --max-calls 900  # 4. 장소·상세·행사·사진 병합
python tools/harvest_merge.py --data data/suwon --photos --pet --camping --add-camps --apply           # 5. 관광사진·반려동물·고캠핑 병합
python tools/tourapi_bulk.py --data data/suwon --barrier-free --max-calls 600                          # 6. 무장애 여행 정보 병합
python tools/image_sizes.py --data data/suwon                            # 7. 사진 크기 기록

# 빌드·검증
python -m pipeline.build --data data/suwon --out dist-preview --mode preview
python -m pipeline.validate --data data/suwon --out dist-preview --mode preview
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/quality_report.py --data data/suwon --out dist-preview --md reports/quality_latest.md
python tools/build_public.py --data data/suwon --out public              # 공개 빌드
```
- `public/`은 `python tools/build_public.py --data data/suwon --out public`으로만 갱신한다. 직접 고치지 않는다.
- `main`에 push하면 곧 배포된다.
