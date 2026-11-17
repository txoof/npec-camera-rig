"""Metrology log 38: tray 1 at 2026-11-12 11:30, plant by grow from leaf cores in magenta, as saved
(cutoff from the top bin, +0.115) and at this branch (the floor), side by side, labels below."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from npec_rig import segmentation as s
Image.MAX_IMAGE_PIXELS = None
line = [l for l in Path(sys.argv[1]).read_text().splitlines() if "T11:30" in l][0]
cid, taken, path, outline, *_ = line.split("|")
pts = [tuple(p) for p in json.loads(outline)]
x0, y0 = int(min(p[0] for p in pts)), int(min(p[1] for p in pts))
x1, y1 = int(max(p[0] for p in pts)) + 1, int(max(p[1] for p in pts)) + 1
rgb = np.ascontiguousarray(np.asarray(Image.open(Path(sys.argv[2]) / (Path(path).name + ".jpg")).convert("RGB").crop((x0, y0, x1, y1))))
m = Image.new("L", (x1 - x0, y1 - y0)); ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=1)
inside = np.asarray(m).astype(bool)
font = ImageFont.load_default(size=40)
panels = []
for title, cutoff in (("As saved: cutoff +0.115, from the leaves", 0.115), ("This branch: soil hidden, floor -0.045", None)):
    g = s.grow_from_cores(rgb, inside, lower_cutoff=cutoff)
    img = rgb.copy(); img[g.mask] = (255, 0, 255)
    p = Image.fromarray(img).resize((rgb.shape[1] // 2, rgb.shape[0] // 2))
    lab = Image.new("RGB", (p.width, 120), "white")
    ImageDraw.Draw(lab).multiline_text((10, 10), f"{title}\nplant px {int(g.mask.sum()):,}", fill="black", font=font)
    page = Image.new("RGB", (p.width, p.height + 120), "white"); page.paste(p, (0, 0)); page.paste(lab, (0, p.height))
    panels.append(page)
out = Image.new("RGB", (sum(p.width for p in panels) + 20, panels[0].height), "white")
out.paste(panels[0], (0, 0)); out.paste(panels[1], (panels[0].width + 20, 0))
out.save(sys.argv[3], quality=88); print(sys.argv[3])
