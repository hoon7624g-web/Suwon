"""수원 시설 공식 페이지(수원문화재단·수원시립미술관·수원시 박물관·수원수목원·국립농업박물관·플라잉수원)의 표 값 병합.

    python tools/suwon_official.py --data data/suwon            # 미리 보기: 무엇이 더해지고 겹치는지 출력
    python tools/suwon_official.py --data data/suwon --apply    # places.json에 반영

규칙(CLAUDE.md 3절 1~3항):
- 값은 OFFICIAL_PAGES에 적은 페이지에서 사람이 읽은 표 값(이용시간·쉬는 날·요금·주차 요금·전화·반려동물·예약)뿐이다.
  페이지마다 주소(url)와 읽은 날(checked_at)을 남기고, 읽은 줄은 data/raw/suwon/official_pages.json에 둔다
  (tests/test_official_pages.py가 값의 숫자·낱말이 그 줄에 있는지 본다). 원문 설명 문장은 옮기지 않는다.
- 실행마다 이 도구가 넣은 값(OFFICIAL_PAGES의 출처)을 먼저 걷어 내고 다시 병합한다. 페이지에서 빠진 값은 남지 않는다.
- TourAPI 값과 같으면 그 값의 confirmed_by·confirmed_urls에 페이지를 적고, 다르면 둘 다 남긴다(fact_alternatives,
  화면은 '출처마다 다름 · 방문 전 전화 확인'). 한쪽을 고르지 않는다.
- 이름만 보고 기본값(연중무휴·무료·상시 개방·인근 공영주차장 등)을 짓지 않는다. 페이지에 없는 장소·값은 넣지 않는다.
- 공개(status·reviewed_at·approved_at)는 쓰지 않는다(사람이 정한다, 3절 7항).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.city import of as city_of
from pipeline.textutil import squash_ws
from tools.tourapi_details import merge_facts

CHECKED = "2026-10-26"
SWCF_GUIDE = "https://www.swcf.or.kr/?p=65"
SWCF_PARKING = "https://www.swcf.or.kr/?p=69"
SWCF_OCHAE = "https://www.swcf.or.kr/?p=74&listGubun=list&page=1&viewMode=view&idx=74"
SWCF_XR = "https://www.swcf.or.kr/?p=74&listGubun=list&page=1&viewMode=view&idx=222"
SWCF_FLY = "https://www.swcf.or.kr/?p=74&listGubun=list&page=1&viewMode=view&idx=93"
FLY = "https://www.flyingsuwon.com/"
SUMA = "https://suma.suwon.go.kr/views/info.do"
HS = "https://smuseum.suwon.go.kr/hs/contents/view?contentsNo=129&menuLevel=3&menuNo=110"
SW = "https://smuseum.suwon.go.kr/sw/contents/view?contentsNo=100&menuLevel=2&menuNo=53"
GG = "https://smuseum.suwon.go.kr/gg/contents/view?contentsNo=151&menuLevel=2&menuNo=114"
IWARBOR = "https://www.suwon.go.kr/sw-www/sw-iwarbor/sw-iwarbor-02/sw-iwarbor-02-01/sw-iwarbor-02-01-01.jsp"
YHARBOR = "https://www.suwon.go.kr/sw-www/sw-yharbor/sw-yharbor-02/sw-yharbor-02-01/sw-yharbor-02-01-01.jsp"
NAMUK = "https://www.namuk.or.kr/kr/530/subview.do"

NO_PET_GUIDE = "반려동물 동반 입장 불가(장애인 보조견 제외)"
# One page of a provider: {provider, url, checked_at, places: [{id, name, facts: {key: value}, confirms: [keys]}]}.
#   facts:    values as the page's table states them (a differing stored value stays next to it — both shown)
#   confirms: stored values (TourAPI) the page states the same way, recorded as confirmed by the page
#   differ:   facts the merger would read as the stored value although the page states them otherwise (a year-round
#             '09:00~18:00' against TourAPI's 하절기/동절기 table) — both are shown
OFFICIAL_PAGES = [
    {"provider": "수원문화재단 수원화성관광 관람안내", "url": SWCF_GUIDE, "checked_at": CHECKED, "places": [
        {"id": "tourapi-125555", "name": "수원 화성", "confirms": ["usetime", "restdate", "usefee"]},
        {"id": "tourapi-129437", "name": "화성행궁", "confirms": ["restdate", "usefee"], "differ": ["usetime"],
         "facts": {"usetime": "09:00~18:00 (입장마감은 관람시간 1시간 전)", "pet": NO_PET_GUIDE}},
        {"id": "tourapi-736662", "name": "수원 화령전", "confirms": ["usefee"]},
        {"id": "tourapi-264402", "name": "화성어차", "confirms": ["usefee"]},
        {"id": "tourapi-3494623", "name": "XR버스 1795행", "confirms": ["usefee"]},
    ]},
    {"provider": "수원문화재단 수원화성관광 주차안내", "url": SWCF_PARKING, "checked_at": CHECKED, "places": [
        {"id": "tourapi-129437", "name": "화성행궁", "facts": {
            "parkingfee": "화성행궁 주차장(행궁로 18): 24시간 운영(카드결제 전용), 소형 최초 30분 900원 · 10분마다 400원 · "
                          "1일 주차권 14,000원, 대형차량 주차 불가(연무대 주차장 이용)"}},
    ]},
    {"provider": "수원문화재단 화성어차 상세안내", "url": SWCF_OCHAE, "checked_at": CHECKED, "places": [
        {"id": "tourapi-264402", "name": "화성어차", "confirms": ["usetime", "restdate", "usefee"], "facts": {
            "infocenter": "연무대 매표소 031-5191-4686 / 수원문화재단 관광운영팀 031-290-3634",
            "reservation": "총 36석 — 온라인예매 36석(다음 달 말일까지), 현장예매 잔여석(당일 매표소 판매)",
            "pet": "반려동물 탑승 불가(시각장애인 보조견·안내견은 탑승 가능)"}},
    ]},
    {"provider": "수원문화재단 XR버스 1795행 상세안내", "url": SWCF_XR, "checked_at": CHECKED, "places": [
        {"id": "tourapi-3494623", "name": "XR버스 1795행", "confirms": ["usetime", "restdate", "usefee"], "facts": {
            "infocenter": "수원시 관광과 031-5191-2190 / 수원문화재단 관광운영팀 031-290-3636",
            "reservation": "'터치수원' 앱으로만 예약(탑승 시 QR 체크인)"}},
    ]},
    {"provider": "플라잉수원 홈페이지", "url": FLY, "checked_at": CHECKED, "places": [
        {"id": "tourapi-2714220", "name": "플라잉 수원", "confirms": ["usetime", "infocenter"], "facts": {
            "usefee": "성인 24,000원 · 중고등학생 22,000원 · 초등학생 20,000원 · 25개월~유치원 15,000원, "
                      "장애인(4급이상)·국가유공자(4급이상)·경로(만65세이상) 20,000원"}},
    ]},
    {"provider": "수원문화재단 플라잉 수원 상세안내", "url": SWCF_FLY, "checked_at": CHECKED, "places": [
        {"id": "tourapi-2714220", "name": "플라잉 수원", "differ": ["usetime", "usefee"], "facts": {
            "usetime": "평일 12:30~21:30 (마지막비행 21:00), 주말 및 공휴일 11:00~22:00 (마지막비행 21:30)",
            "usefee": "성인 24,000원 · 청소년 22,000원 · 초등학생 20,000원 · 25개월~유치원 18,000원, "
                      "장애인(4급이상)·국가유공자(4급이상)·경로(만65세이상) 20,000원"}},
    ]},
    {"provider": "수원시립미술관 관람안내", "url": SUMA, "checked_at": CHECKED, "places": [
        {"id": "tourapi-2033483", "name": "수원시립미술관", "confirms": ["usetime", "restdate", "usefee", "infocenter"]},
    ]},
    {"provider": "수원화성박물관 관람안내", "url": HS, "checked_at": CHECKED, "places": [
        {"id": "tourapi-1921150", "name": "수원화성박물관", "confirms": ["usetime", "restdate", "usefee"],
         "facts": {"pet": "안내견 외 애완동물 출입 금지"}},
    ]},
    {"provider": "수원박물관 관람안내", "url": SW, "checked_at": CHECKED, "places": [
        {"id": "tourapi-638913", "name": "수원박물관", "confirms": ["usetime", "restdate", "infocenter"],
         "facts": {"parkingfee": "무료"}},
    ]},
    {"provider": "수원광교박물관 관람안내", "url": GG, "checked_at": CHECKED, "places": [
        {"id": "tourapi-2379222", "name": "수원광교박물관", "confirms": ["usetime", "restdate"],
         "facts": {"infocenter": "031-5191-4175"}},
    ]},
    {"provider": "일월수목원 관람안내", "url": IWARBOR, "checked_at": CHECKED, "places": [
        {"id": "tourapi-3076051", "name": "일월수목원", "confirms": ["usetime", "restdate"], "facts": {"pet": NO_PET_GUIDE}},
    ]},
    {"provider": "영흥수목원 관람안내", "url": YHARBOR, "checked_at": CHECKED, "places": [
        {"id": "tourapi-2998800", "name": "영흥수목원", "confirms": ["usetime", "restdate"], "facts": {"pet": NO_PET_GUIDE}},
    ]},
    {"provider": "국립농업박물관 관람안내", "url": NAMUK, "checked_at": CHECKED, "places": [
        {"id": "tourapi-2944481", "name": "국립농업박물관", "confirms": ["usetime", "restdate", "usefee"]},
    ]},
]
OURS = {pg["provider"] for pg in OFFICIAL_PAGES}


def _entry_provider(entry: str) -> str:
    return re.sub(r"\s+\d{4}-\d{2}-\d{2}$", "", entry.strip())


def strip_official(place: dict) -> None:
    """Take out every value this tool merged (the OFFICIAL_PAGES providers) so a run rebuilds them from the pages."""
    facts = place.get("facts") or {}
    sources = place.get("fact_sources") or {}
    alts = place.get("fact_alternatives") or {}
    for key in list(facts):
        if (sources.get(key) or {}).get("provider") not in OURS:
            continue
        other = next((a for a in alts.get(key, []) if a.get("provider") not in OURS), None)
        if other:  # another source's value moves up into the field
            facts[key] = other["value"]
            sources[key] = {k: v for k, v in other.items() if k not in ("value", "relation")}
            alts[key] = [a for a in alts[key] if a is not other]
        else:
            facts.pop(key)
            sources.pop(key, None)
    for src in sources.values():
        kept = [e for e in str(src.get("confirmed_by") or "").split(" · ") if e.strip() and _entry_provider(e) not in OURS]
        if kept:
            src["confirmed_by"] = " · ".join(kept)
        else:
            src.pop("confirmed_by", None)
        urls = {p: u for p, u in (src.get("confirmed_urls") or {}).items() if p not in OURS}
        if urls:
            src["confirmed_urls"] = urls
        else:
            src.pop("confirmed_urls", None)
    for key in list(alts):
        alts[key] = [a for a in alts[key] if a.get("provider") not in OURS]
        if not alts[key]:
            alts.pop(key)
    if "fact_alternatives" in place and not place["fact_alternatives"]:
        place.pop("fact_alternatives")


def _alt_of(place: dict, key: str, provider: str) -> dict | None:
    return next((a for a in reversed((place.get("fact_alternatives") or {}).get(key, []))
                 if a.get("provider") == provider), None)


def merge_page(place: dict, facts: dict, provider: str, url: str, checked: str, city, confirms=(), differ=()) -> dict:
    """merge_facts for one page, recording the page on every value it adds, confirms or puts beside another."""
    sources = place.setdefault("fact_sources", {})
    stored = place.setdefault("facts", {})
    apart = {k for k in differ if stored.get(k) and facts.get(k) and squash_ws(stored[k]) != squash_ws(facts[k])}
    res = merge_facts(place, {k: v for k, v in facts.items() if k not in apart}, checked, "", provider=provider,
                      city=city)
    alts = place.setdefault("fact_alternatives", {})
    out = {k: list(v) for k, v in res.items()}
    for k in res["added"]:
        sources[k]["url"] = url
        sources[k].pop("contentid", None)
    for k in res["conflicts"] + res["also"]:
        new = _alt_of(place, k, provider)
        if new is not None:
            new["url"] = url
            new.pop("contentid", None)
    for k in res["confirmed"]:
        sources[k].setdefault("confirmed_urls", {})[provider] = url
    for k in apart:
        alts[k] = [a for a in alts.get(k, []) if a.get("provider") != provider]
        alts[k].append({"value": facts[k], "provider": provider, "checked_at": checked, "url": url})
        out["conflicts"].append(k)
    for k in confirms:
        src = sources.get(k)
        if not stored.get(k):
            continue
        if src is None:
            base = place.get("facts_source") or {}
            src = sources[k] = {x: base[x] for x in ("provider", "checked_at", "url", "contentid") if base.get(x)}
        if src.get("provider") == provider:
            continue
        prev = src.get("confirmed_by") or ""
        if provider not in [_entry_provider(e) for e in prev.split(" · ")]:
            src["confirmed_by"] = " · ".join(x for x in (prev, f"{provider} {checked}") if x)
        src.setdefault("confirmed_urls", {})[provider] = url
        out["confirmed"].append(k)
    if not place.get("fact_alternatives"):
        place.pop("fact_alternatives", None)
    return out


def run(data: Path, apply: bool) -> dict:
    site = json.loads((data / "site.json").read_text("utf-8"))
    city = city_of(site)
    path = data / "places.json"
    places = json.loads(path.read_text("utf-8"))
    by_id = {p["id"]: p for p in places}
    for p in places:
        strip_official(p)
    report = {"pages": len(OFFICIAL_PAGES), "missing": [], "places": {}}
    for page in OFFICIAL_PAGES:
        for item in page["places"]:
            p = by_id.get(item["id"])
            if not p or p.get("name") != item["name"]:
                report["missing"].append(f"{item['id']} {item['name']}")
                continue
            res = merge_page(p, item.get("facts") or {}, page["provider"], page["url"], page["checked_at"], city,
                             confirms=item.get("confirms") or (), differ=item.get("differ") or ())
            row = report["places"].setdefault(p["name"], {})
            for k, v in res.items():
                if v:
                    row.setdefault(k, []).extend(f"{x} ({page['provider']})" for x in v)
    if apply:
        path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True, help="도시 데이터 폴더(예: data/suwon)")
    ap.add_argument("--apply", action="store_true", help="places.json에 쓴다(없으면 미리 보기)")
    a = ap.parse_args(argv)
    rep = run(a.data, a.apply)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 1 if rep["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
