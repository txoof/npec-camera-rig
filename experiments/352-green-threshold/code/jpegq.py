"""#352, metrology log 24.6: current rule and grow from cores on the #355 same-frame stills, each JPEG
setting against the uncompressed frame. One full-size frame in memory at a time; trays by box."""
import json, csv
import numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
J = '/home/pi/scratch/thr-352/jpegq/'
TAG_K = np.ones((61, 61), np.uint8)
SETTINGS = {'B': '75, 4:2:0 (today)', 'C': '85, 4:2:0', 'D': '95, 4:2:0', 'F': '75, 4:4:4', 'G': '85, 4:4:4', 'H': '90, 4:4:4', 'E': '95, 4:4:4'}
trays = json.load(open(J + 'trays.json'))['trays']


def rules(sub, ins):
    r, g, b = (sub[..., i].astype(np.float32) for i in range(3))  # R G B
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    mn, mx = np.minimum(np.minimum(r, g), b), np.maximum(np.maximum(r, g), b)
    white = ((mn > 140) & (mx - mn < 25)).astype(np.uint8)
    n, wl, st, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    tag = cv2.dilate(np.isin(wl, [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] >= 5000]).astype(np.uint8), TAG_K) > 0
    cur = (exg > 0.1) & (g > r) & ins & ~tag
    low = ((exg > -0.045) & ~((b > r) & (b > g)) & ins & ~tag).astype(np.uint8)
    n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool); keep[np.unique(lab[cur])] = True; keep[0] = False
    return {'current': cur, 'grow': keep[lab]}


def per_tray(rgb):
    H, W = rgb.shape[:2]; out = {}
    for t in trays:
        o = np.array(t['outline'])
        x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0); x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
        ins = np.zeros((y1 - y0, x1 - x0), np.uint8); cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
        out[t['tray_id']] = rules(np.ascontiguousarray(rgb[y0:y1, x0:x1]), ins > 0)
    return out


rows = []
for i in range(3):
    ref = per_tray(np.load(J + f'frame{i}.npy', mmap_mode='r'))
    for s in SETTINGS:
        m = per_tray(np.asarray(Image.open(J + f'frame{i}_{s}.jpg').convert('RGB')))
        for tid in ref:
            row = dict(frame=i, setting=s, tray=tid)
            for k in ('current', 'grow'):
                a, b = ref[tid][k], m[tid][k]
                row[f'{k}_ref_px'] = int(a.sum()); row[f'{k}_ratio'] = round(b.sum() / max(a.sum(), 1), 4)
                row[f'{k}_iou'] = round((a & b).sum() / max((a | b).sum(), 1), 4)
            rows.append(row)
        print('frame', i, 'setting', s, 'done', flush=True)
with open(J + 'grow_vs_uncompressed.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f'\n{"setting":20s} | {"current: area / uncompressed":>32s} {"IoU":>6s} | {"grow from cores: area / uncompressed":>38s} {"IoU":>6s}')
for s, name in SETTINGS.items():
    rr = [r for r in rows if r['setting'] == s]
    f = lambda k: np.array([r[k] for r in rr])
    cr, gr = f('current_ratio'), f('grow_ratio')
    print(f'{s} {name:18s} | {cr.mean():.4f} ({cr.min():.3f} to {cr.max():.3f}) {f("current_iou").mean():>12.3f} | {gr.mean():.4f} ({gr.min():.3f} to {gr.max():.3f}) {f("grow_iou").mean():>18.3f}')
