"""Fetch Kakao Map search and panel3 detail responses for Suwon places into data/cache/kakao/."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.enrich import haversine_m

DATA_DIR = ROOT / "data" / "suwon"
CACHE_KAKAO = ROOT / "data" / "cache" / "kakao"

NON_TRAVEL_SHOP_RE = re.compile(
    r"(ABC마트|CC콜렉트|Lee\s|MLB|MUJI|SJSJ|갤럭시아울렛|골든듀|금강제화|기비앤키이스|"
    r"나이스클랍|나이키|내셔널지오그래픽|네파|노브랜드|노스페이스|뉴발란스|닥스|데상트|"
    r"듀엘|디스커버리|라코스테|레노마|록시땅|롯데마트|롯데하이마트|르쿠르제|리스트|"
    r"마에스트로|마이쉘|마인드브릿지|만다리나덕|메트로시티|모조에스핀|미샤|미쏘|"
    r"바나바나|바디프랜드|발렌시아|배럴|베네통|보브|비비안|비이커|빈폴|사만사타바사|"
    r"살로몬|샘소나이트|쌤소나이트|세라|세이코|소다|솔트앤초콜릿|쉬즈미스|슈콤마보니|"
    r"스노우피크|스케쳐스|스톤헨지|스파오|시슬리|시스템|신세계백화점.*점$|써스데이아일랜드|"
    r"아가타|아디다스|아이더|아카이브앱크|아트박스|안다르|알레르망|언더아머|에고이스트|"
    r"에스콰이아|에잇세컨즈|엔비룩|엘르|엠씨|올리브영|온앤온|와코루|원더플레이스|"
    r"유니클로|이마트|잇미샤|자주|정관장|제옥스|제이에스티나|지오다노|지오송지오|"
    r"지컷|찰스앤키스|챔피온|캘빈클라인|컬럼비아|코오롱스포츠|코치|쿠론|크록스|"
    r"클라이드앤|타미힐피거|탠디|테팔|토리버치|톰보이|투미|트라이엄프|티쏘|파슬|"
    r"판도라|폴로|푸마|프랑코페라로|필라|핏플랍|해지스|헤지스|홈플러스|휠라|^CU\s|"
    r"AK플라자\s*수원점|AK백화점\s*수원점|갤러리아.*광교점|롯데백화점\s*수원점|스타필드\s*수원점|수원타임빌라스점|약국$)"
)


def norm_match_name(s: str) -> str:
    s = re.sub(r"\([^)]*\)", "", s or "")
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"[^0-9a-zA-Z가-힣]", "", s).lower()
    for suf in ("수원본점", "수원점", "행궁본점", "행궁점", "광교점", "인계점", "영통점", "권선점", "장안점", "팔달점", "수원역점", "본점", "여관", "모텔", "펜션", "민박", "스테이", "호텔", "카페"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
        if s.startswith(suf) and len(s) > len(suf):
            s = s[len(suf) :]
    return s


def fetch_search(q: str) -> list[dict]:
    CACHE_KAKAO.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(q.encode("utf-8")).hexdigest()[:16]
    cp = CACHE_KAKAO / f"search-{h}.json"
    if cp.exists():
        try:
            return json.loads(cp.read_text("utf-8"))
        except Exception:
            pass
    url = "https://search.map.kakao.com/mapsearch/map.daum?callback=jQuery&q=" + urllib.parse.quote(q)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://map.kakao.com/"},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
        s = raw[raw.index("(") + 1 : raw.rindex(")")]
        data = json.loads(s)
        items = data.get("place") or []
        cp.write_text(json.dumps(items, ensure_ascii=False), "utf-8")
        return items
    except Exception:
        return []


def fetch_panel3(cid: str) -> dict:
    if not cid:
        return {}
    cp = CACHE_KAKAO / f"panel3-{cid}.json"
    if cp.exists():
        try:
            return json.loads(cp.read_text("utf-8"))
        except Exception:
            pass
    url = f"https://place-api.map.kakao.com/places/panel3/{cid}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://place.map.kakao.com/",
            "pf": "web",
        },
    )
    try:
        raw = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
        data = json.loads(raw)
        cp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return data
    except Exception:
        return {}


def match_place(p: dict) -> str | None:
    name = p.get("name") or ""
    clean_name = re.sub(r"\([^)]*\)", "", name).strip()
    clean_name = re.sub(r"\[[^\]]*\]", "", clean_name).strip()
    addr = (p.get("facts") or {}).get("address") or ""
    geo = p.get("geo") or {}
    lat0, lng0 = geo.get("lat"), geo.get("lng")

    queries = [f"수원 {clean_name}"]
    if clean_name != name:
        queries.append(f"수원 {name}")
    if addr:
        m_road = re.search(r"([가-힣0-9]+(?:대로|로|길)\s*\d+(?:-\d+)?)", addr)
        if m_road:
            queries.append(f"수원 {m_road.group(1)} {clean_name}")
            queries.append(f"수원시 {m_road.group(1)}")

    n_target = norm_match_name(clean_name)
    for q in queries:
        items = fetch_search(q)
        suwon_items = [
            it
            for it in items
            if ("수원" in str(it.get("address") or "") or "수원" in str(it.get("new_address") or ""))
            and not any(bad in str(it.get("name") or "") for bad in ("주차장", "매표소", "정문", "후문", "화장실"))
        ]
        if not suwon_items:
            continue
        for it in suwon_items:
            n_it = norm_match_name(str(it.get("name") or ""))
            dist_ok = False
            if lat0 and lng0 and it.get("lat") and it.get("lon"):
                try:
                    d = haversine_m(float(lat0), float(lng0), float(it["lat"]), float(it["lon"]))
                    if d <= 450:
                        dist_ok = True
                except Exception:
                    pass
            if n_target and n_it and (n_target in n_it or n_it in n_target):
                return str(it.get("confirmid") or "")
            if dist_ok and n_target and n_it and (n_target[:2] in n_it or n_it[:2] in n_target):
                return str(it.get("confirmid") or "")
        if "수원시 " in q and lat0 and lng0:
            for it in suwon_items:
                try:
                    d = haversine_m(float(lat0), float(lng0), float(it["lat"]), float(it["lon"]))
                    if d <= 150:
                        return str(it.get("confirmid") or "")
                except Exception:
                    pass
    return None


def extract_panel3_facts(p3: dict, kind: str) -> tuple[dict[str, str], dict]:
    from pipeline.textutil import homepage_url, squash_ws

    facts: dict[str, str] = {}
    meta: dict = {}
    if not p3 or not isinstance(p3, dict):
        return facts, meta

    summary = p3.get("summary") or {}
    cid = str(summary.get("confirm_id") or "")
    if cid:
        meta["kakao_place_id"] = cid
        meta["url"] = f"https://place.map.kakao.com/{cid}"

    pt = summary.get("point") or {}
    if pt.get("lat") and pt.get("lon"):
        try:
            lat, lng = float(pt["lat"]), float(pt["lon"])
            if 37.18 <= lat <= 37.38 and 126.90 <= lng <= 127.15:
                meta["geo"] = {"lat": lat, "lng": lng, "source": "카카오맵"}
        except Exception:
            pass

    phones = summary.get("phone_numbers") or []
    if phones and isinstance(phones, list) and phones[0].get("tel"):
        tel = str(phones[0]["tel"]).strip()
        if tel:
            facts["infocenter"] = tel

    hps = summary.get("homepages") or []
    if hps and isinstance(hps, list):
        hp = homepage_url(str(hps[0]).strip())
        if hp:
            facts["homepage"] = hp

    oh = (p3.get("open_hours") or {}).get("week_from_today") or {}
    wps = oh.get("week_periods") or []
    on_parts = []
    off_parts = []
    for wp in wps:
        days = wp.get("days") or []
        if not days:
            continue
        day_names = [re.sub(r"\([^)]*\)", "", d.get("day_of_the_week_desc") or "").strip() for d in days]
        day_names = [d for d in day_names if d]
        first = days[0]
        if first.get("on_days") and first["on_days"].get("start_end_time_desc"):
            t_desc = first["on_days"]["start_end_time_desc"].strip()
            if len(day_names) == 7:
                on_parts.append(f"매일 {t_desc}")
            elif len(day_names) >= 2:
                on_parts.append(f"{day_names[0]}~{day_names[-1]} {t_desc}")
            elif day_names:
                on_parts.append(f"{day_names[0]} {t_desc}")
            else:
                on_parts.append(t_desc)
        elif first.get("off_days_desc"):
            off_desc = first["off_days_desc"].strip()
            if day_names:
                off_parts.append(f"매주 {', '.join(day_names)}요일 {off_desc}")
    unique_times = list(dict.fromkeys(re.sub(r"^[가-힣~,\s]+\s+", "", p) for p in on_parts))
    if len(unique_times) == 1 and unique_times[0]:
        facts["usetime"] = unique_times[0]
    elif on_parts:
        facts["usetime"] = " / ".join(dict.fromkeys(on_parts[:2]))
    if off_parts:
        facts["restdate"] = ", ".join(dict.fromkeys(off_parts))
    elif on_parts and not off_parts:
        facts["restdate"] = "연중무휴"

    if kind == "food":
        items = ((p3.get("menu") or {}).get("menus") or {}).get("items") or []
        menu_strs = []
        for it in items:
            nm = squash_ws(str(it.get("name") or ""))
            pr = it.get("price")
            if not nm:
                continue
            if isinstance(pr, int) and pr > 0:
                menu_strs.append(f"{nm} {pr:,}원")
            else:
                menu_strs.append(nm)
        if menu_strs:
            facts["menu"] = menu_strs[0]
            if len(menu_strs) > 1:
                facts["treatmenu"] = ", ".join(menu_strs[:6])

    pai = p3.get("place_add_info") or {}
    spi = pai.get("simple_parking_infos") or {}
    if spi.get("summary"):
        facts["parking"] = squash_ws(str(spi["summary"]))
    elif spi.get("texts"):
        facts["parking"] = ", ".join(squash_ws(str(x)) for x in spi["texts"] if squash_ws(str(x)))
    else:
        navs = p3.get("navi_guides") or []
        if any(n.get("type") == "PARKING" or "주차" in str(n.get("name") or "") for n in navs):
            facts["parking"] = "주차 가능"

    if kind == "stay":
        sdi = pai.get("simple_detail_infos") or []
        facs = [squash_ws(str(x.get("text") or "")) for x in sdi if squash_ws(str(x.get("text") or ""))]
        if facs and "subfacility" not in facts:
            facts["subfacility"] = "·".join(facs[:5])
        if any("반려" in f or "애견" in f for f in facs) and "pet" not in facts:
            facts["pet"] = "반려동물 동반 가능"
        stores = (p3.get("available_rooms") or {}).get("stores") or []
        if stores and isinstance(stores, list):
            rooms = stores[0].get("rooms") or []
            if rooms:
                facts.setdefault("roomcount", f"{len(rooms)}실")
                r0 = rooms[0]
                if r0.get("check_in"):
                    facts.setdefault("checkin", str(r0["check_in"]))
                if r0.get("check_out"):
                    facts.setdefault("checkout", str(r0["check_out"]))

    return facts, meta


def process_one(p: dict) -> tuple[str, str | None, bool]:
    cid = match_place(p)
    if not cid:
        return p["id"], None, False
    p3 = fetch_panel3(cid)
    return p["id"], cid, bool(p3 and p3.get("summary"))


def main() -> int:
    places = json.loads((DATA_DIR / "places.json").read_text("utf-8"))
    targets = [
        p
        for p in places
        if not (p.get("category") == "쇼핑" and NON_TRAVEL_SHOP_RE.search(p.get("name") or ""))
    ]
    print(f"Fetching Kakao Map search & panel3 for {len(targets)} Suwon travel places...")
    matched = 0
    with_p3 = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(process_one, p) for p in targets]
        for fut in as_completed(futs):
            pid, cid, ok = fut.result()
            if cid:
                matched += 1
            if ok:
                with_p3 += 1
    print(f"Done: targets={len(targets)}, matched={matched}, panel3_ok={with_p3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
