/* Travel site — maps (progressive enhancement; attached by site.js when the page has a map box). Leaflet 1.9.4
   (self-hosted; map provider: Leaflet + OpenStreetMap tiles, operator decision 2026-10-16 — Kakao Maps only after the
   domain move) is fetched only when a box comes within 400px of the viewport, or when a folded map opens
   (gs:showmap), and never before the window 'load' event: nothing of it is on the first screen's critical path, and a
   page without a map box loads neither this file nor Leaflet. OSM tiles, toned down by the site stylesheet
   (css/30-info.css: tiles, markers, labels, controls); DivIcon markers; scroll-wheel zoom off; 44px zoom buttons;
   attribution kept; the map takes the focus (Leaflet's arrow keys move it, + and − zoom; its name says so). Every
   map has a text equivalent on the page; without JS the box is not shown (css/10-base.css), and when Leaflet fails
   the box keeps its text with the failure line. The words this file writes are Korean on Korean pages, English on
   the others — whose map boxes may carry their own (data-words {in, out, fail, keys}, en/_en.html.j2).

   MARKUP
     <div class="map" data-points='JSON' role="region" aria-label="…">   (data-map='JSON' is accepted too)
       optional data-leaflet-css / data-leaflet-js: where Leaflet lives (default: assets/vendor/leaflet/)
       optional <p class="map-off">…</p> inside: its own text says the page lists the same places (what a reader
       without the map gets); 'loading' once drawing starts, replaced by the map, the failure line if Leaflet fails
     JSON shapes (pipeline/present.py and build.map_points make them):
       [{lat, lng, name, url, kind?, n?}, …]      a list of places; with data-numbered="1" a numbered route
       {self: {lat, lng, name}, near: [{lat, lng, name, url, d, kind}], anchors: [{lat, lng, label}],
        radius?: metres}                          a place (or event) with its neighbours / a radius circle
       {course: [{lat, lng, name, url, n, extra?}]}   numbered stops (n = the stop list's number; ui.coursemap)
                                                  joined in order by a thin straight line; every stop keeps its
                                                  own marker (touching ones pushed apart, a hairline to the true
                                                  point); opens on the most stops that stand alone, the others
                                                  pointed at from the edge; '전체 보기' frames all (see COURSE
                                                  MAPS below); the blue progress line is drawn by course.js
       {guide: [...], route: bool}                numbered places (id: the place, gs:focus), joined only when route is true
       {list: [{lat, lng, name, url, id, kind, r}], far_label?, none_label?}   a list page's places (id = the row's
                                                  id: row ↔ marker; r = its 권역 / 구·군); only the places the list's
                                                  filter keeps (window.GSFilter / gs:filter), framed on them; each
                                                  marker named by its place, quiet beside the shown list (out of the
                                                  tab order: the rows are the same links), in the tab order where the
                                                  list is hidden (phones' 지도)
       {all: [...same...], anchor_pts: [{name, n, geo?}], far_label?, none_label?}   the map page: a label over each
                                                  group's points (an anchor's point when the group has none), an
                                                  edge control for the far group (far_label: site.json regions.far)
       far_label / none_label (site.json regions, present.map_vm): those groups do not frame the first view
       {anchors: [{lat, lng, name, n, url, place}]}  the home: the 권역 anchors labelled with their counts, each a
                                                  link to its region on /map/ (present.home_vm region_map)
     Every box gets data-lenis-prevent (wheel and touch on the map stay the map's).

   API: window.GSMaps (registry: {el, map, markers, data, frame, all, line, progress, lls, activeN, paint, showHome,
   showAround, whenIdle, progressTo}): a numbered map marks stop activeN .on and the earlier ones .past when paint()
   is called; a course map's showHome(fly) returns to its first view and showAround(n) moves to stop n when it is out
   of view (course.js; true when it moves); whenIdle(fn) runs fn once the map has stopped moving and returns a
   function that cancels it; progressTo(from, n) draws the blue line through stop n (the part after stop `from`
   draws itself along the straight lines unless motion is reduced). Numbered markers open their place on Enter or Space as on a click. Every built map
   dispatches gs:mapready {detail: registry entry} (bubbles to document). Listens to gs:hl, gs:filter, gs:focus,
   gs:region, gs:showmap (see site.js). window.GSMapStart(el) builds a box a script adds after load (the course
   planner's day maps, plan.js — the page has no map box of its own, so this file and Leaflet come only then). */
(function () {
  "use strict";
  var doc = document, win = window, maps = win.GSMaps = win.GSMaps || [], loading = null;
  var reduce = win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var BASE = ((doc.currentScript && doc.currentScript.src) || "/assets/map.js").replace(/[^/]*$/, "");
  var INK = "#1d1d1f", BLUE = "#0071e3";   // the Apple skin: ink for lines, the one blue for progress
  // the few words this file writes (zoom buttons, the failure line, how to move the map): Korean on Korean pages,
  // English on the other versions — whose map boxes may carry their own (data-words, en/_en.html.j2)
  var EN = !/^ko/i.test(doc.documentElement.lang || "ko");
  var W = (function () {
    var el = doc.querySelector(".map[data-words]");
    try { return el ? JSON.parse(el.getAttribute("data-words")) || {} : {}; } catch (e) { return {}; }
  })();
  function afterLoad(fn) { if (doc.readyState === "complete") fn(); else win.addEventListener("load", fn); }

  function css(href, before) {
    if (doc.querySelector('link[href="' + href + '"]')) return;
    var l = doc.createElement("link");
    l.rel = "stylesheet"; l.href = href;
    doc.head.insertBefore(l, before);
  }
  function load(el) {
    if (win.L) return Promise.resolve();
    if (loading) return loading;
    var first = doc.head.querySelector("link[rel=stylesheet]");
    // Leaflet's stylesheet goes before the site's own CSS, so the map skin there (css/30-info.css) still wins
    css(el.getAttribute("data-leaflet-css") || BASE + "vendor/leaflet/leaflet.css", first);
    loading = new Promise(function (res, rej) {
      var s = doc.createElement("script");
      s.src = el.getAttribute("data-leaflet-js") || BASE + "vendor/leaflet/leaflet.js";
      s.onload = function () { if (win.L) res(); else rej(); };
      s.onerror = rej;
      doc.head.appendChild(s);
    });
    loading.catch(function () { loading = null; });
    return loading;
  }
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function icon(cls, size, html) {
    return L.divIcon({ className: "", html: '<div class="' + cls + '">' + (html || "") + "</div>", iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
  }
  function label(html, cls, side, off) {
    return L.divIcon({ className: "", html: '<div class="mk-label ' + (cls || "") + '" style="transform:translate(' +
      (side === "l" ? "calc(-100% - " + off + "px)" : off + "px") + ',-50%)">' + html + "</div>", iconSize: [0, 0], iconAnchor: [0, 0] });
  }
  function kindIcon(kind) { return kind === "stay" ? icon("mk-ring", 11) : kind === "food" ? icon("mk-sq", 9) : icon("mk-dot", 10); }
  function textW(t) { return Math.min(280, 13.4 * String(t).length + 8); }
  function idOf(p) { return p.id || decodeURIComponent((p.url || "").split("/")[2] || ""); }
  function visible(el) { return el.offsetParent !== null && el.getBoundingClientRect().height > 0; }
  // a list map's filter (site.js keeps the list's shown row ids in window.GSFilter and sends gs:filter): the kept
  // points ({keep: {id: 1}, lls}), or null when every point is kept (the map then shows its whole frame)
  function picked(list, ids) {
    if (!ids) return null;
    var keep = {}, lls = [];
    ids.forEach(function (id) { keep[id] = 1; });
    list.forEach(function (p) { if (keep[idOf(p)]) lls.push([p.lat, p.lng]); });
    return lls.length === list.length ? null : { keep: keep, lls: lls };
  }
  // the view of a list map: the filtered places with coordinates (all of them, nothing trimmed), else the whole frame
  function listFit(r) {
    var s = r.picked;
    fitVisible(r.map, r.el, s && s.lls.length ? s.lls : r.frame, s && s.lls.length ? 36 : 28, s && s.lls.length ? 15 : 18);
  }
  // beside a shown list a list map's markers are quiet (out of the tab order, hidden from screen readers: the rows
  // are the same links); where the list is not shown (phones' 지도 view) they are named links in the tab order. The
  // list of /map/ (data.all) is its 권역 sections: quiet while one of them is shown
  function quietIcon(mk, quiet) {
    var a = mk._icon;
    if (!a) return;
    a.setAttribute("aria-label", mk._gs ? mk._gs.name : "");
    a.tabIndex = quiet ? -1 : 0;
    if (quiet) a.setAttribute("aria-hidden", "true"); else a.removeAttribute("aria-hidden");
  }
  function listQuiet(r) {
    if (!r.data.list && !r.data.all) return;
    var rows = doc.querySelectorAll(r.data.list ? "[data-ledger]" : "[data-region-sec]");
    r.quiet = Array.prototype.some.call(rows, visible);
    Object.keys(r.markers).forEach(function (id) { quietIcon(r.markers[id], r.quiet); });
  }
  // the middle of the points (outliers stay on the map, one zoom-out away)
  function robust(pts, f) {
    if (pts.length < 8) return pts;
    var la = pts.map(function (p) { return p[0]; }).sort(function (a, b) { return a - b; });
    var ln = pts.map(function (p) { return p[1]; }).sort(function (a, b) { return a - b; });
    var q = function (a, x) { return a[Math.min(a.length - 1, Math.max(0, Math.round((a.length - 1) * x)))]; };
    return [[q(la, f), q(ln, f)], [q(la, 1 - f), q(ln, 1 - f)]];
  }
  // a tall sticky map whose lower part is below the window at first view: frame the points in the visible part
  function hiddenBelow(el) {
    var r = el.getBoundingClientRect(), vh = win.innerHeight;
    return r.top < vh && r.bottom > vh ? Math.min(r.height - 160, r.bottom - vh) : 0;
  }
  function fitVisible(m, el, b, pad, max) {
    if (b.length === 1) { m.setView(b[0], 15, { animate: false }); return; }
    var hb = Math.max(0, hiddenBelow(el));
    m.fitBounds(b, { paddingTopLeft: [pad, pad], paddingBottomRight: [pad, pad + hb], maxZoom: max || 18, animate: false });
  }
  function base(el) {
    var m = L.map(el, { scrollWheelZoom: false, zoomControl: false, attributionControl: true });
    L.control.zoom({ position: "topleft", zoomInTitle: W.in || (EN ? "Zoom in" : "확대"), zoomOutTitle: W.out || (EN ? "Zoom out" : "축소") }).addTo(m);
    // the map takes the focus (Leaflet's keyboard): its name says how to move it
    var keys = W.keys || (!EN ? "화살표 키로 이동, + − 키로 확대·축소" : /^en/i.test(doc.documentElement.lang) ? "arrow keys move it, + and − zoom" : "");
    if (keys && el.getAttribute("aria-label")) el.setAttribute("aria-label", el.getAttribute("aria-label") + " · " + keys);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(m);
    m.attributionControl.setPrefix(false);
    return m;
  }
  // labels: nearest first; each tries right then left of its marker and is dropped when it would overlap a shown
  // label or another marker
  function declutter(m, items, markers) {
    var size = m.getSize(), shown = [];
    (markers || []).forEach(function (mk) {
      var p = m.latLngToContainerPoint(mk.ll), r = (mk.r || 6) + 2;
      shown.push([p.x - r, p.y - r, p.x + r, p.y + r]);
    });
    items.forEach(function (it) {
      var p = m.latLngToContainerPoint(it.ll), w = (it.w || 120) + 6, h = 20, gap = (it.r || 6) + 6, ok = null;
      ["r", "l"].some(function (side) {
        var box = side === "r" ? [p.x + gap, p.y - h / 2, p.x + gap + w, p.y + h / 2] : [p.x - gap - w, p.y - h / 2, p.x - gap, p.y + h / 2];
        if (box[0] < 50 || box[2] > size.x - 4 || box[1] < 4 || box[3] > size.y - 18) return false;
        var hit = shown.some(function (b) { return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]); });
        if (!hit) { ok = side; shown.push(box); }
        return !hit;
      });
      if (ok) { it.lab.setIcon(label(it.html, it.cls, ok, gap)); if (!m.hasLayer(it.lab)) it.lab.addTo(m); }
      else if (m.hasLayer(it.lab)) m.removeLayer(it.lab);
    });
  }
  function go(url) { return function () { if (url) location.href = url; }; }
  // a marker is a link: Enter or Space opens it too (Leaflet 1.9 turns no key on a marker into a click)
  function enterGo(url) {
    return function (e) {
      var k = e.originalEvent && e.originalEvent.key;
      if (url && (k === "Enter" || k === " ")) { e.originalEvent.preventDefault(); location.href = url; }
    };
  }

  // the passed part of a course's straight-line route (course.js through reg.progressTo): the blue line through stop
  // n draws itself from the previous stop, after the map has settled (pixel lengths are then final); reduced motion,
  // going back or a first stop: set at once
  function upto(r, n) { var out = []; r.data.course.forEach(function (p) { if (!p.extra && p.n <= n) out.push([p.lat, p.lng]); }); return out; }
  function pxLen(m, lls) { var t = 0; for (var i = 1; i < lls.length; i++) t += m.latLngToLayerPoint(lls[i - 1]).distanceTo(m.latLngToLayerPoint(lls[i])); return t; }
  function drawRoute(r, m, from, n) {
    if (!r.progress) return;
    var done = upto(r, n);
    r.progress.setLatLngs(n > 0 ? done : []);
    var path = r.progress._path;
    var reset = function () { if (path) { path.style.transition = "none"; path.style.strokeDasharray = ""; path.style.strokeDashoffset = ""; } };
    if (!path || reduce || n <= from || n < 2) { reset(); return; }
    var len = pxLen(m, done), prev = pxLen(m, upto(r, from));
    path.style.transition = "none";
    path.style.strokeDasharray = len + " " + len;
    path.style.strokeDashoffset = String(len - prev);
    path.getBoundingClientRect();
    path.style.transition = "stroke-dashoffset 1.1s cubic-bezier(.65,0,.35,1)";
    path.style.strokeDashoffset = "0";
    var clear = function () { reset(); path.removeEventListener("transitionend", clear); };
    path.addEventListener("transitionend", clear);
  }

  /* COURSE MAPS (ui.coursemap). Every stop keeps its own numbered marker — nothing is merged into a range:
     - spread(): markers that would touch at this zoom are pushed apart from their true points as little as needed
       (stops at one spot ring round it in number order); a hairline joins a moved marker to its true point;
     - bestFrame(): the first view is the box at the zoom (street level outwards) that holds the most stops whose
       markers stand alone (no marker moved more than MAXOFF px) — so a course in two places opens on the place
       with more stops, never on a few dots joined by one long line;
     - edge chips: the stops outside the view are pointed at from the box edge (an arrow towards them and their
       numbers); pressing one moves the map to them. '전체 보기' frames every stop. */
  // marker, centre gap, largest move; box padding (left: clear of the zoom buttons, top: of '전체 보기'); edge chip
  // thickness and margin (its hit area is 44px: css .mk-edge::before)
  var MK = 28, MIN = MK + 3, MAXOFF = 22, CPAD = [68, 62, 54, 54], CHIP_T = 32, CHIP_M = 8;
  var DIRS = EN ? ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]
    : ["동쪽", "남동쪽", "남쪽", "남서쪽", "서쪽", "북서쪽", "북쪽", "북동쪽"];
  function spread(P, rings) {
    var n = P.length, pos = P.map(function (p) { return [p.x, p.y]; }), max = 0, seen = {}, i, j, it;
    // piles: markers that would sit on one another (chained: centres closer than MIN). Stops at one spot are set
    // round it in number order, clockwise from the top (two: side by side); with rings, so is a pile whose points
    // lie closer together than its ring would be (a zoomed-out view); the rest are pushed apart where they touch.
    for (i = 0; i < n; i++) {
      if (seen[i]) continue;
      var g = [i], q = 0;
      seen[i] = 1;
      while (q < g.length) { var a = g[q++]; for (j = 0; j < n; j++) if (!seen[j] && P[a].distanceTo(P[j]) < MIN) { seen[j] = 1; g.push(j); } }
      if (g.length < 2) continue;
      g.sort(function (x, y) { return x - y; }); // items come in course order
      var cx = 0, cy = 0, ext = 0, R = g.length === 2 ? MIN / 2 : MIN / (2 * Math.sin(Math.PI / g.length));
      g.forEach(function (k) { cx += P[k].x / g.length; cy += P[k].y / g.length; });
      g.forEach(function (k) { ext = Math.max(ext, Math.sqrt(Math.pow(P[k].x - cx, 2) + Math.pow(P[k].y - cy, 2))); });
      if (ext > (rings ? R * 0.8 : 0.5)) continue;
      g.forEach(function (k, r) {
        var ang = g.length === 2 ? (r ? 0 : Math.PI) : -Math.PI / 2 + r * 2 * Math.PI / g.length;
        pos[k] = [cx + Math.cos(ang) * R, cy + Math.sin(ang) * R];
      });
    }
    for (it = 0; it < 150; it++) {
      var moved = false;
      for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
        var dx = pos[j][0] - pos[i][0], dy = pos[j][1] - pos[i][1], dd = Math.sqrt(dx * dx + dy * dy);
        if (dd >= MIN - 0.05) continue;
        if (dd < 1e-6) { dx = 1; dy = 0; dd = 1; }
        var k = (MIN - dd) / 2 / dd;
        pos[i][0] -= dx * k; pos[i][1] -= dy * k; pos[j][0] += dx * k; pos[j][1] += dy * k;
        moved = true;
      }
      if (!moved) break;
    }
    for (i = 0; i < n; i++) max = Math.max(max, Math.sqrt(Math.pow(pos[i][0] - P[i].x, 2) + Math.pow(pos[i][1] - P[i].y, 2)));
    return { pos: pos, max: max };
  }
  // the view {c: centre, z} that shows the most stops of pool (indices; default all) standing alone; with must, a
  // view that holds that stop. A view is judged as it will be drawn (the whole zoom level that fits the stops, centred
  // in the padded box, slid a little when that clears an edge): every stop it shows must stand alone, and none may
  // sit cut at an edge or under a control — each is well inside or off the view, where an edge chip points at it.
  function bestFrame(m, items, pool, must) {
    pool = pool || items.map(function (it, q) { return q; });
    var sz = m.getSize(), w = sz.x - CPAD[0] - CPAD[2], h = sz.y - CPAD[1] - CPAD[3], best = null, tried = {};
    var host = m.getContainer(), E = MK / 2 + 6, R = MK / 2 + 2, BOT = 16; // BOT: the credit line
    var ctl = Array.prototype.filter.call(host.querySelectorAll(".leaflet-top .leaflet-control"), function (el) { return el.offsetWidth > 0; })
      .map(function (el) { return boxOf(el, host); });
    var off = function (x, y) { return x < -R || y < -R || x > sz.x + R || y > sz.y + R; };
    var clear = function (x, y) {
      return x >= E && y >= E && x <= sz.x - E && y <= sz.y - E - BOT && !ctl.some(function (a) { return x + R > a[0] && x - R < a[2] && y + R > a[1] && y - R < a[3]; });
    };
    function judge(P, S, z) {
      var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      S.forEach(function (q) { x0 = Math.min(x0, P[q].x); x1 = Math.max(x1, P[q].x); y0 = Math.min(y0, P[q].y); y1 = Math.max(y1, P[q].y); });
      var one = S.length === 1, zf = one ? 15 : Math.min(16, z + Math.floor(Math.log(Math.min(x1 > x0 ? w / (x1 - x0) : 1e9, y1 > y0 ? h / (y1 - y0) : 1e9)) / Math.LN2 + 1e-9));
      var f = Math.pow(2, zf - z), Q = P.map(function (pt) { return L.point(pt.x * f, pt.y * f); });
      var cx = (x0 + x1) / 2 * f + (one ? 0 : (CPAD[2] - CPAD[0]) / 2), cy = (y0 + y1) / 2 * f + (one ? 0 : (CPAD[3] - CPAD[1]) / 2);
      // slides to try: none, then each that moves a stop caught at an edge fully in or fully out
      var dxs = [0], dys = [0];
      Q.forEach(function (pt) {
        var x = pt.x - cx + sz.x / 2, y = pt.y - cy + sz.y / 2;
        if (off(x, y) || clear(x, y)) return;
        dxs.push(E - x, sz.x - E - x, -R - 1 - x, sz.x + R + 1 - x);
        dys.push(E - y, sz.y - E - BOT - y, -R - 1 - y, sz.y + R + 1 - y);
      });
      var tries = [];
      dxs.forEach(function (dx) { dys.forEach(function (dy) { if (Math.abs(dx) <= 48 && Math.abs(dy) <= 48) tries.push([dx, dy]); }); });
      tries.sort(function (a, b) { return Math.abs(a[0]) + Math.abs(a[1]) - Math.abs(b[0]) - Math.abs(b[1]); });
      for (var t = 0; t < tries.length && t < 40; t++) {
        var vx = cx - tries[t][0], vy = cy - tries[t][1], ok = true, V = [];
        for (var q = 0; q < Q.length && ok; q++) {
          var x = Q[q].x - vx + sz.x / 2, y = Q[q].y - vy + sz.y / 2;
          if (off(x, y)) { if (S.indexOf(q) >= 0) ok = false; continue; }
          if (!clear(x, y)) ok = false; else V.push(Q[q]);
        }
        if (ok && spread(V, false).max <= MAXOFF) return { S: S, z: zf, c: m.unproject(L.point(vx, vy), zf) };
      }
      return null;
    }
    for (var z = 16; z >= 4; z--) { // whole zoom levels only: tiles stay crisp, with no seams between scaled tiles
      var P = items.map(function (it) { return m.project(it.ll, z); });
      for (var i = 0; i < pool.length; i++) for (var j = 0; j < pool.length; j++) {
        var S = pool.filter(function (k) { return P[k].x >= P[pool[i]].x - 1e-6 && P[k].x <= P[pool[i]].x + w && P[k].y >= P[pool[j]].y - 1e-6 && P[k].y <= P[pool[j]].y + h; });
        if ((best && S.length <= best.S.length) || (must != null && S.indexOf(must) < 0)) continue;
        var key = S.join(",");
        if (tried[key]) continue;
        tried[key] = 1;
        best = judge(P, S, z) || best;
      }
      if (best && best.S.length === pool.length) break;
    }
    if (!best) { var q0 = must != null ? must : pool[0]; best = { S: [q0], z: 15, c: items[q0].ll }; }
    return best;
  }
  function frameOpts(animate) {
    return { paddingTopLeft: [CPAD[0], CPAD[1]], paddingBottomRight: [CPAD[2], CPAD[3]], maxZoom: 16,
      animate: animate && !reduce, duration: reduce ? 0 : 0.7 };
  }
  // a view from bestFrame ({c, z}), or every stop (fitted in the padded box); fly when asked
  function showStops(reg, m, view, fly) {
    if (view.c) { if (fly) m.flyTo(view.c, view.z, frameOpts(true)); else m.setView(view.c, view.z, { animate: false }); }
    else if (fly) m.flyToBounds(reg.lls, frameOpts(true));
    else m.fitBounds(reg.lls, frameOpts(false));
    if (!fly) placeStops(reg, m);
  }
  // markers at this zoom: pushed apart where they would touch, a hairline from each moved marker to its point
  function placeStops(reg, m) {
    var P = reg.items.map(function (it) { return m.latLngToLayerPoint(it.ll); }), r = spread(P, false);
    if (r.max > MAXOFF) r = spread(P, true); // piled up (zoomed out): rings in number order read better
    reg.legs.clearLayers();
    reg.items.forEach(function (it, i) {
      var q = L.point(r.pos[i][0], r.pos[i][1]);
      it.at = m.layerPointToLatLng(q);
      it.mk.setLatLng(it.at);
      if (q.distanceTo(P[i]) > 5) {
        L.polyline([it.ll, it.at], { color: INK, weight: 1, opacity: 0.6, interactive: false }).addTo(reg.legs);
        L.circleMarker(it.ll, { radius: 2.5, stroke: false, fillColor: INK, fillOpacity: 0.85, interactive: false }).addTo(reg.legs);
      }
    });
  }
  function boxOf(el, host) {
    var a = el.getBoundingClientRect(), b = host.getBoundingClientRect();
    return [a.left - b.left - 6, a.top - b.top - 6, a.right - b.left + 6, a.bottom - b.top + 6];
  }
  function hits(a, b) { return !(a[2] <= b[0] || a[0] >= b[2] || a[3] <= b[1] || a[1] >= b[3]); }
  // the stops outside the view, pointed at from the box edge in their direction (8 directions from the centre);
  // chips that would overlap are joined. '전체 보기' shows only while some stop is outside.
  function edgeChips(reg, m) {
    var host = m.getContainer(), sz = m.getSize(), c = L.point(sz.x / 2, sz.y / 2), groups = [], by = {};
    reg.items.forEach(function (it) {
      var p = m.latLngToContainerPoint(it.at || it.ll);
      if (p.x >= 0 && p.y >= 0 && p.x <= sz.x && p.y <= sz.y) return;
      var s = (Math.round(Math.atan2(p.y - c.y, p.x - c.x) / (Math.PI / 4)) + 8) % 8;
      if (!by[s]) groups.push(by[s] = { items: [], ps: [] });
      by[s].items.push(it); by[s].ps.push(p);
    });
    if (reg.allBtn) reg.allBtn.hidden = !groups.length;
    var avoid = Array.prototype.filter.call(host.querySelectorAll(".leaflet-control"), function (el) { return el.offsetWidth > 0; })
      .map(function (el) { return boxOf(el, host); });
    var place = function (g) {
      var x = 0, y = 0;
      g.ps.forEach(function (p) { x += p.x / g.ps.length; y += p.y / g.ps.length; });
      x -= c.x; y -= c.y;
      g.ang = Math.atan2(y, x);
      var k = g.items.length > 6 ? 5 : g.items.length, len = 34 + k * 24 + (g.items.length > k ? 26 : 0);
      var tx = Math.abs(x) > 1e-6 ? (sz.x / 2) / Math.abs(x) : 1e9, ty = Math.abs(y) > 1e-6 ? (sz.y / 2) / Math.abs(y) : 1e9;
      g.vert = tx < ty; // through a side: a vertical pill on it; through the top or bottom: a horizontal one
      var t = Math.min(tx, ty), px = c.x + x * t, py = c.y + y * t, b;
      if (g.vert) { var bx = x > 0 ? sz.x - CHIP_M - CHIP_T : CHIP_M; b = [bx, py - len / 2, bx + CHIP_T, py + len / 2]; }
      else { var by = y > 0 ? sz.y - CHIP_M - CHIP_T : CHIP_M; b = [px - len / 2, by, px + len / 2, by + CHIP_T]; }
      var clamp = function () {
        var dx = Math.max(0, CHIP_M - b[0]) - Math.max(0, b[2] - (sz.x - CHIP_M)), dy = Math.max(0, CHIP_M - b[1]) - Math.max(0, b[3] - (sz.y - CHIP_M));
        b = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy];
      };
      clamp();
      for (var pass = 0; pass < 3; pass++) avoid.forEach(function (a) { // slide along the edge, away from the control
        if (!hits(b, a)) return;
        var d = g.vert ? ((b[1] + b[3]) / 2 < (a[1] + a[3]) / 2 && a[1] - (b[3] - b[1]) >= CHIP_M ? a[1] - b[3] : a[3] - b[1])
          : ((b[0] + b[2]) / 2 < (a[0] + a[2]) / 2 && a[0] - (b[2] - b[0]) >= CHIP_M ? a[0] - b[2] : a[2] - b[0]);
        if (g.vert) { b[1] += d; b[3] += d; } else { b[0] += d; b[2] += d; }
        clamp();
      });
      g.b = b;
    };
    groups.forEach(place);
    for (var again = true; again;) { // two chips that touch become one
      again = false;
      for (var i = 0; i < groups.length && !again; i++) for (var j = i + 1; j < groups.length && !again; j++) {
        if (!hits(groups[i].b, groups[j].b)) continue;
        groups[i].items = groups[i].items.concat(groups[j].items); groups[i].ps = groups[i].ps.concat(groups[j].ps);
        groups.splice(j, 1); place(groups[i]); again = true;
      }
    }
    var box = reg.chips, had = box.contains(doc.activeElement);
    box.innerHTML = "";
    groups.forEach(function (g) {
      g.items.sort(function (a, b) { return a.n - b.n; });
      var ns = g.items.map(function (it) { return it.n; }), shown = g.items.length > 6 ? ns.slice(0, 5) : ns;
      var dir = DIRS[(Math.round(g.ang / (Math.PI / 4)) + 8) % 8];
      var b = doc.createElement("button");
      b.type = "button"; b.className = "mk-edge" + (g.vert ? " vert" : "");
      b.style.left = Math.round(g.b[0]) + "px"; b.style.top = Math.round(g.b[1]) + "px";
      b.setAttribute("aria-label", EN ? "Stops " + ns.join(", ") + " (" + g.items[0].name + (ns.length > 1 ? " and " + (ns.length - 1) + " more" : "") + ") lie off the map to the " + dir + " · show them"
        : ns.join(", ") + "번 경유지(" + g.items[0].name + (ns.length > 1 ? " 외 " + (ns.length - 1) + "곳" : "") + ")가 지도 밖 " + dir + "에 있습니다 · 눌러서 보기");
      b.title = g.items.map(function (it) { return it.n + ". " + it.name; }).join("\n");
      b.innerHTML = '<svg class="me-arr" viewBox="0 0 16 16" aria-hidden="true" style="transform:rotate(' + (g.ang * 180 / Math.PI).toFixed(1) +
        'deg)"><path d="M2 8h11M9 4l4 4-4 4"/></svg>' + shown.map(function (n) { return '<span class="me-n" aria-hidden="true">' + n + "</span>"; }).join("") +
        (ns.length > shown.length ? '<span class="me-more" aria-hidden="true">+' + (ns.length - shown.length) + "</span>" : "");
      L.DomEvent.disableClickPropagation(b);
      L.DomEvent.disableScrollPropagation(b);
      b.addEventListener("click", function () { showStops(reg, m, bestFrame(m, reg.items, g.items.map(function (it) { return reg.items.indexOf(it); })), true); });
      box.appendChild(b);
    });
    if (had) (box.firstChild || reg.allBtn || host).focus();
  }
  function courseMap(reg, m) {
    reg.legs = L.layerGroup().addTo(m);
    reg.chips = L.DomUtil.create("div", "mk-edges", m.getContainer());
    var All = L.Control.extend({ options: { position: "topright" }, onAdd: function () {
      var b = L.DomUtil.create("button", "far-ctl map-all");
      b.type = "button";
      b.textContent = EN ? "Whole course" : "전체 보기";
      L.DomEvent.disableClickPropagation(b);
      b.addEventListener("click", function () { showStops(reg, m, {}, true); });
      reg.allBtn = b;
      return b;
    } });
    new All().addTo(m);
    reg.home = bestFrame(m, reg.items);
    reg.showHome = function (fly) { showStops(reg, m, reg.home, fly); };
    reg.showAround = function (n) { // course.js: the view that holds stop n (the current one when n is in it)
      var it = reg.items.filter(function (x) { return x.n === n; })[0];
      if (!it) return false;
      var p = m.latLngToContainerPoint(it.at || it.ll), sz = m.getSize();
      if (p.x > CPAD[0] - 10 && p.y > CPAD[1] - 10 && p.x < sz.x - CPAD[2] + 10 && p.y < sz.y - CPAD[3] + 10) return false;
      showStops(reg, m, bestFrame(m, reg.items, null, reg.items.indexOf(it)), true);
      return true;
    };
    m.on("zoomend", function () { placeStops(reg, m); });
    m.on("moveend resize", function () { edgeChips(reg, m); });
    reg.showHome(false);
    edgeChips(reg, m);
  }

  function normalise(raw, el) {
    if (Array.isArray(raw)) return el.hasAttribute("data-numbered") ? { course: raw } : { list: raw };
    return raw || {};
  }

  function build(el) {
    var d;
    try { d = normalise(JSON.parse(el.getAttribute("data-points") || el.getAttribute("data-map")), el); } catch (e) { return null; }
    var pts0 = d.self ? [d.self] : (d.course || d.guide || d.list || d.all || d.anchors || []);
    if (!pts0.length) return null; // nothing to draw: the box keeps its text
    var reg = { el: el, map: null, markers: {}, items: [], data: d }, m;
    el.innerHTML = "";
    if (d.self) { // a place or an event: itself, its neighbours, labelled straight-line anchors, or a radius
      var c = [d.self.lat, d.self.lng];
      m = base(el);
      m.setView(c, 15);
      L.marker(c, { icon: icon("mk-self", 22), keyboard: false, title: d.self.name }).addTo(m);
      var items = [{ ll: L.latLng(c), html: esc(d.self.name), cls: "self", w: textW(d.self.name) + 6, r: 11 }];
      var mks = [], bounds = [c];
      (d.near || []).forEach(function (n, i) {
        var ll = [n.lat, n.lng];
        var mk = L.marker(ll, { icon: kindIcon(n.kind), title: n.name + (n.d ? " " + n.d : "") }).addTo(m);
        mk.on("click", go(n.url));
        mks.push({ ll: L.latLng(ll), r: 6 });
        if (i < 6) items.push({ ll: L.latLng(ll), html: esc(n.name) + (n.d ? "<small>" + esc(n.d) + "</small>" : ""), w: textW(n.name + (n.d || "")), r: 6 });
        if (i < 8) bounds.push(ll);
      });
      (d.anchors || []).forEach(function (a) {
        L.polyline([c, [a.lat, a.lng]], { color: INK, weight: 1.2, dashArray: "2 5", opacity: 0.7, interactive: false }).addTo(m);
        L.marker([a.lat, a.lng], { icon: icon("mk-anchor", 12), title: a.label || a.name }).addTo(m);
        mks.push({ ll: L.latLng(a.lat, a.lng), r: 7 });
        items.push({ ll: L.latLng(a.lat, a.lng), html: esc(a.label || a.name), w: textW(a.label || a.name), r: 7 });
        bounds.push([a.lat, a.lng]);
      });
      if (d.radius) {
        L.circle(c, { radius: d.radius, color: INK, weight: 1, dashArray: "3 5", fill: false, interactive: false }).addTo(m);
        m.fitBounds(L.latLng(c).toBounds(d.radius * 2.25), { animate: false });
      } else if (bounds.length > 1) m.fitBounds(bounds, { padding: [40, 40], maxZoom: 16, animate: false });
      items.forEach(function (it) { it.lab = L.marker(it.ll, { interactive: false, keyboard: false }); });
      var redraw = function () { declutter(m, items, mks); };
      m.on("zoomend moveend", redraw);
      redraw();
    } else if (d.course || d.guide) { // numbered stops; a straight line in order (course: thin solid; routed guide: dashed)
      var pts = d.course || d.guide, route = !!d.course || !!d.route, lls = [];
      m = base(el);
      reg.byId = {}; // a guide's places by id (gs:focus)
      pts.forEach(function (p) {
        var ll = [p.lat, p.lng], extra = !!p.extra;
        var mk = L.marker(ll, { icon: icon("mk-num" + (extra ? " extra" : ""), extra ? 14 : MK, extra ? "" : esc(p.n)),
          title: (extra ? "" : p.n + ". ") + p.name, riseOnHover: true }).addTo(m);
        mk.on("click", go(p.url));
        mk.on("keydown", enterGo(p.url));
        if (p.id) reg.byId[p.id] = mk;
        if (extra) mk.bindTooltip(esc(p.name), { className: "tt-map", direction: "top" });
        else { reg.markers[p.n] = mk; lls.push(ll); reg.items.push({ n: +p.n, ll: L.latLng(ll), mk: mk, name: p.name }); }
      });
      reg.paint = function () { // the stop being read (.on) and the stops before it (.past)
        var n = reg.activeN || 0, cls = function (el, on, past) { if (el) { el.classList.toggle("on", on); el.classList.toggle("past", past); } };
        Object.keys(reg.markers).forEach(function (k) {
          var mk = reg.markers[k];
          cls(mk._icon && mk._icon.firstChild, +k === n, n > 0 && +k < n);
          mk.setZIndexOffset(+k === n ? 1000 : 0);
        });
      };
      if (route && lls.length > 1) {
        reg.line = L.polyline(lls, d.course ? { color: INK, weight: 2, opacity: 0.55, lineJoin: "round", interactive: false }
          : { color: INK, weight: 2, opacity: 0.5, dashArray: "5 7", interactive: false }).addTo(m);
        reg.progress = L.polyline([], { color: BLUE, weight: 4.5, opacity: 1, lineCap: "round", lineJoin: "round",
          className: "course-progress", interactive: false }).addTo(m);
      }
      reg.lls = lls;
      reg.whenIdle = function (fn) { m.once("moveend", fn); return function () { m.off("moveend", fn); }; };
      reg.progressTo = function (from, n) { drawRoute(reg, m, from, n); };
      var frame = lls.length ? lls : pts.map(function (p) { return [p.lat, p.lng]; });
      reg.frame = route ? frame : robust(frame, 0.03);
      reg.all = L.latLngBounds(reg.frame);
      // a course map opens on the most stops that stand alone in the whole box (sticky on desktop: framing only the
      // part above the fold would shrink it); the rest are pointed at from the edge
      if (d.course && reg.items.length > 1) courseMap(reg, m);
      else fitVisible(m, el, reg.frame, 44, 16);
    } else if (d.list || d.all) { // a list page, or the map page with its 권역
      var list = d.list || d.all;
      m = base(el);
      // a list page's filter set before this map was built (phones build it at the first 지도): only those places,
      // framed from the first view
      reg.picked = d.list ? picked(list, win.GSFilter && win.GSFilter.ids) : null;
      list.forEach(function (p) {
        var id = idOf(p), mk = L.marker([p.lat, p.lng], { icon: kindIcon(p.kind), title: p.name });
        if (!reg.picked || reg.picked.keep[id]) mk.addTo(m);
        mk.bindTooltip(esc(p.name), { className: "tt-map", direction: "top", offset: [0, -6] });
        mk.on("click", go(p.url));
        mk.on("keydown", enterGo(p.url));
        mk.on("mouseover", function () { doc.dispatchEvent(new CustomEvent("gs:hlrow", { detail: { id: id, on: true } })); });
        mk.on("mouseout", function () { doc.dispatchEvent(new CustomEvent("gs:hlrow", { detail: { id: id, on: false } })); });
        mk._gs = p;
        reg.markers[id] = mk;
      });
      var farL = d.far_label || "", noneL = d.none_label || "";
      var main = list.filter(function (p) { return !(farL && p.r === farL) && !(noneL && p.r === noneL); }).map(function (p) { return [p.lat, p.lng]; });
      if (!main.length) main = list.map(function (p) { return [p.lat, p.lng]; });
      reg.frame = robust(main, d.all ? 0.03 : 0.08);
      reg.all = L.latLngBounds(reg.frame);
      reg.map = m;
      if (d.list) listFit(reg); else fitVisible(m, el, reg.frame, 28);
      listQuiet(reg);
      if (d.anchor_pts) regions(reg, m, list, main, d.anchor_pts, farL);
    } else if (d.anchors) { // the home: the 권역 anchors labelled with their counts; each links to its region on /map/
      m = base(el);
      var alls = [];
      d.anchors.forEach(function (a) {
        var ll = [a.lat, a.lng];
        alls.push(ll);
        var mk = L.marker(ll, { icon: icon("mk-anchor", 14), title: a.name + " " + a.n + "곳 · 기준점 " + a.place }).addTo(m);
        mk.on("click", go(a.url));
        L.marker(ll, { interactive: false, keyboard: false, icon: L.divIcon({ className: "", iconSize: [0, 0],
          html: '<div class="mk-region" style="transform:translate(-50%,calc(-100% - 10px))">' + esc(a.name) + "<small>" + a.n + "곳</small></div>" }) }).addTo(m);
      });
      reg.frame = alls;
      m.fitBounds(alls, { padding: [56, 40], animate: false });
      reg.all = L.latLngBounds(alls);
    } else {
      return null;
    }
    reg.map = m;
    maps.push(reg);
    el.dispatchEvent(new CustomEvent("gs:mapready", { bubbles: true, detail: reg }));
    return reg;
  }

  // the map page: a label above each group's points (collision-checked) and an edge control for the far group
  function regions(reg, m, list, main, anchors, farL) {
    reg.regions = anchors.map(function (a) {
      var ps = list.filter(function (p) { return p.r === a.name; });
      var la = ps.map(function (p) { return p.lat; }).sort(function (x, y) { return x - y; });
      var ln = ps.map(function (p) { return p.lng; }).sort(function (x, y) { return x - y; });
      var ll = ps.length ? [la[Math.floor((la.length - 1) * 0.9)], ln[ln.length >> 1]] : (a.geo ? [a.geo.lat, a.geo.lng] : null);
      return ll ? { name: a.name, n: a.n, ll: L.latLng(ll), lab: L.marker(ll, { interactive: false, keyboard: false }) } : null;
    }).filter(Boolean);
    reg.drawRegions = function (sel) {
      var shown = [];
      reg.regions.slice().sort(function (x, y) { return y.n - x.n; }).forEach(function (r) {
        var on = !sel || sel === r.name, p = m.latLngToContainerPoint(r.ll), w = textW(r.name) + 50, h = 24;
        var box = [p.x - w / 2, p.y - h - 10, p.x + w / 2, p.y - 10];
        var hit = shown.some(function (b) { return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]); });
        if (on && !hit) {
          shown.push(box);
          r.lab.setIcon(L.divIcon({ className: "", iconSize: [0, 0], html: '<div class="mk-region' + (sel ? " sel" : "") +
            '" style="transform:translate(-50%,calc(-100% - 10px))">' + esc(r.name) + "<small>" + r.n + "곳</small></div>" }));
          if (!m.hasLayer(r.lab)) r.lab.addTo(m);
        } else if (m.hasLayer(r.lab)) m.removeLayer(r.lab);
      });
    };
    m.on("zoomend moveend", function () { reg.drawRegions(reg.sel); });
    reg.drawRegions("");
    var far = farL ? list.filter(function (p) { return p.r === farL; }) : [];
    if (!far.length) return;
    var Far = L.Control.extend({ options: { position: "bottomleft" }, onAdd: function () {
      var b = L.DomUtil.create("button", "far-ctl");
      b.type = "button";
      var names = far.map(function (p) { return p.name; }).slice(0, 2).join("·");
      b.textContent = "← " + farL + " " + far.length + "곳 (" + names + (far.length > 2 ? " 등" : "") + ")";
      L.DomEvent.disableClickPropagation(b);
      b.addEventListener("click", function () {
        m.flyToBounds(far.map(function (p) { return [p.lat, p.lng]; }).concat(main.slice(0, 1)), { padding: [40, 40], duration: reduce ? 0 : 0.8, animate: !reduce });
      });
      return b;
    } });
    new Far().addTo(m);
  }

  // a row lights its marker (state change only, nothing moves)
  doc.addEventListener("gs:hl", function (e) {
    maps.forEach(function (r) {
      var mk = r.markers[e.detail.id] || r.markers[decodeURIComponent(e.detail.id)];
      if (!mk || !mk._icon) return;
      var inner = mk._icon.firstChild;
      if (inner) inner.classList.toggle("mk-hl", e.detail.on);
      mk.setZIndexOffset(e.detail.on ? 1000 : 0);
    });
  });
  // the list's filter (site.js; also sent when only the 목록 | 지도 view changes): the kept markers shown, the others
  // taken off, and the map framed on the kept ones when the set has changed and the map is on screen (a hidden map
  // is framed when it is shown: gs:showmap)
  doc.addEventListener("gs:filter", function (e) {
    maps.forEach(function (r) {
      if (!r.data.list) return;
      var was = r.picked ? r.picked.lls.join(";") : "", s = r.picked = picked(r.data.list, e.detail.ids);
      Object.keys(r.markers).forEach(function (id) {
        var mk = r.markers[id];
        if (!s || s.keep[id]) { if (!r.map.hasLayer(mk)) mk.addTo(r.map); } else if (r.map.hasLayer(mk)) r.map.removeLayer(mk);
      });
      listQuiet(r);
      if ((s ? s.lls.join(";") : "") !== was && visible(r.el)) listFit(r);
    });
  });
  var lastRegion = null;
  function applyRegion(r, det) {
    if (!r.data.all) return;
    var pts = [];
    Object.keys(r.markers).forEach(function (id) {
      var mk = r.markers[id], p = mk._gs, ok = (!det.region || p.r === det.region) && det.kinds[p.kind || "attraction"] !== false;
      if (ok) { if (!r.map.hasLayer(mk)) mk.addTo(r.map); pts.push([p.lat, p.lng]); } else if (r.map.hasLayer(mk)) r.map.removeLayer(mk);
    });
    r.sel = det.region;
    listQuiet(r); // markers added back have new icons
    if (det.region && pts.length) r.map.flyToBounds(pts, { padding: [36, 36], maxZoom: 15, duration: reduce ? 0 : 0.8, animate: !reduce });
    else if (!det.region) r.map.fitBounds(r.all, { animate: !reduce });
    if (r.drawRegions) r.drawRegions(det.region);
  }
  doc.addEventListener("gs:region", function (e) { lastRegion = e.detail; maps.forEach(function (r) { applyRegion(r, e.detail); }); });
  doc.addEventListener("gs:mapready", function (e) { if (lastRegion) applyRegion(e.detail, lastRegion); });
  // a guide's map beside its text follows the section being read (site.js gs:focus {ids}): that section's places
  // are lit (.on), the others step back (.dim), and the map moves to them; no ids = every place, the whole frame.
  // Reduced motion: the same view, without the flight.
  var lastFocus = null;
  function applyFocus(r, ids) {
    if (!r.byId || !r.data.guide) return;
    var lls = [];
    Object.keys(r.byId).forEach(function (id) {
      var mk = r.byId[id], on = ids.indexOf(id) > -1, inner = mk._icon && mk._icon.firstChild;
      if (inner) { inner.classList.toggle("on", on); inner.classList.toggle("dim", ids.length > 0 && !on); }
      mk.setZIndexOffset(on ? 1000 : 0);
      if (on) lls.push(mk.getLatLng());
    });
    var target = lls.length ? L.latLngBounds(lls) : r.all;
    if (target) r.map.flyToBounds(target, { padding: [56, 56], maxZoom: 15, duration: reduce ? 0 : 0.9, animate: !reduce });
  }
  doc.addEventListener("gs:focus", function (e) { lastFocus = (e.detail && e.detail.ids) || []; maps.forEach(function (r) { applyFocus(r, lastFocus); }); });
  doc.addEventListener("gs:mapready", function (e) { if (lastFocus && lastFocus.length) applyFocus(e.detail, lastFocus); });
  win.addEventListener("resize", function () { maps.forEach(listQuiet); }); // the list shows or hides beside the map at 1024px
  win.GSMapsReady = function (fn) { maps.forEach(fn); doc.addEventListener("gs:mapready", function (e) { fn(e.detail); }); };
  // a map box a script adds later (the course planner's day map, plan.js): built at once, Leaflet after 'load'
  win.GSMapStart = function (el) { el.setAttribute("data-lenis-prevent", ""); start(el); };

  var els = Array.prototype.slice.call(doc.querySelectorAll(".map[data-points], .map[data-map]"));
  if (!els.length) return;
  els.forEach(function (el) { el.setAttribute("data-lenis-prevent", ""); });
  function fail(el) {
    el._gs = 0;
    var o = el.querySelector(".map-off");
    if (o) o.textContent = W.fail || (EN ? "The map could not be loaded." : "지도를 불러오지 못했습니다.");
  }
  function start(el) {
    if (el._gs) return;
    el._gs = 1;
    // the box's own text says the page lists the same places (for a reader without the map); drawing starts now
    var o = el.querySelector(".map-off");
    if (o) o.textContent = W.load || (EN ? "Loading the map." : "지도를 불러오는 중입니다.");
    afterLoad(function () {
      load(el).then(function () { if (!build(el)) el._gs = 0; }).catch(function () { fail(el); });
    });
  }
  if ("IntersectionObserver" in win) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting && visible(en.target)) { io.unobserve(en.target); start(en.target); } });
    }, { rootMargin: "400px 0px" });
    els.forEach(function (el) { io.observe(el); });
  } else els.forEach(start);
  doc.addEventListener("gs:showmap", function () {
    setTimeout(function () {
      els.forEach(function (el) { if (visible(el)) start(el); });
      maps.forEach(function (r) {
        listQuiet(r);
        if (!visible(r.el)) return;
        r.map.invalidateSize();
        if (r.showHome) r.showHome(false);
        else if (r.data.list) listFit(r);
        else if (r.data.all && lastRegion && lastRegion.region) applyRegion(r, lastRegion); // /map/: the chosen group stays framed
        else if (r.frame) fitVisible(r.map, r.el, r.frame, 28);
      });
    }, 30);
  });
})();
