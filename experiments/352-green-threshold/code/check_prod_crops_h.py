"""#352, 24.7 checks 1 and 3: rule G on production (24.3 windows, every 4th photo, trays 1 to 7) and on
Aaron's 15 outlined plants (cutoff from the plant's tray on the 3 Nov 10:58 still)."""
import json, csv, sys, os, glob
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(__file__))
from ruleg import rules, grow
from rois import read_zip, read_results, raster
T = '/home/pi/scratch/thr-352/'


def tray_box(img, outline, pad=0):
    H, W = img.shape[:2]; o = np.array(json.loads(outline) if isinstance(outline, str) else outline)
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int) - pad, 0); x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1 + pad, [W, H])
    ins = np.zeros((y1 - y0, x1 - x0), np.uint8); cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    return np.ascontiguousarray(img[y0:y1, x0:x1]), ins > 0


# Check 3.
cap = json.load(open(T + 'prod/db_readings.json'))['19380']
STEM = '2026-11-03_105853_597207'
img = cv2.cvtColor(cv2.imread(T + f'prod/{STEM}.jpg'), cv2.COLOR_BGR2RGB)
cuts, cuts_h = {}, {}
for rd in cap['readings']:
    if rd['tray_id'] in (1, 3, 6):
        sub, ins = tray_box(img, rd['outline']); m = rules(sub, ins, rd['tray_id']); cuts[rd['tray_id']] = m['cut']; cuts_h[rd['tray_id']] = m['cut_h']
print('\ncheck 3: cutoffs G, H on 3 Nov 10:58, trays 1 3 6:', cuts, cuts_h)
def load_pass(p):
    rs = read_zip(glob.glob(T + f'pass_{p}_*Results.roi.zip')[0]); res = read_results(glob.glob(T + f'pass_{p}_*Results.csv')[0])
    if p == 1: res = res[:15] + [res[16]]
    return {r['Label'].split(':')[0]: dict(area=int(r['Area']), poly=poly if typ == 0 else None) for (nm, typ, poly), r in zip(rs, res)}
P = {1: load_pass(1), 2: load_pass(2)}
files = [f'{STEM}_t{t}_p{p}.tif'.replace('_t6_p1.tif', '_t6_p1b.tif') for t in (1, 3, 6) for p in range(1, 6)]
acc = {k: [] for k in ('H_ratio1', 'H_iou1', 'H_iou2', 'G_ratio1', 'G_iou1', 'F_ratio1', 'F_iou1')}
for f in files:
    rgb = cv2.cvtColor(cv2.imread(T + 'imagej/' + f, cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB); h, w = rgb.shape[:2]
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3)); exg = (2 * g - r - b) / (r + g + b + 1e-6); nb = ~((b > r) & (b > g))
    sel = np.ones((h, w), bool); tray = int(f.split('_t')[1][0])
    for k, cut in (('H', cuts_h[tray]), ('G', cuts[tray]), ('F', -0.045)):
        m = grow(exg, g, r, nb, sel, cut)
        acc[f'{k}_ratio1'].append(m.sum() / P[1][f]['area'])
        for p in ((1, 2) if k == 'H' else (1,)):
            if P[p][f]['poly'] is not None:
                hm = raster(P[p][f]['poly'], w, h); acc[f'{k}_iou{p}'].append((m & hm).sum() / (m | hm).sum())
for k, v in acc.items():
    v = np.array(v); print(f'  {k}: {v.mean():.3f} ({v.min():.3f} to {v.max():.3f}, n {len(v)})')

# Check 1.
db = json.load(open(T + 'ts/db_windows.json'))
caps = sorted([v for v in db.values() if not (v['exclusion'] or {}).get('name')], key=lambda v: v['cap']['taken_at'])[::4]
rows = []
for v in caps:
    img = cv2.cvtColor(cv2.imread(T + 'ts/stills/' + v['cap']['path'].split('/stills/')[1] + '.jpg'), cv2.COLOR_BGR2RGB)
    for rd in v['readings']:
        if rd['tray_id'] is None or not (1 <= rd['tray_id'] <= 7) or rd['placement'] != 'placed':
            continue
        sub, ins = tray_box(img, rd['outline'])
        m = rules(sub, ins, rd['tray_id'])
        mm2 = rd['area_mm2'] / rd['plant_px'] if rd['plant_px'] else 0.0408
        rows.append(dict(day=v['cap']['taken_at'][:10], t=v['cap']['taken_at'][11:16], tray=rd['tray_id'], soil_peak=m['soil_peak'], cut=m['cut'],
                         warn=m['warn'], tag_found=any(d.tag_id == rd['tray_id'] for d in m['dets']),
                         current_mm2=round(m['current'].sum() * mm2, 1), F_mm2=round(m['F'].sum() * mm2, 1), G_mm2=round(m['G'].sum() * mm2, 1), H_mm2=round(m['H'].sum() * mm2, 1), cut_h=m['cut_h'], warn_h=m['warn_h']))
with open(T + 'ruleh_prod.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f'check 1: {len(caps)} photos, {len(rows)} tray readings')
for d in sorted({r['day'] for r in rows}):
    for t in range(1, 8):
        rr = [r for r in rows if r['day'] == d and r['tray'] == t]
        if not rr: continue
        g, f = np.array([r['H_mm2'] for r in rr]), np.array([r['F_mm2'] for r in rr])
        print(f"  {d} tray {t}: soil peak {min(r['soil_peak'] for r in rr):+.3f} to {max(r['soil_peak'] for r in rr):+.3f}; H cutoff {min(r['cut_h'] for r in rr):+.3f} to {max(r['cut_h'] for r in rr):+.3f}; "
              f"H warn {sum(r['warn_h'] for r in rr)}/{len(rr)}; tag {sum(r['tag_found'] for r in rr)}/{len(rr)}; H/F {np.mean(g / np.maximum(f, 1)):.3f} ({np.min(g / np.maximum(f, 1)):.3f} to {np.max(g / np.maximum(f, 1)):.3f})")

