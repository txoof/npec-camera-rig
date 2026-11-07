"""Draw example crops for variant E: mask magenta, pot opening red, verdict written on it."""
import csv, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent; DATA = HERE.parent.parent / "data"
idx = list(csv.DictReader(open(DATA / "index.csv")))
res = list(csv.DictReader(open(HERE / "results_E.csv")))
def pick(cond, k=0):
    hits = [i for i, (x, r) in enumerate(zip(idx, res)) if cond(x, r)]
    return hits[min(k, len(hits) - 1)] if hits else None
cases = {
 "right_plant_tune_seedling_day5": lambda x, r: x["rig"] == "prod" and x["tray_id"] == "3" and x["day_since_grow_start"] == "5" and r["verdict"] == "plant",
 "right_fringe_bare_cell_possible": lambda x, r: x["label_contents"].startswith("bare") and r["verdict"] == "possible" and 0 < int(x["mask_px_in_opening"]) < 100,
 "wrong_bare_cell_with_object_plant": lambda x, r: x["label_contents"].startswith("bare") and r["verdict"] == "plant" and int(x["mask_px_in_opening"]) > 1000,
 "wrong_bare_cell_fringe_plant": lambda x, r: x["label_contents"].startswith("bare") and r["verdict"] == "plant" and 0 < int(x["mask_px_in_opening"]) < 100,
 "wrong_seedling_day1_only_possible": lambda x, r: x["rig"] == "prod" and int(x["tray_id"]) <= 6 and x["day_since_grow_start"] == "1" and r["verdict"] == "possible",
 "wrong_dev_open_grid_plant": lambda x, r: x["rig"] == "dev" and x["label_outcome"] == "empty" and r["verdict"] == "plant",
}
for name, cond in cases.items():
    i = pick(cond, 3)
    if i is None: print("none", name); continue
    x, r = idx[i], res[i]
    rgb = Image.open(DATA / x["rgb_png"]).convert("RGB")
    m = np.array(Image.open(DATA / x["mask_png"]).convert("L")) > 127
    a = np.array(rgb); a[m] = [255, 0, 255]; im = Image.fromarray(a)
    s = min(1.0, 700 / max(im.size)) if max(im.size) > 700 else 600 / max(im.size)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.NEAREST)
    d = ImageDraw.Draw(im)
    poly = [(px * s, py * s) for px, py in json.loads(x["opening_polygon_crop_px"])]
    d.line(poly + [poly[0]], fill=(255, 0, 0), width=2)
    t = f"E: {r['verdict']} (label {x['label_outcome']}) {x['rig']} tray {x['tray_id']} {x['cell']} day {x['day_since_grow_start']} sightings {r['score']}"
    d.rectangle([0, 0, im.width, 18], fill=(0, 0, 0)); d.text((4, 3), t, fill=(255, 255, 255))
    im.save(HERE / "examples" / f"{name}.png"); print(name, i, t)
