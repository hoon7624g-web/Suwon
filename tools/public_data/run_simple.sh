#!/bin/bash
# usage: DATA_GO_KR_KEY=… tools/run_simple.sh <log-name> "<tool args before --site>" "<args after>" <slug>...
cd /home/user/work/pubdata
name=$1; pre=$2; post=$3; shift 3
for s in "$@"; do
  echo "=== $s $(date +%H:%M:%S)" >> logs/$name.log
  python3 tools/$pre --site "$s" $post >> logs/$name.log 2>&1
done
echo "DONE $(date +%H:%M:%S)" >> logs/$name.log
