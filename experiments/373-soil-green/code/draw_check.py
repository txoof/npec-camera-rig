"""Metrology log 39.2: each flagged plant-tray reading drawn as two panels, the photo and the plant
with the floor cutoff (-0.045) in magenta, for the by-eye check. Read only: photos copied from
production. Run with PYTHONPATH=src.
Usage: draw_check.py LIST PHOTO_DIR OUT_DIR EXCLUDED_IDS(comma separated) [--reference]
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from npec_rig import segmentation as s  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
rows = [l.split("|") for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
photos, out = Path(sys.argv[2]), Path(sys.argv[3])
excluded = dict(x.split(":") for x in sys.argv[4].split(",") if x)
reference = "--reference" in sys.argv
font = ImageFont.load_default(size=34)
summary = []
for n, (cid, taken, path, tray, outline, soil, cutoff, saved_px, _warn) in enumerate(rows, 1):
    pts = [tuple(p) for p in json.loads(outline)]
    x0, y0 = int(min(p[0] for p in pts)), int(min(p[1] for p in pts))
    x1, y1 = int(max(p[0] for p in pts)) + 1, int(max(p[1] for p in pts)) + 1
    photo = Image.open(photos / (Path(path).name + ".jpg")).convert("RGB").crop((x0, y0, x1, y1))
    rgb = np.ascontiguousarray(np.asarray(photo))
    m = Image.new("L", photo.size)
    ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=1)
    inside = np.asarray(m).astype(bool)
    if reference:
        panels_spec = [("A  photo", None), ("B  as saved: cutoff from the soil", float(cutoff))]
    else:
        panels_spec = [("Photo", None), ("New rule (magenta = plant)", s.GROWN_FLOOR)]
    panels, counts = [], []
    for title, cut in panels_spec:
        img = rgb.copy()
        if cut is not None:
            g = s.grow_from_cores(rgb, inside, lower_cutoff=cut)
            img[g.mask] = (255, 0, 255)
            counts.append(int(g.mask.sum()))
        edge = Image.fromarray(img)
        ImageDraw.Draw(edge).polygon([(x - x0, y - y0) for x, y in pts], outline=(255, 0, 0), width=6)
        p = edge.resize((rgb.shape[1] * 6 // 10, rgb.shape[0] * 6 // 10))
        lab = Image.new("RGB", (p.width, 90), "white")
        text = title
        ImageDraw.Draw(lab).multiline_text((10, 8), text, fill="black", font=font)
        page = Image.new("RGB", (p.width, p.height + 90), "white")
        page.paste(p, (0, 0)); page.paste(lab, (0, p.height))
        panels.append(page)
    sheet = Image.new("RGB", (sum(p.width for p in panels) + 20 * (len(panels) - 1), panels[0].height), "white")
    x = 0
    for p in panels:
        sheet.paste(p, (x, 0)); x += p.width + 20
    status = excluded.get(cid, "counted")
    head = f"Tray {tray}, {taken[:16].replace('T', ' ')} UTC, photo {cid}, {status}"
    name = ("ref" if reference else f"{n:02d}") + f"-tray{tray}-{taken[:16].replace(':', '')}.jpg"
    sheet.save(out / name, quality=85)
    summary.append((name, tray, taken[:16], cid, status, int(saved_px), *counts))
    print(name, status, saved_px, counts, flush=True)
Path(out / ("ref.tsv" if reference else "summary.tsv")).write_text(
    "\n".join("\t".join(str(v) for v in r) for r in summary) + "\n")
