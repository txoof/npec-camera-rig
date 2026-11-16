"""Write data/index.jsonl, data/index.csv and the problem-size table (printed, for the README)."""
import csv, json
from collections import defaultdict
from pathlib import Path
ROOT = Path.home() / "scratch/375-cell-floor"; DATA = ROOT / "data"
rows = [json.loads(l) for f in ("index_prod.jsonl", "index_dev.jsonl") for l in open(ROOT / "work" / f)]
labels = {(l["rig"], int(l["experiment_id"]), int(l["tray_id"]), l["cell"]): l for l in csv.DictReader(open(DATA / "labels.csv"))}

def status(m):
    if m is None: return None
    if m["over_other_cells"]: return "leaves over other cells"
    return "plant" if m["plant_px"] else "missing"

for r in rows:
    r["recomputed"]["status"] = status(r["recomputed"])
    if r["stored"]: r["stored"]["status"] = status(r["stored"])
    lab = labels.get((r["rig"], r["experiment_id"], r["tray_id"], r["cell"]))
    r["label_outcome"] = lab and lab["outcome"]; r["label_contents"] = lab and lab["contents"]
    ed = lab and lab["emerged_day"]
    r["label_visible_plant"] = None if not lab or lab["outcome"] == "unclear" else (
        lab["outcome"] == "plant" and ed not in ("", None) and r["day_since_grow_start"] >= int(ed))
    r["blue_mat"] = bool(lab and lab["contents"] == "soil" and (r["blue_fraction_in_opening"] or 0) >= 0.3)
rows.sort(key=lambda r: (r["rig"], r["experiment_id"], r["tray_id"], r["cell"], r["taken_at_utc"]))
with open(DATA / "index.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
cols = ["rig", "experiment_id", "capture_id", "photo_path", "taken_at_utc", "local_time", "day_since_grow_start", "role",
        "tray_id", "tray_type", "cell", "rgb_png", "mask_png", "crop_x0", "crop_y0", "crop_w", "crop_h", "opening_polygon_crop_px",
        "opening_px", "opening_mm2", "mm_per_px_calibration", "mm_per_px_from_stored",
        "recomputed_plant_px", "recomputed_area_mm2", "recomputed_over_other_cells", "recomputed_status",
        "stored_plant_px", "stored_area_mm2", "stored_over_other_cells", "stored_status",
        "mask_px_in_opening", "mask_px_in_crop", "blue_fraction_in_opening", "blue_mat",
        "exposure_us", "analogue_gain", "exposure_x_gain", "exclusion", "jpeg_quality", "jpeg_chroma",
        "label_outcome", "label_contents", "label_visible_plant"]
with open(DATA / "index.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(cols)
    for r in rows:
        s = r["stored"] or {}
        w.writerow([r["rig"], r["experiment_id"], r["capture_id"], r["photo_path"], r["taken_at_utc"], r["local_time"], r["day_since_grow_start"], r["role"],
                    r["tray_id"], r["tray_type"], r["cell"], r["rgb_png"], r["mask_png"], *r["crop_origin_px"], *r["crop_size_px"], json.dumps(r["opening_polygon_crop_px"]),
                    r["opening_px"], r["opening_mm2"], round(r["mm_per_px_calibration"], 6), r["mm_per_px_from_stored"] and round(r["mm_per_px_from_stored"], 6),
                    r["recomputed"]["plant_px"], r["recomputed"]["area_mm2"], int(r["recomputed"]["over_other_cells"]), r["recomputed"]["status"],
                    s.get("plant_px"), s.get("area_mm2") and round(s["area_mm2"], 2), None if not s else int(s["over_other_cells"]), s.get("status"),
                    r["mask_px_in_opening"], r["mask_px_in_crop"], r["blue_fraction_in_opening"], int(r["blue_mat"]),
                    r["exposure_us"], r["analogue_gain"], r["exposure_x_gain"], r["exclusion"], r["jpeg_quality"], r["jpeg_chroma"],
                    r["label_outcome"], r["label_contents"], r["label_visible_plant"]])
# Size of the problem: crops with no plant visible (label), by rig and contents.
groups = defaultdict(list)
for r in rows:
    if r["label_visible_plant"] is False:
        kind = "empty to the end" if r["label_outcome"] == "empty" else "plant cell, before emergence"
        groups[(r["rig"], kind, r["label_contents"])].append(r)
print("| Rig | Cells with no plant visible | Contents | Crops | Cells | Crops with plant_px > 0 | Area when > 0, mm2 (min, median, max) | Of those over 100 mm2 | Stored readings: crops, with plant_px > 0 |")
print("|---|---|---|---|---|---|---|---|---|")
import statistics
for (rig, kind, cont), rs in sorted(groups.items()):
    pos = sorted(r["recomputed"]["area_mm2"] for r in rs if r["recomputed"]["plant_px"] > 0)
    st = [r for r in rs if r["stored"]]
    rng = f"{pos[0]:.1f}, {statistics.median(pos):.1f}, {pos[-1]:.1f}" if pos else "none"
    print(f"| {rig} | {kind} | {cont} | {len(rs)} | {len({(r['experiment_id'], r['tray_id'], r['cell']) for r in rs})} | {len(pos)} | {rng} | {sum(1 for a in pos if a > 100)} | {len(st)}, {sum(1 for r in st if r['stored']['plant_px'] > 0)} |")
print(len(rows), "crops")
