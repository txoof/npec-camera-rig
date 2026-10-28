"""The rig's plant area of tray 8 (the benchmark, North 6) in the photos around the phone scans
(#228, metrology log 17.13, step 5). Read-only on rig.db (`settings.db_path`).

Only photos taken as captures, with tray 8 placed alone in its slot (`placed` or `close call`) and
an area from SEGMENTER, are used; of these, the photos with no exclusion are counted, as the app
counts them.

Usage: rig_tray8.py FROM TO   (UTC, FROM included, TO not: e.g. 2026-10-28T09:20 2026-10-28T09:59)
"""
import sqlite3
import statistics
import sys

from npec_rig.settings import db_path

SEGMENTER = "green threshold, 0.1"

db = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
rows = db.execute(
    "SELECT capture.taken_at, tray_reading.area_mm2, tray_reading.slot, exclusion.name"
    " FROM tray_reading JOIN capture ON capture.id = tray_reading.capture_id"
    " LEFT JOIN exclusion ON exclusion.capture_id = capture.id"
    " WHERE tray_reading.tray_id = 8 AND capture.purpose = 'capture'"
    " AND tray_reading.placement IN ('placed', 'close call') AND tray_reading.segmenter = ?"
    " AND capture.taken_at >= ? AND capture.taken_at < ? ORDER BY capture.taken_at",
    (SEGMENTER, sys.argv[1], sys.argv[2]),
).fetchall()
counted = [r[1] for r in rows if r[3] is None]
print(f"{len(rows)} photos, {len(counted)} counted, slots {sorted({r[2] for r in rows})}, {SEGMENTER}")
print(f"area mm2: median {statistics.median(counted):.1f}, min {min(counted):.1f}, max {max(counted):.1f}")
