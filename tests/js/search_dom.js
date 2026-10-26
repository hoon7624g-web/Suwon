// templates/assets/search.js in Node: the script runs in a vm context with the few DOM objects it uses (the form with
// its data attributes, the box, the results, the help, the directory) and a fetch that answers the index. One context
// per (script, page, index); search(q) submits the form and reads what the script wrote into [data-results]: the rows
// found (hits: the links of section.res-g), the related guides (related: section.res-rel), the 'also searched' line
// (syn) and the planner's line (plan). The pages and indexes are a build's (search/index.html, search/index.json).
import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";

// the data-* attributes of the page's form[data-search] (HTML-unescaped) and its <html lang>
export function pageForm(html) {
  const form = html.match(/<form\b[^>]*\bdata-search\b[^>]*>/);
  if (!form) throw new Error("no form[data-search]");
  const attrs = {};
  for (const m of form[0].matchAll(/\s(data-[a-z-]+)(?:="([^"]*)")?/g)) attrs[m[1]] = unescape(m[2] || "");
  const lang = (html.match(/<html[^>]*\slang="([^"]+)"/) || [])[1] || "ko";
  return { attrs, lang };
}

function unescape(s) {
  return s.replace(/&(?:(amp|lt|gt|quot|apos)|#(\d+)|#x([0-9a-f]+));/gi, (_, n, d, x) =>
    n ? { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" }[n] : String.fromCodePoint(d ? +d : parseInt(x, 16)));
}

// a built site's search pages: [{code, dir, attrs, lang, rows (the index as JSON text)}] for the Korean page and each
// version that has one
export function sitePages(root, codes) {
  return codes.map((code) => {
    const dir = code === "ko" ? path.join(root, "search") : path.join(root, code, "search");
    const { attrs, lang } = pageForm(readFileSync(path.join(dir, "index.html"), "utf8"));
    return { code, dir, attrs, lang, rows: readFileSync(path.join(dir, "index.json"), "utf8") };
  });
}

function element(attrs = {}) {
  const on = {};
  return {
    hidden: false, innerHTML: "", value: "", on,
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    setAttribute: (k, v) => { attrs[k] = String(v); },
    addEventListener: (type, fn) => { (on[type] = on[type] || []).push(fn); },
    querySelector: () => null,
    focus() {},
  };
}

// source: the script's text; attrs: the form's data-* attributes; rows: the index (JSON text); limit: replaces the
// script's LIMIT (the rows shown), so a comparison sees every row found
export function loadSearch(source, { attrs, rows, lang = "ko", limit } = {}) {
  let code = source;
  if (limit) {
    code = code.replace(/\bLIMIT = \d+/, `LIMIT = ${limit}`);
    if (code === source) throw new Error("no LIMIT in the script");
  }
  const input = element({ name: "q" });
  const form = element({ ...attrs });
  form.querySelector = (sel) => (sel.includes("input") ? input : null);
  const out = element(), dir = element(), help = element();
  const chat = element({ "data-chat-q": "" }), all = element();
  help.querySelector = (sel) => (sel.includes("chat-q") ? chat : sel.includes("show-all") ? all : null);
  const els = { "[data-search]": form, "[data-results]": out, "[data-directory]": dir, "[data-none-help]": help };
  const document = {
    documentElement: { lang },
    querySelector: (sel) => els[sel] || null,
    getElementById: () => null,
  };
  const ctx = {
    document, URLSearchParams, console,
    location: { search: "", pathname: "/search/" },
    history: { replaceState() {} },
    fetch: () => Promise.resolve({ json: () => Promise.resolve(JSON.parse(rows)) }),
  };
  vm.runInNewContext(code, ctx);
  const submit = form.on.submit && form.on.submit[0];
  if (!submit) throw new Error("the script did not listen to the form");
  return {
    async search(q) {
      input.value = q;
      out.innerHTML = "";
      submit({ preventDefault() {} });
      for (let i = 0; i < 20 && !out.innerHTML && q.trim(); i++) await new Promise((r) => setImmediate(r));
      return read(out.innerHTML);
    },
  };
}

function links(html) {
  return [...html.matchAll(/<a href="([^"]*)"/g)].map((m) => unescape(m[1]));
}

// what a search wrote: hits (the rows found, in order), related (the related guides), syn, plan, none, the HTML
export function read(html) {
  const hits = [], related = [];
  for (const m of html.matchAll(/<section class="res-g( res-rel)?">([\s\S]*?)<\/section>/g)) {
    (m[1] ? related : hits).push(...links(m[2]));
  }
  return {
    html, hits, related,
    syn: (html.match(/<p class="res-syn">([^<]*)<\/p>/) || [])[1] || "",
    plan: /class="res-plan"/.test(html),
    none: /class="res-none"/.test(html),
  };
}
