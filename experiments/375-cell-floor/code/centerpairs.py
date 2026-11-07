"""Centre of each pot opening (middle 60%) for chosen days, side by side per cell, for labelling."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT = Path.home() / "scratch/375-cell-floor"; DATA = ROOT / "data"
rig, tray, days, size, per_row = sys.argv[1], int(sys.argv[2]), [int(x) for x in sys.argv[3].split(",")], int(sys.argv[4]), int(sys.argv[5])
rows = [json.loads(l) for l in open(ROOT / f"work/index_{rig}.jsonl")]
rs = [r for r in rows if r["tray_id"] == tray and r["role"] == "daily" and r["day_since_grow_start"] in days]
cells = sorted({r["cell"] for r in rs}, key=lambda c: (c[0], int(c[1:])))
by = {(r["cell"], r["day_since_grow_start"]): r for r in rs}
font = ImageFont.load_default(size=16)
bw = len(days) * (size + 2) + 12
nrow = (len(cells) + per_row - 1) // per_row
sh = Image.new("RGB", (per_row * bw, nrow * (size + 22)), "white"); d = ImageDraw.Draw(sh)
for k, c in enumerate(cells):
    X, Y = (k % per_row) * bw, (k // per_row) * (size + 22)
    d.text((X + 2, Y + 2), f"{c}  days {','.join(map(str, days))}", fill="red", font=font)
    for j, day in enumerate(days):
        r = by.get((c, day))
        if not r: continue
        im = Image.open(DATA / r["rgb_png"]).convert("RGB")
        xs = [p[0] for p in r["opening_polygon_crop_px"]]; ys = [p[1] for p in r["opening_polygon_crop_px"]]
        cx, cy, s = sum(xs) / 4, sum(ys) / 4, 0.3 * (max(xs) - min(xs))
        sh.paste(im.crop((int(cx - s), int(cy - s), int(cx + s), int(cy + s))).resize((size, size), Image.LANCZOS), (X + j * (size + 2), Y + 20))
out = ROOT / f"work/lv_center/{rig}_tray{tray}_{'-'.join(map(str, days))}.jpg"; out.parent.mkdir(exist_ok=True)
sh.save(out, quality=90); print(out, sh.size)
