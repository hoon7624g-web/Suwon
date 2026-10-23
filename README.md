# 수원각 (Suwongak) — 수원 여행 실증 사이트

한국관광공사 TourAPI(국문·8개 외국어·무장애 여행 정보·관광사진 정보·반려동물 동반여행·고캠핑·두루누비)와 수원특례시 공공 관광 데이터를 바탕으로 **장소(관광지·음식점·숙소)·코스·가이드·축제·영상을 연결한 수원 여행 정보 사이트**입니다 (`https://suwon.webforai.kr`).

군산각(`gunsan.webforai.kr`)의 빌드·검증·구조화 데이터·화면·챗봇·AI 코스 플래너 엔진과 다도시 설정 구조(`pipeline/city.py`, `data/suwon/site.json`)를 사용합니다.

## 주요 구성

| 경로 | 역할 |
|---|---|
| `data/suwon/site.json` | 수원각 도시 설정(경기도 수원시 4개 구 법정동 범위, 5대 권역 `anchors`, 9개 언어 로케일, 챗봇·플래너·음식 분류 설정) |
| `data/suwon/*.json` | 수원 장소(`places.json`), 가이드(`guides.json`), 코스(`courses.json`), 행사(`events.json`), 영상(`videos.json`), 해외 시선(`abroad.json`, `abroad_highlights.json`) |
| `pipeline/` | 정적 사이트 빌드(`build.py`), 검증(`validate.py`), 도시 설정(`city.py`), TourAPI 클라이언트(`tourapi.py`), 다국어(`en_site.py`, `locales.py`) |
| `tools/` | TourAPI 수집(`tourapi_doctor.py`, `tourapi_bulk.py`, `tourapi_harvest.py`, `harvest_merge.py`), 품질 리포트(`quality_report.py`), 공개 빌드(`build_public.py`) |
| `templates/` | Jinja2 템플릿, CSS, JS, Pretendard 서브셋 폰트, 3D 아이콘 및 수원각 브랜드 심볼(`suwongak-symbol.svg`) |
| `chatbot/`, `api/` | 사이트 안내 챗봇(`/api/chat`) 및 AI 코스 플래너(`/api/plan`) |

## 빠른 시작

```bash
python -m pip install -r requirements.txt
python tools/tourapi_doctor.py --data data/suwon --check-region
python tools/tourapi_bulk.py --data data/suwon --details --add-new --events --gallery --max-calls 900
python -m pipeline.build --data data/suwon --out dist-preview --mode preview
python -m pipeline.validate --data data/suwon --out dist-preview --mode preview
```
