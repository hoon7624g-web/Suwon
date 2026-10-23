# 수원각(Suwongak) 구축 최종 보고서

## 1. 개요
- **사이트명**: 수원각 (`Suwongak`)
- **공개 도메인**: `https://suwon.webforai.kr`
- **GitHub 저장소**: `https://github.com/hoon7624g-web/Suwon`
- **대상 지역**: 경기도 수원시 전역 (장안구·권선구·팔달구·영통구)
- **지원 언어**: 9개 언어 (`ko`, `en`, `ja`, `zh-hans`, `zh-hant`, `de`, `fr`, `es`, `ru`)
- **브랜드 컬러**: 수원화성 적벽돌·단청 주칠(`#7A2328`) + 성곽 정자 황금 포인트(`#FFD54A`)

## 2. 데이터 및 콘텐츠 지표 (`data/suwon/`)
| 구분 | 수량 | 비고 |
|---|---:|---|
| 전체 수집 장소 (`places.json`) | 683곳 | TourAPI 전 서비스(`KorService2`, 8개 다국어, 무장애, 반려동물, 사진갤러리, 고캠핑, 두루누비) + 카카오맵 통합 |
| 공개 장소 (`status=published`) | 400곳 | 볼거리 163곳, 먹거리 210곳, 숙소 27곳 (전량 `indexable=True`) |
| 색인 대상 장소 (`full` 등급) | 400곳 | 볼거리 163곳, 먹거리 210곳, 숙소 27곳 |
| 무장애 여행 정보 병합 | 86곳 | `KorWithService2` 출입구·휠체어·장애인화장실·점자블록·엘리베이터·수유실 |
| 반려동물 동반 정보 병합 | 16곳 | `KorPetTourService2` 동반 가능 구역·목줄·이동장 기준 |
| 공공누리 제1유형 로컬 미디어 | 36장 | `templates/assets/media/` 216개 AVIF/WebP 파생본 (14.87MB, 15MB 예산 준수) |
| 이미지 크기 메타데이터 | 1,342건 | `data/suwon/image_sizes.json` (원본 732건 + 로컬 파생본 610건, CLS 방지) |
| 축제·행사 (`events.json`) | 18건 | 수원화성문화제, 정조대왕 능행차, 수원화성 미디어아트, 수원 국가유산야행, 수원재즈페스티벌 등 |
| 여행 코스 (`courses.json`) | 6건 | 수원화성·행궁 왕궁 기행, 팔달문·전통시장·통닭거리·행리단길, 연무대·플라잉수원·동북 성곽, 광교호수공원·아쿠아플라넷·박물관, 일월수목원·스타필드·만석공원·해우재, 서호공원·농업박물관·상상캠퍼스·월화원 |
| 여행 가이드 (`guides.json`) | 6편 | 수원화성·행궁·성곽, 아이 동반, 비 오는 날·실내 박물관·미술관, 반려동물 동반, 왕갈비·통닭·월요일 영업 맛집, 호텔·한옥·캠핑 숙소 |
| 공식 영상 (`videos.json`) | 41편 | 수원시·수원문화재단·한국관광공사 등 공식 채널 (YouTube oEmbed 검증 완료) |
| 해외 반응 (`abroad.json`) | 14건 | UNESCO·외신·해외 관광청 기사 9건 + 해외 영상 5건 (`abroad_highlights.json` 9건 포함) |
| 다국어 번역팩 | 8개 언어 | `en`, `ja`, `zh-hans`, `zh-hant`, `de`, `fr`, `es`, `ru` 각 400개 장소·6개 가이드·6개 코스·18개 행사 완비 (`Total issues: 0`) |

## 3. 품질 검증 결과
- **한국어 가이드 검증 (`tools/guide_content.py`)**: 오류 0건
- **영문 및 7개 다국어 검증 (`tools/suwon_i18n.py`, `en_site`, `intl_content`)**: `en_stale_skipped: 0`, `intl_untranslated: 0`, `intl_skipped: 0`, `missing_strings: []`
- **공개 빌드 검증 (`tools/build_public.py --data data/suwon --out public`)**: 총 `3,814` 페이지 생성, `qa_errors: 0`, `dead_links: 0`
- **정보 품질 리포트 (`tools/quality_report.py`)**: 얇은 페이지 `0건`, 상투적 첫 문장 `0건`, FAQ `934개` 전량 존댓말(`100%`) 및 중복 질문 `0건`
- **자동화 테스트 (`pytest`, `node --test`)**: 전 항목 통과
