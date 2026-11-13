"""유튜브·인스타그램 인기 순위 (the first site's operator decision 2026-11-10, carried here 2026-11-13): the curated
videos ranked by views and — once data/<region>/insta.json comes — the curated Instagram posts by likes, under the
opening (.hrk) and on the board from 1680px (.h-rside). Without insta.json the block and the board are YouTube only
(no tabs, no empty Instagram part); with it both show, behind tabs on the board, and the guide carries its Instagram
chapter. Every rank says it is an order within this site's own lists, not a recommendation, and that the counts are
those of the day they were put in."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline.build import State, build, view_count

ROOT = Path(__file__).resolve().parent.parent
SUBSET = ROOT / "tests" / "fixtures" / "gunsan_subset"


def _data(tmp: Path, insta: bool) -> Path:
    data = tmp / "data"
    shutil.copytree(SUBSET, data)
    shutil.copy(ROOT / "data" / "suwon" / "videos.json", data / "videos.json")
    shutil.copy(ROOT / "data" / "suwon" / "yt_channels.json", data / "yt_channels.json")
    if insta:
        places = [p["slug"] for p in json.loads((data / "places.json").read_text("utf-8"))][:6]
        guide = json.loads((data / "guides.json").read_text("utf-8"))[0]["id"]
        items = [{"id": f"ig-{i}", "status": "published", "platform": "instagram", "url": f"https://www.instagram.com/p/x{i}/",
                  "author": f"@acc{i}", "note": f"우리가 쓴 한 줄 소개 {i}", "likes": 1000 * (i + 1),
                  "place_slugs": [places[i]], "guide_ids": [guide]} for i in range(6)]
        (data / "insta.json").write_text(json.dumps({"items": items, "channels": []}, ensure_ascii=False), "utf-8")
    return data


@pytest.fixture(scope="module", params=[False, True], ids=["youtube-only", "with-instagram"])
def world(request, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rank")
    data = _data(tmp, request.param)
    out = tmp / "out"
    build(data, out, "preview")
    return request.param, State(data, "preview"), out


def test_the_curated_videos_are_ranked_by_views_and_the_lists_say_what_the_order_is(world):
    insta, S, out = world
    pop = S.popular_videos
    counts = [view_count(v) for v in pop]
    assert pop and counts == sorted(counts, reverse=True) and all(v.get("popular_curated") for v in pop)
    home = (out / "index.html").read_text("utf-8")
    name = S.site["site_name"]
    note = re.search(r'class="hrk-note">([^<]*)', home).group(1)
    assert f"{name}" in note and "추천 순서가 아닙니다" in note and "목록에 실은 때의 값" in note
    assert re.search(r'class="hrk-sub">.*?영상 <span class="tn">%d</span>편' % len(pop), home, re.S)
    yt_rows = re.findall(r'<li class="hrk-i[^"]*">\s*<a class="hrk-a" href="https://www\.youtube\.com/watch\?v=([^"]+)"', home)
    assert yt_rows == [v["youtube_id"] for v in pop[:5]]
    board = home[home.index('<aside class="h-rside"'):home.index("</aside>")]
    assert "고른 영상" in board and "추천 순서가 아님" in board and "숫자는 목록에 실은 때의 값" in board
    videos = (out / "videos" / "index.html").read_text("utf-8")
    assert 'id="yt-popular"' in videos and "추천 순서가 아닙니다" in videos
    if insta:
        assert "data-tabs" in board and 'id="hrs-panel-ig"' in board and "좋아요 순" in board
        assert 'class="hrk-col hrk-w-ig"' in home and "인스타그램은 좋아요 수" in note
        likes = [int(x.replace(",", "")) for x in re.findall(r'class="hrk-cnt tn">좋아요 ([\d,]+)', home)]
        assert likes == sorted(likes, reverse=True) and len(likes) == 5
        assert any('id="h-insta"' in p.read_text("utf-8") for p in out.glob("guides/*/index.html"))
    else:
        assert "data-tabs" not in board and "hrs-panel-ig" not in board and "인스타" not in board
        assert "hrk-w-ig" not in home and "인스타그램" not in note
        assert not any('id="h-insta"' in p.read_text("utf-8") for p in out.glob("guides/*/index.html"))


def test_the_instagram_words_are_neutral_unless_insta_json_names_them(tmp_path, world):
    """The first site's lists were of cafes ('대형·감성 카페'); a region's posts are of any kind of place: the headings
    say '여행지·맛집' / '장소' unless insta.json's topic / noun name the curation (조정 세션 2026-11-13)."""
    from pipeline.build import INSTA_WORDS, load_insta_words
    assert INSTA_WORDS == {"topic": "여행지·맛집", "noun": "장소"}
    assert load_insta_words(tmp_path) == INSTA_WORDS                       # no insta.json
    (tmp_path / "insta.json").write_text(json.dumps({"topic": "카페", "noun": "카페", "items": []}, ensure_ascii=False), "utf-8")
    assert load_insta_words(tmp_path) == {"topic": "카페", "noun": "카페"}
    insta, S, out = world
    if insta:
        guide = next(p.read_text("utf-8") for p in out.glob("guides/*/index.html") if 'id="h-insta"' in p.read_text("utf-8"))
        guide = re.sub(r"<[^>]+>", "", guide)   # the build keeps '·' with the word before it (textutil.keep_dots: a span)
        assert "인스타그램에서 많이 찾은" in guide and "여행지·맛집" in guide and "장소별 인스타그램 미리보기" in guide
        assert "감성 카페" not in guide and "카페별" not in guide
        assert "여행지·맛집 인스타그램" in re.sub(r"<[^>]+>", "", (out / "index.html").read_text("utf-8"))


def test_insta_page_holds_every_post_by_likes_and_the_home_links_there(world):
    """/insta/ (조정 세션 2026-11-13): '인스타그램에서 본 <region>' with the post count, the rule line (this site's list,
    by likes, not a recommendation, the counts of the day they were put in — no date), each post an <article id> with
    its rank, account, likes, our note, the places this site publishes, the original link and the embed slot; the
    channels at #ig-channels. The home's Instagram rows open /insta/#<id> and its '편 모두' /insta/. Korean only; no page
    without insta.json."""
    insta, S, out = world
    page = out / "insta" / "index.html"
    if not insta:
        assert not page.exists()
        assert "/insta/" not in (out / "index.html").read_text("utf-8")
        return
    html = page.read_text("utf-8")
    posts = sorted(S.insta, key=lambda a: (-int(a.get("likes") or 0), a["id"]))
    assert re.search(r'<h1 id="h-list" class="h-list">인스타그램에서 본 [^<]+<span class="count tn">%d편</span></h1>' % len(posts), html)
    rule = re.search(r'class="lede ig-rule">([^<]*)', html).group(1)
    assert f"게시물 {len(posts)}편 안의 좋아요 순" in rule and "추천 순서가 아님" in rule and "목록에 실은 때의 값" in rule
    main = html[html.index('<section class="pg-hero'):html.index("</main>")]
    assert not re.search(r"20\d\d-\d\d-\d\d|\d{4}년 \d+월|\d+월 \d+일", main)   # no check date on the screen
    ids = re.findall(r'<article class="ab-item ab-post ig-post" id="([^"]+)" data-embed="instagram" data-url="https://www\.instagram\.com/', html)
    assert ids == [a["id"] for a in posts]
    for i, a in enumerate(posts, 1):
        art = html[html.index(f'<article class="ab-item ab-post ig-post" id="{a["id"]}"'):]
        art = art[:art.index("</article>")]
        assert f'<span class="ig-rk tn">{i}<' in art and a["note"] in art and "data-embed-slot" in art and a["url"] in art
        for slug in a["place_slugs"]:
            if slug in S.ent_by_slug:
                assert f'href="{S.ent_by_slug[slug]["_path"]}"' in art
    home = (out / "index.html").read_text("utf-8")
    assert re.findall(r'class="hrk-a" href="/insta/#([^"]+)"', home) == [a["id"] for a in posts[:5]]
    assert 'href="/insta/">' in home and "/en/insta/" not in home
    assert not (out / "en" / "insta").exists()


def test_the_rank_rows_show_short_counts_from_the_whole_number():
    from pipeline.build import short_views
    assert short_views(3486762) == "조회수 349만회" and short_views(916_000) == "조회수 91.6만회"
    assert short_views(52_715) == "조회수 5.3만회" and short_views(9_100) == "조회수 9,100회" and short_views(0) == ""


def test_no_korean_video_outside_the_curated_list_has_more_views_than_its_last(tmp_path):
    """data/suwon: the list (yt_channels.json popular_video_ids) holds every published Korean video with more views than
    its last one (exclude left out), in view-count order (군산각 2026-11-10 '넣어')."""
    S = State(ROOT / "data" / "suwon", "production")
    pop = S.popular_videos
    counts = [view_count(v) for v in pop]
    assert pop and counts == sorted(counts, reverse=True)
    rest = [v for v in S.videos if v not in pop and (v.get("lang") or "ko") == "ko" and not v.get("exclude")]
    assert not [v["youtube_id"] for v in rest if view_count(v) > counts[-1]]
    assert all(v["short_view_text"] for v in pop)
