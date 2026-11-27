"""Grow-from-leaf-cores area of soil-only trays, per tray and UTC day, on counted photos (#293).

Read only: opens `rig.db` with `mode=ro`. Counted photos are those the app counts: an `exclusion`
row with no name (not lights off, not light changing, not a visit). Prints CSV to stdout:
tray, day, photos, then the grown area's 5th percentile, median, 95th percentile and largest, and
the fixed green cutoff's median, all in mm2. Standard library only, so it runs on a rig as it is.

    python3 soil_days.py RIG_DB EXPERIMENT_ID tagged 9,10,11,12      # trays by tag id
    python3 soil_days.py RIG_DB EXPERIMENT_ID untagged-left          # development's NW and SW trays

`untagged-left`: the trays found without a tag whose centre lies left of x = 2200 px; above
y = 3500 px is called NW, below SW (the table as the development camera sees it, 2026-11-19).
"""

import collections
import sqlite3
import sys


def pct(values: list[float], q: float) -> float:
    return values[int(q * (len(values) - 1))]


def main() -> None:
    db, experiment, kind = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = c.execute(
        """select r.tray_id, r.found, r.centre_x_px, r.centre_y_px, substr(cp.taken_at, 1, 10),
                  r.grown_area_mm2, r.area_mm2
           from tray_reading r join capture cp on cp.id = r.capture_id
           join exclusion e on e.capture_id = cp.id and e.name is null
           where cp.experiment_id = ? and r.grown_area_mm2 is not null""",
        (experiment,),
    ).fetchall()
    wanted = {int(t) for t in sys.argv[4].split(",")} if kind == "tagged" else set()
    days = collections.defaultdict(list)
    for tray_id, found, x, y, day, grown, fixed in rows:
        if kind == "tagged":
            if tray_id not in wanted:
                continue
            name = str(tray_id)
        else:
            if found != "photo, no tag" or x >= 2200:
                continue
            name = "NW" if y < 3500 else "SW"
        days[(name, day)].append((grown, fixed))
    print("tray,day,photos,grown_p5,grown_median,grown_p95,grown_max,fixed_median")
    for (name, day), v in sorted(days.items()):
        g = sorted(a for a, _ in v)
        f = sorted(b for _, b in v)
        print(f"{name},{day},{len(g)},{pct(g, .05):.1f},{pct(g, .5):.1f},{pct(g, .95):.1f},{g[-1]:.1f},{pct(f, .5):.1f}")


if __name__ == "__main__":
    main()
