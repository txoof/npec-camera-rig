#!/bin/bash
# Drives the Randomize page on npec-rig-01 for metrology log 25; prints UTC times of each action.
R=http://10.248.49.102:8000
act() { local t0=$(date -u +%H:%M:%S); local out=$(curl -s --max-time 180 -X POST $R/api/randomize/$1); echo "$t0 $1 $(echo "$out" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("detail") or ("id %s" % d.get("id")))')"; }
for i in 1 2 3; do
  act suggest; sleep 15
  act check; id=$(curl -s $R/api/randomize | python3 -c 'import json,sys;print(json.load(sys.stdin)["check"]["id"])')
  curl -s -o /dev/null -w "$(date -u +%H:%M:%S) overlay $id %{http_code}\n" --max-time 120 $R/api/randomize/checks/$id/overlay
  sleep 40
done
# Wait until 2 s after the next scheduled photo (second 45 of the minute on the rig).
until [ "$(date -u +%S)" = "47" ]; do sleep 0.5; done
act suggest &
sleep 1; act check
wait
id=$(curl -s $R/api/randomize | python3 -c 'import json,sys;print(json.load(sys.stdin)["check"]["id"])')
curl -s -o /dev/null -w "$(date -u +%H:%M:%S) overlay $id %{http_code}\n" --max-time 120 $R/api/randomize/checks/$id/overlay
echo done
