"""Metrology log 38: inside tray 1's outline, the share of not-blue pixels (the app's rule, blue
above max(red, green) by no more than 0) and their greenness percentiles, tag not removed."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS = None
for line in Path(sys.argv[1]).read_text().splitlines():
    cid, taken, path, outline, soil, *_ = line.split("|")
    pts = [tuple(p) for p in json.loads(outline)]
    x0, y0 = int(min(p[0] for p in pts)), int(min(p[1] for p in pts))
    x1, y1 = int(max(p[0] for p in pts)) + 1, int(max(p[1] for p in pts)) + 1
    a = np.asarray(Image.open(Path(sys.argv[2]) / (Path(path).name + ".jpg")).convert("RGB").crop((x0, y0, x1, y1))).astype(np.int32)
    m = Image.new("L", (x1 - x0, y1 - y0)); ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=1)
    inside = np.asarray(m).astype(bool)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    nb = inside & (b - np.maximum(r, g) <= 0)
    gr = (2 * g - r - b) / (r + g + b + 1e-6)
    blue = inside & ~nb
    print(taken[:16], f"soil level {float(soil):+.3f}", f"not blue {nb.sum() / inside.sum():.3f}",
          "greenness of not-blue p10/50/90", np.round(np.percentile(gr[nb], [10, 50, 90]), 3),
          "blue margin (B - max(R,G)) of blue p10/50", np.percentile((b - np.maximum(r, g))[blue], [10, 50]))
