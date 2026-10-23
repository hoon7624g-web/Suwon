"""The English names table, data/<region>/en/names.json: the name every English page uses and the other versions'
slugs start from (pipeline/en_source._name_table, pipeline/en_site.SlugBook).

    python tools/en_names.py --data data/<city>            # add a row for every place missing (or renamed) there
    python tools/en_names.py --data data/<city> --check    # check only: every place covered, names in Latin script

Rows already in the table are kept as they are: they were written or reviewed by hand (official TourAPI
EngService2 titles kept for the same place, everything else after the MCST guideline for public terms) — except a
row `tools/en_content.py names` left as the plain romanized name (name_en_source 'romanized'), which gets the
guideline name like a new row. The city's own words (its name, districts, mountains, streets: '한빛' -> 'Hanbit') are
site.json `en_name_words` {Korean: English}, never written here (CLAUDE.md 4); the words below are any city's. A new row
— usually a restaurant or a stay added later — gets a rule-made name after the same guideline: the specific part in
Revised Romanization, the generic part of a public place in English (은파호수공원 -> Eunpa Lake Park), a business
name romanized word by word with its generic word as a word of its own (서우식당 -> Seou Sikdang), English words
written in Hangul in English (블루모텔 -> Blue Motel), Latin letters and digits kept as written. Review new rows by
eye: the rules split only the words they know.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.city import of as city_of
from pipeline.en_source import address_en, romanize
from pipeline.romanize import _rr_run

SOURCE = "romanized specific part + English generic (MCST guideline)"
ALLOWED = re.compile(r"^[A-Za-z0-9 \-'()&,.]+$")

# Words the rules know, longest first when they overlap. English words written in Hangul are written in English;
# Korean food and business words stay in Revised Romanization as a word of their own (the Gunsan table's usage).
WORDS = {
    # English in Hangul
    "게스트하우스": "Guesthouse", "클럽하우스": "Clubhouse", "하우스": "House", "모텔": "Motel", "호텔": "Hotel",
    "펜션": "Pension", "리조트": "Resort", "무인텔": "Muintel", "스파텔": "Spatel", "유스호스텔": "Youth Hostel",
    "카페": "Cafe", "커피숍": "Coffee Shop", "커피": "Coffee", "로스터스": "Roasters", "베이커리": "Bakery",
    "치킨": "Chicken", "피자": "Pizza", "호프": "Hof", "가든": "Garden", "파크": "Park", "레스토랑": "Restaurant",
    "뷔페": "Buffet", "스테이크": "Steak", "버거": "Burger", "파스타": "Pasta", "바베큐": "Barbecue", "샐러드": "Salad",
    "그린": "Green", "블루": "Blue", "오션": "Ocean", "비치": "Beach", "스카이": "Sky", "힐링": "Healing",
    "캠핑": "Camping", "스토리": "Story", "센타": "Center", "센터": "Center", "마트": "Mart", "푸드": "Food",
    "키친": "Kitchen", "라이브": "Live", "뉴": "New", "스타": "Star", "타운": "Town", "랜드": "Land",
    "터미널": "Terminal", "군청": "County Office", "구청": "District Office", "콘서트": "Concert",
    "아트": "Art", "갤러리": "Gallery", "뮤지엄": "Museum", "스타디움": "Stadium", "아쿠아리움": "Aquarium",
    "플라자": "Plaza", "스퀘어": "Square", "아이스링크": "Ice Rink", "워터파크": "Water Park", "테마파크": "Theme Park",
    # Korean food and business words, romanized
    "기사식당": "Gisa Sikdang", "정육식당": "Jeongyuk Sikdang", "식육식당": "Sigyuk Sikdang", "식당": "Sikdang",
    "대중음식점": "Daejung Eumsikjeom", "음식점": "Eumsikjeom", "횟집": "Hoetjip", "회집": "Hoejip", "회관": "Hoegwan",
    "회센타": "Hoe Center", "회센터": "Hoe Center", "수산": "Susan", "반점": "Banjeom", "중화요리": "Junghwa Yori",
    "해물짬뽕": "Haemul Jjamppong", "짬뽕": "Jjamppong", "손짜장": "Son Jjajang", "옛날짜장": "Yennal Jjajang",
    "짜장": "Jjajang", "쌈밥": "Ssambap", "보리밥": "Boribap", "해물탕": "Haemultang", "남원추어탕": "Namwon Chueotang",
    "추어탕": "Chueotang", "감자탕": "Gamjatang", "순대국밥": "Sundae Gukbap", "콩나물국밥": "Kongnamul Gukbap",
    "소머리국밥": "Someori Gukbap", "국밥": "Gukbap", "해장국": "Haejangguk", "곰탕": "Gomtang", "왕갈비탕": "Wanggalbitang",
    "갈비탕": "Galbitang", "설렁탕": "Seolleongtang", "영양탕": "Yeongyangtang", "동태탕": "Dongtaetang",
    "짱뚱어탕": "Jjangttungeotang", "염소탕": "Yeomsotang", "육개장": "Yukgaejang", "민물매운탕": "Minmul Maeuntang",
    "매운탕": "Maeuntang", "숯불구이": "Sutbul Gui", "숯불갈비": "Sutbul Galbi", "숯불고기": "Sutbul Gogi",
    "장작구이": "Jangjak Gui", "돼지갈비": "Dwaeji Galbi", "왕갈비": "Wanggalbi", "닭갈비": "Dakgalbi", "갈비": "Galbi",
    "삼겹살": "Samgyeopsal", "한우촌": "Hanuchon", "한우": "Hanu", "장터": "Jangteo", "뚝배기": "Ttukbaegi",
    "통닭": "Tongdak", "촌닭": "Chondak", "족발": "Jokbal", "보쌈": "Bossam", "김밥": "Gimbap", "분식": "Bunsik",
    "떡볶이": "Tteokbokki", "튀김": "Twigim", "바지락칼국수": "Bajirak Kalguksu", "칼국수": "Kalguksu",
    "멸치국수": "Myeolchi Guksu", "국수": "Guksu", "왕만두": "Wangmandu", "손만두": "Sonmandu", "만두": "Mandu",
    "냉면": "Naengmyeon", "메밀": "Memil", "아구찜": "Agujjim", "아구": "Agu", "코다리찜": "Kodarijjim",
    "코다리": "Kodari", "민물장어": "Minmul Jangeo", "장어": "Jangeo", "흑염소": "Heugyeomso", "오리": "Ori",
    "백숙": "Baeksuk", "복집": "Bokjip", "밥집": "Bapjip", "집밥": "Jipbap", "밥상": "Bapsang", "포차": "Pocha",
    "주막": "Jumak", "다방": "Dabang", "한정식": "Hanjeongsik", "휴게소": "Hyugeso", "쉼터": "Swimteo",
    "실비집": "Silbijip", "곱창": "Gopchang", "순대": "Sundae", "순두부": "Sundubu", "돌솥": "Dolsot",
    "쭈꾸미": "Jjukkumi", "오징어": "Ojingeo", "샤브": "Shabu", "마라탕": "Malatang", "양꼬치": "Yangkkochi",
    "꼬치": "Kkochi", "라멘": "Ramen", "덮밥": "Deopbap", "도시락": "Dosirak", "돈까스": "Donkatsu",
    "돈가스": "Donkatsu", "소주방": "Sojubang", "맥주": "Maekju", "술집": "Suljip", "고구마빵": "Gogumappang",
    "빵": "Ppang", "해물": "Haemul", "민박": "Minbak", "한옥민박": "Hanok Minbak", "한옥": "Hanok", "여관": "Yeogwan",
    "여인숙": "Yeoinsuk", "황토": "Hwangto", "본점": "Main Branch", "전문점": "Jeonmunjeom",
}
BASE_WORDS = dict(WORDS)
_MAX = max(len(w) for w in WORDS)


def use_city_words(words: dict | None) -> None:
    """Add the city's words (site.json en_name_words) to WORDS for this run."""
    global _MAX
    WORDS.clear()
    WORDS.update(BASE_WORDS)
    WORDS.update({k: v for k, v in (words or {}).items() if k and v})
    _MAX = max(len(w) for w in WORDS)
# a public place: the generic at the end of the name in English (the specific part keeps its romanized generic)
PUBLIC_GENERIC = (("해수욕장", "Beach", False), ("해변", "Beach", False), ("공원", "Park", False),
                  ("박물관", "Museum", False), ("기념관", "Memorial Hall", False), ("전시관", "Exhibition Hall", False),
                  ("미술관", "Art Museum", False), ("문학관", "Literary Museum", False), ("전망대", "Observatory", False),
                  ("마을", "Village", False), ("항", "Port", False), ("등대", "Lighthouse", False),
                  ("수목원", "Arboretum", False), ("정원", "Garden", False), ("도서관", "Library", False),
                  ("캠핑장", "Campground", False), ("야영장", "Campground", False), ("사", "Temple", True),
                  ("암", "Hermitage", True), ("산", "Mountain", True), ("도", "Island", True), ("섬", "Island", True),
                  ("계곡", "Valley", False), ("서원", "Seowon (Confucian Academy)", False),
                  ("자연휴양림", "Recreational Forest", False), ("휴양림", "Recreational Forest", False),
                  ("생태공원", "Ecological Park", False), ("시장", "Market", False), ("골목", "Alley", False),
                  ("거리", "Street", False), ("광장", "Plaza", False), ("성당", "Catholic Church", False),
                  ("교회", "Church", False), ("고택", "Historic House", False), ("폭포", "Falls", False),
                  ("저수지", "Reservoir", False), ("호수", "Lake", False), ("체험관", "Experience Center", False),
                  ("문화관", "Culture Center", False), ("문화원", "Cultural Center", False),
                  ("과학관", "Science Museum", False), ("역사관", "History Hall", False),
                  ("향교", "Hyanggyo (Confucian School)", False))
PUBLIC_CATEGORIES = {"사찰": ("사", "암"), "산": ("산",), "섬": ("도", "섬")}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _hangul_run(run: str) -> list[str]:
    """One run of Hangul syllables -> words: known words from WORDS (a one-letter word only as the whole run or its
    last letter), the rest romanized as one word each; a trailing 점 after a known word is a branch."""
    out, buf, i = [], "", 0
    while i < len(run):
        hit = next((run[i:i + n] for n in range(min(_MAX, len(run) - i), 0, -1)
                    if run[i:i + n] in WORDS and (n > 1 or i + n == len(run))), None)
        if hit:
            if buf:
                out.append(_cap(_rr_run(buf)))
                buf = ""
            out.append(WORDS[hit])
            i += len(hit)
        else:
            buf += run[i]
            i += 1
    if buf == "점" and out:                              # 한빛터미널점 -> Hanbit Terminal Branch
        out.append("Branch")
    elif buf:
        out.append(_cap(_rr_run(buf)))   # not romanize(): a name ending in 면·동 is not an area here
    return out


def business_name(name: str) -> str:
    """서우식당 -> Seou Sikdang; 해장꾹이 한빛점 -> Haejangkkugi Hanbit Branch; 모텔SP -> Motel SP."""
    words = []
    name = re.sub(r"(\d+)\s*호점", r" Branch No. \1", name)
    for tok in re.findall(r"[가-힣]+|[^가-힣\s]+", name):
        if re.fullmatch(r"[가-힣]+", tok):
            if words and tok.endswith("본점") and len(tok) > 2:      # 벌툰 한빛본점 -> Beoltun Hanbit Main Branch
                words += _hangul_run(tok[:-2]) + ["Main Branch"]
            elif words and tok.endswith("점") and 2 <= len(tok) <= 6 and not any(tok.endswith(w) for w in WORDS):
                words += _hangul_run(tok[:-1]) + ["Branch"]        # 투다리 해리점 -> Tudari Haeri Branch
            else:
                words += _hangul_run(tok)
        else:
            words.append(tok)
    text = " ".join(words)
    text = re.sub(r"\s+([)\],.])", r"\1", re.sub(r"([(\[])\s+", r"\1", text))
    return re.sub(r"\s{2,}", " ", text).strip()


def public_name(name: str, category: str) -> str:
    """사구미해수욕장 -> Sagumi Beach, 한빛사 -> Hanbitsa Temple, 누리산 -> Nurisan Mountain (a one-letter generic only
    in its category: 사찰, 산, 섬), 해촌서원 -> Haechon Seowon (Confucian Academy)."""
    base = re.sub(r"\s+", " ", name).strip()
    for ko, en, keep in PUBLIC_GENERIC:
        if len(ko) == 1 and ko not in PUBLIC_CATEGORIES.get(category, ()):
            continue
        if base.endswith(ko) and len(base) > len(ko):
            if keep:
                return f"{romanize(base)} {en}"
            head = base[: -len(ko)].strip()
            return f"{business_name(head)} {en}"
    return business_name(base)


def guideline_name(p: dict) -> str:
    if p.get("kind") == "attraction":
        return public_name(p["name"], p.get("category") or "")
    return business_name(p["name"])


def row_for(p: dict, city=None) -> dict:
    return {"name_ko": p["name"], "name_en": guideline_name(p), "name_en_source": SOURCE, "name_rr": romanize(p["name"]),
            "en_contentid": "", "addr_en": address_en((p.get("facts") or {}).get("address"), city) or "",
            "match_m": None, "match_basis": ""}


def problems(table: dict, places: list[dict]) -> list[str]:
    out = []
    for p in places:
        row = table.get(p["id"])
        if not row:
            out.append(f"{p['id']}: no row")
        elif row.get("name_ko") != p["name"]:
            out.append(f"{p['id']}: name_ko '{row.get('name_ko')}' is not the place's name '{p['name']}'")
        elif not ALLOWED.match(row.get("name_en") or ""):
            out.append(f"{p['id']}: name_en '{row.get('name_en')}' is empty or has characters outside Latin script")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="도시 데이터 폴더(예: data/<city>)")
    ap.add_argument("--check", action="store_true", help="check only, write nothing")
    a = ap.parse_args(argv)
    data = Path(a.data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    use_city_words(site.get("en_name_words"))
    city = city_of(site)
    places = [p for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("status") == "published"]
    path = data / "en" / "names.json"
    table = json.loads(path.read_text("utf-8")) if path.exists() else {}
    if not a.check:
        added = [p for p in places if (table.get(p["id"]) or {}).get("name_ko") != p["name"]
                 or (table.get(p["id"]) or {}).get("name_en_source") == "romanized"]
        for p in added:
            table[p["id"]] = row_for(p, city)
        if added:
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", "utf-8")
        for p in added:
            print(f"added {p['id']}: {p['name']} -> {table[p['id']]['name_en']}")
        print(f"{len(added)} rows added; {len(table)} rows")
    found = problems(table, places)
    for f in found:
        print(f)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
