"""ADO2 숏폼 영상 (operator decision at the 2026-11-11 meeting): the short promotional videos the operator's own AI video
service ADO2 (에이아이오투오) made for the stays and restaurants on this site, one per business, shown on that place's
Korean page and gathered on /videos/ — each with 'Powered by ADO2', a link to the service (the meeting: a visitor who
wonders 'how was this made?' finds ADO2 and makes one for their own business).

data/<region>/ado2.json (build.State.ado2), written by tools/ado2_sync.py:
  service: {name, url, about, maker} — the service the badge links to;
  source: where the sync reads (the ADO2 public list) and which items are this site's (accounts, since);
  match / hold: the people's pairings and the videos not shown (by ADO2 name — the sync reads them);
  places: {place id: {name, store_name, video_id, video, poster, created, page, checked_at}} — video and poster are the
  provider's public files (never copied to this site), page the video's own page on ADO2.

What a page says (CLAUDE.md 3.1, 3.10): the video is the business's promotion that ADO2 made from its public
information — its words are not this site's facts, so the block points to '방문 전 확인' — and ADO2 is the operator's
own service (the relationship, said once under the video). Nothing loads from the provider before the press: a poster
image (lazy) in a button, then the <video> (site.js [data-ado2]). Not a place photo (the poster never fills a photo
slot, CLAUDE.md 3.4), not structured data, not in the chat, not on the foreign editions (the videos speak Korean).
pipeline.validate checks the file (data_problems) and that every built place page with a video shows it (page_problems).
"""
from __future__ import annotations

import re
from urllib.parse import urlencode, urlsplit

from .textutil import squash_ws

TRACK = "ado2_click"   # GA4 (track.js): the 'Powered by ADO2' and the video-page links; data-provider = ado2
BLOCK = "ado2"
ANCHOR = "h-ado2"
FILE_HOST = "ado2mediastoragepublic.blob.core.windows.net"
VIDEOS_ID = "ado2"     # the /videos/ section id


def registry(S) -> dict:
    return getattr(S, "ado2", None) or {}


def service(S) -> dict | None:
    """{name, url (with this site as the referral source), about, maker} or None without a service address."""
    svc = registry(S).get("service") or {}
    url = str(svc.get("url") or "")
    if not url.startswith("https://"):
        return None
    host = urlsplit(getattr(S, "site_url", "") or "").hostname or ""
    q = urlencode({"utm_source": host or "travel-site", "utm_medium": "referral", "utm_campaign": "powered_by_ado2"})
    return {"name": squash_ws(svc.get("name")) or "ADO2", "url": f"{url}{'&' if '?' in url else '?'}{q}",
            "home": url, "about": str(svc.get("about") or ""), "maker": squash_ws(svc.get("maker"))}


def for_place(S, e: dict) -> dict | None:
    """The video of a built place (its Korean page), or None."""
    svc = service(S)
    row = (registry(S).get("places") or {}).get(e.get("id") or "")
    if not (svc and row and row.get("video") and row.get("poster")):
        return None
    return {"id": row.get("video_id"), "video": row["video"], "poster": row["poster"], "page": row.get("page") or "",
            "created": row.get("created") or "", "name": e["name"], "place": e.get("id") or "", "path": e.get("_path", ""),
            "kind": e.get("kind") or "", "type": e.get("_type") or "", "dong": e.get("_area") or "", "service": svc}


def shelf(S) -> list[dict]:
    """Every built place with a video, for /videos/: stays, then restaurants, then the rest; 가나다 inside (said on the
    page: not a recommendation)."""
    order = {"stay": 0, "food": 1}
    rows = [v for e in getattr(S, "entities", []) or [] if (v := for_place(S, e))]
    return sorted(rows, key=lambda v: (order.get(v["kind"], 2), v["name"]))


def _file_ok(url: str) -> bool:
    p = urlsplit(url or "")
    return p.scheme == "https" and p.hostname == FILE_HOST and not p.query and "/ado2-media-original/" in p.path


def data_problems(S) -> list[str]:
    """ado2.json (pipeline.validate): a service address; every place row names a place of the data, a public https
    video (.mp4) and poster (.jpg/.png) on the provider's file host without a signature, and its ADO2 page; no place
    twice. A row whose place is not built (a draft) is fine — it shows once the place is published."""
    rec = registry(S)
    if not rec:
        return []
    out = []
    if not service(S):
        out.append("service.url이 https 주소가 아님")
    known = {e.get("id") for e in getattr(S, "entities_all", []) or []}
    seen: dict[int, str] = {}
    for pid, row in (rec.get("places") or {}).items():
        name = row.get("name") or pid
        if known and pid not in known:
            out.append(f"{name}: 장소 id {pid}가 places.json에 없음")
        if not (_file_ok(row.get("video")) and str(row.get("video")).endswith(".mp4")):
            out.append(f"{name}: video가 ADO2 공개 파일(.mp4, 서명 없는 주소)이 아님 — {row.get('video')}")
        if not (_file_ok(row.get("poster")) and re.search(r"\.(jpe?g|png|webp)$", str(row.get("poster")))):
            out.append(f"{name}: poster가 ADO2 공개 이미지 주소가 아님 — {row.get('poster')}")
        if not str(row.get("page") or "").startswith("https://"):
            out.append(f"{name}: page(ADO2 영상 페이지) 없음")
        vid = row.get("video_id")
        if vid in seen:
            out.append(f"{name}: 영상 {vid}번이 {seen[vid]}에도 있음")
        seen[vid] = name
    return out


def page_problems(S, e: dict, html: str, block: str) -> list[str]:
    """A built Korean place page with a video shows it: the block (block = its visible text), the player button with
    the file, 'Powered by ADO2' linking to the service and the relationship ('운영사') inside the block; a page without
    a video has no block."""
    v = for_place(S, e)
    if not v:
        return ["ADO2 영상 상자가 있지만 ado2.json에 이 장소의 영상이 없음"] if f'data-block="{BLOCK}"' in html else []
    out = []
    if f'data-block="{BLOCK}"' not in html:
        return ["ADO2 영상 상자 없음"]
    if f'data-ado2="{v["video"]}"' not in html:
        out.append("ADO2 영상 재생 단추에 영상 주소가 없음")
    if "Powered by" not in block or v["service"]["home"] not in html:
        out.append("ADO2 영상 상자에 'Powered by ADO2' 링크 없음")
    if "운영사" not in block:
        out.append("ADO2 영상 상자에 관계 설명(군산각 운영사의 서비스) 없음")
    return out
