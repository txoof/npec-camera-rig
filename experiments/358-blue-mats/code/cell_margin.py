"""#358, metrology log 36.1: trays 3 and 6, per cell, grow from leaf cores at blue margin 0 (the app)
and 20, on the before still and 09:20 UTC. Picks the 3 cells of each tray that change most
(tray 3: gain on soil from margin 0 to 20; tray 6: what is still missing at 09:20 margin 20 against
the before still at margin 0) and writes close-ups: margin 0 magenta, margin 20 red.
Usage: cell_margin.py STILLS TRAYS OUT_DIR"""
import glob, json, os, sys
import cv2, numpy as np
import npec_rig.segmentation as seg
from npec_rig.tags import detect_tags

stills, trays_dir, out = sys.argv[1:4]
BEFORE = {3: '0832', 6: '0840'}
px, crops = {}, {}
for t in ['0832', '0840', '0920']:
    path = glob.glob(os.path.join(stills, f'*T{t}*.jpg'))[0]
    rgb = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    reading = json.load(open(os.path.join(trays_dir, os.path.basename(path)[:-4] + '.json')))
    tags = {d.tag_id: d for d in detect_tags(rgb)}
    trays = [x for x in reading['trays'] if x['tray_id'] in BEFORE and (t == BEFORE[x['tray_id']] or t == '0920')]
    masks = {}
    for m in (0, 20):
        seg.GROWN_BLUE_MARGIN = m
        masks[m], _ = seg.grow_trays(rgb, [(np.array(x['outline_px'], float), [tags[x['tray_id']].corners]) for x in trays])
    for x in trays:
        for c in x['cells']:
            if c['holds'] != 'plant':
                continue
            q = np.round(np.array(c['corners_px'])).astype(np.int32)
            x0, y0 = q.min(0); x1, y1 = q.max(0) + 1
            cm = np.zeros((y1 - y0, x1 - x0), np.uint8); cv2.fillPoly(cm, [q - [x0, y0]], 1)
            for m in (0, 20):
                px[(x['tray_id'], c['cell'], t, m)] = int((masks[m][y0:y1, x0:x1] & (cm > 0)).sum())
            big = cv2.resize(cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2BGR), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
            for m, colr in ((20, (0, 0, 255)), (0, (255, 0, 255))):
                mm = cv2.resize((masks[m][y0:y1, x0:x1] & (cm > 0)).astype(np.uint8), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
                cs, _ = cv2.findContours(mm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                cv2.drawContours(big, cs, -1, colr, 2)
            for col, th in (((255, 255, 255), 4), ((255, 0, 255), 2)):
                cv2.putText(big, f"tray {x['tray_id']} {c['cell']} {t[:2]}:{t[2:]}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, col, th)
            crops[(x['tray_id'], c['cell'], t)] = cv2.resize(big, (560, 560))
    del rgb, masks
seg.GROWN_BLUE_MARGIN = 0
lines = []
for tray, tb in BEFORE.items():
    cells = sorted({k[1] for k in px if k[0] == tray})
    rows = []
    for c in cells:
        b0, b20, a0, a20 = px[(tray, c, tb, 0)], px[(tray, c, tb, 20)], px[(tray, c, '0920', 0)], px[(tray, c, '0920', 20)]
        rows.append((c, b0, b20, a0, a20))
        lines.append(f'tray {tray} {c}: soil m0 {b0}, soil m20 {b20} ({(b20 / b0 - 1) * 100:+.0f}%), mat m0 {a0} ({(a0 / b0 - 1) * 100:+.0f}%), mat m20 {a20} ({(a20 / b0 - 1) * 100:+.0f}%)')
    key = (lambda r: r[2] - r[1]) if tray == 3 else (lambda r: r[1] - r[4])
    pick = [r[0] for r in sorted(rows, key=key, reverse=True)[:3]]
    lines.append(f'tray {tray} picked: {pick}')
    sheet = np.vstack([np.hstack([crops[(tray, c, tb)], np.full((560, 16, 3), 255, np.uint8), crops[(tray, c, '0920')]]) for c in pick])
    cv2.imwrite(os.path.join(out, f'cells-tray{tray}-m0-m20.jpg'), cv2.resize(sheet, None, fx=0.7, fy=0.7), [cv2.IMWRITE_JPEG_QUALITY, 90])
open(os.path.join(out, 'cell_margin_summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
