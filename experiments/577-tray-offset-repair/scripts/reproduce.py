"""Run the app's blue finder on a copied production photo and draw what it found.

usage: reproduce.py PHOTO.jpg CALIBRATION.json TAGS.json OUT.png
Reads only. Imports npec_rig from the main checkout (PYTHONPATH=~/npec_camera_rig/src).
"""
import json
import sys

import cv2
import numpy as np
from PIL import Image

from npec_rig.calibration import ScaleField
from npec_rig import tray_placement as tp

photo, cal_path, tags_path, out = sys.argv[1:5]
cal = json.load(open(cal_path))["scale_field"]
sf = ScaleField(tuple(cal["coeffs"]), cal["mean_px_per_mm"], cal["residual_std_pct"])
tags = json.load(open(tags_path))

with Image.open(photo) as im:
    w = im.size[0]
    im.draft("RGB", (im.size[0] // 4, im.size[1] // 4))
    small = np.asarray(im.convert("RGB"))
factor = w / small.shape[1]

outlines = tp.find_outlines(small, sf, factor)
rim = tp._blue_rim(small)

vis = small.copy()
vis[rim > 0] = (0.5 * vis[rim > 0] + 0.5 * np.array([255, 255, 0])).astype(np.uint8)
for i, o in enumerate(outlines):
    pts = (np.array(o.corners) / factor).astype(np.int32)
    cv2.polylines(vis, [pts], True, (255, 0, 255), 4)
    cx, cy = (np.array(o.centre) / factor).astype(int)
    cv2.putText(vis, str(i), (cx - 20, cy), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 255), 5)
for t in tags:
    if t["tag_id"] < 300:
        x, y = (np.array(t["centre"]) / factor).astype(int)
        cv2.circle(vis, (x, y), 14, (255, 0, 0), -1)
        cv2.putText(vis, f"t{t['tag_id']}", (x - 30, y - 24), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 0, 0), 4)
Image.fromarray(vis).resize((vis.shape[1] // 2, vis.shape[0] // 2)).save(out)
print(len(outlines), "outlines")
for i, o in enumerate(outlines):
    print(i, [round(c) for c in o.centre], round(o.tilt_deg, 2), o.edge)
