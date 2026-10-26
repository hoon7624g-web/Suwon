"""The site assistant in the pages: one launcher at the end of every page (every language) — a labelled pill whose
accessible name starts with its label and whose data-chat carries the city's words from site.json (the assistant's
name, the region, the example questions) — nothing else of the chat in the first paint (chat.js and chat.css load on
the first press — site.js), the module builds the page from text nodes only and keeps input methods from sending, every
language explains every refusal and can go on with a cut answer, the /about/ section, the launcher's few rules in
style.css, and no city's word in the assistant's code (CLAUDE.md 4: the city's values are site.json's)."""
import ast
import json
import re
from pathlib import Path

import pytest

from pipeline.build import build, make_env
from tests.test_no_city_literals import DAEGU_RX, GUNSAN_RX, hits, template_body

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DAEGU = ROOT / "data" / "suwon"
ASSETS = ROOT / "templates" / "assets"
LABELS = {"ko": "AI 챗봇", "en": "AI chat", "ja": "AIチャット", "zh-Hans": "AI助手", "zh-Hant": "AI助手", "de": "KI-Chat",
          "fr": "Chat IA", "es": "Chat IA", "ru": "ИИ-чат"}
FAB = re.compile(r'<button type="button" class="chat-fab"[^>]*>.*?</button>', re.S)


def chat_data(html: str) -> dict:
    """The launcher's data-chat, as chat.js reads it."""
    raw = re.search(r'class="chat-fab"[^>]*data-chat="([^"]*)"', html).group(1)
    return json.loads(raw.replace("&#34;", '"').replace("&#39;", "'").replace("&amp;", "&").replace("&lt;", "<")
                      .replace("&gt;", ">"))


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    out = tmp_path_factory.mktemp("chatui") / "out"
    build(SAMPLE, out, "sample")
    return out


def test_every_page_has_one_launcher_and_nothing_else_of_the_chat(sample):
    site = json.loads((SAMPLE / "site.json").read_text("utf-8"))
    pages = sorted(sample.rglob("*.html"))
    assert len(pages) > 10
    for p in pages:
        html = p.read_text("utf-8")
        assert html.count('class="chat-fab"') == 1, p
        openers = re.findall(r'<(?:button|a)[^>]*data-chat-open[^>]*>', html)
        # one exception, as on the first site: a search that finds nothing offers to ask the chat that query (the
        # button is in the hidden help search.js shows then); the home's centre card asks in place (no opener)
        asks = [o for o in openers if "data-chat-q" in o]
        assert len(asks) == (1 if p.parent.name == "search" else 0), p
        openers = [o for o in openers if o not in asks]
        assert len(openers) == 1 and 'class="chat-fab"' in openers[0], p
        fab = html[html.index('class="chat-fab"'):]
        fab = fab[:fab.index("</button>")]
        assert "mascot-icon-3d" in fab and 'fetchpriority="low"' in fab, p   # the mascot face, never the LCP
        assert '<span class="chat-fab-l">AI 챗봇</span>' in html and 'aria-haspopup="dialog"' in html
        assert html.index('class="chat-fab"') > html.rindex("</footer>"), p   # after the footer, the last thing in <body>
        assert "chat.js" not in html and "chat.css" not in html and "/api/chat" not in html
        assert html.count("<script src=") == 1
        # the city's words for chat.js: the sample has no chatbot object — its own region, no example questions
        assert chat_data(html) == {"site": site["site_url"], "name": f"{site['region']} 여행 도우미", "region": site["region"],
                                   "chips": []}, p
    assert (sample / "assets" / "chat.js").exists() and (sample / "assets" / "chat.css").exists()
    style = (sample / "assets" / "style.css").read_text("utf-8")
    assert ".chat-fab{" in style and "html:not(.js) .chat-fab" in style
    assert ".chat-log" not in style and ".chat-card" not in style      # the panel's rules come with chat.js
    assert len((ASSETS / "css" / "49-chat.css").read_text("utf-8").encode("utf-8")) < 4000


def test_launcher_in_every_language_is_named_by_its_visible_label_and_carries_the_city_s_words():
    tpl = make_env().get_template("_chat.html.j2")
    site = json.loads((DAEGU / "site.json").read_text("utf-8"))
    cb = site["chatbot"]
    for lang, label in {**LABELS, "xx": "AI chat"}.items():
        html = tpl.render(lang=lang, site=site)
        visible = re.search(r'<span class="chat-fab-l">([^<]+)</span>', html).group(1)
        name = re.search(r'class="chat-fab"[^>]*aria-label="([^"]+)"', html).group(1)   # the launcher's, not the quick menu's
        assert visible == label, lang
        assert name.lower().startswith(label.lower()), (lang, name)      # WCAG 2.5.3 label in name
        assert re.search(r"AI|KI|IA|ИИ", label) and " — " in name, (lang, name)
        data = chat_data(html)
        key = lang if lang in cb["chips"] else "en"
        want = {"site": site["site_url"], "name": cb["assistant_name"][key], "region": cb["region_names"][key],
                "chips": cb["chips"][key]}
        if lang == "ko":   # the course planner's language: the hubs its hand-over reads (chat.js planQuery)
            want["hubs"] = {h["key"]: h["name"] for h in site["plan"]["hubs"]}
        assert data == want, lang
        if lang != "ko":
            assert not re.search(r"[가-힣]", html), lang                 # a page in another language carries no Hangul
    ko = tpl.render(lang="ko", site=site)
    assert f'aria-label="AI 챗봇 — {site["region"]} 여행 질문하기"' in ko
    # without a site (a bare render) the launcher still renders, with nothing of a city in it
    bare = tpl.render(lang="ko")
    assert 'aria-label="AI 챗봇 — 여행 질문하기"' in bare and 'data-chat="{}"' in bare


def test_english_pages_render_the_english_launcher(tmp_path):
    from tests.test_en_site import en_min_data
    data = en_min_data(tmp_path / "data")
    out = tmp_path / "out"
    build(data, out, "production")
    pages = sorted((out / "en").rglob("*.html"))
    assert pages
    for p in pages:
        html = p.read_text("utf-8")
        fab = FAB.search(html).group(0)
        assert '<span class="chat-fab-l">AI chat</span>' in fab and not re.search(r"[가-힣]", fab), p
        assert html.index('class="chat-fab"') > html.rindex("</footer>"), p


def test_about_page_explains_the_assistant(sample):
    html = (sample / "about" / "index.html").read_text("utf-8")
    section = html[html.index('id="chatbot"'):]
    section = section[:section.index("</section>")]
    for words in ("사이트 안내 챗봇", "‘AI 챗봇’", "Claude Haiku 5.5", "Anthropic", "이 사이트의 데이터로 만듭니다", "틀릴 수",
                  "저장하지 않습니다", "링크", "예약·결제·회원가입"):
        assert words in section, words


def test_the_chat_module_builds_text_nodes_only_and_keeps_input_methods_from_sending():
    js = (ASSETS / "chat.js").read_text("utf-8")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in js, sink
    # an Enter is the input method's when it comes while composing, or with keyCode 229 (Safari, after compositionend);
    # no timer after compositionend: the Enter Chrome sends right after a Korean syllable is committed is the reader's
    assert "function imeEnter(e) { return e.isComposing || e.keyCode === 229; }" in js
    assert 'addEventListener("compositionend"' not in js and "compEnd" not in js
    assert 'addEventListener("compositionend"' not in (ASSETS / "site.js").read_text("utf-8")
    assert 'role: "dialog"' in js and '"aria-modal"' in js and '"aria-live": "polite"' in js
    assert 'sessionStorage' in js and "requestAnimationFrame" in js and 'a.rel = "noopener"' in js
    assert '"data-track": "chat_link_click"' in js and 'track("chat_open")' in js and 'track("chat_send")' in js
    # the city's words are the launcher's data-chat, never the module's
    assert 'doc.querySelector("[data-chat]")' in js and 'title: "{name}"' in js and "{region}" in js
    assert not re.search(r'chips: \[', js)
    for lang in LABELS:
        key = f'"{lang}"' if "-" in lang else lang
        assert re.search(rf"\n    {re.escape(key)}: {{", js), lang
    site = (ASSETS / "site.js").read_text("utf-8")
    hook = site[site.index("site assistant: chat.js"):site.index("masthead: compact")]
    assert 'doc.querySelector("[data-chat-open]")' in hook and 'BASE + "chat.js"' in hook and 'BASE + "chat.css"' in hook
    # the module is fetched only from the press handler or the restore path (after load), never at startup
    assert hook.count("chatLoad().then") == 2 and "afterLoad(function () { chatLoad()" in hook


def test_every_language_can_go_on_with_a_cut_answer():
    """A cut answer (done.cut) offers to go on in every language; the request says continue: true (chatbot/server.js
    cleanRequest then adds the request to go on as the last, user, message) and the rest joins the same answer."""
    js = (ASSETS / "chat.js").read_text("utf-8")
    more = re.findall(r'cut: "[^"]+", more: "([^"]+)"', js)
    assert len(more) == len(LABELS) and len(set(more)) >= 8, more
    assert 'body["continue"] = true' in js and "function cont(m)" in js and "run(m, true)" in js
    assert "Object.assign({}, m.f || {}, fix)" in js   # the rest's checked links join those already shown


def test_every_language_explains_every_refusal_and_only_the_minute_limit_says_a_minute():
    """server.js answers 429 with a code per limit: rate_limited (the client's minute, or the Vercel Firewall rule — the
    wait is at most a minute), daily_limit (the client's 24 hours: hours), busy (the whole instance is full — not the
    visitor's doing). Every language has a text for each, and the day's text never promises a minute."""
    js = (ASSETS / "chat.js").read_text("utf-8")
    blocks = re.findall(r"\berr: \{(.*?)\}", js, re.S)
    assert len(blocks) == len(LABELS)
    keys = [set(re.findall(r'(\w+): "', b)) for b in blocks]
    assert all(k == keys[0] for k in keys), keys
    assert {"rate_limited", "daily_limit", "busy", "not_configured", "too_long", "network", "error"} <= keys[0]
    minute = re.compile(r"1분|minute|1分|一分|Minute|minuto|минут", re.I)
    for b in blocks:
        texts = dict(re.findall(r'(\w+): "([^"]+)"', b))
        assert minute.search(texts["rate_limited"]), texts["rate_limited"]
        assert not minute.search(texts["daily_limit"]), texts["daily_limit"]
        assert texts["daily_limit"] not in (texts["rate_limited"], texts["busy"], texts["error"])
    # a day's limit offers the site search instead of a retry that would only be refused again
    err_el = js[js.index("function errEl(m)"):js.index("function linksEl(")]
    assert 'm.e === "daily_limit"' in err_el


def test_chat_styles_keep_the_type_rules_targets_and_reduced_motion():
    panel = (ASSETS / "chat.css").read_text("utf-8")
    launcher = (ASSETS / "css" / "49-chat.css").read_text("utf-8")
    for css in (panel, launcher):
        weights = set(re.findall(r"font-weight:\s*(\d+)", css)) | set(re.findall(r"font:\s*(\d+)\s", css))
        assert weights <= {"400", "700"}, weights
        assert "prefers-reduced-motion" in css
    rules = dict(re.findall(r"(\.chat-[\w-]+) \{([^}]*)\}", panel))
    for sel in (".chat-ib", ".chat-send"):
        assert "width: 44px" in rules[sel] and "height: 44px" in rules[sel], sel
    for sel in (".chat-chip", ".chat-retry"):
        assert "min-height: 44px" in rules[sel], sel
    # the launcher: the mascot face, 68px (84px from 1024px) above the safe area, on every page from the first paint,
    # out of the way while the menu is open
    assert "height: 68px" in launcher and "height: 84px" in launcher and "safe-area-inset-bottom" in launcher
    assert "html.menu-open .chat-fab" in launcher and "chat-up" not in launcher
    # an answer written right to left: its lists indent on the side it starts from
    lists = re.findall(r"\.chat-md [uo]l \{([^}]*)\}", panel)
    assert len(lists) == 2 and all("padding-inline-start" in r and "padding-left" not in r for r in lists), lists
    assert ".chat-num { white-space: nowrap; }" in panel and ".chat-links[dir=rtl] .chat-card .icon" in panel


def test_no_city_word_in_the_assistant_s_code():
    """CLAUDE.md 4: the assistant's code names no city — neither the first city's (the code came from its site) nor
    this one's. Its words come from site.json through the build: docs.json meta for the function, data-chat for the
    page. (pipeline/chat_index.py is in tests/test_no_city_literals.py's scan of pipeline/*.py.)"""
    files = sorted((ROOT / "chatbot").glob("*.js")) + sorted((ROOT / "api").glob("*.js")) + [ASSETS / "chat.js"]
    texts = [(p.relative_to(ROOT).as_posix(), p.read_text("utf-8")) for p in files]
    texts.append(("templates/_chat.html.j2", template_body(ROOT / "templates" / "_chat.html.j2")))
    texts += [("templates/assets/chat.css", (ASSETS / "chat.css").read_text("utf-8")),
              ("templates/assets/css/49-chat.css", (ASSETS / "css" / "49-chat.css").read_text("utf-8"))]
    # the course planner (2026-10-18, chatbot/planner.js) is the same function family: its server files, its page
    # and its doors name no city either — hubs, likes, the site's name and address come from site.json plan / meta
    texts += [(f"templates/{n}", template_body(ROOT / "templates" / n)) for n in ("plan.html.j2", "_plan_cta.html.j2")]
    texts += [(f"templates/assets/{n}", (ASSETS / n).read_text("utf-8")) for n in ("plan.js", "plan.css", "css/46-plan-cta.css")]
    # knowledge · prompt · server · city · planner · plan_prompt · plan_fees · plan_state · plan_build · plan_geo · plan_share,
    # api/chat · api/plan, chat.js
    assert len(files) == 14
    assert hits(GUNSAN_RX, texts) == [] and hits(DAEGU_RX, texts) == []
    # no public address either: the site's address and the extra origins are docs.json meta
    for where, text in texts:
        assert not re.search(r"https://[a-z0-9-]+\.(?:vercel\.app|webforai\.kr)", text), where
    tree = ast.parse((ROOT / "pipeline" / "chat_index.py").read_text("utf-8"))
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [c for c in consts if GUNSAN_RX.search(c) or DAEGU_RX.search(c)]
