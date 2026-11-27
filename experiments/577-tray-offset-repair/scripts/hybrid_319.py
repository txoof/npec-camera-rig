import json, sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, cv2
from PIL import Image
from npec_rig.calibration import ScaleField
from npec_rig import tray_placement as tp
import hybrid
cal = json.load(open("prod-copy/calibration/20261125T132847632943.json"))["scale_field"]
sf = ScaleField(tuple(cal["coeffs"]), cal["mean_px_per_mm"], cal["residual_std_pct"])
with Image.open(sys.argv[1]) as im:
    W = im.size[0]; im.draft("RGB", (W // 4, im.size[1] // 4)); small = np.asarray(im.convert("RGB"))
F = W / small.shape[1]
t = time.time()
lat = tp.find_outlines(small, sf, F)
rim = tp._blue_rim(small).astype(np.float32)
ppm = sf.px_per_mm(W / 2, small.shape[0] * F / 2) / F
res = hybrid.core(rim, ppm, F, [np.array(o.corners) for o in lat])
print(len(res), "trays", round(time.time() - t, 1), "s")
vis = small.copy()
for corners, how in res:
    c = (np.asarray(corners) / F).astype(np.int32)
    cv2.polylines(vis, [c], True, (255, 0, 255), 4)
    cv2.putText(vis, how, (c[0][0] + 20, c[0][1] + 60), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 0), 4)
    print(how, [round(v) for v in np.asarray(corners).mean(axis=0)])
Image.fromarray(vis).resize((vis.shape[1] // 2, vis.shape[0] // 2)).save(sys.argv[2])
