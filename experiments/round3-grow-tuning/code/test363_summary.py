"""#363 log 34 phase 2: summaries of test_cells.csv and outlines.csv (written by test363.py).
Means of IoU per subset; pooled area ratio = sum method px / sum truth px. A28 (empty truth) apart."""
import csv, sys
import numpy as np
d = sys.argv[1]
G = lambda s: 'blue mat' if s.startswith('blue mat') else ('size' if s.startswith('size') else s)
rows = [r for r in csv.DictReader(open(f'{d}/test_cells.csv'))]
out = []
def summ(sub):
    return dict(n=len(sub), mean_iou=round(float(np.mean([float(r['iou']) for r in sub])), 4),
                median_ratio=round(float(np.median([float(r['ratio']) for r in sub])), 3),
                pooled_ratio=round(sum(int(r['method_px']) for r in sub) / sum(int(r['truth_px']) for r in sub), 3))
for m in ('present', 'chosen', 'fixed'):
    rs = [r for r in rows if r['method'] == m and int(r['truth_px']) > 0]
    subsets = [('all', rs), ('prod', [r for r in rs if r['rig'] == 'prod']), ('dev', [r for r in rs if r['rig'] == 'dev']),
               ('corrected', [r for r in rs if r['truth_source'].startswith('corrected')]),
               ('accepted', [r for r in rs if r['truth_source'].startswith('draft')])]
    for g in sorted({G(r['stratum']) for r in rs}):
        subsets.append((f'group {g}', [r for r in rs if G(r['stratum']) == g]))
    for rig in ('prod', 'dev'):
        for s in ('corrected', 'draft'):
            subsets.append((f'{rig} {s}', [r for r in rs if r['rig'] == rig and r['truth_source'].startswith(s)]))
    for name, sub in subsets:
        if sub:
            out.append(dict(method=m, subset=name, **summ(sub)))
    for r in rows:
        if r['method'] == m and int(r['truth_px']) == 0:
            out.append(dict(method=m, subset=f"{r['id']} empty truth: false plant share of crop", n=1,
                            mean_iou='', median_ratio='', pooled_ratio=round(int(r['method_px']) / int(r['crop_px']), 4)))
o = [r for r in csv.DictReader(open(f'{d}/outlines.csv'))]
for m in ('present', 'chosen', 'fixed'):
    for p in ('1', '2'):
        sub = [r for r in o if r['method'] == m and r['vs_pass'] == p]
        iou = [float(r['iou']) for r in sub]; ra = [float(r['ratio']) for r in sub]
        out.append(dict(method=m, subset=f'15 outlines vs pass {p}', n=len(sub), mean_iou=round(float(np.mean(iou)), 4),
                        median_ratio=round(float(np.median(ra)), 3),
                        pooled_ratio=round(sum(int(r['method_px']) for r in sub) / sum(int(r['truth_px']) for r in sub), 3),
                        iou_range=f'{min(iou):.3f} to {max(iou):.3f}', ratio_range=f'{min(ra):.3f} to {max(ra):.3f}'))
sub = [r for r in o if r['method'] == 'present' and r['vs_pass'] == '1']
rep = [float(r['person_repeat_iou']) for r in sub]; rr = [float(r['pass2_over_pass1']) for r in sub]
out.append(dict(method='person', subset='pass 2 vs pass 1', n=len(sub), mean_iou=round(float(np.mean(rep)), 4),
                median_ratio=round(float(np.median(rr)), 3), pooled_ratio='', iou_range=f'{min(rep):.3f} to {max(rep):.3f}',
                ratio_range=f'{min(rr):.3f} to {max(rr):.3f}'))
keys = ['method', 'subset', 'n', 'mean_iou', 'median_ratio', 'pooled_ratio', 'iou_range', 'ratio_range']
with open(f'{d}/test_summary.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(out)
for r in out:
    print('\t'.join(str(r.get(k, '')) for k in keys))
