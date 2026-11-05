#!/bin/bash
# 공공데이터 모음 — 18개 사이트 전체 실행(2026-11-05). 모든 응답은 cache/에 남으므로 같은 명령을 다시 돌리면 캐시에서 이어 간다.
#   키: DATA_GO_KR_KEY="$(cat <키 파일>)" TOURAPI_KEY="$(cat <키 파일>)" tools/run_all.sh [단계…]
#   단계: configs lists stations discover mois related datalab sun tide beaches ferry tago validate (없으면 configs·validate 뺀 전부)
#   START: 해·물때 첫날(기본 2026-11-05 — 캐시를 다시 쓰려면 받은 날과 같게), DAY: 인허가 캐시 날(기본 2026-11-05),
#   END: 방문자 수 마지막 날(기본 20261006)
set -u
cd "$(dirname "$0")/.."
START=${START:-2026-11-05}; DAY=${DAY:-2026-11-05}; END=${END:-20261006}
ALL=$(ls config/*.json | xargs -n1 basename | sed 's/\.json$//')
COAST=$(python3 -c "
import json,glob
for p in sorted(glob.glob('config/*.json')):
    c=json.load(open(p))
    if c['public_data'].get('tide_stations'): print(c['slug'])")
FERRY=$(python3 -c "
import json,glob
for p in sorted(glob.glob('config/*.json')):
    c=json.load(open(p))
    if c['public_data'].get('ferry'): print(c['slug'])")
steps=${*:-lists stations discover mois related datalab sun tide beaches ferry tago}
mkdir -p logs
for step in $steps; do
  echo "##### $step $(date +%H:%M:%S)"
  case $step in
    configs)  python3 tools/make_configs.py ;;
    lists)    python3 tools/tago.py lists ;;
    stations) python3 tools/almanac.py stations --date "${START//-/}" ;;
    discover) for s in $ALL; do python3 tools/tago.py discover --site "$s" --workers 10 | tail -1; done ;;
    mois)     python3 tools/mois_prefetch.py --day "$DAY" --workers 24
              for s in $ALL; do python3 tools/mois_licenses.py --site "$s" fetch --day "$DAY" --max-calls 9500 | tail -1
                                python3 tools/mois_licenses.py --site "$s" --apply | tail -1; done ;;
    related)  for s in $ALL; do python3 tools/tourapi_related.py --site "$s" --apply | grep RESULT; done ;;
    datalab)  for s in $ALL; do python3 tools/datalab.py --site "$s" --apply --end "$END" | grep RESULT; done ;;
    sun)      for s in $ALL; do python3 tools/almanac.py run --site "$s" --only sun --apply --start "$START" | grep RESULT; done ;;
    tide)     python3 tools/tide_prefetch.py --start "$START" --days 120 --workers 12
              for s in $COAST; do python3 tools/almanac.py run --site "$s" --only tide --apply --start "$START" | grep RESULT; done ;;
    beaches)  for s in $COAST; do python3 tools/beaches.py --site "$s" --apply | grep RESULT; done ;;
    ferry)    for s in $FERRY; do python3 tools/ferry.py --site "$s" fetch --date 20261104 --date 20260801 | tail -1
                                  python3 tools/ferry.py --site "$s" --apply | grep RESULT; done ;;
    tago)     for s in $ALL; do python3 tools/tago.py --site "$s" fetch --max-calls 4000 | tail -1
                                python3 tools/tago.py --site "$s" --apply | grep RESULT; done ;;
    validate) for s in $ALL; do python3 tools/validate_sites.py "$s" --mode both | tail -2; done ;;
  esac
done
