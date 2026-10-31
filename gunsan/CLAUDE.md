# CLAUDE.md — 군산 여행 실증 사이트 (WebforAI)

> 이 파일이 최우선 지시다. `AGENTS.md`·`CODEX_TASKS.md`는 1차 기록이다. 충돌하면 이 파일을 따른다.
> 현재 상태와 3차 과제는 `docs/handover/2026-10-08_round2_review.md`에 있다.
> 2차 결과: `docs/handover/round2_report.md` · 배경: `docs/00_summary.md` · 데이터 표준: `docs/02_page_standard.md`

## 1. 무엇을 만드는가
여행자가 실제로 쓰는 군산 여행 사이트이자, 공개 후 AI 답변엔진 인용·유입을 측정할 실험 사이트다.

**3차 성공 기준은 세 가지다.**
1. 공개 대상 페이지가 '방문 판단 정보'로 채워져 있다.
2. 얇은 페이지는 색인되지 않는다.
3. 사람이 검수와 공개 설정만 하면 바로 실험을 시작할 수 있다.

안전장치·문서·테스트·모션의 양은 성공 기준이 아니다.

## 2. 3차 목표 (우선순위 순)
1. **정보 깊이**
   - TourAPI detailCommon2·detailIntro2로 전화·이용시간·쉬는 날·요금·주차·체크인을 채운다.
   - TourAPI에만 있는 장소를 추가한다.
   - 출처는 필드별로 표시하고, 이용시간 충돌 3곳을 해소한다.
2. **얇은 페이지 정리**: 상투구 요약을 다시 쓰고, 장소가 아닌 항목을 정리하고, 색인 기준을 도입한다.
3. **정보 우선 화면**: 장소 첫 화면에 핵심 정보 줄을 두고, 길찾기를 단순화하고, 사진 없는 카드를 줄이고, 검색을 넣는다. 지금 톤은 유지한다.
4. **성능**: 모션은 유지하되 첫 화면을 숨기지 않는다. 글꼴 전송량을 줄인다. 목표는 모바일 LCP 2.5초 이하다.
5. **공개 준비**: 검수 시트·반영 스크립트, 공개 체크, 행사 갱신 명령을 만든다. 공개 전환 자체는 사람이 한다.

## 3. 지켜야 할 규칙
1. **사실은 출처 데이터에서만** 가져온다(TourAPI·군산시 문화관광·해당 시설 공식 홈페이지). 없는 값은 블록마다 "확인 필요: 요금·주차"처럼 한 번만 쓴다. 추정이나 일반 지식으로 채우지 않는다.
2. **필드별 출처**: 한 장소의 사실이 여러 출처에서 오면 필드마다 출처와 확인일을 남기고 화면에도 표시한다.
   - 두 출처 값이 다르면 둘 다 보여 주고 "방문 전 전화 확인"을 한 줄 붙인다.
   - 한쪽을 임의로 고르지 않는다.
   - (운영자 결정 2026-10-31, '출처마다 다름 표시는 좀 안 보이면 좋겠는데' — 부평시장각 2026-10-30과 같은 방식) `site.json`의 `fact_conflicts: "primary"`: 화면·외국어판·챗봇·구조화 데이터에는 대표값 하나만 그 출처와 함께 보인다. 대표값은 자료의 본값(`facts`, 대개 군산시 문화관광·시설 쪽, TourAPI보다 먼저)이고, 값이 다른 다른 출처의 값은 데이터(`fact_alternatives`, 외국어 파일의 alternatives)에만 남긴다(`pipeline.textutil.keep_primary_facts`, `en_site.Site`). 키를 지우면 위 규칙(둘 다)으로 돌아간다.
3. **군산시 원문·사진은 게재하지 않는다**(공공누리 미표시·제4유형, "All rights reserved").
   - 원문은 링크로만 건다.
   - 설명은 우리 문장으로 쓴다(원문과 15자 이상 연속 일치 금지).
   - 표의 값(시간·요금·메뉴)은 값 그대로 써도 된다.
4. **TourAPI 이미지**
   - `cpyrhtDivCd`가 Type1·Type3인 것만 쓰고 "출처: 한국관광공사"를 표기한다.
   - Type3은 자르기·확대·보정을 하지 않는다.
   - overview 문장은 게재하지 않고 사실 확인용으로만 쓴다(사람 결정 전).
5. **요약 문장**: 답부터 쓰는 평서문으로 쓴다.
   - 첫 문장을 "○○은 군산시 ○○에 있는 ○○입니다"로만 끝내지 않는다. 그 장소만의 사실(대표 메뉴·좌석·객실 수·운영 특징·볼거리)을 하나 이상 넣는다.
   - 쓸 사실이 없으면 짧게 두고 색인 대상에서 뺀다(8항).
   - "원문은 ~" 같은 출처 해설체는 쓰지 않는다.
6. **FAQ**
   - 질문은 존댓말 "~나요?/~인가요?"로 통일한다.
   - 같은 질문을 여러 장소 페이지에 반복하지 않는다. 지역 단위 질문은 가이드로 옮긴다.
   - 데이터로 답할 수 없는 질문은 만들지 않는다.
7. **공개는 사람이 정한다**
   - `status=published`, `reviewed_at`, `site.json`의 `site_url`·`ga4_id`·`brand`·`operator`·`publish_rules`·`crawler_policy`, noindex·robots 해제는 바꾸지 않는다.
   - 사람이 표시한 검수 시트를 그대로 반영하는 스크립트는 만들어도 된다.
8. **색인 기준(production)**: 장소 페이지는 세 조건을 모두 갖췄을 때만 색인한다.
   - (a) 유형별 필수 정보가 2개 이상이다(`tools/quality_report.py`의 `KIND_GROUPS`).
   - (b) 요약이 5항을 지킨다.
   - (c) `reviewed_at`이 있다.
   - 미달 페이지는 noindex로 내보내고 sitemap·llms.txt에서 뺀다. 목록·지도에는 남긴다.
9. **비밀값**
   - `TOURAPI_KEY`는 환경 변수나 `.env`에 둔다(커밋 금지).
   - `.env`를 열어 보거나 출력하지 않는다.
   - 로그에서는 키 문자열만 가리고, 공급자 오류 메시지는 그대로 보인다.
10. **제3자 콘텐츠 금지**: 네이버 플레이스·블로그·리뷰·평점은 복제하지 않는다. 회원가입·예약·결제·챗봇은 넣지 않는다. 특정 업체를 근거 없이 추천하지 않는다.
    - (운영자 결정 2026-10-13) 사이트 안내 챗봇을 넣는다: Claude Haiku 5.5(`claude-haiku-5-5`), 키는 Vercel 환경 변수 `ANTHROPIC_API_KEY`(커밋·출력 금지). 이 사이트 데이터로만 답하고(3절 1·2항 그대로 — 없는 값은 '사이트에 없음'과 공식 확인처, 출처가 다르면 둘 다), 답마다 해당 페이지 링크를 단다. 질문한 언어로 답한다. 대화는 저장하지 않는다. 회원가입·예약·결제는 여전히 넣지 않는다.
    - (운영자 결정 2026-10-13) 해외에서 본 군산(/abroad/): 외신·해외 매체 기사와 SNS 게시물은 원문·사진을 옮기지 않고 **우리가 쓴 한 줄 소개 + 원문 링크**로만 싣는다. 기사 미리보기 사진은 매체가 링크 미리보기용으로 공개한 대표 이미지(og:image)를 우리 서버에 복사하지 않고 매체 주소에서 불러오며, 군산을 찍은 사진만 쓴다. SNS 게시물은 화면에 가까워지면 해당 서비스의 공식 임베드로 불러온다(`data/<region>/abroad.json`, `tools/abroad_check.py`, `tools/abroad_candidates.py`). (운영자 확인 2026-10-13, 2026-10-14에 아래로 바뀜) /abroad/ 하이라이트도 같은 원칙 — 우리말 한 줄 요약 + 원문 링크, SNS 원글은 공식 임베드로만 보이고 원문 문장을 따옴표로 옮기지 않는다(data/<region>/abroad_highlights.json).
    - (운영자 결정 2026-10-14) /abroad/ 하이라이트와 기사 카드에는 원문의 짧은 대목을 **번역하지 않고 원문 언어 그대로 인용**한다: 연속한 1~2문장(300자·45단어 이하)을 글자 그대로 `<blockquote lang cite>`에 싣고 매체·필자(SNS는 서비스·계정)·언어·날짜와 원문 링크를 함께 단다. 우리말 요약(praise_ko)은 쓰지 않고, 기사 카드의 우리 한 줄 소개(note)는 그대로 둔다. 인용문은 원문 HTML(SNS는 공식 oEmbed가 돌려준 게시물 글 — 지금은 X만)에서 그대로 옮기고 `tools/abroad_quotes.py`로 원문에 글자 그대로 있는지 확인한다(요약·재작성 도구로 읽은 글은 쓰지 않는다). 군산이나 군산의 장소를 좋게 본 대목만 고르고, 섞인 글은 대표 문장을 고르며 문장을 잘라 뜻을 바꾸지 않는다. 기사 페이지 화면 캡처는 싣지 않는다 — 그림은 매체의 og:image와 서비스 공식 임베드(그리고 3절 4항의 장소 사진)뿐이다.
    - (운영자 결정 2026-10-30) 운영자 블로그 **군산각 블로그**(blog.naver.com/gunsangak)를 /blog/(블로그 카테고리별 전체 목록)와 장소·가이드·칼럼·코스 페이지의 '군산각 블로그' 묶음(글 3개까지)으로 싣는다. 글은 **제목·카테고리·날짜·원문 링크**로 보여 주고 본문·블로그 사진은 옮기지 않는다 — 블로그 사진에는 출처 유형을 확인할 수 없는 한국관광공사·군산시 사진이 섞여 있다(3절 3·4항). (같은 날 운영자 결정) /blog/는 카드형이고 **카드마다 사진**을 단다: 글에 나온 장소 → 한 번 나온 장소 → 그 가까운 장소 → 글이 링크한 페이지의 장소 → 같은 카테고리 글의 장소 순으로 고른 TourAPI 제1·3유형 사진(제3유형은 자르지 않음). 카드마다 출처를 달지 않고 페이지에 '사진 출처: 한국관광공사 · 공공누리' 한 줄만 둔다(공공누리 출처 표시 조건). (같은 날 운영자 결정) 홈에 '군산각 블로그' 카드 6장(카테고리마다 최신 글 하나씩 먼저, 사진이 겹치지 않게), 상단 주 메뉴의 '칼럼' 다음에 '블로그' 탭. 블로그의 가격·시간은 장소 정보로 쓰지 않는다(3절 1항). 장소 짝은 글 제목에 이름이 있거나 본문에 2번 이상 나온 장소, 가이드·칼럼·코스 짝은 글이 그 페이지로 건 링크다. 고객사 숙소가 나오는 글도 관계 표시 없이 싣는다(운영자 결정). 갱신은 `python tools/blog_sync.py --apply`(`data/<region>/blog.json`, 숨길 글은 `exclude`), 검증은 validate의 blog_problems.

## 4. 하지 말 것
- 방어 장치(누적 장부·잠금·메시지 은폐)를 새로 만들지 않는다. 실행당 상한과 캐시, 키 마스킹이면 충분하다.
- 군산시 수집 도구(`tools/collect_*`, `gunsan_*`, `archive_*`, `import_gunsan_*`)는 동결한다. 추가 수집은 9절의 사람 결정이다.
- 검증 규칙을 완화해서 통과시키지 않는다. 테스트·문서 분량을 목표로 삼지 않는다.
- 빈 데이터를 장식으로 덮지 않는다(가짜 사진, AI 이미지, 가짜 지도, 큰 빈 표지).
  - (운영자 결정 2026-10-13 밤) 그림에 'AI 생성 이미지' 표기를 하지 않는다. AI로 만든 풍경·일러스트는 배경·캠페인 그림·장식으로 써도 되지만 실제 사진처럼 내보이지 않는다: alt는 '일러스트'로 시작하고, 소개 페이지(/about/, /en/about/)에 '이 사이트의 일러스트는 생성형 AI로 그렸다'고 한 번 적으며, 특정 장소의 사진 자리(장소 페이지 사진·썸네일)와 구조화 데이터(ImageObject·og:image의 장소 사진)에는 쓰지 않는다. 장소 사진은 3절 4항(TourAPI Type1·3) 그대로다. 없앤 표기는 어느 페이지에도 다시 나오지 않게 validate가 검사한다(pipeline/art.py).
- 첫 화면 내용을 스크립트로 숨겼다가 보여 주지 않는다. 연출은 첫 화면 아래 요소에만 쓴다.
- '멈추고 보고'를 남발하지 않는다. 9절 항목만 보고서로 넘기고, 나머지는 판단해서 진행한 뒤 `docs/handover/round3_log.md`에 한 줄 남긴다.

## 5. 명령어
```bash
python -m pip install -r requirements.txt
python -m pytest
python tools/tourapi_doctor.py                                   # TourAPI 연결 진단 — 가장 먼저
python tools/tourapi_bulk.py --data data/gunsan --max-calls 900  # 목록 매칭·좌표·사진(3차에서 상세 호출로 확장)
python -m pipeline.build --data data/gunsan --out dist-preview --mode preview
python -m pipeline.validate --data data/gunsan --out dist-preview --mode preview
python -m pipeline.build --data data/gunsan --out dist-prod --mode production && python -m pipeline.validate --data data/gunsan --out dist-prod --mode production
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/build_review.py --data data/gunsan --out public --report-dir reports   # public/ 갱신(선별 미리보기)
python tools/quality_report.py --data data/gunsan --out public --md docs/handover/quality_after.md
python tools/perf_check.py --out public                          # Playwright 필요
python tools/blog_sync.py --apply                               # 군산각 블로그 글 목록 갱신(--apply 없으면 미리보기)
```
- **2026-10-08 운영자 공개 전환**: `public/`은 이제 공개(production) 빌드다 — `python tools/build_public.py`(빌드·검증·IndexNow 키 파일)로만 갱신한다. 공개 주소 `https://gunsan-seven.vercel.app`, noindex 헤더 해제. 새로 들어온 레코드는 draft로 남고, 공개하려면 `python tools/approve_publication.py --date <날짜> --apply`(운영자 공개 승인, approved_at). 색인 기준은 그대로다(검수일 또는 운영자 공개 승인 + 필수 정보 2개 + 요약 규칙). GA4는 운영자 예외로 나중에(site.json launch_exceptions).
- `public/`은 Vercel이 그대로 배포하는 산출물이다. 직접 고치지 말고 빌드로만 갱신한다.
- `main`에 push하면 곧 배포된다(공개 사이트).

## 6. 코드·데이터 지도
| 경로 | 역할 | 3차 |
|---|---|---|
| `data/gunsan/*.json` | 사이트 데이터 | 보강·정리(필드별 출처 추가) |
| `pipeline/tourapi.py` | TourAPI 클라이언트(2차에서 단순화) | 상세 호출에 그대로 사용 |
| `tools/tourapi_bulk.py` | 목록 매칭·좌표·사진·주변 | detailCommon2·detailIntro2와 TourAPI 전용 장소 추가로 확장 |
| `pipeline/enrich.py` | 상세 보강(`INTRO_FIELDS` 매핑) | 필드별 출처로 수정 |
| `pipeline/build.py`·`validate.py`·`jsonld.py` | 빌드·검증·구조화 데이터 | 색인 기준, `alternateName`, 필드 출처 |
| `tools/build_review.py` | `public/` 선별 빌드 | 코스·가이드가 가리키는 장소는 선별에 포함 |
| `templates/` | 화면 | 정보 우선으로 수정(톤 유지) |
| `tools/quality_report.py` | 정보 품질 리포트 | 전/후 기준. 판정 기준을 바꾸면 보고서에 적는다 |
| `tools/perf_check.py` | 모바일 속도 점검 | 전/후 기준 |
| `tools/tourapi_doctor.py` | 키·네트워크 진단 | 그대로 |

## 7. 디자인 기준 — 정보 순서·성능·접근성 기준은 아래를 따른다
> **사용자 결정(2026-10-08, 3차 중)**: 톤 유지 대신 **전면 리디자인**으로 바꾼다. 최상급 에이전시·관광 사이트 레퍼런스를 조사해 이 사이트의 목적(방문 판단 정보·AI 인용·측정)에 맞게 새 시각 언어를 만든다. GSAP·Lenis 사용은 유지한다. 아래 정보 순서·길찾기·사진 없는 항목·검색·모션 원칙·성능 목표·접근성 기준과 3절 사진 규칙은 그대로 지킨다.
- **장소 첫 화면(390px)**
  - 순서: 이름 → 한 줄 답 → 핵심 정보 줄(운영시간·쉬는 날·요금·주차·전화 중 있는 값 + 확인일).
  - 사진은 모바일에서 화면 높이의 45% 이하로 줄이고, 썸네일 줄은 핵심 정보 아래로 내린다.
- **길찾기**: 앞줄에 3개(네이버 지도·카카오맵·길찾기)만 두고 나머지는 '다른 지도'로 접는다. 좌표·ID가 있는 정확 링크를 우선한다.
- **사진 없는 항목**: 큰 빈 표지 대신 작은 유형 아이콘 + 텍스트 행으로 보여 준다.
- **카드 칩**: 핵심 값을 말줄임으로 자르지 않는다. 두 줄을 허용하거나 값을 나눠 표시한다.
- **목록 지도**: 좌표가 있는 항목이 30% 미만이면 지도를 기본으로 접고 "좌표가 있는 n곳만 표시"라고 적는다.
- **고정 영역**: 스크롤하면 머리말을 줄인다(모바일 고정 영역 합 ≤ 화면의 15%). 상단 버튼은 맥락형으로 둔다(장소: 길찾기, 그 외: 코스 보기).
- **검색**: 이름·대표 메뉴·지역을 찾는다. 빌드 때 만든 정적 색인 + 작은 JS로 만들고, JS가 없으면 목록 링크로 대신한다.
- **지도 페이지**: 읍·면·동 묶음에 여행 권역 보기를 더한다. 권역을 나눈 기준은 페이지에 적는다.
- **모션**
  - 첫 화면 요소는 처음부터 보이게 한다(`motion-pending` 숨김 제거). 연출은 스크롤 아래 요소에만 쓴다.
  - reduced-motion이거나 JS가 없으면 최종 상태로 보여 준다.
  - Lenis는 데스크톱에만 쓰고, 앵커 이동과 키보드 스크롤이 정상인지 확인한다.
- **글꼴**: Regular·Bold는 unicode-range 분할(다이내믹 서브셋)로 자체 호스팅한다. ExtraLight는 숫자 전용 서브셋으로 만들고, SemiBold는 정리한다.
- **성능 목표**(`tools/perf_check.py`, 느린 4G·CPU 4배): 모션 켠 상태에서 LCP ≤ 2.5초, CLS ≤ 0.1, 첫 방문 글꼴 ≤ 300KB.
- **접근성**: 대비 4.5:1(주색 작은 글씨를 베이지 #e8dfd2 위에 쓰지 않기), 터치 영역 44px, 보이는 포커스, 이미지 alt.
- **검토**: 360·390·768·1440 캡처를 보고 고치기를 2회 이상 한다. 최종본은 `docs/reference/round3_*.png`로 저장한다.

## 8. 완료 기준(3차)
- **정보 품질**: `quality_report` 전/후 표(`docs/handover/quality_before.md`·`quality_after.md`)에서 화면에 나간 장소 기준으로 아래를 확인했다.
  - 전화·이용시간·주차·사진·좌표 채움률 상승
  - 색인 대상 상투구 요약 0
  - 장소가 아닌 항목 0, 주소 공백 0
  - 지난 행사 분리
- **TourAPI**: 사용 호출 수, 매칭률, 추가 장소 수, 이용시간 충돌 해소 결과를 보고했다.
- **색인 기준**: production 빌드에서 기준 미달 페이지는 noindex로 나가고 sitemap에서 빠진다. 테스트가 있다.
- **성능**: `perf_check` 전/후를 보고했고, 모션 켠 상태 LCP가 2.5초 이하다(홈·장소).
- **검수**: 검수 시트(`docs/handover/review_round3.csv`)와 반영 스크립트(`tools/apply_review.py`, 기본 dry-run)를 만들었다. 사람이 OK로 표시한 행만 reviewed가 된다.
- **질문표**: 질문표 ①에서 바뀐 질문만 다시 판정해 갱신했다.
- **검증·보고**: pytest와 샘플·미리보기 validate를 통과했다(규칙 완화 없음). 보고서는 `docs/handover/round3_report.md`(2쪽 이내)다.

## 9. 사람이 정할 것 — 결정하지 말고 선택지와 권장안으로 보고
- 공개 범위·시점, 도메인, GA4, 정정 요청 연락처(`operator.contact`), 검색엔진 인증 토큰(구글·빙·네이버)
- 브랜드: WebforAI / Web4AI / 여행자용 사이트 이름 + '운영: 에이아이오투오'
  - (운영자 결정 2026-10-16) 여행자용 사이트 이름은 **군산각**(외국어 8개 판은 모두 **Gunsangak**). 이전 이름 '군산 여행의 모든 것'은 쓰지 않는다. 로고는 운영자가 고른 등대·책갈피 시안을 도형으로 다시 그리고 글자는 Pretendard Bold로 짠 것이다(`templates/assets/brand/gunsangak-*.svg`, 머리말·바닥글 심볼은 `site.json`의 `brand_symbol`, 파비콘·앱 아이콘 icon-*.png). 링크 미리보기 그림(og-*)의 이름도 바꿨다. (같은 날 운영자 결정) 홈 첫 화면 큰 제목(h1)만은 설명으로 '군산 여행의 모든 것'을 쓴다 — 외국어 8개 판은 이름 변경 전 문구(`locales.Locale.home_h1`: All About Gunsan Travel·群山旅行のすべて 등). 머리말·바닥글·페이지 제목·구조화 데이터의 이름은 군산각/Gunsangak 그대로다.
- 검수: full 30곳·가이드·코스 확인(검수 시트)
- 추가 출처 수집 허용 범위(교통 안내 등 질문 N16·N17용 공식 페이지)
- TourAPI overview 게재 여부, 군산시 원문·사진 이용 협의(메일 초안 있음), 고객사 숙소 노출과 관계 표시
- 저장소 공개 여부와 원본 데이터(`data/raw`) 위치
- (운영자 결정 2026-10-14) 지도 제공자: **카카오맵**. 카카오 지도 JavaScript 키는 `site.json`의 `kakao_js_key`(공개 키 — 카카오 개발자 콘솔에 등록한 웹 도메인 `https://gunsan.webforai.kr`에서만 동작, 다른 주소에서는 HTTP 401로 지도 대신 '지도를 불러오지 못했습니다'). 빌드가 지도 상자마다 SDK 주소(`data-kakao-sdk`)를 적고, `templates/assets/map.js`가 상자가 화면 가까이 오거나 접힌 지도가 열릴 때 페이지 로드 뒤에만 받는다. 지도 없는 페이지는 아무것도 받지 않는다. 표기는 '지도: 카카오맵'(지도 안 로고는 카카오가 그린다). 장소 길찾기 링크(`pipeline/maplinks.py`)는 별도다.
