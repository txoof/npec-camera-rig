"""The rule on the 60 reference cells (metrology log 33, 46): grow_from_cores with the rule on each
lossless crop, the lower cutoff given as the draft's (manifest cut_h, worked out for the whole tray),
against Aaron's truth mask. One row per cell, method and level."""
import csv, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule

DATA = __file__.rsplit("/code/", 1)[0] + "/../round3-classifier/data"
LEVELS = list(range(13))
FORM = os.environ.get("FORM", "A")
rows = []
for m in csv.DictReader(open(DATA + "/manifest.csv")):
    name = m["file"].rsplit(".", 1)[0]
    rgb = np.asarray(Image.open(f"{DATA}/crops/{name}.png").convert("RGB"))
    truth = np.asarray(Image.open(f"{DATA}/truth/{name}_truth.png").convert("L")) > 127
    inside = np.ones(rgb.shape[:2], bool)
    res, s = rule.noise_arrays(rgb, inside, form=FORM)
    sig, sig_all, _ = rule.sigma_from(res, s)
    sweeps = [("app", "-", None)] + [("c", n, float(n)) for n in LEVELS] + [("b", k, k * sig) for k in LEVELS]
    for (method, lev, thr), (_t, mask, soil, lc) in zip(sweeps, rule.grow_sweep(rgb, inside, [x[2] for x in sweeps], lower_cutoff=float(m["cut_h"]), form=FORM)):
        inter = int((mask & truth).sum()); union = int((mask | truth).sum())
        rows.append(dict(form=FORM, id=m["id"], rig=m["rig"], stratum=m["stratum"], split=m["split"], method=method, level=lev,
                         thr=thr if thr is not None else "", sigma_b=round(sig, 3), sigma_all=round(sig_all, 3),
                         px=int(mask.sum()), truth_px=int(truth.sum()), inter=inter, union=union,
                         iou=inter / union if union else 1.0, draft_px=m["draft_px_in_crop"], mm2_per_px=m["mm2_per_px"]))
with open(sys.argv[1], "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
