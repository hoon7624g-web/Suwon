# 시청 사진 이식 키트 (2026-11-14)

군산각이 2026-11-13에 한 '시청 사진' 작업을 지역 ○○각 20곳에 옮기는 안내서다. 이 브랜치(`port-kit-photos-20261114`)에는 안내서, 군산각 참고 코드, 공통 도구, 외국어 문구만 있다. 각 지역 세션은 자기 저장소의 작업 브랜치 `claude/city-photos-20261114`에서 일하고 **main 병합·배포는 하지 않는다**(조정 세션이 운영자 확인 뒤 한다).

## 0. 운영자 결정(그대로 인용해 CLAUDE.md 3절 사진 규칙 아래에 기록한다)

- 군산각 2026-11-13: '군산시 허락은 받았으니까 아래 2개 출처의 모든 사진들 추가해서 적절한 장소들에 모두 배치해 (사이즈 조절 등 편집 가능) 1. 군산시 문화관광 장소 페이지 사진 2. 군산시 온라인 홍보포털 사진'
- 같은 날: '홍보포털에 사진이 15만장 있으면 어차피 다 못 가져오는 거 아니야? 거기서만 추려와도 엄청나겠는데', '홈페이지 내 사진이 빈 곳들은 모두 채워주고', '외국어판에도 군산 사진 넣고'
- **2026-11-14 운영자 결정(표기)**: ''이용 허락'이라는 글자 표기하지 말고 모두 빼 출처만 표기해' — 시청 사진의 출처는 **시청 이름만**('대구광역시', 외국어판 'Daegu Metropolitan City' 등). 출처 줄·사진 칸·바닥글·소개 페이지·'사진 더 보기'·외국어판 어디에도 '이용 허락'·'허락을 받아'·'used with permission'·'利用許可' 같은 이용조건 말을 쓰지 않는다. 군산각 참고: 브랜치 `claude/funny-mendel-2dhpla`의 '이용 허락' 표기 빼기 커밋(present.LIC·credit_line, base·about·place 템플릿, en_site photos·credit_line·주변 사진 출처 photo_city, intl_text·strings의 foot_city_photos·about_city_photos), tests/test_city_photos.py test_no_permission_wording_is_shown.
- **2026-11-14(이 작업)**: '모두 허락 받았어. 전수조사하고, 최대한 사진들 많이 끌어와서 19개 사이트에 모두 넣자. 부평시장각도 포함해서. 모든 사이트가 아주 풍성해지도록'
  - 뜻: 각 사이트의 **지역 자치단체(시청·군청·구청, 제주는 도청·제주시·서귀포시)가 운영하는 누리집·관광 누리집·사진 포털의 사진**은 그 자치단체의 이용 허락으로 싣는다(편집 가능 — 크기 조절·자르기). 다른 기관(관광공사·광역 관광재단·언론사·블로그)의 사진은 이 허락에 들지 않는다 — 공공누리 제1·3유형만 기존 규칙대로.

## 1. 군산각에서 만든 것 = 지역에서 만들 것

참고: 군산각 저장소 `hoon7624g-web/gunsan` — main(커밋 39b538b44 사진, 788290bb1 외국어판, 3b9baa398 og 제외, f40bae277 제목 옆 공유)과 브랜치 `claude/funny-mendel-2dhpla`(시·군 공통으로 일반화한 엔진: CITY-PERMIT·site.json city_photos). 이 키트의 `tools/`·`reference/`는 그 일반화본이다. 군산 저장소를 읽어야 하면 add_repo(read)로 붙인다. 지역 엔진은 군산과 많이 갈라져 있으니 **패치를 적용하지 말고 동작을 옮긴다.** 코드에 지역 이름을 쓰지 않는다(지역 엔진의 test_no_city_literals) — 이름·서버·누리집은 `site.json`에.

1. **이용조건 코드 `CITY-PERMIT`** — `schema.LICENSE_LABELS`("시청 사진(출처표시·편집 가능)"), `EDITABLE_LICENSES = ("KOGL-1", "CITY-PERMIT")`, `site.json publish_rules.allowed_image_licenses`에 추가(운영자 결정이 있으므로 이 키를 바꿔도 된다 — 이 결정만).
2. **site.json `city_photos`**(군산 예: `reference/`가 아니라 군산각 data/gunsan/site.json):
   ```json
   "city_photos": {"_note": "운영자 결정 …", "credit": "대구광역시",
     "credit_intl": {"en": "Daegu Metropolitan City", "ja": "大邱広域市", "zh-hans": "大邱广域市", "zh-hant": "大邱廣域市",
                     "de": "Stadt Daegu", "fr": "Ville de Daegu", "es": "Ciudad Metropolitana de Daegu", "ru": "Город Тэгу"},
     "permit_at": "2026-11-14", "hosts": ["www.daegu.go.kr", "…"],
     "sources": [{"name": "대구광역시 관광", "url": "https://…"}, {"name": "대구시 포토뱅크", "url": "https://…"}]}
   ```
   외국어 이름은 그 사이트 strings.json에 이미 있는 그 도시 표기와 맞춘다(러시아어는 콘체비치 표기).
3. **사진 모델**(군산 `pipeline/present.py` photo/photos/credit_line/place_thumb/grid_thumb, `pipeline/media.py` attach/wanted):
   - CITY-PERMIT 사진은 `src: "city"`, type 1(편집 가능), credit = 사진에 저장된 시청 이름, **이용조건 표기 없음**(present.LIC의 CITY-PERMIT 표기 '').
   - 장소 사진 순서: **한국관광공사 사진 먼저(저장 순서 그대로 — 대표 사진·홈 사진 자리가 번호로 가리킨다)**, 그다음 시청 사진(저장 순서). TourAPI 사진이 없는 곳은 시청 사진이 대표.
   - 화면은 **시청 서버 원본을 절대 부르지 않는다**: `media.attach`가 사본(manifest) 없는 시청 사진을 빼고, 있는 것은 `ph.url`을 우리 가장 큰 WebP로 바꾼다(원래 주소는 `ph.orig`). `ph.full` = 포털 게시물 사진(`opens_page`)이면 그 게시물, 아니면 우리 큰 사본.
   - 사본(`tools/kogl1_media.py`): 대표 사진 k1(AVIF·WebP 480/940), 그 뒤 누리집 사진 view(WebP 480/960), 포털 사진·작은 사본 없는 제1유형 thumb(WebP 480). 공개 장소만(초안의 시청 사진은 사본 안 만듦).
   - 출처 줄 한 곳(`present.credit_line`): '한국관광공사 · 공공누리 제1유형·제3유형(변경금지) / 대구광역시' — 장소·목록·가이드·칼럼·코스·블로그·홈·숙박 예약 카드의 '사진 출처' 줄을 모두 이것으로. 지역 템플릿에 '출처: 한국관광공사'가 박힌 곳을 모두 찾는다.
   - 구조화 데이터 ImageObject: 시청 사진은 우리 사본의 절대 주소·creditText 시청 이름·라이선스 페이지 없음. **og:image(링크 미리보기)는 지금처럼 한국관광공사 제1유형만** — 시청 사진(type 1이지만)은 og 후보에서 뺀다(모든 og 선택 지점).
   - 소개 페이지·바닥글: '사진: <시청>', 사진 문단에 시청 사진 수·장소 수('허락' 말 없이 — '크기를 줄여 싣고 ‘출처: <시청>’를 적습니다').
4. **'사진 더 보기'**(군산 templates/place.html.j2, `css/88-photos-more.css` 그대로): 장소 사진이 7장을 넘으면 처음 7장(대표 + 사진 줄)만 보이고 나머지는 닫힌 `<details class="ph-more">` 안 지연 로딩 격자(작은 파일만 — 제공처 작은 사본 또는 우리 480 WebP, 누르면 `ph.full`), 제3유형은 칸 안에서도 contain. 열기 전 그림 요청 0을 Playwright로 확인.
5. **외국어판**: 같은 사진을 싣고 출처는 그 언어로(`Site.photos`가 사진별 credit·lic, `Site.credit_line`, `city_credit` = credit_intl[언어]). 새 문구는 `strings/city_photo_strings.json`(intl_text.EN 키 4개 + 7개 언어 strings.json 행 + `LIC.CITY-PERMIT` 8개 언어)을 그대로 넣는다 — 영어 원문 짝 검사(test_intl_content) 통과. 외국어 공통 출처 매크로는 카드 사진에 남은 한국어 출처를 찍지 않게 src로 다시 만든다.

## 2. 전수조사(먼저, 30분 안팎)

`docs/handover/city_photos_survey_20261114.md`에 표로 남기고 조정 세션에 보낸다(6절).

| 항목 | 찾을 것 |
|---|---|
| A. 데이터에 이미 있는 시청 사진 | places.json images 가운데 시청·관광 누리집 서버 사진(라이선스 UNKNOWN/NONE 등) — 서버별 장수, 공개·초안 장소 수 |
| B. 관광 누리집 장소 페이지 | 데이터에 없는 장소 사진(장소 페이지마다 여러 장인지), 장소 수 |
| C. 사진 포털·포토뱅크·홍보 사진 갤러리 | 주소, 방식(군산 uprbank와 같은 시스템인지 — `/main/m21/list.do`·`view.do?cntsId=`), 게시물·사진 규모, 분야, 공공누리 표시 |
| D. 공공누리(kogl.or.kr)의 그 기관 저작물 | 사진 수(부평시장각은 이미 인천광역시 제1유형 사진을 씀) |
| E. 관광공사 | 저장된 TourAPI 답(data/raw/<region>/*.tar.gz 등)의 미사용 상세 사진·관광사진 갤러리 |
| F. 사진 없는 공개 장소 | 수, 유형별 |

## 3. 수집과 배치(최대한 많이 — '아주 풍성하게')

순서와 상한(운영자 '최대한 많이'; 군산각보다 넉넉히):
1. **A**: `tools/city_photos.py permit --apply` → `fetch` (지역 data 경로 `--data data/<region>`).
2. **B**: 누리집 장소 페이지의 사진을 이 사이트 장소에 이름·주소로 맞춰 **모두** — 어댑터가 `data/<region>/portal.json`(형식은 tools/city_photos.py 머리말, `opens_page: false`)을 쓰고 `city_photos.py attach --apply`.
3. **C**: 포털이 uprbank 방식이면 `tools/city_portal.py`(설정 `data/<region>/city_portal.json`: base·fields·aliases·cap)를 그대로, 아니면 같은 흐름의 어댑터: 목록 → 제목이 장소를 가리키는 게시물만(행사·인물이 주인공인 게시물 — 개막식·방문·협약·회의·축제 등 — 은 EXCLUDE로 뺀다, 사람 얼굴이 주인공인 사진은 장소 사진이 아니다) → 장소마다 최신 게시물부터 돌아가며 **20장까지**(`cap: 20`), dHash 6비트 이내 연속 사진 제외 → 사진 없는 장소는 포털 검색(이름)도 → `portal.json`(`opens_page: true`) → attach.
4. **D**: kogl.or.kr의 그 기관 제1유형·제3유형 사진은 기존 공공누리 규칙대로(KOGL-1/3, 출처 그 기관) 장소에 — 이미 쓰는 지역은 늘릴 수 있는 만큼.
5. **E**: `tools/kto_more_photos.py --data data/<region> --fill-to 12 --apply`(보이는 사진이 12장보다 적은 곳만, 이름이 맞는 사진만; 지역 설정 `data/<region>/kto_more.json`).
6. 사본: `tools/kogl1_media.py --data data/<region> --max-downloads 3000`. 원본 캐시는 data/cache(커밋 안 함).

지킬 것:
- 시청 서버는 몰아 요청하면 끊는다: **한 번에 1~3개, 요청 사이 3~6초, 끊기면 15초부터 늘려 다시**. HTML 오류 페이지를 사진으로 저장하지 않는다(city_photos.get이 거른다). 주소가 깨진 사진(`****` 등)은 빼고 보고.
- 사진은 제목·주소로 그 장소임이 분명할 때만 붙인다(비슷한 이름은 주소·촬영지로 확인). 행사·시정 사진, 사람이 주인공인 사진은 장소 사진으로 쓰지 않는다.
- 저장소 크기: 사본 합계 250MB·public 파일 15,000개를 넘기면 포털 상한을 줄인다(보고에 적음).
- 사진이 끝내 없는 장소는 목록으로 남긴다(업체 제공이 필요).

## 4. 검증

- `TZ=Asia/Seoul python tools/build_public.py` → qa_errors 0(경고 수는 전과 같게).
- 공개 빌드에서 시청 서버 주소를 그림(src·srcset)으로 부르는 곳 0, 외국어판에 한글 출처 0, og:image에 시청 사진 0.
- 장소 페이지 390·1440 캡처(대표가 시청 사진인 곳, 사진 더 보기 있는 곳), 사진 더 보기 열기 전 요청 0.
- 전체 pytest(`--basetemp`로 임시 폴더를 저장소 밖 한 곳에 두고 끝나면 지운다 — 26GB까지 쌓인 적 있음). 관광공사 사진만 가정하던 테스트는 새 규칙에 맞춘다(검증을 느슨하게 하지 말고 src별로 나눠 검사).

## 5. 커밋·푸시

- 작업 브랜치 `claude/city-photos-20261114`에 소스·데이터(places.json·portal.json·사본·manifest)·public 빌드를 나눠 커밋하고 푸시. main에는 올리지 않는다.
- `docs/handover/round3_log.md`(또는 그 저장소의 작업 기록)에 한 줄, CLAUDE.md 3절에 운영자 결정 기록.

## 6. 보고(조정 세션에 send_message)

조정 세션 id는 시작 메시지에 있다. 끝나면(또는 막히면) 아래를 한 메시지로 보낸다:

```
[지역] 저장소 / 브랜치 / 마지막 커밋
조사: A … B … C(주소·방식·규모·공공누리) … D … E … F …
추가: 누리집 n장(공개 m곳) · 포털 n장(m곳) · 공공누리 n장 · 관광공사 n장
사진 있는 공개 장소: 전 a/b → 후 c/b, 사진 없는 곳 d곳(유형별)
사본: n장·파일 n개·MB, public 파일 수
검증: qa_errors, 경고, pytest 결과
남은 문제·운영자 결정이 필요한 것
```
