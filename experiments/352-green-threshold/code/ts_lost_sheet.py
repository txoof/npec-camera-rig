"""#352: picture of every plant region that grow from cores loses in 20% or more of a window's photos,
on the window's first photo. Magenta: grow from cores. Yellow box: the region."""
import csv, json, glob, os, sys
import numpy as np, cv2
sys.argv = ['x', '/home/pi/scratch/thr-352/ts/db_windows.json', '/home/pi/scratch/thr-352/ts/stills', '/dev/null', '0', '100000']
src = open('/home/pi/scratch/thr-352/code/ts.py').read().split('rows = []')[0]  # the region-finding part of ts.py only
exec(src)
rows = [r for f in sorted(glob.glob('/home/pi/scratch/thr-352/ts/part*.csv')) for r in csv.DictReader(open(f)) if r['visit'] != 'True']
V = '/home/pi/scratch/sam297/352-timeseries/'; os.makedirs(V, exist_ok=True)
tiles = []
for (day, tray), R in sorted(regions.items()):
    rr = [r for r in rows if r['day'] == day and r['tray'] == str(tray)]
    if not rr: continue
    lost = (np.array([json.loads(r['plant_grow_px']) for r in rr]) == 0).mean(0)
    first = next(v for v in caps if v['cap']['taken_at'][:10] == day and not (v['exclusion'] or {}).get('name'))
    img = cv2.imread(path(first)); h, w = R['lab'].shape
    sub = img[R['y0']:R['y0'] + h, R['x0']:R['x0'] + w].copy()
    rd = next(r for r in first['readings'] if r['tray_id'] == tray)
    m = rules(sub, np.array(json.loads(rd['outline'])), R['x0'], R['y0'])['F']
    for k in range(1, R['n'] + 1):
        if lost[k - 1] < 0.2: continue
        ys, xs = np.nonzero(R['lab'] == k)
        y0, y1, x0, x1 = max(ys.min() - 20, 0), ys.max() + 20, max(xs.min() - 20, 0), xs.max() + 20
        c = sub[y0:y1, x0:x1].copy(); mm = m[y0:y1, x0:x1]
        c[mm] = (0.3 * c[mm] + 0.7 * np.array([255, 0, 255])).astype(np.uint8)
        c = cv2.resize(c, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        c = cv2.copyMakeBorder(c, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(c, f'{day[5:]} tray {tray} plant {k}: lost {lost[k-1]:.0%}', (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        tiles.append(c)
print(len(tiles), 'regions lost in 20% or more')
side = 300
tiles = [cv2.resize(t, (side, int(t.shape[0] * side / t.shape[1]))) if t.shape[1] > side else cv2.copyMakeBorder(t, 0, 0, 0, side - t.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
cols = 5; rowsimg = []
for i in range(0, len(tiles), cols):
    row = tiles[i:i + cols]; hh = max(t.shape[0] for t in row)
    row = [cv2.copyMakeBorder(t, 0, hh - t.shape[0] + 10, 0, 10, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in row]
    while len(row) < cols: row.append(np.full((hh + 10, side + 10, 3), 255, np.uint8))
    rowsimg.append(np.hstack(row))
sheet = np.vstack(rowsimg)
sheet = cv2.copyMakeBorder(sheet, 0, 40, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
cv2.putText(sheet, '#352 regions grow from cores loses in 20%+ of photos; first photo of each window; magenta = grow from cores; 2x', (6, sheet.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
cv2.imwrite(V + 'lost_regions.png', sheet)
