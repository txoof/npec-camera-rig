"""Check-in picture for metrology log 26 (#355): one small plant at three settings and the mask
pixels each JPEG setting loses or gains against the uncompressed still.

    python crops.py RUN_DIR TRAY_ID OUT.png

Run on the rig after analyse.py (it reads the JPEGs analyse.py wrote for still 0).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from npec_rig import images, tray_readings

run, tray_id, out = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
tray = next(t for t in json.loads((run / "trays.json").read_text())["trays"] if t["tray_id"] == tray_id)
xs, ys = zip(*tray["outline"])
x0, x1, y0, y1 = int(max(min(xs), 0)), int(max(xs)), int(max(min(ys), 0)), int(max(ys))
raw = np.load(run / "frame0.npy", mmap_mode="r")
seg = tray_readings.SEGMENTER
box = np.ascontiguousarray(raw[y0:y1, x0:x1, :3])
mask_a = seg.segment(box)
yy, xx = np.nonzero(mask_a)
cy, cx = int(np.median(yy)), int(np.median(xx))
h = 160  # crop half size, px
win = (slice(max(cy - h, 0), cy + h), slice(max(cx - h, 0), cx + h))
panels = [("A uncompressed", box[win], mask_a[win], None)]
for slug, name in (("B", "B today (75, half colour)"), ("E", "E 95 full colour")):
    full = images.decode_full(run / f"frame0_{slug}.jpg")
    crop = np.ascontiguousarray(full[y0:y1, x0:x1])
    del full
    m = seg.segment(crop)
    panels.append((name, crop[win], m[win], mask_a[win]))
scale = 2
tiles = []
for name, rgb, m, ref in panels:
    photo = Image.fromarray(rgb).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.NEAREST)
    vis = np.zeros(rgb.shape, np.uint8)
    vis[m] = (235, 235, 235)
    if ref is not None:
        vis[ref & ~m] = (230, 60, 60)   # plant in A, lost here
        vis[~ref & m] = (60, 120, 255)  # gained here
        lost, gained = int((ref & ~m).sum()), int((~ref & m).sum())
        label = f"{name}: lost {lost} px (red), gained {gained} px (blue)"
    else:
        label = f"{name}: plant {int(m.sum())} px (white)"
    maskimg = Image.fromarray(vis).resize(photo.size, Image.NEAREST)
    tile = Image.new("RGB", (photo.width, photo.height * 2 + 40), "white")
    tile.paste(photo, (0, 40))
    tile.paste(maskimg, (0, 40 + photo.height))
    ImageDraw.Draw(tile).text((6, 12), label, fill="black")
    tiles.append(tile)
W = sum(t.width for t in tiles) + 20 * (len(tiles) - 1)
sheet = Image.new("RGB", (W, tiles[0].height), "white")
x = 0
for t in tiles:
    sheet.paste(t, (x, 0))
    x += t.width + 20
sheet.save(out)
print(out, sheet.size)
