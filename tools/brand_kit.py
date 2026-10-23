"""수원각 brand kit: 정조대왕 팔각 어보·옹성 문장 + 수원화성 장안문 2층 누각과 성곽 여장·홍예문 + 플라잉수원 황금 열기구 + 방화수류정 용연·광교호수 물결 마크 for 수원각 (Suwongak).

    python tools/brand_kit.py templates/assets/brand

Writes suwongak-symbol.svg (decorative, inlined beside the site name: site.json brand_symbol), suwongak-app-icon.svg,
icon-48/96/180/192/512.png, apple-touch-icon.png and favicon.ico (16/32/48).
"""
import io
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_DEEP = "#7A2328"   # 수원화성 행궁·성곽 진홍 단청 (--brand, 흰 배경 대비 8.35:1)
DANCHEONG = "#C83E2B"    # 장안문·방화수류정 주홍 공포·서까래
ROOF_TILE = "#1F2937"    # 전통 기와 먹빛 남회색
BALLOON = "#FFB703"      # 플라잉수원 열기구·화성 달빛 황금 주황
GOLD_LIGHT = "#FFD54A"   # 홍예문 석축·윤슬 밝은 금빛
LAKE_BLUE = "#1D6FA5"    # 방화수류정 용연·광교호수 청록 파랑
CREAM = "#FFF8F0"        # 화성 한지·백자 따뜻한 아이보리 배경
W, H = 180, 180

# 팔각 어보·화성 옹성 문장 외곽·내곽 좌표 (180x180 기준)
OCT_OUTER = [
    (53, 11), (127, 11),
    (169, 53), (169, 127),
    (127, 169), (53, 169),
    (11, 127), (11, 53),
]
OCT_INNER = [
    (56, 18), (124, 18),
    (162, 56), (162, 124),
    (124, 162), (56, 162),
    (18, 124), (18, 56),
]


def _roof_tier(cx: float, w_bot: float, w_top: float, y_top: float, y_bot: float,
               sag_top: float, sag_bot: float, steps: int = 12) -> list[tuple[float, float]]:
    """처마 양끝이 하늘로 경쾌하게 들리고 중앙이 완만히 내려앉는 전통 팔작지붕 곡선 다각형."""
    pts: list[tuple[float, float]] = []
    x0_t, x1_t = cx - w_top / 2, cx + w_top / 2
    for i in range(steps + 1):
        t = i / steps
        u = 2 * t - 1
        x = x0_t + (x1_t - x0_t) * t
        y = y_top + sag_top * (1 - u * u)
        pts.append((round(x, 1), round(y, 1)))
    x0_b, x1_b = cx - w_bot / 2, cx + w_bot / 2
    for i in range(steps + 1):
        t = 1 - i / steps
        u = 2 * t - 1
        x = x0_b + (x1_b - x0_b) * t
        y = y_bot + sag_bot * (1 - u * u)
        pts.append((round(x, 1), round(y, 1)))
    return pts


ROOF_UPPER = _roof_tier(cx=82.0, w_bot=74.0, w_top=50.0, y_top=37.0, y_bot=49.0, sag_top=3.5, sag_bot=5.5)
ROOF_LOWER = _roof_tier(cx=82.0, w_bot=98.0, w_top=70.0, y_top=57.0, y_bot=70.0, sag_top=4.0, sag_bot=6.0)


def _poly_str(pts: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:g},{y:g}" for x, y in pts)


def _svg_inner() -> str:
    return (
        # 정조대왕 어보·수원화성 팔각 성곽 문장 배지
        f'<polygon points="{_poly_str(OCT_OUTER)}" fill="{BRAND_DEEP}"/>'
        f'<polygon points="{_poly_str(OCT_INNER)}" fill="{CREAM}"/>'
        # 플라잉수원 황금 열기구 (우측 상단 하늘)
        f'<circle cx="136" cy="48" r="14" fill="{BALLOON}"/>'
        f'<circle cx="136" cy="46" r="8" fill="{GOLD_LIGHT}"/>'
        f'<rect x="123" y="46" width="26" height="4.5" rx="2" fill="{BRAND_DEEP}"/>'
        f'<rect x="132" y="64" width="8" height="5" rx="1.5" fill="{BRAND_DEEP}"/>'
        # 장안문·방화수류정 2층 팔작지붕 누각 (상층 처마 + 단청 + 하층 처마 + 단청)
        f'<polygon points="{_poly_str(ROOF_UPPER)}" fill="{ROOF_TILE}"/>'
        f'<rect x="55" y="52" width="54" height="6.5" rx="1.5" fill="{DANCHEONG}"/>'
        f'<polygon points="{_poly_str(ROOF_LOWER)}" fill="{ROOF_TILE}"/>'
        f'<rect x="44" y="73" width="76" height="8" rx="1.5" fill="{DANCHEONG}"/>'
        # 수원화성 성곽 여장(성가퀴 5개) 및 성벽 본체
        f'<rect x="26" y="82" width="20" height="12" rx="2" fill="{BRAND_DEEP}"/>'
        f'<rect x="53" y="82" width="20" height="12" rx="2" fill="{BRAND_DEEP}"/>'
        f'<rect x="80" y="82" width="20" height="12" rx="2" fill="{BRAND_DEEP}"/>'
        f'<rect x="107" y="82" width="20" height="12" rx="2" fill="{BRAND_DEEP}"/>'
        f'<rect x="134" y="82" width="20" height="12" rx="2" fill="{BRAND_DEEP}"/>'
        f'<rect x="26" y="91" width="128" height="35" rx="4" fill="{BRAND_DEEP}"/>'
        # 장안문·팔달문 무지개 홍예문 (석축 아치 + 성문 내부)
        f'<path fill="{GOLD_LIGHT}" d="M64 126 L64 109 A26 26 0 0 1 116 109 L116 126 Z"/>'
        f'<path fill="{ROOF_TILE}" d="M70 126 L70 110 A20 20 0 0 1 110 110 L110 126 Z"/>'
        # 방화수류정 용연·광교호수 물결 + 황금 윤슬
        f'<rect x="42" y="133" width="96" height="9" rx="4.5" fill="{LAKE_BLUE}"/>'
        f'<rect x="60" y="146" width="60" height="8" rx="4" fill="{BALLOON}"/>'
    )


def symbol_svg(aria: bool = False) -> str:
    a11y = 'role="img" aria-label="수원각"' if aria else 'aria-hidden="true" focusable="false"'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" {a11y}>{_svg_inner()}</svg>\n'


def app_icon_svg(size: int = 512) -> str:
    s, r, m = size, 0.22 * size, 0.08 * size
    h = s - 2 * m
    k = h / H
    tx, ty = (s - W * k) / 2, m
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" role="img" aria-label="수원각">'
        f'<rect width="{s}" height="{s}" rx="{r:.1f}" fill="{CREAM}"/>'
        f'<g transform="translate({tx:.2f} {ty:.2f}) scale({k:.4f})">'
        f'{_svg_inner()}'
        f'</g></svg>\n'
    )


def draw_symbol(dr: ImageDraw.ImageDraw, tx: float, ty: float, k: float) -> None:
    """180x180 좌표계를 (tx, ty, scale=k)로 변환해 Pillow로 동일하게 렌더링"""
    def pt(x: float, y: float) -> tuple[float, float]:
        return (tx + x * k, ty + y * k)

    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (tx + x0 * k, ty + y0 * k, tx + x1 * k, ty + y1 * k)

    # 1. 팔각 성곽 문장 배경 및 테두리
    dr.polygon([pt(x, y) for x, y in OCT_OUTER], fill=BRAND_DEEP)
    dr.polygon([pt(x, y) for x, y in OCT_INNER], fill=CREAM)

    # 2. 플라잉수원 황금 열기구
    dr.ellipse(box(122, 34, 150, 62), fill=BALLOON)
    dr.ellipse(box(128, 38, 144, 54), fill=GOLD_LIGHT)
    dr.rounded_rectangle(box(123, 46, 149, 50.5), radius=2 * k, fill=BRAND_DEEP)
    dr.rounded_rectangle(box(132, 64, 140, 69), radius=1.5 * k, fill=BRAND_DEEP)

    # 3. 장안문 2층 팔작지붕 누각
    dr.polygon([pt(x, y) for x, y in ROOF_UPPER], fill=ROOF_TILE)
    dr.rounded_rectangle(box(55, 52, 109, 58.5), radius=1.5 * k, fill=DANCHEONG)
    dr.polygon([pt(x, y) for x, y in ROOF_LOWER], fill=ROOF_TILE)
    dr.rounded_rectangle(box(44, 73, 120, 81), radius=1.5 * k, fill=DANCHEONG)

    # 4. 수원화성 성곽 여장 5개 및 성벽 본체
    for mx in (26, 53, 80, 107, 134):
        dr.rounded_rectangle(box(mx, 82, mx + 20, 94), radius=2 * k, fill=BRAND_DEEP)
    dr.rounded_rectangle(box(26, 91, 154, 126), radius=4 * k, fill=BRAND_DEEP)

    # 5. 홍예문 (무지개 아치 성문)
    dr.pieslice(box(64, 83, 116, 135), start=180, end=360, fill=GOLD_LIGHT)
    dr.rectangle(box(64, 109, 116, 126), fill=GOLD_LIGHT)
    dr.pieslice(box(70, 90, 110, 130), start=180, end=360, fill=ROOF_TILE)
    dr.rectangle(box(70, 110, 110, 126), fill=ROOF_TILE)

    # 6. 방화수류정 용연·광교호수 물결 + 황금 윤슬
    dr.rounded_rectangle(box(42, 133, 138, 142), radius=4.5 * k, fill=LAKE_BLUE)
    dr.rounded_rectangle(box(60, 146, 120, 154), radius=4 * k, fill=BALLOON)


def draw_icon(size: int, rounded: bool, margin: float = 0.08, ss: int = 16) -> Image.Image:
    big = size * ss
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    if rounded:
        dr.rounded_rectangle((0, 0, big - 1, big - 1), radius=round(0.22 * big), fill=CREAM)
    else:
        dr.rectangle((0, 0, big, big), fill=CREAM)
    h = big * (1 - 2 * margin)
    k = h / H
    tx, ty = (big - W * k) / 2, big * margin
    draw_symbol(dr, tx, ty, k)
    return im.resize((size, size), Image.LANCZOS)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*gak-*.svg"):
        old.unlink()
    (out / "suwongak-symbol.svg").write_text(symbol_svg(), "utf-8", newline="\n")
    (out / "suwongak-app-icon.svg").write_text(app_icon_svg(), "utf-8", newline="\n")
    for n in (48, 96, 180, 192, 512):
        draw_icon(n, rounded=False).convert("RGB").save(out / f"icon-{n}.png", optimize=True)
    if (out / "icon-180.png").exists():
        shutil.copyfile(out / "icon-180.png", out / "apple-touch-icon.png")
    fav = {n: draw_icon(n, rounded=True, margin=0.05 if n <= 32 else 0.08) for n in (16, 32, 48)}
    buf = io.BytesIO()
    fav[48].save(buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[fav[16], fav[32]])
    (out / "favicon.ico").write_bytes(buf.getvalue())
    print("written to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "templates/assets/brand"))
