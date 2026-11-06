"""#352, metrology log 24.1: rule E (greenness > -0.045, not blue, tag area left out) on six days."""
import sys, os, json, glob, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
sys.path.insert(0, os.path.dirname(__file__))
from rois import read_zip, read_results, raster
Image.MAX_IMAGE_PIXELS = None
T = '/home/pi/scratch/thr-352/'; V = '/home/pi/scratch/sam297/352-fixed-cut/'; os.makedirs(V, exist_ok=True)
OUT = T + 'fixed_cut/'; os.makedirs(OUT, exist_ok=True)
CUT = -0.045
db = json.load(open(T + 'prod/db_readings.json'))
stems = {}
for r in map(json.loads, open(T + 'rows.jsonl')):
    stems[r['stem']] = str(r['capture_id'])


def masks(sub):
    r, g, b = (sub[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6); nb = ~((b > r) & (b > g))
    white = (np.minimum(np.minimum(r, g), b) > 140).astype(np.uint8) * 255
    tag = np.asarray(Image.fromarray(white).filter(ImageFilter.MaxFilter(61))) > 0
    return {'C': (exg > 0) & nb & ~tag, 'E': (exg > CUT) & nb & ~tag}


def specks(m, maxpx=30):
    lab = Image.fromarray(m.astype(np.int32), mode='I'); small, k = 0, 2
    ys, xs = np.nonzero(m); done = np.zeros(m.shape, bool)
    for y, x in zip(ys, xs):
        if done[y, x]:
            continue
        ImageDraw.floodfill(lab, (int(x), int(y)), k); sel = np.asarray(lab) == k; done |= sel
        n = int(sel.sum()); small += n if n < maxpx else 0; k += 1
    return small


# 1. The 3 November crops against both passes.
man = {r['file']: r for r in csv.DictReader(open(T + 'imagej/manifest.csv'))}
def load_pass(p):
    rs = read_zip(glob.glob(T + f'pass_{p}_*Results.roi.zip')[0]); res = read_results(glob.glob(T + f'pass_{p}_*Results.csv')[0])
    if p == 1:
        res = res[:15] + [res[16]]
    return {r['Label'].split(':')[0]: dict(area=int(r['Area']), poly=poly if typ == 0 else None) for (nm, typ, poly), r in zip(rs, res)}
P = {1: load_pass(1), 2: load_pass(2)}
STEM = '2026-11-03_105853_597207'
files = [f'{STEM}_t{t}_p{p}.tif' for t in (1, 3, 6) for p in range(1, 6)]
files = [f.replace('_t6_p1.tif', '_t6_p1b.tif') for f in files]
acc = {k: [] for k in ('ratio1', 'ratio2', 'missed1', 'extra1', 'iou1', 'iou2')}
for f in files:
    rgb = np.asarray(Image.open(T + 'imagej/' + f).convert('RGB')); h, w = rgb.shape[:2]
    m = masks(rgb)['E']
    for p in (1, 2):
        acc[f'ratio{p}'].append(m.sum() / P[p][f]['area'])
        if P[p][f]['poly'] is not None:
            hm = raster(P[p][f]['poly'], w, h)
            acc[f'iou{p}'].append((m & hm).sum() / (m | hm).sum())
            if p == 1:
                acc['missed1'].append((hm & ~m).sum() / hm.sum()); acc['extra1'].append((m & ~hm).sum() / hm.sum())
lines = []
for k, v in acc.items():
    v = np.array(v); lines.append(f'crops, rule E {k}: mean {v.mean():.3f} sd {v.std(ddof=1):.3f} range {v.min():.3f} to {v.max():.3f} n {len(v)}')
print('\n'.join(lines))

# 2 to 5. Whole trays, six days.
rows = []
font = ImageFont.load_default(size=22)
for stem in sorted(stems):
    cid = stems[stem]; cap = db[cid]; reads = {r['tray_id']: r for r in cap['readings'] if r['outline']}
    rgb = np.asarray(Image.open(T + f'prod/{stem}.jpg').convert('RGB')); H, W = rgb.shape[:2]
    for t in range(1, 8):
        rd = reads.get(t)
        if rd is None:
            continue
        mm2 = rd['area_mm2'] / rd['plant_px'] if rd['plant_px'] else 0.0408
        o = np.array(json.loads(rd['outline']))
        x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0); x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
        sub = rgb[y0:y1, x0:x1]
        pim = Image.new('L', (x1 - x0, y1 - y0), 0); ImageDraw.Draw(pim).polygon([(float(a - x0), float(c - y0)) for a, c in o], fill=1)
        ins = np.asarray(pim).astype(bool)
        m = {k: v & ins for k, v in masks(sub).items()}
        row = dict(stem=stem, tray=t, app_mm2=round(rd['area_mm2'], 1), C_mm2=round(m['C'].sum() * mm2, 1), E_mm2=round(m['E'].sum() * mm2, 1))
        row['E_over_C'] = round(row['E_mm2'] / row['C_mm2'], 3) if row['C_mm2'] else None
        row['E_specks'] = round(specks(m['E']) / max(m['E'].sum(), 1), 4)
        row['C_specks'] = round(specks(m['C']) / max(m['C'].sum(), 1), 4)
        rows.append(row); print(row, flush=True)
        if t in (1, 7):
            im = sub.copy(); im[m['E']] = (0.3 * im[m['E']] + 0.7 * np.array([255, 0, 255])).astype(np.uint8)
            p = Image.fromarray(im).reduce(2)
            ImageDraw.Draw(p).text((10, 10), f'{stem[:10]} tray {t}, rule E (-0.045, not blue, tag left out), magenta', fill='white', font=font, stroke_width=3, stroke_fill='black')
            p.save(V + f'{stem[:10]}_tray{t}_ruleE.png')
with open(OUT + 'per_tray_day.csv', 'w', newline='') as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
open(OUT + 'crops_summary.txt', 'w').write('\n'.join(lines) + '\n')
