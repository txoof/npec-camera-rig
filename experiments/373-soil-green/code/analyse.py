"""Metrology log 37, analysis 1 and 2: soil level per tray and day, and warning counts.
python3 -I code/analyse.py (numpy only)."""
import csv
import gzip
from collections import defaultdict
from pathlib import Path

import numpy as np

data = Path(__file__).resolve().parent.parent / "data"
levels, cutoffs = defaultdict(list), defaultdict(list)
with gzip.open(data / "soil_levels.csv.gz", "rt") as f:
    for r in csv.DictReader(f):
        if not r["tray_id"]:  # a tray found without its tag: no identity, left out
            continue
        key = (int(r["tray_id"]), r["taken_at"][:10])
        levels[key].append(float(r["soil_level"]))
        cutoffs[key].append(float(r["lower_cutoff"]))

FULL_DAY = 300  # counted photos; a lit day is about 840, fewer marks a part day
daily = []
for (tray, day), v in sorted(levels.items()):
    a = np.array(v)
    daily.append([tray, day, len(a), *np.round(np.percentile(a, [50, 5, 95]), 3)])
with open(data / "per_tray_day.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["tray", "day", "photos", "median", "p05", "p95"])
    w.writerows(daily)

head = ["tray", "photos", "first_full", "med", "last_full", "med", "change", "max_day_med", "min", "max", ">=-0.04", ">-0.115", "off_floor"]
out = []
for tray in sorted({k[0] for k in levels}):
    a = np.concatenate([levels[k] for k in levels if k[0] == tray])
    c = np.concatenate([cutoffs[k] for k in cutoffs if k[0] == tray])
    full = [d for d in daily if d[0] == tray and d[2] >= FULL_DAY]
    out.append([tray, len(a), full[0][1], full[0][3], full[-1][1], full[-1][3], round(full[-1][3] - full[0][3], 3),
                max(d[3] for d in full), round(a.min(), 3), round(a.max(), 3),
                int((a >= -0.04 - 1e-9).sum()), int((a > -0.115 + 1e-9).sum()), int((c > -0.045 + 1e-9).sum())])
with open(data / "per_tray.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(head)
    w.writerows(out)
print("\t".join(head))
for r in out:
    print("\t".join(str(x) for x in r))
