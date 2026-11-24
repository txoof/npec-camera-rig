"""The green target on tray 10, measured alone (log 46). In the app's mask of each photo, the target is
what survives an opening with a 201 px square (so the patches of false plant in the dark cells beside
it, which touch it, are not part of it); the zone is that, widened by 15 px. For each level, the mask
pixels inside the zone, against the app's. Writes data/target_zone_{FORM}.csv."""
import csv, glob, json, os, sys
import cv2
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import images, segmentation as sg
from run_photos import trays_of, TAG_SHRINK

R = "/home/txoof/temp.nobackup/rig-copies/ac-testing/497-dark-pots"
D = __file__.rsplit("/code/", 1)[0] + "/data"
FORM = os.environ.get("FORM", "B")
sig = {}
for s in ("e18", "e20"):
    for r in csv.DictReader(open(f"{D}/sweep_{s}_{FORM}.csv")):
        sig[(r["set"], r["photo"])] = float(r["sigma_b"])
rows = []
for api_f in sorted(glob.glob(D + "/api/*.json")):
    n = os.path.basename(api_f)[:-5]; s, _, stem = n.partition("_")
    api = json.load(open(api_f))
    t10 = [t for t in trays_of(api) if t[0] == 10]
    if not t10:
        continue
    if s == "e18":
        day, photo = stem.split("_", 1)[0], stem.split("_", 1)[1]
        jpg = f"{R}/e18/{day}/{photo}.jpg"
    else:
        photo = stem; jpg = f"{R}/e20/{photo}.jpg"
    if (s, photo) not in sig:
        continue
    tid, outline, tag, mm2, t = t10[0]
    rgb = images.decode_full(jpg)
    box = sg._box(np.zeros(rgb.shape[:2], bool), outline); x0, y0, x1, y1 = box
    inside = sg._inside(box, outline)
    c = np.asarray(tag, float) - [x0, y0]; ctr = c.mean(axis=0); tagc = [ctr + TAG_SHRINK * (c - ctr)]
    sub = rgb[y0:y1, x0:x1]
    sg_ = sig[(s, photo)]
    sweeps = [("app", "-", None)] + [("c", k, float(k)) for k in range(13)] + [("b", k, k * sg_) for k in range(13)]
    res = list(rule.grow_sweep(sub, inside, [x[2] for x in sweeps], tagc, form=FORM))
    base = res[0][1].view(np.uint8)
    core = cv2.morphologyEx(base, cv2.MORPH_OPEN, np.ones((201, 201), np.uint8))
    zone = cv2.dilate(core, np.ones((31, 31), np.uint8)) > 0
    bpx = int((base > 0)[zone].sum())
    for (m, lev, thr), (_t, mask, _s, _l) in zip(sweeps, res):
        px = int(mask[zone].sum())
        rows.append(dict(form=FORM, photo=f"{s}/{photo}", method=m, level=lev, zone_px_app=bpx, zone_px=px, change_pct=100 * (px - bpx) / bpx, mm2_per_px=mm2))
    print(photo, bpx, flush=True)
with open(D + f"/target_zone_{FORM}.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
