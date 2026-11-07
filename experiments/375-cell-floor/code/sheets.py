"""Contact sheets for humans: rows = cells, columns = days (the daily photo, plus late photos), RGB crop
with the ExG mask outline in magenta and the pot opening in red. One sheet per rig, tray (and experiment)."""
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path.home() / "scratch/375-cell-floor"; DATA = ROOT / "data"
rows = [json.loads(l) for f in ("index_dev.jsonl", "index_prod.jsonl") if (ROOT / "work" / f).exists() for l in open(ROOT / "work" / f)]
MAGENTA, RED = (255, 0, 255), (255, 0, 0)
font = ImageFont.load_default(size=14)

def tile(r, size):
    rgb = Image.open(DATA / r["rgb_png"]).convert("RGB")
    m = np.asarray(Image.open(DATA / r["mask_png"]).convert("1"), dtype=bool)
    s = size / max(rgb.size)
    w, h = round(rgb.width * s), round(rgb.height * s)
    im = rgb.resize((w, h), Image.LANCZOS)
    # Mask at tile scale: a tile pixel is plant when any source pixel under it is.
    small = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.BOX)) > 0
    edge = small & ~(np.roll(small, 1, 0) & np.roll(small, -1, 0) & np.roll(small, 1, 1) & np.roll(small, -1, 1))
    a = np.asarray(im).copy(); a[edge] = MAGENTA
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    d.polygon([(x * s, y * s) for x, y in r["opening_polygon_crop_px"]], outline=RED, width=2)
    return im

groups = defaultdict(list)
for r in rows:
    if r["role"] == "extra":
        continue
    key = (r["rig"], "exp2-3" if r["rig"] == "dev" else f"exp{r['experiment_id']}", r["tray_id"])
    groups[key].append(r)
out = DATA / "sheets"; out.mkdir(parents=True, exist_ok=True)
for (rig, exp, tray), rs in sorted(groups.items()):
    cols = sorted({(r["taken_at_utc"], r["day_since_grow_start"], r["role"]) for r in rs})
    cells = sorted({r["cell"] for r in rs}, key=lambda c: (c[0], int(c[1:])))
    size = min(220, (2950 - 50) // len(cols) - 4)
    head = 34
    sheet = Image.new("RGB", (50 + len(cols) * (size + 4), head + len(cells) * (size + 4)), "white")
    d = ImageDraw.Draw(sheet)
    for j, (t, day, role) in enumerate(cols):
        d.text((50 + j * (size + 4) + 2, 2), f"day {day}" + (" late" if role == "late" else ""), fill="black", font=font)
        d.text((50 + j * (size + 4) + 2, 17), t[5:10] + " " + t[11:16] + "Z", fill="black", font=font)
    by = {(r["cell"], r["taken_at_utc"]): r for r in rs}
    for i, c in enumerate(cells):
        d.text((4, head + i * (size + 4) + size // 2 - 7), c, fill="black", font=font)
        for j, (t, _, _) in enumerate(cols):
            r = by.get((c, t))
            if r:
                sheet.paste(tile(r, size), (50 + j * (size + 4), head + i * (size + 4)))
    name = out / f"{rig}_{exp}_tray{tray}.png"
    sheet.save(name); print(name, sheet.size)
