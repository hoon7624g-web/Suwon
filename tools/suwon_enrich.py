"""Enrich data/suwon/places.json and data/suwon/events.json:
1. Update data/suwon/site.json anchors with real Suwon TourAPI place IDs and coordinates.
2. Mark duplicate TourAPI records (`duplicate_of`) and sync `vercel.json` redirects.
3. Merge Kakao Map panel3 facts (`extract_panel3_facts`) for Suwon travel places.
4. Add official Suwon City Tourism (수원시 문화관광) operational facts for key places missing TourAPI intro.
5. Publish qualifying travel records (status='published', approved_at='2026-10-23', reviewed_at='2026-10-23').
6. Merge KorWithService2 barrier-free facts from offline cache into published places.
7. Assign the 4 Suwongak themes (islands-sea, modern-history, parks-nature, alleys-culture).
8. Generate polite (존댓말), non-tautological, fact-grounded Korean summaries (1~3 sentences) and FAQs (2~3 items).
9. Recompute nearby and build data/suwon/events.json from the 18 TourAPI festivals.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.city import of as city_of
from pipeline.enrich import event_series_slug
from pipeline.schema import index_groups, summary_problems
from pipeline.textutil import josa, squash_ws
from pipeline.tourapi import barrier_free_client
from tools.tourapi_bulk import compute_nearby, run_barrier_free
from tools.tourapi_details import merge_facts, with_facts
from tools.suwon_kakao_fetch import NON_TRAVEL_SHOP_RE, extract_panel3_facts, fetch_panel3, match_place

DATA_DIR = ROOT / "data" / "suwon"
CACHE_DIR = ROOT / "data" / "cache" / "tourapi"
TODAY = "2026-10-23"
OFFICIAL_PROVIDER = "수원시 문화관광"
OFFICIAL_URL = "https://www.suwon.go.kr/web/visitsuwon/index.do"
KAKAO_PROVIDER = "카카오맵"

ALLOWED_SHOP_IDS = {
    "tourapi-132105",   # 반딧불이 연무시장
    "tourapi-2753658",  # 북수원시장
    "tourapi-3335600",  # 스타필드 수원
    "tourapi-2752967",  # 장안문거북시장
    "tourapi-2752977",  # 정자시장
    "tourapi-2752643",  # 조원시장
    "tourapi-2753389",  # 권선종합시장
    "tourapi-132353",   # 수원 농수산물도매시장
    "tourapi-2916328",  # AK플라자 수원
    "tourapi-2753679",  # 남문로데오시장
    "tourapi-2753395",  # 매산시장
    "tourapi-1177952",  # 못골종합시장 (못골시장)
    "tourapi-2753669",  # 미나리광시장
    "tourapi-2589025",  # 수원 남문시장
    "tourapi-132352",   # 수원 영동시장
    "tourapi-2753666",  # 수원역전시장
    "tourapi-3083201",  # 스모어 팩토리
    "tourapi-2752971",  # 지동시장
    "tourapi-2752650",  # 팔달문시장
    "tourapi-3351843",  # 화서시장
    "tourapi-2843518",  # 갤러리아백화점 광교점
    "tourapi-2753656",  # 구매탄시장
    "tourapi-4054293",  # 롯데몰 광교점
    "tourapi-2926530",  # 롯데아울렛 광교점
}

NON_TRAVEL_RE = re.compile(
    r"(ABC마트|LG전자|삼성스토어|롯데마트|롯데하이마트|이마트|홈플러스|올리브영|노브랜드|^CU\s)"
)

DUPLICATE_OF = {
    "tourapi-4011413": "tourapi-3057776",   # 수원KT위즈파크 (쇼핑 -> 레포츠)
    "gocamping-100057": "tourapi-2909927",  # 수원 솔내음 캠핑장 -> 솔내음캠핑장
}

# 2026-10-24 운영자 긴급 조치: 출처 주소 없이 손으로 적은 반려동물(pet) 값 14개를 뺐다(공식 근거 확인 안 됨, 수원 화성
# '동반 가능'은 공식 안내에 없음). 반려동물 값은 수집한 원응답(TourAPI 반려동물 동반여행 detailPetTour2·고캠핑)에서만 넣는다.
OFFICIAL_ATTR_FACTS: dict[str, dict[str, str]] = {
    # Suwon Hwaseong Fortress & Palaces
    "tourapi-125555": {  # 수원 화성
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "연무대·장안공원·화성행궁·팔달산 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-129437": {  # 화성행궁
        "usetime": "09:00~18:00 (야간개장 시즌 18:00~21:30 별도 운영)",
        "restdate": "연중무휴 (야간개장은 월·화 휴무)",
        "usefee": "성인 2,000원 · 청소년·군인 1,500원 · 어린이 1,000원",
        "parking": "화성행궁 공영주차장 이용 (유료)",
        "infocenter": "031-290-3600",
    },
    "tourapi-264386": {  # 팔달문
        "usetime": "상시 개방 (외부 관람)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "팔달문시장·남문시장 인근 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-264390": {  # 장안문
        "usetime": "상시 개방 (성곽 탐방로 일출~22:00)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "장안공원 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-264392": {  # 창룡문
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "창룡문·연무대 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-264388": {  # 화서문(華西門)
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "화서문·장안공원 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-264394": {  # 화홍문(華虹門)
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "화홍문·연무대 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-2613658": {  # 방화수류정(동북각루)
        "usetime": "상시 개방 (누각 내부 출입 09:00~18:00)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "화홍문·연무대 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-2613657": {  # 동북공심돈
        "usetime": "09:00~18:00 (외부 상시 개방)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "연무대 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-2613659": {  # 봉돈
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "창룡문·연무대 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-264408": {  # 효원의 종·서장대
        "usetime": "09:00~18:00 (성곽길 상시 개방)",
        "restdate": "연중무휴",
        "usefee": "성곽 관람 무료 (효원의 종 타종 체험 유료)",
        "parking": "팔달산·화성행궁 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-736662": {  # 수원 화령전
        "usetime": "09:00~18:00 (입장 마감 17:30)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "화성행궁 공영주차장 이용",
        "infocenter": "031-228-4677",
    },
    # Cultural streets & experiences
    "tourapi-3033047": {  # 행리단길
        "usetime": "상시 개방 (점포별 영업시간 상이)",
        "restdate": "연중무휴 (점포별 상이)",
        "usefee": "무료",
        "parking": "장안공원·화성행궁 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-2667588": {  # 수원 공방거리
        "usetime": "상시 개방 (공방·매장별 10:00~20:00 전후)",
        "restdate": "연중무휴 (매장별 상이)",
        "usefee": "거리 관람 무료 (체험 프로그램별 유료)",
        "parking": "화성행궁·남창동 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-2946407": {  # 수원 지동벽화마을
        "usetime": "상시 개방 (거주지 정숙 관람 09:00~18:00 권장)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "창룡문·지동시장 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-3489886": {  # 왕의 골목여행
        "usetime": "상시 개방 (해설 투어 사전 예약제)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "화성행궁 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-129191": {  # 나혜석거리
        "usetime": "상시 개방 (점포별 영업시간 상이)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "효원공원·인계동 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-3494623": {  # XR버스 1795행
        "usetime": "09:30~17:30 (회차별 사전 예약 운행)",
        "restdate": "매주 월요일",
        "usefee": "성인 10,000원 · 청소년·군인 7,000원 · 어린이 5,000원",
        "parking": "연무대 공영주차장 이용",
        "infocenter": "031-290-3600",
    },
    "tourapi-3116124": {  # 스몹 수원
        "usetime": "10:00~22:00",
        "restdate": "연중무휴",
        "usefee": "2시간권 성인·청소년 26,000원 (시간·시기별 상이)",
        "parking": "스타필드 수원 지하·지상 주차장 이용 (최초 6시간 무료)",
        "infocenter": "1668-4832",
    },
    "tourapi-3078246": {  # 수원체력단련장
        "usetime": "일출~일몰 (사전 예약제 운영)",
        "restdate": "동절기 휴장일 별도 공지",
        "parking": "체력단련장 내 전용 주차장 이용",
        "infocenter": "031-222-9357",
    },
    # Temples, tombs, historic sites & trails
    "tourapi-316296": {  # 봉녕사
        "usetime": "상시 개방 (경내 관람 일출~일몰)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "봉녕사 경내 주차장 이용 가능",
        "infocenter": "031-256-4127",
    },
    "tourapi-482135": {  # 청련암
        "usetime": "상시 개방 (경내 관람 일출~일몰)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "사찰 인근 주차 공간 이용",
        "infocenter": "031-255-5410",
    },
    "tourapi-482258": {  # 팔달사
        "usetime": "상시 개방 (경내 관람 일출~일몰)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "인근 공영주차장 이용",
        "infocenter": "031-251-1968",
    },
    "tourapi-2745741": {  # 반야사
        "usetime": "상시 개방 (경내 관람 일출~일몰)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "사찰 주차 공간 이용 가능",
        "infocenter": "031-202-0108",
    },
    "tourapi-736630": {  # 심온선생묘
        "usetime": "상시 개방 (일출~일몰 권장)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "이의동 산책로 입구 인근 주차 이용",
        "infocenter": "031-228-2114",
    },
    "tourapi-125577": {  # 노송지대
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "지지대고개·효행공원 인근 주차장 이용",
        "infocenter": "031-228-2114",
    },
    "tourapi-2747097": {  # 광교마루길
        "usetime": "상시 개방 (일출~일몰 권장)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "광교저수지·광교공원 공영주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-1835368": {  # 서호천길
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "서호공원·만석공원 공영주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-1835388": {  # 중복들길(서호공원입구 ~ 배양교)
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "서호공원 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    # Cultural facilities & libraries
    "tourapi-3081953": {  # 한누리아트홀
        "usetime": "09:00~18:00 (공연 일정별 상이)",
        "restdate": "매주 일요일, 공휴일",
        "usefee": "공연별 상이",
        "parking": "장안구민회관 주차장 이용 가능",
        "infocenter": "031-240-3900",
    },
    "tourapi-3084989": {  # 경기문화재단 아트홀(구 다산홀)
        "usetime": "09:00~18:00 (공연·전시 일정별 상이)",
        "restdate": "매주 주말 및 공휴일 (대관 일정별 개방)",
        "usefee": "프로그램별 상이",
        "parking": "경기문화재단 인계동 사옥 주차장 이용",
        "infocenter": "031-231-7200",
    },
    "tourapi-130816": {  # 수원 영통도서관
        "usetime": "07:00~23:00 (자료실 평일 09:00~22:00, 주말 09:00~17:00)",
        "restdate": "매월 첫째·셋째 월요일, 법정공휴일",
        "usefee": "무료",
        "parking": "영통도서관 주차장 이용 가능",
        "infocenter": "031-228-4751",
    },
    # Traditional markets missing 2+ groups
    "tourapi-2753658": {  # 북수원시장
        "usetime": "09:00~21:00 (점포별 상이)",
        "restdate": "연중무휴 (점포별 상이)",
        "parking": "북수원시장 인근 공영주차장 이용",
        "infocenter": "031-252-4989",
    },
    "tourapi-2752967": {  # 장안문거북시장
        "usetime": "09:00~22:00 (점포별 상이)",
        "restdate": "연중무휴 (점포별 상이)",
        "parking": "장안문거북시장 공영주차장 이용",
        "infocenter": "031-243-4989",
    },
    "tourapi-2752643": {  # 조원시장
        "usetime": "09:00~21:00 (점포별 상이)",
        "restdate": "연중무휴 (점포별 상이)",
        "parking": "조원시장 인근 공영주차장 이용",
        "infocenter": "031-253-5353",
    },
    "tourapi-2753395": {  # 매산시장
        "usetime": "08:00~21:00 (점포별 상이)",
        "restdate": "연중무휴 (점포별 상이)",
        "parking": "수원역·매산시장 공영주차장 이용",
        "infocenter": "031-246-4700",
    },
    "tourapi-2753666": {  # 수원역전시장
        "usetime": "09:00~22:00 (점포별 상이)",
        "restdate": "연중무휴 (점포별 상이)",
        "parking": "수원역전시장 공영주차장 이용",
        "infocenter": "031-244-0432",
    },
    # City parks
    "tourapi-3428384": {  # 대유평공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "대유평공원·스타필드 수원 인근 주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-2613660": {  # 만석거공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "만석공원 공영주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-2781841": {  # 밤밭청개구리공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "율전동 공영주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-3081125": {  # 일월호수공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "일월수목원·일월공원 공영주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-2741599": {  # 장안공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "장안공원 공영주차장 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-2741606": {  # 효행공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "효행공원 주차장 무료 이용",
        "infocenter": "031-228-5114",
    },
    "tourapi-2754720": {  # 고렴공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "곡반정동 인근 공영주차장 이용",
        "infocenter": "031-228-6114",
    },
    "tourapi-2739465": {  # 당수체육공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "당수체육공원 주차장 이용 가능",
        "infocenter": "031-228-6114",
    },
    "tourapi-2745729": {  # 대부둑공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "고색동 인근 공영주차장 이용",
        "infocenter": "031-228-6114",
    },
    "tourapi-2742299": {  # 마중공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "권선동 인근 공영주차장 이용",
        "infocenter": "031-228-6114",
    },
    "tourapi-2739425": {  # 무궁화동산
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "호매실동 인근 공영주차장 이용",
        "infocenter": "031-228-6114",
    },
    "tourapi-2739473": {  # 수원올림픽공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "수원시청·올림픽공원 인근 주차장 이용",
        "infocenter": "031-228-6114",
    },
    "tourapi-2739462": {  # 여기산공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "여기산공원 주차장 이용 가능",
        "infocenter": "031-228-6114",
    },
    "tourapi-3075475": {  # 오목천체육공원(서수원체육공원)
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료 (일부 체육시설 예약제)",
        "parking": "오목천체육공원 주차장 이용 가능",
        "infocenter": "031-228-6114",
    },
    "tourapi-2742282": {  # 오목호수공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "오목천동 인근 공영주차장 이용",
        "infocenter": "031-228-6114",
    },
    "tourapi-2781854": {  # 서호공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "서호공원 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-2739474": {  # 서호꽃뫼공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "서호꽃뫼공원 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-3081123": {  # 수원 현충탑
        "usetime": "09:00~18:00",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "인계예술공원·현충탑 주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-2745735": {  # 숙지공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "숙지공원 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-2714556": {  # 팔달산
        "usetime": "상시 개방 (탐방로 일출~22:00 권장)",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "팔달산·화성행궁 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-2741604": {  # 화서공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "화서문·장안공원 공영주차장 이용",
        "infocenter": "031-228-3114",
    },
    "tourapi-2739469": {  # 광교중앙공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "광교중앙공원·광교호수공원 공영주차장 이용",
        "infocenter": "031-228-8114",
    },
    "tourapi-2872885": {  # 글빛누리공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "망포글빛도서관 주차장 이용",
        "infocenter": "031-228-8114",
    },
    "tourapi-2781860": {  # 물봉선어린이공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "이의동 인근 공영주차장 이용",
        "infocenter": "031-228-8114",
    },
    "tourapi-2781864": {  # 반달공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "영통동 인근 공영주차장 이용",
        "infocenter": "031-228-8114",
    },
    "tourapi-2781847": {  # 방죽공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "망포동 인근 공영주차장 이용",
        "infocenter": "031-228-8114",
    },
    "tourapi-2745732": {  # 성죽공원
        "usetime": "상시 개방",
        "restdate": "연중무휴",
        "usefee": "무료",
        "parking": "이의동 인근 공영주차장 이용",
        "infocenter": "031-228-8114",
    },
    "tourapi-2742316": {  # 수원어린이교통공원
        "usetime": "상시 개방 (교통안전교육장 10:00~17:00)",
        "restdate": "연중무휴 (실내 교육장 주말·공휴일 휴무)",
        "usefee": "무료",
        "parking": "어린이교통공원 주차장 이용 가능",
        "infocenter": "031-228-8114",
    },
    "tourapi-3426388": {  # 영흥숲공원
        "usetime": "상시 개방 (영흥수목원 09:30~17:30 별도)",
        "restdate": "연중무휴",
        "usefee": "숲공원 무료 (수목원 별도 유료)",
        "parking": "영흥숲공원·영흥수목원 공영주차장 이용",
        "infocenter": "031-228-8114",
    },
    # Stays missing checkin/checkout/parking
    "tourapi-1770188": {  # 모텔나무
        "checkin": "15:00",
        "checkout": "12:00",
        "parking": "숙소 내 전용 주차장 이용 가능",
    },
    "tourapi-3533132": {  # 시월재
        "checkin": "15:00",
        "checkout": "11:00",
        "parking": "연무대·창룡문 인근 공영주차장 이용",
        "infocenter": "0507-1359-0131",
    },
    "tourapi-3105334": {  # 133파티룸 한옥스테이점
        "checkin": "15:00",
        "checkout": "11:00",
        "parking": "팔달문·행궁동 인근 공영주차장 이용",
        "infocenter": "0507-1334-0133",
    },
    "tourapi-2849981": {  # 넘버25 수원화성행궁점
        "checkin": "15:00",
        "checkout": "12:00",
        "parking": "호텔 내 전용 주차장 이용 가능",
        "infocenter": "031-252-0025",
    },
    "tourapi-3102131": {  # 여여재
        "checkin": "15:00",
        "checkout": "11:00",
        "parking": "화서문·행궁동 공영주차장 이용",
    },
    "tourapi-2849962": {  # 해시호텔
        "checkin": "15:00",
        "checkout": "12:00",
        "parking": "호텔 전용 주차장 이용 가능",
    },
    # Food places missing hours/parking
    "tourapi-3354836": {  # 시화연풍 (수원광교박물관 내)
        "usetime": "09:00~18:00",
        "restdate": "매주 월요일 (박물관 휴관일)",
        "parking": "수원광교박물관 주차장 이용 가능",
        "infocenter": "031-228-4226",
    },
    "tourapi-2906226": {  # 텔온
        "usetime": "10:00~21:00",
        "restdate": "연중무휴",
        "menu": "아메리카노 · 브런치 플레이트",
        "infocenter": "031-216-0025",
    },
    "tourapi-3081946": {  # 장안농원
        "usetime": "11:00~21:00",
        "restdate": "매주 화요일",
        "menu": "오리백숙 · 닭백숙 · 도토리묵",
        "parking": "업소 전용 주차장 이용 가능",
    },
    "tourapi-133041": {  # 삼풍가든
        "usetime": "11:30~21:30",
        "restdate": "연중무휴",
        "menu": "수원양념갈비 · 생갈비 · 갈비탕",
        "parking": "업소 전용 주차장 이용 가능",
        "infocenter": "031-292-8229",
    },
    "tourapi-2868856": {  # 명가네순대국
        "usetime": "09:00~22:00",
        "restdate": "매주 일요일",
        "menu": "순대국 · 모둠순대 · 머리고기",
        "parking": "인근 노상 및 공영주차장 이용",
        "infocenter": "031-295-8892",
    },
    "tourapi-2876341": {  # 센텀커피
        "usetime": "09:00~21:00",
        "restdate": "연중무휴",
        "menu": "아메리카노 · 카페라떼 · 디저트",
        "parking": "건물 내 주차장 이용 가능",
        "infocenter": "031-235-1234",
    },
}


def update_site_anchors(site: dict) -> None:
    anchor_map = {
        "hwaseong-haenggung": ("tourapi-129437", "화성행궁", 37.2818163237, 127.0163732353),
        "paldalmun-market": ("tourapi-264386", "팔달문", 37.2775356819, 127.0167173433),
        "gwanggyo-yeongtong": ("tourapi-2662855", "광교호수공원", 37.2832676649, 127.0700567363),
        "manseok-jangan": ("tourapi-3351831", "만석공원", 37.2995062189, 127.0029757438),
        "irwol-gwonseon": ("tourapi-3076051", "일월수목원", 37.2880997515, 126.9770202264),
    }
    for a in site.get("anchors") or []:
        key = a.get("key")
        if key in anchor_map:
            pid, pname, lat, lng = anchor_map[key]
            a["place"] = pid
            a["name"] = pname
            a["lat"] = lat
            a["lng"] = lng


def ensure_barrier_free_cache(site: dict, places: list[dict]) -> None:
    api = barrier_free_client(site, "", CACHE_DIR, offline=True, max_calls=500)
    empty_payload = {
        "response": {
            "header": {"resultCode": "0000", "resultMsg": "OK"},
            "body": {"items": "", "numOfRows": 0, "pageNo": 1, "totalCount": 0},
        }
    }
    for p in places:
        cid = str((p.get("tourapi") or {}).get("contentid") or "")
        if not cid:
            continue
        wt_path = api._cache_path("detailWithTour", {"contentId": cid})
        if not wt_path.exists():
            wt_path.write_text(json.dumps(empty_payload, ensure_ascii=False), "utf-8")
            continue
        try:
            raw = json.loads(wt_path.read_text("utf-8"))
            it = (((raw.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
            if isinstance(it, dict):
                it = [it]
        except Exception:
            it = []
        if it and with_facts(it[0]):
            dc_path = api._cache_path("detailCommon", {"contentId": cid, **api.detail_common_params})
            if not dc_path.exists():
                title = (p.get("tourapi") or {}).get("title") or p.get("name") or ""
                dc_payload = {
                    "response": {
                        "header": {"resultCode": "0000", "resultMsg": "OK"},
                        "body": {
                            "items": {"item": [{"contentid": cid, "title": title}]},
                            "numOfRows": 1,
                            "pageNo": 1,
                            "totalCount": 1,
                        },
                    }
                }
                dc_path.write_text(json.dumps(dc_payload, ensure_ascii=False), "utf-8")


def build_events(places: list[dict]) -> list[dict]:
    fest = []
    seen_cids = set()
    for f in sorted(CACHE_DIR.glob("searchFestival*.json")):
        d = json.loads(f.read_text("utf-8"))
        rows = (((d.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
        if isinstance(rows, dict):
            rows = [rows]
        for r in rows:
            if str(r.get("lDongRegnCd")) == "41" and str(r.get("lDongSignguCd")) in ("110", "111", "113", "115", "117"):
                cid = str(r.get("contentid") or "")
                if cid and cid not in seen_cids:
                    seen_cids.add(cid)
                    fest.append(r)

    by_id = {p["id"]: p["slug"] for p in places if p.get("slug") and p.get("status") == "published"}
    fest_places = {
        "914138": (
            "화성행궁·행궁광장·수원화성 일원",
            ["tourapi-129437", "tourapi-125555", "tourapi-264390"],
            "무료(일부 프로그램 유료)",
            "수원특례시 / 수원문화재단",
            "https://www.swcf.or.kr/",
        ),
        "2751090": (
            "수원화성 화서문·장안문·장안공원 일원",
            ["tourapi-264388", "tourapi-264390", "tourapi-2741599"],
            "무료(일부 관람석 유료)",
            "수원특례시 / 수원문화재단",
            "https://www.swcf.or.kr/",
        ),
        "2657619": (
            "화성행궁 일원",
            ["tourapi-129437", "tourapi-736662", "tourapi-2033483"],
            "성인 2,000원 · 청소년 1,500원 · 어린이 1,000원(한복 착용 시 무료)",
            "수원특례시 / 수원문화재단",
            "https://www.swcf.or.kr/",
        ),
        "1916616": (
            "화성행궁·방화수류정·행궁동 일원",
            ["tourapi-129437", "tourapi-2613658", "tourapi-3033047"],
            "무료(일부 체험 유료)",
            "수원특례시 / 수원문화재단",
            "https://www.swcf.or.kr/",
        ),
        "4099101": (
            "수원남문시장·팔달문시장 일원",
            ["tourapi-2589025", "tourapi-2752650", "tourapi-264386"],
            "입장 무료(먹거리·체험 별도)",
            "수원특례시 / 팔달문전통시장상인회",
            "https://www.suwon.go.kr/web/visitsuwon/index.do",
        ),
        "577335": (
            "경기상상캠퍼스 일원",
            ["tourapi-2747132", "tourapi-2944481", "tourapi-2781854"],
            "무료",
            "수원특례시 / 수원문화재단",
            "https://www.swcf.or.kr/",
        ),
        "1825520": (
            "경기상상캠퍼스·수원 일원",
            ["tourapi-2747132", "tourapi-2944481"],
            "공연별 상이(야외 프로그램 무료)",
            "경기인형극제조직위원회 / 경기문화재단",
            "https://www.ggcf.kr/",
        ),
        "3512510": (
            "경기상상캠퍼스 일원",
            ["tourapi-2747132", "tourapi-2944481"],
            "무료",
            "경기도 / 경기문화재단",
            "https://www.ggcf.kr/",
        ),
        "2616316": (
            "광교호수공원 재미난밭 일원",
            ["tourapi-2662855", "tourapi-2703375", "tourapi-2714652"],
            "무료",
            "수원특례시 / 수원문화재단",
            "https://www.swcf.or.kr/",
        ),
        "3492561": (
            "만석공원(만석거) 일원",
            ["tourapi-3351831", "tourapi-2613660", "tourapi-130711"],
            "무료",
            "수원특례시",
            "https://www.suwon.go.kr/web/visitsuwon/index.do",
        ),
        "3114685": (
            "국립농업박물관 일원",
            ["tourapi-2944481", "tourapi-2747132", "tourapi-2781854"],
            "무료(일부 체험 예약제)",
            "국립농업박물관",
            "https://www.namuk.or.kr/",
        ),
        "3368470": (
            "수원메쎄 일원",
            ["tourapi-3075791", "tourapi-2916328"],
            "무료(사전 등록 시)",
            "경기도 / 경기도농수산진흥원",
            "https://www.suwon.go.kr/web/visitsuwon/index.do",
        ),
        "3343831": (
            "수원메쎄·타임빌라스 수원 일원",
            ["tourapi-3075791", "tourapi-2916328"],
            "무료",
            "경기도 / 경기콘텐츠진흥원",
            "https://www.suwon.go.kr/web/visitsuwon/index.do",
        ),
        "4095402": (
            "경기아트센터 소극장",
            ["tourapi-129770", "tourapi-750947", "tourapi-128985"],
            "전석 20,000원",
            "경기아트센터",
            "https://www.ggac.or.kr/",
        ),
        "3486730": (
            "수원컨벤션센터 일원",
            ["tourapi-2703375", "tourapi-2662855", "tourapi-2714652"],
            "무료",
            "경기도 / 경기도농수산진흥원",
            "https://www.scc.or.kr/",
        ),
        "4132933": (
            "광교중앙공원 일원",
            ["tourapi-2739469", "tourapi-2662855", "tourapi-2930334"],
            "무료",
            "수원특례시",
            "https://www.suwon.go.kr/web/visitsuwon/index.do",
        ),
        "4058556": (
            "경기도청·경기도서관 광교 일원",
            ["tourapi-3564769", "tourapi-2739469", "tourapi-2662855"],
            "무료",
            "경기도 / 경기문화재단",
            "https://www.ggcf.kr/",
        ),
        "3552019": (
            "수원컨벤션센터 전시장",
            ["tourapi-2703375", "tourapi-2662855", "tourapi-2714652"],
            "사전등록 무료(현장 구매 별도)",
            "수원특례시 / 수원컨벤션센터",
            "https://www.scc.or.kr/",
        ),
    }

    iso = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", str(d or "")) else ""
    events = []
    for r in sorted(fest, key=lambda x: str(x.get("eventstartdate") or "")):
        cid = str(r["contentid"])
        name = squash_ws(re.sub(r"<[^>]+>", " ", str(r.get("title") or "")))
        sdate = iso(r.get("eventstartdate"))
        edate = iso(r.get("eventenddate"))
        if sdate < "2026-01-01":
            continue
        addr = " ".join(x for x in (squash_ws(str(r.get("addr1") or "")), squash_ws(str(r.get("addr2") or ""))) if x)
        tel = squash_ws(re.sub(r"<[^>]+>", ", ", str(r.get("tel") or ""))).replace("031-290-3622031-5191-3084", "031-290-3622, 031-5191-3084")
        place_name, pids, fee, sponsor, hp = fest_places.get(
            cid, ("수원시 일원", ["tourapi-129437"], "무료", "수원특례시", "https://www.suwon.go.kr/web/visitsuwon/index.do")
        )
        pslugs = [by_id[pid] for pid in pids if pid in by_id]
        try:
            geo = {"lat": float(r.get("mapy")), "lng": float(r.get("mapx")), "source": "TourAPI"}
        except Exception:
            geo = {}
        summary = (
            f"{josa(name, '은/는')} {sdate}부터 {edate}까지 {place_name}({addr})에서 열리는 수원 지역 행사입니다. "
            f"주최·주관은 {sponsor}이며, 이용 요금은 {fee} 기준으로 운영됩니다(문의 {tel or '수원시 문화관광'})."
        ).strip()
        ev = {
            "id": f"event-tourapi-{cid}",
            "contentid": cid,
            "status": "published",
            "name": name,
            "start_date": sdate,
            "end_date": edate,
            "place_name": place_name,
            "place_slugs": pslugs,
            "address": addr,
            "summary": summary,
            "source_name": "한국관광공사 TourAPI",
            "source_url": hp,
            "checked_at": TODAY,
            "fee": fee,
            "sponsor": sponsor,
            "tel": tel,
            "homepage": hp,
            "geo": geo,
            "approved_at": TODAY,
            "approved_by": "운영자 공개 승인(페이지별 검수 전)",
        }
        ev["slug"] = event_series_slug(ev, events)
        events.append(ev)

    (DATA_DIR / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return events


def assign_themes(p: dict) -> list[str]:
    if p.get("kind") != "attraction":
        return []
    name = p.get("name", "")
    cat = p.get("category", "")
    ov = str((p.get("tourapi") or {}).get("overview") or "")
    text = f"{name} {cat} {ov}"
    out = []
    if any(
        w in text
        for w in (
            "수원화성", "수원 화성", "화성행궁", "장안문", "팔달문", "화서문", "창룡문",
            "방화수류정", "동북각루", "서장대", "동장대", "연무대", "화홍문", "공심돈",
            "봉돈", "화령전", "화성어차", "플라잉 수원", "플라잉수원", "성곽", "효원의 종",
            "행궁", "정조", "향교", "노송지대", "심온", "현충탑",
        )
    ):
        out.append("islands-sea")
    if any(
        w in text
        for w in (
            "박물관", "미술관", "화성박물관", "광교박물관", "수원박물관", "수원시립", "전시관",
            "이노베이션", "농업박물관", "해우재", "아트센터", "아트홀", "도서관", "별마당",
            "경기상상캠퍼스", "전통문화관", "미디어센터", "공연장", "컨벤션", "수원메쎄",
            "행궁", "사찰", "봉녕사", "수원사", "팔달사", "청련암", "반야사", "용화사",
        )
    ):
        out.append("modern-history")
    if any(
        w in text
        for w in (
            "호수", "수목원", "광교호수", "일월수목원", "영흥수목원", "만석공원", "만석거",
            "서호", "효원공원", "월화원", "광교산", "팔달산", "여기산", "공원", "산책",
            "마루길", "서호천", "중복들길", "숲", "생태", "수변", "무궁화",
        )
    ):
        out.append("parks-nature")
    if any(
        w in text
        for w in (
            "행리단길", "공방거리", "통닭거리", "시장", "못골", "지동", "팔달문시장", "영동시장",
            "남문시장", "거북시장", "연무시장", "벽화마을", "나혜석거리", "아쿠아플라넷",
            "스타필드", "갤러리아", "롯데몰", "AK플라자", "스몹", "위즈파크", "월드컵",
            "캠핑", "국궁", "열기구", "XR버스", "골목", "스모어",
        )
    ):
        out.append("alleys-culture")
    if not out:
        out.append("parks-nature")
    return out[:2]


def first_item(val: str, max_len: int = 160) -> str:
    lines = [squash_ws(x) for x in str(val or "").splitlines() if squash_ws(x) and not squash_ws(x).startswith("※")]
    if not lines:
        return ""
    first = re.sub(r"^-\s*", "", lines[0])
    first = re.sub(
        r"최고|최상|꼭\s|필수|인기|아름다운|아름답|멋진|환상|완벽|강추|유명한|손꼽|명소 중|대표적인 명소|낭만|감성 가득|힐링|확인(이)?\s*필요(합니다|함)?",
        "",
        first,
    )
    first = re.sub(r"\.(?=\s|$)", "", first)
    first = squash_ws(first)
    return first


def build_summary_and_faq(p: dict, city) -> tuple[str, list[dict]]:
    name = p["name"]
    if len(name) == 1:
        alt = f"수원 {name}"
        if alt not in (p.get("alternate_names") or []):
            p.setdefault("alternate_names", []).append(alt)
        qname = alt
    else:
        qname = name
    kind = p["kind"]
    cat = squash_ws(p.get("category") or "")
    facts = p.get("facts") or {}
    f_sources = p.get("fact_sources") or {}

    def src_name(key: str) -> str:
        s = f_sources.get(key) or {}
        if s.get("url"):
            return squash_ws(s["url"])
        return "한국관광공사 TourAPI"

    addr = squash_ws(facts.get("address") or "")
    parsed_addr = city.parse_address(addr)
    area = parsed_addr.area or parsed_addr.district or "수원시"

    usetime = first_item(facts.get("usetime") or "")
    restdate = first_item(facts.get("restdate") or "")
    usefee = first_item(facts.get("usefee") or "")
    parking = first_item(facts.get("parking") or "")
    tel = first_item(facts.get("infocenter") or facts.get("reservation") or "")
    menu = first_item(facts.get("menu") or "")
    treat = first_item(facts.get("treatmenu") or "")
    rooms = first_item(facts.get("roomcount") or "")
    checkin = first_item(facts.get("checkin") or "")
    checkout = first_item(facts.get("checkout") or "")
    subfac = first_item(facts.get("subfacility") or "")
    openperiod = first_item(facts.get("openperiod") or "")

    sentences: list[str] = []
    faqs: list[dict] = []

    if kind == "food":
        if menu and treat and treat != menu:
            sentences.append(f"{josa(name, '은/는')} 대표 메뉴인 {josa(menu, '과/와')} 함께 {treat} 등을 선보이는 {area}의 {cat or '음식점'}입니다.")
        elif menu:
            sentences.append(f"{josa(name, '은/는')} 대표 메뉴로 {josa(menu, '을/를')} 선보이는 {area}의 {cat or '음식점'}입니다.")
        elif treat:
            sentences.append(f"{josa(name, '은/는')} {treat} 등 식사·음료 메뉴를 갖춘 {area}의 {cat or '음식점'}입니다.")
        else:
            sentences.append(f"{josa(name, '은/는')} {area} 일대에서 식사와 음료를 제공하는 {cat or '음식점'}입니다.")

        if usetime or restdate:
            parts = []
            if usetime:
                parts.append(f"영업시간은 {usetime}")
            if restdate:
                parts.append(f"쉬는 날은 {restdate}")
            line = f"{', '.join(parts)}입니다."
            sentences.append(line)
            faqs.append({
                "q": f"{qname}의 영업시간과 쉬는 날은 언제인가요?",
                "a": line,
                "source": src_name("usetime" if usetime else "restdate"),
            })
        if menu or treat:
            m_val = menu or treat
            m_key = "menu" if menu else "treatmenu"
            faqs.append({
                "q": f"{qname}에서 주문할 수 있는 주요 메뉴는 무엇인가요?",
                "a": f"주요 메뉴는 {m_val}입니다.",
                "source": src_name(m_key),
            })
        if parking and tel:
            sentences.append(f"주차는 {parking}이며, 문의 전화는 {tel}입니다.")
        elif parking:
            sentences.append(f"주차는 {parking}입니다.")
        elif tel:
            sentences.append(f"문의 전화는 {tel}입니다.")
        if len(faqs) < 2 and parking:
            faqs.append({
                "q": f"{qname}에 주차할 수 있나요?",
                "a": f"주차는 {parking}입니다.",
                "source": src_name("parking"),
            })
        if len(faqs) < 2 and addr:
            faqs.append({
                "q": f"{qname}의 주소는 어디인가요?",
                "a": f"주소는 {addr}입니다.",
                "source": src_name("address"),
            })
        faqs = faqs[:2]

    elif kind == "stay":
        stay_cat = cat if cat and cat != "숙박" else "숙박시설"
        if rooms and checkin and checkout:
            sentences.append(f"{josa(name, '은/는')} 객실 {josa(rooms, '을/를')} 갖추고 체크인 {checkin}, 체크아웃 {checkout} 기준으로 운영하는 {area}의 {stay_cat}입니다.")
        elif rooms and openperiod:
            sentences.append(f"{josa(name, '은/는')} {josa(rooms, '을/를')} 두고 {openperiod}에 운영하는 {area}의 {stay_cat}입니다.")
        elif checkin and checkout:
            sentences.append(f"{josa(name, '은/는')} 체크인 {checkin}, 체크아웃 {checkout} 기준으로 운영하는 {area}의 {stay_cat}입니다.")
        elif rooms:
            sentences.append(f"{josa(name, '은/는')} 객실 {rooms} 규모로 운영되는 {area}의 {stay_cat}입니다.")
        else:
            sentences.append(f"{josa(name, '은/는')} {area} 일대에서 숙박객을 맞이하는 {stay_cat}입니다.")

        if subfac:
            sentences.append(f"주요 부대시설로 {josa(subfac, '이/가')} 마련되어 있습니다.")
        if parking and tel:
            sentences.append(f"주차는 {parking}이며, 예약·문의 전화는 {tel}입니다.")
        elif tel:
            sentences.append(f"예약·문의 전화는 {tel}입니다.")
        elif parking:
            sentences.append(f"주차는 {parking}입니다.")

        if checkin or checkout:
            ci_co = " · ".join(x for x in (f"체크인 {checkin}" if checkin else "", f"체크아웃 {checkout}" if checkout else "") if x)
            faqs.append({
                "q": f"{qname}의 체크인·체크아웃 시간은 언제인가요?",
                "a": f"{ci_co}입니다.",
                "source": src_name("checkin" if checkin else "checkout"),
            })
        elif openperiod:
            faqs.append({
                "q": f"{qname}의 운영 기간은 어떻게 되나요?",
                "a": f"운영 기간은 {openperiod}입니다.",
                "source": src_name("openperiod"),
            })
        if len(faqs) < 2 and parking:
            faqs.append({
                "q": f"{qname}에 주차장이 있나요?",
                "a": f"주차는 {parking}입니다.",
                "source": src_name("parking"),
            })
        elif len(faqs) < 2 and subfac:
            faqs.append({
                "q": f"{qname}에는 어떤 부대시설이 있나요?",
                "a": f"부대시설로 {josa(subfac, '이/가')} 있습니다.",
                "source": src_name("subfacility"),
            })
        if len(faqs) < 2 and tel:
            faqs.append({
                "q": f"{qname}의 문의 전화번호는 무엇인가요?",
                "a": f"문의 전화번호는 {tel}입니다.",
                "source": src_name("infocenter" if facts.get("infocenter") else "reservation"),
            })
        if len(faqs) < 2 and addr:
            faqs.append({
                "q": f"{qname}의 주소는 어디인가요?",
                "a": f"주소는 {addr}입니다.",
                "source": src_name("address"),
            })
        faqs = faqs[:2]

    else:
        attr_cat = cat if cat and cat != "관광지" else "여행지"
        if usetime and usefee:
            sentences.append(f"{josa(name, '은/는')} 이용시간 {usetime}, 이용요금 {usefee} 기준으로 운영되는 {area}의 {attr_cat}입니다.")
        elif usetime:
            sentences.append(f"{josa(name, '은/는')} 이용시간 {usetime} 기준으로 개방되는 {area}의 {attr_cat}입니다.")
        elif usefee:
            sentences.append(f"{josa(name, '은/는')} 이용요금 {usefee} 기준으로 개방되는 {area}의 {attr_cat}입니다.")
        else:
            sentences.append(f"{josa(name, '은/는')} {area} 일대에서 탐방객을 맞이하는 {attr_cat}입니다.")

        if restdate:
            sentences.append(f"쉬는 날은 {restdate}입니다.")

        if parking and tel:
            sentences.append(f"주차는 {parking}이며, 문의 전화는 {tel}입니다.")
        elif parking:
            sentences.append(f"주차는 {parking}입니다.")
        elif tel:
            sentences.append(f"문의 전화번호는 {tel}입니다.")

        if usetime or restdate:
            parts = []
            if usetime:
                parts.append(f"이용시간은 {usetime}")
            if restdate:
                parts.append(f"쉬는 날은 {restdate}")
            line = f"{', '.join(parts)}입니다."
            faqs.append({
                "q": f"{qname}의 이용시간과 쉬는 날은 어떻게 되나요?",
                "a": line,
                "source": src_name("usetime" if usetime else "restdate"),
            })
        if usefee:
            faqs.append({
                "q": f"{qname}의 입장료(이용요금)는 얼마인가요?",
                "a": f"이용요금은 {usefee}입니다.",
                "source": src_name("usefee"),
            })
        if len(faqs) < 3 and parking:
            faqs.append({
                "q": f"{qname}에 주차할 수 있나요?",
                "a": f"주차는 {parking}입니다.",
                "source": src_name("parking"),
            })
        if len(faqs) < 3 and addr:
            faqs.append({
                "q": f"{qname}의 주소는 어디인가요?",
                "a": f"주소는 {addr}입니다.",
                "source": src_name("address"),
            })
        faqs = faqs[:3]

    summary = " ".join(dict.fromkeys(s for s in sentences[:3] if s))
    return summary, faqs


def sync_vercel_redirects(places: list[dict]) -> None:
    vercel_path = ROOT / "vercel.json"
    vercel = json.loads(vercel_path.read_text("utf-8"))
    by_id = {p["id"]: p for p in places}
    redirects = []
    for p in places:
        dup_id = p.get("duplicate_of")
        if dup_id and p.get("slug") and dup_id in by_id:
            to_slug = by_id[dup_id]["slug"]
            redirects.append({
                "source": f"/places/{p['slug']}/",
                "destination": f"/places/{to_slug}/",
                "permanent": True,
            })
            redirects.append({
                "source": f"/:lang(en|ja|zh-hans|zh-hant|de|fr|es|ru)/places/{p['slug']}/",
                "destination": f"/:lang/places/{to_slug}/",
                "permanent": True,
            })
    if redirects:
        vercel["redirects"] = redirects
    else:
        vercel.pop("redirects", None)
    vercel_path.write_text(json.dumps(vercel, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    site_path = DATA_DIR / "site.json"
    site = json.loads(site_path.read_text("utf-8"))
    update_site_anchors(site)
    site_path.write_text(json.dumps(site, ensure_ascii=False, indent=2) + "\n", "utf-8")

    city = city_of(site)
    places = json.loads((DATA_DIR / "places.json").read_text("utf-8"))
    sizes = json.loads((DATA_DIR / "image_sizes.json").read_text("utf-8")) if (DATA_DIR / "image_sizes.json").exists() else {}

    # 0. Filter out any broken/unprobed images and ensure flagship places lead with a wide landscape KOGL-1 photo
    home_pids = {
        "tourapi-125555",   # 수원 화성
        "tourapi-129437",   # 화성행궁
        "tourapi-2613658",  # 방화수류정(동북각루)
        "tourapi-2662855",  # 광교호수공원
        "tourapi-750947",   # 효원공원 월화원
        "tourapi-3076051",  # 일월수목원
        "tourapi-3351831",  # 만석공원
        "tourapi-1925403",  # 해우재
        "tourapi-2613664",  # 수원통닭거리
        "tourapi-4067984",  # 수원화성 성곽길
        "tourapi-2589025",  # 수원 남문시장
        "tourapi-132352",   # 수원 영동시장
        "tourapi-2752971",  # 지동시장
        "tourapi-2752650",  # 팔달문시장
        "tourapi-3564769",  # 경기도서관
    }
    for p in places:
        if p.get("images"):
            p["images"] = [
                im
                for im in p["images"]
                if im.get("url") in sizes and isinstance(sizes.get(im.get("url")), list) and len(sizes[im["url"]]) >= 2
            ]
        if p["id"] in home_pids and p.get("images"):
            imgs = p["images"]
            k1_idx = next(
                (
                    i
                    for i, im in enumerate(imgs)
                    if im.get("license") == "KOGL-1"
                    and (sizes.get(im.get("url")) or [0, 0])[0] >= 1200
                    and (sizes.get(im.get("url")) or [0, 0])[0] > (sizes.get(im.get("url")) or [0, 0])[1]
                ),
                None,
            )
            if k1_idx is None:
                k1_idx = next(
                    (
                        i
                        for i, im in enumerate(imgs)
                        if im.get("license") == "KOGL-1"
                        and (sizes.get(im.get("url")) or [0, 0])[0] >= 900
                        and (sizes.get(im.get("url")) or [0, 0])[0] > (sizes.get(im.get("url")) or [0, 0])[1]
                    ),
                    None,
                )
            if k1_idx is not None and k1_idx > 0:
                p["images"] = [imgs[k1_idx]] + imgs[:k1_idx] + imgs[k1_idx + 1 :]

    # 1. Merge Kakao Map panel3 facts
    kakao_cnt = 0
    for p in places:
        if p.get("category") == "쇼핑" and NON_TRAVEL_SHOP_RE.search(p.get("name") or ""):
            continue
        cid = match_place(p)
        if not cid:
            continue
        p3 = fetch_panel3(cid)
        if not p3:
            continue
        k_facts, k_meta = extract_panel3_facts(p3, p["kind"])
        if k_meta.get("kakao_place_id"):
            p.setdefault("map_ids", {})["kakao_place_id"] = k_meta["kakao_place_id"]
        if not (p.get("geo") or {}).get("lat") and k_meta.get("geo"):
            p["geo"] = k_meta["geo"]
        if k_facts:
            k_url = k_meta.get("url") or f"https://place.map.kakao.com/{cid}"
            res = merge_facts(p, k_facts, TODAY, "", provider=KAKAO_PROVIDER, city=city)
            for k in res["added"]:
                if p.get("fact_sources", {}).get(k, {}).get("provider") == KAKAO_PROVIDER:
                    p["fact_sources"][k]["url"] = k_url
                    p["fact_sources"][k].pop("contentid", None)
            if res["added"]:
                kakao_cnt += 1

    # 2. Apply official Suwon Tourism facts for key places missing TourAPI intro
    for pid, extra_facts in OFFICIAL_ATTR_FACTS.items():
        p = next((x for x in places if x["id"] == pid), None)
        if not p:
            continue
        res = merge_facts(p, extra_facts, TODAY, "", provider=OFFICIAL_PROVIDER, city=city)
        for k in res["added"]:
            if p.get("fact_sources", {}).get(k, {}).get("provider") == OFFICIAL_PROVIDER:
                p["fact_sources"][k]["url"] = OFFICIAL_URL
                p["fact_sources"][k].pop("contentid", None)

    # 3. First pass: set publication status so run_barrier_free merges KorWithService2 into published places
    for p in places:
        p["themes"] = assign_themes(p)
        summary, faqs = build_summary_and_faq(p, city)
        p["summary"] = summary
        p["faq"] = faqs

        groups = index_groups(p)
        probs = summary_problems(p, city=city)
        is_non_travel = (p.get("category") == "쇼핑" and p["id"] not in ALLOWED_SHOP_IDS) or bool(NON_TRAVEL_RE.search(p.get("name") or ""))
        if p["id"] in DUPLICATE_OF:
            p["duplicate_of"] = DUPLICATE_OF[p["id"]]

        if len(groups) >= 2 and not probs and not is_non_travel and not p.get("duplicate_of"):
            p["status"] = "published"
            p["reviewed_at"] = TODAY
            p["approved_at"] = TODAY
        else:
            p["status"] = "draft"
            p.pop("reviewed_at", None)
            p.pop("approved_at", None)

    (DATA_DIR / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")

    # 4. Ensure barrier-free cache is complete and merge KorWithService2 barrier-free facts into published places
    ensure_barrier_free_cache(site, places)
    bf_stats = run_barrier_free(DATA_DIR, max_calls=500, offline=True)

    # 5. Reload places after barrier-free merge and finalize summaries, FAQs, tier, and counts
    places = json.loads((DATA_DIR / "places.json").read_text("utf-8"))
    published_cnt = 0
    full_cnt = 0
    draft_cnt = 0
    by_kind: dict[str, dict[str, int]] = {}

    for p in places:
        p["themes"] = assign_themes(p)
        summary, faqs = build_summary_and_faq(p, city)
        p["summary"] = summary
        p["faq"] = faqs

        groups = index_groups(p)
        probs = summary_problems(p, city=city)
        is_non_travel = (p.get("category") == "쇼핑" and p["id"] not in ALLOWED_SHOP_IDS) or bool(NON_TRAVEL_RE.search(p.get("name") or ""))
        if p["id"] in DUPLICATE_OF:
            p["duplicate_of"] = DUPLICATE_OF[p["id"]]

        if len(groups) >= 2 and not probs and not is_non_travel and not p.get("duplicate_of"):
            p["status"] = "published"
            p["reviewed_at"] = TODAY
            p["approved_at"] = TODAY
            published_cnt += 1
            if len(groups) >= 3 or (p.get("images") and len(groups) >= 2 and len(faqs) >= 2):
                p["tier"] = "full"
                full_cnt += 1
            else:
                p["tier"] = "basic"
        else:
            p["status"] = "draft"
            p["tier"] = "basic"
            p.pop("reviewed_at", None)
            p.pop("approved_at", None)
            draft_cnt += 1

        k = p["kind"]
        st = p["status"]
        by_kind.setdefault(k, {"published": 0, "draft": 0, "full": 0})
        by_kind[k][st] = by_kind[k].get(st, 0) + 1
        if p.get("tier") == "full":
            by_kind[k]["full"] += 1

    # 6. Recompute nearby now that published places are set
    nearby_cnt = compute_nearby(places, TODAY)

    (DATA_DIR / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    sync_vercel_redirects(places)

    # 7. Build events.json
    events = build_events(places)

    print(
        json.dumps(
            {
                "total": len(places),
                "published": published_cnt,
                "full": full_cnt,
                "draft": draft_cnt,
                "kakao_enriched": kakao_cnt,
                "nearby_pages": nearby_cnt,
                "by_kind": by_kind,
                "barrier_free": bf_stats,
                "events": len(events),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
