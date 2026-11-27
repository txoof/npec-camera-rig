import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import cv2, numpy as np
from PIL import Image
from npec_rig.calibration import ScaleField
from npec_rig import tray_placement as tp
cal = json.load(open("prod-copy/calibration/20261125T132847632943.json"))["scale_field"]
sf = ScaleField(tuple(cal["coeffs"]), cal["mean_px_per_mm"], cal["residual_std_pct"])
with Image.open("prod-copy/photos/132050_172958.jpg") as im:
    W = im.size[0]; im.draft("RGB", (W // 4, im.size[1] // 4)); small = np.asarray(im.convert("RGB"))
F = W / small.shape[1]
rim = tp._blue_rim(small).astype(np.float32); H, Wq = rim.shape
ppm = sf.px_per_mm(W / 2, H * F / 2) / F
band = int(round(9 * ppm)); tw, th = int(round(305 * ppm)), int(round(366 * ppm)); pad = max(tw, th)
padded = cv2.copyMakeBorder(rim, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
ring = np.ones((th, tw), np.float32); ring[band:-band, band:-band] = 0
sc = cv2.matchTemplate(padded, ring, cv2.TM_CCORR) / ring.sum()
for i, o in enumerate(tp.find_outlines(small, sf, F)):
    c = np.array(o.corners) / F; x0, y0 = int(round(c[:, 0].min())), int(round(c[:, 1].min()))
    win = sc[y0 + pad - 6: y0 + pad + 7, x0 + pad - 6: x0 + pad + 7]
    print(i, [round(v) for v in o.centre], "ring score %.2f" % win.max())
