import csv, json, glob
import numpy as np
rows = [r for f in sorted(glob.glob('/home/pi/scratch/thr-352/ts/part*.csv')) for r in csv.DictReader(open(f))]
rows = [r for r in rows if r['visit'] != 'True']
print('rows', len(rows), 'photos', len({r['capture_id'] for r in rows}), 'max tray shift px', max(float(r['shift_px']) for r in rows))
days = sorted({r['day'] for r in rows})
pt = [float(r['photo_s']) for r in rows if r.get('photo_s')]
print('time per photo (3 at once, then 1):', f'median {np.median(pt):.2f} s, max {max(pt):.2f} s')


def med15(x):
    return np.array([np.median(x[max(0, i - 7):i + 8]) for i in range(len(x))])


print('\n1. Plants lost by grow from cores, share of photos, per window')
for d in days:
    loss, nreg = [], 0
    for t in range(1, 8):
        rr = sorted([r for r in rows if r['day'] == d and r['tray'] == str(t)], key=lambda r: r['taken_at'])
        if not rr: continue
        P = np.array([json.loads(r['plant_grow_px']) for r in rr])
        lost = (P == 0).mean(0); nreg += P.shape[1]
        loss += [(t, i + 1, l) for i, l in enumerate(lost)]
    l = np.array([x[2] for x in loss])
    print(f'  {d}: {nreg} plant regions; never lost {int((l == 0).sum())}; lost in under 5% {int(((l > 0) & (l < 0.05)).sum())}; '
          f'5 to 50% {int(((l >= 0.05) & (l < 0.5)).sum())}; 50% or more {int((l >= 0.5).sum())}; worst ' +
          ', '.join(f'tray {a} plant {b} {c:.0%}' for a, b, c in sorted(loss, key=lambda x: -x[2])[:4]))

print('\n2 and 3. Per tray and window: mean mm2, photo-to-photo sd as % of mean, and after a 15-photo median')
print(f'  {"day":10s} tray  n  {"current":>8s} {"sd%":>5s} {"med15 sd%":>9s}  {"grow":>7s} {"sd%":>5s} {"med15 sd%":>9s}  grow/current')
for d in days:
    for t in range(1, 8):
        rr = sorted([r for r in rows if r['day'] == d and r['tray'] == str(t)], key=lambda r: r['taken_at'])
        if not rr: continue
        a = np.array([float(r['current_mm2']) for r in rr]); g = np.array([float(r['grow_mm2']) for r in rr])
        sd = lambda x: 100 * x.std(ddof=1) / x.mean()
        print(f'  {d} {t:4d} {len(rr):3d} {a.mean():8.0f} {sd(a):5.1f} {sd(med15(a)):9.1f}  {g.mean():7.0f} {sd(g):5.1f} {sd(med15(g)):9.1f}  {g.mean() / a.mean():6.2f}')
