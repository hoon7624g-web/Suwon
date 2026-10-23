"""The site assistant's server tests (tests/js/*.test.js, node --test) — run when Node.js is installed, with
CHAT_KB_DIR = the knowledge exported from the real data (production, as the public build writes it), so the search and
link checks also run on the real pages and the real docs.json meta. The tests inject a fake client: no API key, no
network. Node 22 runs them here; Vercel runs the function on Node 24.x (package.json engines)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import chat_index, en_site
from pipeline.build import State

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_node_server_tests(tmp_path):
    data = ROOT / "data" / "suwon"
    S = State(data, "production")
    S.en = en_site.load(S, data)
    chat_index.export(S, tmp_path)
    files = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.js"))
    assert files
    r = subprocess.run([NODE, "--test", *files], cwd=ROOT, env={**os.environ, "CHAT_KB_DIR": str(tmp_path / "chat")},
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, (r.stdout[-6000:] + "\n" + r.stderr[-3000:])
    assert "# fail 0" in r.stdout or "ℹ fail 0" in r.stdout, r.stdout[-2000:]
    assert "CHAT_KB_DIR not set" not in r.stdout   # the real-knowledge tests ran
