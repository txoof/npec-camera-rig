"""Metrology log 27.2: how far each tray's placed cells lie from its real openings or pots (#364).

Usage: placement_shift.py STILL.jpg TRAYS.json OUT_PREFIX [blue|rim]
TRAYS.json: a list of trays, each {"tray_id", "outline_px": 4 corners, "cells": [{"cell", "corners_px"}]},
in full-size photo pixels (the app's tray readings, or cells placed offline).

For each tray the whole cell grid is shifted -15 to +15 mm in 1 mm steps; the score is the fraction
of tray-blue pixels on the walls (inside the outline, outside every cell) minus the fraction inside
the cells. Writes OUT_PREFIX.csv (each tray's best shift) and OUT_PREFIX.jpg (each tray's cells as
placed, magenta, with their names). Reads nothing from a rig. The best shift was meant as the
placement error; on 4 x 5 trays it disagrees with the photo (metrology log 27.4) and is not one.
"""

import csv
import json
import math
import sys

import cv2
import numpy as np
from PIL import Image

from npec_rig.tray_placement import BLUE_HUE, BLUE_SAT_MIN, BLUE_VALUE_MIN, RIM_VALUE_REL

FACTOR = 4
STEPS_MM = range(-15, 16)

still, trays_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
mode = sys.argv[4] if len(sys.argv) > 4 else "blue"
with Image.open(still) as im:
    full = im.size
    im.draft("RGB", (full[0] // FACTOR, full[1] // FACTOR))  # JPEG decoded at 1/4: no 64 MP frame
    rgb = np.asarray(im.convert("RGB"))
f = full[0] / rgb.shape[1]
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
blue = (hsv[..., 0] >= BLUE_HUE[0]) & (hsv[..., 0] <= BLUE_HUE[1]) & (hsv[..., 1] >= BLUE_SAT_MIN) & (hsv[..., 2] >= BLUE_VALUE_MIN)
if mode == "rim":
    # Method B (metrology log 27.3): only the lit top rim, the tray finder's rule (tray_placement._blue_rim):
    # blue brighter than RIM_VALUE_REL times the 75th percentile of blue brightness, then a 3 x 3 opening.
    v = hsv[..., 2]
    blue = (blue & (v >= RIM_VALUE_REL * np.percentile(v[blue], 75))).astype(np.uint8)
    blue = cv2.morphologyEx(blue, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)

trays = json.load(open(trays_path))
picture = rgb.copy()
rows = []
for tray in trays:
    if not tray["cells"]:
        continue
    outline = np.asarray(tray["outline_px"]) / f
    side_px = math.dist(tray["cells"][0]["corners_px"][0], tray["cells"][0]["corners_px"][1]) / f
    size_mm = 59.5 if len(tray["cells"]) == 20 else 108.93
    ppm = side_px / size_mm  # quarter-size pixels per mm, from the placed cell's own size
    x0, y0 = np.floor(outline.min(axis=0)).astype(int) - int(16 * ppm)
    x1, y1 = np.ceil(outline.max(axis=0)).astype(int) + int(16 * ppm)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, rgb.shape[1]), min(y1, rgb.shape[0])
    crop = blue[y0:y1, x0:x1]
    inside = np.zeros(crop.shape, np.uint8)
    cv2.fillPoly(inside, [np.round(outline - [x0, y0]).astype(np.int32)], 1)
    inside = inside.astype(bool)
    best = None
    for dx in STEPS_MM:
        for dy in STEPS_MM:
            cells = np.zeros(crop.shape, np.uint8)
            for c in tray["cells"]:
                pts = np.asarray(c["corners_px"]) / f - [x0, y0] + [dx * ppm, -dy * ppm]  # dy north
                cv2.fillPoly(cells, [np.round(pts).astype(np.int32)], 1)
            cells = cells.astype(bool)
            walls = inside & ~cells
            score = crop[walls].mean() - crop[cells].mean()
            if best is None or score > best[0]:
                best = (score, dx, dy)
    at0 = None
    score0 = None
    rows.append({"tray": tray["tray_id"], "cells": len(tray["cells"]), "best_east_mm": best[1], "best_north_mm": best[2],
                 "score_best": round(best[0], 3)})
    for c in tray["cells"]:
        pts = np.asarray(c["corners_px"]) / f
        cv2.polylines(picture, [np.round(pts).astype(np.int32)], True, (255, 0, 255), 2)
        cx, cy = pts.mean(axis=0)
        cv2.putText(picture, c["cell"], (int(cx) - 12, int(cy) + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    tx, ty = outline.min(axis=0)
    cv2.putText(picture, f"tray {tray['tray_id']}", (int(tx) + 10, int(ty) + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
with open(out + ".csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
Image.fromarray(picture).save(out + ".jpg", quality=85)
for r in rows:
    print(r)
