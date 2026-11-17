#!/bin/bash
# Logs Reprocess progress on production every 10 min until done or the deadline (#410).
out=~/scratch/410-production-reprocess/progress.tsv
deadline=$(date -u -d '2026-11-18 12:00' +%s)
[ -f $out ] || echo -e "utc\tprogress\trss_kb\tavail_mb\tdisk_free_gb\tlast_photo\tread_delay_s\tlog_errors" > $out
while [ $(date -u +%s) -lt $deadline ]; do
  p=$(curl -s -m 30 ac-testing:8000/api/experiments/18/reprocess)
  r=$(ssh pi@ac-testing 'pid=$(ss -ltnp | grep -o "pid=[0-9]*" | head -1 | cut -d= -f2); echo -n "$(ps -o rss= -p $pid | tr -d " ")\t$(free -m | awk "/Mem:/{print \$7}")\t$(df -BG --output=avail / | tail -1 | tr -d " G")\t"; python3 -c "
import sqlite3,datetime as d
c=sqlite3.connect(\"file:/var/lib/npec-rig/rig.db?mode=ro\",uri=True)
r=c.execute(\"select p.taken_at,t.read_at from capture p left join tray_read t on t.capture_id=p.id where experiment_id=18 order by p.id desc limit 1 offset 1\").fetchone()
f=d.datetime.fromisoformat
print(r[0][11:19], round((f(r[1])-f(r[0])).total_seconds(),1) if r[1] else \"unread\", sep=\"\t\", end=\"\t\")"; grep -ciE "traceback" $(ls -t /tmp/npec-rig-server-*.log | head -1)' 2>&1 | tr -d '\n')
  echo -e "$(date -u +%FT%TZ)\t$p\t$r" >> $out
  echo "$p" | grep -q '"running":false' && [ -n "$p" ] && break
  sleep 600
done
