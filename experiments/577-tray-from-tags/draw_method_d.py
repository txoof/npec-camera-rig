"""Before-and-after sheet for one still: the app on production now above, the re-cut below.

This is the script that made the figures of metrology log 56.9. `draw.py` beside it does the same
for method C, which was not adopted.

Outlines are yellow and numbered; each label is black on a filled yellow box, so it stays
readable over white table, brown soil and blue plastic alike. Never blue or cyan lines: they
cannot be seen on blue trays.
"""
import json, sys
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from npec_rig.calibration import scale_field_from_dict
from npec_rig.tags import TagDetection, detect_tags
from npec_rig.tray_placement import BLOCK_SUSPECT, find_outlines, name_trays
import methods

FACTOR, WIDE = 4, 1800
YELLOW, BLACK, WHITE = (255, 210, 0), (0, 0, 0), (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX
root, idx, outpath, caption = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
rec = json.loads((root / "meta.json").read_text())[idx]
files = root / "files"
jpg, cal = files / (rec["path"] + ".jpg"), files / "calibration" / f"{rec['calibration']}.json"
sf = scale_field_from_dict(json.loads(cal.read_text())["scale_field"])
cache = root / "tagcache" / (rec["path"].replace("/", "_") + ".json")
if rec.get("tags"):
    raw = json.loads(rec["tags"])
elif cache.exists():
    raw = json.loads(cache.read_text())
else:
    with Image.open(jpg) as im:
        found = detect_tags(np.asarray(im.convert("RGB")))
    raw = [{"tag_id": t.tag_id, "corners": [list(c) for c in t.corners], "centre": list(t.centre)} for t in found]
tags = [TagDetection(t["tag_id"], tuple(map(tuple, t["corners"])), tuple(t["centre"])) for t in raw]
with Image.open(jpg) as im:
    w = im.size[0]
    im.draft("RGB", (im.size[0] // FACTOR, im.size[1] // FACTOR))
    img = np.asarray(im.convert("RGB"))
factor = w / img.shape[1]
outlines = find_outlines(img, sf, factor)
a_trays = name_trays(outlines, tags)
c_placed, left = methods.place_recut_blocks(tags, img, sf, factor)


def label(p, text, at, scale=0.8):
    (tw, th), base = cv2.getTextSize(text, FONT, scale, 2)
    x, y = int(at[0] - tw / 2), int(at[1])
    cv2.rectangle(p, (x - 8, y - th - 8), (x + tw + 8, y + base + 6), YELLOW, -1)
    cv2.rectangle(p, (x - 8, y - th - 8), (x + tw + 8, y + base + 6), BLACK, 2)
    cv2.putText(p, text, (x, y), FONT, scale, BLACK, 2, cv2.LINE_AA)


def panel(title, shapes, notes):
    p = img.copy()
    for n, (corners, note) in enumerate(zip(shapes, notes), 1):
        pts = np.round(np.asarray(corners, float) / factor).astype(np.int32)
        cv2.polylines(p, [pts], True, YELLOW, 5)
        c = pts.mean(axis=0)
        label(p, f"{n}" + (f"  {note}" if note else ""), (c[0], c[1]), 1.0)
    scale = WIDE / p.shape[1]
    p = cv2.resize(p, (WIDE, int(p.shape[0] * scale)))
    bar = np.zeros((78, WIDE, 3), np.uint8)
    cv2.putText(bar, title, (16, 52), FONT, 1.15, WHITE, 2, cv2.LINE_AA)
    return np.vstack([bar, p])


a_note = []
for o in outlines:
    t = [x for x in a_trays if x.outline == o.corners]
    ids = ", ".join(str(x.tray_id) for x in t if x.tray_id is not None)
    warn = "WARNED" if any(BLOCK_SUSPECT in x.warnings for x in t) else ("no tag" if not ids else "")
    a_note.append(((f"tray {ids}" if ids else "") + (" " + warn if warn else "")).strip())
c_note = [(f"tray {p.tray_id} re-cut" if p.tray_id is not None else "app outline") for p in c_placed]
top = panel(f"BEFORE - the app running on production now: {len(outlines)} outlines",
            [o.corners for o in outlines], a_note)
bot = panel(f"AFTER - app, with tag re-cut of blocks short of tags: {len(c_placed)} trays, {left['blocks_recut']} block(s) re-cut",
            [p.corners for p in c_placed], c_note)
gap = np.full((18, WIDE, 3), 255, np.uint8)
cap = np.zeros((66, WIDE, 3), np.uint8)
cv2.putText(cap, caption, (16, 44), FONT, 0.85, WHITE, 2, cv2.LINE_AA)
outpath.parent.mkdir(parents=True, exist_ok=True)
Image.fromarray(np.vstack([top, gap, bot, cap])).save(outpath, quality=85, optimize=True)
print(outpath)
