"""The 3D picture registry (owner 2026-10-14: '사이트 전수점검해서 모든 부분을 GPT 생성 이미지로 마스코트도 고려해서
아기자기하게'). One data-driven mapping from a picture ID (docs/handover/gpt_image_prompts_3d_2026-10-14.md, the audit
docs/handover/specs/icon_audit.md) to its derived files, its label and its interim glyph:

  data/<region>/icons.json        {"icons": {id: {"glyph", "label", "group"}}} — which pictures exist as slots
  templates/assets/icons/         <id>-<px>.avif|webp + manifest.json, made by tools/icon_media.py from the
                                  git-ignored originals incoming/icons/<id>.png

templates/_pic.html.j2 pic(id, glyph, size, alt) asks lookup(id): the derived files when the manifest has them, else
None and the macro draws the interim look (the line glyph on a pale tinted circle). Templates never name files.
ASSETS can be pointed at another folder (tests drop a generated PNG into a tmp copy).

Which data folder's icons.json (no city is named in code, CLAUDE.md 4): pipeline.build binds the build's own
(load(data_dir)) into the template globals, so nothing global changes between builds; without one — make_env() alone,
a test — the only data/<region>/icons.json there is (none or several: an empty registry)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates" / "assets" / "icons"
URL = "/assets/icons/"


@lru_cache(maxsize=8)
def _manifest(folder: str) -> dict:
    f = Path(folder) / "manifest.json"
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=4)
def _registry(path: str) -> dict:
    f = Path(path)
    return json.loads(f.read_text("utf-8")).get("icons", {}) if f.is_file() else {}


def load(data_dir: Path | str) -> dict:
    """A data folder's registry ({id: {glyph, label, group}}), {} when it has no icons.json."""
    return _registry(str(Path(data_dir) / "icons.json"))


def registry_path() -> Path | None:
    """The default registry file: the only data/<region>/icons.json there is, else None."""
    found = sorted((ROOT / "data").glob("*/icons.json"))
    return found[0] if len(found) == 1 else None


def registry() -> dict:
    """The default registry (registry_path); a build passes its own (load) to lookup and glyph instead."""
    path = registry_path()
    return _registry(str(path)) if path else {}


def reset() -> None:
    _manifest.cache_clear()
    _registry.cache_clear()


def lookup(pid: str, reg: dict | None = None) -> dict | None:
    """{id, label, glyph, avif: [(url, px)], webp: [(url, px)], px} when every listed file of the picture exists,
    else None (the interim look). reg: the build's registry (load), else the default one."""
    reg = registry() if reg is None else reg
    m = _manifest(str(ASSETS)).get(pid)
    if not m:
        return None
    folder = Path(ASSETS)
    out = {"id": pid, "px": m.get("px", []), "label": (reg.get(pid) or {}).get("label", "")}
    for fmt in ("avif", "webp"):
        files = m.get(fmt) or []
        if not files or not all((folder / name).is_file() for name, _px in files):
            return None
        out[fmt] = [(URL + name, px) for name, px in files]
    return out


def glyph(pid: str, default: str = "pin", reg: dict | None = None) -> str:
    return ((registry() if reg is None else reg).get(pid) or {}).get("glyph") or default
