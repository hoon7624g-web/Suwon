// The first city's values (the Gunsan site the engine came from), as its docs.json meta would carry them — for the
// planner tests brought over from that site (tests/js/plan*.test.js, engine_*, review_r8_*): their places, hubs,
// travel areas and likes are that city's, and nothing of a city is written in chatbot/*.js (city.js reads it all from
// the meta), so each of those tests builds its knowledge base with this meta (Knowledge below). The meta is the
// first city's site.json plan as its own engine had it in code (plan_prompt.HUBS / PREFS, plan_state.HUB_REGION,
// knowledge.ISLAND_FLOOR / ISLAND_AREAS, plan_geo.HUB_GUIDES).
import { readFileSync } from "node:fs";

import { useCity } from "../../chatbot/city.js";
import { Knowledge as Base, loadKnowledge as baseLoad, readMeta } from "../../chatbot/knowledge.js";

export const FIRST_SITE = "https://gunsan.webforai.kr";
export const FIRST_META = {
  site: FIRST_SITE, site_name: "군산각", site_name_en: "Gunsangak",
  region: { ko: "군산", en: "Gunsan" }, assistant: { ko: "군산 여행 도우미", en: "Gunsan travel helper" },
  origins: [], tel: ["112", "119", "1330"],
  plan: {
    hubs: { station: { name: "군산역", region: "금강" }, bus: { name: "군산시외버스터미널", region: "원도심" },
      express: { name: "군산고속버스터미널", region: "원도심" }, airport: { name: "군산공항", region: "은파" } },
    prefs: { history: "역사·문화(근대 건물·박물관)", food: "맛집", islands: "섬·바다", nature: "자연·힐링(공원·호수)",
      alleys: "골목 산책", cafe: "카페·빵집", experience: "체험", night: "야경", photo: "사진 명소" },
    resident: "군산시민",
    far: { 고군산: { car: 60, transit: 120 } },
    pref_regions: { islands: ["고군산", "섬"] },
    hub_guides: [
      { region: "고군산", path: "/guides/군산-시내버스-관광지/#h-b6", label: "99번 버스(섬) 안내" },
      { hub: "airport", path: "/guides/군산-시외버스-고속버스-공항/#h-b6", label: "공항 버스·택시 안내" },
      { region: "새만금·비응", path: "/guides/군산-시내버스-관광지/#h-b5", label: "비응항 버스 안내" },
      { hub: "station", region: "원도심", path: "/guides/군산-가는-법-교통/#h-b6", label: "군산역↔원도심 버스 안내" },
      { region: "원도심", path: "/guides/군산-시내버스-관광지/#h-b2", label: "근대역사박물관 버스 안내" },
      { path: "/guides/군산-시내버스-관광지/", label: "시내버스 노선 안내" },
    ],
  },
};
export const HUBS = Object.fromEntries(Object.entries(FIRST_META.plan.hubs).map(([k, h]) => [k, h.name]));
export const HUB_REGION = Object.fromEntries(Object.entries(FIRST_META.plan.hubs).map(([k, h]) => [k, h.region]));
export const ISLAND_FLOOR = FIRST_META.plan.far.고군산;
// (the city of a test that reads the conditions before it builds a knowledge base: the first city's, as the knowledge
// would read it)
useCity(readMeta(FIRST_META));

/** The engine's Knowledge with the first city's meta when the docs carry none. */
export class Knowledge extends Base {
  constructor(o = {}) {
    const docs = o.docs && typeof o.docs === "object" ? o.docs : {};
    super({ ...o, docs: { ...docs, meta: docs.meta || FIRST_META } });
  }
}
/** loadKnowledge with the first city's meta (a directory of that city's knowledge). */
export async function loadKnowledge(dir) {
  const k = await baseLoad(dir);
  return new Knowledge({ catalog: k.catalog, docs: { site: FIRST_SITE, docs: { ...k.docs }, alias: { ...k.alias }, ext: [...k.ext.values()], tickets: k.tickets }, index: { v: 1, docs: {} } });
}
/** The first city's knowledge base for the planner (tests/fixtures/first_city_kb.json: its build's places cut to the
 *  planner's fields, and its guides' first lines). */
export function firstCityKb() {
  const fx = JSON.parse(readFileSync(new URL("../fixtures/first_city_kb.json", import.meta.url), "utf8"));
  return new Knowledge({ catalog: "# catalog", docs: { v: 1, site: fx.site, docs: fx.docs, alias: {}, ext: [], tickets: fx.tickets }, index: { v: 1, docs: {} } });
}
