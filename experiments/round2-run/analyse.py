"""The Round 2 run's analysis (metrology log 16.4) from the rig's own tray readings in a COPY of
rig.db, made and filled by read_photos.py. Nothing is written into rig.db or the experiment folder.

    python analyse.py WORKDIR --experiment 18 --maps sessions/shuffle-maps-2026-10-22.json \
        --shuffles sessions/shuffles-2026-10-22.csv [--events sessions/events-2026-10-22.csv] --out OUT

`--shuffles` is a CSV with columns shuffle, map, start_utc, finish_utc (map 0, the start layout,
has no start). `--events` has columns time_utc, event. Writes OUT-steadiness.csv,
OUT-detection.csv, OUT-tracking.csv, OUT-pairs.csv and prints the tables.
"""

import argparse
import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import analysis
import read_photos

STILL_SCENE = range(8, 13)  # trays 8 to 12: black pots, nothing grows (16.1)
PLANT_TRAYS = range(1, 8)


def utc(text):
    return datetime.fromisoformat(text)


def load(workdir, experiment_id):
    """(photos, centres, placements, camera_events) of an experiment, from the copy of rig.db.
    `app_up_s` is read from each photo's sidecar file (read only), None when not known."""
    conn = sqlite3.connect(f"file:{workdir / 'rig.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    from npec_rig.captures import experiments_root

    experiments_dir = experiments_root()
    photos = []
    for row in conn.execute(
        "SELECT c.*, r.status FROM capture c LEFT JOIN tray_read r ON r.capture_id = c.id"
        " WHERE c.experiment_id = ? ORDER BY c.taken_at",
        (experiment_id,),
    ):
        sidecar = experiments_dir / (row["path"].removeprefix("experiments/") + ".json")
        app_up_s = None
        if sidecar.exists():
            app_up_s = json.loads(sidecar.read_text()).get("uptime", {}).get("app_up_s")
        photos.append({
            "capture_id": row["id"], "path": row["path"], "taken_at": utc(row["taken_at"]),
            "status": row["status"] or "not read yet", "calibration": row["calibration"],
            "lens_position": row["lens_position"], "flags": json.loads(row["flags"] or "[]"),
            "app_up_s": app_up_s,
        })
    centres, placements = {}, {}
    for row in conn.execute(
        "SELECT t.* FROM tray_reading t JOIN capture c ON c.id = t.capture_id WHERE c.experiment_id = ?",
        (experiment_id,),
    ):
        centres.setdefault(row["capture_id"], {})[row["tray_id"]] = (row["centre_x_px"], row["centre_y_px"])
        placements.setdefault(row["capture_id"], {})[row["tray_id"]] = (row["slot"], row["a1_corner"], row["placement"])
    # Rows from the synthetic camera were written by unit tests leaking into the live rig.db (#241,
    # #253): the rig never runs it, so they are not camera events.
    camera_events = [utc(r[0]) for r in conn.execute(
        "SELECT time_utc FROM camera_events WHERE COALESCE(detail, '') NOT LIKE '%synthetic camera%'")]
    conn.close()
    return photos, centres, placements, camera_events


def read_shuffles(path, maps=None):
    """The shuffles file (shuffle, map, start_utc, finish_utc), with each map's slots when `maps`
    ({map: slots}) is given."""
    return [
        {"shuffle": r["shuffle"], "slots": maps[r["map"]] if maps else None,
         "start": utc(r["start_utc"]) if r["start_utc"] else None, "finish": utc(r["finish_utc"])}
        for r in csv.DictReader(Path(path).open())
    ]


def read_events(path):
    """The events file (time_utc, event) as [(time, words)]; none when `path` is None."""
    return [(utc(r["time_utc"]), r["event"]) for r in csv.DictReader(Path(path).open())] if path else []


_scales = {}


def scale(calibration, x, y):
    """mm per pixel at a point under `calibration`, from its scale field (read from the copy)."""
    from npec_rig.calibration_store import load_saved_calibration

    if calibration not in _scales:
        _scales[calibration] = load_saved_calibration(calibration).scale_field.mm_per_px
    return _scales[calibration](x, y)


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        Path(path).write_text("")
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def table(title, rows, keys):
    print(f"\n{title}")
    print("  " + " | ".join(keys))
    for r in rows:
        print("  " + " | ".join(f"{r[k]:.3f}" if isinstance(r[k], float) else str(r[k]) for k in keys))


def report(photos, centres, placements, camera_events, shuffles, events, out):
    breaks = [(s["start"] or s["finish"], s["finish"]) for s in shuffles] + [(t, t) for t in events]
    # Every photo goes in, read or not: a photo not read breaks the pair across it (16.3, rule 3).
    pairs = analysis.pairs(photos, breaks, camera_events)
    reasons = Counter(p["reason"] or "undisturbed" for p in pairs)
    print("Pairs:", dict(reasons))
    steady = analysis.steadiness(photos, pairs, centres, scale)
    trays = sorted({t for found in centres.values() for t in found})
    found = {cid: set(t) for cid, t in centres.items()}
    detected = analysis.detection(photos, found, trays)
    tracked = analysis.tracking(photos, placements, shuffles)

    table("Steadiness, still scene (trays 8 to 12)", [r for r in steady if r["tray"] in STILL_SCENE],
          ["tray", "window", "pairs", "rms_mm", "max_mm"])
    table("Steadiness, plant trays (1 to 7)", [r for r in steady if r["tray"] in PLANT_TRAYS],
          ["tray", "window", "pairs", "rms_mm", "max_mm"])
    table("Detection per tray, day and window", detected["trays"], ["tray", "day", "window", "photos", "found", "share"])
    table("Photos not read for trays", detected["not read"], ["day", "window", "status", "photos"])
    table("Photos with a tray missed while others were found", detected["misses"], ["capture_id", "taken_at", "missing"])
    table("Tracking per shuffle", tracked["shuffles"],
          ["shuffle", "photos", "right", "wrong", "doubtful", "not found", "not read"])
    table("Wrong readings", tracked["wrong"], ["shuffle", "capture_id", "taken_at", "tray", "read", "map"])
    table("Doubtful readings (the app marked the placement)", tracked["doubtful"],
          ["shuffle", "capture_id", "taken_at", "tray", "placement", "read", "map"])

    write_csv(f"{out}-pairs.csv", pairs)
    write_csv(f"{out}-steadiness.csv", steady)
    write_csv(f"{out}-detection.csv", detected["trays"])
    write_csv(f"{out}-not-read.csv", detected["not read"])
    write_csv(f"{out}-misses.csv", detected["misses"])
    write_csv(f"{out}-tracking.csv", tracked["shuffles"])
    write_csv(f"{out}-wrong.csv", tracked["wrong"])
    write_csv(f"{out}-doubtful.csv", tracked["doubtful"])
    return pairs, steady, detected, tracked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--experiment", type=int, required=True)
    parser.add_argument("--maps", type=Path, required=True)
    parser.add_argument("--shuffles", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    read_photos.use_copy(workdir)

    maps = {str(m["map"]): m["slots"] for m in json.loads(args.maps.read_text())["maps"]}
    shuffles = read_shuffles(args.shuffles, maps)
    events = [t for t, _ in read_events(args.events)]
    report(*load(workdir, args.experiment), shuffles, events, args.out)


if __name__ == "__main__":
    main()
