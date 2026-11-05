"""#352, metrology log 24: four colour rules against two passes of hand outlines, per plant crop.
Writes compare/per_plant.csv, compare/summary.txt, compare/sheet_*.png (also to the image viewer)."""
import sys, os, glob, json, csv
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(__file__))
from rois import read_zip, read_results, raster

T = '/home/pi/scratch/thr-352/'
OUT = T + 'compare/'
VIEW = '/home/pi/scratch/sam297/352-compare/'
os.makedirs(OUT, exist_ok=True); os.makedirs(VIEW, exist_ok=True)
STEM = '2026-11-03_105853_597207'
PLANTS = [f'{STEM}_t{t}_p{p}.tif' for t in (1, 3, 6) for p in (1, 2, 3, 4, 5)]
PLANTS = [p.replace('_t6_p1.tif', '_t6_p1b.tif') for p in PLANTS]

man = {r['file']: r for r in csv.DictReader(open(T + 'imagej/manifest.csv'))}
modes = {r['tray']: (r['soil_mode'], r['leaf_mode']) for r in map(json.loads, open(T + 'rows.jsonl'))
         if r['stem'] == STEM}


def load_pass(p):
    rs = read_zip(glob.glob(T + f'pass_{p}_*Results.roi.zip')[0])
    res = read_results(glob.glob(T + f'pass_{p}_*Results.csv')[0])
    if p == 1:
        res = res[:15] + [res[16]]  # row 16 is the first, unsaved t6_p1b outline; row 17 matches roi 16
    out = {}
    for (nm, typ, poly), r in zip(rs, res):
        lab = r['Label'].split(':')[0]
        out[lab] = dict(area=int(r['Area']), poly=poly if typ == 0 else None)  # type 1: only its box was saved
    return out


passes = {1: load_pass(1), 2: load_pass(2)}


def rules(rgb, tray):
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    notblue = ~((b > r) & (b > g))
    soil, leaf = modes[tray]
    half = (soil + leaf) / 2
    return {'A': (exg > 0.1) & (g > r), 'B': (exg > 0) & (g > r), 'C': (exg > 0) & notblue,
            'D': (exg > half) & notblue}, half


rows, crops = [], []
for f in PLANTS:
    tray = int(man[f]['tray'])
    rgb = np.asarray(Image.open(T + 'imagej/' + f).convert('RGB'))
    h, w = rgb.shape[:2]
    masks, half = rules(rgb, tray)
    hand = {p: passes[p][f] for p in (1, 2)}
    hm = {p: raster(hand[p]['poly'], w, h) if hand[p]['poly'] is not None else None for p in (1, 2)}
    row = dict(file=f, tray=tray, half_cut=round(half, 3), hand1_px=hand[1]['area'], hand2_px=hand[2]['area'],
               pass2_over_pass1=round(hand[2]['area'] / hand[1]['area'], 4))
    for k, m in masks.items():
        row[f'{k}_px'] = int(m.sum())
        for p in (1, 2):
            row[f'{k}_ratio{p}'] = round(m.sum() / hand[p]['area'], 4)
            if hm[p] is not None:
                row[f'{k}_missed{p}'] = round((hm[p] & ~m).sum() / hm[p].sum(), 4)
                row[f'{k}_extra{p}'] = round((m & ~hm[p]).sum() / hm[p].sum(), 4)
    rows.append(row)
    crops.append((f, rgb, masks, hm))

keys = list(dict.fromkeys(k for r in rows for k in r))
with open(OUT + 'per_plant.csv', 'w', newline='') as fh:
    wr = csv.DictWriter(fh, fieldnames=keys); wr.writeheader(); wr.writerows(rows)


def stats(v):
    v = np.array([x for x in v if x is not None], float)
    return f'mean {v.mean():.3f}  sd {v.std(ddof=1):.3f}  range {v.min():.3f} to {v.max():.3f}  n {len(v)}'


lines = ['Person, pass 2 / pass 1 area: ' + stats([r['pass2_over_pass1'] for r in rows])]
for k in 'ABCD':
    for p in (1, 2):
        lines.append(f'{k} ratio to pass {p}: ' + stats([r[f"{k}_ratio{p}"] for r in rows]))
    for p in (1, 2):
        lines.append(f'{k} missed, pass {p}: ' + stats([r.get(f"{k}_missed{p}") for r in rows]))
        lines.append(f'{k} extra,  pass {p}: ' + stats([r.get(f"{k}_extra{p}") for r in rows]))
open(OUT + 'summary.txt', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))

# Picture sheet: per plant, the crop, then each rule (magenta = rule pixels) with the pass 1 hand outline (white).
S = 2
font = ImageFont.load_default(size=16)
COL = ['crop', 'A in use (0.1, G>R)', 'B (0, G>R)', 'C (0, not blue)', 'D (halfway, not blue)']
for part, sel in (('1', crops[:8]), ('2', crops[8:])):
    cw = max(c[1].shape[1] for c in sel) * S
    ch = max(c[1].shape[0] for c in sel) * S
    sheet = Image.new('RGB', (len(COL) * (cw + 8) + 200, len(sel) * (ch + 8) + 70), 'white')
    d = ImageDraw.Draw(sheet)
    for j, c in enumerate(COL):
        d.text((200 + j * (cw + 8), 4), c, fill='black', font=font)
    for i, (f, rgb, masks, hm) in enumerate(sel):
        y = 30 + i * (ch + 8)
        d.text((4, y + 4), f.replace(STEM + '_', '').replace('.tif', ''), fill='black', font=font)
        for j, k in enumerate([None, 'A', 'B', 'C', 'D']):
            im = rgb.copy()
            if k:
                im[masks[k]] = (0.4 * im[masks[k]] + 0.6 * np.array([255, 0, 255])).astype(np.uint8)
            if hm[1] is not None:
                e = hm[1] & ~(np.roll(hm[1], 1, 0) & np.roll(hm[1], -1, 0) & np.roll(hm[1], 1, 1) & np.roll(hm[1], -1, 1))
                im[e] = 255
            sheet.paste(Image.fromarray(im).resize((im.shape[1] * S, im.shape[0] * S), Image.NEAREST),
                        (200 + j * (cw + 8), y))
    d.text((4, sheet.height - 36), f'#352 development check, still {STEM} UTC. Magenta: pixels the rule counts as plant. '
           'White line: hand outline, pass 1 (missing where only a box was saved). 2x.', fill='black', font=font)
    sheet.save(OUT + f'sheet_{part}.png'); sheet.save(VIEW + f'sheet_{part}.png')
print('sheets written')
