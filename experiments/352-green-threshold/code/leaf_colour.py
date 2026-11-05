"""#352: colour of the leaf pixels in the plant regions grow from cores lost in 20%+ of photos (24.3),
against all other plant regions. Leaf pixel: greenness > 0 and G > R (no blue test)."""
import csv, json, glob, sys
import numpy as np, cv2
sys.argv = ['x', '/home/pi/scratch/thr-352/ts/db_windows.json', '/home/pi/scratch/thr-352/ts/stills', '/dev/null', '0', '100000']
exec(open('/home/pi/scratch/thr-352/code/ts.py').read().split('rows = []')[0])
rows = [r for f in sorted(glob.glob('/home/pi/scratch/thr-352/ts/part*.csv')) for r in csv.DictReader(open(f)) if r['visit'] != 'True']
S = {'lost': [], 'kept': []}
for (day, tray), R in sorted(regions.items()):
    rr = [r for r in rows if r['day'] == day and r['tray'] == str(tray)]
    lost = (np.array([json.loads(r['plant_grow_px']) for r in rr]) == 0).mean(0)
    first = next(v for v in caps if v['cap']['taken_at'][:10] == day and not (v['exclusion'] or {}).get('name'))
    img = cv2.imread(path(first)); h, w = R['lab'].shape
    sub = img[R['y0']:R['y0'] + h, R['x0']:R['x0'] + w]
    b, g, r = (sub[..., i].astype(np.float32) for i in range(3)); s = r + g + b + 1e-6
    exg = (2 * g - r - b) / s
    leaf = (exg > 0) & (g > r)
    for k in range(1, R['n'] + 1):
        m = leaf & (R['lab'] == k)
        S['lost' if lost[k - 1] >= 0.2 else 'kept'] += list(((b[m] - g[m]) / s[m]))
for k, v in S.items():
    v = np.array(v)
    print(f'{k:5s} leaf px {len(v):7d} | B above G (fails not blue if B>R too) {100*np.mean(v > 0):5.1f}% | (B-G)/sum p1 p5 p50 p95 p99: ' + ' '.join(f'{x:+.3f}' for x in np.percentile(v, [1, 5, 50, 95, 99])))
