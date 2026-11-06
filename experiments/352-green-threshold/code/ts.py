"""#352, metrology log 24.3: grow from cores as a time series. Usage: ts.py <db_windows.json> <stills dir>
<out.csv> <worker> <workers>. Each worker takes every <workers>-th photo; plant regions are found
on each window's first photo (every worker finds the same ones). Only numpy and OpenCV."""
import sys, json, time, os, csv
import numpy as np
import cv2

dbf, sdir, outf, wk, nw = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
db = json.load(open(dbf))
caps = sorted(db.values(), key=lambda v: v['cap']['taken_at'])
TAG_K = np.ones((61, 61), np.uint8)
JOIN_K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))


def path(v):
    return os.path.join(sdir, v['cap']['path'].split('/stills/')[1] + '.jpg')


def box(outline, W, H, pad=0):
    o = np.array(json.loads(outline))
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int) - pad, 0)
    x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1 + pad, [W, H])
    return o, x0, y0, x1, y1


def rules(sub, o, x0, y0):
    b, g, r = (sub[..., i].astype(np.float32) for i in range(3))  # OpenCV reads B G R
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    ins = np.zeros(sub.shape[:2], np.uint8)
    cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    ins = ins.astype(bool)
    tag = cv2.dilate((np.minimum(np.minimum(r, g), b) > 140).astype(np.uint8), TAG_K) > 0
    A_app = (exg > 0.1) & (g > r) & ins           # the current rule as the app runs it (tag not left out)
    A = A_app & ~tag
    C = (exg > 0) & ~((b > r) & (b > g)) & ~tag & ins
    E = ((exg > -0.045) & ~((b > r) & (b > g)) & ~tag & ins).astype(np.uint8)
    n, lab = cv2.connectedComponents(E, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool); keep[np.unique(lab[A])] = True; keep[0] = False
    return dict(A_app=A_app, A=A, C=C, F=keep[lab])


# Plant regions per window and tray, from the window's first photo, in that photo's tray-box coordinates.
regions = {}
for day in sorted({v['cap']['taken_at'][:10] for v in caps}):
    first = next(v for v in caps if v['cap']['taken_at'][:10] == day and not (v['exclusion'] or {}).get('name'))
    img = cv2.imread(path(first)); H, W = img.shape[:2]
    for rd in first['readings']:
        if rd['tray_id'] is None or rd['placement'] != 'placed':
            continue
        o, x0, y0, x1, y1 = box(rd['outline'], W, H, pad=40)
        m = rules(img[y0:y1, x0:x1], o, x0, y0)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m['C'].astype(np.uint8), connectivity=8)
        big = np.isin(lab, [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] >= 150])
        rn, rl = cv2.connectedComponents(cv2.dilate(big.astype(np.uint8), JOIN_K), connectivity=8)
        regions[(day, rd['tray_id'])] = dict(x0=x0, y0=y0, cx=float(np.mean(o[:, 0])), cy=float(np.mean(o[:, 1])), lab=rl, n=rn - 1)

rows = []
mine = [v for i, v in enumerate(caps) if i % nw == wk]
t_all = time.perf_counter()
for v in mine:
    t0 = time.perf_counter()
    day = v['cap']['taken_at'][:10]
    img = cv2.imread(path(v)); H, W = img.shape[:2]
    for rd in v['readings']:
        key = (day, rd['tray_id'])
        if key not in regions or rd['placement'] != 'placed':
            continue
        R = regions[key]
        mm2 = rd['area_mm2'] / rd['plant_px'] if rd['plant_px'] else 0.0408
        o = np.array(json.loads(rd['outline']))
        dx, dy = float(np.mean(o[:, 0])) - R['cx'], float(np.mean(o[:, 1])) - R['cy']
        # Same box as the first photo, moved with the tray, so the plant regions line up.
        x0 = R['x0'] + int(round(dx)); y0 = R['y0'] + int(round(dy))
        h, w = R['lab'].shape
        x0c, y0c = max(x0, 0), max(y0, 0); x1c, y1c = min(x0 + w, W), min(y0 + h, H)
        sub = np.zeros((h, w, 3), np.uint8); sub[y0c - y0:y1c - y0, x0c - x0:x1c - x0] = img[y0c:y1c, x0c:x1c]
        m = rules(sub, o, x0, y0)
        row = dict(capture_id=v['cap']['id'], taken_at=v['cap']['taken_at'], day=day, tray=rd['tray_id'],
                   visit=(v['exclusion'] or {}).get('name') == 'visit', exposure_us=v['cap']['exposure_us'],
                   shift_px=round((dx * dx + dy * dy) ** 0.5, 1), stored_mm2=rd['area_mm2'],
                   current_mm2=round(m['A_app'].sum() * mm2, 2), grow_mm2=round(m['F'].sum() * mm2, 2),
                   zero_nb_mm2=round(m['C'].sum() * mm2, 2))
        pl = np.bincount(R['lab'][m['F']].ravel(), minlength=R['n'] + 1)
        row['plants_lost'] = int((pl[1:] == 0).sum()); row['plants'] = R['n']
        row['plant_grow_px'] = json.dumps(pl[1:].tolist())
        rows.append(row)
    rows[-1]['photo_s'] = round(time.perf_counter() - t0, 2)
with open(outf, 'w', newline='') as fh:
    keys = list(dict.fromkeys(k for r in rows for k in r))
    wr = csv.DictWriter(fh, fieldnames=keys); wr.writeheader(); wr.writerows(rows)
print(f'worker {wk}: {len(mine)} photos in {time.perf_counter() - t_all:.0f} s')
