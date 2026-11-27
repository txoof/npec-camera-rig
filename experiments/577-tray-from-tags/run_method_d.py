"""Method D against the app, on one still. One JSON line out."""
import json, sys, math
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from npec_rig.calibration import scale_field_from_dict
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import BLOCK_SUSPECT, find_outlines, name_trays
import methods  # methods.py sits beside this script

root, idx = Path(sys.argv[1]), int(sys.argv[2])
rec = json.loads((root / "meta.json").read_text())[idx]
files = root / "files"
jpg, cal = files / (rec["path"] + ".jpg"), files / "calibration" / f"{rec['calibration']}.json"
if not jpg.exists() or not cal.exists():
    print(json.dumps({"path": rec["path"], "skip": 1})); raise SystemExit
sf = scale_field_from_dict(json.loads(cal.read_text())["scale_field"])
cache = root / "tagcache" / (rec["path"].replace("/", "_") + ".json")
raw = json.loads(rec["tags"]) if rec.get("tags") else (json.loads(cache.read_text()) if cache.exists() else [])
tags = [TagDetection(t["tag_id"], tuple(map(tuple, t["corners"])), tuple(t["centre"])) for t in raw]
with Image.open(jpg) as im:
    w = im.size[0]
    im.draft("RGB", (im.size[0] // 4, im.size[1] // 4))
    img = np.asarray(im.convert("RGB"))
factor = w / img.shape[1]
outlines = find_outlines(img, sf, factor)
named = name_trays(outlines, tags)
D, rep = methods.place_recut_blocks(tags, img, sf, factor)

def iou(p, q):
    a, b = np.asarray(p, np.float32), np.asarray(q, np.float32)
    i, _ = cv2.intersectConvexConvex(a, b)
    u = cv2.contourArea(a) + cv2.contourArea(b) - i
    return i / u if u > 0 else 0.0

ppm = sf.px_per_mm(img.shape[1] * factor / 2, img.shape[0] * factor / 2)
matched = 0
for o in outlines:
    if any(math.dist(o.centre, d.centre) / ppm <= 30 and iou(o.corners, d.corners) >= 0.80 for d in D):
        matched += 1
print(json.dumps({
    "path": rec["path"], "A": len(outlines), "D": len(D),
    "A_matched_by_D": matched, "blocks_recut": rep["blocks_recut"],
    "warned": sum(1 for t in named if BLOCK_SUSPECT in t.warnings),
    "tray_tags": len(methods._tray_tags(tags)),
}))
