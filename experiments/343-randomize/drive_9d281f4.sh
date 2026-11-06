#!/bin/bash
# runs page actions at chosen second-of-minute; logs UTC epoch start/end
B=http://10.248.49.102:8000
L=/home/pi/.claude/jobs/1c46a9ec/tmp/agentA/actions.log
wait_sec() { # wait until next minute boundary + $1 seconds, at least $2 minutes from now-ish
  local target=$(( ( $(date +%s) / 60 + 1 ) * 60 + $1 ))
  while [ $(date +%s) -lt $target ]; do sleep 0.2; done
}
run() { # name, method, path
  local s=$(date +%s.%N)
  local code=$(curl -s -o /tmp/act_$1.json -w '%{http_code}' -X $2 --max-time 300 $B$3)
  local e=$(date +%s.%N)
  echo "$1 $s $e $code $(stat -c%s /tmp/act_$1.json) $(head -c 150 /tmp/act_$1.json | tr -cd "[:print:]")" >> $L
}
nextmin() { local n=$1; for i in $(seq 1 $n); do wait_sec $2; done; }
wait_sec 15; run suggest1 POST /api/randomize/suggest
nextmin 4 15; run suggest2 POST /api/randomize/suggest
nextmin 4 15; run suggest3 POST /api/randomize/suggest
for k in 1 2 3; do
  nextmin 4 15; run check$k POST /api/randomize/check
  id=$(curl -s $B/api/randomize | python3 -c 'import sys,json;print(json.load(sys.stdin)["check"]["id"])')
  echo "check${k}_id $id" >> $L
  nextmin 1 15; run overlay$k GET /api/randomize/checks/$id/overlay
done
nextmin 4 47; run check_overlap POST /api/randomize/check
echo done >> $L
