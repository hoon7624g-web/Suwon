#!/bin/bash
# usage: tools/run_val.sh <log> <mode> <slug>...
cd /home/user/work/pubdata
name=$1; mode=$2; shift 2
for s in "$@"; do
  echo "=== $s $(date +%H:%M:%S)" >> logs/$name.log
  python3 tools/validate_sites.py "$s" --mode "$mode" >> logs/$name.log 2>&1
done
echo "DONE $(date +%H:%M:%S)" >> logs/$name.log
