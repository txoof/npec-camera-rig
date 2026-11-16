"""Build the #375 cell dataset: one photo at a time, cells placed and measured with the project's own
functions (tray_placement.place_cells, segmentation.ExGSegmenter, segmentation.measure_cells), crops
and index rows written under data/. Usage: process.py RIG [CAPTURE_ID ...]"""
import json, math, os, sys
from pathlib import Path

ROOT = Path.home() / "scratch/375-cell-floor"
RIG = sys.argv[1]
os.environ["NPEC_RIG_CALIBRATION_DIR"] = str(ROOT / "raw/calibration" / RIG)
os.environ["NPEC_RIG_MASKS_DIR"] = str(ROOT / "work/masks-unused")
os.environ["NPEC_RIG_PHOTOS_DIR"] = str(ROOT / "work/photos-unused")
os.environ["NPEC_RIG_EXPERIMENTS_DIR"] = str(ROOT / "work/experiments-unused")

import numpy as np
from PIL import Image
from npec_rig import images, segmentation
from npec_rig.calibration_store import calibration_for_photos, load_saved_calibration
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import TrayPlacement, place_cells, CELL_GRIDS
from npec_rig.randomization import tray_type

Image.MAX_IMAGE_PIXELS = None
SEG = segmentation.ExGSegmenter()
DATA = ROOT / "data"
sel = [s for s in json.load(open(ROOT / "work/selection.json")) if s["rig"] == RIG]
meta = json.load(open(ROOT / f"work/meta_{RIG}.json"))
# 2 x 2 trays: A1 bearing as stored for the tray in experiment 3 (one value per tray, 842 photos), so
# cell names match the rig's own readings; used for experiment 2 as well (same physical trays).
bearings = {b["tray_id"]: b["lo"] for b in meta["bearings"]}
only = {int(x) for x in sys.argv[2:]}
out_jsonl = ROOT / f"work/index_{RIG}.jsonl"
done = set()
if out_jsonl.exists():
    done = {json.loads(l)["capture_id"] for l in open(out_jsonl)}


def poly_area(p):
    return 0.5 * abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))))


for s in sel:
    cid = s["capture_id"]
    if (only and cid not in only) or (not only and cid in done):
        continue
    m = meta["photos"][str(cid)]
    sf = load_saved_calibration(calibration_for_photos(s["calibration"])).scale_field
    scale_stem = calibration_for_photos(s["calibration"])
    tags = [TagDetection(d["tag_id"], tuple(tuple(c) for c in d["corners"]), tuple(d["centre"])) for d in m["tags"]["value"]]
    carried = {}
    for t in tags:
        carried[t.tag_id] = carried.get(t.tag_id, 0) + 1
    by_id = {t.tag_id: t for t in tags}
    rgb = images.decode_full(ROOT / "raw" / RIG / f"{s['path']}.jpg")
    H, W = rgb.shape[:2]
    mask = SEG.segment(rgb)
    stored = {}
    for c in m["cells"]:
        stored[(c["tray_id"], c["cell"])] = c
    rows = []
    for tr in m["trays"]:
        tid = tr["tray_id"]
        if tid is None or tr["outline"] is None:
            continue
        ttype = tray_type(tid).name
        if ttype not in CELL_GRIDS:
            continue
        p = TrayPlacement(tid, (tr["centre_x_px"], tr["centre_y_px"]), tr["slot"], tr["a1_corner"], tr["tilt_deg"],
                          tuple(tuple(c) for c in json.loads(tr["outline"])), tr["margin_mm"], tr["placement"] or "placed",
                          tr["found"] or "tag only", tuple(json.loads(tr["warnings"] or "[]")))
        if carried.get(tid) != 1 or p.status != "placed":
            print("skip tray", tid, "carried", carried.get(tid), p.status)
            continue
        cells = place_cells(p, by_id[tid], sf, a1_bearing_deg=bearings.get(tid) if ttype == "2x2" else None)
        measures = segmentation.measure_cells(mask, cells, sf, outline_px=p.outline)
        for cell, cm in zip(cells, measures):
            if cell.holds != "plant":
                continue
            cs = np.asarray(cell.corners)
            side = float(np.mean([math.dist(cell.corners[i], cell.corners[(i + 1) % 4]) for i in range(4)]))
            x0 = max(0, int(math.floor(cs[:, 0].min() - side / 2))); y0 = max(0, int(math.floor(cs[:, 1].min() - side / 2)))
            x1 = min(W, int(math.ceil(cs[:, 0].max() + side / 2))); y1 = min(H, int(math.ceil(cs[:, 1].max() + side / 2)))
            crop = rgb[y0:y1, x0:x1]; mcrop = mask[y0:y1, x0:x1]
            poly = [[round(x - x0, 2), round(y - y0, 2)] for x, y in cell.corners]
            # Fractions inside the opening (pixel centres inside the polygon).
            from matplotlib.path import Path as MPath
            yy, xx = np.mgrid[0:crop.shape[0], 0:crop.shape[1]]
            inside = MPath(poly).contains_points(np.c_[xx.ravel() + 0.5, yy.ravel() + 0.5]).reshape(crop.shape[:2])
            r, g, b = (crop[..., i].astype(np.int16) for i in range(3))
            n_in = int(inside.sum())
            blue = (b > r + 30) & (b > g + 10)
            ts = s["taken_at"][:19].replace("-", "").replace(":", "") + "Z"
            d = DATA / "crops" / RIG / f"exp{s['experiment_id']}" / f"tray{tid}" / cell.name
            d.mkdir(parents=True, exist_ok=True)
            Image.fromarray(crop).save(d / f"{ts}_rgb.png", compress_level=6)
            Image.fromarray(mcrop).convert("1").save(d / f"{ts}_mask.png")
            st = stored.get((tid, cell.name))
            mm_cal = 1 / sf.px_per_mm(*cell.centre)
            row = dict(
                rig=RIG, experiment_id=s["experiment_id"], capture_id=cid, photo_path=s["path"], taken_at_utc=s["taken_at"],
                local_time=s["local_time"], day_since_grow_start=s["day_since_grow_start"], role=s["role"],
                tray_id=tid, tray_type=ttype, cell=cell.name,
                rgb_png=str((d / f"{ts}_rgb.png").relative_to(DATA)), mask_png=str((d / f"{ts}_mask.png").relative_to(DATA)),
                crop_origin_px=[x0, y0], crop_size_px=[x1 - x0, y1 - y0], opening_polygon_crop_px=poly,
                opening_centre_full_px=[round(cell.centre[0], 2), round(cell.centre[1], 2)],
                opening_px=n_in, opening_mm2=round(poly_area(cell.corners) * mm_cal**2, 1),
                mm_per_px_calibration=mm_cal,
                mm_per_px_from_stored=(math.sqrt(st["area_mm2"] / st["plant_px"]) if st and st["plant_px"] else None),
                calibration=s["calibration"], scale_calibration=scale_stem,
                recomputed=dict(plant_px=cm.plant_px, area_mm2=round(cm.area_mm2, 2), over_other_cells=cm.over_other_cells,
                                plant_centre_px=None if cm.centre_px is None else [round(v, 1) for v in cm.centre_px]),
                stored=None if st is None else dict(plant_px=st["plant_px"], area_mm2=st["area_mm2"], over_other_cells=bool(st["over_other_cells"]),
                                                    segmenter=st["segmenter"], cell_rule=st["cell_rule"],
                                                    corners_max_diff_px=round(max(math.dist(a, b) for a, b in zip(json.loads(st["corners"]), cell.corners)), 2)),
                mask_px_in_opening=int(mcrop[inside].sum()), mask_px_in_crop=int(mcrop.sum()),
                blue_fraction_in_opening=round(float(blue[inside].mean()), 3) if n_in else None,
                exposure_us=s["exposure_us"], analogue_gain=s["analogue_gain"], exposure_x_gain=s["exposure_us"] * s["analogue_gain"],
                exclusion=s["exclusion"], flags=s["flags"], lens_position=s["lens_position"],
                jpeg_quality=s["jpeg_quality"], jpeg_chroma=s["jpeg_chroma"],
                tray_placement=dict(found=tr["found"], warnings=json.loads(tr["warnings"] or "[]"), outside_mm=tr["outside_mm"], tilt_deg=tr["tilt_deg"]),
                a1_bearing_deg=bearings.get(tid) if ttype == "2x2" else None,
            )
            rows.append(row)
    del rgb, mask
    with open(out_jsonl, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    diffs = [r["stored"] for r in rows if r["stored"]]
    msg = ""
    if diffs:
        bad = sum(1 for r in rows if r["stored"] and r["stored"]["plant_px"] != r["recomputed"]["plant_px"])
        msg = f" stored: {len(diffs)} cells, corner diff max {max(d['corners_max_diff_px'] for d in diffs)}, plant_px differ {bad}"
    print(cid, s["local_time"], len(rows), "cells" + msg, flush=True)
