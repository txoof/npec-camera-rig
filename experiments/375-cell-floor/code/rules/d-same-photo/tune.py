"""Tune helper: seedling recall on the tune set and a fringe proxy (tune pots' own wall bands,
days 0 to 6, judged as if they were a core) for one setting."""
import csv, sys, subprocess, numpy as np
from collections import defaultdict
v, Q, KP, KQ, ST = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
F = {r['key']: r for r in csv.DictReader(open('features.csv'))}
rows = list(csv.DictReader(open('../../data/index.csv')))
g = defaultdict(list)
for r in rows:
    r['f'] = F['|'.join([r['rig'], r['experiment_id'], r['tray_id'], r['cell'], r['taken_at_utc']])]
    g[(r['rig'], r['capture_id']) + ((r['tray_id'],) if v == 'B' else ())].append(r)
res = defaultdict(lambda: [0, 0, 0])
for m in g.values():
    ref = np.array([float(x['f'][('core_' if v == 'C' else 'wall_') + ST]) for x in m])
    med = np.median(ref); S = max(1.4826 * np.median(abs(ref - med)), 1e-3)
    if v in ('E','D'): S = max((med - np.percentile(ref, 25)) / 0.6745, 1e-3); Fq = np.percentile(ref, Q)
    if v == 'F': Fq = np.percentile(ref, 25); S = max((Fq - np.percentile(ref, 5)) / 0.9704, 1e-3)
    for x in m:
        if not (x['rig'] == 'prod' and int(x['tray_id']) <= 6): continue
        d = int(x['day_since_grow_start'])
        for name, val in (('core', x['f']['core_' + ST]), ('wallproxy', x['f']['wall_' + ST])):
            if name == 'wallproxy' and d > 6: continue
            grp = name if name == 'wallproxy' else ('d0' if d == 0 else 'd1-2' if d <= 2 else 'd3-6' if d <= 6 else 'd7-13' if d <= 13 else 'd14+')
            if x['label_visible_plant'] != 'True' and name == 'core': grp = 'notvisible'
            z = (float(val) - Fq) / S
            res[grp][0] += 1; res[grp][1] += z > KP; res[grp][2] += z > KQ
print(v, Q, KP, KQ, ST, '  '.join(f"{k}: {100*a/n:.0f}/{100*b/n:.0f}" for k, (n, a, b) in sorted(res.items())))
