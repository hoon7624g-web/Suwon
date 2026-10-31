/* the place page's day card, 오늘의 상태 · 오늘의 바다 (templates/_today.html.j2, present.today_vm;
   operator 2026-10-31). site.js attaches this file when the page has [data-today]. The HTML is the build day and is
   complete without it; here the JSON of every day ([data-today-json]: dates, states, hours in minutes, the axis, the
   words of the page's language) moves the card to the visitor's own date (Asia/Seoul):
   - the row of date buttons starts at today; a build older than its days, or a clock before it, leaves the card
     exactly as built (absolute dates, never '오늘')
   - a button (or ←/→/Home/End in the row, roving tabindex) shows its day: date, status, the bar's segments (--a/--b on
     the JSON's axis), the line under it, sunset and the sun's place on its arc, the crowd forecast, the tide table and
     curve (aria-selected on the button, aria-labelledby on the panel)
   - on today: '오늘 · ' before the date, the '지금' mark on the bar and the tide curve, the sun where it is between
     sunrise and sunset, and one line on what that means now (opens at · time left · break · done), once a minute.
   Text goes in through textContent only. Nothing here touches the first screen (the card sits below it). */
(function () {
  "use strict";
  var doc = document;
  var card = doc.querySelector("[data-today]");
  if (!card || card.getAttribute("data-today") === "on") return;
  var data;
  try { data = JSON.parse(card.querySelector("[data-today-json]").textContent); } catch (e) { return; }
  if (!data || !data.days || !data.days.length) return;
  var days = data.days, W = data.w || {}, ax = data.ax;

  function q(s) { return card.querySelector(s); }
  function qa(s, el) { return Array.prototype.slice.call((el || card).querySelectorAll(s)); }
  function fill(t, o) { return String(t || "").replace(/\{(\w+)\}/g, function (m, k) { return o[k] == null ? m : o[k]; }); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function hm(m) { var t = pad(Math.floor(m / 60) % 24) + ":" + pad(m % 60); return m >= 1440 ? fill(data.nd, { t: t }) : t; }
  function mins(t) { var p = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return p ? +p[1] * 60 + +p[2] : null; }
  function dur(m) {
    var h = Math.floor(m / 60), r = m % 60;
    return h && r ? fill(W.hm, { h: h, m: r }) : h ? fill(W.h, { h: h }) : fill(W.m, { m: r });
  }
  function seoul() {
    try {
      var o = {};
      new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date())
        .forEach(function (p) { o[p.type] = p.value; });
      return { d: o.year + "-" + o.month + "-" + o.day, m: (parseInt(o.hour, 10) % 24) * 60 + parseInt(o.minute, 10) };
    } catch (e) { return null; }
  }
  var now = seoul();
  if (!now) return;
  var first = -1;
  for (var i = 0; i < days.length; i++) if (days[i].d === now.d) { first = i; break; }
  if (first < 0) return;   // the build is older than its days (or the clock is before it): the HTML stays as built
  card.setAttribute("data-today", "on");

  var tabs = qa("[role=tab][data-i]"), panel = q("[role=tabpanel]"), list = q("[role=tablist]");
  var track = q("[data-t-bar]"), nowMark = q("[data-t-now]"), liveEl = q("[data-t-live]");
  var setEl = q("[data-t-set]"), riseEl = q("[data-t-rise]"), sunP = q("[data-t-sunp]");
  var crEl = q("[data-t-cr]"), crM = q("[data-t-crm]");
  var tBody = q("[data-t-tide]"), cLine = q("[data-t-cl]"), cFill = q("[data-t-cf]"), cNow = q("[data-t-cn]");
  var cur = -1;
  function text(sel, v) { qa(sel).forEach(function (el) { el.textContent = v || ""; }); }
  function frac(m) { return Math.max(0, Math.min(1, (m - ax[0]) / (ax[1] - ax[0]))); }

  // the row starts at today: each button takes its day (date, state, its name for assistive technology)
  tabs.forEach(function (b, k) {
    var x = days[first + k];
    if (!x) { b.hidden = true; return; }
    b.setAttribute("data-i", String(first + k));
    b.setAttribute("data-st", x.st);
    b.querySelector(".td-dw").textContent = x.dw;
    b.querySelector(".td-dn").textContent = x.dn;
    b.querySelector(".vh").textContent = (k === 0 ? W.today + " · " : "") + x.l + (x.s ? " " + x.s : "");
  });

  function bar(x, today) {
    if (!track || !ax) return;
    var segs = qa(".td-seg", track), g = x.g || [];
    while (segs.length < g.length) {
      var s = doc.createElement("i");
      s.className = "td-seg";
      track.insertBefore(s, nowMark);
      segs.push(s);
    }
    segs.forEach(function (s, k) {
      if (k >= g.length) { track.removeChild(s); return; }
      s.style.setProperty("--a", frac(g[k][0]).toFixed(4));
      s.style.setProperty("--b", frac(g[k][1]).toFixed(4));
    });
    if (nowMark) {
      var on = today && now.m >= ax[0] && now.m <= ax[1];
      nowMark.hidden = !on;
      if (on) nowMark.style.setProperty("--n", frac(now.m).toFixed(4));
    }
  }
  function live(x, today) {
    if (!liveEl) return;
    var t = "", r = x.r || [], m = now.m;
    if (today && r.length && (x.st === "open" || x.st === "hours")) {
      var at = function (list) { return list.filter(function (a) { return m >= a[0] && m < a[1]; })[0]; };
      var inR = at(r), inK = at(x.k || []), next = r.filter(function (a) { return a[0] > m; })[0];
      if (inK) t = W.brk + " · " + fill(W.before, { t: hm(inK[1]) });
      else if (inR) t = fill(W.left, { t: hm(inR[1]), d: dur(inR[1] - m) });
      else if (next) t = fill(W.before, { t: hm(next[0]) });
      else t = W.after;
      t = fill(W.now, { t: hm(m) }) + " · " + t;
    }
    liveEl.textContent = t;
  }
  function sun(x, today) {
    if (!setEl) return;
    var s = x.sun;
    setEl.textContent = s ? s[1] : data.none;
    if (riseEl) riseEl.textContent = s && s[0] ? fill(data.sunrise, { t: s[0] }) : "";
    var f = 1, a = s ? mins(s[0]) : null, b = s ? mins(s[1]) : null;
    if (today && a != null && b != null && b > a) f = Math.max(0, Math.min(1, (now.m - a) / (b - a)));
    if (sunP) sunP.setAttribute("transform", "translate(" + (80 - 70 * Math.cos(Math.PI * f)).toFixed(1) + " " +
      (64 - 56 * Math.sin(Math.PI * f)).toFixed(1) + ")");
  }
  function crowd(x) {
    if (!crEl) return;
    var c = x.cr;
    crEl.textContent = c ? c[0] + (c[2] ? " · " + c[2] : "") : data.none;
    if (crM) crM.style.setProperty("--v", c ? Math.max(0, Math.min(1, parseFloat(c[0]) / 100)).toFixed(3) : "0");
  }
  function tide(x, today) {
    if (!tBody) return;
    while (tBody.firstChild) tBody.removeChild(tBody.firstChild);
    (x.td || []).forEach(function (p) {
      var tr = doc.createElement("tr");
      tr.className = "is-" + p[1];
      [p[2], p[0], p[3]].forEach(function (v, k) {
        var td = doc.createElement("td");
        td.textContent = v;
        if (k) td.className = "tn";
        tr.appendChild(td);
      });
      tBody.appendChild(tr);
    });
    var c = x.tc || ["", ""];
    if (cLine) cLine.setAttribute("d", c[0] || "");
    if (cFill) cFill.setAttribute("d", c[1] || "");
    if (cNow) {
      if (today) {
        var cx = (now.m / 1440 * 330).toFixed(1);
        cNow.setAttribute("x1", cx);
        cNow.setAttribute("x2", cx);
        cNow.removeAttribute("visibility");
      } else cNow.setAttribute("visibility", "hidden");
    }
  }
  function show(idx, focus) {
    var x = days[idx];
    if (!x) return;
    cur = idx;
    var today = idx === first;
    tabs.forEach(function (b) {
      var on = +b.getAttribute("data-i") === idx;
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
      if (on) {
        if (panel) panel.setAttribute("aria-labelledby", b.id);
        if (focus) b.focus();
      }
    });
    card.setAttribute("data-st", x.st);
    text("[data-t-lab]", (today ? W.today + " · " : "") + x.l);
    text("[data-t-h]", x.h);
    text("[data-t-sub]", x.u);
    bar(x, today);
    live(x, today);
    sun(x, today);
    crowd(x);
    tide(x, today);
  }

  tabs.forEach(function (b) {
    b.addEventListener("click", function () { show(+b.getAttribute("data-i")); });
  });
  if (list) list.addEventListener("keydown", function (ev) {
    var vis = tabs.filter(function (b) { return !b.hidden; }), at = vis.indexOf(doc.activeElement);
    if (at < 0) return;
    var to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: vis.length - 1 }[ev.key];
    if (to == null) return;
    ev.preventDefault();
    show(+vis[(to + vis.length) % vis.length].getAttribute("data-i"), true);
  });
  show(first);
  // the clock moves: today's marks and line once a minute (a new date leaves the row as it is until a reload)
  setInterval(function () {
    var n = seoul();
    if (!n || n.d !== now.d) return;
    now = n;
    if (cur === first) {
      var x = days[first];
      bar(x, true);
      live(x, true);
      sun(x, true);
      tide(x, true);
    }
  }, 60000);
})();
