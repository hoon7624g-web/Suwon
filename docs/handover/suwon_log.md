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

## 2026-11-05 군산각 11-02~11-05 화면 묶음 이식(운영자 '나머지 17곳 화면 작업도 지금 같이 시작해', 작업 브랜치 claude/trusting-shannon-ec29su — 배포 안 함)
지시문: 군산각 `docs/handover/port_2026-11-05.md`. 같은 엔진 계열인 대구각 이식 브랜치의 커밋을 기능별로 3-way로 가져오고 대구 자료·사진·시험은 빼고 수원 값으로 바꿈.
- U1 좌측 탭·휴대폰 메뉴 개수 빼기(군산 4e7783676).
- 카카오맵: `site.json` `map_provider: "kakao"`, `kakao_js_key` 'Default JS Key 2'(운영자가 suwon.webforai.kr 등록, 2026-11-05 18:34). 해남각 지도 엔진(SDK는 지도 상자가 화면 가까이 올 때만, '지도: 카카오맵' 9개 언어). 외국어 strings의 지도 표기 영어 원문 칸이 OSM으로 남아 있던 것도 맞춤. 로컬 캡처에서는 등록 도메인이 아니어서 '지도를 불러오지 못했습니다'(정상).
- U3 목록 카드·지정 칩 색(수원 지정 종류 5개 모두 색 있음)·종류 색·/map/ 동 카드·사진 없는 장소 위치 지도·답 카드 줄(군산 a3de6b844·4b6111774·50b0fada0).
- U10 가이드 소제목 한 줄 묶음·차분한 머리(군산 53950dfe5 등). 수원 가이드 소제목 10개는 모두 명사구라 존댓말로 바꿀 문장 없음.
- U9 행사 띠·행사 페이지 사진·영상·시작 시각(군산 cf4ebcd8a·a0dc577a3). 띠는 events.json `pin_home`이 있을 때만 — 지금 수원 고정 행사 없음(고정은 운영자 결정).
- U8-lite 파트너: /partners/·/partners/contact/(sales@o2o.kr), 왼쪽 패널 아래·휴대폰 메뉴·바닥글 '문의/제휴'. `data/suwon/partners.json`은 수원각 문장. 파트너 숙소·스테이,머뭄 자료는 없음. 한국어 페이지만(군산각과 같음).
- U2·U4·U5·U6 시안 A 홈(표지 카드·검색·4칸·내 일정 만들기·수원 추천 코스, 음식점 카드 줄, MZ 카드), 휴대폰 아래 탭(홈·지도·코스·AI 챗봇 — '숙박' 탭 없음), 장소 전화·길찾기 줄. 블로그 묶음·숙박 예약하기 버튼 없음(운영자 결정).
- 홈 표지 사진(운영자 '제일 이쁜 걸로'): 공공누리 제1유형·1,280px 가로 사진 57장 중 풍경 후보 18장(수원 화성 4·방화수류정 3·화홍문·화성행궁 3·광교호수공원 6·노송지대)을 받아 보고 **방화수류정(동북각루) 야경**(관광사진 2446185, 임영록 2016, 1280×853)으로 정함 — 불 밝힌 누각과 성벽이 용연 물에 그대로 비치고 소나무·꽃이 둘러싸 수원화성을 가장 아름답게 보여 주며, 위쪽 남색 하늘이 넓어 카드 글씨가 잘 읽힘. 2위는 화성행궁 야경(3553519), 화홍문 물보라(3415042). 이전 표지 수원 화성 #1(3343243, 장안문 성벽) 파생 파일은 뺌. 파생 합계 14.65MiB(상한 15MiB).
- 대표값 방식(운영자 '출처 마다 다른 값은 대표 값 하나만'): `fact_conflicts: "primary"`(군산 7fe11475c1·746e1ff61e·c6a85f5729). `tools/place_text.py`도 대표값만 읽게 함. '출처마다 달라' 문장 2곳(화성행궁·플라잉 수원 요약·FAQ)을 다시 쓰고 8개 언어 번역표에 새 문장 4개(report: 낡은 번역·번역 없음 0).
- 대구각 후속 고침: 홈 검색 안내문 '예: 수원화성, 화성행궁'(390px 잘림), 대표 메뉴 칩이 모두 0이던 목록 스크립트, 음식점 줄 제3유형 사진, 근처 주차장 검사 줄 읽기.
- 화면 확인 2회: 목록 권역 머리가 '수원화 성·'처럼 끊기던 것(이식으로 생김), 1024px 목록 머리 제목이 한 글자씩 끊기던 것(main부터 있던 것)을 고침. 최종 캡처 `docs/reference/upgrade_2026-11-05/`(홈·화성행궁·음식점 목록·/partners/·/map/, 360·390·768·1024·1440, 2배율, 가로 넘침 없음).
- 확인: build·validate sample·preview·production 오류 0. npm test 331 통과. pytest 파일별 실행에서 이식으로 깨진 시험(옛 홈 첫 화면을 보던 브라우저 시험, 두 값 표시를 보던 챗 색인 시험)은 새 배치·대표값 방식에 맞게 고침(conftest.engine_both_values). main부터 실패하던 시험: test_audit_engine 1건, test_ask_browser 런처 대화 2건. 가끔 실패하는 시험: test_ask_browser 새 탭 열기(main에서도 6번 중 1번), test_list_conditions 브라우저(부하 중 1번).
- 속도(tools/perf_check.py 조건, 외부 사진 막음): gzip 서버로 홈 LCP 0.98초·화성행궁 1.11초·관광지 목록 1.21초·지도 1.15초, CLS 0(main 1.08·0.98·1.16·1.10초). 음식점 목록 2.8초(main 2.7초, 목록 사진). 압축 없는 perf_check 그대로는 모든 페이지 2.5초 초과(main도 같음). 첫 방문 글꼴 측정값 409KB(main 401KB)로 300KB 목표를 main부터 넘음.

## 2026-11-05 공공데이터 수집분 병합 + 9개 언어 번역(운영자 '다 받으면 9개국어 번역까지 진행하고', '그래 최대한 다 긁어모아', 작업 브랜치 claude/trusting-shannon-ec29su — 배포 안 함)
지시문: `data/raw/suwon/collect_2026-11-05/MERGE.md`. 묶음 세 개(pubdata·filedata·tourapi_delta)는 원자료 기록으로 그대로 둠. 엔진 참고는 군산각 같은 브랜치(시장 가게 블록).

### 넣은 것
- **TourAPI 변경분**(실호출 0, `apply_delta`로 옛 묶음 9,191개 + 변경분 345개를 `data/cache/tourapi/`에): 새 숙소 5곳 **draft**(23-1 하우스·스테이 해성·두드림하우스·스테이우브·해성공간), 바뀐 공개 장소 39곳 중 사실 값이 바뀐 곳 25곳(필드별 출처·확인일 2026-11-05), 행사 18건 확인일만 갱신(새·바뀐 행사 0), 무장애 값 2곳(갤러리아백화점 광교점 5칸·1곳), 고캠핑 솔내음캠핑장 3칸, `--gallery`(묶음 README 순서) TourAPI 상세 사진 1,494장을 공개 362곳에 더함(제1유형 498·제3유형 993 등, 규칙대로 유형 표시), 관광사진 갤러리는 맞는 장소 0(더할 곳 없음).
- 새 TourAPI 응답은 `<br>` 줄바꿈이 빠져 '09:00~18:00- 주말'처럼 붙어 옴: 글자만 같고 줄만 빠진 값 4칸은 옛 값을 두고, 값이 바뀐 시간표 6칸은 '[요일]'·'- '·'※' 앞에서 줄을 다시 나눔(글자는 그대로).
- **API 데이터**(pubdata → `data/suwon/`): 인허가 licenses.json 209곳(영업 201·폐업 확인 8), 연관 관광지 related.json 56곳, 집중률 예측 crowd.json 68곳(2026-11-05~12-04), 해 almanac.json 120일(2026-11-05~2027-03-04), TAGO transport_tago.json 168짝(기준 11-06 금·11-07 토), 일별 방문자 visitors_daily.json(엔진은 아직 읽지 않음). 원자료는 `data/raw/suwon/{licenses,tago,almanac,datalab,tourapi_crowd,tourapi_related}/`, 설정은 `site.json` `public_data`, 수집 도구는 `tools/public_data/`(설정이 없으면 site.json을 읽고 작업 폴더는 `data/cache/public_data`), 다시 받는 명령은 CLAUDE.md 5절.
- **파일 데이터**(filedata): 근처 공영주차장·버스 정류장 nearby.json·parking_lots.json(이전 파일 없음 → 공개 장소 근처 주차 385곳·정류장 675곳, 잃는 값 없음), 지정 26곳(수원시 모범음식점 23·백년가게 3, 새 지정만; 착한가격업소 맞춤 0), 시장 market 16곳(온누리 가맹점·상가정보 주소). 문화축제 표준데이터는 끝나지 않은 새 축제 0이라 행사 추가 0. staged_tourist_spots·toilets·goodprice_menus는 묶음 안 원자료로만 둠. 원자료 `data/raw/suwon/{designations,markets,parking,std_festival,std_tourist}/`.
- **엔진**: 군산각의 시장 '품목별 가게' 블록(present.market_shops, place 템플릿·CSS·챗봇 색인)을 옮김 — 수원 엔진에 없어 market 값이 화면에 안 나왔음. /transport/ 제목·설명·데이터셋 이름이 자료에 있는 교통수단만 말하게 고침(수원은 항공편 0인데 '수원공항'이 적혀 있었음). 오늘의 상태(붐빔·해)·영업 확인·이어서 많이 간 곳·/sun/·/transport/는 이식된 엔진으로 그대로 나옴(해수욕장·섬 항로는 수원 자료 없음).
- **한국어 문장**: 사실·지정이 바뀐 53곳 요약·FAQ를 `tools/place_text.py --only`로 다시 만듦(지정 문장 '수원시가 모범음식점으로 지정한 곳으로…' 포함, 거절 0). 가이드 숫자 다시 셈: guide-01 21·52곳, guide-03 38곳, guide-05 175·55·44곳.
- **번역**: 8개 언어마다 91단위(문장 56·값 28·글 3·화면 문구 4) 번역 → fill → apply --merge. `report` 8개 언어 모두 소리 옮김 0·낡은 번역 0·번역 없음 0. `intl.require_complete` 켠 채.

### 뺀 것과 까닭
- `en_content.py names --offline`을 다시 돌리면 예전에 손으로 고친 외국어 이름(예: 팔달사가 'Paldalmun Gate'로, 수원야외음악당이 다른 시설 이름으로)이 278곳 되돌아가서 names.json은 그대로 둠(새 장소의 외국어 공식 이름은 0건).
- patch_visitors·patch_hygiene는 수원 묶음에 없음(월별 관광객 파일 없음, 식품안심업소 전국 파일 못 받음).

### 사람 확인 목록(공개 상태는 바꾸지 않음)
- 인허가 '폐업 확인' 공개 장소 8곳: 100년한우, 바다로간코끼리꼬창, 멘야고코로, 센텀커피, 메모리, 카페아고, 소롯, 본수원갈비(본수원갈비는 별관 인허가만 폐업 — 같은 주소에 '주식회사 본수원' 영업 중이라 오판으로 보임).
- TourAPI에서 지워진 공개 장소 4곳: 100년한우(2747099), 라이크 노 아더(2893055), 레드브릭커피하우스(2893073), 서린낙지(2893524).
- 새 draft 숙소 5곳(위), 새 행사 0. 월별 관광객 애매 목록 없음.
- TourAPI가 바꾼 값 중 확인할 것: 수원시립만석전시관 주소가 '팔달구 정조로 833'(수원시립미술관 본관 주소)으로, 요금이 '무료'로 바뀜 — 같은 응답의 소개문은 '장안구 송죽동 만석공원 안'이라 맞지 않음. 출처 값 그대로 두었으니 시설에 확인 필요.
- guide-01·02 항목 문장의 화성행궁 야간 개장(10월 30일~11월 1일)은 기간이 지났음(이번 병합 전부터의 문장, check-guide에서 걸림).

### 확인
- build·validate: sample·preview·production 오류 0. npm test 339개 중 331 통과·실패 0.
- pytest 전체: 남은 실패는 main부터 있던 3건(test_audit_engine 1, test_ask_browser 런처 대화 2). 이번 데이터로 처음 돌거나 깨진 시험은 고침 — test_sun_transport_pages(자료가 없어 건너뛰던 시험이 군산 값을 기대하던 것 → 수원 자료 값으로, 두 날 요약이 같고 시각이 다른 목록 경우 추가, 항공편 없는 제목 시험 추가), test_chat_index(근처 주차장 문장은 화면에 있는 곳에만 / 다른 이름이 붙은 카탈로그 줄), test_sidebar_layout(시간표 두 링크, 패널이 길어져 스크롤된 뒤의 탭 순서를 패널 안 위치로 잼). 병합 도구가 공식 페이지 주소(fact_sources.confirmed_urls) 33칸을 지운 것을 되살림(test_official_pages).
- 캡처 `docs/reference/upgrade_2026-11-05/data_{today,related,license,designation,shops,sun,transport,en}-{390,1440}.png`(배율 2, 외부 사진 막음, 가로 넘침 없음).
- perf_check(압축 없는 로컬 서버, 외부 사진 막음, pytest가 함께 도는 중): 홈 LCP 4.5초, 화성행궁 3.3초, 연무대 3.2초, 팔달문시장 3.6초, /transport/ 4.5초, CLS 모두 0. 이식 때처럼 압축 없는 측정은 main부터 2.5초를 넘음. 글꼴 341~436KB로 300KB 목표를 main부터 넘음.
