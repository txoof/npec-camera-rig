"""#375 case 1: how much of a real plant's counted area is blue tray plastic (B/G >= 1)."""
import csv, statistics as st
from collections import defaultdict
idx = {}
for r in csv.DictReader(open('data/index.csv')):
    k = (r['rig'], r['experiment_id'], r['tray_id'], r['cell'], r['taken_at_utc'])
    idx[k] = r
tot = defaultdict(float); blue = defaultdict(float)
for p in csv.DictReader(open('solutions/e-colour-shape/pieces.csv')):
    k = (p['rig'], p['experiment_id'], p['tray_id'], p['cell'], p['taken_at_utc'])
    a = float(p['area_px'])
    tot[k] += a
    if float(p['b_over_g']) >= 1: blue[k] += a
groups = defaultdict(list)
for k, r in idx.items():
    if r['label_outcome'] != 'plant' or r['label_visible_plant'] != 'True': continue
    mmpx = float(r['mm_per_px_calibration'])
    t = tot.get(k, 0.0)
    if t == 0: continue
    d = int(r['day_since_grow_start'])
    span = '0-2' if d <= 2 else '3-6' if d <= 6 else '7-13' if d <= 13 else '14+'
    groups[(r['rig'], span)].append((blue.get(k, 0) / t, blue.get(k, 0) * mmpx**2, t * mmpx**2))
w = csv.writer(open('case1/blue_share_by_day.csv', 'w'))
w.writerow(['rig','days','pictures','green mm2 median','blue mm2 median','blue mm2 p90','blue share median %','blue share p90 %','pictures with any blue %'])
for g in sorted(groups):
    v = groups[g]; sh = sorted(x[0] for x in v); bm = sorted(x[1] for x in v)
    p90 = lambda s: s[int(0.9 * (len(s) - 1))]
    row = [*g, len(v), round(st.median(x[2] for x in v), 1), round(st.median(bm), 2), round(p90(bm), 2),
           round(100 * st.median(sh), 2), round(100 * p90(sh), 2), round(100 * sum(x > 0 for x in sh) / len(sh), 1)]
    w.writerow(row); print(row)
