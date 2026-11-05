"""#352 development check: greenness modes, valley cut and areas per tray, on production stills.
Usage: analyse.py <capture_id> <jpg>. Appends rows to rows.jsonl, histograms to hist/<stem>.npz,
pictures to figures/. Pixel counts use the app's own measure_trays (overlap rule included) with a
scale of 1, so app_px must equal the plant_px stored in rig.db; mm2 = px * (stored area / stored px)."""
import sys, json, os
import numpy as np, cv2
from PIL import Image
from npec_rig.segmentation import ExGSegmenter, measure_trays

Image.MAX_IMAGE_PIXELS = None
OUT = '/home/pi/scratch/thr-352/'
PLANT_TRAYS = range(1, 8)  # soil trays; 8 to 12 hold reference targets (green squares, cut leaves)
cid, jpg = sys.argv[1], sys.argv[2]
stem = os.path.basename(jpg)[:-4]
cap = json.load(open(OUT + 'prod/db_readings.json'))[cid]


class One:
    def mm_per_px(self, x, y):
        return 1.0


def smooth(h, s=2.0):
    k = np.exp(-0.5 * (np.arange(-6, 7) / s) ** 2)
    return np.convolve(h, k / k.sum(), mode='same')


def modes(h, ctr):
    sm = smooth(np.log10(h + 1.0))
    s = int(np.argmax(sm))
    loc = [j for j in range(s + 8, len(sm) - 1) if sm[j] >= sm[j - 1] and sm[j] >= sm[j + 1] and ctr[j] < 0.3]
    l = max(loc, key=lambda j: sm[j]) if loc else None
    v = (s + int(np.argmin(sm[s:l + 1]))) if l is not None else None
    ok = l is not None and v < l and sm[l] - sm[v] > 0.05
    return (float(ctr[s]), float(ctr[l]) if ok else None, float(ctr[v]) if ok else None,
            float(sm[l] - sm[v]) if ok else None)


reads = [r for r in cap['readings'] if r['outline']]
trays = [(json.loads(r['outline']), (r['centre_x_px'], r['centre_y_px'])) for r in reads]
rgb = np.asarray(Image.open(jpg).convert('RGB'))
H, W = rgb.shape[:2]
app = ExGSegmenter().segment(rgb)
exg = np.empty((H, W), np.float16)
gr = np.empty((H, W), bool)
clean = np.empty((H, W), bool)  # not blue plastic, not white or grey (tags, labels)
for t in range(0, H, 512):
    r, g, b = (rgb[t:t + 512, :, i].astype(np.float32) for i in range(3))
    exg[t:t + 512] = (2 * g - r - b) / (r + g + b + 1e-6)
    gr[t:t + 512] = g > r
    clean[t:t + 512] = ~((b > r) & (b > g)) & (np.minimum(np.minimum(r, g), b) <= 140)
app_px = [m.plant_px for m in measure_trays(app, trays, One())]

bins = np.arange(-0.5, 0.5001, 0.01)
ctr = (bins[:-1] + bins[1:]) / 2
hists, rows, boxes = {}, [], {}
for i, rd in enumerate(reads):
    o = np.array(trays[i][0])
    x0, y0 = np.maximum(np.floor(o.min(0)).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(o.max(0)).astype(int) + 1, [W, H])
    ins = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(ins, [np.round(o - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
    ins = ins.astype(bool)
    boxes[i] = (x0, y0, x1, y1, ins)
    h, _ = np.histogram(exg[y0:y1, x0:x1][ins & clean[y0:y1, x0:x1]].astype(np.float32), bins=bins)
    hists[str(rd['tray_id'])] = h
    soil, leaf, valley, depth = modes(h, ctr)
    rows.append(dict(stem=stem, capture_id=int(cid), tray=rd['tray_id'], soil_mode=round(soil, 3),
                     leaf_mode=None if leaf is None else round(leaf, 3),
                     valley=None if valley is None else round(valley, 3),
                     depth_log10=None if depth is None else round(depth, 3),
                     app_px=app_px[i], db_px=rd['plant_px'], db_mm2=rd['area_mm2'],
                     mm2_per_px=(rd['area_mm2'] / rd['plant_px']) if rd['plant_px'] else None,
                     warnings=rd['warnings'], segmenter=rd['segmenter']))

# One cut per photo: the valley of the soil trays' pooled histogram.
pooled = sum(hists[str(r['tray'])] for r in rows if r['tray'] in PLANT_TRAYS)
p_soil, p_leaf, p_valley, p_depth = modes(pooled, ctr)
print('pooled', stem, p_soil, p_leaf, p_valley, p_depth)


def count(mask, i):
    return measure_trays(mask, trays, One())[i].plant_px


masks_for_fig = {}
for i, row in enumerate(rows):
    if row['tray'] not in PLANT_TRAYS:
        continue
    row.update(photo_soil=p_soil, photo_leaf=p_leaf, photo_valley=p_valley)
    cuts = {'c010': 0.1, 'cm005': -0.05, 'cut0': 0.0, 'photo': p_valley}
    if row['valley'] is not None:
        cuts['valley'] = row['valley']
    for k, c in cuts.items():
        if c is None:
            continue
        above = exg > np.float16(c)
        row[k + '_raw_px'] = count(above & gr, i)                # the app's rule at this cut
        row[k + '_px'] = count(above & gr & clean, i)            # plus: not blue, not white
        row[k + '_nogr_px'] = count(above & clean, i)            # without G > R
        if k == ('valley' if 'valley' in cuts else 'photo' if p_valley is not None else 'cut0'):
            x0, y0, x1, y1, ins = boxes[i]
            m = (above & gr & clean)[y0:y1, x0:x1] & ins
            m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            n, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
            row['blobs_ge_100px'] = int(sum(st[j, cv2.CC_STAT_AREA] >= 100 for j in range(1, n)))
            masks_for_fig[i] = (k, c)
        del above
    print({k: row[k] for k in row if k in ('tray', 'soil_mode', 'leaf_mode', 'valley', 'app_px', 'c010_px',
                                            'valley_px', 'photo_px', 'cm005_raw_px', 'cm005_px', 'blobs_ge_100px')}, flush=True)

os.makedirs(OUT + 'hist', exist_ok=True)
np.savez(OUT + 'hist/' + stem + '.npz', bins=bins, pooled=pooled, **hists)
with open(OUT + 'rows.jsonl', 'a') as f:
    for r in rows:
        f.write(json.dumps(r) + '\n')

# --- pictures: app cut 0.1 in yellow, valley cut in cyan ---------------------------------------
YEL, CYA, WHT = (255, 230, 0), (0, 255, 255), (255, 255, 255)
F = 4
ov = np.asarray(Image.fromarray(rgb).resize((W // F, H // F), Image.BILINEAR)).copy()
closeups = []
for i, (k, c) in masks_for_fig.items():
    x0, y0, x1, y1, ins = boxes[i]
    vm = ((exg[y0:y1, x0:x1] > np.float16(c)) & gr[y0:y1, x0:x1] & clean[y0:y1, x0:x1] & ins).astype(np.uint8)
    am = (app[y0:y1, x0:x1] & ins).astype(np.uint8)
    o = np.array(trays[i][0])
    cv2.polylines(ov, [np.round(o / F).astype(np.int32).reshape(-1, 1, 2)], True, WHT, 2)
    for mm, col in ((vm, CYA), (am, YEL)):
        small = cv2.resize(mm, ((x1 - x0) // F, (y1 - y0) // F), interpolation=cv2.INTER_AREA) > 0
        cs, _ = cv2.findContours(small.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(ov[y0 // F:y0 // F + small.shape[0], x0 // F:x0 // F + small.shape[1]], cs, -1, col, 1)
    cx, cy = np.round(o.mean(0) / F).astype(int)
    cv2.putText(ov, f"tray {rows[i]['tray']}", (cx - 60, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.0, WHT, 3)
    # close-up: the largest valley blob of this tray, 500 px square at full size
    if rows[i]['tray'] in (1, 4, 6):
        n, lab, st, cen = cv2.connectedComponentsWithStats(vm, connectivity=8)
        if n > 1:
            j = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            bx, by = int(cen[j][0]), int(cen[j][1])
            a0, b0 = max(bx - 250, 0), max(by - 250, 0)
            crop = rgb[y0 + b0:y0 + b0 + 500, x0 + a0:x0 + a0 + 500].copy()
            for mm, col in ((vm, CYA), (am, YEL)):
                cs, _ = cv2.findContours(np.ascontiguousarray(mm[b0:b0 + 500, a0:a0 + 500]), cv2.RETR_EXTERNAL,
                                         cv2.CHAIN_APPROX_NONE)
                cv2.drawContours(crop, cs, -1, col, 1)
            crop = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
            closeups.append((rows[i]['tray'], k, c, crop))


def legend(img, lines):
    band = np.full((34 * len(lines) + 16, img.shape[1], 3), 255, np.uint8)
    for n, (col, text) in enumerate(lines):
        y = 30 + 34 * n
        cv2.rectangle(band, (12, y - 18), (52, y + 2), (60, 60, 60), -1)
        cv2.line(band, (16, y - 8), (48, y - 8), col, 4)
        cv2.putText(band, text, (64, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    return np.vstack([img, band])


lines = [(YEL, 'yellow outline: app cut, greenness > 0.1 and G > R (what rig.db holds)'),
         (CYA, 'cyan outline: valley cut per tray (else photo valley, else 0), G > R, not blue, not white'),
         (WHT, f'white box: tray outline stored in rig.db. Still {stem} UTC, 1/4 size. Development check #352')]
Image.fromarray(legend(ov, lines)).save(OUT + f'figures/{stem}_overview.png')
for tray, k, c, crop in closeups:
    Image.fromarray(legend(crop, [(YEL, 'yellow: app cut 0.1'), (CYA, f'cyan: {k} cut {c:+.3f}'),
                                  ((0, 0, 0), f'tray {tray}, {stem}, full size x2')])).save(
        OUT + f'figures/{stem}_tray{tray}_closeup.png')
