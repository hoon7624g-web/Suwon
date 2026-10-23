# ○○각 만들기 — 지역 여행 사이트 마스터 프롬프트 v1.0

| 항목 | 내용 |
|---|---|
| 판 | v1.0 (2026-10-22) |
| 기준 엔진 | 군산각 저장소 `hoon7624g-web/gunsan`, `main` 커밋 `6a26206c4` (공개 사이트 https://gunsan.webforai.kr) |
| 함께 받는 것 | 위 저장소의 GitHub ZIP(Code → Download ZIP) |
| 대상 지역 | 시·군 하나. 광역시의 구·군 여러 곳이나 세종시는 1단계에서 코드를 넓혀야 한다(4장 1-2의 1번) |
| 배포 | Vercel |
| 언어 | 한국어 + 외국어 8개 판(en, ja, zh-hans, zh-hant, de, fr, es, ru). 기본으로 포함한다 |
| 도메인 규칙 | 보류. 도메인은 입력값으로 받는다 |
| AI 도구 | 어느 AI 코딩 도구든 쓸 수 있게 썼다(파일을 읽고, 명령을 실행하고, 파일을 고칠 수 있으면 된다) |

> **이 문서가 가장 앞선 지시다.** ZIP 안의 `CLAUDE.md`·`AGENTS.md`·`CODEX_TASKS.md`와 `docs/handover/`는 군산각 운영 기록이다. 새 지역 작업에서는 이 문서가 그 파일들보다 앞선다. 0단계에서 그 파일들을 새 지역용으로 바꾼다(부록 E).
> 줄 번호는 기준 커밋의 값이다. 코드가 바뀌었을 수 있으니 **파일 이름과 상수 이름으로 찾는다.**
> 0장은 사람이 읽는다. 1장부터는 AI 도구가 따른다.

---

## 0. 사람용 안내

### 0.1 준비물
1. **군산각 ZIP**: GitHub `hoon7624g-web/gunsan` → `main` → Code → Download ZIP. 푼 폴더 이름은 `gunsan-main`이다.
2. **이 문서**: ZIP 안 `docs/master/region_master_prompt.md`에도 들어 있다.
3. **1장 입력값 표를 채운 것**: 모르는 칸은 '미정'으로 둔다.
4. **계정과 키**: 키 값은 AI 대화창에 붙이지 않는다. 넣는 곳은 1장 표에 있다.
   - data.go.kr **TourAPI 키**
     - '한국관광공사_국문 관광정보 서비스_GW'를 활용신청한다.
     - 외국어 8개 서비스(EngService2·JpnService2·ChsService2·ChtService2·GerService2·FreService2·SpnService2·RusService2)도 활용신청한다.
     - 무장애 여행 정보(KorWithService2)도 활용신청한다.
   - **Anthropic API 키**: 지역마다 따로 만든다. 챗봇과 코스 만들기에 쓴다.
   - **카카오 개발자 앱**: 지도용 JavaScript 키가 필요하다. 지도 장소 ID를 붙이려면 REST 키도 필요하다(선택).
   - **GA4**: 측정 ID가 없으면 '나중에'라고 적는다.
   - GitHub 계정과 Vercel 계정
5. **작업 PC**
   - macOS나 Linux 셸을 쓴다. Windows는 WSL을 권한다.
   - Python 3.12 이상, Node 22 이상(Vercel은 24.x로 돌린다), git
   - 인터넷: apis.data.go.kr에 닿아야 한다. 일부 관공서 사이트는 해외 IP를 막으므로 한국 네트워크를 권한다.

### 0.2 시작하는 법
1. ZIP을 **새 빈 폴더**에 푼다. 폴더 이름은 예를 들어 `yeongjugak`처럼 짓는다.
2. 그 폴더를 AI 코딩 도구로 연다.
3. 첫 메시지를 아래처럼 보낸다. 1장 표를 채워 붙인다.

```
이 폴더는 군산각 저장소 ZIP을 푼 것이다. docs/master/region_master_prompt.md(첨부한 파일과 같다)를
처음부터 끝까지 읽고, 그 문서를 이 폴더의 CLAUDE.md·AGENTS.md보다 앞선 지시로 삼아 ○○각을 만들어라.
사람이 할 일(체크포인트)에 닿으면 무엇을 해 달라는지 한 번에 정리해서 말하고, 그동안 할 수 있는 다른 단계를 계속하라.
입력값:
(1장 표를 채워 붙인다)
```

### 0.3 사람이 손대는 순간(체크포인트)

| CP | 언제 | 사람이 할 일 |
|---|---|---|
| CP1 | 시작 직후 | AI가 TourAPI에서 찾은 지역 코드가 맞는지 본다. 키를 `.env`에 넣는다(AI는 그 파일을 열지 않는다) |
| CP2 | 브랜드 단계 | AI가 쓴 로고 프롬프트로 이미지 도구에서 시안을 여러 장 만든다. 그중 하나를 골라 폴더에 넣는다 |
| CP3 | 그림 단계 | AI가 쓴 이미지 요청 문서대로 그림을 만들어 `incoming/ai-images/`에 넣는다 |
| CP4 | 검수·공개 승인 | 검수 시트에 OK/수정을 적는다. 공개 범위와 날짜를 정해 '공개 승인'을 지시한다 |
| CP5 | 배포 전 | GitHub 저장소와 Vercel 프로젝트를 만든다. 환경 변수, 도메인, 카카오 도메인 등록, GA4 설정을 한다 |
| CP6 | 배포 뒤 | 6장 순서로 화면을 본다. 검색엔진(구글·빙·네이버)에 사이트를 등록한다 |

- CP4 전에는 외국어 번역을 하지 않는다. 번역은 공개 승인된 한국어 기준이라서다.
- AI는 CP를 기다리는 동안 다른 단계를 진행한다.

### 0.4 미리 알아 둘 한계
- **코드 속 군산 값**: 군산 값이 코드 곳곳에 박혀 있다. 그래서 1단계(엔진 지역화)가 가장 큰 작업이다.
- **수집 기간**: TourAPI 개발계정은 하루 호출 한도가 있다(약 1,000회로 알려짐). 장소가 많은 지역은 수집에 2~4일이 걸린다.
- **번역 비용**: 외국어 8개 판은 AI 토큰을 많이 쓴다. 군산(공개 장소 약 420곳)은 한 언어에 수백만 토큰, 수십 분~1시간 넘게 걸렸다.
- **챗봇 상한**: 챗봇이 읽는 사이트 목록은 상한(약 72,000토큰)이 있다. 군산이 거의 닿아 있다. 장소가 더 많은 지역은 상한을 올릴지 사람이 정한다(올리면 질문당 비용이 커진다).
- **도메인**: 도메인을 정하지 않고 임시 주소(`<프로젝트>.vercel.app`)로 공개할 수 있다. 하지만 나중에 옮기면 할 일이 많다. 이전 규칙, 검색엔진 주소 변경, IndexNow 재전송을 다시 해야 한다.
- **자동화 비율**: AI가 80~90%를 만든다. 나머지(공식 출처에도 없는 값, 사람 결정, 사람 검수)는 '빈칸 보고서'로 받는다.

### 0.5 결과물
1. 새 지역 저장소: 엔진, `data/<지역>/`, 공개 산출물 `public/`
2. Vercel 프로젝트(공개는 사람이 켠다)
3. 작업 기록 `docs/handover/<지역>_log.md`
4. 완료 보고서 `docs/handover/<지역>_report.md`: 숫자, 빈칸, 사람이 정할 것

---

## 1. 입력값

사람이 채운다. 빈칸이면 AI는 멈추지 않는다. '미정'으로 두고 할 수 있는 단계를 하고, 보고서의 '사람이 정할 것'에 적는다.

| 키 | 뜻 | 예시 | 비었을 때 |
|---|---|---|---|
| `region` | 짧은 지역 이름 | 영주 | 필수 |
| `locality` | 행정 이름 | 영주시 / 해남군 | 필수 |
| `region_admin` | 시·도 | 경상북도 | 필수 |
| `region_full` | TourAPI 법정동 코드 이름(시·도 + 시·군) | 경상북도 영주시 | AI가 TourAPI 코드 목록에서 찾아 CP1에서 확인받는다 |
| `slug` | 데이터 폴더·내부 이름(영문 소문자) | yeongju | `region`을 로마자로 바꿔 쓴다 |
| `site_name` | 한국어 사이트 이름 | 영주각 | '<region>각' |
| `site_name_intl` | 외국어 8개 판 사이트 이름 | Yeongjugak | 국어의 로마자 표기법으로 만든다 |
| `city_intl` | 언어별 도시 표기(8개) | en Yeongju, ja 栄州?, zh 荣州?, ru Ёнджу? … | AI가 공식 외국어 표기(TourAPI 외국어 서비스·지자체 외국어 사이트)에서 찾아 근거와 함께 제안한다. 사람이 확정한다 |
| `home_h1` | 홈 첫 화면 큰 제목 | 영주 여행의 모든 것 | '<region> 여행의 모든 것'. 외국어는 군산판 문형('All About Gunsan Travel' 등)에 맞춰 바꾼다 |
| `site_url` | 공개 주소 | 미정 | 임시 `https://<vercel-project>.vercel.app`. 5장의 도메인 결정 |
| `vercel_project` | Vercel 프로젝트 이름 | yeongjugak | `<slug>gak` |
| `official_tourism_url` | 지역 공식 관광 사이트 | https://… | AI가 찾아 제안한다 |
| `probe_keyword` | TourAPI 진단용 대표 장소 이름 | 부석사 | AI가 정한다 |
| `operator` | 운영 주체 | 군산각과 같은 회사 | 군산각 `site.json` `operator`를 그대로 쓴다(`contact` 확인) |
| `operator_contact` | 정정 요청 연락처 | 이메일 | 사람이 정할 것. 공개 빌드에 필요하다 |
| `ga4_id` | GA4 측정 ID | G-XXXX | `launch_exceptions.ga4_id`에 '나중에 설치' 사유를 적는다 |
| `kakao_js_key` | 카카오 지도 JavaScript 키(공개 키) | — | 지도 자리에 '지도를 불러오지 못했습니다'가 나온다. 다른 기능은 된다 |
| `brand_color` | 대표 색(선택) | — | 군산각 팔레트를 쓰고, 로고 시안에서 정한다 |

**비밀값을 넣는 곳**: AI 대화창에 붙이지 않는다. 출력하지 않는다. 커밋하지 않는다.

| 비밀값 | 넣는 곳 |
|---|---|
| `TOURAPI_KEY` | 작업 폴더의 `.env`(한 줄 `TOURAPI_KEY=…`) 또는 셸 환경 변수 |
| `KAKAO_REST_KEY`(선택) | 셸 환경 변수만. 이 도구는 `.env`를 읽지 않는다 |
| `ANTHROPIC_API_KEY` | Vercel 환경 변수만 |
| `PLAN_SHARE_SECRET` | Vercel 환경 변수만 |

---

## 2. 너(AI)의 역할과 목표

너는 이 저장소의 엔진(군산각)을 써서 1장 지역의 여행 사이트 **'○○각'**을 만든다. 이 사이트는 여행자가 실제로 쓰는 사이트이면서, 공개 뒤 AI 답변엔진의 인용과 유입을 재는 실험 사이트다.

**성공 기준**
1. 공개 대상 장소 페이지가 **방문 판단 정보**로 채워져 있다. 방문 판단 정보는 이용시간·쉬는 날·요금·주차·전화·체크인이다.
2. **얇은 페이지는 색인되지 않는다.** 색인 기준은 3장 8번이다.
3. 사람이 **검수와 공개 설정만** 하면 공개할 수 있다.
4. 한국어와 외국어 8개 판이 같은 공개 범위로 나간다.
5. 새 사이트 어디에도 **군산 데이터·문장·그림·키·주소가 섞이지 않는다.**

안전장치·문서·테스트·모션의 양은 성공 기준이 아니다.

**일하는 방식**
- 목표는 80~90%를 자동으로 끝내는 것이다. 나머지는 빈칸 보고서(7장)로 넘긴다.
- 5장(사람이 정할 것)이 아닌 일은 멈추고 묻지 않는다. 판단해서 진행하고 `docs/handover/<slug>_log.md`에 한 줄 남긴다. 형식은 `날짜 · 무엇을 · 왜`다.
- 5장 항목은 결정하지 않는다. 선택지와 권장안으로 보고하고, 그동안 다른 단계를 진행한다.
- 사람이 해야 하는 일(체크포인트)에 닿으면 할 일을 한 번에 정리해서 알린다. 필요한 명령, 넣을 곳, 확인 방법을 함께 적는다.
- 큰 단계가 끝날 때마다 커밋한다. 커밋 메시지는 `무엇을 — 왜`로 짧게 쓴다.
- 작성과 검토를 나눈다. 네가 쓴 요약·가이드·번역의 사실 대조는 다른 세션이나 다른 도구에 맡긴다. 같은 대화에서 자기 글을 다시 읽는 것으로 대신하지 않는다.

---

## 3. 절대 규칙

군산각 운영 규칙을 지역에 맞게 옮긴 것이다. 어기면 그 작업은 실패다.

1. **사실은 출처 데이터에서만 가져온다.**
   - 출처는 TourAPI, 그 지역 시·군의 공식 문화관광 사이트, 해당 시설의 공식 홈페이지다.
   - 없는 값은 블록마다 "확인 필요: 요금·주차"처럼 한 번만 쓴다.
   - 추정이나 일반 지식으로 채우지 않는다.
2. **필드마다 출처를 둔다.**
   - 한 장소의 사실이 여러 출처에서 오면 필드마다 출처와 확인일을 남긴다(`fact_sources`). 화면에도 표시한다.
   - 두 출처 값이 다르면 둘 다 보여 주고(`fact_alternatives`) "방문 전 전화 확인"을 한 줄 붙인다. 한쪽을 임의로 고르지 않는다.
3. **공식 관광 사이트의 원문·사진**
   - 페이지마다 공공누리 표시를 확인한다.
   - 표시가 없거나, 제4유형이거나, "All rights reserved"이면 원문·사진을 싣지 않는다. 원문은 링크로만 건다.
   - 설명은 우리 문장으로 쓴다. 원문과 15자 이상 연속으로 같으면 안 된다.
   - 표의 값(시간·요금·메뉴)은 그대로 써도 된다.
   - 표시가 불명확하면 `UNKNOWN`으로 적는다. KOGL-1로 추정하지 않는다.
4. **TourAPI 사진**
   - `cpyrhtDivCd`가 Type1·Type3인 것만 쓴다. "출처: 한국관광공사"를 표기한다.
   - Type3은 자르기·확대·보정을 하지 않는다.
   - TourAPI `overview` 문장은 싣지 않는다. 사실 확인용으로만 쓴다(게재는 사람 결정).
5. **요약 문장은 답부터 쓰는 평서문이다.**
   - 첫 문장을 "○○은 ○○시 ○○에 있는 ○○입니다"로만 끝내지 않는다. 그 장소만의 사실(대표 메뉴·좌석·객실 수·운영 특징·볼거리)을 하나 이상 넣는다.
   - 쓸 사실이 없으면 짧게 두고 색인 대상에서 뺀다.
   - "원문은 ~" 같은 출처 해설체는 쓰지 않는다.
6. **FAQ**
   - 질문은 존댓말 "~나요?/~인가요?"로 통일한다.
   - 같은 질문을 여러 장소 페이지에 반복하지 않는다. 지역 단위 질문은 가이드로 옮긴다.
   - 데이터로 답할 수 없는 질문은 만들지 않는다.
7. **공개는 사람이 정한다.**
   - 다음 값은 바꾸지 않는다: `status=published`, `reviewed_at`, `approved_at`, `site.json`의 `site_url`·`ga4_id`·`brand`·`operator`·`publish_rules`·`crawler_policy`, noindex·robots 해제.
   - 바꿔도 되는 경우는 둘이다. 사람이 대화에서 값을 주며 지시한 경우, 사람이 표시한 검수 시트를 반영하는 경우.
8. **색인 기준(production)**: 장소 페이지는 세 조건을 모두 갖췄을 때만 색인한다(`pipeline/schema.index_status`).
   - (a) 유형별 필수 정보가 2개 이상이다.
     - 관광지: 이용시간·쉬는 날·요금·주차·전화
     - 음식점: 이용시간·메뉴·주차·전화
     - 숙소: 체크인·주차·전화·홈페이지
   - (b) 요약이 5번 규칙을 지킨다.
   - (c) `reviewed_at`이나 `approved_at`이 있다.
   - 미달 페이지는 noindex로 내보내고 sitemap·llms.txt에서 뺀다. 목록·지도에는 남긴다.
9. **비밀값**
   - 1장 표의 곳에만 둔다. `.env`를 열어 보거나 출력하지 않는다.
   - 로그에서는 키 문자열만 가린다. 공급자 오류 메시지는 그대로 보인다.
   - 비밀값을 찾으면 값을 말하지 않고 위치만 말한다.
10. **제3자 콘텐츠**
    - 네이버 플레이스·블로그·리뷰·평점은 복제하지 않는다.
    - 회원가입·예약·결제는 넣지 않는다. 예약은 공식 예약 페이지로 가는 링크만 둔다.
    - 특정 업체를 근거 없이 추천하지 않는다.
11. **챗봇**
    - 이 사이트 데이터로만 답한다. 없는 값은 '사이트에 없음'과 공식 확인처를 알려 준다. 출처가 다르면 둘 다 알려 준다.
    - 답마다 해당 페이지 링크를 단다. 질문한 언어로 답한다.
    - 대화는 저장하지 않는다.
12. **AI 그림(일러스트)**
    - 배경·캠페인 그림·장식으로만 쓴다. 'AI 생성 이미지' 표기는 하지 않는다(validate가 막는다).
    - alt는 '일러스트: '로 시작한다. 외국어는 언어별 접두어를 쓴다.
    - 소개 페이지에 '이 사이트의 일러스트는 생성형 AI로 그렸다'를 한 번 적는다.
    - 장소 사진 자리(장소 페이지 사진·썸네일·장소 카드)와 장소 구조화 데이터(ImageObject·장소 og:image)에는 쓰지 않는다.
13. **빈 데이터를 장식으로 덮지 않는다.** 가짜 사진, 가짜 지도, 큰 빈 표지를 쓰지 않는다.
14. **첫 화면을 스크립트로 숨기지 않는다.** 연출은 첫 화면 아래 요소에만 쓴다. reduced-motion이거나 JS가 없으면 최종 상태로 보여 준다.
15. **검증 규칙을 완화해서 통과시키지 않는다.**
    - 테스트를 지우거나 약하게 만들어 통과시키지 않는다. skip·느슨한 단언으로 바꾸는 것도 안 된다.
    - 새 방어 장치(누적 장부·잠금·메시지 은폐)를 만들지 않는다. 실행당 상한·캐시·키 가림이면 충분하다.
16. **군산을 섞지 않는다.**
    - `data/gunsan/`의 값·문장·번역, 군산 그림·사진·로고, 군산 키·ID·주소를 새 사이트에 쓰지 않는다(부록 A).
    - 군산 문장을 '예시'로 남겨 두지도 않는다.
17. **추가 출처 수집은 사람이 정한다.**
    - TourAPI와 공식 사이트에서 손으로 확인한 값으로 시작한다.
    - 공식 사이트 수집기를 새로 만들지는 5장 결정이다. 만들게 되면 4장 4단계의 수집 예절을 지킨다.

---

## 4. 작업 단계

### 한눈에

| 단계 | 하는 일 | 사람(CP) | 끝나면 있는 것 |
|---|---|---|---|
| 0 | 작업 폴더·git 준비, 군산 산출물 치우기 | — | 새 저장소 첫 커밋 |
| 1 | 엔진 지역화(군산 값을 데이터로 빼기) | — | 군산 빌드와 같은 결과 + 지역 설정 파일 |
| 2 | `site.json`과 빈 데이터 파일 | CP1 | 빌드가 도는 빈 사이트 |
| 3 | TourAPI 수집 | CP1 | 장소·행사·사진·상세 |
| 4 | 공식·공공 출처 보강 | — | 필드별 출처, 충돌 값 |
| 5 | 장소 요약·FAQ·자세히 | — | 상투구 0 |
| 6 | 가이드·코스·행사·테마·홈 글 | — | 가이드 초안 |
| 7 | 브랜드 | CP2 | 로고·아이콘 |
| 8 | 그림 | CP3 | 그림 파생본 |
| 9 | 검수와 공개 승인 | CP4 | published 레코드 |
| 10 | 외국어 8개 판 | — | 8개 언어 데이터 |
| 11 | 챗봇·코스 만들기 | — | 지역 챗봇 |
| 12 | 공개 빌드·테스트·성능 | — | `public/`, 보고서 |
| 13 | Vercel 배포·공개 뒤 확인 | CP5·CP6 | 공개 사이트 |

- 7·8단계는 3단계 뒤 아무 때나 해도 된다. CP를 기다리는 동안 하기 좋다.
- 10단계는 반드시 9단계 뒤에 한다.

---

### 0단계 — 작업 폴더 준비
1. 저장소 루트에서 모든 명령을 실행한다. 도구들이 `.env`·`reports/`를 현재 폴더 기준으로 쓴다.
2. 점 파일이 있는지 본다: `.gitignore`, `public/.webforai-build`.
   - `.gitignore`가 없으면 `.env`·`node_modules`가 커밋될 수 있다. 부록 C의 내용으로 다시 만든다.
3. `git init` → 모든 파일을 첫 커밋으로 남긴다. 메시지는 "군산각 엔진 6a26206c4 기준"이다.
   - 도구 여러 개가 "사람이 `git diff`로 확인"을 전제로 한다.
4. 설치한다.
   - `python -m pip install -r requirements.txt`
   - `python -m pip install "pillow>=11.3" fonttools playwright`: requirements.txt에 없지만 그림·브랜드·브라우저 테스트에 필요하다. Chromium이 없으면 `python -m playwright install chromium`도 한다.
   - `npm ci`
5. **회귀 기준 빌드를 만든다.** 1단계 검증에 쓴다.
   - `python -m pipeline.build --data data/gunsan --out dist-base --mode production`
   - 시간은 약 5분이다. `dist-base/`는 git에 넣지 않는다(`dist-*`는 이미 무시 대상이다).
   - 행사는 오늘 날짜로 지난 것과 다가오는 것을 나눈다. 그래서 1단계 비교 빌드는 같은 날 만든다. 날이 바뀌면 `dist-base`를 다시 만든다.
6. **군산 공개 산출물을 지운다.** `public/` 폴더를 통째로 지우고 커밋한다.
   - ZIP의 `public/`은 군산 사이트 그대로다. 군산 주소, 군산 IndexNow 키 파일이 들어 있다.
   - 지워 두면 실수로 배포해도 군산이 나가지 않는다. `public/`은 12단계 공개 빌드가 다시 만든다.
7. `CLAUDE.md`·`AGENTS.md`를 부록 E 틀로 새 지역용으로 바꾼다.
   - `CODEX_TASKS.md`와 군산 `docs/handover/` 문서는 읽기 참고로만 쓴다. 12단계 전에 지운다(부록 A).
   - 지금 지우지 않는 이유가 있다. 그림 요청 틀(`docs/handover/image_prompts_round2_2026-10-13.md`)과 챗봇 운영 문서(`docs/handover/chatbot.md`)를 중간에 참고하기 때문이다.
8. `docs/handover/<slug>_log.md`를 만들고 첫 줄을 쓴다.

### 1단계 — 엔진 지역화

**1-1. 원칙**
- 코드에 박힌 군산 값을 지역 설정 파일로 옮긴다. 파일은 `data/<region>/region.json`(이름은 네가 정해도 된다)이나 `site.json`의 새 키다.
- 지역 이름은 `site.json` 값에서 만든다.
- 그다음 **군산 값으로 채운 설정**으로 빌드한다. `dist-base`와 같은 결과가 나와야 한다(`diff -r`). 이것이 리팩터링이 맞았다는 증거다.
  - 차이가 나는 경우는 둘뿐이어야 한다: 빌드 날짜 줄, 그리고 의도해서 바꾼 것(로그에 적는다).
- 그다음 새 지역 값을 채운다. 값이 비면 해당 블록을 **내지 않게** 한다. 군산 문구로 떨어지게 두지 않는다.
- 이렇게 해 두면 나중에 엔진 개선을 지역 저장소에 그대로 옮길 수 있다(9장).
- 시간이 모자라 이 방식을 못 쓰는 상수가 있으면 그 자리에서 새 지역 값으로 바꾼다. 무엇을 그렇게 했는지 로그와 보고서에 적는다.

`region.json` 예시 뼈대다. 키 이름은 정리하면서 확정한다.
```json
{
  "areas": [{"key": "…", "name": "…", "anchor_slug": "…", "art": "area-…"}],
  "far": {"meters": 12000, "label": "…"},
  "province": {"full": "경상북도", "short": "경북"},
  "bounds": {"lat": [36.6, 37.1], "lng": [128.4, 128.8]},
  "default_point": [36.8, 128.6],
  "address_tail_en": "Yeongju-si, Gyeongsangbuk-do",
  "resident_label": "영주시민",
  "official_hosts": [],
  "sources": {"city_prefix": "…", "access": {}, "fee": null},
  "home": {"story": [], "oldtown": null, "islands": null, "focus_dishes": [], "search_example": "…", "teaser_course": null, "video_topics": []},
  "lists": {}, "purposes": [], "hero_picks": [], "attraction_groups": [], "designations": {},
  "media": {"hero_slides": [], "home_cover": null, "story_photos": [], "gallery": []},
  "event_kinds": {},
  "intl": {"en": {"site_name": "Yeongjugak", "city": "Yeongju", "home_h1": "All About Yeongju Travel"}},
  "planner": {"hubs": [], "islands": [], "share_salt": "yeongju-plan-share-v1"},
  "chat": {"title": {}, "chips": {}, "placeholder": {}}
}
```

**1-2. 조용한 실패부터 고친다.** 아래는 고치지 않아도 빌드는 통과한다. 그래서 군산 값이 몰래 남거나 블록이 사라진다.
1. **TourAPI 지역 찾기**(`tools/tourapi_bulk.py` `run`)
   - 지금은 `region_full` 기본값이 `"전북특별자치도 군산시"`이고, 시·군을 `next()`로 하나만 고른다.
   - 기본값을 없애고, 값이 없거나 이름이 안 맞으면 알아듣기 쉬운 오류로 멈추게 한다. 지금은 `StopIteration` 트레이스백이 나온다.
   - 같은 패턴이 `tools/en_content.py`(시·군을 찾는 두 곳)에도 있다.
   - 광역시의 구·군 여러 곳이나 세종시이면 시·군 코드를 모두 돌거나 시·도 단위로 받게 넓힌다. 테스트도 더한다.
2. **외국어판 도시 이름**: `pipeline/locales.py` `LOCALES`의 `site_name`·`city`·`home_h1`(8개 언어)을 지역 설정에서 읽게 한다.
   - `pipeline/en_site.py`는 지역 이름을 `loc.city`에서 읽는다.
   - 러시아어처럼 격변화가 있는 언어는 `home_h1`을 통째로 받는다(예: 'Всё о Кунсане').
3. **아이콘 등록 경로**: `pipeline/icons.py` `REGISTRY`와 `tools/icon_media.py`가 `data/gunsan/icons.json`으로 고정되어 있다. 빌드 중인 `--data` 폴더를 따르게 한다.
   - `icons.json`은 거의 공통이라 새 폴더로 복사해도 된다. 라벨 '해외에서 본 군산'은 바꾼다.
4. **좌표 범위**: `pipeline/schema.py` `REGION_BOUNDS`·`CITY_DEFAULT_POINT`
   - 지역 이름이 키에 없으면 범위 검사가 꺼진다. 지역 설정에서 읽게 한다.
   - 새 지역 상자는 행정 경계를 조금 넉넉히 잡는다. 섬이 있으면 섬까지 넣는다.
5. **외국어 문구 파일**: `data/<region>/<lang>/strings.json`은 군산 것을 복사하지 않는다. 10단계에서 새로 만든다.
   - 복사하면 키가 다 있어서 빌드가 통과한다. 하지만 언어마다 30여 개 줄이 군산 문구로 나간다.
6. **영문 주소**
   - `pipeline/en_source.py` `_ADDR`·`_LOT`·`_TAIL`은 '전북특별자치도 군산시'만 읽고 'Gunsan-si, Jeonbuk State'를 붙인다. 지역 설정에서 읽게 한다.
   - `tools/en_content.py`의 번역 규칙 문장(`RULES`·`rules_for`)에도 같은 꼬리가 있다.
7. **도 이름 통일**: `pipeline/textutil.py` `PROVINCE`·`_PROVINCE_PREFIX`와 `pipeline/relations.py`가 전북 표기만 맞춘다. 다른 도는 '경북'과 '경상북도'를 다른 주소로 본다.
8. **사이트 주소 상수**
   - 해당 위치: `chatbot/knowledge.js` `SITE`, `templates/assets/chat.js` `SITE`, `templates/assets/plan.js` `SITE`, `chatbot/server.js` `PRODUCTION_ALIASES`·`PREVIOUS_SITES`
   - 빌드가 `site.json` `site_url`을 넣게 바꾼다. 예: `public/chat/docs.json`의 `site`, 페이지의 data 속성.
   - `PREVIOUS_SITES`는 `[]`로 시작한다.
   - 짝 테스트: `tests/js/chat.test.js`, `tests/js/plan_share.test.js`
9. **버스 99번·guide-31**: 다음 위치가 군산 노선 번호와 가이드 id에 묶여 있다. 지역 설정을 따르게 하거나, 교통 데이터가 없으면 쓰지 않게 한다.
   - `pipeline/present.py`, `templates/_ui.html.j2`, `templates/en/_en.html.j2`
   - `pipeline/validate.py` `transit_problems`
10. **주간 갱신 2단계**: `tools/refresh.py`가 군산 전용 `tools/round3_official.py`를 부른다.
    - 새 지역에서는 그 단계를 빼거나 지역판으로 바꾼다. 지금은 KeyError로 멈춘다.
11. **도구의 `--data` 기본값**
    - 약 20개 도구의 기본값이 `data/gunsan`이다. `tools/round3_content.py`는 `DATA`가 고정이라 `--data`가 아예 없다. `tools/en_content.py check`는 군산 `en/names.json`을 읽는다.
    - 모두 `--data`를 받게 하고, 기본값을 없애 필수 인자로 만든다.
12. **장소 이름 꼬리**: 다음 함수가 '(군산)'·'(군산시)'만 떼어 낸다. 지역 이름으로 바꾼다.
    - `tools/tourapi_bulk.py` `photo_title()`
    - `tools/tourapi_details.py` `display_name()`
13. **카카오 장소 매칭**: `tools/kakao_places.py`의 지역 필터(`SAFE_EXTRAS`·`REGION_PREFIX`·`queries()`·`judge()`)가 군산이다. 그대로 두면 모든 후보가 '지역 밖'으로 떨어진다.
14. **상투구 판정**: '○○시'를 잡는 정규식이 세 곳에 있다. 지역 `locality`에서 만들게 한다. 두 값이 같은지 보는 테스트가 있다.
    - `pipeline/schema.py` `INDEX_TAUT`
    - `tools/quality_report.py` `TAUT`
    - `tools/round3_content.py` `TAUT`

**1-3. 나머지 군산 값**
- 부록 B 표를 위에서부터 처리한다.
- 가이드 id(`guide-NN`)에 묶인 화면 문구(`present.py`의 `ANSWER_COPY`·`HOME_ANSWERS`·`HUB_LEAD` 등)는 다음 둘 중 하나로 처리한다.
  - 새 지역 가이드의 `answer` 필드로 옮긴다. `guide_answer()`는 `answer`를 상수보다 먼저 쓴다.
  - 비운다.
- 같은 id를 다시 쓰면서 군산 문구를 두면 안 된다. 숫자 대조에서 떨어져 경고만 남는다.

**1-4. 군산 전용 도구와 테스트 정리**
- **지울 도구**
  - `tools/collect_gunsan*.py`, `tools/gunsan_*.py`, `tools/archive_gunsan_static.py`, `tools/import_gunsan_*.py`
  - `tools/official_coords.py`: 함수 `parking_rows()`·`add_nearby_parking()`은 범용 모듈로 옮긴 뒤 지운다.
  - `tools/museum_notices.py`, `tools/round3_official.py`, `tools/round3_festivals.py`
  - 짝 테스트도 함께 지운다.
- **지우기 전에 import 관계를 확인한다.** 예: `tools/round3_content.py`가 `tools/round2_content.py`의 함수를 쓴다. 필요한 함수는 남기거나 옮긴다.
- **`data/gunsan`을 읽는 테스트**(약 30개 파일, 부록 B-8)
  - `data/<region>`을 읽게 바꾼다.
  - 군산 사실을 단언하던 줄은 **같은 성질을 새 지역 데이터로 단언하게** 다시 쓴다.
  - 새 지역에 그 기능의 데이터가 없으면(예: 해외 반응, 버스 시간표) 테스트를 지우지 않는다. `data/sample`에 작은 고정 데이터를 넣어 엔진 동작을 계속 확인한다.
  - `data/sample`은 엔진 테스트 고정 데이터라 그대로 둔다. 공개 빌드에는 쓰이지 않는다.
- **`vercel.json`**: `redirects`를 전부 지우고 `"redirects": []`로 둔다. 모두 군산 주소 이전용이다. 나머지 키는 유지한다.
  - 짝 테스트는 `tests/test_domain_move.py`와 `tests/test_en_site.py`의 guide-NN 리다이렉트 단언이다. 군산 주소 이전 단언만 지우고, `vercel.json` 구조 단언(`outputDirectory`·`includeFiles`·`trailingSlash` 등)은 남긴다.
- **`data/gunsan` 폴더 자체**는 1-5 확인이 끝나면 지운다.

**1-5. 완료 확인**
- 군산 설정으로 만든 빌드가 `dist-base`와 같다(1-1).
- `python -m pytest`가 통과한다(이 시점에는 군산 데이터로 돈다).
- `node --test tests/js/*.test.js`가 통과한다.
- `data/gunsan`을 지운 뒤 다음 grep 결과가 주석 말고 0줄이다.
  ```
  grep -rnE '군산|[Gg]unsan|群山|Кунсан|Jeonbuk|전북특별자치도' pipeline chatbot templates tools api vercel.json package.json
  ```
  - 예외: 내부 함수 이름 `window.gunsanTrack`은 동작과 무관해서 그대로 둬도 된다(바꾸려면 site.js·track.js·plan.js를 함께 바꾼다).
  - 예외: CSS 색 이름 주석.

### 2단계 — `site.json`과 빈 데이터 파일
1. `data/<slug>/site.json`을 쓴다. 필드는 부록 C의 표를 따른다.
   - **입력값을 넣는 키**: `site_url`, `site_name`, `brand`, `brand_symbol`, `region`, `locality`, `region_admin`, `region_full`(새 키, 반드시 넣는다), `description`, `disclaimer`, `source{name,url}`, `official_links`, `tourapi.region_keyword`, `kakao_js_key`, `indexnow_key`
     - `indexnow_key`는 `python -c "import secrets;print(secrets.token_hex(16))"`로 새로 만든다.
   - **그대로 쓰는 키**: `operator`(회사 공통, `contact` 확인), `emergency`(전국 번호), `tmap_scheme`, `tourapi`(나머지 키), `publish_rules`(KOGL-1·3)
   - **비워 두는 키**(사람 결정): `ga4_id`, `gtm_id`, `search_verification`
     - GA4가 없으면 `launch_exceptions.ga4_id`에 사유를 적는다. 없으면 production 검증 오류다.
   - `crawler_policy`는 군산 값을 임시로 두고 5장에 올린다.
   - 군산의 `_notes`·`publication`·`source`·`description`은 옮기지 않는다.
2. 빈 파일을 만든다.
   - `places.json` `[]`, `events.json` `[]`, `courses.json` `[]`, `guides.json` `[]`
   - `themes.json`: 지역에 맞는 테마 3~5개, `[{slug,name,description}]`
   - `tourapi_overrides.json` `{"same":{},"different":[],"hold":{},"skip":[]}`
   - `art.json` `{"images":{},"held":{}}`, `icons.json`(1-2의 3번)
3. **지역 코드를 확인한다**(CP1). 키는 출력하지 않는다.
   ```
   python -c "import os;from pathlib import Path;from pipeline.enrich import load_dotenv;load_dotenv(Path('.env'));from pipeline.tourapi import TourAPI;a=TourAPI(os.environ['TOURAPI_KEY'],cache_dir='data/cache/tourapi',max_calls=3);print([(r['code'],r['name']) for r in a.ldong_code()])"
   ```
   - 시·도 코드를 찾은 뒤 `a.ldong_code('<시도코드>')`로 시·군 이름을 본다.
   - `region_full`은 공급자가 돌려주는 이름 그대로 쓴다. 2026년 행정 개편으로 시·도 이름이 바뀌었을 수 있다.
4. 미리보기 빌드와 검증이 오류 0으로 도는지 본다(부록 C).
   - events·courses가 비어 있으면 `/events/`·`/courses/`로 가는 링크가 깨진다는 오류가 날 수 있다.
   - 이 오류는 3·6단계에서 데이터가 들어오면 사라진다. 그때까지는 '알려진 오류'로 로그에 적는다. 규칙은 완화하지 않는다.

### 3단계 — TourAPI 수집
1. `python tools/tourapi_doctor.py --keyword "<probe_keyword>"` → '정상'이 나오는지 본다.
2. `python tools/tourapi_bulk.py --data data/<slug> --add-new --events --max-calls 900`
   - 상한에 닿으면 멈춘다. 캐시가 이어 주므로 다음 날 같은 명령을 다시 돌린다.
   - `reports/tourapi_bulk.md`에서 '중단'이 사라질 때까지 반복한다.
   - 새 장소는 `draft`·`basic`·`summary ""`로 들어온다.
   - 대상 유형은 관광지·문화시설·레포츠·쇼핑·숙박·음식점이다.
   - `searchFestival2`는 1쪽(100건)만 받는다. 행사가 더 많은 지역이면 쪽 넘김을 더한다.
3. 보고서를 보고 정리한다. 네가 판단하고 로그에 적는다. 사람은 9단계 검수 시트에서 본다.
   - 체인 매장, 지역 밖 → `tourapi_overrides.json` `skip`
   - 애매한 것 → `hold`(사유)
   - TourAPI 안의 중복(1호점·2호점, 같은 곳 두 번) → `duplicate_of`
   - 장소가 아닌 항목(행정 안내, 상품, 행사) → `exclude: "not_a_place"`
4. `python tools/tourapi_bulk.py --data data/<slug> --details --gallery --max-calls 900` → `python tools/image_sizes.py --data data/<slug>`
5. 주의할 것
   - 확인일(`checked_at`)은 캐시 파일 시각이다. 캐시 폴더를 옮기지 않는다.
   - TourAPI 코스(유형 25) 가져오기는 이 엔진에 없다. 코스는 6단계에서 다룬다.
6. 공개 승인(9단계) **뒤에** 할 것
   - 무장애 정보: `python tools/tourapi_bulk.py --data data/<slug> --barrier-free --max-calls 600`. 별도 활용신청이 필요하다.
   - 카카오 장소 ID: `python tools/kakao_places.py --data data/<slug>`로 보고서를 확인한 뒤 `--apply`. 키는 환경 변수 `KAKAO_REST_KEY`다.
   - 좌표가 바뀌었으면 `python tools/tourapi_bulk.py --data data/<slug> --nearby-only`

### 4단계 — 공식·공공 출처 보강
1. 공식 관광 사이트 이용조건을 확인한다.
   - 공공누리 표시, robots.txt를 본다.
   - 근거는 `data/raw/<slug>/rights_evidence.json`, `data/raw/<slug>/robots_check.json`에 남긴다.
2. 수집기를 새로 만들지는 5장 결정이다. 그 전에는 다음만 한다.
   - TourAPI 값과 시설 공식 홈페이지 값을 손으로 확인한다. 기록은 `fact_sources[키]={provider,url,checked_at}`다.
   - 값이 다르면 `fact_alternatives`에 둘 다 넣는다.
3. 수집을 허락받으면 다음 예절을 지킨다.
   - UA는 `WebforAI-collector/0.1 (research; o2o.kr)`로 한다. 간격은 3초, 연결은 하나다.
   - 목록과 상세를 동시에 돌리지 않는다. 누적 980회 이하로 한다.
   - 403·429가 나거나 연속 5회 오류가 나면 멈춘다. 우회하지 않는다.
   - 사진은 주소만 기록한다.
4. 공공데이터(선택, 해당 가이드를 만들 때)
   - **주차**: 전국주차장정보표준데이터(data.go.kr 15012896)의 지역 행으로 `parking_lots.json`을 만든다. 요금은 지역 주차장 조례로 확인한다.
   - **버스**: 지역 버스정류장 데이터로 `nearby.json`을 만든다. 이 엔진에는 버스 쪽 도구가 없다. 노선 번호는 시간표 이름이 글자 그대로 같을 때만 쓴다.
   - **지정 업소**: 백년가게 전국 목록(15132695)은 그대로 쓸 수 있다. 지역 지정 목록(모범음식점 등)은 지역 공식 자료로 새로 조사한다.
5. **이용시간 충돌**: 출처가 다른 값은 3장 2번대로 처리한다. 해소한 것과 남은 것을 보고서에 적는다.

### 5단계 — 장소 요약·FAQ·자세히
`tools/round3_content.py`를 쓴다(1-2의 11번에서 `--data`를 붙인 뒤).
```
python tools/round3_content.py prepare --data data/<slug> --out work/places --batch 12
#  → 입력 파일마다 너(또는 작성 세션)가 rules대로 places-NN.output.json을 쓴다
python tools/round3_content.py check work/places/places-NN.output.json
#  → 다른 세션이 사실표와 대조한다 → 다시 check
python tools/round3_content.py merge --data data/<slug> work/places/places-*.output.json
```
- **대상**: 음식점·숙소 전부, `tourapi-` 장소 전부, 요약이 비었거나 상투구인 관광지
- **출력 형식**: `{"items":[{"id","summary","faq":[{q,a,source}],"thin"?:true}]}`
- **검사 내용**
  - 요약 속 숫자는 모두 사실표에 있어야 한다.
  - 음식점·숙소 FAQ는 2개 이하다.
  - 15자 이상 원문 복사, 수식어, 반복 질문은 거부된다.
- **`thin:true`**: 주소·홈페이지 말고 쓸 사실이 없을 때만 쓴다. 그 페이지는 noindex가 된다(3장 5번).
- **자세히**: 원문이 300자 이상인 곳만 `prepare-details`/`check-details`/`merge-details`로 쓴다.
- **끝나면**: `python tools/quality_report.py --data data/<slug> --out dist-preview`로 색인 대상 상투구 0, 주소 공백 0, 장소가 아닌 항목 0을 확인한다.

### 6단계 — 가이드·코스·행사·테마·홈 글
1. **가이드**
   - 군산 36편의 주제 분류를 출발점으로 쓴다(부록 B-9). 지역 데이터로 답할 수 있는 주제만 고른다.
   - 주제 목록은 보고서에 올린다. 사람이 나중에 빼거나 더할 수 있다.
   - 작성 순서
     1. `python tools/round3_content.py catalog --data data/<slug> --out work/catalog.json`
     2. 가이드 객체 작성: 질문형 `title`, `summary`, `body`, `items`, `sources`, `faq`, `answer{answer,fig,unit,closed}`
     3. 다른 세션이 사실을 대조한다.
     4. `python tools/round3_content.py check-guide work/guide-NN.json --catalog work/catalog.json`이 OK인지 본다.
     5. `guides.json`에 `draft`로 넣는다(병합 명령은 없다).
   - 가이드 id는 `guide-01`부터 새로 매긴다. 숫자는 근거가 있는 것만 쓴다(`allowed_numbers_from`, `_number_sources`).
   - 지역 단위 FAQ(3장 6번)는 가이드로 모은다.
2. **코스**
   - 지역 공식 코스가 있고 이용조건이 허락하면 `stops[]`를 우리 문장으로 만든다. 원문은 링크로만 건다.
   - 없으면 가이드의 동선을 코스로 만든다(`summary_auto`, `link_basis`).
   - 공개 코스가 0이면 `/courses/` 링크 오류가 나니 1개 이상 만든다.
3. **행사**
   - `--events`로 받은 행사에 `highlights`·`usual`을 우리 문장으로 쓴다.
   - 지난 행사는 분리되는지 확인한다.
4. **테마**: `themes.json`과 장소의 `themes`를 채운다.
5. **홈 글과 나머지**
   - 지역 설정의 홈 블록: 이야기·대표 음식·검색 예시·권역
   - `ask.json`: 9개 언어 질문 카드, 40자 이하
   - 소개 페이지 문장
   - 데이터가 없는 홈 블록은 비워서 나오지 않게 한다.

### 7단계 — 브랜드(CP2)
1. **이름**: '○○각'. 외국어 8개 판은 `site_name_intl`이다.
2. **로고 시안 프롬프트**: 사람이 이미지 도구에서 쓸 로고 프롬프트를 쓴다. `docs/handover/<slug>_logo_prompts.md`에 둔다.
   - 지역 상징 3~5개를 고른다. 시·군 공식 상징물이나 대표 경관을 쓰고, 근거를 적는다.
   - 시안마다 다른 상징으로 쓴다.
   - 공통 조건: 단순한 평면 도형, 두세 가지 색, 작은 크기에서도 알아보는 실루엣. 글자는 넣지 않는다(글자는 우리가 짠다).
   - 군산각과 시리즈로 맞출지는 5장 결정이다(권장: '각' 강조와 배치는 같게, 상징·색은 지역별로).
3. **사람이 고르면** 다시 그린다.
   - 고른 시안을 SVG 도형으로 다시 그린다. 글자는 Pretendard Bold 윤곽으로 짠다.
   - `tools/brand_kit.py`를 이름·파일 이름·색·도형을 인자로 받게 고친 뒤 실행한다.
   - Pretendard OTF는 저장소에 없다. 공식 배포본(OFL)을 받아 쓴다. 받지 못하면 CP로 요청한다.
4. **만들 파일**
   - `templates/assets/brand/<slug>gak-*.svg`(심볼·가로형·세로형)
   - `favicon.ico`, `icon-48/96/180/192/512.png`: Chromium이나 Pillow로 SVG를 렌더한다.
   - `site.json` `brand_symbol`을 새 파일로 바꾼다.
5. **지울 것**: `gunsangak-*.svg`와 군산 아이콘 PNG. `aio2o-*.svg`(운영사 로고)는 유지한다.

### 8단계 — 그림(CP3)
1. `templates/assets/art/`를 **비운다**(`manifest.json` 포함).
   - 같은 ID가 남아 있으면 `art_media`가 군산 파생본을 그대로 둔다.
2. **요청 문서**: 부록 D 틀로 `docs/handover/<slug>_image_requests.md`를 쓴다.
   - **최소 세트(먼저)**: og 9장, 목록 머리 9장, 소개 1장, 홈 카드 3장, 코스 만들기 2장
   - **전체 세트(다음)**: 월 12, 행사 종류 12, 영상 주제, 권역, 테마, 코스, 가이드 배너
3. **사람이 그림을 만든다**: 이미지 도구로 만들어 `incoming/ai-images/<ID>.png`로 저장한다.
4. **검수**: 사진처럼 보이는지, 가짜 글씨·번호가 있는지, 구도가 맞는지, 글자 그림의 글자가 한 글자도 틀리지 않았는지 본다.
   - 불합격은 `art.json` `held`에 이유와 함께 적는다.
5. **`art.json` 항목**
   - 받은 그림만 넣는다.
   - 글자 없는 그림은 9개 언어 alt를 쓴다. 접두어: ko '일러스트: ', fr 'Illustration : ', ja 'イラスト：', zh-hans '插图：', zh-hant '插圖：'
   - 글자 그림은 한 언어만 쓰고, `text`와 그 문장이 그대로 든 alt를 넣는다.
6. **파생본**: `python tools/art_media.py --data data/<slug> --dry-run` → `python tools/art_media.py --data data/<slug>`
   - ID 앞부분이 자르기 규칙을 정한다(부록 D).
7. **og 이미지**: 글자 없는 배경에 심볼·이름을 합성한 PNG를 `incoming/ai-images/og-<lang>.png`로 넣는다. 합성 스크립트는 저장소에 없으니 새로 만든다.
8. **장소 사진(KOGL-1)**
   - 지역 설정의 `media`(홈 슬라이드·표지)를 정한다.
   - `templates/assets/media/`(군산 사진 파생본)를 비운다.
   - `python tools/kogl1_media.py --data data/<slug>`
9. **재사용**
   - 3D 아이콘 52장은 그대로 쓴다.
   - 마스코트를 쓸지는 5장 결정이다. 원본 안내에 '군산 사이트 전용'이라고 적혀 있다.
10. **커밋**: 원본은 커밋하지 않는다(`incoming/`은 무시 대상이다). 파생본과 `art.json`만 커밋한다.

### 9단계 — 검수와 공개 승인(CP4)
1. `python tools/build_review.py --data data/<slug> --out dist-review --report-dir reports`
   - 기본값 `--out public`은 쓰지 않는다. 공개 산출물을 덮어쓴다.
2. `python tools/make_review_sheet.py --data data/<slug> --out docs/handover/review_<slug>.csv --base <site_url>`
3. **사람이 시트에 적는다.** '판정' 칸에 OK나 수정을 쓴다.
   - 권장 범위: 장소 10~20% 표본, 두 출처 값이 다른 곳 전부, 가이드·코스 전부.
4. `python tools/apply_review.py --sheet docs/handover/review_<slug>.csv --data data/<slug>`(미리보기) → `--apply`
   - OK 행만 `reviewed`가 된다.
5. **공개 승인은 운영자만 한다.**
   - 너는 `python tools/approve_publication.py --data data/<slug> --date <날짜>`(미리보기) 결과를 보고서에 붙인다.
   - 사람이 대화에서 "공개 승인, 날짜 YYYY-MM-DD"라고 지시하면 `--apply`로 실행한다.
   - 가이드·코스·행사는 전부 published가 된다. 빼려면 `--hold <id>`를 쓴다.

### 10단계 — 외국어 8개 판
**영어를 먼저 한다.** 다른 언어가 영어 slug를 받아 쓴다. 외국어 URL은 영어 이름에서 만들어지므로, 공개 뒤 영어 이름을 바꾸면 8개 언어 주소가 다 바뀐다.
```
python tools/en_content.py names   --data data/<slug> --lang en
python tools/en_content.py prepare --data data/<slug> --lang en --out work/en --batch 40
#  → en-NN.input.json마다 rules대로 en-NN.output.json을 쓴다
python tools/en_content.py check   work/en/en-NN.output.json
#  → 다른 세션이 검토한다 → 다시 check
python tools/en_content.py merge   --data data/<slug> work/en/en-*.output*.json
```
- **이름 정본**: `names`가 공식 외국어 이름을 찾지 못한 곳은 `en/names.json`에 문화체육관광부 관광 표기 지침대로 쓴다.
  - 검토 세션이 공식 표기를 바꾸지 못하게 이름은 `names.json`으로 고정한다.
- **나머지 언어**: ja, zh-hans, zh-hant, de, fr, es, ru를 같은 순서로 한다(`names` → `prepare` → 작성 → `check` → 독립 검토 → `check` → `merge`).
- **문구**: `strings.json`의 지역 문구를 새로 번역한다. 대상은 `site.*`, `theme.*`, `provider:*`, `REGIONS.*`, `designation*`, `ticket:*`, `chrome.*`의 지역 문장이다.
- **한국어를 고치면 그 항목의 번역이 빠진다**(`ko_hash` 불일치). 번역은 한국어가 확정된 뒤에 하고, 고치면 그 항목만 다시 번역한다.
- **완료 확인**: `build_public` 마지막 JSON 줄에서 다음 값이 모두 0이거나 없어야 한다.
  - `en_stale_skipped`
  - `intl_untranslated`(언어마다)
  - `intl_skipped`

### 11단계 — 챗봇·코스 만들기
1. **챗봇 문구**
   - `chatbot/prompt.js` `RULES`: 사이트 이름, 도메인, 예시 경로, 지역 예시를 새 지역 데이터에서 고른다.
   - 9개 언어 마무리 문구, 도구 설명 예시
   - `chatbot/knowledge.js`: 지역 문구(예: '○○시민 아님')
2. **화면 문구**: `templates/assets/chat.js`의 9개 언어 제목·질문 칩·입력창 안내. 칩은 `ask.json`과 같은 글로 맞춘다.
3. **코스 만들기**
   - `chatbot/plan_prompt.js` `PLAN_RULES`·`HUBS`
   - 출발·도착 거점 4곳을 같이 바꾼다: `present.PLAN_CHOICES["hubs"]`, `templates/assets/plan.js`, `templates/assets/chat.js`의 정규식. 거점은 기차역·버스터미널·공항 중 지역에 있는 곳이고, 좌표가 있는 장소여야 한다.
   - 코스 제목 문형('<지역> …박 …일 코스')
   - `chatbot/plan_state.js` `ISLANDS`, `chatbot/plan_share.js` `SHARE_SALT`(`<slug>-plan-share-v1`)
   - `chatbot/plan_geo.js` 거리 기준: 넓은 군 지역이면 장소 사이 거리 통계로 다시 잰다. 근거를 로그에 적는다.
4. **모델과 한도**: 모델은 `chatbot/prompt.js` `MODEL` 값을 그대로 쓴다. 호출 한도(`LIMITS`·`PLAN_LIMITS`)도 그대로 둔다.
5. **카탈로그 상한**: `tests/test_chat_index.py`가 상한(`CATALOG_BUDGET` 72,000)을 확인한다.
   - 넘으면 상한을 올리지 않는다. 숫자와 선택지(목록 줄이기·상한 올리기와 비용)를 5장으로 보고한다.
6. **테스트**: `node --test tests/js/*.test.js`, `python -m pytest tests/test_chat_index.py tests/test_chat_node.py tests/test_chat_ui.py`

### 12단계 — 공개 빌드·테스트·성능
1. 군산 `docs/handover/` 문서, `CODEX_TASKS.md`, 군산 전용 측정 파일을 지운다(부록 A).
2. `python tools/build_public.py --data data/<slug> --out public`(약 5분)
   - 마지막 JSON 줄에서 `qa_errors 0`과 10단계의 0 값을 확인한다.
3. `python -m pytest -rs`(전체 약 25분)
   - skip 목록을 꼭 본다. Playwright·Chromium이 없으면 브라우저 테스트가 skip인데 '통과'처럼 보인다.
   - `tests/test_ask_browser.py`는 부하가 걸리면 흔들린다. 실패하면 그 파일만 다시 돌린다.
4. `node --test tests/js/*.test.js`
5. `python tools/quality_report.py --data data/<slug> --out public --md docs/handover/<slug>_quality.md`
6. `python tools/perf_check.py --out public --pages / /places/<대표-장소-slug>/`
   - 목표: 모바일(느린 4G·CPU 4배) LCP ≤ 2.5초, CLS ≤ 0.1, 첫 방문 글꼴 ≤ 300KB
   - 글꼴 조각은 군산 글자 빈도로 나눈 것이다. Pretendard 원본 woff2(공식 배포본)를 받아 `python tools/font_subset.py --src <원본 woff2 폴더> --corpus public --corpus data/<slug>`로 다시 나누는 것을 권한다.
7. 화면 캡처를 확인한다. 360·390·768·1440 폭으로 홈·목록·장소·가이드를 찍어 보고 고친다. 이 확인을 2회 이상 한다.
   - 장소 첫 화면(390px) 순서: 이름 → 한 줄 답 → 핵심 정보 줄. 사진은 화면 높이의 45% 이하다.
   - 대비 4.5:1, 터치 영역 44px, 보이는 포커스를 지킨다.
8. `python tools/launch_check.py --data data/<slug>`로 사람이 할 일 목록을 다시 만든다.
9. 커밋한다. 소스, `data/<slug>/`, `public/`을 함께 커밋한다.

### 13단계 — Vercel 배포와 공개 뒤 확인(CP5·CP6)
구조: Vercel은 빌드하지 않는다(`vercel.json` `buildCommand ""`). 커밋된 `public/`을 그대로 내보내고, `api/chat.js`·`api/plan.js`만 함수로 돌린다.

**사람에게 넘길 목록(CP5)** — 이 내용을 그대로 정리해 준다.
1. **GitHub**: 새 저장소를 만들고 push한다. 이 시점에는 아직 배포되지 않는다.
2. **Vercel 프로젝트**
   - New Project → 저장소 Import → Preset Other, Root는 저장소 루트
   - Settings → Functions에서 Fluid Compute를 켠다. `maxDuration 120`에 필요하다. 끌 거면 chat을 60초로 줄인다(`docs/handover/chatbot.md`).
3. **환경 변수**(Production + Preview, Sensitive)
   - `ANTHROPIC_API_KEY`: 지역 전용 키
   - `PLAN_SHARE_SECRET`: `openssl rand -base64 32`로 만든다.
   - System Environment Variables 노출을 켠다. 꺼져 있으면 미리보기 배포에서 챗봇이 403이다.
   - 넣은 뒤 **새 배포**가 필요하다. 예전 배포를 Redeploy하면 오래된 `public/`이 나간다.
4. **비용·남용 막기**
   - Anthropic Console에서 월 지출 한도와 알림을 건다(군산 권장: 한도 $30, 알림 $15).
   - Vercel Firewall에 요청 제한 규칙을 건다: `/api/`, 60초, IP당 10회, POST.
   - AI 봇 규칙은 Allow나 Log로 둔다.
5. **도메인**(5장 결정)
   - 정해지면 Domains에 추가하고 DNS를 등록한다.
   - `chatbot/server.js` `PRODUCTION_ALIASES`에 Vercel 별칭을 넣는다.
   - `site.json` `site_url`을 바꾸고 다시 빌드한다.
6. **카카오**: 개발자 콘솔에 공개 주소(임시 vercel.app 포함)를 웹 도메인으로 등록한다. 등록하지 않은 주소에서는 지도가 401이다.
7. **배포 확인**: main에 push한 뒤 **그 커밋의 배포가 Ready**인지 본다. 이제부터 push가 곧 배포다.

**배포 뒤 확인(네가 할 수 있는 것은 네가 한다)**
1. `bash tools/check_access.sh https://<주소> --mode production --path /places/<slug>/ --path /en/`
2. 주소별 확인
   - `/`, `/places/<slug>/`, `/en/` `/ja/` `/zh-hans/` `/zh-hant/` `/de/` `/fr/` `/es/` `/ru/`
   - `/map/`: 카카오 지도가 실제로 뜨는지
   - `/plan/`: noindex인지
   - `/sitemap.xml`(URL 수), `/robots.txt`(Sitemap 줄이 새 주소인지), `/llms.txt`, `/<indexnow_key>.txt`(200), `/chat/catalog.txt`
3. **챗봇**: `docs/handover/chatbot.md` 5절의 확인(응답 스트림, 다른 Origin 403)을 새 주소로 한다. Vercel 로그 `evt:"chat"`에서 `status:"ok"`인지 본다.
4. **코스 만들기**: 하루 코스가 60초 안에 나오는지, 공유 링크가 다른 기기에서 열리는지 본다.
5. **검색엔진(CP6, 사람)**
   - 구글 서치콘솔·빙·네이버에 **새 주소로** 속성을 만든다. meta 방식이면 `search_verification`에 토큰을 넣고 다시 배포한다.
   - `https://<주소>/sitemap.xml`을 제출한다.
6. **IndexNow**: `python tools/indexnow.py --out public --data data/<slug>`(미리보기) → `--send`
   - 도메인이 정해지기 전 임시 주소에서는 보내지 않는다(권장).
7. **GA4**
   - 실시간 보고서를 확인한다.
   - 맞춤 측정기준을 등록한다: place_id, link_provider, page_kind, chat_where, link_lang, method, content_type, item_id
   - 주요 이벤트로 `booking_click`을 등록한다.
   - GTM을 쓰면 GTM 안에 GA4 태그를 다시 넣지 않는다. 중복 집계가 된다.
8. `perf_check`로 공개 주소를 재고 보고서에 적는다.

---

## 5. 사람이 정할 것

결정하지 말고 선택지와 권장안으로 보고한다.

| 항목 | 선택지 | 권장안 |
|---|---|---|
| 도메인 | ① 회사 하위 주소 ② 지역 전용 도메인 ③ 임시 vercel.app으로 먼저 공개 | 정한 뒤 공개한다. ③이면 옮길 때 이전 규칙·검색엔진 주소 변경·IndexNow를 다시 해야 한다 |
| 공개 범위·시점 | 전체 / 색인 기준 충족 장소만 / 단계 공개 | 승인 대상 전체를 공개한다. 색인은 기준이 거른다 |
| 외국어 도시 표기 | 공식 표기 후보 | 지자체 외국어 사이트 표기를 따른다 |
| 로고 | 시안 중 하나, 군산각과 시리즈 통일 여부 | '각' 강조·배치는 시리즈로 통일, 상징·색은 지역별 |
| 마스코트 | 군산 마스코트 재사용 / 새로 / 없음 | 새로 만들거나 뺀다(원본이 군산 전용 표시) |
| GA4·GTM | 지역별 새 속성 / 나중 | 지역별 새 속성(결과를 섞지 않게) |
| 검색엔진 인증 | meta 토큰 / DNS | 도메인 확정 뒤 한다 |
| 정정 요청 연락처 | 회사 공통 / 지역 담당 | 회사 공통 주소 |
| AI 학습 크롤러 | 허용 / 차단(`crawler_policy`) | 군산각과 같게(허용) — 실험 목적에 맞음 |
| 추가 출처 수집 | 공식 관광 사이트 수집기, 교통·주차 공공데이터 | 이용조건 확인 뒤 허용 범위를 정한다 |
| TourAPI overview 게재 | 게재 / 사실 확인용만 | 사실 확인용만(군산과 같음) |
| 고객사 숙소 노출 | 관계 표시 방식 | 관계가 있으면 페이지에 밝힌다 |
| 챗봇 카탈로그 상한 | 목록 줄이기 / 상한 올리기(비용 증가) | 숫자를 보고 정한다 |
| 테스트 정리 | 1-4 방식에서 판단이 갈리는 테스트 | 보고서에 목록으로 올린다 |
| 저장소 공개 여부 | 공개 / 비공개 | 비공개(원본 데이터 위치도 정한다) |
| 페이지 주소 형식 | 한글 slug(엔진 기본) / 영문 slug | 엔진 기본(한글). 외국어판은 영문이다 |

---

## 6. 화면 검수 순서(사람용)

배포 전에는 `dist-review`, 배포 뒤에는 공개 주소에서 본다. 휴대폰(390px)으로 먼저 본다.

1. **홈**
   - 첫 화면에 사이트 이름, 큰 제목, 검색이 바로 보이는지
   - 군산 문구·그림이 없는지
   - 홈 질문 카드가 실제 가이드로 가는지
2. **목록**(장소·음식·숙소)
   - 사진 없는 항목이 작은 아이콘 + 글줄로 나오는지
   - 칩의 값이 잘리지 않는지
3. **장소**: 대표 장소 5곳과 사진 없는 곳 3곳을 본다.
   - 이름 → 한 줄 답 → 핵심 정보 줄(운영시간·쉬는 날·요금·주차·전화 + 확인일) 순서인지
   - 출처가 다른 값이 둘 다 보이는지
   - 길찾기 앞줄이 3개인지
4. **가이드**: 숫자와 장소 이름이 실제 데이터와 맞는지 본다. 표본으로 5편을 본다.
5. **코스**: 정류장 순서와 링크를 본다.
6. **외국어**: 영어와 한자권 1개를 본다.
   - 도시 표기와 사이트 이름
   - 한글이 남지 않았는지
   - 언어 전환이 같은 페이지로 가는지
7. **챗봇**: 질문 셋을 해 본다.
   - 데이터에 있는 것, 없는 것, 외국어 질문
   - 답마다 링크가 달리는지, 없는 값에 '사이트에 없음'이라고 하는지
8. **코스 만들기**: 하루 코스 하나를 만들고 공유 링크를 열어 본다.

---

## 7. 완료 보고 형식

`docs/handover/<slug>_report.md`에 2쪽 이내로 쓴다.
1. **한 줄 상태**: 예) "공개 준비 완료, 사람 결정 4건 남음"
2. **숫자**
   - 장소: 전체 / 공개 / 색인 / noindex 사유별
   - 채움률(공개 장소 기준): 전화·이용시간·주차·사진·좌표
   - TourAPI: 호출 수, 매칭률, 추가 장소 수, 이용시간 충돌 해소 결과
   - 가이드·코스·행사(지난 행사 분리) 수
   - 외국어: 언어별 페이지 수, 미번역 0 여부
   - 그림: 장수(최소·전체 세트 중 어디까지)
   - 테스트: 통과·skip 수와 skip 이유
   - 성능: LCP, CLS, 글꼴 KB(홈·장소)
   - 챗봇 카탈로그 토큰
3. **빈칸 표**: `항목 | 이유 | 누가 | 필요한 것`
   - 예) "요금 미확인 37곳 | TourAPI·공식 사이트에 없음 | 사람 | 시설 전화 확인"
4. **사람이 정할 것**: 5장 항목 중 남은 것, 선택지와 권장안
5. **확인 필요**: 확인하지 못한 가정
6. **엔진을 바꾼 것**: 1단계에서 군산각과 달라진 엔진 파일 목록(9장 역반영용)

---

## 8. 공개 뒤 정기 운영

| 주기 | 할 일 | 명령·방법 |
|---|---|---|
| 배포마다 | 바뀐 페이지 알리기 | `python tools/indexnow.py --out public --data data/<slug> --since <날짜> --send` |
| 매주 | TourAPI 갱신 → 공개 빌드 | `python tools/refresh.py --data data/<slug> --dry-run` → 실제 실행 → push(사람 확인) |
| 매월 | 행사 갱신, 지난 행사 분리 확인 | `tourapi_bulk --events` |
| 매월 | 끊긴 링크 | `python tools/link_check.py --data data/<slug> --guides`(한국 네트워크) → `--apply` |
| 매월 | 측정 | GA4 이벤트, 서치콘솔 검색어·노출, AI 답변 인용 기록 |
| 한국어를 고칠 때 | 그 항목 번역 다시 | `ko_hash`가 바뀐 항목만 한 항목 배치로 |
| 분기 | 비용 | Anthropic 지출, Vercel 사용량 |
| 2027년 안 | 코스 만들기 공휴일 표 | 지금 표는 2026~2027년만 있다 |

---

## 9. 버전 관리
1. **기준 기록**: 새 저장소 `AGENTS.md` 맨 위에 다음을 적는다.
   - 기준 엔진: 군산각 `6a26206c4`
   - 이 프롬프트 판(v1.0)
   - 1단계에서 바꾼 엔진 파일 목록(7장 6번)
2. **엔진과 지역의 경계**
   - **엔진**: `pipeline/`, `chatbot/`, `api/`, `templates/`(아래 지역 몫 제외), `tools/`(지역 무관 도구), `tests/`
   - **지역 몫**: `data/<slug>/`, `templates/assets/{brand,art,media}/`, 지역 설정 파일, `public/`
   - 1단계를 원칙대로 했다면 엔진 파일에는 지역 값이 없다.
3. **공통 개선**(예: 새 기능)
   - 기준 엔진에서 만든 뒤 지역 저장소의 엔진 폴더에 옮긴다.
   - 옮긴 뒤 `pytest`와 `build_public`으로 확인한다.
4. **역반영(권장, 사람 결정)**: 첫 지역에서 만든 '지역 값 분리' 엔진을 군산각에도 되돌려 넣는다. 그러면 이후 모든 지역이 같은 엔진을 쓴다.
5. **파트너 파생본**: 지역 저장소를 복제해 브랜드·운영 주체·연락처만 바꾼다. 범위는 사람이 정한다.
6. **이 프롬프트 개정**: 판을 올리고(v1.1 …) 맨 위 표에 바뀐 점을 한 줄 적는다.

---

## 부록 A. 새 지역으로 가져가지 않는 것
- **데이터**
  - `data/gunsan/` 전부: 장소·가이드·코스·행사·테마, 8개 언어 폴더, `art.json`, `ask.json`, `booking.json`의 장소 목록, `tickets`·`transit`·`parking_lots`·`nearby`·`notices`·`videos`·`abroad*`·`source_documents`·`tourapi_overrides`·`image_sizes`
  - `data/raw/gunsan`, `data/research`
- **그림·사진·브랜드**
  - `templates/assets/art/` 전부
  - `templates/assets/media/`(군산 사진 파생본)
  - `templates/assets/brand/gunsangak-*`, `favicon.ico`, `icon-*.png`
- **산출물**: `public/` 전부(군산 IndexNow 키 파일 포함)
- **설정값**: `site.json`의 `site_url`·`ga4_id`·`gtm_id`·`search_verification`·`indexnow_key`·`kakao_js_key`(같은 카카오 앱을 쓸지는 사람 결정)·`source`·`description`·`disclaimer`·`_notes`·`publication`
- **배포·키**: `vercel.json` `redirects`, 군산 Vercel 프로젝트·별칭, 군산 `ANTHROPIC_API_KEY`
- **문서**
  - `CLAUDE.md`·`AGENTS.md`·`CODEX_TASKS.md`의 군산 내용
  - `docs/handover/` 군산 문서, `docs/handover/review_round3.csv`
  - `measurement/questions.csv`의 군산 질문(질문 구조와 `measurement_workbook.xlsx` 틀은 재사용한다)
  - 예전 그림 지시 문서(`vscode_images_prompt.md`, `image_prompts_2026-10-13.md`): 'AI 생성 이미지' 표기를 지시하는데, 지금은 validate 오류다.
- **도구**: 1-4의 군산 전용 도구들
- **재사용해도 되는 것**
  - 엔진 코드
  - `data/sample`(테스트 고정 데이터)
  - `site.json`의 `operator`·`emergency`·`tmap_scheme`·`publish_rules`·`tourapi` 설정
  - `booking.json`의 bus·rail·ferry 서비스와 `exclude_hosts`
  - 3D 아이콘, Pretendard 글꼴, `aio2o-*.svg`

## 부록 B. 코드 속 군산 값 위치표
기준 커밋 `6a26206c4`의 값이다. 이름으로 찾는다.

**B-1. pipeline**

| 위치 | 군산 값 | 할 일 |
|---|---|---|
| `present.py` `REGIONS`·`FAR_M`·`FAR_LABEL`·`REGION_ART`·`DIST_ANCHORS` | 권역 5개와 기준 장소, '먼 섬' | 새 권역. 권역을 나눈 기준을 지도 페이지에 적는다. strings `REGIONS.n`을 다시 번역한다 |
| `present.py` `OFFICIAL_WEB` | 군산 호스트 3개(전국 호스트는 유지) | 지역 공식 호스트 |
| `present.py`·`en_site.py`의 `"gunsan.go.kr"` 판정 | 군산시 도메인 | `site.source.url` 도메인 |
| `present.py`·`build.py`·`chat_index.py`의 '군산시'·'군산시 문화관광'·'군산시 보도자료' | 출처 이름 | `site.source.name`·`locality` |
| `present.py` `CITY_PREFIX`·`ACCESS_SOURCES`·`FEE_SOURCE` | 주차장 조례·정류장·시간표 출처 이름 | 지역 출처 이름 또는 비움 |
| `present.py` 행사 장소 정규식 | `전북특별자치도?\s+(군산시\s+)?` | `region_admin`·`locality` |
| `present.py` `MOVE_GUIDES`·`ANSWER_COPY`·`HOME_ANSWERS`·`FOCUS_DISHES`·`HOME_ANSWER_DEFAULT`·`SEARCH_EXAMPLE`·`ANSWER_SHORT`·`HUB_SHORT`·`ACCENT_TONES`·`HUB_LEAD`·`PURPOSE_ORDER` | guide-01~15 문구, 짬뽕 | 가이드 `answer` 필드로 옮기거나 비움 |
| `present.py` `HOME_OLDTOWN`·`HOME_ISLANDS`·`TEASER_COURSE`·`VIDEO_ROW_TOPICS`·`home_story()`, H1·1899·1908 문장, '고군산' 집계 | 군산 홈 이야기 | 새 이야기 또는 비움 |
| `present.py` `PLAN_CHOICES["hubs"]` | 군산역·시외·고속·공항 | 11단계 3번 |
| `media.py` `HERO_SLIDES`·`HOME_COVER`·`STORY_PHOTOS`·`GALLERY` | 군산 장소 이름 | 지역 KOGL-1 사진 장소 |
| `build.py` `LISTS`·`ATTRACTION_GROUPS`·`MOUNTAIN`·`HERO_PICKS`·`PURPOSES`·`VISUALS` | 짬뽕·꽃게장·금강·테마 slug | 지역 값 |
| `build.py` `VIDEO_TOPICS`·`VIDEO_TOPIC_ART` | 영상 주제 | 지역 주제 또는 비움 |
| `build.py` 코스 목록 문장 | '군산시 문화관광이 안내하는…' | 지역 출처 |
| `schema.py` `INDEX_TAUT` (+`quality_report.TAUT`, `round3_content.TAUT`) | '군산시' | `locality` |
| `schema.py` `DESIGNATION_*` | 군산맛집·짬뽕 특화거리 | 지역 지정 목록 조사 뒤 |
| `schema.py` `REGION_BOUNDS`·`CITY_DEFAULT_POINT` | 군산 좌표 상자 | 1-2의 4번 |
| `jsonld.py`·`en_site.py`의 `#gunsan` | `@id` | `#city`(네 곳을 함께) |
| `en_site.py` `EN_SITE_NAME`, guide-13/14/15 허브, `SHORT_PROVIDER`, `"Gunsan"` 기본값 | 군산 | 지역 설정 |
| `en_source.py` `_ADDR`·`_LOT`·`_TAIL` | 전북·군산 주소 | 1-2의 6번 |
| `textutil.py` `PROVINCE`·`_PROVINCE_PREFIX`, `relations.py` | 전북 | 1-2의 7번 |
| `locales.py` `LOCALES`(site_name·city·home_h1), `COURSE_WORDS` `src_stops`·`src_tt`, `BOOK_WORDS.svc`(citytour·camp·heli) | 9개 언어 군산 값 | 지역 설정 |
| `intl_text.py` | 'Gunsan City…', 'Jeonbuk State' 약 10줄 | 영어 원문을 고친 뒤 8개 언어 `chrome.*`를 다시 번역 |
| `tickets.py` `RESIDENT`, `fee_table.py` `NOT_VISITOR` | '군산시민' | `resident_label` |
| `art.py` `EVENT_KINDS` | 선유도·어청도·짬뽕·시간여행 | 지역 행사 낱말 |
| `enrich.py` | `tourapi.region_keyword` | site.json 값(옛 방식이라 쓰지 않음) |
| `icons.py` `REGISTRY` | `data/gunsan/icons.json` | 1-2의 3번 |
| `validate.py` `transit_problems` | guide-31 | 1-2의 9번 |

**B-2. chatbot·api**
- `api/chat.js`, `api/plan.js`에는 군산 값이 없다.
- 군산 값이 있는 곳
  - `server.js`: `PRODUCTION_ALIASES`, `PREVIOUS_SITES`, `SITE_URL` 정규식
  - `knowledge.js`: `SITE`, '군산시민 아님'
  - `prompt.js`
    - `RULES`: 이름·URL·예시 경로 `/places/월명공원/`·군산시민·'군산맛집 2026'·군산항 예시
    - 9개 언어 이어쓰기 지시, 도구 설명 예시, 번역 예시
  - `plan_prompt.js`: `PLAN_RULES`, 통합권, 제목 예시, `HUBS`
  - `planner.js`·`plan_build.js`: 코스 제목 '군산 …박 …일'
  - `plan_state.js`: 금지어의 '군산', `ISLANDS ['고군산','섬']`
  - `plan_share.js`: `SHARE_SALT 'gunsan-plan-share-v1'`
  - `plan_geo.js`: `STAY_NEAR`·`NEAR`·`CAP`·`FLOORS`(군산 장소 통계로 정한 값)

**B-3. templates**
- `assets/chat.js`: `SITE`, 9개 언어 제목·칩('선유도 가는 법'·'군산 짬뽕')·placeholder, 거점 정규식
- `assets/plan.js`: `SITE`, '군산각(' 문구, 내려받기 파일 이름 '군산각-코스-'
- `home.html.j2`: 고군산 갤러리('고군산군도', '구 군산세관 본관에서 선유도까지', `?region=고군산`)
- 검색창 예시: `_p2.html.j2`, `_ui.html.j2`('군산 풍경 사진' 등), `search.html.j2`, `404.html.j2`
- `plan.html.j2`: '짬뽕은 꼭'
- `place.html.j2`: '군산시 공식 코스'
- `about.html.j2`: co-note '군산시나 공공기관'
  - AI 일러스트 안내 문장이 사진 있는 장소가 0곳이면 나오지 않는다. 확인한다.
- `en/guide.html.j2`: guide-12/13/30 그림
- `list.html.j2`: 테마 slug(`islands-sea`·`modern-history` 등)와 아이콘 짝
- `_ui.html.j2`·`en/_en.html.j2`: 버스 99번
- 바꾸지 않아도 되는 곳: `map.js`(지역값 없음), CSS 색 이름 주석, 파일 맨 위 '군산 여행 —' 주석

**B-4. tools**
- `tourapi_bulk.py`: `region_full` 기본값, `next()`, `photo_title()`
- `tourapi_details.py`: `display_name()`
- `en_content.py`: `DATA`, 시·군 찾기 두 곳, 주소 꼬리 규칙, `check`가 군산 `names.json`을 읽음
- `round3_content.py`: `DATA` 고정, `TAUT`
- `quality_report.py`: `TAUT`
- `kakao_places.py`: 지역 필터
- `refresh.py`: `round3_official` 단계
- `abroad_candidates.py`: `DEFAULT_KEYWORDS`
- `brand_kit.py`: 이름·파일 이름·색·도형
- `make_review_sheet.py`: `--base` 기본값이 군산 주소
- `perf_check.py`: 기본 페이지가 군산 장소
- `--data` 기본값이 `data/gunsan`인 도구: build_public, build_review, quality_report, approve_publication, apply_review, make_review_sheet, image_sizes, kogl1_media, indexnow, launch_check, link_check, refresh, art_media, tourapi_bulk, abroad_check, abroad_quotes, kakao_places, en_content

**B-5. 설정·배포**
- `vercel.json` `redirects`(군산 주소 이전 2 + guide-NN 21)
- `package.json`의 `name`·`description`(겉보기 문제)

**B-6. data/<slug>/site.json 키**: 2단계 1번

**B-7. 브랜드**: 7단계

**B-8. `data/gunsan`을 직접 읽는 테스트**
- test_aeo_geo, test_art, test_art_slots, test_ask, test_ask_browser, test_booking, test_chat_index, test_chat_node
- test_dead_links, test_desc80, test_designations, test_domain_move, test_en_site, test_guide_reading, test_icons
- test_intl_content, test_intl_site, test_kakao_map, test_media_behaviour, test_nearby_chapter, test_notices
- test_place_relations, test_plan_page, test_present, test_refresh, test_uiux
- 그 밖에 `tests/js/search.test.js`, `tests/fixtures/plan_*.json`(군산 장소)
- 상수에 묶인 테스트: `tests/js/chat.test.js`, `tests/js/plan_share.test.js`
- 1-4 방식으로 옮긴다.

**B-9. 군산 가이드 36편 분류**(새 지역 주제 고르기용)
- **공통 패턴(지역 데이터로 다시 쓴다)**
  - 01 차 없는 당일, 02 아이와, 03 비 오는 날, 04 독채·펜션형 숙소, 07 1박 2일
  - 10 무료 관광지, 11 야경, 12 가는 법·교통, 13 맛집 메뉴별(허브), 14 숙소(허브), 15 가볼만한 곳 권역별(허브)
  - 16 카페, 21 고기집, 22 아침 식사, 23 시장, 24 월요일 맛집, 25 늦게까지 하는 식당
  - 26 농촌·공예 체험, 27 산책로, 28 단체 식당, 29 휠체어(무장애 정보), 30 안내소·해설사·스탬프
  - 31 시내버스(교통 원자료가 있을 때), 33 시외·고속·공항, 34 공영주차장(주차 표준데이터가 있을 때), 41 모범음식점·착한가격업소
- **패턴만 같음(기준을 바꾼다)**: 05 촬영지, 06 대표 음식, 09 도보 동선, 17·19 대표 관광지 근처 맛집, 18 섬·항구 맛집, 20 횟집(해안 지역), 40 시 지정 맛집(지정 제도가 있을 때)
- **군산 전용(쓰지 않음)**: 08 고군산군도, 32 섬 여객선

## 부록 C. 명령 모음
`<slug>`를 바꿔 쓴다. 모든 명령은 저장소 루트에서 실행한다.
```bash
# 설치
python -m pip install -r requirements.txt
python -m pip install "pillow>=11.3" fonttools playwright
npm ci

# TourAPI
python tools/tourapi_doctor.py --keyword "<대표 장소>"
python tools/tourapi_bulk.py --data data/<slug> --add-new --events --max-calls 900
python tools/tourapi_bulk.py --data data/<slug> --details --gallery --max-calls 900
python tools/tourapi_bulk.py --data data/<slug> --barrier-free --max-calls 600      # 공개 승인 뒤
python tools/tourapi_bulk.py --data data/<slug> --nearby-only
python tools/image_sizes.py --data data/<slug>

# 빌드·검증
python -m pipeline.build    --data data/<slug> --out dist-preview --mode preview
python -m pipeline.validate --data data/<slug> --out dist-preview --mode preview --report reports/qa_preview.md
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/build_public.py --data data/<slug> --out public          # production 빌드 + 검증 + IndexNow 키 파일

# 글
python tools/round3_content.py prepare|check|merge|catalog|check-guide …   # 5·6단계
python tools/en_content.py names|prepare|check|merge --lang <c> …           # 10단계
python tools/quality_report.py --data data/<slug> --out public --md docs/handover/<slug>_quality.md

# 검수·공개
python tools/build_review.py --data data/<slug> --out dist-review --report-dir reports
python tools/make_review_sheet.py --data data/<slug> --out docs/handover/review_<slug>.csv --base <site_url>
python tools/apply_review.py --sheet docs/handover/review_<slug>.csv --data data/<slug> [--apply]
python tools/approve_publication.py --data data/<slug> --date YYYY-MM-DD [--hold <id>] [--apply]   # 운영자 지시로만 --apply

# 그림
python tools/art_media.py --data data/<slug> [--dry-run]
python tools/kogl1_media.py --data data/<slug>

# 테스트·성능
python -m pytest -rs
node --test tests/js/*.test.js
python tools/perf_check.py --out public --pages / /places/<slug>/

# 공개 뒤
bash tools/check_access.sh https://<주소> --mode production --path /places/<slug>/ --path /en/
python tools/indexnow.py --out public --data data/<slug> [--since YYYY-MM-DD] [--send]
python tools/refresh.py --data data/<slug> --dry-run
python tools/link_check.py --data data/<slug> --guides [--apply]
python tools/launch_check.py --data data/<slug>
```

**`.gitignore`가 빠졌을 때 최소 내용**
```
.env
reports/
__pycache__/
*.pyc
.pytest_cache/
dist/
dist-*/
data/cache/
data/*/places.json.bak
incoming/ai-images/*
!incoming/ai-images/README.md
incoming/mascot/*
!incoming/mascot/README.md
incoming/icons/*
!incoming/icons/README.md
node_modules/
work/
```

**`site.json` 키 요약**

| 키 | 구분 | 비고 |
|---|---|---|
| `site_url` | 입력·결정 | https, 'example' 금지 |
| `site_name`, `brand` | 입력 | '○○각' |
| `brand_symbol` | 입력 | 7단계 SVG 파일 이름 |
| `region`, `locality`, `region_admin`, `region_full` | 입력 | `region_full` 필수 |
| `description`, `disclaimer`, `affiliation` | 입력 | 우리 문장 |
| `source{name,url}`, `official_links` | 입력 | 지역 공식 관광 사이트 |
| `operator`, `editor` | 결정(재사용) | `operator.contact`는 production 필수 |
| `ga4_id`, `gtm_id`, `launch_exceptions` | 결정 | 둘 다 없으면 `launch_exceptions.ga4_id` 사유 |
| `search_verification{google,bing,naver}` | 결정 | 도메인 확정 뒤 |
| `indexnow_key` | 새로 만듦 | 8~128자 영문·숫자·`-` |
| `kakao_js_key` | 결정 | 콘솔에 도메인 등록 |
| `crawler_policy`, `publish_rules` | 결정 | — |
| `tourapi{…,region_keyword}` | 재사용 + 입력 | `region_keyword`만 지역 값 |
| `emergency`, `tmap_scheme`, `site_faq` | 재사용 | — |
| `center` | 쓰지 않음 | null |

## 부록 D. 이미지 요청 문서 틀
`docs/handover/<slug>_image_requests.md`를 아래 순서로 쓴다. 사람은 그림 한 장마다 **공통 스타일 → 구도 → 프롬프트**를 한 메시지에 붙여 이미지 도구에 넣는다.

**D-1. 공통 스타일(지역 모티프 줄만 바꾼다)**
```
최고 품질로 그린다: 고해상도, 선명하고 깨끗한 윤곽, 정교한 종이 질감과 고르게 칠한 색면, 인쇄용 여행 잡지 표지 수준의 완성도.
흐릿함·뭉개짐·노이즈·찌그러진 건물 선·어색한 사람 모양·반쯤 잘린 사물이 없게 한다.
고급 여행 잡지 표지 같은 일러스트. 과슈와 리소그래프 질감, 고운 종이 결, 깔끔한 면 분할, 따뜻한 자연광, 넓은 여백.
사진처럼 보이지 않게 그린다(포토리얼·3D 렌더·사진 합성 금지).
색: 밝은 미색 바탕 #F5F5F7, 포인트 라임 #E4FF54 · 라벤더 #CBBCFF · 하늘색 #8EE3EF, 짙은 먹색 #1D1D1F, 여기에 계절의 자연색.
무대는 한국의 <지역>이고, 분위기는 <지역 모티프 5~8개: 공식 자료로 확인한 대표 경관을 일반화한 낱말>이다.
실제 장소를 옮겨 그린 그림이 아니라, 이 모티프 가운데 요청한 것만 단순하게 다시 짠 상상 풍경이다.
요청하지 않은 건물·다리·배·탈것은 더하지 않는다. 특정 건물·다리·섬을 실제 모습과 똑같이 그리지 않는다.
종이 등불·초롱, 노렌 천, 도리이, 유카타·핫피, 일본풍 노점 지붕처럼 일본 축제나 거리를 떠올리게 하는 소품은 넣지 않는다.
간판·현판·현수막·천막·버스·번호판·깃발·표지판·메뉴판·책·신문·지도·화면·컵·포장·옷에는 글자·숫자·번호·로고를 넣지 않는다.
글자가 들어갈 자리는 무늬 없는 단색 면으로 둔다.
사람은 작게, 뒷모습이나 옆모습으로 그리고, 실존 인물이나 알려진 캐릭터를 닮게 그리지 않는다.
로고·워터마크·서명 없음. 글자는 프롬프트가 「 」로 요청한 문장만, 한 글자도 바꾸지 않고 깔끔한 고딕체로 쓴다.
요청이 없으면 그림 어디에도 글자·숫자·기호를 넣지 않는다.
```

**D-2. 구도 6가지**(그룹마다 하나를 붙인다)
1. **카드형**(정사각 1024×1024)
   - 위 1/3은 거의 단색으로 비운다.
   - 모든 물체는 높이 40%보다 아래에 둔다. 주제는 아래 2/3 가운데에 크게 둔다.
2. **작은 그림형**(정사각 1024×1024, 약 200px로 씀)
   - 주제 하나를 굵고 단순한 윤곽으로 그린다. 배경은 거의 단색이다.
   - 가장자리 10%는 비운다.
3. **띠형**(가로 1536×1024, 1536×640으로 잘려 쓰임)
   - 주제는 높이 35~65% 띠 안에 둔다.
   - 위아래 35%는 잘려도 되는 하늘·물·땅으로 채운다. 오른쪽 끝 10%는 비운다.
4. **히어로형**(가로 1536×1024)
   - 왼쪽 45%는 무늬 없는 단색 면이다.
   - 그림은 오른쪽 55%와 아래 낮은 띠에만 둔다.
5. **캠페인 글자형**(가로 1536×1024)
   - 글자는 「 」 문장 하나뿐이다. 굵은 고딕체로 쓴다.
   - 가운데 70% 안에 두고, 긴 문장은 낱말 사이에서 두 줄로 나눈다.
6. **공유 이미지형**(가로 1536×1024 → 1200×630, 위 8%·아래 13%가 잘림)
   - 권장: 글자 없는 배경만 만든다. 이름과 심볼은 AI 도구가 합성한다(8단계 7번).

**D-3. 표의 열**: `ID | slot | 비율·크기 | 그림 속 글자(「」, 데이터 출처) | 프롬프트 | alt 초안(ko)`
- 글자는 가이드 배너·언어별 공유 이미지에만 넣는다. 데이터에 있는 문장 그대로 쓴다.
- 데이터에 없는 숫자나 홍보어('최고', '필수')는 쓰지 않는다.

**D-4. ID 규칙**: ID 앞부분이 `tools/art_media.py`의 자르기를 정한다.

| ID 앞부분 | slot | 처리 |
|---|---|---|
| `og-<lang>` | `og.default`(ko), `og.default-en`, `og.<lang>`, `og.plan`, `og.abroad` | 1200×630 JPG |
| `head-<목록>` | `list.head.<places·food·stays·courses·guides·events·videos·abroad·map>` | 1536:640 띠 |
| `theme-<slug>` | `theme.head.<slug>` | 띠 |
| `course-<id>` | `course.banner.<코스 id>` | 띠 |
| `area-<key>` | `area.<권역 key>` | 띠 |
| `vtopic-<topic>` | `videos.head.<topic>` | 띠 |
| `camp-<주제>` / `camp-<주제>-notext` | `guide.banner.<id>`(ko 글자) / `intl.guide.banner.<id>`(글자 없음) | 가로 |
| `about-head` | `about.head` | 가로 |
| `plan-hero`(file `head-plan.png`) | `plan.head` | 가로(띠로 잘리지 않게 `head-`를 쓰지 않음) |
| `month-MM`, `evkind-<k>`, `card-<k>`, `abroad-<g>` | `events.month.MM`, `events.kind.<k>`, `home.card.<k>`, `abroad.group.<g>` | 정사각 |

- 띠가 아닌 그림에 `head-`를 붙이면 1536:640으로 잘린다.
- 여러 og ID가 원본 하나를 같은 `file`로 함께 써도 된다(언어별 `langs`·alt만 다르게).

## 부록 E. 새 저장소의 `AGENTS.md`·`CLAUDE.md` 틀
두 파일의 내용을 같게 둔다. 도구마다 읽는 파일이 달라서다. 또는 `CLAUDE.md`에 "AGENTS.md를 따른다" 한 줄만 둔다.
```markdown
# AGENTS.md — ○○각 (지역 여행 사이트)

> 이 파일이 최우선 지시다. 기준 엔진: 군산각 6a26206c4 · 마스터 프롬프트 v1.0 (docs/master/region_master_prompt.md)
> 작업 기록: docs/handover/<slug>_log.md · 보고서: docs/handover/<slug>_report.md

## 1. 무엇을 만드는가
여행자가 실제로 쓰는 ○○ 여행 사이트이자, 공개 후 AI 답변엔진 인용·유입을 측정할 실험 사이트다.
(마스터 프롬프트 2장의 성공 기준 5개를 그대로 옮긴다)

## 2. 지켜야 할 규칙
(마스터 프롬프트 3장 1~17번을 지역 이름으로 바꿔 옮긴다)

## 3. 명령어
(부록 C를 <slug>로 채워 옮긴다)
- `public/`은 `python tools/build_public.py --data data/<slug>`로만 갱신한다. 직접 고치지 않는다.
- main에 push하면 곧 배포된다.

## 4. 코드·데이터 지도
| 경로 | 역할 |
|---|---|
| data/<slug>/ | 사이트 데이터 |
| data/<slug>/region.json | 지역 설정(1단계) |
| pipeline/ | 빌드·검증·구조화 데이터 |
| chatbot/, api/ | 챗봇·코스 만들기(Vercel 함수) |
| templates/ | 화면 |
| tools/ | 수집·작성·검수·공개 도구 |

## 5. 사람이 정할 것
(마스터 프롬프트 5장에서 아직 남은 것과 이미 정한 것을 날짜와 함께 적는다)
```
