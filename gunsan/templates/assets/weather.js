/* 군산각 — the day card's live parts (templates/_side.html.j2; operator 2026-10-31): 날씨각's weather card (the tab
   panel from 1200px, the homes under their first screen) and the panel's sunrise · sunset. site.js attaches this file
   after the page has loaded, when the browser is idle — nothing here competes with the first screen.
   - Sunrise · sunset ([data-sd-days] 'iso|rise|set|label;…', 한국천문연구원 via the build): the HTML shows the build day,
     its date written out; on the visitor's own date (Asia/Seoul) when the list has it, that day's label and times.
   - Weather ([data-wx] the feed, [data-wx-day] the day's slots; data-wx-w the words — present.weather_vm,
     locales.SIDE_WORDS). 날씨각 (weather.o2o.kr) is the operator's own service: the card is 날씨각's own first-screen
     card, drawn as 날씨각 draws it (operator 2026-10-31 '날씨각 실제 디자인으로 위젯을 가져오라니까?'), with no source words.
     Asked once, when a card comes near the screen (the panel's from 1200px at once; a home's when the reader scrolls
     towards it; the panel is hidden below 1200px, so a phone page without the home's card never asks). From the two
     answers: the sky (the feed's sky_mode — morning · day · sunset · night — over the sky of the slot nearest now:
     clouds, rain, snow, a grey day), the sun or, in the evening and at night, the moon in its phase (moon_pct,
     waxing or waning by moon_name) with '지금 날씨 점수' and the score; on the Korean pages 날씨각's own words (the
     bubble '지금은 러닝각!', top1.summary, the status line), on the others the figures only (now, feels like,
     humidity); the four cells — 아침 · 낮 · 저녁 · 밤, the one the feed says it is now '지금' (white, with the feed's
     temperature now) — each the slot 날씨각 takes for it (the last at or before 7 · 13 · 18 · 22 h) with 날씨각's icon
     (assets/wx/*.webp, copied from 날씨각) and figure. 날씨각's round fonts (Jua, Bagel Fat One) come from Google Fonts,
     only the letters the card shows (&text=), and are added to the page only once they have loaded — the card is
     drawn in them, or, when they are late (2.5 s), in the site's font, and never changes font afterwards. The card
     fills the room css/80-side.css keeps for it (nothing moves). An answer that is late (8 s), fails or is not today's
     (Asia/Seoul) leaves the card as built: its name and the link to weather.o2o.kr. No weather value is ever in the
     HTML (the page is static) — nor in search engines, the chat or the structured data. Text goes in through
     textContent only. Reduced motion: no drop-in, float, shooting stars, twinkling or falling rain. */
(function () {
  "use strict";
  var doc = document, win = window;
  var SVG = "http://www.w3.org/2000/svg";
  function $all(sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); }
  // the visitor's date and time in Korea
  function seoul() {
    var o = {};
    try {
      new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date()).forEach(function (p) { o[p.type] = p.value; });
    } catch (e) { return null; }
    if (!(o.year && o.month && o.day)) return null;
    return { iso: o.year + "-" + o.month + "-" + o.day, mo: +o.month, h: (+o.hour || 0) % 24, mi: +o.minute || 0 };
  }
  var T = seoul(), day = T ? T.iso : "";

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
  if (!boxes.length) return;
  if (!win.fetch) { boxes.forEach(function (b) { b.classList.add("is-failed"); }); return; }

  // 날씨각's own tables (its app: the hero card)
  var COLS = ["morning", "day", "sunset", "night"];
  var HOUR = { morning: 7, day: 13, sunset: 18, night: 22 };
  var ICON = { clear: "sun", partly: "sun_cloud", cloudy: "cloud", rain: "rain", snow: "snow", sleet: "snow" };
  var CLOUDS = { clear: 0, partly: 2, cloudy: 3, rain: 3, snow: 3, sleet: 3 };
  var WANING = ["기우는 달", "하현달", "그믐달"];
  var SUNSET = [17.7, 18.2, 18.6, 19.1, 19.5, 19.9, 19.9, 19.5, 18.9, 18.2, 17.6, 17.3];   // its sky by the clock
  var ICONS = "/assets/wx/";
  function num(v) { return typeof v === "number" && isFinite(v); }
  function deg(v) { return num(v) ? Math.round(v) + "°" : "–"; }
  function el(tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function words(box) {
    try { return JSON.parse(box.getAttribute("data-wx-w") || "{}"); } catch (e) { return {}; }
  }
  function clockSky() {
    if (!T) return "day";
    var h = T.h + T.mi / 60, s = SUNSET[T.mo - 1] || 18.5;
    return h >= 5 && h < 11 ? "morning" : h >= 11 && h < s + 1 ? (h < s - 2 ? "day" : "sunset") : "night";
  }
  // a slot's sky as 날씨각 reads it (rain_type: 2 rain · 3 sleet · 4 snow · 5 shower; sky: 2 partly · 3 cloudy)
  function kind(s) {
    if (!s) return "clear";
    var r = s.rain_type, k = s.sky;
    if (r === 2 || r === 5) return "rain";
    if (r === 4) return "snow";
    if (r === 3) return "sleet";
    if (k === 3) return "cloudy";
    if (k === 2) return "partly";
    if (r == null && k == null) return { cloud: "cloudy", rain: "rain", snow: "snow" }[s.icon] || "clear";
    return "clear";
  }
  // the slot for a cell: the last at or before its hour (one with a figure after it when that one has none)
  function pick(slots, hour) {
    var n = null;
    slots.forEach(function (s) { if (s.hh <= hour) n = s; });
    n = n || slots[0];
    if (!num(n.temp_c)) n = slots.filter(function (s) { return s.hh > hour && num(s.temp_c); })[0] || n;
    return n;
  }
  function nearest(slots) {
    var t = Date.now(), have = slots.filter(function (s) { return num(s.temp_c); });
    return have.reduce(function (a, s) { return Math.abs(s.ms - t) < Math.abs(a.ms - t) ? s : a; }, have[0]);
  }
  function usable(feed, today) {
    var h = feed && feed.hero;
    if (!h || typeof h !== "object" || !num(h.weather_score)) return null;
    if (!today || typeof today !== "object") return null;
    if (day && (String(h.now_at || "").slice(0, 10) !== day || today.day !== day)) return null;
    var slots = (today.slots || []).filter(function (s) { return s && !isNaN(Date.parse(s.at)); }).map(function (s) {
      var ms = Date.parse(s.at), k = new Date(ms + 324e5);   // its hour in Korea
      return { ms: ms, hh: k.getUTCHours() + k.getUTCMinutes() / 60, temp_c: s.temp_c, sky: s.sky, rain_type: s.rain_type, icon: s.icon };
    });
    if (!slots.some(function (s) { return num(s.temp_c); })) return null;
    return { hero: h, slots: slots };
  }

  // 날씨각's moon (its app's own drawing: the disc, its seas and craters, the shade of its phase)
  var SEAS = [[-.32, -.36, .3, .26], [.12, -.36, .17, .15], [.3, -.06, .2, .17], [-.56, .06, .26, .42], [.66, -.26, .1, .12],
    [.52, .22, .13, .15], [-.14, .44, .18, .13], [-.46, .5, .1, .09]];
  var CRATERS = [[.1, .72, .07], [.42, .52, .05], [-.66, -.5, .05], [.62, .52, .04], [-.2, .08, .04]];
  var TONES = { night: { body: ["#fffcf2", "#f6ebcb", "#e0cc98"], shade: "#1a2050" },
                dusk: { body: ["#fff8ee", "#ffe2cc", "#f2b9a2"], shade: "#4a2a63" } };
  var uid = 0;
  function node(tag, at, kids) {
    var e = doc.createElementNS(SVG, tag);
    Object.keys(at || {}).forEach(function (k) { e.setAttribute(k, at[k]); });
    (kids || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }
  function shadePath(pct, r) {
    var f = pct / 100;
    return "M0," + (-r) + " A" + r + "," + r + " 0 0 0 0," + r + " A" + (r * Math.abs(1 - 2 * f)) + "," + r + " 0 0 " + (f < .5 ? 0 : 1) + " 0," + (-r);
  }
  function moon(pct, waxing, tone) {
    var id = "wxm" + (++uid), a = TONES[tone], o = pct / 100, full = pct >= 99, nw = pct <= 1;
    var stop = function (off, c, op) { return node("stop", op == null ? { offset: off, "stop-color": c } : { offset: off, "stop-color": c, "stop-opacity": op }); };
    var defs = node("defs", {}, [
      node("radialGradient", { id: id + "g" }, [stop("0.6", "#fff4cf", "0.55"), stop("0.8", "#ffe9a8", "0.16"), stop("1", "#ffe9a8", "0")]),
      node("radialGradient", { id: id + "b", cx: "0.4", cy: "0.36", r: "0.72" }, [stop("0", a.body[0]), stop("0.6", a.body[1]), stop("1", a.body[2])]),
      node("radialGradient", { id: id + "l" }, [stop("0.72", "#8a6f3c", "0"), stop("1", "#8a6f3c", "0.28")]),
      node("clipPath", { id: id + "c" }, [node("circle", { r: "1" })]),
      node("filter", { id: id + "f", x: "-0.2", y: "-0.2", width: "1.4", height: "1.4" }, [node("feGaussianBlur", { stdDeviation: "0.035" })])
    ]);
    var seas = node("g", { filter: "url(#" + id + "f)", fill: "#c4b287", opacity: "0.55" },
      SEAS.map(function (e) { return node("ellipse", { cx: e[0], cy: e[1], rx: e[2], ry: e[3] }); }));
    var disc = node("g", { "clip-path": "url(#" + id + "c)" }, [node("circle", { r: "1", fill: "url(#" + id + "b)" }), seas]
      .concat(CRATERS.map(function (e) { return node("circle", { cx: e[0], cy: e[1], r: e[2], fill: "#efe2bd", stroke: "#cdbb8c", "stroke-width": "0.018", opacity: "0.8" }); }))
      .concat([node("circle", { r: "1", fill: "url(#" + id + "l)" }),
        full ? null : node("path", waxing ? { d: shadePath(pct, 1.04), fill: a.shade, opacity: "0.94", filter: "url(#" + id + "f)" }
          : { d: shadePath(pct, 1.04), fill: a.shade, opacity: "0.94", filter: "url(#" + id + "f)", transform: "scale(-1,1)" })]));
    return node("svg", { viewBox: "-1.5 -1.5 3 3", class: "wx-mo", "aria-hidden": "true", focusable: "false" }, [defs,
      nw ? null : node("circle", { r: "1.5", fill: "url(#" + id + "g)", opacity: String(full ? 1 : .12 + .8 * o) }), disc,
      nw ? node("circle", { r: "1", fill: "none", stroke: "#fff", "stroke-opacity": "0.18", "stroke-width": "0.025" }) : null]);
  }
  // the night sky: 날씨각's 26 stars (kept between the head and the words: a star by a letter reads as part of it,
  // one behind the see-through link as a dot after it) and 3 shooting stars; rain and snow
  function sky(kindNow) {
    var s = el("div", "wx-stars");
    s.setAttribute("aria-hidden", "true");
    for (var i = 0; i < 26; i++) {
      var st = el("i", i % 3 ? "" : "wx-tw");
      st.style.left = (i * 37 % 100) + "%";
      st.style.top = (12 + (i * 53 % 60) * .55).toFixed(1) + "%";
      st.style.opacity = String(.4 + i * 7 % 6 / 10);
      st.style.setProperty("--dl", (i * 0.7 % 5).toFixed(1) + "s");
      s.appendChild(st);
    }
    [["6%", "80%", "90px", "7s", "1.5s"], ["20%", "52%", "70px", "9s", "4s"], ["34%", "94%", "80px", "11s", "6.5s"]].forEach(function (x) {
      var sh = el("span", "wx-shoot");
      sh.style.top = x[0];
      sh.style.left = x[1];
      sh.style.setProperty("--len", x[2]);
      sh.style.setProperty("--dur", x[3]);
      sh.style.setProperty("--dl", x[4]);
      s.appendChild(sh);
    });
    var out = [s];
    var rain = kindNow === "rain" || kindNow === "sleet", snow = kindNow === "snow" || kindNow === "sleet";
    if (rain || snow) {
      var f = el("div", "wx-fx");
      f.setAttribute("aria-hidden", "true");
      var add = function (n, cls, step, a, b, c, d) {
        for (var i = 0; i < n; i++) {
          var x = el("i", cls);
          x.style.left = (i * step % 100) + "%";
          x.style.setProperty("--top", (i * a % 90) + "%");
          x.style.setProperty("--dl", (i * b % 100 / c) + "s");
          x.style.setProperty("--dur", d(i) + "s");
          f.appendChild(x);
        }
      };
      if (rain) add(22, "wx-drop", 41, 29, 37, 100, function (i) { return .55 + i * 13 % 5 / 10; });
      if (snow) add(16, "wx-flake", 47, 31, 53, 25, function (i) { return 3.2 + i * 7 % 5 / 2; });
      out.push(f);
    }
    return out;
  }
  // the date as 날씨각 writes it ('10월 31일 토요일'); the other versions' short form ('Sat, Oct 31'), which fits the head
  function dateWords(lang) {
    var long = !lang || lang === "ko";
    try {
      return new Intl.DateTimeFormat(lang || "ko", { timeZone: "Asia/Seoul", month: long ? "long" : "short", day: "numeric",
        weekday: long ? "long" : "short" }).format(new Date());
    } catch (e) { return ""; }
  }

  // ------------------------------------------------------------ 날씨각's round fonts, only the letters the card shows
  var FONTS = "https://fonts.googleapis.com/css2?family=";
  function faces(family, as, text) {
    // the stylesheet's faces (one or more, each with its unicode-range), loaded before they join the page; none when
    // the stylesheet or a face does not come
    var url = FONTS + family + "&text=" + encodeURIComponent(text) + "&display=swap";
    return win.fetch(url, { mode: "cors", credentials: "omit" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (css) {
      var out = [];
      (css.match(/@font-face\s*{[^}]*}/g) || []).forEach(function (blk) {
        var src = /src:\s*url\((https:\/\/fonts\.gstatic\.com\/[^)\s]+)\)\s*format\(['"]?woff2['"]?\)/.exec(blk);
        var ur = /unicode-range:\s*([^;]+);/.exec(blk);
        if (!src) return;
        try { out.push(new win.FontFace(as, "url(" + src[1] + ") format('woff2')", ur ? { unicodeRange: ur[1].trim() } : {})); } catch (e) {}
      });
      return Promise.all(out.map(function (f) { return f.load(); }));
    }).catch(function () { return []; });
  }
  function fonts(round, digits, done) {
    var over = false;
    var end = function (list) {
      if (over) return;
      over = true;
      clearTimeout(t);
      // they join the page now, before the card is drawn in them — never afterwards (nothing changes its letters)
      (list || []).forEach(function (fs) { (fs || []).forEach(function (f) { try { doc.fonts.add(f); } catch (e) {} }); });
      done();
    };
    var t = setTimeout(function () { end(null); }, 2500);
    if (!win.FontFace || !doc.fonts || !win.Promise) return end(null);
    Promise.all([faces("Jua", "WxJua", round), faces("Bagel+Fat+One", "WxBagel", digits)]).then(end);
  }
  function letters(s) {
    var seen = {}, out = "";
    s.replace(/\s+/g, "").split("").forEach(function (c) { if (!seen[c]) { seen[c] = 1; out += c; } });
    return out;
  }

  // ------------------------------------------------------------ the card
  function draw(box, D) {
    var w = words(box), ko = !!w.ko, side = box.classList.contains("wx-side"), h = D.hero, slots = D.slots;
    var S = w.slots || {}, SKY = w.sky || {};
    var mode = HOUR[h.sky_mode] ? h.sky_mode : clockSky();
    var now = nearest(slots), skyNow = kind(now);
    var body = box.querySelector("[data-wx-b]");
    if (!body) return;
    box.setAttribute("data-t", mode);
    box.setAttribute("data-sky", skyNow);
    var dt = box.querySelector("[data-wx-dt]");
    if (dt && !side) dt.textContent = dateWords(w.lang);
    sky(skyNow).forEach(function (x) { body.appendChild(x); });
    // the sun, or the moon, with the score; 날씨각's clouds for the sky now
    var stage = el("div", "wx-sky");
    for (var i = 0; i < CLOUDS[skyNow]; i++) {
      var c = el("span", "wx-cl wx-c" + (i + 1));
      c.setAttribute("aria-hidden", "true");
      c.appendChild(el("span", "wx-cb"));
      stage.appendChild(c);
    }
    var mn = (mode === "sunset" || mode === "night") && h.moon_name && num(h.moon_pct)
      ? { pct: Math.max(0, Math.min(100, h.moon_pct)), waning: WANING.indexOf(h.moon_name) > -1 } : null;
    var orb = el("div", "wx-orb" + (mn ? " wx-moon " + (mn.pct >= 50 ? "is-lit" : "is-dim") : ""));
    if (mn) orb.appendChild(moon(mn.pct, !mn.waning, mode === "sunset" ? "dusk" : "night"));
    var ob = el("div", "wx-ob");
    ob.appendChild(orb);
    stage.appendChild(ob);
    body.appendChild(stage);
    var score = el("p", "wx-sc");
    score.appendChild(el("small", "", w.score));
    score.appendChild(el("b", "", String(Math.round(h.weather_score))));
    orb.appendChild(score);
    // the words: 날씨각's own (Korean) — or the figures (the other versions)
    var say = el("div", "wx-say");
    if (ko) {
      if (typeof h.bubble === "string" && h.bubble.trim()) say.appendChild(el("p", "wx-bub", h.bubble.trim()));
      var sum = h.top1 && typeof h.top1.summary === "string" ? h.top1.summary.trim() : "";
      if (!side && sum) say.appendChild(el("p", "wx-sum", sum));
      var st = (Array.isArray(h.status) ? h.status : []).filter(function (x) { return x && typeof x.label === "string" && typeof x.value === "string"; });
      if (!side && st.length) {
        var p = el("p", "wx-st");
        st.forEach(function (x, i) {
          if (i) { var dot = el("span", "wx-dot", "·"); dot.setAttribute("aria-hidden", "true"); p.appendChild(dot); }
          var one = el("span", "wx-si" + (x.tone === "warn" ? " is-warn" : ""));
          one.appendChild(el("span", "wx-sl", x.label));
          one.appendChild(doc.createTextNode(" "));
          one.appendChild(el("b", "", x.value));
          p.appendChild(one);
        });
        say.appendChild(p);
      }
    } else if (!side) {
      say.appendChild(el("p", "wx-bub", deg(h.temp_c)));
      var fig = [];
      if (num(h.feels_c) && w.feels) fig.push(w.feels.replace("{t}", deg(h.feels_c)));
      if (num(h.humidity) && w.hum) fig.push(w.hum.replace("{p}", String(Math.round(h.humidity))));
      if (fig.length) say.appendChild(el("p", "wx-sum", fig.join(" · ")));
    }
    if (say.childNodes.length) body.appendChild(say);
    // the four cells: 아침 · 낮 · 저녁 · 밤, the one it is now '지금'
    var ol = el("ol", "wx-strip");
    COLS.forEach(function (k) {
      var isNow = k === mode, s = isNow ? now : pick(slots, HOUR[k]), sk = kind(s);
      var ic = k === "night" && sk === "clear" ? "moon" : ICON[sk];
      var li = el("li", isNow ? "is-now" : "");
      li.appendChild(el("span", "wx-cn", isNow ? S.now : S[k]));
      var img = el("img", "wx-ic");
      img.src = ICONS + ic + ".webp";
      img.alt = SKY[ic] || "";
      img.width = img.height = side ? 18 : 22;
      img.decoding = "async";
      li.appendChild(img);
      li.appendChild(el("b", "wx-tc", deg(isNow && num(h.temp_c) ? h.temp_c : s && s.temp_c)));
      ol.appendChild(li);
    });
    body.appendChild(ol);
    // the link: the drawn card is one link to 날씨각 (its 자세히 보기 covers it)
    var go = box.querySelector("[data-wx-gl]");
    if (go && w.more) {
      var t = box.querySelector(".wx-t");
      go.textContent = "";
      go.appendChild(el("span", "vh", (t ? t.textContent : "") + " "));
      go.appendChild(doc.createTextNode(w.more));
      var arr = el("span", "wx-ar", "›");
      arr.setAttribute("aria-hidden", "true");
      go.appendChild(arr);
    }
    box.classList.add("is-ready");
  }
  // the letters the card will show in 날씨각's round font (Jua) and in its score font (Bagel Fat One)
  function roundText(D) {
    var h = D.hero, s = "";
    boxes.forEach(function (b) {
      var w = words(b), S = w.slots || {};
      s += (b.querySelector(".wx-t") || {}).textContent || "";
      s += (w.score || "") + (S.morning || "") + (S.day || "") + (S.sunset || "") + (S.night || "") + (S.now || "");
      if (w.ko) {
        s += typeof h.bubble === "string" ? h.bubble : "";
        (Array.isArray(h.status) ? h.status : []).forEach(function (x) { s += (x && x.label || "") + (x && x.value || ""); });
      }
    });
    return letters(s + "0123456789-–°·");
  }

  var state = "";   // "" · "asking" · "ok" · "failed"
  function fail() { boxes.forEach(function (b) { b.classList.add("is-failed"); }); }
  function finish(feed, today) {
    if (state !== "asking") return;
    var D = usable(feed, today);
    if (!D) { state = "failed"; return fail(); }
    state = "ok";
    fonts(roundText(D), "0123456789", function () {
      boxes.forEach(function (b) {
        try { draw(b, D); } catch (e) {
          var x = b.querySelector("[data-wx-b]");
          if (x) x.textContent = "";
          b.classList.remove("is-ready");
          b.classList.add("is-failed");
        }
      });
    });
  }
  function ask() {
    if (state) return;
    state = "asking";
    var ctl = win.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); finish(null, null); }, 8000);
    var get = function (url) {
      return win.fetch(url, { mode: "cors", credentials: "omit", signal: ctl ? ctl.signal : undefined })
        .then(function (r) { return r.ok ? r.json() : null; });
    };
    Promise.all([get(boxes[0].getAttribute("data-wx")), get(boxes[0].getAttribute("data-wx-day"))])
      .then(function (a) { clearTimeout(timer); finish(a[0], a[1]); }, function () { clearTimeout(timer); finish(null, null); });
  }
  // asked once a card comes near the screen: at once for the panel's (on screen from 1200px), when the reader
  // scrolls towards it for a home's (under the first screen); a card that is not shown (the panel below 1200px)
  // never comes near — until the window is widened. A card off the screen rests (its motion paused).
  if (win.IntersectionObserver) {
    var io = new win.IntersectionObserver(function (seen) {
      if (seen.some(function (e) { return e.isIntersecting; })) { io.disconnect(); ask(); }
    }, { rootMargin: "300px 0px" });
    boxes.forEach(function (b) { io.observe(b); });
    var rest = new win.IntersectionObserver(function (seen) {
      seen.forEach(function (e) { e.target.classList.toggle("is-off", !e.isIntersecting); });
    });
    boxes.forEach(function (b) { rest.observe(b); });
  } else if (boxes.some(function (b) { return b.getClientRects().length > 0; })) ask();
})();
