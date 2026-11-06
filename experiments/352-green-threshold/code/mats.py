"""#352, metrology log 24.4: the green squares on tray 7, before (11:06 to 11:41 UTC, on grey backing)
and after (11:47 to 12:17 UTC, on 1.5 mm blue mats), 2026-11-05. Per square and photo: area under the
current rule, zero cutoff not blue, and grow from cores. Also colour samples of plastic, mat, squares."""
import json, os, csv
import numpy as np, cv2

M = '/home/pi/scratch/thr-352/mats/'; V = '/home/pi/scratch/sam297/352-mats/'
TAG_K = np.ones((61, 61), np.uint8)
SIZES = {10: 98.84, 20: 398.30, 40: 1597.94, 55: 3020.97}  # mean calliper area of each size (18.5)
caps = {}
for f, phase in (('db_before.json', 'before'), ('db_after.json', 'after')):
    for v in json.load(open(M + f)).values():
        t = v['cap']['taken_at'][11:16]
        if v['visit'] or not v['readings']:
            continue
        if phase == 'before' and not ('11:06' <= t <= '11:41'):
            continue
        if phase == 'after' and not ('11:47' <= t <= '12:17'):
            continue
        caps[v['cap']['id']] = (phase, v)


def exg_of(sub):
    b, g, r = (sub[..., i].astype(np.float32) for i in range(3))
    return b, g, r, (2 * g - r - b) / (r + g + b + 1e-6)


rows, colour = [], {'plastic': [], 'mat': [], 'square': []}
for cid, (phase, v) in sorted(caps.items()):
    rd = v['readings'][0]
    mm2 = rd['area_mm2'] / rd['plant_px'] if rd['plant_px'] else 0.0408
    o = np.array(json.loads(rd['outline']))
    img = cv2.imread(M + 'stills/' + v['cap']['path'].split('/')[-1] + '.jpg')
    H, W = img.shape[:2]
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0); x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
    sub = img[y0:y1, x0:x1]
    b, g, r, exg = exg_of(sub)
    ins = np.zeros(sub.shape[:2], np.uint8); cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1); ins = ins > 0
    white = ((np.minimum(np.minimum(r, g), b) > 140) & (np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b) < 25)).astype(np.uint8)
    nw_, wl, wst, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    big_white = np.isin(wl, [k for k in range(1, nw_) if wst[k, cv2.CC_STAT_AREA] >= 5000])
    tag = cv2.dilate(big_white.astype(np.uint8), TAG_K) > 0  # tag paper: large colourless white pieces, widened 30 px
    notblue = ~((b > r) & (b > g))
    cur = (exg > 0.1) & (g > r) & ins
    zero = (exg > 0) & notblue & ins & ~tag
    low = ((exg > -0.045) & notblue & ins & ~tag).astype(np.uint8)
    n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool); keep[np.unique(lab[cur & ~tag])] = True; keep[0] = False
    grow = keep[lab]
    # Squares: bright and green, pieces of at least 1500 px (about 60 mm2), only to find where each is.
    sq = ((g > 150) & (exg > 0.05) & ins).astype(np.uint8)
    ns, sl, st, cen = cv2.connectedComponentsWithStats(sq, connectivity=8)
    for k in range(1, ns):
        if st[k, cv2.CC_STAT_AREA] < 1500:
            continue
        bx, by, bw, bh = st[k, :4]
        X0, Y0, X1, Y1 = max(bx - 25, 0), max(by - 25, 0), bx + bw + 25, by + bh + 25
        a_px = st[k, cv2.CC_STAT_AREA]
        size = min(SIZES, key=lambda s: abs(SIZES[s] - a_px * mm2))
        rows.append(dict(phase=phase, capture_id=cid, t=v['cap']['taken_at'][11:19], cx=round(x0 + cen[k][0]), cy=round(y0 + cen[k][1]),
                         size=size, calliper=SIZES[size],
                         current=round(cur[Y0:Y1, X0:X1].sum() * mm2, 2), zero_not_blue=round(zero[Y0:Y1, X0:X1].sum() * mm2, 2),
                         grow=round(grow[Y0:Y1, X0:X1].sum() * mm2, 2)))
        if len(colour['square']) < 20000:
            yy, xx = np.nonzero(cv2.erode((sl == k).astype(np.uint8), np.ones((9, 9), np.uint8)))
            colour['square'] += list(zip(r[yy, xx], g[yy, xx], b[yy, xx]))[::20]
    # Colour samples on the 12:00 photo only: plastic (blue, outside every pot), mat (blue inside pots, after).
    if v['cap']['taken_at'][11:16] in ('11:30', '12:00'):
        blue = (b > r) & (b > g) & ins & ~tag
        if phase == 'before':
            blue_before = cv2.dilate(blue.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0  # plastic, widened 7 px
            sel = blue
        else:
            sel = blue & ~blue_before & ~cv2.dilate(sq, np.ones((15, 15), np.uint8)).astype(bool)  # blue now, not before: mat
        yy, xx = np.nonzero(sel)
        colour['plastic' if phase == 'before' else 'mat'] += list(zip(r[yy, xx], g[yy, xx], b[yy, xx]))[::50]
with open(M + 'per_square_photo.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
np.savez(M + 'colour_samples.npz', **{k: np.array(v, np.float32) for k, v in colour.items()})
print(len(rows), 'square readings;', {k: len(v) for k, v in colour.items()}, 'colour samples')
