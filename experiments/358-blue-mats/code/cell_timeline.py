"""#358, metrology log 36: when each cell got its mat. Per photo (gallery screen copies) and plant
cell of trays 3, 4, 5, 6 (cell corners from the photo's saved reading after the Reprocess): the
share of blue pixels (blue above red and green by more than 20) and of glove green. A cell is
matted from the first photo with blue share above 0.5 and no glove in it.
Usage: cell_timeline.py SCREEN_DIR TRAYS_DIR OUT_CSV"""
import csv, glob, json, os, sys
import cv2, numpy as np

screen, trays, out = sys.argv[1:4]
rows = []
for f in sorted(glob.glob(os.path.join(trays, '*.json'))):
    key = os.path.basename(f)[:-5]
    img = cv2.imread(os.path.join(screen, key + '.jpg'))
    r = json.load(open(f))
    if img is None or not r:
        continue
    s = img.shape[1] / 9152
    b, g, red = (img[..., i].astype(int) for i in range(3))
    blue = (b - np.maximum(g, red)) > 20
    glove = (g > 150) & (g - np.maximum(b, red) > 40)
    for t in r['trays']:
        if t['tray_id'] not in (3, 4, 5, 6):
            continue
        for c in t['cells'] or []:
            if c['holds'] != 'plant':
                continue
            q = np.array(c['corners_px'], float) * s
            q = (q - q.mean(0)) * 0.9 + q.mean(0)
            m = np.zeros(img.shape[:2], np.uint8); cv2.fillPoly(m, [np.round(q).astype(np.int32)], 1); m = m > 0
            rows.append(dict(key=key, t=key[11:13] + ':' + key[13:15], tray=t['tray_id'], cell=c['cell'],
                             exclusion=r['exclusion'], blue=round(blue[m].mean(), 3), glove=round(glove[m].mean(), 4)))
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, rows[0].keys()); w.writeheader(); w.writerows(rows)
print(len(rows))
