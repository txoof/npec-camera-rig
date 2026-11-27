"""Top edge of the top row and bottom edge of the bottom row, measured on the rim mask, vs lattice and ring outlines (photo 319)."""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, cv2
from PIL import Image
from npec_rig.calibration import ScaleField
from npec_rig import tray_placement as tp
cal = json.load(open("prod-copy/calibration/20261125T132847632943.json"))["scale_field"]
sf = ScaleField(tuple(cal["coeffs"]), cal["mean_px_per_mm"], cal["residual_std_pct"])
with Image.open("prod-copy/photos/132050_172958.jpg") as im:
    W = im.size[0]; im.draft("RGB", (W // 4, im.size[1] // 4)); small = np.asarray(im.convert("RGB"))
F = W / small.shape[1]
rim = tp._blue_rim(small)
lat = tp.find_outlines(small, sf, F)
# ring result (centres from proto): use the printed values
ring = {"top": {3934: 2704, 6950: 2716, 5478: 2720, 2498: 2700, 8386: 2696}, "bot": {3926: 4472, 6950: 4500, 5462: 4492, 2470: 4484, 8410: 4508}}
def top_edge(x0, x1, y_from, y_to):
    cols = rim[int(y_from / F):int(y_to / F), int(x0 / F):int(x1 / F)]
    rows = np.where(cols.mean(axis=1) > 0.5)[0]       # first row where over half the width is blue rim
    return (rows[0] * F + y_from) if len(rows) else None
def bot_edge(x0, x1, y_from, y_to):
    cols = rim[int(y_from / F):int(y_to / F), int(x0 / F):int(x1 / F)]
    rows = np.where(cols.mean(axis=1) > 0.5)[0]
    return (rows[-1] * F + y_from) if len(rows) else None
ppm = 4.94
print("Top edge y (full px): measured on rim mask | lattice | ring ; error in mm (positive = outline below the plastic edge)")
for o in lat:
    cx, cy = o.centre
    xs = [c[0] for c in o.corners]; ys = [c[1] for c in o.corners]
    if cx < 1500: continue
    if cy < 3600:
        m = top_edge(min(xs) + 400, max(xs) - 400, 1500, 2300); mine = min(ys)
        rc = min(ring["top"].items(), key=lambda kv: abs(kv[0] - cx)); rr = rc[1] - 366 * ppm / 2
        print("top  col x=%5d measured %6.0f lattice %6.0f (%+.1f mm) ring %6.0f (%+.1f mm)" % (cx, m, mine, (mine - m) / ppm, rr, (rr - m) / ppm))
    else:
        m = bot_edge(min(xs) + 400, max(xs) - 400, 4800, 5700); mine = max(ys)
        rc = min(ring["bot"].items(), key=lambda kv: abs(kv[0] - cx)); rr = rc[1] + 366 * ppm / 2
        print("bot  col x=%5d measured %6.0f lattice %6.0f (%+.1f mm) ring %6.0f (%+.1f mm)" % (cx, m, mine, (mine - m) / ppm, rr, (rr - m) / ppm))
