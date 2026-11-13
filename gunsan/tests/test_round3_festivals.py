"""tools/round3_festivals.py: the festival merge keeps existing values (a differing one goes beside it) and is
idempotent; the copy check catches a copied sentence but not a quoted programme name."""
import json

from tools import round3_festivals as R

FEST = {
    "series": "테스트축제", "name": "2026 테스트축제", "year": 2026, "start_date": "2026-05-01", "end_date": "2026-05-03",
    "period_text": "2026. 5. 1.(금) ~ 5. 3.(일)", "venue": "새 장소 일원", "organizer": "군산시", "fee": "무료",
    "sources": [
        {"name": "군산시 보도자료 '테스트축제 개최' (관광진흥과, 2026-04-01, news_epct_no=100)", "url": R.EMINWON_LIST,
         "checked_at": "2026-10-08", "news_epct_no": "100"},
        {"name": "군산시 누리집 게시물 '2025 테스트축제'", "url": "https://www.gunsan.go.kr/main/m143/view/1",
         "checked_at": "2026-10-08"}],
    "past_editions": [{"year": 2025, "start_date": "2025-05-02", "end_date": "2025-05-04", "venue": "옛 장소"}],
    "place_slugs": ["eunpa", "not-a-place"], "official_urls": [],
}
EXISTING = {"id": "event-1", "status": "published", "reviewed_at": "2026-10-01", "name": "2026 테스트축제",
            "start_date": "2026-05-01", "end_date": "2026-05-03", "place_name": "원래 장소", "fee": "무료",
            "source_name": "군산시 문화관광", "source_url": "https://www.gunsan.go.kr/tour/m2101/view/9",
            "checked_at": "2026-10-01"}


def test_merge_keeps_existing_values_adds_alternatives_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setitem(R.CURATED, "테스트축제", dict(series="테스트축제", src="100", past_src={2025: "view/1"},
                                                  highlights=["우리 문장으로 쓴 프로그램"]))
    data = tmp_path / "data"
    data.mkdir()
    (data / "events.json").write_text(json.dumps([EXISTING], ensure_ascii=False), "utf-8")
    (data / "places.json").write_text(json.dumps([{"slug": "eunpa", "name": "은파"}], ensure_ascii=False), "utf-8")
    fest = tmp_path / "festivals.json"
    fest.write_text(json.dumps([FEST], ensure_ascii=False), "utf-8")

    R.run(data, fest)
    first = (data / "events.json").read_text("utf-8")
    events = {e["id"]: e for e in json.loads(first)}
    ev = events["event-1"]
    # existing value kept, the other source's value beside it with its own source; human fields untouched
    assert ev["place_name"] == "원래 장소" and ev["status"] == "published" and ev["reviewed_at"] == "2026-10-01"
    alt = ev["alternatives"]["place_name"][0]
    assert alt["value"] == "새 장소 일원" and "보도자료 번호 100" in alt["source_name"]
    assert alt["source_url"] == R.EMINWON_LIST
    assert "fee" not in ev["alternatives"]                      # same value: no alternative
    assert ev["highlights"] == ["우리 문장으로 쓴 프로그램"] and ev["series"] == "테스트축제"
    assert ev["place_slugs"] == ["eunpa"]                       # only places that exist
    past = events["fest-테스트축제-2025"]
    assert past["status"] == "draft" and past["start_date"] == "2025-05-02"
    assert past["source_url"] == "https://www.gunsan.go.kr/main/m143/view/1"

    R.run(data, fest)
    assert (data / "events.json").read_text("utf-8") == first   # running twice changes nothing


def test_copy_check_flags_copied_sentences_not_names():
    raw = [("d1.txt", "군산시는 매년 바다의 날인 5월 31일을 '군산 갑오징어 갑토리의 날'로 지정·선포했다.")]
    copied = [("x", "매년 바다의 날인 5월 31일을 '군산 갑오징어 갑토리의 날'로 지정")]
    assert R.copy_runs(copied, raw, [])
    ours = [("y", "군산시는 5월 31일(바다의 날)을 해마다 돌아오는 '군산 갑오징어 갑토리의 날'로 정했습니다.")]
    assert R.copy_runs(ours, raw, []) == []
