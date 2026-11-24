"""The rule on development photos (JPEG 85, 4:4:4; young seedlings on soil plugs), no tray outlines
(npec-rig-01 was not asked for any): two fixed rectangles over two trays, whole rectangle as the tray,
no tag cut-out. Share of the app's mask the rule removes (form B, floor of N levels, and k x sigma_b),
and the number of mask pixels (log 46.6). Writes data/dev_rect.csv."""
import csv, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import rule
from npec_rig import images
R = "/home/txoof/temp.nobackup/rig-copies/npec-rig-01/497-dark-pots"
D = __file__.rsplit("/code/", 1)[0] + "/data"
RECTS = {"left tray": (320, 2520, 1880, 4240), "top-right tray": (6240, 1360, 7760, 3200)}
rows = []
for name in ("2026-11-23/120020_897275", "2026-11-23/200020_898019", "2026-11-24/080520_923498"):
    rgb = images.decode_full(f"{R}/{name}.jpg")
    for rn, (x0, y0, x1, y1) in RECTS.items():
        sub = rgb[y0:y1, x0:x1]; inside = np.ones(sub.shape[:2], bool)
        res, s = rule.noise_arrays(sub, inside, form="B"); sig, sall, _ = rule.sigma_from(res, s)
        sweeps = [("app", "-", None)] + [("c", n, float(n)) for n in range(13)] + [("b", k, k * sig) for k in range(13)]
        out = list(rule.grow_sweep(sub, inside, [x[2] for x in sweeps], form="B"))
        base = int(out[0][1].sum())
        for (m, lev, thr), (_t, mask, _s, _l) in zip(sweeps, out):
            rows.append(dict(photo=name, rect=rn, sigma_b=round(sig, 3), method=m, level=lev, app_px=base, px=int(mask.sum()), removed_pct=100 * (1 - int(mask.sum()) / base) if base else 0))
        print(name, rn, "sigma_b %.2f" % sig, "app px", base, flush=True)
with open(D + "/dev_rect.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
