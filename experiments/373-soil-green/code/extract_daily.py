"""Run on production over ssh (python3 - < extract_daily.py): for each day of experiment 18, the
counted photo nearest 11:00 UTC, and its plant trays' (1 to 6) saved grow-from-leaf-cores readings.
Read-only connection. Lines: id|taken_at|path|tray|outline json|soil|cutoff|plant px|area mm2."""
import json
import sqlite3

c = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
days = [r[0] for r in c.execute("SELECT DISTINCT substr(taken_at, 1, 10) FROM capture WHERE experiment_id = 18 ORDER BY 1")]
for day in days:
    row = c.execute(
        "SELECT c.id FROM capture c JOIN exclusion e ON e.capture_id = c.id WHERE c.experiment_id = 18"
        " AND e.name IS NULL AND substr(c.taken_at, 1, 10) = ? AND c.taken_at >= ? ORDER BY c.taken_at LIMIT 1",
        (day, day + "T11:00")).fetchone()
    if not row:
        continue
    for r in c.execute(
        "SELECT c.id, c.taken_at, c.path, t.tray_id, t.outline, t.grown_soil_level, t.grown_lower_cutoff,"
        " t.grown_plant_px, t.grown_area_mm2 FROM tray_reading t JOIN capture c ON c.id = t.capture_id"
        " WHERE c.id = ? AND t.tray_id BETWEEN 1 AND 6 AND t.grown_plant_px IS NOT NULL ORDER BY t.tray_id", row):
        print("|".join(str(x) for x in r))
