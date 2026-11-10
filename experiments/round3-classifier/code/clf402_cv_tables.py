"""#402 phase 1: tables from cv_cells.csv (training days only) for the chosen forest, rule H's
draft and the current rule, per rig and per stratum, and per cell.

  python clf402_cv_tables.py RUN   -> RUN/cv_tables.txt
"""
import csv
import json
import sys

import numpy as np


def num(v):
    return None if v in ('', 'None') else float(v)


def stats(rs):
    ious = [num(r['iou']) for r in rs if num(r['iou']) is not None]
    ar = [num(r['area_ratio']) for r in rs if num(r['area_ratio']) is not None]
    fp = [num(r['false_plant_share']) for r in rs if num(r['false_plant_share']) is not None]
    s = f'n={len(rs):2d}'
    if ious:
        s += f'  IoU mean {np.mean(ious):.3f} min {np.min(ious):.3f}'
        s += f'  area ratio mean {np.mean(ar):.3f} [{np.min(ar):.3f}, {np.max(ar):.3f}]'
    if fp:
        s += f'  empty cells {len(fp)}: false plant share mean {np.mean(fp):.5f} max {np.max(fp):.5f}'
    return s


def main(run):
    ch = json.load(open(f'{run}/cv_pick.json'))['chosen']
    rows = list(csv.DictReader(open(f'{run}/cv_cells.csv')))
    sel = {'forest (chosen)': [r for r in rows if r['method'] == 'forest' and r['trees'] == ch['trees']
                               and r['depth'] == ch['depth'] and r['leaf'] == ch['leaf']
                               and r['scales'] == ch['scales']
                               and r.get('balance', 'even') == ch['balance']],
           'rule H draft': [r for r in rows if r['method'] == 'rule H draft'],
           'current rule': [r for r in rows if r['method'] == 'current rule']}
    out = [f'chosen: {ch}', '']
    for title, key in (('ALL', lambda r: 'all'), ('PER RIG', lambda r: r['rig']),
                       ('PER RIG AND STRATUM', lambda r: f"{r['rig']} | {r['stratum']}")):
        out.append(f'== {title}')
        groups = sorted({key(r) for r in sel['rule H draft']})
        for g in groups:
            out.append(f'-- {g}')
            for m, rs in sel.items():
                out.append(f'   {m:16s} {stats([r for r in rs if key(r) == g])}')
        out.append('')
    out.append('== PER CELL (IoU / area ratio pred/truth, or false plant share when truth is empty)')
    ids = sorted({r['id'] for r in sel['rule H draft']})
    for i in ids:
        parts = []
        for m, rs in sel.items():
            r = [x for x in rs if x['id'] == i][0]
            if num(r['iou']) is None:
                parts.append(f"{m}: fp share {num(r['false_plant_share']):.5f}")
            else:
                parts.append(f"{m}: {num(r['iou']):.3f} / {num(r['area_ratio']):.3f}")
        r0 = [x for x in sel['rule H draft'] if x['id'] == i][0]
        out.append(f"{i} {r0['day']} {r0['stratum']:24s} truth {r0['truth_px']:>6s} px | " + ' | '.join(parts))
    txt = '\n'.join(out)
    open(f'{run}/cv_tables.txt', 'w').write(txt)
    print(txt)


if __name__ == '__main__':
    main(sys.argv[1])
