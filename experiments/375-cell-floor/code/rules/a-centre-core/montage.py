"""Montage of crops: RGB with mask in magenta and opening in red, verdict text. Usage: montage.py OUT.png key... (key = rgb_png path) [--verdicts results.csv]"""
import csv, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
DATA = Path(__file__).resolve().parents[2] / "data"

def tile(row, text, size=380):
    rgb = Image.open(DATA / row["rgb_png"]).convert("RGB")
    mask = np.array(Image.open(DATA / row["mask_png"]).convert("L")) > 127
    a = np.array(rgb)
    a[mask] = (a[mask] * 0.3 + np.array([255, 0, 255]) * 0.7).astype(np.uint8)
    im = Image.fromarray(a)
    poly = json.loads(row["opening_polygon_crop_px"])
    dr = ImageDraw.Draw(im)
    dr.polygon([tuple(p) for p in poly], outline=(255, 0, 0), width=2)
    p = np.array(poly); c = p.mean(0)
    dr.polygon([tuple(q) for q in c + (p - c) * 0.5], outline=(200, 0, 0), width=1)
    x0, y0 = p.min(0) - 20; x1, y1 = p.max(0) + 20
    im = im.crop((int(max(0, x0)), int(max(0, y0)), int(x1), int(y1))).resize((size, size), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    dr.rectangle((0, 0, size, 34), fill=(0, 0, 0))
    dr.text((4, 2), text, fill=(255, 255, 255))
    return im

if __name__ == "__main__":
    out = sys.argv[1]; keys = sys.argv[2:]
    rows = {r["rgb_png"]: r for r in csv.DictReader(open(DATA / "index.csv"))}
    tiles = []
    for k in keys:
        k, _, t = k.partition("::")
        r = rows[k]
        tiles.append(tile(r, t or f"{r['tray_id']} {r['cell']} d{r['day_since_grow_start']}"))
    cols = min(4, len(tiles)); n = len(tiles); rws = (n + cols - 1) // cols
    W = 380 * cols + 4 * (cols - 1)
    M = Image.new("RGB", (W, 380 * rws + 4 * (rws - 1)), (255, 255, 255))
    for i, t in enumerate(tiles):
        M.paste(t, ((i % cols) * 384, (i // cols) * 384))
    M.save(out)
