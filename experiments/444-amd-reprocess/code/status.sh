#!/bin/bash
# One readable line of full-run progress. Safe to run any time; reads only.
B=/home/txoof/temp.nobackup/444-amd-reprocess/ac-testing
python3 - "$B" <<'PYEOF'
import json, sys, time, os
from datetime import datetime, UTC
B = sys.argv[1]
log = os.path.join(B, "full-run.jsonl")
rows = []
with open(log) as fh:
    for line in fh:
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
starts = [r for r in rows if r.get("event") == "start"]
prog = [r for r in rows if r.get("event") == "progress"]
fails = [r for r in rows if r.get("event") == "failed"]
ends = [r for r in rows if r.get("event") == "end"]
total = sum(r["photos"] for r in starts)
# Each progress record means that worker has completed another 10 photos.
done = 10 * len(prog)
rates = [r["s_per_photo"] for r in prog[-6:]]
avg = sum(rates) / len(rates) if rates else 0
workers = len(starts) - len(ends)
left = total - done
eta_s = (left * avg / workers) if workers and avg else 0
eta = datetime.fromtimestamp(time.time() + eta_s, UTC).strftime("%H:%M UTC") if eta_s else "?"
pct = 100 * done / total if total else 0
reasons = {}
for f in fails:
    key = f["reason"].split(":")[0].strip()
    reasons[key] = reasons.get(key, 0) + 1
print(f"{datetime.now(UTC):%H:%M:%SZ}  {done:,}/{total:,} photos ({pct:.1f}%)  "
      f"failed {len(fails)}  {avg:.2f} s/photo/worker  workers {workers}  finish ~{eta}")
if reasons:
    print("   failure reasons: " + ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items())))
PYEOF
free -h | awk '/^Mem|^Swap/{printf "   %-5s used %-6s avail %s\n",$1,$3,$7}'
