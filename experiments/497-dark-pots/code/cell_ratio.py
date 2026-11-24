"""Cell-level grown / fixed area ratio (metrology log 46.8), from the areas the app already stores per
cell: production's 183 hourly readings of 16 to 23 November (review-434) and the 6 photos of experiment 20,
read from the rig's API (data/api); and the 60 reference cells by their strata, recomputed with the app's
green threshold (fixed) and grow from leaf cores (the draft's lower cutoff). Writes data/cell_ratio.csv
(production readings, one row per cell reading) and data/cell_ratio_ref.csv."""
import csv, glob, json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import segmentation as sg

D = __file__.rsplit("/code/", 1)[0] + "/data"
REF = __file__.rsplit("/code/", 1)[0] + "/../round3-classifier/data"
READ = "/home/txoof/temp.nobackup/rig-copies/ac-testing/review-434/readings"
EMPTY_FROM = {4: "2026-11-23_110053", 5: "2026-11-23_130053", 6: "2026-11-23_140053"}  # first photo with the tray emptied

rows = []
for f in sorted(glob.glob(READ + "/*.json")):
    name = os.path.basename(f)[:-5]
    d = json.load(open(f))
    if d.get("exclusion") or not d.get("trays"):
        continue
    for t in d["trays"]:
        state = "emptied tray" if t["tray_id"] in EMPTY_FROM and name >= EMPTY_FROM[t["tray_id"]] else "tray with plants"
        for c in t["cells"]:
            if c["holds"] == "tag" or c["status"] == "leaves over other cells":
                continue
            rows.append(dict(src="production", photo=name, tray=t["tray_id"], cell=c["cell"], state=state, fixed=c["area_mm2"] or 0.0, grown=c["grown_area_mm2"] or 0.0))
for f in sorted(glob.glob(D + "/api/e20_*.json")):
    d = json.load(open(f))
    if d.get("exclusion") or not d.get("trays"):
        continue
    for t in d["trays"]:
        for c in t["cells"]:
            if c["holds"] == "tag" or c["status"] == "leaves over other cells":
                continue
            rows.append(dict(src="experiment 20", photo=os.path.basename(f)[4:-5], tray=t["tray_id"], cell=c["cell"], state="exp 20 tray", fixed=c["area_mm2"] or 0.0, grown=c["grown_area_mm2"] or 0.0))
with open(D + "/cell_ratio.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

ref = []
seg = sg.ExGSegmenter()
for m in csv.DictReader(open(REF + "/manifest.csv")):
    name = m["file"].rsplit(".", 1)[0]
    rgb = np.asarray(Image.open(f"{REF}/crops/{name}.png").convert("RGB"))
    mask = next(rule.grow_sweep(rgb, np.ones(rgb.shape[:2], bool), [None], lower_cutoff=float(m["cut_h"])))[1]
    fixed = seg.segment(rgb)
    k = float(m["mm2_per_px"])
    ref.append(dict(id=m["id"], rig=m["rig"], stratum=m["stratum"], fixed_mm2=fixed.sum() * k, grown_mm2=mask.sum() * k, fixed_px=int(fixed.sum()), grown_px=int(mask.sum())))
with open(D + "/cell_ratio_ref.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(ref[0])); w.writeheader(); w.writerows(ref)
print(len(rows), len(ref))
