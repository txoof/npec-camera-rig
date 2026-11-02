#!/bin/bash
# usage: log.sh OUTFILE ; logs epoch, main rss MB, camera rss MB, main hwm, mem available MB every 1 s
out=$1
while true; do
  p=$(systemctl show npec-rig -p MainPID --value)
  if [ "$p" != 0 ]; then
    c=$(pgrep -P $p -f spawn_main | head -1)
    m=$(awk "/VmRSS/{print int(\$2/1024)}" /proc/$p/status 2>/dev/null)
    h=$(awk "/VmHWM/{print int(\$2/1024)}" /proc/$p/status 2>/dev/null)
    cr=$( [ -n "$c" ] && awk "/VmRSS/{print int(\$2/1024)}" /proc/$c/status 2>/dev/null)
    ch=$( [ -n "$c" ] && awk "/VmHWM/{print int(\$2/1024)}" /proc/$c/status 2>/dev/null)
  else m=; h=; cr=; ch=; fi
  a=$(awk "/MemAvailable/{print int(\$2/1024)}" /proc/meminfo)
  echo "$(date +%s) $p ${m:-0} ${h:-0} ${cr:-0} ${ch:-0} $a" >> $out
  sleep 1
done
