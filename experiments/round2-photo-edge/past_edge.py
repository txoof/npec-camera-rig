"""Read-only (#282 item 1): how far each tray's outline reaches past the photo edge, in mm, on
stored photos of experiment 18, from the stored centre and tilt and the calibration's scale.

Usage: past_edge.py STEM [STEM ...]   (e.g. 2026-10-27/143453_829671)
"""
import sqlite3
import sys

from PIL import Image

from npec_rig import tray_readings
from npec_rig.calibration_store import calibration_for_photos, load_saved_calibration
from npec_rig.captures import photo_file
from npec_rig.tray_placement import TrayPlacement, _outline

db = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
db.row_factory = sqlite3.Row
for stem in sys.argv[1:]:
    row = db.execute("select id, path, calibration from capture where path like ?", ("%" + stem,)).fetchone()
    sf = load_saved_calibration(calibration_for_photos(row["calibration"])).scale_field
    with Image.open(photo_file(row["path"])) as im:
        w, h = im.size
    print(f"{row['path']} ({w} x {h} px)")
    for t in db.execute("select * from tray_reading where capture_id=? order by tray_id", (row["id"],)):
        c = (t["centre_x_px"], t["centre_y_px"])
        p = TrayPlacement(t["tray_id"], c, t["slot"], t["a1_corner"], t["tilt_deg"],
                          _outline(c, t["tilt_deg"], sf.px_per_mm(*c)), t["margin_mm"])
        mm = tray_readings._outside_mm(p, (h, w), sf)
        if mm > 0:
            mark = "partly outside" if mm > tray_readings.PAST_EDGE_MM else ""
            print(f"  tray {t['tray_id']:2d} {t['slot']:8s} {mm:5.1f} mm past the edge  {mark}")
