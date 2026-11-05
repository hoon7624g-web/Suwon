#!/bin/bash
# 2번째 검증 줄이 끝나면 이어서: 엔진 오류(경주·속초 외국어판 loc.city)를 피해 almanac 없이 확인, 시간 초과였던 제주·부산 다시
cd /home/user/work/pubdata
# (바로 시작)
for args in "gyeongju --skip almanac.json" "sokcho --skip almanac.json" "jeju" "busan"; do
  echo "=== $args $(date +%H:%M:%S)" >> logs/valnew4.log
  python3 tools/validate_sites.py $args --mode new >> logs/valnew4.log 2>&1
done
echo "DONE $(date +%H:%M:%S)" >> logs/valnew4.log
