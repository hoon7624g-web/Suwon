# 수집한 공공데이터 병합 + 9개 언어 번역 — 세션 지시문 (2026-11-05)

운영자 지시(2026-11-05):
- '가지고 올 수 있는 데이터는 다 끌어모은다고 보면 돼'
- '그럼 모든 사이트 다 최대한 자료 받아'
- '다 받으면 9개국어 번역까지 진행하고'
- '그래 최대한 다 긁어모아'

화면 이식(`port_2026-11-05.md`)을 끝낸 세션이 같은 저장소에서 이어서 한다. 저장소의 CLAUDE.md와 2026-11-05 운영자 결정(대표값·카카오 등)은 그대로 지킨다. 분석 배경은 `upgrade_20sites_2026-11-05.md` 4절에 있다.

## 0. 입력

이 폴더(`data/raw/suwon/collect_2026-11-05/`)에 있다. 먼저 `git pull`로 받는다. 수집은 다른 세션이 2026-11-05에 저장소 밖에서 했다.

| 파일 | 내용 |
|---|---|
| `MANIFEST.md` | 무엇이 들어 있는지와 건수 |
| `pubdata.tar.gz` | API 데이터. 엔진 형식 JSON `licenses`·`related`·`crowd`·`visitors_daily`·`almanac`·`beaches`·`ferry`·`transport_tago`(있는 것만, 인천각 10-31과 같은 형식). 원자료 `raw/`, 설정 `config.json`(`public_data` 묶음), 수집 도구 `tools/` |
| `filedata.tar.gz` | 파일·표준 데이터. `README.md`(출처·기준일·이용허락·행·맞춤 수), `parking_lots.json`·`nearby.json`·`nearby_diff.json`, `patch_designations`·`patch_market`·`patch_hygiene`·`patch_visitors`(.json), `patch_visitors_review.json`, `staged_*.json`, `raw/` |
| `tourapi_delta.tar.gz` | TourAPI 변경분 원응답. `README.md`(이 저장소용 병합 명령), `diff.json`(새·바뀜·사라짐·행사·무장애·반려동물·고캠핑·외국어 이름·관광사진), `cache/tourapi/`(저장소 `data/cache/tourapi/`와 같은 구조), `scripts/`(apply_delta 등), `_shared/`(두루누비·고캠핑 전국 목록) |

- 묶음 파일은 원자료 기록으로 커밋된 채 둔다. 군산 `data/raw/`와 같은 방식이다.
- 풀어 쓰는 작업 폴더와 `data/cache/`는 커밋하지 않는다.

## 1. API 데이터 (pubdata)
1. JSON 파일을 `data/<slug>/`에 넣고, `raw/`는 `data/raw/<slug>/` 아래 인천각과 같은 구조로 둔다.
2. `config.json`의 `public_data` 묶음을 `site.json`에 넣는다. 저장소 경로처럼 이 컴퓨터에만 맞는 값은 뺀다.
3. 수집 도구는 `tools/public_data/`에 넣고, 다시 받는 명령을 CLAUDE.md 명령어 절에 적는다.
   - 집중률 예측은 30일 예보라 매달 다시 받는다.
   - 해·물때는 120일치라 기간이 끝나기 전에 다시 받는다.
   - 키는 `DATA_GO_KR_KEY` 환경 변수로 받는다.
4. 엔진이 각 블록을 실제로 보이는지 확인하고, 안 보이면 고친다.
   - 블록: 오늘의 상태(붐빔·해·바다), 장소의 영업 확인 줄, 이어서 많이 간 곳, /sun/, /transport/, 섬 항로, 해수욕장
5. 인허가로 '폐업 확인'된 장소는 목록만 작업 기록에 남긴다. 공개 상태는 바꾸지 않는다(운영자 결정).

## 2. 파일 데이터 (filedata)
1. `nearby.json`·`parking_lots.json`은 `nearby_diff.json`에서 기존보다 나아지고 잃는 값이 없을 때만 바꾼다.
2. `patch_designations`는 places.json `designations`에 새 지정만 더한다.
3. `patch_market`은 `market`에, `patch_visitors`는 `visitors`에 넣는다.
4. `patch_hygiene`은 `licenses.json`의 hygiene에 넣는다. 지정 종료일이 없는 행은 엔진 규칙대로 화면에 나오지 않는다.
5. `patch_visitors_review.json`(이름이 애매한 곳)은 넣지 않고 사람 확인 목록으로 작업 기록에 남긴다.
6. `staged_festivals.json`
   - events.json에 없고 끝나지 않은 축제만 **draft** 행사로 넣는다.
   - 출처 기관·데이터 이름·기준일을 함께 적는다.
   - 공개는 운영자가 정한다.
7. `staged_tourist_spots`·`staged_toilets`·`staged_goodprice_menus`는 원자료로만 둔다(화면에 둘 자리는 운영자 결정).

## 3. TourAPI 변경분 (tourapi_delta)
- 묶음 안 `README.md`의 명령을 순서대로 실행한다: `scripts/apply_delta.py` → `tools/tourapi_bulk.py --offline …` → (대구 계열) `tools/harvest_merge.py --pet --camping --photos --apply` → `tools/en_content.py names --offline`.
- 출력에서 실호출 0인지 확인한다.
- 새 장소·새 행사는 **draft**다.
- 사라진 항목(TourAPI에서 삭제 확인)은 목록만 남기고 공개 상태는 바꾸지 않는다.
- 바뀐 항목은 사실 값과 필드별 출처·확인일을 갱신한다.
- 출처마다 값이 다르면 대표값 규칙(`fact_conflicts: "primary"`)대로 둔다.
- 관광사진(관광사진 갤러리, 공공누리 제1유형)은 이 저장소의 사진 규칙대로 사진이 없는 장소부터 쓴다.
- 해남·군산 계열 저장소에 `harvest_merge.py`가 없으면 대구 계열 저장소에서 옮겨 쓴다.

## 4. 한국어 문장
- 사실이 바뀐 장소만 요약·FAQ를 저장소의 문장 도구(대구 계열은 `tools/place_text.py`)로 다시 만든다.
- 규칙은 그대로다: 답부터 쓰는 존댓말, 그 장소만의 사실, FAQ는 데이터로 답할 수 있는 것만.
- 가이드 속 숫자(근처 n곳, 음식점 수 등)는 다시 세고 가이드 검사(`guide_content.py check-guide` 등)를 통과시킨다.

## 5. 8개 외국어 번역
1. `tools/intl_table.py extract`로 빠진 단위·이름을 뽑는다. 세종은 `tools/sejong_i18n.py`를 쓴다.
2. 직접 번역을 쓴다. 장소 이름은 TourAPI 언어별 공식 이름이 먼저이고, 소리 옮김은 고유명사에만 쓴다.
3. `fill` → `apply --merge` 순서로 넣는다.
4. `report`가 8개 언어 모두 번역 없음·낡은 번역·소리 옮김 0이어야 한다. `intl.require_complete`는 끄지 않는다.

## 6. 확인
- pytest. main에서도 실패하던 시험은 따로 적는다.
- npm test.
- build·validate: sample, preview, production 모두 오류 0.
- perf_check: 이식 때 남은 LCP 초과도 다시 잰다.
- 캡처 390·1440(배율 2)을 `docs/reference/upgrade_2026-11-05/data_*.png`로 남긴다. 대상:
  - 새 블록이 보이는 장소(영업 확인·붐빔·해·바다)
  - /sun/, /transport/
  - 시장 가게가 있는 시장
  - 새 지정 배지가 붙은 음식점
  - 외국어 판 한 쪽

## 7. 마무리
- 작업 기록에 데이터별 넣은 수·뺀 수와 이유를 적는다. 사람 확인 목록(폐업 확인, 사라진 항목, 월별 관광객 애매, draft 새 장소·행사 수)도 함께 적는다.
- `claude/trusting-shannon-ec29su`에 push한다. main push·배포·`approve_publication`·`public/` 재생성은 하지 않는다.
- 끝에 한국어 30줄 이내로 요약한다: 넣은 데이터 수, 번역 report, 검증 수치, 캡처 경로, 사람 확인 목록, 남은 문제.

## 8. 이 사이트(suwon) 알림 — 수집 쪽 시험 빌드 결과(이식 전 main 엔진 기준)
- 인허가 209/240, 연관 56, 집중률 68, TAGO 168짝. 시험 빌드에서 모두 나왔다.
