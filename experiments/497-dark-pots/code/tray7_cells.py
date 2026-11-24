"""Where the rule (form B, floor of N levels) removes pixels in tray 7, cell by cell (log 46): removed
pixels of the app's mask per cell, to see whether the removal is spread over leaves or sits in one cell."""
import csv, json, sys
import cv2
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import images, segmentation as sg
from run_photos import trays_of, TAG_SHRINK
R = "/home/txoof/temp.nobackup/rig-copies/ac-testing/497-dark-pots"
D = __file__.rsplit("/code/", 1)[0] + "/data"
rows = []
for name in ("2026-11-18/130053_642253", "2026-11-20/130053_661727", "2026-11-20/200053_650433", "2026-11-22/090053_635081", "2026-11-22/130053_643712",
             "2026-11-22/200053_652827", "2026-11-23/090053_682903", "2026-11-23/130053_611736"):
    api = json.load(open(f"{D}/api/e18_{name.replace('/', '_')}.json"))
    tid, outline, tag, mm2, t = [x for x in trays_of(api) if x[0] == 7][0]
    rgb = images.decode_full(f"{R}/e18/{name}.jpg")
    box = sg._box(np.zeros(rgb.shape[:2], bool), outline); x0, y0, x1, y1 = box
    inside = sg._inside(box, outline)
    c = np.asarray(tag, float) - [x0, y0]; ctr = c.mean(axis=0); tagc = [ctr + TAG_SHRINK * (c - ctr)]
    res = list(rule.grow_sweep(rgb[y0:y1, x0:x1], inside, [None, 3.0, 5.0], tagc, form="B"))
    base = res[0][1]
    for N, mask in ((3, res[1][1]), (5, res[2][1])):
        gone = base & ~mask
        per = []
        for cell in t["cells"]:
            poly = np.zeros(base.shape, np.uint8)
            cv2.fillPoly(poly, [np.round(np.asarray(cell["corners_px"]) - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)], 1)
            per.append((int((gone & (poly > 0)).sum()), int((base & (poly > 0)).sum()), cell["cell"]))
        per.sort(reverse=True)
        tot = int(gone.sum())
        rows.append(dict(photo=name, N=N, tray_app_px=int(base.sum()), removed_px=tot, removed_pct=100 * tot / int(base.sum()),
                         top_cell=per[0][2], top_cell_removed_px=per[0][0], top_cell_app_px=per[0][1], top_cell_share_pct=100 * per[0][0] / max(tot, 1),
                         second_cell=per[1][2], second_removed_px=per[1][0], second_app_px=per[1][1]))
        print(rows[-1], flush=True)
with open(D + "/tray7_cells.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
