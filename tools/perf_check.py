"""모바일 체감 속도 점검 — 느린 4G·저사양 폰을 흉내 내 LCP·CLS·전송량을 잰다.

    python tools/perf_check.py --out public                      # 기본 페이지(빌드 결과에서 고름), 모션 켬/끔 비교
    python tools/perf_check.py --out dist-preview --pages / /places/<slug>/ --json
    python tools/perf_check.py --out public --block-external      # 외부 사진·지도 타일 없이(재현성 우선)
    python tools/perf_check.py --out public --compress --motion on --pages / /food/   # Vercel처럼 gzip으로 보냄, 모션 켬만

- 필요: pip install playwright && python -m playwright install chromium
- 로컬 정적 서버로 --out 폴더를 띄우고 측정한다. 기본 서버는 압축이 없어 전송량이 실제보다 크게 나온다.
  --compress를 주면 Vercel처럼 글(HTML·CSS·JS·JSON·SVG·XML·txt)을 gzip으로 보낸다(woff2·사진은 이미 압축돼 그대로).
  기준선과 전/후 비교용이며, 공개 후에는 PageSpeed Insights 실측으로 다시 확인한다.
- 기본 페이지: 홈(/), 장소 목록(/places/)과 첫 장소 페이지(/places/ 아래 이름순 첫 폴더) 가운데 --out에 있는 것.
- 목표(이 사이트 기준, CLAUDE.md 4절): 모바일 LCP ≤ 2.5초(느린 4G·CPU 4배 감속), CLS ≤ 0.1, 첫 방문 글꼴 ≤ 300KB,
  첫 화면 제목이 스크립트 때문에 숨지 않을 것. 모션 켬 줄이 하나라도 넘으면 끝 코드 1.
"""
from __future__ import annotations

import argparse
import gzip
import json
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

PROBE = """() => new Promise(res => {
  let lcp = 0, el = '', cls = 0;
  new PerformanceObserver(l => { for (const e of l.getEntries()) { lcp = e.startTime;
      el = e.element ? (e.element.tagName + (e.element.className ? '.' + String(e.element.className).split(' ')[0] : '')) : (e.url || '').slice(-40); } })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
  setTimeout(() => {
    const fcp = (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || 0;
    const res2 = performance.getEntriesByType('resource');
    const by = t => res2.filter(r => r.initiatorType === t || (t === 'font' && /\\.woff2?$/.test(r.name))).reduce((a, r) => a + (r.decodedBodySize || 0), 0);
    // the home's first news slide picture (its LCP on a real visit): really loaded, from where, when it arrived
    const fs = document.querySelector('[data-hcar-item] img'), src = fs ? fs.currentSrc || fs.src : '';
    const fe = src && res2.find(r => r.name === src);
    // is it on the first screen (a phone's 390x844)? Only then can it be the LCP; below it the picture is lazy by design
    const fr = fs && fs.getBoundingClientRect(), first = !!(fr && fr.top < innerHeight && fr.left < innerWidth);
    res({lcp_ms: Math.round(lcp), lcp_element: el, cls: +cls.toFixed(3), fcp_ms: Math.round(fcp),
         font_kb: Math.round(by('font') / 1024), script_kb: Math.round(by('script') / 1024), requests: res2.length,
         slide: src ? (src.startsWith(location.origin) ? 'local ' : 'outside ') + src.split('/').pop() : '',
         slide_ms: fe ? Math.round(fe.responseEnd) : 0, slide_ok: !!(fs && fs.complete && fs.naturalWidth), slide_first: first});
  }, 9000); })"""


def default_pages(out: Path) -> list[str]:
    """Pages of this build to measure when --pages is not given: the home page, the place list and the first place
    page (folder names sorted), each only when the build has it."""
    pages = [path for path in ("/", "/places/") if (out / path.strip("/") / "index.html").exists()]
    places = out / "places"
    first = sorted(d.name for d in places.iterdir() if (d / "index.html").exists()) if places.is_dir() else []
    return pages + [f"/places/{first[0]}/"] if first else pages


LCP_MS, CLS_MAX, FONT_KB = 2500, 0.1, 300
# Text types Vercel compresses; woff2, AVIF/WebP/JPEG/PNG are already compressed and go as they are.
COMPRESSIBLE = (".html", ".css", ".js", ".mjs", ".json", ".svg", ".xml", ".txt", ".webmanifest", ".map")


def gzip_server(folder: str, port: int) -> None:
    """A static server like the local one, but text files go gzip-compressed (Content-Encoding: gzip) when the
    browser accepts it — the way Vercel serves the site, so transfer sizes and timings match a real visit better."""
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    cache: dict[str, bytes] = {}

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send_head(self):
            path = self.translate_path(self.path)
            if Path(path).is_dir():
                path = str(Path(path) / "index.html")
            if (not path.endswith(COMPRESSIBLE) or "gzip" not in self.headers.get("Accept-Encoding", "")
                    or not Path(path).is_file()):
                return super().send_head()
            if path not in cache:
                cache[path] = gzip.compress(Path(path).read_bytes(), 6)
            body = cache[path]
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            import io
            return io.BytesIO(body)

    ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=folder)).serve_forever()


def serve(folder: Path, port: int, compress: bool = False) -> subprocess.Popen:
    cmd = ([sys.executable, str(Path(__file__).resolve()), "--serve-gzip", str(folder), str(port)] if compress else
           [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(folder)])
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return proc
        except OSError:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("로컬 서버를 띄우지 못했습니다")


def measure(out: Path, pages: list[str], block_external: bool, port: int = 8790, compress: bool = False,
            motions: tuple[str, ...] = ("no-preference", "reduce")) -> list[dict]:
    from playwright.sync_api import sync_playwright  # imported here so --help works without playwright
    srv = serve(out, port, compress)
    rows = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for path in pages:
                for motion in motions:
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              reduced_motion=motion)
                    if block_external:
                        ctx.route("http*://**/*", lambda r: r.continue_() if r.request.url.startswith(f"http://127.0.0.1:{port}") else r.abort())
                    page = ctx.new_page()
                    cdp = ctx.new_cdp_session(page)
                    cdp.send("Network.enable")
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                                                                  "downloadThroughput": 1.6 * 1024 * 1024 / 8,
                                                                  "uploadThroughput": 750 * 1024 / 8})
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    page.goto(f"http://127.0.0.1:{port}" + urllib.parse.quote(path), wait_until="domcontentloaded", timeout=90000)
                    r = page.evaluate(PROBE)
                    r.update(page=path, motion="on" if motion == "no-preference" else "off(reduced)")
                    rows.append(r)
                    ctx.close()
            browser.close()
    finally:
        srv.terminate()
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("public"))
    ap.add_argument("--pages", nargs="*", help="잴 경로(기본: 빌드 결과의 홈·장소 목록·첫 장소 페이지)")
    ap.add_argument("--block-external", action="store_true")
    ap.add_argument("--compress", action="store_true", help="Vercel처럼 글 파일을 gzip으로 보내는 로컬 서버로 잰다")
    ap.add_argument("--motion", choices=("both", "on", "off"), default="both", help="모션 켬·끔(줄인 모션) 가운데 잴 것")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--serve-gzip", nargs=2, metavar=("FOLDER", "PORT"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.serve_gzip:
        gzip_server(a.serve_gzip[0], int(a.serve_gzip[1]))
        return 0
    pages = a.pages or default_pages(a.out)
    if not pages:
        ap.error(f"{a.out}에 잴 페이지가 없습니다(index.html 없음) — 먼저 빌드하거나 --pages를 주세요")
    motions = {"both": ("no-preference", "reduce"), "on": ("no-preference",), "off": ("reduce",)}[a.motion]
    rows = measure(a.out, pages, a.block_external, compress=a.compress, motions=motions)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print("| 페이지 | 모션 | LCP(ms) | LCP 요소 | FCP(ms) | CLS | 글꼴 KB | 스크립트 KB | 요청 수 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            lcp = r["lcp_ms"] or "> 9000(측정 창 안에 LCP 없음)"
            print(f"| {r['page']} | {r['motion']} | {lcp} | {r['lcp_element']} | {r['fcp_ms']} | {r['cls']} | "
                  f"{r['font_kb']} | {r['script_kb']} | {r['requests']} |")
            if r.get("slide"):   # the home: its first slide picture really loaded (not blocked), and when
                state = '불러옴' if r['slide_ok'] else ('못 불러옴' if r.get('slide_first', True) else '첫 화면 밖(lazy, 기준 밖)')
                print(f"|  | 첫 소식 그림 | {r['slide_ms'] or '-'} | {r['slide']} | {state} | | | | |")
    # lcp_ms 0 = the largest element (usually a big photo) had not painted within the 9 s window: a failure, not a pass.
    # The home's first slide picture counts too when it is on the first screen (it can be the LCP there): it must load,
    # and by 2.5 s (a blocked outside photo hid a 5.8 s LCP). Below the first screen it is lazy and cannot be the LCP.
    # CLS and first-visit fonts have budgets too (CLAUDE.md 4).
    bad = [r for r in rows if r["motion"] == "on" and (r["lcp_ms"] > LCP_MS or not r["lcp_ms"] or r["cls"] > CLS_MAX
                                                       or r["font_kb"] > FONT_KB
                                                       or (r.get("slide") and r.get("slide_first", True)
                                                           and not (r["slide_ok"] and 0 < r["slide_ms"] <= LCP_MS)))]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
