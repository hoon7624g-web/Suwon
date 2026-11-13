"""군산각 블로그 (operator decision 2026-10-30): tools/blog_sync.py finds the places a post is about and the site pages
it links, build shows the posts as title links (/blog/ and the place, guide, column and course pages), validate checks
that every page links exactly its posts and that no blog photo is shown."""
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from pipeline.build import BLOG_HOME, State, blog_groups, blog_home, blog_photo, build
from pipeline.validate import validate
from tools import blog_sync

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DATA = ROOT / "data" / "gunsan"
URL = "https://blog.naver.com/gunsangak/"


def test_names_match_as_words_with_particles_and_spacing():
    places = [{"id": "a", "name": "이성당"}, {"id": "b", "name": "군산요"}, {"id": "c", "name": "스테이,머뭄"},
              {"id": "d", "name": "여미랑 (구.고우당)"}, {"id": "e", "name": "등대로"}, {"id": "f", "name": "명도"},
              {"id": "g", "name": "경암동 철길마을", "alternate_names": ["철길마을"]}]
    pats = blog_sync.name_patterns(places)
    hits = lambda title, text: {h["id"]: (h["n"], h["title"]) for h in blog_sync.match_places(title, text, pats)}
    # a particle or a space after the name counts; inside a longer word it does not ('군산요리')
    assert hits("", "이성당에서 빵을 사고 이성당 본점 앞 줄을 섰다. 군산요리 군산요리") == {"a": (2, False)}
    assert hits("스테이머뭄 후기", "") == {"c": (0, True)}            # '스테이,머뭄' → 스테이 머뭄 → spaces optional
    assert hits("", "여미랑은 좋았다. 여미랑 2인실") == {"d": (2, False)}  # the bracketed old name is dropped
    assert hits("", "등대로 가는 길, 등대로 걸었다. 명도 명도") == {}        # stop words; 2-letter names are skipped
    assert hits("", "경암동철길마을 산책, 철길마을에서") == {}               # once is not enough
    assert hits("철길마을 교복", "") == {"g": (0, True)}


def test_post_text_keeps_this_sites_paths_and_the_category():
    body = ("<script>var categoryName = '군산 숙소 기록' || '전체보기';</script><div class=\"se-main-container\">"
            "<p>스테이머뭄 소개</p><a href=\"https://gunsan.webforai.kr/guides/%EA%B5%B0%EC%82%B0/\">가이드</a>"
            "<a href=\"https://gunsan.webforai.kr/columns/x\">칼럼</a><a href=\"https://example.com/y\">다른 곳</a>"
            "</div><div class=\"comment_area\"><a href=\"https://gunsan.webforai.kr/z/\">댓글</a></div>")
    category, text, links = blog_sync.post_text(body)
    assert category == "군산 숙소 기록" and "스테이머뭄 소개" in text and "댓글" not in text
    assert links == ["/guides/군산/", "/columns/x/"]


def test_list_dates_absolute_and_relative():
    now = dt.datetime(2026, 10, 30, 3, 0, tzinfo=blog_sync.KST)
    assert blog_sync.list_date("2026. 10. 24.", now) == "2026-10-24"
    assert blog_sync.list_date("7시간 전", now) == "2026-10-29"
    assert blog_sync.list_date("12분 전", now) == "2026-10-30"
    assert blog_sync.list_date("", now) == ""


def _post(no, title, date, cat="6", links=(), places=(), url=None):
    return {"id": no, "title": title, "category": cat, "date": date, "url": url or URL + no, "links": list(links),
            "places": [{"id": p, "n": 2, "title": False} for p in places]}


@pytest.fixture()
def built(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    blog = {"blog": {"id": "gunsangak", "name": "군산각 블로그", "url": URL.rstrip("/")},
            "categories": {"6": "바다 산책", "7": "맛집"}, "exclude": {"1003": "운영자가 숨김"},
            "posts": [_post("1001", "철길마을 교복 대여 후기", "2026-10-29", links=["/guides/no-car-day-trip/"],
                            places=["sample-0001"]),
                      _post("1002", "초원사진관 골목", "2026-10-30", cat="7", places=["sample-0002", "sample-0999"]),
                      _post("1003", "숨긴 글", "2026-10-28", places=["sample-0001"]),
                      _post("1004", "장소 없는 글", "2026-10-27"),
                      _post("1005", "다른 블로그 주소", "2026-10-26", places=["sample-0001"],
                            url="https://blog.naver.com/other/1005")]}
    (data / "blog.json").write_text(json.dumps(blog, ensure_ascii=False), "utf-8")
    out = tmp_path / "site"
    build(data, out, "sample")
    return data, out


def test_build_shows_posts_as_links_where_they_belong(built):
    data, out = built
    S = State(data, "sample")
    assert [p["id"] for p in S.blog["posts"]] == ["1002", "1001", "1004"]   # hidden and foreign posts dropped
    page = (out / "blog" / "index.html").read_text("utf-8")
    for no in ("1001", "1002", "1004"):   # one card each: its title (and its picture, when it has one) links the post
        assert page.count(f'<h3 class="bl-t"><a href="{URL}{no}"') == 1
    # the sample places have no licensed photo: the cards go without one — never the blog's pictures
    assert page.count('<li class="bl-card no-ph">') == 3 and "data-kogl" not in page and "사진 출처" not in page
    assert URL + "1003" not in page and "/other/1005" not in page
    assert '<a href="/places/gyeongam-railroad-village/">경암동 철길마을</a>' in page   # the place the post is about
    assert "sample-draft" not in page                                                  # a draft has no page
    assert page.index('href="#bl-6"') < page.index('href="#bl-7"')   # the largest category first
    place = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    assert URL + "1001" in place and URL + "1003" not in place and 'href="/blog/"' in place
    guide = (out / "guides" / "no-car-day-trip" / "index.html").read_text("utf-8")
    assert 'data-block="blog"' in guide and URL + "1001" in guide
    # the home: the cards (all three posts, newest of each category first) and 블로그 in the main menu (operator
    # 2026-10-30) — since the tab panel (operator 2026-10-31) a link of its '읽을거리' group, in the panel's nav and in the
    # phone menu alike
    home = (out / "index.html").read_text("utf-8")
    assert home.count('<h3 class="bl-t">') == 3 and 'aria-labelledby="h-blog"' in home
    for start in ('<nav class="side-nav"', '<nav class="menu-panel"'):
        mast = home[home.index(start):home.index("</nav>", home.index(start))]
        assert '<a class="sg-a" href="/blog/"><span class="sg-n">블로그</span>' in mast, start
    every = "".join(f.read_text("utf-8") for f in out.rglob("*.html"))
    assert URL + "1003" not in every and "pstatic.net" not in every
    assert "/blog/" in (out / "sitemap.xml").read_text("utf-8")


def test_card_photo_is_a_licensed_place_photo_varied_across_cards():
    a = {"name": "선유도", "_path": "/places/선유도/", "_photos": [{"url": "a1", "type": 1}, {"url": "a2", "type": 3}]}
    b = {"name": "장자도", "_path": "/places/장자도/", "_photos": [{"url": "b1", "type": 3}]}
    used: set = set()
    first = blog_photo([[a, b]], used)
    assert (first["url"], first["place"], first["path"], first["type"]) == ("a1", "선유도", "/places/선유도/", 1)
    assert [blog_photo([[a, b]], used)["url"] for _ in range(3)] == ["a2", "b1", "a1"]   # unused first, then repeats
    assert first["alt"] == "선유도"
    # a tier with a photo is used before a less related one, even when its photos are all on the page already
    assert blog_photo([[a], [b]], {"a1", "a2"})["url"] == "a1"
    assert blog_photo([[{"name": "x", "_path": "/x/", "_photos": []}], [b]], set())["url"] == "b1"
    assert blog_photo([[{"name": "x", "_path": "/x/", "_photos": []}]], used) is None


def test_validate_checks_blog_links_and_photos(built):
    data, out = built
    blog_errors = lambda: [x for x in validate(data, out, "sample")[0] if "블로그" in x or "Naver 사진" in x]
    assert blog_errors() == []
    page = out / "places" / "eunpa-lake-park" / "index.html"
    page.write_text(page.read_text("utf-8").replace(
        "</main>", f'<a href="{URL}1003">숨긴 글</a><img src="https://blogthumb.pstatic.net/a.jpg" alt=""></main>', 1), "utf-8")
    guide = out / "guides" / "no-car-day-trip" / "index.html"
    guide.write_text(guide.read_text("utf-8").replace(f'href="{URL}1001"', 'href="/blog/"'), "utf-8")
    errors = blog_errors()
    assert any("eunpa-lake-park" in x and "1003" in x for x in errors)
    assert any("eunpa-lake-park" in x and "Naver 사진" in x for x in errors)
    assert any("no-car-day-trip" in x and "링크가 없음" in x and "1001" in x for x in errors)


def test_real_blog_data_is_well_formed():
    raw = json.loads((DATA / "blog.json").read_text("utf-8"))
    ids = {p["id"] for p in json.loads((DATA / "places.json").read_text("utf-8"))}
    assert raw["blog"]["id"] == "gunsangak" and raw["posts"]
    for p in raw["posts"]:
        assert p["url"] == URL + p["id"] and p["title"] and p["date"][:4] == "2026" and p["category"] in raw["categories"]
        assert {h["id"] for h in p["places"]} <= ids, p["id"]
        assert all(h["title"] or h["n"] >= blog_sync.MIN_BODY for h in p["places"])
        assert set(p) == {"id", "title", "category", "date", "url", "links", "places", "mentions"}   # no text, no photo
        assert not {h["id"] for h in p["places"]} & set(p["mentions"]) and set(p["mentions"]) <= ids


def test_real_blog_cards_all_have_a_licensed_photo():
    """Operator 2026-10-30: every /blog/ card shows a photo — a KOGL 1/3 photo of this site's places, each card its own."""
    S = State(DATA, "production")
    rows = [r for g in blog_groups(S) for r in g["rows"]]
    assert len(rows) == len(S.blog["posts"]) and all(r["photo"] for r in rows)
    assert {r["photo"]["type"] for r in rows} <= {1, 3}
    assert len({r["photo"]["url"] for r in rows}) > len(rows) / 2   # varied: posts on one place rotate its photos
    home = blog_home(S)   # the home row: every category before any repeats, no photo twice
    assert len(home) == BLOG_HOME and len({r["p"]["category"] for r in home}) == min(BLOG_HOME, len(S.blog["categories"]))
    assert len({r["photo"]["url"] for r in home}) == BLOG_HOME


def _sync_store(tmp_path):
    """A data folder with two posts we already hold (category 1, named)."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    post = lambda no: {"id": no, "title": f"글 {no}", "category": "1", "date": "2026-10-30", "url": URL + no,
                       "links": [], "places": [], "mentions": []}
    (data / "blog.json").write_text(json.dumps({"blog": {"id": "gunsangak"}, "checked_at": "2026-10-30",
                                                "categories": {"1": "군산 원도심"}, "exclude": {},
                                                "posts": [post("11"), post("12")]}, ensure_ascii=False), "utf-8")
    return data


def test_sync_writes_nothing_when_the_list_comes_back_empty(tmp_path, monkeypatch):
    """The nightly job (operator 2026-11-11) runs the sync unattended: a list that comes back empty while we hold
    posts is a failed read — the file stays as it is and the exit code says so."""
    data = _sync_store(tmp_path)
    before = (data / "blog.json").read_text("utf-8")
    monkeypatch.setattr(blog_sync, "post_list", lambda blog: [])
    monkeypatch.setattr(blog_sync, "rss_dates", lambda blog: {})
    assert blog_sync.main(["--data", str(data), "--apply"]) == 1
    assert (data / "blog.json").read_text("utf-8") == before


def test_sync_reads_the_name_of_a_category_a_kept_post_moved_to(tmp_path, monkeypatch):
    """2026-11-11: the blog's posts were moved to new categories; posts we already held were not opened again, so
    the new categories had no name and /blog/ showed several groups titled '그 밖의 글'. One post of a category
    without a name is opened again; the others stay cached."""
    data = _sync_store(tmp_path)
    opened = []

    def read(blog, post, patterns):
        opened.append(post["id"])
        return {"id": post["id"], "category_name": "이성당·빵지순례", "links": [], "places": [], "mentions": []}
    monkeypatch.setattr(blog_sync, "post_list", lambda blog: [
        {"id": "11", "title": "글 11", "category": "21", "date_text": "2026. 10. 30."},
        {"id": "12", "title": "글 12", "category": "21", "date_text": "2026. 10. 30."}])
    monkeypatch.setattr(blog_sync, "rss_dates", lambda blog: {})
    monkeypatch.setattr(blog_sync, "read_post", read)
    assert blog_sync.main(["--data", str(data), "--apply"]) == 0
    out = json.loads((data / "blog.json").read_text("utf-8"))
    assert opened == ["11"] and out["categories"]["21"] == "이성당·빵지순례"
    assert [p["category"] for p in out["posts"]] == ["21", "21"] and {p["date"] for p in out["posts"]} == {"2026-10-30"}
