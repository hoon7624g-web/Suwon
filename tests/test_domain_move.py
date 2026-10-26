"""공개 주소와 배포 설정(vercel.json): 이 도시는 site.json site_url(회사 하위 주소)로 공개했다.

- 호스트 이동 규칙: 같은 사이트를 그대로 내보내던 공개 Vercel 별칭(첫 사이트의 gunsan-seven.vercel.app처럼)은 맨 앞의
  308 규칙으로 site_url의 같은 경로에 넘긴다. IndexNow 키 파일과 챗봇·코스 만들기 함수(/api/chat/·/api/plan/)는 넘기지
  않는다 — 별칭에서 열린 탭의 질문이 끊기지 않고, 별칭은 site.json chatbot.production_aliases(허용 출처)에 그대로 있다.
  새 호스트(site_url)에는 규칙이 없다. 이 사이트는 공개 별칭이 없어(짧은 suwon.vercel.app은 남의 사이트) 이 프로젝트의
  팀 범위 별칭(배포 보호 로그인 뒤) 두 개를 넘긴다 — 로그인한 운영자도 공개 주소에서 본다.
- 경로 규칙: 공개했다가 다른 장소의 중복(duplicate_of)으로 합친 장소의 옛 주소(한국어판과 언어판)를 합친 장소로 308.
  규칙마다 places.json의 중복 기록과 맞아야 한다.
- 배포 설정: trailingSlash, public/ 출력, /api/chat/·/api/plan/ 다시 쓰기, 챗봇 함수와 코스 만들기 함수가 public/chat을
  함께 싣는다(코스 만들기는 maxDuration 60 — 서버 한도 55초). noindex 헤더 없음.
- IndexNow 알림의 host와 키 파일 주소는 site.json site_url을 따른다.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from tools import indexnow

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "suwon"
VERCEL = json.loads((ROOT / "vercel.json").read_text("utf-8"))
SITE = json.loads((DATA / "site.json").read_text("utf-8"))
HOST = urlsplit(SITE["site_url"]).hostname


# this project's Vercel aliases (checked 2026-10-26: both behind the team's login, 302 to vercel.com/sso-api; the
# short suwon.vercel.app is another organisation's site, never an alias of this one)
OLD_HOSTS = ("suwon-hoon7624g-webs-projects.vercel.app", "suwon-git-main-hoon7624g-webs-projects.vercel.app")


def test_old_hosts_move_to_site_url_and_path_rules_only_for_merged_duplicates():
    assert SITE["site_url"].startswith("https://") and HOST
    rules = VERCEL.get("redirects") or []
    host_rules = [r for r in rules if r.get("has")]
    assert rules[:len(host_rules)] == host_rules                       # the host rules come first
    assert [r["has"] for r in host_rules] == [[{"type": "host", "value": h}] for h in OLD_HOSTS]
    aliases = {urlsplit(u).hostname for u in SITE["chatbot"]["production_aliases"]}
    keep = f"{SITE['indexnow_key']}.txt"
    for r in host_rules:
        old = r["has"][0]["value"]
        assert old != HOST and old in aliases, old                      # the assistant still answers a tab there
        assert r["permanent"] is True and r["destination"] == f"{SITE['site_url'].rstrip('/')}/:path*"
        m = re.fullmatch(r"/:path\(\(\?!\(\?:(.+)\)\$\)\.\*\)", r["source"])
        assert m, r["source"]
        rx = re.compile(f"^(?!(?:{m.group(1)})$).*")
        for path in (keep, "api/chat/", "api/chat", "api/plan/", "api/plan"):
            assert not rx.match(path), path                             # stays on the old host
        for path in ("", "places/hwaseonghaenggung/", "en/", "sitemap.xml", "robots.txt", "api/other/"):
            assert rx.match(path), path                                 # moves
    places = {p["id"]: p for p in json.loads((DATA / "places.json").read_text("utf-8"))}
    want = {}
    for p in places.values():
        if p.get("duplicate_of") and p.get("slug") and p["duplicate_of"] in places:
            to = places[p["duplicate_of"]]["slug"]
            want[f"/places/{p['slug']}/"] = f"/places/{to}/"
            want[f"/:lang(en|ja|zh-hans|zh-hant|de|fr|es|ru)/places/{p['slug']}/"] = f"/:lang/places/{to}/"
    path_rules = rules[len(host_rules):]
    assert all(set(r) == {"source", "destination", "permanent"} and r["permanent"] is True for r in path_rules)
    assert {r["source"]: r["destination"] for r in path_rules} == want


def test_the_rest_of_the_deployment_settings_are_unchanged():
    assert VERCEL["trailingSlash"] is True and VERCEL["outputDirectory"] == "public"
    # the assistant, and the course planner of /plan/ on the same knowledge files
    assert VERCEL["rewrites"] == [{"source": "/api/chat/", "destination": "/api/chat"},
                                  {"source": "/api/plan/", "destination": "/api/plan"}]
    assert VERCEL["functions"]["api/chat.js"]["includeFiles"] == "public/chat/**"
    assert VERCEL["functions"]["api/plan.js"]["includeFiles"] == "public/chat/**"
    assert VERCEL["functions"]["api/plan.js"]["maxDuration"] == 60   # chatbot/planner.js PLAN_LIMITS.requestMs 55 s
    assert not VERCEL.get("headers")                                      # no noindex header on any host


def test_indexnow_host_and_key_location_follow_site_url():
    site_url, key = indexnow.load_site(DATA)
    (payload,) = indexnow.payloads(site_url, key, [f"{site_url}/"])
    assert payload["host"] == HOST
    assert payload["keyLocation"] == f"https://{HOST}/{SITE['indexnow_key']}.txt"
