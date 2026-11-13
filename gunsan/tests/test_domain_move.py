"""공개 주소 이전(2026-10-14 운영자 결정): 이전 주소 두 곳은 같은 경로의 새 주소(site.json site_url)로 308.

- vercel.json의 redirects는 이전 호스트(all-about-gunsan.vercel.app, gunsan-seven.vercel.app)에만 걸리고
  새 호스트에는 규칙이 없다(돌고 도는 이동 없음). 예외(2026-10-15): 영어 slug로 옮긴 가이드 21편의 옛 주소
  /<언어>/guides/guide-NN/ → 새 slug 주소(호스트 조건 없음, 옛 주소 하나씩만, 목적지는 guide-NN이 아님).
- IndexNow 키 파일은 두 이전 호스트에서도 그대로 열린다(이동 제외).
- all-about-gunsan.vercel.app의 /api/chat/도 이동에서 뺀다: 옮기기 전에 열린 페이지의 챗봇 요청(POST)이 다른 출처로
  이동되면 Origin이 'null'이 되기 때문이다. chatbot/server.js가 그 출처를 받는다(tests/js/chat.test.js).
- 소스 패턴 '/:path(<정규식>)'은 Vercel(path-to-regexp)이 '^/(<정규식>)$'로 바꾼다. 여기서는 같은 식으로 맞춰 본다.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from tools import indexnow

ROOT = Path(__file__).resolve().parent.parent
VERCEL = json.loads((ROOT / "vercel.json").read_text("utf-8"))
SITE = json.loads((ROOT / "data" / "gunsan" / "site.json").read_text("utf-8"))
NEW_HOST = urlsplit(SITE["site_url"]).hostname
OLD_HOSTS = ("all-about-gunsan.vercel.app", "gunsan-seven.vercel.app")
KEY_FILE = f"/{SITE['indexnow_key']}.txt"
PAGES = ("/", "/places/", "/places/%EC%9B%94%EB%AA%85%EA%B3%B5%EC%9B%90/", "/en/places/", "/ja/", "/sitemap.xml",
         "/robots.txt", "/llms.txt", "/llms-full.txt", "/chat/catalog.txt", "/assets/chat.js",
         f"{KEY_FILE}.bak", f"/x{KEY_FILE}", "/api/chat/more/", "/api/chatty/")


def rules_for(host: str) -> list[dict]:
    return [r for r in VERCEL.get("redirects", [])
            if any(h.get("type") == "host" and h.get("value") == host for h in r.get("has", []))]


def destination(host: str, path: str) -> str | None:
    """Where the first matching redirect sends `path` on `host` (Vercel: first match wins); None when it stays."""
    for rule in rules_for(host):
        m = re.fullmatch(r"/:path\((.*)\)", rule["source"])
        assert m, rule["source"]
        hit = re.fullmatch(f"/({m.group(1)})", path)
        if hit:
            assert rule["destination"].endswith("/:path*")
            return rule["destination"][:-len(":path*")] + hit.group(1)
    return None


def test_site_url_is_the_new_domain_and_every_rule_is_host_bound():
    assert SITE["site_url"] == "https://gunsan.webforai.kr"
    redirects = VERCEL["redirects"]
    moves = [r for r in redirects if r.get("has")]
    assert moves and redirects[:len(moves)] == moves                      # the host rules come first
    assert all(h["type"] == "host" and h["value"] in OLD_HOSTS for r in moves for h in r["has"])
    assert rules_for(NEW_HOST) == []
    assert all(destination(NEW_HOST, p) is None for p in (*PAGES, KEY_FILE, "/api/chat/"))
    # 2026-10-15 (QA SRC-03c): the rules without a host are the retired /<code>/guides/guide-NN/ addresses of
    # the 21 guides that took English slugs; each sends that one path to a slug page, never to a guide-NN path
    retired = redirects[len(moves):len(moves) + 21]
    assert len(retired) == 21
    # 2026-10-29 (operator, 03647ddc2·e29833690): after them, the old /en/ place and guide slugs, each one exact path
    # (with and without the closing slash) sent 308 to one page, never to an address that is itself redirected;
    # 2026-11-04 (operator, 736096e65): also a Korean place merged into another ('파라다이스' → '파라다이스-호텔')
    # in Korean and, by one :lang rule, in the eight language versions
    SLUG, KO = r"[a-z0-9]+(?:-[a-z0-9]+)*", r"(?:%[0-9A-F]{2}|[a-z0-9-])+"
    LEGACY = rf"/(?:en/(?:places|guides)/{SLUG}|:lang(?:\((?:[a-z-]+\|)*[a-z-]+\))?/places/{SLUG}|places/{KO})"
    legacy = redirects[len(moves) + 21:]
    sources = {r["source"] for r in redirects}
    for r in legacy:
        assert set(r) == {"source", "destination", "permanent"} and r["permanent"] is True, r
        assert re.fullmatch(LEGACY + "/?", r["source"]), r
        assert re.fullmatch(LEGACY + "/", r["destination"]), r
        assert r["destination"] not in sources and r["destination"].rstrip("/") not in sources, r
        twin = r["source"][:-1] if r["source"].endswith("/") else r["source"] + "/"
        assert [x["destination"] for x in legacy if x["source"] == twin] == [r["destination"]], r
    for r in retired:
        assert set(r) == {"source", "destination", "permanent"} and r["permanent"] is True, r
        assert re.fullmatch(r"/:lang\(ja\|zh-hans\|zh-hant\|de\|fr\|es\|ru\)/guides/guide-\d\d/", r["source"]), r
        assert re.fullmatch(r"/:lang/guides/[a-z0-9]+(?:-[a-z0-9]+)*/", r["destination"]), r
        assert not re.fullmatch(r"/:lang/guides/guide-\d\d/", r["destination"]), r


def test_both_old_hosts_send_every_page_to_the_same_path_on_the_new_domain():
    for host in OLD_HOSTS:
        rules = rules_for(host)
        assert len(rules) == 1, host
        assert rules[0]["permanent"] is True and "statusCode" not in rules[0]      # 308, keeps the method
        assert rules[0]["destination"] == f"{SITE['site_url']}/:path*"
        for path in PAGES:
            assert destination(host, path) == SITE["site_url"] + path, (host, path)


def test_key_file_stays_on_both_old_hosts_and_chat_api_on_the_previous_one():
    for host in OLD_HOSTS:
        assert destination(host, KEY_FILE) is None, host
    for path in ("/api/chat/", "/api/chat"):
        assert destination("all-about-gunsan.vercel.app", path) is None, path
    # gunsan-seven pages have been redirected since 2026-10-09, before the assistant: nothing there asks
    assert destination("gunsan-seven.vercel.app", "/api/chat/") == f"{SITE['site_url']}/api/chat/"


def test_the_rest_of_the_deployment_settings_are_unchanged():
    assert VERCEL["trailingSlash"] is True and VERCEL["outputDirectory"] == "public"
    # the assistant, and the course planner of /plan/ (operator 2026-10-17) on the same knowledge files
    assert VERCEL["rewrites"] == [{"source": "/api/chat/", "destination": "/api/chat"},
                                  {"source": "/api/plan/", "destination": "/api/plan"}]
    assert VERCEL["functions"]["api/chat.js"]["includeFiles"] == "public/chat/**"
    assert VERCEL["functions"]["api/plan.js"]["includeFiles"] == "public/chat/**"
    assert not VERCEL.get("headers")                                      # no noindex header on any host


def test_indexnow_host_and_key_location_follow_site_url():
    site_url, key = indexnow.load_site(ROOT / "data" / "gunsan")
    (payload,) = indexnow.payloads(site_url, key, [f"{site_url}/"])
    assert payload["host"] == NEW_HOST == "gunsan.webforai.kr"
    assert payload["keyLocation"] == f"https://gunsan.webforai.kr{KEY_FILE}"
