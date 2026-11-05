"""#352: each rule over whole trays 1 to 7 of the 3 Nov still, and the share of its pixels in
pieces under 30 px (about 1.2 mm2: specks, not plants). Picture of rule D on trays 6 and 7."""
import json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
Image.MAX_IMAGE_PIXELS = None
T = '/home/pi/scratch/thr-352/'; STEM = '2026-11-03_105853_597207'
VIEW = '/home/pi/scratch/sam297/352-compare/'
cap = json.load(open(T + 'prod/db_readings.json'))['19380']
reads = {r['tray_id']: r for r in cap['readings'] if r['outline']}
modes = {r['tray']: r for r in map(json.loads, open(T + 'rows.jsonl')) if r['stem'] == STEM}
rgb = np.asarray(Image.open(T + f'prod/{STEM}.jpg').convert('RGB'))
H, W = rgb.shape[:2]


def specks(m, maxpx=30):
    """Pixels of m in 8-connected pieces under maxpx, by flood fill on a label image."""
    lab = Image.fromarray(m.astype(np.int32), mode='I')
    small, k = 0, 2
    a = np.asarray(lab)
    ys, xs = np.nonzero(a == 1)
    done = np.zeros(m.shape, bool)
    for y, x in zip(ys, xs):
        if done[y, x]:
            continue
        ImageDraw.floodfill(lab, (int(x), int(y)), k)
        sel = np.asarray(lab) == k
        done |= sel
        n = int(sel.sum())
        if n < maxpx:
            small += n
        k += 1
    return small


print('tray  half   A_mm2   B_mm2   C_mm2   D_mm2   D/C   D_specks%  C_specks%')
for t in range(1, 8):
    rd = reads[t]; mm2 = rd['area_mm2'] / rd['plant_px'] if rd['plant_px'] else 0.0408
    o = np.array(json.loads(rd['outline']))
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0); x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
    sub = rgb[y0:y1, x0:x1].astype(np.float32); r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    pim = Image.new('L', (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(pim).polygon([(float(a - x0), float(c - y0)) for a, c in o], fill=1)
    ins = np.asarray(pim).astype(bool)
    exg = (2 * g - r - b) / (r + g + b + 1e-6); nb = ~((b > r) & (b > g))
    md = modes[t]; half = (md['soil_mode'] + md['leaf_mode']) / 2 if md['leaf_mode'] is not None else None
    m = {'A': (exg > 0.1) & (g > r), 'B': (exg > 0) & (g > r), 'C': (exg > 0) & nb}
    m['D'] = (exg > half) & nb if half is not None else None
    a = {k: (v & ins).sum() * mm2 if v is not None else float('nan') for k, v in m.items()}
    sc = specks(m['C'] & ins) / max((m['C'] & ins).sum(), 1)
    sd = specks(m['D'] & ins) / max((m['D'] & ins).sum(), 1) if half is not None else float('nan')
    print(f'{t:4d} {half if half is not None else float("nan"):6.3f} {a["A"]:7.0f} {a["B"]:7.0f} {a["C"]:7.0f} {a["D"]:7.0f} {a["D"]/a["C"]:5.2f} {100*sd:9.1f} {100*sc:9.1f}')
    if t in (6, 7) and half is not None or t == 7:
        hh = half if half is not None else -0.05
        mk = (exg > hh) & nb & ins
        im = rgb[y0:y1, x0:x1].copy(); im[mk] = (0.3 * im[mk] + 0.7 * np.array([255, 0, 255])).astype(np.uint8)
        Image.fromarray(im).reduce(2).save(VIEW + f'tray{t}_ruleD_half.png')
