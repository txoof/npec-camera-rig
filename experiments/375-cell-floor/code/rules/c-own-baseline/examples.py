"""Example crops for variant A: mask magenta, pot opening red, centre zone outline red dashed-ish."""
import csv, json, random
import numpy as np
from PIL import Image, ImageDraw
from pathlib import Path
HERE = Path(__file__).resolve().parent; D = Path.home() / "scratch/375-cell-floor/data"
rows = list(csv.DictReader(open(D / "index.csv")))
res = {(r["rig"], r["tray_id"], r["cell"], r["taken_at_utc"]): r["verdict"] for r in csv.DictReader(open(HERE / "results_A.csv"))}
def v(r): return res[(r["rig"], r["tray_id"], r["cell"], r["taken_at_utc"])]
def lab(r):
    return "empty" if r["label_outcome"] == "empty" else ("plant" if r["label_visible_plant"] == "True" else "not visible")
cases = [
 ("right_bare_fringe_possible", lambda r: r["label_contents"].startswith("bare") and v(r) == "possible"),
 ("right_bare_empty", lambda r: r["label_contents"].startswith("bare") and v(r) == "empty" and int(r["mask_px_in_opening"] or 0) > 0),
 ("right_seedling_day0_plant", lambda r: r["rig"] == "prod" and r["day_since_grow_start"] == "0" and lab(r) == "plant" and v(r) == "plant" and int(r["tray_id"]) > 6),
 ("wrong_testobject_plant", lambda r: r["label_contents"].startswith("no soil") and v(r) == "plant" and float(r["recomputed_area_mm2"] or 0) < 50),
 ("wrong_dev_seedling_possible", lambda r: r["rig"] == "dev" and lab(r) == "plant" and v(r) == "possible"),
 ("wrong_seedling_day0_empty", lambda r: r["rig"] == "prod" and r["day_since_grow_start"] == "0" and lab(r) == "plant" and v(r) == "empty" and int(r["tray_id"]) > 6),
]
random.seed(3)
for name, cond in cases:
    c = [r for r in rows if cond(r)]
    if not c: print("none", name); continue
    r = random.choice(c)
    im = Image.open(D / r["rgb_png"]).convert("RGB"); m = np.array(Image.open(D / r["mask_png"]).convert("L")) > 0
    a = np.array(im); a[m] = [255, 0, 255]; im = Image.fromarray(a)
    dr = ImageDraw.Draw(im)
    p = [tuple(x) for x in json.loads(r["opening_polygon_crop_px"])]
    dr.polygon(p, outline=(255, 0, 0), width=3)
    P = np.array(p); c0 = P.mean(0); dr.polygon([tuple(c0 + 0.5 * (q - c0)) for q in P], outline=(200, 0, 0), width=1)
    W = 600; im = im.resize((W, int(W * im.size[1] / im.size[0])), Image.NEAREST)
    canvas = Image.new("RGB", (W, im.size[1] + 70), "white"); canvas.paste(im, (0, 70))
    d2 = ImageDraw.Draw(canvas)
    d2.text((8, 6), f"variant A verdict: {v(r)}   hand label: {lab(r)} ({r['label_contents']})", fill="black")
    d2.text((8, 26), f"{r['rig']} tray {r['tray_id']} {r['cell']} day {r['day_since_grow_start']} {r['taken_at_utc'][:16]}  area {float(r['recomputed_area_mm2'] or 0):.1f} mm2", fill="black")
    d2.text((8, 46), "magenta = ExG mask, red = pot opening, thin red = centre zone (d >= 0.25)", fill="black")
    canvas.save(HERE / "examples" / f"{name}.png"); print(name, r["rig"], r["tray_id"], r["cell"], r["taken_at_utc"])
