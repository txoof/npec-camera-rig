"""Views for labelling by eye (RGB only, no mask): label_views/<rig>_tray<T>_<part>.jpg.
rows = cells (a chunk), columns = chosen days; each tile is the pot opening plus 15% margin."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT = Path.home() / "scratch/375-cell-floor"; DATA = ROOT / "data"
rig, tray, chunk, size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
roles = sys.argv[5].split(",")  # daily,extra,late
days = None if len(sys.argv) < 7 else {int(x) for x in sys.argv[6].split(",")}
rows = [json.loads(l) for l in open(ROOT / f"work/index_{rig}.jsonl")]
rs = [r for r in rows if r["tray_id"] == tray and r["role"] in roles and (days is None or r["day_since_grow_start"] in days)]
cols = sorted({(r["taken_at_utc"], r["day_since_grow_start"]) for r in rs})
cells = sorted({r["cell"] for r in rs}, key=lambda c: (c[0], int(c[1:])))
font = ImageFont.load_default(size=16)
by = {(r["cell"], r["taken_at_utc"]): r for r in rs}
out = ROOT / "work/label_views"; out.mkdir(exist_ok=True)
for k in range(0, len(cells), chunk):
    part = cells[k:k + chunk]
    sh = Image.new("RGB", (40 + len(cols) * (size + 3), 22 + len(part) * (size + 3)), "white"); d = ImageDraw.Draw(sh)
    for j, (t, day) in enumerate(cols):
        d.text((40 + j * (size + 3), 2), f"d{day} {t[11:13]}Z", fill="black", font=font)
    for i, c in enumerate(part):
        d.text((2, 22 + i * (size + 3) + size // 2), c, fill="black", font=font)
        for j, (t, _) in enumerate(cols):
            r = by.get((c, t))
            if not r: continue
            im = Image.open(DATA / r["rgb_png"]).convert("RGB")
            xs = [p[0] for p in r["opening_polygon_crop_px"]]; ys = [p[1] for p in r["opening_polygon_crop_px"]]
            m = 0.15 * (max(xs) - min(xs))
            im = im.crop((int(min(xs) - m), int(min(ys) - m), int(max(xs) + m), int(max(ys) + m))).resize((size, size), Image.LANCZOS)
            sh.paste(im, (40 + j * (size + 3), 22 + i * (size + 3)))
    f = out / f"{rig}_tray{tray}_{k // chunk}.jpg"; sh.save(f, quality=90); print(f, sh.size)
