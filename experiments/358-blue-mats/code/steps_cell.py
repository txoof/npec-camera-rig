"""#358, metrology log 36: as steps.py, but each cell's before window ends 2 minutes before that
cell's own first matted photo (cell_timeline.csv) and leaves out photos with a glove in the cell.
Areas from production's saved readings after the Reprocess (cached by steps.py). After near:
09:14 to 09:27 UTC. Usage: steps_cell.py CELL_TIMELINE_CSV CACHE_DIR OUT_DIR"""
import csv, glob, json, os, statistics as st, sys
from collections import defaultdict

tl_csv, cache, out = sys.argv[1:4]
tl = list(csv.DictReader(open(tl_csv)))
first, glove = {}, set()
for x in sorted(tl, key=lambda x: x['t']):
    k = (int(x['tray']), x['cell'])
    if float(x['glove']) > 0:
        glove.add((x['t'], *k))
    if k not in first and float(x['blue']) > 0.5 and float(x['glove']) == 0:
        first[k] = x['t']
mins = lambda t: int(t[:2]) * 60 + int(t[3:5])
vals = defaultdict(list)
for f in sorted(glob.glob(os.path.join(cache, '*.json'))):
    t = os.path.basename(f)[11:13] + ':' + os.path.basename(f)[13:15]
    r = json.load(open(f))
    if not r or r.get('exclusion') == 'light changing':
        continue
    for tr in r['trays']:
        for c in tr['cells'] or []:
            k = (tr['tray_id'], c['cell'])
            if k not in first or c['holds'] != 'plant':
                continue
            if '08:30' <= t and mins(t) <= mins(first[k]) - 2 and (t, *k) not in glove:
                w = 'before'
            elif '09:14' <= t <= '09:27':
                w = 'near'
            else:
                continue
            vals[(*k, w)].append((c['area_mm2'], c['grown_area_mm2']))
rows, lines = [], []
for tray in (3, 6, 4, 5):
    for i, m in enumerate(('fixed', 'grown')):
        ch, used, nb = [], [], []
        pb = pa = 0
        for (tr, cell, w), v in sorted(vals.items()):
            if tr != tray or w != 'before':
                continue
            b = [x[i] for x in v if x[i] is not None]; a = [x[i] for x in vals.get((tr, cell, 'near'), []) if x[i] is not None]
            if len(b) < 1 or len(a) < 2:
                continue
            mb, ma = st.mean(b), st.mean(a)
            ch.append((ma / mb - 1) * 100); used.append(cell); nb.append(len(b)); pb += mb; pa += ma
            rows.append(dict(tray=tray, cell=cell, method=m, before_n=len(b), before=round(mb, 2), near=round(ma, 2), change_pct=round(ch[-1], 2)))
        missing = sorted(c for (tr, c) in first if tr == tray and c not in used)
        lines.append(f'{m} tray {tray}: cells {len(ch)}, change median {st.median(ch):+.1f}% (range {min(ch):+.1f} to {max(ch):+.1f}), '
                     f'pooled {(pa / pb - 1) * 100:+.1f}%, before photos per cell {min(nb)} to {max(nb)}; no before: {missing}')
with open(os.path.join(out, 'per_cell_own_window.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, rows[0].keys()); w.writeheader(); w.writerows(rows)
open(os.path.join(out, 'own_window_summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
