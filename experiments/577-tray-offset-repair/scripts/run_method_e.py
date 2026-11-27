"""Method E (experiments/round3-tray-outlines/methods_fit.py, tags off) on one copied photo.
usage: run_method_e.py PHOTO.jpg CALIBRATION.json OUT.json"""
import json, sys, time
import cv2, numpy as np
sys.path.insert(0, "/home/pi/npec_camera_rig/experiments/round3-tray-outlines")
from npec_rig.calibration import ScaleField
import methods_fit

photo, cal_path, out = sys.argv[1:4]
cal = json.load(open(cal_path))["scale_field"]
sf = ScaleField(tuple(cal["coeffs"]), cal["mean_px_per_mm"], cal["residual_std_pct"])

class FakeStill:
    def __init__(self):
        self.quarter = cv2.resize(cv2.imread(photo), None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
        h, w = self.quarter.shape[:2]
        self.size = (w * 4, h * 4)
        self.tags, self.tag_placements = [], []
    def px_per_mm(self, x, y):
        return sf.px_per_mm(x, y)

t = time.time()
found = methods_fit.find_notags(FakeStill())
print(len(found), "outlines in", round(time.time() - t, 1), "s")
for f in found:
    xs = [p[0] for p in f["outline"]]; ys = [p[1] for p in f["outline"]]
    print(round(sum(xs)/4), round(sum(ys)/4), f.get("how"), f.get("warnings"))
json.dump(found, open(out, "w"), default=float)
