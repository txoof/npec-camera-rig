"""#352: per-plant crops of one production still, for hand outlines in ImageJ (the reference).

Usage: imagej_crops.py <capture_id> <jpg> <tray> [<tray> ...]
Finds plants with a loose rule (greenness > 0, G > R, not blue), only to know where to cut.
Picks 5 plants per tray across the size range. Crops are native pixels, lossless TIFF, no
overlays, so the hand outline is independent of every rule under test. Writes
imagej/<stem>_t<tray>_p<k>.tif, imagej/manifest.csv (crop origin in the full frame and the mm2 per
px the app stored for that tray), and imagej/index.png (where each crop sits)."""
import sys, json, os, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

Image.MAX_IMAGE_PIXELS = None
OUT = '/home/pi/scratch/thr-352/'
DST = OUT + 'imagej/'
MARGIN = 40  # px around each plant
PER_TRAY = 5
os.makedirs(DST, exist_ok=True)

cid, jpg, trays = sys.argv[1], sys.argv[2], [int(t) for t in sys.argv[3:]]
stem = os.path.basename(jpg)[:-4]
cap = json.load(open(OUT + 'prod/db_readings.json'))[cid]
reads = {r['tray_id']: r for r in cap['readings'] if r['outline']}
rgb = np.asarray(Image.open(jpg).convert('RGB'))
H, W = rgb.shape[:2]

rows, boxes = [], []
for t in trays:
    rd = reads[t]
    o = np.array(json.loads(rd['outline']))
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
    sub = rgb[y0:y1, x0:x1].astype(np.float32)
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    pim = Image.new('L', (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(pim).polygon([(float(a - x0), float(c - y0)) for a, c in o], fill=1)
    ins = np.asarray(pim).astype(bool)
    m = (exg > 0) & (g > r) & ~((b > r) & (b > g)) & ins
    # Not on or next to the tag in cell A1 (white paper): its edge reads green.
    white = (np.minimum(np.minimum(r, g), b) > 140).astype(np.uint8) * 255
    near_tag = np.asarray(Image.fromarray(white).filter(ImageFilter.MaxFilter(61))) > 0
    m &= ~near_tag
    # Join a plant's leaves: close small gaps, then one component per plant.
    jim = Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(15))
    lab = Image.fromarray((np.asarray(jim) > 0).astype(np.int32), mode='I')
    comps, k = [], 2
    while True:
        a = np.asarray(lab)
        ys, xs = np.nonzero(a == 1)
        if not len(ys):
            break
        ImageDraw.floodfill(lab, (int(xs[0]), int(ys[0])), k)
        sel = np.asarray(lab) == k
        px = int(m[sel].sum())
        if px >= 150:  # about 6 mm2: smaller is a speck
            yy, xx = np.nonzero(sel)
            comps.append((px, (xx.min(), yy.min(), xx.max() - xx.min() + 1, yy.max() - yy.min() + 1, 0)))
        k += 1
    comps.sort(key=lambda c: c[0])
    if not comps:
        continue
    pick = sorted(set(np.round(np.linspace(0, len(comps) - 1, PER_TRAY)).astype(int)))
    mm2px = rd['area_mm2'] / rd['plant_px'] if rd['plant_px'] else None
    for i, ci in enumerate(pick, 1):
        px, (bx, by, bw, bh, _) = comps[ci]
        cx0, cy0 = x0 + bx - MARGIN, y0 + by - MARGIN
        cx1, cy1 = x0 + bx + bw + MARGIN, y0 + by + bh + MARGIN
        cx0, cy0, cx1, cy1 = max(cx0, 0), max(cy0, 0), min(cx1, W), min(cy1, H)
        name = f'{stem}_t{t}_p{i}.tif'
        Image.fromarray(rgb[cy0:cy1, cx0:cx1]).save(DST + name)
        rows.append(dict(file=name, capture_id=cid, tray=t, plant=i, x0=cx0, y0=cy0,
                         width=cx1 - cx0, height=cy1 - cy0, mm2_per_px=mm2px,
                         mm_per_px=None if mm2px is None else mm2px ** 0.5))
        boxes.append((t, i, cx0, cy0, cx1, cy1))

with open(DST + 'manifest.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

# Index: each tray at 1/4 size with the crop boxes numbered.
font = ImageFont.load_default(size=28)
panels = []
for t in trays:
    o = np.array(json.loads(reads[t]['outline']))
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int) - 60, 0)
    x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 60, [W, H])
    p = Image.fromarray(rgb[y0:y1, x0:x1]).reduce(4)
    d = ImageDraw.Draw(p)
    for (tt, i, a, b_, c, e) in boxes:
        if tt == t:
            d.rectangle([(a - x0) / 4, (b_ - y0) / 4, (c - x0) / 4, (e - y0) / 4], outline='white', width=2)
            d.text(((a - x0) / 4, (b_ - y0) / 4 - 30), f'p{i}', fill='white', font=font,
                   stroke_width=3, stroke_fill='black')
    d.text((10, 10), f'tray {t}', fill='white', font=font, stroke_width=3, stroke_fill='black')
    panels.append(p)
hh = max(p.height for p in panels)
idx = Image.new('RGB', (sum(p.width for p in panels) + 20 * (len(panels) - 1), hh + 50), 'white')
x = 0
for p in panels:
    idx.paste(p, (x, 0))
    x += p.width + 20
ImageDraw.Draw(idx).text((10, hh + 10), f'#352 ImageJ crops, still {stem} UTC, capture {cid}. '
                         'White box: one crop file (t<tray>_p<n>). 1/4 size.', fill='black', font=font)
idx.save(DST + 'index.png')
print(len(rows), 'crops')
for r in rows:
    print(r['file'], r['width'], 'x', r['height'])
