"""제휴·관련 사이트 (operator 2026-11-11): the company's sites and related sites as a strip at the top of every Korean
footer and as cards at the foot of the home; a partner's site says the relationship and is rel="sponsored"."""
import json, shutil
from pathlib import Path
from types import SimpleNamespace

import jinja2

from pipeline import related_sites
from pipeline.build import build
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "gunsan" / "related_sites.json").read_text("utf-8"))


def test_the_operator_s_list_is_whole_and_every_entry_ships_its_icon():
    S = SimpleNamespace(related_sites=DATA)
    assert related_sites.data_problems(S) == []
    v = related_sites.view(S)
    assert v["title"] == "제휴·관련 사이트"
    assert [s["name"] for s in v["sites"]] == ["AI오투오", "WebforAI", "날씨각", "여행각", "군산각 블로그", "스테이,머뭄"]
    assert [s["url"] for s in v["sites"]][:4] == ["https://www.o2osolution.ai/", "https://webforai.kr/",
                                                  "https://weather.o2o.kr/", "https://travel.webforai.kr/"]
    assert [s["name"] for s in v["sites"] if s["sponsored"]] == ["스테이,머뭄"]


def test_problems_are_named():
    bad = {"sites": [{"name": "x", "url": "http://x.kr/", "note": "", "icon": "/assets/none.png"},
                     {"name": "y", "url": "https://y.kr/", "note": "숙소", "icon": "/assets/related/aio2o.png",
                      "sponsored": True}]}
    out = related_sites.data_problems(SimpleNamespace(related_sites=bad))
    assert any("x: url" in p for p in out) and any("x: note" in p for p in out) and any("x: icon" in p for p in out)
    assert any("y: sponsored" in p for p in out)
    assert related_sites.view(SimpleNamespace(related_sites={})) is None


def test_strip_and_cards_link_out_with_the_right_rel_and_lazy_icons():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    m = env.get_template("_related_sites.html.j2").module
    v = related_sites.view(SimpleNamespace(related_sites=DATA))
    strip = str(m.strip(v))
    assert strip.count('class="rel-a"') == 6 and "<h2" in strip and "제휴·관련 사이트" in strip
    assert 'href="https://co.webforai.kr/s/stay" rel="sponsored noopener"' in strip
    assert 'href="https://weather.o2o.kr/" rel="noopener"' in strip
    assert strip.count('loading="lazy"') == 6 and strip.count('data-track="related_site_click"') == 6
    ui = SimpleNamespace(sec_head=lambda *a, **k: f"<h2>{a[1]}</h2>")
    cards = str(m.cards(v, ui, "", "군산각"))
    assert cards.count('class="rel-c"') == 6 and "군산각과 함께하는 사이트" in cards
    assert str(m.strip(None)).strip() == "" and str(m.cards(None, ui, "", "군산각")).strip() == ""


def test_home_omits_footer_strip_while_subpages_keep_it(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    (data / "related_sites.json").write_text(json.dumps(DATA, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    home = (out / "index.html").read_text("utf-8")
    about = (out / "about" / "index.html").read_text("utf-8")
    assert home.count('class="rel-c"') == 6 and 'class="rel-strip"' not in home and 'class="rel-a"' not in home
    assert about.count('class="rel-a"') == 6 and 'class="rel-strip"' in about and 'class="rel-c"' not in about
    assert not validate(data, out, "sample")[0]
