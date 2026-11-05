"""#352, metrology log 24.2: rule F (rule E pieces holding at least one rule A pixel) on the crops
and on six days of trays 1 to 7."""
import sys, os, json, glob, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(__file__))
from rois import read_zip, read_results, raster
Image.MAX_IMAGE_PIXELS = None
T = '/home/pi/scratch/thr-352/'; V = '/home/pi/scratch/sam297/352-core-grow/'; os.makedirs(V, exist_ok=True)
OUT = T + 'core_grow/'; os.makedirs(OUT, exist_ok=True)
EIGHT = np.ones((3, 3), bool)
db = json.load(open(T + 'prod/db_readings.json'))
stems = {r['stem']: str(r['capture_id']) for r in map(json.loads, open(T + 'rows.jsonl'))}


def masks(sub):
    r, g, b = (sub[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6); nb = ~((b > r) & (b > g))
    tag = ndi.maximum_filter(np.minimum(np.minimum(r, g), b) > 140, size=61)
    A = (exg > 0.1) & (g > r) & ~tag
    C = (exg > 0) & nb & ~tag
    E = (exg > -0.045) & nb & ~tag
    lab, n = ndi.label(E, structure=EIGHT)
    keep = np.zeros(n + 1, bool); keep[np.unique(lab[A])] = True; keep[0] = False
    F = keep[lab]
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    dropped_big = int(((~keep) & (sizes >= 150))[1:].sum())
    return dict(A=A, C=C, E=E, F=F), lab, sizes, dropped_big


def specks(m):
    lab, n = ndi.label(m, structure=EIGHT)
    s = np.bincount(lab.ravel())[1:]
    return s[s < 30].sum() / max(m.sum(), 1)


# 1. The 3 November crops against both passes.
def load_pass(p):
    rs = read_zip(glob.glob(T + f'pass_{p}_*Results.roi.zip')[0]); res = read_results(glob.glob(T + f'pass_{p}_*Results.csv')[0])
    if p == 1:
        res = res[:15] + [res[16]]
    return {r['Label'].split(':')[0]: dict(area=int(r['Area']), poly=poly if typ == 0 else None) for (nm, typ, poly), r in zip(rs, res)}
P = {1: load_pass(1), 2: load_pass(2)}
STEM = '2026-11-03_105853_597207'
files = [f'{STEM}_t{t}_p{p}.tif'.replace('_t6_p1.tif', '_t6_p1b.tif') for t in (1, 3, 6) for p in range(1, 6)]
lines, per = [], []
for rule in ('E', 'F'):
    acc = {k: [] for k in ('ratio1', 'ratio2', 'missed1', 'extra1', 'iou1', 'iou2')}
    for f in files:
        rgb = np.asarray(Image.open(T + 'imagej/' + f).convert('RGB')); h, w = rgb.shape[:2]
        m = masks(rgb)[0][rule]
        row = dict(rule=rule, plant=f[25:-4])
        for p in (1, 2):
            acc[f'ratio{p}'].append(m.sum() / P[p][f]['area']); row[f'ratio{p}'] = round(m.sum() / P[p][f]['area'], 3)
            if P[p][f]['poly'] is not None:
                hm = raster(P[p][f]['poly'], w, h)
                acc[f'iou{p}'].append((m & hm).sum() / (m | hm).sum()); row[f'iou{p}'] = round(acc[f'iou{p}'][-1], 3)
                if p == 1:
                    acc['missed1'].append((hm & ~m).sum() / hm.sum()); acc['extra1'].append((m & ~hm).sum() / hm.sum())
                    row['missed1'] = round(acc['missed1'][-1], 3); row['extra1'] = round(acc['extra1'][-1], 3)
        per.append(row)
    for k, v in acc.items():
        v = np.array(v); lines.append(f'crops, rule {rule} {k}: mean {v.mean():.3f} sd {v.std(ddof=1):.3f} range {v.min():.3f} to {v.max():.3f} n {len(v)}')
print('\n'.join(lines), flush=True)
with open(OUT + 'crops_per_plant.csv', 'w', newline='') as fh:
    keys = list(dict.fromkeys(k for r in per for k in r)); wr = csv.DictWriter(fh, fieldnames=keys); wr.writeheader(); wr.writerows(per)
open(OUT + 'crops_summary.txt', 'w').write('\n'.join(lines) + '\n')

# 2 to 5. Whole trays, six days.
rows = []; font = ImageFont.load_default(size=22)
for stem in sorted(stems):
    cap = db[stems[stem]]; reads = {r['tray_id']: r for r in cap['readings'] if r['outline']}
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
        m, lab, sizes, _ = masks(np.where(ins[..., None], sub, 0).astype(np.uint8))
        m = {k: v & ins for k, v in m.items()}
        dropped = m['E'] & ~m['F']
        dl, dn = ndi.label(dropped, structure=EIGHT); ds = np.bincount(dl.ravel())[1:]
        row = dict(stem=stem, tray=t, app_mm2=round(rd['area_mm2'], 1), C_mm2=round(m['C'].sum() * mm2, 1),
                   E_mm2=round(m['E'].sum() * mm2, 1), F_mm2=round(m['F'].sum() * mm2, 1))
        row['F_over_C'] = round(row['F_mm2'] / row['C_mm2'], 3) if row['C_mm2'] else None
        row['E_over_C'] = round(row['E_mm2'] / row['C_mm2'], 3) if row['C_mm2'] else None
        row['F_specks'] = round(specks(m['F']), 4)
        row['dropped_mm2'] = round(dropped.sum() * mm2, 1)
        row['dropped_ge150px'] = int((ds >= 150).sum()); row['dropped_largest_px'] = int(ds.max()) if len(ds) else 0
        rows.append(row); print(row, flush=True)
        if t in (1, 3, 7):
            im = sub.copy()
            im[m['F']] = (0.3 * im[m['F']] + 0.7 * np.array([255, 0, 255])).astype(np.uint8)
            dd = ndi.binary_dilation(dropped, iterations=2)
            im[dd] = (0.2 * im[dd] + 0.8 * np.array([0, 255, 255])).astype(np.uint8)
            p = Image.fromarray(im).reduce(2)
            ImageDraw.Draw(p).text((10, 10), f'{stem[:10]} tray {t}: magenta rule F (kept), cyan rule E pieces left out (drawn 2 px wider)',
                                   fill='white', font=font, stroke_width=3, stroke_fill='black')
            p.save(V + f'{stem[:10]}_tray{t}_ruleF.png')
with open(OUT + 'per_tray_day.csv', 'w', newline='') as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
