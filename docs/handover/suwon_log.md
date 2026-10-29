# 수원각(Suwongak) 구축 작업 로그

## 0단계: 저장소 준비 및 프로젝트 초기 설정
- 일시: 2026-10-23
- GitHub 원격 저장소 생성: `https://github.com/hoon7624g-web/Suwon`
- 로컬 저장소 초기화: `c:\Users\USER\Downloads\Suwon` (`git init -b main`)
- 군산각(`gunsan`) 마스터 프롬프트(`docs/master/region_master_prompt.md`) 및 다도시 엔진(`pipeline/city.py`) 기반으로 `data/suwon/site.json`, `data/suwon/themes.json`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/rights.md` 수원시 맞춤 재작성.
- 수원시 법정동 코드: `lDongRegnCd=41`(경기도), `lDongSignguCd=110/111/113/115/117`(수원시 전체·장안구·권선구·팔달구·영통구), 구 코드 `areaCode=31, sigunguCode=13`.
- 브랜드 아이덴티티 구성: 수원화성 적벽돌·단청 주칠(`#7A2328`) + 성곽 정자 황금 포인트(`#FFD54A`) 기반으로 `templates/assets/brand/suwongak-symbol.svg`, `suwongak-app-icon.svg`, PNG 아이콘 세트(`icon-512.png`, `icon-192.png`, `apple-touch-icon.png`, `favicon-32.png`, `favicon-16.png`, `favicon.ico`) 생성 완료.

## 1~2단계: 한국관광공사 TourAPI 전 서비스 수집 및 병합
- `KorService2` (장안구 111, 권선구 113, 팔달구 115, 영통구 117, 수원시 110): 장소 469곳, 행사 18건, 여행코스 10건 수집 및 상세(`detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`) 전량 수집.
- 8개 외국어 TourAPI 서비스(`EngService2`, `JpnService2`, `ChsService2`, `ChtService2`, `GerService2`, `FraService2`, `SpnService2`, `RusService2`): 총 933건 수집 및 병합.
- 무장애 여행(`KorWithService2` 86건), 반려동물 동반(`KorPetTourService2` 16건), 관광사진갤러리(`PhotoGalleryService1` 수원 키워드 214건, KOGL-1), 고캠핑(`GoCamping` 수원 매칭), 두루누비(`Durunubi` 코리아둘레길 경기·수원 구간) 전량 수집 및 병합.
- 카카오맵(`panel3`) 공식 상세 연동(463/469곳 매칭)으로 누락된 이용시간·휴무일·주차·메뉴·전화번호 보강.

## 3~5단계: 한국어 데이터 정제 및 에디토리얼 콘텐츠 구성 (`tools/suwon_content.py`)
- `data/suwon/places.json`: 전체 683곳 중 색인 기준을 충족하는 **400곳 공개(`published`)** (볼거리 163곳, 먹거리 210곳, 숙소 27곳). 전 장소 비동어반복 한국어 요약문 및 고유 존댓말 FAQ(총 934문항, 중복 0건) 생성.
- `data/suwon/events.json`: 수원화성문화제, 정조대왕 능행차, 수원화성 미디어아트, 수원 국가유산야행 등 18건 구성 및 검증.
- `data/suwon/courses.json`: 5대 권역 및 도심 정원을 아우르는 6개 여행 코스(총 42개 정류장, 100% 공개 장소 연결) 구성.
- `data/suwon/guides.json`: 수원화성·행궁·성곽, 아이 동반, 비 오는 날 실내 박물관·미술관, 반려동물 동반, 왕갈비·통닭·월요일 영업 맛집, 호텔·한옥·캠핑 숙소 등 6편 작성 (`guide_content.py` 오류 0건).
- `data/suwon/videos.json`(공식 YouTube 41편), `data/suwon/abroad.json`(해외 기사 9건·영상 5건) 및 `abroad_highlights.json`, `data/suwon/ask.json`(9개 언어 챗봇 안내), `data/suwon/art.json`(87개 슬롯) 작성.
- `tools/kogl1_media.py`로 KOGL-1 대표 사진 36장(파생본 216개, 14.87MB) 로컬 생성 및 `image_sizes.json`(1,342건) 기록.

## 6~8단계: 8개 외국어 번역팩(`en`, `ja`, `zh-hans`, `zh-hant`, `de`, `fr`, `es`, `ru`) 구축 및 검증 (`tools/suwon_i18n.py`)
- `tools/en_content.py names --data data/suwon --lang <lang> --offline` 및 `tools/suwon_i18n.py`를 통해 8개 외국어 전체(`strings.json`, `places.json`, `guides.json`, `courses.json`, `events.json`, `names.json`) 생성.
- TourAPI 외국어 오매칭(`tourapi-4067984` 수원화성 성곽길, `tourapi-482258` 팔달사, `tourapi-130094` 수원야외음악당 등) 교정 및 러시아어 라틴 문자 장소명 키릴 문자화 완료.
- 8개 언어 전체 검증 결과: `Total issues across all 8 languages: 0`.

## 9단계: 정적 사이트 빌드, 테스트 및 배포 준비
- `py tools/build_public.py --data data/suwon --out public`: 총 3,814 페이지 생성, `qa_errors: 0`, `dead_links: 0`, `en_stale_skipped: 0`, `intl_untranslated: 0`.
- `py tools/quality_report.py --data data/suwon --out public --md docs/handover/suwon_quality.md` 리포트 생성 완료.
- `pytest` 및 `node --test` 전체 자동화 테스트 스위트 실행 및 GitHub `origin main` 푸시 진행.
- 2026-10-29: 질문형 가이드 8편(guide-07~14: 월요일 휴관·휠체어 대여·전통시장·반려동물 동반 가능/불가·주차 요금·이른 아침 식당·23:00 넘어 여는 식당·입장료)을 draft로 추가(check-guide 통과, 공개·번역은 운영자 결정 뒤). guide-04 번호는 2026-10-24에 내린 가이드 것이라 비워 둠.
