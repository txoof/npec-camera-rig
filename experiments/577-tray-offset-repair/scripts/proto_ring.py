"""Prototype (scratch only): tray = tray-sized rectangle whose outer rim loop is covered by the blue rim.
usage: proto_ring.py PHOTO.jpg CALIBRATION.json OUT.png"""
import json, sys, time
import cv2, numpy as np
from PIL import Image
from npec_rig.calibration import ScaleField
from npec_rig import tray_placement as tp

photo, cal_path, out = sys.argv[1:4]
cal = json.load(open(cal_path))["scale_field"]
sf = ScaleField(tuple(cal["coeffs"]), cal["mean_px_per_mm"], cal["residual_std_pct"])
with Image.open(photo) as im:
    W = im.size[0]; im.draft("RGB", (im.size[0] // 4, im.size[1] // 4)); small = np.asarray(im.convert("RGB"))
F = W / small.shape[1]; H, Wq = small.shape[:2]
t0 = time.time()
rim = tp._blue_rim(small).astype(np.float32)
ppm = sf.px_per_mm(W / 2, small.shape[0] * F / 2) / F          # px per mm at quarter size, frame centre
tw, th = int(round(305 * ppm)), int(round(366 * ppm))
band = max(3, int(round(9 * ppm)))
pad = max(tw, th) // 2
padded = cv2.copyMakeBorder(rim, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
ring = np.zeros((th, tw), np.float32); ring[:] = 1; ring[band:-band, band:-band] = 0
score = cv2.matchTemplate(padded, ring, cv2.TM_CCORR) / ring.sum()   # (top-left corner) coverage in 0..1
found = []
sc = score.copy()
for _ in range(20):
    _, mx, _, loc = cv2.minMaxLoc(sc)
    if mx < 0.55: break
    x0, y0 = loc[0] - pad, loc[1] - pad                        # top-left in photo coords
    box = (x0, y0, x0 + tw, y0 + th)
    found.append((mx, box))
    # suppress: any top-left that would overlap this tray by more than 25% of a tray
    sx0, sx1 = max(0, loc[0] - int(0.75 * tw)), min(sc.shape[1], loc[0] + int(0.75 * tw) + 1)
    sy0, sy1 = max(0, loc[1] - int(0.75 * th)), min(sc.shape[0], loc[1] + int(0.75 * th) + 1)
    sc[sy0:sy1, sx0:sx1] = 0
print(len(found), "trays,", round(time.time() - t0, 2), "s")
vis = small.copy()
for k, (s, (a, b, c, d)) in enumerate(found):
    cv2.rectangle(vis, (a, b), (c, d), (255, 0, 255), 4)
    cv2.putText(vis, f"{k}:{s:.2f}", (a + 20, b + 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 0), 4)
    print(k, round(s, 3), "centre full px", round((a + c) / 2 * F), round((b + d) / 2 * F))
Image.fromarray(vis).resize((vis.shape[1] // 2, vis.shape[0] // 2)).save(out)
