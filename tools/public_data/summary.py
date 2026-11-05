"""모음 결과 요약 — out/<slug>/*.json과 cache/calls.log를 읽어 사이트별 건수·서비스별 호출 수를 out/_summary.json에 쓴다
(2026-11-05). 값은 결과 파일에서 센 것이다.

    python tools/summary.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, OUT_DIR, ROOT, Site, all_slugs  # noqa: E402


def load(slug: str, name: str):
    f = OUT_DIR / slug / name
    return json.loads(f.read_text("utf-8")) if f.is_file() else None


def site_row(slug: str) -> dict:
    site = Site(slug)
    places = site.places()
    groups = {"food": 0, "stay": 0, "camp": 0}
    for p in places:
        g = "camp" if p["id"].startswith("gocamping-") or "캠핑" in (p.get("name") or "") else p.get("kind")
        if g in groups:
            groups[g] += 1
    r: dict = {"places": len(places)}
    lic = load(slug, "licenses.json")
    if lic:
        st = collections.Counter(v["status"] for v in lic["places"].values())
        r["licenses"] = {"matched": len(lic["places"]), "of": sum(groups.values()), "unmatched": len(lic["unmatched_places"]),
                         "status": dict(st), "closed_published": sum(1 for c in lic["closed"] if c["published"]),
                         "rows": {k: v.get("rows", 0) for k, v in lic["sources"].items()},
                         "errors": {k: v["error"] for k, v in lic["sources"].items() if v.get("error")}}
    rel = load(slug, "related.json")
    if rel:
        r["related"] = {"base_ym": rel["base_ym"], "centers_matched": len(rel["places"]),
                        "centers_unmatched": len(rel["unmatched_centers"]),
                        "rows_linked": sum(1 for v in rel["places"].values() for e in v if e["place_id"]),
                        "rows": sum(len(v) for v in rel["places"].values())}
    cr = load(slug, "crowd.json")
    if cr:
        r["crowd"] = {"matched": len(cr["places"]), "unmatched": len(cr["unmatched"]), "period": cr["period"]}
    vd = load(slug, "visitors_daily.json")
    if vd:
        r["visitors_daily"] = {"region": vd["region"], "days": vd["period"]["days"], "missing": len(vd["period"]["missing"]),
                               "period": [vd["period"]["start"], vd["period"]["end"]]}
    al = load(slug, "almanac.json")
    if al:
        r["almanac"] = {"sun_days": len(al.get("sun") or {}), "sun_location": (al["sources"].get("sun") or {}).get("location"),
                        "tide_stations": len(al.get("tide") or {})}
    be = load(slug, "beaches.json")
    if be:
        r["beaches"] = {"rows": be["sources"]["info"].get(f"rows_{slug}"), "matched": len(be["places"]),
                        "unmatched_info": [u["sta_nm"] for u in be["unmatched"] if u["source"] == "info"]}
    fe = load(slug, "ferry.json")
    if fe:
        r["ferry"] = {"routes": [f"{c} {v['name']}" for c, v in fe["routes"].items()], "island_places": len(fe["places"])}
    tr = load(slug, "transport_tago.json")
    if tr:
        r["transport_tago"] = {"routes": len(tr["routes"]), "with_runs": sum(1 for x in tr["routes"] if x["count"]),
                               **{m: len(tr.get(m) or []) for m in ("train", "express_bus", "intercity_bus", "flight")}}
    return r


def calls() -> dict:
    out: dict = collections.Counter()
    f = CACHE_DIR / "calls.log"
    if f.is_file():
        for line in f.read_text("utf-8").splitlines():
            d = json.loads(line)
            out[d["service"].split("(")[0] + ("(" + d["service"].split("(")[1] if "(" in d["service"] else "")] += d["calls"]
    return dict(out)


def main() -> int:
    doc = {"sites": {s: site_row(s) for s in all_slugs()}, "calls_logged": calls()}
    (OUT_DIR / "_summary.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    for s, r in doc["sites"].items():
        print(s, json.dumps({k: v for k, v in r.items() if k != "places"}, ensure_ascii=False)[:600])
    print(json.dumps(doc["calls_logged"], ensure_ascii=False, indent=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
