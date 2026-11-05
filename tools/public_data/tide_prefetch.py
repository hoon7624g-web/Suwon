"""조석예보 미리 받기 — 조석예보는 지점·날짜마다 한 번 불러야 해(지점 80여 곳 × 120일) 사이트마다 차례로 받으면 몇 시간이
든다. 모든 바다 사이트 설정(config tide_stations)의 지점·날짜를 여러 갈래로 동시에 받아 tools/almanac.py와 같은 캐시
(cache/almanac/tide-<지점>-<날>.xml)에 둔다(2026-11-05). 그 뒤 `almanac.py --only tide --apply`는 캐시만 읽는다.

    DATA_GO_KR_KEY=… python tools/tide_prefetch.py --start 2026-11-05 --days 120 --workers 12 [--max-calls 9000]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almanac as A  # noqa: E402
from common import CACHE_DIR, Budget, Site, all_slugs, load_key, log_calls  # noqa: E402


class SafeBudget(Budget):
    def __init__(self, n):
        super().__init__(n)
        self.lock = threading.Lock()

    def spend(self):
        with self.lock:
            super().spend()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-calls", type=int, default=9000)
    a = ap.parse_args(argv)
    key = load_key()
    stations: dict[str, str] = {}
    for slug in all_slugs():
        stations.update(Site(slug).pd.get("tide_stations") or {})
    A.TIDE_STATIONS = stations
    start = dt.date.fromisoformat(a.start)
    days = A.dates(start, a.days)
    cache = CACHE_DIR / "almanac"
    todo = [(o, d) for o in reversed(list(stations)) for d in days
            if not (cache / f"tide-{o}-{d.strftime('%Y%m%d')}.xml").is_file()]
    budget = SafeBudget(a.max_calls)
    errors = []
    print(f"지점 {len(stations)} · 받을 것 {len(todo)}", flush=True)

    def one(t):
        got, err = A.fetch_tide(t[0], [t[1]], key, budget, cache)
        if err:
            errors.append(err)
    done = 0
    try:
        with cf.ThreadPoolExecutor(a.workers) as ex:
            for _ in ex.map(one, todo):
                done += 1
                if done % 500 == 0:
                    print(f"  {done}/{len(todo)} · 남은 하루 한도 {budget.remaining} · 오류 {len(errors)}", flush=True)
    finally:
        log_calls("1192136/tideFcstHghLw(prefetch)", "_coastal", budget.used)
    print(json.dumps({"calls": budget.used, "remaining": budget.remaining, "errors": len(errors),
                      "first_errors": errors[:5]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
