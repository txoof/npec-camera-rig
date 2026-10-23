"""Check the analysis on the 20 October capture (experiment 16, metrology log 15.5l): fed the app's
tray readings of those photos (read_photos.py), does it reproduce what 15.5l found?

    python check_oct20.py WORKDIR --out OUT

Compared, from 15.5l's own outputs in experiments/round1-trays/ (the known answers):
1. Still by still, tray by tray (shuffle-day CSV): found or not, slot, A1 corner, and the placed
   centre within 1 mm.
2. Lit and dark (overnight CSV): photos with all 12 tags against status "read" with 12 trays;
   photos with no tag against status "no tags found".
3. Tracking against the layouts as laid out (sessions/as-laid-out-2026-10-20.json). 20 October
   has Aaron's leave times only, no start times, so each layout's start and finish are taken from
   the moves 15.5l found: a layout is in place from its first settled still, and the next shuffle
   starts just after the last still before the trays moved.
"""

import argparse
import csv
import json
import math
from datetime import timedelta
from pathlib import Path

import analyse
import read_photos

ROUND1 = Path(__file__).resolve().parent.parent / "round1-trays"
HERE = Path(__file__).resolve().parent
CENTRE_TOLERANCE_MM = 1.0  # a decision: 15.5l's CSV rounds centres to the pixel (about 0.1 mm)


def boundaries(rows, layouts):
    """[{"shuffle", "slots", "start", "finish"}] from 15.5l's shuffle-day rows (one per still and tray)."""
    stills = {}
    for r in rows:
        stills.setdefault(r["still"], r)
    ordered = sorted(stills.values(), key=lambda r: r["taken_at_utc"])
    names = list(dict.fromkeys(r["layout"] for r in ordered))
    shuffles = []
    for name in names:
        mine = [r for r in ordered if r["layout"] == name]
        settled = [r for r in mine if r["settled"] == "True"]
        finish = analyse.utc((settled or mine)[0]["taken_at_utc"])
        shuffles.append({"shuffle": name, "slots": layouts[name], "start": None, "finish": finish, "_stills": mine})
    for before, after in zip(shuffles, shuffles[1:]):
        # The trailing run of not-settled stills in the layout before: its first still is the last
        # one still in place (settled looks at the next still), so the move starts just after it.
        mine = before["_stills"]
        i = len(mine)
        while i > 0 and mine[i - 1]["settled"] != "True":
            i -= 1
        last_in_place = mine[i] if i < len(mine) else mine[-1]
        after["start"] = analyse.utc(last_in_place["taken_at_utc"]) + timedelta(seconds=1)
    for s in shuffles:
        del s["_stills"]
    return shuffles


def stem(path):
    return path.rsplit("/", 1)[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    read_photos.use_copy(workdir)

    photos, centres, placements, camera_events = analyse.load(workdir, 16)
    by_stem = {stem(p["path"]): p for p in photos}
    day_rows = list(csv.DictReader((ROUND1 / "shuffle-day-2026-10-20_57f74959.csv").open()))
    night_rows = list(csv.DictReader((ROUND1 / "overnight-2026-10-20_57f74959.csv").open()))
    laid_out = json.loads((HERE / "sessions/as-laid-out-2026-10-20.json").read_text())
    print("1. Still by still against 15.5l")
    counts = {"tray positions": 0, "same found": 0, "same slot and corner": 0, "centre within 1 mm": 0}
    differ, worst = [], 0.0
    for r in day_rows:
        p = by_stem.get(r["still"])
        if p is None:
            differ.append((r["still"], r["tray"], "photo not in rig.db copy"))
            continue
        counts["tray positions"] += 1
        tray, cid = int(r["tray"]), p["capture_id"]
        app_found = tray in centres.get(cid, {})
        if app_found != (r["found"] == "True"):
            differ.append((r["still"], tray, f"found: 15.5l {r['found']}, app {app_found} ({p['status']})"))
            continue
        counts["same found"] += 1
        if not app_found:
            continue
        if placements[cid][tray][:2] == (r["slot"], r["a1"]):
            counts["same slot and corner"] += 1
        else:
            differ.append((r["still"], tray, f"15.5l {r['slot']} {r['a1']}, app {placements[cid][tray][:2]}"))
        (x, y), (x0, y0) = centres[cid][tray], (float(r["x_px"]), float(r["y_px"]))
        mm = math.hypot(x - x0, y - y0) * analyse.scale(p["calibration"], x0, y0)
        worst = max(worst, mm)
        if mm <= CENTRE_TOLERANCE_MM:
            counts["centre within 1 mm"] += 1
        else:
            differ.append((r["still"], tray, f"centre {mm:.2f} mm from 15.5l"))
    print(" ", counts, f"largest centre difference {worst:.3f} mm")

    print("2. Lit and dark against 15.5l's overnight stills")
    light = {"all 12 and read with 12": 0, "none and no tags found": 0, "other": 0}
    for r in night_rows:
        p = by_stem.get(r["still"])
        n = len(centres.get(p["capture_id"], {})) if p else None
        if r["tags_found"] == "12" and p and p["status"] == "read" and n == 12:
            light["all 12 and read with 12"] += 1
        elif r["tags_found"] == "0" and p and p["status"] == "no tags found":
            light["none and no tags found"] += 1
        else:
            light["other"] += 1
            differ.append((r["still"], "-", f"15.5l tags {r['tags_found']}, app {p and p['status']} with {n} trays"))
    print(" ", light)

    # Written before step 3, which stops if the experiment has more than one calibration.
    print(f"\nDifferences from 15.5l: {len(differ)}")
    for d in differ:
        print("  ", *d)
    analyse.write_csv(f"{args.out}-differences.csv", [{"still": s, "tray": t, "difference": d} for s, t, d in differ])

    print("\n3. The analysis of 16.4 on the 20 October photos (layouts as laid out)")
    shuffles = boundaries(day_rows, laid_out["layouts"])
    analyse.report(photos, centres, placements, camera_events, shuffles, [], args.out)


if __name__ == "__main__":
    main()
