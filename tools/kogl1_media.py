"""Resized AVIF/WebP derivatives of KOGL-1 photos — only those a page crops, zooms or shows full-bleed.

    python tools/kogl1_media.py --data data/suwon               # download what is missing, encode, write manifest
    python tools/kogl1_media.py --data data/suwon --dry-run     # list what would be made, change nothing

Options: --data DIR (required: the city's data folder), --out DIR, --cache DIR, --max-downloads N (default 200),
--dry-run, --force (re-encode existing derivatives), --keep-stale (do not delete derivatives no longer wanted).

Which photos (pipeline/media.py wanted()) — of published records only (the production selection; drafts and
reviewed records get none, design Q14): the configured home photo slots, and every place whose lead photo is KOGL-1
(the full-bleed place opening). KOGL-3 (공공누리 제3유형, 변경금지) photos are never touched — each photo is checked
against its stored licence before it is encoded. All derivatives together stay within BUDGET_BYTES (15MB): the
home's opening photos first, then by URL; a photo whose files would cross the budget is not made (reported, exit 1).
No published photo wanted: an empty manifest and no derivative files.

Why: the opening photo is the mobile LCP element. The provider original is an 80–230KB JPEG on a third-party
origin (DNS + TLS on a slow link); a same-origin AVIF at 480/940w is 14–60KB. KOGL-1 allows change with
attribution, and the credit under every photo stays "출처: 한국관광공사". Nothing is upscaled: the widest file is
the source width. The opening slides get a lighter encode (the home's LCP image, a 3:2 product shot).

Output: templates/assets/media/<contentid>-<width>[h].<avif|webp> and manifest.json
{provider url: {"w", "h", "slot", "avif": [[path, width, bytes], …], "webp": [...]}}. The build copies the folder
with the other assets; pipeline/media.attach() adds the srcsets to the photo dicts.
Originals are cached in data/cache/kogl1-src/ (git-ignored); existing derivatives are kept (--force re-encodes).
--max-downloads caps the requests of one run. Outbound HTTPS uses HTTPS_PROXY / SSL_CERT_FILE from the
environment. Re-run after tools/tourapi_bulk.py or tools/tourapi_details.py changes photos.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import media  # noqa: E402
from pipeline.schema import PHOTO_SOURCES  # noqa: E402

WIDTHS = {"cover": (480, 940, 1280), "hero": (480, 940, 1280), "k1": (480, 940, 1280)}   # cover: the full-bleed home photo
QUALITY = {"cover": {"avif": 72, "webp": 86}, "hero": {"avif": 64, "webp": 80}, "k1": {"avif": 64, "webp": 80}}
UA = "Mozilla/5.0 (compatible; kogl1-media)"
BUDGET_BYTES = 15 * 1024 * 1024  # every derivative together (tests/test_media_behaviour.py holds the same bound)


def stem_of(url: str) -> str:
    name = url.rsplit("/", 1)[-1].lower()
    return name.rsplit(".", 1)[0].replace("_image2_1", "")


def licence_of(S, url: str) -> str:
    """The stored licence of a photo URL (any place that shows it); '' when not found."""
    for e in S.entities:
        for im in e.get("_images") or []:
            if im.get("url") == url and im.get("source") in PHOTO_SOURCES:
                return im.get("license") or ""
    return ""


def fetch(url: str, cache: Path, budget: list[int]) -> Path | None:
    raw = cache / url.rsplit("/", 1)[-1].lower()
    if raw.exists() and raw.stat().st_size:
        return raw
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    req = urllib.request.Request(url.replace("http://", "https://", 1), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    cache.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(body)
    return raw


def encode(raw: Path, url: str, slot: str, out: Path, force: bool) -> dict:
    from PIL import Image  # Pillow with AVIF (pillow>=11.3 ships libavif)

    im = Image.open(raw).convert("RGB")
    W, H = im.size
    stem, mark = stem_of(url), "h" if slot == "hero" else ""
    entry = {"w": W, "h": H, "slot": slot, "avif": [], "webp": []}
    for target in WIDTHS[slot]:
        w = min(target, W)
        h = round(H * w / W)
        frame = im if w == W else im.resize((w, h), Image.LANCZOS)
        for fmt in ("avif", "webp"):
            path = out / f"{stem}-{w}{mark}.{fmt}"
            if force or not path.exists():
                buf = io.BytesIO()
                opts = {"quality": QUALITY[slot][fmt], "speed": 4} if fmt == "avif" else \
                    {"quality": QUALITY[slot][fmt], "method": 6}
                frame.save(buf, fmt.upper(), **opts)
                path.write_bytes(buf.getvalue())
            entry[fmt].append([media.URL_PREFIX + path.name, w, path.stat().st_size])
        if w == W:
            break
    return entry


def _files(entry: dict) -> list[tuple[str, int]]:
    """(file name, bytes) of every derivative of one manifest entry."""
    return [(Path(p).name, b) for fmt in ("avif", "webp") for p, _, b in entry[fmt]]


def run(data_dir: Path, out: Path = media.MEDIA_DIR, cache: Path = ROOT / "data" / "cache" / "kogl1-src",
        max_downloads: int = 200, dry_run: bool = False, force: bool = False, prune: bool = True,
        budget_bytes: int = BUDGET_BYTES) -> dict:
    from pipeline.build import State

    S = State(Path(data_dir), "production")  # published records only: drafts and reviewed records get no derivative
    want = media.wanted(S)
    for url in want:  # KOGL-1 only, by construction — and checked against the stored licence again here
        lic = licence_of(S, url)
        if lic != "KOGL-1":
            raise SystemExit(f"공공누리 제1유형이 아닌 사진은 변환하지 않습니다: {url} ({lic or '라이선스 없음'})")
    if dry_run:
        for url, slot in want.items():
            print(f"{slot}\t{url}")
        print(f"공개(published) 기록의 제1유형 사진 {len(want)}장 (변환 안 함, --dry-run)")
        return {"photos": len(want), "dry_run": True}
    out.mkdir(parents=True, exist_ok=True)
    budget, man, skipped, total = [max_downloads], {}, [], 0
    for url, slot in sorted(want.items(), key=lambda kv: (kv[1] not in ("cover", "hero"), kv[1] != "cover", kv[0])):  # the home's cover, then its slides, first
        try:
            raw = fetch(url, cache, budget)
        except OSError as exc:  # the provider's own error text, as is
            skipped.append(f"{url}: {exc}")
            continue
        if raw is None:
            skipped.append(f"{url}: 실행당 내려받기 상한(--max-downloads {max_downloads}) 도달")
            continue
        entry = encode(raw, url, slot, out, force)
        size = sum(b for _, b in _files(entry))
        if total + size > budget_bytes:  # the whole set stays within the budget: this photo is not made
            kept = {name for v in man.values() for name, _ in _files(v)}
            for name, _ in _files(entry):
                if name not in kept:
                    (out / name).unlink(missing_ok=True)
            skipped.append(f"{url}: 파생 이미지 예산 {budget_bytes / 1024 / 1024:g}MB를 넘어 만들지 않음 "
                           f"(지금 {total / 1024 / 1024:.1f}MB + {size / 1024:.0f}KB)")
            continue
        man[url], total = entry, total + size
    keep = {Path(p).name for v in man.values() for fmt in ("avif", "webp") for p, *_ in v[fmt]}
    removed = 0
    if prune:
        for f in out.iterdir():
            if f.suffix in (".avif", ".webp") and f.name not in keep:
                f.unlink()
                removed += 1
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
    files = sum(len(v["avif"]) + len(v["webp"]) for v in man.values())
    total = sum(b for v in man.values() for fmt in ("avif", "webp") for _, _, b in v[fmt])
    report = {"photos": len(man), "files": files, "kb": round(total / 1024), "removed": removed,
              "skipped": skipped, "hero": sum(1 for v in man.values() if v["slot"] == "hero"), "cover": sum(1 for v in man.values() if v["slot"] == "cover")}
    print(json.dumps(report, ensure_ascii=False))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="the city's data folder (e.g. data/suwon)")
    ap.add_argument("--out", type=Path, default=media.MEDIA_DIR)
    ap.add_argument("--cache", type=Path, default=ROOT / "data" / "cache" / "kogl1-src")
    ap.add_argument("--max-downloads", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-encode derivatives that already exist")
    ap.add_argument("--keep-stale", action="store_true", help="do not delete derivatives no longer wanted")
    a = ap.parse_args(argv)
    report = run(a.data, a.out, a.cache, a.max_downloads, a.dry_run, a.force, not a.keep_stale)
    return 1 if report.get("skipped") else 0


if __name__ == "__main__":
    sys.exit(main())
