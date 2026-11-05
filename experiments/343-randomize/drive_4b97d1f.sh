#!/bin/bash
# Checks on npec-rig-01 for metrology log 25.2: three at second 15, one at second 47; logs epochs.
B=http://10.248.49.102:8000
L=/home/pi/.claude/jobs/1c46a9ec/tmp/after/actions.log
wait_sec() { local target=$(( ( $(date +%s) / 60 + 1 ) * 60 + $1 )); while [ $(date +%s) -lt $target ]; do sleep 0.2; done; }
run() { local s=$(date +%s.%N); local code=$(curl -s -o /tmp/act343.json -w '%{http_code}' -X $2 --max-time 300 $B$3); echo "$1 $s $(date +%s.%N) $code" >> $L; }
wait_sec 15; run check1 POST /api/randomize/check
wait_sec 15; wait_sec 15; wait_sec 15; run check2 POST /api/randomize/check
wait_sec 15; wait_sec 15; wait_sec 15; run check3 POST /api/randomize/check
wait_sec 15; wait_sec 15; wait_sec 47; run check_overlap POST /api/randomize/check
echo done >> $L
