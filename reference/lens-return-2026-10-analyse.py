"""Lens-return test 2026-10-05: per-tag area error change against the last baseline round.
Tags are matched by ID and position (IDs repeat across sheets). Read-only."""
import json, sys
import numpy as np
from npec_rig import images
from npec_rig.calibration_store import load_current_calibration
from npec_rig.certainty_map import tag_errors

SESSION = "/var/lib/npec-rig/calibration/validations/20261005T071549445423.json"
BASELINE = "2026-10-05/071742_491975"
CX, CY = 9152 / 2, 6944 / 2
s = json.load(open(SESSION))
art = load_current_calibration()
assert art.frame_stem == s["calibration_stem"], "current calibration is not this session's"
slots = {sl["name"]: sl["box"] for sl in s["slots"]}

def errs(ref):
    e, _ = tag_errors(images.stored_tag_detections(ref), art.scale_field, art.calibration_tag_size_mm)
    return e

def slot_of(x, y):
    for n, (x0, y0, x1, y1) in slots.items():
        if x0 <= x <= x1 and y0 <= y <= y1:
            return n
    return None

base = errs(BASELINE)
bxy = np.array([(b.x, b.y) for b in base])
refs = sys.argv[1:] or [r["capture"] for r in s["rounds"] if r["captured_at"] > "2026-10-05T07:30"]
for ref in refs:
    d = []
    for t in errs(ref):
        dist = np.hypot(*(bxy - (t.x, t.y)).T)
        i = int(dist.argmin())
        if dist[i] < 20 and base[i].tag_id == t.tag_id:
            r = float(np.hypot(t.x - CX, t.y - CY))
            d.append((t.error_pct - base[i].error_pct, r, slot_of(t.x, t.y)))
    a = np.array([x[0] for x in d]); rr = np.array([x[1] for x in d])
    print(f"{ref}: {len(d)} tags matched, change median {np.median(a):+.2f}, sd {a.std():.2f} points")
    for lo, hi in [(0, 1000), (1000, 1500), (1500, 1e9)]:
        m = (rr >= lo) & (rr < hi)
        print(f"  ring {lo}-{hi if hi < 1e9 else 'edge'} px: n={m.sum()}, median {np.median(a[m]):+.2f}")
    per = {}
    for v, _, n in d:
        per.setdefault(n, []).append(v)
    print("  slots: " + ", ".join(f"{n} {np.median(v):+.2f}" for n, v in sorted(per.items(), key=lambda kv: str(kv[0]))))
