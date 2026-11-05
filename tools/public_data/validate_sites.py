"""엔진 검증 — 사이트 저장소를 읽기만 해서(코드·데이터를 임시 폴더에 복사) 새 파일 없이(base) / 새 파일을 넣고(new)
preview 빌드·검증을 돌리고, 새 묶음(오늘의 상태·영업 확인·이어서 많이 간 곳·/sun/·/transport/)이 나오는지 센다
(2026-11-05). 저장소에는 아무것도 쓰지 않는다(PYTHONDONTWRITEBYTECODE=1, 복사본에서 실행).

    python tools/validate_sites.py busan [--mode new|base|both] [--timeout 1800]
결과: validate/<slug>/<mode>.json (반환 코드·출력 끝부분·표시 수), validate/<slug>/<mode>-build.log·-validate.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT_DIR, ROOT, Site  # noqa: E402

VAL = ROOT / "validate"
NEW_FILES = ("licenses.json", "related.json", "crowd.json", "visitors_daily.json", "almanac.json", "beaches.json",
             "ferry.json", "transport_tago.json")
LANGS = ("en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
IGNORE = shutil.ignore_patterns(".git", "public", "dist*", "node_modules", "__pycache__", "*.pyc", ".pytest_cache")
MARKERS = {
    "today_card": 'data-today',
    "license": 'data-block="license"',
    "went_next": 'data-block="went-next"',
    "crowd_in_card": "class=\"td-cr\"",
    "sun_in_card": "class=\"td-sun\"",
    "tide_in_card": "class=\"td-tide\"",
}


def copy_repo(site: Site, dest: Path) -> Path:
    repo = Path(site.cfg["repo"])
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for item in repo.iterdir():
        if item.name in (".git", "public", "node_modules") or item.name.startswith("dist"):
            continue
        if item.name == "data":
            (dest / "data").mkdir()
            for d in item.iterdir():
                if d.name in ("raw", "cache"):
                    continue
                if d.is_dir():
                    shutil.copytree(d, dest / "data" / d.name, ignore=IGNORE, symlinks=True)
                else:
                    shutil.copy2(d, dest / "data" / d.name)
        elif item.is_dir():
            shutil.copytree(item, dest / item.name, ignore=IGNORE, symlinks=True)
        else:
            shutil.copy2(item, dest / item.name)
    return dest


def run(cmd: list[str], cwd: Path, log: Path, timeout: int) -> tuple[int, str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("DATA_GO_KR_KEY", None)
    env.pop("TOURAPI_KEY", None)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        out, code = p.stdout + "\n" + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"{e.stdout or ''}\n{e.stderr or ''}\nTIMEOUT {timeout}s", -9
    log.write_text(out, "utf-8")
    return code, f"[{time.time() - t0:.0f}s] " + "\n".join(out.strip().splitlines()[-25:])


def count(out: Path) -> dict:
    res = {"sun_page": (out / "sun" / "index.html").is_file(), "transport_page": (out / "transport" / "index.html").is_file()}
    ko = {k: 0 for k in MARKERS}
    intl = {k: 0 for k in MARKERS}
    for f in out.rglob("*.html"):
        rel = f.relative_to(out).parts
        try:
            text = f.read_text("utf-8", "replace")
        except OSError:
            continue
        bucket = intl if rel and rel[0] in LANGS else ko
        for k, m in MARKERS.items():
            if m in text:
                bucket[k] += 1
    res["ko_pages_with"] = ko
    res["intl_pages_with"] = intl
    if res["sun_page"]:
        t = (out / "sun" / "index.html").read_text("utf-8", "replace")
        res["sun_tide_block"] = ("만조" in t) or ("물때" in t)
    if res["transport_page"]:
        t = (out / "transport" / "index.html").read_text("utf-8", "replace")
        res["transport_cards"] = len(re.findall(r'<details', t))
    sm = out / "sitemap.xml"
    if sm.is_file():
        s = sm.read_text("utf-8", "replace")
        res["sitemap_sun"] = "/sun/" in s
        res["sitemap_transport"] = "/transport/" in s
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--mode", choices=("new", "base", "both"), default="both")
    ap.add_argument("--timeout", type=int, default=10800)
    ap.add_argument("--skip", nargs="*", default=[], help="new: 넣지 않을 파일(엔진 오류를 피해 나머지를 확인할 때)")
    ap.add_argument("--keep-out", action="store_true", help="빌드 결과 폴더를 남긴다(기본: 표시 수만 세고 지움)")
    a = ap.parse_args(argv)
    site = Site(a.slug)
    base_dir = VAL / a.slug
    base_dir.mkdir(parents=True, exist_ok=True)
    for mode0 in (("base", "new") if a.mode == "both" else (a.mode,)):
        mode = mode0 + ("-skip-" + "-".join(x.replace(".json", "") for x in a.skip) if a.skip and mode0 == "new" else "")
        repo = copy_repo(site, base_dir / f"repo-{mode}")
        data = repo / "data" / a.slug
        added = []
        if mode0 == "new":
            for name in NEW_FILES:
                if name in a.skip:
                    continue
                src = OUT_DIR / a.slug / name
                if src.is_file():
                    shutil.copy2(src, data / name)
                    added.append(name)
        out = base_dir / f"out-{mode}"
        if out.exists():
            shutil.rmtree(out)
        rel = f"data/{a.slug}"
        bcode, btail = run([sys.executable, "-m", "pipeline.build", "--data", rel, "--out", str(out), "--mode", "preview"],
                           repo, base_dir / f"{mode}-build.log", a.timeout)
        vcode, vtail = (None, "")
        if bcode == 0:
            vcode, vtail = run([sys.executable, "-m", "pipeline.validate", "--data", rel, "--out", str(out), "--mode",
                                "preview"], repo, base_dir / f"{mode}-validate.log", a.timeout)
        res = {"slug": a.slug, "mode": mode, "added": added, "build_rc": bcode, "validate_rc": vcode,
               "build_tail": btail, "validate_tail": vtail, **(count(out) if out.exists() else {})}
        (base_dir / f"{mode}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", "utf-8")
        shutil.rmtree(repo, ignore_errors=True)
        if not a.keep_out:
            shutil.rmtree(out, ignore_errors=True)
        print(json.dumps({k: v for k, v in res.items() if not k.endswith("_tail")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
