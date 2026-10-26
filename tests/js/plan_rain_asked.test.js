// A rain edit keeps the outdoor place the reader asked for (operator 2026-10-23): on a '비 와도 실내 위주' trip,
// '히로쓰가옥도 넣어 줘' — or '월명공원 넣어 줘' on a day that starts at 진포해양공원 — came back 'ready' with an indoor place
// in the asked place's stead (settle 2: a rainy day keeps one outdoor visit, the first; the asked place came later).
// Now the outdoor visits the reader did not ask for go first (all of them when one was asked for), the ones asked for
// stay and do not count against the one (plan_build.rainAsked — a place new to the edit, s.asked, and on a later edit
// the reader's own page when it already keeps more than one), and a day that keeps more than one because every one
// was asked for says so once: '비 오는 날 야외 장소 n곳 — 요청대로 두었어요(…)' in what the edit changed and in
// '가기 전에 알아 둘 것'. A new plan, and an edit that asks for no outdoor place, are as before.
// The places are the first city's own (tests/fixtures/first_city_kb.json, from its public/chat); the model is a fake that hands the same
// submit_plan over on every call.
import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { firstCityKb } from "./first_city.js";
import { buildDay, planFlags, rainAsked } from "../../chatbot/plan_build.js";
import { isOutdoor } from "../../chatbot/plan_geo.js";
import { editPlaces, makePlan, validConditions, validEdit, verify, viewPlan } from "../../chatbot/planner.js";
import { compactOf, signCompact } from "../../chatbot/plan_share.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
// (the first city's places: tests/fixtures/first_city_kb.json, its build's knowledge cut to the planner's fields)
const KB = firstCityKb();
const NOW = new Date("2026-10-23T01:00:00Z");   // 2026-10-23 (Fri) 10:00 KST
const P = (name) => {
  const k = KB.keys.find((x) => x.startsWith("/places/") && KB.docs[x].t === name);
  if (!k) throw new Error(`no place ${name}`);
  return k;
};
const HIRO = "군산신흥동일본식가옥(히로쓰가옥)", PARK = "진포해양공원", HILL = "월명공원", LAKE = "은파호수공원";
const out = (s) => isOutdoor((KB.docs[s.path || s.page] || {}).f || {});
const usage = { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
function client(input, calls = []) {
  return { messages: { stream(params) {
    calls.push(structuredClone(params.messages));
    const message = { role: "assistant", content: [{ type: "tool_use", id: `toolu_${calls.length}`, name: "submit_plan", input: structuredClone(input) }], stop_reason: "tool_use", usage };
    return { async *[Symbol.asyncIterator]() {}, async finalMessage() { return message; } };
  } } };
}
const S = (name, start, end, role = "visit") => ({ page: P(name), start, end, role, why: "" });
// a rainy Tuesday without a car, 10:00–18:00
const RAW = { date: "2026-10-27", days: 1, start: "10:00", end: "18:00", move: "transit", with: "couple", adults: 2, seniors: 0, kids: [],
  from: "", to: "", prefs: ["history"], needs: ["rain"], budget: null, note: "" };
// the reader's day: 진포해양공원 at 10:00 (자연·야외 — the day's one outdoor visit), then indoors and a lunch
const DAY = [S(PARK, "10:00", "10:50"), S("근대역사박물관", "11:10", "12:30"), S("한일옥", "12:45", "13:45", "meal"),
  S("테디베어박물관", "14:10", "15:40"), S("초원사진관", "16:00", "16:40")];
// the page's edit body (plan.js sendEdit): a stop's mark of an outdoor place asked for on a rainy day goes with it
const pageOf = (plan) => ({ days: plan.days.map((d) => ({ date: d.date, stops: d.stops.map((s) => ({ page: s.path, start: s.start, end: s.end, role: s.role, why: s.why,
  ...(s.asked === true ? { asked: true } : {}) })) })) });
const names = (plan) => plan.days.flatMap((d) => d.stops.map((s) => s.name));

async function newPlan(stops, raw = RAW, days = null) {
  const c = validConditions(raw, NOW);
  const sent = [];
  await makePlan({ client: client({ title: "비 오는 화요일", summary: "", notes: [], days: days || [{ date: c.date, stops }] }), kb: KB, conditions: c,
    send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.ok(plan, JSON.stringify(sent.at(-1)).slice(0, 400));
  return { plan, c };
}
/** The reader's plan on the page, then the edit `request` with a model that hands back `back(the page's days)`. */
async function editOf(before, c, request, back) {
  const page = pageOf(before);
  const edit = validEdit(structuredClone(page), request, c);
  editPlaces(edit, KB);
  const calls = [];
  const sent = [];
  await makePlan({ client: client({ title: "비 오는 화요일", summary: "", notes: [], days: back(structuredClone(page.days)) }, calls), kb: KB,
    conditions: c, edit, send: (e) => sent.push(e), now: NOW });
  const plan = sent.at(-1).plan;
  assert.ok(plan, JSON.stringify(sent.at(-1)).slice(0, 400));
  return { plan, calls, edit };
}
const ready = (plan) => {
  assert.equal(plan.status, "ready");
  assert.deepEqual(plan.flags, []);
};
const rainLines = (plan) => [...(plan.edited || []).filter((x) => x.k === "rain"), ...plan.aware.filter((x) => /요청대로 두었어요/u.test(x.t))];

test("the reader's day: a rainy Tuesday with one outdoor visit, finished as it is", async () => {
  const { plan } = await newPlan(DAY);
  ready(plan);
  assert.deepEqual(names(plan), [PARK, "근대역사박물관", "한일옥", "테디베어박물관", "초원사진관"]);
  assert.equal(plan.days[0].stops.filter(out).length, 1);
});

test("'히로쓰가옥도 넣어 줘': the asked place stays, the outdoor stop the reader did not ask for becomes an indoor one", async () => {
  const { plan: before, c } = await newPlan(DAY);
  const { plan, calls } = await editOf(before, c, "히로쓰가옥도 넣어 줘", (ds) => {
    const st = ds[0].stops;
    st.splice(4, 0, S(HIRO, "15:55", "16:35"));
    Object.assign(st[5], { start: "16:50", end: "17:30" });
    return ds;
  });
  ready(plan);
  const hiro = plan.days[0].stops.find((s) => s.name === HIRO);
  assert.ok(hiro, names(plan).join(", "));
  assert.deepEqual([hiro.start, hiro.end], ["15:55", "16:35"]);
  assert.ok(!names(plan).includes(PARK), names(plan).join(", "));
  const first = plan.days[0].stops[0];
  assert.equal(first.swapped, "other");
  assert.equal(out(first), false, first.name);
  assert.deepEqual(plan.days[0].stops.filter(out).map((s) => s.name), [HIRO]);
  // one outdoor visit left: nothing kept past the rule, nothing to say of it
  assert.deepEqual(rainLines(plan), []);
  assert.ok(plan.fixed.some((t) => t.startsWith(`${PARK}: 비 오는 날 야외는 하루 한 곳까지라 가까운 `)), plan.fixed.join("\n"));
  // the model was told which to keep (before: '— 짧은 야외는 하루 한 곳까지', and it was the asked place that went)
  const told = JSON.stringify(calls[1].at(-1));
  assert.ok(told.includes(`독자가 요청한 곳(${HIRO})은 두고, 그 밖의 야외 장소(${PARK})는 실내 장소로 바꾼다`), told);
});

test("진포해양공원 at 10:00, then '월명공원 넣어 줘': 월명공원 stays where the model put it", async () => {
  const { plan: before, c } = await newPlan(DAY);
  const { plan } = await editOf(before, c, "월명공원 넣어 줘", (ds) => { ds[0].stops.push(S(HILL, "16:55", "17:40")); return ds; });
  ready(plan);
  const hill = plan.days[0].stops.find((s) => s.name === HILL);
  assert.ok(hill, names(plan).join(", "));
  assert.deepEqual([hill.start, hill.end], ["16:55", "17:40"]);
  assert.ok(!names(plan).includes(PARK));
  assert.deepEqual(plan.days[0].stops.filter(out).map((s) => s.name), [HILL]);
  assert.deepEqual(rainLines(plan), []);
});

test("two outdoor places asked for: both stay, the day says so once — and a later edit keeps them", async () => {
  const { plan: before, c } = await newPlan(DAY);
  const { plan } = await editOf(before, c, "월명공원이랑 은파호수공원 넣어 줘", (ds) => {
    ds[0].stops.splice(4, 1, S(HILL, "16:00", "16:40"), S(LAKE, "17:05", "17:45"));
    return ds;
  });
  ready(plan);
  assert.deepEqual(plan.days[0].stops.filter(out).map((s) => s.name), [HILL, LAKE]);
  assert.ok(!names(plan).includes(PARK));
  const line = `비 오는 날 야외 장소 2곳 — 요청대로 두었어요(${HILL}·${LAKE})`;
  assert.deepEqual(plan.edited, [{ k: "rain", t: line }]);
  assert.deepEqual(plan.aware.filter((x) => x.t === line), [{ k: "need", t: line }]);
  // the needs table still says what each is
  assert.deepEqual(plan.needs.find((n) => n.key === "rain").rows.filter((r) => r.state === "no").map((r) => r.name), [HILL, LAKE]);
  // the next edit (nothing outdoor asked for): the reader's page keeps more than one outdoor visit, so they were
  // asked for before — they stay, said in '가기 전에 알아 둘 것' only
  const { plan: next } = await editOf(plan, c, "조금만 다듬어 주세요", (ds) => ds);
  ready(next);
  assert.deepEqual(next.days[0].stops.filter(out).map((s) => s.name), [HILL, LAKE]);
  assert.deepEqual(next.days[0].stops.map((s) => [s.name, s.start, s.end]), plan.days[0].stops.map((s) => [s.name, s.start, s.end]));
  assert.equal(next.edited, undefined);
  assert.deepEqual(next.aware.filter((x) => x.t === line), [{ k: "need", t: line }]);
});

test("the check and the day builder read the same: asked outdoor places are not flagged and stay in a rebuilt day", async () => {
  const { plan: before, c } = await newPlan(DAY);
  const page = pageOf(before);
  const edit = validEdit(structuredClone(page), "월명공원이랑 은파호수공원 넣어 줘", c);
  editPlaces(edit, KB);
  const asked = (name, start, end) => ({ ...S(name, start, end), name, asked: P(name) });
  const own = (name, start, end, role = "visit") => ({ ...S(name, start, end, role), name });
  const day = { date: c.date, stops: [own(PARK, "10:00", "10:50"), own("근대역사박물관", "11:10", "12:30"), own("한일옥", "12:45", "13:45", "meal"),
    own("테디베어박물관", "14:10", "15:40"), asked(HILL, "16:00", "16:40"), asked(LAKE, "17:05", "17:45")] };
  const plan = { title: "t", summary: "", notes: [], days: [day] };
  const flag = planFlags(plan, c, KB, edit).list.filter((x) => x.kind === "rain");
  assert.equal(flag.length, 1);   // 진포해양공원 was not asked for
  assert.match(flag[0].text, new RegExp(`독자가 요청한 곳\\(${HILL}·${LAKE}\\)은 두고, 그 밖의 야외 장소\\(${PARK}\\)는 실내 장소로 바꾼다$`, "u"));
  const ask = rainAsked(KB, edit, 0);
  assert.deepEqual(day.stops.map((s) => ask(s)), [false, false, false, false, true, true]);
  // the day built again around its stops keeps the asked places and lets the other outdoor one go
  const built = buildDay(c, KB, 0, c.date, { seed: day.stops, edit, plan });
  assert.ok(built, "a day around the seeds");
  const kept = built.stops.filter((s) => out(s)).map((s) => s.name);
  assert.deepEqual(kept, [HILL, LAKE]);
  // without the park: nothing flagged, and verify says the day keeps them as asked
  day.stops.shift();
  assert.deepEqual(planFlags(plan, c, KB, edit).list.filter((x) => x.kind === "rain"), []);
  assert.ok(verify(plan, c, KB, edit).aware.some((x) => x.t === `비 오는 날 야외 장소 2곳 — 요청대로 두었어요(${HILL}·${LAKE})`));
  // the same day not as an edit (no place asked for): flagged as before, the first outdoor visit the one kept
  const bare = { ...plan, days: [{ date: c.date, stops: day.stops.map(({ asked: _, ...s }) => s) }] };
  const was = planFlags(bare, c, KB).list.filter((x) => x.kind === "rain");
  assert.deepEqual(was.map((x) => x.text), [`1일차: '비 와도 실내 위주'인데 야외 장소가 2곳(${HILL}·${LAKE}) — 짧은 야외는 하루 한 곳까지`]);
  const rebuilt = buildDay(c, KB, 0, c.date, { seed: bare.days[0].stops, plan: bare });
  assert.ok(rebuilt);
  assert.deepEqual(rebuilt.stops.filter((s) => out(s)).map((s) => s.name), [HILL]);
});

test("as before: a new rain plan keeps its first outdoor visit, and an edit that asks for no outdoor place changes nothing of the rule", async () => {
  // the model's new plan with two outdoor visits: the later one becomes an indoor place (no place is asked for)
  const two = [...DAY.slice(0, 4), S(HILL, "16:00", "16:40")];
  const { plan, c } = await newPlan(two);
  ready(plan);
  assert.equal(names(plan)[0], PARK);
  assert.ok(!names(plan).includes(HILL), names(plan).join(", "));
  assert.deepEqual(plan.days[0].stops.filter(out).map((s) => s.name), [PARK]);
  assert.ok(plan.fixed.some((t) => t.startsWith(`${HILL}: 비 오는 날 야외는 하루 한 곳까지라 가까운 `)), plan.fixed.join("\n"));
  assert.deepEqual(rainLines(plan), []);
  // an edit asking for no outdoor place (an indoor one for 초원사진관): 진포해양공원 stays the day's one outdoor visit
  const { plan: base } = await newPlan(DAY);
  const { plan: edited } = await editOf(base, c, "초원사진관 대신 실내로 바꿔 주세요", (ds) => {
    ds[0].stops[4] = S("군산항1981", "16:00", "16:40");
    return ds;
  });
  ready(edited);
  assert.deepEqual(names(edited), [PARK, "근대역사박물관", "한일옥", "테디베어박물관", "군산항1981"]);
  assert.deepEqual(rainLines(edited), []);
  // the same plan sent back unchanged: unchanged
  const { plan: same } = await editOf(base, c, "그대로 두세요", (ds) => ds);
  assert.deepEqual(same.days[0].stops.map((s) => [s.path, s.start, s.end]), base.days[0].stops.map((s) => [s.path, s.start, s.end]));
});

test("two days: the line names its day, and only the day whose outdoor places were asked for keeps them", async () => {
  const raw = { ...RAW, days: 2, date: "2026-10-27" };
  const c = validConditions(raw, NOW);
  const day2 = [S("근대역사박물관", "10:00", "11:30"), S("한일옥", "12:00", "13:00", "meal"), S("테디베어박물관", "13:30", "15:00"),
    S("초원사진관", "15:20", "16:00")];
  const { plan: before } = await newPlan(null, raw, [
    { date: "2026-10-27", stops: [...DAY, S("군산스테이 관광호텔", "20:00", "21:00", "stay")] },
    { date: "2026-10-28", stops: day2 }]);
  const { plan } = await editOf(before, c, "둘째 날에 월명공원이랑 은파호수공원 넣어 줘", (ds) => {
    ds[1].stops.splice(3, 1, S(HILL, "15:20", "16:00"), S(LAKE, "16:25", "17:05"));
    return ds;
  });
  ready(plan);
  assert.deepEqual(plan.days[1].stops.filter(out).map((s) => s.name), [HILL, LAKE]);
  assert.deepEqual(plan.days[0].stops.filter(out).map((s) => s.name), before.days[0].stops.filter(out).map((s) => s.name));
  assert.deepEqual(plan.edited, [{ k: "rain", t: `2일차 비 오는 날 야외 장소 2곳 — 요청대로 두었어요(${HILL}·${LAKE})` }]);
});

// review 2026-10-23: the asked place of one edit was the next edit's 'outdoor place not asked for' — '월명공원 넣어 줘'
// then '은파호수공원도 넣어 줘' swapped 월명공원 for 군산문화원 ('비 오는 날 야외는 하루 한 곳까지라'), the complaint again.
// The plan sent marks a rainy day's asked outdoor visit (asked: true); the page sends the mark back with its next edit.
test("one edit after another: the outdoor place asked for first stays when the next edit asks for another", async () => {
  const { plan: before, c } = await newPlan(DAY);
  assert.ok(before.days[0].stops.every((s) => s.asked === undefined), "a new plan marks nothing");
  const { plan: first } = await editOf(before, c, "월명공원 넣어 줘", (ds) => { ds[0].stops.push(S(HILL, "16:55", "17:40")); return ds; });
  ready(first);
  assert.deepEqual(first.days[0].stops.filter((s) => s.asked).map((s) => [s.name, s.asked]), [[HILL, true]]);
  // the mark rides with the edit (validEdit keeps it: true only)
  const page = pageOf(first);
  assert.equal(validEdit(structuredClone(page), "x", c).plan.days[0].stops.find((s) => s.page === P(HILL)).asked, true);
  const forged = structuredClone(page);
  forged.days[0].stops[0].asked = "yes";
  assert.equal(Object.hasOwn(validEdit(forged, "x", c).plan.days[0].stops[0], "asked"), false);
  const { plan: second, calls } = await editOf(first, c, "은파호수공원도 넣어 줘", (ds) => {
    const st = ds[0].stops;
    st.splice(st.findIndex((s) => s.page === P("초원사진관")), 1, S(LAKE, "16:00", "16:40"));
    return ds;
  });
  ready(second);
  // the model is told too (rule 6: a place 지금 일정 marks so stays)
  const said = calls[0][0].content;
  assert.ok(said.includes(`${P(HILL)} (role visit) [앞서 독자가 요청한 야외 장소] why:`), said);
  assert.equal(said.split("[앞서 독자가 요청한 야외 장소]").length, 2);
  assert.deepEqual(second.days[0].stops.filter(out).map((s) => s.name), [LAKE, HILL]);
  assert.ok(!second.fixed.some((t) => t.includes("비 오는 날 야외는 하루 한 곳까지라")), second.fixed.join("\n"));
  const line = `비 오는 날 야외 장소 2곳 — 요청대로 두었어요(${LAKE}·${HILL})`;
  assert.deepEqual(second.edited, [{ k: "rain", t: line }]);
  assert.deepEqual(second.days[0].stops.filter((s) => s.asked).map((s) => s.name), [LAKE, HILL]);
  // the reader takes one out: no request is lost (the mark is not 'new to the edit'), the other stays
  const { plan: third } = await editOf(second, c, "월명공원은 빼 주세요", (ds) => {
    ds[0].stops = ds[0].stops.filter((s) => s.page !== P(HILL));
    return ds;
  });
  ready(third);
  assert.ok(!names(third).includes(HILL));
  assert.deepEqual(third.days[0].stops.filter(out).map((s) => [s.name, s.asked]), [[LAKE, true]]);
  assert.deepEqual(rainLines(third), []);
});

// review 2026-10-23: a plan that keeps two asked outdoor places opened from its link as '공유된 뒤 자료가 바뀐 곳이 있어요'
// with the rain rule's line — the link has no mark, but a signed plan with more than one outdoor visit on a rainy day
// can only have come from requests (rainAsked reads it as the page before an edit); a link not signed is checked as is
test("a shared link of a rainy day that keeps the outdoor places asked for opens as it was made", async () => {
  const { plan: before, c } = await newPlan(DAY);
  const { plan } = await editOf(before, c, "월명공원이랑 은파호수공원 넣어 줘", (ds) => {
    ds[0].stops.splice(4, 1, S(HILL, "16:00", "16:40"), S(LAKE, "17:05", "17:45"));
    return ds;
  });
  ready(plan);
  const key = Buffer.from("rain-asked-share-key");
  const cp = compactOf(plan);
  const r = viewPlan({ compact: cp, sig: signCompact(cp, key) }, KB, NOW, key);
  assert.equal(r.signed, true);
  ready(r.plan);
  const line = `비 오는 날 야외 장소 2곳 — 요청대로 두었어요(${HILL}·${LAKE})`;
  assert.deepEqual(r.plan.aware.filter((x) => x.t === line), [{ k: "need", t: line }]);
  // not signed: what does not fit today's rule is said, as before
  const u = viewPlan({ compact: cp, sig: "x" }, KB, NOW, key);
  assert.equal(u.signed, false);
  assert.deepEqual(u.plan.flags, [`1일차: '비 와도 실내 위주'인데 야외 장소가 2곳(${HILL}·${LAKE}) — 짧은 야외는 하루 한 곳까지`]);
  // a signed link of a day with one outdoor visit: nothing to say of the rain either way
  const one = compactOf(before);
  const v = viewPlan({ compact: one, sig: signCompact(one, key) }, KB, NOW, key);
  ready(v.plan);
  assert.ok(!v.plan.aware.some((x) => /요청대로 두었어요/u.test(x.t)));
});
