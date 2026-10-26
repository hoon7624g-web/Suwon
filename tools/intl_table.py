"""Translation tables for the language versions: every Korean text a version shows is translated from a table a
translator wrote — nothing is filled by sound (romanization, katakana, Cyrillic) in place of a translation
(CLAUDE.md 3절 1·5항). A unit missing from the table stops the run; it is never left out or romanized.

    python tools/intl_table.py extract --data data/<city> --lang <code> [--all] [--out todo.json]
    python tools/intl_table.py fill    --data data/<city> --lang <code> answers.json [...]
    python tools/intl_table.py apply   --data data/<city> --lang <code> --work <dir> [--merge]
    python tools/intl_table.py report  --data data/<city> [--lang <code> ...] [--json]

The table: data/<city>/<code>/table.json
    {"units": {<Korean unit>: <translation>}, "names": {<Korean name>: <name in the language>},
     "proper": [<Korean word the translation writes by its sound on purpose: a mountain, a dish, a brand>]}

Units (the same Korean units for every language, so a unit is translated once per language):
- prose (summaries, FAQ, details, the text of guides, courses and events) is cut into sentences, a value into lines;
- inside a unit the record's own name is {name}, another place or area of this city named in it {m1} {m2} …, each
  won amount {w1} …, each clock time {t1} …, each phone number {p1} …. The tool puts them back in the language's
  form (the place names of this version, Locale.money, two-digit hours), so '{name}은 매주 월요일에 쉽니다.' is
  translated once for every place. A translation keeps every placeholder of its unit.
- a unit with no Hangul ('09:00–18:00', a phone) is the value itself, ranges with an en dash and two-digit hours.
- a place's name in this version: the official TourAPI name of the language (names --lang of tools/en_content.py),
  else "names" (English: data/<city>/en/names.json, tools/en_names.py). An area (동·읍·면·리) named in a text: "names"
  (English: its romanized form, pipeline.romanize). An address without the romanized candidate (floors, building
  names): a unit, the same romanized text in every language (en_content rules.address).

extract lists the units the table lacks (with an id, the hash of the unit); fill adds a translator's answers
({id: translation}) to the table. apply builds the translation batches of tools/en_content.py prepare (the same items
and ko_hash) from the table: a missing unit or name stops it (exit 1, the list printed and written to
<work>/<code>-missing.json). The filled batches must pass tools/en_content.py check (parity, style, script) and the
sound check below; with --merge they are merged into data/<city>/<code>/ (en_content merge) and the strings rows the
version lacks are added to its strings.json.

Sound check (translit, pipeline/intl_check.py): a Korean word of a unit written by its sound — Revised Romanization
('Juchajang' for 주차장) in the Latin-script versions and Chinese, katakana in Japanese, Kontsevich Cyrillic in
Russian — is a finding unless the word is in "proper". Names are masked before the check, so a place name may keep
its romanized form. report counts those words per version in the stored records (a whole record against its Korean
record) and strings rows, with the records that are stale or missing. With site.json intl.require_complete the build
and validate fail on any of these (pipeline/en_site.completeness_problems, pipeline/validate.py): a version is never
built with a value left out or a name filled by its sound in place of its translation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import locales as LC
from pipeline.city import of as city_of
from pipeline.en_source import _admin, _load, current_hashes
from pipeline.romanize import HANGUL, romanize
from pipeline.intl_check import KINDS, SLOT, TRAIL_LABEL, forms_of, load_table, mask_names, report, translit  # noqa: F401
from pipeline.textutil import extract_phones, squash_ws
from tools import en_content as ec

KO_SENT = re.compile(r"(?<=[다요까죠][.?!])\s+|(?<=[?!])\s+")
TIME = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
RANGE = re.compile(r"[~∼～〜]")


# ------------------------------------------------------------------ the table
def table_path(data: Path, code: str) -> Path:
    return data / code / "table.json"


def save_table(data: Path, code: str, table: dict) -> None:
    out = {"units": dict(sorted(table["units"].items())), "names": dict(sorted(table["names"].items())),
           "proper": sorted(set(table["proper"]))}
    table_path(data, code).parent.mkdir(parents=True, exist_ok=True)
    table_path(data, code).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")


def uid(kind: str, ko: str) -> str:
    return hashlib.sha1(f"{kind}␟{ko}".encode("utf-8")).hexdigest()[:7]


# ------------------------------------------------------------------ cutting and masking
def sentences_ko(text: str) -> list[str]:
    return [s for s in (x.strip() for x in KO_SENT.split(squash_ws(text))) if s]


def lines(text: str) -> list[str]:
    return [x.strip() for x in str(text or "").split("\n")]


def norm_plain(text: str) -> str:
    """A unit with no Hangul as every version writes it: ranges with an en dash, hours with two digits."""
    t = RANGE.sub("–", text)
    return TIME.sub(lambda m: f"{int(m.group(1)):02d}:{m.group(2)}", t)


class Masker:
    """Masks one record's units: its own name, the names it mentions, phones, won amounts, clock times."""

    def __init__(self, own: list[str], mentions: list[str]):
        self.own = sorted({squash_ws(n) for n in own if squash_ws(n)}, key=len, reverse=True)
        self.mentions = [squash_ws(m) for m in mentions if squash_ws(m)]

    def mask(self, text: str) -> tuple[str, dict]:
        slots: dict[str, tuple[str, str]] = {}
        t = squash_ws(text)
        if not HANGUL.search(t):
            return t, slots
        names = [(n, "name") for n in self.own] + [(m, "m") for m in self.mentions]
        names.sort(key=lambda x: len(x[0]), reverse=True)
        marks: dict[str, str] = {}
        for n, typ in names:
            if n not in t:
                continue
            if typ == "name":
                key = "name"
            else:
                key = marks.get(n) or f"m{sum(1 for k in slots if k.startswith('m')) + 1}"
                marks[n] = key
            slots[key] = ("name", n)
            t = t.replace(n, "" + key + "")
        n_p = 0
        for ph in extract_phones(t):
            if ph in t:
                n_p += 1
                slots[f"p{n_p}"] = ("phone", ph)
                t = t.replace(ph, "" + f"p{n_p}" + "")
        t = ec._ko_big(t)
        counter = {"w": 0, "t": 0}

        def won(m: re.Match) -> str:
            counter["w"] += 1
            k = f"w{counter['w']}"
            slots[k] = ("won", ec._ko_won(m.group(1)))
            return "" + k + ""

        t = ec.WON_KO.sub(won, t)

        def clock(m: re.Match) -> str:
            counter["t"] += 1
            k = f"t{counter['t']}"
            slots[k] = ("time", f"{int(m.group(1)):02d}:{m.group(2)}")
            return "" + k + ""

        t = TIME.sub(clock, t)
        return t.replace("", "{").replace("", "}"), slots


# ------------------------------------------------------------------ one version
class Version:
    """The table and the names of one language version, and the batches prepare writes for it."""

    def __init__(self, data: Path, code: str, work: Path):
        self.data, self.code, self.work = data, code, work
        self.loc = LC.get(code) if code != "en" else None
        self.table = load_table(data, code)
        self.en_table = load_table(data, "en") if code != "en" else self.table
        self.city = city_of(_load(data, "site.json", {}))
        work.mkdir(parents=True, exist_ok=True)
        ec.DATA = data
        self.prep = ec.prepare(work, 1000, data, code)
        self.batches = [json.loads(Path(b["file"]).read_text("utf-8")) for b in self.prep["batches"]]
        self.missing: dict[str, dict] = {}
        self.findings: list[str] = []
        self.used: set[str] = set()
        # the words a translation may write by their sound: the table's "proper" and every place's name
        self.proper = set(self.table["proper"])
        for p in _load(data, "places.json", []) or []:
            for n in [p.get("name"), *(p.get("alternate_names") or [])]:
                self.proper |= set(re.findall(r"[가-힣]{2,}", str(n or "")))
        # every place's name in this version, by its Korean name (for the names a text mentions)
        self.place_names: dict[str, str] = {}
        key = "name_en" if code == "en" else self.loc.name_key
        for b in self.batches:
            if b["type"] == "places":
                for it in b["items"]:
                    nm = squash_ws(it.get(key)) or (self.table["names"].get(it["name"]) if code != "en" else "")
                    if code == "en" and it.get("name_en_source") == "romanized":   # not a translated name
                        nm = self.table["names"].get(it["name"], "")
                    if nm:
                        for n in [it["name"], *(it.get("alternate_names") or [])]:
                            self.place_names.setdefault(squash_ws(n), nm)

    # ---- names
    def own_name(self, item: dict) -> str:
        if self.code == "en":
            if item.get("name_en_source") != "romanized":   # names.json: official or written by the guideline
                return item["name_en"]
            # names.json lacks the place (or its Korean name changed): its romanized name is not a translation
            return self.name(item["name"], f"places/{item.get('slug')}.name (data/<city>/en/names.json)")
        given = squash_ws(item.get(self.loc.name_key))
        if given:
            return given
        return self.name(item["name"], f"places/{item.get('slug')}.name")

    def name(self, ko: str, where: str) -> str:
        ko = squash_ws(ko)
        if self.code == "en":
            nm = self.table["names"].get(ko) or self.place_names.get(ko)
            if not nm and _admin_like(ko):
                nm = _admin(ko)
        else:
            nm = self.place_names.get(ko) or self.table["names"].get(ko)
        if nm:
            return nm
        self.missing.setdefault(uid("name", ko), {"kind": "name", "ko": ko, "where": where})
        return ""

    # ---- units
    def unit(self, ko_unit: str, kind: str, where: str, slots: dict | None = None) -> str | None:
        units = self.table["units"]
        if ko_unit in units:
            self.used.add(ko_unit)
            return units[ko_unit]
        if kind == "addr" and self.code != "en" and ko_unit in self.en_table["units"]:
            return self.en_table["units"][ko_unit]   # an address is the same romanized text in every language
        miss = {"kind": kind, "ko": ko_unit, "where": where}
        ctx = {k: v for k, (typ, v) in (slots or {}).items() if typ == "name"}
        if ctx:
            miss["names"] = ctx
        self.missing.setdefault(uid(kind, ko_unit), miss)
        return None

    def money(self, amount: str) -> str:
        n = int(float(amount))
        return f"{n:,} won" if self.code == "en" else self.loc.money(n)

    def prose_name(self, name: str) -> str:
        """A name as a text writes it: an official name's trailing label ('浮石寺［ユネスコ世界遺産（文化遺産）］') is not
        part of the Korean the text translates, and Chinese and Japanese text takes full-width brackets."""
        name = TRAIL_LABEL.sub("", name or "")
        if self.loc and self.loc.cjk:
            name = re.sub(r"\s*\(([^()]*)\)", lambda m: f"（{m.group(1)}）", name)
        return name

    def put_back(self, text: str, slots: dict, names: dict, ko_unit: str, where: str) -> str:
        want = set(SLOT.findall(ko_unit))
        got = set(SLOT.findall(text))
        if want != got:
            self.findings.append(f"{where}: placeholders {sorted(want)} in the Korean, {sorted(got)} in the "
                                 f"translation: {text}")

        def rep(m: re.Match) -> str:
            k = m.group(1)
            typ, val = slots.get(k, ("", ""))
            if typ == "name":
                return self.prose_name(names.get(val, ""))
            if typ == "won":
                return self.money(val)
            return val
        return SLOT.sub(rep, text)

    def translate(self, text: str, mode: str, masker: Masker, where: str) -> str:
        """mode: 'prose' (sentences), 'value' (lines), 'text' (one unit), 'addr' (one unit, an address)."""
        if text is None:
            return ""
        parts = sentences_ko(text) if mode == "prose" else lines(text) if mode == "value" else [squash_ws(text)]
        out = []
        for part in parts:
            if not part:
                out.append("")
                continue
            ko_unit, slots = masker.mask(part)
            if not HANGUL.search(ko_unit):
                plain = SLOT.sub(lambda m: "{" + m.group(1) + "}", ko_unit)
                names = {v: self.name(v, where) for typ, v in slots.values() if typ == "name"}
                out.append(self.put_back(norm_plain(plain), slots, names, plain, where))
                continue
            kind = {"prose": "sent", "value": "line"}.get(mode, mode)
            # the names first: a name the table lacks is listed even when its unit is missing too
            names = {v: self.name(v, where) for typ, v in slots.values() if typ == "name"}
            tr = self.unit(ko_unit, kind, where, slots)
            if tr is None:
                out.append("")
                continue
            for w in translit(ko_unit, tr, self.code, self.proper):
                self.findings.append(f"{where}: '{w[1]}' writes {w[0]} by its sound — translate it "
                                     f"(or list it in 'proper' if it is a proper noun)")
            out.append(self.put_back(tr, slots, names, ko_unit, where))
        if mode == "value":
            return "\n".join(out).strip()
        sep = "" if (self.loc and self.loc.cjk) else " "
        return sep.join(x for x in out if x)

    # ---- items
    def place(self, it: dict) -> dict:
        own = self.own_name(it)
        m = Masker([it["name"], *(it.get("alternate_names") or [])], [x["ko"] for x in it.get("mentions") or []])
        nm_key = "name_en" if self.code == "en" else self.loc.name_key
        w = f"places/{it['slug']}"
        self.place_names.setdefault(squash_ws(it["name"]), own)
        out = {"id": it["id"], nm_key: own}
        facts = []
        for f in it["facts"]:
            row = {"key": f["key"]}
            if f["key"] == "address":
                row["value"] = f.get("address_en_candidate") or self.translate(f["value"], "addr", Masker([], []),
                                                                               f"{w}.address")
            else:
                row["value"] = self.translate(f["value"], "value", m, f"{w}.facts.{f['key']}")
            for part in ("alternatives", "also"):
                if f.get(part):
                    row[part] = [{"value": self.translate(a["value"], "value", m, f"{w}.facts.{f['key']}.{part}")}
                                 for a in f[part]]
            if f.get("alternatives"):
                row["note"] = ec.CONFLICT_NOTE if self.code == "en" else self.loc.conflict
            facts.append(row)
        out["facts"] = facts
        out["summary"] = self.translate(it["summary"], "prose", m, f"{w}.summary")
        out["details"] = [{"heading": self.translate(d["heading"], "text", m, f"{w}.details"),
                           "text": self.translate(d["text"], "prose", m, f"{w}.details")} for d in it["details"]]
        out["faq"] = [{"q": self.translate(q["q"], "prose", m, f"{w}.faq"),
                       "a": self.translate(q["a"], "prose", m, f"{w}.faq")} for q in it["faq"]]
        return out

    def guide(self, it: dict) -> dict:
        m = Masker([], [x["ko"] for x in it.get("mentions") or []])
        w = f"guides/{it['slug']}"
        T = lambda s, mode="text": self.translate(s, mode, m, w)  # noqa: E731
        return {"id": it["id"], "label": T(it["label"]), "title": T(it["title"]), "summary": T(it["summary"], "prose"),
                "body": [{"heading": T(b["heading"]), "text": T(b["text"], "prose")} for b in it["body"]],
                "items": [{"place_slug": i["place_slug"], "reason": T(i["reason"], "prose")} for i in it["items"]],
                "faq": [{"q": T(f["q"], "prose"), "a": T(f["a"], "prose")} for f in it["faq"]],
                "sources": [{"name": T(s["name"])} for s in it["sources"]]}

    def course(self, it: dict) -> dict:
        m = Masker([], [x["ko"] for x in it.get("mentions") or []])
        w = f"courses/{it['slug']}"
        stops = []
        for s in it["stops"]:
            nm = self.place_names.get(squash_ws(s["name"])) if s.get("place_slug") else ""
            stops.append({"name": self.prose_name(nm) if nm else self.translate(s["name"], "text", m, w),
                          "note": self.translate(s["note"], "text", m, w)})
        return {"id": it["id"], "name": self.translate(it["name"], "text", m, w),
                "group": self.translate(it["group"], "text", m, w),
                "duration": self.translate(it["duration"], "text", m, w),
                "summary": self.translate(it["summary"], "prose", m, w), "stops": stops}

    def event(self, it: dict) -> dict:
        m = Masker([], [x["ko"] for x in it.get("mentions") or []])
        w = f"events/{it['id']}"
        newest = {}
        for f, v in it["newest"].items():
            if f in ("id", "address_en_candidate"):
                continue
            if f == "notes":
                newest["notes"] = [self.translate(n, "prose", m, w) for n in v]
            elif f == "address":
                newest["address"] = it["newest"].get("address_en_candidate") or self.translate(v, "addr", Masker([], []), w)
            elif f == "summary":
                newest[f] = self.translate(v, "prose", m, w)
            else:
                newest[f] = self.translate(v, "text", m, w)
        note = ec.EVENT_CONFLICT_NOTE if self.code == "en" else self.loc.event_conflict
        return {"id": it["id"], "series_name": self.translate(it["series_name"], "text", m, w), "newest": newest,
                "alternatives": {f: {"values": [self.translate(a["value"], "text", m, w) for a in vals], "note": note}
                                 for f, vals in it["alternatives"].items()},
                "highlights": [self.translate(h, "prose", m, w) for h in it["highlights"]],
                "program_notes": [self.translate(h, "prose", m, w) for h in it["program_notes"]],
                "usual": [{"text": self.translate(u["text"], "text", m, w),
                           "place": self.translate(u["place"], "text", m, w)} for u in it["usual"]],
                "editions": [{"id": e["id"], "name": self.translate(e["name"], "text", m, w),
                              "period_text": self.translate(e["period_text"], "text", m, w),
                              "place_name": self.translate(e["place_name"], "text", m, w)} for e in it["editions"]],
                "sources": [self.translate(s, "text", m, w) for s in it["sources"]]}

    def strings(self, rows: list[dict]) -> dict:
        """The strings rows this version lacks (or whose source changed), from the table: {id: record}."""
        tag = "en" if self.code == "en" else self.loc.tag
        have = _load(self.data, f"{self.code}/strings.json", {}) or {}
        add = {}
        for r in rows:
            if r["id"].startswith("ui:"):
                continue
            src_key = "ko" if "ko" in r else "en"
            old = have.get(r["id"]) or {}
            if old.get(tag) and old.get(src_key) == r[src_key]:
                continue
            src = r[src_key]
            if HANGUL.search(src) or src_key == "en":
                tr = self.unit(src, "string", f"strings/{r['id']}")
                if tr is None:
                    continue
            else:
                tr = norm_plain(src)
            add[r["id"]] = {src_key: src, tag: tr}
        return add

    # ---- run
    def fill(self) -> list[Path]:
        outs = []
        build = {"places": self.place, "guides": self.guide, "courses": self.course, "events": self.event}
        self.new_strings = {}
        for b, info in zip(self.batches, self.prep["batches"]):
            if b["type"] == "strings":
                self.new_strings = self.strings(b["items"])
                continue
            items = [build[b["type"]](it) for it in b["items"]]
            path = Path(info["file"]).with_name(Path(info["file"]).name.replace(".input.", ".output."))
            path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1) + "\n", "utf-8")
            outs.append(path)
        return outs


def _admin_like(ko: str) -> bool:
    return bool(re.fullmatch(r"[가-힣0-9]{2,}[동읍면리]", ko))


# ------------------------------------------------------------------ commands
def extract(data: Path, code: str, work: Path, every: bool = False) -> dict:
    v = Version(data, code, work)
    v.fill()
    if every:   # every unit, translated or not (a translator's full view)
        v.table = {"units": {}, "names": {}, "proper": v.table["proper"]}
        v.en_table = {"units": {}, "names": {}, "proper": []}
        v.missing = {}
        v.place_names = {} if code != "en" else v.place_names
        v.fill()
    return {"lang": code, "missing": v.missing, "findings": v.findings}


def fill(data: Path, code: str, answers: list[Path], work: Path) -> dict:
    """Adds answers ({id: translation}, ids from extract) to the table; ids of names go to "names"."""
    v = Version(data, code, work)
    keep = {"units": dict(v.table["units"]), "names": dict(v.table["names"])}
    v.table = {"units": {}, "names": {}, "proper": v.table["proper"]}
    v.en_table = {"units": {}, "names": {}, "proper": []}
    v.missing = {}
    if code != "en":
        v.place_names = {}
        for b in v.batches:
            if b["type"] == "places":
                for it in b["items"]:
                    nm = squash_ws(it.get(v.loc.name_key))
                    if nm:
                        v.place_names[squash_ws(it["name"])] = nm
    v.fill()
    known = dict(v.missing)
    added = {"units": 0, "names": 0, "unknown": []}
    table = load_table(data, code)
    table["units"].update(keep["units"])
    table["names"].update(keep["names"])
    for path in answers:
        for k, tr in json.loads(path.read_text("utf-8")).items():
            if k == "proper":
                table["proper"] += list(tr)
                continue
            m = known.get(k)
            if not m:
                added["unknown"].append(k)
                continue
            if m["kind"] == "name":
                table["names"][m["ko"]] = squash_ws(tr)
                added["names"] += 1
            else:
                table["units"][m["ko"]] = tr.strip() if "\n" in tr else ec._sq(tr)   # keeps the narrow nbsp (fr, ru)
                added["units"] += 1
    save_table(data, code, table)
    return added


def apply(data: Path, code: str, work: Path, do_merge: bool) -> int:
    v = Version(data, code, work)
    outs = v.fill()
    if v.missing:
        (work / f"{code}-missing.json").write_text(json.dumps(v.missing, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"[{code}] 번역표에 없는 단위 {len(v.missing)}개 — 채우지 않고 멈춥니다 ({work / (code + '-missing.json')}):")
        for k, m in list(v.missing.items())[:40]:
            print(f"  {k} {m['kind']} {m['where']}: {m['ko'][:80]}")
        return 1
    problems = v.findings + ec.check(outs)
    for rid, rec in v.new_strings.items():
        src = {k: rec[k] for k in ("ko", "en") if k in rec}
        item = {"id": rid, **{k: x for k, x in rec.items() if k not in ("ko", "en")}}
        if code == "en":
            item["en"] = rec["en"]
            problems += [f"strings {rid}: {x}" for x in ec.check_string(item, src)]
        else:
            problems += [f"strings {rid}: {x}" for x in ec.check_string_l(item, src, ec.LangCheck(code))]
    if problems:
        print(f"[{code}] 검사 미통과 {len(problems)}건:")
        print("\n".join(problems[:200]))
        return 1
    print(f"[{code}] OK — {sum(len(json.loads(p.read_text('utf-8'))['items']) for p in outs)} records, "
          f"{len(v.new_strings)} strings rows, {len(v.used)} units used")
    if do_merge:
        print(json.dumps(ec.merge(outs, data), ensure_ascii=False))
        if v.new_strings:
            sp = data / code / "strings.json"
            store = _load(data, f"{code}/strings.json", {}) or {}
            store.update(v.new_strings)
            sp.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


def _sample(ko_unit: str, tr: str, code: str) -> tuple[str, str]:
    """A unit and its translation with every placeholder replaced by the same sample value (the language's money)."""
    loc = LC.get(code) if code != "en" else None

    def fill(text: str, korean: bool) -> str:
        def rep(m: re.Match) -> str:
            k = m.group(1)
            if k == "name" or k.startswith("m"):
                return {"ru": "Сэмпл", "ja": "サンプル", "zh-hans": "样本", "zh-hant": "樣本"}.get(code, "Zq") + (k[1:] if k != "name" else "")
            n = int(k[1:])
            if k[0] == "w":
                amt = 1000 * n + 100 * n
                return f"{amt:,}원" if korean else (f"{amt:,} won" if code == "en" else loc.money(amt))
            if k[0] == "t":
                return f"{n % 24:02d}:{(n * 5) % 60:02d}"
            return f"054-63{n % 10}-00{n % 10}{n % 10}"
        return SLOT.sub(rep, text)
    return fill(ko_unit, True), fill(tr, False)


def lint(data: Path, code: str) -> list[str]:
    """Checks every unit of the table on its own (parity, style, script, sound, placeholders) with sample values."""
    table = load_table(data, code)
    proper = set(table["proper"])
    for p in _load(data, "places.json", []) or []:
        for n in [p.get("name"), *(p.get("alternate_names") or [])]:
            proper |= set(re.findall(r"[가-힣]{2,}", str(n or "")))
    issues = []
    for ko_unit, tr in table["units"].items():
        if set(SLOT.findall(ko_unit)) != set(SLOT.findall(tr)):
            issues.append(f"{uid('x', ko_unit)} placeholders {sorted(set(SLOT.findall(ko_unit)))} -> "
                          f"{sorted(set(SLOT.findall(tr)))}: {ko_unit[:50]}")
            continue
        ko, tx = _sample(ko_unit, tr, code)
        prose = bool(re.search(r"(?:[다요까죠][.?!]|[?])$", ko_unit))
        if code == "en":
            found = ec.parity(ko, tx) + ec.style(tx, prose=prose)
        else:
            found = ec.parity_l(ko, tx, code) + ec.style_l(tx, code, prose=prose)
        found += [f"'{f}' writes {w} by its sound" for w, f in translit(ko_unit, tr, code, proper)]
        issues += [f"{x} :: {ko_unit[:60]} => {tr[:80]}" for x in found]
    return issues


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "fill", "apply", "report", "lint"):
        p = sub.add_parser(name)
        p.add_argument("--data", type=Path, required=True, help="도시 데이터 폴더(예: data/suwon)")
        p.add_argument("--lang", action="append", choices=("en", *LC.CODES), required=name != "report")
        p.add_argument("--work", type=Path, default=Path("dist-intl-work"), help="번역 묶음을 쓰는 작업 폴더")
        if name == "extract":
            p.add_argument("--out", type=Path)
            p.add_argument("--all", action="store_true", help="번역표에 있는 단위까지 모두")
        if name == "fill":
            p.add_argument("answers", nargs="+", type=Path)
        if name == "apply":
            p.add_argument("--merge", action="store_true")
        if name == "report":
            p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        codes = a.lang or ["en", *LC.CODES]
        res = report(a.data, codes)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            for c, r in res.items():
                print(f"{c}: 소리 옮김 값 {r['values_with_sound']}/{r['values']} (레코드 {r['records_with_sound']}/"
                      f"{r['records']}), 화면 문구 소리 옮김 {r['strings_with_sound']}/{r['strings']}, "
                      f"낡은 번역 {r['stale']}, 번역 없음 {r['missing']}")
        return 0
    rc = 0
    for code in a.lang:
        if a.cmd == "extract":
            res = extract(a.data, code, a.work / code, a.all)
            if a.out:
                out = a.out if len(a.lang) == 1 else a.out.with_name(f"{a.out.stem}-{code}{a.out.suffix}")
                out.write_text(json.dumps(res["missing"], ensure_ascii=False, indent=1) + "\n", "utf-8")
            kinds = {}
            for m in res["missing"].values():
                kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
            print(f"[{code}] 번역표에 없는 단위 {len(res['missing'])}개 {kinds}")
        elif a.cmd == "lint":
            issues = lint(a.data, code)
            print(f"[{code}] {len(issues)} findings")
            print("\n".join(issues[:300]))
            rc |= 1 if issues else 0
        elif a.cmd == "fill":
            print(f"[{code}]", json.dumps(fill(a.data, code, a.answers, a.work / code), ensure_ascii=False))
        else:
            rc |= apply(a.data, code, a.work / code, a.merge)
    return rc


if __name__ == "__main__":
    sys.exit(main())
