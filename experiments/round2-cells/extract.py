"""A slim read-only copy of experiment 18's tables for the per-cell growth study (#394, metrology log 38).

Two halves:

    ssh pi@ac-testing 'ulimit -v 1000000; python3 -' < extract.py | python3 extract.py load OUT.db

On production (no arguments) it opens rig.db read-only (`mode=ro`), in its own process, not through
the app, and prints one JSON line per row: only the tables and columns the 16.9 pair rules need,
for experiment 18, and cells of trays 1 to 7. Memory stays at one row (a cursor is walked). It
writes nothing on production.

`load OUT.db` reads those lines on the controller and writes them into a new SQLite file with the
same table and column names, so the 16.9 scripts' queries run on it unchanged.
"""
import json
import sqlite3
import sys

EXPERIMENT = 18
TABLES = {
    "capture": ("select id, taken_at, path, experiment_id, calibration, lens_position, flags,"
                " exposure_us, analogue_gain from capture where experiment_id = ?"),
    "tray_read": ("select t.capture_id, t.read_at, t.status from tray_read t"
                  " join capture c on c.id = t.capture_id where c.experiment_id = ?"),
    "exclusion": ("select e.capture_id, e.name from exclusion e"
                  " join capture c on c.id = e.capture_id where c.experiment_id = ?"),
    "app_start": "select started_at from app_start where ? is not null",
    "camera_events": "select time_utc, detail from camera_events where ? is not null",
    "tray_reading": ("select t.capture_id, t.tray_id, t.slot, t.centre_x_px, t.centre_y_px, t.a1_corner, t.placement, t.warnings,"
                     " t.area_mm2, t.grown_area_mm2, t.grown_method from tray_reading t"
                     " join capture c on c.id = t.capture_id where c.experiment_id = ?"
                     " and t.tray_id is not null"),
    "cell_reading": ("select r.capture_id, r.tray_id, r.cell, r.holds, r.centre_x_px, r.centre_y_px,"
                     " r.area_mm2, r.over_other_cells, r.grown_area_mm2, r.grown_over_other_cells"
                     " from cell_reading r join capture c on c.id = r.capture_id"
                     " where c.experiment_id = ? and r.tray_id between 1 and 7"),
}


def dump():
    db = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
    out = sys.stdout
    for table, sql in TABLES.items():
        cur = db.execute(sql, (EXPERIMENT,))
        cols = [d[0] for d in cur.description]
        out.write(json.dumps({"table": table, "cols": cols}) + "\n")
        for row in cur:
            out.write(json.dumps(row) + "\n")
    out.write(json.dumps({"end": True}) + "\n")


def load(path):
    db = sqlite3.connect(path)
    table = cols = None
    batch = []
    ended = False

    def flush():
        if batch:
            db.executemany(f"insert into {table} values ({','.join('?' * len(cols))})", batch)
            batch.clear()

    for line in sys.stdin:
        item = json.loads(line)
        if isinstance(item, dict):
            flush()
            if item.get("end"):
                ended = True
                break
            table, cols = item["table"], item["cols"]
            db.execute(f"create table {table} ({', '.join(cols)})")
            continue
        batch.append(item)
        if len(batch) >= 10000:
            flush()
    flush()
    if not ended:
        sys.exit("stream ended early: copy incomplete")
    db.execute("create index cell_cap on cell_reading (capture_id)")
    db.execute("create index tray_cap on tray_reading (capture_id)")
    db.commit()
    for t in TABLES:
        print(t, db.execute(f"select count(*) from {t}").fetchone()[0])


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "load":
        load(sys.argv[2])
    else:
        dump()
