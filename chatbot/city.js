// The city's own values the course planner reads — docs.json meta.plan (pipeline/plan.py plan_meta, from
// data/<city>/site.json `plan`) and the region's name (meta.region): read once by each Knowledge as it loads
// (knowledge.js: one deployment serves one city), then read by chatbot/plan_*.js and knowledge.js checkPlan. Nothing of
// a city is written in chatbot/*.js: where a trip may start and end (hubs, each with the travel area it is in), the
// 좋아하는 것 choices and the words the model reads for them, the residents' label of the combined tickets, the travel
// areas a leg into or out of needs a longer margin (far), the likings read by travel area (pref_regions) or by the
// city's own type labels (pref_types), the site's bus guidance for a hub's leg (hub_guides), whether a leg without a
// car must be a walk or a bus route the data names (transit_strict), and the city's own lines for the planner's rules.
const KEY = /^[a-z0-9][a-z0-9-]{0,30}$/;
const text = (v) => (typeof v === "string" ? v.trim() : "");
const words = (o) => Object.fromEntries(Object.entries(o && typeof o === "object" ? o : {})
  .filter(([k, v]) => typeof k === "string" && typeof v === "string" && v.trim()).map(([k, v]) => [k, v.trim()]));
const list = (v) => (Array.isArray(v) ? v.map(text).filter(Boolean) : []);
const minutes = (v) => (Number.isInteger(v) && v >= 0 && v <= 600 ? v : null);

/** meta.plan, checked: {hubs {key: {name, path?, g? [lat, lng], region?}}, prefs {key: words}, resident, far {area:
 *  {car, transit}}, prefRegions {pref: [areas]}, prefTypes {pref: [type labels]}, hubGuides [{hub?, region?, path,
 *  label}], transitStrict, rules [lines]} — what cannot be used is left out; missing values are empty, never another
 *  city's. */
export function readPlan(p) {
  const o = p && typeof p === "object" ? p : {};
  const hubs = {};
  for (const [k, h] of Object.entries(o.hubs && typeof o.hubs === "object" ? o.hubs : {})) {
    if (!KEY.test(k) || !h || !text(h.name)) continue;
    const g = Array.isArray(h.g) && h.g.length === 2 && h.g.every((x) => typeof x === "number" && Number.isFinite(x)) ? h.g : null;
    hubs[k] = { name: text(h.name), ...(typeof h.path === "string" && h.path.startsWith("/") ? { path: h.path } : {}),
      ...(g ? { g } : {}), ...(text(h.region) ? { region: text(h.region) } : {}) };
  }
  const prefs = {};
  for (const [k, v] of Object.entries(o.prefs && typeof o.prefs === "object" ? o.prefs : {})) {
    if (KEY.test(k) && text(v)) prefs[k] = text(v);
  }
  const far = {};
  for (const [area, v] of Object.entries(o.far && typeof o.far === "object" ? o.far : {})) {
    const car = minutes(v && v.car), transit = minutes(v && v.transit);
    if (text(area) && car !== null && transit !== null) far[text(area)] = { car, transit };
  }
  const byKey = (raw) => Object.fromEntries(Object.entries(raw && typeof raw === "object" ? raw : {})
    .filter(([k]) => KEY.test(k)).map(([k, v]) => [k, list(v)]).filter(([, v]) => v.length));
  const hubGuides = (Array.isArray(o.hub_guides) ? o.hub_guides : [])
    .filter((x) => x && typeof x.path === "string" && x.path.startsWith("/") && text(x.label))
    .map((x) => ({ path: x.path, label: text(x.label), ...(text(x.hub) ? { hub: text(x.hub) } : {}), ...(text(x.region) ? { region: text(x.region) } : {}) }));
  return { hubs, prefs, resident: text(o.resident), far, prefRegions: byKey(o.pref_regions), prefTypes: byKey(o.pref_types),
    hubGuides, transitStrict: o.transit_strict === true, rules: list(o.rules) };
}

let CITY = { site: "", siteName: "", siteNameEn: "", region: "", regionEn: "", ...readPlan({}) };

/** Read by Knowledge as it loads: the city of this deployment (meta = knowledge.readMeta's: {site, siteName,
 *  siteNameEn, region {lang: name}, plan}). Returns it. */
export function useCity(meta) {
  const m = meta && typeof meta === "object" ? meta : {};
  const region = m.region && typeof m.region === "object" ? m.region : {};
  CITY = { site: text(m.site), siteName: text(m.siteName), siteNameEn: text(m.siteNameEn), region: text(region.ko),
    regionEn: text(region.en), ...(m.plan && m.plan.hubs ? m.plan : readPlan(m.plan)) };
  return CITY;
}
/** The city the planner reads now (useCity's). */
export const city = () => CITY;
/** A hub's name by its key ('' for none). */
export const hubName = (key) => ((key && CITY.hubs[key]) || {}).name || "";
/** {key: name} of the city's hubs. */
export const hubNames = () => Object.fromEntries(Object.entries(CITY.hubs).map(([k, h]) => [k, h.name]));
/** '<region> ' for a title ('' when the meta names none). */
export const regionWord = () => (CITY.region ? `${CITY.region} ` : "");
