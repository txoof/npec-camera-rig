#!/bin/bash
# Append a progress line to chain.log every 5 minutes while workers are alive.
B=/home/txoof/temp.nobackup/444-amd-reprocess/ac-testing
while pgrep -f "run_photos.py.*all-paths" > /dev/null; do
  "$B/status.sh" >> "$B/chain.log" 2>&1
  sleep 300
done
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] workers gone - full run ended" >> "$B/chain.log"
"$B/status.sh" >> "$B/chain.log" 2>&1
