"""tools/harvest_merge.py: harvested TourAPI answers joined to places by rules a person can read in the report — a
관광사진 joins only the place its title names, in the city and the photo's 구·군; a pet or camping value is added with
its source, confirms an equal one (written another way) or stands beside a different one."""
import json

from pipeline import city as citymod
from tools import harvest_merge as hm

C = citymod.from_site({"site_url": "", "region": "한빛", "region_admin": "한빛광역시", "locality": "한빛광역시",
                       "districts": ["누리구", "가람군"], "address_aliases": ["한빛시"]})


def place(pid, name, district="누리구", images=None, lat=None, lng=None, **facts):
    return {"id": pid, "name": name, "status": "published", "images": images or [],
            "facts": {"address": f"한빛광역시 {district} 샘동 1", **facts}, "tourapi": {"contentid": pid, "title": name},
            "geo": {"lat": lat, "lng": lng} if lat else {}}


def gal(gid, title, loc="한빛광역시 누리구 샘동", month="202405", who="갑"):
    return {"galContentId": gid, "galTitle": title, "galWebImageUrl": f"https://x/{gid}.jpg",
            "galPhotographyLocation": loc, "galPhotographyMonth": month, "galPhotographer": who, "_day": "2026-10-16"}


def test_a_photo_joins_only_the_place_its_title_names_in_the_city_and_its_district():
    P = [place("p1", "한빛 별못공원"), place("p2", "솔숲서원", "가람군"),
         place("p3", "(사)선비수련원(솔숲서원)", "가람군"), place("p4", "달빛시장 & 달빛 야시장"), place("p5", "물빛관")]
    items = [gal("1", "별못공원"),                                   # the city's short name in front is dropped
             gal("2", "한빛 솔숲서원", "한빛광역시 가람군 솔면"),          # the whole name wins over a name in brackets
             gal("3", "달빛시장"),                                     # one of the names joined by ' & '
             gal("4", "별못공원", "바다광역시 물결구 중동"),               # taken outside the city
             gal("5", "물빛관", "한빛광역시 가람군 솔면"),                # the photo's 구·군 is not the place's
             gal("6", "물빛관 가는 길"),                                # not the place's name
             gal("7", "물결다리"), gal("8", "물결다리")]
    r = hm.merge_photos(P, items, C, {}, per_place=6, aliases={"물결다리": "p5"})
    got = {p["id"]: [i["gallery_id"] for i in p["images"]] for p in P}
    assert got == {"p1": ["1"], "p2": ["2"], "p3": [], "p4": ["3"], "p5": ["7", "8"]}
    assert r["skipped"]["시·도 밖에서 찍은 사진"] == 1 and r["unmatched"] == {"물빛관": 1, "물빛관 가는 길": 1}
    im = P[0]["images"][0]
    assert im == {"url": "https://x/1.jpg", "alt": "한빛 별못공원", "credit": "한국관광공사", "license": "KOGL-1",
                  "source": "TourAPI 관광사진", "photographer": "갑", "taken": "2024-05", "gallery_id": "1",
                  "checked_at": "2026-10-16"}


def test_a_title_naming_two_places_is_skipped():
    P = [place("p1", "솔숲서원"), place("p2", "솔숲서원", "가람군")]
    r = hm.merge_photos(P, [gal("1", "솔숲서원", "한빛시")], C, {}, per_place=6)
    assert not P[0]["images"] and not P[1]["images"] and sum(r["ambiguous"].values()) == 1


def test_per_place_cap_newest_first_one_per_shoot_and_a_wide_photo_leads_a_narrow_first():
    own = {"url": "https://t/own.jpg", "source": "TourAPI", "license": "KOGL-1"}
    P = [place("p1", "별못공원", images=[own])]
    items = [gal("a", "별못공원", month="202301", who="갑"), gal("b", "별못공원", month="202405", who="을"),
             gal("c", "별못공원", month="202405", who="을"), gal("d", "별못공원", month="202310", who="병")]
    sizes = {"https://t/own.jpg": [640, 480, 1], "https://x/b.jpg": [1280, 853, 1], "https://x/c.jpg": [853, 1280, 1],
             "https://x/d.jpg": [1280, 960, 1], "https://x/a.jpg": [1280, 853, 1]}
    hm.merge_photos(P, items, C, sizes, per_place=3)
    ids = [i.get("gallery_id", "own") for i in P[0]["images"]]
    # b (newest), d, a — c is a second photo of b's shoot and the cap is 3; the 640px own photo gives way to b
    assert ids == ["b", "own", "d", "a"]
    # a second run adds nothing and keeps the order
    hm.merge_photos(P, items, C, sizes, per_place=3)
    assert [i.get("gallery_id", "own") for i in P[0]["images"]] == ids


def test_pet_value_in_the_provider_s_words_beside_a_different_one():
    P = [place("101", "별못공원"), place("102", "물빛관", pet="불가")]
    items = {"101": {"acmpyTypeCd": "전구역 동반가능", "acmpyPsblCpam": "전 견종 동반 가능", "acmpyNeedMtr": "목줄 착용",
                     "_day": "2026-10-16"},
             "102": {"acmpyTypeCd": "일부구역 동반가능", "_day": "2026-10-16"}}
    r = hm.merge_pet(P, items)
    assert P[0]["facts"]["pet"] == "전구역 동반가능 · 전 견종 동반 가능 · 목줄 착용"
    assert P[0]["fact_sources"]["pet"]["provider"] == hm.PET_PROVIDER
    assert P[1]["facts"]["pet"] == "불가" and P[1]["fact_alternatives"]["pet"][0]["value"] == "일부구역 동반가능"
    assert r["added"] == ["별못공원"] and r["differ"] == ["물빛관"]


def test_camping_joins_by_name_and_300m_and_compares_values_written_two_ways():
    P = [place("p1", "별빛캠프 캠핑장", lat=35.80, lng=128.50, homepage="http://www.byeol.kr/intro/a.php",
               infocenter="053-000-1111~2"),
         place("p2", "솔밭 캠핑장", lat=35.90, lng=128.60)]
    camps = [{"contentId": "9", "facltNm": "누리 별빛캠프 캠핑장", "mapY": "35.8001", "mapX": "128.5001",
              "homepage": "https://byeol.kr/", "tel": "053-000-1111", "sbrsCl": "전기,온수", "animalCmgCl": "불가능",
              "operPdCl": "봄,여름", "operDeCl": "평일+주말", "resveUrl": "https://book.example.kr/x", "_day": "2026-10-16"},
             {"contentId": "8", "facltNm": "솔밭 캠핑장", "mapY": "35.95", "mapX": "128.60", "_day": "2026-10-16"}]
    r = hm.merge_camping(P, camps, C)
    f = P[0]["facts"]
    assert (f["subfacility"], f["pet"], f["openperiod"], f["reservationurl"]) == \
           ("전기·온수", "불가능", "봄·여름 · 평일+주말", "https://book.example.kr/x")
    assert f["homepage"] == "http://www.byeol.kr/intro/a.php" and "fact_alternatives" not in P[0]
    assert len(r["same"]) == 2 and r["matched"] == ["누리 별빛캠프 캠핑장 → 별빛캠프 캠핑장 (14m)"]
    assert r["unmatched"] == ["솔밭 캠핑장"] and not P[1]["facts"].get("subfacility")      # 5.5km away
    assert hm.same_value("openperiod", "봄, 여름, 가을", "봄·여름·가을 · 평일+주말")
    assert not hm.same_value("infocenter", "054-383-7778", "054-380-7354")
    assert not hm.same_value("homepage", "http://a.kr/", "https://instagram.com/a")


def test_items_of_reads_one_item_a_list_and_an_error(tmp_path):
    one = {"response": {"body": {"items": {"item": {"contentid": "1"}}}}}
    many = {"response": {"body": {"items": {"item": [{"contentid": "1"}, {"contentid": "2"}]}}}}
    for name, d, n in (("a.json", one, 1), ("b.json", many, 2), ("c.json", {"response": {"body": {"items": ""}}}, 0),
                       ("d.json", {"resultCode": "22"}, 0)):
        (tmp_path / name).write_text(json.dumps(d), "utf-8")
        assert len(hm.items_of(tmp_path / name)) == n, name


def camp(cid, name, **kw):
    return {"contentId": cid, "facltNm": name, "addr1": "한빛광역시 가람군 솔면 숲길 7", "addr2": "", "induty": "자동차야영장",
            "mapX": "127.1", "mapY": "36.1", "doNm": "한빛광역시", "sigunguNm": "가람군", "_day": "2026-10-16", **kw}


def test_a_camp_no_place_matched_becomes_a_draft_stay_with_its_own_values_only():
    P = [place("p1", "솔숲서원", "가람군", lat=36.1, lng=127.1)]
    rich = camp("10", "별빛캠프700", tel="010-1234-5678", sbrsCl="전기,온수", operPdCl="봄,여름", operDeCl="평일+주말",
                gnrlSiteCo="4", autoSiteCo="6", resveUrl="네이버,캠핏")
    thin = camp("11", "숲그늘", tel="010-0000-0000")
    r = hm.add_camps(P, [rich, thin], C)
    assert r == {"new": ["별빛캠프700"], "thin": ["숲그늘"], "have": []}
    rec = P[-1]
    assert rec["id"] == "gocamping-10" and rec["status"] == "draft" and rec["kind"] == "stay" and not rec["images"]
    assert rec["facts"]["roomcount"] == "사이트 10개(일반 4·자동차 6)" and "reservationurl" not in rec["facts"]
    assert set(rec["fact_sources"]) == set(rec["facts"]) and rec["geo"]["lat"] == 36.1
    assert rec["geo"]["url"].endswith("c_no=10") and rec["geo"]["checked_at"] == "2026-10-16"
    # the particle reads the number aloud (칠백 -> 은)
    assert rec["summary"] == ("별빛캠프700은 자동차야영장으로, 사이트 10개(일반 4·자동차 6)를 두고, 봄·여름(평일+주말)에 문을 열며, "
                              "부대시설로 전기·온수가 있습니다.")
    assert hm.add_camps(P, [rich], C)["have"] == ["별빛캠프700"]   # a second run adds nothing


def test_an_aliased_camp_merges_into_its_place_and_its_earlier_stay_becomes_a_duplicate():
    """camp_aliases.json (a person's call): a camp that is a listed place under another name joins that place — its
    values added, a different one beside — and the stay made from it earlier (gocamping-<id>) becomes the place's
    duplicate, so the site keeps one page. A booking note that is not an address is never a booking link."""
    P = [place("p1", "바람숲 야영장", "가람군", lat=36.1, lng=127.1, infocenter="0507-000-1111")]
    hm.add_camps(P, [camp("12", "숲속 야영장", tel="010-2222-3333", sbrsCl="전기", operPdCl="봄", operDeCl="평일",
                          autoSiteCo="7")], C)
    P[-1]["status"] = "published"
    r = hm.merge_camping(P, [camp("12", "숲속 야영장", tel="010-2222-3333", sbrsCl="전기", animalCmgCl="불가능",
                                  resveUrl="네이버,캠핏")], C, {"12": "p1"})
    f = P[0]["facts"]
    assert r["matched"] == ["숲속 야영장 → 바람숲 야영장 (camp_aliases)"] and r["duplicates"] == \
           ["숲속 야영장 (gocamping-12) → 바람숲 야영장 (p1)"]
    assert (f["subfacility"], f["pet"]) == ("전기", "불가능") and "reservationurl" not in f
    assert f["infocenter"] == "0507-000-1111" and P[0]["fact_alternatives"]["infocenter"][0]["value"] == "010-2222-3333"
    assert P[1]["duplicate_of"] == "p1"
    assert hm.merge_camping(P, [camp("12", "숲속 야영장")], C, {"12": "p1"})["duplicates"] == []   # a second run
