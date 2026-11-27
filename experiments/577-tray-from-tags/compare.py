"""One still through methods A, B and C of metrology log 56. One JSON line out."""
import json, sys, math, collections
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from npec_rig.calibration import scale_field_from_dict
from npec_rig.tags import TagDetection, detect_tags
from npec_rig.tray_placement import BLOCK_SUSPECT, find_outlines, name_trays
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "wt/npec-577-tray-from-tags/experiments/577-tray-from-tags"))
import methods

FACTOR = 4
root, idx = Path(sys.argv[1]), int(sys.argv[2])
rec = json.loads((root / "meta.json").read_text())[idx]
files = root / "files"
jpg, cal = files / (rec["path"] + ".jpg"), files / "calibration" / f"{rec['calibration']}.json"
if not jpg.exists() or not cal.exists():
    print(json.dumps({"path": rec["path"], "skip": "missing"})); raise SystemExit
sf = scale_field_from_dict(json.loads(cal.read_text())["scale_field"])

cache = root / "tagcache" / (rec["path"].replace("/", "_") + ".json")
if rec.get("tags"):
    raw = json.loads(rec["tags"])
elif cache.exists():
    raw = json.loads(cache.read_text())
else:
    with Image.open(jpg) as im:
        found = detect_tags(np.asarray(im.convert("RGB")))
    raw = [{"tag_id": t.tag_id, "corners": [list(c) for c in t.corners], "centre": list(t.centre)}
           for t in found]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(raw))
tags = [TagDetection(t["tag_id"], tuple(map(tuple, t["corners"])), tuple(t["centre"])) for t in raw]
with Image.open(jpg) as im:
    w = im.size[0]
    im.draft("RGB", (im.size[0] // FACTOR, im.size[1] // FACTOR))
    img = np.asarray(im.convert("RGB"))
factor = w / img.shape[1]

outlines = find_outlines(img, sf, factor)
a_trays = name_trays(outlines, tags)
A = [(o.centre, o.corners) for o in outlines]
B = [(p.centre, p.corners) for p in methods.place_from_tags(tags, sf, factor)]
c_placed, left = methods.place_tags_then_blue(tags, img, sf, factor)
C = [(p.centre, p.corners) for p in c_placed]

def iou(p, q):
    a = np.asarray(p, np.float32); b = np.asarray(q, np.float32)
    inter, _ = cv2.intersectConvexConvex(a, b)
    ua = cv2.contourArea(a) + cv2.contourArea(b) - inter
    return inter / ua if ua > 0 else 0.0

def agree(x, y, ppm):
    """How many of x have a partner in y within 30 mm and IoU >= 0.80 (log 56 scoring)."""
    n = 0
    for cx, px in x:
        for cy, py in y:
            if math.dist(cx, cy) / ppm <= 30.0 and iou(px, py) >= 0.80:
                n += 1; break
    return n

mid_ppm = sf.px_per_mm(img.shape[1] * factor / 2, img.shape[0] * factor / 2)
out = {"path": rec["path"], "experiment": rec.get("experiment"),
       "A": len(A), "B": len(B), "C": len(C), "tray_tags": len(methods._tray_tags(tags)),
       "A_matched_by_B": agree(A, B, mid_ppm), "A_matched_by_C": agree(A, C, mid_ppm),
       "C_matched_by_A": agree(C, A, mid_ppm),
       "warned_A": sum(1 for t in a_trays if BLOCK_SUSPECT in t.warnings),
       "max_nudge_mm": round(max([p.moved_mm for p in c_placed], default=0.0), 1),
       "mean_ring_C": round(float(np.mean([p.ring for p in c_placed])), 3) if c_placed else None,
       "leftover_share": round(left["leftover_share"], 3),
       "overlapping_pairs": left["overlapping_pairs"],
       "from_tags": left.get("from_tags"), "from_blue": left.get("from_blue"),
       "rings": left.get("rings"), "tray_rings": left.get("tray_rings")}
print(json.dumps(out))
