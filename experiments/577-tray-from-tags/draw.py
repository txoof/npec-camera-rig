"""Side-by-side sheet for one still: the app's outlines (left) against method C's (right).

Outlines are drawn in red and numbered; never blue or cyan, which cannot be seen on blue trays.
"""
import json, sys
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from npec_rig.calibration import scale_field_from_dict
from npec_rig.tags import TagDetection, detect_tags
from npec_rig.tray_placement import BLOCK_SUSPECT, find_outlines, name_trays
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "wt/npec-577-tray-from-tags/experiments/577-tray-from-tags"))
import methods

FACTOR, WIDE = 4, 1500
RED, WHITE, BLACK = (255, 40, 40), (255, 255, 255), (0, 0, 0)
root, idx, outpath, caption = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
rec = json.loads((root / "meta.json").read_text())[idx]
files = root / "files"
jpg, cal = files / (rec["path"] + ".jpg"), files / "calibration" / f"{rec['calibration']}.json"
sf = scale_field_from_dict(json.loads(cal.read_text())["scale_field"])
if rec.get("tags"):
    tags = [TagDetection(t["tag_id"], tuple(map(tuple, t["corners"])), tuple(t["centre"]))
            for t in json.loads(rec["tags"])]
else:
    with Image.open(jpg) as im:
        tags = detect_tags(np.asarray(im.convert("RGB")))
with Image.open(jpg) as im:
    w = im.size[0]
    im.draft("RGB", (im.size[0] // FACTOR, im.size[1] // FACTOR))
    img = np.asarray(im.convert("RGB"))
factor = w / img.shape[1]
outlines = find_outlines(img, sf, factor)
a_trays = name_trays(outlines, tags)
c_placed, left = methods.place_tags_then_blue(tags, img, sf, factor)

def panel(title, shapes, notes):
    p = img.copy()
    for n, (corners, note) in enumerate(zip(shapes, notes), 1):
        pts = np.round(np.asarray(corners, float) / factor).astype(np.int32)
        cv2.polylines(p, [pts], True, RED, 4)
        c = pts.mean(axis=0).astype(int)
        label = f"{n}" + (f" {note}" if note else "")
        cv2.putText(p, label, (c[0] - 30, c[1]), cv2.FONT_HERSHEY_SIMPLEX, 1.4, BLACK, 7)
        cv2.putText(p, label, (c[0] - 30, c[1]), cv2.FONT_HERSHEY_SIMPLEX, 1.4, WHITE, 3)
    scale = WIDE / p.shape[1]
    p = cv2.resize(p, (WIDE, int(p.shape[0] * scale)))
    bar = np.zeros((70, WIDE, 3), np.uint8)
    cv2.putText(bar, title, (14, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.1, WHITE, 2)
    return np.vstack([bar, p])

a_note = []
for o in outlines:
    t = [x for x in a_trays if x.outline == o.corners]
    ids = ", ".join(str(x.tray_id) for x in t if x.tray_id is not None)
    warn = "WARNED" if any(BLOCK_SUSPECT in x.warnings for x in t) else ("no tag" if not ids else "")
    a_note.append((f"tray {ids} " if ids else "") + warn)
c_note = [f"tray {p.tray_id} {p.moved_mm:.0f}mm" for p in c_placed]
left_panel = panel(f"A, the app now: {len(outlines)} outlines", [o.corners for o in outlines], a_note)
right_panel = panel(f"C, tags then blue: {len(c_placed)} trays, leftover {left['leftover_share']:.2f} tray",
                    [p.corners for p in c_placed], c_note)
sheet = np.hstack([left_panel, np.full((left_panel.shape[0], 16, 3), 255, np.uint8), right_panel])
cap = np.zeros((60, sheet.shape[1], 3), np.uint8)
cv2.putText(cap, caption, (14, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, WHITE, 2)
outpath.parent.mkdir(parents=True, exist_ok=True)
Image.fromarray(np.vstack([sheet, cap])).save(outpath, quality=85, optimize=True)
print(outpath)
