/* 군산각 — /sun/ 군산 일출·일몰 시간 (templates/sun.html.j2, pipeline/timetables.sun_vm; operator 2026-10-31). site.js
   attaches this file when the page has [data-sun]. The HTML is complete without it: the answer is the build day written
   out (never '오늘'), every day is a table row. Here, on the visitor's own date (Asia/Seoul) when the table has it:
   - the answer line takes that day's values from its row (data-v: 시민박명 시작|일출|일몰|시민박명 끝|낮 길이) and the
     '오늘' tag ([data-sun-now], its room kept from the first paint by css/78-timetables.css — nothing moves);
   - the row is marked (.is-today, aria-current="date", a '오늘' tag in its date cell) and its month opens;
   - the arc beside the answer (wide screens) puts the sun where it is now between that day's sunrise and sunset.
   A build older than its table, or a clock before it, leaves the page exactly as built. Text goes in through
   textContent only. */
(function () {
  "use strict";
  var doc = document;
  var root = doc.querySelector("[data-sun]");
  if (!root || root.getAttribute("data-sun") === "on") return;
  var word = root.getAttribute("data-w-today") || "";
  var d, now;
  try {
    var o = {};
    new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date()).forEach(function (p) { o[p.type] = p.value; });
    d = o.year + "-" + o.month + "-" + o.day;
    now = (parseInt(o.hour, 10) % 24) * 60 + parseInt(o.minute, 10);
  } catch (e) { return; }
  var row = root.querySelector('tr[data-d="' + d + '"][data-v]');
  if (!row) return;
  root.setAttribute("data-sun", "on");
  function set(sel, v) {
    if (!v) return;
    Array.prototype.forEach.call(root.querySelectorAll(sel), function (el) { el.textContent = v; });
  }
  function mins(t) { var p = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return p ? +p[1] * 60 + +p[2] : null; }

  var ans = root.querySelector("[data-sun-ans]");
  if (ans && ans.getAttribute("data-d") !== d) {
    var v = (row.getAttribute("data-v") || "").split("|"), cells = row.children;
    set("[data-sun-lab]", cells[0].textContent + "(" + cells[1].textContent + ")");
    set("[data-sun-rise]", v[1]);
    set("[data-sun-set]", v[2]);
    set("[data-sun-day]", v[4]);
    if (v[0] && v[3]) set("[data-sun-tw]", v[0] + "–" + v[3]);
    ans.setAttribute("data-d", d);
  }
  set("[data-sun-now]", word);
  // the arc (wide screens): the sun where it is now between sunrise and sunset (at an end before or after them)
  var vv = (row.getAttribute("data-v") || "").split("|"), a = mins(vv[1]), b = mins(vv[2]);
  var dot = root.querySelector("[data-sun-dot]");
  if (dot && a != null && b != null && b > a) {
    var f = Math.max(0, Math.min(1, (now - a) / (b - a)));
    dot.setAttribute("transform", "translate(" + (160 - 136 * Math.cos(Math.PI * f)).toFixed(1) + " " +
      (150 - 124 * Math.sin(Math.PI * f)).toFixed(1) + ")");
  }

  row.classList.add("is-today");
  row.setAttribute("aria-current", "date");
  var tag = doc.createElement("span");
  tag.className = "tt-today";
  tag.textContent = word;
  row.children[0].appendChild(tag);
  var box = row.closest ? row.closest("details") : null;
  if (box && !box.open) box.open = true;
})();
