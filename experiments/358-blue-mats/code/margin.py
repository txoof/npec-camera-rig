"""#358, metrology log 36.1: grow from leaf cores with the blue rule loosened. The app's
`segmentation.grow_trays` with only `GROWN_BLUE_MARGIN` changed (0 is the app; None drops the blue
rule, as a margin no pixel exceeds). Per tray and still: plant pixels; and close-ups of chosen
cells for each margin. Usage: margin.py STILLS TRAYS OUT_DIR"""
import glob, json, os, sys
import cv2, numpy as np
import npec_rig.segmentation as seg
from npec_rig.tags import detect_tags

stills, trays_dir, out = sys.argv[1:4]
BEFORE = {3: '0832', 6: '0840', 4: '0846', 5: '0857'}
AFTER = ['0920', '1030']
MARGINS = {'blue margin 0 (app)': 0, 'blue margin 5': 5, 'blue margin 10': 10, 'blue margin 20': 20, 'no blue rule': 255}
ZOOM = (5, ['B1', 'B5'])
px, zooms = {}, {}
for t in sorted(set(BEFORE.values()) | set(AFTER)):
    path = glob.glob(os.path.join(stills, f'*T{t}*.jpg'))[0]
    rgb = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    reading = json.load(open(os.path.join(trays_dir, os.path.basename(path)[:-4] + '.json')))
    tags = {d.tag_id: d for d in detect_tags(rgb)}
    trays = [x for x in reading['trays'] if x['tray_id'] in BEFORE and x.get('outline_px')
             and (t == BEFORE[x['tray_id']] or t in AFTER)]
    for name, m in MARGINS.items():
        seg.GROWN_BLUE_MARGIN = m
        mask, _ = seg.grow_trays(rgb, [(np.array(x['outline_px'], float), [tags[x['tray_id']].corners]) for x in trays])
        for x in trays:
            o = np.round(np.array(x['outline_px'])).astype(np.int32)
            X0, Y0 = o.min(0); X1, Y1 = o.max(0) + 1
            ins = np.zeros((Y1 - Y0, X1 - X0), np.uint8); cv2.fillPoly(ins, [o - [X0, Y0]], 1)
            px[(x['tray_id'], t, name)] = int((mask[Y0:Y1, X0:X1] & (ins > 0)).sum())
            if x['tray_id'] == ZOOM[0] and t in (BEFORE[ZOOM[0]], '0920'):
                for c in [c for c in x['cells'] if c['cell'] in ZOOM[1]]:
                    cx, cy = np.array(c['corners_px']).mean(0).astype(int); h = 110
                    big = cv2.resize(cv2.cvtColor(rgb[cy - h:cy + h, cx - h:cx + h], cv2.COLOR_RGB2BGR), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
                    cs, _ = cv2.findContours(cv2.resize(mask[cy - h:cy + h, cx - h:cx + h].astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                    cv2.drawContours(big, cs, -1, (255, 0, 255), 2)
                    for col, th in (((255, 255, 255), 4), ((255, 0, 255), 2)):
                        cv2.putText(big, f"{c['cell']} {t[:2]}:{t[2:]} {name}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, th)
                    zooms[(c['cell'], t, name)] = big
    del rgb
seg.GROWN_BLUE_MARGIN = 0
lines = []
for tray, tb in BEFORE.items():
    base = px[(tray, tb, 'blue margin 0 (app)')]
    for name in MARGINS:
        parts = [f'before {px[(tray, tb, name)]} ({(px[(tray, tb, name)] / base - 1) * 100:+.1f}%)']
        parts += [f'{t} {px[(tray, t, name)]} ({(px[(tray, t, name)] / base - 1) * 100:+.1f}%)' for t in AFTER if (tray, t, name) in px]
        lines.append(f'tray {tray}, {name}: ' + ', '.join(parts))
open(os.path.join(out, 'margin_summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
for cell in ZOOM[1]:
    rows = [np.hstack([zooms[(cell, t, n)] for n in MARGINS]) for t in (BEFORE[ZOOM[0]], '0920')]
    cv2.imwrite(os.path.join(out, f'margin-tray{ZOOM[0]}-{cell}.jpg'), cv2.resize(np.vstack(rows), None, fx=0.6, fy=0.6), [cv2.IMWRITE_JPEG_QUALITY, 90])
