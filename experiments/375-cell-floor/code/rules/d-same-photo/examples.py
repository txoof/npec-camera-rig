"""Example crops for d-same-photo: mask magenta, pot opening red, verdicts written on."""
import csv, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data"
K = lambda r: (r["rig"], r["experiment_id"], r["tray_id"], r["cell"], r["taken_at_utc"])
idx = {K(r): r for r in csv.DictReader(open(DATA / "index.csv"))}
res = {name: {K(r): r for r in csv.DictReader(open(p))} for name, p in (("E", HERE / "results_E.csv"), ("F", HERE / "results_F.csv"))}


def tile(k, title):
    r = idx[k]
    im = Image.open(DATA / r["rgb_png"]).convert("RGB")
    m = np.asarray(Image.open(DATA / r["mask_png"])) > 0
    a = np.asarray(im).copy()
    a[m] = (255, 0, 255)
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    p = [tuple(x) for x in json.loads(r["opening_polygon_crop_px"])]
    d.line(p + [p[0]], fill=(255, 0, 0), width=3)
    im = im.resize((360, int(360 * im.height / im.width)))
    out = Image.new("RGB", (360, im.height + 70), "white")
    out.paste(im, (0, 70))
    d = ImageDraw.Draw(out)
    e, f = res["E"][k], res["F"][k]
    d.text((4, 2), title, fill="black")
    d.text((4, 18), f"{r['rig']} tray {r['tray_id']} {r['cell']} day {r['day_since_grow_start']} {r['taken_at_utc'][:16]}", fill="black")
    d.text((4, 34), f"label: {r['label_outcome']} ({r['label_contents']})", fill="black")
    d.text((4, 50), f"E: {e['verdict']} (z {e['score']})   F: {f['verdict']} (z {f['score']})", fill="black")
    return out


def pick(cond, verdict_rule, n=3):
    out = []
    for k, r in idx.items():
        if cond(r) and verdict_rule(k):
            out.append(k)
    return out[:: max(1, len(out) // n)][:n]


sets = {
    "1_tune_day0_seedling_plant": (lambda r: r["rig"] == "prod" and int(r["tray_id"]) <= 6 and r["day_since_grow_start"] == "0", lambda k: res["E"][k]["verdict"] == "plant"),
    "2_tune_day0_seedling_missed": (lambda r: r["rig"] == "prod" and int(r["tray_id"]) <= 6 and r["day_since_grow_start"] == "0", lambda k: res["E"][k]["verdict"] == "empty"),
    "3_day4_exposure_change_and_day15_blue_mats": (lambda r: r["rig"] == "prod" and int(r["tray_id"]) <= 6 and r["day_since_grow_start"] in ("4", "15") and r["cell"] == "B2", lambda k: True),
    "4_bare_cell_false_plant_days0to6": (lambda r: r["label_contents"].startswith("bare") and int(r["day_since_grow_start"]) <= 6, lambda k: res["E"][k]["verdict"] == "plant"),
    "5_bare_cell_late_false_plant": (lambda r: r["label_contents"].startswith("bare") and r["role"] == "late", lambda k: res["E"][k]["verdict"] == "plant"),
    "6_dev_day7_plants_all_walls_covered": (lambda r: r["rig"] == "dev" and r["role"] == "late" and r["label_outcome"] == "plant", lambda k: res["E"][k]["verdict"] != "plant"),
    "7_dev_open_grid_false_plant": (lambda r: r["rig"] == "dev" and r["label_outcome"] == "empty", lambda k: res["F"][k]["verdict"] == "plant"),
}
for name, (c, v) in sets.items():
    ks = pick(c, v, 4)
    if not ks:
        print("none", name); continue
    tiles = [tile(k, name.replace("_", " ")) for k in ks]
    W = sum(t.width for t in tiles) + 10 * (len(tiles) - 1)
    H = max(t.height for t in tiles)
    sheet = Image.new("RGB", (W, H), "white")
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0)); x += t.width + 10
    sheet.save(HERE / "examples" / f"{name}.png")
    print(name, len(ks))
