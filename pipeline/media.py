"""Same-origin AVIF/WebP derivatives of KOGL-1 photos, and the photo slots that use them (CLAUDE.md 3.4, 7).

KOGL-1 (공공누리 제1유형) photos may be resized and re-encoded as long as the credit stays ("출처: 한국관광공사").
KOGL-3 (제3유형, 변경금지) photos never are: a page always shows the provider's own file, whole.

Derivatives exist only for KOGL-1 photos that a page crops, zooms or shows full-bleed:
  - the home's configured photo slots that need KOGL-1 (the opening cover and slides) and the KOGL-1 photos of
    its story chapters and gallery cards — slots whose treatment needs KOGL-1 go through pick_photo(…, need_k1=True);
  - every place whose lead photo is KOGL-1 (the full-bleed place opening; it is that page's LCP image).
tools/kogl1_media.py writes them to templates/assets/media/ with manifest.json; the build copies the folder with
the other assets and present.prepare() calls attach(), so every photo dict carries:

  ph.avif, ph.webp   srcset strings ("/assets/media/3414700-480.avif 480w, /assets/media/3414700-940.avif 940w"),
                     '' when the photo has no derivative (always '' for KOGL-3)
  ph.w, ph.h         the source's intrinsic size (the manifest fills it when image_sizes.json has none)
  ph.url             the provider original — the <img src> fallback inside <picture>
  ph.type            1 or 3

A missing or empty manifest is allowed (Q15: a city without photos yet) — no photo then has a derivative, and
manifest_problems() asks only that no derivative file is left on disk. templates/_media.html.j2 turns the fields
into <picture>/srcset with width/height, and a <link rel=preload>.

The home's photo slots are site.json `home` (S.city.home), each naming a place by its `id` (a slug may still change
before publication) and the n-th of its licensed photos (the last one when it has fewer):
  home.media.cover    [place_id, n] or null   the full-bleed opening photo, cropped to the screen: KOGL-1 only
  home.media.hero     [[place_id, n], …]      the opening slides, cropped 3:2 and pushed in: KOGL-1 only
  home.media.gallery  [[place_id, n], …]      the gallery cards: either licence (KOGL-1 cropped, KOGL-3 whole)
  home.story[].photo  [place_id, n]           a story chapter's photo (keyed by story_id): either licence
This module is the one place that decides them: slot_photos(S) is what the home shows (pipeline.present.home_vm),
wanted(S) what tools/kogl1_media.py derives. A slot whose place is not built or has no usable photo is left out with
a warning (S.warnings); with nothing configured there is no cover, no slide, no story photo and no gallery card.
"""
from __future__ import annotations

import json
from pathlib import Path

from .slugs import SLUG_RE, anchor_id
from .textutil import squash_ws

ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT / "templates" / "assets" / "media"
MANIFEST = MEDIA_DIR / "manifest.json"
URL_PREFIX = "/assets/media/"
MEDIA_BUDGET = 15 * 1024 * 1024   # every derivative together (Q14: KOGL-1 photos of published places only)
FORMATS = ("avif", "webp")


def load_manifest(path: Path = MANIFEST) -> dict:
    """{provider url: {"w", "h", "avif": [[path, width, bytes], …], "webp": [...]}}; {} when absent or unreadable."""
    try:
        return json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {}
    except (OSError, ValueError):
        return {}


def srcset(files: list) -> str:
    return ", ".join(f"{p} {w}w" for p, w, *_ in files)


def smallest(ph: dict) -> tuple[str, int, int] | None:
    """(url, width, height) of the smallest same-origin WebP derivative of a KOGL-1 photo, or None. List rows and
    cards (present.thumb) use it when the provider has no small copy of its own, so a 69-98 px row never downloads
    a 1280 px original (the TourAPI photo gallery has no small copies)."""
    if ph.get("type") != 1 or not ph.get("webp") or not (ph.get("w") and ph.get("h")):
        return None
    files = [p.rsplit(" ", 1) for p in ph["webp"].split(", ")]
    url, w = min(((u, int(d[:-1])) for u, d in files if d.endswith("w") and d[:-1].isdigit()), key=lambda x: x[1])
    return url, w, round(w * ph["h"] / ph["w"])


def attach(S, manifest: dict | None = None) -> None:
    """Add avif/webp srcsets (and a missing intrinsic size) to every photo of every place. KOGL-1 only: a manifest
    entry for any other photo is ignored, so a mistaken derivative can never reach a page."""
    man = load_manifest() if manifest is None else manifest
    for e in S.entities:
        for ph in e.get("_photos") or []:
            entry = (man or {}).get(ph["url"]) if ph.get("type") == 1 else None
            ph["avif"] = srcset(entry["avif"]) if entry and entry.get("avif") else ""
            ph["webp"] = srcset(entry["webp"]) if entry and entry.get("webp") else ""
            if entry and not (ph.get("w") and ph.get("h")):
                ph["w"], ph["h"] = entry["w"], entry["h"]
                ph["ar"] = f"{entry['w']}/{entry['h']}"


def manifest_problems(manifest: dict | None, licences: dict, media_dir: Path = MEDIA_DIR,
                      budget: int = MEDIA_BUDGET) -> list[str]:
    """What is wrong with the derivatives (Korean, one line each; [] when nothing):
    - an entry whose photo is not KOGL-1 in the data (licences: {provider url: licence code}) — KOGL-3 (변경금지) is
      never re-encoded;
    - a format without a file; a file path outside URL_PREFIX, a file missing or not of the listed size, a width
      above the source's (nothing is upscaled);
    - an .avif / .webp in media_dir that the manifest does not list (a stray derivative would ship with the assets);
    - more than `budget` bytes in all.
    An empty or missing manifest with no derivative on disk has no problem (Q15)."""
    out, total, listed = [], 0, set()
    media_dir = Path(media_dir)
    for url, entry in sorted((manifest or {}).items()):
        entry = entry if isinstance(entry, dict) else {}
        if licences.get(url) != "KOGL-1":
            out.append(f"{url}: 공공누리 제1유형이 아닌 사진({licences.get(url) or '라이선스 없음'})의 파생 이미지")
        for fmt in FORMATS:
            files = entry.get(fmt) or []
            if not files:
                out.append(f"{url}: {fmt} 파일 없음")
            for path, width, size in files:
                f = media_dir / Path(path).name
                listed.add(f.name)
                total += size
                if not str(path).startswith(URL_PREFIX):
                    out.append(f"{url}: {URL_PREFIX} 밖의 경로 {path}")
                elif not f.exists() or f.stat().st_size != size:
                    out.append(f"{url}: 파일 없음 또는 크기가 manifest와 다름 {path}")
                if width > (entry.get("w") or 0):
                    out.append(f"{url}: 원본 너비({entry.get('w')})보다 큰 파생 이미지 {path}")
    on_disk = {f.name for f in media_dir.iterdir() if f.suffix[1:] in FORMATS} if media_dir.is_dir() else set()
    out += [f"manifest에 없는 파생 이미지 파일(남은 파일): {name}" for name in sorted(on_disk - listed)]
    if total > budget:
        out.append(f"파생 이미지 합계 {total:,}바이트가 상한 {budget:,}바이트를 넘음")
    return out


# ------------------------------------------------------------------ the home's photo slots (site.json home)
# The one decision of which photo fills which home slot: present.home_vm shows slot_photos(S), tools/kogl1_media.py
# derives wanted(S) from the same references, so a page never shows a slot photo the derivatives missed.
SLOT_WHAT = {"cover": "표지 사진", "hero": "첫 화면 사진", "gallery": "갤러리 사진", "story": "이야기 사진"}
NEED_K1 = {"cover": True, "hero": True, "gallery": False, "story": False}   # cropped / zoomed: KOGL-1 only


def story_id(ch: dict) -> str:
    """A story chapter's key and fragment id: its configured id when it is ASCII ('ch-1899'), else an ASCII id
    from it (slugs.anchor_id)."""
    cid = squash_ws(ch.get("id"))
    return cid if cid and SLUG_RE.match(cid) else anchor_id("ch", cid or squash_ws(ch.get("big")) or "story")


def _ref(ref) -> tuple[str, int] | None:
    """(place_id, n) of a photo reference — [place_id, n] or {place_id, n} (n a whole number ≥ 0, default 0);
    None for anything else."""
    pid, n = (ref.get("place_id"), ref.get("n", 0)) if isinstance(ref, dict) else \
        (ref if isinstance(ref, (list, tuple)) and len(ref) == 2 else (None, None))
    if isinstance(pid, str) and pid.strip() and isinstance(n, int) and not isinstance(n, bool) and n >= 0:
        return pid.strip(), n
    return None


def home_refs(S) -> list[tuple[str, str, object]]:
    """The configured photo references of the home, in slot order: (slot, key, reference as written) — slot cover,
    hero, gallery or story; key '' except a story chapter's story_id. Nothing configured: []."""
    home = S.city.home
    m = home.get("media") if isinstance(home.get("media"), dict) else {}
    out = [("cover", "", m["cover"])] if m.get("cover") else []
    out += [(slot, "", r) for slot in ("hero", "gallery") for r in m.get(slot) or []]
    out += [("story", story_id(ch), ch["photo"]) for ch in home.get("story") or []
            if isinstance(ch, dict) and ch.get("photo")]
    return out


def home_place(S, pid: str | None, what: str) -> dict | None:
    """A built place a home block of site.json names by its id (never a slug: it may still change before
    publication); a warning and None when the build has no such place."""
    pid = squash_ws(pid)
    e = next((x for x in S.entities if x.get("id") == pid), None) if pid else None
    if pid and not e:
        S.warnings.append(f"홈 {what}: 장소 없음 {pid} — 그 블록 생략")
    return e


def _photo(e: dict, pid: str, n: int, need_k1: bool, what: str) -> tuple[dict | None, str]:
    """(photo n of place e — the last one when it has fewer — with the place's name, path, slug, id and kind, '') or
    (None, why)."""
    photos = e.get("_photos") or []
    if not photos:
        return None, f"홈 {what}: {e['name']}({pid})에 쓸 수 있는 사진 없음 — 그 자리 생략"
    ph = photos[min(n, len(photos) - 1)]
    if need_k1 and ph.get("type") != 1:
        return None, (f"홈 {what}: {e['name']}({pid} #{n})은 공공누리 제{ph.get('type')}유형 — "
                      "자르거나 확대하는 자리에 쓰지 않음")
    return {**ph, "place": e["name"], "path": e["_path"], "slug": e.get("slug", ""), "id": e.get("id", ""),
            "kind": e.get("kind", "")}, ""


def pick_photo(S, ref, need_k1: bool = True, what: str = "사진 자리") -> dict | None:
    """Photo n of the place a reference names by id ([place_id, n]: the last photo when it has fewer). A slot that
    crops or zooms passes need_k1=True: a KOGL-3 photo is then refused (never cropped or zoomed). A malformed
    reference, a place the build does not have or no usable photo: a warning (S.warnings) and None."""
    r = _ref(ref)
    if r is None:
        S.warnings.append(f"홈 {what}: 사진 자리 형식 오류 {ref!r}([place_id, n]) — 그 자리 생략")
        return None
    e = home_place(S, r[0], what)
    if not e:
        return None
    ph, why = _photo(e, *r, need_k1, what)
    if why:
        S.warnings.append(why)
    return ph


def slot_photos(S) -> dict:
    """The home's photo slots (home_refs): hero (KOGL-1 only: cropped and pushed in), cover (the full-bleed opening
    photo, KOGL-1 only; None when not configured or refused), story ({story_id: photo}, either licence, None for a
    refused one) and gallery (either licence; templates crop KOGL-1 cards and show KOGL-3 cards whole). A slot that
    cannot be filled is left out with a warning; nothing configured: no slot and no warning."""
    out: dict = {"hero": [], "cover": None, "story": {}, "gallery": []}
    for slot, key, ref in home_refs(S):
        ph = pick_photo(S, ref, NEED_K1[slot], SLOT_WHAT[slot])
        if slot == "cover":
            out["cover"] = ph
        elif slot == "story":
            out["story"][key] = ph
        elif ph:
            out[slot].append(ph)
    return out


def cover_problems(S) -> list[str]:
    """Why the home's full-bleed opening photo (site.json home.media.cover) would not be shown, or []. The template drops a cover
    without its AVIF derivative without a word (2026-10-28: 세종각·목포각 lost theirs — merged TourAPI photos moved
    the place's photos, so the configured photo number named another photo, one tools/kogl1_media.py never encoded).
    pipeline/validate.py reports these as errors in production, warnings otherwise."""
    home = S.city.home
    m = home.get("media") if isinstance(home.get("media"), dict) else {}
    if not m.get("cover"):
        return []
    r = _ref(m["cover"])
    if r is None:
        return [f"홈 표지 사진: 사진 자리 형식 오류 {m['cover']!r}([place_id, n])"]
    key, n = r
    e = next((x for x in S.entities if x.get("id") == key), None)
    if not e:   # a build with no places yet (a new city, tests/test_empty_city) has no cover to show (fix2)
        return [f"홈 표지 사진: 장소 없음 {key}"] if S.entities else []
    ph, why = _photo(e, key, n, True, "표지 사진")
    if why:
        return [why]
    if not ph.get("avif"):
        ready = [f"#{i}" for i, p in enumerate(e.get("_photos") or []) if p.get("type") == 1 and p.get("avif")]
        hint = f"변환본 있는 사진: {', '.join(ready)}" if ready else "tools/kogl1_media.py로 변환본을 만든다"
        return [f"홈 표지 사진: {e['name']}({key} #{n}, {ph.get('url')})에 변환본(AVIF)이 없어 첫 화면 배경이 빠짐 — {hint}"]
    return []


def wanted(S) -> dict:
    """{url: slot} for every KOGL-1 photo that gets derivatives (no warning here: present reports the slots); slot
    'cover' (the full-bleed home opening: up to 1280w, a fuller encode — it fills a wide screen, the LCP image),
    'hero' (the opening slides: a lighter encode, small on phones) or 'k1' — the KOGL-1 photos of the story and
    gallery slots and every place's KOGL-1 lead photo. Used by tools/kogl1_media.py."""
    by_id = {e.get("id"): e for e in S.entities if e.get("id")}
    out: dict[str, str] = {}
    for slot, _, ref in sorted(home_refs(S), key=lambda x: x[0] not in ("cover", "hero")):
        r = _ref(ref)
        e = by_id.get(r[0]) if r else None
        ph = _photo(e, *r, True, "")[0] if e else None
        if ph:
            out.setdefault(ph["url"], slot if slot in ("cover", "hero") else "k1")
    for e in S.entities:
        photos = e.get("_photos") or []
        if photos and photos[0].get("type") == 1:
            out.setdefault(photos[0]["url"], "k1")
    return out


def preload(ph: dict | None, sizes: str = "100vw") -> dict | None:
    """<link rel=preload> fields for a page's first-screen KOGL-1 photo; None when it has no AVIF derivative."""
    if not ph or ph.get("type") != 1 or not ph.get("avif"):
        return None
    return {"srcset": ph["avif"], "type": "image/avif", "sizes": sizes}
