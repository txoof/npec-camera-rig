"""#363, log 34: the choice rule on TRAINING summaries (score363 *_summary.csv files, row 0 of the first
file is the present setting).
1. Eligible: a setting whose gain in mean IoU on the corrected training cells over the present one
   is at least its loss in mean IoU on the accepted-draft training cells (the present one is eligible).
2. Best: the eligible setting with the highest mean IoU over all training cells of both rigs.
3. Within 0.005 of the best's mean IoU, the one whose pooled area ratio on the blue-mat cells is
   closest to 1 is chosen (ties: higher mean IoU). Runner-up: the next in the same order."""
import csv
import sys

KEYS = ['core', 'gr', 'gap', 'floor', 'blue', 'edge', 'fill', 'sigma']
rows, seen = [], set()
for i, f in enumerate(sys.argv[1:]):
    for r in csv.DictReader(open(f)):
        k = tuple(r[c] for c in KEYS)
        if k in seen:
            continue
        seen.add(k)
        r['src'] = f.split('/')[-1].split('_')[0]
        for c in r:
            if c.endswith(('_iou', '_ratio')):
                r[c] = float(r[c]) if r[c] not in ('', 'None') else None
        rows.append(r)
p = rows[0]
assert p['varied'] == 'present'
for r in rows:
    r['gain_corr'] = r['corrected_iou'] - p['corrected_iou']
    r['loss_acc'] = p['accepted_iou'] - r['accepted_iou']
    r['eligible'] = r['gain_corr'] >= r['loss_acc'] - 1e-12
el = sorted([r for r in rows if r['eligible']], key=lambda r: -r['all_iou'])
best = el[0]
near = [r for r in el if best['all_iou'] - r['all_iou'] <= 0.005]
order = sorted(near, key=lambda r: (abs(r['mat_ratio'] - 1), -r['all_iou'])) + [r for r in el if r not in near]
top_raw = max(rows, key=lambda r: r['all_iou'])
print('settings compared', len(rows), 'eligible', len(el), 'within 0.005 of best', len(near))
print('highest mean IoU of any setting', top_raw['src'], top_raw['setting'], top_raw['all_iou'], 'eligible', top_raw['eligible'])
cols = KEYS + ['all_iou', 'corrected_iou', 'accepted_iou', 'prod_iou', 'dev_iou', 'mat_iou', 'mat_ratio',
               'all_ratio', 'corrected_ratio', 'accepted_ratio', 'gain_corr', 'loss_acc']
print('\t'.join(['which', 'src', 'setting'] + cols))
for lab, r in [('chosen', order[0]), ('runner-up', order[1]), ('present', p)] + [('near', r) for r in near[:15]]:
    print('\t'.join([lab, r['src'], r['setting']] + [str(round(r[c], 4)) if isinstance(r[c], float) else str(r[c]) for c in cols]))
