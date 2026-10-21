"""Round 1 (issue #213): does a tray's tag fix where the tray is? (15.5g)

Method: docs/metrology-log.md section 15.5g, written before this ran. Each tray's offset from its
tag to its FastSAM mask centre, in the tag's own frame, is learned from step 1 and used to predict
the tray centre in every later still; the prediction is compared with the masks FastSAM placed
right. Reads the tracking result (track-<name>.csv), the stills and rig.db; nothing is written to
the experiment folder.

    cd experiments/round1-trays
    PYTHONPATH=<worktree>/src <venv python> footprint.py --session 2026-10-19 track-pots19.csv

Writes footprint-<name>.csv (one row per measured position) next to this file and the outline
pictures to ~/scratch/round1-trays/footprint/.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict

import cv2
import numpy as np

import trays

LEARN_STEP = "1"
HOLDOUT_GAPS = ["2", "3", "4"]
TOUCHING = ["5", "6"]
PICTURES = ["085249_313204", "090504_356551"]  # step 6, both with trays 16 and 24 unplaced
OFF_MAX_MM = 50.0  # 15.5d: a position this far from its tray's median where nothing moved is wrong
OUT = trays.SCRATCH / "footprint"


def frame(heading_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """The tag's right and up directions in image coordinates (y down), heading clockwise from up."""
    t = math.radians(heading_deg)
    return np.array([math.cos(t), math.sin(t)]), np.array([math.sin(t), -math.cos(t)])


def to_tag(d: np.ndarray, heading_deg: float) -> np.ndarray:
    r, u = frame(heading_deg)
    return np.array([d @ r, d @ u])


def from_tag(v: np.ndarray, heading_deg: float) -> np.ndarray:
    r, u = frame(heading_deg)
    return v[0] * r + v[1] * u


def stats(xs: list[float]) -> str:
    if not xs:
        return "n 0"
    a = np.sort(np.asarray(xs))
    return (f"n {len(a):4d}  median {np.median(a):5.1f}  p95 {a[int(math.ceil(0.95 * len(a))) - 1]:5.1f}"
            f"  max {a[-1]:5.1f} mm")


def main(argv: list[str]) -> None:
    argv = trays.session_argv(argv)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("track", help="track-NAME.csv")
    ap.add_argument("--pictures", nargs="*", default=PICTURES, help="stills to draw the outlines on")
    ap.add_argument("--common", action="store_true",
                    help="one offset for every tray (the median of step 1) and the tilt from the tag alone")
    args = ap.parse_args(argv)
    name = args.track.removeprefix("track-").removesuffix(".csv") + ("-common" if args.common else "")
    from npec_rig.calibration_store import load_calibration

    rows = list(csv.DictReader(open(trays.HERE / args.track)))
    scales = {}

    def ppm_at(still: str, x: float, y: float) -> float:
        stem = trays.capture_info(still)["calibration"]
        if stem not in scales:
            scales[stem] = load_calibration(trays.RIG / "calibration" / f"{stem}.json").scale_field
        return scales[stem].px_per_mm(x, y)

    def good(r: dict) -> bool:
        return r["label"] == "measured" and not (r["off_median_mm"] and float(r["off_median_mm"]) > OFF_MAX_MM)

    # 1. Learn: each tray's median tag-frame offset (mm) and heading over step 1.
    learn = defaultdict(list)
    heading1 = defaultdict(list)
    for r in rows:
        if r["step"] == LEARN_STEP and good(r):
            tx, ty = float(r["tag_x_px"]), float(r["tag_y_px"])
            d = (np.array([float(r["x_px"]), float(r["y_px"])]) - [tx, ty]) / ppm_at(r["still"], tx, ty)
            learn[r["tray"]].append(to_tag(d, float(r["heading_deg"])))
            heading1[r["tray"]].append(float(r["heading_deg"]))
    offset = {t: np.median(np.array(v), axis=0) for t, v in learn.items()}
    print("step 1 offsets, tag frame (right, up), mm, and spread within step 1:")
    for t in sorted(offset, key=int):
        sp = [float(np.hypot(*(v - offset[t]))) for v in learn[t]]
        print(f"  tray {t:>2}: ({offset[t][0]:7.1f}, {offset[t][1]:7.1f})  n {len(sp)}  max {max(sp):4.1f}")
    allv = np.array(list(offset.values()))
    mid = np.median(allv, axis=0)
    print(f"4. single offset: median ({mid[0]:.1f}, {mid[1]:.1f}) mm; trays from it: "
          + stats([float(np.hypot(*(v - mid))) for v in allv]))
    if args.common:  # every tray placed by the same offset, nothing learned per tray
        offset = {t: mid for t in offset}

    # 2, 3. Predicted centre against the mask centre.
    out, dist = [], defaultdict(list)
    for r in rows:
        if r["tray"] not in offset or not good(r) or r["step"] == LEARN_STEP:
            continue
        tx, ty = float(r["tag_x_px"]), float(r["tag_y_px"])
        ppm = ppm_at(r["still"], tx, ty)
        pred = np.array([tx, ty]) + from_tag(offset[r["tray"]], float(r["heading_deg"])) * ppm
        d = float(np.hypot(pred[0] - float(r["x_px"]), pred[1] - float(r["y_px"]))) / ppm
        group = "gaps" if r["step"] in HOLDOUT_GAPS else "touching" if r["step"] in TOUCHING else "other"
        dist[group].append(d)
        dist[f"step {r['step']}"].append(d)
        out.append({"still": r["still"], "step": r["step"], "tray": r["tray"], "group": group,
                    "pred_x_px": round(pred[0]), "pred_y_px": round(pred[1]),
                    "mask_x_px": r["x_px"], "mask_y_px": r["y_px"], "dist_mm": round(d, 1)})
    print("predicted centre to mask centre:")
    for g in ["gaps", *[f"step {s}" for s in HOLDOUT_GAPS], "touching", *[f"step {s}" for s in TOUCHING]]:
        print(f"  {g:9s} {stats(dist[g])}")
    trays.write_csv(trays.HERE / f"footprint-{name}.csv", out)

    # 5. Pictures: predicted outlines on touching stills.
    OUT.mkdir(parents=True, exist_ok=True)
    by_still = defaultdict(list)
    for r in rows:
        by_still[r["still"]].append(r)
    for still in args.pictures:
        img = cv2.imread(str(trays.SESSION.stills_dir / f"{still}.jpg"))
        for r in by_still[still]:
            t = r["tray"]
            if t not in offset:
                continue
            tx, ty, h = float(r["tag_x_px"]), float(r["tag_y_px"]), float(r["heading_deg"])
            ppm = ppm_at(still, tx, ty)
            c = np.array([tx, ty]) + from_tag(offset[t], h) * ppm
            if args.common:  # the tag lies square in its cell: tray tilt is the heading off a right angle
                turn = (h + 45) % 90 - 45
            else:
                turn = (h - float(np.median(heading1[t])) + 90) % 180 - 90  # the tray's tilt from step 1
            box = cv2.boxPoints(((c[0], c[1]), (trays.TRAY_EW_MM * ppm, trays.TRAY_NS_MM * ppm), turn))
            colour = (0, 200, 0) if r["label"] == "measured" else (0, 0, 255)
            cv2.polylines(img, [box.astype(np.int32)], True, colour, 14)
            if r["x_px"]:
                cv2.circle(img, (int(float(r["x_px"])), int(float(r["y_px"]))), 40, (255, 255, 0), -1)
            cv2.circle(img, (int(c[0]), int(c[1])), 40, colour, -1)
            cv2.putText(img, f"tray {t}: {r['label']}", (int(c[0]) - 600, int(c[1]) + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 4, colour, 12)
        cv2.imwrite(str(OUT / f"{still}.jpg"), cv2.resize(img, None, fx=0.25, fy=0.25))
    print(f"pictures: {len(args.pictures)} in {OUT}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
