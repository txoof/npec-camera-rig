"""#402: compare one CV fold's per-cell rows from two runs (for example Pi vs Mac), row by row.

  python clf402_compare_folds.py A.csv B.csv rig day
"""
import csv
import sys

KEY = ('id', 'method', 'trees', 'depth', 'leaf', 'scales')
VALS = ('truth_px', 'pred_px', 'fp_px', 'fn_px', 'iou', 'area_ratio')


def load(p, rig, day):
    out = {}
    for r in csv.DictReader(open(p)):
        if r['rig'] != rig or r['day'] != day:
            continue
        if r['method'] == 'forest' and r.get('balance', 'even') != 'even':
            continue  # the Pi run had only 'even'
        out[tuple(r[k] for k in KEY)] = r
    return out


a, b = load(sys.argv[1], *sys.argv[3:5]), load(sys.argv[2], *sys.argv[3:5])
print('rows', len(a), len(b), 'common', len(set(a) & set(b)))
diff = 0
maxd = {'pred_px': 0, 'iou': 0.0}
for k in sorted(set(a) & set(b)):
    if any(a[k][v] != b[k][v] for v in VALS):
        diff += 1
        maxd['pred_px'] = max(maxd['pred_px'], abs(int(a[k]['pred_px']) - int(b[k]['pred_px'])))
        if a[k]['iou'] and b[k]['iou']:
            maxd['iou'] = max(maxd['iou'], abs(float(a[k]['iou']) - float(b[k]['iou'])))
        if diff <= 5:
            print('differs', k, {v: (a[k][v], b[k][v]) for v in VALS if a[k][v] != b[k][v]})
print('rows differing', diff, 'max |pred_px| diff', maxd['pred_px'], 'max |IoU| diff', maxd['iou'])
