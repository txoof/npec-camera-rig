"""#358, metrology log 36: pictures of each matted tray before and after, with the app's masks.

For each copied full-size still (read only from production's experiment files), the app's own
`segmentation.grow_trays` with each tray's saved outline and its tag's corners from
`tags.detect_tags`, and the fixed green cutoff (`segmentation.ExGSegmenter`). Check: each tray's
pixel counts beside the ones production saved for that photo. One photo in memory at a time.

Output: one picture per tray, its before still, 09:20 and 10:30 UTC side by side, each plant cell
cropped, grow from leaf cores outlined in magenta and the fixed cutoff in red; the check lines;
colour percentiles, (B - G) / (R + G + B), of leaf (grow mask), soil (before, rest of the cell) and
mat (after, rest of the cell) pixels, the rest kept 7 px clear of the leaf.

Usage: masks.py STILLS_DIR TRAYS_DIR OUT_DIR"""
import glob, json, os, sys
import cv2, numpy as np
from npec_rig.segmentation import ExGSegmenter, grow_trays
from npec_rig.tags import detect_tags

stills, trays_dir, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
BEFORE = {3: '0832', 6: '0840', 4: '0846', 5: '0857'}
AFTER = ['0920', '1030']
fixed_seg = ExGSegmenter()


def inside_box(poly, x0, y0, shape):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(np.array(poly) - [x0, y0]).astype(np.int32)], 1)
    return m > 0


checks, colour = [], {'mat': [], 'soil': [], 'leaf': []}
panels = {tray: {} for tray in BEFORE}
for t in sorted(set(BEFORE.values()) | set(AFTER)):
    path = glob.glob(os.path.join(stills, f'*T{t}*.jpg'))[0]
    key = os.path.basename(path)[:-4]
    rgb = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    reading = json.load(open(os.path.join(trays_dir, key + '.json')))
    tags = {d.tag_id: d for d in detect_tags(rgb)}
    wanted = [tray for tray, tb in BEFORE.items() if t == tb or t in AFTER]
    trays = {x['tray_id']: x for x in reading['trays'] if x['tray_id'] in wanted and x.get('outline_px')}
    order = list(trays)
    grown, _ = grow_trays(rgb, [(np.array(trays[i]['outline_px'], float), [tags[i].corners]) for i in order])
    fixed = fixed_seg.segment(rgb)
    for tray in order:
        tr = trays[tray]
        o = np.array(tr['outline_px'])
        X0, Y0 = np.floor(o.min(0)).astype(int); X1, Y1 = np.ceil(o.max(0)).astype(int) + 1
        ins = inside_box(o, X0, Y0, (Y1 - Y0, X1 - X0))
        checks.append(f'tray {tray} {t}: grown px here {int((grown[Y0:Y1, X0:X1] & ins).sum())}, saved {tr["grown_plant_px"]}; '
                      f'fixed px here {int((fixed[Y0:Y1, X0:X1] & ins).sum())}, saved {tr["plant_px"]}')
        cells = []
        for c in tr['cells']:
            if c['holds'] != 'plant':
                continue
            q = np.array(c['corners_px'])
            x0, y0 = np.floor(q.min(0)).astype(int); x1, y1 = np.ceil(q.max(0)).astype(int) + 1
            cm = inside_box(q, x0, y0, (y1 - y0, x1 - x0))
            sub = rgb[y0:y1, x0:x1]
            crop = cv2.cvtColor(sub, cv2.COLOR_RGB2BGR).copy()
            for m, colr in ((fixed, (0, 0, 255)), (grown, (255, 0, 255))):
                cs, _ = cv2.findContours((m[y0:y1, x0:x1] & cm).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                cv2.drawContours(crop, cs, -1, colr, 2)
            for col, th in (((255, 255, 255), 3), ((255, 0, 255), 2)):
                cv2.putText(crop, f"{c['cell']} {t[:2]}:{t[2:]}", (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, col, th)
            cells.append(cv2.resize(crop, (360, 360)))
            r, g, b = (sub[..., i].astype(np.float32) for i in range(3))
            bg = (b - g) / (r + g + b + 1e-6)
            leaf = grown[y0:y1, x0:x1] & cm
            rest = cm & ~cv2.dilate(leaf.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
            colour['leaf'].append(bg[leaf][::7])
            colour['soil' if t == BEFORE[tray] else 'mat'].append(bg[rest][::50])
        blank = np.zeros((360, 360, 3), np.uint8)
        rows = [np.hstack(cells[i:i + 5] + [blank] * (5 - len(cells[i:i + 5]))) for i in range(0, len(cells), 5)]
        panels[tray][t] = np.vstack(rows)
    del rgb, grown, fixed
for tray, tb in BEFORE.items():
    ps = [panels[tray][x] for x in [tb] + AFTER if x in panels[tray]]
    gap = np.full((ps[0].shape[0], 24, 3), 255, np.uint8)
    sheet = np.hstack(sum([[p_, gap] for p_ in ps], [])[:-1])
    cv2.imwrite(os.path.join(out, f'tray{tray}-cells.jpg'), cv2.resize(sheet, None, fx=0.5, fy=0.5), [cv2.IMWRITE_JPEG_QUALITY, 88])
lines = checks + [f'{k}: n {sum(map(len, v))}, (B-G)/(R+G+B) p1 {np.percentile(np.concatenate(v), 1):+.3f} '
                  f'p50 {np.percentile(np.concatenate(v), 50):+.3f} p99 {np.percentile(np.concatenate(v), 99):+.3f}'
                  for k, v in colour.items()]
open(os.path.join(out, 'masks_summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
