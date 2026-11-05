"""인허가 조회서비스 쪽 미리 받기 — 행정안전부 인허가 API는 한 쪽(100행)에 약 10초가 걸려(2026-11-05) 사이트마다 차례로 받으면
몇 시간이 든다. 이 도구는 모든 사이트·서비스·개방자치단체코드의 쪽을 여러 갈래로 동시에 받아 tools/mois_licenses.py와
같은 캐시(cache/mois_licenses/<날>/<서비스>-<코드>-<쪽>.json)에 둔다. 그 뒤 사이트마다 `mois_licenses.py fetch --day <날>`을
돌리면 캐시만 읽어 원자료 CSV를 만든다(호출 0).

    DATA_GO_KR_KEY=… python tools/mois_prefetch.py --day 2026-11-05 --workers 24 [--sites busan daegu] [--only general_restaurants]

- 1단계: 쪽 1을 모두 받아 totalCount를 안다. 2단계: 남은 쪽을 모두 동시에 받는다.
- 응답 머리말 X-RateLimit-Remaining(서비스별 하루 한도)이 --reserve 아래로 내려가거나 하루 한도 오류가 오면 그 서비스는 멈춘다.
- 키는 환경 변수로만 받고 오류 메시지에서 가린다(mois_licenses.mask). 실패한 쪽은 다시 실행하면 이어 받는다.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mois_licenses as M  # noqa: E402
from common import CACHE_DIR, Site, all_slugs, is_quota, log_calls, normalize_key  # noqa: E402

LOCK = threading.Lock()
STATE = {"calls": {}, "remaining": {}, "stopped": {}, "errors": []}


def get_page(svc: str, group: str, page: int, key: str, day_cache: Path, reserve: int) -> dict | None:
    f = day_cache / f"{svc}-{group}-{page}.json"
    if f.is_file():
        return json.loads(f.read_text("utf-8"))
    if svc in STATE["stopped"]:
        return None
    q = urllib.parse.urlencode({"serviceKey": key, "pageNo": page, "numOfRows": 100, "returnType": "json",
                                "cond[OPN_ATMY_GRP_CD::EQ]": group})
    err = ""
    for i in range(6):
        raw = ""
        try:
            with LOCK:
                STATE["calls"][svc] = STATE["calls"].get(svc, 0) + 1
            with urllib.request.urlopen(M.BASE.format(svc=svc) + "?" + q, timeout=120) as r:
                rem = r.headers.get("X-RateLimit-Remaining")
                raw = r.read().decode("utf-8")
            if rem is not None:
                with LOCK:
                    STATE["remaining"][svc] = int(rem)
                    if int(rem) < reserve:
                        STATE["stopped"][svc] = f"남은 하루 한도 {rem} < {reserve}"
            resp = json.loads(raw)["response"]
            head = resp.get("header") or {}
            if str(head.get("resultCode", "0")) not in ("0", "00"):
                err = f"resultCode {head.get('resultCode')} {head.get('resultMsg')}"
                break
            body = resp["body"]
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(body, ensure_ascii=False), "utf-8")
            tmp.replace(f)
            return body
        except Exception as e:   # noqa: BLE001
            if isinstance(e, urllib.error.HTTPError):
                raw = e.read().decode("utf-8", "replace")
            err = M.mask(f"{type(e).__name__}: {e} {raw[:300]}", key)
            if is_quota(err) and "PER_SECOND" not in err.upper():
                with LOCK:
                    STATE["stopped"][svc] = "하루 한도: " + err[:200]
                return None
            time.sleep(2 + 2 * i)
    with LOCK:
        STATE["errors"].append(f"{svc} {group} {page}쪽: {err[:300]}")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--sites", nargs="*")
    ap.add_argument("--only", nargs="*", choices=list(M.SVC))
    ap.add_argument("--reserve", type=int, default=30)
    a = ap.parse_args(argv)
    key = normalize_key(os.environ.get("DATA_GO_KR_KEY") or "")
    if not key:
        raise SystemExit("키가 없습니다 — DATA_GO_KR_KEY")
    day_cache = CACHE_DIR / "mois_licenses" / a.day
    day_cache.mkdir(parents=True, exist_ok=True)
    groups = {}
    for slug in a.sites or all_slugs():
        groups.update(Site(slug).pd["mois_groups"])
    svcs = a.only or list(M.SVC)
    first = [(s, g, 1) for s in svcs for g in groups]
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        bodies = dict(zip(first, ex.map(lambda t: get_page(*t, key, day_cache, a.reserve), first)))
    rest = []
    for (s, g, _), b in bodies.items():
        if b:
            total = int(b.get("totalCount") or 0)
            rest += [(s, g, p) for p in range(2, (total + 99) // 100 + 1)]
    todo = [t for t in rest if not (day_cache / f"{t[0]}-{t[1]}-{t[2]}.json").is_file()]
    print(f"쪽 1: {len(first)} · 남은 쪽 {len(rest)}(캐시 없음 {len(todo)}) · {time.time() - t0:.0f}초", flush=True)
    done = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(get_page, *t, key, day_cache, a.reserve) for t in todo]
        for fu in cf.as_completed(futs):
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(todo)} · {time.time() - t0:.0f}초 · 남은 한도 {STATE['remaining']}", flush=True)
    log_calls("1741000(prefetch)", ",".join(a.sites or ["all"]), sum(STATE["calls"].values()),
              json.dumps(STATE["calls"], ensure_ascii=False))
    print(json.dumps({"calls": STATE["calls"], "remaining": STATE["remaining"], "stopped": STATE["stopped"],
                      "errors": STATE["errors"][:20], "n_errors": len(STATE["errors"]),
                      "seconds": round(time.time() - t0)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
