"""수원각 brand kit: 책갈피 마크 (수원화성 행궁 단청 적색 #7A2328 + 방화수류정·장안문 누각 처마 + 플라잉수원·화성 보름달 황금 원 #FFD54A + 광교호수·용연 물결) for 수원각 (Suwongak).

    python tools/brand_kit.py templates/assets/brand

Writes suwongak-symbol.svg (decorative, inlined beside the site name: site.json brand_symbol), suwongak-app-icon.svg,
icon-48/96/180/192/512.png (full-bleed squares, as the first site's), apple-touch-icon.png and favicon.ico (16/32/48,
rounded, the small form). The PNGs are drawn from the same shapes with Pillow (16x supersampled), so the SVG and the
PNGs cannot drift.

The bookmark is the family shape of 군산각·대구각·세종각·강릉각·용인각·수원각; Suwon royal crimson #7A2328 (8.35:1 on white) is the
symbol and the 각 of the name; inside sit a curved traditional pavilion eave (방화수류정·장안문 처마, 각/閣), the golden
full-moon / hot-air balloon disk (#FFD54A) over Hwaseong Fortress, and two calm horizon wave bars (용연·광교호수) below."""
import io
import math
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_DEEP, YEL, WHITE = "#7A2328", "#FFD54A", "#FFFFFF"

# the bookmark in a 100 x 162 box
W, H, NOTCH, R = 100, 162, 134, 5


def _eave(x0: float, x1: float, y_top_edge: float, sag_top: float,
          dx_in: float, y_bot_edge: float, sag_bot: float, steps: int = 16) -> list[tuple[float, float]]:
    """A smooth upturned traditional Korean roof eave (방화수류정·장안문 처마 곡선) sampled symmetrically."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 2 * t - 1
        x = x0 + (x1 - x0) * t
        y = y_top_edge + sag_top * (1 - u * u)
        pts.append((round(x, 1), round(y, 1)))
    for i in range(steps + 1):
        t = 1 - i / steps
        u = 2 * t - 1
        x = (x0 + dx_in) + ((x1 - dx_in) - (x0 + dx_in)) * t
        y = y_bot_edge + sag_bot * (1 - u * u)
        pts.append((round(x, 1), round(y, 1)))
    return pts


# the curved pavilion eave (방화수류정·장안문 전통 처마) crowning the top of the bookmark
EAVE = _eave(16, 84, 21.0, 6.0, 4.0, 33.5, 5.0)
# the outer halo cutout and golden core (수원화성 달빛 · 플라잉수원 열기구)
RING = (50, 72, 24)
DOT = (50, 72, 13)
# two calm horizon water reflection bars (방화수류정 용연 · 광교호수공원) below the disk
WAVE1 = [(22, 104), (78, 104), (78, 112), (22, 112)]
WAVE2 = [(32, 118), (68, 118), (68, 125), (32, 125)]

# the small form (favicon 16/32 px): bolder eave and disk
EAVE_S = _eave(15, 85, 19.5, 6.0, 4.0, 35.0, 5.0)
RING_S = (50, 78, 27)
DOT_S = (50, 78, 13)


def bookmark_points(steps: int = 12) -> list[tuple[float, float]]:
    """The outline with its two rounded top corners as points (for Pillow)."""
    pts = []
    for cx, a0 in ((W - R, -90), (R, 180)):
        if cx == R:
            pts += [(W, H), (W / 2, NOTCH), (0, H)]
        for k in range(steps + 1):
            a = math.radians(a0 + 90 * k / steps)
            pts.append((cx + R * math.cos(a), R + R * math.sin(a)))
    return pts


def bookmark_d() -> str:
    return f"M{R} 0H{W - R}A{R} {R} 0 0 1 {W} {R}V{H}L{W / 2:g} {NOTCH}L0 {H}V{R}A{R} {R} 0 0 1 {R} 0Z"


def poly_d(pts) -> str:
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in pts) + "Z"


def circle_d(cx, cy, r) -> str:
    return f"M{cx - r:g} {cy:g}A{r:g} {r:g} 0 1 0 {cx + r:g} {cy:g}A{r:g} {r:g} 0 1 0 {cx - r:g} {cy:g}Z"


def symbol_paths(fill: str, dot: str | None, small: bool = False) -> str:
    eave = EAVE_S if small else EAVE
    ring = RING_S if small else RING
    core = DOT_S if small else DOT
    d = bookmark_d() + poly_d(eave) + circle_d(*ring) + ("" if small else (poly_d(WAVE1) + poly_d(WAVE2)))
    if dot is None:
        d += circle_d(*core)
    out = f'<path fill="{fill}" fill-rule="evenodd" d="{d}"/>'
    if dot and not small:
        out += f'<path fill="{dot}" d="{circle_d(*core)}"/>'
    return out


def symbol_svg() -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" aria-hidden="true" focusable="false">'
            f"{symbol_paths(BRAND_DEEP, YEL)}</svg>\n")


def icon_box(size: float, margin: float) -> tuple[float, float, float]:
    sc = size * (1 - 2 * margin) / H
    return sc, (size - W * sc) / 2, size * margin


def app_icon_svg(size: int = 512) -> str:
    sc, x, y = icon_box(size, .18)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="수원각">'
            f'<rect width="{size}" height="{size}" rx="{.22 * size:.1f}" fill="{BRAND_DEEP}"/>'
            f'<g transform="translate({x:.2f} {y:.2f}) scale({sc:.4f})">{symbol_paths(WHITE, None)}</g></svg>\n')


def draw_icon(size: int, rounded: bool, small: bool, margin: float, ss: int = 16) -> Image.Image:
    big = size * ss
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    if rounded:
        dr.rounded_rectangle((0, 0, big - 1, big - 1), radius=.22 * big, fill=BRAND_DEEP)
    else:
        dr.rectangle((0, 0, big, big), fill=BRAND_DEEP)
    sc, x, y = icon_box(big, margin)
    tr = lambda pts: [(x + px * sc, y + py * sc) for px, py in pts]
    dr.polygon(tr(bookmark_points(24)), fill=WHITE)
    dr.polygon(tr(EAVE_S if small else EAVE), fill=BRAND_DEEP)
    cx, cy, r = RING_S if small else RING
    dr.ellipse((x + (cx - r) * sc, y + (cy - r) * sc, x + (cx + r) * sc, y + (cy + r) * sc), fill=BRAND_DEEP)
    cx2, cy2, r2 = DOT_S if small else DOT
    dr.ellipse((x + (cx2 - r2) * sc, y + (cy2 - r2) * sc, x + (cx2 + r2) * sc, y + (cy2 + r2) * sc), fill=WHITE)
    if not small:
        dr.polygon(tr(WAVE1), fill=BRAND_DEEP)
        dr.polygon(tr(WAVE2), fill=BRAND_DEEP)
    return im.resize((size, size), Image.LANCZOS)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in (list(out.glob("sejonggak-*")) + list(out.glob("jejugak-*"))
                + list(out.glob("yeongjugak-*")) + list(out.glob("gangneunggak-*"))
                + list(out.glob("yongingak-*"))):
        old.unlink()
    (out / "suwongak-symbol.svg").write_text(symbol_svg(), "utf-8")
    (out / "suwongak-app-icon.svg").write_text(app_icon_svg(), "utf-8")
    for n in (48, 96, 180, 192, 512):
        draw_icon(n, rounded=False, small=False, margin=.18).convert("RGB").save(out / f"icon-{n}.png", optimize=True)
    shutil.copyfile(out / "icon-180.png", out / "apple-touch-icon.png")
    fav = {n: draw_icon(n, rounded=True, small=n <= 32, margin=.12 if n <= 32 else .18) for n in (16, 32, 48)}
    buf = io.BytesIO()
    fav[48].save(buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[fav[16], fav[32]])
    (out / "favicon.ico").write_bytes(buf.getvalue())
    print("written to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "templates/assets/brand"))
