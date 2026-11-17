"""#358: close-ups of chosen cells before and after their mat, the app's masks drawn as in masks.py
(grow from leaf cores magenta, fixed cutoff red), 3 times enlarged. Usage: zoom.py STILLS TRAYS OUT TRAY CELL[,CELL] TIME[,TIME]"""
import glob, json, os, sys
import cv2, numpy as np
from npec_rig.segmentation import ExGSegmenter, grow_trays
from npec_rig.tags import detect_tags

stills, trays_dir, out, tray, cells, times = sys.argv[1:7]
tray = int(tray); cells = cells.split(','); rows = []
for t in times.split(','):
    path = glob.glob(os.path.join(stills, f'*T{t}*.jpg'))[0]
    rgb = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    tr = [x for x in json.load(open(os.path.join(trays_dir, os.path.basename(path)[:-4] + '.json')))['trays'] if x['tray_id'] == tray][0]
    tag = [d for d in detect_tags(rgb) if d.tag_id == tray][0]
    grown, _ = grow_trays(rgb, [(np.array(tr['outline_px'], float), [tag.corners])])
    fixed = ExGSegmenter().segment(rgb)
    row = []
    for c in [c for c in tr['cells'] if c['cell'] in cells]:
        cx, cy = np.array(c['corners_px']).mean(0).astype(int); h = 110
        sub = cv2.cvtColor(rgb[cy - h:cy + h, cx - h:cx + h], cv2.COLOR_RGB2BGR)
        big = cv2.resize(sub, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
        for m, colr in ((fixed, (0, 0, 255)), (grown, (255, 0, 255))):
            mm = cv2.resize(m[cy - h:cy + h, cx - h:cx + h].astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
            cs, _ = cv2.findContours(mm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(big, cs, -1, colr, 2)
        for col, th in (((255, 255, 255), 4), ((255, 0, 255), 2)):
            cv2.putText(big, f"tray {tray} {c['cell']} {t[:2]}:{t[2:]} UTC", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, col, th)
        row.append(big)
    rows.append(np.hstack(row)); del rgb, grown, fixed
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
