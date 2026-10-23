/* Travel site — /search/: a static index (search/index.json, built with the site by pipeline/present.search_index)
   fetched on the first focus of the box, or at once when the page opens with ?q=. No server.
   Index rows: n name, a other names (course: its stops), o the names in the other versions ('Suseongmot Lake' on the
   Korean index, '수성못' on the others; QA 2026-10-15 U10), v a course's stops in the other versions, m 대표 메뉴·취급
   메뉴, g official designations ('OO맛집(2026, OO시 지정) · 모범음식점(OO시 지정)'), d area ('중구 삼덕동1가', or 구·군
   and road), r 권역 / 구·군, t type, k kind, p path, s the status line as text.
   Ranking: name (exact, prefix, inside) > other names (a, o, v) > menu > designation > 동·권역·type. Spaces and
   ·-()[]|, are ignored when matching. A row says why it matched when it was not the name ("메뉴: 짜장면", "다른 이름: …",
   "경유: …", "지정: 모범음식점(OO시 지정)").
   Nothing found (QA 2026-10-15 F08): one line, then — a diet word (halal, vegan, 채식, アレルギー …): the site has no
   such information, ask the restaurant (no place is named); else up to three names of the index one or two letters
   away ('Suseongmut' → Suseongmot, '수성뭇' → 수성못; Hangul compared letter by letter), each a link that searches it —
   and [data-none-help]: the list pages, the AI chat asked this query, and the whole directory only on request.

   MARKUP
     form[data-search]          action="/search/"; data-index overrides the index URL; its input[name=q]
     [data-results]             results go here (aria-live="polite" in the markup)
     [data-directory]           the no-JS answer (가나다 directory): hidden while results are shown or nothing was
                                found (shown again by [data-show-all]; it stays when the index did not load)
     [data-none-help] [hidden]  shown when nothing matches: list links, button[data-chat-open][data-chat-q] (site.js
                                asks the chat that question), button[data-show-all] (shows the directory, focus #h-dir)
   Result markup (style hooks): p.f-result (count line), section.res-g > h2 (+ .tn count) > ol > li > a >
   span.res-nm (with <mark>), span.res-meta, span.res-why, span.res-st; p.res-none when nothing matches, p.res-sug
   (a[data-sug] links), p.res-diet.
   Without JS the form reloads this page and the directory answers.
   The other language versions (<home>search/, owner 2026-10-14): form[data-words] carries that version's words —
   {kinds, none ('{q}'), menu, other, via, des, of ('{n}', '{m}'), sug, diet} — and the index its rows; Korean is the
   default. */
(function () {
  "use strict";
  var doc = document, form = doc.querySelector("[data-search]"), out = doc.querySelector("[data-results]");
  if (!form || !out) return;
  var input = form.querySelector('input[name="q"]') || form.querySelector("input");
  var dir = doc.querySelector("[data-directory]");
  var help = doc.querySelector("[data-none-help]");
  var emptyArt = doc.querySelector("[data-empty-art]");   // the small picture shown with no result
  var W = null;
  try { W = JSON.parse(form.getAttribute("data-words") || "null"); } catch (e) { W = null; }
  var LANG = doc.documentElement.lang || "ko";
  var KIND = (W && W.kinds) || { attraction: "관광지", stay: "숙소", food: "음식점", course: "코스", guide: "가이드", event: "행사" };
  var ORDER = ["attraction", "food", "stay", "course", "guide", "event"];
  var PLACES = ["attraction", "stay", "food"];
  var STRIP = /[\s·\-()（）\[\]|,]/g, LIMIT = 80, DOT = /\s*·\s*/;
  // words of food rules the site has no data on (tests/test_intl_site.py keeps the index and the chat's knowledge free
  // of them, so the note stays true); the Latin ones only at a word start ('navegan' is no 'vegan')
  var DIET = /\b(?:halal|kosher|koscher|casher|vegetari|végétari|vegan|végan|gluten|allerg|alerg|muslim|musulm)|할랄|코셔|채식|비건|글루텐|알레르기|알러지|무슬림|ハラール|ハラル|ベジタリアン|ヴィーガン|ビーガン|グルテン|アレルギー|ムスリム|菜食|清真|素食|纯素|純素|麸质|麩質|过敏|過敏|穆斯林|حلال|халял|веган|вегетари|глютен|аллерг|мусульм/i;
  var index = null, loading = null;

  function norm(s) { return String(s || "").toLowerCase().replace(STRIP, ""); }
  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = fetch(form.getAttribute("data-index") || "/search/index.json")
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          index = rows.map(function (row) {
            row._n = norm(row.n); row._a = norm(row.a); row._o = norm(row.o); row._v = norm(row.v);
            row._m = norm(row.m); row._g = norm(row.g);
            row._d = norm([row.d, row.r, row.t].join(" "));
            return row;
          });
          return index;
        })
        .catch(function () { loading = null; return []; });
    }
    return loading;
  }
  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  // highlight the matched run once (not every syllable of the query), mapping normalised positions back to the text
  function mark(text, q) {
    var s = String(text || ""), pos = [], flat = "";
    for (var i = 0; i < s.length; i++) {
      var c = s[i].toLowerCase();
      if (!c.match(STRIP)) { pos.push(i); flat += c; }
    }
    var at = q ? flat.indexOf(q) : -1;
    if (at < 0) return esc(s);
    var a = pos[at], b = pos[at + q.length - 1] + 1;
    return esc(s.slice(0, a)) + "<mark>" + esc(s.slice(a, b)) + "</mark>" + esc(s.slice(b));
  }
  // the dish, stop or other name that matched, shown whole
  function piece(list, sep, q) {
    var parts = String(list || "").split(sep);
    for (var i = 0; i < parts.length; i++) if (norm(parts[i]).indexOf(q) > -1) return parts[i].trim();
    return "";
  }
  function josaWa(word) {
    var c = String(word).trim().slice(-1).charCodeAt(0) - 0xac00;
    return c >= 0 && c < 11172 && c % 28 ? "과" : "와";
  }
  function score(row, q) {
    if (row._n === q) return [0, ""];
    if (row._n.indexOf(q) === 0) return [1, ""];
    if (row._n.indexOf(q) > -1) return [2, ""];
    if (row._a.indexOf(q) > -1) {
      if (row.k === "course") return [3, (W ? W.via : "경유: ") + piece(row.a, W ? DOT : /\s+/, q)];
      return [3, row.k === "guide" || row.k === "event" ? "" : (W ? W.other : "다른 이름: ") + (W ? row.a : piece(row.a, /\s+/, q))];
    }
    if (row.o && row._o.indexOf(q) > -1) return [3, (W ? W.other : "다른 이름: ") + piece(row.o, DOT, q)];
    if (row.v && row._v.indexOf(q) > -1) return [3, (W ? W.via : "경유: ") + piece(row.v, DOT, q)];
    if (row.m && row._m.indexOf(q) > -1) return [4, (W ? W.menu : "메뉴: ") + piece(row.m, /\s*[,\/·、，]\s*/, q)];
    if (row.g && row._g.indexOf(q) > -1) return [5, (W ? W.des : "지정: ") + piece(row.g, /\s+·\s+/, q)];
    if (row._d.indexOf(q) > -1) return [6, ""];
    return null;
  }

  // ---- 'did you mean': names of the index one letter away (two from 8 letters), Hangul split into its letters
  function keyOf(s) {
    var o = "";
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i) - 0xac00;
      if (c >= 0 && c < 11172) {
        o += String.fromCharCode(0x1100 + Math.floor(c / 588), 0x1161 + Math.floor((c % 588) / 28));
        if (c % 28) o += String.fromCharCode(0x11a7 + c % 28);
      } else o += s[i];
    }
    return o;
  }
  // optimal string alignment distance (a swap of two neighbours counts 1), max + 1 as soon as it is above max
  function osa(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var p2 = null, p = [], c, i, j;
    for (j = 0; j <= b.length; j++) p.push(j);
    for (i = 1; i <= a.length; i++) {
      c = [i];
      var lo = i;
      for (j = 1; j <= b.length; j++) {
        var v = Math.min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        if (p2 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, p2[j - 2] + 1);
        c.push(v);
        if (v < lo) lo = v;
      }
      if (lo > max) return max + 1;
      p2 = p; p = c;
    }
    return p[b.length];
  }
  var SPLIT = /[\s·\-()（）\[\]|,\/、，:：—–]+/;
  // a row's words: each word of its names and dishes, each pair of neighbours, the first 2–4 syllables of a Korean
  // compound ('수성못유원지' → 수성, 수성못, 수성못유), and a name of several words whole ('Suseongmot Lake Park');
  // [shown, key, the compound of a part] once per row
  function terms(row) {
    if (row._t) return row._t;
    var t = [];
    [row.n].concat(String(row.o || "").split(DOT)).forEach(function (w) {
      w = String(w || "").trim();
      if (SPLIT.test(w)) t.push([w, ""]);
    });
    ["n", "a", "o", "m"].forEach(function (f) {
      var ws = String(row[f] || "").split(SPLIT).filter(Boolean);
      ws.forEach(function (w, i) {
        t.push([w, ""]);
        if (i + 1 < ws.length) t.push([w + " " + ws[i + 1], ""]);
        if (/^[가-힣]{3,}$/.test(w)) for (var k = 2; k < Math.min(w.length, 5); k++) t.push([w.slice(0, k), w]);
      });
    });
    row._t = t.map(function (w) { return [w[0], keyOf(norm(w[0])), w[1]]; });
    return row._t;
  }
  function suggest(rows, raw) {
    var q = keyOf(norm(raw));
    if (q.length < 4) return [];
    var max = q.length >= 8 ? 2 : 1, best = {}, all = [];
    rows.forEach(function (row) {
      var seen = {};
      terms(row).forEach(function (tk) {
        var k = tk[1], b = best[k];
        if (k.length < 3) return;
        if (b && !tk[2]) b.whole = true;   // the part is a word of its own somewhere
        if (seen[k]) return;
        seen[k] = 1;
        var d = b ? b.d : osa(q, k, max);
        if (d > max || d === 0) return;
        if (!b) { b = best[k] = { t: tk[0], d: d, n: 0, whole: !tk[2], of: tk[2] }; all.push(b); }
        b.n++;
      });
    });
    var dmin = Math.min.apply(null, all.map(function (x) { return x.d; })), out = [];
    all.filter(function (x) { return x.d === dmin; })
      .sort(function (x, y) { return y.n - x.n || x.t.length - y.t.length; })
      .forEach(function (x) {   // a part that is no word of its own ('두류공' of 두류공원) shows its whole word
        var t = x.whole ? x.t : x.of;
        if (out.length < 3 && out.indexOf(t) < 0) out.push(t);
      });
    return out;
  }

  // nothing found: the line, then the diet note or the names it may have meant, and the help below
  function none(rows, raw) {
    var q = raw.trim(), html = '<p class="res-none">' + (W ? esc(W.none).replace("{q}", esc(q)) :
      "‘" + esc(q) + "’" + josaWa(q) + " 맞는 곳이 없습니다.") + "</p>";
    if (DIET.test(raw)) html += diet();
    else {
      var sug = rows.length ? suggest(rows, raw) : [];
      if (sug.length) html += '<p class="res-sug">' + esc(W ? W.sug : "혹시 이것을 찾으셨나요? ") +
        sug.map(function (t) { return '<a href="?q=' + encodeURIComponent(t) + '" data-sug>' + esc(t) + "</a>"; }).join(" ") + "</p>";
    }
    out.innerHTML = html;
    if (dir) dir.hidden = rows.length > 0;   // an index that did not load: the directory stays the answer
    if (help) {
      help.hidden = false;
      var ask = help.querySelector("[data-chat-q]"), all = help.querySelector("[data-show-all]");
      if (ask) ask.setAttribute("data-chat-q", q);
      if (all) all.hidden = !dir || !dir.hidden;
    }
  }
  function diet() {
    return '<p class="res-diet">' + esc(W ? W.diet : "이 사이트에는 음식점의 할랄·채식·알레르기 정보가 없습니다. " +
      "방문 전에 음식점에 직접 확인하세요. 전화번호가 있으면 장소 페이지에 있습니다.") + "</p>";
  }
  function render(raw) {
    var q = norm(raw);
    if (help) help.hidden = true;
    if (!q) { out.innerHTML = ""; if (dir) dir.hidden = false; if (emptyArt) emptyArt.hidden = true; return; }
    load().then(function (rows) {
      if (norm(input.value) !== q) return; // a newer query is on its way
      var hits = [];
      rows.forEach(function (row) { var s = score(row, q); if (s) hits.push([s[0], row, s[1]]); });
      hits.sort(function (x, y) { return x[0] - y[0] || x[1].n.localeCompare(y[1].n, LANG); });
      if (emptyArt) emptyArt.hidden = hits.length > 0;
      if (!hits.length) { none(rows, raw); return; }
      if (dir) dir.hidden = true;
      var shown = hits.slice(0, LIMIT), groups = {};
      shown.forEach(function (h) { (groups[h[1].k] = groups[h[1].k] || []).push(h); });
      var counts = ORDER.filter(function (k) { return groups[k]; }).map(function (k) { return KIND[k] + " " + groups[k].length; });
      var places = hits.every(function (h) { return PLACES.indexOf(h[1].k) > -1; });
      var unit = places ? "곳" : "건";
      // '‘짜장면’ 12곳', or with several kinds '‘호수’ 25건 · 관광지 10 · 숙소 3 · 코스 12' (the kind counts only
      // when there is more than one kind; '중 20건' when the list is cut at LIMIT)
      var html = W ? '<p class="f-result">‘' + esc(raw.trim()) + "’ " +
          (hits.length > LIMIT ? esc(W.of).replace("{n}", LIMIT).replace("{m}", hits.length) : hits.length) +
          (counts.length > 1 ? " · " + esc(counts.join(" · ")) : "") + "</p>"
        : '<p class="f-result">‘' + esc(raw.trim()) + "’ " + hits.length + unit +
        (hits.length > LIMIT ? " 중 " + LIMIT + unit : "") + (counts.length > 1 ? " · " + esc(counts.join(" · ")) : "") + "</p>";
      if (DIET.test(raw)) html += diet();
      ORDER.forEach(function (k) {
        if (!groups[k]) return;
        html += '<section class="res-g"><h2>' + KIND[k] + ' <span class="tn">' + groups[k].length + "</span></h2><ol>";
        groups[k].forEach(function (h) {
          var row = h[1], meta = [row.t, row.d, row.r].filter(Boolean);
          html += '<li><a href="' + esc(row.p) + '"><span class="res-nm">' + mark(row.n, q) + "</span>" +
            '<span class="res-meta">' + esc(meta.join(" · ")) + "</span>" +
            (h[2] ? '<span class="res-why">' + mark(h[2], q) + "</span>" : "") +
            (row.s ? '<span class="res-st">' + esc(row.s) + "</span>" : "") + "</a></li>";
        });
        html += "</ol></section>";
      });
      out.innerHTML = html;
    });
  }
  function remember(value) {
    try { history.replaceState(null, "", value ? "?q=" + encodeURIComponent(value) : location.pathname); } catch (e) { /* file:// */ }
  }
  var timer = null;
  input.addEventListener("focus", load, { once: true });
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { render(input.value); remember(input.value.trim()); }, 120);
  });
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    render(input.value);
    remember(input.value.trim());
  });
  // a suggested name searches at once (with a modifier key it stays a link: the same search in a new tab)
  out.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[data-sug]");
    if (!a || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    ev.preventDefault();
    input.value = a.textContent;
    render(input.value);
    remember(input.value);
  });
  var showAll = help && help.querySelector("[data-show-all]");
  if (showAll && dir) showAll.addEventListener("click", function () {
    dir.hidden = false;
    showAll.hidden = true;
    var h = doc.getElementById("h-dir");
    if (h) h.focus();
  });
  var q0 = new URLSearchParams(location.search).get("q");
  if (q0) { input.value = q0; render(q0); }
})();
