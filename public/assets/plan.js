/* Travel site — the AI course planner (/plan/, the first city's operator 2026-10-17), attached by site.js for [data-plan].

   FORM      the cards are real radio / check boxes; the counters (어른, 그중 65세 이상, 어린이·유아) add an age select per
             child; where the trip starts and ends (a station or a terminal, by name); the day's start and end every
             half hour (HH:MM, three hours apart by the minute — the server's own bound); the date starts on the coming
             Saturday (never before today); 좋아하는 것 keeps at most 4 ticked; a summary line says what will be asked.
             Submit → POST /api/plan/ {conditions}. A reload puts the conditions of the plan shown back in the form.
             The assistant hands a reader over with conditions in the address (/plan/?date=…&days=…&move=…): on the
             form's defaults (a plan the tab kept is not shown under them), each value only when it is one of the
             form's own choices, who comes and how many as the form's buttons keep them, the date empty when none came
             (the button asks for one: '날짜를 골라 주세요.'); the page opens at the form under a line saying so and
             that what the assistant could not read is the form's default ('대화에서 읽은 조건만 채웠어요 …', its words
             for a date carried or none; role=status); nothing is sent until the reader presses the button. On phones
             only the button's bar stays at the screen's foot, and the assistant's round button steps aside while the
             button is on screen.
   WORKING   the steps the server reports (SSE status {step}) light up in order; '멈추기' aborts the request.
   RESULT    drawn from the server's checked plan (chatbot/planner.js finish, v 2) and the site's own place data
             (/plan/places.json, fetched once). The code's statements come first (review 2026-10-17: a '6/6 확인' badge
             stood above two unconfirmed places): the plan's status ('코스 완성 · 가기 전 확인 N가지' — N the status
             rows not marked ✓, operator 2026-10-23 — or '완성된 코스예요' with none; 조건을 다 맞추지 못함), regular
             hours, that day's own checks, the reader's needs at each stop and the fees each as its own
             state; then the course at a glance, the day clock, the needs table, per day the stops (TourAPI photo or 3D
             picture, the model's one-line reason marked AI, the facts — a place whose inside is not open to visitors
             '외관 감상 · 내부 관람 불가' with its sources —, what to check), the legs (straight line, the
             margin the plan keeps — never a travel time — and a Kakao Map link), the start and end hubs, a numbered map,
             the fees person by person, everything to check; copy, share, print, save as a text file; after an edit,
             what changed. Charts sit in <details>, open from 900px, closed on phones. Outside evaluation 2026-10-18:
             the status panel says how complete the day is (meals, likings, empty time, what an edit kept — planner
             finish 'complete'), an 'unmet' plan offers one-tap fixes for what is left (finish 'todo', sent as an
             edit), a distance total only when every leg has one, and a draft still unmet is marked so in its text.
             Operator 2026-10-18 ('이런 거 좀 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게'): what holds for any plan
             (planned margins, hubs, a stay's booking — finish 'aware') and what the data does not say (a place's closed
             days, a fee — finish 'checks') never make it a draft and never sit on top as '확인할 것': they are an
             information mark (i) in the status rows and one closed box, '가기 전에 알아 둘 것'. What the site put right
             itself (finish 'fixed') is not listed. Conditions no plan can meet come back before any model call
             (HTTP 422 / SSE error 'conditions' with problems and fixes): a box right above the button says why and
             offers the fixes as buttons that set the form; a plan the site built itself when the AI gave none (one
             'fixed' line starting '일정 전체:') says so above the course; a change that cannot be finished keeps the
             plan ('edit_failed').
   FIRST     (operator 2026-10-19: 20–40 s of waiting) a new plan's SSE {type: 'early'} is the course the site built from
             its data at once: drawn under a status line '사이트 자료로 먼저 짠 코스예요 · AI가 조건에 맞게 다듬는 중'
             (role=status, a small progress mark, '멈추기'), the working view gone. The AI's plan replaces it in place
             when the reader has not touched the result (no scroll past the status panel, no tap or key inside it) —
             'AI가 다듬은 코스로 바꿨어요' and what changed (diffPlans) —, else nothing moves under them: the line offers
             'AI가 다듬은 코스 보기' (and a fixed toast when the line is out of sight). After a switch '먼저 보여 드린 코스
             보기' brings the first back; both stay in this tab, which keeps (and links) the one on screen. Cancel, an
             error or a timeout keep the first course, and so does a final plan that is the same course the site built
             (the AI gave nothing).
   SHARE     '링크 복사' puts the plan on screen in the address fragment: /plan/#p=z.<base64url of deflate-raw JSON>.<sig>
             (j. and plain JSON where CompressionStream cannot deflate) — the compact form of chatbot/plan_share.js, the
             conditions without the reader's note, the server's signature of the plan. Nothing is stored on a server.
             An edit sends the plan's compact form without its stops and its signature (base), so the server keeps
             its reasons. Opening such a link (bounded: 16,000 characters, 32 KB inflated, as the server): the
             fragment leaves the address (plan.html.j2, before any tag; a reload shows this tab's state), POST
             /api/plan/ {view: {compact, sig}} reads it against today's data (no model call), the plan is drawn under
             '공유받은 코스예요 · 오늘 자료로 다시 검사했어요' with '이 조건으로 내 코스 만들기'; a signature that does
             not check out drops the AI's words and says so; a past date says so, a trip under way too; what today's
             data flags is a neutral notice — '공유된 뒤 자료가 바뀐 곳' on a signed link, '오늘 자료와 맞지 않는 곳' on
             one not signed.
   STOPS     (operator 2026-10-23, mockup A) under each stop's facts 빼기 · 다른 곳으로 · 고정 on the reader's own plan:
             the first two an edit with an act, made by the code alone (planner actOn) and drawn in place; 고정 the
             page's own, its pins sent with every later edit (stopActs, sendAct).
   STATE     sessionStorage 'gs-plan' (this tab only): the conditions, the plan on screen and its signature, the last
             change, the course sent first and the AI's (early, final, phase), a shared plan's state, the pinned stops
             and the places each slot was swapped away from (pins, tried — never in a link). Nothing is stored
             anywhere else. GA4 (window.siteTrack): plan_submit, plan_done, plan_edit, plan_error, plan_export,
             plan_fix, plan_conditions, plan_early, plan_swap, plan_share, plan_shared_open with fixed parameters only
             (days, move, with, status, code, how, kind, fields, auto, sig) — never the reader's words. */
(function () {
  "use strict";
  var doc = document, win = window;
  var root = doc.querySelector("[data-plan]");
  if (!root) return;
  var form = root.querySelector("[data-plan-form]"), work = root.querySelector("[data-plan-work]");
  var result = root.querySelector("[data-plan-result]"), sumEl = root.querySelector("[data-plan-sum]");
  var formErr = root.querySelector("[data-plan-formerr]"), live = root.querySelector("[data-plan-live]");
  var API = root.getAttribute("data-api"), PLACES = root.getAttribute("data-places");
  var KEY = "gs-plan", WEEK = "일월화수목금토", MAX_PREFS = 4;
  var BASE = (doc.currentScript && doc.currentScript.src || "").replace(/[^/]*$/, "") || "/assets/";
  var places = null, placesLoading = null, ctrl = null, state = null;
  var barEl = null, toastEl = null, touched = false, linkCache = null;
  // the page is going (a reload, a link followed): a request cut by it is no failure of the AI's, and nothing is said or
  // counted (round-6 verifier: a reload while refining stored 'kept' and sent plan_error)
  var leaving = false;
  win.addEventListener("pagehide", function () {
    leaving = true;
    // where the reader was, for a reload of this tab's plan (the page puts it back once the plan is drawn: the browser's
    // own restoring landed on the footer of a page not yet drawn, and the course then pushed it out — round-6 verifier)
    try { win.sessionStorage.setItem(KEY + "-y", String(Math.round(win.scrollY || 0))); } catch (e) { /* private mode */ }
  });
  win.addEventListener("beforeunload", function () { leaving = true; });
  win.addEventListener("pageshow", function () { leaving = false; });
  try { if ("scrollRestoration" in win.history) win.history.scrollRestoration = "manual"; } catch (e) { /* the browser's own */ }
  // the city's hubs (site.json plan.hubs) as the form names them; the site's address and name for the text a plan is
  // copied, shared and saved as (templates/plan.html.j2 data-site, data-site-name)
  var HUBS = {};
  if (form.elements.from) Array.prototype.forEach.call(form.elements.from.options, function (o) { if (o.value) HUBS[o.value] = o.textContent; });
  var SITE = (root.getAttribute("data-site") || "").replace(/\/+$/, ""), NAME = root.getAttribute("data-site-name") || "";
  var TICKETS = root.hasAttribute("data-tickets");   // the site keeps combined tickets' tables (data/<region>/tickets.json)
  var LABEL = {
    move: { car: "자가용", transit: "대중교통·걷기" },
    with: { solo: "혼자", couple: "연인·친구", kids: "아이와 가족", parents: "부모님과" },
    role: { visit: "둘러보기", meal: "식사", cafe: "카페", stay: "숙소" },
    day: { open: "그날 운영", closed: "그날 휴무", unknown: "그날 운영 확인 필요" },
    mode: { car: "자동차", walk: "걷기", traffic: "대중교통" },
  };

  function track(name, params) { try { if (win.siteTrack) win.siteTrack(name, params || {}); } catch (e) { /* no analytics */ } }
  function h(tag, attrs, kids) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) el.append(c); });
    return el;
  }
  function pic(id) {
    var t = doc.getElementById("trp-pics"), s = t && t.content.querySelector('[data-id="' + id + '"]');
    return s ? s.firstElementChild.cloneNode(true) : h("span", { class: "pic pic-tmp" });
  }
  function mascot(id) {
    var t = doc.getElementById("trp-mascots"), s = t && t.content.querySelector('[data-id="' + id + '"]');
    return s ? s.firstElementChild.cloneNode(true) : null;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function dayName(s) { var d = new Date(s + "T12:00:00"); return (d.getMonth() + 1) + "월 " + d.getDate() + "일(" + WEEK[d.getDay()] + ")"; }
  function won(n) { return n.toLocaleString("ko-KR") + "원"; }
  function dist(m) { return m === null || m === undefined ? "" : m >= 1000 ? "직선 " + (m / 1000).toFixed(1) + "km" : "직선 " + m + "m"; }
  // the tab keeps the plan (sessionStorage). When it cannot — its storage full, a private window (UX05 2026-10-24) —
  // the conditions alone are kept, marked lost, so a reload says why the course is gone; the reader is told at once,
  // with the ways that keep it (링크 복사, 파일로 저장)
  var saveWarned = null;
  function save() {
    try {
      win.sessionStorage.setItem(KEY, JSON.stringify(state));
      var n = root.querySelector(".trp-save-note");
      if (n) n.remove();
      return true;
    } catch (e) {
      try { win.sessionStorage.setItem(KEY, JSON.stringify({ conditions: state && state.conditions, plan: null, lost: 1 })); } catch (x) { /* nothing kept */ }
      if (state && state.plan && saveWarned !== state.plan) { saveWarned = state.plan; saveNote(); }
      return false;
    }
  }
  function saveNote() {
    var old = root.querySelector(".trp-save-note");
    if (old) old.remove();
    result.before(h("p", { class: "wrap trp-save-note", role: "status", text: "이 탭에 코스를 보관하지 못했어요(브라우저 저장 공간이 모자라거나 사생활 보호 모드) — "
      + "새로고침하거나 다른 페이지에 다녀오면 사라질 수 있어요. 코스 아래 '링크 복사'나 '파일로 저장'으로 남겨 두세요." }));
  }
  function load() { try { return JSON.parse(win.sessionStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function getPlaces() {
    if (places) return Promise.resolve(places);
    if (!placesLoading) {
      placesLoading = fetch(PLACES).then(function (r) { if (!r.ok) throw new Error("places"); return r.json(); })
        .then(function (p) { places = p; return p; }).catch(function () { placesLoading = null; return {}; });
    }
    return placesLoading;
  }

  // ------------------------------------------------------------ the form
  var dateIn = form.querySelector("[data-plan-date]"), today = new Date();
  dateIn.min = iso(today);
  var last = new Date(today.getTime() + 180 * 86400000);
  dateIn.max = iso(last);
  var sat = new Date(today.getTime() + ((6 - today.getDay() + 7) % 7 || 7) * 86400000);
  dateIn.value = iso(sat);
  var counts = { adults: 2, seniors: 0, kids: 0 }, ages = [];
  function setCount(key, n) {
    counts[key] = n;
    form.querySelector('[data-count="' + key + '"] [data-count-value]').textContent = String(n);
  }
  function drawAges() {
    var box = form.querySelector("[data-ages]");
    box.textContent = "";
    ages.forEach(function (a, i) {
      var sel = h("select", { "aria-label": (i + 1) + "번째 아이 나이" });
      for (var y = 0; y <= 17; y += 1) sel.append(h("option", { value: String(y), text: y === 0 ? "1살 미만" : y + "살", selected: y === a }));
      sel.addEventListener("change", function () { ages[i] = +sel.value; summary(); });
      box.append(h("label", { class: "trp-age" }, [h("span", { text: "아이 " + (i + 1) }), sel]));
    });
  }
  form.querySelectorAll("[data-count]").forEach(function (c) {
    var key = c.getAttribute("data-count"), out = c.querySelector("[data-count-value]");
    c.addEventListener("click", function (e) {
      var b = e.target.closest("[data-step]");
      if (!b) return;
      var n = counts[key] + +b.getAttribute("data-step");
      var max = key === "adults" ? 10 : key === "seniors" ? counts.adults : 6;
      if (n < 0 || n > max || (key === "adults" ? n + counts.kids : key === "kids" ? counts.adults + n : 1) < 1) return;
      counts[key] = n;
      out.textContent = String(n);
      if (key === "adults" && counts.seniors > n) setCount("seniors", n);
      if (key === "kids") {
        while (ages.length < n) ages.push(7);
        ages.length = n;
        drawAges();
        if (n && !form.querySelector('input[name="with"][value="kids"]').checked) form.querySelector('input[name="with"][value="kids"]').checked = true;
      }
      summary();
    });
  });
  form.querySelector('input[name="with"][value="kids"]').addEventListener("change", function () {
    if (!counts.kids) form.querySelector('[data-count="kids"] [data-step="1"]').click();
  });
  form.querySelector('input[name="with"][value="solo"]').addEventListener("change", function () {
    if (counts.adults > 1) { setCount("adults", 1); if (counts.seniors > 1) setCount("seniors", 1); summary(); }
  });
  form.addEventListener("change", function (e) {
    if (e.target.name === "prefs") {
      var on = form.querySelectorAll('input[name="prefs"]:checked');
      if (on.length > MAX_PREFS) {
        e.target.checked = false;
        sumEl.textContent = "좋아하는 것은 " + MAX_PREFS + "개까지 고를 수 있어요.";
        return;
      }
    }
    summary();
  });
  form.querySelectorAll("[data-budget]").forEach(function (b) {
    b.addEventListener("click", function () { form.budget.value = b.getAttribute("data-budget"); summary(); });
  });
  form.addEventListener("focusin", function () { getPlaces(); }, { once: true });

  function picked(name) { return Array.prototype.map.call(form.querySelectorAll('input[name="' + name + '"]:checked'), function (i) { return i.value; }); }
  function conditions() {
    var budget = form.budget.value === "" ? null : Math.max(0, Math.min(1000000, Math.round(+form.budget.value)));
    return { date: dateIn.value, days: +picked("days")[0], start: form.start.value, end: form.end.value,
      from: form.elements.from ? form.elements.from.value || "" : "", to: form.elements.to ? form.elements.to.value || "" : "",
      move: picked("move")[0], with: picked("with")[0], adults: counts.adults, seniors: counts.seniors, kids: ages.slice(),
      prefs: picked("prefs"), needs: picked("needs"), budget: isNaN(budget) ? null : budget,
      note: form.note.value.trim() || undefined };
  }
  // the form shows the conditions of the plan on screen after a reload (review 2026-10-17: the result came back, the
  // form went back to its defaults)
  function setForm(c) {
    if (c.date >= dateIn.min && c.date <= dateIn.max) dateIn.value = c.date;
    else if (c.date === "") dateIn.value = "";   // a hand-over that carried no date (fromAddress): still none after a reload
    [["start", c.start], ["end", c.end], ["from", c.from || ""], ["to", c.to || ""]].forEach(function (x) {
      var el = form.elements[x[0]];
      if (el && Array.prototype.some.call(el.options, function (o) { return o.value === x[1]; })) el.value = x[1];
    });
    [["days", String(c.days)], ["move", c.move], ["with", c.with]].forEach(function (x) {
      var i = form.querySelector('input[name="' + x[0] + '"][value="' + x[1] + '"]');
      if (i) i.checked = true;
    });
    ["prefs", "needs"].forEach(function (name) {
      form.querySelectorAll('input[name="' + name + '"]').forEach(function (i) { i.checked = (c[name] || []).indexOf(i.value) >= 0; });
    });
    setCount("adults", c.adults);
    setCount("seniors", Math.min(c.seniors || 0, c.adults));
    ages = (c.kids || []).slice();
    setCount("kids", ages.length);
    drawAges();
    form.budget.value = c.budget === null || c.budget === undefined ? "" : String(c.budget);
    form.note.value = c.note || "";
    summary();
  }
  function label(name, value) {
    var i = form.querySelector('input[name="' + name + '"][value="' + value + '"]');
    return i ? i.closest(".trp-card").querySelector("b").textContent : value;
  }
  function describe(c) {
    var who = "어른 " + c.adults + (c.seniors ? "(65세 이상 " + c.seniors + ")" : "")
      + (c.kids.length ? ", 아이 " + c.kids.map(function (a) { return a ? a + "살" : "1살 미만"; }).join("·") : "");
    var bits = [c.date ? dayName(c.date) : "날짜 미정", label("days", c.days), LABEL.move[c.move], LABEL.with[c.with] + "(" + who + ")"];
    if (c.from || c.to) bits.push((c.from ? HUBS[c.from] + " " + c.start + " 출발" : "") + (c.from && c.to ? " → " : "") + (c.to ? HUBS[c.to] + " " + c.end + " 도착" : ""));
    if (c.prefs.length) bits.push(c.prefs.map(function (p) { return label("prefs", p); }).join("·"));
    if (c.needs.length) bits.push(c.needs.map(function (p) { return label("needs", p); }).join("·"));
    if (c.budget !== null) bits.push("입장료 " + won(c.budget) + " 이내");
    return bits.join(" · ");
  }
  // the needs picked, each with the count of places to visit the site's data says fit it (UI-A01, 2026-10-24: the
  // build's data-need-note) and once what the count means — a place the data says nothing of is not one the need does
  // not fit
  // (drawn again only when the needs picked change: the box is a live region, and the form's other changes — a date, a
  // count — would have it read the same lines out again)
  var needBox = form.querySelector("[data-need-notes]"), needKey = null;
  function needNotes() {
    if (!needBox) return;
    var on = Array.prototype.filter.call(form.querySelectorAll('input[name="needs"]:checked'), function (i) { return i.getAttribute("data-need-note"); });
    var key = on.map(function (i) { return i.value; }).join(",");
    if (key === needKey) return;
    needKey = key;
    needBox.textContent = "";
    on.forEach(function (i) { needBox.append(h("p", { text: i.getAttribute("data-need-note") })); });
    if (on.some(function (i) { return i.hasAttribute("data-need-n"); })) needBox.append(h("p", { class: "trp-need-tail", text: needBox.getAttribute("data-tail") || "" }));
    needBox.hidden = !on.length;
  }
  function summary() { sumEl.textContent = describe(conditions()); needNotes(); if (!applying) hideProblems(); }
  summary();

  // conditions in the address (/plan/?date=2026-10-24&days=2&start=10:30&move=transit&with=kids&adults=2&kids=8,5&
  // needs=rain&prefs=history,food&from=station&to=station&note=…): the assistant's hand-over, put on the form's
  // defaults. Each value is checked against the form's own choices (a radio or check box with that value, a select's
  // option, the date's range, the counters' bounds); an unknown value is left out, the form's default stays. Then the
  // rules the form's own buttons keep between who comes and how many (people()), so the form never shows what it
  // could not. Returns whether anything was put in. A hand-over with no date the form can take leaves the date empty
  // (review 2026-10-22: '월요일' said in the conversation — the assistant never guesses a day — came over as the coming
  // Saturday): the reader picks it, the line above the form asks for it, and the button will not go without it.
  function fromAddress() {
    var q;
    try { q = new URLSearchParams(win.location.search); } catch (e) { return false; }
    var any = false, dated = false;
    var get = function (k) { var v = q.get(k); return v === null ? "" : v.trim(); };
    var list = function (k) { return get(k).split(",").map(function (x) { return x.trim(); }).filter(Boolean); };
    var d = get("date");
    if (/^\d{4}-\d{2}-\d{2}$/.test(d) && d >= dateIn.min && d <= dateIn.max) { dateIn.value = d; any = dated = true; }
    var box = function (name, v) {   // the radio or check box of that value, or null (only plain values are looked up)
      return /^[a-z0-9]+$/.test(v) ? form.querySelector('input[name="' + name + '"][value="' + v + '"]') : null;
    };
    ["days", "move", "with"].forEach(function (name) {
      var i = box(name, get(name));
      if (i) { i.checked = true; any = true; }
    });
    ["start", "end", "from", "to"].forEach(function (name) {
      var v = get(name), el = form.elements[name];
      if (v && el && Array.prototype.some.call(el.options, function (o) { return o.value === v; })) { el.value = v; any = true; }
    });
    var count = function (k, max) { var v = get(k); return /^\d{1,2}$/.test(v) && +v <= max ? +v : null; };
    var adults = count("adults", 10), seniors = count("seniors", 10);
    var kids = list("kids");
    kids = kids.length && kids.length <= 6 && kids.every(function (x) { return /^\d{1,2}$/.test(x) && +x <= 17; }) ? kids.map(Number) : null;
    if ((adults === null ? counts.adults : adults) + (kids ? kids.length : counts.kids) >= 1) {
      if (adults !== null) { setCount("adults", adults); any = true; }
      if (kids) { ages = kids; setCount("kids", kids.length); drawAges(); any = true; }
    }
    if (seniors !== null) { setCount("seniors", Math.min(seniors, counts.adults)); any = true; }
    else if (counts.seniors > counts.adults) setCount("seniors", counts.adults);
    ["prefs", "needs"].forEach(function (name) {
      var want = list(name).filter(function (v) { return box(name, v); });
      if (name === "prefs") want = want.slice(0, MAX_PREFS);
      if (!want.length) return;
      form.querySelectorAll('input[name="' + name + '"]').forEach(function (i) { i.checked = want.indexOf(i.value) >= 0; });
      any = true;
    });
    var note = get("note");
    if (note) { form.note.value = Array.from(note).slice(0, +form.note.getAttribute("maxlength") || 200).join(""); any = true; }
    if (any) { people(); if (!dated) dateIn.value = ""; summary(); }
    return any;
  }
  // who comes and how many, as the form's buttons keep them: a child makes it 아이와 가족 (the child counter), 아이와
  // 가족 has a child (the card adds one of 7), 혼자 is one adult (the card), 65세 이상 are among the adults
  function people() {
    var w = picked("with")[0];
    if (counts.kids && w !== "kids") { form.querySelector('input[name="with"][value="kids"]').checked = true; w = "kids"; }
    if (w === "kids" && !counts.kids) { ages = [7]; setCount("kids", 1); drawAges(); }
    if (w === "solo" && counts.adults !== 1) setCount("adults", 1);
    if (counts.seniors > counts.adults) setCount("seniors", counts.adults);
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var c = conditions();
    var err = "", noDay = !c.date || c.date < dateIn.min || c.date > dateIn.max;
    if (!c.date) err = "날짜를 골라 주세요.";   // a hand-over with no date leaves it empty (fromAddress)
    else if (noDay) err = "여행 날짜는 오늘부터 180일 안에서 골라 주세요.";
    else if (mins(c.end) - mins(c.start) < 180) err = "하루 일정은 3시간 이상으로 골라 주세요.";   // by the minute: 12:30–15:00 is not three hours
    formErr.hidden = !err;
    formErr.textContent = err;
    if (noDay) {   // to the date, as '이 조건으로 내 코스 만들기' does (ownCourse)
      form.scrollIntoView({ behavior: "smooth", block: "start" });
      dateIn.focus({ preventScroll: true });
    }
    if (err) return;
    track("plan_submit", { days: c.days, move: c.move, with: c.with });
    hideProblems();
    ask({ conditions: c }, c, false);
  });
  // the line under the button goes once the reader changes a condition, as the conditions box does (k4b review:
  // '날짜를 골라 주세요.' stayed after a date was picked, and on phones it held the button's bar over 15% of the
  // screen, CLAUDE.md 7); the button says it again if it still holds
  form.addEventListener("change", function () {
    if (!formErr.hidden) { formErr.hidden = true; formErr.textContent = ""; }
  });
  // the assistant's round button steps aside while the button is on screen (plan.css html.trp-go-on; review
  // 2026-10-22: on phones it covered the right end of the bar at the screen's foot), as on the homes while their
  // question box is (site.js html.ask-out); without IntersectionObserver it stays
  if ("IntersectionObserver" in win) {
    new IntersectionObserver(function (es) {
      doc.documentElement.classList.toggle("trp-go-on", es[es.length - 1].isIntersecting);
    }).observe(form.querySelector(".trp-submit"));
  }

  // ------------------------------------------------------------ asking the server
  var STEPS = ["search", "read", "check", "submit", "fix"];
  function setStep(step) {
    var at = STEPS.indexOf(step === "fees" ? "submit" : step);
    work.querySelectorAll("[data-step]").forEach(function (li) {
      var i = STEPS.indexOf(li.getAttribute("data-step"));
      li.classList.toggle("on", i === at);
      li.classList.toggle("done", i < at);
      if (li.getAttribute("data-step") === "fix") li.hidden = step !== "fix";
    });
  }
  function busy(on) {
    // (the focus inside the working view, or nowhere, when it goes: it moves to what is on screen in its place —
    // UX04 2026-10-24: after a cancel by keyboard document.activeElement was BODY)
    var lost = !on && !work.hidden && (work.contains(doc.activeElement) || doc.activeElement === doc.body || !doc.activeElement);
    work.hidden = !on;
    form.querySelector(".trp-submit").disabled = on;
    if (on) {
      setStep("search");
      stepSaid = "";
      live.textContent = "";
      work.scrollIntoView({ block: "start", behavior: "smooth" });
      work.querySelector("h2").focus({ preventScroll: true });
    } else if (lost) {
      var to = !result.hidden && result.querySelector("#h-result") || form.querySelector(".trp-submit");
      if (to) to.focus({ preventScroll: true });
    }
  }
  // the step the server last said (its 'status' events) and the seconds gone — never words of its own about how far it
  // is (UX04 2026-10-24: '거의 다 됐어요' from 40 seconds on whatever the server had said)
  var stepSaid = "";
  function progress(sec, edit) {
    var li = stepSaid && work.querySelector('[data-step="' + (stepSaid === "fees" ? "submit" : stepSaid) + '"]');
    return sec + "초째 " + (edit ? "고치고" : "만들고") + " 있어요" + (li ? " · 지금: " + li.textContent : "");
  }
  var t0 = 0, tick = null, LIMIT_S = 70;   // the page gives up after 70 s (the server's own limit is 55 s)
  // opts (a stop's own button — stopActs): quiet — no working view, the course stays where the reader is; done(ev) —
  // in place of drawing the result from its top
  function ask(body, c, edit, opts) {
    opts = opts || {};
    if (ctrl) ctrl.abort();
    // a course still being refined when the reader asks for something else: it stays as it is
    if (state && state.phase === "wait") { state.phase = "stopped"; save(); syncBar(); }
    hideToast();
    ctrl = new AbortController();
    var mine = ctrl;
    if (!opts.quiet) busy(true);
    if (edit) result.classList.add("trp-acting");   // a stop's own buttons wait for this change (actIdle)
    t0 = Date.now();
    clearInterval(tick);
    tick = setInterval(function () {
      var sec = Math.round((Date.now() - t0) / 1000);
      live.textContent = progress(sec, edit);
      if (sec >= LIMIT_S && mine === ctrl) { mine.late = true; mine.abort(); }
    }, 1000);
    getPlaces();
    fetch(API, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: mine.signal })
      .then(function (res) {
        if (!res.ok || !res.body) {
          return res.json().catch(function () { return {}; }).then(function (j) { throw { code: j.code || "error", message: j.message, problems: j.problems }; });
        }
        var reader = res.body.getReader(), dec = new TextDecoder(), buf = "", done = null;
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) { if (!done) throw { code: "cut" }; return done; }
            buf += dec.decode(r.value, { stream: true });
            var parts = buf.split("\n\n");
            buf = parts.pop();
            parts.forEach(function (p) {
              if (p.indexOf("data: ") !== 0) return;
              var ev;
              try { ev = JSON.parse(p.slice(6)); } catch (x) { return; }
              if (ev.type === "status") { setStep(ev.step); if (mine === ctrl) stepSaid = String(ev.step || ""); }
              else if (ev.type === "early") { if (!edit) early(ev, mine, c); }
              else if (ev.type === "plan") done = ev;
              else if (ev.type === "error") throw { code: ev.code, message: ev.message, problems: ev.problems };
            });
            return pump();
          });
        }
        return pump();
      })
      .then(function (ev) {
        if (mine !== ctrl) return;
        var plan = ev && ev.plan;
        if (!fits(plan)) throw { code: "error" };
        if (mine.early && state && state.early) return arrive(ev, c);
        // after an edit: what changed against the plan it was made from (review 2026-10-17: a café added, the fees
        // and the access facts changed unasked)
        var diff = edit && state && fits(state.plan) ? diffPlans(state.plan, plan) : null;
        var had = edit && state ? state : null;
        state = { conditions: c, plan: plan, sig: ev.sig || null, diff: diff };
        if (had) carry(had, state, body.act, ev.act);
        save();
        var done = { days: c.days, flags: (plan.flags || []).length, status: plan.status, code: codeBuilt(plan) ? 1 : 0 };
        if (body.act) done.kind = body.act.op;   // (a stop's own button: which one)
        track(edit ? "plan_edit" : "plan_done", done);
        return getPlaces().then(function () { if (opts.done) opts.done(ev); else show(true); });
      })
      .catch(function (err) {
        if (mine !== ctrl || leaving) return;
        // the course sent first stays on screen whatever happens to the AI's (cancelled, an error, too long): never a
        // failure page for a new plan. A stream or a connection cut (the network, the stream's end with no plan) is
        // 'cut' — the AI did not fail — and the server's own error or the time running out 'kept'
        if (mine.early && state && state.early) {
          var stopped = err && err.name === "AbortError" && !mine.late;
          var cut = !stopped && !mine.late && !!err && (err.name === "TypeError" || err.code === "cut");
          if (!stopped) track("plan_error", { code: (err && err.code) || (mine.late ? "timeout" : cut ? "cut" : "error") });
          if (state.phase === "wait") { state.phase = stopped ? "stopped" : cut ? "cut" : "kept"; save(); syncBar(); }
          return;
        }
        if (err && err.name === "AbortError" && !mine.late) { busy(false); return; }
        if (mine.late) err = { code: "timeout", message: "1분 넘게 걸려 멈췄어요. 다시 시도하거나, 기간을 줄이거나 조건을 덜 골라 주세요." };
        // conditions no plan can meet (planner preflight): back to the form, the causes and their fixes by the button
        if (err && err.code === "conditions" && Array.isArray(err.problems) && err.problems.length && !edit) {
          track("plan_conditions", { fields: err.problems.map(function (x) { return String(x.field || ""); }).join(",") });
          showProblems(err, c);
          return;
        }
        track("plan_error", { code: (err && err.code) || "error" });
        // the server's own messages only; a script error is never shown as it is
        failed((err && err.code && err.message) || "코스를 만들지 못했습니다. 다시 시도해 주세요.", body, c, edit, opts);
      })
      .then(function () { if (mine === ctrl) { clearInterval(tick); busy(false); ctrl = null; actIdle(); } });
  }
  work.querySelector("[data-plan-cancel]").addEventListener("click", function () { if (ctrl) ctrl.abort(); });

  // ------------------------------------------------------------ the course sent first (SSE 'early', a new plan only)
  // The site's own course, drawn at once; the request goes on under it. The tab keeps the plan on screen (state.plan)
  // and both courses (state.early, state.final) with where the reader is (state.phase).
  var BAR = {
    wait: ["busy", "사이트 자료로 먼저 짠 코스예요 · AI가 조건에 맞게 다듬는 중", "멈추기"],
    ready: ["ok", "AI가 다듬은 코스가 왔어요", "AI가 다듬은 코스 보기"],
    swapped: ["ok", "AI가 다듬은 코스로 바꿨어요", "먼저 보여 드린 코스 보기"],
    back: ["info", "먼저 보여 드린 코스예요", "AI가 다듬은 코스 보기"],
    kept: ["info", "AI가 다듬지 못해 먼저 짠 코스를 그대로 둬요", ""],
    stopped: ["info", "다듬기를 멈췄어요 · 먼저 짠 코스를 그대로 둬요", ""],
    cut: ["info", "다듬는 중에 끊겨 먼저 짠 코스를 그대로 둬요", ""],
  };
  function early(ev, mine, c) {
    if (mine !== ctrl || !fits(ev.plan)) return;
    mine.early = true;
    state = { conditions: c, plan: ev.plan, sig: ev.sig || null, diff: null, early: { plan: ev.plan, sig: ev.sig || null }, phase: "wait" };
    save();
    touched = false;
    track("plan_early", { days: c.days });
    form.querySelector(".trp-submit").disabled = false;
    // the working view goes in the frame the course comes in ('멈추기' moves to the line over the course): what is
    // below it never comes into view in between
    // (also when the request ended meanwhile — stopped, failed: the course sent first is still the one to show)
    getPlaces().then(function () {
      if ((ctrl && ctrl !== mine) || !state || !state.early || state.early.plan !== ev.plan) return;
      work.hidden = true;
      show(true);
    });
  }
  function sameCourse(a, b) {
    return a.days.length === b.days.length && a.days.every(function (d, i) {
      var e = b.days[i].stops;
      return d.stops.length === e.length && d.stops.every(function (s, j) {
        return s.path === e[j].path && s.start === e[j].start && s.end === e[j].end && s.role === e[j].role;
      });
    });
  }
  // the AI's plan, after the course sent first: in place while the reader has not touched the result, else offered
  function arrive(ev, c) {
    return getPlaces().then(function () {
      if (!state || !state.early) return;
      var plan = ev.plan;
      state.final = { plan: plan, sig: ev.sig || null };
      track("plan_done", { days: c.days, flags: (plan.flags || []).length, status: plan.status, code: codeBuilt(plan) ? 1 : 0 });
      // the AI gave nothing (the server sent the same course back, built by the site, its line saying why): kept.
      // The tab keeps the plan on screen — redrawn with that line only while the reader has not touched it
      if (codeBuilt(plan) && sameCourse(state.early.plan, plan)) {
        state.phase = "kept";
        if (!touched) { state.plan = plan; state.sig = state.final.sig; }
        save();
        if (touched) syncBar(); else redraw();
        return;
      }
      if (!touched) { swapTo("final", true, false); return; }
      state.phase = "ready";
      save();
      syncBar();
      var r = barEl && barEl.getBoundingClientRect();
      if (!r || r.bottom < 0 || r.top > win.innerHeight) showToast();
    });
  }
  // which: 'final' (the AI's) or 'early' (the first); jump: to the result's top (the reader asked from further down)
  function swapTo(which, auto, jump) {
    if (!state || !state.early || !state.final) return;
    var to = which === "final" ? state.final : state.early, from = which === "final" ? state.early : state.final;
    state.plan = to.plan;
    state.sig = to.sig;
    state.phase = which === "final" ? "swapped" : "back";
    state.diff = which === "final" ? diffPlans(from.plan, to.plan) : null;
    save();
    hideToast();
    if (which === "final") track("plan_swap", { auto: auto ? 1 : 0 });
    redraw();
    if (jump) {
      result.scrollIntoView({ block: "start" });
      result.querySelector("#h-result").focus({ preventScroll: true });
    }
  }
  // the course drawn again in place: focus stays where it was (on the heading when it was in the result — the redraw
  // takes the old nodes away), and the line's new words are read out once the line is back on the page (draw)
  function redraw() {
    var a = doc.activeElement, inside = !!(a && a !== doc.body && result.contains(a) && !(barEl && barEl.contains(a)));
    var onBar = !!(a && barEl && barEl.contains(a));
    draw(false);
    if (onBar && barEl && barEl.isConnected) barEl.querySelector("button").focus({ preventScroll: true });
    else if (inside || a === doc.body) {
      var hd = result.querySelector("#h-result");
      if (hd) hd.focus({ preventScroll: true });
    }
  }
  function onBar() {
    if (!state) return;
    if (state.phase === "wait") { if (ctrl) ctrl.abort(); }
    else if (state.phase === "ready" || state.phase === "back") swapTo("final", false, false);
    else if (state.phase === "swapped") swapTo("early", false, false);
  }
  // the line over the course: one node for the whole request (a status region whose words change, so they are read
  // out), its height the same in every phase — the button keeps its room when there is none (nothing above the
  // reader moves when the AI's plan comes)
  function syncBar() {
    wakeActs();
    if (!state || !state.early || !BAR[state.phase]) { barEl = null; return null; }
    var fresh = !barEl;
    if (!barEl) {
      // every phase's words and every button's label sit, unseen, in the same cells (.trp-early-g): the cells keep
      // the size of the longest at any width, so a change of phase never moves what is under the line
      var phases = Object.keys(BAR);
      var labels = phases.map(function (k) { return BAR[k][2]; }).filter(function (x, i, a) { return x && a.indexOf(x) === i; });
      barEl = h("div", { class: "trp-early" }, [h("span", { class: "trp-early-m", "aria-hidden": "true" }),
        h("span", { class: "trp-early-s" }, [h("p", { class: "trp-early-t", id: "trp-line", role: "status" })].concat(phases.map(function (k) {
          return h("span", { class: "trp-early-t trp-early-g", "aria-hidden": "true", text: BAR[k][1] });
        }))),
        h("span", { class: "trp-early-a" }, [h("button", { type: "button", class: "btn btn-ol trp-early-b" })].concat(labels.map(function (l) {
          return h("span", { class: "btn btn-ol trp-early-b trp-early-g", "aria-hidden": "true", text: l });
        })))]);
      barEl.querySelector("button").addEventListener("click", onBar);
    }
    var b = BAR[state.phase], t = barEl.querySelector(".trp-early-t"), btn = barEl.querySelector("button");
    barEl.className = "trp-early is-" + b[0];
    barEl.setAttribute("data-phase", state.phase);
    barEl.querySelector(".trp-early-m").textContent = b[0] === "busy" ? "" : b[0] === "ok" ? "✓" : "i";
    // a status region's change is read out only while it is on the page: when draw has just taken the line off to put
    // it back, its words change a moment after it is back (the cells keep their size: nothing moves)
    if (t.textContent !== b[1]) {
      if (fresh || barEl.isConnected) t.textContent = b[1];
      else setTimeout(function () { if (state && BAR[state.phase] && BAR[state.phase][1] === b[1]) t.textContent = b[1]; }, 120);
    }
    // the button that goes (a phase with none: 멈추기 pressed, the AI's course kept or cut) gives its focus to the line's
    // words, read out — never to the page's top (round-6 verifier: keyboard and screen readers lost their place)
    if (!b[2] && doc.activeElement === btn) { t.setAttribute("tabindex", "-1"); t.focus({ preventScroll: true }); }
    btn.textContent = b[2] || "멈추기";
    btn.style.visibility = b[2] ? "" : "hidden";
    if (b[2]) { btn.removeAttribute("aria-hidden"); btn.removeAttribute("tabindex"); }
    else { btn.setAttribute("aria-hidden", "true"); btn.setAttribute("tabindex", "-1"); }
    return barEl;
  }
  // the AI's plan came while the reader is further down: a toast at the screen's foot (fixed — nothing moves)
  function showToast() {
    hideToast();
    var go = h("button", { type: "button", class: "btn trp-toast-go", "aria-label": "AI가 다듬은 코스 보기", text: "코스 보기" });
    var x = h("button", { type: "button", class: "trp-toast-x", "aria-label": "알림 닫기", text: "×" });
    go.addEventListener("click", function () { swapTo("final", false, true); });
    x.addEventListener("click", hideToast);
    toastEl = h("div", { class: "trp-toast" }, [h("p", { text: "AI가 다듬은 코스가 왔어요" }), go, x]);
    root.append(toastEl);
  }
  function hideToast() { if (toastEl) { toastEl.remove(); toastEl = null; } }
  // has the reader touched the course sent first? A tap or a key inside the result (not on the line), a scroll past
  // the status panel. Programmatic focus and scrolling (the page's own, on drawing) do not count.
  function touch(e) {
    if (touched || !state || state.phase !== "wait" || (barEl && barEl.contains(e.target))) return;
    if (e.type === "focusin" && e.target && e.target.id === "h-result") return;
    touched = true;
  }
  ["pointerdown", "keydown", "input", "focusin"].forEach(function (t) { result.addEventListener(t, touch); });
  win.addEventListener("scroll", function () {
    if (touched || !state || state.phase !== "wait") return;
    var p = result.querySelector(".trp-status");
    if (p && p.getBoundingClientRect().bottom < 0) touched = true;
  }, { passive: true });

  // ------------------------------------------------------------ conditions no plan can meet (planner preflight)
  // {message, problems: [{field, text, fixes: [{label, set?, focus?}]}]}: the server's own words, a fix that sets the
  // form (the same controls the reader uses, so the summary and the counters follow) or puts the cursor on a field.
  // A change by hand makes the box stale and it goes.
  var applying = false;
  var goBox = form.querySelector(".trp-go");
  var prob = h("div", { class: "trp-prob", role: "alert", hidden: true });
  goBox.parentNode.insertBefore(prob, goBox);   // above the button's bar (on phones that bar stays at the screen's foot)
  function hideProblems() { if (prob && !prob.hidden) { prob.hidden = true; prob.textContent = ""; } }
  var FOCUS = { date: function () { return dateIn; }, days: "days", move: "move", with: "with", prefs: "prefs", needs: "needs",
    adults: '[data-count="adults"] [data-step="1"]', seniors: '[data-count="seniors"] [data-step="1"]', kids: '[data-count="kids"] [data-step="1"]' };
  function fieldEl(name) {
    var f = FOCUS[name];
    if (typeof f === "function") return f();
    if (f && f.charAt(0) === "[") return form.querySelector(f);
    if (f) return form.querySelector('input[name="' + f + '"]:checked') || form.querySelector('input[name="' + f + '"]');
    return form.elements[name] || null;
  }
  function showProblems(err, c) {
    formErr.hidden = true;
    prob.textContent = "";
    var done = h("p", { class: "trp-prob-done", role: "status" });
    var list = h("ul", { class: "trp-prob-l" }, err.problems.map(function (x) {
      var fixes = (x.fixes || []).filter(function (f) { return f && f.label && (f.set || f.focus); }).map(function (f) {
        var b = h("button", { type: "button", class: "btn btn-ol trp-prob-fix", text: f.label });
        b.addEventListener("click", function () {
          track("plan_fix", { kind: "conditions" });
          if (f.set) {
            var next = Object.assign(conditions(), f.set);
            applying = true;
            try { setForm(next); } finally { applying = false; }
            done.textContent = "조건을 바꿨어요. 바꾼 조건은 아래 요약 줄에 있어요.";
            go.hidden = false;
            go.scrollIntoView({ block: "center" });   // clear of the button's bar at the foot of a phone's screen
            go.focus({ preventScroll: true });
          } else {
            var el = fieldEl(f.focus);
            if (el) { el.scrollIntoView({ block: "center", behavior: "smooth" }); el.focus({ preventScroll: true }); }
          }
        });
        return b;
      });
      return h("li", {}, [h("p", { text: x.text })].concat(fixes.length ? [h("div", { class: "trp-prob-fixes" }, fixes)] : []));
    }));
    var go = h("button", { type: "submit", class: "btn trp-prob-go", text: "바꾼 조건으로 코스 만들기", hidden: true });
    prob.append(h("h3", { tabindex: "-1", text: "이 조건으로는 코스를 끝까지 짤 수 없어요" }),
      h("p", { class: "trp-prob-m", text: (err.message || "").replace(/^이 조건으로는 코스를 끝까지 짤 수 없어요\.\s*/, "") || "아래를 바꿔 주세요." }), list, done, go);
    prob.hidden = false;
    prob.scrollIntoView({ block: "center" });
    prob.querySelector("h3").focus({ preventScroll: true });
  }

  function failed(message, body, c, edit, opts) {
    work.hidden = true;   // first: the box is placed (and focused) where it stays
    var again = h("button", { type: "button", class: "btn", text: "다시 시도" });
    // (a stop's own button tried again the way it was sent: no working view, drawn in place — opts)
    again.addEventListener("click", function () { ask(body, c, edit, opts); });
    if (edit && state) {   // a change that failed: the plan stays, the message sits above the edit box
      draw(false);
      var box = result.querySelector(".trp-edit");
      var note = h("div", { class: "trp-fail trp-fail-edit", role: "alert" }, [mascot("sorry"), h("div", {}, [
        h("h3", { tabindex: "-1", text: "바꾸지 못했어요" }), h("p", { text: message }), again])]);
      box.prepend(note);
      note.querySelector("h3").focus();
      return;
    }
    result.hidden = false;
    result.textContent = "";
    result.append(h("div", { class: "wrap trp-fail", role: "alert" }, [mascot("sorry"), h("div", {}, [
      h("h2", { id: "h-result", tabindex: "-1", text: "코스를 만들지 못했어요" }), h("p", { text: message }), again,
      h("p", { class: "trp-hint" }, ["그동안 ", h("a", { href: "/courses/", text: "공식 코스" }), "나 ", h("a", { href: "/guides/", text: "가이드" }),
        "에서 일정을 찾아볼 수 있어요."])])]));
    result.querySelector("h2").focus();
  }


  function lostNote(full) {
    var again = h("button", { type: "button", class: "btn", text: "이 조건으로 다시 만들기" });
    again.addEventListener("click", function () {
      if (form.requestSubmit) form.requestSubmit(); else form.querySelector(".trp-submit").click();
    });
    result.hidden = false;
    result.textContent = "";
    result.append(h("div", { class: "wrap trp-fail trp-lost", role: "status" }, [mascot("sorry"), h("div", {}, [
      h("h2", { id: "h-result", tabindex: "-1", text: "이전 코스를 다시 불러오지 못했어요" }),
      h("p", { text: full ? "이 탭에 코스를 보관하지 못했어요(브라우저 저장 공간이 모자라거나 사생활 보호 모드)." : "이 탭에 남은 코스가 지금 페이지가 그릴 수 없는 예전 형식이에요." }),
      h("p", { text: "고른 조건은 위 폼에 그대로 두었어요. 다시 만든 코스는 '링크 복사'나 '파일로 저장'으로 남겨 두면 탭을 닫아도 다시 볼 수 있어요." }),
      again])]));
  }

  // ------------------------------------------------------------ the result
  var curDay = 0;
  // a plan this page can draw: the server's checked plan (planner.js finish v 2); an older shape kept in the tab or a
  // reply missing a part is not drawn (review 2026-10-17 CE10: a fee object without amounts broke the page)
  function fits(p) {
    return !!(p && p.v === 2 && Array.isArray(p.days) && p.days.length && p.days.every(function (d) { return d && Array.isArray(d.stops); })
      && p.fees && typeof p.fees === "object" && Array.isArray(p.checks) && Array.isArray(p.needs));
  }
  function num(n) { return typeof n === "number" && isFinite(n); }
  // a plan the site built from its own data when the AI gave none it could use (planner codePlan): one 'fixed' line
  // starting '일정 전체:', every stop put in by the site
  function codeBuilt(p) { return !!(p && (p.fixed || []).length === 1 && /^일정 전체:/.test(p.fixed[0])); }
  function codeLine(p) { return p.fixed[0].replace(/^일정 전체:\s*/, "").replace(/짰습니다$/, "짰어요"); }
  function money(n) { return num(n) ? won(n) : "—"; }
  function outsideText(o) { return "외관 감상 · 내부 관람 불가(자료: " + (o.p || "자료") + ")"; }
  function factRow(label, value, cls) {
    if (!value) return null;
    return h("li", { class: cls || "" }, [h("span", { class: "trp-fl", text: label }), h("span", { text: value })]);
  }
  // the day as the stop's label says it (review 2026-10-22 S2: '그날 운영' above '확인: 그날은 공휴일 … 그날 여는지 확인
  // 필요'): a stop its regular rule keeps open (knowledge.checkPlan day 'open') whose day still asks whether it opens —
  // a public holiday, a 설·추석 rule — reads '운영 확인 필요' like a stop the rule cannot decide; a season's hours or a
  // second visit says nothing of the day
  var DAY_CHECK = /그날 (?:여는지|쉬는지) 확인 필요/;
  function dayShown(s) {
    var st = LABEL.day[s.day] ? s.day : "unknown";
    return st === "open" && (s.checks || []).some(function (x) { return DAY_CHECK.test(x); }) ? "unknown" : st;
  }
  // a stop the site swapped in, by why (review 2026-10-22 S5: every swap read '그날 쉬는 곳 대신', a budget's or a
  // need's too): planner finish swapped 'closed' — the stop it replaced was closed that day; any other value, and true
  // from a plan made before the reason was passed, only that the site swapped it in. short: the text passed on
  function swapWords(s, short) {
    if (!s.swapped) return "";
    if (s.swapped === "closed") return short ? "쉬는 곳 대신 사이트가 고름" : "그날 쉬는 곳 대신 사이트가 고른 가까운 곳이에요";
    return short ? "사이트가 바꿔 넣음" : "사이트가 바꿔 넣은 가까운 곳이에요";
  }
  function stopCard(s, n, di, day) {
    var p = (places || {})[s.path] || {};
    var ph;
    if (p.img) {
      var img = h("img", { src: p.img.u, alt: p.img.alt || p.n || s.name, loading: "lazy", decoding: "async",
        width: p.img.w || null, height: p.img.h || null, "data-kogl": String(p.img.t) });
      if (p.img.s && p.img.sw && p.img.w) { img.setAttribute("srcset", p.img.s + " " + p.img.sw + "w, " + p.img.u + " " + p.img.w + "w"); img.setAttribute("sizes", "(min-width: 768px) 200px, 112px"); }
      ph = h("figure", { class: "trp-ph" + (p.img.t === 3 ? " t3" : " t1") }, [img, h("figcaption", { text: "출처: 한국관광공사" })]);
    } else {
      ph = h("div", { class: "trp-ph trp-ph-pic" }, [pic(p.ic || "kind-attraction")]);
    }
    var st = s.day || "unknown", shown = dayShown(s);
    var facts = h("ul", { class: "trp-facts" }, [
      h("li", { class: "trp-day trp-day-" + shown }, [h("span", { class: "trp-fl", text: "그날" }), h("span", { text: LABEL.day[shown].replace("그날 ", "") })]),
      // a place whose inside is not open to visitors (planner finish 'outside', outside tester 2026-10-23): what it is,
      // with the sources that say so, in place of hours that are only those words ('내부 관람 불가')
      s.outside ? factRow("관람", outsideText(s.outside)) : null,
      s.outside && s.outside.only ? null : factRow("시간", p.h), factRow("쉬는 날", p.c, "trp-closed"),
      factRow(p.k === "food" ? "메뉴" : "요금", p.k === "food" ? p.m : p.f), factRow("주차", p.p),
      s.role === "stay" ? factRow("체크인", p.ci) : null]);
    var notes = (s.flags || []).map(function (f) { return h("li", { class: "bad", text: f }); })
      .concat((s.checks || []).map(function (f) { return h("li", { text: "확인: " + f }); }));
    var kind = [LABEL.role[s.role] || "", p.t, p.r || ""].filter(Boolean).join(" · ");   // p.r: its 구·군 or 권역
    // a stop the site put in itself (planner.repair): said so, where the AI's reason would be
    var by = state && codeBuilt(state.plan) ? "" : s.added ? (s.role === "meal" ? "식사할 곳이 없어 사이트가 넣은 가까운 음식점이에요"
      : s.role === "stay" ? "묵을 곳이 없어 사이트가 넣은 숙소예요" : "빈 시간이 길어 사이트가 넣은 가까운 곳이에요")
      : swapWords(s, false);
    return h("li", { class: "trp-stop", "data-day": st, "data-role": s.role, "data-by": s.added ? "site" : s.swapped ? "swap" : null, "data-path": s.path }, [
      h("div", { class: "trp-time" }, [h("span", { class: "trp-num", text: String(n) }), h("b", { class: "tn", text: s.start }), h("span", { class: "tn", text: "~" + s.end })]),
      h("article", { class: "trp-card2" }, [ph, h("div", { class: "trp-body" }, [
        h("p", { class: "trp-kind", text: kind }),
        h("h3", {}, [h("a", { href: s.path, text: s.name })]),
        s.why ? h("p", { class: "trp-why" }, [h("span", { class: "trp-ai", text: "AI" }), h("span", { text: s.why })]) : null,
        by ? h("p", { class: "trp-why trp-by" }, [h("span", { class: "trp-site", text: "사이트" }), h("span", { text: by })]) : null,
        facts, notes.length ? h("ul", { class: "trp-warn" }, notes) : null, day ? stopActs(s, di, day) : null])])]);
  }

  // ------------------------------------------------------------ a stop's own buttons (operator 2026-10-23, mockup A)
  // Under each stop's facts: 빼기 · 다른 곳으로 · 고정, on the reader's own plan only — not on a shared one (as the quick
  // fixes), not while the AI still refines the course sent first. 빼기 and 다른 곳으로 go as an edit with an act
  // (planner actOn: the code alone, no model call — the stop taken out and the stops after it moved sooner, or swapped
  // for a place of its kind that fits the same slot; tried: the places this slot was swapped away from in this tab);
  // 고정 is the page's own: the pinned stops (state.pins, 'day|path') stay in this tab with the plan, never in a link,
  // and ride with every later edit (pins), the server keeping each on its day. 빼기 on a pinned stop unpins it; 다른
  // 곳으로 waits while it is pinned (said in its title and to a screen reader). A day's only stop has no 빼기, a night's
  // stay no 다른 곳으로, a place with no point on the site no 다른 곳으로 (nothing to search near).
  var ICONS = {
    drop: [["circle", { cx: "12", cy: "12", r: "8.5" }], ["path", { d: "M8 12h8" }]],
    swap: [["path", { d: "M5 8h13l-3.5-3.5M19 16H6l3.5 3.5" }]],
    pin: [["path", { d: "M9 3.5h6l-1 6 3.5 3.5h-11L10 9.5z" }], ["path", { d: "M12 13v7.5" }]],
  };
  function actIcon(k) {
    var el = svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor",
      "stroke-width": "2.2", "stroke-linecap": "round", "stroke-linejoin": "round" });
    ICONS[k].forEach(function (x) { el.append(svg(x[0], x[1])); });
    return h("span", { class: "trp-act-ic" }, [el]);
  }
  function pinKey(di, path) { return di + "|" + path; }
  function isPinned(di, path) { return !!(state && state.pins && state.pins.indexOf(pinKey(di, path)) >= 0); }
  var NO_SWAP = { pin: "고정한 곳이라 다른 곳으로 바꾸지 않아요 — 고정을 풀면 바꿀 수 있어요", point: "사이트에 좌표가 없어 가까운 곳을 찾을 수 없어요" };
  // a button that does nothing for now: still focusable, its reason in its title and in its name for a screen reader
  function holdAct(b, why) {
    var r = b.querySelector(".trp-act-why");
    if (r) r.remove();
    if (why) {
      b.setAttribute("aria-disabled", "true");
      b.setAttribute("title", why);
      b.append(h("span", { class: "vh trp-act-why", text: " — " + why }));
    } else {
      b.removeAttribute("aria-disabled");
      b.removeAttribute("title");
    }
  }
  function stopActs(s, di, day) {
    var plan = state && state.plan;
    if (!plan || viewing(plan)) return null;
    var p = (places || {})[s.path] || {};
    var only = s.role !== "stay" && day.stops.filter(function (x) { return x.role !== "stay"; }).length < 2;
    var b = function (kind, label, cls) {
      return h("button", { type: "button", class: "trp-act" + (cls ? " " + cls : ""), "data-act": kind }, [actIcon(kind), h("span", { class: "trp-act-t", text: label })]);
    };
    var drop = only ? null : b("drop", "빼기", "trp-act-drop");
    var swap = s.role === "stay" ? null : b("swap", "다른 곳으로");
    var pin = b("pin", "고정");
    var paint = function () {
      var on = isPinned(di, s.path);
      pin.setAttribute("aria-pressed", String(on));
      pin.querySelector(".trp-act-t").textContent = on ? "고정됨" : "고정";
      if (swap) holdAct(swap, on ? NO_SWAP.pin : !p.g ? NO_SWAP.point : "");
    };
    if (drop) drop.addEventListener("click", function () { sendAct("drop", di, s, drop); });
    if (swap) swap.addEventListener("click", function () { if (swap.getAttribute("aria-disabled") !== "true") sendAct("swap", di, s, swap); });
    pin.addEventListener("click", function () {
      if (ctrl) return;
      var k = pinKey(di, s.path), list = (state.pins || []).slice(), at = list.indexOf(k);
      if (at >= 0) list.splice(at, 1); else list.push(k);
      state.pins = list;
      save();
      paint();
    });
    paint();
    var kids = [drop, swap, pin].filter(Boolean);
    // (while the AI still refines the course sent first, the row keeps its room unseen and out of reach — inert —, so
    // nothing under the reader moves when it comes: wakeActs)
    return h("div", { class: "trp-acts" + (kids.length < 3 ? " trp-acts-" + kids.length : ""), role: "group", "aria-label": s.name + " 바꾸기",
      inert: state.phase === "wait" ? true : null }, kids);
  }
  function wakeActs() {
    if (state && state.phase === "wait") return;
    Array.prototype.forEach.call(result.querySelectorAll(".trp-acts[inert]"), function (x) { x.removeAttribute("inert"); });
  }
  // the button pressed: busy until the answer comes (the others wait: one change at a time)
  var acting = null;
  function sendAct(op, di, s, btn) {
    if (!state || !state.plan || ctrl) return;
    var stops = state.plan.days[di].stops, j = stops.indexOf(s);
    var act = { op: op, day: di, page: s.path };
    if (op === "swap") act.tried = ((state.tried || {})[pinKey(di, s.path)] || []).slice(-20);
    var body = editBody("");
    body.act = act;
    // (빼기 on a pinned stop: sent unpinned — the reader takes it out themselves; the pin goes with the stop (carry),
    // and stays when the change fails — review: a failed 빼기 left the stop unpinned on screen)
    if (op === "drop" && body.pins) {
      body.pins = body.pins.filter(function (p) { return !(p.day === di && p.page === s.path); });
      if (!body.pins.length) delete body.pins;
    }
    acting = { btn: btn, text: btn.querySelector(".trp-act-t").textContent };
    btn.setAttribute("aria-busy", "true");
    btn.querySelector(".trp-act-t").textContent = op === "drop" ? "빼는 중…" : "찾는 중…";
    result.classList.add("trp-acting");
    actSaid.textContent = "";
    // where the focus goes after: the stop swapped in, or the stop after the one taken out (else the one before it)
    var next = op === "drop" ? (stops[j + 1] || stops[j - 1] || {}).path : null;
    ask(body, state.conditions, true, { quiet: true, done: function (ev) { afterAct(ev, op, di, j, next); } });
  }
  function actIdle() {
    result.classList.remove("trp-acting");
    if (!acting) return;
    if (acting.btn.isConnected) { acting.btn.removeAttribute("aria-busy"); acting.btn.querySelector(".trp-act-t").textContent = acting.text; }
    acting = null;
  }
  // what the button did, read out (the list '바꾼 뒤 달라진 것' is at the result's top, out of sight)
  var actSaid = h("p", { class: "vh", role: "status" });
  root.append(actSaid);
  function afterAct(ev, op, di, j, next) {
    acting = null;
    result.classList.remove("trp-acting");
    curDay = di;
    draw(false);
    var cards = Array.prototype.slice.call(result.querySelectorAll(".trp-tl .trp-stop"));
    var want = op === "swap" ? (ev.act && ev.act.to) || (state.plan.days[di].stops[j] || {}).path : next;
    var card = cards.filter(function (li) { return li.getAttribute("data-path") === want; })[0] || cards[Math.min(j, cards.length - 1)];
    if (card) {
      var swapB = card.querySelector('[data-act="swap"]');
      var target = op === "swap" && swapB && swapB.getAttribute("aria-disabled") !== "true" ? swapB : card.querySelector(".trp-body h3 a");
      card.scrollIntoView({ block: "center" });
      if (target) target.focus({ preventScroll: true });
    }
    var said = ((state.plan.edited || []).filter(function (x) { return x && x.k === "act"; })[0] || {}).t;
    if (said) setTimeout(function () { actSaid.textContent = said; }, 60);
  }
  // what an edit keeps of the tab's own: the pins still on their day, and the places each slot was swapped away from
  // (a swap's: the stop swapped in inherits its slot's list, with the place it replaced)
  function carry(had, now, act, done) {
    var on = function (k) {
      var i = k.indexOf("|"), d = now.plan.days[+k.slice(0, i)];
      return !!d && d.stops.some(function (x) { return x.path === k.slice(i + 1); });
    };
    var pins = (had.pins || []).filter(on);
    if (pins.length) now.pins = pins;
    var tried = {};
    Object.keys(had.tried || {}).forEach(function (k) { if (on(k)) tried[k] = had.tried[k]; });
    if (act && act.op === "swap" && done && done.to) {
      tried[pinKey(act.day, done.to)] = ((had.tried || {})[pinKey(act.day, act.page)] || []).concat([act.page]).slice(-20);
    }
    if (Object.keys(tried).length) now.tried = tried;
  }
  // a leg: its straight line, the margin the plan keeps, shared bus routes, a directions link; the line that the real
  // travel time is not known is said once above the day (legNote), and under a leg only when the leg is flagged
  function legRow(l, move) {
    var icon = l.mode === "car" ? "fact-parking" : l.mode === "walk" ? "sit-walk" : "transit-bus";
    var bits = [h("span", { class: "trp-leg-d tn", text: dist(l.m) || "거리 모름" })];
    bits.push(h("span", { class: "trp-leg-g", text: l.gap > 0 ? "계획상 여유 " + l.gap + "분" : "여유 없음" }));
    if (move === "transit" && l.routes && l.routes.length) bits.push(h("span", { class: "trp-leg-r", text: "근처 정류장에 같은 번호 노선 " + l.routes.join("·") + "번(방향·시각 확인)" }));
    var go = l.url ? h("a", { class: "trp-leg-go", href: l.url, target: "_blank", rel: "noopener", text: "카카오맵 " + LABEL.mode[l.mode] + " 길찾기" }) : null;
    // (l.open: without a car, a leg the site's data cannot confirm — no walk, no bus both places' stops share)
    var note = l.flag ? l.flag + " — 지도 앱에서 실제 시간을 확인하세요"
      : l.open ? "차 없이 이어 갈 확인된 대중교통이 사이트에 없어요 — 버스 시간표나 택시로 확인하세요" : "";
    return h("li", { class: "trp-leg" + (l.flag ? " trp-leg-bad" : l.open ? " trp-leg-open" : "") }, [pic(icon), h("div", { class: "trp-leg-in" }, [
      h("p", {}, bits), note ? h("p", { class: "trp-leg-note", text: note }) : null, go])]);
  }
  function legNote(day) {
    return (day.legs || []).length ? h("p", { class: "trp-tl-note" }, [pic("transit-bus"),
      h("span", { text: "장소 사이 거리는 직선거리이고, 시간은 계획에 둔 여유예요. 실제 이동 시간은 확인되지 않았어요 — 구간마다 있는 카카오맵 길찾기로 확인하세요." })]) : null;
  }
  function hubRow(hb) {   // the trip's start or end at a station or a terminal: no point on the site, a link by names
    var from = hb.dir === "from";
    return h("li", { class: "trp-leg trp-hub" + (hb.gap > 0 ? "" : " trp-leg-bad") }, [pic("transit-bus"), h("div", { class: "trp-leg-in" }, [
      h("p", {}, [h("span", { class: "trp-leg-d", text: from ? hb.name + " " + hb.at + " 출발" : hb.name + " " + hb.at + "까지 도착" }),
        h("span", { class: "trp-leg-g", text: (from ? "첫 장소까지 계획상 여유 " : "마지막 장소 뒤 계획상 여유 ") + Math.max(0, hb.gap) + "분" })]),
      h("p", { class: "trp-leg-note", text: "이동 시간·거리는 사이트에 없어요 — 지도 앱에서 확인하세요" }),
      h("a", { class: "trp-leg-go", href: hb.url, target: "_blank", rel: "noopener", text: "카카오맵 길찾기" }), hubGuideLink(hb)])]);
  }
  // the site's own bus guide for a hub leg (review 2026-10-22 movement S2: the guides cover these legs and the plan
  // never linked them): planner hubLegs' guide {path, label}, a page of this site, for a reader on the bus only
  function hubGuide(hb) {
    var g = hb && hb.guide, move = ((state || {}).conditions || {}).move;
    return g && typeof g.path === "string" && /^\/[^/]/.test(g.path) && move !== "car" ? g : null;
  }
  function hubGuideLink(hb) {
    var g = hubGuide(hb);
    return g ? h("a", { class: "trp-leg-go", href: g.path, text: "버스 안내(가이드)",
      "aria-label": g.label ? "버스 안내(가이드): " + g.label : null }) : null;
  }
  function hubGuideText(hb) {
    var g = hubGuide(hb);
    return g ? " · 버스 안내 " + SITE + encodeURI(g.path) : "";
  }
  function dayMap(day) {
    var pts = [];
    day.stops.forEach(function (s, i) {
      var p = (places || {})[s.path];
      if (p && p.g) pts.push({ lat: p.g[0], lng: p.g[1], name: s.name, url: s.path, n: i + 1 });
    });
    if (pts.length < 1) return h("p", { class: "trp-nomap", text: "이 날의 장소에는 지도 좌표가 없어요." });
    var box = h("div", { class: "map", role: "region", "aria-label": day.label + " 지도", "data-map": JSON.stringify({ course: pts }) },
      [h("p", { class: "map-off", text: "지도를 불러오는 중입니다." })]);
    var fig = h("figure", { class: "trp-map" }, [box, h("figcaption", { text: "번호는 일정 순서" + (pts.length < day.stops.length ? " · 좌표가 있는 " + pts.length + "곳만 표시" : "") + " · 지도 © OpenStreetMap contributors" })]);
    setTimeout(function () { startMap(box); }, 0);
    return fig;
  }
  function startMap(box) {   // map.js (Leaflet + OpenStreetMap) builds a box added after load; loaded here when needed
    if (win.GSMapStart) { win.GSMapStart(box); return; }
    var s = doc.querySelector('script[src$="map.js"]');
    if (!s) { s = h("script", { src: BASE + "map.js" }); doc.body.append(s); }
    s.addEventListener("load", function () { if (win.GSMapStart) win.GSMapStart(box); });
  }

  // ------------------------------------------------------------ what the code says about the plan
  // 'check' is a plan made before 2026-10-18 kept in the tab: it broke nothing either (its checks were notes)
  var STATUS = {
    ready: ["ok", "완성된 코스예요"],
    check: ["ok", "완성된 코스예요"],
    unmet: ["bad", "조건을 다 맞추지 못한 초안이에요"],
  };
  var MARK = { ok: "✓", info: "i", bad: "!", na: "–" };
  // finish 'aware' (2026-10-18 on); for a plan kept from before, the same kinds out of its checks
  var AWARE_K = { move: 1, hub: 1, stay: 1, walk: 1, note: 1, outside: 1 };
  function awareOf(plan) {
    return Array.isArray(plan.aware) ? plan.aware : plan.checks.filter(function (x) { return AWARE_K[x.k]; });
  }
  function checksOf(plan) {
    return plan.checks.filter(function (x) { return !AWARE_K[x.k] && !/^걷기: /.test(x.t); });
  }
  var FEE_STATE = { none: "입장료를 내는 방문지 없음", free: "모두 무료(요금 값 기준)", known: "", partial: "", unknown: "요금 확인 필요" };
  function feeHead(f) {   // [the amount as shown, a short line]: never a number the server did not give
    if (f.state === "none") return ["—", FEE_STATE.none];
    if (f.state === "free") return ["0원", FEE_STATE.free];
    if (f.state === "known") return [money(f.total), "모든 사람·방문지 계산됨"];
    if (f.state === "partial") return [money(f.known) + " + 확인 필요", "확인 필요 " + (f.open || []).length + "건 — 합계 확정 안 됨"];
    return ["확인 필요", "요금 정보 없음 " + (f.open || []).length + "건"];
  }
  function verdictText(f) {
    return { within: "예산 안", over: "예산 넘음", open: "예산 충족 확정 못 함(확인 필요 남음)", none: "" }[f.verdict] || "";
  }
  // open: the stops whose regular rule keeps them open that day, at hours that fit (review 2026-10-22 S1: a stop its own
  // rule cannot decide — day 'unknown' — counted as '방문 가능' under a ✓ and a full ring); unknown: those, apart.
  // need: per need the reader picked, its own counts (completion C1: one sum over 실내 and 유모차 hid which was unknown)
  function counted(plan) {
    var n = { all: 0, open: 0, closed: 0, timeBad: 0, unknown: 0, dayCheck: 0 };
    plan.days.forEach(function (d) {
      d.stops.forEach(function (s) {
        n.all += 1;
        if (s.day === "closed") n.closed += 1;
        else if ((s.flags || []).length) n.timeBad += 1;
        else if (s.day === "open") n.open += 1;
        if (s.day !== "open" && s.day !== "closed") n.unknown += 1;
        if (s.day === "unknown" || (s.checks || []).length) n.dayCheck += 1;
      });
    });
    n.need = plan.needs.map(function (x) {
      var c = { label: x.label || x.key || "", ok: 0, check: 0, bad: 0 };
      x.rows.forEach(function (r) { if (r.state === "ok" || r.state === "near") c.ok += 1; else if (r.state === "no") c.bad += 1; else if (r.state === "unknown" || r.state === "cond") c.check += 1; });
      return c;
    });
    n.walk = lessWalk(plan);
    return n;
  }
  // 걷기 적게 has no column (plan_state.needsTable: no data reads walking) but the reader picked it (review 2026-10-22
  // S4: the row read '고른 조건 없음' under a condition line ending '· 걷기 적게'): the plan's conditions, this tab's,
  // or the walking line finish wrote for it
  function lessWalk(plan) {
    var c = plan.conditions && Array.isArray(plan.conditions.needs) ? plan.conditions : state && state.plan === plan && state.conditions || {};
    return (c.needs || []).indexOf("lesswalk") >= 0 || knowList(plan).some(function (x) { return x.k === "walk"; });
  }
  var WALK_WORDS = "걷기 적게: 사이트 자료로 잴 수 없음 · 구간 직선거리만 있음";
  // the row '필요한 조건': '유모차: 자료 있음 4 · 정보 없음 1 / 실내: 자료 있음 2 · 정보 없음 3' (맞지 않음 when there is one)
  function needRow(n) {
    var parts = n.need.map(function (x) {
      return x.label + ": " + (x.ok + x.check + x.bad ? "자료 있음 " + x.ok + " · 정보 없음 " + x.check + (x.bad ? " · 맞지 않음 " + x.bad : "") : "해당하는 곳 없음");
    });
    if (n.walk) parts.push(WALK_WORDS);
    if (!parts.length) return ["na", "고른 조건 없음"];
    var bad = n.need.some(function (x) { return x.bad; }), check = n.walk || n.need.some(function (x) { return x.check; });
    return [bad ? "bad" : check ? "info" : "ok", parts.join(" / ")];
  }
  // a year whose 설·추석·대체공휴일 the site's holiday table does not have (planner finish, when it says so — or
  // knowledge.checkPlan's own name for it, noHolidayTable): the date rows never read all-clear for it
  function holidayTableMissing(plan) {
    var said = function (o) {
      return [o.holidayTableMissing, o.noHolidayTable].some(function (v) { return Array.isArray(v) ? v.length > 0 : !!v; });
    };
    return said(plan) || plan.days.some(said);
  }
  // how complete the day is (planner finish 'complete'): [state, words] — '점심 포함 · 역사·문화 반영 / 섬·바다 미반영 ·
  // 13:00~16:30 3시간 30분 비어 있음'; null for a plan made before it was there
  var MEAL = { lunch: "점심", dinner: "저녁" };
  var MEAL_STATE = { ok: "포함", added: "사이트가 넣음", skip: "따로(적은 대로)", missing: "빠짐" };
  var EDIT_STATE = { kept: "유지", restored: "사이트가 다시 넣음", dropped: "요청대로 뺌", lost: "빠짐" };
  function completeLine(plan) {
    var cp = plan.complete;
    if (!cp || !Array.isArray(cp.meals) || !Array.isArray(cp.gaps) || !Array.isArray(cp.prefs)) return null;
    var many = plan.days.length > 1, bad = false, check = false, parts = [], meals = [];
    // per meal: '1·2·3일차 점심 포함' when the days agree, else day by day
    ["lunch", "dinner"].forEach(function (kind) {
      var ms = cp.meals.filter(function (m) { return m.kind === kind; });
      if (ms.some(function (m) { return m.state === "missing"; })) bad = true;
      var one = ms.length > 1 && ms.every(function (m) { return m.state === ms[0].state; });
      (one ? [ms[0]] : ms).forEach(function (m) {
        var days = one ? ms.map(function (x) { return x.day + 1; }).join("·") : String(m.day + 1);
        meals.push((many ? days + "일차 " : "") + MEAL[kind] + " " + (MEAL_STATE[m.state] || m.state));
      });
    });
    if (meals.length) parts.push(meals.join(", "));
    // 맛집 is met by any meal stop (plan_state.prefMet): said as that, not as '반영' (review 2026-10-22 S6)
    var food = cp.prefs.filter(function (p) { return p.key === "food" && p.met === true; }).map(function (p) { return (p.label || "맛집") + ": 식사 장소 포함"; });
    var met = cp.prefs.filter(function (p) { return p.met === true && p.key !== "food"; }).map(function (p) { return p.label; });
    var unmet = cp.prefs.filter(function (p) { return p.met === false; }).map(function (p) { return p.label; });
    var unknown = cp.prefs.filter(function (p) { return p.met === null; }).map(function (p) { return p.label; });
    if (unmet.length || unknown.length) check = true;   // shown as information: a liking is not a condition
    var likes = [met.length ? met.join("·") + " 반영" : "", food.join(""), unmet.length ? unmet.join("·") + " 미반영" : "",
      unknown.length ? "자료로 판단 못 함: " + unknown.join("·") : ""].filter(Boolean);
    if (likes.length) parts.push(likes.join(" / "));
    if (cp.gaps.length) {
      bad = true;
      parts.push(cp.gaps.map(function (g) { return (many ? (g.day + 1) + "일차 " : "") + g.from + "~" + g.to + " " + hm(g.minutes) + " 비어 있음"; }).join(", "));
    } else parts.push("2시간 넘게 빈 시간 없음");
    (cp.edit || []).forEach(function (x) {
      if (x.state === "lost") bad = true;
      parts.push("고치기 전 일정의 " + x.what + ": " + (EDIT_STATE[x.state] || x.state));
    });
    return [bad ? "bad" : check ? "info" : "ok", parts.join(" · ")];
  }
  // the quick fixes of an 'unmet' plan (planner finish 'todo'): each sends the edit request below with fixed words
  var FIX = {
    closed: ["휴무 장소 바꾸기", "그날 쉬는 장소를 그날 여는 가까운 장소로 바꿔 주세요"],
    legs: ["이동 구간 다시 짜기", "이동이 빠듯한 구간은 여유를 두고, 가까운 곳끼리 이어지게 다시 짜 주세요"],
    meal: ["빠진 점심 넣기", "빠진 점심을 그 시간에 여는 가까운 음식점으로 넣어 주세요"],
    gaps: ["빈 시간 채우기", "비어 있는 시간에 가까운 장소를 넣어 주세요"],
  };
  function quickFixes(plan) {
    var todo = (plan.todo || []).filter(function (k) { return FIX[k]; });
    if (plan.status !== "unmet" || !todo.length) return null;
    var missing = ((plan.complete || {}).meals || []).filter(function (m) { return m.state === "missing"; }).map(function (m) { return m.kind; });
    var meal = missing.indexOf("lunch") < 0 && missing.indexOf("dinner") >= 0 ? "저녁" : missing.indexOf("dinner") >= 0 ? "식사" : "점심";
    return h("div", { class: "trp-qfix", role: "group", "aria-label": "남은 문제 바로 고치기" }, [h("p", { class: "trp-qfix-h", text: "남은 문제를 AI에게 다시 맡기기" })].concat(todo.map(function (k) {
      var label = FIX[k][0].replace("점심", meal), ask = FIX[k][1].replace("점심", meal);
      var b = h("button", { type: "button", class: "btn btn-ol trp-qf", "data-fix": k, text: label });
      b.addEventListener("click", function () { track("plan_fix", { kind: k }); sendEdit(ask); });
      return b;
    })));
  }
  // the status box's rows: [picture, label, [mark state, words]]
  function statusRows(plan) {
    var n = counted(plan), f = plan.fees;
    var done = completeLine(plan);
    var rows = [
      ["fact-hours", "정기 휴무·운영시간",
        n.closed ? ["bad", "그날 휴무인 곳 " + n.closed + "곳"] : n.timeBad ? ["bad", "시간이 맞지 않는 곳 " + n.timeBad + "곳"]
          : n.unknown ? ["info", "정기 규칙상 방문 가능 " + n.open + "/" + n.all + "곳 · 규칙만으로 알 수 없음 " + n.unknown + "곳"]
            : ["ok", "정기 규칙상 " + n.open + "/" + n.all + "곳 방문 가능"]],
      // a holiday or a date's rule (review 2026-10-18: '날짜 규칙에 걸리는 곳 없음' beside '정기 휴무 5곳'): never
      // all-clear while a stop is closed that day, nor for a year the holiday table does not have
      ["fact-closed", "공휴일·특별 운영",
        n.dayCheck ? ["info", "그날 운영 자료가 없는 곳 " + n.dayCheck + "곳 — 장소 칸에 적어 두었어요" + (holidayTableMissing(plan) ? " · 그해 공휴일 표 없음" : "")]
          : n.closed ? ["bad", "그날 쉬는 곳 " + n.closed + "곳이 남아 있음 · " + (holidayTableMissing(plan) ? "그해 공휴일 표 없음" : "그 밖에 공휴일·날짜별 공지로 걸리는 곳은 없음")]
            : holidayTableMissing(plan) ? ["info", "그해 공휴일 표 없음 — 설·추석·대체공휴일이면 그날 운영 확인"]
              : ["ok", "공휴일·날짜별 공지에 걸리는 곳 없음"]],
      ["cond-wheelchair", "필요한 조건", needRow(n)],
      ["plan-budget", "입장료",
        [f.verdict === "over" ? "bad" : f.state === "partial" || f.state === "unknown" ? "info" : "ok",
          feeHead(f)[0] + (verdictText(f) ? " · " + verdictText(f) : f.state === "partial" || f.state === "unknown" ? " · 요금 자료 없는 곳은 빼고 셈" : "")]],
      ["transit-bus", "이동", ["info", "구간마다 계획상 여유를 두었어요 · 실제 이동 시간은 지도 앱에서"]],
    ];
    if (done) rows.push(["kind-food", "일정 완성도", done]);
    return rows;
  }
  // how many of those rows are things to check before going: the ones the box marks i or ! (not ✓, not '–' for
  // 고른 조건 없음) — the number the reader counts in the box (operator 2026-10-23: an outside tester read '완성된
  // 코스예요' as 'meets every condition' above rows saying 공휴일 운영 자료가 없는 곳 2곳, 입장료 확인 필요, 걷기 적게)
  function toCheck(plan) {
    return statusRows(plan).filter(function (r) { return r[2][0] === "info" || r[2][0] === "bad"; }).length;
  }
  // the box's heading, and the 상태 line of the text passed on: a plan that broke no rule (status ready — the status
  // itself stays the server's) reads '코스 완성 · 가기 전 확인 N가지' while N rows are to check, '완성된 코스예요' with
  // none; a shared plan the same count after '오늘 자료와 어긋난 곳 없음' (viewStatus). own: the plan's own heading even
  // on a shared view (what an edit changed)
  function headOf(plan, own) {
    if (!own && viewing(plan)) return viewStatus(plan);
    var st = STATUS[plan.status] || STATUS.ready;
    if (st[0] !== "ok") return st;
    var n = toCheck(plan);
    // a way without a car the site cannot confirm (checks kind 'transit'): a draft to check, never a finished course
    var moves = (plan.checks || []).filter(function (x) { return x.k === "transit"; }).length;
    if (moves) return ["info", "이동 확인이 필요한 후보 일정 · 가기 전 확인 " + n + "가지"];
    return n ? [st[0], "코스 완성 · 가기 전 확인 " + n + "가지"] : st;
  }
  function statusPanel(plan) {
    var view = viewing(plan), st = headOf(plan);
    var list = h("ul", { class: "trp-st4" }, statusRows(plan).map(function (r) {
      return h("li", { class: "is-" + r[2][0] }, [pic(r[0]), h("span", { class: "trp-st4-l", text: r[1] }),
        h("span", { class: "trp-st4-v" }, [h("i", { class: "trp-mark", "aria-hidden": "true", text: MARK[r[2][0]] }), r[2][1]])]);
    }));
    return h("section", { class: "trp-status is-" + st[0], "aria-labelledby": "h-status" }, [
      h("h3", { id: "h-status" }, [h("i", { class: "trp-mark", "aria-hidden": "true", text: MARK[st[0]] }), st[1]]),
      (plan.flags || []).length && !view ? h("ul", { class: "trp-flags" }, plan.flags.map(function (x) { return h("li", { text: x }); })) : null,
      list,
      view ? null : quickFixes(plan)]);
  }
  function feeCard(f) {
    var head = feeHead(f), lines = [];
    (f.days || []).forEach(function (d, i) {
      d.lines.forEach(function (l) {
        var v = l.status === "paid" && num(l.won) ? won(l.won) + " × " + l.count + " = " + money(l.sub) : l.status === "free" ? "0원" : "확인 필요";
        lines.push(h("li", { class: "is-" + l.status }, [h("b", { text: ((f.days.length > 1) ? (i + 1) + "일차 " : "") + l.what + " · " + l.who + " " + l.count + "명: " }),
          h("span", { class: "tn", text: v }), h("small", { text: " (" + l.basis + ")" })]));
      });
    });
    return h("section", { class: "trp-box trp-budget-c", id: "trp-fees" }, [
      h("div", { class: "trp-box-h" }, [pic("plan-budget"), h("h3", { text: "입장료" })]),
      h("p", { class: "trp-total tn", text: head[0] }),
      h("p", { class: "trp-verdict trp-v-" + (f.verdict === "over" ? "over" : f.state === "partial" || f.state === "unknown" ? "partial" : "ok"),
        text: head[1] + (verdictText(f) ? " · " + verdictText(f) + (num(f.limit) ? " (예산 " + won(f.limit) + ")" : "") : "") }),
      lines.length ? h("ul", { class: "trp-lines" }, lines) : null,
      (f.conds || []).length ? h("ul", { class: "trp-lines trp-conds" }, f.conds.map(function (x) { return h("li", { text: x }); })) : null,
      h("p", { class: "trp-hint", text: (TICKETS ? "사이트가 장소 요금표와 통합권 요금표로 사람마다 계산했어요(통합권은 하루에 한 번, 어른 한 명 기준으로 더 싼 쪽 — 일행이 모두 65세 이상이면 그 기준)."
        : "사이트가 장소마다의 요금표로 사람마다 계산했어요.") + " 식비·교통비·숙박비는 들어 있지 않아요." })]);
  }
  // what the data does not say (finish 'checks') and what holds for any plan (finish 'aware'), in one closed box —
  // information for the day, never a list of problems (operator 2026-10-18)
  var KLABEL = { day: "그날 운영", outside: "외관만 보는 곳", fee: "입장료", need: "필요한 조건", hub: "출발·도착", transit: "차 없이 이동", stay: "숙소", move: "이동", walk: "걷기", note: "하고 싶은 말" };
  function knowList(plan) {
    var all = checksOf(plan).concat(awareOf(plan));
    if (plan.checks.some(function (x) { return /^걷기: /.test(x.t); }) && !awareOf(plan).some(function (x) { return x.k === "walk"; })) {
      all = all.concat(plan.checks.filter(function (x) { return /^걷기: /.test(x.t); }).map(function (x) { return { k: "walk", t: x.t }; }));
    }
    return all;
  }
  function checkBox(plan) {
    var groups = {}, all = knowList(plan);
    all.forEach(function (x) { (groups[x.k] = groups[x.k] || []).push(x.t); });
    var kids = [];
    if ((plan.flags || []).length) kids.push(h("div", { class: "trp-qg" + (viewing(plan) ? "" : " bad") }, [h("h4", { text: viewing(plan) ? changedWords().head : "맞지 않는 것" }), h("ul", { class: "trp-qs" }, plan.flags.map(function (x) { return h("li", { class: "trp-q-flag", text: x }); }))]));
    Object.keys(KLABEL).forEach(function (k) {
      if (groups[k]) kids.push(h("div", { class: "trp-qg" }, [h("h4", { text: KLABEL[k] }), h("ul", { class: "trp-qs" }, groups[k].map(function (x) { return h("li", { text: x }); }))]));
    });
    if (!kids.length) return null;
    return h("details", { class: "trp-box trp-check-c", id: "trp-checks", open: (plan.flags || []).length ? true : null }, [
      h("summary", { class: "trp-box-h" }, [pic("fact-closed"), h("h3", { text: "가기 전에 알아 둘 것" })])].concat(kids));
  }
  function needsTable(plan) {   // the needs the reader picked × the stops: the data's own words in each cell
    if (!plan.needs.length) return null;
    var SYM = { ok: ["✓", "자료 있음"], near: ["△", "근처 주차장"], cond: ["△", "조건부"], no: ["✕", "맞지 않음"], unknown: ["?", "정보 없음"], na: ["–", "해당 없음"] };
    var many = plan.days.length > 1;
    var rows = [];
    plan.days.forEach(function (d, di) {
      d.stops.forEach(function (s, i) {
        var cells = plan.needs.map(function (x) {
          var r = x.rows.filter(function (y) { return y.day === di && y.i === i; })[0] || { state: "na", text: "" };
          var sym = SYM[r.state] || SYM.na;
          var mark = h("span", { class: "trp-nd is-" + r.state }, [h("i", { "aria-hidden": "true", text: sym[0] }), h("span", { text: sym[1] })]);
          return h("td", {}, [r.text ? tooltip(mark, x.label + " — " + s.name + ": " + r.text) : mark]);
        });
        rows.push(h("tr", {}, [h("th", { scope: "row", text: (many ? (di + 1) + "일차 " : "") + (i + 1) + ". " + s.name })].concat(cells)));
      });
    });
    var table = h("table", { class: "trp-ndt" }, [h("thead", {}, [h("tr", {}, [h("th", { scope: "col", text: "장소" })].concat(plan.needs.map(function (x) { return h("th", { scope: "col", text: x.label }); })))]),
      h("tbody", {}, rows)]);
    return h("figure", { class: "trp-chart trp-needs" }, [h("figcaption", {}, [h("b", { text: "필요한 조건, 장소마다" }), h("span", { text: "칸을 누르면 사이트 자료의 내용이 보여요" })]),
      h("div", { class: "trp-ndt-w", "data-lenis-prevent": "" }, [table]),
      h("p", { class: "trp-hint", text: "✓ 자료에 맞는 내용이 있음(출입구 등 일부만 확인된 것일 수 있어요) · △ 자체 주차는 없고 근처 공영주차장 · ✕ 자료상 맞지 않음 · ? 사이트에 정보 없음" })]);
  }
  // ------------------------------------------------------------ the diagrams (operator: '답변을 여러 도식과 함께 화려하게')
  // Every number comes from the plan the server checked: times, roles, legs' straight-line distances, the fee state,
  // the day states. Colours (the dataviz skill's validator, adjacent CVD ΔE 9.1): 관람 sea blue · 식사 orange · 카페
  // aqua · 숙소 yellow, in that fixed order; the margins between places neutral grey. Aqua and yellow sit under 3:1 on
  // white, so every chart keeps visible labels (legend with values) and the stop list below is the table.
  var ROLES = [["visit", "관람", "#2F6FC9"], ["meal", "식사", "#eb6834"], ["cafe", "카페", "#1baf7a"], ["stay", "숙소", "#eda100"]];
  function mins(t) { var m = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; }
  function hm(n) { var hh = Math.floor(n / 60), m = n % 60; return (hh ? hh + "시간" : "") + (m ? (hh ? " " : "") + m + "분" : (hh ? "" : "0분")); }
  function km(m) { return m >= 1000 ? (m / 1000).toFixed(1) + "km" : m + "m"; }
  var tip = null;
  function tooltip(el, text) {
    el.setAttribute("tabindex", "0");
    if (!el.getAttribute("role")) el.setAttribute("role", "img");
    el.setAttribute("aria-label", text);
    var show = function () {
      if (!tip) { tip = h("div", { class: "trp-tip", role: "tooltip" }); doc.body.append(tip); }
      tip.textContent = text;
      tip.hidden = false;
      var r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
      var x = Math.max(8, Math.min(win.innerWidth - t.width - 8, r.left + r.width / 2 - t.width / 2));
      var y = r.top - t.height - 8 < 8 ? r.bottom + 8 : r.top - t.height - 8;
      tip.style.left = Math.round(x + win.scrollX) + "px";
      tip.style.top = Math.round(y + win.scrollY) + "px";
    };
    var hide = function () { if (tip) tip.hidden = true; };
    // a mouse shows it on hover; a finger taps (the tap focuses the mark) and it stays until the focus moves on
    el.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") show(); });
    el.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse" && doc.activeElement !== el) hide(); });
    el.addEventListener("focus", show); el.addEventListener("click", show); el.addEventListener("blur", hide);
    return el;
  }
  function svg(tag, attrs) {
    var el = doc.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }
  function ring(part, whole) {   // a meter as a ring: the filled arc on a lighter track of the same blue
    var r = 26, c = 2 * Math.PI * r, f = whole ? part / whole : 0;
    var s = svg("svg", { viewBox: "0 0 64 64", width: "64", height: "64", class: "trp-ring", "aria-hidden": "true" });
    s.append(svg("circle", { cx: "32", cy: "32", r: String(r), fill: "none", stroke: "#D9E7F8", "stroke-width": "8" }));
    s.append(svg("circle", { cx: "32", cy: "32", r: String(r), fill: "none", stroke: "#2F6FC9", "stroke-width": "8", "stroke-linecap": "round",
      "stroke-dasharray": (c * f).toFixed(1) + " " + c.toFixed(1), transform: "rotate(-90 32 32)" }));
    return s;
  }
  function tile(picId, label, value, note, extra) {
    return h("li", { class: "trp-kpi" }, [h("div", { class: "trp-kpi-h" }, [pic(picId), h("span", { class: "trp-kpi-l", text: label })]),
      h("p", { class: "trp-kpi-v" }, [value]), note ? h("p", { class: "trp-kpi-n", text: note }) : null, extra || null]);
  }
  // the straight lines of the legs added up only when every leg has one (outside evaluation 2026-10-18: '구간 직선거리
  // 합 971m' over three legs of which one had a distance): {legs, known, metres, all}. A start or an end at a station
  // or a terminal is a leg with no distance on the site (review 2026-10-22 movement S1: '2.6km' over a day whose two
  // hub legs were some 35 km each)
  function lineSum(days) {
    var out = { legs: 0, known: 0, metres: 0 };
    days.forEach(function (d) {
      (d.legs || []).forEach(function (l) { out.legs += 1; if (num(l.m)) { out.known += 1; out.metres += l.m; } });
      out.legs += (d.hubs || []).length;
    });
    out.all = out.legs > 0 && out.known === out.legs;
    return out;
  }
  function overview(plan) {
    var cnt = { visit: 0, meal: 0, cafe: 0, stay: 0 }, n = counted(plan), sum = lineSum(plan.days);
    plan.days.forEach(function (d) { d.stops.forEach(function (s) { cnt[s.role] = (cnt[s.role] || 0) + 1; }); });
    var mix = ROLES.filter(function (r) { return cnt[r[0]]; }).map(function (r) { return r[1] + " " + cnt[r[0]]; }).join(" · ");
    var f = plan.fees, head = feeHead(f), meter = null;
    if (num(f.limit) && num(f.known) && f.state !== "none") {
      var pct = f.limit ? Math.min(100, Math.round(f.known / f.limit * 100)) : 100;
      meter = h("div", { class: "trp-meter" + (f.verdict === "over" ? " over" : f.verdict === "open" ? " open" : ""), role: "img",
        "aria-label": "확인된 입장료 " + won(f.known) + " / 예산 " + won(f.limit) + (f.verdict === "open" ? ", 확인 필요가 남아 예산 충족 미확정" : "") }, [h("span", { style: "width:" + pct + "%" })]);
    }
    var ok = n.open;   // as the status row: open by the regular rule at hours that fit (review 2026-10-22 S1)
    var rowCheck = h("div", { class: "trp-kpi-ring" }, [ring(ok, n.all), h("span", { class: "tn", text: ok + "/" + n.all })]);
    return h("ul", { class: "trp-kpis", "aria-label": "코스 요약" }, [
      tile("icon-course", "들르는 곳", h("span", { class: "tn", text: n.all + "곳" }), mix),
      tile("transit-bus", "구간 직선거리 합", !sum.legs ? h("span", { class: "tn", text: "—" }) : sum.all ? h("span", { class: "tn", text: km(sum.metres) })
        : h("span", { class: "trp-kpi-x", text: "전체 이동거리 계산 안 됨" }),
        !sum.legs ? "구간 없음" : sum.all ? "구간 " + sum.legs + "개 · 실제 길 거리·시간 아님" : sum.legs + "개 구간 중 " + sum.known + "개만 거리 있음"),
      tile("plan-budget", "입장료", h("span", { class: "tn", text: head[0] }),
        num(f.limit) ? "예산 " + won(f.limit) + (verdictText(f) ? " · " + verdictText(f) : "") : head[1], meter),
      tile("fact-closed", "정기 규칙상 방문 가능", rowCheck, ringNote(plan, n)),
    ]);
  }
  // what the ring leaves out, said under it: closed, hours that do not fit (a shared plan), the day to check
  function ringNote(plan, n) {
    var bits = [n.closed ? "그날 휴무 " + n.closed + "곳" : "", n.timeBad ? "시간이 맞지 않는 곳 " + n.timeBad + "곳" : "",
      n.dayCheck ? (n.closed || n.timeBad ? "운영 확인 필요 " : "그날 운영 확인 필요 ") + n.dayCheck + "곳" : ""].filter(Boolean);
    if (holidayTableMissing(plan)) bits.push("그해 공휴일 표 없음");
    return bits.length ? bits.join(" · ") : "공휴일·날짜별 공지에 걸리는 곳 없음";
  }
  function timeline(plan) {   // one row per day on a shared clock: stops by role, margins grey, a mark where no time is left
    var lo = 24 * 60, hi = 0;
    plan.days.forEach(function (d) { d.stops.forEach(function (s) { lo = Math.min(lo, mins(s.start)); hi = Math.max(hi, mins(s.end)); }); });
    lo = Math.floor(lo / 60) * 60; hi = Math.ceil(hi / 60) * 60;
    var span = Math.max(60, hi - lo), pct = function (t) { return ((t - lo) / span * 100).toFixed(2) + "%"; };
    var totals = { gap: 0 }, tight = 0;
    var rows = plan.days.map(function (d, di) {
      var track = h("div", { class: "trp-tlx-track" });
      d.stops.forEach(function (s, i) {
        var a = mins(s.start), z = mins(s.end), role = ROLES.filter(function (r) { return r[0] === s.role; })[0] || ROLES[0];
        totals[s.role] = (totals[s.role] || 0) + (z - a);
        var seg = h("span", { class: "trp-seg", style: "left:" + pct(a) + ";width:calc(" + ((z - a) / span * 100).toFixed(2) + "% - 2px);background:" + role[2] },
          [h("span", { class: "trp-seg-n", text: String(i + 1) })]);
        track.append(tooltip(seg, (i + 1) + ". " + s.name + " · " + role[1] + " " + s.start + "~" + s.end + " (" + hm(z - a) + ")"));
        var next = d.stops[i + 1];
        if (next) {
          var g = mins(next.start) - z;
          var leg = (d.legs || []).filter(function (x) { return x.from === i; })[0];
          if (g > 0) {
            totals.gap += g;
            track.append(tooltip(h("span", { class: "trp-seg trp-seg-gap", style: "left:" + pct(z) + ";width:calc(" + (g / span * 100).toFixed(2) + "% - 2px)" }),
              "계획상 여유 " + hm(g) + " (" + s.name + " → " + next.name + ", 이동 시간 확인 안 됨)"));
          }
          if ((g <= 0 && next.path !== s.path) || (leg && leg.flag)) {
            tight += 1;
            track.append(tooltip(h("span", { class: "trp-seg-flag", style: "left:" + pct(z) }, [h("span", { text: "!" })]),
              (leg && leg.flag ? leg.flag : "이동할 틈이 없음") + ": " + s.name + " → " + next.name));
          }
        }
      });
      return h("div", { class: "trp-tlx-row" }, [h("span", { class: "trp-tlx-day", text: (di + 1) + "일차" }), track]);
    });
    var ticks = h("div", { class: "trp-tlx-ticks", "aria-hidden": "true" });
    for (var t = lo; t <= hi; t += 60) {
      if ((t - lo) % (span > 600 ? 120 : 60)) continue;
      ticks.append(h("span", { style: "left:" + pct(t), text: (t / 60) + "시" }));
    }
    var legend = h("ul", { class: "trp-legend" }, ROLES.filter(function (r) { return totals[r[0]]; }).map(function (r) {
      return h("li", {}, [h("i", { style: "background:" + r[2] }), h("span", { text: r[1] + " " + hm(totals[r[0]]) })]);
    }).concat(totals.gap ? [h("li", {}, [h("i", { class: "gap" }), h("span", { text: "계획상 여유 " + hm(totals.gap) })])] : [],
      tight ? [h("li", {}, [h("i", { class: "flag" }), h("span", { text: "이동이 빠듯한 곳 " + tight + "곳" })])] : []));
    return h("figure", { class: "trp-chart trp-tlx" }, [h("figcaption", {}, [h("b", { text: "하루 시간표" }), h("span", { text: "막대에 손가락이나 마우스를 대면 자세히 보여요" })]),
      h("div", { class: "trp-tlx-body", "data-lenis-prevent": "" }, [h("div", { class: "trp-tlx-grid" }, [ticks].concat(rows))]), legend]);
  }
  function metro(day) {   // the day as a line of stations: numbered stops, each link with its distance and how to go
    var line = h("ol", { class: "trp-metro", "aria-label": day.label + " 경로" });
    var hubs = day.hubs || [];
    var hubSt = function (hb) {
      return h("li", { class: "trp-st trp-st-hub" }, [h("span", { class: "trp-st-dot", text: hb.dir === "from" ? "출" : "도" }),
        h("span", { class: "trp-st-n", text: hb.name }), h("span", { class: "trp-st-t tn", text: hb.at })]);
    };
    var hubLink = function () { return h("li", { class: "trp-link trp-link-hub", "aria-label": "이동 거리·시간 모름" }, [h("span", { class: "tn", text: "?" })]); };
    hubs.filter(function (x) { return x.dir === "from"; }).forEach(function (hb) { line.append(hubSt(hb), hubLink()); });
    day.stops.forEach(function (s, i) {
      var role = ROLES.filter(function (r) { return r[0] === s.role; })[0] || ROLES[0];
      line.append(h("li", { class: "trp-st" + (s.day === "closed" ? " closed" : "") }, [
        h("span", { class: "trp-st-dot", style: "--c:" + role[2], text: String(i + 1) }),
        h("span", { class: "trp-st-n", text: s.name }), h("span", { class: "trp-st-t tn", text: s.start })]));
      var l = (day.legs || []).filter(function (x) { return x.from === i; })[0];
      if (l) {
        line.append(h("li", { class: "trp-link" + (l.flag ? " bad" : ""), "aria-label": dist(l.m) + (l.flag ? ", " + l.flag : ", 계획상 여유 " + l.gap + "분") }, [
          pic(l.mode === "car" ? "fact-parking" : l.mode === "walk" ? "sit-walk" : "transit-bus"),
          h("span", { class: "tn", text: num(l.m) ? km(l.m) : "?" })]));
      }
    });
    hubs.filter(function (x) { return x.dir === "to"; }).forEach(function (hb) { line.append(hubLink(), hubSt(hb)); });
    return h("figure", { class: "trp-chart trp-metro-f" }, [h("figcaption", {}, [h("b", { text: "경로 한눈에" }), h("span", { text: "숫자는 직선거리예요" })]),
      h("div", { class: "trp-metro-w", "data-lenis-prevent": "" }, [line])]);
  }
  function legBars(day) {   // each leg's straight-line distance, one blue
    var legs = (day.legs || []).filter(function (l) { return num(l.m); });
    if (!legs.length) return null;
    var max = Math.max.apply(null, legs.map(function (l) { return l.m; })) || 1;
    var rows = legs.map(function (l) {
      var a = day.stops[l.from], b = day.stops[l.to];
      var bar = h("span", { class: "trp-bar" + (l.flag ? " bad" : ""), style: "width:" + Math.max(3, l.m / max * 100).toFixed(1) + "%" });
      return h("li", {}, [h("span", { class: "trp-bar-l", text: (l.from + 1) + "→" + (l.to + 1) }),
        h("span", { class: "trp-bar-t" }, [tooltip(bar, a.name + " → " + b.name + " 직선 " + km(l.m) + (l.flag ? " · " + l.flag : " · 계획상 여유 " + l.gap + "분")),
          h("span", { class: "trp-bar-v tn", text: km(l.m) + (l.flag ? " ⚠" : "") })])]);
    });
    var missing = (day.legs || []).length - legs.length;
    return h("figure", { class: "trp-chart trp-bars" }, [h("figcaption", {}, [h("b", { text: "구간별 직선거리" }), h("span", { text: "실제 이동 시간은 지도 앱에서" })]),
      h("ul", {}, rows), missing ? h("p", { class: "trp-hint", text: "좌표가 없어 거리를 모르는 구간 " + missing + "개는 막대에 없어요." }) : null]);
  }
  // a chart in a box that opens: open from 900px, closed on phones (review 2026-10-17: on a phone the schedule and
  // the map come first, the rest one tap away)
  var wide = win.matchMedia ? win.matchMedia("(min-width: 900px)").matches : true;
  function fold(label, node) {
    if (!node) return null;
    return h("details", { class: "trp-fold", open: wide }, [h("summary", { text: label }), node]);
  }

  // ------------------------------------------------------------ a link that carries the plan (chatbot/plan_share.js)
  // The compact form — the server signs the same (plan_share.compactOf): the conditions without the reader's note
  // (a condition at its default left out), k for a plan the site built itself, e the meals the reader eats elsewhere
  // (the note's or an edit's decision, so the plan reads the same when opened), the words, per day the stops [slug,
  // start, end, role letter, why?].
  var COND_KEYS = ["date", "days", "start", "end", "move", "with", "adults", "seniors", "kids", "from", "to", "prefs", "needs", "budget"];
  var COND_DEFAULT = { seniors: "0", kids: "[]", from: '""', to: '""', prefs: "[]", needs: "[]", budget: "null" };
  var ROLE1 = { visit: "v", meal: "m", cafe: "c", stay: "s" };
  function eatsOf(plan) {
    var meals = ((plan && plan.complete) || {}).meals || [];
    return [["lunch", "l"], ["dinner", "d"]].filter(function (k) {
      return meals.some(function (m) { return m.kind === k[0] && m.state === "skip"; });
    }).map(function (k) { return k[1]; }).join("");
  }
  function compactOf(plan, conditions) {
    var c = plan.conditions || conditions || {}, cond = {};
    COND_KEYS.forEach(function (k) { if (c[k] !== undefined && COND_DEFAULT[k] !== JSON.stringify(c[k])) cond[k] = c[k]; });
    var out = { v: 1, c: cond };
    if (codeBuilt(plan)) out.k = 1;
    if (eatsOf(plan)) out.e = eatsOf(plan);
    out.t = plan.title || "";
    out.s = plan.summary || "";
    out.n = Array.isArray(plan.notes) ? plan.notes : [];
    out.d = plan.days.map(function (d) {
      return d.stops.map(function (s) {
        var m = /^\/places\/([^/?#]+)\/$/.exec(s.path || ""), row = [m ? m[1] : s.path, s.start, s.end, ROLE1[s.role] || "v"];
        if (s.why) row.push(s.why);
        return row;
      });
    });
    return out;
  }
  function b64url(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function unb64url(s) {
    var t = s.replace(/-/g, "+").replace(/_/g, "/");
    while (t.length % 4) t += "=";
    var bin = atob(t), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
    return out;
  }
  // 'z.' + deflate-raw where the browser can (CompressionStream), else 'j.' + the JSON itself
  function pack(obj) {
    var bytes = new TextEncoder().encode(JSON.stringify(obj)), plain = "j." + b64url(bytes);
    if (!win.CompressionStream) return Promise.resolve(plain);
    try {
      var stream = new Blob([bytes]).stream().pipeThrough(new win.CompressionStream("deflate-raw"));
      return new Response(stream).arrayBuffer().then(function (buf) { return "z." + b64url(new Uint8Array(buf)); }, function () { return plain; });
    } catch (e) {
      return Promise.resolve(plain);   // CompressionStream without 'deflate-raw'
    }
  }
  // the compact object of a packed link, or null when this browser cannot inflate it (the server then does). Bounded as
  // the server is (plan_share.SHARE_LIMITS: 16,000 characters packed, 32 KB of JSON): a link past them is refused
  // ({bad: true}) before or while it is inflated — never a whole crafted payload blown up in the reader's tab
  var LINK_CHARS = 16000, LINK_BYTES = 32 * 1024;
  function unpack(packed) {
    if (packed.length > LINK_CHARS) return Promise.reject({ bad: true });
    var bytes = unb64url(packed.slice(2));
    if (packed.charAt(0) === "j") {
      if (bytes.length > LINK_BYTES) return Promise.reject({ bad: true });
      return Promise.resolve(JSON.parse(new TextDecoder().decode(bytes)));
    }
    if (!win.DecompressionStream) return Promise.resolve(null);
    try {
      var reader = new Blob([bytes]).stream().pipeThrough(new win.DecompressionStream("deflate-raw")).getReader();
      var parts = [], size = 0;
      var next = function () {
        return reader.read().then(function (r) {
          if (r.done) {
            var all = new Uint8Array(size), at = 0;
            parts.forEach(function (x) { all.set(x, at); at += x.length; });
            return JSON.parse(new TextDecoder().decode(all));
          }
          size += r.value.length;
          if (size > LINK_BYTES) { reader.cancel().catch(function () { /* gone */ }); throw { bad: true }; }
          parts.push(r.value);
          return next();
        });
      };
      return next().catch(function (e) { if (e && e.bad) throw e; return null; });
    } catch (e) {
      return Promise.resolve(null);
    }
  }
  // the link of the plan on screen, made once per plan (copy and share use it within the reader's tap)
  function linkOf() {
    if (!state || !state.plan) return Promise.reject(new Error("no plan"));
    if (linkCache && linkCache.plan === state.plan && linkCache.sig === (state.sig || null)) return linkCache.p;
    var mine = { plan: state.plan, sig: state.sig || null, url: "" };
    mine.p = pack(compactOf(state.plan, state.conditions)).then(function (p) {
      mine.url = win.location.origin + "/plan/#p=" + p + (mine.sig ? "." + mine.sig : "");
      return mine.url;
    });
    linkCache = mine;
    return mine.p;
  }
  // #p=z.<data>.<sig>: {packed, sig}; a fragment that starts so but is not one: {bad: true}; else null
  // hash: the fragment — the one plan.html.j2's head script took out of the address before the analytics tags could
  // read it (window.__trpLink: on load, and on popstate/hashchange for a link pasted into this tab), else the address's
  function readLink(hash) {
    // (a messenger may keep the sentence's own full stop or bracket on the end of a pasted link)
    hash = String(hash || "").replace(/[^A-Za-z0-9_-]+$/, "");
    if (hash.indexOf("#p=") !== 0) return null;
    var m = /^#p=([zj]\.[A-Za-z0-9_-]+)(?:\.([A-Za-z0-9_-]{43}))?$/.exec(hash);
    return m ? { packed: m[1], sig: m[2] || null } : { bad: true };
  }
  // opening a link: the plan read against today's data by the server (no model call), drawn as a shared plan
  function openShared(link) {
    // the room the course takes is laid out before the page goes to it, a frame apart: the result keeps at least the
    // height it had (a plan drawn before, on a link pasted into this tab) and a screen (.trp-hold) while what is
    // under it is out of sight; then the scroll (round-6 verifier: in one frame, the room growing and the scroll read
    // as the crumbs and the footer pushed out — CLS 0.74–0.91)
    var had = result.hidden ? 0 : result.getBoundingClientRect().height;
    result.hidden = false;
    result.classList.add("trp-hold");
    if (had) result.style.minHeight = had + "px";
    doc.documentElement.classList.remove("trp-holding");
    result.textContent = "";
    result.append(h("div", { class: "wrap trp-opening" }, [h("p", { role: "status", text: "공유받은 코스를 여는 중이에요…" })]));
    win.requestAnimationFrame(function () {
      win.requestAnimationFrame(function () {
        result.scrollIntoView({ block: "start" });
        win.requestAnimationFrame(function () { win.requestAnimationFrame(function () { result.style.minHeight = ""; }); });
      });
    });
    if (link.bad) { sharedFailed(""); return; }
    var p;
    try { p = unpack(link.packed); } catch (e) { p = Promise.resolve(null); }
    p.catch(function (e) { if (e && e.bad) throw e; return null; }).then(function (compact) {
      var view = compact ? { compact: compact } : { packed: link.packed };
      if (link.sig) view.sig = link.sig;
      return fetch(API, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ view: view }) }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (j) { if (!res.ok || j.type !== "view") throw j; return j; });
      });
    }).then(function (v) {
      if (!fits(v.plan)) throw {};
      state = { conditions: v.plan.conditions, plan: v.plan, sig: v.sig || null, diff: null,
        shared: { signed: !!v.signed, words: v.words === undefined ? !!v.signed : !!v.words, past: !!v.past, during: !!v.during, dropped: +v.dropped || 0 } };
      save();
      track("plan_shared_open", { sig: v.signed ? 1 : 0 });
      return getPlaces().then(function () { show(true); });
    }).catch(function (err) { sharedFailed(err && err.code && err.message); });
  }
  function sharedFailed(message) {
    result.hidden = false;
    result.textContent = "";
    var make = h("button", { type: "button", class: "btn", text: "새 코스 만들기" });
    make.addEventListener("click", function () {
      result.hidden = true;
      form.scrollIntoView({ behavior: "smooth" });
      form.querySelector("input,select").focus({ preventScroll: true });
    });
    result.append(h("div", { class: "wrap trp-fail", role: "alert" }, [mascot("sorry"), h("div", {}, [
      h("h2", { id: "h-result", tabindex: "-1", text: "공유받은 코스를 열지 못했어요" }),
      h("p", { text: message || "공유 링크를 읽을 수 없어요. 링크가 잘렸는지 확인하고, 계속 안 되면 보낸 사람에게 다시 받아 주세요." }), make])]));
    result.scrollIntoView({ block: "start" });
    result.querySelector("h2").focus({ preventScroll: true });
  }
  // a shared plan on screen (opened from a link in this tab)
  function viewing(plan) { return !!(state && state.shared && state.plan === plan); }
  // what today's data flags on a shared plan: on a signed link the data that changed since the plan was made; on one
  // not signed (its words could not be confirmed, nor that the site made it) only that it does not fit today's data
  function changedWords() {
    return state.shared && state.shared.signed
      ? { head: "공유된 뒤 자료가 바뀐 곳", status: "공유된 뒤 자료가 바뀐 곳이 있어요", hint: "코스를 만든 뒤 사이트 자료가 바뀌어 오늘 자료로는 맞지 않는 곳이에요. 가기 전에 장소 페이지에서 확인하세요." }
      : { head: "오늘 자료와 맞지 않는 곳", status: "오늘 자료와 맞지 않는 곳이 있어요", hint: "공유받은 순서와 시각을 오늘 사이트 자료로 검사해 맞지 않는 곳을 적었어요. 가기 전에 장소 페이지에서 확인하세요." };
  }
  // the shared plan's own header: '맞는 코스' only when today's data leaves nothing open either (review 2026-10-22
  // S3: a ✓ above five stops '그날 여는지 확인 필요') — what the data does not say is an (i), counted, never a '확인할
  // 것' on top (operator 2026-10-18, above); counted as the plan's own heading counts it — the status rows marked i or !,
  // a year the holiday table lacks among them (operator 2026-10-23: '가기 전 확인 N가지')
  function viewStatus(plan) {
    if ((plan.flags || []).length) return ["info", changedWords().status];
    var n = toCheck(plan);
    return n ? ["info", "오늘 자료와 어긋난 곳 없음 · 가기 전 확인 " + n + "가지"] : ["ok", "오늘 자료로도 맞는 코스예요"];
  }
  function sharedBar() {
    var sh = state.shared;
    var mine = h("button", { type: "button", class: "btn btn-ol trp-early-b", text: "이 조건으로 내 코스 만들기" });
    mine.addEventListener("click", ownCourse);
    var lines = [h("p", { class: "trp-early-t", text: "공유받은 코스예요 · 오늘 자료로 다시 검사했어요" })];
    if (sh.past) lines.push(h("p", { class: "trp-shared-n", text: "이미 지난 날짜의 코스예요" }));
    else if (sh.during) lines.push(h("p", { class: "trp-shared-n", text: "여행 중인 코스예요" }));
    if (!sh.signed) lines.push(h("p", { class: "trp-shared-n", text: "코스를 만들 때의 설명(제목·요약·장소마다의 이유·메모)은 확인할 수 없어 빼고, 사이트 자료로 쓴 제목과 요약을 보여 드려요" }));
    if (sh.dropped) lines.push(h("p", { class: "trp-shared-n", text: "사이트에서 더는 찾을 수 없는 곳 " + sh.dropped + "곳은 뺐어요"
      + (sh.signed ? " · 그 곳을 말하는 설명이 있을 수 있어 사이트 자료로 쓴 제목과 요약을 보여 드려요" : "") }));
    return h("div", { class: "trp-early trp-shared is-info" }, [h("span", { class: "trp-early-m", "aria-hidden": "true", text: "i" }),
      h("div", { class: "trp-shared-in", id: "trp-line", role: "status" }, lines), h("span", { class: "trp-early-a" }, [mine])]);
  }
  // '이 조건으로 내 코스 만들기': the shared conditions in the form (a date gone by stays the form's own, said so)
  function ownCourse() {
    var c = state.conditions;
    applying = true;
    try { setForm(c); } finally { applying = false; }
    var sh = state.shared || {};
    var past = !c.date || c.date < dateIn.min || sh.past || sh.during;
    if (past && dateIn.value === c.date) { dateIn.value = iso(sat); summary(); }
    formErr.hidden = !past;
    formErr.textContent = !past ? "" : sh.during && !sh.past ? "공유받은 코스는 이미 시작한 여행이에요. 날짜를 다시 골라 주세요."
      : "공유받은 코스의 날짜는 이미 지났어요. 날짜를 다시 골라 주세요.";
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    (past ? dateIn : form.querySelector(".trp-submit")).focus({ preventScroll: true });
  }

  // ------------------------------------------------------------ keeping and passing the plan on
  // the plan as text: copy, share, a saved file, the printed page — a draft still unmet says so on its first line, so
  // a copy passed on is never read as a finished itinerary
  function planText(plan, c) {
    var view = viewing(plan);
    var L = [(plan.status === "unmet" && !view ? "[수정이 필요한 초안] " : "") + plan.title, "", plan.summary, "", "조건: " + describe(c),
      "상태: " + headOf(plan)[1]];
    var done = completeLine(plan);
    if (done) L.push("일정 완성도: " + done[1]);
    var sum = lineSum(plan.days);
    if (sum.legs) L.push("구간 직선거리: " + (sum.all ? "합 " + km(sum.metres) + "(실제 길 거리·시간 아님)" : "전체 이동거리 계산 안 됨(" + sum.legs + "개 구간 중 " + sum.known + "개만 거리 있음)"));
    L.push("만든 때: " + new Date(plan.made || Date.now()).toLocaleString("ko-KR"), "");
    plan.days.forEach(function (d) {
      L.push("■ " + d.label);
      (d.hubs || []).filter(function (x) { return x.dir === "from"; }).forEach(function (hb) { L.push("  " + hb.at + " " + hb.name + " 출발 (길찾기 " + hb.url + hubGuideText(hb) + ")"); });
      d.stops.forEach(function (s, i) {
        L.push("  " + s.start + "~" + s.end + " " + (i + 1) + ". " + s.name + " [" + (LABEL.role[s.role] || "") + " · " + LABEL.day[dayShown(s)]
          + (codeBuilt(plan) ? "" : s.added ? " · 사이트가 넣음" : s.swapped ? " · " + swapWords(s, true) : "") + "] " + SITE + encodeURI(s.path));
        if (s.outside) L.push("     관람: " + outsideText(s.outside));
        (s.checks || []).forEach(function (x) { L.push("     확인: " + x); });
        var l = (d.legs || []).filter(function (x) { return x.from === i; })[0];
        if (l) L.push("     → " + (dist(l.m) || "거리 모름") + " · 계획상 여유 " + Math.max(0, l.gap) + "분" + (l.url ? " · 길찾기 " + l.url : ""));
      });
      (d.hubs || []).filter(function (x) { return x.dir === "to"; }).forEach(function (hb) { L.push("  " + hb.at + "까지 " + hb.name + " (길찾기 " + hb.url + hubGuideText(hb) + ")"); });
      L.push("");
    });
    var f = plan.fees, head = feeHead(f);
    L.push("입장료: " + head[0] + " — " + head[1] + (verdictText(f) ? " · " + verdictText(f) : ""));
    if ((plan.flags || []).length) { L.push("", view ? changedWords().head + ":" : "맞지 않는 것:"); plan.flags.forEach(function (x) { L.push("- " + x); }); }
    var know = knowList(plan);
    if (know.length) { L.push("", "가기 전에 알아 둘 것:"); know.forEach(function (x) { L.push("- " + x.t); }); }
    if ((plan.notes || []).length) { L.push("", "메모(AI):"); plan.notes.forEach(function (x) { L.push("- " + x); }); }
    var here = (NAME || "이 사이트") + "(" + SITE + "/plan/)";
    L.push("", (view ? "공유받은 코스를 " + here + " 오늘 자료로 다시 검사했어요."
      : codeBuilt(plan) ? codeLine(plan) + ". " + here + " 자료로 검사했어요."
      : "AI(Claude)가 고른 일정을 " + here + " 자료로 검사했어요.") + " 장소 정보의 출처는 각 장소 페이지에 있어요. 실제 운영·이동 시간·예약은 장소와 지도 앱에서 확인하세요.");
    return L.join("\n");
  }
  function exportBar(plan, c) {
    var msg = h("p", { class: "trp-x-msg", role: "status" });
    var say = function (t) { msg.textContent = t; };
    var text = function () { return planText(plan, c); };
    var b = function (label, how, fn) {
      var el = h("button", { type: "button", class: "btn btn-ol trp-x", text: label });
      el.addEventListener("click", function () { track("plan_export", { how: how }); fn(); });
      return el;
    };
    var copy = b("일정 복사", "copy", function () {
      var done = function () { say("일정을 복사했어요. 메시지나 메모에 붙여 넣으세요."); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text()).then(done, function () { say("복사하지 못했어요. 파일로 저장해 주세요."); });
      else say("이 브라우저는 복사를 지원하지 않아요. 파일로 저장해 주세요.");
    });
    // the share sheet's text carries the plan's link (made when the plan was drawn, so the sheet opens within the tap)
    var share = navigator.share ? b("공유", "share", function () {
      var go = function (url) {
        navigator.share({ title: plan.title, text: text() + (url ? "\n\n코스 링크(열면 이 코스가 보여요): " + url : "") }).catch(function () { /* closed */ });
      };
      if (linkCache && linkCache.plan === plan && linkCache.url) go(linkCache.url);
      else linkOf().then(go, function () { go(""); });
    }) : null;
    // a link a companion opens on their own phone: the plan in the address, nothing stored (chatbot/plan_share.js)
    var link = h("button", { type: "button", class: "btn btn-ol trp-x trp-x-link", text: "링크 복사" });
    var field = null;
    link.addEventListener("click", function () {
      track("plan_share", { how: "link" });
      var put = function (url) {   // no clipboard: the link in a field to copy by hand
        if (!field) {
          field = h("input", { type: "text", class: "trp-x-url", readonly: true, "aria-label": "코스 링크" });
          field.addEventListener("focus", function () { field.select(); });
          msg.after(field);
        }
        field.value = url;
        say("아래 링크를 길게 눌러 복사하세요.");
        field.focus();
      };
      linkOf().then(function (url) {
        var done = function () { say("링크를 복사했어요. 동행이 열면 자기 휴대폰에서 이 코스를 볼 수 있어요."); };
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done, function () { put(url); });
        else put(url);
      }, function () { say("링크를 만들지 못했어요. 일정 복사나 파일 저장을 써 주세요."); });
    });
    var save = b("파일로 저장", "file", function () {
      var blob = new Blob([text()], { type: "text/plain;charset=utf-8" });
      var a = h("a", { href: URL.createObjectURL(blob), download: (NAME ? NAME + "-" : "") + "코스-" + c.date + ".txt" });
      doc.body.append(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
      say("텍스트 파일로 저장했어요.");
    });
    var print = b("인쇄·PDF", "print", function () { win.print(); });
    return h("div", { class: "trp-x-bar" }, [h("div", { class: "trp-x-row", role: "group", "aria-label": "일정 보관·전달" }, [link, copy, share, save, print]), msg,
      h("p", { class: "trp-hint", text: "일정은 이 탭에만 있어요. '링크 복사'로 보내면 동행의 휴대폰에서도 이 코스가 열려요 — 코스는 링크에만 담기고 서버에 저장하지 않으며, 하고 싶은 말은 넣지 않아요." })]);
  }
  // what an edit changed: stops, times, the fee state, the plan's status — and what the server says of the request
  // itself (planner 'edited', [{k, t}]: an edit asking for fewer admissions says the fees before and after, or why they
  // stayed — outside test 2026-10-23: '입장료 줄이기' came back '장소와 시각은 그대로예요' under a '무료' title)
  // A stop's own button (planner actOn, k 'act'): its lines come first and say every place put in or taken out, so the
  // page's own '추가'·'뺌' lines are left to them — the times that moved are still the page's.
  function diffPlans(a, b) {
    var out = [];
    var acts = (Array.isArray(b.edited) ? b.edited : []).filter(function (x) { return x && x.k === "act" && typeof x.t === "string" && x.t; });
    b.days.forEach(function (d, i) {
      var was = (a.days[i] || { stops: [] }).stops, now = d.stops;
      var key = function (s) { return s.path; };
      var wasKeys = was.map(key), nowKeys = now.map(key);
      if (!acts.length) {
        now.forEach(function (s) { if (wasKeys.indexOf(s.path) < 0) out.push((i + 1) + "일차: " + s.name + " 추가(" + s.start + "~" + s.end + ")"); });
        was.forEach(function (s) { if (nowKeys.indexOf(s.path) < 0) out.push((i + 1) + "일차: " + s.name + " 뺌"); });
      }
      now.forEach(function (s) {
        var o = was.filter(function (x) { return x.path === s.path; })[0];
        if (o && (o.start !== s.start || o.end !== s.end)) out.push((i + 1) + "일차: " + s.name + " " + o.start + "~" + o.end + " → " + s.start + "~" + s.end);
      });
    });
    var said = (Array.isArray(b.edited) ? b.edited : []).filter(function (x) { return x && x.k !== "act" && typeof x.t === "string" && x.t; });
    if ((said.length || acts.length) && !out.length && !acts.some(function (x) { return /뺐어요|바꿨어요|넣었어요/.test(x.t); })) out.push("장소와 시각은 그대로예요.");
    out = acts.map(function (x) { return x.t; }).concat(out);
    said.forEach(function (x) { out.push(x.t); });
    var fa = feeHead(a.fees)[0], fb = feeHead(b.fees)[0];
    // (the server's fee line has the same numbers: said once)
    if (fa !== fb && !said.some(function (x) { return x.k === "fee"; })) out.push("입장료: " + fa + " → " + fb);
    // (a change of status, in the words of the headings the reader saw — a shared plan's own, when it was one)
    var sa = (STATUS[a.status] || STATUS.ready)[1], sb = (STATUS[b.status] || STATUS.ready)[1];
    if (sa !== sb) out.push("상태: " + headOf(a)[1] + " → " + headOf(b, true)[1]);
    return out.length ? out : ["장소와 시각은 그대로예요."];
  }
  // an edit: the plan on screen and the change asked for. The stops go with their role and reason: the server hands
  // them over as they are, so the stops the change keeps are copied, not read and written again (operator
  // 2026-10-17: an edit took too long). false when there is nothing to send.
  // With them goes the plan's compact form without its stops and its signature (base): the server keeps the reasons
  // only when that signature proves them its own (plan_share.baseValid) — a reader cannot have it sign words they wrote.
  // The pinned stops (고정) ride with it — with a stop's own button too (sendAct) — for the server to keep on their day.
  // A rainy day's outdoor place the reader asked for goes with its mark (the server's asked: true), so the next edit
  // keeps it too (review 2026-10-23).
  function editBody(req) {
    var compact = { days: state.plan.days.map(function (d) { return { date: d.date, stops: d.stops.map(function (s) {
      var o = { page: s.path, start: s.start, end: s.end, role: s.role, why: s.why || "" };
      if (s.asked === true) o.asked = true;
      return o; }) }; }) };
    var body = { conditions: state.conditions, plan: compact };
    if (req) body.request = req;
    if (state.sig) {
      var cp = compactOf(state.plan, state.conditions);
      body.base = { k: cp.k, e: cp.e, t: cp.t, s: cp.s, n: cp.n, sig: state.sig };
    }
    var pins = (state.pins || []).map(function (k) { var i = k.indexOf("|"); return { day: +k.slice(0, i), page: k.slice(i + 1) }; });
    if (pins.length) body.pins = pins;
    return body;
  }
  function sendEdit(req) {
    if (!req || !state || !state.plan) return false;
    ask(editBody(req), state.conditions, true);
    return true;
  }
  function editBox() {
    var ta = h("textarea", { id: "trp-ask", rows: "2", maxlength: "300", placeholder: "예: 둘째 날 비가 온대요. 실내 위주로, 주차하기 편한 곳으로 바꿔 주세요." });
    var go = h("button", { type: "submit", class: "btn" }, [pic("plan-swap"), h("span", { text: "이렇게 바꾸기" })]);
    var f = h("form", { class: "trp-edit-f" }, [h("label", { for: "trp-ask", class: "vh", text: "바꾸고 싶은 점" }), ta, go]);
    var quick = h("div", { class: "trp-qes", role: "group", "aria-label": "빠르게 바꾸기" });
    var tq = doc.getElementById("trp-quick");
    if (tq) Array.prototype.forEach.call(tq.content.children, function (b) {
      var c = b.cloneNode(true);
      c.addEventListener("click", function () { ta.value = c.getAttribute("data-ask"); ta.focus(); });
      quick.append(c);
    });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!sendEdit(ta.value.trim())) ta.focus();
    });
    return h("section", { class: "trp-edit", "aria-labelledby": "h-edit" }, [
      h("div", { class: "trp-edit-h" }, [mascot("rain"), h("div", {}, [h("h3", { id: "h-edit", text: "바꾸고 싶은 점이 있나요?" }),
        h("p", { text: "말로 적으면 조건은 그대로 두고 그 부분만 다시 짜요. 날짜·인원·예산을 바꾸려면 위에서 조건을 다시 골라 주세요." })])]), quick, f]);
  }

  // ------------------------------------------------------------ drawing it
  function draw(focus) {
    var plan = state.plan, c = state.conditions, view = viewing(plan);
    result.textContent = "";
    result.hidden = false;
    if (curDay >= plan.days.length || curDay < 0) curDay = 0;   // a plan with fewer days than the tab shown before
    // over the course: the line of the course sent first, or of a shared plan
    var top = view ? sharedBar() : syncBar();
    // the summary is the AI's only when the AI wrote it: not on a plan the site built, not on a shared plan whose
    // signature did not check out (the server put the code's own summary there)
    var siteWords = codeBuilt(plan) || (view && !state.shared.words);
    var head = h("header", { class: "trp-r-head" }, [h("span", { class: "trp-r-art" }, [mascot("done")]), h("div", { class: "trp-r-t" }, [
      h("p", { class: "trp-eyebrow" }, [h("span", { text: view ? "공유받은 코스 · 오늘 사이트 자료와 코드로 다시 검사함"
        : plan.status === "unmet" ? "AI가 고른 초안 · 사이트 자료와 코드로 검사함"
        : codeBuilt(plan) ? "사이트 자료로 짜고 코드로 검사한 코스" : "AI가 짜고 사이트 자료와 코드로 검사한 코스" })]),
      // (the line over the course describes it: its words were on the page before they could be read out as a change,
      // so the heading the focus goes to carries them — round-6 verifier: '공유받은 코스예요 …' went unheard)
      h("h2", { id: "h-result", tabindex: "-1", "aria-describedby": top ? "trp-line" : null, text: plan.title }),
      codeBuilt(plan) ? h("p", { class: "trp-r-code" }, [h("span", { class: "trp-site", text: "사이트" }), " " + codeLine(plan)]) : null,
      plan.summary ? h("p", { class: "trp-r-sum" }, [siteWords ? h("span", { class: "trp-site", text: "사이트" }) : h("span", { class: "trp-ai", text: "AI" }), " " + plan.summary]) : null,
      h("p", { class: "trp-r-cond", text: describe(c) })])]);
    // a shared plan that today's data flags: what changed since it was made (a signed link), or what does not fit
    // today's data (one not signed) — a neutral notice, never a draft
    var cw = view ? changedWords() : null;
    var changed = view && (plan.flags || []).length ? h("section", { class: "trp-changed", "aria-labelledby": "h-changed" }, [
      h("h3", { id: "h-changed", text: cw.head }), h("ul", {}, plan.flags.map(function (x) { return h("li", { text: x }); })),
      h("p", { class: "trp-hint", text: cw.hint })]) : null;
    var diff = state.diff ? h("section", { class: "trp-diff", "aria-labelledby": "h-diff" }, [
      h("h3", { id: "h-diff", text: state.phase === "swapped" ? "먼저 보여 드린 코스와 달라진 것" : "바꾼 뒤 달라진 것" }),
      h("ul", {}, state.diff.map(function (x) { return h("li", { text: x }); }))]) : null;
    var again = h("button", { type: "button", class: "btn btn-ol", text: "조건 다시 고르기" });
    again.addEventListener("click", function () { form.scrollIntoView({ behavior: "smooth" }); form.querySelector("input,select").focus({ preventScroll: true }); });
    var tabs = null;
    if (plan.days.length > 1) {
      tabs = h("div", { class: "trp-days", role: "tablist", "aria-label": "일차" });
      plan.days.forEach(function (d, i) {
        var b = h("button", { type: "button", role: "tab", id: "trp-tab-" + i, "aria-selected": String(i === curDay), "aria-controls": "trp-day-" + i,
          tabindex: i === curDay ? "0" : "-1", text: d.label });
        b.addEventListener("click", function () { curDay = i; draw(false); doc.getElementById("trp-tab-" + i).focus(); });
        b.addEventListener("keydown", function (e) {
          var k = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
          if (!k) return;
          curDay = (i + k + plan.days.length) % plan.days.length;
          draw(false);
          doc.getElementById("trp-tab-" + curDay).focus();
        });
        tabs.append(b);
      });
    }
    var day = plan.days[curDay];
    var tl = h("ol", { class: "trp-tl" });
    (day.hubs || []).filter(function (x) { return x.dir === "from"; }).forEach(function (hb) { tl.append(hubRow(hb)); });
    day.stops.forEach(function (s, i) {
      tl.append(stopCard(s, i + 1, curDay, day));
      var l = (day.legs || []).filter(function (x) { return x.from === i; })[0];
      if (l) tl.append(legRow(l, c.move));
    });
    (day.hubs || []).filter(function (x) { return x.dir === "to"; }).forEach(function (hb) { tl.append(hubRow(hb)); });
    var panel = h("div", { class: "trp-grid", id: "trp-day-" + curDay, role: tabs ? "tabpanel" : null, "aria-labelledby": tabs ? "trp-tab-" + curDay : null }, [
      h("div", { class: "trp-main" }, [h("h3", { class: "trp-day-h", text: day.label }), fold("경로 한눈에 보기", metro(day)), legNote(day), tl]),
      h("aside", { class: "trp-side" }, [dayMap(day), fold("구간별 직선거리 보기", legBars(day)), feeCard(plan.fees), checkBox(plan)])]);
    var notes = (plan.notes || []).length ? h("ul", { class: "trp-notes" }, plan.notes.map(function (n) { return h("li", {}, [h("span", { class: "trp-ai", text: "AI" }), " " + n]); })) : null;
    var glance = h("section", { class: "trp-glance", "aria-labelledby": "h-glance" }, [h("h3", { id: "h-glance", text: "한눈에 보는 코스" }),
      overview(plan), fold("하루 시간표 보기", timeline(plan)), fold("필요한 조건 표 보기", needsTable(plan))]);
    var printed = h("pre", { class: "trp-print", "aria-hidden": "true", text: planText(plan, c) });
    result.append(h("div", { class: "wrap" }, [top, head, changed, statusPanel(plan), diff, h("div", { class: "trp-r-acts" }, [exportBar(plan, c), again]), glance, tabs, panel, notes,
      view && (state.shared.past || state.shared.during) ? null : editBox(),
      h("p", { class: "trp-foot", text: view ? "공유받은 순서와 시각을 오늘의 사이트 자료로 휴무·운영시간·입장마감·입장료·조건까지 다시 검사했지만, 그날의 실제 운영·이동 시간·예약은 각 장소와 지도 앱에서 확인하세요. 장소 사진: 한국관광공사."
        : (codeBuilt(plan) ? "사이트 자료로 고른" : "AI가 고른") + " 순서와 시각을 이 사이트 자료로 휴무·운영시간·입장마감·입장료·조건까지 검사했지만, 그날의 실제 운영·이동 시간·예약은 각 장소와 지도 앱에서 확인하세요. 장소 사진: 한국관광공사." }), printed]));
    result.classList.remove("trp-hold");   // the course is in the room held for it (openShared, a reload)
    linkOf().catch(function () { /* made again on the tap */ });   // ready before the reader taps 링크 복사 or 공유
    if (focus) {
      // the working view above goes first: scrolled to with it still there, the course's top would land a screen
      // above the window once it went (it goes in the same frame — the course is drawn where it stays)
      work.hidden = true;
      result.scrollIntoView({ behavior: "smooth", block: "start" });
      result.querySelector("#h-result").focus({ preventScroll: true });
    }
  }
  function show(focus) {   // a plan that cannot be drawn is let go; the conditions stay in the form
    try {
      draw(focus);
    } catch (e) {
      var c = state && state.conditions;
      state = c ? { conditions: c, plan: null } : null;
      save();
      failed("일정을 그리지 못했어요. 같은 조건으로 다시 만들어 주세요.", { conditions: c }, c, false);
    }
  }

  // conditions handed over in the address start from the form's defaults — never from the conditions or the plan this
  // tab kept, which is not shown under them —, are kept for this tab without a plan and leave the address, so a
  // reload comes back to them (and to the plan made from them); never sent by themselves. The reader lands on the
  // form (review 2026-10-18, fourth round: the hand-over opened on the page's top, the filled form out of sight): a
  // line above it says where the values came from — a status region (plan.html.j2), empty until its words come, so
  // it is read out; its room is there from the first paint (html.trp-handing), so nothing moves — and the form comes
  // into view under it. A plain visit has neither. Otherwise a plan made
  // earlier in this tab comes back with its conditions in the form.
  // A share link (#p=…) comes first: the fragment leaves the address at once (a reload shows this tab's state, the
  // shared plan once it is read) and the plan is read against today's data by the server.
  var handed = false, linked = readLink(win.__trpLink || win.location.hash);
  win.__trpLink = null;
  if (linked) {
    doc.documentElement.classList.remove("trp-handing");
    try { win.history.replaceState(win.history.state, "", win.location.pathname + win.location.search); } catch (e) { /* the address stays */ }
    openShared(linked);
  } else {
    try { handed = fromAddress(); } catch (e) { /* the form stays as it is */ }
  }
  // a link opened in a tab already on /plan/ changes only the fragment: no reload, so it is read here — the head's
  // first script has already taken it out of the address on popstate (window.__trpLink), before any tag's listener
  win.addEventListener("hashchange", function () {
    var next = readLink(win.__trpLink || win.location.hash);
    win.__trpLink = null;
    if (!next) return;
    if (ctrl) ctrl.abort();
    hideToast();
    try { win.history.replaceState(win.history.state, "", win.location.pathname + win.location.search); } catch (e) { /* the address stays */ }
    openShared(next);
  });
  if (linked) {
    /* the shared plan is on its way */
  } else if (handed) {
    root.setAttribute("data-prefilled", "");
    state = { conditions: conditions(), plan: null };
    save();
    try { win.history.replaceState(win.history.state, "", win.location.pathname + win.location.hash); } catch (e) { /* the address stays */ }
    var said = root.querySelector("[data-plan-handed]"), saidBox = said && said.closest(".trp-handed-w");
    doc.documentElement.classList.add("trp-handing");
    // the words for a date carried or none (the head script chose the same from the address, so the room fits them)
    var undated = !dateIn.value;
    doc.documentElement.classList.toggle("trp-undated", undated);
    if (said) setTimeout(function () {
      said.textContent = saidBox.querySelector(".trp-handed-ghost [data-" + (undated ? "undated" : "dated") + "]").textContent;
      saidBox.scrollIntoView({ block: "start" });
    }, 60);
  } else {
    doc.documentElement.classList.remove("trp-handing", "trp-undated");   // keys the form has no choice for: no line, no room
    var kept = load(), holding = doc.documentElement.classList.contains("trp-holding");
    // a shared plan comes back as it was opened, a date gone by too (its conditions go to the form only on '이 조건으로
    // 내 코스 만들기'); a course still being refined when the tab was reloaded stays as the course sent first; a
    // hand-over that carried no date comes back with the date still empty (no plan yet)
    var undatedHandOver = kept && kept.conditions && kept.conditions.date === "" && !kept.plan && !kept.shared;
    if (kept && kept.conditions && (kept.conditions.date >= iso(today) || (kept.shared && fits(kept.plan)) || undatedHandOver)) {
      if (!kept.shared) { try { setForm(kept.conditions); } catch (e) { /* the defaults stay */ } }
      if (fits(kept.plan)) {
        if (kept.phase === "wait") { kept.phase = "cut"; state = kept; save(); }
        if (kept.early && !fits(kept.early.plan)) { delete kept.early; delete kept.final; delete kept.phase; }
        state = kept;
        // the room plan.html.j2 held from the first paint stays the result's until the course is drawn in it; then
        // the reader is put back where they were (the browser's own restoring is off on this page)
        result.hidden = false;
        result.classList.add("trp-hold");
        doc.documentElement.classList.remove("trp-holding");
        getPlaces().then(function () {
          show(false);
          var y = 0;
          try { y = +win.sessionStorage.getItem(KEY + "-y") || 0; } catch (e) { /* private mode */ }
          // a frame after the course is drawn, not in the same one: what the drawing moved (out of sight) and the
          // scroll that brings it into sight in one frame would read as a layout shift
          if (y > 0) win.requestAnimationFrame(function () { win.requestAnimationFrame(function () { win.scrollTo(0, y); }); });
        });
      } else {
        state = { conditions: kept.conditions, plan: null };
        // a course the tab had but could not keep (save: lost) or cannot draw (an older shape): said, with the
        // conditions on the form and the way to make it again — never a bare form as if nothing had been made (UX05)
        if (kept.lost || kept.plan) lostNote(!!kept.lost);
      }
    }
    if (holding) doc.documentElement.classList.remove("trp-holding");
  }
})();
