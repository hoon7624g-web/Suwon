# suwon — 2026-11-05 수집 결과 (병합 전 원자료)

다른 세션이 2026-11-05~06 저장소 밖에서 모은 공공데이터다. 병합·번역 방법은 hoon7624g-web/gunsan 브랜치 claude/trusting-shannon-ec29su의 docs/handover/merge_2026-11-05.md를 따른다. 키는 어느 파일에도 없다.

| 묶음 | 크기 | 들어 있는 것 |
|---|---|---|
| pubdata.tar.gz | 4.1M | almanac.json config.json crowd.json licenses.json related.json transport_tago.json visitors_daily.json  |
| filedata.tar.gz | 1012K | README.md designations_summary.json nearby.json nearby_diff.json parking_lots.json patch_designations.json patch_market.json staged_festivals.json staged_goodprice_menus.json staged_summary.json staged_toilets.json staged_tourist_spots.json std_report.json  |
| tourapi_delta.tar.gz | 2.0M | README.md diff.json  |

## TourAPI 변경분 요약 (tourapi_delta/README.md 앞부분)
## 차이 (사이트 places.json·events.json 기준)

| 구분 | 수 |
|---|---|
| 새 항목(places.json에 없음) | 5 (숙박 5) |
| tourapi_overrides skip·hold로 빼 둔 항목 | 0 |
| 바뀐 항목(목록 modifiedtime > places.json) | 39 (공개 39) |
| 사라진 항목(사이트에 있으나 지금 목록에 없음, 보고만) | 4 (detailCommon2 빈 응답으로 삭제 확인 4) |
| 새 행사(1월 1일 이후, events.json에 없음) | 0 |
| 바뀐 행사(modifiedtime > checked_at) | 0 |
| 무장애 정보 새로 생길 공개 장소 | 2 |
| 반려동물 정보 새로 생길 공개 장소 | 0 |
| 고캠핑 야영장(지역 1곳 중 사이트에 없는 곳) | 0 |
| 새 항목의 외국어 공식 이름(언어별) | en 0, ja 0, zh-hans 0, zh-hant 0, de 0, fr 0, es 0, ru 0 |
| 관광사진 갤러리 메타데이터 | 853장 (이미지 파일은 받지 않음) |
| 원응답 파일 | 310 |

자세한 목록은 `diff.json`(new·changed·gone은 contenttypeid별, events_new·events_changed, barrier_free·pet·gocamping·foreign_names_for_new_items·photo_gallery). 외국어 이름은 그 저장소 `tools/en_content.py`의 match_en 규칙(좌표 150m·유형·이름 근거)으로 찾은 보고용 후보다 — names.json에는 새 장소가 공개된 뒤 `en_content.py names`가 넣는다.

## 파일 데이터 (filedata/README.md)
# 수원시 (suwon) — 파일·표준 공공데이터 모음 (2026-11-05)

저장소에는 아무것도 쓰지 않았다. 아래 파일을 그 사이트 데이터 폴더에 옮기거나(patch_*는 places.json 해당 id의 필드를 바꿈) 버린다.
형식: 데이터 — 출처 페이지 · 제공기관 · 기준일 · 이용허락(포털 표기) · 행 · 맞춘 수 · 못 맞춘 수 · 결과 파일

- 전국주차장정보표준데이터 — https://www.data.go.kr/data/15012896/standard.do · 경기도 수원시 · 기준일(파일 수정일) 2026-04-20 · 이용허락범위 제한 없음 · 원본 59행 → 좌표·지역 맞는 59행, 근처 목록용 공영 54곳 (제외 {'화물·버스 전용': 2, '좌표 공유': 3}, 버림 {}) · 공개 장소 근처 주차 0→385곳 (0.0%→56.5%) · 근처 주차장 없는 공개 장소 296곳 · parking_lots.json, nearby.json, nearby_diff.json
- 버스 정류장 — 국토교통부 · 공공데이터포털 전국 버스정류장 위치정보 · 기준일 2026-10-20 · 이용허락범위 제한 없음(서울은 공공누리 제1유형) · 정류장 1529행(좌표 공유 0행 제외) · 공개 장소 근처 정류장 0→675곳 (0.0%→99.1%) · 없는 곳 6곳 · nearby.json(bus, 노선 번호 없음)
- 온누리상품권 가맹점(3060079) — https://www.data.go.kr/data/3060079/fileData.do · 소상공인시장진흥공단 · 기준일 2026-07-31 · 이용허락범위 제한 없음 · 이 지역 시장 가맹점 1534행 · 시장 장소 16곳에 연결(가게 1508곳) · 못 맞춘 시장 모양 장소 2곳 · patch_market.json, raw/markets/onnuri_suwon_20260731.csv, raw/markets/market_links.json
- 상가(상권)정보(15083033) — https://www.data.go.kr/data/15083033/fileData.do · 소상공인시장진흥공단 · 기준일 2026-09-30 · 이용허락범위 제한 없음 · 시장 400m 안 행만 raw/markets/sangga_suwon_markets_202609.csv · 주소가 붙은 가게 810곳 · 떡·한과 점포 카드 35장
- 행정안전부 인허가 식품 3종(즉석판매제조가공업·식품제조가공업·축산판매업) — 이 키는 세 서비스에 등록되지 않음 (HTTP 403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR, 2026-11-05) — 활용신청 뒤 다시 받는다(호출 0)
- 식품안심업소 전국(15060883, 식품안전나라 C004) — 포털 API 유형 LINK(식품안전나라 키 필요), data.go.kr 키로 HTTP 503, www.foodsafetykorea.go.kr 연결 끊김 — 전국 파일을 받지 못함
- 지정 baeknyeon (baeknyeon) — https://www.data.go.kr/data/15132695/fileData.do · 소상공인시장진흥공단 · 기준일 2026-08-20 · 이용허락범위 제한 없음 · 이 지역 18행 · high 3 · 새로 넣음 3 · 같은 지정 이미 있음 0 · 못 맞춤 15(그중 비슷한 후보 0·두 곳에 걸림 0) · patch_designations.json
- 지정 goodprice (goodprice_mois) — https://www.data.go.kr/data/3045247/fileData.do · 행정안전부 · 기준일 2026-09-30 · 이용허락범위 제한 없음 · 이 지역 122행 · high 0 · 새로 넣음 0 · 같은 지정 이미 있음 0 · 못 맞춤 122(그중 비슷한 후보 0·두 곳에 걸림 0) · patch_designations.json
- 지정 mobeom (mobeom_suwon) — https://www.data.go.kr/data/3044660/fileData.do · 경기도 수원시 · 기준일 2026-06-30 · 이용허락범위 제한 없음 · 이 지역 154행 · high 23 · 새로 넣음 23 · 같은 지정 이미 있음 0 · 못 맞춤 131(그중 비슷한 후보 1·두 곳에 걸림 0) · patch_designations.json
- 관광지점 월별 관광객 — 이 시·군의 월별·지점별 파일을 찾지 못함(연별·시 전체 합계뿐이거나 없음)
- (분석) 전국관광지정보표준데이터 15021141 — 제공 0파일 · 0행 · 장소에 없는 이름 0 (예: )
- (분석) 전국문화축제표준데이터 15013104 — 제공 1파일 · 3행 · 2026-11-05 이후 끝나는 축제 0 · 그중 events.json에 없는 이름 0 (예: 2026 정조대왕 능행차 공동재현(2026-10-04))
- (분석) 전국공중화장실표준데이터 15012892 — 포털 표준데이터 목록에 제공기관 파일이 없음(자료가 지방행정 인허가 데이터 localdata.go.kr/file/public_restroom_info로 옮겨짐, 행정안전부_공중화장실정보 15075531은 링크형 52,255행 2025-11-27). localdata.go.kr 연결이 이 환경에서 끊겨 받지 못함 — 받으면 화장실명·개방시간·장애인 변기·기저귀 교환대·비상벨·좌표로 '근처 공중화장실'을 만들 수 있다

## 모아 둔 자료(staged — 엔진 형식 아님, 행마다 provider·base_date)
- 전국관광지정보표준데이터 15021141 — https://www.data.go.kr/data/15021141/standard.do · 이 지역 제공 파일 없음 · - · 0행 · 장소에 맞춤 0 · 못 맞춤 0 · staged_tourist_spots.json (표준데이터 API tn_pubr_public_trrsrt_api는 이 키로 HTTP 403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR → 파일)
- 전국문화축제표준데이터 15013104 — https://www.data.go.kr/data/15013104/standard.do · 경기도 수원시(2026-07-28), 한국관광공사(2026-09-30) · 이용허락범위 제한 없음 · 4행 · events.json에 맞춤 3 · 못 맞춤 1 · 2026-11-05 이후 끝나는 축제 0(그중 events.json에 없음 0) · staged_festivals.json (API tn_pubr_public_cltur_fstvl_api 403 → 파일)
- 공중화장실 — 이 지역 시·구 파일 없음(서울 15146086·강원 15160229는 링크형, 전국은 localdata.go.kr 연결 끊김, 표준데이터 API 403)
- 행정안전부 착한가격업소 메뉴·가격 — https://www.data.go.kr/data/3045247/fileData.do · 행정안전부 · 기준일 2026-09-30 · 이용허락범위 제한 없음 · 이 지역 182행(메뉴 있는 행 182) · 장소에 맞춤 0 · 못 맞춤 182(미용·세탁 등 비음식 업종 포함) · staged_goodprice_menus.json (자동변환 API api.odcloud.kr: HTTP 401 {"code":-4,"msg":"등록되지 않은 인증키 입니다."} → 파일)
