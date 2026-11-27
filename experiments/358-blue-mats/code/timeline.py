"""#358, metrology log 36: when each tray got its blue mats on 2026-11-06, and when a hand was over it.

Per photo (screen copies, 1600 px wide, from production's gallery, read only) and per tray (its
saved outline, shrunk 8% about its centre to keep the tray wall out): the share of blue pixels
(blue above red and green by more than 20) and of glove green (green above 150 and above red and
blue by more than 40). Bare soil reads a low blue share, a matted tray a high one.
Usage: timeline.py SCREEN_DIR TRAYS_DIR OUT_CSV"""
import csv, glob, json, os, sys
import cv2, numpy as np

screen, trays, out = sys.argv[1:4]
rows = []
for f in sorted(glob.glob(os.path.join(trays, '*.json'))):
    key = os.path.basename(f)[:-5]
    r = json.load(open(f))
    img = cv2.imread(os.path.join(screen, key + '.jpg'))
    if not r or img is None:
        continue
    s = img.shape[1] / 9152
    b, g, red = (img[..., i].astype(int) for i in range(3))
    blue = (b - np.maximum(g, red)) > 20
    glove = (g > 150) & (g - np.maximum(b, red) > 40)
    for t in r['trays']:
        if not t.get('outline_px'):
            continue
        o = np.array(t['outline_px'], float) * s
        o = (o - o.mean(0)) * 0.92 + o.mean(0)
        m = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(m, [np.round(o).astype(np.int32)], 1)
        m = m > 0
        rows.append(dict(key=key, t=key[11:13] + ':' + key[13:15] + ':' + key[15:17], tray=t['tray_id'],
                         location=t['location'], cx=round(t['centre_px'][0]), exclusion=r['exclusion'],
                         blue=round(blue[m].mean(), 3), glove=round(glove[m].mean(), 4)))
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, rows[0].keys()); w.writeheader(); w.writerows(rows)
print(len(rows))
