#!/bin/bash
# Append a progress line to chain.log every 5 minutes while any run_photos.py worker is
# alive -- Part 3B's workers included, so starting this beside chain.sh does not exit early.
B=/home/txoof/temp.nobackup/444-amd-reprocess/ac-testing
while pgrep -f "run_photos.py" > /dev/null; do
  "$(dirname "$0")/status.sh" >> "$B/chain.log" 2>&1
  sleep 300
done
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] workers gone - full run ended" >> "$B/chain.log"
"$(dirname "$0")/status.sh" >> "$B/chain.log" 2>&1
