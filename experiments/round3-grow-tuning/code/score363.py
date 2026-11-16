"""#363, log 34: summaries of a sweep's per-cell scores (TRAINING cells only).
  score363.py GRID.json SCORES.csv MANIFEST_TRAIN.csv TRUTH_INDEX_TRAIN.csv OUT_PREFIX
writes OUT_PREFIX_summary.csv (one row per setting) and OUT_PREFIX_groups.csv (per rig and group).
IoU of a cell with neither method nor truth pixels counts as 1; area ratio = method px / truth px,
left out where the truth is empty. Pooled ratio = sum of method px / sum of truth px."""
import csv
import json
import sys

import numpy as np

KEYS = ['core', 'gr', 'gap', 'floor', 'blue', 'edge', 'fill', 'sigma']


def group(stratum):
    if stratum.startswith('blue mat'):
        return 'blue mat'
    if stratum.startswith('size'):
        return 'size ' + stratum.split()[1]
    return stratum


def stats(rows):
    if not rows:
        return dict(n=0)
    iou = [r['inter'] / r['union'] if r['union'] else 1.0 for r in rows]
    ratio = [r['method_px'] / r['truth_px'] for r in rows if r['truth_px'] > 0]
    tp = sum(r['truth_px'] for r in rows)
    return dict(n=len(rows), mean_iou=round(float(np.mean(iou)), 4),
                median_ratio=round(float(np.median(ratio)), 3) if ratio else None,
                pooled_ratio=round(sum(r['method_px'] for r in rows) / tp, 3) if tp else None)


def main(grid_f, scores_f, man_f, idx_f, prefix):
    grid = json.load(open(grid_f))
    man = {r['id']: r for r in csv.DictReader(open(man_f))}
    src = {r['id']: r['truth_source'] for r in csv.DictReader(open(idx_f))}
    assert all(r['split'] == 'train' for r in man.values())
    by = {}
    for r in csv.DictReader(open(scores_f)):
        r = {k: int(v) if k != 'id' else v for k, v in r.items()}
        m = man[r['id']]
        r.update(rig=m['rig'], group=group(m['stratum']),
                 src='corrected' if src[r['id']].startswith('corrected') else 'accepted')
        by.setdefault(r['setting'], []).append(r)
    summ, groups = [], []
    for si, s in enumerate(grid):
        rows = by[si]
        row = dict(setting=si, varied=s.get('varied', ''), **{k: s[k] for k in KEYS})
        for name, sub in (('all', rows), ('corrected', [r for r in rows if r['src'] == 'corrected']),
                          ('accepted', [r for r in rows if r['src'] == 'accepted']),
                          ('prod', [r for r in rows if r['rig'] == 'prod']), ('dev', [r for r in rows if r['rig'] == 'dev']),
                          ('mat', [r for r in rows if r['group'] == 'blue mat'])):
            st = stats(sub)
            row[f'{name}_n'] = st['n']
            row[f'{name}_iou'] = st.get('mean_iou')
            row[f'{name}_ratio'] = st.get('pooled_ratio')
            row[f'{name}_med_ratio'] = st.get('median_ratio')
        summ.append(row)
        for rig in ('prod', 'dev', 'both'):
            for g in sorted({r['group'] for r in rows}):
                for srcn in ('all', 'corrected', 'accepted'):
                    sub = [r for r in rows if (rig == 'both' or r['rig'] == rig) and r['group'] == g
                           and (srcn == 'all' or r['src'] == srcn)]
                    if sub:
                        groups.append(dict(setting=si, rig=rig, group=g, truth=srcn, **stats(sub)))
    for f, rows in ((prefix + '_summary.csv', summ), (prefix + '_groups.csv', groups)):
        with open(f, 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    p = summ[0]
    print('present: all IoU', p['all_iou'], 'corrected', p['corrected_iou'], 'accepted', p['accepted_iou'])
    cols = ['setting', 'varied'] + KEYS + ['all_iou', 'corrected_iou', 'accepted_iou', 'prod_iou', 'dev_iou',
                                           'mat_iou', 'mat_ratio', 'all_ratio', 'corrected_ratio']
    print('\t'.join(cols))
    for r in sorted(summ, key=lambda r: -r['all_iou'])[:int(sys.argv[6]) if len(sys.argv) > 6 else 400]:
        print('\t'.join(str(r[c]) for c in cols))


if __name__ == '__main__':
    main(*sys.argv[1:6])
