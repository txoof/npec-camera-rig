"""Side-by-side samples for metrology log 26 (#355): for each tray, its plant at several JPEG
settings, photo above and plant mask below, red = plant lost against the uncompressed still,
blue = gained. One PNG per tray.

    python samples.py RUN_DIR OUT_DIR TRAY_ID [TRAY_ID ...]

Needs RUN_DIR/frame0.npy, trays.json and frame0_<B|G|E>.jpg (written by analyse.py).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from npec_rig.segmentation import ExGSegmenter  # the app's segmenter (tray_readings.SEGMENTER)

run, out = Path(sys.argv[1]), Path(sys.argv[2])
wanted = [int(t) for t in sys.argv[3:]]
out.mkdir(parents=True, exist_ok=True)
seg = ExGSegmenter()
SETTINGS = [("A", "Uncompressed"), ("B", "Today: 75, half colour"),
            ("G", "85, full colour"), ("E", "95, full colour")]
TILE = 520  # px on screen per crop
font = ImageFont.load_default(size=22)
small = ImageFont.load_default(size=18)



def largest_group(blocks):
    """Rows and columns of the largest 4-connected group of True blocks."""
    seen = np.zeros_like(blocks)
    best = ([], [])
    for start in zip(*np.nonzero(blocks)):
        if seen[start]:
            continue
        stack, ys, xs = [start], [], []
        seen[start] = True
        while stack:
            y, x = stack.pop()
            ys.append(y)
            xs.append(x)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < blocks.shape[0] and 0 <= nx < blocks.shape[1] and blocks[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(ys) > len(best[0]):
            best = (ys, xs)
    return np.array(best[0]), np.array(best[1])


trays = {t["tray_id"]: t for t in json.loads((run / "trays.json").read_text())["trays"]}
raw = np.load(run / "frame0.npy", mmap_mode="r")

# One window per tray: around the plant as the uncompressed still shows it, at most 640 px.
windows, ref_masks = {}, {}
for tid in wanted:
    xs, ys = zip(*trays[tid]["outline"])
    x0, x1 = int(max(min(xs), 0)), int(min(max(xs), raw.shape[1]))
    y0, y1 = int(max(min(ys), 0)), int(min(max(ys), raw.shape[0]))
    m = seg.segment(np.ascontiguousarray(raw[y0:y1, x0:x1, :3]))
    # The solid plant: 16 px blocks at least half plant, so green specks in the soil do not
    # set the window.
    b = 16
    hh, ww = (m.shape[0] // b) * b, (m.shape[1] // b) * b
    blocks = m[:hh, :ww].reshape(hh // b, b, ww // b, b).mean(axis=(1, 3)) >= 0.5
    by, bx = largest_group(blocks)
    ya, yb, xa, xb = by.min() * b, (by.max() + 1) * b, bx.min() * b, (bx.max() + 1) * b
    side = int(min(max(yb - ya, xb - xa) * 1.3 + 60, 640))
    cy, cx = (ya + yb) // 2 + y0, (xa + xb) // 2 + x0
    win = (slice(max(cy - side // 2, 0), cy + side // 2), slice(max(cx - side // 2, 0), cx + side // 2))
    windows[tid] = win
crops = {tid: {} for tid in wanted}
for slug, _label in SETTINGS:
    if slug == "A":
        full = raw
    else:
        with Image.open(run / f"frame0_{slug}.jpg") as im:
            full = np.asarray(im.convert("RGB"))  # as images.decode_full
    for tid, win in windows.items():
        crops[tid][slug] = np.ascontiguousarray(full[win][..., :3])
    del full

for tid in wanted:
    ref = seg.segment(crops[tid]["A"])
    tiles = []
    for slug, label in SETTINGS:
        rgb = crops[tid][slug]
        m = seg.segment(rgb)
        vis = np.zeros(rgb.shape, np.uint8)
        vis[m & ref] = (235, 235, 235)
        vis[ref & ~m] = (230, 60, 60)
        vis[~ref & m] = (60, 120, 255)
        if slug == "A":
            sub = f"plant {int(ref.sum())} px"
        else:
            lost, gained = int((ref & ~m).sum()), int((~ref & m).sum())
            sub = f"lost {lost} px (red), gained {gained} px (blue), net {100 * (m.sum() / ref.sum() - 1):+.1f}%"
        size = (TILE, TILE)
        photo = Image.fromarray(rgb).resize(size, Image.NEAREST)
        mask = Image.fromarray(vis).resize(size, Image.NEAREST)
        tile = Image.new("RGB", (TILE, 2 * TILE + 70), "white")
        d = ImageDraw.Draw(tile)
        d.text((4, 4), label, fill="black", font=font)
        d.text((4, 36), sub, fill="black", font=small)
        tile.paste(photo, (0, 70))
        tile.paste(mask, (0, 70 + TILE))
        tiles.append(tile)
    h = rgb.shape[0]
    head = 50
    sheet = Image.new("RGB", (len(tiles) * TILE + (len(tiles) - 1) * 16, tiles[0].height + head), "white")
    ImageDraw.Draw(sheet).text(
        (4, 10), f"Tray {tid}: still 0, window {h} x {h} px of the photo, shown at {TILE / h:.1f}x. "
        "Top: photo. Bottom: plant mask (green threshold 0.1).", fill="black", font=font)
    for k, t in enumerate(tiles):
        sheet.paste(t, (k * (TILE + 16), head))
    path = out / f"tray{tid:03d}.png"
    sheet.save(path, optimize=True)
    print(path, sheet.size)
