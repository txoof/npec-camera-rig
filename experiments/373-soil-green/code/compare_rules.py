"""Tray areas by grow from leaf cores, the rule before #373 (lower cutoff = max(floor, soil level +
0.07) always) against this branch (the floor when the soil level is in the top bin), on the photo
nearest 11:00 UTC each day, plant trays 1 to 6. mm2 from the saved reading's mm2 per px (tag
corners are not stored, so offline px differ slightly from the app's: the column 'old/saved').
python compare_rules.py data/daily_1100.txt PHOTO_DIR > data/compare_rules.csv"""
import csv, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from npec_rig import images, segmentation as s
Image.MAX_IMAGE_PIXELS = None
rows = [l.split("|") for l in Path(sys.argv[1]).read_text().splitlines()]
w = csv.writer(sys.stdout)
w.writerow(["capture_id", "taken_at", "tray", "mats", "soil_level", "old_cutoff", "new_cutoff", "soil_hidden",
            "saved_px", "old_px", "new_px", "old_mm2", "new_mm2", "new_over_old", "old_over_saved"])
for path in sorted({r[2] for r in rows}):
    rgb = np.asarray(Image.open(Path(sys.argv[2]) / (Path(path).name + ".jpg")).convert("RGB"))
    for cid, taken, _p, tray, outline, soil, cutoff, saved_px, saved_mm2 in (r for r in rows if r[2] == path):
        pts = [tuple(p) for p in json.loads(outline)]
        x0, y0 = max(0, int(min(p[0] for p in pts))), max(0, int(min(p[1] for p in pts)))
        x1, y1 = min(rgb.shape[1], int(max(p[0] for p in pts)) + 1), min(rgb.shape[0], int(max(p[1] for p in pts)) + 1)
        box = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        m = Image.new("L", (x1 - x0, y1 - y0)); ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=1)
        inside = np.asarray(m).astype(bool)
        new = s.grow_from_cores(box, inside)
        old_cut = s.GROWN_FLOOR if new.soil_level is None else max(s.GROWN_FLOOR, new.soil_level + s.GROWN_GAP)
        old = s.grow_from_cores(box, inside, lower_cutoff=old_cut)
        per_px = float(saved_mm2) / int(saved_px) if int(saved_px) else float("nan")
        op, np_ = int(old.mask.sum()), int(new.mask.sum())
        w.writerow([cid, taken[:16], tray, "yes" if taken >= "2026-11-06T09:20" else "no", f"{new.soil_level:+.3f}",
                    f"{old_cut:+.3f}", f"{new.lower_cutoff:+.3f}", new.soil_hidden, saved_px, op, np_,
                    f"{op * per_px:.0f}", f"{np_ * per_px:.0f}", f"{np_ / op:.3f}" if op else "", f"{op / int(saved_px):.3f}" if int(saved_px) else ""])
    del rgb
    sys.stdout.flush()
