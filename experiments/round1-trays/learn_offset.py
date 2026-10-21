"""Round 2 (issue #236): the tray offset of a cell A1 tag lying any way round, learned from one layout (15.5l).

Method: docs/metrology-log.md section 15.5l, decided before any later still was looked at. For each
tray in each still of the learning step, the vector from the tag centre to the FastSAM mask centre
is put in the frame shuffle.py places with: the tray's SW heading turned by the tag's tilt only, and
reversed when the plan has A1 at NE. The offset is the median over trays of each tray's median.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> learn_offset.py track-oct20-learn.csv

Reads the tracking result, the shuffle plan and the calibration; prints the offsets.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys

import numpy as np

import trays
from footprint import frame
from shuffle import tilt
from npec_rig.calibration_store import load_calibration

SW_HEADING_DEG = 180.0
PLAN = trays.SESSIONS / "shuffle-maps-2026-10-20.json"


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("track", help="track-NAME.csv")
    ap.add_argument("--step", default="1", help="the learning step")
    ap.add_argument("--round", type=int, default=1, help="the plan round laid out in that step")
    args = ap.parse_args(argv)

    plan = next(r for r in json.loads(PLAN.read_text())["rounds"] if r["round"] == args.round)
    a1 = {v["tray"]: v["a1"] for v in plan["slots"].values()}
    db = sqlite3.connect(f"file:{trays.RIG / 'rig.db'}?mode=ro", uri=True)
    per_tray: dict[int, list[np.ndarray]] = {}
    with open(args.track) as f:
        for r in csv.DictReader(f):
            if r["step"] != args.step or r["label"] != "measured":
                continue
            stem = db.execute("select calibration from capture where path like ?",
                              (f"%/{r['still']}",)).fetchone()[0]
            sf = load_calibration(trays.RIG / "calibration" / f"{stem}.json").scale_field
            tx, ty = float(r["tag_x_px"]), float(r["tag_y_px"])
            d = (np.array([float(r["x_px"]), float(r["y_px"])]) - [tx, ty]) / sf.px_per_mm(tx, ty)
            right, up = frame(SW_HEADING_DEG + tilt(float(r["heading_deg"])))
            v = np.array([d @ right, d @ up]) * (-1 if a1[int(r["tray"])] == "NE" else 1)
            per_tray.setdefault(int(r["tray"]), []).append(v)
    meds = {}
    for t in sorted(per_tray):
        vs = np.array(per_tray[t])
        meds[t] = np.median(vs, axis=0)
        spread = np.linalg.norm(vs - meds[t], axis=1).max()
        print(f"  tray {t:2d} A1 {a1[t]}: ({meds[t][0]:7.1f}, {meds[t][1]:7.1f}) mm  n {len(vs)}  max {spread:5.1f}")
    common = np.median(np.array(list(meds.values())), axis=0)
    off = {t: np.linalg.norm(m - common) for t, m in meds.items()}
    print(f"offset: ({common[0]:.1f}, {common[1]:.1f}) mm; trays from it: median {np.median(list(off.values())):.1f}, "
          f"max {max(off.values()):.1f} mm (tray {max(off, key=off.get)})")


if __name__ == "__main__":
    main(sys.argv[1:])
