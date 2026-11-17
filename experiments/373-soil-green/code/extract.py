"""Run on production over ssh (python3 - < extract.py): experiment 18's soil level per tray per
counted photo, read through a read-only connection, written to stdout as CSV. Metrology log 38."""
import csv
import sqlite3
import sys

conn = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
rows = conn.execute(
    "SELECT c.id, c.taken_at, t.tray_id, t.slot, t.grown_soil_level, t.grown_lower_cutoff, t.warnings"
    " FROM tray_reading t JOIN capture c ON c.id = t.capture_id"
    " JOIN exclusion e ON e.capture_id = c.id"
    " WHERE c.experiment_id = 18 AND e.name IS NULL AND t.grown_soil_level IS NOT NULL"
    " ORDER BY c.taken_at, t.tray_id")
w = csv.writer(sys.stdout)
w.writerow(["capture_id", "taken_at", "tray_id", "slot", "soil_level", "lower_cutoff", "warnings"])
w.writerows(rows)
