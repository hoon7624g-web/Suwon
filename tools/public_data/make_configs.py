"""사이트 설정 만들기 — config/<slug>.json(나중에 그 사이트 site.json의 'public_data' 묶음으로 옮길 값)을 SITES 표와
계산한 값(조석 지점)으로 쓴다(2026-11-05). TAGO의 routes·names·discovered는 tools/tago.py discover가 채우므로, 이미 있는
설정 파일의 그 값은 그대로 둔다.

    python tools/make_configs.py            # config/*.json 쓰기(있는 파일은 tago 짝을 지키고 나머지를 다시 씀)

값의 근거(2026-11-05 확인)
- mois_groups: 인허가 응답의 OPN_ATMY_GRP_CD(gunsan docs/handover/upgrade_20sites_2026-11-05.md 4절, 춘천 응답에 섞인
  3150000 1건은 버림).
- tourapi_area: 연관 관광지·집중률이 답한 areaCd/signguCd(같은 문서 4절, potential.json admin_used). signgu 이름은 두 서비스와
  DataLab 응답의 signguNm. 전남 3곳은 집중률이 없다(crowd false).
- datalab: DataLab 응답의 코드·이름(전남 3곳은 2026-06-30까지 46xxx, 2026-07-01부터 12xxx — 둘 다).
- sun_location: 천문연 출몰시각이 이름으로 답한 지점(종로는 '서울').
- tide_stations: cache/tide_stations.json(포털 활용가이드 예보지점 166곳의 응답 좌표) 가운데 사이트의 바닷가 장소
  (COAST_RX에 맞는 이름, 좌표 있음, 중복·제외 아님)에서 TIDE_KM 안의 지점. 어느 바닷가 장소에 가장 가까운 지점을 먼저,
  나머지는 거리순.
- beaches: 해수욕장정보 응답의 sido_nm·gugun_nm.
- ferry: 2026-11-04(수)·2026-08-01(토) 운항상태 전국 행의 기항지명. island_places는 기항지명과 장소 이름·주소를 보고 맞춘 것
  (섬 자체 또는 그 섬·항의 선착장·여객선터미널 장소). 강릉·부산·속초·경주는 두 날 모두 항로가 없다.
- tago: TAGO 목록(cache/tago_lists.json)의 ID. home은 그 도시의 역·터미널·공항, candidates는 전국 주요 역·터미널·공항과
  (시외버스) 같은 시도의 터미널. home_keys는 그 사이트 엔진이 읽는 열쇠(pipeline/timetables.py).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, CONFIG_DIR, metres  # noqa: E402

COAST_RX = re.compile(r"해수욕장|해변|해안|항$|항구|포구|선착장|여객선|등대|방파제|갯벌|어촌체험|해녀")
TIDE_KM = 30
NO_2027_SUN = ("yongin", "danyang", "gapyeong")

TRAIN_MAJOR = ["NAT010000", "NAT010032", "NAT130126", "NAT010091", "NATH30000", "NAT010415", "NATH10219", "NATH10960",
               "NAT050044", "NAT011668", "NAT030057", "NAT013271", "NAT014445", "NATH13717", "NATH13421", "NAT8B0351",
               "NAT031857", "NAT032563", "NAT041993", "NAT041595", "NAT040257", "NAT030879", "NAT601936", "NAT020947",
               "NAT022558", "NAT881014", "NAT880281", "NAT880345", "NAT140873", "NAT021549", "NAT022188", "NATH12383",
               "NAT601485"]
EXP_MAJOR = ["NAEK010", "NAEK020", "NAEK021", "NAEK030", "NAEK050", "NAEK100", "NAEK105", "NAEK117", "NAEK110", "NAEK120",
             "NAEK150", "NAEK300", "NAEK360", "NAEK310", "NAEK400", "NAEK352", "NAEK800", "NAEK805", "NAEK700", "NAEK703",
             "NAEK715", "NAEK815", "NAEK830", "NAEK710", "NAEK705", "NAEK720", "NAEK735", "NAEK500", "NAEK600", "NAEK615",
             "NAEK610", "NAEK505", "NAEK510", "NAEK515", "NAEK200", "NAEK230", "NAEK240", "NAEK250", "NAEK840", "NAEK835",
             "NAEK450", "NAEK420", "NAEK210", "NAEK220", "NAEK270", "NAEK595", "NAEK575", "NAEK730", "NAEK732", "NAEK460",
             # 한 터미널의 다른 ID(동대구 801~808·대전복합 301·동서울 031~035·성남 121·전주 601~604) — 노선이 ID마다 나뉘어 있다
             "NAEK801", "NAEK802", "NAEK803", "NAEK804", "NAEK806", "NAEK808", "NAEK301", "NAEK031", "NAEK032", "NAEK035",
             "NAEK121", "NAEK601", "NAEK602", "NAEK603", "NAEK604"]
SUB_MAJOR = ["NAI0511601", "NAI0671801", "NAI0654501", "NAI0215101", "NAI0750501", "NAI2224201", "NAI2238202", "NAI1349701",
             "NAI1658501", "NAI1706301", "NAI1454501", "NAI1529901", "NAI1045001", "NAI1174901", "NAI1791901", "NAI1737301",
             "NAI1263101", "NAI2443501", "NAI2638201", "NAI2551901", "NAI2482701", "NAI2592901", "NAI2600701", "NAI2839701",
             "NAI2736001", "NAI2716501", "NAI2701101", "NAI3112001", "NAI3015401", "NAI3258501", "NAI3455101", "NAI3417501",
             "NAI3663601", "NAI3607801", "NAI3776001", "NAI3815701", "NAI3923301", "NAI4124601", "NAI4248201", "NAI4472001",
             "NAI4620401", "NAI4696901", "NAI5139301", "NAI5135601", "NAI5275901", "NAI5302001", "NAI5325101", "NAI5093801",
             "NAI5403701", "NAI5467401", "NAI5493301", "NAI5576001", "NAI5615801", "NAI6193701", "NAI5864201", "NAI5796001",
             "NAI5971501", "NAI5903801", "NAI5911401", "NAI5892201"]
AIRPORTS = ["NAARKJJ", "NAARKJK", "NAARKSS", "NAARKPK", "NAARKTN", "NAARKJB", "NAARKPS", "NAARKNY", "NAARKJY", "NAARKPU",
            "NAARKNW", "NAARKSI", "NAARKPC", "NAARKTU", "NAARKTH"]

JN = ["전남광주통합특별시", "전라남도", "전남"]
SITES = {
    "daegu": {
        "repo": "/home/user/Daegu", "region": {"name": "대구광역시", "short": "대구", "address_prefixes": ["대구광역시", "대구시", "대구"],
                                              "groups_label": "대구광역시 9개 구·군", "hygiene_prefix": "대구 "},
        "mois_groups": {"3410000": "중구", "3420000": "동구", "3430000": "서구", "3440000": "남구", "3450000": "북구",
                        "3460000": "수성구", "3470000": "달서구", "3480000": "달성군", "5141000": "군위군"},
        "area": {"area_cd": "27", "level": "area", "area_names": ["대구광역시"],
                 "signgu": {"27110": "중구", "27140": "동구", "27170": "서구", "27200": "남구", "27230": "북구",
                            "27260": "수성구", "27290": "달서구", "27710": "달성군", "27720": "군위군"}},
        "datalab": {"level": "metco", "codes": ["27"], "names": ["대구광역시"], "name": "대구광역시"},
        "sun": "대구",
        "tago": {"train": ["NAT013271", "NAT013239", "NAT013189"], "express_bus": ["NAEK800", "NAEK801", "NAEK802", "NAEK803", "NAEK804", "NAEK806", "NAEK808", "NAEK805"],
                 "intercity_bus": ["NAI4124601", "NAI4248201"], "flight": ["NAARKTN"]},
        "provinces": ["대구광역시", "경상북도"], "home_keys": ["home", "homes_by_mode"]},
    "haenam": {
        "repo": "/home/user/haenam", "region": {"name": "해남군", "short": "해남", "address_prefixes": JN, "city_names": ["해남군"],
                                               "name_suffixes": ["군"], "hygiene_prefix": "전남 해남군"},
        "mois_groups": {"5870000": "해남군"},
        "area": {"area_cd": "12", "level": "signgu", "signgu": {"12790": "해남군"}, "crowd": False},
        "datalab": {"level": "locgo", "codes": ["12790", "46820"], "names": ["해남군"], "name": "해남군"},
        "sun": "해남", "coastal": True, "beaches": {"sido": "전남", "gugun": ["해남군"]},
        "ferry": {"ports": ["땅끝", "우수영"], "island_places": {"땅끝": ["tourapi-2778520"]}, "label": "해남군"},
        "tago": {"train": ["NAT470312"], "express_bus": ["NAEK595"], "intercity_bus": ["NAI5903801", "NAI5906502"]},
        "provinces": ["전라남도"]},
    "sejong": {
        "repo": "/home/user/sejong", "region": {"name": "세종특별자치시", "short": "세종", "address_prefixes": ["세종특별자치시", "세종시", "세종"],
                                               "name_suffixes": ["시", "특별자치시"], "hygiene_prefix": "세종 "},
        "mois_groups": {"5690000": "세종특별자치시"},
        "area": {"area_cd": "36", "level": "area", "area_names": ["세종특별자치시"], "signgu": {"36110": "세종특별자치시"}},
        "datalab": {"level": "metco", "codes": ["36"], "names": ["세종특별자치시"], "name": "세종특별자치시"},
        "sun": "세종",
        "tago": {"train": ["NAT011298", "NAT050044"], "express_bus": ["NAEK352", "NAEK350"],
                 "intercity_bus": ["NAI3015401", "NAI3002601"], "flight": ["NAARKTU"]},
        "provinces": ["세종특별자치시"], "home_keys": ["home"],
        "tago_notes": ["오송역(충청북도 청주시)과 청주국제공항은 세종 밖이지만 세종을 오가는 KTX·항공편이 서는 곳이라 넣었다."]},
    "yeongju": {
        "repo": "/home/user/yeougju", "region": {"name": "영주시", "short": "영주", "address_prefixes": ["경상북도", "경북"],
                                                "city_names": ["영주시"], "hygiene_prefix": "경북 영주시"},
        "mois_groups": {"5090000": "영주시"},
        "area": {"area_cd": "47", "level": "signgu", "signgu": {"47210": "영주시"}},
        "datalab": {"level": "locgo", "codes": ["47210"], "names": ["영주시"], "name": "영주시"},
        "sun": "영주",
        "tago": {"train": ["NAT022188", "NAT022053"], "express_bus": ["NAEK835", "NAEK834"], "intercity_bus": ["NAI3607801"]},
        "provinces": ["경상북도"], "home_keys": ["home"]},
    "gangneung": {
        "repo": "/home/user/gangneung", "region": {"name": "강릉시", "short": "강릉", "address_prefixes": ["강원특별자치도", "강원도", "강원"],
                                                  "city_names": ["강릉시"], "hygiene_prefix": "강원 강릉시"},
        "mois_groups": {"4201000": "강릉시"},
        "area": {"area_cd": "51", "level": "signgu", "signgu": {"51150": "강릉시"}},
        "datalab": {"level": "locgo", "codes": ["51150"], "names": ["강릉시"], "name": "강릉시"},
        "sun": "강릉", "coastal": True, "beaches": {"sido": "강원", "gugun": ["강릉시"]},
        "ferry": {"ports": ["강릉", "안목", "주문진"], "island_places": {}, "label": "강릉시"},
        "tago": {"train": ["NAT601936", "NAT601774"], "express_bus": ["NAEK200"], "intercity_bus": ["NAI2551901"],
                 "flight": ["NAARKNY"]},
        "provinces": ["강원도"],
        "tago_notes": ["양양국제공항(강원특별자치도 양양군)은 강릉 밖이지만 강릉에 가장 가까운 공항이라 넣었다."]},
    "jeju": {
        "repo": "/home/user/jeju", "region": {"name": "제주특별자치도", "short": "제주", "address_prefixes": ["제주특별자치도", "제주도"],
                                             "city_names": ["제주시", "서귀포시"], "name_suffixes": ["도", "특별자치도", "시"],
                                             "groups_label": "제주특별자치도 제주시·서귀포시", "hygiene_prefix": "제주 "},
        "mois_groups": {"6510000": "제주시", "6520000": "서귀포시"},
        "area": {"area_cd": "50", "level": "area", "area_names": ["제주특별자치도"], "signgu": {"50110": "제주시", "50130": "서귀포시"}},
        "datalab": {"level": "metco", "codes": ["50"], "names": ["제주특별자치도"], "name": "제주특별자치도"},
        "sun": "제주", "sun_far_note": "서귀포·성산·모슬포처럼 제주 지점에서 멀리 떨어진 곳과 추자도·마라도 같은 섬",
        "coastal": True, "beaches": {"sido": "제주", "gugun": []},
        "ferry": {"ports": ["제주", "모슬포", "산이수동", "가파도", "마라도 살레덕", "하추자도", "상추자도"],
                  "island_places": {"제주": ["tourapi-2791511"], "모슬포": ["tourapi-2781327"], "가파도": ["tourapi-126446"],
                                    "마라도 살레덕": ["tourapi-126450"], "하추자도": ["tourapi-127863"],
                                    "상추자도": ["tourapi-127863", "tourapi-3557958"]},
                  "label": "제주특별자치도"},
        "tago": {"flight": ["NAARKPC"]}, "provinces": []},
    "yeosu": {
        "repo": "/home/user/yeosu", "region": {"name": "여수시", "short": "여수", "address_prefixes": JN, "city_names": ["여수시"],
                                              "hygiene_prefix": "전남 여수시"},
        "mois_groups": {"5785000": "여수시"},
        "area": {"area_cd": "12", "level": "signgu", "signgu": {"12130": "여수시"}, "crowd": False},
        "datalab": {"level": "locgo", "codes": ["12130", "46130"], "names": ["여수시"], "name": "여수시"},
        "sun": "여수", "coastal": True, "beaches": {"sido": "전남", "gugun": ["여수시"]},
        "ferry": {"ports": ["여수", "여천", "백야", "신기", "거문", "거문(서도)", "초도(의성)", "손죽", "소거문", "평도", "광도", "서고지",
                            "안도", "역포", "우학", "유송", "개도(화산)", "송고", "자봉", "제도", "함구미", "낭도", "사도", "상화",
                            "하화"],
                  "note": "'추도'는 충남 보령 추도(K12 오천-선촌)와 이름이 같아 기항지 목록에서 뺐다 — 여수 추도는 H04 여수-둔병의 다른 기항지(낭도·사도 등)로 여수 항로가 된다.",
                  "island_places": {"여수": ["tourapi-2752379"], "여천": ["tourapi-2752387"], "백야": ["tourapi-2752556"],
                                    "거문": ["tourapi-126283"], "거문(서도)": ["tourapi-126283"], "초도(의성)": ["tourapi-1528652"],
                                    "손죽": ["tourapi-2024407"], "개도(화산)": ["tourapi-3026607"],
                                    "낭도": ["tourapi-2496315", "tourapi-2752382"], "사도": ["tourapi-126968"],
                                    "하화": ["tourapi-2497099"], "추도": ["tourapi-2607009"]},
                  "label": "여수시"},
        "tago": {"train": ["NAT041993", "NAT041866"], "express_bus": ["NAEK510", "NAEK509"], "intercity_bus": ["NAI5971501"],
                 "flight": ["NAARKJY"]},
        "provinces": ["전라남도"], "home_keys": ["home", "home_stops"]},
    "jeonju": {
        "repo": "/home/user/jeonju", "region": {"name": "전주시", "short": "전주", "address_prefixes": ["전북특별자치도", "전라북도", "전북"],
                                               "city_names": ["전주시"], "hygiene_prefix": "전북 전주시"},
        "mois_groups": {"4641000": "전주시"},
        "area": {"area_cd": "52", "level": "signgu", "signgu": {"52111": "전주시 완산구", "52113": "전주시 덕진구"},
                 "label": "전주시(완산구·덕진구)"},
        "datalab": {"level": "locgo", "codes": ["52110"], "names": ["전주시"], "name": "전주시"},
        "sun": "전주",
        "tago": {"train": ["NAT040257"], "express_bus": ["NAEK600", "NAEK601", "NAEK602", "NAEK603", "NAEK604", "NAEK605"], "intercity_bus": ["NAI5493301"]},
        "provinces": ["전라북도"]},
    "chuncheon": {
        "repo": "/home/user/chuncheon", "region": {"name": "춘천시", "short": "춘천", "address_prefixes": ["강원특별자치도", "강원도", "강원"],
                                                  "city_names": ["춘천시"], "hygiene_prefix": "강원 춘천시"},
        "mois_groups": {"4181000": "춘천시"},
        "area": {"area_cd": "51", "level": "signgu", "signgu": {"51110": "춘천시"}},
        "datalab": {"level": "locgo", "codes": ["51110"], "names": ["춘천시"], "name": "춘천시"},
        "sun": "춘천",
        "tago": {"train": ["NAT140873", "NAT140840"], "express_bus": ["NAEK250"], "intercity_bus": ["NAI2443501"]},
        "provinces": ["강원도"], "train_extra": ["NAT020040"]},
    "yongin": {
        "repo": "/home/user/yongin", "region": {"name": "용인시", "short": "용인", "address_prefixes": ["경기도", "경기"],
                                               "city_names": ["용인시"], "hygiene_prefix": "경기 용인시"},
        "mois_groups": {"4050000": "용인시"},
        "area": {"area_cd": "41", "level": "signgu",
                 "signgu": {"41461": "용인시 처인구", "41463": "용인시 기흥구", "41465": "용인시 수지구"},
                 "label": "용인시(처인구·기흥구·수지구)"},
        "datalab": {"level": "locgo", "codes": ["41460"], "names": ["용인시"], "name": "용인시"},
        "sun": "용인",
        "tago": {"express_bus": ["NAEK150", "NAEK149"], "intercity_bus": ["NAI1706301"]},
        "provinces": ["경기도"]},
    "gyeongju": {
        "repo": "/home/user/gyeongju", "region": {"name": "경주시", "short": "경주", "address_prefixes": ["경상북도", "경북"],
                                                 "city_names": ["경주시"], "hygiene_prefix": "경북 경주시"},
        "mois_groups": {"5050000": "경주시"},
        "area": {"area_cd": "47", "level": "signgu", "signgu": {"47130": "경주시"}},
        "datalab": {"level": "locgo", "codes": ["47130"], "names": ["경주시"], "name": "경주시"},
        "sun": "경주", "coastal": True, "beaches": {"sido": "경북", "gugun": ["경주시"]},
        "ferry": {"ports": ["감포"], "island_places": {}, "label": "경주시"},
        "tago": {"train": ["NATH13421"], "express_bus": ["NAEK815"], "intercity_bus": ["NAI3815701", "NAI3815702"], "flight": ["NAARKTH"]},
        "provinces": ["경상북도"],
        "tago_notes": ["포항경주공항(경상북도 포항시)은 경주 밖이지만 경주에 가장 가까운 공항이라 넣었다."],
        # 경주각 엔진은 transport_tago.json 'notes'를 {수단: 그 수단 아래 문장}으로 읽는다(목록이면 빌드가 멈춘다)
        "tago_extra": {"notes_format": "by_mode", "mode_notes": {
            "train": "열차 요금은 TAGO가 등급 구분 없이 준 값입니다 — 같은 구간이면 무궁화호·새마을호가 같은 값으로 나옵니다. "
                     "등급별 운임은 코레일에서 확인하세요.",
            "flight": "포항경주공항(경상북도 포항시)은 경주 밖이지만 경주에 가장 가까운 공항이라 넣었습니다. 확인 필요: 요금 — "
                      "TAGO 항공 운항정보에는 요금 값이 없습니다(항공사에서 확인)."}}},
    "busan": {
        "repo": "/home/user/busan", "region": {"name": "부산광역시", "short": "부산", "address_prefixes": ["부산광역시", "부산시", "부산"],
                                              "groups_label": "부산광역시 16개 구·군", "hygiene_prefix": "부산 "},
        "mois_groups": {"3250000": "중구", "3260000": "서구", "3270000": "동구", "3280000": "영도구", "3290000": "부산진구",
                        "3300000": "동래구", "3310000": "남구", "3320000": "북구", "3330000": "해운대구", "3340000": "사하구",
                        "3350000": "금정구", "3360000": "강서구", "3370000": "연제구", "3380000": "수영구", "3390000": "사상구",
                        "3400000": "기장군"},
        "area": {"area_cd": "26", "level": "area", "area_names": ["부산광역시"],
                 "signgu": {"26110": "중구", "26140": "서구", "26170": "동구", "26200": "영도구", "26230": "부산진구",
                            "26260": "동래구", "26290": "남구", "26320": "북구", "26350": "해운대구", "26380": "사하구",
                            "26410": "금정구", "26440": "강서구", "26470": "연제구", "26500": "수영구", "26530": "사상구",
                            "26710": "기장군"}},
        "datalab": {"level": "metco", "codes": ["26"], "names": ["부산광역시"], "name": "부산광역시"},
        "sun": "부산", "coastal": True, "beaches": {"sido": "부산", "gugun": []},
        "ferry": {"ports": ["부산", "부산(연안)", "다대포", "가덕"], "island_places": {}, "label": "부산광역시"},
        "tago": {"train": ["NAT014445", "NAT014281", "NAT750046", "NAT750189"], "express_bus": ["NAEK700", "NAEK703"],
                 "intercity_bus": ["NAI4620401", "NAI4696901"], "flight": ["NAARKPK"]},
        "provinces": ["부산광역시", "경상남도"]},
    "suwon": {
        "repo": "/home/user/hoon7624g-web/suwon", "region": {"name": "수원시", "short": "수원", "address_prefixes": ["경기도", "경기"],
                                                            "city_names": ["수원시"], "hygiene_prefix": "경기 수원시"},
        "mois_groups": {"3740000": "수원시"},
        "area": {"area_cd": "41", "level": "signgu",
                 "signgu": {"41111": "수원시 장안구", "41113": "수원시 권선구", "41115": "수원시 팔달구", "41117": "수원시 영통구"},
                 "label": "수원시(장안구·권선구·팔달구·영통구)"},
        "datalab": {"level": "locgo", "codes": ["41110"], "names": ["수원시"], "name": "수원시"},
        "sun": "수원",
        "tago": {"train": ["NAT010415"], "express_bus": ["NAEK110"], "intercity_bus": ["NAI1658501"]},
        "provinces": ["경기도"]},
    "sokcho": {
        "repo": "/home/user/sokcho", "region": {"name": "속초시", "short": "속초", "address_prefixes": ["강원특별자치도", "강원도", "강원"],
                                               "city_names": ["속초시"], "hygiene_prefix": "강원 속초시"},
        "mois_groups": {"4231000": "속초시"},
        "area": {"area_cd": "51", "level": "signgu", "signgu": {"51210": "속초시"}},
        "datalab": {"level": "locgo", "codes": ["51210"], "names": ["속초시"], "name": "속초시"},
        "sun": "속초", "coastal": True, "beaches": {"sido": "강원", "gugun": ["속초시"]},
        "ferry": {"ports": ["속초"], "island_places": {}, "label": "속초시"},
        "tago": {"express_bus": ["NAEK230"], "intercity_bus": ["NAI2482701"], "flight": ["NAARKNY"]},
        "provinces": ["강원도"],
        "tago_notes": ["양양국제공항(강원특별자치도 양양군)은 속초 밖이지만 속초에 가장 가까운 공항이라 넣었다."]},
    "danyang": {
        "repo": "/home/user/danyang", "region": {"name": "단양군", "short": "단양", "address_prefixes": ["충청북도", "충북"],
                                                "city_names": ["단양군"], "name_suffixes": ["군"], "hygiene_prefix": "충북 단양군"},
        "mois_groups": {"4480000": "단양군"},
        "area": {"area_cd": "43", "level": "signgu", "signgu": {"43800": "단양군"}},
        "datalab": {"level": "locgo", "codes": ["43800"], "names": ["단양군"], "name": "단양군"},
        "sun": "단양",
        "tago": {"train": ["NAT021784"], "express_bus": ["NAEK460"], "intercity_bus": ["NAI2701101", "NAI2702001"]},
        "provinces": ["충청북도"]},
    "mokpo": {
        "repo": "/home/user/mokpo", "region": {"name": "목포시", "short": "목포", "address_prefixes": JN, "city_names": ["목포시"],
                                              "hygiene_prefix": "전남 목포시"},
        "mois_groups": {"5780000": "목포시"},
        "area": {"area_cd": "12", "level": "signgu", "signgu": {"12110": "목포시"}, "crowd": False},
        "datalab": {"level": "locgo", "codes": ["12110", "46110"], "names": ["목포시"], "name": "목포시"},
        "sun": "목포", "coastal": True, "beaches": {"sido": "전남", "gugun": ["목포시"]},
        "ferry": {"ports": ["목포", "목포(북항)", "외달", "달리", "율도(목포)", "장좌"],
                  "island_places": {"목포": ["tourapi-2707901"], "목포(북항)": ["tourapi-2784224"], "외달": ["tourapi-128292"]},
                  "label": "목포시"},
        "tago": {"train": ["NAT032563"], "express_bus": ["NAEK505"], "intercity_bus": ["NAI5864201"], "flight": ["NAARKJB"]},
        "provinces": ["전라남도"], "home_keys": ["home", "homes_list"],
        "tago_notes": ["무안국제공항(전남광주통합특별시 무안군)은 목포 밖이지만 목포에 가장 가까운 공항이라 넣었다."]},
    "gapyeong": {
        "repo": "/home/user/gapyeong", "region": {"name": "가평군", "short": "가평", "address_prefixes": ["경기도", "경기"],
                                                 "city_names": ["가평군"], "name_suffixes": ["군"], "hygiene_prefix": "경기 가평군"},
        "mois_groups": {"4160000": "가평군"},
        "area": {"area_cd": "41", "level": "signgu", "signgu": {"41820": "가평군"}},
        "datalab": {"level": "locgo", "codes": ["41820"], "names": ["가평군"], "name": "가평군"},
        "sun": "가평",
        "tago": {"train": ["NAT140576", "NAT140436"], "express_bus": ["NAEK255", "NAEK252"]},
        "provinces": [], "train_extra": ["NAT020040", "NAT140840"]},
    "jongno": {
        "repo": "/home/user/jongno", "region": {"name": "종로구", "short": "종로", "address_prefixes": ["서울특별시", "서울시", "서울"],
                                               "city_names": ["종로구"], "name_suffixes": ["구"], "hygiene_prefix": "서울 종로구"},
        "mois_groups": {"3000000": "종로구"},
        "area": {"area_cd": "11", "level": "signgu", "signgu": {"11110": "종로구"}},
        "datalab": {"level": "locgo", "codes": ["11110"], "names": ["종로구"], "name": "종로구"},
        "sun": "서울", "sun_far_note": "천문연 '서울' 지점(종로구 밖)과 떨어진 곳",
        "tago": {"train": ["NAT010000"], "express_bus": ["NAEK010", "NAEK030", "NAEK031", "NAEK032", "NAEK035"], "intercity_bus": ["NAI0511601"],
                 "flight": ["NAARKSS"]},
        "provinces": [],
        "tago_notes": ["종로구에는 철도역·버스터미널·공항이 없어 종로를 오가는 사람이 쓰는 서울역·서울경부·동서울·김포국제공항을 "
                       "넣었다(모두 종로구 밖)."]},
}


def tide_for(slug: str, places: list[dict], stations: dict) -> tuple[dict, dict]:
    coast = [p for p in places if COAST_RX.search(p.get("name") or "") and (p.get("geo") or {}).get("lat")
             and not p.get("duplicate_of") and not p.get("exclude")]
    pts = [(float(p["geo"]["lat"]), float(p["geo"]["lng"])) for p in coast]
    if not pts:
        return {}, {}
    near = {}
    for code, v in stations.items():
        d = min(metres((v["lat"], v["lng"]), q) for q in pts)
        if d <= TIDE_KM * 1000:
            near[code] = d
    first = {min(stations, key=lambda k: metres((stations[k]["lat"], stations[k]["lng"]), q)) for q in pts}
    first &= set(near)
    order = sorted(near, key=lambda c: (c not in first, near[c]))
    basis = {"rule": f"바닷가 장소(이름이 {COAST_RX.pattern}에 맞고 좌표가 있는 {len(coast)}곳)에서 {TIDE_KM}km 안의 예보지점 — "
                     "어느 바닷가 장소에 가장 가까운 지점을 먼저, 나머지는 거리순",
             "coastal_places": len(coast),
             "distance_km": {c: round(near[c] / 1000, 1) for c in order}}
    return {c: stations[c]["name"] for c in order}, basis


def main() -> int:
    stations = json.loads((CACHE_DIR / "tide_stations.json").read_text("utf-8"))["stations"]
    lists = json.loads((CACHE_DIR / "tago_lists.json").read_text("utf-8"))["lists"]
    sub_by_city: dict[str, list[str]] = {}
    for t in lists["SuburbsBusInfo/GetSuberbsBusTrminlList"]:
        sub_by_city.setdefault(t.get("cityName") or "", []).append(t["terminalId"])
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for slug, s in SITES.items():
        data_dir = Path(s["repo"]) / "data" / slug
        places = json.loads((data_dir / "places.json").read_text("utf-8"))
        path = CONFIG_DIR / f"{slug}.json"
        old = json.loads(path.read_text("utf-8")) if path.is_file() else {}
        old_tago = (old.get("public_data") or {}).get("tago") or {}
        area = dict(s["area"])
        area.setdefault("crowd", True)
        area.setdefault("confirmed", {})
        pd = {"region": s["region"], "mois_groups": s["mois_groups"], "tourapi_area": area, "datalab": s["datalab"],
              "sun_location": s["sun"]}
        if s.get("sun_far_note"):
            pd["sun_far_note"] = s["sun_far_note"]
        if slug in NO_2027_SUN:     # 천문연에 2027년 값이 없는 지점(2026-11-05): 2026-12-31까지
            pd["sun_days"] = 57
            pd["sun_days_note"] = (f"기간이 120일이 아니라 2026-12-31까지 57일인 것은 천문연 출몰시각에 '{s['sun']}' 지점의 "
                                   "2027년 값이 아직 없어서다(2026-11-05 확인 — 2027-01-01·02-10 모두 0건).")
        if s.get("coastal"):
            pd["tide_stations"], pd["tide_basis"] = tide_for(slug, places, stations)
            pd["beaches"] = s["beaches"]
        if s.get("ferry"):
            pd["ferry"] = s["ferry"]
        home = {m: s["tago"].get(m, []) for m in ("train", "express_bus", "intercity_bus", "flight")}
        subs = list(dict.fromkeys(SUB_MAJOR + [i for c in s.get("provinces") or [] for i in sub_by_city.get(c, [])]))
        cands = {"train": TRAIN_MAJOR + list(s.get("train_extra") or []), "express_bus": EXP_MAJOR,
                 "intercity_bus": subs, "flight": AIRPORTS}
        tago = {"home": home, "candidates": {m: [c for c in v if c not in home[m]] for m, v in cands.items()},
                "home_keys": s.get("home_keys") or ["home"], "notes": s.get("tago_notes") or []}
        tago.update(s.get("tago_extra") or {})
        for k in ("routes", "names", "discovered", "check_only"):
            if k in old_tago:
                tago[k] = old_tago[k]
        pd["tago"] = tago
        cfg = {"_about": ("공공데이터 모음 설정 — public_data는 나중에 사이트 site.json의 'public_data' 묶음으로 옮길 값이다 "
                          "(tools/make_configs.py가 쓰고 tools/tago.py discover가 tago.routes·names를 채운다, 2026-11-05)."),
               "slug": slug, "repo": s["repo"], "data_dir": str(data_dir), "public_data": pd}
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(slug, "tide", len(pd.get("tide_stations") or {}), "intercity cands", len(tago["candidates"]["intercity_bus"]),
              "homes", {m: len(v) for m, v in home.items() if v})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
