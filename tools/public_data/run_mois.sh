#!/bin/bash
# usage: DATA_GO_KR_KEY=… tools/run_mois.sh <log-name> <slug>...   — 인허가 12종을 사이트마다 차례로 받는다(같은 날 캐시)
cd /home/user/work/pubdata
name=$1; shift
for s in "$@"; do
  echo "=== $s $(date +%H:%M:%S)" >> logs/mois_$name.log
  python3 tools/mois_licenses.py --site "$s" fetch --max-calls 9500 --day 2026-11-05 >> logs/mois_$name.log 2>&1
done
echo "DONE $(date +%H:%M:%S)" >> logs/mois_$name.log
