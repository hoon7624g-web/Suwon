# 군산각 → 지역 ○○각 이식 키트 (2026-11-13)

이 브랜치(`port-kit-20261113`)는 이 저장소 코드와 섞이지 않는 독립 브랜치다. **사이트 코드를 여기에 커밋하지 말 것.**
군산각 세션(조정 세션)이 넣어 두었다. 2026-10-31 키트(`port-kit-20261031`)와 같은 방식이다.

## 0. 무엇을 하나 (운영자 결정 2026-11-13)
운영자 '18곳 동시에 세션 띄워서 진행해' — 군산각에 2026-11-06~11-12 들어간 아래 기능을 지역 ○○각 18곳에 동시에 옮긴다(대구각은 조정 세션이 따로 함).
- 옮긴다: **A 정돈 작업**, **B 유튜브·인스타그램 인기 순위**, **C 제휴·관련 사이트(회사 사이트 4개만)**, **D 공유하기 전체**, **E 날씨 카드 '자세히 보기'를 그 지역 날씨각 페이지로**.
- 보류(옮기지 않음, 운영자 '일단 보류'): 숙박 제휴 링크·숙박 예약하기, 파트너 숙소 표시, 블로그, ADO2 숏폼. (지역 저장소에 원래 있던 파트너 모집 페이지·'문의/제휴'는 그대로 둔다.)
- 인스타그램 게시물 자료는 Antigravity가 따로 모아 각 저장소 `insta-curation-2026-11` 브랜치에 `data/<지역>/insta.json`으로 올린다. 이 작업에서는 **자료를 만들지 말고**, 자료가 들어오면 그대로 보이도록 코드만 옮긴다(자료가 없으면 순위 블록은 유튜브만).

## 1. 키트 구성
- `gunsan/` — 군산각 `origin/main` 459928163(2026-11-12) 기준 pipeline·templates(큰 그림 폴더 제외)·tests·CLAUDE.md·requirements.txt, 참고 자료(`data/gunsan/related_sites.json`·`yt_channels.json`·`insta.json`·`icons.json`), `tools/icon_media.py`.
  - `gunsan/templates/assets/icons/`에는 공유 아이콘 `btn-share-*`만 있고, `manifest.json`은 군산 것 전체다(필요한 `btn-share` 항목만 옮길 것).
  - `gunsan/templates/assets/related/` — 회사 사이트 아이콘 4개(aio2o·webforai·weather·travel).
- `patches/NN-<묶음>-<군산 커밋>.patch` — 옮길 군산 커밋 20개를 순서대로(빌드 산출물·군산 전용 그림 제외). **참고용이다.** 지역 저장소는 군산 코드에서 갈라져 따로 고쳐져 왔으므로(같은 파일도 수천 줄 다름) `git am`·cherry-pick이 맞지 않는다. 커밋이 바꾼 뜻을 이 저장소 코드의 해당 자리에 맞춰 옮긴다.
- `scripts/yt_popular.py` — 화제 영상 목록 만들기(B). `scripts/og_card.js` — 링크 미리보기 로고 카드(D). `scripts/weather_paths.txt` — 날씨각 today 페이지 주소 269개(E).
- `assets/example-og-card-daegu.png` — 로고 카드 예시.

쓰는 법: `git fetch origin port-kit-20261113 && git worktree add ../kit origin/port-kit-20261113` 뒤 `../kit`을 읽는다(경로는 편한 곳으로).

## 2. 작업 규칙
- 이 저장소의 `CLAUDE.md`를 먼저 끝까지 읽는다. 지역마다 다른 운영자 결정(블로그·제휴 없음, 지도 제공자, 슬러그 방식, 언어 수 등)은 그 파일이 우선이다. 군산 `gunsan/CLAUDE.md`는 이식할 기능의 뜻을 읽는 데 쓴다(3절 4항 미리보기 그림, 3절 10항 제휴·관련 사이트, 7절 '공유'·'정돈 규칙'·'유튜브·인스타그램 인기 순위').
- 기준은 이 저장소의 `origin/main`(공개 배포 브랜치). 기본 브랜치가 main이 아닌 저장소가 있으니 꼭 `origin/main`에서 시작한다.
- 커밋은 **이 세션에 지정된 작업 브랜치**에만 하고 그 브랜치를 push 한다. **main에 합치거나 push하지 않는다. 배포(`tools/build_public.py`로 `public/` 갱신·커밋)도 하지 않는다.** 배포는 운영자 확인 뒤 조정 세션이 한다.
- 커밋 메시지는 이 저장소의 이전 이식 커밋 형식을 따른다(예: `feat(ui): … (군산 82d3298d02 이식)`).
- 지역 이름 바꾸기: 군산→<지역>, 군산각→<지역>각, Gunsangak→<로마자>gak(이 저장소 `site.json`·locales에 있는 이름을 쓴다). 군산 장소·가이드 id, 군산 수치(영상 69편·카페 게시물 22편 등)는 이 지역 값으로 바꾸거나 자료에서 세어 넣는다.
- 검증 규칙을 완화해서 통과시키지 않는다. 사실·사진·원문 규칙은 이 저장소 CLAUDE.md 그대로.

## 3. 옮길 것

### A. 정돈 작업 (patches 01~04)
- 82d3298d02가 본체: `css/90-refine.css`(마지막 CSS 파일, 머리에 규칙 여섯 가지), 휴대폰 장소 하단 바의 'AI 챗봇' 버튼, '이어서 보기'(present.see_also), 가이드 읽기 층(present.section_reading — guides.json body[].short가 없으면 짧은 제목 없이 자연스럽게 보이게; 자료를 지어내지 않는다), 홈 덜어내기, 낮은 창에서 패널 날씨 카드 접기, 1200px부터 좌우 여백·챗봇·맨 위로 자리.
- 6db5c1de62·cb17302e82: 화면 수정과 낡은 브라우저 시험 갱신. 군산 블로그 목록 부분은 빼고, 숙박 예약하기·제휴 타일·파트너 숙소·ADO2에만 걸리는 규칙은 뺀다(규칙의 뜻은 남긴다).
- 57dc9fc51e: 휴대폰 목록 칸 폭 수정 — 이미 같은 것이 있으면 건너뛴다.

### B. 유튜브·인스타그램 인기 순위 (patches 05~12)
- 인스타그램 큐레이션 코드(load_insta·load_insta_channels, 가이드의 인스타 장, 홈 줄)는 **자료 없이도 깨지지 않게** 옮긴다(파일이 없거나 비면 아무것도 안 나옴).
- 유튜브: `data/<지역>/yt_channels.json`을 `python ../kit/scripts/yt_popular.py data/<지역> <지역 한글 이름> > data/<지역>/yt_channels.json`로 만든다(군산 규칙: 사이트에 실린 한국어 영상, 조회수 10만 회 이상, 조회수 순, 최대 70편 / 10만 회가 20편보다 적으면 상위 20편). channels는 빈 목록 — '인기 채널' 칸은 비면 나오지 않게.
- 홈 순위 블록(.hrk, css/47-rank.css), 1680px부터 오른쪽 보드(탭), /videos/ 화제 영상의 순위 숫자, build.load_yt_channels의 조회수 정렬. 인스타그램 자료가 없으면 블록·보드는 유튜브만 보이고(탭·빈 칸 없이), 인스타 자료가 들어오면 군산처럼 둘 다 보인다 — 두 경우를 시험으로 확인한다(임시 insta.json으로 확인하고 커밋하지 않는다).
- 순위가 보이는 곳마다 '<지역>각이 고른 목록(영상 n편[·게시물 m편]) 안의 순서'·'추천 순서가 아님'·'숫자는 실은 때의 값'을 적는다(n·m은 자료에서 센 값). 인스타그램 줄의 사진은 게시물에 나온 장소의 TourAPI 제1·3유형 사진(제3유형은 자르거나 키우지 않음, 그 위에 순위 숫자를 올리지 않음).

### C. 제휴·관련 사이트 (patches 13~15)
- `data/<지역>/related_sites.json`에 **회사 사이트 4개만**: AI오투오·WebforAI·날씨각·여행각(군산 파일의 그 4개 항목 그대로, 아이콘은 `gunsan/templates/assets/related/`의 4개). 군산각 블로그·스테이,머뭄은 넣지 않는다(운영자 2026-11-13 '두 가지만 빼놓고 나머지 4개는 그대로').
- 서브페이지 바닥글 맨 위 띠 + 홈 맨 아래 카드(홈 바닥글 띠는 없음 — 군산 2026-11-12 결정, patch 14). validate의 related_sites.data_problems, 시험 갱신(patch 15 포함).

### D. 공유하기 (patches 16~19)
- `pipeline/share.py`, `templates/_share.html.j2`, `css/88-share.css`, site.js의 공유 부분(보내기 상자·카카오톡·더보기·링크 타일·대화상자 — **patch 17의 고침 포함: Kakao SDK 2.x는 Kakao.init 뒤에만 Kakao.Share가 생긴다**), track.js 설명, `requirements.txt`에 `segno==1.6.6`.
- 상단 바 '공유' 알약은 휴대폰에서도 글자를 보인다. 제목 줄 '공유' 알약은 코스 목록·영상(그리고 이 저장소에 있을 때만 숙박 예약하기·블로그). 관광지·음식점·숙소 목록에는 두지 않는다(휴대폰 첫 결과 500px).
- 보내기 상자 자리: 장소는 길찾기(·예약) 줄 아래, 가이드·코스·칼럼은 '이어서 보기' 앞, 행사는 길찾기 아래, 홈은 '<지역>각 알리기'(#share, 관련 사이트 카드 앞). 패널·휴대폰 메뉴의 '<지역>각 공유하기' 카드('문의/제휴' 바로 위)는 사이트 상자를 대화상자로 연다.
- 공유 카드 아이콘: `gunsan/templates/assets/icons/btn-share-*` 6개 파일을 이 저장소 `templates/assets/icons/`로, `manifest.json`·`data/<지역>/icons.json`에는 `btn-share` 항목만 더한다.
- 카카오톡 타일은 `site.json`의 `kakao_js_key`를 쓴다. 키가 없는 사이트(지도 OSM)는 카카오톡 타일이 나오지 않아야 한다. 키가 있으면 그 도메인이 카카오 앱에 등록돼 있어야 실제로 열린다 — 배포 전에는 확인할 수 없으니 보고에 '배포 뒤 확인 필요'로 적는다.
- 링크 미리보기(og:image): 제1유형 사진만(build.og_image·first_og, 외국어판 장소도). 제1유형이 없으면 목록·읽을거리는 사이트 미리보기 그림(og.default), 장소 페이지는 로고 카드 `templates/assets/brand/og-card.png` — `node ../kit/scripts/og_card.js …`로 이 저장소의 상징 svg·이름·로마자·도메인·브랜드 색으로 만든다(일러스트 없음).
- 시험: 군산 tests/test_present.py의 공유 시험 4개(share.view, 상자 자리·대화상자, 미리보기 그림, 브라우저 동작 — 대역 SDK는 init 때 Share가 생기게)를 이 저장소 시험에 맞춰 옮긴다.

### E. 날씨 카드 '자세히 보기' (patch 20)
- 날씨각 홈 대신 `https://weather.o2o.kr/today/<path>`. path는 `scripts/weather_paths.txt`에서 이 사이트 날씨 위젯이 보이는 곳(`site.json`의 weather region_code·label)과 같은 시·군·구로 고른다. 제안:
  해남 jeonnam/haenam · 제주 jeju/jeju(또는 위젯이 서귀포면 jeju/seogwipo) · 춘천 gangwon/chuncheon · 용인 gyeonggi/yongin · 종로 seoul/jongno · 여수 jeonnam/yeosu · 경주 gyeongbuk/gyeongju · 강릉 gangwon/gangneung · 전주 jeonbuk/jeonju · 가평 gyeonggi/gapyeong · 세종 sejong/sejong · 속초 gangwon/sokcho · 영주 gyeongbuk/yeongju · 목포 jeonnam/mokpo · 단양 chungbuk/danyang · 수원 gyeonggi/suwon · 부산·인천은 위젯의 구(예: busan/jung, incheon/jemulpo)와 맞는 path.
- 외국어판 날씨 카드도 같은 링크.

## 4. 확인
- 시작 전 기준: preview 빌드·validate를 한 번 돌려 오류·경고 수를 적어 둔다.
  `TZ=Asia/Seoul python -m pipeline.build --data data/<지역> --out <스크래치>/prev --mode preview && python -m pipeline.validate --data data/<지역> --out <스크래치>/prev --mode preview`
- 끝: preview·sample validate 오류 0(경고는 기준보다 늘지 않게), 공개 빌드도 스크래치 폴더로 한 번(`python tools/build_public.py --out <스크래치>/pub` 또는 production build+validate) 오류 0. `public/`은 건드리지 않는다.
- 시험: 바꾼 부분과 닿는 tests 파일 + 가능하면 전체 pytest. Python Playwright가 없으면 `pip install playwright==<node playwright 버전>`(Chromium은 이미 깔려 있음, `playwright install` 금지).
- 화면: 360·390·768·1440 캡처를 보고 고치기 2회 이상(홈·장소·가이드·영상·패널 대화상자). 옆으로 밀림 없음, 휴대폰 고정 영역 ≤ 15%, 휴대폰 목록 첫 결과 500px 안.
- 빌드는 메모리를 많이 쓸 수 있으니 한 번에 하나만.

## 5. 기록
- 이 저장소의 인수인계 기록 파일(round 로그)에 한 줄, CLAUDE.md에 이번 결정 줄(공유·미리보기 그림·관련 사이트·인기 순위)을 이 지역 말로 더한다.

## 6. 마지막 보고 (조정 세션이 읽는다 — 마지막 메시지에 이 형식으로)
- 작업 브랜치 이름과 마지막 커밋 해시
- 묶음 A~E 각각: 완료 / 일부 / 못 함 + 이유
- validate(preview·sample·공개 빌드) 오류·경고 수, 기준 대비
- 돌린 시험과 결과(실패는 이름과 원인, 원래부터 실패면 그렇다고)
- 화면 확인에서 남은 문제, 운영자 결정이 필요한 것
