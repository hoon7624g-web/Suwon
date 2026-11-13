"""제휴 예약 링크 (operator decision at the 2026-11-03 meeting: '군산각에 있는 숙소는 제휴 링크 연결, 링크가 있는 예약사는
모두 노출'): a published stay's pages on the booking sites, through the affiliate network's links.

The registry is data/<region>/affiliate.json (build.State.affiliate):
- network: the affiliate network ({name, host, checked_at}); every link is an address on its host;
- providers: {key: {name, host, logo, logo_from}} in the order the links show — host = the booking site the link must
  open; logo = that site's own icon (templates/assets/ota/<key>.png, from logo_from), shown beside its name;
- places: {place id: {name, links: {provider key: {url, to}}}} — url = the network's link, to = the booking site's
  page of the stay it opened when it was checked (tracking values removed), kept so a person can check the match;
- hold: {place id: reason} — a stay whose links are not shown. A provider may carry hold: reason as well — none of
  its links is shown (they stay in the file): operator 2026-11-11 '야놀자 버튼은 일단 숨겨줘' — the network's 야놀자
  links end on 야놀자's home, not on the stay (below, provider_held).
Korean place pages of published stays show them under the official booking row, and the page STAYS_PATH (숙박
예약하기, every such stay as a card in a grid) shows them all (templates/_ui.html.j2 aff(), _staybook.html.j2:
data-block="affiliate", data-track="affiliate_click", rel="sponsored nofollow noopener", one line saying they are
affiliate links — the economic relationship a reader must be told). Nothing from the booking sites (no price, no
free rooms, no date: the booking site has them; a card's facts are this site's own data); the links are not structured data and not in the chat (CLAUDE.md 3.10: no booking).
pipeline.validate affiliate_problems checks every page against links_for(); data_problems checks the file.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from .textutil import link_url, squash_ws

TRACK = "affiliate_click"
BLOCK = "affiliate"
REL = "sponsored nofollow noopener"
# 숙박 예약하기 (operator 2026-11-03, after the stay pages: '메인 홈화면에 숙박 예약하기 버튼 … 바둑판식 배열로 사진과 함께'):
# the page of every stay with links (present.stay_booking_vm, templates/stay_booking.html.j2), opened from the home's
# first screen and the stays list
STAYS_PATH = "/stays/booking/"


def registry(S) -> dict:
    return getattr(S, "affiliate", None) or {}


def _host(url: str) -> str:
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


def on_host(url: str, host: str) -> bool:
    h, want = _host(url), (host or "").lower().removeprefix("www.")
    return bool(want) and (h == want or h.endswith("." + want))


def held(S, pid: str) -> bool:
    """Not shown: the registry's hold. (booking.json exclude_places keeps a place from the official booking buttons
    only: the client's stay shows its affiliate links since the operator's decision of 2026-11-04.)"""
    return pid in (registry(S).get("hold") or {})


def provider_held(prov: dict | None) -> bool:
    """A booking site whose links are not shown for now: providers.<key>.hold = the reason. (2026-11-11 야놀자: the
    network's link goes through 링크프라이스 to 야놀자's app link, which carries the stay only as an app address —
    on a computer and on a phone without the app it ends on 야놀자's home. The links stay in the file; taking the
    hold away shows them again.)"""
    return bool(squash_ws((prov or {}).get("hold")))


def links_for(S, e: dict | None) -> list[dict]:
    """The affiliate links a place's Korean page shows: [{key, name, url}] in the providers' order — only for a
    published stay that is not held, only addresses on the network's host and providers the registry names that
    are not held themselves."""
    reg = registry(S)
    if not reg or not e or e.get("kind") != "stay" or e.get("status") != "published" or held(S, e.get("id")):
        return []
    rec = (reg.get("places") or {}).get(e.get("id")) or {}
    links = rec.get("links") or {}
    net = (reg.get("network") or {}).get("host") or ""
    out = []
    for key, prov in (reg.get("providers") or {}).items():
        if provider_held(prov):
            continue
        url = link_url((links.get(key) or {}).get("url"))
        if url and on_host(url, net) and squash_ws(prov.get("name")):
            out.append({"key": key, "name": prov["name"], "url": url, "logo": prov.get("logo") or ""})
    return out


def stays(S) -> list[dict]:
    """The built stays that show affiliate links (in the data's order), computed once per State."""
    got = getattr(S, "_aff_stays", None)
    if got is None:
        got = [e for e in getattr(S, "entities", None) or [] if links_for(S, e)]
        S._aff_stays = got
    return got


def data_problems(S) -> list[str]:
    """affiliate.json itself (pipeline.validate): the network has its name, host and checked date; every provider its
    name and host; every place id is a stay of the data with that name; every link names a known provider, is an
    address on the network's host, used once, and records the provider's page it opened (to) on the provider's host;
    every hold (a stay's or a provider's) has its reason."""
    reg = registry(S)
    if not reg:
        return []
    out = []
    net = reg.get("network") or {}
    for k in ("name", "host", "checked_at"):
        if not squash_ws(net.get(k)):
            out.append(f"network: {k} 없음")
    providers = reg.get("providers") or {}
    assets = Path(__file__).resolve().parent.parent / "templates"
    for key, prov in providers.items():
        for k in ("name", "host"):
            if not squash_ws(prov.get(k)):
                out.append(f"providers.{key}: {k} 없음")
        logo = prov.get("logo") or ""
        if logo and not (logo.startswith("/assets/") and (assets / logo.lstrip("/")).is_file()):
            out.append(f"providers.{key}: 로고 파일이 templates{logo}에 없음")
        if "hold" in prov and not provider_held(prov):
            out.append(f"providers.{key}.hold: 이유 없음")
    ents = {e.get("id"): e for e in getattr(S, "entities_all", None) or []}
    seen: dict[str, str] = {}
    for pid, rec in (reg.get("places") or {}).items():
        e = ents.get(pid)
        if not e:
            out.append(f"places.{pid}: places.json에 없는 장소")
        elif e.get("kind") != "stay":
            out.append(f"places.{pid}: 숙소가 아님({e.get('kind')})")
        elif squash_ws(rec.get("name")) != squash_ws(e.get("name")):
            out.append(f"places.{pid}: 이름이 places.json과 다름 — {rec.get('name')} / {e.get('name')}")
        if not rec.get("links"):
            out.append(f"places.{pid}: links 없음")
        for key, ln in (rec.get("links") or {}).items():
            url, to = (ln or {}).get("url") or "", (ln or {}).get("to") or ""
            if key not in providers:
                out.append(f"places.{pid}: 없는 예약사 {key}")
            if not link_url(url) or not on_host(url, net.get("host")):
                out.append(f"places.{pid}.{key}: 제휴 네트워크({net.get('host')}) 주소가 아님: {url}")
            elif url in seen:
                out.append(f"places.{pid}.{key}: 같은 링크를 {seen[url]}에서도 씀: {url}")
            seen.setdefault(url, f"{pid}.{key}")
            if key in providers and not on_host(to, providers[key].get("host")):
                out.append(f"places.{pid}.{key}: 연 페이지(to)가 {providers[key].get('host')}가 아님: {to or '없음'}")
    for pid, why in (reg.get("hold") or {}).items():
        if not squash_ws(why):
            out.append(f"hold.{pid}: 이유 없음")
    return out


def all_urls(S) -> set[str]:
    """Every link the registry holds (shown or held) — a page may open one only inside its affiliate block."""
    return {ln.get("url") for rec in (registry(S).get("places") or {}).values()
            for ln in (rec.get("links") or {}).values() if ln.get("url")}
