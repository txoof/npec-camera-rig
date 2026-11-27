"""One still: run the merged finder and report what the warnings do. Printed as one JSON line."""
import json, sys, collections
from pathlib import Path
import numpy as np
from PIL import Image
from npec_rig.calibration import scale_field_from_dict
from npec_rig.tags import TagDetection, detect_tags
from npec_rig.tray_placement import BLOCK_SUSPECT, find_outlines, name_trays

FACTOR = 4
root, idx = Path(sys.argv[1]), int(sys.argv[2])
rec = json.loads((root / "meta.json").read_text())[idx]
files = root / "files"
jpg = files / (rec["path"] + ".jpg")
cal = files / "calibration" / f"{rec['calibration']}.json"
if not jpg.exists() or not cal.exists():
    print(json.dumps({"path": rec["path"], "skip": "no photo or calibration"})); raise SystemExit
sf = scale_field_from_dict(json.loads(cal.read_text())["scale_field"])

if rec.get("tags"):
    tags = [TagDetection(t["tag_id"], tuple(map(tuple, t["corners"])), tuple(t["centre"]))
            for t in json.loads(rec["tags"])]
    how = "stored"
else:
    with Image.open(jpg) as im:
        full = np.asarray(im.convert("RGB"))
    tags = detect_tags(full)
    del full
    how = "detected"

with Image.open(jpg) as im:
    w = im.size[0]
    im.draft("RGB", (im.size[0] // FACTOR, im.size[1] // FACTOR))
    img = np.asarray(im.convert("RGB"))
outlines = find_outlines(img, sf, w / img.shape[1])
trays = name_trays(outlines, tags)
blocks = collections.Counter(o.block for o in outlines)
touching = {b for b, n in blocks.items() if n > 1}
print(json.dumps({
    "path": rec["path"], "experiment": rec.get("experiment"), "tags_from": how,
    "outlines": len(outlines), "blocks": len(blocks),
    "touching_blocks": len(touching), "biggest_block": max(blocks.values()) if blocks else 0,
    "tray_tags": sum(1 for t in tags if 0 <= t.tag_id <= 299), "trays": len(trays),
    "warned": sum(1 for t in trays if BLOCK_SUSPECT in t.warnings),
    "no_tag": sum(1 for t in trays if "no tag" in t.warnings),
    "edge_now": sum(1 for t in trays if "partly outside the photo" in t.warnings),
    "edge_stored": sum(1 for s in rec["stored"] if "partly outside the photo" in (s["warnings"] or "")),
    "stored_rows": len(rec["stored"]),
}))
