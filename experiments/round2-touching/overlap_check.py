"""Read-only: old (per tray) vs new (shared strip split) plant areas on one stored potato-run photo."""
import sqlite3, sys
from npec_rig import segmentation
from npec_rig.calibration_store import calibration_for_photos, load_saved_calibration
from npec_rig.tray_placement import _outline

db = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
db.row_factory = sqlite3.Row
row = db.execute("select id, path, calibration from capture where path like ?", ("%"+sys.argv[1],)).fetchone()
trays = db.execute("select * from tray_reading where capture_id=? order by tray_id", (row["id"],)).fetchall()
print(row["path"])
sf = load_saved_calibration(calibration_for_photos(row["calibration"])).scale_field
mask = segmentation.load_mask(row["path"])
pairs = []
for t in trays:
    cx, cy = t["centre_x_px"], t["centre_y_px"]
    pairs.append((_outline((cx, cy), t["tilt_deg"], sf.px_per_mm(cx, cy)), (cx, cy)))
new = segmentation.measure_trays(mask, pairs, sf)
tot_old = tot_new = 0
for t, (outline, _), n in zip(trays, pairs, new):
    o = segmentation.measure_plant(mask, outline, sf)
    tot_old += o.area_mm2; tot_new += n.area_mm2
    if abs(o.area_mm2 - n.area_mm2) > 0.01:
        print(f"tray {t['tray_id']:2d} {t['slot']:8s} stored {t['area_mm2']:8.1f}  old {o.area_mm2:8.1f}  new {n.area_mm2:8.1f}  diff {n.area_mm2-o.area_mm2:+7.1f} mm2")
print(f"all trays: old {tot_old:.1f}, new {tot_new:.1f} mm2")
