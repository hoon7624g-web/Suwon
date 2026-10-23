"""공개 주소와 배포 설정(vercel.json): 대구는 아직 주소를 옮기지 않았다(CLAUDE.md 2절 — Vercel 주소로 시작, 회사 하위
주소로 옮기면 308·서치콘솔·IndexNow·측정 질문표 주소를 다시 한다).

- 호스트 이동 규칙은 아직 없다. 주소를 옮기면 첫 사이트(2026-10-14 이전)처럼 이전 호스트에만 거는 308 규칙을 맨 앞에
  두고 새 호스트에는 규칙을 두지 않는다 — 그때 이 파일에 이전 호스트별 검사를 더한다.
- 경로 규칙만 있다: 공개했다가 다른 장소의 중복(duplicate_of)으로 합친 장소의 옛 주소(한국어판과 언어판)를 합친 장소로
  308(운영자 2026-10-17 '중복 캠핑장 합치고'). 규칙마다 places.json의 중복 기록과 맞아야 한다.
- 배포 설정: trailingSlash, public/ 출력, /api/chat/·/api/plan/ 다시 쓰기, 챗봇 함수와 코스 만들기 함수(2026-10-18)가
  public/chat을 함께 싣는다(코스 만들기는 maxDuration 60 — 서버 한도 55초, docs/handover/planner.md). noindex 헤더 없음.
- IndexNow 알림의 host와 키 파일 주소는 site.json site_url을 따른다.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

from tools import indexnow

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "suwon"
VERCEL = json.loads((ROOT / "vercel.json").read_text("utf-8"))
SITE = json.loads((DATA / "site.json").read_text("utf-8"))
HOST = urlsplit(SITE["site_url"]).hostname


def test_no_host_move_yet_and_path_rules_only_for_merged_duplicates():
    assert SITE["site_url"].startswith("https://") and HOST
    places = {p["id"]: p for p in json.loads((DATA / "places.json").read_text("utf-8"))}
    want = {}
    for p in places.values():
        if p.get("duplicate_of") and p.get("slug") and p["duplicate_of"] in places:
            to = places[p["duplicate_of"]]["slug"]
            want[f"/places/{p['slug']}/"] = f"/places/{to}/"
            want[f"/:lang(en|ja|zh-hans|zh-hant|de|fr|es|ru)/places/{p['slug']}/"] = f"/:lang/places/{to}/"
    rules = VERCEL.get("redirects") or []
    assert all(set(r) == {"source", "destination", "permanent"} and r["permanent"] is True for r in rules)  # no host rule
    assert {r["source"]: r["destination"] for r in rules} == want


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
