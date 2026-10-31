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

## 2026-10-31 군산각 오늘 변경 이식(운영자 요청 '위 사이트들에도 병렬적으로 반영')
- 원본 `hoon7624g-web/gunsan` `claude/magical-noether-togzxp`(b5e1fb236e) 안내서 `docs/handover/port_2026-10-31.md` 1·2·7절을 기능 단위로 3-way 이식(기준 2d4ed5de3e): PC 왼쪽 탭 패널·휴대폰 메뉴 묶음, 코스 목록 카드, AI 챗봇 버튼 확대, 장소 출처 칸 축소, 홈 고정 행사(`pin_home`, 수원은 고정 행사 없음), 챗봇 대문자 약어 매체 인식, 오늘의 상태 카드·조건으로 찾기 칩·영업 확인·이어서 많이 간 곳(데이터 파일이 생기면 표시), 일출·일몰·교통 시간표 엔진(데이터 없으면 페이지 없음), 글꼴 굵기 400/700, 변화 감시 도구(`tools/watch_updates.py`: TourAPI 행사·crowd/almanac 상태만 — 보도자료·인허가·조석은 수원에 해당 체계가 없어 뺌).
- 날씨각 위젯: `site.json` `weather.region_code` 4111500000(경기 수원시 팔달구, 홈 첫 권역)·`area` 팔달구. 날씨각 첫 화면 카드 디자인(밤 남색 하늘·별·달 위상·점수·구름·'지금은 ○○각!'·상태줄·아침/낮/저녁/지금 4칸), '출처' 표기 없음. 군산 저장소에 'ui(weather)' 커밋이 없어 안내서 7절과 weather.o2o.kr 실제 화면대로 직접 구현(`templates/assets/weather.js`, `css/80-side.css`, 아이콘 `assets/wx/`).
- 수원 맞춤: 도시 값은 site.json·city(`city=`)로, 코스 그룹 ID는 slugs 방식 유지, '·' 줄바꿈 단위 뒤 `<wbr>`(긴 코스 제목 넘침), 화면 전환 opt-in을 head 인라인으로(뒤로 가기 오류).
- 안내서 3절 데이터(인허가·연관 관광지·천문연·TAGO)는 `DATA_GO_KR_KEY`·`TOURAPI_KEY`가 이 환경에 없어 하지 않음(키 필요). 4절(대표값 방식·카카오맵)은 수원 운영자 결정이 없어 옮기지 않음.
- 발견: 가이드 guide-05 '월요일 영업·맛집'에 매주 월요일 휴무인 곳 2곳(리틀본수원갈비집·진미통닭)이 들어 있음 — 내용 정정 필요(테스트에 xfail로 표시).
- 확인: 빌드·validate preview·sample·production 오류 0. 바뀐 기능 테스트를 파일 하나씩 통과(사이드 패널·날씨 카드 17, 코스 카드 7, 조건 칩 14+xfail 1, 오늘의 상태 54, 감시 도구 12 등). 전체 91개 파일 중 test_ask_browser 3건은 이식 전(HEAD)에도 실패하던 것(1440px 홈 챗봇 버튼 기대가 test_present와 서로 다름 — HEAD 6건 → 3건). 360·390·1440 캡처 가로 넘침 0. 브라우저 테스트용 Python Playwright(1.63.0, 설치된 Chromium과 같은 버전)를 설치해 돌림.
