"""제휴·관련 사이트 (operator 2026-11-11 '군산각 내 제휴파트너 배너 추가'): the company's sites and the sites related to
this one — a strip at the top of every Korean page's footer and cards at the foot of the home (the operator chose both
from the mock-ups, and the title '제휴·관련 사이트').

data/<region>/related_sites.json (build.State.related_sites; related.json is another file — 연관 관광지):
  {"title": "제휴·관련 사이트", "sites": [{name, url, note, icon, icon_from?, sponsored?}, …]}
- icon: a file the build ships (/assets/…); icon_from: where it came from (the site's own app icon).
- sponsored: a partner's site (a customer of the operator): its note says the relationship ('파트너') and its link is
  rel="sponsored" (표시·광고 기준).
No file or no site, no strip and no cards. Foreign pages show neither (the sites are Korean)."""
from __future__ import annotations

from pathlib import Path

from .textutil import squash_ws, web_url

TRACK = "related_site_click"   # GA4 (track.js): data-provider is the site's name
ASSETS = Path(__file__).resolve().parent.parent / "templates" / "assets"


def view(S) -> dict | None:
    """{title, sites: [{name, url, note, icon, sponsored}]} for the templates, else None."""
    rec = getattr(S, "related_sites", None) or {}
    out = []
    for s in rec.get("sites") or []:
        url = web_url(s.get("url") or "")
        if not (squash_ws(s.get("name")) and url):
            continue
        out.append({"name": squash_ws(s["name"]), "url": url, "note": squash_ws(s.get("note")),
                    "icon": s.get("icon") or "", "sponsored": bool(s.get("sponsored"))})
    return {"title": squash_ws(rec.get("title")) or "제휴·관련 사이트", "sites": out} if out else None


def data_problems(S) -> list[str]:
    """related_sites.json (pipeline.validate): every site has a name, an https address, a note and an icon the build ships;
    a sponsored site's note says it is a partner."""
    out = []
    for i, s in enumerate((getattr(S, "related_sites", None) or {}).get("sites") or []):
        name = squash_ws(s.get("name")) or f"sites[{i}]"
        if not squash_ws(s.get("name")):
            out.append(f"sites[{i}]: name 없음")
        if not str(s.get("url") or "").startswith("https://") or not web_url(s.get("url") or ""):
            out.append(f"{name}: url이 https 주소가 아님")
        if not squash_ws(s.get("note")):
            out.append(f"{name}: note(한 줄 설명) 없음")
        icon = str(s.get("icon") or "")
        if not icon.startswith("/assets/") or not (ASSETS / icon[len("/assets/"):]).is_file():
            out.append(f"{name}: icon이 templates/assets에 없음 ({icon or '빈 값'})")
        if s.get("sponsored") and "파트너" not in str(s.get("note") or ""):
            out.append(f"{name}: sponsored인데 설명에 관계('파트너')가 없음 — 표시·광고 기준")
    return out
