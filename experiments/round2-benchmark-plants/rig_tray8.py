"""The rig's plant area of tray 8 (the benchmark, North 6) in the photos around the phone scans
(#228, metrology log 17.13, step 5). Read-only on rig.db.

Usage: rig_tray8.py FROM TO   (UTC, e.g. 2026-10-28T09:20 2026-10-28T09:59)
"""
import sqlite3
import statistics
import sys

db = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
rows = db.execute(
    "SELECT capture.taken_at, tray_reading.area_mm2, tray_reading.slot, tray_reading.segmenter, exclusion.name"
    " FROM tray_reading JOIN capture ON capture.id = tray_reading.capture_id"
    " LEFT JOIN exclusion ON exclusion.capture_id = capture.id"
    " WHERE tray_reading.tray_id = 8 AND capture.taken_at BETWEEN ? AND ? ORDER BY capture.taken_at",
    (sys.argv[1], sys.argv[2]),
).fetchall()
counted = [r[1] for r in rows if r[4] is None and r[1] is not None]
print(f"{len(rows)} photos, {len(counted)} counted, slots {sorted({r[2] for r in rows})}, segmenter {sorted({r[3] for r in rows})}")
print(f"area mm2: median {statistics.median(counted):.1f}, min {min(counted):.1f}, max {max(counted):.1f}")
