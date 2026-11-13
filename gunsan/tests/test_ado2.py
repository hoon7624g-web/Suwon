"""ADO2 숏폼 영상 (operator decision 2026-11-11 meeting): one ADO2 video per place on its Korean page with 'Powered by
ADO2' and the relationship line, gathered on /videos/; the sync pairs ADO2 names with this site's places."""
import json, shutil
from pathlib import Path
from types import SimpleNamespace

import tools.ado2_sync as sync
from pipeline import ado2
from pipeline.build import build
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "gunsan" / "ado2.json").read_text("utf-8"))
PLACES = json.loads((ROOT / "data" / "gunsan" / "places.json").read_text("utf-8"))
FILE = ("https://ado2mediastoragepublic.blob.core.windows.net/ado2-media-public-access/ado2-media-original/"
        "019c9894-c761-74b7-8c5e-71d854ce6389/01a1bda3-2811-7178-b486-c3ef4034c7be/")


def test_the_gunsan_file_is_clean_and_pairs_the_hand_checked_names():
    S = SimpleNamespace(ado2=DATA, entities_all=PLACES, site_url="https://gunsan.webforai.kr")
    assert ado2.data_problems(S) == []
    rows = DATA["places"]
    assert len(rows) >= 38 and len({r["video_id"] for r in rows.values()}) == len(rows)
    by_name = {r["store_name"]: pid for pid, r in rows.items()}
    assert by_name["H모텔"] == "gunsan-306698"                  # 홍인모텔 (수석 기록 2026-11-12, same address)
    assert by_name["JNK Classic Hotel"] == "gunsan-968157"      # 백릉안1길 17 = 1st Black, not 6th Rose Gold
    assert "gunsan-1020706" not in rows
    assert all("?" not in r["video"] and r["video"].endswith(".mp4") for r in rows.values())


def test_service_link_carries_the_site_as_referral_and_problems_are_named():
    S = SimpleNamespace(ado2=DATA, site_url="https://gunsan.webforai.kr", entities_all=[])
    svc = ado2.service(S)
    assert svc["url"].startswith("https://ado2.o2osolution.ai/?utm_source=gunsan.webforai.kr&utm_medium=referral")
    bad = {"service": {"url": "http://x"}, "places": {
        "a": {"name": "A", "video_id": 1, "video": FILE + "video/x.mp4?sig=1", "poster": "https://x.com/p.jpg", "page": ""},
        "b": {"name": "B", "video_id": 1, "video": FILE + "video/y.mp4", "poster": FILE + "image/y.jpg",
              "page": "https://ado2.o2osolution.ai/video/1"}}}
    out = ado2.data_problems(SimpleNamespace(ado2=bad, site_url="", entities_all=[]))
    assert any("service.url" in p for p in out) and any("A: video" in p for p in out)
    assert any("A: poster" in p for p in out) and any("A: page" in p for p in out) and any("B: 영상 1번" in p for p in out)
    assert ado2.for_place(SimpleNamespace(ado2={}, site_url=""), {"id": "a", "name": "A"}) is None


def test_sync_pairs_by_name_then_by_name_part_and_road_address():
    places = [{"id": "p1", "name": "동국", "status": "published", "facts": {"address": "전라북도 군산시 동국사길 7 (월명동)"}},
              {"id": "p2", "name": "동국사", "status": "published", "facts": {"address": "군산시 동국사길 16"}},
              {"id": "p3", "name": "달", "status": "published", "facts": {}},
              {"id": "p4", "name": "하늘", "status": "published", "facts": {"address": "군산시 구영3길 72"}}]
    rec = {"match": {"하늘게스트하우스": "p4"}}
    item = lambda n, d="": {"store_name": n, "description": d}
    assert sync.match(item("달"), places, rec)[0]["id"] == "p3"
    assert sync.match(item("게스트하우스 동국", "\"게스트하우스 동국\"은 전북 군산시 동국사길 7에 있는"), places, rec)[0]["id"] == "p1"
    assert sync.match(item("게스트하우스 동국", "군산시 어딘가"), places, rec)[0] is None   # no address: a person decides
    assert sync.match(item("하늘게스트하우스"), places, rec)[0]["id"] == "p4"
    assert sync.bare(FILE + "video/x.mp4?sp=r&sig=abc") == FILE + "video/x.mp4"
    assert sync.account(FILE + "video/x.mp4") == "019c9894-c761-74b7-8c5e-71d854ce6389"


def test_place_page_and_videos_shelf_show_the_video_with_powered_by(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    rec = {"service": DATA["service"], "source": DATA["source"], "match": {}, "hold": {}, "places": {
        "sample-0101": {"name": "[샘플] 주변 숙소 A", "store_name": "A", "video_id": 9001, "video": FILE + "video/a.mp4",
                        "poster": FILE + "image/a.jpg", "created": "2026-11-12", "page": "https://ado2.o2osolution.ai/video/9001"}}}
    (data / "ado2.json").write_text(json.dumps(rec, ensure_ascii=False), "utf-8")
    vid = json.loads((ROOT / "data" / "gunsan" / "videos.json").read_text("utf-8"))[:2]
    (data / "videos.json").write_text(json.dumps(vid, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    stay = next(p for p in (out / "places").glob("*/index.html") if "sample-0101" in p.read_text("utf-8"))
    html = stay.read_text("utf-8")
    assert 'data-block="ado2"' in html and f'data-ado2="{FILE}video/a.mp4"' in html and 'loading="lazy"' in html
    assert "Powered by" in html and "utm_campaign=powered_by_ado2" in html and "운영사" in html
    assert 'href="#h-ado2"' in html                                   # the local bar
    other = (out / "places").glob("*/index.html")
    assert sum('data-block="ado2"' in p.read_text("utf-8") for p in other) == 1
    shelf = (out / "videos" / "index.html").read_text("utf-8")
    assert 'id="ado2"' in shelf and shelf.count('class="a2-card"') == 1 and "추천 순서가 아닙니다" in shelf
    assert not any(ado2.FILE_HOST in p.read_text("utf-8") for p in (out / "en").rglob("*.html"))
    errors = validate(data, out, "sample")[0]
    assert not errors, errors[:5]
