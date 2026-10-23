"""YouTube videos: only checked entries, linked from places, all on /videos/, nothing loaded before play."""
import json
import shutil
from pathlib import Path

from pipeline.build import build, load_videos, video_groups
from pipeline.validate import validate

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


def test_videos_page_place_block_and_facade(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    videos = [
        {"youtube_id": "dBTZVpcDnw0", "title": "철길마을 걷기", "channel": "군산시 공식채널", "channel_kind": "official",
         "url": "https://www.youtube.com/watch?v=dBTZVpcDnw0", "place_slugs": ["gyeongam-railroad-village"],
         "topics": ["근대문화"], "checked_at": "2026-10-08", "verified_by": "YouTube oEmbed",
         "thumbnail": {"url": "https://i.ytimg.com/vi/dBTZVpcDnw0/mqdefault.jpg", "width": 320, "height": 180}},
        {"youtube_id": "17KwFK9VnEs", "title": "확인 안 된 영상", "url": "https://www.youtube.com/watch?v=17KwFK9VnEs",
         "place_slugs": ["gyeongam-railroad-village"], "topics": ["축제"]},  # no verified_by: never shown
    ]
    (data / "videos.json").write_text(json.dumps(videos, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    page = (out / "videos" / "index.html").read_text("utf-8")
    assert "철길마을 걷기" in page and "확인 안 된 영상" not in page
    assert "youtube-nocookie.com/embed" not in page  # facade only: the player is created on click
    assert 'data-yt="dBTZVpcDnw0"' in page and "https://www.youtube.com/watch?v=dBTZVpcDnw0" in page
    assert '<script src="/assets/site.js"' in page  # the play buttons need it
    assert 'src="https://i.ytimg.com/vi/dBTZVpcDnw0/mqdefault.jpg"' in page and 'loading="lazy"' in page
    place = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    assert 'data-yt="dBTZVpcDnw0"' in place and 'href="/videos/"' in place and "/assets/site.js" in place
    # one page per topic, at the path the view model gives (an ASCII slug: site.json video_topics, else the RR of
    # the topic's title)
    groups = video_groups(load_videos(data), ())
    assert [g["title"] for g in groups] == ["근대문화"] and groups[0]["_path"] == "/videos/geundaemunhwa/"
    topic = (out / groups[0]["_path"].strip("/") / "index.html").read_text("utf-8")
    assert "철길마을 걷기" in topic and "확인 안 된 영상" not in topic
    errors, warns, _ = validate(data, out, "sample")
    assert errors == [] and any("근대문화" in w and "video_topics" in w for w in warns)  # not configured: a warning


def test_topic_slugs_follow_site_json_and_other_topics_go_last(tmp_path):
    vids = [{"youtube_id": f"v{i}", "url": f"https://www.youtube.com/watch?v=v{i}", "verified_by": "YouTube oEmbed",
             "topics": t, "published_date": f"2026-10-0{i}"} for i, t in enumerate([["먹거리"], [], ["축제"], ["먹거리"]], 1)]
    groups = video_groups(vids, (("축제", "festivals"), ("먹거리", "food")))
    assert [(g["title"], g["_path"], len(g["items"])) for g in groups] == [
        ("축제", "/videos/festivals/", 1), ("먹거리", "/videos/food/", 2), ("기타", "/videos/other/", 1)]
    # the same videos and configuration always name the same pages (State computes them once: S.video_groups)
    assert [g["_path"] for g in video_groups(vids, (("축제", "festivals"), ("먹거리", "food")))] == [
        "/videos/festivals/", "/videos/food/", "/videos/other/"]
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["video_topics"] = [{"title": "축제", "slug": "festivals"}, {"title": "먹거리", "slug": "food"}]
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    (data / "videos.json").write_text(json.dumps(vids, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    assert all((out / "videos" / s / "index.html").exists() for s in ("festivals", "food", "other"))
    errors, warns, _ = validate(data, out, "sample")
    assert errors == [] and not [w for w in warns if "video_topics" in w]
