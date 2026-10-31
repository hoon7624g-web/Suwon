/* the day card's live parts (templates/_side.html.j2; operator 2026-10-31): 날씨각's card (the tab panel from 1200px,
   the homes under their first screen) and the panel's sunrise · sunset. site.js attaches this file after the page has
   loaded, when the browser is idle — nothing here competes with the first screen.
   - Sunrise · sunset ([data-sd-days] 'iso|rise|set|label;…', 한국천문연구원 via the build): the HTML shows the build day,
     its date written out; on the visitor's own date (Asia/Seoul) when the list has it, that day's label and times.
   - Weather ([data-wx]: /v1/feed, [data-wx-t]: /v1/weather/today; data-wx-w the words — present.weather_vm,
     locales.SIDE_WORDS): 날씨각's own home card (operator 2026-10-31 '날씨각 실제 디자인으로 위젯을 가져오라니까?'; no
     '출처' line — 날씨각 is the operator's own service, its pictures and design are ours to use): the sky of the hour
     (hero.sky_mode: morning · day · sunset · night; a cloudy day greys), at night stars and the moon in its phase
     (hero.moon_pct lit, '기우는' / '그믐' the waning side), by day the sun; inside it '지금 날씨 점수' and the score
     (Bagel Fat One), clouds either side, then — Korean pages only, the provider's own sentences — '지금은 러닝각!'
     (hero.bubble, Jua), the top index's summary and the status line (습도 · 불쾌지수 · 미세먼지); last the four cells
     아침 · 낮 · 저녁 · 지금 (지금 white): a period's figure is the today slot nearest its middle (날씨각's periods:
     6시 전 새벽 · 10시 전 아침 · 17시 전 낮 · 21시 전 저녁 · 그 뒤 밤), 지금 the hero's figure. The two display faces come from Google Fonts with &text= (only the letters drawn), after the answer.
     Asked once, when a card comes near the screen. An answer that is late (8 s), fails or is not today's leaves the
     card as built: its title and the link. No weather value is ever in the HTML (the page is static) — nor in search
     engines, the chat or the structured data. Text goes in through textContent only. Reduced motion: no float. */
(function () {
  "use strict";
  var doc = document, win = window;
  function $all(sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); }
  function today() {
    var o = {};
    try {
      new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" })
        .formatToParts(new Date()).forEach(function (p) { o[p.type] = p.value; });
    } catch (e) { return ""; }
    return o.year && o.month && o.day ? o.year + "-" + o.month + "-" + o.day : "";
  }
  var day = today();

  // ------------------------------------------------------------ sunrise · sunset on the visitor's day
  $all("[data-sd-days]").forEach(function (a) {
    var hit = (a.getAttribute("data-sd-days") || "").split(";").map(function (x) { return x.split("|"); })
      .filter(function (x) { return x.length === 4 && x[0] === day; })[0];
    if (!hit) return;
    [["[data-sd-lab]", hit[3]], ["[data-sd-rise]", hit[1]], ["[data-sd-set]", hit[2]]].forEach(function (p) {
      var el = a.querySelector(p[0]);
      if (el && p[1]) el.textContent = p[1];
    });
  });

  // ------------------------------------------------------------ weather
  var boxes = $all("[data-wx]");
  if (!boxes.length || !win.fetch) return;
  var SVG = "http://www.w3.org/2000/svg";
  var ICONS = { sun: "sun", moon: "moon", cloud: "cloud", sunset: "sunset", rain: "rain", snow: "snow", sun_cloud: "sun_cloud" };
  var BASE = (function () {
    var me = doc.querySelector('script[src*="weather.js"]');
    return me ? me.getAttribute("src").replace(/weather\.js.*$/, "wx/") : "/assets/wx/";
  })();
  function el(tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function svg(tag, attrs, parent) {
    var e = doc.createElementNS(SVG, tag);
    for (var k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function num(v) { return typeof v === "number" && isFinite(v); }
  function deg(v) { return Math.round(v) + "°"; }
  function hourOf(iso) { var m = /T(\d{2}):/.exec(iso || ""); return m ? +m[1] : -1; }
  function period(h) { return h < 6 ? "night" : h < 10 ? "morning" : h < 17 ? "day" : h < 21 ? "evening" : "night"; }
  var MID = { morning: 8, day: 13.5, evening: 19 };
  function img(key, alt) {
    var i = el("img", "wx-i");
    i.src = BASE + (ICONS[key] || "cloud") + ".png";
    i.alt = alt || "";
    i.width = 28; i.height = 28;
    i.decoding = "async";
    return i;
  }
  var uid = 0;
  // the moon as 날씨각 draws it: a lit disc with its seas and a few craters, the dark side by the phase
  function moon(pct, waning) {
    var id = "wxm" + (++uid), lit = Math.max(0, Math.min(100, num(pct) ? pct : 50)) / 100;
    var s = svg("svg", { viewBox: "-1.5 -1.5 3 3", "class": "wx-moon", "aria-hidden": "true", focusable: "false" });
    var defs = svg("defs", {}, s);
    var g1 = svg("radialGradient", { id: id + "g" }, defs);
    [["0.6", "#fff4cf", ".55"], ["0.8", "#ffe9a8", ".16"], ["1", "#ffe9a8", "0"]].forEach(function (x) { svg("stop", { offset: x[0], "stop-color": x[1], "stop-opacity": x[2] }, g1); });
    var g2 = svg("radialGradient", { id: id + "b", cx: ".4", cy: ".36", r: ".72" }, defs);
    [["0", "#fffcf2"], [".6", "#f6ebcb"], ["1", "#e0cc98"]].forEach(function (x) { svg("stop", { offset: x[0], "stop-color": x[1] }, g2); });
    var g3 = svg("radialGradient", { id: id + "l" }, defs);
    svg("stop", { offset: ".72", "stop-color": "#8a6f3c", "stop-opacity": "0" }, g3);
    svg("stop", { offset: "1", "stop-color": "#8a6f3c", "stop-opacity": ".28" }, g3);
    svg("circle", { r: "1" }, svg("clipPath", { id: id + "c" }, defs));
    svg("circle", { r: "1.5", fill: "url(#" + id + "g)", opacity: ".63" }, s);
    var g = svg("g", { "clip-path": "url(#" + id + "c)" }, s);
    svg("circle", { r: "1", fill: "url(#" + id + "b)" }, g);
    var seas = svg("g", { fill: "#c4b287", opacity: ".55" }, g);
    [[-.32, -.36, .3, .26], [.12, -.36, .17, .15], [.3, -.06, .2, .17], [-.56, .06, .26, .42], [.66, -.26, .1, .12],
     [.52, .22, .13, .15], [-.14, .44, .18, .13], [-.46, .5, .1, .09]].forEach(function (e) {
      svg("ellipse", { cx: e[0], cy: e[1], rx: e[2], ry: e[3] }, seas);
    });
    [[.1, .72, .07], [.42, .52, .05], [-.66, -.5, .05], [.62, .52, .04], [-.2, .08, .04]].forEach(function (c) {
      svg("circle", { cx: c[0], cy: c[1], r: c[2], fill: "#efe2bd", stroke: "#cdbb8c", "stroke-width": ".018", opacity: ".8" }, g);
    });
    svg("circle", { r: "1", fill: "url(#" + id + "l)" }, g);
    if (lit < 0.99) {   // the dark side: half the disc and the terminator's ellipse (rx by the lit share)
      var rx = (1.04 * Math.abs(1 - 2 * lit)).toFixed(4);
      var d = "M0,-1.04 A1.04,1.04 0 0 0 0,1.04 A" + rx + ",1.04 0 0 " + (lit > 0.5 ? 1 : 0) + " 0,-1.04";
      var p = svg("path", { d: d, fill: "#1a2050", opacity: ".94" }, g);
      if (waning) p.setAttribute("transform", "scale(-1,1)");
    }
    return s;
  }
  function words(box) {
    try { return JSON.parse(box.getAttribute("data-wx-w") || "{}"); } catch (e) { return {}; }
  }
  var feed = null, slots = [], state = "", jua = "";   // state: "" · "asking" · "ok" · "failed"
  function render(box) {
    var w = words(box), ko = !!w.ko, sky = w.sky || {}, cells = w.slots || {}, h = feed.hero;
    var mode = /^(morning|day|sunset|night)$/.test(h.sky_mode) ? h.sky_mode : "day";
    var nowH = hourOf(h.now_at);
    var near = null;
    slots.forEach(function (s) {
      var d = Math.abs(hourOf(s.at) - nowH);
      if (!near || d < Math.abs(hourOf(near.at) - nowH)) near = s;
    });
    var nowIcon = near ? near.icon : (mode === "night" ? "moon" : "sun");
    box.setAttribute("data-t", mode);
    if (/^(cloud|rain|snow)$/.test(nowIcon)) box.setAttribute("data-sky", "cloudy");
    var b = box.querySelector("[data-wx-b]");
    if (!b) return;
    var stars = el("span", "wx-stars");
    for (var i = 0; i < 18; i++) {
      var st = el("i");
      st.style.left = ((i * 37) % 100) + "%";
      st.style.top = ((i * 53 + 7) % 60) + "%";
      st.style.opacity = String(0.4 + (i % 6) / 10);
      stars.appendChild(st);
    }
    b.appendChild(stars);
    var skyRow = el("span", "wx-sky");
    [["wx-c1"], ["wx-c2"], ["wx-c3"]].forEach(function (c) { skyRow.appendChild(el("span", "wx-cloud " + c[0])); });
    var orb = el("span", "wx-orb" + (mode === "night" ? " is-moon" : ""));
    if (mode === "night") orb.appendChild(moon(h.moon_pct, /기우|그믐|하현/.test(h.moon_name || "")));
    var lab = el("span", "wx-ol");
    lab.appendChild(el("small", "wx-sl", w.score || ""));
    if (num(h.weather_score)) lab.appendChild(el("b", "wx-sc", String(Math.round(h.weather_score))));
    orb.appendChild(lab);
    skyRow.appendChild(orb);
    b.appendChild(skyRow);
    var tt = box.querySelector(".wx-t");
    var jtext = (tt ? tt.textContent : "") + (w.score || "") + (num(h.weather_score) ? String(Math.round(h.weather_score)) : "");
    if (ko) {
      if (typeof h.bubble === "string" && h.bubble.trim()) { b.appendChild(el("span", "wx-bub", h.bubble.trim())); jtext += h.bubble; }
      var sum = h.top1 && typeof h.top1.summary === "string" ? h.top1.summary.trim() : "";
      if (sum) b.appendChild(el("span", "wx-sum", sum));
      var st2 = (h.status || []).filter(function (x) { return x && x.label && x.value; });
      if (st2.length) {
        var line = el("span", "wx-st");
        st2.forEach(function (x, k) {
          if (k) line.appendChild(el("span", "wx-dot", "·"));
          var one = el("span", "wx-s1");
          one.appendChild(el("span", "wx-sk", x.label + " "));
          one.appendChild(el("b", "", x.value));
          line.appendChild(one);
          jtext += x.label + x.value;
        });
        b.appendChild(line);
      }
    }
    var ol = el("ol", "wx-cells");
    ["morning", "day", "evening", "now"].forEach(function (p) {
      var isNow = p === "now", s = null;
      if (!isNow) slots.forEach(function (x) {
        var hh = hourOf(x.at);
        if (period(hh) === p && (!s || Math.abs(hh - MID[p]) < Math.abs(hourOf(s.at) - MID[p]))) s = x;
      });
      var t = isNow ? (num(h.temp_c) ? h.temp_c : near && near.temp_c) : s && s.temp_c;
      if (!num(t)) return;
      var li = el("li", isNow ? "is-now" : "");
      li.appendChild(el("span", "wx-cn", cells[p] || ""));
      var key = isNow ? nowIcon : s.icon;
      li.appendChild(img(key, sky[key] || ""));
      li.appendChild(el("b", "wx-ct", deg(t)));
      jtext += (cells[p] || "") + deg(t);
      ol.appendChild(li);
    });
    b.appendChild(ol);
    jua += jtext;
    box.classList.add("is-ready");
  }
  function fonts() {
    var chars = {};
    (jua + "0123456789°").split("").forEach(function (c) { if (c.trim()) chars[c] = 1; });
    var l = doc.createElement("link");
    l.rel = "stylesheet";
    l.href = "https://fonts.googleapis.com/css2?family=Jua&family=Bagel+Fat+One&display=swap&text=" +
      encodeURIComponent(Object.keys(chars).join(""));
    doc.head.appendChild(l);
  }
  function finish(f, t) {
    if (state !== "asking") return;
    var h = f && f.hero, ok = !!(h && typeof h === "object" && num(h.temp_c) && (!day || String(h.now_at || "").slice(0, 10) === day));
    state = ok ? "ok" : "failed";
    feed = ok ? f : null;
    slots = ok && t && (!day || t.day === day) ? (t.slots || []).filter(function (s) { return s && num(s.temp_c) && hourOf(s.at) >= 0; }) : [];
    boxes.forEach(function (bx) {
      if (ok) {
        try { render(bx); } catch (e) { bx.classList.add("is-failed"); }
      } else bx.classList.add("is-failed");
    });
    if (ok) fonts();
  }
  function get(url, ctl) {
    return win.fetch(url, { mode: "cors", credentials: "omit", signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  function ask() {
    if (state) return;
    state = "asking";
    var ctl = win.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); finish(null, null); }, 8000);
    var b0 = boxes[0];
    Promise.all([get(b0.getAttribute("data-wx"), ctl), get(b0.getAttribute("data-wx-t"), ctl)])
      .then(function (r) { clearTimeout(timer); finish(r[0], r[1]); });
  }
  // asked once a card comes near the screen: at once for the panel's (on screen from 1200px), when the reader scrolls
  // towards it for a home's (under the first screen); a card that is not shown (the panel below 1200px) never comes
  // near — until the window is widened
  if (win.IntersectionObserver) {
    var io = new win.IntersectionObserver(function (seen) {
      if (seen.some(function (e) { return e.isIntersecting; })) { io.disconnect(); ask(); }
    }, { rootMargin: "300px 0px" });
    boxes.forEach(function (bx) { io.observe(bx); });
  } else if (boxes.some(function (bx) { return bx.getClientRects().length > 0; })) ask();
})();
