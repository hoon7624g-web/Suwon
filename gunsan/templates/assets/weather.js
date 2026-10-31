/* 군산각 — the day card's live parts (templates/_side.html.j2; operator 2026-10-31): 날씨각's weather module (the tab
   panel from 1200px, the homes under their first screen) and the panel's sunrise · sunset. site.js attaches this file
   after the page has loaded, when the browser is idle — nothing here competes with the first screen.
   - Sunrise · sunset ([data-sd-days] 'iso|rise|set|label;…', 한국천문연구원 via the build): the HTML shows the build day,
     its date written out; on the visitor's own date (Asia/Seoul) when the list has it, that day's label and times.
   - Weather ([data-wx]: the API address; data-wx-w the words — present.weather_vm, locales.SIDE_WORDS): asked once, when
     a module comes near the screen (the panel's from 1200px at once; a home's when the reader scrolls towards it; the
     panel is hidden below 1200px, so a phone page without the home's module never asks). The answer fills the
     module's kept room (css/80-side.css: nothing moves): the slot nearest now — its figure, sky icon and word, rain
     chance —, the provider's headline on the Korean pages only, the next slots' times and figures (the homes' module),
     '발표 HH:MM' and the source link. The other versions show figures, icons and times only (the provider's sentences are Korean). An
     answer that is late (8 s), fails, is not today's or has no slot leaves the module as built: its title and the
     link to weather.o2o.kr. No weather value is ever in the HTML (the page is static) — nor in search engines, the
     chat or the structured data. Text goes in through textContent only. Reduced motion: no fade. */
(function () {
  "use strict";
  var doc = document, win = window;
  var SVG = "http://www.w3.org/2000/svg";
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
  // the provider's icon keys (sun · moon · cloud · sunset · rain · snow); any other key draws the cloud, with no word
  var PATHS = {
    sun: "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM12 2.5V5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8",
    moon: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z",
    cloud: "M7 18.5h10a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.2 11.6 3.5 3.5 0 0 0 7 18.5Z",
    sunset: "M3 17.5h18M7 17.5a5 5 0 0 1 10 0M12 6.5v3M5.3 10.8l1.5 1.5M18.7 10.8l-1.5 1.5M8.5 21h7",
    rain: "M7 14.5h10a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.2 7.6 3.5 3.5 0 0 0 7 14.5ZM9 17.5l-1 3M13 17.5l-1 3M17 17.5l-1 3",
    snow: "M7 14.5h10a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.2 7.6 3.5 3.5 0 0 0 7 14.5ZM8.5 18.5h.01M12 20.5h.01M15.5 18.5h.01"
  };
  function icon(key) {
    var k = PATHS[key] ? key : "cloud";
    var s = doc.createElementNS(SVG, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("class", "wx-svg wx-k-" + (PATHS[key] ? key : "x"));
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    var p = doc.createElementNS(SVG, "path");
    p.setAttribute("d", PATHS[k]);
    s.appendChild(p);
    return s;
  }
  function el(tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function num(v) { return typeof v === "number" && isFinite(v); }
  function deg(v) { return Math.round(v) + "°"; }
  function hhmm(iso) { var m = /T(\d{2}:\d{2})/.exec(iso || ""); return m ? m[1] : ""; }

  var state = "";   // "" · "asking" · "ok" · "failed"
  var data = null;
  function words(box) {
    try { return JSON.parse(box.getAttribute("data-wx-w") || "{}"); } catch (e) { return {}; }
  }
  function slotsOf(j) {
    return (j.slots || []).filter(function (s) { return s && num(s.temp_c) && !isNaN(Date.parse(s.at)); });
  }
  function render(box) {
    var w = words(box), ko = !!w.ko, sky = w.sky || {};
    var slots = slotsOf(data), t = Date.now(), at = 0;
    slots.forEach(function (s, i) {
      if (Math.abs(Date.parse(s.at) - t) < Math.abs(Date.parse(slots[at].at) - t)) at = i;
    });
    var s = slots[at];
    var body = box.querySelector("[data-wx-b]");
    if (!body) return;
    var now = el("p", "wx-now");
    var ic = el("span", "wx-ic");
    ic.appendChild(icon(s.icon));
    now.appendChild(ic);
    now.appendChild(el("b", "wx-tmp tn", deg(s.temp_c)));
    if (sky[s.icon]) now.appendChild(el("span", "wx-sky", sky[s.icon]));
    if (num(s.rain_prob) && w.rain) now.appendChild(el("span", "wx-rp tn", w.rain.replace("{p}", String(Math.round(s.rain_prob)))));
    body.appendChild(now);
    if (ko && typeof data.headline === "string" && data.headline.trim()) body.appendChild(el("p", "wx-hl", data.headline.trim()));
    // the next slots' times and figures: the homes' module (the panel's keeps to the slot nearest now)
    var next = box.classList.contains("wx-home") ? slots.slice(at + 1, at + 6) : [];
    if (next.length) {
      var ol = el("ol", "wx-strip");
      next.forEach(function (n) {
        var li = el("li");
        li.appendChild(el("span", "wx-st tn", ko && n.label ? n.label : hhmm(n.at)));
        li.appendChild(icon(n.icon));
        li.appendChild(el("b", "tn", deg(n.temp_c)));
        ol.appendChild(li);
      });
      body.appendChild(ol);
    }
    var iss = box.querySelector("[data-wx-iss]");
    if (iss && w.issued && hhmm(data.issued_at)) iss.textContent = w.issued.replace("{t}", hhmm(data.issued_at));
    var go = box.querySelector("[data-wx-go]");
    if (go && w.src) {
      var x = go.querySelector("svg");
      go.textContent = w.src;
      if (x) go.appendChild(x);
    }
    box.classList.add("is-ready");
  }
  function finish(j) {
    if (state !== "asking") return;
    var ok = j && typeof j === "object" && (!day || j.day === day) && slotsOf(j).length > 0;
    state = ok ? "ok" : "failed";
    data = ok ? j : null;
    boxes.forEach(function (b) {
      if (ok) {
        try { render(b); } catch (e) { b.classList.add("is-failed"); }
      } else b.classList.add("is-failed");
    });
  }
  function ask() {
    if (state) return;
    state = "asking";
    var ctl = win.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); finish(null); }, 8000);
    win.fetch(boxes[0].getAttribute("data-wx"), { mode: "cors", credentials: "omit", signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { clearTimeout(timer); finish(j); }, function () { clearTimeout(timer); finish(null); });
  }
  // asked once a module comes near the screen: at once for the panel's (on screen from 1200px), when the reader
  // scrolls towards it for a home's (under the first screen); a module that is not shown (the panel below 1200px)
  // never comes near — until the window is widened
  if (win.IntersectionObserver) {
    var io = new win.IntersectionObserver(function (seen) {
      if (seen.some(function (e) { return e.isIntersecting; })) { io.disconnect(); ask(); }
    }, { rootMargin: "300px 0px" });
    boxes.forEach(function (b) { io.observe(b); });
  } else if (boxes.some(function (b) { return b.getClientRects().length > 0; })) ask();
})();
