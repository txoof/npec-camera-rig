"""Noise of the greenness numerator (2G - R - B, form B) and of G - R (form A) against analogue gain,
in the same pixels of the same trays on lit photos (gain 1.0) and lights-off photos (gain 4.0, not
counted by the app), production and development (log 46.5). Production: the outlines of trays 4 to 6
at 14:00 UTC on 23 November (emptied). Development: a fixed rectangle over the left tray (4 x 5 soil
plugs and empty cells), same pixels in every photo. Outputs a CSV."""
import csv, json, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import images, segmentation as sg

R = "/home/txoof/temp.nobackup/rig-copies"
D = __file__.rsplit("/code/", 1)[0] + "/data"
api = json.load(open(D + "/api/e18_2026-11-23_140053_650696.json"))
outlines = [t["outline_px"] for t in api["trays"] if t["tray_id"] in (4, 5, 6)]
PROD = [("e18/2026-11-23/140053_650696", "lit"), ("e18/2026-11-23/130053_611736", "lit"), ("e18/2026-11-24/030053_730173", "dark"), ("e18/2026-11-24/070053_735341", "dark")]
DEV = [("2026-11-23/120020_897275", "lit"), ("2026-11-23/200020_898019", "lit"), ("2026-11-24/100020_896994", "lit"), ("2026-11-24/080520_923498", "lit"), ("2026-11-24/050020_988903", "dark")]
RECT = (320, 2520, 1880, 4240)  # x0, y0, x1, y1 on development photos

def run(rig, name, kind, rgb, sel_boxes):
    meta = json.load(open(f"{R}/{'ac-testing' if rig=='prod' else 'npec-rig-01'}/497-dark-pots/{name}.json"))
    m = meta["sensor_metadata"]; q = meta.get("photo_quality") or {}
    out = dict(rig=rig, photo=name.split("/", 1)[1] if rig == "prod" else name, kind=kind, gain=round(m["AnalogueGain"], 2),
               exposure_ms=round(m["ExposureTime"] / 1000, 1), jpeg=f"{q.get('quality')} {q.get('chroma')}")
    for form in "AB":
        ra, sa = [], []
        for box, inside in sel_boxes:
            x0, y0, x1, y1 = box
            res, s = rule.noise_arrays(rgb[y0:y1, x0:x1], inside, form=form); ra.append(res); sa.append(s)
        res = np.concatenate(ra); s = np.concatenate(sa)
        dark, allp, n = rule.sigma_from(res, s)
        out[f"sigma{form}_dark10"] = round(dark, 3); out[f"sigma{form}_all"] = round(allp, 3)
        out["mean_S"] = round(float(s.mean()), 1)
    return out

rows = []
for name, kind in PROD:
    rgb = images.decode_full(f"{R}/ac-testing/497-dark-pots/{name}.jpg")
    sel = []
    for o in outlines:
        box = sg._box(np.zeros(rgb.shape[:2], bool), o); sel.append((box, sg._inside(box, o)))
    rows.append(run("prod", name, kind, rgb, sel)); print(rows[-1], flush=True)
for name, kind in DEV:
    rgb = images.decode_full(f"{R}/npec-rig-01/497-dark-pots/{name}.jpg")
    x0, y0, x1, y1 = RECT
    sel = [(RECT, np.ones((y1 - y0, x1 - x0), bool))]
    rows.append(run("dev", name, kind, rgb, sel)); print(rows[-1], flush=True)
with open(D + "/noise_vs_gain.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
